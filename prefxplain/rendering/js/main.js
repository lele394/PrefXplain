// main.js — entry point. Phase 6: full UI chrome wired.
//   - Top info bar (selection-driven)
//   - Chrome strip (reload + theme) — view switching is state-driven
//   - Left sidebar explorer with filter
//   - Main SVG canvas
//   - Bottom legend
//   - Flow modal on double-click
//   - Keyboard: '/' focus filter, Escape deselect, dbl-click card -> flow
//
// One graph type: when `state.focusedGroup` is null we render the Group Map
// overview (hero cards + aggregate arrows). When it's set we render the
// focused group story (bands + intra-group edges). No explicit viewMode.

(async function main() {
  const root = document.getElementById('root');
  if (!root) return;

  const graph = window.__PREFXPLAIN_GRAPH__;
  if (!graph || !Array.isArray(graph.nodes)) {
    root.innerHTML = '<div style="padding:24px;color:#b8321f">No graph payload found.</div>';
    return;
  }
  if (typeof ELK === 'undefined') {
    root.innerHTML = '<div style="padding:24px;color:#b8321f">ELK failed to load.</div>';
    return;
  }

  const T = PX.T;
  const index = PX.buildGraphIndex(graph);
  const groupsMeta = graph.metaGroups || {};

  const state = {
    showBullets: true,
    selected: null,
    filter: '',
    focusedGroup: null,
    hoveredGroup: null,
    // Clicking a ghost anchor pins a group-highlight that persists after
    // mouseout. Single-click toggles; double-click teleports to that group.
    pinnedGroup: null,
    // Hovering a file card lights up its edges transiently (no dim).
    hoveredFile: null,
    // Standalone band collapse toggle — persists across re-renders without
    // being reset by selection changes.
    standaloneCollapsed: false,
  };

  // ── Shell DOM ─────────────────────────────────────────────────────
  root.innerHTML = '';
  const shell = document.createElement('div');
  shell.id = 'px-shell';
  shell.style.cssText = `width:100vw;height:100vh;display:flex;flex-direction:column;background:${T.bg};color:${T.ink};font-family:${T.ui};overflow:hidden`;
  const topHost = document.createElement('div'); shell.appendChild(topHost);
  const switchHost = document.createElement('div'); shell.appendChild(switchHost);
  const middle = document.createElement('div');
  middle.style.cssText = 'flex:1;display:flex;min-height:0';
  shell.appendChild(middle);
  const sideHost = document.createElement('div'); middle.appendChild(sideHost);
  const canvasWrap = document.createElement('div');
  canvasWrap.style.cssText = 'flex:1;min-width:0;min-height:0;position:relative;display:flex';
  const canvas = document.createElement('div');
  canvas.id = 'px-canvas';
  canvas.style.cssText = `flex:1;overflow:auto;min-width:0;min-height:0;padding:24px`;
  canvasWrap.appendChild(canvas);
  middle.appendChild(canvasWrap);

  // ── Bottom-right overlay stack: minimap (when focused) + zoom controls ──
  // Both live in one flex-column so the minimap sits directly above the zoom
  // buttons. The minimap self-hides when no group is focused.
  const bottomRight = document.createElement('div');
  bottomRight.style.cssText = `position:absolute;right:16px;bottom:16px;display:flex;flex-direction:column;align-items:flex-end;gap:8px;z-index:2;pointer-events:none`;
  canvasWrap.appendChild(bottomRight);

  const minimapHost = document.createElement('div');
  minimapHost.style.cssText = 'pointer-events:auto';
  bottomRight.appendChild(minimapHost);
  const miniMap = PX.ui.minimap(minimapHost, { graph, groupsMeta });

  // Two buttons in the bottom-right: zoom in to 150% and reset to 100%.
  // Zoom is tracked per mode (overview vs focused group) so each keeps its
  // own scale across toggles. Mode is derived from state.focusedGroup.
  const zoomKey = () => (state.focusedGroup ? 'focused' : 'overview');
  const zoomState = { overview: 1, focused: 1 };
  const zoomPanel = document.createElement('div');
  zoomPanel.style.cssText = `display:flex;align-items:center;gap:4px;padding:4px;background:${T.panel};border:1px solid ${T.border};border-radius:8px;font-family:${T.mono};color:${T.ink};box-shadow:${T.shadowMd};user-select:none;pointer-events:auto`;
  const btn = (label, title) => {
    const b = document.createElement('button');
    b.textContent = label;
    b.title = title;
    b.style.cssText = `background:transparent;border:0;color:${T.ink};font-family:${T.mono};font-size:12px;padding:6px 10px;border-radius:4px;cursor:pointer`;
    b.onmouseenter = () => { b.style.background = T.panelAlt; };
    b.onmouseleave = () => { b.style.background = 'transparent'; };
    return b;
  };
  const zIn = btn('150%', 'Zoom in to 150%');
  const zOut = btn('100%', 'Reset to 100%');
  zoomPanel.append(zIn, zOut);
  bottomRight.appendChild(zoomPanel);

  const applyZoom = () => {
    const effective = zoomState[zoomKey()] ?? 1;
    canvas.style.setProperty('--px-zoom', effective);
  };
  const setZoom = (next) => {
    zoomState[zoomKey()] = next;
    applyZoom();
  };
  zIn.onclick = () => setZoom(1.5);
  zOut.onclick = () => setZoom(1);
  applyZoom();
  // Pinch shortcut: trackpad pinch emits wheel with ctrlKey set.
  canvasWrap.addEventListener('wheel', (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    if (e.deltaY < 0) setZoom(1.5);
    else if (e.deltaY > 0) setZoom(1);
  }, { passive: false });
  const legendHost = document.createElement('div'); shell.appendChild(legendHost);
  root.appendChild(shell);

  const top = PX.ui.topPanel(topHost, { graph, index, groupsMeta });
  PX.ui.viewSwitcher(switchHost);
  const side = PX.ui.sidebar(sideHost, { graph, groupsMeta, index });
  PX.ui.legend(legendHost);

  // ── Wiring ────────────────────────────────────────────────────────
  const syncChrome = () => {
    top.setSelected(state.selected);
    top.setFocusedGroup(state.focusedGroup);
    side.setSelected(state.selected);
    side.setFocusedGroup(state.focusedGroup);
    // Minimap only relevant inside a focused group.
    miniMap.setFocused(state.focusedGroup || null);
  };
  const setSelected = async (id) => {
    state.selected = id;
    if (id && index.byId[id]) {
      state.focusedGroup = (index.byId[id].group || 'Ungrouped');
      // Selecting a file overrides any pinned ghost-anchor highlight —
      // the user's attention has moved to a specific file, so the group
      // pin shouldn't keep dimming everything else. Also flush any
      // in-flight hover state so the debounce can't stomp the selection.
      state.pinnedGroup = null;
      state.hoveredGroup = null;
      state.hoveredFile = null;
    }
    syncChrome();
    await rerender();
  };
  const setFocusedGroup = async (groupId) => {
    state.focusedGroup = groupId;
    // Focused-group change invalidates any pinned anchor — the pin belonged
    // to the previous focus context.
    state.pinnedGroup = null;
    state.hoveredFile = null;
    if (!groupId) {
      state.selected = null;
    } else if (state.selected) {
      const selGroup = ((index.byId[state.selected] || {}).group || 'Ungrouped');
      if (selGroup !== groupId) state.selected = null;
    }
    syncChrome();
    await rerender();
  };
  side.onSelect((id) => setSelected(id));
  side.onOpen((id) => openEditor(id));
  side.onSelectGroup((groupId) => setFocusedGroup(groupId));
  side.onFilter((v) => { state.filter = v; rerender(); });
  top.onDeselect(() => setSelected(null));
  top.onClearFocus(() => setFocusedGroup(null));

  // Hero single-click: toggle focus on that group's story. Hero double-click
  // behaves the same way (kept for muscle memory from the previous "drill
  // into nested" gesture). Debounce the single-click so dblclick preempts it
  // without flicker.
  let heroClickTimer = null;
  // Ghost anchor single-click pins the group; double-click teleports to it.
  // Same debounce pattern as hero so the two pin-toggles fired by a dblclick
  // don't fight the teleport. The timer is cleared by the dblclick handler.
  let anchorClickTimer = null;
  // File card single-click selects; double-click opens the flow modal. A bare
  // click triggers rerender(), which rebuilds the DOM so the second click's
  // target is a fresh element — and dblclick then fails to match .file-card
  // via elementFromPoint. Debounce the selection the same way hero does so
  // the dblclick handler can cancel it before the rerender wipes the card.
  let fileClickTimer = null;
  canvas.addEventListener('click', async (e) => {
    // Standalone collapse toggle — handled before any other target so the
    // clickable <g> doesn't fall through to the background-click handler.
    if (e.target.closest('[data-toggle-standalone]')) {
      state.standaloneCollapsed = !state.standaloneCollapsed;
      await rerender();
      return;
    }
    const entryChip = e.target.closest('.entry-chip');
    const clusterHeader = e.target.closest('.cluster-header');
    const ghostAnchor = e.target.closest('.ghost-anchor');
    const hero = e.target.closest('.hero-card');
    const file = e.target.closest('.file-card');
    if (ghostAnchor) {
      const g = ghostAnchor.getAttribute('data-anchor-group');
      if (!g) return;
      if (anchorClickTimer) clearTimeout(anchorClickTimer);
      anchorClickTimer = setTimeout(() => {
        anchorClickTimer = null;
        // Single-click (after dblclick window): toggle the pin. Pinning moves
        // attention to the group level, so any active file selection is
        // cleared (mirrors how selecting a file clears the pin).
        state.pinnedGroup = state.pinnedGroup === g ? null : g;
        if (state.pinnedGroup) {
          state.selected = null;
          state.hoveredGroup = null;
          state.hoveredFile = null;
        }
        syncChrome();
        rerender();
      }, 240);
      return;
    }
    if (entryChip) {
      const id = entryChip.getAttribute('data-node');
      if (id) await setSelected(state.selected === id ? null : id);
      return;
    }
    if (clusterHeader) {
      const id = clusterHeader.getAttribute('data-target');
      if (id) await setSelected(state.selected === id ? null : id);
      return;
    }
    if (hero) {
      const groupId = hero.getAttribute('data-group');
      if (!groupId) return;
      if (heroClickTimer) clearTimeout(heroClickTimer);
      heroClickTimer = setTimeout(() => {
        heroClickTimer = null;
        const next = state.focusedGroup === groupId ? null : groupId;
        setFocusedGroup(next);
      }, 240);
      return;
    }
    if (file) {
      const id = file.getAttribute('data-node');
      if (!id) return;
      if (fileClickTimer) clearTimeout(fileClickTimer);
      fileClickTimer = setTimeout(() => {
        fileClickTimer = null;
        setSelected(state.selected === id ? null : id);
      }, 240);
      return;
    }
    // Click on empty canvas background: first drop any pin, then equivalent
    // to "back to overview" if still engaged.
    if (state.pinnedGroup) {
      state.pinnedGroup = null;
      await rerender();
      return;
    }
    if (state.focusedGroup || state.selected) {
      await setFocusedGroup(null);
    }
  });
  // Minimap hover tracking: illuminate the hovered block's group in the
  // bottom-right overview. Works off mouseover (bubbles) so we only install a
  // single listener. Targets: file cards (group = file's group), hero cards,
  // ghost anchors (external group), and cluster headers (points at a file
  // whose group is external). Only active inside a focused group.
  const hoverGroupFromTarget = (target) => {
    const ghost = target.closest('.ghost-anchor');
    if (ghost) return ghost.getAttribute('data-anchor-group');
    const cluster = target.closest('.cluster-header');
    if (cluster) {
      const tid = cluster.getAttribute('data-target');
      const node = tid ? index.byId[tid] : null;
      if (node) return node.group || 'Ungrouped';
    }
    const file = target.closest('.file-card');
    if (file) {
      const id = file.getAttribute('data-node');
      const node = id ? index.byId[id] : null;
      if (node) return node.group || 'Ungrouped';
    }
    const hero = target.closest('.hero-card');
    if (hero) return hero.getAttribute('data-group');
    return null;
  };
  canvas.addEventListener('mouseover', (e) => {
    if (!state.focusedGroup) return;
    const g = hoverGroupFromTarget(e.target);
    if (g) miniMap.setHighlight(g);
  });
  canvas.addEventListener('mouseout', (e) => {
    if (!state.focusedGroup) return;
    const to = e.relatedTarget;
    if (to && canvas.contains(to) && hoverGroupFromTarget(to)) return;
    miniMap.clearHighlight();
  });

  canvas.addEventListener('dblclick', (e) => {
    if (heroClickTimer) { clearTimeout(heroClickTimer); heroClickTimer = null; }
    if (anchorClickTimer) { clearTimeout(anchorClickTimer); anchorClickTimer = null; }
    if (fileClickTimer) { clearTimeout(fileClickTimer); fileClickTimer = null; }
    const hero = e.target.closest('.hero-card');
    const ghost = e.target.closest('.ghost-anchor');
    const file = e.target.closest('.file-card');
    if (ghost) {
      // Double-click teleports to the external group. Undo the pin first so
      // the new focus starts clean (pin belonged to the previous context).
      const g = ghost.getAttribute('data-anchor-group');
      if (g) setFocusedGroup(g);
      return;
    }
    if (hero) {
      const groupId = hero.getAttribute('data-group');
      if (groupId) setFocusedGroup(groupId);
      return;
    }
    if (file) {
      const id = file.getAttribute('data-node');
      if (id) PX.ui.flowModal({ nodeId: id, graph, index, groupsMeta });
    }
  });

  // Hover: highlight aggregate arrows in the overview AND per-file arrows
  // when hovering a file card in a focused group story.
  let hoverTimer = null;
  canvas.addEventListener('mouseover', (e) => {
    const hero = e.target.closest('.hero-card');
    const ghost = e.target.closest('.ghost-anchor');
    const file = e.target.closest('.file-card');
    const gid = hero?.getAttribute('data-group')
      || ghost?.getAttribute('data-anchor-group')
      || null;
    const fid = file?.getAttribute('data-node') || null;
    if (gid === state.hoveredGroup && fid === state.hoveredFile) return;

    if (hoverTimer) clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => {
      state.hoveredGroup = gid;
      state.hoveredFile = fid;
      rerender();
    }, 40);
  });
  canvas.addEventListener('mouseout', (e) => {
    if (e.relatedTarget && e.currentTarget.contains(e.relatedTarget)) {
      const rel = e.relatedTarget;
      if (rel.closest('.hero-card,.ghost-anchor,.file-card')) return;
    }
    if (hoverTimer) clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => {
      if (state.hoveredGroup !== null || state.hoveredFile !== null) {
        state.hoveredGroup = null;
        state.hoveredFile = null;
        rerender();
      }
    }, 40);
  });

  // Editor opener: shared by canvas (space on selected file card) and
  // explorer (space on selected entry, or double-click).
  const openEditor = (id) => {
    if (!id || !index.byId[id]) return;
    PX.ui.codeEditor({ nodeId: id, graph, index });
  };

  // Keyboard
  window.addEventListener('keydown', (e) => {
    const typing = document.activeElement && (
      document.activeElement.tagName === 'INPUT' ||
      document.activeElement.tagName === 'TEXTAREA' ||
      document.activeElement.isContentEditable
    );
    // Skip shell shortcuts when an overlay (editor/flow-modal) is open.
    const modalOpen = document.body.querySelector('#px-editor-card, #px-flow-card');
    if (e.key === '/' && !typing) {
      e.preventDefault();
      side.focusFilter();
    } else if ((e.key === ' ' || e.code === 'Space') && !typing && !modalOpen) {
      if (state.selected) {
        e.preventDefault();
        openEditor(state.selected);
      }
    } else if (e.key === 'Escape') {
      const overlay = document.querySelector('#px-shell + *, body > div > div[style*="backdrop-filter"]');
      if (overlay && overlay.textContent.includes('Flow')) { overlay.remove(); return; }
      if (state.pinnedGroup) {
        state.pinnedGroup = null;
        rerender();
      } else if (state.selected) {
        setSelected(null);
      } else if (state.focusedGroup) {
        setFocusedGroup(null);
      }
    }
  });

  // ── Render loop ───────────────────────────────────────────────────
  async function rerender() {
    applyZoom();
    if (!canvas.innerHTML || canvas.innerHTML.includes('Laying out')) {
      canvas.innerHTML = `<div style="padding:16px;font-family:${T.mono};font-size:11px;color:${T.inkFaint}">Laying out \u2026</div>`;
    }
    try {
      // Pinned anchor groups act like a sticky hover — merge into the
      // effective hoveredGroup passed to views. Transient hover wins while
      // the cursor is over a group target.
      const effectiveGroup = state.hoveredGroup || state.pinnedGroup;
      const view = state.focusedGroup
        ? await PX.views.focused(graph, {
          showBullets: state.showBullets,
          selected: state.selected,
          filter: state.filter,
          index,
          focusedGroup: state.focusedGroup,
          hoveredGroup: effectiveGroup,
          hoveredFile: state.hoveredFile,
          standaloneCollapsed: state.standaloneCollapsed,
        })
        : await PX.views.groupMap(graph, {
          selected: state.selected,
          index,
          focusedGroup: null,
          hoveredGroup: effectiveGroup,
        });
      const mode = state.focusedGroup ? 'focused' : 'overview';
      canvas.innerHTML = view.svg;
      PX.log(`[prefxplain] rendered ${mode}: ${view.W}x${view.H}`);
    } catch (err) {
      console.error('[prefxplain] render failed:', err);
      canvas.innerHTML = '';
      const box = document.createElement('div');
      box.style.cssText = `padding:24px;color:${T.danger};font-family:monospace`;
      box.textContent = `Render error: ${err && err.message ? err.message : String(err)}`;
      canvas.appendChild(box);
    }
  }

  syncChrome();
  await rerender();
})();
