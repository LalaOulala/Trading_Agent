from __future__ import annotations

from abc import ABC, abstractmethod

from trading_pipeline.models import FinancialSnapshot


class FinancialDataProvider(ABC):
    @abstractmethod
    def fetch(self, symbols: list[str]) -> FinancialSnapshot:
        raise NotImplementedError
