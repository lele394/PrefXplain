# Design System — PrefXplain

> One slash-command turns any codebase into an interactive architecture map. This design system governs the generated HTML artifact — the hero surface, the thing users actually look at.

## Product Context

- **What this is:** A self-contained interactive dependency graph rendered as one HTML file. No API key, no upload, no setup. The generated artifact is the product.
- **Who it's for:** Founders explaining their stack to investors and new hires; devs steering AI coding agents and drowning in diff review; tech leads onboarding onto a repo they didn't write.
- **Space / industry:** Developer tools, AI-assisted engineering, code visualization. Peers: Sourcetrail, CodeSee, Greptile, GitHub Next's repo-visualization, madge, dependency-cruiser.
- **Project type:** Generated data-dense visualization UI, embedded inside IDEs (VS Code, Cursor, Windsurf) and opened standalone in browsers.
- **Memorable thing:** "I understood this complex codebase in five minutes, not one day." Every design decision must serve comprehension speed.

## Aesthetic Direction

- **Direction:** Refined information document. Reads like a well-designed technical handbook, not a dev tool UI. Editorial, confident, unhurried. Closer to The Atlantic × a Tufte book than to Linear × Raycast.
- **Decoration level:** Intentional. Hairline borders, one precise drop-shadow on hover, subtle warm paper bg. No gradients, no blobs, no decorative icons, no uniform bubble radii.
- **Mood:** Quiet expertise. Respects the reader's time. The tool gets out of the way; the graph carries the signal.
- **Category departure:** Every dep-graph tool ships dark-mode-first because "dev tool = dark." PrefXplain defaults to light because comprehension speed — the memorable-thing — is actually better served by high-contrast typographic hierarchy on a light surface. Dark mode exists as a toggle, not the hero.
- **Reference peers examined:** GitHub Next's repo-visualization (editorial, circle-packing, pastel on white), Observable (content-as-product), madge (terminal aesthetic), dependency-cruiser (classic graphviz). We lean editorial, deliberately.

## Typography

Three fonts. Each does one job.

- **Display / hero:** **Fraunces** — variable serif with optical sizes. Weight 500, optical size 144 for the hero, 72 for subheads, 36 for detail headings. Loaded from Google Fonts.
- **Display italic:** **Fraunces italic** — 400, opsz 36. Used on detail-panel headings and rare editorial moments. Rare is the point.
- **Body, UI labels, descriptions:** **Geist Sans** — 400 / 500 / 600. Tabular-nums enabled globally (`font-variant-numeric: tabular-nums`). Loaded from Google Fonts.
- **Code, filenames, snippets:** **JetBrains Mono** — 400 / 500. Loaded from Google Fonts.
- **No additional fonts.** No Inter, no Space Grotesk, no system-ui, no Arial fallback as primary.

**Loading:**

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400;1,9..144,500&family=Geist:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

Offline fallback: the generated HTML is self-contained by design. For hardened offline use, consider bundling the WOFF2 files as base64 in a `<style>` block — tracked as a follow-up, not blocking.

**Type scale:**

| Role | Font | Size / line-height | Weight |
|------|------|--------------------|--------|
| Hero display | Fraunces | `clamp(48px, 7vw, 96px)` / 1.0 | 500 |
| Section h2 | Fraunces | 40px / 1.1 | 500 |
| Detail heading | Fraunces italic | 22px / 1.25 | 400 |
| Lede italic | Fraunces italic | 24px / 1.4 | 400 |
| Body | Geist | 15px / 1.6 | 400 |
| UI label | Geist | 14px / 1.45 | 500 |
| Filename (mono) | JetBrains Mono | 12px / 1.35 | 500 |
| Description | Geist | 12–13px / 1.45 | 400 |
| Meta / kicker | Geist | 11px / 1.0, letter-spacing 0.12em uppercase | 500 |
| Column head | Geist | 10px / 1.0, letter-spacing 0.14em uppercase | 500 |
| Code snippet | JetBrains Mono | 11.5–13px / 1.7 | 400 |

