"""PrefXplain CLI — analyze and visualize your codebase.

Usage:
    prefxplain .                        # analyze current dir, open in browser
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

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import __version__
from .analyzer import analyze
from .describer import describe
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


def _open_output(path: Path) -> None:
    """Open the output file in the IDE tab if possible, otherwise in the browser."""
    resolved = str(path.resolve())
    if _in_ide() and shutil.which("code"):
        subprocess.Popen(["code", resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
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
    model: str = typer.Option(
        "claude-haiku-4-5-20251001",
        "--model",
        help="LLM model for descriptions.",
    ),
    max_files: int = typer.Option(
        500,
        "--max-files",
        help="Maximum files to analyze.",
    ),
    open_browser: bool = typer.Option(
        True,
        "--open/--no-open",
        help="Open the generated HTML in your browser.",
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
    model: str = typer.Option(
        "claude-haiku-4-5-20251001",
        "--model",
    ),
    max_files: int = typer.Option(
        500,
        "--max-files",
    ),
    open_browser: bool = typer.Option(
        False,
        "--open/--no-open",
        help="Open the generated HTML in your browser after update.",
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
    subcommands = {"create", "update", "check", "context", "mcp", "--help", "-h", "--version", "-v"}
    if args and args[0] not in subcommands:
        sys.argv.insert(1, "create")
    app()


if __name__ == "__main__":
    entry_point()
