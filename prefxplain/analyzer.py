"""Static analysis: extract file nodes and IMPORTS edges from a codebase.

Python:     uses ast module (built-in, zero deps, exact).
JS/TS:      uses regex for import/require statements.
C/C++:      uses regex for #include "..." (local headers only, not <system>).
Go:         uses regex for import "..." and import (...) blocks.
Rust:       uses regex for mod/use + pub fn/struct/enum/trait.
Java/Kotlin: uses regex for import statements.
"""

from __future__ import annotations

import ast
import fnmatch
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .graph import Edge, Graph, Node, Symbol

# ---------------------------------------------------------------------------
# File extension sets
# ---------------------------------------------------------------------------

PYTHON_EXTS = {".py"}
JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
C_CPP_EXTS = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"}
GO_EXTS = {".go"}
RUST_EXTS = {".rs"}
JAVA_EXTS = {".java"}
KOTLIN_EXTS = {".kt", ".kts"}

ALL_EXTS = PYTHON_EXTS | JS_EXTS | C_CPP_EXTS | GO_EXTS | RUST_EXTS | JAVA_EXTS | KOTLIN_EXTS

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".nuxt", "coverage", ".coverage", "htmlcov",
    "site-packages", "eggs", ".eggs",
    "out", "node_modules",
}

# Directories whose __init__.py should not anchor a package root (they're test
# namespaces, not import roots).  The directories themselves are still analyzed.
_PKG_ROOT_FILTER = {"tests", "test", "__tests__", "testing"}

# Dot-directories the walker keeps instead of blanket-skipping them.
# .github houses CI workflows, .vscode/.devcontainer house IDE/dev env config —
# high-signal non-code files users often want surfaced.
ALLOWED_DOTDIRS = {".github", ".vscode", ".devcontainer"}

# High-signal non-code files. They become graph nodes (no edges) so users see
# the project's build/deploy/config surface alongside the code. Policy is
# path/name-based — ".yml" alone is too broad (fixtures, data) so we anchor
# patterns under known parent dirs (e.g. .github/workflows/*.yml).
CONFIG_NODE_BASENAMES = {
    "Makefile", "makefile", "Dockerfile", "dockerfile",
    "pyproject.toml", "package.json",
    "go.mod", "Cargo.toml", "pom.xml",
    ".env.example",
}
# Patterns are matched with fnmatch against the POSIX-ified relative path when
# the pattern contains "/", otherwise against the basename.
CONFIG_NODE_GLOBS = (
    "tsconfig*.json",
    "requirements*.txt",
    "build.gradle*",
    "docker-compose*.yml", "docker-compose*.yaml",
    "compose*.yml", "compose*.yaml",
    ".github/workflows/*.yml", ".github/workflows/*.yaml",
)


def _is_config_file(path: Path, root: Path) -> bool:
    """True if `path` matches the high-signal non-code allowlist."""
    if path.name in CONFIG_NODE_BASENAMES:
        return True
    try:
        rel_posix = path.relative_to(root).as_posix()
    except ValueError:
        rel_posix = path.name
    for pattern in CONFIG_NODE_GLOBS:
        target = rel_posix if "/" in pattern else path.name
        if fnmatch.fnmatch(target, pattern):
            return True
    return False


def discover_package_roots(repo: Path) -> list[tuple[Path, str]]:
    """Heuristic: find Python package roots by climbing __init__.py chains.

    For each __init__.py, climb until the parent no longer contains an
    __init__.py — that outermost package's parent is an import root.  Filters
    out test namespaces so they don't pollute the root list.

    Returns list of (root_path, reason) sorted by path length (shallowest first).
    """
    skip = SKIP_DIRS | _PKG_ROOT_FILTER
    repo_str = str(repo)
    roots: dict[Path, str] = {}

    for init in repo.rglob("__init__.py"):
        if any(part in skip for part in init.parts):
            continue
        # Climb while parent is still a package
        pkg_top = init.parent
        while True:
            parent = pkg_top.parent
            if not str(parent).startswith(repo_str):
                break
            if not (parent / "__init__.py").exists():
                break
            pkg_top = parent
        # pkg_top is the outermost package dir; its parent is the import root
        pkg_root = pkg_top.parent
        if pkg_root not in roots:
            roots[pkg_root] = f"heuristic: {pkg_top.name}/__init__.py"

    return sorted(roots.items(), key=lambda kv: len(kv[0].parts))


