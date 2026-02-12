#!/usr/bin/env python3
"""
Smoke test Yahoo Finance (pool local).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from trading_pipeline.financial.yfinance_tools import (
    get_current_price,
    get_detailed_info,
    get_market_status,
    get_price_history,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def save_price_history(symbol: str, folder: str, history) -> str | None:
    try:
        os.makedirs(folder, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(folder, f"{symbol}_history_{ts}.csv")
        history.to_csv(path, index=True)
        return path
    except Exception:
        return None


def test_symbol(symbol: str = "AAPL") -> None:
    print(f"=== Test YFinance - {symbol} ===")

    price = get_current_price(symbol)
    print(f"Prix actuel: {price}" if price is not None else "Prix actuel: indisponible")

    history = get_price_history(symbol, period="5d", interval="1d")
    if history is None or history.empty:
        print("Historique: indisponible")
    else:
        print(f"Historique: {len(history)} points")
        saved = save_price_history(
            symbol,
            folder=str(REPO_ROOT / "price_history"),
            history=history,
        )
        if saved:
            print(f"CSV sauvegardé: {saved}")

    info = get_detailed_info(symbol)
    if info:
        print(f"Entreprise: {info.get('company_name')}")
        print(f"Secteur: {info.get('sector')}")
        print(f"P/E: {info.get('pe_ratio')}")
    else:
        print("Infos détaillées: indisponibles")

    is_open, status = get_market_status()
    print(f"Statut marché: {status} ({is_open})")


if __name__ == "__main__":
    test_symbol("AAPL")
