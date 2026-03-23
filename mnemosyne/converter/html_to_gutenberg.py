"""Convert classic HTML post content to Gutenberg block markup."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from io import StringIO


def _strip_inline_styles(html: str) -> str:
    """Remove style attributes from all tags."""
    return re.sub(r'\s+style="[^"]*"', "", html)


def _strip_class_attrs(html: str) -> str:
    """Remove class attributes from all tags."""
    return re.sub(r'\s+class="[^"]*"', "", html)


def _clean_empty_paragraphs(html: str) -> str:
    """Remove empty <p> tags."""
    return re.sub(r"<p>\s*</p>", "", html)


def _normalize_whitespace(html: str) -> str:
    """Collapse multiple newlines into double newlines."""
    return re.sub(r"\n{3,}", "\n\n", html).strip()


def _wrap_paragraph(content: str) -> str:
    """Wrap text in a Gutenberg paragraph block."""
    content = content.strip()
    if not content:
        return ""
    return f"<!-- wp:paragraph -->\n<p>{content}</p>\n<!-- /wp:paragraph -->"


def _spacer(height: int = 30) -> str:
    """Gutenberg spacer block."""
    return (
        f'<!-- wp:spacer {{"height":"{height}px"}} -->\n'
        f'<div style="height:{height}px" aria-hidden="true" class="wp-block-spacer"></div>\n'
        f"<!-- /wp:spacer -->"
    )


def _wrap_heading(content: str, level: int) -> str:
    """Wrap text in a Gutenberg heading block, preceded by a 30px spacer."""
    content = content.strip()
    if not content:
        return ""
    spacer = _spacer(30)
    if level == 2:
        heading = f"<!-- wp:heading -->\n<h2 class=\"wp-block-heading\">{content}</h2>\n<!-- /wp:heading -->"
    else:
        heading = (
            f'<!-- wp:heading {{"level":{level}}} -->\n'
            f'<h{level} class="wp-block-heading">{content}</h{level}>\n'
            f"<!-- /wp:heading -->"
        )
    return f"{spacer}\n\n{heading}"


def _wrap_list(items_html: str, ordered: bool = False) -> str:
    """Wrap list items in a Gutenberg list block."""
    items_html = items_html.strip()
    if not items_html:
        return ""
    # Convert <li>...</li> to Gutenberg list items
    items = re.findall(r"<li[^>]*>(.*?)</li>", items_html, re.DOTALL | re.IGNORECASE)
    if not items:
        return ""
    li_blocks = "\n".join(
        f"<!-- wp:list-item -->\n<li>{item.strip()}</li>\n<!-- /wp:list-item -->"
        for item in items
    )
    if ordered:
        return (
            '<!-- wp:list {"ordered":true} -->\n'
            f"<ol>{li_blocks}</ol>\n"
            "<!-- /wp:list -->"
        )
    return f"<!-- wp:list -->\n<ul>{li_blocks}</ul>\n<!-- /wp:list -->"


def _wrap_blockquote(content: str) -> str:
    """Wrap text in a Gutenberg quote block."""
    content = content.strip()
    if not content:
        return ""
    # Ensure content is wrapped in <p> if it isn't already
    if not content.startswith("<p"):
        content = f"<p>{content}</p>"
    return f"<!-- wp:quote -->\n<blockquote class=\"wp-block-quote\">{content}</blockquote>\n<!-- /wp:quote -->"


def _wrap_image(src: str, alt: str = "") -> str:
    """Wrap an image in a Gutenberg image block."""
    alt_attr = f' alt="{alt}"' if alt else ""
    return (
        "<!-- wp:image -->\n"
        f'<figure class="wp-block-image"><img src="{src}"{alt_attr}/></figure>\n'
        "<!-- /wp:image -->"
    )


def _wrap_embed(url: str) -> str:
    """Wrap a URL in a Gutenberg embed block (for iframes/videos)."""
    # Detect YouTube
    yt_match = re.search(r"youtube\.com/embed/([^\"?]+)", url)
    if yt_match:
        video_url = f"https://www.youtube.com/watch?v={yt_match.group(1)}"
        return (
            '<!-- wp:embed {"url":"' + video_url + '","type":"video","providerNameSlug":"youtube"} -->\n'
            f'<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube">'
            f"<div class=\"wp-block-embed__wrapper\">\n{video_url}\n</div></figure>\n"
            "<!-- /wp:embed -->"
        )
    # Generic embed
    return (
        f'<!-- wp:html -->\n<iframe src="{url}" width="100%" height="400" '
        f'frameborder="0" allowfullscreen></iframe>\n<!-- /wp:html -->'
    )


def convert(html: str) -> str:
    """Convert classic HTML content to Gutenberg block markup.

    Handles: p, h2-h4, ul/ol+li, blockquote, img, iframe, and inline
    formatting (strong, em, a, span).
    """
    # Pre-clean
    html = _strip_inline_styles(html)
    html = _strip_class_attrs(html)
    html = _clean_empty_paragraphs(html)

    blocks: list[str] = []

    # Split into top-level blocks using regex
    # We process: headings, paragraphs, lists, blockquotes, iframes, images, divs
    # Anything between recognized blocks is treated as a paragraph

    # Pattern to match block-level elements
    block_pattern = re.compile(
        r"(<h([2-6])[^>]*>(.*?)</h\2>)"          # headings
        r"|(<(?:ul|ol)[^>]*>.*?</(?:ul|ol)>)"     # lists
        r"|(<blockquote[^>]*>.*?</blockquote>)"    # blockquotes
        r"|(<iframe[^>]*(?:/>|>.*?</iframe>))"     # iframes
        r"|(<img[^>]*(?:/>|>))"                    # standalone images
        r"|(<p[^>]*>(.*?)</p>)"                    # paragraphs
        r"|(<div[^>]*>(.*?)</div>)",               # divs (treat as paragraph)
        re.DOTALL | re.IGNORECASE,
    )

    last_end = 0
    for match in block_pattern.finditer(html):
        # Handle any text between blocks
        gap = html[last_end : match.start()].strip()
        if gap:
            # Loose text between blocks → paragraph
            gap = re.sub(r"<br\s*/?>", "\n", gap)
            lines = [line.strip() for line in gap.split("\n") if line.strip()]
            for line in lines:
                blocks.append(_wrap_paragraph(line))

        if match.group(1):  # heading
            level = int(match.group(2))
            content = match.group(3)
            # Extract images embedded inside headings
            img_in_h = re.findall(r'<a[^>]*><img[^>]*(?:/>|>)</a>|<img[^>]*(?:/>|>)', content, re.IGNORECASE)
            for img_tag in img_in_h:
                src_m = re.search(r'src="([^"]+)"', img_tag)
                alt_m = re.search(r'alt="([^"]*)"', img_tag)
                if src_m:
                    blocks.append(_wrap_image(
                        src_m.group(1),
                        alt_m.group(1) if alt_m else "",
                    ))
            if img_in_h:
                content = re.sub(r'<a[^>]*><img[^>]*(?:/>|>)</a>|<img[^>]*(?:/>|>)', '', content, flags=re.IGNORECASE).strip()
            if content:
                blocks.append(_wrap_heading(content, level))

        elif match.group(4):  # list
            list_html = match.group(4)
            ordered = list_html.strip().lower().startswith("<ol")
            blocks.append(_wrap_list(list_html, ordered=ordered))

        elif match.group(5):  # blockquote
            inner = re.sub(
                r"</?blockquote[^>]*>", "", match.group(5), flags=re.IGNORECASE
            ).strip()
            blocks.append(_wrap_blockquote(inner))

        elif match.group(6):  # iframe
            src_match = re.search(r'src="([^"]+)"', match.group(6))
            if src_match:
                blocks.append(_wrap_embed(src_match.group(1)))

        elif match.group(7):  # img
            src_match = re.search(r'src="([^"]+)"', match.group(7))
            alt_match = re.search(r'alt="([^"]*)"', match.group(7))
            if src_match:
                blocks.append(
                    _wrap_image(
                        src_match.group(1),
                        alt_match.group(1) if alt_match else "",
                    )
                )

        elif match.group(8):  # paragraph
            content = match.group(9)
            if content and content.strip():
                # Extract iframes embedded inside paragraphs
                iframe_in_p = re.findall(r'<iframe[^>]*(?:/>|>(?:.*?</iframe>)?)', content, re.DOTALL | re.IGNORECASE)
                for iframe_tag in iframe_in_p:
                    src_m = re.search(r'src="([^"]+)"', iframe_tag)
                    if src_m:
                        blocks.append(_wrap_embed(src_m.group(1)))
                if iframe_in_p:
                    content = re.sub(r'<iframe[^>]*(?:/>|>(?:.*?</iframe>)?)', '', content, flags=re.DOTALL | re.IGNORECASE).strip()

                # Extract images embedded inside paragraphs
                img_in_p = re.findall(r'<img[^>]*(?:/>|>)', content, re.IGNORECASE)
                if img_in_p:
                    for img_tag in img_in_p:
                        src_m = re.search(r'src="([^"]+)"', img_tag)
                        alt_m = re.search(r'alt="([^"]*)"', img_tag)
                        if src_m:
                            blocks.append(_wrap_image(
                                src_m.group(1),
                                alt_m.group(1) if alt_m else "",
                            ))
                    content = re.sub(r'<img[^>]*(?:/>|>)', '', content).strip()

                # Remaining text as paragraph
                if content:
                    blocks.append(_wrap_paragraph(content))

        elif match.group(10):  # div
            content = match.group(11)
            if content and content.strip():
                blocks.append(_wrap_paragraph(content))

        last_end = match.end()

    # Handle any trailing text
    tail = html[last_end:].strip()
    if tail:
        tail = re.sub(r"<br\s*/?>", "\n", tail)
        lines = [line.strip() for line in tail.split("\n") if line.strip()]
        for line in lines:
            blocks.append(_wrap_paragraph(line))

    result = "\n\n".join(b for b in blocks if b)
    return _normalize_whitespace(result)
