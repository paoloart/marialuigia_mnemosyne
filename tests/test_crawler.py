"""Test per il modulo crawler: sitemap, fetcher, analyzers, engine."""

import json
import sqlite3
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from mnemosyne.crawler.sitemap import (
    SitemapEntry,
    _parse_sitemap_index,
    _parse_urlset,
    _strip_ns,
    parse_sitemap,
)
from mnemosyne.crawler.fetcher import FetchResult, SiteFetcher
from mnemosyne.crawler.analyzers.http_check import (
    check_redirect_chain,
    check_status_code,
    check_ttfb,
)
from mnemosyne.crawler.analyzers.onpage import (
    analyze_onpage,
    check_canonical,
    check_h1,
    check_headings_structure,
    check_meta_description,
    check_meta_robots,
    check_og_tags,
    check_schema_jsonld,
    check_title,
)
from mnemosyne.crawler.analyzers.images import (
    ImageInfo,
    extract_images,
    check_missing_alt,
    check_image_size,
    check_image_format,
    check_broken_image,
)
from mnemosyne.crawler.analyzers.links import (
    LinkInfo,
    extract_links,
    check_empty_anchor,
    check_nofollow_internal,
    check_broken_link,
    check_redirect_link,
)
from mnemosyne.crawler.analyzers.content import check_thin_content, check_text_ratio
from mnemosyne.crawler.analyzers.resources import check_mixed_content, check_render_blocking
from mnemosyne.crawler.engine import CrawlEngine
from mnemosyne.crawler.report import generate_crawl_report
from mnemosyne.crawler.diff import compare_runs, CrawlDiff
from mnemosyne.crawler.prioritize import prioritize_issues, PrioritizedIssue
from mnemosyne.db.schema import create_tables


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def db():
    """In-memory SQLite DB with all tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    yield conn
    conn.close()


# ── Sitemap tests ─────────────────────────────────────────


URLSET_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/page1</loc>
    <lastmod>2026-01-01</lastmod>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://example.com/page2</loc>
  </url>
</urlset>
"""

SITEMAP_INDEX_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>https://example.com/sitemap-posts.xml</loc>
  </sitemap>
  <sitemap>
    <loc>https://example.com/sitemap-pages.xml</loc>
  </sitemap>
