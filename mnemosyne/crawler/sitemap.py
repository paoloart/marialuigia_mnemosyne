"""Parsing sitemap XML — supporta sitemap index Yoast e singoli urlset."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests

# Namespace comuni nelle sitemap
_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
}

USER_AGENT = "MnemosyneBot/1.0 (+ospedalemarialuigia.it)"


@dataclass
class SitemapEntry:
    url: str
    lastmod: str | None = None
    changefreq: str | None = None
    priority: float | None = None


def parse_sitemap(source: str, session: requests.Session | None = None) -> list[SitemapEntry]:
    """Parse a sitemap from URL or local file path.

    Handles both sitemap index and urlset formats.
    """
    xml_bytes = _fetch_source(source, session)
    root = ET.fromstring(xml_bytes)
    tag = _strip_ns(root.tag)

    if tag == "sitemapindex":
        sub_urls = _parse_sitemap_index(root)
        entries: list[SitemapEntry] = []
        for sub_url in sub_urls:
            try:
                entries.extend(parse_sitemap(sub_url, session))
            except Exception as e:
                print(f"  [WARN] Errore parsing sub-sitemap {sub_url}: {e}")
        return entries

    if tag == "urlset":
        return _parse_urlset(root)

    raise ValueError(f"Root element sconosciuto: {root.tag}")


def _fetch_source(source: str, session: requests.Session | None = None) -> bytes:
    """Fetch sitemap XML from URL or local file."""
    if source.startswith("http://") or source.startswith("https://"):
        sess = session or requests.Session()
        resp = sess.get(source, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        return resp.content

    with open(source, "rb") as f:
        return f.read()


def _strip_ns(tag: str) -> str:
    """Remove XML namespace from tag name."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_urlset(root: ET.Element) -> list[SitemapEntry]:
    """Parse a <urlset> element into SitemapEntry list."""
    entries = []
    for url_el in root.findall("sm:url", _NS):
        loc = url_el.findtext("sm:loc", namespaces=_NS)
        if not loc:
            continue
        entries.append(SitemapEntry(
            url=loc.strip(),
            lastmod=url_el.findtext("sm:lastmod", namespaces=_NS),
            changefreq=url_el.findtext("sm:changefreq", namespaces=_NS),
            priority=_parse_priority(url_el.findtext("sm:priority", namespaces=_NS)),
        ))
    return entries


def _parse_sitemap_index(root: ET.Element) -> list[str]:
    """Parse a <sitemapindex> element, return list of sub-sitemap URLs."""
    urls = []
    for sitemap_el in root.findall("sm:sitemap", _NS):
        loc = sitemap_el.findtext("sm:loc", namespaces=_NS)
        if loc:
            urls.append(loc.strip())
    return urls


def _parse_priority(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except ValueError:
        return None
