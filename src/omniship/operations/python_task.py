from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import sys
import time
import traceback
from pathlib import Path

from pydantic import BaseModel, Field

from omniship.core.context import ExecutionContext
from omniship.core.node import NodeInputs
from omniship.core.result import NodeResult, NodeStatus
from omniship.core.stage import Stage
from omniship.plugins.metadata import OperationDefinition
from omniship.runtime import TaskContext, TaskFailure


class PythonTaskConfig(BaseModel):
    callable: str = Field(description="Workspace-relative Python task reference")


class PythonTaskOperation:
    name = "core/python"
    stages = frozenset({Stage.CHECK, Stage.BUILD, Stage.SHIP})
    cacheable = False

    async def execute(
        self,
        context: ExecutionContext,
        inputs: NodeInputs,
    ) -> NodeResult:
        started = time.monotonic()
        try:
            config = PythonTaskConfig.model_validate(inputs.params)
            function = self._load_callable(context.workspace_root, config.callable)
            task_context = TaskContext(
                context.workspace_root,
                {**os.environ, **context.env},
                context.artifacts.to_list(),
                context.inputs,
                context.emit_log,
            )
            if inspect.iscoroutinefunction(function):
                await function(task_context)
            else:
                await asyncio.to_thread(function, task_context)
            return NodeResult(
                status=NodeStatus.SUCCESS,
                duration=time.monotonic() - started,
                artifacts=tuple(task_context.artifacts.values),
                stdout="\n".join(task_context.log.lines),
            )
        except Exception as exc:
            return NodeResult(
                status=NodeStatus.FAILED,
                duration=time.monotonic() - started,
                error_message=f"{type(exc).__name__}: {exc}",
                stderr=traceback.format_exc(),
            )

    @staticmethod
    def _load_callable(workspace_root: Path, reference: str):
        parts = reference.split(":")
        if len(parts) == 2:
            file_name, function_name = parts
            pipeline_task: tuple[Stage, str] | None = None
        elif len(parts) == 4 and parts[1] == "pipeline":
            file_name, _, stage_name, function_name = parts
            try:
                pipeline_task = (Stage(stage_name), function_name)
            except ValueError as exc:
                raise TaskFailure(f"Unknown pipeline stage: {stage_name}") from exc
        else:
            raise TaskFailure(
                "Callable must use file.py:function or "
                "file.py:pipeline:stage:task format"
            )
        path = (workspace_root / file_name).resolve()
        if not path.is_relative_to(workspace_root.resolve()):
            raise TaskFailure("Python task path escapes workspace")
        if not path.is_file():
            raise TaskFailure(f"Python task file not found: {file_name}")
        module_name = f"_omniship_task_{abs(hash((path, function_name)))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise TaskFailure(f"Could not load Python task file: {file_name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        if pipeline_task is None:
            function = getattr(module, function_name, None)
        else:
            pipeline = getattr(module, "pipeline", None)
            task_callable = getattr(pipeline, "task_callable", None)
            if task_callable is None:
                raise TaskFailure("Workflow does not export a valid Pipeline")
            function = task_callable(*pipeline_task)
        if not inspect.isfunction(function):
            raise TaskFailure(f"Python task function not found: {function_name}")
        signature = inspect.signature(function)
        if len(signature.parameters) != 1:
            raise TaskFailure("Python task must accept exactly one context argument")
        return function


def get_python_task_definition() -> OperationDefinition:
    return OperationDefinition(
        name="core/python",
        stages=PythonTaskOperation.stages,
        description="Execute a trusted local Python workflow task",
        config_model=PythonTaskConfig,
    )
