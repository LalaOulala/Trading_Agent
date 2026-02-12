from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def build_run_command(
    *,
    query: str,
    web_topic: str,
    web_time_range: str,
    web_max_results: int,
    financial_provider: str,
    interval_seconds: int,
    execute_live: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "run_v2.py"),
        "--query",
        query,
        "--web-topic",
        web_topic,
        "--web-time-range",
        web_time_range,
        "--web-max-results",
        str(web_max_results),
        "--financial-provider",
        financial_provider,
        "--once",
        "--interval-seconds",
        str(interval_seconds),
    ]

    if execute_live:
        # UI mode: no stdin confirmation available.
        cmd.extend(["--execute-orders", "--auto-confirm-orders", "--stop-if-market-closed"])
    return cmd


def run_workflow_once(
    *,
    query: str,
    web_topic: str,
    web_time_range: str,
    web_max_results: int,
    financial_provider: str,
    interval_seconds: int,
    execute_live: bool,
) -> dict[str, Any]:
    cmd = build_run_command(
        query=query,
        web_topic=web_topic,
        web_time_range=web_time_range,
        web_max_results=web_max_results,
        financial_provider=financial_provider,
        interval_seconds=interval_seconds,
        execute_live=execute_live,
    )
    completed = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return {
        "cmd": " ".join(shlex.quote(part) for part in cmd),
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
    }


def is_market_closed_message(text: str) -> bool:
    normalized = (text or "").lower()
    return "marché est fermé" in normalized or "marche est ferme" in normalized


def evaluate_run_feedback(
    *,
    run_result: dict[str, Any] | None,
    latest_artifact: dict[str, Any] | None,
) -> tuple[str, str]:
    if not run_result:
        return "info", "Aucun lancement manuel dans cette session."

    if int(run_result.get("returncode", 1)) != 0:
        return "error", "Le workflow a retourne une erreur shell. Voir les logs."

    stdout = str(run_result.get("stdout", ""))
    stderr = str(run_result.get("stderr", ""))
    merged = f"{stdout}\n{stderr}".strip()
    if is_market_closed_message(merged):
        return "warning", "Le marche est ferme: aucune tentative d'ordre live n'a ete envoyee."

    execution = (latest_artifact or {}).get("execution_report", {})
    status = str(execution.get("status", "")).lower()
    message = str(execution.get("message", ""))

    if status == "error":
        return "error", f"Erreur execution broker: {message or 'inconnue'}"
    if status == "skipped" and is_market_closed_message(message):
        return "warning", message

    return "success", "Workflow termine."

