// views/nested.js — Nested renderer.
//
// Two paths:
//   - Overview (no group focused): the classic multi-group nested overview
//     with aggregate labelled edges. Unchanged from before.
//   - Focused group: renders a structured "group story" — breadcrumb,
//     summary, primary entry paths, dependency-position bands (Entry /
//     Core / Leaf / Test), intra-group edges with top-N verb labels, and
//     a "stress points" strip when hubs/cycles/dominant-bridges exist.
//     Cards are hand-positioned in bands (deterministic across renders);
//     ELK is used only to route edges between fixed positions.

window.PX = window.PX || {};
PX.views = PX.views || {};

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

PX.views.nested = async function renderNested(graph, opts = {}) {
  const {
    showBullets = true,
    selected = null,
    filter = '',
    index = null,
    focusedGroup = null,
    hoveredGroup = null,
  } = opts;
  const idx = index || PX.buildGraphIndex(graph);
  const focusGroupId = focusedGroup || (selected && idx.byId[selected]
    ? ((idx.byId[selected].group || 'Ungrouped'))
    : null);

  if (!focusGroupId) {
    return PX.views._nestedOverview(graph, idx, { showBullets, selected, filter, hoveredGroup });
  }
  return PX.views._nestedFocused(graph, idx, focusGroupId, {
    showBullets, selected, filter, hoveredGroup,
  });
};

