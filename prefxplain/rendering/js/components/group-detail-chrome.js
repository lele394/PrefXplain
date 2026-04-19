// components/group-detail-chrome.js — chrome pieces for the nested detail view.
// Breadcrumb strip, summary header, "Primary entry paths" ranked strip, band
// headers, and "Stress points" strip. All SVG via foreignObject so we can
// lean on HTML/CSS for dense prose layout.

window.PX = window.PX || {};
PX.components = PX.components || {};

PX.components.detailBreadcrumb = function detailBreadcrumb({ x, y, w, groupId, color }) {
  const T = PX.T;
  const h = 36;
  const label = PX.escapeXml(groupId);
  const accent = color || T.accent2;
  return `<g class="detail-breadcrumb" data-back-to-overview="1" style="cursor:pointer">
    <rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${T.panel}" stroke="${T.border}" stroke-width="1" rx="6"/>
    <text x="${x + 14}" y="${y + 22}" font-family="${T.mono}" font-size="10" letter-spacing="1.2" fill="${T.inkFaint}">GROUPS</text>
    <text x="${x + 68}" y="${y + 22}" font-family="${T.mono}" font-size="10" fill="${T.inkMuted}">/</text>
    <circle cx="${x + 84}" cy="${y + 18}" r="4" fill="${accent}"/>
    <text x="${x + 94}" y="${y + 22}" font-family="${T.mono}" font-size="12" font-weight="700" fill="${T.ink}">${label}</text>
    <text x="${x + w - 14}" y="${y + 22}" font-family="${T.mono}" font-size="11" fill="${T.inkMuted}" text-anchor="end">\u2190 back to overview</text>
  </g>`;
};

PX.components.detailSummary = function detailSummary({ x, y, w, story }) {
  const T = PX.T;
  const { meta, summary } = story;
  const h = 84;
  const pill = (text, color) => `<span style="display:inline-flex;align-items:center;padding:3px 9px;background:${T.bg};border:1px solid ${T.border};border-radius:999px;font-family:${T.mono};font-size:10.5px;color:${color || T.ink2}">${PX.escapeXml(text)}</span>`;
  const pills = [
    pill(`${summary.fileCount} files`),
    pill(`\u2190 ${summary.externalIn}`, T.good),
    pill(`${summary.externalOut} \u2192`, T.accent2),
    pill(`\u21BB ${summary.internalEdges}`, T.inkMuted),
  ].join('');
  const routeSpan = (r) => {
    const arrow = r.dir === 'out' ? '\u2192' : '\u2190';
    const col = r.dir === 'out' ? T.accent2 : T.good;
    return `<span style="display:inline-flex;align-items:center;gap:5px;font-family:${T.mono};font-size:11px;color:${T.ink2}">
      <span style="color:${col};font-weight:700">${arrow}</span>
      <span style="color:${T.ink}">${PX.escapeXml(r.group)}</span>
      <span style="color:${T.inkMuted}">${r.count}\u00D7</span>
    </span>`;
  };
  const routes = (summary.topRoutes || []).slice(0, 4).map(routeSpan).join('<span style="color:'+T.borderAlt+';margin:0 8px">\u00B7</span>');
  const routesBlock = routes
    ? `<div style="margin-top:10px;display:flex;flex-wrap:wrap;align-items:center;gap:4px 0">
        <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.3px;text-transform:uppercase;color:${T.inkFaint};margin-right:12px">Strongest routes</span>
        ${routes}
      </div>`
    : '';
  const desc = PX.escapeXml(meta.description || '');
  const descBlock = desc
    ? `<div style="margin-top:6px;font-size:12px;line-height:1.5;color:${T.ink2};max-width:820px">${desc}</div>`
    : '';
  const html = `<div xmlns="http://www.w3.org/1999/xhtml" style="padding:14px 16px;font-family:${T.ui};color:${T.ink}">
    <div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap">
      <span style="width:10px;height:10px;background:${meta.color};border-radius:50%;display:inline-block"></span>
      <span style="font-size:17px;font-weight:700;color:${T.ink}">${PX.escapeXml(meta.name)}</span>
      <span style="display:inline-flex;flex-wrap:wrap;gap:6px;margin-left:auto">${pills}</span>
    </div>
    ${descBlock}
    ${routesBlock}
  </div>`;
  return `<g class="detail-summary">
    <rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${T.panel}" stroke="${T.border}" stroke-width="1" rx="8"/>
    <rect x="${x}" y="${y}" width="${w}" height="3" fill="${meta.color}" rx="8"/>
    <foreignObject x="${x}" y="${y + 3}" width="${w}" height="${h - 3}">${html}</foreignObject>
  </g>`;
};

