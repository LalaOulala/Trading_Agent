from __future__ import annotations

import unittest

from trading_pipeline.agents.reasoning_agents import (
    _guard_orders_from_trade_errors,
    _latest_api_error_message,
)


class ReasoningAgentsHelpersTests(unittest.TestCase):
    def test_latest_api_error_message_returns_last_error(self) -> None:
        history = [
            {"execution_report": {"status": "submitted", "message": "ok"}},
            {"execution_report": {"status": "error", "message": "e1"}},
            {"execution_report": {"status": "error", "message": "e2"}},
        ]
        self.assertEqual(_latest_api_error_message(history), "e2")

    def test_guard_blocks_orders_after_insufficient_buying_power(self) -> None:
        parsed = {
            "should_execute": True,
            "orders": [{"symbol": "COST", "side": "buy", "qty": 1}],
        }
        history = [
            {
                "execution_report": {
                    "status": "error",
                    "message": "APIError: insufficient buying power",
                }
            }
        ]
        adjusted, notes = _guard_orders_from_trade_errors(parsed=parsed, trade_events=history)
        self.assertFalse(adjusted["should_execute"])
        self.assertEqual(adjusted["orders"], [])
        self.assertTrue(notes)

    def test_guard_filters_sell_when_short_not_allowed(self) -> None:
        parsed = {
            "should_execute": True,
            "orders": [
                {"symbol": "SPY", "side": "sell", "qty": 1},
                {"symbol": "AAPL", "side": "buy", "qty": 1},
            ],
        }
        history = [
            {
                "execution_report": {
                    "status": "error",
                    "message": "account is not allowed to short",
                }
            }
        ]
        adjusted, notes = _guard_orders_from_trade_errors(parsed=parsed, trade_events=history)
        self.assertEqual(len(adjusted["orders"]), 1)
        self.assertEqual(adjusted["orders"][0]["side"], "buy")
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
