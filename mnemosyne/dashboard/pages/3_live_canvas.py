import json
import sqlite3

import pandas as pd
import plotly.io as pio
import streamlit as st

from mnemosyne.config import get_db_path
from mnemosyne.dashboard.chart_store import delete_unpinned, ensure_table, get_charts


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


# ── Sidebar controls ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<p style="color:#8b949e; font-size:0.75rem; text-transform:uppercase; '
        'letter-spacing:0.08em; font-weight:600; margin-bottom:0.5rem;">Canvas</p>',
        unsafe_allow_html=True,
    )
    if st.button("🗑️  Pulisci canvas", use_container_width=True):
        conn = _get_conn()
        deleted = delete_unpinned(conn)
        conn.close()
        st.success(f"Rimossi {deleted} chart.")
        st.rerun()


@st.fragment(run_every=2)
def canvas_panel():
    conn = _get_conn()
    ensure_table(conn)
    charts = get_charts(conn)
    conn.close()

    if not charts:
        st.markdown(
            """
            <div style="text-align:center; padding: 4rem 2rem; color:#8b949e;">
                <div style="font-size: 3rem; margin-bottom: 1rem; opacity: 0.4;">🎨</div>
                <h3 style="color:#8b949e !important; font-weight: 600; margin-bottom: 0.5rem;">
                    Canvas vuoto
                </h3>
                <p style="font-size: 0.9rem; max-width: 400px; margin: 0 auto;">
                    Chiedi a Claude nel terminale di generare un grafico.<br>
                    Apparira qui in tempo reale.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    for chart in charts:
        title = chart["title"]
        pinned = chart.get("pinned")
        if pinned:
            title = f"📌 {title}"

        with st.container(border=True):
            st.markdown(
                f'<p style="font-size:1.05rem; font-weight:700; color:#e6edf3; '
                f'margin:0.2rem 0 0.8rem 0;">{title}</p>',
                unsafe_allow_html=True,
            )

            chart_type = chart["chart_type"]
            data_json = chart["data_json"]

            if chart_type == "plotly_json":
                fig = pio.from_json(data_json)
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(26,31,46,0.5)",
                    font_color="#e6edf3",
                    margin=dict(l=20, r=20, t=30, b=20),
                )
                st.plotly_chart(fig, use_container_width=True)

            elif chart_type == "table":
                df = pd.DataFrame(json.loads(data_json))
                st.dataframe(df, use_container_width=True, hide_index=True)

            elif chart_type == "metric":
                metric_data = json.loads(data_json)
                st.metric(
                    label=chart["title"],
                    value=metric_data.get("value"),
                    delta=metric_data.get("delta"),
                )

            elif chart_type == "markdown":
                st.markdown(data_json)

            else:
                st.warning(f"Tipo chart sconosciuto: {chart_type}")

            # Timestamp
            st.markdown(
                f'<p style="font-size:0.7rem; color:#484f58; text-align:right; margin:0.3rem 0 0 0;">'
                f'{chart.get("created_at", "")}</p>',
                unsafe_allow_html=True,
            )


# ── Run ───────────────────────────────────────────────────────────────
canvas_panel()