**Font-feature-settings:** `'ss01'`, `'cv11'` on Geist (cleaner zero and lowercase). Tabular-nums everywhere numeric alignment matters.

## Color

- **Approach:** Restrained. Warm paper + rich ink + one saturated accent. The graph's semantic colors (group hues, state colors) carry signal; chrome never competes.

### Core palette (light — default)

| Token | Hex | Role |
|-------|-----|------|
| `--paper` | `#faf8f2` | Primary surface, warm off-white (NOT pure white, NOT cool gray) |
| `--paper-2` | `#f4f0e4` | Recessed panels, detail sidebar, hover surfaces |
| `--ink` | `#111111` | Primary text, filename |
| `--ink-2` | `#2a2824` | Body text, description |
| `--ink-muted` | `#5b5b52` | Secondary text, muted labels |
| `--ink-faint` | `#8b8578` | Meta, crumb, timestamps |
| `--hairline` | `#e8e4d8` | Default borders, dividers |
| `--hairline-2` | `#d9d3c1` | Input borders, emphasized dividers |
| `--accent` | `#1953d8` | Selection, focus ring, "depends" edges |
| `--accent-soft` | `#e8eefc` | Focus halo, selection background |

### Semantic (retuned for light bg)

| Token | Hex | Role |
|-------|-----|------|
| `--good` | `#2d7a3d` | "Imports me" state, success |
| `--warn` | `#b47f14` | Blast-radius, warning |
| `--danger` | `#b8321f` | Error, breaking change |

### Group fallback palette

Confident, quiet colors on warm paper. Never neon. Never pastel candy.

| Token | Hex |
|-------|-----|
| `--g-sage` | `#6b8e5e` |
| `--g-rose` | `#c45e7a` |
| `--g-amber` | `#b47f14` |
| `--g-indigo` | `#4c4e9e` |
| `--g-teal` | `#2a7a7a` |
| `--g-ochre` | `#a68026` |
| `--g-brick` | `#b8321f` |
| `--g-slate` | `#4a5968` |

### Dark mode (toggle, not default)

Warm near-black, not clinical `#000`. Accent shifts brighter for contrast.

| Token | Hex |
|-------|-----|
| `--paper` | `#0e0d0a` |
| `--paper-2` | `#17150f` |
| `--ink` | `#f0ece2` |
| `--ink-2` | `#ddd8cc` |
| `--ink-muted` | `#8b847a` |
| `--ink-faint` | `#5e5a50` |
| `--hairline` | `#2a2721` |
| `--hairline-2` | `#3a352c` |
| `--accent` | `#5a8fff` |
| `--accent-soft` | `#1a2744` |
| `--good` | `#4caf5f` |
| `--warn` | `#d4a845` |
| `--danger` | `#e05a3f` |

Dark-mode strategy: warm the near-black (not pure `#000`), desaturate nothing (the palette is already restrained), brighten the accent for contrast against dark paper. Keep group colors the same — they read on both surfaces.

### State-to-color mapping (preserves existing convention)

