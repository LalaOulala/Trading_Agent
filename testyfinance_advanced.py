#!/usr/bin/env python3
"""
Test Yahoo Finance avancé (intervalles/périodes/dates custom).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from yfinance_tools import get_price_history, get_price_history_advanced


def save(symbol: str, history, suffix: str, folder: str = "price_history") -> str | None:
    try:
        os.makedirs(folder, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(folder, f"{symbol}_history_{ts}{suffix}.csv")
        history.to_csv(path, index=True)
        print(f"  saved: {path}")
        return path
    except Exception as exc:
        print(f"  save error: {exc}")
        return None


def _test_interval(symbol: str, period: str, interval: str, suffix: str) -> None:
    history = get_price_history(symbol, period=period, interval=interval)
    if history is None:
        print(f"  {period}/{interval}: no data")
        return
    print(f"  {period}/{interval}: {len(history)} rows")
    save(symbol, history, suffix=suffix)


def _test_custom(symbol: str, start: str, end: str, interval: str, suffix: str) -> None:
    history = get_price_history_advanced(
        symbol,
        start_date=start,
        end_date=end,
        interval=interval,
    )
    if history is None:
        print(f"  custom {start}->{end} {interval}: no data")
        return
    print(f"  custom {start}->{end} {interval}: {len(history)} rows")
    save(symbol, history, suffix=suffix)


def main() -> None:
    symbol = "AAPL"
    print(f"=== Test YFinance avancé - {symbol} ===")

    for interval in ("1h", "30m", "15m", "5m"):
        _test_interval(symbol, period="1d", interval=interval, suffix=f"_1d_{interval}")

    for period in ("1mo", "3mo", "6mo", "1y"):
        _test_interval(symbol, period=period, interval="1d", suffix=f"_{period}_1d")

    _test_interval(symbol, period="5d", interval="5m", suffix="_5d_5m")
    _test_interval(symbol, period="5d", interval="1m", suffix="_5d_1m")

    today = datetime.now()
    end_date = today.strftime("%Y-%m-%d")
    start_30d = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    start_7d = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    start_ytd = f"{today.year}-01-01"

    _test_custom(symbol, start_30d, end_date, "1d", "_30days_custom")
    _test_custom(symbol, start_ytd, end_date, "1d", "_ytd_custom")
    _test_custom(symbol, start_7d, end_date, "1h", "_7days_1h")


if __name__ == "__main__":
    main()
