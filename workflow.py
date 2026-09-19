from omniship import Pipeline
from omniship.plugins.github import (
    GitHubActions,
    GitHubBootstrap,
    GitHubRelease,
    GitHubRunner,
)
from omniship.plugins.python import Pytest, Ruff, Wheel

github = GitHubActions(
    bootstrap=GitHubBootstrap.WORKSPACE,
    default_runner=GitHubRunner.UBUNTU_24_04,
)
pipeline = Pipeline(targets=[github])


@pipeline.check
def check(stage):
    stage.task(
        Ruff(),
        execution=github.job(runners=[GitHubRunner.UBUNTU_SLIM]),
    )
    stage.task(
        Pytest(),
        execution=github.job(
            runners=[
                GitHubRunner.UBUNTU_24_04,
                GitHubRunner.MACOS_15,
                GitHubRunner.WINDOWS_2025,
            ]
        ),
    )


@pipeline.build
def build(stage):
    stage.task(
        Wheel(),
        execution=github.job(runners=[GitHubRunner.UBUNTU_24_04]),
    )


@pipeline.ship
def ship(stage):
    stage.task(
        GitHubRelease(
            repository="0ctacity/omniship",
            notes="auto",
        ),
    )
