# Mnemosyne Maria Luigia — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local SQLite database of ~190 WordPress blog posts with extraction pipeline and embedding support for SEO/structural analysis.

**Architecture:** Three-phase pipeline (Sync → Extract → Embeddings) with SQLite storage. WordPress REST API with Basic Auth for data ingestion. BeautifulSoup for HTML parsing. OpenAI for embeddings on demand.

**Tech Stack:** Python 3.11+, SQLite, requests, beautifulsoup4, python-dotenv, openai, numpy

**Spec:** `docs/superpowers/specs/2026-03-17-mnemosyne-design.md`

**Deferred to later phase:** `analysis/` modules (seo.py, structure.py, links.py) and `notebooks/` directory. These will be added once the data pipeline is stable and real data is available.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `mnemosyne/__init__.py` | Package marker |
| `mnemosyne/__main__.py` | CLI entry point (`python -m mnemosyne sync\|extract\|embeddings`) |
| `mnemosyne/config.py` | Load .env, expose settings (lazy, no crash without .env) |
| `mnemosyne/db/__init__.py` | Package marker |
| `mnemosyne/db/connection.py` | get_connection() → sqlite3.Connection with WAL mode and FK enforcement |
| `mnemosyne/db/schema.py` | create_tables() — all 8 tables per spec |
| `mnemosyne/scraper/__init__.py` | Package marker |
| `mnemosyne/scraper/wp_client.py` | WPClient class — fetch single post, list all post IDs, fetch categories, fetch tags |
| `mnemosyne/scraper/sync.py` | sync_all() — orchestrate download with delay, incremental via date_modified |
| `mnemosyne/scraper/parser.py` | extract_text(), extract_headings(), extract_links() from content_html |
| `mnemosyne/scraper/extract.py` | extract_all() — populate derived fields (content_text, links, headings) |
| `mnemosyne/embeddings/__init__.py` | Package marker |
| `mnemosyne/embeddings/generator.py` | generate_embeddings() — OpenAI API, hash comparison, numpy serialization |
| `tests/test_db.py` | Tests for schema creation and connection |
| `tests/test_parser.py` | Tests for HTML parsing (text extraction, links, headings) |
| `tests/test_wp_client.py` | Tests for WP client (mocked HTTP) |
| `tests/test_sync.py` | Tests for sync orchestration |
| `tests/test_extract.py` | Tests for extract phase |
| `tests/test_embeddings.py` | Tests for embedding generation |
| `.env.example` | Template for .env |
| `.gitignore` | Ignore .env, data/*.db, __pycache__, .venv |
| `requirements.txt` | Dependencies |

---

## Task 1: Project scaffolding

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`, `mnemosyne/__init__.py`

- [ ] **Step 1: Initialize git repo**

```bash
cd /Users/paoloartoni/tinke/progetti_AI/Mnemosyne_Maria_Luigia
git init
```

- [ ] **Step 2: Create .gitignore**

```
.env
data/*.db
__pycache__/
*.pyc
.venv/
*.egg-info/
.ipynb_checkpoints/
```

- [ ] **Step 3: Create .env.example**

```
WP_BASE_URL=https://your-site.com
WP_USERNAME=your-username
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx
OPENAI_API_KEY=sk-...
```

- [ ] **Step 4: Create requirements.txt**

```
requests>=2.31.0
beautifulsoup4>=4.12.0
python-dotenv>=1.0.0
openai>=1.0.0
numpy>=1.26.0
pytest>=7.0.0
```

- [ ] **Step 5: Create mnemosyne/__init__.py**

```python
"""Mnemosyne Maria Luigia — WordPress blog analysis toolkit."""
```

- [ ] **Step 6: Create data/ directory**

```bash
mkdir -p data
touch data/.gitkeep
```

- [ ] **Step 7: Commit**

```bash
git add .gitignore .env.example requirements.txt mnemosyne/__init__.py data/.gitkeep
git commit -m "chore: project scaffolding"
```

---

## Task 2: Database schema and connection

**Files:**
- Create: `mnemosyne/db/__init__.py`, `mnemosyne/db/connection.py`, `mnemosyne/db/schema.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Create tests/test_db.py with failing tests**

```python
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
    tables = sorted([row[0] for row in cursor.fetchall()])
    expected = sorted([
        "posts", "categories", "tags", "post_categories", "post_tags",
        "internal_links", "external_links", "headings", "embeddings",
    ])
    assert tables == expected


def test_posts_table_columns(db):
    cursor = db.execute("PRAGMA table_info(posts)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "id" in columns
    assert "content_html" in columns
    assert "content_text" in columns
    assert "meta_description" in columns
    assert "content_text_hash" in columns
    assert "word_count" in columns


def test_embeddings_composite_pk(db):
    """Embeddings PK is (post_id, model_name)."""
    db.execute(
        "INSERT INTO posts (id, title, slug, url, content_html, status, date_published, date_modified) "
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Create mnemosyne/db/__init__.py**

```python
```

- [ ] **Step 4: Create mnemosyne/db/connection.py**

```python
import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn
```

- [ ] **Step 5: Create mnemosyne/db/schema.py**

```python
import sqlite3

SQL = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    url TEXT NOT NULL,
    content_html TEXT NOT NULL,
    content_text TEXT,
    excerpt TEXT,
    status TEXT NOT NULL,
    date_published TEXT NOT NULL,
    date_modified TEXT NOT NULL,
    author TEXT,
    featured_image_url TEXT,
    featured_image_alt TEXT,
    meta_description TEXT,
    content_text_hash TEXT,
    word_count INTEGER
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    parent_id INTEGER,
    FOREIGN KEY (parent_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_categories (
    post_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY (post_id, category_id),
    FOREIGN KEY (post_id) REFERENCES posts(id),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS post_tags (
    post_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (post_id, tag_id),
    FOREIGN KEY (post_id) REFERENCES posts(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
);

CREATE TABLE IF NOT EXISTS internal_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_post_id INTEGER NOT NULL,
    target_post_id INTEGER,
    target_url TEXT NOT NULL,
    anchor_text TEXT,
    FOREIGN KEY (source_post_id) REFERENCES posts(id),
    FOREIGN KEY (target_post_id) REFERENCES posts(id)
);

CREATE TABLE IF NOT EXISTS external_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_post_id INTEGER NOT NULL,
    target_url TEXT NOT NULL,
    anchor_text TEXT,
    FOREIGN KEY (source_post_id) REFERENCES posts(id)
);

CREATE TABLE IF NOT EXISTS headings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 6),
    text TEXT NOT NULL,
    position INTEGER NOT NULL,
    FOREIGN KEY (post_id) REFERENCES posts(id)
);

CREATE TABLE IF NOT EXISTS embeddings (
    post_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    vector BLOB NOT NULL,
    source_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (post_id, model_name),
    FOREIGN KEY (post_id) REFERENCES posts(id)
);
"""


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all database tables."""
    conn.executescript(SQL)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: All 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add mnemosyne/db/ tests/test_db.py
git commit -m "feat: database schema and connection with tests"
```

---

## Task 3: Configuration

**Files:**
- Create: `mnemosyne/config.py`

- [ ] **Step 1: Create mnemosyne/config.py**

Config uses functions to avoid crashing on import when .env is not present (e.g., during tests).

```python
import os
from functools import lru_cache
from dotenv import load_dotenv


def _load():
    load_dotenv()


@lru_cache
def get_wp_base_url() -> str:
    _load()
    return os.environ["WP_BASE_URL"].rstrip("/")


@lru_cache
def get_wp_username() -> str:
    _load()
    return os.environ["WP_USERNAME"]


@lru_cache
def get_wp_app_password() -> str:
    _load()
    return os.environ["WP_APP_PASSWORD"]


@lru_cache
def get_openai_api_key() -> str:
    _load()
    return os.environ["OPENAI_API_KEY"]


def get_db_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "maria_luigia.db")


def get_sync_delay() -> float:
    _load()
    return float(os.environ.get("SYNC_DELAY", "1.0"))


def get_retry_max() -> int:
    _load()
    return int(os.environ.get("RETRY_MAX", "3"))
```

- [ ] **Step 2: Commit**

```bash
git add mnemosyne/config.py
git commit -m "feat: lazy configuration module with env vars"
```

---

## Task 4: WordPress API client

**Files:**
- Create: `mnemosyne/scraper/__init__.py`, `mnemosyne/scraper/wp_client.py`
- Test: `tests/test_wp_client.py`

- [ ] **Step 1: Create tests/test_wp_client.py with failing tests**

```python
from unittest.mock import patch, MagicMock
import pytest

from mnemosyne.scraper.wp_client import WPClient


@pytest.fixture
def client():
    return WPClient(
        base_url="https://example.com",
        username="user",
        app_password="pass",
    )


def _mock_response(json_data, status_code=200, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.headers = headers or {"X-WP-Total": "2"}
    resp.raise_for_status = MagicMock()
    return resp


@patch("mnemosyne.scraper.wp_client.requests.get")
def test_get_total_posts(mock_get, client):
    mock_get.return_value = _mock_response([], headers={"X-WP-Total": "190"})
    assert client.get_total_posts() == 190


@patch("mnemosyne.scraper.wp_client.requests.get")
def test_get_post_ids(mock_get, client):
    page1 = [{"id": 1}, {"id": 2}]
    page2 = [{"id": 3}]
    mock_get.side_effect = [
        _mock_response(page1, headers={"X-WP-TotalPages": "2", "X-WP-Total": "3"}),
        _mock_response(page2, headers={"X-WP-TotalPages": "2", "X-WP-Total": "3"}),
    ]
    ids = client.get_post_ids()
    assert ids == [1, 2, 3]


@patch("mnemosyne.scraper.wp_client.requests.get")
def test_get_post(mock_get, client):
    post_data = {
        "id": 42,
        "title": {"rendered": "Test Title"},
        "slug": "test-title",
        "link": "https://example.com/test-title",
        "content": {"rendered": "<p>Hello</p>"},
        "excerpt": {"rendered": "<p>Ex</p>"},
        "status": "publish",
        "date": "2024-01-01T00:00:00",
        "modified": "2024-01-02T00:00:00",
        "author": 1,
        "featured_media": 0,
        "categories": [1, 2],
        "tags": [3],
        "yoast_head_json": {"description": "Meta desc"},
    }
    mock_get.return_value = _mock_response(post_data)
    post = client.get_post(42)
    assert post["id"] == 42
    assert post["title"]["rendered"] == "Test Title"


@patch("mnemosyne.scraper.wp_client.requests.get")
def test_get_categories(mock_get, client):
    cats = [{"id": 1, "name": "News", "slug": "news", "parent": 0}]
    mock_get.return_value = _mock_response(cats, headers={"X-WP-TotalPages": "1", "X-WP-Total": "1"})
    result = client.get_categories()
    assert result[0]["name"] == "News"


@patch("mnemosyne.scraper.wp_client.requests.get")
def test_get_tags(mock_get, client):
    tags = [{"id": 1, "name": "Food", "slug": "food"}]
    mock_get.return_value = _mock_response(tags, headers={"X-WP-TotalPages": "1", "X-WP-Total": "1"})
    result = client.get_tags()
    assert result[0]["name"] == "Food"


@patch("mnemosyne.scraper.wp_client.requests.get")
def test_retry_on_429(mock_get, client):
    error_resp = MagicMock()
    error_resp.status_code = 429
    error_resp.raise_for_status.side_effect = Exception("Rate limited")
    ok_resp = _mock_response({"id": 1})
    mock_get.side_effect = [error_resp, ok_resp]
    result = client._request("https://example.com/wp-json/wp/v2/posts/1")
    assert result.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_wp_client.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Create mnemosyne/scraper/__init__.py**

```python
```

- [ ] **Step 4: Create mnemosyne/scraper/wp_client.py**

Note: WordPress REST API uses `_fields` (with underscore) for field filtering.

```python
import time
import requests
from requests.auth import HTTPBasicAuth


class WPClient:
    """Client for WordPress REST API."""

    def __init__(self, base_url: str, username: str, app_password: str,
                 retry_max: int = 3):
        self.api_url = f"{base_url.rstrip('/')}/wp-json/wp/v2"
        self.auth = HTTPBasicAuth(username, app_password)
        self.retry_max = retry_max

    def _request(self, url: str, params: dict | None = None) -> requests.Response:
        """Make a GET request with exponential backoff on 429/5xx."""
        for attempt in range(self.retry_max):
            resp = requests.get(url, params=params, auth=self.auth)
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = 2 ** attempt
                print(f"HTTP {resp.status_code}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def get_total_posts(self) -> int:
        """Return total number of posts."""
        resp = self._request(f"{self.api_url}/posts", params={"per_page": 1})
        return int(resp.headers["X-WP-Total"])

    def get_post_ids(self) -> list[int]:
        """Return all post IDs, paginating through results."""
        ids = []
        page = 1
        while True:
            resp = self._request(
                f"{self.api_url}/posts",
                params={"per_page": 100, "page": page, "_fields": "id"},
            )
            posts = resp.json()
            if not posts:
                break
            ids.extend(p["id"] for p in posts)
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1
        return ids

    def get_post(self, post_id: int) -> dict:
        """Fetch a single post by ID."""
        resp = self._request(f"{self.api_url}/posts/{post_id}")
        return resp.json()

    def get_categories(self) -> list[dict]:
        """Fetch all categories."""
        return self._fetch_all(f"{self.api_url}/categories")

    def get_tags(self) -> list[dict]:
        """Fetch all tags."""
        return self._fetch_all(f"{self.api_url}/tags")

    def _fetch_all(self, url: str) -> list[dict]:
        """Fetch all items from a paginated endpoint."""
        items = []
        page = 1
        while True:
            resp = self._request(url, params={"per_page": 100, "page": page})
            data = resp.json()
            if not data:
                break
            items.extend(data)
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1
        return items
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_wp_client.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add mnemosyne/scraper/ tests/test_wp_client.py
git commit -m "feat: WordPress REST API client with retry logic"
```

---

## Task 5: Sync orchestration

**Files:**
- Create: `mnemosyne/scraper/sync.py`
- Test: `tests/test_sync.py`

- [ ] **Step 1: Create tests/test_sync.py with failing tests**

```python
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
    client.get_categories.return_value = []
    client.get_tags.return_value = []

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
    client.get_categories.return_value = []
    client.get_tags.return_value = []

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sync.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Create mnemosyne/scraper/sync.py**

Uses `INSERT ... ON CONFLICT DO UPDATE` to preserve extract-phase columns (content_text, content_text_hash, word_count) on re-sync.

```python
import time
import sqlite3


def sync_all(conn: sqlite3.Connection, client, delay: float = 1.0) -> None:
    """Sync all posts, categories, and tags from WordPress."""
    print("Fetching categories...")
    _sync_categories(conn, client.get_categories())

    print("Fetching tags...")
    _sync_tags(conn, client.get_tags())

    print("Fetching post IDs...")
    post_ids = client.get_post_ids()
    print(f"Found {len(post_ids)} posts")

    for i, post_id in enumerate(post_ids, 1):
        existing = conn.execute(
            "SELECT date_modified FROM posts WHERE id = ?", (post_id,)
        ).fetchone()

        post = client.get_post(post_id)
        remote_modified = post["modified"]

        if existing and existing[0] == remote_modified:
            print(f"[{i}/{len(post_ids)}] Post {post_id}: unchanged, skipping")
            if delay > 0 and i < len(post_ids):
                time.sleep(delay)
            continue

        action = "updating" if existing else "inserting"
        print(f"[{i}/{len(post_ids)}] Post {post_id}: {action}")
        _upsert_post(conn, post)
        _sync_post_relations(conn, post)
        conn.commit()

        if delay > 0 and i < len(post_ids):
            time.sleep(delay)

    print("Sync complete.")


def _upsert_post(conn: sqlite3.Connection, post: dict) -> None:
    """Insert or update a post, preserving extract-phase columns."""
    yoast = post.get("yoast_head_json") or {}
    meta_desc = yoast.get("description")

    conn.execute(
        """INSERT INTO posts
        (id, title, slug, url, content_html, excerpt, status,
         date_published, date_modified, author, featured_image_url,
         featured_image_alt, meta_description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            slug = excluded.slug,
            url = excluded.url,
            content_html = excluded.content_html,
            excerpt = excluded.excerpt,
            status = excluded.status,
            date_published = excluded.date_published,
            date_modified = excluded.date_modified,
            author = excluded.author,
            featured_image_url = excluded.featured_image_url,
            featured_image_alt = excluded.featured_image_alt,
            meta_description = excluded.meta_description
        """,
        (
            post["id"],
            post["title"]["rendered"],
            post["slug"],
            post["link"],
            post["content"]["rendered"],
            post["excerpt"]["rendered"],
            post["status"],
            post["date"],
            post["modified"],
            post.get("author"),
            None,  # featured_image_url — requires separate media fetch
            None,  # featured_image_alt
            meta_desc,
        ),
    )


def _sync_post_relations(conn: sqlite3.Connection, post: dict) -> None:
    """Sync category and tag relations for a post."""
    post_id = post["id"]
    conn.execute("DELETE FROM post_categories WHERE post_id = ?", (post_id,))
    conn.execute("DELETE FROM post_tags WHERE post_id = ?", (post_id,))

    for cat_id in post.get("categories", []):
        conn.execute(
            "INSERT OR IGNORE INTO post_categories (post_id, category_id) VALUES (?, ?)",
            (post_id, cat_id),
        )
    for tag_id in post.get("tags", []):
        conn.execute(
            "INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)",
            (post_id, tag_id),
        )


def _sync_categories(conn: sqlite3.Connection, categories: list[dict]) -> None:
    """Sync all categories."""
    for cat in categories:
        conn.execute(
            "INSERT OR REPLACE INTO categories (id, name, slug, parent_id) VALUES (?, ?, ?, ?)",
            (cat["id"], cat["name"], cat["slug"], cat["parent"] or None),
        )
    conn.commit()


def _sync_tags(conn: sqlite3.Connection, tags: list[dict]) -> None:
    """Sync all tags."""
    for tag in tags:
        conn.execute(
            "INSERT OR REPLACE INTO tags (id, name, slug) VALUES (?, ?, ?)",
            (tag["id"], tag["name"], tag["slug"]),
        )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sync.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add mnemosyne/scraper/sync.py tests/test_sync.py
git commit -m "feat: sync orchestration with incremental upsert"
```

---

## Task 6: HTML parser

**Files:**
- Create: `mnemosyne/scraper/parser.py`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Create tests/test_parser.py with failing tests**

```python
import pytest
from mnemosyne.scraper.parser import extract_text, extract_headings, extract_links


SAMPLE_HTML = """
<h2>Introduction</h2>
<p>Welcome to <a href="https://marialuigia.com/altro-post">another post</a> about food.</p>
<h3>Details</h3>
<p>Read more at <a href="https://external.com/page">external site</a>.</p>
<p>Also check <a href="https://marialuigia.com/ricetta">our recipe</a>.</p>
"""

SITE_DOMAIN = "marialuigia.com"


def test_extract_text_strips_html():
    text = extract_text(SAMPLE_HTML)
    assert "<p>" not in text
    assert "<h2>" not in text
    assert "Welcome to" in text
    assert "another post" in text


def test_extract_text_preserves_content():
    text = extract_text("<p>Hello <strong>world</strong></p>")
    assert "Hello" in text
    assert "world" in text


def test_extract_headings():
    headings = extract_headings(SAMPLE_HTML)
    assert len(headings) == 2
    assert headings[0] == {"level": 2, "text": "Introduction", "position": 0}
    assert headings[1] == {"level": 3, "text": "Details", "position": 1}


def test_extract_links_separates_internal_and_external():
    internal, external = extract_links(SAMPLE_HTML, SITE_DOMAIN)
    assert len(internal) == 2
    assert len(external) == 1
    assert internal[0]["url"] == "https://marialuigia.com/altro-post"
    assert internal[0]["anchor_text"] == "another post"
    assert external[0]["url"] == "https://external.com/page"
    assert external[0]["anchor_text"] == "external site"


def test_extract_links_handles_relative_urls():
    html = '<a href="/local-page">Local</a>'
    internal, external = extract_links(html, "example.com")
    assert len(internal) == 1


def test_extract_links_ignores_anchors_and_empty():
    html = '<a href="#section">Jump</a><a href="">Empty</a><a>No href</a>'
    internal, external = extract_links(html, "example.com")
    assert len(internal) == 0
    assert len(external) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_parser.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Create mnemosyne/scraper/parser.py**

```python
from urllib.parse import urlparse
from bs4 import BeautifulSoup


def extract_text(html: str) -> str:
    """Strip HTML tags and return clean text."""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def extract_headings(html: str) -> list[dict]:
    """Extract all headings (h1-h6) with level and position."""
    soup = BeautifulSoup(html, "html.parser")
    headings = []
    for i, tag in enumerate(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])):
        headings.append({
            "level": int(tag.name[1]),
            "text": tag.get_text(strip=True),
            "position": i,
        })
    return headings


def extract_links(html: str, site_domain: str) -> tuple[list[dict], list[dict]]:
    """Extract links, separating internal from external.

    Returns (internal_links, external_links).
    Each link is {"url": str, "anchor_text": str}.
    """
    soup = BeautifulSoup(html, "html.parser")
    internal = []
    external = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#"):
            continue

        anchor = a.get_text(strip=True)
        parsed = urlparse(href)

        # Relative URL → internal
        if not parsed.netloc:
            if parsed.path:
                internal.append({"url": href, "anchor_text": anchor})
            continue

        # Strict domain match: exact or subdomain
        if parsed.netloc == site_domain or parsed.netloc.endswith("." + site_domain):
            internal.append({"url": href, "anchor_text": anchor})
        else:
            external.append({"url": href, "anchor_text": anchor})

    return internal, external
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_parser.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add mnemosyne/scraper/parser.py tests/test_parser.py
git commit -m "feat: HTML parser for text, headings, and links extraction"
```

---

## Task 7: Extract command

**Files:**
- Create: `mnemosyne/scraper/extract.py`
- Test: `tests/test_extract.py`

- [ ] **Step 1: Create tests/test_extract.py with failing tests**

```python
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
        """INSERT INTO posts (id, title, slug, url, content_html, status, date_published, date_modified)
        VALUES (1, 'Test', 'test', 'https://marialuigia.com/test',
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_extract.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Create mnemosyne/scraper/extract.py**

```python
import hashlib
import sqlite3
from urllib.parse import urlparse

from mnemosyne.scraper.parser import extract_text, extract_headings, extract_links


def extract_all(conn: sqlite3.Connection, site_domain: str) -> None:
    """Extract text, headings, and links from all posts' content_html."""
    posts = conn.execute("SELECT id, content_html, url FROM posts").fetchall()
    print(f"Extracting from {len(posts)} posts...")

    for post in posts:
        post_id = post["id"]
        html = post["content_html"]

        # Extract clean text
        text = extract_text(html)
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        word_count = len(text.split())

        conn.execute(
            "UPDATE posts SET content_text = ?, content_text_hash = ?, word_count = ? WHERE id = ?",
            (text, text_hash, word_count, post_id),
        )

        # Clear old derived data
        conn.execute("DELETE FROM headings WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM internal_links WHERE source_post_id = ?", (post_id,))
        conn.execute("DELETE FROM external_links WHERE source_post_id = ?", (post_id,))

        # Headings
        for heading in extract_headings(html):
            conn.execute(
                "INSERT INTO headings (post_id, level, text, position) VALUES (?, ?, ?, ?)",
                (post_id, heading["level"], heading["text"], heading["position"]),
            )

        # Links
        internal, external = extract_links(html, site_domain)

        for link in internal:
            target_post_id = _resolve_post_id(conn, link["url"], site_domain)
            conn.execute(
                "INSERT INTO internal_links (source_post_id, target_post_id, target_url, anchor_text) "
                "VALUES (?, ?, ?, ?)",
                (post_id, target_post_id, link["url"], link["anchor_text"]),
            )

        for link in external:
            conn.execute(
                "INSERT INTO external_links (source_post_id, target_url, anchor_text) VALUES (?, ?, ?)",
                (post_id, link["url"], link["anchor_text"]),
            )

    conn.commit()
    print("Extraction complete.")


def _resolve_post_id(conn: sqlite3.Connection, url: str, site_domain: str) -> int | None:
    """Try to find a post ID matching the given internal URL."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return None
    slug = path.split("/")[-1]
    row = conn.execute("SELECT id FROM posts WHERE slug = ?", (slug,)).fetchone()
    return row["id"] if row else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_extract.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add mnemosyne/scraper/extract.py tests/test_extract.py
git commit -m "feat: extract phase — text, headings, links from HTML"
```

---

## Task 8: Embeddings generator

**Files:**
- Create: `mnemosyne/embeddings/__init__.py`, `mnemosyne/embeddings/generator.py`
- Test: `tests/test_embeddings.py`

Note: The embeddings table includes `source_hash` (added during design review) to track which content_text_hash was used when the embedding was generated.

- [ ] **Step 1: Create tests/test_embeddings.py with failing tests**

```python
import numpy as np
from unittest.mock import MagicMock
import pytest

from mnemosyne.db.connection import get_connection
from mnemosyne.db.schema import create_tables
from mnemosyne.embeddings.generator import generate_embeddings


@pytest.fixture
def db(tmp_path):
    conn = get_connection(str(tmp_path / "test.db"))
    create_tables(conn)
    conn.execute(
        """INSERT INTO posts (id, title, slug, url, content_html, content_text,
        content_text_hash, status, date_published, date_modified, word_count)
        VALUES (1, 'Test', 'test', 'http://test', '<p>test</p>', 'This is test content',
        'abc123', 'publish', '2024-01-01', '2024-01-01', 4)"""
    )
    conn.commit()
    return conn


def _mock_openai_client(embedding_dim=3072):
    client = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.embedding = list(np.random.rand(embedding_dim))
    mock_response = MagicMock()
    mock_response.data = [mock_embedding]
    client.embeddings.create.return_value = mock_response
    return client


def test_generate_creates_embedding(db):
    client = _mock_openai_client()
    generate_embeddings(db, client, model="text-embedding-3-large")

    row = db.execute("SELECT * FROM embeddings WHERE post_id = 1").fetchone()
    assert row is not None
    assert row["model_name"] == "text-embedding-3-large"
    vector = np.frombuffer(row["vector"], dtype=np.float64)
    assert len(vector) == 3072


def test_generate_skips_existing_unchanged(db):
    client = _mock_openai_client()
    generate_embeddings(db, client, model="text-embedding-3-large")

    # Second run — hash unchanged, should skip
    client.embeddings.create.reset_mock()
    generate_embeddings(db, client, model="text-embedding-3-large")
    client.embeddings.create.assert_not_called()


def test_generate_regenerates_on_hash_change(db):
    client = _mock_openai_client()
    generate_embeddings(db, client, model="text-embedding-3-large")

    # Change hash (simulates extract ran after content changed)
    db.execute("UPDATE posts SET content_text_hash = 'new_hash' WHERE id = 1")
    db.commit()

    client.embeddings.create.reset_mock()
    generate_embeddings(db, client, model="text-embedding-3-large")
    assert client.embeddings.create.call_count == 1


def test_generate_skips_posts_without_text(db):
    db.execute(
        """INSERT INTO posts (id, title, slug, url, content_html, status, date_published, date_modified)
        VALUES (2, 'No Text', 'no-text', 'http://test2', '<p>x</p>', 'publish', '2024-01-01', '2024-01-01')"""
    )
    db.commit()

    client = _mock_openai_client()
    generate_embeddings(db, client, model="text-embedding-3-large")

    count = db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    assert count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_embeddings.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Create mnemosyne/embeddings/__init__.py**

```python
```

- [ ] **Step 4: Create mnemosyne/embeddings/generator.py**

```python
import sqlite3
import numpy as np
from datetime import datetime, timezone


def generate_embeddings(
    conn: sqlite3.Connection,
    openai_client,
    model: str = "text-embedding-3-large",
) -> None:
    """Generate embeddings for posts that need them.

    Skips posts where the existing embedding's source_hash matches current content_text_hash.
    """
    posts = conn.execute(
        "SELECT id, content_text, content_text_hash FROM posts "
        "WHERE content_text IS NOT NULL AND content_text_hash IS NOT NULL"
    ).fetchall()

    print(f"Checking {len(posts)} posts for embedding generation...")
    generated = 0

    for post in posts:
        post_id = post["id"]
        text = post["content_text"]
        current_hash = post["content_text_hash"]

        existing = conn.execute(
            "SELECT source_hash FROM embeddings WHERE post_id = ? AND model_name = ?",
            (post_id, model),
        ).fetchone()

        if existing and existing["source_hash"] == current_hash:
            continue

        print(f"Generating embedding for post {post_id}...")
        response = openai_client.embeddings.create(input=text, model=model)
        vector = np.array(response.data[0].embedding, dtype=np.float64)

        conn.execute(
            "INSERT OR REPLACE INTO embeddings (post_id, model_name, vector, source_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (post_id, model, vector.tobytes(), current_hash, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        generated += 1

    print(f"Generated {generated} new embeddings.")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_embeddings.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add mnemosyne/embeddings/ tests/test_embeddings.py
git commit -m "feat: embedding generation with hash-based invalidation"
```

---

## Task 9: CLI entry point

**Files:**
- Create: `mnemosyne/__main__.py`

- [ ] **Step 1: Create mnemosyne/__main__.py**

```python
import sys

from mnemosyne.db.connection import get_connection
from mnemosyne.db.schema import create_tables


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m mnemosyne <command>")
        print("Commands: sync, extract, embeddings")
        sys.exit(1)

    command = sys.argv[1]

    # Late imports to avoid loading config (and requiring .env) at import time
    from mnemosyne import config

    conn = get_connection(config.get_db_path())
    create_tables(conn)

    try:
        if command == "sync":
            from mnemosyne.scraper.wp_client import WPClient
            from mnemosyne.scraper.sync import sync_all

            client = WPClient(
                base_url=config.get_wp_base_url(),
                username=config.get_wp_username(),
                app_password=config.get_wp_app_password(),
                retry_max=config.get_retry_max(),
            )
            sync_all(conn, client, delay=config.get_sync_delay())

        elif command == "extract":
            from mnemosyne.scraper.extract import extract_all
            from urllib.parse import urlparse

            domain = urlparse(config.get_wp_base_url()).netloc
            extract_all(conn, site_domain=domain)

        elif command == "embeddings":
            from openai import OpenAI
            from mnemosyne.embeddings.generator import generate_embeddings

            client = OpenAI(api_key=config.get_openai_api_key())
            generate_embeddings(conn, client)

        else:
            print(f"Unknown command: {command}")
            print("Commands: sync, extract, embeddings")
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add mnemosyne/__main__.py
git commit -m "feat: CLI entry point for sync, extract, embeddings commands"
```

---

## Task 10: Integration test with real .env

**This task is manual — requires the user to provide credentials.**

- [ ] **Step 1: User creates .env with real credentials**

```bash
cp .env.example .env
# Edit .env with real values
```

- [ ] **Step 2: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 3: Run all unit tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Run sync**

```bash
python -m mnemosyne sync
```

Expected: Downloads ~190 posts one by one with 1s delay, ~3 minutes total.

- [ ] **Step 5: Run extract**

```bash
python -m mnemosyne extract
```

Expected: Extracts text, headings, internal/external links for all posts. Fast (seconds).

- [ ] **Step 6: Verify data in SQLite**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/maria_luigia.db')
for table in ['posts', 'categories', 'tags', 'internal_links', 'external_links', 'headings']:
    count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'{table}: {count} rows')
conn.close()
"
```

- [ ] **Step 7: Commit any fixes**

```bash
git add -A
git commit -m "fix: integration adjustments after first real sync"
```
