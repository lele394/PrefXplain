"""Static analysis: extract file nodes and IMPORTS edges from a codebase.

Python: uses ast module (built-in, zero deps, exact).
JS/TS:  uses regex for import/require statements (fast, good-enough for v0.1).

No tree-sitter dependency at v0.1. Adds multi-language support in v0.2.
"""

from __future__ import annotations

import ast
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .graph import Edge, Graph, Node, Symbol

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


def _read_preview(path: Path, max_lines: int = 50, max_bytes: int = 3000) -> str:
    """Read the first N lines of a file for the sidebar code preview.

    Capped by both line count and byte count so we don't blow up the JSON
    payload on large files. Returns an empty string on read errors.
    """
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fp:
            lines: list[str] = []
            total_bytes = 0
            for i, line in enumerate(fp):
                if i >= max_lines:
                    break
                # Truncate over-long lines (e.g. minified JS)
                if len(line) > 200:
                    line = line[:200] + "…\n"
                lines.append(line)
                total_bytes += len(line)
                if total_bytes >= max_bytes:
                    break
            return "".join(lines).rstrip()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Python analysis
# ---------------------------------------------------------------------------

def _analyze_python(
    path: Path, root: Path
) -> tuple[list[Symbol], list[tuple[str, int]]]:
    """Return (symbols, imports) for a Python file.

    Each import is a (module, level) tuple. `level` is 0 for absolute imports
    and N for `from ..foo import x` (level N). For `from . import x`, module
    is an empty string and level >= 1.

    Symbol extraction only captures top-level and class-level definitions,
    not nested local functions.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError):
        return [], []

    symbols: list[Symbol] = []
    imports: list[tuple[str, int]] = []

    # Walk the module body directly so we only see top-level statements
    # and class-level methods, not nested functions.
    def _scan(body: list[ast.stmt], in_class: bool = False) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(
                    Symbol(name=node.name, kind="function", line=node.lineno)
                )
                # Do NOT recurse into function bodies — local functions are noise.
            elif isinstance(node, ast.ClassDef):
                symbols.append(
                    Symbol(name=node.name, kind="class", line=node.lineno)
                )
                _scan(node.body, in_class=True)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, 0))
            elif isinstance(node, ast.ImportFrom):
                # node.module is None for `from . import x`
                # node.level is 0 for absolute, N for relative dots
                module = node.module or ""
                imports.append((module, node.level))
            elif isinstance(node, ast.If):
                # Imports can be conditionally declared at top level
                _scan(node.body, in_class=in_class)
                _scan(node.orelse, in_class=in_class)
            elif isinstance(node, ast.Try):
                _scan(node.body, in_class=in_class)
                for handler in node.handlers:
                    _scan(handler.body, in_class=in_class)
                _scan(node.orelse, in_class=in_class)
                _scan(node.finalbody, in_class=in_class)

    _scan(tree.body)
    return symbols, imports


def _resolve_python_import(
    raw: str | tuple[str, int], source_file: Path, root: Path
) -> str | None:
    """Resolve a Python import to a file path relative to root.

    Accepts either a legacy string (absolute import) or a (module, level) tuple
    from `_analyze_python`. Returns the relative path string, or None if the
    import is third-party/stdlib.

    Relative imports resolve against the source file's parent directory,
    walking up `level` packages. `from . import x` (module="", level=1) means
    "import `x` from the current package" — we try `<parent>/x.py` first,
    then `<parent>/x/__init__.py`.
    """
    # Back-compat: allow plain strings (treated as absolute)
    if isinstance(raw, tuple):
        module, level = raw
    else:
        module, level = raw, 0

    if level > 0:
        # Relative import: walk up `level` directories from source file
        base = source_file.parent
        for _ in range(level - 1):
            base = base.parent

        if not module:
            # `from . import x` — we don't know which `x` without parsing names.
            # Return the package dir's __init__.py as the edge target.
            init = base / "__init__.py"
            if init.exists():
                try:
                    return str(init.relative_to(root))
                except ValueError:
                    return None
            return None

        parts = module.split(".")
        candidate_file = base / Path(*parts).with_suffix(".py")
        candidate_pkg = base / Path(*parts) / "__init__.py"
        for candidate in (candidate_file, candidate_pkg):
            if candidate.exists():
                try:
                    return str(candidate.resolve().relative_to(root.resolve()))
                except ValueError:
                    return None
        return None

    # Absolute import
    if not module:
        return None
    parts = module.split(".")
    candidate_file = root / Path(*parts).with_suffix(".py")
    candidate_pkg = root / Path(*parts) / "__init__.py"

    if candidate_file.exists():
        return str(candidate_file.relative_to(root))
    if candidate_pkg.exists():
        return str(candidate_pkg.relative_to(root))

    # Also try common src layouts: src/<pkg>/...
    for src_root_name in ("src", "lib"):
        src_root = root / src_root_name
        if not src_root.exists():
            continue
        candidate_file = src_root / Path(*parts).with_suffix(".py")
        candidate_pkg = src_root / Path(*parts) / "__init__.py"
        if candidate_file.exists():
            return str(candidate_file.relative_to(root))
        if candidate_pkg.exists():
            return str(candidate_pkg.relative_to(root))

    # Fallback: try relative to source file's directory
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


_JSONC_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _strip_jsonc(text: str) -> str:
    """Strip JSONC comments and trailing commas so json.loads accepts tsconfig files.

    Handles // line comments, /* */ block comments, and trailing commas.
    Carefully avoids stripping comment-like sequences inside string literals.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        # Line comment
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = j if j != -1 else n
            continue
        # Block comment
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = (j + 2) if j != -1 else n
            continue
        out.append(c)
        i += 1

    result = "".join(out)
    result = _JSONC_TRAILING_COMMA_RE.sub(r"\1", result)
    return result


