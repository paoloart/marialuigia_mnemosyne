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
