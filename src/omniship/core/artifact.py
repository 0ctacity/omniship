"""Artifact values and the collection used to move outputs between stages."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Mapping


@dataclass(frozen=True, slots=True)
class Artifact:
    """A named file or directory produced by a pipeline operation."""

    path: Path
    name: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        name: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> "Artifact":
        """Create an artifact with an absolute path and copied metadata."""

        p = Path(path).resolve()
        return cls(
            path=p,
            name=name or p.name,
            metadata=dict(metadata or {}),
        )


@dataclass
class ArtifactSet:
    """An insertion-ordered collection deduplicated by artifact path."""

    _artifacts: list[Artifact] = field(default_factory=list)

    def add(self, artifact: Artifact) -> None:
        """Add an artifact unless another artifact already uses its path."""

        # Avoid duplicate identical paths
        if not any(a.path == artifact.path for a in self._artifacts):
            self._artifacts.append(artifact)

    def get(self, name_or_path: str) -> Artifact | None:
        """Find the first artifact by name, full path, or path suffix."""

        for a in self._artifacts:
            if (
                a.name == name_or_path
                or str(a.path) == name_or_path
                or str(a.path).endswith(name_or_path)
            ):
                return a
        return None

    def __iter__(self) -> Iterator[Artifact]:
        return iter(self._artifacts)

    def __len__(self) -> int:
        return len(self._artifacts)

    def __contains__(self, name_or_path: str) -> bool:
        return self.get(name_or_path) is not None

    def to_list(self) -> list[Artifact]:
        """Return a shallow copy suitable for operation inputs."""

        return list(self._artifacts)
