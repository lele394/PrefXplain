// post.js — post-processing on the ELK layout output.
//
// Three passes, each pure (input → output):
//
//   1. extractEdgePolylines(laid)
//      Turns ELK's section-based edge output into a simple list of polylines
//      { id, source, target, points: [{x,y}, ...] }. All downstream code
//      works on polylines, not ELK's raw shape.
//
//   2. detectBus(edges, nodesById)
//      Simplifies N parallel edges into a "bus" (shared trunk + split) when
//      they share a source AND their targets sit in the same row band, or
//      mirror for fan-in (same target, sources in one row band). Motivated
//      by the SPOF `graph.py`: 15 arrows into one target should visually
//      converge, not fan out like a comb.
//
//   3. placeEdgeLabels(edges)
//      For each edge, finds the longest horizontal segment and stores its
//      midpoint as { labelX, labelY }. Used by the SVG renderer to position
//      edge labels cleanly (not on a corner, not overlapping a node).
//
// All labels stay on this side — we never ask ELK for inline labels.

window.PX = window.PX || {};

const BUS_MIN = 3;         // min # of parallel edges to collapse into a bus
const BUS_FUNNEL_GAP = 24; // px above/below target for the shared funnel Y

function _absolutePath(containerStack, point) {
  let x = point.x, y = point.y;
  for (const c of containerStack) { x += (c.x || 0); y += (c.y || 0); }
  return { x, y };
}

function _collectNodes(root) {
  // Walk ELK's compound tree, return flat nodesById with absolute coords +
  // a parent chain so we can translate section coords to the root frame.
  const nodesById = {};
  const walk = (node, ancestors) => {
    const abs = { x: (node.x || 0), y: (node.y || 0), w: (node.width || 0), h: (node.height || 0) };
    for (const a of ancestors) { abs.x += (a.x || 0); abs.y += (a.y || 0); }
    if (node.id !== 'root') nodesById[node.id] = { id: node.id, ...abs };
    for (const c of (node.children || [])) walk(c, [...ancestors, node]);
  };
  walk(root, []);
  return nodesById;
}

function _findEdgeContainer(root, edgeId, stack = []) {
  for (const e of (root.edges || [])) if (e.id === edgeId) return stack;
  for (const c of (root.children || [])) {
    const s = _findEdgeContainer(c, edgeId, [...stack, c]);
    if (s) return s;
  }
  return null;
}

// Walk ELK's compound tree, harvest each edge's first label position, and
// translate its (x, y) from container-relative to root-frame coords. Returns
// an object keyed by edge id → { x, y, width, height } of the label's
// top-left corner in root coords. ELK only populates x/y for edges that
// had a label declared in the IR and that the router had room for.
PX.extractEdgeLabels = function extractEdgeLabels(laidRoot) {
  const byId = {};
  const walk = (container, ancestors) => {
    for (const e of (container.edges || [])) {
      const lbl = (e.labels || [])[0];
      if (!lbl) continue;
      let x = lbl.x || 0, y = lbl.y || 0;
      for (const a of ancestors) { x += (a.x || 0); y += (a.y || 0); }
      byId[e.id] = {
        x, y,
        width: lbl.width || 0,
        height: lbl.height || 0,
      };
    }
    for (const c of (container.children || [])) walk(c, [...ancestors, c]);
  };
  walk(laidRoot, []);
  return byId;
};

PX.extractEdgePolylines = function extractEdgePolylines(laidRoot) {
  const results = [];
  const walkEdges = (container, ancestors) => {
    for (const e of (container.edges || [])) {
      // ELK may emit container-relative coords; translate to root frame.
      const sections = e.sections || [];
      if (!sections.length) continue;
      const sec = sections[0];
      const pts = [];
      const tr = (p) => {
        let x = p.x, y = p.y;
        for (const a of ancestors) { x += (a.x || 0); y += (a.y || 0); }
        return { x, y };
      };
      pts.push(tr(sec.startPoint));
      for (const b of (sec.bendPoints || [])) pts.push(tr(b));
      pts.push(tr(sec.endPoint));
      results.push({
        id: e.id,
        source: (e.sources && e.sources[0]) || null,
        target: (e.targets && e.targets[0]) || null,
        points: pts,
        raw: e,
      });
    }
    for (const c of (container.children || [])) walkEdges(c, [...ancestors, c]);
  };
  walkEdges(laidRoot, []);
  return results;
};

