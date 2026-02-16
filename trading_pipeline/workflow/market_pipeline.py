from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from trading_pipeline.agents.final_trader import FinalTraderAgent
from trading_pipeline.agents.focus_trader import FocusTraderAgent
from trading_pipeline.agents.pre_analysis import PreAnalysisAgent
from trading_pipeline.collectors.base import FreshDataCollector
from trading_pipeline.execution.base import TradeExecutor
from trading_pipeline.financial.base import FinancialDataProvider
from trading_pipeline.models import FreshMarketSnapshot, FreshSignal, utc_now_iso


@dataclass
class TradingDecisionPipeline:
    fresh_collector: FreshDataCollector
    pre_agent: PreAnalysisAgent
    focus_agent: FocusTraderAgent
    financial_provider: FinancialDataProvider
    final_agent: FinalTraderAgent
    executor: TradeExecutor

    @staticmethod
    def _collect_agent_trace(agent: Any, *, step: str) -> dict[str, Any] | None:
        getter = getattr(agent, "get_last_trace", None)
        if not callable(getter):
            return None
        trace = getter()
        if not isinstance(trace, dict):
            return None
        return {"step": step, **trace}

    @staticmethod
    def _merge_web_signals(
        base_signals: list[FreshSignal],
        extra_signals: list[FreshSignal],
    ) -> list[FreshSignal]:
        merged: list[FreshSignal] = []
        seen: set[str] = set()

        def _key(signal: FreshSignal) -> str:
            url = signal.url.strip().rstrip("/").lower()
            if url:
                return url
            return f"{signal.title.strip().lower()}::{signal.snippet.strip().lower()}"

        for signal in [*base_signals, *extra_signals]:
            key = _key(signal)
            if key in seen:
                continue
            seen.add(key)
            merged.append(signal)
        return merged

    def run(self, query: str) -> dict[str, Any]:
        fresh = self.fresh_collector.collect(query)
        agent_traces: list[dict[str, Any]] = []

        pre = self.pre_agent.run(fresh)
        pre_trace = self._collect_agent_trace(self.pre_agent, step="pre_analysis")
        if pre_trace:
            agent_traces.append(pre_trace)

        follow_up_queries: list[str] = []
        get_follow_ups = getattr(self.pre_agent, "get_follow_up_web_queries", None)
        collect_additional_web = getattr(self.fresh_collector, "collect_additional_web", None)
        if callable(get_follow_ups):
            raw_follow_ups = get_follow_ups()
            if isinstance(raw_follow_ups, list):
                follow_up_queries = [str(q).strip() for q in raw_follow_ups if str(q).strip()]

        if follow_up_queries and callable(collect_additional_web):
            extra_result = collect_additional_web(follow_up_queries)
            if extra_result.signals:
                fresh = FreshMarketSnapshot(
                    generated_at=fresh.generated_at,
                    web_signals=self._merge_web_signals(fresh.web_signals, extra_result.signals),
                    social_signals=fresh.social_signals,
                    notes=[
                        *fresh.notes,
                        f"Follow-up web queries demandées par pre-analysis: {len(follow_up_queries)}",
                        *extra_result.notes,
                    ],
                )
                pre = self.pre_agent.run(fresh)
                pre_follow_up_trace = self._collect_agent_trace(
                    self.pre_agent,
                    step="pre_analysis_after_follow_up",
                )
                if pre_follow_up_trace:
                    agent_traces.append(pre_follow_up_trace)

        focus = self.focus_agent.run(pre, fresh)
        focus_trace = self._collect_agent_trace(self.focus_agent, step="focus_selection")
        if focus_trace:
            agent_traces.append(focus_trace)

        financial = self.financial_provider.fetch(focus.symbols)
        final = self.final_agent.run(pre, focus, financial, fresh)
        final_trace = self._collect_agent_trace(self.final_agent, step="final_decision")
        if final_trace:
            agent_traces.append(final_trace)

        execution = self.executor.execute(final)

        return {
            "generated_at": utc_now_iso(),
            "query": query,
            "fresh_snapshot": asdict(fresh),
            "pre_analysis": asdict(pre),
            "focus_selection": asdict(focus),
            "financial_snapshot": asdict(financial),
            "final_decision": asdict(final),
            "execution_report": asdict(execution),
            "web_follow_up_queries": follow_up_queries,
            "agent_traces": agent_traces,
        }

    @staticmethod
    def save_artifact(artifact: dict[str, Any], out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
