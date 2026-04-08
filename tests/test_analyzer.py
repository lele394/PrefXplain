"""Tests for the static analyzer."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from prefxplain.analyzer import (
    analyze,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_py_project(tmp_path: Path) -> Path:
    """Create a minimal Python project for testing."""
    (tmp_path / "main.py").write_text(textwrap.dedent("""\
        from utils import helper
        import os

        def run():
            pass
    """))
    (tmp_path / "utils.py").write_text(textwrap.dedent("""\
        def helper():
            return 42
    """))
    (tmp_path / "models" / "__init__.py").parent.mkdir()
    (tmp_path / "models" / "__init__.py").write_text("class User: pass\n")
    return tmp_path


@pytest.fixture
def tmp_ts_project(tmp_path: Path) -> Path:
    """Create a minimal TypeScript project for testing."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text(textwrap.dedent("""\
        import { helper } from './utils';
        export function main() {}
    """))
    (src / "utils.ts").write_text(textwrap.dedent("""\
        export function helper() { return 42; }
        export const VERSION = '1.0';
    """))
    return tmp_path


# ---------------------------------------------------------------------------
# Python analysis
# ---------------------------------------------------------------------------

class TestPythonAnalysis:
    def test_finds_all_files(self, tmp_py_project: Path) -> None:
        graph = analyze(tmp_py_project)
        ids = {n.id for n in graph.nodes}
        assert "main.py" in ids
        assert "utils.py" in ids
        assert str(Path("models") / "__init__.py") in ids

    def test_extracts_imports_edge(self, tmp_py_project: Path) -> None:
        graph = analyze(tmp_py_project)
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("main.py", "utils.py") in edges

    def test_skips_stdlib_imports(self, tmp_py_project: Path) -> None:
        graph = analyze(tmp_py_project)
        # 'os' is stdlib — should not create an edge
        targets = {e.target for e in graph.edges if e.source == "main.py"}
        assert all("os" not in t for t in targets)

    def test_extracts_symbols(self, tmp_py_project: Path) -> None:
        graph = analyze(tmp_py_project)
        main_node = graph.get_node("main.py")
        assert main_node is not None
        symbol_names = {s.name for s in main_node.symbols}
        assert "run" in symbol_names

    def test_language_detected(self, tmp_py_project: Path) -> None:
        graph = analyze(tmp_py_project)
        main_node = graph.get_node("main.py")
        assert main_node is not None
        assert main_node.language == "python"

    def test_metadata_populated(self, tmp_py_project: Path) -> None:
        graph = analyze(tmp_py_project)
        assert graph.metadata is not None
        assert graph.metadata.total_files == len(graph.nodes)
        assert "python" in graph.metadata.languages


# ---------------------------------------------------------------------------
# JS/TS analysis
# ---------------------------------------------------------------------------

class TestJSTSAnalysis:
    def test_finds_ts_files(self, tmp_ts_project: Path) -> None:
        graph = analyze(tmp_ts_project)
        ids = {n.id for n in graph.nodes}
        assert "src/index.ts" in ids
        assert "src/utils.ts" in ids

    def test_extracts_relative_import_edge(self, tmp_ts_project: Path) -> None:
        graph = analyze(tmp_ts_project)
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("src/index.ts", "src/utils.ts") in edges

    def test_extracts_exported_symbols(self, tmp_ts_project: Path) -> None:
        graph = analyze(tmp_ts_project)
        utils_node = graph.get_node("src/utils.ts")
        assert utils_node is not None
        names = {s.name for s in utils_node.symbols}
        assert "helper" in names
        assert "VERSION" in names

    def test_language_detected(self, tmp_ts_project: Path) -> None:
        graph = analyze(tmp_ts_project)
        node = graph.get_node("src/index.ts")
        assert node is not None
        assert node.language == "typescript"


# ---------------------------------------------------------------------------
# Graph methods
# ---------------------------------------------------------------------------

class TestGraphMethods:
    def test_get_node(self, tmp_py_project: Path) -> None:
        graph = analyze(tmp_py_project)
        node = graph.get_node("main.py")
        assert node is not None
        assert node.label == "main.py"

    def test_get_node_missing(self, tmp_py_project: Path) -> None:
        graph = analyze(tmp_py_project)
        assert graph.get_node("nonexistent.py") is None

    def test_indegree_outdegree(self, tmp_py_project: Path) -> None:
        graph = analyze(tmp_py_project)
        # utils.py is imported by main.py
        assert graph.indegree("utils.py") >= 1
        assert graph.outdegree("main.py") >= 1

    def test_save_load_roundtrip(self, tmp_py_project: Path, tmp_path: Path) -> None:
        from prefxplain.graph import Graph

        graph = analyze(tmp_py_project)
        out = tmp_path / "graph.json"
        graph.save(out)
        loaded = Graph.load(out)
        assert len(loaded.nodes) == len(graph.nodes)
        assert len(loaded.edges) == len(graph.edges)


# ---------------------------------------------------------------------------
# Skip dirs
# ---------------------------------------------------------------------------

class TestSkipDirs:
    def test_skips_node_modules(self, tmp_path: Path) -> None:
        nm = tmp_path / "node_modules" / "lodash"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {};")
        (tmp_path / "app.js").write_text("const _ = require('lodash');")
        graph = analyze(tmp_path)
        ids = {n.id for n in graph.nodes}
        assert not any("node_modules" in i for i in ids)

    def test_skips_venv(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "site.py").write_text("pass")
        (tmp_path / "main.py").write_text("pass")
        graph = analyze(tmp_path)
        ids = {n.id for n in graph.nodes}
        assert not any(".venv" in i for i in ids)


# ---------------------------------------------------------------------------
# tsconfig.json path alias resolution
# ---------------------------------------------------------------------------


class TestTsconfigAliases:
    """The function that 35x'd edge counts on Next.js projects. Critical path."""

    def _make_ts_project(self, tmp_path: Path, tsconfig_content: str, sub: str = "") -> Path:
        """Create a TS project with src/lib/utils.ts and a configurable tsconfig."""
        root = tmp_path / sub if sub else tmp_path
        root.mkdir(parents=True, exist_ok=True)
        src = root / "src" / "lib"
        src.mkdir(parents=True)
        (src / "utils.ts").write_text("export function cn() {}\n")
        # Importer uses the @ alias
        components = root / "src" / "components"
        components.mkdir()
        (components / "Button.tsx").write_text(
            "import { cn } from '@/lib/utils';\nexport function Button() {}\n"
        )
        (root / "tsconfig.json").write_text(tsconfig_content)
        return tmp_path

    def test_at_alias_resolves(self, tmp_path: Path) -> None:
        """`@/lib/utils` → `src/lib/utils.ts` via tsconfig paths."""
        self._make_ts_project(
            tmp_path,
            '{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}',
        )
        graph = analyze(tmp_path)
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("src/components/Button.tsx", "src/lib/utils.ts") in edges

    def test_jsonc_comments_supported(self, tmp_path: Path) -> None:
        """Real tsconfig.json files use JSONC. Comments must not break parsing."""
        self._make_ts_project(
            tmp_path,
            """{
  // This is a line comment
  /* Block comment
     with multiple lines */
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"]  // trailing comment
    }
  }
}
""",
        )
        graph = analyze(tmp_path)
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("src/components/Button.tsx", "src/lib/utils.ts") in edges

    def test_trailing_commas_supported(self, tmp_path: Path) -> None:
        """JSONC allows trailing commas."""
        self._make_ts_project(
            tmp_path,
            """{
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"],
    },
  },
}
""",
        )
        graph = analyze(tmp_path)
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("src/components/Button.tsx", "src/lib/utils.ts") in edges

    def test_tsconfig_one_level_down(self, tmp_path: Path) -> None:
        """Common Next.js layout: tsconfig.json lives in `web/`, not the repo root."""
        web = tmp_path / "web"
        web.mkdir()
        src_lib = web / "src" / "lib"
        src_lib.mkdir(parents=True)
        (src_lib / "utils.ts").write_text("export function cn() {}\n")
        components = web / "src" / "components"
        components.mkdir()
        (components / "Button.tsx").write_text(
            "import { cn } from '@/lib/utils';\nexport function Button() {}\n"
        )
        (web / "tsconfig.json").write_text(
            '{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}'
        )
        graph = analyze(tmp_path)
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("web/src/components/Button.tsx", "web/src/lib/utils.ts") in edges

    def test_malformed_tsconfig_does_not_crash(self, tmp_path: Path) -> None:
        """Invalid JSON in tsconfig should not crash analysis."""
        (tmp_path / "main.ts").write_text("export const X = 1;\n")
        (tmp_path / "tsconfig.json").write_text("not valid json {{{ [")
        # Should not raise
        graph = analyze(tmp_path)
        ids = {n.id for n in graph.nodes}
        assert "main.ts" in ids


