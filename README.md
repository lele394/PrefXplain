# PrefXplain

> **Claude Code ships a feature in 1 hour. Reviewing it takes me 5.**

That gap is the real bottleneck of AI-assisted software engineering, and
it's not going away. The more code your agent writes, the more your job
shifts from *writing* to *understanding* — understanding the architecture,
understanding what the agent just did, understanding what will break if
you let it ship.

Reading 40 diffs across 20 files is slow, painful, and doesn't scale. But
humans read pictures fast. Give me one good diagram and I'll grasp a
codebase in five minutes that would take me five hours of file-by-file
reading.

**PrefXplain is that diagram.** One slash-command inside Claude Code (or
Codex, or Cursor, or Windsurf) turns your repo into an interactive
architecture map — every file has a role, a plain-English description, and
a place in the dependency flow. No API key, no setup, no upload. Just a
single HTML file you can open, share, or drop into a deck.

**The goal isn't to replace reading code. It's to know what to read.**

I'm a founder shipping with Claude Code every day. I built PrefXplain
because I was drowning in review. Now I run `/prefxplain` before every
audit, every onboarding, every investor walkthrough. It takes 30 seconds
and it changes how I think about the codebase I'm steering.

Free. MIT. Fork it, improve it, make it yours.

**Who this is for:**
- **Founders** explaining their tech to non-technical stakeholders — investors, customers, new hires
- **Devs steering a coding agent** and tired of reviewing diffs blind
- **Tech leads onboarding onto a repo** they didn't write

**Lives inside your IDE.** `/prefxplain` opens the diagram in a preview tab right next to your agent — VS Code, Cursor, Windsurf, Antigravity, whatever. Architecture map on the left, Claude Code (or Codex) on the right. No window swapping, no context loss. (Prefer a browser? The HTML works standalone too.)

---

## What is PrefXplain?

PrefXplain is a free, open-source slash command that turns any codebase into an interactive architecture diagram — one self-contained HTML file, no API key, no upload — so you can grasp a repo in 5 minutes instead of 5 hours.

It runs inside Claude Code, Codex, Cursor, Windsurf, Copilot CLI, or Gemini CLI as `/prefxplain`, or as a standalone `prefxplain` CLI. Every file in your repo gets a plain-English description, a layered position in the dependency graph, a blast-radius view, and an auto-generated flowchart.

## See it

![PrefXplain open side-by-side with Claude Code inside VS Code](docs/images/hero-split.png)

*PrefXplain on the left, Claude Code on the right. Architecture stays
visible while your agent codes. No alt-tab, no context loss.*

Every block is a file or an architectural group. Click to see the
description, the blast radius, the imports, and the actual logic as a
flowchart. Search matches descriptions, not just filenames. The whole
thing is one HTML file — offline, shareable, safe to send.

## Install — 30 seconds

