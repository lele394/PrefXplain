"""Tests for the semantic diagram layer."""

from __future__ import annotations

from prefxplain.describer import _validate_flowchart
from prefxplain.diagram import (
    build_semantic_diagram,
    infer_group_kind,
    infer_node_kind,
)
from prefxplain.exporter import export_mermaid
from prefxplain.graph import Edge, Graph, GraphMetadata, Node


def _semantic_graph() -> Graph:
    graph = Graph(
        nodes=[
            Node(
                id="api.py",
                label="api.py",
                description="Handles incoming API requests.",
                short_title="API Handler",
                role="api_route",
                group="API Layer",
                language="python",
            ),
            Node(
                id="schemas.py",
                label="schemas.py",
                description="Defines request and response schemas.",
                short_title="Schema Types",
                role="data_model",
                group="Data Models",
                language="python",
            ),
            Node(
                id="tests/test_api.py",
                label="test_api.py",
                description="Verifies the API behavior end to end.",
                short_title="API Tests",
                role="test",
                group="Tests",
                language="python",
            ),
        ],
        edges=[
            Edge(source="api.py", target="schemas.py"),
            Edge(source="tests/test_api.py", target="api.py"),
        ],
        metadata=GraphMetadata(
            repo="semantic-test",
            generated_at="2026-01-01T00:00:00Z",
            total_files=3,
            languages=["python"],
            groups={
                "API Layer": "Handles incoming application requests.",
                "Data Models": "Defines shared schemas and data shapes.",
                "Tests": "Verifies user-facing behavior.",
            },
        ),
    )
    return graph


def _ungrouped_tool_graph() -> Graph:
    return Graph(
        nodes=[
            Node(id="pkg/cli.py", label="cli.py", description="Exposes the command-line entry points and orchestrates the pipeline.", role="entry_point", language="python"),
            Node(id="pkg/mcp_server.py", label="mcp_server.py", description="Serves MCP stdio tools so external agents can query the graph.", language="python"),
            Node(id="pkg/analyzer.py", label="analyzer.py", description="Scans source files, parses imports, and builds the dependency graph.", language="python"),
            Node(id="pkg/checker.py", label="checker.py", description="Checks dependency rules and validates architectural constraints.", language="python"),
            Node(id="pkg/describer.py", label="describer.py", description="Generates natural-language descriptions and flowcharts with an LLM-backed cache.", language="python"),
            Node(id="pkg/graph.py", label="graph.py", description="Defines Node, Edge, and Graph with PageRank, cycles, and clustering.", role="data_model", language="python"),
            Node(id="pkg/renderer.py", label="renderer.py", description="Renders the interactive HTML diagram with canvas layout and overlays.", language="python"),
            Node(id="pkg/diagram.py", label="diagram.py", description="Builds the semantic diagram model consumed by the renderer.", language="python"),
            Node(id="pkg/exporter.py", label="exporter.py", description="Exports Mermaid and DOT views from the graph.", language="python"),
            Node(id="tests/test_renderer.py", label="test_renderer.py", description="Verifies rendering behavior.", role="test", language="python"),
        ],
        edges=[
            Edge(source="pkg/cli.py", target="pkg/analyzer.py"),
            Edge(source="pkg/cli.py", target="pkg/describer.py"),
            Edge(source="pkg/cli.py", target="pkg/renderer.py"),
            Edge(source="pkg/mcp_server.py", target="pkg/graph.py"),
            Edge(source="pkg/mcp_server.py", target="pkg/exporter.py"),
            Edge(source="pkg/analyzer.py", target="pkg/graph.py"),
            Edge(source="pkg/checker.py", target="pkg/graph.py"),
            Edge(source="pkg/describer.py", target="pkg/graph.py"),
            Edge(source="pkg/diagram.py", target="pkg/graph.py"),
            Edge(source="pkg/renderer.py", target="pkg/graph.py"),
            Edge(source="pkg/exporter.py", target="pkg/diagram.py"),
            Edge(source="pkg/exporter.py", target="pkg/graph.py"),
            Edge(source="tests/test_renderer.py", target="pkg/renderer.py"),
        ],
        metadata=GraphMetadata(
            repo="ungrouped-tool",
            generated_at="2026-01-01T00:00:00Z",
            total_files=10,
            languages=["python"],
        ),
    )


def test_to_render_dict_includes_semantic_diagram() -> None:
    graph = _semantic_graph()
    payload = graph.to_render_dict()

    assert "semantic_diagram" in payload
    assert "node_semantics" in payload

    semantic_nodes = payload["semantic_diagram"]["nodes"]
    labels = {node["label"] for node in semantic_nodes}
    assert "API Layer" in labels
    assert "Data Models" in labels
    assert "Tests" in labels

    node_semantics = payload["node_semantics"]
    assert node_semantics["schemas.py"]["kind"] == "data"
    assert node_semantics["tests/test_api.py"]["kind"] == "test"


def test_semantic_diagram_assigns_shapes_and_edge_labels() -> None:
    diagram = build_semantic_diagram(_semantic_graph()).to_dict()
    nodes_by_label = {node["label"]: node for node in diagram["nodes"]}
    edges_by_label = {edge["label"]: edge for edge in diagram["edges"]}

    assert nodes_by_label["Data Models"]["shape"] == "data"
    assert nodes_by_label["Tests"]["shape"] == "test"
    assert "reads" in edges_by_label
    assert "tests" in edges_by_label


