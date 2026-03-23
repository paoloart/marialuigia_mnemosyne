"""Analyzer: link interni/esterni — rotti, anchor vuoti, nofollow interni, redirect."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .http_check import CrawlIssue


@dataclass
class LinkInfo:
    target_url: str
    anchor_text: str
    is_internal: bool
    rel: str | None = None


def extract_links(url: str, soup: BeautifulSoup) -> list[LinkInfo]:
    """Extract all <a> links, classifying as internal or external."""
    page_domain = urlparse(url).netloc
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        # Resolve relative URLs
        resolved = urljoin(url, href)
        anchor = a.get_text(strip=True)
        rel = a.get("rel")
        rel_str = " ".join(rel) if isinstance(rel, list) else rel

        parsed = urlparse(resolved)
        is_internal = (
            not parsed.netloc
            or parsed.netloc == page_domain
            or parsed.netloc.endswith("." + page_domain)
        )

        links.append(LinkInfo(
            target_url=resolved,
            anchor_text=anchor,
            is_internal=is_internal,
            rel=rel_str,
        ))

    return links


def check_empty_anchor(url: str, links: list[LinkInfo]) -> list[CrawlIssue]:
    """Flag links with empty anchor text (no text and no alt on child img)."""
    issues = []
    empty = [lk for lk in links if not lk.anchor_text.strip()]
    if empty:
        issues.append(CrawlIssue(
            category="links", severity="warning", check_name="empty_anchor",
            message=f"{len(empty)} link con anchor vuoto su {url}",
        ))
    return issues


def check_nofollow_internal(url: str, links: list[LinkInfo]) -> list[CrawlIssue]:
    """Flag internal links with rel=nofollow (wasted link juice)."""
    issues = []
    nf = [lk for lk in links if lk.is_internal and lk.rel and "nofollow" in lk.rel]
    if nf:
        for lk in nf:
            issues.append(CrawlIssue(
                category="links", severity="info", check_name="nofollow_internal",
                message=f"Link interno con nofollow: {lk.target_url} su {url}",
            ))
    return issues


def check_broken_link(url: str, link: LinkInfo, status_code: int) -> list[CrawlIssue]:
    """Flag a link whose target returns 4xx/5xx."""
    issues = []
    if status_code >= 400:
        severity = "critical" if link.is_internal else "warning"
        label = "broken_internal_link" if link.is_internal else "broken_external_link"
        issues.append(CrawlIssue(
            category="links", severity=severity, check_name=label,
            message=f"Link rotto ({status_code}): {link.target_url} su {url}",
        ))
    return issues


def check_redirect_link(url: str, link: LinkInfo, status_code: int) -> list[CrawlIssue]:
    """Flag internal links that point to a redirect."""
    issues = []
    if link.is_internal and 300 <= status_code < 400:
        issues.append(CrawlIssue(
            category="links", severity="warning", check_name="redirect_internal_link",
            message=f"Link interno punta a redirect ({status_code}): {link.target_url} su {url}",
        ))
    return issues
