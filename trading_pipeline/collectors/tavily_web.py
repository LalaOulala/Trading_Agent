from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .base import CollectorResult, WebCollector
from trading_pipeline.models import FreshSignal

_DOLLAR_TICKER_RE = re.compile(r"\$([A-Z][A-Z0-9]{0,4}(?:\.[A-Z])?)\b")
_UPPER_TOKEN_RE = re.compile(r"\b([A-Z]{2,5}(?:\.[A-Z])?)\b")

_SYMBOL_STOPWORDS = {
    "A",
    "AN",
    "AND",
    "AS",
    "AT",
    "BY",
    "FOR",
    "FROM",
    "IN",
    "IS",
    "IT",
    "OF",
    "ON",
    "OR",
    "THE",
    "TO",
    "US",
    "USA",
    "UTC",
    "AI",
    "GDP",
    "CPI",
    "PPI",
    "PMI",
    "ETF",
    "SEC",
}

_COMMON_MARKET_SYMBOLS = {
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "TLT",
    "GLD",
    "USO",
    "VIXY",
    "XLF",
    "XLK",
    "XLE",
    "XLI",
    "XLB",
    "XLV",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "TSLA",
    "GOOGL",
    "GOOG",
    "AMD",
    "INTC",
    "NFLX",
    "CRM",
    "CSCO",
    "JPM",
    "BAC",
    "GS",
    "WMT",
    "COST",
    "KO",
    "PEP",
    "XOM",
    "CVX",
}

