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
