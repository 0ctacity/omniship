from omniship.config.models import OmniShipConfig
from omniship.core.graph import GraphError, StageGraph
from omniship.core.node import Node
from omniship.core.stage import Stage
from omniship.plugins.registry import PluginRegistry


class ConfigValidationError(Exception):
    pass


def validate_config(
    config: OmniShipConfig,
    registry: PluginRegistry | None = None,
) -> dict[Stage, StageGraph]:
    if config.version != 1:
        raise ConfigValidationError(
            f"Unsupported configuration version: {config.version}. Only version 1 is supported."
        )

    stage_mapping = [
        (Stage.CHECK, config.check),
        (Stage.BUILD, config.build),
        (Stage.SHIP, config.ship),
    ]

    graphs: dict[Stage, StageGraph] = {}

    for stage, stage_nodes in stage_mapping:
        graph = StageGraph(stage=stage)

        for node_id, node_cfg in stage_nodes.items():
            if registry is not None:
                if not registry.has_operation(node_cfg.uses):
                    raise ConfigValidationError(
                        f"Stage '{stage.value}', node '{node_id}': Unknown operation '{node_cfg.uses}'."
                    )
                op = registry.get_operation(node_cfg.uses)
                if stage not in op.stages:
                    allowed = ", ".join(s.value for s in op.stages)
                    raise ConfigValidationError(
                        f"Stage '{stage.value}', node '{node_id}': Operation '{node_cfg.uses}' is not allowed in stage '{stage.value}'. Allowed stages: [{allowed}]."
                    )

            node = Node(
                id=node_id,
                stage=stage,
                operation_name=node_cfg.uses,
                inputs=node_cfg.with_,
                dependencies=frozenset(node_cfg.needs),
                condition=node_cfg.condition,
            )
            graph.add_node(node)

        try:
            graph.validate()
        except GraphError as e:
            raise ConfigValidationError(f"Invalid graph for stage '{stage.value}': {e}") from e

        graphs[stage] = graph

    return graphs
