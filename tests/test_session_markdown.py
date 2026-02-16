from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trading_pipeline.context.session_markdown import SessionMarkdownLogger


class SessionMarkdownLoggerTests(unittest.TestCase):
    def test_logger_writes_session_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "session_transcripts"
            logger = SessionMarkdownLogger.start_new(
                base_dir=base,
                query="S&P 500 market drivers today",
                args_dict={"once": True, "interval_seconds": 300},
                prefix="run_v2",
            )

            logger.log_cli_message(message="[V2 Pipeline] cycle #1 started", cycle=1)
            logger.log_agent_trace(
                step="pre_analysis",
                trace={"prompt": "PROMPT", "response": "RESPONSE", "error": ""},
                cycle=1,
            )
            logger.log_cycle_artifact(
                cycle=1,
                summary_message="[V2 Pipeline] done",
                artifact_path=Path("pipeline_runs_v2/2026-02-14_10-00-00.json"),
                final_decision={"action": "HOLD"},
                execution_report={"status": "skipped"},
            )
            logger.finalize(reason="once_completed")

            content = logger.session_file.read_text(encoding="utf-8")
            self.assertIn("# Session Trading Agent V2", content)
            self.assertIn("## Agent `pre_analysis`", content)
            self.assertIn("## Résumé cycle 1", content)
            self.assertIn("## Fin de session", content)


if __name__ == "__main__":
    unittest.main()
