"""yfinance wrapper — provides price/volume/fundamentals for international tickers.

Used as the data backend for non-US stocks where Polygon's US-only endpoints
don't apply. Mirrors the interface of polygon.py so screener.py can call either.
"""

from __future__ import annotations

import yfinance as yf


def get_snapshot(ticker: str) -> dict:
    """Return price + volume snapshot matching Polygon's snapshot shape."""
    t = yf.Ticker(ticker)
    info = t.fast_info
    hist = t.history(period="2d")

    if hist.empty:
        return {}

    last = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) > 1 else last

    return {
        "ticker": {
            "day": {
                "c": float(last.get("Close", 0)),
                "v": float(last.get("Volume", 0)),
                "o": float(last.get("Open", 0)),
                "h": float(last.get("High", 0)),
                "l": float(last.get("Low", 0)),
            },
            "prevDay": {"c": float(prev.get("Close", 0))},
        }
    }


def get_ticker_details(ticker: str) -> dict:
    """Return metadata matching Polygon's ticker details shape."""
    t = yf.Ticker(ticker)
    info = t.info or {}

    return {
        "results": {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName", ticker),
            "market_cap": info.get("marketCap", 0) or 0,
            "sic_description": info.get("sector", "Unknown"),
            "description": info.get("longBusinessSummary", ""),
            "country": info.get("country", ""),
            "currency": info.get("currency", "USD"),
            "exchange": info.get("exchange", ""),
        }
    }


def get_aggregates(ticker: str, days: int = 90) -> dict:
    """Daily OHLCV bars — matches Polygon's aggregates shape."""
    t = yf.Ticker(ticker)
    hist = t.history(period=f"{days}d")

    if hist.empty:
        return {"results": []}

    results = []
    for ts, row in hist.iterrows():
        results.append({
            "t": int(ts.timestamp() * 1000),
            "o": float(row["Open"]),
            "h": float(row["High"]),
            "l": float(row["Low"]),
            "c": float(row["Close"]),
            "v": float(row["Volume"]),
        })

    return {"results": results}
