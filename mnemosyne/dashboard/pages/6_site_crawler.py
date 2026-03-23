"""Pagina dashboard: Site Crawler SEO."""

import io
import json
import sqlite3

import pandas as pd
import streamlit as st

from mnemosyne.config import get_db_path


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _severity_badge(severity: str) -> str:
    colors = {"critical": "#ff6b6b", "warning": "#ffd93d", "info": "#6bcbff"}
    c = colors.get(severity, "#8b949e")
    return f'<span style="color:{c}; font-weight:700;">{severity.upper()}</span>'


# ── Main ──────────────────────────────────────────────────


def page():
    conn = _get_conn()

    # Check for running crawl — show progress bar
    _show_crawl_progress()

    # Sidebar: selettore run
    runs = conn.execute(
        "SELECT id, started_at, total_urls, crawled_urls, status FROM crawl_runs ORDER BY id DESC LIMIT 20"
    ).fetchall()

    if not runs:
        st.info("Nessun crawl trovato. Esegui `python -m mnemosyne crawl <sitemap>`.")
        conn.close()
        return

    with st.sidebar:
        run_options = {r["id"]: f"#{r['id']} — {r['started_at'][:16]} ({r['crawled_urls']} pagine)" for r in runs}
        selected_run_id = st.selectbox("Crawl run", options=list(run_options.keys()),
                                       format_func=lambda x: run_options[x])

    run = conn.execute("SELECT * FROM crawl_runs WHERE id = ?", (selected_run_id,)).fetchone()

    # Header
    st.markdown(f"### Crawl #{run['id']} — {run['started_at'][:16]}")
    st.caption(f"Sitemap: `{run['sitemap_url']}` | Status: **{run['status']}** | "
               f"Durata: {_duration(run['started_at'], run['finished_at'])}")

    # Metric cards — with delta if previous run exists
    critical = _count_issues(conn, selected_run_id, "critical")
    warning = _count_issues(conn, selected_run_id, "warning")
    info_count = _count_issues(conn, selected_run_id, "info")
    health = _health_score(conn, selected_run_id)

    prev_run = conn.execute(
        "SELECT id FROM crawl_runs WHERE id < ? AND status = 'completed' ORDER BY id DESC LIMIT 1",
        (selected_run_id,),
    ).fetchone()

    if prev_run:
        prev_id = prev_run["id"]
        d_crit = critical - _count_issues(conn, prev_id, "critical")
        d_warn = warning - _count_issues(conn, prev_id, "warning")
        d_info = info_count - _count_issues(conn, prev_id, "info")
        d_health = health - _health_score(conn, prev_id)
    else:
        d_crit = d_warn = d_info = d_health = None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Health Score", f"{health:.0f}%",
              delta=f"{d_health:+.1f}pp" if d_health is not None else None,
              delta_color="normal")
    c2.metric("Critical", critical,
              delta=d_crit if d_crit is not None else None,
              delta_color="inverse")
    c3.metric("Warning", warning,
              delta=d_warn if d_warn is not None else None,
              delta_color="inverse")
    c4.metric("Info", info_count,
              delta=d_info if d_info is not None else None,
              delta_color="off")

    st.divider()

    # Tabs
    tab_overview, tab_http, tab_seo, tab_images, tab_links, tab_content, tab_diff = st.tabs([
        "Panoramica", "Errori HTTP", "SEO On-Page", "Immagini", "Link", "Contenuto", "Confronto"
    ])

    # ── Panoramica ─────────────────────────────────────────
    with tab_overview:
        _tab_overview(conn, selected_run_id)

    # ── Errori HTTP ────────────────────────────────────────
    with tab_http:
        _tab_http(conn, selected_run_id)

    # ── SEO On-Page ────────────────────────────────────────
    with tab_seo:
        _tab_seo(conn, selected_run_id)

    # ── Immagini ───────────────────────────────────────────
    with tab_images:
        _tab_images(conn, selected_run_id)

    # ── Link ───────────────────────────────────────────────
    with tab_links:
        _tab_links(conn, selected_run_id)

    # ── Contenuto ──────────────────────────────────────────
    with tab_content:
        _tab_content(conn, selected_run_id)

    # ── Confronto ─────────────────────────────────────────
    with tab_diff:
        _tab_diff(conn, selected_run_id, runs)

    # Sidebar: actions
    with st.sidebar:
        st.divider()
        _sidebar_launch_crawl()
        if st.button("Export Issue CSV"):
            csv = _export_issues_csv(conn, selected_run_id)
            st.download_button("Download CSV", csv, f"crawl_{selected_run_id}_issues.csv", "text/csv")

    conn.close()


