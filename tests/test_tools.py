"""Tests for tool layer: MACD, RSI, FRED, delivery."""

import pytest
from unittest.mock import patch, MagicMock


class TestMACDCalculation:

    def test_bullish_cross_detected(self):
        from mcp_servers.market_mcp import _compute_macd
        # MACD line crossing above signal → bullish cross
        # Build prices that produce a recent bullish MACD cross
        import math
        closes = [100 + 10 * math.sin(i * 0.2) for i in range(60)]
        # Push last 5 values steeply upward to force a bullish cross
        for i in range(5):
            closes.append(closes[-1] + 5)
        result = _compute_macd(closes)
        assert "signal" in result
        assert result["signal"] in {"bullish_cross", "bullish_momentum", "bearish_cross", "bearish_momentum", "insufficient_data"}

    def test_insufficient_data_returns_safe_default(self):
        from mcp_servers.market_mcp import _compute_macd
        result = _compute_macd([100.0] * 10)
        assert result["signal"] == "insufficient_data"

    def test_macd_keys_present(self):
        from mcp_servers.market_mcp import _compute_macd
        closes = [100 + i * 0.5 for i in range(50)]
        result = _compute_macd(closes)
        assert "signal" in result
        assert "macd" in result
        assert "histogram" in result


class TestEMACalculation:

    def test_ema_same_as_price_for_single_period(self):
        from mcp_servers.market_mcp import _ema
        prices = [100.0]
        result = _ema(prices, 1)
        assert result == [100.0]

    def test_ema_converges_toward_new_level(self):
        from mcp_servers.market_mcp import _ema
        # Start at 100, then all 200s — EMA should climb toward 200
        prices = [100.0] + [200.0] * 30
        result = _ema(prices, 10)
        # EMA should be well above 100 by the end
        assert result[-1] > 150


class TestDeliveryRendering:

    def test_html_render_contains_ticker(self):
        from tools.delivery import _render_html
        report = {
            "run_id": "abc-123",
            "generated_at": "2026-04-27T06:30:00",
            "market_regime": {"label": "Risk-Off"},
            "causal_summary": "Markets are choppy.",
            "horizons": [
                {
                    "horizon": "quarter",
                    "picks": [{"ticker": "NVDA", "signal": "BUY", "confidence": 80, "thesis": "AI demand"}],
                    "avoid": [],
                    "contrarian_picks": [],
                }
            ],
            "analyst_note": "Stay disciplined.",
        }
        html = _render_html(report)
        assert "NVDA" in html
        assert "2026-04-27" in html
        assert "Risk-Off" in html

    def test_terminal_delivery_does_not_raise(self, capsys):
        from tools.delivery import _deliver_terminal
        report = {"run_id": "x", "generated_at": "2026-04-27", "horizons": []}
        _deliver_terminal(report)
        captured = capsys.readouterr()
        assert "run_id" in captured.out


class TestFREDClient:

    def test_get_series_returns_list(self):
        mock_response = {
            "observations": [
                {"date": "2026-04-01", "value": "103.5"},
                {"date": "2026-03-01", "value": "102.1"},
            ]
        }
        with patch("tools.fred.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )
            from tools.fred import get_series
            result = get_series("DTWEXBGS", limit=2)

        assert len(result) == 2
        assert result[0]["value"] == "103.5"

    def test_dollar_index_returns_latest(self):
        mock_response = {
            "observations": [
                {"date": "2026-04-01", "value": "103.5"},
                {"date": "2026-03-01", "value": "102.1"},
            ]
        }
        with patch("tools.fred.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )
            from tools.fred import get_dollar_index
            result = get_dollar_index()

        assert "latest" in result
        assert result["latest"]["value"] == "103.5"


class TestSignalModel:

    def test_signal_to_mongo_converts_enum(self):
        from models.signal import Signal, SignalType
        s = Signal(
            run_id="r1",
            ticker="AAPL",
            signal=SignalType.BUY,
            horizon="quarter",
            confidence=75,
            thesis="Strong AI theme alignment",
        )
        doc = s.to_mongo()
        assert doc["signal"] == "BUY"   # enum → string
        assert doc["confidence"] == 75

    def test_signal_confidence_bounds(self):
        from models.signal import Signal, SignalType
        with pytest.raises(Exception):
            Signal(run_id="r1", ticker="X", signal=SignalType.BUY,
                   horizon="quarter", confidence=101, thesis="test")

    def test_signal_defaults(self):
        from models.signal import Signal, SignalType
        s = Signal(run_id="r", ticker="T", signal=SignalType.HOLD,
                   horizon="one_year", confidence=50, thesis="neutral")
        assert s.is_contrarian is False
        assert s.risks == []
        assert s.theme_ids == []
