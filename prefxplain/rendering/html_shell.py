"""Build the self-contained HTML shell for the ELK renderer.

Phase 1: minimal scaffold that loads elkjs + a sanity-check JS module. Graph
data is embedded as JSON on `window.__PREFXPLAIN_GRAPH__` so later phases can
consume it without reparsing the DOM.
"""

from __future__ import annotations

import json
from typing import Any

from ..graph import Graph
from .assets import app_modules, vendor_elk, vendor_elk_worker


_APP_MODULES = [
    "tokens.js",
    "graph-utils.js",
    "ir.js",
    "layout.js",
    "post.js",
    "components/edge.js",
    "components/card-hero.js",
    "components/card-file.js",
    "components/group-container.js",
    "components/group-detail-chrome.js",
    "views/group-map.js",
    "views/nested.js",
    "ui/view-switcher.js",
    "ui/top-panel.js",
    "ui/sidebar.js",
    "ui/flow-modal.js",
    "ui/code-editor.js",
    "ui/legend.js",
    "ui/minimap.js",
    "main.js",
]


def build_html(graph: Graph) -> str:
    """Return the full HTML document as a string."""
    repo = graph.metadata.repo if graph.metadata else "repo"
    payload = _serialize_graph(graph)
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    elk_js = vendor_elk()
    elk_worker_js = vendor_elk_worker()
    app_js = app_modules(_APP_MODULES)

    return _TEMPLATE.format(
        repo=_escape_attr(repo),
        payload_json=payload_json,
        elk_js=elk_js,
        elk_worker_js=elk_worker_js,
        app_js=app_js,
    )


def _serialize_graph(graph: Graph) -> dict[str, Any]:
    """Serialize the graph into a JSON-friendly dict consumed by the JS side."""
    meta = graph.metadata
    group_descs: dict[str, str] = (
        dict(getattr(meta, "groups", {}) or {}) if meta else {}
    )
    group_highlights: dict[str, list[str]] = (
        dict(getattr(meta, "group_highlights", {}) or {}) if meta else {}
    )
    # Merge into the shape the JS renderer expects: { name: { desc, highlights } }.
    meta_groups: dict[str, dict[str, Any]] = {}
    for name in set(group_descs) | set(group_highlights):
        meta_groups[name] = {
            "desc": group_descs.get(name, ""),
            "highlights": list(group_highlights.get(name, []) or []),
        }
    return {
        "repo": meta.repo if meta else "repo",
        "version": getattr(meta, "version", None) if meta else None,
        "total_files": meta.total_files if meta else len(graph.nodes),
        "languages": list(getattr(meta, "languages", []) or []) if meta else [],
        "summary": getattr(meta, "summary", "") if meta else "",
        "health_score": getattr(meta, "health_score", None) if meta else None,
        "health_notes": getattr(meta, "health_notes", "") if meta else "",
        "metaGroups": meta_groups,
        "nodes": [
            {
                "id": n.id,
                "label": n.label,
                "short": getattr(n, "short_title", None) or n.label,
                "description": n.description or "",
                "role": getattr(n, "role", None) or "undefined",
                "group": getattr(n, "group", None) or "",
                "language": getattr(n, "language", None) or "",
                "size": getattr(n, "size", 0) or 0,
                "highlights": list(getattr(n, "highlights", []) or []),
            }
            for n in graph.nodes
        ],
        "edges": [
            {
                "source": e.source,
                "target": e.target,
                "type": getattr(e, "type", None) or "import",
            }
            for e in graph.edges
        ],
    }


