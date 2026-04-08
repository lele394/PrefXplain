"""LLM-powered file description generator with SQLite cache.

Generates natural-language descriptions for each file node AND its symbols
(functions, classes). Caches by (file_path, SHA-256 of file content).

Default model: claude-haiku-4-5-20251001 (fast, cheap).
Requires ANTHROPIC_API_KEY or OPENAI_API_KEY (or --api-key flag).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .graph import Graph, Node, Symbol

console = Console()

CACHE_DIR = Path.home() / ".prefxplain"
CACHE_DB = CACHE_DIR / "cache.db"

# Default: Claude Haiku (fast + cheap for codebase analysis)
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_BASE = "https://api.anthropic.com/v1"

# v2 system prompt — returns JSON with file description + per-symbol descriptions
SYSTEM_PROMPT_V2 = """\
You are a senior software engineer explaining code to a first-year CS student.
Given a source file, write plain-language descriptions in JSON format.
Rules:
- "file": 1-2 sentences saying what this file does in plain language. No jargon. \
Start with a verb (e.g. "Handles...", "Reads...", "Manages..."). Do not mention the filename.
- "symbols": for each symbol name, write 3-6 words saying what it does \
(e.g. "run": "starts the web server", "User": "stores user account data"). \
Only include functions and classes, not imports or variables.
Respond with valid JSON only, no markdown fences.
Example: {"file": "Manages database connections and query helpers.", "symbols": {"connect": "opens a database connection", "run_query": "executes SQL and returns rows"}}
"""

SYSTEM_PROMPT_DETAIL = """\
You are a senior software engineer writing thorough documentation.
Given a source file's path, its top-level symbols, and a few lines of content,
write a detailed paragraph (4-6 sentences) describing:
1. What this file does and its primary responsibility
2. Key functions/classes and what they provide
3. How it fits into the broader system architecture
4. Any notable patterns, dependencies, or design decisions
Be specific. Do not repeat the filename. Write in present tense.
"""

USER_PROMPT_V2 = """\
File: {file_path}
Language: {language}
Functions/classes: {symbols}

First {preview_lines} lines:
```
{preview}
```

Respond with JSON as described."""

USER_PROMPT_DETAIL = """\
File: {file_path}
Language: {language}
Symbols: {symbols}

First {preview_lines} lines:
```
{preview}
```

Describe what this file does in a detailed paragraph (4-6 sentences)."""


def _init_cache() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    # v1: plain text descriptions (kept for backward compat)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS descriptions (
            file_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            description TEXT NOT NULL,
            PRIMARY KEY (file_path, content_hash)
        )
    """)
    # v2: JSON blob with file description + per-symbol descriptions
    conn.execute("""
        CREATE TABLE IF NOT EXISTS descriptions_v2 (
            file_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (file_path, content_hash)
        )
    """)
    conn.commit()
    return conn


def _content_hash(file_path: Path) -> str:
    try:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _get_cached(conn: sqlite3.Connection, file_path: str, content_hash: str) -> str | None:
    row = conn.execute(
        "SELECT description FROM descriptions WHERE file_path = ? AND content_hash = ?",
        (file_path, content_hash),
    ).fetchone()
    return row[0] if row else None


def _set_cached(conn: sqlite3.Connection, file_path: str, content_hash: str, description: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO descriptions (file_path, content_hash, description) VALUES (?, ?, ?)",
        (file_path, content_hash, description),
    )
    conn.commit()


def _file_preview(root: Path, node: Node, lines: int = 60) -> str:
    fpath = root / node.id
    try:
        if not fpath.resolve().is_relative_to(root.resolve()):
            return ""  # path traversal attempt
        text = fpath.read_text(encoding="utf-8", errors="ignore")
        return "\n".join(text.splitlines()[:lines])
    except OSError:
        return ""


def _make_prompt_v2(node: Node, root: Path) -> str:
    symbols = ", ".join(
        s.name for s in node.symbols[:20]
        if s.kind in ("function", "class")
    ) or "none"
    preview = _file_preview(root, node, lines=60)
    return USER_PROMPT_V2.format(
        file_path=node.id,
        language=node.language,
        symbols=symbols,
        preview=preview,
        preview_lines=60,
    )


def _make_prompt_detail(node: Node, root: Path) -> str:
    symbols = ", ".join(s.name for s in node.symbols[:20]) or "none"
    preview = _file_preview(root, node, lines=120)
    return USER_PROMPT_DETAIL.format(
        file_path=node.id,
        language=node.language,
        symbols=symbols,
        preview=preview,
        preview_lines=120,
    )


