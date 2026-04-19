"""Tests for the non-code-node extension: high-signal config files surfaced
as graph nodes, allowlisted dot-directories walked, and `include_changed`
escape hatch for files returned by git diff."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from prefxplain.analyzer import (
    ALLOWED_DOTDIRS,
    SKIP_DIRS,
    _collect_files,
    _git_changed_files,
    _is_config_file,
    analyze,
)


class TestIsConfigFile:
    def test_basename_matches(self, tmp_path: Path) -> None:
        assert _is_config_file(tmp_path / "Makefile", tmp_path) is True
        assert _is_config_file(tmp_path / "Dockerfile", tmp_path) is True
        assert _is_config_file(tmp_path / "pyproject.toml", tmp_path) is True
        assert _is_config_file(tmp_path / "package.json", tmp_path) is True
        assert _is_config_file(tmp_path / "go.mod", tmp_path) is True

    def test_name_glob_matches(self, tmp_path: Path) -> None:
        # basename-only glob patterns
        assert _is_config_file(tmp_path / "tsconfig.json", tmp_path) is True
        assert _is_config_file(tmp_path / "tsconfig.base.json", tmp_path) is True
        assert _is_config_file(tmp_path / "requirements.txt", tmp_path) is True
        assert _is_config_file(tmp_path / "requirements-dev.txt", tmp_path) is True

    def test_path_glob_matches_only_under_anchor(self, tmp_path: Path) -> None:
        gh = tmp_path / ".github" / "workflows"
        gh.mkdir(parents=True)
        assert _is_config_file(gh / "ci.yml", tmp_path) is True
        assert _is_config_file(gh / "release.yaml", tmp_path) is True
        # Generic YAMLs NOT under .github/workflows must not match.
        elsewhere = tmp_path / "config" / "random.yml"
        elsewhere.parent.mkdir(parents=True)
        assert _is_config_file(elsewhere, tmp_path) is False

    def test_random_code_file_not_config(self, tmp_path: Path) -> None:
        assert _is_config_file(tmp_path / "script.py", tmp_path) is False
        assert _is_config_file(tmp_path / "README.md", tmp_path) is False


class TestWalkerAllowedDotdirs:
    def test_github_workflow_yml_picked_up(self, tmp_path: Path) -> None:
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
        (tmp_path / "main.py").write_text("import os\n")
        files = _collect_files(tmp_path, max_files=100)
        rels = {str(f.relative_to(tmp_path)) for f in files}
        assert "main.py" in rels
        assert ".github/workflows/ci.yml" in rels

    def test_git_dir_still_skipped(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (tmp_path / "main.py").write_text("pass\n")
        files = _collect_files(tmp_path, max_files=100)
        assert not any(".git" in f.parts for f in files)

    def test_generic_dotdir_still_skipped(self, tmp_path: Path) -> None:
        # .cache is not in the allowlist → pruned regardless of contents.
        (tmp_path / ".cache").mkdir()
        (tmp_path / ".cache" / "noise.py").write_text("pass\n")
        (tmp_path / "main.py").write_text("pass\n")
        files = _collect_files(tmp_path, max_files=100)
        rels = {str(f.relative_to(tmp_path)) for f in files}
        assert "main.py" in rels
        assert ".cache/noise.py" not in rels

    def test_allowed_dotdirs_set_is_sensible(self) -> None:
        assert ".github" in ALLOWED_DOTDIRS
        assert ".vscode" in ALLOWED_DOTDIRS

    def test_prefxplain_vscode_not_skipped(self) -> None:
        # Regression: used to live in SKIP_DIRS which hid the bundled
        # extension from the graph.
        assert "prefxplain-vscode" not in SKIP_DIRS


class TestCollectFilesIncludeConfig:
    def test_include_config_true_surfaces_makefile(self, tmp_path: Path) -> None:
        (tmp_path / "Makefile").write_text("all:\n\techo hi\n")
        (tmp_path / "main.py").write_text("pass\n")
        files = _collect_files(tmp_path, 100, include_config=True)
        rels = {str(f.relative_to(tmp_path)) for f in files}
        assert "Makefile" in rels
        assert "main.py" in rels

    def test_include_config_false_hides_config(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile").write_text("FROM python:3\n")
        (tmp_path / "main.py").write_text("pass\n")
        files = _collect_files(tmp_path, 100, include_config=False)
        rels = {str(f.relative_to(tmp_path)) for f in files}
        assert "main.py" in rels
        assert "Dockerfile" not in rels

    def test_random_yaml_not_included_even_with_config_on(self, tmp_path: Path) -> None:
        # A random .yml file outside .github/workflows must NOT sneak in.
        (tmp_path / "random.yml").write_text("a: 1\n")
        (tmp_path / "main.py").write_text("pass\n")
        files = _collect_files(tmp_path, 100, include_config=True)
        rels = {str(f.relative_to(tmp_path)) for f in files}
        assert "random.yml" not in rels


class TestIncludeChanged:
    def test_include_changed_surfaces_untracked_md(
        self, tmp_path: Path,
    ) -> None:
        notes = tmp_path / "NOTES.md"
        notes.write_text("# hi\n")
        (tmp_path / "main.py").write_text("pass\n")

        fake = (
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="NOTES.md\n", stderr="",
            ),
        )
        it = iter(fake)
        with patch(
            "prefxplain.analyzer.subprocess.run",
            side_effect=lambda *a, **k: next(it),
        ):
            files = _collect_files(
                tmp_path, 100,
                include_config=True,
                include_changed=True,
            )
        rels = {str(f.relative_to(tmp_path)) for f in files}
        assert "NOTES.md" in rels
        assert "main.py" in rels

    def test_git_missing_no_crash(self, tmp_path: Path) -> None:
        with patch(
            "prefxplain.analyzer.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            assert _git_changed_files(tmp_path) == []

    def test_include_changed_off_by_default(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("hi\n")
        (tmp_path / "main.py").write_text("pass\n")
        with patch(
            "prefxplain.analyzer.subprocess.run",
        ) as runner:
            files = _collect_files(tmp_path, 100)
            runner.assert_not_called()
        rels = {str(f.relative_to(tmp_path)) for f in files}
        assert "README.md" not in rels

    def test_include_changed_is_prioritized_under_max_files(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("pass\n")
        for index in range(5):
            (tmp_path / f"mod_{index}.py").write_text("pass\n")
        (tmp_path / "notes.txt").write_text("scratch\n")

        fake = (
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="notes.txt\n", stderr="",
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            ),
        )
        it = iter(fake)
        with patch(
            "prefxplain.analyzer.subprocess.run",
            side_effect=lambda *a, **k: next(it),
        ):
            files = _collect_files(
                tmp_path, 3,
                include_config=True,
                include_changed=True,
            )
        rels = {str(f.relative_to(tmp_path)) for f in files}
        assert "notes.txt" in rels


class TestAnalyzeConfigLang:
    def test_config_file_becomes_node_with_lang_config(
        self, tmp_path: Path,
    ) -> None:
        (tmp_path / "Makefile").write_text("all:\n\techo hi\n")
        (tmp_path / "main.py").write_text("pass\n")
        graph = analyze(tmp_path)
        by_id = {n.id: n for n in graph.nodes}
        assert "Makefile" in by_id
        assert by_id["Makefile"].language == "config"
        # No edges produced from a config node.
        assert not any(
            e.source == "Makefile" or e.target == "Makefile"
            for e in graph.edges
        )

    def test_changed_file_with_unknown_ext_gets_lang_other(
        self, tmp_path: Path,
    ) -> None:
        # A random txt surfaced via --include-changed is a node with language "other".
        (tmp_path / "notes.txt").write_text("scratch\n")
        (tmp_path / "main.py").write_text("pass\n")
        fake = (
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="notes.txt\n", stderr="",
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            ),
        )
        it = iter(fake)
        with patch(
            "prefxplain.analyzer.subprocess.run",
            side_effect=lambda *a, **k: next(it),
        ):
            graph = analyze(tmp_path, include_changed=True)
        by_id = {n.id: n for n in graph.nodes}
        assert "notes.txt" in by_id
        assert by_id["notes.txt"].language == "other"
