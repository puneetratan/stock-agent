# CLAUDE.md
# Project rules, architecture, conventions, and repo map
# Claude in VSCode reads this before touching ANY file
# Last updated: 2026
# Version: 1.0

---

## WHAT THIS PROJECT IS

Stock Intelligence Agent — a macro-intelligent investment
research system that:
  - Runs automatically every morning at 06:30
  - Scans global world events and traces root causes
  - Screens 500+ stocks down to 20-25 candidates
  - Deep analyses candidates with 8 specialist agents
  - Ranks picks across 5 time horizons (quarter to 10 years)
  - Stores EVERYTHING in MongoDB Atlas (data is the asset)
  - Verifies every signal at 30/90/180 days (builds proof)
  - Targets 70% signal accuracy on high-confidence picks
  - Runs for 5-8 years until crossover point is reached

## THE NORTH STAR
Every line of code in this project serves one goal:

  Build a verified market intelligence database
  consistently for 5-8 years until side income
  exceeds full time salary for 3 consecutive months.

When making any decision ask:
  "Does this serve the 5-8 year data collection goal?"
  If yes → do it
  If no  → question whether it is needed

Consistency beats cleverness.
Simple beats complex.
Working beats perfect.
Verified data beats unverified assumption.

---

## ARCHITECTURE RULES

### The Sacred Rules — Never Break These

RULE 1: Every agent loads its skill file FIRST
  Before any analysis runs
  Before any LLM call is made
  The skill file IS the agent's analytical framework
  ```python
  def __init__(self):
      self.skill = load_skill("agent_name")  # ALWAYS FIRST
      self.llm   = get_llm("model_name")
  ```

RULE 2: Every signal MUST save price_at_signal
  Without this signal verification cannot work
  Without verification there is no accuracy tracking
  Without accuracy there is no proof
  Without proof there is no product
  This field is non-negotiable in every signal document

RULE 3: Agents never write to MongoDB directly
  All DB writes go through mongo_mcp.py tools
  This keeps the data layer clean and consistent
  If an agent needs to save — call a mongo_mcp tool

RULE 4: MCP tools never call LLM
  MCP servers are data layer only
  Fetch → save raw → return processed
  No reasoning happens in MCP servers
  Reasoning happens in agents only

RULE 5: Never crash the whole run for one stock
  If NVDA analysis fails → log it → move to AAPL
  If one MCP tool fails → log it → agent continues
  Only abort entire run if:
    - World agent fails (no context for anything)
    - Causal agent fails (no thesis for screening)
    - MongoDB connection fails (nowhere to save)

RULE 6: Output schema must never change silently
  If you change an agent output schema:
    - Update the skill file schema section
    - Update the Pydantic model in models/
    - Update the mongo_mcp save function
    - Add a migration note in CLAUDE.md changelog
  Breaking schema = breaking 5 years of data consistency

RULE 7: All configuration in config.yaml
  No hardcoded values in agent code
  No hardcoded model IDs
  No hardcoded API keys
  No hardcoded collection names
  Everything configurable without touching code

### Agent Architecture Rules

Each agent follows this exact pattern:
```python
class AgentName:

    def __init__(self):
        # 1. Load skill (always first)
        self.skill = load_skill("skill_name")
        # 2. Get LLM from factory
        self.llm = get_llm("agent_name_from_config")
        # 3. Set up logging
        self.logger = logging.getLogger(__name__)

    def run(self, input_data: dict) -> dict:
        try:
            # 4. Build prompt with skill prepended
            prompt = self._build_prompt(input_data)
            # 5. Call LLM
            response = self.llm.invoke(prompt)
            # 6. Parse and validate output
            result = self._parse_and_validate(response)
            # 7. Return structured dict
            return result
        except Exception as e:
            self.logger.error(f"[AgentName] Failed: {e}")
            return self._empty_result(error=str(e))

    def _build_prompt(self, input_data: dict) -> str:
        return f"""
        {self.skill}

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        NOW APPLY YOUR SKILL TO THIS DATA:
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        {json.dumps(input_data, indent=2)}

        Follow your skill framework exactly.
        Return valid JSON matching the schema in your skill.
        """

    def _parse_and_validate(self, response) -> dict:
        # Extract JSON from response
        # Validate against Pydantic model
        # Raise if schema mismatch
        pass

    def _empty_result(self, error: str) -> dict:
        # Return minimum valid structure on failure
        # So downstream agents do not crash
        pass
```

