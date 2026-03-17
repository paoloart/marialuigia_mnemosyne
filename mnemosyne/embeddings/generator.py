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
