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
const { placeEdgeLabels, avoidLabelCollisions } = globalThis.PX;

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
