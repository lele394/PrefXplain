---
name: prefxplain-create
description: Generate an interactive dependency graph of the current codebase with natural-language descriptions for each file, rendered as a self-contained HTML the user can share. Use this skill whenever the user wants to understand, map, review, present, or explain the architecture of a codebase -- onboarding onto a new repo, preparing a walkthrough for a manager or teammate, pitching the code to an investor or client, or finding the core files vs the orphans. Trigger on indirect phrasings too: "help me understand this repo", "what's the structure here", "I need to present the code to X", "what are the load-bearing files", "draw me a map of this project".
argument-hint: [path] [--no-descriptions] [--output path/to/graph.html]
allowed-tools: Bash, Read, Edit
---

# prefxplain-create

Produces `prefxplain.html` -- an interactive, self-contained map of the codebase.
Nodes are files, edges are imports, and each node carries a 1-2 sentence
natural-language description written by you (the LLM running this skill).

## Bootstrap

Run these checks at the very start of every invocation:

**1. Check Python package:**

```bash
python -c "import prefxplain; print('prefxplain', prefxplain.__version__)" 2>/dev/null
```

If exit code != 0, tell the user:

> prefxplain is not installed in `which python`. I can run `pip install prefxplain` to set it up. OK? [y/N]

Wait for confirmation. If yes, run `pip install prefxplain`.
If that also fails, stop and say what went wrong.

**2. Check IDE extension (for in-IDE preview):**

```bash
PREFXPLAIN_ROOT="$(python3 -c "import prefxplain, pathlib; print(pathlib.Path(prefxplain.__file__).parent.parent)" 2>/dev/null)"
IDE_CLI="$(which code 2>/dev/null || which cursor 2>/dev/null || which windsurf 2>/dev/null || echo "")"
if [ -n "$IDE_CLI" ]; then
  $IDE_CLI --list-extensions 2>/dev/null | grep -q "prefxplain.browser" && echo "EXTENSION_OK" || echo "EXTENSION_MISSING"
else
  echo "NO_IDE_CLI"
fi
```

