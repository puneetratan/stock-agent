"""Run Steps 6 + 7 (Ranking + Delivery) for a completed deep analysis run."""
import os, sys
from dotenv import load_dotenv
load_dotenv()

run_id = sys.argv[1] if len(sys.argv) > 1 else None
if not run_id:
    print("Usage: python finalize_run.py <run_id>")
    sys.exit(1)

print(f"\nFinalizing run {run_id[:8]}...")

print("\n[STEP 6] Ranking & Synthesis")
from agents.ranking import RankingAgent
report = RankingAgent().rank(run_id=run_id)
print(f"  → {report.total_signals} signals generated")
if report.market_regime:
    print(f"  → Market Regime: {report.market_regime.label}")

print("\n[STEP 7] Delivering Report")
from tools.delivery import deliver_report
deliver_report(report.to_mongo())

print(f"\nDone — Run ID: {run_id}\n")
