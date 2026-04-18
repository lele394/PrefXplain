// ir.js — Graph (Python JSON) → ELK input.
// Ports are FIXED_SIDE: every node exposes a NORTH "in" port and a SOUTH "out"
// port. Every edge references the `source.out` and `target.in` port ids, so
// ELK enters cards from the top and leaves from the bottom (cohérent with
// "top imports bottom" in the layered view).
//
// Two view modes produce two different ELK trees:
//
//   group-map: only group nodes at top level (hero cards, 320×180).
//              Edges are aggregated group-to-group with a `count` property.
//
//   nested:    groups are compound nodes containing their files as children.
//              File nodes carry the real card dimensions (220×92 or 220×52).
//              Edges keep file-to-file granularity; ELK draws them across
//              the hierarchy because hierarchyHandling: INCLUDE_CHILDREN.
//
//   group-detail: file-only layout for one focused group. Used by the split
//              Nested view's right-hand detail pane.
//
// Sizes come from tokens defined inline here so layout.js stays purely about
// options; the visual components can read the same constants later.

window.PX = window.PX || {};

PX.NODE_SIZES = {
  hero:        { w: 320, h: 180 },
  nestedGroup: { w: 320, h: 144 },
  // Rail size: used when the overview is collapsed into a compact sidebar
  // next to the focused detail panel. Just enough to show name + stripe +
  // file count. Dramatically less real estate than a full nested card.
  railGroup:   { w: 184, h: 72 },
  // File cards need room for: row 1 (glyph + filename + bridge badge + size
  // dots + size), row 2 (subtitle), row 3 (up to 2 highlights), row 4
  // (IN/OUT bars). The old 220×92 cramped filenames ≥20 chars; 304×132 is
  // wide enough for full filenames and tall enough to breathe.
  fileBullets: { w: 304, h: 132 },
  fileNoBullets:{ w: 304, h: 64 },
};

function _port(nodeId, side) {
  return {
    id: `${nodeId}.${side === 'NORTH' ? 'in' : 'out'}`,
    properties: { 'port.side': side },
  };
}

function _makeNode(id, w, h) {
  return {
    id,
    width: w,
    height: h,
    ports: [_port(id, 'NORTH'), _port(id, 'SOUTH')],
    properties: { 'org.eclipse.elk.portConstraints': 'FIXED_SIDE' },
  };
}

function _groupsOf(nodes) {
  const seen = new Set();
  const order = [];
  for (const n of nodes) {
    const g = n.group || 'Ungrouped';
    if (!seen.has(g)) { seen.add(g); order.push(g); }
  }
  return order;
}

// Char-width estimates for the 3-line colored labels. Must stay in sync
// with the rendering in components/edge.js — drift between the layout
// dimensions and the drawn dimensions is what causes labels to overflow
// their reserved ELK slot.
const LABEL_CH_BOLD = 8.2;
const LABEL_CH_REG = 7.6;
const LABEL_HEIGHT = 50;
const LABEL_PADDING = 26;

function _labelDims(sourceName, targetName, count) {
  const line1 = `[${sourceName}]`;
  const line2 = `imports ${count}\u00d7`;
  const line3 = `[${targetName}]`;
  const w = Math.max(
    line1.length * LABEL_CH_BOLD,
    line2.length * LABEL_CH_REG,
    line3.length * LABEL_CH_BOLD,
  ) + LABEL_PADDING;
  return { width: Math.ceil(w), height: LABEL_HEIGHT };
}

// Aggregate edges with UNIQUE ports per edge. Sharing ports (`$group.out`
// for all outgoing edges of a group) forces ELK to stack edges through the
// same point, which produces the "traffic jam" look where multiple edges
// hug the same x-column and have to snake around each others' labels. With
// per-edge ports, ELK's FIXED_SIDE port constraint distributes each port
// along the node side (NORTH for incoming, SOUTH for outgoing), and each
// edge gets its own corridor from source to target.
function _aggregateGroupEdges(graph, byId) {
  const counts = {};
  for (const e of graph.edges) {
    const a = (byId[e.source] || {}).group || 'Ungrouped';
    const b = (byId[e.target] || {}).group || 'Ungrouped';
    if (a === b) continue;
    const k = `${a}\u0000${b}`;
    counts[k] = (counts[k] || 0) + 1;
  }
  return Object.entries(counts).map(([k, count], i) => {
    const [source, target] = k.split('\u0000');
    const dims = _labelDims(source, target, count);
    return {
      id: `ge${i}`,
      sources: [`${source}.out-ge${i}`],
      targets: [`${target}.in-ge${i}`],
      sourceGroupName: source,
      targetGroupName: target,
      count,
      labels: [{ text: '', width: dims.width, height: dims.height }],
    };
  });
}

