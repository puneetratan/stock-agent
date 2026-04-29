"""
dashboard.py — Terminal metrics dashboard.

Shows system health at a glance: accuracy, recent signals, crossover status, data health.

Usage:
    uv run python dashboard.py
"""

import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))


def _divider(width: int = 45) -> str:
    return "─" * width


def _box(lines: list[str], width: int = 45) -> None:
    print("┌" + "─" * (width - 2) + "┐")
    for line in lines:
        padded = f"│ {line:<{width - 4}} │"
        print(padded)
    print("└" + "─" * (width - 2) + "┘")


def section_accuracy(db) -> None:
    from db.collections import Collections
    col = db[Collections.ACCURACY_SCORECARD]

    print("\n  📈 SIGNAL ACCURACY SCORECARD")
    print("  " + _divider())

    scorecard = col.find_one({}, {"_id": 0}, sort=[("run_date", -1)])
    if not scorecard:
        print("  No accuracy data yet — run signal_verification_job.py first.")
        return

    run_date = scorecard.get("run_date", "unknown")[:10]
    print(f"  Last verified: {run_date}")
    print()

    rows = []
    for key, label in [("30d", "30d"), ("90d", "90d"), ("180d", "180d")]:
        h = scorecard.get("horizons", {}).get(key, {})
        if not h:
            continue
        acc = h.get("accuracy_pct", 0)
        hc = h.get("high_conf_accuracy_pct", 0)
        total = h.get("total", 0)
        target = "✅" if h.get("target_hit") else "  "
        rows.append(f"  {label}:  overall {acc:.0f}%  high-conf {hc:.0f}%  ({total} signals)  {target}")

    if rows:
        for r in rows:
            print(r)
    else:
        print("  No horizon data in latest scorecard.")

    total_ver = scorecard.get("total_verified_this_run", 0)
    print(f"\n  Signals verified in last run: {total_ver}")


def section_recent_signals(db, limit: int = 10) -> None:
    from db.collections import Collections
    col = db[Collections.SIGNALS]

    print("\n\n  📋 RECENT SIGNALS (last 10)")
    print("  " + _divider())

    signals = list(col.find(
        {},
        {"_id": 0, "ticker": 1, "signal": 1, "horizon": 1, "confidence": 1,
         "created_at": 1, "verified_30d": 1, "return_30d_pct": 1, "signal_correct_30d": 1},
        sort=[("created_at", -1)],
        limit=limit,
    ))

    if not signals:
        print("  No signals yet.")
        return

    print(f"  {'Ticker':<7} {'Signal':<6} {'Horizon':<10} {'Conf':<5} {'Verified':<9} {'Return':<8} {'Date'}")
    print("  " + _divider(70))
    for s in signals:
        date_str = s.get("created_at", "")[:10]
        verified = "✅" if s.get("verified_30d") else "⏳"
        ret = f"{s['return_30d_pct']:+.1f}%" if s.get("return_30d_pct") is not None else "—"
        correct = "✓" if s.get("signal_correct_30d") else ("✗" if s.get("verified_30d") else "")
        print(f"  {s.get('ticker','?'):<7} {s.get('signal','?'):<6} {s.get('horizon','?'):<10} "
              f"{s.get('confidence',0):<5} {verified:<9} {ret:<8} {date_str} {correct}")


def section_top_agents(db) -> None:
    from db.collections import Collections

    print("\n\n  🏆 SIGNAL CONFIDENCE DISTRIBUTION")
    print("  " + _divider())

    col = db[Collections.SIGNALS]
    total = col.count_documents({})
    high = col.count_documents({"confidence": {"$gte": 80}})
    medium = col.count_documents({"confidence": {"$gte": 60, "$lt": 80}})
    low = col.count_documents({"confidence": {"$lt": 60}})

    if total == 0:
        print("  No signals yet.")
        return

    print(f"  Total signals:  {total}")
    print(f"  High conf (≥80): {high} ({high/total*100:.0f}%)")
    print(f"  Med conf  (60-79): {medium} ({medium/total*100:.0f}%)")
    print(f"  Low conf  (<60): {low} ({low/total*100:.0f}%)")

    # BUY vs SELL vs HOLD breakdown
    buy = col.count_documents({"signal": "BUY"})
    sell = col.count_documents({"signal": {"$in": ["SELL", "AVOID"]}})
    hold = col.count_documents({"signal": "HOLD"})
    print(f"\n  BUY: {buy}  |  SELL/AVOID: {sell}  |  HOLD: {hold}")


