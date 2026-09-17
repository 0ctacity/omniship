from omniship.plugins.github import GitHubRelease
from omniship.plugins.python import Pytest, Ruff, Wheel
from omniship.workflow.model import Build, Check, Pipeline, Ship


def PythonRelease(
    *,
    repository: str | None = None,
    tag: str | None = None,
    coverage: bool = False,
    minimum_coverage: int | None = None,
    verify_wheel: bool = True,
    dry_run: bool = False,
) -> Pipeline:
    return Pipeline(
        Check(Ruff(), Pytest(coverage=coverage, minimum_coverage=minimum_coverage)),
        Build(Wheel(verify=verify_wheel)),
        Ship(
            GitHubRelease(
                repository=repository,
                tag=tag,
                notes="auto",
                dry_run=dry_run,
            )
        ),
    )
