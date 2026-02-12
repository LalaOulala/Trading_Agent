from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from trading_pipeline.models import FocusSelection, FreshMarketSnapshot, PreAnalysis


@dataclass
class FocusTraderAgent:
    max_focus_symbols: int = 6

    def run(self, pre_analysis: PreAnalysis, snapshot: FreshMarketSnapshot) -> FocusSelection:
        mention_counts: Counter[str] = Counter()
        rationale: dict[str, str] = {}

        all_signals = [*snapshot.web_signals, *snapshot.social_signals]
        for symbol in pre_analysis.candidate_symbols:
            sym = symbol.upper()
            for signal in all_signals:
                joined = f"{signal.title} {signal.snippet}".upper()
                if sym in joined:
                    mention_counts[sym] += 1
                    rationale[sym] = (
                        f"Symbole fréquemment observé dans les signaux frais ({mention_counts[sym]} mentions)."
                    )

        ranked = [s for s, _ in mention_counts.most_common(self.max_focus_symbols)]
        if not ranked:
            ranked = pre_analysis.candidate_symbols[: self.max_focus_symbols]
            for sym in ranked:
                rationale[sym] = "Sélection de fallback depuis la shortlist préliminaire."

        questions = [
            f"{sym}: momentum court terme confirmé ou simple bruit d'actualité ?"
            for sym in ranked
        ]
        if not questions:
            questions = ["Aucun symbole focus: faut-il rester en attente ?"]

        return FocusSelection(
            symbols=ranked,
            rationale_by_symbol=rationale,
            questions=questions,
        )
