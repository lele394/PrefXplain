// ui/top-panel.js — sticky info bar at the top of the shell.
// Empty state shows repo-level stats. When a file is selected, it shows
// the file title, pills (blast / deps / size), role tag, description,
// and highlights as pills.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

// GitHub Linguist canonical colors for the languages we detect.
// Any unknown language falls back to _LANG_FALLBACK_PALETTE via stable hash.
const _LANG_COLORS = {
  python:     '#3572A5',
  javascript: '#f1e05a',
  typescript: '#3178c6',
  tsx:        '#3178c6',
  jsx:        '#f1e05a',
  html:       '#e34c26',
  css:        '#563d7c',
  scss:       '#c6538c',
  sass:       '#a53b70',
  less:       '#1d365d',
  json:       '#292929',
  yaml:       '#cb171e',
  toml:       '#9c4221',
  markdown:   '#083fa1',
  md:         '#083fa1',
  shell:      '#89e051',
  bash:       '#89e051',
  sh:         '#89e051',
  go:         '#00ADD8',
  rust:       '#dea584',
  java:       '#b07219',
  kotlin:     '#A97BFF',
  swift:      '#F05138',
  ruby:       '#701516',
  php:        '#4F5D95',
  c:          '#555555',
  cpp:        '#f34b7d',
  'c++':      '#f34b7d',
  csharp:     '#178600',
  'c#':       '#178600',
  dart:       '#00B4AB',
  vue:        '#41b883',
  svelte:     '#ff3e00',
  sql:        '#e38c00',
  dockerfile: '#384d54',
};
const _LANG_FALLBACK_PALETTE = [
  '#a78bfa', '#f59e0b', '#fb923c', '#22c55e', '#06b6d4',
  '#3b82f6', '#ec4899', '#14b8a6', '#eab308', '#ef4444',
];

function _langColor(lang) {
  const key = String(lang || '').toLowerCase().trim();
  if (_LANG_COLORS[key]) return _LANG_COLORS[key];
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return _LANG_FALLBACK_PALETTE[h % _LANG_FALLBACK_PALETTE.length];
}

function _langLabel(lang) {
  const key = String(lang || '').toLowerCase().trim();
  const map = {
    cpp: 'C++', 'c++': 'C++', csharp: 'C#', 'c#': 'C#',
    javascript: 'JavaScript', typescript: 'TypeScript', tsx: 'TypeScript',
    jsx: 'JavaScript', html: 'HTML', css: 'CSS', scss: 'SCSS', sass: 'Sass',
    less: 'Less', json: 'JSON', yaml: 'YAML', toml: 'TOML', markdown: 'Markdown',
    md: 'Markdown', shell: 'Shell', bash: 'Shell', sh: 'Shell', go: 'Go',
    rust: 'Rust', java: 'Java', kotlin: 'Kotlin', swift: 'Swift', ruby: 'Ruby',
    php: 'PHP', c: 'C', dart: 'Dart', vue: 'Vue', svelte: 'Svelte', sql: 'SQL',
    dockerfile: 'Dockerfile', python: 'Python',
  };
  return map[key] || (key ? key[0].toUpperCase() + key.slice(1) : 'Other');
}

// Paths excluded from the language bar, mirroring GitHub Linguist defaults:
// vendored dependencies and generated/minified bundles shouldn't skew the stats.
const _VENDOR_PATH_RX = /(^|\/)(vendor|node_modules|third_party|dist|build|bower_components)\//i;
const _GENERATED_RX = /\.min\.(js|css|mjs)$|\.bundle\.(js|mjs)$|\.bundled\.js$/i;

function _isVendored(nodeId) {
  if (!nodeId) return false;
  return _VENDOR_PATH_RX.test(nodeId) || _GENERATED_RX.test(nodeId);
}

function _langStats(graph) {
  const totals = {};
  for (const n of graph.nodes || []) {
    if (_isVendored(n.id)) continue;
    const key = String(n.language || '').toLowerCase().trim() || 'other';
    const bytes = (n.size && n.size > 0) ? n.size : 1;
    totals[key] = (totals[key] || 0) + bytes;
  }
  const total = Object.values(totals).reduce((a, b) => a + b, 0);
  if (!total) return { total: 0, items: [] };
  const items = Object.entries(totals)
    .map(([lang, bytes]) => ({
      lang,
      bytes,
      pct: (bytes / total) * 100,
      color: _langColor(lang),
      label: _langLabel(lang),
    }))
    .sort((a, b) => b.bytes - a.bytes);
  return { total, items };
}

