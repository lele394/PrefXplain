#!/bin/bash
# Open a local prefxplain.html file in the IDE webview via the prefxplain-vscode extension.
# Usage: ./open-in-ide.sh /absolute/path/to/prefxplain.html

HTML_PATH="$1"
if [ -z "$HTML_PATH" ]; then
  echo "Usage: ./open-in-ide.sh /absolute/path/to/prefxplain.html" >&2
  exit 1
fi

if [ ! -f "$HTML_PATH" ]; then
  echo "File not found: $HTML_PATH" >&2
  exit 1
fi

BUNDLE="${__CFBundleIdentifier:-}"
TERM="${TERM_PROGRAM:-}"

if [[ "$BUNDLE" == *"Cursor"* ]] || [[ "$TERM" == "cursor" ]]; then
  SCHEME="cursor"
elif [[ "$BUNDLE" == *"Windsurf"* ]] || [[ "$TERM" == "windsurf" ]]; then
  SCHEME="windsurf"
elif [[ "$BUNDLE" == *"VSCodeInsiders"* ]] || [[ "$TERM" == "vscode-insiders" ]]; then
  SCHEME="vscode-insiders"
else
  SCHEME="vscode"
fi

PREVIEW_URI="$(
  HTML_PATH="$HTML_PATH" SCHEME="$SCHEME" python3 - <<'PY'
import os
import urllib.parse

scheme = os.environ["SCHEME"]
html_path = os.environ["HTML_PATH"]
print(f"{scheme}://prefxplain.prefxplain-vscode/preview?path={urllib.parse.quote(html_path)}")
PY
)"

open "$PREVIEW_URI"
