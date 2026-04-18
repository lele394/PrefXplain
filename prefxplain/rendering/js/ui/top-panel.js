// ui/top-panel.js — sticky info bar at the top of the shell.
// Empty state shows repo-level stats. When a file is selected, it shows
// the file title, pills (blast / deps / size), role tag, description,
// highlights as pills, and a "code preview" toggle that reveals the
// first lines of the (stub) source.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

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
    <div style="padding:10px 14px;background:${T.panel};border-bottom:1px solid ${T.border};display:flex;align-items:center;gap:12px;font-family:${T.ui};flex-shrink:0">
      <span style="font-size:13px;font-weight:600;color:${T.ink}">prefxplain ${v ? `<span style="color:${T.inkFaint};font-family:${T.mono};font-weight:400">v${PX.escapeXml(v)}</span>` : ''}</span>
      <span style="color:${T.borderAlt}">\u00b7</span>
      ${_pill('FILES', graph.nodes.length)}
      ${_pill('EDGES', graph.edges.length)}
      ${graph.health_score != null ? _pill('HEALTH', `${graph.health_score}/10`, 'good') : ''}
      <span style="flex:1"></span>
      <span style="font-size:11.5px;color:${T.inkMuted}">
        <span style="color:${T.ink};font-weight:500">Click a group</span> to highlight its links \u00b7 <span style="color:${T.ink};font-weight:500">double-click</span> to drill into Nested.
      </span>
    </div>
  `;
}

function _renderFocusedGroup(graph, groupId, index, groupsMeta) {
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
  return `
    <div style="background:${T.panel};border-bottom:1px solid ${T.border};font-family:${T.ui};flex-shrink:0">
      <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid ${T.borderAlt};white-space:nowrap;overflow-x:auto">
        <span style="width:3px;height:20px;background:${color};border-radius:1px;flex-shrink:0"></span>
        <span style="font-size:13px;font-weight:700;color:${T.ink};flex-shrink:0">${PX.escapeXml(groupId)}</span>
        <span style="color:${T.borderAlt}">\u00b7</span>
        ${_pill('FILES', stats.fileCount)}
        ${_pill('IN', stats.externalIn)}
        ${_pill('OUT', stats.externalOut)}
        <span style="flex:1"></span>
        <button data-action="clear-focus" style="font-family:${T.mono};font-size:10.5px;padding:3px 9px;background:${T.panelAlt};color:${T.inkMuted};border:1px solid ${T.border};border-radius:4px;cursor:pointer;flex-shrink:0">\u2190 back to overview</button>
      </div>
      <div style="display:flex;align-items:flex-start;gap:14px;padding:8px 14px;font-size:12px;color:${T.ink2};line-height:1.5">
        <div style="flex:1;min-width:0">
          <div>${PX.escapeXml(meta.desc || meta.description || '')}</div>
          <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;color:${T.inkMuted};font-family:${T.mono};font-size:11px">
            <span>OUT \u2192 ${PX.escapeXml(strongestOut)}</span>
            <span>IN \u2190 ${PX.escapeXml(strongestIn)}</span>
          </div>
        </div>
        ${bridgePills ? `<div style="display:flex;flex-wrap:wrap;gap:5px;flex-shrink:0;max-width:420px;justify-content:flex-end">${bridgePills}</div>` : ''}
      </div>
    </div>
  `;
}

function _renderSelected(graph, selected, index, showCode, groupsMeta) {
  const T = PX.T;
  const n = index.byId[selected];
  if (!n) return _renderEmpty(graph);
  const meta = groupsMeta[n.group] || {};
  const color = PX.groupColor(n.group, meta);
  const blast = index.blastRadius(selected);
  const deps = index.importsOf[selected] || [];
  const highlights = n.highlights || [];
  const kb = ((n.size || 0) / 1024).toFixed(1);
  return `
    <div style="background:${T.panel};border-bottom:1px solid ${T.border};font-family:${T.ui};flex-shrink:0">
      <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid ${T.borderAlt};white-space:nowrap;overflow-x:auto">
        <span style="width:3px;height:20px;background:${color};border-radius:1px;flex-shrink:0"></span>
        <span style="font-size:13px;font-weight:700;color:${T.ink};flex-shrink:0">${PX.escapeXml(n.short || n.label)}</span>
        <span style="color:${T.borderAlt}">\u00b7</span>
        <span style="font-size:11px;color:${T.inkFaint};font-family:${T.mono};flex-shrink:0;overflow:hidden;text-overflow:ellipsis;max-width:360px">${PX.escapeXml(n.id)}</span>
        <span style="color:${T.borderAlt}">\u00b7</span>
        ${_roleTag(n.role)}
        <span style="flex:1"></span>
        ${_pill('BLAST', blast.size, blast.size > 5 ? 'warn' : null)}
        ${_pill('DEPS', deps.length)}
        ${_pill('SIZE', `${kb} kB`)}
        <button data-action="toggle-code" style="font-family:${T.mono};font-size:10.5px;padding:3px 9px;background:${showCode ? T.accent + '22' : T.panelAlt};color:${showCode ? T.accent : T.inkMuted};border:1px solid ${showCode ? T.accent : T.border};border-radius:4px;cursor:pointer;flex-shrink:0">${showCode ? '\u25b2 hide code' : '\u25bc code preview'}</button>
        <button data-action="deselect" style="font-family:${T.mono};font-size:10.5px;padding:3px 7px;background:${T.panelAlt};color:${T.inkMuted};border:1px solid ${T.border};border-radius:4px;cursor:pointer;flex-shrink:0">\u00d7</button>
      </div>
      <div style="display:flex;align-items:flex-start;gap:14px;padding:8px 14px;font-size:12px;color:${T.ink2};line-height:1.5">
        <div style="flex:1;min-width:0">${PX.escapeXml(n.description || '')}</div>
        ${highlights.length ? `<div style="display:flex;flex-wrap:wrap;gap:5px;flex-shrink:0;max-width:360px;justify-content:flex-end">
          ${highlights.map(h => `<span style="display:inline-flex;align-items:center;background:${T.pill};border:1px solid ${T.pillBorder};border-radius:999px;padding:2px 9px;font-size:11px;color:${T.accent2};font-weight:500">${PX.escapeXml(h)}</span>`).join('')}
        </div>` : ''}
      </div>
      ${showCode ? `<div style="background:${T.codeBg};border-top:1px solid ${T.borderAlt};max-height:200px;overflow:auto;font-family:${T.mono};font-size:11.5px;line-height:1.55;padding:10px 14px;color:${T.ink2}">
        <pre style="margin:0;white-space:pre-wrap">${PX.escapeXml(n.description || '')}\n\n# ${PX.escapeXml(n.label)} \u00b7 ${kb} kB \u00b7 ${(index.importers[n.id] || []).length} importers</pre>
      </div>` : ''}
    </div>
  `;
}

PX.ui.topPanel = function topPanel(container, { graph, index, groupsMeta }) {
  container.innerHTML = '';
  const mount = document.createElement('div');
  container.appendChild(mount);
  let selected = null;
  let focusedGroup = null;
  let showCode = false;
  const listeners = { onDeselect: [], onToggleCode: [], onClearFocus: [] };

  const render = () => {
    mount.innerHTML = selected
      ? _renderSelected(graph, selected, index, showCode, groupsMeta)
      : focusedGroup
      ? _renderFocusedGroup(graph, focusedGroup, index, groupsMeta)
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
    } else if (action === 'toggle-code') {
      showCode = !showCode;
      render();
      for (const fn of listeners.onToggleCode) fn(showCode);
    }
  });

  return {
    setSelected: (id) => { selected = id; showCode = false; render(); },
    setFocusedGroup: (groupId) => { focusedGroup = groupId; if (selected) return; render(); },
    setShowCode: (v) => { showCode = v; render(); },
    onDeselect: (fn) => listeners.onDeselect.push(fn),
    onClearFocus: (fn) => listeners.onClearFocus.push(fn),
    onToggleCode: (fn) => listeners.onToggleCode.push(fn),
  };
};
