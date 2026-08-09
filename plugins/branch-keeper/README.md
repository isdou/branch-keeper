# Branch Keeper

Branch Keeper is a local-first Codex/Antigravity plugin for preserving valuable product directions and continuing them later. It includes an optional Codex Companion that injects a native-looking sidebar entry and local board into a Codex window.

## Current V1

- Global Skill with selective branch suggestions
- Batch-confirmed direction capture
- Local SQLite storage through a stdlib-only MCP server
- Conversation roots and direction children
- Layered lifecycle, review, attention, blocker, and resume-operation states
- Event timeline and resume-session history
- Status/search/list tools with soft-limit warnings and duplicate suggestions
- Clean continuation prompts
- Markdown/JSON board output
- Optional Codex Companion: local board, sidebar entry, status updates, and prompt handoff

The core plugin works without the Companion. The Companion is a local CDP launcher/injector; it does not modify Codex's app bundle or send branch data to a cloud service.

Lifecycle is intentionally small: `parked`, `exploring`, `adopted`, `merged`,
and `abandoned`. Review state, attention badges (`due`, `stale`, `blocked`), and
resume operation results are tracked separately so a blocked or overdue branch
does not lose its product meaning. Duplicate detection and branch-count limits
only produce reviewable warnings; they never auto-merge or silently discard a
confirmed branch.

## Local data

By default, data is stored at `~/.branch-keeper/branches.sqlite3`. Set `BRANCH_KEEPER_HOME` to use another local directory.

## Hosts

- Codex uses `.codex-plugin/plugin.json` and `.mcp.json`.
- Antigravity uses the root `plugin.json`, `mcp_config.json`, and `skills/`.

Both host configurations invoke the Node launcher at
`./scripts/branch_keeper_launcher.mjs`, which resolves the MCP server path and
automatically finds Python 3.10+ as `python3`, `python`, or `py -3` on Windows.
Set `BRANCH_KEEPER_PYTHON` when Python is installed under a non-standard path.
The launcher keeps `cwd: "."` so the same configuration works from an
installed plugin cache or a local checkout.

## Codex Companion

The Companion must be started separately because the plugin manifest does not expose a supported native-sidebar injection API. It launches or attaches to a Codex process through the local Chromium DevTools Protocol, injects the Codex-side bridge, and mounts the board from a loopback-only HTTP server.

From this plugin directory:

```bash
# Launch a separate Codex profile with CDP enabled and keep the injector alive.
node companion/codex-injector.mjs --launch --watch

# Or attach to a Codex window that was already started with CDP.
node companion/codex-injector.mjs --port 9232 --watch
```

Useful options:

- `--codex-path /Applications/ChatGPT.app/Contents/MacOS/ChatGPT` chooses the Codex executable.
- `--profile ~/.branch-keeper/codex-profile` chooses the persistent launched profile.
- `--open` also opens the local board in the default browser for debugging.
- `--once` injects once and exits, which is useful for smoke tests.

The Companion is macOS-first in this version. Codex DOM selectors and CDP behavior can change across Codex releases, so the core Skill/MCP workflow remains the portable fallback.
