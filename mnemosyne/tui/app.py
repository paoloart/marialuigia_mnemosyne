from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane


class MnemosyneApp(App):
    """TUI pannello di controllo Mnemosyne."""

    TITLE = "Mnemosyne — Maria Luigia"
    CSS = """
    Screen {
        layout: vertical;
    }
    TabbedContent {
        height: 1fr;
    }
    TabbedContent ContentSwitcher {
        height: 1fr;
    }
    TabPane {
        height: 1fr;
        padding: 0;
    }
    DashboardScreen, CommandsScreen, ClaudeScreen {
        height: 1fr;
    }
    """
    BINDINGS = [
        ("1", "show_tab('dashboard')", "Dashboard"),
        ("2", "show_tab('commands')", "Comandi"),
        ("3", "show_tab('claude')", "Claude"),
        ("q", "quit", "Esci"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="dashboard"):
            with TabPane("Dashboard", id="dashboard"):
                # Screen caricata lazy per evitare import circolari
                from mnemosyne.tui.screens.dashboard import DashboardScreen
                yield DashboardScreen()
            with TabPane("Comandi", id="commands"):
                from mnemosyne.tui.screens.commands import CommandsScreen
                yield CommandsScreen()
            with TabPane("Claude", id="claude"):
                from mnemosyne.tui.screens.claude import ClaudeScreen
                yield ClaudeScreen()
        yield Footer()

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id
