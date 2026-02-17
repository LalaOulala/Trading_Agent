from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from trading_pipeline.context import load_recent_runtime_events, load_recent_trade_events
from trading_pipeline.models import (
    FinalDecision,
    FinancialSnapshot,
    FocusSelection,
    FreshMarketSnapshot,
    PreAnalysis,
)
from trading_pipeline.xai_compat import create_chat_with_reasoning_fallback


Confidence = Literal["low", "medium", "high"]


def _extract_json_object(text: str) -> dict[str, Any]:
    if not (text or "").strip():
        raise ValueError("Réponse vide: aucun JSON à parser.")

    decoder = json.JSONDecoder()
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        try:
            parsed, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            i = start + 1
            continue
        if isinstance(parsed, dict):
            return parsed
        i = start + end

    raise ValueError("Aucun objet JSON valide détecté dans la réponse du modèle.")


def _normalize_confidence(raw: Any, *, default: Confidence = "low") -> Confidence:
    value = str(raw or "").strip().lower()
    if value in {"low", "medium", "high"}:
        return value  # type: ignore[return-value]
    return default


def _normalize_reasoning_effort(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value not in {"low", "high"}:
        return "high"
    return value


def _normalize_ticker(raw: Any) -> str | None:
    symbol = str(raw or "").strip().upper()
    if not symbol:
        return None
    if not symbol.replace(".", "").isalnum():
        return None
    if len(symbol) > 10:
        return None
    return symbol


def _latest_api_error_message(trade_events: list[dict[str, Any]]) -> str | None:
    for item in reversed(trade_events):
        execution = item.get("execution_report")
        if not isinstance(execution, dict):
            continue
        if str(execution.get("status", "")).lower() != "error":
            continue
        message = str(execution.get("message") or "").strip()
        if message:
            return message
    return None


def _limit_lines(text: str, *, max_chars: int = 16000) -> str:
    raw = text or ""
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 1] + "…"


