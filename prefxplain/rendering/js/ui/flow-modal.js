// ui/flow-modal.js — double-click a file card to open its modal.
//
// When the node carries an AI-generated `flowchart` payload (≥2 nodes,
// ≥1 edge), the modal renders that logical flowchart as an SVG diagram.
// Otherwise it falls back to the original 3-column dependency schematic
// (importers | this file | deps) so older runs without LLM enrichment
// still produce a useful view.
//
// Escape or click-outside to close.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

// ---- shared helpers --------------------------------------------------------

function _truncate(s, n) {
  const str = String(s == null ? '' : s);
  return str.length > n ? str.slice(0, n - 1).trimEnd() + '\u2026' : str;
}

// ---- dependency-schematic fallback (importers | file | deps) ---------------

function _col(title, tone, items, emptyText, T, groupsMeta) {
  const head = `<div style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${tone};margin-bottom:8px">${PX.escapeXml(title)}</div>`;
  if (!items.length) {
    return `<div>${head}<div style="padding:12px;background:${T.bg};border:1px dashed ${T.borderAlt};border-radius:4px;font-family:${T.mono};font-size:11px;color:${T.inkFaint};text-align:center">${PX.escapeXml(emptyText)}</div></div>`;
  }
  const rows = items.map(f => {
    const meta = groupsMeta[f.group] || {};
    const color = PX.groupColor(f.group, meta);
    return `<div style="display:flex;align-items:center;gap:8px;padding:8px 10px;background:${T.bg};border:1px solid ${T.border};border-left:3px solid ${color};border-radius:3px">
      <span style="font-family:${T.mono};font-size:11px;color:${T.ink};font-weight:600;flex:1">${PX.escapeXml(f.label)}</span>
      <span style="font-family:${T.mono};font-size:9px;color:${T.inkFaint};text-transform:uppercase;letter-spacing:0.8px">${PX.escapeXml(f.group || '')}</span>
    </div>`;
  }).join('');
  return `<div>${head}<div style="display:flex;flex-direction:column;gap:6px;max-height:340px;overflow:auto">${rows}</div></div>`;
}

function _arrow(color, count) {
  return `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center">
    <svg width="40" height="40" viewBox="0 0 40 40"><line x1="2" y1="20" x2="32" y2="20" stroke="${color}" stroke-width="1.6" marker-end="url(#fmarr)"/>
    <defs><marker id="fmarr" viewBox="0 -5 10 10" refX="10" refY="0" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,-4L10,0L0,4" fill="${color}"/></marker></defs></svg>
    <span style="font-family:${PX.T.mono};font-size:9.5px;color:${color};font-weight:600">${count}</span>
  </div>`;
}

