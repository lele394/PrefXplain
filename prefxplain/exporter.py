"""Export graphs to Mermaid and Graphviz DOT formats.

Mermaid renders natively in GitHub READMEs and PR descriptions.
DOT can be rendered by Graphviz or online tools.
"""

from __future__ import annotations

import re

from .diagram import build_semantic_diagram
from .graph import Graph


def _sanitize_mermaid_id(node_id: str, seen: dict[str, int]) -> str:
    """Convert a file path to a unique valid Mermaid node identifier."""
    base = re.sub(r"[^a-zA-Z0-9_]", "_", node_id)
    count = seen.get(base, 0)
    seen[base] = count + 1
    return base if count == 0 else f"{base}_{count}"


def _escape_mermaid_label(label: str) -> str:
    """Escape a label for use inside Mermaid quoted strings."""
    return label.replace("\\", "\\\\").replace('"', "&quot;")


def _escape_dot_str(s: str) -> str:
    """Escape a string for use inside DOT quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _semantic_mermaid_decl(node: dict) -> str:
    label = _escape_mermaid_label(node["label"])
    shape = node.get("shape", "process")
    node_id = node["id"]
    if shape == "decision":
        return f'    {node_id}{{"{label}"}}'
    if shape == "data":
        return f'    {node_id}[/"{label}"/]'
    if shape == "analysis":
        return f'    {node_id}[["{label}"]]'
    if shape in {"entry", "test"}:
        return f'    {node_id}(["{label}"])'
    return f'    {node_id}["{label}"]'


def _semantic_dot_shape(shape: str) -> str:
    return {
        "decision": "diamond",
        "analysis": "hexagon",
        "data": "parallelogram",
        "entry": "oval",
        "test": "box",
        "external": "box",
    }.get(shape, "box")


def export_mermaid(graph: Graph) -> str:
    """Export graph as a Mermaid flowchart string.

    Example output:
        ```mermaid
        graph LR
            main_py["main.py"] --> utils_py["utils.py"]
        ```
    """
    semantic = build_semantic_diagram(graph).to_dict()
    if len(semantic.get("nodes", [])) >= 2:
        lines = ["graph LR"]
        seen: dict[str, int] = {}
        id_map = {
            node["id"]: _sanitize_mermaid_id(node["id"], seen)
            for node in semantic["nodes"]
        }
        for node in semantic["nodes"]:
            node = {**node, "id": id_map[node["id"]]}
            lines.append(_semantic_mermaid_decl(node))
        lines.append("")
        for edge in semantic["edges"]:
            edge_label = f'|{_escape_mermaid_label(edge.get("label", ""))}|' if edge.get("label") else ""
            lines.append(f'    {id_map[edge["source"]]} -->{edge_label} {id_map[edge["target"]]}')
        return "\n".join(lines) + "\n"

    lines = ["graph LR"]

    cycle_nodes = graph.cycle_node_ids()
    cycle_edge_set = graph.cycle_edges()

    # Build unique IDs, tracking collisions
    seen: dict[str, int] = {}
    id_map: dict[str, str] = {}
    for node in graph.nodes:
        id_map[node.id] = _sanitize_mermaid_id(node.id, seen)

    # Declare nodes with labels
    for node in graph.nodes:
        mid = id_map[node.id]
        label = _escape_mermaid_label(node.label)
        if node.id in cycle_nodes:
            lines.append(f'    {mid}["{label}"]:::cycle')
        else:
            lines.append(f'    {mid}["{label}"]')

    lines.append("")

    # Edges
    for edge in graph.edges:
        src = id_map.get(edge.source, _sanitize_mermaid_id(edge.source, seen))
        tgt = id_map.get(edge.target, _sanitize_mermaid_id(edge.target, seen))
        if (edge.source, edge.target) in cycle_edge_set:
            lines.append(f"    {src} -.->|cycle| {tgt}")
        else:
            lines.append(f"    {src} --> {tgt}")

    # Style classes
    lines.append("")
    lines.append("    classDef cycle fill:#f44,stroke:#c00,color:#fff")

    return "\n".join(lines) + "\n"


def export_dot(graph: Graph) -> str:
    """Export graph as a Graphviz DOT string."""
    semantic = build_semantic_diagram(graph).to_dict()
    if len(semantic.get("nodes", [])) >= 2:
        lines = ["digraph PrefXplain {"]
        lines.append('    rankdir=LR;')
        lines.append('    node [style="rounded,filled", fontname="Helvetica", fontsize=10];')
        lines.append('    edge [color="#666666", arrowsize=0.7, fontname="Helvetica", fontsize=9];')
        lines.append("")
        for node in semantic["nodes"]:
            safe_id = f'"{_escape_dot_str(node["id"])}"'
            safe_label = _escape_dot_str(node["label"])
            shape = _semantic_dot_shape(node.get("shape", "process"))
            lines.append(
                f'    {safe_id} [label="{safe_label}", shape="{shape}", fillcolor="#161b2240", color="#58a6ff"];'
            )
        lines.append("")
        for edge in semantic["edges"]:
            src = f'"{_escape_dot_str(edge["source"])}"'
            tgt = f'"{_escape_dot_str(edge["target"])}"'
            label = _escape_dot_str(edge.get("label", ""))
            label_part = f' [label="{label}"]' if label else ""
            lines.append(f"    {src} -> {tgt}{label_part};")
        lines.append("}")
        return "\n".join(lines) + "\n"

    lines = ["digraph PrefXplain {"]
    lines.append('    rankdir=LR;')
    lines.append('    node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];')
    lines.append('    edge [color="#666666", arrowsize=0.7];')
    lines.append("")

    cycle_nodes = graph.cycle_node_ids()
    cycle_edge_set = graph.cycle_edges()

    lang_colors = {
        "python": "#4B8BBE",
        "typescript": "#3178C6",
        "javascript": "#F7DF1E",
        "other": "#888888",
    }

    # Cluster by directory
    clusters = graph.cluster_by_directory()
    cluster_idx = 0
    for directory, node_ids in sorted(clusters.items()):
        lines.append(f"    subgraph cluster_{cluster_idx} {{")
        lines.append(f'        label="{_escape_dot_str(directory)}";')
        lines.append('        style=dashed;')
        lines.append('        color="#666666";')
        for nid in node_ids:
            node = graph.get_node(nid)
            if not node:
                continue
            safe_id = f'"{_escape_dot_str(nid)}"'
            safe_label = _escape_dot_str(node.label)
            color = lang_colors.get(node.language, "#888888")
            if nid in cycle_nodes:
                lines.append(
                    f'        {safe_id} [label="{safe_label}", fillcolor="#ff4444", fontcolor="white"];'
                )
            else:
                lines.append(
                    f'        {safe_id} [label="{safe_label}", fillcolor="{color}40", color="{color}"];'
                )
        lines.append("    }")
        cluster_idx += 1

    lines.append("")

    # Edges
    for edge in graph.edges:
        src = f'"{_escape_dot_str(edge.source)}"'
        tgt = f'"{_escape_dot_str(edge.target)}"'
        if (edge.source, edge.target) in cycle_edge_set:
            lines.append(f'    {src} -> {tgt} [color="red", style=bold, penwidth=2];')
        else:
            lines.append(f"    {src} -> {tgt};")

    lines.append("}")
    return "\n".join(lines) + "\n"


def export_agent_context(
    graph: Graph,
    query: str,
    depth: int = 2,
    token_budget: int = 2000,
) -> str:
    """Token-efficient context dump for AI agents.

    BFS around files matching query, serialized as plain text within a token budget.
    Inspired by graphify's serve.py subgraph_to_text pattern (MIT license).
    """
    q = query.lower()
    seeds = [
        n.id for n in graph.nodes
        if q in n.id.lower() or q in n.label.lower() or q in n.description.lower()
    ]
    if not seeds:
        return f"# No files matching '{query}'\n"

    # Merge subgraphs from each seed (cap at 5 to avoid context explosion)
    visited_ids: set[str] = set()
    edge_pairs: set[tuple[str, str]] = set()
    node_map = {n.id: n for n in graph.nodes}

    for seed in seeds[:5]:
        sub = graph.depth_subgraph(seed, depth)  # reuses existing BFS impl
        for n in sub.nodes:
            visited_ids.add(n.id)
        for e in sub.edges:
            edge_pairs.add((e.source, e.target))

    # Sort by indegree desc — most-imported files first (highest signal)
    sorted_ids = sorted(visited_ids, key=lambda nid: graph.indegree(nid), reverse=True)

    char_budget = token_budget * 4  # ~4 chars/token approximation
    lines: list[str] = [f"# Context: '{query}' — {len(visited_ids)} files, depth {depth}\n"]

    for nid in sorted_ids:
        n = node_map.get(nid)
        if not n:
            continue
        role_tag = f" role={n.role}" if n.role else ""
        lines.append(f"FILE {n.id} [{n.language}{role_tag}]")
        if n.description:
            lines.append(f"  > {n.description}")
        if n.symbols:
            syms = ", ".join(f"{s.name}({s.kind[0]})" for s in n.symbols[:10])
            lines.append(f"  exports: {syms}")

    if edge_pairs:
        lines.append("")
        for src, tgt in sorted(edge_pairs):
            lines.append(f"IMPORT {src} -> {tgt}")

    output = "\n".join(lines)
    if len(output) > char_budget:
        output = output[:char_budget] + f"\n... [truncated — budget ~{token_budget} tokens]\n"
    return output
