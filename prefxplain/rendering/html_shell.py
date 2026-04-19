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
    # Escape `<`, `>`, `&` so HTML-tokenizer regexes (including those run by
    # the VS Code webview's injectBaseTag/injectVsCodeBridge) can't match
    # tag-like substrings inside description strings and rewrite our JSON.
    # JSON.parse decodes \u003c/\u003e/\u0026 back to the original characters.
    payload_json = (
        payload_json
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

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
    group_summaries = dict(getattr(meta, "group_summaries", {}) or {}) if meta else {}
    # Merge into the shape the JS renderer expects: { name: { desc, highlights,
    # semantic_role, flow, extends_at, pattern } }. The enriched fields ride
    # alongside the legacy `desc`/`highlights` so older consumers keep working.
    meta_groups: dict[str, dict[str, Any]] = {}
    for name in set(group_descs) | set(group_highlights) | set(group_summaries):
        summary = group_summaries.get(name)
        # Prefer the LLM-authored description on the summary over whatever lives
        # in `groups` — `apply_inferred_groups` may run before `group_summaries`
        # is preserved on re-runs, leaving `groups[name]` stale with the static
        # PROFILE_BY_LABEL fallback even when a real synthesis exists.
        llm_desc = getattr(summary, "description", "") if summary is not None else ""
        entry: dict[str, Any] = {
            "desc": llm_desc or group_descs.get(name, ""),
            "highlights": list(group_highlights.get(name, []) or []),
        }
        if summary is not None:
            for field_name in ("semantic_role", "flow", "extends_at", "pattern"):
                value = getattr(summary, field_name, "")
                if value:
                    entry[field_name] = value
        meta_groups[name] = entry
    return {
        "repo": meta.repo if meta else "repo",
        "version": getattr(meta, "version", None) if meta else None,
        "total_files": meta.total_files if meta else len(graph.nodes),
        "languages": list(getattr(meta, "languages", []) or []) if meta else [],
        "summary": getattr(meta, "summary", "") if meta else "",
        "health_score": getattr(meta, "health_score", None) if meta else None,
        "health_notes": getattr(meta, "health_notes", "") if meta else "",
        "metaGroups": meta_groups,
        "nodes": [_serialize_node(n) for n in graph.nodes],
        "edges": [
            {
                "source": e.source,
                "target": e.target,
                "type": getattr(e, "type", None) or "import",
            }
            for e in graph.edges
        ],
    }


def _serialize_node(n: Any) -> dict[str, Any]:
    """Serialize one node, omitting empty semantic fields so the JS payload
    stays compact. The renderer treats missing keys the same as empty strings.
    """
    payload: dict[str, Any] = {
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
    for field_name in ("semantic_role", "flow", "extends_at", "pattern"):
        value = getattr(n, field_name, "") or ""
        if value:
            payload[field_name] = value
    return payload


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
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400;1,9..144,500&family=Geist:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  /* Anti-flash: a tiny inline bootstrap at the top of the body flips
     :root[data-theme="dark"] before CSS parses if localStorage says so.
     These rules then cascade through generated SVG / HTML that reads
     var(--px-*). tokens.js exposes the same palette to JS via PX.T. */
  :root {{
    --px-bg:            #faf8f2;
    --px-panel:         #f4f0e4;
    --px-panel-alt:     #efebdd;
    --px-border:        #e8e4d8;
    --px-border-alt:    #d9d3c1;
    --px-code-bg:       #f4f0e4;
    --px-code-gutter:   #faf8f2;
    --px-ink:           #111111;
    --px-ink2:          #2a2824;
    --px-ink-muted:     #5b5b52;
    --px-ink-faint:     #8b8578;
    --px-accent:        #1953d8;
    --px-accent2:       #3e71e8;
    --px-pill:          #e8eefc;
    --px-pill-border:   #c5d4f5;
    --px-danger:        #b8321f;
    --px-warn:          #b47f14;
    --px-good:          #2d7a3d;
    --px-scroll-track:  #f4f0e4;
    --px-scroll-thumb:  #b5b0a2;
    --px-scroll-thumb-hover: #8b8578;
    --px-overlay:       rgba(17,17,17,0.35);

    /* Semantic tints — alpha-blended fills for cards, pills, halos.
       Keep here so they track theme instead of being baked into view code. */
    --px-accent-tint:      rgba(25,83,216,0.10);
    --px-accent-tint-soft: rgba(25,83,216,0.06);
    --px-good-tint:        rgba(45,122,61,0.11);
    --px-warn-tint:        rgba(180,127,20,0.14);
    --px-warn-tint-soft:   rgba(180,127,20,0.07);
    --px-danger-tint:      rgba(184,50,31,0.10);
    --px-test-color:       #8957e5;
    --px-test-tint:        rgba(137,87,229,0.14);

    /* Shadows calibrated for warm paper — ink-tinted, not pure black. */
    --px-shadow-sm:        0 1px 2px rgba(17,17,17,0.06);
    --px-shadow-md:        0 4px 14px rgba(17,17,17,0.10);
    --px-shadow-lg:        0 24px 80px rgba(17,17,17,0.14);
  }}
  :root[data-theme="dark"] {{
    --px-bg:            #0e0d0a;
    --px-panel:         #17150f;
    --px-panel-alt:     #1c1a14;
    --px-border:        #2a2721;
    --px-border-alt:    #3a352c;
    --px-code-bg:       #17150f;
    --px-code-gutter:   #0e0d0a;
    --px-ink:           #f0ece2;
    --px-ink2:          #ddd8cc;
    --px-ink-muted:     #8b847a;
    --px-ink-faint:     #5e5a50;
    --px-accent:        #5a8fff;
    --px-accent2:       #7aa8ff;
    --px-pill:          #1a2744;
    --px-pill-border:   #2a3a5c;
    --px-danger:        #e05a3f;
    --px-warn:          #d4a845;
    --px-good:          #4caf5f;
    --px-scroll-track:  #17150f;
    --px-scroll-thumb:  #484f58;
    --px-scroll-thumb-hover: #6e7681;
    --px-overlay:       rgba(0,0,0,0.62);

    --px-accent-tint:      rgba(90,143,255,0.14);
    --px-accent-tint-soft: rgba(90,143,255,0.08);
    --px-good-tint:        rgba(76,175,95,0.16);
    --px-warn-tint:        rgba(212,168,69,0.16);
    --px-warn-tint-soft:   rgba(212,168,69,0.08);
    --px-danger-tint:      rgba(224,90,63,0.14);
    --px-test-color:       #a371f7;
    --px-test-tint:        rgba(163,113,247,0.20);

    --px-shadow-sm:        0 1px 2px rgba(0,0,0,0.4);
    --px-shadow-md:        0 4px 14px rgba(0,0,0,0.5);
    --px-shadow-lg:        0 24px 80px rgba(0,0,0,0.6);
  }}

  html, body {{ margin: 0; padding: 0; height: 100%;
    background: var(--px-bg); color: var(--px-ink2);
    font-family: 'Geist', -apple-system, BlinkMacSystemFont, 'Inter', system-ui, sans-serif; overflow: hidden;
    font-feature-settings: 'ss01', 'cv11';
    font-variant-numeric: tabular-nums;
    -webkit-font-smoothing: antialiased;
    color-scheme: light dark;
    transition: background 180ms ease, color 180ms ease; }}
  * {{ box-sizing: border-box; }}

  /* Always-visible scrollbar for the left file explorer list.
     Colors drive from theme-aware CSS vars so dark mode picks up the dark
     scrollbar track automatically. */
  .px-explorer-list {{ scrollbar-width: thin; scrollbar-color: var(--px-scroll-thumb) var(--px-scroll-track); }}
  .px-explorer-list::-webkit-scrollbar {{
    width: 10px;
    -webkit-appearance: none;
    background: var(--px-scroll-track);
  }}
  .px-explorer-list::-webkit-scrollbar-track {{
    background: var(--px-scroll-track);
    border-left: 1px solid var(--px-border);
  }}
  .px-explorer-list::-webkit-scrollbar-thumb {{
    background: var(--px-scroll-thumb);
    border-radius: 5px;
    border: 2px solid var(--px-scroll-track);
    min-height: 30px;
  }}
  .px-explorer-list::-webkit-scrollbar-thumb:hover {{ background: var(--px-scroll-thumb-hover); }}

  /* Main canvas: same always-visible scrollbar treatment. */
  #px-canvas {{ scrollbar-width: thin; scrollbar-color: var(--px-scroll-thumb) var(--px-bg); }}
  #px-canvas::-webkit-scrollbar {{
    width: 10px;
    height: 10px;
    -webkit-appearance: none;
    background: var(--px-bg);
  }}
  #px-canvas::-webkit-scrollbar-track {{
    background: var(--px-bg);
  }}
  #px-canvas::-webkit-scrollbar-thumb {{
    background: var(--px-scroll-thumb);
    border-radius: 5px;
    border: 2px solid var(--px-bg);
    min-height: 30px;
    min-width: 30px;
  }}
  #px-canvas::-webkit-scrollbar-thumb:hover {{ background: var(--px-scroll-thumb-hover); }}
  #px-canvas::-webkit-scrollbar-corner {{ background: var(--px-bg); }}

  /* Code editor: inherits the VS Code theme inside the webview when available.
     Otherwise falls back to theme-aware CSS vars so the editor stays coherent
     with the document surface whether we're in light or dark mode. */
  .px-editor-surface {{
    background: var(--vscode-editor-background, var(--px-code-bg));
    color: var(--vscode-editor-foreground, var(--px-ink));
    font-family: var(--vscode-editor-font-family, 'JetBrains Mono', 'SFMono-Regular', Menlo, monospace);
    font-size: var(--vscode-editor-font-size, 13px);
    line-height: 1.55;
  }}
  .px-editor-textarea::selection {{
    background: var(--vscode-editor-selectionBackground, var(--px-pill));
    color: transparent;
  }}

  /* Syntax highlighting: light theme is the default. Dark theme is applied
     when either VS Code signals it OR the user picks dark via the toggle
     (documented on :root[data-theme="dark"]). High-contrast stays on its
     existing body attribute selector. */
  .px-t-keyword {{ color: #af00db; }}
  .px-t-string {{ color: #a31515; }}
  .px-t-number {{ color: #098658; }}
  .px-t-comment {{ color: #008000; font-style: italic; }}
  .px-t-function {{ color: #795e26; }}
  .px-t-type {{ color: #267f99; }}
  .px-t-operator {{ color: #000000; }}
  .px-t-builtin {{ color: #0070c1; }}
  .px-t-decorator {{ color: #795e26; }}

  :root[data-theme="dark"] .px-t-keyword,
  body[data-vscode-theme-kind="vscode-dark"] .px-t-keyword {{ color: #c586c0; }}
  :root[data-theme="dark"] .px-t-string,
  body[data-vscode-theme-kind="vscode-dark"] .px-t-string {{ color: #ce9178; }}
  :root[data-theme="dark"] .px-t-number,
  body[data-vscode-theme-kind="vscode-dark"] .px-t-number {{ color: #b5cea8; }}
  :root[data-theme="dark"] .px-t-comment,
  body[data-vscode-theme-kind="vscode-dark"] .px-t-comment {{ color: #6a9955; font-style: italic; }}
  :root[data-theme="dark"] .px-t-function,
  body[data-vscode-theme-kind="vscode-dark"] .px-t-function {{ color: #dcdcaa; }}
  :root[data-theme="dark"] .px-t-type,
  body[data-vscode-theme-kind="vscode-dark"] .px-t-type {{ color: #4ec9b0; }}
  :root[data-theme="dark"] .px-t-operator,
  body[data-vscode-theme-kind="vscode-dark"] .px-t-operator {{ color: #d4d4d4; }}
  :root[data-theme="dark"] .px-t-builtin,
  body[data-vscode-theme-kind="vscode-dark"] .px-t-builtin {{ color: #4fc1ff; }}
  :root[data-theme="dark"] .px-t-decorator,
  body[data-vscode-theme-kind="vscode-dark"] .px-t-decorator {{ color: #dcdcaa; }}

  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-keyword {{ color: #569cd6; }}
  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-string {{ color: #ce9178; }}
  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-number {{ color: #b5cea8; }}
  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-comment {{ color: #7ca668; }}
  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-function {{ color: #dcdcaa; }}
  body[data-vscode-theme-kind="vscode-high-contrast"] .px-t-type {{ color: #4ec9b0; }}
</style>
</head>
<body>
<script>
  /* Anti-flash theme bootstrap. Runs before CSS paints so the user never
     sees a light-to-dark jump if they previously selected dark. Kept
     deliberately tiny and dependency-free. Mirrored by PX.initTheme() in
     tokens.js (belt-and-braces) and by the toggle wired in view-switcher.js. */
  (function () {{
    try {{
      var s = localStorage.getItem('prefxplain-theme');
      if (s === 'dark' || s === 'light') {{
        document.documentElement.setAttribute('data-theme', s);
      }}
    }} catch (e) {{ /* sandboxed iframe: stay with default light */ }}
  }})();
</script>
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
