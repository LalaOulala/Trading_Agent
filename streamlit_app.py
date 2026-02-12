from __future__ import annotations

from pathlib import Path

import streamlit as st

from trading_pipeline.ui.dashboard_data import load_artifact_records
from trading_pipeline.ui.file_browser import list_log_files
from trading_pipeline.ui.theme import apply_theme, render_header, render_metric_card


REPO_ROOT = Path(__file__).resolve().parent


def main() -> None:
    apply_theme(page_title="Trading Control Room", layout="wide")
    render_header(
        title="Trading Workflow Control Room",
        subtitle=(
            "Accueil multi-pages: pilotage workflow, reflexions agents, "
            "explorateur de logs TXT/JSON eurodates."
        ),
    )

    records = load_artifact_records(REPO_ROOT / "pipeline_runs_v2")
    logs = list_log_files(REPO_ROOT, max_items=1200)

    top = st.columns(3)
    with top[0]:
        render_metric_card(label="Artefacts V2", value=str(len(records)))
    with top[1]:
        render_metric_card(label="Fichiers logs (TXT/JSON)", value=str(len(logs)))
    with top[2]:
        latest_run = records[0]["generated_at_eu"] if records else "N/A"
        render_metric_card(label="Dernier run (EU)", value=latest_run)

    st.markdown("### Navigation")
    st.page_link("pages/1_Workflow_Dashboard.py", label="Dashboard Workflow", icon=":material/dashboard:")
    st.page_link("pages/2_Agents_Reflections.py", label="Reflexions Agents", icon=":material/psychology:")
    st.page_link("pages/3_Fichiers_Logs.py", label="Fichiers Logs TXT/JSON", icon=":material/folder_open:")

    st.caption(
        "Astuce: depuis les pages Agents/Logs, un clic ouvre directement le contenu du fichier "
        "JSON ou TXT dans l'app."
    )


if __name__ == "__main__":
    main()

