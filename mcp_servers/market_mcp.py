"""
MCP server: market_mcp — wraps Polygon.io REST API.

Starts as a subprocess; agents call its tools via MCP protocol.
Each tool: (1) calls Polygon, (2) saves raw data to MongoDB, (3) returns processed data.
"""

import math
import statistics
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from db import get_collection
from db.collections import Collections
import tools.yfinance_client as yfc

mcp = FastMCP("market_mcp")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_raw(collection: str, ticker: str, endpoint: str, raw: dict) -> None:
    get_collection(collection).insert_one(
        {"ticker": ticker, "endpoint": endpoint, "raw": raw, "saved_at": _now()}
    )


# ---------------------------------------------------------------------------
# RSI calculation (Wilder's smoothed method)
# ---------------------------------------------------------------------------

def _compute_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


# ---------------------------------------------------------------------------
# MACD calculation
# ---------------------------------------------------------------------------

def _ema(prices: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    ema_vals = [prices[0]]
    for p in prices[1:]:
        ema_vals.append(p * k + ema_vals[-1] * (1 - k))
    return ema_vals


def _compute_macd(closes: list[float]) -> dict:
    if len(closes) < 26:
        return {"signal": "insufficient_data", "macd": None, "histogram": None}
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema12[13:], ema26)]
    if len(macd_line) < 9:
        return {"signal": "insufficient_data", "macd": None, "histogram": None}
    signal_line = _ema(macd_line, 9)
    histogram = [m - s for m, s in zip(macd_line[-9:], signal_line[-9:])]
    latest_hist = histogram[-1]
    prev_hist = histogram[-2] if len(histogram) > 1 else 0

    if latest_hist > 0 and prev_hist <= 0:
        sig = "bullish_cross"
    elif latest_hist < 0 and prev_hist >= 0:
        sig = "bearish_cross"
    elif latest_hist > prev_hist:
        sig = "bullish_momentum"
    else:
        sig = "bearish_momentum"

    return {
        "signal": sig,
        "macd": round(macd_line[-1], 4),
        "signal_line": round(signal_line[-1], 4),
        "histogram": round(latest_hist, 4),
    }


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_price_history(ticker: str, days: int = 90) -> dict:
    """Fetch daily OHLCV history for `ticker` over last `days` calendar days."""
    try:
        raw = yfc.get_aggregates(ticker, days)
        _save_raw(Collections.MARKET_DATA, ticker, "aggregates", raw)
        bars = raw.get("results", [])
        return {
            "ticker": ticker,
            "bars": bars,
            "count": len(bars),
            "source": "yfinance",
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e), "bars": []}


@mcp.tool()
def get_rsi(ticker: str) -> dict:
    """Compute 14-period RSI from last 90 days of price data."""
    try:
        raw = yfc.get_aggregates(ticker, 90)
        bars = raw.get("results", [])
        closes = [b["c"] for b in bars]
        rsi = _compute_rsi(closes)
        return {"ticker": ticker, "rsi": rsi, "bars_used": len(closes)}
    except Exception as e:
        return {"ticker": ticker, "rsi": None, "error": str(e)}


@mcp.tool()
def get_macd(ticker: str) -> dict:
    """Compute MACD (12/26/9) from last 90 days of price data."""
    try:
        raw = yfc.get_aggregates(ticker, 120)
        bars = raw.get("results", [])
        closes = [b["c"] for b in bars]
        result = _compute_macd(closes)
        result["ticker"] = ticker
        return result
    except Exception as e:
        return {"ticker": ticker, "signal": "error", "error": str(e)}


