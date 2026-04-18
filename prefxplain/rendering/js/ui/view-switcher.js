// ui/view-switcher.js — segmented control for Group Map / Nested.
// Single source of truth for view state lives in main.js, which gets notified
// via onChange.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

PX.ui.viewSwitcher = function viewSwitcher(container, {
  value,
  onChange,
}) {
  const T = PX.T;
  const views = [
    { id: 'group-map', label: 'Group map' },
    { id: 'nested',    label: 'Nested' },
  ];
  let current = value;

  const wrap = document.createElement('div');
  wrap.style.cssText = `display:flex;align-items:center;gap:12px;padding:6px 14px;background:${T.panel};border-bottom:1px solid ${T.border};font-family:${T.ui};font-size:11.5px;flex-shrink:0`;

  const lead = document.createElement('span');
  lead.textContent = 'View';
  lead.style.cssText = `color:${T.inkFaint};font-family:${T.mono};font-size:9.5px;letter-spacing:1.2px;text-transform:uppercase`;
  wrap.appendChild(lead);

  const pill = document.createElement('div');
  pill.style.cssText = `display:flex;gap:1px;padding:1px;background:${T.bg};border:1px solid ${T.border};border-radius:4px`;

  const buttons = {};
  const paint = () => {
    for (const v of views) {
      const b = buttons[v.id];
      const active = current === v.id;
      b.style.background = active ? T.accent : 'transparent';
      b.style.color = active ? '#fff' : T.inkMuted;
    }
  };

  for (const v of views) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = v.label;
    b.style.cssText = `font-family:${T.mono};font-size:10.5px;padding:3px 9px;border:none;cursor:pointer;border-radius:3px`;
    b.addEventListener('click', () => {
      if (current === v.id) return;
      current = v.id;
      paint();
      if (typeof onChange === 'function') onChange(current);
    });
    pill.appendChild(b);
    buttons[v.id] = b;
  }
  wrap.appendChild(pill);
  paint();

  // Spacer + keyboard hints
  const spacer = document.createElement('span'); spacer.style.flex = '1'; wrap.appendChild(spacer);
  const hint = document.createElement('span');
  hint.style.cssText = `font-family:${T.mono};font-size:9.5px;color:${T.inkFaint}`;
  hint.innerHTML = `<kbd style="font-family:${T.mono};font-size:9.5px;padding:1px 5px;background:${T.bg};border:1px solid ${T.border};border-radius:3px;color:${T.inkFaint}">/</kbd> search \u00b7 <kbd style="font-family:${T.mono};font-size:9.5px;padding:1px 5px;background:${T.bg};border:1px solid ${T.border};border-radius:3px;color:${T.inkFaint}">esc</kbd> deselect \u00b7 dbl-click card \u2192 flow`;
  wrap.appendChild(hint);

  container.appendChild(wrap);
  return {
    setValue: (v) => { current = v; paint(); },
    get value() { return current; },
  };
};
