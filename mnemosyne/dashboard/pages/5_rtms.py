import json
import sqlite3

import pandas as pd
import plotly.io as pio
import streamlit as st

from mnemosyne.config import get_db_path


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


@st.fragment(run_every=30)
def rtms_panel():
    conn = _get_conn()

    charts = conn.execute(
        "SELECT * FROM dashboard_charts WHERE title LIKE 'rTMS —%' OR title LIKE 'Query TMS%' "
        "ORDER BY id ASC"
    ).fetchall()

    conn.close()

    if not charts:
        st.info("Nessun dato rTMS. Genera le metriche dal terminale con l'analisi semantica.")
        return

    for chart in charts:
        chart_type = chart["chart_type"]
        data_json = chart["data_json"]
        title = chart["title"]

        st.markdown(
            f'<p style="font-size:1.05rem; font-weight:700; color:#e6edf3; '
            f'margin:1.2rem 0 0.5rem 0;">{title}</p>',
            unsafe_allow_html=True,
        )

        if chart_type == "markdown":
            st.markdown(data_json)

        elif chart_type == "plotly_json":
            fig = pio.from_json(data_json)
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(26,31,46,0.5)",
                font_color="#e6edf3",
            )
            st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "table":
            df = pd.DataFrame(json.loads(data_json))
            st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)


# ── Run ───────────────────────────────────────────────────────────
rtms_panel()
