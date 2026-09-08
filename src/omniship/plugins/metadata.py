from dataclasses import dataclass
from typing import Any

from omniship.core.stage import Stage


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    name: str
    stages: frozenset[Stage]
    description: str = ""
    config_model: Any | None = None
    cacheable: bool = False
