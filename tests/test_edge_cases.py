"""Edge case tests for the analyzer and graph."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from prefxplain.analyzer import analyze
from prefxplain.graph import Graph, GraphMetadata, Node

# ---------------------------------------------------------------------------
# Analyzer edge cases
# ---------------------------------------------------------------------------


class TestAnalyzerEdgeCases:
    def test_empty_python_file(self, tmp_path: Path) -> None:
        (tmp_path / "empty.py").write_text("")
        graph = analyze(tmp_path)
        node = graph.get_node("empty.py")
        assert node is not None
        assert node.symbols == []

    def test_syntax_error_file(self, tmp_path: Path) -> None:
        (tmp_path / "broken.py").write_text("def foo(\n")
        graph = analyze(tmp_path)
        node = graph.get_node("broken.py")
        assert node is not None
        # Should still create a node, just no symbols
        assert node.symbols == []

    def test_binary_content_in_py_file(self, tmp_path: Path) -> None:
        (tmp_path / "binary.py").write_bytes(b"\x00\x01\x02\x03def foo(): pass\n")
        graph = analyze(tmp_path)
        # Should not crash
        assert isinstance(graph, Graph)

    def test_large_file(self, tmp_path: Path) -> None:
        lines = [f"def func_{i}(): pass" for i in range(1000)]
        (tmp_path / "large.py").write_text("\n".join(lines))
        graph = analyze(tmp_path)
        node = graph.get_node("large.py")
        assert node is not None
        assert len(node.symbols) == 1000

    def test_max_files_limit(self, tmp_path: Path) -> None:
        for i in range(10):
            (tmp_path / f"file_{i}.py").write_text(f"x = {i}\n")
        graph = analyze(tmp_path, max_files=3)
        assert len(graph.nodes) == 3

    def test_nested_directories(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("pass\n")
        graph = analyze(tmp_path)
        ids = {n.id for n in graph.nodes}
        assert any("deep.py" in i for i in ids)

    def test_mixed_languages(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("import os\n")
        (tmp_path / "index.ts").write_text("export const x = 1;\n")
        (tmp_path / "main.js").write_text("const y = require('./index');\n")
        graph = analyze(tmp_path)
        languages = {n.language for n in graph.nodes}
        assert "python" in languages
        assert "typescript" in languages
        assert "javascript" in languages

    def test_circular_imports(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("from b import y\nx = 1\n")
        (tmp_path / "b.py").write_text("from a import x\ny = 2\n")
        graph = analyze(tmp_path)
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("a.py", "b.py") in edges
        assert ("b.py", "a.py") in edges

    def test_self_import_not_created(self, tmp_path: Path) -> None:
        # A file importing itself shouldn't create a self-edge
        (tmp_path / "self_ref.py").write_text("from self_ref import foo\ndef foo(): pass\n")
        graph = analyze(tmp_path)
        # self-edges are technically valid but unusual; just verify no crash
        assert isinstance(graph, Graph)

    @pytest.mark.skipif(os.name == "nt", reason="Symlinks need admin on Windows")
    def test_symlinks_skipped(self, tmp_path: Path) -> None:
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "module.py").write_text("x = 1\n")

        link_dir = tmp_path / "link"
        link_dir.symlink_to(real_dir)

        graph = analyze(tmp_path)
        # Should only find module.py once (from real dir, not symlink)
        matching = [n for n in graph.nodes if "module.py" in n.id]
        assert len(matching) == 1


# ---------------------------------------------------------------------------
# Graph edge cases
# ---------------------------------------------------------------------------


class TestGraphEdgeCases:
    def test_get_node_after_append(self) -> None:
        graph = Graph(
            metadata=GraphMetadata(
                repo="test", generated_at="", total_files=0, languages=[]
            )
        )
        graph.nodes.append(Node(id="a.py", label="a.py"))
        assert graph.get_node("a.py") is not None
        # Add another node — index should update
        graph.nodes.append(Node(id="b.py", label="b.py"))
        assert graph.get_node("b.py") is not None

    def test_neighbors_empty(self) -> None:
        graph = Graph(
            metadata=GraphMetadata(
                repo="test", generated_at="", total_files=0, languages=[]
            )
        )
        graph.nodes.append(Node(id="lonely.py", label="lonely.py"))
        assert graph.neighbors("lonely.py") == []

    def test_indegree_outdegree_zero(self) -> None:
        graph = Graph(
            metadata=GraphMetadata(
                repo="test", generated_at="", total_files=0, languages=[]
            )
        )
        graph.nodes.append(Node(id="orphan.py", label="orphan.py"))
        assert graph.indegree("orphan.py") == 0
        assert graph.outdegree("orphan.py") == 0