def _parse_pyproject_roots(repo: Path) -> list[tuple[Path, str]]:
    """Parse pyproject.toml at repo root for explicit source directories.

    Reads [tool.setuptools], [tool.setuptools.packages.find], and
    [tool.poetry] stanzas.  Returns [] if tomllib/tomli is unavailable
    (Python < 3.11 without the backport) — the heuristic covers most cases.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        return []

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-reattr]
        except ImportError:
            return []

    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:
        return []

    roots: list[tuple[Path, str]] = []
    tool = data.get("tool", {})

    # [tool.setuptools] package-dir = {"": "src"}
    st = tool.get("setuptools", {})
    pkg_dir = st.get("package-dir", {})
    if "" in pkg_dir:
        src = repo / pkg_dir[""]
        if src.is_dir():
            roots.append((src, "config: pyproject.toml [tool.setuptools]"))

    # [tool.setuptools.packages.find] where = ["src"]
    packages = st.get("packages", {})
    if isinstance(packages, dict):
        for w in packages.get("find", {}).get("where", []):
            src = repo / w
            if src.is_dir():
                roots.append((src, "config: pyproject.toml [tool.setuptools.packages.find]"))

    # [tool.poetry] packages = [{include = "foo", from = "src"}]
    for pkg in tool.get("poetry", {}).get("packages", []):
        if isinstance(pkg, dict) and pkg.get("from"):
            src = repo / pkg["from"]
            if src.is_dir():
                roots.append((src, "config: pyproject.toml [tool.poetry]"))

    # [tool.hatch.build.targets.wheel] packages = ["src/mylib"]
    for pkg_path in (
        tool.get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
        .get("packages", [])
    ):
        src = (repo / pkg_path).parent
        if src.is_dir():
            roots.append((src, "config: pyproject.toml [tool.hatch]"))

    return roots


def _git_changed_files(root: Path) -> list[Path]:
    """Return modified + untracked files under `root` via git.

    Honors `root` via `-C`. Returns [] if git is missing, the dir is not a
    repo, or the commands time out. Errors are swallowed — this is an opt-in
    best-effort feature, not a hard dependency.
    """
    cmds = (
        ["git", "-C", str(root), "diff", "--name-only", "HEAD"],
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
    )
    out: list[Path] = []
    for cmd in cmds:
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=5, check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
        if res.returncode != 0:
            continue
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(root / line)
    return out


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
    if ext in C_CPP_EXTS:
        return "c++" if ext in {".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"} else "c"
    if ext in GO_EXTS:
        return "go"
    if ext in RUST_EXTS:
        return "rust"
    if ext in JAVA_EXTS:
        return "java"
    if ext in KOTLIN_EXTS:
        return "kotlin"
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
    and N for `from ..foo import x` (level N). For `from . import x`, we store
    the imported name (`x`) as the module so sibling modules resolve correctly.

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
                if node.module:
                    imports.append((node.module, node.level))
                else:
                    for alias in node.names:
                        imports.append((alias.name, node.level))
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
    raw: str | tuple[str, int], source_file: Path, root: Path,
    pkg_roots: list[Path] | None = None,
) -> str | None:
    """Resolve a Python import to a file path relative to root.

    Accepts either a legacy string (absolute import) or a (module, level) tuple
    from `_analyze_python`. Returns the relative path string, or None if the
    import is third-party/stdlib.

    Relative imports resolve against the source file's parent directory,
    walking up `level` packages. `from . import x` is represented as
    `(module="x", level=1)`, so we try `<parent>/x.py` first, then
    `<parent>/x/__init__.py`.

    pkg_roots: ordered list of import roots to search (config first, heuristic
    next, legacy fallbacks last).  When None, the old src/lib heuristic is used.
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

    # Absolute import — search all registered roots in priority order.
    if not module:
        return None
    parts = module.split(".")
    root_resolved = root.resolve()

    # Build search order: explicit pkg_roots first, then legacy fallbacks.
    search_roots: list[Path] = list(pkg_roots) if pkg_roots else []
    for fallback in (root, root / "src", root / "lib"):
        if fallback not in search_roots:
            search_roots.append(fallback)

    for search_root in search_roots:
        if not search_root.is_dir():
            continue
        candidate_file = search_root / Path(*parts).with_suffix(".py")
        candidate_pkg = search_root / Path(*parts) / "__init__.py"
        if candidate_file.exists():
            try:
                return str(candidate_file.resolve().relative_to(root_resolved))
            except ValueError:
                continue
        if candidate_pkg.exists():
            try:
                return str(candidate_pkg.resolve().relative_to(root_resolved))
            except ValueError:
                continue

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
# C/C++ analysis
# ---------------------------------------------------------------------------

