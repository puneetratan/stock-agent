"""
Agent 6 — Fundamentals Agent.

Analyses company financial health: revenue growth, margins, valuation,
cash flow quality, debt, insider activity. Uses Sonnet for complex reasoning.
"""

from crewai import Agent, Task

from tools.bedrock import get_llm

_BACKSTORY = """
You are a Fundamental Financial Analyst trained in value investing,
growth analysis, and quality screening.

You apply frameworks from:
- Warren Buffett: durable competitive advantages, owner earnings, ROIC
- Peter Lynch: PEG ratio, growth at reasonable price (GARP)
- Benjamin Graham: margin of safety, balance sheet strength
- Joel Greenblatt: return on capital + earnings yield (Magic Formula)

You read financial statements not as accountants do — for compliance —
but as detectives do — for truth. You look for:
- Revenue quality: recurring vs one-time, organic vs acquired
- Margin trend direction (improving vs deteriorating)
- Cash conversion: does net income turn into real cash?
- Balance sheet stress: can the company survive a recession?
- Insider conviction: are insiders buying or quietly selling?

You know that valuation without quality is a value trap.
You know that quality without valuation is an expensive mistake.
You synthesise both.
"""


def build_fundamentals_agent() -> Agent:
    return Agent(
        role="Fundamental Financial Analyst",
        goal=(
            "Assess the financial health, growth trajectory, and valuation "
            "of a company using income statements, balance sheets, and filings."
        ),
        backstory=_BACKSTORY,
        llm=get_llm("fundamentals"),
        verbose=True,
        allow_delegation=False,
    )


FUNDAMENTALS_TASK_DESCRIPTION = """
Perform deep fundamental analysis for {ticker}.

Context from News Agent:
{news_report}

Financial data:
- Income statements (8 quarters): {income_statements}
- Balance sheet: {balance_sheet}
- Cash flow: {cash_flow}
- PE ratio and valuation ratios: {pe_ratio}
- Insider trades (90 days): {insider_trades}
- Most recent SEC filing: {sec_filing}

Compute year-over-year revenue growth (most recent quarter vs same quarter prior year).
Assess gross margin trend across the 8 quarters (improving/stable/deteriorating).
Evaluate balance sheet quality (net cash vs net debt position).
Interpret insider activity as a signal (buying = conviction, selling = caution).

Output STRICTLY as JSON — no other text:
{{
  "ticker": "{ticker}",
  "revenue_growth_yoy": <percent or null>,
  "gross_margin": <latest percent>,
  "gross_margin_trend": "improving | stable | deteriorating",
  "net_margin": <latest percent>,
  "pe_ratio": <number or null>,
  "pe_vs_sector": "<string: premium/discount/fair with reasoning>",
  "peg_ratio": <number or null>,
  "debt_to_equity": <number or null>,
  "net_cash_position_b": <number, negative = net debt>,
  "free_cash_flow_trend": "positive | improving | declining | negative",
  "insider_activity": "<description: buying/selling/neutral with context>",
  "earnings_trend": "<3 consecutive beats | mixed | misses>",
  "business_quality": "exceptional | high | average | poor",
  "valuation": "<one of: cheap | fair | premium | expensive with reasoning>",
  "summary": "<2-3 sentence fundamental summary>",
  "confidence": <0-100>
}}
"""