| State | Color | Meaning |
|-------|-------|---------|
| `depends` | `--accent` (#1953d8) | What I depend on (outgoing) |
| `imports` | `--good` (#2d7a3d) | Who imports me (incoming) |
| `blast` | `--warn` (#b47f14) | Further blast radius |
| `faded` | `--hairline` / `--hairline-2` | Dimmed |

## Spacing

- **Base unit:** 4px.
- **Density:** Comfortable. More breathing room than a typical dev tool. Cards breathe. Margins are generous. The whole thing feels roomy, never cramped.
- **Scale:** `2 / 4 / 8 / 12 / 16 / 24 / 32 / 48 / 72 / 120`.
- **Canvas padding:** 40px (desktop), 24px (narrow).
- **Section padding:** 72px vertical, between major sections.
- **Hero:** 96px top, 80px bottom.

## Layout

- **Approach:** Hybrid. Disciplined vertical grid for the graph (columns = dependency layers, left-to-right). Editorial, roomy composition for detail panels and marketing moments.
- **Grid:** 3 columns for the main dependency canvas (Entry / Services / Rendering — labels are project-specific). 1-column editorial flow for hero and section heads. Detail sidebar is a fixed 340px on the right.
- **Max content width:** 1180px for non-graph sections. The graph canvas expands to container width.
- **Border radius:** hierarchical, not uniform.
  - Inline pill: `2px`
  - File card: `4px`
  - Button, input: `6px`
  - Panel, mockup container: `8–10px`
  - No `border-radius: 50%` except status dots and group dots.
- **Hairline rule:** Default border is `1px solid var(--hairline)`. Inputs and emphasized edges use `var(--hairline-2)`. Never more than 1px.

## Motion

- **Approach:** Minimal-functional. Motion only when it aids comprehension.
- **Easing:** `ease-out` for enter, `ease-in` for exit, `ease-in-out` for state transitions.
- **Duration:**
  - Micro (hover / focus): 150ms
  - State change (theme, selection): 180–250ms
  - Overlay reveal: 250ms
- **Never animate the graph on load.** The graph is the content. The user's promised 5-minute comprehension starts the moment they open the file — delaying it for a flourish breaks the promise.
- **Drop shadow on elevation:** only one level. `0 1px 2px rgba(17,17,17,0.04), 0 8px 24px -6px rgba(17,17,17,0.08)`. Used on the selected file card and the outer mockup frame. Nowhere else.

## Anti-slop Checklist

Things that MUST NOT appear in PrefXplain visuals:

- Purple or violet gradients (anywhere)
- 3-column feature grid with icons in colored circles
- Centered-everything composition with uniform spacing
- Bubble radii on everything (especially buttons)
- Gradient CTA buttons
- Inter, Space Grotesk, system-ui, or Arial as primary display or body
- Decorative blobs, hand-drawn icons, playful rounded illustrations
- Generic "Built for X / Designed for Y" marketing copy
- Drop shadows with more than 2 layers
- Multiple display fonts fighting each other

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-19 | Initial design system created via `/design-consultation` | First DESIGN.md for PrefXplain. Replaces the ad-hoc GitHub-dark clone in `rendering/js/tokens.js`. |
| 2026-04-19 | Light mode as default hero (dark as toggle) | Every competitor defaults to dark. Comprehension speed — the memorable-thing — is better served by light-bg typographic hierarchy. Deliberate category departure, worth the risk for differentiation + a real reading-speed win. |
| 2026-04-19 | Fraunces + Geist + JetBrains Mono | Three fonts each doing one job. Fraunces gives editorial personality in rare moments. Geist is neutral UI workhorse with tabular-nums. JetBrains Mono stays for category literacy in code contexts. |
| 2026-04-19 | Warm off-white (`#faf8f2`) over pure white | Paper-like, less clinical, reduces eye strain on long comprehension sessions. Small risk of reading "tinted" when expecting neutral. |
| 2026-04-19 | Accent `#1953d8` (inky saturated blue) preserved over ink-red / deep-green alternatives | Ties to existing `depends` edge convention in `tokens.js`. Risky accent deferred to a follow-up iteration. |
| 2026-04-19 | Preview file saved to `~/.gstack/projects/prefxplain/designs/design-system-20260419/preview.html` | Reference implementation of the system. Screenshot alongside. Design artifacts live outside the repo per project convention. |
| 2026-04-19 | Token-layer migration landed in `tokens.js` + `html_shell.py` + 3 view files | Palette, fonts, scrollbars, editor fallback all swapped to the light system. Zero view-rendering changes. `make test` green (193/193), `make lint` clean, `prefxplain.html` regenerates on the new palette. |
| 2026-04-19 | Dark theme shipped with runtime toggle | CSS var bridge: `PX.T` values emit `var(--px-*, #fallback)` strings; `:root[data-theme="dark"]` overrides every palette/tint/shadow token. Toggle button in top chrome (☼/☽), choice persisted in `localStorage`, anti-flash bootstrap runs before CSS paints. Zero re-render on toggle — browser re-resolves cascading vars automatically. |
| 2026-04-19 | Semantic tint + shadow tokens introduced | Added `accentTint`, `accentTintSoft`, `goodTint`, `warnTint`, `warnTintSoft`, `dangerTint`, `testColor`, `testTint`, `overlay`, `shadowSm/Md/Lg` to `PX.T`. Replaced 15 hardcoded rgba/hex literals across card-file.js, code-editor.js, flow-modal.js, sidebar.js, top-panel.js, minimap.js, main.js. Every visual primitive now adapts to theme. |

## Dark Theme Palette

Dark mode is not "light mode inverted." It's a warm near-black surface designed to feel like the same product at night, not a second theme. Values live in `html_shell.py` under `:root[data-theme="dark"]`.

### Surfaces + ink

| Token | Light | Dark |
|-------|-------|------|
| `--px-bg` | `#faf8f2` (warm paper) | `#0e0d0a` (warm near-black) |
| `--px-panel` | `#f4f0e4` | `#17150f` |
| `--px-panel-alt` | `#efebdd` | `#1c1a14` |
| `--px-border` | `#e8e4d8` | `#2a2721` |
| `--px-border-alt` | `#d9d3c1` | `#3a352c` |
| `--px-code-bg` | `#f4f0e4` | `#17150f` |
| `--px-code-gutter` | `#faf8f2` | `#0e0d0a` |
| `--px-ink` | `#111111` | `#f0ece2` (warm cream) |
| `--px-ink2` | `#2a2824` | `#ddd8cc` |
| `--px-ink-muted` | `#5b5b52` | `#8b847a` |
| `--px-ink-faint` | `#8b8578` | `#5e5a50` |
| `--px-accent` | `#1953d8` | `#5a8fff` (brighter for dark contrast) |
| `--px-accent2` | `#3e71e8` | `#7aa8ff` |
| `--px-pill` | `#e8eefc` | `#1a2744` |
| `--px-pill-border` | `#c5d4f5` | `#2a3a5c` |

### Semantic + role

| Token | Light | Dark |
|-------|-------|------|
| `--px-danger` | `#b8321f` | `#e05a3f` |
| `--px-warn` | `#b47f14` | `#d4a845` |
| `--px-good` | `#2d7a3d` | `#4caf5f` |
| `--px-test-color` | `#8957e5` | `#a371f7` |

### Tints, overlays, shadows

| Token | Light | Dark |
|-------|-------|------|
| `--px-overlay` | `rgba(17,17,17,0.35)` (soft ink dim) | `rgba(0,0,0,0.62)` (deep black dim) |
| `--px-accent-tint` | `rgba(25,83,216,0.10)` | `rgba(90,143,255,0.14)` |
| `--px-accent-tint-soft` | `rgba(25,83,216,0.06)` | `rgba(90,143,255,0.08)` |
| `--px-good-tint` | `rgba(45,122,61,0.11)` | `rgba(76,175,95,0.16)` |
| `--px-warn-tint` | `rgba(180,127,20,0.14)` | `rgba(212,168,69,0.16)` |
| `--px-warn-tint-soft` | `rgba(180,127,20,0.07)` | `rgba(212,168,69,0.08)` |
| `--px-danger-tint` | `rgba(184,50,31,0.10)` | `rgba(224,90,63,0.14)` |
| `--px-test-tint` | `rgba(137,87,229,0.14)` | `rgba(163,113,247,0.20)` |
| `--px-shadow-sm` | `0 1px 2px rgba(17,17,17,0.06)` | `0 1px 2px rgba(0,0,0,0.4)` |
| `--px-shadow-md` | `0 4px 14px rgba(17,17,17,0.10)` | `0 4px 14px rgba(0,0,0,0.5)` |
| `--px-shadow-lg` | `0 24px 80px rgba(17,17,17,0.14)` | `0 24px 80px rgba(0,0,0,0.6)` |

### Dark-mode rules of thumb

- **Light palette is still the hero.** Dark is a toggle for users who want IDE parity or read at night. Hero screenshots, marketing, investor decks — light.
- **Warm, not clinical.** Background is `#0e0d0a`, never `#000`. Ink is warm cream `#f0ece2`, never pure white. Matches the paper-feel of light mode.
- **Accent brightens in dark.** `#1953d8` → `#5a8fff`. Dark saturated blue would disappear on near-black; the brighter variant holds presence without being neon.
- **Group colors stay the same across themes.** Sage / rose / amber / indigo / teal / ochre / brick / slate have enough mid-luminance to read on both warm paper and warm near-black.
- **Shadows get heavier in dark.** Light-mode shadows are ink-tinted at 6–14% opacity; dark-mode shadows hit 40–60% opacity because they're doing the work of carving elevation on a dark surface where ink-tint shadows would vanish.

## Theme Toggle Architecture

How the toggle works (for future editors of the system):

1. **`:root`** carries the light palette as CSS custom properties. `:root[data-theme="dark"]` overrides each one.
2. **`PX.T`** in `tokens.js` emits `var(--px-*, #hexFallback)` strings for every theme-switchable key. The fallback is the light value, so rendered markup still reads correctly if CSS vars fail to load.
3. **Anti-flash bootstrap** (inline script at the top of `<body>`) reads `localStorage.getItem('prefxplain-theme')` and sets `data-theme` on `<html>` BEFORE CSS parses. No flash of light when dark is selected.
4. **`PX.applyTheme(mode)`** in tokens.js flips the attribute, persists to localStorage, fires a `'prefxplain:themechange'` window event. Views that care about the change (the toggle button's glyph, for example) subscribe.
5. **No re-render needed.** Every SVG `fill=`, CSS `background:`, inline style that referenced `T.bg` emits `var(--px-bg, #faf8f2)`. When the root attribute flips, the browser re-resolves all those var references automatically. Zero JS involvement at paint time.
6. **`PX.T_LIGHT` and `PX.T_DARK`** hold raw hex palettes for future code that needs concrete colors (canvas2D, color math, screenshot generation).

This architecture assumes `color-mix()` is NOT used in generated SVG attributes (patchy SVG support in some browsers). Semantic tints are declared as alpha-baked rgba values in the CSS var block instead. Any future tint/halo that needs a theme-adaptive value should be added as a new CSS var + PX.T token, not computed from existing values in JS.

## Implementation Notes (historical — kept for context)

The original migration plan called for:

1. ~~Replace the `PX.T` palette with the light-mode tokens above. Add a parallel dark-mode token set gated on `[data-theme="dark"]` or a `prefers-color-scheme` media query.~~ ✅ Done 2026-04-19.
2. ~~Swap the Google Fonts link in `html_shell.py` to load Fraunces + Geist + JetBrains Mono (not Inter).~~ ✅ Done.
3. ~~Update the `--ui` and `--mono` CSS custom properties to point at the new stack.~~ ✅ Done.
4. ~~Retune the `GROUP_COLOR_FALLBACK` array to the 8 group colors defined above.~~ ✅ Done.
5. ~~Edge colors (`PX.stateColor`) already map to semantic tokens — just verify hex values update when the palette swaps.~~ ✅ Verified.
6. Audit existing view modules (`group-map.js`, `nested.js`, `flat.js`) for hardcoded hex strings — per the tokens.js comment, they should already read from `PX.T`, but verify.

Do not touch `prefxplain/rendering/js/views/*` rendering logic as part of the palette swap — design-system migration is a token-layer change only. Rendering layout changes are a separate conversation.

## Reference Artifacts

- Preview HTML: `~/.gstack/projects/prefxplain/designs/design-system-20260419/preview.html`
- Screenshot: `~/.gstack/projects/prefxplain/designs/design-system-20260419/preview-screenshot.png`
- Peer research: `/tmp/prefxplain-research/` (ephemeral)
