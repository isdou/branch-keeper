# Branch Keeper

> Keep the product paths you didn't take.

Branch Keeper is a local-first plugin for Codex and Antigravity. It helps you
preserve product directions that surfaced in an AI conversation but are not the
path you are pursuing right now—along with why they matter, why they are
parked, what to ask next, and how to resume them later.

It is intentionally not a generic AI memory app, clipping inbox, or task
manager. Branch Keeper is a small decision-branch system for product work.

[![Latest release](https://img.shields.io/github/v/release/isdou/branch-keeper?display_name=tag&sort=semver)](https://github.com/isdou/branch-keeper/releases)
[![License](https://img.shields.io/github/license/isdou/branch-keeper)](LICENSE)

## The problem

Product conversations branch quickly. An AI may suggest several promising
directions, but you usually explore only one of them. The alternatives often
contain useful insight, yet disappear into the conversation history before you
can return to them.

Branch Keeper turns those alternatives into explicit, reviewable branches:

- what the direction is;
- why it is worth keeping;
- why it is not being pursued now;
- the next question or action;
- the condition that should bring it back;
- the source conversation and project context.

## What it does

- **Proactively spots branches**: the global Skill can surface distinct
  directions that are easy to overlook.
- **Asks before saving**: the Skill proposes candidates, but confirmed product
  directions are saved only after user confirmation.
- **Keeps the rationale**: each branch records the reasoning behind keeping it
  and parking it.
- **Separates state from attention**: lifecycle, review, blocker, and resume
  operation states are tracked independently.
- **Resumes cleanly**: generate a continuation prompt instead of reopening an
  old conversation and reconstructing the context by hand.
- **Warns without creating branch debt**: duplicate suggestions and soft limits
  make branch growth visible without silently discarding anything.
- **Stays local-first**: the core plugin uses a local SQLite database and does
  not upload branch content to a remote service.

## Distribution status

| Channel | Status |
| --- | --- |
| GitHub repository | Available |
| GitHub Release | [v0.2.0](https://github.com/isdou/branch-keeper/releases/tag/v0.2.0) |
| Codex GitHub-backed Marketplace | Available and pinned to `v0.2.0` |
| Universal Plugins Directory | Not required for installation |
| Standalone remote MCP endpoint | Not provided |

The repository contains a bundled **stdio MCP server** as part of the plugin.
It runs on the user's machine and does not expose a public HTTP endpoint. This
is different from a hosted Streamable HTTP MCP server or a standalone package
listed in the [MCP Registry](https://modelcontextprotocol.io/registry/quickstart).

## Install

### Codex

Requirements:

- a Codex host with plugin support;
- Node.js 18 or newer;
- Python 3.10 or newer.

The Node launcher automatically looks for `python3`, `python`, or `py -3` on
Windows. For a reproducible install pinned to the current release:

```bash
codex plugin marketplace add isdou/branch-keeper@v0.2.0
codex plugin add branch-keeper@branch-keeper
```

Restart Codex, open the Plugins directory, enable Branch Keeper, and start a
new task so its Skill and MCP tools are loaded.

To use a non-standard Python installation:

```bash
export BRANCH_KEEPER_PYTHON=/absolute/path/to/python3
```

On PowerShell:

```powershell
$env:BRANCH_KEEPER_PYTHON = "C:\Python312\python.exe"
```

### Antigravity

Use the `plugins/branch-keeper` directory as the plugin package. Antigravity
reads its root `plugin.json`, `mcp_config.json`, and `skills/` directory. The
same Node launcher is used to locate Python and start the local MCP server.

## Quick start

In a product conversation, try:

```text
Find the valuable product directions we are not pursuing right now.
Do not save anything until I confirm the candidates.
```

After reviewing the candidates:

```text
Save the confirmed directions with why they are worth keeping,
why we are not pursuing them now, the next question, and the revisit trigger.
```

Later, in a new task:

```text
Show me my unfinished product branches and group them by project.
```

Then:

```text
Resume the branch about [direction]. Prepare a clean continuation prompt
and tell me what context and next question you are carrying forward.
```

The Skill is designed to be globally available because valuable branches can
appear in any product conversation. It should still stay selective: it is
intended to suggest a branch when the conversation contains a distinct,
deferred direction—not on every ordinary task.

## Branch model

### Lifecycle

| Status | Meaning |
| --- | --- |
| `parked` | Confirmed direction kept for later |
| `exploring` | Direction is actively being investigated |
| `adopted` | Direction has been selected for implementation or validation |
| `merged` | Direction was folded into another branch |
| `abandoned` | Direction was intentionally closed |

### Independent state layers

| Layer | Values | Purpose |
| --- | --- | --- |
| Review | `confirmed`, `needs_review` | Whether the branch has been reviewed by a person |
| Attention | `normal`, `due`, `stale`, `blocked` | Whether it needs attention |
| Resume operation | `idle`, `prompt_ready`, `task_launching`, `succeeded`, `failed` | What happened during continuation |

Resolved transitions require a reason or outcome rationale. Reopening a branch
preserves its previous outcome and event history.

Branch-count limits are intentionally soft:

- more than 5 branches in one capture is flagged for review;
- more than 15 active branches in one project is flagged for review;
- duplicate suggestions are returned instead of silently merging or deleting
  branches.

## MCP tools

The bundled stdio server exposes these tools:

| Tool | Purpose |
| --- | --- |
| `park_branches` | Save confirmed directions under a discussion context |
| `list_branches` | List unfinished or filtered branches |
| `get_branch` | Read a branch with its event timeline and resume sessions |
| `search_branches` | Search titles, rationale, questions, actions, blockers, and excerpts |
| `resume_branch` | Create a resume session and generate a continuation prompt |
| `record_resume_result` | Record whether a continuation handoff succeeded or failed |
| `update_branch` | Edit metadata, states, blockers, outcomes, and relationships |
| `render_branch_board` | Render unfinished branches as a Markdown board grouped by project |

The MCP server communicates over **stdio**. Its entrypoint is
`scripts/branch_keeper_mcp.py`, launched through
`scripts/branch_keeper_launcher.mjs`.

## Storage and privacy

By default, Branch Keeper stores its SQLite database at:

```text
~/.branch-keeper/branches.sqlite3
```

You can change the storage location with either variable:

```bash
export BRANCH_KEEPER_HOME=/path/to/branch-keeper-data
export BRANCH_KEEPER_DB_PATH=/path/to/branches.sqlite3
```

The core server has no cloud database, account system, API key, or hosted
backend. Branch content is kept on the local machine where the MCP server is
running. The optional Companion uses loopback-only HTTP and local CDP
communication to display the board; it does not upload branch data.

Because the server runs with the permissions of the local user, review the
source and configuration before enabling it in a workspace containing
sensitive product strategy.

## Optional Codex Companion

The Companion adds a local board and an optional Codex-side entry point. It is
separate from the core Skill/MCP workflow and is not required to use Branch
Keeper.

From the plugin directory:

```bash
# Launch a separate Codex profile with CDP enabled.
node companion/codex-injector.mjs --launch --watch

# Or attach to a Codex window already started with CDP.
node companion/codex-injector.mjs --port 9232 --watch
```

Useful options:

- `--codex-path <path>` chooses the Codex executable or `.app`;
- `--profile <path>` chooses the persistent launched profile;
- `--server-port <port>` chooses the local board port;
- `--open` opens the board in the default browser;
- `--once` injects once and exits.

The Companion is macOS-first. It uses the local Chromium DevTools Protocol and
DOM selectors that may change as Codex evolves. The core Skill and stdio MCP
server remain the portable fallback.

## Project layout

```text
.
├── .agents/plugins/marketplace.json       # Repo Marketplace entry
├── plugins/branch-keeper/
│   ├── .codex-plugin/plugin.json          # Codex plugin manifest
│   ├── .mcp.json                          # Codex MCP connection
│   ├── mcp_config.json                    # Antigravity MCP connection
│   ├── plugin.json                        # Antigravity plugin metadata
│   ├── skills/branch-keeper/SKILL.md      # Global product-branch workflow
│   ├── scripts/branch_keeper_mcp.py      # Local stdio MCP server
│   ├── scripts/branch_keeper_launcher.mjs # Runtime launcher
│   ├── companion/                         # Optional local Codex board
│   └── tests/                             # MCP and Companion tests
└── LICENSE
```

## Development

Run the test suite from the plugin directory:

```bash
cd plugins/branch-keeper
python3 -m unittest discover -s tests -v
node --check scripts/branch_keeper_launcher.mjs
node --check companion/codex-injector.mjs
```

The tests use temporary directories and do not modify your personal Branch
Keeper database.

## Release and publishing

The public release is made in three connected places:

1. the plugin version in `.codex-plugin/plugin.json`;
2. the GitHub tag and Release;
3. the `ref` in `.agents/plugins/marketplace.json`.

For a new release:

1. Update the plugin version, for example from `0.2.0` to `0.3.0`.
2. Point the Marketplace `source.ref` at the matching tag, such as `v0.3.0`.
3. Run the tests and plugin validation.
4. Commit and push the changes to `main`.
5. Create and push the tag:

   ```bash
   git tag -a v0.3.0 -m "Branch Keeper 0.3.0"
   git push origin v0.3.0
   ```

6. Create the GitHub Release:

   ```bash
   gh release create v0.3.0 \
     --title "Branch Keeper 0.3.0" \
     --generate-notes
   ```

The Marketplace must point to an existing tag before users install the
release. The current public release is [v0.2.0](https://github.com/isdou/branch-keeper/releases/tag/v0.2.0), and the Marketplace is pinned to that tag.

## Contributing

Issues and pull requests are welcome. Before opening a change:

1. keep the local-first privacy boundary intact;
2. add or update tests for behavior changes;
3. document new tools, fields, states, or runtime requirements;
4. run the full test suite and the relevant syntax checks.

For Companion changes, include the Codex build or DOM behavior that was tested.

## License

Branch Keeper is released under the [MIT License](LICENSE).
