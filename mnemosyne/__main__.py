import sys

from mnemosyne.db.connection import get_connection
from mnemosyne.db.schema import create_tables


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m mnemosyne <command>")
        print("Commands: sync, extract, embeddings, seo, refresh-analytics, crawl, dashboard")
        sys.exit(1)

    command = sys.argv[1]

    # Late imports to avoid loading config (and requiring .env) at import time
    from mnemosyne import config

    if command == "dashboard":
        import subprocess
        import os
        app_path = os.path.join(os.path.dirname(__file__), "dashboard", "app.py")
        subprocess.run(["streamlit", "run", app_path, "--server.headless", "true"])
        return

    conn = get_connection(config.get_db_path())
    create_tables(conn)

    try:
        if command == "sync":
            from mnemosyne.scraper.wp_client import WPClient
            from mnemosyne.scraper.sync import sync_all

            client = WPClient(
                base_url=config.get_wp_base_url(),
                username=config.get_wp_username(),
                app_password=config.get_wp_app_password(),
                retry_max=config.get_retry_max(),
            )
            sync_all(conn, client, delay=config.get_sync_delay())

        elif command == "extract":
            from mnemosyne.scraper.extract import extract_all
            from urllib.parse import urlparse

            domain = urlparse(config.get_wp_base_url()).netloc
            extract_all(conn, site_domain=domain)

        elif command == "embeddings":
            from openai import OpenAI
            from mnemosyne.embeddings.generator import generate_embeddings

            client = OpenAI(api_key=config.get_openai_api_key())
            generate_embeddings(conn, client)

        elif command == "seo":
            from mnemosyne.seo.audit import (
                posts_summary, posts_missing_meta, posts_thin_content,
                posts_no_internal_links, posts_no_inbound_links,
                heading_issues, embedding_status_report, print_table,
            )

            subcommand = sys.argv[2] if len(sys.argv) > 2 else "audit"

            if subcommand == "summary":
                rows = posts_summary(conn)
                print_table(rows, ["id", "title", "word_count", "heading_count", "outgoing_links", "incoming_links"])

            elif subcommand == "thin":
                min_words = int(sys.argv[3]) if len(sys.argv) > 3 else 500
                rows = posts_thin_content(conn, min_words)
                print(f"\nPost con meno di {min_words} parole: {len(rows)}\n")
                print_table(rows, ["id", "title", "word_count"])

            elif subcommand == "orphans":
                print("\n--- Post senza link interni in uscita ---")
                rows = posts_no_internal_links(conn)
                print(f"Trovati: {len(rows)}\n")
                print_table(rows, ["id", "title", "word_count"])

                print("\n--- Post senza link interni in entrata ---")
                rows = posts_no_inbound_links(conn)
                print(f"Trovati: {len(rows)}\n")
                print_table(rows, ["id", "title", "word_count"])

            elif subcommand == "headings":
                rows = heading_issues(conn)
                print(f"\nProblemi di heading: {len(rows)}\n")
                print_table(rows, ["id", "title", "word_count", "issue"])

            elif subcommand == "meta":
                rows = posts_missing_meta(conn)
                print(f"\nPost senza meta description: {len(rows)}\n")
                print_table(rows, ["id", "title", "word_count"])

            elif subcommand == "embeddings":
                report = embedding_status_report(conn)
                print(f"\nEmbedding status:")
                for k, v in report.items():
                    print(f"  {k}: {v}")

            elif subcommand == "audit":
                # Full audit
                print("=" * 60)
                print("SEO AUDIT — ospedalemarialuigia.it")
                print("=" * 60)

                report = embedding_status_report(conn)
                print(f"\nPost totali: {report['total']}")
                print(f"Embeddings: {report['current']} current, {report['pending']} pending, {report['not_generated']} da generare")

                rows = posts_missing_meta(conn)
                print(f"\nPost senza meta description: {len(rows)}")

                rows = posts_thin_content(conn)
                print(f"Post con meno di 500 parole: {len(rows)}")

                rows = posts_no_internal_links(conn)
                print(f"Post senza link interni in uscita: {len(rows)}")

                rows = posts_no_inbound_links(conn)
                print(f"Post senza link interni in entrata: {len(rows)}")

                rows = heading_issues(conn)
                print(f"Post con problemi di heading: {len(rows)}")

            else:
                print(f"Unknown seo subcommand: {subcommand}")
                print("Subcommands: audit, summary, thin, orphans, headings, meta, embeddings")
                sys.exit(1)

        elif command == "refresh-analytics":
            from mnemosyne.analytics.semantic_map import generate_semantic_map
            generate_semantic_map(conn)

        elif command == "crawl":
            from mnemosyne.crawler.engine import CrawlEngine

            if "--report" in sys.argv:
                _print_crawl_report(conn)
            elif "--history" in sys.argv:
                _print_crawl_history(conn)
            elif "--diff" in sys.argv:
                from mnemosyne.crawler.diff import compare_runs, print_diff
                old_id = int(_get_flag("--diff", "0"))
                new_id = int(_get_flag("--vs", "0"))
                if not old_id or not new_id:
                    print("Usage: python -m mnemosyne crawl --diff <old_run_id> --vs <new_run_id>")
                    sys.exit(1)
                diff = compare_runs(conn, old_id, new_id)
                print_diff(diff)
            elif "--prioritize" in sys.argv:
                from mnemosyne.crawler.prioritize import prioritize_issues, print_prioritized
                from mnemosyne.dashboard.gsc_client import get_top_pages
                run_id = int(_get_flag("--prioritize", "0"))
                if not run_id:
                    # Use latest run
                    row = conn.execute("SELECT id FROM crawl_runs ORDER BY id DESC LIMIT 1").fetchone()
                    run_id = row[0] if row else 0
                if not run_id:
                    print("Nessun crawl trovato.")
                    sys.exit(1)
                print(f"Caricando dati GSC per run #{run_id}...")
                gsc_data = get_top_pages(config.get_google_credentials_path(), limit=500)
                issues = prioritize_issues(conn, run_id, gsc_data)
                print_prioritized(issues)
            else:
                DEFAULT_SITEMAP = config.get_wp_base_url() + "/sitemap_index.xml"
                sitemap_source = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else DEFAULT_SITEMAP
                workers = int(_get_flag("--workers", "5"))
                delay = float(_get_flag("--delay", "0.5"))
                check_ext = "--check-external" in sys.argv

                engine = CrawlEngine(
                    conn, sitemap_source,
                    max_workers=workers, delay=delay,
                    check_external_links=check_ext,
                )
                run_id = engine.run()
                if run_id:
                    print(f"\nCrawl completato! Run ID: {run_id}")

        else:
            print(f"Unknown command: {command}")
            print("Commands: sync, extract, embeddings, seo, refresh-analytics, crawl, tui")
            sys.exit(1)
    finally:
        conn.close()


