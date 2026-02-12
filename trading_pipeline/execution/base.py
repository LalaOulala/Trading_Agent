from __future__ import annotations

from abc import ABC, abstractmethod

from trading_pipeline.models import ExecutionReport, FinalDecision


class TradeExecutor(ABC):
    @abstractmethod
    def execute(self, decision: FinalDecision) -> ExecutionReport:
        raise NotImplementedError
