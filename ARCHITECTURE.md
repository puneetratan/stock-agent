# System Architecture — CLAUDE.md & Skill Files Integration

---

## 1. Two-Layer Intelligence System

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TWO INTELLIGENCE LAYERS                       │
│                                                                      │
│   LAYER 1 — BUILD TIME (for Claude in VSCode)                        │
│   ┌──────────────────────────────────────────────────────┐          │
│   │  CLAUDE.md                                           │          │
│   │  • Architecture rules                               │          │
│   │  • Naming conventions                               │          │
│   │  • Sacred rules (never break these)                 │          │
│   │  • Repo map                                         │          │
│   │  • MongoDB schema                                   │          │
│   │  Read by: Claude (you) when writing/editing code    │          │
│   └──────────────────────────────────────────────────────┘          │
│                                                                      │
│   LAYER 2 — RUN TIME (for LLM agents during analysis)               │
│   ┌──────────────────────────────────────────────────────┐          │
│   │  skills/*.md  (10 files)                            │          │
│   │  • Professional identity                            │          │
│   │  • Step-by-step analytical protocol                 │          │
│   │  • Historical parallel database                     │          │
│   │  • Output schema the agent must return              │          │
│   │  • Quality checklist                                │          │
│   │  Loaded by: each agent before every LLM call        │          │
│   └──────────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Skill Loading — How It Works

```
                    AGENT STARTUP
                         │
                         ▼
              ┌──────────────────────┐
              │   Agent.__init__()   │
              │                      │
              │  self.skill =        │
              │  load_skill(         │
              │  "causal_reasoning"  │
              │  )                   │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  skill_loader.py     │
              │                      │
              │  SKILLS_DIR /        │
              │  causal_reasoning.md │
              │  → read file         │
              │  → return string     │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  self.skill =        │
              │  "# CAUSAL           │
              │   REASONING SKILL    │
              │   ## YOUR IDENTITY   │
              │   You are a Macro    │
              │   Causal Analyst...  │
              │   ## 8-STEP PROTOCOL │
              │   ## OUTPUT SCHEMA   │
              │   ## QUALITY CHECK"  │
              └──────────────────────┘
                   held in memory
                   for entire run
```

---

## 3. How Skill Becomes the LLM Prompt

```
              _build_crew() called with live data
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│  TASK DESCRIPTION sent to LLM (what the model actually sees)│
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SKILL FILE CONTENT  (from skills/causal_reasoning.md)│  │
│  │                                                      │  │
│  │  # CAUSAL REASONING SKILL                           │  │
│  │  ## YOUR IDENTITY                                   │  │
│  │  You are a Macro Causal Analyst. You think like     │  │
│  │  Ray Dalio and George Soros combined...             │  │
│  │                                                      │  │
│  │  ## ANALYTICAL FRAMEWORK                            │  │
│  │  STEP 1 — SURFACE NARRATIVE                         │  │
│  │  STEP 2 — ROOT CAUSE IDENTIFICATION                 │  │
│  │  STEP 3 — HISTORICAL PARALLEL DATABASE              │  │
│  │    ▸ Petrodollar: Nixon 1971...                     │  │
│  │    ▸ Trade war: US-Japan 1980s...                   │  │
│  │  STEP 4 — CAUSAL CHAIN (3-5 levels)                 │  │
│  │  STEP 5 — SECOND ORDER PLAYS                        │  │
│  │  STEP 6 — CONTRARIAN CHECK                          │  │
│  │  STEP 7 — TIME-BUCKETED THESIS (5 horizons)         │  │
│  │  STEP 8 — RISK FLAGS                                │  │
│  │                                                      │  │
│  │  ## OUTPUT SCHEMA  { ... }                          │  │
│  │  ## QUALITY CHECKLIST                               │  │
│  └──────────────────────────────────────────────────────┘  │
│                         +                                  │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                     │
│  NOW APPLY YOUR SKILL TO THIS THEME:                       │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                     │
│                         +                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  LIVE DATA  (fetched this run)                       │  │
│  │                                                      │  │
│  │  THEME: IRAN_OIL_BLOCKADE_CRISIS                    │  │
│  │  Urgency: 9/10                                      │  │
│  │  Summary: Iran threatening to close Strait...       │  │
│  │  Evidence: ["Reuters: Iran blockade...", ...]       │  │
│  │                                                      │  │
│  │  MACRO CONTEXT:                                     │  │
│  │  DXY: 104.2                                         │  │
│  │  Fed Funds: 4.75%                                   │  │
│  │  Yield Curve: -0.3%                                 │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
                    LLM RESPONSE
                  (follows the schema
                   defined in skill)
```

---

## 4. Full Daily Run — Sequence Diagram

```
run_agent.py          skill_loader.py       Agent              LLM            MongoDB
     │                      │                 │                  │                │
     │  validate_skills()   │                 │                  │                │
     │─────────────────────►│                 │                  │                │
     │  ✓ all 10 exist      │                 │                  │                │
     │◄─────────────────────│                 │                  │                │
     │                      │                 │                  │                │
     │── STEP 1 ─────────────────────────────►│                  │                │
     │  WorldIntelligenceAgent()               │                  │                │
     │                      │  load_skill(    │                  │                │
     │                      │  "world_intel") │                  │                │
     │                      │────────────────►│                  │                │
     │                      │  skill string   │                  │                │
     │                      │◄────────────────│                  │                │
     │                      │  self.skill ✓   │                  │                │
     │                      │                 │  fetch_news()    │                │
     │                      │                 │─────────────────►│                │
     │                      │                 │  headlines       │                │
     │                      │                 │◄─────────────────│                │
     │                      │                 │                  │                │
     │                      │                 │  skill + data    │                │
     │                      │                 │─────────────────►│                │
     │                      │                 │  8-12 themes JSON│                │
     │                      │                 │◄─────────────────│                │
     │                      │                 │                  │  save themes   │
     │                      │                 │─────────────────────────────────►│
     │  themes[]            │                 │                  │  world_themes  │
     │◄────────────────────────────────────────│                  │                │
     │                      │                 │                  │                │
     │── STEP 2 ─────────────────────────────►│                  │                │
     │  CausalReasoningAgent() × N themes      │                  │                │
     │                      │  load_skill(    │                  │                │
     │                      │  "causal_reason")                  │                │
     │                      │────────────────►│                  │                │
     │                      │                 │  skill+theme data│                │
     │                      │                 │─────────────────►│                │
     │                      │                 │  causal thesis   │                │
     │                      │                 │◄─────────────────│                │
     │                      │                 │                  │  save thesis   │
     │                      │                 │─────────────────────────────────►│
     │                      │                 │                  │  causal_theses │
     │  theses[]            │                 │                  │                │
     │◄────────────────────────────────────────│                  │                │
     │                      │                 │                  │                │
     │── STEP 3 ────────────────────── SentimentAgent ──────────────────────────►│
     │── STEP 4 ────────────────────── NarrativeCycleAgent ─────────────────────►│
     │── STEP 5 ────────────────────── ScreenerAgent ────────────────────────────►│
     │                      │                 │                  │  screener_res  │
     │  candidates[]        │                 │                  │                │
     │◄────────────────────────────────────────│                  │                │
     │                      │                 │                  │                │
     │── STEP 6 — FOR EACH TICKER ────────────►│                  │                │
     │  build_analysis_crew()                  │                  │                │
     │                      │  load_skill(    │                  │                │
     │                      │  "market_anal") │                  │                │
     │                      │  load_skill(    │                  │                │
     │                      │  "news_anal")   │                  │                │
     │                      │  load_skill(    │                  │                │
     │                      │  "fund_anal")   │                  │                │
     │                      │  load_skill(    │                  │                │
     │                      │  "geo_anal")    │                  │                │
     │                      │                 │                  │                │
     │                      │     ┌───────────┤                  │                │
     │                      │     │MarketAgent│ skill+price data  │                │
     │                      │     │           │─────────────────►│                │
     │                      │     │           │ technical report │                │
     │                      │     │           │◄─────────────────│                │
     │                      │     ├───────────┤                  │  market_data   │
     │                      │     │NewsAgent  │ skill+headlines  │                │
     │                      │     │           │─────────────────►│                │
     │                      │     │           │ sentiment report │                │
     │                      │     │           │◄─────────────────│  news_sentiment│
     │                      │     ├───────────┤                  │                │
     │                      │     │FundAgent  │ skill+financials │                │
     │                      │     │           │─────────────────►│                │
     │                      │     │           │ fundamentals     │                │
     │                      │     │           │◄─────────────────│  fundamentals  │
     │                      │     ├───────────┤                  │                │
     │                      │     │GeoAgent   │ skill+theses     │                │
     │                      │     │           │─────────────────►│                │
     │                      │     │           │ geo risk report  │                │
     │                      │     │           │◄─────────────────│  geo_macro     │
     │                      │     └───────────┘                  │                │
     │                      │                 │                  │                │
     │── STEP 7 ─────────────────────────────►│                  │                │
     │  RankingAgent()                         │                  │                │
     │                      │  load_skill(    │                  │                │
     │                      │  "ranking")     │                  │                │
     │                      │────────────────►│                  │                │
     │                      │                 │  reads ALL       │                │
     │                      │                 │  collections ────────────────────►│
     │                      │                 │  for this run_id │  read all      │
     │                      │                 │◄─────────────────────────────────│
     │                      │                 │  skill+all data  │                │
     │                      │                 │─────────────────►│                │
     │                      │                 │  final report    │                │
     │                      │                 │◄─────────────────│                │
     │                      │                 │                  │  signals       │
     │                      │                 │─────────────────────────────────►│
     │  FinalReport         │                 │                  │                │
     │◄────────────────────────────────────────│                  │                │
     │                      │                 │                  │                │
     │── STEP 8 ────────────────────────────────────────────────────────────────►│
     │  deliver_report()                        delivery_log (dedup guard)        │
     │  → ONE email to you ✉️                                                      │
```

---

## 5. Skill File Anatomy

```
skills/causal_reasoning.md
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  ## YOUR IDENTITY          ← WHO the agent is            │
│  You are a Macro Causal    (replaces short _BACKSTORY    │
│  Analyst. You think like   string that was hardcoded)    │
│  Ray Dalio + George Soros  │
│                            │
│  ## ANALYTICAL FRAMEWORK   ← HOW the agent thinks       │
│  STEP 1 Surface Narrative  (the actual protocol it       │
│  STEP 2 Root Cause         must follow every run)        │
│  STEP 3 Historical DB      │
│    ▸ Petrodollar: 1971...  ← built-in reference library  │
│    ▸ Trade war: 1980s...   (no need to search for this)  │
│    ▸ Carry trade: LTCM...  │
│  STEP 4 Causal Chain       │
│  STEP 5 Second Order Plays │
│  STEP 6 Contrarian Check   │
│  STEP 7 5 Horizons         │
│  STEP 8 Risk Flags         │
│                            │
│  ## OUTPUT SCHEMA          ← WHAT the agent returns     │
│  { theme_id, root_cause,   (exact JSON MongoDB expects)  │
│    causal_chain, theses,   │
│    risk_flags, confidence} │
│                            │
│  ## QUALITY CHECKLIST      ← self-verification before   │
│  ✓ Historical parallel     returning (reduces bad output)│
│  ✓ 3-5 causal levels       │
│  ✓ Second order ≠ obvious  │
│  ✓ All 5 horizons filled   │
│  ✓ Valid JSON              │
└──────────────────────────────────────────────────────────┘
```

---

## 6. MongoDB — What Each Agent Writes

```
                          MongoDB Atlas
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
    world_themes         causal_theses      sentiment_history
    ─────────────        ─────────────      ─────────────────
    WorldAgent           CausalAgent        SentimentAgent
    • theme id           • root_cause       • fear_greed_score
    • urgency 1-10       • causal_chain     • market_emotion
    • status             • theses ×5        • smart_vs_dumb
    • evidence           • risk_flags       • contrarian_signal
    • run_id ✓           • run_id ✓         • run_id ✓
          │                    │                    │
    narrative_cycles     screener_results    market_data
    ────────────────     ────────────────    ───────────
    NarrativeAgent       ScreenerAgent       MarketAgent
    • current_phase      • ticker            • rsi, macd
    • phase_direction    • alignment_score   • technical_signal
    • action             • theme_alignment   • support/resist
    • run_id ✓           • run_id ✓          • run_id ✓
          │                    │                    │
    news_sentiment       fundamentals         geo_macro
    ──────────────       ────────────         ─────────
    NewsAgent            FundAgent            GeoAgent
    • sentiment_score    • revenue_growth     • relevant_theses
    • analyst_consensus  • gross_margin       • supply_chain_risk
    • narrative_shift    • business_quality   • override_flag
    • run_id ✓           • run_id ✓           • run_id ✓
          │                    │                    │
          └────────────────────┼────────────────────┘
                               │
                               ▼
                           signals
                          ─────────
                          RankingAgent reads ALL above
                          • ticker
                          • signal BUY/SELL/HOLD
                          • confidence 0-100
                          • price_at_signal  ← critical for verification
                          • horizon (quarter/1yr/2yr/5yr/10yr)
                          • agent_agreement (5/5, 4/5 etc)
                          • causal_theme
                          • run_id ✓
                               │
                               ▼
                       accuracy_scorecard
                      ──────────────────
                      signal_verification_job.py
                      runs nightly at 23:00
                      checks at 30d / 90d / 180d
                      • was signal_correct?
                      • return_pct achieved?
                      • builds proof over 5-8 years
```

---

## 7. CLAUDE.md vs Skills — Side by Side

```
┌──────────────────────────────┬──────────────────────────────┐
│         CLAUDE.md            │       skills/*.md            │
├──────────────────────────────┼──────────────────────────────┤
│ Read by: Claude (VSCode)     │ Read by: LLM agents at       │
│          when you ask it to  │          runtime during       │
│          write/edit code     │          daily analysis run   │
├──────────────────────────────┼──────────────────────────────┤
│ Loaded: once per conversation│ Loaded: once per agent init  │
│         automatically by IDE │         via load_skill()     │
├──────────────────────────────┼──────────────────────────────┤
│ Controls: HOW THE SYSTEM     │ Controls: HOW THE AGENTS     │
│           IS BUILT           │           THINK AND ANALYSE  │
├──────────────────────────────┼──────────────────────────────┤
│ Contains:                    │ Contains:                    │
│ • Sacred rules               │ • Expert identity            │
│ • File naming                │ • Analytical protocol        │
│ • Agent patterns             │ • Historical references      │
│ • MongoDB schemas            │ • Output schemas             │
│ • Execution order            │ • Quality checklists         │
├──────────────────────────────┼──────────────────────────────┤
│ Updated: when architecture   │ Updated: when analysis       │
│          changes             │          quality improves    │
│          (rare)              │          (regularly)         │
├──────────────────────────────┼──────────────────────────────┤
│ If missing: Claude makes     │ If missing: run_agent.py     │
│             bad code choices │             aborts at startup│
└──────────────────────────────┴──────────────────────────────┘
```

---

## 8. Startup Validation Flow

```
uv run python run_agent.py
         │
         ▼
  validate_skills()
         │
         ├─ world_intelligence.md  ✓
         ├─ causal_reasoning.md    ✓
         ├─ sentiment.md           ✓
         ├─ narrative_cycle.md     ✓
         ├─ screener.md            ✓
         ├─ market_analysis.md     ✓
         ├─ news_analysis.md       ✓
         ├─ fundamentals_analysis.md ✓
         ├─ geo_analysis.md        ✓
         └─ ranking.md             ✓
                   │
                   ▼ all present
         ✓ All 10 skill files loaded
                   │
                   ▼
           run continues...
                   │
           if ANY missing
                   │
                   ▼
         RuntimeError: Missing skill files: [...]
         → run aborts before wasting API calls
```
