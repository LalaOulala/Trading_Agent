from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any

from trading_pipeline.models import (
    FinalDecision,
    FinancialSnapshot,
    FocusSelection,
    FreshMarketSnapshot,
    PreAnalysis,
)


def _extract_change_1d(symbol_data: dict[str, Any]) -> float | None:
    raw = symbol_data.get("change_1d_pct")
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


@dataclass
class FinalTraderAgent:
    order_qty: float = 1.0

    def run(
        self,
        pre_analysis: PreAnalysis,
        focus: FocusSelection,
        financial: FinancialSnapshot,
        fresh: FreshMarketSnapshot,
    ) -> FinalDecision:
        if not focus.symbols:
            return FinalDecision(
                action="HOLD",
                symbols=[],
                thesis="Aucun symbole focus retenu: attente recommandée.",
                risk_controls=["Pas d'exécution tant que la shortlist est vide."],
                confidence="low",
                should_execute=False,
                orders=[],
            )

        changes: list[float] = []
        missing: list[str] = []
        for sym in focus.symbols:
            data = financial.symbols_data.get(sym, {})
            value = _extract_change_1d(data)
            if value is None:
                missing.append(sym)
                continue
            changes.append(value)

        if not changes:
            thesis = (
                "Données financières insuffisantes pour trancher. "
                "Le pipeline reste en attente (HOLD)."
            )
            return FinalDecision(
                action="HOLD",
                symbols=focus.symbols,
                thesis=thesis,
                risk_controls=["Pas d'ordre sans métriques prix/variation fiables."],
                confidence="low",
                should_execute=False,
                orders=[],
            )

        avg_change = mean(changes)
        if avg_change >= 1.0:
            action = "LONG"
            side = "buy"
            confidence = "medium"
        elif avg_change <= -1.0:
            action = "SHORT"
            side = "sell"
            confidence = "medium"
        else:
            action = "HOLD"
            side = "none"
            confidence = "low"

        orders: list[dict[str, Any]] = []
        if action != "HOLD":
            for sym in focus.symbols:
                if sym in missing:
                    continue
                orders.append(
                    {
                        "symbol": sym,
                        "side": side,
                        "qty": self.order_qty,
                        "type": "market",
                        "time_in_force": "day",
                    }
                )

        should_execute = bool(orders)
        thesis = (
            f"Pré-analyse: {pre_analysis.summary} "
            f"Variation moyenne 1D sur la shortlist: {avg_change:.2f}% -> action {action}."
        )
        if missing:
            thesis += f" Symboles sans data exploitable: {', '.join(missing)}."

        risk_controls = [
            "Taille unitaire faible pour chaque ordre.",
            "Ne rien exécuter si données financières partielles/incohérentes.",
            "Réévaluer après la prochaine vague de news fraîches.",
        ]

        return FinalDecision(
            action=action,
            symbols=focus.symbols,
            thesis=thesis,
            risk_controls=risk_controls,
            confidence=confidence,
            should_execute=should_execute,
            orders=orders,
        )
