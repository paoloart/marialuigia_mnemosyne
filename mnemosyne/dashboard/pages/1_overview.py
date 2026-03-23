import os
import sqlite3

import pandas as pd
import streamlit as st

from mnemosyne.config import get_db_path
from mnemosyne.dashboard import ga4_client, gsc_client
from mnemosyne.seo.audit import embedding_status_report, posts_missing_meta

# ── Credentials path ─────────────────────────────────────────────────
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
creds_path = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.path.join(_project_root, "ospedalemarialuigia-1231-2501577589f1.json"),
)


# ── Cached API calls ─────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _ga4_overview() -> dict:
    return ga4_client.get_overview(creds_path)


@st.cache_data(ttl=300)
def _ga4_top_pages() -> list[dict]:
    return ga4_client.get_top_pages(creds_path)


@st.cache_data(ttl=300)
def _gsc_overview() -> dict:
    return gsc_client.get_overview(creds_path)


@st.cache_data(ttl=300)
def _gsc_top_queries() -> list[dict]:
    return gsc_client.get_top_queries(creds_path)


# ── DB helpers ────────────────────────────────────────────────────────
def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _db_summary() -> dict:
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    emb = embedding_status_report(conn)
    missing_meta = len(posts_missing_meta(conn))
    conn.close()
    return {
        "total_posts": total,
        "embeddings": emb,
        "missing_meta": missing_meta,
    }


# ── Section header helper ────────────────────────────────────────────
def _section(icon: str, title: str):
    st.markdown(
        f'<h3 style="margin:0 0 0.8rem 0;">'
        f'<span style="color:#00d4aa; margin-right:0.5rem;">{icon}</span>{title}</h3>',
        unsafe_allow_html=True,
    )


# ── Auto-refresh fragment ────────────────────────────────────────────
@st.fragment(run_every=60)
def metrics_panel():
    # ── GA4 metrics ───────────────────────────────────────────────────
    _section("", "Google Analytics 4")
    try:
        ga4 = _ga4_overview()
        if ga4:
            c1, c2, c3 = st.columns(3, gap="medium")
            c1.metric("Utenti", f"{ga4['users']['value']:,}", f"{ga4['users']['delta']:+.1f}%")
            c2.metric("Sessioni", f"{ga4['sessions']['value']:,}", f"{ga4['sessions']['delta']:+.1f}%")
            c3.metric("Pageviews", f"{ga4['pageviews']['value']:,}", f"{ga4['pageviews']['delta']:+.1f}%")
        else:
            st.info("Dati GA4 non disponibili. Configura `GOOGLE_APPLICATION_CREDENTIALS`.")
    except Exception:
        st.info("Credenziali GA4 non configurate — collega un service account per vedere i dati.")

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── GSC metrics ───────────────────────────────────────────────────
    _section("", "Google Search Console")
    try:
        gsc = _gsc_overview()
        if gsc:
            c1, c2, c3, c4 = st.columns(4, gap="medium")
            _d = lambda v: f"{v:+.1f}%" if v is not None else None
            c1.metric("Click", f"{gsc['clicks']['value']:,.0f}", _d(gsc["clicks"]["delta"]))
            c2.metric("Impressioni", f"{gsc['impressions']['value']:,.0f}", _d(gsc["impressions"]["delta"]))
            ctr_val = gsc["ctr"]["value"]
            c3.metric("CTR", f"{ctr_val:.2%}" if isinstance(ctr_val, float) else ctr_val, _d(gsc["ctr"]["delta"]))
            pos_val = gsc["position"]["value"]
            c4.metric("Posizione", f"{pos_val:.1f}" if isinstance(pos_val, float) else pos_val, _d(gsc["position"]["delta"]), delta_color="inverse")
        else:
            st.info("Dati GSC non disponibili. Configura `GOOGLE_APPLICATION_CREDENTIALS`.")
    except Exception:
        st.info("Credenziali GSC non configurate — collega un service account per vedere i dati.")

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── DB summary ────────────────────────────────────────────────────
    _section("", "Database Locale")
    summary = _db_summary()
    c1, c2, c3 = st.columns(3, gap="medium")
    c1.metric("Post totali", f"{summary['total_posts']:,}")

    emb = summary["embeddings"]
    current = emb.get("current", 0)
    total = emb.get("total", 0)
    c2.metric("Embeddings", f"{current}/{total}")

    c3.metric("Meta mancanti", summary["missing_meta"])

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ── Expandable tables ─────────────────────────────────────────────
    with st.expander("Top pagine GA4", icon="📈"):
        try:
            pages = _ga4_top_pages()
            if pages:
                df = pd.DataFrame(pages)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Nessun dato disponibile.")
        except Exception:
            st.info("Dati non disponibili.")

    with st.expander("Top query GSC", icon="🔎"):
        try:
            queries = _gsc_top_queries()
            if queries:
                df = pd.DataFrame(queries)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Nessun dato disponibile.")
        except Exception:
            st.info("Dati non disponibili.")


# ── Run ───────────────────────────────────────────────────────────────
metrics_panel()
