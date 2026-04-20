// ui/flow-modal.js — double-click a file card to open its modal.
//
// Three-panel body: Dependencies (left) · Logic flow (center) · Complexity
// (right), with the full description spanning the bottom. The center panel
// renders the AI-authored flowchart when present and falls back to the
// stored code preview otherwise. Escape or click-outside to close.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

// ---- shared helpers --------------------------------------------------------

function _truncate(s, n) {
  const str = String(s == null ? '' : s);
  return str.length > n ? str.slice(0, n - 1).trimEnd() + '\u2026' : str;
}

function _countLines(text) {
  if (!text) return 0;
  let n = 1;
  for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) === 10) n++;
  return n;
}

// ---- dependency list panel -------------------------------------------------

// One row per imported/importing file. Group-colored left stripe so the reader
// can glance-match the file back to its architectural group in the main map.
function _depRow(file, groupsMeta, T) {
  const meta = groupsMeta[file.group] || {};
  const color = PX.groupColor(file.group, meta);
  return `<div style="display:flex;align-items:center;gap:8px;padding:7px 10px;background:${T.bg};border:1px solid ${T.border};border-left:3px solid ${color};border-radius:3px">
    <span style="font-family:${T.mono};font-size:10.5px;color:${T.ink};font-weight:600;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${PX.escapeXml(file.label)}</span>
    <span style="font-family:${T.mono};font-size:8.5px;color:${T.inkFaint};text-transform:uppercase;letter-spacing:0.8px;white-space:nowrap">${PX.escapeXml(file.group || '')}</span>
  </div>`;
}

// A single section (Uses / Used by). Collapses long lists behind a disclosure
// so hubs with 40 importers don't push the flowchart off-screen.
function _depSection(title, tone, items, emptyText, T, groupsMeta, sectionId) {
  const head = `<div style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${tone};margin-bottom:6px">${PX.escapeXml(title)}</div>`;
  if (!items.length) {
    return `<div>${head}<div style="padding:10px;background:${T.bg};border:1px dashed ${T.borderAlt};border-radius:4px;font-family:${T.mono};font-size:10.5px;color:${T.inkFaint};text-align:center">${PX.escapeXml(emptyText)}</div></div>`;
  }
  const VISIBLE = 8;
  const first = items.slice(0, VISIBLE).map(f => _depRow(f, groupsMeta, T)).join('');
  const rest = items.slice(VISIBLE).map(f => _depRow(f, groupsMeta, T)).join('');
  const hasRest = items.length > VISIBLE;
  const hiddenId = `px-dep-more-${sectionId}`;
  const toggle = hasRest
    ? `<button data-toggle="${hiddenId}" style="margin-top:4px;padding:6px 10px;background:${T.panelAlt};border:1px solid ${T.border};border-radius:4px;font-family:${T.mono};font-size:10px;color:${T.inkMuted};cursor:pointer;width:100%;text-align:center">+ ${items.length - VISIBLE} more</button>`
    : '';
  const hidden = hasRest
    ? `<div id="${hiddenId}" style="display:none;flex-direction:column;gap:5px;margin-top:5px">${rest}</div>`
    : '';
  return `<div>${head}<div style="display:flex;flex-direction:column;gap:5px;max-height:360px;overflow:auto">${first}${hidden}${toggle}</div></div>`;
}

function _depsPanel(importers, deps, T, groupsMeta) {
  const usesTitle = `Uses \u00b7 ${deps.length} ${deps.length === 1 ? 'dep' : 'deps'}`;
  const byTitle = `Used by \u00b7 ${importers.length} ${importers.length === 1 ? 'caller' : 'callers'}`;
  return `<div style="display:flex;flex-direction:column;gap:18px">
    ${_depSection(usesTitle, T.accent, deps, 'no internal deps \u2014 leaf module', T, groupsMeta, 'uses')}
    ${_depSection(byTitle, T.good, importers, 'nobody imports this \u2014 top of chain', T, groupsMeta, 'by')}
  </div>`;
}

// ---- center panel: flowchart or code preview -------------------------------

