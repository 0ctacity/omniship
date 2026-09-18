import re
import shlex
from collections.abc import Iterable
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

import yaml

from omniship.config.models import NodeConfig, OmniShipConfig
from omniship.core.stage import Stage
from omniship.plugins.api import GeneratedFile
from omniship.workflow.model import Pipeline

from .dependencies import LOCK_FILENAME, GitHubActionLock
from .runtime import PAGES_STAGING_PATH

ARTIFACT_PATH = ".omniship/handoff"
ARTIFACT_IMPORT_PATH = ".omniship/imports"


def _display_name(value: str) -> str:
    words = value.replace("_", "-").split("-")
    return " ".join(
        "GitHub" if word.casefold() == "github" else word.title() for word in words
    )


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


def _normalize_trigger_values(
    values: Iterable[str], *, field_name: str
) -> tuple[str, ...]:
    if isinstance(values, str):
        raise TypeError(f"{field_name} must be an iterable of strings")
    normalized = tuple(values)
    if any(not isinstance(value, str) or not value for value in normalized):
        raise TypeError(f"{field_name} must contain non-empty strings")
    return normalized


@dataclass(frozen=True)
class GitHubPush:
    branches: Iterable[str] = ()
    branches_ignore: Iterable[str] = ()
    tags: Iterable[str] = ()
    tags_ignore: Iterable[str] = ()
    paths: Iterable[str] = ()
    paths_ignore: Iterable[str] = ()
    event: ClassVar[str] = "push"

    def __post_init__(self) -> None:
        for field_name in (
            "branches",
            "branches_ignore",
            "tags",
            "tags_ignore",
            "paths",
            "paths_ignore",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_trigger_values(
                    getattr(self, field_name), field_name=field_name
                ),
            )
        self._reject_conflicting_filters("branches", "branches_ignore")
        self._reject_conflicting_filters("tags", "tags_ignore")
        self._reject_conflicting_filters("paths", "paths_ignore")

    def _reject_conflicting_filters(self, include: str, exclude: str) -> None:
        if getattr(self, include) and getattr(self, exclude):
            raise ValueError(f"GitHub push cannot use both {include} and {exclude}")

    def to_document(self) -> dict[str, object]:
        return _trigger_filters_document(self)


@dataclass(frozen=True)
class GitHubPullRequest:
    branches: Iterable[str] = ()
    branches_ignore: Iterable[str] = ()
    paths: Iterable[str] = ()
    paths_ignore: Iterable[str] = ()
    types: Iterable[str] = ()
    event: ClassVar[str] = "pull_request"

    def __post_init__(self) -> None:
        for field_name in (
            "branches",
            "branches_ignore",
            "paths",
            "paths_ignore",
            "types",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_trigger_values(
                    getattr(self, field_name), field_name=field_name
                ),
            )
        self._reject_conflicting_filters("branches", "branches_ignore")
        self._reject_conflicting_filters("paths", "paths_ignore")

    def _reject_conflicting_filters(self, include: str, exclude: str) -> None:
        if getattr(self, include) and getattr(self, exclude):
            raise ValueError(
                f"GitHub pull request cannot use both {include} and {exclude}"
            )

    def to_document(self) -> dict[str, object]:
        return _trigger_filters_document(self)


@dataclass(frozen=True)
class GitHubStringInput:
    name: str
    description: str | None = None
    required: bool = False
    default: str | None = None

    def __post_init__(self) -> None:
        _validate_workflow_input(self.name, self.description, self.required)
        if self.default is not None and not isinstance(self.default, str):
            raise TypeError("GitHub string input default must be a string")

    def to_document(self) -> dict[str, object]:
        return _workflow_input_document(self, input_type="string")


