from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trading_pipeline.context.trade_history import append_trade_event, load_recent_trade_events


class TradeHistoryTests(unittest.TestCase):
    def test_append_and_load_recent_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "runtime_history" / "run_v2_trade_events.jsonl"
            append_trade_event(
                history_file,
                query="q1",
                cycle=1,
                final_decision={"action": "LONG"},
                execution_report={"status": "submitted", "message": "ok"},
                artifact_path="pipeline_runs_v2/a.json",
            )
            append_trade_event(
                history_file,
                query="q2",
                cycle=2,
                final_decision={"action": "SHORT"},
                execution_report={"status": "error", "message": "insufficient buying power"},
                artifact_path="pipeline_runs_v2/b.json",
            )

            events = load_recent_trade_events(history_file, limit=15)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["query"], "q1")
            self.assertEqual(events[1]["execution_report"]["status"], "error")

    def test_load_respects_limit_and_ignores_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "events.jsonl"
            history_file.write_text(
                "\n".join(
                    [
                        '{"query":"q1","execution_report":{"status":"submitted"}}',
                        "not-json",
                        '{"query":"q2","execution_report":{"status":"error"}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            events = load_recent_trade_events(history_file, limit=1)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["query"], "q2")

    def test_load_handles_missing_file_or_zero_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "missing.jsonl"
            self.assertEqual(load_recent_trade_events(history_file, limit=15), [])
            self.assertEqual(load_recent_trade_events(history_file, limit=0), [])


if __name__ == "__main__":
    unittest.main()