function _renderLangBar(graph) {
  const T = PX.T;
  const { items } = _langStats(graph);
  if (!items.length) return '';
  const tooltip = items.map(it => `${it.label} ${it.pct.toFixed(1)}%`).join('  \u00b7  ');
  const segments = items.map(it =>
    `<span style="height:100%;background:${it.color};flex:${it.pct} 0 0;min-width:${it.pct > 0 && it.pct < 0.3 ? '2px' : '0'}"></span>`
  ).join('');
  const legend = items.map(it =>
    `<span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:${T.inkMuted};font-family:${T.ui};flex-shrink:0">
      <span style="width:7px;height:7px;border-radius:50%;background:${it.color};display:inline-block"></span>
      <span style="color:${T.ink2};font-weight:500">${PX.escapeXml(it.label)}</span>
      <span style="color:${T.inkFaint};font-family:${T.mono}">${it.pct.toFixed(1)}%</span>
    </span>`
  ).join('');
  return `
    <span title="${PX.escapeXml(tooltip)}" style="display:inline-flex;align-items:center;gap:10px;flex-shrink:0">
      <span style="display:flex;width:140px;height:6px;border-radius:999px;overflow:hidden;background:${T.panelAlt};border:1px solid ${T.borderAlt};flex-shrink:0">${segments}</span>
      <span style="display:inline-flex;align-items:center;gap:10px">${legend}</span>
    </span>
  `;
}

function _pill(label, value, tone) {
  const T = PX.T;
  const col = tone === 'warn' ? T.warn : tone === 'good' ? T.good : T.inkMuted;
  return `<span style="display:inline-flex;align-items:center;gap:6px;padding:3px 9px;background:${T.bg};border:1px solid ${T.border};border-radius:999px;font-size:11px;color:${T.inkMuted};font-family:${T.mono};flex-shrink:0">
    <span style="font-size:9px;letter-spacing:0.8px;color:${T.inkFaint}">${PX.escapeXml(label)}</span>
    <span style="color:${col};font-weight:600">${PX.escapeXml(String(value))}</span>
  </span>`;
}

function _roleTag(role) {
  const T = PX.T;
  if (!role || role === 'undefined') return '';
  const map = {
    entry_point: { label: 'entry', col: T.accent, bg: 'rgba(88,166,255,0.14)' },
    utility:     { label: 'utility', col: T.inkMuted, bg: T.panelAlt },
    test:        { label: 'test', col: '#bc8cff', bg: 'rgba(188,140,255,0.14)' },
  };
  const t = map[role] || map.utility;
  return `<span style="font-family:${T.mono};font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;padding:1px 6px;background:${t.bg};color:${t.col};border-radius:3px">${t.label}</span>`;
}

function _renderEmpty(graph) {
  const T = PX.T;
  const v = graph.version || '';
  return `
    <div style="padding:6px 14px;background:${T.panel};border-bottom:1px solid ${T.border};display:flex;align-items:center;gap:12px;font-family:${T.ui};flex-shrink:0">
      <span style="font-size:13px;font-weight:600;color:${T.ink}">prefxplain ${v ? `<span style="color:${T.inkFaint};font-family:${T.mono};font-weight:400">v${PX.escapeXml(v)}</span>` : ''}</span>
      <span style="color:${T.borderAlt}">\u00b7</span>
      ${_pill('FILES', graph.nodes.length)}
      ${_pill('EDGES', graph.edges.length)}
      ${graph.health_score != null ? _pill('HEALTH', `${graph.health_score}/10`, 'good') : ''}
      <span style="flex:1"></span>
      ${_renderLangBar(graph)}
      <span style="flex:1"></span>
      <span style="font-size:11.5px;color:${T.inkMuted}">
        <span style="color:${T.ink};font-weight:500">Click a group</span> to highlight its links \u00b7 <span style="color:${T.ink};font-weight:500">double-click</span> to drill into Nested.
      </span>
    </div>
  `;
}

