import click
from rich.console import Console
from rich.table import Table

from omniship.plugins.discovery import load_plugins
from omniship.plugins.template import generate_operation_template


@click.group(name="plugins", invoke_without_command=True)
@click.pass_context
def plugins_cmd(ctx: click.Context) -> None:
    """List available plugins and operations."""
    if ctx.invoked_subcommand is None:
        console = Console()
        registry = load_plugins()
        ops = registry.list_operations()

        table = Table(title="Registered Operations")
        table.add_column("Operation", style="bold cyan")
        table.add_column("Stages", style="green")
        table.add_column("Cacheable", style="magenta")
        table.add_column("Description")

        for op in sorted(ops, key=lambda x: x.name):
            stages_str = ", ".join(s.value for s in sorted(op.stages))
            table.add_row(
                op.name,
                stages_str,
                "yes" if op.cacheable else "no",
                op.description,
            )

        console.print(table)


@click.group(name="plugin")
def plugin_cmd() -> None:
    """Inspect or generate templates for operations."""
    pass


@plugin_cmd.command(name="show")
@click.argument("name")
def plugin_show(name: str) -> None:
    """Show details for an operation."""
    console = Console()
    registry = load_plugins()
    definition = registry.get_definition(name)
    if not definition:
        console.print(f"[bold red]Error:[/bold red] Operation '{name}' not found.")
        return

    console.print(f"[bold cyan]Operation:[/bold cyan] {definition.name}")
    console.print(f"[bold]Description:[/bold] {definition.description}")
    console.print(f"[bold]Allowed Stages:[/bold] {', '.join(s.value for s in definition.stages)}")
    console.print(f"[bold]Cacheable:[/bold] {'yes' if definition.cacheable else 'no'}")
    if definition.config_model:
        console.print("\n[bold]Configuration Template:[/bold]")
        console.print(generate_operation_template(definition))


@plugin_cmd.command(name="template")
@click.argument("name")
def plugin_template(name: str) -> None:
    """Generate example YAML configuration for an operation."""
    console = Console()
    registry = load_plugins()
    definition = registry.get_definition(name)
    if not definition:
        console.print(f"[bold red]Error:[/bold red] Operation '{name}' not found.")
        return

    console.print(generate_operation_template(definition), end="")
