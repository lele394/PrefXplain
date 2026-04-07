"""Static analysis: extract file nodes and IMPORTS edges from a codebase.

Python: uses ast module (built-in, zero deps, exact).
JS/TS:  uses regex for import/require statements (fast, good-enough for v0.1).

No tree-sitter dependency at v0.1. Adds multi-language support in v0.2.
"""

from __future__ import annotations

import ast
import re
import os
from datetime import datetime, timezone
from pathlib import Path

from .graph import Edge, Graph, GraphMetadata, Node, Symbol


# ---------------------------------------------------------------------------
# File extension sets
# ---------------------------------------------------------------------------

PYTHON_EXTS = {".py"}
JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".nuxt", "coverage", ".coverage", "htmlcov",
    "site-packages", "eggs", ".eggs",
}

# JS/TS import patterns
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:.*?\s+from\s+)?['"]([^'"]+)['"]"""
    r"""|require\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def _language(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in PYTHON_EXTS:
        return "python"
    if ext in {".ts", ".tsx"}:
        return "typescript"
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:
        return "javascript"
    return "other"


# ---------------------------------------------------------------------------
# Python analysis
# ---------------------------------------------------------------------------

def _analyze_python(path: Path, root: Path) -> tuple[list[Symbol], list[str]]:
    """Return (symbols, raw_import_strings) for a Python file."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return [], []

    symbols: list[Symbol] = []
    raw_imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Only top-level and class-level functions
            symbols.append(Symbol(name=node.name, kind="function", line=node.lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(Symbol(name=node.name, kind="class", line=node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                raw_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                raw_imports.append(node.module)

    return symbols, raw_imports


def _resolve_python_import(raw: str, source_file: Path, root: Path) -> str | None:
    """Try to resolve a Python import string to a file path relative to root.

    Returns the relative path string if found, None if it's a third-party import.
    """
    # Convert "a.b.c" → "a/b/c.py" or "a/b/c/__init__.py"
    parts = raw.split(".")
    candidate_file = root / Path(*parts).with_suffix(".py")
    candidate_pkg = root / Path(*parts) / "__init__.py"

    if candidate_file.exists():
        return str(candidate_file.relative_to(root))
    if candidate_pkg.exists():
        return str(candidate_pkg.relative_to(root))

    # Try relative: if source is src/a/b.py and import is "c" → src/a/c.py
    rel_dir = source_file.parent
    rel_candidate = rel_dir / Path(*parts).with_suffix(".py")
    if rel_candidate.exists():
        try:
            return str(rel_candidate.relative_to(root))
        except ValueError:
            return None

    return None  # third-party or stdlib


# ---------------------------------------------------------------------------
# JS/TS analysis
# ---------------------------------------------------------------------------

def _analyze_js(path: Path, root: Path) -> tuple[list[Symbol], list[str]]:
    """Return (symbols, raw_import_strings) for a JS/TS file."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], []

    raw_imports: list[str] = []
    for m in _JS_IMPORT_RE.finditer(source):
        target = m.group(1) or m.group(2)
        if target:
            raw_imports.append(target)

    # Extract top-level export/function names as symbols (simple regex)
    fn_re = re.compile(
        r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.MULTILINE
    )
    class_re = re.compile(r"^(?:export\s+)?class\s+(\w+)", re.MULTILINE)
    const_re = re.compile(
        r"^export\s+(?:const|let|var)\s+(\w+)", re.MULTILINE
    )

    symbols: list[Symbol] = []
    for m in fn_re.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="function", line=source[:m.start()].count("\n") + 1))
    for m in class_re.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="class", line=source[:m.start()].count("\n") + 1))
    for m in const_re.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="variable", line=source[:m.start()].count("\n") + 1))

    return symbols, raw_imports


def _load_ts_aliases(root: Path) -> dict[str, Path]:
    """Read tsconfig.json paths and return alias→absolute_dir mapping.

    Handles the common `@/*` → `./src/*` pattern.
    """
    import json

    aliases: dict[str, Path] = {}
    for tsconfig_name in ("tsconfig.json", "jsconfig.json"):
        tsconfig = root / tsconfig_name
        if not tsconfig.exists():
            # Try one level down (e.g. root/web/tsconfig.json)
            for child in root.iterdir():
                candidate = child / tsconfig_name
                if candidate.exists():
                    tsconfig = candidate
                    break
            else:
                continue

        try:
            data = json.loads(tsconfig.read_text())
            paths = data.get("compilerOptions", {}).get("paths", {})
            tsconfig_dir = tsconfig.parent
            for alias, targets in paths.items():
                # `@/*` → strip `/*` suffix → `@`
                alias_prefix = alias.rstrip("/*").rstrip("/")
                if targets:
                    # `./src/*` → strip `/*` suffix → resolve to absolute
                    target_dir_str = targets[0].rstrip("/*").rstrip("/")
                    target_dir = (tsconfig_dir / target_dir_str).resolve()
                    aliases[alias_prefix] = target_dir
        except Exception:
            pass

    return aliases