function _centerPanel(node, T) {
  if (_hasFlowchart(node)) {
    return _renderFlowchart(node.flowchart, T);
  }
  const preview = node.preview || '';
  if (!preview.trim()) {
    return `<div style="padding:24px;background:${T.bg};border:1px dashed ${T.borderAlt};border-radius:6px;font-family:${T.mono};font-size:11px;color:${T.inkFaint};text-align:center">no flowchart and no preview available for this file</div>`;
  }
  const lines = _countLines(preview);
  const header = `<div style="display:flex;align-items:center;gap:8px;font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint};margin-bottom:8px">
    <span>preview</span><span style="color:${T.borderAlt}">\u00b7</span>
    <span>first ${lines} line${lines === 1 ? '' : 's'}</span>
  </div>`;
  const code = `<pre style="margin:0;padding:14px 16px;background:${T.codeBg || T.bg};border:1px solid ${T.border};border-radius:6px;overflow:auto;max-height:70vh;font-family:${T.mono};font-size:11.5px;line-height:1.45;color:${T.ink2};white-space:pre">${PX.escapeXml(preview)}</pre>`;
  return `<div>${header}${code}</div>`;
}

// ---- right panel: complexity -----------------------------------------------

// Rank a pagerank value against every other node's pagerank. Returns a tier
// name so the UI shows "Core" / "Connected" / "Leaf" instead of raw 0.001-ish
// float noise users can't interpret.
function _centralityTier(nodeId, nodeMetrics, allNodes) {
  if (!nodeMetrics || !allNodes || !allNodes.length) return null;
  const my = (nodeMetrics[nodeId] || {}).pagerank;
  if (typeof my !== 'number') return null;
  const sorted = allNodes
    .map(n => (nodeMetrics[n.id] || {}).pagerank || 0)
    .sort((a, b) => b - a);
  const rank = sorted.findIndex(v => v <= my); // top-ranked = index 0
  const percentile = rank < 0 ? 100 : (rank / sorted.length) * 100;
  if (percentile <= 10) return { label: 'Core',      tone: 'warn',  pct: Math.round(percentile) };
  if (percentile <= 50) return { label: 'Connected', tone: 'accent', pct: Math.round(percentile) };
  return { label: 'Leaf', tone: 'muted', pct: Math.round(percentile) };
}

function _metricRow(label, value, T) {
  return `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:${T.bg};border:1px solid ${T.border};border-radius:4px">
    <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.2px;text-transform:uppercase;color:${T.inkFaint}">${PX.escapeXml(label)}</span>
    <span style="font-family:${T.mono};font-size:11px;color:${T.ink};font-weight:600;text-align:right">${value}</span>
  </div>`;
}

function _fanBars(inDeg, outDeg, T) {
  const maxBar = 70;
  const peak = Math.max(1, inDeg, outDeg);
  const inW = (inDeg / peak) * maxBar;
  const outW = (outDeg / peak) * maxBar;
  const bar = (label, w, count, color) => `<div style="display:flex;align-items:center;gap:8px">
    <span style="font-family:${T.mono};font-size:9px;letter-spacing:1px;color:${color};font-weight:600;min-width:24px">${label}</span>
    <div style="flex:1;height:6px;background:${T.bg};border-radius:2px;overflow:hidden"><div style="width:${w}px;height:100%;background:${color};border-radius:2px"></div></div>
    <span style="font-family:${T.mono};font-size:10.5px;color:${T.ink};font-weight:600;min-width:20px;text-align:right">${count}</span>
  </div>`;
  return `<div style="display:flex;flex-direction:column;gap:6px;padding:8px 10px;background:${T.bg};border:1px solid ${T.border};border-radius:4px">
    <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.2px;text-transform:uppercase;color:${T.inkFaint}">Fan in / out</span>
    ${bar('IN', inW, inDeg, T.good)}
    ${bar('OUT', outW, outDeg, T.accent)}
  </div>`;
}

function _tierPill(tier, T) {
  if (!tier) return '';
  const color = tier.tone === 'warn' ? T.warn : tier.tone === 'accent' ? T.accent : T.inkFaint;
  const bg = tier.tone === 'warn' ? T.warnTint : tier.tone === 'accent' ? T.accentTint : T.panelAlt;
  return `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:${T.bg};border:1px solid ${T.border};border-radius:4px">
    <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.2px;text-transform:uppercase;color:${T.inkFaint}">Centrality</span>
    <span style="display:inline-flex;align-items:center;gap:6px">
      <span style="font-family:${T.mono};font-size:10px;padding:2px 8px;background:${bg};color:${color};border:1px solid ${color};border-radius:3px;text-transform:uppercase;letter-spacing:1px;font-weight:600">${PX.escapeXml(tier.label)}</span>
      <span style="font-family:${T.mono};font-size:10px;color:${T.inkMuted}">top ${tier.pct}%</span>
    </span>
  </div>`;
}

