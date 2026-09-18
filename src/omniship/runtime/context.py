from __future__ import annotations

import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from omniship.core.artifact import Artifact


class TaskFailure(Exception):
    pass


@dataclass
class TaskLog:
    lines: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.lines.append(message)


@dataclass
class TaskArtifacts:
    workspace_root: Path
    existing: tuple[Artifact, ...] = ()
    values: list[Artifact] = field(default_factory=list)

    def __iter__(self) -> Iterator[Artifact]:
        return iter((*self.existing, *self.values))

    def get(self, name: str) -> Artifact | None:
        return next((artifact for artifact in self if artifact.name == name), None)

    def add(
        self,
        path: str | Path,
        name: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> Artifact:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        candidate = candidate.resolve()
        if not candidate.is_relative_to(self.workspace_root):
            raise TaskFailure(f"Artifact path escapes workspace: {path}")
        if not candidate.exists():
            raise TaskFailure(f"Artifact does not exist: {path}")
        artifact = Artifact.from_path(candidate, name=name, metadata=metadata)
        self.values.append(artifact)
        return artifact


@dataclass(frozen=True)
class GitTools:
    workspace_root: Path

    def _read(self, *arguments: str) -> str:
        process = subprocess.run(
            ["git", *arguments],
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise TaskFailure(process.stderr.strip() or "Git command failed")
        return process.stdout.strip()

    def branch(self) -> str:
        return self._read("branch", "--show-current")

    def tags(self) -> list[str]:
        output = self._read("tag", "--list")
        return output.splitlines() if output else []

    def remote_url(self) -> str:
        return self._read("remote", "get-url", "origin")

    def changelog(self) -> str:
        return self._read("log", "--pretty=format:%s")


class TaskContext:
    def __init__(
        self,
        workspace_root: Path,
        env: Mapping[str, str],
        artifacts: Iterable[Artifact] = (),
    ) -> None:
        self.workspace = workspace_root.resolve()
        self.env = dict(env)
        self.log = TaskLog()
        self.artifacts = TaskArtifacts(self.workspace, tuple(artifacts))
        self.git = GitTools(self.workspace)

    def fail(self, message: str) -> None:
        raise TaskFailure(message)
