// Tests for prefxplain/rendering/js/post.js — PX.placeEdgeLabels and
// PX.avoidLabelCollisions. Pure-compute functions (polyline → label coord),
// trivial to test. Run with: node --test tests/test_label_placement.mjs
//
// Loading strategy: post.js is a browser script (window.PX = ...), not an ES
// module. We shim `window` onto globalThis, then evaluate the source via
// new Function() so free `PX` references resolve against globalThis.PX (set
// in the file's first line).

import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const POST_JS = resolve(__dirname, '../prefxplain/rendering/js/post.js');

globalThis.window = globalThis;
new Function(readFileSync(POST_JS, 'utf8'))();
const { placeEdgeLabels, avoidLabelCollisions, detourAroundLabels } = globalThis.PX;

const edge = (id, points) => ({ id, points, source: `${id}.s`, target: `${id}.t` });

// ── placeEdgeLabels: longest-horizontal branch (centerOnPath=false) ──────

test('longest-horizontal: straight horizontal edge → midpoint', () => {
  const [r] = placeEdgeLabels([edge('e1', [{ x: 0, y: 100 }, { x: 200, y: 100 }])]);
  assert.equal(r.labelX, 100);
  assert.equal(r.labelY, 100);
});

test('longest-horizontal: L-shape (long horizontal + short vertical) → label on horizontal', () => {
  const pts = [{ x: 0, y: 100 }, { x: 500, y: 100 }, { x: 500, y: 150 }];
  const [r] = placeEdgeLabels([edge('e1', pts)]);
  assert.equal(r.labelX, 250);
  assert.equal(r.labelY, 100);
});

test('longest-horizontal: Z-shape picks the longer of two horizontals', () => {
  const pts = [
    { x: 0, y: 0 }, { x: 50, y: 0 },       // short horiz (50)
    { x: 50, y: 200 },                     // vertical
    { x: 400, y: 200 },                    // long horiz (350)
  ];
  const [r] = placeEdgeLabels([edge('e1', pts)]);
  assert.equal(r.labelX, 225); // midpoint of the long horiz
  assert.equal(r.labelY, 200);
});

test('longest-horizontal: no horizontal > 40px → falls back to arc-length midpoint', () => {
  // Purely vertical edge — no horizontal segment at all.
  const pts = [{ x: 100, y: 0 }, { x: 100, y: 400 }];
  const [r] = placeEdgeLabels([edge('e1', pts)]);
  assert.equal(r.labelX, 100);
  assert.equal(r.labelY, 200);
});

// ── placeEdgeLabels: centerOnPath branch ────────────────────────────────

test('centerOnPath: straight horizontal → midpoint on line (identical to default)', () => {
  const [r] = placeEdgeLabels(
    [edge('e1', [{ x: 0, y: 100 }, { x: 200, y: 100 }])],
    { centerOnPath: true },
  );
  assert.equal(r.labelX, 100);
  assert.equal(r.labelY, 100);
});

test('centerOnPath: L-shape → arc-length midpoint lands near corner (NOT on longest horiz)', () => {
  // Corner at (500,100). Horiz len=500, vert len=100. Total=600, halfway=300.
  // Walked 300 on horiz segment → landed at (300,100). This is ON the polyline.
  const pts = [{ x: 0, y: 100 }, { x: 500, y: 100 }, { x: 500, y: 200 }];
  const [r] = placeEdgeLabels([edge('e1', pts)], { centerOnPath: true });
  assert.equal(r.labelX, 300);
  assert.equal(r.labelY, 100);
});

