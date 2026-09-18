import pytest

from omniship.config.loader import load_config_from_yaml
from omniship.config.validation import ConfigValidationError
from omniship.plugins.discovery import load_plugins


def test_valid_config_loading():
    yaml_text = """
    version: 1
    check:
      test:
        uses: core/command
        with:
          run: echo "ok"
    build:
      app:
        uses: core/noop
    ship:
      publish:
        uses: core/noop
    """
    cfg = load_config_from_yaml(yaml_text)
    assert cfg.version == 1
    assert "test" in cfg.check
    assert cfg.check["test"].uses == "core/command"
    assert "app" in cfg.build
    assert "publish" in cfg.ship


def test_invalid_operation_rejected():
    registry = load_plugins()
    yaml_text = """
    version: 1
    check:
      bad:
        uses: non_existent/op
    """
    cfg = load_config_from_yaml(yaml_text)
    from omniship.config.validation import validate_config

    with pytest.raises(ConfigValidationError) as exc:
        validate_config(cfg, registry)
    assert "Unknown operation 'non_existent/op'" in str(exc.value)


def test_operation_disallowed_in_stage():
    registry = load_plugins()
    yaml_text = """
    version: 1
    check:
      gh:
        uses: github/release
        with:
          repository: test/repo
          tag: v1.0.0
    """
    cfg = load_config_from_yaml(yaml_text)
    from omniship.config.validation import validate_config

    with pytest.raises(ConfigValidationError) as exc:
        validate_config(cfg, registry)
    assert "Operation 'github/release' is not allowed in stage 'check'" in str(exc.value)


def test_cycle_in_config_rejected():
    registry = load_plugins()
    yaml_text = """
    version: 1
    check:
      a:
        uses: core/noop
        needs: [b]
      b:
        uses: core/noop
        needs: [a]
    """
    cfg = load_config_from_yaml(yaml_text)
    from omniship.config.validation import validate_config

    with pytest.raises(ConfigValidationError) as exc:
        validate_config(cfg, registry)
    assert "Cyclic dependency" in str(exc.value)
