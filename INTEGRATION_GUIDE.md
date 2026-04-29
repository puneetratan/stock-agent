# STOCK INTELLIGENCE AGENT — FULL INTEGRATION GUIDE
# Feed this to Claude in VSCode
# This extends the existing project from ARCHITECTURE.md
# and GLOBAL_ARCHITECTURE.md

---

## CONTEXT FOR CLAUDE IN VSCODE

You are extending an existing Python project called
stock_intelligence that was scaffolded from ARCHITECTURE.md
and GLOBAL_ARCHITECTURE.md.

The base project already has:
  - 8 agents (world, causal, screener, market, news, fundamentals, geo, ranking)
  - 3 MCP servers (market_mcp, intelligence_mcp, mongo_mcp)
  - MongoDB Atlas connection
  - AWS Bedrock connection
  - CrewAI orchestration
  - pyproject.toml with uv

Now add everything listed below.
Do not break existing code.
These are additions and extensions only.

---

## ITEM 1 — SIGNAL VERIFICATION JOB
File to create: signal_verification_job.py (root level)

Purpose:
  Runs every night at 23:00.
  Checks every signal that is 30, 90, 180 days old.
  Fetches actual price outcome from Polygon.io.
  Records whether signal was correct.
  Calculates running accuracy scorecard.
  This is the foundation of the 70% accuracy target.

Logic:
  BUY signal correct  → price higher after N days
  SELL signal correct → price lower after N days
  HOLD signal correct → price moved less than 5%

Accuracy scorecard breaks down by:
  - Overall accuracy (all signals)
  - By horizon (30d, 90d, 180d)
  - By signal type (BUY, SELL, HOLD)
  - By confidence band:
      High confidence:   >= 80%
      Medium confidence: 60-79%
      Low confidence:    < 60%
  - Average return on correct signals
  - Whether 70% target is hit

MongoDB collections to write:
  signals collection:
    Add fields per verified signal:
      price_30d_later, return_30d_pct, signal_correct_30d, verified_30d
      price_90d_later, return_90d_pct, signal_correct_90d, verified_90d
      price_180d_later, return_180d_pct, signal_correct_180d, verified_180d

  accuracy_scorecard collection (new):
    Insert one document per run with full scorecard

Key rule:
  Never re-verify already verified signals
  Never verify future dates
  Rate limit Polygon API calls (0.5s between calls)
  Log every verification with emoji: ✅ correct ❌ wrong

Print report format:
  ================================================
  📊 SIGNAL ACCURACY SCORECARD
  ================================================
  ⏱  30d horizon (N signals)
     Overall accuracy:     X%  ✅/❌
     High conf accuracy:   X%  ✅/❌
     BUY accuracy:         X%
     Avg return (correct): +X%
     70% target:           HIT ✅ / NOT YET
  ================================================

---

## ITEM 2 — SENTIMENT AGENT
File to create: agents/sentiment.py

Purpose:
  Measures human emotions and market psychology.
  Detects where we are in narrative cycles.
  Finds divergence between sentiment and price.
  Identifies fear/greed extremes.
  This is what makes the system different from
  pure technical analysis tools.

Role: "Market Psychology & Sentiment Analyst"
LLM: Claude Sonnet (needs nuanced reasoning)

What it measures:

  FEAR INDICATORS:
    VIX level            (below 15=complacent, above 30=fear, above 40=panic)
    Put/Call ratio       (above 1.2 = fear, below 0.7 = greed)
    Google Trends        ("stock market crash", "recession", "bear market")
    News negativity      (NLP sentiment score on financial headlines)
    Insider selling      (when CEOs sell = they know something)
    Fund outflows        (money leaving equity funds)

  GREED INDICATORS:
    IPO volume           (too many IPOs = greed peak like 2021)
    Margin debt levels   (borrowing to buy = greed)
    Call option volume   (retail buying calls = euphoria)
    "To the moon" language on Reddit
    Google Trends        ("how to buy stocks", "best stocks to buy now")
    Fund inflows         (money pouring into equities = late cycle)

  NARRATIVE CYCLE TRACKER:
    For each active theme track which phase:
      Phase 1: Story emerges     (maximum opportunity)
      Phase 2: Hype peak         (maximum danger)
      Phase 3: Disappointment    (short opportunity)
      Phase 4: Death or rebirth  (contrarian opportunity)

    Examples:
      AI:          Phase 2 hype (still going, watch carefully)
      Crypto:      Phase 3 disillusion
      Defence:     Phase 1 emerging
      Metaverse:   Phase 4 dead
      Web3:        Phase 4 dead
      Space:       Phase 1 emerging

  SMART MONEY vs DUMB MONEY:
    Smart money: institutional options flow, 13F filings,
                 dark pool prints, insider BUYING
    Dumb money:  retail options flow, Reddit euphoria,
                 YouTube finance pump videos
    Divergence warning: when retail euphoric but
                        institutions quietly reducing = danger

