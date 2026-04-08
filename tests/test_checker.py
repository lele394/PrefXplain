"""Tests for the CI rule checker."""

from __future__ import annotations

from pathlib import Path

from prefxplain.checker import Rule, Violation, check, format_violations, load_rules
from prefxplain.graph import Edge, Graph, GraphMetadata, Node


def _make_graph(edges: list[tuple[str, str]]) -> Graph:
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


class TestNoCircularDeps:
    def test_detects_cycle(self) -> None:
        graph = _make_graph([("a.py", "b.py"), ("b.py", "a.py")])
        rule = Rule(name="no-circular-deps", kind="no-circular-deps")
        violations = check(graph, [rule])
        assert len(violations) == 1
        assert "Circular" in violations[0].message

    def test_no_cycle_clean(self) -> None:
        graph = _make_graph([("a.py", "b.py"), ("b.py", "c.py")])
        rule = Rule(name="no-circular-deps", kind="no-circular-deps")
        violations = check(graph, [rule])
        assert violations == []

    def test_cycle_with_from_pattern(self) -> None:
        graph = _make_graph([("src/a.py", "src/b.py"), ("src/b.py", "src/a.py")])
        rule = Rule(name="no-circular-deps", kind="no-circular-deps", from_pattern="src/*")
        violations = check(graph, [rule])
        assert len(violations) == 1


class TestNoCrossBoundary:
    def test_detects_boundary_violation(self) -> None:
        graph = _make_graph([("api/handler.py", "internal/secrets.py")])
        rule = Rule(
            name="no-cross-boundary",
            kind="no-cross-boundary",
            from_pattern="api/*",
            to_pattern="internal/*",
        )
        violations = check(graph, [rule])
        assert len(violations) == 1
        assert "crosses boundary" in violations[0].message

    def test_allowed_import_no_violation(self) -> None:
        graph = _make_graph([("api/handler.py", "api/utils.py")])
        rule = Rule(
            name="no-cross-boundary",
            kind="no-cross-boundary",
            from_pattern="api/*",
            to_pattern="internal/*",
        )
        violations = check(graph, [rule])
        assert violations == []

    def test_missing_patterns_no_violation(self) -> None:
        graph = _make_graph([("a.py", "b.py")])
        rule = Rule(name="no-cross-boundary", kind="no-cross-boundary")
        violations = check(graph, [rule])
        assert violations == []


class TestMaxImports:
    def test_exceeds_max(self) -> None:
        edges = [("hub.py", f"dep{i}.py") for i in range(15)]
        graph = _make_graph(edges)
        rule = Rule(name="max-imports", kind="max-imports", max_value=10)
        violations = check(graph, [rule])
        assert len(violations) == 1
        assert "15" in violations[0].message

    def test_within_max(self) -> None:
        edges = [("hub.py", f"dep{i}.py") for i in range(3)]
        graph = _make_graph(edges)
        rule = Rule(name="max-imports", kind="max-imports", max_value=10)
        violations = check(graph, [rule])
        assert violations == []


class TestLoadRules:
    def test_load_simple_yaml(self, tmp_path: Path) -> None:
        config = tmp_path / ".prefxplain.yml"
        config.write_text(
            "rules:\n"
            "  - name: no-circular-deps\n"
            "  - name: max-imports\n"
            "    max: 8\n"
        )
        rules = load_rules(config)
        assert len(rules) == 2
        assert rules[0].name == "no-circular-deps"
        assert rules[1].max_value == 8


class TestFormatViolations:
    def test_no_violations(self) -> None:
        assert format_violations([]) == "No violations found."

    def test_formats_errors(self) -> None:
        v = Violation(rule="test", message="bad thing", files=["a.py"], severity="error")
        output = format_violations([v])
        assert "1 error" in output
        assert "bad thing" in output
