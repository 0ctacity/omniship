from omniship import Check, Pipeline
from omniship.plugins.github import GitHubRelease
from omniship.plugins.python import Pytest, Python, Ruff


pipeline = Pipeline(
    Check(
        Ruff(),
        Pytest(),
    )
)


@pipeline.build
def package(ctx):
    wheel = Python(ctx).build_wheel()
    ctx.artifacts.add(wheel)


pipeline.ship(
    GitHubRelease(
        repository="octacity/omniship",
        tag="v0.1.0",
        notes="auto",
        dry_run=True,
    )
)
