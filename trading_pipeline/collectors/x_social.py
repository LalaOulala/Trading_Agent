from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .base import CollectorResult, SocialCollector
from trading_pipeline.models import FreshSignal


@dataclass
class XPlaceholderCollector(SocialCollector):
    """
    Collecteur social X placeholder.

    - Si `cache_file` est fourni, lit les signaux depuis un JSON local.
    - Sinon, retourne une liste vide avec une note explicite.
    """

    cache_file: Path | None = None

    def collect(self, query: str) -> CollectorResult:
        if self.cache_file is None:
            return CollectorResult(
                signals=[],
                notes=[
                    "Collecteur X non branché en direct pour l'instant (placeholder actif)."
                ],
            )

        path = self.cache_file
        if not path.exists():
            raise FileNotFoundError(f"X cache file introuvable: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("X cache invalide: liste JSON attendue.")

        signals: list[FreshSignal] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url:
                continue
            signals.append(
                FreshSignal(
                    source="x_cache",
                    title=title,
                    url=url,
                    snippet=str(item.get("snippet") or "").strip(),
                    published_at=str(item.get("published_at")) if item.get("published_at") else None,
                    score=float(item["score"]) if isinstance(item.get("score"), (int, float)) else None,
                    metadata={"query": query},
                )
            )

        return CollectorResult(
            signals=signals,
            notes=[f"X cache loaded: {len(signals)} signals depuis {path}"],
        )
