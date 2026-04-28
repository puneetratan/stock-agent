"""Tests for the three-stage screener logic."""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stage A — quantitative filter
# ---------------------------------------------------------------------------

class TestStageAQuantitative:
    def _make_agent(self):
        with patch("agents.screener.get_llm"), \
             patch("agents.screener.get_snapshot"), \
             patch("agents.screener.get_ticker_details"), \
             patch("agents.screener.get_collection"):
            from agents.screener import ScreenerAgent
            return ScreenerAgent()

    def test_passes_stock_above_thresholds(self):
        snap = {"ticker": {"day": {"c": 150.0, "v": 2_000_000}}}
        detail = {"results": {"market_cap": 2_000_000_000, "name": "Test Corp", "sic_description": "Technology"}}

        with patch("agents.screener.get_snapshot", return_value=snap), \
             patch("agents.screener.get_ticker_details", return_value=detail), \
             patch("agents.screener.get_collection"):
            from agents.screener import ScreenerAgent
            agent = ScreenerAgent.__new__(ScreenerAgent)
            result = agent._stage_a_quantitative(["AAPL"], {"min_market_cap_m": 500, "min_avg_volume": 500_000})

        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["price"] == 150.0

    def test_filters_stock_below_min_price(self):
        snap = {"ticker": {"day": {"c": 3.0, "v": 5_000_000}}}
        detail = {"results": {"market_cap": 2_000_000_000, "name": "Penny Corp", "sic_description": "Finance"}}

        with patch("agents.screener.get_snapshot", return_value=snap), \
             patch("agents.screener.get_ticker_details", return_value=detail), \
             patch("agents.screener.get_collection"):
            from agents.screener import ScreenerAgent
            agent = ScreenerAgent.__new__(ScreenerAgent)
            result = agent._stage_a_quantitative(["AAPL"], {"min_market_cap_m": 500, "min_avg_volume": 500_000})

        assert len(result) == 0

    def test_filters_stock_below_min_volume(self):
        snap = {"ticker": {"day": {"c": 50.0, "v": 100_000}}}
        detail = {"results": {"market_cap": 2_000_000_000, "name": "Low Vol Corp", "sic_description": "Utilities"}}

        with patch("agents.screener.get_snapshot", return_value=snap), \
             patch("agents.screener.get_ticker_details", return_value=detail), \
             patch("agents.screener.get_collection"):
            from agents.screener import ScreenerAgent
            agent = ScreenerAgent.__new__(ScreenerAgent)
            result = agent._stage_a_quantitative(["XYZ"], {"min_market_cap_m": 500, "min_avg_volume": 500_000})

        assert len(result) == 0

    def test_api_error_skips_ticker(self):
        with patch("agents.screener.get_snapshot", side_effect=Exception("API error")), \
             patch("agents.screener.get_collection"):
            from agents.screener import ScreenerAgent
            agent = ScreenerAgent.__new__(ScreenerAgent)
            result = agent._stage_a_quantitative(["FAIL"], {"min_market_cap_m": 500, "min_avg_volume": 500_000})

        assert result == []


# ---------------------------------------------------------------------------
# Stage C — technical filter (RSI + MA)
# ---------------------------------------------------------------------------

class TestStageCTechnical:

    def _make_bars(self, closes: list[float]) -> list[dict]:
        return [{"c": c, "h": c + 1, "l": c - 1, "v": 1_000_000} for c in closes]

    def test_passes_stock_in_rsi_range_and_uptrend(self):
        # RSI ~50, price above 50-day MA
        import random
        random.seed(42)
        closes = [100 + random.uniform(-2, 2) for _ in range(90)]
        closes[-1] = closes[-1] + 5  # push above MA

        raw = {"results": self._make_bars(closes)}
        candidate = {"ticker": "TEST", "price": closes[-1], "volume": 1_000_000, "market_cap": 1e9}

        with patch("agents.screener.get_aggregates", return_value=raw), \
             patch("agents.screener.get_collection"), \
             patch("mcp_servers.market_mcp._compute_rsi", return_value=52.0):
            from agents.screener import ScreenerAgent
            agent = ScreenerAgent.__new__(ScreenerAgent)
            result = agent._stage_c_technical([candidate])

        assert len(result) == 1

    def test_rejects_overbought_rsi(self):
        closes = [float(i) for i in range(90, 180)]  # strong uptrend → high RSI
        raw = {"results": self._make_bars(closes)}
        candidate = {"ticker": "HOT", "price": 179.0, "volume": 1_000_000, "market_cap": 1e9}

        with patch("agents.screener.get_aggregates", return_value=raw), \
             patch("agents.screener.get_collection"), \
             patch("mcp_servers.market_mcp._compute_rsi", return_value=85.0):
            from agents.screener import ScreenerAgent
            agent = ScreenerAgent.__new__(ScreenerAgent)
            result = agent._stage_c_technical([candidate])

        assert len(result) == 0


# ---------------------------------------------------------------------------
# RSI calculation unit tests
# ---------------------------------------------------------------------------

class TestRSICalculation:

    def test_neutral_rsi_for_flat_price(self):
        from mcp_servers.market_mcp import _compute_rsi
        closes = [100.0] * 30
        rsi = _compute_rsi(closes)
        assert rsi == 50.0 or rsi == 100.0  # no losses → RS undefined, capped at 100

    def test_rsi_below_30_for_sustained_decline(self):
        from mcp_servers.market_mcp import _compute_rsi
        closes = [100.0 - i * 2 for i in range(30)]  # steady decline
        rsi = _compute_rsi(closes)
        assert rsi < 30

    def test_rsi_above_70_for_sustained_rally(self):
        from mcp_servers.market_mcp import _compute_rsi
        closes = [50.0 + i * 2 for i in range(30)]  # steady rally
        rsi = _compute_rsi(closes)
        assert rsi > 70

    def test_rsi_insufficient_data_returns_50(self):
        from mcp_servers.market_mcp import _compute_rsi
        rsi = _compute_rsi([100.0, 101.0, 99.0])  # only 3 data points
        assert rsi == 50.0
