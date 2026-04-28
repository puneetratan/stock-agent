"""
Quick test: runs Agent 4 (Market) for a single ticker.
No LLM needed for data fetch — only for the final synthesis task.

Usage:
    uv run python test_market_agent.py
"""

import json
import uuid
from dotenv import load_dotenv
load_dotenv()

TICKER = "NVDA"  # change this to test a different stock

def main():
    run_id = str(uuid.uuid4())
    print(f"\nTesting Agent 4 — Market Agent ({TICKER})")
    print(f"Run ID: {run_id[:8]}\n")

    # Pre-fetch all market data (same as crew.py does)
    print("Fetching market data from Polygon.io...")
    from mcp_servers.market_mcp import (
        get_price_history, get_rsi, get_macd,
        get_volume_profile, get_options_flow, get_52w_range,
    )

    data = {}
    steps = [
        ("price_history",  lambda: get_price_history(TICKER, days=90)),
        ("rsi",            lambda: get_rsi(TICKER)),
        ("macd",           lambda: get_macd(TICKER)),
        ("volume_profile", lambda: get_volume_profile(TICKER)),
        ("options_flow",   lambda: get_options_flow(TICKER)),
        ("range_52w",      lambda: get_52w_range(TICKER)),
    ]

    for key, fn in steps:
        try:
            data[key] = fn()
            print(f"  [OK] {key}")
        except Exception as e:
            data[key] = {}
            print(f"  [FAIL] {key}: {e}")

    print(f"\nRaw data summary:")
    print(f"  RSI:          {data.get('rsi', {}).get('rsi')}")
    print(f"  MACD signal:  {data.get('macd', {}).get('signal')}")
    print(f"  Volume trend: {data.get('volume_profile', {}).get('trend')}")
    print(f"  52w position: {data.get('range_52w', {}).get('pct_above_52w_low')}% above 52w low")
    print(f"  Options flow: {data.get('options_flow', {}).get('sentiment')}")

    # Now run the LLM synthesis via CrewAI
    print(f"\nRunning LLM synthesis (needs Bedrock)...")
    try:
        from crewai import Crew, Process
        from agents.market import build_market_agent, MARKET_TASK_DESCRIPTION
        from crewai import Task

        agent = build_market_agent()
        task = Task(
            description=MARKET_TASK_DESCRIPTION.format(
                ticker=TICKER,
                price_history=json.dumps(data.get("price_history", {}))[:1000],
                rsi=data.get("rsi", {}),
                macd=data.get("macd", {}),
                volume_profile=data.get("volume_profile", {}),
                options_flow=data.get("options_flow", {}),
                range_52w=data.get("range_52w", {}),
            ),
            agent=agent,
            expected_output="Structured JSON market report",
        )
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff()

        raw = str(result)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        start, end = raw.find("{"), raw.rfind("}") + 1
        report = json.loads(raw[start:end])

        print(f"\n{'='*60}")
        print(f"Market Report for {TICKER}")
        print(f"  Signal:       {report.get('technical_signal')}")
        print(f"  RSI:          {report.get('rsi')}")
        print(f"  MACD:         {report.get('macd')}")
        print(f"  Volume trend: {report.get('volume_trend')}")
        print(f"  Options flow: {report.get('options_flow')}")
        print(f"  Support:      {report.get('support_level')}")
        print(f"  Resistance:   {report.get('resistance_level')}")
        print(f"  Confidence:   {report.get('confidence')}%")
        print(f"\n  Summary: {report.get('summary')}")

    except Exception as e:
        print(f"  [LLM skipped — Bedrock not available]: {e}")
        print(f"\n  Raw data fetch succeeded. Agent 4 data layer is working.")


if __name__ == "__main__":
    main()
