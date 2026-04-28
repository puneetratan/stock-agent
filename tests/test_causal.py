"""Tests for CausalReasoningAgent JSON parsing and output structure."""

import json
import pytest
from unittest.mock import MagicMock, patch

from models import Theme, ThemeStatus


VALID_THESIS = {
    "theme_id": "PETRODOLLAR_EROSION",
    "surface_narrative": "Middle East conflict escalating",
    "root_cause": "Iran/BRICS bypassing USD in oil trade",
    "historical_parallel": {
        "event": "Nixon closes gold window 1971",
        "what_happened": "Gold +2400% over next decade",
        "lesson": "Dollar alternatives outperform in dedollarisation",
    },
    "causal_chain": [
        "Level 1: Iran sells oil in Yuan",
        "Level 2: BRICS nations follow, reducing USD demand",
        "Level 3: US must monetise debt → inflation",
        "Level 4: Bretton Woods II breaking down — reserve currency transition",
    ],
    "second_order": [
        "Cybersecurity stocks (cyber war follows kinetic)",
        "Gold miners (hard asset demand)",
        "Non-USD markets outperform",
    ],
    "contrarian_take": "Everyone buys oil. Smart money buys gold miners.",
    "theses": {
        "quarter": {"sectors": ["gold"], "tickers_to_watch": ["GLD", "NEM"], "avoid_sectors": ["consumer"], "reason": "short-term safe haven"},
        "one_year": {"sectors": ["defense", "cybersecurity"], "tickers_to_watch": ["RTX", "PANW"], "avoid_sectors": [], "reason": "escalation cycle"},
        "two_year": {"sectors": ["energy"], "tickers_to_watch": ["XOM"], "avoid_sectors": [], "reason": "supply rerouting"},
        "five_year": {"sectors": ["gold", "commodities"], "tickers_to_watch": ["NEM", "FCX"], "avoid_sectors": [], "reason": "dedollarisation"},
        "ten_year": {"sectors": ["hard_assets"], "tickers_to_watch": ["GLD"], "avoid_sectors": ["bonds"], "reason": "currency debasement"},
    },
    "risk_flags": ["Saudi Arabia reaffirms petrodollar deal"],
    "confidence": 78,
}


class TestCausalReasoningOutputParsing:

    def _make_theme(self) -> Theme:
        return Theme(
            id="PETRODOLLAR_EROSION",
            name="Iran/BRICS Petrodollar Bypass",
            urgency=9,
            status=ThemeStatus.HOT,
            summary="Iran and BRICS nations are increasingly settling oil trades in non-USD currencies",
            evidence=["Iran sells oil in Yuan", "BRICS currency proposal"],
            run_id="test-run-001",
        )

    def test_valid_json_is_parsed_correctly(self):
        with patch("agents.causal_reasoning.get_llm"), \
             patch("agents.causal_reasoning.fred_client"), \
             patch("agents.causal_reasoning.get_collection"):
            from agents.causal_reasoning import CausalReasoningAgent
            agent = CausalReasoningAgent.__new__(CausalReasoningAgent)

            mock_crew = MagicMock()
            mock_crew.kickoff.return_value = json.dumps(VALID_THESIS)

            with patch.object(agent, "_build_crew", return_value=mock_crew), \
                 patch.object(agent, "_fetch_macro_context", return_value="DXY: 103"):
                results = agent.analyse([self._make_theme()], run_id="test-run-001")

        assert len(results) == 1
        result = results[0]
        assert result["theme_id"] == "PETRODOLLAR_EROSION"
        assert result["confidence"] == 78
        assert len(result["causal_chain"]) == 4

    def test_json_wrapped_in_markdown_is_parsed(self):
        wrapped = f"```json\n{json.dumps(VALID_THESIS)}\n```"

        with patch("agents.causal_reasoning.get_llm"), \
             patch("agents.causal_reasoning.fred_client"), \
             patch("agents.causal_reasoning.get_collection"):
            from agents.causal_reasoning import CausalReasoningAgent
            agent = CausalReasoningAgent.__new__(CausalReasoningAgent)

            mock_crew = MagicMock()
            mock_crew.kickoff.return_value = wrapped

            with patch.object(agent, "_build_crew", return_value=mock_crew), \
                 patch.object(agent, "_fetch_macro_context", return_value=""):
                results = agent.analyse([self._make_theme()], run_id="test-run-001")

        assert results[0]["theme_id"] == "PETRODOLLAR_EROSION"

    def test_all_five_horizons_present(self):
        with patch("agents.causal_reasoning.get_llm"), \
             patch("agents.causal_reasoning.fred_client"), \
             patch("agents.causal_reasoning.get_collection"):
            from agents.causal_reasoning import CausalReasoningAgent
            agent = CausalReasoningAgent.__new__(CausalReasoningAgent)

            mock_crew = MagicMock()
            mock_crew.kickoff.return_value = json.dumps(VALID_THESIS)

            with patch.object(agent, "_build_crew", return_value=mock_crew), \
                 patch.object(agent, "_fetch_macro_context", return_value=""):
                results = agent.analyse([self._make_theme()], run_id="test-run-001")

        theses = results[0]["theses"]
        for horizon in ["quarter", "one_year", "two_year", "five_year", "ten_year"]:
            assert horizon in theses

    def test_api_error_returns_error_dict(self):
        with patch("agents.causal_reasoning.get_llm"), \
             patch("agents.causal_reasoning.fred_client"), \
             patch("agents.causal_reasoning.get_collection"):
            from agents.causal_reasoning import CausalReasoningAgent
            agent = CausalReasoningAgent.__new__(CausalReasoningAgent)

            mock_crew = MagicMock()
            mock_crew.kickoff.side_effect = Exception("Bedrock timeout")

            with patch.object(agent, "_build_crew", return_value=mock_crew), \
                 patch.object(agent, "_fetch_macro_context", return_value=""):
                results = agent.analyse([self._make_theme()], run_id="test-run-001")

        assert len(results) == 1
        assert "error" in results[0]
        assert results[0]["theme_id"] == "PETRODOLLAR_EROSION"

    def test_run_id_stamped_on_result(self):
        with patch("agents.causal_reasoning.get_llm"), \
             patch("agents.causal_reasoning.fred_client"), \
             patch("agents.causal_reasoning.get_collection"):
            from agents.causal_reasoning import CausalReasoningAgent
            agent = CausalReasoningAgent.__new__(CausalReasoningAgent)

            mock_crew = MagicMock()
            mock_crew.kickoff.return_value = json.dumps(VALID_THESIS)

            with patch.object(agent, "_build_crew", return_value=mock_crew), \
                 patch.object(agent, "_fetch_macro_context", return_value=""):
                results = agent.analyse([self._make_theme()], run_id="specific-run-999")

        assert results[0]["run_id"] == "specific-run-999"


class TestThemeModel:

    def test_theme_serialises_to_mongo(self):
        theme = Theme(
            id="AI_CAPEX_BOOM",
            name="AI Infrastructure Spending Surge",
            urgency=8,
            status=ThemeStatus.HOT,
            summary="Hyperscalers spending record capex on AI data centres",
            run_id="test-001",
        )
        doc = theme.to_mongo()
        assert doc["status"] == "hot"   # enum → string
        assert doc["urgency"] == 8
        assert "causal_chain" in doc

    def test_theme_urgency_clamped(self):
        with pytest.raises(Exception):
            Theme(
                id="X", name="X", urgency=11,
                status=ThemeStatus.NEW, summary="X", run_id="x",
            )
