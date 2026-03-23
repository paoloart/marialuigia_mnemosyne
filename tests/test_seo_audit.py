import sqlite3
import pytest

from mnemosyne.db.connection import get_connection
from mnemosyne.db.schema import create_tables
from mnemosyne.seo.audit import (
    posts_summary, posts_missing_meta, posts_thin_content,
    posts_no_internal_links, posts_no_inbound_links,
    heading_issues, embedding_status_report,
)
from mnemosyne.seo.url_match import match_url_to_post


@pytest.fixture
def db(tmp_path):
    conn = get_connection(str(tmp_path / "test.db"))
    create_tables(conn)
    # Insert test posts
    conn.execute(
        "INSERT INTO posts (id, title, slug, url, content_raw, content_rendered, content_text, "
        "status, date_published, date_modified, word_count, meta_description) "
        "VALUES (1, 'Post One', 'post-one', 'https://www.example.com/cat/post-one/', "
        "'<p>raw</p>', '<p>rendered</p>', 'word ' * 600, 'publish', '2024-01-01', '2024-01-01', 600, 'Meta one')"
    )
    conn.execute(
        "INSERT INTO posts (id, title, slug, url, content_raw, content_rendered, content_text, "
        "status, date_published, date_modified, word_count, meta_description) "
        "VALUES (2, 'Post Two', 'post-two', 'https://www.example.com/cat/post-two/', "
        "'<p>raw</p>', '<p>rendered</p>', 'word ' * 200, 'publish', '2024-02-01', '2024-02-01', 200, NULL)"
    )
    conn.execute(
        "INSERT INTO posts (id, title, slug, url, content_raw, content_rendered, content_text, "
        "status, date_published, date_modified, word_count, meta_description, embedding_status) "
        "VALUES (3, 'Post Three', 'post-three', 'https://www.example.com/cat/post-three/', "
        "'<p>raw</p>', '<p>rendered</p>', 'word ' * 100, 'publish', '2024-03-01', '2024-03-01', 100, '', 'current')"
    )
    # Headings
    conn.execute("INSERT INTO headings (post_id, level, text, position) VALUES (1, 2, 'First H2', 1)")
    conn.execute("INSERT INTO headings (post_id, level, text, position) VALUES (1, 3, 'Sub H3', 2)")
    conn.execute("INSERT INTO headings (post_id, level, text, position) VALUES (2, 2, 'H2', 1)")
    conn.execute("INSERT INTO headings (post_id, level, text, position) VALUES (2, 4, 'Jump to H4', 2)")  # level jump
    # Internal links: post 1 links to post 2
    conn.execute(
        "INSERT INTO internal_links (source_post_id, target_post_id, target_url, anchor_text) "
        "VALUES (1, 2, 'https://www.example.com/cat/post-two/', 'link text')"
    )
    conn.commit()
    return conn


def test_posts_summary(db):
    rows = posts_summary(db)
    assert len(rows) == 3
    # Post 1 has most words, should be first (ordered by word_count DESC)
    assert rows[0]["id"] == 1
    assert rows[0]["heading_count"] == 2
    assert rows[0]["outgoing_links"] == 1
    assert rows[0]["incoming_links"] == 0


def test_posts_missing_meta(db):
    rows = posts_missing_meta(db)
    # Post 2 has NULL meta, Post 3 has empty string meta
    assert len(rows) == 2
    ids = [r["id"] for r in rows]
    assert 2 in ids
    assert 3 in ids


def test_posts_thin_content(db):
    rows = posts_thin_content(db, min_words=500)
    assert len(rows) == 2  # Post 2 (200) and Post 3 (100)
    assert rows[0]["id"] == 3  # ordered by word_count ASC


def test_posts_no_internal_links(db):
    rows = posts_no_internal_links(db)
    # Post 2 and 3 have no outgoing internal links
    ids = [r["id"] for r in rows]
    assert 2 in ids
    assert 3 in ids
    assert 1 not in ids


def test_posts_no_inbound_links(db):
    rows = posts_no_inbound_links(db)
    # Post 1 and 3 have no incoming links (only post 2 is linked by post 1)
    ids = [r["id"] for r in rows]
    assert 1 in ids
    assert 3 in ids
    assert 2 not in ids


def test_heading_issues(db):
    rows = heading_issues(db)
    # Post 2 has a level jump (H2 -> H4), Post 3 has no H2 but only 100 words (below 200 threshold)
    issues = {r["id"]: r["issue"] for r in rows}
    assert 2 in issues
    assert "heading level jump" in issues[2]


def test_embedding_status_report(db):
    report = embedding_status_report(db)
    assert report["current"] == 1
    assert report["pending"] == 0
    assert report["not_generated"] == 2
    assert report["total"] == 3


def test_match_url_exact(db):
    result = match_url_to_post(db, "https://www.example.com/cat/post-one/")
    assert result is not None
    assert result["id"] == 1


def test_match_url_by_slug(db):
    result = match_url_to_post(db, "https://different-domain.com/something/post-two/")
    assert result is not None
    assert result["id"] == 2


def test_match_url_not_found(db):
    result = match_url_to_post(db, "https://www.example.com/nonexistent/")
    assert result is None
