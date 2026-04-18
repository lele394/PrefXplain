// components/group-container.js — slim group container for Nested mode.
// Colored left stripe, title top-left, "L{layer} · N" top-right, one-line
// group description underneath. Quiet so the file cards inside are the
// main attraction.

window.PX = window.PX || {};
PX.components = PX.components || {};

PX.components.groupContainer = function groupContainerSvg(opts = {}) {
  const T = PX.T;
  const {
    x, y, w, h,
    name,
    color = T.border,
    desc = '',
    layer = 0,
    fileCount = 0,
    bridgeIn = 0,
    bridgeOut = 0,
    strongestIn = null,
    strongestOut = null,
    gatewayFiles = [],
    expanded = false,
    selected = false,
    faded = false,
  } = opts;
  const strokeCol = selected ? color : T.border;
  const strokeW = selected ? 1.8 : 1;
  const opacity = faded ? 0.34 : 1;
  const metaText = `${fileCount} files \u00b7 \u2190 ${bridgeIn} \u00b7 ${bridgeOut} \u2192`;
  const routeSummary = [
    strongestOut ? `OUT \u2192 ${strongestOut.group} ${strongestOut.count}\u00d7` : null,
    strongestIn ? `IN \u2190 ${strongestIn.group} ${strongestIn.count}\u00d7` : null,
  ].filter(Boolean).join(' \u00b7 ');
  const gatewaySummary = (gatewayFiles || []).slice(0, 3).map(file => `${file.label} \u2194${file.count}`).join(' \u00b7 ');
  // Rail variant: the overview collapses to ~180px wide next to a focused
  // detail panel. Render only the essentials — color stripe, group name,
  // file count — so the rail stays legible without crowding.
  const isRail = w <= 210;
  let out = `<g class="group-container" data-group="${PX.escapeXml(name)}" opacity="${opacity}" style="transition:opacity 200ms;cursor:pointer">`;
  out += `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${T.panel}" stroke="${strokeCol}" stroke-width="${strokeW}" rx="6"/>`;
  out += `<rect x="${x}" y="${y}" width="${expanded ? w : 4}" height="${expanded ? 6 : h}" fill="${color}" rx="2"/>`;
  if (isRail && !expanded) {
    out += `<text x="${x + 14}" y="${y + 24}" font-family="${T.ui}" font-size="13" font-weight="700" fill="${T.ink}">${PX.escapeXml(name)}</text>`;
    out += `<text x="${x + 14}" y="${y + 44}" font-family="${T.mono}" font-size="10" fill="${T.inkFaint}">${fileCount} files</text>`;
    out += `<text x="${x + w - 10}" y="${y + 44}" font-family="${T.mono}" font-size="9.5" fill="${T.inkFaint}" text-anchor="end" letter-spacing="1">L${layer}</text>`;
    if (bridgeIn || bridgeOut) {
      out += `<text x="${x + 14}" y="${y + 60}" font-family="${T.mono}" font-size="9.5" fill="${T.inkFaint}">\u2190${bridgeIn} \u00b7 ${bridgeOut}\u2192</text>`;
    }
    out += `</g>`;
    return out;
  }
  out += `<text x="${x + 18}" y="${y + 22}" font-family="${T.ui}" font-size="${expanded ? 14 : 13}" font-weight="700" fill="${T.ink}">${PX.escapeXml(name)}</text>`;
  out += `<text x="${x + w - 14}" y="${y + 22}" font-family="${T.mono}" font-size="9.5" fill="${T.inkFaint}" text-anchor="end" letter-spacing="1">L${layer}</text>`;
  if (desc) {
    out += `<foreignObject x="${x + 18}" y="${y + 30}" width="${Math.max(0, w - 36)}" height="${expanded ? 36 : 30}">`
      +  `<div xmlns="http://www.w3.org/1999/xhtml" style="font-family:${T.ui};font-size:${expanded ? '11px' : '10.5px'};line-height:1.45;color:${T.inkMuted};overflow:hidden">${PX.escapeXml(desc)}</div>`
      +  `</foreignObject>`;
  }
  out += `<text x="${x + 18}" y="${expanded ? y + 72 : y + 66}" font-family="${T.mono}" font-size="10" fill="${T.inkFaint}">${PX.escapeXml(metaText)}</text>`;
  if (routeSummary) {
    out += `<foreignObject x="${x + 18}" y="${expanded ? y + 80 : y + 78}" width="${Math.max(0, w - 36)}" height="18">`
      + `<div xmlns="http://www.w3.org/1999/xhtml" style="font-family:${T.mono};font-size:10px;color:${T.ink2};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${PX.escapeXml(routeSummary)}</div>`
      + `</foreignObject>`;
  }
  if (gatewaySummary) {
    out += `<foreignObject x="${x + 18}" y="${expanded ? y + 98 : y + 94}" width="${Math.max(0, w - 36)}" height="18">`
      + `<div xmlns="http://www.w3.org/1999/xhtml" style="font-family:${T.mono};font-size:10px;color:${T.ink2};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${PX.escapeXml(gatewaySummary)}</div>`
      + `</foreignObject>`;
  }
  out += `<text x="${x + 18}" y="${h + y - 14}" font-family="${T.mono}" font-size="10" fill="${expanded ? T.accent2 : T.inkFaint}">${expanded ? 'Select a file to trace exact links' : 'Click to open in detail'}</text>`;
  out += `</g>`;
  return out;
};
