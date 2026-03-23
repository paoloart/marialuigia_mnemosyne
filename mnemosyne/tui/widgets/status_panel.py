import sqlite3
import time
from mnemosyne.seo.audit import (
    posts_missing_meta,
    posts_thin_content,
    posts_no_internal_links,
    heading_issues,
    embedding_status_report,
)

# Cache semplice per GA4/GSC (evita chiamate HTTP ad ogni refresh 30s)
_ga4_cache: dict = {"data": None, "ts": 0.0}
_gsc_cache: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 300  # secondi


def fetch_db_stats(conn: sqlite3.Connection) -> dict:
    """Statistiche base del DB: totale post e data ultimo sync."""
    total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    last_sync = conn.execute(
        "SELECT MAX(date_modified) FROM posts"
    ).fetchone()[0]
    return {"total_posts": total, "last_sync": last_sync}


def fetch_embedding_status(conn: sqlite3.Connection) -> dict:
    """Conta post per embedding_status."""
    report = embedding_status_report(conn)
    return {
        "current": report["current"],
        "pending": report["pending"],
        "not_generated": report["not_generated"],
    }


def fetch_seo_summary(conn: sqlite3.Connection) -> dict:
    """Conteggi audit SEO principali."""
    return {
        "orphan": len(posts_no_internal_links(conn)),
        "thin": len(posts_thin_content(conn)),
        "missing_meta": len(posts_missing_meta(conn)),
        "heading_issues": len(heading_issues(conn)),
    }


def fetch_cluster_info(conn: sqlite3.Connection) -> dict:
    """Info cornerstone: conta le chart pinned di analytics nel dashboard_charts."""
    # Il cornerstone score è calcolato in-memory da semantic_map.py e non viene
    # persistito in posts. Come proxy usiamo il numero di chart analytics pinned
    # nel dashboard, che indica che refresh-analytics è stato eseguito.
    pinned = conn.execute(
        "SELECT COUNT(*) FROM dashboard_charts WHERE pinned = 1"
    ).fetchone()[0]
    return {"cornerstone": pinned}


def fetch_ga4_stats() -> dict | None:
    """Fetch GA4 overview con cache 300s. Ritorna None se non disponibile."""
    now = time.time()
    if _ga4_cache["data"] is not None and now - _ga4_cache["ts"] < _CACHE_TTL:
        return _ga4_cache["data"]
    try:
        from mnemosyne.dashboard import ga4_client
        from mnemosyne import config
        data = ga4_client.get_overview(config.get_google_credentials_path())
        _ga4_cache["data"] = data
        _ga4_cache["ts"] = now
        return data
    except Exception:
        return _ga4_cache["data"]  # ritorna dati vecchi se disponibili


def fetch_gsc_stats() -> dict | None:
    """Fetch GSC overview con cache 300s. Ritorna None se non disponibile."""
    now = time.time()
    if _gsc_cache["data"] is not None and now - _gsc_cache["ts"] < _CACHE_TTL:
        return _gsc_cache["data"]
    try:
        from mnemosyne.dashboard import gsc_client
        from mnemosyne import config
        data = gsc_client.get_overview(config.get_google_credentials_path())
        _gsc_cache["data"] = data
        _gsc_cache["ts"] = now
        return data
    except Exception:
        return _gsc_cache["data"]
