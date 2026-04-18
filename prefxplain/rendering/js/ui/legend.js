// ui/legend.js — bottom legend strip.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

PX.ui.legend = function legend(container) {
  const T = PX.T;
  const row = document.createElement('div');
  row.style.cssText = `padding:10px 16px;border-top:1px solid ${T.border};background:${T.panel};display:flex;gap:18px;font-family:${T.mono};font-size:10.5px;color:${T.inkMuted};flex-shrink:0`;
  const sw = (col, label) => `<span style="display:inline-flex;align-items:center;gap:5px"><span style="width:16px;height:2px;background:${col}"></span>${PX.escapeXml(label)}</span>`;
  row.innerHTML = `
    <span style="letter-spacing:1.4px;color:${T.inkFaint};text-transform:uppercase">Legend</span>
    ${sw(T.inkFaint, 'imports')}
    ${sw(T.accent, 'this depends on \u2192')}
    ${sw(T.good, '\u2190 this is used by')}
    ${sw(T.warn, 'blast radius')}
    <span style="color:${T.inkFaint}">\u00b7 Nested overview keeps links at group level until you focus a group or file</span>
  `;
  container.appendChild(row);
};