# ── Tab: Panoramica ───────────────────────────────────────


def _tab_overview(conn, run_id):
    import plotly.graph_objects as go

    col1, col2 = st.columns(2)

    # Severità pie
    with col1:
        counts = {}
        for sev in ("critical", "warning", "info"):
            counts[sev] = _count_issues(conn, run_id, sev)

        if sum(counts.values()) > 0:
            colors = {"critical": "#ff6b6b", "warning": "#ffd93d", "info": "#6bcbff"}
            fig = go.Figure(go.Pie(
                labels=[s.capitalize() for s in counts],
                values=list(counts.values()),
                marker=dict(colors=[colors[s] for s in counts]),
                hole=0.4,
                textinfo="value+percent",
            ))
            fig.update_layout(
                title="Distribuzione Severità", height=350,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e6edf3"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.success("Nessun issue trovato!")

    # Issue per categoria
    with col2:
        rows = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM crawl_issues WHERE run_id = ? GROUP BY category ORDER BY cnt DESC",
            (run_id,),
        ).fetchall()
        if rows:
            cat_colors = {
                "http": "#ff6b6b", "onpage": "#ffa94d", "content": "#ffd93d",
                "images": "#a9e34b", "links": "#38d9a9", "resources": "#6bcbff",
            }
            fig = go.Figure(go.Bar(
                x=[r["cnt"] for r in rows],
                y=[r["category"] for r in rows],
                orientation="h",
                marker=dict(color=[cat_colors.get(r["category"], "#8b949e") for r in rows]),
                text=[r["cnt"] for r in rows],
                textposition="auto",
            ))
            fig.update_layout(
                title="Issue per Categoria", height=350,
                yaxis=dict(autorange="reversed"),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e6edf3"),
            )
            st.plotly_chart(fig, use_container_width=True)

    # TTFB scatter
    ttfb_rows = conn.execute(
        "SELECT url, ttfb_ms FROM crawl_pages WHERE run_id = ? AND ttfb_ms IS NOT NULL ORDER BY ttfb_ms DESC LIMIT 100",
        (run_id,),
    ).fetchall()
    if ttfb_rows:
        df = pd.DataFrame([dict(r) for r in ttfb_rows])
        df["slug"] = df["url"].apply(lambda u: u.rstrip("/").split("/")[-1][:40])
        colors = df["ttfb_ms"].apply(lambda t: "#ff6b6b" if t > 3000 else ("#ffd93d" if t > 1000 else "#00d4aa"))

        fig = go.Figure(go.Bar(
            x=df["slug"], y=df["ttfb_ms"],
            marker=dict(color=colors),
            text=df["ttfb_ms"],
            textposition="outside",
        ))
        fig.update_layout(
            title="TTFB per Pagina (top 100 più lente)", height=400,
            xaxis=dict(tickangle=-45, tickfont=dict(size=9)),
            yaxis=dict(title="ms"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
        )
        fig.add_hline(y=1000, line_dash="dot", line_color="#ffd93d", opacity=0.5)
        fig.add_hline(y=3000, line_dash="dot", line_color="#ff6b6b", opacity=0.5)
        st.plotly_chart(fig, use_container_width=True)


# ── Tab: Errori HTTP ──────────────────────────────────────


def _tab_http(conn, run_id):
    rows = conn.execute(
        """SELECT url, status_code, redirect_url, ttfb_ms
           FROM crawl_pages WHERE run_id = ? AND status_code != 200
           ORDER BY status_code DESC""",
        (run_id,),
    ).fetchall()

    if not rows:
        st.success("Tutte le pagine rispondono 200!")
        return

    status_filter = st.multiselect(
        "Filtra per status code",
        sorted(set(r["status_code"] for r in rows)),
        default=sorted(set(r["status_code"] for r in rows)),
    )

    filtered = [r for r in rows if r["status_code"] in status_filter]
    df = pd.DataFrame([dict(r) for r in filtered])
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={"url": st.column_config.LinkColumn("URL")})


