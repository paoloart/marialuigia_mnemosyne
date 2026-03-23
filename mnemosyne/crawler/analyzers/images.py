"""Analyzer: immagini — alt mancanti, rotte, pesanti, formato non ottimizzato."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .http_check import CrawlIssue


@dataclass
class ImageInfo:
    src: str
    alt: str | None
    is_missing_alt: bool = False


def extract_images(url: str, soup: BeautifulSoup) -> list[ImageInfo]:
    """Extract all <img> tags with src and alt info."""
    images = []
    for img in soup.find_all("img"):
        src = img.get("src", "").strip()
        if not src:
            continue
        # Resolve relative URLs
        src = urljoin(url, src)
        alt = img.get("alt")
        missing_alt = alt is None or alt.strip() == ""
        images.append(ImageInfo(src=src, alt=alt, is_missing_alt=missing_alt))
    return images


def check_missing_alt(url: str, images: list[ImageInfo]) -> list[CrawlIssue]:
    """Flag images without alt text."""
    issues = []
    no_alt = [img for img in images if img.is_missing_alt]
    if no_alt:
        issues.append(CrawlIssue(
            category="images", severity="warning", check_name="missing_alt",
            message=f"{len(no_alt)} immagini senza alt su {url}",
        ))
    return issues


def check_image_size(url: str, img_src: str, content_length: int) -> list[CrawlIssue]:
    """Flag images over 200KB."""
    issues = []
    if content_length > 200 * 1024:
        size_kb = content_length // 1024
        issues.append(CrawlIssue(
            category="images", severity="warning", check_name="oversized_image",
            message=f"Immagine pesante ({size_kb}KB): {img_src} su {url}",
        ))
    return issues


def check_image_format(url: str, img_src: str, content_type: str) -> list[CrawlIssue]:
    """Flag JPEG/PNG images that could be WebP/AVIF."""
    issues = []
    non_optimal = ("image/jpeg", "image/png", "image/bmp")
    if any(content_type.startswith(t) for t in non_optimal):
        issues.append(CrawlIssue(
            category="images", severity="info", check_name="non_optimal_format",
            message=f"Immagine {content_type} potrebbe essere WebP: {img_src}",
        ))
    return issues


def check_broken_image(url: str, img_src: str, status_code: int) -> list[CrawlIssue]:
    """Flag images that return 4xx/5xx."""
    issues = []
    if status_code >= 400:
        issues.append(CrawlIssue(
            category="images", severity="critical", check_name="broken_image",
            message=f"Immagine rotta ({status_code}): {img_src} su {url}",
        ))
    return issues
