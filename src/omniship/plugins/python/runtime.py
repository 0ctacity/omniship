from __future__ import annotations

import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from omniship.runtime.context import TaskFailure

if TYPE_CHECKING:
    from omniship.runtime.context import TaskContext


@dataclass(frozen=True)
class ProjectTools:
    workspace_root: Path

    def version(self) -> str:
        path = self.workspace_root / "pyproject.toml"
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            version = data["project"]["version"]
        except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
            raise TaskFailure(
                "Could not read [project].version from pyproject.toml"
            ) from exc
        if not isinstance(version, str) or not version:
            raise TaskFailure("Project version must be a non-empty string")
        return version


@dataclass(frozen=True)
class PythonTools:
    workspace_root: Path
    env: Mapping[str, str]

    def _run(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        process = subprocess.run(
            arguments,
            cwd=self.workspace_root,
            env=dict(self.env),
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise TaskFailure(process.stderr.strip() or "Python tool failed")
        return process

    def pytest(self) -> None:
        self._run([sys.executable, "-m", "pytest"])

    def pyright(self) -> None:
        self._run(["pyright"])

    def ruff(self, *, fix: bool = False) -> None:
        arguments = ["ruff", "check", "."]
        if fix:
            arguments.append("--fix")
        self._run(arguments)

    def build_wheels(self, output: str = "dist") -> list[Path]:
        output_path = (self.workspace_root / output).resolve()
        before = set(output_path.glob("*.whl")) if output_path.exists() else set()
        self._run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(output_path)]
        )
        wheels = sorted(set(output_path.glob("*.whl")) - before)
        if not wheels:
            raise TaskFailure("Wheel build produced no new .whl files")
        return wheels

    def build_wheel(self, output: str = "dist") -> Path:
        wheels = self.build_wheels(output)
        if len(wheels) != 1:
            raise TaskFailure(f"Expected one wheel, found {len(wheels)}")
        return wheels[0]


class Python(PythonTools):
    """Typed Python capability facade for an imperative task context."""

    def __init__(self, context: TaskContext) -> None:
        super().__init__(context.workspace, context.env)
        self.project = ProjectTools(context.workspace)

