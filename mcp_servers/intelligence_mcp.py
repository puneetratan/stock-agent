"""
MCP server: intelligence_mcp — wraps NewsAPI, SEC EDGAR, FRED, and web search.

Each tool: (1) calls external API, (2) saves raw data to MongoDB, (3) returns processed data.
"""

import os
from datetime import datetime, timezone

import requests
from mcp.server.fastmcp import FastMCP

from db import get_collection
from db.collections import Collections
from tools import edgar as edgar_client
from tools import fred as fred_client
from tools import news_api

mcp = FastMCP("intelligence_mcp")

FMP_BASE = "https://financialmodelingprep.com/api/v3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmp_get(path: str, params: dict | None = None) -> dict | list:
    """Financial Modeling Prep API — free tier has broad fundamental data."""
    params = params or {}
    params["apikey"] = os.environ.get("FMP_API_KEY", "demo")
    resp = requests.get(f"{FMP_BASE}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _save(collection: str, ticker: str, endpoint: str, raw) -> None:
    get_collection(collection).insert_one(
        {"ticker": ticker, "endpoint": endpoint, "raw": raw, "saved_at": _now()}
    )


# ---------------------------------------------------------------------------
# News & Sentiment Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_news(query: str, days: int = 3) -> list[dict]:
    """Search news articles for a query over the last `days` days."""
    try:
        articles = news_api.search_everything(query, days)
        ticker_guess = query.upper().split()[0]
        _save(Collections.NEWS_SENTIMENT, ticker_guess, "news_search", articles)
        return [
            {
                "title": a.get("title"),
                "source": a.get("source", {}).get("name"),
                "published_at": a.get("publishedAt"),
                "url": a.get("url"),
                "description": a.get("description"),
            }
            for a in articles
        ]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
def get_analyst_ratings(ticker: str) -> dict:
    """Latest analyst consensus ratings and price targets from FMP."""
    try:
        raw = _fmp_get(f"/analyst-stock-recommendations/{ticker}", {"limit": 30})
        _save(Collections.NEWS_SENTIMENT, ticker, "analyst_ratings", raw)

        if not raw:
            return {"ticker": ticker, "consensus": "unknown"}

        buy = sum(1 for r in raw if r.get("analystRatingsStrongBuy", 0) + r.get("analystRatingsBuy", 0) > 0)
        sell = sum(1 for r in raw if r.get("analystRatingsStrongSell", 0) + r.get("analystRatingsSell", 0) > 0)
        hold = sum(1 for r in raw if r.get("analystRatingsHold", 0) > 0)

        if buy > sell + hold:
            consensus = "strong_buy"
        elif buy > sell:
            consensus = "buy"
        elif sell > buy:
            consensus = "sell"
        else:
            consensus = "hold"

        return {
            "ticker": ticker,
            "consensus": consensus,
            "buy_count": buy,
            "hold_count": hold,
            "sell_count": sell,
            "latest_rating": raw[0] if raw else {},
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


@mcp.tool()
def get_reddit_sentiment(query: str) -> dict:
    """
    Approximate Reddit sentiment via Pushshift-style count heuristic.
    In production: replace with proper Reddit API or third-party sentiment service.
    """
    try:
        articles = news_api.search_everything(f"site:reddit.com {query}", days=7)
        count = len(articles)
        sentiment = "high" if count > 10 else ("medium" if count > 3 else "low")
        return {"query": query, "mention_count": count, "buzz_level": sentiment}
    except Exception as e:
        return {"query": query, "error": str(e)}


@mcp.tool()
def get_earnings_call_summary(ticker: str) -> str:
    """Fetch most recent earnings call transcript summary from FMP."""
    try:
        raw = _fmp_get(f"/earning_call_transcript/{ticker}", {"quarter": 1, "year": 2024})
        if not raw:
            return f"No earnings call transcript found for {ticker}"
        content = raw[0].get("content", "") if isinstance(raw, list) else str(raw)
        _save(Collections.NEWS_SENTIMENT, ticker, "earnings_transcript", {"ticker": ticker, "content": content[:2000]})
        # Return first 1500 chars as summary context
        return content[:1500]
    except Exception as e:
        return f"Error fetching earnings call for {ticker}: {e}"


# ---------------------------------------------------------------------------
# Fundamental Data Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_income_statement(ticker: str, quarters: int = 8) -> dict:
    """Quarterly income statements: revenue, gross profit, net income."""
    try:
        raw = _fmp_get(f"/income-statement/{ticker}", {"period": "quarter", "limit": quarters})
        _save(Collections.FUNDAMENTALS, ticker, "income_statement", raw)
        if not raw:
            return {"ticker": ticker, "statements": []}
        return {
            "ticker": ticker,
            "statements": [
                {
                    "date": s.get("date"),
                    "revenue": s.get("revenue"),
                    "gross_profit": s.get("grossProfit"),
                    "net_income": s.get("netIncome"),
                    "eps": s.get("eps"),
                    "gross_margin": round(s.get("grossProfitRatio", 0) * 100, 1),
                    "net_margin": round(s.get("netIncomeRatio", 0) * 100, 1),
                }
                for s in raw[:quarters]
            ],
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


@mcp.tool()
def get_balance_sheet(ticker: str) -> dict:
    """Latest balance sheet: assets, liabilities, cash, debt."""
    try:
        raw = _fmp_get(f"/balance-sheet-statement/{ticker}", {"period": "annual", "limit": 2})
        _save(Collections.FUNDAMENTALS, ticker, "balance_sheet", raw)
        if not raw:
            return {"ticker": ticker, "balance_sheet": {}}
        latest = raw[0]
        return {
            "ticker": ticker,
            "date": latest.get("date"),
            "total_assets": latest.get("totalAssets"),
            "total_liabilities": latest.get("totalLiabilities"),
            "cash": latest.get("cashAndCashEquivalents"),
            "total_debt": latest.get("totalDebt"),
            "shareholders_equity": latest.get("totalStockholdersEquity"),
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


@mcp.tool()
def get_cash_flow(ticker: str) -> dict:
    """Operating, investing, and free cash flow for last 4 quarters."""
    try:
        raw = _fmp_get(f"/cash-flow-statement/{ticker}", {"period": "quarter", "limit": 4})
        _save(Collections.FUNDAMENTALS, ticker, "cash_flow", raw)
        if not raw:
            return {"ticker": ticker, "cash_flows": []}
        return {
            "ticker": ticker,
            "cash_flows": [
                {
                    "date": s.get("date"),
                    "operating_cf": s.get("operatingCashFlow"),
                    "capex": s.get("capitalExpenditure"),
                    "free_cf": s.get("freeCashFlow"),
                }
                for s in raw
            ],
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


@mcp.tool()
def get_sec_filing(ticker: str, form: str = "10-Q") -> str:
    """Retrieve the most recent SEC filing text excerpt."""
    try:
        cik = edgar_client.get_cik(ticker)
        if not cik:
            return f"CIK not found for {ticker}"
        filings = edgar_client.get_recent_filings(cik, form)
        if not filings:
            return f"No {form} filings found for {ticker}"
        latest = filings[0]
        _save(Collections.FUNDAMENTALS, ticker, "sec_filing_meta", latest)
        return f"{form} filing for {ticker}: filed {latest['date']}, accession {latest['accession']}"
    except Exception as e:
        return f"Error fetching SEC filing for {ticker}: {e}"


@mcp.tool()
def get_insider_trades(ticker: str, days: int = 90) -> list[dict]:
    """Recent insider buy/sell transactions from SEC Form 4."""
    try:
        raw = _fmp_get(f"/insider-trading", {"symbol": ticker, "limit": 20})
        _save(Collections.FUNDAMENTALS, ticker, "insider_trades", raw)
        if not raw:
            return []
        return [
            {
                "name": t.get("reportingName"),
                "title": t.get("typeOfOwner"),
                "transaction": t.get("transactionType"),
                "shares": t.get("securitiesTransacted"),
                "price": t.get("price"),
                "date": t.get("transactionDate"),
            }
            for t in raw[:10]
        ]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
def get_pe_ratio(ticker: str) -> dict:
    """Current P/E ratio and related valuation metrics."""
    try:
        raw = _fmp_get(f"/ratios-ttm/{ticker}")
        _save(Collections.FUNDAMENTALS, ticker, "ratios_ttm", raw)
        if not raw:
            return {"ticker": ticker, "pe_ratio": None}
        r = raw[0] if isinstance(raw, list) else raw
        return {
            "ticker": ticker,
            "pe_ratio": r.get("peRatioTTM"),
            "forward_pe": r.get("priceEarningsRatioTTM"),
            "peg_ratio": r.get("pegRatioTTM"),
            "price_to_book": r.get("priceToBookRatioTTM"),
            "ev_to_ebitda": r.get("enterpriseValueMultipleTTM"),
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


# ---------------------------------------------------------------------------
# Macro & Geo Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_fed_rate_decision() -> dict:
    """Latest Fed Funds rate from FRED."""
    try:
        return fred_client.get_fed_funds_rate()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_inflation_cpi() -> dict:
    """CPI and core CPI from FRED."""
    try:
        return fred_client.get_inflation_data()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_sector_etf_flow(sector: str) -> dict:
    """
    Proxy ETF flow for a sector using FMP ETF holder data.
    Sector string examples: "technology", "energy", "financials".
    """
    SECTOR_ETFS = {
        "technology": "XLK",
        "energy": "XLE",
        "financials": "XLF",
        "healthcare": "XLV",
        "consumer": "XLY",
        "materials": "XLB",
        "industrials": "XLI",
        "utilities": "XLU",
        "real_estate": "XLRE",
    }
    etf = SECTOR_ETFS.get(sector.lower(), "SPY")
    try:
        raw = _fmp_get(f"/etf-info/{etf}")
        _save(Collections.GEO_MACRO, etf, "etf_info", raw)
        if not raw:
            return {"sector": sector, "etf": etf, "flow": "unknown"}
        info = raw[0] if isinstance(raw, list) else raw
        return {
            "sector": sector,
            "etf": etf,
            "aum": info.get("aum"),
            "avg_volume": info.get("avgVolume"),
            "description": info.get("description", "")[:200],
        }
    except Exception as e:
        return {"sector": sector, "etf": etf, "error": str(e)}


@mcp.tool()
def web_search(query: str) -> list[dict]:
    """Search web via NewsAPI as a proxy for general web search results."""
    try:
        articles = news_api.search_everything(query, days=7)
        return [
            {
                "title": a.get("title"),
                "source": a.get("source", {}).get("name"),
                "url": a.get("url"),
                "published_at": a.get("publishedAt"),
                "snippet": a.get("description", "")[:300],
            }
            for a in articles[:10]
        ]
    except Exception as e:
        return [{"error": str(e)}]


if __name__ == "__main__":
    mcp.run(transport="stdio")
