import time

from pydantic import BaseModel

from omniship.core.context import ExecutionContext
from omniship.core.node import NodeInputs
from omniship.core.result import NodeResult, NodeStatus
from omniship.core.stage import Stage
from omniship.plugins.metadata import OperationDefinition


class NoopConfig(BaseModel):
    pass


class NoopOperation:
    name: str = "core/noop"
    stages: frozenset[Stage] = frozenset({Stage.CHECK, Stage.BUILD, Stage.SHIP})
    cacheable: bool = True

    async def execute(
        self,
        context: ExecutionContext,
        inputs: NodeInputs,
    ) -> NodeResult:
        start_time = time.monotonic()
        return NodeResult(
            status=NodeStatus.SUCCESS,
            duration=time.monotonic() - start_time,
            outputs={"message": "No-op completed"},
        )


def get_noop_definition() -> OperationDefinition:
    return OperationDefinition(
        name=NoopOperation.name,
        stages=NoopOperation.stages,
        description="No-operation dummy task that always succeeds immediately",
        config_model=NoopConfig,
        cacheable=True,
    )
