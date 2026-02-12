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
from trading_pipeline.models import utc_now_iso


@dataclass
class TradingDecisionPipeline:
    fresh_collector: FreshDataCollector
    pre_agent: PreAnalysisAgent
    focus_agent: FocusTraderAgent
    financial_provider: FinancialDataProvider
    final_agent: FinalTraderAgent
    executor: TradeExecutor

    def run(self, query: str) -> dict[str, Any]:
        fresh = self.fresh_collector.collect(query)
        pre = self.pre_agent.run(fresh)
        focus = self.focus_agent.run(pre, fresh)
        financial = self.financial_provider.fetch(focus.symbols)
        final = self.final_agent.run(pre, focus, financial, fresh)
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
        }

    @staticmethod
    def save_artifact(artifact: dict[str, Any], out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
