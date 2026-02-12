from __future__ import annotations

from pathlib import Path

import streamlit as st

from trading_pipeline.ui.file_browser import (
    format_file_button_label,
    list_log_files,
    parse_json_text,
    read_text_file,
)
from trading_pipeline.ui.theme import apply_theme, render_header


REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_selected_file() -> Path | None:
    raw = st.session_state.get("file_browser_selected")
    if not raw:
        return None
    candidate = Path(str(raw)).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    try:
        resolved = candidate.resolve()
    except Exception:
        return None
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except Exception:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def main() -> None:
    apply_theme(page_title="Fichiers Logs", layout="wide")
    render_header(
        title="Fichiers Logs TXT/JSON",
        subtitle=(
            "Clique sur un fichier pour l'ouvrir dans l'app en mode texte brut ou JSON parse."
        ),
    )

    with st.sidebar:
        st.header("Sources")
        include_pipeline = st.toggle("pipeline_runs_v2", value=True)
        include_responses = st.toggle("responses", value=True)
        include_reflex = st.toggle("reflex_trader", value=True)
        max_items = int(st.number_input("Max fichiers", min_value=50, max_value=2000, value=700, step=50))
        view_mode = st.radio("Mode affichage", ["Auto", "Texte", "JSON"], index=0)
        search = st.text_input("Filtre nom/chemin", value="")
        st.button("Rafraichir", width="stretch")

    include_dirs: list[str] = []
    if include_pipeline:
        include_dirs.append("pipeline_runs_v2")
    if include_responses:
        include_dirs.append("responses")
    if include_reflex:
        include_dirs.append("reflex_trader")
    if not include_dirs:
        st.warning("Selectionne au moins un dossier source.")
        st.stop()

    rows = list_log_files(REPO_ROOT, include_dirs=tuple(include_dirs), max_items=max_items)
    if search.strip():
        needle = search.strip().lower()
        rows = [
            row
            for row in rows
            if needle in row["relative_path"].lower() or needle in row["datetime_eu"].lower()
        ]

    left, right = st.columns([1.25, 1.55])
    with left:
        st.subheader("Index eurodate")
        if not rows:
            st.info("Aucun fichier correspondant.")
        else:
            for idx, row in enumerate(rows):
                if st.button(
                    format_file_button_label(row),
                    key=f"log_file_btn_{idx}",
                    width="stretch",
                ):
                    st.session_state["file_browser_selected"] = row["path_str"]
        selected = _resolve_selected_file()
        if selected is None and rows:
            st.session_state["file_browser_selected"] = rows[0]["path_str"]
            selected = _resolve_selected_file()

    with right:
        st.subheader("Contenu")
        selected = _resolve_selected_file()
        if selected is None:
            st.info("Choisis un fichier dans la colonne de gauche.")
            st.stop()

        relative_path = str(selected.relative_to(REPO_ROOT.resolve()))
        st.markdown(f"`{relative_path}`")
        text = read_text_file(selected)

        json_candidate = parse_json_text(text) if selected.suffix.lower() == ".json" else None
        if view_mode == "JSON":
            if json_candidate is None:
                st.warning("Ce fichier n'est pas un JSON parseable.")
                st.code(text, language="text")
            else:
                st.json(json_candidate)
        elif view_mode == "Texte":
            st.code(text, language="text")
        else:
            if json_candidate is not None:
                st.json(json_candidate)
            else:
                st.code(text, language="text")


if __name__ == "__main__":
    main()

