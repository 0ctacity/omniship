"""Official Rust workflow primitives and Cargo publishing."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from omniship.core.stage import Stage
from omniship.plugins.github import GitHubActionStep
from omniship.plugins.metadata import OperationDefinition
from omniship.plugins.registry import PluginRegistry
from omniship.plugins.tooling import FacadeOperation, ToolFacade, exact_version
from omniship.workflow.errors import WorkflowError
from omniship.workflow.model import NodeSpec

_COMPONENT = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True, init=False)
class RustToolchain:
    toolchain: str
    components: tuple[str, ...]
    targets: tuple[str, ...]
    name: str = "rust/toolchain"

    def __init__(
        self,
        *,
        toolchain: str,
        components: Iterable[str] = (),
        targets: Iterable[str] = (),
    ) -> None:
        exact_version(toolchain, tool="Rust")
        if isinstance(components, (str, bytes)) or isinstance(targets, (str, bytes)):
            raise ValueError("Rust components and targets must be iterables")
        normalized_components = tuple(components)
        normalized_targets = tuple(targets)
        if any(_COMPONENT.fullmatch(value) is None for value in normalized_components):
            raise ValueError("Rust components contain an invalid value")
        if any(_COMPONENT.fullmatch(value) is None for value in normalized_targets):
            raise ValueError("Rust targets contain an invalid value")
        object.__setattr__(self, "toolchain", toolchain)
        object.__setattr__(self, "components", normalized_components)
        object.__setattr__(self, "targets", normalized_targets)
        object.__setattr__(self, "name", "rust/toolchain")

    def github(self) -> GitHubActionStep:
        inputs: dict[str, object] = {
            "toolchain": self.toolchain,
            "cache": False,
        }
        if self.components:
            inputs["components"] = ",".join(self.components)
        if self.targets:
            inputs["target"] = ",".join(self.targets)
        return GitHubActionStep(
            "setup-rust-toolchain",
            "Set up Rust",
            inputs,
        )


class Rust(ToolFacade):
    """Imperative Cargo capabilities."""

    def test(self, *, all_features: bool = False) -> None:
        arguments = ["cargo", "test"]
        if all_features:
            arguments.append("--all-features")
        self._run(arguments)

    def build(
        self,
        *,
        release: bool = True,
        target: str | None = None,
        artifacts: Iterable[str] = (),
    ) -> None:
        arguments = ["cargo", "build"]
        if release:
            arguments.append("--release")
        if target is not None:
            arguments.extend(["--target", target])
        self._run(arguments)
        self._add_artifacts(tuple(artifacts))

    def publish(
        self,
        *,
        package: str | None = None,
        registry: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self._require_env("CARGO_REGISTRY_TOKEN", dry_run=dry_run)
        arguments = ["cargo", "publish"]
        if package is not None:
            arguments.extend(["--package", package])
        if registry is not None:
            arguments.extend(["--registry", registry])
        if dry_run:
            arguments.append("--dry-run")
        self._run(arguments)


@dataclass(frozen=True)
class CargoTest:
    all_features: bool = False
    name: str = "cargo-test"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.CHECK:
            raise WorkflowError("CargoTest can only be used in the check stage")
        return [
            NodeSpec(
                self.name,
                stage,
                "rust/cargo-test",
                {"all_features": self.all_features},
            )
        ]


@dataclass(frozen=True)
class CargoBuild:
    release: bool = True
    target: str | None = None
    artifacts: tuple[str, ...] = ()
    name: str = "cargo-build"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.BUILD:
            raise WorkflowError("CargoBuild can only be used in the build stage")
        return [
            NodeSpec(
                self.name,
                stage,
                "rust/cargo-build",
                {
                    "release": self.release,
                    "target": self.target,
                    "artifacts": list(self.artifacts),
                },
            )
        ]


@dataclass(frozen=True)
class CargoPublish:
    package: str | None = None
    registry: str | None = None
    dry_run: bool = False
    name: str = "cargo-publish"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.SHIP:
            raise WorkflowError("CargoPublish can only be used in the ship stage")
        return [
            NodeSpec(
                self.name,
                stage,
                "rust/cargo-publish",
                {
                    "package": self.package,
                    "registry": self.registry,
                    "dry_run": self.dry_run,
                },
            )
        ]


class _TestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    all_features: bool = False


class _BuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    release: bool = True
    target: str | None = None
    artifacts: list[str] = Field(default_factory=list)


class _PublishConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package: str | None = None
    registry: str | None = None
    dry_run: bool = False


def _operations() -> tuple[FacadeOperation, ...]:
    return (
        FacadeOperation(
            "rust/cargo-test",
            Stage.CHECK,
            _TestConfig,
            lambda ctx, cfg: Rust(ctx).test(all_features=cfg.all_features),
        ),
        FacadeOperation(
            "rust/cargo-build",
            Stage.BUILD,
            _BuildConfig,
            lambda ctx, cfg: Rust(ctx).build(
                release=cfg.release,
                target=cfg.target,
                artifacts=cfg.artifacts,
            ),
        ),
        FacadeOperation(
            "rust/cargo-publish",
            Stage.SHIP,
            _PublishConfig,
            lambda ctx, cfg: Rust(ctx).publish(
                package=cfg.package,
                registry=cfg.registry,
                dry_run=cfg.dry_run,
            ),
        ),
    )


def register_rust_plugin(registry: PluginRegistry) -> None:
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
        RustToolchain,
        lambda requirement: requirement.github(),
    )


__all__ = [
    "CargoBuild",
    "CargoPublish",
    "CargoTest",
    "Rust",
    "RustToolchain",
    "register_rust_plugin",
]
