import json
from collections.abc import Mapping
from typing import Any

INPUT_REFERENCE_KEY = "$omniship_input"
RUNTIME_INPUTS_ENV = "OMNISHIP_INPUTS"


class RuntimeInputError(ValueError):
    pass


def runtime_input_reference(name: str) -> dict[str, str]:
    return {INPUT_REFERENCE_KEY: name}


def resolve_runtime_inputs(value: Any, inputs: Mapping[str, Any]) -> Any:
    if isinstance(value, dict):
        if set(value) == {INPUT_REFERENCE_KEY}:
            name = value[INPUT_REFERENCE_KEY]
            if not isinstance(name, str) or not name:
                raise RuntimeInputError("Runtime input reference has an invalid name")
            if name not in inputs:
                raise RuntimeInputError(
                    f"Required workflow input '{name}' was not provided"
                )
            return inputs[name]
        return {
            key: resolve_runtime_inputs(item, inputs) for key, item in value.items()
        }
    if isinstance(value, list):
        return [resolve_runtime_inputs(item, inputs) for item in value]
    if isinstance(value, tuple):
        return tuple(resolve_runtime_inputs(item, inputs) for item in value)
    return value


def load_runtime_inputs(env: Mapping[str, str]) -> dict[str, Any]:
    raw = env.get(RUNTIME_INPUTS_ENV)
    if not raw:
        return {}
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeInputError(
            f"{RUNTIME_INPUTS_ENV} must contain valid JSON"
        ) from exc
    if not isinstance(values, dict):
        raise RuntimeInputError(f"{RUNTIME_INPUTS_ENV} must contain a JSON object")
    return values
