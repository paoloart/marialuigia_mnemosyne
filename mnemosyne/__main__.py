import sys

from mnemosyne.db.connection import get_connection
from mnemosyne.db.schema import create_tables


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m mnemosyne <command>")
        print("Commands: sync, extract, embeddings, seo, refresh-analytics, tui")
        sys.exit(1)

    command = sys.argv[1]

    # Late imports to avoid loading config (and requiring .env) at import time
    from mnemosyne import config

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

        elif command == "tui":
            from mnemosyne.tui.app import MnemosyneApp
            app = MnemosyneApp()
            app.run()

        else:
            print(f"Unknown command: {command}")
            print("Commands: sync, extract, embeddings, seo, refresh-analytics, tui")
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
