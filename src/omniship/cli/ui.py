from rich.console import Console

from omniship.core.graph import StageGraph
from omniship.core.node import Node
from omniship.core.result import NodeResult, NodeStatus
from omniship.core.stage import Stage


class TerminalUI:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self._current_stage: Stage | None = None
        self._stage_failed = False
        self._printed_stages: set[Stage] = set()

    def on_stage_start(self, stage: Stage, graph: StageGraph) -> None:
        self._current_stage = stage
        self.console.print()
        self.console.print(f"[bold cyan]{stage.value.upper()}[/bold cyan]")
        if not graph.nodes:
            self.console.print("  [dim](no nodes defined)[/dim]")

    def on_node_start(self, stage: Stage, node: Node) -> None:
        pass

    def on_node_finish(self, stage: Stage, node: Node, result: NodeResult) -> None:
        if result.status == NodeStatus.SUCCESS:
            dur = f"{result.duration:.2f}s"
            self.console.print(f"  [green]✓[/green] [bold]{node.id:<24}[/bold] [dim]{dur:>8}[/dim]")
        elif result.status == NodeStatus.SKIPPED:
            reason = result.error_message or "skipped"
            self.console.print(f"  [yellow]⊘[/yellow] [bold]{node.id:<24}[/bold] [yellow]{reason}[/yellow]")
        elif result.status == NodeStatus.FAILED:
            dur = f"{result.duration:.2f}s"
            self.console.print(f"  [red]✗[/red] [bold]{node.id:<24}[/bold] [red]{dur:>8}[/red]")
            if result.error_message:
                self.console.print(f"    [red]Error:[/red] {result.error_message}")
            if result.stdout.strip():
                self.console.print("    [dim]--- stdout ---[/dim]")
                for line in result.stdout.strip().splitlines():
                    self.console.print(f"    {line}")
            if result.stderr.strip():
                self.console.print("    [dim]--- stderr ---[/dim]")
                for line in result.stderr.strip().splitlines():
                    self.console.print(f"    [red]{line}[/red]")

    def on_stage_finish(self, stage: Stage, success: bool) -> None:
        if not success:
            self._stage_failed = True
            self.console.print(f"\n[bold red]{stage.value.upper()} FAILED[/bold red]")

    def print_artifacts(self, artifacts: list) -> None:
        if artifacts:
            self.console.print()
            self.console.print("[bold]Artifacts[/bold]")
            for art in artifacts:
                self.console.print(f"  [green]•[/green] {art.name} [dim]({art.path})[/dim]")
