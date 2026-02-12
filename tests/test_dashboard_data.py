from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from trading_pipeline.ui.dashboard_data import (
    AGENT_ORDER,
    build_agent_histories,
    build_orders_history,
    extract_timing_metrics,
    load_artifact_records,
)


def _artifact(
    *,
    generated_at: str,
    fresh_generated_at: str,
    status: str = "dry_run",
    details: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "generated_at": generated_at,
        "query": "S&P 500 market drivers today",
        "fresh_snapshot": {
            "generated_at": fresh_generated_at,
            "web_signals": [{"title": "Signal 1"}],
            "social_signals": [],
            "notes": ["web=1 social=0"],
        },
        "pre_analysis": {
            "summary": "Summary",
            "key_drivers": ["Driver 1"],
            "candidate_symbols": ["SPY", "QQQ"],
            "risks": ["Risk 1"],
            "confidence": "medium",
        },
        "focus_selection": {
            "symbols": ["SPY", "QQQ"],
            "rationale_by_symbol": {"SPY": "Because"},
            "questions": ["Question 1"],
        },
        "financial_snapshot": {
            "source": "yahoo_finance_pool",
            "asof": generated_at,
            "symbols_data": {"SPY": {"last_price": 690.0}},
            "missing_symbols": [],
            "notes": [],
        },
        "final_decision": {
            "action": "LONG",
            "symbols": ["SPY", "QQQ"],
            "thesis": "Thesis",
            "risk_controls": ["Small size"],
            "confidence": "medium",
            "should_execute": True,
            "orders": details or [],
        },
        "execution_report": {
            "status": status,
            "broker": "alpaca",
            "details": details or [],
            "message": "ok",
        },
    }


class DashboardDataTests(unittest.TestCase):
    def test_load_artifact_records_sorted_desc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            older = _artifact(
                generated_at="2026-02-12T12:00:10+00:00",
                fresh_generated_at="2026-02-12T12:00:00+00:00",
            )
            newer = _artifact(
                generated_at="2026-02-12T12:05:10+00:00",
                fresh_generated_at="2026-02-12T12:05:00+00:00",
            )
            (base / "2026-02-12_12-00-10.json").write_text(
                json.dumps(older),
                encoding="utf-8",
            )
            (base / "2026-02-12_12-05-10.json").write_text(
                json.dumps(newer),
                encoding="utf-8",
            )

            records = load_artifact_records(base)

            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["path"].name, "2026-02-12_12-05-10.json")
            self.assertEqual(records[1]["path"].name, "2026-02-12_12-00-10.json")

    def test_extract_timing_metrics(self) -> None:
        record = {
            "artifact": _artifact(
                generated_at="2026-02-12T12:05:10+00:00",
                fresh_generated_at="2026-02-12T12:05:00+00:00",
            ),
            "generated_at": datetime(2026, 2, 12, 12, 5, 10, tzinfo=timezone.utc),
        }
        now = datetime(2026, 2, 12, 12, 6, 10, tzinfo=timezone.utc)
        metrics = extract_timing_metrics(record, interval_seconds=300, now_utc=now)

        self.assertEqual(metrics["request_to_reflection_seconds"], 10.0)
        self.assertEqual(metrics["next_iteration_in_seconds"], 240)

    def test_build_agent_histories_creates_rows_for_each_agent(self) -> None:
        records = [
            {
                "path": Path("2026-02-12_12-05-10.json"),
                "artifact": _artifact(
                    generated_at="2026-02-12T12:05:10+00:00",
                    fresh_generated_at="2026-02-12T12:05:00+00:00",
                ),
                "generated_at_eu": "12/02/2026 13:05:10",
            }
        ]
        histories = build_agent_histories(records)

        for agent in AGENT_ORDER:
            self.assertIn(agent, histories)
            self.assertEqual(len(histories[agent]), 1)
            self.assertEqual(histories[agent][0]["run_file"], "2026-02-12_12-05-10.json")

    def test_build_orders_history_extracts_detail_rows(self) -> None:
        details = [
            {"symbol": "SPY", "side": "buy", "qty": 1.0},
            {"symbol": "QQQ", "side": "sell", "qty": 2.0},
        ]
        records = [
            {
                "path": Path("2026-02-12_12-05-10.json"),
                "artifact": _artifact(
                    generated_at="2026-02-12T12:05:10+00:00",
                    fresh_generated_at="2026-02-12T12:05:00+00:00",
                    status="dry_run",
                    details=details,
                ),
                "generated_at_eu": "12/02/2026 13:05:10",
            }
        ]
        rows = build_orders_history(records)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["symbol"], "SPY")
        self.assertEqual(rows[1]["side"], "sell")


if __name__ == "__main__":
    unittest.main()

