"""Tests for graph analysis methods (cycle detection, components, centrality)."""

from __future__ import annotations

from prefxplain.graph import Edge, Graph, GraphMetadata, Node


def _make_graph(edges: list[tuple[str, str]]) -> Graph:
    """Helper to build a graph from edge tuples."""
    node_ids = set()
    for src, tgt in edges:
        node_ids.add(src)
        node_ids.add(tgt)

    graph = Graph(
        metadata=GraphMetadata(
            repo="test", generated_at="", total_files=len(node_ids), languages=["python"]
        )
    )
    for nid in sorted(node_ids):
        graph.nodes.append(Node(id=nid, label=nid.split("/")[-1], language="python"))
    for src, tgt in edges:
        graph.edges.append(Edge(source=src, target=tgt))
    return graph


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestCycleDetection:
    def test_no_cycles(self) -> None:
        graph = _make_graph([("a.py", "b.py"), ("b.py", "c.py")])
        assert graph.find_cycles() == []

    def test_simple_cycle(self) -> None:
        graph = _make_graph([("a.py", "b.py"), ("b.py", "a.py")])
        cycles = graph.find_cycles()
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a.py", "b.py"}

    def test_three_node_cycle(self) -> None:
        graph = _make_graph([("a.py", "b.py"), ("b.py", "c.py"), ("c.py", "a.py")])
        cycles = graph.find_cycles()
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a.py", "b.py", "c.py"}

    def test_multiple_cycles(self) -> None:
        graph = _make_graph([
            ("a.py", "b.py"), ("b.py", "a.py"),
            ("c.py", "d.py"), ("d.py", "c.py"),
        ])
        cycles = graph.find_cycles()
        assert len(cycles) == 2

    def test_cycle_node_ids(self) -> None:
        graph = _make_graph([("a.py", "b.py"), ("b.py", "a.py"), ("c.py", "a.py")])
        cycle_ids = graph.cycle_node_ids()
        assert "a.py" in cycle_ids
        assert "b.py" in cycle_ids
        assert "c.py" not in cycle_ids

    def test_cycle_edges(self) -> None:
        graph = _make_graph([("a.py", "b.py"), ("b.py", "a.py"), ("c.py", "a.py")])
        cedges = graph.cycle_edges()
        assert ("a.py", "b.py") in cedges
        assert ("b.py", "a.py") in cedges
        assert ("c.py", "a.py") not in cedges

    def test_empty_graph_no_cycles(self) -> None:
        graph = Graph(
            metadata=GraphMetadata(repo="test", generated_at="", total_files=0, languages=[])
        )
        assert graph.find_cycles() == []


# ---------------------------------------------------------------------------
# Connected components
# ---------------------------------------------------------------------------


class TestConnectedComponents:
    def test_single_component(self) -> None:
        graph = _make_graph([("a.py", "b.py"), ("b.py", "c.py")])
        components = graph.connected_components()
        assert len(components) == 1
        assert components[0] == {"a.py", "b.py", "c.py"}

    def test_two_components(self) -> None:
        graph = _make_graph([("a.py", "b.py"), ("c.py", "d.py")])
        components = graph.connected_components()
        assert len(components) == 2

    def test_isolated_node(self) -> None:
        graph = _make_graph([("a.py", "b.py")])
        graph.nodes.append(Node(id="lonely.py", label="lonely.py", language="python"))
        components = graph.connected_components()
        assert len(components) == 2
        # Largest component first
        assert len(components[0]) == 2
        assert len(components[1]) == 1

    def test_empty_graph(self) -> None:
        graph = Graph(
            metadata=GraphMetadata(repo="test", generated_at="", total_files=0, languages=[])
        )
        assert graph.connected_components() == []
