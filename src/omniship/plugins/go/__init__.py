"""Official Go workflow primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
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


class GoOS(StrEnum):
    AIX = "aix"
    ANDROID = "android"
    DARWIN = "darwin"
    DRAGONFLY = "dragonfly"
    FREEBSD = "freebsd"
    ILLUMOS = "illumos"
    IOS = "ios"
    JS = "js"
    LINUX = "linux"
    NETBSD = "netbsd"
    OPENBSD = "openbsd"
    PLAN9 = "plan9"
    SOLARIS = "solaris"
    WASIP1 = "wasip1"
    WINDOWS = "windows"


class GoArch(StrEnum):
    X86 = "386"
    AMD64 = "amd64"
    ARM = "arm"
    ARM64 = "arm64"
    LOONG64 = "loong64"
    MIPS = "mips"
    MIPS64 = "mips64"
    MIPS64LE = "mips64le"
    MIPSLE = "mipsle"
    PPC64 = "ppc64"
    PPC64LE = "ppc64le"
    RISCV64 = "riscv64"
    S390X = "s390x"
    WASM = "wasm"


@dataclass(frozen=True, slots=True)
class GoTarget:
    os: GoOS
    arch: GoArch

    def __post_init__(self) -> None:
        if not isinstance(self.os, GoOS) or not isinstance(self.arch, GoArch):
            raise TypeError("GoTarget requires GoOS and GoArch values")

    @property
    def environment(self) -> dict[str, str]:
        return {"GOOS": self.os.value, "GOARCH": self.arch.value}


@dataclass(frozen=True, slots=True)
class GoToolchain:
    version: str | None = None
    version_file: str | None = None
    name: str = "go/toolchain"

    def __post_init__(self) -> None:
        if (self.version is None) == (self.version_file is None):
            raise ValueError("GoToolchain requires exactly one version source")
        if self.version is not None:
            exact_version(self.version, tool="Go")
        if self.version_file is not None:
            relative_file(self.version_file, field_name="Go version_file")

    def github(self) -> GitHubActionStep:
        inputs: dict[str, object] = {"cache": False}
        if self.version is not None:
            inputs["go-version"] = self.version
        else:
            inputs["go-version-file"] = self.version_file
        return GitHubActionStep("setup-go", "Set up Go", inputs)


class Go(ToolFacade):
    """Imperative Go capabilities."""

    def test(self, *, packages: Iterable[str] = ("./...",)) -> None:
        self._run(["go", "test", *tuple(packages)])

    def build(
        self,
        *,
        output: str,
        package: str = ".",
        target: GoTarget | None = None,
    ) -> None:
        output = relative_file(output, field_name="Go build output")
        self._run(
            ["go", "build", "-o", output, package],
            env={} if target is None else target.environment,
        )
        self.context.artifacts.add(output)


@dataclass(frozen=True)
class GoTest:
    packages: tuple[str, ...] = ("./...",)
    name: str = "go-test"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.CHECK:
            raise WorkflowError("GoTest can only be used in the check stage")
        return [
            NodeSpec(
                self.name,
                stage,
                "go/test",
                {"packages": list(self.packages)},
            )
        ]


@dataclass(frozen=True)
class GoBuild:
    output: str
    package: str = "."
    target: GoTarget | None = None
    name: str = "go-build"

    def __post_init__(self) -> None:
        relative_file(self.output, field_name="Go build output")

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.BUILD:
            raise WorkflowError("GoBuild can only be used in the build stage")
        params: dict[str, object] = {
            "output": self.output,
            "package": self.package,
        }
        if self.target is not None:
            params["goos"] = self.target.os.value
            params["goarch"] = self.target.arch.value
        return [NodeSpec(self.name, stage, "go/build", params)]


class _TestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    packages: list[str] = Field(default_factory=lambda: ["./..."])


class _BuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output: str = Field(min_length=1)
    package: str = Field(default=".", min_length=1)
    goos: GoOS | None = None
    goarch: GoArch | None = None

    def target(self) -> GoTarget | None:
        if (self.goos is None) != (self.goarch is None):
            raise ValueError("goos and goarch must be provided together")
        if self.goos is None:
            return None
        return GoTarget(self.goos, self.goarch)


def _operations() -> tuple[FacadeOperation, ...]:
    return (
        FacadeOperation(
            "go/test",
            Stage.CHECK,
            _TestConfig,
            lambda ctx, cfg: Go(ctx).test(packages=cfg.packages),
        ),
        FacadeOperation(
            "go/build",
            Stage.BUILD,
            _BuildConfig,
            lambda ctx, cfg: Go(ctx).build(
                output=cfg.output,
                package=cfg.package,
                target=cfg.target(),
            ),
        ),
    )


def register_go_plugin(registry: PluginRegistry) -> None:
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
        GoToolchain,
        lambda requirement: requirement.github(),
    )


__all__ = [
    "Go",
    "GoArch",
    "GoBuild",
    "GoOS",
    "GoTarget",
    "GoTest",
    "GoToolchain",
    "register_go_plugin",
]
