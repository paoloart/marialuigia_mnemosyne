from unittest.mock import MagicMock
import pytest

from mnemosyne.db.connection import get_connection
from mnemosyne.db.schema import create_tables
from mnemosyne.scraper.sync import sync_all


def _make_wp_post(post_id, title="Test", modified="2024-01-01T00:00:00"):
    return {
        "id": post_id,
        "title": {"rendered": title},
        "slug": f"test-{post_id}",
        "link": f"https://example.com/test-{post_id}",
        "content": {"rendered": f"<p>Content {post_id}</p>"},
        "excerpt": {"rendered": "<p>Excerpt</p>"},
        "status": "publish",
        "date": "2024-01-01T00:00:00",
        "modified": modified,
        "author": 1,
        "featured_media": 0,
        "categories": [1],
        "tags": [2],
        "yoast_head_json": {"description": "Meta description"},
    }


@pytest.fixture
def db(tmp_path):
    conn = get_connection(str(tmp_path / "test.db"))
    create_tables(conn)
    return conn


def test_sync_inserts_new_posts(db):
    client = MagicMock()
    client.get_post_ids.return_value = [1, 2]
    client.get_post.side_effect = [_make_wp_post(1), _make_wp_post(2)]
    client.get_categories.return_value = [{"id": 1, "name": "Cat", "slug": "cat", "parent": 0}]
    client.get_tags.return_value = [{"id": 2, "name": "Tag", "slug": "tag"}]

    sync_all(db, client, delay=0)

    cursor = db.execute("SELECT COUNT(*) FROM posts")
    assert cursor.fetchone()[0] == 2


def test_sync_skips_unmodified_posts(db):
    """On second sync with same date_modified, post is fetched but not re-inserted."""
    client = MagicMock()
    client.get_post_ids.return_value = [1]
    client.get_post.return_value = _make_wp_post(1, modified="2024-01-01T00:00:00")
    client.get_categories.return_value = [{"id": 1, "name": "Cat", "slug": "cat", "parent": 0}]
    client.get_tags.return_value = [{"id": 2, "name": "Tag", "slug": "tag"}]

    sync_all(db, client, delay=0)

    # Manually set content_text to verify it's NOT wiped on re-sync
    db.execute("UPDATE posts SET content_text = 'preserved' WHERE id = 1")
    db.commit()

    # Second sync — post not modified
    client.get_post.return_value = _make_wp_post(1, modified="2024-01-01T00:00:00")
    sync_all(db, client, delay=0)

    row = db.execute("SELECT content_text FROM posts WHERE id = 1").fetchone()
    assert row[0] == "preserved"


def test_sync_updates_modified_posts(db):
    client = MagicMock()
    client.get_post_ids.return_value = [1]
    client.get_post.return_value = _make_wp_post(1, title="Original", modified="2024-01-01T00:00:00")
    client.get_categories.return_value = [{"id": 1, "name": "Cat", "slug": "cat", "parent": 0}]
    client.get_tags.return_value = [{"id": 2, "name": "Tag", "slug": "tag"}]

    sync_all(db, client, delay=0)

    client.get_post.return_value = _make_wp_post(1, title="Updated", modified="2024-06-01T00:00:00")
    sync_all(db, client, delay=0)

    cursor = db.execute("SELECT title FROM posts WHERE id = 1")
    assert cursor.fetchone()[0] == "Updated"


def test_sync_saves_categories_and_tags(db):
    client = MagicMock()
    client.get_post_ids.return_value = [1]
    client.get_post.return_value = _make_wp_post(1)
    client.get_categories.return_value = [{"id": 1, "name": "News", "slug": "news", "parent": 0}]
    client.get_tags.return_value = [{"id": 2, "name": "Food", "slug": "food"}]

    sync_all(db, client, delay=0)

    cats = db.execute("SELECT * FROM categories").fetchall()
    assert len(cats) == 1
    tags = db.execute("SELECT * FROM tags").fetchall()
    assert len(tags) == 1
    pc = db.execute("SELECT * FROM post_categories").fetchall()
    assert len(pc) == 1
    pt = db.execute("SELECT * FROM post_tags").fetchall()
    assert len(pt) == 1
