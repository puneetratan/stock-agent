"""
Agent 7 — Geo/Macro Agent.

Assesses how current macro environment and geopolitical events affect
a specific stock. Uses active causal theses as context.
"""

from crewai import Agent, Task

from tools.bedrock import get_llm

_BACKSTORY = """
You are a Macro and Geopolitical Risk Analyst. Your job is to assess how
the big picture — monetary policy, geopolitics, supply chains, regulatory
regimes, and global capital flows — affects individual stocks.

You understand:
- How Fed rate cycles affect growth vs value rotation, credit spreads, USD
- How geopolitical events disrupt specific supply chains and sectors
- How sanctions and trade policy create winners and losers
- How currency moves affect multinational earnings
- How energy prices cascade through transport, manufacturing, and margins

You work closely with the Causal Reasoning Agent's theses. Your job is to
apply those macro frameworks to the specific company being analysed.
You identify both tailwinds and headwinds.

You rate risk levels conservatively — "low" means genuinely low,
not "it'll probably be fine".
"""


def build_geo_agent() -> Agent:
    return Agent(
        role="Macro & Geopolitical Risk Analyst",
        goal=(
            "Assess how the current macro environment, Fed policy, and "
            "geopolitical events affect this specific stock."
        ),
        backstory=_BACKSTORY,
        llm=get_llm("geo"),
        verbose=True,
        allow_delegation=False,
    )


GEO_TASK_DESCRIPTION = """
Assess macro and geopolitical context for {ticker}.

Active causal theses from our root-cause analysis:
{causal_theses}

Macro data:
- Fed rate decision: {fed_rate}
- Inflation (CPI): {cpi}
- Sector ETF flow: {sector_flow}

Context from other agents:
- Technical signal: {technical_signal}
- Sentiment: {sentiment_label}
- Business quality: {business_quality}

Specific geo/supply-chain queries have been searched:
- "{ticker} geopolitical risk": {geo_search}
- "{ticker} supply chain risk": {supply_chain_search}

Map the active causal theses to this specific company.
Identify whether this company is a BENEFICIARY, VICTIM, or NEUTRAL
to each active macro theme.

Output STRICTLY as JSON — no other text:
{{
  "ticker": "{ticker}",
  "macro_environment": "<one sentence on current macro climate>",
  "sector_flow": "<positive/negative/neutral with context>",
  "geopolitical_risks": ["risk1", "risk2"],
  "macro_tailwinds": ["tailwind1", "tailwind2"],
  "theme_exposure": {{
    "THEME_ID": "beneficiary | victim | neutral — reason"
  }},
  "risk_level": "low | medium | high | critical",
  "risk_overrides_positive_signals": false,
  "summary": "<2-3 sentence geo/macro assessment>",
  "confidence": <0-100>
}}
"""
