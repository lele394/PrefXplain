# TODOS

## v0.1 fixes (from eng review 2026-04-07)

- [ ] `.mjs`/`.cjs` extension resolution in `_try_js_candidates()` — analyzer collects these files but never tries them during import resolution. ~5 lines in `analyzer.py`.
- [ ] Cache key should include model name — current `(file_path, content_hash)` serves stale descriptions when switching models. Add model column to SQLite table in `describer.py`.

## v0.2 / v0.3 deferred

- [ ] Wire `exporter.py` (Mermaid + DOT export) into CLI — file exists, created during Codex review. Design doc puts Mermaid export at v0.3. Add `prefxplain export --format mermaid|dot` command.
- [ ] MCP server (`prefxplain mcp --port 3333`) — v0.2 per design doc.
- [ ] CALLS edges (cross-file function calls) — v0.2.
- [ ] `prefxplain query "where is auth handled?"` — embedding similarity on descriptions — v0.2.
- [ ] GitHub Action for auto-commit on push — v0.3.
- [ ] Multi-language support (Go, Rust via tree-sitter grammars) — v0.3.
- [ ] CI/CD pipeline for PyPI releases — v0.2.
