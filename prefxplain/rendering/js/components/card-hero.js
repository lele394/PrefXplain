// components/card-hero.js — SVG string for one hero card (Group Map mode).
// 320x180 box, matches the design prototype: colored top stripe, count chip,
// group title + "L{layer} · N files" meta, description, 3 bullet highlights.

window.PX = window.PX || {};
PX.components = PX.components || {};

PX.components.cardHero = function cardHeroSvg(groupMeta, opts = {}) {
  const T = PX.T;
  const {
    x, y, w = 320, h = 180,
    name,                       // group name
    color,                      // group color (hex)
    desc = '',                  // group description (one paragraph)
    highlights = [],            // up to 3 bullet strings
    fileCount = 0,              // number of files in group
    layer = 0,                  // layer index (0 = deepest)
    selected = false,
    faded = false,
    inDegree = 0,               // groups that depend on this one
    outDegree = 0,              // groups this one depends on
  } = Object.assign({}, groupMeta, opts);
  const strokeCol = selected ? color : T.border;
  // Border thickens with inDegree: heavily-imported groups read as foundational.
  const strokeW = selected ? 2.5 : 1 + Math.min(inDegree, 3) * 0.4;
  const opacity = faded ? 0.28 : 1;
  const hs = highlights.slice(0, 3);
  let out = `<g class="hero-card" data-group="${PX.escapeXml(name)}" opacity="${opacity}" style="transition:opacity 200ms;cursor:pointer">`;
  // outer card
  out += `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${T.panel}" stroke="${strokeCol}" stroke-width="${strokeW}" rx="10"/>`;
  // top stripe
  out += `<rect x="${x}" y="${y}" width="${w}" height="6" fill="${color}" rx="6"/>`;
  out += `<rect x="${x}" y="${y + 3}" width="${w}" height="3" fill="${color}" opacity="0.6"/>`;
  // count chip
  out += `<rect x="${x + 22}" y="${y + 22}" width="28" height="28" fill="${color}" opacity="0.18" rx="6"/>`;
  out += `<rect x="${x + 22}" y="${y + 22}" width="28" height="28" fill="none" stroke="${color}" stroke-width="1" rx="6"/>`;
  out += `<text x="${x + 36}" y="${y + 41}" font-family="${T.mono}" font-size="13" font-weight="700" fill="${color}" text-anchor="middle">${fileCount}</text>`;
  // title + meta
  out += `<text x="${x + 60}" y="${y + 38}" font-family="${T.ui}" font-size="17" font-weight="700" fill="${T.ink}">${PX.escapeXml(name)}</text>`;
  const fileLabel = fileCount === 1 ? 'file' : 'files';
  out += `<text x="${x + 60}" y="${y + 53}" font-family="${T.mono}" font-size="10" fill="${T.inkFaint}" letter-spacing="1">L${layer} \u00b7 ${fileCount} ${fileLabel}</text>`;
  // description (foreignObject so it wraps; fall back to text tspans if host lacks FO)
  const descSafe = PX.escapeXml(desc);
  out += `<foreignObject x="${x + 22}" y="${y + 70}" width="${w - 44}" height="48">`
    +  `<div xmlns="http://www.w3.org/1999/xhtml" style="font-family:${T.ui};font-size:12px;line-height:1.45;color:${T.ink2};overflow:hidden">${descSafe}</div>`
    +  `</foreignObject>`;
  // highlights
  hs.forEach((h, i) => {
    const by = y + 124 + i * 17;
    out += `<rect x="${x + 22}" y="${by}" width="4" height="4" fill="${color}" rx="2"/>`;
    out += `<text x="${x + 34}" y="${by + 4}" font-family="${T.mono}" font-size="11" fill="${T.ink2}">${PX.escapeXml(h)}</text>`;
  });
  // Dependency badges: ↑N = N groups depend on this (foundational), ↓M = depends on M others.
  if (inDegree > 0 || outDegree > 0) {
    const parts = [];
    if (inDegree > 0)  parts.push(`↑${inDegree}`);
    if (outDegree > 0) parts.push(`↓${outDegree}`);
    out += `<text x="${x + w - 12}" y="${y + h - 10}" font-family="${T.mono}" font-size="9" fill="${T.inkFaint}" text-anchor="end" pointer-events="none">${parts.join('  ')}</text>`;
  }
  out += `</g>`;
  return out;
};
