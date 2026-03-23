"""Analyzer: risorse — mixed content, CSS/JS render-blocking."""

from __future__ import annotations

from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .http_check import CrawlIssue


def check_mixed_content(url: str, soup: BeautifulSoup) -> list[CrawlIssue]:
    """Flag HTTP resources loaded on HTTPS pages."""
    issues = []
    if not url.startswith("https://"):
        return issues

    http_resources = []

    # Check img, script, link[stylesheet], iframe, video, audio, source
    for tag_name, attr in [
        ("img", "src"), ("script", "src"), ("iframe", "src"),
        ("video", "src"), ("audio", "src"), ("source", "src"),
    ]:
        for tag in soup.find_all(tag_name, **{attr: True}):
            src = tag[attr].strip()
            if src.startswith("http://"):
                http_resources.append(f"{tag_name}: {src[:100]}")

    for link in soup.find_all("link", rel="stylesheet", href=True):
        href = link["href"].strip()
        if href.startswith("http://"):
            http_resources.append(f"css: {href[:100]}")

    if http_resources:
        issues.append(CrawlIssue(
            category="resources", severity="critical", check_name="mixed_content",
            message=f"{len(http_resources)} risorse HTTP su pagina HTTPS: {url}",
            details="; ".join(http_resources[:10]),
        ))

    return issues


def check_render_blocking(url: str, soup: BeautifulSoup) -> list[CrawlIssue]:
    """Flag CSS/JS in <head> without async/defer."""
    issues = []
    head = soup.find("head")
    if not head:
        return issues

    blocking_scripts = []
    for script in head.find_all("script", src=True):
        if not script.has_attr("async") and not script.has_attr("defer"):
            blocking_scripts.append(script["src"][:100])

    if blocking_scripts:
        issues.append(CrawlIssue(
            category="resources", severity="info", check_name="render_blocking_js",
            message=f"{len(blocking_scripts)} script render-blocking nel <head>: {url}",
            details="; ".join(blocking_scripts[:5]),
        ))

    return issues
