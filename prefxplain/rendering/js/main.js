// main.js — entry point. Phase 6: full UI chrome wired.
//   - Top info bar (selection-driven)
//   - View switcher (Group map / Nested)
//   - Left sidebar explorer with filter
//   - Main SVG canvas
//   - Bottom legend
//   - Flow modal on double-click
//   - Keyboard: '/' focus filter, Escape deselect, dbl-click card -> flow

(async function main() {
  const root = document.getElementById('root');
  if (!root) return;

  const graph = window.__PREFXPLAIN_GRAPH__;
  if (!graph || !Array.isArray(graph.nodes)) {
    root.innerHTML = '<div style="padding:24px;color:#f85149">No graph payload found.</div>';
    return;
  }
  if (typeof ELK === 'undefined') {
    root.innerHTML = '<div style="padding:24px;color:#f85149">ELK failed to load.</div>';
    return;
  }

  const T = PX.T;
  const index = PX.buildGraphIndex(graph);
  const groupsMeta = graph.metaGroups || {};

  const state = {
    viewMode: 'group-map',
    showBullets: true,
    selected: null,
    filter: '',
    focusedGroup: null,
    hoveredGroup: null,
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
  // Zoom is tracked per view so each keeps its own scale across toggles.
  const zoomState = { 'group-map': 1, nested: 1 };
  const zoomPanel = document.createElement('div');
  zoomPanel.style.cssText = `display:flex;align-items:center;gap:4px;padding:4px;background:${T.panel};border:1px solid ${T.border};border-radius:8px;font-family:${T.mono};color:${T.ink};box-shadow:0 4px 14px rgba(0,0,0,0.35);user-select:none;pointer-events:auto`;
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
    const effective = zoomState[state.viewMode] ?? 1;
    canvas.style.setProperty('--px-zoom', effective);
  };
  const setZoom = (next) => {
    zoomState[state.viewMode] = next;
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
  const switcher = PX.ui.viewSwitcher(switchHost, {
    value: state.viewMode,
    onChange: async (v) => { state.viewMode = v; syncChrome(); await rerender(); },
  });
  const side = PX.ui.sidebar(sideHost, { graph, groupsMeta, index });
  PX.ui.legend(legendHost);

  // ── Wiring ────────────────────────────────────────────────────────
  const syncChrome = () => {
    top.setSelected(state.selected);
    top.setFocusedGroup(state.focusedGroup);
    side.setSelected(state.selected);
    side.setFocusedGroup(state.focusedGroup);
    switcher.setValue(state.viewMode);
    // Minimap only relevant inside a focused group in nested mode.
    const showMinimap = state.viewMode === 'nested' && state.focusedGroup;
    miniMap.setFocused(showMinimap ? state.focusedGroup : null);
  };
  const setSelected = async (id) => {
    state.selected = id;
    if (id && index.byId[id]) {
      state.focusedGroup = (index.byId[id].group || 'Ungrouped');
    }
    syncChrome();
    await rerender();
  };
  const setFocusedGroup = async (groupId, { switchView = true } = {}) => {
    state.focusedGroup = groupId;
    if (!groupId) {
      state.selected = null;
    } else if (state.selected) {
      const selGroup = ((index.byId[state.selected] || {}).group || 'Ungrouped');
      if (selGroup !== groupId) state.selected = null;
    }
    if (switchView && groupId) state.viewMode = 'nested';
    syncChrome();
    await rerender();
  };
  side.onSelect((id) => setSelected(id));
  side.onOpen((id) => openEditor(id));
  side.onSelectGroup((groupId) => setFocusedGroup(groupId, { switchView: true }));
  side.onFilter((v) => { state.filter = v; rerender(); });
  top.onDeselect(() => setSelected(null));
  top.onClearFocus(() => setFocusedGroup(null, { switchView: false }));

  // Hero single-click: just highlight the group's links in Group map (toggle).
  // Hero double-click: drill into Nested with that group focused. Debounce the
  // single-click so dblclick preempts it without flicker.
  let heroClickTimer = null;
  canvas.addEventListener('click', async (e) => {
    const entryChip = e.target.closest('.entry-chip');
    const clusterHeader = e.target.closest('.cluster-header');
    const ghostAnchor = e.target.closest('.ghost-anchor');
    const hero = e.target.closest('.hero-card');
    const group = e.target.closest('.group-container');
    const file = e.target.closest('.file-card');
    if (ghostAnchor) {
      const g = ghostAnchor.getAttribute('data-anchor-group');
      if (g) await setFocusedGroup(g, { switchView: false });
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
        setFocusedGroup(next, { switchView: false });
      }, 240);
      return;
    }
    if (group) {
      const groupId = group.getAttribute('data-group');
      if (groupId) await setFocusedGroup(groupId, { switchView: false });
      return;
    }
    if (file) {
      const id = file.getAttribute('data-node');
      if (id) await setSelected(state.selected === id ? null : id);
      return;
    }
    // Click on empty canvas background: equivalent to "back to overview".
    if (state.focusedGroup || state.selected) {
      await setFocusedGroup(null, { switchView: false });
    }
  });
  // Minimap hover tracking: illuminate the hovered block's group in the
  // bottom-right overview. Works off mouseover (bubbles) so we only install a
  // single listener. Targets: file cards (group = file's group), group
  // containers, ghost anchors (external group), and cluster headers (points
  // at a file whose group is external).
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
    const group = target.closest('.group-container,.hero-card');
    if (group) return group.getAttribute('data-group');
    return null;
  };
  canvas.addEventListener('mouseover', (e) => {
    if (!(state.viewMode === 'nested' && state.focusedGroup)) return;
    const g = hoverGroupFromTarget(e.target);
    if (g) miniMap.setHighlight(g);
  });
  canvas.addEventListener('mouseout', (e) => {
    if (!(state.viewMode === 'nested' && state.focusedGroup)) return;
    const to = e.relatedTarget;
    if (to && canvas.contains(to) && hoverGroupFromTarget(to)) return;
    miniMap.clearHighlight();
  });

  canvas.addEventListener('dblclick', (e) => {
    if (heroClickTimer) { clearTimeout(heroClickTimer); heroClickTimer = null; }
    const hero = e.target.closest('.hero-card');
    const file = e.target.closest('.file-card');
    if (hero) {
      const groupId = hero.getAttribute('data-group');
      if (groupId) setFocusedGroup(groupId, { switchView: true });
      return;
    }
    if (file) {
      const id = file.getAttribute('data-node');
      if (id) PX.ui.flowModal({ nodeId: id, graph, index, groupsMeta });
    }
  });

  // Hover: highlight group connections in Overview/GroupMap
  let hoverTimer = null;
  canvas.addEventListener('mouseover', (e) => {
    const hero = e.target.closest('.hero-card');
    const group = e.target.closest('.group-container');
    const ghost = e.target.closest('.ghost-anchor');
    const gid = (hero || group)?.getAttribute('data-group') || ghost?.getAttribute('data-anchor-group');
    if (gid === state.hoveredGroup) return;

    if (hoverTimer) clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => {
      state.hoveredGroup = gid || null;
      rerender();
    }, 40);
  });
  canvas.addEventListener('mouseout', (e) => {
    if (e.relatedTarget && e.currentTarget.contains(e.relatedTarget)) {
      const hero = e.relatedTarget.closest('.hero-card');
      const group = e.relatedTarget.closest('.group-container');
      const ghost = e.relatedTarget.closest('.ghost-anchor');
      if (hero || group || ghost) return;
    }
    if (hoverTimer) clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => {
      if (state.hoveredGroup !== null) {
        state.hoveredGroup = null;
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
      if (state.selected) {
        setSelected(null);
      } else if (state.focusedGroup) {
        setFocusedGroup(null, { switchView: false });
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
      const view = state.viewMode === 'nested'
        ? await PX.views.nested(graph, {
          showBullets: state.showBullets,
          selected: state.selected,
          filter: state.filter,
          index,
          focusedGroup: state.focusedGroup,
          hoveredGroup: state.hoveredGroup,
        })
        : await PX.views.groupMap(graph, {
          selected: state.selected,
          index,
          focusedGroup: state.focusedGroup,
          hoveredGroup: state.hoveredGroup,
        });
      canvas.innerHTML = view.svg;
      console.log(`[prefxplain] rendered ${state.viewMode}: ${view.W}x${view.H}`);
    } catch (err) {
      console.error('[prefxplain] render failed:', err);
      canvas.innerHTML = `<div style="padding:24px;color:${T.danger};font-family:monospace">Render error: ${err.message}</div>`;
    }
  }

  syncChrome();
  await rerender();
})();
