import asyncio
from pathlib import Path

from rich.console import Console

from omniship.cli.ui import TerminalUI
from omniship.config.loader import find_config_file, load_and_validate
from omniship.core.context import ExecutionContext
from omniship.core.executor import StageExecutor
from omniship.core.stage import Stage
from omniship.plugins.discovery import load_plugins


def run_pipeline(
    stages_to_run: list[Stage],
    config_path: str | None = None,
    console: Console | None = None,
) -> int:
    console = console or Console()
    console.print("[bold]OmniShip v0.1.0[/bold]")

    # 1. Load plugins
    registry = load_plugins()

    # 2. Locate config
    path = Path(config_path) if config_path else find_config_file()
    if not path or not path.is_file():
        console.print("[bold red]Error:[/bold red] No omniship.yaml configuration file found.")
        return 1

    # 3. Load & validate configuration
    try:
        config, graphs = load_and_validate(path, registry)
    except Exception as exc:
        console.print(f"[bold red]Configuration Error:[/bold red] {exc}")
        return 1

    # 4. Set up context and executor
    workspace_root = path.parent.resolve()
    context = ExecutionContext(
        workspace_root=workspace_root,
        stage=stages_to_run[0],
    )

    ui = TerminalUI(console=console)
    executor = StageExecutor(registry=registry, listeners=[ui])

    async def _execute() -> bool:
        graphs_to_execute = [graphs[st] for st in stages_to_run if st in graphs]
        for g in graphs_to_execute:
            context.stage = g.stage
            success = await executor.execute_stage(g, context)
            if g.stage == Stage.BUILD and context.artifacts:
                ui.print_artifacts(context.artifacts.to_list())
            if not success:
                return False
        return True

    success = asyncio.run(_execute())

    if success:
        if Stage.SHIP in stages_to_run:
            console.print("\n[bold green]Shipped successfully![/bold green]")
        else:
            console.print(f"\n[bold green]{stages_to_run[-1].value.capitalize()} completed successfully![/bold green]")
        return 0
    else:
        return 1