function _renderFocusedGroup(graph, groupId, index, groupsMeta, selected = null) {
  const T = PX.T;
  const stats = ((index.groupStats || {})[groupId]) || null;
  if (!stats) return _renderEmpty(graph);
  const meta = groupsMeta[groupId] || {};
  const color = PX.groupColor(groupId, meta);
  const strongestOut = stats.strongestOut
    ? `${stats.strongestOut.group} \u00b7 ${stats.strongestOut.count}\u00d7`
    : 'none';
  const strongestIn = stats.strongestIn
    ? `${stats.strongestIn.group} \u00b7 ${stats.strongestIn.count}\u00d7`
    : 'none';
  const bridgePills = (stats.bridgeFiles || []).slice(0, 4).map(file =>
    `<span style="display:inline-flex;align-items:center;gap:5px;background:${T.pill};border:1px solid ${T.pillBorder};border-radius:999px;padding:2px 8px;font-size:11px;color:${T.accent2};font-weight:500">${PX.escapeXml(file.label)} <span style="color:${T.inkFaint};font-family:${T.mono}">\u2194${file.count}</span></span>`
  ).join('');
  // When a file in this group is selected, its name rides inline next to
  // the group title (same line, monospace) and its pills (BLAST/DEPS/SIZE)
  // replace the group-level counters. This merges the old floating
  // "detail summary" banner into the top info bar.
  const selNode = selected ? index.byId[selected] : null;
  const selInGroup = selNode && (selNode.group || 'Ungrouped') === groupId ? selNode : null;
  const selLabel = selInGroup ? (selInGroup.short || selInGroup.label || selInGroup.id) : null;
  const selDesc = selInGroup ? (selInGroup.description || '') : '';
  const selHighlights = selInGroup ? (selInGroup.highlights || []) : [];
  const selKb = selInGroup ? ((selInGroup.size || 0) / 1024).toFixed(1) : null;
  const selDeps = selInGroup ? (index.importsOf[selInGroup.id] || []).length : 0;
  const selBlast = selInGroup ? index.blastRadius(selInGroup.id).size : 0;
  const topRightPills = selInGroup
    ? `${_pill('BLAST', selBlast, selBlast > 5 ? 'warn' : null)}${_pill('DEPS', selDeps)}${_pill('SIZE', `${selKb} kB`)}
       <button data-action="deselect" style="font-family:${T.mono};font-size:10.5px;padding:3px 7px;background:${T.panelAlt};color:${T.inkMuted};border:1px solid ${T.border};border-radius:4px;cursor:pointer;flex-shrink:0">\u00d7</button>`
    : `${_pill('FILES', stats.fileCount)}${_pill('IN', stats.externalIn)}${_pill('OUT', stats.externalOut)}
       <button data-action="clear-focus" style="font-family:${T.mono};font-size:10.5px;padding:3px 9px;background:${T.panelAlt};color:${T.inkMuted};border:1px solid ${T.border};border-radius:4px;cursor:pointer;flex-shrink:0">\u2190 back to overview</button>`;
  const titleSuffix = selLabel
    ? `<span style="color:${T.borderAlt}">\u2014</span>
       <span style="font-family:${T.mono};font-size:13px;font-weight:700;color:${T.ink};flex-shrink:0">${PX.escapeXml(selLabel)}</span>
       ${_roleTag(selInGroup.role)}`
    : '';
  // Secondary row: if a file is selected show its description + highlights;
  // otherwise keep the group description + strongest routes + bridge pills.
  const secondaryRow = selInGroup
    ? `<div style="flex:1;min-width:0">${PX.escapeXml(selDesc)}</div>
       ${selHighlights.length ? `<div style="display:flex;flex-wrap:wrap;gap:5px;flex-shrink:0;max-width:360px;justify-content:flex-end">
         ${selHighlights.map(h => `<span style="display:inline-flex;align-items:center;background:${T.pill};border:1px solid ${T.pillBorder};border-radius:999px;padding:2px 9px;font-size:11px;color:${T.accent2};font-weight:500">${PX.escapeXml(h)}</span>`).join('')}
       </div>` : ''}`
    : `<div style="flex:1;min-width:0">
         <div>${PX.escapeXml(meta.desc || meta.description || '')}</div>
         <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;color:${T.inkMuted};font-family:${T.mono};font-size:11px">
           <span>OUT \u2192 ${PX.escapeXml(strongestOut)}</span>
           <span>IN \u2190 ${PX.escapeXml(strongestIn)}</span>
         </div>
       </div>
       ${bridgePills ? `<div style="display:flex;flex-wrap:wrap;gap:5px;flex-shrink:0;max-width:420px;justify-content:flex-end">${bridgePills}</div>` : ''}`;
  return `
    <div style="background:${T.panel};border-bottom:1px solid ${T.border};font-family:${T.ui};flex-shrink:0">
      <div style="display:flex;align-items:center;gap:10px;padding:6px 14px;border-bottom:1px solid ${T.borderAlt};white-space:nowrap;overflow-x:auto">
        <span style="width:10px;height:10px;background:${color};border-radius:50%;flex-shrink:0"></span>
        <span style="font-size:13px;font-weight:700;color:${T.ink};flex-shrink:0">${PX.escapeXml(groupId)}</span>
        ${titleSuffix}
        <span style="color:${T.borderAlt}">\u00b7</span>
        <span style="flex:1"></span>
        ${_renderLangBar(graph)}
        <span style="flex:1"></span>
        ${topRightPills}
      </div>
      <div style="display:flex;align-items:flex-start;gap:14px;padding:5px 14px;font-size:12px;color:${T.ink2};line-height:1.45">
        ${secondaryRow}
      </div>
    </div>
  `;
}

