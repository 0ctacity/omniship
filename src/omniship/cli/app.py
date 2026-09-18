import click

from omniship.cli.build import build_cmd
from omniship.cli.check import check_cmd
from omniship.cli.generate import generate_cmd
from omniship.cli.plan import plan_cmd
from omniship.cli.plugins import plugin_cmd, plugins_cmd
from omniship.cli.run_node import run_node_cmd
from omniship.cli.ship import ship_cmd


@click.group()
def cli() -> None:
    """OmniShip: Next-generation release & build DAG executor."""
    pass


cli.add_command(check_cmd, name="check")
cli.add_command(build_cmd, name="build")
cli.add_command(ship_cmd, name="ship")
cli.add_command(plan_cmd, name="plan")
cli.add_command(plugins_cmd, name="plugins")
cli.add_command(plugin_cmd, name="plugin")
cli.add_command(generate_cmd, name="generate")
cli.add_command(run_node_cmd, name="run-node")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
