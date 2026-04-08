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
  .health-badge {{ padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
  #statsbar {{ padding: 6px 20px; background: #0d1117; border-bottom: 1px solid #21262d; display: flex; gap: 24px; align-items: center; flex-shrink: 0; flex-wrap: wrap; font-size: 11px; color: #8b949e; }}
  #statsbar .stat-group {{ display: flex; gap: 6px; align-items: center; }}
  #statsbar .stat-label {{ color: #6e7681; }}
  #statsbar .stat-value {{ color: #e6edf3; font-weight: 600; }}
  #statsbar .role-chip {{ padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; text-transform: uppercase; margin-right: 2px; }}
  main {{ display: flex; flex: 1; overflow: hidden; position: relative; }}
  #minimap {{ position: absolute; bottom: 12px; right: 328px; width: 160px; height: 100px; background: #161b22cc; border: 1px solid #30363d; border-radius: 6px; cursor: pointer; z-index: 10; }}
  #help-overlay {{ display: none; position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 24px; z-index: 20; min-width: 280px; }}
  #help-overlay h3 {{ color: #e6edf3; font-size: 14px; margin-bottom: 12px; }}
  #help-overlay kbd {{ background: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 1px 6px; font-size: 11px; font-family: monospace; }}
  #help-overlay .kb-row {{ display: flex; justify-content: space-between; gap: 20px; padding: 4px 0; font-size: 12px; color: #c9d1d9; }}
  #ego-banner {{ display: none; position: absolute; top: 10px; left: 50%; transform: translateX(-50%); background: #58a6ff20; border: 1px solid #58a6ff60; border-radius: 6px; padding: 4px 12px; font-size: 12px; color: #58a6ff; z-index: 10; }}
  /* Only the main canvas should grow to fill flex space — minimap is absolute. */
  #canvas {{ flex: 1; min-width: 0; cursor: grab; display: block; }}
  #canvas.dragging {{ cursor: grabbing; }}
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
  /* Code preview panel — like CodeViz, monospace with line numbers */
  .code-preview {{
    background: #010409;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 10px 0;
    margin-top: 6px;
    max-height: 360px;
    overflow: auto;
    font-family: "SF Mono", Monaco, Menlo, "Courier New", monospace;
    font-size: 11px;
    line-height: 1.55;
    color: #c9d1d9;
    white-space: pre;
  }}
  .code-preview code {{ display: block; padding: 0 12px; }}
  .code-preview .ln {{
    display: inline-block;
    width: 32px;
    margin-right: 12px;
    color: #484f58;
    text-align: right;
    user-select: none;
  }}
  /* Make the sidebar wider so the code preview is actually readable */
  #sidebar {{ width: 360px; }}
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
    <button id="btnClusters" onclick="toggleClusters()">By Purpose</button>
    <button id="btnEdges" onclick="toggleEdgeMode()">Edges: Hover</button>
    <button onclick="zoomToFit()">Fit</button>
    <button onclick="toggleHelp()">?</button>
  </div>
  <input type="text" id="search" placeholder="/ to search..." autocomplete="off" style="margin-left:auto">
</header>
<div id="statsbar"></div>
<main>
  <canvas id="canvas"></canvas>
  <canvas id="minimap"></canvas>
  <div id="ego-banner">Ego view &mdash; press <kbd>Esc</kbd> to exit</div>
  <div id="help-overlay">
    <h3>Keyboard Shortcuts</h3>
    <div class="kb-row"><span><kbd>/</kbd></span><span>Focus search</span></div>
    <div class="kb-row"><span><kbd>Esc</kbd></span><span>Deselect / exit ego view</span></div>
    <div class="kb-row"><span><kbd>E</kbd></span><span>Ego-centric view (selected node)</span></div>
    <div class="kb-row"><span><kbd>F</kbd></span><span>Zoom to fit all nodes</span></div>
    <div class="kb-row"><span><kbd>C</kbd></span><span>Toggle cluster backgrounds</span></div>
    <div class="kb-row"><span><kbd>?</kbd></span><span>Toggle this help panel</span></div>
    <div style="margin-top:12px;font-size:11px;color:#6e7681">Double-click a node to enter ego view</div>
  </div>
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
const CLUSTERS_BY_ROLE = {clusters_by_role_json};
const ROLE_ORDER = {role_order_json};
const ROLE_SUBTITLES = {role_subtitles_json};
const METRICS = {metrics_json};
const NODE_METRICS = {node_metrics_json};
const HEALTH = {health_json};
const LANG_COUNTS = {lang_counts_json};

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const sidebar = document.getElementById('sidebar');
const searchInput = document.getElementById('search');

// ── State ───────────────────────────────────────────────────────────────────
let colorMode = 'language'; // 'language' | 'role'
let clusterMode = 'off'; // 'off' | 'dir' | 'role'
let edgeMode = 'hover'; // 'hover' | 'all'

// Convenience getter used throughout the code (replaces the old showClusters bool)
function showClusters() {{ return clusterMode !== 'off'; }}

function setColorMode(mode) {{
  colorMode = mode;
  document.getElementById('btnColorLang').classList.toggle('active', mode === 'language');
  document.getElementById('btnColorRole').classList.toggle('active', mode === 'role');
  draw();
}}

// Toggle between the two cluster views: role ↔ dir
function toggleClusters() {{
  clusterMode = (clusterMode === 'role') ? 'dir' : 'role';
  const btn = document.getElementById('btnClusters');
  btn.textContent = clusterMode === 'dir' ? 'By Directory' : 'By Purpose';
  btn.classList.add('active');
  layoutClusters(clusterMode);
  simRunning = false;
  draw();
}}

function toggleEdgeMode() {{
  edgeMode = edgeMode === 'hover' ? 'all' : 'hover';
  const btn = document.getElementById('btnEdges');
  btn.textContent = edgeMode === 'hover' ? 'Edges: Hover' : 'Edges: All';
  btn.classList.toggle('active', edgeMode === 'all');
  draw();
}}

// One-shot grid layout when Clusters mode is enabled.
// mode = 'dir': each directory becomes a labeled box, packed left-to-right.
// mode = 'role': each architectural role becomes a full-width horizontal band,
//                stacked top-to-bottom in semantic order (high-level → low-level).
function layoutClusters(mode) {{
  const CLUSTER_PAD_X = 24;
  const CLUSTER_PAD_Y = 40; // top padding for cluster label
  const NODE_GAP_X = 16;
  const NODE_GAP_Y = 14;
  const CLUSTER_GAP = 50;

  let clusterBoxes;

  if (mode === 'dir') {{
    // ── Directory mode: packed grid, same as before ───────────────────────
    const keys = Object.keys(CLUSTERS).sort();
    if (keys.length === 0) return;

    clusterBoxes = keys.map(dir => {{
      const ids = CLUSTERS[dir];
      const clNodes = ids.map(id => nodeIndex[id]).filter(Boolean);
      const count = clNodes.length;
      if (count === 0) return null;
      const cols = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(count))));
      const rows = Math.ceil(count / cols);
      const cellW = Math.max(...clNodes.map(n => n.w));
      const cellH = Math.max(...clNodes.map(n => n.h));
      const innerW = cols * cellW + (cols - 1) * NODE_GAP_X;
      const innerH = rows * cellH + (rows - 1) * NODE_GAP_Y;
      return {{
        dir, clNodes, cols, rows, cellW, cellH,
        boxW: innerW + CLUSTER_PAD_X * 2,
        boxH: innerH + 40 + CLUSTER_PAD_X,  // 40 = header with label only
      }};
    }}).filter(Boolean);

    const startX = 60, startY = 60;
    const wrapW = Math.max(800, canvas.width - 120);
    let cx = startX, cy = startY, rowH = 0;
    for (const cb of clusterBoxes) {{
      if (cx + cb.boxW > startX + wrapW && cx > startX) {{
        cx = startX; cy += rowH + CLUSTER_GAP; rowH = 0;
      }}
      cb.x = cx; cb.y = cy;
      rowH = Math.max(rowH, cb.boxH);
      cx += cb.boxW + CLUSTER_GAP;
    }}

  }} else {{
    // ── Role/Purpose mode: full-width horizontal bands stacked vertically ─
    const labelMap = {{
      'entry_point': 'Entry Points', 'api_route': 'API Layer',
      'data_model': 'Data Models', 'utility': 'Utilities',
      'config': 'Configuration', 'test': 'Tests', 'other': 'Other',
    }};
    const orderedLabels = ROLE_ORDER.map(roleKey => labelMap[roleKey] || roleKey)
      .filter(label => CLUSTERS_BY_ROLE[label] && CLUSTERS_BY_ROLE[label].length > 0);

    const canvasW = Math.max(canvas.width, 900);
    const bandW = canvasW - 120;
    const HEADER_H = 56; // title (16px) + subtitle (12px) + padding
    const startX = 60, startY = 60;
    let cy = startY;

    clusterBoxes = orderedLabels.map(label => {{
      const ids = CLUSTERS_BY_ROLE[label] || [];
      // Sort nodes by pagerank descending — most central/important appears first
      const clNodes = ids.map(id => nodeIndex[id]).filter(Boolean)
        .sort((a, b) => (b.pagerank || 0) - (a.pagerank || 0));
      const count = clNodes.length;
      if (count === 0) return null;

      const cellW = Math.max(...clNodes.map(n => n.w));
      const cellH = Math.max(...clNodes.map(n => n.h));
      const maxCols = Math.max(1, Math.floor((bandW - CLUSTER_PAD_X * 2 + NODE_GAP_X) / (cellW + NODE_GAP_X)));
      const cols = Math.min(maxCols, count);
      const rows = Math.ceil(count / cols);
      const innerH = rows * cellH + (rows - 1) * NODE_GAP_Y;
      const cb = {{
        dir: label,
        clNodes, cols, rows, cellW, cellH,
        x: startX, y: cy,
        boxW: bandW,
        boxH: innerH + HEADER_H + CLUSTER_PAD_X,
        headerH: HEADER_H,
      }};
      cy += cb.boxH + CLUSTER_GAP;
      return cb;
    }}).filter(Boolean);
  }}

  // Position each node inside its cluster box (same for both modes)
  for (const cb of clusterBoxes) {{
    const headerH = cb.headerH || CLUSTER_PAD_Y;
    cb.clNodes.forEach((n, i) => {{
      const col = i % cb.cols;
      const row = Math.floor(i / cb.cols);
      n.x = cb.x + CLUSTER_PAD_X + col * (cb.cellW + NODE_GAP_X) + cb.cellW / 2;
      n.y = cb.y + headerH + row * (cb.cellH + NODE_GAP_Y) + cb.cellH / 2;
      n.vx = 0; n.vy = 0;
      n.pinned = true;
    }});
  }}

  // Center the whole layout in the viewport
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {{
    minX = Math.min(minX, n.x - n.w / 2);
    minY = Math.min(minY, n.y - n.h / 2);
    maxX = Math.max(maxX, n.x + n.w / 2);
    maxY = Math.max(maxY, n.y + n.h / 2);
  }}
  const layoutW = maxX - minX, layoutH = maxY - minY;
  pan.x = (canvas.width - layoutW * zoom) / 2 - minX * zoom;
  pan.y = (canvas.height - layoutH * zoom) / 2 - minY * zoom;

  window.__clusterBoxes = clusterBoxes;

  // Build nodeId → clusterBox map for edge routing
  window.__nodeClusterMap = new Map();
  for (const cb of clusterBoxes) {{
    for (const n of cb.clNodes) window.__nodeClusterMap.set(n.id, cb);
  }}
}}