function _sourceNodeId(portId) {
  if (!portId) return null;
  const dot = portId.lastIndexOf('.');
  return dot > 0 ? portId.slice(0, dot) : portId;
}

PX.detectBus = function detectBus(edges, nodesById) {
  // A "hub" is any node with >= BUS_MIN edges pointing to it (fan-in) OR
  // from it (fan-out). We collapse those edges around a shared funnel Y
  // placed just above (fan-in) or just below (fan-out) the hub, so the
  // arrows converge into / diverge from a single trunk.
  const bySource = {};
  const byTarget = {};
  for (const e of edges) {
    const s = _sourceNodeId(e.source);
    const t = _sourceNodeId(e.target);
    if (s) (bySource[s] = bySource[s] || []).push(e);
    if (t) (byTarget[t] = byTarget[t] || []).push(e);
  }
  const annotated = edges.map(e => ({ ...e, bus: null }));
  const edgeById = Object.fromEntries(annotated.map(e => [e.id, e]));
  const markBus = (group, direction, pivotId) => {
    const unbussed = group.filter(e => !edgeById[e.id].bus);
    if (unbussed.length < BUS_MIN) return;
    const pivot = nodesById[pivotId];
    if (!pivot) return;
    const trunkX = pivot.x + pivot.w / 2;
    const trunkY = direction === 'fanin'
      ? pivot.y - BUS_FUNNEL_GAP
      : pivot.y + pivot.h + BUS_FUNNEL_GAP;
    for (const e of unbussed) {
      edgeById[e.id].bus = { direction, trunkX, trunkY, size: unbussed.length, hub: pivotId };
    }
  };
  for (const tid in byTarget) markBus(byTarget[tid], 'fanin', tid);
  for (const sid in bySource) markBus(bySource[sid], 'fanout', sid);
  return annotated;
};

// Two placement strategies, selected per call:
//
//   centerOnPath=false (default, used by nested overview/detail):
//     pick the longest horizontal segment > 40px, label sits on its midpoint.
//     Stable when edges have a clear "main run" horizontal. Falls back to
//     arc-length midpoint if no qualifying horizontal exists.
//
//   centerOnPath=true (used by group-map):
//     always use the arc-length midpoint of the polyline. Guarantees the
//     label sits ON the traversal path — even when that midpoint lands on
//     a vertical segment. The label's rect (fill=bg) masks the line locally,
//     which reads as "label on the arrow". Previously this branch applied
//     a sideways offset on vertical segments; that pushed labels into empty
//     canvas and was the root cause of the "floating labels" bug.
PX.placeEdgeLabels = function placeEdgeLabels(edges, opts = {}) {
  const { centerOnPath = false } = opts;
  return edges.map(e => {
    const pts = e.points || [];
    if (pts.length < 2) return { ...e, labelX: 0, labelY: 0 };
    const segments = [];
    let totalLen = 0;
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1];
      const dx = b.x - a.x, dy = b.y - a.y;
      const len = Math.hypot(dx, dy);
      segments.push({ a, b, len, horizontal: Math.abs(dy) <= 1, vertical: Math.abs(dx) <= 1 });
      totalLen += len;
    }

    if (!centerOnPath) {
      let bestIdx = -1, maxL = -1;
      for (let i = 0; i < segments.length; i++) {
        if (segments[i].horizontal && segments[i].len > maxL) {
          maxL = segments[i].len; bestIdx = i;
        }
      }
      if (bestIdx >= 0 && maxL > 40) {
        const s = segments[bestIdx];
        return { ...e, labelX: (s.a.x + s.b.x) / 2, labelY: s.a.y };
      }
    }

    const halfway = totalLen / 2;
    let walked = 0;
    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      if (walked + seg.len >= halfway) {
        const ratio = seg.len > 0 ? (halfway - walked) / seg.len : 0.5;
        return {
          ...e,
          labelX: seg.a.x + (seg.b.x - seg.a.x) * ratio,
          labelY: seg.a.y + (seg.b.y - seg.a.y) * ratio,
        };
      }
      walked += seg.len;
    }
    return { ...e, labelX: pts[0].x, labelY: pts[0].y };
  });
};

