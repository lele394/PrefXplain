"""PrefXplain CLI — analyze and visualize your codebase.

Usage:
    prefxplain .                        # analyze current dir, open in IDE preview
    prefxplain /path/to/repo            # analyze a specific repo
    prefxplain . --output graph.html    # write to custom path
    prefxplain . --no-descriptions      # skip LLM step (fast, offline)
    prefxplain . --format matrix        # dependency matrix view
    prefxplain . --format mermaid       # Mermaid export
    prefxplain . --filter "src/**"      # only show files matching pattern
    prefxplain . --depth 2 --focus main.py  # 2 hops around main.py
    prefxplain . --check-cycles         # exit 1 if circular deps found
    prefxplain check                    # CI rule enforcement
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import __version__
from .analyzer import analyze
from .describer import describe, describe_groups
from .renderer import render, render_matrix

app = typer.Typer(
    name="prefxplain",
    help="Understand your codebase. Visual dependency maps + natural language descriptions.",
    add_completion=False,
    no_args_is_help=False,
)

console = Console()


def _in_ide() -> bool:
    """Detect if we're running inside VS Code or JetBrains terminal."""
    return bool(
        os.environ.get("VSCODE_PID")
        or os.environ.get("TERM_PROGRAM") == "vscode"
        or os.environ.get("TERMINAL_EMULATOR") == "JetBrains-JediTerm"
    )


def _ide_uri_scheme() -> str:
    """Best-effort URI scheme for the active IDE."""
    term_program = (os.environ.get("TERM_PROGRAM") or "").lower()
    if term_program == "cursor":
        return "cursor"
    if term_program == "windsurf":
        return "windsurf"
    if term_program == "vscode-insiders":
        return "vscode-insiders"
    return "vscode"


