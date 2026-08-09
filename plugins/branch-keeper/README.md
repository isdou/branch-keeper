# Branch Keeper plugin package

This directory contains the installable Codex and Antigravity package for
[Branch Keeper](https://github.com/isdou/branch-keeper). The public overview,
user-facing installation guide, and publishing workflow live in the
[repository README](../../README.md).

Branch Keeper is a local-first product-direction system. It captures a
valuable direction that came up in an AI conversation, records why it is being
kept and deferred, and prepares the context needed to continue it later.

## Package metadata

- **Version:** `0.2.0`
- **License:** MIT
- **Runtime:** Node.js 18+ launcher, Python 3.10+ MCP server
- **Transport:** local MCP over stdio
- **Storage:** local SQLite
- **Hosts:** Codex and Antigravity

This is a bundled local MCP server, not a hosted HTTP endpoint. It does not
require an API key, account, cloud database, or separate backend service.

## Host integration

| Host | Package files | MCP entrypoint |
| --- | --- | --- |
| Codex | `.codex-plugin/plugin.json`, `.mcp.json`, `skills/` | `node ./scripts/branch_keeper_launcher.mjs ./scripts/branch_keeper_mcp.py` |
| Antigravity | `plugin.json`, `mcp_config.json`, `skills/` | `node ./scripts/branch_keeper_launcher.mjs ./scripts/branch_keeper_mcp.py` |

Both host configurations use the same launcher. The launcher resolves the
server path relative to the installed package and looks for Python in this
order:

1. `BRANCH_KEEPER_PYTHON`, when set;
2. `python3`;
3. `python`;
4. `py -3` on Windows.

If Python is installed in a non-standard location, set the environment
variable before starting the host:

```bash
export BRANCH_KEEPER_PYTHON=/absolute/path/to/python3
```

```powershell
$env:BRANCH_KEEPER_PYTHON = "C:\Python312\python.exe"
```

The launcher forwards MCP arguments and keeps protocol traffic on stdout;
diagnostic messages are written to stderr. This makes the package usable from
an installed plugin cache as well as from a local checkout.

## MCP surface

The server entrypoint is `scripts/branch_keeper_mcp.py`. It exposes:

| Tool | What it is for |
| --- | --- |
| `park_branches` | Save confirmed product directions from a discussion |
| `list_branches` | List branches by project, status, attention, or review state |
| `get_branch` | Read a branch, event timeline, and resume sessions |
| `search_branches` | Search titles, rationale, questions, actions, blockers, and excerpts |
| `resume_branch` | Create a resume session and continuation prompt |
| `record_resume_result` | Record the result of a continuation handoff |
| `update_branch` | Update status, metadata, blockers, outcomes, and relationships |
| `render_branch_board` | Render an unfinished-branch board in Markdown or JSON |

The global Skill is intentionally selective. It may suggest a distinct
deferred direction in any product conversation, but it asks for confirmation
before writing a branch. Duplicate detection and the soft branch limits are
warnings for review; they never silently merge or delete user-confirmed work.

## Data and state model

The default database is:

```text
~/.branch-keeper/branches.sqlite3
```

Override it with either of these variables:

```bash
export BRANCH_KEEPER_HOME=/path/to/branch-keeper-data
export BRANCH_KEEPER_DB_PATH=/path/to/branches.sqlite3
```

Lifecycle status is deliberately separate from operational attention:

- lifecycle: `parked`, `exploring`, `adopted`, `merged`, `abandoned`;
- review: `confirmed`, `needs_review`;
- attention: `normal`, `due`, `stale`, `blocked`;
- resume operation: `idle`, `prompt_ready`, `task_launching`, `succeeded`, `failed`.

Resolved transitions require a reason or outcome rationale, and reopening a
branch preserves its previous outcome and event history.

## Optional Codex Companion

The Companion is separate from the core Skill and MCP server. It provides a
local board and an optional Codex-side entry point by attaching to a Codex
window through the local Chromium DevTools Protocol. It does not modify the
Codex application bundle or upload branch data.

From this directory:

```bash
# Launch a separate Codex profile with CDP enabled.
node companion/codex-injector.mjs --launch --watch

# Or attach to a Codex window already started with CDP.
node companion/codex-injector.mjs --port 9232 --watch
```

Useful options include `--codex-path`, `--profile`, `--server-port`, `--open`,
and `--once`. The Companion is macOS-first and relies on Codex DOM selectors
that may change. The core Skill and stdio MCP workflow are the portable path.

## Development and verification

Run these checks from the repository root or this package directory:

```bash
cd plugins/branch-keeper
python3 -m unittest discover -s tests -v
node --check scripts/branch_keeper_launcher.mjs
node --check companion/codex-injector.mjs
```

The tests use temporary directories and do not modify the personal Branch
Keeper database. The MCP server uses Python's standard library at runtime;
the optional test suite may use additional test-only dependencies documented
by the repository.

## Release packaging

A public release keeps three references aligned:

1. `version` in `.codex-plugin/plugin.json`;
2. the Git tag and GitHub Release;
3. `source.ref` in `../../.agents/plugins/marketplace.json`.

For a new version, update the manifest and Marketplace ref, run the checks,
commit and push the changes, then create the matching tag and GitHub Release.
For example:

```bash
git tag -a v0.3.0 -m "Branch Keeper 0.3.0"
git push origin v0.3.0
gh release create v0.3.0 \
  --title "Branch Keeper 0.3.0" \
  --generate-notes
```

The Marketplace ref must point to an existing tag. Users can install directly
from the GitHub-backed Marketplace without a separate remote MCP deployment.

## License

Branch Keeper is released under the [MIT License](../../LICENSE).
