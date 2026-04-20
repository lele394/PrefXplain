// ui/view-switcher.js — top chrome bar: reload, theme toggle, keyboard hints.
//
// This file used to host a Group Map / Nested segmented control, but the two
// views were consolidated into a single graph whose mode (overview vs focused
// group) is driven by state.focusedGroup in main.js. The name is kept for now
// to avoid touching the bundler/HTML shell; only the contents changed.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

PX.ui.viewSwitcher = function viewSwitcher(container) {
  const T = PX.T;

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

  // Spacer + keyboard hints
  const spacer = document.createElement('span'); spacer.style.flex = '1'; wrap.appendChild(spacer);
  const hint = document.createElement('span');
  hint.style.cssText = `font-family:${T.mono};font-size:9.5px;color:${T.inkFaint}`;
  hint.innerHTML = `<kbd style="font-family:${T.mono};font-size:9.5px;padding:1px 5px;background:${T.bg};border:1px solid ${T.border};border-radius:3px;color:${T.inkFaint}">/</kbd> search \u00b7 <kbd style="font-family:${T.mono};font-size:9.5px;padding:1px 5px;background:${T.bg};border:1px solid ${T.border};border-radius:3px;color:${T.inkFaint}">esc</kbd> deselect \u00b7 dbl-click card \u2192 flow`;
  wrap.appendChild(hint);

  container.appendChild(wrap);
};
