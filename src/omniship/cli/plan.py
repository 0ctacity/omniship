import sys
from pathlib import Path
import click
from rich.console import Console
from rich.tree import Tree

from omniship.config.loader import find_config_file, load_and_validate
from omniship.core.graph import StageGraph
from omniship.core.stage import Stage
from omniship.plugins.discovery import load_plugins


def print_plan(graphs: dict[Stage, StageGraph], console: Console | None = None) -> None:
    console = console or Console()

    console.print("[bold]OmniShip Execution Plan[/bold]\n")

    for stage in (Stage.CHECK, Stage.BUILD, Stage.SHIP):
        graph = graphs.get(stage)
        console.print(f"[bold cyan]{stage.value.upper()}[/bold cyan]")
        if not graph or not graph.nodes:
            console.print("  [dim](empty)[/dim]\n")
            continue

        roots = graph.get_roots()
        if roots:
            for root in sorted(roots, key=lambda n: n.id):
                root_tree = Tree(f"[bold]{root.id}[/bold] [dim]({root.operation_name})[/dim]")
                _add_children(root.id, root_tree, graph, set())
                console.print(root_tree)
        else:
            for node_id, node in sorted(graph.nodes.items()):
                console.print(f"  • {node_id} [dim]({node.operation_name})[/dim]")
        console.print()


def _add_children(node_id: str, tree: Tree, graph: StageGraph, visited: set[str]) -> None:
    if node_id in visited:
        return
    visited.add(node_id)
    dependents = sorted(graph.get_direct_dependents(node_id))
    for dep_id in dependents:
        node = graph.nodes[dep_id]
        branch = tree.add(f"[bold]{node.id}[/bold] [dim]({node.operation_name})[/dim]")
        _add_children(dep_id, branch, graph, visited.copy())


@click.command(name="plan")
@click.option("-c", "--config", "config_path", help="Path to configuration file")
def plan_cmd(config_path: str | None) -> None:
    """Inspect the execution plan and dependency DAG."""
    console = Console()
    registry = load_plugins()
    path = Path(config_path) if config_path else find_config_file()
    if not path or not path.is_file():
        console.print("[bold red]Error:[/bold red] No omniship.yaml configuration file found.")
        sys.exit(1)

    try:
        _, graphs = load_and_validate(path, registry)
    except Exception as exc:
        console.print(f"[bold red]Configuration Error:[/bold red] {exc}")
        sys.exit(1)

    print_plan(graphs, console)
