from pathlib import Path

import pytest

from omniship.core.execution import (
    Architecture,
    CacheSpec,
    ExecutionHost,
    OperatingSystem,
    SecretRef,
    load_execution_revision,
)
from omniship.runtime.context import TaskContext


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        (
            "Linux",
            "x86_64",
            ExecutionHost(OperatingSystem.LINUX, Architecture.X86_64),
        ),
        (
            "Darwin",
            "arm64",
            ExecutionHost(OperatingSystem.MACOS, Architecture.ARM64),
        ),
        (
            "Windows",
            "AMD64",
            ExecutionHost(OperatingSystem.WINDOWS, Architecture.X86_64),
        ),
    ],
)
def test_execution_host_normalizes_platform_names(
    system: str,
    machine: str,
    expected: ExecutionHost,
) -> None:
    assert ExecutionHost.from_platform(system, machine) == expected


def test_task_context_exposes_the_execution_host(tmp_path: Path) -> None:
    host = ExecutionHost(OperatingSystem.LINUX, Architecture.ARM64)

    context = TaskContext(tmp_path, {}, host=host)

    assert context.host is host


def test_secret_reference_contains_only_a_valid_name() -> None:
    secret = SecretRef("NPM_TOKEN")

    assert secret.name == "NPM_TOKEN"
    assert repr(secret) == "SecretRef(name='NPM_TOKEN')"

    with pytest.raises(ValueError, match="secret name"):
        SecretRef("${{ secrets.NPM_TOKEN }}")


def test_cache_spec_normalizes_paths_and_restore_keys() -> None:
    cache = CacheSpec(
        paths=["~/.cargo/registry", "target"],
        key="cargo-linux-lockhash",
        restore_keys=["cargo-linux-", "cargo-"],
    )

    assert cache.paths == ("~/.cargo/registry", "target")
    assert cache.restore_keys == ("cargo-linux-", "cargo-")

    with pytest.raises(ValueError, match="path"):
        CacheSpec(paths=[], key="cargo")
    with pytest.raises(TypeError, match="paths"):
        CacheSpec(paths="target", key="cargo")
    with pytest.raises(TypeError, match="restore_keys"):
        CacheSpec(paths=["target"], key="cargo", restore_keys="cargo-")


def test_execution_revision_uses_the_provider_neutral_environment_name() -> None:
    assert load_execution_revision({"OMNISHIP_REVISION": "abc123"}) == "abc123"
    assert load_execution_revision({}) is None
