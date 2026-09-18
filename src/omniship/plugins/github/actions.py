import re
import shlex
from collections.abc import Iterable
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

import yaml

from omniship.config.models import OmniShipConfig
from omniship.core.stage import Stage
from omniship.plugins.api import GeneratedFile
from omniship.workflow.model import Pipeline

CHECKOUT_ACTION = (  # v7.0.1
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
)
SETUP_UV_ACTION = (  # v10.1.0
    "astral-sh/setup-uv@bec219d24cd3e171d82865faccec33120bb574f4"
)
UPLOAD_ARTIFACT_ACTION = (  # v4.6.2
    "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
)
DOWNLOAD_ARTIFACT_ACTION = (  # v4.3.0
    "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
)
ARTIFACT_PATH = ".omniship/handoff"
ARTIFACT_IMPORT_PATH = ".omniship/imports"


class GitHubRunner(StrEnum):
    UBUNTU_SLIM = "ubuntu-slim"
    UBUNTU_LATEST = "ubuntu-latest"
    UBUNTU_22_04 = "ubuntu-22.04"
    UBUNTU_24_04 = "ubuntu-24.04"
    UBUNTU_26_04 = "ubuntu-26.04"
    UBUNTU_22_04_ARM = "ubuntu-22.04-arm"
    UBUNTU_24_04_ARM = "ubuntu-24.04-arm"
    UBUNTU_26_04_ARM = "ubuntu-26.04-arm"
    WINDOWS_LATEST = "windows-latest"
    WINDOWS_2022 = "windows-2022"
    WINDOWS_2025 = "windows-2025"
    WINDOWS_2025_VS2026 = "windows-2025-vs2026"
    WINDOWS_11_ARM = "windows-11-arm"
    WINDOWS_11_VS2026_ARM = "windows-11-vs2026-arm"
    MACOS_LATEST = "macos-latest"
    MACOS_14 = "macos-14"
    MACOS_15 = "macos-15"
    MACOS_26 = "macos-26"
    MACOS_15_INTEL = "macos-15-intel"
    MACOS_26_INTEL = "macos-26-intel"
    XCODE_27 = "xcode-27"


class GitHubPermission(StrEnum):
    NONE = "none"
    READ = "read"
    WRITE = "write"


_PERMISSION_RANK = {
    GitHubPermission.NONE: 0,
    GitHubPermission.READ: 1,
    GitHubPermission.WRITE: 2,
}


@dataclass(frozen=True)
class GitHubPermissions:
    actions: GitHubPermission | None = None
    artifact_metadata: GitHubPermission | None = None
    attestations: GitHubPermission | None = None
    checks: GitHubPermission | None = None
    code_quality: GitHubPermission | None = None
    contents: GitHubPermission | None = None
    deployments: GitHubPermission | None = None
    discussions: GitHubPermission | None = None
    id_token: GitHubPermission | None = None
    issues: GitHubPermission | None = None
    models: GitHubPermission | None = None
    packages: GitHubPermission | None = None
    pages: GitHubPermission | None = None
    pull_requests: GitHubPermission | None = None
    security_events: GitHubPermission | None = None
    statuses: GitHubPermission | None = None
    vulnerability_alerts: GitHubPermission | None = None

    def __post_init__(self) -> None:
        for permission_field in fields(self):
            value = getattr(self, permission_field.name)
            if value is not None and not isinstance(value, GitHubPermission):
                raise TypeError(
                    f"{permission_field.name} must be a GitHubPermission value"
                )
        for write_or_none in ("id_token",):
            if getattr(self, write_or_none) == GitHubPermission.READ:
                raise ValueError(f"{write_or_none} supports only write or none")
        for read_or_none in ("models", "vulnerability_alerts"):
            if getattr(self, read_or_none) == GitHubPermission.WRITE:
                raise ValueError(f"{read_or_none} supports only read or none")

    def to_document(self) -> dict[str, str]:
        return {
            permission_field.name.replace("_", "-"): value.value
            for permission_field in fields(self)
            if (value := getattr(self, permission_field.name)) is not None
        }

    def satisfies(self, required: GitHubPermissions) -> bool:
        for permission_field in fields(self):
            minimum = getattr(required, permission_field.name)
            if minimum is None:
                continue
            granted = getattr(self, permission_field.name) or GitHubPermission.NONE
            if _PERMISSION_RANK[granted] < _PERMISSION_RANK[minimum]:
                return False
        return True

    def with_minimum(
        self,
        required: GitHubPermissions,
        *,
        node_name: str,
    ) -> GitHubPermissions:
        values: dict[str, GitHubPermission] = {}
        for permission_field in fields(self):
            minimum = getattr(required, permission_field.name)
            granted = getattr(self, permission_field.name)
            if minimum is None:
                continue
            if (
                granted is not None
                and _PERMISSION_RANK[granted] < _PERMISSION_RANK[minimum]
            ):
                scope = permission_field.name.replace("_", "-")
                raise ValueError(
                    f"Node '{node_name}' requires '{scope}: {minimum.value}', "
                    f"but its GitHub job grants '{scope}: {granted.value}'"
                )
            if granted is None:
                values[permission_field.name] = minimum
        return replace(self, **values)


