"""
Test: Market Agent data layer via yfinance (no Polygon).

Fetches price history, computes RSI/MACD/volume, then runs LLM synthesis.

Usage:
    uv run python test_market_yfinance.py
"""

import json
import uuid
from dotenv import load_dotenv
load_dotenv()

TICKER = "NVDA"

def main():
    print(f"\n{'='*60}")
    print(f"Test: Market Agent — yfinance data layer ({TICKER})")
    print(f"{'='*60}\n")

    # ── Step 1: Test raw yfinance functions ──────────────────────────────────
    print("Step 1: Raw yfinance fetch")
    import tools.yfinance_client as yfc

    snap = yfc.get_snapshot(TICKER)
    day  = snap.get("ticker", {}).get("day", {})
    price = day.get("c", 0)
    print(f"  Current price : ${price}")

    detail = yfc.get_ticker_details(TICKER)
    info   = detail.get("results", {})
    print(f"  Name          : {info.get('name')}")
    print(f"  Market cap    : ${info.get('market_cap', 0):,.0f}")
    print(f"  Sector        : {info.get('sic_description')}")

    agg = yfc.get_aggregates(TICKER, 90)
    bars = agg.get("results", [])
    print(f"  Price bars    : {len(bars)} days of OHLCV data")
    if bars:
        print(f"  Latest close  : ${bars[-1]['c']:.2f}")
        print(f"  90d ago close : ${bars[0]['c']:.2f}")

    opts = yfc.get_options_contracts(TICKER)
    contracts = opts.get("results", [])
    calls = sum(1 for c in contracts if c.get("contract_type") == "call")
    puts  = sum(1 for c in contracts if c.get("contract_type") == "put")
    print(f"  Options       : {calls} calls / {puts} puts")

    # ── Step 2: Test via market_mcp functions ────────────────────────────────
    print("\nStep 2: market_mcp tools (all now backed by yfinance)")
    from mcp_servers.market_mcp import (
        get_price_history, get_rsi, get_macd,
        get_volume_profile, get_options_flow, get_52w_range,
    )

    results = {}
    steps = [
        ("price_history",  lambda: get_price_history(TICKER, days=90)),
        ("rsi",            lambda: get_rsi(TICKER)),
        ("macd",           lambda: get_macd(TICKER)),
        ("volume_profile", lambda: get_volume_profile(TICKER)),
        ("options_flow",   lambda: get_options_flow(TICKER)),
        ("52w_range",      lambda: get_52w_range(TICKER)),
    ]
    for key, fn in steps:
        try:
            results[key] = fn()
            print(f"  [OK] {key}")
        except Exception as e:
            results[key] = {}
            print(f"  [FAIL] {key}: {e}")

    print(f"\n  RSI:          {results.get('rsi', {}).get('rsi')}")
    print(f"  MACD signal:  {results.get('macd', {}).get('signal')}")
    print(f"  Volume trend: {results.get('volume_profile', {}).get('trend')}")
    rng = results.get("52w_range", {})
    print(f"  52w position: {rng.get('pct_above_52w_low')}% above 52w low")
    print(f"  52w high:     ${rng.get('52w_high')}")
    print(f"  Options flow: {results.get('options_flow', {}).get('sentiment')}")

    # ── Step 3: LLM synthesis ────────────────────────────────────────────────
    print(f"\nStep 3: LLM synthesis (Haiku — minimal cost)")
    try:
        from crewai import Crew, Process, Task
        from agents.market import build_market_agent, MARKET_TASK_DESCRIPTION

        agent = build_market_agent()
        task = Task(
            description=MARKET_TASK_DESCRIPTION.format(
                ticker=TICKER,
                price_history=json.dumps(results.get("price_history", {}))[:1000],
                rsi=results.get("rsi", {}),
                macd=results.get("macd", {}),
                volume_profile=results.get("volume_profile", {}),
                options_flow=results.get("options_flow", {}),
                range_52w=results.get("52w_range", {}),
            ),
            agent=agent,
            expected_output="Structured JSON market report",
        )
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff()

        raw = str(result)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        start, end = raw.find("{"), raw.rfind("}") + 1
        report = json.loads(raw[start:end])

        print(f"\n  {'='*50}")
        print(f"  Market Report — {TICKER}")
        print(f"  {'='*50}")
        print(f"  Signal      : {report.get('technical_signal')}")
        print(f"  RSI         : {report.get('rsi')}")
        print(f"  MACD        : {report.get('macd')}")
        print(f"  Volume      : {report.get('volume_trend')}")
        print(f"  Confidence  : {report.get('confidence')}%")
        print(f"\n  Summary: {report.get('summary')}")
        print(f"\n  ✅ Market Agent (yfinance) — PASS")

    except Exception as e:
        print(f"  [LLM error]: {e}")


if __name__ == "__main__":
    main()
