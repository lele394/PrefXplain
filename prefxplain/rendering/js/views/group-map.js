// views/group-map.js — Group Map renderer.
// Shows only hero cards for each group + aggregate "Nx imports" arrows
// between them. The view runs its own ELK layout (viewMode='group-map')
// because the card sizes differ from Nested (320x180 hero cards).
//
// Labels participate in layout via the IR (ir.js → _aggregateGroupEdges
// declares them). ELK reserves space and routes edges aware of label
// footprints. ELK's own label placement (with inline=true) was tried and
// produced all-labels-clustered-at-(0,0) in our setup, so we keep our own
// placeEdgeLabels + avoidLabelCollisions pass on top of ELK's routing.

window.PX = window.PX || {};
PX.views = PX.views || {};

PX.views.groupMap = async function renderGroupMap(graph, opts = {}) {
  const { selected = null, index = null, focusedGroup = null, hoveredGroup = null } = opts;
  const groupsMeta = graph.metaGroups || {};
  const ir = PX.buildIr(graph, 'group-map');

  // Sort high-out-degree groups first so dependency arrows tend to flow
  // downward toward their imports within the Coffman-Graham layers.
  const outDeg = {};
  for (const e of ir.edges || []) {
    if (e.sourceGroupName) outDeg[e.sourceGroupName] = (outDeg[e.sourceGroupName] || 0) + 1;
  }
  ir.children.sort((a, b) => (outDeg[b.id] || 0) - (outDeg[a.id] || 0));

  // Coffman-Graham layering with layerBound=3 hard-caps nodes-per-layer to 3,
  // producing at most 3 visible columns. Edge routing stays with `layered`
  // (the default algorithm) so ELK creates proper edge sections — unlike
  // `elk.algorithm:'fixed'` which leaves edges with 0 sections and throws.
  ir.layoutOptions = {
    'elk.layered.layering.strategy': 'COFFMAN_GRAHAM',
    'elk.layered.layering.coffmanGraham.layerBound': '3',
  };

  const laid = await PX.runLayout(ir);
  const nodesById = PX._collectNodes(laid);
  const rawPolylines = PX.extractEdgePolylines(laid);
  const irEdgesById = Object.fromEntries((ir.edges || []).map(e => [e.id, e]));

  // Degree maps for badge rendering on hero cards.
  const inDegree = {}, outDegree = {};
  for (const e of ir.edges || []) {
    if (e.sourceGroupName) outDegree[e.sourceGroupName] = (outDegree[e.sourceGroupName] || 0) + 1;
    if (e.targetGroupName) inDegree[e.targetGroupName] = (inDegree[e.targetGroupName] || 0) + 1;
  }

  // Rule: arrows never cross group blocks. Detour any middle segment that
  // would clip an intermediate group card (source/target cards excluded).
  const cardBboxes = (laid.children || []).map(box => ({
    id: box.id,
    x1: box.x || 0, y1: box.y || 0,
    x2: (box.x || 0) + (box.width || 0),
    y2: (box.y || 0) + (box.height || 0),
  }));
  const edges = rawPolylines.map(p => {
    const srcId = PX.splitPortId(p.source).nodeId;
    const tgtId = PX.splitPortId(p.target).nodeId;
    const irEdge = irEdgesById[p.id] || {};
    const obstacles = cardBboxes.filter(b => b.id !== srcId && b.id !== tgtId);
    const points = obstacles.length === 0
      ? (p.points || [])
      : PX.detourAroundLabels(p.points || [], obstacles, 14, { preserveEndSegments: true });
    return {
      ...p,
      points,
      count: irEdge.count || 1,
      sourceGroup: srcId,
      targetGroup: tgtId,
    };
  });

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

  const selectedGroup = focusedGroup || hoveredGroup || (selected && index ? (index.byId[selected] || {}).group : null);
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
  }
  const pad = 20;
  const vbX = Math.floor(minX - pad);
  const vbY = Math.floor(minY - pad);
  const W = Math.ceil(maxX - minX + 2 * pad);
  const H = Math.ceil(maxY - minY + 2 * pad);
  let svg = `<svg viewBox="${vbX} ${vbY} ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="display:block;margin:0 auto;width:calc(100% * var(--px-zoom, 1));height:auto" data-view="group-map" data-natural-w="${W}" data-natural-h="${H}">`;
  svg += PX.components.markers();

  // Two layers: arrows below cards so arrowheads don't overdraw card borders.
  for (const e of edges) {
    const st = groupEdgeState(e);
    svg += PX.components.edge(e, { nodesById, state: st, thick: true });
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
      inDegree: inDegree[box.id] || 0,
      outDegree: outDegree[box.id] || 0,
    });
  }

  svg += `</svg>`;
  return { svg, laid, nodesById, edges, W, H };
};