@dataclass(frozen=True)
class GitHubJob:
    runners: tuple[GitHubRunner, ...]
    fail_fast: bool = False
    permissions: GitHubPermissions | None = None

    def __post_init__(self) -> None:
        if not self.runners:
            raise ValueError("A GitHub job requires at least one runner")
        if any(not isinstance(runner, GitHubRunner) for runner in self.runners):
            raise TypeError("GitHub job runners must be GitHubRunner values")
        if self.permissions is not None and not isinstance(
            self.permissions, GitHubPermissions
        ):
            raise TypeError("permissions must be a GitHubPermissions value")


@dataclass(frozen=True)
class GitHubActions:
    name: ClassVar[str] = "github/actions"
    default_runner: GitHubRunner = GitHubRunner.UBUNTU_LATEST
    default_permissions: GitHubPermissions = GitHubPermissions(
        contents=GitHubPermission.READ
    )

    def __post_init__(self) -> None:
        if not isinstance(self.default_runner, GitHubRunner):
            raise TypeError("default_runner must be a GitHubRunner value")
        if not isinstance(self.default_permissions, GitHubPermissions):
            raise TypeError("default_permissions must be a GitHubPermissions value")

    @property
    def default_job(self) -> GitHubJob:
        return GitHubJob((self.default_runner,))

    def job(
        self,
        *,
        runners: Iterable[GitHubRunner] | None = None,
        fail_fast: bool = False,
        permissions: GitHubPermissions | None = None,
    ) -> GitHubJob:
        selected_runners = (
            (self.default_runner,) if runners is None else tuple(runners)
        )
        return GitHubJob(
            selected_runners,
            fail_fast=fail_fast,
            permissions=permissions,
        )


