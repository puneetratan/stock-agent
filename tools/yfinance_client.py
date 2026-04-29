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


def get_options_contracts(ticker: str) -> dict:
    """Options chain summary — matches Polygon's options shape."""
    try:
        t = yf.Ticker(ticker)
        expiries = t.options
        if not expiries:
            return {"results": []}
        # Use nearest expiry
        chain = t.option_chain(expiries[0])
        calls = [{"contract_type": "call", "strike": row["strike"], "volume": row.get("volume", 0)}
                 for _, row in chain.calls.iterrows()]
        puts = [{"contract_type": "put", "strike": row["strike"], "volume": row.get("volume", 0)}
                for _, row in chain.puts.iterrows()]
        return {"results": calls + puts}
    except Exception:
        return {"results": []}


def get_close_on_date(ticker: str, target_date: str) -> float | None:
    """
    Returns closing price on or near target_date (YYYY-MM-DD).
    Looks back up to 5 days for weekends/holidays.
    Used by signal_verification_job.
    """
    from datetime import datetime, timedelta
    try:
        t = yf.Ticker(ticker)
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        # Fetch a window around the target date
        start = (dt - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        hist = t.history(start=start, end=end)
        if hist.empty:
            return None
        # Return the closest date at or before target
        hist.index = hist.index.tz_localize(None) if hist.index.tzinfo else hist.index
        hist = hist[hist.index <= dt]
        if hist.empty:
            return None
        return float(hist.iloc[-1]["Close"])
    except Exception:
        return None
