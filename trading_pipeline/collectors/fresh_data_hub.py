from __future__ import annotations

from dataclasses import dataclass

from .base import FreshDataCollector, SocialCollector, WebCollector
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
