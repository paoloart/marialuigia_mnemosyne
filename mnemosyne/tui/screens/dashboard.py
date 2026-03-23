import asyncio
from datetime import datetime
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, Label
from textual.containers import Horizontal, Vertical
from mnemosyne.tui.widgets.log_panel import LogPanel
from mnemosyne.tui.widgets.status_panel import (
    fetch_db_stats,
    fetch_embedding_status,
    fetch_seo_summary,
    fetch_cluster_info,
    fetch_ga4_stats,
    fetch_gsc_stats,
)
from mnemosyne import config
from mnemosyne.db.connection import get_connection


class DashboardScreen(Widget):
    """Screen principale con stato del sistema."""

    DEFAULT_CSS = """
    DashboardScreen {
        height: 100%;
    }
    .panel {
        border: solid $surface-darken-1;
        padding: 1;
        height: 1fr;
    }
    .panel-title {
        text-style: bold;
        color: $accent;
    }
    #columns {
        height: 1fr;
    }
    #log-section {
        height: 8;
        border: solid $surface-darken-1;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="columns"):
                with Vertical(classes="panel"):
                    yield Label("DB STATUS", classes="panel-title")
                    yield Static("Caricamento...", id="db-stats")
                with Vertical(classes="panel"):
                    yield Label("SEO AUDIT", classes="panel-title")
                    yield Static("Caricamento...", id="seo-stats")
                with Vertical(classes="panel"):
                    yield Label("GA4 / GSC", classes="panel-title")
                    yield Static("Caricamento...", id="ga4-stats")
            with Vertical(id="log-section"):
                yield Label("LOG RECENTI", classes="panel-title")
                yield LogPanel(id="dash-log")

    def on_mount(self) -> None:
        self.set_interval(30, self._refresh_stats)
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        self.run_worker(self._fetch_and_update(), exclusive=True, name="dash-refresh")

    async def _fetch_and_update(self) -> None:
        log = self.query_one("#dash-log", LogPanel)

        # DB e SEO — critici, mostra errore se falliscono
        try:
            db_result, seo_result = await asyncio.gather(
                asyncio.to_thread(self._fetch_db_data),
                asyncio.to_thread(self._fetch_seo_data),
            )
            db_stats, emb_status = db_result
            seo_summary, cluster_info = seo_result
            self._update_db_panel(db_stats, emb_status)
            self._update_seo_panel(seo_summary, cluster_info)
        except Exception as e:
            log.write_error(f"[{datetime.now().strftime('%H:%M')}] Errore DB/SEO: {e}")

        # GA4/GSC — opzionali, falliscono silenziosamente (ritornano None)
        try:
            ga4_data, gsc_data = await asyncio.gather(
                asyncio.to_thread(fetch_ga4_stats),
                asyncio.to_thread(fetch_gsc_stats),
            )
            self._update_ga4_panel(ga4_data, gsc_data)
        except Exception:
            self._update_ga4_panel(None, None)

    @staticmethod
    def _fetch_db_data() -> tuple:
        conn = get_connection(config.get_db_path())
        try:
            return fetch_db_stats(conn), fetch_embedding_status(conn)
        finally:
            conn.close()

    @staticmethod
    def _fetch_seo_data() -> tuple:
        conn = get_connection(config.get_db_path())
        try:
            return fetch_seo_summary(conn), fetch_cluster_info(conn)
        finally:
            conn.close()

    def _update_db_panel(self, stats: dict, emb: dict) -> None:
        text = (
            f"Posts: {stats['total_posts']}\n"
            f"Embeddings:\n"
            f"  current: {emb['current']}\n"
            f"  pending: {emb['pending']}\n"
            f"  da gen.: {emb['not_generated']}\n"
            f"Last sync:\n  {(stats['last_sync'] or 'mai')[:10]}"
        )
        self.query_one("#db-stats", Static).update(text)

    def _update_seo_panel(self, seo: dict, cluster: dict) -> None:
        text = (
            f"Orphan: {seo['orphan']}\n"
            f"Thin: {seo['thin']}\n"
            f"No meta: {seo['missing_meta']}\n"
            f"H-issues: {seo['heading_issues']}\n"
            f"Cornerstone: {cluster['cornerstone']}"
        )
        self.query_one("#seo-stats", Static).update(text)

    def _update_ga4_panel(self, ga4: dict | None, gsc: dict | None) -> None:
        ga4_text = "GA4: N/D"
        if ga4:
            sessions = ga4.get("sessions", {}).get("value", "?")
            users = ga4.get("users", {}).get("value", "?")
            pageviews = ga4.get("pageviews", {}).get("value", "?")
            ga4_text = f"GA4 (7d)\nSessions: {sessions}\nUsers: {users}\nPageviews: {pageviews}"

        gsc_text = "GSC: N/D"
        if gsc:
            clicks = gsc.get("clicks", {}).get("value", "?")
            impressions = gsc.get("impressions", {}).get("value", "?")
            ctr = gsc.get("ctr", {}).get("value", "?")
            pos = gsc.get("position", {}).get("value", "?")
            ctr_pct = f"{ctr * 100:.1f}%" if isinstance(ctr, float) else "?"
            pos_fmt = f"{pos:.1f}" if isinstance(pos, float) else "?"
            gsc_text = f"GSC (7d)\nClicks: {clicks}\nImpr: {impressions}\nCTR: {ctr_pct}\nPos: {pos_fmt}"

        self.query_one("#ga4-stats", Static).update(f"{ga4_text}\n\n{gsc_text}")
