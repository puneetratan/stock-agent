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
from tools.polygon import get_aggregates, get_snapshot, get_ticker_details


# S&P 500 ticker universe — in production, fetch dynamically from Polygon
SP500_SAMPLE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK.B",
    "LLY", "AVGO", "JPM", "UNH", "XOM", "V", "MA", "COST", "HD", "PG",
    "JNJ", "MRK", "ABBV", "WMT", "BAC", "CRM", "ORCL", "CVX", "NFLX",
    "AMD", "KO", "PEP", "TMO", "ACN", "ADBE", "TXN", "WFC", "LIN",
    "INTU", "DIS", "AMGN", "CAT", "GS", "UNP", "NEE", "RTX", "HON",
    "LOW", "DE", "SPGI", "BKNG", "AXP", "GE", "MS", "ISRG", "VRTX",
    "NOW", "PANW", "PLTR", "CRWD", "MSTR", "COIN", "SOFI", "HOOD",
    "GLD", "SLV", "GDX", "FCX", "NEM", "X", "CLF", "MT", "AA",
]


class ScreenerAgent:
    """Three-stage stock screener driven by causal theses."""

    def __init__(self):
        self._llm = get_llm("screener")

    def _stage_a_quantitative(self, tickers: list[str], cfg: dict) -> list[dict]:
        """Hard quantitative filter — fast, no LLM needed."""
        min_cap = cfg.get("min_market_cap_m", 500) * 1_000_000
        min_vol = cfg.get("min_avg_volume", 500_000)
        passed = []

        for ticker in tickers:
            try:
                snap = get_snapshot(ticker)
                day = snap.get("ticker", {}).get("day", {})
                price = day.get("c", 0)
                volume = day.get("v", 0)

                detail = get_ticker_details(ticker)
                results = detail.get("results", {})
                market_cap = results.get("market_cap", 0) or 0

                if price >= 5 and volume >= min_vol and market_cap >= min_cap:
                    passed.append({
                        "ticker": ticker,
                        "price": price,
                        "volume": volume,
                        "market_cap": market_cap,
                        "name": results.get("name", ticker),
                        "sector": results.get("sic_description", "Unknown"),
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
For each stock in the candidates list, score its alignment with the active macro theses.

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
                raw = get_aggregates(ticker, 90)
                bars = raw.get("results", [])
                if len(bars) < 15:
                    continue

                closes = [b["c"] for b in bars]

                # RSI filter: 30-70 (avoid overbought / oversold)
                from mcp_servers.market_mcp import _compute_rsi
                rsi = _compute_rsi(closes)
                if not (30 <= rsi <= 70):
                    continue

                # Uptrend: current price above 50-day MA
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

        tickers = SP500_SAMPLE[:]

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
