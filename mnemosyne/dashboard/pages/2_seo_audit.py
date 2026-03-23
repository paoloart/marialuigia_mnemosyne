import sqlite3

import pandas as pd
import streamlit as st

from mnemosyne.config import get_db_path
from mnemosyne.seo.audit import (
    embedding_status_report,
    heading_issues,
    posts_missing_meta,
    posts_no_inbound_links,
    posts_no_internal_links,
    posts_thin_content,
)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _badge(count: int, color: str = "#00d4aa") -> str:
    """HTML badge with count."""
    bg = "rgba(0,212,170,0.12)" if count == 0 else "rgba(255,107,107,0.15)"
    fg = color if count == 0 else "#ff6b6b"
    return (
        f'<span style="background:{bg}; color:{fg}; padding:2px 8px; '
        f'border-radius:6px; font-size:0.8rem; font-weight:700;">{count}</span>'
    )


@st.fragment(run_every=30)
def audit_panel():
    conn = _get_conn()

    missing_meta = posts_missing_meta(conn)
    thin = posts_thin_content(conn, st.session_state.get("thin_threshold", 500))
    no_outgoing = posts_no_internal_links(conn)
    no_inbound = posts_no_inbound_links(conn)
    h_issues = heading_issues(conn)
    emb_status = embedding_status_report(conn)

    orphan_total = len(no_outgoing) + len(no_inbound)

    tab_meta, tab_thin, tab_orphan, tab_heading, tab_emb = st.tabs([
        f"Meta mancanti  ({len(missing_meta)})",
        f"Thin content  ({len(thin)})",
        f"Link orfani  ({orphan_total})",
        f"Heading issues  ({len(h_issues)})",
        f"Embeddings  ({emb_status.get('current', 0)}/{emb_status.get('total', 0)})",
    ])

    # ── Tab: Meta mancanti ────────────────────────────────────────────
    with tab_meta:
        if missing_meta:
            st.dataframe(
                pd.DataFrame(missing_meta),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "url": st.column_config.LinkColumn("URL"),
                    "word_count": st.column_config.NumberColumn("Parole", format="%d"),
                },
            )
        else:
            st.success("Tutti i post hanno una meta description.")

    # ── Tab: Thin content ─────────────────────────────────────────────
    with tab_thin:
        threshold = st.slider(
            "Soglia minima parole",
            min_value=300,
            max_value=1000,
            value=500,
            step=50,
            key="thin_threshold",
        )
        thin_data = posts_thin_content(conn, threshold)
        if thin_data:
            df = pd.DataFrame(thin_data)
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "url": st.column_config.LinkColumn("URL"),
                    "word_count": st.column_config.ProgressColumn(
                        "Parole", min_value=0, max_value=threshold, format="%d"
                    ),
                },
            )
        else:
            st.success(f"Nessun post sotto le {threshold} parole.")

    # ── Tab: Link orfani ──────────────────────────────────────────────
    with tab_orphan:
        st.markdown("##### Post senza link interni in uscita")
        if no_outgoing:
            st.dataframe(pd.DataFrame(no_outgoing), use_container_width=True, hide_index=True)
        else:
            st.success("Tutti i post hanno link interni in uscita.")

        st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

        st.markdown("##### Post senza link interni in entrata")
        if no_inbound:
            st.dataframe(pd.DataFrame(no_inbound), use_container_width=True, hide_index=True)
        else:
            st.success("Tutti i post ricevono link interni.")

    # ── Tab: Heading issues ───────────────────────────────────────────
    with tab_heading:
        if h_issues:
            st.dataframe(
                pd.DataFrame(h_issues),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "issue": st.column_config.TextColumn("Problema", width="large"),
                },
            )
        else:
            st.success("Nessun problema di struttura heading rilevato.")

    # ── Tab: Embeddings ───────────────────────────────────────────────
    with tab_emb:
        total = emb_status.get("total", 0)
        current = emb_status.get("current", 0)
        pending = emb_status.get("pending", 0)
        not_gen = emb_status.get("not_generated", 0)

        if total > 0:
            pct = current / total
            st.progress(pct, text=f"{current}/{total} embeddings generati ({pct:.0%})")
        else:
            st.info("Nessun post nel database.")

        st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3, gap="medium")
        c1.metric("Correnti", current)
        c2.metric("In attesa", pending)
        c3.metric("Non generati", not_gen)

    conn.close()


