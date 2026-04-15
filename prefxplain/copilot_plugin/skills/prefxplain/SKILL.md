---
name: prefxplain
description: Map and explain repository architecture with an interactive dependency graph.
---

When the user asks to map, visualize, or explain the architecture of a repository:

1. Run `prefxplain create .` in the target repo.
2. If the user wants a fast/offline run, use `prefxplain create . --no-descriptions`.
3. If they want a refresh preserving prior descriptions, use `prefxplain update .`.
4. Report where `prefxplain.html` and `prefxplain.json` were generated.

Use this skill for prompts like:
- "map this codebase"
- "explain repo architecture"
- "show me dependencies between files"
- "refresh the prefxplain diagram"
