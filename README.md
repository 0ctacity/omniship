# OmniShip (v0.1)

OmniShip is a plugin-driven DAG executor designed around three strict stage boundaries:
`Check` → `Build` → `Ship`.

Pipelines can be authored directly as YAML or generated from Python. Python
workflows combine recipes, typed blocks, and imperative tasks while compiling
to the same validated YAML and execution engine.

---

## Architecture

1. **Strict Stage Boundaries**:
   - `CHECK`: Unit tests, integration tests, linting, code preparation.
   - `BUILD`: Compiles binaries, bundles assets, produces named `Artifact`s.
   - `SHIP`: Consumes produced artifacts, publishes releases, notifies destinations.
   - All nodes in a stage must succeed before the next stage starts.

2. **Async DAG Execution**:
   - Sequential dependencies (`needs: [...]`)
   - Concurrent parallel fan-out
   - Fan-in barriers
   - Automatic cycle detection
   - Failure propagation & downstream skipping

3. **First-Class Artifacts**:
   - Build operations produce declared artifacts.
   - Validated on disk, indexed in `ArtifactSet`, and made available to the `Ship` stage.

4. **Plugin Architecture**:
   - Standard Python package entry-point discovery: `omniship.plugins`.
   - First-party operations use the exact same registration protocol as third-party plugins.
   - Core operations: `core/command`, `core/noop`, `core/python`.
   - Bundled official providers: Python (`python/ruff`, `python/pytest`,
     `python/wheel`) and GitHub (`github/release`).

---

## Configuration (`omniship.yaml`)

```yaml
version: 1

check:
  prepare:
    uses: core/command
    with:
      run: ./scripts/prepare.sh

  test-a:
    uses: core/command
    needs: [prepare]
    with:
      run: pytest tests/test_a.py

  test-b:
    uses: core/command
    needs: [prepare]
    with:
      run: pytest tests/test_b.py

build:
  linux:
    uses: core/command
    with:
      run: ./scripts/build-linux.sh
      artifacts:
        - dist/linux/app

  macos:
    uses: core/command
    with:
      run: ./scripts/build-macos.sh
      artifacts:
        - dist/macos/app

ship:
  github:
    uses: github/release
    with:
      repository: octacity/example
      tag: v0.1.0
      dry_run: true
```

---

## CLI Usage

```bash
# Run Check only
omniship check

# Run Check → Build
omniship build

# Run Build only (skip Check)
omniship build --skip-check

# Run full flow: Check → Build → Ship
omniship ship

# Inspect the execution DAG
omniship plan

# List registered plugins & operations
omniship plugins

# View operation details or generate YAML config template
omniship plugin show core/command
omniship plugin template core/command
```

---

## Python Workflows

Create `workflow.py` in a project and choose the level of control you need.

### Recipe

```python
from omniship.recipes import PythonRelease

pipeline = PythonRelease(repository="owner/project")
```

### Typed blocks

```python
from omniship import Pipeline
from omniship.plugins.github import GitHubRelease
from omniship.plugins.python import Pytest, Ruff, Wheel

pipeline = Pipeline()


@pipeline.check
def check(stage):
    stage.task(Ruff())
    stage.task(Pytest())


@pipeline.build
def build(stage):
    stage.task(Wheel())


@pipeline.ship
def ship(stage):
    stage.task(GitHubRelease(repository="owner/project"))
```

Execution placement belongs to each DAG node, not to a whole stage. A node can
run once or fan out over a GitHub Actions runner matrix:

```python
from omniship import Pipeline
from omniship.plugins.github import GitHubActions, GitHubRunner
from omniship.plugins.python import Pytest, Ruff

github = GitHubActions(default_runner=GitHubRunner.UBUNTU_24_04)
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
            ],
            fail_fast=False,
        ),
    )
```

### Imperative tasks

Each `@pipeline.check`, `@pipeline.build`, or `@pipeline.ship` function defines
one stage DAG during generation. Only `stage.task(...)` creates a node. A
nested task function receives the runtime context and executes later in the
generated pipeline.