// ── Overview (no group focused): full-canvas nested landscape ──────────
PX.views._nestedOverview = async function renderOverview(graph, idx, opts) {
  const { showBullets, selected, filter, hoveredGroup = null } = opts;
  const groupsMeta = (graph.metaGroups && graph.metaGroups) || {};
  const overviewIr = PX.buildIr(graph, 'nested', {
    showBullets,
    index: idx,
    compact: false,
  });
  overviewIr.layoutOptions = { 'elk.aspectRatio': '0.9' };

  const laid = await PX.runLayout(overviewIr);
  const nodesByIdRaw = PX._collectNodes(laid);
  const edgeMetaById = Object.fromEntries((overviewIr.edges || []).map(e => [e.id, e]));
  const polylines = PX.extractEdgePolylines(laid).map(e => ({
    ...e,
    ...(edgeMetaById[e.id] || {}),
  }));
  const labelled = PX.placeEdgeLabels(polylines, { centerOnPath: true }).map(e => {
    if (!(e.count > 0 && e.sourceGroup && e.targetGroup)) {
      return { ...e, __labelW: 0, __labelH: 0 };
    }
    const dims = PX._labelDims(e.sourceGroup, e.targetGroup, e.count);
    return { ...e, __labelW: dims.width, __labelH: dims.height };
  });
  const segments = [];
  for (const edge of labelled) {
    const pts = edge.points || [];
    for (let i = 0; i < pts.length - 1; i++) {
      segments.push({
        x1: pts[i].x, y1: pts[i].y,
        x2: pts[i + 1].x, y2: pts[i + 1].y,
        edgeId: edge.id,
      });
    }
  }
  const cardRects = (laid.children || []).map(box => ({
    x1: box.x || 0, y1: box.y || 0,
    x2: (box.x || 0) + (box.width || 0),
    y2: (box.y || 0) + (box.height || 0),
  }));
  const edges = PX.avoidLabelCollisions(labelled, {
    labelW: (e) => e.__labelW || 180,
    labelH: (e) => e.__labelH || 50,
    gap: 18,
    segments,
    walkPath: true,
    cardRects,
  }).map(e => ({
    ...e,
    sourceGroup: PX.splitPortId(e.source).nodeId,
    targetGroup: PX.splitPortId(e.target).nodeId,
  }));

  const topBoxes = (laid.children || []).slice().sort((a, b) => (a.y || 0) - (b.y || 0));
  const layerOf = {};
  const rowTol = 40;
  let layer = topBoxes.length;
  let prevY = -1e9;
  for (const b of topBoxes) {
    if ((b.y || 0) - prevY > rowTol) layer -= 1;
    layerOf[b.id] = Math.max(0, layer);
    prevY = b.y || 0;
  }

  const selectedGroup = hoveredGroup || (selected && idx ? (idx.byId[selected] || {}).group : null);
  const groupEdgeState = (e) => {
    if (!selectedGroup) return 'normal';
    if (e.sourceGroup === selectedGroup) return 'depends';
    if (e.targetGroup === selectedGroup) return 'imports';
    return 'faded';
  };
  const groupBoxState = (name) => {
    if (!selectedGroup) return 'normal';
    if (name === selectedGroup) return 'selected';
    const involved = edges.some(e => (e.sourceGroup === selectedGroup && e.targetGroup === name) || (e.targetGroup === selectedGroup && e.sourceGroup === name));
    return involved ? 'normal' : 'faded';
  };

  const LEFT_PAD = 24;
  const TOP_PAD = 28;
  let minX = 0, minY = 0;
  let maxX = laid.width || 640;
  let maxY = laid.height || 520;
  for (const box of (laid.children || [])) {
    const bx = box.x || 0, by = box.y || 0;
    const bw = box.width || 0, bh = box.height || 0;
    if (bx < minX) minX = bx;
    if (by < minY) minY = by;
    if (bx + bw > maxX) maxX = bx + bw;
    if (by + bh > maxY) maxY = by + bh;
  }
  for (const e of edges) {
    for (const p of e.points || []) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    if (e.labelX != null && e.labelY != null) {
      const lw = e.__labelW || 0, lh = e.__labelH || 0;
      if (e.labelX - lw / 2 < minX) minX = e.labelX - lw / 2;
      if (e.labelY - lh / 2 < minY) minY = e.labelY - lh / 2;
      if (e.labelX + lw / 2 > maxX) maxX = e.labelX + lw / 2;
      if (e.labelY + lh / 2 > maxY) maxY = e.labelY + lh / 2;
    }
  }
  const PAD = 20;
  const dx = LEFT_PAD + PAD - minX;
  const dy = TOP_PAD + PAD - minY;
  const W = Math.ceil(maxX - minX + 2 * PAD + 2 * LEFT_PAD);
  const H = Math.ceil(maxY - minY + 2 * PAD + 2 * TOP_PAD);
  const nodesById = {};
  for (const [id, node] of Object.entries(nodesByIdRaw)) {
    nodesById[id] = { ...node, x: (node.x || 0) + dx, y: (node.y || 0) + dy };
  }
  const translated = edges.map(e => _translateEdge(e, dx, dy));

  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="display:block;margin:0 auto;width:calc(100% * var(--px-zoom, 1));height:auto" data-view="nested" data-natural-w="${W}" data-natural-h="${H}">`;
  svg += PX.components.markers();

  const mkLabel = (e) => (e.count > 0 && e.sourceGroup && e.targetGroup ? {
    sourceName: e.sourceGroup,
    sourceColor: PX.groupColor(e.sourceGroup, groupsMeta[e.sourceGroup] || {}),
    targetName: e.targetGroup,
    targetColor: PX.groupColor(e.targetGroup, groupsMeta[e.targetGroup] || {}),
    count: e.count,
  } : null);

  for (const e of translated) {
    const st = groupEdgeState(e);
    svg += PX.components.edge(e, {
      nodesById,
      state: st,
      thick: true,
      pathOnly: true,
    });
  }
  for (const box of (laid.children || [])) {
    const meta = groupsMeta[box.id] || {};
    const stats = ((idx.groupStats || {})[box.id]) || {};
    const color = PX.groupColor(box.id, meta);
    const st = groupBoxState(box.id);
    svg += PX.components.groupContainer({
      x: (box.x || 0) + dx,
      y: (box.y || 0) + dy,
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
      selected: st === 'selected',
      faded: st === 'faded',
    });
  }
  for (const e of translated) {
    const st = groupEdgeState(e);
    const label = mkLabel(e);
    if (!label) continue;
    svg += PX.components.edge(e, {
      nodesById,
      state: st,
      label,
      thick: true,
      labelOnly: true,
    });
  }
  svg += `</svg>`;
  return { svg, laid, nodesById, edges: translated, W, H };
};

// ── Focused group: ranked architectural narrative ──────────────────────
PX.views._nestedFocused = async function renderFocused(graph, idx, groupId, opts) {
  const { showBullets, selected, filter, hoveredGroup = null } = opts;
  const story = PX.buildGroupStory(graph, groupId, idx);
  const CANVAS = 1640;
  const LEFT = 32;
  const TOP = 20;
  const SUMMARY_H = 84;
  const GAP = 14;
  const ANCHOR_W = 180;
  const ANCHOR_H = 48;
  const ANCHOR_GAP_Y = 16;
  const ANCHOR_MARGIN = 36;

  // Boundary anchors follow the data-flow convention used in architecture
  // diagrams: UPSTREAM (what this group depends on) sits on the LEFT,
  // DOWNSTREAM (who depends on this group) sits on the RIGHT. Arrows all
  // flow left → right so the visual reads as a pipeline, independent of
  // the import-graph edge direction.
  //   depAnchors = story.externalOut (we import from them) → LEFT
  //   useAnchors = story.externalIn  (they import from us) → RIGHT
  const depAnchors = (story.externalOut || []);  // upstream dependencies
  const useAnchors = (story.externalIn || []);   // downstream consumers
  const leftReserved = depAnchors.length > 0 ? ANCHOR_W + ANCHOR_MARGIN : 0;
  const rightReserved = useAnchors.length > 0 ? ANCHOR_W + ANCHOR_MARGIN : 0;
  const mainLeft = LEFT + leftReserved;
  const mainWidth = CANVAS - 2 * LEFT - leftReserved - rightReserved;

  // Top bar (#px-top) already shows the focused group name, description, and a
  // "back to overview" button — no breadcrumb needed inside the SVG. No
  // PRIMARY ENTRY PATHS strip either; it duplicated the ENTRY band.
  const bandsStartY = TOP + SUMMARY_H + GAP;

  // Compose the band grid layout (deterministic, hand-positioned).
  const layout = PX.buildGroupStoryLayoutIr(story, {
    showBullets,
    canvasWidth: mainWidth,
    topPad: 0,           // we apply our own top offset below
    leftPad: 0,
    bandGapY: 72,
    bandGapX: 72,
    cardGapY: 22,
  });

  // Run ELK in routing-only mode on the hand-positioned tree.
  let laid = null;
  let edgesRouted = [];
  if (layout.ir.edges.length > 0) {
    try {
      laid = await PX.runLayout(layout.ir);
      const polylines = PX.extractEdgePolylines(laid);
      const edgeMetaById = Object.fromEntries(layout.ir.edges.map(e => [e.id, e]));
      edgesRouted = polylines.map(p => ({
        ...p,
        ...(edgeMetaById[p.id] || {}),
      }));
    } catch (err) {
      console.warn('[prefxplain] edge routing failed, drawing direct lines:', err);
      edgesRouted = [];
    }
  }

  // If ELK couldn't route (or declined), fall back to direct lines between
  // port anchors so the panel still shows flow.
  if (edgesRouted.length === 0 && layout.ir.edges.length > 0) {
    edgesRouted = layout.ir.edges.map(e => {
      const srcNode = layout.ir.children.find(c => c.id === e.sourceNode);
      const tgtNode = layout.ir.children.find(c => c.id === e.targetNode);
      if (!srcNode || !tgtNode) return null;
      const sx = srcNode.x + srcNode.width / 2;
      const sy = srcNode.y + srcNode.height;
      const tx = tgtNode.x + tgtNode.width / 2;
      const ty = tgtNode.y;
      return {
        ...e,
        id: e.id,
        source: `${e.sourceNode}.out`,
        target: `${e.targetNode}.in`,
        points: [{ x: sx, y: sy }, { x: sx, y: (sy + ty) / 2 }, { x: tx, y: (sy + ty) / 2 }, { x: tx, y: ty }],
      };
    }).filter(Boolean);
  }

  // Translate everything by (mainLeft, bandsStartY) so the boundary anchor
  // columns on the left stay clear of the main bands.
  const nodesById = {};
  for (const c of layout.ir.children) {
    nodesById[c.id] = {
      id: c.id,
      x: c.x + mainLeft,
      y: c.y + bandsStartY,
      w: c.width,
      h: c.height,
    };
  }
  const bandRects = layout.bandRects.map(b => ({
    ...b,
    x: b.x + mainLeft,
    y: b.y + bandsStartY,
  }));
  const edgesTranslated = edgesRouted.map(e => _translateEdge(e, mainLeft, bandsStartY));

  // Edge label placement + collision avoidance — reuse the group-map pipeline.
  const labelled = PX.placeEdgeLabels(edgesTranslated, { centerOnPath: false });
  const segments = [];
  for (const edge of labelled) {
    const pts = edge.points || [];
    for (let i = 0; i < pts.length - 1; i++) {
      segments.push({
        x1: pts[i].x, y1: pts[i].y,
        x2: pts[i + 1].x, y2: pts[i + 1].y,
        edgeId: edge.id,
      });
    }
  }
  const cardRects = Object.values(nodesById).map(n => ({
    x1: n.x, y1: n.y, x2: n.x + n.w, y2: n.y + n.h,
  }));
  const finalEdges = PX.avoidLabelCollisions(labelled, {
    labelW: (e) => e.labelled ? (String(e.count).length + 8) * 6.4 + 16 : 0,
    labelH: (e) => e.labelled ? 20 : 0,
    gap: 14,
    segments,
    walkPath: true,
    cardRects,
  });

  // ── Compose SVG ───────────────────────────────────────────────────
  // Compute final canvas size. Bands section height comes from the layout;
  // stress strip adds its own measured height. Anchor columns may be taller
  // than the bands for groups with many external neighbors — make canvas
  // at least as tall as the tallest anchor column.
  const bandsH = layout.canvasH;
  const maxAnchorCount = Math.max(depAnchors.length, useAnchors.length);
  const anchorsStackH = maxAnchorCount > 0
    ? maxAnchorCount * ANCHOR_H + Math.max(0, maxAnchorCount - 1) * ANCHOR_GAP_Y
    : 0;
  const contentH = Math.max(bandsH, anchorsStackH);
  const stressPreview = PX.components.stressStrip({
    x: LEFT, y: 0, w: CANVAS - 2 * LEFT, stress: story.stress,
  });
  const STRESS_H = stressPreview.h;
  const totalH = bandsStartY + contentH + (STRESS_H ? GAP + STRESS_H : 0) + TOP;
  const W = CANVAS;
  const H = totalH;

  // Anchor positions (centered vertically within the content area).
  const contentCenterY = bandsStartY + contentH / 2;
  const placeAnchors = (list, startX) => {
    const positions = {};
    if (list.length === 0) return positions;
    const totalStackH = list.length * ANCHOR_H + Math.max(0, list.length - 1) * ANCHOR_GAP_Y;
    const yTop = Math.max(bandsStartY, contentCenterY - totalStackH / 2);
    for (let i = 0; i < list.length; i++) {
      positions[list[i].groupId] = {
        x: startX,
        y: yTop + i * (ANCHOR_H + ANCHOR_GAP_Y),
        w: ANCHOR_W,
        h: ANCHOR_H,
      };
    }
    return positions;
  };
  const depAnchorPos = placeAnchors(depAnchors, LEFT);
  const useAnchorPos = placeAnchors(useAnchors, CANVAS - LEFT - ANCHOR_W);

  // Boundary edges ALWAYS flow left → right (data-flow convention):
  //   depAnchor  →  file   (upstream dependency feeds us)
  //   file       →  useAnchor (we feed our downstream consumer)
  // Per-group corridors sit just inside each anchor column so the
  // horizontal run never crosses a file card.
  const DEP_CORRIDOR_BASE = mainLeft - 12;   // just right of LEFT anchors
  const USE_CORRIDOR_BASE = mainLeft + mainWidth + 12; // just left of RIGHT anchors
  const depCorridorX = {};
  depAnchors.forEach((a, i) => { depCorridorX[a.groupId] = DEP_CORRIDOR_BASE - i * 6; });
  const useCorridorX = {};
  useAnchors.forEach((a, i) => { useCorridorX[a.groupId] = USE_CORRIDOR_BASE + i * 6; });
  const boundaryEdges = [];
  // Dependency edges: arrow tail on the anchor (upstream), arrowhead on our
  // file card (downstream consumer within our group).
  for (const e of story.externalOutEdges || []) {
    const tgt = nodesById[e.fileId];
    const anchor = depAnchorPos[e.groupId];
    if (!tgt || !anchor) continue;
    const sx = anchor.x + anchor.w;         // anchor's right edge (left column)
    const sy = anchor.y + anchor.h / 2;
    const tx = tgt.x;                        // file's left edge (middle area)
    const ty = tgt.y + tgt.h / 2;
    const cx = depCorridorX[e.groupId];
    boundaryEdges.push({
      id: `bd-${e.fileId}-${e.groupId}`,
      kind: 'boundary-dep',
      fileId: e.fileId,
      groupId: e.groupId,
      count: e.count,
      color: depAnchors.find(a => a.groupId === e.groupId)?.color || PX.T.inkMuted,
      points: [
        { x: sx, y: sy },
        { x: cx, y: sy },
        { x: cx, y: ty },
        { x: tx, y: ty },
      ],
    });
  }
  // Consumer edges: arrow tail on our file, arrowhead on the downstream
  // anchor (rightward data flow toward whoever imports us).
  for (const e of story.externalInEdges || []) {
    const src = nodesById[e.fileId];
    const anchor = useAnchorPos[e.groupId];
    if (!src || !anchor) continue;
    const sx = src.x + src.w;                // file's right edge
    const sy = src.y + src.h / 2;
    const tx = anchor.x;                     // anchor's left edge (right column)
    const ty = anchor.y + anchor.h / 2;
    const cx = useCorridorX[e.groupId];
    boundaryEdges.push({
      id: `bu-${e.fileId}-${e.groupId}`,
      kind: 'boundary-use',
      fileId: e.fileId,
      groupId: e.groupId,
      count: e.count,
      color: useAnchors.find(a => a.groupId === e.groupId)?.color || PX.T.inkMuted,
      points: [
        { x: sx, y: sy },
        { x: cx, y: sy },
        { x: cx, y: ty },
        { x: tx, y: ty },
      ],
    });
  }

  // Selection-driven file states.
  const neighborsOf = (id) => {
    const n = new Set();
    for (const e of graph.edges || []) {
      if (e.source === id) n.add(e.target);
      if (e.target === id) n.add(e.source);
    }
    return n;
  };
  const selectedNeighbors = selected ? neighborsOf(selected) : null;
  const fileState = (id) => {
    if (filter) {
      const n = idx.byId[id];
      if (!n) return 'normal';
      const q = filter.toLowerCase();
      const matches = (n.label || '').toLowerCase().includes(q)
        || (n.description || '').toLowerCase().includes(q)
        || (n.short || '').toLowerCase().includes(q);
      if (!selected) return matches ? 'match' : 'dimmed';
    }
    if (hoveredGroup) {
      const isConnected = boundaryEdges.some(be => be.groupId === hoveredGroup && be.fileId === id);
      return isConnected ? 'normal' : 'dimmed';
    }
    if (!selected) return 'normal';
    if (id === selected) return 'selected';
    if (selectedNeighbors && selectedNeighbors.has(id)) {
      for (const e of graph.edges || []) {
        if (e.source === selected && e.target === id) return 'depends';
        if (e.target === selected && e.source === id) return 'imports';
      }
    }
    return 'dimmed';
  };
  const edgeState = (e) => {
    if (hoveredGroup) return 'faded';
    if (!selected) return 'normal';
    if (e.sourceNode === selected) return 'depends';
    if (e.targetNode === selected) return 'imports';
    return 'faded';
  };

  const boundaryEdgeState = (be) => {
    if (hoveredGroup === be.groupId) return be.kind === 'boundary-use' ? 'imports' : 'depends';
    if (!selected) return 'normal';
    if (be.fileId === selected) return be.kind === 'boundary-use' ? 'imports' : 'depends';
    return 'faded';
  };

  // Use a natural pixel width (scaled by zoom) so the focused view keeps its
  // air-per-card budget even when the parent canvas is narrower than CANVAS.
  // Parent #px-canvas has overflow:auto, so the SVG drives horizontal scroll.
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="display:block;margin:0 auto;width:calc(${W}px * var(--px-zoom, 1));height:auto;min-width:${W}px" data-view="nested" data-natural-w="${W}" data-natural-h="${H}" data-focused-group="${PX.escapeXml(groupId)}">`;
  svg += PX.components.markers();

  // Summary header. (No breadcrumb here — the top info bar owns the
  // "focused group" identity and the back-to-overview button.)
  svg += PX.components.detailSummary({
    x: LEFT,
    y: TOP,
    w: CANVAS - 2 * LEFT,
    story,
  });

  // Band & cluster labels. Band labels sit above a band's top edge. Cluster
  // headers sit INSIDE the test band, one per test-target column. When a
  // test band has clusters, the outer band label is suppressed (redundant).
  const hasClusters = bandRects.some(b => b.kind === 'cluster');
  for (const band of bandRects) {
    if (band.kind === 'cluster') {
      svg += PX.components.clusterHeader({
        x: band.x,
        y: band.y,
        w: band.w,
        name: band.name,
        count: band.count,
        color: band.targetColor,
        targetId: band.targetId,
      });
      continue;
    }
    if (band.key === 'test' && hasClusters) continue; // cluster headers own this band
    svg += PX.components.bandLabel({
      x: band.x,
      y: band.y,
      w: band.w,
      name: band.name,
      count: band.count,
    });
  }

  // Boundary edges: drawn BEFORE anchors and file cards so they pass under
  // the opaque rectangles cleanly. Each edge emits a thin dashed-looking
  // path plus an optional count chip when count > 1.
  for (const be of boundaryEdges) {
    const state = boundaryEdgeState(be);
    const stroke = state === 'faded' ? PX.T.borderAlt
      : state === 'depends' ? PX.stateColor('depends')
      : state === 'imports' ? PX.stateColor('imports')
      : PX.T.inkFaint;
    const opacity = state === 'faded' ? 0.18 : state === 'normal' ? 0.5 : 0.95;
    const d = PX.pathD(be.points, 6, 14);
    svg += `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="2" opacity="${opacity}" marker-end="url(#arr-${state === 'faded' ? 'faded' : 'normal'})" style="transition:all 200ms"/>`;
    if (be.count > 1) {
      const lx = (be.points[1].x + be.points[2].x) / 2;
      const ly = (be.points[1].y + be.points[2].y) / 2;
      const txt = `${be.count}\u00D7`;
      const lw = txt.length * 6 + 12;
      svg += `<g pointer-events="none" opacity="${state === 'faded' ? 0.3 : 1}">`
        + `<rect x="${lx - lw / 2}" y="${ly - 9}" width="${lw}" height="18" fill="${PX.T.bg}" stroke="${stroke}" stroke-width="1" stroke-opacity="0.7" rx="9"/>`
        + `<text x="${lx}" y="${ly + 4}" font-family="${PX.T.mono}" font-size="10" font-weight="600" fill="${PX.T.inkMuted}" text-anchor="middle">${txt}</text>`
        + `</g>`;
    }
  }

  // Ghost anchors for external groups. LEFT = upstream dependencies,
  // RIGHT = downstream consumers (data-flow convention).
  for (const a of depAnchors) {
    const p = depAnchorPos[a.groupId];
    if (!p) continue;
    svg += PX.components.ghostAnchor({
      x: p.x, y: p.y, w: p.w, h: p.h,
      groupId: a.groupId, count: a.count, color: a.color, direction: 'dep',
      selected: hoveredGroup === a.groupId,
      faded: hoveredGroup && hoveredGroup !== a.groupId,
    });
  }
  for (const a of useAnchors) {
    const p = useAnchorPos[a.groupId];
    if (!p) continue;
    svg += PX.components.ghostAnchor({
      x: p.x, y: p.y, w: p.w, h: p.h,
      groupId: a.groupId, count: a.count, color: a.color, direction: 'use',
      selected: hoveredGroup === a.groupId,
      faded: hoveredGroup && hoveredGroup !== a.groupId,
    });
  }

  // Edges: paths first, then labels (z-order).
  for (const e of finalEdges) {
    svg += PX.components.edge(e, {
      nodesById,
      state: edgeState(e),
      thick: false,
      pathOnly: true,
    });
  }
  for (const e of finalEdges) {
    if (!e.labelled) continue;
    svg += PX.components.edge(e, {
      nodesById,
      state: edgeState(e),
      label: `${e.count}\u00D7`,
      thick: false,
      labelOnly: true,
    });
  }

  // File cards (on top of edges/bands).
  const inDeg = {}, outDeg = {};
  for (const n of graph.nodes || []) { inDeg[n.id] = 0; outDeg[n.id] = 0; }
  for (const e of graph.edges || []) {
    if (inDeg[e.target]  != null) inDeg[e.target]  += 1;
    if (outDeg[e.source] != null) outDeg[e.source] += 1;
  }
  const maxDeg = Math.max(1, ...Object.values(inDeg), ...Object.values(outDeg));
  const focusColor = story.meta.color;
  for (const band of story.bands) {
    for (const f of band.files) {
      const c = nodesById[f.id];
      if (!c) continue;
      const node = idx.byId[f.id] || { id: f.id, label: f.label };
      svg += PX.components.cardFile(
        node,
        { x: c.x, y: c.y, w: c.w, h: c.h },
        {
          showBullets,
          groupColor: focusColor,
          maxDeg,
          inDeg: inDeg[f.id] || 0,
          outDeg: outDeg[f.id] || 0,
          isHub: f.isHub,
          bridgeIn: f.bridgeIn,
          bridgeOut: f.bridgeOut,
          state: fileState(f.id),
        },
      );
    }
  }

  // Stress-points strip (bottom).
  if (STRESS_H > 0) {
    const stress = PX.components.stressStrip({
      x: LEFT,
      y: bandsStartY + bandsH + GAP,
      w: CANVAS - 2 * LEFT,
      stress: story.stress,
    });
    svg += stress.svg;
  }

  svg += `</svg>`;

  console.log(`[prefxplain] group-story ${groupId}: ${story.entries.length} entries, ${story.bands.length} bands, ${story.edges.length} edges, stress=${story.stress.length}`);

  return {
    svg,
    laid,
    nodesById,
    edges: finalEdges,
    W, H,
    story,
  };
};
