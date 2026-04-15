"""Graph data structures for PrefXplain.

Nodes are files. Edges are import/dependency relationships.
Schema is PrefOptimize-compatible: nodes.id = file_path, edges.type = event_type.
"""

from __future__ import annotations

import fnmatch
import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal


@dataclass
class Symbol:
    name: str
    kind: Literal["function", "class", "variable", "import"]
    line: int
    description: str = ""   # short natural-language hint, e.g. "parses CLI arguments"

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "kind": self.kind, "line": self.line}
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Symbol:
        return cls(
            name=d["name"], kind=d["kind"], line=d["line"],
            description=d.get("description", ""),
        )


@dataclass
class Node:
    id: str          # relative file path from repo root, e.g. "src/auth/token.py"
    label: str       # filename only, e.g. "token.py"
    description: str = ""
    short_title: str = ""  # 1-3 word role label shown on the card, e.g. "Graph Engine"
    symbols: list[Symbol] = field(default_factory=list)
    language: str = ""
    size: int = 0    # file size in bytes
    role: str = ""   # architectural role: entry_point, utility, data_model, etc.
    group: str = ""  # AI-assigned architectural group, e.g. "Analysis Pipeline"
    preview: str = ""  # first ~50 lines of the file content (for sidebar code panel)
    flowchart: dict | None = None  # AI-generated flowchart: {nodes: [...], edges: [...]}
    highlights: list[str] = field(default_factory=list)  # concrete, codebase-specific facts (e.g. integrations, model names, hyperparameters)

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "short_title": self.short_title,
            "symbols": [s.to_dict() for s in self.symbols],
            "language": self.language,
            "size": self.size,
        }
        if self.role:
            d["role"] = self.role
        if self.group:
            d["group"] = self.group
        if self.preview:
            d["preview"] = self.preview
        if self.flowchart:
            d["flowchart"] = self.flowchart
        if self.highlights:
            d["highlights"] = self.highlights
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Node:
        return cls(
            id=d["id"],
            label=d["label"],
            description=d.get("description", ""),
            short_title=d.get("short_title", ""),
            symbols=[Symbol.from_dict(s) for s in d.get("symbols", [])],
            language=d.get("language", ""),
            size=d.get("size", 0),
            role=d.get("role", ""),
            group=d.get("group", ""),
            preview=d.get("preview", ""),
            flowchart=d.get("flowchart"),
            highlights=list(d.get("highlights") or []),
        )


@dataclass
class Edge:
    source: str       # node id
    target: str       # node id
    type: str = "imports"
    symbols: list[str] = field(default_factory=list)  # specific symbols imported

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "symbols": self.symbols,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Edge:
        return cls(
            source=d["source"],
            target=d["target"],
            type=d.get("type", "imports"),
            symbols=d.get("symbols", []),
        )


@dataclass
class GraphMetadata:
    repo: str
    generated_at: str
    total_files: int
    languages: list[str]
    codemap_version: str = "0.1.0"
    summary: str = ""       # LLM-generated plain-English overview of the codebase
    health_score: int = 0   # 1-10 architecture health rating
    health_notes: str = ""  # plain-English health interpretation
    groups: dict[str, str] = field(default_factory=dict)  # AI group name → description
    group_highlights: dict[str, list[str]] = field(default_factory=dict)  # AI group name → concrete facts

    def to_dict(self) -> dict:
        d = {
            "repo": self.repo,
            "generated_at": self.generated_at,
            "total_files": self.total_files,
            "languages": self.languages,
            "codemap_version": self.codemap_version,
        }
        if self.summary:
            d["summary"] = self.summary
        if self.health_score:
            d["health_score"] = self.health_score
        if self.health_notes:
            d["health_notes"] = self.health_notes
        if self.groups:
            d["groups"] = self.groups
        if self.group_highlights:
            d["group_highlights"] = self.group_highlights
        return d

    @classmethod
    def from_dict(cls, d: dict) -> GraphMetadata:
        return cls(
            repo=d["repo"],
            generated_at=d["generated_at"],
            total_files=d["total_files"],
            languages=d["languages"],
            codemap_version=d.get("codemap_version", "0.1.0"),
            summary=d.get("summary", ""),
            health_score=d.get("health_score", 0),
            health_notes=d.get("health_notes", ""),
            groups=d.get("groups", {}),
            group_highlights=dict(d.get("group_highlights") or {}),
        )


