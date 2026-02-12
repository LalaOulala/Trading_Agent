from __future__ import annotations

import py_compile
import unittest
from pathlib import Path


class CompilationTests(unittest.TestCase):
    def test_project_python_files_compile(self) -> None:
        root = Path(__file__).resolve().parents[1]
        files = [
            root / "run.py",
            root / "grok_tools_test.py",
            root / "reflex_trader_agent.py",
            root / "grok_api_test.py",
            root / "alpaca_api_test.py",
        ]
        for path in files:
            with self.subTest(path=path.name):
                py_compile.compile(str(path), doraise=True)


if __name__ == "__main__":
    unittest.main()
