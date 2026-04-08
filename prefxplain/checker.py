"""CI rule enforcement engine for PrefXplain.

Loads rules from .prefxplain.yml and checks the dependency graph for violations.
Exit code 1 if any violations found — designed for CI pipelines.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .graph import Graph


@dataclass
class Rule:
    name: str
    kind: str                      # "no-circular-deps", "no-cross-boundary", "max-imports"
    from_pattern: str | None = None
    to_pattern: str | None = None
    max_value: int | None = None   # for "max-imports" rule
    severity: str = "error"        # "error" or "warning"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Rule:
        return cls(
            name=d.get("name", d.get("kind", "unnamed")),
            kind=d["kind"] if "kind" in d else d["name"],
            from_pattern=d.get("from"),
            to_pattern=d.get("to"),
            max_value=d.get("max"),
            severity=d.get("severity", "error"),
        )


@dataclass
class Violation:
    rule: str
    message: str
    files: list[str] = field(default_factory=list)
    severity: str = "error"

    def __str__(self) -> str:
        files_str = ", ".join(self.files[:5])
        if len(self.files) > 5:
            files_str += f" (+{len(self.files) - 5} more)"
        return f"[{self.severity.upper()}] {self.rule}: {self.message} [{files_str}]"


def load_rules(config_path: Path) -> list[Rule]:
    """Load rules from a YAML config file.

    Expected format:
        rules:
          - name: no-circular-deps
          - name: no-cross-boundary
            from: "api/**"
            to: "internal/**"
            severity: error
          - name: max-imports
            max: 10
    """
    try:
        import yaml
    except ImportError:
        # Fall back to a simple parser for basic YAML
        return _parse_simple_yaml(config_path)

    text = config_path.read_text()
    data = yaml.safe_load(text) or {}
    raw_rules = data.get("rules", [])
    return [Rule.from_dict(r) for r in raw_rules]


def _parse_simple_yaml(config_path: Path) -> list[Rule]:
    """Minimal YAML parser for rule configs — no PyYAML dependency required."""
    text = config_path.read_text()
    rules: list[Rule] = []
    current: dict[str, Any] = {}

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:") or stripped.startswith("- kind:"):
            if current:
                rules.append(Rule.from_dict(current))
            key = "name" if "name:" in stripped else "kind"
            current = {key: stripped.split(":", 1)[1].strip().strip('"').strip("'")}
        elif stripped.startswith("from:") and current:
            current["from"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.startswith("to:") and current:
            current["to"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.startswith("max:") and current:
            try:
                current["max"] = int(stripped.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif stripped.startswith("severity:") and current:
            current["severity"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")

    if current:
        rules.append(Rule.from_dict(current))

    return rules


def check(graph: Graph, rules: list[Rule]) -> list[Violation]:
    """Check graph against rules, returning a list of violations."""
    violations: list[Violation] = []

    for rule in rules:
        if rule.kind == "no-circular-deps":
            violations.extend(_check_no_circular_deps(graph, rule))
        elif rule.kind == "no-cross-boundary":
            violations.extend(_check_no_cross_boundary(graph, rule))
        elif rule.kind == "max-imports":
            violations.extend(_check_max_imports(graph, rule))

    return violations


def _check_no_circular_deps(graph: Graph, rule: Rule) -> list[Violation]:
    """Check for circular dependencies."""
    cycles = graph.find_cycles()

    if rule.from_pattern:
        cycles = [
            c for c in cycles
            if any(fnmatch.fnmatch(f, rule.from_pattern) for f in c)
        ]

    violations: list[Violation] = []
    for cycle in cycles:
        chain = " -> ".join(cycle) + " -> " + cycle[0]
        violations.append(Violation(
            rule=rule.name,
            message=f"Circular dependency: {chain}",
            files=cycle,
            severity=rule.severity,
        ))

    return violations


def _check_no_cross_boundary(graph: Graph, rule: Rule) -> list[Violation]:
    """Check that files matching 'from' pattern do not import files matching 'to' pattern."""
    if not rule.from_pattern or not rule.to_pattern:
        return []

    violations: list[Violation] = []
    for edge in graph.edges:
        if fnmatch.fnmatch(edge.source, rule.from_pattern) and fnmatch.fnmatch(edge.target, rule.to_pattern):
            violations.append(Violation(
                rule=rule.name,
                message=f"{edge.source} imports {edge.target} (crosses boundary)",
                files=[edge.source, edge.target],
                severity=rule.severity,
            ))

    return violations


def _check_max_imports(graph: Graph, rule: Rule) -> list[Violation]:
    """Check that no file imports more than max modules."""
    max_val = rule.max_value or 10
    violations: list[Violation] = []

    for node in graph.nodes:
        if rule.from_pattern and not fnmatch.fnmatch(node.id, rule.from_pattern):
            continue
        out = graph.outdegree(node.id)
        if out > max_val:
            violations.append(Violation(
                rule=rule.name,
                message=f"{node.id} imports {out} modules (max: {max_val})",
                files=[node.id],
                severity=rule.severity,
            ))

    return violations


def format_violations(violations: list[Violation]) -> str:
    """Format violations for terminal output."""
    if not violations:
        return "No violations found."

    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]

    lines: list[str] = []
    if errors:
        lines.append(f"\n{len(errors)} error(s):")
        for v in errors:
            lines.append(f"  {v}")
    if warnings:
        lines.append(f"\n{len(warnings)} warning(s):")
        for v in warnings:
            lines.append(f"  {v}")

    lines.append(f"\nTotal: {len(errors)} errors, {len(warnings)} warnings")
    return "\n".join(lines)
