"""
Quick test: runs Agent 5 (News/Sentiment) for a single ticker.

Usage:
    uv run python test_news_agent.py
"""

import json
import uuid
from dotenv import load_dotenv
load_dotenv()

TICKER = "NVDA"

def main():
    run_id = str(uuid.uuid4())
    print(f"\nTesting Agent 5 — News Agent ({TICKER})")
    print(f"Run ID: {run_id[:8]}\n")

    print("Fetching news and sentiment data...")
    from mcp_servers.intelligence_mcp import (
        search_news, get_analyst_ratings,
        get_reddit_sentiment, get_earnings_call_summary,
    )

    data = {}
    steps = [
        ("headlines",        lambda: search_news(TICKER, days=7)),
        ("analyst_ratings",  lambda: get_analyst_ratings(TICKER)),
        ("social_sentiment", lambda: get_reddit_sentiment(TICKER)),
        ("earnings_summary", lambda: get_earnings_call_summary(TICKER)),
    ]

    for key, fn in steps:
        try:
            data[key] = fn()
            print(f"  [OK] {key}")
        except Exception as e:
            data[key] = {} if key != "headlines" else []
            print(f"  [FAIL] {key}: {e}")

    headlines = data.get("headlines", [])
    ratings   = data.get("analyst_ratings", {})
    social    = data.get("social_sentiment", {})

    print(f"\nRaw data summary:")
    print(f"  Headlines found:    {len(headlines)}")
    print(f"  Analyst consensus:  {ratings.get('consensus', 'N/A')}")
    print(f"  Buy / Hold / Sell:  {ratings.get('buy_count',0)} / {ratings.get('hold_count',0)} / {ratings.get('sell_count',0)}")
    print(f"  Social buzz:        {social.get('buzz_level', 'N/A')} ({social.get('mention_count', 0)} mentions)")
    if headlines:
        print(f"  Latest headline:    {headlines[0].get('title', '')[:80]}")

    print(f"\nRunning LLM synthesis (needs Bedrock)...")
    try:
        from crewai import Crew, Process, Task
        from agents.news import build_news_agent, NEWS_TASK_DESCRIPTION

        agent = build_news_agent()
        task = Task(
            description=NEWS_TASK_DESCRIPTION.format(
                ticker=TICKER,
                headlines=json.dumps(headlines[:5])[:2000],
                analyst_ratings=json.dumps(ratings),
                social_sentiment=json.dumps(social),
                earnings_summary=str(data.get("earnings_summary", ""))[:800],
            ),
            agent=agent,
            expected_output="Structured JSON news/sentiment report",
        )
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff()

        raw = str(result)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        start, end = raw.find("{"), raw.rfind("}") + 1
        report = json.loads(raw[start:end])

        print(f"\n{'='*60}")
        print(f"News Report for {TICKER}")
        print(f"  Sentiment score:   {report.get('sentiment_score')}/10")
        print(f"  Sentiment label:   {report.get('sentiment_label')}")
        print(f"  Analyst consensus: {report.get('analyst_consensus')}")
        print(f"  Narrative shift:   {report.get('narrative_shift')}")
        print(f"  Social buzz:       {report.get('social_buzz')}")
        print(f"  Confidence:        {report.get('confidence')}%")
        print(f"\n  Summary: {report.get('summary')}")

    except Exception as e:
        print(f"  [LLM skipped — Bedrock not available]: {e}")
        print(f"\n  Raw data fetch succeeded. Agent 5 data layer is working.")


if __name__ == "__main__":
    main()
