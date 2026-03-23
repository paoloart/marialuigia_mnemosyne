"""Orchestratore del crawl: sitemap → fetch → analyze → store."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .fetcher import FetchResult, SiteFetcher
from .sitemap import SitemapEntry, parse_sitemap
from .analyzers.http_check import CrawlIssue, check_redirect_chain, check_status_code, check_ttfb
from .analyzers.onpage import analyze_onpage
from .analyzers.images import ImageInfo, extract_images, check_missing_alt, check_broken_image, check_image_size, check_image_format
from .analyzers.links import LinkInfo, extract_links, check_empty_anchor, check_nofollow_internal, check_broken_link, check_redirect_link
from .analyzers.content import check_thin_content, check_text_ratio
from .analyzers.resources import check_mixed_content, check_render_blocking


class CrawlEngine:
    def __init__(
        self,
        conn: sqlite3.Connection,
        sitemap_source: str,
        max_workers: int = 5,
        delay: float = 0.5,
        check_external_links: bool = False,
    ):
        self.conn = conn
        self.sitemap_source = sitemap_source
        self.max_workers = max_workers
        self.delay = delay
        self.check_external_links = check_external_links
        self.fetcher = SiteFetcher(
            max_workers=max_workers, delay=delay,
        )

    def run(self) -> int:
        """Execute the full crawl. Returns run_id."""
        now = datetime.now(timezone.utc).isoformat()

        # 1. Parse sitemap
        print(f"Parsing sitemap: {self.sitemap_source}")
        entries = parse_sitemap(self.sitemap_source, self.fetcher.session)
        print(f"  Trovate {len(entries)} URL nella sitemap")

        if not entries:
            print("  Nessuna URL trovata. Aborting.")
            return 0

        # 2. Create crawl run
        cur = self.conn.execute(
            "INSERT INTO crawl_runs (started_at, sitemap_url, total_urls, status) VALUES (?, ?, ?, ?)",
            (now, self.sitemap_source, len(entries), "running"),
        )
        run_id = cur.lastrowid
        self.conn.commit()

        # 3. Fetch all pages
        urls = [e.url for e in entries]
        print(f"Crawling {len(urls)} pagine (workers={self.max_workers}, delay={self.delay}s)...")

        def progress(done: int, total: int) -> None:
            if done % 10 == 0 or done == total:
                print(f"  [{done}/{total}] crawlate")
                self.conn.execute(
                    "UPDATE crawl_runs SET crawled_urls = ? WHERE id = ?",
                    (done, run_id),
                )
                self.conn.commit()

        results = self.fetcher.fetch_all(urls, callback=progress)

        # Build URL→FetchResult map (for cross-referencing internal links)
        result_map = {r.url: r for r in results}
        # Also map final_url → status for redirect targets
        status_map: dict[str, int] = {}
        for r in results:
            status_map[r.url] = r.status_code
            if r.final_url and r.final_url != r.url:
                status_map[r.final_url] = r.status_code

        # 4. Process each page (collect images/links for post-processing)
        print("Analizzando pagine...")
        all_images: list[tuple[int, str, ImageInfo]] = []  # (page_id, page_url, img)
        all_links: list[tuple[int, str, LinkInfo]] = []    # (page_id, page_url, link)

        for entry in entries:
            fetch_result = result_map.get(entry.url)
            if fetch_result:
                page_id, images, links = self._process_page(run_id, entry, fetch_result)
                for img in images:
                    all_images.append((page_id, entry.url, img))
                for lk in links:
                    all_links.append((page_id, entry.url, lk))

        # 5. Post-processing
        print("Post-processing...")
        self._post_process(run_id)
        self._post_process_links(run_id, all_links, status_map)
        self._post_process_images(run_id, all_images)

        # 5b. Generate dashboard report
        print("Generando report dashboard...")
        from .report import generate_crawl_report
        n_charts = generate_crawl_report(self.conn, run_id)
        print(f"  {n_charts} grafici pushati in dashboard_charts")

        # 6. Mark complete
        finished = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE crawl_runs SET finished_at = ?, crawled_urls = ?, status = ? WHERE id = ?",
            (finished, len(results), "completed", run_id),
        )
        self.conn.commit()

        self._print_summary(run_id)
        return run_id

    def _process_page(
        self, run_id: int, entry: SitemapEntry, result: FetchResult
    ) -> tuple[int, list[ImageInfo], list[LinkInfo]]:
        """Process a single page. Returns (page_id, images, links)."""
        all_issues: list[CrawlIssue] = []
        images: list[ImageInfo] = []
        links: list[LinkInfo] = []

        # HTTP checks
        all_issues.extend(check_status_code(entry.url, result.status_code))
        all_issues.extend(check_redirect_chain(entry.url, result.redirect_chain))
        all_issues.extend(check_ttfb(entry.url, result.ttfb_ms))

        # On-page + content + resources analysis (only if we got HTML)
        page_data: dict = {}
        is_html = result.body and "text/html" in result.content_type
        if is_html:
            page_data = analyze_onpage(entry.url, result.body)
            all_issues.extend(page_data.pop("issues", []))

            soup = BeautifulSoup(result.body, "html.parser")

            # Images
            images = extract_images(entry.url, soup)
            all_issues.extend(check_missing_alt(entry.url, images))

            # Links
            links = extract_links(entry.url, soup)
            all_issues.extend(check_empty_anchor(entry.url, links))
            all_issues.extend(check_nofollow_internal(entry.url, links))

            # Content
            all_issues.extend(check_thin_content(entry.url, page_data.get("word_count", 0)))
            all_issues.extend(check_text_ratio(entry.url, page_data.get("text_ratio", 0)))

            # Resources
            all_issues.extend(check_mixed_content(entry.url, soup))
            all_issues.extend(check_render_blocking(entry.url, soup))

        now = datetime.now(timezone.utc).isoformat()

        # Insert crawl_page
        cur = self.conn.execute(
            """INSERT INTO crawl_pages (
                run_id, url, status_code, redirect_url, redirect_chain, ttfb_ms,
                content_type, content_length, title, meta_description, meta_robots,
                canonical_url, h1_count, h1_text, word_count, html_size, text_ratio,
                has_og_title, has_og_description, has_og_image,
                has_schema_json_ld, schema_types,
                img_total, img_no_alt,
                internal_links_count, external_links_count, crawled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                entry.url,
                result.status_code,
                result.final_url if result.final_url != entry.url else None,
                json.dumps(result.redirect_chain) if result.redirect_chain else None,
                result.ttfb_ms,
                result.content_type,
                result.content_length,
                page_data.get("title"),
                page_data.get("meta_description"),
                page_data.get("meta_robots"),
                page_data.get("canonical_url"),
                page_data.get("h1_count", 0),
                page_data.get("h1_text"),
                page_data.get("word_count", 0),
                page_data.get("html_size", 0),
                page_data.get("text_ratio"),
                page_data.get("has_og_title", 0),
                page_data.get("has_og_description", 0),
                page_data.get("has_og_image", 0),
                page_data.get("has_schema_json_ld", 0),
                page_data.get("schema_types"),
                page_data.get("img_total", 0),
                page_data.get("img_no_alt", 0),
                page_data.get("internal_links_count", 0),
                page_data.get("external_links_count", 0),
                now,
            ),
        )
        page_id = cur.lastrowid

        # Insert issues
        for issue in all_issues:
            self.conn.execute(
                """INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, page_id, entry.url, issue.category, issue.severity,
                 issue.check_name, issue.message, issue.details),
            )

        self.conn.commit()
        return page_id, images, links

    def _post_process(self, run_id: int) -> None:
        """Detect duplicates (title, meta_description)."""
        for field in ("title", "meta_description"):
            rows = self.conn.execute(
                f"""SELECT {field}, GROUP_CONCAT(url, '||'), COUNT(*) as cnt
                    FROM crawl_pages
                    WHERE run_id = ? AND {field} IS NOT NULL AND {field} != ''
                    GROUP BY {field}
                    HAVING cnt > 1""",
                (run_id,),
            ).fetchall()

            for value, urls_str, count in rows:
                urls_list = urls_str.split("||")
                self.conn.execute(
                    "INSERT INTO crawl_duplicates (run_id, field, value, urls, count) VALUES (?, ?, ?, ?, ?)",
                    (run_id, field, value, json.dumps(urls_list), count),
                )
                for url in urls_list:
                    self.conn.execute(
                        """INSERT INTO crawl_issues (run_id, url, category, severity, check_name, message, details)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (run_id, url, "content", "warning",
                         f"duplicate_{field}",
                         f"{field.replace('_', ' ').title()} duplicato ({count} pagine): \"{value[:80]}\"",
                         json.dumps(urls_list)),
                    )

        self.conn.commit()

    def _post_process_links(
        self, run_id: int,
        all_links: list[tuple[int, str, LinkInfo]],
        status_map: dict[str, int],
    ) -> None:
        """Cross-reference internal links with crawled status codes.
        Optionally check external links with HEAD requests."""
        external_checked: dict[str, int] = {}  # cache per evitare HEAD duplicati

        for page_id, page_url, link in all_links:
            status_code = None
            is_broken = 0
            is_redirect = 0

            if link.is_internal:
                # Cross-reference with already-crawled pages
                status_code = status_map.get(link.target_url)
                if status_code is not None:
                    if status_code >= 400:
                        is_broken = 1
                        for issue in check_broken_link(page_url, link, status_code):
                            self.conn.execute(
                                """INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message, details)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                (run_id, page_id, page_url, issue.category, issue.severity,
                                 issue.check_name, issue.message, issue.details),
                            )
                    elif 300 <= status_code < 400:
                        is_redirect = 1
                        for issue in check_redirect_link(page_url, link, status_code):
                            self.conn.execute(
                                """INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message, details)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                (run_id, page_id, page_url, issue.category, issue.severity,
                                 issue.check_name, issue.message, issue.details),
                            )
            elif self.check_external_links:
                # HEAD request for external links (with cache)
                if link.target_url not in external_checked:
                    head_result = self.fetcher.fetch_head(link.target_url)
                    external_checked[link.target_url] = head_result.status_code
                status_code = external_checked[link.target_url]
                if status_code >= 400:
                    is_broken = 1
                    for issue in check_broken_link(page_url, link, status_code):
                        self.conn.execute(
                            """INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message, details)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (run_id, page_id, page_url, issue.category, issue.severity,
                             issue.check_name, issue.message, issue.details),
                        )

            # Store link
            self.conn.execute(
                """INSERT INTO crawl_links (run_id, source_page_id, target_url, anchor_text, is_internal, rel, status_code, is_broken, is_redirect)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, page_id, link.target_url, link.anchor_text,
                 int(link.is_internal), link.rel, status_code, is_broken, is_redirect),
            )

        self.conn.commit()
        internal_broken = self.conn.execute(
            "SELECT COUNT(*) FROM crawl_links WHERE run_id = ? AND is_internal = 1 AND is_broken = 1", (run_id,)
        ).fetchone()[0]
        if internal_broken:
            print(f"  Link interni rotti: {internal_broken}")

    def _post_process_images(
        self, run_id: int,
        all_images: list[tuple[int, str, ImageInfo]],
    ) -> None:
        """Store image data. HEAD-check a sample for size/format/broken."""
        # Deduplicate image URLs for HEAD checking
        unique_srcs: dict[str, list[tuple[int, str]]] = {}  # src → [(page_id, page_url)]
        for page_id, page_url, img in all_images:
            unique_srcs.setdefault(img.src, []).append((page_id, page_url))

        # HEAD check unique images (limit to avoid hammering)
        MAX_IMAGE_CHECKS = 200
        checked: dict[str, tuple[int, int, str]] = {}  # src → (status, content_length, content_type)
        srcs_to_check = list(unique_srcs.keys())[:MAX_IMAGE_CHECKS]

        if srcs_to_check:
            print(f"  Verificando {len(srcs_to_check)} immagini uniche (HEAD)...")
            for src in srcs_to_check:
                head = self.fetcher.fetch_head(src)
                checked[src] = (head.status_code, head.content_length, head.content_type)

        # Store all images and generate issues
        for page_id, page_url, img in all_images:
            status_code = None
            content_length = None
            content_type = None
            is_broken = 0
            is_oversized = 0

            if img.src in checked:
                status_code, content_length, content_type = checked[img.src]
                if status_code >= 400:
                    is_broken = 1
                if content_length and content_length > 200 * 1024:
                    is_oversized = 1

            self.conn.execute(
                """INSERT INTO crawl_images (run_id, page_id, src, alt, status_code, content_length, content_type, is_broken, is_missing_alt, is_oversized)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, page_id, img.src, img.alt, status_code, content_length,
                 content_type, is_broken, int(img.is_missing_alt), is_oversized),
            )

            # Issues from HEAD checks
            if is_broken:
                for issue in check_broken_image(page_url, img.src, status_code):
                    self.conn.execute(
                        """INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message, details)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (run_id, page_id, page_url, issue.category, issue.severity,
                         issue.check_name, issue.message, issue.details),
                    )
            if is_oversized:
                for issue in check_image_size(page_url, img.src, content_length):
                    self.conn.execute(
                        """INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message, details)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (run_id, page_id, page_url, issue.category, issue.severity,
                         issue.check_name, issue.message, issue.details),
                    )
            if content_type:
                for issue in check_image_format(page_url, img.src, content_type):
                    self.conn.execute(
                        """INSERT INTO crawl_issues (run_id, page_id, url, category, severity, check_name, message, details)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (run_id, page_id, page_url, issue.category, issue.severity,
                         issue.check_name, issue.message, issue.details),
                    )

        self.conn.commit()

    def _print_summary(self, run_id: int) -> None:
        """Print CLI summary."""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM crawl_pages WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        critical = self.conn.execute(
            "SELECT COUNT(*) FROM crawl_issues WHERE run_id = ? AND severity = 'critical'", (run_id,)
        ).fetchone()[0]
        warning = self.conn.execute(
            "SELECT COUNT(*) FROM crawl_issues WHERE run_id = ? AND severity = 'warning'", (run_id,)
        ).fetchone()[0]
        info = self.conn.execute(
            "SELECT COUNT(*) FROM crawl_issues WHERE run_id = ? AND severity = 'info'", (run_id,)
        ).fetchone()[0]
        dupes = self.conn.execute(
            "SELECT COUNT(*) FROM crawl_duplicates WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        imgs_broken = self.conn.execute(
            "SELECT COUNT(*) FROM crawl_images WHERE run_id = ? AND is_broken = 1", (run_id,)
        ).fetchone()[0]
        links_broken = self.conn.execute(
            "SELECT COUNT(*) FROM crawl_links WHERE run_id = ? AND is_broken = 1", (run_id,)
        ).fetchone()[0]

        print(f"\n{'='*50}")
        print(f"CRAWL COMPLETATO — Run #{run_id}")
        print(f"{'='*50}")
        print(f"Pagine crawlate:    {total}")
        print(f"Issue critici:      {critical}")
        print(f"Warning:            {warning}")
        print(f"Info:               {info}")
        print(f"Duplicati:          {dupes}")
        print(f"Immagini rotte:     {imgs_broken}")
        print(f"Link rotti:         {links_broken}")
        print(f"\nUsa 'python -m mnemosyne crawl --report' per il report dettagliato.")
