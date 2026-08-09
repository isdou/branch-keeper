# Branch Keeper

> Keep the product paths you did not take.

[![Latest release](https://img.shields.io/github/v/release/isdou/branch-keeper?display_name=tag&sort=semver)](https://github.com/isdou/branch-keeper/releases)
[![License](https://img.shields.io/github/license/isdou/branch-keeper)](LICENSE)

Branch Keeper is a local-first plugin for Codex and Antigravity. It helps you
save a promising product direction when an AI conversation gives you several
paths, but you decide to explore only one for now.

It records:

- what the direction is;
- why it is worth keeping;
- why it is not being pursued now;
- what to ask or do next;
- when it should be revisited.

This is not a general AI memory app, clipping inbox, or task manager. It is a
small decision-branch system for product work.

## Install

### Codex

Requirements: Node.js 18+ and Python 3.10+.

Install the current GitHub release:

```bash
codex plugin marketplace add isdou/branch-keeper@v0.2.0
codex plugin add branch-keeper@branch-keeper
```

Restart Codex, enable **Branch Keeper** from the Plugins directory, and start a
new task.

If Python is installed in a non-standard location:

```bash
export BRANCH_KEEPER_PYTHON=/absolute/path/to/python3
```

### Antigravity

Use the [`plugins/branch-keeper`](plugins/branch-keeper) directory as the
plugin package. It contains the Antigravity manifest, MCP configuration, and
Skill.

## How to use it

In any product conversation, ask:

```text
Find the valuable product directions we are not pursuing right now.
Do not save anything until I confirm them.
```

After reviewing the suggestions:

```text
Save the confirmed directions with why we are keeping them,
why we are parking them, the next question, and the revisit trigger.
```

Later:

```text
Show me my unfinished product branches and resume the one about [direction].
```

The Skill is globally available because useful branches can appear in any
conversation. It asks for confirmation before saving and is intended to stay
selective rather than interrupt every task.

## Privacy and storage

Branch Keeper runs locally. The core plugin does not upload branch content and
does not require an account, API key, or cloud service.

Data is stored in:

```text
~/.branch-keeper/branches.sqlite3
```

You can change the location with `BRANCH_KEEPER_HOME` or
`BRANCH_KEEPER_DB_PATH`.

The optional Codex Companion displays a local board and is not required for the
core workflow. It is currently macOS-first.

## Learn more

- [Latest releases](https://github.com/isdou/branch-keeper/releases)
- [Plugin package documentation](plugins/branch-keeper/README.md)
- [Issues and discussions](https://github.com/isdou/branch-keeper/issues)

## License

MIT
