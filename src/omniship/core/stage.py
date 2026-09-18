"""Delivery stages shared by workflow declarations and runtime execution."""

from enum import StrEnum


class Stage(StrEnum):
    """A phase of an OmniShip pipeline, in execution order."""

    CHECK = "check"
    BUILD = "build"
    SHIP = "ship"
