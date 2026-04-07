# /prefxplain-create

Generate an interactive dependency graph for the current codebase.

## What this does

1. Walks all Python and TypeScript/JavaScript files in the project root
2. Extracts import relationships to build a dependency graph
3. Generates 1-2 sentence natural language descriptions for each file using Claude
4. Renders a self-contained interactive HTML file you can share with anyone

## Usage

```
/prefxplain-create [path] [--no-descriptions] [--output path/to/graph.html]
```

## Instructions

When this command is invoked:

1. Determine the repo root. If `$ARGUMENTS` contains a path, use it. Otherwise default to the current working directory.

2. Run the analysis using Python directly (no API key needed — you ARE the LLM):

```bash
cd <repo-root>
python -c "
from pathlib import Path
from prefxplain.analyzer import analyze
from prefxplain.renderer import render

root = Path('.')
graph = analyze(root, max_files=500)
print(f'Found {len(graph.nodes)} files, {len(graph.edges)} edges')
print('Languages:', graph.metadata.languages)
render(graph, output_path=root / 'prefxplain.html')
print('Written: prefxplain.html')
graph.save(root / 'prefxplain.json')
print('Written: prefxplain.json')
"
```

3. Generate descriptions by reading each file yourself (you are the LLM — no OpenAI key needed):

   For each node in the graph where `description == ""`:
   - Read the first 60 lines of the file at `<repo-root>/<node.id>`
   - Write a 1-2 sentence description: what the file does, what it provides to other parts of the codebase
   - Rules: present tense, don't start with "This file", don't repeat the filename, be specific
   - Store the description in `graph.nodes[i].description`

4. Re-render with descriptions filled in:

```bash
python -c "
import json
from pathlib import Path
from prefxplain.graph import Graph
from prefxplain.renderer import render

graph = Graph.load(Path('prefxplain.json'))
# [descriptions will be patched in by the AI before this step]
render(graph, output_path=Path('prefxplain.html'))
print('Updated prefxplain.html with descriptions')
"
```

5. Report to the user:
   - How many files were mapped
   - Languages detected
   - Path to `prefxplain.html`
   - Any files that had import errors or couldn't be parsed
   - Top 5 most-imported files (highest indegree) — these are the core abstractions

6. Offer to explain any specific file or cluster the user asks about.

## Notes

- The HTML file is self-contained — no server needed, works offline, safe to share
- `prefxplain.json` contains the raw graph data for programmatic use
- If `--no-descriptions` is passed, skip step 3
- If prefxplain is not installed: `pip install prefxplain` or `pip install -e /path/to/prefxplain`
