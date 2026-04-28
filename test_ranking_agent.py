"""
Quick test: runs Agent 8 (Ranking) with hardcoded reports for 3 stocks.
Bypasses all earlier agents.

Usage:
    uv run python test_ranking_agent.py
"""

import uuid
from dotenv import load_dotenv
load_dotenv()

from db import get_collection
from db.collections import Collections

# Hardcoded deep analysis reports — what Agents 4-7 would normally produce
MOCK_REPORTS = {
    "market_reports": [
        {"ticker": "NVDA", "technical_signal": "bullish", "rsi": 58, "macd": "bullish_momentum",
         "volume_trend": "increasing", "summary": "Strong uptrend with healthy momentum.", "confidence": 82},
        {"ticker": "PANW",  "technical_signal": "bullish", "rsi": 52, "macd": "bullish_cross",
         "volume_trend": "neutral", "summary": "Breakout above resistance on volume.", "confidence": 74},
        {"ticker": "XOM",  "technical_signal": "neutral", "rsi": 48, "macd": "bearish_momentum",
         "volume_trend": "decreasing", "summary": "Consolidating near support.", "confidence": 58},
    ],
    "news_reports": [
        {"ticker": "NVDA", "sentiment_score": 9.1, "analyst_consensus": "strong_buy",
         "narrative_shift": "Blackwell demand far exceeding supply", "summary": "Extremely bullish sentiment.", "confidence": 88},
        {"ticker": "PANW",  "sentiment_score": 7.8, "analyst_consensus": "buy",
         "narrative_shift": "Platformisation thesis gaining traction", "summary": "Positive with improving narrative.", "confidence": 76},
        {"ticker": "XOM",  "sentiment_score": 6.2, "analyst_consensus": "hold",
         "narrative_shift": "Energy demand uncertain short term", "summary": "Mixed sentiment on oil outlook.", "confidence": 61},
    ],
    "fundamentals_reports": [
        {"ticker": "NVDA", "revenue_growth_yoy": 122, "gross_margin": 74.6, "business_quality": "exceptional",
         "valuation": "premium — justified by growth", "net_cash_position_b": 26, "summary": "Best-in-class financials.", "confidence": 91},
        {"ticker": "PANW",  "revenue_growth_yoy": 14, "gross_margin": 74.1, "business_quality": "high",
         "valuation": "fair", "net_cash_position_b": 3, "summary": "Strong recurring revenue model.", "confidence": 79},
        {"ticker": "XOM",  "revenue_growth_yoy": -8, "gross_margin": 31.2, "business_quality": "average",
         "valuation": "cheap", "net_cash_position_b": -12, "summary": "Cyclical pressures weighing on growth.", "confidence": 65},
    ],
    "geo_reports": [
        {"ticker": "NVDA", "risk_level": "medium", "macro_tailwinds": ["AI capex supercycle", "Data centre buildout"],
         "geopolitical_risks": ["Taiwan TSMC concentration", "US chip export restrictions"],
         "summary": "Medium geo risk offset by massive structural tailwinds.", "confidence": 77},
        {"ticker": "PANW",  "risk_level": "low", "macro_tailwinds": ["Cyber threat escalation drives spend"],
         "geopolitical_risks": ["Budget scrutiny if recession"],
         "summary": "Low geo risk — cybersecurity benefits from geopolitical tension.", "confidence": 83},
        {"ticker": "XOM",  "risk_level": "high", "macro_tailwinds": ["Iran tensions lift oil price"],
         "geopolitical_risks": ["Hormuz closure", "OPEC+ policy uncertainty", "Energy transition"],
         "summary": "High geo risk on both upside and downside.", "confidence": 62},
    ],
}

MOCK_CAUSAL_THESES = [
    {
        "theme_id": "AI_INFRASTRUCTURE_BOOM",
        "root_cause": "Hyperscaler AI capex supercycle",
        "contrarian_take": "Everyone buys NVDA. Smart money buys the power grid.",
        "confidence": 85,
    },
    {
        "theme_id": "US_IRAN_TENSIONS",
        "root_cause": "Hormuz closure → energy supply shock → hard asset bid",
        "contrarian_take": "Everyone buys oil majors. Smart money buys gold and cybersecurity.",
        "confidence": 78,
    },
]


def _seed_mongo(run_id: str) -> None:
    """Write mock reports into MongoDB so RankingAgent can read them."""
    col_map = {
        "market_reports":       Collections.MARKET_DATA,
        "news_reports":         Collections.NEWS_SENTIMENT,
        "fundamentals_reports": Collections.FUNDAMENTALS,
        "geo_reports":          Collections.GEO_MACRO,
    }
    for key, collection in col_map.items():
        col = get_collection(collection)
        for report in MOCK_REPORTS[key]:
            doc = {**report, "run_id": run_id}
            col.update_one(
                {"ticker": doc["ticker"], "run_id": run_id},
                {"$set": doc},
                upsert=True,
            )

    # Seed causal theses
    col = get_collection(Collections.CAUSAL_THESES)
    for thesis in MOCK_CAUSAL_THESES:
        col.update_one(
            {"theme_id": thesis["theme_id"], "run_id": run_id},
            {"$set": {**thesis, "run_id": run_id}},
            upsert=True,
        )

    # Seed screener results
    col = get_collection(Collections.SCREENER_RESULTS)
    for ticker in ["NVDA", "PANW", "XOM"]:
        col.update_one(
            {"ticker": ticker, "run_id": run_id},
            {"$set": {"ticker": ticker, "run_id": run_id}},
            upsert=True,
        )
    print(f"  Seeded mock data for run {run_id[:8]}")


def main():
    run_id = str(uuid.uuid4())
    print(f"\nTesting Agent 8 — Ranking Agent")
    print(f"Stocks: NVDA, PANW, XOM")
    print(f"Run ID: {run_id[:8]}\n")

    print("Seeding mock reports into MongoDB...")
    try:
        _seed_mongo(run_id)
        print("  [OK] MongoDB seeded")
    except Exception as e:
        print(f"  [FAIL] MongoDB seed failed: {e}")
        return

    print("\nRunning Ranking Agent (needs Bedrock)...")
    try:
        from agents.ranking import RankingAgent
        agent = RankingAgent()
        report = agent.rank(run_id=run_id)

        print(f"\n{'='*60}")
        print(f"Final Report")
        print(f"  Market regime:     {report.market_regime.label if report.market_regime else 'N/A'}")
        print(f"  Total signals:     {report.total_signals}")
        print(f"  Stocks analysed:   {report.stocks_deep_analysed}")
        print(f"  Causal summary:    {report.causal_summary[:120]}...")
        print()

        for horizon in report.horizons:
            print(f"  [{horizon.horizon.upper()}]")
            for pick in horizon.picks:
                print(f"    BUY  {pick.ticker:<6} {pick.confidence}% — {pick.thesis[:60]}")
            for pick in horizon.contrarian_picks:
                print(f"    CONTRARIAN {pick.ticker:<6} — {pick.thesis[:60]}")
            for pick in horizon.avoid:
                print(f"    AVOID {pick.ticker:<6} — {pick.thesis[:60]}")

        print(f"\n  Analyst note: {report.analyst_note[:150]}")

    except Exception as e:
        print(f"  [LLM skipped — Bedrock not available]: {e}")
        print(f"\n  MongoDB seed succeeded. Agent 8 data layer is working.")
        print(f"  Once Bedrock is available, run: uv run python test_ranking_agent.py")


if __name__ == "__main__":
    main()
