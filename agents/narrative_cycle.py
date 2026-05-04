"""
Narrative Cycle Detector — tracks where investment themes sit in their hype cycle.

Based on the Gartner Hype Cycle adapted for markets:
  Phase 1: Innovation trigger    — early awareness, maximum opportunity
  Phase 2: Peak of inflated expectations — maximum hype, maximum danger
  Phase 3: Trough of disillusionment  — short opportunity
  Phase 4: Slope of enlightenment / Death — contrarian opportunity or permanent death
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from crewai import Agent, Crew, Process, Task

from db import get_collection
from db.collections import Collections
from tools.bedrock import get_llm
from tools.skill_loader import load_skill

log = logging.getLogger(__name__)

# Default themes to track — updated from MongoDB world_themes when available
DEFAULT_THEMES = [
    {"id": "AI_BOOM", "name": "AI / Artificial Intelligence"},
    {"id": "CRYPTO", "name": "Cryptocurrency / Web3"},
    {"id": "DEFENCE", "name": "Defence & Military Tech"},
    {"id": "SPACE", "name": "Space Exploration"},
    {"id": "CLEAN_ENERGY", "name": "Clean Energy / Green Tech"},
]

_SYSTEM_PROMPT = """
For the given investment theme, determine its current position in the market hype cycle.

Use the following phase definitions:
  phase_1_emerging:        Google Trends rising from low base, specialist media only,
                           early institutional money moving in, retail unaware
  phase_2_hype:            Google Trends at/near peak, mainstream media daily coverage,
                           everyone on Reddit discussing it, retail FOMO maximum,
                           IPOs in space accelerating, valuations disconnected
  phase_3_disillusion:     Google Trends falling from peak, negative news cycle,
                           Reddit going quiet or turning negative, IPOs pulled/failing
  phase_4_dead_or_rebirth: Google Trends at floor, minimal media, only believers remain,
                           valuations at historical lows, next cycle opportunity

OUTPUT STRICTLY as JSON — no other text:
{{
  "theme": "THEME_ID",
  "current_phase": "phase_1_emerging|phase_2_hype|phase_3_disillusion|phase_4_dead_or_rebirth",
  "phase_score": 0-100,
  "trend": "accelerating|approaching_peak|at_peak|declining|bottoming",
  "google_peak": "YYYY-MM-DD or null",
  "news_volume_30d": "high|medium|low",
  "reddit_sentiment": "euphoric|bullish|neutral|bearish|dead",
  "action": "recommendation for investors",
  "historical_note": "comparison to a historical hype cycle",
  "confidence": 0-100
}}
"""


class NarrativeCycleAgent:
    """Tracks hype cycle phase for each investment theme."""

    def __init__(self):
        self.skill = load_skill("narrative_cycle")
        self._llm = get_llm("narrative")

    def _gather_theme_data(self, theme: dict) -> dict:
        """Pre-fetch Google Trends + news + Reddit data for a theme."""
        data: dict = {"theme_id": theme["id"], "theme_name": theme["name"]}
        kw = theme["name"]

        try:
            from tools.google_trends import get_trend_score
            data["google_trends"] = get_trend_score(kw)
            time.sleep(0.5)
        except Exception as e:
            data["google_trends"] = {"error": str(e)}

        try:
            from mcp_servers.intelligence_mcp import search_news
            data["recent_news"] = search_news(kw, days=7)
        except Exception as e:
            data["recent_news"] = {"error": str(e)}

        try:
            from mcp_servers.intelligence_mcp import get_reddit_sentiment
            data["reddit"] = get_reddit_sentiment(kw)
        except Exception as e:
            data["reddit"] = {"error": str(e)}

        # Pull historical narrative data from MongoDB if available
        try:
            col = get_collection(Collections.NARRATIVE_CYCLES)
            history = list(col.find(
                {"theme": theme["id"]},
                {"_id": 0, "current_phase": 1, "captured_at": 1},
                sort=[("captured_at", -1)],
                limit=5,
            ))
            data["history"] = history
        except Exception as e:
            data["history"] = []

        return data

    def _build_crew(self, theme: dict, theme_data: dict) -> Crew:
        agent = Agent(
            role="Investment Narrative & Hype Cycle Analyst",
            goal=(
                f"Determine the current hype cycle phase for the '{theme['name']}' theme "
                "and provide actionable guidance for investors."
            ),
            backstory=(
                "You are a market cycle expert who has studied every major investment mania "
                "and crash from the South Sea Bubble to the dot-com bust to crypto 2022. "
                "You can read when a narrative is peaking before the crowd realises it. "
                "You use data, not intuition — Google Trends, news volume, and Reddit sentiment "
                "are your instruments."
            ),
            llm=self._llm,
            verbose=True,
            allow_delegation=False,
        )

        task = Task(
            description=f"""
{self.skill}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOW APPLY YOUR SKILL TO THIS THEME:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

