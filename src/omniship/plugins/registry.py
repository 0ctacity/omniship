from omniship.plugins.api import Operation
from omniship.plugins.metadata import OperationDefinition


class RegistryError(Exception):
    pass


class PluginRegistry:
    def __init__(self) -> None:
        self._operations: dict[str, Operation] = {}
        self._definitions: dict[str, OperationDefinition] = {}

    def register_operation(
        self,
        operation: Operation,
        definition: OperationDefinition | None = None,
    ) -> None:
        name = operation.name
        self._operations[name] = operation
        if definition is not None:
            self._definitions[name] = definition
        else:
            self._definitions[name] = OperationDefinition(
                name=name,
                stages=operation.stages,
                cacheable=getattr(operation, "cacheable", False),
            )

    def get_operation(self, name: str) -> Operation:
        if name not in self._operations:
            raise RegistryError(f"Operation '{name}' is not registered.")
        return self._operations[name]

    def get_definition(self, name: str) -> OperationDefinition | None:
        return self._definitions.get(name)

    def has_operation(self, name: str) -> bool:
        return name in self._operations

    def list_operations(self) -> list[OperationDefinition]:
        return list(self._definitions.values())
