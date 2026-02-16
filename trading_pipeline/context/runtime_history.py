from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUN_V2_TERMINAL_HISTORY_FILE = Path("runtime_history/run_v2_terminal_events.jsonl")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_runtime_event(
    history_file: Path,
    *,
    event_type: str,
    message: str,
    cycle: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """
    Ajoute un événement runtime dans un fichier JSONL.

    Chaque ligne est un objet JSON avec horodatage UTC, type d'événement et message.
    """
    event: dict[str, Any] = {
        "timestamp_utc": _utc_now_iso(),
        "event_type": event_type,
        "message": message,
    }
    if cycle is not None:
        event["cycle"] = cycle
    if payload:
        event["payload"] = payload

    history_file.parent.mkdir(parents=True, exist_ok=True)
    with history_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_recent_runtime_events(
    history_file: Path,
    *,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """
    Charge les `limit` derniers événements runtime depuis un fichier JSONL.

    - Ignore les lignes vides ou JSON invalides.
    - Retourne les événements du plus ancien au plus récent dans la fenêtre demandée.
    """
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