</sitemapindex>
"""


def test_parse_urlset():
    root = ET.fromstring(URLSET_XML)
    entries = _parse_urlset(root)
    assert len(entries) == 2
    assert entries[0].url == "https://example.com/page1"
    assert entries[0].lastmod == "2026-01-01"
    assert entries[0].priority == 0.8
    assert entries[1].url == "https://example.com/page2"
    assert entries[1].lastmod is None


def test_parse_sitemap_index():
    root = ET.fromstring(SITEMAP_INDEX_XML)
    urls = _parse_sitemap_index(root)
    assert len(urls) == 2
    assert "sitemap-posts.xml" in urls[0]
    assert "sitemap-pages.xml" in urls[1]


def test_strip_ns():
    assert _strip_ns("{http://www.sitemaps.org/schemas/sitemap/0.9}urlset") == "urlset"
    assert _strip_ns("urlset") == "urlset"


def test_parse_sitemap_from_file(tmp_path):
    sitemap_file = tmp_path / "sitemap.xml"
    sitemap_file.write_bytes(URLSET_XML)
    entries = parse_sitemap(str(sitemap_file))
    assert len(entries) == 2


# ── HTTP check tests ─────────────────────────────────────


def test_check_status_code_200():
    assert check_status_code("http://x.com", 200) == []


def test_check_status_code_404():
    issues = check_status_code("http://x.com", 404)
    assert len(issues) == 1
    assert issues[0].severity == "critical"
    assert issues[0].check_name == "not_found"


def test_check_status_code_500():
    issues = check_status_code("http://x.com", 500)
    assert len(issues) == 1
    assert issues[0].severity == "critical"
    assert issues[0].check_name == "server_error"


def test_check_status_code_0_connection_error():
    issues = check_status_code("http://x.com", 0)
    assert len(issues) == 1
    assert issues[0].check_name == "connection_error"


def test_check_redirect_chain_short():
    assert check_redirect_chain("http://x.com", [("http://a.com", 301)]) == []


def test_check_redirect_chain_long():
    chain = [("http://a.com", 301), ("http://b.com", 301), ("http://c.com", 301)]
    issues = check_redirect_chain("http://x.com", chain)
    assert len(issues) == 1
    assert issues[0].check_name == "long_redirect_chain"


def test_check_redirect_loop():
    chain = [("http://a.com", 301), ("http://b.com", 301), ("http://a.com", 301)]
    issues = check_redirect_chain("http://x.com", chain)
    assert any(i.check_name == "redirect_loop" for i in issues)


def test_check_ttfb_ok():
    assert check_ttfb("http://x.com", 200) == []


def test_check_ttfb_slow():
    issues = check_ttfb("http://x.com", 3500)
    assert len(issues) == 1
    assert issues[0].severity == "warning"


def test_check_ttfb_high():
    issues = check_ttfb("http://x.com", 1500)
    assert len(issues) == 1
    assert issues[0].severity == "info"


# ── Onpage tests ──────────────────────────────────────────

GOOD_HTML = b"""<!DOCTYPE html>
<html>
<head>
    <title>Test Page Title - Maria Luigia</title>
    <meta name="description" content="Una descrizione completa per la meta description che supera i 70 caratteri facilmente.">
    <link rel="canonical" href="https://example.com/test-page">
    <meta property="og:title" content="Test">
    <meta property="og:description" content="Desc">
    <meta property="og:image" content="https://example.com/img.jpg">
    <script type="application/ld+json">{"@type": "Article", "name": "Test"}</script>
</head>
<body>
    <h1>Main Heading</h1>
    <p>Some paragraph text here with enough words to count.</p>
    <h2>Section</h2>
    <p>More content in section.</p>
    <a href="https://example.com/other">Internal link</a>
    <a href="https://external.com/page">External link</a>
    <img src="test.jpg" alt="Test image">
    <img src="noalt.jpg">
</body>
</html>
"""

BAD_HTML = b"""<!DOCTYPE html>
<html>
<head></head>
<body>
    <h2>No H1, starts with H2</h2>
    <h4>Skips H3</h4>
    <p>Short.</p>
