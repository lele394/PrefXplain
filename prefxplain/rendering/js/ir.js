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
  // File cards need room for: row 1 (glyph + short_title + bridge badge +
  // size dots + size), row 2 (filename subtitle), row 3 (up to 3 highlights),
  // row 4 (IN/OUT bars). 304×132 keeps the 3-bullet grid from colliding with
  // the IN/OUT bars while giving the title room to breathe.
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
// LABEL_PADDING covers: inner text padding + enough slack for the arrow's
// stroke shoulder. Aggregate edges use up to 5px thick strokes, so a label
// sitting on-path has a 2.5px perpendicular shoulder poking out of the rect
// at the entry/exit bend. ≥10px horizontal padding per side (LABEL_PADDING/2)
// hides the shoulder under the rect's opaque bg fill.
const LABEL_CH_BOLD = 8.2;
const LABEL_CH_REG = 7.6;
const LABEL_HEIGHT = 56;
const LABEL_PADDING = 36;

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
    return {
      id: `ge${i}`,
      sources: [`${source}.out-ge${i}`],
      targets: [`${target}.in-ge${i}`],
      sourceGroupName: source,
      targetGroupName: target,
      count,
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

// ─── Group Story: composed view over the analyzer's index ─────────────
// Emits a self-describing object that the nested view renders section by
// section. Every field is derived from data the analyzer already computes
// (roles, bridges, cycles, pair stats) — no extra passes at render time.
//
// Shape:
//   {
//     meta:      { id, name, description, color },
//     summary:   { fileCount, externalIn, externalOut, internalEdges,
//                  topRoutes: [{dir:'out'|'in', group, count}, ...] },
//     entries:   [{ id, label, short, role, fanIn, fanOut }, ... ≤5],
//     bands:     [{ key, name, files:[{ id, label, short, role, fanIn,
//                  fanOut, isHub, inCycle, bridgeIn, bridgeOut }] }],
//     edges:     [{ source, target, count, labelled, verb }],
//     stress:    [{ kind, text, files:[id, ...] }],
//   }
PX.buildGroupStory = function buildGroupStory(graph, groupId, index) {
  const byId = Object.fromEntries((graph.nodes || []).map(n => [n.id, n]));
  const metaGroups = graph.metaGroups || {};
  const meta = metaGroups[groupId] || {};
  const stats = (index.groupStats || {})[groupId] || {};
  const bandsRaw = (index.groupBands || {})[groupId] || { entry: [], core: [], leaf: [], test: [], standalone: [] };
  const cycles = (index.groupCycles || {})[groupId] || [];

  // Files in a set-of-file-ids that are part of a cycle.
  const cycleMembership = new Set();
  for (const scc of cycles) for (const id of scc) cycleMembership.add(id);

  // Intra-group edges + weights.
  const edgePairCount = {};
  const intraEdges = [];
  for (const e of graph.edges || []) {
    const sg = (byId[e.source] || {}).group || 'Ungrouped';
    const tg = (byId[e.target] || {}).group || 'Ungrouped';
    if (sg !== groupId || tg !== groupId) continue;
    const key = `${e.source}\u0000${e.target}`;
    edgePairCount[key] = (edgePairCount[key] || 0) + 1;
    if (edgePairCount[key] === 1) intraEdges.push([e.source, e.target]);
  }
  // Label only the heaviest intra-group edges: top 5 by count OR any
  // edge with count ≥ 2. Rest render as plain arrows. This is Codex's
  // "threshold/collapse" guidance — labels stay legible on dense groups.
  const ranked = intraEdges
    .map(([s, t]) => ({ source: s, target: t, count: edgePairCount[`${s}\u0000${t}`] }))
    // Secondary + tertiary keys keep lane-offset assignment deterministic
    // across runs (edge index drives laneX/laneY in the nested view).
    .sort((a, b) => (b.count - a.count) || a.source.localeCompare(b.source) || a.target.localeCompare(b.target));
  const labelledIds = new Set();
  for (const e of ranked) {
    if (labelledIds.size >= 5 && e.count < 2) break;
    labelledIds.add(`${e.source}\u0000${e.target}`);
  }

  const inDeg = {}, outDeg = {};
  for (const n of graph.nodes || []) { inDeg[n.id] = 0; outDeg[n.id] = 0; }
  for (const e of graph.edges || []) {
    if (inDeg[e.target]  != null) inDeg[e.target]  += 1;
    if (outDeg[e.source] != null) outDeg[e.source] += 1;
  }
  const SPOF_MIN = 8;
  const bridgeIn = index.fileBridgeIn || {};
  const bridgeOut = index.fileBridgeOut || {};

  const fileView = (id) => {
    const n = byId[id] || {};
    return {
      id,
      label: n.label || id,
      short: n.short || n.label || id,
      description: n.description || '',
      highlights: n.highlights || [],
      role: n.role || 'other',
      fanIn: inDeg[id] || 0,
      fanOut: outDeg[id] || 0,
      size: n.size || 0,
      isHub: (inDeg[id] || 0) >= SPOF_MIN,
      inCycle: cycleMembership.has(id),
      bridgeIn: bridgeIn[id] || 0,
      bridgeOut: bridgeOut[id] || 0,
    };
  };

  const bandDefs = [
    { key: 'entry',      name: 'Entry / Gateway' },
    { key: 'core',       name: 'Core'            },
    { key: 'leaf',       name: 'Leaf / Utility'  },
    { key: 'test',       name: 'Tests'           },
    { key: 'standalone', name: 'Standalone'      },
  ];
  const bands = bandDefs
    .map(def => ({
      key: def.key,
      name: def.name,
      files: (bandsRaw[def.key] || []).map(fileView),
    }))
    .filter(b => b.files.length > 0);

  // Standalone taxonomy: per-category semantic split of the orphan files.
  // The synthesis step (see prefxplain.md §4g) writes one taxonomy per group
  // to metadata.group_summaries[<groupId>].standalone_taxonomy. We resolve
  // member_file_ids to fileView objects, preserve category order from the
  // LLM (importance-sorted), and drop any file ID that isn't actually in this
  // group's standalone band (defensive — handles stale json after refactors).
  //
  // Files in the standalone band that the LLM didn't categorize are bucketed
  // into a synthetic "Uncategorized" tail-category so nothing silently
  // disappears from the view. That category renders with a neutral
  // description so it's clear it's a fallback, not a curated bucket.
  const standaloneBand = bands.find(b => b.key === 'standalone');
  if (standaloneBand && Array.isArray(meta.standalone_taxonomy) && meta.standalone_taxonomy.length > 0) {
    const standaloneById = new Map(standaloneBand.files.map(f => [f.id, f]));
    const claimed = new Set();
    const taxonomy = [];
    for (const raw of meta.standalone_taxonomy) {
      if (!raw || typeof raw !== 'object') continue;
      const category = typeof raw.category === 'string' ? raw.category.trim() : '';
      if (!category) continue;
      const memberIds = Array.isArray(raw.member_file_ids) ? raw.member_file_ids : [];
      const catFiles = [];
      for (const fid of memberIds) {
        if (claimed.has(fid)) continue;
        const fv = standaloneById.get(fid);
        if (!fv) continue;
        claimed.add(fid);
        catFiles.push(fv);
      }
      if (catFiles.length === 0) continue;
      const description = typeof raw.description === 'string' ? raw.description.trim() : '';
      taxonomy.push({ category, description, files: catFiles });
    }
    const uncategorized = standaloneBand.files.filter(f => !claimed.has(f.id));
    if (uncategorized.length > 0) {
      taxonomy.push({
        category: 'Uncategorized',
        description: 'No category assigned by the synthesis step — inspect individually.',
        files: uncategorized,
      });
    }
    if (taxonomy.length > 0) {
      standaloneBand.taxonomy = taxonomy;
    }
  }

  // Primary entry paths — top 5 entry-band files (already ordered by fan-in).
  const entries = (bandsRaw.entry || []).slice(0, 5).map(fileView);

  // Top external routes, condensed.
  const topRoutes = [];
  if (stats.strongestOut) topRoutes.push({ dir: 'out', group: stats.strongestOut.group, count: stats.strongestOut.count });
  if (stats.strongestIn)  topRoutes.push({ dir: 'in',  group: stats.strongestIn.group,  count: stats.strongestIn.count  });
  // Add second-strongest out + in for context (if present and distinct).
  const pairs = (index.groupPairStats || []);
  const outs = pairs.filter(r => r.sourceGroup === groupId).sort((a, b) => b.count - a.count);
  const ins  = pairs.filter(r => r.targetGroup === groupId).sort((a, b) => b.count - a.count);
  if (outs[1]) topRoutes.push({ dir: 'out', group: outs[1].targetGroup, count: outs[1].count });
  if (ins[1])  topRoutes.push({ dir: 'in',  group: ins[1].sourceGroup,  count: ins[1].count  });

  // Stress points — only surface non-trivial architectural smells.
  const stress = [];
  const hubs = [];
  for (const band of bands) for (const f of band.files) if (f.isHub) hubs.push(f);
  if (hubs.length > 0) {
    stress.push({
      kind: 'hub',
      text: hubs.length === 1
        ? `${hubs[0].label} is a hub (${hubs[0].fanIn} importers) — change with care`
        : `${hubs.length} hub files: ${hubs.slice(0, 3).map(f => f.label).join(', ')}${hubs.length > 3 ? '…' : ''}`,
      files: hubs.map(f => f.id),
    });
  }
  if (cycles.length > 0) {
    const biggest = cycles.slice().sort((a, b) => b.length - a.length)[0];
    stress.push({
      kind: 'cycle',
      text: cycles.length === 1
        ? `Import cycle detected (${biggest.length} files): ${biggest.slice(0, 3).map(id => (byId[id] || {}).label || id).join(' ↔ ')}${biggest.length > 3 ? '…' : ''}`
        : `${cycles.length} import cycles inside this group — architectural smell`,
      files: biggest,
    });
  }
  // Dominant single-file bridges to other groups: "describer.py is the sole bridge to Graph Data Model".
  const dominantBridges = [];
  for (const pair of outs) {
    const topFiles = pair.topSourceFiles || [];
    if (topFiles.length === 1 && topFiles[0].count >= 2 && pair.count === topFiles[0].count) {
      dominantBridges.push({ file: topFiles[0], direction: 'out', group: pair.targetGroup });
    }
  }
  for (const pair of ins) {
    const topFiles = pair.topTargetFiles || [];
    if (topFiles.length === 1 && topFiles[0].count >= 2 && pair.count === topFiles[0].count) {
      dominantBridges.push({ file: topFiles[0], direction: 'in', group: pair.sourceGroup });
    }
  }
  for (const b of dominantBridges.slice(0, 2)) {
    stress.push({
      kind: 'bridge',
      text: b.direction === 'out'
        ? `${b.file.label} is the sole bridge to ${b.group}`
        : `${b.file.label} receives all incoming from ${b.group}`,
      files: [b.file.id],
    });
  }
  // Untested coverage — only surface for non-test groups with significant file counts.
  if (groupId !== 'Tests' && (stats.fileCount || 0) >= 5) {
    const testGroups = ['Tests'];
    const testEdges = new Set();
    for (const e of graph.edges || []) {
      const sg = (byId[e.source] || {}).group || 'Ungrouped';
      if (!testGroups.includes(sg)) continue;
      testEdges.add(e.target);
    }
    const untested = [];
    for (const band of bands) {
      if (band.key === 'test') continue;
      for (const f of band.files) if (!testEdges.has(f.id)) untested.push(f);
    }
    // Only flag if at least 3 files are untested — single-file groups don't need nagging.
    if (untested.length >= 3) {
      stress.push({
        kind: 'untested',
        text: `${untested.length} files have no direct test coverage`,
        files: untested.map(f => f.id),
      });
    }
  }

  // ─── Test-coverage clustering (groups where tests are the dominant role) ──
  // For a test-majority group, grouping files by the file they test is
  // more actionable than "all tests in one pile". Derivation:
  //   1. For each test file, read its outbound intra-repo imports.
  //   2. Prefer the one whose filename matches `<test_X.ext → X.ext>`.
  //   3. Fallback to the most frequent external import target.
  //   4. No-target tests go to a "General" bucket.
  const testBand = bands.find(b => b.key === 'test');
  const totalFiles = bands.reduce((n, b) => n + b.files.length, 0);
  const testCount = testBand ? testBand.files.length : 0;
  const isTestMajority = totalFiles > 0 && testBand && testCount / totalFiles >= 0.5;
  if (isTestMajority) {
    const importsOf = index.importsOf || {};
    const stripExt = (s) => String(s).replace(/\.(py|pyi|ts|tsx|js|jsx|mjs|cjs|rb|go|java|kt|rs|swift)$/i, '');
    const baseOf = (label) => stripExt(label).replace(/^test[_-]/i, '').replace(/[_-]test$/i, '');
    const clustersByTarget = new Map(); // targetId → { target, tests: [] }
    const generalTests = [];
    for (const f of testBand.files) {
      const outs = (importsOf[f.id] || [])
        .map(id => byId[id])
        .filter(n => n && n.id !== f.id);
      if (outs.length === 0) { generalTests.push(f); continue; }
      const wanted = baseOf(f.label || f.id);
      let target = outs.find(n => baseOf(n.label || n.id) === wanted);
      if (!target) {
        // Fallback: pick the externally-grouped import with highest pair count,
        // tiebreak by filename similarity.
        const extOuts = outs.filter(n => (n.group || 'Ungrouped') !== groupId);
        target = (extOuts.length ? extOuts : outs)[0];
      }
      if (!target) { generalTests.push(f); continue; }
      if (!clustersByTarget.has(target.id)) {
        const tg = target.group || 'Ungrouped';
        const tgMeta = metaGroups[tg] || {};
        clustersByTarget.set(target.id, {
          targetId: target.id,
          targetLabel: target.label || target.id,
          targetGroup: tg,
          targetColor: PX.groupColor(tg, tgMeta),
          tests: [],
        });
      }
      clustersByTarget.get(target.id).tests.push(f);
    }
    // Sort clusters: by test-count desc, tiebreak by target filename.
    const sorted = Array.from(clustersByTarget.values()).sort((a, b) => {
      if (b.tests.length !== a.tests.length) return b.tests.length - a.tests.length;
      return a.targetLabel.localeCompare(b.targetLabel);
    });
    if (generalTests.length > 0) {
      sorted.push({
        targetId: null,
        targetLabel: 'General',
        targetGroup: null,
        targetColor: PX.T.inkMuted,
        tests: generalTests,
      });
    }
    testBand.clusters = sorted;
  }

  // ─── External anchors: per-file × per-external-group aggregate ──────
  // Every edge crossing this group's boundary gets a drawable anchor, so
  // the viewer sees "which files in this group talk to which outside
  // group" at a glance. This is what makes boundary groups (CLI, Tests)
  // legible — their value lives in the outbound arrows, not in internal
  // cohesion.
  const outPairCount = {};   // `${fileId}\u0000${externalGroup}` → count
  const inPairCount = {};    // `${externalGroup}\u0000${fileId}` → count
  const outGroupTotal = {};  // externalGroup → total count
  const inGroupTotal = {};
  for (const e of graph.edges || []) {
    const sg = (byId[e.source] || {}).group || 'Ungrouped';
    const tg = (byId[e.target] || {}).group || 'Ungrouped';
    if (sg === groupId && tg !== groupId) {
      const key = `${e.source}\u0000${tg}`;
      outPairCount[key] = (outPairCount[key] || 0) + 1;
      outGroupTotal[tg] = (outGroupTotal[tg] || 0) + 1;
    } else if (tg === groupId && sg !== groupId) {
      const key = `${sg}\u0000${e.target}`;
      inPairCount[key] = (inPairCount[key] || 0) + 1;
      inGroupTotal[sg] = (inGroupTotal[sg] || 0) + 1;
    }
  }
  const mkAnchor = (gid, count, dir) => ({
    groupId: gid,
    label: gid,
    color: PX.groupColor(gid, metaGroups[gid] || {}),
    count,
    direction: dir,
  });
  const externalOut = Object.entries(outGroupTotal)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([gid, count]) => mkAnchor(gid, count, 'out'));
  const externalIn = Object.entries(inGroupTotal)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([gid, count]) => mkAnchor(gid, count, 'in'));
  const outEdges = Object.entries(outPairCount).map(([key, count]) => {
    const [fileId, gid] = key.split('\u0000');
    return { fileId, groupId: gid, count, direction: 'out' };
  });
  const inEdges = Object.entries(inPairCount).map(([key, count]) => {
    const [gid, fileId] = key.split('\u0000');
    return { fileId, groupId: gid, count, direction: 'in' };
  });

  return {
    meta: {
      id: groupId,
      name: groupId,
      description: meta.desc || meta.description || '',
      color: PX.groupColor(groupId, meta),
      // Pass-through of LLM-authored semantic scaffolding so the detail
      // summary header can render role/flow/extends_at without reaching back
      // into graph.metaGroups.
      semantic_role: meta.semantic_role || '',
      flow: meta.flow || '',
      extends_at: meta.extends_at || '',
      pattern: meta.pattern || '',
      highlights: Array.isArray(meta.highlights) ? meta.highlights : [],
    },
    summary: {
      fileCount: stats.fileCount || 0,
      externalIn: stats.externalIn || 0,
      externalOut: stats.externalOut || 0,
      internalEdges: stats.internalEdges || 0,
      topRoutes,
    },
    entries,
    bands,
    edges: ranked.map(e => ({
      source: e.source,
      target: e.target,
      count: e.count,
      labelled: labelledIds.has(`${e.source}\u0000${e.target}`),
    })),
    stress,
    testMajority: !!isTestMajority,
    externalIn,
    externalOut,
    externalInEdges: inEdges,
    externalOutEdges: outEdges,
  };
};

