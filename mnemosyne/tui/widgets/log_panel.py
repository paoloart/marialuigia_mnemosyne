from textual.app import ComposeResult
from textual.widgets import RichLog
from textual.widget import Widget
from textual.css.query import NoMatches


class LogPanel(Widget):
    """Pannello scrollabile per log output con colori."""

    DEFAULT_CSS = """
    LogPanel {
        height: 100%;
        border: solid $surface-darken-1;
    }
    """

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, wrap=True, id="log-output")

    def write(self, text: str, style: str = "white") -> None:
        """Aggiunge una riga al log con lo stile specificato."""
        try:
            log = self.query_one("#log-output", RichLog)
            log.write(f"[{style}]{text}[/{style}]")
        except NoMatches:
            pass

    def write_error(self, text: str) -> None:
        self.write(text, style="red")

    def write_success(self, text: str) -> None:
        self.write(text, style="green")

    def write_info(self, text: str) -> None:
        self.write(text, style="cyan")

    def clear(self) -> None:
        try:
            self.query_one("#log-output", RichLog).clear()
        except NoMatches:
            pass