### MCP Server Architecture Rules

Each MCP tool follows this exact pattern:
```python
@mcp.tool()
async def tool_name(param: str) -> dict:
    """
    Tool description — what it fetches and where from.
    """
    try:
        # Step 1: Fetch from external API
        raw_data = await fetch_from_api(param)

        # Step 2: Save raw data to MongoDB
        await save_raw_to_mongo(
            collection=COLLECTION_NAME,
            data={
                "source":     "api_name",
                "param":      param,
                "raw":        raw_data,
                "fetched_at": datetime.utcnow(),
                "run_id":     current_run_id()
            }
        )

        # Step 3: Process and return to agent
        return process(raw_data)

    except ExternalAPIError as e:
        logger.error(f"[MCP:tool_name] API failed: {e}")
        return None   # Agent handles None gracefully

    except MongoError as e:
        logger.error(f"[MCP:tool_name] DB save failed: {e}")
        return process(raw_data)   # Still return data even if save failed
```

---

## NAMING CONVENTIONS

### Files and Folders
```
agents/world_intelligence.py    snake_case always
agents/causal_reasoning.py      snake_case always
mcp_servers/market_mcp.py       snake_case always
tools/skill_loader.py           snake_case always
skills/causal_reasoning.md      snake_case matches agent name
tests/test_skill_loader.py      test_ prefix always
```

### Classes
```python
class WorldIntelligenceAgent:   # PascalCase + Agent suffix
class CausalReasoningAgent:     # PascalCase + Agent suffix
class MarketMCPServer:          # PascalCase + MCPServer suffix
class SignalVerificationJob:    # PascalCase + Job suffix
class SkillLoader:              # PascalCase for utilities
```

### Functions
```python
def load_skill():               # snake_case always
def get_price_history():        # snake_case always
def run_verification_job():     # snake_case always
def build_analysis_crew():      # snake_case always
async def save_signal():        # async prefix for async functions
```

### Variables
```python
skill_content = ""              # snake_case for local vars
mongo_uri = ""                  # snake_case for instance vars
POLYGON_API_KEY = ""            # UPPER_SNAKE for env vars
MAX_CANDIDATES = 60             # UPPER_SNAKE for module constants
run_id = generate_run_id()      # snake_case for runtime vars
```

### MongoDB Collections
Always use constants from db/collections.py
Never use raw strings in agent or MCP code:
```python
# WRONG — never do this
db["signals"].insert_one(doc)

# RIGHT — always do this
from db.collections import SIGNALS
db[SIGNALS].insert_one(doc)
```

### Run ID Format
```
YYYYMMDD_HHMMSS_XXXX
20260427_063000_a3f9
```
Generated ONCE in run_agent.py at startup.
Passed to all agents and MCP servers via context.
Every MongoDB document includes run_id.

---

## REPO MAP

