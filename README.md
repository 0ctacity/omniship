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
from omniship import Build, Check, Pipeline, Ship
from omniship.plugins.github import GitHubRelease
from omniship.plugins.python import Pytest, Ruff, Wheel

pipeline = Pipeline(
    Check(Ruff(), Pytest()),
    Build(Wheel()),
    Ship(GitHubRelease(repository="owner/project", tag="v1.0.0")),
)
```

### Imperative tasks

Use ordinary Python when a release needs custom logic. Each decorated function
is one DAG node and runs only when the generated pipeline is executed.

```python
from omniship import Pipeline
from omniship.plugins.github import GitHubRelease
from omniship.plugins.python import Python

pipeline = Pipeline()


@pipeline.build
def package(ctx):
    python = Python(ctx)
    version = python.project.version()
    wheel = python.build_wheel()
    if version not in wheel.name:
        ctx.fail(f"Unexpected wheel name: {wheel.name}")
    ctx.artifacts.add(wheel)


pipeline.ship(GitHubRelease(repository="owner/project"))
```

Generate and inspect the YAML before execution:

```bash
omniship generate
omniship plan
omniship ship
```

Use `omniship generate --check` in CI to verify that committed YAML matches
`workflow.py`. Generation refuses to overwrite hand-authored YAML unless
`--force` is supplied.

Workflow files are trusted Python code. Generating a workflow imports it;
executing `core/python` nodes imports it again to call the declared task.
