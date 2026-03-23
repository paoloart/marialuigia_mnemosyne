import json
import sqlite3

import pytest

from mnemosyne.dashboard.chart_store import (
    delete_unpinned,
    ensure_table,
    get_charts,
    get_latest_id,
    insert_chart,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_table(c)
    yield c
    c.close()


def test_ensure_table_idempotent(conn):
    ensure_table(conn)  # second call should not raise
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    assert any(r[0] == "dashboard_charts" for r in tables)


def test_insert_and_get(conn):
    cid = insert_chart(conn, "Test", "markdown", "hello")
    assert cid == 1
    charts = get_charts(conn)
    assert len(charts) == 1
    assert charts[0]["title"] == "Test"
    assert charts[0]["data_json"] == "hello"


def test_insert_dict_data(conn):
    data = {"value": 42, "delta": 5}
    insert_chart(conn, "Metric", "metric", data)
    charts = get_charts(conn)
    assert json.loads(charts[0]["data_json"]) == data


def test_get_latest_id_empty(conn):
    assert get_latest_id(conn) == 0


def test_get_latest_id(conn):
    insert_chart(conn, "A", "markdown", "a")
    insert_chart(conn, "B", "markdown", "b")
    assert get_latest_id(conn) == 2


def test_get_charts_since_id(conn):
    insert_chart(conn, "A", "markdown", "a")
    insert_chart(conn, "B", "markdown", "b")
    charts = get_charts(conn, since_id=1)
    assert len(charts) == 1
    assert charts[0]["title"] == "B"


def test_pinned_charts_first(conn):
    insert_chart(conn, "Normal", "markdown", "x")
    insert_chart(conn, "Pinned", "markdown", "y", pinned=True)
    charts = get_charts(conn)
    assert charts[0]["title"] == "Pinned"


def test_delete_unpinned(conn):
    insert_chart(conn, "Normal", "markdown", "x")
    insert_chart(conn, "Pinned", "markdown", "y", pinned=True)
    deleted = delete_unpinned(conn)
    assert deleted == 1
    charts = get_charts(conn)
    assert len(charts) == 1
    assert charts[0]["title"] == "Pinned"
