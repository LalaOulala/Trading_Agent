from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from trading_pipeline.config import PipelineConfig
from trading_pipeline.execution.alpaca_executor import AlpacaTradeExecutor
from trading_pipeline.ui.dashboard_data import build_orders_history, extract_timing_metrics, load_artifact_records
from trading_pipeline.ui.theme import apply_theme, render_header, render_metric_card
from trading_pipeline.ui.workflow_runner import evaluate_run_feedback, run_workflow_once


REPO_ROOT = Path(__file__).resolve().parents[1]


def _switch_to_logs(*, file_path: str | None = None) -> None:
    if file_path:
        st.session_state["file_browser_selected"] = file_path
    try:
        st.switch_page("pages/3_Fichiers_Logs.py")
    except Exception:
        st.info("Navigation page indisponible dans cette version Streamlit.")


@st.cache_data(ttl=20, show_spinner=False)
def _load_portfolio_snapshot() -> tuple[dict[str, Any] | None, str | None]:
    config = PipelineConfig.from_env()
    executor = AlpacaTradeExecutor(
        api_key=config.alpaca_api_key,
        api_secret=config.alpaca_api_secret,
        paper=config.alpaca_paper,
        execute_live=False,
        require_confirmation=False,
    )
    return executor._load_portfolio_snapshot()


def _render_latest_orders(latest_artifact: dict[str, Any]) -> None:
    decision = latest_artifact.get("final_decision", {})
    execution = latest_artifact.get("execution_report", {})
    st.write(
        f"Action={decision.get('action', 'n/a')} | "
        f"Confidence={decision.get('confidence', 'n/a')} | "
        f"Execution status={execution.get('status', 'n/a')}"
    )
    st.caption(f"Execution message: {execution.get('message', 'n/a')}")

    details = execution.get("details", [])
    if isinstance(details, list) and details:
        st.dataframe(details, width="stretch", hide_index=True)
    else:
        st.info("Aucun ordre detaille dans la derniere execution.")


def _render_portfolio() -> None:
    snapshot, error_message = _load_portfolio_snapshot()
    if error_message:
        st.info(f"Portefeuille indisponible: {error_message}")
        return
    if not snapshot:
        st.info("Portefeuille indisponible.")
        return

    top = st.columns(4)
    with top[0]:
        render_metric_card(label="Status", value=str(snapshot.get("status", "n/a")))
    with top[1]:
        render_metric_card(label="Equity", value=str(snapshot.get("equity", "n/a")))
    with top[2]:
        render_metric_card(label="Cash", value=str(snapshot.get("cash", "n/a")))
    with top[3]:
        render_metric_card(label="Buying power", value=str(snapshot.get("buying_power", "n/a")))

    positions = snapshot.get("positions", [])
    if isinstance(positions, list) and positions:
        st.dataframe(positions, width="stretch", hide_index=True)
    else:
        st.caption("Aucune position ouverte.")


def main() -> None:
    apply_theme(page_title="Dashboard Workflow", layout="wide")
    render_header(
        title="Dashboard Workflow",
        subtitle=(
            "Suivi run, ordres, portefeuille et delai request/reflexion/prochaine iteration."
        ),
    )

    with st.sidebar:
        st.header("Donnees")
        artifacts_dir_raw = st.text_input(
            "Dossier artefacts V2",
            value=str(REPO_ROOT / "pipeline_runs_v2"),
        )
        interval_seconds = int(
            st.number_input(
                "Intervalle cible (sec)",
                min_value=10,
                max_value=7200,
                value=300,
                step=10,
            )
        )
        st.button("Rafraichir", width="stretch")

        st.markdown("---")
        st.header("Workflow")
        query = st.text_input("Query", value="S&P 500 market drivers today")
        web_topic = st.selectbox("Web topic", ["finance", "news", "general"], index=0)
        web_time_range = st.selectbox(
            "Web time range",
            ["day", "week", "month", "year", "none"],
            index=0,
        )
        web_max_results = int(
            st.slider("Web max results", min_value=1, max_value=20, value=8, step=1)
        )
        financial_provider = st.selectbox(
            "Financial provider",
            ["yahoo", "placeholder"],
            index=0,
        )
        execute_live = st.toggle("Execution live Alpaca (auto-confirm)", value=False)
        run_clicked = st.button("Lancer un cycle run_v2", type="primary", width="stretch")

    artifacts_dir = Path(artifacts_dir_raw).expanduser()
    before_records = load_artifact_records(artifacts_dir)
    before_latest_artifact = before_records[0]["artifact"] if before_records else None

    if run_clicked:
        with st.spinner("Execution du workflow en cours..."):
            run_result = run_workflow_once(
                query=query,
                web_topic=web_topic,
                web_time_range=web_time_range,
                web_max_results=web_max_results,
                financial_provider=financial_provider,
                interval_seconds=interval_seconds,
                execute_live=execute_live,
            )
        st.session_state["last_workflow_run"] = run_result
        _load_portfolio_snapshot.clear()

    records = load_artifact_records(artifacts_dir)
    latest_artifact = records[0]["artifact"] if records else before_latest_artifact

    run_result = st.session_state.get("last_workflow_run")
    level, message = evaluate_run_feedback(run_result=run_result, latest_artifact=latest_artifact)
    if run_result:
        if level == "error":
            st.error(message)
        elif level == "warning":
            st.warning(message)
        elif level == "success":
            st.success(message)
        else:
            st.info(message)
        with st.expander("Logs du dernier lancement"):
            st.code(run_result.get("cmd", ""), language="bash")
            st.text(run_result.get("stdout", ""))
            stderr = run_result.get("stderr", "")
            if stderr:
                st.text(stderr)

    if not records:
        st.warning(f"Aucun artefact JSON trouve dans: {artifacts_dir}")
        st.stop()

    latest_record = records[0]
    timing = extract_timing_metrics(latest_record, interval_seconds=interval_seconds)

    cols = st.columns(4)
    with cols[0]:
        render_metric_card(label="Derniere request (EU)", value=timing["last_request_label"])
    with cols[1]:
        render_metric_card(label="Derniere reflexion (EU)", value=timing["last_reflection_label"])
    with cols[2]:
        delay = timing.get("request_to_reflection_seconds")
        delay_value = f"{delay:.2f} s" if isinstance(delay, float) else "N/A"
        render_metric_card(label="Delai request -> reflexion", value=delay_value)
    with cols[3]:
        next_in = timing.get("next_iteration_in_seconds")
        next_value = f"{next_in} s" if isinstance(next_in, int) else "N/A"
        render_metric_card(label="Prochaine iteration dans", value=next_value)

    st.caption(
        f"Dernier artefact charge: {latest_record['path'].name} | "
        f"query={latest_artifact.get('query', 'n/a')}"
    )
    if st.button("Ouvrir le dernier artefact JSON dans la page Fichiers", width="stretch"):
        _switch_to_logs(file_path=str(latest_record["path"]))

    left, right = st.columns([1.25, 1.0])
    with left:
        st.subheader("Ordres")
        _render_latest_orders(latest_artifact)

        st.markdown("#### Historique ordres")
        orders_history = build_orders_history(records, max_rows=80)
        if orders_history:
            st.dataframe(orders_history, width="stretch", hide_index=True)
        else:
            st.info("Aucun ordre trouve dans l'historique courant.")

    with right:
        st.subheader("Portefeuille")
        _render_portfolio()


if __name__ == "__main__":
    main()

