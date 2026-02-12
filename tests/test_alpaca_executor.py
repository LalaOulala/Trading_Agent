from __future__ import annotations

import unittest
from unittest.mock import patch

from trading_pipeline.execution.alpaca_executor import AlpacaTradeExecutor
from trading_pipeline.models import FinalDecision


def _decision_with_order() -> FinalDecision:
    return FinalDecision(
        action="LONG",
        symbols=["AAPL"],
        thesis="Momentum positif.",
        risk_controls=["Taille unitaire faible."],
        confidence="medium",
        should_execute=True,
        orders=[
            {
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1,
                "type": "market",
                "time_in_force": "day",
            }
        ],
    )


def _decision_with_sell_order(symbol: str = "AAPL", qty: float = 1.0) -> FinalDecision:
    return FinalDecision(
        action="SHORT",
        symbols=[symbol],
        thesis="Pression vendeuse.",
        risk_controls=["Taille unitaire faible."],
        confidence="medium",
        should_execute=True,
        orders=[
            {
                "symbol": symbol,
                "side": "sell",
                "qty": qty,
                "type": "market",
                "time_in_force": "day",
            }
        ],
    )


class _NoSubmitExecutor(AlpacaTradeExecutor):
    def _load_portfolio_snapshot(self) -> tuple[dict[str, object] | None, str | None]:
        return (
            {
                "status": "ACTIVE",
                "equity": "100000",
                "cash": "50000",
                "buying_power": "200000",
                "positions": [],
            },
            None,
        )

    def _submit_orders(self, orders: list[dict[str, object]]) -> list[dict[str, str]]:
        raise AssertionError("_submit_orders ne doit pas être appelé.")

    def _check_market_open(self) -> tuple[bool, str | None]:
        return True, None


class _StubSubmitExecutor(AlpacaTradeExecutor):
    def _load_portfolio_snapshot(self) -> tuple[dict[str, object] | None, str | None]:
        return (
            {
                "status": "ACTIVE",
                "equity": "100000",
                "cash": "50000",
                "buying_power": "200000",
                "positions": [
                    {
                        "symbol": "SPY",
                        "qty": "1",
                        "side": "long",
                        "market_value": "500",
                    }
                ],
            },
            None,
        )

    def _submit_orders(self, orders: list[dict[str, object]]) -> list[dict[str, str]]:
        submitted: list[dict[str, str]] = []
        for order in orders:
            submitted.append(
                {
                    "symbol": str(order["symbol"]),
                    "side": str(order["side"]),
                    "qty": str(order["qty"]),
                    "order_id": "stub-order-id",
                }
            )
        return submitted

    def _check_market_open(self) -> tuple[bool, str | None]:
        return True, None


class _ClosedMarketExecutor(AlpacaTradeExecutor):
    def _submit_orders(self, orders: list[dict[str, object]]) -> list[dict[str, str]]:
        raise AssertionError("_submit_orders ne doit pas être appelé si le marché est fermé.")

    def _check_market_open(self) -> tuple[bool, str | None]:
        return False, "Le marché est fermé, il réouvre dans 5h 0m 0s."


class AlpacaExecutorTests(unittest.TestCase):
    def test_execute_live_cancelled_when_confirmation_is_not_yes(self) -> None:
        executor = _NoSubmitExecutor(
            api_key="key",
            api_secret="secret",
            paper=True,
            execute_live=True,
            require_confirmation=True,
        )
        with patch("builtins.input", return_value="no"):
            report = executor.execute(_decision_with_order())

        self.assertEqual(report.status, "skipped")
        self.assertIn("confirmation", report.message.lower())
        self.assertEqual(len(report.details), 1)

    def test_execute_live_submits_when_user_confirms_yes(self) -> None:
        executor = _StubSubmitExecutor(
            api_key="key",
            api_secret="secret",
            paper=True,
            execute_live=True,
            require_confirmation=True,
        )
        with patch("builtins.input", return_value="yes"):
            report = executor.execute(_decision_with_order())

        self.assertEqual(report.status, "submitted")
        self.assertEqual(report.details[0]["symbol"], "AAPL")
        self.assertEqual(report.details[0]["order_id"], "stub-order-id")

    def test_execute_live_auto_confirm_bypasses_prompt(self) -> None:
        executor = _StubSubmitExecutor(
            api_key="key",
            api_secret="secret",
            paper=True,
            execute_live=True,
            require_confirmation=False,
        )
        with patch("builtins.input", side_effect=AssertionError("input() ne doit pas être appelé")):
            report = executor.execute(_decision_with_order())

        self.assertEqual(report.status, "submitted")
        self.assertEqual(len(report.details), 1)

    def test_execute_live_skips_when_market_is_closed(self) -> None:
        executor = _ClosedMarketExecutor(
            api_key="key",
            api_secret="secret",
            paper=True,
            execute_live=True,
            require_confirmation=False,
        )
        with patch("builtins.input", side_effect=AssertionError("input() ne doit pas être appelé")):
            report = executor.execute(_decision_with_order())

        self.assertEqual(report.status, "skipped")
        self.assertIn("marché est fermé", report.message.lower())
        self.assertEqual(len(report.details), 1)

    def test_execute_live_blocks_sell_when_it_would_open_short(self) -> None:
        executor = _NoSubmitExecutor(
            api_key="key",
            api_secret="secret",
            paper=True,
            execute_live=True,
            require_confirmation=False,
        )
        with patch("builtins.input", side_effect=AssertionError("input() ne doit pas être appelé")):
            report = executor.execute(_decision_with_sell_order("AAPL", 1.0))

        self.assertEqual(report.status, "skipped")
        self.assertIn("short", report.message.lower())
        self.assertEqual(len(report.details), 1)

    def test_execute_live_allows_sell_to_close_existing_long(self) -> None:
        executor = _StubSubmitExecutor(
            api_key="key",
            api_secret="secret",
            paper=True,
            execute_live=True,
            require_confirmation=False,
        )
        with patch("builtins.input", side_effect=AssertionError("input() ne doit pas être appelé")):
            report = executor.execute(_decision_with_sell_order("SPY", 1.0))

        self.assertEqual(report.status, "submitted")
        self.assertEqual(report.details[0]["symbol"], "SPY")
        self.assertEqual(report.details[0]["side"], "sell")


if __name__ == "__main__":
    unittest.main()
