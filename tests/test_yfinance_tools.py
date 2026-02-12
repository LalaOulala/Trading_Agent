from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from trading_pipeline.financial import yfinance_tools


class _StubTicker:
    def __init__(self, info: dict | None = None, history_df: pd.DataFrame | None = None):
        self.info = info or {}
        self._history_df = history_df
        self.fast_info = {"last_price": None}

    def history(self, **kwargs):
        return self._history_df if self._history_df is not None else pd.DataFrame()


class YFinanceToolsTests(unittest.TestCase):
    def test_get_current_price_prefers_info(self) -> None:
        stub = _StubTicker(info={"currentPrice": 123.45})
        with patch.object(yfinance_tools, "_ticker", return_value=stub):
            price = yfinance_tools.get_current_price("AAPL")
        self.assertEqual(price, 123.45)

    def test_get_price_history_accepts_interval(self) -> None:
        df = pd.DataFrame({"Close": [1.0, 2.0]})
        stub = _StubTicker(history_df=df)
        with patch.object(yfinance_tools, "_ticker", return_value=stub):
            history = yfinance_tools.get_price_history("AAPL", period="1d", interval="5m")
        self.assertIsNotNone(history)
        assert history is not None
        self.assertEqual(len(history), 2)

    def test_get_price_history_advanced(self) -> None:
        df = pd.DataFrame({"Close": [10.0, 11.0, 12.0]})
        stub = _StubTicker(history_df=df)
        with patch.object(yfinance_tools, "_ticker", return_value=stub):
            history = yfinance_tools.get_price_history_advanced(
                "AAPL",
                start_date="2026-01-01",
                end_date="2026-01-31",
                interval="1d",
            )
        self.assertIsNotNone(history)
        assert history is not None
        self.assertEqual(float(history["Close"].iloc[-1]), 12.0)

    def test_calculate_technical_indicators(self) -> None:
        df = pd.DataFrame({"Close": [float(x) for x in range(1, 80)]})
        out = yfinance_tools.calculate_technical_indicators(df)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("RSI", out.columns)
        self.assertIn("Change_5d", out.columns)
        self.assertIn("Volatility", out.columns)

    def test_get_price_history_returns_none_when_empty(self) -> None:
        stub = _StubTicker(history_df=pd.DataFrame())
        with patch.object(yfinance_tools, "_ticker", return_value=stub):
            history = yfinance_tools.get_price_history("AAPL")
        self.assertIsNone(history)


if __name__ == "__main__":
    unittest.main()
