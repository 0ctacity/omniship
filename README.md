# OmniShip (v0.1)

OmniShip is a plugin-driven DAG executor designed around three strict stage boundaries:
`Check` → `Build` → `Ship`.

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
   - Built-ins: `core/command`, `core/noop`, `github/release`.

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
