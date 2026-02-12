from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import FinancialDataProvider
from trading_pipeline.models import FinancialSnapshot, utc_now_iso


@dataclass
class YahooPlaceholderProvider(FinancialDataProvider):
    """
    Branche dédiée aux datas financières.

    Placeholder volontaire: la connexion Yahoo Finance sera branchée plus tard.
    Si `mock_file` est fourni, ce provider charge des données locales pour tests.
    """

    mock_file: Path | None = None
    source_name: str = "yahoo_placeholder"

    def _load_mock(self) -> dict[str, dict[str, Any]]:
        if not self.mock_file:
            return {}
        if not self.mock_file.exists():
            raise FileNotFoundError(f"Mock financial file introuvable: {self.mock_file}")
        data = json.loads(self.mock_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Mock financial invalide: objet JSON attendu.")
        out: dict[str, dict[str, Any]] = {}
        for symbol, payload in data.items():
            if not isinstance(symbol, str) or not isinstance(payload, dict):
                continue
            out[symbol.upper()] = payload
        return out

    def fetch(self, symbols: list[str]) -> FinancialSnapshot:
        symbols = [s.upper() for s in symbols if s.strip()]
        mock_data = self._load_mock()
        symbols_data: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        notes: list[str] = []

        for sym in symbols:
            if sym in mock_data:
                symbols_data[sym] = mock_data[sym]
                continue
            missing.append(sym)
            symbols_data[sym] = {
                "last_price": None,
                "change_1d_pct": None,
                "change_5d_pct": None,
                "status": "not_connected_yet",
            }

        if self.mock_file:
            notes.append(f"Financial mock loaded from {self.mock_file}")
        else:
            notes.append("Yahoo Finance non branché: valeurs placeholder renvoyées.")

        return FinancialSnapshot(
            source=self.source_name,
            asof=utc_now_iso(),
            symbols_data=symbols_data,
            missing_symbols=missing,
            notes=notes,
        )


@dataclass
class StaticFinancialDataProvider(FinancialDataProvider):
    """
    Provider de test: injecte un mapping statique en mémoire.
    """

    data: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_name: str = "static_test_provider"

    def fetch(self, symbols: list[str]) -> FinancialSnapshot:
        normalized = [s.upper() for s in symbols]
        symbols_data = {s: self.data.get(s, {}) for s in normalized}
        missing = [s for s in normalized if s not in self.data]
        return FinancialSnapshot(
            source=self.source_name,
            asof=utc_now_iso(),
            symbols_data=symbols_data,
            missing_symbols=missing,
            notes=[],
        )
