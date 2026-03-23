"""Verifica link esterni: GET request con browser headers su tutti i link esterni di un crawl run."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Headers che simulano un browser reale — riduce i falsi positivi 403
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Publisher che bloccano anche con browser headers (Cloudflare/JS challenge)
# Li marchiamo come "non verificabili" invece di "rotti"
_UNVERIFIABLE_DOMAINS = frozenset([
    # Publisher accademici con Cloudflare/JS challenge
    "journals.sagepub.com",
    "jamanetwork.com",
    "onlinelibrary.wiley.com",
    "www.tandfonline.com",
    # Social network che bloccano bot
    "www.facebook.com",
    "www.instagram.com",
    "it.linkedin.com",
    "www.linkedin.com",
    "www.youtube.com",
    "twitter.com",
    "x.com",
])


def check_external_links(
    conn: sqlite3.Connection,
    run_id: int,
    max_workers: int = 10,
    timeout: int = 15,
    callback=None,
) -> dict:
    """Check all external links from a crawl run.

    Uses GET with browser-like headers to minimize false 403s.
    Returns {"total": N, "ok": N, "broken": N, "unverifiable": N, "errors": N}.
    """
    rows = conn.execute(
        """SELECT DISTINCT target_url FROM crawl_links
           WHERE run_id = ? AND is_internal = 0 AND status_code IS NULL""",
        (run_id,),
    ).fetchall()

    urls = [r[0] for r in rows]
    if not urls:
        return {"total": 0, "ok": 0, "broken": 0, "unverifiable": 0, "errors": 0}

    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)
    retry = Retry(total=1, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    results: dict[str, tuple[int, str | None]] = {}
    done = 0
    total = len(urls)

    def _check_one(url: str) -> tuple[str, int, str | None]:
        try:
            # GET instead of HEAD — many publishers block HEAD
            resp = session.get(url, allow_redirects=True, timeout=timeout, stream=True)
            status = resp.status_code

            # Check if final domain is unverifiable (403 = false positive)
            from urllib.parse import urlparse
            final_domain = urlparse(resp.url).netloc
            if status == 403 and final_domain in _UNVERIFIABLE_DOMAINS:
                # Mark as 200 — we can't verify, but it's likely fine
                return url, -403, None  # -403 = unverifiable

            resp.close()
            return url, status, None
        except requests.RequestException as e:
            return url, 0, str(e)[:200]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_check_one, url): url for url in urls}
        for future in as_completed(futures):
            url, status, error = future.result()
            results[url] = (status, error)
            done += 1
            if callback and done % 20 == 0:
                callback(done, total)

    ok = broken = unverifiable = errors = 0
    for url, (status, error) in results.items():
        if status == -403:
            # Unverifiable — don't mark as broken
            conn.execute(
                """UPDATE crawl_links SET status_code = 200, is_broken = 0
                   WHERE run_id = ? AND target_url = ? AND is_internal = 0""",
                (run_id, url),
            )
            unverifiable += 1
        elif status == 0:
            conn.execute(
                """UPDATE crawl_links SET status_code = 0, is_broken = 1
                   WHERE run_id = ? AND target_url = ? AND is_internal = 0""",
                (run_id, url),
            )
            errors += 1
        elif status >= 400:
            conn.execute(
                """UPDATE crawl_links SET status_code = ?, is_broken = 1
                   WHERE run_id = ? AND target_url = ? AND is_internal = 0""",
                (status, run_id, url),
            )
            broken += 1
        else:
            conn.execute(
                """UPDATE crawl_links SET status_code = ?, is_broken = 0
                   WHERE run_id = ? AND target_url = ? AND is_internal = 0""",
                (status, run_id, url),
            )
            ok += 1

    conn.commit()
    return {"total": total, "ok": ok, "broken": broken, "unverifiable": unverifiable, "errors": errors}


def get_broken_external_links(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    """Get all broken external links with source page info."""
    rows = conn.execute(
        """SELECT cl.target_url, cl.status_code, cl.anchor_text, cp.url as source_url, cp.title as source_title
           FROM crawl_links cl
           JOIN crawl_pages cp ON cl.source_page_id = cp.id
           WHERE cl.run_id = ? AND cl.is_internal = 0 AND cl.is_broken = 1
           ORDER BY cl.status_code, cl.target_url""",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]
