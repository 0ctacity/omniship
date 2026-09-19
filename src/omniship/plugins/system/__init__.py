"""Typed operating-system package requirements."""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable
from dataclasses import dataclass

from omniship.plugins.registry import PluginRegistry

_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+_.:@/-]*$")


def _packages(values: Iterable[str], *, field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of package names")
    normalized = tuple(values)
    if any(
        not isinstance(package, str) or _PACKAGE_NAME.fullmatch(package) is None
        for package in normalized
    ):
        raise ValueError(f"{field_name} contains an invalid package name")
    return normalized


@dataclass(frozen=True, slots=True, init=False)
class SystemPackages:
    """Native packages selected according to the execution host OS."""

    ubuntu: tuple[str, ...]
    macos: tuple[str, ...]
    windows: tuple[str, ...]
    name: str = "system/packages"

    def __init__(
        self,
        *,
        ubuntu: Iterable[str] = (),
        macos: Iterable[str] = (),
        windows: Iterable[str] = (),
    ) -> None:
        selected = {
            "ubuntu": _packages(ubuntu, field_name="ubuntu"),
            "macos": _packages(macos, field_name="macos"),
            "windows": _packages(windows, field_name="windows"),
        }
        if not any(selected.values()):
            raise ValueError("SystemPackages requires at least one package name")
        for field_name, packages in selected.items():
            object.__setattr__(self, field_name, packages)
        object.__setattr__(self, "name", "system/packages")


def _github_steps(requirement: SystemPackages) -> tuple[dict[str, object], ...]:
    steps: list[dict[str, object]] = []
    if requirement.ubuntu:
        packages = " ".join(map(shlex.quote, requirement.ubuntu))
        steps.append(
            {
                "name": "Install Ubuntu system packages",
                "if": "runner.os == 'Linux'",
                "run": (
                    "sudo apt-get update && sudo apt-get install -y "
                    f"--no-install-recommends {packages}"
                ),
            }
        )
    if requirement.macos:
        packages = " ".join(map(shlex.quote, requirement.macos))
        steps.append(
            {
                "name": "Install macOS system packages",
                "if": "runner.os == 'macOS'",
                "run": f"brew install {packages}",
            }
        )
    if requirement.windows:
        packages = " ".join(requirement.windows)
        steps.append(
            {
                "name": "Install Windows system packages",
                "if": "runner.os == 'Windows'",
                "run": f"choco install {packages} -y --no-progress",
            }
        )
    return tuple(steps)


def register_system_plugin(registry: PluginRegistry) -> None:
    """Register system requirements for supported workflow targets."""

    registry.register_requirement_resolver(
        "github/actions",
        SystemPackages,
        _github_steps,
    )


__all__ = ["SystemPackages", "register_system_plugin"]