function _overlapsSegment(bbox, seg, gap) {
  if (seg.y1 === seg.y2) {
    const y = seg.y1;
    if (y < bbox.y1 - gap || y > bbox.y2 + gap) return false;
    const segMinX = Math.min(seg.x1, seg.x2);
    const segMaxX = Math.max(seg.x1, seg.x2);
    return segMaxX >= bbox.x1 - gap && segMinX <= bbox.x2 + gap;
  }
  if (seg.x1 === seg.x2) {
    const x = seg.x1;
    if (x < bbox.x1 - gap || x > bbox.x2 + gap) return false;
    const segMinY = Math.min(seg.y1, seg.y2);
    const segMaxY = Math.max(seg.y1, seg.y2);
    return segMaxY >= bbox.y1 - gap && segMinY <= bbox.y2 + gap;
  }
  return false;
}

// Walk along an edge's own polyline and return the point at fractional arc
// length t in [0, 1]. Guarantees the returned point sits ON the polyline.
function _pointAtT(points, t) {
  if (!points || points.length < 2) return null;
  const lens = [];
  let total = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const dx = points[i + 1].x - points[i].x;
    const dy = points[i + 1].y - points[i].y;
    const len = Math.hypot(dx, dy);
    lens.push(len);
    total += len;
  }
  if (total === 0) return { x: points[0].x, y: points[0].y };
  const target = Math.max(0, Math.min(total, total * t));
  let walked = 0;
  for (let i = 0; i < lens.length; i++) {
    if (walked + lens[i] >= target) {
      const ratio = lens[i] > 0 ? (target - walked) / lens[i] : 0;
      return {
        x: points[i].x + (points[i + 1].x - points[i].x) * ratio,
        y: points[i].y + (points[i + 1].y - points[i].y) * ratio,
      };
    }
    walked += lens[i];
  }
  const last = points[points.length - 1];
  return { x: last.x, y: last.y };
}

PX.avoidLabelCollisions = function avoidLabelCollisions(edges, opts = {}) {
  const {
    labelW = (e) => (e.__labelW || 180),
    labelH = (e) => (e.__labelH || 50),
    gap = 8,
    maxIter = 60,
    segments = [],
    walkPath = false,
    cardRects = [],
  } = opts;
  // Inputs are never mutated: each placed edge is a fresh object with
  // updated labelX/labelY. Returned array order mirrors the input.
  const placed = [];
  const byId = new Map();
  const sorted = [...edges].sort((a, b) =>
    ((a.labelY || 0) - (b.labelY || 0)) || ((a.labelX || 0) - (b.labelX || 0))
  );

  const collides = (e, lx, ly, w, h) => {
    const bbox = { x1: lx - w / 2, y1: ly - h / 2, x2: lx + w / 2, y2: ly + h / 2 };
    for (const c of cardRects) {
      if (!(bbox.x2 < c.x1 || bbox.x1 > c.x2 || bbox.y2 < c.y1 || bbox.y1 > c.y2)) {
        return true;
      }
    }
    for (const p of placed) {
      if (p.labelX == null || p.labelY == null) continue;
      const pw = labelW(p), ph = labelH(p);
      const dx = Math.abs(p.labelX - lx);
      const dy = Math.abs(p.labelY - ly);
      if (dx < (pw + w) / 2 + gap && dy < (ph + h) / 2 + gap) return true;
    }
    const ownCovers = segments.some(s => s.edgeId === e.id && _overlapsSegment(bbox, s, 0));
    for (const seg of segments) {
      if (seg.edgeId === e.id) continue;
      if (_overlapsSegment(bbox, seg, gap)) {
        if (ownCovers) continue;
        return true;
      }
    }
    return false;
  };

  const tryWalkPath = (e, w, h) => {
    const pts = e.points;
    if (!pts || pts.length < 2) return null;
    const tries = [0.5];
    for (let i = 1; i <= 16; i++) {
      const d = i * 0.025;
      tries.push(0.5 + d, 0.5 - d);
    }
    for (const t of tries) {
      if (t < 0.1 || t > 0.9) continue;
      const p = _pointAtT(pts, t);
      if (!p) continue;
      if (!collides(e, p.x, p.y, w, h)) return p;
    }
    return null;
  };
  const tryYNudge = (e, lx, w, h, originalY) => {
    if (!collides(e, lx, originalY, w, h)) return originalY;
    for (let i = 0; i < maxIter; i++) {
      const step = Math.ceil((i + 1) / 2) * (h + gap);
      const yy = originalY + (i % 2 === 0 ? step : -step);
      if (!collides(e, lx, yy, w, h)) return yy;
    }
    return null;
  };

  const emit = (src, labelX, labelY) => {
    const copy = { ...src, labelX, labelY };
    placed.push(copy);
    byId.set(src.id, copy);
  };

  for (const e of sorted) {
    if (e.labelX == null || e.labelY == null) { emit(e, e.labelX, e.labelY); continue; }
    const w = labelW(e), h = labelH(e);
    const originalX = e.labelX;
    const originalY = e.labelY;

    if (walkPath) {
      if (!collides(e, originalX, originalY, w, h)) {
        emit(e, originalX, originalY);
        continue;
      }
      const p = tryWalkPath(e, w, h);
      if (p) { emit(e, p.x, p.y); continue; }
      emit(e, originalX, originalY);
      continue;
    }

    const yAtOriginalX = tryYNudge(e, originalX, w, h, originalY);
    if (yAtOriginalX != null) {
      emit(e, originalX, yAtOriginalX);
      continue;
    }

    const dx = w / 2 + gap;
    let solved = false;
    for (const off of [-dx, +dx]) {
      const yy = tryYNudge(e, originalX + off, w, h, originalY);
      if (yy != null) {
        emit(e, originalX + off, yy); solved = true; break;
      }
    }
    if (!solved) emit(e, originalX, originalY);
  }
  // Return results in input order (callers rely on stable positional mapping).
  return edges.map(e => byId.get(e.id) || e);
};

