from pathlib import Path

from click.testing import CliRunner

from omniship.cli.app import cli


def test_cli_plan_command(tmp_path: Path):
    cfg_file = tmp_path / "omniship.yaml"
    cfg_file.write_text("""
    version: 1
    check:
      test:
        uses: core/noop
    build:
      app:
        uses: core/noop
    ship:
      rel:
        uses: core/noop
    """)

    runner = CliRunner()
    res = runner.invoke(cli, ["plan", "-c", str(cfg_file)])
    assert res.exit_code == 0
    assert "CHECK" in res.output
    assert "BUILD" in res.output
    assert "SHIP" in res.output
    assert "test" in res.output


def test_cli_full_ship_with_artifacts(tmp_path: Path):
    cfg_file = tmp_path / "omniship.yaml"
    cfg_file.write_text("""
    version: 1
    check:
      lint:
        uses: core/command
        with:
          run: echo "checked"
    build:
      compile:
        uses: core/command
        with:
          run: mkdir -p dist && echo "binary-content" > dist/mybin
          artifacts:
            - dist/mybin
    ship:
      release:
        uses: github/release
        with:
          repository: test/demo
          tag: v1.0.0
          dry_run: true
    """)

    runner = CliRunner()
    res = runner.invoke(cli, ["ship", "-c", str(cfg_file)])
    assert res.exit_code == 0
    assert "CHECK" in res.output
    assert "Starting lint" in res.output
    assert "checked" in res.output
    assert "BUILD" in res.output
    assert "SHIP" in res.output
    assert "Artifacts" in res.output
    assert "dist/mybin" in res.output
    assert "Shipped successfully!" in res.output


def test_cli_failure_stops_pipeline(tmp_path: Path):
    cfg_file = tmp_path / "omniship.yaml"
    cfg_file.write_text("""
    version: 1
    check:
      fail_test:
        uses: core/command
        with:
          run: exit 1
    build:
      app:
        uses: core/noop
    ship:
      rel:
        uses: core/noop
    """)

    runner = CliRunner()
    res = runner.invoke(cli, ["ship", "-c", str(cfg_file)])
    assert res.exit_code == 1
    assert "CHECK FAILED" in res.output
    assert "BUILD" not in res.output
    assert "SHIP" not in res.output
    assert (
        "::error title=Check · Fail Test::Command failed with exit code 1"
        in runner.invoke(
            cli,
            ["check", "-c", str(cfg_file)],
            env={"GITHUB_ACTIONS": "true"},
        ).output
    )


def test_cli_logging_can_hide_successful_command_output(tmp_path: Path) -> None:
    cfg_file = tmp_path / "omniship.yaml"
    cfg_file.write_text(
        """
        version: 1
        logging:
          show_output: false
        check:
          quiet:
            uses: core/command
            with:
              run: echo "hidden-success-output"
        """,
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["check", "-c", str(cfg_file)])

    assert result.exit_code == 0, result.output
    assert "Starting quiet" in result.output
    assert "hidden-success-output" not in result.output
