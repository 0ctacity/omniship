"""Official Zig workflow primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from omniship.core.stage import Stage
from omniship.plugins.github import GitHubActionStep
from omniship.plugins.metadata import OperationDefinition
from omniship.plugins.registry import PluginRegistry
from omniship.plugins.tooling import FacadeOperation, ToolFacade, exact_version
from omniship.workflow.errors import WorkflowError
from omniship.workflow.model import NodeSpec

ZigOptimize = Literal["Debug", "ReleaseSafe", "ReleaseFast", "ReleaseSmall"]


@dataclass(frozen=True, slots=True)
class ZigToolchain:
    version: str
    name: str = "zig/toolchain"

    def __post_init__(self) -> None:
        exact_version(self.version, tool="Zig")

    def github(self) -> GitHubActionStep:
        return GitHubActionStep(
            "setup-zig",
            "Set up Zig",
            {"version": self.version},
        )


class Zig(ToolFacade):
    """Imperative Zig capabilities."""

    def test(self, *, step: str = "test") -> None:
        self._run(["zig", "build", step])

    def build(
        self,
        *,
        step: str | None = None,
        optimize: ZigOptimize | None = None,
        target: str | None = None,
        artifacts: Iterable[str] = (),
    ) -> None:
        arguments = ["zig", "build"]
        if step is not None:
            arguments.append(step)
        if optimize is not None:
            arguments.append(f"-Doptimize={optimize}")
        if target is not None:
            arguments.append(f"-Dtarget={target}")
        self._run(arguments)
        self._add_artifacts(tuple(artifacts))


@dataclass(frozen=True)
class ZigTest:
    step: str = "test"
    name: str = "zig-test"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.CHECK:
            raise WorkflowError("ZigTest can only be used in the check stage")
        return [NodeSpec(self.name, stage, "zig/test", {"step": self.step})]


@dataclass(frozen=True)
class ZigBuild:
    step: str | None = None
    optimize: ZigOptimize | None = None
    target: str | None = None
    artifacts: tuple[str, ...] = ()
    name: str = "zig-build"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.BUILD:
            raise WorkflowError("ZigBuild can only be used in the build stage")
        return [
            NodeSpec(
                self.name,
                stage,
                "zig/build",
                {
                    "step": self.step,
                    "optimize": self.optimize,
                    "target": self.target,
                    "artifacts": list(self.artifacts),
                },
            )
        ]


class _TestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: str = Field(default="test", min_length=1)


class _BuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: str | None = None
    optimize: ZigOptimize | None = None
    target: str | None = None
    artifacts: list[str] = Field(default_factory=list)


def _operations() -> tuple[FacadeOperation, ...]:
    return (
        FacadeOperation(
            "zig/test",
            Stage.CHECK,
            _TestConfig,
            lambda ctx, cfg: Zig(ctx).test(step=cfg.step),
        ),
        FacadeOperation(
            "zig/build",
            Stage.BUILD,
            _BuildConfig,
            lambda ctx, cfg: Zig(ctx).build(
                step=cfg.step,
                optimize=cfg.optimize,
                target=cfg.target,
                artifacts=cfg.artifacts,
            ),
        ),
    )


def register_zig_plugin(registry: PluginRegistry) -> None:
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
        ZigToolchain,
        lambda requirement: requirement.github(),
    )


__all__ = [
    "Zig",
    "ZigBuild",
    "ZigTest",
    "ZigToolchain",
    "register_zig_plugin",
]
