// views/nested.js — Focused group story renderer.
//
// Exports PX.views.focused(graph, opts). Used when a group is focused
// (state.focusedGroup !== null). Renders a structured "group story":
// breadcrumb, summary, primary entry paths, dependency-position bands
// (Entry / Core / Leaf / Test), intra-group edges with top-N verb labels,
// and a "stress points" strip when hubs/cycles/dominant-bridges exist.
// Cards are hand-positioned in bands (deterministic across renders);
// ELK is used only to route edges between fixed positions.
//
// The overview path (no group focused) is rendered by PX.views.groupMap.
// There used to be a `PX.views.nested` router + `_nestedOverview` body
// here; both are gone. Kept in git history if you need the previous
// multi-group nested landscape.

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

// Public entry point: render the focused group story. Requires a non-null
// `focusedGroup` — main.js only calls this branch when state.focusedGroup
// is set, so we don't route back to the overview here.
PX.views.focused = async function renderFocusedView(graph, opts = {}) {
  const {
    showBullets = true,
    selected = null,
    filter = '',
    index = null,
    focusedGroup = null,
    hoveredGroup = null,
    hoveredFile = null,
    standaloneCollapsed = false,
  } = opts;
  if (!focusedGroup) {
    throw new Error('PX.views.focused requires opts.focusedGroup');
  }
  const idx = index || PX.buildGraphIndex(graph);
  return PX.views._nestedFocused(graph, idx, focusedGroup, {
    showBullets, selected, filter, hoveredGroup, hoveredFile,
  });
};

