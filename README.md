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
        execution=github.job(runners=[GitHubRunner.UBUNTU_24_04, GitHubRunner.MACOS_15])
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
`.github/workflows/check.yml`, `.github/workflows/build.yml`, and
`.github/workflows/ship.yml` through the GitHub plugin.

Use `omniship generate --check` in CI to verify that every committed generated
file matches `workflow.py`. Generation refuses to overwrite hand-authored YAML
unless `--force` is supplied.

### GitHub Actions workflows

The GitHub plugin generates one workflow per stage. `check.yml` runs for pull
requests and pushes to `main`, and can also be called by another workflow.
`build.yml` is callable. The tag-triggered `ship.yml` composes both reusable
workflows before running the Ship DAG. Nodes without explicit placement use
`default_runner`; nodes with multiple runners use a matrix.

The filenames and names shown by GitHub can be changed in `workflow.py`:

```python
from omniship.plugins.github import GitHubActions, GitHubWorkflow

github = GitHubActions(
    check=GitHubWorkflow(file="ci.yml", name="CI"),
    build=GitHubWorkflow(file="package.yml", name="Package"),
    ship=GitHubWorkflow(file="publish.yml", name="Publish"),
)
```

External triggers are typed as well. Omitting `triggers` preserves the stage
defaults; passing an empty list disables external triggers while keeping the
internal reusable-workflow links required by later stages:

```python
from omniship.plugins.github import (
    GitHubActions,
    GitHubPullRequest,
    GitHubPush,
    GitHubWorkflow,
    GitHubWorkflowDispatch,
)

github = GitHubActions(
    check=GitHubWorkflow(
        file="ci.yml",
        name="CI",
        triggers=[
            GitHubPullRequest(
                branches=["main", "develop"],
                paths=["src/**", "tests/**"],
            ),
            GitHubPush(
                branches=["main", "develop"],
                paths_ignore=["docs/**"],
            ),
            GitHubWorkflowDispatch(),
        ],
    ),
    build=GitHubWorkflow(
        file="build.yml",
        name="Build",
        triggers=[],
    ),
    ship=GitHubWorkflow(
        file="ship.yml",
        name="Ship",
        triggers=[GitHubPush(tags=["release-*"])],
    ),
)
```

Manual workflows can declare typed inputs and bind them directly to typed
blocks. Imperative tasks read the same values from `ctx.inputs`:

```python
from omniship import Pipeline
from omniship.plugins.github import (
    GitHubActions,
    GitHubBooleanInput,
    GitHubRelease,
    GitHubStringInput,
    GitHubWorkflow,
    GitHubWorkflowDispatch,
)

tag = GitHubStringInput("tag", description="Tag to release", required=True)
prerelease = GitHubBooleanInput("prerelease", default=False)

github = GitHubActions(
    ship=GitHubWorkflow(
        file="ship.yml",
        name="Ship",
        triggers=[GitHubWorkflowDispatch(inputs=[tag, prerelease])],
    )
)
pipeline = Pipeline(targets=[github])


@pipeline.ship
def ship(stage):
    stage.task(
        GitHubRelease(
            repository="owner/project",
            tag=tag,
            prerelease=prerelease,
        )
    )

    @stage.task
    def announce(ctx):
        ctx.log.info(f"Releasing {ctx.inputs['tag']}")
```

This is optional. `GitHubRelease()` without a `tag` keeps the default behavior:
OmniShip reads the project version from `pyproject.toml` and releases
`v<version>`.

### Logging

Logging is automatic. OmniShip prints stage and task lifecycle events, streams
built-in command output while the task is running, labels concurrent output by
task, reports durations, and includes errors automatically. Generated GitHub
Actions workflows also use readable job and step names; task warnings and
errors become GitHub annotations.

Imperative tasks can add structured messages when useful. Ordinary `print()`
also remains visible:

```python
@pipeline.build
def build(stage):
    @stage.task
    def package(ctx):
        ctx.log.debug("Resolved build configuration")
        ctx.log.info("Building wheel")
        ctx.log.warning("Using compatibility mode")
        # ctx.log.error(...) reports an error without failing the task.
        # Use ctx.fail(...) when execution must stop.
```

The default is equivalent to `Logging()` and requires no configuration. A
pipeline can adjust verbosity without changing its tasks:

```python
from omniship import LogLevel, Logging, Pipeline

pipeline = Pipeline(
    logging=Logging(
        level=LogLevel.INFO,
        show_output=True,
        timestamps=False,
    )
)
```

`level` sets the minimum message severity (subprocess output is `INFO`),
`show_output` controls subprocess stdout and stderr, and `timestamps` adds
local timestamps. Lifecycle and final task status remain visible even when
command output is hidden.

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
  check:
    uses: ./.github/workflows/check.yml
  build:
    needs: check
    uses: ./.github/workflows/build.yml
  ship-github-release:
    needs: build
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
[compiled pipeline](omniship.yaml), and generated GitHub Actions
[Check](.github/workflows/check.yml), [Build](.github/workflows/build.yml), and
[Ship](.github/workflows/ship.yml) workflows.
`github/release` fails if `GITHUB_TOKEN` is absent, except when the block
explicitly uses `dry_run=True`. Tokens cannot be supplied through Python
blocks or generated OmniShip YAML.

Workflow files are trusted Python code. Generating a workflow imports it;
executing `core/python` nodes imports it again to call the declared task.
