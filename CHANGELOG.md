# Changelog

All notable changes to PrefXplain are documented here.

---

## [Unreleased]

### Added
- **Audience levels** (`--level` / `-l`): tailor description voice to the reader. Four levels — `newbie` (plain, zero-jargon), `middle` (working developer, standard terms), `strong` (senior engineer, names patterns), `expert` (domain specialist, no padding). Cache key includes the level so switching voices re-describes cleanly without wiping the DB. Empty flag reuses the prior run's level; first runs default to `newbie`.
- **Larger file cards + on-diagram highlight bullets**: each block now surfaces up to 3 concrete, codebase-specific facts (integrations, model names, exact thresholds) that stay legible when the diagram is fully zoomed out.
- **Group-level highlights**: architectural groups carry up to 3 cross-file facts synthesized from their children (e.g. `"supports Claude Code + Codex + Copilot"` from three sibling integration files).

### Changed
- **Default audience level is now `newbie`** (was `middle`). Run `/prefxplain middle` (or any other level) to override.
- Card and group dimensions enlarged so bullet highlights remain readable at the worst-case zoom-out.
- **Group Map: max 3 columns**: the overview now uses Coffman-Graham layering (`layerBound=3`), so architectural groups always arrange in at most 3 columns. Previously all groups could land in one horizontal row, making dependency arrows invisible.
- **Group Map: arrow labels removed**: "[Tests] imports 5× [CLI]" labels are gone. Coupling strength is now communicated by arrow thickness alone, reducing visual noise.
- **Group Map: ↑N / ↓M dependency badges**: each group card shows how many groups import it (↑N) and how many it imports (↓M). Border thickness also scales with in-degree — foundational groups look visually heavier.
- **Focused group view: horizontal scroll**: the inner diagram renders at natural pixel width instead of scaling down to fit the container. Groups with more than 3 file columns now scroll horizontally instead of squishing to fit.

### Fixed
- **`standaloneCollapsed` ReferenceError**: clicking a group block when using the focused view threw "standaloneCollapsed is not defined". The variable is now correctly scoped in both render paths.

---

## [0.1.0.2] - 2026-04-15

### Fixed
- **Arrow overlap in vertical flow**: arrows sharing the same routing corridor now exit/enter at staggered Y positions proportional to lane index, eliminating collinear horizontal segments that caused visual stacking
- **Arrow overlap at low zoom**: lane stagger is zoom-aware (`max(LANE_SPREAD × 0.7, lw × 3.5)`) so parallel arrows stay visually distinct regardless of zoom level
- **Fallback routing overlap**: when all 32 routing attempts are exhausted, the fallback now prefers the alt side if the primary corridor would overlap an already-drawn edge, preventing last-resort routes from stacking on top of earlier arrows
- **Solo block visual weight**: solo (ungrouped) blocks now have a thicker border, matching the visual prominence of grouped blocks
- **Arrow margin near blocks**: edge routing corridor margin increased so arrows can't graze the edges of neighboring blocks in tight layouts
- **Open group inner padding**: added breathing room (`OPEN_GROUP_INNER_TOP`) between the separator line and the first child row inside open groups
- **Open group cell width**: cell width inside open groups now dynamically widens to fit the longest title without truncation (capped at 2× `NODE_W`)
- **Group block width**: closed group block width scales with label length to prevent title truncation

### Added
- **VS Code Dark+ code preview**: clicking a node expands the sidebar to show syntax-highlighted source code; keywords, strings, comments, numbers, types, and functions each get their own VS Code color; supports Python, TypeScript, JavaScript, Go, Rust, Java, and Kotlin
- **Description snippet in sidebar**: the sidebar now shows the first 90 characters of the file's natural-language description instead of raw symbol names like `to_dict` or `CapabilityProfile`
- **Group header legibility**: closed group headers use a single uniform font size across kind label, file count, and title — cleaner than the previous proportional sizing

### Changed
- **Lane corridor spacing** (`LANE_SPREAD`): increased from 18 → 65 world units so parallel arrow corridors are visually well-separated at all zoom levels
- Hover tooltip button added to toolbar (`Hover: On/Off`); details sidebar button removed
- **Sidebar default height**: reduced to 68px (collapsed state); expands to 260px when a node with a code preview is selected

---

## [0.1.0.1] - 2026-04-12

### Fixed
- **Group header titles invisible at low zoom**: proportional font sizing and strict clip to actual header height (`OPEN_GROUP_HEADER = 120px`) ensures labels always render within the header band regardless of zoom level
- **Horizontal flow arrow overlap**: arrow routing now uses a horizontal corridor (`sideY`) in `Flow: →` mode instead of a vertical one, giving each edge its own horizontal lane
- **VS Code preview always opens**: `_open_output()` now attempts the `vscode://` URI first unconditionally, so the IDE webview opens even when running from a non-IDE terminal

### Changed
- Enlarged open group header (`OPEN_GROUP_HEADER`: 56 → 120px), padding, and gap constants for better readability
- Closed group block dimensions increased to 360×210 (was 308×168) to accommodate title and description
- Chip sizes for collapsed group sub-block hints increased (44×20, was 36×16)

---

## [0.1.0.0] - 2026-04-12

### Added
- **Semantic diagram engine** (`prefxplain/diagram.py`): groups files into architecture layers (CLI, Analysis, Exports, Graph Model, Interactive Diagram, Tests) with topological ordering and intra-group edges
- **Panel resizer**: drag the horizontal bar between the top panel and graph to resize; double-line visual handle with hover highlight
- **Semantic rendering in the main canvas**: grouped blocks show architecture labels, file cards use semantic shapes and short titles, edge labels surface the relationship kind (reads / validates / tests...)
- **Collapsed group sub-block hints**: collapsed groups show mini child chips (≤4 files) or distinct-kind summary chips for larger groups
- **Workflow overlay**: double-click any block to open a flow diagram showing data/control flow within that group or file
- **Topological layer bands**: background bands labeled Entry / Core / Data / Tests in flat mode; suppressed in grouped mode where semantic containers provide the visual hierarchy
- **VSIX packaging** for the VS Code extension (v0.1.0)
- New `exporter.py` Markdown/JSON export helpers
- `tests/test_semantic_diagram.py`: full test suite for the diagram engine

### Changed
- Default top-details panel height reduced to 100 px (was 200 px) so more graph is visible on open
- Canvas height calculation now uses flexbox sizing instead of explicit `style.height` overrides, fixing a bug where the canvas reported full viewport height and `zoomToFit` computed an incorrect pan offset
- Layer bands only render in flat mode (`groupingState === 'flat'`); grouped mode relies on semantic group containers for visual hierarchy
- Startup functions wrapped in `try/catch` so a crash in `renderDefaultSidebar` or `renderStatsBar` no longer silently aborts the layout pass

### Fixed
- Groups not rendering: uncaught exceptions in startup functions prevented `initLayout()` from running
- Canvas 720 px sizing bug: `applyViewportHeight()` was setting `graphArea.style.height = 720 px` (full viewport), causing `zoomToFit` to pan to y=360 instead of the visible center at y≈235
- Layer band headers dominating grouped mode: full-height column bands now suppressed when semantic groups are active
