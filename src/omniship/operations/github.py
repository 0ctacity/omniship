import json
import os
import time
import urllib.request
from typing import Any

from pydantic import BaseModel, Field

from omniship.core.artifact import Artifact
from omniship.core.context import ExecutionContext
from omniship.core.node import NodeInputs
from omniship.core.result import NodeResult, NodeStatus
from omniship.core.stage import Stage
from omniship.plugins.metadata import OperationDefinition
from omniship.plugins.registry import PluginRegistry


class GithubReleaseConfig(BaseModel):
    repository: str = Field(..., description="GitHub repository in 'owner/repo' format")
    tag: str = Field(..., description="Git release tag name, e.g. 'v1.0.0'")
    title: str | None = Field(default=None, description="Release title")
    body: str | None = Field(default=None, description="Release notes / description")
    draft: bool = Field(default=False, description="Whether to create as draft")
    prerelease: bool = Field(default=False, description="Whether this is a prerelease")
    files: list[str] = Field(
        default_factory=list,
        description="Explicit artifact names or paths to attach; defaults to all context artifacts",
    )
    token: str | None = Field(
        default=None,
        description="GitHub personal access token (falls back to GITHUB_TOKEN env)",
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

        token = cfg.token or os.environ.get("GITHUB_TOKEN") or context.env.get("GITHUB_TOKEN")

        # Determine artifacts to upload
        artifacts_to_upload: list[Artifact] = []
        if cfg.files:
            for file_ref in cfg.files:
                art = context.get_artifact(file_ref)
                if art:
                    artifacts_to_upload.append(art)
                else:
                    # check if it exists as file
                    p = (context.workspace_root / file_ref).resolve()
                    if p.exists():
                        artifacts_to_upload.append(Artifact.from_path(p))
                    else:
                        return NodeResult(
                            status=NodeStatus.FAILED,
                            duration=time.monotonic() - start_time,
                            error_message=f"Artifact '{file_ref}' not found in context or workspace",
                        )
        else:
            # Default to all artifacts collected so far
            artifacts_to_upload = context.artifacts.to_list()

        # If dry run or no token provided in test/offline environment
        if cfg.dry_run or not token:
            stdout_lines = [
                f"[github/release] Target repository: {cfg.repository}",
                f"[github/release] Tag: {cfg.tag}",
                f"[github/release] Title: {cfg.title or cfg.tag}",
                f"[github/release] Artifacts to attach ({len(artifacts_to_upload)}):",
            ]
            for a in artifacts_to_upload:
                stdout_lines.append(f"  - {a.name} ({a.path})")
            if not token:
                stdout_lines.append("[github/release] Note: GITHUB_TOKEN not set; executed in simulated mode.")

            return NodeResult(
                status=NodeStatus.SUCCESS,
                duration=time.monotonic() - start_time,
                stdout="\n".join(stdout_lines),
                outputs={
                    "repository": cfg.repository,
                    "tag": cfg.tag,
                    "release_url": f"https://github.com/{cfg.repository}/releases/tag/{cfg.tag}",
                    "uploaded_count": len(artifacts_to_upload),
                },
            )

        # Real GitHub API release creation
        try:
            url = f"https://api.github.com/repos/{cfg.repository}/releases"
            payload = json.dumps({
                "tag_name": cfg.tag,
                "name": cfg.title or cfg.tag,
                "body": cfg.body or "",
                "draft": cfg.draft,
                "prerelease": cfg.prerelease,
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "OmniShip-v0.1",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                release_url = data.get("html_url", "")
                upload_url = data.get("upload_url", "")

            # If upload_url is available, upload artifacts
            # upload_url format: https://uploads.github.com/repos/.../assets{?name,label}
            if upload_url and "{" in upload_url:
                base_upload_url = upload_url.split("{")[0]
                for art in artifacts_to_upload:
                    if art.path.is_file():
                        file_data = art.path.read_bytes()
                        asset_url = f"{base_upload_url}?name={art.name}"
                        up_req = urllib.request.Request(
                            asset_url,
                            data=file_data,
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/octet-stream",
                                "User-Agent": "OmniShip-v0.1",
                            },
                            method="POST",
                        )
                        with urllib.request.urlopen(up_req, timeout=30):
                            pass

            return NodeResult(
                status=NodeStatus.SUCCESS,
                duration=time.monotonic() - start_time,
                stdout=f"Successfully published release {cfg.tag} to {release_url}",
                outputs={
                    "repository": cfg.repository,
                    "tag": cfg.tag,
                    "release_url": release_url,
                    "uploaded_count": len(artifacts_to_upload),
                },
            )
        except Exception as err:
            return NodeResult(
                status=NodeStatus.FAILED,
                duration=time.monotonic() - start_time,
                error_message=f"GitHub release creation failed: {err}",
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
