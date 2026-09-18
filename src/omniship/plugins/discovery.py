import logging
from importlib.metadata import entry_points

from omniship.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


def load_plugins(registry: PluginRegistry | None = None) -> PluginRegistry:
    if registry is None:
        registry = PluginRegistry()

    # Official and third-party plugins use the same entry-point path.
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
