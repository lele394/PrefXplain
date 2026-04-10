---
name: prefxplain-show
description: Ouvre prefxplain.html dans un onglet VS Code (webview plein ecran, pas de toolbar). A utiliser quand l'utilisateur veut revoir le diagramme deja genere sans le regenerer. Trigger aussi sur "montre-moi le diagramme", "ouvre prefxplain", "preview", "show the graph", "open the map".
allowed-tools: Bash
---

# prefxplain-show

Opens the previously generated `prefxplain.html` in a clean VS Code webview tab.
No toolbar, no URL bar, just the diagram. Auto-refreshes if the file changes on disk.

Does NOT regenerate the graph. Use `/prefxplain-create` for that.

## Bootstrap

Check the VS Code extension is installed:

```bash
IDE_CLI="$(which code 2>/dev/null || which cursor 2>/dev/null || which windsurf 2>/dev/null || echo "")"
if [ -n "$IDE_CLI" ]; then
  $IDE_CLI --list-extensions 2>/dev/null | grep -q "prefxplain.prefxplain-vscode" && echo "EXTENSION_OK" || echo "EXTENSION_MISSING"
else
  echo "NO_IDE_CLI"
fi
```

If EXTENSION_MISSING, try to install silently:

```bash
PREFXPLAIN_ROOT="$(python3 -c "import prefxplain, pathlib; print(pathlib.Path(prefxplain.__file__).parent.parent)" 2>/dev/null)"
[ -f "$PREFXPLAIN_ROOT/Makefile" ] && cd "$PREFXPLAIN_ROOT" && make install-extension
```

## Workflow

### 1. Check that prefxplain.html exists

```bash
REPO="${ARGUMENTS:-.}"
cd "$REPO"
[ -f prefxplain.html ] && echo "FOUND: $(pwd)/prefxplain.html" || echo "NOT_FOUND"
```

If NOT_FOUND, tell the user:

> No prefxplain.html found in this directory. Run `/prefxplain-create` first to
> generate it.

Then stop.

### 2. Open in IDE

```bash
HTML_PATH="$(pwd)/prefxplain.html"
ENCODED_PATH=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$HTML_PATH', safe=''))")
SCHEME="vscode"
[[ "${TERM_PROGRAM:-}" == "cursor" ]] && SCHEME="cursor"
[[ "${TERM_PROGRAM:-}" == "windsurf" ]] && SCHEME="windsurf"
open "${SCHEME}://prefxplain.prefxplain-vscode/preview?path=${ENCODED_PATH}"
echo "Opened prefxplain.html in IDE"
```

That's it. No server, no descriptions, no re-analysis. Just open the file.