def _resolve_js_import(
    raw: str,
    source_file: Path,
    root: Path,
    aliases: dict[str, Path] | None = None,
) -> str | None:
    """Try to resolve a JS/TS import path to a file relative to root.

    Handles relative imports (./foo) and path aliases (@/foo → src/foo).
    Package imports return None.
    """
    resolved_aliases = aliases or {}

    # Try path aliases first (e.g. @/components/Button)
    for alias_prefix, target_dir in resolved_aliases.items():
        if raw == alias_prefix or raw.startswith(alias_prefix + "/"):
            suffix = raw[len(alias_prefix):].lstrip("/")
            base = target_dir / suffix if suffix else target_dir
            result = _try_js_candidates(base, root)
            if result:
                return result

    if not raw.startswith("."):
        return None  # npm package, skip

    base = source_file.parent / raw

    return _try_js_candidates(base, root)


def _try_js_candidates(base: Path, root: Path) -> str | None:
    """Try a base path with various JS/TS extensions."""
    candidates = [
        base,
        base.with_suffix(".ts"),
        base.with_suffix(".tsx"),
        base.with_suffix(".js"),
        base.with_suffix(".jsx"),
        base / "index.ts",
        base / "index.tsx",
        base / "index.js",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            try:
                return str(candidate.resolve().relative_to(root.resolve()))
            except ValueError:
                return None

    return None


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

def _collect_files(root: Path, max_files: int) -> list[Path]:
    """Walk root and collect source files, skipping known junk dirs."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in PYTHON_EXTS | JS_EXTS:
                files.append(fpath)
            if len(files) >= max_files:
                return files
    return files


def analyze(root_path: Path, max_files: int = 500) -> Graph:
    """Parse a project directory and return a Graph with nodes and IMPORTS edges.

    Args:
        root_path: Project root directory.
        max_files: Maximum number of files to analyze (ranked by discovery order).

    Returns:
        A Graph with nodes (one per file) and edges (IMPORTS relationships).
        Node descriptions are empty — call describer.describe() to fill them.
    """
    root = root_path.resolve()
    files = _collect_files(root, max_files)

    # Load TypeScript/JS path aliases once for the whole project
    ts_aliases = _load_ts_aliases(root)

    graph = Graph.empty(root)
    node_ids: set[str] = set()

    # Pass 1: create all nodes
    for fpath in files:
        rel = str(fpath.relative_to(root))
        lang = _language(fpath)

        if lang == "python":
            symbols, _ = _analyze_python(fpath, root)
        elif lang in ("javascript", "typescript"):
            symbols, _ = _analyze_js(fpath, root)
        else:
            symbols = []

        node = Node(
            id=rel,
            label=fpath.name,
            description="",
            symbols=symbols,
            language=lang,
            size=fpath.stat().st_size,
        )
        graph.nodes.append(node)
        node_ids.add(rel)

    # Pass 2: create edges
    seen_edges: set[tuple[str, str]] = set()

    for fpath in files:
        rel = str(fpath.relative_to(root))
        lang = _language(fpath)

        if lang == "python":
            _, raw_imports = _analyze_python(fpath, root)
            for raw in raw_imports:
                target = _resolve_python_import(raw, fpath, root)
                if target and target in node_ids and (rel, target) not in seen_edges:
                    graph.edges.append(Edge(source=rel, target=target, type="imports"))
                    seen_edges.add((rel, target))

        elif lang in ("javascript", "typescript"):
            _, raw_imports = _analyze_js(fpath, root)
            for raw in raw_imports:
                target = _resolve_js_import(raw, fpath, root, aliases=ts_aliases)
                if target and target in node_ids and (rel, target) not in seen_edges:
                    graph.edges.append(Edge(source=rel, target=target, type="imports"))
                    seen_edges.add((rel, target))

    # Update metadata
    languages = sorted(set(n.language for n in graph.nodes if n.language))
    graph.metadata.total_files = len(graph.nodes)
    graph.metadata.languages = languages
    graph.metadata.generated_at = datetime.now(timezone.utc).isoformat()

    return graph