# Matches #include "path" (local includes only — not <system>)
_C_INCLUDE_RE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.MULTILINE)

# Top-level symbols: functions, classes, structs, enums, typedefs
_C_FUNC_RE = re.compile(
    r"^(?:[\w:*&<>, ]+\s+)?(\w+)\s*\([^)]*\)\s*\{", re.MULTILINE
)
_C_CLASS_RE = re.compile(
    r"^(?:class|struct|enum)\s+(\w+)", re.MULTILINE
)


def _analyze_c_cpp(path: Path) -> tuple[list[Symbol], list[str]]:
    """Return (symbols, raw_include_paths) for a C/C++ file."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], []

    raw_includes = [m.group(1) for m in _C_INCLUDE_RE.finditer(source)]

    symbols: list[Symbol] = []
    for m in _C_CLASS_RE.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="class", line=source[:m.start()].count("\n") + 1))
    for m in _C_FUNC_RE.finditer(source):
        name = m.group(1)
        # Skip keywords that look like functions
        if name in ("if", "for", "while", "switch", "return", "sizeof", "catch", "else"):
            continue
        symbols.append(Symbol(name=name, kind="function", line=source[:m.start()].count("\n") + 1))

    return symbols, raw_includes


def _resolve_c_include(
    raw: str, source_file: Path, root: Path,
) -> str | None:
    """Resolve a #include "path" to a file path relative to root."""
    # Try relative to source file's directory first
    candidate = source_file.parent / raw
    if candidate.exists() and candidate.is_file():
        try:
            return str(candidate.resolve().relative_to(root.resolve()))
        except ValueError:
            return None

    # Try from project root
    candidate = root / raw
    if candidate.exists() and candidate.is_file():
        return str(candidate.relative_to(root))

    # Try common include dirs
    for inc_dir in ("include", "src", "lib"):
        candidate = root / inc_dir / raw
        if candidate.exists() and candidate.is_file():
            try:
                return str(candidate.resolve().relative_to(root.resolve()))
            except ValueError:
                return None

    return None


# ---------------------------------------------------------------------------
# Go analysis
# ---------------------------------------------------------------------------

# Single import: import "path"
# Block import: import (\n  "path"\n  "path"\n)
_GO_IMPORT_SINGLE_RE = re.compile(r'^\s*import\s+"([^"]+)"', re.MULTILINE)
_GO_IMPORT_BLOCK_RE = re.compile(r'import\s*\((.*?)\)', re.DOTALL)
_GO_IMPORT_LINE_RE = re.compile(r'"([^"]+)"')