If EXTENSION_MISSING and `$PREFXPLAIN_ROOT/vscode-extension/` exists, install it
silently (no need to ask, it's a 3KB extension with zero overhead):

```bash
cd "$PREFXPLAIN_ROOT" && make install-extension
```

If NO_IDE_CLI, skip silently. Preview will fall back to the browser.

## Division of labor

- **The package** (`prefxplain.analyzer`, `prefxplain.renderer`, `prefxplain.graph`)
  handles: filesystem walk, AST parsing for Python and TS/JS, graph construction,
  metrics (in/out-degree, cycles), automatic layering by abstraction level, and HTML
  rendering. Exclusions are built into the walker: `node_modules/`, `.venv/`,
  `__pycache__/`, `dist/`, `build/`, `.git/`, and anything gitignored.

- **You** (the model executing this skill) handle: reading each file and writing a
  good description. This is the only LLM-dependent step, and because you run
  in-session, no API key is needed -- which makes the command free for the user.
  Do **not** invoke `describer.py` (that is the API-based fallback path).

## Workflow

### 1. Resolve the repo root

If `$ARGUMENTS` contains a path, use it. Otherwise use the current working directory.
Store as `$REPO`.

### 2. Analyze and save JSON

```bash
cd $REPO && python -c "
from pathlib import Path
from prefxplain.analyzer import analyze

root = Path('.')
graph = analyze(root, max_files=500)
graph.save(root / 'prefxplain.json')
print(f'FILES: {len(graph.nodes)}')
print(f'EDGES: {len(graph.edges)}')
print(f'LANGUAGES: {graph.metadata.languages}')
print(f'TRUNCATED: {len(graph.nodes) >= 500}')
"
```

Read the output. **If TRUNCATED is True**, stop and ask:

> I found N files and hit the 500-file cap. Want me to scope to a subdirectory
> (e.g. `src/`) or proceed on the truncated set?

Do not silently drop files.

### 3. If `--no-descriptions` was passed, skip to step 5.

### 4. Fill in descriptions

#### 4a. List undescribed nodes

```bash
cd $REPO && python -c "
import json
g = json.loads(open('prefxplain.json').read())
for n in g['nodes']:
    if not n.get('description'):
        print(n['id'])
" 
```

#### 4b. Read files and write descriptions in batches

Process 10-20 files per batch. For each file:

**How much to read:**
- **Short files (<80 lines)**: read the whole thing.
- **Barrel/index files** (`__init__.py`, `index.ts`, `index.js`): read the whole
  thing -- the re-exports are the content.
- **Default (80-500 lines)**: imports block + top-level definitions + module
  docstring. Usually the first 60-120 lines.
- **Huge files (>500 lines)**: first 150 lines, then grep for `^class `, `^def `,
  `^export `, `^function ` to get the shape.

**For each file, generate TWO things:**

1. **`short_title`** (1-3 words): The role of the file shown on the diagram card.
   Think of it as a label you'd write on a box in an architecture whiteboard.
   - GOOD: `Graph Engine`, `HTML Renderer`, `JWT Validator`, `CLI Entry`, `AST Parser`
   - GOOD for tests: `Graph Tests`, `CLI Tests`, `Auth Tests`
   - BAD: `graph.py`, `utils`, `helpers` (filename or too vague)

2. **`description`** (1-2 sentences): What the file exposes and who uses it.
   Start with an active verb. Be specific enough that a reader who knows the
   domain could guess the file's role without opening it.

   Hard rules:
   - Don't start with "This file", "Contains", "Module for", "Handles".
   - Don't repeat the filename.
   - Don't hedge ("some", "various", "utilities for"). If it's truly a grab-bag,
     name the 2-3 main things.
   - Present tense, active voice.

   Examples:
   - GOOD: `Validates JWT tokens; exposes verify(token) which returns the decoded payload or raises AuthError.`
   - GOOD: `Builds the dependency graph via AST walking; main entry point for analyze() and Graph.from_root().`
   - BAD: `This file handles authentication logic for the app.` (starts with "This file", vague)
   - BAD: `Utilities for processing graph data and various helpers.` (hedged, grab-bag)

   Test files: describe what behavior is covered, not the framework.
   `Covers edge cases in Graph.add_edge, including self-referential cycles and missing imports.`

#### 4c. Patch the JSON after each batch

After writing descriptions for a batch, run this script with the dict filled in:

```bash
cd $REPO && python3 << 'PYEOF'
from pathlib import Path
from prefxplain.graph import Graph

graph = Graph.load(Path("prefxplain.json"))

# FILL THIS IN -- one entry per file in this batch
# Format: "path/to/file.py": ("Short Title", "Full description sentence."),
files = {
    # "src/auth.py": ("JWT Validator", "Validates JWT tokens; exposes verify(token) which returns the decoded payload or raises AuthError."),
}

for node in graph.nodes:
    if node.id in files:
        node.short_title, node.description = files[node.id]

graph.save(Path("prefxplain.json"))
print(f"Patched {len(files)} files")
PYEOF
```

IMPORTANT: You MUST fill in the `files` dict with real values before running.
Each value is a tuple of `("Short Title", "Full description.")`.
Do NOT leave the placeholder comment. Run once per batch. Save after each batch.

#### 4d. Completeness check

After all batches, verify nothing was missed:

```bash
cd $REPO && python -c "
import json
g = json.loads(open('prefxplain.json').read())
missing = [n['id'] for n in g['nodes'] if not n.get('description')]
print(f'MISSING: {len(missing)}')
for f in missing: print(f'  {f}')
"
```

If MISSING > 0, go back and describe them.

#### 4e. Generate executive summary + health score

This is the most important step. The summary is what founders paste into decks
and what devs read to understand a project in 30 seconds.

First, collect the structural signals you need. Run:

```bash
cd $REPO && python -c "
import json
from collections import Counter
g = json.loads(open('prefxplain.json').read())
indeg = Counter()
outdeg = Counter()
for e in g['edges']:
    indeg[e['target']] += 1
    outdeg[e['source']] += 1
print('FILES:', len(g['nodes']))
print('EDGES:', len(g['edges']))
print('LANGUAGES:', g['metadata']['languages'])
# Top 3 most-imported
for f, c in indeg.most_common(3):
    desc = next((n.get('description','') for n in g['nodes'] if n['id']==f), '')
    print(f'HUB: {f} ({c} imports) -- {desc}')
# Entry points
for n in g['nodes']:
    if indeg[n['id']] == 0 and not n['id'].startswith('tests/'):
        print(f'ENTRY: {n[\"id\"]}')
# Orphans
orphans = [n['id'] for n in g['nodes'] if indeg[n['id']]==0 and outdeg[n['id']]==0]
print(f'ORPHANS: {len(orphans)}')
# Cycles
cycles = g.get('cycle_node_ids', [])
print(f'CYCLES: {len(cycles)} nodes in cycles')
# Test ratio
tests = sum(1 for n in g['nodes'] if n['id'].startswith('tests/'))
print(f'TEST_RATIO: {tests}/{len(g[\"nodes\"])}')
"
```

Now look at the README too if it exists. Use the Read tool on `$REPO/README.md`
(first 30 lines). This gives you the project's own description of itself.

**Then write the summary and health score.** This is NOT an aggregation of the
per-file descriptions. It answers a different question: "What is this project,
how is it built, and should I be worried about the architecture?"

Use these structural signals + the README + your understanding from reading the
files to write:

- **summary**: 3-5 sentences. What does the project do? What are the main
  architectural layers? What's the critical path (entry → core)? Mention
  specific file names for the load-bearing modules. A non-technical person
  should understand the first sentence; a dev should find the next 2-3 useful.

- **health_score**: integer 1-10. Based on: cycles (>0 = -2), orphan ratio
  (>20% = -1), test coverage (no tests = -3, <50% ratio = -1), single points
  of failure (one file with >50% of imports = -1), overall modularity.

- **health_notes**: 1-2 sentences interpreting the score. Name the specific
  risks. "No circular dependencies. graph.py is a single point of failure
  (13 of 17 files depend on it). Test coverage is solid (9 test files for
  8 source files)."

Patch them into the JSON:

```bash
cd $REPO && python3 << 'PYEOF'
from pathlib import Path
from prefxplain.graph import Graph

graph = Graph.load(Path("prefxplain.json"))

# FILL THESE IN from your analysis above
graph.metadata.summary = "..."
graph.metadata.health_score = 8
graph.metadata.health_notes = "..."

graph.save(Path("prefxplain.json"))
print("Patched summary + health")
PYEOF
```

IMPORTANT: The summary must NOT be generic. It must name specific files, specific
numbers, and specific architectural decisions. If it reads like it could describe
any project, rewrite it.

### 5. Render the final HTML

```bash
cd $REPO && python -c "
from pathlib import Path
from prefxplain.graph import Graph
from prefxplain.renderer import render

graph = Graph.load(Path('prefxplain.json'))
output = Path('${OUTPUT:-prefxplain.html}')
render(graph, output_path=output)
print(f'Written: {output}')
print(f'OPEN: {output.resolve()}')
"
```

If `--output` was passed in `$ARGUMENTS`, use that path instead of the default.

### 6. Preview in IDE

Open the HTML directly in a VS Code webview tab (no server needed):

```bash
HTML_PATH="$(cd "$REPO" && pwd)/prefxplain.html"
ENCODED_PATH=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$HTML_PATH', safe=''))")
SCHEME="vscode"
[[ "${TERM_PROGRAM:-}" == "cursor" ]] && SCHEME="cursor"
[[ "${TERM_PROGRAM:-}" == "windsurf" ]] && SCHEME="windsurf"
open "${SCHEME}://prefxplain.prefxplain-vscode/preview?path=${ENCODED_PATH}"
```

If the extension is not installed, the URI will fail silently. Tell the user:
`Run make install-extension in the prefxplain repo to enable IDE preview.`

The webview auto-refreshes when prefxplain.html changes on disk, so re-running
`/prefxplain-create` updates the existing tab without opening a new one.

### 7. Report to the user

Keep this tight. Pull structural insights from the JSON:

- **File count + languages** (note if the cap was hit)
- **Top 3 most-imported files** -- the load-bearing abstractions. Name them with
  their one-line description.
- **Entry points** (in-degree 0, excluding tests) -- where to start reading
- **Orphans** (no imports in or out) -- if >3, give the count, offer to list
- **Cycles** if detected -- flag as architectural debt
- **Path to prefxplain.html**

Close with: "Happy to walk through any specific file or cluster."
Don't preempt -- wait for the user to ask.

## Notes

- The HTML is self-contained, works offline, safe to share with non-technical
  stakeholders
- `prefxplain.json` stays on disk so `/prefxplain-update` can do incremental
  refreshes without re-describing unchanged files
- The HTML renderer already surfaces entry points, core files, orphans, and cycles
  visually -- the text report is a summary for people reading along in chat
- A background HTTP server runs after `create` for IDE preview. It consumes zero
  CPU at rest but holds a port open. Kill it with `kill $(cat /tmp/prefxplain.pid)`.
  It relaunches automatically via `/prefxplain-show` if killed.
- Use `/prefxplain-show` to reopen the preview without regenerating the graph.
