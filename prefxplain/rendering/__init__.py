"""ELK-based renderer for PrefXplain.

Replaces the legacy Canvas force-directed layout with an SVG renderer driven
by ELK.js (layered + orthogonal routing), matching the Claude Design redesign.

Public entry point:
    render_elk(graph, output_path=None) -> str

Called by prefxplain.renderer.render() when renderer='elk' is selected.
"""

from __future__ import annotations

from pathlib import Path

from ..graph import Graph
from .html_shell import build_html


def render_elk(graph: Graph, output_path: Path | None = None) -> str:
    """Render a Graph as a self-contained interactive HTML string.

    Args:
        graph: The graph to render.
        output_path: If provided, write the HTML to this path.

    Returns:
        The HTML string.
    """
    html = build_html(graph)
    if output_path is not None:
        output_path.write_text(html, encoding="utf-8")
    return html


__all__ = ["render_elk"]
