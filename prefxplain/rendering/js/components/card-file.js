// components/card-file.js — SVG string for one file card (Nested mode).
// 220x92 (with bullets) or 220x52 (without). Four rows:
//   1. role glyph + filename + size dots + "{size}k"
//   2. subtitle (short title)
//   3. up to 2 highlight bullets
//   4. IN / OUT fan bars (normalized by maxDeg across all files)

window.PX = window.PX || {};
PX.components = PX.components || {};

function _sizeDots(sizeKB) {
  // 1..5 dots on a log scale so small files aren't all at 0 and huge files aren't all at 5.
  return Math.max(1, Math.min(5, Math.ceil(Math.log2(Math.max(1, sizeKB)))));
}

function _glyph(node, x, y, color, isSelFill) {
  const col = isSelFill ? '#fff' : color;
  if (node.isHub) {
    return `<path d="M${x + 12} ${y + 10} L${x + 18} ${y + 19} L${x + 6} ${y + 19} Z" fill="none" stroke="${col}" stroke-width="1.3" stroke-linejoin="round"/>`
      +  `<line x1="${x + 12}" y1="${y + 13}" x2="${x + 12}" y2="${y + 16}" stroke="${col}" stroke-width="1.3"/>`
      +  `<circle cx="${x + 12}" cy="${y + 18}" r="0.7" fill="${col}"/>`;
  }
  if (node.role === 'entry_point') {
    return `<path d="M${x + 8} ${y + 10} L${x + 17} ${y + 15} L${x + 8} ${y + 20} Z" fill="${col}" opacity="${isSelFill ? 1 : 0.85}"/>`;
  }
  if (node.role === 'test') {
    return `<path d="M${x + 7} ${y + 15} L${x + 11} ${y + 19} L${x + 18} ${y + 11}" fill="none" stroke="${isSelFill ? '#fff' : PX.T.testColor}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`;
  }
  // util default — 3 dots
  const d = isSelFill ? '#fff' : PX.T.inkFaint;
  return `<circle cx="${x + 9}" cy="${y + 15}" r="1.2" fill="${d}"/>`
    +  `<circle cx="${x + 13}" cy="${y + 15}" r="1.2" fill="${d}"/>`
    +  `<circle cx="${x + 17}" cy="${y + 15}" r="1.2" fill="${d}"/>`;
}

