import hashlib
import pytest

from mnemosyne.db.connection import get_connection
from mnemosyne.db.schema import create_tables
from mnemosyne.scraper.extract import extract_all


@pytest.fixture
def db(tmp_path):
    conn = get_connection(str(tmp_path / "test.db"))
    create_tables(conn)
    conn.execute(
        """INSERT INTO posts (id, title, slug, url, content_raw, content_rendered, status, date_published, date_modified)
        VALUES (1, 'Test', 'test', 'https://marialuigia.com/test',
        'raw gutenberg',
        '<h2>Titolo</h2><p>Testo con <a href="https://marialuigia.com/altro">link interno</a> e <a href="https://google.com">link esterno</a>.</p>',
        'publish', '2024-01-01', '2024-01-01')"""
    )
    conn.commit()
    return conn


def test_extract_populates_content_text(db):
    extract_all(db, site_domain="marialuigia.com")
    row = db.execute("SELECT content_text FROM posts WHERE id = 1").fetchone()
    assert "Titolo" in row[0]
    assert "<h2>" not in row[0]


def test_extract_populates_word_count(db):
    extract_all(db, site_domain="marialuigia.com")
    row = db.execute("SELECT word_count FROM posts WHERE id = 1").fetchone()
    assert row[0] > 0


def test_extract_populates_content_text_hash(db):
    extract_all(db, site_domain="marialuigia.com")
    row = db.execute("SELECT content_text, content_text_hash FROM posts WHERE id = 1").fetchone()
    expected_hash = hashlib.sha256(row[0].encode()).hexdigest()
    assert row[1] == expected_hash


def test_extract_creates_headings(db):
    extract_all(db, site_domain="marialuigia.com")
    headings = db.execute("SELECT * FROM headings WHERE post_id = 1").fetchall()
    assert len(headings) == 1
    assert headings[0]["level"] == 2
    assert headings[0]["text"] == "Titolo"


def test_extract_creates_internal_links(db):
    extract_all(db, site_domain="marialuigia.com")
    links = db.execute("SELECT * FROM internal_links WHERE source_post_id = 1").fetchall()
    assert len(links) == 1
    assert "marialuigia.com/altro" in links[0]["target_url"]


def test_extract_creates_external_links(db):
    extract_all(db, site_domain="marialuigia.com")
    links = db.execute("SELECT * FROM external_links WHERE source_post_id = 1").fetchall()
    assert len(links) == 1
    assert "google.com" in links[0]["target_url"]