// ─── Group Story Layout: band grid + ELK for edge routing only ────────
// Hand-positions cards in bands (deterministic, Codex's guidance), then
// feeds ELK only the routing job via algorithm=fixed. Returns both the
// positions (for card rendering) and the ELK IR (for edge polylines).
PX.buildGroupStoryLayoutIr = function buildGroupStoryLayoutIr(story, {
  showBullets = true,
  canvasWidth = 1280,
  topPad = 28,
  leftPad = 28,
  bandGapY = 52,
  bandGapX = 44,
  cardGapY = 18,
  standaloneCollapsed = false,
} = {}) {
  const fileSize = showBullets ? PX.NODE_SIZES.fileBullets : PX.NODE_SIZES.fileNoBullets;
  const cw = fileSize.w, ch = fileSize.h;
  // Standalone cards are always compact (no bullets) — they carry no story,
  // so the shorter height lets a dense group's orphan grid fit in a few rows
  // instead of a giant column.
  const CH_STANDALONE = PX.NODE_SIZES.fileNoBullets.h;
  // Entry, Core, Leaf → 3 parallel columns (side by side). Tests → own row below.
  // Standalone → compact full-width grid AFTER tests (pure orphans, no story).
  const BAND_ORDER = ['entry', 'core', 'leaf'];
  const columnBands = story.bands.filter(b => BAND_ORDER.includes(b.key));
  const testBand = story.bands.find(b => b.key === 'test') || null;
  const standaloneBand = story.bands.find(b => b.key === 'standalone') || null;
  const standaloneIds = new Set(
    standaloneBand ? standaloneBand.files.map(f => f.id) : []
  );

  // Figure out how many columns fit side-by-side given canvas width.
  // Target: 3 columns when canvas ≥ 3*cw + 2*bandGapX + 2*leftPad.
  // Narrower → stack vertically (each band becomes its own row).
  const targetCols = Math.max(1, Math.min(columnBands.length, Math.floor((canvasWidth - 2 * leftPad + bandGapX) / (cw + bandGapX))));
  const stacked = targetCols < columnBands.length;

  const positions = {}; // fileId → { x, y }
  let cursorY = topPad;
  let totalW = 0;
  let totalH = topPad;
  const bandRects = [];

  if (stacked) {
    // Narrow layout: each band is a row, files wrap as 2+ per row.
    for (const band of columnBands) {
      const bandX = leftPad;
      const perRow = Math.max(1, Math.floor((canvasWidth - 2 * leftPad + bandGapX) / (cw + bandGapX)));
      const rows = Math.ceil(band.files.length / perRow);
      const bandH = rows * ch + (rows - 1) * cardGapY;
      for (let i = 0; i < band.files.length; i++) {
        const col = i % perRow;
        const row = Math.floor(i / perRow);
        positions[band.files[i].id] = {
          x: bandX + col * (cw + bandGapX),
          y: cursorY + row * (ch + cardGapY),
        };
      }
      bandRects.push({
        key: band.key,
        name: band.name,
        x: bandX, y: cursorY,
        w: Math.max(cw, perRow * cw + (perRow - 1) * bandGapX),
        h: bandH,
        count: band.files.length,
      });
      cursorY += bandH + bandGapY;
    }
    totalW = canvasWidth - 2 * leftPad;
  } else {
    // Wide layout: columnBands side by side. Each column stacks its files
    // vertically. Row height for this section = tallest column's height.
    let maxColH = 0;
    const colXs = [];
    for (let i = 0; i < columnBands.length; i++) {
      colXs.push(leftPad + i * (cw + bandGapX));
    }
    // If fewer than targetCols bands, still position them left-aligned.
    for (let i = 0; i < columnBands.length; i++) {
      const band = columnBands[i];
      const bandX = colXs[i];
      for (let j = 0; j < band.files.length; j++) {
        positions[band.files[j].id] = {
          x: bandX,
          y: cursorY + j * (ch + cardGapY),
        };
      }
      const bandH = band.files.length * ch + Math.max(0, band.files.length - 1) * cardGapY;
      bandRects.push({
        key: band.key,
        name: band.name,
        x: bandX, y: cursorY,
        w: cw,
        h: bandH || ch,
        count: band.files.length,
      });
      if (bandH > maxColH) maxColH = bandH;
    }
    if (columnBands.length > 0) {
      cursorY += Math.max(maxColH, ch) + bandGapY;
      totalW = colXs[colXs.length - 1] + cw - leftPad;
    }
  }

  // Tests band: always spans the FULL canvas width (bug-fix for single-band
  // groups that previously inherited totalW=0 and degenerated to one column).
  if (testBand && testBand.files.length > 0) {
    const usableW = canvasWidth - 2 * leftPad;
    const perRow = Math.max(1, Math.floor((usableW + bandGapX) / (cw + bandGapX)));

    // Clustered layout: one sub-column per test target ("tests for analyzer.py").
    // Falls through to the flat layout if no clusters were computed.
    const SUBHEADER_H = 26;
    if (Array.isArray(testBand.clusters) && testBand.clusters.length > 0) {
      const clusters = testBand.clusters;
      const totalRows = Math.ceil(clusters.length / perRow);
      let bandTop = cursorY;
      for (let r = 0; r < totalRows; r++) {
        let rowMaxH = 0;
        for (let c = 0; c < perRow; c++) {
          const idx = r * perRow + c;
          if (idx >= clusters.length) break;
          const cluster = clusters[idx];
          const h = SUBHEADER_H + cluster.tests.length * ch
            + Math.max(0, cluster.tests.length - 1) * cardGapY;
          if (h > rowMaxH) rowMaxH = h;
        }
        for (let c = 0; c < perRow; c++) {
          const idx = r * perRow + c;
          if (idx >= clusters.length) break;
          const cluster = clusters[idx];
          const clusterX = leftPad + c * (cw + bandGapX);
          const cardsStartY = cursorY + SUBHEADER_H;
          for (let j = 0; j < cluster.tests.length; j++) {
            positions[cluster.tests[j].id] = {
              x: clusterX,
              y: cardsStartY + j * (ch + cardGapY),
            };
          }
          bandRects.push({
            key: 'test-cluster',
            kind: 'cluster',
            name: cluster.targetLabel,
            targetId: cluster.targetId,
            targetGroup: cluster.targetGroup,
            targetColor: cluster.targetColor,
            x: clusterX,
            y: cursorY,
            w: cw,
            h: SUBHEADER_H + cluster.tests.length * ch
              + Math.max(0, cluster.tests.length - 1) * cardGapY,
            count: cluster.tests.length,
          });
        }
        cursorY += rowMaxH + (r < totalRows - 1 ? bandGapY : 0);
      }
      bandRects.push({
        key: 'test',
        kind: 'band',
        name: testBand.name,
        x: leftPad, y: bandTop,
        w: usableW,
        h: cursorY - bandTop,
        count: testBand.files.length,
      });
      cursorY += bandGapY;
    } else {
      // Flat grid across the full canvas — fixes the pile-of-cards bug.
      const rows = Math.ceil(testBand.files.length / perRow);
      const bandH = rows * ch + (rows - 1) * cardGapY;
      for (let i = 0; i < testBand.files.length; i++) {
        const col = i % perRow;
        const row = Math.floor(i / perRow);
        positions[testBand.files[i].id] = {
          x: leftPad + col * (cw + bandGapX),
          y: cursorY + row * (ch + cardGapY),
        };
      }
      bandRects.push({
        key: 'test',
        kind: 'band',
        name: testBand.name,
        x: leftPad, y: cursorY,
        w: usableW,
        h: bandH,
        count: testBand.files.length,
      });
      cursorY += bandH + bandGapY;
    }
  }

  // Standalone band: pure orphans (no edges anywhere). Rendered as a compact
  // grid capped to the CORE content width so they don't push the canvas wider.
  //
  // Taxonomy split: when buildGroupStory has attached a taxonomy (LLM-defined
  // semantic categories — see prefxplain.md §4g), we break the single grid
  // into N stacked sub-bands, each with its own 2-line chrome (category name
  // + 1-line description). Sub-bands share the column grid and stack with a
  // tighter gap so they read as one grouped section. The outer 'standalone'
  // rect is always emitted for hit-testing; the nested renderer controls
  // the label via the data-toggle-standalone pattern.
  //
  // When standaloneCollapsed=true (user clicked the ▶ toggle): emit only the
  // outer band rect (h=0, so just the dashed-rule label chrome) and skip all
  // file positions. The canvas height stays accurate — no blank space.
  if (standaloneBand && standaloneBand.files.length > 0) {
    const usableW = canvasWidth - 2 * leftPad;
    if (standaloneCollapsed) {
      bandRects.push({
        key: 'standalone',
        kind: 'band',
        name: standaloneBand.name,
        x: leftPad, y: cursorY,
        w: usableW,
        h: 0,
        count: standaloneBand.files.length,
      });
      cursorY += bandGapY / 2;
    } else {
    const perRow = Math.max(1, Math.floor((usableW + bandGapX) / (cw + bandGapX)));
    const hasTaxonomy = Array.isArray(standaloneBand.taxonomy) && standaloneBand.taxonomy.length > 0;
    if (hasTaxonomy) {
      // Tight inter-sub-band spacing. 38px accommodates the 2-line chrome
      // (name at -26, description at -12, rule at -4 relative to band top)
      // plus ~8px of breathing room before the next sub-band's first row.
      const SUB_BAND_GAP_Y = 38;
      const bandTop = cursorY;
      for (let si = 0; si < standaloneBand.taxonomy.length; si++) {
        const sub = standaloneBand.taxonomy[si];
        // Sub-band columns = min(category size, canvas capacity). Small
        // categories don't waste horizontal space on empty slots; large
        // ones wrap at the canvas-wide perRow.
        const subPerRow = Math.max(1, Math.min(perRow, sub.files.length));
        const subRows = Math.ceil(sub.files.length / subPerRow);
        const subBandH = subRows * CH_STANDALONE + Math.max(0, subRows - 1) * cardGapY;
        const subW = subPerRow * cw + Math.max(0, subPerRow - 1) * bandGapX;
        for (let i = 0; i < sub.files.length; i++) {
          const col = i % subPerRow;
          const row = Math.floor(i / subPerRow);
          positions[sub.files[i].id] = {
            x: leftPad + col * (cw + bandGapX),
            y: cursorY + row * (CH_STANDALONE + cardGapY),
          };
        }
        bandRects.push({
          key: 'standalone-sub',
          kind: 'sub-band',
          category: sub.category,
          description: sub.description,
          name: sub.category,
          x: leftPad,
          y: cursorY,
          w: subW,
          h: subBandH,
          count: sub.files.length,
        });
        cursorY += subBandH + (si < standaloneBand.taxonomy.length - 1 ? SUB_BAND_GAP_Y : 0);
      }
      // Outer wrapper — renders the umbrella "Standalone (N)" chrome is
      // suppressed by the renderer since each sub-band already carries its
      // own label. Kept so hit-testing / aggregate consumers still find the
      // full region by key='standalone'.
      bandRects.push({
        key: 'standalone',
        kind: 'band',
        name: standaloneBand.name,
        x: leftPad,
        y: bandTop,
        w: usableW,
        h: cursorY - bandTop,
        count: standaloneBand.files.length,
      });
      cursorY += bandGapY;
    } else {
      // Fallback: single compact grid when no taxonomy is available.
      const rows = Math.ceil(standaloneBand.files.length / perRow);
      const bandH = rows * CH_STANDALONE + Math.max(0, rows - 1) * cardGapY;
      for (let i = 0; i < standaloneBand.files.length; i++) {
        const col = i % perRow;
        const row = Math.floor(i / perRow);
        positions[standaloneBand.files[i].id] = {
          x: leftPad + col * (cw + bandGapX),
          y: cursorY + row * (CH_STANDALONE + cardGapY),
        };
      }
      bandRects.push({
        key: 'standalone',
        kind: 'band',
        name: standaloneBand.name,
        x: leftPad, y: cursorY,
        w: usableW,
        h: bandH,
        count: standaloneBand.files.length,
      });
      cursorY += bandH + bandGapY;
    }
    } // end else (standaloneCollapsed)
  }

  totalH = cursorY;

  // Build ELK IR with hand-positioned children. Use algorithm=fixed so ELK
  // respects (x, y) and only computes edge polylines. Keep FIXED_SIDE ports.
  //
  // Each edge gets UNIQUE per-edge ports on source (SOUTH) and target
  // (NORTH) so ELK fans them out along the card's bottom/top edges, giving
  // every arrow its own lane at the port. Shared .in/.out ports collapsed
  // every edge onto the card's midline — parallel arrows then stacked on
  // top of each other near the endpoints, which read as a single ribbon.
  // We keep SOUTH/NORTH everywhere: mixing EAST/WEST on the same card under
  // algorithm=fixed caused ELK to abort ("edge section count 0") for some
  // combinations. The card-detour post-pass handles obstacle avoidance.
  const outPortsByNode = {};
  const inPortsByNode = {};
  story.edges.forEach((e, i) => {
    (outPortsByNode[e.source] = outPortsByNode[e.source] || []).push(`${e.source}.out-gs${i}`);
    (inPortsByNode[e.target]  = inPortsByNode[e.target]  || []).push(`${e.target}.in-gs${i}`);
  });
  const children = [];
  for (const band of story.bands) {
    for (const f of band.files) {
      const pos = positions[f.id];
      if (!pos) continue;
      const isStandalone = standaloneIds.has(f.id);
      const nodeH = isStandalone ? CH_STANDALONE : ch;
      const ports = [];
      for (const pid of outPortsByNode[f.id] || []) {
        ports.push({ id: pid, properties: { 'port.side': 'SOUTH' } });
      }
      for (const pid of inPortsByNode[f.id] || []) {
        ports.push({ id: pid, properties: { 'port.side': 'NORTH' } });
      }
      // Fallback for isolated cards so ELK always has at least one port per side.
      if (ports.length === 0) {
        ports.push(_port(f.id, 'NORTH'), _port(f.id, 'SOUTH'));
      }
      children.push({
        id: f.id,
        x: pos.x,
        y: pos.y,
        width: cw,
        height: nodeH,
        ports,
        properties: {
          'org.eclipse.elk.portConstraints': 'FIXED_SIDE',
          'org.eclipse.elk.position': `(${pos.x},${pos.y})`,
        },
      });
    }
  }
  const edges = story.edges.map((e, i) => ({
    id: `gs${i}`,
    sources: [`${e.source}.out-gs${i}`],
    targets: [`${e.target}.in-gs${i}`],
    count: e.count,
    labelled: e.labelled,
    sourceNode: e.source,
    targetNode: e.target,
    kind: 'internal',
  }));
  const ir = {
    id: 'root',
    children,
    edges,
    layoutOptions: {
      'elk.algorithm': 'fixed',
      'elk.edgeRouting': 'ORTHOGONAL',
      // Wider edge-edge spacing stops parallel arrows from collapsing onto
      // the same horizontal/vertical run (each gets its own visible lane).
      // edgeNode spacing keeps the routed polylines clear of card borders
      // so the card-detour pass in the view rarely has to fire.
      'elk.spacing.edgeEdge': '24',
      'elk.spacing.edgeNode': '32',
    },
  };
  return {
    ir,
    positions,
    bandRects,
    canvasW: Math.max(totalW + 2 * leftPad, canvasWidth),
    canvasH: totalH + topPad,
  };
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
    const pairStats = (index && index.groupPairStats) || [];
    const includeFocusDetails = focusedGroup && edgeDetailMode !== 'overview';
    const selectedGroup = selected && byId[selected] ? ((byId[selected].group || 'Ungrouped')) : null;
    const focusSelection = includeFocusDetails && selected && selectedGroup === focusedGroup ? selected : null;

    // Pre-compute aggregate edges with UNIQUE ports per edge — same trick
    // as group-map (see _aggregateGroupEdges). Sharing `.in` / `.out` ports
    // across all aggregate edges of a group forces ELK to stack them; per-
    // edge ports give each aggregate arrow its own fanned-out corridor.
    const aggregateEdges = [];
    let aggIdx = 0;
    for (const rec of pairStats) {
      if (includeFocusDetails && (rec.sourceGroup === focusedGroup || rec.targetGroup === focusedGroup)) continue;
      const dims = _labelDims(rec.sourceGroup, rec.targetGroup, rec.count);
      aggregateEdges.push({
        id: `e-agg${aggIdx}`,
        sources: [`${rec.sourceGroup}.out-agg${aggIdx}`],
        targets: [`${rec.targetGroup}.in-agg${aggIdx}`],
        count: rec.count,
        kind: 'aggregate',
        sourceGroup: rec.sourceGroup,
        targetGroup: rec.targetGroup,
        labels: [{ text: '', width: dims.width, height: dims.height }],
      });
      aggIdx++;
    }

    const groupNodes = groups.map((g) => {
      const isFocused = focusedGroup === g;
      const isExpanded = isFocused;
      // Always expose the default shared ports for gateway edges (used when
      // a group is focused). Add per-aggregate-edge ports for any aggregate
      // edge touching this group.
      const ports = [_port(g, 'NORTH'), _port(g, 'SOUTH')];
      for (const e of aggregateEdges) {
        if (e.sourceGroup === g) ports.push({ id: e.sources[0], properties: { 'port.side': 'SOUTH' } });
        if (e.targetGroup === g) ports.push({ id: e.targets[0], properties: { 'port.side': 'NORTH' } });
      }
      const groupNode = {
        id: g,
        ports,
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

    const edges = [...aggregateEdges];
    let edgeId = aggregateEdges.length;
    const pushEdge = (sourcePort, targetPort, extra = {}) => {
      edges.push({
        id: `e${edgeId++}`,
        sources: [sourcePort],
        targets: [targetPort],
        ...extra,
      });
    };

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
