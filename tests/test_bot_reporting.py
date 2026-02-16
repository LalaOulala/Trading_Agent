from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.reporting import (
    estimate_api_costs,
    split_discord_message,
    summarize_trade_events,
)


class BotReportingTests(unittest.TestCase):
    def test_summarize_trade_events(self) -> None:
        events = [
            {
                "final_decision": {"action": "LONG", "symbols": ["SPY"]},
                "execution_report": {
                    "status": "submitted",
                    "details": [{"symbol": "SPY"}, {"symbol": "QQQ"}],
                    "message": "ok",
                },
            },
            {
                "final_decision": {"action": "SHORT", "symbols": ["AAPL"]},
                "execution_report": {
                    "status": "error",
                    "details": [],
                    "message": "insufficient buying power",
                },
            },
        ]

        summary = summarize_trade_events(events)

        self.assertEqual(summary.trade_event_count, 2)
        self.assertEqual(summary.execution_status_counts["submitted"], 1)
        self.assertEqual(summary.execution_status_counts["error"], 1)
        self.assertEqual(summary.action_counts["LONG"], 1)
        self.assertEqual(summary.action_counts["SHORT"], 1)
        self.assertEqual(summary.total_orders, 2)
        self.assertEqual(summary.last_error_message, "insufficient buying power")
        self.assertTrue(summary.top_symbols)

    def test_estimate_api_costs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            artifacts_dir = base / "pipeline_runs_v2"
            responses_dir = base / "responses"
            artifacts_dir.mkdir(parents=True)
            (responses_dir / "2026-02-16_16-14-37").mkdir(parents=True)

            now = datetime.now(timezone.utc)
            artifact = {
                "generated_at": now.isoformat(),
                "fresh_snapshot": {"notes": ["Tavily total credits used: 4"]},
            }
            (artifacts_dir / "a.json").write_text(
                json.dumps(artifact),
                encoding="utf-8",
            )
            (responses_dir / "2026-02-16_16-14-37" / "debug.txt").write_text(
                "\n".join(
                    [
                        "total_tokens: 21800",
                        "Tools used (billed): {'SERVER_SIDE_TOOL_X_SEARCH': 2}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            summary = estimate_api_costs(
                artifacts_dir=artifacts_dir,
                responses_dir=responses_dir,
                since_utc=now - timedelta(hours=1),
            )

            self.assertEqual(summary.artifacts_considered, 1)
            self.assertEqual(summary.tavily_credits, 4.0)
            self.assertEqual(summary.response_debug_files_considered, 1)
            self.assertEqual(summary.xai_total_tokens, 21800)
            self.assertEqual(summary.x_search_calls, 2)

    def test_split_discord_message(self) -> None:
        text = "\n".join([f"line-{i}" for i in range(200)])
        chunks = split_discord_message(text, max_len=120)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 120)


if __name__ == "__main__":
    unittest.main()
