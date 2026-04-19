// ui/minimap.js — Overview minimap shown inside a focused group in nested mode.
// Miniature of the full group-map diagram (real positions + aggregate arrows)
// so the viewer can see where the focused group sits in the overall
// architecture and never feels "blind" when drilled into a child view.
//
// Layout is computed with ELK once (lazily, on first show) and cached for the
// rest of the session. Paint runs are DOM-only after that.

window.PX = window.PX || {};
PX.ui = PX.ui || {};

PX.ui.minimap = function minimap(container, { graph, groupsMeta }) {
  const T = PX.T;
  let _layout = null;          // { groups[], edges[], bbox }
  let _layoutPromise = null;
  let _focused = null;
  let _highlight = null;
  let _visible = false;
  let _collapsed = false;

  const wrap = document.createElement('div');
  wrap.style.cssText = `display:none;padding:8px 10px 10px;background:${T.panel};border:1px solid ${T.border};border-radius:8px;box-shadow:0 4px 14px rgba(0,0,0,0.35);width:260px;user-select:none`;

  const header = document.createElement('div');
  header.style.cssText = `display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:6px`;
  const titleBox = document.createElement('div');
  titleBox.style.cssText = `display:flex;flex-direction:column;line-height:1.15;min-width:0`;
  const title = document.createElement('span');
  title.textContent = 'Overview';
  title.style.cssText = `color:${T.inkFaint};font-family:${T.mono};font-size:9px;letter-spacing:1.2px;text-transform:uppercase`;
  titleBox.appendChild(title);
  const hint = document.createElement('span');
  hint.textContent = 'you are here';
  hint.style.cssText = `color:${T.inkFaint};font-family:${T.ui};font-size:9.5px;font-style:italic;margin-top:2px`;
  titleBox.appendChild(hint);
  header.appendChild(titleBox);

  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button';
  toggleBtn.style.cssText = `background:${T.panelAlt};border:1px solid ${T.border};border-radius:4px;color:${T.ink};font-family:${T.mono};font-size:13px;line-height:1;padding:2px 8px;cursor:pointer;flex-shrink:0`;
  toggleBtn.onmouseenter = () => { toggleBtn.style.background = T.pill || T.panelAlt; };
  toggleBtn.onmouseleave = () => { toggleBtn.style.background = T.panelAlt; };
  toggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    _collapsed = !_collapsed;
    applyCollapsedUi();
    if (!_collapsed && _visible) render();
  });
  header.appendChild(toggleBtn);
  wrap.appendChild(header);

  const svgHost = document.createElement('div');
  svgHost.style.cssText = 'line-height:0';
  wrap.appendChild(svgHost);
  container.appendChild(wrap);

  const applyCollapsedUi = () => {
    toggleBtn.textContent = _collapsed ? '+' : '\u2212';
    toggleBtn.title = _collapsed ? 'Expand overview' : 'Collapse overview';
    toggleBtn.setAttribute('aria-label', _collapsed ? 'Expand overview' : 'Collapse overview');
    toggleBtn.setAttribute('aria-expanded', _collapsed ? 'false' : 'true');
    hint.style.display = _collapsed ? 'none' : '';
    svgHost.style.display = _collapsed ? 'none' : '';
    wrap.style.width = _collapsed ? 'auto' : '260px';
  };
  applyCollapsedUi();

  const computeLayout = () => {
    if (_layout) return Promise.resolve(_layout);
    if (_layoutPromise) return _layoutPromise;
    _layoutPromise = (async () => {
      try {
        const ir = PX.buildIr(graph, 'group-map');
        ir.layoutOptions = { 'elk.aspectRatio': '1.4' };
        const laid = await PX.runLayout(ir);
        const groups = (laid.children || []).map(b => ({
          id: b.id,
          x: b.x || 0,
          y: b.y || 0,
          w: b.width || 0,
          h: b.height || 0,
        }));
        const polylines = PX.extractEdgePolylines(laid);
        const edges = polylines.map(p => {
          const src = PX.splitPortId(p.source).nodeId;
          const tgt = PX.splitPortId(p.target).nodeId;
          return { id: p.id, source: src, target: tgt, points: p.points || [] };
        });
        let minX = 0, minY = 0;
        let maxX = laid.width || 1000;
        let maxY = laid.height || 800;
        for (const g of groups) {
          if (g.x < minX) minX = g.x;
          if (g.y < minY) minY = g.y;
          if (g.x + g.w > maxX) maxX = g.x + g.w;
          if (g.y + g.h > maxY) maxY = g.y + g.h;
        }
        for (const e of edges) {
          for (const p of e.points) {
            if (p.x < minX) minX = p.x;
            if (p.y < minY) minY = p.y;
            if (p.x > maxX) maxX = p.x;
            if (p.y > maxY) maxY = p.y;
          }
        }
        _layout = { groups, edges, minX, minY, maxX, maxY };
        return _layout;
      } catch (err) {
        console.warn('[prefxplain] minimap layout failed:', err);
        return null;
      }
    })();
    return _layoutPromise;
  };

  const MINIMAP_W = 244;

  const render = async () => {
    if (!_visible) { wrap.style.display = 'none'; return; }
    wrap.style.display = 'block';
    if (_collapsed) return;
    const lay = await computeLayout();
    if (!lay || lay.groups.length === 0) { wrap.style.display = 'none'; return; }
    const pad = 12;
    const vbX = lay.minX - pad;
    const vbY = lay.minY - pad;
    const W = (lay.maxX - lay.minX) + 2 * pad;
    const H = (lay.maxY - lay.minY) + 2 * pad;
    // Text targets ~10.5px rendered regardless of layout density.
    const displayScale = MINIMAP_W / W;
    const fontSize = Math.max(14, 11 / displayScale);
    const stripeH = Math.max(10, 9 / displayScale);
    const radius = Math.max(4, 7 / displayScale);
    const edgeStrokeW = Math.max(1.5, 1.4 / displayScale);

    let svg = `<svg viewBox="${vbX} ${vbY} ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="display:block;width:${MINIMAP_W}px;height:auto;max-height:240px">`;

    // Arrowhead marker.
    svg += `<defs>`
      + `<marker id="px-mini-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">`
      + `<path d="M0,0 L10,5 L0,10 z" fill="${T.inkFaint}"/>`
      + `</marker>`
      + `</defs>`;

    // Edges first (so they sit behind boxes).
    for (const e of lay.edges) {
      if (!e.points || e.points.length < 2) continue;
      const touchesFocus = _focused && (e.source === _focused || e.target === _focused);
      const touchesHighlight = _highlight && (e.source === _highlight || e.target === _highlight);
      const strokeCol = touchesFocus ? T.accent : (touchesHighlight ? T.accent2 : T.borderAlt);
      const strokeOp = touchesFocus ? 0.9 : (touchesHighlight ? 0.8 : 0.4);
      const sw = touchesFocus || touchesHighlight ? edgeStrokeW * 1.7 : edgeStrokeW;
      const d = e.points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
      svg += `<path d="${d}" fill="none" stroke="${strokeCol}" stroke-width="${sw}" stroke-opacity="${strokeOp}" marker-end="url(#px-mini-arr)"/>`;
    }

    // Group boxes.
    for (const g of lay.groups) {
      const meta = groupsMeta[g.id] || {};
      const color = PX.groupColor(g.id, meta);
      const isFocused = g.id === _focused;
      const isHighlight = g.id === _highlight && !isFocused;
      const fill = isFocused ? color : T.panelAlt;
      const fillOp = isFocused ? 0.92 : 1;
      const strokeCol = isFocused ? '#ffffff' : (isHighlight ? color : T.border);
      const strokeW = isFocused ? Math.max(3, 3 / displayScale) : (isHighlight ? Math.max(2.4, 2.6 / displayScale) : Math.max(1, 1.1 / displayScale));
      const groupOpacity = _focused && !isFocused && !isHighlight ? 0.55 : 1;
      const nameCol = isFocused ? '#ffffff' : (isHighlight ? color : T.ink);
      const nameWeight = isFocused || isHighlight ? 700 : 600;

      svg += `<g opacity="${groupOpacity}" style="transition:opacity 160ms">`;
      svg += `<rect x="${g.x}" y="${g.y}" width="${g.w}" height="${g.h}" fill="${fill}" fill-opacity="${fillOp}" stroke="${strokeCol}" stroke-width="${strokeW}" rx="${radius}"/>`;
      svg += `<rect x="${g.x}" y="${g.y}" width="${g.w}" height="${stripeH}" fill="${color}" opacity="${isFocused ? 1 : 0.9}" rx="${radius}"/>`;
      const textPad = Math.max(6, 10 / displayScale);
      svg += `<foreignObject x="${g.x + textPad}" y="${g.y + stripeH + textPad / 2}" width="${Math.max(0, g.w - 2 * textPad)}" height="${Math.max(0, g.h - stripeH - textPad)}">`
        + `<div xmlns="http://www.w3.org/1999/xhtml" style="display:flex;align-items:center;justify-content:center;height:100%;font-family:${T.ui};font-size:${fontSize}px;font-weight:${nameWeight};color:${nameCol};text-align:center;line-height:1.15;overflow:hidden;word-break:break-word">${PX.escapeXml(g.id)}</div>`
        + `</foreignObject>`;
      svg += `</g>`;
    }

    svg += `</svg>`;
    svgHost.innerHTML = svg;
  };

  return {
    setFocused(groupId) {
      _focused = groupId || null;
      _highlight = null;
      _visible = !!_focused;
      render();
    },
    setHighlight(groupId) {
      if (_highlight === groupId) return;
      _highlight = groupId || null;
      if (_visible) render();
    },
    clearHighlight() {
      if (_highlight == null) return;
      _highlight = null;
      if (_visible) render();
    },
  };
};