// ── Focused group: ranked architectural narrative ──────────────────────
PX.views._nestedFocused = async function renderFocused(graph, idx, groupId, opts) {
  const { showBullets, selected, filter, hoveredGroup = null, hoveredFile = null, standaloneCollapsed = false } = opts;
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
  // Tests + standalone wrap into a grid. Cap at 3 columns (matches maxCols=3
  // in buildGroupStoryLayoutIr) so a group with many tests grows DOWN instead
  // of blowing up the canvas horizontally.
  const MAX_WRAP_COLS_NAT = 3;
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
  // Standalone natural width. Capped to the CORE content width so orphan files
  // never push the canvas wider than the main graph — they scroll vertically.
  // With a taxonomy, each sub-band lays out independently; the widest drives
  // the cap. Without a taxonomy we fall back to the total-file grid.
  let naturalStandaloneW = 0;
  if (storyStandaloneBand && storyStandaloneBand.files.length > 0 && !standaloneCollapsed) {
    const coreW = Math.max(naturalColW, CW_NAT);
    if (Array.isArray(storyStandaloneBand.taxonomy) && storyStandaloneBand.taxonomy.length > 0) {
      naturalStandaloneW = Math.min(
        Math.max(...storyStandaloneBand.taxonomy.map(sub => gridNatW(sub.files.length))),
        coreW,
      );
    } else {
      naturalStandaloneW = Math.min(gridNatW(storyStandaloneBand.files.length), coreW);
    }
  }
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
    standaloneCollapsed,
  });

  // ELK layered+interactive routes edges with ORTHOGONAL routing while
  // respecting pre-positioned nodes (set by buildGroupStoryLayoutIr).
  // portConstraints:FREE lets ELK assign EAST/WEST for inter-column hops
  // and SOUTH/NORTH for same-column hops — no hand-routing needed.
  const laid = await PX.runLayout(layout.ir);
  const laidNodesById = PX._collectNodes(laid);
  const rawPolylines = PX.extractEdgePolylines(laid);
  const irEdgesById = Object.fromEntries((layout.ir.edges || []).map(e => [e.id, e]));

  // Merge IR edge metadata (count, labelled, sourceNode, targetNode) into polylines.
  const edgesContentFrame = rawPolylines.map(p => ({ ...p, ...(irEdgesById[p.id] || {}) }));

  // Two-section architecture:
  // Core section — all nodes returned by ELK (ELK repositioned them freely
  //   since standalone was excluded and every node here has at least one edge).
  // Standalone section — hand-positioned below the core's actual ELK bottom.
  //   They never enter ELK so ELK can't shunt them to an arbitrary layer.
  const nodesById = {};
  const fileSize = CW_NAT;
  const CH_STANDALONE = PX.NODE_SIZES.fileNoBullets.h;
  for (const [id, n] of Object.entries(laidNodesById)) {
    nodesById[id] = { id, x: n.x + mainLeft, y: n.y + bandsStartY, w: n.w, h: n.h };
  }

  // Compute actual ELK core bottom (in ir coordinates) to anchor standalone below.
  const coreIrBottom = Object.values(laidNodesById).length > 0
    ? Math.max(...Object.values(laidNodesById).map(n => n.y + n.h))
    : (layout.standaloneStartY || 0);
  const STANDALONE_GAP = 72; // matches bandGapY passed to buildGroupStoryLayoutIr
  const standaloneIrTop = coreIrBottom + STANDALONE_GAP;

  for (const [id, pos] of Object.entries(layout.positions)) {
    if (!layout.standaloneIds.has(id)) continue;
    const relY = pos.y - layout.standaloneStartY;
    nodesById[id] = {
      id,
      x: pos.x + mainLeft,
      y: standaloneIrTop + relY + bandsStartY,
      w: fileSize,
      h: CH_STANDALONE,
    };
  }

  // Translate bandRects; shift standalone bands to match the new standalone section Y.
  const standaloneIrShift = standaloneIrTop - layout.standaloneStartY;
  const bandRects = layout.bandRects.map(b => {
    const isStandaloneBand = b.key === 'standalone' || b.key === 'standalone-sub';
    return {
      ...b,
      x: b.x + mainLeft,
      y: b.y + (isStandaloneBand ? standaloneIrShift : 0) + bandsStartY,
    };
  });
  const edgesTranslated = edgesContentFrame.map(e => _translateEdge(e, mainLeft, bandsStartY));

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
  // Actual content height: max bottom across all placed nodes (both ELK-positioned
  // core nodes and hand-positioned standalone nodes), converted back to ir frame.
  const actualContentBottom = Object.values(nodesById).reduce(
    (m, n) => Math.max(m, n.y - bandsStartY + n.h), layout.canvasH
  );
  const bandsH = actualContentBottom;
  const anchorsStackH = maxAnchorCount > 0
    ? maxAnchorCount * ANCHOR_H + Math.max(0, maxAnchorCount - 1) * ANCHOR_GAP_Y
    : 0;
  // Reserve room below the bands for the hand-routed trunk zone. Without
  // this, the trunk Y (mainBandsBottomY + 20 + lane*10) can overshoot bandsH
  // for groups with many edges, pushing the polyline past the canvas.
  const allEdgeYs = edgesContentFrame.flatMap(e => (e.points || []).map(p => p.y));
  const maxEdgeY = allEdgeYs.length > 0 ? Math.max(...allEdgeYs) : 0;
  const neededH = Math.max(bandsH, maxEdgeY + 20);
  const contentH = Math.max(neededH + USE_ZONE_H, anchorsStackH);
  const stressPreview = PX.components.stressStrip({
    x: LEFT, y: 0, w: CANVAS - 2 * LEFT, stress: story.stress,
  });
  const STRESS_H = stressPreview.h;
  const totalH = bandsStartY + contentH + (STRESS_H ? GAP + STRESS_H : 0) + TOP;
  // Expand W to cover ELK's actual node positions — ELK interactive mode
  // can place nodes slightly beyond the hand-computed CANVAS width.
  const maxNodeRight = Object.values(nodesById).reduce((m, n) => Math.max(m, n.x + n.w), 0);
  const W = Math.max(CANVAS, maxNodeRight + LEFT);
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
  // Natural pixel width so columns stay full-size; the canvas div (overflow:auto)
  // handles horizontal scroll when the layout is wider than the viewport.
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="display:block;width:calc(${W}px * var(--px-zoom, 1));height:calc(${H}px * var(--px-zoom, 1))" data-view="nested" data-natural-w="${W}" data-natural-h="${H}" data-focused-group="${PX.escapeXml(groupId)}">`;
  svg += PX.components.markers();

  // No in-SVG summary banner — the top info bar (#px-top) owns the
  // "focused group + selected file" identity, the description, and the
  // back-to-overview button.

  // Band & cluster labels. Band labels sit above a band's top edge. Cluster
  // headers sit INSIDE the test band, one per test-target column. When a
  // test band has clusters, the outer band label is suppressed (redundant).
  //
  // Standalone taxonomy sub-bands work the same way: ir.js still emits an
  // outer 'standalone' wrapper rect (for backward compat + hit-testing), but
  // each sub-band carries its own 2-line chrome (category name + LLM
  // description). We render the sub-band labels and suppress the outer one
  // to avoid a redundant "STANDALONE (N)" header stacked above them.
  const hasClusters = bandRects.some(b => b.kind === 'cluster');
  const hasStandaloneSubs = bandRects.some(b => b.kind === 'sub-band');
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
    if (band.kind === 'sub-band') {
      // Standalone taxonomy sub-band: 2-line header via bandLabel's optional
      // description. Headroom (26px above y) is already reserved by ir.js's
      // SUB_BAND_GAP_Y between stacked sub-bands.
      svg += PX.components.bandLabel({
        x: band.x,
        y: band.y,
        w: band.w,
        name: band.name,
        count: band.count,
        description: band.description,
      });
      continue;
    }
    if (band.key === 'test' && hasClusters) continue; // cluster headers own this band
    if (band.key === 'standalone') {
      // Render a clickable toggle header regardless of sub-bands. ▼ = expanded,
      // ▶ = collapsed. When sub-bands exist their labels render below this one;
      // when collapsed both the sub-band labels and cards are absent (ir.js
      // emits no positions for standalone files when standaloneCollapsed=true).
      const chevron = standaloneCollapsed ? '▶' : '▼';
      svg += `<g data-toggle-standalone="true" style="cursor:pointer" pointer-events="all">`;
      svg += PX.components.bandLabel({
        x: band.x,
        y: band.y,
        w: band.w,
        name: `${chevron}  ${band.name}`,
        count: band.count,
      });
      svg += `</g>`;
      continue;
    }
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
      y: bandsStartY + contentH + GAP,
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
