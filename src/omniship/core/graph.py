from collections import defaultdict, deque
from dataclasses import dataclass, field

from omniship.core.node import Node
from omniship.core.stage import Stage


class GraphError(Exception):
    pass


class CyclicDependencyError(GraphError):
    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        super().__init__(f"Cyclic dependency detected: {' -> '.join(cycle)}")


class MissingDependencyError(GraphError):
    def __init__(self, node_id: str, missing: str):
        self.node_id = node_id
        self.missing = missing
        super().__init__(f"Node '{node_id}' depends on non-existent node '{missing}'")


@dataclass
class StageGraph:
    stage: Stage
    nodes: dict[str, Node] = field(default_factory=dict)
    _dependents: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add_node(self, node: Node) -> None:
        if node.stage != self.stage:
            raise GraphError(
                f"Cannot add node '{node.id}' with stage '{node.stage}' to '{self.stage}' graph"
            )
        self.nodes[node.id] = node
        for dep in node.dependencies:
            self._dependents[dep].add(node.id)

    def validate(self) -> None:
        # 1. Check for missing dependencies
        for node_id, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    raise MissingDependencyError(node_id, dep)

        # 2. Cycle detection via DFS (3-color tracking: 0=unvisited, 1=visiting, 2=visited)
        visited: dict[str, int] = {}
        def dfs(curr: str, path: list[str]) -> None:
            visited[curr] = 1
            for nxt in self._dependents.get(curr, set()):
                if visited.get(nxt, 0) == 1:
                    cycle = path + [nxt]
                    # trim to actual cycle start
                    cycle_start = cycle.index(nxt)
                    raise CyclicDependencyError(cycle[cycle_start:])
                elif visited.get(nxt, 0) == 0:
                    dfs(nxt, path + [nxt])
            visited[curr] = 2

        for node_id in self.nodes:
            if visited.get(node_id, 0) == 0:
                dfs(node_id, [node_id])

    def get_roots(self) -> list[Node]:
        return [node for node in self.nodes.values() if not node.dependencies]

    def get_terminals(self) -> list[Node]:
        return [
            node
            for node_id, node in self.nodes.items()
            if not self._dependents.get(node_id)
        ]

    def get_direct_dependents(self, node_id: str) -> set[str]:
        return set(self._dependents.get(node_id, set()))

    def get_all_downstream(self, node_id: str) -> set[str]:
        downstream = set()
        queue = deque(self._dependents.get(node_id, set()))
        while queue:
            curr = queue.popleft()
            if curr not in downstream:
                downstream.add(curr)
                queue.extend(self._dependents.get(curr, set()))
        return downstream

    def get_levels(self) -> list[list[str]]:
        self.validate()
        in_degree = {n: len(node.dependencies) for n, node in self.nodes.items()}
        queue = deque([n for n, deg in in_degree.items() if deg == 0])
        levels: list[list[str]] = []

        while queue:
            current_level = []
            next_queue = deque()
            for _ in range(len(queue)):
                curr = queue.popleft()
                current_level.append(curr)
                for dep_id in sorted(self._dependents.get(curr, set())):
                    in_degree[dep_id] -= 1
                    if in_degree[dep_id] == 0:
                        next_queue.append(dep_id)
            levels.append(sorted(current_level))
            queue = next_queue
        return levels
