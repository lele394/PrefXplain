"""Semantic diagram builder for PrefXplain.

Transforms a file-level dependency graph into a higher-level diagram model that
the renderer can consume directly.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import Graph, Node


TEST_SEGMENTS = {"test", "tests", "spec", "specs", "__tests__"}
GENERIC_DIR_SEGMENTS = {
    "src", "lib", "libs", "app", "apps", "pkg", "packages", "modules",
    "module", "services", "service", "internal", "core",
}
ROLE_ORDER = [
    "entry_point", "api_route", "data_model", "utility", "config", "test", "other",
]
FLOW_KEYWORDS: dict[str, tuple[str, str]] = {
    "validate": ("decision", "validates"),
    "check": ("decision", "checks"),
    "question": ("decision", "questions"),
    "prompt": ("decision", "questions"),
    "decide": ("decision", "decides"),
    "analy": ("analysis", "analyzes"),
    "scan": ("analysis", "scans"),
    "inspect": ("analysis", "inspects"),
    "parse": ("analysis", "parses"),
    "score": ("analysis", "scores"),
    "render": ("process", "renders"),
    "draw": ("process", "renders"),
    "paint": ("process", "renders"),
    "view": ("process", "renders"),
    "query": ("process", "queries"),
    "search": ("process", "queries"),
    "lookup": ("process", "queries"),
    "load": ("data", "reads"),
    "read": ("data", "reads"),
    "write": ("data", "writes"),
    "save": ("data", "writes"),
    "store": ("data", "persists"),
    "persist": ("data", "persists"),
    "cache": ("data", "caches"),
    "export": ("process", "exports"),
    "serialize": ("process", "exports"),
    "decode": ("process", "reads"),
    "encode": ("process", "writes"),
    "import": ("process", "uses"),
    "depend": ("process", "depends on"),
    "test": ("test", "tests"),
    "assert": ("test", "tests"),
    "verify": ("test", "tests"),
}
KIND_TO_SHAPE = {
    "entry": "entry",
    "process": "process",
    "decision": "decision",
    "analysis": "analysis",
    "data": "data",
    "external": "external",
    "test": "test",
}
KIND_ORDER = ["entry", "process", "analysis", "decision", "data", "external", "test"]
MAX_DETAIL_MEMBERS = 5
TEST_GROUP_LABEL = "Tests"


@dataclass(frozen=True)
class CapabilityProfile:
    key: str
    label: str
    description: str
    keywords: tuple[str, ...]
    roles: tuple[str, ...] = ()
    fallback: str = ""
    standalone: bool = False


CAPABILITY_PROFILES = [
    CapabilityProfile(
        key="integration",
        label="CLI & Integrations",
        description="Entrypoints and external integrations that expose PrefXplain to users or tools.",
        keywords=("cli", "command", "terminal", "mcp", "server", "stdio", "tool", "entry"),
        roles=("entry_point", "api_route"),
        fallback="Code Analysis",
    ),
    CapabilityProfile(
        key="analysis",
        label="Code Analysis",
        description="Scans source files, parses dependencies, and validates architectural rules.",
        keywords=("analy", "parse", "parser", "scan", "walk", "inspect", "check", "checker", "rule", "ast", "regex", "import"),
    ),
    CapabilityProfile(
        key="model",
        label="Graph Data Model",
        description="Owns the dependency graph structures, metrics, and shared architecture state.",
        keywords=("graph", "node", "edge", "model", "schema", "pagerank", "tarjan", "cycle", "centrality", "cluster", "serialize"),
        roles=("data_model", "config"),
        standalone=True,
    ),
    CapabilityProfile(
        key="diagram",
        label="Interactive Diagram",
        description="Builds and renders the interactive diagram, layouts, and visual drill-down views.",
        keywords=("render", "diagram", "layout", "canvas", "svg", "html", "view", "overlay", "tooltip", "matrix", "visual"),
    ),
    CapabilityProfile(
        key="description",
        label="Description Engine",
        description="Generates natural-language summaries, flowcharts, and semantic metadata for the graph.",
        keywords=("describe", "description", "prompt", "llm", "summary", "cache", "sqlite", "flowchart"),
        fallback="Code Analysis",
    ),
    CapabilityProfile(
        key="export",
        label="Exports & Context",
        description="Turns the graph into export formats and agent-friendly context views.",
        keywords=("export", "mermaid", "graphviz", "dot", "context", "agent", "dump"),
        fallback="Interactive Diagram",
    ),
]
PROFILE_BY_LABEL = {profile.label: profile for profile in CAPABILITY_PROFILES}
TOKEN_RE = re.compile(r"[a-z0-9_]+")
GENERATED_GROUP_LABELS = {profile.label for profile in CAPABILITY_PROFILES} | {TEST_GROUP_LABEL}


@dataclass
class SemanticDiagramNode:
    id: str
    label: str
    kind: str
    shape: str
    summary: str = ""
    members: list[str] = field(default_factory=list)
    role: str = ""
    level: int = 0
    detail: dict | None = None
    highlights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "shape": self.shape,
            "members": self.members,
            "level": self.level,
        }
        if self.summary:
            data["summary"] = self.summary
        if self.role:
            data["role"] = self.role
        if self.detail:
            data["detail"] = self.detail
        if self.highlights:
            data["highlights"] = self.highlights
        return data


@dataclass
class SemanticDiagramEdge:
    source: str
    target: str
    kind: str
    label: str
    weight: int = 1

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "label": self.label,
            "weight": self.weight,
        }


@dataclass
class SemanticDiagram:
    nodes: list[SemanticDiagramNode]
    edges: list[SemanticDiagramEdge]
    layout_hint: str = "layered"
    legend: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "layout_hint": self.layout_hint,
            "legend": self.legend,
        }


def build_node_semantics(graph: Graph) -> dict[str, dict]:
    """Return per-file semantic metadata used by the renderer."""
    result: dict[str, dict] = {}
    for node in graph.nodes:
        entry: dict = {
            "kind": infer_node_kind(node),
            "shape": KIND_TO_SHAPE[infer_node_kind(node)],
            "summary": first_sentence(node.description) or display_node_name(node),
            "role": node.role or "",
        }
        if node.highlights:
            entry["highlights"] = list(node.highlights)
        result[node.id] = entry
    return result


def build_semantic_diagram(graph: Graph) -> SemanticDiagram:
    """Build a renderer-friendly semantic diagram from a Graph."""
    if not graph.nodes:
        return SemanticDiagram(nodes=[], edges=[], legend=_legend_items())

    apply_inferred_groups(graph)

    node_lookup = {node.id: node for node in graph.nodes}
    pagerank = graph.pagerank() if graph.nodes else {}
    source_kind, cluster_map = select_group_source(graph)
    if len(cluster_map) < 2:
        cluster_map = fallback_cluster_map(graph)
        source_kind = "role"

    diagram_nodes: list[SemanticDiagramNode] = []
    member_to_group: dict[str, str] = {}

    for index, (group_key, member_ids) in enumerate(sorted(cluster_map.items())):
        child_nodes = [node_lookup[node_id] for node_id in member_ids if node_id in node_lookup]
        if not child_nodes:
            continue
        label = group_display_label(source_kind, group_key, child_nodes)
        role = dominant_role(child_nodes)
        kind = infer_group_kind(child_nodes, role)
        shape = KIND_TO_SHAPE[kind]
        summary = summarize_group(graph, source_kind, group_key, label, child_nodes, pagerank)
        group_id = f"semantic:{source_kind}:{slugify(group_key or label)}:{index}"
        detail = build_group_detail(graph, child_nodes, label)
        group_highlights_map = getattr(graph.metadata, "group_highlights", {}) or {}
        group_highlights = list(group_highlights_map.get(label) or group_highlights_map.get(group_key) or [])
        semantic_node = SemanticDiagramNode(
            id=group_id,
            label=label,
            kind=kind,
            shape=shape,
            summary=summary,
            members=[node.id for node in child_nodes],
            role=role,
            detail=detail,
            highlights=group_highlights,
        )
        diagram_nodes.append(semantic_node)
        for node in child_nodes:
            member_to_group[node.id] = group_id

    diagram_edges = build_group_edges(graph, member_to_group, diagram_nodes, node_lookup)
    apply_topological_levels(diagram_nodes, diagram_edges)
    return SemanticDiagram(
        nodes=diagram_nodes,
        edges=diagram_edges,
        legend=_legend_items(),
    )


def _legend_items() -> list[dict[str, str]]:
    return [
        {"kind": "entry", "shape": "entry", "label": "Entry / start"},
        {"kind": "process", "shape": "process", "label": "Action / process"},
        {"kind": "analysis", "shape": "analysis", "label": "Analysis"},
        {"kind": "decision", "shape": "decision", "label": "Decision / question"},
        {"kind": "data", "shape": "data", "label": "Data / state"},
        {"kind": "test", "shape": "test", "label": "Test / verification"},
    ]


def apply_inferred_groups(graph: Graph) -> None:
    """Populate missing architectural groups and descriptions in-place."""
    assignments, descriptions = infer_architectural_groups(graph)
    if not getattr(graph.metadata, "groups", None):
        graph.metadata.groups = {}

    for node in graph.nodes:
        inferred = assignments.get(node.id)
        if inferred and (not node.group or is_generated_group_label(node.group)):
            node.group = inferred

    for label, description in descriptions.items():
        if description:
            if label not in graph.metadata.groups or is_generated_group_label(label):
                graph.metadata.groups[label] = description


def infer_architectural_groups(graph: Graph) -> tuple[dict[str, str], dict[str, str]]:
    """Infer functional group labels when the graph has no AI-authored grouping."""
    assignments = {
        node.id: node.group
        for node in graph.nodes
        if node.group and not is_generated_group_label(node.group)
    }
    descriptions = dict(graph.metadata.groups or {})
    explicit_labels = {
        node.group
        for node in graph.nodes
        if node.group and not is_generated_group_label(node.group)
    }

    for node in graph.nodes:
        if node.id in assignments:
            continue
        label = classify_capability_group(node)
        if label:
            assignments[node.id] = label

    for node in graph.nodes:
        if node.id in assignments:
            continue
        exclude = {TEST_GROUP_LABEL} if node.role != "test" else set()
        label = dominant_neighbor_group(graph, node.id, assignments, exclude=exclude)
        if label:
            assignments[node.id] = label

    for node in graph.nodes:
        if node.id in assignments:
            continue
        if node.role == "test":
            assignments[node.id] = TEST_GROUP_LABEL
        elif node.role in {"entry_point", "api_route"}:
            assignments[node.id] = "CLI & Integrations"
        elif node.role in {"data_model", "config"}:
            assignments[node.id] = "Graph Data Model"
        else:
            assignments[node.id] = "Code Analysis"

    assignments = rebalance_inferred_groups(graph, assignments, explicit_labels)

    for label in set(assignments.values()):
        if label in descriptions:
            continue
        profile = PROFILE_BY_LABEL.get(label)
        if profile:
            descriptions[label] = profile.description
        elif label == TEST_GROUP_LABEL:
            descriptions[label] = "Exercises the behavior of the codebase."

    return assignments, descriptions


def rebalance_inferred_groups(
    graph: Graph,
    assignments: dict[str, str],
    explicit_labels: set[str],
) -> dict[str, str]:
    """Merge weak singleton buckets into related functional groups."""
    current = dict(assignments)

    while True:
        buckets: dict[str, list[str]] = defaultdict(list)
        for node_id, label in current.items():
            buckets[label].append(node_id)

        changed = False
        for label, node_ids in list(buckets.items()):
            if label == TEST_GROUP_LABEL or label in explicit_labels:
                continue
            if len(node_ids) != 1:
                continue

            node_id = node_ids[0]
            node = graph.get_node(node_id)
            if not node:
                continue
            profile = PROFILE_BY_LABEL.get(label)
            if should_keep_singleton_group(graph, node, profile):
                continue

            exclude = {label}
            if node.role != "test":
                exclude.add(TEST_GROUP_LABEL)
            target = ""
            if profile and profile.fallback and profile.fallback in buckets:
                target = profile.fallback
            if not target:
                target = dominant_neighbor_group(
                    graph,
                    node_id,
                    {other_id: other_label for other_id, other_label in current.items() if other_id != node_id},
                    exclude=exclude,
                )
            if not target:
                continue

            current[node_id] = target
            changed = True
            break

        if not changed:
            return current


def should_keep_singleton_group(graph: Graph, node: Node, profile: CapabilityProfile | None) -> bool:
    if not profile:
        return False
    return profile.standalone


def dominant_neighbor_group(
    graph: Graph,
    node_id: str,
    assignments: dict[str, str],
    exclude: set[str] | None = None,
) -> str:
    exclude = exclude or set()
    counts: Counter[str] = Counter()
    for edge in graph.edges:
        if edge.source == node_id:
            label = assignments.get(edge.target)
            if label and label not in exclude:
                counts[label] += 2
        elif edge.target == node_id:
            label = assignments.get(edge.source)
            if label and label not in exclude:
                counts[label] += 1
    return counts.most_common(1)[0][0] if counts else ""


def classify_capability_group(node: Node) -> str:
    if node.role == "test":
        return TEST_GROUP_LABEL

    searchable = capability_search_text(node)
    tokens = set(TOKEN_RE.findall(searchable))
    stem = PurePosixPath(node.id).stem.lower()

    best_label = ""
    best_score = 0
    for profile in CAPABILITY_PROFILES:
        score = 0
        if node.role and node.role in profile.roles:
            score += 4
        if stem in profile.keywords:
            score += 5
        for keyword in profile.keywords:
            if keyword in tokens:
                score += 3
            elif keyword in searchable:
                score += 1
        if score > best_score:
            best_score = score
            best_label = profile.label

    return best_label if best_score >= 3 else ""


def capability_search_text(node: Node) -> str:
    return " ".join(
        [
            node.id.replace("/", " "),
            node.label,
            node.short_title,
            node.description,
            " ".join(symbol.name for symbol in node.symbols[:16]),
        ]
    ).lower()


def is_generated_group_label(label: str) -> bool:
    return label in GENERATED_GROUP_LABELS


def merge_overflow_clusters(cluster_map: dict[str, list[str]], max_groups: int) -> dict[str, list[str]]:
    entries = [(key, ids) for key, ids in cluster_map.items() if ids]
    entries.sort(key=lambda item: len(item[1]), reverse=True)
    if len(entries) <= max_groups:
        return dict(entries)
    kept = entries[: max_groups - 1]
    other_ids = [node_id for _, ids in entries[max_groups - 1 :] for node_id in ids]
    return dict([*kept, ("(other)", other_ids)])


def compress_cluster_key(dir_name: str, depth: int) -> str:
    if dir_name in {"(root)", "(other)"}:
        return dir_name
    parts = [part for part in dir_name.split("/") if part]
    return "/".join(parts[: min(depth, len(parts))])


def merge_directory_clusters(clusters: dict[str, list[str]], depth: int) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = defaultdict(list)
    for dir_name, ids in clusters.items():
        merged[compress_cluster_key(dir_name, depth)].extend(ids)
    return merge_overflow_clusters(dict(merged), 10)


def cluster_stats(cluster_map: dict[str, list[str]], total_nodes: int) -> dict[str, float]:
    groups = [ids for ids in cluster_map.values() if ids]
    if not groups:
        return {"count": 0, "meaningful": 0, "max_share": 1.0}
    return {
        "count": float(len(groups)),
        "meaningful": float(sum(1 for ids in groups if len(ids) >= 2)),
        "max_share": max(len(ids) for ids in groups) / max(total_nodes, 1),
    }


def is_useful_cluster_map(cluster_map: dict[str, list[str]], total_nodes: int) -> bool:
    stats = cluster_stats(cluster_map, total_nodes)
    return (
        stats["count"] >= 2
        and stats["count"] <= 10
        and stats["meaningful"] >= 2
        and stats["max_share"] <= 0.78
    )


def fallback_cluster_map(graph: Graph) -> dict[str, list[str]]:
    clusters = graph.cluster_by_role()
    if len(clusters) >= 2:
        return merge_overflow_clusters(clusters, 8)
    return {"Codebase": [node.id for node in graph.nodes]}


def select_group_source(graph: Graph) -> tuple[str, dict[str, list[str]]]:
    group_clusters = graph.cluster_by_group()
    if len(group_clusters) >= 2:
        return "group", group_clusters

    directory_clusters = graph.cluster_by_directory()
    dir_depths = sorted(
        {
            len([part for part in key.split("/") if part])
            for key in directory_clusters
            if key not in {"(root)", "(other)"}
        },
        reverse=True,
    )
    for depth in dir_depths:
        candidate = merge_directory_clusters(directory_clusters, depth)
        if is_useful_cluster_map(candidate, len(graph.nodes)):
            return "directory", candidate

    candidate = merge_overflow_clusters(directory_clusters, 10)
    if is_useful_cluster_map(candidate, len(graph.nodes)):
        return "directory", candidate

    role_clusters = fallback_cluster_map(graph)
    return "role", role_clusters


def dominant_role(nodes: list[Node]) -> str:
    counts = Counter(node.role or "other" for node in nodes)
    if not counts:
        return "other"
    return counts.most_common(1)[0][0]


def humanize_label(value: str) -> str:
    return re.sub(r"\b\w", lambda match: match.group(0).upper(), value.replace("_", " ").replace("-", " "))


def group_display_label(source_kind: str, group_key: str, child_nodes: list[Node]) -> str:
    if source_kind == "group":
        return group_key
    if source_kind == "role":
        return "Miscellaneous" if group_key == "Other" else group_key
    if group_key == "(root)":
        return "Root Files"
    if group_key == "(other)":
        return "Miscellaneous"

    parts = [part for part in group_key.split("/") if part]
    lowered = [part.lower() for part in parts]
    if any(part in TEST_SEGMENTS for part in lowered):
        return "Tests"

    chosen = parts[-1] if parts else group_key
    for index in range(len(parts) - 1, -1, -1):
        if lowered[index] not in GENERIC_DIR_SEGMENTS:
            chosen = parts[index]
            break

    if chosen.lower() in TEST_SEGMENTS:
        return "Tests"
    if chosen.lower() == "src":
        return "Source Files"
    if chosen.lower() == "app":
        return "App Files"
    return humanize_label(chosen)


def first_sentence(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    match = re.match(r".+?[.!?](?:\s|$)", cleaned)
    return match.group(0).strip() if match else cleaned


def display_node_name(node: Node) -> str:
    if node.short_title:
        return node.short_title
    return re.sub(r"\.(py|js|jsx|ts|tsx|go|rs|java|kt|kts|c|cc|cpp|h|hpp)$", "", node.label)


def node_score(node: Node, pagerank: dict[str, float]) -> float:
    return (pagerank.get(node.id, 0.0) * 100.0) + (node.size / 1024.0) + len(node.symbols)


def summarize_group(
    graph: Graph,
    source_kind: str,
    group_key: str,
    label: str,
    child_nodes: list[Node],
    pagerank: dict[str, float],
) -> str:
    if source_kind == "group" and graph.metadata.groups.get(group_key):
        return graph.metadata.groups[group_key]

    ranked = sorted(child_nodes, key=lambda node: node_score(node, pagerank), reverse=True)
    snippets = [first_sentence(node.description) for node in ranked if first_sentence(node.description)]
    snippets = snippets[:2]
    if label == "Tests":
        if snippets:
            return " ".join(snippets)
        titles = [display_node_name(node) for node in ranked[:3]]
        return f"Covers {', '.join(titles)}." if titles else "Exercises key behaviors in this codebase."
    if snippets:
        return " ".join(snippets)
    titles = [display_node_name(node) for node in ranked[:3]]
    return f"Combines {', '.join(titles)}." if titles else ""


_ROLE_KIND: dict[str, str] = {
    "test": "test",
    "data_model": "data",
    "config": "data",
    "entry_point": "entry",
    "api_route": "process",
    "utility": "analysis",
}

_DECISION_LABEL_HINTS = ("decision", "router", "validator", "policy", "guard", "rule")


def infer_node_kind(node: Node) -> str:
    """Return the semantic kind for a file.

    Role wins over keyword search — a file whose role is explicitly set by the
    analyzer should not be reclassified by a keyword match in its description.
    Only files without a role fall back to keyword inference.
    """
    role = node.role or ""
    if role in _ROLE_KIND:
        return _ROLE_KIND[role]

    searchable = " ".join(
        [
            node.short_title,
            node.description,
            " ".join(symbol.name for symbol in node.symbols[:12]),
        ]
    ).lower()
    for keyword, (kind, _) in FLOW_KEYWORDS.items():
        if keyword in searchable:
            return kind
    return "process"


def infer_group_kind(child_nodes: list[Node], role: str) -> str:
    """Return the semantic kind for a group.

    Uses role signals from children before falling back to the modal file kind,
    so a "Data Models" group made of ``data_model`` files reliably comes out as
    ``data`` (parallelogram) instead of getting overwritten by keyword matches.
    """
    if role == "test":
        return "test"
    if not child_nodes:
        return "process"

    # Label hint (checked first so decision-flavored groups surface as diamonds
    # even when the underlying files all share a generic role like "utility").
    # Only scan short_title — descriptions leak generic tokens like "rule" or
    # "policy" in unrelated contexts and caused false positives in practice.
    title_source = " ".join((node.short_title or "") for node in child_nodes).lower()
    if any(hint in title_source for hint in _DECISION_LABEL_HINTS):
        return "decision"

    # Strong role-based signal: if ≥60% of children share a role whose mapping
    # is a distinctive shape, use that. This is what makes "Data Models" look
    # like a parallelogram instead of a generic rectangle.
    role_counts: Counter[str] = Counter(node.role or "" for node in child_nodes)
    total = len(child_nodes)
    for child_role, count in role_counts.most_common():
        if not child_role or child_role not in _ROLE_KIND:
            continue
        if count / total >= 0.6:
            return _ROLE_KIND[child_role]

    counts = Counter(infer_node_kind(node) for node in child_nodes)
    if not counts:
        return "process"
    max_count = max(counts.values())
    for preferred in KIND_ORDER:
        if counts[preferred] == max_count:
            return preferred
    return counts.most_common(1)[0][0]


def infer_edge_label(source: Node, target: Node) -> tuple[str, str]:
    src_kind = infer_node_kind(source)
    tgt_kind = infer_node_kind(target)
    searchable = " ".join(
        [target.short_title, target.description, " ".join(symbol.name for symbol in target.symbols[:10])]
    ).lower()

    if src_kind == "test":
        return "tests", "tests"
    if tgt_kind == "data":
        if any(token in searchable for token in ("save", "store", "write", "persist", "cache")):
            return "persists", "persists"
        return "reads", "reads"
    if tgt_kind == "decision":
        return "validates", "validates"
    if tgt_kind == "analysis":
        return "analyzes", "analyzes"
    if tgt_kind == "entry":
        return "starts", "starts"
    for keyword, (_, label) in FLOW_KEYWORDS.items():
        if keyword in searchable and label != "depends on":
            return label.replace(" ", "_"), label
    return "depends_on", "depends on"


def build_group_detail(graph: Graph, child_nodes: list[Node], label: str) -> dict | None:
    if not child_nodes:
        return None

    pagerank = graph.pagerank() if graph.nodes else {}
    ranked = sorted(child_nodes, key=lambda node: node_score(node, pagerank), reverse=True)
    featured = ranked[:MAX_DETAIL_MEMBERS]
    featured_ids = {node.id for node in featured}

    detail_nodes = []
    for index, node in enumerate(featured):
        kind = infer_node_kind(node)
        legacy_type = {
            "entry": "start",
            "decision": "decision",
            "test": "test",
            "analysis": "analysis",
            "data": "data",
        }.get(kind, "step")
        detail_nodes.append(
            {
                "id": node.id,
                "label": display_node_name(node),
                "type": legacy_type,
                "shape": KIND_TO_SHAPE[kind],
                "description": first_sentence(node.description)
                or f"{display_node_name(node)} participates in {label.lower()}.",
                "rank": index,
            }
        )

    detail_edges = []
    for edge in graph.edges:
        if edge.source not in featured_ids or edge.target not in featured_ids:
            continue
        source = graph.get_node(edge.source)
        target = graph.get_node(edge.target)
        if not source or not target:
            continue
        _, label_text = infer_edge_label(source, target)
        detail_edges.append(
            {
                "from": edge.source,
                "to": edge.target,
                "label": label_text,
            }
        )

    if not detail_edges and len(detail_nodes) > 1:
        ordered = [node["id"] for node in detail_nodes]
        detail_edges = [
            {"from": ordered[index], "to": ordered[index + 1], "label": "flows to"}
            for index in range(len(ordered) - 1)
        ]

    if not detail_edges:
        return None
    return {"nodes": detail_nodes, "edges": detail_edges}


def build_group_edges(
    graph: Graph,
    member_to_group: dict[str, str],
    diagram_nodes: list[SemanticDiagramNode],
    node_lookup: dict[str, Node],
) -> list[SemanticDiagramEdge]:
    edge_weights: dict[tuple[str, str], int] = defaultdict(int)
    edge_labels: dict[tuple[str, str], list[str]] = defaultdict(list)
    edge_kinds: dict[tuple[str, str], list[str]] = defaultdict(list)

    for edge in graph.edges:
        source_group = member_to_group.get(edge.source)
        target_group = member_to_group.get(edge.target)
        if not source_group or not target_group or source_group == target_group:
            continue
        source_node = node_lookup.get(edge.source)
        target_node = node_lookup.get(edge.target)
        if not source_node or not target_node:
            continue
        kind, label = infer_edge_label(source_node, target_node)
        pair = (source_group, target_group)
        edge_weights[pair] += 1
        edge_kinds[pair].append(kind)
        edge_labels[pair].append(label)

    by_id = {node.id: node for node in diagram_nodes}
    semantic_edges: list[SemanticDiagramEdge] = []
    for (source, target), weight in edge_weights.items():
        kinds = edge_kinds[(source, target)]
        labels = edge_labels[(source, target)]
        kind = Counter(kinds).most_common(1)[0][0]
        non_generic = [label for label in labels if label != "depends on"]
        label = Counter(non_generic or labels).most_common(1)[0][0]
        if source in by_id and by_id[source].kind == "test":
            kind = "tests"
            label = "tests"
        semantic_edges.append(
            SemanticDiagramEdge(
                source=source,
                target=target,
                kind=kind,
                label=label,
                weight=weight,
            )
        )
    return semantic_edges


def apply_topological_levels(nodes: list[SemanticDiagramNode], edges: list[SemanticDiagramEdge]) -> None:
    indegree: dict[str, int] = {node.id: 0 for node in nodes}
    adjacency: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.source not in adjacency or edge.target not in indegree:
            continue
        adjacency[edge.source].append(edge.target)
        indegree[edge.target] += 1

    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    levels: dict[str, int] = {node_id: 0 for node_id in queue}
    for index, node_id in enumerate(queue):
        for target in adjacency[node_id]:
            next_level = levels[node_id] + 1
            if target not in levels or next_level > levels[target]:
                levels[target] = next_level
                queue.append(target)

    for node in nodes:
        node.level = levels.get(node.id, 0)
        if node.kind == "test" and nodes:
            node.level = max(levels.values(), default=0) + 1


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "group"
