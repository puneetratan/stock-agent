"""
Agent 8 — Ranking Agent.

Synthesises all deep analysis reports into final ranked picks per horizon.
The most important agent — its output is what the user reads every morning.
"""

import json
import time
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from crewai import Agent, Task, Crew, Process

from db import get_collection
from db.collections import Collections
from models import FinalReport, HorizonPicks, Signal, SignalType, MarketRegime
from tools.bedrock import get_llm
from tools.skill_loader import load_skill


def _json_default(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _repair_json(raw: str) -> dict:
    """
    Best-effort JSON repair for truncated or trailing-comma LLM output.
    Tries progressively more aggressive fixes until one parses.
    """
    import re

    attempts = [
        raw,
        # Remove trailing commas before ] or }
        re.sub(r",\s*([}\]])", r"\1", raw),
    ]

    # Also try truncating at each closing brace from the end
    for i in range(len(raw) - 1, max(len(raw) - 500, 0), -1):
        if raw[i] == "}":
            attempts.append(raw[: i + 1])

    for attempt in attempts:
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue

    print("[RankingAgent] JSON repair failed — returning empty report")
    return {}


_BACKSTORY = """
You are the Chief Investment Strategist. Every morning you review all intelligence
gathered by a team of specialised analysts and synthesise it into clear, ranked
investment recommendations.

You apply the following ranking framework:
1. CONVICTION = (fundamental_score × 0.35) + (technical_score × 0.25) +
                (sentiment_score × 0.20) + (geo_score × 0.20)
2. Adjust conviction DOWN if geo risk is "high" or "critical"
3. Adjust conviction UP if stock is directly aligned to hot macro themes (urgency ≥ 8)
4. Contrarian picks get their own category — not included in main ranks

You know that the best investments are boring on the surface but compelling
at the second-order level. You are not impressed by hype. You are impressed
by confluence: technical + fundamental + macro alignment.

You think in time horizons:
- Quarter: momentum plays, short-term catalysts
- 1 year: earnings re-rating, narrative shifts completing
- 2 year: structural transitions (e.g., AI infrastructure build-out)
- 5 year: category leaders in durable themes
- 10 year: inevitable demographic, energy, or technology transitions

You always include a market regime assessment.
You always include stocks to AVOID — not just stocks to buy.
You always include one contrarian pick per horizon — the non-obvious play.
"""

_RANKING_PROMPT = """
You are the Chief Investment Strategist. Synthesise all reports and produce
a compact ranked investment report.

CAUSAL THESES:
{causal_theses}

SENTIMENT REPORT:
{sentiment_report}

NARRATIVE CYCLE PHASES:
{narrative_phases}

ALL DEEP ANALYSIS REPORTS:
{all_reports}

NARRATIVE CYCLE RULES — apply these adjustments before scoring:
  - phase_1_emerging themes: BOOST conviction for stocks in that theme (+5 pts)
  - phase_2_hype themes: FLAG as late-cycle risk, add to risks list
  - phase_3_disillusion themes: LOWER conviction, flag short opportunity
  - phase_4_dead_or_rebirth themes: contrarian flag only, long-horizon only

RANKING FORMULA:
conviction = (fundamental_score × 0.35) + (technical_score × 0.25) +
             (sentiment_score × 0.20) + (geo_score × 0.20)

Scores: fundamental: exceptional=90, high=75, average=50, poor=25
        technical: bullish=80, neutral=50, bearish=20
        sentiment: sentiment_score × 10
        geo: low_risk=80, medium_risk=60, high_risk=30, critical=10

Output STRICTLY as JSON — no other text. Keep thesis fields to 1 sentence max.
Include "region" and "exchange" on every pick (e.g. region: "JAPAN", exchange: "TSE"):
{{
  "market_regime": {{"label": "string", "description": "1 sentence", "recommended_posture": "1 sentence"}},
  "causal_summary": "2-3 sentences max",
  "analyst_note": "2-3 sentences max",
  "horizons": {{
    "quarter":   {{"picks": [{{"ticker": "X", "region": "US", "exchange": "NASDAQ", "confidence": 80, "thesis": "1 sentence", "risks": ["r1"], "theme_ids": [], "is_contrarian": false, "technical_score": 80, "sentiment_score": 8.0, "fundamental_score": 85, "geo_score": 70}}], "avoid": [{{"ticker": "Y", "region": "US", "exchange": "NYSE", "confidence": 70, "thesis": "1 sentence", "risks": []}}], "contrarian_picks": [{{"ticker": "Z", "region": "JAPAN", "exchange": "TSE", "confidence": 60, "thesis": "1 sentence", "risks": [], "is_contrarian": true}}]}},
    "one_year":  {{"picks": [], "avoid": [], "contrarian_picks": []}},
    "two_year":  {{"picks": [], "avoid": [], "contrarian_picks": []}},
    "five_year": {{"picks": [], "avoid": [], "contrarian_picks": []}},
    "ten_year":  {{"picks": [], "avoid": [], "contrarian_picks": []}}
  }}
}}
"""


class RankingAgent:
    """Synthesises all agent outputs into the final ranked report."""

    def __init__(self):
        self.skill = load_skill("ranking")
        self._llm = get_llm("ranking")

    def _build_crew(self, causal_theses: list[dict], all_reports: dict, sentiment_report: dict | None = None, narrative_phases: dict | None = None) -> Crew:
        agent = Agent(
            role="Chief Investment Strategist",
            goal=(
                "Synthesise all analysis reports into final ranked investment "
                "picks per time horizon with conviction scores."
            ),
            backstory=_BACKSTORY,
            llm=self._llm,
            verbose=True,
            allow_delegation=False,
        )

        # Truncate reports to stay within context window
        reports_json = json.dumps(all_reports, indent=2)
        if len(reports_json) > 40000:
            # Trim to most relevant fields only
            slim = {
                "market_reports": [
                    {"ticker": r.get("ticker"), "technical_signal": r.get("technical_signal"),
                     "rsi": r.get("rsi"), "macd": r.get("macd"), "summary": r.get("summary")}
                    for r in all_reports.get("market_reports", [])
                ],
                "news_reports": [
                    {"ticker": r.get("ticker"), "sentiment_score": r.get("sentiment_score"),
                     "analyst_consensus": r.get("analyst_consensus"), "summary": r.get("summary")}
                    for r in all_reports.get("news_reports", [])
                ],
                "fundamentals_reports": [
                    {"ticker": r.get("ticker"), "revenue_growth_yoy": r.get("revenue_growth_yoy"),
                     "business_quality": r.get("business_quality"), "valuation": r.get("valuation"),
                     "summary": r.get("summary")}
                    for r in all_reports.get("fundamentals_reports", [])
                ],
                "geo_reports": [
                    {"ticker": r.get("ticker"), "risk_level": r.get("risk_level"),
                     "macro_tailwinds": r.get("macro_tailwinds", [])[:2], "summary": r.get("summary")}
                    for r in all_reports.get("geo_reports", [])
                ],
            }
            reports_json = json.dumps(slim, indent=2, default=_json_default)

        sentiment_json = json.dumps(sentiment_report or {}, indent=2, default=_json_default)[:1500]
        narrative_json = json.dumps(narrative_phases or {}, indent=2, default=_json_default)[:1500]

        task = Task(
            description=self.skill + "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nNOW APPLY YOUR SKILL TO SYNTHESISE ALL REPORTS:\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n" + _RANKING_PROMPT.format(
                causal_theses=json.dumps(causal_theses, indent=2, default=_json_default)[:8000],
                sentiment_report=sentiment_json,
                narrative_phases=narrative_json,
                all_reports=reports_json[:40000],
            ),
            agent=agent,
            expected_output="JSON object with ranked picks per horizon",
        )

        return Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    def rank(self, run_id: str) -> FinalReport:
        """
        Pull all agent reports from MongoDB, synthesise, and produce FinalReport.
        """
        print(f"[RankingAgent] Pulling all reports for run {run_id}")
        all_reports = get_collection(Collections.MARKET_DATA).database
        # Fetch all reports via mongo directly
        all_reports_dict = {
            "market_reports": list(get_collection(Collections.MARKET_DATA).find({"run_id": run_id}, {"_id": 0})),
            "news_reports": list(get_collection(Collections.NEWS_SENTIMENT).find({"run_id": run_id}, {"_id": 0})),
            "fundamentals_reports": list(get_collection(Collections.FUNDAMENTALS).find({"run_id": run_id}, {"_id": 0})),
            "geo_reports": list(get_collection(Collections.GEO_MACRO).find({"run_id": run_id}, {"_id": 0})),
        }

        causal_theses = list(get_collection(Collections.CAUSAL_THESES).find({"run_id": run_id}, {"_id": 0}))
        screener_results = list(get_collection(Collections.SCREENER_RESULTS).find({"run_id": run_id}, {"_id": 0}))

        # Load latest sentiment and narrative cycle data for context
        sentiment_report = None
        narrative_phases = None
        try:
            sent_col = get_collection(Collections.SENTIMENT_HISTORY)
            latest_sentiment = sent_col.find_one({}, {"_id": 0}, sort=[("captured_at", -1)])
            if latest_sentiment:
                sentiment_report = {k: v for k, v in latest_sentiment.items() if k not in ("raw_data", "_id")}
        except Exception as e:
            print(f"[RankingAgent] Could not load sentiment: {e}")

        try:
            from agents.narrative_cycle import NarrativeCycleAgent
            narrative_phases = NarrativeCycleAgent().get_phase_context()
        except Exception as e:
            print(f"[RankingAgent] Could not load narrative phases: {e}")

        crew = self._build_crew(causal_theses, all_reports_dict, sentiment_report, narrative_phases)

        # Retry up to 2 times on failure
        last_exc = None
        for attempt in range(1, 3):
            try:
                result = crew.kickoff()
                break
            except Exception as e:
                last_exc = e
                print(f"[RankingAgent] Attempt {attempt} failed: {e} — retrying...")
                time.sleep(10)
        else:
            raise RuntimeError(f"Ranking crew failed after 2 attempts: {last_exc}")

        raw_text = str(result)

        # Save raw output for debugging
        with open("/tmp/ranking_raw_output.txt", "w") as f:
            f.write(raw_text)
        print(f"[RankingAgent] Raw output saved to /tmp/ranking_raw_output.txt ({len(raw_text)} chars)")

        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1

        try:
            data = json.loads(raw_text[start:end])
        except json.JSONDecodeError as e:
            print(f"[RankingAgent] JSON parse error: {e} — attempting repair")
            data = _repair_json(raw_text[start:end])

        now = datetime.now(timezone.utc).isoformat()
        horizons = []
        signals_col = get_collection(Collections.SIGNALS)

        # Cache current prices to avoid multiple API calls per ticker
        _price_cache: dict[str, float | None] = {}

        def _get_price(ticker: str) -> float | None:
            if ticker in _price_cache:
                return _price_cache[ticker]
            try:
                import tools.yfinance_client as yfc
                snap = yfc.get_snapshot(ticker)
                day = snap.get("ticker", {}).get("day", {})
                price = day.get("c") or snap.get("ticker", {}).get("prevDay", {}).get("c")
                _price_cache[ticker] = float(price) if price else None
            except Exception:
                _price_cache[ticker] = None
            return _price_cache[ticker]

        for horizon_name, horizon_data in data.get("horizons", {}).items():
            if not isinstance(horizon_data, dict):
                continue

            def parse_signals(raw_list: list, signal_type: SignalType) -> list[Signal]:
                signals = []
                for item in (raw_list or []):
                    try:
                        ticker = item.get("ticker", "")
                        price_at_signal = _get_price(ticker) if ticker else None
                        s = Signal(
                            run_id=run_id,
                            ticker=ticker,
                            signal=signal_type,
                            horizon=horizon_name,
                            confidence=int(item.get("confidence", 50)),
                            technical_score=item.get("technical_score"),
                            sentiment_score=item.get("sentiment_score"),
                            fundamental_score=item.get("fundamental_score"),
                            geo_score=item.get("geo_score"),
                            thesis=item.get("thesis", ""),
                            risks=item.get("risks", []),
                            theme_ids=item.get("theme_ids", []),
                            is_contrarian=item.get("is_contrarian", False),
                            created_at=now,
                            price_at_signal=price_at_signal,
                        )
                        signals_col.update_one(
                            {"ticker": s.ticker, "run_id": run_id, "horizon": horizon_name},
                            {"$set": s.to_mongo()},
                            upsert=True,
                        )
                        signals.append(s)
                    except Exception:
                        continue
                return signals

            hp = HorizonPicks(
                horizon=horizon_name,
                picks=parse_signals(horizon_data.get("picks", []), SignalType.BUY),
                avoid=parse_signals(horizon_data.get("avoid", []), SignalType.AVOID),
                contrarian_picks=parse_signals(horizon_data.get("contrarian_picks", []), SignalType.BUY),
            )
            horizons.append(hp)

        regime_data = data.get("market_regime", {})
        regime = MarketRegime(
            label=regime_data.get("label", "Unknown"),
            description=regime_data.get("description", ""),
            recommended_posture=regime_data.get("recommended_posture", ""),
        ) if regime_data else None

        report = FinalReport(
            run_id=run_id,
            generated_at=now,
            causal_summary=data.get("causal_summary", ""),
            market_regime=regime,
            horizons=horizons,
            stocks_screened=len(screener_results),
            stocks_deep_analysed=len(all_reports_dict.get("market_reports", [])),
            total_signals=sum(len(h.picks) for h in horizons),
            analyst_note=data.get("analyst_note", ""),
        )

        # Persist final report
        get_collection("final_reports").update_one(
            {"run_id": run_id},
            {"$set": report.to_mongo()},
            upsert=True,
        )

        print(f"[RankingAgent] Final report: {report.total_signals} signals across {len(horizons)} horizons")
        return report
