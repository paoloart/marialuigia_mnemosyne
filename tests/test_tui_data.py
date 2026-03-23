import sqlite3
import pytest
from mnemosyne.db.schema import create_tables
from mnemosyne.tui.widgets.status_panel import (
    fetch_db_stats,
    fetch_embedding_status,
    fetch_seo_summary,
    fetch_cluster_info,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_tables(c)
    yield c
    c.close()


def test_fetch_db_stats_empty(conn):
    stats = fetch_db_stats(conn)
    assert stats["total_posts"] == 0
    assert stats["last_sync"] is None


def test_fetch_db_stats_with_posts(conn):
    # content_raw è NOT NULL — deve essere incluso
    conn.execute(
        "INSERT INTO posts (id, title, slug, url, content_raw, status, date_modified, date_published) "
        "VALUES (1, 'Test', 'test', 'http://x.com/test', '<p>hi</p>', 'publish', '2026-01-01', '2026-01-01')"
    )
    conn.commit()
    stats = fetch_db_stats(conn)
    assert stats["total_posts"] == 1


def test_fetch_embedding_status_empty(conn):
    status = fetch_embedding_status(conn)
    assert status["current"] == 0
    assert status["pending"] == 0
    assert status["not_generated"] == 0


def test_fetch_embedding_status_counts(conn):
    conn.execute(
        "INSERT INTO posts (id, title, slug, url, content_raw, status, date_modified, date_published, embedding_status) "
        "VALUES (1, 'A', 'a', 'http://x.com/a', '', 'publish', '2026-01-01', '2026-01-01', 'current')"
    )
    conn.execute(
        "INSERT INTO posts (id, title, slug, url, content_raw, status, date_modified, date_published, embedding_status) "
        "VALUES (2, 'B', 'b', 'http://x.com/b', '', 'publish', '2026-01-01', '2026-01-01', 'pending')"
    )
    conn.execute(
        "INSERT INTO posts (id, title, slug, url, content_raw, status, date_modified, date_published) "
        "VALUES (3, 'C', 'c', 'http://x.com/c', '', 'publish', '2026-01-01', '2026-01-01')"
    )
    conn.commit()
    status = fetch_embedding_status(conn)
    assert status["current"] == 1
    assert status["pending"] == 1
    assert status["not_generated"] == 1


def test_fetch_seo_summary_empty(conn):
    summary = fetch_seo_summary(conn)
    assert summary["orphan"] == 0
    assert summary["thin"] == 0
    assert summary["missing_meta"] == 0
    assert summary["heading_issues"] == 0


def test_fetch_cluster_info_empty(conn):
    info = fetch_cluster_info(conn)
    assert info["cornerstone"] == 0
