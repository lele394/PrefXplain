# PrefXplain

Understand your codebase. Visual dependency maps + natural language descriptions.

PrefXplain parses your source code, extracts import relationships, generates AI-powered file descriptions, and renders an interactive dependency graph as a self-contained HTML file.

## What it does

1. **Static analysis** - walks Python and JS/TS files, extracts symbols and import edges (supports `tsconfig.json` path aliases like `@/`)
2. **AI descriptions** - generates a 1-2 sentence description of each file using an LLM (cached in SQLite so re-runs are instant)
3. **Interactive graph** - renders a force-directed graph in a single HTML file (no server, no CDN, shareable)
4. **Agent context** - exports a token-efficient context dump for AI coding agents via CLI or MCP server (`get_context`, `get_file`, `search_files` tools)

## Install

```bash
pip install -e .             # core (analysis + rendering)
pip install -e ".[llm]"      # + OpenAI-compatible LLM for descriptions
pip install -e ".[agent]"    # + MCP server for AI agent integration
pip install -e ".[llm,agent]"  # everything
```

## Usage

### CLI

```bash
# Analyze current directory (opens in browser)
prefxplain .

# Custom output path, skip LLM descriptions
prefxplain . --output graph.html --no-descriptions

# Use a different model or API endpoint
prefxplain . --model gpt-4o --api-base http://localhost:11434/v1

# Re-analyze (only changed files get new descriptions)
prefxplain update .

# Token-efficient context dump for AI agents
prefxplain context "auth" --depth 2 --tokens 2000

# Start MCP server (requires prefxplain[agent])
prefxplain mcp .

# Enforce architectural rules in CI
prefxplain check . --config .prefxplain.yml
```

### Claude Code Skills

No API key needed. Claude generates descriptions directly.

```
/prefxplain-create          # analyze and render
/prefxplain-update          # re-analyze changed files
```

Install the skill commands:
```bash
cp commands/prefxplain-*.md ~/.claude/commands/
```

## AI Agent Integration

PrefXplain can serve your codebase graph to AI coding agents — giving them structured,
token-efficient context instead of reading every file raw.

### `prefxplain context` (no extra deps)

```bash
prefxplain create . --no-descriptions   # generate prefxplain.json once
prefxplain context "auth" --depth 2     # instant context dump, loads from JSON
```

Output example:
```
# Context: 'auth' — 4 files, depth 2

FILE src/auth/token.py [python role=utility]
  > Handles JWT generation and validation for API endpoints.
  exports: sign(f), verify(f), decode(f)
FILE src/auth/middleware.py [python role=api_route]
  > Request middleware that validates bearer tokens on protected routes.
  exports: require_auth(f)

IMPORT src/api/routes.py -> src/auth/middleware.py
IMPORT src/auth/middleware.py -> src/auth/token.py
```

### MCP server (Claude Code, Cursor, Windsurf)

```bash
pip install 'prefxplain[agent]'
prefxplain mcp .
```

Configure in Claude Code (`~/.claude/mcp.json`):
```json
{
  "mcpServers": {
    "prefxplain": {
      "command": "prefxplain",
      "args": ["mcp", "/path/to/your/repo"]
    }
  }
}
```

Once configured, Claude Code can call `get_context("auth")` before navigating the codebase,
reducing context usage significantly on large repos.

## Output

- `prefxplain.html` - self-contained interactive graph (open in any browser)
- `prefxplain.json` - raw graph data for programmatic access

### Graph features

- Force-directed layout with pan, zoom, and drag
- Nodes colored by language (Python blue, TypeScript cyan, JS yellow)
- Click a node to see: file path, description, exported symbols, imports, imported-by
- Search box filters nodes by filename
- Clickable neighbor navigation in sidebar

## CLI Options

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
| `--open/--no-open` | true (create) | Open result in browser |
| `--filter` | — | Only include files matching glob (e.g. `src/**/*.py`) |
| `--focus` | — | Focus file for depth-limited view |
| `--depth` | — | Hops around `--focus` file |
| `--check-cycles` | false | Exit 1 if circular dependencies found |

### `prefxplain context`

| Flag | Default | Description |
|------|---------|-------------|
| `--depth`, `-d` | 2 | BFS hops around matching files |
| `--tokens`, `-t` | 2000 | Approximate token budget for output |
| `--from` | `<root>/prefxplain.json` | Load from existing graph JSON |
| `--max-files` | 500 | Max files if re-analyzing from source |

Loads from `prefxplain.json` when it exists (instant). Falls back to re-analyzing from source.

### `prefxplain mcp`

| Flag | Default | Description |
|------|---------|-------------|
| `--from` | `<root>/prefxplain.json` | Load from existing graph JSON |

Starts a stdio MCP server exposing three tools to any MCP-compatible client (Claude Code, Cursor, Windsurf):

| Tool | Description |
|------|-------------|
| `get_context(query, depth?, token_budget?)` | BFS context dump around matching files |
| `get_file(file_path)` | Description, role, and exports for one file |
| `search_files(query)` | List matching file paths |

## Architecture

```
prefxplain/
  analyzer.py    # Python ast + JS/TS regex, two-pass graph build
  graph.py       # Graph/Node/Edge/Symbol dataclasses, JSON I/O, BFS/cycle/centrality
  describer.py   # LLM descriptions with SHA-256 SQLite cache
  renderer.py    # Self-contained HTML canvas force-directed graph
  exporter.py    # Mermaid, DOT, and agent context text export
  checker.py     # CI rule enforcement (.prefxplain.yml)
  mcp_server.py  # MCP stdio server (get_context, get_file, search_files)
  cli.py         # Typer CLI: create, update, check, context, mcp
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
