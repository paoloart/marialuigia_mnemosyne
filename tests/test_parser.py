import pytest
from mnemosyne.scraper.parser import extract_text, extract_headings, extract_links


SAMPLE_HTML = """
<h2>Introduction</h2>
<p>Welcome to <a href="https://marialuigia.com/altro-post">another post</a> about food.</p>
<h3>Details</h3>
<p>Read more at <a href="https://external.com/page">external site</a>.</p>
<p>Also check <a href="https://marialuigia.com/ricetta">our recipe</a>.</p>
"""

SITE_DOMAIN = "marialuigia.com"


def test_extract_text_strips_html():
    text = extract_text(SAMPLE_HTML)
    assert "<p>" not in text
    assert "<h2>" not in text
    assert "Welcome to" in text
    assert "another post" in text


def test_extract_text_preserves_content():
    text = extract_text("<p>Hello <strong>world</strong></p>")
    assert "Hello" in text
    assert "world" in text


def test_extract_headings():
    headings = extract_headings(SAMPLE_HTML)
    assert len(headings) == 2
    assert headings[0] == {"level": 2, "text": "Introduction", "position": 0}
    assert headings[1] == {"level": 3, "text": "Details", "position": 1}


def test_extract_links_separates_internal_and_external():
    internal, external = extract_links(SAMPLE_HTML, SITE_DOMAIN)
    assert len(internal) == 2
    assert len(external) == 1
    assert internal[0]["url"] == "https://marialuigia.com/altro-post"
    assert internal[0]["anchor_text"] == "another post"
    assert external[0]["url"] == "https://external.com/page"
    assert external[0]["anchor_text"] == "external site"


def test_extract_links_handles_relative_urls():
    html = '<a href="/local-page">Local</a>'
    internal, external = extract_links(html, "example.com")
    assert len(internal) == 1


def test_extract_links_ignores_anchors_and_empty():
    html = '<a href="#section">Jump</a><a href="">Empty</a><a>No href</a>'
    internal, external = extract_links(html, "example.com")
    assert len(internal) == 0
    assert len(external) == 0
