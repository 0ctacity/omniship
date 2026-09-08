import sys
import click

from omniship.cli.runner import run_pipeline
from omniship.core.stage import Stage


@click.command()
@click.option("--skip-check", is_flag=True, default=False, help="Skip the Check stage")
@click.option("--skip-build", is_flag=True, default=False, help="Skip the Build stage")
@click.option("-c", "--config", "config_path", help="Path to configuration file")
def ship_cmd(skip_check: bool, skip_build: bool, config_path: str | None) -> None:
    """Run Check -> Build -> Ship (complete release flow)."""
    stages: list[Stage] = []
    if not skip_check:
        stages.append(Stage.CHECK)
    if not skip_build:
        stages.append(Stage.BUILD)
    stages.append(Stage.SHIP)

    code = run_pipeline(stages, config_path=config_path)
    if code != 0:
        sys.exit(code)
