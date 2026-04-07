"""Graph data structures for PrefXplain.

Nodes are files. Edges are import/dependency relationships.
Schema is PrefOptimize-compatible: nodes.id = file_path, edges.type = event_type.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


@dataclass
class Symbol:
    name: str
    kind: Literal["function", "class", "variable", "import"]
    line: int

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "line": self.line}

    @classmethod
    def from_dict(cls, d: dict) -> "Symbol":
        return cls(name=d["name"], kind=d["kind"], line=d["line"])


@dataclass
class Node:
    id: str          # relative file path from repo root, e.g. "src/auth/token.py"
    label: str       # filename only, e.g. "token.py"
    description: str = ""
    symbols: list[Symbol] = field(default_factory=list)
    language: str = ""
    size: int = 0    # file size in bytes

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "symbols": [s.to_dict() for s in self.symbols],
            "language": self.language,
            "size": self.size,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        return cls(
            id=d["id"],
            label=d["label"],
            description=d.get("description", ""),
            symbols=[Symbol.from_dict(s) for s in d.get("symbols", [])],
            language=d.get("language", ""),
            size=d.get("size", 0),
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
    def from_dict(cls, d: dict) -> "Edge":
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

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "generated_at": self.generated_at,
            "total_files": self.total_files,
            "languages": self.languages,
            "codemap_version": self.codemap_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GraphMetadata":
        return cls(
            repo=d["repo"],
            generated_at=d["generated_at"],
            total_files=d["total_files"],
            languages=d["languages"],
            codemap_version=d.get("codemap_version", "0.1.0"),
        )


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    metadata: GraphMetadata | None = None

    def get_node(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def neighbors(self, node_id: str) -> list[str]:
        """Return all node ids directly connected to node_id."""
        result = set()
        for e in self.edges:
            if e.source == node_id:
                result.add(e.target)
            elif e.target == node_id:
                result.add(e.source)
        return list(result)

    def outdegree(self, node_id: str) -> int:
        """Number of files this node imports."""
        return sum(1 for e in self.edges if e.source == node_id)

    def indegree(self, node_id: str) -> int:
        """Number of files that import this node."""
        return sum(1 for e in self.edges if e.target == node_id)

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata.to_dict() if self.metadata else {},
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "Graph":
        data = json.loads(path.read_text())
        graph = cls(
            nodes=[Node.from_dict(n) for n in data.get("nodes", [])],
            edges=[Edge.from_dict(e) for e in data.get("edges", [])],
        )
        if data.get("metadata"):
            graph.metadata = GraphMetadata.from_dict(data["metadata"])
        return graph

    @classmethod
    def empty(cls, root_path: Path) -> "Graph":
        return cls(
            metadata=GraphMetadata(
                repo=root_path.name,
                generated_at=datetime.now(timezone.utc).isoformat(),
                total_files=0,
                languages=[],
            )
        )