test('centerOnPath: Z-shape with peripheral horizontal → midpoint on central VERTICAL', () => {
  // This is the bug-reproducer. Two small horizontals at ends (at top/bottom
  // of canvas) + a long central vertical. The "longest horizontal" strategy
  // picks one of the peripheral horizontals → label flies to the edge. The
  // centerOnPath strategy lands on the central vertical → label sits on the
  // actual arrow path.
  const pts = [
    { x: 0, y: 0 },     { x: 100, y: 0 },    // top horiz   (len 100)
    { x: 100, y: 500 },                       // center vert (len 500)
    { x: 200, y: 500 },                       // bottom horiz (len 100)
  ];
  const [r] = placeEdgeLabels([edge('e1', pts)], { centerOnPath: true });
  // Total = 700, halfway = 350. Walked 100 on top horiz + 250 into vertical.
  // Landing at (100, 250) — on the vertical segment.
  assert.equal(r.labelX, 100);
  assert.equal(r.labelY, 250);
});

test('centerOnPath: no sideways offset on vertical segment (regression for bug)', () => {
  // Single vertical edge. With offsetVertical=true (old code), label X was
  // pushed sideways by labelW/2 + verticalPad. centerOnPath must NOT push.
  const pts = [{ x: 100, y: 0 }, { x: 100, y: 400 }];
  const [r] = placeEdgeLabels(
    [{ ...edge('e1', pts), __labelW: 300 }],
    { centerOnPath: true, labelW: (e) => e.__labelW },
  );
  assert.equal(r.labelX, 100); // stays on the vertical line
  assert.equal(r.labelY, 200);
});

test('centerOnPath: U-shape picks the middle horizontal', () => {
  // Vertical down, horizontal across, vertical up. Halfway lands on horiz.
  const pts = [
    { x: 0, y: 0 }, { x: 0, y: 100 },       // vert (100)
    { x: 300, y: 100 },                      // horiz (300)
    { x: 300, y: 0 },                        // vert (100)
  ];
  const [r] = placeEdgeLabels([edge('e1', pts)], { centerOnPath: true });
  // Total=500, halfway=250. Walked 100 + 150 on horiz → (150, 100).
  assert.equal(r.labelX, 150);
  assert.equal(r.labelY, 100);
});

test('placeEdgeLabels: degenerate <2 points → (0,0)', () => {
  const [r] = placeEdgeLabels([edge('e1', [{ x: 5, y: 5 }])]);
  assert.equal(r.labelX, 0);
  assert.equal(r.labelY, 0);
});

// ── avoidLabelCollisions: basic behavior ────────────────────────────────

test('avoidLabelCollisions: non-overlapping labels pass through unchanged', () => {
  const a = { id: 'a', labelX: 100, labelY: 100, __labelW: 80, __labelH: 30 };
  const b = { id: 'b', labelX: 400, labelY: 100, __labelW: 80, __labelH: 30 };
  const out = avoidLabelCollisions(
    [a, b],
    { labelW: (e) => e.__labelW, labelH: (e) => e.__labelH, gap: 8 },
  );
  const outA = out.find(e => e.id === 'a');
  const outB = out.find(e => e.id === 'b');
  assert.equal(outA.labelY, 100);
  assert.equal(outB.labelY, 100);
});

test('avoidLabelCollisions: overlapping labels get Y-nudged apart', () => {
  const a = { id: 'a', labelX: 100, labelY: 100, __labelW: 80, __labelH: 30 };
  const b = { id: 'b', labelX: 100, labelY: 105, __labelW: 80, __labelH: 30 };
  const out = avoidLabelCollisions(
    [a, b],
    { labelW: (e) => e.__labelW, labelH: (e) => e.__labelH, gap: 8 },
  );
  const outA = out.find(e => e.id === 'a');
  const outB = out.find(e => e.id === 'b');
  // They must no longer overlap: |dy| ≥ (h + gap) when sharing same X
  assert.ok(Math.abs(outA.labelY - outB.labelY) >= 30 + 8 - 0.01);
});

