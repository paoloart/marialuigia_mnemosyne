from textual.app import App, ComposeResult


class MnemosyneApp(App):
    """TUI pannello di controllo Mnemosyne."""

    TITLE = "Mnemosyne — Maria Luigia"
    CSS = """
    Screen {
        layout: vertical;
    }
    .panel-title {
        text-style: bold;
        color: $accent;
    }
    """

    def on_mount(self) -> None:
        from mnemosyne.tui.screens.dashboard import DashboardScreen
        from mnemosyne.tui.screens.commands import CommandsScreen
        from mnemosyne.tui.screens.claude import ClaudeScreen
        self.install_screen(DashboardScreen(), name="dashboard")
        self.install_screen(CommandsScreen(), name="commands")
        self.install_screen(ClaudeScreen(), name="claude")
        self.push_screen("dashboard")
