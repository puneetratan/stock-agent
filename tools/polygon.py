"""Polygon.io REST client — thin wrapper used by market_mcp.py."""

import os
from datetime import date, timedelta
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://api.polygon.io"


def _key() -> str:
    return os.environ["POLYGON_API_KEY"]


def _get(path: str, params: dict | None = None) -> Any:
    params = params or {}
    params["apiKey"] = _key()
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_aggregates(ticker: str, days: int = 90) -> dict:
    """Daily OHLCV bars for the last `days` calendar days."""
    to_date = date.today()
    from_date = to_date - timedelta(days=days)
    return _get(
        f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}",
        {"adjusted": "true", "sort": "asc", "limit": 365},
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_ticker_details(ticker: str) -> dict:
    """Metadata: market cap, sector, description."""
    return _get(f"/v3/reference/tickers/{ticker}")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_snapshot(ticker: str) -> dict:
    """Real-time snapshot: last price, day range, prev close."""
    return _get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_options_contracts(ticker: str) -> dict:
    """Options chain summary for unusual-activity detection."""
    return _get(
        "/v3/reference/options/contracts",
        {"underlying_ticker": ticker, "limit": 250},
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def screen_tickers(params: dict) -> list[dict]:
    """Polygon Ticker Search endpoint — filter by market cap, type, market."""
    return _get("/v3/reference/tickers", params).get("results", [])
