// views/group-map.js — Group Map renderer.
// Shows only hero cards for each group + aggregate "Nx imports" arrows
// between them. The view runs its own ELK layout (viewMode='group-map')
// because the card sizes differ from Nested (320x180 hero cards).

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
  const edgeCounts = Object.fromEntries((ir.edges || []).map(e => [e.id, e.count || 1]));
  const withCounts = polylines.map(p => {
    const src = PX.splitPortId(p.source).nodeId;
    const tgt = PX.splitPortId(p.target).nodeId;
    return { ...p, count: edgeCounts[p.id] || 1, sourceGroup: src, targetGroup: tgt };
  });
  // Pre-compute label bbox so the collision avoider can nudge overlaps apart
  // before anything is drawn. 3-line colored labels are 50px tall; width is
  // driven by the widest of the 3 lines. The 7.6/7.2 char multipliers match
  // actual rendered width for JetBrains Mono at 11px — earlier numbers (6.8/6.4)
  // underestimated by ~15%, which made the avoider think non-overlapping
  // labels were fine when they were actually touching.
  // Char-width estimates have to run slightly wide so the collision avoider
  // nudges labels apart even in borderline cases. We measured real rendered
  // width and went 10% higher, then added a generous gap so the "almost
  // touching" case never leaks into visual overlap.
  const CH_BOLD = 8.2;
  const CH_REG  = 7.6;
  const withLabelDims = withCounts.map(e => {
    const line1 = `[${e.sourceGroup}]`;
    const line2 = `imports ${e.count}\u00d7`;
    const line3 = `[${e.targetGroup}]`;
    const w = Math.max(line1.length * CH_BOLD, line2.length * CH_REG, line3.length * CH_BOLD) + 26;
    return { ...e, __labelW: w, __labelH: 50 };
  });
  // centerOnPath: aggregate edges between big hero cards often route as
  // L/Z/U shapes around obstacles. The longest-horizontal strategy (used by
  // nested) can pick a peripheral detour segment, leaving labels visually
  // detached from the "main" path. Arc-length midpoint keeps the label on
  // the polyline — vertical-segment landings are masked by the label rect's
  // bg fill.
  const placed = PX.placeEdgeLabels(withLabelDims, { centerOnPath: true });
  // Flat list of every orthogonal segment, tagged with its owning edge. The
  // collision avoider uses it to reject label Y-positions that would sit on
  // a foreign arrow (the label's own segment is masked by its rect fill).
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
  const withLabels = PX.avoidLabelCollisions(placed, {
    labelW: (e) => e.__labelW || 180,
    labelH: (e) => e.__labelH || 50,
    gap: 18,
    segments,
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

  // Selection lives at group level in Group Map. The selected file from the
  // sidebar maps to a group; edges in/out of that group highlight.
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
    const involved = withLabels.some(e => (e.sourceGroup === selectedGroup && e.targetGroup === name) || (e.targetGroup === selectedGroup && e.sourceGroup === name));
    return involved ? 'normal' : 'faded';
  };

  const W = Math.round((laid.width || 1000) + 40);
  const H = Math.round((laid.height || 800) + 40);
  // Scale SVG to fit container width — never blow past natural size but always
  // shrink to fit when the canvas is narrower. Height follows aspect ratio,
  // so the user scrolls vertically instead of horizontally. This kills the
  // "Tests card clipped on the right" bug that appeared when laid.width > viewport.
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="display:block;margin:0 auto;width:calc(100% * var(--px-zoom, 1));height:auto" data-view="group-map" data-natural-w="${W}" data-natural-h="${H}">`;
  svg += PX.components.markers();

  for (const e of withLabels) {
    const st = groupEdgeState(e);
    // Three-line label: [source] / imports Nx / [target]. Source + target
    // names are colored with their group's swatch so the eye links arrow
    // to block instantly.
    const label = e.count > 0 && e.sourceGroup && e.targetGroup ? {
      sourceName: e.sourceGroup,
      sourceColor: PX.groupColor(e.sourceGroup, groupsMeta[e.sourceGroup] || {}),
      targetName: e.targetGroup,
      targetColor: PX.groupColor(e.targetGroup, groupsMeta[e.targetGroup] || {}),
      count: e.count,
    } : null;
    svg += PX.components.edge(e, { nodesById, state: st, label, thick: true, reverseArrow: true });
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

  svg += `</svg>`;
  return { svg, laid, nodesById, edges: withLabels, W, H };
};
