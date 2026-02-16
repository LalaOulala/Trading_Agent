from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bot.config import BotConfig


_TAVILY_CREDITS_RE = re.compile(r"Tavily total credits used:\s*([0-9]+(?:\.[0-9]+)?)")
_TOTAL_TOKENS_RE = re.compile(r"^\s*total_tokens:\s*(\d+)\s*$", flags=re.MULTILINE)
_X_SEARCH_RE = re.compile(r"SERVER_SIDE_TOOL_X_SEARCH['\"]?\s*:\s*(\d+)")


@dataclass(frozen=True)
class TradeSummary:
    trade_event_count: int
    execution_status_counts: dict[str, int]
    action_counts: dict[str, int]
    total_orders: int
    top_symbols: list[tuple[str, int]]
    last_error_message: str | None


@dataclass(frozen=True)
class ApiCostSummary:
    artifacts_considered: int
    tavily_credits: float
    response_debug_files_considered: int
    xai_total_tokens: int
    x_search_calls: int


def _parse_iso_datetime(raw: Any) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_jsonl_since(path: Path, *, since_utc: datetime) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            timestamp = _parse_iso_datetime(item.get("timestamp_utc"))
            if timestamp is None:
                continue
            if timestamp < since_utc:
                continue
            out.append(item)
    return out


def summarize_trade_events(events: list[dict[str, Any]]) -> TradeSummary:
    execution_status: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    symbols: Counter[str] = Counter()
    total_orders = 0
    last_error: str | None = None

    for event in events:
        final_decision = event.get("final_decision")
        if isinstance(final_decision, dict):
            action = str(final_decision.get("action") or "").strip().upper()
            if action:
                actions[action] += 1
            symbols_list = final_decision.get("symbols")
            if isinstance(symbols_list, list):
                for symbol in symbols_list:
                    sym = str(symbol or "").strip().upper()
                    if sym:
                        symbols[sym] += 1

        execution = event.get("execution_report")
        if isinstance(execution, dict):
            status = str(execution.get("status") or "").strip().lower()
            if status:
                execution_status[status] += 1
                if status == "error":
                    message = str(execution.get("message") or "").strip()
                    if message:
                        last_error = message
            details = execution.get("details")
            if isinstance(details, list):
                total_orders += len(details)
                for detail in details:
                    if not isinstance(detail, dict):
                        continue
                    sym = str(detail.get("symbol") or "").strip().upper()
                    if sym:
                        symbols[sym] += 1

    return TradeSummary(
        trade_event_count=len(events),
        execution_status_counts=dict(execution_status),
        action_counts=dict(actions),
        total_orders=total_orders,
        top_symbols=symbols.most_common(6),
        last_error_message=last_error,
    )


def _extract_tavily_credits(notes: list[Any]) -> float:
    total = 0.0
    for note in notes:
        text = str(note or "")
        match = _TAVILY_CREDITS_RE.search(text)
        if not match:
            continue
        try:
            total += float(match.group(1))
        except ValueError:
            continue
    return total


def estimate_api_costs(
    *,
    artifacts_dir: Path,
    responses_dir: Path,
    since_utc: datetime,
) -> ApiCostSummary:
    tavily_credits = 0.0
    artifacts_considered = 0

    if artifacts_dir.exists():
        for path in artifacts_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            generated_at = _parse_iso_datetime(payload.get("generated_at"))
            if generated_at is not None and generated_at < since_utc:
                continue
            fresh_snapshot = payload.get("fresh_snapshot")
            notes = fresh_snapshot.get("notes") if isinstance(fresh_snapshot, dict) else []
            if not isinstance(notes, list):
                notes = []
            tavily_credits += _extract_tavily_credits(notes)
            artifacts_considered += 1

    response_debug_files_considered = 0
    xai_total_tokens = 0
    x_search_calls = 0

    if responses_dir.exists():
        for path in responses_dir.glob("*/debug.txt"):
            mtime_utc = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime_utc < since_utc:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for raw_tokens in _TOTAL_TOKENS_RE.findall(text):
                try:
                    xai_total_tokens += int(raw_tokens)
                except ValueError:
                    continue
            for raw_calls in _X_SEARCH_RE.findall(text):
                try:
                    x_search_calls += int(raw_calls)
                except ValueError:
                    continue
            response_debug_files_considered += 1

    return ApiCostSummary(
        artifacts_considered=artifacts_considered,
        tavily_credits=tavily_credits,
        response_debug_files_considered=response_debug_files_considered,
        xai_total_tokens=xai_total_tokens,
        x_search_calls=x_search_calls,
    )


