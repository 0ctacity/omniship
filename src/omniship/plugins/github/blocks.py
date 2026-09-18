import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from omniship.core.input import runtime_input_reference
from omniship.core.stage import Stage
from omniship.plugins.github.actions import GitHubBooleanInput, GitHubStringInput
from omniship.workflow.errors import WorkflowError
from omniship.workflow.model import NodeSpec


def _project_version(workspace_root: Path) -> str:
    path = workspace_root / "pyproject.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        version = data["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise WorkflowError(
            "Could not resolve [project].version from pyproject.toml"
        ) from exc
    if not isinstance(version, str) or not version:
        raise WorkflowError("Project version must be a non-empty string")
    return version


def _github_repository(workspace_root: Path) -> str:
    process = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise WorkflowError("Could not resolve GitHub repository from origin remote")
    url = process.stdout.strip()
    if url.startswith("git@github.com:"):
        repository = url.removeprefix("git@github.com:")
    elif url.startswith("https://github.com/"):
        repository = url.removeprefix("https://github.com/")
    else:
        raise WorkflowError("Origin is not a supported GitHub remote")
    return repository.removesuffix(".git")


@dataclass(frozen=True)
class GitHubRelease:
    repository: str | None = None
    tag: str | GitHubStringInput | None = None
    notes: str | None = "auto"
    title: str | None = None
    draft: bool = False
    prerelease: bool | GitHubBooleanInput = False
    files: tuple[str, ...] = ()
    dry_run: bool = False
    name: str = "github-release"

    def compile(self, stage: Stage, workspace_root: Path) -> list[NodeSpec]:
        if stage != Stage.SHIP:
            raise WorkflowError("GitHubRelease can only be used in the ship stage")
        tag: object
        if isinstance(self.tag, GitHubStringInput):
            tag = runtime_input_reference(self.tag.name)
        else:
            tag = self.tag or f"v{_project_version(workspace_root)}"
        params: dict[str, object] = {
            "repository": self.repository or _github_repository(workspace_root),
            "tag": tag,
        }
        if self.notes == "auto":
            params["generate_notes"] = True
        elif self.notes:
            params["body"] = self.notes
        if self.title:
            params["title"] = self.title
        if self.draft:
            params["draft"] = True
        if isinstance(self.prerelease, GitHubBooleanInput):
            params["prerelease"] = runtime_input_reference(self.prerelease.name)
        elif self.prerelease:
            params["prerelease"] = True
        if self.files:
            params["files"] = list(self.files)
        if self.dry_run:
            params["dry_run"] = True
        return [NodeSpec(self.name, stage, "github/release", params)]
