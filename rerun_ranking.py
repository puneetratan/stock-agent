"""
Re-runs Agent 8 (Ranking) against an existing run_id already in MongoDB.
Use this to recover from a ranking parse failure without re-running the full pipeline.

Usage:
    uv run python rerun_ranking.py <run_id>
    uv run python rerun_ranking.py          # uses the most recent run
"""

import sys
from dotenv import load_dotenv
load_dotenv()

from db import get_collection
from db.collections import Collections
from tools.delivery import deliver_report


def get_latest_run_id() -> str | None:
    col = get_collection(Collections.SCREENER_RESULTS)
    doc = col.find_one({}, {"run_id": 1}, sort=[("screened_at", -1)])
    return doc["run_id"] if doc else None


def main():
    if len(sys.argv) > 1:
        run_id = sys.argv[1]
    else:
        run_id = get_latest_run_id()
        if not run_id:
            print("No runs found in MongoDB. Run the full pipeline first.")
            sys.exit(1)
        print(f"Using most recent run_id: {run_id}")

    # Show what data exists for this run
    counts = {
        "market":       get_collection(Collections.MARKET_DATA).count_documents({"run_id": run_id}),
        "news":         get_collection(Collections.NEWS_SENTIMENT).count_documents({"run_id": run_id}),
        "fundamentals": get_collection(Collections.FUNDAMENTALS).count_documents({"run_id": run_id}),
        "geo":          get_collection(Collections.GEO_MACRO).count_documents({"run_id": run_id}),
        "causal":       get_collection(Collections.CAUSAL_THESES).count_documents({"run_id": run_id}),
    }
    print(f"\nData in MongoDB for run {run_id[:8]}:")
    for k, v in counts.items():
        print(f"  {k:<15} {v} documents")

    if all(v == 0 for v in counts.values()):
        print("\nNo data found for this run_id. Check the ID and try again.")
        sys.exit(1)

    print(f"\nRunning Agent 8 — Ranking...")
    from agents.ranking import RankingAgent
    agent = RankingAgent()
    report = agent.rank(run_id=run_id)

    print(f"\n{'='*60}")
    print(f"Final Report — Run {run_id[:8]}")
    print(f"  Market regime:   {report.market_regime.label if report.market_regime else 'N/A'}")
    print(f"  Total signals:   {report.total_signals}")
    print(f"  Stocks analysed: {report.stocks_deep_analysed}")
    print()

    for horizon in report.horizons:
        if not horizon.picks and not horizon.contrarian_picks:
            continue
        print(f"  [{horizon.horizon.upper()}]")
        for pick in horizon.picks:
            print(f"    BUY       {pick.ticker:<6} {pick.confidence}% — {pick.thesis[:70]}")
        for pick in horizon.contrarian_picks:
            print(f"    CONTRARIAN {pick.ticker:<6} — {pick.thesis[:70]}")
        for pick in horizon.avoid:
            print(f"    AVOID     {pick.ticker:<6} — {pick.thesis[:70]}")

    print(f"\n  Analyst note: {report.analyst_note[:200]}")
    print(f"\nDelivering report...")
    deliver_report(report.to_mongo())


if __name__ == "__main__":
    main()
