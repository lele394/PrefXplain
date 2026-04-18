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
  } = opts;
  const T = PX.T;
  const color = PX.stateColor(state);
  const rawPts = edge.bus ? PX.buildBusTrunkPath(edge, nodesById || {}) : edge.points;
  if (!rawPts || rawPts.length < 2) return '';
  const pts = reverseArrow ? [...rawPts].reverse() : rawPts;
  const d = PX.pathD(pts, 5);
  const strokeW = thick
    ? Math.max(1.8, Math.min(5, 1.4 + (edge.count || 1) * 0.55))
    : (state === 'normal' ? 1 : 1.6);
  const eff = opacity != null ? opacity : (state === 'faded' ? 0.12 : state === 'normal' ? 0.55 : 0.95);
  const markerId = `arr-${state}${markerSuffix}`;
  let out = `<path d="${d}" fill="none" stroke="${color}" stroke-width="${strokeW}" opacity="${eff}" marker-end="url(#${markerId})" style="transition:all 200ms"/>`;
  if (label) {
    let lx = edge.labelX, ly = edge.labelY;
    if (lx == null || ly == null) {
      lx = (pts[0].x + pts[pts.length - 1].x) / 2;
      ly = (pts[0].y + pts[pts.length - 1].y) / 2;
    }
    const labelOpacity = state === 'faded' ? 0.3 : 1;
    if (typeof label === 'object' && label.sourceName && label.targetName) {
      // Three-line colored label: [source] / imports Nx / [target]
      // Char widths match group-map's collision estimate — drift between them
      // is what makes the collision avoider fire too late.
      const line1 = `[${label.sourceName}]`;
      const line2 = `imports ${label.count}\u00d7`;
      const line3 = `[${label.targetName}]`;
      const charW1 = 8.2, charW2 = 7.6;
      const w = Math.max(line1.length * charW1, line2.length * charW2, line3.length * charW1) + 26;
      const h = 50;
      const top = ly - h / 2;
      out += `<g pointer-events="none" opacity="${labelOpacity}">`
        +  `<rect x="${lx - w / 2}" y="${top}" width="${w}" height="${h}" fill="${T.bg}" stroke="${color}" stroke-width="1" rx="8"/>`
        +  `<text x="${lx}" y="${top + 14}" font-family="${T.mono}" font-size="11" fill="${label.sourceColor || color}" text-anchor="middle" font-weight="700">${PX.escapeXml(line1)}</text>`
        +  `<text x="${lx}" y="${top + 28}" font-family="${T.mono}" font-size="10" fill="${T.inkMuted}" text-anchor="middle">${PX.escapeXml(line2)}</text>`
        +  `<text x="${lx}" y="${top + 42}" font-family="${T.mono}" font-size="11" fill="${label.targetColor || color}" text-anchor="middle" font-weight="700">${PX.escapeXml(line3)}</text>`
        +  `</g>`;
    } else {
      const txt = PX.escapeXml(String(label));
      const w = txt.length * 6.4 + 16;
      out += `<g pointer-events="none" opacity="${labelOpacity}">`
        +  `<rect x="${lx - w / 2}" y="${ly - 11}" width="${w}" height="22" fill="${T.bg}" stroke="${color}" stroke-width="1" rx="11"/>`
        +  `<text x="${lx}" y="${ly + 4.5}" font-family="${T.mono}" font-size="11" fill="${color}" text-anchor="middle" font-weight="600">${txt}</text>`
        +  `</g>`;
    }
  }
  return out;
};

PX.components.markers = function markersSvg(suffix = '') {
  const states = ['normal', 'depends', 'imports', 'blast', 'faded'];
  let out = '<defs>';
  for (const s of states) {
    const col = PX.stateColor(s);
    out += `<marker id="arr-${s}${suffix}" viewBox="0 -5 10 10" refX="10" refY="0" markerWidth="7" markerHeight="7" orient="auto">`
      +  `<path d="M0,-4L10,0L0,4" fill="${col}"/></marker>`;
    out += `<marker id="garr-${s}${suffix}" viewBox="0 -6 12 12" refX="12" refY="0" markerWidth="9" markerHeight="9" orient="auto">`
      +  `<path d="M0,-5L12,0L0,5" fill="${col}"/></marker>`;
  }
  out += '</defs>';
  return out;
};
