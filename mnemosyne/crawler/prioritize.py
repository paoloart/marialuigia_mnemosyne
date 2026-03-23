"""Prioritizzazione issue del crawl con dati GSC (click/impressioni)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass
class PrioritizedIssue:
    url: str
    category: str
    severity: str
    check_name: str
    message: str
    clicks: int = 0
    impressions: int = 0
    impact_score: float = 0.0


def prioritize_issues(
    conn: sqlite3.Connection,
    run_id: int,
    gsc_page_data: list[dict],
) -> list[PrioritizedIssue]:
    """Cross-reference crawl issues with GSC traffic data.

    gsc_page_data: list of dicts with keys: page, clicks, impressions, ctr, position
    (as returned by gsc_client.get_top_pages)

    Returns issues sorted by impact_score descending.
    """
    # Build URL→traffic map (normalize trailing slash)
    traffic: dict[str, dict] = {}
    for row in gsc_page_data:
        url = row["page"].rstrip("/")
        traffic[url] = row
        # Also store with trailing slash
        traffic[url + "/"] = row

    # Get all issues for this run
    issues = conn.execute(
        """SELECT url, category, severity, check_name, message
           FROM crawl_issues WHERE run_id = ?""",
        (run_id,),
    ).fetchall()

    # Severity weights
    severity_weight = {"critical": 3.0, "warning": 1.5, "info": 0.5}

    prioritized = []
    for url, category, severity, check_name, message in issues:
        # Match with GSC data
        t = traffic.get(url) or traffic.get(url.rstrip("/")) or traffic.get(url.rstrip("/") + "/")
        clicks = t["clicks"] if t else 0
        impressions = t["impressions"] if t else 0

        # Impact = severity_weight * log(1 + clicks) + log(1 + impressions) * 0.3
        import math
        sw = severity_weight.get(severity, 1.0)
        impact = sw * math.log1p(clicks) + math.log1p(impressions) * 0.3

        prioritized.append(PrioritizedIssue(
            url=url,
            category=category,
            severity=severity,
            check_name=check_name,
            message=message,
            clicks=clicks,
            impressions=impressions,
            impact_score=round(impact, 2),
        ))

    # Sort by impact descending
    prioritized.sort(key=lambda x: x.impact_score, reverse=True)
    return prioritized


def print_prioritized(issues: list[PrioritizedIssue], limit: int = 30) -> None:
    """Print prioritized issues to CLI."""
    print(f"\n{'='*70}")
    print(f"ISSUE PRIORITIZZATI PER IMPATTO (top {limit})")
    print(f"{'='*70}")
    print(f"{'Impact':>7}  {'Sev':>8}  {'Click':>6}  {'Impr':>7}  Check / URL")
    print(f"{'-'*70}")

    for issue in issues[:limit]:
        print(
            f"{issue.impact_score:>7.1f}  "
            f"{issue.severity.upper():>8}  "
            f"{issue.clicks:>6}  "
            f"{issue.impressions:>7}  "
            f"[{issue.check_name}] {issue.url[:50]}"
        )

    remaining = len(issues) - limit
    if remaining > 0:
        print(f"\n... e altri {remaining} issue.")
