"""
Resume a run from a specific ticker — skips Steps 1-4.

Usage:
    python resume_from_ticker.py --run-id <RUN_ID> --start-from <TICKER>

Example:
    python resume_from_ticker.py --run-id bbd6b07d-8599-4605-8697-c8443bf4db21 --start-from RELIANCE.NS
"""

import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

import argparse

STATE_FILE = os.path.join(os.path.dirname(__file__), "current_run.json")

parser = argparse.ArgumentParser()
parser.add_argument("--run-id", required=True, help="Original run_id to resume")
parser.add_argument("--start-from", required=True, help="Ticker to resume from (inclusive)")
args = parser.parse_args()

run_id = args.run_id
start_from = args.start_from.upper()

# Register this process in the state file so the watchdog can track it
with open(STATE_FILE, "w") as _f:
    json.dump({"run_id": run_id, "pid": os.getpid(),
               "log_file": os.path.abspath(sys.stdout.name) if hasattr(sys.stdout, "name") else "",
               "started_at": datetime.now(timezone.utc).isoformat(),
               "resumed_from": start_from}, _f)

print(f"\n{'='*60}")
print(f"Resuming run {run_id[:8]}... from {start_from}")
print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"{'='*60}\n")

# Load theses from MongoDB (saved during original run)
from db import get_collection
from db.collections import Collections

print("[RESUME] Loading causal theses from MongoDB...")
theses_docs = list(get_collection(Collections.CAUSAL_THESES).find({"run_id": run_id}))
if not theses_docs:
    print(f"[RESUME] ERROR: No theses found for run_id={run_id}. Cannot resume.")
    sys.exit(1)

# Reconstruct theses list in the format agents expect
theses = []
for doc in theses_docs:
    doc.pop("_id", None)
    theses.append(doc)
print(f"[RESUME] Loaded {len(theses)} causal theses")

# Re-run screener to get the same candidate list (fast — no LLM calls)
print("\n[RESUME] Re-running screener to get candidate list...")
from agents.screener import ScreenerAgent
screener = ScreenerAgent()
candidates = screener.screen(theses, run_id=run_id)
print(f"  → {len(candidates)} candidates")

import yaml
cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(cfg_path) as f:
    cfg = yaml.safe_load(f)
max_deep = cfg["screening"]["max_deep_analyse"]
analyse_list = candidates[:max_deep]

print(f"\n[STEP 5] Deep Analysis — resuming from {start_from} ({len(analyse_list)} total)")

from run_agent import run_analysis_crew_for_ticker

skipping = True
for i, candidate in enumerate(analyse_list, 1):
    ticker = candidate["ticker"]
    if skipping:
        if ticker.upper() == start_from:
            skipping = False
        else:
            print(f"  [{i}/{len(analyse_list)}] Skipping {ticker} (already done)")
            continue
    print(f"\n  [{i}/{len(analyse_list)}] Analysing {ticker}...")
    run_analysis_crew_for_ticker(ticker, theses, run_id)

# Step 6: Ranking
print("\n[STEP 6] Ranking & Synthesis")
from agents.ranking import RankingAgent
report = RankingAgent().rank(run_id=run_id)
print(f"  → {report.total_signals} signals generated")
if report.market_regime:
    print(f"  → Market Regime: {report.market_regime.label}")

# Step 7: Deliver
print("\n[STEP 7] Delivering Report")
from tools.delivery import deliver_report
deliver_report(report.to_mongo())

print(f"\n{'='*60}")
print(f"Resume complete — Run ID: {run_id}")
print(f"{'='*60}\n")

# Clean up state file so watchdog knows the run finished cleanly
try:
    os.remove(STATE_FILE)
except FileNotFoundError:
    pass