@mcp.tool()
def get_volume_profile(ticker: str) -> dict:
    """Average volume vs recent volume — detects unusual activity."""
    try:
        raw = yfc.get_aggregates(ticker, 60)
        bars = raw.get("results", [])
        if not bars:
            return {"ticker": ticker, "error": "no data"}
        volumes = [b["v"] for b in bars]
        avg_vol = statistics.mean(volumes[:-5]) if len(volumes) > 5 else statistics.mean(volumes)
        recent_vol = statistics.mean(volumes[-5:])
        ratio = round(recent_vol / avg_vol, 2) if avg_vol else 1.0
        trend = "increasing" if ratio > 1.1 else ("decreasing" if ratio < 0.9 else "neutral")
        return {
            "ticker": ticker,
            "avg_volume_20d": round(avg_vol),
            "recent_volume_5d": round(recent_vol),
            "volume_ratio": ratio,
            "trend": trend,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


@mcp.tool()
def get_options_flow(ticker: str) -> dict:
    """Summarise options chain to derive call/put sentiment."""
    try:
        raw = yfc.get_options_contracts(ticker)
        _save_raw(Collections.MARKET_DATA, ticker, "options", raw)
        contracts = raw.get("results", [])
        calls = [c for c in contracts if c.get("contract_type") == "call"]
        puts = [c for c in contracts if c.get("contract_type") == "put"]
        ratio = round(len(calls) / len(puts), 2) if puts else 0.0
        sentiment = "bullish" if ratio > 1.2 else ("bearish" if ratio < 0.8 else "neutral")
        return {
            "ticker": ticker,
            "call_count": len(calls),
            "put_count": len(puts),
            "call_put_ratio": ratio,
            "sentiment": sentiment,
        }
    except Exception as e:
        return {"ticker": ticker, "sentiment": "unknown", "error": str(e)}


@mcp.tool()
def get_52w_range(ticker: str) -> dict:
    """52-week high/low and current price position within that range."""
    try:
        raw = yfc.get_aggregates(ticker, 365)
        bars = raw.get("results", [])
        if not bars:
            return {"ticker": ticker, "error": "no data"}
        highs = [b["h"] for b in bars]
        lows = [b["l"] for b in bars]
        current = bars[-1]["c"]
        high52 = max(highs)
        low52 = min(lows)
        pct_from_low = round((current - low52) / (high52 - low52) * 100, 1) if high52 != low52 else 50.0
        return {
            "ticker": ticker,
            "current_price": current,
            "52w_high": high52,
            "52w_low": low52,
            "pct_above_52w_low": pct_from_low,
            "pct_from_52w_high": round((high52 - current) / high52 * 100, 1),
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


@mcp.tool()
def get_sector_stocks(sector: str) -> list[str]:
    """Return a list of tickers for a given sector from Polygon reference data."""
    try:
        from agents.screener import GLOBAL_UNIVERSE
        return [t for t, _, _ in GLOBAL_UNIVERSE][:100]
    except Exception:
        return []


@mcp.tool()
def get_stock_metrics(ticker: str) -> dict:
    """Price + market cap + basic metadata for a single ticker."""
    try:
        snap = yfc.get_snapshot(ticker)
        detail = yfc.get_ticker_details(ticker)
        _save_raw(Collections.MARKET_DATA, ticker, "snapshot", snap)
        day = snap.get("ticker", {}).get("day", {})
        results = detail.get("results", {})
        return {
            "ticker": ticker,
            "price": day.get("c"),
            "volume": day.get("v"),
            "market_cap": results.get("market_cap"),
            "name": results.get("name"),
            "sector": results.get("sic_description"),
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


@mcp.tool()
def screen_stocks(criteria: dict) -> list[dict]:
    """
    Stage-A quantitative screener.
    criteria keys: min_market_cap (int), min_volume (int), max_results (int)
    """
    try:
        from agents.screener import GLOBAL_UNIVERSE
        raw_tickers = [{"ticker": t} for t, _, _ in GLOBAL_UNIVERSE]
        min_cap = criteria.get("min_market_cap", 500_000_000)
        min_vol = criteria.get("min_volume", 500_000)
        max_res = criteria.get("max_results", 60)

        candidates = []
        for t in raw_tickers:
            ticker = t.get("ticker")
            if not ticker:
                continue
            try:
                metrics = get_stock_metrics(ticker)
                cap = metrics.get("market_cap") or 0
                vol = metrics.get("volume") or 0
                price = metrics.get("price") or 0
                if cap >= min_cap and vol >= min_vol and price >= 5:
                    candidates.append({**metrics, "ticker": ticker})
                if len(candidates) >= max_res:
                    break
            except Exception:
                continue
        return candidates
    except Exception as e:
        return []


@mcp.tool()
def get_vix() -> dict:
    """
    Current VIX level from yfinance (^VIX).
    Interpretation: below 15 = complacent, 15-25 = normal,
    above 30 = fear, above 40 = panic.
    """
    try:
        import yfinance as yf
        t = yf.Ticker("^VIX")
        hist = t.history(period="5d")
        if hist.empty:
            return {"vix": None, "error": "no data"}
        latest = float(hist["Close"].iloc[-1])
        prev   = float(hist["Close"].iloc[-2]) if len(hist) > 1 else latest

        if latest < 15:
            label = "complacent"
        elif latest < 25:
            label = "normal"
        elif latest < 30:
            label = "elevated"
        elif latest < 40:
            label = "fear"
        else:
            label = "panic"

        return {
            "vix": round(latest, 2),
            "prev_close": round(prev, 2),
            "change": round(latest - prev, 2),
            "label": label,
            "source": "yfinance",
        }
    except Exception as e:
        return {"vix": None, "error": str(e)}


@mcp.tool()
def get_put_call_ratio(ticker: str = "SPY") -> dict:
    """
    Compute put/call ratio from live options chain via yfinance.
    Uses SPY as market proxy by default.
    Above 1.2 = fear, below 0.7 = greed.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        expiries = t.options
        if not expiries:
            return {"put_call_ratio": None, "error": "no options data"}

        # Use nearest expiry for most current sentiment
        chain = t.option_chain(expiries[0])

        call_vol = chain.calls["volume"].fillna(0).sum()
        put_vol  = chain.puts["volume"].fillna(0).sum()

        if call_vol == 0:
            return {"put_call_ratio": None, "error": "zero call volume"}

        ratio = round(float(put_vol) / float(call_vol), 3)

        if ratio > 1.2:
            label = "fear"
        elif ratio < 0.7:
            label = "greed"
        else:
            label = "neutral"

        return {
            "ticker": ticker,
            "put_call_ratio": ratio,
            "call_volume": int(call_vol),
            "put_volume": int(put_vol),
            "label": label,
            "expiry_used": expiries[0],
            "source": "yfinance",
        }
    except Exception as e:
        return {"put_call_ratio": None, "error": str(e)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
