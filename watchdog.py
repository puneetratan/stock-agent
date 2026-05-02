"""
Watchdog — standalone pipeline guardian.

Run as its own always-alive launchd service (com.stockintelligence.watchdog).
It does NOT need to be started by run_schedule.py.

Every CHECK_INTERVAL seconds it reads current_run.json and acts on two failure modes:

  CRASH  — process exited before run_metadata.status == "complete"
           → resume from first incomplete ticker, or finalize if all tickers done
  STALL  — process still alive but log file hasn't grown in STALL_THRESHOLD seconds
           → kill the stuck process and resume the same way

Recovery is retried up to MAX_RETRIES times per run_id. After that the watchdog
stops touching the run and leaves it for manual inspection.
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

CHECK_INTERVAL  = 120    # poll every 2 minutes
STALL_THRESHOLD = 600    # 10 min of no log growth = stalled
MAX_RETRIES     = 3      # max recovery attempts per run before giving up
CRASH_WAIT      = 30     # seconds to wait after crash before relaunching

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
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


def _clear_state() -> None:
    try:
        os.remove(STATE_FILE)
    except FileNotFoundError:
        pass


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
        log.info(f"Killed PID {pid}")
    except Exception as e:
        log.warning(f"Could not kill PID {pid}: {e}")


# ---------------------------------------------------------------------------
# Log staleness check
# ---------------------------------------------------------------------------

def _log_stalled(log_file: str, started_at: str | None = None) -> bool:
    if log_file and os.path.exists(log_file):
        return (time.time() - os.path.getmtime(log_file)) > STALL_THRESHOLD
    # Log file missing or invalid (e.g. "<stdout>" from a manual run) —
    # fall back to elapsed time since started_at.
    if started_at:
        try:
            start = datetime.fromisoformat(started_at)
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            return elapsed > STALL_THRESHOLD
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# MongoDB helpers
# ---------------------------------------------------------------------------

def _get_run_status(run_id: str) -> str | None:
    """Return run_metadata.status for this run, or None if not found."""
    try:
        from db import get_collection
        from db.collections import Collections
        doc = get_collection(Collections.RUN_METADATA).find_one(
            {"run_id": run_id}, {"status": 1, "_id": 0}
        )
        return doc.get("status") if doc else None
    except Exception as e:
        log.error(f"Could not get run status: {e}")
        return None


def _get_ordered_tickers(run_id: str) -> list[str]:
    """Return the ordered deep-analysis ticker list saved during Step 4."""
    try:
        from db import get_collection
        from db.collections import Collections
        doc = get_collection(Collections.RUN_METADATA).find_one({"run_id": run_id})
        if doc:
            return doc.get("ordered_tickers", [])
        log.warning("run_metadata not found — falling back to screener_results")
        import yaml
        with open(os.path.join(BASE_DIR, "config.yaml")) as f:
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
    ordered   = _get_ordered_tickers(run_id)
    completed = _get_completed_tickers(run_id)
    log.info(f"Ordered: {ordered}")
    log.info(f"Completed ({len(completed)}): {sorted(completed)}")
    for ticker in ordered:
        if ticker not in completed:
            log.info(f"First incomplete ticker: {ticker}")
            return ticker
    log.info("All tickers complete")
    return None


# ---------------------------------------------------------------------------
# Recovery actions
# ---------------------------------------------------------------------------

def _resume(run_id: str, start_from: str, retries: int) -> int:
    """Spawn resume_from_ticker.py — picks up mid-pipeline from start_from."""
    script    = os.path.join(BASE_DIR, "resume_from_ticker.py")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file  = os.path.join(BASE_DIR, f"run_{timestamp}_watchdog_resume.log")

    with open(log_file, "w") as out:
        proc = subprocess.Popen(
            [VENV_PYTHON, script, f"--run-id={run_id}", f"--start-from={start_from}"],
            stdout=out, stderr=out,
            start_new_session=True,
        )

    log.info(f"Resume spawned — run {run_id[:8]}, from {start_from}, PID {proc.pid}, log: {log_file}")
    _write_state({
        "run_id": run_id, "pid": proc.pid, "log_file": log_file,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "resumed_from": start_from, "retries": retries,
    })
    return proc.pid


def _finalize(run_id: str, retries: int) -> int:
    """Spawn finalize_run.py — runs only Steps 6+7 (ranking + delivery)."""
    script    = os.path.join(BASE_DIR, "finalize_run.py")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file  = os.path.join(BASE_DIR, f"run_{timestamp}_watchdog_finalize.log")

    with open(log_file, "w") as out:
        proc = subprocess.Popen(
            [VENV_PYTHON, script, run_id],
            stdout=out, stderr=out,
            start_new_session=True,
        )

    log.info(f"Finalize spawned — run {run_id[:8]}, PID {proc.pid}, log: {log_file}")
    _write_state({
        "run_id": run_id, "pid": proc.pid, "log_file": log_file,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stage": "finalize", "retries": retries,
    })
    return proc.pid


def _recover(state: dict) -> None:
    """Decide and execute the right recovery action for a dead/stalled run."""
    run_id  = state["run_id"]
    retries = state.get("retries", 0)

    if retries >= MAX_RETRIES:
        log.error(
            f"Run {run_id[:8]} has exceeded max retries ({MAX_RETRIES}). "
            "Leaving state file in place — manual intervention required."
        )
        return

    time.sleep(CRASH_WAIT)  # let any in-flight MongoDB writes settle

    resume_from = _find_resume_ticker(run_id)
    if resume_from:
        log.warning(f"Resuming run {run_id[:8]} from ticker {resume_from} (retry {retries + 1}/{MAX_RETRIES})")
        _resume(run_id, resume_from, retries + 1)
    else:
        log.warning(f"All tickers done — finalizing run {run_id[:8]} (retry {retries + 1}/{MAX_RETRIES})")
        _finalize(run_id, retries + 1)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    log.info(
        f"Watchdog started — stall threshold: {STALL_THRESHOLD // 60} min, "
        f"poll: {CHECK_INTERVAL // 60} min, max retries: {MAX_RETRIES}"
    )

    while True:
        time.sleep(CHECK_INTERVAL)

        state = _read_state()
        if not state:
            continue  # no active run

        run_id   = state["run_id"]
        pid      = state["pid"]
        log_file = state.get("log_file", "")

        # ── Crash detection ──────────────────────────────────────────────────
        if not _process_alive(pid):
            run_status = _get_run_status(run_id)
            if run_status == "complete":
                log.info(f"Run {run_id[:8]} completed cleanly — clearing state")
                _clear_state()
                continue

            log.warning(
                f"CRASH DETECTED — run {run_id[:8]}, PID {pid} is gone, "
                f"status in DB: {run_status!r}"
            )
            _recover(state)
            continue

        # ── Stall detection ──────────────────────────────────────────────────
        started_at = state.get("started_at")
        if not _log_stalled(log_file, started_at):
            if log_file and os.path.exists(log_file):
                age = time.time() - os.path.getmtime(log_file)
                log.info(f"Run {run_id[:8]} healthy — log updated {age:.0f}s ago (PID {pid})")
            else:
                elapsed = (time.time() - datetime.fromisoformat(started_at).timestamp()
                           if started_at else 0)
                log.info(f"Run {run_id[:8]} healthy — no log file, elapsed {elapsed:.0f}s (PID {pid})")
            continue

        log.warning(
            f"STALL DETECTED — run {run_id[:8]}, PID {pid}, "
            f"log unchanged >{STALL_THRESHOLD // 60} min"
        )
        _kill(pid)
        _recover(state)


if __name__ == "__main__":
    main()
