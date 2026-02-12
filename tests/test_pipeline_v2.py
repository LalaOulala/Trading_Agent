from __future__ import annotations

import unittest

from trading_pipeline.agents import FinalTraderAgent, FocusTraderAgent, PreAnalysisAgent
from trading_pipeline.collectors.base import CollectorResult, SocialCollector, WebCollector
from trading_pipeline.collectors.fresh_data_hub import FreshDataHub
from trading_pipeline.execution.alpaca_executor import AlpacaTradeExecutor
from trading_pipeline.financial.yahoo_placeholder import StaticFinancialDataProvider
from trading_pipeline.models import FreshSignal
from trading_pipeline.workflow.market_pipeline import TradingDecisionPipeline


class _StubWebCollector(WebCollector):
    def collect(self, query: str) -> CollectorResult:
        return CollectorResult(
            signals=[
                FreshSignal(
                    source="stub_web",
                    title="AAPL rises after earnings",
                    url="https://example.com/aapl",
                    snippet="AAPL and MSFT lead the move.",
                ),
                FreshSignal(
                    source="stub_web",
                    title="MSFT guidance update",
                    url="https://example.com/msft",
                    snippet="MSFT remains in focus.",
                ),
            ],
            notes=["stub web ok"],
        )


class _StubSocialCollector(SocialCollector):
    def collect(self, query: str) -> CollectorResult:
        return CollectorResult(signals=[], notes=["stub social empty"])


class PipelineV2Tests(unittest.TestCase):
    def _build_pipeline(self, financial_data: dict[str, dict[str, float]]) -> TradingDecisionPipeline:
        fresh_collector = FreshDataHub(
            web_collector=_StubWebCollector(),
            social_collector=_StubSocialCollector(),
        )
        return TradingDecisionPipeline(
            fresh_collector=fresh_collector,
            pre_agent=PreAnalysisAgent(max_candidate_symbols=5),
            focus_agent=FocusTraderAgent(max_focus_symbols=3),
            financial_provider=StaticFinancialDataProvider(data=financial_data),
            final_agent=FinalTraderAgent(order_qty=1.0),
            executor=AlpacaTradeExecutor(
                api_key=None,
                api_secret=None,
                paper=True,
                execute_live=False,
            ),
        )

    def test_pipeline_long_and_dry_run(self) -> None:
        pipeline = self._build_pipeline(
            financial_data={
                "AAPL": {"change_1d_pct": 1.8},
                "MSFT": {"change_1d_pct": 1.1},
            }
        )
        artifact = pipeline.run("market query")
        self.assertEqual(artifact["final_decision"]["action"], "LONG")
        self.assertTrue(artifact["final_decision"]["should_execute"])
        self.assertEqual(artifact["execution_report"]["status"], "dry_run")

    def test_pipeline_hold_without_financial_data(self) -> None:
        pipeline = self._build_pipeline(financial_data={})
        artifact = pipeline.run("market query")
        self.assertEqual(artifact["final_decision"]["action"], "HOLD")
        self.assertFalse(artifact["final_decision"]["should_execute"])
        self.assertEqual(artifact["execution_report"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
