"""Pillar Score — punteggio di qualità per articoli cornerstone.

Ogni post riceve un punteggio 0-100 basato su:
- Contenuto (word count, freschezza, meta description, title)
- Linking (inbound, outbound, esterni, fonti DOI)
- Struttura (headings, H1, schema JSON-LD)
- Performance (TTFB, status code)

Score più basso = più bisogno di lavoro.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PillarScore:
    post_id: int
    title: str
    url: str
    total_score: float = 0.0
    # Sub-scores (0-100 each)
    content_score: float = 0.0
    linking_score: float = 0.0
    structure_score: float = 0.0
    performance_score: float = 0.0
    # Raw data for transparency
    details: dict = field(default_factory=dict)


# ── Weights ───────────────────────────────────────────────
W_CONTENT = 0.35
W_LINKING = 0.30
W_STRUCTURE = 0.20
W_PERFORMANCE = 0.15


def score_post(conn: sqlite3.Connection, post_id: int, run_id: int | None = None) -> PillarScore:
    """Calculate pillar score for a single post."""
    post = conn.execute(
        "SELECT id, title, url, word_count, date_modified, yoast_title, yoast_metadesc FROM posts WHERE id = ?",
        (post_id,),
    ).fetchone()
    if not post:
        return PillarScore(post_id=post_id, title="?", url="?")

    ps = PillarScore(post_id=post_id, title=post["title"], url=post["url"])

    # ── Content score ─────────────────────────────────────
    wc = post["word_count"] or 0
    # Word count: 0 at 0 words, 100 at 2000+
    wc_score = min(wc / 2000, 1.0) * 100

    # Freshness: days since last modified, 100 if <90 days, 0 if >730 days
    freshness = 100
    if post["date_modified"]:
        try:
            mod = datetime.fromisoformat(post["date_modified"].replace("Z", "+00:00"))
            if mod.tzinfo is None:
                mod = mod.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days_old = (now - mod).days
            freshness = max(0, min(100, 100 - (days_old - 90) * (100 / 640)))
        except (ValueError, TypeError):
            freshness = 50

    # Meta description: 0 or 100
    has_meta = 100 if post["yoast_metadesc"] else 0

    # Title length: 100 if 30-60ch, penalized otherwise
    title_len = len(post["yoast_title"] or post["title"] or "")
    if 30 <= title_len <= 60:
        title_score = 100
    elif title_len > 60:
        title_score = max(0, 100 - (title_len - 60) * 5)
    else:
        title_score = max(0, title_len / 30 * 100)

    ps.content_score = wc_score * 0.4 + freshness * 0.3 + has_meta * 0.15 + title_score * 0.15
    ps.details["word_count"] = wc
    if post["date_modified"]:
        try:
            mod_str = post["date_modified"].replace("Z", "+00:00")
            mod_dt = datetime.fromisoformat(mod_str)
            if mod_dt.tzinfo is None:
                mod_dt = mod_dt.replace(tzinfo=timezone.utc)
            ps.details["freshness_days"] = int((datetime.now(timezone.utc) - mod_dt).days)
        except (ValueError, TypeError):
            ps.details["freshness_days"] = None
    else:
        ps.details["freshness_days"] = None
    ps.details["has_meta"] = bool(post["yoast_metadesc"])
    ps.details["title_len"] = title_len

    # ── Linking score ─────────────────────────────────────
    inbound = conn.execute(
        "SELECT COUNT(*) FROM internal_links WHERE target_post_id = ?", (post_id,)
    ).fetchone()[0]

    outbound = conn.execute(
        "SELECT COUNT(*) FROM internal_links WHERE source_post_id = ?", (post_id,)
    ).fetchone()[0]

    external = conn.execute(
        "SELECT COUNT(*) FROM external_links WHERE source_post_id = ?", (post_id,)
    ).fetchone()[0]

    # DOI count (scientific sources)
    content_raw = conn.execute("SELECT content_raw FROM posts WHERE id = ?", (post_id,)).fetchone()
    doi_count = (content_raw["content_raw"] or "").count("doi.org/") if content_raw else 0

    # Inbound: 0 at 0, 100 at 10+
    inbound_score = min(inbound / 10, 1.0) * 100
    # Outbound: 0 at 0, 100 at 5+
    outbound_score = min(outbound / 5, 1.0) * 100
    # External/DOI: 0 at 0, 100 at 8+
    sources_score = min((external + doi_count) / 8, 1.0) * 100

    ps.linking_score = inbound_score * 0.45 + outbound_score * 0.25 + sources_score * 0.30
    ps.details["inbound_links"] = inbound
    ps.details["outbound_links"] = outbound
    ps.details["external_links"] = external
    ps.details["doi_count"] = doi_count

    # ── Structure score ───────────────────────────────────
    headings = conn.execute(
        "SELECT level, COUNT(*) FROM headings WHERE post_id = ? GROUP BY level", (post_id,)
    ).fetchall()
    heading_map = {r[0]: r[1] for r in headings}

    has_h1 = 100 if heading_map.get(1, 0) == 1 else (50 if heading_map.get(1, 0) > 1 else 0)
    has_h2 = min(heading_map.get(2, 0) / 3, 1.0) * 100  # 100 at 3+ H2s
    has_h3 = min(heading_map.get(3, 0) / 2, 1.0) * 100  # 100 at 2+ H3s

    # Heading hierarchy: check for skips
    levels = sorted(heading_map.keys())
    hierarchy_ok = 100
    for i in range(1, len(levels)):
        if levels[i] > levels[i - 1] + 1:
            hierarchy_ok = 50
            break

    # Schema JSON-LD (from crawl data if available)
    has_schema = 0
    if run_id:
        schema = conn.execute(
            "SELECT has_schema_json_ld FROM crawl_pages WHERE run_id = ? AND url = ?",
            (run_id, post["url"]),
        ).fetchone()
        if schema and schema[0]:
            has_schema = 100

    ps.structure_score = has_h1 * 0.20 + has_h2 * 0.25 + has_h3 * 0.15 + hierarchy_ok * 0.20 + has_schema * 0.20
    ps.details["h1_count"] = heading_map.get(1, 0)
    ps.details["h2_count"] = heading_map.get(2, 0)
    ps.details["h3_count"] = heading_map.get(3, 0)
    ps.details["has_schema"] = bool(has_schema)

    # ── Performance score ─────────────────────────────────
    if run_id:
        crawl = conn.execute(
            "SELECT status_code, ttfb_ms FROM crawl_pages WHERE run_id = ? AND url = ?",
            (run_id, post["url"]),
        ).fetchone()
        if crawl:
            status_score = 100 if crawl["status_code"] == 200 else 0
            ttfb = crawl["ttfb_ms"] or 0
            # 100 if <500ms, 0 if >3000ms
            ttfb_score = max(0, min(100, 100 - (ttfb - 500) * (100 / 2500)))
            ps.performance_score = status_score * 0.5 + ttfb_score * 0.5
            ps.details["status_code"] = crawl["status_code"]
            ps.details["ttfb_ms"] = ttfb
        else:
            ps.performance_score = 50  # Unknown
    else:
        ps.performance_score = 50

    # ── Total score ───────────────────────────────────────
    ps.total_score = round(
        ps.content_score * W_CONTENT
        + ps.linking_score * W_LINKING
        + ps.structure_score * W_STRUCTURE
        + ps.performance_score * W_PERFORMANCE,
        1,
    )

    return ps


def score_all_posts(conn: sqlite3.Connection, run_id: int | None = None) -> list[PillarScore]:
    """Score all posts. Returns sorted by score ascending (worst first)."""
    posts = conn.execute("SELECT id FROM posts").fetchall()

    if not run_id:
        row = conn.execute("SELECT id FROM crawl_runs WHERE status = 'completed' ORDER BY id DESC LIMIT 1").fetchone()
        run_id = row[0] if row else None

    scores = [score_post(conn, p[0], run_id) for p in posts]
    scores.sort(key=lambda s: s.total_score)
    return scores
