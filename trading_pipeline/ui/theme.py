from __future__ import annotations

import streamlit as st


_THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap');

:root {
  --cream: #fff9ec;
  --mint: #effaf4;
  --ink: #18212f;
  --teal: #0b8c75;
  --amber: #d98d2f;
  --card: rgba(255, 255, 255, 0.86);
}

.stApp {
  background:
    radial-gradient(circle at 10% 0%, #ffe7ba 0%, transparent 32%),
    radial-gradient(circle at 85% 0%, #cdf5e8 0%, transparent 36%),
    linear-gradient(180deg, var(--cream), var(--mint));
}

html, body, [class*="css"] {
  font-family: "Space Grotesk", sans-serif;
  color: var(--ink);
}

.dash-title {
  margin: 0;
  font-size: 2.05rem;
  letter-spacing: 0.03em;
}

.dash-sub {
  margin: 0.2rem 0 1.2rem;
  color: #3b4a60;
}

.metric-card {
  background: var(--card);
  border: 1px solid rgba(14, 34, 57, 0.08);
  border-left: 6px solid var(--teal);
  border-radius: 14px;
  padding: 0.8rem 1rem;
  box-shadow: 0 8px 24px rgba(20, 46, 72, 0.06);
}

.metric-label {
  font-size: 0.84rem;
  color: #43536a;
  margin-bottom: 0.18rem;
}

.metric-value {
  font-size: 1.25rem;
  font-weight: 700;
  line-height: 1.2;
  color: #13233d;
}

.status-line {
  font-size: 0.92rem;
  color: #314661;
  margin-top: 0.4rem;
}

code {
  font-family: "IBM Plex Mono", monospace;
}
</style>
"""


def apply_theme(*, page_title: str, layout: str = "wide") -> None:
    st.set_page_config(page_title=page_title, layout=layout)
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def render_header(*, title: str, subtitle: str) -> None:
    st.markdown(f"<h1 class='dash-title'>{title}</h1>", unsafe_allow_html=True)
    st.markdown(f"<p class='dash-sub'>{subtitle}</p>", unsafe_allow_html=True)


def render_metric_card(*, label: str, value: str) -> None:
    st.markdown(
        (
            "<div class='metric-card'>"
            f"<div class='metric-label'>{label}</div>"
            f"<div class='metric-value'>{value}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