def _open_uri(uri: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if os.name == "nt":
            subprocess.Popen(
                ["cmd", "/c", "start", "", uri],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except OSError:
        return False
    return False


def _open_ide_preview(path: Path) -> bool:
    uri = (
        f"{_ide_uri_scheme()}://prefxplain.prefxplain-vscode/preview"
        f"?path={quote(str(path.resolve()))}"
    )
    return _open_uri(uri)


def _open_output(path: Path) -> None:
    """Open the output in the IDE preview when possible, otherwise in the browser."""
    resolved = str(path.resolve())
    # Always attempt the IDE preview URI first — the OS routes vscode:// to VS Code
    # if the extension is installed, regardless of whether we're inside the IDE terminal.
    if _open_ide_preview(path):
        return
    webbrowser.open(f"file://{resolved}")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"prefxplain {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    pass


@app.command(name="create")
def create(
    root: Path = typer.Argument(
        Path("."),
        help="Repository root to analyze. Defaults to current directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output HTML file path. Defaults to <root>/prefxplain.html.",
    ),
    no_descriptions: bool = typer.Option(
        False,
        "--no-descriptions",
        help="Skip LLM-generated descriptions (fast, works offline).",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        envvar="ANTHROPIC_API_KEY",
        help="API key (ANTHROPIC_API_KEY preferred, falls back to OPENAI_API_KEY).",
        show_default=False,
    ),
    api_base: Optional[str] = typer.Option(
        None,
        "--api-base",
        help="Custom API base URL (for Ollama, Groq, etc.).",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="LLM model for descriptions. Defaults to $ANTHROPIC_MODEL, then claude-sonnet-4-6.",
    ),
    max_files: int = typer.Option(
        500,
        "--max-files",
        help="Maximum files to analyze.",
    ),
    open_browser: bool = typer.Option(
        True,
        "--open/--no-open",
        help="Open the generated output in the IDE preview when available, otherwise in the browser.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Re-generate all LLM descriptions, ignoring cache.",
    ),
    detail: bool = typer.Option(
        False,
        "--detail",
        help="Generate paragraph-length descriptions instead of 1-2 sentences.",
    ),
    output_format: str = typer.Option(
        "html",
        "--format",
        help="Output format: html, matrix, mermaid, dot.",
    ),
    filter_pattern: Optional[str] = typer.Option(
        None,
        "--filter",
        help="Only include files matching this glob pattern (e.g. 'src/**/*.py').",
    ),
    focus: Optional[str] = typer.Option(
        None,
        "--focus",
        help="Focus on this file (used with --depth).",
    ),
    depth: Optional[int] = typer.Option(
        None,
        "--depth",
        help="Only show files within N hops of --focus file.",
    ),
    check_cycles: bool = typer.Option(
        False,
        "--check-cycles",
        help="Exit with code 1 if circular dependencies are found.",
    ),
) -> None:
    """Analyze a codebase and generate an interactive HTML dependency graph."""
    _run(
        root=root,
        output=output,
        no_descriptions=no_descriptions,
        api_key=api_key,
        api_base=api_base,
        model=model,
        max_files=max_files,
        open_browser=open_browser,
        force=force,
        detail=detail,
        output_format=output_format,
        filter_pattern=filter_pattern,
        focus=focus,
        depth=depth,
        check_cycles=check_cycles,
    )


@app.command(name="update")
def update(
    root: Path = typer.Argument(
        Path("."),
        help="Repository root to re-analyze.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output HTML file path. Defaults to <root>/prefxplain.html.",
    ),
    no_descriptions: bool = typer.Option(
        False,
        "--no-descriptions",
        help="Skip LLM-generated descriptions.",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        envvar="ANTHROPIC_API_KEY",
        show_default=False,
    ),
    api_base: Optional[str] = typer.Option(
        None,
        "--api-base",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="LLM model for descriptions. Defaults to $ANTHROPIC_MODEL, then claude-sonnet-4-6.",
    ),
    max_files: int = typer.Option(
        500,
        "--max-files",
    ),
    open_browser: bool = typer.Option(
        False,
        "--open/--no-open",
        help="Open the generated output in the IDE preview when available, otherwise in the browser.",
    ),
) -> None:
    """Re-analyze the codebase. Same as `create` but defaults to not opening the browser.

    Re-analysis is fast: the SQLite cache in describer.py only re-generates
    descriptions for files whose content hash changed since the last run.
    """
    _run(
        root=root,
        output=output,
        no_descriptions=no_descriptions,
        api_key=api_key,
        api_base=api_base,
        model=model,
        max_files=max_files,
        open_browser=open_browser,
        force=False,
        detail=False,
        output_format="html",
        filter_pattern=None,
        focus=None,
        depth=None,
        check_cycles=False,
    )


@app.command(name="check")
def check_cmd(
    root: Path = typer.Argument(
        Path("."),
        help="Repository root to check.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    config: Path = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to .prefxplain.yml config. Defaults to <root>/.prefxplain.yml.",
    ),
    max_files: int = typer.Option(
        500,
        "--max-files",
    ),
) -> None:
    """Check dependency rules (CI enforcement). Exits 1 on violations."""
    from .checker import check, format_violations, load_rules

    config_path = config or (root / ".prefxplain.yml")
    if not config_path.exists():
        console.print(f"[red]Config not found: {config_path}[/red]")
        console.print("Create a .prefxplain.yml with rules. Example:")
        console.print("[dim]rules:[/dim]")
        console.print("[dim]  - name: no-circular-deps[/dim]")
        console.print("[dim]  - name: max-imports[/dim]")
        console.print("[dim]    max: 10[/dim]")
        raise typer.Exit(1)

    console.print(f"[bold]PrefXplain Check[/bold] — {root}")
    rules = load_rules(config_path)
    console.print(f"  Loaded {len(rules)} rule(s) from {config_path.name}")

    graph = analyze(root, max_files=max_files)
    console.print(f"  Analyzed {len(graph.nodes)} files, {len(graph.edges)} edges")

    violations = check(graph, rules)
    console.print(format_violations(violations))

    errors = [v for v in violations if v.severity == "error"]
    if errors:
        raise typer.Exit(1)


@app.command(name="context")
def context_cmd(
    query: str = typer.Argument(..., help="Search term — file name, path, or concept"),
    root: Path = typer.Argument(
        Path("."),
        help="Repository root. Defaults to current directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    depth: int = typer.Option(2, "--depth", "-d", help="BFS hops around matching files"),
    tokens: int = typer.Option(2000, "--tokens", "-t", help="Approximate token budget for output"),
    from_json: Optional[Path] = typer.Option(
        None,
        "--from",
        help="Load from prefxplain.json (default: <root>/prefxplain.json).",
    ),
    max_files: int = typer.Option(500, "--max-files"),
) -> None:
    """Output token-efficient context for AI agents. Loads from prefxplain.json when available."""
    from .exporter import export_agent_context

    json_path = from_json or (root / "prefxplain.json")
    if json_path.exists():
        from .graph import Graph as _Graph
        graph = _Graph.load(json_path)
    else:
        console.print("[yellow]prefxplain.json not found — analyzing from source...[/yellow]")
        graph = analyze(root, max_files=max_files)
        graph.infer_roles()

    print(export_agent_context(graph, query, depth=depth, token_budget=tokens))


@app.command(name="mcp")
def mcp_cmd(
    root: Path = typer.Argument(
        Path("."),
        help="Repository root. Defaults to current directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    from_json: Optional[Path] = typer.Option(
        None,
        "--from",
        help="Load from prefxplain.json (default: <root>/prefxplain.json).",
    ),
) -> None:
    """Start MCP stdio server for AI agent integration. Requires: pip install 'prefxplain[agent]'"""
    from .mcp_server import serve
    serve(root, from_json)


@app.command(name="setup")
def setup_cmd(
    tool: Optional[str] = typer.Argument(
        None,
        help="AI tool to set up: claude-code, cursor, codex, copilot. Auto-detects if omitted.",
    ),
    project: bool = typer.Option(
        False,
        "--project",
        "-p",
        help="Install to current project only (not global).",
    ),
) -> None:
    """Install the /prefxplain slash command for your AI coding tool.

    Auto-detects Claude Code, Cursor, Codex, and Copilot CLI. Use --project
    to install for the current repo only instead of globally.
    """
    package_root = Path(__file__).parent
    cmd_source = package_root / "commands" / "prefxplain.md"
    cmd_content: Optional[str] = None
    copilot_plugin_dir = package_root / "copilot_plugin"
    copilot_plugin_manifest = copilot_plugin_dir / "plugin.json"

    def _load_cmd_content() -> str:
        nonlocal cmd_content
        if cmd_content is None:
            if not cmd_source.exists():
                console.print("[red]Command template not found in package. Reinstall prefxplain.[/red]")
                raise typer.Exit(1)
            cmd_content = cmd_source.read_text(encoding="utf-8")
        return cmd_content

    # Detect available tools
    detected: list[str] = []
    home = Path.home()
    if (home / ".claude").is_dir() or shutil.which("claude"):
        detected.append("claude-code")
    if (home / ".cursor").is_dir() or shutil.which("cursor"):
        detected.append("cursor")
    if shutil.which("codex"):
        detected.append("codex")
    if shutil.which("copilot"):
        detected.append("copilot")

    targets = [tool] if tool else detected
    if not targets:
        console.print("[yellow]No AI coding tools detected.[/yellow]")
        console.print("Supported: claude-code, cursor, codex, copilot")
        console.print("Run: [bold]prefxplain setup copilot[/bold] to install manually.")
        raise typer.Exit(1)

    installed: list[str] = []
    failed = False
    for t in targets:
        if t == "claude-code":
            if project:
                dest = Path.cwd() / ".claude" / "commands" / "prefxplain.md"
            else:
                dest = home / ".claude" / "commands" / "prefxplain.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(_load_cmd_content(), encoding="utf-8")
            scope = "project" if project else "global"
            installed.append(f"Claude Code ({scope}): {dest}")

        elif t == "cursor":
            # Cursor uses .cursor/rules/ for project-level instructions
            if project:
                dest = Path.cwd() / ".cursor" / "rules" / "prefxplain.mdc"
            else:
                dest = home / ".cursor" / "rules" / "prefxplain.mdc"
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Cursor uses .mdc format — wrap the command as a rule
            cursor_content = (
                "---\n"
                "description: Generate interactive dependency graph with /prefxplain\n"
                "globs: \n"
                "alwaysApply: false\n"
                "---\n\n"
                + _load_cmd_content()
            )
            dest.write_text(cursor_content, encoding="utf-8")
            scope = "project" if project else "global"
            installed.append(f"Cursor ({scope}): {dest}")

        elif t == "codex":
            # Codex uses AGENTS.md for project instructions
            dest = Path.cwd() / "AGENTS.md"
            section = (
                "\n\n## /prefxplain\n\n"
                "When the user asks to map, visualize, or explain the codebase architecture, "
                "run `prefxplain .` to generate an interactive HTML dependency graph.\n"
            )
            if dest.exists():
                existing = dest.read_text(encoding="utf-8")
                if "prefxplain" not in existing:
                    dest.write_text(existing + section, encoding="utf-8")
                    installed.append(f"Codex (appended to {dest})")
                else:
                    installed.append(f"Codex: already configured in {dest}")
            else:
                dest.write_text(f"# Agent Instructions{section}", encoding="utf-8")
                installed.append(f"Codex: created {dest}")

        elif t == "copilot":
            if not copilot_plugin_manifest.exists():
                console.print(
                    "[red]Copilot plugin assets missing from package. Reinstall prefxplain.[/red]"
                )
                failed = True
                if tool == "copilot":
                    raise typer.Exit(1)
                console.print("[yellow]Skipping Copilot setup.[/yellow]")
                continue

            copilot_bin = shutil.which("copilot")
            if not copilot_bin:
                console.print("[red]copilot CLI not found on PATH.[/red]")
                console.print(
                    "Install GitHub Copilot CLI, then run: [bold]prefxplain setup copilot[/bold]."
                )
                failed = True
                if tool == "copilot":
                    raise typer.Exit(1)
                console.print("[yellow]Skipping Copilot setup.[/yellow]")
                continue

            if project:
                console.print(
                    "[yellow]Copilot setup uses global plugins; ignoring --project.[/yellow]"
                )

            try:
                result = subprocess.run(
                    [copilot_bin, "plugin", "install", str(copilot_plugin_dir)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except subprocess.TimeoutExpired:
                console.print("[red]Copilot plugin install timed out.[/red]")
                failed = True
                if tool == "copilot":
                    raise typer.Exit(1)
                console.print("[yellow]Skipping Copilot setup.[/yellow]")
                continue
            if result.returncode != 0:
                console.print("[red]Failed to install Copilot plugin.[/red]")
                if result.stderr.strip():
                    console.print(f"[dim]{result.stderr.strip()}[/dim]")
                failed = True
                if tool == "copilot":
                    raise typer.Exit(1)
                console.print("[yellow]Skipping Copilot setup.[/yellow]")
                continue

            installed.append(f"Copilot CLI (global plugin): {copilot_plugin_manifest}")

        else:
            console.print(f"[yellow]Unknown tool: {t}. Skipping.[/yellow]")

    if installed:
        console.print("[bold green]Setup complete![/bold green]")
        for item in installed:
            console.print(f"  [green]\u2713[/green] {item}")
        console.print()
        console.print("Now type [bold]/prefxplain[/bold] in your AI tool to generate a codebase map.")
    else:
        console.print("[yellow]Nothing to install.[/yellow]")
        if failed:
            raise typer.Exit(1)


def _run(
    root: Path,
    output: Optional[Path],
    no_descriptions: bool,
    api_key: Optional[str],
    api_base: Optional[str],
    model: str,
    max_files: int,
    open_browser: bool,
    force: bool,
    detail: bool,
    output_format: str,
    filter_pattern: Optional[str],
    focus: Optional[str],
    depth: Optional[int],
    check_cycles: bool,
) -> None:
    """Shared implementation for create and update commands.

    Both commands run the full pipeline: analyze, describe, render. Re-runs are
    fast because describer.py caches by (file_path, content_hash) in SQLite.
    """
    fmt = output_format.lower()
    default_ext = {
        "html": ".html",
        "matrix": ".html",
        "mermaid": ".md",
        "dot": ".dot",
    }
    ext = default_ext.get(fmt, ".html")
    output_path = output or (root / f"prefxplain{ext}")

    console.print(
        Panel(
            Text.from_markup(
                f"[bold]PrefXplain[/bold] [dim]v{__version__}[/dim]\n"
                f"Analyzing [cyan]{root}[/cyan]"
            ),
            expand=False,
        )
    )

    # Step 1: Static analysis
    console.print("[bold blue]1/3[/bold blue] Parsing files and extracting imports...")
    graph = analyze(root, max_files=max_files)

    # Apply filter
    if filter_pattern:
        graph = graph.filter_subgraph(filter_pattern)
        console.print(f"    [dim]Filtered to {len(graph.nodes)} files matching '{filter_pattern}'[/dim]")

    # Apply depth focus
    if focus and depth is not None:
        graph = graph.depth_subgraph(focus, depth)
        console.print(f"    [dim]Focused on {len(graph.nodes)} files within {depth} hops of '{focus}'[/dim]")
    elif focus and depth is None:
        console.print("[yellow]    \u26a0 --focus requires --depth. Ignoring --focus.[/yellow]")

    # Infer architectural roles
    graph.infer_roles()
    graph.infer_groups()

    console.print(
        f"    [green]\u2713[/green] Found {len(graph.nodes)} files, {len(graph.edges)} import edges"
        f" ({', '.join(graph.metadata.languages or ['?'])})"
    )

    # Report cycles
    cycles = graph.find_cycles()
    if cycles:
        console.print(
            f"    [yellow]\u26a0[/yellow] {len(cycles)} circular dependency chain(s) detected"
        )
        for cycle in cycles[:3]:
            chain = " \u2192 ".join(cycle) + " \u2192 " + cycle[0]
            console.print(f"      [dim]{chain}[/dim]")
        if len(cycles) > 3:
            console.print(f"      [dim]+{len(cycles) - 3} more[/dim]")

    # Step 2: LLM descriptions
    # Always preserve prior descriptions first — so a failed LLM call or
    # --no-descriptions never silently wipes descriptions from a previous run.
    prior_json_path = (output or (root / f"prefxplain{ext}")).with_suffix(".json")
    if prior_json_path.exists():
        try:
            from .diagram import is_generated_group_label
            from .graph import Graph as _Graph

            prior_graph = _Graph.load(prior_json_path)
            prior_descs = {n.id: n for n in prior_graph.nodes if n.description}
            preserved = 0
            for node in graph.nodes:
                prior = prior_descs.get(node.id)
                if prior:
                    node.description = prior.description
                    # Also restore per-symbol descriptions
                    old_sym = {s.name: s.description for s in prior.symbols if s.description}
                    for sym in node.symbols:
                        if sym.name in old_sym:
                            sym.description = old_sym[sym.name]
                    if prior.group and not is_generated_group_label(prior.group):
                        node.group = prior.group
                    preserved += 1
            if preserved:
                console.print(
                    f"    [dim]Preserved {preserved} description(s) from previous run[/dim]"
                )
        except Exception:  # noqa: BLE001 — graceful degradation
            pass

    if no_descriptions or fmt in ("mermaid", "dot"):
        console.print("[bold blue]2/3[/bold blue] Skipping descriptions (preserved from cache)")
    else:
        console.print("[bold blue]2/3[/bold blue] Generating natural language descriptions...")
        graph = describe(
            graph,
            root=root,
            api_key=api_key,
            api_base=api_base,
            model=model,
            force=force,
            detail=detail,
        )
        if not detail:
            graph = describe_groups(
                graph,
                root=root,
                api_key=api_key,
                api_base=api_base,
                model=model,
                force=force,
            )

    # Step 3: Render output
    console.print(f"[bold blue]3/3[/bold blue] Rendering {fmt} output...")

    if fmt == "matrix":
        render_matrix(graph, output_path=output_path)
    elif fmt == "mermaid":
        from .exporter import export_mermaid
        mermaid_str = export_mermaid(graph)
        content = f"```mermaid\n{mermaid_str}```\n"
        output_path.write_text(content, encoding="utf-8")
    elif fmt == "dot":
        from .exporter import export_dot
        dot_str = export_dot(graph)
        output_path.write_text(dot_str, encoding="utf-8")
    else:
        render(graph, output_path=output_path)

    console.print(f"    [green]\u2713[/green] Written to [cyan]{output_path}[/cyan]")

    # Save graph.json alongside for programmatic access
    json_path = output_path.with_suffix(".json")
    graph.save(json_path)
    console.print(f"    [green]\u2713[/green] Graph data at [cyan]{json_path}[/cyan]")

    # Print metrics summary
    metrics = graph.metrics()
    console.print()
    console.print(
        f"[bold green]Done![/bold green] {metrics['total_files']} files, "
        f"{metrics['total_edges']} edges, "
        f"{metrics['components']} component(s), "
        f"{metrics['cycles']} cycle(s)"
    )

    if open_browser and fmt in ("html", "matrix"):
        _open_output(output_path)

    if check_cycles and cycles:
        console.print(f"\n[red bold]FAIL:[/red bold] {len(cycles)} circular dependency chain(s) found.")
        raise typer.Exit(1)


def entry_point() -> None:
    """Entry point that handles bare `prefxplain <path>` without a subcommand.

    If the first arg looks like a path or is missing, prepend `create` so typer
    routes correctly. This makes `prefxplain .` work as shorthand for
    `prefxplain create .`.
    """
    args = sys.argv[1:]
    subcommands = {"create", "update", "check", "context", "mcp", "setup", "--help", "-h", "--version", "-v"}
    if args and args[0] not in subcommands:
        sys.argv.insert(1, "create")
    app()


if __name__ == "__main__":
    entry_point()
