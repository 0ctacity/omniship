import sys

import click

from omniship.cli.runner import run_pipeline
from omniship.core.stage import Stage


@click.command()
@click.option("--skip-check", is_flag=True, default=False, help="Skip the Check stage")
@click.option("-c", "--config", "config_path", help="Path to configuration file")
@click.option(
    "--export-artifacts",
    "artifact_export_path",
    help="Export build artifacts for a later Ship stage",
)
def build_cmd(
    skip_check: bool,
    config_path: str | None,
    artifact_export_path: str | None,
) -> None:
    """Run Check -> Build (or only Build if --skip-check)."""
    stages = [Stage.BUILD] if skip_check else [Stage.CHECK, Stage.BUILD]
    code = run_pipeline(
        stages,
        config_path=config_path,
        artifact_export_path=artifact_export_path,
    )
    if code != 0:
        sys.exit(code)