def pillar_panel():
    import html as html_mod
    import plotly.graph_objects as go
    from mnemosyne.seo.pillar_score import score_post

    conn = _get_conn()

    # ── Pillar selection ──────────────────────────────────
    st.markdown("##### Pillar Content")

    pillar_count = conn.execute("SELECT COUNT(*) FROM posts WHERE is_pillar = 1").fetchone()[0]
    total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

    st.caption(f"{pillar_count} pillar su {total_posts} post totali")

    tab_score, tab_manage = st.tabs(["Pillar Score", "Gestisci Pillar"])

    # ── Tab: Gestisci Pillar ──────────────────────────────
    with tab_manage:
        st.markdown("Seleziona quali articoli sono **pillar content** (cornerstone). "
                    "Tipicamente sono gli articoli principali su ogni disturbo/patologia.")

        all_posts = conn.execute(
            "SELECT id, title, is_pillar, word_count FROM posts ORDER BY is_pillar DESC, word_count DESC"
        ).fetchall()

        # Filter
        show_filter = st.radio("Mostra", ["Tutti", "Solo pillar", "Solo non-pillar"],
                              horizontal=True, key="pillar_filter")

        for p in all_posts:
            if show_filter == "Solo pillar" and not p["is_pillar"]:
                continue
            if show_filter == "Solo non-pillar" and p["is_pillar"]:
                continue

            title = html_mod.unescape(p["title"])[:50]
            is_p = bool(p["is_pillar"])

            cols = st.columns([0.07, 0.63, 0.12, 0.18])
            with cols[0]:
                st.markdown(f"`{p['id']}`")
            with cols[1]:
                icon = "**[P]** " if is_p else ""
                st.markdown(f"{icon}{title} ({p['word_count'] or 0}w)")
            with cols[2]:
                st.markdown(f"{'Pillar' if is_p else '—'}")
            with cols[3]:
                label = "Rimuovi" if is_p else "Pillar"
                if st.button(label, key=f"pillar_btn_{p['id']}", use_container_width=True,
                            type="secondary" if is_p else "primary"):
                    new_val = 0 if is_p else 1
                    conn.execute("UPDATE posts SET is_pillar = ? WHERE id = ?", (new_val, p["id"]))
                    conn.commit()
                    st.rerun()

    # ── Tab: Pillar Score ─────────────────────────────────
    with tab_score:
        pillars = conn.execute("SELECT id FROM posts WHERE is_pillar = 1").fetchall()

        if not pillars:
            st.info("Nessun pillar selezionato. Vai nel tab 'Gestisci Pillar' per marcare gli articoli cornerstone.")
            conn.close()
            return

        last_run = conn.execute("SELECT id FROM crawl_runs WHERE status = 'completed' ORDER BY id DESC LIMIT 1").fetchone()
        run_id = last_run["id"] if last_run else None

        scores = [score_post(conn, p["id"], run_id) for p in pillars]
        scores.sort(key=lambda s: s.total_score)

        # Load GSC data for clicks
        try:
            from mnemosyne.dashboard.gsc_client import get_top_pages
            from mnemosyne.config import get_google_credentials_path
            gsc_pages = get_top_pages(get_google_credentials_path(), limit=500)
            gsc_map = {}
            for p in gsc_pages:
                url = p["page"].rstrip("/")
                gsc_map[url] = p
                gsc_map[url + "/"] = p
        except Exception:
            gsc_map = {}

        # Attach clicks to scores
        for s in scores:
            g = gsc_map.get(s.url) or gsc_map.get(s.url.rstrip("/")) or gsc_map.get(s.url.rstrip("/") + "/")
            s.details["clicks_28d"] = g["clicks"] if g else 0
            s.details["impressions_28d"] = g["impressions"] if g else 0

        # Summary
        avg = sum(s.total_score for s in scores) / len(scores)
        total_clicks = sum(s.details.get("clicks_28d", 0) for s in scores)
        c1, c2, c3 = st.columns(3)
        c1.metric("Score medio", f"{avg:.0f}/100")
        c2.metric("Pillar totali", len(scores))
        c3.metric("Click totali (28gg)", f"{total_clicks:,}")

        st.caption("Score 0-100: contenuto 35%, linking 30%, struttura 20%, performance 15%. Peggiori in cima.")

        # Table — compact view
        for s in scores:
            title = html_mod.unescape(s.title)[:40]
            score_color = "#00d4aa" if s.total_score >= 80 else ("#ffd93d" if s.total_score >= 60 else "#ff6b6b")
            clicks = s.details.get("clicks_28d", 0)

            with st.container():
                cols = st.columns([0.05, 0.30, 0.10, 0.10, 0.10, 0.10, 0.10, 0.15])
                with cols[0]:
                    st.markdown(f'<span style="color:{score_color};font-weight:800;font-size:1.2em;">{s.total_score:.0f}</span>', unsafe_allow_html=True)
                with cols[1]:
                    st.markdown(f"**{title}**")
                with cols[2]:
                    st.caption(f"Cont. {s.content_score:.0f}")
                with cols[3]:
                    st.caption(f"Link {s.linking_score:.0f}")
                with cols[4]:
                    st.caption(f"Strutt. {s.structure_score:.0f}")
                with cols[5]:
                    st.caption(f"Perf. {s.performance_score:.0f}")
                with cols[6]:
                    st.caption(f"{s.details.get('word_count', 0)}w")
                with cols[7]:
                    click_color = "#00d4aa" if clicks > 500 else ("#ffd93d" if clicks > 100 else "#8b949e")
                    st.markdown(f'<span style="color:{click_color};font-weight:600;">{clicks:,} click</span>', unsafe_allow_html=True)

    conn.close()


# ── Run ───────────────────────────────────────────────────────────────
audit_panel()
st.divider()
pillar_panel()
