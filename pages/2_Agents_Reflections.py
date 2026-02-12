from __future__ import annotations

from pathlib import Path

import streamlit as st

from trading_pipeline.ui.dashboard_data import AGENT_ORDER, build_agent_histories, load_artifact_records
from trading_pipeline.ui.theme import apply_theme, render_header


REPO_ROOT = Path(__file__).resolve().parents[1]


def _switch_to_logs(*, file_path: str | None = None) -> None:
    if file_path:
        st.session_state["file_browser_selected"] = file_path
    try:
        st.switch_page("pages/3_Fichiers_Logs.py")
    except Exception:
        st.info("Navigation page indisponible dans cette version Streamlit.")


def main() -> None:
    apply_theme(page_title="Reflexions Agents", layout="wide")
    render_header(
        title="Reflexions Agents",
        subtitle=(
            "Un bloc par agent, historique eurodate et ouverture directe du JSON correspondant."
        ),
    )

    artifacts_dir = Path(
        st.text_input(
            "Dossier artefacts V2",
            value=str(REPO_ROOT / "pipeline_runs_v2"),
        )
    ).expanduser()
    records = load_artifact_records(artifacts_dir)
    if not records:
        st.warning(f"Aucun artefact JSON trouve dans: {artifacts_dir}")
        st.stop()

    histories = build_agent_histories(records, max_rows_per_agent=300)

    for agent_name in AGENT_ORDER:
        agent_rows = histories.get(agent_name, [])
        latest = agent_rows[0] if agent_rows else None
        latest_date = latest["date_eu"] if latest else "N/A"
        latest_summary = latest["reflection"] if latest else "Aucune reflexion"

        with st.expander(f"{agent_name} | {latest_date} | {latest_summary}", expanded=False):
            if not agent_rows:
                st.info("Aucune donnee pour cet agent.")
                continue

            for idx, row in enumerate(agent_rows[:120]):
                row_label = (
                    f"{row['date_eu']} | {row['run_file']} | {row['reflection']}"
                )
                col_a, col_b = st.columns([1.7, 1.0])
                with col_a:
                    if st.button(
                        f"Ouvrir JSON run #{idx + 1}",
                        key=f"open_json_{agent_name}_{idx}",
                        width="stretch",
                    ):
                        _switch_to_logs(file_path=row.get("artifact_path"))
                with col_b:
                    if st.button(
                        f"Voir section #{idx + 1}",
                        key=f"show_section_{agent_name}_{idx}",
                        width="stretch",
                    ):
                        st.session_state[f"selected_section_{agent_name}"] = idx
                st.caption(row_label)

            selected_idx = st.session_state.get(f"selected_section_{agent_name}", 0)
            if isinstance(selected_idx, int) and 0 <= selected_idx < len(agent_rows):
                st.markdown("#### Section JSON selectionnee")
                st.json(agent_rows[selected_idx]["raw_section"])


if __name__ == "__main__":
    main()

