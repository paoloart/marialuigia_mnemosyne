"""Synchronous Google Search Console API client."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
DEFAULT_SITE = "https://www.ospedalemarialuigia.it/"


def _build_service(creds_path: str):
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return build("searchconsole", "v1", credentials=creds)


def _date_ranges(days: int) -> tuple[str, str, str, str]:
    """Return (cur_start, cur_end, prev_start, prev_end) as ISO strings."""
    today = date.today()
    # GSC data has ~3-day lag
    cur_end = today - timedelta(days=3)
    cur_start = cur_end - timedelta(days=days - 1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return (
        cur_start.isoformat(),
        cur_end.isoformat(),
        prev_start.isoformat(),
        prev_end.isoformat(),
    )


def _delta(current: float, previous: float) -> float | None:
    """Percentage change from previous to current. None if previous is zero."""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


# ── Public API ────────────────────────────────────────────────────────


def get_overview(
    creds_path: str,
    site_url: str = DEFAULT_SITE,
    days: int = 7,
) -> dict:
    """Totals for clicks/impressions/ctr/position with delta vs previous period."""
    try:
        service = _build_service(creds_path)
        cur_start, cur_end, prev_start, prev_end = _date_ranges(days)

        cur_resp = (
            service.searchanalytics()
            .query(
                siteUrl=site_url,
                body={
                    "startDate": cur_start,
                    "endDate": cur_end,
                },
            )
            .execute()
        )

        prev_resp = (
            service.searchanalytics()
            .query(
                siteUrl=site_url,
                body={
                    "startDate": prev_start,
                    "endDate": prev_end,
                },
            )
            .execute()
        )

        cur_rows = cur_resp.get("rows", [{}])
        prev_rows = prev_resp.get("rows", [{}])

        cur = cur_rows[0] if cur_rows else {}
        prev = prev_rows[0] if prev_rows else {}

        result = {}
        for key in ("clicks", "impressions", "ctr", "position"):
            c_val = cur.get(key, 0)
            p_val = prev.get(key, 0)
            result[key] = {"value": c_val, "delta": _delta(c_val, p_val)}

        return result

    except Exception:
        logger.exception("Failed to fetch GSC overview")
        return {}


def get_top_queries(
    creds_path: str,
    site_url: str = DEFAULT_SITE,
    days: int = 28,
    limit: int = 30,
) -> list[dict]:
    """Top queries by clicks."""
    try:
        service = _build_service(creds_path)
        cur_start, cur_end, _, _ = _date_ranges(days)

        resp = (
            service.searchanalytics()
            .query(
                siteUrl=site_url,
                body={
                    "startDate": cur_start,
                    "endDate": cur_end,
                    "dimensions": ["query"],
                    "rowLimit": limit,
                },
            )
            .execute()
        )

        return [
            {
                "query": row["keys"][0],
                "clicks": row["clicks"],
                "impressions": row["impressions"],
                "ctr": row["ctr"],
                "position": row["position"],
            }
            for row in resp.get("rows", [])
        ]

    except Exception:
        logger.exception("Failed to fetch GSC top queries")
        return []


def get_top_pages(
    creds_path: str,
    site_url: str = DEFAULT_SITE,
    days: int = 28,
    limit: int = 30,
) -> list[dict]:
    """Top pages by clicks."""
    try:
        service = _build_service(creds_path)
        cur_start, cur_end, _, _ = _date_ranges(days)

        resp = (
            service.searchanalytics()
            .query(
                siteUrl=site_url,
                body={
                    "startDate": cur_start,
                    "endDate": cur_end,
                    "dimensions": ["page"],
                    "rowLimit": limit,
                },
            )
            .execute()
        )

        return [
            {
                "page": row["keys"][0],
                "clicks": row["clicks"],
                "impressions": row["impressions"],
                "ctr": row["ctr"],
                "position": row["position"],
            }
            for row in resp.get("rows", [])
        ]

    except Exception:
        logger.exception("Failed to fetch GSC top pages")
        return []
