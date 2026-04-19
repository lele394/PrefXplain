// graph-utils.js — per-graph indexes built once and shared across UI + views.
//   PX.buildGraphIndex(graph) -> { byId, importers, importsOf, blastRadius, fileState, edgeState }
//
// The fileState / edgeState closures take a `selected` id (or null) and return
// the semantic bucket used for coloring: 'selected' | 'depends' | 'imports'
// | 'blast' | 'faded' | 'normal'.

window.PX = window.PX || {};

PX.buildGraphIndex = function buildGraphIndex(graph) {
  const byId = Object.fromEntries((graph.nodes || []).map(n => [n.id, n]));
  const importers = {}, importsOf = {};
  const byGroup = {};
  const groupOrder = [];
  const bridgeIn = {}, bridgeOut = {};
  for (const n of graph.nodes || []) { importers[n.id] = []; importsOf[n.id] = []; }
  for (const n of graph.nodes || []) {
    const g = n.group || 'Ungrouped';
    if (!byGroup[g]) {
      byGroup[g] = [];
      groupOrder.push(g);
    }
    byGroup[g].push(n.id);
    bridgeIn[n.id] = 0;
    bridgeOut[n.id] = 0;
  }
  const groupPairStats = {};
  const internalEdgeCount = {};
  const externalInCount = {};
  const externalOutCount = {};
  for (const g of groupOrder) {
    internalEdgeCount[g] = 0;
    externalInCount[g] = 0;
    externalOutCount[g] = 0;
  }
  for (const e of graph.edges || []) {
    if (importers[e.target]) importers[e.target].push(e.source);
    if (importsOf[e.source]) importsOf[e.source].push(e.target);
    const srcGroup = (byId[e.source] || {}).group || 'Ungrouped';
    const tgtGroup = (byId[e.target] || {}).group || 'Ungrouped';
    if (srcGroup === tgtGroup) {
      internalEdgeCount[srcGroup] = (internalEdgeCount[srcGroup] || 0) + 1;
      continue;
    }
    bridgeOut[e.source] = (bridgeOut[e.source] || 0) + 1;
    bridgeIn[e.target] = (bridgeIn[e.target] || 0) + 1;
    externalOutCount[srcGroup] = (externalOutCount[srcGroup] || 0) + 1;
    externalInCount[tgtGroup] = (externalInCount[tgtGroup] || 0) + 1;
    const key = `${srcGroup}\u0000${tgtGroup}`;
    const rec = groupPairStats[key] || {
      sourceGroup: srcGroup,
      targetGroup: tgtGroup,
      count: 0,
      sourceFiles: {},
      targetFiles: {},
      filePairs: {},
    };
    rec.count += 1;
    rec.sourceFiles[e.source] = (rec.sourceFiles[e.source] || 0) + 1;
    rec.targetFiles[e.target] = (rec.targetFiles[e.target] || 0) + 1;
    const pairKey = `${e.source}\u0000${e.target}`;
    rec.filePairs[pairKey] = (rec.filePairs[pairKey] || 0) + 1;
    groupPairStats[key] = rec;
  }
  const roleWeight = {
    entry_point: 6,
    api_route: 5,
    data_model: 4,
    utility: 3,
    config: 2,
    test: 1,
    other: 0,
  };
  const topCountItems = (counts, limit = 3) => Object.entries(counts || {})
    .sort((a, b) => {
      const diff = b[1] - a[1];
      if (diff !== 0) return diff;
      return String((byId[a[0]] || {}).label || a[0]).localeCompare(String((byId[b[0]] || {}).label || b[0]));
    })
    .slice(0, limit)
    .map(([id, count]) => ({
      id,
      count,
      label: (byId[id] || {}).short || (byId[id] || {}).label || id,
    }));
  const topPairItems = (counts, limit = 3) => Object.entries(counts || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([pairKey, count]) => {
      const [source, target] = pairKey.split('\u0000');
      return {
        source,
        target,
        count,
        sourceLabel: (byId[source] || {}).short || (byId[source] || {}).label || source,
        targetLabel: (byId[target] || {}).short || (byId[target] || {}).label || target,
      };
    });
  const pairList = Object.values(groupPairStats).map(rec => ({
    ...rec,
    topSourceFiles: topCountItems(rec.sourceFiles),
    topTargetFiles: topCountItems(rec.targetFiles),
    topPairs: topPairItems(rec.filePairs),
  }));
  const pairByGroup = {};
  for (const g of groupOrder) pairByGroup[g] = { incoming: [], outgoing: [] };
  for (const rec of pairList) {
    if (!pairByGroup[rec.sourceGroup]) pairByGroup[rec.sourceGroup] = { incoming: [], outgoing: [] };
    if (!pairByGroup[rec.targetGroup]) pairByGroup[rec.targetGroup] = { incoming: [], outgoing: [] };
    pairByGroup[rec.sourceGroup].outgoing.push(rec);
    pairByGroup[rec.targetGroup].incoming.push(rec);
  }
  const groupStats = {};
  for (const g of groupOrder) {
    const fileIds = (byGroup[g] || []).slice();
    const orderedFileIds = fileIds.sort((a, b) => {
      const aBridge = (bridgeIn[a] || 0) + (bridgeOut[a] || 0);
      const bBridge = (bridgeIn[b] || 0) + (bridgeOut[b] || 0);
      if (bBridge !== aBridge) return bBridge - aBridge;
      const aFlow = (importers[a] || []).length + (importsOf[a] || []).length;
      const bFlow = (importers[b] || []).length + (importsOf[b] || []).length;
      if (bFlow !== aFlow) return bFlow - aFlow;
      const aRole = roleWeight[(byId[a] || {}).role] || 0;
      const bRole = roleWeight[(byId[b] || {}).role] || 0;
      if (bRole !== aRole) return bRole - aRole;
      return String((byId[a] || {}).label || a).localeCompare(String((byId[b] || {}).label || b));
    });
    const outgoingPairs = (pairByGroup[g] || {}).outgoing || [];
    const incomingPairs = (pairByGroup[g] || {}).incoming || [];
    outgoingPairs.sort((a, b) => b.count - a.count);
    incomingPairs.sort((a, b) => b.count - a.count);
    groupStats[g] = {
      group: g,
      fileCount: fileIds.length,
      internalEdges: internalEdgeCount[g] || 0,
      externalIn: externalInCount[g] || 0,
      externalOut: externalOutCount[g] || 0,
      gatewayInFiles: topCountItems(Object.fromEntries(fileIds.map(id => [id, bridgeIn[id] || 0]).filter(([, count]) => count > 0)), 4),
      gatewayOutFiles: topCountItems(Object.fromEntries(fileIds.map(id => [id, bridgeOut[id] || 0]).filter(([, count]) => count > 0)), 4),
      bridgeFiles: orderedFileIds
        .filter(id => (bridgeIn[id] || 0) + (bridgeOut[id] || 0) > 0)
        .slice(0, 4)
        .map(id => ({
          id,
          count: (bridgeIn[id] || 0) + (bridgeOut[id] || 0),
          incoming: bridgeIn[id] || 0,
          outgoing: bridgeOut[id] || 0,
          label: (byId[id] || {}).short || (byId[id] || {}).label || id,
        })),
      strongestOut: outgoingPairs[0] ? {
        group: outgoingPairs[0].targetGroup,
        count: outgoingPairs[0].count,
        topFiles: outgoingPairs[0].topSourceFiles,
      } : null,
      strongestIn: incomingPairs[0] ? {
        group: incomingPairs[0].sourceGroup,
        count: incomingPairs[0].count,
        topFiles: incomingPairs[0].topTargetFiles,
      } : null,
      orderedFileIds,
    };
  }
  const blastRadius = (id) => {
    const out = new Set();
    const stack = [id];
    while (stack.length) {
      const cur = stack.pop();
      for (const dep of importers[cur] || []) {
        if (!out.has(dep)) { out.add(dep); stack.push(dep); }
      }
    }
    return out;
  };
  const fileState = (selected, id, filter) => {
    if (!selected) {
      if (!filter) return 'normal';
      const n = byId[id];
      if (!n) return 'normal';
      const q = filter.toLowerCase();
      return (n.label || '').toLowerCase().includes(q) || (n.description || '').toLowerCase().includes(q) ? 'match' : 'faded';
    }
    if (id === selected) return 'selected';
    if ((importsOf[selected] || []).includes(id)) return 'depends';
    if ((importers[selected] || []).includes(id)) return 'imports';
    if (blastRadius(selected).has(id)) return 'blast';
    return 'faded';
  };
  const edgeState = (selected, e) => {
    if (!selected) return 'normal';
    if (e.source === selected) return 'depends';
    if (e.target === selected) return 'imports';
    return 'faded';
  };
  // ─── Intra-group band classification ────────────────────────────────
  // Bands derive from dependency position INSIDE a group. Roles are a
  // tiebreaker, not the primary axis — Codex pushback made this clear.
  //
  //   entry  = files with inbound bridges from other groups OR role=entry_point|api_route
  //   test   = role=test (kept in its own band; tests are the consumers of everything)
  //   leaf   = no intra-group outgoing edges (nothing inside the group depends on them)
  //   core   = everything else (the coordinating majority)
  //
  // Computed once at index time and keyed by groupId for O(1) lookup.
  const groupBands = {};
  for (const g of groupOrder) {
    const intraOut = {}; // fileId → count of intra-group outgoing edges
    const intraIn  = {}; // fileId → count of intra-group incoming edges
    for (const id of byGroup[g] || []) { intraOut[id] = 0; intraIn[id] = 0; }
    for (const e of graph.edges || []) {
      const sg = (byId[e.source] || {}).group || 'Ungrouped';
      const tg = (byId[e.target] || {}).group || 'Ungrouped';
      if (sg !== g || tg !== g) continue;
      if (intraOut[e.source] != null) intraOut[e.source] += 1;
      if (intraIn[e.target]  != null) intraIn[e.target]  += 1;
    }
    const bands = { entry: [], core: [], leaf: [], test: [] };
    for (const id of byGroup[g] || []) {
      const n = byId[id] || {};
      const role = n.role || 'other';
      const bIn  = bridgeIn[id]  || 0;
      if (role === 'test') { bands.test.push(id); continue; }
      if (role === 'entry_point' || role === 'api_route' || bIn >= 2) {
        bands.entry.push(id); continue;
      }
      if ((intraOut[id] || 0) === 0 && (intraIn[id] || 0) > 0) {
        bands.leaf.push(id); continue;
      }
      bands.core.push(id);
    }
    // Deterministic intra-band ordering: fan-in desc → fan-out desc → role → name.
    const cmp = (a, b) => {
      const aIn = (importers[a] || []).length;
      const bIn = (importers[b] || []).length;
      if (bIn !== aIn) return bIn - aIn;
      const aOut = (importsOf[a] || []).length;
      const bOut = (importsOf[b] || []).length;
      if (bOut !== aOut) return bOut - aOut;
      const aRole = roleWeight[(byId[a] || {}).role] || 0;
      const bRole = roleWeight[(byId[b] || {}).role] || 0;
      if (bRole !== aRole) return bRole - aRole;
      return String((byId[a] || {}).label || a).localeCompare(String((byId[b] || {}).label || b));
    };
    bands.entry.sort(cmp);
    bands.core.sort(cmp);
    bands.leaf.sort(cmp);
    bands.test.sort(cmp);
    groupBands[g] = bands;
  }

  // ─── Intra-group cycles (Tarjan's SCC on the group's induced subgraph) ─
  // Only non-trivial components (size ≥ 2 OR a self-loop) count. Used to
  // surface architectural smells in the "Stress points" strip.
  const groupCycles = {};
  const MAX_EDGES = 500;
  for (const g of groupOrder) {
    const fileIds = byGroup[g] || [];
    if (fileIds.length < 2) { groupCycles[g] = []; continue; }
    const intraEdges = [];
    for (const e of graph.edges || []) {
      const sg = (byId[e.source] || {}).group || 'Ungrouped';
      const tg = (byId[e.target] || {}).group || 'Ungrouped';
      if (sg === g && tg === g) intraEdges.push([e.source, e.target]);
      if (intraEdges.length > MAX_EDGES) break;
    }
    if (intraEdges.length === 0) { groupCycles[g] = []; continue; }
    const adj = {};
    for (const id of fileIds) adj[id] = [];
    for (const [s, t] of intraEdges) { if (adj[s]) adj[s].push(t); }
    // Iterative Tarjan.
    let idxCounter = 0;
    const idxMap = {}, lowMap = {}, onStack = {};
    const stack = [];
    const sccs = [];
    const run = (start) => {
      const frames = [{ v: start, it: 0 }];
      idxMap[start] = idxCounter;
      lowMap[start] = idxCounter;
      idxCounter += 1;
      stack.push(start); onStack[start] = true;
      while (frames.length) {
        const f = frames[frames.length - 1];
        const succ = adj[f.v] || [];
        if (f.it < succ.length) {
          const w = succ[f.it++];
          if (idxMap[w] === undefined) {
            idxMap[w] = idxCounter;
            lowMap[w] = idxCounter;
            idxCounter += 1;
            stack.push(w); onStack[w] = true;
            frames.push({ v: w, it: 0 });
          } else if (onStack[w]) {
            lowMap[f.v] = Math.min(lowMap[f.v], idxMap[w]);
          }
        } else {
          if (lowMap[f.v] === idxMap[f.v]) {
            const comp = [];
            let w;
            do { w = stack.pop(); onStack[w] = false; comp.push(w); } while (w !== f.v);
            if (comp.length > 1) sccs.push(comp);
            else if ((adj[comp[0]] || []).includes(comp[0])) sccs.push(comp); // self-loop
          }
          frames.pop();
          if (frames.length) {
            const parent = frames[frames.length - 1];
            lowMap[parent.v] = Math.min(lowMap[parent.v], lowMap[f.v]);
          }
        }
      }
    };
    for (const id of fileIds) {
      if (idxMap[id] === undefined) run(id);
    }
    groupCycles[g] = sccs;
  }

  return {
    byId,
    importers,
    importsOf,
    blastRadius,
    fileState,
    edgeState,
    groupOrder,
    groupFiles: byGroup,
    groupStats,
    groupPairStats: pairList,
    groupPairStatsByKey: Object.fromEntries(pairList.map(rec => [`${rec.sourceGroup}\u0000${rec.targetGroup}`, rec])),
    fileBridgeIn: bridgeIn,
    fileBridgeOut: bridgeOut,
    groupBands,
    groupCycles,
  };
};

PX.splitPortId = function splitPortId(portId) {
  if (!portId) return { nodeId: null, side: null };
  const dot = portId.lastIndexOf('.');
  if (dot <= 0) return { nodeId: portId, side: null };
  return { nodeId: portId.slice(0, dot), side: portId.slice(dot + 1) };
};
