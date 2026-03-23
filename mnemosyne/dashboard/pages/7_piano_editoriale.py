"""Pagina dashboard: Piano Editoriale & Suggerimenti — redesign con 3 tab + card uniforme."""

import html as html_mod
import json
import math
import sqlite3
from datetime import datetime, timezone

import streamlit as st

from mnemosyne.config import get_db_path
from mnemosyne.db.schema import create_tables

PAGE_SIZE = 20


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    return conn


# ── Plan item helpers ─────────────────────────────────────


def _is_done(conn, key: str) -> bool:
    r = conn.execute("SELECT done FROM plan_items WHERE item_key = ?", (key,)).fetchone()
    return bool(r and r["done"])


def _toggle_done(key: str):
    conn = _get_conn()
    r = conn.execute("SELECT done FROM plan_items WHERE item_key = ?", (key,)).fetchone()
    now = datetime.now(timezone.utc).isoformat()
    if r:
        new_val = 0 if r["done"] else 1
        conn.execute("UPDATE plan_items SET done = ?, done_at = ? WHERE item_key = ?",
                     (new_val, now if new_val else None, key))
    else:
        conn.execute("INSERT INTO plan_items (item_key, done, done_at) VALUES (?, 1, ?)", (key, now))
    conn.commit()
    conn.close()


def _dismiss_suggestion(suggestion_id: int):
    conn = _get_conn()
    conn.execute(
        "UPDATE suggestions SET status = 'dismissed', dismissed_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), suggestion_id),
    )
    conn.commit()
    conn.close()


# ── Uniform card component ────────────────────────────────


def _action_card(
    title: str,
    subtitle: str = "",
    badge: str = "",
    url: str | None = None,
    done: bool = False,
    btn_key: str = "",
    on_toggle: bool = False,
    on_dismiss: bool = False,
) -> bool:
    """Render a uniform action card. Returns True if button was clicked."""
    clicked = False
    with st.container(border=True):
        cols = st.columns([0.55, 0.12, 0.13, 0.20])
        with cols[0]:
            display = f"~~{title}~~" if done else f"**{title}**"
            st.markdown(display)
            if subtitle:
                st.caption(subtitle)
        with cols[1]:
            if badge:
                color = "#ff6b6b" if badge == "alta" else ("#ffd93d" if badge == "media" else "#8b949e")
                st.markdown(f'<span style="color:{color};font-size:0.8em;">{badge}</span>', unsafe_allow_html=True)
        with cols[2]:
            if url:
                st.link_button("Apri", url, use_container_width=True)
        with cols[3]:
            if on_toggle:
                label = "Fatto" if done else "Da fare"
                if st.button(label, key=btn_key, type="secondary" if done else "primary", use_container_width=True):
                    clicked = True
            elif on_dismiss:
                if st.button("Dismissa", key=btn_key, use_container_width=True):
                    clicked = True
    return clicked


# ── Pagination helper ─────────────────────────────────────


def _paginate(items: list, key: str) -> list:
    """Paginate a list and show page selector. Returns visible items."""
    if len(items) <= PAGE_SIZE:
        return items
    total_pages = math.ceil(len(items) / PAGE_SIZE)
    page = st.number_input("Pagina", min_value=1, max_value=total_pages, value=1, key=f"page_{key}")
    start = (page - 1) * PAGE_SIZE
    st.caption(f"Mostrando {start+1}–{min(start+PAGE_SIZE, len(items))} di {len(items)}")
    return items[start:start + PAGE_SIZE]


# ══════════════════════════════════════════════════════════
# MAIN PAGE
# ══════════════════════════════════════════════════════════


