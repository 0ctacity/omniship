"""Official Bun workflow primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from omniship.core.stage import Stage
from omniship.plugins.github import GitHubActionStep
from omniship.plugins.metadata import OperationDefinition
from omniship.plugins.registry import PluginRegistry
from omniship.plugins.tooling import (
    FacadeOperation,
    ToolFacade,
    exact_version,
    relative_file,
)
from omniship.workflow.errors import WorkflowError
from omniship.workflow.model import NodeSpec


@dataclass(frozen=True, slots=True)
class BunToolchain:
    version: str | None = None
    version_file: str | None = None
    name: str = "bun/toolchain"

    def __post_init__(self) -> None:
        if (self.version is None) == (self.version_file is None):
            raise ValueError("BunToolchain requires exactly one version source")
        if self.version is not None:
            exact_version(self.version, tool="Bun")
        if self.version_file is not None:
            relative_file(self.version_file, field_name="Bun version_file")

    def github(self) -> GitHubActionStep:
        key = "bun-version" if self.version is not None else "bun-version-file"
        value = self.version if self.version is not None else self.version_file
        return GitHubActionStep("setup-bun", "Set up Bun", {key: value})


class Bun(ToolFacade):
    """Imperative Bun capabilities."""

    def install(self, *, frozen_lockfile: bool = True) -> None:
        arguments = ["bun", "install"]
        if frozen_lockfile:
            arguments.append("--frozen-lockfile")
        self._run(arguments)

    def test(self) -> None:
        self._run(["bun", "test"])

    def build(
        self,
        *,
        script: str = "build",
        artifacts: Iterable[str] = (),
    ) -> None:
        self._run(["bun", "run", script])
        self._add_artifacts(tuple(artifacts))


@dataclass(frozen=True)
class BunInstall:
    frozen_lockfile: bool = True
    name: str = "bun-install"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.CHECK:
            raise WorkflowError("BunInstall can only be used in the check stage")
        return [
            NodeSpec(
                self.name,
                stage,
                "bun/install",
                {"frozen_lockfile": self.frozen_lockfile},
            )
        ]


@dataclass(frozen=True)
class BunTest:
    install: bool = True
    frozen_lockfile: bool = True
    name: str = "bun-test"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.CHECK:
            raise WorkflowError("BunTest can only be used in the check stage")
        return [
            NodeSpec(
                self.name,
                stage,
                "bun/test",
                {
                    "install": self.install,
                    "frozen_lockfile": self.frozen_lockfile,
                },
            )
        ]


@dataclass(frozen=True)
class BunBuild:
    script: str = "build"
    install: bool = True
    frozen_lockfile: bool = True
    artifacts: tuple[str, ...] = ()
    name: str = "bun-build"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.BUILD:
            raise WorkflowError("BunBuild can only be used in the build stage")
        return [
            NodeSpec(
                self.name,
                stage,
                "bun/build",
                {
                    "script": self.script,
                    "install": self.install,
                    "frozen_lockfile": self.frozen_lockfile,
                    "artifacts": list(self.artifacts),
                },
            )
        ]


class _InstallConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frozen_lockfile: bool = True


class _TestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    install: bool = True
    frozen_lockfile: bool = True


class _BuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    script: str = Field(default="build", min_length=1)
    install: bool = True
    frozen_lockfile: bool = True
    artifacts: list[str] = Field(default_factory=list)


def _operations() -> tuple[FacadeOperation, ...]:
    return (
        FacadeOperation(
            "bun/install",
            Stage.CHECK,
            _InstallConfig,
            lambda ctx, cfg: Bun(ctx).install(
                frozen_lockfile=cfg.frozen_lockfile
            ),
        ),
        FacadeOperation(
            "bun/test",
            Stage.CHECK,
            _TestConfig,
            _test,
        ),
        FacadeOperation(
            "bun/build",
            Stage.BUILD,
            _BuildConfig,
            _build,
        ),
    )


def _test(ctx, cfg) -> None:
    bun = Bun(ctx)
    if cfg.install:
        bun.install(frozen_lockfile=cfg.frozen_lockfile)
    bun.test()


def _build(ctx, cfg) -> None:
    bun = Bun(ctx)
    if cfg.install:
        bun.install(frozen_lockfile=cfg.frozen_lockfile)
    bun.build(script=cfg.script, artifacts=cfg.artifacts)


def register_bun_plugin(registry: PluginRegistry) -> None:
    for operation in _operations():
        registry.register_operation(
            operation,
            OperationDefinition(
                name=operation.name,
                stages=operation.stages,
                description=f"Run {operation.name}",
                config_model=operation.config_model,
            ),
        )
    registry.register_requirement_resolver(
        "github/actions",
        BunToolchain,
        lambda requirement: requirement.github(),
    )


__all__ = [
    "Bun",
    "BunBuild",
    "BunInstall",
    "BunTest",
    "BunToolchain",
    "register_bun_plugin",
]
