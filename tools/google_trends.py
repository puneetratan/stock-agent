"""
Google Trends tool — free retail sentiment data via pytrends.

Peak Google Trends for a stock/theme often correlates with peak price
(retail FOMO at the top). Use to detect greed/fear cycles.
"""

import logging
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Keywords to track for market sentiment context
FEAR_KEYWORDS = ["stock market crash", "recession 2026", "bear market", "inflation"]
GREED_KEYWORDS = ["how to buy stocks", "best stocks 2026", "get rich stocks", "stock tips"]
THEME_KEYWORDS = ["AI stocks", "defence stocks", "oil stocks", "gold", "bitcoin"]


def _get_pytrends():
    try:
        from pytrends.request import TrendReq
        return TrendReq(hl="en-US", tz=0, timeout=(10, 25))
    except ImportError:
        raise ImportError("pytrends not installed — run: uv add pytrends")


def get_trend_score(keyword: str, timeframe: str = "today 3-m") -> dict:
    """
    Returns current interest score (0-100), trend direction, and peak date.
    """
    try:
        pt = _get_pytrends()
        pt.build_payload([keyword], timeframe=timeframe)
        df = pt.interest_over_time()

        if df.empty or keyword not in df.columns:
            return {"keyword": keyword, "current_score": 0, "trend": "no_data", "peak_date": None, "vs_30d_ago": None}

        series = df[keyword].dropna()
        if len(series) < 2:
            return {"keyword": keyword, "current_score": int(series.iloc[-1]) if len(series) else 0, "trend": "insufficient_data", "peak_date": None, "vs_30d_ago": None}

        current_score = int(series.iloc[-1])
        peak_idx = series.idxmax()
        peak_date = peak_idx.strftime("%Y-%m-%d") if hasattr(peak_idx, "strftime") else str(peak_idx)

        # Compare to 30 days ago (approx 4 weeks back in weekly data)
        lookback = min(4, len(series) - 1)
        score_30d_ago = int(series.iloc[-(lookback + 1)])
        delta = current_score - score_30d_ago

        if current_score >= series.max() * 0.9:
            trend = "peak"
        elif delta > 10:
            trend = "rising"
        elif delta < -10:
            trend = "falling"
        else:
            trend = "stable"

        return {
            "keyword": keyword,
            "current_score": current_score,
            "trend": trend,
            "peak_date": peak_date,
            "vs_30d_ago": delta,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        log.warning(f"[google_trends] get_trend_score failed for '{keyword}': {e}")
        return {"keyword": keyword, "current_score": 0, "trend": "error", "error": str(e)}


def get_related_queries(keyword: str) -> list[str]:
    """Returns top rising related queries for emerging sub-theme detection."""
    try:
        pt = _get_pytrends()
        pt.build_payload([keyword], timeframe="today 3-m")
        related = pt.related_queries()
        rising = related.get(keyword, {}).get("rising")
        if rising is not None and not rising.empty:
            return rising["query"].head(10).tolist()
        return []
    except Exception as e:
        log.warning(f"[google_trends] get_related_queries failed for '{keyword}': {e}")
        return []


def compare_trends(keywords: list[str], timeframe: str = "today 3-m") -> dict:
    """
    Compares multiple keywords on the same 0-100 scale.
    Example: compare ["buy NVDA", "sell NVDA", "NVDA crash"]
    """
    try:
        pt = _get_pytrends()
        # pytrends allows max 5 keywords at once
        results = {}
        for i in range(0, len(keywords), 5):
            batch = keywords[i:i + 5]
            pt.build_payload(batch, timeframe=timeframe)
            df = pt.interest_over_time()
            for kw in batch:
                if kw in df.columns:
                    results[kw] = int(df[kw].iloc[-1]) if not df.empty else 0
                else:
                    results[kw] = 0
            time.sleep(0.5)
        return {"comparison": results, "captured_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        log.warning(f"[google_trends] compare_trends failed: {e}")
        return {"comparison": {}, "error": str(e)}


def get_regional_interest(keyword: str) -> dict:
    """Returns which countries have the highest interest in a keyword."""
    try:
        pt = _get_pytrends()
        pt.build_payload([keyword], timeframe="today 3-m")
        by_region = pt.interest_by_region(resolution="COUNTRY", inc_low_vol=False)
        if by_region.empty or keyword not in by_region.columns:
            return {"keyword": keyword, "top_regions": []}
        top = by_region[keyword].sort_values(ascending=False).head(10)
        return {
            "keyword": keyword,
            "top_regions": [{"region": str(r), "score": int(v)} for r, v in top.items()],
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        log.warning(f"[google_trends] get_regional_interest failed for '{keyword}': {e}")
        return {"keyword": keyword, "top_regions": [], "error": str(e)}


def get_sentiment_snapshot() -> dict:
    """
    Fetches fear/greed keyword scores in one call.
    Used by the weekly sentiment snapshot job.
    """
    snapshot = {"fear": {}, "greed": {}, "themes": {}, "captured_at": datetime.now(timezone.utc).isoformat()}

    for kw in FEAR_KEYWORDS:
        result = get_trend_score(kw)
        snapshot["fear"][kw] = result
        time.sleep(0.5)

    for kw in GREED_KEYWORDS:
        result = get_trend_score(kw)
        snapshot["greed"][kw] = result
        time.sleep(0.5)

    for kw in THEME_KEYWORDS:
        result = get_trend_score(kw)
        snapshot["themes"][kw] = result
        time.sleep(0.5)

    # Compute aggregate fear score and greed score (average of current scores)
    fear_scores = [v.get("current_score", 0) for v in snapshot["fear"].values()]
    greed_scores = [v.get("current_score", 0) for v in snapshot["greed"].values()]
    snapshot["aggregate_fear_score"] = round(sum(fear_scores) / len(fear_scores), 1) if fear_scores else 0
    snapshot["aggregate_greed_score"] = round(sum(greed_scores) / len(greed_scores), 1) if greed_scores else 0

    return snapshot
