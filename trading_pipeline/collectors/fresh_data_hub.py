from __future__ import annotations

from dataclasses import dataclass

from .base import CollectorResult, FreshDataCollector, SocialCollector, WebCollector
from trading_pipeline.models import FreshMarketSnapshot, utc_now_iso


@dataclass
class FreshDataHub(FreshDataCollector):
    web_collector: WebCollector
    social_collector: SocialCollector

    def collect(self, query: str) -> FreshMarketSnapshot:
        web = self.web_collector.collect(query)
        social = self.social_collector.collect(query)

        notes = [
            f"Web signals: {len(web.signals)}",
            f"Social signals: {len(social.signals)}",
            *web.notes,
            *social.notes,
        ]
        return FreshMarketSnapshot(
            generated_at=utc_now_iso(),
            web_signals=web.signals,
            social_signals=social.signals,
            notes=notes,
        )

    def collect_additional_web(self, queries: list[str]) -> CollectorResult:
        """
        Exécute une liste de requêtes web additionnelles et fusionne les signaux.

        Utilisé quand un agent reasoning propose des follow-ups Tavily.
        """
        if not queries:
            return CollectorResult(signals=[], notes=["Aucune requête web additionnelle demandée."])

        merged = []
        notes: list[str] = []
        seen_urls: set[str] = set()
        executed = 0
        for query in queries:
            q = query.strip()
            if not q:
                continue
            result = self.web_collector.collect(q)
            executed += 1
            notes.extend(result.notes)
            for signal in result.signals:
                url_key = signal.url.strip().rstrip("/").lower()
                if url_key and url_key in seen_urls:
                    continue
                if url_key:
                    seen_urls.add(url_key)
                merged.append(signal)

        notes.insert(0, f"Requêtes web additionnelles exécutées: {executed}")
        notes.append(f"Signaux web additionnels uniques: {len(merged)}")
        return CollectorResult(signals=merged, notes=notes)