```
stock_intelligence/               ← project root
│
├── CLAUDE.md                     ← YOU ARE HERE
│                                   Read before touching anything
│
├── pyproject.toml                ← dependencies (uv only)
├── uv.lock                       ← commit this (reproducible)
├── .env                          ← secrets (NEVER commit)
├── .env.example                  ← template (commit this)
├── .gitignore                    ← standard Python gitignore
├── config.yaml                   ← all configuration
├── README.md                     ← setup instructions
│
├── run_agent.py                  ← MAIN ENTRY POINT
│                                   python run_agent.py
│                                   Runs full daily analysis
│
├── run_schedule.py               ← SCHEDULER
│                                   python run_schedule.py
│                                   Runs continuously, triggers jobs
│
├── signal_verification_job.py    ← NIGHTLY VERIFIER
│                                   Checks signals at 30/90/180d
│                                   Calculates accuracy scorecard
│                                   THE MOST CRITICAL FILE
│
├── ask.py                        ← RAG TERMINAL INTERFACE
│                                   python ask.py
│                                   Talk to your MongoDB data
│
├── dashboard.py                  ← METRICS TERMINAL VIEW
│                                   python dashboard.py
│                                   See system health at a glance
│
├── agents/                       ← ALL AGENT DEFINITIONS
│   ├── __init__.py
│   ├── crew.py                   ← CrewAI crew wiring
│   │                               Defines execution order
│   │                               Passes context between agents
│   │
│   ├── world_intelligence.py     ← Agent 1: scans global events
│   ├── causal_reasoning.py       ← Agent 2: root cause WHY
│   │                               (most important agent)
│   ├── sentiment.py              ← Agent 3: fear/greed/emotions
│   ├── narrative_cycle.py        ← Agent 4: hype cycle detection
│   ├── screener.py               ← Agent 5: 500+ → 20-25 stocks
│   ├── market.py                 ← Agent 6: technicals per stock
│   ├── news.py                   ← Agent 7: sentiment per stock
│   ├── fundamentals.py           ← Agent 8: financials per stock
│   ├── ranking.py                ← Agent 9: final picks by horizon
│   └── geo/                      ← Geo agents by region
│       ├── __init__.py
│       ├── us_macro.py
│       ├── europe_macro.py
│       ├── asia_macro.py
│       └── middle_east.py
│
├── mcp_servers/                  ← MCP SERVER DEFINITIONS
│   │                               These are data fetchers
│   │                               Not agents — no LLM calls here
│   │
│   ├── market_mcp.py             ← Wraps Polygon.io
│   │                               price, RSI, MACD, volume,
│   │                               options flow, screener
│   │
│   ├── intelligence_mcp.py       ← Wraps NewsAPI + FRED +
│   │                               SEC EDGAR + FMP + web search
│   │
│   └── mongo_mcp.py              ← Wraps MongoDB Atlas
│                                   all read/write operations
│
├── tools/                        ← UTILITY FUNCTIONS
│   ├── __init__.py
│   ├── skill_loader.py           ← loads skill files
│   │                               used by every agent
│   │
│   ├── bedrock.py                ← LLM factory
│   │                               get_llm("agent_name")
│   │                               returns correct model
│   │
│   ├── polygon.py                ← Polygon.io REST client
│   ├── news_api.py               ← NewsAPI client
│   ├── edgar.py                  ← SEC EDGAR client
│   ├── fred.py                   ← FRED macro data client
│   ├── ecb.py                    ← ECB API client
│   ├── eia.py                    ← EIA energy API client
│   ├── worldbank.py              ← World Bank API client
│   ├── alpha_vantage.py          ← global stock data client
│   ├── google_trends.py          ← sentiment data (pytrends)
│   ├── delivery.py               ← email via AWS SES / Gmail
│   └── crossover_tracker.py      ← income line tracker
│
├── db/                           ← DATABASE LAYER
│   ├── __init__.py
│   ├── client.py                 ← MongoDB Atlas connection
│   │                               single connection shared
│   └── collections.py            ← collection name constants
│                                   NEVER hardcode names elsewhere
│
├── models/                       ← PYDANTIC DATA MODELS
│   ├── __init__.py               ← validates agent outputs
│   ├── signal.py                 ← Signal (BUY/SELL/HOLD)
│   ├── theme.py                  ← Theme (world event)
│   ├── causal.py                 ← CausalThesis
│   ├── sentiment.py              ← SentimentReport
│   ├── screener.py               ← ScreenerResult
│   ├── stock_analysis.py         ← FullStockAnalysis
│   └── report.py                 ← FinalReport
│
├── skills/                       ← AGENT SKILL FILES
│   │                               YOUR INTELLECTUAL PROPERTY
│   │                               Commit to private repo
│   │                               Refine over 5-8 years
│   │                               These ARE the competitive moat
│   │
│   ├── world_intelligence.md
│   ├── causal_reasoning.md       ← most important
│   ├── sentiment.md
│   ├── narrative_cycle.md
│   ├── screener.md
│   ├── market_analysis.md
│   ├── news_analysis.md
│   ├── fundamentals_analysis.md
│   ├── geo_analysis.md
│   └── ranking.md
│
└── tests/                        ← TEST SUITE
    ├── __init__.py
    ├── conftest.py               ← shared fixtures
    ├── test_skill_loader.py
    ├── test_verification.py
    ├── test_agents.py
    ├── test_mcp_servers.py
    └── test_tools.py
```