def _get_cached_v2(conn: sqlite3.Connection, file_path: str, content_hash: str) -> dict | None:
    row = conn.execute(
        "SELECT data FROM descriptions_v2 WHERE file_path = ? AND content_hash = ?",
        (file_path, content_hash),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None


def _set_cached_v2(conn: sqlite3.Connection, file_path: str, content_hash: str, data: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO descriptions_v2 (file_path, content_hash, data) VALUES (?, ?, ?)",
        (file_path, content_hash, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()


def describe(
    graph: Graph,
    root: Path,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str = DEFAULT_MODEL,
    force: bool = False,
    detail: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Graph:
    """Fill in descriptions for all nodes and their symbols.

    Uses SQLite cache — only calls the LLM for files that changed since last run.
    Defaults to claude-haiku-4-5-20251001 via Anthropic API (fast and cheap).

    Args:
        graph: Graph with nodes to describe.
        root: Repo root path (for reading file content).
        api_key: API key. Falls back to ANTHROPIC_API_KEY then OPENAI_API_KEY env vars.
        api_base: Optional API base URL. Defaults to Anthropic's endpoint.
        model: LLM model name. Default: claude-haiku-4-5-20251001.
        force: Re-generate all descriptions, ignoring cache.
        detail: If True, generate paragraph-length file descriptions (no symbol descriptions).
        progress_callback: Called with (current, total) for custom progress reporting.

    Returns:
        The same graph with descriptions filled in on nodes and symbols.
    """
    try:
        from openai import OpenAI
    except ImportError:
        console.print("[yellow]openai package not installed. Run: pip install openai[/yellow]")
        console.print("[yellow]Skipping descriptions. Use --no-descriptions to suppress this warning.[/yellow]")
        return graph

    # Resolve API key: explicit > ANTHROPIC_API_KEY > OPENAI_API_KEY
    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")

    # Resolve base URL: explicit > Anthropic default (if Anthropic key in use)
    resolved_base = api_base
    if not resolved_base and (api_key or os.environ.get("ANTHROPIC_API_KEY")):
        resolved_base = ANTHROPIC_BASE

    client_kwargs: dict = {}
    if resolved_key:
        client_kwargs["api_key"] = resolved_key
    if resolved_base:
        client_kwargs["base_url"] = resolved_base

    try:
        client = OpenAI(**client_kwargs)
    except Exception as e:
        console.print(f"[yellow]Could not initialize LLM client: {e}[/yellow]")
        console.print("[yellow]Skipping descriptions. Set ANTHROPIC_API_KEY or use --no-descriptions.[/yellow]")
        return graph

    conn = _init_cache()
    try:
        return _describe_with_conn(
            conn, graph, root, client, model, force, detail, progress_callback,
        )
    finally:
        conn.close()


def _apply_v2_data(node: Node, data: dict) -> None:
    """Apply a v2 JSON response (file desc + symbol descs) to a node."""
    node.description = data.get("file", "").strip()
    sym_descs: dict[str, str] = data.get("symbols", {})
    for sym in node.symbols:
        if sym.name in sym_descs:
            sym.description = str(sym_descs[sym.name]).strip()


def _describe_with_conn(
    conn: sqlite3.Connection,
    graph: Graph,
    root: Path,
    client: object,
    model: str,
    force: bool,
    detail: bool,
    progress_callback: Callable[[int, int], None] | None,
) -> Graph:
    nodes_to_describe = [n for n in graph.nodes if not n.description or force]
    total = len(nodes_to_describe)

    if total == 0:
        return graph

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Generating descriptions...", total=total)

        for i, node in enumerate(nodes_to_describe):
            fpath = root / node.id
            content_hash = _content_hash(fpath)
            cache_key = f"{node.id}:detail" if detail else node.id

            if not force and content_hash:
                if detail:
                    # detail mode: check v1 cache for plain text
                    cached = _get_cached(conn, cache_key, content_hash)
                    if cached:
                        node.description = cached
                        progress.advance(task)
                        if progress_callback:
                            progress_callback(i + 1, total)
                        continue
                else:
                    # normal mode: check v2 cache (JSON with symbol descriptions)
                    cached_data = _get_cached_v2(conn, cache_key, content_hash)
                    if cached_data:
                        _apply_v2_data(node, cached_data)
                        progress.advance(task)
                        if progress_callback:
                            progress_callback(i + 1, total)
                        continue

            # Call LLM
            try:
                if detail:
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT_DETAIL},
                            {"role": "user", "content": _make_prompt_detail(node, root)},
                        ],
                        max_tokens=400,
                        temperature=0.3,
                    )
                    content = response.choices[0].message.content if response.choices else None
                    node.description = content.strip() if content else ""
                    if content_hash and node.description:
                        _set_cached(conn, cache_key, content_hash, node.description)
                else:
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT_V2},
                            {"role": "user", "content": _make_prompt_v2(node, root)},
                        ],
                        max_tokens=300,
                        temperature=0.2,
                    )
                    content = response.choices[0].message.content if response.choices else None
                    raw = content.strip() if content else "{}"
                    # Strip markdown fences if the model wrapped in ```json
                    if raw.startswith("```"):
                        raw = raw.split("```", 2)[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                        raw = raw.strip()
                    try:
                        data = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        # Fallback: treat as plain text file description
                        data = {"file": raw, "symbols": {}}
                    _apply_v2_data(node, data)
                    if content_hash and node.description:
                        _set_cached_v2(conn, cache_key, content_hash, data)
            except Exception as e:
                console.print(f"[yellow]  Warning: LLM failed for {node.id}: {e}[/yellow]")

            progress.advance(task)
            if progress_callback:
                progress_callback(i + 1, total)

    return graph
