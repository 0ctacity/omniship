from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from omniship.config.models import NodeConfig, OmniShipConfig
from omniship.core.execution import CacheSpec, SecretRef
from omniship.plugins.github import (
    GitHubActions,
    GitHubBooleanInput,
    GitHubPermission,
    GitHubPermissions,
    GitHubPullRequest,
    GitHubPush,
    GitHubRunner,
    GitHubShell,
    GitHubStringInput,
    GitHubWorkflow,
    GitHubWorkflowArtifacts,
    GitHubWorkflowDispatch,
)
from omniship.plugins.github.actions import GitHubActionsGenerator
from omniship.plugins.registry import PluginRegistry
from omniship.workflow.model import Pipeline


def test_github_runner_contains_every_standard_hosted_label() -> None:
    assert {runner.value for runner in GitHubRunner} == {
        "ubuntu-slim",
        "ubuntu-latest",
        "ubuntu-22.04",
        "ubuntu-24.04",
        "ubuntu-26.04",
        "ubuntu-22.04-arm",
        "ubuntu-24.04-arm",
        "ubuntu-26.04-arm",
        "windows-latest",
        "windows-2022",
        "windows-2025",
        "windows-2025-vs2026",
        "windows-11-arm",
        "windows-11-vs2026-arm",
        "macos-latest",
        "macos-14",
        "macos-15",
        "macos-26",
        "macos-15-intel",
        "macos-26-intel",
        "xcode-27",
    }


def test_github_actions_creates_node_placement_with_runner_matrix() -> None:
    actions = GitHubActions(default_runner=GitHubRunner.UBUNTU_24_04)

    placement = actions.job(
        runners=[GitHubRunner.UBUNTU_24_04, GitHubRunner.MACOS_15],
        fail_fast=False,
    )

    assert placement.runners == (
        GitHubRunner.UBUNTU_24_04,
        GitHubRunner.MACOS_15,
    )
    assert placement.fail_fast is False
    assert actions.default_job.runners == (GitHubRunner.UBUNTU_24_04,)


def test_github_actions_creates_a_fully_configured_job() -> None:
    actions = GitHubActions()
    cache = CacheSpec(paths=["~/.cache/demo", "build"], key="demo-cache")

    placement = actions.job(
        timeout_minutes=30,
        environment="release",
        working_directory="packages/cli",
        shell=GitHubShell.BASH,
        env={
            "MODE": "release",
            "NPM_TOKEN": SecretRef("NPM_TOKEN"),
        },
        caches=[cache],
    )

    assert placement.timeout_minutes == 30
    assert placement.environment == "release"
    assert placement.working_directory == "packages/cli"
    assert placement.shell == GitHubShell.BASH
    assert placement.env == {
        "MODE": "release",
        "NPM_TOKEN": SecretRef("NPM_TOKEN"),
    }
    assert placement.caches == (cache,)


def test_github_actions_builds_cache_keys_and_secret_references() -> None:
    github = GitHubActions()

    cache = github.cache(
        paths=["~/.cargo/registry", "target"],
        key=[
            "cargo",
            github.runner_os,
            github.runner_arch,
            github.hash_files("Cargo.lock"),
        ],
        restore_prefixes=["cargo-${{ runner.os }}-"],
    )

    assert cache == CacheSpec(
        paths=["~/.cargo/registry", "target"],
        key=(
            "cargo-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('Cargo.lock') }}"
        ),
        restore_keys=["cargo-${{ runner.os }}-"],
    )
    assert github.secret("NPM_TOKEN") == SecretRef("NPM_TOKEN")


def test_github_actions_declares_a_typed_external_checkout() -> None:
    github = GitHubActions()

    checkout = github.checkout(
        repository="ata-sesli/zova",
        ref="0123456789abcdef",
        path=".deps/zova",
        fetch_depth=1,
        persist_credentials=False,
        submodules=True,
        token=github.secret("ZOVA_TOKEN"),
    )

    assert checkout.name == "github/checkout:.deps/zova"
    assert checkout.repository == "ata-sesli/zova"
    assert checkout.token == SecretRef("ZOVA_TOKEN")


