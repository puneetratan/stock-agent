"""
Quick test: runs Agent 3 (Screener) with hardcoded causal theses.
Bypasses Agents 1 and 2.

Usage:
    uv run python test_screener_agent.py
"""

import uuid
from dotenv import load_dotenv
load_dotenv()

from agents.screener import ScreenerAgent

# Hardcoded theses — what Agent 2 would normally produce
TEST_THESES = [
    {
        "theme_id": "US_IRAN_TENSIONS",
        "root_cause": "Strait of Hormuz closure threatening global oil supply",
        "theses": {
            "quarter":   {"sectors": ["energy", "defense"], "tickers_to_watch": ["XOM", "RTX", "LMT"], "avoid_sectors": ["airlines"], "reason": "energy supply shock"},
            "one_year":  {"sectors": ["gold", "cybersecurity"], "tickers_to_watch": ["NEM", "PANW", "CRWD"], "avoid_sectors": ["consumer"], "reason": "geopolitical premium"},
            "two_year":  {"sectors": ["energy", "defense"], "tickers_to_watch": ["CVX", "NOC"], "avoid_sectors": [], "reason": "prolonged conflict cycle"},
            "five_year": {"sectors": ["gold", "commodities"], "tickers_to_watch": ["GLD", "FCX"], "avoid_sectors": [], "reason": "dedollarisation"},
            "ten_year":  {"sectors": ["hard_assets"], "tickers_to_watch": ["GLD"], "avoid_sectors": ["bonds"], "reason": "currency debasement"},
        },
        "confidence": 78,
    },
    {
        "theme_id": "AI_INFRASTRUCTURE_BOOM",
        "root_cause": "Hyperscaler AI capex creating multi-year infrastructure supercycle",
        "theses": {
            "quarter":   {"sectors": ["semiconductors", "data_centers"], "tickers_to_watch": ["NVDA", "AMD", "AVGO"], "avoid_sectors": [], "reason": "earnings momentum"},
            "one_year":  {"sectors": ["power", "cooling"], "tickers_to_watch": ["VST", "CEG", "VIST"], "avoid_sectors": [], "reason": "power demand surge"},
            "two_year":  {"sectors": ["networking", "storage"], "tickers_to_watch": ["ANET", "PSTG"], "avoid_sectors": [], "reason": "infrastructure buildout"},
            "five_year": {"sectors": ["AI_software"], "tickers_to_watch": ["MSFT", "GOOGL", "META"], "avoid_sectors": [], "reason": "monetisation phase"},
            "ten_year":  {"sectors": ["robotics", "autonomous"], "tickers_to_watch": ["TSLA", "ISRG"], "avoid_sectors": [], "reason": "physical AI"},
        },
        "confidence": 85,
    },
]

def main():
    run_id = str(uuid.uuid4())
    print(f"\nTesting Agent 3 — Screener")
    print(f"Run ID: {run_id[:8]}")
    print(f"Input theses: {[t['theme_id'] for t in TEST_THESES]}\n")

    agent = ScreenerAgent()
    candidates = agent.screen(TEST_THESES, run_id=run_id)

    print(f"\n{'='*60}")
    print(f"Screener Results: {len(candidates)} candidates passed all 3 stages\n")

    for i, c in enumerate(candidates[:20], 1):
        ticker   = c.get("ticker", "?")
        score    = c.get("theme_alignment_score", "N/A")
        themes   = c.get("theme_alignment", [])
        reason   = c.get("pass_reason", "")
        rsi      = c.get("rsi", "N/A")
        print(f"  {i:2}. {ticker:<6}  score={score}  rsi={rsi}  themes={themes}")
        if reason:
            print(f"       {reason[:80]}")

if __name__ == "__main__":
    main()
