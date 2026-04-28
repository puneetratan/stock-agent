"""
Entry point: python run_agent.py

Runs the full stock intelligence pipeline once:
  1. World Intelligence Agent — scan world events
  2. Causal Reasoning Agent  — WHY 3-4 levels deep
  3. Screener Agent          — filter stock universe
  4. 4-agent deep analysis crew for top N candidates
  5. Ranking Agent           — final picks by horizon
  6. Deliver report
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# Validate required env vars before importing anything that uses them
REQUIRED_VARS = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "MONGO_URI", "POLYGON_API_KEY", "NEWS_API_KEY"]
missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
if missing:
    print(f"[run_agent] Missing required environment variables: {', '.join(missing)}")
    print("[run_agent] Copy .env.example to .env and fill in your keys.")
    sys.exit(1)


def ensure_indexes():
    """Bootstrap MongoDB indexes on first run."""
    try:
        from db.collections import ensure_indexes as _ensure
        _ensure()
        print("[run_agent] MongoDB indexes ensured")
    except Exception as e:
        print(f"[run_agent] Warning: could not ensure MongoDB indexes: {e}")


def run_analysis_crew_for_ticker(ticker: str, theses: list[dict], run_id: str) -> dict:
    """Run the 4-agent deep analysis crew for a single ticker."""
    from agents.crew import build_analysis_crew, parse_crew_outputs
    from db import get_collection
    from db.collections import Collections

    print(f"[run_agent] Deep analysis: {ticker}")
    try:
        crew = build_analysis_crew(ticker=ticker, theses=theses, run_id=run_id)
        result = crew.kickoff()
        reports = parse_crew_outputs(result, ticker, run_id)

        # Persist each sub-report to the appropriate collection
        col_map = {
            "market":       Collections.MARKET_DATA,
            "news":         Collections.NEWS_SENTIMENT,
            "fundamentals": Collections.FUNDAMENTALS,
            "geo":          Collections.GEO_MACRO,
        }
        for key, collection in col_map.items():
            if key in reports:
                get_collection(collection).update_one(
                    {"ticker": ticker, "run_id": run_id},
                    {"$set": reports[key]},
                    upsert=True,
                )
        return reports
    except Exception as e:
        print(f"[run_agent] Error analysing {ticker}: {e}")
        return {"error": str(e)}


def main():
    run_id = str(uuid.uuid4())
    start_time = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"Stock Intelligence Agent — Run {run_id[:8]}")
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}\n")

    ensure_indexes()

    # -----------------------------------------------------------------------
    # Step 1: World Intelligence — scan events
    # -----------------------------------------------------------------------
    print("\n[STEP 1] World Intelligence Scan")
    from agents.world_intelligence import WorldIntelligenceAgent
    world_agent = WorldIntelligenceAgent()
    themes = world_agent.scan(run_id=run_id)
    print(f"  → {len(themes)} themes detected")
    for t in themes:
        print(f"     [{t.urgency}/10] {t.name} ({t.status.value})")

    if not themes:
        print("[run_agent] No themes detected — cannot proceed. Check news API keys.")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Step 2: Causal Reasoning — root cause 3-4 levels deep
    # -----------------------------------------------------------------------
    print("\n[STEP 2] Causal Reasoning Analysis")
    from agents.causal_reasoning import CausalReasoningAgent
    causal_agent = CausalReasoningAgent()

    # Analyse top 5 themes by urgency (avoid burning too many LLM calls)
    top_themes = sorted(themes, key=lambda t: t.urgency, reverse=True)[:5]
    theses = causal_agent.analyse(top_themes, run_id=run_id)
    print(f"  → {len(theses)} causal theses produced")

    # -----------------------------------------------------------------------
    # Step 3: Screener — filter stock universe
    # -----------------------------------------------------------------------
    print("\n[STEP 3] Stock Screener")
    from agents.screener import ScreenerAgent
    screener = ScreenerAgent()
    candidates = screener.screen(theses, run_id=run_id)
    print(f"  → {len(candidates)} candidates passed screening")
    if candidates:
        top_tickers = [c["ticker"] for c in candidates[:5]]
        print(f"     Top 5: {', '.join(top_tickers)}")

    # -----------------------------------------------------------------------
    # Step 4: Deep analysis — 4 agents per stock
    # -----------------------------------------------------------------------
    import yaml
    cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    max_deep = cfg["screening"]["max_deep_analyse"]

    analyse_list = candidates[:max_deep]
    print(f"\n[STEP 4] Deep Analysis ({len(analyse_list)} stocks)")

    for i, candidate in enumerate(analyse_list, 1):
        ticker = candidate["ticker"]
        print(f"\n  [{i}/{len(analyse_list)}] Analysing {ticker}...")
        run_analysis_crew_for_ticker(ticker, theses, run_id)

    # -----------------------------------------------------------------------
    # Step 5: Ranking — final picks by horizon
    # -----------------------------------------------------------------------
    print("\n[STEP 5] Ranking & Synthesis")
    from agents.ranking import RankingAgent
    ranking_agent = RankingAgent()
    report = ranking_agent.rank(run_id=run_id)

    print(f"\n  → {report.total_signals} signals generated")
    if report.market_regime:
        print(f"  → Market Regime: {report.market_regime.label}")

    # -----------------------------------------------------------------------
    # Step 6: Deliver report
    # -----------------------------------------------------------------------
    print("\n[STEP 6] Delivering Report")
    from tools.delivery import deliver_report
    deliver_report(report.to_mongo())

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    print(f"\n{'='*60}")
    print(f"Run complete in {elapsed:.0f}s")
    print(f"Run ID: {run_id}")
    print(f"{'='*60}\n")

    return report


if __name__ == "__main__":
    main()
