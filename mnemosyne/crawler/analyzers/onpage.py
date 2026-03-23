"""Analyzer: SEO on-page checks (title, meta, H1, headings, canonical, OG, schema)."""

from __future__ import annotations

import html
import json
import re

from bs4 import BeautifulSoup

from .http_check import CrawlIssue


def check_title(url: str, soup: BeautifulSoup) -> tuple[str | None, list[CrawlIssue]]:
    """Check <title> tag. Returns (title_text, issues)."""
    issues = []
    title_tag = soup.find("title")
    if not title_tag:
        issues.append(CrawlIssue(
            category="onpage", severity="critical", check_name="missing_title",
            message=f"Title tag mancante: {url}",
        ))
        return None, issues

    title = html.unescape(title_tag.get_text(strip=True))
    if not title:
        issues.append(CrawlIssue(
            category="onpage", severity="critical", check_name="empty_title",
            message=f"Title tag vuoto: {url}",
        ))
        return "", issues

    if len(title) > 60:
        issues.append(CrawlIssue(
            category="onpage", severity="warning", check_name="title_too_long",
            message=f"Title troppo lungo ({len(title)} ch): {url}",
        ))
    elif len(title) < 30:
        issues.append(CrawlIssue(
            category="onpage", severity="warning", check_name="title_too_short",
            message=f"Title troppo corto ({len(title)} ch): {url}",
        ))

    return title, issues


def check_meta_description(url: str, soup: BeautifulSoup) -> tuple[str | None, list[CrawlIssue]]:
    """Check meta description. Returns (description_text, issues)."""
    issues = []
    meta = soup.find("meta", attrs={"name": "description"})
    if not meta:
        issues.append(CrawlIssue(
            category="onpage", severity="warning", check_name="missing_meta_description",
            message=f"Meta description mancante: {url}",
        ))
        return None, issues

    content = html.unescape(meta.get("content", "").strip())
    if not content:
        issues.append(CrawlIssue(
            category="onpage", severity="warning", check_name="empty_meta_description",
            message=f"Meta description vuota: {url}",
        ))
        return "", issues

    if len(content) > 160:
        issues.append(CrawlIssue(
            category="onpage", severity="warning", check_name="meta_description_too_long",
            message=f"Meta description troppo lunga ({len(content)} ch): {url}",
        ))
    elif len(content) < 70:
        issues.append(CrawlIssue(
            category="onpage", severity="info", check_name="meta_description_too_short",
            message=f"Meta description troppo corta ({len(content)} ch): {url}",
        ))

    return content, issues


def check_h1(url: str, soup: BeautifulSoup) -> tuple[int, str | None, list[CrawlIssue]]:
    """Check H1 tags. Returns (h1_count, first_h1_text, issues)."""
    issues = []
    h1s = soup.find_all("h1")
    count = len(h1s)

    if count == 0:
        issues.append(CrawlIssue(
            category="onpage", severity="critical", check_name="missing_h1",
            message=f"H1 mancante: {url}",
        ))
        return 0, None, issues

    first_text = html.unescape(h1s[0].get_text(strip=True))
    if not first_text:
        issues.append(CrawlIssue(
            category="onpage", severity="warning", check_name="empty_h1",
            message=f"H1 vuoto: {url}",
        ))

    if count > 1:
        issues.append(CrawlIssue(
            category="onpage", severity="warning", check_name="multiple_h1",
            message=f"H1 multipli ({count}): {url}",
        ))

    return count, first_text, issues


def check_headings_structure(url: str, soup: BeautifulSoup) -> list[CrawlIssue]:
    """Check heading hierarchy for level skips."""
    issues = []
    headings = soup.find_all(re.compile(r"^h[1-6]$"))
    levels = [int(h.name[1]) for h in headings]

    for i in range(1, len(levels)):
        if levels[i] > levels[i - 1] + 1:
            issues.append(CrawlIssue(
                category="onpage", severity="warning", check_name="heading_skip",
                message=f"Salto di heading H{levels[i-1]}→H{levels[i]}: {url}",
            ))
            break  # Report only once per page

    return issues


def check_canonical(url: str, soup: BeautifulSoup) -> tuple[str | None, list[CrawlIssue]]:
    """Check canonical tag. Returns (canonical_url, issues)."""
    issues = []
    link = soup.find("link", attrs={"rel": "canonical"})
    if not link:
        issues.append(CrawlIssue(
            category="onpage", severity="warning", check_name="missing_canonical",
            message=f"Canonical tag mancante: {url}",
        ))
        return None, issues

    canonical = link.get("href", "").strip()
    if canonical and canonical != url:
        # Not self-referencing — could be intentional or a problem
        issues.append(CrawlIssue(
            category="onpage", severity="info", check_name="canonical_mismatch",
            message=f"Canonical punta a URL diverso: {canonical} (pagina: {url})",
        ))

    return canonical, issues