// Build the list of ports a group node needs based on which aggregate edges
// connect to it. Incoming edges → NORTH ports, outgoing → SOUTH. Order in
// the array doesn't matter under FIXED_SIDE — ELK reorders to minimise
// crossings.
function _portsForGroup(groupName, aggregateEdges) {
  const ports = [];
  for (const e of aggregateEdges) {
    if (e.sourceGroupName === groupName) {
      ports.push({ id: e.sources[0], properties: { 'port.side': 'SOUTH' } });
    }
    if (e.targetGroupName === groupName) {
      ports.push({ id: e.targets[0], properties: { 'port.side': 'NORTH' } });
    }
  }
  return ports;
}

PX._labelDims = _labelDims;

function _groupPort(groupId, side) {
  return `${groupId}.${side === 'NORTH' ? 'in' : 'out'}`;
}

function _orderedFileIds(index, graph, groupId) {
  const ordered = (((index || {}).groupStats || {})[groupId] || {}).orderedFileIds;
  if (Array.isArray(ordered) && ordered.length > 0) return ordered.slice();
  return (graph.nodes || [])
    .filter(n => (n.group || 'Ungrouped') === groupId)
    .map(n => n.id);
}

PX.buildGroupDetailIr = function buildGroupDetailIr(graph, groupId, {
  showBullets = true,
  index = null,
} = {}) {
  const byId = Object.fromEntries((graph.nodes || []).map(n => [n.id, n]));
  const fileSize = showBullets ? PX.NODE_SIZES.fileBullets : PX.NODE_SIZES.fileNoBullets;
  const fileIds = _orderedFileIds(index, graph, groupId);
  const children = fileIds
    .map(id => byId[id])
    .filter(Boolean)
    .map(n => _makeNode(n.id, fileSize.w, fileSize.h));
  const edges = [];
  let edgeId = 0;
  for (const e of graph.edges || []) {
    const srcGroup = (byId[e.source] || {}).group || 'Ungrouped';
    const tgtGroup = (byId[e.target] || {}).group || 'Ungrouped';
    if (srcGroup !== groupId || tgtGroup !== groupId) continue;
    edges.push({
      id: `gd${edgeId++}`,
      sources: [`${e.source}.out`],
      targets: [`${e.target}.in`],
      kind: 'internal',
      sourceNode: e.source,
      targetNode: e.target,
      sourceGroup: srcGroup,
      targetGroup: tgtGroup,
    });
  }
  return { id: 'root', children, edges };
};

