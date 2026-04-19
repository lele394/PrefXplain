// ui/flow-modal.js — 3-column schematic: importers | this file | deps.
// Double-click a file card to open; Escape or click-outside to close.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

function _col(title, tone, items, emptyText, T, groupsMeta) {
  const head = `<div style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${tone};margin-bottom:8px">${PX.escapeXml(title)}</div>`;
  if (!items.length) {
    return `<div>${head}<div style="padding:12px;background:${T.bg};border:1px dashed ${T.borderAlt};border-radius:4px;font-family:${T.mono};font-size:11px;color:${T.inkFaint};text-align:center">${PX.escapeXml(emptyText)}</div></div>`;
  }
  const rows = items.map(f => {
    const meta = groupsMeta[f.group] || {};
    const color = PX.groupColor(f.group, meta);
    return `<div style="display:flex;align-items:center;gap:8px;padding:8px 10px;background:${T.bg};border:1px solid ${T.border};border-left:3px solid ${color};border-radius:3px">
      <span style="font-family:${T.mono};font-size:11px;color:${T.ink};font-weight:600;flex:1">${PX.escapeXml(f.label)}</span>
      <span style="font-family:${T.mono};font-size:9px;color:${T.inkFaint};text-transform:uppercase;letter-spacing:0.8px">${PX.escapeXml(f.group || '')}</span>
    </div>`;
  }).join('');
  return `<div>${head}<div style="display:flex;flex-direction:column;gap:6px;max-height:340px;overflow:auto">${rows}</div></div>`;
}

function _arrow(color, count) {
  return `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center">
    <svg width="40" height="40" viewBox="0 0 40 40"><line x1="2" y1="20" x2="32" y2="20" stroke="${color}" stroke-width="1.6" marker-end="url(#fmarr)"/>
    <defs><marker id="fmarr" viewBox="0 -5 10 10" refX="10" refY="0" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,-4L10,0L0,4" fill="${color}"/></marker></defs></svg>
    <span style="font-family:${PX.T.mono};font-size:9.5px;color:${color};font-weight:600">${count}</span>
  </div>`;
}

