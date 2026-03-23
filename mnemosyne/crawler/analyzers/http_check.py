"""Analyzer: HTTP status code, redirect chain, TTFB."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CrawlIssue:
    category: str
    severity: str  # critical, warning, info
    check_name: str
    message: str
    details: str | None = None


def check_status_code(url: str, status_code: int) -> list[CrawlIssue]:
    issues = []
    if status_code == 0:
        issues.append(CrawlIssue(
            category="http", severity="critical", check_name="connection_error",
            message=f"Impossibile raggiungere {url}",
        ))
    elif status_code >= 500:
        issues.append(CrawlIssue(
            category="http", severity="critical", check_name="server_error",
            message=f"Errore server {status_code} su {url}",
        ))
    elif status_code == 404:
        issues.append(CrawlIssue(
            category="http", severity="critical", check_name="not_found",
            message=f"Pagina non trovata (404): {url}",
        ))
    elif status_code == 410:
        issues.append(CrawlIssue(
            category="http", severity="critical", check_name="gone",
            message=f"Pagina rimossa (410): {url}",
        ))
    elif 400 <= status_code < 500:
        issues.append(CrawlIssue(
            category="http", severity="warning", check_name="client_error",
            message=f"Errore client {status_code} su {url}",
        ))
    return issues


def check_redirect_chain(url: str, chain: list[tuple[str, int]]) -> list[CrawlIssue]:
    issues = []
    if len(chain) > 2:
        issues.append(CrawlIssue(
            category="http", severity="warning", check_name="long_redirect_chain",
            message=f"Catena di redirect lunga ({len(chain)} hop) per {url}",
            details=str(chain),
        ))
    # Detect loops
    urls_in_chain = [u for u, _ in chain]
    if len(urls_in_chain) != len(set(urls_in_chain)):
        issues.append(CrawlIssue(
            category="http", severity="critical", check_name="redirect_loop",
            message=f"Redirect loop rilevato per {url}",
            details=str(chain),
        ))
    return issues


def check_ttfb(url: str, ttfb_ms: int) -> list[CrawlIssue]:
    issues = []
    if ttfb_ms > 3000:
        issues.append(CrawlIssue(
            category="http", severity="warning", check_name="slow_ttfb",
            message=f"TTFB molto alto ({ttfb_ms}ms) per {url}",
        ))
    elif ttfb_ms > 1000:
        issues.append(CrawlIssue(
            category="http", severity="info", check_name="high_ttfb",
            message=f"TTFB alto ({ttfb_ms}ms) per {url}",
        ))
    return issues
