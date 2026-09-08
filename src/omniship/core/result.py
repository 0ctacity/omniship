from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from omniship.core.artifact import Artifact


class NodeStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class NodeResult:
    status: NodeStatus
    duration: float = 0.0
    outputs: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Artifact, ...] = ()
    error_message: str | None = None
    stdout: str = ""
    stderr: str = ""

    @property
    def is_success(self) -> bool:
        return self.status == NodeStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        return self.status == NodeStatus.FAILED

    @property
    def is_skipped(self) -> bool:
        return self.status == NodeStatus.SKIPPED
