from omniship.core.stage import Stage
from omniship.plugins.discovery import load_plugins
from omniship.plugins.metadata import OperationDefinition
from omniship.plugins.registry import PluginRegistry
from omniship.plugins.template import generate_operation_template


def test_plugin_registry_and_discovery():
    reg = load_plugins()
    assert reg.has_operation("core/command")
    assert reg.has_operation("core/noop")
    assert reg.has_operation("core/python")
    assert reg.has_operation("python/ruff")
    assert reg.has_operation("python/pytest")
    assert reg.has_operation("python/wheel")
    assert reg.has_operation("github/release")

    op = reg.get_operation("core/command")
    assert op.name == "core/command"
    assert Stage.BUILD in op.stages


def test_operation_template_generation():
    reg = load_plugins()
    cmd_def = reg.get_definition("core/command")
    assert cmd_def is not None

    template = generate_operation_template(cmd_def)
    assert "uses: core/command" in template
    assert "run:" in template
    assert "artifacts:" in template


def test_custom_plugin_registration():
    reg = PluginRegistry()

    class CustomOp:
        name = "custom/test"
        stages = frozenset({Stage.CHECK})
        cacheable = True

        async def execute(self, context, inputs):
            pass

    def custom_plugin(r: PluginRegistry):
        r.register_operation(CustomOp())

    custom_plugin(reg)
    assert reg.has_operation("custom/test")
    definition = reg.get_definition("custom/test")
    assert definition.name == "custom/test"
    assert definition.cacheable is True