@dataclass
class _ReasoningAgentBase:
    api_key: str
    model: str
    reasoning_effort: str
    max_tokens: int
    runtime_history_file: Any
    trade_history_file: Any
    history_limit: int

    _last_trace: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def get_last_trace(self) -> dict[str, Any] | None:
        return self._last_trace

    def _chat(self, *, system_prompt: str, user_prompt: str) -> str:
        from xai_sdk import Client
        from xai_sdk.chat import system, user

        client = Client(api_key=self.api_key)
        chat = create_chat_with_reasoning_fallback(
            client=client,
            model=self.model,
            reasoning_effort=_normalize_reasoning_effort(self.reasoning_effort),
            max_tokens=self.max_tokens,
        )
        chat.append(system(system_prompt))
        chat.append(user(user_prompt))
        response = chat.sample()
        return (response.content or "").strip()

    def _load_histories(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
        runtime_events = load_recent_runtime_events(self.runtime_history_file, limit=self.history_limit)
        trade_events = load_recent_trade_events(self.trade_history_file, limit=self.history_limit)
        latest_error = _latest_api_error_message(trade_events)
        return runtime_events, trade_events, latest_error


@dataclass
class ReasoningPreAnalysisAgent(_ReasoningAgentBase):
    fallback_agent: Any
    max_candidate_symbols: int = 12
    max_follow_up_queries: int = 3

    _last_follow_up_queries: list[str] | None = field(default=None, init=False, repr=False)

    def get_follow_up_web_queries(self) -> list[str]:
        return list(self._last_follow_up_queries or [])

    def run(self, snapshot: FreshMarketSnapshot) -> PreAnalysis:
        runtime_events, trade_events, latest_error = self._load_histories()

        system_prompt = """
Tu es un agent de pré-analyse marché. Tu dois répondre en JSON strict.
Règle critique:
- Consulte l'historique des transactions.
- Identifie le dernier message d'erreur API broker (s'il existe).
- Dis explicitement si cet historique pose un risque pour le prochain ordre.
Tu peux proposer des requêtes Tavily de suivi (follow-up) si cela améliore la qualité.
""".strip()

        web_signals = [
            {
                "title": s.title,
                "url": s.url,
                "snippet": s.snippet,
                "source": s.source,
            }
            for s in snapshot.web_signals[:20]
        ]
        social_signals = [
            {
                "title": s.title,
                "url": s.url,
                "snippet": s.snippet,
                "source": s.source,
            }
            for s in snapshot.social_signals[:20]
        ]

        user_prompt = _limit_lines(
            json.dumps(
                {
                    "task": "Pré-analyse de marché",
                    "expected_json_schema": {
                        "summary": "str",
                        "key_drivers": ["str"],
                        "candidate_symbols": ["str"],
                        "risks": ["str"],
                        "confidence": "low|medium|high",
                        "follow_up_tavily_queries": ["str"],
                    },
                    "instruction_obligatoire": (
                        "Vérifie le dernier message d'erreur API dans l'historique transactionnel, "
                        "explique le risque pour le prochain ordre, et adapte la shortlist."
                    ),
                    "latest_api_error_message": latest_error,
                    "runtime_events_recent": runtime_events,
                    "trade_events_recent": trade_events,
                    "fresh_snapshot": {
                        "notes": snapshot.notes,
                        "web_signals": web_signals,
                        "social_signals": social_signals,
                    },
                    "limits": {
                        "max_candidate_symbols": self.max_candidate_symbols,
                        "max_follow_up_queries": self.max_follow_up_queries,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        response_text = ""
        try:
            response_text = self._chat(system_prompt=system_prompt, user_prompt=user_prompt)
            parsed = _extract_json_object(response_text)

            key_drivers = [str(x).strip() for x in parsed.get("key_drivers", []) if str(x).strip()][:6]
            risks = [str(x).strip() for x in parsed.get("risks", []) if str(x).strip()][:8]

            candidate_symbols: list[str] = []
            seen: set[str] = set()
            for raw in parsed.get("candidate_symbols", []):
                sym = _normalize_ticker(raw)
                if not sym or sym in seen:
                    continue
                seen.add(sym)
                candidate_symbols.append(sym)
                if len(candidate_symbols) >= self.max_candidate_symbols:
                    break

            if not candidate_symbols:
                candidate_symbols = ["SPY", "QQQ"]
            if not risks:
                risks = ["Pas de risque explicite fourni par le modèle."]

            follow_ups: list[str] = []
            seen_queries: set[str] = set()
            for raw in parsed.get("follow_up_tavily_queries", []):
                query = str(raw or "").strip()
                if not query:
                    continue
                lowered = query.lower()
                if lowered in seen_queries:
                    continue
                seen_queries.add(lowered)
                follow_ups.append(query)
                if len(follow_ups) >= self.max_follow_up_queries:
                    break
            self._last_follow_up_queries = follow_ups

            result = PreAnalysis(
                summary=str(parsed.get("summary") or "Pré-analyse indisponible."),
                key_drivers=key_drivers,
                candidate_symbols=candidate_symbols,
                risks=risks,
                confidence=_normalize_confidence(parsed.get("confidence"), default="low"),
            )
            self._last_trace = {
                "mode": "reasoning",
                "prompt": user_prompt,
                "response": response_text,
                "error": "",
            }
            return result
        except Exception as exc:
            self._last_follow_up_queries = []
            fallback = self.fallback_agent.run(snapshot)
            self._last_trace = {
                "mode": "fallback",
                "prompt": user_prompt,
                "response": response_text,
                "error": f"{type(exc).__name__}: {exc}",
            }
            return fallback


@dataclass
class ReasoningFocusTraderAgent(_ReasoningAgentBase):
    fallback_agent: Any
    max_focus_symbols: int = 6

    def run(self, pre_analysis: PreAnalysis, snapshot: FreshMarketSnapshot) -> FocusSelection:
        runtime_events, trade_events, latest_error = self._load_histories()

        system_prompt = """
Tu es un agent de sélection focus. Réponse JSON strict.
Tu dois vérifier l'historique de transactions et le dernier message d'erreur API.
Si une contrainte opérationnelle est détectée, limite les symboles exposés au même risque.
""".strip()

        user_prompt = _limit_lines(
            json.dumps(
                {
                    "task": "Focus symbols",
                    "expected_json_schema": {
                        "symbols": ["str"],
                        "rationale_by_symbol": {"SYMBOL": "str"},
                        "questions": ["str"],
                    },
                    "instruction_obligatoire": (
                        "Analyse explicitement le dernier message d'erreur API et dis en quoi il impacte "
                        "la sélection de symboles pour le prochain ordre."
                    ),
                    "latest_api_error_message": latest_error,
                    "runtime_events_recent": runtime_events,
                    "trade_events_recent": trade_events,
                    "pre_analysis": {
                        "summary": pre_analysis.summary,
                        "key_drivers": pre_analysis.key_drivers,
                        "candidate_symbols": pre_analysis.candidate_symbols,
                        "risks": pre_analysis.risks,
                        "confidence": pre_analysis.confidence,
                    },
                    "fresh_notes": snapshot.notes,
                    "limits": {"max_focus_symbols": self.max_focus_symbols},
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        response_text = ""
        try:
            response_text = self._chat(system_prompt=system_prompt, user_prompt=user_prompt)
            parsed = _extract_json_object(response_text)

            symbols: list[str] = []
            seen: set[str] = set()
            for raw in parsed.get("symbols", []):
                sym = _normalize_ticker(raw)
                if not sym or sym in seen:
                    continue
                seen.add(sym)
                symbols.append(sym)
                if len(symbols) >= self.max_focus_symbols:
                    break
            if not symbols:
                symbols = pre_analysis.candidate_symbols[: self.max_focus_symbols] or ["SPY", "QQQ"]

            rationale_raw = parsed.get("rationale_by_symbol")
            rationale: dict[str, str] = {}
            if isinstance(rationale_raw, dict):
                for sym in symbols:
                    value = rationale_raw.get(sym) or rationale_raw.get(sym.upper())
                    if value:
                        rationale[sym] = str(value)
            for sym in symbols:
                rationale.setdefault(sym, "Symbole retenu après revue des signaux et contraintes runtime.")

            questions = [str(x).strip() for x in parsed.get("questions", []) if str(x).strip()][:8]
            if not questions:
                questions = [f"{symbols[0]}: confirmer le signal avant ordre ?"]

            result = FocusSelection(symbols=symbols, rationale_by_symbol=rationale, questions=questions)
            self._last_trace = {
                "mode": "reasoning",
                "prompt": user_prompt,
                "response": response_text,
                "error": "",
            }
            return result
        except Exception as exc:
            fallback = self.fallback_agent.run(pre_analysis, snapshot)
            self._last_trace = {
                "mode": "fallback",
                "prompt": user_prompt,
                "response": response_text,
                "error": f"{type(exc).__name__}: {exc}",
            }
            return fallback


def _guard_orders_from_trade_errors(
    *,
    parsed: dict[str, Any],
    trade_events: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    adjusted = dict(parsed)
    notes: list[str] = []
    last_error = _latest_api_error_message(trade_events)
    if not last_error:
        return adjusted, notes

    lower = last_error.lower()
    orders = adjusted.get("orders")
    if not isinstance(orders, list):
        orders = []

    if "insufficient buying power" in lower:
        adjusted["should_execute"] = False
        adjusted["orders"] = []
        notes.append(
            "Blocage préventif: dernier run en erreur 'insufficient buying power'; aucun nouvel ordre envoyé."
        )

    if "not allowed to short" in lower or "short non autorisé" in lower:
        filtered = [o for o in orders if str(o.get("side", "")).lower() != "sell"]
        if len(filtered) != len(orders):
            adjusted["orders"] = filtered
            adjusted["should_execute"] = bool(filtered)
            notes.append(
                "Ajustement préventif: ordres SELL retirés après erreur récente de short non autorisé."
            )

    return adjusted, notes


@dataclass
class ReasoningFinalTraderAgent(_ReasoningAgentBase):
    fallback_agent: Any
    order_qty: float = 1.0

    def run(
        self,
        pre_analysis: PreAnalysis,
        focus: FocusSelection,
        financial: FinancialSnapshot,
        fresh: FreshMarketSnapshot,
    ) -> FinalDecision:
        runtime_events, trade_events, latest_error = self._load_histories()

        system_prompt = """
Tu es l'agent de décision finale de trading. Réponse JSON strict.
Obligation:
- Consulte l'historique de transactions.
- Vérifie le dernier message d'erreur API.
- Explique si ce message impacte le prochain ordre et adapte les ordres.
""".strip()

        user_prompt = _limit_lines(
            json.dumps(
                {
                    "task": "Décision finale + ordres",
                    "expected_json_schema": {
                        "action": "LONG|SHORT|HOLD",
                        "symbols": ["str"],
                        "thesis": "str",
                        "risk_controls": ["str"],
                        "confidence": "low|medium|high",
                        "should_execute": "bool",
                        "orders": [
                            {
                                "symbol": "str",
                                "side": "buy|sell",
                                "qty": "number",
                                "type": "market",
                                "time_in_force": "day",
                            }
                        ],
                    },
                    "instruction_obligatoire": (
                        "Vérifie l'historique transactionnel, identifie le dernier message d'erreur API "
                        "et explicite son impact sur l'ordre suivant."
                    ),
                    "latest_api_error_message": latest_error,
                    "runtime_events_recent": runtime_events,
                    "trade_events_recent": trade_events,
                    "pre_analysis": {
                        "summary": pre_analysis.summary,
                        "candidate_symbols": pre_analysis.candidate_symbols,
                        "risks": pre_analysis.risks,
                        "confidence": pre_analysis.confidence,
                    },
                    "focus_selection": {
                        "symbols": focus.symbols,
                        "rationale_by_symbol": focus.rationale_by_symbol,
                        "questions": focus.questions,
                    },
                    "financial_snapshot": {
                        "source": financial.source,
                        "asof": financial.asof,
                        "symbols_data": financial.symbols_data,
                        "missing_symbols": financial.missing_symbols,
                        "notes": financial.notes,
                    },
                    "fresh_notes": fresh.notes,
                    "default_order_qty": self.order_qty,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        response_text = ""
        try:
            response_text = self._chat(system_prompt=system_prompt, user_prompt=user_prompt)
            parsed = _extract_json_object(response_text)
            parsed, guard_notes = _guard_orders_from_trade_errors(parsed=parsed, trade_events=trade_events)

            action = str(parsed.get("action") or "HOLD").strip().upper()
            if action not in {"LONG", "SHORT", "HOLD"}:
                action = "HOLD"

            symbols: list[str] = []
            seen: set[str] = set()
            for raw in parsed.get("symbols", []):
                sym = _normalize_ticker(raw)
                if not sym or sym in seen:
                    continue
                seen.add(sym)
                symbols.append(sym)

            orders: list[dict[str, Any]] = []
            for raw in parsed.get("orders", []):
                if not isinstance(raw, dict):
                    continue
                symbol = _normalize_ticker(raw.get("symbol"))
                side = str(raw.get("side") or "").strip().lower()
                if not symbol or side not in {"buy", "sell"}:
                    continue
                try:
                    qty = float(raw.get("qty", self.order_qty))
                except (TypeError, ValueError):
                    qty = self.order_qty
                if qty <= 0:
                    continue
                orders.append(
                    {
                        "symbol": symbol,
                        "side": side,
                        "qty": qty,
                        "type": "market",
                        "time_in_force": "day",
                    }
                )

            should_execute = bool(parsed.get("should_execute")) and bool(orders)
            if action == "HOLD":
                should_execute = False
                orders = []

            risk_controls = [str(x).strip() for x in parsed.get("risk_controls", []) if str(x).strip()][:8]
            risk_controls.extend(guard_notes)
            if not risk_controls:
                risk_controls = ["Aucun contrôle de risque explicite fourni par le modèle."]

            result = FinalDecision(
                action=action,  # type: ignore[arg-type]
                symbols=symbols,
                thesis=str(parsed.get("thesis") or "Décision basée sur le contexte courant."),
                risk_controls=risk_controls,
                confidence=_normalize_confidence(parsed.get("confidence"), default="low"),
                should_execute=should_execute,
                orders=orders,
            )
            self._last_trace = {
                "mode": "reasoning",
                "prompt": user_prompt,
                "response": response_text,
                "error": "",
            }
            return result
        except Exception as exc:
            fallback = self.fallback_agent.run(pre_analysis, focus, financial, fresh)
            self._last_trace = {
                "mode": "fallback",
                "prompt": user_prompt,
                "response": response_text,
                "error": f"{type(exc).__name__}: {exc}",
            }
            return fallback
