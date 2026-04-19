// tokens.js — design tokens (GitHub-dark) ported from the Claude Design
// prototype's `T` object. Kept tiny and stable — other modules read these
// instead of hardcoding hex strings.

window.PX = window.PX || {};

// Diagnostic logging. Off by default so production renders stay quiet.
// Flip at runtime via `window.PX.DEBUG = true` from the devtools console.
PX.DEBUG = false;
PX.log = function pxLog(...args) { if (PX.DEBUG) console.log(...args); };

// Light + dark palettes per DESIGN.md. Editorial "information document"
// aesthetic — warm paper, rich ink, one saturated accent. Dark is a true
// warm near-black, not clinical #000.
//
// CSS var bridge: PX.T values are emitted as `var(--px-*, #fallback)` strings
// so the same rendered markup adapts to theme changes without re-rendering.
// html_shell.py declares the vars on :root and overrides them under
// :root[data-theme="dark"]. Flipping the attribute is all it takes.
//
// Raw hex palettes are preserved below (PX.T_LIGHT / PX.T_DARK) for code that
// genuinely needs a concrete color (color math, canvas2D fills, etc.).
PX.T_LIGHT = {
  bg:        '#faf8f2',
  panel:     '#f4f0e4',
  panelAlt:  '#efebdd',
  border:    '#e8e4d8',
  borderAlt: '#d9d3c1',
  codeBg:    '#f4f0e4',
  codeGutter:'#faf8f2',
  ink:       '#111111',
  ink2:      '#2a2824',
  inkMuted:  '#5b5b52',
  inkFaint:  '#8b8578',
  accent:    '#1953d8',
  accent2:   '#3e71e8',
  pill:      '#e8eefc',
  pillBorder:'#c5d4f5',
  danger:    '#b8321f',
  warn:      '#b47f14',
  good:      '#2d7a3d',
};

PX.T_DARK = {
  bg:        '#0e0d0a',
  panel:     '#17150f',
  panelAlt:  '#1c1a14',
  border:    '#2a2721',
  borderAlt: '#3a352c',
  codeBg:    '#17150f',
  codeGutter:'#0e0d0a',
  ink:       '#f0ece2',
  ink2:      '#ddd8cc',
  inkMuted:  '#8b847a',
  inkFaint:  '#5e5a50',
  accent:    '#5a8fff',
  accent2:   '#7aa8ff',
  pill:      '#1a2744',
  pillBorder:'#2a3a5c',
  danger:    '#e05a3f',
  warn:      '#d4a845',
  good:      '#4caf5f',
};

// The live token object consumed by every view. Each entry is a CSS var
// reference with a hex fallback (so static SVG renders without the var block
// still look right). Typography tokens are plain font-stack strings.
PX.T = {
  // surfaces
  bg:        'var(--px-bg,#faf8f2)',
  panel:     'var(--px-panel,#f4f0e4)',
  panelAlt:  'var(--px-panel-alt,#efebdd)',
  border:    'var(--px-border,#e8e4d8)',
  borderAlt: 'var(--px-border-alt,#d9d3c1)',
  codeBg:    'var(--px-code-bg,#f4f0e4)',
  codeGutter:'var(--px-code-gutter,#faf8f2)',
  // text
  ink:       'var(--px-ink,#111111)',
  ink2:      'var(--px-ink2,#2a2824)',
  inkMuted:  'var(--px-ink-muted,#5b5b52)',
  inkFaint:  'var(--px-ink-faint,#8b8578)',
  // accent
  accent:    'var(--px-accent,#1953d8)',
  accent2:   'var(--px-accent2,#3e71e8)',
  pill:      'var(--px-pill,#e8eefc)',
  pillBorder:'var(--px-pill-border,#c5d4f5)',
  // semantic
  danger:    'var(--px-danger,#b8321f)',
  warn:      'var(--px-warn,#b47f14)',
  good:      'var(--px-good,#2d7a3d)',
  // semantic tints (alpha-blended fills for selection halos, card state bg,
  // inline pills). Theme-aware — html_shell.py flips the var values under
  // :root[data-theme="dark"].
  accentTint:     'var(--px-accent-tint,rgba(25,83,216,0.10))',
  accentTintSoft: 'var(--px-accent-tint-soft,rgba(25,83,216,0.06))',
  goodTint:       'var(--px-good-tint,rgba(45,122,61,0.11))',
  warnTint:       'var(--px-warn-tint,rgba(180,127,20,0.14))',
  warnTintSoft:   'var(--px-warn-tint-soft,rgba(180,127,20,0.07))',
  dangerTint:     'var(--px-danger-tint,rgba(184,50,31,0.10))',
  // test-role accent (purple) — theme-adaptive: darker on paper, brighter on dark.
  testColor:      'var(--px-test-color,#8957e5)',
  testTint:       'var(--px-test-tint,rgba(137,87,229,0.14))',
  // modal overlay (full-viewport dim). Calibrated per theme in html_shell.py.
  overlay:        'var(--px-overlay,rgba(17,17,17,0.35))',
  // Shadows. Use as whole box-shadow values, not as single colors.
  shadowSm:       'var(--px-shadow-sm,0 1px 2px rgba(17,17,17,0.06))',
  shadowMd:       'var(--px-shadow-md,0 4px 14px rgba(17,17,17,0.10))',
  shadowLg:       'var(--px-shadow-lg,0 24px 80px rgba(17,17,17,0.14))',
  // typography — Fraunces (display), Geist (UI + body), JetBrains Mono (code).
  mono:      "'JetBrains Mono','SFMono-Regular',Menlo,monospace",
  ui:        "'Geist','Inter',-apple-system,BlinkMacSystemFont,sans-serif",
  display:   "'Fraunces',ui-serif,Georgia,serif",
};

