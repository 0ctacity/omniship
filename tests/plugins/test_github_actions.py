import pytest

from omniship.plugins.github import (
    GitHubActions,
    GitHubPermission,
    GitHubPermissions,
    GitHubRunner,
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
