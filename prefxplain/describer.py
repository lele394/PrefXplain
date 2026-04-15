"""LLM-powered file description generator with SQLite cache.

Generates natural-language descriptions for each file node AND its symbols
(functions, classes). Caches by (file_path, SHA-256 of file content).

Default model: claude-sonnet-4-6 (strong descriptions out of the box).
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

# Default: Claude Sonnet 4.6 — better descriptions than Haiku with acceptable latency/cost
DEFAULT_MODEL = "claude-sonnet-4-6"
ANTHROPIC_BASE = "https://api.anthropic.com/v1"


def _resolve_model(model: str | None) -> str:
    """Pick the model to use for a describe call.

    Priority: explicit argument > $ANTHROPIC_MODEL env var > DEFAULT_MODEL.
    This lets Claude Code sessions (which set ANTHROPIC_MODEL) flow their
    currently-selected model into the describer without extra config.
    """
    if model:
        return model
    env_model = os.environ.get("ANTHROPIC_MODEL")
    if env_model:
        return env_model
    return DEFAULT_MODEL

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
- "highlights": up to 3 CONCRETE, codebase-specific facts that make this file \
interesting. List proper nouns: named integrations, third-party tools, model names, \
hyperparameters, cloud providers, protocols, file formats, CLI tools, exact thresholds. \
NOT adjectives or architectural platitudes. If nothing concrete exists, return []. \
GOOD: ["Claude Code integration", "Codex CLI support", "SQLite cache"]. \
BAD: ["handles user commands", "entry point for CLI", "well-structured module"]. \
Empty is better than generic.
- "flowchart": a flowchart showing the main logic of the file. \
Use 3-7 nodes. Each node has "id" (string "1","2"...), "label" (3-6 words describing the step), \
"type" ("start", "end", "decision", or "step"), and "description" (1 plain-English sentence \
explaining what happens here — like you're telling a smart friend who doesn't know this codebase). \
Each edge has "from" and "to" (node ids) and "label" (condition text for decisions, or "" for unconditional). \
The flowchart should reflect the ACTUAL logic flow, not be generic. \
Decision nodes MUST have at least 2 outgoing edges with meaningful condition labels (e.g. "yes"/"no", "found"/"not found", "valid"/"invalid"). \
Start with one "start" node and end with one "end" node.
Respond with valid JSON only, no markdown fences.
Example: {"file": "Manages database connections.", "symbols": {"connect": "opens a database connection"}, \
"highlights": ["PostgreSQL driver", "connection pooling via pgbouncer", "SSL required"], \
"flowchart": {"nodes": [{"id": "1", "label": "Receive query request", "type": "start", \
"description": "Someone wants to run a database query."}, \
{"id": "2", "label": "Connection pool available?", "type": "decision", \
"description": "Checks if there's already an open connection we can reuse instead of creating a new one."}, \
{"id": "3", "label": "Reuse existing connection", "type": "step", \
"description": "Grabs an idle connection from the pool — faster than opening a new one."}, \
{"id": "4", "label": "Create new connection", "type": "step", \
"description": "Opens a fresh connection to the database since the pool was empty."}, \
{"id": "5", "label": "Return query results", "type": "end", \
"description": "Runs the SQL, sends back the rows, and returns the connection to the pool for reuse."}], \
"edges": [{"from": "1", "to": "2", "label": ""}, \
{"from": "2", "to": "3", "label": "available"}, \
{"from": "2", "to": "4", "label": "empty"}, \
{"from": "3", "to": "5", "label": ""}, \
{"from": "4", "to": "5", "label": ""}]}}
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
    # group_highlights: cached synthesis per group keyed by content signature
    conn.execute("""
        CREATE TABLE IF NOT EXISTS group_highlights (
            group_label TEXT NOT NULL,
            signature TEXT NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (group_label, signature)
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


# Backward-compatible alias used by tests and older callers.
def _make_prompt(node: Node, root: Path) -> str:
    return _make_prompt_v2(node, root)


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


SYSTEM_PROMPT_GROUP = """\
You are a senior software engineer summarizing a group of related files for a \
first-year CS student.
Given the group name and a list of its files (with short descriptions and any \
highlights extracted from each file), output JSON: {"highlights": [...]}.
The highlights list contains up to 3 CONCRETE, group-wide facts that a user would \
find genuinely interesting about THIS group in THIS codebase.
Rules:
- Look for patterns that span multiple files: integrations, supported tools, model \
names, hyperparameters, cloud providers, protocols, file formats, exact versions.
- Prefer proper nouns over adjectives. GOOD: ["supports Claude Code + Codex", \
"SQLite-backed cache", "ANTHROPIC_API_KEY env var"]. BAD: ["handles CLI commands", \
"well-organized", "modular design"].
- If nothing concrete and group-worthy is visible, return []. Empty is better than generic.
- Each highlight must be ≤60 characters.
- Respond with valid JSON only, no markdown fences.
"""


def _group_signature(label: str, children: list[dict]) -> str:
    """Build a content-hash signature for a group so we can cache its highlights."""
    payload = json.dumps(
        {"label": label, "children": sorted((c.get("id", ""), c.get("hash", "")) for c in children)},
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_cached_group(
    conn: sqlite3.Connection, label: str, signature: str,
) -> list[str] | None:
    row = conn.execute(
        "SELECT data FROM group_highlights WHERE group_label = ? AND signature = ?",
        (label, signature),
    ).fetchone()
    if not row:
        return None
    try:
        parsed = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, list) else None


def _set_cached_group(
    conn: sqlite3.Connection, label: str, signature: str, highlights: list[str],
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO group_highlights (group_label, signature, data) VALUES (?, ?, ?)",
        (label, signature, json.dumps(highlights, ensure_ascii=False)),
    )
    conn.commit()


def describe_groups(
    graph: Graph,
    root: Path,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    force: bool = False,
) -> Graph:
    """Synthesize group-level highlights by reading child file descriptions.

    Groups with fewer than 2 member files are skipped — not enough signal.
    Results are written to graph.metadata.group_highlights and cached in sqlite
    keyed by group label + hash of child file contents.
    """
    model = _resolve_model(model)
    try:
        from openai import OpenAI
    except ImportError:
        return graph

    graph.infer_groups()

    # Collect members per group label
    members_by_group: dict[str, list[Node]] = {}
    for node in graph.nodes:
        if not node.group:
            continue
        members_by_group.setdefault(node.group, []).append(node)

    eligible = {label: nodes for label, nodes in members_by_group.items() if len(nodes) >= 2}
    if not eligible:
        return graph

    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
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
        console.print(f"[yellow]Could not initialize LLM client for group highlights: {e}[/yellow]")
        return graph

    conn = _init_cache()
    try:
        if not getattr(graph.metadata, "group_highlights", None):
            graph.metadata.group_highlights = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Synthesizing group highlights...", total=len(eligible))

            for label, nodes in sorted(eligible.items()):
                children_payload = []
                for n in nodes:
                    children_payload.append(
                        {
                            "id": n.id,
                            "hash": _content_hash(root / n.id),
                            "description": n.description,
                            "highlights": n.highlights,
                        }
                    )
                signature = _group_signature(label, children_payload)

                if not force:
                    cached = _get_cached_group(conn, label, signature)
                    if cached is not None:
                        graph.metadata.group_highlights[label] = cached
                        progress.advance(task)
                        continue

                # Trim payload for prompt: top 12 files, description + highlights only
                trimmed = [
                    {
                        "file": c["id"],
                        "description": c["description"],
                        "highlights": c["highlights"],
                    }
                    for c in children_payload[:12]
                ]
                user_prompt = (
                    f'Group name: "{label}"\n'
                    f"Files in group: {len(nodes)}\n\n"
                    f"Children (JSON):\n{json.dumps(trimmed, ensure_ascii=False, indent=2)}\n\n"
                    'Respond with {"highlights": [...]} as described.'
                )

                highlights: list[str] = []
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT_GROUP},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=200,
                        temperature=0.2,
                    )
                    content = response.choices[0].message.content if response.choices else None
                    raw = content.strip() if content else "{}"
                    if raw.startswith("```"):
                        raw = raw.split("```", 2)[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                        raw = raw.strip()
                    try:
                        parsed = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        parsed = {}
                    highlights = _clean_highlights(parsed.get("highlights") if isinstance(parsed, dict) else None)
                except Exception as e:
                    console.print(f"[yellow]  Warning: group highlight call failed for {label}: {e}[/yellow]")
                    highlights = []

                graph.metadata.group_highlights[label] = highlights
                _set_cached_group(conn, label, signature, highlights)
                progress.advance(task)
    finally:
        conn.close()

    return graph


def describe(
    graph: Graph,
    root: Path,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    force: bool = False,
    detail: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Graph:
    """Fill in descriptions for all nodes and their symbols.

    Uses SQLite cache — only calls the LLM for files that changed since last run.
    Defaults to claude-sonnet-4-6 via Anthropic API.

    Args:
        graph: Graph with nodes to describe.
        root: Repo root path (for reading file content).
        api_key: API key. Falls back to ANTHROPIC_API_KEY then OPENAI_API_KEY env vars.
        api_base: Optional API base URL. Defaults to Anthropic's endpoint.
        model: LLM model name. Default: claude-sonnet-4-6.
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

    resolved_model = _resolve_model(model)
    conn = _init_cache()
    try:
        return _describe_with_conn(
            conn, graph, root, client, resolved_model, force, detail, progress_callback,
        )
    finally:
        conn.close()


def _validate_flowchart(fc: dict | None) -> dict | None:
    """Validate and sanitize an AI-generated flowchart structure."""
    if not fc or not isinstance(fc, dict):
        return None
    nodes = fc.get("nodes")
    edges = fc.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    if len(nodes) < 2 or len(nodes) > 12:
        return None
    valid_types = {"start", "end", "decision", "step", "entry", "process", "analysis", "data", "external", "test"}
    node_ids: set[str] = set()
    clean_nodes = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id", ""))
        label = str(n.get("label", ""))
        ntype = str(n.get("type", "step"))
        shape = str(n.get("shape", ntype or "step"))
        description = str(n.get("description", ""))
        if not nid or not label:
            continue
        if ntype not in valid_types:
            ntype = "step"
        if shape not in valid_types:
            shape = ntype
        node_ids.add(nid)
        clean_node = {"id": nid, "label": label, "type": ntype, "shape": shape}
        if description:
            clean_node["description"] = description
        clean_nodes.append(clean_node)
    clean_edges = []
    for e in edges:
        if not isinstance(e, dict):
            continue
        efrom = str(e.get("from", ""))
        eto = str(e.get("to", ""))
        elabel = str(e.get("label", ""))
        if efrom in node_ids and eto in node_ids:
            clean_edges.append({"from": efrom, "to": eto, "label": elabel})
    if len(clean_nodes) < 2 or len(clean_edges) < 1:
        return None
    return {"nodes": clean_nodes, "edges": clean_edges}


MAX_HIGHLIGHTS = 3
HIGHLIGHT_MAX_LEN = 60

_GENERIC_HIGHLIGHT_TOKENS = (
    "handles ", "manages ", "provides ", "implements ", "contains ",
    "well-", "clean ", "modular ", "robust ", "comprehensive",
    "entry point", "main module", "core module", "utility module",
)


def _clean_highlights(raw: object) -> list[str]:
    """Validate and sanitize an AI-generated highlights list.

    Drops non-strings, strips, caps length, filters empty/generic entries,
    and truncates to MAX_HIGHLIGHTS.
    """
    if not isinstance(raw, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip().strip("-•*·").strip()
        if not text:
            continue
        if len(text) > HIGHLIGHT_MAX_LEN:
            text = text[: HIGHLIGHT_MAX_LEN - 1].rstrip() + "\u2026"
        lowered = text.lower()
        if any(tok in lowered for tok in _GENERIC_HIGHLIGHT_TOKENS):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(text)
        if len(cleaned) >= MAX_HIGHLIGHTS:
            break
    return cleaned


def _apply_v2_data(node: Node, data: dict) -> None:
    """Apply a v2 JSON response (file desc + symbol descs + flowchart) to a node."""
    node.description = data.get("file", "").strip()
    sym_descs: dict[str, str] = data.get("symbols", {})
    for sym in node.symbols:
        if sym.name in sym_descs:
            sym.description = str(sym_descs[sym.name]).strip()
    flowchart = _validate_flowchart(data.get("flowchart"))
    if flowchart:
        node.flowchart = flowchart
    node.highlights = _clean_highlights(data.get("highlights"))


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
                    # Backward compatibility: accept legacy plain-text cache entries.
                    cached_text = _get_cached(conn, cache_key, content_hash)
                    if cached_text:
                        node.description = cached_text
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
                        max_tokens=600,
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