def section_crossover(db) -> None:
    from db.collections import Collections

    print("\n\n  💰 CROSSOVER TRACKER")
    print("  " + _divider())

    try:
        from tools.crossover_tracker import get_crossover_status
        status = get_crossover_status()
    except Exception as e:
        print(f"  Could not load crossover data: {e}")
        return

    job = status.get("job_income_avg", 0)
    side = status.get("side_income_avg", 0)
    confirmed = status.get("crossover_confirmed", False)
    consecutive = status.get("months_consecutive", 0)
    gap = status.get("gap_to_crossover", "N/A")
    proj = status.get("projected_crossover", "N/A")

    if confirmed:
        print("  🎉 CROSSOVER CONFIRMED — 3+ consecutive months!")
    else:
        print(f"  Job income (3mo avg):  ${job:>10,.0f}")
        print(f"  Side income (3mo avg): ${side:>10,.0f}")
        print(f"  Gap remaining:         {gap}")
        print(f"  Consecutive months:    {consecutive}/{3}")
        print(f"  At current growth:     {proj}")
        print()
        print("  Run tools/crossover_tracker.py to record monthly income.")


def section_sentiment(db) -> None:
    from db.collections import Collections

    print("\n\n  🧠 MARKET SENTIMENT")
    print("  " + _divider())

    col = db[Collections.SENTIMENT_HISTORY]
    latest = col.find_one({}, {"_id": 0, "market_emotion": 1, "fear_greed_score": 1,
                                "summary": 1, "captured_at": 1, "narrative_cycles": 1},
                          sort=[("captured_at", -1)])

    if not latest:
        print("  No sentiment data yet — run agents/sentiment.py first.")
        return

    captured = latest.get("captured_at", "")[:10]
    emotion = latest.get("market_emotion", "unknown").upper()
    score = latest.get("fear_greed_score", 50)
    bar_len = int(score / 5)
    bar = "█" * bar_len + "░" * (20 - bar_len)
    print(f"  As of: {captured}")
    print(f"  Emotion:    {emotion}  (score: {score}/100)")
    print(f"  Fear◄{bar}►Greed")

    cycles = latest.get("narrative_cycles", {})
    if cycles:
        print("\n  Narrative Cycles:")
        for theme, phase in cycles.items():
            phase_short = phase.replace("phase_", "P").replace("_", " ")
            print(f"    {theme:<15}: {phase_short}")


def section_data_health(db) -> None:
    from db.collections import Collections

    print("\n\n  🗄️  DATA HEALTH")
    print("  " + _divider())

    signals_col = db[Collections.SIGNALS]
    total_signals = signals_col.count_documents({})
    verified_30d = signals_col.count_documents({"verified_30d": True})

    # Days running — from oldest signal
    oldest = signals_col.find_one({}, {"created_at": 1, "_id": 0}, sort=[("created_at", 1)])
    days_running = 0
    if oldest and oldest.get("created_at"):
        try:
            first_date = datetime.fromisoformat(oldest["created_at"].replace("Z", "+00:00"))
            days_running = (datetime.now(timezone.utc) - first_date).days
        except Exception:
            pass

    # Last run time
    latest_sig = signals_col.find_one({}, {"created_at": 1, "_id": 0}, sort=[("created_at", -1)])
    last_run = "never"
    hours_ago = "?"
    if latest_sig and latest_sig.get("created_at"):
        try:
            last_dt = datetime.fromisoformat(latest_sig["created_at"].replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - last_dt
            hours_ago = f"{delta.total_seconds() / 3600:.1f}"
            last_run = last_dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            pass

    print(f"  Total signals stored:  {total_signals}")
    print(f"  Signals verified (30d): {verified_30d}")
    print(f"  Days running:          {days_running}")
    print(f"  Last agent run:        {last_run} ({hours_ago}h ago)")

    # MongoDB collections overview
    collections_to_check = [
        Collections.SIGNALS, Collections.ACCURACY_SCORECARD,
        Collections.SENTIMENT_HISTORY, Collections.NARRATIVE_CYCLES,
        Collections.CROSSOVER_DATA, Collections.GOOGLE_TRENDS,
    ]
    print("\n  Collection counts:")
    for c in collections_to_check:
        try:
            count = db[c].count_documents({})
            print(f"    {c:<30}: {count}")
        except Exception:
            pass


def main():
    print("\n" + "=" * 55)
    print("  📊 STOCK INTELLIGENCE AGENT — DASHBOARD")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    try:
        from db.client import get_db
        db = get_db()
    except Exception as e:
        print(f"\n  ❌ Cannot connect to MongoDB: {e}")
        print("  Check MONGO_URI in .env")
        sys.exit(1)

    section_accuracy(db)
    section_recent_signals(db)
    section_top_agents(db)
    section_sentiment(db)
    section_crossover(db)
    section_data_health(db)

    print("\n" + "=" * 55 + "\n")


if __name__ == "__main__":
    main()