_GO_FUNC_RE = re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(", re.MULTILINE)
_GO_TYPE_RE = re.compile(r"^type\s+(\w+)\s+(?:struct|interface)", re.MULTILINE)


def _analyze_go(path: Path) -> tuple[list[Symbol], list[str]]:
    """Return (symbols, raw_import_paths) for a Go file."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], []

    raw_imports: list[str] = []
    for m in _GO_IMPORT_SINGLE_RE.finditer(source):
        raw_imports.append(m.group(1))
    for m in _GO_IMPORT_BLOCK_RE.finditer(source):
        for line_m in _GO_IMPORT_LINE_RE.finditer(m.group(1)):
            raw_imports.append(line_m.group(1))

    symbols: list[Symbol] = []
    for m in _GO_FUNC_RE.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="function", line=source[:m.start()].count("\n") + 1))
    for m in _GO_TYPE_RE.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="class", line=source[:m.start()].count("\n") + 1))

    return symbols, raw_imports


def _resolve_go_import(
    raw: str, source_file: Path, root: Path,
) -> str | None:
    """Resolve a Go import to a file path relative to root.

    Go imports are package paths. We try to match the last segment(s) to
    directories in the project. Only resolves project-internal imports.
    """
    # Check if the import path contains the module name (from go.mod)
    go_mod = root / "go.mod"
    module_path = ""
    if go_mod.exists():
        try:
            for line in go_mod.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("module "):
                    module_path = line.split(None, 1)[1].strip()
                    break
        except OSError:
            pass

    if module_path and raw.startswith(module_path):
        # Internal import: strip module prefix
        rel = raw[len(module_path):].lstrip("/")
        candidate = root / rel
        if candidate.is_dir():
            # Find any .go file in the package dir to use as edge target
            for go_file in sorted(candidate.glob("*.go")):
                if go_file.name.endswith("_test.go"):
                    continue
                try:
                    return str(go_file.relative_to(root))
                except ValueError:
                    continue
    return None


# ---------------------------------------------------------------------------
# Rust analysis
# ---------------------------------------------------------------------------

_RUST_MOD_RE = re.compile(r"^\s*(?:pub\s+)?mod\s+(\w+)\s*;", re.MULTILINE)
_RUST_USE_RE = re.compile(r"^\s*(?:pub\s+)?use\s+(?:crate::)?(\w+)", re.MULTILINE)
_RUST_FN_RE = re.compile(r"^\s*(?:pub(?:\(.*?\))?\s+)?(?:async\s+)?fn\s+(\w+)", re.MULTILINE)
_RUST_TYPE_RE = re.compile(r"^\s*(?:pub(?:\(.*?\))?\s+)?(?:struct|enum|trait)\s+(\w+)", re.MULTILINE)


def _analyze_rust(path: Path) -> tuple[list[Symbol], list[str]]:
    """Return (symbols, raw_mod_names) for a Rust file."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], []

    # Collect mod declarations and use statements as import targets
    raw_imports: list[str] = []
    for m in _RUST_MOD_RE.finditer(source):
        raw_imports.append(m.group(1))
    for m in _RUST_USE_RE.finditer(source):
        name = m.group(1)
        if name not in ("self", "super", "std") and name not in raw_imports:
            raw_imports.append(name)

    symbols: list[Symbol] = []
    for m in _RUST_FN_RE.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="function", line=source[:m.start()].count("\n") + 1))
    for m in _RUST_TYPE_RE.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="class", line=source[:m.start()].count("\n") + 1))

    return symbols, raw_imports


def _resolve_rust_import(
    raw: str, source_file: Path, root: Path,
) -> str | None:
    """Resolve a Rust mod/use name to a file path relative to root.

    Rust modules map to either sibling_name.rs or sibling_name/mod.rs.
    """
    parent = source_file.parent

    # If source is lib.rs or main.rs, modules are in the same dir
    # If source is foo.rs, modules are in foo/<name>.rs
    stem = source_file.stem
    if stem in ("lib", "main", "mod"):
        base = parent
    else:
        base = parent / stem

    # Try <base>/<name>.rs
    candidate = base / f"{raw}.rs"
    if candidate.exists():
        try:
            return str(candidate.resolve().relative_to(root.resolve()))
        except ValueError:
            return None

    # Try <base>/<name>/mod.rs
    candidate = base / raw / "mod.rs"
    if candidate.exists():
        try:
            return str(candidate.resolve().relative_to(root.resolve()))
        except ValueError:
            return None

    # Try from src/ root for crate-level use statements
    src = root / "src"
    if src.is_dir():
        for cand in (src / f"{raw}.rs", src / raw / "mod.rs"):
            if cand.exists():
                try:
                    return str(cand.resolve().relative_to(root.resolve()))
                except ValueError:
                    return None

    return None


