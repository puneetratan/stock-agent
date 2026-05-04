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


def validate_skills():
    """Ensure all skill files are present before the run starts."""
    from tools.skill_loader import validate_all_skills
    validate_all_skills()


def ensure_indexes():
    """Bootstrap MongoDB indexes on first run."""
    try:
        from db.collections import ensure_indexes as _ensure
        _ensure()
        print("[run_agent] MongoDB indexes ensured")
    except Exception as e:
        print(f"[run_agent] Warning: could not ensure MongoDB indexes: {e}")


TICKER_TIMEOUT_SECONDS = 1200  # 20 min per ticker before giving up


def run_analysis_crew_for_ticker(ticker: str, theses: list[dict], run_id: str) -> dict:
    """Run the 4-agent deep analysis crew for a single ticker with a hard timeout."""
    import concurrent.futures
    from agents.crew import build_analysis_crew, parse_crew_outputs
    from db import get_collection
    from db.collections import Collections

    print(f"[run_agent] Deep analysis: {ticker}")

    def _kickoff():
        crew = build_analysis_crew(ticker=ticker, theses=theses, run_id=run_id)
        return crew.kickoff()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_kickoff)
            try:
                result = future.result(timeout=TICKER_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                print(f"[run_agent] TIMEOUT after {TICKER_TIMEOUT_SECONDS//60} min — skipping {ticker}")
                return {"error": f"timeout after {TICKER_TIMEOUT_SECONDS}s"}

        reports = parse_crew_outputs(result, ticker, run_id)

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


STATE_FILE = os.path.join(os.path.dirname(__file__), "current_run.json")


def _write_state(run_id: str, pid: int, log_file: str) -> None:
    import json
    with open(STATE_FILE, "w") as f:
        json.dump({"run_id": run_id, "pid": pid, "log_file": log_file,
                   "started_at": datetime.now(timezone.utc).isoformat()}, f)


def _clear_state() -> None:
    try:
        os.remove(STATE_FILE)
    except FileNotFoundError:
        pass


def main():
    run_id = str(uuid.uuid4())
    start_time = datetime.now(timezone.utc)

    # Accept --log-file=<path> so the scheduler can tell us which file it redirected
    # stdout to — that path is what the watchdog monitors for staleness.
    _cli_log_file = None
    for _arg in sys.argv[1:]:
        if _arg.startswith("--log-file="):
            _cli_log_file = _arg.split("=", 1)[1]
    log_file = _cli_log_file or os.path.join(
        os.path.dirname(__file__),
        f"run_{start_time.strftime('%Y%m%d_%H%M%S')}.log",
    )
    _write_state(run_id, os.getpid(), log_file)

    print(f"\n{'='*60}")
    print(f"Stock Intelligence Agent — Run {run_id[:8]}")
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}\n")

    validate_skills()
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
    # Step 2: Sentiment Analysis — market psychology before causal reasoning
    # -----------------------------------------------------------------------
    print("\n[STEP 2] Sentiment Analysis")
    sentiment_report = None
    try:
        from agents.sentiment import SentimentAgent
        sentiment_agent = SentimentAgent()
        sentiment_report = sentiment_agent.analyse(run_id=run_id, save=True)
        emotion = sentiment_report.get("market_emotion", "unknown")
        score = sentiment_report.get("fear_greed_score", 50)
        print(f"  → Market emotion: {emotion} (fear/greed: {score}/100)")
    except Exception as e:
        print(f"  [WARNING] Sentiment analysis failed: {e} — continuing without it")

    # -----------------------------------------------------------------------
    # Step 2b: Narrative Cycle Analysis — use themes from step 1 directly
    # -----------------------------------------------------------------------
    print("\n[STEP 2b] Narrative Cycle Analysis")
    try:
        from agents.narrative_cycle import NarrativeCycleAgent
        narrative_agent = NarrativeCycleAgent()
        theme_dicts = [{"id": t.id, "name": t.name} for t in themes]
        narrative_results = narrative_agent.analyse(themes=theme_dicts, run_id=run_id)
        for nr in narrative_results:
            phase = nr.get("current_phase", "unknown")
            theme_id = nr.get("theme", "?")
            print(f"  → {theme_id}: {phase}")
    except Exception as e:
        print(f"  [WARNING] Narrative cycle analysis failed: {e} — continuing without it")

    # -----------------------------------------------------------------------
    # Step 3: Causal Reasoning — root cause 3-4 levels deep
    # -----------------------------------------------------------------------
    print("\n[STEP 3] Causal Reasoning Analysis")
    from agents.causal_reasoning import CausalReasoningAgent
    causal_agent = CausalReasoningAgent()

    # Analyse top 5 themes by urgency (avoid burning too many LLM calls)
    top_themes = sorted(themes, key=lambda t: t.urgency, reverse=True)[:5]
    theses = causal_agent.analyse(top_themes, run_id=run_id, sentiment_report=sentiment_report)
    print(f"  → {len(theses)} causal theses produced")

    # -----------------------------------------------------------------------
    # Step 4: Screener — filter stock universe
    # -----------------------------------------------------------------------
    import yaml
    cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    max_deep = cfg["screening"]["max_deep_analyse"]

    print("\n[STEP 4] Stock Screener")
    from agents.screener import ScreenerAgent
    screener = ScreenerAgent()
    candidates = screener.screen(theses, run_id=run_id)
    print(f"  → {len(candidates)} candidates passed screening")
    if candidates:
        top_tickers = [c["ticker"] for c in candidates[:5]]
        print(f"     Top 5: {', '.join(top_tickers)}")

    # Persist run metadata + ordered candidate list so watchdog/resume can use it
    from db import get_collection
    from db.collections import Collections
    get_collection(Collections.RUN_METADATA).update_one(
        {"run_id": run_id},
        {"$set": {
            "run_id": run_id,
            "started_at": start_time.isoformat(),
            "pid": os.getpid(),
            "ordered_tickers": [c["ticker"] for c in candidates[:max_deep]],
            "total_candidates": len(candidates),
            "status": "running",
        }},
        upsert=True,
    )

    # -----------------------------------------------------------------------
    # Step 5: Deep analysis — 4 agents per stock
    # -----------------------------------------------------------------------
    analyse_list = candidates[:max_deep]
    print(f"\n[STEP 5] Deep Analysis ({len(analyse_list)} stocks)")

    start_from = None
    for arg in sys.argv[1:]:
        if arg.startswith("--start-from="):
            start_from = arg.split("=", 1)[1].upper()
    skipping = start_from is not None

    for i, candidate in enumerate(analyse_list, 1):
        ticker = candidate["ticker"]
        if skipping:
            if ticker.upper() == start_from:
                skipping = False
            else:
                print(f"\n  [{i}/{len(analyse_list)}] Skipping {ticker} (already done)")
                continue
        print(f"\n  [{i}/{len(analyse_list)}] Analysing {ticker}...")
        run_analysis_crew_for_ticker(ticker, theses, run_id)

    # -----------------------------------------------------------------------
    # Step 6: Ranking — final picks by horizon
    # -----------------------------------------------------------------------
    print("\n[STEP 6] Ranking & Synthesis")
    from agents.ranking import RankingAgent
    ranking_agent = RankingAgent()
    report = ranking_agent.rank(run_id=run_id)

    print(f"\n  → {report.total_signals} signals generated")
    if report.market_regime:
        print(f"  → Market Regime: {report.market_regime.label}")

    # -----------------------------------------------------------------------
    # Step 7: Deliver report
    # -----------------------------------------------------------------------
    print("\n[STEP 7] Delivering Report")
    from tools.delivery import deliver_report
    deliver_report(report.to_mongo())

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    print(f"\n{'='*60}")
    print(f"Run complete in {elapsed:.0f}s")
    print(f"Run ID: {run_id}")
    print(f"{'='*60}\n")

    _clear_state()
    from db import get_collection
    from db.collections import Collections
    get_collection(Collections.RUN_METADATA).update_one(
        {"run_id": run_id},
        {"$set": {"status": "complete", "finished_at": datetime.now(timezone.utc).isoformat(),
                  "total_signals": report.total_signals}},
    )
    return report


if __name__ == "__main__":
    main()
