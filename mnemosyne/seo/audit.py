import sqlite3


def posts_summary(conn: sqlite3.Connection) -> list[dict]:
    """Summary table of all posts with key metrics."""
    rows = conn.execute("""
        SELECT p.id, p.title, p.slug, p.url, p.word_count, p.meta_description,
               p.embedding_status, p.date_published,
               (SELECT COUNT(*) FROM headings h WHERE h.post_id = p.id) as heading_count,
               (SELECT COUNT(*) FROM internal_links il WHERE il.source_post_id = p.id) as outgoing_links,
               (SELECT COUNT(*) FROM internal_links il WHERE il.target_post_id = p.id) as incoming_links,
               (SELECT COUNT(*) FROM external_links el WHERE el.source_post_id = p.id) as external_links
        FROM posts p
        ORDER BY p.word_count DESC
    """).fetchall()
    return [dict(r) for r in rows]


def posts_missing_meta(conn: sqlite3.Connection) -> list[dict]:
    """Posts without meta_description."""
    rows = conn.execute(
        "SELECT id, title, slug, url, word_count FROM posts "
        "WHERE meta_description IS NULL OR meta_description = '' "
        "ORDER BY word_count DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def posts_thin_content(conn: sqlite3.Connection, min_words: int = 500) -> list[dict]:
    """Posts with word_count below threshold."""
    rows = conn.execute(
        "SELECT id, title, slug, url, word_count FROM posts "
        "WHERE word_count < ? ORDER BY word_count ASC",
        (min_words,)
    ).fetchall()
    return [dict(r) for r in rows]


def posts_no_internal_links(conn: sqlite3.Connection) -> list[dict]:
    """Posts with no outgoing internal links (orphan content)."""
    rows = conn.execute("""
        SELECT p.id, p.title, p.slug, p.url, p.word_count
        FROM posts p
        WHERE p.id NOT IN (SELECT DISTINCT source_post_id FROM internal_links)
        ORDER BY p.word_count DESC
    """).fetchall()
    return [dict(r) for r in rows]


def posts_no_inbound_links(conn: sqlite3.Connection) -> list[dict]:
    """Posts that no other post links to (dead ends)."""
    rows = conn.execute("""
        SELECT p.id, p.title, p.slug, p.url, p.word_count
        FROM posts p
        WHERE p.id NOT IN (
            SELECT DISTINCT target_post_id FROM internal_links
            WHERE target_post_id IS NOT NULL
        )
        ORDER BY p.word_count DESC
    """).fetchall()
    return [dict(r) for r in rows]


def heading_issues(conn: sqlite3.Connection) -> list[dict]:
    """Posts with heading structure problems."""
    results = []

    # Posts with no H2 at all
    no_h2 = conn.execute("""
        SELECT p.id, p.title, p.slug, p.word_count
        FROM posts p
        WHERE p.id NOT IN (SELECT DISTINCT post_id FROM headings WHERE level = 2)
        AND p.word_count > 200
    """).fetchall()
    for r in no_h2:
        results.append({**dict(r), "issue": "no H2 headings"})

    # Posts with heading level jumps (e.g. H2 -> H4)
    posts_with_headings = conn.execute("""
        SELECT DISTINCT post_id FROM headings
    """).fetchall()

    for post_row in posts_with_headings:
        post_id = post_row[0]
        headings = conn.execute(
            "SELECT level FROM headings WHERE post_id = ? ORDER BY position",
            (post_id,)
        ).fetchall()
        levels = [h[0] for h in headings]

        has_jump = False
        for i in range(1, len(levels)):
            if levels[i] > levels[i-1] + 1:
                has_jump = True
                break

        if has_jump:
            post = conn.execute(
                "SELECT id, title, slug, word_count FROM posts WHERE id = ?",
                (post_id,)
            ).fetchone()
            if post:
                results.append({**dict(post), "issue": f"heading level jump: {' -> '.join(f'H{l}' for l in levels)}"})

    return results


def embedding_status_report(conn: sqlite3.Connection) -> dict:
    """Count posts by embedding status."""
    result = {}
    for status in ["current", "pending"]:
        count = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE embedding_status = ?", (status,)
        ).fetchone()[0]
        result[status] = count

    null_count = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE embedding_status IS NULL"
    ).fetchone()[0]
    result["not_generated"] = null_count
    result["total"] = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    return result


def print_table(rows: list[dict], columns: list[str] | None = None, max_width: int = 60) -> None:
    """Print a list of dicts as a formatted table."""
    if not rows:
        print("  (nessun risultato)")
        return

    if columns is None:
        columns = list(rows[0].keys())

    # Calculate column widths
    widths = {}
    for col in columns:
        values = [str(r.get(col, ""))[:max_width] for r in rows]
        widths[col] = max(len(col), max(len(v) for v in values))

    # Header
    header = " | ".join(col.ljust(widths[col]) for col in columns)
    print(header)
    print("-" * len(header))

    # Rows
    for r in rows:
        line = " | ".join(str(r.get(col, ""))[:max_width].ljust(widths[col]) for col in columns)
        print(line)