ROLE_LABELS: dict[str, str] = {
    "entry_point": "Entry Points",
    "api_route":   "API Layer",
    "data_model":  "Data Models",
    "utility":     "Utilities",
    "config":      "Configuration",
    "test":        "Tests",
    "other":       "Other",
}

# Human-friendly subtitle shown under each cluster header
ROLE_SUBTITLES: dict[str, str] = {
    "entry_point": "Where the program starts — run these files to launch the app",
    "api_route":   "Routes & controllers — handles requests coming in from outside",
    "data_model":  "Data shapes & schemas — defines what your data looks like",
    "utility":     "Helper functions — reusable tools used everywhere else",
    "config":      "Settings & constants — controls how the app behaves",
    "test":        "Tests — checks that everything works correctly",
    "other":       "Other files that didn't fit the categories above",
}

# Semantic ordering: high-level concepts first, low-level infrastructure last
ROLE_ORDER: list[str] = [
    "entry_point", "api_route", "data_model", "utility", "config", "test", "other",
]


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    metadata: GraphMetadata = field(default_factory=lambda: GraphMetadata(
        repo="", generated_at="", total_files=0, languages=[],
    ))

    def get_node(self, node_id: str) -> Node | None:
        return self._node_index.get(node_id)

    @property
    def _node_index(self) -> dict[str, Node]:
        """Lazily build a dict index for O(1) node lookups.

        Invalidated when the node list length changes.
        """
        cache = getattr(self, "_cached_node_index", None)
        if cache is None or len(cache) != len(self.nodes):
            index = {n.id: n for n in self.nodes}
            self._cached_node_index = index  # type: ignore[attr-defined]
            return index
        return cache

    def neighbors(self, node_id: str) -> list[str]:
        """Return all node ids directly connected to node_id."""
        result: set[str] = set()
        for e in self.edges:
            if e.source == node_id:
                result.add(e.target)
            elif e.target == node_id:
                result.add(e.source)
        return list(result)

    @property
    def _degree_cache(self) -> tuple[dict[str, int], dict[str, int]]:
        """Lazily build in/out degree dicts for O(1) lookups."""
        cache = getattr(self, "_cached_degrees", None)
        edge_count = getattr(self, "_cached_degrees_edge_count", -1)
        if cache is None or edge_count != len(self.edges):
            in_deg: dict[str, int] = defaultdict(int)
            out_deg: dict[str, int] = defaultdict(int)
            for e in self.edges:
                in_deg[e.target] += 1
                out_deg[e.source] += 1
            self._cached_degrees = (in_deg, out_deg)
            self._cached_degrees_edge_count = len(self.edges)
            return in_deg, out_deg
        return cache

    def outdegree(self, node_id: str) -> int:
        """Number of files this node imports."""
        _, out_deg = self._degree_cache
        return out_deg.get(node_id, 0)

    def indegree(self, node_id: str) -> int:
        """Number of files that import this node."""
        in_deg, _ = self._degree_cache
        return in_deg.get(node_id, 0)

    # ------------------------------------------------------------------
    # Cycle detection (Tarjan's SCC)
    # ------------------------------------------------------------------

    def find_cycles(self) -> list[list[str]]:
        """Find circular dependencies using Tarjan's strongly connected components.

        Returns a list of cycles, where each cycle is a list of node ids.
        Only returns SCCs with 2+ nodes (actual circular deps).
        """
        import sys
        needed = max(1000, len(self.nodes) * 2)
        if sys.getrecursionlimit() < needed:
            sys.setrecursionlimit(needed)
        adj: dict[str, list[str]] = defaultdict(list)
        for e in self.edges:
            adj[e.source].append(e.target)

        index_counter = [0]
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        sccs: list[list[str]] = []

        def strongconnect(v: str) -> None:
            indices[v] = lowlinks[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w in adj.get(v, []):
                if w not in indices:
                    strongconnect(w)
                    lowlinks[v] = min(lowlinks[v], lowlinks[w])
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], indices[w])

            if lowlinks[v] == indices[v]:
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    sccs.append(scc[::-1])

        all_nodes = {n.id for n in self.nodes}
        for node_id in sorted(all_nodes):
            if node_id not in indices:
                strongconnect(node_id)

        return sccs

    def cycle_node_ids(self) -> set[str]:
        """Return the set of all node ids that participate in any cycle."""
        ids: set[str] = set()
        for cycle in self.find_cycles():
            ids.update(cycle)
        return ids

    def cycle_edges(self) -> set[tuple[str, str]]:
        """Return edges (source, target) that are part of a cycle."""
        result: set[tuple[str, str]] = set()
        for cycle in self.find_cycles():
            cycle_set = set(cycle)
            adj: dict[str, set[str]] = defaultdict(set)
            for e in self.edges:
                if e.source in cycle_set and e.target in cycle_set:
                    adj[e.source].add(e.target)
            for node in cycle:
                for neighbor in adj.get(node, set()):
                    if neighbor in cycle_set:
                        result.add((node, neighbor))
        return result

    # ------------------------------------------------------------------
    # Connected components
    # ------------------------------------------------------------------

    def connected_components(self) -> list[set[str]]:
        """Find weakly connected components (ignoring edge direction)."""
        adj: dict[str, set[str]] = defaultdict(set)
        for e in self.edges:
            adj[e.source].add(e.target)
            adj[e.target].add(e.source)

        visited: set[str] = set()
        components: list[set[str]] = []

        for node in self.nodes:
            if node.id in visited:
                continue
            component: set[str] = set()
            queue = deque([node.id])
            while queue:
                v = queue.popleft()
                if v in visited:
                    continue
                visited.add(v)
                component.add(v)
                for w in adj.get(v, set()):
                    if w not in visited:
                        queue.append(w)
            components.append(component)

        return sorted(components, key=len, reverse=True)

    # ------------------------------------------------------------------
    # Centrality metrics
    # ------------------------------------------------------------------

    def betweenness_centrality(self) -> dict[str, float]:
        """Compute betweenness centrality for all nodes (Brandes' algorithm)."""
        node_ids = [n.id for n in self.nodes]
        node_id_set = set(node_ids)
        adj: dict[str, list[str]] = defaultdict(list)
        for e in self.edges:
            if e.source in node_id_set and e.target in node_id_set:
                adj[e.source].append(e.target)

        centrality: dict[str, float] = {nid: 0.0 for nid in node_ids}

        for s in node_ids:
            bfs_stack: list[str] = []
            pred: dict[str, list[str]] = {nid: [] for nid in node_ids}
            sigma: dict[str, int] = {nid: 0 for nid in node_ids}
            sigma[s] = 1
            dist: dict[str, int] = {nid: -1 for nid in node_ids}
            dist[s] = 0
            queue: deque[str] = deque([s])

            while queue:
                v = queue.popleft()
                bfs_stack.append(v)
                for w in adj.get(v, []):
                    if dist[w] < 0:
                        dist[w] = dist[v] + 1
                        queue.append(w)
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        pred[w].append(v)

            delta: dict[str, float] = {nid: 0.0 for nid in node_ids}
            while bfs_stack:
                w = bfs_stack.pop()
                for v in pred[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
                if w != s:
                    centrality[w] += delta[w]

        n = len(node_ids)
        if n > 2:
            norm = 1.0 / ((n - 1) * (n - 2))
            centrality = {k: v * norm for k, v in centrality.items()}

        return centrality

    def pagerank(self, damping: float = 0.85, iterations: int = 100) -> dict[str, float]:
        """Compute PageRank for all nodes."""
        node_ids = [n.id for n in self.nodes]
        n = len(node_ids)
        if n == 0:
            return {}

        adj: dict[str, list[str]] = defaultdict(list)
        out_count: dict[str, int] = defaultdict(int)
        for e in self.edges:
            adj[e.target].append(e.source)
            out_count[e.source] += 1

        rank: dict[str, float] = {nid: 1.0 / n for nid in node_ids}

        for _ in range(iterations):
            new_rank: dict[str, float] = {}
            for nid in node_ids:
                incoming = sum(
                    rank[src] / out_count[src]
                    for src in adj.get(nid, [])
                    if out_count[src] > 0
                )
                new_rank[nid] = (1 - damping) / n + damping * incoming
            rank = new_rank

        return rank

    # ------------------------------------------------------------------
    # Graph metrics summary
    # ------------------------------------------------------------------

    def metrics(self) -> dict:
        """Compute a full metrics summary for the graph."""
        cycles = self.find_cycles()
        components = self.connected_components()
        centrality = self.betweenness_centrality()
        pr = self.pagerank()

        top_central = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]
        top_imported = sorted(
            [(n.id, self.indegree(n.id)) for n in self.nodes],
            key=lambda x: x[1], reverse=True,
        )[:10]
        top_importing = sorted(
            [(n.id, self.outdegree(n.id)) for n in self.nodes],
            key=lambda x: x[1], reverse=True,
        )[:10]
        top_pagerank = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_files": len(self.nodes),
            "total_edges": len(self.edges),
            "cycles": len(cycles),
            "cycle_details": [{"files": c} for c in cycles],
            "components": len(components),
            "largest_component": len(components[0]) if components else 0,
            "top_centrality": [{"id": k, "score": round(v, 4)} for k, v in top_central],
            "top_imported": [{"id": k, "indegree": v} for k, v in top_imported],
            "top_importing": [{"id": k, "outdegree": v} for k, v in top_importing],
            "top_pagerank": [{"id": k, "score": round(v, 6)} for k, v in top_pagerank],
        }

    # ------------------------------------------------------------------
    # Filtering and subgraphs
    # ------------------------------------------------------------------

    def filter_subgraph(self, pattern: str) -> Graph:
        """Return a new graph containing only nodes matching the glob pattern."""
        matching_ids: set[str] = set()
        for node in self.nodes:
            if fnmatch.fnmatch(node.id, pattern):
                matching_ids.add(node.id)

        new_nodes = [n for n in self.nodes if n.id in matching_ids]
        new_edges = [
            e for e in self.edges
            if e.source in matching_ids and e.target in matching_ids
        ]

        new_graph = Graph(nodes=new_nodes, edges=new_edges)
        if self.metadata:
            new_graph.metadata = GraphMetadata(
                repo=self.metadata.repo,
                generated_at=self.metadata.generated_at,
                total_files=len(new_nodes),
                languages=sorted(set(n.language for n in new_nodes if n.language)),
                codemap_version=self.metadata.codemap_version,
            )
        return new_graph

    def depth_subgraph(self, node_id: str, max_depth: int) -> Graph:
        """Return a subgraph within max_depth hops of node_id (both directions)."""
        if self.get_node(node_id) is None:
            return Graph(metadata=self.metadata)

        adj: dict[str, set[str]] = defaultdict(set)
        for e in self.edges:
            adj[e.source].add(e.target)
            adj[e.target].add(e.source)

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue:
            v, depth = queue.popleft()
            if v in visited:
                continue
            visited.add(v)
            if depth < max_depth:
                for w in adj.get(v, set()):
                    if w not in visited:
                        queue.append((w, depth + 1))

        new_nodes = [n for n in self.nodes if n.id in visited]
        new_edges = [
            e for e in self.edges
            if e.source in visited and e.target in visited
        ]

        new_graph = Graph(nodes=new_nodes, edges=new_edges)
        if self.metadata:
            new_graph.metadata = GraphMetadata(
                repo=self.metadata.repo,
                generated_at=self.metadata.generated_at,
                total_files=len(new_nodes),
                languages=sorted(set(n.language for n in new_nodes if n.language)),
                codemap_version=self.metadata.codemap_version,
            )
        return new_graph

    # ------------------------------------------------------------------
    # Clustering
    # ------------------------------------------------------------------

    def cluster_by_directory(self) -> dict[str, list[str]]:
        """Group node ids by their parent directory."""
        clusters: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            parent = str(PurePosixPath(node.id).parent)
            if parent == ".":
                parent = "(root)"
            clusters[parent].append(node.id)
        return dict(clusters)

    def cluster_by_group(self) -> dict[str, list[str]]:
        """Group node ids by AI-assigned architectural group."""
        clusters: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            if node.group:
                clusters[node.group].append(node.id)
        return dict(clusters) if clusters else {}

    def cluster_by_role(self) -> dict[str, list[str]]:
        """Group node ids by architectural role, keyed by human-readable label."""
        clusters: dict[str, list[str]] = defaultdict(list)
        for node in self.nodes:
            role = node.role or "other"
            label = ROLE_LABELS.get(role, "Other")
            clusters[label].append(node.id)
        return {k: v for k, v in clusters.items() if v}

    # ------------------------------------------------------------------
    # Role inference
    # ------------------------------------------------------------------

    def infer_roles(self) -> None:
        """Assign architectural roles to nodes based on name patterns and graph position."""
        entry_names = {"main", "index", "app", "server", "cli", "entry", "__main__"}
        model_names = {"model", "models", "schema", "schemas", "types", "entities"}
        route_names = {
            "route", "routes", "api", "endpoint", "endpoints",
            "view", "views", "controller", "controllers",
        }
        config_names = {"config", "settings", "env", "constants", "conf"}
        test_names = {"test", "tests", "spec", "specs", "__tests__"}
        util_names = {"util", "utils", "helpers", "helper", "lib", "common", "shared"}

        for node in self.nodes:
            if node.role:
                continue

            stem = PurePosixPath(node.id).stem.lower()
            parts_lower = {p.lower() for p in PurePosixPath(node.id).parts[:-1]}

            if stem in test_names or test_names & parts_lower:
                node.role = "test"
            elif stem in config_names or stem.startswith("config"):
                node.role = "config"
            elif stem in model_names or model_names & parts_lower:
                node.role = "data_model"
            elif stem in route_names or route_names & parts_lower:
                node.role = "api_route"
            elif stem in entry_names:
                node.role = "entry_point"
            elif stem in util_names or util_names & parts_lower:
                node.role = "utility"

        # Heuristic: high indegree with no role -> utility
        for node in self.nodes:
            if node.role:
                continue
            if self.indegree(node.id) >= 3:
                node.role = "utility"
            elif self.outdegree(node.id) >= 3 and self.indegree(node.id) == 0:
                node.role = "entry_point"

    def infer_groups(self) -> None:
        """Assign architectural groups when no curated grouping exists yet."""
        from .diagram import apply_inferred_groups

        apply_inferred_groups(self)

    # ------------------------------------------------------------------
    # Health score
    # ------------------------------------------------------------------

    def health_score(self) -> dict:
        """Compute a 0-100 health score with a breakdown of penalties.

        Penalties:
          - Cycles: -15 per cycle (capped at -45)
          - Fragmentation: -10 per disconnected component beyond the first (capped at -30)
          - High coupling: -10 if max indegree > 30% of file count
          - Large files: -5 if any file has > 50 symbols
        """
        score = 100
        breakdown: list[dict] = []

        cycles = self.find_cycles()
        if cycles:
            penalty = min(len(cycles) * 15, 45)
            score -= penalty
            breakdown.append({
                "label": f"{len(cycles)} circular dependency chain(s)",
                "penalty": -penalty,
                "severity": "critical",
            })

        components = self.connected_components()
        if len(components) > 1:
            penalty = min((len(components) - 1) * 10, 30)
            score -= penalty
            breakdown.append({
                "label": f"{len(components)} disconnected component(s)",
                "penalty": -penalty,
                "severity": "warning",
            })

        if self.nodes:
            max_in = max((self.indegree(n.id) for n in self.nodes), default=0)
            if max_in > max(3, len(self.nodes) * 0.3):
                score -= 10
                breakdown.append({
                    "label": f"High coupling (max indegree={max_in})",
                    "penalty": -10,
                    "severity": "warning",
                })

        fat_files = [n for n in self.nodes if len(n.symbols) > 50]
        if fat_files:
            score -= 5
            breakdown.append({
                "label": f"{len(fat_files)} file(s) with 50+ symbols",
                "penalty": -5,
                "severity": "info",
            })

        score = max(0, min(100, score))
        return {"score": score, "breakdown": breakdown}

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata.to_dict(),
        }

    def to_render_dict(self) -> dict:
        """Bundle graph + precomputed analysis for the renderer.

        The renderer consumes this payload directly — all graph algorithms
        run in Python so the JS side only handles layout and interaction.
        """
        from .diagram import build_node_semantics, build_semantic_diagram

        # Render paths can be reached from prefxplain.json loads that do not
        # carry inferred roles. Recompute them here so the diagram model always
        # has a stable semantic base.
        self.infer_roles()
        self.infer_groups()

        base = self.to_dict()

        clusters = self.cluster_by_directory()
        clusters_by_role = self.cluster_by_role()
        cycle_edges_list = [list(e) for e in sorted(self.cycle_edges())]
        cycle_node_set = self.cycle_node_ids()
        metrics = self.metrics()
        health = self.health_score()
        semantic_diagram = build_semantic_diagram(self)
        node_semantics = build_node_semantics(self)

        # Per-node metrics dict: indegree, outdegree, pagerank, role, in_cycle
        pr = self.pagerank()
        in_deg, out_deg = self._degree_cache
        node_metrics: dict[str, dict] = {}
        for n in self.nodes:
            node_metrics[n.id] = {
                "indegree": in_deg.get(n.id, 0),
                "outdegree": out_deg.get(n.id, 0),
                "pagerank": round(pr.get(n.id, 0.0), 6),
                "role": n.role or "",
                "in_cycle": n.id in cycle_node_set,
            }

        # Language breakdown — by bytes (like GitHub), with file count alongside
        lang_counts: dict[str, int] = defaultdict(int)
        lang_file_counts: dict[str, int] = defaultdict(int)
        for n in self.nodes:
            lang = n.language or "other"
            lang_counts[lang] += n.size if n.size > 0 else 1
            lang_file_counts[lang] += 1

        clusters_by_group = self.cluster_by_group()

        base.update({
            "clusters": clusters,
            "clusters_by_role": clusters_by_role,
            "clusters_by_group": clusters_by_group,
            "group_descriptions": self.metadata.groups,
            "semantic_diagram": semantic_diagram.to_dict(),
            "node_semantics": node_semantics,
            "role_order": ROLE_ORDER,
            "role_subtitles": ROLE_SUBTITLES,
            "cycle_edges": cycle_edges_list,
            "cycle_node_ids": sorted(cycle_node_set),
            "metrics": metrics,
            "node_metrics": node_metrics,
            "health": health,
            "language_counts": dict(lang_counts),
            "language_file_counts": dict(lang_file_counts),
        })
        return base

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> Graph:
        data = json.loads(path.read_text())
        meta = data.get("metadata", {})
        graph = cls(
            nodes=[Node.from_dict(n) for n in data.get("nodes", [])],
            edges=[Edge.from_dict(e) for e in data.get("edges", [])],
            metadata=GraphMetadata.from_dict(meta) if meta else GraphMetadata(
                repo="", generated_at="", total_files=0, languages=[],
            ),
        )
        return graph

    @classmethod
    def empty(cls, root_path: Path) -> Graph:
        return cls(
            metadata=GraphMetadata(
                repo=root_path.name,
                generated_at=datetime.now(timezone.utc).isoformat(),
                total_files=0,
                languages=[],
            )
        )