# ── Tab: SEO On-Page ─────────────────────────────────────


def _tab_seo(conn, run_id):
    check_types = conn.execute(
        "SELECT DISTINCT check_name FROM crawl_issues WHERE run_id = ? AND category = 'onpage' ORDER BY check_name",
        (run_id,),
    ).fetchall()

    if not check_types:
        st.success("Nessun issue SEO on-page trovato!")
        return

    all_checks = [r[0] for r in check_types]
    selected = st.multiselect("Filtra per tipo di check", all_checks, default=all_checks)

    if selected:
        placeholders = ",".join(["?"] * len(selected))
        rows = conn.execute(
            f"""SELECT severity, check_name, message, url
                FROM crawl_issues
                WHERE run_id = ? AND category = 'onpage' AND check_name IN ({placeholders})
                ORDER BY severity, check_name""",
            (run_id, *selected),
        ).fetchall()
        df = pd.DataFrame([dict(r) for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={"url": st.column_config.LinkColumn("URL")})


# ── Tab: Immagini ─────────────────────────────────────────


def _tab_images(conn, run_id):
    stats = conn.execute(
        """SELECT
            COUNT(*) as totale,
            SUM(is_missing_alt) as senza_alt,
            SUM(is_broken) as rotte,
            SUM(is_oversized) as pesanti
           FROM crawl_images WHERE run_id = ?""",
        (run_id,),
    ).fetchone()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Totale", stats["totale"] or 0)
    c2.metric("Senza alt", stats["senza_alt"] or 0)
    c3.metric("Rotte", stats["rotte"] or 0)
    c4.metric("Pesanti (>200KB)", stats["pesanti"] or 0)

    sub_broken, sub_noalt, sub_heavy = st.tabs(["Rotte", "Senza alt", "Pesanti"])

    with sub_broken:
        rows = conn.execute(
            """SELECT ci.src, ci.status_code, cp.url as pagina
               FROM crawl_images ci JOIN crawl_pages cp ON ci.page_id = cp.id
               WHERE ci.run_id = ? AND ci.is_broken = 1""",
            (run_id,),
        ).fetchall()
        if rows:
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
        else:
            st.success("Nessuna immagine rotta.")

    with sub_noalt:
        rows = conn.execute(
            """SELECT ci.src, cp.url as pagina
               FROM crawl_images ci JOIN crawl_pages cp ON ci.page_id = cp.id
               WHERE ci.run_id = ? AND ci.is_missing_alt = 1 LIMIT 100""",
            (run_id,),
        ).fetchall()
        if rows:
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
        else:
            st.success("Tutte le immagini hanno alt text.")

    with sub_heavy:
        rows = conn.execute(
            """SELECT ci.src, ci.content_length, ci.content_type, cp.url as pagina
               FROM crawl_images ci JOIN crawl_pages cp ON ci.page_id = cp.id
               WHERE ci.run_id = ? AND ci.is_oversized = 1
               ORDER BY ci.content_length DESC""",
            (run_id,),
        ).fetchall()
        if rows:
            df = pd.DataFrame([dict(r) for r in rows])
            df["size_kb"] = df["content_length"].apply(lambda x: f"{x // 1024}KB" if x else "?")
            st.dataframe(df[["src", "size_kb", "content_type", "pagina"]],
                        use_container_width=True, hide_index=True)
        else:
            st.success("Nessuna immagine pesante.")


# ── Tab: Link ─────────────────────────────────────────────


def _tab_links(conn, run_id):
    # Stats header
    total_ext = conn.execute(
        "SELECT COUNT(DISTINCT target_url) FROM crawl_links WHERE run_id = ? AND is_internal = 0", (run_id,)
    ).fetchone()[0]
    checked_ext = conn.execute(
        "SELECT COUNT(DISTINCT target_url) FROM crawl_links WHERE run_id = ? AND is_internal = 0 AND status_code IS NOT NULL", (run_id,)
    ).fetchone()[0]
    broken_ext = conn.execute(
        "SELECT COUNT(DISTINCT target_url) FROM crawl_links WHERE run_id = ? AND is_internal = 0 AND is_broken = 1", (run_id,)
    ).fetchone()[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Link esterni unici", total_ext)
    c2.metric("Verificati", checked_ext)
    c3.metric("Rotti", broken_ext)

    # Check button
    if checked_ext < total_ext:
        remaining = total_ext - checked_ext
        if st.button(f"Verifica {remaining} link esterni", type="primary", use_container_width=True):
            _run_external_check(run_id)
            st.rerun()

    sub_int_broken, sub_ext_broken, sub_redirect, sub_anchor = st.tabs([
        "Interni rotti", "Esterni rotti", "Redirect interni", "Anchor vuoti"
    ])

    with sub_int_broken:
        rows = conn.execute(
            """SELECT cl.target_url, cl.anchor_text, cl.status_code, cp.url as pagina_sorgente
               FROM crawl_links cl JOIN crawl_pages cp ON cl.source_page_id = cp.id
               WHERE cl.run_id = ? AND cl.is_internal = 1 AND cl.is_broken = 1""",
            (run_id,),
        ).fetchall()
        if rows:
            st.error(f"{len(rows)} link interni rotti")
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
        else:
            st.success("Nessun link interno rotto.")

    with sub_ext_broken:
        rows = conn.execute(
            """SELECT cl.target_url, cl.status_code, cl.anchor_text, cp.url as pagina_sorgente, cp.title as titolo_pagina
               FROM crawl_links cl JOIN crawl_pages cp ON cl.source_page_id = cp.id
               WHERE cl.run_id = ? AND cl.is_internal = 0 AND cl.is_broken = 1
               ORDER BY cl.status_code, cl.target_url""",
            (run_id,),
        ).fetchall()
        if rows:
            st.error(f"{len(rows)} link esterni rotti")

            # Filter by status code
            status_codes = sorted(set(r["status_code"] for r in rows))
            selected_codes = st.multiselect("Filtra per status", status_codes, default=status_codes, key="ext_broken_filter")
            filtered = [r for r in rows if r["status_code"] in selected_codes]

            df = pd.DataFrame([dict(r) for r in filtered])
            st.dataframe(df, use_container_width=True, hide_index=True,
                        column_config={
                            "target_url": st.column_config.LinkColumn("Link rotto"),
                            "pagina_sorgente": st.column_config.LinkColumn("Pagina"),
                        })
        elif checked_ext > 0:
            st.success("Nessun link esterno rotto!")
        else:
            st.info("Clicca 'Verifica link esterni' per controllare.")

    with sub_redirect:
        rows = conn.execute(
            """SELECT cl.target_url, cl.anchor_text, cl.status_code, cp.url as pagina_sorgente
               FROM crawl_links cl JOIN crawl_pages cp ON cl.source_page_id = cp.id
               WHERE cl.run_id = ? AND cl.is_internal = 1 AND cl.is_redirect = 1""",
            (run_id,),
        ).fetchall()
        if rows:
            st.warning(f"{len(rows)} link interni che puntano a redirect")
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
        else:
            st.success("Nessun link interno punta a redirect.")

    with sub_anchor:
        rows = conn.execute(
            """SELECT cl.target_url, cp.url as pagina_sorgente
               FROM crawl_links cl JOIN crawl_pages cp ON cl.source_page_id = cp.id
               WHERE cl.run_id = ? AND (cl.anchor_text IS NULL OR cl.anchor_text = '')
               LIMIT 100""",
            (run_id,),
        ).fetchall()
        if rows:
            st.warning(f"{len(rows)} link con anchor text vuoto")
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
        else:
            st.success("Tutti i link hanno anchor text.")


def _run_external_check(run_id):
    """Run external link check with progress in Streamlit."""
    from mnemosyne.crawler.check_external import check_external_links
    conn = _get_conn()

    progress = st.progress(0, text="Verificando link esterni...")

    def on_progress(done, total):
        progress.progress(done / total, text=f"Verificando link esterni... {done}/{total}")

    result = check_external_links(conn, run_id, max_workers=10, callback=on_progress)
    conn.close()

    progress.progress(1.0, text=f"Completato! OK: {result['ok']}, Rotti: {result['broken']}, Errori: {result['errors']}")


# ── Tab: Contenuto ────────────────────────────────────────


def _tab_content(conn, run_id):
    # Thin content
    st.markdown("##### Thin Content (<300 parole)")
    rows = conn.execute(
        "SELECT url, word_count, title FROM crawl_pages WHERE run_id = ? AND word_count > 0 AND word_count < 300 ORDER BY word_count",
        (run_id,),
    ).fetchall()
    if rows:
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True,
                     column_config={"url": st.column_config.LinkColumn("URL")})
    else:
        st.success("Nessuna pagina con meno di 300 parole.")

    st.divider()

    # Duplicati
    st.markdown("##### Duplicati Title / Meta Description")
    dupes = conn.execute(
        "SELECT field, value, count, urls FROM crawl_duplicates WHERE run_id = ? ORDER BY count DESC",
        (run_id,),
    ).fetchall()
    if dupes:
        for d in dupes:
            urls = json.loads(d["urls"])
            with st.expander(f"**{d['field']}**: \"{d['value'][:80]}\" ({d['count']} pagine)"):
                for u in urls:
                    st.markdown(f"- [{u}]({u})")
    else:
        st.success("Nessun duplicato trovato.")

    st.divider()

    # Word count distribution
    st.markdown("##### Distribuzione Word Count")
    wc_rows = conn.execute(
        "SELECT word_count FROM crawl_pages WHERE run_id = ? AND word_count > 0", (run_id,)
    ).fetchall()
    if wc_rows:
        import plotly.express as px
        df = pd.DataFrame([{"word_count": r["word_count"]} for r in wc_rows])
        fig = px.histogram(df, x="word_count", nbins=30, color_discrete_sequence=["#00d4aa"])
        fig.update_layout(
            xaxis_title="Parole", yaxis_title="Pagine",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"), height=350,
        )
        fig.add_vline(x=300, line_dash="dot", line_color="#ff6b6b",
                      annotation_text="Thin (300)", annotation_font_color="#ff6b6b")
        st.plotly_chart(fig, use_container_width=True)


# ── Sidebar: lancio crawl ─────────────────────────────────


def _sidebar_launch_crawl():
    """Button to launch a new crawl from the dashboard."""
    conn = _get_conn()
    running = conn.execute("SELECT id FROM crawl_runs WHERE status = 'running' LIMIT 1").fetchone()
    conn.close()

    if running:
        st.warning(f"Crawl #{running['id']} in corso...")
        return

    if st.button("Nuovo Crawl"):
        import subprocess
        import sys
        # Launch crawl in background subprocess
        subprocess.Popen(
            [sys.executable, "-m", "mnemosyne", "crawl"],
            cwd="/Users/paoloartoni/tinke/progetti_AI/Maria_Luigia_Mnemosyne",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        st.success("Crawl lanciato! La progress bar apparirà tra pochi secondi.")
        st.rerun()


# ── Progress bar live ─────────────────────────────────────


@st.fragment(run_every=3)
def _show_crawl_progress(_conn_unused=None):
    """Show a progress bar if a crawl is currently running."""
    conn = _get_conn()
    running = conn.execute(
        "SELECT id, total_urls, crawled_urls, started_at FROM crawl_runs WHERE status = 'running' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not running:
        return

    total = running["total_urls"] or 1
    done = running["crawled_urls"] or 0
    pct = min(done / total, 1.0)

    st.info(f"Crawl #{running['id']} in corso... ({done}/{total} pagine)")
    st.progress(pct, text=f"{done}/{total} pagine crawlate ({pct:.0%})")


# ── Tab: Confronto ────────────────────────────────────────


def _tab_diff(conn, current_run_id, runs):
    """Compare current run with a previous one."""
    completed_runs = [r for r in runs if r["status"] == "completed" and r["id"] != current_run_id]

    if not completed_runs:
        st.info("Serve almeno un altro crawl completato per il confronto.")
        return

    compare_options = {r["id"]: f"#{r['id']} — {r['started_at'][:16]} ({r['crawled_urls']} pg)" for r in completed_runs}
    compare_id = st.selectbox("Confronta con", options=list(compare_options.keys()),
                              format_func=lambda x: compare_options[x],
                              key="diff_compare_run")

    from mnemosyne.crawler.diff import compare_runs
    diff = compare_runs(conn, compare_id, current_run_id)

    # Health score delta
    delta = diff.score_new - diff.score_old
    col1, col2, col3 = st.columns(3)
    col1.metric("Health (vecchio)", f"{diff.score_old:.1f}%")
    col2.metric("Health (nuovo)", f"{diff.score_new:.1f}%",
                delta=f"{delta:+.1f}pp", delta_color="normal")
    col3.metric("Issue nuovi / risolti", f"+{len(diff.new_issues)} / -{len(diff.resolved_issues)}")

    # Status changes
    if diff.status_changes:
        st.markdown(f"##### Status code cambiati ({len(diff.status_changes)})")
        st.dataframe(
            pd.DataFrame(diff.status_changes),
            use_container_width=True, hide_index=True,
            column_config={"url": st.column_config.LinkColumn("URL")},
        )

    # New / removed pages
    col_new, col_rem = st.columns(2)
    with col_new:
        if diff.new_pages:
            st.markdown(f"##### Nuove pagine ({len(diff.new_pages)})")
            for url in diff.new_pages[:20]:
                st.markdown(f"- `{url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]}`")
        else:
            st.caption("Nessuna nuova pagina")

    with col_rem:
        if diff.removed_pages:
            st.markdown(f"##### Pagine rimosse ({len(diff.removed_pages)})")
            for url in diff.removed_pages[:20]:
                st.markdown(f"- `{url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]}`")
        else:
            st.caption("Nessuna pagina rimossa")

    # New issues
    if diff.new_issues:
        with st.expander(f"Nuovi issue ({len(diff.new_issues)})", expanded=True):
            df = pd.DataFrame(diff.new_issues)
            st.dataframe(df, use_container_width=True, hide_index=True)

    # Resolved issues
    if diff.resolved_issues:
        with st.expander(f"Issue risolti ({len(diff.resolved_issues)})"):
            df = pd.DataFrame(diff.resolved_issues)
            st.dataframe(df, use_container_width=True, hide_index=True)

    if not diff.new_issues and not diff.resolved_issues and not diff.status_changes:
        st.success("Nessun cambiamento significativo tra i due crawl.")


# ── Helpers ───────────────────────────────────────────────


def _count_issues(conn, run_id, severity):
    return conn.execute(
        "SELECT COUNT(*) FROM crawl_issues WHERE run_id = ? AND severity = ?",
        (run_id, severity),
    ).fetchone()[0]


def _health_score(conn, run_id) -> float:
    total = conn.execute("SELECT COUNT(*) FROM crawl_pages WHERE run_id = ?", (run_id,)).fetchone()[0]
    if total == 0:
        return 100.0
    with_critical = conn.execute(
        "SELECT COUNT(DISTINCT page_id) FROM crawl_issues WHERE run_id = ? AND severity = 'critical'",
        (run_id,),
    ).fetchone()[0]
    return ((total - with_critical) / total) * 100


def _duration(start: str | None, end: str | None) -> str:
    if not start or not end:
        return "—"
    try:
        from datetime import datetime
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
        delta = e - s
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60}s"
    except (ValueError, TypeError):
        return "—"


def _export_issues_csv(conn, run_id) -> str:
    rows = conn.execute(
        "SELECT severity, category, check_name, message, url FROM crawl_issues WHERE run_id = ? ORDER BY severity, category",
        (run_id,),
    ).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    return df.to_csv(index=False)


# ── Run ───────────────────────────────────────────────────
# Auto-refresh every 5s to pick up new crawl data
st.empty()
page()
st_autorefresh_interval = 5000  # ms

# Inject auto-refresh via HTML when a crawl is running
_conn_check = _get_conn()
_is_running = _conn_check.execute("SELECT 1 FROM crawl_runs WHERE status = 'running' LIMIT 1").fetchone()
_conn_check.close()
if _is_running:
    st.markdown(
        f'<meta http-equiv="refresh" content="5">',
        unsafe_allow_html=True,
    )