def load_portfolio_snapshot(
    *,
    api_key: str | None,
    api_secret: str | None,
    paper: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    if not api_key or not api_secret:
        return None, "credentials Alpaca absents"

    try:
        from alpaca.trading.client import TradingClient
    except Exception as exc:  # pragma: no cover
        return None, f"alpaca-py indisponible ({type(exc).__name__}: {exc})"

    try:
        client = TradingClient(api_key=api_key, secret_key=api_secret, paper=paper)
        account = client.get_account()
        positions = client.get_all_positions()
    except Exception as exc:
        return None, f"snapshot indisponible ({type(exc).__name__}: {exc})"

    snapshot = {
        "status": str(getattr(account, "status", "n/a")),
        "equity": getattr(account, "equity", None),
        "cash": getattr(account, "cash", None),
        "buying_power": getattr(account, "buying_power", None),
        "shorting_enabled": getattr(account, "shorting_enabled", None),
        "positions": [
            {
                "symbol": getattr(position, "symbol", None),
                "qty": getattr(position, "qty", None),
                "side": str(getattr(position, "side", "")),
                "market_value": getattr(position, "market_value", None),
            }
            for position in positions
        ],
    }
    return snapshot, None


def _format_counter(values: dict[str, int]) -> str:
    if not values:
        return "n/a"
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    return " | ".join(f"{name}={count}" for name, count in ordered)


def build_hourly_report(config: BotConfig, *, now_utc: datetime | None = None) -> str:
    now = now_utc or datetime.now(timezone.utc)
    since = now - timedelta(minutes=config.report_interval_minutes)

    trade_events = _load_jsonl_since(config.trade_history_file, since_utc=since)
    runtime_events = _load_jsonl_since(config.runtime_history_file, since_utc=since)

    trade_summary = summarize_trade_events(trade_events)
    api_summary = estimate_api_costs(
        artifacts_dir=config.artifacts_dir,
        responses_dir=config.responses_dir,
        since_utc=since,
    )
    portfolio_snapshot, portfolio_error = load_portfolio_snapshot(
        api_key=config.alpaca_api_key,
        api_secret=config.alpaca_api_secret,
        paper=config.alpaca_paper,
    )

    top_symbols_txt = ", ".join(f"{symbol}({count})" for symbol, count in trade_summary.top_symbols)
    if not top_symbols_txt:
        top_symbols_txt = "n/a"

    lines = [
        f"Trading Agent Report ({config.report_interval_minutes} min)",
        f"Période UTC: {since.strftime('%Y-%m-%d %H:%M')} -> {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        "Ordres et exécution",
        f"- Événements trade: {trade_summary.trade_event_count}",
        f"- Statuts exécution: {_format_counter(trade_summary.execution_status_counts)}",
        f"- Actions: {_format_counter(trade_summary.action_counts)}",
        f"- Total ordres détaillés: {trade_summary.total_orders}",
        f"- Symboles les plus vus: {top_symbols_txt}",
    ]

    if trade_summary.last_error_message:
        lines.append(f"- Dernière erreur broker: {trade_summary.last_error_message}")

    lines.extend(
        [
            f"- Événements runtime (fenêtre): {len(runtime_events)}",
            "",
            "Portefeuille Alpaca",
        ]
    )

    if portfolio_error:
        lines.append(f"- Indisponible: {portfolio_error}")
    elif portfolio_snapshot is None:
        lines.append("- Indisponible")
    else:
        lines.append(f"- Status: {portfolio_snapshot.get('status')}")
        lines.append(f"- Equity: {portfolio_snapshot.get('equity')}")
        lines.append(f"- Cash: {portfolio_snapshot.get('cash')}")
        lines.append(f"- Buying power: {portfolio_snapshot.get('buying_power')}")
        lines.append(f"- Shorting enabled: {portfolio_snapshot.get('shorting_enabled')}")

        positions = portfolio_snapshot.get("positions")
        if isinstance(positions, list) and positions:
            lines.append("- Positions:")
            for position in positions[: config.max_positions_in_report]:
                lines.append(
                    "  - "
                    f"{position.get('symbol')} qty={position.get('qty')} "
                    f"side={position.get('side')} mv={position.get('market_value')}"
                )
            if len(positions) > config.max_positions_in_report:
                remaining = len(positions) - config.max_positions_in_report
                lines.append(f"  - ... ({remaining} positions supplémentaires)")
        else:
            lines.append("- Positions: aucune")

    lines.extend(
        [
            "",
            "Coûts API (estimation fichiers locaux)",
            f"- Tavily credits: {api_summary.tavily_credits:g} (artefacts analysés: {api_summary.artifacts_considered})",
            f"- xAI total tokens: {api_summary.xai_total_tokens} (debug files: {api_summary.response_debug_files_considered})",
            f"- x_search calls: {api_summary.x_search_calls}",
            "",
            "Note: ce rapport est un snapshot technique. La logique fine sera ajustée ensuite.",
        ]
    )

    return "\n".join(lines).strip()


def split_discord_message(text: str, *, max_len: int = 1900) -> list[str]:
    message = (text or "").strip()
    if not message:
        return []
    if len(message) <= max_len:
        return [message]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in message.splitlines():
        line_len = len(line) + 1
        if current and current_len + line_len > max_len:
            chunks.append("\n".join(current).strip())
            current = [line]
            current_len = line_len
            continue
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current).strip())
    return [chunk for chunk in chunks if chunk]