PX.components.entryPathsStrip = function entryPathsStrip({ x, y, w, entries, color }) {
  const T = PX.T;
  const h = entries.length ? 58 : 0;
  if (!entries.length) return { svg: '', h };
  const chip = (f) => {
    const roleLabel = f.role === 'entry_point' ? 'entry'
      : f.role === 'api_route' ? 'route'
      : f.role === 'data_model' ? 'model'
      : f.role;
    const name = PX.escapeXml(f.label);
    const short = PX.escapeXml(f.short || '');
    const fanIn = f.fanIn || 0;
    return `<div data-node="${PX.escapeXml(f.id)}" class="entry-chip" style="cursor:pointer;display:flex;flex-direction:column;gap:2px;padding:7px 12px;background:${T.bg};border:1px solid ${T.border};border-left:3px solid ${color};border-radius:4px;min-width:200px;max-width:320px;flex:1;transition:border-color 200ms">
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.2px;text-transform:uppercase;color:${color};font-weight:700">${PX.escapeXml(roleLabel)}</span>
        <span style="font-family:${T.mono};font-size:11.5px;font-weight:700;color:${T.ink};flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${name}</span>
        <span style="font-family:${T.mono};font-size:9.5px;color:${T.good};font-weight:700">\u2190 ${fanIn}</span>
      </div>
      ${short ? `<div style="font-family:${T.ui};font-size:10.5px;color:${T.inkMuted};line-height:1.35;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${short}</div>` : ''}
    </div>`;
  };
  const html = `<div xmlns="http://www.w3.org/1999/xhtml" style="display:flex;align-items:stretch;gap:10px;font-family:${T.ui};padding:8px 0">
    <div style="flex-shrink:0;display:flex;flex-direction:column;justify-content:center;min-width:160px">
      <div style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint}">Primary entry paths</div>
      <div style="font-family:${T.mono};font-size:10px;color:${T.inkMuted};margin-top:2px">${entries.length} file${entries.length > 1 ? 's' : ''} receive external imports</div>
    </div>
    <div style="display:flex;gap:8px;flex:1;overflow-x:auto;min-width:0">
      ${entries.map(chip).join('')}
    </div>
  </div>`;
  const svg = `<g class="entry-paths">
    <foreignObject x="${x}" y="${y}" width="${w}" height="${h}">${html}</foreignObject>
  </g>`;
  return { svg, h };
};

PX.components.bandLabel = function bandLabel({ x, y, w, name, count }) {
  const T = PX.T;
  return `<g class="band-label" pointer-events="none">
    <text x="${x}" y="${y - 10}" font-family="${T.mono}" font-size="10" letter-spacing="1.4" fill="${T.inkFaint}">${PX.escapeXml(name.toUpperCase())}</text>
    <text x="${x + w}" y="${y - 10}" font-family="${T.mono}" font-size="10" fill="${T.inkMuted}" text-anchor="end">${count}</text>
    <line x1="${x}" y1="${y - 4}" x2="${x + w}" y2="${y - 4}" stroke="${T.borderAlt}" stroke-width="1" stroke-dasharray="2 3"/>
  </g>`;
};

PX.components.stressStrip = function stressStrip({ x, y, w, stress }) {
  const T = PX.T;
  if (!stress || stress.length === 0) return { svg: '', h: 0 };
  const row = (s) => {
    const icon = s.kind === 'hub' ? '\u26A1' : s.kind === 'cycle' ? '\u21BB' : s.kind === 'bridge' ? '\u25C7' : '\u25CB';
    const col = s.kind === 'hub' ? T.warn : s.kind === 'cycle' ? T.danger : s.kind === 'bridge' ? T.accent2 : T.inkMuted;
    return `<div style="display:flex;align-items:center;gap:10px;padding:6px 12px;background:${T.bg};border:1px solid ${T.border};border-left:3px solid ${col};border-radius:4px">
      <span style="font-family:${T.mono};font-size:13px;color:${col}">${icon}</span>
      <span style="font-family:${T.ui};font-size:11.5px;color:${T.ink2};flex:1;line-height:1.35">${PX.escapeXml(s.text)}</span>
      <span style="font-family:${T.mono};font-size:9px;letter-spacing:1.2px;text-transform:uppercase;color:${col};font-weight:700">${PX.escapeXml(s.kind)}</span>
    </div>`;
  };
  const h = stress.length * 32 + 24;
  const html = `<div xmlns="http://www.w3.org/1999/xhtml" style="font-family:${T.ui}">
    <div style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint};margin-bottom:8px">Stress points</div>
    <div style="display:flex;flex-direction:column;gap:6px">${stress.map(row).join('')}</div>
  </div>`;
  const svg = `<g class="stress-strip">
    <foreignObject x="${x}" y="${y}" width="${w}" height="${h}">${html}</foreignObject>
  </g>`;
  return { svg, h };
};
