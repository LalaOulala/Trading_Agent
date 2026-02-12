from __future__ import annotations

import unittest

from trading_pipeline.ui.workflow_runner import (
    build_run_command,
    evaluate_run_feedback,
    is_market_closed_message,
)


class WorkflowRunnerTests(unittest.TestCase):
    def test_build_run_command_adds_market_guard_in_live_mode(self) -> None:
        cmd = build_run_command(
            query="q",
            web_topic="finance",
            web_time_range="day",
            web_max_results=8,
            financial_provider="yahoo",
            interval_seconds=300,
            execute_live=True,
        )
        self.assertIn("--execute-orders", cmd)
        self.assertIn("--auto-confirm-orders", cmd)
        self.assertIn("--stop-if-market-closed", cmd)

    def test_build_run_command_omits_live_flags_when_not_live(self) -> None:
        cmd = build_run_command(
            query="q",
            web_topic="finance",
            web_time_range="day",
            web_max_results=8,
            financial_provider="yahoo",
            interval_seconds=300,
            execute_live=False,
        )
        self.assertNotIn("--execute-orders", cmd)
        self.assertNotIn("--stop-if-market-closed", cmd)

    def test_is_market_closed_message(self) -> None:
        self.assertTrue(is_market_closed_message("Le marché est fermé."))
        self.assertTrue(is_market_closed_message("Le marche est ferme."))
        self.assertFalse(is_market_closed_message("All good"))

    def test_evaluate_run_feedback_detects_shell_error(self) -> None:
        level, message = evaluate_run_feedback(
            run_result={"returncode": 1, "stdout": "", "stderr": "boom"},
            latest_artifact=None,
        )
        self.assertEqual(level, "error")
        self.assertIn("erreur shell", message.lower())

    def test_evaluate_run_feedback_detects_market_closed(self) -> None:
        level, _ = evaluate_run_feedback(
            run_result={
                "returncode": 0,
                "stdout": "[V2 Pipeline] Le marché est fermé, il réouvre dans 1h.",
                "stderr": "",
            },
            latest_artifact=None,
        )
        self.assertEqual(level, "warning")

    def test_evaluate_run_feedback_detects_execution_error(self) -> None:
        level, message = evaluate_run_feedback(
            run_result={"returncode": 0, "stdout": "", "stderr": ""},
            latest_artifact={
                "execution_report": {
                    "status": "error",
                    "message": "Echec soumission Alpaca (APIError).",
                }
            },
        )
        self.assertEqual(level, "error")
        self.assertIn("alpaca", message.lower())


if __name__ == "__main__":
    unittest.main()

