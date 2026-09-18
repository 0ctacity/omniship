from pathlib import Path

import yaml

from omniship.config.models import OmniShipConfig
from omniship.config.validation import validate_config
from omniship.core.graph import StageGraph
from omniship.core.stage import Stage
from omniship.plugins.registry import PluginRegistry


class ConfigLoadError(Exception):
    pass


def find_config_file(directory: Path | None = None) -> Path | None:
    d = (directory or Path.cwd()).resolve()
    for candidate in ("omniship.yaml", "omniship.yml"):
        p = d / candidate
        if p.is_file():
            return p
    return None


def load_config_from_yaml(content: str) -> OmniShipConfig:
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"YAML parsing error: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigLoadError("Configuration file must contain a top-level mapping/dictionary")

    try:
        return OmniShipConfig.model_validate(data)
    except Exception as exc:
        raise ConfigLoadError(f"Configuration schema validation failed: {exc}") from exc


def load_config_from_file(path: str | Path) -> OmniShipConfig:
    p = Path(path).resolve()
    if not p.is_file():
        raise ConfigLoadError(f"Configuration file not found: {p}")
    try:
        content = p.read_text(encoding="utf-8")
    except Exception as exc:
        raise ConfigLoadError(f"Failed to read configuration file: {exc}") from exc
    return load_config_from_yaml(content)


def load_and_validate(
    path: str | Path,
    registry: PluginRegistry,
) -> tuple[OmniShipConfig, dict[Stage, StageGraph]]:
    config = load_config_from_file(path)
    graphs = validate_config(config, registry)
    return config, graphs
