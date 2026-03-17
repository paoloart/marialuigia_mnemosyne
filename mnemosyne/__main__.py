import sys

from mnemosyne.db.connection import get_connection
from mnemosyne.db.schema import create_tables


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m mnemosyne <command>")
        print("Commands: sync, extract, embeddings")
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

        else:
            print(f"Unknown command: {command}")
            print("Commands: sync, extract, embeddings")
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
