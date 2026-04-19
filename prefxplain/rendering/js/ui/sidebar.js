// ui/sidebar.js — left explorer with filter input + collapsible groups,
// and a top-left collapse/expand button. When collapsed the sidebar
// shrinks to a 32px rail so the toggle stays reachable. State persists
// in localStorage so reloading keeps the user's preference.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

const STORAGE_KEY = 'px-sidebar-collapsed';

PX.ui.sidebar = function sidebar(container, { graph, groupsMeta, index }) {
  const T = PX.T;
  container.innerHTML = '';
  const aside = document.createElement('aside');
  aside.style.cssText = `flex-shrink:0;height:100%;min-height:0;background:${T.panel};border-right:1px solid ${T.border};display:flex;flex-direction:column;font-family:${T.ui};font-size:12.5px;transition:width 180ms ease`;

  let collapsed = false;
  try { collapsed = localStorage.getItem(STORAGE_KEY) === '1'; } catch {}

  // Header row: toggle + "Explorer · N files" label.
  const header = document.createElement('div');
  header.style.cssText = `display:flex;align-items:center;gap:6px;padding:8px 10px;border-bottom:1px solid ${T.border};flex-shrink:0`;
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.title = 'Collapse explorer';
  toggle.style.cssText = `display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;padding:0;background:${T.panelAlt};border:1px solid ${T.border};border-radius:4px;color:${T.inkMuted};font-family:${T.mono};font-size:12px;cursor:pointer;flex-shrink:0`;
  const headerLabel = document.createElement('span');
  headerLabel.style.cssText = `font-family:${T.mono};font-size:9.5px;letter-spacing:1.4px;color:${T.inkFaint};text-transform:uppercase;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap`;
  headerLabel.textContent = `Explorer \u00b7 ${graph.nodes.length} files`;
  header.appendChild(toggle);
  header.appendChild(headerLabel);
  aside.appendChild(header);

  const filterBox = document.createElement('div');
  filterBox.style.cssText = `padding:10px;border-bottom:1px solid ${T.border}`;
  const input = document.createElement('input');
  input.id = 'px-filter';
  input.placeholder = 'filter files\u2026 (/)';
  input.style.cssText = `width:100%;padding:6px 9px;background:${T.bg};border:1px solid ${T.border};color:${T.ink};font-family:${T.mono};font-size:11px;outline:none;border-radius:4px`;
  input.addEventListener('focus', () => { input.style.borderColor = T.accent; });
  input.addEventListener('blur', () => { input.style.borderColor = T.border; });
  filterBox.appendChild(input);
  aside.appendChild(filterBox);

  const listHost = document.createElement('div');
  listHost.className = 'px-explorer-list';
  // min-height:0 is required for `flex:1 + overflow` to actually scroll inside
  // a flex column. overflow-y:scroll (not auto) keeps the track visible so
  // users immediately see the explorer is scrollable.
  listHost.style.cssText = `flex:1;min-height:0;overflow-y:scroll;padding:6px 0 30px`;
  aside.appendChild(listHost);

  const listeners = { onSelect: [], onSelectGroup: [], onFilter: [], onToggle: [], onOpen: [] };
  let selected = null;
  let focusedGroup = null;
  let lastNodeClickId = null;
  let lastNodeClickTs = 0;
  const openGroups = {};
  const groups = ((index && index.groupOrder) || [...new Set((graph.nodes || []).map(n => n.group || 'Ungrouped'))]).slice();
  for (const g of groups) openGroups[g] = true;

  const applyCollapsed = () => {
    aside.style.width = collapsed ? '32px' : '240px';
    filterBox.style.display = collapsed ? 'none' : 'block';
    listHost.style.display = collapsed ? 'none' : 'block';
    headerLabel.style.display = collapsed ? 'none' : 'inline';
    toggle.textContent = collapsed ? '\u25b8' : '\u25c2';
    toggle.title = collapsed ? 'Expand explorer' : 'Collapse explorer';
    toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    try { localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0'); } catch {}
    for (const fn of listeners.onToggle) fn(collapsed);
  };

  toggle.addEventListener('click', () => { collapsed = !collapsed; applyCollapsed(); });
  applyCollapsed();

  const render = () => {
    const filter = input.value.trim().toLowerCase();
    let html = '';
    for (const g of groups) {
      const meta = groupsMeta[g] || {};
      const color = PX.groupColor(g, meta);
      const orderedIds = (((index || {}).groupStats || {})[g] || {}).orderedFileIds
        || (((index || {}).groupFiles || {})[g])
        || (graph.nodes || []).filter(n => (n.group || 'Ungrouped') === g).map(n => n.id);
      const files = orderedIds
        .map(id => (index && index.byId ? index.byId[id] : null) || (graph.nodes || []).find(n => n.id === id))
        .filter(Boolean)
        .filter(n => !filter || n.label.toLowerCase().includes(filter) || (n.description || '').toLowerCase().includes(filter));
      if (filter && files.length === 0) continue;
      const isOpen = openGroups[g];
      const focusBg = focusedGroup === g ? T.accentTint : 'transparent';
      const focusBorder = focusedGroup === g ? T.accent : 'transparent';
      html += `<div style="display:flex;align-items:center;gap:4px;padding:2px 10px 2px 8px">
        <button data-group-toggle="${PX.escapeXml(g)}" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;padding:0;background:transparent;border:none;color:${T.inkFaint};font-size:9px;cursor:pointer">${isOpen ? '\u25be' : '\u25b8'}</button>
        <button data-group-focus="${PX.escapeXml(g)}" style="display:flex;align-items:center;gap:6px;flex:1;min-width:0;padding:5px 8px;background:${focusBg};border:none;border-left:2px solid ${focusBorder};color:${T.ink};font-family:${T.ui};font-size:11.5px;font-weight:500;cursor:pointer;text-align:left;border-radius:4px">
          <span style="width:8px;height:8px;border-radius:2px;background:${color};flex-shrink:0"></span>
          <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${PX.escapeXml(g)}</span>
          <span style="color:${T.inkFaint};font-family:${T.mono};font-size:10px">${files.length}</span>
        </button>
      </div>`;
      if (isOpen) {
        for (const f of files) {
          const sel = selected === f.id;
          const entryFlag = f.role === 'entry_point' ? `<span style="font-size:8.5px;color:${T.accent}">ENTRY</span>` : '';
          const bridgeCount = (((index || {}).fileBridgeIn || {})[f.id] || 0) + (((index || {}).fileBridgeOut || {})[f.id] || 0);
          const bridgeFlag = bridgeCount > 0 ? `<span style="font-size:8.5px;color:${T.good}">\u2194${bridgeCount}</span>` : '';
          html += `<button data-node="${PX.escapeXml(f.id)}" style="display:flex;align-items:center;gap:6px;width:100%;padding:3px 14px 3px 34px;background:${sel ? T.accentTint : 'transparent'};border:none;border-left:2px solid ${sel ? T.accent : 'transparent'};color:${sel ? T.ink : T.ink2};font-family:${T.mono};font-size:11px;cursor:pointer;text-align:left">
            <span style="color:${T.inkFaint};font-size:10px">\u2397</span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${PX.escapeXml(f.label)}</span>
            ${bridgeFlag}${entryFlag}
          </button>`;
        }
      }
    }
    listHost.innerHTML = html;
  };
  render();

  listHost.addEventListener('click', (e) => {
    const btnToggle = e.target.closest('button[data-group-toggle]');
    const btnG = e.target.closest('button[data-group-focus]');
    const btnN = e.target.closest('button[data-node]');
    if (btnToggle) {
      const g = btnToggle.getAttribute('data-group-toggle');
      openGroups[g] = !openGroups[g];
      render();
      return;
    }
    if (btnG) {
      const g = btnG.getAttribute('data-group-focus');
      focusedGroup = focusedGroup === g ? null : g;
      render();
      for (const fn of listeners.onSelectGroup) fn(focusedGroup);
      return;
    }
    if (btnN) {
      const id = btnN.getAttribute('data-node');
      const now = Date.now();
      const isDoubleClick = lastNodeClickId === id && (now - lastNodeClickTs) <= 320;
      lastNodeClickId = isDoubleClick ? null : id;
      lastNodeClickTs = isDoubleClick ? 0 : now;

      if (selected !== id) {
        for (const fn of listeners.onSelect) fn(id);
      }
      if (isDoubleClick) {
        for (const fn of listeners.onOpen) fn(id);
      }
      return;
    }
  });

  input.addEventListener('input', () => {
    render();
    for (const fn of listeners.onFilter) fn(input.value);
  });

  container.appendChild(aside);
  return {
    setSelected: (id) => { selected = id; render(); },
    setFocusedGroup: (groupId) => { focusedGroup = groupId; render(); },
    focusFilter: () => { if (collapsed) { collapsed = false; applyCollapsed(); } input.focus(); },
    toggle: () => { collapsed = !collapsed; applyCollapsed(); },
    isCollapsed: () => collapsed,
    onSelect: (fn) => listeners.onSelect.push(fn),
    onOpen: (fn) => listeners.onOpen.push(fn),
    onSelectGroup: (fn) => listeners.onSelectGroup.push(fn),
    onFilter: (fn) => listeners.onFilter.push(fn),
    onToggle: (fn) => listeners.onToggle.push(fn),
  };
};
