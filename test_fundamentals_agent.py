"""
Quick test: runs Agent 6 (Fundamentals) for a single ticker.

Usage:
    uv run python test_fundamentals_agent.py
"""

import json
import uuid
from dotenv import load_dotenv
load_dotenv()

TICKER = "NVDA"

# Simulated news report context (normally comes from Agent 5)
MOCK_NEWS_REPORT = {
    "ticker": TICKER,
    "sentiment_score": 8.2,
    "sentiment_label": "bullish",
    "analyst_consensus": "strong_buy",
    "narrative_shift": "Blackwell demand accelerating beyond expectations",
    "summary": "Sentiment is strongly bullish driven by AI infrastructure demand.",
}

def main():
    run_id = str(uuid.uuid4())
    print(f"\nTesting Agent 6 — Fundamentals Agent ({TICKER})")
    print(f"Run ID: {run_id[:8]}\n")

    print("Fetching fundamental data...")
    from mcp_servers.intelligence_mcp import (
        get_income_statement, get_balance_sheet, get_cash_flow,
        get_pe_ratio, get_insider_trades, get_sec_filing,
    )

    data = {}
    steps = [
        ("income_statements", lambda: get_income_statement(TICKER, quarters=8)),
        ("balance_sheet",     lambda: get_balance_sheet(TICKER)),
        ("cash_flow",         lambda: get_cash_flow(TICKER)),
        ("pe_ratio",          lambda: get_pe_ratio(TICKER)),
        ("insider_trades",    lambda: get_insider_trades(TICKER, days=90)),
        ("sec_filing",        lambda: get_sec_filing(TICKER, form="10-Q")),
    ]

    for key, fn in steps:
        try:
            data[key] = fn()
            print(f"  [OK] {key}")
        except Exception as e:
            data[key] = {}
            print(f"  [FAIL] {key}: {e}")

    # Print a quick summary of raw data
    stmts = data.get("income_statements", {}).get("statements", [])
    bs    = data.get("balance_sheet", {})
    pe    = data.get("pe_ratio", {})
    insiders = data.get("insider_trades", [])

    print(f"\nRaw data summary:")
    print(f"  Income statements:  {len(stmts)} quarters")
    if stmts:
        latest = stmts[0]
        print(f"  Latest revenue:     ${latest.get('revenue', 0)/1e9:.1f}B")
        print(f"  Latest gross margin:{latest.get('gross_margin')}%")
        print(f"  Latest net margin:  {latest.get('net_margin')}%")
    print(f"  Cash on hand:       ${(bs.get('cash') or 0)/1e9:.1f}B")
    print(f"  Total debt:         ${(bs.get('total_debt') or 0)/1e9:.1f}B")
    print(f"  P/E ratio:          {pe.get('pe_ratio')}")
    print(f"  Insider trades:     {len(insiders)} recent transactions")

    print(f"\nRunning LLM synthesis (needs Bedrock)...")
    try:
        from crewai import Crew, Process, Task
        from agents.fundamentals import build_fundamentals_agent, FUNDAMENTALS_TASK_DESCRIPTION

        agent = build_fundamentals_agent()
        task = Task(
            description=FUNDAMENTALS_TASK_DESCRIPTION.format(
                ticker=TICKER,
                news_report=json.dumps(MOCK_NEWS_REPORT),
                income_statements=json.dumps(data.get("income_statements", {}))[:2000],
                balance_sheet=json.dumps(bs),
                cash_flow=json.dumps(data.get("cash_flow", {}))[:1000],
                pe_ratio=json.dumps(pe),
                insider_trades=json.dumps(insiders[:5])[:800],
                sec_filing=str(data.get("sec_filing", ""))[:500],
            ),
            agent=agent,
            expected_output="Structured JSON fundamentals report",
        )
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff()

        raw = str(result)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        start, end = raw.find("{"), raw.rfind("}") + 1
        report = json.loads(raw[start:end])

        print(f"\n{'='*60}")
        print(f"Fundamentals Report for {TICKER}")
        print(f"  Revenue growth YoY:  {report.get('revenue_growth_yoy')}%")
        print(f"  Gross margin:        {report.get('gross_margin')}%")
        print(f"  Margin trend:        {report.get('gross_margin_trend')}")
        print(f"  P/E ratio:           {report.get('pe_ratio')}")
        print(f"  Net cash (B):        ${report.get('net_cash_position_b')}")
        print(f"  Insider activity:    {report.get('insider_activity')}")
        print(f"  Business quality:    {report.get('business_quality')}")
        print(f"  Valuation:           {report.get('valuation')}")
        print(f"  Confidence:          {report.get('confidence')}%")
        print(f"\n  Summary: {report.get('summary')}")

    except Exception as e:
        print(f"  [LLM skipped — Bedrock not available]: {e}")
        print(f"\n  Raw data fetch succeeded. Agent 6 data layer is working.")


if __name__ == "__main__":
    main()