---

## TEST CONVENTIONS

### Test Naming
```python
# File:     test_{module}.py
# Function: test_{function}_{scenario}_{expected_outcome}()

def test_load_skill_returns_full_content():
def test_load_skill_raises_when_file_missing():
def test_verify_signal_marks_buy_correct_when_price_rises():
def test_verify_signal_marks_buy_incorrect_when_price_falls():
def test_screener_rejects_penny_stocks():
def test_screener_rejects_low_volume_stocks():
```

### Test Structure — AAA Pattern Always
```python
def test_signal_correct_when_buy_and_price_rises():
    # ── Arrange ──────────────────────────────────────────
    signal = {
        "ticker":          "NVDA",
        "signal":          "BUY",
        "price_at_signal": 850.00,
        "confidence":      84,
        "date":            datetime(2026, 1, 15)
    }
    price_30_days_later = 940.00

    # ── Act ──────────────────────────────────────────────
    result = calculate_signal_outcome(signal, price_30_days_later, days=30)

    # ── Assert ───────────────────────────────────────────
    assert result["signal_correct_30d"] is True
    assert result["return_30d_pct"] == pytest.approx(10.59, rel=0.01)
    assert result["verified_30d"] is True
```

### What To Test
```
ALWAYS test:
  ✓ tools/skill_loader.py      — loads files, handles missing
  ✓ signal_verification_job.py — correct/incorrect calculation
  ✓ db/collections.py          — constants exist and are strings
  ✓ tools/crossover_tracker.py — crossover detection logic
  ✓ models/*.py                — Pydantic validation works

MOCK and test:
  ✓ MCP servers                — mock external APIs
  ✓ Agent output parsing       — mock LLM response

NEVER test:
  ✗ LLM output quality         — non-deterministic
  ✗ Live external APIs         — use mocks
  ✗ MongoDB in unit tests      — use mongomock or fixtures
```

### Running Tests
```bash
uv run pytest tests/ -v
uv run pytest tests/ -v --tb=short
uv run pytest tests/test_verification.py -v    # one file
uv run pytest -k "test_signal" -v              # by name pattern
```

---

## ENVIRONMENT AND PACKAGE RULES

### Package Management — uv ONLY
```bash
# Install all dependencies
uv sync

# Add a new package
uv add package_name

# Add dev-only package
uv add --dev package_name

# Run any script
uv run python run_agent.py
uv run python ask.py
uv run pytest tests/

# NEVER use pip directly in this project
```

### Environment Variables
All secrets in .env — never in code:
```bash
# AWS
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1

# MongoDB
MONGO_URI=mongodb+srv://...

# APIs
POLYGON_API_KEY=
NEWS_API_KEY=

# Delivery
SES_SENDER_EMAIL=
SES_RECIPIENT_EMAIL=

# Gmail (alternative to SES)
GMAIL_USER=
GMAIL_APP_PASSWORD=
```