// Detour an orthogonal polyline around foreign label bboxes. For each segment
// in the input polyline, find all bboxes it crosses, compute a UNION envelope
// of those bboxes, and route a SINGLE bypass around the envelope. No iterative
// per-bbox processing: this prevents the "cascade zigzag" when several labels
// cluster in a fan-in corridor (each iteration's detour waypoints would land
// inside the next bbox, triggering more detours and accumulating bends).
//
// Handles partial overlap correctly: if a segment endpoint is inside an
// envelope, the detour turns sideways immediately at that endpoint rather
// than trying to "enter" at the envelope boundary (which would walk backward).
//
// Returns a new points array. Safe to call with empty bboxes (returns input).
PX.detourAroundLabels = function detourAroundLabels(points, bboxes, gap = 12, opts = {}) {
  const { preserveEndSegments = false } = opts;
  if (!points || points.length < 2 || !bboxes || bboxes.length === 0) return points;
  const out = [points[0]];
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    // preserveEndSegments=true: keep the first and last segments untouched so
    // port connections stay clean AND the last segment is long enough for the
    // arrowhead's tailTrim sleeve (~35px for a 5px stroke). Detouring those
    // segments can shorten them and push the marker into the card's opaque
    // fill, which hides the arrowhead entirely.
    if (preserveEndSegments && (i === 0 || i === points.length - 2)) {
      out.push(b);
      continue;
    }
    for (const p of _detourSegment(a, b, bboxes, gap)) out.push(p);
  }
  return out;
};

// For one orthogonal segment (a, b), return the list of waypoints (including
// b) that route around every bbox the segment crosses. If no bbox is crossed,
// returns [b].
function _detourSegment(a, b, bboxes, gap) {
  const isH = Math.abs(a.y - b.y) <= 1;
  const isV = Math.abs(a.x - b.x) <= 1;
  if (!isH && !isV) return [b];

  // Map each bbox into the segment's reference frame: "pass" axis = the axis
  // the segment travels on, "cross" axis = the constant axis.
  const crossed = [];
  for (const bb of bboxes) {
    const B = {
      pass1: (isH ? bb.x1 : bb.y1) - gap,
      pass2: (isH ? bb.x2 : bb.y2) + gap,
      cross1: (isH ? bb.y1 : bb.x1) - gap,
      cross2: (isH ? bb.y2 : bb.x2) + gap,
    };
    const crossCoord = isH ? a.y : a.x;
    const passA = isH ? a.x : a.y;
    const passB = isH ? b.x : b.y;
    if (crossCoord > B.cross1 && crossCoord < B.cross2
        && Math.max(passA, passB) > B.pass1
        && Math.min(passA, passB) < B.pass2) {
      crossed.push(B);
    }
  }
  if (crossed.length === 0) return [b];

  const passA = isH ? a.x : a.y;
  const passB = isH ? b.x : b.y;
  const crossCoord = isH ? a.y : a.x;

  // Envelope of all crossed bboxes.
  const envPass1 = Math.min(...crossed.map(c => c.pass1));
  const envPass2 = Math.max(...crossed.map(c => c.pass2));
  const envCross1 = Math.min(...crossed.map(c => c.cross1));
  const envCross2 = Math.max(...crossed.map(c => c.cross2));

  // Choose detour side (closer of top/bottom or left/right).
  const detourCross = Math.abs(crossCoord - envCross1) <= Math.abs(crossCoord - envCross2)
    ? envCross1 : envCross2;

  const dir = passB >= passA ? 1 : -1;
  // Clip entry/exit pass-axis coords to the segment's own range and the
  // envelope's pass range. If the endpoint is already inside the envelope,
  // the entry (or exit) stays at the endpoint's coord — no backward walk.
  const entryPass = dir > 0 ? Math.max(passA, envPass1) : Math.min(passA, envPass2);
  const exitPass  = dir > 0 ? Math.min(passB, envPass2) : Math.max(passB, envPass1);

  const mk = (p, c) => isH ? { x: p, y: c } : { x: c, y: p };

  const waypoints = [];
  // If A is OUTSIDE the envelope pass-range, walk along cross-axis to the
  // envelope boundary before turning. Inside → turn immediately at A.
  const aOutside = (dir > 0 && passA < envPass1) || (dir < 0 && passA > envPass2);
  if (aOutside) waypoints.push(mk(entryPass, crossCoord));
  waypoints.push(mk(entryPass, detourCross));
  waypoints.push(mk(exitPass, detourCross));
  const bOutside = (dir > 0 && passB > envPass2) || (dir < 0 && passB < envPass1);
  if (bOutside) waypoints.push(mk(exitPass, crossCoord));
  waypoints.push(b);
  return waypoints;
}