PX.components.cardFile = function cardFileSvg(node, box, ctx) {
  const T = PX.T;
  const {
    state = 'normal',
    showBullets = true,
    groupColor = T.border,
    maxDeg = 1,
    inDeg = 0,
    outDeg = 0,
    isHub = false,
    bridgeIn = 0,
    bridgeOut = 0,
    hubSource = null,   // { color } for top-right trail (optional)
  } = ctx || {};
  const { x, y, w, h } = box;
  const isSel = state === 'selected';
  const isEntry = node.role === 'entry_point';
  const isTest = node.role === 'test';
  const fill = isSel ? T.accent
    : state === 'blast' ? T.warnTint
    : state === 'depends' ? T.accentTint
    : state === 'imports' ? T.goodTint
    : state === 'match' ? T.goodTint
    : T.panelAlt;
  const stroke = isSel ? T.accent2
    : state === 'blast' ? T.warn
    : state === 'depends' ? T.accent
    : state === 'imports' ? T.good
    : state === 'match' ? T.good
    : isHub ? T.warn
    : T.border;
  const textCol = isSel ? '#fff' : T.ink;
  const mutedCol = isSel ? 'rgba(255,255,255,0.6)' : T.inkFaint;
  const subCol = isSel ? 'rgba(255,255,255,0.8)' : T.inkMuted;
  const sizeKB = Math.round((node.size || 0) / 1024);
  const dots = _sizeDots(sizeKB);
  const accent = isHub ? T.warn : isEntry ? T.accent : isTest ? T.testColor : groupColor;
  const glyph = _glyph({ isHub, role: node.role }, x, y, accent, isSel);
  const barMaxW = 44;
  const inBarW = (inDeg / Math.max(1, maxDeg)) * barMaxW;
  const outBarW = (outDeg / Math.max(1, maxDeg)) * barMaxW;
  const opacity = state === 'faded' ? 0.32 : state === 'dimmed' ? 0.55 : 1;

  let out = `<g class="file-card" data-node="${PX.escapeXml(node.id)}" opacity="${opacity}" style="cursor:pointer;transition:opacity 200ms">`;
  out += `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" stroke="${stroke}" stroke-width="${isSel || isHub ? 1.8 : 1}" rx="5"/>`;
  // left accent stripe
  out += `<rect x="${x}" y="${y}" width="3" height="${h}" fill="${accent}" opacity="${isSel ? 0.9 : 0.7}" rx="1.5"/>`;
  // row 1: glyph + name + size dots + size label
  out += glyph;
  out += `<text x="${x + 24}" y="${y + 18}" font-family="${T.mono}" font-size="11.5" font-weight="600" fill="${textCol}">${PX.escapeXml(node.label)}</text>`;
  if (bridgeIn > 0 || bridgeOut > 0) {
    const badge = [];
    if (bridgeIn > 0) badge.push(`\u2190${bridgeIn}`);
    if (bridgeOut > 0) badge.push(`${bridgeOut}\u2192`);
    const badgeText = badge.join(' ');
    const badgeW = badgeText.length * 5.8 + 12;
    out += `<rect x="${x + w - badgeW - 54}" y="${y + 7}" width="${badgeW}" height="14" fill="${isSel ? 'rgba(255,255,255,0.16)' : T.accentTint}" stroke="${isSel ? 'rgba(255,255,255,0.18)' : T.accent}" stroke-width="0.8" rx="7"/>`;
    out += `<text x="${x + w - 54 - badgeW / 2}" y="${y + 17}" font-family="${T.mono}" font-size="8.5" font-weight="700" fill="${isSel ? '#fff' : T.accent2}" text-anchor="middle">${badgeText}</text>`;
  }
  // size dots
  for (let i = 0; i < 5; i++) {
    const active = i < dots;
    const dColor = active ? (isSel ? 'rgba(255,255,255,0.7)' : T.inkMuted) : (isSel ? 'rgba(255,255,255,0.15)' : T.borderAlt);
    out += `<circle cx="${x + w - 38 + i * 5}" cy="${y + 15}" r="1.6" fill="${dColor}"/>`;
  }
  out += `<text x="${x + w - 9}" y="${y + 17}" font-family="${T.mono}" font-size="9" fill="${mutedCol}" text-anchor="end">${sizeKB}k</text>`;
  if (showBullets && h >= PX.NODE_SIZES.fileBullets.h) {
    // row 2: subtitle
    out += `<text x="${x + 24}" y="${y + 31}" font-family="${T.ui}" font-size="10" fill="${subCol}">${PX.escapeXml(node.short || node.label)}</text>`;
    // row 3: up to 2 highlights
    (node.highlights || []).slice(0, 2).forEach((h, i) => {
      const maxChars = Math.floor((w - 28) / 5.4);
      const shown = h.length > maxChars ? h.slice(0, maxChars - 1) + '\u2026' : h;
      out += `<circle cx="${x + 12}" cy="${y + 44 + i * 13}" r="1.3" fill="${isSel ? 'rgba(255,255,255,0.7)' : T.inkMuted}"/>`;
      out += `<text x="${x + 18}" y="${y + 47 + i * 13}" font-family="${T.mono}" font-size="9.5" fill="${isSel ? 'rgba(255,255,255,0.85)' : T.ink2}">${PX.escapeXml(shown)}</text>`;
    });
    // row 4: IN / OUT bars
    const bx = x + 10, by = y + h - 14;
    out += `<g transform="translate(${bx},${by})">`;
    out += `<text x="0" y="4" font-family="${T.mono}" font-size="8.5" fill="${isSel ? 'rgba(255,255,255,0.7)' : T.good}" letter-spacing="0.5" font-weight="600">IN</text>`;
    out += `<rect x="15" y="-2" width="${barMaxW}" height="6" fill="${isSel ? 'rgba(255,255,255,0.08)' : T.bg}" rx="1"/>`;
    out += `<rect x="15" y="-2" width="${inBarW}" height="6" fill="${isSel ? 'rgba(255,255,255,0.9)' : T.good}" rx="1" opacity="0.95"/>`;
    out += `<text x="${15 + barMaxW + 4}" y="4" font-family="${T.mono}" font-size="9" font-weight="600" fill="${isSel ? '#fff' : T.ink2}">${inDeg}</text>`;
    out += `<g transform="translate(100,0)">`;
    out += `<text x="0" y="4" font-family="${T.mono}" font-size="8.5" fill="${isSel ? 'rgba(255,255,255,0.7)' : T.accent}" letter-spacing="0.5" font-weight="600">OUT</text>`;
    out += `<rect x="22" y="-2" width="${barMaxW}" height="6" fill="${isSel ? 'rgba(255,255,255,0.08)' : T.bg}" rx="1"/>`;
    out += `<rect x="22" y="-2" width="${outBarW}" height="6" fill="${isSel ? 'rgba(255,255,255,0.9)' : T.accent}" rx="1" opacity="0.95"/>`;
    out += `<text x="${22 + barMaxW + 4}" y="4" font-family="${T.mono}" font-size="9" font-weight="600" fill="${isSel ? '#fff' : T.ink2}">${outDeg}</text>`;
    out += `</g></g>`;
  }
  out += `</g>`;
  return out;
};
