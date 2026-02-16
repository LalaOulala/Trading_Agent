from __future__ import annotations

import unittest

from trading_pipeline.collectors.base import CollectorResult, FreshDataCollector
from trading_pipeline.execution.alpaca_executor import AlpacaTradeExecutor
from trading_pipeline.financial.yahoo_placeholder import StaticFinancialDataProvider
from trading_pipeline.models import FreshMarketSnapshot, FreshSignal, PreAnalysis, utc_now_iso
from trading_pipeline.workflow.market_pipeline import TradingDecisionPipeline
from trading_pipeline.agents.focus_trader import FocusTraderAgent
from trading_pipeline.agents.final_trader import FinalTraderAgent


class _FreshCollectorWithExtra(FreshDataCollector):
    def collect(self, query: str) -> FreshMarketSnapshot:
        return FreshMarketSnapshot(
            generated_at=utc_now_iso(),
            web_signals=[
                FreshSignal(
                    source="stub_web",
                    title="SPY baseline signal",
                    url="https://example.com/base",
                    snippet="SPY moves",
                )
            ],
            social_signals=[],
            notes=["base collected"],
        )

    def collect_additional_web(self, queries: list[str]) -> CollectorResult:
        return CollectorResult(
            signals=[
                FreshSignal(
                    source="stub_web",
                    title="AAPL follow up",
                    url="https://example.com/follow-up",
                    snippet="AAPL catalyst",
                )
            ],
            notes=[f"follow-up queries: {queries}"],
        )


class _PreAgentWithFollowUps:
    def __init__(self) -> None:
        self.run_count = 0

    def run(self, snapshot: FreshMarketSnapshot) -> PreAnalysis:
        self.run_count += 1
        symbols = ["SPY"]
        for signal in snapshot.web_signals:
            if "AAPL" in (signal.title or ""):
                symbols.append("AAPL")
                break
        return PreAnalysis(
            summary="pre",
            key_drivers=[s.title for s in snapshot.web_signals],
            candidate_symbols=symbols,
            risks=["r1"],
            confidence="medium",
        )

    def get_follow_up_web_queries(self) -> list[str]:
        return ["AAPL latest catalyst"]


class PipelineFollowUpQueriesTests(unittest.TestCase):
    def test_pipeline_executes_agent_follow_up_queries(self) -> None:
        pre_agent = _PreAgentWithFollowUps()
        pipeline = TradingDecisionPipeline(
            fresh_collector=_FreshCollectorWithExtra(),
            pre_agent=pre_agent,
            focus_agent=FocusTraderAgent(max_focus_symbols=4),
            financial_provider=StaticFinancialDataProvider(
                data={"SPY": {"change_1d_pct": 0.1}, "AAPL": {"change_1d_pct": 0.2}}
            ),
            final_agent=FinalTraderAgent(order_qty=1.0),
            executor=AlpacaTradeExecutor(
                api_key=None,
                api_secret=None,
                paper=True,
                execute_live=False,
            ),
        )

        artifact = pipeline.run("market query")

        self.assertEqual(artifact.get("web_follow_up_queries"), ["AAPL latest catalyst"])
        self.assertGreaterEqual(pre_agent.run_count, 2)
        self.assertIn("AAPL", artifact["pre_analysis"]["candidate_symbols"])


if __name__ == "__main__":
    unittest.main()
