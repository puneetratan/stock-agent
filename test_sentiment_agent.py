"""
Test: Sentiment Agent (new) — market psychology analysis.

Checks fear/greed, Google Trends, and LLM sentiment synthesis.

Usage:
    uv run python test_sentiment_agent.py
"""

import json
from dotenv import load_dotenv
load_dotenv()


def main():
    print(f"\n{'='*60}")
    print(f"Test: Sentiment Agent (new)")
    print(f"{'='*60}\n")

    # ── Step 1: Test Google Trends directly ──────────────────────────────────
    print("Step 1: Google Trends data fetch")
    try:
        from tools.google_trends import get_trend_score
        import time

        for kw in ["AI stocks", "stock market crash", "recession"]:
            r = get_trend_score(kw)
            trend = r.get("trend", "?")
            score = r.get("current_score", 0)
            print(f"  [{score:>3}/100]  {trend:<10}  '{kw}'")
            time.sleep(0.5)
        print("  [OK] Google Trends")
    except Exception as e:
        print(f"  [FAIL] Google Trends: {e}")

    # ── Step 2: Test individual sentiment data sources ────────────────────────
    print("\nStep 2: Sentiment data sources")

    try:
        from mcp_servers.intelligence_mcp import get_reddit_sentiment
        r = get_reddit_sentiment("wallstreetbets")
        print(f"  [OK] Reddit WSB — sentiment: {r.get('sentiment') or r.get('overall_sentiment') or 'fetched'}")
    except Exception as e:
        print(f"  [FAIL] Reddit: {e}")

    try:
        from mcp_servers.intelligence_mcp import search_news
        headlines = search_news("stock market", days=2)
        print(f"  [OK] News — {len(headlines)} headlines fetched")
    except Exception as e:
        print(f"  [FAIL] News: {e}")

    try:
        from mcp_servers.market_mcp import get_options_flow
        # Put/call via options flow on SPY as market proxy
        r = get_options_flow("SPY")
        ratio = r.get("call_put_ratio", "?")
        sentiment = r.get("sentiment", "?")
        print(f"  [OK] Options flow (SPY) — call/put ratio: {ratio}, sentiment: {sentiment}")
    except Exception as e:
        print(f"  [FAIL] Options flow: {e}")

    # ── Step 3: Run the full Sentiment Agent ─────────────────────────────────
    print("\nStep 3: Sentiment Agent — LLM synthesis (Haiku)")
    try:
        from agents.sentiment import SentimentAgent

        agent = SentimentAgent()
        # save=False to avoid writing to DB during test
        report = agent.analyse(save=False)

        print(f"\n  {'='*50}")
        print(f"  Sentiment Report")
        print(f"  {'='*50}")
        print(f"  Market emotion  : {report.get('market_emotion', '?').upper()}")
        print(f"  Fear/greed score: {report.get('fear_greed_score', '?')} / 100")
        print(f"  VIX level       : {report.get('vix_level', 'N/A')}")
        print(f"  Put/call ratio  : {report.get('put_call_ratio', 'N/A')}")
        print(f"  Confidence      : {report.get('confidence', '?')}%")

        cycles = report.get("narrative_cycles", {})
        if cycles:
            print(f"\n  Narrative cycles:")
            for theme, phase in cycles.items():
                print(f"    {theme:<15}: {phase}")

        smart_dumb = report.get("smart_vs_dumb", {})
        if smart_dumb:
            print(f"\n  Smart money : {smart_dumb.get('institutional', '?')}")
            print(f"  Dumb money  : {smart_dumb.get('retail', '?')}")
            div = smart_dumb.get("divergence")
            if div:
                print(f"  Divergence  : {div}")

        contrarian = report.get("contrarian_signal")
        if contrarian:
            print(f"\n  Contrarian  : {contrarian}")

        print(f"\n  Summary: {report.get('summary', '')}")
        print(f"\n  ✅ Sentiment Agent — PASS")

    except Exception as e:
        import traceback
        print(f"  [FAIL] Sentiment Agent: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
