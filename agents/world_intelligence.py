"""
Agent 1 — World Intelligence Agent.

Scans global news and geopolitical events to surface macro themes
that will drive market opportunities over the next days-to-months.
"""

import json
import uuid
from datetime import datetime, timezone

from crewai import Agent, Task, Crew, Process

from db import get_collection
from db.collections import Collections
from models import Theme, ThemeStatus
from tools.bedrock import get_llm


_BACKSTORY = """
You are a Chief World Events Intelligence Analyst with deep knowledge of
geopolitics, monetary history, and market cycles. You have studied every
major financial crisis, currency transition, and geopolitical shift since
1900. You read between the lines of news — most events have hidden root
causes that surface narratives obscure.

You understand:
- The petrodollar system and how its erosion affects global capital flows
- How central bank policy decisions create second and third-order effects
- How military conflicts shift supply chains and energy markets
- How technology transitions create decade-long investment themes
- How demographic shifts create inevitable macro tailwinds and headwinds

You are not fooled by noise. You focus on structural changes.
You output precise, structured intelligence — not vague summaries.
"""

_SYSTEM_PROMPT = """
You are scanning today's world events to identify macro themes that will
move markets. For each theme you identify:

1. Assign a unique ID (SCREAMING_SNAKE_CASE)
2. Rate urgency 1-10 (10 = market-moving today, 1 = slow-burn multi-year)
3. Classify status: hot (actively escalating), warm (developing),
   cooling (resolving), new (just emerged)
4. Provide 3-5 evidence headlines

OUTPUT STRICTLY as JSON matching this schema — no other text:
{
  "themes": [
    {
      "id": "THEME_ID",
      "name": "Short descriptive name",
      "urgency": 8,
      "status": "hot",
      "summary": "2-3 sentence explanation of what is happening and why it matters",
      "evidence": ["headline1", "headline2", "headline3"]
    }
  ]
}

Identify 5-10 themes. Include both fast-moving events and structural shifts.
"""


class WorldIntelligenceAgent:
    """Orchestrates the world intelligence scanning crew."""

    def __init__(self):
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
{_SYSTEM_PROMPT}

Today's news context:
{news_context}

Identify and rank macro themes. Output only valid JSON.
            """,
            agent=agent,
            expected_output="JSON object with a 'themes' array",
        )

        return Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    def _fetch_news_context(self) -> str:
        """Pull today's headlines to give the agent raw material."""
        try:
            from tools.news_api import get_top_headlines, search_everything
            headlines = get_top_headlines("business")
            geopolitical = search_everything("geopolitical war conflict sanctions", days=2)
            macro = search_everything("federal reserve inflation recession GDP", days=2)

            all_articles = headlines + geopolitical + macro
            context_lines = []
            for a in all_articles[:40]:
                title = a.get("title", "")
                source = a.get("source", {}).get("name", "unknown") if isinstance(a.get("source"), dict) else "unknown"
                published = a.get("publishedAt", "")[:10]
                if title:
                    context_lines.append(f"[{published}] {source}: {title}")

            return "\n".join(context_lines)
        except Exception as e:
            return f"News fetch error: {e}. Use your training knowledge for current macro context."

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
        try:
            # Extract JSON if wrapped in markdown code block
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            data = json.loads(raw_text)
        except (json.JSONDecodeError, IndexError):
            # Fallback: try to find JSON object in output
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw_text[start:end])
            else:
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
