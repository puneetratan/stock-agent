"""
CrewAI Crew definition — wires Market, News, Fundamentals, and Geo agents
for deep per-stock analysis.

Usage:
    crew = build_analysis_crew(ticker="NVDA", theses=[...], run_id="...")
    result = crew.kickoff()
"""

import json
from typing import Any

from crewai import Agent, Crew, Process, Task

from agents.fundamentals import FUNDAMENTALS_TASK_DESCRIPTION, build_fundamentals_agent
from agents.geo import GEO_TASK_DESCRIPTION, build_geo_agent
from agents.market import MARKET_TASK_DESCRIPTION, build_market_agent
from agents.news import NEWS_TASK_DESCRIPTION, build_news_agent
from db import get_collection
from db.collections import Collections


def _prefetch_market_data(ticker: str) -> dict:
    """Pre-fetch all market data before building the crew (avoids MCP calls in tasks)."""
    data = {}
    try:
        from mcp_servers.market_mcp import (
            get_52w_range, get_macd, get_options_flow, get_price_history,
            get_rsi, get_volume_profile,
        )
        data["price_history"] = get_price_history(ticker, days=90)
        data["rsi"] = get_rsi(ticker)
        data["macd"] = get_macd(ticker)
        data["volume_profile"] = get_volume_profile(ticker)
        data["options_flow"] = get_options_flow(ticker)
        data["range_52w"] = get_52w_range(ticker)
    except Exception as e:
        data["error"] = str(e)
    return data


def _prefetch_news_data(ticker: str) -> dict:
    data = {}
    try:
        from mcp_servers.intelligence_mcp import (
            get_analyst_ratings, get_earnings_call_summary,
            get_reddit_sentiment, search_news,
        )
        data["headlines"] = search_news(ticker, days=7)
        data["analyst_ratings"] = get_analyst_ratings(ticker)
        data["social_sentiment"] = get_reddit_sentiment(ticker)
        data["earnings_summary"] = get_earnings_call_summary(ticker)
    except Exception as e:
        data["error"] = str(e)
    return data


def _prefetch_fundamentals_data(ticker: str) -> dict:
    data = {}
    try:
        from mcp_servers.intelligence_mcp import (
            get_balance_sheet, get_cash_flow, get_income_statement,
            get_insider_trades, get_pe_ratio, get_sec_filing,
        )
        data["income_statements"] = get_income_statement(ticker, quarters=8)
        data["balance_sheet"] = get_balance_sheet(ticker)
        data["cash_flow"] = get_cash_flow(ticker)
        data["pe_ratio"] = get_pe_ratio(ticker)
        data["insider_trades"] = get_insider_trades(ticker, days=90)
        data["sec_filing"] = get_sec_filing(ticker, form="10-Q")
    except Exception as e:
        data["error"] = str(e)
    return data


def _prefetch_geo_data(ticker: str, sector: str) -> dict:
    data = {}
    try:
        from mcp_servers.intelligence_mcp import (
            get_fed_rate_decision, get_inflation_cpi,
            get_sector_etf_flow, web_search,
        )
        data["fed_rate"] = get_fed_rate_decision()
        data["cpi"] = get_inflation_cpi()
        data["sector_flow"] = get_sector_etf_flow(sector)
        data["geo_search"] = web_search(f"{ticker} geopolitical risk")[:3]
        data["supply_chain_search"] = web_search(f"{ticker} supply chain risk")[:3]
    except Exception as e:
        data["error"] = str(e)
    return data