# ---------------------------------------------------------------------------
# Java / Kotlin analysis
# ---------------------------------------------------------------------------

_JAVA_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([a-zA-Z_][\w.]*)", re.MULTILINE)
_JAVA_CLASS_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+)?(?:abstract\s+|final\s+)?(?:class|interface|enum|record)\s+(\w+)",
    re.MULTILINE,
)
_JAVA_METHOD_RE = re.compile(
    r"^\s*(?:public|private|protected)\s+(?:static\s+)?(?:[\w<>,\[\] ]+\s+)(\w+)\s*\(",
    re.MULTILINE,
)

_KOTLIN_IMPORT_RE = re.compile(r"^\s*import\s+([a-zA-Z_][\w.]*)", re.MULTILINE)
_KOTLIN_CLASS_RE = re.compile(
    r"^\s*(?:data\s+|sealed\s+|abstract\s+|open\s+|enum\s+)?class\s+(\w+)",
    re.MULTILINE,
)
_KOTLIN_FUN_RE = re.compile(r"^\s*(?:(?:private|internal|public|override|suspend)\s+)*fun\s+(\w+)", re.MULTILINE)


def _analyze_java(path: Path) -> tuple[list[Symbol], list[str]]:
    """Return (symbols, raw_import_paths) for a Java file."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], []

    raw_imports = [m.group(1) for m in _JAVA_IMPORT_RE.finditer(source)]

    symbols: list[Symbol] = []
    for m in _JAVA_CLASS_RE.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="class", line=source[:m.start()].count("\n") + 1))
    for m in _JAVA_METHOD_RE.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="function", line=source[:m.start()].count("\n") + 1))

    return symbols, raw_imports


def _analyze_kotlin(path: Path) -> tuple[list[Symbol], list[str]]:
    """Return (symbols, raw_import_paths) for a Kotlin file."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], []

    raw_imports = [m.group(1) for m in _KOTLIN_IMPORT_RE.finditer(source)]

    symbols: list[Symbol] = []
    for m in _KOTLIN_CLASS_RE.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="class", line=source[:m.start()].count("\n") + 1))
    for m in _KOTLIN_FUN_RE.finditer(source):
        symbols.append(Symbol(name=m.group(1), kind="function", line=source[:m.start()].count("\n") + 1))

    return symbols, raw_imports


def _resolve_java_import(
    raw: str, source_file: Path, root: Path,
) -> str | None:
    """Resolve a Java/Kotlin import to a file path relative to root.

    Java imports are fully qualified class names (com.example.Foo).
    We try to map them to a .java or .kt file in the project.
    """
    parts = raw.split(".")
    # The last part is the class name, everything before is the package path
    # Try: src/main/java/com/example/Foo.java (Maven/Gradle layout)
    # Also try: src/com/example/Foo.java and just com/example/Foo.java
    class_name = parts[-1]
    package_path = Path(*parts[:-1]) if len(parts) > 1 else Path()

    ext = source_file.suffix  # .java or .kt
    search_roots = [
        root / "src" / "main" / "java",
        root / "src" / "main" / "kotlin",
        root / "src",
        root,
    ]

    for sr in search_roots:
        if not sr.is_dir():
            continue
        for try_ext in (ext, ".java", ".kt"):
            candidate = sr / package_path / f"{class_name}{try_ext}"
            if candidate.exists() and candidate.is_file():
                try:
                    return str(candidate.resolve().relative_to(root.resolve()))
                except ValueError:
                    return None

    return None


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

