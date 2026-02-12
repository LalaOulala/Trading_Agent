from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytz


EUROPE_TZ = pytz.timezone("Europe/Paris")

AGENT_ORDER = (
    "FreshDataHub",
    "PreAnalysisAgent",
    "FocusTraderAgent",
    "FinancialDataProvider",
    "FinalTraderAgent",
    "AlpacaTradeExecutor",
)


def _to_short_text(raw: Any, *, max_chars: int = 160) -> str:
    text = str(raw or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def parse_iso_datetime(raw: Any) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_euro_datetime(dt: datetime | None) -> str:
    if dt is None:
        return "N/A"
    return dt.astimezone(EUROPE_TZ).strftime("%d/%m/%Y %H:%M:%S")


def _load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _parse_run_filename(path: Path) -> datetime | None:
    try:
        local_dt = datetime.strptime(path.stem, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None
    return EUROPE_TZ.localize(local_dt).astimezone(timezone.utc)


def load_artifact_records(artifacts_dir: Path, *, max_items: int = 400) -> list[dict[str, Any]]:
    if max_items <= 0:
        return []
    if not artifacts_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    for path in sorted(artifacts_dir.glob("*.json"), reverse=True):
        artifact = _load_json_file(path)
        if artifact is None:
            continue

        generated_at = parse_iso_datetime(artifact.get("generated_at")) or _parse_run_filename(path)
        records.append(
            {
                "path": path,
                "artifact": artifact,
                "generated_at": generated_at,
                "generated_at_eu": format_euro_datetime(generated_at),
            }
        )
        if len(records) >= max_items:
            break

    records.sort(
        key=lambda rec: rec["generated_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return records


def extract_timing_metrics(
    latest_record: dict[str, Any],
    *,
    interval_seconds: int,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or datetime.now(timezone.utc)
    artifact = latest_record.get("artifact", {})
    last_reflection_at: datetime | None = latest_record.get("generated_at")

    fresh_snapshot = artifact.get("fresh_snapshot", {})
    last_request_at = parse_iso_datetime(fresh_snapshot.get("generated_at"))

    request_to_reflection_seconds: float | None = None
    if last_request_at and last_reflection_at:
        request_to_reflection_seconds = max(
            (last_reflection_at - last_request_at).total_seconds(),
            0.0,
        )

    next_iteration_in_seconds: int | None = None
    if last_reflection_at and interval_seconds > 0:
        elapsed = max((now - last_reflection_at).total_seconds(), 0.0)
        next_iteration_in_seconds = max(int(interval_seconds - elapsed), 0)

    return {
        "last_request_at": last_request_at,
        "last_request_label": format_euro_datetime(last_request_at),
        "last_reflection_at": last_reflection_at,
        "last_reflection_label": format_euro_datetime(last_reflection_at),
        "request_to_reflection_seconds": request_to_reflection_seconds,
        "next_iteration_in_seconds": next_iteration_in_seconds,
    }


def _summarize_fresh_snapshot(artifact: dict[str, Any]) -> str:
    fresh = artifact.get("fresh_snapshot", {})
    web_signals = fresh.get("web_signals", [])
    social_signals = fresh.get("social_signals", [])
    notes = fresh.get("notes", [])
    note_preview = ""
    if isinstance(notes, list) and notes:
        note_preview = f" | Notes: {_to_short_text(notes[0], max_chars=70)}"
    return (
        f"Web={len(web_signals) if isinstance(web_signals, list) else 0} "
        f"Social={len(social_signals) if isinstance(social_signals, list) else 0}"
        f"{note_preview}"
    )


def _summarize_pre_analysis(artifact: dict[str, Any]) -> str:
    pre = artifact.get("pre_analysis", {})
    confidence = pre.get("confidence", "n/a")
    symbols = pre.get("candidate_symbols", [])
    summary = _to_short_text(pre.get("summary", ""), max_chars=110)
    symbol_text = ", ".join(symbols[:4]) if isinstance(symbols, list) else ""
    return f"Confidence={confidence} | Symbols={symbol_text or 'n/a'} | {summary}"


def _summarize_focus_selection(artifact: dict[str, Any]) -> str:
    focus = artifact.get("focus_selection", {})
    symbols = focus.get("symbols", [])
    questions = focus.get("questions", [])
    symbol_text = ", ".join(symbols[:6]) if isinstance(symbols, list) else "n/a"
    question_preview = ""
    if isinstance(questions, list) and questions:
        question_preview = f" | Q: {_to_short_text(questions[0], max_chars=80)}"
    return f"Focus symbols={symbol_text}{question_preview}"


def _summarize_financial_snapshot(artifact: dict[str, Any]) -> str:
    financial = artifact.get("financial_snapshot", {})
    source = financial.get("source", "n/a")
    symbols_data = financial.get("symbols_data", {})
    symbol_count = len(symbols_data) if isinstance(symbols_data, dict) else 0
    missing = financial.get("missing_symbols", [])
    missing_count = len(missing) if isinstance(missing, list) else 0
    return f"Source={source} | Symbols={symbol_count} | Missing={missing_count}"


def _summarize_final_decision(artifact: dict[str, Any]) -> str:
    final_decision = artifact.get("final_decision", {})
    action = final_decision.get("action", "n/a")
    confidence = final_decision.get("confidence", "n/a")
    should_execute = final_decision.get("should_execute", False)
    thesis = _to_short_text(final_decision.get("thesis", ""), max_chars=95)
    return f"Action={action} | Confidence={confidence} | Execute={should_execute} | {thesis}"


def _summarize_execution_report(artifact: dict[str, Any]) -> str:
    execution = artifact.get("execution_report", {})
    status = execution.get("status", "n/a")
    details = execution.get("details", [])
    detail_count = len(details) if isinstance(details, list) else 0
    message = _to_short_text(execution.get("message", ""), max_chars=95)
    return f"Status={status} | Orders={detail_count} | {message}"


def summarize_agent_reflection(artifact: dict[str, Any], *, agent_name: str) -> str:
    if agent_name == "FreshDataHub":
        return _summarize_fresh_snapshot(artifact)
    if agent_name == "PreAnalysisAgent":
        return _summarize_pre_analysis(artifact)
    if agent_name == "FocusTraderAgent":
        return _summarize_focus_selection(artifact)
    if agent_name == "FinancialDataProvider":
        return _summarize_financial_snapshot(artifact)
    if agent_name == "FinalTraderAgent":
        return _summarize_final_decision(artifact)
    if agent_name == "AlpacaTradeExecutor":
        return _summarize_execution_report(artifact)
    return "n/a"


def _agent_payload(artifact: dict[str, Any], *, agent_name: str) -> Any:
    if agent_name == "FreshDataHub":
        return artifact.get("fresh_snapshot", {})
    if agent_name == "PreAnalysisAgent":
        return artifact.get("pre_analysis", {})
    if agent_name == "FocusTraderAgent":
        return artifact.get("focus_selection", {})
    if agent_name == "FinancialDataProvider":
        return artifact.get("financial_snapshot", {})
    if agent_name == "FinalTraderAgent":
        return artifact.get("final_decision", {})
    if agent_name == "AlpacaTradeExecutor":
        return artifact.get("execution_report", {})
    return {}


def build_agent_histories(
    records: list[dict[str, Any]],
    *,
    max_rows_per_agent: int = 300,
) -> dict[str, list[dict[str, Any]]]:
    histories: dict[str, list[dict[str, Any]]] = {agent: [] for agent in AGENT_ORDER}
    if max_rows_per_agent <= 0:
        return histories

    for record in records:
        artifact = record.get("artifact", {})
        run_file = record.get("path", Path("unknown.json")).name
        artifact_path = str(record.get("path", Path("unknown.json")))
        run_date = record.get("generated_at_eu", "N/A")
        query = str(artifact.get("query", ""))

        for agent_name in AGENT_ORDER:
            agent_rows = histories[agent_name]
            if len(agent_rows) >= max_rows_per_agent:
                continue
            agent_rows.append(
                {
                    "date_eu": run_date,
                    "run_file": run_file,
                    "artifact_path": artifact_path,
                    "query": query,
                    "reflection": summarize_agent_reflection(artifact, agent_name=agent_name),
                    "raw_section": _agent_payload(artifact, agent_name=agent_name),
                }
            )
    return histories


def build_orders_history(
    records: list[dict[str, Any]],
    *,
    max_rows: int = 250,
) -> list[dict[str, Any]]:
    if max_rows <= 0:
        return []

    rows: list[dict[str, Any]] = []
    for record in records:
        artifact = record.get("artifact", {})
        execution = artifact.get("execution_report", {})
        status = str(execution.get("status", "n/a"))
        message = str(execution.get("message", ""))
        run_file = record.get("path", Path("unknown.json")).name
        run_date = record.get("generated_at_eu", "N/A")
        details = execution.get("details", [])

        if not isinstance(details, list) or not details:
            continue

        for detail in details:
            rows.append(
                {
                    "date_eu": run_date,
                    "run_file": run_file,
                    "status": status,
                    "symbol": detail.get("symbol", "n/a"),
                    "side": detail.get("side", "n/a"),
                    "qty": detail.get("qty", "n/a"),
                    "message": _to_short_text(message, max_chars=90),
                }
            )
            if len(rows) >= max_rows:
                return rows

    return rows
