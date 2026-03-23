import asyncio
import contextlib
import io
import shutil
from datetime import datetime
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, Label, Button
from textual.containers import Horizontal, Vertical
from mnemosyne.tui.widgets.log_panel import LogPanel
from mnemosyne import config
from mnemosyne.db.connection import get_connection
from mnemosyne.db.schema import create_tables


def _run_with_capture(fn, *args) -> str:
    """Esegue fn(*args) catturando stdout (print-based). Ritorna l'output come stringa."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


class CommandsScreen(Widget):
    """Screen per triggerare i comandi pipeline."""

    DEFAULT_CSS = """
    CommandsScreen {
        height: 100%;
    }
    #cmd-list {
        width: 30;
        border: solid $surface-darken-1;
        padding: 1;
    }
    #cmd-output {
        width: 1fr;
        height: 100%;
    }
    Button {
        width: 100%;
        margin-bottom: 1;
    }
    Button.running {
        background: $warning;
    }
    Button.done {
        background: $success;
    }
    Button.error {
        background: $error;
    }
    """

    _running: bool = False

    def on_mount(self) -> None:
        self._running = False

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="cmd-list"):
                yield Label("PIPELINE", classes="panel-title")
                yield Button("[S] Sync WP", id="btn-sync", variant="default")
                yield Button("[E] Extract", id="btn-extract", variant="default")
                yield Button("[B] Embeddings", id="btn-embeddings", variant="default")
                yield Button("[A] Analytics", id="btn-analytics", variant="default")
                yield Button("[U] SEO Audit", id="btn-seo", variant="default")
                yield Button("[K] Backup DB", id="btn-backup", variant="default")
            with Vertical(id="cmd-output"):
                yield LogPanel(id="cmd-log")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._running:
            return
        btn_id = event.button.id
        commands = {
            "btn-sync": self._run_sync,
            "btn-extract": self._run_extract,
            "btn-embeddings": self._run_embeddings,
            "btn-analytics": self._run_analytics,
            "btn-seo": self._run_seo,
            "btn-backup": self._run_backup,
        }
        if btn_id in commands:
            self.run_worker(self._execute(btn_id, commands[btn_id]), exclusive=True)

    async def _execute(self, btn_id: str, fn) -> None:
        self._running = True
        log = self.query_one("#cmd-log", LogPanel)
        btn = self.query_one(f"#{btn_id}", Button)
        btn.remove_class("done", "error")
        btn.add_class("running")
        log.write_info(f"[{datetime.now().strftime('%H:%M:%S')}] Avvio {btn_id}...")
        try:
            output = await fn()
            log.write(output)
            log.write_success(f"[{datetime.now().strftime('%H:%M:%S')}] Completato.")
            btn.remove_class("running")
            btn.add_class("done")
        except Exception as e:
            log.write_error(f"[{datetime.now().strftime('%H:%M:%S')}] Errore: {e}")
            btn.remove_class("running")
            btn.add_class("error")
        finally:
            self._running = False

    async def _run_sync(self) -> str:
        from mnemosyne.scraper.wp_client import WPClient
        from mnemosyne.scraper.sync import sync_all
        def _do():
            conn = get_connection(config.get_db_path())
            create_tables(conn)
            try:
                client = WPClient(
                    base_url=config.get_wp_base_url(),
                    username=config.get_wp_username(),
                    app_password=config.get_wp_app_password(),
                    retry_max=config.get_retry_max(),
                )
                return _run_with_capture(sync_all, conn, client, config.get_sync_delay())
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def _run_extract(self) -> str:
        from mnemosyne.scraper.extract import extract_all
        from urllib.parse import urlparse
        def _do():
            conn = get_connection(config.get_db_path())
            try:
                domain = urlparse(config.get_wp_base_url()).netloc
                return _run_with_capture(extract_all, conn, domain)
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def _run_embeddings(self) -> str:
        from openai import OpenAI
        from mnemosyne.embeddings.generator import generate_embeddings
        def _do():
            conn = get_connection(config.get_db_path())
            try:
                client = OpenAI(api_key=config.get_openai_api_key())
                return _run_with_capture(generate_embeddings, conn, client)
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def _run_analytics(self) -> str:
        from mnemosyne.analytics.semantic_map import generate_semantic_map
        def _do():
            conn = get_connection(config.get_db_path())
            try:
                return _run_with_capture(generate_semantic_map, conn)
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def _run_seo(self) -> str:
        from mnemosyne.seo.audit import (
            embedding_status_report, posts_missing_meta,
            posts_thin_content, posts_no_internal_links,
            posts_no_inbound_links, heading_issues,
        )
        def _do():
            conn = get_connection(config.get_db_path())
            try:
                report = embedding_status_report(conn)
                lines = [
                    "SEO AUDIT",
                    "=" * 40,
                    f"Post totali: {report['total']}",
                    f"Embeddings: {report['current']} current, {report['pending']} pending",
                    f"Senza meta description: {len(posts_missing_meta(conn))}",
                    f"Thin content (<500): {len(posts_thin_content(conn))}",
                    f"Orphan (no outgoing): {len(posts_no_internal_links(conn))}",
                    f"Dead ends (no inbound): {len(posts_no_inbound_links(conn))}",
                    f"Heading issues: {len(heading_issues(conn))}",
                ]
                return "\n".join(lines)
            finally:
                conn.close()
        return await asyncio.to_thread(_do)

    async def _run_backup(self) -> str:
        import os
        def _do():
            db_path = config.get_db_path()
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = db_path.replace(".db", f"_backup_{date_str}.db")
            shutil.copy2(db_path, backup_path)
            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            return f"Backup salvato: {backup_path} ({size_mb:.1f} MB)"
        return await asyncio.to_thread(_do)
