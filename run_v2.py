"""
Orchestrateur V2 (architecture segmentée OO):

1) Fresh data branch: web + social
2) IA pre-analysis
3) IA focus trader (shortlist symboles)
4) Financial data branch (placeholder Yahoo pour l'instant)
5) IA final trader (décision)
6) Execution branch (Alpaca, optionnelle)
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from trading_pipeline.agents import FinalTraderAgent, FocusTraderAgent, PreAnalysisAgent
from trading_pipeline.collectors import FreshDataHub, TavilyWebCollector, XPlaceholderCollector
from trading_pipeline.config import PipelineConfig
from trading_pipeline.execution import AlpacaTradeExecutor
from trading_pipeline.financial import YahooFinancePoolProvider, YahooPlaceholderProvider
from trading_pipeline.workflow import TradingDecisionPipeline


def _split_csv(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    values = [x.strip() for x in raw.split(",") if x.strip()]
    return values or None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline V2 segmenté: fresh data -> IA -> finance -> décision -> exécution."
    )
    parser.add_argument(
        "--query",
        default="S&P 500 market drivers today",
        help="Question de recherche initiale.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("pipeline_runs_v2"),
        help="Répertoire d'artefacts JSON V2.",
    )
    parser.add_argument(
        "--web-topic",
        choices=["general", "news", "finance"],
        default="finance",
        help="Topic web pour Tavily.",
    )
    parser.add_argument(
        "--web-search-depth",
        choices=["basic", "advanced", "fast", "ultra-fast"],
        default="basic",
        help="Profondeur Tavily.",
    )
    parser.add_argument(
        "--web-time-range",
        choices=["none", "day", "week", "month", "year", "d", "w", "m", "y"],
        default="day",
        help="Fenêtre temporelle Tavily.",
    )
    parser.add_argument(
        "--web-max-results",
        type=int,
        default=8,
        help="Nombre max de résultats web (0..20).",
    )
    parser.add_argument(
        "--web-include-domains",
        default="reuters.com,bloomberg.com,cnbc.com,wsj.com,investopedia.com",
        help="Domaines web autorisés (CSV).",
    )
    parser.add_argument(
        "--web-exclude-domains",
        default=None,
        help="Domaines web exclus (CSV).",
    )
    parser.add_argument(
        "--x-cache-file",
        type=Path,
        default=None,
        help="JSON local optionnel pour injecter des signaux X (placeholder).",
    )
    parser.add_argument(
        "--financial-mock-file",
        type=Path,
        default=None,
        help="JSON mock financier (branche finance) en attendant Yahoo branché.",
    )
    parser.add_argument(
        "--financial-provider",
        choices=["yahoo", "placeholder"],
        default="yahoo",
        help="Provider financier utilisé par la branche data finance.",
    )
    parser.add_argument(
        "--order-qty",
        type=float,
        default=1.0,
        help="Quantité unitaire par ordre proposé.",
    )
    parser.add_argument(
        "--execute-orders",
        action="store_true",
        help="Active l'exécution Alpaca (sinon dry-run).",
    )
    args = parser.parse_args()

    if args.web_max_results < 0 or args.web_max_results > 20:
        raise ValueError("--web-max-results doit être entre 0 et 20.")

    repo_root = Path(__file__).resolve().parent
    load_dotenv(dotenv_path=repo_root / ".env", override=False)

    config = PipelineConfig.from_env(output_dir=args.output_dir)
    if not config.tavily_api_key:
        raise RuntimeError(
            "TAVILY_API_KEY manquante: la branche fresh data web ne peut pas démarrer."
        )

    web_collector = TavilyWebCollector(
        api_key=config.tavily_api_key,
        topic=args.web_topic,
        search_depth=args.web_search_depth,
        time_range=args.web_time_range,
        max_results=args.web_max_results,
        include_domains=_split_csv(args.web_include_domains),
        exclude_domains=_split_csv(args.web_exclude_domains),
        include_answer=False,
    )
    social_collector = XPlaceholderCollector(cache_file=args.x_cache_file)
    fresh_hub = FreshDataHub(web_collector=web_collector, social_collector=social_collector)

    pre_agent = PreAnalysisAgent(max_candidate_symbols=config.max_candidate_symbols)
    focus_agent = FocusTraderAgent(max_focus_symbols=config.max_focus_symbols)
    if args.financial_provider == "yahoo":
        financial_provider = YahooFinancePoolProvider()
    else:
        financial_provider = YahooPlaceholderProvider(mock_file=args.financial_mock_file)
    final_agent = FinalTraderAgent(order_qty=args.order_qty)
    executor = AlpacaTradeExecutor(
        api_key=config.alpaca_api_key,
        api_secret=config.alpaca_api_secret,
        paper=config.alpaca_paper,
        execute_live=args.execute_orders or config.execute_orders,
    )

    pipeline = TradingDecisionPipeline(
        fresh_collector=fresh_hub,
        pre_agent=pre_agent,
        focus_agent=focus_agent,
        financial_provider=financial_provider,
        final_agent=final_agent,
        executor=executor,
    )

    artifact = pipeline.run(args.query)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_path = config.output_dir / f"{timestamp}.json"
    TradingDecisionPipeline.save_artifact(artifact, out_path)

    decision = artifact.get("final_decision", {})
    execution = artifact.get("execution_report", {})
    print("[V2 Pipeline] done")
    print(f"- Query: {args.query}")
    print(f"- Action: {decision.get('action')}")
    print(f"- Symbols: {decision.get('symbols')}")
    print(f"- Execute: {decision.get('should_execute')}")
    print(f"- Broker status: {execution.get('status')} ({execution.get('message')})")
    print(f"- Artifact: {out_path}")


if __name__ == "__main__":
    main()
