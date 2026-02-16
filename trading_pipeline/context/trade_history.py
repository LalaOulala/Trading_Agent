from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUN_V2_TRADE_HISTORY_FILE = Path("runtime_history/run_v2_trade_events.jsonl")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_trade_event(
    history_file: Path,
    *,
    query: str,
    cycle: int | None,
    final_decision: dict[str, Any] | None,
    execution_report: dict[str, Any] | None,
    artifact_path: str | None = None,
) -> None:
    """Ajoute un événement transactionnel (décision + exécution) en JSONL."""
    event: dict[str, Any] = {
        "timestamp_utc": _utc_now_iso(),
        "query": query,
        "final_decision": final_decision or {},
        "execution_report": execution_report or {},
    }
    if cycle is not None:
        event["cycle"] = cycle
    if artifact_path:
        event["artifact_path"] = artifact_path

    history_file.parent.mkdir(parents=True, exist_ok=True)
    with history_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_recent_trade_events(
    history_file: Path,
    *,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Charge les `limit` derniers événements transactionnels valides."""
    if limit <= 0:
        return []
    if not history_file.exists():
        return []

    parsed: list[dict[str, Any]] = []
    with history_file.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                parsed.append(item)

    if len(parsed) <= limit:
        return parsed
    return parsed[-limit:]