</body>
</html>
"""


def test_check_title_good():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(GOOD_HTML, "html.parser")
    title, issues = check_title("http://x.com", soup)
    assert title == "Test Page Title - Maria Luigia"
    assert len(issues) == 0


def test_check_title_missing():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(BAD_HTML, "html.parser")
    title, issues = check_title("http://x.com", soup)
    assert title is None
    assert issues[0].check_name == "missing_title"


def test_check_meta_description_good():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(GOOD_HTML, "html.parser")
    desc, issues = check_meta_description("http://x.com", soup)
    assert desc is not None
    assert len(issues) == 0


def test_check_h1_good():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(GOOD_HTML, "html.parser")
    count, text, issues = check_h1("http://x.com", soup)
    assert count == 1
    assert text == "Main Heading"
    assert len(issues) == 0


def test_check_h1_missing():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(BAD_HTML, "html.parser")
    count, text, issues = check_h1("http://x.com", soup)
    assert count == 0
    assert issues[0].check_name == "missing_h1"


def test_check_headings_skip():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(BAD_HTML, "html.parser")
    issues = check_headings_structure("http://x.com", soup)
    assert len(issues) == 1
    assert issues[0].check_name == "heading_skip"


def test_check_meta_robots_noindex():
    from bs4 import BeautifulSoup
    html = b'<html><head><meta name="robots" content="noindex, nofollow"></head><body></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    content, issues = check_meta_robots("http://x.com", soup)
    assert "noindex" in content
    assert any(i.check_name == "noindex" for i in issues)
    assert any(i.check_name == "nofollow" for i in issues)


def test_check_og_tags_present():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(GOOD_HTML, "html.parser")
    og, issues = check_og_tags("http://x.com", soup)
    assert og["og:title"] is True
    assert len(issues) == 0


def test_check_schema_jsonld():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(GOOD_HTML, "html.parser")
    types, issues = check_schema_jsonld("http://x.com", soup)
    assert "Article" in types
    assert len(issues) == 0


def test_analyze_onpage_full():
    data = analyze_onpage("https://example.com/test-page", GOOD_HTML)
    assert data["title"] == "Test Page Title - Maria Luigia"
    assert data["h1_count"] == 1
    assert data["img_total"] == 2
    assert data["img_no_alt"] == 1
    assert data["word_count"] > 0
    assert data["has_schema_json_ld"] == 1


# ── Engine integration test ───────────────────────────────


def test_engine_creates_tables(db):
    """Verify crawl tables exist after create_tables."""
    tables = [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "crawl_runs" in tables
    assert "crawl_pages" in tables
    assert "crawl_issues" in tables
    assert "crawl_duplicates" in tables


def test_engine_stores_results(db):
    """Test engine with mocked fetcher."""
    with patch("mnemosyne.crawler.engine.parse_sitemap") as mock_sitemap, \
         patch.object(SiteFetcher, "fetch_all") as mock_fetch:

        mock_sitemap.return_value = [
            SitemapEntry(url="https://example.com/page1"),
            SitemapEntry(url="https://example.com/page2"),
        ]

        mock_fetch.return_value = [
            FetchResult(
                url="https://example.com/page1",
                final_url="https://example.com/page1",
                status_code=200,
                ttfb_ms=150,
                content_type="text/html; charset=UTF-8",
                content_length=len(GOOD_HTML),
                body=GOOD_HTML,
                headers={"Content-Type": "text/html"},
            ),
            FetchResult(
                url="https://example.com/page2",
                final_url="https://example.com/page2",
                status_code=404,
                ttfb_ms=50,
                content_type="text/html",
                content_length=0,
                body=None,
                headers={},
            ),
        ]

        engine = CrawlEngine(db, "https://example.com/sitemap.xml")
        run_id = engine.run()

        assert run_id > 0

        # Check crawl_run
        run = db.execute("SELECT * FROM crawl_runs WHERE id = ?", (run_id,)).fetchone()
        assert run["status"] == "completed"
        assert run["crawled_urls"] == 2

        # Check pages
        pages = db.execute("SELECT * FROM crawl_pages WHERE run_id = ?", (run_id,)).fetchall()
        assert len(pages) == 2

        # Check issues (404 should create a critical issue)
        issues = db.execute(
            "SELECT * FROM crawl_issues WHERE run_id = ? AND severity = 'critical'", (run_id,)
        ).fetchall()
        assert len(issues) > 0
        assert any(i["check_name"] == "not_found" for i in issues)

        # Check crawl_links were stored
        links = db.execute("SELECT * FROM crawl_links WHERE run_id = ?", (run_id,)).fetchall()
        assert len(links) > 0

        # Check crawl_images were stored
        images = db.execute("SELECT * FROM crawl_images WHERE run_id = ?", (run_id,)).fetchall()
        assert len(images) > 0


# ── Images analyzer tests ─────────────────────────────────


def test_extract_images():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(GOOD_HTML, "html.parser")
    images = extract_images("https://example.com/page", soup)
    assert len(images) == 2
    assert any(img.is_missing_alt for img in images)
    assert any(not img.is_missing_alt for img in images)


def test_extract_images_resolves_relative_urls():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(GOOD_HTML, "html.parser")
    images = extract_images("https://example.com/page", soup)
    for img in images:
        assert img.src.startswith("https://")


def test_check_missing_alt_issues():
    images = [
        ImageInfo(src="https://x.com/a.jpg", alt="Good alt", is_missing_alt=False),
        ImageInfo(src="https://x.com/b.jpg", alt=None, is_missing_alt=True),
        ImageInfo(src="https://x.com/c.jpg", alt="", is_missing_alt=True),
    ]
    issues = check_missing_alt("https://x.com/page", images)
    assert len(issues) == 1
    assert "2 immagini" in issues[0].message


def test_check_image_size_ok():
    assert check_image_size("http://x.com", "img.jpg", 100 * 1024) == []


def test_check_image_size_oversized():
    issues = check_image_size("http://x.com", "img.jpg", 300 * 1024)
    assert len(issues) == 1
    assert issues[0].check_name == "oversized_image"


def test_check_image_format_jpeg():
    issues = check_image_format("http://x.com", "img.jpg", "image/jpeg")
    assert len(issues) == 1
    assert issues[0].check_name == "non_optimal_format"


def test_check_image_format_webp():
    assert check_image_format("http://x.com", "img.webp", "image/webp") == []


def test_check_broken_image_ok():
    assert check_broken_image("http://x.com", "img.jpg", 200) == []


def test_check_broken_image_404():
    issues = check_broken_image("http://x.com", "img.jpg", 404)
    assert len(issues) == 1
    assert issues[0].severity == "critical"


# ── Links analyzer tests ──────────────────────────────────


def test_extract_links():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(GOOD_HTML, "html.parser")
    links = extract_links("https://example.com/page", soup)
    internal = [l for l in links if l.is_internal]
    external = [l for l in links if not l.is_internal]
    assert len(internal) == 1
    assert len(external) == 1
    assert internal[0].anchor_text == "Internal link"


def test_extract_links_resolves_relative():
    from bs4 import BeautifulSoup
    html = b'<html><body><a href="/about">About</a></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    links = extract_links("https://example.com/page", soup)
    assert len(links) == 1
    assert links[0].target_url == "https://example.com/about"
    assert links[0].is_internal is True


def test_extract_links_ignores_anchors_mailto():
    from bs4 import BeautifulSoup
    html = b'<html><body><a href="#section">Anchor</a><a href="mailto:a@b.com">Mail</a><a href="tel:123">Tel</a></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    links = extract_links("https://example.com/page", soup)
    assert len(links) == 0


def test_check_empty_anchor():
    links = [
        LinkInfo(target_url="https://x.com/a", anchor_text="Good", is_internal=True),
        LinkInfo(target_url="https://x.com/b", anchor_text="", is_internal=True),
        LinkInfo(target_url="https://x.com/c", anchor_text="  ", is_internal=False),
    ]
    issues = check_empty_anchor("https://x.com/page", links)
    assert len(issues) == 1
    assert "2 link" in issues[0].message


def test_check_nofollow_internal():
    links = [
        LinkInfo(target_url="https://x.com/a", anchor_text="A", is_internal=True, rel="nofollow"),
        LinkInfo(target_url="https://other.com/b", anchor_text="B", is_internal=False, rel="nofollow"),
        LinkInfo(target_url="https://x.com/c", anchor_text="C", is_internal=True, rel=None),
    ]
    issues = check_nofollow_internal("https://x.com/page", links)
    assert len(issues) == 1  # only the internal nofollow


def test_check_broken_link_internal():
    link = LinkInfo(target_url="https://x.com/dead", anchor_text="Dead", is_internal=True)
    issues = check_broken_link("https://x.com/page", link, 404)
    assert len(issues) == 1
    assert issues[0].severity == "critical"
    assert issues[0].check_name == "broken_internal_link"


def test_check_broken_link_external():
    link = LinkInfo(target_url="https://other.com/dead", anchor_text="Dead", is_internal=False)
    issues = check_broken_link("https://x.com/page", link, 503)
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].check_name == "broken_external_link"


def test_check_redirect_link():
    link = LinkInfo(target_url="https://x.com/old", anchor_text="Old", is_internal=True)
    issues = check_redirect_link("https://x.com/page", link, 301)
    assert len(issues) == 1
    assert issues[0].check_name == "redirect_internal_link"


def test_check_redirect_link_external_ignored():
    link = LinkInfo(target_url="https://other.com/old", anchor_text="Old", is_internal=False)
    issues = check_redirect_link("https://x.com/page", link, 301)
    assert len(issues) == 0  # external redirects are not flagged


# ── Content analyzer tests ────────────────────────────────


def test_check_thin_content_ok():
    assert check_thin_content("http://x.com", 500) == []


def test_check_thin_content_thin():
    issues = check_thin_content("http://x.com", 100)
    assert len(issues) == 1
    assert issues[0].check_name == "thin_content"


def test_check_text_ratio_ok():
    assert check_text_ratio("http://x.com", 0.25) == []


def test_check_text_ratio_low():
    issues = check_text_ratio("http://x.com", 0.05)
    assert len(issues) == 1
    assert issues[0].check_name == "low_text_ratio"


# ── Resources analyzer tests ─────────────────────────────


def test_check_mixed_content_clean():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(GOOD_HTML, "html.parser")
    issues = check_mixed_content("https://example.com/page", soup)
    assert len(issues) == 0


def test_check_mixed_content_found():
    from bs4 import BeautifulSoup
    html = b"""<html><body>
        <img src="http://insecure.com/img.jpg">
        <script src="http://insecure.com/script.js"></script>
    </body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    issues = check_mixed_content("https://example.com/page", soup)
    assert len(issues) == 1
    assert issues[0].check_name == "mixed_content"
    assert "2 risorse" in issues[0].message


