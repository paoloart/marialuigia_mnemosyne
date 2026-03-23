"""HTTP fetcher concorrente con TTFB tracking e redirect chain."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "MnemosyneBot/1.0 (+ospedalemarialuigia.it)"


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    status_code: int = 0
    redirect_chain: list[tuple[str, int]] = field(default_factory=list)
    ttfb_ms: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    content_type: str = ""
    content_length: int = 0
    error: str | None = None


class SiteFetcher:
    def __init__(self, max_workers: int = 5, delay: float = 0.5, timeout: int = 10):
        self.max_workers = max_workers
        self.delay = delay
        self.timeout = timeout
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        retry = Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def fetch_all(
        self,
        urls: list[str],
        callback: Callable[[int, int], None] | None = None,
    ) -> list[FetchResult]:
        """Fetch all URLs with controlled concurrency."""
        results: list[FetchResult] = []
        done_count = 0
        total = len(urls)

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._fetch_one_with_delay, url): url for url in urls}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                done_count += 1
                if callback:
                    callback(done_count, total)

        return results

    def fetch_head(self, url: str) -> FetchResult:
        """HEAD request for checking link status without downloading body."""
        try:
            t0 = time.monotonic()
            resp = self.session.head(url, allow_redirects=True, timeout=self.timeout)
            ttfb = int((time.monotonic() - t0) * 1000)
            return FetchResult(
                url=url,
                final_url=resp.url,
                status_code=resp.status_code,
                ttfb_ms=ttfb,
                headers=dict(resp.headers),
                content_type=resp.headers.get("Content-Type", ""),
                content_length=int(resp.headers.get("Content-Length", 0)),
            )
        except requests.RequestException as e:
            return FetchResult(url=url, error=str(e))

    def _fetch_one_with_delay(self, url: str) -> FetchResult:
        result = self.fetch_one(url)
        if self.delay > 0:
            time.sleep(self.delay)
        return result

    def fetch_one(self, url: str) -> FetchResult:
        """Fetch a single URL, tracking redirect chain and TTFB."""
        chain: list[tuple[str, int]] = []
        current_url = url

        try:
            # Manual redirect following to track the chain
            for _ in range(10):  # max 10 redirects
                t0 = time.monotonic()
                resp = self.session.get(
                    current_url,
                    allow_redirects=False,
                    timeout=self.timeout,
                    stream=True,
                )
                ttfb = int((time.monotonic() - t0) * 1000)

                if resp.is_redirect:
                    chain.append((current_url, resp.status_code))
                    location = resp.headers.get("Location", "")
                    if not location:
                        break
                    # Handle relative redirects
                    if location.startswith("/"):
                        from urllib.parse import urlparse
                        parsed = urlparse(current_url)
                        location = f"{parsed.scheme}://{parsed.netloc}{location}"
                    current_url = location
                    resp.close()
                    continue

                # Final response — read body
                body = resp.content
                return FetchResult(
                    url=url,
                    final_url=current_url,
                    status_code=resp.status_code,
                    redirect_chain=chain,
                    ttfb_ms=ttfb,
                    headers=dict(resp.headers),
                    body=body,
                    content_type=resp.headers.get("Content-Type", ""),
                    content_length=len(body),
                )

            # Too many redirects
            return FetchResult(
                url=url,
                final_url=current_url,
                status_code=0,
                redirect_chain=chain,
                error="Too many redirects (>10)",
            )

        except requests.RequestException as e:
            return FetchResult(url=url, redirect_chain=chain, error=str(e))
