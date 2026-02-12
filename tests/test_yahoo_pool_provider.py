from __future__ import annotations

import unittest
from unittest.mock import patch

from trading_pipeline.financial.yahoo_pool import YahooFinancePoolProvider


class YahooPoolProviderTests(unittest.TestCase):
    def test_fetch_with_data(self) -> None:
        provider = YahooFinancePoolProvider()
        with patch(
            "trading_pipeline.financial.yahoo_pool.get_current_price",
            side_effect=lambda s: 100.0 if s == "AAPL" else None,
        ), patch(
            "trading_pipeline.financial.yahoo_pool._compute_changes",
            side_effect=lambda s: (1.2, 2.4) if s == "AAPL" else (None, None),
        ), patch(
            "trading_pipeline.financial.yahoo_pool.get_detailed_info",
            return_value={"company_name": "Apple", "sector": "Tech"},
        ):
            snapshot = provider.fetch(["AAPL"])

        self.assertEqual(snapshot.source, "yahoo_finance_pool")
        self.assertIn("AAPL", snapshot.symbols_data)
        self.assertEqual(snapshot.symbols_data["AAPL"]["status"], "ok")
        self.assertEqual(snapshot.missing_symbols, [])

    def test_fetch_marks_missing_symbol(self) -> None:
        provider = YahooFinancePoolProvider()
        with patch("trading_pipeline.financial.yahoo_pool.get_current_price", return_value=None), patch(
            "trading_pipeline.financial.yahoo_pool._compute_changes",
            return_value=(None, None),
        ), patch(
            "trading_pipeline.financial.yahoo_pool.get_detailed_info",
            return_value=None,
        ):
            snapshot = provider.fetch(["MSFT"])

        self.assertEqual(snapshot.symbols_data["MSFT"]["status"], "no_data")
        self.assertEqual(snapshot.missing_symbols, ["MSFT"])


if __name__ == "__main__":
    unittest.main()