function _renderSelected(graph, selected, index, groupsMeta) {
  const T = PX.T;
  const n = index.byId[selected];
  if (!n) return _renderEmpty(graph);
  const meta = groupsMeta[n.group] || {};
  const color = PX.groupColor(n.group, meta);
  const blast = index.blastRadius(selected);
  const deps = index.importsOf[selected] || [];
  const highlights = n.highlights || [];
  const kb = ((n.size || 0) / 1024).toFixed(1);
  const v = graph.version || '';
  // Top bar stays anchored on the "prefxplain" brand even when a file is
  // selected — the file's own name/id now rides inline with the focused
  // group's title inside the nested view's summary banner, so showing it
  // up here would duplicate. Colored tick still tracks the file's group.
  return `
    <div style="background:${T.panel};border-bottom:1px solid ${T.border};font-family:${T.ui};flex-shrink:0">
      <div style="display:flex;align-items:center;gap:10px;padding:6px 14px;border-bottom:1px solid ${T.borderAlt};white-space:nowrap;overflow-x:auto">
        <span style="width:3px;height:20px;background:${color};border-radius:1px;flex-shrink:0"></span>
        <span style="font-size:13px;font-weight:700;color:${T.ink};flex-shrink:0">prefxplain ${v ? `<span style="color:${T.inkFaint};font-family:${T.mono};font-weight:400">v${PX.escapeXml(v)}</span>` : ''}</span>
        <span style="color:${T.borderAlt}">\u00b7</span>
        ${_roleTag(n.role)}
        <span style="flex:1"></span>
        ${_renderLangBar(graph)}
        <span style="flex:1"></span>
        ${_pill('BLAST', blast.size, blast.size > 5 ? 'warn' : null)}
        ${_pill('DEPS', deps.length)}
        ${_pill('SIZE', `${kb} kB`)}
        <button data-action="deselect" style="font-family:${T.mono};font-size:10.5px;padding:3px 7px;background:${T.panelAlt};color:${T.inkMuted};border:1px solid ${T.border};border-radius:4px;cursor:pointer;flex-shrink:0">\u00d7</button>
      </div>
      <div style="display:flex;align-items:flex-start;gap:14px;padding:5px 14px;font-size:12px;color:${T.ink2};line-height:1.45">
        <div style="flex:1;min-width:0">${PX.escapeXml(n.description || '')}</div>
        ${highlights.length ? `<div style="display:flex;flex-wrap:wrap;gap:5px;flex-shrink:0;max-width:360px;justify-content:flex-end">
          ${highlights.map(h => `<span style="display:inline-flex;align-items:center;background:${T.pill};border:1px solid ${T.pillBorder};border-radius:999px;padding:2px 9px;font-size:11px;color:${T.accent2};font-weight:500">${PX.escapeXml(h)}</span>`).join('')}
        </div>` : ''}
      </div>
    </div>
  `;
}

PX.ui.topPanel = function topPanel(container, { graph, index, groupsMeta }) {
  container.innerHTML = '';
  const mount = document.createElement('div');
  container.appendChild(mount);
  let selected = null;
  let focusedGroup = null;
  const listeners = { onDeselect: [], onClearFocus: [] };

  const render = () => {
    mount.innerHTML = focusedGroup
      ? _renderFocusedGroup(graph, focusedGroup, index, groupsMeta, selected)
      : selected
      ? _renderSelected(graph, selected, index, groupsMeta)
      : _renderEmpty(graph);
  };
  render();

  mount.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const action = btn.getAttribute('data-action');
    if (action === 'deselect') {
      for (const fn of listeners.onDeselect) fn();
    } else if (action === 'clear-focus') {
      for (const fn of listeners.onClearFocus) fn();
    }
  });

  return {
    setSelected: (id) => { selected = id; render(); },
    // Re-render whenever the focused group changes — the combined group +
    // file header depends on BOTH values.
    setFocusedGroup: (groupId) => { focusedGroup = groupId; render(); },
    onDeselect: (fn) => listeners.onDeselect.push(fn),
    onClearFocus: (fn) => listeners.onClearFocus.push(fn),
  };
};