Load in every file that needs them:
```python
from dotenv import load_dotenv
import os
load_dotenv()
KEY = os.getenv("KEY_NAME")
```

### Git Rules
```
NEVER commit:     .env, *.pyc, __pycache__
ALWAYS commit:    uv.lock, CLAUDE.md, skills/*.md, config.yaml
PRIVATE REPO:     This entire project is private
                  skills/ contains your IP
```

---

## ERROR HANDLING RULES

### Logging Pattern
```python
import logging
logger = logging.getLogger(__name__)

# Use these levels consistently:
logger.debug("Detailed flow information")
logger.info("Normal operation milestones")
logger.warning("Something unexpected but recoverable")
logger.error("Something failed — investigate")
logger.critical("System cannot continue — abort run")
```

### Error Escalation
```
Level 1 — Skip and continue (most errors):
  One stock analysis fails → log → next stock

Level 2 — Save error and continue (tool failures):
  One MCP tool fails → log → agent returns partial result
  Save error to MongoDB errors collection

Level 3 — Abort run (critical failures):
  MongoDB connection fails → cannot save anything → abort
  World agent fails → no context → abort
  Causal agent fails → no thesis → abort
  All other agents → skip and continue
```

### Error Document Schema
Every error saved to MongoDB errors collection:
```python
{
    "run_id":       current_run_id,
    "timestamp":    datetime.utcnow(),
    "agent":        "agent_name",
    "error_type":   "ExceptionClassName",
    "error_msg":    str(exception),
    "ticker":       "NVDA or None",
    "recoverable":  True|False
}
```

---

## EXECUTION ORDER

The daily run executes agents in this exact order.
Do not change this order without updating CLAUDE.md.

```
06:30 DAILY RUN (run_agent.py)
  │
  ├─ 1. Validate skill files exist (all 10)
  ├─ 2. Generate run_id
  ├─ 3. Start MCP servers
  │
  ├─ 4. WorldIntelligenceAgent.scan()
  │      → themes saved to MongoDB
  │
  ├─ 5. CausalReasoningAgent.analyse(themes)
  │      → causal theses saved to MongoDB
  │
  ├─ 6. SentimentAgent.scan()           ← parallel with causal
  │      → sentiment saved to MongoDB
  │
  ├─ 7. NarrativeCycleAgent.detect(themes, sentiment)
  │      → cycle phases saved to MongoDB
  │
  ├─ 8. ScreenerAgent.screen(theses, sentiment, cycles)
  │      → 20-25 candidates returned
  │
  ├─ 9. FOR EACH candidate ticker:
  │      ├─ MarketAgent.analyse(ticker)      ─┐ parallel
  │      ├─ NewsAgent.analyse(ticker)         │
  │      ├─ FundamentalsAgent.analyse(ticker, news_report)
  │      └─ GeoAgent.analyse(ticker, all_reports, theses)
  │
  ├─ 10. RankingAgent.rank(all_analyses, theses, sentiment)
  │       → final report saved to MongoDB
  │
  └─ 11. DeliveryAgent.send(report)
          → ONE email sent (dedup guard prevents duplicates)

23:00 NIGHTLY VERIFICATION (signal_verification_job.py)
  ├─ Check all signals due at 30d
  ├─ Check all signals due at 90d
  ├─ Check all signals due at 180d
  └─ Calculate and save accuracy scorecard

SUNDAY 08:00 WEEKLY SENTIMENT SNAPSHOT
  └─ Run SentimentAgent standalone
     Save fear/greed snapshot to sentiment_history

1ST OF MONTH 09:00 CROSSOVER CHECK
  ├─ Prompt user for job income this month
  ├─ Calculate portfolio return this month
  └─ Update crossover_data collection
```

---

## MONGODB COLLECTIONS REFERENCE

All defined in db/collections.py.
Use constants — never raw strings.

