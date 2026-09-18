import asyncio
import os
import time

from pydantic import BaseModel, ConfigDict, Field

from omniship.core.context import ExecutionContext
from omniship.core.node import NodeInputs
from omniship.core.result import NodeResult, NodeStatus
from omniship.core.stage import Stage
from omniship.plugins.metadata import OperationDefinition
from omniship.plugins.registry import PluginRegistry
from omniship.runtime import TaskContext

from .actions import GitHubActionsGenerator
from .runtime import GitHub


class GithubReleaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(..., description="GitHub repository in 'owner/repo' format")
    tag: str = Field(..., description="Git release tag name, e.g. 'v1.0.0'")
    title: str | None = Field(default=None, description="Release title")
    body: str | None = Field(default=None, description="Release notes / description")
    generate_notes: bool = Field(
        default=False,
        description="Ask GitHub to generate release notes",
    )
    draft: bool = Field(default=False, description="Whether to create as draft")
    prerelease: bool = Field(default=False, description="Whether this is a prerelease")
    files: list[str] = Field(
        default_factory=list,
        description="Explicit artifact names or paths to attach; defaults to all context artifacts",
    )
    dry_run: bool = Field(
        default=False,
        description="Dry run mode: simulate release creation and artifact upload",
    )


class GithubReleaseOperation:
    name: str = "github/release"
    stages: frozenset[Stage] = frozenset({Stage.SHIP})
    cacheable: bool = False

    async def execute(
        self,
        context: ExecutionContext,
        inputs: NodeInputs,
    ) -> NodeResult:
        start_time = time.monotonic()
        try:
            cfg = GithubReleaseConfig.model_validate(inputs.params)
        except Exception as e:
            return NodeResult(
                status=NodeStatus.FAILED,
                duration=time.monotonic() - start_time,
                error_message=f"Invalid github/release configuration: {e}",
            )

        task_context = TaskContext(
            context.workspace_root,
            {**os.environ, **context.env},
            context.artifacts.to_list(),
        )
        notes = "auto" if cfg.generate_notes else cfg.body
        try:
            release = await asyncio.to_thread(
                GitHub(task_context).release,
                repository=cfg.repository,
                tag=cfg.tag,
                notes=notes,
                title=cfg.title,
                draft=cfg.draft,
                prerelease=cfg.prerelease,
                files=tuple(cfg.files),
                dry_run=cfg.dry_run,
            )
        except Exception as exc:
            return NodeResult(
                status=NodeStatus.FAILED,
                duration=time.monotonic() - start_time,
                error_message=str(exc),
            )
        return NodeResult(
            status=NodeStatus.SUCCESS,
            duration=time.monotonic() - start_time,
            stdout="\n".join(task_context.log.lines),
            outputs={
                "repository": release.repository,
                "tag": release.tag,
                "release_url": release.release_url,
                "uploaded_count": release.uploaded_count,
            },
        )


def get_github_definition() -> OperationDefinition:
    return OperationDefinition(
        name=GithubReleaseOperation.name,
        stages=GithubReleaseOperation.stages,
        description="Publish release and upload built artifacts to GitHub",
        config_model=GithubReleaseConfig,
        cacheable=False,
    )


def register_github_plugin(registry: PluginRegistry) -> None:
    registry.register_operation(
        GithubReleaseOperation(),
        get_github_definition(),
    )
    registry.register_workflow_generator(GitHubActionsGenerator())
