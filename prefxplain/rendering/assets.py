"""Read JS/CSS modules from disk and concatenate for inline embedding.

The rendering pipeline ships as a single self-contained HTML file. We keep the
JS source organized on disk (for maintainability) and this module concatenates
the modules at render time, in a defined order.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_JS_DIR = Path(__file__).parent / "js"


@cache
def _read(rel_path: str) -> str:
    """Read a file under the js/ directory, cached for the process lifetime."""
    return (_JS_DIR / rel_path).read_text(encoding="utf-8")


def vendor_elk() -> str:
    """Return the vendored elkjs bundle (main thread)."""
    return _read("vendor/elk.bundled.js")


def vendor_elk_worker() -> str:
    """Return the vendored elkjs worker bundle (for new ELK({workerUrl})).

    We inline this and turn it into a Blob URL at runtime so the worker can
    load in a single-file HTML without a network fetch.
    """
    return _read("vendor/elk-worker.min.js")


def app_modules(names: list[str]) -> str:
    """Concatenate the listed JS modules (relative to js/), in order.

    Each module is wrapped in a banner comment so the resulting blob is easier
    to debug in the browser DevTools.
    """
    parts: list[str] = []
    for name in names:
        parts.append(f"\n/* === {name} === */\n")
        parts.append(_read(name))
    return "".join(parts)