```python
# Core signal collections
SIGNALS              = "signals"
ACCURACY_SCORECARD   = "accuracy_scorecard"

# World intelligence
WORLD_THEMES         = "world_themes"
CAUSAL_THESES        = "causal_theses"

# Sentiment
SENTIMENT_HISTORY    = "sentiment_history"
NARRATIVE_CYCLES     = "narrative_cycles"
GOOGLE_TRENDS        = "google_trends_history"

# Per-stock analysis
MARKET_DATA          = "market_data"
NEWS_SENTIMENT       = "news_sentiment"
FUNDAMENTALS         = "fundamentals"
GEO_MACRO            = "geo_macro"

# Screener
SCREENER_RESULTS     = "screener_results"

# Global macro
REGIONAL_MACRO       = "regional_macro"
SUPPLY_CHAIN_RISKS   = "supply_chain_risks"
CURRENCY_WAR         = "currency_war"
COMMODITIES          = "commodities"
GEOPOLITICAL_RISK    = "geopolitical_risk"

# System
ERRORS               = "errors"
RUN_LOG              = "run_log"
CROSSOVER_DATA       = "crossover_data"
DELIVERY_LOG         = "delivery_log"    ← dedup guard for emails

# Vector search
EMBEDDINGS           = "embeddings"
```

### Required Fields In Every Document
```python
{
    "run_id":        str,        # YYYYMMDD_HHMMSS_XXXX
    "created_at":    datetime,   # UTC always
    "agent_version": str,        # from config.yaml
    # ... all other fields
}
```

### Signal Document — Special Required Fields
```python
{
    "run_id":           str,
    "created_at":       datetime,
    "ticker":           str,
    "signal":           str,    # "BUY" | "SELL" | "HOLD"
    "confidence":       int,    # 0-100
    "price_at_signal":  float,  # CRITICAL — never omit
    "horizon":          str,    # "quarter|1yr|2yr|5yr|10yr"
    "causal_theme":     str,    # theme_id driving this signal
    "agent_agreement":  str,    # "5/5|4/5|3/5|2/5|1/5"
    "thesis":           str,
    "key_risk":         str,
    # Verification fields (added by verification job later)
    "verified_30d":     bool,   # added at day 30
    "price_30d_later":  float,
    "return_30d_pct":   float,
    "signal_correct_30d": bool,
    # ... same for 90d and 180d
}
```

---

## SKILL FILES REFERENCE

Location: skills/
Purpose: Agent analytical protocols
Rule: Never modify skill files mid-run
Rule: When modifying — version the change in changelog below
Rule: Commit skill files to private repo — they are your IP

```
skills/world_intelligence.md    → WorldIntelligenceAgent
skills/causal_reasoning.md      → CausalReasoningAgent
skills/sentiment.md             → SentimentAgent
skills/narrative_cycle.md       → NarrativeCycleAgent
skills/screener.md              → ScreenerAgent
skills/market_analysis.md       → MarketAgent
skills/news_analysis.md         → NewsAgent
skills/fundamentals_analysis.md → FundamentalsAgent
skills/geo_analysis.md          → GeoAgent
skills/ranking.md               → RankingAgent
```

---

## CHANGELOG
Track every meaningful change here.
Especially schema changes that affect MongoDB consistency.