# ---------------------------------------------------------------------------
# Python relative imports (the P1 fix)
# ---------------------------------------------------------------------------


class TestPythonRelativeImports:
    def test_from_dot_resolves(self, tmp_path: Path) -> None:
        """`from .utils import x` resolves to sibling utils.py."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "main.py").write_text("from .utils import helper\n")
        (pkg / "utils.py").write_text("def helper(): pass\n")
        graph = analyze(tmp_path)
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("mypkg/main.py", "mypkg/utils.py") in edges

    def test_from_double_dot_resolves(self, tmp_path: Path) -> None:
        """`from ..foo import bar` resolves up one level."""
        pkg = tmp_path / "mypkg"
        sub = pkg / "sub"
        sub.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (sub / "__init__.py").write_text("")
        (sub / "child.py").write_text("from ..parent import thing\n")
        (pkg / "parent.py").write_text("def thing(): pass\n")
        graph = analyze(tmp_path)
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("mypkg/sub/child.py", "mypkg/parent.py") in edges

    def test_src_layout_resolves(self, tmp_path: Path) -> None:
        """`from mypkg import x` works when package is under src/."""
        src_pkg = tmp_path / "src" / "mypkg"
        src_pkg.mkdir(parents=True)
        (src_pkg / "__init__.py").write_text("")
        (src_pkg / "core.py").write_text("def thing(): pass\n")
        # Top-level test that imports the package
        (tmp_path / "test_main.py").write_text("from mypkg.core import thing\n")
        graph = analyze(tmp_path)
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("test_main.py", "src/mypkg/core.py") in edges

    def test_nested_function_not_extracted_as_symbol(self, tmp_path: Path) -> None:
        """ast.walk would record nested functions; we should only get top-level + class methods."""
        (tmp_path / "main.py").write_text(
            "def outer():\n"
            "    def inner():\n"
            "        pass\n"
            "    return inner\n"
        )
        graph = analyze(tmp_path)
        node = graph.get_node("main.py")
        assert node is not None
        symbol_names = {s.name for s in node.symbols}
        assert "outer" in symbol_names
        assert "inner" not in symbol_names