# Bounded list of likely tsconfig locations. Avoids iterating every top-level
# directory in the repo (which could be thousands in monorepos).
_TSCONFIG_SEARCH_DIRS = (
    "",
    "web",
    "src",
    "app",
    "client",
    "frontend",
    "www",
    "apps",
)


def _find_tsconfig_files(root: Path) -> list[Path]:
    """Find tsconfig.json / jsconfig.json files in known locations.

    Bounded search — only looks in common project layouts, not every directory.
    Also handles monorepo `packages/*/tsconfig.json` and `apps/*/tsconfig.json`.
    """
    found: list[Path] = []
    for sub in _TSCONFIG_SEARCH_DIRS:
        for name in ("tsconfig.json", "jsconfig.json"):
            candidate = (root / sub / name) if sub else (root / name)
            if candidate.exists() and candidate.is_file():
                found.append(candidate)

    # Monorepo layouts: scan one level under packages/ and apps/
    for mono_dir in ("packages", "apps"):
        mono_root = root / mono_dir
        if mono_root.is_dir():
            try:
                for pkg in sorted(mono_root.iterdir()):
                    if not pkg.is_dir() or pkg.name.startswith("."):
                        continue
                    for name in ("tsconfig.json", "jsconfig.json"):
                        candidate = pkg / name
                        if candidate.exists() and candidate.is_file():
                            found.append(candidate)
            except OSError:
                pass

    return found