def page():
    st.markdown("## Piano Editoriale & Suggerimenti")

    conn = _get_conn()

    # Sidebar
    with st.sidebar:
        st.divider()
        if st.button("Rigenera suggerimenti", use_container_width=True):
            with st.spinner("Generando..."):
                from mnemosyne.analytics.suggestions import generate_suggestions
                n = generate_suggestions(conn)
                st.success(f"{n} suggerimenti.")
                st.rerun()

    # ── Metrics bar ───────────────────────────────────────
    plan_done = conn.execute("SELECT COUNT(*) FROM plan_items WHERE done = 1 AND item_key NOT LIKE 'orphan_%' AND item_key NOT LIKE 'thin_%'").fetchone()[0]
    plan_total = len(PLAN_ITEMS)
    link_pending = conn.execute("SELECT COUNT(*) FROM suggestions WHERE type = 'add_link' AND status = 'pending'").fetchone()[0]
    refresh_pending = conn.execute("SELECT COUNT(*) FROM suggestions WHERE type = 'refresh_content' AND status = 'pending'").fetchone()[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Piano SEO", f"{plan_done}/{plan_total}")
    c2.metric("Link suggeriti", f"{link_pending:,}")
    c3.metric("Contenuti da aggiornare", refresh_pending)
    pct = plan_done / plan_total if plan_total else 0
    c4.metric("Completamento", f"{pct:.0%}")

    st.progress(pct)

    # ── Tabs ──────────────────────────────────────────────
    tab_piano, tab_links, tab_refresh = st.tabs([
        f"Piano SEO ({plan_done}/{plan_total})",
        f"Link da aggiungere ({link_pending:,})",
        f"Contenuti da aggiornare ({refresh_pending})",
    ])

    with tab_piano:
        _tab_piano(conn)

    with tab_links:
        _tab_links(conn)

    with tab_refresh:
        _tab_refresh(conn)

    conn.close()


# ══════════════════════════════════════════════════════════
# TAB 1: PIANO SEO
# ══════════════════════════════════════════════════════════


# Plan items definition
PLAN_ITEMS = [
    {"num": 1, "key": "meta_desc", "title": "Meta description mancanti", "week": "1-2", "sub": None},
    {"num": 2, "key": "title_long", "title": "Title troppo lunghi", "week": "1-2", "sub": None},
    {"num": 3, "key": "images_heavy", "title": "Immagini pesanti → WebP", "week": "1-2", "sub": None},
    {"num": 4, "key": "alt_text", "title": "Alt text immagini", "week": "1-2", "sub": None},
    {"num": 5, "key": "orphan_inbound", "title": "Post senza link in entrata", "week": "3-4", "sub": "orphan_in"},
    {"num": 6, "key": "orphan_outbound", "title": "Post senza link in uscita", "week": "3-4", "sub": "orphan_out"},
    {"num": 7, "key": "thin_content", "title": "Espandere pagine sotto 800 parole", "week": "5-6", "sub": "thin"},
    {"num": 8, "key": "schema_jsonld", "title": "Structured data JSON-LD (Yoast)", "week": "5-6", "sub": None},
    {"num": 8.5, "key": "schema_medical", "title": "Schema MedicalCondition su pillar", "week": "5-6", "sub": None},
    {"num": 9, "key": "ttfb", "title": "Ridurre TTFB pagine lente", "week": "7-8", "sub": None},
    {"num": 10, "key": "embeddings", "title": "Aggiornare embeddings", "week": "7-8", "sub": None},
]


def _tab_piano(conn):
    # Filters
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filter = st.radio("Mostra", ["Tutti", "Da fare", "Fatti"], horizontal=True, key="piano_status")
    with col_f2:
        week_options = ["Tutte"] + sorted(set(i["week"] for i in PLAN_ITEMS))
        week_filter = st.selectbox("Settimana", week_options, key="piano_week")

    for item in PLAN_ITEMS:
        done = _is_done(conn, item["key"])

        # Apply filters
        if status_filter == "Da fare" and done:
            continue
        if status_filter == "Fatti" and not done:
            continue
        if week_filter != "Tutte" and item["week"] != week_filter:
            continue

        # Sub-item progress
        sub_info = ""
        if item["sub"]:
            sub_rows = _get_sub_items(conn, item)
            sub_done = sum(1 for r in sub_rows if _is_done(conn, f"{item['sub']}_{r['id']}"))
            sub_total = len(sub_rows)
            sub_info = f" — {sub_done}/{sub_total}"

        card_title = f"{item['num']}. {item['title']}{sub_info}"
        clicked = _action_card(
            title=card_title,
            badge=f"Sett. {item['week']}",
            done=done,
            btn_key=f"plan_{item['key']}",
            on_toggle=True,
        )
        if clicked:
            _toggle_done(item["key"])
            st.rerun()

        # Expandable sub-items
        if item["sub"] and not done:
            sub_rows = _get_sub_items(conn, item)
            sub_done = sum(1 for r in sub_rows if _is_done(conn, f"{item['sub']}_{r['id']}"))
            sub_total = len(sub_rows)

            with st.expander(f"Dettaglio: {sub_done}/{sub_total} completati"):
                sub_filter = st.radio("Filtra", ["Da fare", "Fatti", "Tutti"],
                                     horizontal=True, key=f"sub_filter_{item['key']}")

                filtered = []
                for r in sub_rows:
                    # Use post id, or URL hash as fallback for pages without a post match
                    uid = r['id'] if r['id'] else hash(r['url']) % 100000
                    sub_key = f"{item['sub']}_{uid}"
                    is_d = _is_done(conn, sub_key)
                    if sub_filter == "Da fare" and is_d:
                        continue
                    if sub_filter == "Fatti" and not is_d:
                        continue
                    filtered.append((r, sub_key, is_d))

                visible = _paginate(filtered, f"sub_{item['key']}")

                for r, sub_key, is_d in visible:
                    title = html_mod.unescape(r['title'])[:45]
                    extra = f"{r['word_count'] or 0} parole" if 'word_count' in r.keys() else ""
                    clicked = _action_card(
                        title=title,
                        subtitle=extra,
                        url=r['url'] if 'url' in r.keys() else '',
                        done=is_d,
                        btn_key=f"sub_{sub_key}",
                        on_toggle=True,
                    )
                    if clicked:
                        _toggle_done(sub_key)
                        st.rerun()


def _get_sub_items(conn, item):
    """Get sub-items for a plan item."""
    if item["sub"] == "orphan_in":
        return conn.execute("""
            SELECT p.id, p.title, p.url, p.word_count FROM posts p
            WHERE NOT EXISTS (SELECT 1 FROM internal_links il WHERE il.target_post_id = p.id)
            ORDER BY p.word_count DESC
        """).fetchall()
    elif item["sub"] == "orphan_out":
        return conn.execute("""
            SELECT p.id, p.title, p.url, p.word_count FROM posts p
            WHERE NOT EXISTS (SELECT 1 FROM internal_links il WHERE il.source_post_id = p.id)
            ORDER BY p.word_count DESC
        """).fetchall()
    elif item["sub"] == "thin":
        last_run = conn.execute("SELECT id FROM crawl_runs WHERE status = 'completed' ORDER BY id DESC LIMIT 1").fetchone()
        run_id = last_run["id"] if last_run else 3
        return conn.execute("""
            SELECT cp.url, cp.title, cp.word_count, COALESCE(p.id, 0) as id
            FROM crawl_pages cp LEFT JOIN posts p ON p.url = cp.url
            WHERE cp.run_id = ? AND cp.word_count > 0 AND cp.word_count < 800 AND cp.status_code = 200
            ORDER BY cp.word_count ASC
        """, (run_id,)).fetchall()
    return []


# ══════════════════════════════════════════════════════════
# TAB 2: LINK DA AGGIUNGERE
# ══════════════════════════════════════════════════════════


def _tab_links(conn):
    col_f1, col_f2 = st.columns([0.3, 0.7])
    with col_f1:
        priority = st.selectbox("Priorità", ["Tutte", "Alta", "Media"], key="link_prio")
    with col_f2:
        search = st.text_input("Cerca per titolo", key="link_search", placeholder="es. anoressia")

    # Build query
    where = "WHERE type = 'add_link' AND status = 'pending'"
    params = []
    if priority == "Alta":
        where += " AND priority = 'alta'"
    elif priority == "Media":
        where += " AND priority = 'media'"
    if search:
        where += " AND (post_title LIKE ? OR target_title LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    total = conn.execute(f"SELECT COUNT(*) FROM suggestions {where}", params).fetchone()[0]

    # Bulk dismiss
    col_count, col_dismiss = st.columns([0.7, 0.3])
    with col_count:
        st.caption(f"{total} suggerimenti")
    with col_dismiss:
        if total > 0 and st.button("Dismissa tutti filtrati", key="dismiss_all_links", use_container_width=True):
            conn.execute(
                f"UPDATE suggestions SET status = 'dismissed', dismissed_at = ? {where}",
                [datetime.now(timezone.utc).isoformat()] + params,
            )
            conn.commit()
            st.rerun()

    # Paginated results
    rows = conn.execute(
        f"SELECT * FROM suggestions {where} ORDER BY priority DESC, id DESC LIMIT ? OFFSET ?",
        params + [PAGE_SIZE, (st.session_state.get("page_links", 1) - 1) * PAGE_SIZE],
    ).fetchall()

    if total > PAGE_SIZE:
        total_pages = math.ceil(total / PAGE_SIZE)
        pg = st.number_input("Pagina", 1, total_pages, 1, key="page_links")

        rows = conn.execute(
            f"SELECT * FROM suggestions {where} ORDER BY priority DESC, id DESC LIMIT ? OFFSET ?",
            params + [PAGE_SIZE, (pg - 1) * PAGE_SIZE],
        ).fetchall()

    for r in rows:
        source = html_mod.unescape(r['post_title'] or '')[:35]
        target = html_mod.unescape(r['target_title'] or '')[:35]
        data = json.loads(r['data_json']) if r['data_json'] else {}
        sim = data.get('similarity', 0)

        clicked = _action_card(
            title=f"{source} → {target}",
            subtitle=f"{r['reason'][:60]} (sim: {sim:.2f})" if sim else r['reason'][:60],
            badge=r['priority'],
            url=r['post_url'],
            btn_key=f"dismiss_link_{r['id']}",
            on_dismiss=True,
        )
        if clicked:
            _dismiss_suggestion(r['id'])
            st.rerun()


# ══════════════════════════════════════════════════════════
# TAB 3: CONTENUTI DA AGGIORNARE
# ══════════════════════════════════════════════════════════


def _tab_refresh(conn):
    col_f1, col_f2 = st.columns([0.3, 0.7])
    with col_f1:
        priority = st.selectbox("Priorità", ["Tutte", "Alta", "Media"], key="refresh_prio")
    with col_f2:
        search = st.text_input("Cerca", key="refresh_search", placeholder="es. depressione")

    where = "WHERE type = 'refresh_content' AND status = 'pending'"
    params = []
    if priority == "Alta":
        where += " AND priority = 'alta'"
    elif priority == "Media":
        where += " AND priority = 'media'"
    if search:
        where += " AND post_title LIKE ?"
        params.append(f"%{search}%")

    total = conn.execute(f"SELECT COUNT(*) FROM suggestions {where}", params).fetchone()[0]
    st.caption(f"{total} suggerimenti")

    rows = conn.execute(
        f"SELECT * FROM suggestions {where} ORDER BY priority DESC, id DESC LIMIT ?",
        params + [PAGE_SIZE],
    ).fetchall()

    if total > PAGE_SIZE:
        total_pages = math.ceil(total / PAGE_SIZE)
        pg = st.number_input("Pagina", 1, total_pages, 1, key="page_refresh")
        rows = conn.execute(
            f"SELECT * FROM suggestions {where} ORDER BY priority DESC, id DESC LIMIT ? OFFSET ?",
            params + [PAGE_SIZE, (pg - 1) * PAGE_SIZE],
        ).fetchall()

    for r in rows:
        data = json.loads(r['data_json']) if r['data_json'] else {}
        tags = []
        if data.get('zero_traffic'):
            tags.append("Zero traffico")
        if data.get('low_ctr'):
            tags.append(f"CTR basso ({data.get('clicks', 0)}/{data.get('impressions', 0)})")
        if data.get('old_content'):
            tags.append(f"Pubblicato {data.get('pub_year', '?')}")
        if data.get('thin_with_potential'):
            tags.append("Thin content")

        clicked = _action_card(
            title=html_mod.unescape(r['post_title'] or '')[:50],
            subtitle=" · ".join(tags) if tags else r['reason'][:60],
            badge=r['priority'],
            url=r['post_url'],
            btn_key=f"dismiss_refresh_{r['id']}",
            on_dismiss=True,
        )
        if clicked:
            _dismiss_suggestion(r['id'])
            st.rerun()


# ── Run ───────────────────────────────────────────────────
page()
