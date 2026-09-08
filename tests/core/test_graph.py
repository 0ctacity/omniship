import pytest

from omniship.core.graph import (
    CyclicDependencyError,
    MissingDependencyError,
    StageGraph,
)
from omniship.core.node import Node
from omniship.core.stage import Stage


def test_stage_graph_validation_success():
    graph = StageGraph(stage=Stage.CHECK)
    n1 = Node(id="compile", stage=Stage.CHECK, operation_name="core/noop")
    n2 = Node(
        id="unit",
        stage=Stage.CHECK,
        operation_name="core/noop",
        dependencies=frozenset({"compile"}),
    )
    n3 = Node(
        id="integration",
        stage=Stage.CHECK,
        operation_name="core/noop",
        dependencies=frozenset({"compile"}),
    )
    n4 = Node(
        id="summary",
        stage=Stage.CHECK,
        operation_name="core/noop",
        dependencies=frozenset({"unit", "integration"}),
    )

    for n in (n1, n2, n3, n4):
        graph.add_node(n)

    graph.validate()
    assert [n.id for n in graph.get_roots()] == ["compile"]
    assert [n.id for n in graph.get_terminals()] == ["summary"]

    levels = graph.get_levels()
    assert levels == [["compile"], ["integration", "unit"], ["summary"]]


def test_stage_graph_missing_dependency():
    graph = StageGraph(stage=Stage.CHECK)
    n = Node(
        id="test",
        stage=Stage.CHECK,
        operation_name="core/noop",
        dependencies=frozenset({"nonexistent"}),
    )
    graph.add_node(n)

    with pytest.raises(MissingDependencyError) as exc_info:
        graph.validate()
    assert "nonexistent" in str(exc_info.value)


def test_stage_graph_cycle_detection():
    graph = StageGraph(stage=Stage.CHECK)
    n1 = Node(
        id="a",
        stage=Stage.CHECK,
        operation_name="core/noop",
        dependencies=frozenset({"c"}),
    )
    n2 = Node(
        id="b",
        stage=Stage.CHECK,
        operation_name="core/noop",
        dependencies=frozenset({"a"}),
    )
    n3 = Node(
        id="c",
        stage=Stage.CHECK,
        operation_name="core/noop",
        dependencies=frozenset({"b"}),
    )

    graph.add_node(n1)
    graph.add_node(n2)
    graph.add_node(n3)

    with pytest.raises(CyclicDependencyError) as exc_info:
        graph.validate()
    assert "Cyclic dependency detected" in str(exc_info.value)
