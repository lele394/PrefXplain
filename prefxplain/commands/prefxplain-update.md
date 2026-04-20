---
name: prefxplain-update
description: Upgrade prefxplain itself to the latest version from GitHub main. Use when the user says "update prefxplain", "upgrade prefxplain", "get the latest prefxplain", or asks why /prefxplain is rendering old-style diagrams (legacy Canvas instead of the ELK view with minimap and group-map toggle).
argument-hint: (no arguments)
allowed-tools: Bash
---

# prefxplain-update

Upgrades the user's local prefxplain install to the latest version on GitHub
main. This is the canonical update path — the project intentionally does not
rely on PyPI, which lags behind the GitHub renderer.

## Workflow

### 1. Record the current version (for before/after reporting)

```bash
BEFORE="$(prefxplain --version 2>/dev/null || echo 'not installed')"
echo "BEFORE: $BEFORE"
```

### 2. Run the upgrade

Prefer the CLI subcommand if prefxplain is already installed — it re-runs the
official installer under the hood and handles venv + shim + slash-command
refresh in one go:

```bash
if command -v prefxplain >/dev/null 2>&1; then
  prefxplain upgrade
else
  curl -fsSL https://raw.githubusercontent.com/PrefOptimize/PrefXplain/main/install.sh | bash
fi
```

If the upgrade fails, stop and show the error.

### 3. Verify the upgrade landed

```bash
AFTER="$(prefxplain --version 2>/dev/null || echo 'still missing')"
echo "AFTER: $AFTER"

# Sanity check: the new ELK renderer module must exist
ls ~/.prefxplain/prefxplain/rendering/html_shell.py >/dev/null 2>&1 \
  && echo "ELK renderer: present" \
  || echo "ELK renderer: MISSING"

# Warn about PATH shadowing — a common cause of "upgrade didn't take"
PATHS="$(which -a prefxplain 2>/dev/null)"
COUNT="$(printf '%s\n' "$PATHS" | grep -c .)"
if [ "$COUNT" -gt 1 ]; then
  echo
  echo "WARNING: multiple prefxplain binaries on PATH:"
  echo "$PATHS"
  echo
  echo "The first one wins. If it is not ~/.local/bin/prefxplain (the shim),"
  echo "remove the others with: pip uninstall prefxplain  (in the relevant env)"
fi
```

### 4. Report to the user

Tell the user:
- What version they had before and what they have now (e.g., `0.3.0 → 0.4.0`)
- That the ELK renderer is present (or not)
- Any PATH shadowing warnings, with the exact `pip uninstall` command to run
- Suggest re-running `/prefxplain` in their project to regenerate with the new
  renderer

Keep the report to 3–5 lines unless there is a warning to surface.

## Notes

- Do **not** use `pip install --upgrade prefxplain`. PyPI intentionally lags
  GitHub main; upgrading via pip will leave the user on an older renderer.
- The installer is idempotent: it wipes `~/.prefxplain` and reclones. Local
  edits inside that directory will be lost — this is by design, since
  `~/.prefxplain` is a managed install location, not a workspace.
- This command only updates the prefxplain package. To regenerate a project's
  diagram with the new renderer, run `/prefxplain` afterwards.