test('avoidLabelCollisions: segment collision pushes label off the segment', () => {
  // Segment at y=100 stretching from x=50 to x=150. A label centered at
  // (100, 100) with h=30 intersects the segment. Expect Y to move away.
  const a = { id: 'a', labelX: 100, labelY: 100, __labelW: 80, __labelH: 30 };
  const segments = [{ x1: 50, y1: 100, x2: 150, y2: 100, edgeId: 'other' }];
  const out = avoidLabelCollisions(
    [a],
    { labelW: (e) => e.__labelW, labelH: (e) => e.__labelH, gap: 8, segments },
  );
  assert.notEqual(out[0].labelY, 100);
});

test('walkPath: when midpoint collides, fallback samples positions ALONG the own polyline', () => {
  // L-shape polyline. Midpoint lands at corner. A foreign segment blocks the
  // midpoint region. walkPath=true must find another point ON the polyline —
  // NOT an off-path free-float y-nudge position.
  const pts = [
    { x: 0, y: 100 }, { x: 1000, y: 100 },
    { x: 1000, y: 1100 },
  ];
  const ownSegs = [];
  for (let i = 0; i < pts.length - 1; i++) {
    ownSegs.push({
      x1: pts[i].x, y1: pts[i].y,
      x2: pts[i + 1].x, y2: pts[i + 1].y,
      edgeId: 'e1',
    });
  }
  // Foreign segment that blocks the arc-length midpoint area (~x=500,y=100 on
  // the horizontal part + some band around the corner).
  const foreignSegs = [
    { x1: 400, y1: 0, x2: 400, y2: 200, edgeId: 'blocker' },
  ];
  const edge = {
    id: 'e1', points: pts,
    labelX: 500, labelY: 100,
    __labelW: 200, __labelH: 50,
  };
  const out = avoidLabelCollisions(
    [edge],
    {
      labelW: (e) => e.__labelW, labelH: (e) => e.__labelH, gap: 18,
      segments: [...ownSegs, ...foreignSegs],
      walkPath: true,
    },
  );
  const r = out[0];
  // Must be on the polyline: either horizontal (y=100, x in [0, 1000]) OR
  // vertical (x=1000, y in [100, 1100]).
  const onHoriz = r.labelY === 100 && r.labelX >= 0 && r.labelX <= 1000;
  const onVert  = r.labelX === 1000 && r.labelY >= 100 && r.labelY <= 1100;
  assert.ok(onHoriz || onVert, `label (${r.labelX},${r.labelY}) not on polyline`);
});

test('walkPath: if every polyline position collides, keep midpoint on-path (never free-float)', () => {
  // Pathological: polyline fully blocked by foreign segments. Label must
  // still sit on the polyline (accept overlap — rect fill masks the line).
  const pts = [{ x: 0, y: 100 }, { x: 200, y: 100 }];
  const ownSegs = [{ x1: 0, y1: 100, x2: 200, y2: 100, edgeId: 'e1' }];
  const foreignSegs = [{ x1: 0, y1: 100, x2: 200, y2: 100, edgeId: 'blocker' }];
  const edge = {
    id: 'e1', points: pts,
    labelX: 100, labelY: 100,
    __labelW: 180, __labelH: 50,
  };
  const out = avoidLabelCollisions(
    [edge],
    {
      labelW: (e) => e.__labelW, labelH: (e) => e.__labelH, gap: 8,
      segments: [...ownSegs, ...foreignSegs],
      walkPath: true,
    },
  );
  // Label still on horizontal line y=100 (foreign shares the trunk so own
  // coverage kicks in and it doesn't even register as collision — label
  // stays at the computed arc-length midpoint).
  assert.equal(out[0].labelY, 100);
  assert.ok(out[0].labelX >= 0 && out[0].labelX <= 200);
});

