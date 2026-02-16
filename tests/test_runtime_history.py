from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trading_pipeline.context.runtime_history import (
    append_runtime_event,
    load_recent_runtime_events,
)


class RuntimeHistoryTests(unittest.TestCase):
    def test_append_and_load_recent_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "runtime_history" / "run_v2_terminal_events.jsonl"

            append_runtime_event(
                history_file,
                event_type="cycle_summary",
                message="cycle #1",
                cycle=1,
                payload={"status": "submitted"},
            )
            append_runtime_event(
                history_file,
                event_type="cycle_summary",
                message="cycle #2",
                cycle=2,
                payload={"status": "error"},
            )

            events = load_recent_runtime_events(history_file, limit=15)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["message"], "cycle #1")
            self.assertEqual(events[1]["payload"]["status"], "error")

    def test_load_recent_respects_limit_and_skips_invalid_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "events.jsonl"
            history_file.parent.mkdir(parents=True, exist_ok=True)
            history_file.write_text(
                "\n".join(
                    [
                        '{"event_type":"ok","message":"m1"}',
                        "not json",
                        '{"event_type":"ok","message":"m2"}',
                        '{"event_type":"ok","message":"m3"}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            events = load_recent_runtime_events(history_file, limit=2)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["message"], "m2")
            self.assertEqual(events[1]["message"], "m3")

    def test_load_recent_handles_missing_file_or_zero_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "missing.jsonl"
            self.assertEqual(load_recent_runtime_events(history_file, limit=15), [])
            self.assertEqual(load_recent_runtime_events(history_file, limit=0), [])


if __name__ == "__main__":
    unittest.main()
