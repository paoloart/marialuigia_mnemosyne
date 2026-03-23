import sqlite3
import pytest

from mnemosyne.db.connection import get_connection
from mnemosyne.db.schema import create_tables


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def db(db_path):
    conn = get_connection(db_path)
    create_tables(conn)
    yield conn
    conn.close()


def test_get_connection_returns_connection(db_path):
    conn = get_connection(db_path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_foreign_keys_enabled(db_path):
    conn = get_connection(db_path)
    cursor = conn.execute("PRAGMA foreign_keys")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_create_tables_creates_all_tables(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = sorted([row[0] for row in cursor.fetchall() if row[0] != 'sqlite_sequence'])
    expected = sorted([
        "posts", "categories", "tags", "post_categories", "post_tags",
        "internal_links", "external_links", "headings", "embeddings",
        "dashboard_charts", "suggestions",
        "crawl_runs", "crawl_pages", "crawl_issues", "crawl_duplicates",
        "crawl_images", "crawl_links",
    ])
    assert tables == expected


def test_posts_table_columns(db):
    cursor = db.execute("PRAGMA table_info(posts)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "id" in columns
    assert "content_raw" in columns
    assert "content_text" in columns
    assert "meta_description" in columns
    assert "content_text_hash" in columns
    assert "word_count" in columns


def test_embeddings_composite_pk(db):
    db.execute(
        "INSERT INTO posts (id, title, slug, url, content_raw, status, date_published, date_modified) "
        "VALUES (1, 'Test', 'test', 'http://test', '<p>test</p>', 'publish', '2024-01-01', '2024-01-01')"
    )
    db.execute(
        "INSERT INTO embeddings (post_id, model_name, vector, source_hash, created_at) "
        "VALUES (1, 'model-a', X'00', 'hash-a', '2024-01-01')"
    )
    db.execute(
        "INSERT INTO embeddings (post_id, model_name, vector, source_hash, created_at) "
        "VALUES (1, 'model-b', X'00', 'hash-b', '2024-01-01')"
    )
    db.commit()
    cursor = db.execute("SELECT COUNT(*) FROM embeddings WHERE post_id = 1")
    assert cursor.fetchone()[0] == 2
