"""
Sentiment Agent — Market Psychology & Sentiment Analyst.

Measures human emotions and market psychology.
Detects fear/greed extremes, narrative cycles, and smart vs dumb money divergence.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from crewai import Agent, Crew, Process, Task

from db import get_collection
from db.collections import Collections
from tools.bedrock import get_llm
from tools.skill_loader import load_skill

log = logging.getLogger(__name__)

_BACKSTORY = """
You have studied market psychology for 20 years.
You understand that markets are human emotions at scale.
You know that fear and greed are more predictive than any technical indicator at extremes.
You have read every book on behavioural finance: Thinking Fast and Slow, Irrational Exuberance,
The Psychology of Money, Extraordinary Popular Delusions.
You are not fooled by narrative — you measure it.
You find divergence between what retail investors feel and what smart money is actually doing.
"""

_SYSTEM_PROMPT = """
Analyse the provided market sentiment data and produce a structured sentiment assessment.

Focus on:
1. Fear vs greed balance (VIX, put/call, Google Trends, news negativity)
2. Smart money vs dumb money divergence (institutional vs retail positioning)
3. Narrative cycle phases for each active theme
4. Contrarian signals at sentiment extremes

OUTPUT STRICTLY as JSON — no other text:
{{
  "market_emotion": "fear|greed|neutral",
  "fear_greed_score": 0-100,
  "vix_level": float,
  "put_call_ratio": float,
  "narrative_cycles": {{
    "AI": "phase_1_emerging|phase_2_hype|phase_3_disillusion|phase_4_dead_or_rebirth",
    "crypto": "...",
    "defence": "...",
    "space": "..."
  }},
  "smart_vs_dumb": {{
    "institutional": "cautiously_bullish|bullish|bearish|neutral",
    "retail": "euphoric|bullish|neutral|fearful|panic",
    "divergence": "description of divergence or null"
  }},
  "contrarian_signal": "signal description or null",
  "google_trends": {{
    "buy stocks": "rising|falling|peak|stable",
    "recession": "rising|falling|peak|stable",
    "AI stocks": "rising|falling|peak|stable"
  }},
  "summary": "2-3 sentence summary of overall market psychology",
  "confidence": 0-100
}}
"""


class SentimentAgent:
    """Measures market psychology and sentiment across fear/greed dimensions."""

    def __init__(self):
        self.skill = load_skill("sentiment")
        self._llm = get_llm("sentiment")

    def _gather_sentiment_data(self) -> dict:
        """Pre-fetch all sentiment inputs before running the LLM crew."""
        data: dict = {}

        try:
            from mcp_servers.market_mcp import get_put_call_ratio
            data["put_call_ratio"] = get_put_call_ratio()
        except Exception as e:
            data["put_call_ratio"] = {"error": str(e)}

        try:
            from tools.google_trends import get_trend_score
            import time
            trends = {}
            for kw in ["stock market crash", "recession", "how to buy stocks", "AI stocks", "bear market"]:
                trends[kw] = get_trend_score(kw)
                time.sleep(0.5)
            data["google_trends"] = trends
        except Exception as e:
            data["google_trends"] = {"error": str(e)}

        try:
            from mcp_servers.intelligence_mcp import get_reddit_sentiment
            data["reddit_wallstreetbets"] = get_reddit_sentiment("wallstreetbets")
        except Exception as e:
            data["reddit_wallstreetbets"] = {"error": str(e)}

        try:
            from mcp_servers.intelligence_mcp import search_news
            data["recent_headlines"] = search_news("stock market sentiment", days=3)
        except Exception as e:
            data["recent_headlines"] = {"error": str(e)}

        try:
            from tools.fred import get_dollar_index
            data["dxy"] = get_dollar_index()
        except Exception as e:
            data["dxy"] = {"error": str(e)}

        try:
            from mcp_servers.market_mcp import get_vix
            data["vix"] = get_vix()
        except Exception as e:
            data["vix"] = {"error": str(e)}

        return data

    def _build_crew(self, sentiment_data: dict) -> Crew:
        agent = Agent(
            role="Market Psychology & Sentiment Analyst",
            goal=(
                "Measure current market emotions, identify fear/greed extremes, "
                "detect smart vs dumb money divergence, and assess narrative cycle phases."
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
NOW APPLY YOUR SKILL TO THIS DATA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CURRENT SENTIMENT DATA:
VIX: {json.dumps(sentiment_data.get('vix', {}), indent=2)[:500]}
Put/Call Ratio: {json.dumps(sentiment_data.get('put_call_ratio', {}), indent=2)[:300]}
Google Trends: {json.dumps(sentiment_data.get('google_trends', {}), indent=2)[:1500]}
Reddit Sentiment (WSB): {json.dumps(sentiment_data.get('reddit_wallstreetbets', {}), indent=2)[:500]}
Recent Headlines: {json.dumps(sentiment_data.get('recent_headlines', []), indent=2)[:1500]}
DXY: {json.dumps(sentiment_data.get('dxy', {}), indent=2)[:200]}

Based on the above data, produce a comprehensive sentiment assessment.
Output only valid JSON.
            """,
            agent=agent,
            expected_output="JSON sentiment assessment with fear/greed score, narrative cycles, and contrarian signals",
        )

        return Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    def analyse(self, run_id: str | None = None, save: bool = True) -> dict:
        """
        Run sentiment analysis.
        Returns sentiment dict and optionally persists to MongoDB.
        """
        run_id = run_id or str(uuid.uuid4())
        log.info("[SentimentAgent] Gathering sentiment data...")
        sentiment_data = self._gather_sentiment_data()

        log.info("[SentimentAgent] Running LLM analysis...")
        try:
            crew = self._build_crew(sentiment_data)
            result = crew.kickoff()

            raw_text = str(result)
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()

            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            analysis = json.loads(raw_text[start:end])

        except Exception as e:
            log.error(f"[SentimentAgent] LLM analysis failed: {e}")
            analysis = {
                "market_emotion": "unknown",
                "fear_greed_score": 50,
                "error": str(e),
                "summary": "Sentiment analysis failed — data may be unavailable.",
                "confidence": 0,
            }

        analysis["run_id"] = run_id
        analysis["captured_at"] = datetime.now(timezone.utc).isoformat()
        analysis["raw_data"] = {k: v for k, v in sentiment_data.items() if "error" not in str(v)[:20]}

        if save:
            try:
                col = get_collection(Collections.SENTIMENT_HISTORY)
                col.insert_one({k: v for k, v in analysis.items() if k != "_id"})
                log.info(f"[SentimentAgent] Saved to {Collections.SENTIMENT_HISTORY}")
            except Exception as e:
                log.warning(f"[SentimentAgent] Failed to save to MongoDB: {e}")

        log.info(f"[SentimentAgent] Done — emotion={analysis.get('market_emotion')}, score={analysis.get('fear_greed_score')}")
        return analysis