def _get_flag(flag: str, default: str) -> str:
    """Extract --flag value from sys.argv."""
    try:
        idx = sys.argv.index(flag)
        return sys.argv[idx + 1]
    except (ValueError, IndexError):
        return default


def _print_crawl_report(conn):
    """Print the last crawl report to CLI."""
    row = conn.execute(
        "SELECT id, started_at, finished_at, sitemap_url, total_urls, crawled_urls, status "
        "FROM crawl_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        print("Nessun crawl trovato.")
        return

    run_id = row[0]
    print(f"\n{'='*60}")
    print(f"REPORT CRAWL — Run #{run_id} ({row[5]} pagine)")
    print(f"{'='*60}")
    print(f"Sitemap: {row[3]}")
    print(f"Inizio:  {row[1]}")
    print(f"Fine:    {row[2]}")
    print(f"Status:  {row[6]}")

    # Issues by severity
    for sev in ("critical", "warning", "info"):
        issues = conn.execute(
            "SELECT check_name, message FROM crawl_issues WHERE run_id = ? AND severity = ? LIMIT 20",
            (run_id, sev),
        ).fetchall()
        if issues:
            label = {"critical": "CRITICI", "warning": "WARNING", "info": "INFO"}[sev]
            print(f"\n--- {label} ({len(issues)}) ---")
            for check, msg in issues:
                print(f"  [{check}] {msg}")

    # Duplicates
    dupes = conn.execute(
        "SELECT field, value, count FROM crawl_duplicates WHERE run_id = ?", (run_id,)
    ).fetchall()
    if dupes:
        print(f"\n--- DUPLICATI ---")
        for field, value, count in dupes:
            print(f"  {field}: \"{value[:60]}\" ({count} pagine)")


def _print_crawl_history(conn):
    """Print crawl history."""
    rows = conn.execute(
        "SELECT id, started_at, total_urls, crawled_urls, status FROM crawl_runs ORDER BY id DESC LIMIT 10"
    ).fetchall()
    if not rows:
        print("Nessun crawl trovato.")
        return

    print(f"\n{'ID':>4}  {'Data':>20}  {'URL':>6}  {'Crawl':>6}  {'Status'}")
    print("-" * 55)
    for rid, started, total, crawled, status in rows:
        print(f"{rid:>4}  {started[:19]:>20}  {total:>6}  {crawled:>6}  {status}")


if __name__ == "__main__":
    main()