```
v1.0 — 2026-04-27
  Initial project scaffold
  9 core agents
  3 MCP servers
  Signal verification job
  10 skill files

v1.1 — 2026-05-03
  Integrated skills/*.md with all agents via tools/skill_loader.py
  Every agent now loads its skill in __init__ before any LLM call
  crew.py injects market/news/fundamentals/geo skills at task build time
  run_agent.py validates all 10 skill files exist at startup

  Fixed delivery dedup: deliver_report() now checks delivery_log
  collection — guarantees exactly 1 email per run_id regardless of
  how many scripts (run_agent, resume_from_ticker, finalize_run) call it
  Added DELIVERY_LOG collection constant to db/collections.py

  Fixed WorldIntelligenceAgent JSON parsing: added _parse_json_tolerant()
  to recover partial themes from truncated LLM responses (token limit)

  Improved ask.py context routing: keyword detection now routes to
  correct collections (world_themes, causal_theses, screener_results,
  narrative_cycles for trend/theme questions; market_data/fundamentals/
  geo_macro for ticker-specific technical/fundamental/geo questions)

v1.2 — 2026-05-03
  Politician trade intelligence layer added (FEED_AUTOPILOT_POLITICIAN)

  db/collections.py: added POLITICIAN_TRADES and SKILL_SUGGESTIONS
  collections; added 4 indexes for politician_trades (ticker+date,
  politician, signal_strength, fetched_at)

  mcp_servers/intelligence_mcp.py: added get_politician_trades(days=45)
  Fetches House and Senate disclosures from public S3 buckets
  Enriches with committee mapping, sector relevance, disclosure delay,
  signal strength scoring, and cluster detection (3+ same sector)
  Saves enriched trades to politician_trades collection

  skills/world_intelligence.md: added STEP 6 — POLITICIAN TRADE SCAN
  Committee interpretation table (10 committees → sectors)
  Signal scoring by disclosure delay, cross-party upgrade rule
  Clustering detection protocol
  Added politician_signals and politician_clustering to OUTPUT SCHEMA
  Added politician checklist items to QUALITY CHECKLIST

  skills/causal_reasoning.md: added STEP 9 — POLITICIAN CROSS-REFERENCE
  Committee interpretation table for thesis confirmation
  Confidence delta rules: +15/+5 for confirms, -30/-10 for contradicts
  Cross-party cluster bonus (+10) and penalty (-10)
  Added politician_confirmation object to OUTPUT SCHEMA
  Confidence score now applied AFTER politician delta
  ANALYTICAL FRAMEWORK updated to "ALL 9 steps"
```

---

## QUICK REFERENCE — COMMON COMMANDS

```bash
# Setup (first time)
uv sync
cp .env.example .env
# edit .env with your keys

# Daily development
uv run python run_agent.py        # run full agent
uv run python ask.py              # talk to your data
uv run python dashboard.py        # see metrics
uv run python signal_verification_job.py  # check accuracy

# Scheduler (leave running in tmux)
uv run python run_schedule.py     # runs all scheduled jobs

# Testing
uv run pytest tests/ -v           # all tests
uv run pytest tests/ -v -k "skill"  # filter by name

# Package management
uv add requests                   # add dependency
uv add --dev pytest-mock          # add dev dependency
uv sync                           # install all

# Linting
uv run ruff check .               # check issues
uv run ruff check . --fix         # auto fix

# Monitoring a run
tail -f run_20260503_manual.log   # follow live output
cat current_run.json              # see active run_id and PID
```

---

## IF YOU ARE CLAUDE IN VSCODE READING THIS

You now understand:
  What this project does (5-8 year data collection)
  Where everything lives (repo map above)
  How it must be built (architecture rules)
  How to name things (naming conventions)
  How to test things (test conventions)
  How errors are handled (error rules)
  What order things execute (execution order)
  What goes in MongoDB (collections reference)
  Where the skill files are (skills/)

Before touching any file:
  1. Check the repo map — does this file already exist?
  2. Check naming conventions — am I naming correctly?
  3. Check architecture rules — am I following the patterns?
  4. Check the north star — does this serve the 5-8 year goal?

The most important files in order:
  1. signal_verification_job.py   (proof the system works)
  2. skills/*.md                  (how agents think)
  3. agents/causal_reasoning.py   (most important agent)
  4. db/collections.py            (data consistency foundation)

When in doubt: simple, consistent, and working
beats clever, complex, and fragile.
Every time. For a system running 5-8 years.
```
