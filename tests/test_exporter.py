"""Tests for Mermaid and DOT exporters."""

from __future__ import annotations

from prefxplain.exporter import _sanitize_mermaid_id, export_dot, export_mermaid
from prefxplain.graph import Edge, Graph, GraphMetadata, Node


def _simple_graph() -> Graph:
    graph = Graph(
        metadata=GraphMetadata(
            repo="test", generated_at="", total_files=2, languages=["python"]
        )
    )
    graph.nodes.append(Node(id="main.py", label="main.py", language="python"))
    graph.nodes.append(Node(id="utils.py", label="utils.py", language="python"))
    graph.edges.append(Edge(source="main.py", target="utils.py"))
    return graph


class TestSanitizeMermaidId:
    def test_simple_name(self) -> None:
        seen: dict[str, int] = {}
        assert _sanitize_mermaid_id("main_py", seen) == "main_py"

    def test_dots_and_slashes(self) -> None:
        seen: dict[str, int] = {}
        result = _sanitize_mermaid_id("src/utils.py", seen)
        assert "/" not in result
        assert "." not in result

    def test_collision_detection(self) -> None:
        seen: dict[str, int] = {}
        id1 = _sanitize_mermaid_id("src/a.py", seen)
        id2 = _sanitize_mermaid_id("src_a.py", seen)
        assert id1 != id2  # should get unique suffixed IDs


class TestMermaidExport:
    def test_basic_export(self) -> None:
        graph = _simple_graph()
        mermaid = export_mermaid(graph)
        assert "graph LR" in mermaid
        assert "main_py" in mermaid
        assert "utils_py" in mermaid
        assert "-->" in mermaid

    def test_cycle_styling(self) -> None:
        graph = _simple_graph()
        graph.edges.append(Edge(source="utils.py", target="main.py"))
        mermaid = export_mermaid(graph)
        assert "cycle" in mermaid.lower()

    def test_empty_graph(self) -> None:
        graph = Graph(
            metadata=GraphMetadata(repo="test", generated_at="", total_files=0, languages=[])
        )
        mermaid = export_mermaid(graph)
        assert "graph LR" in mermaid


class TestDotExport:
    def test_basic_export(self) -> None:
        graph = _simple_graph()
        dot = export_dot(graph)
        assert "digraph" in dot
        assert "main.py" in dot
        assert "utils.py" in dot
        assert "->" in dot

    def test_cycle_edges_red(self) -> None:
        graph = _simple_graph()
        graph.edges.append(Edge(source="utils.py", target="main.py"))
        dot = export_dot(graph)
        assert "red" in dot

    def test_empty_graph(self) -> None:
        graph = Graph(
            metadata=GraphMetadata(repo="test", generated_at="", total_files=0, languages=[])
        )
        dot = export_dot(graph)
        assert "digraph" in dot
