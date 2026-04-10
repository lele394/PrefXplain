#!/bin/bash
# Open a URL in the current IDE's Simple Browser via the prefxplain.browser extension.
# Usage: ./open-in-ide.sh <url>
# Detects VS Code, Cursor, Windsurf, VS Code Insiders automatically.

URL="$1"
if [ -z "$URL" ]; then
  echo "Usage: open-in-ide.sh <url>" >&2
  exit 1
fi

# URL-encode the target URL for the query string
ENCODED_URL=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$URL', safe=''))")

# Detect which IDE is running from environment
BUNDLE="${__CFBundleIdentifier:-}"
TERM="${TERM_PROGRAM:-}"

if [[ "$BUNDLE" == *"Cursor"* ]] || [[ "$TERM" == "cursor" ]]; then
  SCHEME="cursor"
elif [[ "$BUNDLE" == *"Windsurf"* ]] || [[ "$TERM" == "windsurf" ]]; then
  SCHEME="windsurf"
elif [[ "$BUNDLE" == *"VSCodeInsiders"* ]] || [[ "$TERM" == "vscode-insiders" ]]; then
  SCHEME="vscode-insiders"
elif [[ "$BUNDLE" == *"VSCode"* ]] || [[ "$TERM" == "vscode" ]]; then
  SCHEME="vscode"
else
  # Fallback: try vscode, then open in browser
  SCHEME="vscode"
fi

open "${SCHEME}://prefxplain.browser/open?url=${ENCODED_URL}"
