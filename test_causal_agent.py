"""
Quick test: runs Agent 2 (Causal Reasoning) with hardcoded themes.
Bypasses Agent 1 so you can test the causal analysis in isolation.

Usage:
    uv run python test_causal_agent.py
"""

import uuid
from dotenv import load_dotenv
load_dotenv()

from models import Theme, ThemeStatus
from agents.causal_reasoning import CausalReasoningAgent

# Hardcoded themes — what Agent 1 would normally produce
TEST_THEMES = [
    Theme(
        id="US_IRAN_TENSIONS",
        name="US-Iran Tensions / Strait of Hormuz",
        urgency=9,
        status=ThemeStatus.HOT,
        summary=(
            "US-Iran tensions are escalating with the Strait of Hormuz "
            "partially closed, threatening global oil supply routes and "
            "pushing energy prices higher."
        ),
        evidence=[
            "Strait of Hormuz Remains Largely Closed as US-Iran Tensions Escalate",
            "Stock futures fall as Iran peace talks stall, oil rises",
            "EU considers helping with Mideast energy infrastructure to bypass conflict zones",
        ],
        run_id="test-run",
    ),
    Theme(
        id="AI_INFRASTRUCTURE_BOOM",
        name="AI Data Centre Infrastructure Buildout",
        urgency=7,
        status=ThemeStatus.HOT,
        summary=(
            "Massive AI infrastructure investment is accelerating, with towns "
            "planning dozens of data centres and hyperscalers committing "
            "record capex to GPU compute and power."
        ),
        evidence=[
            "A town of 7,000 planned so many data centres, it's like adding 51 Walmarts",
            "Intel stock wins new street-high price target",
            "Apple setting new CEO up to be synonymous with foldable iPhone",
        ],
        run_id="test-run",
    ),
]

def main():
    run_id = str(uuid.uuid4())
    print(f"\nTesting Agent 2 — Causal Reasoning")
    print(f"Run ID: {run_id[:8]}")
    print(f"Themes: {[t.id for t in TEST_THEMES]}\n")

    agent = CausalReasoningAgent()
    theses = agent.analyse(TEST_THEMES, run_id=run_id)

    print(f"\n{'='*60}")
    print(f"Results: {len(theses)} causal theses produced")
    for t in theses:
        if "error" in t:
            print(f"\n[FAILED] {t['theme_id']}: {t['error']}")
        else:
            print(f"\n[OK] {t.get('theme_id')}")
            print(f"  Root cause: {t.get('root_cause', '')[:100]}")
            print(f"  Confidence: {t.get('confidence')}%")
            horizons = list(t.get('theses', {}).keys())
            print(f"  Horizons: {horizons}")

if __name__ == "__main__":
    main()
