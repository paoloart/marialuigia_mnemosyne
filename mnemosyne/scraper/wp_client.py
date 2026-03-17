import time
import requests
from requests.auth import HTTPBasicAuth


class WPClient:
    """Client for WordPress REST API."""

    def __init__(self, base_url: str, username: str, app_password: str,
                 retry_max: int = 3):
        self.api_url = f"{base_url.rstrip('/')}/wp-json/wp/v2"
        self.auth = HTTPBasicAuth(username, app_password)
        self.retry_max = retry_max

    def _request(self, url: str, params: dict | None = None) -> requests.Response:
        """Make a GET request with exponential backoff on 429/5xx."""
        for attempt in range(self.retry_max):
            resp = requests.get(url, params=params, auth=self.auth)
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = 2 ** attempt
                print(f"HTTP {resp.status_code}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def get_total_posts(self) -> int:
        """Return total number of posts."""
        resp = self._request(f"{self.api_url}/posts", params={"per_page": 1})
        return int(resp.headers["X-WP-Total"])

    def get_post_ids(self) -> list[int]:
        """Return all post IDs, paginating through results."""
        ids = []
        page = 1
        while True:
            resp = self._request(
                f"{self.api_url}/posts",
                params={"per_page": 100, "page": page, "_fields": "id"},
            )
            posts = resp.json()
            if not posts:
                break
            ids.extend(p["id"] for p in posts)
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1
        return ids

    def get_post(self, post_id: int) -> dict:
        """Fetch a single post by ID."""
        resp = self._request(f"{self.api_url}/posts/{post_id}")
        return resp.json()

    def get_categories(self) -> list[dict]:
        """Fetch all categories."""
        return self._fetch_all(f"{self.api_url}/categories")

    def get_tags(self) -> list[dict]:
        """Fetch all tags."""
        return self._fetch_all(f"{self.api_url}/tags")

    def _fetch_all(self, url: str) -> list[dict]:
        """Fetch all items from a paginated endpoint."""
        items = []
        page = 1
        while True:
            resp = self._request(url, params={"per_page": 100, "page": page})
            data = resp.json()
            if not data:
                break
            items.extend(data)
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1
        return items
