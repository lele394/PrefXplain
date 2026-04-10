# PrefXplain

**Explain your codebase in 30 seconds.** Architecture diagrams that actually tell a story.

PrefXplain generates interactive architecture maps from your source code. Each file gets a plain-English description, a role label, and a position in a layered diagram that shows how everything connects. The output is a single HTML file you can share with your team, your manager, your investors, or drop into a pitch deck.

Built for two audiences: **developers** who need to understand and present code they didn't write (or wrote with AI), and **founders** who need to explain their technical architecture to non-technical stakeholders.

## Why this exists

AI writes code fast. Humans review it slow. The bottleneck is no longer writing code, it's understanding it. PrefXplain closes that gap: run one command, get a visual explanation of your entire codebase that anyone can read.

## What you get

- **Executive summary** at the top of the page: what the project does, the main layers, the critical path. Copy-paste this into a pitch deck.
- **Architecture health score** (1-10) with plain-English interpretation: "No circular dependencies. graph.py is a single point of failure. Test coverage is solid."
- **Layered diagram** organized by abstraction level: Surface (entry points, tests) > Features > Services > Foundation (core modules everything depends on).
- **Blast radius on click**: select any file and instantly see every file that would be affected if you changed it. Highlighted in amber on the diagram.
- **Smart search**: type "authentication" or "database" and it matches on descriptions, not just filenames.
- **Language breakdown**: GitHub-style percentage bar showing code distribution by language.

## Quick start

### With Claude Code (recommended, free)

No API key needed. Claude generates all descriptions directly in your session.

```bash
pip install prefxplain
make install               # installs Claude Code skills + VS Code extension
```

Then in Claude Code:

```
/prefxplain-create         # analyze, describe, render, open in IDE
/prefxplain-show           # reopen the diagram without regenerating
/prefxplain-update         # update after code changes (preserves existing descriptions)
```

The diagram opens automatically in a VS Code / Cursor / Windsurf tab.

### With the CLI

```bash
pip install prefxplain

# Analyze and open (descriptions require an API key)
prefxplain .

# Skip descriptions (fast, offline, still useful)
prefxplain . --no-descriptions

# Custom output path
prefxplain . --output architecture.html

# Re-analyze after changes (cached descriptions are preserved)
prefxplain update .
```

## Install

```bash
pip install prefxplain                # core: analysis + rendering
pip install 'prefxplain[llm]'         # + LLM descriptions via API
pip install 'prefxplain[agent]'       # + MCP server for AI agents
pip install 'prefxplain[llm,agent]'   # everything
```

### IDE integration (VS Code, Cursor, Windsurf)

```bash
make install
```

This does two things:
1. Symlinks the Claude Code skills (`/prefxplain-create`, `/prefxplain-show`, `/prefxplain-update`) into `~/.claude/commands/`
2. Builds and installs a tiny VS Code extension (3KB) that enables automatic diagram preview in an IDE tab

Works with any VS Code fork: VS Code, Cursor, Windsurf, VS Code Insiders.

## The diagram

The HTML output is self-contained (no server, no CDN, works offline) and includes:

### Layout

Files are organized top-to-bottom by dependency depth:

| Layer | What's there | Why it matters |
|-------|-------------|----------------|
| **Surface** | Tests, CLI entry points, standalone scripts | Nothing depends on these. Safe to change. |
| **Features** | Main application logic | The features your users interact with. |
| **Services** | Shared modules used across features | Changes here ripple upward. |
| **Foundation** | Core data models, utilities | Everything depends on these. Change with care. |

Each layer has a colored band with a subtitle explaining the count and relationship (e.g., "3 files, shared across features").

### Node cards

Each file is a card showing:
- **Short title** (1-3 words): the role of the file, like "Graph Engine" or "JWT Validator"
- **Filename** in small text below
- **Import count** badge showing how many files depend on it

### Sidebar (click any node)

- Full file path, language, size
- Plain-English description
- Blast radius count ("8 files affected if you change this")
- Exported symbols (functions, classes)
- Import/imported-by lists with clickable navigation
- Code preview (first 50 lines)

### Header

- Language percentage bar (GitHub-style)
- File and edge counts
- "Start here" and "Core file" quick links
- Search box (matches filenames, descriptions, and titles)

## Claude Code skills

The skills are the recommended way to use PrefXplain. Claude reads each file and writes descriptions directly, so no API key is needed and it's completely free.

