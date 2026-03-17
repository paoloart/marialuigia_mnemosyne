import sqlite3
from urllib.parse import urlparse


def match_url_to_post(conn: sqlite3.Connection, url: str) -> dict | None:
    """Match a URL (e.g. from GSC) to a post in the local DB.

    Strategy:
    1. Exact match on posts.url
    2. Extract slug from URL path, match on posts.slug
    3. Normalize www/non-www and trailing slash, retry exact match
    """
    # 1. Exact match
    row = conn.execute("SELECT id, title, slug, url, word_count FROM posts WHERE url = ?", (url,)).fetchone()
    if row:
        return dict(row)

    # 2. Slug match
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if path:
        slug = path.split("/")[-1]
        if slug:
            row = conn.execute(
                "SELECT id, title, slug, url, word_count FROM posts WHERE slug = ?", (slug,)
            ).fetchone()
            if row:
                return dict(row)

    # 3. Normalize www and trailing slash
    normalized = url.rstrip("/")
    for variant in [
        normalized,
        normalized + "/",
        normalized.replace("://www.", "://"),
        normalized.replace("://", "://www."),
    ]:
        if variant != url:
            row = conn.execute(
                "SELECT id, title, slug, url, word_count FROM posts WHERE url = ?", (variant,)
            ).fetchone()
            if row:
                return dict(row)

    return None
