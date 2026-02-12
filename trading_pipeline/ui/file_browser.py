from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_pipeline.ui.dashboard_data import EUROPE_TZ, format_euro_datetime


_TS_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")


def _extract_timestamp(path: Path) -> datetime | None:
    candidates = (
        path.stem,
        path.name,
        path.parent.name,
        str(path.relative_to(path.anchor)) if path.is_absolute() else str(path),
    )
    for candidate in candidates:
        match = _TS_PATTERN.search(candidate)
        if not match:
            continue
        try:
            local_dt = datetime.strptime(match.group(1), "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            continue
        return EUROPE_TZ.localize(local_dt).astimezone(timezone.utc)
    return None


def _safe_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except Exception:
        return str(path.resolve())


def list_log_files(
    repo_root: Path,
    *,
    include_dirs: tuple[str, ...] = ("pipeline_runs_v2", "responses", "reflex_trader"),
    extensions: tuple[str, ...] = (".json", ".txt"),
    max_items: int = 700,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    normalized_ext = {ext.lower() for ext in extensions}

    for dirname in include_dirs:
        base = (repo_root / dirname).resolve()
        if not base.exists() or not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in normalized_ext:
                continue
            timestamp = _extract_timestamp(path)
            if timestamp is None:
                timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

            rel_path = _safe_relative(path, repo_root)
            rows.append(
                {
                    "path": path.resolve(),
                    "path_str": str(path.resolve()),
                    "relative_path": rel_path,
                    "category": dirname,
                    "suffix": path.suffix.lower(),
                    "size_bytes": int(path.stat().st_size),
                    "datetime_utc": timestamp,
                    "datetime_eu": format_euro_datetime(timestamp),
                }
            )
            if len(rows) >= max_items:
                break
        if len(rows) >= max_items:
            break

    rows.sort(key=lambda row: row["datetime_utc"], reverse=True)
    return rows


def read_text_file(path: Path, *, max_chars: int = 500_000) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars] + "\n\n[Truncated]"
    return text


def parse_json_text(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def format_file_button_label(row: dict[str, Any]) -> str:
    size_kb = row.get("size_bytes", 0) / 1024
    return f"{row.get('datetime_eu', 'N/A')} | {row.get('relative_path', '?')} ({size_kb:.1f} KB)"

