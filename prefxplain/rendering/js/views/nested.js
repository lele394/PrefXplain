// views/nested.js — Nested renderer.
// Split layout:
//   - left: compact overview of all groups + aggregate inter-group links
//   - right: one focused group's file-level detail

window.PX = window.PX || {};
PX.views = PX.views || {};

function _translateNodes(nodesById, dx, dy) {
  const out = {};
  for (const [id, node] of Object.entries(nodesById || {})) {
    out[id] = { ...node, x: (node.x || 0) + dx, y: (node.y || 0) + dy };
  }
  return out;
}

function _translateEdge(edge, dx, dy) {
  const out = {
    ...edge,
    points: (edge.points || []).map(p => ({ x: p.x + dx, y: p.y + dy })),
  };
  if (edge.labelX != null) out.labelX = edge.labelX + dx;
  if (edge.labelY != null) out.labelY = edge.labelY + dy;
  if (edge.bus) {
    out.bus = {
      ...edge.bus,
      trunkX: edge.bus.trunkX + dx,
      trunkY: edge.bus.trunkY + dy,
    };
  }
  return out;
}

function _routePairs(index, groupId) {
  const pairs = (index && index.groupPairStats) || [];
  const outgoing = pairs
    .filter(rec => rec.sourceGroup === groupId)
    .sort((a, b) => b.count - a.count)
    .slice(0, 4);
  const incoming = pairs
    .filter(rec => rec.targetGroup === groupId)
    .sort((a, b) => b.count - a.count)
    .slice(0, 4);
  return { outgoing, incoming };
}

function _detailSummaryHtml(groupId, meta, stats, routes) {
  const T = PX.T;
  const desc = PX.escapeXml(meta.desc || meta.description || '');
  const pills = [
    `${stats.fileCount || 0} files`,
    `\u2190 ${stats.externalIn || 0}`,
    `${stats.externalOut || 0} \u2192`,
  ].map(text =>
    `<span style="display:inline-flex;align-items:center;padding:3px 8px;background:${T.bg};border:1px solid ${T.border};border-radius:999px;font-family:${T.mono};font-size:10px;color:${T.inkMuted}">${PX.escapeXml(text)}</span>`
  ).join('');
  const routeList = (title, items, tone) => {
    const color = tone === 'out' ? T.accent2 : T.good;
    const body = items.length
      ? items.map(rec => `<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid ${T.borderAlt}">
          <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${PX.escapeXml(rec[tone === 'out' ? 'targetGroup' : 'sourceGroup'])}</span>
          <span style="color:${color};font-family:${T.mono};font-weight:600">${rec.count}\u00d7</span>
        </div>`).join('')
      : `<div style="color:${T.inkFaint};font-size:11px">No cross-group traffic</div>`;
    return `<div style="min-width:0">
      <div style="margin-bottom:6px;font-family:${T.mono};font-size:10px;letter-spacing:0.8px;text-transform:uppercase;color:${T.inkFaint}">${title}</div>
      ${body}
    </div>`;
  };
  const bridgeFiles = (stats.bridgeFiles || []).slice(0, 4).map(file =>
    `<span style="display:inline-flex;align-items:center;gap:5px;padding:2px 8px;background:${T.pill};border:1px solid ${T.pillBorder};border-radius:999px;font-size:10px;color:${T.accent2}">
      ${PX.escapeXml(file.label)}
      <span style="color:${T.inkFaint};font-family:${T.mono}">\u2194${file.count}</span>
    </span>`
  ).join('');
  return `<div xmlns="http://www.w3.org/1999/xhtml" style="height:100%;display:flex;flex-direction:column;gap:12px;font-family:${T.ui};color:${T.ink2}">
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px">
      <div style="min-width:0;flex:1">
        <div style="font-family:${T.mono};font-size:10px;letter-spacing:1px;text-transform:uppercase;color:${T.inkFaint};margin-bottom:5px">Selected group</div>
        <div style="font-size:13px;line-height:1.55">${desc || 'No group description available yet.'}</div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end;flex-shrink:0">${pills}</div>
    </div>
    <div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;font-size:11px;line-height:1.45">
      ${routeList('Outgoing', routes.outgoing, 'out')}
      ${routeList('Incoming', routes.incoming, 'in')}
    </div>
    ${bridgeFiles ? `<div style="display:flex;flex-wrap:wrap;gap:6px">${bridgeFiles}</div>` : ''}
  </div>`;
}