Tools (MCP calls):
  - fred_mcp.get_vix()
  - market_mcp.get_put_call_ratio()
  - intelligence_mcp.google_trends(keyword)
  - intelligence_mcp.reddit_sentiment(subreddit)
  - intelligence_mcp.news_sentiment_score(topic)
  - market_mcp.get_short_interest(ticker)
  - market_mcp.get_insider_activity(ticker)
  - intelligence_mcp.web_search("IPO volume 2026")
  - mongo_mcp.get_recent_themes()

Output schema:
  {
    "market_emotion":       "greed",
    "fear_greed_score":     72,
    "vix_level":            14.2,
    "put_call_ratio":       0.72,
    "narrative_cycles": {
      "AI":          "phase_2_hype",
      "crypto":      "phase_3_disillusion",
      "defence":     "phase_1_emerging",
      "space":       "phase_1_emerging"
    },
    "smart_vs_dumb": {
      "institutional":  "cautiously_bullish",
      "retail":         "euphoric",
      "divergence":     "WARNING — retail euphoric,
                         institutions reducing quietly"
    },
    "contrarian_signal":  "Retail euphoria at 89/100 —
                            historically precedes correction
                            within 4-8 weeks",
    "google_trends": {
      "buy stocks":   "rising",
      "recession":    "falling",
      "AI stocks":    "peak"
    },
    "fear_greed_history": [],
    "summary":            "...",
    "confidence":         78
  }

Backstory:
  You have studied market psychology for 20 years.
  You understand that markets are human emotions at scale.
  You know that fear and greed are more predictive than
  any technical indicator at extremes.
  You have read every book on behavioural finance:
  Thinking Fast and Slow, Irrational Exuberance,
  The Psychology of Money, Extraordinary Popular Delusions.
  You are not fooled by narrative — you measure it.

---

## ITEM 3 — GOOGLE TRENDS TOOL
File to create: tools/google_trends.py

Purpose:
  Free sentiment data source.
  Measures retail investor interest in topics over time.
  Peak Google Trends for a stock/theme often correlates
  with peak price (retail FOMO at the top).

Library to use: pytrends (add to pyproject.toml)
  uv add pytrends

Functions to implement:

  get_trend_score(keyword: str, timeframe: str = "today 3-m") -> dict
    Returns:
      current_score:  0-100 (relative interest)
      trend:          "rising" | "falling" | "peak" | "stable"
      peak_date:      when was interest highest
      comparison:     vs 30 days ago

  get_related_queries(keyword: str) -> list[str]
    Returns rising related queries
    Useful for detecting emerging sub-themes

  compare_trends(keywords: list[str]) -> dict
    Compare multiple keywords
    Example: compare ["buy NVDA", "sell NVDA", "NVDA crash"]

  get_regional_interest(keyword: str) -> dict
    Which countries are most interested
    Useful for global sentiment coverage

Key keywords to track regularly:
  Financial fear:    "stock market crash", "recession 2026",
                     "bear market", "inflation"
  Financial greed:   "how to buy stocks", "best stocks 2026",
                     "get rich stocks", "stock tips"
  Theme tracking:    "AI stocks", "defence stocks",
                     "oil stocks", "gold", "bitcoin"
  Specific tickers:  Add top tickers from watchlist

---

## ITEM 4 — NARRATIVE CYCLE DETECTOR
File to create: agents/narrative_cycle.py

Purpose:
  Tracks where any investment theme sits in its hype cycle.
  Uses Google Trends + news volume + Reddit activity
  to measure narrative momentum.
  Predicts when themes are about to peak or bottom.

