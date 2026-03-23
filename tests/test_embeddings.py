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
        """INSERT INTO posts (id, title, slug, url, content_raw, content_text,
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
        """INSERT INTO posts (id, title, slug, url, content_raw, status, date_published, date_modified)
        VALUES (2, 'No Text', 'no-text', 'http://test2', '<p>x</p>', 'publish', '2024-01-01', '2024-01-01')"""
    )
    db.commit()

    client = _mock_openai_client()
    generate_embeddings(db, client, model="text-embedding-3-large")

    count = db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    assert count == 1
