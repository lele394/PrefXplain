// views/group-map.js — Group Map renderer.
// Shows only hero cards for each group + aggregate "Nx imports" arrows
// between them. The view runs its own ELK layout (viewMode='group-map')
// because the card sizes differ from Nested (320x180 hero cards).
//
// Labels participate in layout via the IR (ir.js → _aggregateGroupEdges
// declares them). ELK reserves space and routes edges aware of label
// footprints — no post-processing detour (which caused the "F1 circuit"
// zigzags) is needed. ELKjs doesn't position edge labels automatically,
// so we still compute label positions with placeEdgeLabels + avoidLabel
// Collisions AFTER routing. The key win: no polyline rewriting.

window.PX = window.PX || {};
PX.views = PX.views || {};

PX.views.groupMap = async function renderGroupMap(graph, opts = {}) {
  const { selected = null, index = null, focusedGroup = null } = opts;
  const groupsMeta = (graph.metaGroups && graph.metaGroups) || {};
  const ir = PX.buildIr(graph, 'group-map');
  ir.layoutOptions = { 'elk.aspectRatio': '1.0' };
  const laid = await PX.runLayout(ir);
  const nodesById = PX._collectNodes(laid);
  const polylines = PX.extractEdgePolylines(laid);
  const irEdgesById = Object.fromEntries((ir.edges || []).map(e => [e.id, e]));

  const withLabelDims = polylines.map(p => {
    const irEdge = irEdgesById[p.id] || {};
    const lbl = (irEdge.labels || [])[0] || {};
    return {
      ...p,
      count: irEdge.count || 1,
      sourceGroup: PX.splitPortId(p.source).nodeId,
      targetGroup: PX.splitPortId(p.target).nodeId,
      __labelW: lbl.width || 180,
      __labelH: lbl.height || 50,
    };
  });

  const placed = PX.placeEdgeLabels(withLabelDims, { centerOnPath: true });

  const segments = [];
  for (const edge of placed) {
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
    x1: box.x, y1: box.y,
    x2: box.x + box.width, y2: box.y + box.height,
  }));
  const edges = PX.avoidLabelCollisions(placed, {
    labelW: (e) => e.__labelW,
    labelH: (e) => e.__labelH,
    gap: 18,
    segments,
    walkPath: true,
    cardRects,
  });

  // Detour post-processing removed: unique per-edge ports (ir.js →
  // _aggregateGroupEdges) give every edge its own corridor, so edges no
  // longer share trunks with foreign labels. Any remaining label overlaps
  // are masked visually by the opaque label rect rendered on top of paths.
  // Bringing back detour at this layer caused "tentacle" jogs where ELK's
  // clean route was post-edited for tiny overlaps.

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

  const selectedGroup = focusedGroup || (selected && index ? (index.byId[selected] || {}).group : null);
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

  // Compute the true bounding box of everything that gets drawn: node rects,
  // polyline waypoints (including detour bumps), and label rects. ELK's
  // laid.width/height only covers the node frame — labels and detour waypoints
  // can spill over, which used to clip the right/left edges of the canvas.
  let minX = 0, minY = 0;
  let maxX = laid.width || 1000;
  let maxY = laid.height || 800;
  for (const box of (laid.children || [])) {
    if (box.x < minX) minX = box.x;
    if (box.y < minY) minY = box.y;
    if (box.x + box.width  > maxX) maxX = box.x + box.width;
    if (box.y + box.height > maxY) maxY = box.y + box.height;
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
  const pad = 20;
  const vbX = Math.floor(minX - pad);
  const vbY = Math.floor(minY - pad);
  const W = Math.ceil(maxX - minX + 2 * pad);
  const H = Math.ceil(maxY - minY + 2 * pad);
  let svg = `<svg viewBox="${vbX} ${vbY} ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="display:block;margin:0 auto;width:calc(100% * var(--px-zoom, 1));height:auto" data-view="group-map" data-natural-w="${W}" data-natural-h="${H}">`;
  svg += PX.components.markers();

  // Render in three layers: arrow paths → cards → labels. Labels on top
  // means their bg-filled rects mask any stray arrow that clips them.
  const mkLabel = (e) => (e.count > 0 && e.sourceGroup && e.targetGroup ? {
    sourceName: e.sourceGroup,
    sourceColor: PX.groupColor(e.sourceGroup, groupsMeta[e.sourceGroup] || {}),
    targetName: e.targetGroup,
    targetColor: PX.groupColor(e.targetGroup, groupsMeta[e.targetGroup] || {}),
    count: e.count,
  } : null);

  for (const e of edges) {
    const st = groupEdgeState(e);
    svg += PX.components.edge(e, { nodesById, state: st, thick: true, pathOnly: true });
  }

  for (const box of (laid.children || [])) {
    const meta = groupsMeta[box.id] || {};
    const color = PX.groupColor(box.id, meta);
    const fileCount = (graph.nodes || []).filter(n => (n.group || 'Ungrouped') === box.id).length;
    const st = groupBoxState(box.id);
    svg += PX.components.cardHero({
      x: box.x, y: box.y, w: box.width, h: box.height,
      name: box.id,
      color,
      desc: meta.desc || meta.description || '',
      highlights: meta.highlights || [],
      fileCount,
      layer: layerOf[box.id] || 0,
      selected: st === 'selected',
      faded: st === 'faded',
    });
  }

  for (const e of edges) {
    const st = groupEdgeState(e);
    const label = mkLabel(e);
    if (!label) continue;
    svg += PX.components.edge(e, { nodesById, state: st, label, thick: true, labelOnly: true });
  }

  svg += `</svg>`;
  return { svg, laid, nodesById, edges, W, H };
};