@dataclass(frozen=True)
class GitHubBooleanInput:
    name: str
    description: str | None = None
    required: bool = False
    default: bool | None = None

    def __post_init__(self) -> None:
        _validate_workflow_input(self.name, self.description, self.required)
        if self.default is not None and not isinstance(self.default, bool):
            raise TypeError("GitHub boolean input default must be a boolean")

    def to_document(self) -> dict[str, object]:
        return _workflow_input_document(self, input_type="boolean")


GitHubInput = GitHubStringInput | GitHubBooleanInput


def _validate_workflow_input(
    name: str,
    description: str | None,
    required: bool,
) -> None:
    if not isinstance(name, str) or not name:
        raise TypeError("GitHub workflow input name must be a non-empty string")
    if description is not None and not isinstance(description, str):
        raise TypeError("GitHub workflow input description must be a string")
    if not isinstance(required, bool):
        raise TypeError("GitHub workflow input required must be a boolean")


def _workflow_input_document(
    workflow_input: GitHubInput,
    *,
    input_type: str,
) -> dict[str, object]:
    document: dict[str, object] = {}
    if workflow_input.description is not None:
        document["description"] = workflow_input.description
    if workflow_input.required:
        document["required"] = True
    if workflow_input.default is not None:
        document["default"] = workflow_input.default
    document["type"] = input_type
    return document


@dataclass(frozen=True)
class GitHubWorkflowDispatch:
    inputs: Iterable[GitHubInput] = ()
    event: ClassVar[str] = "workflow_dispatch"

    def __post_init__(self) -> None:
        if isinstance(self.inputs, (str, bytes)):
            raise TypeError("GitHub workflow inputs must be typed input values")
        inputs = tuple(self.inputs)
        if any(
            not isinstance(workflow_input, (GitHubStringInput, GitHubBooleanInput))
            for workflow_input in inputs
        ):
            raise TypeError("GitHub workflow inputs must be typed input values")
        names = [workflow_input.name for workflow_input in inputs]
        if len(set(names)) != len(names):
            raise ValueError("GitHub workflow inputs must have unique names")
        if len(inputs) > 25:
            raise ValueError("GitHub workflow dispatch supports at most 25 inputs")
        object.__setattr__(self, "inputs", inputs)

    def to_document(self) -> dict[str, object]:
        if not self.inputs:
            return {}
        return {
            "inputs": {
                workflow_input.name: workflow_input.to_document()
                for workflow_input in self.inputs
            }
        }


GitHubTrigger = GitHubPush | GitHubPullRequest | GitHubWorkflowDispatch


def _trigger_filters_document(trigger: object) -> dict[str, object]:
    document: dict[str, object] = {}
    for field_info in fields(trigger):
        values = getattr(trigger, field_info.name)
        if values:
            document[field_info.name.replace("_", "-")] = list(values)
    return document


@dataclass(frozen=True)
class GitHubWorkflow:
    file: str
    name: str
    triggers: Iterable[GitHubTrigger] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.file, str) or not self.file:
            raise TypeError("GitHub workflow file must be a non-empty string")
        if "/" in self.file or "\\" in self.file:
            raise ValueError("GitHub workflow file must be a filename")
        if Path(self.file).suffix not in {".yml", ".yaml"}:
            raise ValueError("GitHub workflow file must end in .yml or .yaml")
        if not isinstance(self.name, str) or not self.name:
            raise TypeError("GitHub workflow name must be a non-empty string")
        if self.triggers is None:
            return
        if isinstance(self.triggers, (str, bytes)):
            raise TypeError("GitHub workflow triggers must be typed trigger values")
        triggers = tuple(self.triggers)
        if any(
            not isinstance(
                trigger,
                (GitHubPush, GitHubPullRequest, GitHubWorkflowDispatch),
            )
            for trigger in triggers
        ):
            raise TypeError("GitHub workflow triggers must be typed trigger values")
        events = [trigger.event for trigger in triggers]
        if len(set(events)) != len(events):
            raise ValueError("GitHub workflow cannot contain duplicate trigger types")
        object.__setattr__(self, "triggers", triggers)


