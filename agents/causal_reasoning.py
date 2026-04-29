"""
Agent 2 — Causal Reasoning Agent.

For each macro theme, traces the ROOT CAUSE 3-4 levels deep.
Maps ripple effects to investment theses across 5 time horizons.
Think: Ray Dalio + George Soros + Howard Marks combined.
"""

import json
import uuid
from datetime import datetime, timezone

from crewai import Agent, Task, Crew, Process

from db import get_collection
from db.collections import Collections
from models import Theme
from tools.bedrock import get_llm


_BACKSTORY = """
Macro Causal Analyst applying Dalio debt cycle, Soros reflexivity, and
Marks second-level thinking. Trace root causes 3-4 levels deep.
Use historical parallels (1971 Nixon shock, 2008 GFC, Weimar, Bretton Woods).
Never accept surface narratives. Ask: who benefits, what system is contested,
what happened last time. Find the non-obvious investment thesis.
"""

_SYSTEM_PROMPT = """
For the given macro theme, perform ROOT CAUSE analysis 3-4 levels deep.
Then derive investment theses for 5 time horizons.

Causal depth means:
Level 1: The surface event (what headlines say)
Level 2: The economic/political mechanism driving it
Level 3: The systemic imbalance that made level 2 possible
Level 4: The deep historical/structural force at work

OUTPUT STRICTLY as JSON — no other text:
{
  "theme_id": "THEME_ID",
  "surface_narrative": "what headlines say",
  "root_cause": "the real driver at level 3-4",
  "historical_parallel": {
    "event": "specific historical event",
    "what_happened": "market/asset outcomes",
    "lesson": "what this implies for today"
  },
  "causal_chain": [
    "Level 1: ...",
    "Level 2: ...",
    "Level 3: ...",
    "Level 4: ..."
  ],
  "second_order": ["effect1", "effect2", "effect3"],
  "contrarian_take": "the non-obvious play that smart money sees",
  "theses": {
    "quarter":  {"sectors": ["sector1"], "tickers_to_watch": ["A", "B"], "avoid_sectors": ["x"], "reason": "..."},
    "one_year": {"sectors": ["sector1"], "tickers_to_watch": ["A", "B"], "avoid_sectors": ["x"], "reason": "..."},
    "two_year": {"sectors": ["sector1"], "tickers_to_watch": ["A", "B"], "avoid_sectors": ["x"], "reason": "..."},
    "five_year": {"sectors": ["sector1"], "tickers_to_watch": ["A", "B"], "avoid_sectors": ["x"], "reason": "..."},
    "ten_year": {"sectors": ["sector1"], "tickers_to_watch": ["A", "B"], "avoid_sectors": ["x"], "reason": "..."}
  },
  "risk_flags": ["condition that would invalidate thesis"],
  "sentiment_alignment": "bullish sentiment CONFIRMS causal thesis OR WARNING — sentiment CONTRADICTS causal thesis (contrarian signal)",
  "confidence": 75
}
"""


class CausalReasoningAgent:
    """Performs root-cause analysis on world themes."""

    def __init__(self):
        self._llm = get_llm("causal")

    def _build_crew(self, theme: Theme, macro_context: str) -> Crew:
        agent = Agent(
            role="Macro Causal Analyst — Root Cause Specialist",
            goal=(
                f"Trace the root cause of '{theme.name}' 3-4 levels deep. "
                "Map ripple effects across currencies, commodities, sectors, "
                "and time horizons. Find the non-obvious investment thesis."
            ),
            backstory=_BACKSTORY,
            llm=self._llm,
            verbose=True,
            allow_delegation=False,
        )

        task = Task(
            description=f"""
{_SYSTEM_PROMPT}

THEME TO ANALYSE:
ID: {theme.id}
Name: {theme.name}
Urgency: {theme.urgency}/10
Summary: {theme.summary}
Evidence: {json.dumps(theme.evidence)}

CURRENT MACRO CONTEXT:
{macro_context}

Perform 4-level causal analysis. Output only valid JSON.
            """,
            agent=agent,
            expected_output="JSON object with causal analysis and theses per horizon",
        )

        return Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    def _fetch_macro_context(self) -> str:
        """Pull FRED data as grounding for causal analysis."""
        lines = []
        try:
            from tools.fred import get_dollar_index, get_inflation_data, get_fed_funds_rate, get_yield_curve
            dxy = get_dollar_index()
            lines.append(f"DXY (USD Index): {dxy.get('latest', {}).get('value', 'N/A')}")
            fed = get_fed_funds_rate()
            rates = fed.get("fed_funds_rate", [])
            if rates:
                lines.append(f"Fed Funds Rate: {rates[0].get('value', 'N/A')}%")
            yc = get_yield_curve()
            obs = yc.get("t10y2y", [])
            if obs:
                lines.append(f"Yield Curve (10Y-2Y): {obs[0].get('value', 'N/A')}%")
            cpi = get_inflation_data()
            cpi_obs = cpi.get("cpi", [])
            if cpi_obs:
                lines.append(f"CPI YoY approx: see FRED CPIAUCSL")
        except Exception as e:
            lines.append(f"FRED data unavailable: {e}")
        return "\n".join(lines) if lines else "Macro data unavailable."

    def analyse(self, themes: list[Theme], run_id: str | None = None, sentiment_report: dict | None = None) -> list[dict]:
        """
        Run causal analysis for each theme.
        Returns list of thesis dicts and persists to MongoDB.
        """
        run_id = run_id or str(uuid.uuid4())
        macro_context = self._fetch_macro_context()
        col = get_collection(Collections.CAUSAL_THESES)
        results = []

        sentiment_context = ""
        if sentiment_report:
            emotion = sentiment_report.get("market_emotion", "unknown")
            score = sentiment_report.get("fear_greed_score", 50)
            contrarian = sentiment_report.get("contrarian_signal", "")
            sentiment_context = (
                f"\nSENTIMENT CONTEXT:\n"
                f"  Market emotion: {emotion} (fear/greed score: {score}/100)\n"
                f"  Contrarian signal: {contrarian}\n"
                f"  Summary: {sentiment_report.get('summary', '')}\n"
            )

        for theme in themes:
            print(f"[CausalReasoningAgent] Analysing theme: {theme.id}")
            try:
                crew = self._build_crew(theme, macro_context + sentiment_context)
                result = crew.kickoff()

                raw_text = str(result)
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()

                start = raw_text.find("{")
                end = raw_text.rfind("}") + 1
                thesis = json.loads(raw_text[start:end])

                thesis["run_id"] = run_id
                thesis["analysed_at"] = datetime.now(timezone.utc).isoformat()

                col.update_one(
                    {"theme_id": thesis.get("theme_id"), "run_id": run_id},
                    {"$set": thesis},
                    upsert=True,
                )
                results.append(thesis)

            except Exception as e:
                print(f"[CausalReasoningAgent] Error on {theme.id}: {e}")
                results.append({"theme_id": theme.id, "error": str(e), "run_id": run_id})

        print(f"[CausalReasoningAgent] Completed {len(results)} causal analyses")
        return results
