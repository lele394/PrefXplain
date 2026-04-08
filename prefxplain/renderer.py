"""Render a Graph as a self-contained interactive HTML file.

No CDN dependencies. No external requests at render time.
Uses a minimal vanilla JS force-directed layout (canvas-based).
Supports: cycle highlighting, metrics panel, directory clusters, matrix view.
"""

from __future__ import annotations

import html as html_mod
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

# Role → hex color (for role-based coloring mode)
ROLE_COLORS = {
    "entry_point": "#22c55e",
    "utility":     "#a78bfa",
    "data_model":  "#f59e0b",
    "api_route":   "#3b82f6",
    "config":      "#6b7280",
    "test":        "#ef4444",
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
  header {{ padding: 12px 20px; background: #161b22; border-bottom: 1px solid #30363d; display: flex; align-items: center; gap: 16px; flex-shrink: 0; flex-wrap: wrap; }}
  header h1 {{ font-size: 15px; font-weight: 600; color: #e6edf3; }}
  header .stats {{ font-size: 12px; color: #8b949e; }}
  header input {{ padding: 5px 10px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; font-size: 12px; width: 200px; outline: none; }}
  header input:focus {{ border-color: #58a6ff; }}
  .legend {{ display: flex; gap: 12px; align-items: center; }}
  .legend-item {{ display: flex; align-items: center; gap: 4px; font-size: 11px; color: #8b949e; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .toolbar {{ display: flex; gap: 8px; align-items: center; }}
  .toolbar button {{ padding: 4px 10px; background: #21262d; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; font-size: 11px; cursor: pointer; }}
  .toolbar button:hover {{ background: #30363d; }}
  .toolbar button.active {{ background: #58a6ff; color: #0d1117; border-color: #58a6ff; }}
  .cycle-badge {{ background: #f8514930; border: 1px solid #f85149; color: #f85149; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
  main {{ display: flex; flex: 1; overflow: hidden; }}
  canvas {{ flex: 1; cursor: grab; }}
  canvas.dragging {{ cursor: grabbing; }}
  #sidebar {{ width: 320px; background: #161b22; border-left: 1px solid #30363d; padding: 16px; overflow-y: auto; flex-shrink: 0; font-size: 13px; display: flex; flex-direction: column; gap: 12px; }}
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
  #sidebar .role-tag {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }}
  .metric-row {{ display: flex; justify-content: space-between; padding: 3px 0; font-size: 12px; }}
  .metric-row .label {{ color: #8b949e; }}
  .metric-row .value {{ color: #e6edf3; font-weight: 600; }}
  .cycle-warning {{ background: #f8514920; border: 1px solid #f85149; border-radius: 6px; padding: 8px 12px; font-size: 12px; color: #f85149; }}
  .cycle-warning strong {{ color: #ff7b72; }}
  .metrics-panel {{ background: #21262d; border-radius: 6px; padding: 10px 12px; }}
</style>
</head>
<body>
<header>
  <h1>PrefXplain &mdash; {repo}</h1>
  <span class="stats">{total_files} files &middot; {total_edges} edges &middot; {languages}</span>
  {cycle_badge_html}
  <div class="legend">
    {legend_html}
  </div>
  <div class="toolbar">
    <button id="btnColorLang" class="active" onclick="setColorMode('language')">By Language</button>
    <button id="btnColorRole" onclick="setColorMode('role')">By Role</button>
    <button id="btnClusters" onclick="toggleClusters()">Clusters</button>
  </div>
  <input type="text" id="search" placeholder="Search files..." autocomplete="off" style="margin-left:auto">
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

function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}}
const ROLE_COLORS = {role_colors_json};
const CYCLE_NODES = new Set({cycle_nodes_json});
const CYCLE_EDGES = new Set({cycle_edges_json});
const CLUSTERS = {clusters_json};
const METRICS = {metrics_json};

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const sidebar = document.getElementById('sidebar');
const searchInput = document.getElementById('search');

// ── State ───────────────────────────────────────────────────────────────────
let colorMode = 'language'; // 'language' | 'role'
let showClusters = false;

function setColorMode(mode) {{
  colorMode = mode;
  document.getElementById('btnColorLang').classList.toggle('active', mode === 'language');
  document.getElementById('btnColorRole').classList.toggle('active', mode === 'role');
  draw();
}}

function toggleClusters() {{
  showClusters = !showClusters;
  document.getElementById('btnClusters').classList.toggle('active', showClusters);
  draw();
}}

// ── Layout ──────────────────────────────────────────────────────────────────

function resize() {{
  canvas.width = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;
}}
window.addEventListener('resize', () => {{ resize(); draw(); }});
resize();

// ── Force simulation ─────────────────────────────────────────────────────────

const NODE_W = 130, NODE_H = 36, NODE_R = 6;
const REPULSION = 8000, SPRING_LEN = 180, SPRING_K = 0.04, GRAVITY = 0.015, DAMPING = 0.85;

const nodes = GRAPH.nodes.map((n, i) => ({{
  ...n,
  x: canvas.width / 2 + (Math.random() - 0.5) * 600,
  y: canvas.height / 2 + (Math.random() - 0.5) * 400,
  vx: 0, vy: 0,
  fx: 0, fy: 0,
  pinned: false,
}}));

const nodeIndex = {{}};
nodes.forEach(n => {{ nodeIndex[n.id] = n; }});

const edges = GRAPH.edges.map(e => ({{
  ...e,
  source: nodeIndex[e.source],
  target: nodeIndex[e.target],
  _srcId: e.source,
  _tgtId: e.target,
}})).filter(e => e.source && e.target);

// Pre-built adjacency index — sidebar lookups go from O(E) per render to O(1).
// importsByNode[id] = list of {{id, dir}} for outgoing edges (this file imports X).
// importedByNode[id] = list of {{id, dir}} for incoming edges (X imports this file).
const importsByNode = {{}};
const importedByNode = {{}};
for (const n of nodes) {{
  importsByNode[n.id] = [];
  importedByNode[n.id] = [];
}}
for (const e of GRAPH.edges) {{
  if (importsByNode[e.source]) importsByNode[e.source].push({{ id: e.target, dir: 'out' }});
  if (importedByNode[e.target]) importedByNode[e.target].push({{ id: e.source, dir: 'in' }});
}}

let simRunning = true;
let simTicks = 0;

// ── Barnes-Hut quadtree ──────────────────────────────────────────────────────
// Replaces the O(n^2) all-pairs repulsion loop with an O(n log n) approximation.
// Each tree cell aggregates the center-of-mass of its nodes; when a node is
// "far enough" from a cell (cell width / distance < THETA), we treat the whole
// cell as a single point. This is the standard Barnes-Hut trick.

const THETA = 0.9;

function buildQuadtree(nodes) {{
  let xMin = Infinity, yMin = Infinity, xMax = -Infinity, yMax = -Infinity;
  for (const n of nodes) {{
    if (n.x < xMin) xMin = n.x;
    if (n.y < yMin) yMin = n.y;
    if (n.x > xMax) xMax = n.x;
    if (n.y > yMax) yMax = n.y;
  }}
  // Expand to a square so the quadrants are uniform
  const w = Math.max(xMax - xMin, yMax - yMin, 1);
  const cx = (xMin + xMax) / 2, cy = (yMin + yMax) / 2;
  const root = makeCell(cx - w / 2, cy - w / 2, w);
  for (const n of nodes) insertNode(root, n);
  return root;
}}

function makeCell(x, y, w) {{
  return {{ x, y, w, mass: 0, cmx: 0, cmy: 0, node: null, children: null }};
}}

function insertNode(cell, n) {{
  if (cell.mass === 0 && cell.node === null) {{
    cell.node = n;
    cell.mass = 1;
    cell.cmx = n.x;
    cell.cmy = n.y;
    return;
  }}
  if (cell.children === null) {{
    // Subdivide and re-insert the existing node
    const existing = cell.node;
    cell.node = null;
    cell.children = [
      makeCell(cell.x, cell.y, cell.w / 2),
      makeCell(cell.x + cell.w / 2, cell.y, cell.w / 2),
      makeCell(cell.x, cell.y + cell.w / 2, cell.w / 2),
      makeCell(cell.x + cell.w / 2, cell.y + cell.w / 2, cell.w / 2),
    ];
    if (existing) insertNode(cell.children[quadrant(cell, existing)], existing);
  }}
  insertNode(cell.children[quadrant(cell, n)], n);
  // Update center of mass
  const newMass = cell.mass + 1;
  cell.cmx = (cell.cmx * cell.mass + n.x) / newMass;
  cell.cmy = (cell.cmy * cell.mass + n.y) / newMass;
  cell.mass = newMass;
}}

function quadrant(cell, n) {{
  const right = n.x >= cell.x + cell.w / 2 ? 1 : 0;
  const bottom = n.y >= cell.y + cell.w / 2 ? 2 : 0;
  return right + bottom;
}}

function applyRepulsion(cell, n) {{
  if (cell.mass === 0) return;
  // Single-node leaf, skip self
  if (cell.node === n) return;
  const dx = n.x - cell.cmx, dy = n.y - cell.cmy;
  const dist2 = dx * dx + dy * dy + 1;
  const dist = Math.sqrt(dist2);
  // Far enough to approximate the whole cell as a point
  if (cell.children === null || (cell.w / dist) < THETA) {{
    const f = REPULSION * cell.mass / dist2;
    n.fx += f * dx / dist;
    n.fy += f * dy / dist;
    return;
  }}
  for (const child of cell.children) {{
    if (child.mass > 0) applyRepulsion(child, n);
  }}
}}

function tickSim() {{
  if (!simRunning) return;

  for (const n of nodes) {{ n.fx = 0; n.fy = 0; }}

  // O(n log n) repulsion via Barnes-Hut quadtree
  if (nodes.length > 0) {{
    const tree = buildQuadtree(nodes);
    for (const n of nodes) applyRepulsion(tree, n);
  }}

  // Gravity toward center
  for (const n of nodes) {{
    n.fx += (canvas.width / 2 - n.x) * GRAVITY;
    n.fy += (canvas.height / 2 - n.y) * GRAVITY;
  }}

  // Spring forces along edges
  for (const e of edges) {{
    const {{ source: a, target: b }} = e;
    const dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
    const f = (dist - SPRING_LEN) * SPRING_K;
    const fx = f * dx / dist, fy = f * dy / dist;
    a.fx += fx; a.fy += fy;
    b.fx -= fx; b.fy -= fy;
  }}

  // Apply forces with damping and integrate
  let totalEnergy = 0;
  for (const n of nodes) {{
    if (n.pinned) continue;
    n.vx = (n.vx + n.fx) * DAMPING;
    n.vy = (n.vy + n.fy) * DAMPING;
    n.x += n.vx;
    n.y += n.vy;
    totalEnergy += n.vx * n.vx + n.vy * n.vy;
  }}

  simTicks++;
  if (simTicks > 500 || totalEnergy < 0.01) simRunning = false;
}}

// ── Rendering ────────────────────────────────────────────────────────────────

let selectedNode = null;
let hoveredNode = null;
let searchQuery = '';
let highlightSet = null;

function nodeColor(n) {{
  if (colorMode === 'role' && n.role) return ROLE_COLORS[n.role] || '#888888';
  return COLORS[n.language] || '#888888';
}}

function nodeTextColor(n) {{
  if (colorMode === 'role') return '#ffffff';
  return TEXT_COLORS[n.language] || '#ffffff';
}}

function isVisible(n) {{
  if (!searchQuery) return true;
  return n.id.toLowerCase().includes(searchQuery) || n.label.toLowerCase().includes(searchQuery);
}}

function isCycleEdge(e) {{
  return CYCLE_EDGES.has(e._srcId + '|' + e._tgtId);
}}

// Cluster background colors (muted, semi-transparent)
const CLUSTER_PALETTE = [
  'rgba(75,139,190,0.06)', 'rgba(49,120,198,0.06)', 'rgba(247,223,30,0.06)',
  'rgba(34,197,94,0.06)', 'rgba(167,139,250,0.06)', 'rgba(245,158,11,0.06)',
  'rgba(239,68,68,0.06)', 'rgba(59,130,246,0.06)', 'rgba(107,114,128,0.06)',
];

function drawClusters() {{
  if (!showClusters) return;
  const clusterKeys = Object.keys(CLUSTERS);
  clusterKeys.forEach((dir, ci) => {{
    const clusterNodeIds = CLUSTERS[dir];
    const clusterNodes = clusterNodeIds.map(id => nodeIndex[id]).filter(Boolean);
    if (clusterNodes.length < 2) return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of clusterNodes) {{
      minX = Math.min(minX, n.x - NODE_W / 2);
      minY = Math.min(minY, n.y - NODE_H / 2);
      maxX = Math.max(maxX, n.x + NODE_W / 2);
      maxY = Math.max(maxY, n.y + NODE_H / 2);
    }}

    const pad = 20;
    const color = CLUSTER_PALETTE[ci % CLUSTER_PALETTE.length];
    ctx.fillStyle = color;
    ctx.strokeStyle = color.replace('0.06', '0.2');
    ctx.lineWidth = 1 / zoom;
    roundRect(ctx, minX - pad, minY - pad, maxX - minX + pad * 2, maxY - minY + pad * 2, 12);
    ctx.fill();
    ctx.stroke();

    // Label
    ctx.fillStyle = 'rgba(142,153,174,0.6)';
    ctx.font = `${{10 / zoom}}px -apple-system, monospace`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(dir, minX - pad + 6, minY - pad + 4);
  }});
}}

function draw() {{
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(zoom, zoom);

  // Cluster backgrounds
  drawClusters();

  // Edges
  for (const e of edges) {{
    const a = e.source, b = e.target;
    const vis = isVisible(a) && isVisible(b);
    if (!vis) continue;

    const faded = highlightSet && !highlightSet.has(a.id) && !highlightSet.has(b.id);
    const isCycle = isCycleEdge(e);
    ctx.globalAlpha = faded ? 0.08 : (isCycle ? 0.9 : 0.5);
    ctx.strokeStyle = isCycle ? '#f85149' : '#30363d';
    ctx.lineWidth = (isCycle ? 2.5 : 1) / zoom;

    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();

    // Arrow head
    const angle = Math.atan2(b.y - a.y, b.x - a.x);
    const tx = b.x - Math.cos(angle) * (NODE_W / 2 + 4);
    const ty = b.y - Math.sin(angle) * (NODE_H / 2 + 4);
    const as = (isCycle ? 9 : 7) / zoom;
    ctx.fillStyle = isCycle ? '#f85149' : '#30363d';
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
    const inCycle = CYCLE_NODES.has(n.id);

    // Shadow for selected
    if (isSelected) {{
      ctx.shadowColor = color;
      ctx.shadowBlur = 12 / zoom;
    }}

    // Rounded rect
    ctx.fillStyle = isSelected ? color : (isHovered ? '#21262d' : '#161b22');
    ctx.strokeStyle = inCycle ? '#f85149' : (isSelected ? color : (isHovered ? color : '#30363d'));
    ctx.lineWidth = (inCycle ? 2 : isSelected ? 2 : 1) / zoom;
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

    // Cycle indicator (right bar, red)
    if (inCycle && !isSelected) {{
      ctx.fillStyle = '#f85149';
      roundRect(ctx, x + NODE_W - 4, y, 4, NODE_H, {{ tl: 0, bl: 0, tr: NODE_R, br: NODE_R }});
      ctx.fill();
    }}

    // Label
    ctx.fillStyle = isSelected ? nodeTextColor(n) : '#e6edf3';
    ctx.font = `${{12 / zoom}}px -apple-system, monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const label = n.label.length > 18 ? n.label.slice(0, 16) + '\u2026' : n.label;
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
    simTicks = Math.max(simTicks, 400);
    startAnim();
  }} else {{
    dragStart = {{ x: e.offsetX, y: e.offsetY }};
    panStart = {{ ...pan }};
  }}
  canvas.classList.add('dragging');
  startAnim();
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
  draw();
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
    renderDefaultSidebar();
  }}
}}

function renderDefaultSidebar() {{
  let html = '<p class="placeholder">Click a node to see details.</p>';

  // Always show metrics overview
  html += '<div class="metrics-panel">';
  html += '<p class="section-title">Graph Metrics</p>';
  html += metricRow('Files', METRICS.total_files);
  html += metricRow('Edges', METRICS.total_edges);
  html += metricRow('Components', METRICS.components);
  html += metricRow('Cycles', METRICS.cycles, METRICS.cycles > 0 ? '#f85149' : '#22c55e');
  html += '</div>';

  if (METRICS.cycles > 0) {{
    html += '<div class="cycle-warning"><strong>\u26a0 ' + METRICS.cycles + ' circular dep' + (METRICS.cycles > 1 ? 's' : '') + '</strong><br>';
    METRICS.cycle_details.slice(0, 3).forEach(c => {{
      html += '<div style="margin-top:4px;font-size:11px">' + c.files.join(' \u2192 ') + ' \u2192 ' + c.files[0] + '</div>';
    }});
    if (METRICS.cycle_details.length > 3) html += '<div style="margin-top:4px;font-size:11px;color:#8b949e">+' + (METRICS.cycle_details.length - 3) + ' more</div>';
    html += '</div>';
  }}

  // Top hub files
  if (METRICS.top_imported && METRICS.top_imported.length) {{
    html += '<div class="metrics-panel">';
    html += '<p class="section-title">Most Imported (Hub Files)</p>';
    METRICS.top_imported.slice(0, 5).forEach(m => {{
      if (m.indegree > 0) html += metricRow(m.id.split('/').pop(), m.indegree + ' imports');
    }});
    html += '</div>';
  }}

  sidebar.innerHTML = html;
}}

function metricRow(label, value, color) {{
  const vc = color ? ' style="color:' + color + '"' : '';
  return '<div class="metric-row"><span class="label">' + label + '</span><span class="value"' + vc + '>' + value + '</span></div>';
}}

function renderSidebar(n) {{
  // O(1) lookup via pre-built adjacency index instead of O(E) filter.
  const imports = importsByNode[n.id] || [];
  const importedBy = importedByNode[n.id] || [];
  const inCycle = CYCLE_NODES.has(n.id);

  const roleHtml = n.role ? '<span class="role-tag" style="background:' + (ROLE_COLORS[n.role] || '#888') + '30;color:' + (ROLE_COLORS[n.role] || '#888') + '">' + n.role.replace('_', ' ') + '</span>' : '';

  const symbolHtml = n.symbols.length
    ? n.symbols.slice(0, 30).map(s => `<span class="symbol ${{s.kind === 'function' ? 'fn' : s.kind === 'class' ? 'cls' : 'var'}}">${{esc(s.name)}}</span>`).join('')
    : '<span style="color:#6e7681;font-size:12px">none</span>';

  const neighborHtml = (list, arrow) => list.slice(0, 20).map(item => {{
    // O(1) node lookup via nodeIndex instead of O(N) Array.find.
    const node = nodeIndex[item.id];
    const label = node ? node.label : item.id.split('/').pop();
    const cycleFlag = CYCLE_EDGES.has(n.id + '|' + item.id) || CYCLE_EDGES.has(item.id + '|' + n.id)
      ? ' <span style="color:#f85149;font-size:10px">\u26a0 cycle</span>' : '';
    return `<div class="neighbor" onclick="jumpTo('${{esc(item.id)}}')">`
      + `<span class="arrow">${{arrow}}</span>`
      + `<span>${{esc(label)}}</span>${{cycleFlag}}`
      + `</div>`;
  }}).join('') || '<span style="color:#6e7681;font-size:12px">none</span>';

  sidebar.innerHTML = `
    <div>
      <h2>${{esc(n.id)}}</h2>
      <span style="font-size:11px;color:#6e7681">${{esc(n.language)}} &middot; ${{(n.size/1024).toFixed(1)}} KB ${{roleHtml}}</span>
    </div>
    ${{inCycle ? '<div class="cycle-warning"><strong>\u26a0 In circular dependency</strong></div>' : ''}}
    ${{n.description ? `<p class="desc">${{esc(n.description)}}</p>` : '<p class="desc" style="color:#6e7681">No description yet.</p>'}}
    <div>
      <p class="section-title">Exports / Symbols</p>
      <div style="margin-top:6px">${{symbolHtml}}</div>
    </div>
    <div>
      <p class="section-title">Imports (${{imports.length}})</p>
      <div style="margin-top:4px">${{neighborHtml(imports, '\u2192')}}</div>
    </div>
    <div>
      <p class="section-title">Imported by (${{importedBy.length}})</p>
      <div style="margin-top:4px">${{neighborHtml(importedBy, '\u2190')}}</div>
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
    renderDefaultSidebar();
  }}
  // Force a redraw — without this, filtering doesn't appear until the next
  // mouseover or animation frame.
  draw();
}});

// ── Animation loop ────────────────────────────────────────────────────────────

let animating = false;
function loop() {{
  tickSim();
  draw();
  if (simRunning || dragging) {{
    requestAnimationFrame(loop);
  }} else {{
    animating = false;
    draw(); // final frame
  }}
}}
function startAnim() {{
  if (!animating) {{ animating = true; loop(); }}
}}

// Initial sidebar with metrics
renderDefaultSidebar();

startAnim();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Matrix view renderer
# ---------------------------------------------------------------------------

_MATRIX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PrefXplain Matrix — {repo}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }}
  h1 {{ font-size: 18px; margin-bottom: 8px; color: #e6edf3; }}
  .stats {{ font-size: 12px; color: #8b949e; margin-bottom: 20px; }}
  .matrix-wrap {{ overflow: auto; max-height: calc(100vh - 100px); }}
  table {{ border-collapse: collapse; }}
  th, td {{ width: 28px; height: 28px; text-align: center; font-size: 9px; border: 1px solid #21262d; }}
  th {{ background: #161b22; color: #8b949e; position: sticky; }}
  th.row-header {{ text-align: right; padding-right: 6px; white-space: nowrap; min-width: 120px; left: 0; z-index: 2; }}
  th.col-header {{ writing-mode: vertical-lr; text-orientation: mixed; padding: 4px 2px; top: 0; z-index: 1; }}
  th.corner {{ top: 0; left: 0; z-index: 3; }}
  td.dep {{ background: #58a6ff30; cursor: pointer; }}
  td.dep:hover {{ background: #58a6ff60; }}
  td.cycle {{ background: #f8514940; }}
  td.cycle:hover {{ background: #f8514970; }}
  td.self {{ background: #21262d; }}
  .legend-matrix {{ margin-bottom: 12px; display: flex; gap: 16px; font-size: 12px; color: #8b949e; }}
  .legend-matrix span {{ display: flex; align-items: center; gap: 4px; }}
  .legend-matrix .box {{ width: 14px; height: 14px; border-radius: 2px; }}
</style>
</head>
<body>
<h1>PrefXplain Matrix &mdash; {repo}</h1>
<div class="stats">{total_files} files &middot; {total_edges} edges &middot; Rows import columns</div>
<div class="legend-matrix">
  <span><div class="box" style="background:#58a6ff30;border:1px solid #58a6ff"></div> Dependency</span>
  <span><div class="box" style="background:#f8514940;border:1px solid #f85149"></div> Circular</span>
</div>
<div class="matrix-wrap">
{matrix_table}
</div>
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

    # Cycle info — compute once, reuse everywhere
    cycles = graph.find_cycles()
    cycle_node_set: set[str] = set()
    for c in cycles:
        cycle_node_set.update(c)
    cycle_nodes = list(cycle_node_set)

    # Derive cycle edges from the computed cycles directly
    cycle_edge_set: set[tuple[str, str]] = set()
    for cycle in cycles:
        cs = set(cycle)
        for e in graph.edges:
            if e.source in cs and e.target in cs:
                cycle_edge_set.add((e.source, e.target))
    cycle_edges_list = [f"{s}|{t}" for s, t in cycle_edge_set]

    num_cycles = len(cycles)
    cycle_badge_html = ""
    if num_cycles > 0:
        cycle_badge_html = (
            f'<span class="cycle-badge">{num_cycles} circular dep'
            f'{"s" if num_cycles > 1 else ""}</span>'
        )

    # Clusters + Metrics (pass pre-computed cycles)
    clusters = graph.cluster_by_directory()
    metrics = graph.metrics()

    def _safe_json(obj) -> str:
        # Escape </ to prevent breaking out of <script> context.
        # A description or filename containing </script> would otherwise
        # close the script block and execute arbitrary HTML/JS that follows.
        # We also escape <!-- and ]]> for HTML comment / CDATA safety.
        text = json.dumps(obj, ensure_ascii=False)
        return (
            text.replace("</", "<\\/")
            .replace("<!--", "<\\!--")
            .replace("]]>", "]]\\>")
        )

    graph_json = _safe_json(graph.to_dict())
    colors_json = _safe_json(LANG_COLORS)
    text_colors_json = _safe_json(LANG_TEXT_COLORS)
    role_colors_json = _safe_json(ROLE_COLORS)
    cycle_nodes_json = _safe_json(cycle_nodes)
    cycle_edges_json = _safe_json(cycle_edges_list)
    clusters_json = _safe_json(clusters)
    metrics_json = _safe_json(metrics)

    html = _HTML_TEMPLATE.format(
        repo=repo,
        total_files=total_files,
        total_edges=total_edges,
        languages=languages,
        legend_html=legend_html,
        cycle_badge_html=cycle_badge_html,
        graph_json=graph_json,
        colors_json=colors_json,
        text_colors_json=text_colors_json,
        role_colors_json=role_colors_json,
        cycle_nodes_json=cycle_nodes_json,
        cycle_edges_json=cycle_edges_json,
        clusters_json=clusters_json,
        metrics_json=metrics_json,
    )

    if output_path:
        output_path.write_text(html, encoding="utf-8")

    return html


def render_matrix(graph: Graph, output_path: Path | None = None) -> str:
    """Render a dependency matrix as self-contained HTML.

    Rows are importers, columns are imported files.
    """
    meta = graph.metadata
    repo = meta.repo if meta else "repo"
    total_files = len(graph.nodes)
    total_edges = len(graph.edges)

    node_ids = sorted(n.id for n in graph.nodes)
    edge_set = {(e.source, e.target) for e in graph.edges}
    cycle_edge_set = graph.cycle_edges()

    # Build the HTML table
    esc = html_mod.escape
    labels = [nid.split("/")[-1] for nid in node_ids]

    rows = ['<table>']
    # Header row
    rows.append('<tr><th class="corner"></th>')
    for i, label in enumerate(labels):
        rows.append(f'<th class="col-header" title="{esc(node_ids[i])}">{esc(label)}</th>')
    rows.append('</tr>')

    # Data rows
    for i, src_id in enumerate(node_ids):
        rows.append(f'<tr><th class="row-header" title="{esc(src_id)}">{esc(labels[i])}</th>')
        for j, tgt_id in enumerate(node_ids):
            if i == j:
                rows.append('<td class="self"></td>')
            elif (src_id, tgt_id) in cycle_edge_set:
                rows.append(f'<td class="cycle" title="{esc(src_id)} \u2192 {esc(tgt_id)} (cycle)">\u25cf</td>')
            elif (src_id, tgt_id) in edge_set:
                rows.append(f'<td class="dep" title="{esc(src_id)} \u2192 {esc(tgt_id)}">\u25cf</td>')
            else:
                rows.append('<td></td>')
        rows.append('</tr>')

    rows.append('</table>')
    matrix_table = "\n".join(rows)

    html = _MATRIX_TEMPLATE.format(
        repo=repo,
        total_files=total_files,
        total_edges=total_edges,
        matrix_table=matrix_table,
    )

    if output_path:
        output_path.write_text(html, encoding="utf-8")

    return html