@dataclass(frozen=True)
class GitHubActions:
    name: ClassVar[str] = "github/actions"
    default_runner: GitHubRunner = GitHubRunner.UBUNTU_LATEST
    default_permissions: GitHubPermissions = GitHubPermissions(
        contents=GitHubPermission.READ
    )
    check: GitHubWorkflow = GitHubWorkflow(file="check.yml", name="Check")
    build: GitHubWorkflow = GitHubWorkflow(file="build.yml", name="Build")
    ship: GitHubWorkflow = GitHubWorkflow(file="ship.yml", name="Ship")

    def __post_init__(self) -> None:
        if not isinstance(self.default_runner, GitHubRunner):
            raise TypeError("default_runner must be a GitHubRunner value")
        if not isinstance(self.default_permissions, GitHubPermissions):
            raise TypeError("default_permissions must be a GitHubPermissions value")
        workflows = (self.check, self.build, self.ship)
        if any(not isinstance(workflow, GitHubWorkflow) for workflow in workflows):
            raise TypeError("check, build, and ship must be GitHubWorkflow values")
        filenames = [workflow.file.casefold() for workflow in workflows]
        if len(set(filenames)) != len(filenames):
            raise ValueError("GitHub workflow files must be unique")

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
        selected_runners = (self.default_runner,) if runners is None else tuple(runners)
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
        targets = [
            target for target in pipeline.targets if isinstance(target, GitHubActions)
        ]
        if len(targets) > 1:
            raise ValueError("Pipeline has more than one GitHub Actions target")
        github_nodes = tuple(
            node
            for node in config.ship.values()
            if node.uses in {"github/pages", "github/release"}
        )
        if not targets and not github_nodes:
            return ()
        actions = targets[0] if targets else GitHubActions()
        pages_nodes = [node for node in config.ship.values() if node.uses == "github/pages"]
        if len(pages_nodes) > 1:
            raise ValueError("A pipeline can contain only one GitHub Pages deployment")

        workspace_root = source_path.parent.resolve()
        lock_path = workspace_root / LOCK_FILENAME
        action_defaults = GitHubActionLock.defaults()
        action_lock = GitHubActionLock.load(lock_path) if lock_path.is_file() else action_defaults
        action_lock.validate_compatibility(action_defaults)
        source = source_path.resolve().relative_to(workspace_root)
        pipeline_config = config_path.resolve().relative_to(workspace_root)
        workflow_root = workspace_root / ".github" / "workflows"
        generate_command = ["uv", "run", "omniship", "generate"]
        if source != Path("workflow.py"):
            generate_command.extend(["--workflow-file", source.as_posix()])
        if pipeline_config != Path("omniship.yaml"):
            generate_command.extend(["--output", pipeline_config.as_posix()])
        generate_command.append("--check")

        def setup_steps() -> list[dict[str, object]]:
            return [
                {"uses": action_lock.reference("checkout")},
                {"uses": action_lock.reference("setup-uv")},
                {"run": "uv sync --all-groups --locked"},
            ]

        def prepare_job() -> dict[str, object]:
            return {
                "name": "Check · Prepare",
                "runs-on": actions.default_runner.value,
                "steps": [
                    *setup_steps(),
                    {"run": shlex.join(generate_command)},
                ],
            }

        def stage_jobs(
            stage: Stage,
            nodes: dict[str, NodeConfig],
            *,
            root_dependency: str,
            has_runtime_inputs: bool,
        ) -> dict[str, dict[str, object]]:
            job_ids: dict[str, str] = {}
            used_job_ids: set[str] = set()
            for node_name in nodes:
                normalized = (
                    re.sub(r"[^a-zA-Z0-9_-]+", "-", node_name).strip("-").lower()
                )
                job_id = f"{stage.value}-{normalized}"
                if job_id in used_job_ids:
                    raise ValueError(
                        f"GitHub Actions job id collision for node "
                        f"'{node_name}': {job_id}"
                    )
                used_job_ids.add(job_id)
                job_ids[node_name] = job_id

            depended_on = {
                dependency for node in nodes.values() for dependency in node.needs
            }
            generated_jobs: dict[str, dict[str, object]] = {}
            terminal_job_ids: list[str] = []
            for node_name, node in nodes.items():
                job_id = job_ids[node_name]
                placement = node.execution or actions.default_job
                if not isinstance(placement, GitHubJob):
                    raise ValueError(
                        f"Node '{node_name}' has execution metadata that is not a GitHub job"
                    )
                if node.uses == "github/pages" and len(placement.runners) != 1:
                    raise ValueError(
                        "GitHub Pages deployment requires exactly one runner"
                    )

                required_permissions = GitHubPermissions()
                if node.uses == "github/release" and not node.with_.get(
                    "dry_run", False
                ):
                    required_permissions = GitHubPermissions(
                        contents=GitHubPermission.WRITE
                    )
                elif node.uses == "github/pages":
                    required_permissions = GitHubPermissions(
                        actions=GitHubPermission.READ,
                        contents=GitHubPermission.READ,
                        id_token=GitHubPermission.WRITE,
                        pages=GitHubPermission.WRITE,
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

                dependency_jobs = [job_ids[dependency] for dependency in node.needs]
                if not dependency_jobs:
                    dependency_jobs = [root_dependency]

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
                        dependency_job = job_ids[dependency]
                        steps.append(
                            {
                                "uses": action_lock.reference("download-artifact"),
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
                            "uses": action_lock.reference("download-artifact"),
                            "with": {
                                "pattern": "omniship-build-*",
                                "path": ARTIFACT_IMPORT_PATH,
                            },
                        }
                    )
                    command.extend(["--import-artifacts-root", ARTIFACT_IMPORT_PATH])

                run_step: dict[str, object] = {
                    "name": f"Run {_display_name(node_name)}",
                    "run": shlex.join(command),
                }
                step_env: dict[str, str] = {}
                if has_runtime_inputs:
                    step_env["OMNISHIP_INPUTS"] = "${{ toJSON(inputs) }}"
                if node.uses == "github/release" or placement.permissions is not None:
                    step_env["GITHUB_TOKEN"] = "${{ github.token }}"
                if step_env:
                    run_step["env"] = step_env
                steps.append(run_step)

                if node.uses == "github/pages":
                    steps.extend(
                        [
                            {
                                "uses": action_lock.reference(
                                    "upload-pages-artifact"
                                ),
                                "with": {"path": PAGES_STAGING_PATH.as_posix()},
                            },
                            {
                                "name": "Deploy GitHub Pages",
                                "id": "deployment",
                                "uses": action_lock.reference("deploy-pages"),
                            },
                        ]
                    )

                if stage == Stage.BUILD:
                    artifact_name = f"omniship-build-{job_id}"
                    if len(placement.runners) > 1:
                        artifact_name += "-${{ matrix.runner }}"
                    steps.append(
                        {
                            "uses": action_lock.reference("upload-artifact"),
                            "with": {
                                "name": artifact_name,
                                "path": f"{ARTIFACT_PATH}/{job_id}",
                                "include-hidden-files": True,
                            },
                        }
                    )

                job: dict[str, object] = {
                    "name": f"{stage.value.title()} · {_display_name(node_name)}",
                    "needs": dependency_jobs[0]
                    if len(dependency_jobs) == 1
                    else dependency_jobs,
                }
                if job_permissions is not None:
                    job["permissions"] = job_permissions.to_document()
                if node.uses == "github/pages":
                    job["environment"] = {
                        "name": "github-pages",
                        "url": "${{ steps.deployment.outputs.page_url }}",
                    }
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
                generated_jobs[job_id] = job
                if node_name not in depended_on:
                    terminal_job_ids.append(job_id)

            barrier_id = f"{stage.value}-complete"
            barrier_needs = terminal_job_ids or [root_dependency]
            generated_jobs[barrier_id] = {
                "name": f"{stage.value.title()} complete",
                "needs": barrier_needs[0] if len(barrier_needs) == 1 else barrier_needs,
                "runs-on": actions.default_runner.value,
                "steps": [{"run": f"echo '{stage.value} stage complete'"}],
            }
            return generated_jobs

        def workflow_events(
            workflow: GitHubWorkflow,
            defaults: tuple[GitHubTrigger, ...],
            *,
            is_callable: bool,
        ) -> dict[str, object]:
            configured = defaults if workflow.triggers is None else workflow.triggers
            events = {trigger.event: trigger.to_document() for trigger in configured}
            if is_callable:
                events["workflow_call"] = {}
            return events

        def has_runtime_inputs(
            workflow: GitHubWorkflow,
            defaults: tuple[GitHubTrigger, ...],
        ) -> bool:
            configured = defaults if workflow.triggers is None else workflow.triggers
            return any(
                isinstance(trigger, GitHubWorkflowDispatch) and bool(trigger.inputs)
                for trigger in configured
            )

        check_jobs = {"prepare": prepare_job()}
        check_jobs.update(
            stage_jobs(
                Stage.CHECK,
                config.check,
                root_dependency="prepare",
                has_runtime_inputs=has_runtime_inputs(
                    actions.check,
                    (GitHubPullRequest(), GitHubPush(branches=("main",))),
                ),
            )
        )
        build_jobs: dict[str, dict[str, object]] = {
            "check": {
                "name": actions.check.name,
                "uses": f"./.github/workflows/{actions.check.file}",
            }
        }
        build_jobs.update(
            stage_jobs(
                Stage.BUILD,
                config.build,
                root_dependency="check",
                has_runtime_inputs=has_runtime_inputs(actions.build, ()),
            )
        )
        ship_jobs: dict[str, dict[str, object]] = {
            "build": {
                "name": actions.build.name,
                "uses": f"./.github/workflows/{actions.build.file}",
            },
        }
        ship_jobs.update(
            stage_jobs(
                Stage.SHIP,
                config.ship,
                root_dependency="build",
                has_runtime_inputs=has_runtime_inputs(
                    actions.ship,
                    (GitHubPush(tags=("v*",)),),
                ),
            )
        )

        ship_document: dict[str, object] = {
            "name": actions.ship.name,
            "on": workflow_events(
                actions.ship,
                (GitHubPush(tags=("v*",)),),
                is_callable=False,
            ),
            "permissions": actions.default_permissions.to_document(),
            "jobs": ship_jobs,
        }
        if pages_nodes:
            ship_document["concurrency"] = {
                "group": "pages",
                "cancel-in-progress": True,
            }

        documents = (
            (
                actions.check,
                {
                    "name": actions.check.name,
                    "on": workflow_events(
                        actions.check,
                        (
                            GitHubPullRequest(),
                            GitHubPush(branches=("main",)),
                        ),
                        is_callable=True,
                    ),
                    "permissions": actions.default_permissions.to_document(),
                    "jobs": check_jobs,
                },
            ),
            (
                actions.build,
                {
                    "name": actions.build.name,
                    "on": workflow_events(
                        actions.build,
                        (),
                        is_callable=True,
                    ),
                    "permissions": actions.default_permissions.to_document(),
                    "jobs": build_jobs,
                },
            ),
            (
                actions.ship,
                ship_document,
            ),
        )
        generated = [GeneratedFile(lock_path, action_lock.render())]
        for workflow, document in documents:
            rendered = yaml.safe_dump(
                document,
                sort_keys=False,
                width=1000,
                allow_unicode=True,
            )
            content = (
                f"# Generated by OmniShip from {source.name}. Do not edit directly.\n"
                f"{rendered}"
            )
            generated.append(GeneratedFile(workflow_root / workflow.file, content))
        return tuple(generated)
