"""
Agent 1 — World Intelligence Agent.

Scans global news and geopolitical events to surface macro themes
that will drive market opportunities over the next days-to-months.
"""

import json
import re
import uuid
from datetime import datetime, timezone

from crewai import Agent, Task, Crew, Process

from db import get_collection
from db.collections import Collections
from models import Theme, ThemeStatus
from tools.bedrock import get_llm
from tools.skill_loader import load_skill


_BACKSTORY = """
Chief World Events Intelligence Analyst. Deep knowledge of geopolitics,
monetary history, and market cycles. Focus on structural changes and
root causes behind surface narratives. Output precise structured intelligence.
"""

_SYSTEM_PROMPT = """
You are scanning today's world events across ALL global markets — US, Europe,
Asia, India, Australia, Canada, Latin America, and Emerging Markets — to
identify macro themes that will move markets globally.

For each theme you identify:
1. Assign a unique ID (SCREAMING_SNAKE_CASE)
2. Rate urgency 1-10 (10 = market-moving today, 1 = slow-burn multi-year)
3. Classify status: hot (actively escalating), warm (developing),
   cooling (resolving), new (just emerged)
4. Tag affected_regions (e.g. ["ASIA", "EUROPE", "US", "GLOBAL"])
5. Provide 3-5 evidence headlines

OUTPUT STRICTLY as JSON matching this schema — no other text:
{
  "themes": [
    {
      "id": "THEME_ID",
      "name": "Short descriptive name",
      "urgency": 8,
      "status": "hot",
      "affected_regions": ["GLOBAL"],
      "summary": "2-3 sentence explanation of what is happening and why it matters",
      "evidence": ["headline1", "headline2", "headline3"]
    }
  ]
}

Identify 8-12 themes covering: US macro, European outlook, Asian dynamics
(China/Japan/Korea/India), commodity moves, currency shifts, and structural
technology/geopolitical trends. Include both fast-moving events and slow burns.
"""


