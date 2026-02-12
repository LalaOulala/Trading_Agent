from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from trading_pipeline.models import FreshMarketSnapshot, FreshSignal


@dataclass(frozen=True)
class CollectorResult:
    signals: list[FreshSignal]
    notes: list[str] = field(default_factory=list)


class WebCollector(ABC):
    @abstractmethod
    def collect(self, query: str) -> CollectorResult:
        raise NotImplementedError


class SocialCollector(ABC):
    @abstractmethod
    def collect(self, query: str) -> CollectorResult:
        raise NotImplementedError


class FreshDataCollector(ABC):
    @abstractmethod
    def collect(self, query: str) -> FreshMarketSnapshot:
        raise NotImplementedError
