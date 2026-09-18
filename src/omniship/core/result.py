"""Operation outcomes recorded by the DAG executor."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from omniship.core.artifact import Artifact


class NodeStatus(StrEnum):
    """Terminal state of a node execution."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class NodeResult:
    """The complete terminal result returned by an operation.

    ``SKIPPED`` covers both unmet conditions and dependency propagation; the
    accompanying ``error_message`` explains which case occurred.
    """

    status: NodeStatus
    duration: float = 0.0
    outputs: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Artifact, ...] = ()
    error_message: str | None = None
    stdout: str = ""
    stderr: str = ""

    @property
    def is_success(self) -> bool:
        """Whether the operation completed successfully."""

        return self.status == NodeStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        """Whether the node failed."""

        return self.status == NodeStatus.FAILED

    @property
    def is_skipped(self) -> bool:
        """Whether execution was intentionally bypassed."""

        return self.status == NodeStatus.SKIPPED