def _collect_files(
    root: Path,
    max_files: int,
    include_config: bool = True,
    include_changed: bool = False,
) -> list[Path]:
    """Walk root and collect files worth surfacing in the graph.

    Policy:
      * Files returned by git diff / untracked status are prioritized when
        include_changed=True, so the escape hatch still works under max_files.
      * Code files (suffix in ALL_EXTS) are otherwise included.
      * High-signal non-code files (see CONFIG_NODE_BASENAMES/CONFIG_NODE_GLOBS)
        are included when include_config=True.

    Dot-directories are skipped unless they're in ALLOWED_DOTDIRS. SKIP_DIRS
    is always honored. Symlinks are never followed.
    """
    files: list[Path] = []
    seen_real: set[str] = set()

    def _add(fpath: Path) -> bool:
        """Record fpath if new. Returns True when the max_files cap is reached."""
        if fpath.is_symlink():
            return False
        try:
            real = str(fpath.resolve())
        except OSError:
            return False
        if real in seen_real:
            return False
        seen_real.add(real)
        files.append(fpath)
        return len(files) >= max_files

    if include_changed:
        for fpath in _git_changed_files(root):
            if not fpath.exists() or fpath.is_dir():
                continue
            if _add(fpath):
                return files

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune skip dirs and symlinked dirs in-place. Dot-directories get a
        # one-shot allowlist check — generic `.cache`, `.idea`, etc. still get
        # pruned, but `.github`/`.vscode`/`.devcontainer` pass through.
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS
            and (not d.startswith(".") or d in ALLOWED_DOTDIRS)
            and not (Path(dirpath) / d).is_symlink()
        ]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            ext_supported = fpath.suffix.lower() in ALL_EXTS
            is_config = include_config and _is_config_file(fpath, root)
            if not (ext_supported or is_config):
                continue
            if _add(fpath):
                return files

    return files


