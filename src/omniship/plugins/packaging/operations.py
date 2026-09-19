from __future__ import annotations

import asyncio
import os
import time
import traceback
from typing import Literal

from pydantic import BaseModel, Field

from omniship.core.context import ExecutionContext
from omniship.core.node import NodeInputs
from omniship.core.result import NodeResult, NodeStatus
from omniship.core.stage import Stage
from omniship.plugins.metadata import OperationDefinition
from omniship.runtime import TaskContext, TaskFailure

from .runtime import Archive, Checksums


class ArchiveConfig(BaseModel):
    output: str
    files: dict[str, str] = Field(min_length=1)
    reproducible: bool = True


class Sha256ManifestConfig(BaseModel):
    output: str = "dist/SHA256SUMS.txt"
    artifacts: list[str] = Field(default_factory=list)


class ArchiveOperation:
    stages = frozenset({Stage.BUILD})
    cacheable = False

    def __init__(self, kind: Literal["tar-gz", "zip"]) -> None:
        self.kind = kind
        self.name = f"packaging/{kind}"

    async def execute(self, context: ExecutionContext, inputs: NodeInputs) -> NodeResult:
        started = time.monotonic()
        try:
            config = ArchiveConfig.model_validate(inputs.params)
            task_context = _task_context(context)
            archive = Archive(task_context)
            function = archive.tar_gz if self.kind == "tar-gz" else archive.zip
            await asyncio.to_thread(
                function,
                output=config.output,
                files=config.files,
                reproducible=config.reproducible,
            )
            return _success(started, task_context)
        except Exception as exc:
            return _failure(started, exc)


class Sha256ManifestOperation:
    name = "packaging/sha256-manifest"
    stages = frozenset({Stage.BUILD})
    cacheable = False

    async def execute(self, context: ExecutionContext, inputs: NodeInputs) -> NodeResult:
        started = time.monotonic()
        try:
            config = Sha256ManifestConfig.model_validate(inputs.params)
            task_context = _task_context(context)
            selected = None
            if config.artifacts:
                selected = []
                for name in config.artifacts:
                    artifact = task_context.artifacts.get(name)
                    if artifact is None:
                        raise TaskFailure(f"Artifact not found: {name}")
                    selected.append(artifact)
            await asyncio.to_thread(
                Checksums(task_context).sha256,
                output=config.output,
                artifacts=selected,
            )
            return _success(started, task_context)
        except Exception as exc:
            return _failure(started, exc)


def _task_context(context: ExecutionContext) -> TaskContext:
    return TaskContext(
        context.workspace_root,
        {**os.environ, **context.env},
        context.artifacts.to_list(),
        context.inputs,
        context.emit_log,
        host=context.host,
    )


def _success(started: float, context: TaskContext) -> NodeResult:
    return NodeResult(
        status=NodeStatus.SUCCESS,
        duration=time.monotonic() - started,
        artifacts=tuple(context.artifacts.values),
    )


def _failure(started: float, exc: Exception) -> NodeResult:
    return NodeResult(
        status=NodeStatus.FAILED,
        duration=time.monotonic() - started,
        error_message=f"{type(exc).__name__}: {exc}",
        stderr=traceback.format_exc(),
    )


def get_packaging_definitions() -> tuple[OperationDefinition, ...]:
    return (
        OperationDefinition(
            name="packaging/tar-gz",
            stages=ArchiveOperation.stages,
            description="Create a reproducible gzip-compressed tar archive",
            config_model=ArchiveConfig,
        ),
        OperationDefinition(
            name="packaging/zip",
            stages=ArchiveOperation.stages,
            description="Create a reproducible ZIP archive",
            config_model=ArchiveConfig,
        ),
        OperationDefinition(
            name="packaging/sha256-manifest",
            stages=Sha256ManifestOperation.stages,
            description="Create a SHA-256 artifact manifest",
            config_model=Sha256ManifestConfig,
        ),
    )
