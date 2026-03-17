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
            None,
            None,
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
