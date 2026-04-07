# /prefxplain-update

Re-analyze the codebase and update the dependency graph for changed files.

## What this does

Like `/prefxplain-create` but faster: the SQLite cache at `~/.prefxplain/cache.db` means
only files that changed since the last run get new LLM descriptions. Structure (nodes/edges)
is always re-analyzed from scratch since import relationships are cheap to compute.

## Usage

```
/prefxplain-update [path]
```

## Instructions

When this command is invoked:

1. Determine the repo root. If `$ARGUMENTS` contains a path, use it. Otherwise use cwd.

2. Check if `prefxplain.json` exists at the repo root. If not, run `/prefxplain-create` instead.

3. Load existing graph for context:

```bash
python -c "
from pathlib import Path
from prefxplain.graph import Graph

existing = Graph.load(Path('prefxplain.json'))
print(f'Existing: {len(existing.nodes)} files, {len(existing.edges)} edges')
described = sum(1 for n in existing.nodes if n.description)
print(f'Described: {described}/{len(existing.nodes)} files')
"
```

4. Re-run the full analysis (picks up new files, dropped files, changed imports):

```bash
python -c "
from pathlib import Path
from prefxplain.analyzer import analyze
from prefxplain.graph import Graph

root = Path('.')
new_graph = analyze(root, max_files=500)
old_graph = Graph.load(root / 'prefxplain.json')

# Preserve descriptions for unchanged files
old_descs = {n.id: n.description for n in old_graph.nodes if n.description}
for node in new_graph.nodes:
    if node.id in old_descs:
        node.description = old_descs[node.id]

new_graph.save(root / 'prefxplain.json')
print(f'Updated: {len(new_graph.nodes)} files, {len(new_graph.edges)} edges')
undescribed = [n.id for n in new_graph.nodes if not n.description]
print(f'Need descriptions: {len(undescribed)} files')
for f in undescribed[:20]:
    print(f'  {f}')
"
```

5. For each file with an empty description, generate one (you are the LLM):
   - Read the first 60 lines
   - Write 1-2 sentences: what the file does, what it provides
   - Present tense, don't start with "This file", don't repeat filename

6. Re-render:

```bash
python -c "
from pathlib import Path
from prefxplain.graph import Graph
from prefxplain.renderer import render

graph = Graph.load(Path('prefxplain.json'))
render(graph, output_path=Path('prefxplain.html'))
print('prefxplain.html updated')
"
```

7. Report: files added, files removed, files with updated imports, total coverage.

## Notes

- Descriptions from the previous run are preserved for unchanged files (by file path match)
- New files added since last run always get fresh descriptions
- Deleted files are automatically dropped from the graph
