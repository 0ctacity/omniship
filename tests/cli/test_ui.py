from io import StringIO

from rich.console import Console

from omniship.cli.ui import TerminalUI
from omniship.core.logging import Logging, LogLevel, LogRecord
from omniship.core.stage import Stage


def test_terminal_ui_hides_debug_logs_by_default() -> None:
    output = StringIO()
    ui = TerminalUI(console=Console(file=output, force_terminal=False))

    ui.emit(LogRecord(Stage.CHECK, "lint", LogLevel.DEBUG, "details"))
    ui.emit(LogRecord(Stage.CHECK, "lint", LogLevel.INFO, "visible"))

    assert "details" not in output.getvalue()
    assert "[lint] visible" in output.getvalue()


def test_terminal_ui_renders_github_warning_annotations(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    output = StringIO()
    ui = TerminalUI(
        console=Console(file=output, force_terminal=False),
        logging=Logging(level=LogLevel.WARNING),
    )

    ui.emit(LogRecord(Stage.BUILD, "package", LogLevel.WARNING, "Check output"))

    assert "::warning title=Build · Package::Check output" in output.getvalue()
