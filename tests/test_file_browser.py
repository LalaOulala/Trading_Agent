from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trading_pipeline.ui.file_browser import (
    format_file_button_label,
    list_log_files,
    parse_json_text,
    read_text_file,
)


class FileBrowserTests(unittest.TestCase):
    def test_list_log_files_sorts_by_eurodated_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pipeline_runs_v2").mkdir(parents=True)
            (root / "responses" / "2026-02-12_13-01-00").mkdir(parents=True)
            (root / "reflex_trader").mkdir(parents=True)

            (root / "pipeline_runs_v2" / "2026-02-12_13-00-00.json").write_text(
                json.dumps({"ok": True}),
                encoding="utf-8",
            )
            (root / "responses" / "2026-02-12_13-01-00" / "report.txt").write_text(
                "report",
                encoding="utf-8",
            )
            (root / "reflex_trader" / "2026-02-12_12-59-00.txt").write_text(
                "trader",
                encoding="utf-8",
            )

            rows = list_log_files(root)

            self.assertEqual(len(rows), 3)
            self.assertTrue(rows[0]["relative_path"].endswith("responses/2026-02-12_13-01-00/report.txt"))
            self.assertTrue(rows[1]["relative_path"].endswith("pipeline_runs_v2/2026-02-12_13-00-00.json"))

    def test_read_text_file_truncates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file.txt"
            path.write_text("abcdef", encoding="utf-8")
            content = read_text_file(path, max_chars=3)
            self.assertIn("[Truncated]", content)

    def test_parse_json_text(self) -> None:
        self.assertEqual(parse_json_text('{"a": 1}'), {"a": 1})
        self.assertIsNone(parse_json_text("not json"))

    def test_format_file_button_label(self) -> None:
        label = format_file_button_label(
            {
                "datetime_eu": "12/02/2026 14:05:10",
                "relative_path": "pipeline_runs_v2/2026-02-12_13-05-10.json",
                "size_bytes": 2048,
            }
        )
        self.assertIn("12/02/2026 14:05:10", label)
        self.assertIn("pipeline_runs_v2/2026-02-12_13-05-10.json", label)
        self.assertIn("2.0 KB", label)


if __name__ == "__main__":
    unittest.main()