class GitHubActionsGenerator:
    name = "github/actions"

    def generate(
        self,
        config: OmniShipConfig,
        source_path: Path,
        config_path: Path,
        pipeline: Pipeline,
    ) -> tuple[GeneratedFile, ...]:
        targets = [target for target in pipeline.targets if isinstance(target, GitHubActions)]
        if len(targets) > 1:
            raise ValueError("Pipeline has more than one GitHub Actions target")
        has_release_block = any(
            node.uses == "github/release" for node in config.ship.values()
        )
        if not targets and not has_release_block:
            return ()
        actions = targets[0] if targets else GitHubActions()

        workspace_root = source_path.parent.resolve()
        source = source_path.resolve().relative_to(workspace_root)
        pipeline_config = config_path.resolve().relative_to(workspace_root)
        destination = workspace_root / ".github" / "workflows" / "release.yml"
        generate_command = ["uv", "run", "omniship", "generate"]
        if source != Path("workflow.py"):
            generate_command.extend(["--workflow-file", source.as_posix()])
        if pipeline_config != Path("omniship.yaml"):
            generate_command.extend(["--output", pipeline_config.as_posix()])
        generate_command.append("--check")

        def setup_steps() -> list[dict[str, object]]:
            return [
                {"uses": CHECKOUT_ACTION},
                {"uses": SETUP_UV_ACTION},
                {"run": "uv sync --all-groups --locked"},
            ]

        stage_configs = {
            Stage.CHECK: config.check,
            Stage.BUILD: config.build,
            Stage.SHIP: config.ship,
        }
        job_ids: dict[tuple[Stage, str], str] = {}
        used_job_ids: set[str] = set()
        for stage, nodes in stage_configs.items():
            for node_name in nodes:
                normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", node_name).strip("-").lower()
                job_id = f"{stage.value}-{normalized}"
                if job_id in used_job_ids:
                    raise ValueError(
                        f"GitHub Actions job id collision for node '{node_name}': {job_id}"
                    )
                used_job_ids.add(job_id)
                job_ids[(stage, node_name)] = job_id

        jobs: dict[str, dict[str, object]] = {
            "prepare": {
                "runs-on": actions.default_runner.value,
                "steps": [
                    *setup_steps(),
                    {"run": shlex.join(generate_command)},
                ],
            }
        }

        previous_barrier = "prepare"
        for stage, nodes in stage_configs.items():
            depended_on = {
                dependency
                for node in nodes.values()
                for dependency in node.needs
            }
            terminal_job_ids: list[str] = []
            for node_name, node in nodes.items():
                job_id = job_ids[(stage, node_name)]
                placement = node.execution or actions.default_job
                if not isinstance(placement, GitHubJob):
                    raise ValueError(
                        f"Node '{node_name}' has execution metadata that is not a GitHub job"
                    )

                required_permissions = GitHubPermissions()
                if (
                    node.uses == "github/release"
                    and not node.with_.get("dry_run", False)
                ):
                    required_permissions = GitHubPermissions(
                        contents=GitHubPermission.WRITE
                    )
                job_permissions = placement.permissions
                if job_permissions is None:
                    if not actions.default_permissions.satisfies(required_permissions):
                        job_permissions = GitHubPermissions().with_minimum(
                            required_permissions,
                            node_name=node_name,
                        )
                else:
                    job_permissions = job_permissions.with_minimum(
                        required_permissions,
                        node_name=node_name,
                    )

                dependency_jobs = [
                    job_ids[(stage, dependency)] for dependency in node.needs
                ]
                if not dependency_jobs:
                    dependency_jobs = [previous_barrier]

                steps = setup_steps()
                command = [
                    "uv",
                    "run",
                    "omniship",
                    "run-node",
                    "--stage",
                    stage.value,
                    "--node",
                    node_name,
                    "--config",
                    pipeline_config.as_posix(),
                ]

                if stage == Stage.BUILD and node.needs:
                    for dependency in node.needs:
                        dependency_job = job_ids[(stage, dependency)]
                        steps.append(
                            {
                                "uses": DOWNLOAD_ARTIFACT_ACTION,
                                "with": {
                                    "pattern": f"omniship-build-{dependency_job}*",
                                    "path": f"{ARTIFACT_IMPORT_PATH}/{dependency_job}",
                                },
                            }
                        )
                    command.extend(["--import-artifacts-root", ARTIFACT_IMPORT_PATH])

                if stage == Stage.BUILD:
                    export_path = f"{ARTIFACT_PATH}/{job_id}"
                    command.extend(["--export-artifacts", export_path])

                if stage == Stage.SHIP and config.build:
                    steps.append(
                        {
                            "uses": DOWNLOAD_ARTIFACT_ACTION,
                            "with": {
                                "pattern": "omniship-build-*",
                                "path": ARTIFACT_IMPORT_PATH,
                            },
                        }
                    )
                    command.extend(["--import-artifacts-root", ARTIFACT_IMPORT_PATH])

                run_step: dict[str, object] = {"run": shlex.join(command)}
                if node.uses == "github/release" or placement.permissions is not None:
                    run_step["env"] = {"GITHUB_TOKEN": "${{ github.token }}"}
                steps.append(run_step)

                if stage == Stage.BUILD:
                    artifact_name = f"omniship-build-{job_id}"
                    if len(placement.runners) > 1:
                        artifact_name += "-${{ matrix.runner }}"
                    steps.append(
                        {
                            "uses": UPLOAD_ARTIFACT_ACTION,
                            "with": {
                                "name": artifact_name,
                                "path": f"{ARTIFACT_PATH}/{job_id}",
                                "include-hidden-files": True,
                            },
                        }
                    )

                job: dict[str, object] = {
                    "needs": dependency_jobs[0]
                    if len(dependency_jobs) == 1
                    else dependency_jobs,
                }
                if job_permissions is not None:
                    job["permissions"] = job_permissions.to_document()
                job["runs-on"] = placement.runners[0].value
                job["steps"] = steps
                if len(placement.runners) > 1:
                    job["strategy"] = {
                        "fail-fast": placement.fail_fast,
                        "matrix": {
                            "runner": [runner.value for runner in placement.runners]
                        },
                    }
                    job["runs-on"] = "${{ matrix.runner }}"
                jobs[job_id] = job
                if node_name not in depended_on:
                    terminal_job_ids.append(job_id)

            barrier_id = f"{stage.value}-complete"
            barrier_needs = terminal_job_ids or [previous_barrier]
            jobs[barrier_id] = {
                "needs": barrier_needs[0] if len(barrier_needs) == 1 else barrier_needs,
                "runs-on": actions.default_runner.value,
                "steps": [{"run": f"echo '{stage.value} stage complete'"}],
            }
            previous_barrier = barrier_id

        document = {
            "name": "Release",
            "on": {"push": {"tags": ["v*"]}},
            "permissions": actions.default_permissions.to_document(),
            "jobs": jobs,
        }
        rendered = yaml.safe_dump(document, sort_keys=False, width=1000)
        content = (
            f"# Generated by OmniShip from {source.name}. Do not edit directly.\n"
            f"{rendered}"
        )
        return (GeneratedFile(destination, content),)