function _rolePills(node, T) {
  const role = node.semantic_role || '';
  const pattern = node.pattern || '';
  if (!role && !pattern) return '';
  const pill = (text, color) => `<span style="font-family:${T.mono};font-size:9.5px;padding:2px 8px;background:${T.panelAlt};color:${color};border:1px solid ${color};border-radius:3px;text-transform:uppercase;letter-spacing:1px;font-weight:600">${PX.escapeXml(text)}</span>`;
  const parts = [];
  if (role)    parts.push(pill(role,    T.accent2 || T.accent));
  if (pattern) parts.push(pill(pattern, T.good));
  return `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:${T.bg};border:1px solid ${T.border};border-radius:4px;gap:10px;flex-wrap:wrap">
    <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.2px;text-transform:uppercase;color:${T.inkFaint}">Role</span>
    <span style="display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap">${parts.join('')}</span>
  </div>`;
}

function _complexityPanel(node, inDeg, outDeg, nodeMetrics, allNodes, T) {
  const kb = Math.round((node.size || 0) / 1024);
  const lines = _countLines(node.preview || '') || Math.max(1, Math.round((node.size || 0) / 40));
  const sizeRow = _metricRow('Size', `${kb}k \u00b7 ~${lines} line${lines === 1 ? '' : 's'}`, T);
  const fanRow = _fanBars(inDeg, outDeg, T);
  const metrics = (nodeMetrics || {})[node.id] || {};
  const tier = _centralityTier(node.id, nodeMetrics, allNodes);
  const tierRow = _tierPill(tier, T);
  const cycleRow = metrics.in_cycle
    ? `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:${T.warnTint};border:1px solid ${T.warn};border-radius:4px">
        <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.2px;text-transform:uppercase;color:${T.warn}">Cycle</span>
        <span style="font-family:${T.mono};font-size:10.5px;color:${T.warn};font-weight:600">In circular dep</span>
      </div>`
    : '';
  const roleRow = _rolePills(node, T);
  return `<div style="display:flex;flex-direction:column;gap:8px">
    ${sizeRow}
    ${fanRow}
    ${tierRow}
    ${cycleRow}
    ${roleRow}
  </div>`;
}

// ---- AI-generated flowchart renderer ---------------------------------------

// Color per node.type. Start/end pop with semantic green/red, decisions sit
// on warn-amber, tests carry the reserved test-purple, everything else uses
// the accent so the flow reads as one cohesive process.
function _flowchartColor(type, T) {
  switch (type) {
    case 'start':    return T.good;
    case 'end':      return T.danger;
    case 'decision': return T.warn;
    case 'test':     return T.testColor;
    default:         return T.accent;
  }
}

function _flowchartTint(type, T) {
  switch (type) {
    case 'start':    return T.goodTint;
    case 'end':      return T.dangerTint;
    case 'decision': return T.warnTintSoft;
    case 'test':     return T.testTint;
    default:         return T.accentTintSoft;
  }
}

// Render a single node: pill (start/end), diamond (decision), rounded rect
// (everything else). Color encodes the type so we don't burn pixels on a
// chip — label and optional description sit centered inside the shape.
function _renderFlowchartNode(node, p, T) {
  const color = _flowchartColor(node.type, T);
  const fill = _flowchartTint(node.type, T);
  const cx = p.x + p.w / 2;
  const cy = p.y + p.h / 2;
  const isDiamond = node.type === 'decision';
  const isPill = node.type === 'start' || node.type === 'end';

  const labelMax = isDiamond ? 22 : 28;
  const label = _truncate(node.label, labelMax);
  // Diamonds are visually busy — skip the description to keep them readable.
  const desc = (!isDiamond && node.description) ? _truncate(node.description, 42) : '';

  let shape;
  if (isPill) {
    shape = `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="${p.h / 2}" ry="${p.h / 2}" fill="${fill}" stroke="${color}" stroke-width="1.6"/>`;
  } else if (isDiamond) {
    const pts = `${cx},${p.y} ${p.x + p.w},${cy} ${cx},${p.y + p.h} ${p.x},${cy}`;
    shape = `<polygon points="${pts}" fill="${fill}" stroke="${color}" stroke-width="1.6"/>`;
  } else {
    shape = `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="6" ry="6" fill="${fill}" stroke="${color}" stroke-width="1.4"/>`;
  }

  const labelY = desc ? cy - 5 : cy;
  const labelText = `<text x="${cx}" y="${labelY}" text-anchor="middle" dominant-baseline="middle" font-family="${T.mono}" font-size="11.5" font-weight="600" fill="${T.ink}">${PX.escapeXml(label)}</text>`;
  const descText = desc
    ? `<text x="${cx}" y="${cy + 11}" text-anchor="middle" dominant-baseline="middle" font-family="${T.ui}" font-size="10" fill="${T.inkMuted}">${PX.escapeXml(desc)}</text>`
    : '';

  return shape + labelText + descText;
}

