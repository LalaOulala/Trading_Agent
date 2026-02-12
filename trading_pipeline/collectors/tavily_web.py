from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import CollectorResult, WebCollector
from trading_pipeline.models import FreshSignal


@dataclass
class TavilyWebCollector(WebCollector):
    api_key: str
    topic: str = "finance"
    search_depth: str = "basic"
    time_range: str = "day"
    max_results: int = 8
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    include_answer: bool = False
    include_raw_content: str = "none"  # none|text|markdown

    def _make_client(self) -> Any:
        try:
            from tavily import TavilyClient
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Le package `tavily-python` est requis pour TavilyWebCollector."
            ) from exc
        return TavilyClient(api_key=self.api_key)

    def collect(self, query: str) -> CollectorResult:
        if not query.strip():
            raise ValueError("Query vide: impossible d'interroger Tavily.")

        client = self._make_client()
        kwargs: dict[str, Any] = {
            "query": query,
            "topic": self.topic,
            "search_depth": self.search_depth,
            "max_results": self.max_results,
            "include_answer": self.include_answer,
            "include_usage": True,
        }
        if self.time_range and self.time_range != "none":
            kwargs["time_range"] = self.time_range
        if self.include_raw_content and self.include_raw_content != "none":
            kwargs["include_raw_content"] = self.include_raw_content
        if self.include_domains:
            kwargs["include_domains"] = self.include_domains
        if self.exclude_domains:
            kwargs["exclude_domains"] = self.exclude_domains

        try:
            response = client.search(**kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"Echec de récupération Tavily ({type(exc).__name__}: {exc})"
            ) from exc

        if not isinstance(response, dict):
            raise RuntimeError("Réponse Tavily invalide: objet JSON attendu.")

        raw_results = response.get("results")
        if not isinstance(raw_results, list):
            raise RuntimeError("Réponse Tavily invalide: champ `results` manquant ou invalide.")

        signals: list[FreshSignal] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url:
                continue

            snippet = str(item.get("content") or "").strip()
            raw_content = item.get("raw_content")
            if raw_content and isinstance(raw_content, str):
                snippet = snippet or raw_content[:500]

            score = item.get("score")
            score_value = float(score) if isinstance(score, (int, float)) else None
            signals.append(
                FreshSignal(
                    source="tavily_web",
                    title=title,
                    url=url,
                    snippet=snippet,
                    score=score_value,
                    metadata={"favicon": item.get("favicon")},
                )
            )

        notes: list[str] = []
        usage = response.get("usage")
        if isinstance(usage, dict) and usage.get("credits") is not None:
            notes.append(f"Tavily credits used: {usage.get('credits')}")
        if response.get("response_time") is not None:
            notes.append(f"Tavily response_time: {response.get('response_time')}s")
        answer = response.get("answer")
        if isinstance(answer, str) and answer.strip():
            notes.append(f"Tavily answer: {answer.strip()[:300]}")

        return CollectorResult(signals=signals, notes=notes)
