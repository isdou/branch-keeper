# Branch Keeper

> Keep the product paths you didn't take.

Branch Keeper is a Codex/Antigravity plugin for product conversations. When an
AI suggests several directions and you pursue only one, Branch Keeper helps you
preserve the others with:

- why the direction is worth keeping;
- why it is not being pursued now;
- the next question or action;
- the condition that should bring it back.

It is not a general AI memory or a clipping inbox. It is a local-first manager
for product decision branches that can be resumed as a clean Codex task later.

## Install from this marketplace

```bash
codex plugin marketplace add isdou/branch-keeper
codex plugin add branch-keeper@branch-keeper
```

Restart Codex and open the Plugins directory to enable Branch Keeper. Start a
new task after installation so the Skill and MCP tools are loaded.

The plugin uses a Node.js launcher to locate Python automatically. Node.js and
Python 3.10+ are required; set `BRANCH_KEEPER_PYTHON` if Python is installed
under a non-standard path.

## Try it

Use a real product discussion, then ask Codex:

```text
Find the valuable product directions we are not pursuing right now.
Ask me to confirm them, then save the confirmed branches with why we are
parking them and what we should ask next.
```

Later:

```text
Show me my unfinished product branches and resume the one about [direction].
```

## What it stores

Branch Keeper stores data locally in SQLite by default at
`~/.branch-keeper/branches.sqlite3`. It does not send branch content to a
remote service. Saving requires user confirmation, and the Skill does not
automatically modify project files or begin implementation.

The lifecycle is intentionally small: `parked`, `exploring`, `adopted`,
`merged`, and `abandoned`. Review, attention, blockers, resume operations, and
the event timeline are tracked separately.

## Package contents

The plugin lives under [`plugins/branch-keeper`](./plugins/branch-keeper). It
includes the global Skill, local MCP server, tests, and an optional macOS-first
Codex Companion with a native-looking board surface.

## Development

```bash
cd plugins/branch-keeper
python3 -m unittest discover -s tests -v
```

The Companion is optional and currently targets macOS Codex desktop builds.

## Privacy

Branch Keeper is local-first. Review the plugin source and local MCP
configuration before enabling it in a workspace with sensitive product data.

## License

MIT