PX.buildIr = function buildIr(graph, viewMode, {
  showBullets = true,
  focusedGroup = null,
  edgeDetailMode = 'focus',
  selected = null,
  index = null,
  compact = false,
} = {}) {
  const byId = Object.fromEntries((graph.nodes || []).map(n => [n.id, n]));
  if (viewMode === 'group-map') {
    const groups = _groupsOf(graph.nodes || []);
    const aggregateEdges = _aggregateGroupEdges(graph, byId);
    const children = groups.map(g => ({
      id: g,
      width: PX.NODE_SIZES.hero.w,
      height: PX.NODE_SIZES.hero.h,
      ports: _portsForGroup(g, aggregateEdges),
      properties: { 'org.eclipse.elk.portConstraints': 'FIXED_SIDE' },
    }));
    return {
      id: 'root',
      children,
      edges: aggregateEdges,
    };
  }
  if (viewMode === 'nested') {
    const groups = _groupsOf(graph.nodes || []);
    const fileSize = showBullets ? PX.NODE_SIZES.fileBullets : PX.NODE_SIZES.fileNoBullets;
    const groupNodes = groups.map((g) => {
      const isFocused = focusedGroup === g;
      const isExpanded = isFocused;
      const groupNode = {
        id: g,
        ports: [_port(g, 'NORTH'), _port(g, 'SOUTH')],
        properties: {
          'org.eclipse.elk.portConstraints': 'FIXED_SIDE',
          'org.eclipse.elk.padding': isExpanded
            ? '[top=92,left=22,bottom=20,right=22]'
            : '[top=18,left=16,bottom=18,right=16]',
        },
      };
      if (!isExpanded) {
        const size = compact ? PX.NODE_SIZES.railGroup : PX.NODE_SIZES.nestedGroup;
        groupNode.width = size.w;
        groupNode.height = size.h;
        return groupNode;
      }
      groupNode.children = _orderedFileIds(index, graph, g)
        .map(id => byId[id])
        .filter(Boolean)
        .map(n => _makeNode(n.id, fileSize.w, fileSize.h));
      return groupNode;
    });

    const edges = [];
    let edgeId = 0;
    const pushEdge = (sourcePort, targetPort, extra = {}) => {
      edges.push({
        id: `e${edgeId++}`,
        sources: [sourcePort],
        targets: [targetPort],
        ...extra,
      });
    };

    const pairStats = (index && index.groupPairStats) || [];
    const includeFocusDetails = focusedGroup && edgeDetailMode !== 'overview';
    const selectedGroup = selected && byId[selected] ? ((byId[selected].group || 'Ungrouped')) : null;
    const focusSelection = includeFocusDetails && selected && selectedGroup === focusedGroup ? selected : null;

    // Aggregate group edges remain visible for the overview and for routes
    // between non-focused groups. When a focused group is open with detail
    // edges visible, omit its aggregate connections to avoid duplicating the
    // gateway edges that replace them.
    for (const rec of pairStats) {
      if (includeFocusDetails && (rec.sourceGroup === focusedGroup || rec.targetGroup === focusedGroup)) continue;
      pushEdge(_groupPort(rec.sourceGroup, 'SOUTH'), _groupPort(rec.targetGroup, 'NORTH'), {
        count: rec.count,
        kind: 'aggregate',
        sourceGroup: rec.sourceGroup,
        targetGroup: rec.targetGroup,
      });
    }

    if (!focusedGroup) {
      return { id: 'root', children: groupNodes, edges };
    }

    const gatewayOut = {};
    const gatewayIn = {};
    for (const e of graph.edges || []) {
      const srcGroup = (byId[e.source] || {}).group || 'Ungrouped';
      const tgtGroup = (byId[e.target] || {}).group || 'Ungrouped';
      const selectedTouches = !focusSelection || e.source === focusSelection || e.target === focusSelection;
      if (!selectedTouches && edgeDetailMode === 'focus') continue;
      if (srcGroup === focusedGroup && tgtGroup === focusedGroup) {
        if (edgeDetailMode === 'debug' || (edgeDetailMode === 'focus' && focusSelection)) {
          pushEdge(`${e.source}.out`, `${e.target}.in`, {
            kind: 'internal',
            sourceNode: e.source,
            targetNode: e.target,
            sourceGroup: srcGroup,
            targetGroup: tgtGroup,
          });
        }
        continue;
      }
      if (srcGroup === focusedGroup && tgtGroup !== focusedGroup) {
        const key = `${e.source}\u0000${tgtGroup}`;
        gatewayOut[key] = gatewayOut[key] || {
          sourceNode: e.source,
          targetGroup: tgtGroup,
          count: 0,
        };
        gatewayOut[key].count += 1;
      } else if (srcGroup !== focusedGroup && tgtGroup === focusedGroup) {
        const key = `${srcGroup}\u0000${e.target}`;
        gatewayIn[key] = gatewayIn[key] || {
          sourceGroup: srcGroup,
          targetNode: e.target,
          count: 0,
        };
        gatewayIn[key].count += 1;
      }
    }
    if (edgeDetailMode === 'debug' || (edgeDetailMode === 'focus' && focusSelection)) {
      for (const rec of Object.values(gatewayOut)) {
        pushEdge(`${rec.sourceNode}.out`, _groupPort(rec.targetGroup, 'NORTH'), {
          kind: 'gateway-out',
          sourceNode: rec.sourceNode,
          sourceGroup: focusedGroup,
          targetGroup: rec.targetGroup,
          count: rec.count,
        });
      }
      for (const rec of Object.values(gatewayIn)) {
        pushEdge(_groupPort(rec.sourceGroup, 'SOUTH'), `${rec.targetNode}.in`, {
          kind: 'gateway-in',
          sourceGroup: rec.sourceGroup,
          targetNode: rec.targetNode,
          targetGroup: focusedGroup,
          count: rec.count,
        });
      }
    }
    return {
      id: 'root',
      children: groupNodes,
      edges,
    };
  }
  throw new Error(`unknown viewMode ${viewMode}`);
};

PX.countNodes = function countNodes(ir) {
  let n = 0;
  const walk = (x) => { if (!x) return; if (x.id && x !== ir) n++; (x.children || []).forEach(walk); };
  (ir.children || []).forEach(walk);
  return n;
};
