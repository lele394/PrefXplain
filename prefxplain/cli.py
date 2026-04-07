"""PrefXplain CLI — analyze and visualize your codebase.

Usage:
    prefxplain .                        # analyze current dir, open in browser
    prefxplain /path/to/repo            # analyze a specific repo
    prefxplain . --output graph.html    # write to custom path
    prefxplain . --no-descriptions      # skip LLM step (fast, offline)
    prefxplain update                   # re-analyze changed files only
"""

from __future__ import annotations

import os
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
from .graph import Graph
from .renderer import render

app = typer.Typer(
    name="prefxplain",
    help="Understand your codebase. Visual dependency maps + natural language descriptions.",
    add_completion=False,
    no_args_is_help=False,
)

console = Console()


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
        envvar="OPENAI_API_KEY",
        help="OpenAI-compatible API key.",
        show_default=False,
    ),
    api_base: Optional[str] = typer.Option(
        None,
        "--api-base",
        help="Custom API base URL (for Ollama, Groq, etc.).",
    ),
    model: str = typer.Option(
        "gpt-4o-mini",
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
        update_only=False,
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
        envvar="OPENAI_API_KEY",
        show_default=False,
    ),
    api_base: Optional[str] = typer.Option(
        None,
        "--api-base",
    ),
    model: str = typer.Option(
        "gpt-4o-mini",
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
    """Re-analyze the codebase, updating only changed files (uses cache)."""
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
        update_only=True,
    )


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
    update_only: bool,
) -> None:
    """Shared implementation for create and update commands."""
    output_path = output or (root / "prefxplain.html")

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

    console.print(
        f"    [green]✓[/green] Found {len(graph.nodes)} files, {len(graph.edges)} import edges"
        f" ({', '.join(graph.metadata.languages or ['?'])})"
    )

    # Step 2: LLM descriptions
    if no_descriptions:
        console.print("[bold blue]2/3[/bold blue] Skipping descriptions (--no-descriptions)")
    else:
        console.print("[bold blue]2/3[/bold blue] Generating natural language descriptions...")
        graph = describe(
            graph,
            root=root,
            api_key=api_key,
            api_base=api_base,
            model=model,
            force=force,
        )

    # Step 3: Render HTML
    console.print("[bold blue]3/3[/bold blue] Rendering interactive graph...")
    render(graph, output_path=output_path)
    console.print(f"    [green]✓[/green] Written to [cyan]{output_path}[/cyan]")

    # Also save graph.json alongside the HTML for programmatic access
    json_path = output_path.with_suffix(".json")
    graph.save(json_path)
    console.print(f"    [green]✓[/green] Graph data at [cyan]{json_path}[/cyan]")

    console.print()
    console.print(f"[bold green]Done![/bold green] {len(graph.nodes)} files mapped.")

    if open_browser:
        webbrowser.open(f"file://{output_path.resolve()}")


# Allow `prefxplain .` (no subcommand) as shorthand for `prefxplain create .`
@app.command(name="map", hidden=True)
def map_cmd(
    root: Path = typer.Argument(Path(".")),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    no_descriptions: bool = typer.Option(False, "--no-descriptions"),
    api_key: Optional[str] = typer.Option(None, "--api-key", envvar="OPENAI_API_KEY"),
    api_base: Optional[str] = typer.Option(None, "--api-base"),
    model: str = typer.Option("gpt-4o-mini", "--model"),
    max_files: int = typer.Option(500, "--max-files"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Alias for create (hidden)."""
    create(
        root=root,
        output=output,
        no_descriptions=no_descriptions,
        api_key=api_key,
        api_base=api_base,
        model=model,
        max_files=max_files,
        open_browser=open_browser,
        force=force,
    )


def entry_point() -> None:
    """Entry point that handles bare `prefxplain <path>` without a subcommand."""
    # If first arg looks like a path or is missing, route to `create`
    args = sys.argv[1:]
    subcommands = {"create", "update", "map", "--help", "-h", "--version", "-v"}
    if args and args[0] not in subcommands:
        # Prepend "create" so typer routes correctly
        sys.argv.insert(1, "create")
    app()


if __name__ == "__main__":
    entry_point()
