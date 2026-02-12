from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import FinancialDataProvider
from trading_pipeline.models import FinancialSnapshot, utc_now_iso
from yfinance_tools import get_current_price, get_detailed_info, get_price_history


def _compute_changes(symbol: str) -> tuple[float | None, float | None]:
    history = get_price_history(symbol, period="5d", interval="1d")
    if history is None or history.empty or "Close" not in history.columns:
        return None, None

    closes = history["Close"].dropna()
    if closes.empty:
        return None, None

    last = float(closes.iloc[-1])
    change_1d_pct: float | None = None
    change_5d_pct: float | None = None

    if len(closes) >= 2:
        prev = float(closes.iloc[-2])
        if prev != 0:
            change_1d_pct = ((last - prev) / prev) * 100
    if len(closes) >= 5:
        first_5d = float(closes.iloc[-5])
        if first_5d != 0:
            change_5d_pct = ((last - first_5d) / first_5d) * 100
    elif len(closes) >= 2:
        first = float(closes.iloc[0])
        if first != 0:
            change_5d_pct = ((last - first) / first) * 100

    return change_1d_pct, change_5d_pct


@dataclass
class YahooFinancePoolProvider(FinancialDataProvider):
    """
    Provider financier branché sur le pool Yahoo Finance (yfinance_tools).
    """

    source_name: str = "yahoo_finance_pool"

    def fetch(self, symbols: list[str]) -> FinancialSnapshot:
        normalized = [s.upper().strip() for s in symbols if s and s.strip()]
        symbols_data: dict[str, dict[str, Any]] = {}
        missing_symbols: list[str] = []
        notes: list[str] = []

        for sym in normalized:
            price = get_current_price(sym)
            change_1d_pct, change_5d_pct = _compute_changes(sym)
            details = get_detailed_info(sym) or {}

            payload: dict[str, Any] = {
                "last_price": price,
                "change_1d_pct": change_1d_pct,
                "change_5d_pct": change_5d_pct,
                "company_name": details.get("company_name"),
                "sector": details.get("sector"),
                "market_cap": details.get("market_cap"),
                "pe_ratio": details.get("pe_ratio"),
                "volume": details.get("volume"),
            }
            if (
                payload["last_price"] is None
                and payload["change_1d_pct"] is None
                and payload["change_5d_pct"] is None
            ):
                missing_symbols.append(sym)
                payload["status"] = "no_data"
            else:
                payload["status"] = "ok"

            symbols_data[sym] = payload

        notes.append(
            "Yahoo pool: données prix + variations + infos entreprise collectées via yfinance_tools."
        )
        if missing_symbols:
            notes.append(f"Symbols sans data exploitable: {', '.join(missing_symbols)}")

        return FinancialSnapshot(
            source=self.source_name,
            asof=utc_now_iso(),
            symbols_data=symbols_data,
            missing_symbols=missing_symbols,
            notes=notes,
        )