def test_export_mermaid_prefers_semantic_diagram() -> None:
    mermaid = export_mermaid(_semantic_graph())
    assert "API Layer" in mermaid
    assert "Data Models" in mermaid
    assert "|reads|" in mermaid
    assert "|tests|" in mermaid
    assert "api.py" not in mermaid


def test_validate_flowchart_accepts_extended_shapes() -> None:
    flowchart = _validate_flowchart(
        {
            "nodes": [
                {"id": "1", "label": "Start request", "type": "entry", "shape": "entry", "description": "Begins the request."},
                {"id": "2", "label": "Analyze payload", "type": "analysis", "shape": "analysis", "description": "Inspects the payload."},
                {"id": "3", "label": "Persist data", "type": "data", "shape": "data", "description": "Stores the result."},
            ],
            "edges": [
                {"from": "1", "to": "2", "label": "received"},
                {"from": "2", "to": "3", "label": "valid"},
            ],
        }
    )

    assert flowchart is not None
    assert flowchart["nodes"][1]["shape"] == "analysis"
    assert flowchart["nodes"][2]["type"] == "data"
    assert flowchart["nodes"][0]["description"] == "Begins the request."


def test_infer_node_kind_prefers_role_over_keyword_search() -> None:
    # A utility file whose description contains the keyword "persist" would
    # previously be reclassified as a data node by the keyword fallback.
    # Role-priority keeps it an analysis node, which is what its role says.
    utility_node = Node(
        id="cache.py",
        label="cache.py",
        role="utility",
        short_title="Cache helpers",
        description="Utilities to persist intermediate results between runs.",
    )
    assert infer_node_kind(utility_node) == "analysis"

    api_node = Node(
        id="routes.py",
        label="routes.py",
        role="api_route",
        short_title="User routes",
        description="Validates user input and dispatches handlers.",
    )
    # "validates" would previously force kind=decision. Role wins.
    assert infer_node_kind(api_node) == "process"


def test_infer_group_kind_uses_role_majority() -> None:
    data_children = [
        Node(id=f"m{i}.py", label=f"m{i}.py", role="data_model", short_title="Schema", description="Schema.")
        for i in range(3)
    ]
    # Mixed role — one utility snuck in, but data_model is still >= 60%.
    data_children.append(
        Node(id="helpers.py", label="helpers.py", role="utility", short_title="Helpers", description="Misc.")
    )
    assert infer_group_kind(data_children, role="data_model") == "data"


def test_infer_group_kind_decision_from_label_hints() -> None:
    children = [
        Node(
            id="policy.py",
            label="policy.py",
            role="utility",
            short_title="Access policy",
            description="Decides which users can access which resources.",
        ),
        Node(
            id="router.py",
            label="router.py",
            role="utility",
            short_title="Request router",
            description="Routes incoming requests to the right handler.",
        ),
    ]
    # "policy" and "router" hints should lift the group to decision even
    # though neither file has a data_model role.
    assert infer_group_kind(children, role="utility") == "decision"


def test_infer_group_kind_ignores_description_false_positives() -> None:
    # A generic utility group whose description happens to mention "rule"
    # once must NOT be reclassified as a decision. Only short_title tokens
    # count as a decision hint.
    children = [
        Node(
            id="analyzer.py",
            label="analyzer.py",
            role="utility",
            short_title="AST walker",
            description="Walks the AST and collects imports and symbols.",
        ),
        Node(
            id="checker.py",
            label="checker.py",
            role="utility",
            short_title="Graph checker",
            description="Loads dependency rules from .prefxplain.yml and checks the graph.",
        ),
    ]
    assert infer_group_kind(children, role="utility") == "analysis"


def test_data_models_group_resolves_to_data_shape() -> None:
    graph = Graph(
        nodes=[
            Node(
                id="cli.py",
                label="cli.py",
                role="entry_point",
                short_title="CLI",
                description="Runs the pipeline end to end.",
                group="Pipeline",
                language="python",
            ),
            Node(
                id="user.py",
                label="user.py",
                role="data_model",
                short_title="User",
                description="User record.",
                group="Data Models",
                language="python",
            ),
            Node(
                id="order.py",
                label="order.py",
                role="data_model",
                short_title="Order",
                description="Order record.",
                group="Data Models",
                language="python",
            ),
            Node(
                id="invoice.py",
                label="invoice.py",
                role="data_model",
                short_title="Invoice",
                description="Invoice record.",
                group="Data Models",
                language="python",
            ),
        ],
        edges=[
            Edge(source="cli.py", target="user.py"),
            Edge(source="cli.py", target="order.py"),
        ],
        metadata=GraphMetadata(
            repo="data-test",
            generated_at="2026-01-01T00:00:00Z",
            total_files=4,
            languages=["python"],
            groups={
                "Pipeline": "End-to-end pipeline entry.",
                "Data Models": "Shared persistence types.",
            },
        ),
    )
    diagram = build_semantic_diagram(graph).to_dict()
    by_label = {node["label"]: node for node in diagram["nodes"]}
    assert by_label["Data Models"]["shape"] == "data"
    assert by_label["Data Models"]["kind"] == "data"


def test_semantic_diagram_infers_functional_groups_without_ai_groups() -> None:
    payload = _ungrouped_tool_graph().to_render_dict()
    labels = {node["label"] for node in payload["semantic_diagram"]["nodes"]}

    assert "CLI & Integrations" in labels
    assert "Code Analysis" in labels
    assert "Graph Data Model" in labels
    assert "Interactive Diagram" in labels
    assert "Tests" in labels