function _renderDepsSchematic(n, importersList, depsList, color, isHub, isEntry, steps, kb, T, groupsMeta) {
  return `<div style="display:grid;grid-template-columns:1fr 40px 1.1fr 40px 1fr;gap:0;align-items:center">
    ${_col(`Inputs \u00b7 ${importersList.length} ${importersList.length === 1 ? 'caller' : 'callers'}`, T.good, importersList, `nobody imports this \u2014 ${isEntry ? 'this is an entry point' : 'top of chain'}`, T, groupsMeta)}
    ${_arrow(T.good, importersList.length)}
    <div style="background:${T.bg};border:2px solid ${isHub ? T.warn : T.accent};border-radius:6px;padding:16px;box-shadow:0 0 0 4px ${isHub ? T.warnTintSoft : T.accentTintSoft}">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span style="width:6px;height:6px;background:${color};border-radius:50%"></span>
        <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint}">${PX.escapeXml(n.group || '')} / file</span>
      </div>
      <div style="font-family:${T.mono};font-size:16px;color:${T.ink};font-weight:700;margin-bottom:6px">${PX.escapeXml(n.label)}</div>
      <div style="font-family:${T.ui};font-size:12px;color:${T.inkMuted};line-height:1.5;margin-bottom:14px">${PX.escapeXml(n.description || n.short || '')}</div>
      ${steps.length ? `<div style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint};margin-bottom:8px">What it does</div>
      <ol style="margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px">
        ${steps.map((s, i) => `<li style="display:flex;gap:10px;align-items:flex-start">
          <span style="font-family:${T.mono};font-size:9.5px;color:${T.accent};margin-top:2px;min-width:18px">${String(i + 1).padStart(2, '0')}</span>
          <span style="font-family:${T.mono};font-size:11px;color:${T.ink2};line-height:1.5">${PX.escapeXml(s)}</span>
        </li>`).join('')}
      </ol>` : ''}
      <div style="margin-top:14px;display:flex;gap:16px;font-family:${T.mono};font-size:10px;color:${T.inkFaint}">
        <span>${kb}k</span><span>\u00b7</span>
        <span>fan-in ${importersList.length}</span><span>\u00b7</span>
        <span>fan-out ${depsList.length}</span>
      </div>
    </div>
    ${_arrow(T.accent, depsList.length)}
    ${_col(`Uses \u00b7 ${depsList.length} ${depsList.length === 1 ? 'dep' : 'deps'}`, T.accent, depsList, 'no internal deps \u2014 leaf module', T, groupsMeta)}
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
  const importersList = (index.importers[nodeId] || []).map(id => index.byId[id]).filter(Boolean);
  const depsList = (index.importsOf[nodeId] || []).map(id => index.byId[id]).filter(Boolean);
  const meta = groupsMeta[n.group] || {};
  const color = PX.groupColor(n.group, meta);
  const isHub = (index.importers[nodeId] || []).length >= 8;
  const isEntry = n.role === 'entry_point';
  const isTest = n.role === 'test';
  const steps = (n.highlights || []).slice(0, 4);
  const kb = Math.round((n.size || 0) / 1024);

  const hasFlow = _hasFlowchart(n);
  const modeLabel = hasFlow ? 'Logic flow' : 'Flow';

  let body;
  if (hasFlow) {
    const flowSvg = _renderFlowchart(n.flowchart, T);
    const desc = n.description || n.short || '';
    body = `
      ${desc ? `<div style="font-family:${T.ui};font-size:12.5px;color:${T.inkMuted};line-height:1.5;margin-bottom:16px;max-width:780px">${PX.escapeXml(desc)}</div>` : ''}
      ${flowSvg}
      <div style="margin-top:14px;display:flex;gap:14px;font-family:${T.mono};font-size:10px;color:${T.inkFaint};align-items:center">
        <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:6px;height:6px;background:${color};border-radius:50%"></span>${PX.escapeXml(n.group || '')}</span>
        <span>\u00b7</span>
        <span>${kb}k</span>
        <span>\u00b7</span>
        <span>fan-in ${importersList.length}</span>
        <span>\u00b7</span>
        <span>fan-out ${depsList.length}</span>
      </div>
    `;
  } else {
    body = _renderDepsSchematic(n, importersList, depsList, color, isHub, isEntry, steps, kb, T, groupsMeta);
  }

  const overlay = document.createElement('div');
  overlay.style.cssText = `position:fixed;inset:0;background:${T.overlay};z-index:100;display:flex;align-items:center;justify-content:center;font-family:${T.ui};backdrop-filter:blur(6px)`;

  overlay.innerHTML = `
    <div id="px-flow-card" style="background:${T.panel};border:1px solid ${T.border};border-radius:8px;width:min(1100px,94vw);max-height:92vh;overflow:auto;box-shadow:${T.shadowLg}">
      <div style="padding:14px 20px;border-bottom:1px solid ${T.border};display:flex;align-items:center;gap:10px;background:${T.panelAlt}">
        <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint}">${PX.escapeXml(modeLabel)}</span>
        <span style="color:${T.borderAlt}">\u00b7</span>
        <span style="font-family:${T.mono};font-size:13px;color:${T.ink};font-weight:600">${PX.escapeXml(n.label)}</span>
        <span style="font-family:${T.mono};font-size:10.5px;color:${T.inkFaint}">${PX.escapeXml(n.id)}</span>
        ${isHub ? `<span style="font-family:${T.mono};font-size:9.5px;padding:2px 7px;background:${T.warnTint};color:${T.warn};border:1px solid ${T.warn};border-radius:3px;text-transform:uppercase;letter-spacing:1px">SPOF</span>` : ''}
        ${isEntry && !isHub ? `<span style="font-family:${T.mono};font-size:9.5px;padding:2px 7px;background:${T.accentTint};color:${T.accent};border:1px solid ${T.accent};border-radius:3px;text-transform:uppercase;letter-spacing:1px">Entry</span>` : ''}
        ${isTest ? `<span style="font-family:${T.mono};font-size:9.5px;padding:2px 7px;background:${T.testTint};color:${T.testColor};border:1px solid ${T.testColor};border-radius:3px;text-transform:uppercase;letter-spacing:1px">Test</span>` : ''}
        <span style="flex:1"></span>
        <span style="font-family:${T.mono};font-size:10px;color:${T.inkFaint}">esc to close</span>
        <button data-close style="background:transparent;border:1px solid ${T.border};color:${T.inkMuted};font-family:${T.mono};font-size:13px;width:26px;height:26px;border-radius:3px;cursor:pointer">\u00d7</button>
      </div>
      <div style="padding:20px 24px 28px">
        ${body}
      </div>
    </div>
  `;

  const close = () => { overlay.remove(); if (typeof onClose === 'function') onClose(); };
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
    if (e.target.closest('[data-close]')) close();
  });

  document.body.appendChild(overlay);
  return { close, element: overlay };
};
