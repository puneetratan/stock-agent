"""
Agent 4 — Market Agent.

Fetches and analyses all technical indicators for a given stock.
Outputs a structured market report with a technical signal.
"""

from crewai import Agent, Task

from tools.bedrock import get_llm

_BACKSTORY = """
You are a Technical Market Analyst with 20 years of experience reading charts
and market microstructure. You use price action, momentum indicators, volume
analysis, and options flow to assess near-term directional bias.

Your outputs are always structured, precise, and quantified.
You do not make vague statements — every claim is backed by a specific number.
"""


def build_market_agent() -> Agent:
    """Returns a configured Market Agent for use in a Crew."""
    return Agent(
        role="Technical Market Analyst",
        goal=(
            "Analyse price momentum, volume trends, technical indicators, and "
            "options flow to determine the near-term technical picture."
        ),
        backstory=_BACKSTORY,
        llm=get_llm("market"),
        verbose=True,
        allow_delegation=False,
    )


MARKET_TASK_DESCRIPTION = """
Perform a complete technical analysis for {ticker}.

You have access to the following data already fetched:
- Price history (90 days): {price_history}
- RSI (14-period): {rsi}
- MACD: {macd}
- Volume profile: {volume_profile}
- Options flow: {options_flow}
- 52-week range: {range_52w}

Synthesise this data and output STRICTLY as JSON — no other text:
{{
  "ticker": "{ticker}",
  "technical_signal": "bullish | bearish | neutral",
  "rsi": <number>,
  "rsi_interpretation": "oversold | neutral | overbought",
  "macd": "<macd signal string>",
  "volume_trend": "increasing | decreasing | neutral",
  "price_vs_52w": "<string like '68% above 52w low'>",
  "options_flow": "<string like 'bullish — call/put ratio 2.3'>",
  "support_level": <price or null>,
  "resistance_level": <price or null>,
  "summary": "<2-3 sentence technical summary>",
  "confidence": <0-100>
}}
"""
