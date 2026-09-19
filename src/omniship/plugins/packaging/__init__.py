from omniship.plugins.registry import PluginRegistry

from .blocks import Sha256Manifest, TarGz, Zip
from .operations import (
    ArchiveOperation,
    Sha256ManifestOperation,
    get_packaging_definitions,
)
from .runtime import Archive, Checksums


def register_packaging_plugin(registry: PluginRegistry) -> None:
    operations = (
        ArchiveOperation("tar-gz"),
        ArchiveOperation("zip"),
        Sha256ManifestOperation(),
    )
    for operation, definition in zip(
        operations,
        get_packaging_definitions(),
        strict=True,
    ):
        registry.register_operation(operation, definition)


__all__ = [
    "Archive",
    "Checksums",
    "Sha256Manifest",
    "TarGz",
    "Zip",
    "register_packaging_plugin",
]
