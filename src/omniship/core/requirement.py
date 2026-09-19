"""Composable runtime requirements declared by tasks and blocks."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable


@runtime_checkable
class Requirement(Protocol):
    """A typed capability that an execution target must provision."""

    name: str


def merge_requirements(*groups: Iterable[Requirement]) -> tuple[Requirement, ...]:
    """Merge requirements by name and reject incompatible declarations."""

    merged: list[Requirement] = []
    by_name: dict[str, Requirement] = {}
    for group in groups:
        for requirement in group:
            if not isinstance(requirement, Requirement) or not requirement.name:
                raise ValueError("requirements must provide a non-empty name")
            existing = by_name.get(requirement.name)
            if existing is None:
                by_name[requirement.name] = requirement
                merged.append(requirement)
            elif existing != requirement:
                raise ValueError(
                    f"Conflicting requirement '{requirement.name}': "
                    f"{existing!r} and {requirement!r}"
                )
    return tuple(merged)