def _escape_attr(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PrefXplain \u2014 {repo}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; background: #0d1117; color: #c9d1d9;
    font-family: 'Inter', system-ui, sans-serif; overflow: hidden; }}
  * {{ box-sizing: border-box; }}

  /* Always-visible scrollbar for the left file explorer list.
     -webkit-appearance:none + explicit track/thumb backgrounds defeat macOS
     overlay scrollbars that auto-hide when idle. Scoped by class so other
     scrollable surfaces keep platform defaults. */
  .px-explorer-list {{ scrollbar-width: thin; scrollbar-color: #484f58 #0d1117; }}
  .px-explorer-list::-webkit-scrollbar {{
    width: 10px;
    -webkit-appearance: none;
    background: #0d1117;
  }}
  .px-explorer-list::-webkit-scrollbar-track {{
    background: #0d1117;
    border-left: 1px solid #21262d;
  }}
  .px-explorer-list::-webkit-scrollbar-thumb {{
    background: #484f58;
    border-radius: 5px;
    border: 2px solid #0d1117;
    min-height: 30px;
  }}
  .px-explorer-list::-webkit-scrollbar-thumb:hover {{ background: #6e7681; }}

  /* Main canvas: same always-visible scrollbar treatment so users can see
     when there's more diagram off-screen (focused groups can be much wider
     than the viewport). */
  #px-canvas {{ scrollbar-width: thin; scrollbar-color: #484f58 #0d1117; }}
  #px-canvas::-webkit-scrollbar {{
    width: 10px;
    height: 10px;
    -webkit-appearance: none;
    background: #0d1117;
  }}
  #px-canvas::-webkit-scrollbar-track {{
    background: #0d1117;
  }}
  #px-canvas::-webkit-scrollbar-thumb {{
    background: #484f58;
    border-radius: 5px;
    border: 2px solid #0d1117;
    min-height: 30px;
    min-width: 30px;
  }}
  #px-canvas::-webkit-scrollbar-thumb:hover {{ background: #6e7681; }}
  #px-canvas::-webkit-scrollbar-corner {{ background: #0d1117; }}

  /* Code editor: inherits the VS Code theme inside the webview (font, colors,
     selection). Falls back to sensible dark defaults when loaded as plain HTML
     so it still looks reasonable outside a VS Code webview. */
  .px-editor-surface {{
    background: var(--vscode-editor-background, #1e1e1e);
    color: var(--vscode-editor-foreground, #d4d4d4);
    font-family: var(--vscode-editor-font-family, 'JetBrains Mono', 'SFMono-Regular', Menlo, monospace);
    font-size: var(--vscode-editor-font-size, 13px);
    line-height: 1.55;
  }}
  .px-editor-textarea::selection {{
    background: var(--vscode-editor-selectionBackground, rgba(88,166,255,0.30));
    color: transparent;
  }}

  /* Token colors keyed to the theme kind that VS Code sets on <body>. */
  .px-t-keyword {{ color: #c586c0; }}
  .px-t-string {{ color: #ce9178; }}
  .px-t-number {{ color: #b5cea8; }}
  .px-t-comment {{ color: #6a9955; font-style: italic; }}
  .px-t-function {{ color: #dcdcaa; }}
  .px-t-type {{ color: #4ec9b0; }}
  .px-t-operator {{ color: #d4d4d4; }}
  .px-t-builtin {{ color: #4fc1ff; }}
  .px-t-decorator {{ color: #dcdcaa; }}

  body[data-vscode-theme-kind="vscode-light"] .px-t-keyword {{ color: #af00db; }}
  body[data-vscode-theme-kind="vscode-light"] .px-t-string {{ color: #a31515; }}
  body[data-vscode-theme-kind="vscode-light"] .px-t-number {{ color: #098658; }}
  body[data-vscode-theme-kind="vscode-light"] .px-t-comment {{ color: #008000; }}
  body[data-vscode-theme-kind="vscode-light"] .px-t-function {{ color: #795e26; }}
  body[data-vscode-theme-kind="vscode-light"] .px-t-type {{ color: #267f99; }}
  body[data-vscode-theme-kind="vscode-light"] .px-t-operator {{ color: #000000; }}
  body[data-vscode-theme-kind="vscode-light"] .px-t-builtin {{ color: #0070c1; }}
  body[data-vscode-theme-kind="vscode-light"] .px-t-decorator {{ color: #795e26; }}

  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-keyword {{ color: #569cd6; }}
  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-string {{ color: #ce9178; }}
  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-number {{ color: #b5cea8; }}
  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-comment {{ color: #7ca668; }}
  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-function {{ color: #dcdcaa; }}
  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-type {{ color: #4ec9b0; }}
</style>
</head>
<body>
<div id="root"></div>

<script id="prefxplain-graph" type="application/json">{payload_json}</script>
<script>
  try {{
    window.__PREFXPLAIN_GRAPH__ = JSON.parse(document.getElementById('prefxplain-graph').textContent);
  }} catch (e) {{
    console.error('[prefxplain] failed to parse embedded graph JSON', e);
    window.__PREFXPLAIN_GRAPH__ = null;
  }}
</script>

<script>
{elk_js}
</script>

<!-- Inline worker source: turned into a Blob URL at runtime by layout.js
     when nodeCount > WORKER_THRESHOLD, so layout never blocks the UI. -->
<script id="elk-worker-source" type="text/plain">
{elk_worker_js}
</script>

<script>
{app_js}
</script>
</body>
</html>
"""