// ---- Theme application -----------------------------------------------------

PX.THEME_KEY = 'prefxplain-theme';

PX.getTheme = function getTheme() {
  const attr = document.documentElement.getAttribute('data-theme');
  if (attr === 'dark' || attr === 'light') return attr;
  try {
    const s = localStorage.getItem(PX.THEME_KEY);
    if (s === 'dark' || s === 'light') return s;
  } catch (e) { /* localStorage unavailable (e.g., sandboxed iframe) */ }
  return 'light';
};

PX.applyTheme = function applyTheme(mode) {
  const next = mode === 'dark' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem(PX.THEME_KEY, next); } catch (e) { /* same */ }
  window.dispatchEvent(new CustomEvent('prefxplain:themechange', { detail: { mode: next } }));
};

PX.toggleTheme = function toggleTheme() {
  PX.applyTheme(PX.getTheme() === 'dark' ? 'light' : 'dark');
};

// Initialize from localStorage on module load so the attribute is set before
// any view renders. The inline bootstrap script in html_shell.py also runs
// earlier (before CSS parses) to prevent a light-to-dark flash; this is a
// belt-and-braces second pass for runtimes where the bootstrap didn't run.
(function initTheme() {
  try {
    const s = localStorage.getItem(PX.THEME_KEY);
    if ((s === 'dark' || s === 'light')
        && document.documentElement.getAttribute('data-theme') !== s) {
      document.documentElement.setAttribute('data-theme', s);
    }
  } catch (e) { /* ignore */ }
})();

// Fallback palette for groups whose metadata doesn't carry a color.
// Indexed by stable hash of the group name so re-runs stay consistent.
// Retuned for warm paper: confident but quiet — never neon, never pastel candy.
PX.GROUP_COLOR_FALLBACK = [
  '#6b8e5e', // sage
  '#c45e7a', // rose
  '#b47f14', // amber
  '#4c4e9e', // indigo
  '#2a7a7a', // teal
  '#a68026', // ochre
  '#b8321f', // brick
  '#4a5968', // slate
];

PX.groupColor = function groupColor(name, meta) {
  if (meta && meta.color) return meta.color;
  let h = 0;
  for (let i = 0; i < (name || '').length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return PX.GROUP_COLOR_FALLBACK[h % PX.GROUP_COLOR_FALLBACK.length];
};

// Selection state → stroke/marker color.
PX.stateColor = function stateColor(state) {
  const T = PX.T;
  switch (state) {
    case 'depends': return T.accent;    // out / what I depend on
    case 'imports': return T.good;      // in / who imports me
    case 'blast':   return T.warn;      // further blast radius
    case 'faded':   return T.borderAlt; // dimmed
    default:        return T.inkFaint;  // baseline
  }
};

// Selection state → edge/path opacity. Single source of truth so every view
// (group-map, nested, boundary arrows) reads the same ladder. `variant`
// picks between the `thick` ambient value used on aggregate arrows and the
// `thin` value used on single-file arrows; both ladders agree on faded and
// highlighted states.
PX.stateOpacity = function stateOpacity(state, variant = 'thick') {
  if (state === 'faded') return 0.06;
  if (state === 'normal') return variant === 'thin' ? 0.5 : 0.55;
  return 0.95;
};

PX.escapeXml = function escapeXml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};
