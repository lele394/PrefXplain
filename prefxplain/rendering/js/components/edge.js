// components/edge.js — SVG string for one edge.
//
// Reads the polyline shape (bus-aware: uses buildBusTrunkPath when edge.bus
// is set), the state color, and optional label text. Returns an <g>..</g>
// block that can be concatenated into the main SVG.

window.PX = window.PX || {};
PX.components = PX.components || {};

PX.components.edge = function edgeSvg(edge, opts = {}) {
  const {
    nodesById,
    state = 'normal',
    label = null,        // string (simple) OR { sourceName, sourceColor, count, targetName, targetColor } (3-line colored)
    thick = false,
    opacity = null,
    markerSuffix = '',
    reverseArrow = false, // when true, arrowhead lands on the source (importer) instead of target (importee)
    pathOnly = false,    // emit the <path> only, skip the label
    labelOnly = false,   // emit the label <g> only, skip the <path>
  } = opts;
  const T = PX.T;
  const color = PX.stateColor(state);
  const rawPts = edge.bus ? PX.buildBusTrunkPath(edge, nodesById || {}) : edge.points;
  if (!rawPts || rawPts.length < 2) return '';
  const pts = reverseArrow ? [...rawPts].reverse() : rawPts;
  const strokeW = thick
    ? Math.max(1.8, Math.min(5, 1.4 + (edge.count || 1) * 0.55))
    : (state === 'normal' ? 1 : 1.6);
  // Markers use markerUnits="strokeWidth" and a viewBox width of 10. Actual
  // marker length in user units = markerWidth_attr * strokeWidth. Matches
  // the refX=0 markers: stroke ends at arrowhead base, triangle extends
  // forward to the original polyline endpoint.
  const MARKER_WIDTH_ATTR = 7;
  const tailTrim = MARKER_WIDTH_ATTR * strokeW;
  const d = PX.pathD(pts, 5, tailTrim);
  const eff = opacity != null ? opacity : (state === 'faded' ? 0.12 : state === 'normal' ? 0.55 : 0.95);
  const markerId = `arr-${state}${markerSuffix}`;
  let out = labelOnly
    ? ''
    : `<path d="${d}" fill="none" stroke="${color}" stroke-width="${strokeW}" opacity="${eff}" marker-end="url(#${markerId})" style="transition:all 200ms"/>`;
  if (label && !pathOnly) {
    let lx = edge.labelX, ly = edge.labelY;
    if (lx == null || ly == null) {
      lx = (pts[0].x + pts[pts.length - 1].x) / 2;
      ly = (pts[0].y + pts[pts.length - 1].y) / 2;
    }
    // Faded state dims text/stroke AND drops the source/target accent colors
    // to a uniform neutral grey. Keeping the vivid group colors at low opacity
    // made dimmed labels still visually compete with the highlighted edges —
    // the "les labels restent colorés" regression.
    const faded = state === 'faded';
    const textOpacity = faded ? 0.5 : 1;
    const strokeOpacity = faded ? 0.5 : 1;
    const srcFill = faded ? T.inkMuted : (label.sourceColor || color);
    const tgtFill = faded ? T.inkMuted : (label.targetColor || color);
    const simpleFill = faded ? T.inkMuted : color;
    if (typeof label === 'object' && label.sourceName && label.targetName) {
      const line1 = `[${label.sourceName}]`;
      const line2 = `imports ${label.count}\u00d7`;
      const line3 = `[${label.targetName}]`;
      // Width/height/padding must match ir.js → _labelDims. The padding is
      // sized to cover the thick-stroke shoulder of aggregate edges.
      const charW1 = 8.2, charW2 = 7.6;
      const w = Math.max(line1.length * charW1, line2.length * charW2, line3.length * charW1) + 36;
      const h = 56;
      const top = ly - h / 2;
      out += `<g pointer-events="none">`
        +  `<rect x="${lx - w / 2}" y="${top}" width="${w}" height="${h}" fill="${T.bg}" stroke="${color}" stroke-width="1" stroke-opacity="${strokeOpacity}" rx="8"/>`
        +  `<text x="${lx}" y="${top + 17}" font-family="${T.mono}" font-size="11" fill="${srcFill}" fill-opacity="${textOpacity}" text-anchor="middle" font-weight="700">${PX.escapeXml(line1)}</text>`
        +  `<text x="${lx}" y="${top + 31}" font-family="${T.mono}" font-size="10" fill="${T.inkMuted}" fill-opacity="${textOpacity}" text-anchor="middle">${PX.escapeXml(line2)}</text>`
        +  `<text x="${lx}" y="${top + 45}" font-family="${T.mono}" font-size="11" fill="${tgtFill}" fill-opacity="${textOpacity}" text-anchor="middle" font-weight="700">${PX.escapeXml(line3)}</text>`
        +  `</g>`;
    } else {
      const txt = PX.escapeXml(String(label));
      const w = txt.length * 6.4 + 16;
      out += `<g pointer-events="none">`
        +  `<rect x="${lx - w / 2}" y="${ly - 10}" width="${w}" height="20" fill="${T.bg}" stroke="${color}" stroke-width="1" stroke-opacity="${strokeOpacity}" rx="10"/>`
        +  `<text x="${lx}" y="${ly + 4}" font-family="${T.mono}" font-size="10" fill="${simpleFill}" fill-opacity="${textOpacity}" text-anchor="middle" font-weight="600">${txt}</text>`
        +  `</g>`;
    }
  }
  return out;
};

PX.components.markers = function markersSvg(suffix = '') {
  // refX=0 (base-at-endpoint) pairs with pathD's tailTrim: stroke terminates
  // at the arrowhead's base, the triangle extends forward to the original
  // polyline endpoint. Clean seam between shaft and arrowhead, no overlap.
  const states = ['normal', 'depends', 'imports', 'blast', 'faded'];
  let out = '<defs>';
  for (const s of states) {
    const col = PX.stateColor(s);
    out += `<marker id="arr-${s}${suffix}" viewBox="0 -5 10 10" refX="0" refY="0" markerWidth="7" markerHeight="7" orient="auto">`
      +  `<path d="M0,-4L10,0L0,4" fill="${col}"/></marker>`;
    out += `<marker id="garr-${s}${suffix}" viewBox="0 -6 12 12" refX="0" refY="0" markerWidth="9" markerHeight="9" orient="auto">`
      +  `<path d="M0,-5L12,0L0,5" fill="${col}"/></marker>`;
  }
  out += '</defs>';
  return out;
};