def test_github_actions_declares_reviewed_workflow_artifacts() -> None:
    github = GitHubActions()
    run_id = GitHubStringInput("source_run_id", required=True)

    requirement = github.workflow_artifacts(
        repository="0ctacity/omniship",
        run_id=run_id,
        pattern="omniship-build-*",
        token=github.secret("SOURCE_REPOSITORY_TOKEN"),
    )

    assert requirement.repository == "0ctacity/omniship"
    assert requirement.run_id is run_id
    assert requirement.token == SecretRef("SOURCE_REPOSITORY_TOKEN")


@pytest.mark.parametrize("timeout", [0, -1, 361])
def test_github_job_rejects_invalid_timeout(timeout: int) -> None:
    with pytest.raises(ValueError, match="timeout"):
        GitHubActions().job(timeout_minutes=timeout)


@pytest.mark.parametrize(
    "working_directory", ["../outside", "/tmp/project", "C:\\project"]
)
def test_github_job_rejects_working_directory_outside_workspace(
    working_directory: str,
) -> None:
    with pytest.raises(ValueError, match="working_directory"):
        GitHubActions().job(working_directory=working_directory)


def test_github_generator_provisions_task_requirements_before_execution(
    tmp_path: Path,
) -> None:
    @dataclass(frozen=True)
    class Toolchain:
        version: str
        name: str = "example/toolchain"

    registry = PluginRegistry()
    registry.register_requirement_resolver(
        "github/actions",
        Toolchain,
        lambda requirement: {
            "name": "Set up example toolchain",
            "run": f"setup-example {requirement.version}",
        },
    )
    actions = GitHubActions()
    config = OmniShipConfig(
        version=1,
        check={
            "verify": NodeConfig(
                uses="core/noop",
                requirements=(Toolchain("1.2.3"),),
            )
        },
    )

    generated = GitHubActionsGenerator(registry).generate(
        config,
        tmp_path / "workflow.py",
        tmp_path / "omniship.yaml",
        Pipeline(targets=[actions]),
    )
    check_file = next(item for item in generated if item.path.name == "check.yml")
    document = yaml.safe_load(check_file.content)
    steps = document["jobs"]["check-verify"]["steps"]

    assert steps[3] == {
        "name": "Set up example toolchain",
        "run": "setup-example 1.2.3",
    }


def test_github_generator_reviews_and_imports_prior_workflow_artifacts(
    tmp_path: Path,
) -> None:
    registry = PluginRegistry()
    registry.register_requirement_resolver(
        "github/actions",
        GitHubWorkflowArtifacts,
        lambda requirement: requirement,
    )
    github = GitHubActions()
    requirement = github.workflow_artifacts(
        repository="0ctacity/omniship",
        run_id=42,
        pattern="omniship-build-*",
    )
    config = OmniShipConfig(
        check={
            "verify": NodeConfig(
                uses="core/noop",
                requirements=(requirement,),
            )
        }
    )

    generated = GitHubActionsGenerator(registry).generate(
        config,
        tmp_path / "workflow.py",
        tmp_path / "omniship.yaml",
        Pipeline(targets=[github]),
    )
    check_file = next(item for item in generated if item.path.name == "check.yml")
    document = yaml.safe_load(check_file.content)
    job = document["jobs"]["check-verify"]

    assert job["permissions"] == {"actions": "read", "contents": "read"}
    assert any(step.get("name") == "Review artifacts from run 42" for step in job["steps"])
    assert {
        "name": "Download artifacts from run 42",
        "uses": (
            "actions/download-artifact@"
            "d3f86a106a0bac45b974a628896c90dbdf5c8093"
        ),
        "with": {
            "pattern": "omniship-build-*",
            "path": ".omniship/imports/external-1",
            "github-token": "${{ github.token }}",
            "repository": "0ctacity/omniship",
            "run-id": "42",
        },
    } in job["steps"]
    run_step = next(step for step in job["steps"] if step.get("name") == "Run Verify")
    assert run_step["run"].endswith(
        "--import-artifacts-root .omniship/imports"
    )


def test_github_actions_uses_read_only_defaults_and_job_permission_overrides() -> None:
    actions = GitHubActions(default_runner=GitHubRunner.UBUNTU_24_04)
    permissions = GitHubPermissions(
        contents=GitHubPermission.WRITE,
        packages=GitHubPermission.WRITE,
    )

    placement = actions.job(permissions=permissions)

    assert actions.default_permissions == GitHubPermissions(
        contents=GitHubPermission.READ
    )
    assert placement.runners == (GitHubRunner.UBUNTU_24_04,)
    assert placement.permissions == permissions
    assert permissions.to_document() == {
        "contents": "write",
        "packages": "write",
    }


