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


def _start_watchdog() -> None:
    """Start the watchdog as a background subprocess."""
    import subprocess
    script = os.path.join(os.path.dirname(__file__), "watchdog.py")
    venv_python = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python")
    watchdog_log = os.path.join(os.path.dirname(__file__), "watchdog.log")
    with open(watchdog_log, "a") as out:
        proc = subprocess.Popen(
            [venv_python, script],
            stdout=out, stderr=out,
            start_new_session=True,
        )
    log.info(f"Watchdog started — PID {proc.pid}")


def run_job():
    """Called by the scheduler at the configured time."""
    cfg = _load_config()
    if cfg["schedule"].get("weekdays_only", True) and not _is_weekday():
        log.info("Skipping — today is a weekend")
        return

    _start_watchdog()
    log.info("Starting scheduled intelligence run")
    try:
        from run_agent import main
        report = main()
        log.info(f"Run complete — {report.total_signals} signals, run_id={report.run_id}")
    except Exception as e:
        log.error(f"Run failed: {e}", exc_info=True)


def run_verification_job():
    """Nightly signal verification — runs at 23:00."""
    log.info("Starting nightly signal verification")
    try:
        from signal_verification_job import verify_signals
        scorecard = verify_signals()
        log.info(f"Verification complete — {scorecard.get('total_verified_this_run', 0)} signals verified")
    except Exception as e:
        log.error(f"Signal verification failed: {e}", exc_info=True)


def run_weekly_sentiment():
    """Weekly sentiment snapshot — runs every Sunday at 08:00."""
    log.info("Starting weekly sentiment snapshot")
    try:
        from agents.sentiment import SentimentAgent
        report = SentimentAgent().analyse(save=True)
        log.info(f"Sentiment snapshot saved — emotion={report.get('market_emotion')}, score={report.get('fear_greed_score')}")
    except Exception as e:
        log.error(f"Weekly sentiment failed: {e}", exc_info=True)


def run_monthly_crossover():
    """Monthly crossover tracking — first of each month at 09:00."""
    log.info("Monthly crossover check starting")
    try:
        from tools.crossover_tracker import get_crossover_status
        status = get_crossover_status()
        log.info(f"Crossover status: {status}")

        print("\n" + "=" * 50)
        print("💰 MONTHLY CROSSOVER CHECK")
        print("=" * 50)
        if status.get("crossover_confirmed"):
            print("🎉 CROSSOVER CONFIRMED — 3+ consecutive months!")
        else:
            gap = status.get("gap_to_crossover", "unknown")
            proj = status.get("projected_crossover", "unknown")
            print(f"Gap remaining:    {gap}")
            print(f"Projected date:   {proj}")
        print("=" * 50 + "\n")
        print("Enter job income for this month (or press Enter to skip):")
        try:
            job_income = input("> ").strip()
            if job_income:
                from tools.crossover_tracker import record_monthly
                result = record_monthly(job_income=float(job_income), product_revenue=0.0)
                log.info(f"Monthly crossover recorded: {result}")
        except (EOFError, ValueError):
            log.info("Skipping monthly income input (non-interactive mode)")
    except Exception as e:
        log.error(f"Monthly crossover failed: {e}", exc_info=True)


def _local_to_utc(run_at: str, tz_name: str) -> str:
    tz = pytz.timezone(tz_name)
    now_utc = datetime.now(pytz.utc)
    now_local = now_utc.astimezone(tz)
    hour, minute = map(int, run_at.split(":"))
    target_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target_local.astimezone(pytz.utc).strftime("%H:%M")


def main():
    cfg = _load_config()
    run_at = cfg["schedule"].get("run_at", "06:30")
    tz_name = cfg["schedule"].get("timezone", "US/Eastern")

    log.info(f"Scheduler starting — will run daily at {run_at} {tz_name}")
    log.info("Keep this process alive (tmux / screen / systemd)")

    # Morning agent run (weekdays at 06:30 ET)
    utc_morning = _local_to_utc(run_at, tz_name)
    log.info(f"Morning run scheduled at UTC {utc_morning} (= {run_at} {tz_name})")
    schedule.every().day.at(utc_morning).do(run_job)

    # Nightly verification at 23:00 UTC every day
    schedule.every().day.at("23:00").do(run_verification_job)
    log.info("Nightly verification scheduled at 23:00 UTC")

    # Weekly sentiment snapshot — Sunday 08:00 UTC
    schedule.every().sunday.at("08:00").do(run_weekly_sentiment)
    log.info("Weekly sentiment snapshot scheduled every Sunday 08:00 UTC")

    # Monthly crossover — first of each month at 09:00 UTC
    # schedule library doesn't support "first of month" natively,
    # so we run daily at 09:00 and guard with a day-of-month check.
    schedule.every().day.at("09:00").do(
        lambda: run_monthly_crossover() if datetime.now().day == 1 else None
    )
    log.info("Monthly crossover check scheduled for 1st of each month at 09:00 UTC")

    if "--now" in sys.argv:
        log.info("--now flag detected — running immediately")
        run_job()

    if "--verify-now" in sys.argv:
        log.info("--verify-now flag detected — running verification immediately")
        run_verification_job()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
