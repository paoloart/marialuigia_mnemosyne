import asyncio
import subprocess
import shutil
from datetime import datetime
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Input, Static
from textual.containers import Vertical
from textual.binding import Binding
from mnemosyne.tui.widgets.log_panel import LogPanel


class ClaudeScreen(Widget):
    """Screen per chat con Claude Code."""

    DEFAULT_CSS = """
    ClaudeScreen {
        height: 100%;
    }
    #chat-log {
        height: 1fr;
        border: solid $surface-darken-1;
    }
    #input-row {
        height: 3;
        padding: 1;
    }
    #chat-input {
        width: 1fr;
    }
    #hint {
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+o", "open_interactive", "Sessione interattiva"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            with Vertical(id="chat-log"):
                yield LogPanel(id="claude-log")
            with Vertical(id="input-row"):
                yield Input(placeholder="Scrivi un prompt per Claude...", id="chat-input")
            yield Static("[dim]Invio: invia prompt  |  Ctrl+O: apri sessione interattiva  |  (richiede claude in PATH)[/dim]", id="hint", markup=True)

    def on_mount(self) -> None:
        claude_path = shutil.which("claude")
        if not claude_path:
            log = self.query_one("#claude-log", LogPanel)
            log.write_error("Claude Code non trovato in PATH. Installa claude-code.")
        self.query_one("#chat-input", Input).focus()

    def on_show(self) -> None:
        self.query_one("#chat-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        event.input.value = ""
        log = self.query_one("#claude-log", LogPanel)
        log.write_info(f"[{datetime.now().strftime('%H:%M:%S')}] > {prompt}")
        self.run_worker(self._ask_claude(prompt, log), exclusive=True, name="claude-query")

    async def _ask_claude(self, prompt: str, log: LogPanel) -> None:
        claude_path = shutil.which("claude")
        if not claude_path:
            log.write_error("Claude Code non trovato in PATH.")
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                claude_path, "-p", prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if stdout:
                log.write(stdout.decode("utf-8", errors="replace"))
            if stderr and proc.returncode != 0:
                log.write_error(stderr.decode("utf-8", errors="replace"))
        except Exception as e:
            log.write_error(f"Errore subprocess: {e}")

    async def action_open_interactive(self) -> None:
        """Apre una sessione Claude Code interattiva sospendendo la TUI."""
        claude_path = shutil.which("claude")
        if not claude_path:
            log = self.query_one("#claude-log", LogPanel)
            log.write_error("Claude Code non trovato in PATH.")
            return
        # app.suspend() cede il controllo del terminale al processo figlio
        # e lo riprende quando l'utente esce dalla sessione Claude.
        # Funziona su macOS Terminal, iTerm2, tmux. Non garantito in CI.
        with self.app.suspend():
            subprocess.run([claude_path])
