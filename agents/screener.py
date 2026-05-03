"""
Agent 3 — Screener Agent.

Filters the stock universe in 3 stages:
  A) Quantitative hard rules (market cap, volume, price)
  B) Theme alignment (LLM-assisted: does this stock benefit?)
  C) Technical filter (RSI, 50-day MA, earnings proximity)
"""

import json
import uuid
from datetime import datetime, timezone

from crewai import Agent, Task, Crew, Process

from db import get_collection
from db.collections import Collections
from tools.bedrock import get_llm
from tools.skill_loader import load_skill
import tools.yfinance_client as yfc


# ---------------------------------------------------------------------------
# Global ticker universe — organized by region
# Each entry: (ticker, region, exchange_label)
# ---------------------------------------------------------------------------

GLOBAL_UNIVERSE: list[tuple[str, str, str]] = [
    # ── United States ───────────────────────────────────────────────────────
    ("AAPL",  "US", "NASDAQ"), ("MSFT",  "US", "NASDAQ"), ("NVDA",  "US", "NASDAQ"),
    ("GOOGL", "US", "NASDAQ"), ("AMZN",  "US", "NASDAQ"), ("META",  "US", "NASDAQ"),
    ("TSLA",  "US", "NASDAQ"), ("LLY",   "US", "NYSE"),   ("AVGO",  "US", "NASDAQ"),
    ("JPM",   "US", "NYSE"),   ("UNH",   "US", "NYSE"),   ("XOM",   "US", "NYSE"),
    ("V",     "US", "NYSE"),   ("MA",    "US", "NYSE"),   ("COST",  "US", "NASDAQ"),
    ("HD",    "US", "NYSE"),   ("PG",    "US", "NYSE"),   ("JNJ",   "US", "NYSE"),
    ("MRK",   "US", "NYSE"),   ("ABBV",  "US", "NYSE"),   ("WMT",   "US", "NYSE"),
    ("BAC",   "US", "NYSE"),   ("CRM",   "US", "NYSE"),   ("ORCL",  "US", "NYSE"),
    ("CVX",   "US", "NYSE"),   ("NFLX",  "US", "NASDAQ"), ("AMD",   "US", "NASDAQ"),
    ("KO",    "US", "NYSE"),   ("PEP",   "US", "NASDAQ"), ("TMO",   "US", "NYSE"),
    ("ACN",   "US", "NYSE"),   ("ADBE",  "US", "NASDAQ"), ("TXN",   "US", "NASDAQ"),
    ("WFC",   "US", "NYSE"),   ("INTU",  "US", "NASDAQ"), ("DIS",   "US", "NYSE"),
    ("AMGN",  "US", "NASDAQ"), ("CAT",   "US", "NYSE"),   ("GS",    "US", "NYSE"),
    ("NEE",   "US", "NYSE"),   ("RTX",   "US", "NYSE"),   ("HON",   "US", "NASDAQ"),
    ("SPGI",  "US", "NYSE"),   ("BKNG",  "US", "NASDAQ"), ("AXP",   "US", "NYSE"),
    ("GE",    "US", "NYSE"),   ("MS",    "US", "NYSE"),   ("ISRG",  "US", "NASDAQ"),
    ("VRTX",  "US", "NASDAQ"), ("NOW",   "US", "NYSE"),   ("PANW",  "US", "NASDAQ"),
    ("PLTR",  "US", "NYSE"),   ("CRWD",  "US", "NASDAQ"), ("GLD",   "US", "NYSE"),
    ("FCX",   "US", "NYSE"),   ("NEM",   "US", "NYSE"),   ("BRK.B", "US", "NYSE"),
    ("UNP",   "US", "NYSE"),   ("DE",    "US", "NYSE"),   ("LOW",   "US", "NYSE"),
    ("LIN",   "US", "NYSE"),   ("COIN",  "US", "NASDAQ"), ("MSTR",  "US", "NASDAQ"),

    # ── Japan ───────────────────────────────────────────────────────────────
    ("7203.T",  "JAPAN", "TSE"),   # Toyota
    ("9984.T",  "JAPAN", "TSE"),   # SoftBank Group
    ("6758.T",  "JAPAN", "TSE"),   # Sony
    ("8035.T",  "JAPAN", "TSE"),   # Tokyo Electron
    ("6861.T",  "JAPAN", "TSE"),   # Keyence
    ("7974.T",  "JAPAN", "TSE"),   # Nintendo
    ("6367.T",  "JAPAN", "TSE"),   # Daikin Industries
    ("7267.T",  "JAPAN", "TSE"),   # Honda
    ("4519.T",  "JAPAN", "TSE"),   # Chugai Pharmaceutical

    # ── South Korea ─────────────────────────────────────────────────────────
    ("005930.KS", "KOREA", "KRX"),  # Samsung Electronics
    ("000660.KS", "KOREA", "KRX"),  # SK Hynix
    ("051910.KS", "KOREA", "KRX"),  # LG Chem
    ("035420.KS", "KOREA", "KRX"),  # NAVER
    ("207940.KS", "KOREA", "KRX"),  # Samsung Biologics

    # ── Taiwan ──────────────────────────────────────────────────────────────
    ("2330.TW",  "TAIWAN", "TWSE"),  # TSMC
    ("2317.TW",  "TAIWAN", "TWSE"),  # Foxconn
    ("2454.TW",  "TAIWAN", "TWSE"),  # MediaTek

    # ── Hong Kong / China ───────────────────────────────────────────────────
    ("0700.HK",  "CHINA", "HKEX"),  # Tencent
    ("9988.HK",  "CHINA", "HKEX"),  # Alibaba
    ("3690.HK",  "CHINA", "HKEX"),  # Meituan
    ("9999.HK",  "CHINA", "HKEX"),  # NetEase
    ("0941.HK",  "CHINA", "HKEX"),  # China Mobile
    ("1299.HK",  "CHINA", "HKEX"),  # AIA Group
    ("BABA",     "CHINA", "NYSE"),   # Alibaba ADR
    ("BIDU",     "CHINA", "NASDAQ"), # Baidu ADR
    ("PDD",      "CHINA", "NASDAQ"), # PDD Holdings (Temu)

    # ── India ───────────────────────────────────────────────────────────────
    ("RELIANCE.NS",    "INDIA", "NSE"),
    ("TCS.NS",         "INDIA", "NSE"),
    ("INFY.NS",        "INDIA", "NSE"),
    ("HDFCBANK.NS",    "INDIA", "NSE"),
    ("ICICIBANK.NS",   "INDIA", "NSE"),
    ("WIPRO.NS",       "INDIA", "NSE"),
    ("HINDUNILVR.NS",  "INDIA", "NSE"),
    ("BAJFINANCE.NS",  "INDIA", "NSE"),
    ("LT.NS",          "INDIA", "NSE"),  # Larsen & Toubro

    # ── Australia ───────────────────────────────────────────────────────────
    ("BHP.AX",  "AUSTRALIA", "ASX"),
    ("RIO.AX",  "AUSTRALIA", "ASX"),
    ("CBA.AX",  "AUSTRALIA", "ASX"),
    ("CSL.AX",  "AUSTRALIA", "ASX"),
    ("ANZ.AX",  "AUSTRALIA", "ASX"),
    ("WES.AX",  "AUSTRALIA", "ASX"),  # Wesfarmers
    ("MQG.AX",  "AUSTRALIA", "ASX"),  # Macquarie

    # ── United Kingdom ──────────────────────────────────────────────────────
    ("HSBA.L",  "UK", "LSE"),   # HSBC
    ("BP.L",    "UK", "LSE"),
    ("SHEL.L",  "UK", "LSE"),   # Shell
    ("AZN.L",   "UK", "LSE"),   # AstraZeneca
    ("GSK.L",   "UK", "LSE"),
    ("ULVR.L",  "UK", "LSE"),   # Unilever
    ("DGE.L",   "UK", "LSE"),   # Diageo
    ("RIO.L",   "UK", "LSE"),   # Rio Tinto

    # ── Germany ─────────────────────────────────────────────────────────────
    ("SAP.DE",   "GERMANY", "XETRA"),
    ("SIE.DE",   "GERMANY", "XETRA"),  # Siemens
    ("ALV.DE",   "GERMANY", "XETRA"),  # Allianz
    ("BAS.DE",   "GERMANY", "XETRA"),  # BASF
    ("BMW.DE",   "GERMANY", "XETRA"),
    ("BAYN.DE",  "GERMANY", "XETRA"),  # Bayer
    ("DBK.DE",   "GERMANY", "XETRA"),  # Deutsche Bank

    # ── France ──────────────────────────────────────────────────────────────
    ("MC.PA",   "FRANCE", "EURONEXT"),  # LVMH
    ("OR.PA",   "FRANCE", "EURONEXT"),  # L'Oreal
    ("AIR.PA",  "FRANCE", "EURONEXT"),  # Airbus
    ("TTE.PA",  "FRANCE", "EURONEXT"),  # TotalEnergies
    ("BNP.PA",  "FRANCE", "EURONEXT"),  # BNP Paribas
    ("SU.PA",   "FRANCE", "EURONEXT"),  # Schneider Electric

    # ── Netherlands ─────────────────────────────────────────────────────────
    ("ASML.AS",  "NETHERLANDS", "EURONEXT"),  # ASML
    ("HEIA.AS",  "NETHERLANDS", "EURONEXT"),  # Heineken
    ("ING.AS",   "NETHERLANDS", "EURONEXT"),

    # ── Switzerland ─────────────────────────────────────────────────────────
    ("NESN.SW",  "SWITZERLAND", "SIX"),  # Nestle
    ("ROG.SW",   "SWITZERLAND", "SIX"),  # Roche
    ("NOVN.SW",  "SWITZERLAND", "SIX"),  # Novartis

    # ── Spain ───────────────────────────────────────────────────────────────
    ("ITX.MC",  "SPAIN", "BME"),  # Inditex (Zara)
    ("IBE.MC",  "SPAIN", "BME"),  # Iberdrola

    # ── Canada ──────────────────────────────────────────────────────────────
    ("SHOP.TO",  "CANADA", "TSX"),
    ("RY.TO",    "CANADA", "TSX"),  # Royal Bank
    ("TD.TO",    "CANADA", "TSX"),  # TD Bank
    ("CNR.TO",   "CANADA", "TSX"),  # CN Rail
    ("ENB.TO",   "CANADA", "TSX"),  # Enbridge
    ("SU.TO",    "CANADA", "TSX"),  # Suncor
    ("ABX.TO",   "CANADA", "TSX"),  # Barrick Gold

    # ── Brazil ──────────────────────────────────────────────────────────────
    ("VALE3.SA",  "BRAZIL", "B3"),  # Vale
    ("PETR4.SA",  "BRAZIL", "B3"),  # Petrobras
    ("ITUB4.SA",  "BRAZIL", "B3"),  # Itau Unibanco

    # ── ADRs — large non-US companies on US exchanges ────────────────────────
    ("ASML",  "NETHERLANDS", "NASDAQ"),  # ASML ADR
    ("TSM",   "TAIWAN",      "NYSE"),    # TSMC ADR
    ("NVO",   "DENMARK",     "NYSE"),    # Novo Nordisk ADR
    ("SAP",   "GERMANY",     "NYSE"),    # SAP ADR
    ("SHOP",  "CANADA",      "NYSE"),    # Shopify
    ("VALE",  "BRAZIL",      "NYSE"),    # Vale ADR
    ("RIO",   "AUSTRALIA",   "NYSE"),    # Rio Tinto ADR
    ("BP",    "UK",          "NYSE"),    # BP ADR
    ("SONY",  "JAPAN",       "NYSE"),    # Sony ADR
    ("HDB",   "INDIA",       "NYSE"),    # HDFC Bank ADR
    ("INFY",  "INDIA",       "NYSE"),    # Infosys ADR
    ("WIT",   "INDIA",       "NYSE"),    # Wipro ADR
]