def analyze(
    root_path: Path,
    max_files: int = 500,
    include_config: bool = True,
    include_changed: bool = False,
) -> Graph:
    """Parse a project directory and return a Graph with nodes and IMPORTS edges.

    Args:
        root_path: Project root directory.
        max_files: Maximum number of files to analyze (ranked by discovery order).
        include_config: Surface high-signal non-code files (Makefile, Dockerfile,
            pyproject.toml, .github/workflows/*.yml, ...) as node-only entries.
        include_changed: Also include files returned by `git diff --name-only`
            and `git ls-files --others --exclude-standard`, even if they aren't
            code or config. Opt-in escape hatch for files the user just touched.

    Returns:
        A Graph with nodes (one per file) and edges (IMPORTS relationships).
        Node descriptions are empty — call describer.describe() to fill them.
    """
    root = root_path.resolve()
    files = _collect_files(
        root, max_files,
        include_config=include_config,
        include_changed=include_changed,
    )

    # Discover Python package roots (config > heuristic > legacy fallbacks).
    # Printed so users can immediately see why imports resolve (or don't).
    cfg_roots = _parse_pyproject_roots(root)
    heuristic_roots = [
        (p, r) for p, r in discover_package_roots(root)
        if not any(p == cp for cp, _ in cfg_roots)
    ]
    all_root_entries = cfg_roots + heuristic_roots
    pkg_roots: list[Path] = [p for p, _ in all_root_entries]

    if all_root_entries:
        print("Package roots detected:")
        for p, reason in all_root_entries:
            try:
                label = str(p.relative_to(root)) or "."
            except ValueError:
                label = str(p)
            print(f"  {label}  ({reason})")
        print(f"Resolving imports from {len(pkg_roots)} root(s).")

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

        # Non-code files that passed the collector either because they're in
        # the config allowlist or because --include-changed surfaced them.
        # They get a node but no edges. "config" tags allowlisted files;
        # "other" tags unknown-type files picked up via --include-changed.
        if lang == "other" and _is_config_file(fpath, root):
            lang = "config"

        if lang == "python":
            symbols, raw_imports = _analyze_python(fpath, root)
        elif lang in ("javascript", "typescript"):
            symbols, raw_imports = _analyze_js(fpath, root)
        elif lang in ("c", "c++"):
            symbols, raw_imports = _analyze_c_cpp(fpath)
        elif lang == "go":
            symbols, raw_imports = _analyze_go(fpath)
        elif lang == "rust":
            symbols, raw_imports = _analyze_rust(fpath)
        elif lang == "java":
            symbols, raw_imports = _analyze_java(fpath)
        elif lang == "kotlin":
            symbols, raw_imports = _analyze_kotlin(fpath)
        else:
            # "config" and "other" land here — Node-only, no edges.
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
    # Track unresolved absolute Python imports for the orphan-import warning.
    _failed_abs: dict[str, int] = {}
    # Resolution coverage counters (internal = resolved to a node in graph).
    _total_imports = 0
    _internal_imports = 0
    _external_imports = 0

    for fpath in files:
        rel = str(fpath.relative_to(root))
        lang, raw_imports = file_analysis[rel]

        for raw in raw_imports:
            _total_imports += 1
            if lang == "python":
                target = _resolve_python_import(raw, fpath, root, pkg_roots=pkg_roots)
                # Record misses for the orphan-import warning (absolute only).
                if target is None and isinstance(raw, tuple):
                    module, level = raw
                    if level == 0 and module:
                        top = module.split(".")[0]
                        _failed_abs[top] = _failed_abs.get(top, 0) + 1
            elif lang in ("javascript", "typescript"):
                target = _resolve_js_import(raw, fpath, root, aliases=ts_aliases)
            elif lang in ("c", "c++"):
                target = _resolve_c_include(raw, fpath, root)
            elif lang == "go":
                target = _resolve_go_import(raw, fpath, root)
            elif lang == "rust":
                target = _resolve_rust_import(raw, fpath, root)
            elif lang in ("java", "kotlin"):
                target = _resolve_java_import(raw, fpath, root)
            else:
                target = None

            if target and target in node_ids and (rel, target) not in seen_edges:
                graph.edges.append(Edge(source=rel, target=target, type="imports"))
                seen_edges.add((rel, target))
                _internal_imports += 1
            elif target is None:
                _external_imports += 1

    # Orphan-import warning: top-level names that appear ≥5 times as external
    # but match a real directory in the repo — almost certainly a missing root.
    if _failed_abs:
        repo_dirs: dict[str, Path] = {}
        for dirpath, dirnames, _ in os.walk(root, followlinks=False):
            # Mirror the same pruning as _collect_files so we don't false-positive
            # on .mypy_cache, .venv, node_modules, etc.
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS
                and (not d.startswith(".") or d in ALLOWED_DOTDIRS)
            ]
            for d in dirnames:
                if d not in repo_dirs:
                    repo_dirs[d] = Path(dirpath) / d
        for name, count in sorted(_failed_abs.items(), key=lambda kv: -kv[1]):
            if count >= 5 and name in repo_dirs:
                match_path = repo_dirs[name]
                try:
                    parent_rel = str(match_path.parent.relative_to(root)) or "."
                except ValueError:
                    parent_rel = str(match_path.parent)
                print(
                    f"\n⚠  {count} imports of `{name}` classified as external,\n"
                    f"   but `{parent_rel}/{name}/` exists in the repo.\n"
                    f"   → re-run from inside `{parent_rel}/`, or\n"
                    f"   → add `{parent_rel}` to [tool.prefxplain] package_roots in pyproject.toml"
                )

    # Resolution coverage summary (helps users spot misconfigured roots quickly).
    if _total_imports > 0:
        _other = _total_imports - _internal_imports - _external_imports
        msg = f"Imports resolved: {_internal_imports}/{_total_imports} internal"
        if _external_imports:
            msg += f", {_external_imports} external/stdlib"
        if _other:
            msg += f", {_other} cross-file deduped"
        print(msg)

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
            if not has_real_code and in_deg.get(n.id, 0) == 0 and out_deg.get(n.id, 0) == 0:
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
    graph.metadata.package_roots = [
        str(p.relative_to(root)) if p != root else "." for p in pkg_roots
    ]

    return graph