// Alias kept for any direct callers
function layoutClustersAsGrid() {{ layoutClusters('dir'); }}

// ── Layout ──────────────────────────────────────────────────────────────────

function resize() {{
  canvas.width = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;
}}
window.addEventListener('resize', () => {{ resize(); draw(); }});
resize();

// ── Force simulation ─────────────────────────────────────────────────────────

const NODE_W = 220, NODE_H_BASE = 44, NODE_R = 6;
// Taller nodes need more space — bump repulsion and spring length
const REPULSION = 12000, SPRING_LEN = 280, SPRING_K = 0.04, GRAVITY = 0.012, DAMPING = 0.85;

// Dynamic height: base + 16px per symbol shown (max 4), plus 10px for dividers
function nodeHeight(n) {{
  const symCount = Math.min((n.symbols || []).length, 4);
  return NODE_H_BASE + symCount * 16 + (symCount > 0 ? 10 : 0);
}}

// ── Topology-aware initial placement ─────────────────────────────────────────
// BFS from sources (indegree=0) assigns each node a "depth layer".
// Layer 0 = entry points / test files (nothing imports them).
// Layer N = core modules (imported by many).
// Nodes start on a grid organised left→right by layer, so connected nodes
// begin close together and the simulation has much less work to do.
(function computeInitialPositions() {{
  const inDeg = {{}}, adj = {{}};
  for (const n of GRAPH.nodes) {{ inDeg[n.id] = 0; adj[n.id] = []; }}
  for (const e of GRAPH.edges) {{
    if (inDeg[e.target] !== undefined) inDeg[e.target]++;
    if (adj[e.source]) adj[e.source].push(e.target);
  }}
  // BFS — assign layers
  const layer = {{}};
  const queue = GRAPH.nodes.filter(n => inDeg[n.id] === 0).map(n => n.id);
  queue.forEach(id => {{ layer[id] = 0; }});
  for (let i = 0; i < queue.length; i++) {{
    const id = queue[i];
    for (const child of adj[id]) {{
      if (layer[child] === undefined || layer[child] < layer[id] + 1) {{
        layer[child] = layer[id] + 1;
        queue.push(child);
      }}
    }}
  }}
  // Nodes in cycles never reached — assign to layer 0 with jitter
  for (const n of GRAPH.nodes) if (layer[n.id] === undefined) layer[n.id] = 0;

  // Group by layer
  const maxLayer = Math.max(0, ...Object.values(layer));
  const byLayer = {{}};
  for (let l = 0; l <= maxLayer; l++) byLayer[l] = [];
  for (const n of GRAPH.nodes) byLayer[layer[n.id]].push(n.id);

  // Store positions on GRAPH nodes so the map below can read them
  const cw = Math.max(canvas.width, 800), ch = Math.max(canvas.height, 600);
  const padX = 120, padY = 80;
  for (let l = 0; l <= maxLayer; l++) {{
    const ids = byLayer[l];
    const lx = maxLayer === 0 ? cw / 2 : padX + (l / maxLayer) * (cw - padX * 2);
    ids.forEach((id, i) => {{
      const ly = padY + ((i + 0.5) / ids.length) * (ch - padY * 2);
      const gn = GRAPH.nodes.find(n => n.id === id);
      if (gn) {{ gn._ix = lx + (Math.random() - 0.5) * 30; gn._iy = ly + (Math.random() - 0.5) * 30; }}
    }});
  }}
}})();