def _load_ts_aliases(root: Path) -> dict[str, Path]:
    """Read tsconfig.json paths and return alias→absolute_dir mapping.

    Handles:
    - JSONC comments (// and /* */)
    - Trailing commas
    - baseUrl resolution
    - Multiple tsconfigs (monorepos)
    """
    import json

    aliases: dict[str, Path] = {}
    for tsconfig in _find_tsconfig_files(root):
        try:
            raw = tsconfig.read_text(encoding="utf-8", errors="ignore")
            data = json.loads(_strip_jsonc(raw))
        except (json.JSONDecodeError, OSError, ValueError):
            continue

        compiler_options = data.get("compilerOptions") or {}
        paths = compiler_options.get("paths") or {}
        base_url = compiler_options.get("baseUrl")

        tsconfig_dir = tsconfig.parent
        base = (tsconfig_dir / base_url).resolve() if base_url else tsconfig_dir

        for alias, targets in paths.items():
            if not isinstance(targets, list) or not targets:
                continue
            target_str = targets[0]
            if not isinstance(target_str, str):
                continue
            alias_prefix = alias.rstrip("/*").rstrip("/")
            target_dir_str = target_str.rstrip("/*").rstrip("/")
            target_dir = (base / target_dir_str).resolve()
            aliases[alias_prefix] = target_dir

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
    """Try a base path with various JS/TS extensions and common index files."""
    candidates = [
        base,
        base.with_suffix(".ts"),
        base.with_suffix(".tsx"),
        base.with_suffix(".js"),
        base.with_suffix(".jsx"),
        base.with_suffix(".mjs"),
        base.with_suffix(".cjs"),
        base / "index.ts",
        base / "index.tsx",
        base / "index.js",
        base / "index.jsx",
        base / "index.mjs",
        base / "index.cjs",
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
    """Walk root and collect source files, skipping known junk dirs and symlinks."""
    files: list[Path] = []
    seen_real: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune skip dirs and symlinked dirs in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS
            and not d.startswith(".")
            and not (Path(dirpath) / d).is_symlink()
        ]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.is_symlink():
                continue
            if fpath.suffix.lower() in PYTHON_EXTS | JS_EXTS:
                real = str(fpath.resolve())
                if real in seen_real:
                    continue
                seen_real.add(real)
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

    # Pass 1: create all nodes and cache analysis results.
    # For Python, raw_imports is list[tuple[module, level]]; for JS/TS it's list[str].
    file_analysis: dict[str, tuple[str, list]] = {}  # rel → (lang, raw_imports)

    for fpath in files:
        rel = str(fpath.relative_to(root))
        lang = _language(fpath)

        if lang == "python":
            symbols, raw_imports = _analyze_python(fpath, root)
        elif lang in ("javascript", "typescript"):
            symbols, raw_imports = _analyze_js(fpath, root)
        else:
            symbols, raw_imports = [], []

        try:
            size = fpath.stat().st_size
        except OSError:
            size = 0

        # Read first 50 lines for the sidebar code preview.
        # Capped at ~3KB per file to keep the JSON payload reasonable.
        preview = _read_preview(fpath, max_lines=50, max_bytes=3000)

        node = Node(
            id=rel,
            label=fpath.name,
            description="",
            symbols=symbols,
            language=lang,
            size=size,
            preview=preview,
        )
        graph.nodes.append(node)
        node_ids.add(rel)
        file_analysis[rel] = (lang, raw_imports)

    # Pass 2: create edges (using cached analysis, no re-parse)
    seen_edges: set[tuple[str, str]] = set()

    for fpath in files:
        rel = str(fpath.relative_to(root))
        lang, raw_imports = file_analysis[rel]

        for raw in raw_imports:
            if lang == "python":
                target = _resolve_python_import(raw, fpath, root)
            elif lang in ("javascript", "typescript"):
                target = _resolve_js_import(raw, fpath, root, aliases=ts_aliases)
            else:
                target = None

            if target and target in node_ids and (rel, target) not in seen_edges:
                graph.edges.append(Edge(source=rel, target=target, type="imports"))
                seen_edges.add((rel, target))

    # ── Prune trivial nodes that add noise to the diagram ──────────────
    # Compute in/out degree for pruning decisions
    in_deg: dict[str, int] = {n.id: 0 for n in graph.nodes}
    out_deg: dict[str, int] = {n.id: 0 for n in graph.nodes}
    for e in graph.edges:
        in_deg[e.target] = in_deg.get(e.target, 0) + 1
        out_deg[e.source] = out_deg.get(e.source, 0) + 1

    prune_ids: set[str] = set()
    for n in graph.nodes:
        # Trivial __init__.py: tiny, no real code (no classes/functions), low connectivity
        if n.label == "__init__.py" and n.size < 500:
            has_real_code = any(
                s.kind in ("function", "class") for s in n.symbols
            )
            if not has_real_code and in_deg.get(n.id, 0) + out_deg.get(n.id, 0) <= 1:
                prune_ids.add(n.id)

    if prune_ids:
        graph.nodes = [n for n in graph.nodes if n.id not in prune_ids]
        graph.edges = [
            e for e in graph.edges
            if e.source not in prune_ids and e.target not in prune_ids
        ]

    # Update metadata
    languages = sorted(set(n.language for n in graph.nodes if n.language))
    graph.metadata.total_files = len(graph.nodes)
    graph.metadata.languages = languages
    graph.metadata.generated_at = datetime.now(timezone.utc).isoformat()

    return graph