PX.pathD = function pathD(points, r = 5, tailTrim = 0) {
  if (!points || points.length < 2) return '';
  // tailTrim pulls the last point back along its direction. Pairs with a
  // marker whose refX=0 (base-at-endpoint): the stroke ends at the arrow-
  // head's BASE, the arrowhead triangle extends forward to the original
  // endpoint. Visually: clean boundary between shaft and arrowhead, no
  // stroke visible past the arrowhead tip or "under" the triangle.
  let endPt = points[points.length - 1];
  if (tailTrim > 0 && points.length >= 2) {
    const prev = points[points.length - 2];
    const dx = endPt.x - prev.x, dy = endPt.y - prev.y;
    const len = Math.hypot(dx, dy);
    if (len > tailTrim + 1) {
      const ratio = (len - tailTrim) / len;
      endPt = { x: prev.x + dx * ratio, y: prev.y + dy * ratio };
    }
  }
  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1], cur = points[i];
    // Clamp rounding radius by the actual NEXT segment length — which might
    // be the trimmed final segment.
    const next = (i === points.length - 2) ? endPt : points[i + 1];
    const dx1 = Math.sign(cur.x - prev.x), dy1 = Math.sign(cur.y - prev.y);
    const dx2 = Math.sign(next.x - cur.x), dy2 = Math.sign(next.y - cur.y);
    const len1 = Math.hypot(cur.x - prev.x, cur.y - prev.y);
    const len2 = Math.hypot(next.x - cur.x, next.y - cur.y);
    const rr = Math.min(r, len1 / 2, len2 / 2);
    d += ` L${cur.x - dx1 * rr},${cur.y - dy1 * rr}`;
    d += ` Q${cur.x},${cur.y} ${cur.x + dx2 * rr},${cur.y + dy2 * rr}`;
  }
  d += ` L${endPt.x},${endPt.y}`;
  return d;
};

PX.buildBusTrunkPath = function buildBusTrunkPath(edge, nodesById) {
  if (!edge || !edge.bus) return edge.points;
  const src = nodesById[_sourceNodeId(edge.source)];
  const tgt = nodesById[_sourceNodeId(edge.target)];
  if (!src || !tgt) return edge.points;
  const { direction, trunkX, trunkY } = edge.bus;
  const srcAnchor = { x: src.x + src.w / 2, y: src.y + src.h };
  const tgtAnchor = { x: tgt.x + tgt.w / 2, y: tgt.y };
  if (direction === 'fanin') {
    return [srcAnchor, { x: srcAnchor.x, y: trunkY }, { x: trunkX, y: trunkY }, { x: trunkX, y: tgtAnchor.y }];
  }
  return [{ x: trunkX, y: srcAnchor.y }, { x: trunkX, y: trunkY }, { x: tgtAnchor.x, y: trunkY }, tgtAnchor];
};

PX._collectNodes = _collectNodes;
