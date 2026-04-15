---
name: prefxplain
description: Generate or refresh an interactive architecture map for the current repo and open it in IDE preview.
argument-hint: [path] [--no-descriptions] [--output path/to/prefxplain.html]
allowed-tools: Bash, Read, Edit
---

# /prefxplain

Use the `prefxplain` CLI to generate a codebase architecture map.

## Behavior

1. Resolve repo path:
- If `$ARGUMENTS` contains a path, use it.
- Otherwise use current working directory.

2. Decide mode:
- If user includes `--no-descriptions`, keep it.
- Otherwise run default mode with descriptions.

3. Run command:

```bash
cd "$REPO" && prefxplain create . ${EXTRA_ARGS}
```

4. Confirm outputs:
- `prefxplain.html` (or custom `--output`)
- `prefxplain.json`

5. Report succinctly:
- Files/edges summary from command output.
- Where artifacts were written.

If `prefxplain` is not installed, ask permission to run:

```bash
python -m pip install --user prefxplain
```
