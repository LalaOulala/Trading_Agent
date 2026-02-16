from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_RUN_V2_SESSION_DIR = Path("session_transcripts")


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _session_filename(prefix: str = "run_v2") -> str:
    # Eurodate: JJ-MM-AAAA_HH-MM-SS
    stamp = _now_local().strftime("%d-%m-%Y_%H-%M-%S")
    return f"{prefix}_session_{stamp}.md"


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


@dataclass
class SessionMarkdownLogger:
    session_file: Path

    @classmethod
    def start_new(
        cls,
        *,
        base_dir: Path,
        query: str,
        args_dict: dict[str, Any],
        prefix: str = "run_v2",
    ) -> "SessionMarkdownLogger":
        base_dir.mkdir(parents=True, exist_ok=True)
        path = base_dir / _session_filename(prefix=prefix)

        started_at = _now_local().strftime("%Y-%m-%d %H:%M:%S %Z")
        args_lines = [f"- `{key}`: `{value}`" for key, value in sorted(args_dict.items())]

        content = [
            "# Session Trading Agent V2",
            "",
            f"- Démarrée: {started_at}",
            f"- Query: `{query}`",
            "",
            "## Paramètres CLI",
            *args_lines,
            "",
            "---",
            "",
        ]
        path.write_text("\n".join(content), encoding="utf-8")
        return cls(session_file=path)

    def _append(self, lines: list[str]) -> None:
        with self.session_file.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    def log_cli_message(self, *, message: str, cycle: int | None = None) -> None:
        cycle_txt = f"cycle {cycle}" if cycle is not None else "global"
        self._append(
            [
                f"### CLI ({cycle_txt})",
                "```text",
                _to_text(message),
                "```",
                "",
            ]
        )

    def log_agent_trace(self, *, step: str, trace: dict[str, Any], cycle: int | None = None) -> None:
        cycle_suffix = f" — cycle {cycle}" if cycle is not None else ""
        prompt = _to_text(trace.get("prompt"))
        response = _to_text(trace.get("response"))
        error = _to_text(trace.get("error"))

        lines = [
            f"## Agent `{step}`{cycle_suffix}",
            "",
            "### Prompt",
            "```text",
            prompt,
            "```",
            "",
            "### Réponse",
            "```text",
            response,
            "```",
            "",
        ]
        if error:
            lines.extend(
                [
                    "### Erreur",
                    "```text",
                    error,
                    "```",
                    "",
                ]
            )
        lines.append("---")
        lines.append("")
        self._append(lines)

    def log_cycle_artifact(
        self,
        *,
        cycle: int | None,
        summary_message: str,
        artifact_path: Path,
        final_decision: dict[str, Any] | None,
        execution_report: dict[str, Any] | None,
    ) -> None:
        cycle_suffix = f"cycle {cycle}" if cycle is not None else "run unique"
        self._append(
            [
                f"## Résumé {cycle_suffix}",
                "",
                "### Synthèse CLI",
                "```text",
                _to_text(summary_message),
                "```",
                "",
                f"- Artifact: `{artifact_path}`",
                "",
                "### Final Decision",
                "```json",
                _to_text(final_decision),
                "```",
                "",
                "### Execution Report",
                "```json",
                _to_text(execution_report),
                "```",
                "",
                "---",
                "",
            ]
        )

    def finalize(self, *, reason: str) -> None:
        ended_at = _now_local().strftime("%Y-%m-%d %H:%M:%S %Z")
        self._append(
            [
                "## Fin de session",
                f"- Terminée: {ended_at}",
                f"- Raison: {reason}",
                "",
            ]
        )
