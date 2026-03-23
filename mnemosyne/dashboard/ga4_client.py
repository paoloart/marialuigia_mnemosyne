"""Synchronous GA4 Data API client using google-analytics-data library."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
)
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def _build_client(creds_path: str) -> BetaAnalyticsDataClient:
    credentials = Credentials.from_service_account_file(creds_path, scopes=_SCOPES)
    return BetaAnalyticsDataClient(credentials=credentials)


def _date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _pct_delta(current: float, previous: float) -> float:
    """Return percentage change from previous to current."""
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return round((current - previous) / previous * 100, 2)


def get_overview(
    creds_path: str,
    property_id: str = "281919772",
    days: int = 7,
) -> dict:
    """Return users, sessions, pageviews with delta vs previous period.

    Returns dict with keys: users, sessions, pageviews — each containing
    "value" (int) and "delta" (percentage change vs previous period).
    """
    try:
        client = _build_client(creds_path)

        today = date.today()
        current_start = today - timedelta(days=days)
        previous_start = current_start - timedelta(days=days)
        previous_end = current_start - timedelta(days=1)

        request = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[
                DateRange(
                    start_date=_date_str(current_start),
                    end_date=_date_str(today),
                ),
                DateRange(
                    start_date=_date_str(previous_start),
                    end_date=_date_str(previous_end),
                ),
            ],
            metrics=[
                Metric(name="activeUsers"),
                Metric(name="sessions"),
                Metric(name="screenPageViews"),
            ],
        )

        response = client.run_report(request)

        # With two date ranges and no dimensions the response contains
        # two rows: index 0 = current period, index 1 = previous period.
        current_row = response.rows[0] if len(response.rows) > 0 else None
        previous_row = response.rows[1] if len(response.rows) > 1 else None

        def _val(row, idx: int) -> int:
            if row is None:
                return 0
            return int(row.metric_values[idx].value)

        metric_keys = ["users", "sessions", "pageviews"]
        result: dict = {}
        for i, key in enumerate(metric_keys):
            cur = _val(current_row, i)
            prev = _val(previous_row, i)
            result[key] = {"value": cur, "delta": _pct_delta(cur, prev)}

        return result

    except Exception:
        logger.exception("GA4 get_overview failed")
        return {}


def get_top_pages(
    creds_path: str,
    property_id: str = "281919772",
    days: int = 7,
    limit: int = 20,
) -> list[dict]:
    """Return top pages ordered by pageviews desc.

    Each dict contains: page_path, pageviews, users.
    """
    try:
        client = _build_client(creds_path)

        today = date.today()
        start = today - timedelta(days=days)

        request = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[
                DateRange(
                    start_date=_date_str(start),
                    end_date=_date_str(today),
                ),
            ],
            dimensions=[Dimension(name="pagePath")],
            metrics=[
                Metric(name="screenPageViews"),
                Metric(name="activeUsers"),
            ],
            limit=limit,
            order_bys=[
                {
                    "metric": {"metric_name": "screenPageViews"},
                    "desc": True,
                }
            ],
        )

        response = client.run_report(request)

        pages: list[dict] = []
        for row in response.rows:
            pages.append(
                {
                    "page_path": row.dimension_values[0].value,
                    "pageviews": int(row.metric_values[0].value),
                    "users": int(row.metric_values[1].value),
                }
            )

        return pages

    except Exception:
        logger.exception("GA4 get_top_pages failed")
        return []