Based on Gartner Hype Cycle adapted for markets:
  Innovation trigger   → Phase 1: Early awareness
  Peak of inflated     → Phase 2: Maximum hype
  expectations
  Trough of            → Phase 3: Disillusionment
  disillusionment
  Slope of             → Phase 4: Quiet recovery
  enlightenment           or permanent death

How to detect each phase:
  Phase 1 signals:
    Google Trends rising from low base
    Only specialist media covering it
    Reddit mentions starting
    Early institutional money moving in

  Phase 2 signals:
    Google Trends at or near peak
    Mainstream media covering it daily
    Everyone on Reddit talking about it
    Retail FOMO at maximum
    IPOs in the space accelerating
    Valuations disconnected from fundamentals
    THIS IS THE DANGER ZONE — do not initiate new positions

  Phase 3 signals:
    Google Trends falling from peak
    Negative news cycle starting
    Reddit going quiet or negative
    IPOs in space pulled or failing
    Layoffs in theme companies

  Phase 4 signals:
    Minimal media coverage
    Google Trends at floor
    Only true believers remain
    Valuations at historical lows
    THIS IS THE OPPORTUNITY ZONE for next cycle

Tools:
  - google_trends(theme_keyword)
  - intelligence_mcp.search_news(theme, days=7)
  - intelligence_mcp.get_news_volume(theme, days=90)
  - intelligence_mcp.reddit_sentiment(theme)
  - mongo_mcp.get_theme_history(theme_id)

Output per theme:
  {
    "theme":           "AI_BOOM",
    "current_phase":   "phase_2_hype",
    "phase_score":     78,
    "trend":           "approaching_peak",
    "google_peak":     "2026-02-14",
    "news_volume_30d": "high",
    "reddit_sentiment":"euphoric",
    "action":          "CAUTION — reduce new positions,
                        protect existing gains",
    "historical_note": "Similar to crypto in Nov 2021 —
                        3 months before 70% drawdown"
  }

---

## ITEM 5 — CROSSOVER TRACKER
File to create: tools/crossover_tracker.py

Purpose:
  Tracks two income lines over time.
  Line 1: Full time job income (user inputs monthly)
  Line 2: Side gig income (portfolio returns + product revenue)
  Calculates when crossover point is reached.
  This is the decision support tool for when to switch.

MongoDB collection: crossover_data (new)
  {
    date:           Date,
    job_income:     Number,    # user inputs this monthly
    portfolio_value: Number,   # auto from signals
    portfolio_return_month: Number,
    product_revenue: Number,   # newsletter + API income
    total_side_income: Number, # portfolio_return + product_revenue
    crossover_reached: Boolean,
    months_above_job: Number,  # consecutive months side > job
    crossover_date:  Date      # when it first happened
  }

Functions:
  record_monthly(job_income, product_revenue) -> dict
    User calls this once a month
    System calculates portfolio return automatically
    Saves to crossover_data collection
    Returns current status

  get_crossover_status() -> dict
    Returns:
      job_income_avg:        last 3 month average
      side_income_avg:       last 3 month average
      crossover_reached:     bool
      months_consecutive:    how many months side > job
      crossover_confirmed:   True if 3+ consecutive months
      gap_to_crossover:      how much more needed
      projected_crossover:   estimated date based on growth rate

  plot_crossover_chart() -> None
    Prints ASCII chart of both lines over time
    Simple, no frontend needed
    Shows trajectory clearly

Rule for confirmed crossover:
  Side income > Job income for 3 CONSECUTIVE months
  Not 1 month — 3 months (same logic as 70/100 rule)
  Consistency over one lucky event

---

## ITEM 6 — UPDATED SENTIMENT IN EXISTING AGENTS

Update agents/causal_reasoning.py:
  Add sentiment context to causal analysis
  Causal agent now receives sentiment report
  as additional context before reasoning
  Adds field to output:
    "sentiment_alignment": "bullish sentiment CONFIRMS
                             causal thesis" OR
                           "WARNING — sentiment CONTRADICTS
                             causal thesis (contrarian signal)"

Update agents/ranking.py:
  Ranking agent now receives sentiment report
  Narrative cycle phase affects ranking:
    Phase 1 themes → boost ranking (early opportunity)
    Phase 2 themes → flag warning (late cycle risk)
    Phase 3 themes → lower ranking or short signal
    Phase 4 themes → contrarian flag for long horizon

