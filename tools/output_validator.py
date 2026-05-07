"""
Output validator — cross-checks LLM agent outputs against raw market data.

Runs after ranking, before delivery. Four checks:

  1. Missing price_at_signal    — breaks the 30/90/180d verification system
  2. RSI mismatch               — LLM-reported RSI vs recomputed from raw bars (±5 tolerance)
  3. Score range violations     — out-of-bounds values (confidence 0-100, scores 0-100)
  4. Hallucinated tickers       — signal tickers not present in screener_results for this run
"""

import logging
from datetime import datetime, timezone

from db import get_collection
from db.collections import Collections

logger = logging.getLogger(__name__)

RSI_TOLERANCE = 5.0   # points — accounts for minor bar-count differences between fetches


def _recompute_rsi(ticker: str) -> float | None:
    """Fetch 90 days of bars via yfinance and recompute RSI independently."""
    try:
        import tools.yfinance_client as yfc
        from mcp_servers.market_mcp import _compute_rsi
        raw = yfc.get_aggregates(ticker, 90)
        closes = [b["c"] for b in raw.get("results", [])]
        if len(closes) < 15:
            return None
        return _compute_rsi(closes)
    except Exception as e:
        logger.warning(f"[validator] RSI recompute failed for {ticker}: {e}")
        return None


def validate_run(run_id: str) -> dict:
    """
    Validate all signals and market data for a completed run.
    Saves the report to MongoDB and returns it.
    """
    report: dict = {
        "run_id": run_id,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        # check 1
        "missing_price": [],
        # check 2
        "rsi_mismatches": [],
        # check 3
        "score_violations": [],
        # check 4
        "hallucinated_tickers": [],
        # advisory — not failures
        "suspicious_signals": [],
        "warnings": [],
        "validation_passed": True,
    }

    # ── Build the ground-truth set of analysed tickers ───────────────────────
    screened = get_collection(Collections.SCREENER_RESULTS).find(
        {"run_id": run_id}, {"ticker": 1, "_id": 0}
    )
    screened_tickers = {doc["ticker"] for doc in screened}

    # ── Check 1 & 3 & 4: Signal-level checks ────────────────────────────────
    signals = list(get_collection(Collections.SIGNALS).find({"run_id": run_id}, {"_id": 0}))
    report["signals_total"] = len(signals)

    for sig in signals:
        ticker = sig.get("ticker", "?")
        horizon = sig.get("horizon", "?")

        # 1. Missing price_at_signal — critical
        price = sig.get("price_at_signal")
        if not price or price <= 0:
            report["missing_price"].append({"ticker": ticker, "horizon": horizon})
            report["validation_passed"] = False

        # 3. Score range checks
        for field, lo, hi in [
            ("confidence",        0, 100),
            ("technical_score",   0, 100),
            ("fundamental_score", 0, 100),
            ("geo_score",         0, 100),
            ("sentiment_score",   0, 10),
        ]:
            val = sig.get(field)
            if val is not None and not (lo <= val <= hi):
                report["score_violations"].append({
                    "ticker": ticker, "horizon": horizon,
                    "field": field, "value": val, "valid_range": f"{lo}-{hi}",
                })
                report["validation_passed"] = False

        # 4. Hallucinated ticker — signal for a ticker not in screener results
        if screened_tickers and ticker not in screened_tickers:
            report["hallucinated_tickers"].append({"ticker": ticker, "horizon": horizon})
            report["validation_passed"] = False

        # Advisory: BUY signal with very low technical AND fundamental scores
        if sig.get("signal") == "BUY":
            tech = sig.get("technical_score") or 50
            fund = sig.get("fundamental_score") or 50
            if tech < 20 and fund < 20:
                report["suspicious_signals"].append({
                    "ticker": ticker, "horizon": horizon,
                    "reason": f"BUY but technical={tech}, fundamental={fund}",
                })
                report["warnings"].append(
                    f"{ticker}/{horizon}: BUY with very low scores (tech={tech}, fund={fund}) — review manually"
                )

    # ── Check 2: RSI cross-reference ─────────────────────────────────────────
    market_docs = list(get_collection(Collections.MARKET_DATA).find({"run_id": run_id}, {"_id": 0}))
    report["market_docs_total"] = len(market_docs)

    for doc in market_docs:
        ticker = doc.get("ticker", "?")
        agent_rsi = doc.get("rsi")
        if agent_rsi is None:
            continue

        computed_rsi = _recompute_rsi(ticker)
        if computed_rsi is None:
            continue

        delta = abs(float(agent_rsi) - computed_rsi)
        if delta > RSI_TOLERANCE:
            report["rsi_mismatches"].append({
                "ticker": ticker,
                "agent_rsi": round(float(agent_rsi), 2),
                "computed_rsi": round(computed_rsi, 2),
                "delta": round(delta, 2),
            })
            report["warnings"].append(
                f"{ticker}: RSI mismatch — agent reported {agent_rsi:.1f}, "
                f"recomputed {computed_rsi:.1f} (Δ{delta:.1f})"
            )
            report["validation_passed"] = False

    report["total_warnings"] = len(report["warnings"])

    get_collection(Collections.VALIDATION_RESULTS).update_one(
        {"run_id": run_id},
        {"$set": report},
        upsert=True,
    )

    return report


def print_validation_report(report: dict) -> None:
    """Pretty-print the validation report to stdout."""
    passed = report.get("validation_passed", False)
    total = report.get("signals_total", 0)
    warnings = report.get("total_warnings", 0)

    status = "PASSED" if passed else "FAILED"
    print(f"\n  Validation {status} — {total} signals, {warnings} warnings")

    for item in report.get("missing_price", []):
        print(f"  [CRITICAL] Missing price_at_signal: {item['ticker']}/{item['horizon']}")

    for item in report.get("hallucinated_tickers", []):
        print(f"  [CRITICAL] Hallucinated ticker not in screener: {item['ticker']}/{item['horizon']}")

    for item in report.get("score_violations", []):
        print(f"  [FAIL] Score out of range: {item['ticker']}/{item['horizon']} "
              f"{item['field']}={item['value']} (expected {item['valid_range']})")

    for item in report.get("rsi_mismatches", []):
        print(f"  [FAIL] RSI mismatch {item['ticker']}: "
              f"agent={item['agent_rsi']}, actual={item['computed_rsi']} (Δ{item['delta']})")

    for msg in report.get("suspicious_signals", []):
        print(f"  [WARN] {msg['reason']}")
