from __future__ import annotations

import unittest
from typing import Any

from trading_pipeline.collectors.tavily_web import TavilyWebCollector
from trading_pipeline.models import FreshSignal


def _response(
    *,
    results: list[dict[str, Any]],
    credits: int | float | None = None,
    response_time: float | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"results": results}
    if credits is not None:
        payload["usage"] = {"credits": credits}
    if response_time is not None:
        payload["response_time"] = response_time
    return payload


class _StubTavilyCollector(TavilyWebCollector):
    def __init__(
        self,
        *,
        responses_by_query: dict[str, dict[str, Any]],
        forced_follow_ups: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key="stub-key", **kwargs)
        self.responses_by_query = responses_by_query
        self.forced_follow_ups = forced_follow_ups
        self.calls: list[tuple[str, int]] = []

    def _make_client(self) -> Any:
        return object()

    def _search(self, client: Any, *, query: str, max_results: int) -> dict[str, Any]:
        del client
        self.calls.append((query, max_results))
        payload = self.responses_by_query.get(query)
        if payload is None:
            raise RuntimeError(f"unexpected query: {query}")
        return payload

    def _build_follow_up_queries(
        self,
        *,
        base_query: str,
        seed_signals: list[FreshSignal],
    ) -> list[str]:
        if self.forced_follow_ups is not None:
            return self.forced_follow_ups
        return super()._build_follow_up_queries(base_query=base_query, seed_signals=seed_signals)


class TavilyWebCollectorTests(unittest.TestCase):
    def test_collect_executes_follow_up_queries_and_deduplicates_urls(self) -> None:
        base_query = "S&P 500 market drivers today"
        follow_up_1 = "SPY latest market-moving news and catalysts today"
        follow_up_2 = "US equities treasury yields latest developments today"

        collector = _StubTavilyCollector(
            responses_by_query={
                base_query: _response(
                    results=[
                        {"title": "SPY opens higher", "url": "https://example.com/a"},
                        {"title": "QQQ in focus", "url": "https://example.com/b"},
                    ],
                    credits=1,
                ),
                follow_up_1: _response(
                    results=[
                        {"title": "SPY opens higher", "url": "https://example.com/a"},
                        {"title": "SPY intraday update", "url": "https://example.com/c"},
                    ],
                    credits=2,
                ),
                follow_up_2: _response(
                    results=[
                        {"title": "Treasury yields pull back", "url": "https://example.com/d"},
                    ],
                    credits=3,
                ),
            },
            forced_follow_ups=[follow_up_1, follow_up_2],
            max_results=8,
            follow_up_max_results=2,
            max_follow_up_queries=2,
        )

        result = collector.collect(base_query)

        self.assertEqual(
            collector.calls,
            [
                (base_query, 8),
                (follow_up_1, 2),
                (follow_up_2, 2),
            ],
        )
        self.assertEqual(len(result.signals), 4)  # URL dupliquée supprimée
        self.assertEqual(result.signals[0].metadata.get("query"), base_query)
        self.assertIn(
            follow_up_1,
            {signal.metadata.get("query") for signal in result.signals},
        )
        self.assertTrue(any(note.startswith("Tavily queries executed (3):") for note in result.notes))
        self.assertIn("Tavily total credits used: 6", result.notes)

    def test_build_follow_up_queries_detects_symbols_and_themes(self) -> None:
        collector = TavilyWebCollector(
            api_key="stub-key",
            max_follow_up_queries=4,
        )
        seed = [
            FreshSignal(
                source="tavily_web",
                title="SPY jumps as Treasury yields ease",
                url="https://example.com/a",
                snippet="Fed rate cut expectations are repriced.",
            )
        ]

        queries = collector._build_follow_up_queries(
            base_query="S&P 500 market drivers today",
            seed_signals=seed,
        )

        self.assertTrue(queries)
        self.assertLessEqual(len(queries), 4)
        self.assertTrue(any("SPY" in query for query in queries))
        self.assertTrue(any("treasury yields" in query.lower() for query in queries))

    def test_collect_rejects_invalid_max_results(self) -> None:
        collector = _StubTavilyCollector(
            responses_by_query={},
            forced_follow_ups=[],
            max_results=0,
        )

        with self.assertRaisesRegex(ValueError, "max_results"):
            collector.collect("SPY query")

        self.assertEqual(collector.calls, [])

    def test_collect_continues_when_follow_up_fails(self) -> None:
        base_query = "S&P 500 market drivers today"
        collector = _StubTavilyCollector(
            responses_by_query={
                base_query: _response(
                    results=[
                        {"title": "SPY update", "url": "https://example.com/a"},
                    ],
                    credits=1,
                )
            },
            forced_follow_ups=["missing follow up query"],
            max_follow_up_queries=1,
        )

        result = collector.collect(base_query)

        self.assertEqual(len(result.signals), 1)
        self.assertTrue(any("follow-up failed" in note for note in result.notes))


if __name__ == "__main__":
    unittest.main()
