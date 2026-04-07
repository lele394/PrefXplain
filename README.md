# PrefXplain

Understand your codebase. Visual dependency maps + natural language descriptions.

PrefXplain parses your source code, extracts import relationships, generates AI-powered file descriptions, and renders an interactive dependency graph as a self-contained HTML file.

## What it does

1. **Static analysis** - walks Python and JS/TS files, extracts symbols and import edges (supports `tsconfig.json` path aliases like `@/`)
2. **AI descriptions** - generates a 1-2 sentence description of each file using an LLM (cached in SQLite so re-runs are instant)
3. **Interactive graph** - renders a force-directed graph in a single HTML file (no server, no CDN, shareable)

## Install

```bash
pip install -e .           # core (analysis + rendering)
pip install -e ".[llm]"    # + OpenAI-compatible LLM for descriptions
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

| Flag | Default | Description |
|------|---------|-------------|
| `--output`, `-o` | `./prefxplain.html` | Output file path |
| `--no-descriptions` | false | Skip LLM step (fast, offline) |
| `--api-key` | `$OPENAI_API_KEY` | API key for descriptions |
| `--api-base` | OpenAI | Custom API base URL |
| `--model` | `gpt-4o-mini` | LLM model name |
| `--max-files` | 500 | Maximum files to analyze |
| `--force`, `-f` | false | Regenerate all descriptions |
| `--open/--no-open` | true (create) | Open result in browser |

## Architecture

```
prefxplain/
  analyzer.py    # Python ast + JS/TS regex, two-pass graph build
  graph.py       # Graph/Node/Edge/Symbol dataclasses, JSON I/O
  describer.py   # LLM descriptions with SHA-256 SQLite cache
  renderer.py    # Self-contained HTML canvas force-directed graph
  cli.py         # Typer CLI with create/update commands
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
