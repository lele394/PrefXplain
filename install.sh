#!/usr/bin/env bash
# PrefXplain remote installer.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/PrefOptimize/PrefXplain/main/install.sh | bash
#
# Clones (or updates) PrefXplain into ~/.prefxplain and runs ./setup, which
# registers /prefxplain for every AI coding tool it detects and auto-installs
# the preview extension into every VS Code fork it detects.
#
# Idempotent: safe to re-run to upgrade. Handles phantom CWDs (a common
# footgun when the user is still `cd`'d inside a ~/.prefxplain that was
# wiped by a prior install attempt) by jumping to $HOME first.

set -euo pipefail

REPO_URL="https://github.com/PrefOptimize/PrefXplain.git"
TARGET="${PREFXPLAIN_HOME:-$HOME/.prefxplain}"

GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
RED=$'\033[0;31m'
BOLD=$'\033[1m'
DIM=$'\033[2m'
NC=$'\033[0m'

echo "${BOLD}PrefXplain installer${NC}"
echo "${DIM}Target: $TARGET${NC}"
echo

# Escape any phantom CWD — a shell still sitting inside a deleted directory
# fails every subsequent command with "Unable to read current working
# directory". Jumping to $HOME unconditionally is safe and idempotent.
cd "$HOME"

# Pre-flight tooling.
for cmd in git python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "${RED}✗${NC} Missing required tool: $cmd"
    case "$cmd" in
      git)     echo "  Install:  sudo apt install git   (or brew install git)" ;;
      python3) echo "  Install:  sudo apt install python3 python3-venv   (or brew install python)" ;;
    esac
    exit 1
  fi
done

# Clone fresh or update in place.
if [ -d "$TARGET/.git" ]; then
  echo "${DIM}Existing clone detected — updating…${NC}"
  git -C "$TARGET" fetch --depth 1 origin main >/dev/null 2>&1 || true
  git -C "$TARGET" reset --hard origin/main >/dev/null 2>&1 || true
  echo "${GREEN}✓${NC} Updated $TARGET"
else
  # Any non-git directory at the target path is assumed to be a failed
  # prior install — remove it. We never touch paths outside $TARGET.
  if [ -e "$TARGET" ]; then
    echo "${DIM}Removing previous install at ${TARGET}…${NC}"
    rm -rf "$TARGET"
  fi
  echo "${DIM}Cloning ${REPO_URL}…${NC}"
  git clone --single-branch --depth 1 "$REPO_URL" "$TARGET" >/dev/null 2>&1
  echo "${GREEN}✓${NC} Cloned into $TARGET"
fi

echo
# Hand off to the repo-local setup script. It builds the venv, drops the
# prefxplain shim on PATH, and runs `prefxplain setup`.
cd "$TARGET"
exec ./setup