def test_check_mixed_content_http_page():
    from bs4 import BeautifulSoup
    html = b'<html><body><img src="http://x.com/img.jpg"></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    # HTTP page — mixed content check should not fire
    issues = check_mixed_content("http://example.com/page", soup)
    assert len(issues) == 0


def test_check_render_blocking():
    from bs4 import BeautifulSoup
    html = b"""<html><head>
        <script src="blocking.js"></script>
        <script src="async.js" async></script>
        <script src="defer.js" defer></script>
    </head><body></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    issues = check_render_blocking("https://example.com/page", soup)
    assert len(issues) == 1
    assert "1 script" in issues[0].message


# ── Report tests ──────────────────────────────────────────


def _seed_crawl_data(db):
    """Seed a crawl run with test data for report tests."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        "INSERT INTO crawl_runs (id, started_at, finished_at, sitemap_url, total_urls, crawled_urls, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (99, now, now, "https://example.com/sitemap.xml", 3, 3, "completed"),
    )
    # 3 pages
    for i, (url, status, ttfb, wc) in enumerate([
        ("https://example.com/page1", 200, 150, 800),
        ("https://example.com/page2", 200, 2500, 100),
        ("https://example.com/page3", 404, 50, 0),
    ], start=1):
        db.execute(
            """INSERT INTO crawl_pages (id, run_id, url, status_code, ttfb_ms, word_count,
               content_type, content_length, title, h1_count, html_size, crawled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (i, 99, url, status, ttfb, wc, "text/html", 5000,
             f"Title Page {i}" if status == 200 else None, 1, 5000, now),
        )

    # Issues
    db.execute(
        "INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (99, 3, "https://example.com/page3", "http", "critical", "not_found", "404 on page3"),
    )
    db.execute(
        "INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (99, 2, "https://example.com/page2", "content", "warning", "thin_content", "Thin content"),
    )
    db.execute(
        "INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (99, 1, "https://example.com/page1", "onpage", "info", "no_schema_jsonld", "No schema"),
    )
    db.commit()


def test_report_generates_charts(db):
    """Test that generate_crawl_report creates charts in dashboard_charts."""
    _seed_crawl_data(db)
    n = generate_crawl_report(db, 99)
    assert n > 0

    charts = db.execute("SELECT * FROM dashboard_charts WHERE title LIKE 'Crawl:%'").fetchall()
    assert len(charts) == n
    assert all(c["pinned"] == 1 for c in charts)


def test_report_health_score(db):
    """Test health score: 1 out of 3 pages has critical issue = 66%."""
    _seed_crawl_data(db)
    from mnemosyne.crawler.report import _health_score
    score = _health_score(db, 99)
    assert abs(score - 66.67) < 1.0


def test_report_issue_counts(db):
    _seed_crawl_data(db)
    from mnemosyne.crawler.report import _issue_counts
    counts = _issue_counts(db, 99)
    assert counts["critical"] == 1
    assert counts["warning"] == 1
    assert counts["info"] == 1


def test_report_idempotent(db):
    """Running report twice should replace old charts, not duplicate."""
    _seed_crawl_data(db)
    generate_crawl_report(db, 99)
    generate_crawl_report(db, 99)
    charts = db.execute("SELECT * FROM dashboard_charts WHERE title LIKE 'Crawl:%'").fetchall()
    # Should have same count as one run
    n = generate_crawl_report(db, 99)
    charts_after = db.execute("SELECT * FROM dashboard_charts WHERE title LIKE 'Crawl:%'").fetchall()
    assert len(charts_after) == n


def test_engine_generates_report(db):
    """Full engine run should also produce dashboard charts."""
    with patch("mnemosyne.crawler.engine.parse_sitemap") as mock_sitemap, \
         patch.object(SiteFetcher, "fetch_all") as mock_fetch:

        mock_sitemap.return_value = [
            SitemapEntry(url="https://example.com/page1"),
        ]
        mock_fetch.return_value = [
            FetchResult(
                url="https://example.com/page1",
                final_url="https://example.com/page1",
                status_code=200,
                ttfb_ms=150,
                content_type="text/html; charset=UTF-8",
                content_length=len(GOOD_HTML),
                body=GOOD_HTML,
                headers={"Content-Type": "text/html"},
            ),
        ]

        engine = CrawlEngine(db, "https://example.com/sitemap.xml")
        run_id = engine.run()

        charts = db.execute("SELECT * FROM dashboard_charts WHERE title LIKE 'Crawl:%'").fetchall()
        assert len(charts) > 0


# ── Diff tests ────────────────────────────────────────────


def _seed_two_runs(db):
    """Seed two crawl runs for diff testing."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    # Run 1: 2 pages, page2 is 404
    db.execute(
        "INSERT INTO crawl_runs (id, started_at, finished_at, sitemap_url, total_urls, crawled_urls, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (50, now, now, "https://example.com/sitemap.xml", 2, 2, "completed"),
    )
    db.execute(
        "INSERT INTO crawl_pages (id, run_id, url, status_code, ttfb_ms, word_count, content_type, content_length, h1_count, html_size, crawled_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (50, 50, "https://example.com/page1", 200, 100, 500, "text/html", 5000, 1, 5000, now),
    )
    db.execute(
        "INSERT INTO crawl_pages (id, run_id, url, status_code, ttfb_ms, word_count, content_type, content_length, h1_count, html_size, crawled_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (51, 50, "https://example.com/page2", 404, 50, 0, "text/html", 0, 0, 0, now),
    )
    db.execute(
        "INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (50, 51, "https://example.com/page2", "http", "critical", "not_found", "404 on page2"),
    )
    db.execute(
        "INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (50, 50, "https://example.com/page1", "onpage", "info", "no_schema_jsonld", "No schema"),
    )

    # Run 2: page2 fixed (200), page3 added (200), page1 lost schema issue but got thin content
    db.execute(
        "INSERT INTO crawl_runs (id, started_at, finished_at, sitemap_url, total_urls, crawled_urls, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (51, now, now, "https://example.com/sitemap.xml", 3, 3, "completed"),
    )
    db.execute(
        "INSERT INTO crawl_pages (id, run_id, url, status_code, ttfb_ms, word_count, content_type, content_length, h1_count, html_size, crawled_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (60, 51, "https://example.com/page1", 200, 100, 200, "text/html", 5000, 1, 5000, now),
    )
    db.execute(
        "INSERT INTO crawl_pages (id, run_id, url, status_code, ttfb_ms, word_count, content_type, content_length, h1_count, html_size, crawled_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (61, 51, "https://example.com/page2", 200, 80, 600, "text/html", 5000, 1, 5000, now),
    )
    db.execute(
        "INSERT INTO crawl_pages (id, run_id, url, status_code, ttfb_ms, word_count, content_type, content_length, h1_count, html_size, crawled_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (62, 51, "https://example.com/page3", 200, 120, 400, "text/html", 5000, 1, 5000, now),
    )
    db.execute(
        "INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (51, 60, "https://example.com/page1", "content", "warning", "thin_content", "Thin content 200 words"),
    )
    db.commit()


def test_diff_detects_new_and_resolved_issues(db):
    _seed_two_runs(db)
    diff = compare_runs(db, 50, 51)

    # The 404 issue on page2 should be resolved
    assert any(i["check_name"] == "not_found" for i in diff.resolved_issues)
    # The no_schema_jsonld on page1 should be resolved
    assert any(i["check_name"] == "no_schema_jsonld" for i in diff.resolved_issues)

    # The thin_content on page1 should be new
    assert any(i["check_name"] == "thin_content" for i in diff.new_issues)


def test_diff_detects_new_pages(db):
    _seed_two_runs(db)
    diff = compare_runs(db, 50, 51)
    assert "https://example.com/page3" in diff.new_pages


def test_diff_detects_status_changes(db):
    _seed_two_runs(db)
    diff = compare_runs(db, 50, 51)
    # page2 went from 404 to 200
    changes = {ch["url"]: ch for ch in diff.status_changes}
    assert "https://example.com/page2" in changes
    assert changes["https://example.com/page2"]["old_status"] == 404
    assert changes["https://example.com/page2"]["new_status"] == 200


def test_diff_health_score(db):
    _seed_two_runs(db)
    diff = compare_runs(db, 50, 51)
    # Run 50: 1/2 pages has critical = 50% health
    assert abs(diff.score_old - 50.0) < 1.0
    # Run 51: 0/3 pages has critical = 100% health
    assert diff.score_new == 100.0


# ── Prioritize tests ─────────────────────────────────────


def test_prioritize_sorts_by_impact(db):
    _seed_crawl_data(db)  # run 99

    gsc_data = [
        {"page": "https://example.com/page3", "clicks": 500, "impressions": 10000, "ctr": 0.05, "position": 5.0},
        {"page": "https://example.com/page1", "clicks": 10, "impressions": 200, "ctr": 0.05, "position": 8.0},
    ]

    result = prioritize_issues(db, 99, gsc_data)
    assert len(result) > 0
    # The 404 on page3 (high traffic) should rank higher than info on page1 (low traffic)
    top = result[0]
    assert top.url == "https://example.com/page3"
    assert top.clicks == 500
    assert top.impact_score > 0


def test_prioritize_handles_no_gsc_data(db):
    _seed_crawl_data(db)
    result = prioritize_issues(db, 99, [])
    # Should still return issues, just with 0 traffic
    assert len(result) > 0
    assert all(i.clicks == 0 for i in result)


def test_prioritize_normalizes_trailing_slash(db):
    _seed_crawl_data(db)
    # GSC often returns URLs with trailing slash
    gsc_data = [
        {"page": "https://example.com/page3/", "clicks": 100, "impressions": 5000, "ctr": 0.02, "position": 4.0},
    ]
    result = prioritize_issues(db, 99, gsc_data)
    page3_issues = [i for i in result if "page3" in i.url]
    assert any(i.clicks == 100 for i in page3_issues)
