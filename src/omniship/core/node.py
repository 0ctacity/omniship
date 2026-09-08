from dataclasses import dataclass, field
from typing import Any, Mapping

from omniship.core.artifact import Artifact
from omniship.core.stage import Stage


@dataclass(frozen=True, slots=True)
class Dependency:
    node_id: str


@dataclass
class NodeInputs:
    params: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    stage: Stage
    operation_name: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    dependencies: frozenset[str] = field(default_factory=frozenset)
    condition: Mapping[str, Any] | str | None = None