test('cardRects: label on polyline that passes through a card walks to a position outside the card', () => {
  // Polyline passes through a hero card (x=100..300, y=200..400). Initial
  // midpoint is inside the card. walkPath must find a position outside.
  const pts = [{ x: 0, y: 300 }, { x: 1000, y: 300 }];
  const ownSegs = [{ x1: 0, y1: 300, x2: 1000, y2: 300, edgeId: 'e1' }];
  const edge = {
    id: 'e1', points: pts,
    labelX: 500, labelY: 300,
    __labelW: 180, __labelH: 50,
  };
  const cardRects = [{ x1: 420, y1: 275, x2: 580, y2: 325 }]; // covers midpoint
  const out = avoidLabelCollisions(
    [edge],
    {
      labelW: (e) => e.__labelW, labelH: (e) => e.__labelH, gap: 8,
      segments: ownSegs, cardRects, walkPath: true,
    },
  );
  const r = out[0];
  // Label must not overlap the card rect (with label bbox ±w/2, ±h/2).
  const bbox = { x1: r.labelX - 90, y1: r.labelY - 25, x2: r.labelX + 90, y2: r.labelY + 25 };
  for (const c of cardRects) {
    const overlaps = !(bbox.x2 < c.x1 || bbox.x1 > c.x2 || bbox.y2 < c.y1 || bbox.y1 > c.y2);
    assert.equal(overlaps, false, `label bbox overlaps card`);
  }
});

test('detourAroundLabels: horizontal segment passing through a bbox routes around (above)', () => {
  // Segment (0,100)→(500,100). Bbox (200,80)→(300,120). Expanded by gap=12:
  // (188,68)→(312,132). The detour should go above (y=68) since distance to
  // top and bottom are equal, the implementation picks top on tie.
  const pts = [{ x: 0, y: 100 }, { x: 500, y: 100 }];
  const bboxes = [{ x1: 200, y1: 80, x2: 300, y2: 120 }];
  const out = detourAroundLabels(pts, bboxes, 12);
  assert.deepEqual(out, [
    { x: 0, y: 100 },
    { x: 188, y: 100 },
    { x: 188, y: 68 },
    { x: 312, y: 68 },
    { x: 312, y: 100 },
    { x: 500, y: 100 },
  ]);
});

test('detourAroundLabels: vertical segment passing through a bbox routes around (left)', () => {
  // Segment (200,0)→(200,500). Bbox (180,200)→(220,300). gap=12 → expanded
  // (168,188)→(232,312). x=200 is equidistant to 168 and 232 → picks left.
  const pts = [{ x: 200, y: 0 }, { x: 200, y: 500 }];
  const bboxes = [{ x1: 180, y1: 200, x2: 220, y2: 300 }];
  const out = detourAroundLabels(pts, bboxes, 12);
  assert.deepEqual(out, [
    { x: 200, y: 0 },
    { x: 200, y: 188 },
    { x: 168, y: 188 },
    { x: 168, y: 312 },
    { x: 200, y: 312 },
    { x: 200, y: 500 },
  ]);
});

test('detourAroundLabels: segment that misses the bbox passes through unchanged', () => {
  const pts = [{ x: 0, y: 100 }, { x: 500, y: 100 }];
  const bboxes = [{ x1: 200, y1: 200, x2: 300, y2: 400 }]; // far below segment
  const out = detourAroundLabels(pts, bboxes, 12);
  assert.deepEqual(out, pts);
});

test('detourAroundLabels: empty bbox list returns input unchanged', () => {
  const pts = [{ x: 0, y: 100 }, { x: 500, y: 100 }];
  assert.equal(detourAroundLabels(pts, [], 12), pts);
});

