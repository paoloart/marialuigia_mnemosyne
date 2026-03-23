"""Pagina dashboard: Comandi Pipeline — lancia sync, extract, embeddings, ecc."""

import subprocess
import sys
import os
import sqlite3
import time

import streamlit as st

from mnemosyne.config import get_db_path

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _run_command(args: list[str], label: str) -> None:
    """Run a mnemosyne command and show output in the dashboard."""
    with st.status(f"Eseguendo: {label}...", expanded=True) as status:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "mnemosyne"] + args,
                cwd=_PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.stdout:
                st.code(result.stdout, language=None)
            if result.returncode == 0:
                status.update(label=f"{label} — completato!", state="complete")
            else:
                if result.stderr:
                    st.error(result.stderr[:500])
                status.update(label=f"{label} — errore (exit {result.returncode})", state="error")
        except subprocess.TimeoutExpired:
            status.update(label=f"{label} — timeout (>10 min)", state="error")


def _run_command_bg(args: list[str], label: str) -> None:
    """Run a mnemosyne command in background (for long-running tasks like crawl)."""
    subprocess.Popen(
        [sys.executable, "-m", "mnemosyne"] + args,
        cwd=_PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    st.success(f"{label} lanciato in background!")


def page():
    st.markdown("### Comandi Pipeline")
    st.caption("Lancia i comandi di Mnemosyne direttamente dalla dashboard.")

    conn = _get_conn()

    # Status overview
    total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    emb_current = conn.execute("SELECT COUNT(*) FROM posts WHERE embedding_status = 'current'").fetchone()[0]
    emb_pending = conn.execute("SELECT COUNT(*) FROM posts WHERE embedding_status = 'pending'").fetchone()[0]
    last_crawl = conn.execute("SELECT started_at, status FROM crawl_runs ORDER BY id DESC LIMIT 1").fetchone()
    crawl_running = conn.execute("SELECT 1 FROM crawl_runs WHERE status = 'running' LIMIT 1").fetchone()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Post nel DB", total_posts)
    c2.metric("Embeddings", f"{emb_current} current")
    c3.metric("Pending", emb_pending)
    c4.metric("Ultimo crawl", last_crawl["started_at"][:10] if last_crawl else "Mai")

    conn.close()

    st.divider()

    # ── Comandi ───────────────────────────────────────────

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Dati WordPress")

        if st.button("Sync WordPress", use_container_width=True, help="Scarica post/categorie/tag da WordPress"):
            _run_command(["sync"], "Sync WordPress")

        if st.button("Estrai contenuti", use_container_width=True, help="Estrai testo, headings e link dai post"):
            _run_command(["extract"], "Estrai contenuti")

        st.markdown("##### Embeddings & Analytics")

        if st.button("Genera embeddings", use_container_width=True, help=f"Genera embeddings per i {emb_pending} post pending"):
            _run_command(["embeddings"], "Genera embeddings")

        if st.button("Refresh analytics", use_container_width=True, help="Ricalcola UMAP + KMeans + cornerstone"):
            _run_command(["refresh-analytics"], "Refresh analytics")

    with col2:
        st.markdown("##### SEO")

        if st.button("SEO Audit", use_container_width=True, help="Audit completo: meta, thin, orphans, headings"):
            _run_command(["seo", "audit"], "SEO Audit")

        st.markdown("##### Crawl Sito")

        if crawl_running:
            st.warning("Crawl in corso...")
        else:
            if st.button("Nuovo Crawl", use_container_width=True, type="primary", help="Crawla tutte le 315 pagine dalla sitemap"):
                _run_command_bg(["crawl"], "Crawl sito")
                st.rerun()

    st.divider()

    # ── Pipeline completa ─────────────────────────────────
    st.markdown("##### Pipeline completa")
    st.caption("Esegue sync → extract → embeddings in sequenza.")

    if st.button("Esegui pipeline completa", use_container_width=True, type="secondary"):
        _run_command(["sync"], "1/3 — Sync WordPress")
        _run_command(["extract"], "2/3 — Estrai contenuti")
        _run_command(["embeddings"], "3/3 — Genera embeddings")
        st.success("Pipeline completata!")


# ── Run ───────────────────────────────────────────────────
page()
