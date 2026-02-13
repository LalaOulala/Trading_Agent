from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from grok_tools_test import _load_financial_snapshot, _normalize_reasoning_effort


class GrokToolsHelpersTests(unittest.TestCase):
    def test_normalize_reasoning_effort(self) -> None:
        self.assertEqual(_normalize_reasoning_effort("high"), "high")
        self.assertEqual(_normalize_reasoning_effort("LOW"), "low")
        self.assertEqual(_normalize_reasoning_effort("invalid"), "high")
        self.assertEqual(_normalize_reasoning_effort(None), "high")

    def test_load_financial_snapshot_missing_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            snapshot = _load_financial_snapshot()

        self.assertFalse(snapshot["available"])
        self.assertIn("Credentials Alpaca manquants", snapshot["reason"])

    def test_load_financial_snapshot_handles_alpaca_errors(self) -> None:
        with patch.dict(
            os.environ,
            {"ALPACA_API_KEY": "key", "ALPACA_API_SECRET": "secret", "ALPACA_PAPER": "true"},
            clear=True,
        ):
            with patch("grok_tools_test.TradingClient", side_effect=RuntimeError("boom")):
                snapshot = _load_financial_snapshot()

        self.assertFalse(snapshot["available"])
        self.assertTrue(snapshot["paper"])
        self.assertIn("Snapshot Alpaca indisponible", snapshot["reason"])
        self.assertIn("RuntimeError", snapshot["reason"])

    def test_load_financial_snapshot_success(self) -> None:
        account = SimpleNamespace(
            status="ACTIVE",
            equity="2500",
            last_equity="2490",
            cash="1200",
            buying_power="2400",
            shorting_enabled=True,
            multiplier="2",
            daytrading_buying_power="0",
            portfolio_value="2500",
        )
        positions = [
            SimpleNamespace(
                symbol="SPY",
                qty="1",
                side="long",
                avg_entry_price="600",
                market_value="605",
                unrealized_pl="5",
                unrealized_plpc="0.0083",
            )
        ]

        class _FakeClient:
            def __init__(self, api_key: str, secret_key: str, paper: bool) -> None:
                self.api_key = api_key
                self.secret_key = secret_key
                self.paper = paper

            def get_account(self) -> SimpleNamespace:
                return account

            def get_all_positions(self) -> list[SimpleNamespace]:
                return positions

        with patch.dict(
            os.environ,
            {"ALPACA_API_KEY": "key", "ALPACA_API_SECRET": "secret", "ALPACA_PAPER": "true"},
            clear=True,
        ):
            with patch("grok_tools_test.TradingClient", _FakeClient):
                snapshot = _load_financial_snapshot()

        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["account"]["buying_power"], "2400")
        self.assertTrue(snapshot["account"]["shorting_enabled"])
        self.assertEqual(snapshot["positions"][0]["symbol"], "SPY")


if __name__ == "__main__":
    unittest.main()
