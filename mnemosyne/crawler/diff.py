"""Confronto tra due crawl run: issue nuovi, risolti, metriche cambiate."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class CrawlDiff:
    run_old: int
    run_new: int
    new_issues: list[dict] = field(default_factory=list)       # issue presenti in new ma non in old
    resolved_issues: list[dict] = field(default_factory=list)  # issue presenti in old ma non in new
    new_pages: list[str] = field(default_factory=list)         # URL in new ma non in old
    removed_pages: list[str] = field(default_factory=list)     # URL in old ma non in new
    status_changes: list[dict] = field(default_factory=list)   # pagine con status code cambiato
    score_old: float = 0.0
    score_new: float = 0.0


def compare_runs(conn: sqlite3.Connection, old_id: int, new_id: int) -> CrawlDiff:
    """Compare two crawl runs and return a CrawlDiff."""
    diff = CrawlDiff(run_old=old_id, run_new=new_id)

    # Health scores
    diff.score_old = _health_score(conn, old_id)
    diff.score_new = _health_score(conn, new_id)

    # Pages: new and removed
    old_urls = {r[0] for r in conn.execute(
        "SELECT url FROM crawl_pages WHERE run_id = ?", (old_id,)
    ).fetchall()}
    new_urls = {r[0] for r in conn.execute(
        "SELECT url FROM crawl_pages WHERE run_id = ?", (new_id,)
    ).fetchall()}

    diff.new_pages = sorted(new_urls - old_urls)
    diff.removed_pages = sorted(old_urls - new_urls)

    # Status code changes for pages in both runs
    common_urls = old_urls & new_urls
    if common_urls:
        old_status = {r[0]: r[1] for r in conn.execute(
            "SELECT url, status_code FROM crawl_pages WHERE run_id = ?", (old_id,)
        ).fetchall()}
        new_status = {r[0]: r[1] for r in conn.execute(
            "SELECT url, status_code FROM crawl_pages WHERE run_id = ?", (new_id,)
        ).fetchall()}
        for url in common_urls:
            if old_status.get(url) != new_status.get(url):
                diff.status_changes.append({
                    "url": url,
                    "old_status": old_status.get(url),
                    "new_status": new_status.get(url),
                })

    # Issues: compare by (url, check_name) fingerprint
    old_issues = _issue_fingerprints(conn, old_id)
    new_issues = _issue_fingerprints(conn, new_id)

    old_fps = {(i["url"], i["check_name"]) for i in old_issues}
    new_fps = {(i["url"], i["check_name"]) for i in new_issues}

    # New issues = in new but not in old
    added_fps = new_fps - old_fps
    diff.new_issues = [i for i in new_issues if (i["url"], i["check_name"]) in added_fps]

    # Resolved issues = in old but not in new
    resolved_fps = old_fps - new_fps
    diff.resolved_issues = [i for i in old_issues if (i["url"], i["check_name"]) in resolved_fps]

    return diff


def _issue_fingerprints(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT url, category, severity, check_name, message FROM crawl_issues WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    return [{"url": r[0], "category": r[1], "severity": r[2], "check_name": r[3], "message": r[4]} for r in rows]


def _health_score(conn: sqlite3.Connection, run_id: int) -> float:
    total = conn.execute("SELECT COUNT(*) FROM crawl_pages WHERE run_id = ?", (run_id,)).fetchone()[0]
    if total == 0:
        return 100.0
    with_critical = conn.execute(
        "SELECT COUNT(DISTINCT page_id) FROM crawl_issues WHERE run_id = ? AND severity = 'critical'",
        (run_id,),
    ).fetchone()[0]
    return round(((total - with_critical) / total) * 100, 1)


def print_diff(diff: CrawlDiff) -> None:
    """Print diff to CLI."""
    print(f"\n{'='*55}")
    print(f"CONFRONTO CRAWL — Run #{diff.run_old} → #{diff.run_new}")
    print(f"{'='*55}")

    # Health score
    delta = diff.score_new - diff.score_old
    arrow = "+" if delta > 0 else ""
    print(f"\nHealth Score: {diff.score_old:.1f}% → {diff.score_new:.1f}% ({arrow}{delta:.1f}pp)")

    # New/removed pages
    if diff.new_pages:
        print(f"\n--- NUOVE PAGINE ({len(diff.new_pages)}) ---")
        for url in diff.new_pages[:10]:
            print(f"  + {url}")
        if len(diff.new_pages) > 10:
            print(f"  ... e altre {len(diff.new_pages) - 10}")

    if diff.removed_pages:
        print(f"\n--- PAGINE RIMOSSE ({len(diff.removed_pages)}) ---")
        for url in diff.removed_pages[:10]:
            print(f"  - {url}")

    # Status changes
    if diff.status_changes:
        print(f"\n--- STATUS CODE CAMBIATI ({len(diff.status_changes)}) ---")
        for ch in diff.status_changes[:15]:
            print(f"  {ch['url']}: {ch['old_status']} → {ch['new_status']}")

    # New issues
    if diff.new_issues:
        print(f"\n--- NUOVI ISSUE ({len(diff.new_issues)}) ---")
        for i in diff.new_issues[:15]:
            print(f"  [{i['severity'].upper():>8}] [{i['check_name']}] {i['message'][:80]}")
        if len(diff.new_issues) > 15:
            print(f"  ... e altri {len(diff.new_issues) - 15}")

    # Resolved issues
    if diff.resolved_issues:
        print(f"\n--- ISSUE RISOLTI ({len(diff.resolved_issues)}) ---")
        for i in diff.resolved_issues[:15]:
            print(f"  [{i['severity'].upper():>8}] [{i['check_name']}] {i['message'][:80]}")
        if len(diff.resolved_issues) > 15:
            print(f"  ... e altri {len(diff.resolved_issues) - 15}")

    if not diff.new_issues and not diff.resolved_issues and not diff.status_changes:
        print("\nNessun cambiamento significativo tra i due crawl.")
