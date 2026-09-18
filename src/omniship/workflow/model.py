from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from omniship.core.logging import Logging
from omniship.core.stage import Stage

from .errors import WorkflowError


@dataclass(frozen=True)
class NodeRef:
    name: str
    stage: Stage


@dataclass(frozen=True)
class NodeSpec:
    name: str
    stage: Stage
    uses: str
    params: dict[str, Any] = field(default_factory=dict)
    needs: tuple[NodeRef, ...] = ()
    condition: dict[str, Any] | str | None = None
    execution: Any = None


class Block(Protocol):
    def compile(self, stage: Stage, workspace_root: Any) -> list[NodeSpec]: ...


@dataclass(frozen=True)
class TaskDeclaration:
    function: Callable[[Any], Any]
    ref: NodeRef
    after: tuple[NodeRef, ...] = ()
    execution: Any = None


@dataclass(frozen=True)
class BlockDeclaration:
    block: Block
    after: tuple[NodeRef, ...] = ()
    execution: Any = None


class StageBuilder:
    def __init__(self, pipeline: Pipeline, stage: Stage) -> None:
        self._pipeline = pipeline
        self.stage = stage

    def task(
        self,
        item: Any = None,
        *,
        after: Iterable[NodeRef | Callable[[Any], Any]] = (),
        name: str | None = None,
        execution: Any = None,
    ) -> Any:
        if item is None:

            def decorator(function: Callable[[Any], Any]) -> Callable[[Any], Any]:
                return self._pipeline._add_imperative_task(
                    self.stage,
                    function,
                    name=name,
                    after=after,
                    execution=execution,
                )

            return decorator
        if inspect.isfunction(item):
            return self._pipeline._add_imperative_task(
                self.stage,
                item,
                name=name,
                after=after,
                execution=execution,
            )
        if name is not None:
            raise WorkflowError("name applies only to imperative tasks")
        return self._pipeline._add_block_task(
            self.stage,
            item,
            after=after,
            execution=execution,
        )


class Pipeline:
    def __init__(
        self,
        *,
        targets: Iterable[Any] = (),
        logging: Logging | None = None,
    ) -> None:
        self._entries: dict[Stage, list[BlockDeclaration | TaskDeclaration]] = {
            stage: [] for stage in Stage
        }
        self._stage_definitions: dict[Stage, Callable[[StageBuilder], Any]] = {}
        self._task_refs: dict[Callable[[Any], Any], NodeRef] = {}
        self._task_callables: dict[tuple[Stage, str], Callable[[Any], Any]] = {}
        self.targets = tuple(targets)
        if logging is not None and not isinstance(logging, Logging):
            raise TypeError("logging must be a Logging value")
        self.logging = logging or Logging()

    def check(
        self, definition: Callable[[StageBuilder], Any]
    ) -> Callable[[StageBuilder], Any]:
        return self._define_stage(Stage.CHECK, definition)

    def build(
        self, definition: Callable[[StageBuilder], Any]
    ) -> Callable[[StageBuilder], Any]:
        return self._define_stage(Stage.BUILD, definition)

    def ship(
        self, definition: Callable[[StageBuilder], Any]
    ) -> Callable[[StageBuilder], Any]:
        return self._define_stage(Stage.SHIP, definition)

    def entries(self, stage: Stage) -> tuple[BlockDeclaration | TaskDeclaration, ...]:
        return tuple(self._entries[stage])

    def task_callable(self, stage: Stage, name: str) -> Callable[[Any], Any]:
        try:
            return self._task_callables[(stage, name)]
        except KeyError as exc:
            raise WorkflowError(
                f"Imperative task '{name}' does not exist in stage '{stage.value}'"
            ) from exc

    def _define_stage(
        self,
        stage: Stage,
        definition: Callable[[StageBuilder], Any],
    ) -> Callable[[StageBuilder], Any]:
        if not inspect.isfunction(definition):
            raise WorkflowError(
                f"pipeline.{stage.value} requires a stage definition function"
            )
        if stage in self._stage_definitions:
            raise WorkflowError(f"Stage '{stage.value}' is already defined")
        if len(inspect.signature(definition).parameters) != 1:
            raise WorkflowError(
                f"Stage definition '{definition.__name__}' must accept exactly one stage argument"
            )

        self._stage_definitions[stage] = definition
        before = len(self._entries[stage])
        definition(StageBuilder(self, stage))
        if len(self._entries[stage]) == before:
            self._stage_definitions.pop(stage, None)
            raise WorkflowError(
                f"{stage.value.capitalize()} stage '{definition.__name__}' did not declare any tasks"
            )
        return definition

    def _add_imperative_task(
        self,
        stage: Stage,
        function: Callable[[Any], Any],
        *,
        name: str | None,
        after: Iterable[NodeRef | Callable[[Any], Any]],
        execution: Any,
    ) -> Callable[[Any], Any]:
        ref = NodeRef(name or function.__name__.replace("_", "-"), stage)
        after_refs = tuple(self._resolve_ref(item) for item in after)
        self._entries[stage].append(
            TaskDeclaration(function, ref, after_refs, execution)
        )
        self._task_refs[function] = ref
        self._task_callables[(stage, ref.name)] = function
        return function

    def _add_block_task(
        self,
        stage: Stage,
        block: Block,
        *,
        after: Iterable[NodeRef | Callable[[Any], Any]],
        execution: Any,
    ) -> NodeRef:
        ref = NodeRef(self._block_name(block), stage)
        after_refs = tuple(self._resolve_ref(item) for item in after)
        self._entries[stage].append(BlockDeclaration(block, after_refs, execution))
        return ref

    def _resolve_ref(self, value: NodeRef | Callable[[Any], Any]) -> NodeRef:
        if isinstance(value, NodeRef):
            return value
        try:
            return self._task_refs[value]
        except (KeyError, TypeError) as exc:
            raise WorkflowError(
                "after must reference a registered task or node"
            ) from exc

    @staticmethod
    def _block_name(block: Any) -> str:
        block_name = getattr(block, "name", None)
        if not isinstance(block_name, str) or not block_name:
            raise WorkflowError(f"{type(block).__name__} is not a valid workflow block")
        return block_name
