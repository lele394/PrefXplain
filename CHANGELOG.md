# Changelog

All notable changes to PrefXplain are documented here.

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
