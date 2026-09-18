"""Immutable DAG node declarations and the inputs supplied to operations."""

from dataclasses import dataclass, field
from typing import Any, Mapping

from omniship.core.artifact import Artifact
from omniship.core.stage import Stage


@dataclass(frozen=True, slots=True)
class Dependency:
    """A reference to another node in the same stage graph."""

    node_id: str


@dataclass
class NodeInputs:
    """Resolved parameters and available artifacts passed to an operation."""

    params: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Node:
    """A single operation invocation in one stage DAG.

    Dependencies are node identifiers within the same :class:`StageGraph`; stage
    ordering is handled by the pipeline executor rather than cross-stage edges.
    """

    id: str
    stage: Stage
    operation_name: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    dependencies: frozenset[str] = field(default_factory=frozenset)
    condition: Mapping[str, Any] | str | None = None
