"""NewsAPI client — used by intelligence_mcp.py."""

import os
from datetime import date, timedelta

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://newsapi.org/v2"


def _key() -> str:
    return os.environ["NEWS_API_KEY"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def search_everything(query: str, days: int = 3) -> list[dict]:
    """Full-text news search across all indexed sources."""
    from_date = (date.today() - timedelta(days=days)).isoformat()
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "relevancy",
        "language": "en",
        "pageSize": 20,
        "apiKey": _key(),
    }
    resp = requests.get(f"{BASE_URL}/everything", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("articles", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_top_headlines(category: str = "business") -> list[dict]:
    """Top business/financial headlines right now."""
    params = {
        "category": category,
        "country": "us",
        "pageSize": 20,
        "apiKey": _key(),
    }
    resp = requests.get(f"{BASE_URL}/top-headlines", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("articles", [])