# Lookup maps
TICKER_REGION   = {t: r for t, r, _ in GLOBAL_UNIVERSE}
TICKER_EXCHANGE = {t: e for t, _, e in GLOBAL_UNIVERSE}

# US-exchange tickers use Polygon; everything else uses yfinance
_US_EXCHANGES     = {"NASDAQ", "NYSE"}
_POLYGON_TICKERS  = {t for t, _, e in GLOBAL_UNIVERSE if e in _US_EXCHANGES}

# Flat list for iteration
SP500_SAMPLE = [t for t, _, _ in GLOBAL_UNIVERSE]


class ScreenerAgent:
    """Three-stage stock screener driven by causal theses."""

    def __init__(self):
        self.skill = load_skill("screener")
        self._llm = get_llm("screener")

    def _stage_a_quantitative(self, tickers: list[str], cfg: dict) -> list[dict]:
        """Hard quantitative filter — routes US tickers to Polygon, international to yfinance."""
        min_cap = cfg.get("min_market_cap_m", 500) * 1_000_000
        min_vol = cfg.get("min_avg_volume", 500_000)
        passed = []

        for ticker in tickers:
            try:
                # yfinance works for all tickers (US + international) — Polygon snapshot
                # requires a paid plan, so we use yfinance everywhere for Stage A
                snap    = yfc.get_snapshot(ticker)
                day     = snap.get("ticker", {}).get("day", {})
                price   = day.get("c", 0)
                volume  = day.get("v", 0)
                detail  = yfc.get_ticker_details(ticker)
                results = detail.get("results", {})

                market_cap = results.get("market_cap", 0) or 0
                is_us = ticker in _POLYGON_TICKERS
                # Non-US exchanges have lower absolute volume — relax threshold
                effective_min_vol = min_vol if is_us else min_vol * 0.1
                effective_min_cap = min_cap if is_us else min_cap * 0.5

                if price > 0 and volume >= effective_min_vol and market_cap >= effective_min_cap:
                    passed.append({
                        "ticker":     ticker,
                        "price":      price,
                        "volume":     volume,
                        "market_cap": market_cap,
                        "name":       results.get("name", ticker),
                        "sector":     results.get("sic_description") or results.get("sector", "Unknown"),
                        "region":     TICKER_REGION.get(ticker, "US"),
                        "exchange":   TICKER_EXCHANGE.get(ticker, ""),
                        "country":    results.get("country", ""),
                        "currency":   results.get("currency", "USD"),
                    })
            except Exception:
                continue  # skip on API error — don't let one failure halt the screener

        return passed

    def _stage_b_theme_alignment(self, candidates: list[dict], theses: list[dict]) -> list[dict]:
        """LLM-assisted: does each stock benefit from active causal theses?"""
        if not theses or not candidates:
            return candidates

        # Build a compact themes summary for the prompt
        themes_json = json.dumps(
            [{
                "theme_id": t.get("theme_id"),
                "root_cause": t.get("root_cause"),
                "sectors": [
                    sector
                    for horizon in t.get("theses", {}).values()
                    for sector in horizon.get("sectors", [])
                ],
                "tickers_to_watch": [
                    ticker
                    for horizon in t.get("theses", {}).values()
                    for ticker in horizon.get("tickers_to_watch", [])
                ],
                "avoid_sectors": [
                    s
                    for horizon in t.get("theses", {}).values()
                    for s in horizon.get("avoid_sectors", [])
                ],
            } for t in theses[:5]],
            indent=2,
        )

        candidates_json = json.dumps(
            [{"ticker": c["ticker"], "sector": c.get("sector", "")} for c in candidates],
            indent=2,
        )

        agent = Agent(
            role="Quantitative Stock Screener",
            goal="Score stocks for alignment with active macro investment theses",
            backstory="Expert at matching individual stocks to macro trends and causal investment theses",
            llm=self._llm,
            verbose=False,
            allow_delegation=False,
        )

        task = Task(
            description=f"""
{self.skill}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOW APPLY YOUR SKILL TO THESE STOCKS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ACTIVE MACRO THESES:
{themes_json}

CANDIDATES:
{candidates_json}

For each candidate, output a JSON array — one object per stock:
[
  {{
    "ticker": "AAPL",
    "theme_alignment": ["THEME_ID_1"],
    "alignment_type": "second_order",
    "theme_alignment_score": 65,
    "pass_reason": "why this stock passes"
  }}
]

Only include stocks with theme_alignment_score >= 30.
Output only valid JSON array — no other text.
            """,
            agent=agent,
            expected_output="JSON array of stocks with theme alignment scores",
        )

        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff()

        try:
            raw = str(result)
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            start = raw.find("[")
            end = raw.rfind("]") + 1
            scored = json.loads(raw[start:end])

            # Merge alignment data back into candidate dicts
            scored_map = {s["ticker"]: s for s in scored}
            enriched = []
            for c in candidates:
                tk = c["ticker"]
                if tk in scored_map:
                    enriched.append({**c, **scored_map[tk]})
            return sorted(enriched, key=lambda x: x.get("theme_alignment_score", 0), reverse=True)
        except Exception as e:
            print(f"[ScreenerAgent] Stage B parse error: {e}")
            return candidates

    def _stage_c_technical(self, candidates: list[dict]) -> list[dict]:
        """Technical filter: RSI range, uptrend, no imminent earnings."""
        passed = []
        for c in candidates:
            try:
                ticker = c["ticker"]
                raw = (get_aggregates if ticker in _POLYGON_TICKERS else yfc.get_aggregates)(ticker, 90)
                bars = raw.get("results", [])
                if len(bars) < 15:
                    continue

                closes = [b["c"] for b in bars]

                from mcp_servers.market_mcp import _compute_rsi
                rsi = _compute_rsi(closes)
                if not (30 <= rsi <= 70):
                    continue

                ma50 = sum(closes[-50:]) / min(50, len(closes))
                if closes[-1] < ma50:
                    continue

                passed.append({**c, "rsi": rsi, "ma50": round(ma50, 2)})
            except Exception:
                continue

        return passed

    def screen(self, theses: list[dict], run_id: str | None = None) -> list[dict]:
        """
        Full 3-stage screen.
        Returns up to max_candidates tickers with enriched metadata.
        """
        run_id = run_id or str(uuid.uuid4())

        import yaml, os
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)["screening"]

        # Filter universe by configured regions (default: all)
        allowed_regions = set(cfg.get("regions", [r for _, r, _ in GLOBAL_UNIVERSE]))
        tickers = [t for t, r, _ in GLOBAL_UNIVERSE if r in allowed_regions]

        region_counts = {}
        for _, r, _ in GLOBAL_UNIVERSE:
            if r in allowed_regions:
                region_counts[r] = region_counts.get(r, 0) + 1
        print(f"[ScreenerAgent] Universe: {len(tickers)} tickers across {len(region_counts)} regions: "
              + ", ".join(f"{r}({n})" for r, n in sorted(region_counts.items())))

        print(f"[ScreenerAgent] Stage A: quantitative filter on {len(tickers)} tickers")
        stage_a = self._stage_a_quantitative(tickers, cfg)
        print(f"[ScreenerAgent] Stage A passed: {len(stage_a)}")

        print(f"[ScreenerAgent] Stage B: theme alignment filter")
        stage_b = self._stage_b_theme_alignment(stage_a, theses)
        print(f"[ScreenerAgent] Stage B passed: {len(stage_b)}")

        print(f"[ScreenerAgent] Stage C: technical filter")
        stage_c = self._stage_c_technical(stage_b)
        print(f"[ScreenerAgent] Stage C passed: {len(stage_c)}")

        final = stage_c[: cfg.get("max_candidates", 60)]

        # Stamp run_id and persist
        now = datetime.now(timezone.utc).isoformat()
        col = get_collection(Collections.SCREENER_RESULTS)
        for stock in final:
            stock["run_id"] = run_id
            stock["screened_at"] = now
            col.update_one(
                {"ticker": stock["ticker"], "run_id": run_id},
                {"$set": stock},
                upsert=True,
            )

        print(f"[ScreenerAgent] Final candidates: {len(final)}")
        return final
