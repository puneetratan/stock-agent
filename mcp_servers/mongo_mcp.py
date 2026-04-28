"""
MCP server: mongo_mcp — wraps MongoDB Atlas read/write operations.

Agents call these tools to persist and retrieve all analysis data.
"""

from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from db import get_collection
from db.collections import Collections

mcp = FastMCP("mongo_mcp")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp(doc: dict) -> dict:
    doc["updated_at"] = _now()
    return doc


# ---------------------------------------------------------------------------
# Write Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def save_market_report(ticker: str, report: dict) -> bool:
    """Upsert technical market analysis report for a ticker."""
    try:
        col = get_collection(Collections.MARKET_DATA)
        col.update_one(
            {"ticker": ticker, "run_id": report.get("run_id")},
            {"$set": _stamp({**report, "ticker": ticker})},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[mongo_mcp] save_market_report error: {e}")
        return False


@mcp.tool()
def save_news_report(ticker: str, report: dict) -> bool:
    """Upsert news sentiment report for a ticker."""
    try:
        col = get_collection(Collections.NEWS_SENTIMENT)
        col.update_one(
            {"ticker": ticker, "run_id": report.get("run_id")},
            {"$set": _stamp({**report, "ticker": ticker})},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[mongo_mcp] save_news_report error: {e}")
        return False


@mcp.tool()
def save_fundamentals_report(ticker: str, report: dict) -> bool:
    """Upsert fundamental analysis report for a ticker."""
    try:
        col = get_collection(Collections.FUNDAMENTALS)
        col.update_one(
            {"ticker": ticker, "run_id": report.get("run_id")},
            {"$set": _stamp({**report, "ticker": ticker})},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[mongo_mcp] save_fundamentals_report error: {e}")
        return False


@mcp.tool()
def save_geo_report(ticker: str, report: dict) -> bool:
    """Upsert geo/macro risk report for a ticker."""
    try:
        col = get_collection(Collections.GEO_MACRO)
        col.update_one(
            {"ticker": ticker, "run_id": report.get("run_id")},
            {"$set": _stamp({**report, "ticker": ticker})},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[mongo_mcp] save_geo_report error: {e}")
        return False


@mcp.tool()
def save_final_signal(signal: dict) -> bool:
    """Persist a final BUY/SELL/HOLD signal from Ranking Agent."""
    try:
        col = get_collection(Collections.SIGNALS)
        col.update_one(
            {"ticker": signal.get("ticker"), "run_id": signal.get("run_id"), "horizon": signal.get("horizon")},
            {"$set": _stamp(signal)},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[mongo_mcp] save_final_signal error: {e}")
        return False


@mcp.tool()
def save_causal_theses(theses: list) -> bool:
    """Bulk upsert causal analyses from CausalReasoningAgent."""
    try:
        col = get_collection(Collections.CAUSAL_THESES)
        for thesis in theses:
            col.update_one(
                {"theme_id": thesis.get("theme_id"), "run_id": thesis.get("run_id")},
                {"$set": _stamp(thesis)},
                upsert=True,
            )
        return True
    except Exception as e:
        print(f"[mongo_mcp] save_causal_theses error: {e}")
        return False


@mcp.tool()
def save_screener_results(results: list) -> bool:
    """Persist screener output (list of candidate tickers with scores)."""
    try:
        col = get_collection(Collections.SCREENER_RESULTS)
        for r in results:
            col.update_one(
                {"ticker": r.get("ticker"), "run_id": r.get("run_id")},
                {"$set": _stamp(r)},
                upsert=True,
            )
        return True
    except Exception as e:
        print(f"[mongo_mcp] save_screener_results error: {e}")
        return False


# ---------------------------------------------------------------------------
# Read Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_recent_themes() -> list[dict]:
    """Return world themes from the last 3 most recent runs."""
    try:
        col = get_collection(Collections.WORLD_THEMES)
        docs = list(col.find({}, {"_id": 0}).sort("detected_at", -1).limit(30))
        return docs
    except Exception as e:
        print(f"[mongo_mcp] get_recent_themes error: {e}")
        return []


@mcp.tool()
def get_causal_theses() -> list[dict]:
    """Return the most recent causal analyses (latest run first)."""
    try:
        col = get_collection(Collections.CAUSAL_THESES)
        docs = list(col.find({}, {"_id": 0}).sort("updated_at", -1).limit(20))
        return docs
    except Exception as e:
        print(f"[mongo_mcp] get_causal_theses error: {e}")
        return []


@mcp.tool()
def get_all_reports(run_id: str) -> dict:
    """Aggregate all agent reports for a given run_id into one dict."""
    try:
        def fetch(collection: str) -> list[dict]:
            col = get_collection(collection)
            return list(col.find({"run_id": run_id}, {"_id": 0}))

        return {
            "market_reports":       fetch(Collections.MARKET_DATA),
            "news_reports":         fetch(Collections.NEWS_SENTIMENT),
            "fundamentals_reports": fetch(Collections.FUNDAMENTALS),
            "geo_reports":          fetch(Collections.GEO_MACRO),
            "causal_theses":        fetch(Collections.CAUSAL_THESES),
            "screener_results":     fetch(Collections.SCREENER_RESULTS),
        }
    except Exception as e:
        print(f"[mongo_mcp] get_all_reports error: {e}")
        return {}


@mcp.tool()
def vector_search(ticker: str, query: str) -> list[dict]:
    """
    Approximate vector search using text index on embeddings collection.
    Replace with Atlas Vector Search ($vectorSearch) for production use.
    """
    try:
        col = get_collection(Collections.EMBEDDINGS)
        docs = list(col.find(
            {"$text": {"$search": f"{ticker} {query}"}},
            {"_id": 0, "score": {"$meta": "textScore"}},
        ).sort([("score", {"$meta": "textScore"})]).limit(5))
        return docs
    except Exception:
        # Text index may not exist yet — return empty list gracefully
        return []


@mcp.tool()
def get_past_causal_analyses() -> list[dict]:
    """Return historical causal analyses for pattern learning."""
    try:
        col = get_collection(Collections.CAUSAL_THESES)
        docs = list(col.find({}, {"_id": 0}).sort("updated_at", -1).limit(50))
        return docs
    except Exception as e:
        print(f"[mongo_mcp] get_past_causal_analyses error: {e}")
        return []


@mcp.tool()
def get_signal_history(ticker: str) -> list[dict]:
    """Return all past signals for a ticker — useful for tracking accuracy."""
    try:
        col = get_collection(Collections.SIGNALS)
        docs = list(col.find({"ticker": ticker}, {"_id": 0}).sort("updated_at", -1).limit(20))
        return docs
    except Exception as e:
        print(f"[mongo_mcp] get_signal_history error: {e}")
        return []


if __name__ == "__main__":
    mcp.run(transport="stdio")