const nodes = GRAPH.nodes.map(n => ({{
  ...n,
  x: n._ix !== undefined ? n._ix : canvas.width / 2 + (Math.random() - 0.5) * 400,
  y: n._iy !== undefined ? n._iy : canvas.height / 2 + (Math.random() - 0.5) * 300,
  vx: 0, vy: 0,
  fx: 0, fy: 0,
  pinned: false,
}}));

const nodeIndex = {{}};
nodes.forEach(n => {{ nodeIndex[n.id] = n; }});

// Expanded card layout: description + symbols + footer.
// Width fixed at NODE_W; height is dynamic based on symbol count.
const maxIndegree = Math.max(1, ...nodes.map(n => NODE_METRICS[n.id]?.indegree || 0));
nodes.forEach(n => {{
  const m = NODE_METRICS[n.id] || {{}};
  n.w = NODE_W;
  n.h = nodeHeight(n); // dynamic: base + symbols
  n.indegree = m.indegree || 0;
  n.outdegree = m.outdegree || 0;
  n.pagerank = m.pagerank || 0;
  n.inCycle = m.in_cycle || false;
}});

// Subtitle text for each card footer: "filename · role · size"
function nodeSubtitle(n) {{
  const parts = [];
  parts.push(n.label); // filename always first in footer
  if (n.role) parts.push(n.role.replace(/_/g, '\u00a0'));
  if (n.size) parts.push((n.size / 1024).toFixed(1) + '\u00a0KB');
  return parts.join(' \u00b7 ');
}}

