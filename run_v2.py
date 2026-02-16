"""
Orchestrateur V2 (architecture segmentée OO):

1) Fresh data branch: web + social
2) IA pre-analysis
3) IA focus trader (shortlist symboles)
4) Financial data branch (Yahoo pool réel ou placeholder)
5) IA final trader (décision)
6) Execution branch (Alpaca, optionnelle)
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from trading_pipeline.agents import (
    FinalTraderAgent,
    FocusTraderAgent,
    PreAnalysisAgent,
    ReasoningFinalTraderAgent,
    ReasoningFocusTraderAgent,
    ReasoningPreAnalysisAgent,
)
from trading_pipeline.collectors import FreshDataHub, TavilyWebCollector, XPlaceholderCollector
from trading_pipeline.config import PipelineConfig
from trading_pipeline.context import (
    DEFAULT_RUN_V2_TERMINAL_HISTORY_FILE,
    DEFAULT_RUN_V2_TRADE_HISTORY_FILE,
    DEFAULT_RUN_V2_SESSION_DIR,
    SessionMarkdownLogger,
    append_runtime_event,
    append_trade_event,
)
from trading_pipeline.execution import AlpacaTradeExecutor
from trading_pipeline.financial import YahooFinancePoolProvider, YahooPlaceholderProvider
from trading_pipeline.workflow import TradingDecisionPipeline


def _split_csv(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    values = [x.strip() for x in raw.split(",") if x.strip()]
    return values or None


def _run_once(
    *,
    pipeline: TradingDecisionPipeline,
    query: str,
    output_dir: Path,
) -> tuple[dict[str, object], Path]:
    artifact = pipeline.run(query)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_path = output_dir / f"{timestamp}.json"
    TradingDecisionPipeline.save_artifact(artifact, out_path)
    return artifact, out_path


def _print_summary(*, query: str, artifact: dict[str, object], out_path: Path) -> None:
    decision = artifact.get("final_decision", {})
    execution = artifact.get("execution_report", {})
    print("[V2 Pipeline] done")
    print(f"- Query: {query}")
    print(f"- Action: {decision.get('action')}")
    print(f"- Symbols: {decision.get('symbols')}")
    print(f"- Execute: {decision.get('should_execute')}")
    print(f"- Broker status: {execution.get('status')} ({execution.get('message')})")
    print(f"- Artifact: {out_path}")


def _summary_message(*, query: str, artifact: dict[str, object], out_path: Path) -> str:
    decision = artifact.get("final_decision", {})
    execution = artifact.get("execution_report", {})
    lines = [
        "[V2 Pipeline] done",
        f"- Query: {query}",
        f"- Action: {decision.get('action')}",
        f"- Symbols: {decision.get('symbols')}",
        f"- Execute: {decision.get('should_execute')}",
        f"- Broker status: {execution.get('status')} ({execution.get('message')})",
        f"- Artifact: {out_path}",
    ]
    return "\n".join(lines)


def _record_runtime_event(
    *,
    history_file: Path,
    event_type: str,
    message: str,
    cycle: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        append_runtime_event(
            history_file,
            event_type=event_type,
            message=message,
            cycle=cycle,
            payload=payload,
        )
    except Exception:
        # Ne jamais casser le pipeline pour un souci d'écriture d'historique.
        pass


def _record_trade_event(
    *,
    history_file: Path,
    query: str,
    artifact: dict[str, object],
    out_path: Path,
    cycle: int | None,
) -> None:
    try:
        append_trade_event(
            history_file,
            query=query,
            cycle=cycle,
            final_decision=artifact.get("final_decision") if isinstance(artifact, dict) else None,
            execution_report=artifact.get("execution_report") if isinstance(artifact, dict) else None,
            artifact_path=str(out_path),
        )
    except Exception:
        # Ne jamais casser le pipeline pour un souci d'écriture d'historique.
        pass


def _record_session_agent_traces(
    *,
    logger: SessionMarkdownLogger | None,
    artifact: dict[str, object],
    cycle: int | None,
) -> None:
    if logger is None:
        return
    traces = artifact.get("agent_traces")
    if not isinstance(traces, list):
        return
    for item in traces:
        if not isinstance(item, dict):
            continue
        step = str(item.get("step") or "unknown_step")
        trace = {
            "prompt": str(item.get("prompt") or ""),
            "response": str(item.get("response") or ""),
            "error": str(item.get("error") or ""),
        }
        logger.log_agent_trace(step=step, trace=trace, cycle=cycle)


def _sleep_between_runs(interval_seconds: int) -> str | None:
    if interval_seconds <= 0:
        return None
    next_run = datetime.now().timestamp() + interval_seconds
    next_run_str = datetime.fromtimestamp(next_run).strftime("%Y-%m-%d %H:%M:%S")
    message = f"[V2 Pipeline] next run in {interval_seconds}s (at {next_run_str})"
    print(message)
    time.sleep(interval_seconds)
    return message


def _coerce_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_duration(total_seconds: int) -> str:
    seconds = max(int(total_seconds), 0)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}j")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if sec or not parts:
        parts.append(f"{sec}s")
    return " ".join(parts)


def _market_closed_message(now: datetime, next_open: datetime) -> str:
    now_utc = _coerce_utc(now)
    next_open_utc = _coerce_utc(next_open)
    remaining = _format_duration(int((next_open_utc - now_utc).total_seconds()))
    next_open_local = next_open_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return (
        f"Le marché est fermé, il réouvre dans {remaining} "
        f"(prochaine ouverture: {next_open_local})."
    )


def _check_market_open(*, api_key: str, api_secret: str, paper: bool) -> tuple[bool, str | None]:
    try:
        from alpaca.trading.client import TradingClient
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            f"alpaca-py indisponible ({type(exc).__name__}: {exc})"
        ) from exc

    client = TradingClient(api_key=api_key, secret_key=api_secret, paper=paper)
    clock = client.get_clock()
    if bool(getattr(clock, "is_open", False)):
        return True, None

    now = getattr(clock, "timestamp", None)
    next_open = getattr(clock, "next_open", None)
    if isinstance(now, datetime) and isinstance(next_open, datetime):
        return False, _market_closed_message(now, next_open)
    return False, "Le marché est fermé, heure de réouverture indisponible."


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
        help="Nombre max de résultats web pour la requête principale Tavily (1..20).",
    )
    parser.add_argument(
        "--web-max-follow-up-queries",
        type=int,
        default=3,
        help=(
            "Nombre max de requêtes Tavily contextuelles supplémentaires "
            "(défaut: 3, 0 pour désactiver)."
        ),
    )
    parser.add_argument(
        "--web-follow-up-max-results",
        type=int,
        default=5,
        help="Nombre max de résultats par requête Tavily contextuelle (1..20).",
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
    parser.add_argument(
        "--auto-confirm-orders",
        "--auto-accept-orders",
        dest="auto_confirm_orders",
        action="store_true",
        help=(
            "Bypass la confirmation interactive avant envoi des ordres Alpaca "
            "(alias: --auto-accept-orders)."
        ),
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="(Option conservée) Exécute le pipeline en continu jusqu'à interruption utilisateur (Ctrl+C).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exécute un seul cycle puis quitte (désactive le mode boucle par défaut).",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=300,
        help="Intervalle entre deux runs quand `--loop` est activé (défaut: 300).",
    )
    parser.add_argument(
        "--stop-if-market-closed",
        action="store_true",
        help=(
            "Vérifie l'état marché via Alpaca avant chaque cycle; "
            "si fermé, affiche le délai avant réouverture puis quitte."
        ),
    )
    parser.add_argument(
        "--terminal-history-file",
        type=Path,
        default=DEFAULT_RUN_V2_TERMINAL_HISTORY_FILE,
        help=(
            "Fichier JSONL d'historique runtime terminal (inclut erreurs API), "
            "consultable par les agents."
        ),
    )
    parser.add_argument(
        "--trade-history-file",
        type=Path,
        default=DEFAULT_RUN_V2_TRADE_HISTORY_FILE,
        help=(
            "Fichier JSONL d'historique transactionnel (décisions + messages broker), "
            "consultable par les agents."
        ),
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=15,
        help="Nombre d'événements récents (runtime + transactions) injectés dans chaque prompt agent.",
    )
    parser.add_argument(
        "--reasoning-all-steps",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Active les agents reasoning (xAI) à chaque étape pre/focus/final. "
            "Utiliser --no-reasoning-all-steps pour revenir au mode déterministe."
        ),
    )
    parser.add_argument(
        "--reasoning-model",
        default="grok-4-1-fast-reasoning-latest",
        help="Modèle xAI utilisé par les agents reasoning.",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "high"],
        default="high",
        help="Effort de raisonnement xAI utilisé par les agents reasoning.",
    )
    parser.add_argument(
        "--reasoning-max-tokens",
        type=int,
        default=1800,
        help="Tokens max pour chaque appel reasoning d'agent.",
    )
    parser.add_argument(
        "--agent-follow-up-queries",
        type=int,
        default=3,
        help="Nombre max de requêtes Tavily supplémentaires proposées par l'agent pre-analysis.",
    )
    parser.add_argument(
        "--session-markdown-dir",
        type=Path,
        default=DEFAULT_RUN_V2_SESSION_DIR,
        help="Répertoire des journaux Markdown de session (un fichier par lancement).",
    )
    args = parser.parse_args()

    if args.web_max_results < 1 or args.web_max_results > 20:
        raise ValueError("--web-max-results doit être entre 1 et 20.")
    if args.web_max_follow_up_queries < 0:
        raise ValueError("--web-max-follow-up-queries doit être >= 0.")
    if args.web_follow_up_max_results < 1 or args.web_follow_up_max_results > 20:
        raise ValueError("--web-follow-up-max-results doit être entre 1 et 20.")
    if args.interval_seconds <= 0:
        raise ValueError("--interval-seconds doit être > 0.")
    if args.history_limit < 0:
        raise ValueError("--history-limit doit être >= 0.")
    if args.reasoning_max_tokens <= 0:
        raise ValueError("--reasoning-max-tokens doit être > 0.")
    if args.agent_follow_up_queries < 0:
        raise ValueError("--agent-follow-up-queries doit être >= 0.")

    repo_root = Path(__file__).resolve().parent
    load_dotenv(dotenv_path=repo_root / ".env", override=False)

    config = PipelineConfig.from_env(output_dir=args.output_dir)
    if not config.tavily_api_key:
        raise RuntimeError(
            "TAVILY_API_KEY manquante: la branche fresh data web ne peut pas démarrer."
        )
    if args.stop_if_market_closed and (not config.alpaca_api_key or not config.alpaca_api_secret):
        raise RuntimeError(
            "--stop-if-market-closed requiert ALPACA_API_KEY et ALPACA_API_SECRET."
        )

    session_logger = SessionMarkdownLogger.start_new(
        base_dir=args.session_markdown_dir,
        query=args.query,
        args_dict=vars(args),
        prefix="run_v2",
    )

    reasoning_enabled = bool(args.reasoning_all_steps and config.xai_api_key)
    if args.reasoning_all_steps and not config.xai_api_key:
        warning = (
            "[V2 Pipeline] reasoning-all-steps demandé mais XAI_API_KEY absente: "
            "fallback déterministe activé."
        )
        print(warning)
        session_logger.log_cli_message(message=warning, cycle=None)
        _record_runtime_event(
            history_file=args.terminal_history_file,
            event_type="reasoning_disabled",
            message=warning,
        )

    web_collector = TavilyWebCollector(
        api_key=config.tavily_api_key,
        topic=args.web_topic,
        search_depth=args.web_search_depth,
        time_range=args.web_time_range,
        max_results=args.web_max_results,
        max_follow_up_queries=args.web_max_follow_up_queries,
        follow_up_max_results=args.web_follow_up_max_results,
        include_domains=_split_csv(args.web_include_domains),
        exclude_domains=_split_csv(args.web_exclude_domains),
        include_answer=False,
    )
    social_collector = XPlaceholderCollector(cache_file=args.x_cache_file)
    fresh_hub = FreshDataHub(web_collector=web_collector, social_collector=social_collector)

    base_pre_agent = PreAnalysisAgent(max_candidate_symbols=config.max_candidate_symbols)
    base_focus_agent = FocusTraderAgent(max_focus_symbols=config.max_focus_symbols)
    if args.financial_provider == "yahoo":
        financial_provider = YahooFinancePoolProvider()
    else:
        financial_provider = YahooPlaceholderProvider(mock_file=args.financial_mock_file)
    base_final_agent = FinalTraderAgent(order_qty=args.order_qty)

    if reasoning_enabled:
        pre_agent = ReasoningPreAnalysisAgent(
            api_key=config.xai_api_key or "",
            model=args.reasoning_model,
            reasoning_effort=args.reasoning_effort,
            max_tokens=args.reasoning_max_tokens,
            runtime_history_file=args.terminal_history_file,
            trade_history_file=args.trade_history_file,
            history_limit=args.history_limit,
            fallback_agent=base_pre_agent,
            max_candidate_symbols=config.max_candidate_symbols,
            max_follow_up_queries=args.agent_follow_up_queries,
        )
        focus_agent = ReasoningFocusTraderAgent(
            api_key=config.xai_api_key or "",
            model=args.reasoning_model,
            reasoning_effort=args.reasoning_effort,
            max_tokens=args.reasoning_max_tokens,
            runtime_history_file=args.terminal_history_file,
            trade_history_file=args.trade_history_file,
            history_limit=args.history_limit,
            fallback_agent=base_focus_agent,
            max_focus_symbols=config.max_focus_symbols,
        )
        final_agent = ReasoningFinalTraderAgent(
            api_key=config.xai_api_key or "",
            model=args.reasoning_model,
            reasoning_effort=args.reasoning_effort,
            max_tokens=args.reasoning_max_tokens,
            runtime_history_file=args.terminal_history_file,
            trade_history_file=args.trade_history_file,
            history_limit=args.history_limit,
            fallback_agent=base_final_agent,
            order_qty=args.order_qty,
        )
    else:
        pre_agent = base_pre_agent
        focus_agent = base_focus_agent
        final_agent = base_final_agent
    executor = AlpacaTradeExecutor(
        api_key=config.alpaca_api_key,
        api_secret=config.alpaca_api_secret,
        paper=config.alpaca_paper,
        execute_live=args.execute_orders or config.execute_orders,
        require_confirmation=not args.auto_confirm_orders,
    )

    pipeline = TradingDecisionPipeline(
        fresh_collector=fresh_hub,
        pre_agent=pre_agent,
        focus_agent=focus_agent,
        financial_provider=financial_provider,
        final_agent=final_agent,
        executor=executor,
    )

    reasoning_mode_message = (
        "[V2 Pipeline] reasoning agents: "
        f"{'enabled' if reasoning_enabled else 'disabled'} "
        f"(model={args.reasoning_model if reasoning_enabled else 'deterministic'})"
    )
    print(reasoning_mode_message)
    session_logger.log_cli_message(message=reasoning_mode_message, cycle=None)
    _record_runtime_event(
        history_file=args.terminal_history_file,
        event_type="reasoning_mode",
        message=reasoning_mode_message,
    )

    loop_mode = not args.once

    if not loop_mode:
        if args.stop_if_market_closed:
            is_open, closed_message = _check_market_open(
                api_key=config.alpaca_api_key or "",
                api_secret=config.alpaca_api_secret or "",
                paper=config.alpaca_paper,
            )
            if not is_open:
                message = f"[V2 Pipeline] {closed_message}"
                print(message)
                session_logger.log_cli_message(message=message, cycle=None)
                _record_runtime_event(
                    history_file=args.terminal_history_file,
                    event_type="market_closed",
                    message=message,
                )
                session_logger.finalize(reason="market_closed")
                return
        artifact, out_path = _run_once(
            pipeline=pipeline,
            query=args.query,
            output_dir=config.output_dir,
        )
        summary_message = _summary_message(query=args.query, artifact=artifact, out_path=out_path)
        _print_summary(query=args.query, artifact=artifact, out_path=out_path)
        _record_runtime_event(
            history_file=args.terminal_history_file,
            event_type="cycle_summary",
            message=summary_message,
            payload={
                "query": args.query,
                "artifact": str(out_path),
                "execution_report": artifact.get("execution_report"),
                "final_decision": artifact.get("final_decision"),
            },
        )
        _record_trade_event(
            history_file=args.trade_history_file,
            query=args.query,
            artifact=artifact,
            out_path=out_path,
            cycle=None,
        )
        _record_session_agent_traces(logger=session_logger, artifact=artifact, cycle=None)
        session_logger.log_cycle_artifact(
            cycle=None,
            summary_message=summary_message,
            artifact_path=out_path,
            final_decision=artifact.get("final_decision") if isinstance(artifact, dict) else None,
            execution_report=artifact.get("execution_report") if isinstance(artifact, dict) else None,
        )
        session_logger.finalize(reason="once_completed")
        return

    loop_message = (
        "[V2 Pipeline] loop mode active "
        f"(interval={args.interval_seconds}s). Press Ctrl+C to stop."
    )
    print(loop_message)
    session_logger.log_cli_message(message=loop_message, cycle=None)
    _record_runtime_event(
        history_file=args.terminal_history_file,
        event_type="loop_start",
        message=loop_message,
    )
    cycle = 0
    try:
        while True:
            if args.stop_if_market_closed:
                is_open, closed_message = _check_market_open(
                    api_key=config.alpaca_api_key or "",
                    api_secret=config.alpaca_api_secret or "",
                    paper=config.alpaca_paper,
                )
                if not is_open:
                    message = f"[V2 Pipeline] {closed_message}"
                    print(message)
                    session_logger.log_cli_message(message=message, cycle=cycle if cycle > 0 else None)
                    _record_runtime_event(
                        history_file=args.terminal_history_file,
                        event_type="market_closed",
                        message=message,
                        cycle=cycle if cycle > 0 else None,
                    )
                    session_logger.finalize(reason="market_closed")
                    return
            cycle += 1
            started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cycle_start_message = f"[V2 Pipeline] cycle #{cycle} started at {started_at}"
            print(f"\n{cycle_start_message}")
            session_logger.log_cli_message(message=cycle_start_message, cycle=cycle)
            _record_runtime_event(
                history_file=args.terminal_history_file,
                event_type="cycle_start",
                message=cycle_start_message,
                cycle=cycle,
            )
            try:
                artifact, out_path = _run_once(
                    pipeline=pipeline,
                    query=args.query,
                    output_dir=config.output_dir,
                )
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                error_message = (
                    f"[V2 Pipeline] cycle #{cycle} failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                print(error_message)
                session_logger.log_cli_message(message=error_message, cycle=cycle)
                _record_runtime_event(
                    history_file=args.terminal_history_file,
                    event_type="cycle_failed",
                    message=error_message,
                    cycle=cycle,
                )
            else:
                summary_message = _summary_message(
                    query=args.query,
                    artifact=artifact,
                    out_path=out_path,
                )
                _print_summary(query=args.query, artifact=artifact, out_path=out_path)
                _record_trade_event(
                    history_file=args.trade_history_file,
                    query=args.query,
                    artifact=artifact,
                    out_path=out_path,
                    cycle=cycle,
                )
                _record_session_agent_traces(logger=session_logger, artifact=artifact, cycle=cycle)
                session_logger.log_cycle_artifact(
                    cycle=cycle,
                    summary_message=summary_message,
                    artifact_path=out_path,
                    final_decision=artifact.get("final_decision") if isinstance(artifact, dict) else None,
                    execution_report=artifact.get("execution_report") if isinstance(artifact, dict) else None,
                )
                _record_runtime_event(
                    history_file=args.terminal_history_file,
                    event_type="cycle_summary",
                    message=summary_message,
                    cycle=cycle,
                    payload={
                        "query": args.query,
                        "artifact": str(out_path),
                        "execution_report": artifact.get("execution_report"),
                        "final_decision": artifact.get("final_decision"),
                    },
                )

            next_run_message = _sleep_between_runs(args.interval_seconds)
            if next_run_message:
                session_logger.log_cli_message(message=next_run_message, cycle=cycle)
                _record_runtime_event(
                    history_file=args.terminal_history_file,
                    event_type="loop_sleep",
                    message=next_run_message,
                    cycle=cycle,
                )
    except KeyboardInterrupt:
        interrupted_message = "[V2 Pipeline] interrupted by user. Loop stopped."
        print(f"\n{interrupted_message}")
        session_logger.log_cli_message(message=interrupted_message, cycle=cycle if cycle > 0 else None)
        _record_runtime_event(
            history_file=args.terminal_history_file,
            event_type="loop_interrupted",
            message=interrupted_message,
            cycle=cycle if cycle > 0 else None,
        )
        session_logger.finalize(reason="user_interrupt")


if __name__ == "__main__":
    main()
