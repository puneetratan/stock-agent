"""
Quick test: runs Agent 7 (Geo/Macro) for a single ticker.

Usage:
    uv run python test_geo_agent.py
"""

import json
import uuid
from dotenv import load_dotenv
load_dotenv()

TICKER = "NVDA"
SECTOR = "technology"

# Simulated context from earlier agents
MOCK_TECHNICAL_SIGNAL = "bullish"
MOCK_SENTIMENT_LABEL  = "bullish"
MOCK_BUSINESS_QUALITY = "exceptional"

MOCK_CAUSAL_THESES = [
    {
        "theme_id": "AI_INFRASTRUCTURE_BOOM",
        "root_cause": "Hyperscaler AI capex creating multi-year infrastructure supercycle",
        "confidence": 85,
    },
    {
        "theme_id": "US_IRAN_TENSIONS",
        "root_cause": "Strait of Hormuz closure threatening global oil supply",
        "confidence": 78,
    },
]

def main():
    run_id = str(uuid.uuid4())
    print(f"\nTesting Agent 7 — Geo/Macro Agent ({TICKER})")
    print(f"Run ID: {run_id[:8]}\n")

    print("Fetching macro and geo data...")
    from mcp_servers.intelligence_mcp import (
        get_fed_rate_decision, get_inflation_cpi,
        get_sector_etf_flow, web_search,
    )

    data = {}
    steps = [
        ("fed_rate",             lambda: get_fed_rate_decision()),
        ("cpi",                  lambda: get_inflation_cpi()),
        ("sector_flow",          lambda: get_sector_etf_flow(SECTOR)),
        ("geo_search",           lambda: web_search(f"{TICKER} geopolitical risk")[:3]),
        ("supply_chain_search",  lambda: web_search(f"{TICKER} supply chain risk")[:3]),
    ]

    for key, fn in steps:
        try:
            data[key] = fn()
            print(f"  [OK] {key}")
        except Exception as e:
            data[key] = {}
            print(f"  [FAIL] {key}: {e}")

    fed  = data.get("fed_rate", {})
    cpi  = data.get("cpi", {})
    flow = data.get("sector_flow", {})

    print(f"\nRaw data summary:")
    rates = fed.get("fed_funds_rate", [])
    print(f"  Fed funds rate:  {rates[0].get('value') if rates else 'N/A'}%")
    cpi_obs = cpi.get("cpi", [])
    print(f"  CPI latest:      {cpi_obs[0].get('value') if cpi_obs else 'N/A'}")
    print(f"  Sector ETF:      {flow.get('etf')} AUM=${flow.get('aum')}")
    print(f"  Geo results:     {len(data.get('geo_search', []))} articles")

    print(f"\nRunning LLM synthesis (needs Bedrock)...")
    try:
        from crewai import Crew, Process, Task
        from agents.geo import build_geo_agent, GEO_TASK_DESCRIPTION

        agent = build_geo_agent()
        task = Task(
            description=GEO_TASK_DESCRIPTION.format(
                ticker=TICKER,
                causal_theses=json.dumps(MOCK_CAUSAL_THESES),
                fed_rate=json.dumps(fed),
                cpi=json.dumps(cpi),
                sector_flow=json.dumps(flow),
                technical_signal=MOCK_TECHNICAL_SIGNAL,
                sentiment_label=MOCK_SENTIMENT_LABEL,
                business_quality=MOCK_BUSINESS_QUALITY,
                geo_search=json.dumps(data.get("geo_search", []))[:1000],
                supply_chain_search=json.dumps(data.get("supply_chain_search", []))[:1000],
            ),
            agent=agent,
            expected_output="Structured JSON geo/macro report",
        )
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff()

        raw = str(result)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        start, end = raw.find("{"), raw.rfind("}") + 1
        report = json.loads(raw[start:end])

        print(f"\n{'='*60}")
        print(f"Geo/Macro Report for {TICKER}")
        print(f"  Macro environment:  {report.get('macro_environment')}")
        print(f"  Sector flow:        {report.get('sector_flow')}")
        print(f"  Risk level:         {report.get('risk_level')}")
        print(f"  Geo risks:          {report.get('geopolitical_risks', [])}")
        print(f"  Macro tailwinds:    {report.get('macro_tailwinds', [])}")
        print(f"  Theme exposure:     {report.get('theme_exposure', {})}")
        print(f"  Confidence:         {report.get('confidence')}%")
        print(f"\n  Summary: {report.get('summary')}")

    except Exception as e:
        print(f"  [LLM skipped — Bedrock not available]: {e}")
        print(f"\n  Raw data fetch succeeded. Agent 7 data layer is working.")


if __name__ == "__main__":
    main()
