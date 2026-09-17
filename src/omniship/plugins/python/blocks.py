from dataclasses import dataclass
from pathlib import Path

from omniship.core.stage import Stage
from omniship.workflow.errors import WorkflowError
from omniship.workflow.model import NodeSpec


@dataclass(frozen=True)
class Ruff:
    fix: bool = False
    name: str = "ruff"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.CHECK:
            raise WorkflowError("Ruff can only be used in the check stage")
        params = {"fix": True} if self.fix else {}
        return [NodeSpec(self.name, stage, "python/ruff", params)]


@dataclass(frozen=True)
class Pytest:
    coverage: bool = False
    minimum_coverage: int | None = None
    name: str = "pytest"

    def __post_init__(self) -> None:
        if self.minimum_coverage is not None and not self.coverage:
            raise WorkflowError("minimum_coverage requires coverage=True")

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.CHECK:
            raise WorkflowError("Pytest can only be used in the check stage")
        params: dict[str, object] = {}
        if self.coverage:
            params["coverage"] = True
        if self.minimum_coverage is not None:
            params["minimum_coverage"] = self.minimum_coverage
        return [NodeSpec(self.name, stage, "python/pytest", params)]


@dataclass(frozen=True)
class Wheel:
    verify: bool = True
    output: str = "dist"
    name: str = "wheel"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.BUILD:
            raise WorkflowError("Wheel can only be used in the build stage")
        params: dict[str, object] = {}
        if not self.verify:
            params["verify"] = False
        if self.output != "dist":
            params["output"] = self.output
        return [NodeSpec(self.name, stage, "python/wheel", params)]