def test_github_actions_uses_stage_workflow_defaults() -> None:
    actions = GitHubActions()

    assert actions.check == GitHubWorkflow(file="check.yml", name="Check")
    assert actions.build == GitHubWorkflow(file="build.yml", name="Build")
    assert actions.ship == GitHubWorkflow(file="ship.yml", name="Ship")


def test_github_actions_rejects_duplicate_stage_workflow_files() -> None:
    duplicate = GitHubWorkflow(file="pipeline.yml", name="Pipeline")

    with pytest.raises(ValueError, match="must be unique"):
        GitHubActions(check=duplicate, build=duplicate)


@pytest.mark.parametrize("filename", ["workflow", "nested/check.yml", "../check.yml"])
def test_github_workflow_rejects_invalid_filename(filename: str) -> None:
    with pytest.raises(ValueError, match="workflow file"):
        GitHubWorkflow(file=filename, name="Check")


def test_github_workflow_normalizes_typed_triggers() -> None:
    workflow = GitHubWorkflow(
        file="ci.yml",
        name="CI",
        triggers=[
            GitHubPullRequest(branches=["main"]),
            GitHubPush(branches=["main", "develop"]),
            GitHubWorkflowDispatch(),
        ],
    )

    assert workflow.triggers == (
        GitHubPullRequest(branches=("main",)),
        GitHubPush(branches=("main", "develop")),
        GitHubWorkflowDispatch(),
    )


def test_github_workflow_dispatch_renders_typed_inputs() -> None:
    dispatch = GitHubWorkflowDispatch(
        inputs=[
            GitHubStringInput(
                "tag",
                description="Tag to release",
                required=True,
            ),
            GitHubBooleanInput("prerelease", default=False),
        ]
    )

    assert dispatch.to_document() == {
        "inputs": {
            "tag": {
                "description": "Tag to release",
                "required": True,
                "type": "string",
            },
            "prerelease": {
                "default": False,
                "type": "boolean",
            },
        }
    }


def test_github_workflow_dispatch_rejects_duplicate_input_names() -> None:
    with pytest.raises(ValueError, match="unique names"):
        GitHubWorkflowDispatch(
            inputs=[GitHubStringInput("version"), GitHubBooleanInput("version")]
        )


def test_github_workflow_input_rejects_default_of_wrong_type() -> None:
    with pytest.raises(TypeError, match="string input default"):
        GitHubStringInput("tag", default=False)  # type: ignore[arg-type]


def test_github_workflow_rejects_duplicate_trigger_types() -> None:
    with pytest.raises(ValueError, match="duplicate trigger"):
        GitHubWorkflow(
            file="ci.yml",
            name="CI",
            triggers=[GitHubPush(branches=["main"]), GitHubPush(tags=["v*"])],
        )


def test_github_push_rejects_conflicting_filters() -> None:
    with pytest.raises(ValueError, match="branches and branches_ignore"):
        GitHubPush(branches=["main"], branches_ignore=["legacy"])


def test_github_actions_rejects_empty_node_runner_list() -> None:
    actions = GitHubActions()

    with pytest.raises(ValueError, match="at least one runner"):
        actions.job(runners=[])


def test_github_actions_rejects_untyped_runner_values() -> None:
    actions = GitHubActions()

    with pytest.raises(TypeError, match="GitHubRunner"):
        actions.job(runners=["ubuntu-latest"])  # type: ignore[list-item]


def test_github_permissions_reject_invalid_access_for_id_token() -> None:
    with pytest.raises(ValueError, match="id_token"):
        GitHubPermissions(id_token=GitHubPermission.READ)


def test_github_permissions_add_missing_typed_block_requirements() -> None:
    requested = GitHubPermissions(packages=GitHubPermission.WRITE)
    required = GitHubPermissions(contents=GitHubPermission.WRITE)

    merged = requested.with_minimum(required, node_name="release")

    assert merged.to_document() == {
        "contents": "write",
        "packages": "write",
    }
