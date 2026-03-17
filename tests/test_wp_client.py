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
