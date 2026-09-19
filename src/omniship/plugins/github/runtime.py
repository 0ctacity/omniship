from __future__ import annotations

import json
import shutil
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from omniship.core.artifact import Artifact
from omniship.runtime import TaskContext, TaskFailure

PAGES_STAGING_PATH = Path(".omniship/pages/site")


@dataclass(frozen=True, slots=True)
class GitHubReleaseResult:
    repository: str
    tag: str
    release_url: str
    uploaded_count: int


@dataclass(frozen=True, slots=True)
class GitHubPagesResult:
    artifact: str
    path: Path


@dataclass(frozen=True, slots=True)
class GitHubTagResult:
    repository: str
    tag: str
    target: str


class GitHub:
    """Typed GitHub capability facade for an imperative task context."""

    def __init__(self, context: TaskContext) -> None:
        self.context = context

    def release(
        self,
        repository: str,
        tag: str,
        *,
        notes: str | None = "auto",
        title: str | None = None,
        draft: bool = False,
        prerelease: bool = False,
        files: Iterable[str] = (),
        dry_run: bool = False,
    ) -> GitHubReleaseResult:
        token = self.context.env.get("GITHUB_TOKEN")
        if not dry_run and not token:
            raise TaskFailure(
                "GITHUB_TOKEN is required for github/release when dry_run is false"
            )

        artifacts = self._select_artifacts(tuple(files))
        release_url = f"https://github.com/{repository}/releases/tag/{tag}"
        if dry_run:
            self._log_dry_run(repository, tag, title, artifacts)
            return GitHubReleaseResult(
                repository=repository,
                tag=tag,
                release_url=release_url,
                uploaded_count=len(artifacts),
            )

        try:
            payload = json.dumps(
                {
                    "tag_name": tag,
                    "name": title or tag,
                    "body": "" if notes in (None, "auto") else notes,
                    "generate_release_notes": notes == "auto",
                    "draft": draft,
                    "prerelease": prerelease,
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                f"https://api.github.com/repos/{repository}/releases",
                data=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "OmniShip-v0.1",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            release_url = data.get("html_url", "")
            self._upload_artifacts(token, data.get("upload_url", ""), artifacts)
        except Exception as exc:
            raise TaskFailure(f"GitHub release creation failed: {exc}") from exc

        self.context.log.info(
            f"Successfully published release {tag} to {release_url}"
        )
        return GitHubReleaseResult(
            repository=repository,
            tag=tag,
            release_url=release_url,
            uploaded_count=len(artifacts),
        )

    def tag(
        self,
        repository: str,
        tag: str,
        *,
        target: str | None = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> GitHubTagResult:
        target = target or self.context.env.get("GITHUB_SHA")
        if not target:
            raise TaskFailure(
                "GitHub tag target is required outside GitHub Actions"
            )
        token = self.context.env.get("GITHUB_TOKEN")
        if not dry_run and not token:
            raise TaskFailure(
                "GITHUB_TOKEN is required for github/tag when dry_run is false"
            )
        if dry_run:
            self.context.log.info("[github/tag] Simulated tag creation (dry run)")
            self.context.log.info(f"[github/tag] Target repository: {repository}")
            self.context.log.info(f"[github/tag] Tag: {tag} -> {target}")
            return GitHubTagResult(repository, tag, target)

        ref = f"tags/{tag}"
        try:
            if force:
                request = urllib.request.Request(
                    f"https://api.github.com/repos/{repository}/git/refs/{ref}",
                    data=json.dumps({"sha": target, "force": True}).encode("utf-8"),
                    headers=self._api_headers(token),
                    method="PATCH",
                )
            else:
                request = urllib.request.Request(
                    f"https://api.github.com/repos/{repository}/git/refs",
                    data=json.dumps(
                        {"ref": f"refs/tags/{tag}", "sha": target}
                    ).encode("utf-8"),
                    headers=self._api_headers(token),
                    method="POST",
                )
            with urllib.request.urlopen(request, timeout=15):
                pass
        except Exception as exc:
            raise TaskFailure(f"GitHub tag creation failed: {exc}") from exc
        self.context.log.info(f"Created GitHub tag {tag} at {target}")
        return GitHubTagResult(repository, tag, target)

    def pages(self, *, artifact: str = "site") -> GitHubPagesResult:
        selected = self.context.artifacts.get(artifact)
        if selected is None:
            raise TaskFailure(f"GitHub Pages artifact '{artifact}' was not found")
        if not selected.path.is_dir():
            raise TaskFailure(
                f"GitHub Pages artifact '{artifact}' must be a directory"
            )

        symlink = next(
            (candidate for candidate in selected.path.rglob("*") if candidate.is_symlink()),
            None,
        )
        if symlink is not None:
            raise TaskFailure(
                f"GitHub Pages artifact '{artifact}' contains a symlink: {symlink}"
            )
        if not any(candidate.is_file() for candidate in selected.path.rglob("*")):
            raise TaskFailure(f"GitHub Pages artifact '{artifact}' is empty")

        destination = (self.context.workspace / PAGES_STAGING_PATH).resolve()
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(selected.path, destination)
        self.context.log.info(
            f"Prepared GitHub Pages artifact '{artifact}' at {destination}"
        )
        return GitHubPagesResult(artifact=artifact, path=destination)

    def _select_artifacts(self, files: tuple[str, ...]) -> list[Artifact]:
        available = tuple(self.context.artifacts)
        if not files:
            return list(available)

        selected: list[Artifact] = []
        for file_ref in files:
            artifact = next(
                (
                    item
                    for item in available
                    if item.name == file_ref
                    or str(item.path) == file_ref
                    or str(item.path).endswith(file_ref)
                ),
                None,
            )
            if artifact is not None:
                selected.append(artifact)
                continue
            path = (self.context.workspace / file_ref).resolve()
            if not path.exists():
                raise TaskFailure(
                    f"Artifact '{file_ref}' not found in context or workspace"
                )
            selected.append(Artifact.from_path(path))
        return selected

    def _log_dry_run(
        self,
        repository: str,
        tag: str,
        title: str | None,
        artifacts: list[Artifact],
    ) -> None:
        self.context.log.info("[github/release] Simulated release (dry run)")
        self.context.log.info(f"[github/release] Target repository: {repository}")
        self.context.log.info(f"[github/release] Tag: {tag}")
        self.context.log.info(f"[github/release] Title: {title or tag}")
        self.context.log.info(
            f"[github/release] Artifacts to attach ({len(artifacts)}):"
        )
        for artifact in artifacts:
            self.context.log.info(f"  - {artifact.name} ({artifact.path})")

    @staticmethod
    def _api_headers(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "OmniShip-v0.1",
        }

    @staticmethod
    def _upload_artifacts(
        token: str,
        upload_url: str,
        artifacts: list[Artifact],
    ) -> None:
        if not upload_url or "{" not in upload_url:
            return
        base_upload_url = upload_url.split("{")[0]
        for artifact in artifacts:
            if not artifact.path.is_file():
                continue
            request = urllib.request.Request(
                f"{base_upload_url}?name={artifact.name}",
                data=artifact.path.read_bytes(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/octet-stream",
                    "User-Agent": "OmniShip-v0.1",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30):
                pass