// Route an edge between two laid-out nodes. Down-flowing edges (the common
// case) get an orthogonal step that keeps the diagram readable; back-edges
// (cycles, retries) loop around the right side so they never cross a node.
function _renderFlowchartEdge(edge, pos, T) {
  const a = pos[edge.from];
  const b = pos[edge.to];
  if (!a || !b) return '';

  const ax = a.x + a.w / 2;
  const bx = b.x + b.w / 2;
  let path;
  let mx;
  let my;

  if (b.y > a.y) {
    // Down-flowing: bottom of A → top of B with a horizontal mid-step.
    const ay = a.y + a.h;
    const by = b.y;
    const midY = ay + (by - ay) / 2;
    path = `M${ax},${ay} L${ax},${midY} L${bx},${midY} L${bx},${by}`;
    mx = (ax + bx) / 2;
    my = midY;
  } else {
    // Back-edge or sideways: route around the right side of both nodes.
    const sx = a.x + a.w;
    const sy = a.y + a.h / 2;
    const tx = b.x + b.w;
    const ty = b.y + b.h / 2;
    const off = 28;
    const rightX = Math.max(sx, tx) + off;
    path = `M${sx},${sy} L${rightX},${sy} L${rightX},${ty} L${tx},${ty}`;
    mx = rightX;
    my = (sy + ty) / 2;
  }

  const line = `<path d="${path}" fill="none" stroke="${T.inkFaint}" stroke-width="1.4" marker-end="url(#fc-arrow)"/>`;
  if (!edge.label) return line;

  // Conditional labels (e.g. "yes" / "no" off a decision) get a paneled
  // background chip so they stay legible when crossing other lines.
  const labelText = _truncate(edge.label, 18);
  const labelW = Math.max(labelText.length * 5.6 + 14, 28);
  const labelH = 16;
  const bg = `<rect x="${mx - labelW / 2}" y="${my - labelH / 2}" width="${labelW}" height="${labelH}" rx="3" ry="3" fill="${T.panel}" stroke="${T.borderAlt}" stroke-width="0.8"/>`;
  const txt = `<text x="${mx}" y="${my}" text-anchor="middle" dominant-baseline="middle" font-family="${T.mono}" font-size="9.5" fill="${T.inkMuted}">${PX.escapeXml(labelText)}</text>`;
  return line + bg + txt;
}

