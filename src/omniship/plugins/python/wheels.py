from pathlib import Path


def publish_staged_wheels(staging: Path, output: Path) -> list[Path]:
    """Move exactly the wheels produced by one build into its final directory."""
    staged_wheels = sorted(staging.glob("*.whl"))
    output.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    for staged_wheel in staged_wheels:
        destination = output / staged_wheel.name
        staged_wheel.replace(destination)
        published.append(destination)
    return published