test('detourAroundLabels: multiple bboxes on the same segment get a single UNION detour', () => {
  // Two labels in a row along a horizontal edge. Union detour goes around
  // both at once (not two separate bumps that could conflict).
  const pts = [{ x: 0, y: 100 }, { x: 1000, y: 100 }];
  const bboxes = [
    { x1: 200, y1: 90, x2: 300, y2: 110 },
    { x1: 600, y1: 90, x2: 700, y2: 110 },
  ];
  const out = detourAroundLabels(pts, bboxes, 10);
  // Env: pass [190, 710], cross [80, 120]. Detour at y=80 (top) since |100-80|
  // < |100-120|+ties-to-top. A outside (0 < 190) → walk to (190, 100) first.
  // B outside (1000 > 710) → end with (710, 100).
  assert.deepEqual(out, [
    { x: 0, y: 100 },
    { x: 190, y: 100 },
    { x: 190, y: 80 },
    { x: 710, y: 80 },
    { x: 710, y: 100 },
    { x: 1000, y: 100 },
  ]);
});

test('detourAroundLabels: partial overlap — segment starts INSIDE the bbox, turns immediately at start', () => {
  // Segment (732, 1080) → (732, 1272), vertical going DOWN. Bbox (645.2,1077,
  // 818.8,1127), gap=12 → env pass [1065, 1139], cross [633.2, 830.8].
  // a.y=1080 is INSIDE env pass range (1065..1139). Detour must not walk
  // backward to 1065 — it must turn sideways immediately at y=1080.
  const pts = [{ x: 732, y: 1080 }, { x: 732, y: 1272 }];
  const bboxes = [{ x1: 645.2, y1: 1077, x2: 818.8, y2: 1127 }];
  const out = detourAroundLabels(pts, bboxes, 12);
  assert.deepEqual(out, [
    { x: 732, y: 1080 },      // a — immediate turn (no backward walk)
    { x: 633.2, y: 1080 },    // turn left to detour column
    { x: 633.2, y: 1139 },    // down along detour column past envelope
    { x: 732, y: 1139 },      // back to original x
    { x: 732, y: 1272 },      // b
  ]);
});

test('avoidLabelCollisions: shared-trunk regression — label stays on-path when foreign segment is collinear with own segment', () => {
  // Bug repro (codex-diagnosed). Edge "Tests → Interactive Diagram" polyline
  // is 402,192 → 402,240 → 172,240 → 172,852 — a vertical trunk at x=172.
  // placeEdgeLabels(centerOnPath) puts the label at (172, 407) ON the trunk.
  // Many other edges share that same x=172 trunk (fan-in on Tests).
  // The OLD collision detector saw every foreign segment at x=172 as an
  // obstacle and Y-nudged the label up to y=135 (off the polyline).
  // The FIX: if one of MY own segments covers the label bbox, foreign
  // segments overlapping the same bbox are shared trunk, not obstacles.
  const edgePts = [
    { x: 402, y: 192 }, { x: 402, y: 240 },
    { x: 172, y: 240 }, { x: 172, y: 852 },
  ];
  const ownSegs = [];
  for (let i = 0; i < edgePts.length - 1; i++) {
    ownSegs.push({
      x1: edgePts[i].x, y1: edgePts[i].y,
      x2: edgePts[i + 1].x, y2: edgePts[i + 1].y,
      edgeId: 'tests-to-id',
    });
  }
  // Four foreign edges sharing the x=172 trunk at various y ranges (fan-in).
  const foreignSegs = [
    { x1: 172, y1: 280, x2: 172, y2: 850, edgeId: 'other1' },
    { x1: 172, y1: 300, x2: 172, y2: 820, edgeId: 'other2' },
    { x1: 172, y1: 320, x2: 172, y2: 800, edgeId: 'other3' },
    { x1: 172, y1: 340, x2: 172, y2: 780, edgeId: 'other4' },
  ];
  const label = {
    id: 'tests-to-id', labelX: 172, labelY: 407,
    __labelW: 180, __labelH: 50,
  };
  const out = avoidLabelCollisions(
    [label],
    {
      labelW: (e) => e.__labelW,
      labelH: (e) => e.__labelH,
      gap: 18,
      segments: [...ownSegs, ...foreignSegs],
    },
  );
  assert.equal(out[0].labelX, 172);
  assert.equal(out[0].labelY, 407);
});