function _emptyDetailHtml() {
  const T = PX.T;
  return `<div xmlns="http://www.w3.org/1999/xhtml" style="height:100%;display:flex;align-items:center;justify-content:center;text-align:center;font-family:${T.ui};color:${T.inkMuted};padding:24px">
    <div>
      <div style="font-family:${T.mono};font-size:10px;letter-spacing:1px;text-transform:uppercase;color:${T.inkFaint};margin-bottom:10px">Detail</div>
      <div style="font-size:18px;font-weight:700;color:${T.ink};margin-bottom:8px">Select a group</div>
      <div style="font-size:13px;line-height:1.55;max-width:360px">The left side stays compact so you can keep the whole structure visible. Click any group to open its files here.</div>
    </div>
  </div>`;
}

PX.views.nested = async function renderNested(graph, opts = {}) {
  const {
    showBullets = true,
    selected = null,
    filter = '',
    index = null,
    focusedGroup = null,
  } = opts;
  const idx = index || PX.buildGraphIndex(graph);
  const groupsMeta = (graph.metaGroups && graph.metaGroups) || {};
  const focusGroupId = focusedGroup || (selected && idx.byId[selected] ? ((idx.byId[selected].group || 'Ungrouped')) : null);
  // When a group is focused, shrink the overview into a rail so the detail
  // panel keeps real estate. Aspect ratio 0.3 (rail) vs 0.8 (overview-only)
  // matches the visual role in each mode.
  const isRail = !!focusGroupId;
  const overviewIr = PX.buildIr(graph, 'nested', {
    showBullets,
    index: idx,
    compact: isRail,
  });
  overviewIr.layoutOptions = { 'elk.aspectRatio': isRail ? '0.25' : '0.9' };

  const detailIr = focusGroupId
    ? PX.buildGroupDetailIr(graph, focusGroupId, { showBullets, index: idx })
    : null;
  if (detailIr) {
    // Why not 'layered' here: files inside a single group are often
    // independent (e.g. Tests). Layered would dump all 10 tests into one
    // layer → one row ~2500 px wide, which then forces the whole SVG to
    // downscale until text becomes unreadable. When files ARE linked
    // (Code Analysis, Graph Data Model), we still want them packed in 2D
    // rather than stretched along the longest chain.
    //
    // 'rectpacking' if no edges (pure grid). 'force' otherwise (2D + keeps
    // edges as straight lines, which is enough for intra-group context).
    const hasEdges = (detailIr.edges || []).length > 0;
    detailIr.layoutOptions = hasEdges
      ? {
          'elk.algorithm': 'force',
          'elk.aspectRatio': '0.9',
          'elk.spacing.nodeNode': '56',
          'elk.randomSeed': '42',
        }
      : {
          'elk.algorithm': 'rectpacking',
          'elk.aspectRatio': '0.9',
          'elk.spacing.nodeNode': '24',
        };
  }
  const [overviewLaid, detailLaid] = await Promise.all([
    PX.runLayout(overviewIr),
    detailIr ? PX.runLayout(detailIr) : Promise.resolve(null),
  ]);

  const overviewNodesByIdRaw = PX._collectNodes(overviewLaid);
  const overviewEdgeMetaById = Object.fromEntries((overviewIr.edges || []).map(e => [e.id, e]));
  const overviewPolylines = PX.extractEdgePolylines(overviewLaid).map(e => ({
    ...e,
    ...(overviewEdgeMetaById[e.id] || {}),
  }));
  // Aggregate edges carry a 3-line colored label (same shape as group-map).
  // The dims are deterministic from source/target names + count, so ELK
  // already reserved space in the layered layout (see ir.js → aggregateEdges
  // with `labels: [{width, height}]`).
  const overviewLabelled = PX.placeEdgeLabels(PX.detectBus(overviewPolylines, overviewNodesByIdRaw), { centerOnPath: true }).map(e => {
    if (!(e.count > 0 && e.sourceGroup && e.targetGroup)) {
      return { ...e, __labelW: 0, __labelH: 0 };
    }
    const dims = PX._labelDims(e.sourceGroup, e.targetGroup, e.count);
    return { ...e, __labelW: dims.width, __labelH: dims.height };
  });
  const overviewSegments = [];
  for (const edge of overviewLabelled) {
    const pts = edge.bus ? PX.buildBusTrunkPath(edge, overviewNodesByIdRaw) : (edge.points || []);
    for (let i = 0; i < pts.length - 1; i++) {
      overviewSegments.push({
        x1: pts[i].x, y1: pts[i].y,
        x2: pts[i + 1].x, y2: pts[i + 1].y,
        edgeId: edge.id,
      });
    }
  }
  const overviewCardRects = (overviewLaid.children || []).map(box => ({
    x1: box.x || 0, y1: box.y || 0,
    x2: (box.x || 0) + (box.width || 0),
    y2: (box.y || 0) + (box.height || 0),
  }));
  const overviewEdgesRaw = PX.avoidLabelCollisions(overviewLabelled, {
    labelW: (e) => e.__labelW || 40,
    labelH: (e) => e.__labelH || 22,
    gap: 12,
    segments: overviewSegments,
    walkPath: true,
    cardRects: overviewCardRects,
  }).map(e => ({
    ...e,
    sourceGroup: PX.splitPortId(e.source).nodeId,
    targetGroup: PX.splitPortId(e.target).nodeId,
  }));

  const detailNodesByIdRaw = detailLaid ? PX._collectNodes(detailLaid) : {};
  const detailEdgeMetaById = Object.fromEntries(((detailIr && detailIr.edges) || []).map(e => [e.id, e]));
  const detailEdgesRaw = detailLaid
    ? PX.placeEdgeLabels(PX.detectBus(
      PX.extractEdgePolylines(detailLaid).map(e => ({
        ...e,
        ...(detailEdgeMetaById[e.id] || {}),
      })),
      detailNodesByIdRaw,
    )).map(e => ({
      ...e,
      sourceNode: PX.splitPortId(e.source).nodeId,
      targetNode: PX.splitPortId(e.target).nodeId,
    }))
    : [];

  const inDeg = {}, outDeg = {};
  for (const n of graph.nodes || []) { inDeg[n.id] = 0; outDeg[n.id] = 0; }
  for (const e of graph.edges || []) {
    if (inDeg[e.target] != null) inDeg[e.target]++;
    if (outDeg[e.source] != null) outDeg[e.source]++;
  }
  const maxDeg = Math.max(1, ...Object.values(inDeg), ...Object.values(outDeg));
  const SPOF_MIN = 8;

  const topBoxes = (overviewLaid.children || []).slice().sort((a, b) => (a.y || 0) - (b.y || 0));
  const layerOf = {};
  const rowTol = 40;
  let layer = topBoxes.length;
  let prevY = -1e9;
  for (const b of topBoxes) {
    if ((b.y || 0) - prevY > rowTol) layer -= 1;
    layerOf[b.id] = Math.max(0, layer);
    prevY = b.y || 0;
  }

  const relatedGroups = new Set(focusGroupId ? [focusGroupId] : []);
  if (focusGroupId) {
    for (const rec of (idx.groupPairStats || [])) {
      if (rec.sourceGroup === focusGroupId) relatedGroups.add(rec.targetGroup);
      if (rec.targetGroup === focusGroupId) relatedGroups.add(rec.sourceGroup);
    }
  }
  if (selected) {
    for (const e of graph.edges || []) {
      if (e.source !== selected && e.target !== selected) continue;
      relatedGroups.add((idx.byId[e.source] || {}).group || 'Ungrouped');
      relatedGroups.add((idx.byId[e.target] || {}).group || 'Ungrouped');
    }
  }

  const fileState = (id) => idx ? idx.fileState(selected, id, filter) : 'normal';
  const overviewEdgeState = (e) => {
    if (!focusGroupId) return 'normal';
    if (e.sourceGroup === focusGroupId) return 'depends';
    if (e.targetGroup === focusGroupId) return 'imports';
    return 'faded';
  };
  const detailEdgeState = (e) => {
    if (!selected) return 'normal';
    if (e.sourceNode === selected) return 'depends';
    if (e.targetNode === selected) return 'imports';
    return 'faded';
  };

  const LEFT_PAD = 24;
  const TOP_PAD = 28;
  const SECTION_GAP = 28;
  const overviewX = LEFT_PAD;
  const overviewY = TOP_PAD + 18;
  const overviewW = Math.round((overviewLaid.width || 640) + 40);
  const overviewH = Math.round((overviewLaid.height || 520) + 40);
  const detailSummaryH = focusGroupId ? 150 : 200;
  const detailBoxX = overviewX + overviewW + SECTION_GAP + 18;
  const detailPanelX = detailBoxX - 18;
  const detailPanelY = TOP_PAD;
  const detailBoxY = detailPanelY + detailSummaryH;
  const detailBoxInnerPadX = 22;
  const detailBoxInnerPadY = 110;
  const detailBoxW = focusGroupId
    ? Math.max(640, Math.round((detailLaid.width || 540) + detailBoxInnerPadX * 2 + 12))
    : 680;
  const detailBoxH = focusGroupId
    ? Math.max(320, Math.round((detailLaid.height || 0) + detailBoxInnerPadY + 28))
    : 0;
  const detailPanelW = detailBoxW + 36;
  const detailPanelH = focusGroupId
    ? detailSummaryH + detailBoxH + 18
    : detailSummaryH + 40;
  const W = Math.round(detailPanelX + detailPanelW + LEFT_PAD);
  const H = Math.round(Math.max(overviewY + overviewH + TOP_PAD, detailPanelY + detailPanelH + TOP_PAD));
  const overviewDx = overviewX;
  const overviewDy = overviewY;
  const detailDx = detailBoxX + detailBoxInnerPadX;
  const detailDy = detailBoxY + detailBoxInnerPadY;
  const overviewNodesById = _translateNodes(overviewNodesByIdRaw, overviewDx, overviewDy);
  const detailNodesById = _translateNodes(detailNodesByIdRaw, detailDx, detailDy);
  const overviewEdges = overviewEdgesRaw.map(e => _translateEdge(e, overviewDx, overviewDy));
  const detailEdges = detailEdgesRaw.map(e => _translateEdge(e, detailDx, detailDy));
  const routes = focusGroupId ? _routePairs(idx, focusGroupId) : { outgoing: [], incoming: [] };

  // Fill the canvas width (no max-width cap) and apply a user-controlled
  // zoom via the `--px-zoom` CSS variable. The parent #px-canvas has
  // `overflow:auto`, so zooming > 1 triggers scrollbars instead of pushing
  // content off-screen.
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="display:block;margin:0 auto;width:calc(100% * var(--px-zoom, 1));height:auto" data-view="nested" data-natural-w="${W}" data-natural-h="${H}">`;
  svg += PX.components.markers();

  svg += `<text x="${overviewX}" y="${TOP_PAD - 2}" font-family="${PX.T.mono}" font-size="10" letter-spacing="1.2" fill="${PX.T.inkFaint}">GROUPS</text>`;
  svg += `<text x="${detailPanelX}" y="${TOP_PAD - 2}" font-family="${PX.T.mono}" font-size="10" letter-spacing="1.2" fill="${PX.T.inkFaint}">DETAIL</text>`;
  svg += `<line x1="${overviewX + overviewW + SECTION_GAP / 2}" y1="${TOP_PAD}" x2="${overviewX + overviewW + SECTION_GAP / 2}" y2="${H - TOP_PAD}" stroke="${PX.T.borderAlt}" stroke-width="1"/>`;

  // Build the rich 3-line label object shape (same as group-map) for each
  // aggregate edge; paths first, cards next, labels last for clean z-order.
  const mkOverviewLabel = (e) => (e.count > 0 && e.sourceGroup && e.targetGroup ? {
    sourceName: e.sourceGroup,
    sourceColor: PX.groupColor(e.sourceGroup, groupsMeta[e.sourceGroup] || {}),
    targetName: e.targetGroup,
    targetColor: PX.groupColor(e.targetGroup, groupsMeta[e.targetGroup] || {}),
    count: e.count,
  } : null);

  for (const e of overviewEdges) {
    svg += PX.components.edge(e, {
      nodesById: overviewNodesById,
      state: overviewEdgeState(e),
      thick: true,
      pathOnly: true,
    });
  }

  for (const box of (overviewLaid.children || [])) {
    const meta = groupsMeta[box.id] || {};
    const stats = ((idx.groupStats || {})[box.id]) || {};
    const color = PX.groupColor(box.id, meta);
    const faded = !!focusGroupId && box.id !== focusGroupId && !relatedGroups.has(box.id);
    svg += PX.components.groupContainer({
      x: (box.x || 0) + overviewDx,
      y: (box.y || 0) + overviewDy,
      w: box.width,
      h: box.height,
      name: box.id,
      color,
      desc: meta.desc || meta.description || '',
      fileCount: stats.fileCount || 0,
      layer: layerOf[box.id] || 0,
      bridgeIn: stats.externalIn || 0,
      bridgeOut: stats.externalOut || 0,
      strongestIn: stats.strongestIn || null,
      strongestOut: stats.strongestOut || null,
      gatewayFiles: (stats.bridgeFiles || []).slice(0, 3),
      expanded: false,
      selected: box.id === focusGroupId,
      faded: !!faded,
    });
  }

  for (const e of overviewEdges) {
    const label = mkOverviewLabel(e);
    if (!label) continue;
    svg += PX.components.edge(e, {
      nodesById: overviewNodesById,
      state: overviewEdgeState(e),
      label,
      thick: true,
      labelOnly: true,
    });
  }

  svg += `<rect x="${detailPanelX}" y="${detailPanelY}" width="${detailPanelW}" height="${detailPanelH}" fill="${PX.T.panel}" stroke="${PX.T.border}" stroke-width="1" rx="12"/>`;
  if (!focusGroupId) {
    svg += `<foreignObject x="${detailPanelX + 14}" y="${detailPanelY + 14}" width="${detailPanelW - 28}" height="${detailPanelH - 28}">${_emptyDetailHtml()}</foreignObject>`;
    svg += `</svg>`;
    return { svg, laid: overviewLaid, nodesById: overviewNodesById, edges: overviewEdges, W, H };
  }

  const focusMeta = groupsMeta[focusGroupId] || {};
  const focusStats = ((idx.groupStats || {})[focusGroupId]) || {};
  const focusColor = PX.groupColor(focusGroupId, focusMeta);
  const detailBoxWidth = detailPanelW - 36;
  svg += `<rect x="${detailPanelX}" y="${detailPanelY}" width="${detailPanelW}" height="4" fill="${focusColor}" rx="12"/>`;
  svg += `<foreignObject x="${detailPanelX + 14}" y="${detailPanelY + 14}" width="${detailPanelW - 28}" height="${detailSummaryH - 24}">${_detailSummaryHtml(focusGroupId, focusMeta, focusStats, routes)}</foreignObject>`;
  svg += PX.components.groupContainer({
    x: detailBoxX,
    y: detailBoxY,
    w: detailBoxWidth,
    h: detailBoxH,
    name: focusGroupId,
    color: focusColor,
    desc: focusMeta.desc || focusMeta.description || '',
    fileCount: focusStats.fileCount || 0,
    layer: 0,
    bridgeIn: focusStats.externalIn || 0,
    bridgeOut: focusStats.externalOut || 0,
    strongestIn: focusStats.strongestIn || null,
    strongestOut: focusStats.strongestOut || null,
    gatewayFiles: (focusStats.bridgeFiles || []).slice(0, 4),
    expanded: true,
    selected: true,
    faded: false,
  });

  for (const e of detailEdges) {
    svg += PX.components.edge(e, {
      nodesById: detailNodesById,
      state: detailEdgeState(e),
      label: null,
      thick: false,
    });
  }

  const byId = Object.fromEntries((graph.nodes || []).map(n => [n.id, n]));
  for (const c of (detailLaid.children || [])) {
    const node = byId[c.id];
    if (!node) continue;
    const absX = (c.x || 0) + detailDx;
    const absY = (c.y || 0) + detailDy;
    svg += PX.components.cardFile(node, { x: absX, y: absY, w: c.width, h: c.height }, {
      showBullets,
      groupColor: focusColor,
      maxDeg,
      inDeg: inDeg[node.id] || 0,
      outDeg: outDeg[node.id] || 0,
      isHub: (inDeg[node.id] || 0) >= SPOF_MIN,
      bridgeIn: (idx.fileBridgeIn || {})[node.id] || 0,
      bridgeOut: (idx.fileBridgeOut || {})[node.id] || 0,
      state: fileState(node.id),
    });
  }

  svg += `</svg>`;
  return {
    svg,
    laid: overviewLaid,
    nodesById: { ...overviewNodesById, ...detailNodesById },
    edges: [...overviewEdges, ...detailEdges],
    W,
    H,
  };
};
