// layout.js — thin async wrapper around ELK.layout().
//
// Worker-ready from the start: if the page ships an inline worker source
// (<script id="elk-worker-source">) and the graph has more than
// WORKER_THRESHOLD nodes, we turn the inline source into a Blob URL and
// instantiate `new ELK({ workerUrl })`. Otherwise we run on the main thread.
//
// Both paths return the same promise, so callers don't branch on mode.

window.PX = window.PX || {};

PX.WORKER_THRESHOLD = 40;

PX.LAYOUT_OPTIONS = {
  'elk.algorithm': 'layered',
  'elk.direction': 'DOWN',
  'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.portConstraints': 'FIXED_SIDE',
  'elk.nodeSize.constraints': 'PORTS NODE_LABELS',
  'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
  // Generous room so 3-line colored labels + parallel arrow channels don't stack.
  'elk.spacing.nodeNode': '140',
  'elk.spacing.edgeNode': '40',
  'elk.spacing.edgeEdge': '32',
  'elk.spacing.portPort': '20',
  'elk.spacing.edgeLabel': '12',
  'elk.layered.spacing.nodeNodeBetweenLayers': '240',
  'elk.layered.spacing.edgeNodeBetweenLayers': '48',
  'elk.layered.spacing.edgeEdgeBetweenLayers': '40',
  // Nudge nodes apart if the router still can't avoid an overlap.
  'elk.layered.nodePlacement.bk.fixedAlignment': 'BALANCED',
  // Edge labels participate in layout. ELK reserves space for each edge's
  // declared label (see ir.js → _aggregateGroupEdges.labels) and routes
  // edges so foreign labels are AVOIDED. Placement CENTER keeps the label
  // on the middle stretch of the edge's trunk. SMART_UP picks the side
  // that minimises crossings with node and edge geometry.
  'elk.edgeLabels.placement': 'CENTER',
  'elk.edgeLabels.inline': 'true',
  'elk.layered.edgeLabels.sideSelection': 'SMART_UP',
};

let _workerUrlPromise = null;

function _workerUrl() {
  if (_workerUrlPromise) return _workerUrlPromise;
  _workerUrlPromise = new Promise((resolve) => {
    const src = document.getElementById('elk-worker-source');
    if (!src || !src.textContent) { resolve(null); return; }
    try {
      const blob = new Blob([src.textContent], { type: 'application/javascript' });
      resolve(URL.createObjectURL(blob));
    } catch (e) {
      console.warn('[prefxplain] could not build worker Blob URL, falling back to main thread:', e);
      resolve(null);
    }
  });
  return _workerUrlPromise;
}

PX.runLayout = async function runLayout(ir) {
  const nodeCount = PX.countNodes(ir);
  let elk;
  let workerUrl = null;
  if (typeof Worker !== 'undefined' && nodeCount > PX.WORKER_THRESHOLD) {
    workerUrl = await _workerUrl();
  }
  if (workerUrl) {
    // ELKNode's browser fallback still calls console.warn about 'web-worker'
    // even when a workerFactory is supplied (the warning fires *before*
    // ELKNode checks optionsClone.workerFactory). The user-supplied factory
    // is ultimately used, so the warning is a misleading false positive.
    // Silence it for this single constructor call.
    const origWarn = console.warn;
    console.warn = (msg, ...rest) => {
      if (typeof msg === 'string' && msg.indexOf("'web-worker' package not installed") !== -1) return;
      return origWarn.call(console, msg, ...rest);
    };
    try {
      elk = new ELK({
        workerUrl,
        workerFactory: (url) => new Worker(url),
      });
    } finally {
      console.warn = origWarn;
    }
    console.log(`[prefxplain] layout: worker path (${nodeCount} nodes)`);
  } else {
    elk = new ELK();
    console.log(`[prefxplain] layout: main thread (${nodeCount} nodes)`);
  }
  const withOptions = {
    ...ir,
    layoutOptions: Object.assign({}, PX.LAYOUT_OPTIONS, ir.layoutOptions || {})
  };
  const t0 = performance.now();
  const laid = await elk.layout(withOptions);
  const t1 = performance.now();
  console.log(`[prefxplain] layout done in ${(t1 - t0).toFixed(0)} ms`);
  return laid;
};
