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

PX.avoidLabelCollisions = function avoidLabelCollisions(edges, opts = {}) {
  const {
    labelW = (e) => (e.__labelW || 180),
    labelH = (e) => (e.__labelH || 50),
    gap = 8,
    maxIter = 60,
    segments = [],
  } = opts;
  const placed = [];
  const sorted = [...edges].sort((a, b) =>
    ((a.labelY || 0) - (b.labelY || 0)) || ((a.labelX || 0) - (b.labelX || 0))
  );

  const collides = (e, lx, ly, w, h) => {
    const bbox = { x1: lx - w / 2, y1: ly - h / 2, x2: lx + w / 2, y2: ly + h / 2 };
    for (const p of placed) {
      if (p.labelX == null || p.labelY == null) continue;
      const pw = labelW(p), ph = labelH(p);
      const dx = Math.abs(p.labelX - lx);
      const dy = Math.abs(p.labelY - ly);
      if (dx < (pw + w) / 2 + gap && dy < (ph + h) / 2 + gap) return true;
    }
    for (const seg of segments) {
      if (seg.edgeId === e.id) continue;
      if (_overlapsSegment(bbox, seg, gap)) return true;
    }
    return false;
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

  for (const e of sorted) {
    if (e.labelX == null || e.labelY == null) { placed.push(e); continue; }
    const w = labelW(e), h = labelH(e);
    const originalX = e.labelX;
    const originalY = e.labelY;

    const yAtOriginalX = tryYNudge(e, originalX, w, h, originalY);
    if (yAtOriginalX != null) {
      e.labelY = yAtOriginalX;
      placed.push(e);
      continue;
    }

    // Small X-nudge as last resort
    const dx = w / 2 + gap;
    let solved = false;
    for (const off of [-dx, +dx]) {
      const yy = tryYNudge(e, originalX + off, w, h, originalY);
      if (yy != null) {
        e.labelX = originalX + off; e.labelY = yy; solved = true; break;
      }
    }
    if (!solved) e.labelY = originalY;
    placed.push(e);
  }
  return edges;
};

PX.pathD = function pathD(points, r = 5) {
  if (!points || points.length < 2) return '';
  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1], cur = points[i], next = points[i + 1];
    const dx1 = Math.sign(cur.x - prev.x), dy1 = Math.sign(cur.y - prev.y);
    const dx2 = Math.sign(next.x - cur.x), dy2 = Math.sign(next.y - cur.y);
    const len1 = Math.hypot(cur.x - prev.x, cur.y - prev.y);
    const len2 = Math.hypot(next.x - cur.x, next.y - cur.y);
    const rr = Math.min(r, len1 / 2, len2 / 2);
    d += ` L${cur.x - dx1 * rr},${cur.y - dy1 * rr}`;
    d += ` Q${cur.x},${cur.y} ${cur.x + dx2 * rr},${cur.y + dy2 * rr}`;
  }
  const last = points[points.length - 1];
  d += ` L${last.x},${last.y}`;
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
