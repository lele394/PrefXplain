"""Render a Graph as a self-contained interactive HTML file.

No CDN dependencies. No external requests at render time.
Uses a minimal vanilla JS force-directed layout (canvas-based).
"""

from __future__ import annotations

import json
from pathlib import Path

from .graph import Graph

# Language → hex color
LANG_COLORS = {
    "python":     "#4B8BBE",  # Python blue
    "typescript": "#3178C6",  # TS blue
    "javascript": "#F7DF1E",  # JS yellow (text will be dark)
    "other":      "#888888",
}

LANG_TEXT_COLORS = {
    "javascript": "#111111",
}


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PrefXplain — {repo}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", monospace; background: #0d1117; color: #c9d1d9; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}
  header {{ padding: 12px 20px; background: #161b22; border-bottom: 1px solid #30363d; display: flex; align-items: center; gap: 16px; flex-shrink: 0; }}
  header h1 {{ font-size: 15px; font-weight: 600; color: #e6edf3; }}
  header .stats {{ font-size: 12px; color: #8b949e; }}
  header input {{ margin-left: auto; padding: 5px 10px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; font-size: 12px; width: 200px; outline: none; }}
  header input:focus {{ border-color: #58a6ff; }}
  .legend {{ display: flex; gap: 12px; align-items: center; }}
  .legend-item {{ display: flex; align-items: center; gap: 4px; font-size: 11px; color: #8b949e; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  main {{ display: flex; flex: 1; overflow: hidden; }}
  canvas {{ flex: 1; cursor: grab; }}
  canvas.dragging {{ cursor: grabbing; }}
  #sidebar {{ width: 300px; background: #161b22; border-left: 1px solid #30363d; padding: 16px; overflow-y: auto; flex-shrink: 0; font-size: 13px; display: flex; flex-direction: column; gap: 12px; }}
  #sidebar h2 {{ font-size: 13px; font-weight: 600; color: #e6edf3; word-break: break-all; }}
  #sidebar .desc {{ color: #8b949e; line-height: 1.5; }}
  #sidebar .section-title {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #6e7681; margin-top: 4px; }}
  #sidebar .symbol {{ display: inline-block; background: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-family: monospace; margin: 2px; }}
  #sidebar .symbol.fn {{ color: #d2a8ff; }}
  #sidebar .symbol.cls {{ color: #79c0ff; }}
  #sidebar .symbol.var {{ color: #ffa657; }}
  #sidebar .neighbor {{ display: flex; align-items: center; gap: 6px; padding: 4px 0; cursor: pointer; color: #58a6ff; }}
  #sidebar .neighbor:hover {{ color: #79c0ff; }}
  #sidebar .neighbor .arrow {{ color: #6e7681; font-size: 10px; }}
  #sidebar .placeholder {{ color: #6e7681; font-style: italic; font-size: 12px; }}
</style>
</head>
<body>
<header>
  <h1>PrefXplain — {repo}</h1>
  <span class="stats">{total_files} files &middot; {total_edges} edges &middot; {languages}</span>
  <div class="legend">
    {legend_html}
  </div>
  <input type="text" id="search" placeholder="Search files..." autocomplete="off">
</header>
<main>
  <canvas id="canvas"></canvas>
  <div id="sidebar">
    <p class="placeholder">Click a node to see details.</p>
  </div>
</main>

<script>
const GRAPH = {graph_json};

const COLORS = {colors_json};
const TEXT_COLORS = {text_colors_json};

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const sidebar = document.getElementById('sidebar');
const searchInput = document.getElementById('search');

// ── Layout ──────────────────────────────────────────────────────────────────

function resize() {{
  canvas.width = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;
}}
window.addEventListener('resize', () => {{ resize(); draw(); }});
resize();

// ── Force simulation ─────────────────────────────────────────────────────────

const NODE_W = 130, NODE_H = 36, NODE_R = 6;
const REPULSION = 8000, SPRING_LEN = 180, SPRING_K = 0.04, GRAVITY = 0.015, DAMPING = 0.88;

const nodes = GRAPH.nodes.map((n, i) => ({{
  ...n,
  x: canvas.width / 2 + (Math.random() - 0.5) * 600,
  y: canvas.height / 2 + (Math.random() - 0.5) * 400,
  vx: 0, vy: 0,
  pinned: false,
}}));

const nodeIndex = {{}};
nodes.forEach(n => {{ nodeIndex[n.id] = n; }});

const edges = GRAPH.edges.map(e => ({{
  ...e,
  source: nodeIndex[e.source],
  target: nodeIndex[e.target],
}})).filter(e => e.source && e.target);

let simRunning = true;
let simTicks = 0;

function tickSim() {{
  if (!simRunning) return;

  for (let i = 0; i < nodes.length; i++) {{
    const a = nodes[i];
    if (a.pinned) continue;
    let fx = 0, fy = 0;

    // Repulsion
    for (let j = 0; j < nodes.length; j++) {{
      if (i === j) continue;
      const b = nodes[j];
      const dx = a.x - b.x, dy = a.y - b.y;
      const dist2 = dx * dx + dy * dy + 1;
      const f = REPULSION / dist2;
      fx += f * dx / Math.sqrt(dist2);
      fy += f * dy / Math.sqrt(dist2);
    }}

    // Gravity toward center
    fx += (canvas.width / 2 - a.x) * GRAVITY;
    fy += (canvas.height / 2 - a.y) * GRAVITY;

    a.vx = (a.vx + fx) * DAMPING;
    a.vy = (a.vy + fy) * DAMPING;
  }}

  // Spring forces along edges
  for (const e of edges) {{
    const {{ source: a, target: b }} = e;
    const dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
    const f = (dist - SPRING_LEN) * SPRING_K;
    const fx = f * dx / dist, fy = f * dy / dist;
    if (!a.pinned) {{ a.vx += fx; a.vy += fy; }}
    if (!b.pinned) {{ b.vx -= fx; b.vy -= fy; }}
  }}

  // Integrate
  for (const n of nodes) {{
    if (!n.pinned) {{ n.x += n.vx; n.y += n.vy; }}
  }}

  simTicks++;
  if (simTicks > 300) simRunning = false;
}}

// ── Rendering ────────────────────────────────────────────────────────────────

let selectedNode = null;
let hoveredNode = null;
let searchQuery = '';
let highlightSet = null; // set of node ids to highlight (neighbors of selected)

function nodeColor(n) {{
  return COLORS[n.language] || '#888888';
}}
function nodeTextColor(n) {{
  return TEXT_COLORS[n.language] || '#ffffff';
}}

function isVisible(n) {{
  if (!searchQuery) return true;
  return n.id.toLowerCase().includes(searchQuery) || n.label.toLowerCase().includes(searchQuery);
}}

function draw() {{
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(zoom, zoom);

  // Edges
  ctx.strokeStyle = '#30363d';
  ctx.lineWidth = 1 / zoom;
  for (const e of edges) {{
    const a = e.source, b = e.target;
    const vis = isVisible(a) && isVisible(b);
    if (!vis) continue;

    const faded = highlightSet && !highlightSet.has(a.id) && !highlightSet.has(b.id);
    ctx.globalAlpha = faded ? 0.12 : 0.5;

    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();

    // Arrow head
    const angle = Math.atan2(b.y - a.y, b.x - a.x);
    const tx = b.x - Math.cos(angle) * (NODE_W / 2 + 4);
    const ty = b.y - Math.sin(angle) * (NODE_H / 2 + 4);
    const as = 7 / zoom;
    ctx.fillStyle = '#30363d';
    ctx.beginPath();
    ctx.moveTo(tx, ty);
    ctx.lineTo(tx - as * Math.cos(angle - 0.4), ty - as * Math.sin(angle - 0.4));
    ctx.lineTo(tx - as * Math.cos(angle + 0.4), ty - as * Math.sin(angle + 0.4));
    ctx.closePath();
    ctx.fill();
  }}

  ctx.globalAlpha = 1;

  // Nodes
  for (const n of nodes) {{
    if (!isVisible(n)) continue;
    const faded = highlightSet && !highlightSet.has(n.id);
    ctx.globalAlpha = faded ? 0.2 : 1;

    const x = n.x - NODE_W / 2, y = n.y - NODE_H / 2;
    const color = nodeColor(n);
    const isSelected = selectedNode === n;
    const isHovered = hoveredNode === n;

    // Shadow for selected
    if (isSelected) {{
      ctx.shadowColor = color;
      ctx.shadowBlur = 12 / zoom;
    }}

    // Rounded rect
    ctx.fillStyle = isSelected ? color : (isHovered ? '#21262d' : '#161b22');
    ctx.strokeStyle = isSelected ? color : (isHovered ? color : '#30363d');
    ctx.lineWidth = (isSelected ? 2 : 1) / zoom;
    roundRect(ctx, x, y, NODE_W, NODE_H, NODE_R);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Language indicator (left bar)
    if (!isSelected) {{
      ctx.fillStyle = color;
      roundRect(ctx, x, y, 4, NODE_H, {{ tl: NODE_R, bl: NODE_R, tr: 0, br: 0 }});
      ctx.fill();
    }}

    // Label
    ctx.fillStyle = isSelected ? nodeTextColor(n) : '#e6edf3';
    ctx.font = `${{12 / zoom}}px -apple-system, monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const label = n.label.length > 18 ? n.label.slice(0, 16) + '…' : n.label;
    ctx.fillText(label, n.x, n.y);
  }}

  ctx.globalAlpha = 1;
  ctx.restore();
}}

function roundRect(ctx, x, y, w, h, r) {{
  const radii = typeof r === 'number'
    ? {{ tl: r, tr: r, br: r, bl: r }}
    : {{ tl: r.tl || 0, tr: r.tr || 0, br: r.br || 0, bl: r.bl || 0 }};
  ctx.beginPath();
  ctx.moveTo(x + radii.tl, y);
  ctx.lineTo(x + w - radii.tr, y);
  ctx.arcTo(x + w, y, x + w, y + radii.tr, radii.tr);
  ctx.lineTo(x + w, y + h - radii.br);
  ctx.arcTo(x + w, y + h, x + w - radii.br, y + h, radii.br);
  ctx.lineTo(x + radii.bl, y + h);
  ctx.arcTo(x, y + h, x, y + h - radii.bl, radii.bl);
  ctx.lineTo(x, y + radii.tl);
  ctx.arcTo(x, y, x + radii.tl, y, radii.tl);
  ctx.closePath();
}}

// ── Pan & zoom ───────────────────────────────────────────────────────────────

let pan = {{ x: 0, y: 0 }}, zoom = 1;
let dragging = false, dragStart = null, panStart = null, dragNode = null;

function worldCoords(cx, cy) {{
  return {{ x: (cx - pan.x) / zoom, y: (cy - pan.y) / zoom }};
}}

function nodeAt(wx, wy) {{
  for (let i = nodes.length - 1; i >= 0; i--) {{
    const n = nodes[i];
    if (!isVisible(n)) continue;
    if (Math.abs(wx - n.x) <= NODE_W / 2 && Math.abs(wy - n.y) <= NODE_H / 2) return n;
  }}
  return null;
}}

canvas.addEventListener('mousedown', e => {{
  const {{ x: wx, y: wy }} = worldCoords(e.offsetX, e.offsetY);
  const n = nodeAt(wx, wy);
  dragging = true;
  if (n) {{
    dragNode = n;
    n.pinned = true;
    simRunning = true;
    simTicks = 0;
  }} else {{
    dragStart = {{ x: e.offsetX, y: e.offsetY }};
    panStart = {{ ...pan }};
  }}
  canvas.classList.add('dragging');
}});

canvas.addEventListener('mousemove', e => {{
  const {{ x: wx, y: wy }} = worldCoords(e.offsetX, e.offsetY);
  if (dragging && dragNode) {{
    dragNode.x = wx; dragNode.y = wy;
    dragNode.vx = 0; dragNode.vy = 0;
  }} else if (dragging && dragStart) {{
    pan.x = panStart.x + (e.offsetX - dragStart.x);
    pan.y = panStart.y + (e.offsetY - dragStart.y);
  }} else {{
    const prev = hoveredNode;
    hoveredNode = nodeAt(wx, wy);
    if (prev !== hoveredNode) draw();
    canvas.style.cursor = hoveredNode ? 'pointer' : 'grab';
  }}
}});

canvas.addEventListener('mouseup', e => {{
  if (dragging && dragNode && !dragStart) {{
    // click on node if barely moved
    const {{ x: wx, y: wy }} = worldCoords(e.offsetX, e.offsetY);
    if (Math.abs(wx - dragNode.x) < 5 && Math.abs(wy - dragNode.y) < 5) {{
      selectNode(dragNode);
    }}
    dragNode.pinned = false;
    dragNode = null;
  }}
  dragging = false;
  dragStart = null;
  panStart = null;
  canvas.classList.remove('dragging');
}});

canvas.addEventListener('wheel', e => {{
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  const wx = (e.offsetX - pan.x) / zoom;
  const wy = (e.offsetY - pan.y) / zoom;
  zoom *= factor;
  zoom = Math.max(0.1, Math.min(4, zoom));
  pan.x = e.offsetX - wx * zoom;
  pan.y = e.offsetY - wy * zoom;
}}, {{ passive: false }});

// ── Sidebar ──────────────────────────────────────────────────────────────────

function selectNode(n) {{
  selectedNode = selectedNode === n ? null : n;
  if (selectedNode) {{
    const neighbors = new Set([n.id]);
    GRAPH.edges.forEach(e => {{
      if (e.source === n.id) neighbors.add(e.target);
      if (e.target === n.id) neighbors.add(e.source);
    }});
    highlightSet = neighbors;
    renderSidebar(n);
  }} else {{
    highlightSet = null;
    sidebar.innerHTML = '<p class="placeholder">Click a node to see details.</p>';
  }}
}}

function renderSidebar(n) {{
  const imports = GRAPH.edges.filter(e => e.source === n.id).map(e => ({{ id: e.target, dir: 'out' }}));
  const importedBy = GRAPH.edges.filter(e => e.target === n.id).map(e => ({{ id: e.source, dir: 'in' }}));

  const symbolHtml = n.symbols.length
    ? n.symbols.slice(0, 30).map(s => `<span class="symbol ${{s.kind === 'function' ? 'fn' : s.kind === 'class' ? 'cls' : 'var'}}">${{s.name}}</span>`).join('')
    : '<span style="color:#6e7681;font-size:12px">none</span>';

  const neighborHtml = (list, arrow) => list.slice(0, 20).map(item => {{
    const node = GRAPH.nodes.find(x => x.id === item.id);
    const label = node ? node.label : item.id.split('/').pop();
    return `<div class="neighbor" onclick="jumpTo('${{item.id}}')">`
      + `<span class="arrow">${{arrow}}</span>`
      + `<span>${{label}}</span>`
      + `</div>`;
  }}).join('') || '<span style="color:#6e7681;font-size:12px">none</span>';

  sidebar.innerHTML = `
    <div>
      <h2>${{n.id}}</h2>
      <span style="font-size:11px;color:#6e7681">${{n.language}} &middot; ${{(n.size/1024).toFixed(1)}} KB</span>
    </div>
    ${{n.description ? `<p class="desc">${{n.description}}</p>` : '<p class="desc" style="color:#6e7681">No description yet.</p>'}}
    <div>
      <p class="section-title">Exports / Symbols</p>
      <div style="margin-top:6px">${{symbolHtml}}</div>
    </div>
    <div>
      <p class="section-title">Imports (${{imports.length}})</p>
      <div style="margin-top:4px">${{neighborHtml(imports, '→')}}</div>
    </div>
    <div>
      <p class="section-title">Imported by (${{importedBy.length}})</p>
      <div style="margin-top:4px">${{neighborHtml(importedBy, '←')}}</div>
    </div>
  `;
}}

function jumpTo(nodeId) {{
  const n = nodeIndex[nodeId];
  if (!n) return;
  selectNode(n);
  pan.x = canvas.width / 2 - n.x * zoom;
  pan.y = canvas.height / 2 - n.y * zoom;
}}
window.jumpTo = jumpTo;

// ── Search ───────────────────────────────────────────────────────────────────

searchInput.addEventListener('input', e => {{
  searchQuery = e.target.value.toLowerCase().trim();
  if (!searchQuery) {{
    selectedNode = null;
    highlightSet = null;
    sidebar.innerHTML = '<p class="placeholder">Click a node to see details.</p>';
  }}
}});

// ── Animation loop ────────────────────────────────────────────────────────────

function loop() {{
  tickSim();
  draw();
  requestAnimationFrame(loop);
}}
loop();
</script>
</body>
</html>
"""


def render(graph: Graph, output_path: Path | None = None) -> str:
    """Render a graph as a self-contained interactive HTML string.

    Args:
        graph: The graph to render.
        output_path: If provided, write the HTML to this path.

    Returns:
        The HTML string.
    """
    meta = graph.metadata
    repo = meta.repo if meta else "repo"
    total_files = meta.total_files if meta else len(graph.nodes)
    total_edges = len(graph.edges)
    languages = ", ".join(meta.languages) if meta and meta.languages else "unknown"

    # Legend HTML
    lang_set = sorted(set(n.language for n in graph.nodes if n.language))
    legend_items = []
    for lang in lang_set:
        color = LANG_COLORS.get(lang, "#888888")
        legend_items.append(
            f'<div class="legend-item">'
            f'<div class="legend-dot" style="background:{color}"></div>'
            f'{lang}</div>'
        )
    legend_html = "".join(legend_items)

    graph_json = json.dumps(graph.to_dict(), ensure_ascii=False)
    colors_json = json.dumps(LANG_COLORS)
    text_colors_json = json.dumps(LANG_TEXT_COLORS)

    html = _HTML_TEMPLATE.format(
        repo=repo,
        total_files=total_files,
        total_edges=total_edges,
        languages=languages,
        legend_html=legend_html,
        graph_json=graph_json,
        colors_json=colors_json,
        text_colors_json=text_colors_json,
    )

    if output_path:
        output_path.write_text(html, encoding="utf-8")

    return html