Update agents/crew.py:
  Add sentiment_agent to crew
  Add narrative_cycle agent to crew
  Run sentiment BEFORE ranking
  Pass sentiment output to ranking agent as context

---

## ITEM 7 — UPDATED run_schedule.py

Add to existing schedule:

  # Morning agent run (existing — keep)
  Weekdays at 06:30 — full agent run

  # Nightly verification (NEW)
  Every day at 23:00 — signal_verification_job.py

  # Monthly crossover tracking (NEW)
  First of each month at 09:00:
    Prompt user to input job income
    Auto-calculate portfolio value
    Save to crossover_data
    Print crossover status

  # Weekly sentiment snapshot (NEW)
  Every Sunday at 08:00:
    Run sentiment agent standalone
    Save fear/greed snapshot to MongoDB
    This builds sentiment history over time

---

## ITEM 8 — UPDATED MongoDB COLLECTIONS

Add to db/collections.py:

  ACCURACY_SCORECARD = "accuracy_scorecard"
  CROSSOVER_DATA     = "crossover_data"
  SENTIMENT_HISTORY  = "sentiment_history"
  NARRATIVE_CYCLES   = "narrative_cycles"
  GOOGLE_TRENDS      = "google_trends_history"

Schema additions to signals collection:
  price_at_signal:     Number   # MUST save this when signal created
  verified_30d:        Boolean
  price_30d_later:     Number
  return_30d_pct:      Number
  signal_correct_30d:  Boolean
  verified_90d:        Boolean
  price_90d_later:     Number
  return_90d_pct:      Number
  signal_correct_90d:  Boolean
  verified_180d:       Boolean
  price_180d_later:    Number
  return_180d_pct:     Number
  signal_correct_180d: Boolean

IMPORTANT:
  When saving any new signal to MongoDB
  ALWAYS include price_at_signal field.
  Without this verification cannot work.
  This is the most critical field in the system.

---

## ITEM 9 — UPDATED pyproject.toml DEPENDENCIES

Add these to existing dependencies:

  "pytrends>=4.9.0",          # Google Trends
  "schedule>=1.2.0",          # already there, keep
  "numpy>=1.26.0",            # for accuracy calculations
  "tabulate>=0.9.0",          # pretty print tables in terminal

Run after updating:
  uv sync

---

## ITEM 10 — ask.py (RAG TERMINAL INTERFACE)
File to create: ask.py (root level)

Purpose:
  Talk to your own 180-day data in plain English.
  Conversational agent grounded in YOUR MongoDB data.
  No hallucination — every answer traceable to real data.
  This is the RAG layer on top of your data asset.

How it works:
  1. User types question in terminal
  2. Convert question to embedding (Bedrock Titan)
  3. Vector search MongoDB for relevant documents
  4. Also keyword search for specific tickers mentioned
  5. Build context from real verified data
  6. Claude Sonnet answers ONLY from that context
  7. If data not available → says so clearly, no making up

Key rule for Claude in this agent:
  System prompt must include:
  "You are grounded in real verified data.
   Never make up signals, returns, or dates.
   If the data does not contain the answer say:
   'I do not have data on this yet — we need
    more time collecting signals'
   Cite specific dates, numbers, and outcomes
   from the context provided."

Questions it should handle well:
  "How has NVDA performed in our signals?"
  "What was our accuracy last 90 days?"
  "When AI theme was hot which stocks benefited?"
  "Show me all signals where confidence was above 80%"
  "What did we miss and why?"
  "Which agent was most accurate — market or fundamentals?"
  "What happened last time fear greed was above 80?"
  "Compare NVDA vs AMD in our signal history"
  "What is our best performing time horizon?"
  "If I had followed every high-confidence BUY signal
   with $1000 what would I have made?"

Conversation memory:
  Keep last 10 messages in context
  User can ask follow-up questions naturally
  "Compare that to AMD" → agent remembers NVDA context

Run with:
  uv run python ask.py

---

## ITEM 11 — SIMPLE ACCURACY DASHBOARD
File to create: dashboard.py

Purpose:
  Terminal dashboard showing key metrics.
  Run anytime to see system health.
  No web UI needed — pure Python terminal output.

