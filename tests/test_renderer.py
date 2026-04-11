"""Tests for the HTML renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from prefxplain.analyzer import analyze
from prefxplain.graph import Edge, Graph, GraphMetadata, Node
from prefxplain.renderer import render


@pytest.fixture
def simple_graph() -> Graph:
    graph = Graph(
        metadata=GraphMetadata(
            repo="test-repo",
            generated_at="2026-01-01T00:00:00Z",
            total_files=2,
            languages=["python"],
        )
    )
    graph.nodes.append(Node(id="main.py", label="main.py", description="Entry point.", language="python", size=100))
    graph.nodes.append(Node(id="utils.py", label="utils.py", description="Utility helpers.", language="python", size=50))
    graph.edges.append(Edge(source="main.py", target="utils.py", type="imports"))
    return graph


class TestRenderer:
    def test_returns_html_string(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html or "<html" in html

    def test_contains_node_ids(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert "main.py" in html
        assert "utils.py" in html

    def test_writes_to_file(self, simple_graph: Graph, tmp_path: Path) -> None:
        out = tmp_path / "graph.html"
        render(simple_graph, output_path=out)
        assert out.exists()
        content = out.read_text()
        assert "main.py" in content

    def test_self_contained_no_cdn(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        # No external CDN links
        assert "cdn.jsdelivr.net" not in html
        assert "unpkg.com" not in html
        assert "cdnjs.cloudflare.com" not in html

    def test_descriptions_included(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert "Entry point." in html
        assert "Utility helpers." in html

    def test_empty_graph(self) -> None:
        graph = Graph(
            metadata=GraphMetadata(
                repo="empty",
                generated_at="2026-01-01T00:00:00Z",
                total_files=0,
                languages=[],
            )
        )
        html = render(graph)
        assert isinstance(html, str)
        assert len(html) > 100  # still renders a valid page

    def test_real_project(self, tmp_path: Path) -> None:
        """End-to-end: analyze a real Python project and render it."""
        (tmp_path / "a.py").write_text("from b import foo\ndef main(): pass\n")
        (tmp_path / "b.py").write_text("def foo(): return 1\n")
        graph = analyze(tmp_path)
        html = render(graph)
        assert "a.py" in html
        assert "b.py" in html

    def test_embedded_js_is_syntactically_valid(self, tmp_path: Path) -> None:
        """Catch Python-template bugs that produce malformed JS in the output.

        We had a bug where '\\n' in the f-string template got rendered as a
        literal newline inside a JS string, breaking the whole script. This
        test syntax-checks the embedded <script> with node if available.
        """
        import re
        import shutil
        import subprocess

        if not shutil.which("node"):
            pytest.skip("node not installed — skipping JS syntax check")

        (tmp_path / "a.py").write_text(
            'def helper():\n'
            '    """A docstring with quotes \'mixed\' and special <chars>."""\n'
            '    return 42\n'
        )
        graph = analyze(tmp_path)
        html = render(graph)

        match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
        assert match is not None, "rendered HTML missing <script> tag"
        js_path = tmp_path / "embedded.js"
        js_path.write_text(match.group(1))

        result = subprocess.run(
            ["node", "--check", str(js_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"embedded JS syntax error:\n{result.stderr}"

    def test_layout_supports_vertical_shrink(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert ":root { --viewport-height: 100vh; --top-panel-header-height: 32px; --top-details-height: 200px; }" in html
        assert "body { font-family:" in html
        assert "display: flex; flex-direction: column; min-height: 0; max-height: var(--viewport-height);" in html
        assert "#left-panel { width: 100%; height: calc(var(--top-panel-header-height) + var(--top-details-height)); max-height: calc(var(--top-panel-header-height) + var(--top-details-height));" in html
        assert "#center { flex: 1; display: flex; position: relative; min-width: 0; min-height: 0; height: 0; overflow: hidden; }" in html
        assert "#graph-area { flex: 1; display: flex; flex-direction: column; position: relative; min-width: 0; min-height: 0; height: 100%; overflow: hidden; }" in html
        assert "#sidebar { flex: 0 0 var(--top-details-height); min-height: 0; max-height: var(--top-details-height);" in html
        assert "#sidebar > * { flex-shrink: 0; }" in html
        assert "max-height: min(360px, 34vh);" in html

    def test_resize_tracks_graph_container(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert "const rootEl = document.documentElement;" in html
        assert "const bodyEl = document.body;" in html
        assert "const leftPanel = document.getElementById('left-panel');" in html
        assert "const panelHeader = document.getElementById('panel-header');" in html
        assert "const centerPane = document.getElementById('center');" in html
        assert "const graphArea = document.getElementById('graph-area');" in html
        assert "function applyViewportHeight() {" in html
        assert "const hostWidth = window.__prefxplainHostWidth;" in html
        assert "const hostHeight = window.__prefxplainHostHeight;" in html
        assert "const headerHeight = Math.max(0, Math.ceil(panelHeader ? panelHeader.getBoundingClientRect().height : 0));" in html
        assert "const detailsHeight = Math.max(0, Math.min(200, vp.height - headerHeight));" in html
        assert "rootEl.style.setProperty('--viewport-height'" in html
        assert "rootEl.style.setProperty('--top-panel-header-height', `${headerHeight}px`);" in html
        assert "rootEl.style.setProperty('--top-details-height', `${detailsHeight}px`);" in html
        assert "centerPane.style.height = `${vp.height}px`;" in html
        assert "graphArea.style.height = `${vp.height}px`;" in html
        assert "const rect = graphArea.getBoundingClientRect();" in html
        assert "function syncViewport() {" in html
        assert "let fitZoomLevel = 1;" in html
        assert "let userZoomScale = 1;" in html
        assert "function computeFitZoom(width, height, nodeList) {" in html
        assert "function syncZoomScale(width, height) {" in html
        assert "function setViewportForWorldCenter(centerWorld, nextZoom, width, height) {" in html
        assert "fitZoomLevel * userZoomScale" in html
        assert "viewportWasManuallyMoved = false;" in html
        assert "setViewportForWorldCenter(" in html
        assert "clampPan();" in html
        assert "window.addEventListener('prefxplain-host-resize'" in html
        assert "new ResizeObserver(() => { syncViewport(); }).observe(graphArea);" in html
        assert "window.visualViewport.addEventListener('resize'" in html
        assert "function watchViewport() {" in html
        assert "window.requestAnimationFrame(watchViewport);" in html

    def test_default_view_uses_architecture_blocks(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert "function layoutBlocks(nodeList, edgeList) {" in html
        assert "function layoutGroupedBlocks(nodeList, edgeList) {" in html
        assert "function layoutExpandedBlock(nodeList) {" in html
        assert 'placeholder="Search... (/)"' in html
        assert "Click</span><span>Open a block or inspect a file</span>" in html
        assert "Double-click</span><span>Open the workflow diagram</span>" in html
        assert "Starting points" not in html
        assert "Shared building blocks" not in html
        assert "Feature logic" not in html
        assert "Shared workflows" not in html
        assert "Core utilities" not in html

    def test_group_interactions_search_inside_child_files(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert "n.childIds.some(childId => {" in html
        assert "const miniNodes = fitNodesForViewport().filter(n => isVisible(n));" in html

    def test_double_click_opens_workflow_overlay(self, simple_graph: Graph) -> None:
        html = render(simple_graph)
        assert 'id="flow-overlay"' in html
        assert 'id="flow-panel"' in html
        assert "function buildGroupFlowModel(groupNode) {" in html
        assert "function buildFileFlowModel(fileNode) {" in html
        assert "function buildFlowDiagram(config) {" in html
        assert "function renderFlowSvg(diagram) {" in html
        assert 'class="flow-svg"' in html
        assert "function openFlowOverlay(targetNode) {" in html
        assert "function closeFlowOverlay() {" in html
        assert "const DOUBLE_CLICK_DELAY = 220;" in html
        assert "function queueNodeClick(node) {" in html
        assert "if (pendingClickNode.id === node.id) {" in html
        assert "openFlowOverlay(node);" in html