// Primary title text — natural language preferred over filename
const _ROLE_HINTS = {{
  entry_point: 'Program entry', api_route: 'API\u00a0route',
  data_model: 'Data\u00a0model', utility: 'Helper\u00a0module',
  config: 'Configuration', test: 'Test\u00a0suite',
}};
function nodeTitleText(n) {{
  if (n.description) return n.description;
  // No description: build something meaningful from role + symbol names
  const roleHint = _ROLE_HINTS[n.role] || 'Module';
  const topSyms = (n.symbols || [])
    .filter(s => s.kind === 'function' || s.kind === 'class')
    .slice(0, 3).map(s => s.name).join(', ');
  return topSyms ? roleHint + ': ' + topSyms : roleHint;
}}

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

  // Cluster gravity — attract nodes to their cluster centroid
  if (showClusters()) {{
    const CLUSTER_GRAVITY = 0.025;
    const activeClusters = clusterMode === 'role' ? CLUSTERS_BY_ROLE : CLUSTERS;
    for (const [, ids] of Object.entries(activeClusters)) {{
      const clNodes = ids.map(id => nodeIndex[id]).filter(Boolean);
      if (clNodes.length < 2) continue;
      const cx = clNodes.reduce((s, n) => s + n.x, 0) / clNodes.length;
      const cy = clNodes.reduce((s, n) => s + n.y, 0) / clNodes.length;
      for (const n of clNodes) {{
        n.fx += (cx - n.x) * CLUSTER_GRAVITY;
        n.fy += (cy - n.y) * CLUSTER_GRAVITY;
      }}
    }}
  }}

  // Collision detection — push overlapping nodes apart based on actual size
  for (let i = 0; i < nodes.length; i++) {{
    for (let j = i + 1; j < nodes.length; j++) {{
      const a = nodes[i], b = nodes[j];
      const dx = b.x - a.x, dy = b.y - a.y;
      const minSepX = (a.w + b.w) / 2 + 12;
      const minSepY = (a.h + b.h) / 2 + 12;
      const overlapX = minSepX - Math.abs(dx);
      const overlapY = minSepY - Math.abs(dy);
      if (overlapX > 0 && overlapY > 0) {{
        const push = Math.min(overlapX, overlapY) * 1.1;
        const dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
        const fx = push * dx / dist, fy = push * dy / dist;
        a.fx -= fx; a.fy -= fy;
        b.fx += fx; b.fy += fy;
      }}
    }}
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
  if (simTicks > 800 || totalEnergy < 0.01) simRunning = false;
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
  if (!showClusters()) return;

  // Prefer the deterministic cluster boxes from layoutClusters if available
  const boxes = window.__clusterBoxes;
  if (boxes && boxes.length > 0) {{
    const isRole = clusterMode === 'role';
    boxes.forEach((cb, ci) => {{
      const color = CLUSTER_PALETTE[ci % CLUSTER_PALETTE.length];
      ctx.fillStyle = color;
      ctx.strokeStyle = color.replace('0.06', '0.35');
      ctx.lineWidth = 1.5 / zoom;
      roundRect(ctx, cb.x, cb.y, cb.boxW, cb.boxH, 14);
      ctx.fill();
      ctx.stroke();

      // Cluster label — prominent at top of box
      ctx.fillStyle = '#e6edf3';
      ctx.font = `bold ${{15 / zoom}}px -apple-system, sans-serif`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      const displayLabel = isRole ? cb.dir : (cb.dir + '/');
      ctx.fillText(displayLabel, cb.x + 16, cb.y + 12);

      // File count
      ctx.fillStyle = '#8b949e';
      ctx.font = `${{10 / zoom}}px "SF Mono", monospace`;
      const countText = cb.clNodes.length + ' file' + (cb.clNodes.length === 1 ? '' : 's');
      const labelW = ctx.measureText(displayLabel).width;
      ctx.fillText(countText, cb.x + 16 + labelW + 8, cb.y + 16);

      // Role mode: subtitle (what this group means in plain language)
      if (isRole) {{
        const roleKeyMap = {{
          'Entry Points': 'entry_point', 'API Layer': 'api_route',
          'Data Models': 'data_model', 'Utilities': 'utility',
          'Configuration': 'config', 'Tests': 'test', 'Other': 'other',
        }};
        const roleKey = roleKeyMap[cb.dir] || 'other';
        const subtitle = ROLE_SUBTITLES[roleKey] || '';
        if (subtitle) {{
          ctx.fillStyle = '#6e7681';
          ctx.font = `${{11 / zoom}}px -apple-system, sans-serif`;
          ctx.fillText(subtitle, cb.x + 16, cb.y + 31);
        }}
      }}

      // High/low level indicators on first and last box — larger and more visible
      if (isRole && boxes.length > 1) {{
        const indicatorY = cb.y + (isRole ? 13 : 13);
        ctx.textAlign = 'right';
        if (ci === 0) {{
          ctx.fillStyle = '#58a6ff';
          ctx.font = `bold ${{11 / zoom}}px -apple-system, sans-serif`;
          ctx.fillText('\u2191 HIGH LEVEL', cb.x + cb.boxW - 16, cb.y + 12);
        }}
        if (ci === boxes.length - 1) {{
          ctx.fillStyle = '#a78bfa';
          ctx.font = `bold ${{11 / zoom}}px -apple-system, sans-serif`;
          ctx.fillText('\u2193 LOW LEVEL', cb.x + cb.boxW - 16, cb.y + 12);
        }}
        ctx.textAlign = 'left';
      }}
    }});
    return;
  }}

  // Fallback: bounding box around nodes (used if grid layout hasn't run)
  const clusterKeys = Object.keys(CLUSTERS);
  clusterKeys.forEach((dir, ci) => {{
    const clusterNodeIds = CLUSTERS[dir];
    const clusterNodes = clusterNodeIds.map(id => nodeIndex[id]).filter(Boolean);
    if (clusterNodes.length < 2) return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of clusterNodes) {{
      minX = Math.min(minX, n.x - n.w / 2);
      minY = Math.min(minY, n.y - n.h / 2);
      maxX = Math.max(maxX, n.x + n.w / 2);
      maxY = Math.max(maxY, n.y + n.h / 2);
    }}

    const pad = 20;
    const color = CLUSTER_PALETTE[ci % CLUSTER_PALETTE.length];
    ctx.fillStyle = color;
    ctx.strokeStyle = color.replace('0.06', '0.2');
    ctx.lineWidth = 1 / zoom;
    roundRect(ctx, minX - pad, minY - pad, maxX - minX + pad * 2, maxY - minY + pad * 2, 12);
    ctx.fill();
    ctx.stroke();

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

  // Pre-compute bidirectional pairs once per draw call
  const edgeKeySet = new Set(GRAPH.edges.map(e => e.source + '|' + e.target));

  // Draw arrowhead at (x2,y2) arriving from direction (x1,y1)
  function drawArrowHead(x1, y1, x2, y2, color, arrowSize) {{
    const angle = Math.atan2(y2 - y1, x2 - x1);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - arrowSize * Math.cos(angle - 0.42), y2 - arrowSize * Math.sin(angle - 0.42));
    ctx.lineTo(x2 - arrowSize * Math.cos(angle + 0.42), y2 - arrowSize * Math.sin(angle + 0.42));
    ctx.closePath();
    ctx.fill();
  }}

  function drawArrow(x1, y1, x2, y2, color, lw, arrowSize) {{
    const angle = Math.atan2(y2 - y1, x2 - x1);
    const tx = x2 - Math.cos(angle) * arrowSize * 0.6;
    const ty = y2 - Math.sin(angle) * arrowSize * 0.6;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(tx, ty);
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.stroke();
    drawArrowHead(x1, y1, x2, y2, color, arrowSize);
  }}

  // Deterministic hash → consistent lane index per edge pair
  function edgeLaneIndex(a, b) {{
    const N_LANES = 8;
    let h = 5381;
    for (let i = 0; i < a.id.length; i++) h = ((h << 5) + h + a.id.charCodeAt(i)) & 0x7fffffff;
    for (let i = 0; i < b.id.length; i++) h = ((h << 5) + h + b.id.charCodeAt(i)) & 0x7fffffff;
    return h % N_LANES;
  }}

  // Route an edge as a bezier curve that exits LEFT from source, travels down
  // a lane in the LEFT MARGIN (between x=8 and cluster left edge-8), then
  // enters LEFT into target. Lanes are spread evenly across the margin width.
  function drawRoutedEdge(a, b, color, lw, arrowSize) {{
    const boxes = window.__clusterBoxes || [];
    const clusterLeft = boxes.length > 0 ? boxes[0].x : 60;
    const marginRight = clusterLeft - 6;  // just left of cluster band
    const marginLeft = 8;                  // left edge of canvas
    const N_LANES = 8;
    const lane = edgeLaneIndex(a, b);
    const laneX = marginLeft + (lane / (N_LANES - 1)) * (marginRight - marginLeft);
    const sx = a.x - a.w / 2;
    const sy = a.y;
    const ex = b.x - b.w / 2;
    const ey = b.y;
    // S-curve: exit source horizontally → down the lane → enter target horizontally
    const cp1x = laneX, cp1y = sy;
    const cp2x = laneX, cp2y = ey;
    const endX = ex - arrowSize * 0.6;
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, endX, ey);
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.stroke();
    drawArrowHead(cp2x, cp2y, ex, ey, color, arrowSize);
  }}

  const nodeClusterMap = window.__nodeClusterMap;

  // Edges
  for (const e of edges) {{
    const a = e.source, b = e.target;
    const vis = isVisible(a) && isVisible(b);
    if (!vis) continue;

    // Only show an edge if the focal node (selected or hovered) is one of its endpoints.
    // Using highlightSet membership would also light up edges between neighbors, which is noisy.
    const focalId = selectedNode ? selectedNode.id : (hoveredNode ? hoveredNode.id : null);
    const isDirect = focalId && (a.id === focalId || b.id === focalId);
    const inHighlight = isDirect; // kept for opacity logic below
    const faded = highlightSet && !isDirect && !(highlightSet.has(a.id) && highlightSet.has(b.id));

    // Hover mode: only draw edges when a node is selected/hovered
    if (edgeMode === 'hover' && !isDirect) continue;

    const isCycle = isCycleEdge(e);
    const isBidi = edgeKeySet.has(b.id + '|' + a.id);

    // Opacity: highlighted edges bright, others very faint in all-mode
    let alpha;
    if (faded) alpha = 0.04;
    else if (inHighlight) alpha = isCycle ? 0.95 : 0.85;
    else alpha = isCycle ? 0.6 : 0.22; // all-mode, no selection
    ctx.globalAlpha = alpha;

    const edgeColor = isCycle ? '#f85149' : '#6b7280';
    const lw = (isCycle ? 2 : 1.5) / zoom;
    const as = (isCycle ? 9 : 8) / zoom;

    // In role cluster mode: route inter-band edges via left margin
    if (clusterMode === 'role' && nodeClusterMap) {{
      const aBox = nodeClusterMap.get(a.id);
      const bBox = nodeClusterMap.get(b.id);
      if (aBox && bBox && aBox !== bBox) {{
        // Different cluster bands — route around them
        drawRoutedEdge(a, b, edgeColor, lw, as);
        continue;
      }}
    }}

    const angle = Math.atan2(b.y - a.y, b.x - a.x);
    if (isBidi) {{
      const ox = Math.sin(angle) * 5 / zoom;
      const oy = -Math.cos(angle) * 5 / zoom;
      drawArrow(a.x + ox, a.y + oy, b.x + ox, b.y + oy, edgeColor, lw, as);
    }} else {{
      const ex = b.x - Math.cos(angle) * (b.w / 2 + 2);
      const ey = b.y - Math.sin(angle) * (b.h / 2 + 2);
      drawArrow(a.x, a.y, ex, ey, edgeColor, lw, as);
    }}
  }}

  ctx.globalAlpha = 1;

  // Nodes
  for (const n of nodes) {{
    if (!isVisible(n)) continue;
    const faded = highlightSet && !highlightSet.has(n.id);
    ctx.globalAlpha = faded ? 0.15 : 1;

    const nw = n.w, nh = n.h;
    const x = n.x - nw / 2, y = n.y - nh / 2;
    const color = nodeColor(n);
    const isSelected = selectedNode === n;
    const isHovered = hoveredNode === n;
    const inCycle = n.inCycle;

    // Shadow for selected/hovered
    if (isSelected || isHovered) {{
      ctx.shadowColor = color;
      ctx.shadowBlur = (isSelected ? 14 : 6) / zoom;
    }}

    // Rounded rect
    ctx.fillStyle = isSelected ? color : (isHovered ? '#21262d' : '#161b22');
    ctx.strokeStyle = inCycle ? '#f85149' : (isSelected ? color : (isHovered ? color : '#30363d'));
    ctx.lineWidth = (inCycle ? 2 : isSelected ? 2 : 1) / zoom;
    roundRect(ctx, x, y, nw, nh, NODE_R);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Language indicator (left bar)
    if (!isSelected) {{
      ctx.fillStyle = color;
      roundRect(ctx, x, y, 4, nh, {{ tl: NODE_R, bl: NODE_R, tr: 0, br: 0 }});
      ctx.fill();
    }}

    // Cycle indicator (right bar, red)
    if (inCycle && !isSelected) {{
      ctx.fillStyle = '#f85149';
      roundRect(ctx, x + nw - 4, y, 4, nh, {{ tl: 0, bl: 0, tr: NODE_R, br: NODE_R }});
      ctx.fill();
    }}

    // LOD: skip text if card is too small on screen (< 55px wide)
    // This keeps the graph clean when zoomed out.
    if (nw * zoom < 55) {{
      // Draw just a tiny label for identification
      if (nw * zoom >= 28) {{
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.font = `bold 9px -apple-system, sans-serif`;
        ctx.fillStyle = '#8b949e';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(n.label.replace(/\.(py|js|ts)$/, ''), n.x * zoom + pan.x, n.y * zoom + pan.y);
        ctx.restore();
      }}
      continue;
    }}

    // Clip ALL text drawing to the card rectangle — prevents overflow onto adjacent cards
    // Text is drawn in SCREEN SPACE (constant 12px size regardless of zoom).
    const screenX = n.x * zoom + pan.x;
    const screenY = n.y * zoom + pan.y;
    const screenW = nw * zoom;
    const screenH = nh * zoom;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0); // reset to screen coords
    ctx.beginPath();
    roundRect(ctx, screenX - screenW/2 + 1, screenY - screenH/2 + 1, screenW - 2, screenH - 2, NODE_R * zoom);
    ctx.clip();

    // 4-section card layout:
    //   Section 1: description (or label if no description) — primary text
    //   Divider
    //   Section 2: symbol list (function/class names, colored by kind)
    //   Divider
    //   Section 3: filename · role · size (footer, muted)
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    const textColor = isSelected ? nodeTextColor(n) : '#e6edf3';
    const mutedColor = isSelected ? 'rgba(255,255,255,0.7)' : '#8b949e';
    const symFnColor  = isSelected ? 'rgba(255,255,255,0.9)' : '#c084fc';
    const symClsColor = isSelected ? 'rgba(255,255,255,0.9)' : '#93c5fd';
    const divColor    = isSelected ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.08)';

    // All drawing is in screen space (setTransform reset above).
    // innerW/positions in screen px — font sizes are fixed (not /zoom).
    const padding = 8;
    const innerW = screenW - padding * 2;

    // ── Section 1: description / title ───────────────────────────────────
    const titleText = nodeTitleText(n);
    ctx.font = `bold 12px -apple-system, sans-serif`;
    const maxLineW = innerW - 4;
    const words = titleText.split(' ');
    let line1 = '', line2 = '';
    for (const word of words) {{
      const test = line1 ? line1 + ' ' + word : word;
      if (ctx.measureText(test).width <= maxLineW) {{
        line1 = test;
      }} else if (!line2) {{
        line2 = word;
      }} else {{
        const test2 = line2 + ' ' + word;
        if (ctx.measureText(test2).width <= maxLineW) {{
          line2 = test2;
        }} else {{
          while (line2 && ctx.measureText(line2 + '\u2026').width > maxLineW) {{
            line2 = line2.slice(0, -1);
          }}
          line2 += '\u2026';
          break;
        }}
      }}
    }}

    const syms = (n.symbols || []).slice(0, 4);
    const hasSyms = syms.length > 0;
    // Top of text content in screen px (NODE_R * zoom = border radius in screen px)
    let curY = screenY - screenH / 2 + NODE_R * zoom + 6;

    // Title line(s)
    ctx.fillStyle = textColor;
    ctx.font = `bold 12px -apple-system, sans-serif`;
    ctx.textBaseline = 'top';
    ctx.textAlign = 'center';
    ctx.fillText(line1, screenX, curY);
    curY += 14;
    if (line2) {{
      ctx.fillText(line2, screenX, curY);
      curY += 14;
    }}
    curY += 4;

    if (hasSyms) {{
      // ── Divider ─────────────────────────────────────────────────────────
      ctx.strokeStyle = divColor;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(screenX - screenW / 2 + padding, curY);
      ctx.lineTo(screenX + screenW / 2 - padding, curY);
      ctx.stroke();
      curY += 5;

      // ── Section 2: symbol list ──────────────────────────────────────────
      ctx.textAlign = 'left';
      for (const s of syms) {{
        const icon = s.kind === 'function' ? '\u0192' : s.kind === 'class' ? '\u25c6' : '\u00b7';
        ctx.font = `10px "SF Mono", monospace`;
        ctx.fillStyle = s.kind === 'function' ? symFnColor : s.kind === 'class' ? symClsColor : mutedColor;
        const nameText = icon + ' ' + s.name;
        ctx.fillText(nameText, screenX - screenW / 2 + padding + 2, curY);
        const nameW = ctx.measureText(nameText).width;
        if (s.description) {{
          ctx.font = `9px -apple-system, sans-serif`;
          ctx.fillStyle = mutedColor;
          const sep = ' \u2014 ';
          const sepW = ctx.measureText(sep).width;
          const availW = innerW - 8 - nameW - sepW;
          if (availW > 20) {{
            const maxDescChars = Math.floor(availW / 5.5);
            const descText = s.description.length > maxDescChars
              ? s.description.slice(0, maxDescChars - 1) + '\u2026'
              : s.description;
            ctx.fillText(sep + descText, screenX - screenW / 2 + padding + 2 + nameW, curY);
          }}
        }}
        curY += 13;
      }}
      curY += 3;
    }}

    // ── Bottom divider + footer ──────────────────────────────────────────
    ctx.strokeStyle = divColor;
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(screenX - screenW / 2 + padding, screenY + screenH / 2 - 18);
    ctx.lineTo(screenX + screenW / 2 - padding, screenY + screenH / 2 - 18);
    ctx.stroke();

    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.fillStyle = mutedColor;
    ctx.font = `9px "SF Mono", monospace`;
    const footer = nodeSubtitle(n);
    if (footer) {{
      const footerMaxW = Math.floor(innerW / 5.5);
      const footerText = footer.length > footerMaxW ? footer.slice(0, footerMaxW - 1) + '\u2026' : footer;
      ctx.fillText(footerText, screenX, screenY + screenH / 2 - 5);
    }}
    ctx.restore(); // end card clip

    // Indegree badge on hub nodes (indegree >= 3) — top-right corner
    if (!isSelected && n.indegree >= 3) {{
      const badge = String(n.indegree);
      const bx = x + nw - 2, by = y - 2;
      ctx.fillStyle = '#58a6ff';
      ctx.font = `bold ${{9 / zoom}}px monospace`;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText(badge, bx, by);
    }}
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
    if (Math.abs(wx - n.x) <= n.w / 2 && Math.abs(wy - n.y) <= n.h / 2) return n;
  }}
  return null;
}}

