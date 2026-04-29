"""
Signal Verification Job — runs nightly at 23:00.

Checks signals that are 30, 90, or 180 days old.
Fetches actual price from Polygon.io and records whether the signal was correct.
Calculates a running accuracy scorecard.

This is the foundation of the 70% accuracy target.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

# Add project root to path when running directly
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [verification] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

RATE_LIMIT_SECONDS = 0.5  # yfinance is free but be polite
HOLD_THRESHOLD_PCT = 5.0  # HOLD correct if price moved less than this %

HORIZONS = [
    {"days": 30, "key": "30d"},
    {"days": 90, "key": "90d"},
    {"days": 180, "key": "180d"},
]


def _fetch_close_price(ticker: str, date: datetime) -> float | None:
    """Fetch closing price on or near the given date via yfinance."""
    from tools.yfinance_client import get_close_on_date
    date_str = date.strftime("%Y-%m-%d")
    try:
        return get_close_on_date(ticker, date_str)
    except Exception as e:
        log.warning(f"yfinance price fetch failed for {ticker} on {date_str}: {e}")
        return None


def _signal_correct(signal_type: str, return_pct: float) -> bool:
    signal_upper = signal_type.upper()
    if signal_upper == "BUY":
        return return_pct > 0
    if signal_upper in ("SELL", "AVOID"):
        return return_pct < 0
    if signal_upper == "HOLD":
        return abs(return_pct) < HOLD_THRESHOLD_PCT
    return False


def verify_signals() -> dict:
    """
    Main verification loop.
    Returns the accuracy scorecard dict.
    """
    from db import get_collection
    from db.collections import Collections

    signals_col = get_collection(Collections.SIGNALS)
    scorecard_col = get_collection(Collections.ACCURACY_SCORECARD)

    now = datetime.now(timezone.utc)
    total_verified = 0
    total_skipped = 0
    horizon_stats: dict[str, dict] = {}

    for h in HORIZONS:
        days = h["days"]
        key = h["key"]
        horizon_stats[key] = {
            "total": 0,
            "correct": 0,
            "high_conf_total": 0,
            "high_conf_correct": 0,
            "medium_conf_total": 0,
            "medium_conf_correct": 0,
            "low_conf_total": 0,
            "low_conf_correct": 0,
            "buy_total": 0,
            "buy_correct": 0,
            "sell_total": 0,
            "sell_correct": 0,
            "hold_total": 0,
            "hold_correct": 0,
            "correct_returns": [],
        }

        verified_field = f"verified_{key}"
        cutoff = now - timedelta(days=days)

        # Find unverified signals old enough to check
        query = {
            verified_field: {"$ne": True},
            "price_at_signal": {"$exists": True, "$ne": None},
            "created_at": {"$lte": cutoff.isoformat()},
        }

        signals = list(signals_col.find(query, {"_id": 0}))
        log.info(f"[{key}] Found {len(signals)} signals to verify")

        for sig in signals:
            ticker = sig.get("ticker", "")
            created_raw = sig.get("created_at", "")
            signal_type = sig.get("signal", "BUY")
            confidence = sig.get("confidence", 50)
            price_at = sig.get("price_at_signal")

            if not ticker or not created_raw or not price_at:
                total_skipped += 1
                continue

            try:
                created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            except ValueError:
                total_skipped += 1
                continue

            target_date = created_dt + timedelta(days=days)
            if target_date > now:
                total_skipped += 1
                continue

            time.sleep(RATE_LIMIT_SECONDS)
            price_later = _fetch_close_price(ticker, target_date)

            if price_later is None:
                log.warning(f"No price for {ticker} on {target_date.date()}, skipping")
                total_skipped += 1
                continue

            return_pct = ((price_later - price_at) / price_at) * 100
            correct = _signal_correct(signal_type, return_pct)

            emoji = "✅" if correct else "❌"
            log.info(f"{emoji} {ticker} [{signal_type}] {key}: {return_pct:+.1f}% — {'correct' if correct else 'wrong'}")

            update = {
                f"price_{key}_later": price_later,
                f"return_{key}_pct": round(return_pct, 2),
                f"signal_correct_{key}": correct,
                verified_field: True,
            }
            signals_col.update_one(
                {"ticker": sig.get("ticker"), "run_id": sig.get("run_id"), "horizon": sig.get("horizon")},
                {"$set": update},
            )
            total_verified += 1

            # Aggregate stats
            stats = horizon_stats[key]
            stats["total"] += 1
            if correct:
                stats["correct"] += 1
                stats["correct_returns"].append(return_pct)

            if confidence >= 80:
                stats["high_conf_total"] += 1
                if correct:
                    stats["high_conf_correct"] += 1
            elif confidence >= 60:
                stats["medium_conf_total"] += 1
                if correct:
                    stats["medium_conf_correct"] += 1
            else:
                stats["low_conf_total"] += 1
                if correct:
                    stats["low_conf_correct"] += 1

            st = signal_type.upper()
            if st == "BUY":
                stats["buy_total"] += 1
                if correct:
                    stats["buy_correct"] += 1
            elif st in ("SELL", "AVOID"):
                stats["sell_total"] += 1
                if correct:
                    stats["sell_correct"] += 1
            elif st == "HOLD":
                stats["hold_total"] += 1
                if correct:
                    stats["hold_correct"] += 1

    # Build scorecard
    scorecard: dict = {
        "run_date": now.isoformat(),
        "total_verified_this_run": total_verified,
        "total_skipped_this_run": total_skipped,
        "horizons": {},
    }

    _print_header()

    for key in ["30d", "90d", "180d"]:
        stats = horizon_stats[key]
        total = stats["total"]
        correct = stats["correct"]
        accuracy = (correct / total * 100) if total > 0 else 0.0

        hc_total = stats["high_conf_total"]
        hc_correct = stats["high_conf_correct"]
        hc_accuracy = (hc_correct / hc_total * 100) if hc_total > 0 else 0.0

        avg_return = (sum(stats["correct_returns"]) / len(stats["correct_returns"])) if stats["correct_returns"] else 0.0
        target_hit = hc_accuracy >= 70.0

        scorecard["horizons"][key] = {
            "total": total,
            "correct": correct,
            "accuracy_pct": round(accuracy, 1),
            "high_conf_accuracy_pct": round(hc_accuracy, 1),
            "avg_return_correct_pct": round(avg_return, 2),
            "target_hit": target_hit,
            "buy_accuracy": round((stats["buy_correct"] / stats["buy_total"] * 100) if stats["buy_total"] > 0 else 0, 1),
            "sell_accuracy": round((stats["sell_correct"] / stats["sell_total"] * 100) if stats["sell_total"] > 0 else 0, 1),
            "hold_accuracy": round((stats["hold_correct"] / stats["hold_total"] * 100) if stats["hold_total"] > 0 else 0, 1),
        }

        days_label = {"30d": "30d", "90d": "90d", "180d": "180d"}[key]
        target_str = "HIT ✅" if target_hit else "NOT YET"
        print(f"\n  ⏱  {days_label} horizon ({total} signals verified this run)")
        print(f"     Overall accuracy:     {accuracy:.0f}%")
        print(f"     High conf accuracy:   {hc_accuracy:.0f}%  ({target_str})")
        print(f"     BUY accuracy:         {scorecard['horizons'][key]['buy_accuracy']:.0f}%")
        print(f"     Avg return (correct): {avg_return:+.1f}%")
        print(f"     70% target:           {target_str}")

    print("=" * 50)

    scorecard_col.insert_one(scorecard)
    log.info(f"Scorecard saved — {total_verified} verified, {total_skipped} skipped")
    return scorecard


def _print_header():
    print()
    print("=" * 50)
    print("📊 SIGNAL ACCURACY SCORECARD")
    print("=" * 50)


if __name__ == "__main__":
    verify_signals()
