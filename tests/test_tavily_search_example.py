from __future__ import annotations

import argparse
import unittest

from scripts.data.tavily_search_example import (
    _build_search_kwargs,
    _domain,
    _split_csv,
    _trusted_hits,
)


class TavilySearchExampleTests(unittest.TestCase):
    def test_split_csv(self) -> None:
        self.assertIsNone(_split_csv(None))
        self.assertIsNone(_split_csv(" , , "))
        self.assertEqual(_split_csv("a.com, b.com"), ["a.com", "b.com"])

    def test_domain(self) -> None:
        self.assertEqual(_domain("https://www.reuters.com/world"), "www.reuters.com")
        self.assertEqual(_domain("not a url"), "")

    def test_trusted_hits(self) -> None:
        results = [
            {"url": "https://www.reuters.com/a"},
            {"url": "https://example.com/b"},
            {"url": "https://www.bloomberg.com/c"},
        ]
        hits, total = _trusted_hits(results, ["reuters.com", "bloomberg.com"])
        self.assertEqual(hits, 2)
        self.assertEqual(total, 3)

    def test_build_search_kwargs(self) -> None:
        args = argparse.Namespace(
            query="test",
            topic="finance",
            search_depth="basic",
            max_results=5,
            include_answer=True,
            time_range="day",
            include_raw_content="markdown",
            include_domains="reuters.com,bloomberg.com",
            exclude_domains="x.com",
        )
        kwargs = _build_search_kwargs(args)
        self.assertEqual(kwargs["query"], "test")
        self.assertEqual(kwargs["topic"], "finance")
        self.assertEqual(kwargs["include_domains"], ["reuters.com", "bloomberg.com"])
        self.assertEqual(kwargs["exclude_domains"], ["x.com"])
        self.assertEqual(kwargs["include_raw_content"], "markdown")
        self.assertTrue(kwargs["include_usage"])

    def test_build_search_kwargs_omits_optional_fields(self) -> None:
        args = argparse.Namespace(
            query="test",
            topic="general",
            search_depth="fast",
            max_results=3,
            include_answer=False,
            time_range="none",
            include_raw_content="none",
            include_domains=None,
            exclude_domains=None,
        )
        kwargs = _build_search_kwargs(args)
        self.assertNotIn("time_range", kwargs)
        self.assertNotIn("include_raw_content", kwargs)
        self.assertNotIn("include_domains", kwargs)
        self.assertNotIn("exclude_domains", kwargs)


if __name__ == "__main__":
    unittest.main()
