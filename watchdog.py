"""
Watchdog: monitors the running pipeline and auto-resumes if stalled.

Started automatically by run_schedule.py alongside every morning run.

Every CHECK_INTERVAL seconds:
  1. Reads current_run.json to get run_id, pid, log_file
  2. Checks if log file has grown recently
  3. If no growth for STALL_THRESHOLD seconds and process is alive:
     a. Queries run_metadata collection for the ordered ticker list
     b. Queries fundamentals collection to find which tickers are done
     c. Kills the stuck process
     d. Launches resume_from_ticker.py with same run_id + next incomplete ticker
     e. Updates current_run.json with new PID

Design principles:
  - Watchdog never re-runs Steps 1-4 (uses MongoDB data from original run)
  - A ticker is "done" if it has a fundamentals document for this run_id
  - Watchdog itself is stateless — safe to restart at any time
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

CHECK_INTERVAL  = 120   # poll every 2 minutes
STALL_THRESHOLD = 900   # 15 min of no log growth = stalled

BASE_DIR    = os.path.dirname(__file__)
STATE_FILE  = os.path.join(BASE_DIR, "current_run.json")
VENV_PYTHON = os.path.join(BASE_DIR, ".venv", "bin", "python")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watchdog] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _read_state() -> dict | None:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_state(data: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------

def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(3)
        if _process_alive(pid):
            os.kill(pid, signal.SIGKILL)
        log.info(f"Killed stuck process PID {pid}")
    except Exception as e:
        log.warning(f"Could not kill PID {pid}: {e}")


# ---------------------------------------------------------------------------
# Log staleness check
# ---------------------------------------------------------------------------

def _log_stalled(log_file: str) -> bool:
    if not log_file or not os.path.exists(log_file):
        return False
    age = time.time() - os.path.getmtime(log_file)
    return age > STALL_THRESHOLD


# ---------------------------------------------------------------------------
# MongoDB helpers — no screener re-run needed
# ---------------------------------------------------------------------------

def _get_ordered_tickers(run_id: str) -> list[str]:
    """Return the ordered deep-analysis ticker list saved during Step 4."""
    try:
        from db import get_collection
        from db.collections import Collections
        doc = get_collection(Collections.RUN_METADATA).find_one({"run_id": run_id})
        if doc:
            return doc.get("ordered_tickers", [])
        log.warning("run_metadata not found — falling back to screener_results")
        # Fallback: screener_results doesn't preserve order, so sort by score descending
        import yaml
        cfg_path = os.path.join(BASE_DIR, "config.yaml")
        with open(cfg_path) as f:
            max_deep = yaml.safe_load(f)["screening"]["max_deep_analyse"]
        docs = list(
            get_collection(Collections.SCREENER_RESULTS)
            .find({"run_id": run_id}, {"ticker": 1, "score": 1, "_id": 0})
            .sort("score", -1)
            .limit(max_deep)
        )
        return [d["ticker"] for d in docs]
    except Exception as e:
        log.error(f"Could not get ordered tickers: {e}")
        return []


def _get_completed_tickers(run_id: str) -> set[str]:
    """Tickers that have a completed fundamentals document for this run."""
    try:
        from db import get_collection
        from db.collections import Collections
        docs = get_collection(Collections.FUNDAMENTALS).find(
            {"run_id": run_id}, {"ticker": 1, "_id": 0}
        )
        return {d["ticker"] for d in docs}
    except Exception as e:
        log.error(f"MongoDB query failed: {e}")
        return set()


def _find_resume_ticker(run_id: str) -> str | None:
    """First ticker in the ordered list that hasn't been completed yet."""
    ordered  = _get_ordered_tickers(run_id)
    completed = _get_completed_tickers(run_id)
    log.info(f"Ordered tickers: {ordered}")
    log.info(f"Completed in MongoDB ({len(completed)}): {sorted(completed)}")
    for ticker in ordered:
        if ticker not in completed:
            log.info(f"First incomplete ticker: {ticker}")
            return ticker
    log.info("All tickers complete — nothing to resume")
    return None


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

def _resume(run_id: str, start_from: str) -> int:
    script    = os.path.join(BASE_DIR, "resume_from_ticker.py")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file  = os.path.join(BASE_DIR, f"run_{timestamp}_watchdog_resume.log")

    with open(log_file, "w") as out:
        proc = subprocess.Popen(
            [VENV_PYTHON, script, f"--run-id={run_id}", f"--start-from={start_from}"],
            stdout=out, stderr=out,
            start_new_session=True,
        )

    log.info(f"Resumed run {run_id[:8]} from {start_from} — PID {proc.pid}, log: {log_file}")
    _write_state({"run_id": run_id, "pid": proc.pid, "log_file": log_file,
                  "started_at": datetime.now(timezone.utc).isoformat(),
                  "resumed_from": start_from})
    return proc.pid


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    log.info(f"Watchdog started — stall threshold: {STALL_THRESHOLD // 60} min, "
             f"poll interval: {CHECK_INTERVAL // 60} min")

    while True:
        time.sleep(CHECK_INTERVAL)

        state = _read_state()
        if not state:
            continue  # No active run

        run_id   = state["run_id"]
        pid      = state["pid"]
        log_file = state.get("log_file", "")

        if not _process_alive(pid):
            log.info(f"PID {pid} is not running — watchdog idle")
            continue

        if not _log_stalled(log_file):
            age = (time.time() - os.path.getmtime(log_file)
                   if log_file and os.path.exists(log_file) else 0)
            log.info(f"Run {run_id[:8]} healthy — log updated {age:.0f}s ago (PID {pid})")
            continue

        log.warning(
            f"STALL DETECTED — run {run_id[:8]}, PID {pid}, "
            f"log unchanged >{STALL_THRESHOLD // 60} min"
        )

        resume_from = _find_resume_ticker(run_id)
        if not resume_from:
            log.info("No incomplete ticker — killing without resume (run may already be done)")
            _kill(pid)
            continue

        log.warning(f"Killing PID {pid} and resuming from {resume_from}...")
        _kill(pid)
        _resume(run_id, resume_from)


if __name__ == "__main__":
    main()
