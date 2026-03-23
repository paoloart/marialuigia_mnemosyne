"""Analyzer: contenuto — thin content, text/HTML ratio."""

from __future__ import annotations

from .http_check import CrawlIssue

THIN_THRESHOLD = 300


def check_thin_content(url: str, word_count: int) -> list[CrawlIssue]:
    """Flag pages with fewer than THIN_THRESHOLD words."""
    issues = []
    if word_count < THIN_THRESHOLD:
        issues.append(CrawlIssue(
            category="content", severity="warning", check_name="thin_content",
            message=f"Contenuto thin ({word_count} parole): {url}",
        ))
    return issues


def check_text_ratio(url: str, text_ratio: float) -> list[CrawlIssue]:
    """Flag pages with very low text/HTML ratio (<10%)."""
    issues = []
    if text_ratio < 0.10:
        pct = round(text_ratio * 100, 1)
        issues.append(CrawlIssue(
            category="content", severity="info", check_name="low_text_ratio",
            message=f"Ratio testo/HTML basso ({pct}%): {url}",
        ))
    return issues