**Requirements:** `git`, `python3` (3.9+), and one of:
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- [Codex CLI](https://github.com/openai/codex)
- [GitHub Copilot CLI](https://docs.github.com/copilot/concepts/agents/about-copilot-cli)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli)

**One line, no paste-breaks:**

```bash
curl -fsSL https://raw.githubusercontent.com/PrefOptimize/PrefXplain/main/install.sh | bash
```

That's it. The installer clones PrefXplain to `~/.prefxplain`, builds an
isolated Python venv, drops a `prefxplain` command on your PATH,
registers the `/prefxplain` slash command for every AI tool it detects
(Claude Code, Cursor/Windsurf, Copilot CLI, Gemini CLI), and
auto-installs the bundled preview extension into every VS Code fork it
finds (VS Code, Cursor, Windsurf, Antigravity, Trae, Void, VSCodium,
Positron, …). The preview extension is bundled with the Python package,
so `pipx` / `uv tool` installs can install it too; `npm` is only needed
if you want to rebuild the extension from source. Re-run the same command
to upgrade — it's idempotent. Codex is project-local, so run
`prefxplain setup codex` inside each repo you want to use it in.

> **Inside your AI coding tool?** Paste the line above into Claude Code /
> Codex / Copilot / Gemini and the agent runs it for you.
>
> **Already on pipx / uv?** `pipx install prefxplain && prefxplain setup`
> (or `uv tool install prefxplain && prefxplain setup`) also works — the
> bundled preview extension is installed there too.

## Use it — 1 line

Open your AI coding CLI (Claude Code, Codex, Copilot, or Gemini) inside any repo and type:

```
/prefxplain
```

![The /prefxplain slash-command showing up inside Claude Code](docs/images/slash-command.png)

The agent reads your files, groups them into architectural blocks, writes
a short description for each, and opens an interactive diagram in an IDE
preview tab. First run on a medium repo: ~2 minutes. Re-runs: seconds
(descriptions are cached).

**No API key.** The agent runs inside your existing Claude Code, Codex,
Copilot, or Gemini session, so you pay nothing extra — your subscription
already covers it.
If you'd rather call a model directly (CI, automation, headless), set
`ANTHROPIC_API_KEY` or `OPENAI_API_KEY` and use the `prefxplain` CLI.

## What you get

- **Executive summary** — 3–5 sentences covering what the project does, its main layers, and its critical path. Paste it into a deck.
- **Health score (1–10)** with plain-English notes. *"No circular deps. `graph.py` is a single point of failure (13 of 17 files depend on it). Test coverage is solid."*
- **Layered architecture diagram** — files grouped into logical blocks (CLI, Analysis, Rendering, …), laid out by dependency depth.
- **Blast radius on click** — select any file and see every file that breaks if you change it, highlighted in amber.
- **Semantic search** — type `auth` or `database` and it matches descriptions, not just filenames.
- **Flowcharts** — double-click a file to see its real logic as a flowchart.

![Clicking a block highlights its blast radius and shows the description on hover](docs/images/blast-radius.png)

*Click any block: neighbors fade, dependency edges light up with labels,
and a hover reveals the plain-English description.*

![Double-clicking a file opens its real logic as a flowchart](docs/images/flowchart-popup.png)

*Double-click to see the actual control flow of a file — start, decisions,
steps, end. Not a generic diagram, the real shape of the code.*

Everything is in a single self-contained HTML file. No server, no CDN, no
JavaScript dependencies, no upload. Safe to share with anyone.

## CLI (optional)

If you don't use a coding agent, the CLI works standalone — set an API
key and run:

```bash
prefxplain create .                    # analyze + open
prefxplain update .                    # re-analyze, preserve descriptions
prefxplain create . --no-descriptions  # offline, no LLM, still useful
prefxplain check .                     # CI: fail on circular deps
prefxplain mcp .                       # MCP server for AI agents
```

You can also force setup for a specific tool:

```bash
prefxplain setup copilot   # installs a global Copilot CLI plugin
prefxplain setup gemini    # installs an Agent Skill in ~/.gemini/skills/prefxplain/
prefxplain setup claude-code
prefxplain setup cursor
prefxplain setup codex     # installs into the current repo's AGENTS.md
```

Each variant installs the same `/prefxplain` slash command — plus a
natural-language trigger ("map this codebase architecture") for agents
that use the Anthropic Agent Skill format (Copilot, Gemini, Claude Code).

<details>
<summary>Full flag reference</summary>

| Flag | Default | Description |
|---|---|---|
| `--output`, `-o` | `./prefxplain.html` | Output path |
| `--format` | `html` | `html`, `matrix`, `mermaid`, `dot` |
| `--no-descriptions` | false | Skip LLM step |
| `--api-key` | env | Override API key |
| `--model` | `gpt-4o-mini` | LLM model |
| `--max-files` | 500 | Analysis cap |
| `--force`, `-f` | false | Regenerate all descriptions |
| `--filter` | — | Glob filter (e.g. `src/**/*.py`) |
| `--focus` / `--depth` | — | Depth-limited view around a file |
| `--level`, `-l` | `newbie` | Audience voice for descriptions: `newbie`, `middle`, `strong`, `expert`. Empty reuses the prior run's level. |

</details>

## Supported languages

| Language | Parser | Status |
|---|---|---|
| Python | `ast` (built-in) | Stable |
| TypeScript / JavaScript | Regex + `tsconfig` path aliases | Stable |
| Go, Rust, Java, Kotlin, C/C++ | Regex | Best-effort |

First-class tree-sitter support for the regex-parsed languages is on the
roadmap.

## FAQ

<details>
<summary>Does PrefXplain upload my code?</summary>

No. The dependency graph is built **locally** — Python AST for Python, regex + `tsconfig` parsing for TypeScript/JavaScript, regex for the rest. The optional LLM step sends only per-file signatures (path, imports, exports, a handful of top-level symbol names) to the model you already use; it never sends file contents. Run `prefxplain create . --no-descriptions` to skip the LLM step entirely and stay fully offline.

</details>

<details>
<summary>Does it work offline / without an API key?</summary>

Yes. `--no-descriptions` produces a full diagram — structure, blast radius, search — with zero network calls. When you *do* want descriptions, PrefXplain runs inside your existing Claude Code / Codex / Copilot / Gemini session, so there's no extra billing. Only the standalone `prefxplain` CLI requires `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`.

</details>

<details>
<summary>How is this different from CodeSee, Sourcegraph, or `tree`?</summary>

- **`tree` / `madge` / `pydeps`** show the shape of your codebase. PrefXplain adds plain-English descriptions, a layered layout, blast-radius on click, and per-file flowcharts.
- **Sourcegraph / CodeSee** are SaaS — they require an account, upload source to their servers, and cost money. PrefXplain is one offline HTML file, no account, MIT.
- PrefXplain is **agent-native**: a single slash command inside the AI coding tool you already use, not a separate UI.

</details>

<details>
<summary>How accurate are the AI-generated descriptions?</summary>

Good enough for navigation, not a substitute for reading the code. The LLM sees one file at a time plus its imports and exports, so descriptions are reliable for *what a file does* and less reliable for *subtle contract details*. Descriptions are cached and re-used across runs; `prefxplain update .` preserves them unless you pass `--force`.

</details>

<details>
<summary>Can I use PrefXplain in CI?</summary>

Yes. `prefxplain check .` exits non-zero on circular dependencies — drop it into a GitHub Action to fail the build when new cycles appear. For artifacts, `prefxplain create . --no-descriptions` generates an offline HTML diagram with no API calls, safe to upload as a CI artifact.

</details>

<details>
<summary>How is it different from a dependency graph I could generate myself?</summary>

`madge`, `pydeps`, and `import-linter` give you edges. PrefXplain adds a description per file, a layered layout that groups files by architectural role, blast-radius on click, per-file flowcharts, and semantic search across descriptions (not just filenames). The output is one self-contained HTML file — shareable, safe to drop into a deck.

</details>

## Development

```bash
git clone https://github.com/PrefOptimize/PrefXplain.git
cd prefxplain
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make test
```

## License

MIT. Free forever. Go build something.

---

Built by [Rémi Al Ajroudi](https://github.com/RemiAJR) — [LinkedIn](https://www.linkedin.com/in/remi-al-ajroudi/). Source and issues at [github.com/PrefOptimize/PrefXplain](https://github.com/PrefOptimize/PrefXplain). MIT licensed.