```python
from omniship import Pipeline
from omniship.plugins.github import GitHub, GitHubActions, GitHubRunner
from omniship.plugins.python import Python

github = GitHubActions()
pipeline = Pipeline(targets=[github])


@pipeline.build
def build(stage):
    @stage.task(
        execution=github.job(
            runners=[GitHubRunner.UBUNTU_24_04, GitHubRunner.MACOS_15]
        )
    )
    def package(ctx):
        python = Python(ctx)
        version = python.project.version()
        wheel = python.build_wheel()
        if version not in wheel.name:
            ctx.fail(f"Unexpected wheel name: {wheel.name}")
        ctx.artifacts.add(wheel)


@pipeline.ship
def ship(stage):
    @stage.task
    def release(ctx):
        version = Python(ctx).project.version()
        GitHub(ctx).release(
            repository="owner/project",
            tag=f"v{version}",
            notes="auto",
        )
```

`stage` is a generation-time declaration context; `ctx` is a runtime task
context. A declared stage with no tasks is rejected instead of being treated as
an implicit task.

Provider blocks use these same imperative capabilities underneath. For example,
`GitHubRelease(...)` validates and compiles the release node, while its operation
delegates publishing to `GitHub(ctx).release(...)`.

Generate and inspect the release files before execution:

```bash
omniship generate
omniship plan
omniship ship
```

`omniship generate` always writes `omniship.yaml`. Installed providers may
contribute additional generated files. A pipeline containing `GitHubRelease`,
or an explicit `GitHubActions` target for imperative publishing, also produces
`.github/workflows/release.yml` through the GitHub plugin.

Use `omniship generate --check` in CI to verify that every committed generated
file matches `workflow.py`. Generation refuses to overwrite hand-authored YAML
unless `--force` is supplied.

### GitHub Actions releases

The GitHub plugin generates a tag-triggered Actions workflow with one job per
DAG node. Nodes without explicit placement use `default_runner`; nodes with
multiple runners use a matrix. Small barrier jobs preserve the strict
Check → Build → Ship ordering while independent nodes in a stage still run in
parallel.

Every successful Build node uploads its own OmniShip artifact bundle. A
dependent Build node downloads its predecessors' bundles, and every Ship node
downloads all completed Build bundles. OmniShip restores them into the normal
artifact context before executing the node.

Generated workflows default to `contents: read`. Typed GitHub blocks declare
their minimum permissions, so a non-dry-run `GitHubRelease` receives
`contents: write` only on its generated job. Developers do not need to
configure a release token on their machines.

```yaml
permissions:
  contents: read

jobs:
  check-pytest:
    runs-on: ${{ matrix.runner }}
    strategy:
      matrix:
        runner: [ubuntu-24.04, macos-15, windows-2025]
  check-complete:
    needs: check-pytest
  build-wheel:
    needs: check-complete
  build-complete:
    needs: build-wheel
  ship-github-release:
    needs: build-complete
    permissions:
      contents: write
```

Permissions are typed and can also be controlled explicitly for imperative
tasks:

```python
from omniship import Pipeline
from omniship.plugins.github import (
    GitHub,
    GitHubActions,
    GitHubPermission,
    GitHubPermissions,
)

github = GitHubActions(
    default_permissions=GitHubPermissions(
        contents=GitHubPermission.READ,
    ),
)
pipeline = Pipeline(targets=[github])


@pipeline.ship
def ship(stage):
    @stage.task(
        execution=github.job(
            permissions=GitHubPermissions(
                contents=GitHubPermission.WRITE,
            ),
        )
    )
    def release(ctx):
        GitHub(ctx).release(repository="owner/project", tag="v1.0.0")
```

`GitHubActions(default_permissions=...)` changes the workflow default.
Explicit permissions that are weaker than a typed block's requirements are
rejected during generation. Tasks without GitHub permissions do not receive a
`GITHUB_TOKEN` environment variable.

OmniShip uses this mechanism for its own [release definition](workflow.py),
[compiled pipeline](omniship.yaml), and [GitHub Actions workflow](.github/workflows/release.yml).
`github/release` fails if `GITHUB_TOKEN` is absent, except when the block
explicitly uses `dry_run=True`. Tokens cannot be supplied through Python
blocks or generated OmniShip YAML.

Workflow files are trusted Python code. Generating a workflow imports it;
executing `core/python` nodes imports it again to call the declared task.
