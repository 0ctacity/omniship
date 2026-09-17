import inspect
from pathlib import Path

from omniship.config.models import NodeConfig, OmniShipConfig
from omniship.core.stage import Stage

from .errors import WorkflowError
from .model import NodeSpec, Pipeline, TaskDeclaration


def compile_pipeline(pipeline: Pipeline, source_path: str | Path) -> OmniShipConfig:
    source = Path(source_path).resolve()
    workspace_root = source.parent
    stages: dict[Stage, dict[str, NodeConfig]] = {stage: {} for stage in Stage}

    for stage in Stage:
        specs: list[NodeSpec] = []
        for entry in pipeline.entries(stage):
            if isinstance(entry, TaskDeclaration):
                if len(inspect.signature(entry.function).parameters) != 1:
                    raise WorkflowError(
                        f"Task '{entry.function.__name__}' must accept exactly one context argument"
                    )
                for dependency in entry.after:
                    if dependency.stage != stage:
                        raise WorkflowError(
                            f"Dependency '{dependency.name}' must be in the same stage"
                        )
                specs.append(
                    NodeSpec(
                        name=entry.ref.name,
                        stage=stage,
                        uses="core/python",
                        params={
                            "callable": f"{source.name}:{entry.function.__name__}"
                        },
                        needs=entry.after,
                    )
                )
            else:
                specs.extend(entry.compile(stage, workspace_root))

        for spec in specs:
            if spec.stage != stage:
                raise WorkflowError(
                    f"Block '{spec.name}' cannot be used in stage '{stage.value}'"
                )
            if spec.name in stages[stage]:
                raise WorkflowError(
                    f"Duplicate node name '{spec.name}' in stage '{stage.value}'"
                )
            for dependency in spec.needs:
                if dependency.stage != stage:
                    raise WorkflowError(
                        f"Dependency '{dependency.name}' must be in the same stage"
                    )
            stages[stage][spec.name] = NodeConfig(
                uses=spec.uses,
                needs=[dependency.name for dependency in spec.needs],
                with_=spec.params,
                if_=spec.condition,
            )

    return OmniShipConfig(
        version=1,
        check=stages[Stage.CHECK],
        build=stages[Stage.BUILD],
        ship=stages[Stage.SHIP],
    )