THEME: {theme['id']} — {theme['name']}

GOOGLE TRENDS DATA:
{json.dumps(theme_data.get('google_trends', {}), indent=2)[:600]}

RECENT NEWS (7 days):
{json.dumps(theme_data.get('recent_news', []), indent=2)[:1000]}

REDDIT SENTIMENT:
{json.dumps(theme_data.get('reddit', {}), indent=2)[:400]}

HISTORICAL PHASE READINGS:
{json.dumps(theme_data.get('history', []), indent=2)[:400]}

Apply all 6 data points from your phase detection protocol. Output only valid JSON matching the schema above.
            """,
            agent=agent,
            expected_output="JSON hype cycle phase assessment for this theme",
        )

        return Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    def analyse(self, themes: list[dict] | None = None, run_id: str | None = None) -> list[dict]:
        """
        Analyse hype cycle phase for each theme.
        Returns list of phase assessments and persists to MongoDB.
        """
        run_id = run_id or str(uuid.uuid4())

        if themes is None:
            # Try to load active themes from MongoDB, fall back to defaults
            try:
                col = get_collection(Collections.WORLD_THEMES)
                raw = list(col.find({}, {"_id": 0, "id": 1, "name": 1}, sort=[("urgency", -1)], limit=8))
                themes = [{"id": t.get("id", "UNKNOWN"), "name": t.get("name", "Unknown")} for t in raw if t.get("name")]
                if not themes:
                    themes = DEFAULT_THEMES
            except Exception:
                themes = DEFAULT_THEMES

        col = get_collection(Collections.NARRATIVE_CYCLES)
        results = []

        for theme in themes:
            log.info(f"[NarrativeCycleAgent] Analysing theme: {theme['id']}")
            try:
                theme_data = self._gather_theme_data(theme)
                crew = self._build_crew(theme, theme_data)
                result = crew.kickoff()

                raw_text = str(result)
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()

                start = raw_text.find("{")
                end = raw_text.rfind("}") + 1
                assessment = json.loads(raw_text[start:end])

                assessment["run_id"] = run_id
                assessment["captured_at"] = datetime.now(timezone.utc).isoformat()

                col.update_one(
                    {"theme": theme["id"], "run_id": run_id},
                    {"$set": assessment},
                    upsert=True,
                )
                results.append(assessment)
                log.info(f"[NarrativeCycleAgent] {theme['id']} → {assessment.get('current_phase')}")

            except Exception as e:
                log.error(f"[NarrativeCycleAgent] Error on {theme['id']}: {e}")
                results.append({"theme": theme["id"], "error": str(e), "run_id": run_id})

        log.info(f"[NarrativeCycleAgent] Completed {len(results)} theme analyses")
        return results

    def get_phase_context(self) -> dict:
        """
        Returns the most recent phase for each tracked theme.
        Used as context input for ranking and causal agents.
        """
        try:
            col = get_collection(Collections.NARRATIVE_CYCLES)
            # Get latest reading per theme
            pipeline = [
                {"$sort": {"captured_at": -1}},
                {"$group": {"_id": "$theme", "latest": {"$first": "$$ROOT"}}},
                {"$replaceRoot": {"newRoot": "$latest"}},
            ]
            phases = list(col.aggregate(pipeline))
            return {p.get("theme", "UNKNOWN"): {k: v for k, v in p.items() if k != "_id"} for p in phases}
        except Exception as e:
            log.warning(f"[NarrativeCycleAgent] get_phase_context failed: {e}")
            return {}
