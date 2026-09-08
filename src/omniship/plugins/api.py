from typing import TYPE_CHECKING, Protocol

from omniship.core.context import ExecutionContext
from omniship.core.node import NodeInputs
from omniship.core.result import NodeResult
from omniship.core.stage import Stage

if TYPE_CHECKING:
    from omniship.plugins.registry import PluginRegistry


class Operation(Protocol):
    name: str
    stages: frozenset[Stage]
    cacheable: bool = False

    async def execute(
        self,
        context: ExecutionContext,
        inputs: NodeInputs,
    ) -> NodeResult: ...


class Plugin(Protocol):
    def register(self, registry: "PluginRegistry") -> None: ...
