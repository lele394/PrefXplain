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

  const reload = document.createElement('button');
  reload.type = 'button';
  reload.title = 'Reload preview';
  reload.textContent = '\u21bb';
  reload.style.cssText = `display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;padding:0;background:${T.ink};color:${T.bg};border:1px solid ${T.ink};border-radius:4px;font-family:${T.mono};font-size:17px;font-weight:700;line-height:1;cursor:pointer;flex-shrink:0;box-shadow:0 1px 2px rgba(17,17,17,0.08)`;
  reload.addEventListener('click', () => {
    // Inside a VS Code webview, window.location.reload() leaves the panel
    // blank (the custom vscode-webview:// scheme doesn't reload cleanly).
    // Ask the extension host to re-set panel.webview.html instead.
    const bridge = window.__prefxplainVsCodeApi;
    if (bridge && typeof bridge.postMessage === 'function') {
      bridge.postMessage({ type: 'prefxplain:reload' });
      return;
    }
    window.location.reload();
  });
  reload.addEventListener('mouseenter', () => { reload.style.background = T.accent; reload.style.color = T.bg; reload.style.borderColor = T.accent; });
  reload.addEventListener('mouseleave', () => { reload.style.background = T.ink; reload.style.color = T.bg; reload.style.borderColor = T.ink; });
  wrap.appendChild(reload);

  // Theme toggle. Flips :root[data-theme] — every view re-resolves its
  // var(--px-*) references through CSS cascading without re-rendering.
  // The glyph updates reactively via the 'prefxplain:themechange' event.
  const theme = document.createElement('button');
  theme.type = 'button';
  theme.setAttribute('aria-label', 'Toggle theme');
  const paintTheme = () => {
    const isDark = PX.getTheme && PX.getTheme() === 'dark';
    theme.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
    theme.textContent = isDark ? '\u263C' : '\u263D';  // ☼ sun / ☽ moon
  };
  theme.style.cssText = `display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;padding:0;background:transparent;color:${T.inkMuted};border:1px solid ${T.border};border-radius:4px;font-family:${T.mono};font-size:14px;line-height:1;cursor:pointer;flex-shrink:0;transition:border-color 150ms ease,color 150ms ease`;
  theme.addEventListener('mouseenter', () => { theme.style.borderColor = T.borderAlt; theme.style.color = T.ink; });
  theme.addEventListener('mouseleave', () => { theme.style.borderColor = T.border; theme.style.color = T.inkMuted; });
  theme.addEventListener('click', () => { if (PX.toggleTheme) PX.toggleTheme(); });
  window.addEventListener('prefxplain:themechange', paintTheme);
  paintTheme();
  wrap.appendChild(theme);

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