// Lay out nodes by BFS depth from the start, then render the SVG. Returns
// the empty string if the payload is too thin to draw a meaningful diagram —
// the caller treats that as "fall back to the dependency schematic".
function _renderFlowchart(fc, T) {
  if (!fc || !Array.isArray(fc.nodes) || !Array.isArray(fc.edges)) return '';
  const nodes = fc.nodes;
  const edges = fc.edges;
  if (nodes.length < 2 || edges.length < 1) return '';

  const out = {};
  const inDeg = {};
  nodes.forEach(n => { out[n.id] = []; inDeg[n.id] = 0; });
  edges.forEach(e => {
    if (out[e.from]) out[e.from].push(e.to);
    if (inDeg[e.to] != null) inDeg[e.to] += 1;
  });

  // Pick a start: explicit type=start wins, else the first node with no
  // incoming edges, else just the first declared node.
  let startId = (nodes.find(n => n.type === 'start') || {}).id;
  if (!startId) startId = (nodes.find(n => inDeg[n.id] === 0) || nodes[0]).id;

  // BFS rank assignment. Cycles are tolerated because we only assign each
  // node once (the first depth at which BFS reaches it).
  const rank = {};
  rank[startId] = 0;
  const queue = [startId];
  while (queue.length) {
    const id = queue.shift();
    for (const next of out[id]) {
      if (rank[next] == null) {
        rank[next] = rank[id] + 1;
        queue.push(next);
      }
    }
  }
  // Anything BFS couldn't reach (orphan branches) gets stacked below the
  // main flow so it's still drawn, just visually quarantined.
  let maxRank = 0;
  Object.values(rank).forEach(r => { if (r > maxRank) maxRank = r; });
  for (const node of nodes) {
    if (rank[node.id] == null) {
      maxRank += 1;
      rank[node.id] = maxRank;
    }
  }

  const byRank = {};
  for (const node of nodes) {
    const r = rank[node.id];
    if (!byRank[r]) byRank[r] = [];
    byRank[r].push(node);
  }
  const ranks = Object.keys(byRank).map(Number).sort((a, b) => a - b);

  const NODE_W = 200;
  const NODE_H = 60;
  const COL_GAP = 36;
  const ROW_PITCH = 110;
  const PAD = 36;

  let maxCols = 0;
  for (const r of ranks) maxCols = Math.max(maxCols, byRank[r].length);
  const innerW = maxCols * NODE_W + (maxCols - 1) * COL_GAP;
  const totalW = PAD * 2 + innerW;
  const totalH = PAD * 2 + (ranks.length - 1) * ROW_PITCH + NODE_H;

  const pos = {};
  for (let ri = 0; ri < ranks.length; ri++) {
    const row = byRank[ranks[ri]];
    const rowW = row.length * NODE_W + (row.length - 1) * COL_GAP;
    const startX = PAD + (innerW - rowW) / 2;
    const y = PAD + ri * ROW_PITCH;
    row.forEach((node, i) => {
      pos[node.id] = {
        x: startX + i * (NODE_W + COL_GAP),
        y,
        w: NODE_W,
        h: NODE_H,
      };
    });
  }

  // Edges first so node fills cover the line endpoints cleanly.
  const edgeSvg = edges.map(e => _renderFlowchartEdge(e, pos, T)).join('');
  const nodeSvg = nodes.map(node => _renderFlowchartNode(node, pos[node.id], T)).join('');

  const svg = `<svg width="${totalW}" height="${totalH}" viewBox="0 0 ${totalW} ${totalH}" xmlns="http://www.w3.org/2000/svg" style="display:block;margin:0 auto">
    <defs>
      <marker id="fc-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="${T.inkFaint}"/>
      </marker>
    </defs>
    ${edgeSvg}
    ${nodeSvg}
  </svg>`;

  return `<div style="overflow:auto;max-height:70vh;background:${T.bg};border:1px solid ${T.border};border-radius:6px;padding:16px">${svg}</div>`;
}

function _hasFlowchart(node) {
  const fc = node && node.flowchart;
  return !!(fc && Array.isArray(fc.nodes) && Array.isArray(fc.edges)
    && fc.nodes.length >= 2 && fc.edges.length >= 1);
}

// ---- modal entry point -----------------------------------------------------

