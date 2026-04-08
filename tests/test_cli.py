"""Tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from prefxplain.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def py_project(tmp_path: Path) -> Path:
    """Minimal Python project for CLI tests."""
    (tmp_path / "main.py").write_text("from utils import helper\ndef run(): pass\n")
    (tmp_path / "utils.py").write_text("def helper(): return 42\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Create command
# ---------------------------------------------------------------------------


class TestCreateCommand:
    def test_create_produces_html(self, py_project: Path) -> None:
        result = runner.invoke(app, ["create", str(py_project), "--no-descriptions", "--no-open"])
        assert result.exit_code == 0, result.output
        assert (py_project / "prefxplain.html").exists()
        assert (py_project / "prefxplain.json").exists()

    def test_create_custom_output(self, py_project: Path, tmp_path: Path) -> None:
        out = tmp_path / "custom.html"
        result = runner.invoke(
            app, ["create", str(py_project), "--no-descriptions", "--no-open", "-o", str(out)]
        )
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_create_reports_file_count(self, py_project: Path) -> None:
        result = runner.invoke(app, ["create", str(py_project), "--no-descriptions", "--no-open"])
        assert result.exit_code == 0
        assert "2 files" in result.output

    def test_create_max_files(self, py_project: Path) -> None:
        result = runner.invoke(
            app,
            ["create", str(py_project), "--no-descriptions", "--no-open", "--max-files", "1"],
        )
        assert result.exit_code == 0
        assert "1 file" in result.output or "1 files" in result.output


# ---------------------------------------------------------------------------
# Update command
# ---------------------------------------------------------------------------


class TestUpdateCommand:
    def test_update_after_create(self, py_project: Path) -> None:
        # First create
        runner.invoke(app, ["create", str(py_project), "--no-descriptions", "--no-open"])
        assert (py_project / "prefxplain.json").exists()

        # Then update
        result = runner.invoke(app, ["update", str(py_project), "--no-descriptions", "--no-open"])
        assert result.exit_code == 0, result.output
        assert (py_project / "prefxplain.html").exists()


# ---------------------------------------------------------------------------
# Version flag
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "prefxplain" in result.output


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_directory(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["create", str(tmp_path), "--no-descriptions", "--no-open"])
        assert result.exit_code == 0
        assert "0 files" in result.output

    def test_html_is_self_contained(self, py_project: Path) -> None:
        runner.invoke(app, ["create", str(py_project), "--no-descriptions", "--no-open"])
        html = (py_project / "prefxplain.html").read_text()
        assert "<script>" in html
        assert "<style>" in html
        # No external CDN references
        assert "cdn." not in html.lower()
