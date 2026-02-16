from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int, *, min_value: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        value = default
    else:
        try:
            value = int(raw.strip())
        except ValueError as exc:
            raise ValueError(f"Variable {name} invalide (entier attendu): {raw!r}") from exc
    if min_value is not None and value < min_value:
        raise ValueError(f"Variable {name} invalide (>= {min_value} attendu): {value!r}")
    return value


def _resolve_repo_path(repo_root: Path, raw: str | None, default: str) -> Path:
    value = (raw or default).strip()
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _env_value(names: list[str]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


@dataclass(frozen=True)
class BotConfig:
    discord_token: str
    discord_channel_id: int | None
    report_interval_minutes: int
    timezone_name: str
    repo_root: Path
    runtime_history_file: Path
    trade_history_file: Path
    artifacts_dir: Path
    responses_dir: Path
    keep_alive_host: str
    keep_alive_port: int
    enable_keep_alive: bool
    max_positions_in_report: int
    alpaca_api_key: str | None
    alpaca_api_secret: str | None
    alpaca_paper: bool

    @staticmethod
    def from_env(repo_root: Path | None = None) -> "BotConfig":
        root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
        load_dotenv(dotenv_path=root / ".env", override=False)

        channel_raw = (os.environ.get("DISCORD_CHANNEL_ID") or "").strip()
        channel_id = int(channel_raw) if channel_raw.isdigit() else None

        discord_token = (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()
        report_interval_minutes = _env_int("BOT_REPORT_INTERVAL_MINUTES", 60, min_value=1)
        keep_alive_port_default = _env_int("PORT", 8000, min_value=1)
        keep_alive_port = _env_int("KEEP_ALIVE_PORT", keep_alive_port_default, min_value=1)
        keep_alive_host = (os.environ.get("KEEP_ALIVE_HOST") or "0.0.0.0").strip()
        max_positions = _env_int("BOT_MAX_POSITIONS_IN_REPORT", 8, min_value=1)

        alpaca_api_key = _env_value(["ALPACA_API_KEY", "APCA_API_KEY_ID"])
        alpaca_api_secret = _env_value(
            ["ALPACA_API_SECRET", "ALPACA_SECRET", "APCA_API_SECRET_KEY"]
        )

        return BotConfig(
            discord_token=discord_token,
            discord_channel_id=channel_id,
            report_interval_minutes=report_interval_minutes,
            timezone_name=(os.environ.get("BOT_TIMEZONE") or "Europe/Paris").strip(),
            repo_root=root,
            runtime_history_file=_resolve_repo_path(
                root,
                os.environ.get("BOT_RUNTIME_HISTORY_FILE"),
                "runtime_history/run_v2_terminal_events.jsonl",
            ),
            trade_history_file=_resolve_repo_path(
                root,
                os.environ.get("BOT_TRADE_HISTORY_FILE"),
                "runtime_history/run_v2_trade_events.jsonl",
            ),
            artifacts_dir=_resolve_repo_path(
                root,
                os.environ.get("BOT_ARTIFACTS_DIR"),
                "pipeline_runs_v2",
            ),
            responses_dir=_resolve_repo_path(
                root,
                os.environ.get("BOT_RESPONSES_DIR"),
                "responses",
            ),
            keep_alive_host=keep_alive_host,
            keep_alive_port=keep_alive_port,
            enable_keep_alive=_env_bool("BOT_ENABLE_KEEP_ALIVE", True),
            max_positions_in_report=max_positions,
            alpaca_api_key=alpaca_api_key,
            alpaca_api_secret=alpaca_api_secret,
            alpaca_paper=_env_bool("ALPACA_PAPER", True),
        )
