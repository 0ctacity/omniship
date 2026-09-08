import sys
import click

from omniship.cli.runner import run_pipeline
from omniship.core.stage import Stage


@click.command()
@click.option("-c", "--config", "config_path", help="Path to configuration file")
def check_cmd(config_path: str | None) -> None:
    """Run only the Check stage."""
    code = run_pipeline([Stage.CHECK], config_path=config_path)
    if code != 0:
        sys.exit(code)
