"""
Crossover Tracker — tracks the point where side-gig income exceeds full-time salary.

Crossover is CONFIRMED when side income > job income for 3 consecutive months.
"""

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

CONFIRMED_MONTHS_REQUIRED = 3


def _get_col():
    from db import get_collection
    from db.collections import Collections
    return get_collection(Collections.CROSSOVER_DATA)


def _get_portfolio_return_month() -> float:
    """Calculate this month's portfolio return from verified signals."""
    try:
        from db import get_collection
        from db.collections import Collections
        from datetime import timedelta

        col = get_collection(Collections.SIGNALS)
        month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        signals = list(col.find(
            {"verified_30d": True, "return_30d_pct": {"$exists": True}, "created_at": {"$gte": month_ago}},
            {"return_30d_pct": 1, "_id": 0},
        ))
        if not signals:
            return 0.0
        returns = [s.get("return_30d_pct", 0.0) for s in signals]
        return round(sum(returns) / len(returns), 2)
    except Exception as e:
        log.warning(f"[crossover] Could not calculate portfolio return: {e}")
        return 0.0


def _get_portfolio_value() -> float:
    """
    Returns approximate portfolio value.
    Uses latest crossover record's value if available; otherwise returns 0.
    Extend this to connect to a brokerage API if needed.
    """
    try:
        latest = _get_col().find_one({}, {"portfolio_value": 1, "_id": 0}, sort=[("date", -1)])
        return float(latest.get("portfolio_value", 0.0)) if latest else 0.0
    except Exception:
        return 0.0


def record_monthly(job_income: float, product_revenue: float = 0.0, portfolio_value: float | None = None) -> dict:
    """
    Record monthly income figures.
    Call once a month — system auto-calculates portfolio return.

    Args:
        job_income:       full-time salary this month
        product_revenue:  newsletter/API revenue this month
        portfolio_value:  current portfolio value (optional — uses last known if omitted)

    Returns the recorded document.
    """
    now = datetime.now(timezone.utc)
    col = _get_col()

    portfolio_return_month = _get_portfolio_return_month()
    pv = portfolio_value if portfolio_value is not None else _get_portfolio_value()

    # Approximate portfolio income from the return percentage
    portfolio_income = round(pv * portfolio_return_month / 100, 2) if pv > 0 else 0.0
    total_side_income = round(portfolio_income + product_revenue, 2)

    doc = {
        "date": now.isoformat(),
        "year_month": now.strftime("%Y-%m"),
        "job_income": round(job_income, 2),
        "portfolio_value": round(pv, 2),
        "portfolio_return_month": portfolio_return_month,
        "portfolio_income": portfolio_income,
        "product_revenue": round(product_revenue, 2),
        "total_side_income": total_side_income,
        "crossover_reached": total_side_income >= job_income,
    }

    # Calculate consecutive months above crossover
    history = list(col.find({}, {"crossover_reached": 1, "date": 1, "_id": 0}, sort=[("date", -1)], limit=CONFIRMED_MONTHS_REQUIRED))
    consecutive = 0
    if doc["crossover_reached"]:
        consecutive = 1
        for past in history:
            if past.get("crossover_reached"):
                consecutive += 1
            else:
                break

    doc["months_above_job"] = consecutive
    doc["crossover_confirmed"] = consecutive >= CONFIRMED_MONTHS_REQUIRED

    if doc["crossover_confirmed"] and not any(h.get("crossover_confirmed") for h in history):
        doc["crossover_date"] = now.isoformat()
        log.info("🎉 CROSSOVER CONFIRMED — 3 consecutive months!")

    col.insert_one({k: v for k, v in doc.items() if k != "_id"})
    log.info(f"[crossover] Recorded: job={job_income}, side={total_side_income}, confirmed={doc['crossover_confirmed']}")
    return doc


def get_crossover_status() -> dict:
    """
    Returns current crossover status based on last 3 months of data.
    """
    col = _get_col()
    history = list(col.find({}, {"_id": 0}, sort=[("date", -1)], limit=6))

    if not history:
        return {
            "job_income_avg": 0.0,
            "side_income_avg": 0.0,
            "crossover_reached": False,
            "months_consecutive": 0,
            "crossover_confirmed": False,
            "gap_to_crossover": "No data yet",
            "projected_crossover": "Need more data",
        }

    recent_3 = history[:3]
    job_avg = round(sum(r.get("job_income", 0) for r in recent_3) / len(recent_3), 2)
    side_avg = round(sum(r.get("total_side_income", 0) for r in recent_3) / len(recent_3), 2)

    consecutive = 0
    for rec in recent_3:
        if rec.get("crossover_reached"):
            consecutive += 1
        else:
            break

    gap = round(job_avg - side_avg, 2) if side_avg < job_avg else 0.0

    # Project crossover date based on growth trend
    projected = "N/A"
    if len(history) >= 2 and side_avg < job_avg:
        values = [r.get("total_side_income", 0) for r in reversed(history)]
        if len(values) >= 2 and values[0] > 0:
            growth_rate = (values[-1] / values[0]) ** (1 / len(values)) - 1 if values[0] > 0 else 0
            if growth_rate > 0:
                months_needed = 0
                current = side_avg
                while current < job_avg and months_needed < 120:
                    current *= (1 + growth_rate)
                    months_needed += 1
                from datetime import timedelta
                proj_date = datetime.now(timezone.utc) + timedelta(days=months_needed * 30)
                projected = proj_date.strftime("%Y-%m")

    return {
        "job_income_avg": job_avg,
        "side_income_avg": side_avg,
        "crossover_reached": side_avg >= job_avg,
        "months_consecutive": consecutive,
        "crossover_confirmed": consecutive >= CONFIRMED_MONTHS_REQUIRED,
        "gap_to_crossover": f"${gap:,.0f}/month" if gap > 0 else "Already crossed",
        "projected_crossover": projected,
    }


def plot_crossover_chart() -> None:
    """
    Prints a simple ASCII chart of job vs side income over time.
    """
    col = _get_col()
    history = list(col.find({}, {"_id": 0, "year_month": 1, "job_income": 1, "total_side_income": 1}, sort=[("date", 1)], limit=24))

    if not history:
        print("No crossover data yet. Run record_monthly() first.")
        return

    max_val = max(
        max(r.get("job_income", 0) for r in history),
        max(r.get("total_side_income", 0) for r in history),
    )
    if max_val == 0:
        print("No income data to chart.")
        return

    width = 40
    print("\n  Income Crossover Chart")
    print("  " + "-" * (width + 14))
    for rec in history:
        month = rec.get("year_month", "??-??")
        job = rec.get("job_income", 0)
        side = rec.get("total_side_income", 0)
        job_bar = int(job / max_val * width)
        side_bar = int(side / max_val * width)
        print(f"  {month}  J: {'█' * job_bar:<{width}} ${job:,.0f}")
        print(f"            S: {'░' * side_bar:<{width}} ${side:,.0f}")
        print()
    print("  J = Job income  |  S = Side income")
    print("  " + "-" * (width + 14) + "\n")
