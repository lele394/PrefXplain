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
    hoveredFile = null,
  } = opts;
  const idx = index || PX.buildGraphIndex(graph);
  const focusGroupId = focusedGroup || (selected && idx.byId[selected]
    ? ((idx.byId[selected].group || 'Ungrouped'))
    : null);

  if (!focusGroupId) {
    return PX.views._nestedOverview(graph, idx, { showBullets, selected, filter, hoveredGroup });
  }
  return PX.views._nestedFocused(graph, idx, focusGroupId, {
    showBullets, selected, filter, hoveredGroup, hoveredFile,
  });
};

// ── Overview (no group focused): full-canvas nested landscape ──────────
PX.views._nestedOverview = async function renderOverview(graph, idx, opts) {
  const { showBullets, selected, filter, hoveredGroup = null } = opts;
  const groupsMeta = graph.metaGroups || {};
  const overviewIr = PX.buildIr(graph, 'nested', {
    showBullets,
    index: idx,
    compact: false,
  });
  overviewIr.layoutOptions = { 'elk.aspectRatio': '0.9' };

  const laid = await PX.runLayout(overviewIr);
  const nodesByIdRaw = PX._collectNodes(laid);
  const edgeMetaById = Object.fromEntries((overviewIr.edges || []).map(e => [e.id, e]));
  const rawPolylines = PX.extractEdgePolylines(laid).map(e => ({
    ...e,
    ...(edgeMetaById[e.id] || {}),
  }));
  // Rule: arrows never cross group blocks. Detour any middle segment that
  // would clip an intermediate group card (source/target cards excluded —
  // the arrow terminates at their ports).
  const overviewCardBboxes = (laid.children || []).map(box => ({
    id: box.id,
    x1: box.x || 0, y1: box.y || 0,
    x2: (box.x || 0) + (box.width || 0),
    y2: (box.y || 0) + (box.height || 0),
  }));
  const polylines = rawPolylines.map(e => {
    const srcId = PX.splitPortId(e.source).nodeId;
    const tgtId = PX.splitPortId(e.target).nodeId;
    const obstacles = overviewCardBboxes.filter(b => b.id !== srcId && b.id !== tgtId);
    if (obstacles.length === 0) return e;
    return {
      ...e,
      points: PX.detourAroundLabels(e.points || [], obstacles, 14, { preserveEndSegments: true }),
    };
  });
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
  const placed = PX.avoidLabelCollisions(labelled, {
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
  // Mirror group-map's final detour pass: route each edge around OTHER
  // edges' label rects so foreign segments don't cross a visible label
  // when the edge highlights. preserveEndSegments keeps port stubs clean.
  const labelBboxes = placed
    .filter(e => e.labelX != null && e.labelY != null && e.count > 0)
    .map(e => ({
      id: e.id,
      x1: e.labelX - (e.__labelW || 0) / 2,
      y1: e.labelY - (e.__labelH || 0) / 2,
      x2: e.labelX + (e.__labelW || 0) / 2,
      y2: e.labelY + (e.__labelH || 0) / 2,
    }));
  const edges = placed.map(e => {
    const foreign = labelBboxes.filter(b => b.id !== e.id);
    if (foreign.length === 0) return e;
    return {
      ...e,
      points: PX.detourAroundLabels(e.points || [], foreign, 2, { preserveEndSegments: true }),
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
  const { showBullets, selected, filter, hoveredGroup = null, hoveredFile = null } = opts;
  const story = PX.buildGroupStory(graph, groupId, idx);
  const LEFT = 32;
  const TOP = 20;
  const GAP = 14;
  // Selected file (if it belongs to the focused group) gets its name tucked
  // next to the group title inside the summary banner. The top bar used to
  // own that text; we moved it here so the top bar stays a stable brand
  // anchor ("prefxplain"). The in-SVG "detail summary" banner was folded
  // into the top info bar (#px-top), so no extra vertical space is
  // reserved here beyond the standard top pad + gap.
  const SUMMARY_H = 0;
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
  // Anchor margin scales with anchor count — but each side is budgeted
  // INDEPENDENTLY. Using max(depCount, useCount) for both sides (the old
  // behavior) over-allocates the lighter side and pushes its anchor column
  // needlessly far from the content, which showed up as "USED BY floats
  // way off to the right" when a group has e.g. 3 deps + 1 use.
  //
  // Routing geometry is asymmetric:
  //   USE (right) last-segment stub  [furthest corridor → anchor tip]:
  //     must be > tailTrim (14) + bend radius (6) + visible shaft (14) = 34,
  //     with one extra anchor adding 12px of corridor offset. That gives
  //     useMargin ≥ 58 + (N_use − 1) * 12. We use max(60, 48 + N_use*12)
  //     for a 2px safety.
  //   DEP (left) first-segment stub  [anchor.right → closest corridor]:
  //     only needs a clean visible shaft (≥14px) before the first bend.
  //     depMargin ≥ 28 + (N_dep − 1) * 12; we use max(40, 28 + N_dep*12)
  //     for 2px safety and a 40px floor to keep the arrow tail readable
  //     even when the anchor column is lightly populated.
  const depMarginDyn = Math.max(40, 28 + depAnchors.length * 12);
  const useMarginDyn = Math.max(60, 48 + useAnchors.length * 12);
  const leftReserved = depAnchors.length > 0 ? ANCHOR_W + depMarginDyn : 0;
  const rightReserved = useAnchors.length > 0 ? ANCHOR_W + useMarginDyn : 0;
  // Kept for the anchor-column VERTICAL stack height calc below (anchors
  // are stacked per-side, but the canvas height must fit the taller one).
  const maxAnchorCount = Math.max(depAnchors.length, useAnchors.length);

  // Adaptive canvas width: hug the actual story instead of forcing a fixed
  // 1640px shell. A group with 2–3 child blocks should not leave a giant
  // empty right-hand gutter that pushes the USED-BY anchors off-screen and
  // forces horizontal scrolling through nothing.
  //
  // Must stay in lock-step with the buildGroupStoryLayoutIr call below
  // (bandGapX=72, leftPad=0). The ir's "wide" column layout needs
  //   canvasWidth ≥ columnBands.length * cw + (columnBands.length-1) * bandGapX
  // otherwise targetCols drops and bands collapse into a stacked grid.
  const CW_NAT = (showBullets ? PX.NODE_SIZES.fileBullets.w : PX.NODE_SIZES.fileNoBullets.w);
  const BAND_GAP_X_NAT = 72;
  const BAND_COL_KEYS_NAT = ['entry', 'core', 'leaf'];
  const storyBands = story.bands || [];
  const storyColBands = storyBands.filter(b => BAND_COL_KEYS_NAT.includes(b.key));
  const storyTestBand = storyBands.find(b => b.key === 'test') || null;
  const storyStandaloneBand = storyBands.find(b => b.key === 'standalone') || null;
  // Column bands render SIDE-BY-SIDE, one card wide each.
  const colCountNat = storyColBands.length;
  const naturalColW = colCountNat > 0
    ? colCountNat * CW_NAT + (colCountNat - 1) * BAND_GAP_X_NAT
    : 0;
  // Tests + standalone wrap into a grid. Cap at 4 columns so a group with
  // many tests grows DOWN (more rows) instead of blowing up the canvas
  // horizontally. Matches the density feel of the multi-group overview.
  const MAX_WRAP_COLS_NAT = 4;
  const gridNatW = (units) => {
    if (units <= 0) return 0;
    const cols = Math.min(Math.max(units, 1), MAX_WRAP_COLS_NAT);
    return cols * CW_NAT + (cols - 1) * BAND_GAP_X_NAT;
  };
  const testUnitsNat = storyTestBand
    ? (Array.isArray(storyTestBand.clusters) && storyTestBand.clusters.length > 0
        ? storyTestBand.clusters.length
        : storyTestBand.files.length)
    : 0;
  const naturalTestW = gridNatW(testUnitsNat);
  const naturalStandaloneW = gridNatW(
    storyStandaloneBand ? storyStandaloneBand.files.length : 0,
  );
  // Final main width = widest content row. Floor at one card so a lone
  // standalone file still renders cleanly instead of 0-width.
  const mainWidth = Math.max(
    CW_NAT,
    naturalColW,
    naturalTestW,
    naturalStandaloneW,
  );
  const CANVAS = mainWidth + 2 * LEFT + leftReserved + rightReserved;
  const mainLeft = LEFT + leftReserved;

  // Boundary edges route as:  anchor → corridor → vertical → target
  // They pick up local detours around intermediate cards only where the
  // horizontal-at-target-Y leg actually crosses one. No global trunk
  // above/below — that created a U-shape (UP to trunk, across, DOWN to
  // target) which read as "retour en arrière" when target sat between
  // the anchor and the trunk.
  const DEP_ZONE_H = 0;
  const USE_ZONE_H = 0;

  // Top bar (#px-top) already shows the focused group name, description, and a
  // "back to overview" button — no breadcrumb needed inside the SVG. No
  // PRIMARY ENTRY PATHS strip either; it duplicated the ENTRY band.
  const bandsStartY = TOP + SUMMARY_H + GAP + DEP_ZONE_H;

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

  // Hand-route intra-group edges using the known band/column structure.
  //
  // ELK's 'fixed' algorithm proved fragile for this layout — it aborts with
  // "edge section count 0" on some graphs and leaves zero polylines. Hand-
  // routing is deterministic, respects the rules, and always succeeds.
  //
  // The rules we enforce:
  //   1. Arrows NEVER cross a card. Horizontal runs sit in the gap BETWEEN
  //      columns (empty by construction) or BELOW all cards (trunk zone).
  //      Vertical runs sit in a column's side gap.
  //   2. The arrowhead tip lands AT the target's border.
  //   3. Each arrow owns its own corridor (per-edge lane offset).
  //
  // Routing strategy (picked per edge from relative position):
  //   SHORT HOP (same col OR adjacent col, dx ≤ cw + bandGapX):
  //     4-point C/Z shape flowing horizontally through the gap between
  //     source and target. Enters target from its WEST or EAST side.
  //     Short path, stays inside the visible band area — no risk of
  //     overshooting the canvas top.
  //   LONG HOP (>1 column apart):
  //     6-point trunk route: source.SOUTH → down to trunk below all cards
  //     → across → up in target's side-gap → across above target → DOWN
  //     into target.NORTH. Only this shape can skip over intermediate
  //     columns without crossing their cards.
  const cards = layout.ir.children || [];
  const cardById = Object.fromEntries(cards.map(c => [c.id, c]));
  const mainBandsBottomY = cards.length > 0
    ? Math.max(...cards.map(c => c.y + c.height))
    : 0;
  const TRUNK_BASE = mainBandsBottomY + 20;
  const APPROACH_MARGIN = 18;
  const GAP_OFFSET = 22;
  // Column width including the bandGapX that separates parallel columns.
  // We use this to decide whether a hop crosses zero, one, or many gaps.
  const BAND_GAP_X = 72;            // matches buildGroupStoryLayoutIr call
  const CARD_WIDTH = cards.length > 0 ? cards[0].width : 304;
  const COL_STRIDE = CARD_WIDTH + BAND_GAP_X;

  const edgesRouted = layout.ir.edges.map((e, i) => {
    const sNode = cardById[e.sourceNode];
    const tNode = cardById[e.targetNode];
    if (!sNode || !tNode) return null;

    const dx = tNode.x - sNode.x;
    const numColsApart = Math.round(Math.abs(dx) / COL_STRIDE);
    const laneX = i * 10;
    const laneY = i * 10;

    const sMidY = sNode.y + sNode.height / 2;
    const tMidY = tNode.y + tNode.height / 2;

    let points;

    if (numColsApart === 0) {
      // Same column — 4-point C route in the RIGHT gap of the column.
      // Enters target from its EAST side, so arrowhead touches the right
      // border of the card.
      const gapX = sNode.x + sNode.width + GAP_OFFSET + laneX;
      const sSideX = sNode.x + sNode.width;
      const tSideX = tNode.x + tNode.width;
      points = [
        { x: sSideX, y: sMidY },     // source.EAST
        { x: gapX,   y: sMidY },     // horiz into right gap
        { x: gapX,   y: tMidY },     // vert in right gap
        { x: tSideX, y: tMidY },     // horiz back into target.EAST
      ];
    } else if (numColsApart === 1) {
      // Adjacent columns — 4-point route through the gap between them.
      // Arrow flows left→right (or right→left), enters target from the
      // WEST or EAST side depending on direction.
      const rightward = dx > 0;
      const gapCenterX = rightward
        ? sNode.x + sNode.width + BAND_GAP_X / 2 + laneX - (BAND_GAP_X / 4)
        : sNode.x - BAND_GAP_X / 2 - laneX + (BAND_GAP_X / 4);
      const sSideX = rightward ? sNode.x + sNode.width : sNode.x;
      const tSideX = rightward ? tNode.x : tNode.x + tNode.width;
      points = [
        { x: sSideX,    y: sMidY },
        { x: gapCenterX, y: sMidY },
        { x: gapCenterX, y: tMidY },
        { x: tSideX,    y: tMidY },
      ];
    } else {
      // Far hop (skips one or more columns) — 6-point trunk route below
      // all cards. Only this shape can get past intermediate columns.
      const sx = sNode.x + sNode.width / 2;
      const sy = sNode.y + sNode.height;
      const tx = tNode.x + tNode.width / 2;
      const ty = tNode.y;
      const trunkY = TRUNK_BASE + laneY;
      const approachY = ty - APPROACH_MARGIN;
      const gapX = dx > 0
        ? tNode.x - GAP_OFFSET - laneX
        : tNode.x + tNode.width + GAP_OFFSET + laneX;
      points = [
        { x: sx,   y: sy },
        { x: sx,   y: trunkY },
        { x: gapX, y: trunkY },
        { x: gapX, y: approachY },
        { x: tx,   y: approachY },
        { x: tx,   y: ty },
      ];
    }

    return {
      ...e,
      source: `${e.sourceNode}.out-gs${i}`,
      target: `${e.targetNode}.in-gs${i}`,
      points,
    };
  }).filter(Boolean);

  // Used only for bounding-box computation later (layout.ir.children already
  // carry absolute coordinates in the pre-translate frame); we no longer
  // need ELK's laid tree for anything.
  const laid = null;

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

  // Rule: arrows never cross cards — they must go AROUND them. ELK's router
  // mostly honors this under FIXED with ORTHOGONAL + generous edgeNode
  // spacing, but tight band layouts can still produce segments that clip an
  // intermediate card. We detour any middle segment that would cross a card
  // (source/target cards excluded since the path terminates at their ports).
  // preserveEndSegments keeps the port stubs untouched so the arrowhead's
  // tailTrim sleeve (~14px at stroke-width 2) lands cleanly on the border.
  const cardObstaclesFor = (e) => {
    const excluded = new Set([e.sourceNode, e.targetNode]);
    return Object.entries(nodesById)
      .filter(([id]) => !excluded.has(id))
      .map(([id, n]) => ({ id, x1: n.x, y1: n.y, x2: n.x + n.w, y2: n.y + n.h }));
  };
  const cardAvoidedEdges = edgesTranslated.map(e => {
    const obstacles = cardObstaclesFor(e);
    if (obstacles.length === 0) return e;
    return {
      ...e,
      points: PX.detourAroundLabels(e.points || [], obstacles, 14, { preserveEndSegments: true }),
    };
  });

  // Edge label placement + collision avoidance — reuse the group-map pipeline.
  const labelled = PX.placeEdgeLabels(cardAvoidedEdges, { centerOnPath: false });
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
  const labelWFn = (e) => e.labelled ? (String(e.count).length + 8) * 6.4 + 16 : 0;
  const labelHFn = (e) => e.labelled ? 20 : 0;
  const placedEdges = PX.avoidLabelCollisions(labelled, {
    labelW: labelWFn,
    labelH: labelHFn,
    gap: 14,
    segments,
    walkPath: true,
    cardRects,
  });

  // Final pass: detour each intra-group edge around OTHER edges' label
  // rects. Same technique as group-map — without it, foreign segments that
  // pass under a label become visible when the edge highlights (bg-fill
  // rect can't hide segments from unrelated edges). Uses preserveEndSegments
  // so port stubs stay clean and the arrowhead tailTrim sleeve is kept.
  const intraLabelBboxes = placedEdges
    .filter(e => e.labelled && e.labelX != null && e.labelY != null)
    .map(e => {
      const lw = labelWFn(e), lh = labelHFn(e);
      return {
        id: e.id,
        x1: e.labelX - lw / 2,
        y1: e.labelY - lh / 2,
        x2: e.labelX + lw / 2,
        y2: e.labelY + lh / 2,
      };
    });
  const finalEdges = placedEdges.map(e => {
    const foreign = intraLabelBboxes.filter(b => b.id !== e.id);
    if (foreign.length === 0) return e;
    return {
      ...e,
      points: PX.detourAroundLabels(e.points || [], foreign, 2, { preserveEndSegments: true }),
    };
  });

  // ── Compose SVG ───────────────────────────────────────────────────
  // Compute final canvas size. Bands section height comes from the layout;
  // stress strip adds its own measured height. Anchor columns may be taller
  // than the bands for groups with many external neighbors — make canvas
  // at least as tall as the tallest anchor column. USE_ZONE_H reserves the
  // horizontal USE trunk zone below the bands so the stress strip doesn't
  // collide with below-bands trunks.
  const bandsH = layout.canvasH;
  const anchorsStackH = maxAnchorCount > 0
    ? maxAnchorCount * ANCHOR_H + Math.max(0, maxAnchorCount - 1) * ANCHOR_GAP_Y
    : 0;
  // Reserve room below the bands for the hand-routed trunk zone. Without
  // this, the trunk Y (mainBandsBottomY + 20 + lane*10) can overshoot bandsH
  // for groups with many edges, pushing the polyline past the canvas.
  const allEdgeYs = edgesRouted.flatMap(e => (e.points || []).map(p => p.y));
  const maxEdgeY = allEdgeYs.length > 0 ? Math.max(...allEdgeYs) : 0;
  const neededH = Math.max(bandsH, maxEdgeY + 20);
  const contentH = Math.max(neededH + USE_ZONE_H, anchorsStackH);
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
  //
  // Six-point trunk routing — every vertical drop sits OUTSIDE the column
  // (in the card-free gap between bands), so it can't slice through the
  // same-column cards above/below the endpoint:
  //
  //   DEP: anchor.right @ anchor.y
  //     →  corridorX @ anchor.y             (horiz into LEFT corridor)
  //     →  corridorX @ depTrunkY            (vert in corridor to DEP trunk)
  //     →  (target.left - APPROACH) @ depTrunkY  (horiz in DEP trunk)
  //     →  (target.left - APPROACH) @ target.midY  (vert in LEFT gap of target column)
  //     →  target.left @ target.midY        (short stub into target)
  //
  //   USE: source.right @ source.midY
  //     →  (source.right + APPROACH) @ source.midY
  //     →  (source.right + APPROACH) @ useTrunkY  (vert in RIGHT gap of source column)
  //     →  corridorX @ useTrunkY
  //     →  corridorX @ anchor.y
  //     →  anchor.left @ anchor.y
  //
  // Per-anchor trunk Y and corridor X offsets keep parallel boundary edges
  // separated. APPROACH must be large enough that the final stub
  // (APPROACH − PAD) leaves ≥14px of clean horizontal shaft AFTER tailTrim
  // (14) AND the Q-rounded corner (6). Budget: APPROACH ≥ PAD + 14 + 6 + 14
  // = PAD + 34. With PAD=10 → APPROACH=44. PAD is the breathing gap
  // between the arrowhead tip and the target card's border.
  const APPROACH = 44;
  const PAD = 10;
  const DEP_CORRIDOR_BASE = mainLeft - 14;   // just right of LEFT anchors
  const USE_CORRIDOR_BASE = mainLeft + mainWidth + 14; // just left of RIGHT anchors
  const depCorridorX = {};
  depAnchors.forEach((a, i) => { depCorridorX[a.groupId] = DEP_CORRIDOR_BASE - i * 12; });
  const useCorridorX = {};
  useAnchors.forEach((a, i) => { useCorridorX[a.groupId] = USE_CORRIDOR_BASE + i * 12; });
  const boundaryEdges = [];
  // Dependency edges: arrow tail on the anchor (upstream), arrowhead lands
  // on the LEFT side of the target card via a drop in the LEFT-of-column gap.
  for (const e of story.externalOutEdges || []) {
    const tgt = nodesById[e.fileId];
    const anchor = depAnchorPos[e.groupId];
    if (!tgt || !anchor) continue;
    const sx = anchor.x + anchor.w;              // anchor's right edge
    const sy = anchor.y + anchor.h / 2;
    const approachX = tgt.x - APPROACH;          // LEFT gap of target column
    const ty = tgt.y + tgt.h / 2;                // target mid-Y
    const tipX = tgt.x - PAD;                    // arrow tip lands PAD px OUTSIDE the card
    const cx = depCorridorX[e.groupId];
    // Normalize: when the target sits next to the anchor column (approachX
    // would land LEFT of the corridor), collapse the corridor onto the
    // approach X so every horizontal segment still flows left→right. This
    // kills the LEFT-going jog that reads as "retour en arrière".
    const effectiveCx = Math.min(cx, approachX);
    const points = effectiveCx < approachX ? [
      { x: sx, y: sy },
      { x: effectiveCx, y: sy },
      { x: effectiveCx, y: ty },
      { x: approachX, y: ty },
      { x: tipX, y: ty },
    ] : [
      { x: sx, y: sy },
      { x: effectiveCx, y: sy },
      { x: effectiveCx, y: ty },
      { x: tipX, y: ty },
    ];
    boundaryEdges.push({
      id: `bd-${e.fileId}-${e.groupId}`,
      kind: 'boundary-dep',
      fileId: e.fileId,
      groupId: e.groupId,
      count: e.count,
      color: depAnchors.find(a => a.groupId === e.groupId)?.color || PX.T.inkMuted,
      points,
    });
  }
  // Consumer edges: arrow tail on the RIGHT side of our file (via a stub
  // into the RIGHT-of-column gap), arrowhead on the downstream anchor.
  for (const e of story.externalInEdges || []) {
    const src = nodesById[e.fileId];
    const anchor = useAnchorPos[e.groupId];
    if (!src || !anchor) continue;
    const sx = src.x + src.w;                    // source's right edge
    const sy = src.y + src.h / 2;                // source mid-Y
    const approachX = src.x + src.w + APPROACH;  // RIGHT gap of source column
    const tipX = anchor.x - PAD;                 // arrow tip lands PAD px OUTSIDE the anchor
    const ty = anchor.y + anchor.h / 2;
    const cx = useCorridorX[e.groupId];
    // Mirror the DEP normalization: keep every horizontal segment flowing
    // left → right by clamping approachX so it never sits right of the
    // anchor-side corridor.
    const effectiveCx = Math.max(cx, approachX);
    const points = effectiveCx > approachX ? [
      { x: sx, y: sy },
      { x: approachX, y: sy },
      { x: effectiveCx, y: sy },
      { x: effectiveCx, y: ty },
      { x: tipX, y: ty },
    ] : [
      { x: sx, y: sy },
      { x: effectiveCx, y: sy },
      { x: effectiveCx, y: ty },
      { x: tipX, y: ty },
    ];
    boundaryEdges.push({
      id: `bu-${e.fileId}-${e.groupId}`,
      kind: 'boundary-use',
      fileId: e.fileId,
      groupId: e.groupId,
      count: e.count,
      color: useAnchors.find(a => a.groupId === e.groupId)?.color || PX.T.inkMuted,
      points,
    });
  }

  // Local detour: any horizontal leg of a boundary edge that clips a card
  // in an intermediate column bumps around the card's bbox (top or bottom,
  // whichever is closer to the leg's Y). preserveEndSegments keeps port
  // stubs clean so the arrowhead shaft stays long enough for tailTrim.
  for (let i = 0; i < boundaryEdges.length; i++) {
    const be = boundaryEdges[i];
    const obstacles = Object.entries(nodesById)
      .filter(([id]) => id !== be.fileId)
      .map(([id, n]) => ({ id, x1: n.x, y1: n.y, x2: n.x + n.w, y2: n.y + n.h }));
    if (obstacles.length === 0) continue;
    boundaryEdges[i] = {
      ...be,
      points: PX.detourAroundLabels(be.points, obstacles, 12, { preserveEndSegments: true }),
    };
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
  // Transient hover over a file card: light up its arrows without dimming
  // the rest. Takes effect only when nothing is selected so clicks win.
  const effectiveHoverFile = (!selected && hoveredFile && hoveredFile !== selected)
    ? hoveredFile
    : null;
  const hoverNeighbors = effectiveHoverFile ? neighborsOf(effectiveHoverFile) : null;
  // Priority: explicit selection wins over any transient group/file hover.
  // Without this order a stale hoveredGroup — a pin that's about to be
  // cleared, or a hover debounce that hasn't fired yet — dominates the
  // just-made file selection and makes the click look like a no-op.
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
    if (selected) {
      if (id === selected) return 'selected';
      if (selectedNeighbors && selectedNeighbors.has(id)) {
        for (const e of graph.edges || []) {
          if (e.source === selected && e.target === id) return 'depends';
          if (e.target === selected && e.source === id) return 'imports';
        }
      }
      return 'dimmed';
    }
    if (hoveredGroup) {
      const isConnected = boundaryEdges.some(be => be.groupId === hoveredGroup && be.fileId === id);
      return isConnected ? 'normal' : 'dimmed';
    }
    if (effectiveHoverFile) {
      if (id === effectiveHoverFile) return 'normal';
      if (hoverNeighbors && hoverNeighbors.has(id)) {
        for (const e of graph.edges || []) {
          if (e.source === effectiveHoverFile && e.target === id) return 'depends';
          if (e.target === effectiveHoverFile && e.source === id) return 'imports';
        }
      }
      return 'normal';
    }
    return 'normal';
  };
  const edgeState = (e) => {
    if (selected) {
      if (e.sourceNode === selected) return 'depends';
      if (e.targetNode === selected) return 'imports';
      return 'faded';
    }
    if (hoveredGroup) return 'faded';
    if (effectiveHoverFile) {
      if (e.sourceNode === effectiveHoverFile) return 'depends';
      if (e.targetNode === effectiveHoverFile) return 'imports';
      // Fade unrelated arrows on hover so the highlighted ones pop.
      return 'faded';
    }
    return 'normal';
  };

  const boundaryEdgeState = (be) => {
    if (selected) {
      if (be.fileId === selected) return be.kind === 'boundary-use' ? 'imports' : 'depends';
      return 'faded';
    }
    if (hoveredGroup) {
      return hoveredGroup === be.groupId
        ? (be.kind === 'boundary-use' ? 'imports' : 'depends')
        : 'faded';
    }
    if (effectiveHoverFile) {
      if (be.fileId === effectiveHoverFile) {
        return be.kind === 'boundary-use' ? 'imports' : 'depends';
      }
      return 'faded';
    }
    return 'normal';
  };

  // Scale the focused view to fit its parent like the multi-group overview:
  // width:100% + preserveAspectRatio="xMidYMid meet" lets the SVG shrink
  // proportionally on narrow viewports instead of locking to the natural
  // CANVAS width. Previously we pinned min-width:${W}px which forced the
  // parent (#px-canvas, overflow:auto) to scroll horizontally whenever the
  // viewport was narrower than CANVAS — even when the canvas was only
  // slightly over budget. With this, zoom > 1 is the opt-in path for bigger
  // cards; at zoom = 1 the whole story is always fully visible.
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="display:block;margin:0 auto;width:calc(100% * var(--px-zoom, 1));height:auto" data-view="nested" data-natural-w="${W}" data-natural-h="${H}" data-focused-group="${PX.escapeXml(groupId)}">`;
  svg += PX.components.markers();

  // No in-SVG summary banner — the top info bar (#px-top) owns the
  // "focused group + selected file" identity, the description, and the
  // back-to-overview button.

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
    const stroke = PX.stateColor(state);
    const opacity = PX.stateOpacity(state, 'thin');
    const d = PX.pathD(be.points, 6, 14);
    // Marker matches state so the arrowhead color tracks the path color
    // (was hardcoded normal/faded → arrowheads stayed grey on lit paths).
    svg += `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="2" opacity="${opacity}" marker-end="url(#arr-${state})" style="transition:all 200ms"/>`;
    if (be.count > 1) {
      const lx = (be.points[1].x + be.points[2].x) / 2;
      const ly = (be.points[1].y + be.points[2].y) / 2;
      const txt = `${be.count}\u00D7`;
      const lw = txt.length * 6 + 12;
      svg += `<g pointer-events="none" opacity="${state === 'faded' ? 0.1 : 1}">`
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

  // Stress-points strip (bottom). Slide past the USE trunk zone so the
  // below-bands horizontal trunks don't collide with the stress strip.
  if (STRESS_H > 0) {
    const stress = PX.components.stressStrip({
      x: LEFT,
      y: bandsStartY + bandsH + USE_ZONE_H + GAP,
      w: CANVAS - 2 * LEFT,
      stress: story.stress,
    });
    svg += stress.svg;
  }

  svg += `</svg>`;

  PX.log(`[prefxplain] group-story ${groupId}: ${story.entries.length} entries, ${story.bands.length} bands, ${story.edges.length} edges, stress=${story.stress.length}`);

  return {
    svg,
    laid,
    nodesById,
    edges: finalEdges,
    W, H,
    story,
  };
};
