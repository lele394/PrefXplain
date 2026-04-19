// tokens.js — design tokens (GitHub-dark) ported from the Claude Design
// prototype's `T` object. Kept tiny and stable — other modules read these
// instead of hardcoding hex strings.

window.PX = window.PX || {};

// Diagnostic logging. Off by default so production renders stay quiet.
// Flip at runtime via `window.PX.DEBUG = true` from the devtools console.
PX.DEBUG = false;
PX.log = function pxLog(...args) { if (PX.DEBUG) console.log(...args); };

PX.T = {
  // surfaces
  bg:        '#0d1117',
  panel:     '#161b22',
  panelAlt:  '#1c2128',
  border:    '#30363d',
  borderAlt: '#21262d',
  codeBg:    '#010409',
  codeGutter:'#0d1117',
  // text
  ink:       '#e6edf3',
  ink2:      '#c9d1d9',
  inkMuted:  '#8b949e',
  inkFaint:  '#6e7681',
  // accents
  accent:    '#58a6ff',
  accent2:   '#79c0ff',
  pill:      '#1f2d3d',
  pillBorder:'#2b4764',
  danger:    '#f85149',
  warn:      '#d29922',
  good:      '#3fb950',
  // typography
  mono:      "'JetBrains Mono','SFMono-Regular',Menlo,monospace",
  ui:        "'Inter',-apple-system,BlinkMacSystemFont,sans-serif",
};

// Fallback palette for groups whose metadata doesn't carry a color.
// Indexed by stable hash of the group name so re-runs stay consistent.
PX.GROUP_COLOR_FALLBACK = [
  '#a78bfa', '#f59e0b', '#fb923c', '#22c55e', '#06b6d4',
  '#3b82f6', '#ec4899', '#14b8a6', '#eab308', '#ef4444',
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
