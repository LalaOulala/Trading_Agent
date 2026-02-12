from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run import (
    _ensure_non_empty_file,
    _extract_first_object_with_keys,
    _extract_json_objects,
    _latest_research_report,
    _latest_trader_report,
    _resolve_repo_path,
)


class RunHelpersTests(unittest.TestCase):
    def test_extract_json_objects_skips_invalid_blocks(self) -> None:
        text = 'prefix {not json} then {"a": 1} and {"b": 2}'
        parsed = _extract_json_objects(text)
        self.assertEqual(parsed, [{"a": 1}, {"b": 2}])

    def test_extract_first_object_with_keys(self) -> None:
        text = '{"foo": 1}\n{"requested_market_data": [], "questions": []}'
        parsed = _extract_first_object_with_keys(text, {"requested_market_data"})
        self.assertEqual(parsed, {"requested_market_data": [], "questions": []})

    def test_ensure_non_empty_file_errors_for_missing_or_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            missing = base / "missing.txt"
            with self.assertRaisesRegex(FileNotFoundError, "introuvable"):
                _ensure_non_empty_file(missing, "Report")

            empty = base / "empty.txt"
            empty.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "vide"):
                _ensure_non_empty_file(empty, "Report")

    def test_latest_research_report_picks_latest_non_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "2026-01-01_10-00-00").mkdir(parents=True)
            (base / "2026-01-01_10-00-00" / "report.txt").write_text(
                "older",
                encoding="utf-8",
            )
            (base / "2026-01-01_11-00-00").mkdir(parents=True)
            (base / "2026-01-01_11-00-00" / "report.txt").write_text(
                "",
                encoding="utf-8",
            )

            latest = _latest_research_report(base)
            self.assertEqual(latest.name, "report.txt")
            self.assertEqual(latest.parent.name, "2026-01-01_10-00-00")

    def test_latest_trader_report_picks_latest_non_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "2026-01-01_10-00-00.txt").write_text("a", encoding="utf-8")
            (base / "2026-01-01_11-00-00.txt").write_text("", encoding="utf-8")
            (base / "notes.md").write_text("ignored", encoding="utf-8")

            latest = _latest_trader_report(base)
            self.assertEqual(latest.name, "2026-01-01_10-00-00.txt")

    def test_resolve_repo_path(self) -> None:
        repo_root = Path("/tmp/example")
        self.assertEqual(
            _resolve_repo_path(Path("responses"), repo_root=repo_root),
            repo_root / "responses",
        )
        self.assertEqual(
            _resolve_repo_path(Path("/var/data"), repo_root=repo_root),
            Path("/var/data"),
        )


if __name__ == "__main__":
    unittest.main()
