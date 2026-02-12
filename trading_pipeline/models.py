from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


Action = Literal["LONG", "SHORT", "HOLD"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class FreshSignal:
    source: str
    title: str
    url: str
    snippet: str = ""
    published_at: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FreshMarketSnapshot:
    generated_at: str
    web_signals: list[FreshSignal]
    social_signals: list[FreshSignal]
    notes: list[str] = field(default_factory=list)

    @staticmethod
    def empty(note: str = "") -> "FreshMarketSnapshot":
        notes = [note] if note else []
        return FreshMarketSnapshot(
            generated_at=utc_now_iso(),
            web_signals=[],
            social_signals=[],
            notes=notes,
        )


@dataclass(frozen=True)
class PreAnalysis:
    summary: str
    key_drivers: list[str]
    candidate_symbols: list[str]
    risks: list[str]
    confidence: Literal["low", "medium", "high"]


@dataclass(frozen=True)
class FocusSelection:
    symbols: list[str]
    rationale_by_symbol: dict[str, str]
    questions: list[str]


@dataclass(frozen=True)
class FinancialSnapshot:
    source: str
    asof: str
    symbols_data: dict[str, dict[str, Any]]
    missing_symbols: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FinalDecision:
    action: Action
    symbols: list[str]
    thesis: str
    risk_controls: list[str]
    confidence: Literal["low", "medium", "high"]
    should_execute: bool
    orders: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionReport:
    status: Literal["skipped", "dry_run", "submitted", "error"]
    broker: str
    details: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""
