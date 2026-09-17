from pathlib import Path

from omniship.recipes import PythonRelease
from omniship.workflow.compiler import compile_pipeline


def test_python_release_expands_to_public_blocks(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )
    pipeline = PythonRelease(
        repository="octacity/demo",
        dry_run=True,
    )

    config = compile_pipeline(pipeline, tmp_path / "workflow.py")

    assert list(config.check) == ["ruff", "pytest"]
    assert list(config.build) == ["wheel"]
    assert config.ship["github-release"].with_ == {
        "repository": "octacity/demo",
        "tag": "v1.2.3",
        "generate_notes": True,
        "dry_run": True,
    }
