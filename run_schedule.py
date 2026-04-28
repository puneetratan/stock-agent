"""
Scheduled runner: python run_schedule.py

Runs the full intelligence pipeline every weekday at 06:30 US/Eastern
(before market open at 09:30 ET).

Keep this process alive in a tmux session or systemd service.
"""

import logging
import os
import sys
import time
from datetime import datetime

import pytz
import schedule
import yaml
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def _load_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def _is_weekday() -> bool:
    tz = pytz.timezone("US/Eastern")
    now_et = datetime.now(tz)
    return now_et.weekday() < 5   # 0=Monday … 4=Friday


def run_job():
    """Called by the scheduler at the configured time."""
    cfg = _load_config()
    if cfg["schedule"].get("weekdays_only", True) and not _is_weekday():
        log.info("Skipping — today is a weekend")
        return

    log.info("Starting scheduled intelligence run")
    try:
        # Import here so module-level errors don't crash the scheduler
        from run_agent import main
        report = main()
        log.info(f"Run complete — {report.total_signals} signals, run_id={report.run_id}")
    except Exception as e:
        log.error(f"Run failed: {e}", exc_info=True)


def main():
    cfg = _load_config()
    run_at = cfg["schedule"].get("run_at", "06:30")
    tz_name = cfg["schedule"].get("timezone", "US/Eastern")

    log.info(f"Scheduler starting — will run daily at {run_at} {tz_name}")
    log.info("Keep this process alive (tmux / screen / systemd)")

    # schedule library uses local time; we convert run_at to UTC
    tz = pytz.timezone(tz_name)
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    now_local = now_utc.astimezone(tz)

    hour, minute = map(int, run_at.split(":"))
    # Calculate UTC equivalent of the local run time
    target_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    target_utc = target_local.astimezone(pytz.utc)
    utc_time_str = target_utc.strftime("%H:%M")

    log.info(f"Scheduling at UTC {utc_time_str} (= {run_at} {tz_name})")
    schedule.every().day.at(utc_time_str).do(run_job)

    # Optionally run immediately on start (useful for testing)
    if "--now" in sys.argv:
        log.info("--now flag detected — running immediately")
        run_job()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
