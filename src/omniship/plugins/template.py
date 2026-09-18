from typing import Any

import yaml
from pydantic import BaseModel

from omniship.plugins.metadata import OperationDefinition


def generate_operation_template(definition: OperationDefinition) -> str:
    template_data: dict[str, Any] = {
        "uses": definition.name,
    }

    if definition.config_model and issubclass(definition.config_model, BaseModel):
        with_fields: dict[str, Any] = {}
        for name, field_info in definition.config_model.model_fields.items():
            desc = field_info.description or ""
            # Generate a helpful example value based on type / annotation
            annotation = field_info.annotation
            annotation_str = str(annotation)
            
            if "list" in annotation_str or field_info.default_factory is list:
                example = [f"<{name}_item>"]
            elif "dict" in annotation_str or field_info.default_factory is dict:
                example = {"KEY": "value"}
            elif annotation is bool or field_info.default is False or field_info.default is True:
                example = field_info.default if field_info.default is not None else False
            elif annotation in (int, float):
                example = field_info.default if field_info.default is not None else 0
            else:
                example = f"<{desc or name}>"

            with_fields[name] = example

        template_data["with"] = with_fields
    else:
        template_data["with"] = {}

    return yaml.dump(template_data, sort_keys=False)
