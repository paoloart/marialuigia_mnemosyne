from urllib.parse import urlparse
from bs4 import BeautifulSoup


def extract_text(html: str) -> str:
    """Strip HTML tags and return clean text."""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def extract_headings(html: str) -> list[dict]:
    """Extract all headings (h1-h6) with level and position."""
    soup = BeautifulSoup(html, "html.parser")
    headings = []
    for i, tag in enumerate(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])):
        headings.append({
            "level": int(tag.name[1]),
            "text": tag.get_text(strip=True),
            "position": i,
        })
    return headings


def extract_links(html: str, site_domain: str) -> tuple[list[dict], list[dict]]:
    """Extract links, separating internal from external.

    Returns (internal_links, external_links).
    Each link is {"url": str, "anchor_text": str}.
    """
    soup = BeautifulSoup(html, "html.parser")
    internal = []
    external = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#"):
            continue

        anchor = a.get_text(strip=True)
        parsed = urlparse(href)

        # Relative URL → internal
        if not parsed.netloc:
            if parsed.path:
                internal.append({"url": href, "anchor_text": anchor})
            continue

        # Strict domain match: exact or subdomain
        if parsed.netloc == site_domain or parsed.netloc.endswith("." + site_domain):
            internal.append({"url": href, "anchor_text": anchor})
        else:
            external.append({"url": href, "anchor_text": anchor})

    return internal, external
