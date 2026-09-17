from pathlib import Path
import tomllib

from omniship.operations import register_core_plugin
from omniship.plugins.github import GitHubRelease, register_github_plugin
from omniship.plugins.python import Python, Ruff, register_python_plugin
from omniship.plugins.registry import PluginRegistry
from omniship.runtime import TaskContext


def _operation_names(registry: PluginRegistry) -> set[str]:
    return {definition.name for definition in registry.list_operations()}


def test_official_plugins_have_independent_registration_boundaries() -> None:
    core = PluginRegistry()
    register_core_plugin(core)
    assert _operation_names(core) == {
        "core/command",
        "core/noop",
        "core/python",
    }

    python = PluginRegistry()
    register_python_plugin(python)
    assert _operation_names(python) == {
        "python/ruff",
        "python/pytest",
        "python/wheel",
    }

    github = PluginRegistry()
    register_github_plugin(github)
    assert _operation_names(github) == {"github/release"}


def test_public_types_are_owned_by_their_provider_packages() -> None:
    assert Ruff.__module__.startswith("omniship.plugins.python")
    assert Python.__module__.startswith("omniship.plugins.python")
    assert GitHubRelease.__module__.startswith("omniship.plugins.github")


def test_package_entry_points_discover_official_plugins_separately() -> None:
    pyproject = tomllib.loads(
        Path("pyproject.toml").read_text(encoding="utf-8")
    )

    assert pyproject["project"]["entry-points"]["omniship.plugins"] == {
        "core": "omniship.operations:register_core_plugin",
        "python": "omniship.plugins.python:register_python_plugin",
        "github": "omniship.plugins.github:register_github_plugin",
    }


def test_python_imperative_capabilities_are_provider_owned(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )
    context = TaskContext(tmp_path, {})

    assert not hasattr(context, "python")
    assert not hasattr(context, "project")
    assert Python(context).project.version() == "1.2.3"