PX.ui.flowModal = function flowModal({ nodeId, graph, index, groupsMeta, onClose }) {
  const T = PX.T;
  const n = index.byId[nodeId];
  if (!n) return null;

  const importers = (index.importers[nodeId] || []).map(id => index.byId[id]).filter(Boolean);
  const deps = (index.importsOf[nodeId] || []).map(id => index.byId[id]).filter(Boolean);
  const inDeg = importers.length;
  const outDeg = deps.length;
  const isHub = inDeg >= 8;
  const isEntry = n.role === 'entry_point';
  const isTest = n.role === 'test';
  const allNodes = graph && Array.isArray(graph.nodes) ? graph.nodes : [];
  const nodeMetrics = (graph && graph.nodeMetrics) || {};

  const desc = n.description || n.short || '';
  const titleText = n.short || n.label;
  const headerBadges = [
    isHub ? `<span style="font-family:${T.mono};font-size:9.5px;padding:2px 7px;background:${T.warnTint};color:${T.warn};border:1px solid ${T.warn};border-radius:3px;text-transform:uppercase;letter-spacing:1px">SPOF</span>` : '',
    isEntry && !isHub ? `<span style="font-family:${T.mono};font-size:9.5px;padding:2px 7px;background:${T.accentTint};color:${T.accent};border:1px solid ${T.accent};border-radius:3px;text-transform:uppercase;letter-spacing:1px">Entry</span>` : '',
    isTest ? `<span style="font-family:${T.mono};font-size:9.5px;padding:2px 7px;background:${T.testTint || T.accentTint};color:${T.testColor || T.accent};border:1px solid ${T.testColor || T.accent};border-radius:3px;text-transform:uppercase;letter-spacing:1px">Test</span>` : '',
  ].filter(Boolean).join('');

  const modeLabel = _hasFlowchart(n) ? 'Logic flow' : (n.preview ? 'Code preview' : 'File');

  const isNarrow = (typeof window !== 'undefined') && window.innerWidth < 1100;
  const gridTemplate = isNarrow
    ? 'grid-template-columns:1fr;grid-auto-rows:min-content;gap:18px'
    : 'grid-template-columns:0.9fr 2.4fr 0.9fr;gap:20px';

  // On narrow viewports stack in priority order: flowchart → deps → complexity.
  // On wide viewports columns are ordered deps | flowchart | complexity.
  const centerOrder = isNarrow ? 'order:1' : '';
  const depsOrder = isNarrow ? 'order:2' : '';
  const complexOrder = isNarrow ? 'order:3' : '';

  const body = `
    <div style="display:grid;${gridTemplate};align-items:flex-start">
      <section style="${depsOrder}">
        ${_depsPanel(importers, deps, T, groupsMeta)}
      </section>
      <section style="${centerOrder};min-width:0">
        ${_centerPanel(n, T)}
      </section>
      <section style="${complexOrder}">
        ${_complexityPanel(n, inDeg, outDeg, nodeMetrics, allNodes, T)}
      </section>
    </div>
    ${desc ? `<div style="margin-top:22px;padding-top:18px;border-top:1px solid ${T.border};font-family:${T.ui};font-size:12.5px;color:${T.inkMuted};line-height:1.55;max-width:900px">${PX.escapeXml(desc)}</div>` : ''}
  `;

  const overlay = document.createElement('div');
  overlay.style.cssText = `position:fixed;inset:0;background:${T.overlay};z-index:100;display:flex;align-items:center;justify-content:center;font-family:${T.ui};backdrop-filter:blur(6px)`;

  overlay.innerHTML = `
    <div id="px-flow-card" style="background:${T.panel};border:1px solid ${T.border};border-radius:8px;width:min(1240px,96vw);max-height:92vh;overflow:auto;box-shadow:${T.shadowLg}">
      <div style="padding:14px 20px;border-bottom:1px solid ${T.border};display:flex;align-items:center;gap:12px;background:${T.panelAlt}">
        <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint}">${PX.escapeXml(modeLabel)}</span>
        <span style="color:${T.borderAlt}">\u00b7</span>
        <span style="font-family:${T.ui};font-size:14px;color:${T.ink};font-weight:600">${PX.escapeXml(titleText)}</span>
        <span style="font-family:${T.mono};font-size:10.5px;color:${T.inkFaint}">${PX.escapeXml(n.label)}</span>
        ${headerBadges}
        <span style="flex:1"></span>
        <span style="font-family:${T.mono};font-size:10px;color:${T.inkFaint}">esc to close</span>
        <button data-close style="background:transparent;border:1px solid ${T.border};color:${T.inkMuted};font-family:${T.mono};font-size:13px;width:26px;height:26px;border-radius:3px;cursor:pointer">\u00d7</button>
      </div>
      <div style="padding:22px 24px 26px">
        ${body}
      </div>
    </div>
  `;

  const close = () => { overlay.remove(); if (typeof onClose === 'function') onClose(); };
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) { close(); return; }
    if (e.target.closest('[data-close]')) { close(); return; }
    // "+N more" disclosure: swap display of the hidden list and hide the button.
    const toggleBtn = e.target.closest('[data-toggle]');
    if (toggleBtn) {
      const targetId = toggleBtn.getAttribute('data-toggle');
      const panel = overlay.querySelector('#' + CSS.escape(targetId));
      if (panel) panel.style.display = 'flex';
      toggleBtn.style.display = 'none';
    }
  });

  document.body.appendChild(overlay);
  return { close, element: overlay };
};