Display sections:

  SECTION 1 — SIGNAL ACCURACY
  ┌─────────────────────────────────────┐
  │ 📊 ACCURACY SCORECARD               │
  │ 30d:  Overall 63% │ High conf: 71% │
  │ 90d:  Overall 61% │ High conf: 68% │
  │ 180d: Overall 58% │ High conf: 64% │
  │ Total signals verified: 247         │
  │ 70% target: HIT on 30d high conf ✅ │
  └─────────────────────────────────────┘

  SECTION 2 — RECENT SIGNALS
  Last 10 signals with outcome if verified

  SECTION 3 — TOP PERFORMING AGENTS
  Which agent combination produces best signals

  SECTION 4 — CROSSOVER STATUS
  ┌─────────────────────────────────────┐
  │ 💰 CROSSOVER TRACKER                │
  │ Job income (3mo avg):  $X,XXX       │
  │ Side income (3mo avg): $XXX         │
  │ Gap remaining:         $X,XXX       │
  │ Crossover reached:     Not yet      │
  │ At current growth:     ~4.2 years   │
  └─────────────────────────────────────┘

  SECTION 5 — DATA HEALTH
  Total signals stored: XXX
  Days running: XXX
  MongoDB size: XXX MB
  Last agent run: X hours ago
  Next run: X hours from now

Run with:
  uv run python dashboard.py

---

## BUILD ORDER FOR CLAUDE IN VSCODE

Build in exactly this sequence.
Each item depends on the previous.

Step 1:
  Update db/collections.py
  Add new collection names and schemas
  Add price_at_signal to signal schema
  This must come first — everything writes to DB

Step 2:
  Create tools/google_trends.py
  Add pytrends to pyproject.toml
  Run uv sync
  Test with one keyword before moving on

Step 3:
  Create signal_verification_job.py
  This is the most critical file
  Test it runs without errors
  Verify it reads from signals collection correctly

Step 4:
  Create agents/sentiment.py
  Wire to existing MCP tools
  Add to agents/__init__.py

Step 5:
  Create agents/narrative_cycle.py
  Uses google_trends tool from step 2
  Add to agents/__init__.py

Step 6:
  Update agents/causal_reasoning.py
  Add sentiment_alignment field to output
  Takes sentiment report as optional context

Step 7:
  Update agents/ranking.py
  Add narrative cycle phase to ranking logic
  Phase 1 themes boosted, Phase 2 flagged

Step 8:
  Update agents/crew.py
  Add sentiment and narrative agents to crew
  Ensure correct execution order

Step 9:
  Update run_schedule.py
  Add nightly verification at 23:00
  Add weekly sentiment snapshot
  Add monthly crossover prompt

Step 10:
  Create tools/crossover_tracker.py
  Simple income tracking over time

Step 11:
  Create ask.py
  RAG interface to MongoDB data
  Test with sample questions

Step 12:
  Create dashboard.py
  Terminal metrics display
  Test all sections render correctly

Step 13:
  Integration test
  Run full pipeline end to end:
    uv run python run_agent.py
    uv run python signal_verification_job.py
    uv run python dashboard.py
    uv run python ask.py

---

## KEY PRINCIPLES — REMIND CLAUDE IN VSCODE

1. NEVER break existing agent code
   All changes are additive

2. ALWAYS save price_at_signal when creating signals
   Without this verification is impossible

3. NEVER hallucinate in ask.py
   Ground every answer in real MongoDB data
   "I don't have data on this yet" is correct answer

4. ALL new files use same patterns as existing:
   - dotenv for secrets
   - pymongo for DB
   - langchain_aws for Bedrock
   - async/await throughout
   - logging not print (except dashboard and ask.py)

5. ERROR HANDLING everywhere
   Every external API call in try/except
   Agent continues if one tool fails
   Log errors, do not crash

6. uv for all package management
   Never use pip directly
   uv add package_name
   uv sync

7. The verification job is sacred
   It is the proof the system works
   It is the foundation of the 70% target
   It is the evidence for the crossover decision
   Make it bulletproof

---

## THE NORTH STAR — REMIND YOURSELF

This system exists for one purpose:

  Collect verified market intelligence data
  for 5-8 years until the crossover point —
  when side gig income exceeds full time salary
  for 3 consecutive months.

Every feature serves this goal.
Every brick builds this Rome.
The agent runs while you work.
The data compounds while you sleep.
The crossover happens when the math says so.
Not when the excitement says so.
The math.
```
