# Stock Intelligence Agent

A macro-intelligent stock investment research system. Every morning at 06:30 ET it:

1. **Scans world events** for market-moving themes (geopolitics, macro, tech shifts)
2. **Traces root causes** 3–4 levels deep using Ray Dalio / Soros frameworks
3. **Screens 500+ stocks** for theme alignment (quantitative + LLM-assisted)
4. **Deep-analyses top 20 candidates** (technical + sentiment + fundamentals + macro risk)
5. **Ranks picks by time horizon** (quarter / 1yr / 2yr / 5yr / 10yr)
6. **Delivers a report** via email (AWS SES), Slack, or terminal

The user never hard-codes stock names. The agent discovers opportunities autonomously.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Package manager | uv |
| Agent framework | CrewAI |
| LLM provider | AWS Bedrock (Claude Haiku + Sonnet) |
| Database | MongoDB Atlas (pymongo) |
| Tool servers | MCP Python SDK |
| Market data | Polygon.io |
| News | NewsAPI |
| Financials | SEC EDGAR + FMP |
| Macro data | FRED (St. Louis Fed) |
| Email delivery | AWS SES |

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) installed
- AWS account with Bedrock access (Claude models enabled in `us-east-1`)
- MongoDB Atlas cluster (free tier works)
- API keys: Polygon.io, NewsAPI

---

## Setup

### 1. Clone and install dependencies

```bash
cd stock_intelligence
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your real keys
```

Required keys in `.env`:

```bash
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
MONGO_URI=mongodb+srv://...
POLYGON_API_KEY=...
NEWS_API_KEY=...
SES_SENDER_EMAIL=you@domain.com
SES_RECIPIENT_EMAIL=you@domain.com
```

### 3. Enable Claude models in AWS Bedrock

Go to AWS Console → Bedrock → Model Access and request access to:
- `anthropic.claude-3-5-sonnet-20241022-v2:0`
- `anthropic.claude-3-haiku-20240307-v1:0`

### 4. Configure MongoDB Atlas

1. Create a free cluster at [mongodb.com/atlas](https://www.mongodb.com/atlas)
2. Create a database user and whitelist your IP
3. Copy the connection string to `MONGO_URI` in `.env`

---

## Running

### Run once (manual)

```bash
uv run python run_agent.py
```

### Run on schedule (06:30 ET weekdays)

```bash
uv run python run_schedule.py
```

Add `--now` to also run immediately on startup:

```bash
uv run python run_schedule.py --now
```

### Keep alive with tmux

```bash
tmux new-session -s stock-agent
uv run python run_schedule.py
# Ctrl+B, D to detach
```

---

## Configuration

Edit `config.yaml` to tune behaviour:

```yaml
screening:
  universe: "SP500"           # stock universe to screen
  max_candidates: 60          # stocks passing Stage 1
  max_deep_analyse: 20        # stocks getting 4-agent treatment

horizons:
  quarter: 5                  # top N picks per time horizon
  one_year: 5

delivery:
  method: email               # email | slack | terminal
```

---

## Architecture

```
World Events → Causal Analysis → Screener → Deep Analysis × N → Ranking → Report
     ↑                                              ↓
  NewsAPI                           Market Agent (Haiku)
  FRED                              News Agent (Haiku)
  Web search                        Fundamentals Agent (Sonnet)
                                    Geo/Macro Agent (Haiku)
```

Each agent runs on the appropriate Claude model:
- **Haiku**: fast structured tasks (technical, news, geo)
- **Sonnet**: complex reasoning (world events, causal, fundamentals, ranking)

All data is saved to MongoDB with a `run_id` per daily run, so you can query
the full history of analyses.

---

## MongoDB Collections

| Collection | Contents |
|-----------|---------|
| `world_themes` | Detected macro events with urgency scores |
| `causal_theses` | Root cause analyses + investment theses |
| `screener_results` | Daily screener output |
| `market_data` | Technical indicators per stock per run |
| `news_sentiment` | News scores, analyst ratings per stock |
| `fundamentals` | Income statements, ratios, filings |
| `geo_macro` | FRED data, geopolitical risk reports |
| `signals` | Final BUY/SELL/HOLD signals (the gold) |
| `final_reports` | Complete assembled reports |

Query today's signals:
```python
from db import get_collection
signals = list(get_collection("signals").find({"run_id": "<run_id>", "signal": "BUY"}))
```

---

## Testing

```bash
uv run pytest tests/ -v
```

---

## MCP Servers

The three MCP servers (`market_mcp`, `intelligence_mcp`, `mongo_mcp`) can also
be run standalone for debugging:

```bash
uv run python mcp_servers/market_mcp.py       # starts MCP stdio server
uv run python mcp_servers/intelligence_mcp.py
uv run python mcp_servers/mongo_mcp.py
```

---

## Delivery Methods

**Email** (default): set `delivery.method: email` in `config.yaml`, requires SES setup.

**Slack**: set `delivery.method: slack`, set `SLACK_WEBHOOK_URL` in `.env`.

**Terminal**: set `delivery.method: terminal` — prints JSON to stdout. Good for testing.

---

## Linting

```bash
uv run ruff check .
uv run ruff format .
```
