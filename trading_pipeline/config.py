from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Variable {name} invalide (entier attendu): {raw!r}") from exc


@dataclass(frozen=True)
class PipelineConfig:
    tavily_api_key: str | None
    xai_api_key: str | None
    alpaca_api_key: str | None
    alpaca_api_secret: str | None
    alpaca_paper: bool
    execute_orders: bool
    max_candidate_symbols: int
    max_focus_symbols: int
    output_dir: Path

    @staticmethod
    def from_env(output_dir: Path | None = None) -> "PipelineConfig":
        alpaca_key = os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY_ID")
        alpaca_secret = (
            os.environ.get("ALPACA_API_SECRET")
            or os.environ.get("ALPACA_SECRET")
            or os.environ.get("APCA_API_SECRET_KEY")
        )
        return PipelineConfig(
            tavily_api_key=os.environ.get("TAVILY_API_KEY"),
            xai_api_key=os.environ.get("XAI_API_KEY"),
            alpaca_api_key=alpaca_key,
            alpaca_api_secret=alpaca_secret,
            alpaca_paper=_env_bool("ALPACA_PAPER", True),
            execute_orders=_env_bool("PIPELINE_EXECUTE_ORDERS", False),
            max_candidate_symbols=_env_int("PIPELINE_MAX_CANDIDATES", 12),
            max_focus_symbols=_env_int("PIPELINE_MAX_FOCUS", 6),
            output_dir=output_dir or Path("pipeline_runs_v2"),
        )
