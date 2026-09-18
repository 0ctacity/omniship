import os
from datetime import datetime

from rich.console import Console
from rich.text import Text

from omniship.core.graph import StageGraph
from omniship.core.logging import (
    Logging,
    LogLevel,
    LogRecord,
    LogStream,
    includes_level,
)
from omniship.core.node import Node
from omniship.core.result import NodeResult, NodeStatus
from omniship.core.stage import Stage


class TerminalUI:
    def __init__(
        self,
        console: Console | None = None,
        logging: Logging | None = None,
    ) -> None:
        self.console = console or Console()
        self.logging = logging or Logging()
        self._github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
        self._current_stage: Stage | None = None
        self._stage_failed = False
        self._printed_stages: set[Stage] = set()
        self._streamed_lines: dict[tuple[Stage, str], list[str]] = {}

    def on_stage_start(self, stage: Stage, graph: StageGraph) -> None:
        self._current_stage = stage
        self.console.print()
        self.console.print(f"[bold cyan]{stage.value.upper()}[/bold cyan]")
        if not graph.nodes:
            self.console.print("  [dim](no nodes defined)[/dim]")

    def on_node_start(self, stage: Stage, node: Node) -> None:
        self.console.print(f"  [cyan]→[/cyan] Starting [bold]{node.id}[/bold]")

    def emit(self, record: LogRecord) -> None:
        self._streamed_lines.setdefault((record.stage, record.task), []).append(
            record.message
        )
        if not includes_level(self.logging.level, record.level):
            return
        if record.stream != LogStream.LOG and not self.logging.show_output:
            return
        timestamp = ""
        if self.logging.timestamps:
            timestamp = (
                f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] "
            )
        style = {
            LogLevel.DEBUG: "dim",
            LogLevel.INFO: "",
            LogLevel.WARNING: "yellow",
            LogLevel.ERROR: "red",
        }[record.level]
        if record.stream == LogStream.STDERR and not style:
            style = "red"
        self.console.print(
            Text(
                f"    [{record.task}] {timestamp}{record.message}",
                style=style,
            )
        )
        if self._github_actions and record.level in {
            LogLevel.WARNING,
            LogLevel.ERROR,
        }:
            command = "warning" if record.level == LogLevel.WARNING else "error"
            title = self._escape_workflow_property(
                self._annotation_title(record.stage, record.task)
            )
            message = self._escape_workflow_data(record.message)
            self.console.print(
                f"::{command} title={title}::{message}",
                markup=False,
            )

    def on_node_finish(self, stage: Stage, node: Node, result: NodeResult) -> None:
        if result.status == NodeStatus.SUCCESS:
            dur = f"{result.duration:.2f}s"
            self.console.print(
                f"  [green]✓[/green] [bold]{node.id:<24}[/bold] [dim]{dur:>8}[/dim]"
            )
        elif result.status == NodeStatus.SKIPPED:
            reason = result.error_message or "skipped"
            self.console.print(
                f"  [yellow]⊘[/yellow] [bold]{node.id:<24}[/bold] [yellow]{reason}[/yellow]"
            )
        elif result.status == NodeStatus.FAILED:
            dur = f"{result.duration:.2f}s"
            self.console.print(
                f"  [red]✗[/red] [bold]{node.id:<24}[/bold] [red]{dur:>8}[/red]"
            )
            if result.error_message:
                self.console.print(f"    [red]Error:[/red] {result.error_message}")
                if self._github_actions:
                    title = self._escape_workflow_property(
                        self._annotation_title(stage, node.id)
                    )
                    message = self._escape_workflow_data(result.error_message)
                    self.console.print(
                        f"::error title={title}::{message}",
                        markup=False,
                    )
        if self.logging.show_output and includes_level(
            self.logging.level,
            LogLevel.INFO,
        ):
            self._print_result_output(stage, node.id, result)

    def on_stage_finish(self, stage: Stage, success: bool) -> None:
        if not success:
            self._stage_failed = True
            self.console.print(f"\n[bold red]{stage.value.upper()} FAILED[/bold red]")
        else:
            self.console.print(
                f"[bold green]{stage.value.upper()} COMPLETE[/bold green]"
            )

    def _print_result_output(
        self,
        stage: Stage,
        task: str,
        result: NodeResult,
    ) -> None:
        streamed = list(self._streamed_lines.get((stage, task), ()))

        def already_streamed(line: str) -> bool:
            try:
                streamed.remove(line)
            except ValueError:
                return False
            return True

        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                if not already_streamed(line):
                    self.console.print(Text(f"    [{task}] {line}"))
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                if not already_streamed(line):
                    self.console.print(Text(f"    [{task}] {line}", style="red"))

    @staticmethod
    def _annotation_title(stage: Stage, task: str) -> str:
        words = task.replace("_", "-").split("-")
        name = " ".join(
            "GitHub" if word.casefold() == "github" else word.title() for word in words
        )
        return f"{stage.value.title()} · {name}"

    @staticmethod
    def _escape_workflow_data(value: str) -> str:
        return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

    @classmethod
    def _escape_workflow_property(cls, value: str) -> str:
        return cls._escape_workflow_data(value).replace(":", "%3A").replace(",", "%2C")

    def print_artifacts(self, artifacts: list) -> None:
        if artifacts:
            self.console.print()
            self.console.print("[bold]Artifacts[/bold]")
            for art in artifacts:
                self.console.print(
                    f"  [green]•[/green] {art.name} [dim]({art.path})[/dim]"
                )