def build_analysis_crew(ticker: str, theses: list[dict], run_id: str) -> Crew:
    """
    Builds a sequential 4-agent crew for deep stock analysis.

    Order:
      1. Market Agent    — technical analysis
      2. News Agent      — sentiment analysis
      3. Fundamentals    — financials (uses news context)
      4. Geo Agent       — macro risk (uses all context)

    All external data is pre-fetched before the crew runs to keep
    tasks fast and deterministic.
    """
    # Pre-fetch all data upfront
    market_data = _prefetch_market_data(ticker)
    news_data = _prefetch_news_data(ticker)

    # Determine sector for geo ETF flow query
    sector = "technology"  # default; enriched from screener results if available
    try:
        col = get_collection(Collections.SCREENER_RESULTS)
        rec = col.find_one({"ticker": ticker, "run_id": run_id})
        if rec and rec.get("sector"):
            sector = rec["sector"].lower().split()[0]
    except Exception:
        pass

    funds_data = _prefetch_fundamentals_data(ticker)
    geo_data = _prefetch_geo_data(ticker, sector)
    causal_theses_json = json.dumps(theses[:3], indent=2)[:4000]

    # Build agents
    market_agent = build_market_agent()
    news_agent = build_news_agent()
    fundamentals_agent = build_fundamentals_agent()
    geo_agent = build_geo_agent()

    # Define tasks with pre-fetched data embedded
    market_task = Task(
        description=MARKET_TASK_DESCRIPTION.format(
            ticker=ticker,
            price_history=json.dumps(market_data.get("price_history", {}))[:2000],
            rsi=market_data.get("rsi", {}),
            macd=market_data.get("macd", {}),
            volume_profile=market_data.get("volume_profile", {}),
            options_flow=market_data.get("options_flow", {}),
            range_52w=market_data.get("range_52w", {}),
        ),
        agent=market_agent,
        expected_output="Structured JSON market report",
    )

    news_task = Task(
        description=NEWS_TASK_DESCRIPTION.format(
            ticker=ticker,
            headlines=json.dumps(news_data.get("headlines", []))[:3000],
            analyst_ratings=json.dumps(news_data.get("analyst_ratings", {})),
            social_sentiment=json.dumps(news_data.get("social_sentiment", {})),
            earnings_summary=str(news_data.get("earnings_summary", ""))[:1500],
        ),
        agent=news_agent,
        expected_output="Structured JSON news/sentiment report",
    )

    fundamentals_task = Task(
        description=FUNDAMENTALS_TASK_DESCRIPTION.format(
            ticker=ticker,
            news_report="{news_task_output}",  # CrewAI injects previous task output
            income_statements=json.dumps(funds_data.get("income_statements", {}))[:3000],
            balance_sheet=json.dumps(funds_data.get("balance_sheet", {})),
            cash_flow=json.dumps(funds_data.get("cash_flow", {})),
            pe_ratio=json.dumps(funds_data.get("pe_ratio", {})),
            insider_trades=json.dumps(funds_data.get("insider_trades", []))[:1500],
            sec_filing=str(funds_data.get("sec_filing", ""))[:1000],
        ),
        agent=fundamentals_agent,
        context=[news_task],           # runs after news task
        expected_output="Structured JSON fundamentals report",
    )

    geo_task = Task(
        description=GEO_TASK_DESCRIPTION.format(
            ticker=ticker,
            causal_theses=causal_theses_json,
            fed_rate=json.dumps(geo_data.get("fed_rate", {})),
            cpi=json.dumps(geo_data.get("cpi", {})),
            sector_flow=json.dumps(geo_data.get("sector_flow", {})),
            technical_signal="{market_task_output}",
            sentiment_label="{news_task_output}",
            business_quality="{fundamentals_task_output}",
            geo_search=json.dumps(geo_data.get("geo_search", [])),
            supply_chain_search=json.dumps(geo_data.get("supply_chain_search", [])),
        ),
        agent=geo_agent,
        context=[market_task, news_task, fundamentals_task],  # runs last
        expected_output="Structured JSON geo/macro report",
    )

    return Crew(
        agents=[market_agent, news_agent, fundamentals_agent, geo_agent],
        tasks=[market_task, news_task, fundamentals_task, geo_task],
        process=Process.sequential,
        verbose=True,
    )


def parse_crew_outputs(crew_result: Any, ticker: str, run_id: str) -> dict:
    """
    Extract and parse JSON reports from each task's output.
    Returns dict with keys: market, news, fundamentals, geo.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    reports = {}

    tasks_output = getattr(crew_result, "tasks_output", [])
    names = ["market", "news", "fundamentals", "geo"]

    for i, name in enumerate(names):
        if i >= len(tasks_output):
            break
        raw = str(tasks_output[i])
        try:
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            report = json.loads(raw[start:end])
            report["ticker"] = ticker
            report["run_id"] = run_id
            report["generated_at"] = now
            reports[name] = report
        except Exception as e:
            print(f"[crew] Failed to parse {name} report for {ticker}: {e}")
            reports[name] = {"ticker": ticker, "run_id": run_id, "error": str(e)}

    return reports
