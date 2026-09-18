from __future__ import annotations

import json
import shutil
from pathlib import Path

from omniship.core.artifact import Artifact, ArtifactSet

MANIFEST_NAME = "manifest.json"


def export_artifacts(artifacts: ArtifactSet, destination: str | Path) -> Path:
    bundle = Path(destination).resolve()
    items = bundle / "items"
    items.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []

    for index, artifact in enumerate(artifacts):
        if not artifact.path.is_file():
            raise ValueError(f"Artifact is not a file: {artifact.path}")
        stored = Path("items") / f"{index:04d}" / artifact.path.name
        target = bundle / stored
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact.path, target)
        manifest.append(
            {
                "name": artifact.name,
                "path": stored.as_posix(),
                "metadata": dict(artifact.metadata),
            }
        )

    manifest_path = bundle / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps({"version": 1, "artifacts": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def import_artifacts(source: str | Path) -> ArtifactSet:
    bundle = Path(source).resolve()
    manifest_path = bundle / MANIFEST_NAME
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if document.get("version") != 1 or not isinstance(document.get("artifacts"), list):
        raise ValueError(f"Unsupported artifact manifest: {manifest_path}")

    artifacts = ArtifactSet()
    for entry in document["artifacts"]:
        stored = (bundle / entry["path"]).resolve()
        if not stored.is_relative_to(bundle) or not stored.is_file():
            raise ValueError(f"Invalid artifact path in manifest: {entry['path']}")
        artifacts.add(
            Artifact.from_path(
                stored,
                name=entry["name"],
                metadata=entry.get("metadata", {}),
            )
        )
    return artifacts


def import_artifact_bundles(source: str | Path) -> ArtifactSet:
    root = Path(source).resolve()
    manifests = sorted(root.rglob(MANIFEST_NAME))
    if not manifests:
        raise ValueError(f"No artifact manifests found under: {root}")

    artifacts = ArtifactSet()
    for manifest in manifests:
        for artifact in import_artifacts(manifest.parent):
            artifacts.add(artifact)
    return artifacts