class WorldIntelligenceAgent:
    """Orchestrates the world intelligence scanning crew."""

    def __init__(self):
        self.skill = load_skill("world_intelligence")
        self._llm = get_llm("world")

    def _build_crew(self, news_context: str) -> Crew:
        agent = Agent(
            role="Chief World Events Intelligence Analyst",
            goal=(
                "Scan global news and geopolitical events. Identify what is "
                "happening RIGHT NOW that will move markets. Output a structured "
                "list of active themes with urgency scores."
            ),
            backstory=_BACKSTORY,
            llm=self._llm,
            verbose=True,
            allow_delegation=False,
        )

        task = Task(
            description=f"""
{self.skill}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOW APPLY YOUR SKILL TO TODAY'S DATA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Today's news context:
{news_context}

Identify and rank macro themes. Output only valid JSON matching the schema above.
            """,
            agent=agent,
            expected_output="JSON object with a 'themes' array",
        )

        return Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    def _fetch_news_context(self) -> str:
        """Pull today's headlines from all major global regions."""
        try:
            from tools.news_api import get_global_headlines, search_everything

            context_lines = []

            # Regional headlines (US, UK, India, Japan, China, etc.)
            regional = get_global_headlines()
            for region, articles in regional.items():
                for a in articles[:3]:  # 3 per region keeps tokens manageable
                    title = a.get("title", "")
                    if title and "[Removed]" not in title:
                        published = a.get("publishedAt", "")[:10]
                        context_lines.append(f"[{region}][{published}] {title}")

            # Global topic searches (English only, but covers cross-border stories)
            searches = [
                ("geopolitical war conflict sanctions trade", 2),
                ("federal reserve ECB BOJ central bank interest rates", 2),
                ("China economy property tech regulation", 2),
                ("India economy growth Modi", 2),
                ("Europe energy recession inflation", 2),
                ("emerging markets currency debt", 2),
            ]
            for query, days in searches:
                for a in search_everything(query, days)[:3]:
                    title = a.get("title", "")
                    source = a.get("source", {}).get("name", "") if isinstance(a.get("source"), dict) else ""
                    if title and "[Removed]" not in title:
                        context_lines.append(f"[GLOBAL][{a.get('publishedAt','')[:10]}] {source}: {title}")

            # Deduplicate and cap
            seen, unique = set(), []
            for line in context_lines:
                if line not in seen:
                    seen.add(line)
                    unique.append(line)

            return "\n".join(unique[:40])  # 40 headlines across all regions
        except Exception as e:
            return f"News fetch error: {e}. Use your training knowledge for current global macro context."

    def _fetch_recent_themes(self) -> list[dict]:
        """Load previously detected themes so agent can track evolution."""
        try:
            return list(
                get_collection(Collections.WORLD_THEMES)
                .find({}, {"_id": 0})
                .sort("detected_at", -1)
                .limit(10)
            )
        except Exception:
            return []

    @staticmethod
    def _parse_json_tolerant(raw: str) -> dict | None:
        """
        Parse JSON that may be truncated (LLM hit token limit mid-response).
        Tries clean parse first, then progressively repairs truncated output.
        """
        # 1. Clean parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # 2. Find outermost { ... }
        start = raw.find("{")
        if start < 0:
            return None
        # Try from last } backwards
        for end in range(len(raw), start, -1):
            if raw[end - 1] == "}":
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    continue

        # 3. Response was truncated inside the themes array — recover complete themes
        # Find the "themes" array start and extract only fully-closed objects
        themes_match = re.search(r'"themes"\s*:\s*\[', raw)
        if not themes_match:
            return None

        array_start = themes_match.end() - 1  # position of '['
        themes = []
        depth = 0
        obj_start = None

        for i, ch in enumerate(raw[array_start:], start=array_start):
            if ch == "{":
                if depth == 1:  # start of a top-level theme object
                    obj_start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 1 and obj_start is not None:  # closed a theme object
                    try:
                        themes.append(json.loads(raw[obj_start:i + 1]))
                    except json.JSONDecodeError:
                        pass
                    obj_start = None
            elif ch == "[":
                depth += 1
            elif ch == "]" and depth == 1:
                break  # clean end of array

        if themes:
            print(f"[WorldIntelligenceAgent] Recovered {len(themes)} themes from truncated JSON")
            return {"themes": themes}

        return None

    def scan(self, run_id: str | None = None) -> list[Theme]:
        """
        Run the world intelligence scan.
        Returns list of Theme objects and persists them to MongoDB.
        """
        run_id = run_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        news_context = self._fetch_news_context()
        recent_themes = self._fetch_recent_themes()

        if recent_themes:
            recent_summary = "\n".join(
                f"- {t.get('name', '')} (last seen: {t.get('detected_at', '')[:10]})"
                for t in recent_themes[:5]
            )
            news_context += f"\n\nPreviously detected themes (for continuity):\n{recent_summary}"

        crew = self._build_crew(news_context)
        result = crew.kickoff()

        # Parse JSON output from the agent
        raw_text = str(result)
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()

        data = self._parse_json_tolerant(raw_text)
        if data is None:
            print(f"[WorldIntelligenceAgent] Failed to parse JSON: {raw_text[:200]}")
            return []

        themes = []
        col = get_collection(Collections.WORLD_THEMES)

        for t in data.get("themes", []):
            theme = Theme(
                id=t.get("id", "UNKNOWN"),
                name=t.get("name", ""),
                urgency=min(max(int(t.get("urgency", 5)), 1), 10),
                status=ThemeStatus(t.get("status", "warm")),
                summary=t.get("summary", ""),
                evidence=t.get("evidence", []),
                detected_at=now,
                run_id=run_id,
            )
            themes.append(theme)

            # Persist to MongoDB
            col.update_one(
                {"id": theme.id, "run_id": run_id},
                {"$set": theme.to_mongo()},
                upsert=True,
            )

        print(f"[WorldIntelligenceAgent] Detected {len(themes)} themes for run {run_id}")
        return themes
