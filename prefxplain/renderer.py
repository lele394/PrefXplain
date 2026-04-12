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
    "c":          "#555555",  # C grey
    "c++":        "#f34b7d",  # C++ pink
    "go":         "#00ADD8",  # Go cyan
    "rust":       "#DEA584",  # Rust orange
    "java":       "#b07219",  # Java brown
    "kotlin":     "#A97BFF",  # Kotlin purple
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
  :root {{ --viewport-height: 100vh; --top-panel-header-height: 32px; --top-details-height: 200px; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: var(--viewport-height); min-height: var(--viewport-height); max-height: var(--viewport-height); width: 100%; overflow: hidden; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0d1117; color: #c9d1d9; display: flex; flex-direction: column; min-height: 0; max-height: var(--viewport-height); }}

  /* ── Top panel (collapsible, vertical content, full width) ──────────── */
  #left-panel {{ width: 100%; height: calc(var(--top-panel-header-height) + var(--top-details-height)); max-height: calc(var(--top-panel-header-height) + var(--top-details-height)); background: #161b22; border-bottom: 1px solid #30363d; display: flex; flex-direction: column; flex-shrink: 0; overflow: hidden; transition: height .2s ease, max-height .2s ease; }}
  #left-panel.collapsed {{ height: 0; max-height: 0; border-bottom: none; }}
  /* Compact header bar: brand, stats, search, buttons — single strip */
  #panel-header {{ display: flex; align-items: center; gap: 8px; padding: 5px 12px; border-bottom: 1px solid #21262d; flex-shrink: 0; flex-wrap: nowrap; overflow: hidden; }}
  #panel-header .ph-brand {{ font-size: 11px; font-weight: 700; color: #58a6ff; white-space: nowrap; }}
  #panel-header .ph-sep {{ width: 1px; height: 16px; background: #30363d; flex-shrink: 0; }}
  #panel-header .ph-stat {{ font-size: 11px; color: #8b949e; white-space: nowrap; }}
  #panel-header .ph-stat b {{ color: #e6edf3; font-weight: 600; }}
  #panel-header .ph-search {{ width: 130px; min-width: 80px; padding: 3px 8px; background: #0d1117; border: 1px solid #30363d; border-radius: 5px; color: #c9d1d9; font-size: 11px; outline: none; flex-shrink: 1; }}
  #panel-header .ph-search:focus {{ border-color: #58a6ff; }}
  #panel-header .ph-spacer {{ flex: 1; }}
  #panel-header button {{ padding: 2px 7px; background: #21262d; border: 1px solid #30363d; border-radius: 5px; color: #c9d1d9; font-size: 10px; cursor: pointer; white-space: nowrap; }}
  #panel-header button:hover {{ background: #30363d; }}
  #panel-header button.active {{ background: #58a6ff; color: #0d1117; border-color: #58a6ff; }}

  /* ── Toggle button (horizontal bar below top panel) ──────────────── */
  #panel-resizer {{ position: relative; z-index: 15; display: flex; align-items: center; gap: 10px; padding: 0 12px; height: 24px; flex-shrink: 0; cursor: ns-resize; user-select: none; background: transparent; transition: background .15s ease; }}
  #panel-resizer:hover {{ background: rgba(88, 166, 255, 0.06); }}
  #panel-resizer .pr-line {{ flex: 1; height: 1px; background: #30363d; transition: background .15s ease; }}
  #panel-resizer:hover .pr-line, body.panel-resizing #panel-resizer .pr-line {{ background: #58a6ff; }}
  #panel-toggle {{ position: relative; z-index: 16; width: 56px; height: 20px; margin: 0; background: #21262d; border: 1px solid #30363d; border-top: none; border-radius: 0 0 8px 8px; color: #8b949e; font-size: 11px; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: background .15s ease, color .15s ease, border-color .15s ease; }}
  #panel-toggle:hover {{ background: #30363d; color: #e6edf3; border-color: #58a6ff; }}
  #panel-resizer:hover #panel-toggle {{ color: #e6edf3; border-color: #58a6ff; }}

  /* ── Center (graph) ────────────────────────────────────────────────── */
  #center {{ flex: 1; display: flex; position: relative; min-width: 0; min-height: 0; height: 0; overflow: hidden; }}
  #graph-area {{ flex: 1; display: flex; flex-direction: column; position: relative; min-width: 0; min-height: 0; height: 100%; overflow: hidden; }}
  #canvas {{ flex: 1; min-width: 0; cursor: grab; display: block; }}
  #canvas.dragging {{ cursor: grabbing; }}
  #minimap {{ position: absolute; bottom: 12px; right: 12px; width: 140px; height: 90px; background: #161b22e6; border: 1px solid #484f58; border-radius: 6px; cursor: pointer; z-index: 10; box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35); }}
  #minimap:hover {{ border-color: #58a6ff; }}
  #help-overlay {{ display: none; position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 24px; z-index: 20; min-width: 280px; }}
  #help-overlay h3 {{ color: #e6edf3; font-size: 14px; margin-bottom: 12px; }}
  #help-overlay kbd {{ background: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 1px 6px; font-size: 11px; font-family: monospace; }}
  #help-overlay .kb-row {{ display: flex; justify-content: space-between; gap: 20px; padding: 4px 0; font-size: 12px; color: #c9d1d9; }}
  #flow-overlay {{ display: none; position: absolute; inset: 0; align-items: center; justify-content: center; padding: 28px; background: rgba(1, 4, 9, 0.72); z-index: 25; }}
  #flow-overlay.open {{ display: flex; }}
  #flow-panel {{ width: min(960px, calc(100vw - 180px)); max-height: calc(var(--viewport-height) - 72px); overflow: auto; background: #161b22; border: 1px solid #30363d; border-radius: 14px; box-shadow: 0 30px 80px rgba(0, 0, 0, 0.45); }}
  #flow-panel header {{ display: flex; justify-content: space-between; gap: 16px; padding: 18px 20px 14px; border-bottom: 1px solid #21262d; }}
  #flow-panel .flow-eyebrow {{ font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: #58a6ff; font-weight: 700; }}
  #flow-panel h3 {{ font-size: 18px; color: #e6edf3; line-height: 1.25; margin-top: 4px; }}
  #flow-panel .flow-subtitle {{ font-size: 13px; color: #8b949e; margin-top: 8px; line-height: 1.5; }}
  #flow-close {{ flex-shrink: 0; width: 32px; height: 32px; border-radius: 999px; border: 1px solid #30363d; background: #21262d; color: #c9d1d9; cursor: pointer; font-size: 18px; line-height: 1; }}
  #flow-close:hover {{ background: #30363d; color: #ffffff; }}
  #flow-body {{ padding: 18px 20px 22px; }}
  .flow-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
  .flow-pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 9px; background: #0d1117; border: 1px solid #30363d; border-radius: 999px; font-size: 11px; color: #8b949e; }}
  .flow-pill strong {{ color: #e6edf3; font-weight: 600; }}
  .flow-graph-wrap {{ border: 1px solid #21262d; border-radius: 12px; background: radial-gradient(circle at top, #1d2633, #0f141b 78%); padding: 16px; overflow: auto; }}
  .flow-svg {{ width: 100%; min-width: 720px; height: auto; display: block; }}
  .flow-svg .flow-node-group {{ cursor: default; }}
  .flow-svg .flow-node-group:hover .flow-node-shape {{ stroke-width: 3; filter: brightness(1.3); }}
  .flow-svg .flow-node-shape {{ stroke-width: 2; transition: stroke-width .15s, filter .15s; }}
  #flow-tooltip, #group-tooltip {{ display: none; position: fixed; z-index: 50; max-width: 300px; padding: 8px 12px; background: #1c2333; border: 1px solid #58a6ff44; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); pointer-events: none; }}
  #flow-tooltip .ft-detail, #group-tooltip .gt-detail {{ font-size: 12px; color: #c9d1d9; line-height: 1.5; }}
  .flow-svg .flow-node-label {{ fill: #e6edf3; font-size: 16px; font-weight: 700; text-anchor: middle; dominant-baseline: middle; }}
  .flow-svg .flow-node-caption {{ fill: #b8c3cf; font-size: 13px; text-anchor: middle; }}
  .flow-svg .flow-edge {{ stroke: #58a6ff; stroke-width: 3; fill: none; }}
  .flow-svg .flow-edge-label {{ fill: #79c0ff; font-size: 12px; font-weight: 600; text-anchor: middle; }}
  .flow-note {{ margin-top: 16px; font-size: 13px; color: #9aa4af; line-height: 1.55; }}
  @media (max-width: 900px) {{
    #flow-overlay {{ padding: 16px; }}
    #flow-panel {{ width: min(100%, calc(100vw - 32px)); max-height: calc(var(--viewport-height) - 32px); }}
    .flow-svg {{ min-width: 560px; }}
  }}

  /* ── Detail section (fills remaining height in top panel, scrollable) */
  #sidebar {{ flex: 0 0 var(--top-details-height); min-height: 0; max-height: var(--top-details-height); overflow-y: auto; padding: 6px 12px; font-size: 12px; display: flex; flex-direction: column; gap: 8px; }}
  #sidebar.hidden {{ display: none; }}
  #sidebar > * {{ flex-shrink: 0; }}
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
  .code-preview {{
    background: #010409; border: 1px solid #30363d; border-radius: 6px;
    padding: 10px 0; margin-top: 6px; max-height: min(360px, 34vh); overflow: auto;
    font-family: "SF Mono", Monaco, Menlo, monospace; font-size: 11px;
    line-height: 1.55; color: #c9d1d9; white-space: pre;
  }}
  .code-preview code {{ display: block; padding: 0 12px; }}
  .code-preview .ln {{ display: inline-block; width: 32px; margin-right: 12px; color: #484f58; text-align: right; user-select: none; }}
  body.panel-resizing {{ cursor: ns-resize; }}
</style>
</head>
<body>
<!-- Top panel: compact header bar + detail section -->
<div id="left-panel">
  <div id="panel-header">
    <span class="ph-brand">{repo}</span>
    <span class="ph-sep"></span>
    <span class="ph-stat"><b>{total_files}</b> files</span>
    <span class="ph-stat"><b>{total_edges}</b> edges</span>
    <span class="ph-stat">{languages}</span>
    <span id="tb-health"></span>
    <span class="ph-sep"></span>
    <input type="text" id="search" class="ph-search" placeholder="Search... (/)" autocomplete="off">
    <span class="ph-spacer"></span>
    <button id="btnEdges" class="active" onclick="toggleEdgeMode()">Edges: All</button>
    <button id="btnFlow" onclick="toggleFlowDirection()">Flow: Auto</button>
    <button id="btnSidebar" onclick="toggleSidebarEnabled()">Details: On</button>
    <button onclick="zoomToFit()">Fit</button>
    <button onclick="toggleHelp()">?</button>
  </div>
  <div id="sidebar"></div>
</div>

<div id="panel-resizer" title="Drag to resize the top panel">
  <span class="pr-line"></span>
  <button id="panel-toggle" type="button" onclick="toggleLeftPanel()" title="Toggle panel">&#x25B2;</button>
  <span class="pr-line"></span>
</div>

<!-- Center: graph + sidebar side by side -->
<div id="center">
  <div id="graph-area">
    <canvas id="canvas"></canvas>
    <canvas id="minimap"></canvas>
    <div id="help-overlay">
      <h3>Keyboard Shortcuts</h3>
      <div class="kb-row"><span><kbd>/</kbd></span><span>Focus search</span></div>
      <div class="kb-row"><span><kbd>Esc</kbd></span><span>Deselect</span></div>
      <div class="kb-row"><span><kbd>F</kbd></span><span>Zoom to fit all nodes</span></div>
      <div class="kb-row"><span>Click</span><span>Open a block or inspect a file</span></div>
      <div class="kb-row"><span>Double-click</span><span>Open the workflow diagram</span></div>
      <div class="kb-row"><span><kbd>?</kbd></span><span>Toggle this help panel</span></div>
    </div>
    <div id="flow-overlay">
      <div id="flow-panel">
        <header>
          <div>
            <div id="flow-eyebrow" class="flow-eyebrow">Workflow Diagram</div>
            <h3 id="flow-title">How this part works</h3>
            <p id="flow-subtitle" class="flow-subtitle"></p>
          </div>
          <button id="flow-close" type="button" aria-label="Close workflow overlay">&times;</button>
        </header>
        <div id="flow-body"></div>
      </div>
    </div>
    <div id="flow-tooltip"></div>
    <div id="group-tooltip"></div>
  </div>
</div>

<script>
const GRAPH = {graph_json};
const SEMANTIC_DIAGRAM = GRAPH.semantic_diagram || null;
const FILE_SEMANTICS = GRAPH.node_semantics || {{}};
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
const CLUSTERS_BY_GROUP = {clusters_by_group_json};
const GROUP_DESCRIPTIONS = {group_descriptions_json};
const ROLE_ORDER = {role_order_json};
const ROLE_SUBTITLES = {role_subtitles_json};
const METRICS = {metrics_json};
const NODE_METRICS = {node_metrics_json};
const HEALTH = {health_json};
const LANG_COUNTS = {lang_counts_json};
const LANG_FILE_COUNTS = {lang_file_counts_json};
const SUMMARY = {summary_json};
const HEALTH_SCORE = {health_score_json};
const HEALTH_NOTES = {health_notes_json};

const rootEl = document.documentElement;
const bodyEl = document.body;
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const leftPanel = document.getElementById('left-panel');
const panelHeader = document.getElementById('panel-header');
const panelResizer = document.getElementById('panel-resizer');
const panelToggle = document.getElementById('panel-toggle');
const centerPane = document.getElementById('center');
const graphArea = document.getElementById('graph-area');
const sidebar = document.getElementById('sidebar');
const searchInput = document.getElementById('search');
const flowOverlay = document.getElementById('flow-overlay');
const flowEyebrow = document.getElementById('flow-eyebrow');
const flowTitle = document.getElementById('flow-title');
const flowSubtitle = document.getElementById('flow-subtitle');
const flowBody = document.getElementById('flow-body');
const flowClose = document.getElementById('flow-close');

const DEFAULT_TOP_DETAILS_HEIGHT = 100;
const MIN_TOP_DETAILS_HEIGHT = 72;
const MAX_TOP_DETAILS_HEIGHT = 420;

// ── Left panel toggle ────────────────────────────────────────────────────────
function toggleLeftPanel() {{
  const lp = document.getElementById('left-panel');
  lp.classList.toggle('collapsed');
  document.body.classList.toggle('panel-collapsed');
  panelToggle.innerHTML = lp.classList.contains('collapsed') ? '&#x25BC;' : '&#x25B2;';
  // Resize canvas and refit after transition
  setTimeout(() => {{ resize(); zoomToFit(); draw(); drawMinimap(); }}, 250);
}}

// ── State ───────────────────────────────────────────────────────────────────
let colorMode = 'language';
let clusterMode = 'off';
let edgeMode = 'all'; // 'hover' | 'all'
let layoutMode = 'layered'; // 'layered' | 'force'
let flowDirection = 'auto'; // 'auto' | 'horizontal' | 'vertical'
let groupingState = 'flat'; // 'grouped' | 'flat'
const pinnedGroupIds = new Set();
let viewportWasManuallyMoved = false;
let fitZoomLevel = 1;
let userZoomScale = 1;
let spreadFactor = 1.0; // controls spacing between blocks (scroll wheel)
let topDetailsHeight = DEFAULT_TOP_DETAILS_HEIGHT;
let panelResizeActive = false;
let panelResizeStartY = 0;
let panelResizeStartHeight = DEFAULT_TOP_DETAILS_HEIGHT;
const semanticNodeById = {{}};
const semanticEdgeByPair = {{}};

function showClusters() {{ return clusterMode !== 'off'; }}

// ── Directory grouping ──────────────────────────────────────────────────────

const groupMap = {{}};       // groupId -> group object
const nodeToGroup = {{}};    // nodeId -> groupId
let visibleNodes = [];
let visibleEdges = [];
let intraGroupEdges = {{}}; // groupId → [{{source, target, type}}]
let groupSourceKind = 'directory';
let semanticGroupingActive = false;

const TEST_SEGMENTS = new Set(['test', 'tests', 'spec', 'specs', '__tests__']);
const GENERIC_DIR_SEGMENTS = new Set([
  'src', 'lib', 'libs', 'app', 'apps', 'pkg', 'packages', 'modules', 'module',
  'services', 'service', 'internal', 'core',
]);

function humanizeLabel(value) {{
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\\b\\w/g, c => c.toUpperCase());
}}

function humanizeSemanticKind(kind) {{
  return humanizeLabel(String(kind || 'process')).replace(/\\bApi\\b/g, 'API');
}}

function mergeOverflowClusters(clusterMap, maxGroups) {{
  const entries = Object.entries(clusterMap)
    .filter(([, ids]) => ids.length > 0)
    .sort((a, b) => b[1].length - a[1].length);
  if (entries.length <= maxGroups) return Object.fromEntries(entries);
  const kept = entries.slice(0, maxGroups - 1);
  const otherIds = entries.slice(maxGroups - 1).flatMap(([, ids]) => ids);
  return Object.fromEntries([...kept, ['(other)', otherIds]]);
}}

function compressClusterKey(dirName, depth) {{
  if (dirName === '(root)' || dirName === '(other)') return dirName;
  const parts = dirName.split('/').filter(Boolean);
  return parts.slice(0, Math.min(depth, parts.length)).join('/');
}}

function mergeDirectoryClusters(depth) {{
  const merged = {{}};
  for (const [dirName, ids] of Object.entries(CLUSTERS)) {{
    const key = compressClusterKey(dirName, depth);
    if (!merged[key]) merged[key] = [];
    merged[key].push(...ids);
  }}
  return mergeOverflowClusters(merged, 10);
}}

function clusterStats(clusterMap) {{
  const groups = Object.values(clusterMap).filter(ids => ids.length > 0);
  if (groups.length === 0) {{
    return {{ count: 0, meaningful: 0, maxShare: 1 }};
  }}
  return {{
    count: groups.length,
    meaningful: groups.filter(ids => ids.length >= 2).length,
    maxShare: Math.max(...groups.map(ids => ids.length)) / Math.max(nodes.length, 1),
  }};
}}

function isUsefulClusterMap(clusterMap) {{
  const stats = clusterStats(clusterMap);
  return (
    stats.count >= 2 &&
    stats.count <= 10 &&
    stats.meaningful >= 2 &&
    stats.maxShare <= 0.78
  );
}}

function selectGroupSource() {{
  // Prefer AI-defined architectural groups when available
  if (Object.keys(CLUSTERS_BY_GROUP).length >= 2) {{
    return {{ kind: 'group', clusters: CLUSTERS_BY_GROUP }};
  }}

  const dirDepths = [...new Set(
    Object.keys(CLUSTERS)
      .filter(dirName => dirName !== '(root)' && dirName !== '(other)')
      .map(dirName => dirName.split('/').filter(Boolean).length)
  )].sort((a, b) => b - a);

  for (const depth of dirDepths) {{
    const candidate = mergeDirectoryClusters(depth);
    if (isUsefulClusterMap(candidate)) {{
      return {{ kind: 'directory', clusters: candidate }};
    }}
  }}

  const directDirectoryClusters = mergeOverflowClusters(CLUSTERS, 10);
  if (isUsefulClusterMap(directDirectoryClusters)) {{
    return {{ kind: 'directory', clusters: directDirectoryClusters }};
  }}

  return {{
    kind: 'role',
    clusters: mergeOverflowClusters(CLUSTERS_BY_ROLE, 8),
  }};
}}

function dominantRole(childNodes) {{
  const counts = {{}};
  for (const node of childNodes) {{
    if (!node.role) continue;
    counts[node.role] = (counts[node.role] || 0) + 1;
  }}
  const winner = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  return winner ? winner[0] : '';
}}

function isTestGroup(groupKey, childNodes, label) {{
  if (label === 'Tests') return true;
  if (groupKey === '(other)') return false;
  if (TEST_SEGMENTS.has(groupKey.toLowerCase())) return true;
  const role = dominantRole(childNodes);
  if (role === 'test') return true;
  return childNodes.every(node => TEST_SEGMENTS.has(node.label.toLowerCase()) || node.role === 'test');
}}

function groupDisplayLabel(groupKey, childNodes) {{
  if (groupSourceKind === 'group') {{
    return groupKey;  // AI-defined group names are already human-readable
  }}
  if (groupSourceKind === 'role') {{
    if (groupKey === 'Other') return 'Miscellaneous';
    return groupKey;
  }}
  if (groupKey === '(root)') return 'Root Files';
  if (groupKey === '(other)') return 'Miscellaneous';

  const parts = groupKey.split('/').filter(Boolean);
  const lowered = parts.map(part => part.toLowerCase());
  if (lowered.some(part => TEST_SEGMENTS.has(part))) return 'Tests';

  let chosen = parts[parts.length - 1] || groupKey;
  for (let i = parts.length - 1; i >= 0; i--) {{
    if (!GENERIC_DIR_SEGMENTS.has(lowered[i])) {{
      chosen = parts[i];
      break;
    }}
  }}

  if (TEST_SEGMENTS.has(chosen.toLowerCase())) return 'Tests';
  if (chosen.toLowerCase() === 'src') return 'Source Files';
  if (chosen.toLowerCase() === 'app') return 'App Files';
  return humanizeLabel(chosen);
}}

function firstSentence(text) {{
  if (!text) return '';
  const cleaned = text.replace(WHITESPACE_RE, ' ').trim();
  const match = cleaned.match(/.+?[.!?](?:\\s|$)/);
  return match ? match[0].trim() : cleaned;
}}

function rankChildNodes(childNodes) {{
  return [...childNodes].sort((a, b) => {{
    const aScore = (a.pagerank || 0) * 100 + (a.indegree || 0) * 2 + (a.outdegree || 0);
    const bScore = (b.pagerank || 0) * 100 + (b.indegree || 0) * 2 + (b.outdegree || 0);
    return bScore - aScore;
  }});
}}

function summarizeGroup(groupKey, label, childNodes) {{
  // Use AI group description when available
  if (GROUP_DESCRIPTIONS[groupKey]) return GROUP_DESCRIPTIONS[groupKey];

  const ranked = rankChildNodes(childNodes);
  const snippets = ranked
    .map(node => firstSentence(node.description))
    .filter(Boolean)
    .slice(0, 2);

  if (isTestGroup(groupKey, childNodes, label)) {{
    if (snippets.length > 0) return snippets.join(' ');
    const titles = ranked.slice(0, 3).map(node => node.short_title || node.label.replace(JS_EXT_RE, ''));
    return titles.length > 0 ? `Covers ${{titles.join(', ')}}.` : 'Test coverage for the project.';
  }}

  if (snippets.length > 0) return snippets.join(' ');

  const titles = ranked
    .slice(0, 3)
    .map(node => node.short_title || node.label.replace(JS_EXT_RE, ''))
    .filter(Boolean);
  return titles.length > 0 ? `Contains ${{titles.join(', ')}}.` : '';
}}

function buildGroups() {{
  for (const key of Object.keys(groupMap)) delete groupMap[key];
  for (const key of Object.keys(nodeToGroup)) delete nodeToGroup[key];
  for (const key of Object.keys(semanticNodeById)) delete semanticNodeById[key];
  for (const key of Object.keys(semanticEdgeByPair)) delete semanticEdgeByPair[key];

  semanticGroupingActive = Boolean(SEMANTIC_DIAGRAM && SEMANTIC_DIAGRAM.nodes && SEMANTIC_DIAGRAM.nodes.length >= 2);
  if (semanticGroupingActive) {{
    groupSourceKind = 'semantic';
    groupingState = 'grouped';

    for (const semanticNode of (SEMANTIC_DIAGRAM.nodes || [])) {{
      semanticNodeById[semanticNode.id] = semanticNode;
      const ids = (semanticNode.members || []).filter(Boolean);
      const childNodes = ids.map(id => nodeIndex[id]).filter(Boolean);
      if (childNodes.length === 0) continue;

      const langCounts = {{}};
      for (const n of childNodes) {{
        langCounts[n.language] = (langCounts[n.language] || 0) + 1;
      }}
      const lang = Object.entries(langCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || '';
      const totalSize = childNodes.reduce((sum, n) => sum + (n.size || 0), 0);
      const role = semanticNode.role || dominantRole(childNodes);

      const group = {{
        id: semanticNode.id,
        label: semanticNode.label,
        fullPath: semanticNode.id,
        description: semanticNode.summary || summarizeGroup(semanticNode.id, semanticNode.label, childNodes),
        short_title: semanticNode.label,
        childIds: ids,
        isGroup: true,
        language: lang,
        size: totalSize,
        fileCount: childNodes.length,
        x: 0, y: 0, vx: 0, vy: 0, fx: 0, fy: 0, pinned: false,
        w: NODE_W + 56, h: NODE_H_BASE + 28,
        indegree: 0, outdegree: 0, pagerank: 0,
        symbols: [], role, preview: '', inCycle: false,
        kind: semanticNode.kind || 'process',
        shape: semanticNode.shape || semanticNode.kind || 'process',
        level: semanticNode.level || 0,
        detailDiagram: semanticNode.detail || null,
      }};

      // Groups in semantic mode read as architecture blocks, not as fat file
      // cards. Size them so there's room for title + description + a row of
      // child sub-block hints rendered inside.
      group.w = 360;
      group.h = 210;

      groupMap[group.id] = group;
      for (const id of ids) nodeToGroup[id] = group.id;
    }}

    for (const semanticEdge of (SEMANTIC_DIAGRAM.edges || [])) {{
      semanticEdgeByPair[semanticEdge.source + '|' + semanticEdge.target] = semanticEdge;
    }}

    for (const g of Object.values(groupMap)) {{
      g._closedW = g.w;
      g._closedH = g.h;
    }}
    computeVisibleState();
    return;
  }}

  const source = selectGroupSource();
  groupSourceKind = source.kind;
  if (!source.clusters || Object.keys(source.clusters).length < 2) {{
    groupingState = 'flat';
    visibleNodes = nodes;
    visibleEdges = edges;
    return;
  }}

  groupingState = 'grouped';

  for (const [groupKey, ids] of Object.entries(source.clusters)) {{
    const childNodes = ids.map(id => nodeIndex[id]).filter(Boolean);
    if (childNodes.length === 0) continue;
    const label = groupDisplayLabel(groupKey, childNodes);
    const role = isTestGroup(groupKey, childNodes, label) ? 'test' : dominantRole(childNodes);
    const desc = summarizeGroup(groupKey, label, childNodes);

    // Dominant language
    const langCounts = {{}};
    for (const n of childNodes) {{ langCounts[n.language] = (langCounts[n.language] || 0) + 1; }}
    const lang = Object.entries(langCounts).sort((a,b) => b[1]-a[1])[0]?.[0] || '';

    const totalSize = childNodes.reduce((s, n) => s + (n.size || 0), 0);

    const group = {{
      id: 'group:' + groupKey,
      label,
      fullPath: groupKey,
      description: desc,
      short_title: label,
      childIds: ids,
      isGroup: true,
      language: lang,
      size: totalSize,
      fileCount: childNodes.length,
      x: 0, y: 0, vx: 0, vy: 0, fx: 0, fy: 0, pinned: false,
      w: NODE_W + 56, h: NODE_H_BASE + 28, // temporary, replaced below
      indegree: 0, outdegree: 0, pagerank: 0,
      symbols: [], role, preview: '', inCycle: false,
    }};

    groupMap[group.id] = group;
    for (const id of ids) nodeToGroup[id] = group.id;
  }}

  // Store closed dimensions — layout uses these.
  // Open dimensions computed on-the-fly when hovering/pinning.
  for (const g of Object.values(groupMap)) {{
    g._closedW = g.w;
    g._closedH = g.h;
  }}

  // Compute group-level in/out degree from aggregated edges
  computeVisibleState();
}}

function computeVisibleState() {{
  if (groupingState === 'flat') {{
    visibleNodes = nodes;
    visibleEdges = edges;
    intraGroupEdges = {{}};
    return;
  }}

  // Show all groups as nodes (children drawn inline when open)
  const vNodes = [];
  for (const g of Object.values(groupMap)) vNodes.push(g);
  visibleNodes = vNodes;

  if (semanticGroupingActive) {{
    intraGroupEdges = {{}};
    for (const e of edges) {{
      const srcId = e._srcId || e.source.id || e.source;
      const tgtId = e._tgtId || e.target.id || e.target;
      const srcVisible = nodeToGroup[srcId] || srcId;
      const tgtVisible = nodeToGroup[tgtId] || tgtId;
      if (srcVisible !== tgtVisible) continue;
      if (!intraGroupEdges[srcVisible]) intraGroupEdges[srcVisible] = [];
      const srcNode = nodeIndex[srcId];
      const tgtNode = nodeIndex[tgtId];
      if (srcNode && tgtNode) {{
        intraGroupEdges[srcVisible].push({{
          source: srcNode,
          target: tgtNode,
          _srcId: srcId,
          _tgtId: tgtId,
          type: e.type || 'imports',
        }});
      }}
    }}

    visibleEdges = (SEMANTIC_DIAGRAM.edges || [])
      .map(edge => {{
        const source = groupMap[edge.source];
        const target = groupMap[edge.target];
        if (!source || !target) return null;
        return {{
          source,
          target,
          _srcId: edge.source,
          _tgtId: edge.target,
          type: edge.kind || 'depends_on',
          kind: edge.kind || 'depends_on',
          label: edge.label || '',
          weight: edge.weight || 1,
        }};
      }})
      .filter(Boolean);

    for (const g of Object.values(groupMap)) {{
      g.indegree = 0;
      g.outdegree = 0;
    }}
    for (const e of visibleEdges) {{
      const src = e.source;
      const tgt = e.target;
      if (src && src.isGroup) src.outdegree++;
      if (tgt && tgt.isGroup) tgt.indegree++;
    }}
    return;
  }}

  // Aggregate edges at group level
  intraGroupEdges = {{}};
  const aggMap = {{}};
  for (const e of edges) {{
    const srcId = e._srcId || e.source.id || e.source;
    const tgtId = e._tgtId || e.target.id || e.target;

    const srcVisible = nodeToGroup[srcId] || srcId;
    const tgtVisible = nodeToGroup[tgtId] || tgtId;

    if (srcVisible === tgtVisible) {{
      // Collect intra-group edges for display inside open groups
      const gid = srcVisible;
      if (!intraGroupEdges[gid]) intraGroupEdges[gid] = [];
      const srcNode = nodeIndex[srcId], tgtNode = nodeIndex[tgtId];
      if (srcNode && tgtNode) {{
        intraGroupEdges[gid].push({{ source: srcNode, target: tgtNode, _srcId: srcId, _tgtId: tgtId, type: 'imports' }});
      }}
      continue;
    }}

    const key = srcVisible + '|' + tgtVisible;
    if (aggMap[key]) {{
      aggMap[key].weight++;
    }} else {{
      const srcNode = nodeIndex[srcVisible] || groupMap[srcVisible];
      const tgtNode = nodeIndex[tgtVisible] || groupMap[tgtVisible];
      if (!srcNode || !tgtNode) continue;
      aggMap[key] = {{
        source: srcNode, target: tgtNode,
        _srcId: srcVisible, _tgtId: tgtVisible,
        weight: 1, type: 'imports', symbols: [],
      }};
    }}
  }}

  visibleEdges = Object.values(aggMap);

  // Update group degrees from aggregated edges
  for (const g of Object.values(groupMap)) {{ g.indegree = 0; g.outdegree = 0; }}
  for (const e of visibleEdges) {{
    const src = e.source; const tgt = e.target;
    if (src.isGroup) src.outdegree++;
    if (tgt.isGroup) tgt.indegree++;
  }}
}}

function isGroupOpen(g) {{
  if (!g || !g.isGroup) return false;
  if (pinnedGroupIds.has(g.id)) return true;
  return false;
}}

function toggleGroupPin(groupId) {{
  if (pinnedGroupIds.has(groupId)) {{
    pinnedGroupIds.delete(groupId);
  }} else {{
    pinnedGroupIds.add(groupId);
  }}
  // Clear any file selection so the graph doesn't dim
  selectedNode = null;
  highlightSet = null;
  blastRadiusSet = new Set();
  resolveGroupOverlaps();
  renderDefaultSidebar();
  zoomToFit();
}}

// Resolve overlaps between ALL groups using their actual dimensions
// (expanded for open groups, collapsed for closed ones).
// Called once when open-state changes, not every frame.
function resolveGroupOverlaps() {{
  if (groupingState === 'flat') return;
  const groups = Object.values(groupMap);

  // Save layout positions once (after relayout)
  for (const g of groups) {{
    if (g._layoutX === undefined) {{ g._layoutX = g.x; g._layoutY = g.y; }}
  }}
  // Reset ALL to layout positions
  for (const g of groups) {{
    g.x = g._layoutX;
    g.y = g._layoutY;
  }}

  // Compute effective bounds for each group (open = expanded, closed = collapsed)
  function groupBounds(g) {{
    const open = isGroupOpen(g);
    let w, h;
    if (open) {{
      const layout = layoutOpenGroupChildren(g);
      w = layout.openW;
      h = layout.openH;
    }} else {{
      w = g._closedW;
      h = g._closedH;
    }}
    const top = g.y - g._closedH / 2; // anchor at original closed-top
    return {{ left: g.x - w / 2, right: g.x + w / 2, top: top, bottom: top + h, w, h }};
  }}

  // Sort by layout Y (top to bottom) — process top groups first
  const sorted = [...groups].sort((a, b) => a._layoutY - b._layoutY);

  // Sweep top-down: each group pushes all groups below it if they overlap
  for (let pass = 0; pass < 12; pass++) {{
    let moved = false;
    for (let i = 0; i < sorted.length; i++) {{
      const a = sorted[i];
      const ab = groupBounds(a);
      for (let j = i + 1; j < sorted.length; j++) {{
        const b = sorted[j];
        const bb = groupBounds(b);
        // Horizontal overlap — generous margin so adjacent columns are caught
        if (bb.right <= ab.left - 30 || bb.left >= ab.right + 30) continue;
        // Vertical overlap check
        if (bb.top >= ab.bottom + 16) continue;
        // Push b down below a
        const newY = ab.bottom + 80 + b._closedH / 2;
        if (newY > b.y) {{
          b.y = newY;
          moved = true;
        }}
      }}
    }}
    if (!moved) break;
  }}
}}

function collapseGroups() {{
  pinnedGroupIds.clear();
  selectedNode = null; highlightSet = null; blastRadiusSet = new Set();
  computeVisibleState();
  renderDefaultSidebar();
  relayout();
}}

// Position children inside an open group as a grid of full-size cards.
// Returns {{ items: [{{ node, cx, cy }}], openW, openH, cols, rows }}.
const OPEN_GROUP_HEADER = 120;
const OPEN_GROUP_PAD = 36;
const OPEN_GROUP_GAP = 48;

function layoutOpenGroupChildren(group) {{
  const children = (group.childIds || []).map(id => nodeIndex[id]).filter(Boolean);
  if (children.length === 0) return {{ items: [], openW: group.w, openH: group.h, cols: 0, rows: 0, internalEdges: [] }};

  // Topological sort using intra-group edges (Kahn's algorithm)
  const gEdges = intraGroupEdges[group.id] || [];
  const childSet = new Set(children.map(c => c.id));
  const inDeg = {{}};
  const adj = {{}};
  for (const c of children) {{ inDeg[c.id] = 0; adj[c.id] = []; }}
  for (const e of gEdges) {{
    const sid = e._srcId || e.source.id, tid = e._tgtId || e.target.id;
    if (childSet.has(sid) && childSet.has(tid)) {{
      adj[sid].push(tid);
      inDeg[tid] = (inDeg[tid] || 0) + 1;
    }}
  }}
  const queue = children.filter(c => inDeg[c.id] === 0)
    .sort((a, b) => (b.pagerank || 0) - (a.pagerank || 0));
  const sorted = [];
  const visited = new Set();
  for (let i = 0; i < queue.length; i++) {{
    const node = queue[i];
    if (visited.has(node.id)) continue;
    visited.add(node.id);
    sorted.push(node);
    for (const nid of (adj[node.id] || [])) {{
      inDeg[nid]--;
      if (inDeg[nid] === 0) {{
        const nNode = nodeIndex[nid];
        if (nNode && !visited.has(nid)) queue.push(nNode);
      }}
    }}
  }}
  for (const c of rankChildNodes(children)) {{
    if (!visited.has(c.id)) sorted.push(c);
  }}

  const n = sorted.length;
  // Side-by-side layout for small groups (2–4 children) so they read as
  // "two blocks inside a container" rather than a tall single-column stack.
  const cols = n <= 1 ? 1 : (n <= 4 ? 2 : 3);
  const rows = Math.ceil(n / cols);
  const cellW = NODE_W;
  const cellH = Math.max(...sorted.map(c => c.h || NODE_H_BASE));
  const openW = cols * cellW + (cols - 1) * OPEN_GROUP_GAP + OPEN_GROUP_PAD * 2;
  const openH = OPEN_GROUP_HEADER + rows * cellH + (rows - 1) * OPEN_GROUP_GAP + OPEN_GROUP_PAD;
  const topY = group.y - group.h / 2;
  const leftX = group.x - openW / 2;

  const items = sorted.map((node, i) => {{
    const col = i % cols;
    const row = Math.floor(i / cols);
    const cx = leftX + OPEN_GROUP_PAD + col * (cellW + OPEN_GROUP_GAP) + cellW / 2;
    const cy = topY + OPEN_GROUP_HEADER + row * (cellH + OPEN_GROUP_GAP) + cellH / 2;
    return {{ node, cx, cy }};
  }});
  return {{ items, openW, openH, cols, rows, internalEdges: gEdges }};
}}

function openGroupVisualHeight(group) {{
  return layoutOpenGroupChildren(group).openH;
}}

function openGroupVisualWidth(group) {{
  return layoutOpenGroupChildren(group).openW;
}}

function relayout() {{
  layoutBlocks(visibleNodes, visibleEdges);
  // Clear cached layout positions so resolveGroupOverlaps re-captures them
  for (const g of Object.values(groupMap)) {{ delete g._layoutX; delete g._layoutY; }}
  viewportWasManuallyMoved = false;
  simRunning = false;
  draw();
  drawMinimap();
  setTimeout(() => {{ zoomToFit(); draw(); drawMinimap(); }}, 50);
}}

function resolvedFlowDirection() {{
  if (flowDirection !== 'auto') return flowDirection;
  // Use the actual DOM element size, not the canvas buffer
  const rect = graphArea.getBoundingClientRect();
  const w = rect.width || canvasW();
  const h = rect.height || canvasH();
  return w > h * 1.3 ? 'horizontal' : 'vertical';
}}

function toggleFlowDirection() {{
  const cycle = {{ auto: 'horizontal', horizontal: 'vertical', vertical: 'auto' }};
  flowDirection = cycle[flowDirection] || 'auto';
  const btn = document.getElementById('btnFlow');
  if (btn) {{
    const labels = {{ auto: 'Flow: Auto', horizontal: 'Flow: \u2192', vertical: 'Flow: \u2193' }};
    btn.textContent = labels[flowDirection];
  }}
  if (groupingState !== 'flat') relayout();
}}

let sidebarEnabled = true;
function toggleSidebarEnabled() {{
  sidebarEnabled = !sidebarEnabled;
  const btn = document.getElementById('btnSidebar');
  if (btn) btn.textContent = sidebarEnabled ? 'Details: On' : 'Details: Off';
  if (!sidebarEnabled) {{
    sidebar.classList.add('hidden');
    sidebar.innerHTML = '';
  }} else {{
    sidebar.classList.remove('hidden');
    if (selectedNode) {{
      renderSidebar(selectedNode);
    }} else if (hoveredNode) {{
      hoveredNode.isGroup ? renderGroupSidebar(hoveredNode) : renderSidebar(hoveredNode);
    }} else {{
      sidebar.innerHTML = '<div class="placeholder">Hover or click a block to see details.</div>';
    }}
  }}
}}

function toggleEdgeMode() {{
  edgeMode = edgeMode === 'hover' ? 'all' : 'hover';
  const btn = document.getElementById('btnEdges');
  btn.textContent = edgeMode === 'hover' ? 'Edges: Hover' : 'Edges: All';
  btn.classList.toggle('active', edgeMode === 'all');
  draw();
}}

function blockScore(n) {{
  return ((n.pagerank || 0) * 160) + ((n.indegree || 0) * 6) + ((n.outdegree || 0) * 4) + (n.fileCount || 1);
}}

function rankBlocks(blocks) {{
  return [...blocks].sort((a, b) => {{
    const delta = blockScore(b) - blockScore(a);
    if (delta !== 0) return delta;
    return a.label.localeCompare(b.label);
  }});
}}

function topologicalDepths(nodeList, edgeList) {{
  const inDeg = {{}};
  const adj = {{}};
  for (const n of nodeList) {{
    inDeg[n.id] = 0;
    adj[n.id] = [];
  }}
  for (const e of edgeList) {{
    const srcId = e.source.id || e.source;
    const tgtId = e.target.id || e.target;
    if (!(srcId in adj) || !(tgtId in inDeg)) continue;
    adj[srcId].push(tgtId);
    inDeg[tgtId]++;
  }}

  const depth = {{}};
  const queue = nodeList.filter(n => inDeg[n.id] === 0).map(n => n.id);
  queue.forEach(id => {{ depth[id] = 0; }});
  for (let i = 0; i < queue.length; i++) {{
    const id = queue[i];
    for (const nextId of adj[id]) {{
      const nextDepth = depth[id] + 1;
      if (depth[nextId] === undefined || depth[nextId] < nextDepth) {{
        depth[nextId] = nextDepth;
        queue.push(nextId);
      }}
    }}
  }}
  for (const n of nodeList) {{
    if (depth[n.id] === undefined) depth[n.id] = 0;
  }}
  const maxDepth = Math.max(0, ...Object.values(depth));
  return {{ depth, maxDepth }};
}}

function stackNodesVertically(nodeList, centerX, startY, gapY) {{
  let y = startY;
  for (const n of nodeList) {{
    n.x = centerX;
    n.y = y + n.h / 2;
    n.vx = 0;
    n.vy = 0;
    n.pinned = true;
    y += n.h + gapY;
  }}
}}

// Vertical flow: each row = one topo depth, blocks arranged left-to-right within rows
function layoutBlockRows(rows) {{
  const nonEmpty = rows.filter(r => r.length > 0);
  if (nonEmpty.length === 0) return;

  const ROW_GAP = Math.max(140, 140 * spreadFactor);
  const COL_GAP = Math.max(80, 80 * spreadFactor);
  const rowHeights = nonEmpty.map(row => Math.max(...row.map(n => n.h)));
  const rowWidths = nonEmpty.map(row =>
    row.reduce((sum, n) => sum + n.w, 0) + Math.max(0, row.length - 1) * COL_GAP
  );
  const totalHeight = rowHeights.reduce((sum, h) => sum + h, 0) + Math.max(0, rowHeights.length - 1) * ROW_GAP;

  let cursorY = -totalHeight / 2;
  nonEmpty.forEach((row, ri) => {{
    const height = rowHeights[ri];
    const centerY = cursorY + height / 2;
    const rw = rowWidths[ri];
    let cursorX = -rw / 2;
    row.forEach(n => {{
      n.x = cursorX + n.w / 2;
      n.y = centerY;
      cursorX += n.w + COL_GAP;
    }});
    cursorY += height + ROW_GAP;
  }});
}}

// Horizontal flow: each column = one topo depth, blocks stacked vertically
function layoutBlockColumns(columns) {{
  const nonEmpty = columns.filter(col => col.length > 0);
  if (nonEmpty.length === 0) return;

  const COLUMN_GAP = Math.max(180, 180 * spreadFactor);
  const ROW_GAP = Math.max(80, 80 * spreadFactor);
  const widths = nonEmpty.map(col => Math.max(...col.map(n => n.w)));
  const heights = nonEmpty.map(col => col.reduce((sum, n) => sum + n.h, 0) + Math.max(0, col.length - 1) * ROW_GAP);
  const totalWidth = widths.reduce((sum, width) => sum + width, 0) + Math.max(0, widths.length - 1) * COLUMN_GAP;

  let cursorX = -totalWidth / 2;
  nonEmpty.forEach((col, index) => {{
    const width = widths[index];
    const centerX = cursorX + width / 2;
    const startY = -heights[index] / 2;
    stackNodesVertically(col, centerX, startY, ROW_GAP);
    cursorX += width + COLUMN_GAP;
  }});
}}

// Human-readable title for a layered band. Uses the dominant kind and role
// among the blocks in the lane so the backdrop reads like an architecture
// diagram ("Entry & CLI" / "Data & State" / "Tests") instead of "Layer 2".
function describeBandForBlocks(blocks, laneIndex, laneCount) {{
  if (!blocks || blocks.length === 0) {{
    return {{ title: 'Layer ' + (laneIndex + 1), subtitle: '' }};
  }}
  const kindCounts = {{}};
  const roleCounts = {{}};
  for (const b of blocks) {{
    const k = b.kind || b.shape || 'process';
    kindCounts[k] = (kindCounts[k] || 0) + 1;
    const r = b.role || '';
    if (r) roleCounts[r] = (roleCounts[r] || 0) + 1;
  }}
  const topKind = Object.entries(kindCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'process';
  const topRole = Object.entries(roleCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || '';
  const allTests = blocks.every(b => b.role === 'test' || b.kind === 'test');
  if (allTests) return {{ title: 'Tests', subtitle: 'verification & coverage' }};
  if (laneIndex === 0) {{
    if (topKind === 'entry' || topRole === 'entry_point') {{
      return {{ title: 'Entry & CLI', subtitle: 'what the user runs' }};
    }}
    return {{ title: 'Entry layer', subtitle: 'drives the pipeline' }};
  }}
  if (laneIndex === laneCount - 1) {{
    if (topKind === 'data') return {{ title: 'Data & State', subtitle: 'what the system remembers' }};
    return {{ title: 'Foundations', subtitle: 'depended on by layers above' }};
  }}
  switch (topKind) {{
    case 'data': return {{ title: 'Data & State', subtitle: 'shared types & storage' }};
    case 'decision': return {{ title: 'Decisions & Policy', subtitle: 'routing & validation' }};
    case 'analysis': return {{ title: 'Analysis', subtitle: 'parsing & scoring' }};
    case 'entry': return {{ title: 'Entry layer', subtitle: 'drives the pipeline' }};
    case 'test': return {{ title: 'Tests', subtitle: 'verification & coverage' }};
    default: return {{ title: 'Core logic', subtitle: 'application layer' }};
  }}
}}

// Compute band rectangles for each non-empty lane from the (already
// positioned) blocks. Called after layoutBlockRows/Columns so we can use the
// actual x/y of each block. Populates window.__layerBands so drawClusters's
// band backdrop routine picks them up.
function computeBlockLayerBands(nonEmptyLanes, direction) {{
  if (!nonEmptyLanes || nonEmptyLanes.length === 0) {{
    window.__layerBands = null;
    return;
  }}
  const bands = [];
  const pad = 32;
  const laneCount = nonEmptyLanes.length;
  for (let i = 0; i < laneCount; i++) {{
    const lane = nonEmptyLanes[i];
    if (!lane || lane.length === 0) continue;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const n of lane) {{
      minX = Math.min(minX, n.x - n.w / 2);
      maxX = Math.max(maxX, n.x + n.w / 2);
      minY = Math.min(minY, n.y - n.h / 2);
      maxY = Math.max(maxY, n.y + n.h / 2);
    }}
    const info = describeBandForBlocks(lane, i, laneCount);
    if (direction === 'horizontal') {{
      bands.push({{
        orientation: 'vertical',
        top: minY - pad,
        bottom: maxY + pad,
        left: minX - pad,
        right: maxX + pad,
        title: info.title,
        subtitle: info.subtitle,
      }});
    }} else {{
      bands.push({{
        orientation: 'horizontal',
        top: minY - pad,
        bottom: maxY + pad,
        left: minX - pad,
        right: maxX + pad,
        title: info.title,
        subtitle: info.subtitle,
      }});
    }}
  }}
  window.__layerBands = bands;
}}

function layoutGroupedBlocks(nodeList, edgeList) {{
  const blocks = nodeList.filter(n => n.isGroup);
  if (blocks.length === 0) return;

  const ranked = rankBlocks(blocks);
  const groupEdges = edgeList.filter(e => e.source.isGroup && e.target.isGroup);
  // Prefer the precomputed semantic level when available — it comes from
  // apply_topological_levels in diagram.py and is guaranteed consistent with
  // the lane labels / band titles we show below.
  const hasSemanticLevels = blocks.some(b => typeof b.level === 'number' && b.level > 0);
  let depth, maxDepth;
  if (hasSemanticLevels) {{
    depth = {{}};
    maxDepth = 0;
    for (const b of blocks) {{
      const lvl = typeof b.level === 'number' ? b.level : 0;
      depth[b.id] = lvl;
      if (lvl > maxDepth) maxDepth = lvl;
    }}
  }} else {{
    const td = topologicalDepths(blocks, groupEdges);
    depth = td.depth;
    maxDepth = td.maxDepth;
  }}
  const dir = resolvedFlowDirection();

  // Assign blocks to lanes (by topo depth). Depth 0 = first lane.
  const laneCount = Math.max(1, maxDepth + 1);
  const lanes = Array.from({{ length: laneCount }}, () => []);

  if (maxDepth > 0) {{
    for (const block of ranked) {{
      const d = depth[block.id] || 0;
      // Tests go in last lane
      const laneIdx = block.role === 'test' ? laneCount - 1 : Math.min(d, laneCount - 1);
      lanes[laneIdx].push(block);
    }}
  }} else {{
    // No topo structure — just put all in one lane
    ranked.forEach(block => lanes[0].push(block));
  }}

  // Sort within each lane: tests last, then by score
  lanes.forEach(lane => {{
    lane.sort((a, b) => {{
      if (a.role === 'test' && b.role !== 'test') return 1;
      if (b.role === 'test' && a.role !== 'test') return -1;
      return blockScore(b) - blockScore(a);
    }});
  }});

  // If all ended up in one lane, use the old column-based fallback
  const nonEmptyLanes = lanes.filter(l => l.length > 0);
  if (nonEmptyLanes.length <= 1 && blocks.length > 1) {{
    // Fallback: split by score into 2 columns
    const columns = [[], []];
    ranked.forEach((block, i) => {{
      const col = block.role === 'test' ? 1 : i % 2;
      columns[col].push(block);
    }});
    if (dir === 'horizontal') {{
      layoutBlockColumns(columns);
    }} else {{
      layoutBlockRows(columns);
    }}
    computeBlockLayerBands(columns.filter(c => c.length > 0), dir);
    return;
  }}

  if (dir === 'horizontal') {{
    // Horizontal flow: topo depth = column (left to right)
    layoutBlockColumns(nonEmptyLanes);
  }} else {{
    // Vertical flow: topo depth = row (top to bottom)
    layoutBlockRows(nonEmptyLanes);
  }}
  computeBlockLayerBands(nonEmptyLanes, dir);
}}

function layoutExpandedBlock(nodeList) {{
  const blocks = rankBlocks(nodeList.filter(n => n.isGroup));
  const files = rankChildNodes(nodeList.filter(n => !n.isGroup));
  if (files.length === 0) {{
    layoutGroupedBlocks(blocks, []);
    return;
  }}

  const sideWidth = blocks.length > 0 ? Math.max(...blocks.map(n => n.w)) + 28 : 0;
  const sideGap = blocks.length > 0 ? 96 : 0;
  const GRID_GAP_X = 30;
  const GRID_GAP_Y = 28;
  const cols = files.length === 1
    ? 1
    : Math.min(4, Math.max(2, Math.ceil(Math.sqrt(files.length))));
  const rows = Math.ceil(files.length / cols);
  const cellW = Math.max(...files.map(n => n.w));
  const cellH = Math.max(...files.map(n => n.h));
  const gridWidth = cols * cellW + Math.max(0, cols - 1) * GRID_GAP_X;
  const gridHeight = rows * cellH + Math.max(0, rows - 1) * GRID_GAP_Y;
  const totalWidth = sideWidth + sideGap + gridWidth;
  const leftEdge = -totalWidth / 2;

  if (blocks.length > 0) {{
    const sideCenterX = leftEdge + sideWidth / 2;
    const sideHeight = blocks.reduce((sum, n) => sum + n.h, 0) + Math.max(0, blocks.length - 1) * 34;
    stackNodesVertically(blocks, sideCenterX, -sideHeight / 2, 34);
  }}

  const gridLeft = leftEdge + sideWidth + sideGap;
  const gridTop = -gridHeight / 2;
  files.forEach((n, index) => {{
    const row = Math.floor(index / cols);
    const col = index % cols;
    n.x = gridLeft + col * (cellW + GRID_GAP_X) + cellW / 2;
    n.y = gridTop + row * (cellH + GRID_GAP_Y) + cellH / 2;
    n.vx = 0;
    n.vy = 0;
    n.pinned = true;
  }});
}}

function layoutBlocks(nodeList, edgeList) {{
  nodeList = nodeList || visibleNodes || nodes;
  edgeList = edgeList || visibleEdges || edges;
  window.__clusterBoxes = null;
  window.__nodeClusterMap = null;
  window.__layerBands = null;

  if (groupingState === 'flat') {{
    layoutLayered(nodeList, edgeList);
    window.__layerBands = null;
    return;
  }}

  layoutGroupedBlocks(nodeList, edgeList);
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
    const wrapW = Math.max(800, canvasW() - 120);
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

    const canvasWide = Math.max(canvasW(), 900);
    const bandW = canvasWide - 120;
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
  pan.x = (canvasW() - layoutW * zoom) / 2 - minX * zoom;
  pan.y = (canvasH() - layoutH * zoom) / 2 - minY * zoom;

  window.__clusterBoxes = clusterBoxes;

  // Build nodeId → clusterBox map for edge routing
  window.__nodeClusterMap = new Map();
  for (const cb of clusterBoxes) {{
    for (const n of cb.clNodes) window.__nodeClusterMap.set(n.id, cb);
  }}
}}

// Alias kept for any direct callers
function layoutClustersAsGrid() {{ layoutClusters('dir'); }}

// ── Layered layout (by abstraction level) ──────────────────────────────────
// Uses BFS depth from sources (indegree=0) to assign horizontal lanes.
// Lane 0 = entry points / high-level files (top).
// Lane N = core utilities / low-level (bottom).
// Labels each lane with its role description.

function layoutLayered(nodeList, edgeList) {{
  nodeList = nodeList || visibleNodes || nodes;
  edgeList = edgeList || visibleEdges || edges;
  // Compute depth via BFS
  const inDeg = {{}}, adj = {{}};
  for (const n of nodeList) {{ inDeg[n.id] = 0; adj[n.id] = []; }}
  for (const e of edgeList) {{
    const srcId = e.source.id || e.source;
    const tgtId = e.target.id || e.target;
    if (inDeg[tgtId] !== undefined) inDeg[tgtId]++;
    if (adj[srcId]) adj[srcId].push(tgtId);
  }}
  const layer = {{}};
  const queue = nodeList.filter(n => inDeg[n.id] === 0).map(n => n.id);
  queue.forEach(id => {{ layer[id] = 0; }});
  for (let i = 0; i < queue.length; i++) {{
    const id = queue[i];
    for (const child of (adj[id] || [])) {{
      if (layer[child] === undefined || layer[child] < layer[id] + 1) {{
        layer[child] = layer[id] + 1;
        queue.push(child);
      }}
    }}
  }}
  for (const n of nodeList) if (layer[n.id] === undefined) layer[n.id] = 0;

  const maxLayer = Math.max(0, ...Object.values(layer));

  // Group nodes by layer
  const byLayer = {{}};
  for (let l = 0; l <= maxLayer; l++) byLayer[l] = [];
  for (const n of nodeList) byLayer[layer[n.id]].push(n);

  // Sort within each layer by number of connections (most connected = center)
  for (const l in byLayer) {{
    byLayer[l].sort((a, b) => (b.indegree + b.outdegree) - (a.indegree + a.outdegree));
  }}

  // Compute positions
  const LANE_PAD_TOP = 72;  // space for lane label + subtitle
  const NODE_GAP_X = 28;
  const NODE_GAP_Y = 40;
  const LANE_GAP = 30;

  let currentY = 40;
  window.__layerBands = [];

  for (let l = 0; l <= maxLayer; l++) {{
    const layerNodes = byLayer[l];
    if (layerNodes.length === 0) continue;

    const bandTop = currentY;
    currentY += LANE_PAD_TOP;

    // Lay out nodes in a centered row, wrapping if needed
    const maxPerRow = Math.max(1, Math.floor(1200 / (NODE_W + NODE_GAP_X)));
    const rows = [];
    for (let i = 0; i < layerNodes.length; i += maxPerRow) {{
      rows.push(layerNodes.slice(i, i + maxPerRow));
    }}

    for (const row of rows) {{
      const totalW = row.length * NODE_W + (row.length - 1) * NODE_GAP_X;
      const startX = (1200 - totalW) / 2 + NODE_W / 2;
      for (let i = 0; i < row.length; i++) {{
        const n = row[i];
        n.x = startX + i * (NODE_W + NODE_GAP_X);
        n.y = currentY + nodeHeight(n) / 2;
        n.vx = 0; n.vy = 0;
      }}
      currentY += Math.max(...row.map(n => nodeHeight(n))) + NODE_GAP_Y;
    }}

    const bandBottom = currentY + LANE_GAP / 2;
    currentY = bandBottom + LANE_GAP / 2;
  }}

  simRunning = false;
}}

function toggleLayout() {{
  const btn = document.getElementById('btnLayout');
  if (layoutMode === 'layered') {{
    layoutMode = 'force';
    btn.textContent = 'Force';
    btn.classList.remove('active');
    // Restart force sim
    simRunning = true;
    startAnim();
  }} else {{
    layoutMode = 'layered';
    btn.textContent = 'Layered';
    btn.classList.add('active');
    layoutLayered();
    draw();
    drawMinimap();
    // Auto-fit
    zoomToFit();
  }}
}}

// ── Layout ──────────────────────────────────────────────────────────────────

function viewportSize() {{
  const hostWidth = window.__prefxplainHostWidth;
  const hostHeight = window.__prefxplainHostHeight;
  if (hostWidth && hostHeight) {{
    return {{
      width: Math.max(1, Math.floor(hostWidth)),
      height: Math.max(1, Math.floor(hostHeight)),
    }};
  }}
  const vv = window.visualViewport;
  return {{
    width: Math.max(1, Math.floor(vv ? vv.width : window.innerWidth || 1)),
    height: Math.max(1, Math.floor(vv ? vv.height : window.innerHeight || 1)),
  }};
}}

function clampTopDetailsHeight(nextHeight, vp = viewportSize()) {{
  const headerHeight = Math.max(0, Math.ceil(panelHeader ? panelHeader.getBoundingClientRect().height : 0));
  const maxDetailsHeight = Math.max(MIN_TOP_DETAILS_HEIGHT, Math.min(MAX_TOP_DETAILS_HEIGHT, vp.height - headerHeight - 120));
  return {{
    headerHeight,
    detailsHeight: Math.max(MIN_TOP_DETAILS_HEIGHT, Math.min(maxDetailsHeight, nextHeight)),
  }};
}}

function applyViewportHeight() {{
  const vp = viewportSize();
  const {{ headerHeight, detailsHeight }} = clampTopDetailsHeight(topDetailsHeight, vp);
  topDetailsHeight = detailsHeight;
  rootEl.style.setProperty('--viewport-height', `${{vp.height}}px`);
  rootEl.style.setProperty('--top-panel-header-height', `${{headerHeight}}px`);
  rootEl.style.setProperty('--top-details-height', `${{detailsHeight}}px`);
  bodyEl.style.height = `${{vp.height}}px`;
  bodyEl.style.maxHeight = `${{vp.height}}px`;
  // centerPane and graphArea use flexbox (flex:1) to fill remaining space —
  // do NOT set explicit heights here or the canvas overflows below the viewport.
  return vp;
}}

function resize() {{
  applyViewportHeight();
  const dpr = window.devicePixelRatio || 1;
  const rect = graphArea.getBoundingClientRect();
  const cssW = Math.max(1, Math.floor(rect.width));
  const cssH = Math.max(1, Math.floor(rect.height));
  const bufW = Math.floor(cssW * dpr);
  const bufH = Math.floor(cssH * dpr);
  const prevWidth = canvas._cssW || 0;
  const prevHeight = canvas._cssH || 0;
  if (canvas.width !== bufW || canvas.height !== bufH) {{
    canvas.width = bufW;
    canvas.height = bufH;
    canvas.style.width = cssW + 'px';
    canvas.style.height = cssH + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }}
  canvas._cssW = cssW;
  canvas._cssH = cssH;
  return {{
    width: cssW, height: cssH, prevWidth, prevHeight,
    changed: prevWidth !== cssW || prevHeight !== cssH,
  }};
}}
function canvasW() {{ return canvas._cssW || Math.floor(canvas.width / (window.devicePixelRatio || 1)); }}
function canvasH() {{ return canvas._cssH || Math.floor(canvas.height / (window.devicePixelRatio || 1)); }}

function keepViewportCenter(prevWidth, prevHeight, width, height) {{
  if (!prevWidth || !prevHeight) return;
  pan.x += (width - prevWidth) / 2;
  pan.y += (height - prevHeight) / 2;
}}

function fitNodesForViewport() {{
  return (groupingState !== 'flat') ? visibleNodes : nodes;
}}

function graphBounds(nodeList) {{
  if (!nodeList || nodeList.length === 0) return null;
  let wx0 = Infinity, wy0 = Infinity, wx1 = -Infinity, wy1 = -Infinity;
  for (const n of nodeList) {{
    // Use expanded dimensions for open groups
    const box = (typeof nodeBox === 'function') ? nodeBox(n) : {{ x: n.x, y: n.y, w: n.w, h: n.h }};
    wx0 = Math.min(wx0, box.x - box.w / 2);
    wy0 = Math.min(wy0, box.y - box.h / 2);
    wx1 = Math.max(wx1, box.x + box.w / 2);
    wy1 = Math.max(wy1, box.y + box.h / 2);
  }}
  return {{ wx0, wy0, wx1, wy1 }};
}}

function computeFitZoom(width, height, nodeList) {{
  const bounds = graphBounds(nodeList);
  if (!bounds) return 1;
  // graphBounds only measures raw node boxes; intra-group edge labels
  // ("tests · xN") and group chrome extend beyond. Reserve slack so content
  // doesn't clip on the edges of the viewport.
  const pad = 48;
  const labelMarginX = 90;
  const labelMarginY = 40;
  const spanX = Math.max(bounds.wx1 - bounds.wx0 + labelMarginX * 2, 1);
  const spanY = Math.max(bounds.wy1 - bounds.wy0 + labelMarginY * 2, 1);
  const zx = Math.max(0.01, (width - pad * 2) / spanX);
  const zy = Math.max(0.01, (height - pad * 2) / spanY);
  return Math.max(0.3, Math.min(zx, zy, 2.5));
}}

function syncZoomScale(width, height) {{
  fitZoomLevel = computeFitZoom(width, height, fitNodesForViewport());
  if (fitZoomLevel > 0) {{
    userZoomScale = zoom / fitZoomLevel;
  }}
}}

function viewportCenterWorld(width, height) {{
  return {{
    x: (width / 2 - pan.x) / zoom,
    y: (height / 2 - pan.y) / zoom,
  }};
}}

function setViewportForWorldCenter(centerWorld, nextZoom, width, height) {{
  zoom = Math.max(0.5, Math.min(2.5, nextZoom));
  pan.x = width / 2 - centerWorld.x * zoom;
  pan.y = height / 2 - centerWorld.y * zoom;
}}

let _lastFlowDir = '';
function syncViewport() {{
  const size = resize();
  const centerWorld = (size.prevWidth && size.prevHeight)
    ? viewportCenterWorld(size.prevWidth, size.prevHeight)
    : null;
  if (size.changed) {{
    // Re-layout if auto flow direction changed due to aspect ratio
    if (flowDirection === 'auto' && groupingState !== 'flat') {{
      const newDir = resolvedFlowDirection();
      if (newDir !== _lastFlowDir) {{
        _lastFlowDir = newDir;
        relayout();
      }}
    }}
    fitZoomLevel = computeFitZoom(size.width, size.height, fitNodesForViewport());
    const shouldRefit =
      !panelResizeActive &&
      !viewportWasManuallyMoved &&
      !selectedNode &&
      !hoveredNode &&
      !searchQuery;

    if (shouldRefit) {{
      zoomToFit();
      drawMinimap();
      return;
    }}

    if (centerWorld) {{
      setViewportForWorldCenter(
        centerWorld,
        fitZoomLevel * userZoomScale,
        size.width,
        size.height,
      );
    }}
  }}
  clampPan();
  draw();
  drawMinimap();
}}

window.addEventListener('resize', () => {{ syncViewport(); }});
window.addEventListener('prefxplain-host-resize', () => {{ syncViewport(); }});
// Also use ResizeObserver for IDE preview resizes that do not emit window.resize.
if (typeof ResizeObserver !== 'undefined') {{
  new ResizeObserver(() => {{ syncViewport(); }}).observe(graphArea);
}}
if (window.visualViewport) {{
  window.visualViewport.addEventListener('resize', () => {{ syncViewport(); }});
}}
resize();

let lastViewportWatch = '';
function watchViewport() {{
  const vp = applyViewportHeight();
  const rect = graphArea.getBoundingClientRect();
  const next = `${{vp.width}}x${{vp.height}}:${{Math.floor(rect.width)}}x${{Math.floor(rect.height)}}`;
  if (next !== lastViewportWatch) {{
    lastViewportWatch = next;
    syncViewport();
  }}
  window.requestAnimationFrame(watchViewport);
}}
window.requestAnimationFrame(watchViewport);

function startPanelResize(clientY) {{
  if (leftPanel.classList.contains('collapsed')) {{
    leftPanel.classList.remove('collapsed');
    document.body.classList.remove('panel-collapsed');
    panelToggle.innerHTML = '&#x25B2;';
  }}
  panelResizeActive = true;
  panelResizeStartY = clientY;
  panelResizeStartHeight = topDetailsHeight;
  bodyEl.classList.add('panel-resizing');
}}

function updatePanelResize(clientY) {{
  if (!panelResizeActive) return;
  topDetailsHeight = panelResizeStartHeight + (clientY - panelResizeStartY);
  syncViewport();
}}

function stopPanelResize() {{
  if (!panelResizeActive) return;
  panelResizeActive = false;
  bodyEl.classList.remove('panel-resizing');
}}

panelResizer.addEventListener('mousedown', e => {{
  if (e.button !== 0) return;
  if (e.target && e.target.closest && e.target.closest('#panel-toggle')) return;
  e.preventDefault();
  startPanelResize(e.clientY);
}});

window.addEventListener('mousemove', e => {{
  if (!panelResizeActive) return;
  e.preventDefault();
  updatePanelResize(e.clientY);
}});

window.addEventListener('mouseup', () => {{ stopPanelResize(); }});
window.addEventListener('blur', () => {{ stopPanelResize(); }});

// ── Pan limits — keep the diagram in view ────────────────────────────────────
function clampPan() {{
  const list = (groupingState !== 'flat') ? visibleNodes : nodes;
  if (list.length === 0) return;
  let wx0 = Infinity, wy0 = Infinity, wx1 = -Infinity, wy1 = -Infinity;
  for (const n of list) {{
    wx0 = Math.min(wx0, n.x - (n.w || NODE_W) / 2);
    wy0 = Math.min(wy0, n.y - (n.h || NODE_H_BASE) / 2);
    wx1 = Math.max(wx1, n.x + (n.w || NODE_W) / 2);
    wy1 = Math.max(wy1, n.y + (n.h || NODE_H_BASE) / 2);
  }}
  // Allow panning up to half the canvas beyond the diagram edges
  const margin = 0.4;
  const minPanX = -(wx1 * zoom) + canvasW() * margin;
  const maxPanX = -(wx0 * zoom) + canvasW() * (1 - margin);
  const minPanY = -(wy1 * zoom) + canvasH() * margin;
  const maxPanY = -(wy0 * zoom) + canvasH() * (1 - margin);
  pan.x = Math.max(minPanX, Math.min(maxPanX, pan.x));
  pan.y = Math.max(minPanY, Math.min(maxPanY, pan.y));
}}

// ── Force simulation ─────────────────────────────────────────────────────────

const NODE_W = 220, NODE_H_BASE = 76, NODE_R = 6;
// Taller nodes need more space — bump repulsion and spring length
const REPULSION = 12000, SPRING_LEN = 280, SPRING_K = 0.04, GRAVITY = 0.012, DAMPING = 0.85;

// Fixed height sized to fit a short explanation under each node title.
function nodeHeight(n) {{
  return NODE_H_BASE;
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
  const cw = Math.max(canvasW(), 800), ch = Math.max(canvasH(), 600);
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
  x: n._ix !== undefined ? n._ix : canvasW() / 2 + (Math.random() - 0.5) * 400,
  y: n._iy !== undefined ? n._iy : canvasH() / 2 + (Math.random() - 0.5) * 300,
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

// Primary title text — use group label for solo-group nodes in grouped mode
function nodeTitleText(n) {{
  if (n.isGroup) return n.label;
  return n.short_title || derivedNodeTitle(n);
}}

function nodeSummaryText(n) {{
  if (n.description) return n.description.replace(WHITESPACE_RE, ' ').trim();
  if (n.role && ROLE_SUBTITLES[n.role]) return ROLE_SUBTITLES[n.role];
  return '';
}}

function truncateToFit(ctx, text, maxWidth) {{
  if (!text) return '';
  if (ctx.measureText(text).width <= maxWidth) return text;
  const ell = '\u2026';
  let lo = 0, hi = text.length;
  while (lo < hi) {{
    const mid = (lo + hi + 1) >> 1;
    if (ctx.measureText(text.slice(0, mid) + ell).width <= maxWidth) lo = mid;
    else hi = mid - 1;
  }}
  return lo > 0 ? text.slice(0, lo).trimEnd() + ell : ell;
}}

function wrapTextLines(ctx, text, maxWidth, maxLines) {{
  if (!text) return [];
  const words = text.split(WHITESPACE_RE).filter(Boolean);
  const lines = [];
  let current = '';
  for (const word of words) {{
    const test = current ? current + ' ' + word : word;
    if (ctx.measureText(test).width <= maxWidth) {{
      current = test;
      continue;
    }}
    if (current) lines.push(current);
    current = word;
    if (lines.length === maxLines - 1) break;
  }}
  if (current && lines.length < maxLines) lines.push(current);
  const consumedWords = lines.join(' ').split(WHITESPACE_RE).filter(Boolean).length;
  if (consumedWords < words.length && lines.length > 0) {{
    let tail = lines[lines.length - 1];
    while (tail && ctx.measureText(tail + '\u2026').width > maxWidth) tail = tail.slice(0, -1);
    lines[lines.length - 1] = (tail || lines[lines.length - 1]) + '\u2026';
  }}
  return lines;
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

const WHITESPACE_RE = new RegExp('\\\\s+', 'g');
const JS_EXT_RE = new RegExp('\\\\.(py|js|ts)$');

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
  if (!simRunning || layoutMode === 'layered') return;

  for (const n of nodes) {{ n.fx = 0; n.fy = 0; }}

  // O(n log n) repulsion via Barnes-Hut quadtree
  if (nodes.length > 0) {{
    const tree = buildQuadtree(nodes);
    for (const n of nodes) applyRepulsion(tree, n);
  }}

  // Gravity toward center
  for (const n of nodes) {{
    n.fx += (canvasW() / 2 - n.x) * GRAVITY;
    n.fy += (canvasH() / 2 - n.y) * GRAVITY;
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
let lastMouseWX = 0, lastMouseWY = 0; // last known mouse position in world coords

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
  const matchesNode = node => node.id.toLowerCase().includes(searchQuery)
    || node.label.toLowerCase().includes(searchQuery)
    || (node.description || '').toLowerCase().includes(searchQuery)
    || (node.short_title || '').toLowerCase().includes(searchQuery);
  if (matchesNode(n)) return true;
  if (n.isGroup && n.childIds) {{
    return n.childIds.some(childId => {{
      const child = nodeIndex[childId];
      return child ? matchesNode(child) : false;
    }});
  }}
  return false;
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

// ── Group color palette ─────────────────────────────────────────────────────
const GROUP_COLORS = [
  '#58a6ff', // blue
  '#7ee787', // green
  '#d2a8ff', // purple
  '#f0883e', // orange
  '#ff7b72', // red
  '#79c0ff', // light blue
  '#56d364', // lime
  '#f778ba', // pink
];
const _groupColorMap = {{}};
let _groupColorIdx = 0;
function groupColor(groupId) {{
  if (_groupColorMap[groupId]) return _groupColorMap[groupId];
  const c = GROUP_COLORS[_groupColorIdx % GROUP_COLORS.length];
  _groupColorIdx++;
  _groupColorMap[groupId] = c;
  return c;
}}

// Get the effective bounding box of a node (expanded if open group)
function nodeBox(n) {{
  if (n.isGroup && isGroupOpen(n)) {{
    const layout = layoutOpenGroupChildren(n);
    return {{ x: n.x, y: n.y - n._closedH / 2 + layout.openH / 2,
             w: layout.openW, h: layout.openH }};
  }}
  return {{ x: n.x, y: n.y, w: n.w, h: n.h }};
}}

function traceBlockShape(ctx, x, y, w, h, shape, radius) {{
  const normalized = shape || 'process';
  if (normalized === 'decision') {{
    ctx.beginPath();
    ctx.moveTo(x + w / 2, y);
    ctx.lineTo(x + w, y + h / 2);
    ctx.lineTo(x + w / 2, y + h);
    ctx.lineTo(x, y + h / 2);
    ctx.closePath();
    return;
  }}
  if (normalized === 'analysis') {{
    const inset = Math.max(18, Math.min(28, w * 0.12));
    ctx.beginPath();
    ctx.moveTo(x + inset, y);
    ctx.lineTo(x + w - inset, y);
    ctx.lineTo(x + w, y + h / 2);
    ctx.lineTo(x + w - inset, y + h);
    ctx.lineTo(x + inset, y + h);
    ctx.lineTo(x, y + h / 2);
    ctx.closePath();
    return;
  }}
  if (normalized === 'data') {{
    const skew = Math.max(16, Math.min(28, w * 0.12));
    ctx.beginPath();
    ctx.moveTo(x + skew, y);
    ctx.lineTo(x + w, y);
    ctx.lineTo(x + w - skew, y + h);
    ctx.lineTo(x, y + h);
    ctx.closePath();
    return;
  }}
  roundRect(ctx, x, y, w, h, normalized === 'entry' ? Math.max(radius, 18) : radius);
}}

// Inside a collapsed semantic group, draw a small row of sub-block shapes so
// the group reads as "a container with structured pieces" instead of "one fat
// card with a file count". For small groups (≤4 children) we draw each file
// as its own mini shape in its actual kind; for larger groups we show up to
// five distinct-kind chips with counts so the shape mix is still legible.
function drawGroupSubBlocks(ctx, group, sx, sy, sw, sh, topY, groupColorStr) {{
  if (!group || !group.childIds || group.childIds.length === 0) return;
  const children = group.childIds
    .map(id => nodeIndex[id])
    .filter(Boolean);
  if (children.length === 0) return;

  const bottomY = sy + sh / 2 - 12;
  const availableH = bottomY - topY;
  if (availableH < 18) return;

  const CHIP_W = 44;
  const CHIP_H = 20;
  const CHIP_GAP = 8;

  function kindOf(node) {{
    const semantic = FILE_SEMANTICS[node.id] || {{}};
    return semantic.kind || semantic.shape || node.kind || node.shape || 'process';
  }}

  // Draw the row of chips centered horizontally, clipped to the group width.
  function drawChipRow(items) {{
    const count = items.length;
    if (count === 0) return;
    const totalW = count * CHIP_W + (count - 1) * CHIP_GAP;
    let cursorX = sx - totalW / 2;
    const cy = bottomY - CHIP_H / 2;
    for (const item of items) {{
      ctx.save();
      ctx.fillStyle = '#0d1117';
      ctx.strokeStyle = groupColorStr;
      ctx.lineWidth = 1;
      traceBlockShape(ctx, cursorX, cy - CHIP_H / 2, CHIP_W, CHIP_H, item.shape, 3);
      ctx.fill();
      ctx.stroke();
      if (item.count > 1) {{
        ctx.fillStyle = groupColorStr;
        ctx.font = 'bold 10px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('x' + item.count, cursorX + CHIP_W / 2, cy);
      }}
      ctx.restore();
      cursorX += CHIP_W + CHIP_GAP;
    }}
  }}

  // Small groups: show every child as its own chip.
  if (children.length <= 4) {{
    const items = children.map(child => ({{ shape: kindOf(child), count: 1 }}));
    drawChipRow(items);
    return;
  }}

  // Larger groups: collapse to distinct kinds (max 5) with counts.
  const kindCounts = {{}};
  for (const child of children) {{
    const k = kindOf(child);
    kindCounts[k] = (kindCounts[k] || 0) + 1;
  }}
  const ordered = Object.entries(kindCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([shape, count]) => ({{ shape, count }}));
  drawChipRow(ordered);
}}

function draw() {{

  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas._cssW || canvas.width;
  const cssH = canvas._cssH || canvas.height;
  // Clear the full buffer, then reset dpr base transform
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.restore();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(zoom, zoom);

  // Cluster backgrounds
  drawClusters();

  // Layer bands — rendered only in flat mode. In semantic/grouped mode the
  // group containers already encode the architecture layers visually.
  if (groupingState === 'flat' && window.__layerBands && window.__layerBands.length) {{
    const BAND_COLORS = [
      {{ bg: '#22c55e12', border: '#22c55e30', text: '#22c55e' }},  // green  — entry points
      {{ bg: '#3b82f612', border: '#3b82f630', text: '#3b82f6' }},  // blue   — app logic
      {{ bg: '#a78bfa12', border: '#a78bfa30', text: '#a78bfa' }},  // purple — services
      {{ bg: '#f59e0b12', border: '#f59e0b30', text: '#f59e0b' }},  // amber  — models
      {{ bg: '#6b728012', border: '#6b728030', text: '#6b7280' }},  // gray   — config
      {{ bg: '#ef444412', border: '#ef444430', text: '#ef4444' }},  // red    — tests
    ];
    const bands = window.__layerBands;
    for (let i = 0; i < bands.length; i++) {{
      const b = bands[i];
      const palette = BAND_COLORS[i % BAND_COLORS.length];
      const orientation = b.orientation || 'horizontal';
      if (orientation === 'vertical') {{
        // Column band (horizontal flow): fills vertically, label on top.
        const left = typeof b.left === 'number' ? b.left : -2000;
        const right = typeof b.right === 'number' ? b.right : 4000;
        ctx.fillStyle = palette.bg;
        ctx.fillRect(left, -4000, right - left, 9000);
        ctx.strokeStyle = palette.border;
        ctx.lineWidth = 1.5 / zoom;
        ctx.beginPath();
        ctx.moveTo(left, -4000);
        ctx.lineTo(left, 5000);
        ctx.stroke();
        const labelY = (-pan.y / zoom) + 20 / zoom;
        ctx.font = `bold ${{14 / zoom}}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        ctx.fillStyle = palette.text;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(b.title, left + 12 / zoom, labelY);
        ctx.font = `${{11 / zoom}}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        ctx.fillStyle = '#6e7681';
        ctx.fillText(b.subtitle, left + 12 / zoom, labelY + 20 / zoom);
      }} else {{
        // Row band (vertical flow) — horizontal stripe.
        ctx.fillStyle = palette.bg;
        ctx.fillRect(-2000, b.top, 6000, b.bottom - b.top);
        ctx.strokeStyle = palette.border;
        ctx.lineWidth = 1.5 / zoom;
        ctx.beginPath();
        ctx.moveTo(-2000, b.top);
        ctx.lineTo(4000, b.top);
        ctx.stroke();
        // Lane title — positioned relative to viewport center, not world origin,
        // so it stays visible regardless of pan position.
        const labelX = (-pan.x / zoom) + 20 / zoom;
        ctx.font = `bold ${{14 / zoom}}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        ctx.fillStyle = palette.text;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(b.title, labelX, b.top + 8);
        ctx.font = `${{11 / zoom}}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        ctx.fillStyle = '#6e7681';
        ctx.fillText(b.subtitle, labelX, b.top + 28);
      }}
    }}
  }}

  // Pre-compute bidirectional pairs once per draw call
  const edgeKeySet = new Set(GRAPH.edges.map(e => e.source + '|' + e.target));

  // Draw arrowhead at (x2,y2) arriving from direction (x1,y1)
  function drawArrowHead(x1, y1, x2, y2, color, arrowSize) {{
    const angle = Math.atan2(y2 - y1, x2 - x1);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - arrowSize * Math.cos(angle - 0.55), y2 - arrowSize * Math.sin(angle - 0.55));
    ctx.lineTo(x2 - arrowSize * Math.cos(angle + 0.55), y2 - arrowSize * Math.sin(angle + 0.55));
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

  // ── Smart edge routing ────────────────────────────────────────────────
  // Routes edges around group bounding boxes using orthogonal paths.
  // Edges exit from the nearest side of the source, travel through clear
  // corridors between groups, and enter the nearest side of the target.

  function nodeEdgePoint(n, side) {{
    if (side === 'top')    return {{ x: n.x, y: n.y - n.h / 2 }};
    if (side === 'bottom') return {{ x: n.x, y: n.y + n.h / 2 }};
    if (side === 'left')   return {{ x: n.x - n.w / 2, y: n.y }};
    return                        {{ x: n.x + n.w / 2, y: n.y }};
  }}

  function bestSide(a, b) {{
    const dx = b.x - a.x, dy = b.y - a.y;
    if (Math.abs(dx) > Math.abs(dy)) {{
      return dx > 0 ? ['right', 'left'] : ['left', 'right'];
    }}
    return dy > 0 ? ['bottom', 'top'] : ['top', 'bottom'];
  }}

  function rectContains(box, x, y, pad) {{
    return x >= box.x - pad && x <= box.x + box.boxW + pad &&
           y >= box.y - pad && y <= box.y + box.boxH + pad;
  }}

  function segmentIntersectsRect(x1, y1, x2, y2, box, pad) {{
    const bx = box.x - pad, by = box.y - pad;
    const bw = box.boxW + 2 * pad, bh = box.boxH + 2 * pad;
    // Check if a horizontal or vertical segment crosses the box
    if (x1 === x2) {{ // vertical
      const minY = Math.min(y1, y2), maxY = Math.max(y1, y2);
      return x1 >= bx && x1 <= bx + bw && maxY >= by && minY <= by + bh;
    }}
    if (y1 === y2) {{ // horizontal
      const minX = Math.min(x1, x2), maxX = Math.max(x1, x2);
      return y1 >= by && y1 <= by + bh && maxX >= bx && minX <= bx + bw;
    }}
    return false;
  }}

  function drawRoutedEdge(a, b, color, lw, arrowSize) {{
    const boxes = (window.__clusterBoxes || []).filter(Boolean);
    const nodeCluster = window.__nodeClusterMap;
    const aBox = nodeCluster ? nodeCluster.get(a.id) : null;
    const bBox = nodeCluster ? nodeCluster.get(b.id) : null;

    // Pick exit/entry sides
    const [aSide, bSide] = bestSide(a, b);
    const start = nodeEdgePoint(a, aSide);
    const end = nodeEdgePoint(b, bSide);

    // Corridor offset based on edge hash to spread parallel edges
    const lane = edgeLaneIndex(a, b);
    const spread = (lane - 3.5) * 6 / zoom;

    // Compute midpoints for orthogonal path
    const midX = (start.x + end.x) / 2 + spread;
    const midY = (start.y + end.y) / 2 + spread;

    // Build candidate path points
    let waypoints;
    const isHorizontal = aSide === 'left' || aSide === 'right';
    if (isHorizontal) {{
      // Exit horizontally → vertical segment → enter horizontally
      waypoints = [start, {{x: midX, y: start.y}}, {{x: midX, y: end.y}}, end];
    }} else {{
      // Exit vertically → horizontal segment → enter vertically
      waypoints = [start, {{x: start.x, y: midY}}, {{x: end.x, y: midY}}, end];
    }}

    // Check if the middle segments pass through any box (that isn't source or target's box)
    const otherBoxes = boxes.filter(box => box !== aBox && box !== bBox);
    for (const box of otherBoxes) {{
      for (let i = 0; i < waypoints.length - 1; i++) {{
        if (segmentIntersectsRect(waypoints[i].x, waypoints[i].y,
            waypoints[i + 1].x, waypoints[i + 1].y, box, 4)) {{
          // Reroute around the box: go around its edge
          const boxCx = box.x + box.boxW / 2;
          const boxCy = box.y + box.boxH / 2;
          const goRight = midX > boxCx;
          const goDown = midY > boxCy;
          const detourX = goRight ? box.x + box.boxW + 16 / zoom : box.x - 16 / zoom;
          const detourY = goDown ? box.y + box.boxH + 16 / zoom : box.y - 16 / zoom;
          if (isHorizontal) {{
            waypoints = [start, {{x: detourX, y: start.y}}, {{x: detourX, y: end.y}}, end];
          }} else {{
            waypoints = [start, {{x: start.x, y: detourY}}, {{x: end.x, y: detourY}}, end];
          }}
          break; // one reroute is enough
        }}
      }}
    }}

    // Draw smooth path through waypoints
    ctx.beginPath();
    ctx.moveTo(waypoints[0].x, waypoints[0].y);
    for (let i = 1; i < waypoints.length; i++) {{
      const prev = waypoints[i - 1];
      const curr = waypoints[i];
      // Rounded corners: use a small arc radius
      if (i < waypoints.length - 1) {{
        const next = waypoints[i + 1];
        const r = Math.min(12 / zoom, Math.abs(curr.x - prev.x) / 2, Math.abs(curr.y - prev.y) / 2,
                           Math.abs(next.x - curr.x) / 2, Math.abs(next.y - curr.y) / 2) || 0;
        if (r > 0.5) {{
          ctx.arcTo(curr.x, curr.y, next.x, next.y, r);
        }} else {{
          ctx.lineTo(curr.x, curr.y);
        }}
      }} else {{
        ctx.lineTo(curr.x, curr.y);
      }}
    }}
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.stroke();

    // Arrowhead at the last segment
    const last = waypoints[waypoints.length - 1];
    const prev = waypoints[waypoints.length - 2];
    drawArrowHead(prev.x, prev.y, last.x, last.y, color, arrowSize);
  }}

  const nodeClusterMap = window.__nodeClusterMap;

  // ── Edge color palette (for source-colored edges) ─────────────────────
  const EDGE_PALETTE = [
    '#58a6ff', '#7ee787', '#d2a8ff', '#f0883e', '#ff7b72',
    '#79c0ff', '#56d364', '#bc8cff', '#ffa657', '#ffa198',
  ];
  const edgeColorCache = {{}};
  let edgeColorIdx = 0;
  function edgeColorForSource(srcId) {{
    if (edgeColorCache[srcId]) return edgeColorCache[srcId];
    // Use source group's color for consistency
    const c = groupColor(srcId) || EDGE_PALETTE[edgeColorIdx++ % EDGE_PALETTE.length];
    edgeColorCache[srcId] = c;
    return c;
  }}

  // Find the point where a line from (fx,fy) to rect center (nx,ny) exits the rect border
  function rectEdgePoint(fx, fy, nx, ny, hw, hh) {{
    const dx = fx - nx, dy = fy - ny;
    if (dx === 0 && dy === 0) return {{ x: nx + hw, y: ny }};
    const sx = dx !== 0 ? hw / Math.abs(dx) : 1e9;
    const sy = dy !== 0 ? hh / Math.abs(dy) : 1e9;
    const s = Math.min(sx, sy);
    return {{ x: nx + dx * s, y: ny + dy * s }};
  }}

  // Check if a straight line from (x1,y1)→(x2,y2) intersects a rect
  function lineHitsRect(x1, y1, x2, y2, rx, ry, rw, rh, pad) {{
    const left = rx - rw / 2 - pad, right = rx + rw / 2 + pad;
    const top = ry - rh / 2 - pad, bottom = ry + rh / 2 + pad;
    // Parametric line: P(t) = (x1,y1) + t*(x2-x1, y2-y1), t in [0,1]
    const dx = x2 - x1, dy = y2 - y1;
    let tmin = 0, tmax = 1;
    if (dx !== 0) {{
      let t1 = (left - x1) / dx, t2 = (right - x1) / dx;
      if (t1 > t2) {{ const tmp = t1; t1 = t2; t2 = tmp; }}
      tmin = Math.max(tmin, t1); tmax = Math.min(tmax, t2);
    }} else if (x1 < left || x1 > right) return false;
    if (dy !== 0) {{
      let t1 = (top - y1) / dy, t2 = (bottom - y1) / dy;
      if (t1 > t2) {{ const tmp = t1; t1 = t2; t2 = tmp; }}
      tmin = Math.max(tmin, t1); tmax = Math.min(tmax, t2);
    }} else if (y1 < top || y1 > bottom) return false;
    return tmin <= tmax && tmax > 0.05 && tmin < 0.95;
  }}

  // Collect all obstacle rects (excluding source and target)
  function getObstacles(a, b) {{
    const blocks = (groupingState !== 'flat') ? visibleNodes : nodes;
    const obs = [];
    for (const n of blocks) {{
      if (n === a || n === b) continue;
      const box = nodeBox(n);
      obs.push(box);
    }}
    return obs;
  }}

  // Shift a border point along the edge it sits on, clamped to block bounds
  function shiftAlongBorder(pt, box, offset) {{
    const hw = box.w / 2 - 8, hh = box.h / 2 - 8;
    const dx = Math.abs(pt.x - box.x), dy = Math.abs(pt.y - box.y);
    if (dx * box.h <= dy * box.w) {{
      // Closer to top/bottom edge → shift horizontally
      return {{ x: box.x + Math.max(-hw, Math.min(hw, (pt.x - box.x) + offset)), y: pt.y }};
    }}
    // Closer to left/right edge → shift vertically
    return {{ x: pt.x, y: box.y + Math.max(-hh, Math.min(hh, (pt.y - box.y) + offset)) }};
  }}

  // Draw arrow from a→b, routing around any blocking nodes
  // laneIdx = unique index for this edge, used to offset routing lanes
  function drawEdgeArrow(a, b, color, lw, arrowSize, weight, bidi, laneIdx, labelText) {{
    const aBox = nodeBox(a), bBox = nodeBox(b);
    // Lane spacing MUST be zoom-invariant in world units. Previously this
    // was `18 / zoom` to keep screen spacing constant, but that made corridor
    // world positions shift with zoom — close enough at high zoom that
    // lineHitsRect (fixed 4-unit pad) would flag the route as blocked and
    // flip to the alt side. Result: edges visibly jumped as the user zoomed.
    const LANE_SPREAD = 18;
    const laneOffset = (laneIdx - (totalLanes - 1) / 2) * LANE_SPREAD;
    const obstacles = getObstacles(a, b);

    // Check if straight line hits any obstacle
    const blockers = [];
    for (const ob of obstacles) {{
      if (lineHitsRect(aBox.x, aBox.y, bBox.x, bBox.y, ob.x, ob.y, ob.w, ob.h, 12)) {{
        blockers.push(ob);
      }}
    }}

    // Build waypoints
    let waypoints;
    if (blockers.length === 0) {{
      // Straight: compute edge points on borders, then shift along the border
      let sp = rectEdgePoint(bBox.x, bBox.y, aBox.x, aBox.y, aBox.w / 2 + 2, aBox.h / 2 + 2);
      let ep = rectEdgePoint(aBox.x, aBox.y, bBox.x, bBox.y, bBox.w / 2 + 2, bBox.h / 2 + 2);
      sp = shiftAlongBorder(sp, aBox, laneOffset);
      ep = shiftAlongBorder(ep, bBox, laneOffset);
      waypoints = [sp, ep];
    }} else {{
      // Route around ALL blockers with per-edge lane offset.
      // Corridor axis depends on the flow direction:
      //   vertical flow   → corridor is a vertical line (constant X, vary Y)
      //   horizontal flow → corridor is a horizontal line (constant Y, vary X)
      const routeOffset = laneIdx * LANE_SPREAD;
      // Zoom-invariant corridor margin (world units). See LANE_SPREAD note
      // above — any /zoom here makes routing non-deterministic.
      const margin = 24;
      const dir = resolvedFlowDirection(); // 'horizontal' | 'vertical'

      // Rule: arrows must never pass through blocks. Build candidate
      // waypoints for the chosen side, validate against every obstacle,
      // and if blocked try the opposite side. If both sides are blocked
      // at the base offset, push both sides outward one lane width at a
      // time until one becomes clear (bounded by MAX_PUSHES).
      const MAX_PUSHES = 16;

      const routeWaypoints = (primarySide, extraPush) => {{
        const off = margin + routeOffset + extraPush;
        if (dir === 'horizontal') {{
          const goDown = aBox.y <= bBox.y;
          const pickSide = primarySide === 'primary' ? goDown : !goDown;
          let sideY;
          if (pickSide) {{
            sideY = Math.max(aBox.y + aBox.h / 2, bBox.y + bBox.h / 2);
            for (const ob of blockers) sideY = Math.max(sideY, ob.y + ob.h / 2);
            sideY += off;
          }} else {{
            sideY = Math.min(aBox.y - aBox.h / 2, bBox.y - bBox.h / 2);
            for (const ob of blockers) sideY = Math.min(sideY, ob.y - ob.h / 2);
            sideY -= off;
          }}
          const sp = rectEdgePoint(aBox.x, sideY, aBox.x, aBox.y, aBox.w / 2 + 2, aBox.h / 2 + 2);
          const ep = rectEdgePoint(bBox.x, sideY, bBox.x, bBox.y, bBox.w / 2 + 2, bBox.h / 2 + 2);
          return [sp, {{ x: sp.x, y: sideY }}, {{ x: ep.x, y: sideY }}, ep];
        }} else {{
          const goRight = aBox.x <= bBox.x;
          const pickSide = primarySide === 'primary' ? goRight : !goRight;
          let sideX;
          if (pickSide) {{
            sideX = Math.max(aBox.x + aBox.w / 2, bBox.x + bBox.w / 2);
            for (const ob of blockers) sideX = Math.max(sideX, ob.x + ob.w / 2);
            sideX += off;
          }} else {{
            sideX = Math.min(aBox.x - aBox.w / 2, bBox.x - bBox.w / 2);
            for (const ob of blockers) sideX = Math.min(sideX, ob.x - ob.w / 2);
            sideX -= off;
          }}
          const sp = rectEdgePoint(sideX, aBox.y, aBox.x, aBox.y, aBox.w / 2 + 2, aBox.h / 2 + 2);
          const ep = rectEdgePoint(sideX, bBox.y, bBox.x, bBox.y, bBox.w / 2 + 2, bBox.h / 2 + 2);
          return [sp, {{ x: sideX, y: sp.y }}, {{ x: sideX, y: ep.y }}, ep];
        }}
      }};

      const waypointsHit = (wps) => {{
        for (const ob of obstacles) {{
          for (let i = 0; i < wps.length - 1; i++) {{
            if (lineHitsRect(wps[i].x, wps[i].y, wps[i+1].x, wps[i+1].y,
                ob.x, ob.y, ob.w, ob.h, 4)) return true;
          }}
        }}
        return false;
      }};

      let chosen = null;
      for (let push = 0; push < MAX_PUSHES && !chosen; push++) {{
        const extra = push * LANE_SPREAD;
        const primary = routeWaypoints('primary', extra);
        if (!waypointsHit(primary)) {{ chosen = primary; break; }}
        const alt = routeWaypoints('alt', extra);
        if (!waypointsHit(alt)) {{ chosen = alt; break; }}
      }}
      // Fall back to the furthest-pushed primary if nothing was clear,
      // so we still render a route instead of a broken edge.
      waypoints = chosen || routeWaypoints('primary', MAX_PUSHES * LANE_SPREAD);
    }}

    // Shorten endpoints so the line stops at the arrowhead base (not the tip)
    const tipLen = arrowSize * 0.7;
    const lastPt = waypoints[waypoints.length - 1];
    const prevPt = waypoints[waypoints.length - 2];
    // Only shorten if the segment is long enough
    const lastSegLen = Math.sqrt((lastPt.x - prevPt.x) ** 2 + (lastPt.y - prevPt.y) ** 2);
    let shortenedEnd = lastPt;
    if (lastSegLen > tipLen * 2) {{
      const endAngle = Math.atan2(lastPt.y - prevPt.y, lastPt.x - prevPt.x);
      shortenedEnd = {{
        x: lastPt.x - Math.cos(endAngle) * tipLen,
        y: lastPt.y - Math.sin(endAngle) * tipLen,
      }};
    }}
    let shortenedStart = waypoints[0];
    if (bidi && waypoints.length >= 2) {{
      const firstPt = waypoints[0], secPt = waypoints[1];
      const firstSegLen = Math.sqrt((firstPt.x - secPt.x) ** 2 + (firstPt.y - secPt.y) ** 2);
      if (firstSegLen > tipLen * 2) {{
        const startAngle = Math.atan2(firstPt.y - secPt.y, firstPt.x - secPt.x);
        shortenedStart = {{
          x: firstPt.x - Math.cos(startAngle) * tipLen,
          y: firstPt.y - Math.sin(startAngle) * tipLen,
        }};
      }}
    }}

    // Draw path with rounded corners (using shortened endpoints)
    const drawPts = [...waypoints];
    drawPts[0] = shortenedStart;
    drawPts[drawPts.length - 1] = shortenedEnd;

    ctx.beginPath();
    ctx.moveTo(drawPts[0].x, drawPts[0].y);
    for (let i = 1; i < drawPts.length; i++) {{
      if (i < drawPts.length - 1) {{
        const p = drawPts[i - 1], c = drawPts[i], n = drawPts[i + 1];
        const r = Math.min(16 / zoom,
          (Math.abs(c.x - p.x) / 2) || 1e9,
          (Math.abs(c.y - p.y) / 2) || 1e9,
          (Math.abs(n.x - c.x) / 2) || 1e9,
          (Math.abs(n.y - c.y) / 2) || 1e9);
        if (r > 0.5) {{ ctx.arcTo(c.x, c.y, n.x, n.y, r); }}
        else {{ ctx.lineTo(c.x, c.y); }}
      }} else {{
        ctx.lineTo(drawPts[i].x, drawPts[i].y);
      }}
    }}
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.stroke();

    // Queue arrowheads to draw AFTER nodes (so they appear on top)
    _deferredArrowheads.push({{ fx: prevPt.x, fy: prevPt.y, tx: lastPt.x, ty: lastPt.y, color, size: arrowSize, alpha: ctx.globalAlpha }});
    if (bidi) {{
      _deferredArrowheads.push({{ fx: waypoints[1].x, fy: waypoints[1].y, tx: waypoints[0].x, ty: waypoints[0].y, color, size: arrowSize, alpha: ctx.globalAlpha }});
    }}

    // Semantic label / edge weight
    const edgeBadgeText = labelText
      ? (weight > 1 ? `${{labelText}} · ×${{weight}}` : labelText)
      : (weight > 1 ? '×' + weight : '');
    if (edgeBadgeText) {{
      const midIdx = Math.floor(waypoints.length / 2);
      const lx = (waypoints[midIdx - 1].x + waypoints[midIdx].x) / 2;
      const ly = (waypoints[midIdx - 1].y + waypoints[midIdx].y) / 2;
      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const lsx = lx * zoom + pan.x, lsy = ly * zoom + pan.y;
      ctx.font = 'bold 14px -apple-system, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const text = edgeBadgeText;
      const tw = ctx.measureText(text).width + 8;
      ctx.fillStyle = '#0d1117cc';
      ctx.beginPath();
      ctx.roundRect(lsx - tw / 2, lsy - 10, tw, 20, 5);
      ctx.fill();
      ctx.fillStyle = color;
      ctx.fillText(text, lsx, lsy);
      ctx.restore();
    }}
  }}

  // Deferred arrowheads: drawn AFTER nodes so they're always visible on top
  const _deferredArrowheads = [];

  // Edges (use visibleEdges when grouping is active)
  const drawEdges = (groupingState !== 'flat') ? visibleEdges : edges;
  // Build bidi set + dedup tracker
  const drawEdgeKeySet = new Set(drawEdges.map(e => (e._srcId || e.source.id || e.source) + '|' + (e._tgtId || e.target.id || e.target)));
  const drawnBidiPairs = new Set();

  // Pre-assign lane indices so parallel edges don't cross each other.
  //
  // Rule: when several edges share a routing corridor (e.g. all detour under
  // the same row of nodes), the edge with the SHORTEST run turns off the
  // corridor first. It must sit on the INNERMOST lane (laneIdx 0 = closest
  // to nodes) so its vertical leg has nothing to cross. Longer-running edges
  // sit on outer lanes.
  //
  // Implementation: group edges by source, then sort each group by the
  // distance the edge travels along the flow axis (target-minus-source on
  // the primary axis). Shortest distance → smallest laneIdx. Edges from
  // different sources are kept in their original relative order so bundles
  // from the same block stay contiguous.
  const _flowDir = resolvedFlowDirection();
  const _edgeDistance = (e) => {{
    const a = e.source, b = e.target;
    if (!a || !b || typeof a.x !== 'number' || typeof b.x !== 'number') return 0;
    return _flowDir === 'horizontal'
      ? Math.abs(b.x - a.x)
      : Math.abs(b.y - a.y);
  }};
  const _bySource = new Map();
  const _sourceOrder = [];
  drawEdges.forEach((e, i) => {{
    const sId = e._srcId || (e.source && e.source.id) || e.source;
    if (!_bySource.has(sId)) {{
      _bySource.set(sId, []);
      _sourceOrder.push(sId);
    }}
    _bySource.get(sId).push({{ edge: e, origIdx: i }});
  }});
  const edgeLaneMap = {{}};
  let _laneCounter = 0;
  for (const sId of _sourceOrder) {{
    const bucket = _bySource.get(sId);
    // Stable sort: shortest run first (innermost lane), ties keep original order.
    bucket.sort((p, q) => {{
      const d = _edgeDistance(p.edge) - _edgeDistance(q.edge);
      return d !== 0 ? d : p.origIdx - q.origIdx;
    }});
    for (const {{ edge }} of bucket) {{
      const s = edge._srcId || (edge.source && edge.source.id) || edge.source;
      const t = edge._tgtId || (edge.target && edge.target.id) || edge.target;
      edgeLaneMap[s + '|' + t] = _laneCounter++;
    }}
  }}
  const totalLanes = _laneCounter || 1;

  for (const e of drawEdges) {{
    const a = e.source, b = e.target;
    if (!isVisible(a) || !isVisible(b)) continue;

    const srcId = e._srcId || a.id;
    const tgtId = e._tgtId || b.id;

    // Detect bidirectional
    const bidi = drawEdgeKeySet.has(tgtId + '|' + srcId) || edgeKeySet.has(b.id + '|' + a.id);
    // Skip reverse of a bidi pair (already drawn with double arrowheads)
    if (bidi) {{
      const pairKey = [srcId, tgtId].sort().join('|');
      if (drawnBidiPairs.has(pairKey)) continue;
      drawnBidiPairs.add(pairKey);
    }}

    const focalId = selectedNode ? selectedNode.id : (hoveredNode ? hoveredNode.id : null);
    const focalGroupId = focalId ? (nodeToGroup[focalId] || null) : null;
    const isDirect = focalId && (a.id === focalId || b.id === focalId
      || (focalGroupId && (a.id === focalGroupId || b.id === focalGroupId)));
    const faded = highlightSet && !isDirect && !(highlightSet.has(a.id) && highlightSet.has(b.id));

    if (edgeMode === 'hover' && !isDirect) continue;

    const isCycle = isCycleEdge(e);

    let alpha;
    if (faded) alpha = 0.06;
    else if (isDirect) alpha = isCycle ? 0.95 : 0.9;
    else alpha = isCycle ? 0.7 : 0.45;
    ctx.globalAlpha = alpha;

    const edgeColor = isCycle ? '#f85149' : edgeColorForSource(srcId);
    // For bidi, combine weights from both directions
    let weight = e.weight || 1;
    if (bidi) {{
      const reverse = drawEdges.find(re => (re._srcId || re.source.id) === tgtId && (re._tgtId || re.target.id) === srcId);
      if (reverse) weight += (reverse.weight || 1);
    }}
    const baseLw = isCycle ? 5 : (4 + (weight > 1 ? Math.log2(weight) * 1.5 : 0));
    const lw = baseLw / zoom;
    const arrowSz = (isCycle ? 24 : 20) / zoom;

    const laneIdx = edgeLaneMap[srcId + '|' + tgtId] || 0;
    const edgeLabel = typeof e.label === 'string' ? e.label : '';
    drawEdgeArrow(a, b, edgeColor, lw, arrowSz, weight, bidi, laneIdx, edgeLabel);
  }}

  ctx.globalAlpha = 1;

  // Nodes (use visibleNodes when grouping is active)
  // Build draw list: closed groups first, then open groups + children on top
  let drawNodes;
  const openGroupChildSet = new Set();
  if (groupingState !== 'flat') {{
    const closedGroups = [];
    const openGroups = [];
    for (const g of visibleNodes) {{
      if (g.isGroup && isGroupOpen(g)) {{
        openGroups.push(g);
        const layout = layoutOpenGroupChildren(g);
        for (const item of layout.items) {{
          openGroups.push(item.node);
          openGroupChildSet.add(item.node.id);
        }}
      }} else {{
        closedGroups.push(g);
      }}
    }}
    drawNodes = [...closedGroups, ...openGroups];
  }} else {{
    drawNodes = nodes;
  }}
  for (const n of drawNodes) {{
    if (!isVisible(n)) continue;
    const faded = highlightSet && !highlightSet.has(n.id);
    ctx.globalAlpha = faded ? 0.15 : 1;

    const nw = n.w, nh = n.h;
    const x = n.x - nw / 2, y = n.y - nh / 2;
    const color = nodeColor(n);
    const isSelected = selectedNode === n;
    const isHovered = hoveredNode === n;
    const inCycle = n.inCycle;
    const inBlast = blastRadiusSet.has(n.id);

    // Singleton groups render as if they were a regular file node:
    // the group label is the title, the child's shape is the block shape,
    // and the group-specific chrome (kind chip + file count + stacked
    // cards) is skipped. Drop through to the standard node render below.
    const isSingletonGroup = n.isGroup && (n.childIds || []).length === 1;

    // Groups handle their own card drawing (collapsed or expanded)
    if (n.isGroup && !isSingletonGroup) {{
      const open = isGroupOpen(n);
      const pinned = pinnedGroupIds.has(n.id);

      if (open) {{
        // ── Expanded: draw container background, children drawn later ──
        const layout = layoutOpenGroupChildren(n);
        const gTop = n.y - n.h / 2;
        const gLeft = n.x - layout.openW / 2;
        // Position children in world coords (used by the node draw loop below)
        for (const item of layout.items) {{
          item.node.x = item.cx;
          item.node.y = item.cy;
        }}
        // Container background with group color
        const gc = groupColor(n.id);
        // Slightly tinted background (not pitch-black) so the container reads
        // as a distinct surface rather than a window cut out of the backdrop.
        ctx.fillStyle = gc + '0c';
        ctx.strokeStyle = gc;
        ctx.lineWidth = Math.max(1.5, 2.5 / zoom);
        roundRect(ctx, gLeft, gTop, layout.openW, layout.openH, 10);
        ctx.fill(); ctx.stroke();
        // Header band — full-opacity group-color tint across the top
        ctx.fillStyle = gc + '30';
        roundRect(ctx, gLeft + 1.5, gTop + 1.5, layout.openW - 3, OPEN_GROUP_HEADER, {{ tl: 9, tr: 9, bl: 0, br: 0 }});
        ctx.fill();
        // Separator line between header and body
        ctx.strokeStyle = gc + '60';
        ctx.lineWidth = Math.max(0.5, 0.8 / zoom);
        ctx.beginPath();
        ctx.moveTo(gLeft + 8, gTop + OPEN_GROUP_HEADER);
        ctx.lineTo(gLeft + layout.openW - 8, gTop + OPEN_GROUP_HEADER);
        ctx.stroke();
        ctx.shadowBlur = 0;
        // Header in screen space — always render if container is large enough
        if (layout.openW * zoom >= 80) {{
          ctx.save();
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          const sx = n.x * zoom + pan.x;
          const sy = gTop * zoom + pan.y;
          const sw = layout.openW * zoom;
          const hh = OPEN_GROUP_HEADER * zoom; // header height in screen px
          // Clip to header area so long labels don't overflow into body
          ctx.save();
          ctx.beginPath();
          // Strict clip to actual header height — extending beyond hh lets text
          // render in the body where child card backgrounds cover it.
          ctx.rect(sx - sw/2 + 2, sy + 1, sw - 4, hh - 2);
          ctx.clip();
          // Proportional font sizes and positions within the real header height.
          const kindLabel = humanizeSemanticKind(n.kind || n.shape || 'process').toUpperCase();
          const kindFont = Math.max(7, Math.min(11, Math.floor(hh * 0.18)));
          const titleFont = Math.max(9, Math.min(16, Math.floor(hh * 0.28)));
          const kindY = sy + Math.max(2, Math.floor(hh * 0.10));
          const titleY = kindY + kindFont + Math.max(2, Math.floor(hh * 0.06));
          ctx.font = `bold ${{kindFont}}px -apple-system, sans-serif`;
          ctx.fillStyle = gc + 'cc';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'top';
          ctx.fillText(kindLabel, sx - sw/2 + 12, kindY);
          // File count — top-right of header, same row as kind label
          ctx.font = `${{kindFont}}px -apple-system, sans-serif`;
          ctx.fillStyle = gc + 'aa';
          ctx.textAlign = 'right';
          ctx.fillText(n.fileCount + (n.fileCount === 1 ? ' file' : ' files'), sx + sw/2 - 12, kindY);
          // Group label — only render if it fits within the header
          if (titleY + titleFont < sy + hh) {{
            ctx.font = `bold ${{titleFont}}px -apple-system, sans-serif`;
            ctx.fillStyle = '#e6edf3';
            ctx.textAlign = 'left';
            ctx.fillText(n.label, sx - sw/2 + 12, titleY);
          }}
          ctx.restore(); // end header clip
          ctx.restore();
        }}
      }} else {{
        // ── Collapsed: stacked-cards with group color ─────────────────
        const gc = groupColor(n.id);
        const shape = n.shape || n.kind || 'process';
        ctx.fillStyle = '#1a1f26';
        ctx.strokeStyle = gc + '40';
        ctx.lineWidth = 0.5 / zoom;
        traceBlockShape(ctx, x + 4, y + 4, nw, nh, shape, NODE_R); ctx.fill(); ctx.stroke();
        traceBlockShape(ctx, x + 2, y + 2, nw, nh, shape, NODE_R); ctx.fill(); ctx.stroke();
        // Main card with colored border
        ctx.fillStyle = isHovered ? '#21262d' : '#161b22';
        ctx.strokeStyle = isHovered ? gc : gc + '80';
        ctx.lineWidth = (isHovered ? 2 : 1.5) / zoom;
        if (shape === 'external' || shape === 'test') ctx.setLineDash([8 / zoom, 6 / zoom]);
        traceBlockShape(ctx, x, y, nw, nh, shape, NODE_R); ctx.fill(); ctx.stroke();
        ctx.setLineDash([]);
        // Color bar on left
        if (shape === 'process' || shape === 'entry' || shape === 'external' || shape === 'test') {{
          ctx.fillStyle = gc;
          roundRect(ctx, x, y, 5, nh, {{ tl: NODE_R, bl: NODE_R, tr: 0, br: 0 }}); ctx.fill();
        }}
        ctx.shadowBlur = 0;
        // Text in screen space
        if (nw * zoom >= 40) {{
          ctx.save();
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          const sx = n.x * zoom + pan.x, sy = n.y * zoom + pan.y;
          const sw = nw * zoom, sh = nh * zoom;
          ctx.beginPath();
          ctx.rect(sx - sw/2, sy - sh/2, sw, sh);
          ctx.clip();
          ctx.font = 'bold 10px -apple-system, sans-serif';
          ctx.fillStyle = '#8b949e';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(humanizeSemanticKind(shape).toUpperCase(), sx, sy - sh / 2 + 12);
          ctx.font = 'bold 18px -apple-system, sans-serif';
          ctx.fillStyle = gc;
          const groupTitleLines = wrapTextLines(ctx, n.label, sw - 28, 2);
          let groupY = sy - sh / 2 + 30;
          groupTitleLines.forEach(line => {{
            ctx.fillText(line, sx, groupY);
            groupY += 20;
          }});
          ctx.font = '13px -apple-system, sans-serif';
          ctx.fillStyle = '#6e7681';
          ctx.fillText(n.fileCount + (n.fileCount === 1 ? ' file' : ' files'), sx, groupY + 4);
          let subRowBottom = groupY + 22;
          if (n.description && sh > 60) {{
            ctx.font = '13px -apple-system, sans-serif';
            ctx.fillStyle = '#6e7681';
            const descLines = wrapTextLines(ctx, n.description, sw - 20, 2);
            let descY = groupY + 18;
            descLines.forEach(line => {{
              ctx.fillText(line, sx, descY);
              descY += 15;
            }});
            subRowBottom = descY;
          }}
          // Sub-block hints: show that this group CONTAINS structured pieces,
          // not just a file count. Tiny traced shapes of the children's kinds
          // (or the actual children if the group is small).
          drawGroupSubBlocks(ctx, n, sx, sy, sw, sh, subRowBottom, gc);
          ctx.restore();
        }}
      }}
      continue;
    }}

    // ── Regular file node card background ──────────────────────────────
    const semantic = fileSemantic(n);
    const nodeShape = semantic.shape || n.shape || n.kind || 'process';
    // Nodes drawn inside an open group container get a simplified "component
    // block" style — just the title, no description or footer, with a
    // group-color border/bar so they read as parts of the parent block.
    const isGroupChild = openGroupChildSet.has(n.id);
    const parentGroupId = isGroupChild ? nodeToGroup[n.id] : null;
    const parentGc = parentGroupId ? groupColor(parentGroupId) : null;

    // Shadow for selected/hovered/blast
    if (isSelected || isHovered || inBlast) {{
      ctx.shadowColor = inBlast ? '#f59e0b' : color;
      ctx.shadowBlur = (isSelected ? 14 : inBlast ? 10 : 6) / zoom;
    }}
    ctx.fillStyle = isSelected ? color : (inBlast ? '#2d2008' : (isGroupChild ? '#1a212b' : (isHovered ? '#21262d' : '#161b22')));
    ctx.strokeStyle = inCycle ? '#f85149' : (inBlast ? '#f59e0b' : (isSelected ? color : (isGroupChild && parentGc ? parentGc + '70' : (isHovered ? color : '#30363d'))));
    ctx.lineWidth = (inCycle ? 2 : isSelected ? 2 : inBlast ? 1.5 : isGroupChild ? 0.8 : 1) / zoom;
    if (nodeShape === 'external' || nodeShape === 'test') ctx.setLineDash([8 / zoom, 6 / zoom]);
    traceBlockShape(ctx, x, y, nw, nh, nodeShape, NODE_R);
    ctx.fill();
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.shadowBlur = 0;
    // Left accent bar — group color for group children, language color otherwise
    if (!isSelected && (nodeShape === 'process' || nodeShape === 'entry' || nodeShape === 'external' || nodeShape === 'test')) {{
      ctx.fillStyle = isGroupChild && parentGc ? parentGc : color;
      roundRect(ctx, x, y, isGroupChild ? 3 : 4, nh, {{ tl: NODE_R, bl: NODE_R, tr: 0, br: 0 }});
      ctx.fill();
    }}
    // Cycle indicator (right bar, red)
    if (inCycle && !isSelected) {{
      ctx.fillStyle = '#f85149';
      roundRect(ctx, x + nw - 4, y, 4, nh, {{ tl: 0, bl: 0, tr: NODE_R, br: NODE_R }});
      ctx.fill();
    }}

    // LOD: skip text if card is too small on screen
    if (nw * zoom < 75 || nh * zoom < 36) {{
      if (nw * zoom >= 36 && nh * zoom >= 22) {{
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.font = 'bold 12px -apple-system, sans-serif';
        ctx.fillStyle = '#8b949e';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        // Truncate to the card's screen width so long titles don't bleed
        // into adjacent cards. Leave ~12px total horizontal padding.
        const lodMaxW = Math.max(16, nw * zoom - 12);
        const lodText = truncateToFit(ctx, nodeTitleText(n), lodMaxW);
        ctx.fillText(lodText, n.x * zoom + pan.x, n.y * zoom + pan.y);
        ctx.restore();
      }}
      continue;
    }}
    // Group children: always compact (title only — no description or footer)
    const compactCard = isGroupChild || nh * zoom < 90;

    // Clip ALL text drawing to the card rectangle — prevents overflow onto adjacent cards
    // Text is drawn in SCREEN SPACE (constant 12px size regardless of zoom).
    const screenX = n.x * zoom + pan.x;
    const screenY = n.y * zoom + pan.y;
    const screenW = nw * zoom;
    const screenH = nh * zoom;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // reset to screen coords (dpr-aware)
    ctx.beginPath();
    traceBlockShape(ctx, screenX - screenW/2 + 1, screenY - screenH/2 + 1, screenW - 2, screenH - 2, nodeShape, NODE_R * zoom);
    ctx.clip();

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    const textColor = isSelected ? nodeTextColor(n) : '#e6edf3';
    const mutedColor = isSelected ? 'rgba(255,255,255,0.7)' : '#8b949e';
    const divColor    = isSelected ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.08)';

    // All drawing is in screen space (setTransform reset above).
    // innerW/positions in screen px — font sizes are fixed (not /zoom).
    const padding = 8;
    const innerW = screenW - padding * 2;

    // ── Section 1: kind chip (group children only) + title ───────────────
    const titleText = nodeTitleText(n);
    const summaryText = nodeSummaryText(n);
    ctx.font = 'bold 16px -apple-system, sans-serif';
    const maxLineW = innerW - 4;
    const titleLines = wrapTextLines(ctx, titleText, maxLineW, 2);
    ctx.font = '13px -apple-system, sans-serif';
    const summaryLines = wrapTextLines(ctx, summaryText, maxLineW, 2);

    // For group children: kind label at top, then title centered in remaining space
    if (isGroupChild) {{
      const kindLabel = humanizeSemanticKind(nodeShape);
      ctx.font = '10px -apple-system, sans-serif';
      ctx.fillStyle = parentGc ? parentGc + 'cc' : mutedColor;
      ctx.textBaseline = 'top';
      ctx.textAlign = 'center';
      ctx.fillText(kindLabel, screenX, screenY - screenH / 2 + 5);

      // Re-measure title wrap at the actual draw font (14px) so truncation
      // matches what gets rendered. The outer titleLines above were computed
      // at 16px, which mis-sizes the wrap for child cards.
      ctx.font = 'bold 14px -apple-system, sans-serif';
      // Tighten the usable width: shape clip (hexagon/diamond/parallelogram)
      // and card border chrome both eat a few px on each side. Without this
      // buffer the text visually butts the card border or bleeds.
      const childLineW = Math.max(20, innerW - 14);
      const childTitleLines = wrapTextLines(ctx, titleText, childLineW, 2)
        .map(line => truncateToFit(ctx, line, childLineW));
      ctx.fillStyle = textColor;
      ctx.textBaseline = 'middle';
      const titleY = screenY + (childTitleLines.length > 1 ? -8 : 0);
      childTitleLines.forEach((line, i) => {{
        ctx.fillText(line, screenX, titleY + i * 17);
      }});
      ctx.restore();
      continue;
    }}

    // ── Standard file card: title + optional description + footer ─────────
    // Top of text content in screen px (NODE_R * zoom = border radius in screen px)
    let curY = screenY - screenH / 2 + NODE_R * zoom + 6;

    // Title line(s)
    ctx.fillStyle = textColor;
    ctx.font = 'bold 16px -apple-system, sans-serif';
    ctx.textBaseline = 'top';
    ctx.textAlign = 'center';
    titleLines.forEach(line => {{
      ctx.fillText(line, screenX, curY);
      curY += 18;
    }});
    curY += 6;

    if (!compactCard) {{
      const dividerY = screenY + screenH / 2 - 22;
      if (summaryLines.length > 0 && curY < dividerY - 10) {{
        ctx.fillStyle = mutedColor;
        ctx.font = '13px -apple-system, sans-serif';
        summaryLines.forEach(line => {{
          if (curY <= dividerY - 11) {{
            ctx.fillText(line, screenX, curY);
            curY += 15;
          }}
        }});
      }}

      // ── Bottom divider + footer ────────────────────────────────────────
      ctx.strokeStyle = divColor;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(screenX - screenW / 2 + padding, dividerY);
      ctx.lineTo(screenX + screenW / 2 - padding, dividerY);
      ctx.stroke();

      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillStyle = mutedColor;
      ctx.font = `12px "SF Mono", monospace`;
      const footer = nodeSubtitle(n);
      if (footer) {{
        const footerMaxW = Math.floor(innerW / 5.5);
        const footerText = footer.length > footerMaxW ? footer.slice(0, footerMaxW - 1) + '\u2026' : footer;
        ctx.fillText(footerText, screenX, screenY + screenH / 2 - 6);
      }}
    }}
    ctx.restore(); // end card clip

    // Indegree badge on hub nodes (indegree >= 3) — top-right corner
    // Not shown for group children (their container already signals importance)
    if (!isSelected && !isGroupChild && n.indegree >= 3) {{
      const badge = String(n.indegree);
      const bx = x + nw - 2, by = y - 2;
      ctx.fillStyle = '#58a6ff';
      ctx.font = `bold ${{9 / zoom}}px monospace`;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText(badge, bx, by);
    }}
  }}

  // ── Draw intra-group edges inside open groups ──────────────────────
  if (groupingState !== 'flat') {{
    for (const g of visibleNodes) {{
      if (!g.isGroup || !isGroupOpen(g)) continue;
      const layout = layoutOpenGroupChildren(g);
      const iEdges = layout.internalEdges;
      if (!iEdges || iEdges.length === 0) continue;
      const gc = groupColor(g.id);
      const posMap = {{}};
      for (const item of layout.items) posMap[item.node.id] = item;

      // Check if a child in this group is selected
      const childIds = new Set((g.childIds || []).filter(id => posMap[id]));
      const focusChild = selectedNode && childIds.has(selectedNode.id) ? selectedNode.id : null;

      for (const e of iEdges) {{
        const sid = e._srcId || e.source.id, tid = e._tgtId || e.target.id;
        const sp = posMap[sid], ep = posMap[tid];
        if (!sp || !ep) continue;
        const sHw = NODE_W / 2 + 2, sHh = (sp.node.h || NODE_H_BASE) / 2 + 2;
        const tHw = NODE_W / 2 + 2, tHh = (ep.node.h || NODE_H_BASE) / 2 + 2;
        const start = rectEdgePoint(ep.cx, ep.cy, sp.cx, sp.cy, sHw, sHh);
        const end = rectEdgePoint(sp.cx, sp.cy, ep.cx, ep.cy, tHw, tHh);
        const touches = focusChild && (sid === focusChild || tid === focusChild);
        const alpha = focusChild ? (touches ? 0.95 : 0.1) : 0.7;
        const lw = (touches ? 2.5 : 1.5) / zoom;
        const aSize = (touches ? 13 : 10) / zoom;
        ctx.globalAlpha = alpha;
        drawArrow(start.x, start.y, end.x, end.y, gc, lw, aSize);
      }}
    }}
    ctx.globalAlpha = 1;
  }}

  // Draw deferred arrowheads ON TOP of everything
  for (const ah of _deferredArrowheads) {{
    ctx.globalAlpha = ah.alpha;
    drawArrowHead(ah.fx, ah.fy, ah.tx, ah.ty, ah.color, ah.size);
  }}

  ctx.globalAlpha = 1;
  ctx.restore();

  window.__backButton = null;
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
let clickTimer = null, pendingClickNode = null;
const DOUBLE_CLICK_DELAY = 220;

function worldCoords(cx, cy) {{
  return {{ x: (cx - pan.x) / zoom, y: (cy - pan.y) / zoom }};
}}

function nodeAt(wx, wy) {{
  const list = (groupingState !== 'flat') ? visibleNodes : nodes;
  // For open groups: header area → group, children area → child node
  if (groupingState !== 'flat') {{
    for (const g of list) {{
      if (!g.isGroup || !isGroupOpen(g)) continue;
      const layout = layoutOpenGroupChildren(g);
      const gTop = g.y - g.h / 2;
      const gLeft = g.x - layout.openW / 2;
      // Check if inside the expanded bounds
      if (wx < gLeft || wx > gLeft + layout.openW) continue;
      if (wy < gTop || wy > gTop + layout.openH) continue;
      // Header area → return group (for pin/unpin)
      if (wy < gTop + OPEN_GROUP_HEADER) return g;
      // Children area → check individual children (full-size cards)
      for (const item of layout.items) {{
        const child = item.node;
        if (Math.abs(wx - item.cx) <= child.w / 2 && Math.abs(wy - item.cy) <= child.h / 2) {{
          return child;
        }}
      }}
      // In the group box but not on a child → return group
      return g;
    }}
  }}
  // Then check closed groups/nodes
  for (let i = list.length - 1; i >= 0; i--) {{
    const n = list[i];
    if (!isVisible(n)) continue;
    if (Math.abs(wx - n.x) <= n.w / 2 && Math.abs(wy - n.y) <= n.h / 2) return n;
  }}
  return null;
}}

function runSingleNodeClick(node) {{
  if (!node) return;
  if (node.isGroup && groupingState !== 'flat') {{
    selectedNode = null;
    highlightSet = null;
    blastRadiusSet = new Set();
    if (sidebarEnabled) renderGroupSidebar(node);
    draw();
    return;
  }}
  selectNode(node);
}}

function clearPendingNodeClick(commit) {{
  if (!clickTimer) {{
    pendingClickNode = null;
    return;
  }}
  const pending = pendingClickNode;
  window.clearTimeout(clickTimer);
  clickTimer = null;
  pendingClickNode = null;
  if (commit && pending) runSingleNodeClick(pending);
}}

function queueNodeClick(node) {{
  if (clickTimer && pendingClickNode) {{
    if (pendingClickNode.id === node.id) {{
      clearPendingNodeClick(false);
      selectNode(node);
      openFlowOverlay(node);
      return;
    }}
    clearPendingNodeClick(true);
  }}
  pendingClickNode = node;
  clickTimer = window.setTimeout(() => {{
    const pending = pendingClickNode;
    clickTimer = null;
    pendingClickNode = null;
    if (pending) runSingleNodeClick(pending);
  }}, DOUBLE_CLICK_DELAY);
}}

canvas.addEventListener('mousedown', e => {{
  document.getElementById('group-tooltip').style.display = 'none';
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
  lastMouseWX = wx; lastMouseWY = wy;
  if (dragging && dragNode) {{
    // No node dragging — just update cursor
  }} else if (dragging && dragStart) {{
    pan.x = panStart.x + (e.offsetX - dragStart.x);
    pan.y = panStart.y + (e.offsetY - dragStart.y);
    viewportWasManuallyMoved = true;
    clampPan();
    draw();
  }} else {{
    const prev = hoveredNode;
    hoveredNode = nodeAt(wx, wy);
    if (prev !== hoveredNode) {{
      draw();
      // Group tooltip — only for closed (non-open) groups
      const gtt = document.getElementById('group-tooltip');
      if (hoveredNode && hoveredNode.isGroup && hoveredNode.description && !isGroupOpen(hoveredNode)) {{
        gtt.innerHTML = `<div class="gt-detail">${{esc(hoveredNode.description)}}</div>`;
        gtt.style.display = 'block';
      }} else {{
        gtt.style.display = 'none';
      }}
      // Sidebar preview on hover (only if nothing is selected and sidebar is enabled)
      if (!selectedNode && sidebarEnabled) {{
        if (hoveredNode && !hoveredNode.isGroup) {{
          renderSidebar(hoveredNode);
        }} else if (hoveredNode && hoveredNode.isGroup) {{
          renderGroupSidebar(hoveredNode);
        }} else {{
          renderDefaultSidebar();
        }}
      }}
    }}
    // Position group tooltip near cursor
    if (hoveredNode && hoveredNode.isGroup) {{
      const gtt = document.getElementById('group-tooltip');
      if (gtt.style.display === 'block') {{
        const pad = 16;
        let tx = e.clientX + pad;
        let ty = e.clientY + pad;
        const rect = gtt.getBoundingClientRect();
        if (tx + rect.width > window.innerWidth - 8) tx = e.clientX - rect.width - pad;
        if (ty + rect.height > window.innerHeight - 8) ty = e.clientY - rect.height - pad;
        gtt.style.left = tx + 'px';
        gtt.style.top = ty + 'px';
      }}
    }}
    canvas.style.cursor = hoveredNode ? 'pointer' : 'grab';
  }}
}});

canvas.addEventListener('mouseup', e => {{
  // Back button click detection (check BEFORE drag logic)
  if (window.__backButton) {{
    const bb = window.__backButton;
    if (e.offsetX >= bb.x && e.offsetX <= bb.x + bb.w && e.offsetY >= bb.y && e.offsetY <= bb.y + bb.h) {{
      dragging = false; dragStart = null; panStart = null; dragNode = null;
      canvas.classList.remove('dragging');
      collapseGroups();
      return;
    }}
  }}
  if (dragging && dragNode) {{
    queueNodeClick(dragNode);
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
    // Pinch gesture (trackpad) or Ctrl+scroll → real-time zoom
    const factor = e.deltaY < 0 ? 1.08 : 0.93;
    const wx = (e.offsetX - pan.x) / zoom;
    const wy = (e.offsetY - pan.y) / zoom;
    const minZoom = Math.max(0.3, (fitZoomLevel || 0.5) * 0.8);
    zoom = Math.max(minZoom, Math.min(3.0, zoom * factor));
    pan.x = e.offsetX - wx * zoom;
    pan.y = e.offsetY - wy * zoom;
    viewportWasManuallyMoved = true;
    clampPan();
    draw();
  }} else {{
    // Two-finger scroll (trackpad) → pan
    pan.x -= e.deltaX * 1.2;
    pan.y -= e.deltaY * 1.2;
    viewportWasManuallyMoved = true;
    clampPan();
    draw();
  }}
}}, {{ passive: false }});

// ── Sidebar ──────────────────────────────────────────────────────────────────

function selectNode(n) {{
  selectedNode = selectedNode === n ? null : n;
  if (selectedNode) {{
    highlightSet = nhopNeighborhood(n.id, 1);
    // Add parent group IDs so group-level nodes + edges light up
    for (const id of [...highlightSet]) {{
      const gid = nodeToGroup[id];
      if (gid) highlightSet.add(gid);
    }}
    // Add groups connected to the focal group via inter-group edges
    const myGroup = nodeToGroup[n.id];
    if (myGroup) {{
      for (const ve of visibleEdges) {{
        const sid = ve._srcId || ve.source.id, tid = ve._tgtId || ve.target.id;
        if (sid === myGroup) highlightSet.add(tid);
        if (tid === myGroup) highlightSet.add(sid);
      }}
    }}
    blastRadiusSet = computeBlastRadius(n.id);
    if (sidebarEnabled) renderSidebar(n);
  }} else {{
    highlightSet = null;
    blastRadiusSet = new Set();
    if (sidebarEnabled) renderDefaultSidebar();
  }}
  draw();
  drawMinimap();
}}

function renderGroupSidebar(g) {{
  const children = (g.childIds || []).map(id => nodeIndex[id]).filter(Boolean);
  const ranked = rankChildNodes(children);
  const fileList = ranked.map(c => {{
    const title = nodeTitleText(c);
    const desc = c.description ? ` \u2014 ${{compactText(c.description, 60)}}` : '';
    return `<div class="neighbor" onclick="jumpTo('${{esc(c.id)}}')" style="flex-direction:column;align-items:flex-start;gap:2px">
      <span style="font-weight:600">${{esc(title)}}</span>
      <span style="color:#8b949e;font-size:11px">${{esc(c.id)}}${{desc}}</span>
    </div>`;
  }}).join('');

  sidebar.innerHTML = `
    <div>
      <h2>${{esc(g.label)}}</h2>
      <div style="margin-top:4px;font-size:11px;color:#6e7681">${{g.fileCount}} file${{g.fileCount !== 1 ? 's' : ''}} \u00b7 ${{esc(g.language || '')}}${{g.kind ? ` \u00b7 ${{esc(humanizeSemanticKind(g.kind))}}` : ''}}</div>
    </div>
    ${{g.description ? `<p class="desc">${{esc(g.description)}}</p>` : ''}}
    <div>
      <p class="section-title">Files</p>
      <div style="margin-top:4px">${{fileList}}</div>
    </div>
  `;
}}

function renderDefaultSidebar() {{
  if (sidebarEnabled) {{
    sidebar.classList.remove('hidden');
    sidebar.innerHTML = '<div class="placeholder">Hover or click a block to see details.</div>';
  }} else {{
    sidebar.classList.add('hidden');
    sidebar.innerHTML = '';
  }}
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

  // Top symbols: classes first, then functions, max 6
  const sortedSymbols = [...n.symbols].sort((a, b) => {{
    const kindOrder = {{ class: 0, function: 1 }};
    return (kindOrder[a.kind] ?? 2) - (kindOrder[b.kind] ?? 2);
  }});
  const topSymbols = sortedSymbols.slice(0, 6);
  const symbolHtml = topSymbols.length
    ? topSymbols.map(s => `<span class="symbol ${{s.kind === 'function' ? 'fn' : s.kind === 'class' ? 'cls' : 'var'}}">${{esc(s.name)}}</span>`).join('')
      + (n.symbols.length > 6 ? `<span style="color:#6e7681;font-size:11px;margin-left:4px">+${{n.symbols.length - 6}} more</span>` : '')
    : '';

  const neighborHtml = (list, arrow) => list.slice(0, 8).map(item => {{
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
  const semantic = fileSemantic(n);
  const semanticPill = semantic.kind
    ? `<span class="role-tag" style="background:#58a6ff22;color:#79c0ff;margin-left:6px">${{esc(humanizeSemanticKind(semantic.kind))}}</span>`
    : '';

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
      <h2>${{esc(nodeTitleText(n))}}</h2>
      <span style="font-size:11px;color:#6e7681;word-break:break-all">${{esc(n.id)}}</span>
      <div style="margin-top:4px;font-size:11px;color:#6e7681">${{esc(n.language || '')}} \u00b7 ${{(n.size/1024).toFixed(1)}} KB${{rolePill}}${{semanticPill}}</div>
    </div>
    ${{inCycle ? '<div class="cycle-warning"><strong>\u26a0 In circular dependency</strong></div>' : ''}}
    ${{n.description ? `<p class="desc">${{esc(n.description)}}</p>` : ''}}
    <div class="metrics-panel">
      ${{metricRow('Imported by', n.indegree + ' file' + (n.indegree !== 1 ? 's' : ''))}}
      ${{metricRow('Imports', n.outdegree + ' file' + (n.outdegree !== 1 ? 's' : ''))}}
      ${{blastRadiusSet.size > 0 ? metricRow('Blast radius', blastRadiusSet.size + ' files affected', '#f59e0b') : ''}}
    </div>
    ${{symbolHtml ? `<div><p class="section-title">Key Symbols</p><div style="margin-top:6px">${{symbolHtml}}</div></div>` : ''}}
    ${{imports.length ? `<div><p class="section-title">Imports (${{imports.length}})</p><div style="margin-top:4px">${{neighborHtml(imports, '\u2192')}}</div></div>` : ''}}
    ${{importedBy.length ? `<div><p class="section-title">Imported by (${{importedBy.length}})</p><div style="margin-top:4px">${{neighborHtml(importedBy, '\u2190')}}</div></div>` : ''}}
    ${{codePanelHtml}}
  `;
  // Resize canvas after sidebar appears
}}

function jumpTo(nodeId) {{
  const n = nodeIndex[nodeId];
  if (!n) return;
  const parentGroupId = nodeToGroup[nodeId];
  selectNode(n);
  const target = (groupingState !== 'flat' && parentGroupId && groupMap[parentGroupId])
    ? groupMap[parentGroupId]
    : n;
  pan.x = canvasW() / 2 - target.x * zoom;
  pan.y = canvasH() / 2 - target.y * zoom;
  viewportWasManuallyMoved = true;
}}
window.jumpTo = jumpTo;

function compactText(text, maxLen) {{
  const cleaned = (text || '').replace(WHITESPACE_RE, ' ').trim();
  if (!cleaned) return '';
  if (cleaned.length <= maxLen) return cleaned;
  return cleaned.slice(0, maxLen - 1).replace(/[ ,;:.!?-]+$/g, '') + '\u2026';
}}

function displayNodeName(node) {{
  return nodeTitleText(node);
}}

function fileSemantic(node) {{
  return node && node.id ? (FILE_SEMANTICS[node.id] || {{}}) : {{}};
}}

function derivedNodeTitle(node) {{
  if (!node) return '';
  // Prefer the actual filename (minus extension and path) — it's concrete
  // and identifiable. Generic verb phrases like "Render View" or "Check
  // Rules" collide across unrelated files and turn the diagram into a word
  // soup. Tidy underscores/dashes into title-case so `test_describer.py`
  // reads as "Test Describer" rather than a raw identifier.
  const rawLabel = String(node.label || '');
  const stripped = rawLabel
    .replace(JS_EXT_RE, '')
    .replace(/\.(py|pyi|kt|kts|rb|java|cs|swift|go|rs|c|cc|cpp|h|hpp)$/i, '');
  if (stripped) {{
    const pretty = titleCaseWords(flowWords(stripped));
    if (pretty) return pretty;
    return stripped;
  }}
  // Only fall back to the phrase/role heuristics for truly empty labels.
  const semantic = fileSemantic(node);
  const phrase = phraseFromText(node.description || semantic.summary || '');
  if (phrase) return phrase;
  const rolePhrase = roleFlowPhrase(node.role, '');
  if (rolePhrase) return rolePhrase;
  const words = flowWords(rawLabel);
  if (words.length > 0) return titleCaseWords(words.slice(0, 3));
  return rawLabel;
}}

function flowShapeForNode(node, fallbackShape) {{
  if (!node) return fallbackShape || 'process';
  const semantic = fileSemantic(node);
  if (semantic.shape) return semantic.shape;
  if (node.shape) return node.shape;
  if (node.kind) return node.kind;
  return fallbackShape || 'process';
}}

function itemFromNode(node, meta, fallbackSummary) {{
  return {{
    title: displayNodeName(node),
    meta: meta || '',
    summary: compactText(node.description || fallbackSummary || '', 120),
  }};
}}

function flowWords(text) {{
  return String(text || '')
    .replace(JS_EXT_RE, '')
    .replace(/\\(\\)/g, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[._/:-]+/g, ' ')
    .replace(WHITESPACE_RE, ' ')
    .trim()
    .split(' ')
    .filter(Boolean);
}}

function titleCaseWords(words) {{
  return words.map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}}

const FLOW_PHRASE_RULES = [
  {{ pattern: /(render|draw|paint|canvas|view|visual)/i, label: 'Render View' }},
  {{ pattern: /(describe|explain|summary)/i, label: 'Explain Code' }},
  {{ pattern: /(check|validate|rule|lint|enforce)/i, label: 'Check Rules' }},
  {{ pattern: /(export|serialize|to dict|to_dict|json)/i, label: 'Export Data' }},
  {{ pattern: /(from dict|from_dict|parse|decode|load)/i, label: 'Read Data' }},
  {{ pattern: /(cycle|scc|tarjan)/i, label: 'Find Cycles' }},
  {{ pattern: /(cluster|group|bucket)/i, label: 'Group Files' }},
  {{ pattern: /(metric|centrality|pagerank|score|rank)/i, label: 'Score Graph' }},
  {{ pattern: /(import|dependency|resolve)/i, label: 'Resolve Imports' }},
  {{ pattern: /(schema|model|dataclass|type|class)/i, label: 'Define Types' }},
  {{ pattern: /(query|search|find|get|lookup|neighbor)/i, label: 'Query Graph' }},
  {{ pattern: /(graph)/i, label: 'Model Graph' }},
  {{ pattern: /(test|assert|verify)/i, label: 'Run Checks' }},
  {{ pattern: /(config|setting|env)/i, label: 'Load Settings' }},
  {{ pattern: /(api|request|route|http)/i, label: 'Handle Request' }},
  {{ pattern: /(analy|scan|inspect)/i, label: 'Analyze Code' }},
];

const GENERIC_FLOW_LABELS = new Set([
  'symbol', 'node', 'edge', 'graph', 'data', 'file', 'main', 'run', 'init',
  'helper', 'utils', 'core', 'module', 'item', 'value', 'result',
]);

function shortFlowLabel(text, fallback) {{
  const primary = flowWords(text);
  if (primary.length > 0) return titleCaseWords(primary.slice(0, 3));
  const backup = flowWords(fallback || 'Main Flow');
  return backup.length > 0 ? titleCaseWords(backup.slice(0, 3)) : 'Main Flow';
}}

function shortFlowHint(text, fallback) {{
  const source = compactText(text || fallback || '', 42);
  return source;
}}

function roleFlowPhrase(role, fallback) {{
  if (role === 'entry_point') return 'Start App';
  if (role === 'api_route') return 'Handle Request';
  if (role === 'data_model') return 'Model Data';
  if (role === 'utility') return 'Run Helper';
  if (role === 'config') return 'Load Settings';
  if (role === 'test') return 'Run Checks';
  return fallback || 'Core Logic';
}}

function phraseFromText(text) {{
  const value = String(text || '').replace(/[_-]+/g, ' ');
  for (const rule of FLOW_PHRASE_RULES) {{
    if (rule.pattern.test(value)) return rule.label;
  }}
  return '';
}}

function symbolFlowPhrase(symbol) {{
  if (!symbol) return '';
  const name = String(symbol.name || '');
  const human = shortFlowLabel(name, '');
  const lowerWords = flowWords(name).map(word => word.toLowerCase());
  if (lowerWords.length === 1 && GENERIC_FLOW_LABELS.has(lowerWords[0])) {{
    if (symbol.kind === 'class') return 'Define Types';
    if (symbol.kind === 'function') return 'Run Logic';
    return '';
  }}
  const mapped = phraseFromText(name);
  if (mapped) return mapped;
  if (symbol.kind === 'class' && lowerWords.length <= 2) return 'Define Types';
  return human;
}}

function nodeFlowPhrase(node, fallback) {{
  if (!node) return fallback || 'Core Logic';
  const fromDescription = phraseFromText(node.description);
  if (fromDescription) return fromDescription;
  if (node.role) {{
    const rolePhrase = roleFlowPhrase(node.role, '');
    if (rolePhrase) return rolePhrase;
  }}
  return shortFlowLabel(node.short_title || node.label, fallback || 'Core Logic');
}}

function outcomeFlowPhrase(text, role, fallback) {{
  const phrase = phraseFromText(text);
  if (phrase === 'Export Data') return 'Return Data';
  if (phrase === 'Render View') return 'Show Result';
  if (phrase === 'Run Checks') return 'Report Status';
  if (phrase === 'Define Types' || role === 'data_model') return 'Share Types';
  if (phrase === 'Resolve Imports') return 'Link Files';
  return fallback || 'Finish Here';
}}

function humanizeSymbolName(symbol) {{
  if (!symbol || !symbol.name) return '';
  const kind = symbol.kind || '';
  const raw = symbol.name;
  // Convert _snake_case or camelCase to readable words
  const words = flowWords(raw).map(w => w.toLowerCase());
  if (words.length === 0) return raw;
  const readable = titleCaseWords(words);
  // Add kind hint for clarity
  if (kind === 'class') return readable + ' (class)';
  if (kind === 'function') return readable + '()';
  return readable;
}}

function symbolDetailLines(symbols, count) {{
  return (symbols || [])
    .filter(symbol => symbol.kind !== 'import')
    .slice(0, count)
    .map(symbol => humanizeSymbolName(symbol))
    .filter(Boolean);
}}

function nodeDetailLines(node, count) {{
  if (!node) return [];
  const symbols = symbolDetailLines(node.symbols, count);
  if (symbols.length > 0) return symbols;
  return [displayNodeName(node)];
}}

function nodesDetailLines(nodeList, count) {{
  const details = [];
  for (const node of nodeList || []) {{
    for (const name of symbolDetailLines(node.symbols, count)) {{
      if (!details.includes(name)) details.push(name);
      if (details.length >= count) return details;
    }}
  }}
  if (details.length === 0) {{
    for (const node of nodeList || []) {{
      const label = displayNodeName(node);
      if (!details.includes(label)) details.push(label);
      if (details.length >= count) break;
    }}
  }}
  return details;
}}

function renderFlowMeta(metaItems) {{
  if (!metaItems || metaItems.length === 0) return '';
  return `<div class="flow-meta">${{metaItems.map(item =>
    `<div class="flow-pill"><span>${{esc(item.label)}}</span><strong>${{esc(String(item.value))}}</strong></div>`
  ).join('')}}</div>`;
}}

function flowNode(id, shape, label, x, y, details, color, tooltip) {{
  return {{ id, shape, label, x, y, details: details || [], color: color || '#58a6ff', tooltip: tooltip || '' }};
}}

function flowEdge(from, to, label) {{
  return {{ from, to, label: label || '' }};
}}

// ── Auto-layout for AI-generated flowcharts ─────────────────────────────────

const FLOW_TYPE_COLORS = {{
  start: '#22c55e',
  end: '#22c55e',
  decision: '#58a6ff',
  step: '#f59e0b',
  entry: '#22c55e',
  process: '#f59e0b',
  analysis: '#eab308',
  data: '#14b8a6',
  external: '#94a3b8',
  test: '#ef4444',
}};

function layoutFlowchart(fc) {{
  // Build adjacency
  const adj = {{}};
  const inDeg = {{}};
  for (const n of fc.nodes) {{
    adj[n.id] = [];
    inDeg[n.id] = 0;
  }}
  for (const e of fc.edges) {{
    if (adj[e.from]) adj[e.from].push(e.to);
    inDeg[e.to] = (inDeg[e.to] || 0) + 1;
  }}

  // Assign layers via topological BFS
  const layers = {{}};
  const queue = [];
  for (const n of fc.nodes) {{
    if ((inDeg[n.id] || 0) === 0) {{
      layers[n.id] = 0;
      queue.push(n.id);
    }}
  }}
  // If no root found (cycle), start from first node
  if (queue.length === 0 && fc.nodes.length > 0) {{
    layers[fc.nodes[0].id] = 0;
    queue.push(fc.nodes[0].id);
  }}
  let qi = 0;
  while (qi < queue.length) {{
    const cur = queue[qi++];
    for (const next of (adj[cur] || [])) {{
      const newLayer = (layers[cur] || 0) + 1;
      if (layers[next] === undefined || newLayer > layers[next]) {{
        layers[next] = newLayer;
        queue.push(next);
      }}
    }}
  }}
  // Assign any unvisited nodes
  for (const n of fc.nodes) {{
    if (layers[n.id] === undefined) layers[n.id] = 0;
  }}

  // Group nodes by layer
  const layerGroups = {{}};
  let maxLayer = 0;
  for (const n of fc.nodes) {{
    const l = layers[n.id];
    if (!layerGroups[l]) layerGroups[l] = [];
    layerGroups[l].push(n);
    if (l > maxLayer) maxLayer = l;
  }}

  // Position nodes
  const NODE_W = 200;
  const NODE_H_STEP = 86;
  const NODE_H_DECISION = 136;
  const LAYER_GAP = 140;
  const COL_GAP = 240;
  const PAD_X = 60;
  const PAD_Y = 80;

  const positioned = [];
  let maxX = 0;
  for (let l = 0; l <= maxLayer; l++) {{
    const group = layerGroups[l] || [];
    const y = PAD_Y + l * LAYER_GAP;
    const totalWidth = group.length * COL_GAP;
    const startX = PAD_X + (860 - 2 * PAD_X) / 2 - totalWidth / 2 + COL_GAP / 2;
    for (let i = 0; i < group.length; i++) {{
      const n = group[i];
      const x = startX + i * COL_GAP;
      const shape = n.shape || n.type || 'step';
      const color = FLOW_TYPE_COLORS[shape] || '#f59e0b';
      const detailLines = [];
      if (n.description) detailLines.push(compactText(n.description, 56));
      positioned.push(flowNode(n.id, shape, n.label, x, y, detailLines, color, n.description || ''));
      if (x > maxX) maxX = x;
    }}
  }}

  const width = Math.max(860, maxX + PAD_X + NODE_W / 2);
  const height = PAD_Y + (maxLayer + 1) * LAYER_GAP + 40;

  const edges = fc.edges.map(e => flowEdge(e.from, e.to, e.label || ''));

  return {{ width, height, nodes: positioned, edges }};
}}

// ── Fallback generic diagram (used when no AI flowchart available) ───────────

function buildFlowDiagram(config) {{
  return {{
    width: 860,
    height: 680,
    nodes: [
      flowNode('start', config.startShape || 'start', config.startLabel, 430, 74, config.startDetails, FLOW_TYPE_COLORS[config.startShape || 'start'] || '#22c55e'),
      flowNode('focus', config.focusShape || 'decision', config.focusLabel, 430, 248, config.focusDetails, FLOW_TYPE_COLORS[config.focusShape || 'decision'] || '#58a6ff'),
      flowNode('left', config.leftShape || 'step', config.leftLabel, 210, 440, config.leftDetails, FLOW_TYPE_COLORS[config.leftShape || 'step'] || '#f59e0b'),
      flowNode('right', config.rightShape || 'step', config.rightLabel, 650, 440, config.rightDetails, FLOW_TYPE_COLORS[config.rightShape || 'step'] || '#a78bfa'),
      flowNode('end', config.endShape || 'end', config.endLabel, 430, 600, config.endDetails, FLOW_TYPE_COLORS[config.endShape || 'end'] || '#22c55e'),
    ],
    edges: [
      flowEdge('start', 'focus', config.startEdge || 'invoked'),
      flowEdge('focus', 'left', config.leftEdge || 'yes'),
      flowEdge('focus', 'right', config.rightEdge || 'no'),
      flowEdge('left', 'end', config.leftEndEdge || 'done'),
      flowEdge('right', 'end', config.rightEndEdge || 'done'),
    ],
  }};
}}

// ── SVG rendering ───────────────────────────────────────────────────────────

function svgNodeShape(node) {{
  if (node.shape === 'decision') {{
    const dh = 68, dw = 118;
    return `<polygon class="flow-node-shape" points="${{node.x}},${{node.y - dh}} ${{node.x + dw}},${{node.y}} ${{node.x}},${{node.y + dh}} ${{node.x - dw}},${{node.y}}" fill="${{node.color}}22" stroke="${{node.color}}" />`;
  }}
  if (node.shape === 'analysis') {{
    return `<polygon class="flow-node-shape" points="${{node.x - 80}},${{node.y - 43}} ${{node.x + 80}},${{node.y - 43}} ${{node.x + 104}},${{node.y}} ${{node.x + 80}},${{node.y + 43}} ${{node.x - 80}},${{node.y + 43}} ${{node.x - 104}},${{node.y}}" fill="${{node.color}}20" stroke="${{node.color}}" />`;
  }}
  if (node.shape === 'data') {{
    return `<polygon class="flow-node-shape" points="${{node.x - 82}},${{node.y - 43}} ${{node.x + 92}},${{node.y - 43}} ${{node.x + 82}},${{node.y + 43}} ${{node.x - 92}},${{node.y + 43}}" fill="${{node.color}}20" stroke="${{node.color}}" />`;
  }}
  const width = node.shape === 'step' || node.shape === 'process' ? 200 : 178;
  const height = node.shape === 'end' || node.shape === 'entry' ? 74 : 86;
  const rx = (node.shape === 'step' || node.shape === 'process') ? 12 : 26;
  const dash = (node.shape === 'external' || node.shape === 'test') ? ' stroke-dasharray="8 6"' : '';
  return `<rect class="flow-node-shape" x="${{node.x - width / 2}}" y="${{node.y - height / 2}}" width="${{width}}" height="${{height}}" rx="${{rx}}" fill="${{node.color}}20" stroke="${{node.color}}"${{dash}} />`;
}}

function svgLabelLines(label) {{
  const words = String(label || '').split(/\\s+/).filter(Boolean);
  if (words.length <= 3) return [words.join(' ')];
  const mid = Math.ceil(words.length / 2);
  return [words.slice(0, mid).join(' '), words.slice(mid).join(' ')];
}}

function svgNodeLabel(node) {{
  const lines = svgLabelLines(node.label);
  const detailLines = (node.details || []).filter(Boolean).slice(0, 3).map(line => compactText(line, 30));
  const labelBlockHeight = lines.length * 20;
  const detailBlockHeight = detailLines.length * 14;
  const totalHeight = labelBlockHeight + (detailLines.length ? 10 : 0) + detailBlockHeight;
  let currentY = node.y - totalHeight / 2 + 16;
  const text = lines.map((line, index) =>
    `<tspan x="${{node.x}}" y="${{currentY + index * 20}}">${{esc(line)}}</tspan>`
  ).join('');
  currentY += labelBlockHeight + 10;
  const details = detailLines.length > 0
    ? `<text class="flow-node-caption">${{detailLines.map((line, index) =>
        `<tspan x="${{node.x}}" y="${{currentY + index * 14}}">${{esc(line)}}</tspan>`
      ).join('')}}</text>`
    : '';
  return `<text class="flow-node-label">${{text}}</text>${{details}}`;
}}

function nodeAnchor(node, side) {{
  if (node.shape === 'decision') {{
    if (side === 'top') return {{ x: node.x, y: node.y - 68 }};
    if (side === 'bottom') return {{ x: node.x, y: node.y + 68 }};
    if (side === 'left') return {{ x: node.x - 118, y: node.y }};
    return {{ x: node.x + 118, y: node.y }};
  }}
  const width = node.shape === 'analysis' ? 208 : ((node.shape === 'data' || node.shape === 'step' || node.shape === 'process') ? 200 : 178);
  const height = node.shape === 'end' || node.shape === 'entry' ? 74 : 86;
  if (side === 'top') return {{ x: node.x, y: node.y - height / 2 }};
  if (side === 'bottom') return {{ x: node.x, y: node.y + height / 2 }};
  if (side === 'left') return {{ x: node.x - width / 2, y: node.y }};
  return {{ x: node.x + width / 2, y: node.y }};
}}

function renderFlowSvg(diagram) {{
  const nodeMap = Object.fromEntries(diagram.nodes.map(node => [node.id, node]));
  const defs = `
    <defs>
      <marker id="flow-arrowhead" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
        <path d="M 0 0 L 7 3.5 L 0 7 z" fill="#58a6ff"></path>
      </marker>
    </defs>
  `;
  const edges = diagram.edges.map(edge => {{
    const from = nodeMap[edge.from];
    const to = nodeMap[edge.to];
    if (!from || !to) return '';
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    let startSide, endSide;
    if (Math.abs(dy) > Math.abs(dx) * 0.3) {{
      startSide = dy > 0 ? 'bottom' : 'top';
      endSide = dy > 0 ? 'top' : 'bottom';
    }} else {{
      startSide = dx > 0 ? 'right' : 'left';
      endSide = dx > 0 ? 'left' : 'right';
    }}
    const start = nodeAnchor(from, startSide);
    const end = nodeAnchor(to, endSide);
    const midX = (start.x + end.x) / 2;
    const midY = (start.y + end.y) / 2;
    const edgeLabel = edge.label
      ? `<text class="flow-edge-label" x="${{midX}}" y="${{midY - 8}}">${{esc(edge.label)}}</text>`
      : '';
    return `<g><path class="flow-edge" d="M ${{start.x}} ${{start.y}} L ${{end.x}} ${{end.y}}" marker-end="url(#flow-arrowhead)"></path>${{edgeLabel}}</g>`;
  }}).join('');
  const nodes = diagram.nodes.map(node => {{
    const attrs = node.tooltip
      ? ` data-ft-tooltip="${{esc(node.tooltip).replace(/"/g, '&quot;')}}" `
      : '';
    return `<g class="flow-node-group"${{attrs}}>${{svgNodeShape(node)}}${{svgNodeLabel(node)}}</g>`;
  }}).join('');
  const legend = `
    <g transform="translate(20, ${{diagram.height - 40}})">
      <rect x="0" y="-12" width="16" height="16" rx="8" fill="none" stroke="#6e7681" stroke-width="1.5" />
      <text x="22" y="0" fill="#6e7681" font-size="11">Start / End</text>
      <polygon points="100,-4 112,4 100,12 88,4" fill="none" stroke="#6e7681" stroke-width="1.5" />
      <text x="118" y="0" fill="#6e7681" font-size="11">Decision</text>
      <rect x="196" y="-12" width="16" height="16" rx="3" fill="none" stroke="#6e7681" stroke-width="1.5" />
      <text x="218" y="0" fill="#6e7681" font-size="11">Step</text>
      <polygon points="296,-10 308,-10 318,0 308,10 296,10 286,0" fill="none" stroke="#6e7681" stroke-width="1.5" />
      <text x="326" y="0" fill="#6e7681" font-size="11">Analysis</text>
      <polygon points="414,-12 430,-12 420,12 404,12" fill="none" stroke="#6e7681" stroke-width="1.5" />
      <text x="438" y="0" fill="#6e7681" font-size="11">Data / state</text>
    </g>
  `;
  return `<div class="flow-graph-wrap"><svg class="flow-svg" viewBox="0 0 ${{diagram.width}} ${{diagram.height}}" role="img" aria-label="Workflow diagram">${{defs}}${{edges}}${{nodes}}${{legend}}</svg></div>`;
}}

function relatedNodeScore(node, weight) {{
  return (weight * 10) + ((node.pagerank || 0) * 100) + (node.indegree || 0) + (node.outdegree || 0);
}}

function aggregateNeighborNodes(nodeIds, direction) {{
  const counts = {{}};
  const lists = direction === 'imports' ? importsByNode : importedByNode;
  const internalIds = new Set(nodeIds);
  for (const nodeId of nodeIds) {{
    for (const item of (lists[nodeId] || [])) {{
      if (internalIds.has(item.id)) continue;
      counts[item.id] = (counts[item.id] || 0) + 1;
    }}
  }}
  return Object.entries(counts)
    .map(([id, count]) => {{
      const node = nodeIndex[id];
      return node ? {{ node, count }} : null;
    }})
    .filter(Boolean)
    .sort((a, b) => relatedNodeScore(b.node, b.count) - relatedNodeScore(a.node, a.count));
}}

function internalConnectionCount(nodeId, internalIds, direction) {{
  const list = direction === 'imports' ? (importsByNode[nodeId] || []) : (importedByNode[nodeId] || []);
  let count = 0;
  for (const item of list) if (internalIds.has(item.id)) count++;
  return count;
}}

function buildGroupFlowModel(groupNode) {{
  const childNodes = rankChildNodes(groupNode.childIds.map(id => nodeIndex[id]).filter(Boolean));
  const internalIds = new Set(childNodes.map(node => node.id));
  if (childNodes.length === 0) return null;

  if (groupNode.detailDiagram && groupNode.detailDiagram.nodes && groupNode.detailDiagram.edges) {{
    return {{
      eyebrow: 'Block Workflow',
      title: groupNode.label,
      subtitle: compactText(groupNode.description || 'Derived from the files and dependency flow inside this block.', 180),
      meta: [
        {{ label: 'Files', value: groupNode.fileCount }},
        {{ label: 'Incoming Links', value: groupNode.indegree }},
        {{ label: 'Outgoing Links', value: groupNode.outdegree }},
      ],
      diagram: layoutFlowchart(groupNode.detailDiagram),
    }};
  }}

  let leftLabel = 'Starts Here';
  let leftNodes = childNodes.filter(node =>
    node.role === 'entry_point'
    || node.role === 'api_route'
    || node.role === 'test'
    || internalConnectionCount(node.id, internalIds, 'importedBy') === 0
  ).slice(0, 3);

  const externalCallers = aggregateNeighborNodes(groupNode.childIds, 'importedBy').slice(0, 3);
  if (leftNodes.length === 0 && externalCallers.length > 0) {{
    leftLabel = 'Used By';
    leftNodes = externalCallers.map(item => item.node);
  }}
  if (leftNodes.length === 0) leftNodes = childNodes.slice(0, Math.min(3, childNodes.length));

  const leftIds = new Set(leftNodes.map(node => node.id));
  let centerNodes = childNodes.filter(node => !leftIds.has(node.id)).slice(0, 4);
  if (centerNodes.length === 0) centerNodes = childNodes.slice(0, Math.min(4, childNodes.length));

  let rightLabel = 'Depends On';
  let rightItems = aggregateNeighborNodes(groupNode.childIds, 'imports')
    .slice(0, 4)
    .map(item => itemFromNode(item.node, item.count + ' file' + (item.count === 1 ? '' : 's') + ' rely on this link', 'Shared dependency outside this block.'));

  if (rightItems.length === 0) {{
    rightLabel = 'Finishes In';
    const centerIds = new Set(centerNodes.map(node => node.id));
    const terminalNodes = childNodes.filter(node =>
      !leftIds.has(node.id)
      && !centerIds.has(node.id)
      && internalConnectionCount(node.id, internalIds, 'imports') === 0
    ).slice(0, 3);
    const fallbackTerminal = terminalNodes.length > 0 ? terminalNodes : childNodes.slice(-Math.min(3, childNodes.length));
    rightItems = fallbackTerminal.map(node => itemFromNode(node, node.role ? humanizeLabel(node.role) : 'Internal step', 'This is where work tends to settle inside the block.'));
  }}

  const triggerNode = leftNodes[0] || childNodes[0];
  const insideNode = centerNodes[0] || childNodes[0];
  const branchNode = centerNodes[1] || childNodes[Math.min(1, childNodes.length - 1)] || triggerNode;
  const dependencyNode = aggregateNeighborNodes(groupNode.childIds, 'imports')[0]?.node || null;
  const rightNode = dependencyNode || branchNode || insideNode;

  return {{
    eyebrow: 'Block Workflow',
    title: groupNode.label,
    subtitle: compactText(groupNode.description || 'Autogenerated from the files, imports, and descriptions inside this block.', 180),
    meta: [
      {{ label: 'Files', value: groupNode.fileCount }},
      {{ label: 'Incoming Links', value: groupNode.indegree }},
      {{ label: 'Outgoing Links', value: groupNode.outdegree }},
    ],
    diagram: buildFlowDiagram({{
      startLabel: 'Enter Block',
      startDetails: nodesDetailLines(leftNodes, 2),
      startEdge: 'called',
      startShape: groupNode.kind === 'entry' ? 'entry' : 'start',
      focusLabel: nodeFlowPhrase(groupNode, roleFlowPhrase(groupNode.role, 'Core Logic')),
      focusDetails: nodesDetailLines(childNodes, 3),
      focusShape: groupNode.shape || 'decision',
      leftEdge: 'internal path',
      leftLabel: symbolFlowPhrase(insideNode.symbols?.[0]) || nodeFlowPhrase(insideNode, 'Main Step'),
      leftDetails: nodeDetailLines(insideNode, 2),
      leftShape: flowShapeForNode(insideNode, 'process'),
      rightEdge: dependencyNode ? 'external dep' : 'alt path',
      rightLabel: dependencyNode
        ? nodeFlowPhrase(dependencyNode, rightLabel === 'Depends On' ? 'Use Shared Code' : 'Second Step')
        : (symbolFlowPhrase(branchNode.symbols?.[0]) || nodeFlowPhrase(branchNode, rightLabel === 'Depends On' ? 'Use Shared Code' : 'Second Step')),
      rightDetails: dependencyNode
        ? nodeDetailLines(dependencyNode, 2)
        : nodeDetailLines(branchNode, 2),
      rightShape: dependencyNode ? flowShapeForNode(dependencyNode, 'external') : flowShapeForNode(branchNode, 'process'),
      leftEndEdge: 'returns',
      rightEndEdge: 'returns',
      endLabel: outcomeFlowPhrase(groupNode.description, groupNode.role, 'Exit Block'),
      endDetails: [],
      endShape: groupNode.kind === 'test' ? 'test' : 'end',
    }}),
  }};
}}

function buildFileFlowModel(fileNode) {{
  const callers = (importedByNode[fileNode.id] || [])
    .map(item => nodeIndex[item.id])
    .filter(Boolean);
  const dependencies = (importsByNode[fileNode.id] || [])
    .map(item => nodeIndex[item.id])
    .filter(Boolean);
  const sortedSymbols = [...(fileNode.symbols || [])]
    .filter(symbol => symbol.kind !== 'import')
    .sort((a, b) => (a.line || 0) - (b.line || 0))
    .slice(0, 6);

  const leftItems = callers.length > 0
    ? rankChildNodes(callers).slice(0, 3).map(node => itemFromNode(node, 'Caller', 'This file is reached from here.'))
    : [{{ title: fileNode.role ? humanizeLabel(fileNode.role) : 'Standalone file', meta: 'Entry context', summary: 'No direct callers were found in the import graph.' }}];

  const centerItems = sortedSymbols.length > 0
    ? sortedSymbols.map(symbol => ({{
        title: symbol.kind === 'function' ? symbol.name : symbol.name,
        meta: humanizeLabel(symbol.kind) + (symbol.line ? ' · line ' + symbol.line : ''),
        summary: '',
      }}))
    : [itemFromNode(fileNode, fileNode.role ? humanizeLabel(fileNode.role) : 'File', 'No named top-level symbols were extracted from this file.')];

  const rightItems = dependencies.length > 0
    ? rankChildNodes(dependencies).slice(0, 4).map(node => itemFromNode(node, 'Dependency', 'This file imports it directly.'))
    : [{{ title: 'No direct imports', meta: 'Leaf file', summary: 'This file does not import another project file in the graph.' }}];

  const triggerItem = leftItems[0];
  const focusItem = centerItems[0] || itemFromNode(fileNode, 'File', 'Main file');
  const branchItem = centerItems[1] || itemFromNode(fileNode, 'File step', 'Core work inside the file');
  const dependencyNode = dependencies[0] || null;
  const secondSymbol = sortedSymbols[1] || null;
  const semantic = fileSemantic(fileNode);

  // Use AI-generated flowchart if available, otherwise fall back to generic template
  const aiFlowchart = fileNode.flowchart;
  const diagram = aiFlowchart
    ? layoutFlowchart(aiFlowchart)
    : buildFlowDiagram({{
      startLabel: 'Enter File',
      startDetails: nodeDetailLines(fileNode, 2),
      startEdge: 'imported',
      startShape: semantic.kind === 'entry' ? 'entry' : 'start',
      focusLabel: nodeFlowPhrase(fileNode, roleFlowPhrase(fileNode.role, 'Core Logic')),
      focusDetails: symbolDetailLines(sortedSymbols, 3),
      focusShape: semantic.shape || 'decision',
      leftEdge: 'main logic',
      leftLabel: symbolFlowPhrase(sortedSymbols[0]) || nodeFlowPhrase(fileNode, 'Main Step'),
      leftDetails: sortedSymbols[0] ? [humanizeSymbolName(sortedSymbols[0])] : [],
      leftShape: semantic.shape || 'process',
      rightEdge: dependencyNode ? 'delegates to' : 'also runs',
      rightLabel: dependencyNode
        ? nodeFlowPhrase(dependencyNode, 'Use Helper')
        : (symbolFlowPhrase(secondSymbol) || roleFlowPhrase(fileNode.role, 'Second Step')),
      rightDetails: dependencyNode
        ? nodeDetailLines(dependencyNode, 2)
        : (secondSymbol ? [humanizeSymbolName(secondSymbol)] : []),
      rightShape: dependencyNode ? flowShapeForNode(dependencyNode, 'external') : (semantic.kind === 'data' ? 'data' : 'process'),
      leftEndEdge: 'returns',
      rightEndEdge: 'returns',
      endLabel: outcomeFlowPhrase(fileNode.description, fileNode.role, 'Finish Here'),
      endDetails: [],
      endShape: semantic.kind === 'test' ? 'test' : 'end',
    }});

  return {{
    eyebrow: aiFlowchart ? 'File Workflow' : 'File Workflow (generic)',
    title: fileNode.label,
    subtitle: compactText(fileNode.description || 'Autogenerated from extracted functions, classes, and import relationships for this file.', 180),
    meta: [
      {{ label: 'Functions / Types', value: fileNode.symbols.length }},
      {{ label: 'Imported By', value: fileNode.indegree }},
      {{ label: 'Imports', value: fileNode.outdegree }},
    ],
    diagram,
  }};
}}

function openFlowOverlay(targetNode) {{
  const model = targetNode && targetNode.isGroup
    ? buildGroupFlowModel(targetNode)
    : buildFileFlowModel(targetNode);
  if (!model) return;
  flowEyebrow.textContent = model.eyebrow;
  flowTitle.textContent = model.title;
  flowSubtitle.textContent = model.subtitle || '';
  flowBody.innerHTML =
    renderFlowMeta(model.meta)
    + renderFlowSvg(model.diagram);
  flowOverlay.classList.add('open');
}}

function closeFlowOverlay() {{
  flowOverlay.classList.remove('open');
}}

flowClose.addEventListener('click', closeFlowOverlay);
flowOverlay.addEventListener('click', e => {{
  if (e.target === flowOverlay) closeFlowOverlay();
}});

// ── Flow tooltip ────────────────────────────────────────────────────────────

const flowTip = document.getElementById('flow-tooltip');

flowBody.addEventListener('mouseover', e => {{
  const g = e.target.closest('.flow-node-group[data-ft-tooltip]');
  if (!g) return;
  const desc = g.dataset.ftTooltip || '';
  if (!desc) return;
  flowTip.innerHTML = `<div class="ft-detail">${{esc(desc)}}</div>`;
  flowTip.style.display = 'block';
}});

flowBody.addEventListener('mousemove', e => {{
  if (flowTip.style.display !== 'block') return;
  const pad = 16;
  let x = e.clientX + pad;
  let y = e.clientY + pad;
  // Keep tooltip inside viewport
  const rect = flowTip.getBoundingClientRect();
  if (x + rect.width > window.innerWidth - 8) x = e.clientX - rect.width - pad;
  if (y + rect.height > window.innerHeight - 8) y = e.clientY - rect.height - pad;
  flowTip.style.left = x + 'px';
  flowTip.style.top = y + 'px';
}});

flowBody.addEventListener('mouseout', e => {{
  const g = e.target.closest('.flow-node-group[data-ft-tooltip]');
  if (!g) return;
  const related = e.relatedTarget;
  if (related && g.contains(related)) return;
  flowTip.style.display = 'none';
}});

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

  const miniNodes = fitNodesForViewport().filter(n => isVisible(n));
  if (miniNodes.length === 0) return;

  // Compute world bounds
  let wx0 = Infinity, wy0 = Infinity, wx1 = -Infinity, wy1 = -Infinity;
  for (const n of miniNodes) {{
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
  for (const n of miniNodes) {{
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
  const vx1 = (canvasW() - pan.x) / zoom, vy1 = (canvasH() - pan.y) / zoom;
  mctx.strokeStyle = 'rgba(88,166,255,0.6)';
  mctx.lineWidth = 1;
  mctx.strokeRect(
    vx0 * sc + offX, vy0 * sc + offY,
    (vx1 - vx0) * sc, (vy1 - vy0) * sc
  );
}}

minimap.addEventListener('click', e => {{
  const mw = minimap.width, mh = minimap.height;
  const miniNodes = fitNodesForViewport().filter(n => isVisible(n));
  if (miniNodes.length === 0) return;
  let wx0 = Infinity, wy0 = Infinity, wx1 = -Infinity, wy1 = -Infinity;
  for (const n of miniNodes) {{
    wx0 = Math.min(wx0, n.x - n.w / 2);
    wy0 = Math.min(wy0, n.y - n.h / 2);
    wx1 = Math.max(wx1, n.x + n.w / 2);
    wy1 = Math.max(wy1, n.y + n.h / 2);
  }}
  const wspan = Math.max(wx1 - wx0, 1), hspan = Math.max(wy1 - wy0, 1);
  const pad = 8;
  const sc = Math.min((mw - pad * 2) / wspan, (mh - pad * 2) / hspan);
  const offX = pad + (mw - pad * 2 - wspan * sc) / 2 - wx0 * sc;
  const offY = pad + (mh - pad * 2 - hspan * sc) / 2 - wy0 * sc;
  const worldX = (e.offsetX - offX) / sc;
  const worldY = (e.offsetY - offY) / sc;
  pan.x = canvasW() / 2 - worldX * zoom;
  pan.y = canvasH() / 2 - worldY * zoom;
  viewportWasManuallyMoved = true;
  draw();
}});

// ── Neighbor highlight ────────────────────────────────────────────────────────

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

// ── Double-click: expand/collapse groups ─────────────────────────────────────

canvas.addEventListener('dblclick', e => {{
  const {{ x: wx, y: wy }} = worldCoords(e.offsetX, e.offsetY);
  const n = nodeAt(wx, wy);
  if (!n && groupingState === 'grouped' && pinnedGroupIds.size > 0 && !flowOverlay.classList.contains('open')) {{
    pinnedGroupIds.clear();
    draw();
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
      if (flowOverlay.classList.contains('open')) {{
        closeFlowOverlay();
        break;
      }}
      selectedNode = null; highlightSet = null; blastRadiusSet = new Set(); renderDefaultSidebar(); draw();
      break;
    case 'b': case 'B':
      if (pinnedGroupIds.size > 0) {{ pinnedGroupIds.clear(); draw(); }}
      break;
    case 'f': case 'F':
      zoomToFit();
      break;
    case '?':
      toggleHelp();
      break;
  }}
}});

// ── Zoom to fit ───────────────────────────────────────────────────────────────

function zoomToFit() {{
  const fitNodes = fitNodesForViewport();
  if (fitNodes.length === 0) return;
  const bounds = graphBounds(fitNodes);
  if (!bounds) return;
  fitZoomLevel = computeFitZoom(canvasW(), canvasH(), fitNodes);
  zoom = fitZoomLevel;
  userZoomScale = 1;
  pan.x = canvasW() / 2 - ((bounds.wx0 + bounds.wx1) / 2) * zoom;
  pan.y = canvasH() / 2 - ((bounds.wy0 + bounds.wy1) / 2) * zoom;
  viewportWasManuallyMoved = false;
  draw();
}}

// ── Help overlay ──────────────────────────────────────────────────────────────

function toggleHelp() {{
  const el = document.getElementById('help-overlay');
  el.style.display = el.style.display === 'block' ? 'none' : 'block';
}}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function renderStatsBar() {{
  const sb = document.getElementById('lp-statsbar');
  if (!sb || !METRICS) return;

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

// ── Language bar (GitHub-style) ──────────────────────────────────────────────

function renderLangBar() {{
  const container = document.getElementById('lp-langs');
  if (!container) return;
  if (!LANG_COUNTS || Object.keys(LANG_COUNTS).length === 0) {{
    container.style.display = 'none';
    return;
  }}

  const total = Object.values(LANG_COUNTS).reduce((a, b) => a + b, 0);
  if (total === 0) {{ container.style.display = 'none'; return; }}

  const sorted = Object.entries(LANG_COUNTS).sort((a, b) => b[1] - a[1]);

  let barHTML = '<div class="lp-langbar">';
  let labelsHTML = '<div class="lp-lang-labels">';

  for (const [lang, bytes] of sorted) {{
    const pct = (bytes / total * 100);
    const pctStr = pct < 0.1 ? '<0.1' : pct.toFixed(1);
    const color = COLORS[lang] || COLORS['other'] || '#888';
    const name = lang.charAt(0).toUpperCase() + lang.slice(1);

    barHTML += `<div class="lang-segment" style="width:${{pct}}%;background:${{color}}"></div>`;
    labelsHTML += `<div class="lp-lang-label"><span class="lp-lang-dot" style="background:${{color}}"></span>${{pctStr}}% ${{name}}</div>`;
  }}

  barHTML += '</div>';
  labelsHTML += '</div>';
  container.innerHTML = barHTML + labelsHTML;
}}

// ── Summary + Health panel ───────────────────────────────────────────────────

function renderSummary() {{
  if (!HEALTH_SCORE) return;
  const el = document.getElementById('tb-health');
  if (!el) return;
  const score = Math.max(1, Math.min(10, HEALTH_SCORE));
  const color = score >= 8 ? '#22c55e' : score >= 5 ? '#f59e0b' : '#ef4444';
  el.style.cssText = `font-size:11px;color:${{color}};font-weight:600;white-space:nowrap`;
  el.textContent = score + '/10';
}}

// ── Blast radius ────────────────────────────────────────────────────────────
// BFS from a selected node following REVERSE edges (importedBy) to find all
// transitively affected files. Returns set of node IDs.

let blastRadiusSet = new Set();

function computeBlastRadius(nodeId) {{
  const visited = new Set();
  const queue = [nodeId];
  visited.add(nodeId);
  while (queue.length > 0) {{
    const id = queue.shift();
    const dependents = importedByNode[id] || [];
    for (const dep of dependents) {{
      if (!visited.has(dep.id)) {{
        visited.add(dep.id);
        queue.push(dep.id);
      }}
    }}
  }}
  visited.delete(nodeId); // don't include the node itself
  return visited;
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
try {{ renderDefaultSidebar(); }} catch(e) {{ console.error('[prefxplain] renderDefaultSidebar failed:', e); }}
try {{ renderStatsBar(); }} catch(e) {{ console.error('[prefxplain] renderStatsBar failed:', e); }}
try {{ renderLangBar(); }} catch(e) {{ console.error('[prefxplain] renderLangBar failed:', e); }}
try {{ renderSummary(); }} catch(e) {{ console.error('[prefxplain] renderSummary failed:', e); }}

// Initialize minimap size
if (minimap) {{ minimap.width = 160; minimap.height = 100; }}

// Start: build groups, open them all so the main view reads as
// container-with-children (not scattered file cards), then run the
// architecture-block layout. We bump each group's w/h to its expanded
// container size BEFORE laying out, so the topological row/column layout
// reserves enough space for every container.
(function initLayout() {{
  layoutMode = 'layered';
  buildGroups();
  if (groupingState === 'grouped') {{
    for (const gid of Object.keys(groupMap)) pinnedGroupIds.add(gid);
    // Use the full expanded container size for layout so the row/column
    // placer actually sees how much room each group will take up. Keep the
    // closed-state dimensions in sync so overlap resolution and hit-testing
    // use the same numbers we laid out with.
    //
    // Singleton groups (exactly 1 child) are a special case: wrapping one
    // block inside a group container adds nothing — the group and the child
    // carry the same information. Collapse them to a single-block visual
    // by unpinning (so the draw loop takes the closed-group path) and
    // shrinking them to standard node dimensions. We also inherit the
    // child's semantic shape so the rendered block reads correctly.
    for (const g of Object.values(groupMap)) {{
      const childIds = g.childIds || [];
      if (childIds.length === 1) {{
        pinnedGroupIds.delete(g.id);
        const child = nodeIndex[childIds[0]];
        // Singleton renders through the regular file-node path (see the
        // isSingletonGroup branch in draw()), so use standard node
        // dimensions. We still inherit the child's shape so the block
        // looks semantically the same as the file it wraps.
        g.w = NODE_W;
        g.h = NODE_H_BASE;
        g._closedW = g.w;
        g._closedH = g.h;
        if (child) g.shape = child.shape || child.kind || g.shape;
        continue;
      }}
      const layout = layoutOpenGroupChildren(g);
      g.w = layout.openW;
      g.h = layout.openH;
      g._closedW = layout.openW;
      g._closedH = layout.openH;
    }}
  }}
  layoutBlocks(visibleNodes, visibleEdges);
  if (groupingState === 'grouped') {{
    resolveGroupOverlaps();
  }}
  simRunning = false;
  draw();
  drawMinimap();
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
    clusters_by_group_json = _safe_json(render_data.get("clusters_by_group", {}))
    group_descriptions_json = _safe_json(render_data.get("group_descriptions", {}))
    role_order_json = _safe_json(render_data.get("role_order", []))
    role_subtitles_json = _safe_json(render_data.get("role_subtitles", {}))
    metrics_json = _safe_json(render_data.get("metrics", {}))
    node_metrics_json = _safe_json(render_data.get("node_metrics", {}))
    health_json = _safe_json(render_data.get("health", {}))
    lang_counts_json = _safe_json(render_data.get("language_counts", {}))
    lang_file_counts_json = _safe_json(render_data.get("language_file_counts", {}))

    # Summary + health from metadata
    summary_json = _safe_json(meta.summary if meta else "")
    health_score_json = _safe_json(meta.health_score if meta else 0)
    health_notes_json = _safe_json(meta.health_notes if meta else "")

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
        clusters_by_group_json=clusters_by_group_json,
        group_descriptions_json=group_descriptions_json,
        role_order_json=role_order_json,
        role_subtitles_json=role_subtitles_json,
        metrics_json=metrics_json,
        node_metrics_json=node_metrics_json,
        health_json=health_json,
        lang_counts_json=lang_counts_json,
        lang_file_counts_json=lang_file_counts_json,
        summary_json=summary_json,
        health_score_json=health_score_json,
        health_notes_json=health_notes_json,
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
