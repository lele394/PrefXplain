"""Export graphs to Mermaid and Graphviz DOT formats.

Mermaid renders natively in GitHub READMEs and PR descriptions.
DOT can be rendered by Graphviz or online tools.
"""

from __future__ import annotations

import re

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


def export_mermaid(graph: Graph) -> str:
    """Export graph as a Mermaid flowchart string.

    Example output:
        ```mermaid
        graph LR
            main_py["main.py"] --> utils_py["utils.py"]
        ```
    """
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