_THEMES: list[tuple[str, tuple[str, ...]]] = [
    (
        "federal reserve policy",
        ("fed", "federal reserve", "interest rate", "rate cut", "rate hike"),
    ),
    ("treasury yields", ("treasury", "bond yield", "yields", "10-year", "2-year")),
    ("inflation data", ("inflation", "cpi", "ppi", "core inflation")),
    ("labor market", ("jobs report", "payrolls", "unemployment", "labor market")),
    ("earnings guidance", ("earnings", "guidance", "results", "forecast")),
    ("oil prices", ("oil", "crude", "wti", "brent")),
    ("geopolitical risk", ("geopolitical", "tariff", "sanction", "war")),
]


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
    max_follow_up_queries: int = 3
    follow_up_max_results: int = 5

    def _make_client(self) -> Any:
        try:
            from tavily import TavilyClient
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Le package `tavily-python` est requis pour TavilyWebCollector."
            ) from exc
        return TavilyClient(api_key=self.api_key)

    @staticmethod
    def _validate_max_results(value: int, *, field: str) -> int:
        if value < 1 or value > 20:
            raise ValueError(f"{field} doit être entre 1 et 20.")
        return value

    @staticmethod
    def _short(text: str, *, max_len: int = 80) -> str:
        normalized = text.strip()
        if len(normalized) <= max_len:
            return normalized
        return normalized[: max_len - 1].rstrip() + "…"

    def _build_search_kwargs(self, *, query: str, max_results: int) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "query": query,
            "topic": self.topic,
            "search_depth": self.search_depth,
            "max_results": max_results,
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
        return kwargs

    def _search(self, client: Any, *, query: str, max_results: int) -> dict[str, Any]:
        kwargs = self._build_search_kwargs(query=query, max_results=max_results)
        return client.search(**kwargs)

    @staticmethod
    def _extract_symbol_candidates(text: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        upper_text = text.upper()

        for match in _DOLLAR_TICKER_RE.finditer(upper_text):
            symbol = match.group(1).strip()
            if symbol in _SYMBOL_STOPWORDS:
                continue
            if symbol not in seen:
                seen.add(symbol)
                out.append(symbol)

        for match in _UPPER_TOKEN_RE.finditer(upper_text):
            symbol = match.group(1).strip()
            if symbol in _SYMBOL_STOPWORDS:
                continue
            if symbol not in _COMMON_MARKET_SYMBOLS:
                continue
            if symbol not in seen:
                seen.add(symbol)
                out.append(symbol)

        return out

    @staticmethod
    def _extract_theme_candidates(text: str) -> list[str]:
        lowered = text.lower()
        found: list[str] = []
        for theme, keywords in _THEMES:
            if any(keyword in lowered for keyword in keywords):
                found.append(theme)
        return found

    def _build_follow_up_queries(self, *, base_query: str, seed_signals: list[FreshSignal]) -> list[str]:
        if self.max_follow_up_queries <= 0:
            return []

        merged_text = " ".join(
            f"{signal.title}. {signal.snippet}".strip()
            for signal in seed_signals
            if signal.title or signal.snippet
        )
        analysis_text = f"{base_query} {merged_text}".strip()
        symbols = self._extract_symbol_candidates(analysis_text)
        themes = self._extract_theme_candidates(analysis_text)

        raw_candidates: list[str] = [f"{base_query} catalysts and market impact today"]
        raw_candidates.extend(
            f"{symbol} latest market-moving news and catalysts today"
            for symbol in symbols
        )
        raw_candidates.extend(
            f"US equities {theme} latest developments today"
            for theme in themes
        )

        unique: list[str] = []
        seen: set[str] = set()
        normalized_base = base_query.strip().lower()
        for candidate in raw_candidates:
            trimmed = candidate.strip()
            if not trimmed:
                continue
            lowered = trimmed.lower()
            if lowered == normalized_base:
                continue
            if lowered in seen:
                continue
            seen.add(lowered)
            unique.append(trimmed)
            if len(unique) >= self.max_follow_up_queries:
                break
        return unique

    def _parse_response(
        self,
        response: dict[str, Any],
        *,
        source_query: str,
    ) -> tuple[list[FreshSignal], list[str], float | None]:
        if not isinstance(response, dict):
            raise RuntimeError("Réponse Tavily invalide: objet JSON attendu.")

        raw_results = response.get("results")
        if not isinstance(raw_results, list):
            raise RuntimeError("Réponse Tavily invalide: champ `results` manquant ou invalide.")

        query_short = self._short(source_query)
        notes: list[str] = [f"Tavily[{query_short}] raw results: {len(raw_results)}"]
        credits: float | None = None

        usage = response.get("usage")
        if isinstance(usage, dict):
            usage_credits = usage.get("credits")
            if isinstance(usage_credits, (int, float)):
                credits = float(usage_credits)
                notes.append(f"Tavily[{query_short}] credits used: {usage_credits}")
        if response.get("response_time") is not None:
            notes.append(f"Tavily[{query_short}] response_time: {response.get('response_time')}s")
        answer = response.get("answer")
        if isinstance(answer, str) and answer.strip():
            notes.append(f"Tavily[{query_short}] answer: {answer.strip()[:300]}")

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
                    metadata={
                        "favicon": item.get("favicon"),
                        "query": source_query,
                    },
                )
            )

        return signals, notes, credits

    @staticmethod
    def _signal_dedup_key(signal: FreshSignal) -> str:
        url = signal.url.strip().rstrip("/").lower()
        if url:
            return url
        return f"{signal.title.strip().lower()}::{signal.snippet.strip().lower()}"

    def collect(self, query: str) -> CollectorResult:
        base_query = query.strip()
        if not base_query:
            raise ValueError("Query vide: impossible d'interroger Tavily.")

        if self.max_follow_up_queries < 0:
            raise ValueError("max_follow_up_queries doit être >= 0.")
        base_max_results = self._validate_max_results(self.max_results, field="max_results")
        follow_up_max_results = self._validate_max_results(
            self.follow_up_max_results,
            field="follow_up_max_results",
        )

        client = self._make_client()
        executed_queries: list[str] = []
        all_signals: list[FreshSignal] = []
        notes: list[str] = []
        seen_keys: set[str] = set()
        total_credits = 0.0
        credits_found = False

        def _merge_signals(signals: list[FreshSignal]) -> None:
            for signal in signals:
                key = self._signal_dedup_key(signal)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                all_signals.append(signal)

        try:
            response = self._search(client, query=base_query, max_results=base_max_results)
        except Exception as exc:
            raise RuntimeError(
                f"Echec de récupération Tavily ({type(exc).__name__}: {exc})"
            ) from exc

        base_signals, response_notes, credits = self._parse_response(
            response,
            source_query=base_query,
        )
        executed_queries.append(base_query)
        _merge_signals(base_signals)
        notes.extend(response_notes)
        if credits is not None:
            credits_found = True
            total_credits += credits

        follow_up_queries = self._build_follow_up_queries(
            base_query=base_query,
            seed_signals=base_signals,
        )
        for follow_up_query in follow_up_queries:
            try:
                response = self._search(
                    client,
                    query=follow_up_query,
                    max_results=follow_up_max_results,
                )
            except Exception as exc:
                notes.append(
                    "Tavily follow-up failed "
                    f"[{self._short(follow_up_query)}]: {type(exc).__name__}: {exc}"
                )
                continue

            signals, response_notes, credits = self._parse_response(
                response,
                source_query=follow_up_query,
            )
            executed_queries.append(follow_up_query)
            _merge_signals(signals)
            notes.extend(response_notes)
            if credits is not None:
                credits_found = True
                total_credits += credits

        executed = " | ".join(self._short(q) for q in executed_queries)
        notes.insert(0, f"Tavily queries executed ({len(executed_queries)}): {executed}")
        notes.append(f"Tavily unique web signals: {len(all_signals)}")
        if credits_found:
            notes.append(f"Tavily total credits used: {total_credits:g}")

        return CollectorResult(signals=all_signals, notes=notes)
