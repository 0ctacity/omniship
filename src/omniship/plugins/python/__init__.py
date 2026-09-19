from omniship.plugins.registry import PluginRegistry

from .blocks import PyPIPublish, Pytest, Ruff, Wheel
from .operations import (
    PytestOperation,
    RuffOperation,
    WheelOperation,
    get_pypi_publish_operation,
    get_python_definitions,
)
from .runtime import Python


def register_python_plugin(registry: PluginRegistry) -> None:
    for operation, definition in zip(
        (
            RuffOperation(),
            PytestOperation(),
            WheelOperation(),
            get_pypi_publish_operation(),
        ),
        get_python_definitions(),
        strict=True,
    ):
        registry.register_operation(operation, definition)


__all__ = [
    "Pytest",
    "PyPIPublish",
    "Python",
    "Ruff",
    "Wheel",
    "register_python_plugin",
]