def check_meta_robots(url: str, soup: BeautifulSoup) -> tuple[str | None, list[CrawlIssue]]:
    """Check meta robots for noindex/nofollow. Returns (robots_content, issues)."""
    issues = []
    meta = soup.find("meta", attrs={"name": "robots"})
    if not meta:
        return None, issues

    content = meta.get("content", "").strip().lower()
    if "noindex" in content:
        issues.append(CrawlIssue(
            category="onpage", severity="critical", check_name="noindex",
            message=f"Pagina con noindex: {url}",
        ))
    if "nofollow" in content:
        issues.append(CrawlIssue(
            category="onpage", severity="warning", check_name="nofollow",
            message=f"Pagina con nofollow: {url}",
        ))

    return content, issues


def check_og_tags(url: str, soup: BeautifulSoup) -> tuple[dict[str, bool], list[CrawlIssue]]:
    """Check Open Graph tags. Returns (og_presence_dict, issues)."""
    issues = []
    og = {
        "og:title": bool(soup.find("meta", attrs={"property": "og:title"})),
        "og:description": bool(soup.find("meta", attrs={"property": "og:description"})),
        "og:image": bool(soup.find("meta", attrs={"property": "og:image"})),
    }
    missing = [k for k, v in og.items() if not v]
    if missing:
        issues.append(CrawlIssue(
            category="onpage", severity="info", check_name="missing_og_tags",
            message=f"OG tag mancanti ({', '.join(missing)}): {url}",
        ))
    return og, issues


def _extract_types(data, types: list) -> None:
    """Recursively extract @type from JSON-LD, including Yoast @graph format."""
    if isinstance(data, dict):
        t = data.get("@type")
        if t:
            if isinstance(t, str):
                types.append(t)
            elif isinstance(t, list):
                types.extend(t)
        # Yoast uses @graph array
        if "@graph" in data:
            for item in data["@graph"]:
                _extract_types(item, types)
    elif isinstance(data, list):
        for item in data:
            _extract_types(item, types)


def check_schema_jsonld(url: str, soup: BeautifulSoup) -> tuple[list[str], list[CrawlIssue]]:
    """Check JSON-LD structured data. Returns (schema_types, issues)."""
    issues = []
    types = []
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for script in scripts:
        try:
            data = json.loads(script.string or "")
            _extract_types(data, types)
        except (json.JSONDecodeError, AttributeError):
            pass

    if not types:
        issues.append(CrawlIssue(
            category="onpage", severity="info", check_name="no_schema_jsonld",
            message=f"Nessun JSON-LD trovato: {url}",
        ))

    return types, issues


def analyze_onpage(url: str, html: bytes) -> dict:
    """Run all on-page checks. Returns dict with extracted data and issues."""
    soup = BeautifulSoup(html, "html.parser")
    all_issues: list[CrawlIssue] = []

    title, issues = check_title(url, soup)
    all_issues.extend(issues)

    meta_desc, issues = check_meta_description(url, soup)
    all_issues.extend(issues)

    h1_count, h1_text, issues = check_h1(url, soup)
    all_issues.extend(issues)

    all_issues.extend(check_headings_structure(url, soup))

    canonical, issues = check_canonical(url, soup)
    all_issues.extend(issues)

    meta_robots, issues = check_meta_robots(url, soup)
    all_issues.extend(issues)

    og, issues = check_og_tags(url, soup)
    all_issues.extend(issues)

    schema_types, issues = check_schema_jsonld(url, soup)
    all_issues.extend(issues)

    # Content stats
    body = soup.find("body")
    text = body.get_text(separator=" ", strip=True) if body else ""
    word_count = len(text.split())
    html_size = len(html)
    text_ratio = len(text.encode()) / html_size if html_size > 0 else 0

    # Images
    imgs = soup.find_all("img")
    img_no_alt = sum(1 for img in imgs if not img.get("alt", "").strip())

    # Links
    links = soup.find_all("a", href=True)
    internal = 0
    external = 0
    from urllib.parse import urlparse
    page_domain = urlparse(url).netloc
    for a in links:
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        parsed = urlparse(href)
        if not parsed.netloc or parsed.netloc == page_domain or parsed.netloc.endswith("." + page_domain):
            internal += 1
        else:
            external += 1

    return {
        "title": title,
        "meta_description": meta_desc,
        "meta_robots": meta_robots,
        "canonical_url": canonical,
        "h1_count": h1_count,
        "h1_text": h1_text,
        "word_count": word_count,
        "html_size": html_size,
        "text_ratio": round(text_ratio, 4),
        "has_og_title": int(og.get("og:title", False)),
        "has_og_description": int(og.get("og:description", False)),
        "has_og_image": int(og.get("og:image", False)),
        "has_schema_json_ld": int(bool(schema_types)),
        "schema_types": json.dumps(schema_types) if schema_types else None,
        "img_total": len(imgs),
        "img_no_alt": img_no_alt,
        "internal_links_count": internal,
        "external_links_count": external,
        "issues": all_issues,
    }