PX.ui.flowModal = function flowModal({ nodeId, graph, index, groupsMeta, onClose }) {
  const T = PX.T;
  const n = index.byId[nodeId];
  if (!n) return null;
  const importersList = (index.importers[nodeId] || []).map(id => index.byId[id]).filter(Boolean);
  const depsList = (index.importsOf[nodeId] || []).map(id => index.byId[id]).filter(Boolean);
  const meta = groupsMeta[n.group] || {};
  const color = PX.groupColor(n.group, meta);
  const isHub = (index.importers[nodeId] || []).length >= 8;
  const isEntry = n.role === 'entry_point';
  const isTest = n.role === 'test';
  const steps = (n.highlights || []).slice(0, 4);
  const kb = Math.round((n.size || 0) / 1024);

  const overlay = document.createElement('div');
  overlay.style.cssText = `position:fixed;inset:0;background:${T.overlay};z-index:100;display:flex;align-items:center;justify-content:center;font-family:${T.ui};backdrop-filter:blur(6px)`;

  overlay.innerHTML = `
    <div id="px-flow-card" style="background:${T.panel};border:1px solid ${T.border};border-radius:8px;width:min(1100px,94vw);max-height:92vh;overflow:auto;box-shadow:${T.shadowLg}">
      <div style="padding:14px 20px;border-bottom:1px solid ${T.border};display:flex;align-items:center;gap:10px;background:${T.panelAlt}">
        <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint}">Flow</span>
        <span style="color:${T.borderAlt}">\u00b7</span>
        <span style="font-family:${T.mono};font-size:13px;color:${T.ink};font-weight:600">${PX.escapeXml(n.label)}</span>
        <span style="font-family:${T.mono};font-size:10.5px;color:${T.inkFaint}">${PX.escapeXml(n.id)}</span>
        ${isHub ? `<span style="font-family:${T.mono};font-size:9.5px;padding:2px 7px;background:${T.warnTint};color:${T.warn};border:1px solid ${T.warn};border-radius:3px;text-transform:uppercase;letter-spacing:1px">SPOF</span>` : ''}
        ${isEntry && !isHub ? `<span style="font-family:${T.mono};font-size:9.5px;padding:2px 7px;background:${T.accentTint};color:${T.accent};border:1px solid ${T.accent};border-radius:3px;text-transform:uppercase;letter-spacing:1px">Entry</span>` : ''}
        ${isTest ? `<span style="font-family:${T.mono};font-size:9.5px;padding:2px 7px;background:${T.testTint};color:${T.testColor};border:1px solid ${T.testColor};border-radius:3px;text-transform:uppercase;letter-spacing:1px">Test</span>` : ''}
        <span style="flex:1"></span>
        <span style="font-family:${T.mono};font-size:10px;color:${T.inkFaint}">esc to close</span>
        <button data-close style="background:transparent;border:1px solid ${T.border};color:${T.inkMuted};font-family:${T.mono};font-size:13px;width:26px;height:26px;border-radius:3px;cursor:pointer">\u00d7</button>
      </div>
      <div style="padding:20px 24px 28px">
        <div style="display:grid;grid-template-columns:1fr 40px 1.1fr 40px 1fr;gap:0;align-items:center">
          ${_col(`Inputs \u00b7 ${importersList.length} ${importersList.length === 1 ? 'caller' : 'callers'}`, T.good, importersList, `nobody imports this \u2014 ${isEntry ? 'this is an entry point' : 'top of chain'}`, T, groupsMeta)}
          ${_arrow(T.good, importersList.length)}
          <div style="background:${T.bg};border:2px solid ${isHub ? T.warn : T.accent};border-radius:6px;padding:16px;box-shadow:0 0 0 4px ${isHub ? T.warnTintSoft : T.accentTintSoft}">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
              <span style="width:6px;height:6px;background:${color};border-radius:50%"></span>
              <span style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint}">${PX.escapeXml(n.group || '')} / file</span>
            </div>
            <div style="font-family:${T.mono};font-size:16px;color:${T.ink};font-weight:700;margin-bottom:6px">${PX.escapeXml(n.label)}</div>
            <div style="font-family:${T.ui};font-size:12px;color:${T.inkMuted};line-height:1.5;margin-bottom:14px">${PX.escapeXml(n.description || n.short || '')}</div>
            ${steps.length ? `<div style="font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;text-transform:uppercase;color:${T.inkFaint};margin-bottom:8px">What it does</div>
            <ol style="margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px">
              ${steps.map((s, i) => `<li style="display:flex;gap:10px;align-items:flex-start">
                <span style="font-family:${T.mono};font-size:9.5px;color:${T.accent};margin-top:2px;min-width:18px">${String(i + 1).padStart(2, '0')}</span>
                <span style="font-family:${T.mono};font-size:11px;color:${T.ink2};line-height:1.5">${PX.escapeXml(s)}</span>
              </li>`).join('')}
            </ol>` : ''}
            <div style="margin-top:14px;display:flex;gap:16px;font-family:${T.mono};font-size:10px;color:${T.inkFaint}">
              <span>${kb}k</span><span>\u00b7</span>
              <span>fan-in ${importersList.length}</span><span>\u00b7</span>
              <span>fan-out ${depsList.length}</span>
            </div>
          </div>
          ${_arrow(T.accent, depsList.length)}
          ${_col(`Uses \u00b7 ${depsList.length} ${depsList.length === 1 ? 'dep' : 'deps'}`, T.accent, depsList, 'no internal deps \u2014 leaf module', T, groupsMeta)}
        </div>
      </div>
    </div>
  `;

  const close = () => { overlay.remove(); if (typeof onClose === 'function') onClose(); };
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
    if (e.target.closest('[data-close]')) close();
  });

  document.body.appendChild(overlay);
  return { close, element: overlay };
};
