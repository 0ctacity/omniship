from importlib.metadata import entry_points
import logging

from omniship.operations import register_core_plugin
from omniship.operations.github import register_github_plugin
from omniship.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


def load_plugins(registry: PluginRegistry | None = None) -> PluginRegistry:
    if registry is None:
        registry = PluginRegistry()

    # Register first-party built-in plugins using the standard plugin interface
    register_core_plugin(registry)
    register_github_plugin(registry)

    # Discover external plugins via standard Python entry points
    try:
        eps = entry_points()
        if hasattr(eps, "select"):
            discovered = eps.select(group="omniship.plugins")
        else:
            discovered = eps.get("omniship.plugins", [])

        for ep in discovered:
            try:
                plugin = ep.load()
                if callable(plugin):
                    plugin(registry)
                elif hasattr(plugin, "register") and callable(plugin.register):
                    plugin.register(registry)
            except Exception as e:
                logger.warning(f"Failed to load plugin '{ep.name}': {e}")
    except Exception as e:
        logger.warning(f"Error during entry points discovery: {e}")

    return registry