canvas.addEventListener('mousedown', e => {{
  const {{ x: wx, y: wy }} = worldCoords(e.offsetX, e.offsetY);
  const n = nodeAt(wx, wy);
  dragging = true;
  if (n) {{
    // Click on node — select it, no drag
    dragNode = n;
  }} else {{
    // Click on empty space — pan the canvas
    dragStart = {{ x: e.offsetX, y: e.offsetY }};
    panStart = {{ ...pan }};
  }}
  canvas.classList.add('dragging');
}});

canvas.addEventListener('mousemove', e => {{
  const {{ x: wx, y: wy }} = worldCoords(e.offsetX, e.offsetY);
  if (dragging && dragNode) {{
    // No node dragging — just update cursor
  }} else if (dragging && dragStart) {{
    pan.x = panStart.x + (e.offsetX - dragStart.x);
    pan.y = panStart.y + (e.offsetY - dragStart.y);
    draw();
  }} else {{
    const prev = hoveredNode;
    hoveredNode = nodeAt(wx, wy);
    if (prev !== hoveredNode) draw();
    canvas.style.cursor = hoveredNode ? 'pointer' : 'grab';
  }}
}});

canvas.addEventListener('mouseup', e => {{
  if (dragging && dragNode) {{
    const {{ x: wx, y: wy }} = worldCoords(e.offsetX, e.offsetY);
    selectNode(dragNode);
    dragNode = null;
  }}
  dragging = false;
  dragStart = null;
  panStart = null;
  canvas.classList.remove('dragging');
}});

