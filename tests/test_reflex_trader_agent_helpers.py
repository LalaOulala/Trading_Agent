from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from reflex_trader_agent import (
    _extract_json_object,
    _load_portfolio_snapshot,
    _normalize_reasoning_effort,
    _normalize_us_equity_symbol,
)


class ReflexTraderHelpersTests(unittest.TestCase):
    def test_extract_json_object_parses_with_noise(self) -> None:
        text = 'noise {not json} before {"requested_market_data": [], "questions": [], "conclusion": "ok"} trailing'
        parsed = _extract_json_object(text)
        self.assertEqual(parsed["conclusion"], "ok")

    def test_extract_json_object_raises_explicit_error(self) -> None:
        text = "no json here"
        with self.assertRaisesRegex(ValueError, "aucun bloc"):
            _extract_json_object(text)

    def test_extract_json_object_raises_explicit_decode_error(self) -> None:
        text = "{bad}\n{still bad}"
        with self.assertRaisesRegex(ValueError, "Aucun objet JSON valide détecté"):
            _extract_json_object(text)

    def test_normalize_us_equity_symbol(self) -> None:
        self.assertEqual(_normalize_us_equity_symbol(" spy "), "SPY")
        self.assertEqual(_normalize_us_equity_symbol("brk.b"), "BRK.B")
        self.assertIsNone(_normalize_us_equity_symbol("BTC-USD"))
        self.assertIsNone(_normalize_us_equity_symbol("TOO_LONG_TICKER"))

    def test_normalize_reasoning_effort(self) -> None:
        self.assertEqual(_normalize_reasoning_effort("high"), "high")
        self.assertEqual(_normalize_reasoning_effort("LOW"), "low")
        self.assertEqual(_normalize_reasoning_effort("invalid"), "high")
        self.assertEqual(_normalize_reasoning_effort(None), "high")

    def test_load_portfolio_snapshot_missing_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            snapshot = _load_portfolio_snapshot()
        self.assertFalse(snapshot["available"])
        self.assertIn("Credentials Alpaca manquants", snapshot["reason"])

    def test_load_portfolio_snapshot_handles_alpaca_errors(self) -> None:
        with patch.dict(
            os.environ,
            {"ALPACA_API_KEY": "key", "ALPACA_API_SECRET": "secret", "ALPACA_PAPER": "true"},
            clear=True,
        ):
            with patch("reflex_trader_agent.TradingClient", side_effect=RuntimeError("boom")):
                snapshot = _load_portfolio_snapshot()

        self.assertFalse(snapshot["available"])
        self.assertTrue(snapshot["paper"])
        self.assertIn("Snapshot Alpaca indisponible", snapshot["reason"])
        self.assertIn("RuntimeError", snapshot["reason"])


if __name__ == "__main__":
    unittest.main()
