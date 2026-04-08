"""Tests for the HTML renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from prefxplain.analyzer import analyze
from prefxplain.graph import Edge, Graph, GraphMetadata, Node
from prefxplain.renderer import render


@pytest.fixture
def simple_graph() -> Graph:
    graph = Graph(
        metadata=GraphMetadata(
            repo="test-repo",
            generated_at="2026-01-01T00:00:00Z",
            total_files=2,
            languages=["python"],
        )
    )
    graph.nodes.append(Node(id="main.py", label="main.py", description="Entry point.", language="python", size=100))
    graph.nodes.append(Node(id="utils.py", label="utils.py", description="Utility helpers.", language="python", size=50))
    graph.edges.append(Edge(source="main.py", target="utils.py", type="imports"))
    return graph


class TestRenderer:
    def test_returns_html_string(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html or "<html" in html

    def test_contains_node_ids(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert "main.py" in html
        assert "utils.py" in html

    def test_writes_to_file(self, simple_graph: Graph, tmp_path: Path) -> None:
        out = tmp_path / "graph.html"
        render(simple_graph, output_path=out)
        assert out.exists()
        content = out.read_text()
        assert "main.py" in content

    def test_self_contained_no_cdn(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        # No external CDN links
        assert "cdn.jsdelivr.net" not in html
        assert "unpkg.com" not in html
        assert "cdnjs.cloudflare.com" not in html

    def test_descriptions_included(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert "Entry point." in html
        assert "Utility helpers." in html

    def test_empty_graph(self) -> None:
        graph = Graph(
            metadata=GraphMetadata(
                repo="empty",
                generated_at="2026-01-01T00:00:00Z",
                total_files=0,
                languages=[],
            )
        )
        html = render(graph)
        assert isinstance(html, str)
        assert len(html) > 100  # still renders a valid page

    def test_real_project(self, tmp_path: Path) -> None:
        """End-to-end: analyze a real Python project and render it."""
        (tmp_path / "a.py").write_text("from b import foo\ndef main(): pass\n")
        (tmp_path / "b.py").write_text("def foo(): return 1\n")
        graph = analyze(tmp_path)
        html = render(graph)
        assert "a.py" in html
        assert "b.py" in html