| Skill | What it does |
|-------|-------------|
| `/prefxplain-create` | Full pipeline: analyze, describe every file, generate summary + health score, render HTML, open in IDE |
| `/prefxplain-update` | Re-analyze after code changes. Preserves descriptions for unchanged files, generates new ones for added/modified files. |
| `/prefxplain-show` | Reopen the diagram in the IDE without regenerating anything. Reuses or starts the local preview server. |

### What the skill generates

For each file:
- **short_title**: 1-3 word role label (e.g., "AST Parser", "Auth Tests")
- **description**: 1-2 sentence explanation of what the file exposes and who uses it

For the project:
- **executive summary**: 3-5 sentences covering what the project does, main layers, critical path
- **health score**: 1-10 rating based on cycles, orphans, test coverage, single points of failure
- **health notes**: plain-English interpretation of the score

## CLI reference

### `prefxplain create` / `prefxplain update`

| Flag | Default | Description |
|------|---------|-------------|
| `--output`, `-o` | `./prefxplain.html` | Output file path |
| `--format` | `html` | Output format: `html`, `matrix`, `mermaid`, `dot` |
| `--no-descriptions` | false | Skip LLM step (fast, offline) |
| `--api-key` | `$OPENAI_API_KEY` | API key for descriptions |
| `--api-base` | OpenAI | Custom API base URL |
| `--model` | `gpt-4o-mini` | LLM model name |
| `--max-files` | 500 | Maximum files to analyze |
| `--force`, `-f` | false | Regenerate all descriptions |
| `--open/--no-open` | true (create) | Open result in browser or IDE |
| `--filter` | - | Only include files matching glob (e.g. `src/**/*.py`) |
| `--focus` | - | Focus file for depth-limited view |
| `--depth` | - | Hops around `--focus` file |
| `--check-cycles` | false | Exit 1 if circular dependencies found |

### `prefxplain context`

Token-efficient context dump for AI coding agents. No server needed.

```bash
prefxplain context "auth" --depth 2 --tokens 2000
```

| Flag | Default | Description |
|------|---------|-------------|
| `--depth`, `-d` | 2 | BFS hops around matching files |
| `--tokens`, `-t` | 2000 | Approximate token budget |
| `--from` | `prefxplain.json` | Load from existing graph |

### `prefxplain check`

CI rule enforcement. Define rules in `.prefxplain.yml`, exit 1 on violations.

```bash
prefxplain check . --config .prefxplain.yml
```

### `prefxplain mcp`

MCP stdio server for AI agent integration (Claude Code, Cursor, Windsurf).

```bash
pip install 'prefxplain[agent]'
prefxplain mcp .
```

Exposes three tools:

| Tool | Description |
|------|-------------|
| `get_context(query, depth?, token_budget?)` | BFS context dump around matching files |
| `get_file(file_path)` | Description, role, and exports for one file |
| `search_files(query)` | List matching file paths |

## Supported languages

| Language | Parser | Status |
|----------|--------|--------|
| Python | `ast` module (built-in) | Stable |
| TypeScript | Regex + `tsconfig.json` path aliases | Stable |
| JavaScript | Regex (import/require) | Stable |

More languages (Go, Rust, Java) planned via tree-sitter grammars.

## Architecture

```
prefxplain/
  analyzer.py    # AST parsing (Python) + regex (JS/TS), two-pass graph build
  graph.py       # Node/Edge/Symbol/Graph dataclasses, cycle detection, centrality
  renderer.py    # Self-contained HTML: canvas layout, layers, sidebar, search
  describer.py   # LLM descriptions with SHA-256 SQLite cache
  exporter.py    # Mermaid + Graphviz DOT export
  checker.py     # CI rule enforcement from .prefxplain.yml
  mcp_server.py  # MCP stdio server for AI agents
  cli.py         # Typer CLI: create, update, check, context, mcp

commands/
  prefxplain-create.md   # Claude Code skill: full pipeline
  prefxplain-update.md   # Claude Code skill: incremental update
  prefxplain-show.md     # Claude Code skill: open preview

vscode-extension/
  src/extension.ts       # URI handler for auto-opening in IDE
  package.json           # Extension manifest

scripts/
  open-in-ide.sh         # IDE detection + URI dispatch
```

## Development

```bash
git clone https://github.com/remi-ajr/prefxplain.git
cd prefxplain
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make test
make lint
```

## License

MIT
