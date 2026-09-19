from __future__ import annotations

import gzip
import hashlib
import shutil
import stat
import tarfile
import zipfile
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath

from omniship.core.artifact import Artifact
from omniship.runtime import TaskContext, TaskFailure


class Archive:
    """Create portable archives and register them as task artifacts."""

    def __init__(self, context: TaskContext) -> None:
        self.context = context

    def tar_gz(
        self,
        *,
        output: str | Path,
        files: Mapping[str | Path, str],
        reproducible: bool = True,
        name: str | None = None,
    ) -> Artifact:
        destination, entries = self._prepare(output, files)
        with destination.open("wb") as raw:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw,
                mtime=0 if reproducible else None,
            ) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as archive:
                    for source, archive_name in entries:
                        archive.add(
                            source,
                            arcname=archive_name,
                            recursive=True,
                            filter=(
                                self._normalize_tar_info if reproducible else None
                            ),
                        )
        return self.context.artifacts.add(destination, name=name)

    def zip(
        self,
        *,
        output: str | Path,
        files: Mapping[str | Path, str],
        reproducible: bool = True,
        name: str | None = None,
    ) -> Artifact:
        destination, entries = self._prepare(output, files)
        with zipfile.ZipFile(
            destination,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for source, archive_name in entries:
                for path, member_name in self._walk(source, archive_name):
                    info = zipfile.ZipInfo(member_name)
                    if reproducible:
                        info.date_time = (1980, 1, 1, 0, 0, 0)
                    else:
                        modified = datetime.fromtimestamp(path.stat().st_mtime)
                        info.date_time = max(modified, datetime(1980, 1, 1)).timetuple()[:6]
                    info.create_system = 3
                    mode = (
                        0o755
                        if path.is_dir() or path.stat().st_mode & stat.S_IXUSR
                        else 0o644
                    )
                    kind = stat.S_IFDIR if path.is_dir() else stat.S_IFREG
                    info.external_attr = (kind | mode) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    if path.is_dir():
                        archive.writestr(info, b"")
                    else:
                        with path.open("rb") as source_file, archive.open(info, "w") as target:
                            shutil.copyfileobj(source_file, target)
        return self.context.artifacts.add(destination, name=name)

    def _prepare(
        self,
        output: str | Path,
        files: Mapping[str | Path, str],
    ) -> tuple[Path, tuple[tuple[Path, str], ...]]:
        if not files:
            raise TaskFailure("Archive requires at least one input")
        destination = self._inside_workspace(output, "Archive output")
        entries: list[tuple[Path, str]] = []
        names: set[str] = set()
        for source_value, name_value in files.items():
            source = self._inside_workspace(source_value, "Archive source")
            if not source.exists():
                raise TaskFailure(f"Archive source does not exist: {source_value}")
            if source.is_symlink() or any(path.is_symlink() for path in source.rglob("*")):
                raise TaskFailure(f"Archive sources cannot contain symlinks: {source_value}")
            archive_name = self._archive_name(name_value)
            if archive_name in names:
                raise TaskFailure(f"Duplicate archive destination: {archive_name}")
            names.add(archive_name)
            if destination == source or destination.is_relative_to(source):
                raise TaskFailure("Archive output cannot be inside an input directory")
            entries.append((source, archive_name))
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination, tuple(sorted(entries, key=lambda item: item[1]))

    def _inside_workspace(self, value: str | Path, label: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.context.workspace / path
        path = path.resolve()
        if not path.is_relative_to(self.context.workspace):
            raise TaskFailure(f"{label} escapes workspace: {value}")
        return path

    @staticmethod
    def _archive_name(value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or not value or ".." in path.parts:
            raise TaskFailure(f"Invalid archive destination: {value}")
        return path.as_posix().rstrip("/")

    @staticmethod
    def _normalize_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.mtime = 0
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mode = 0o755 if info.isdir() or info.mode & stat.S_IXUSR else 0o644
        return info

    @staticmethod
    def _walk(source: Path, archive_name: str) -> Iterable[tuple[Path, str]]:
        if source.is_file():
            yield source, archive_name
            return
        yield source, f"{archive_name}/"
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source).as_posix()
            yield path, f"{archive_name}/{relative}{'/' if path.is_dir() else ''}"


class Checksums:
    """Create checksum manifests from artifacts already known to a task."""

    def __init__(self, context: TaskContext) -> None:
        self.context = context

    def sha256(
        self,
        *,
        output: str | Path,
        artifacts: Iterable[Artifact] | None = None,
        name: str | None = None,
    ) -> Artifact:
        selected = tuple(artifacts if artifacts is not None else self.context.artifacts)
        names: set[str] = set()
        lines: list[str] = []
        for artifact in sorted(selected, key=lambda item: item.name):
            if artifact.name in names:
                raise TaskFailure(f"Duplicate artifact name: {artifact.name}")
            if "\n" in artifact.name or "\r" in artifact.name:
                raise TaskFailure("Artifact names cannot contain line breaks")
            if not artifact.path.is_file():
                raise TaskFailure(f"Cannot checksum non-file artifact: {artifact.name}")
            names.add(artifact.name)
            digest = hashlib.sha256()
            with artifact.path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            lines.append(f"{digest.hexdigest()}  {artifact.name}\n")
        if not lines:
            raise TaskFailure("Checksum manifest requires at least one artifact")
        destination = Archive(self.context)._inside_workspace(output, "Checksum output")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("".join(lines), encoding="utf-8", newline="\n")
        return self.context.artifacts.add(destination, name=name)
