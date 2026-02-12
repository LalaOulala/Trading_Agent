from __future__ import annotations

import py_compile
import unittest
from pathlib import Path


class CompilationTests(unittest.TestCase):
    def test_project_python_files_compile(self) -> None:
        root = Path(__file__).resolve().parents[1]
        files = sorted(root.rglob("*.py"))
        for path in files:
            if any(
                part in {".venv", ".git", "__pycache__", ".cache"}
                for part in path.parts
            ):
                continue
            with self.subTest(path=path.name):
                py_compile.compile(str(path), doraise=True)


if __name__ == "__main__":
    unittest.main()
