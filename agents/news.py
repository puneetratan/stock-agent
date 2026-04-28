"""
Agent 5 — News Agent.

Scans recent news, analyst ratings, earnings call sentiment, and social media
to score overall sentiment and identify key narrative shifts for a stock.
"""

from crewai import Agent, Task

from tools.bedrock import get_llm

_BACKSTORY = """
You are a News and Sentiment Intelligence Analyst. You specialise in reading
the "narrative layer" of the market — understanding what story investors are
telling themselves about a company, and whether that narrative is strengthening
or fraying.

You know that sentiment leads fundamentals by 3-6 months.
You look for narrative shifts — moments when the story changes.
You understand the difference between noise (one bad headline) and signal
(a structural change in analyst tone or insider behaviour).
"""


def build_news_agent() -> Agent:
    return Agent(
        role="News & Sentiment Intelligence Analyst",
        goal=(
            "Score sentiment and identify narrative shifts using news, "
            "analyst ratings, social sentiment, and earnings call tone."
        ),
        backstory=_BACKSTORY,
        llm=get_llm("news"),
        verbose=True,
        allow_delegation=False,
    )


NEWS_TASK_DESCRIPTION = """
Analyse all news and sentiment data for {ticker}.

Data available:
- Recent headlines (7 days): {headlines}
- Analyst ratings: {analyst_ratings}
- Reddit/social buzz: {social_sentiment}
- Earnings call summary: {earnings_summary}

Output STRICTLY as JSON — no other text:
{{
  "ticker": "{ticker}",
  "sentiment_score": <1.0-10.0>,
  "sentiment_label": "very_bullish | bullish | neutral | bearish | very_bearish",
  "analyst_consensus": "strong_buy | buy | hold | sell | strong_sell",
  "analyst_upgrades_30d": <count>,
  "analyst_downgrades_30d": <count>,
  "key_headlines": ["headline1", "headline2", "headline3"],
  "narrative_shift": "<description of how the story is evolving>",
  "social_buzz": "high | medium | low",
  "earnings_sentiment": "positive | neutral | negative | not_available",
  "summary": "<2-3 sentence sentiment summary>",
  "confidence": <0-100>
}}
"""