canvas.addEventListener('wheel', e => {{
  e.preventDefault();
  if (e.ctrlKey || e.metaKey) {{
    // Pinch gesture (trackpad) or Ctrl+scroll → zoom
    const factor = e.deltaY < 0 ? 1.08 : 0.93;
    const wx = (e.offsetX - pan.x) / zoom;
    const wy = (e.offsetY - pan.y) / zoom;
    zoom = Math.max(0.2, Math.min(2.5, zoom * factor));
    pan.x = e.offsetX - wx * zoom;
    pan.y = e.offsetY - wy * zoom;
  }} else {{
    // Two-finger scroll (trackpad) → pan
    pan.x -= e.deltaX * 1.2;
    pan.y -= e.deltaY * 1.2;
  }}
  draw();
}}, {{ passive: false }});

// ── Sidebar ──────────────────────────────────────────────────────────────────

function selectNode(n) {{
  if (egoMode) exitEgoMode();
  selectedNode = selectedNode === n ? null : n;
  if (selectedNode) {{
    highlightSet = nhopNeighborhood(n.id, 1);
    renderSidebar(n);
  }} else {{
    highlightSet = null;
    renderDefaultSidebar();
  }}
  draw();
  drawMinimap();
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

  const roleLabel = n.role ? n.role.replace(/_/g, ' ') : '';
  const rolePill = roleLabel ? `<span class="role-tag" style="background:${{ROLE_COLORS[n.role] || '#888'}}30;color:${{ROLE_COLORS[n.role] || '#888'}};margin-left:6px">${{roleLabel}}</span>` : '';

  // Code preview panel — first ~50 lines of the file, monospace, line-numbered.
  // Empty when --no-descriptions wasn't used or when the file couldn't be read.
  let codePanelHtml = '';
  if (n.preview) {{
    // Use String.fromCharCode(10) for newline so the Python template doesn't
    // turn the embedded \\n into a literal newline, breaking the JS string.
    const NL = String.fromCharCode(10);
    const lines = n.preview.split(NL);
    const numbered = lines.map((line, i) => {{
      const num = String(i + 1).padStart(3, ' ');
      return `<span class="ln">${{num}}</span>${{esc(line) || ' '}}`;
    }}).join(NL);
    codePanelHtml = `
      <div>
        <p class="section-title">Code preview</p>
        <pre class="code-preview"><code>${{numbered}}</code></pre>
      </div>
    `;
  }}

  sidebar.innerHTML = `
    <div>
      <h2>${{esc(n.label)}}</h2>
      <span style="font-size:11px;color:#6e7681;word-break:break-all">${{esc(n.id)}}</span>
      <div style="margin-top:4px;font-size:11px;color:#6e7681">${{esc(n.language || '')}} &middot; ${{(n.size/1024).toFixed(1)}} KB${{rolePill}}</div>
    </div>
    ${{inCycle ? '<div class="cycle-warning"><strong>\u26a0 In circular dependency</strong></div>' : ''}}
    ${{n.description ? `<p class="desc">${{esc(n.description)}}</p>` : '<p class="desc" style="color:#6e7681">No description. Run without --no-descriptions to generate.</p>'}}
    <div class="metrics-panel">
      ${{metricRow('Imported by', n.indegree + ' file' + (n.indegree !== 1 ? 's' : ''))}}
      ${{metricRow('Imports', n.outdegree + ' file' + (n.outdegree !== 1 ? 's' : ''))}}
      ${{metricRow('PageRank', n.pagerank.toFixed(4))}}
    </div>
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
    ${{codePanelHtml}}
    <div style="margin-top:8px">
      <button onclick="enterEgoMode(nodeIndex['${{esc(n.id)}}'])" style="padding:4px 10px;background:#21262d;border:1px solid #30363d;border-radius:6px;color:#58a6ff;font-size:11px;cursor:pointer;width:100%">
        Ego view (2-hop neighborhood)
      </button>
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

// ── Minimap ───────────────────────────────────────────────────────────────────

const minimap = document.getElementById('minimap');
const mctx = minimap.getContext('2d');

function drawMinimap() {{
  const mw = minimap.width, mh = minimap.height;
  mctx.clearRect(0, 0, mw, mh);
  mctx.fillStyle = '#0d1117';
  mctx.fillRect(0, 0, mw, mh);

  if (nodes.length === 0) return;

  // Compute world bounds
  let wx0 = Infinity, wy0 = Infinity, wx1 = -Infinity, wy1 = -Infinity;
  for (const n of nodes) {{
    wx0 = Math.min(wx0, n.x - n.w / 2);
    wy0 = Math.min(wy0, n.y - n.h / 2);
    wx1 = Math.max(wx1, n.x + n.w / 2);
    wy1 = Math.max(wy1, n.y + n.h / 2);
  }}
  const wspan = Math.max(wx1 - wx0, 1), hspan = Math.max(wy1 - wy0, 1);
  const pad = 8;
  const scaleX = (mw - pad * 2) / wspan, scaleY = (mh - pad * 2) / hspan;
  const sc = Math.min(scaleX, scaleY);
  const offX = pad + (mw - pad * 2 - wspan * sc) / 2 - wx0 * sc;
  const offY = pad + (mh - pad * 2 - hspan * sc) / 2 - wy0 * sc;

  // Draw nodes
  for (const n of nodes) {{
    const faded = highlightSet && !highlightSet.has(n.id);
    mctx.globalAlpha = faded ? 0.2 : 0.8;
    mctx.fillStyle = nodeColor(n);
    const mx = n.x * sc + offX, my = n.y * sc + offY;
    const rw = Math.max(2, n.w * sc), rh = Math.max(2, n.h * sc);
    mctx.fillRect(mx - rw / 2, my - rh / 2, rw, rh);
  }}
  mctx.globalAlpha = 1;

  // Viewport indicator
  const vx0 = (-pan.x) / zoom, vy0 = (-pan.y) / zoom;
  const vx1 = (canvas.width - pan.x) / zoom, vy1 = (canvas.height - pan.y) / zoom;
  mctx.strokeStyle = 'rgba(88,166,255,0.6)';
  mctx.lineWidth = 1;
  mctx.strokeRect(
    vx0 * sc + offX, vy0 * sc + offY,
    (vx1 - vx0) * sc, (vy1 - vy0) * sc
  );
}}

minimap.addEventListener('click', e => {{
  const mw = minimap.width, mh = minimap.height;
  if (nodes.length === 0) return;
  let wx0 = Infinity, wy0 = Infinity, wx1 = -Infinity, wy1 = -Infinity;
  for (const n of nodes) {{
    wx0 = Math.min(wx0, n.x); wy0 = Math.min(wy0, n.y);
    wx1 = Math.max(wx1, n.x); wy1 = Math.max(wy1, n.y);
  }}
  const wspan = Math.max(wx1 - wx0, 1), hspan = Math.max(wy1 - wy0, 1);
  const pad = 8;
  const sc = Math.min((mw - pad * 2) / wspan, (mh - pad * 2) / hspan);
  const offX = pad + (mw - pad * 2 - wspan * sc) / 2 - wx0 * sc;
  const offY = pad + (mh - pad * 2 - hspan * sc) / 2 - wy0 * sc;
  const worldX = (e.offsetX - offX) / sc;
  const worldY = (e.offsetY - offY) / sc;
  pan.x = canvas.width / 2 - worldX * zoom;
  pan.y = canvas.height / 2 - worldY * zoom;
  draw();
}});

// ── Ego-centric mode ──────────────────────────────────────────────────────────

let egoMode = false;

function nhopNeighborhood(nodeId, hops) {{
  const visited = new Set([nodeId]);
  let frontier = [nodeId];
  for (let h = 0; h < hops; h++) {{
    const next = [];
    for (const id of frontier) {{
      for (const e of GRAPH.edges) {{
        if (e.source === id && !visited.has(e.target)) {{ visited.add(e.target); next.push(e.target); }}
        if (e.target === id && !visited.has(e.source)) {{ visited.add(e.source); next.push(e.source); }}
      }}
    }}
    frontier = next;
  }}
  return visited;
}}

function enterEgoMode(n) {{
  egoMode = true;
  highlightSet = nhopNeighborhood(n.id, 2);
  document.getElementById('ego-banner').style.display = 'block';
  draw();
}}

function exitEgoMode() {{
  egoMode = false;
  highlightSet = selectedNode ? nhopNeighborhood(selectedNode.id, 1) : null;
  document.getElementById('ego-banner').style.display = 'none';
  draw();
}}

canvas.addEventListener('dblclick', e => {{
  const {{ x: wx, y: wy }} = worldCoords(e.offsetX, e.offsetY);
  const n = nodeAt(wx, wy);
  if (n) {{
    selectNode(n);
    enterEgoMode(n);
  }}
}});

// ── Keyboard shortcuts ────────────────────────────────────────────────────────

document.addEventListener('keydown', e => {{
  if (e.target.tagName === 'INPUT') {{
    if (e.key === 'Escape') {{ e.target.blur(); searchQuery = ''; draw(); }}
    return;
  }}
  switch (e.key) {{
    case '/':
      e.preventDefault();
      document.getElementById('search').focus();
      break;
    case 'Escape':
      if (egoMode) {{ exitEgoMode(); }}
      else {{ selectedNode = null; highlightSet = null; renderDefaultSidebar(); draw(); }}
      break;
    case 'e': case 'E':
      if (selectedNode) enterEgoMode(selectedNode);
      break;
    case 'f': case 'F':
      zoomToFit();
      break;
    case 'c': case 'C':
      toggleClusters();
      break;
    case '?':
      toggleHelp();
      break;
  }}
}});

// ── Zoom to fit ───────────────────────────────────────────────────────────────

function zoomToFit() {{
  if (nodes.length === 0) return;
  let wx0 = Infinity, wy0 = Infinity, wx1 = -Infinity, wy1 = -Infinity;
  for (const n of nodes) {{
    wx0 = Math.min(wx0, n.x - n.w / 2);
    wy0 = Math.min(wy0, n.y - n.h / 2);
    wx1 = Math.max(wx1, n.x + n.w / 2);
    wy1 = Math.max(wy1, n.y + n.h / 2);
  }}
  const pad = 40;
  const zx = (canvas.width - pad * 2) / (wx1 - wx0);
  const zy = (canvas.height - pad * 2) / (wy1 - wy0);
  zoom = Math.min(zx, zy, 2);
  pan.x = canvas.width / 2 - ((wx0 + wx1) / 2) * zoom;
  pan.y = canvas.height / 2 - ((wy0 + wy1) / 2) * zoom;
  draw();
}}

// ── Help overlay ──────────────────────────────────────────────────────────────

function toggleHelp() {{
  const el = document.getElementById('help-overlay');
  el.style.display = el.style.display === 'block' ? 'none' : 'block';
}}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function renderStatsBar() {{
  const sb = document.getElementById('statsbar');
  if (!METRICS) return;

  // Entry point (where the program starts)
  const entryNodes = nodes.filter(n => n.role === 'entry_point');
  const startFile = entryNodes.length > 0
    ? entryNodes.sort((a, b) => b.outdegree - a.outdegree)[0]
    : [...nodes].sort((a, b) => b.outdegree - a.outdegree)[0];

  // Most-imported file (the "backbone" other files depend on)
  const coreFile = [...nodes].sort((a, b) => b.indegree - a.indegree)[0];

  // Health / issues
  const cycles = METRICS.cycles || 0;
  const orphans = nodes.filter(n => n.indegree === 0 && n.outdegree === 0).length;

  let html = '';

  // "Start here" pill
  if (startFile) {{
    const desc = startFile.description
      ? startFile.description.split('.')[0] + '.'
      : 'entry point';
    html += `<div class="stat-group">
      <span class="stat-label">\u25b6 Start here</span>
      <span class="stat-value" style="cursor:pointer;color:#22c55e;text-decoration:underline dotted"
        onclick="selectNode(nodeIndex['${{startFile.id}}'])">${{startFile.label}}</span>
      <span class="stat-label" style="max-width:260px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${{esc(desc)}}</span>
    </div>`;
  }}

  // "Core file" pill (most depended on)
  if (coreFile && coreFile !== startFile && coreFile.indegree > 0) {{
    html += `<div class="stat-group">
      <span class="stat-label">\u2764 Core file</span>
      <span class="stat-value" style="cursor:pointer;color:#58a6ff;text-decoration:underline dotted"
        onclick="selectNode(nodeIndex['${{coreFile.id}}'])">${{coreFile.label}}</span>
      <span class="stat-label">${{coreFile.indegree}} file${{coreFile.indegree > 1 ? 's' : ''}} depend on it</span>
    </div>`;
  }}

  // Warnings
  if (cycles > 0) {{
    html += `<div class="stat-group"><span style="color:#f85149">\u26a0 ${{cycles}} circular dependency${{cycles > 1 ? ' ies' : ''}} — files that import each other (can cause bugs)</span></div>`;
  }}
  if (orphans > 0) {{
    html += `<div class="stat-group"><span style="color:#f59e0b">\u26a0 ${{orphans}} unused file${{orphans > 1 ? 's' : ''}} — not imported anywhere</span></div>`;
  }}

  sb.innerHTML = html;
}}

// ── Animation loop ────────────────────────────────────────────────────────────

let animating = false;
let didInitialFit = false;
function loop() {{
  tickSim();
  draw();
  drawMinimap();
  if (simRunning || dragging) {{
    requestAnimationFrame(loop);
  }} else {{
    animating = false;
    // Auto-fit the viewport once the simulation has settled.
    // Bigger node cards in v2 land off-screen on first render without this.
    if (!didInitialFit) {{
      didInitialFit = true;
      zoomToFit();
    }}
    draw(); // final frame
    drawMinimap();
  }}
}}
function startAnim() {{
  if (!animating) {{ animating = true; loop(); }}
}}

// Initial sidebar with metrics
renderDefaultSidebar();
renderStatsBar();

// Initialize minimap size
minimap.width = 160;
minimap.height = 100;

// Start in "By Purpose" mode — hierarchical layout is the default view.
// Run layout before physics so nodes start in the right positions.
(function initLayout() {{
  const btn = document.getElementById('btnClusters');
  clusterMode = 'role';
  btn.textContent = 'By Purpose';
  btn.classList.add('active');
  layoutClusters('role');
  simRunning = false; // deterministic layout — no physics needed
  draw();
  drawMinimap();
  // Fit viewport after layout
  setTimeout(() => {{ zoomToFit(); draw(); drawMinimap(); }}, 50);
}})();
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

    # Use to_render_dict() for all analysis in one pass
    render_data = graph.to_render_dict()

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

    graph_json = _safe_json(render_data)  # full render dict includes nodes/edges + analysis
    colors_json = _safe_json(LANG_COLORS)
    text_colors_json = _safe_json(LANG_TEXT_COLORS)
    role_colors_json = _safe_json(ROLE_COLORS)
    cycle_nodes_json = _safe_json(render_data.get("cycle_node_ids", cycle_nodes))
    cycle_edges_json = _safe_json(cycle_edges_list)
    clusters_json = _safe_json(render_data.get("clusters", {}))
    clusters_by_role_json = _safe_json(render_data.get("clusters_by_role", {}))
    role_order_json = _safe_json(render_data.get("role_order", []))
    role_subtitles_json = _safe_json(render_data.get("role_subtitles", {}))
    metrics_json = _safe_json(render_data.get("metrics", {}))
    node_metrics_json = _safe_json(render_data.get("node_metrics", {}))
    health_json = _safe_json(render_data.get("health", {}))
    lang_counts_json = _safe_json(render_data.get("language_counts", {}))

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
        clusters_by_role_json=clusters_by_role_json,
        role_order_json=role_order_json,
        role_subtitles_json=role_subtitles_json,
        metrics_json=metrics_json,
        node_metrics_json=node_metrics_json,
        health_json=health_json,
        lang_counts_json=lang_counts_json,
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
