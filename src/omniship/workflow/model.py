from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

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


class Block(Protocol):
    def compile(self, stage: Stage, workspace_root: Any) -> list[NodeSpec]: ...


@dataclass(frozen=True)
class StageGroup:
    stage: Stage
    blocks: tuple[Block, ...]


class Check(StageGroup):
    def __init__(self, *blocks: Block) -> None:
        super().__init__(Stage.CHECK, blocks)


class Build(StageGroup):
    def __init__(self, *blocks: Block) -> None:
        super().__init__(Stage.BUILD, blocks)


class Ship(StageGroup):
    def __init__(self, *blocks: Block) -> None:
        super().__init__(Stage.SHIP, blocks)


@dataclass(frozen=True)
class TaskDeclaration:
    function: Callable[[Any], Any]
    ref: NodeRef
    after: tuple[NodeRef, ...] = ()


class Pipeline:
    def __init__(self, *groups: StageGroup) -> None:
        self._entries: dict[Stage, list[Block | TaskDeclaration]] = {
            stage: [] for stage in Stage
        }
        self._task_refs: dict[Callable[[Any], Any], NodeRef] = {}
        for group in groups:
            self.add(group)

    def add(self, group: StageGroup) -> Pipeline:
        self._entries[group.stage].extend(group.blocks)
        return self

    def check(self, *items: Any, **kwargs: Any) -> Any:
        return self._register(Stage.CHECK, *items, **kwargs)

    def build(self, *items: Any, **kwargs: Any) -> Any:
        return self._register(Stage.BUILD, *items, **kwargs)

    def ship(self, *items: Any, **kwargs: Any) -> Any:
        return self._register(Stage.SHIP, *items, **kwargs)

    def entries(self, stage: Stage) -> tuple[Block | TaskDeclaration, ...]:
        return tuple(self._entries[stage])

    def _register(
        self,
        stage: Stage,
        *items: Any,
        after: Iterable[NodeRef | Callable[[Any], Any]] = (),
        name: str | None = None,
    ) -> Any:
        after_refs = tuple(self._resolve_ref(item) for item in after)
        if not items:
            def decorator(function: Callable[[Any], Any]) -> Callable[[Any], Any]:
                return self._add_task(stage, function, name, after_refs)

            return decorator

        if len(items) == 1 and inspect.isfunction(items[0]):
            return self._add_task(stage, items[0], name, after_refs)

        if name is not None or after_refs:
            raise WorkflowError("name and after apply only to imperative tasks")
        self._entries[stage].extend(items)
        refs = tuple(NodeRef(self._block_name(item), stage) for item in items)
        return refs[0] if len(refs) == 1 else refs

    def _add_task(
        self,
        stage: Stage,
        function: Callable[[Any], Any],
        name: str | None,
        after: tuple[NodeRef, ...],
    ) -> Callable[[Any], Any]:
        if function.__qualname__ != function.__name__:
            raise WorkflowError("Imperative tasks must be top-level functions")
        ref = NodeRef(name or function.__name__.replace("_", "-"), stage)
        self._entries[stage].append(TaskDeclaration(function, ref, after))
        self._task_refs[function] = ref
        return function

    def _resolve_ref(self, value: NodeRef | Callable[[Any], Any]) -> NodeRef:
        if isinstance(value, NodeRef):
            return value
        try:
            return self._task_refs[value]
        except (KeyError, TypeError) as exc:
            raise WorkflowError("after must reference a registered task or node") from exc

    @staticmethod
    def _block_name(block: Any) -> str:
        block_name = getattr(block, "name", None)
        if not isinstance(block_name, str) or not block_name:
            raise WorkflowError(f"{type(block).__name__} is not a valid workflow block")
        return block_name
