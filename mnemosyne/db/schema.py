import sqlite3

SQL = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    url TEXT NOT NULL,
    content_raw TEXT NOT NULL,
    content_rendered TEXT,
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
    word_count INTEGER,
    embedding_status TEXT DEFAULT NULL
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

CREATE TABLE IF NOT EXISTS dashboard_charts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    chart_type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    pinned INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    sitemap_url TEXT NOT NULL,
    total_urls INTEGER DEFAULT 0,
    crawled_urls INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS crawl_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    status_code INTEGER,
    redirect_url TEXT,
    redirect_chain TEXT,
    ttfb_ms INTEGER,
    content_type TEXT,
    content_length INTEGER,
    title TEXT,
    meta_description TEXT,
    meta_robots TEXT,
    canonical_url TEXT,
    h1_count INTEGER DEFAULT 0,
    h1_text TEXT,
    word_count INTEGER DEFAULT 0,
    html_size INTEGER DEFAULT 0,
    text_ratio REAL,
    has_og_title INTEGER DEFAULT 0,
    has_og_description INTEGER DEFAULT 0,
    has_og_image INTEGER DEFAULT 0,
    has_schema_json_ld INTEGER DEFAULT 0,
    schema_types TEXT,
    img_total INTEGER DEFAULT 0,
    img_no_alt INTEGER DEFAULT 0,
    internal_links_count INTEGER DEFAULT 0,
    external_links_count INTEGER DEFAULT 0,
    crawled_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES crawl_runs(id)
);

CREATE TABLE IF NOT EXISTS crawl_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    page_id INTEGER,
    url TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    check_name TEXT NOT NULL,
    message TEXT NOT NULL,
    details TEXT,
    FOREIGN KEY (run_id) REFERENCES crawl_runs(id),
    FOREIGN KEY (page_id) REFERENCES crawl_pages(id)
);

CREATE TABLE IF NOT EXISTS crawl_duplicates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    urls TEXT NOT NULL,
    count INTEGER NOT NULL,
    FOREIGN KEY (run_id) REFERENCES crawl_runs(id)
);

CREATE TABLE IF NOT EXISTS crawl_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    page_id INTEGER NOT NULL,
    src TEXT NOT NULL,
    alt TEXT,
    status_code INTEGER,
    content_length INTEGER,
    content_type TEXT,
    is_broken INTEGER DEFAULT 0,
    is_missing_alt INTEGER DEFAULT 0,
    is_oversized INTEGER DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES crawl_runs(id),
    FOREIGN KEY (page_id) REFERENCES crawl_pages(id)
);

CREATE TABLE IF NOT EXISTS crawl_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    source_page_id INTEGER NOT NULL,
    target_url TEXT NOT NULL,
    anchor_text TEXT,
    is_internal INTEGER NOT NULL,
    rel TEXT,
    status_code INTEGER,
    is_broken INTEGER DEFAULT 0,
    is_redirect INTEGER DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES crawl_runs(id),
    FOREIGN KEY (source_page_id) REFERENCES crawl_pages(id)
);

CREATE TABLE IF NOT EXISTS plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_key TEXT NOT NULL UNIQUE,
    done INTEGER DEFAULT 0,
    done_at TEXT
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'media',
    post_id INTEGER,
    post_title TEXT,
    post_url TEXT,
    target_post_id INTEGER,
    target_title TEXT,
    target_url TEXT,
    reason TEXT NOT NULL,
    data_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    dismissed_at TEXT,
    FOREIGN KEY (post_id) REFERENCES posts(id),
    FOREIGN KEY (target_post_id) REFERENCES posts(id)
);
"""


MIGRATIONS = [
    # Rename content_html -> content_raw, add content_rendered
    """
    ALTER TABLE posts RENAME COLUMN content_html TO content_raw;
    """,
    """
    ALTER TABLE posts ADD COLUMN content_rendered TEXT;
    """,
    """
    ALTER TABLE posts ADD COLUMN embedding_status TEXT DEFAULT NULL;
    """,
    """
    ALTER TABLE posts ADD COLUMN yoast_title TEXT;
    """,
    """
    ALTER TABLE posts ADD COLUMN yoast_metadesc TEXT;
    """,
    """
    ALTER TABLE posts ADD COLUMN is_pillar INTEGER DEFAULT 0;
    """,
]


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all database tables and run migrations."""
    conn.executescript(SQL)
    for migration in MIGRATIONS:
        try:
            conn.executescript(migration)
        except Exception:
            pass  # Already applied
