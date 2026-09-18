import pytest

from omniship.plugins.github import (
    GitHubActions,
    GitHubBooleanInput,
    GitHubPermission,
    GitHubPermissions,
    GitHubPullRequest,
    GitHubPush,
    GitHubRunner,
    GitHubStringInput,
    GitHubWorkflow,
    GitHubWorkflowDispatch,
)


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
