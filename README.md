# Branch Keeper

> Save the product directions you are not taking — with the reason, the next question, and a path back.

[![Latest release](https://img.shields.io/github/v/release/isdou/branch-keeper?display_name=tag&sort=semver)](https://github.com/isdou/branch-keeper/releases)
[![License](https://img.shields.io/github/license/isdou/branch-keeper)](LICENSE)
[![Intent-Preserving Protocol](https://img.shields.io/badge/IPP-Compliant-success.svg)](https://github.com/isdou/intent-preserving-protocol)

When an AI conversation gives you several promising product directions, you
usually explore one and lose the others in the chat history. Branch Keeper
keeps those deferred directions structured and ready to resume.

It is not a general AI memory app, clipping inbox, or task manager. It is a
small decision-branch tool for product work.

## Design Philosophy / 设计哲学

> *"Why structured decision branches over transient chat history?"*

Agent sessions are stateless by nature. When a generative discussion branches into multiple viable paths, exploring one almost always means discarding the rest to transcript oblivion. 

As highlighted in Anthropic & Warp's engineering pattern [*How Warp builds self-improving agents on Claude*](https://claude.com/blog/how-warp-builds-self-improving-agents-on-claude), sustainable agentic workflows require durable, inspectable artifacts where human signals compound over time rather than resetting every session.

Branch Keeper applies this philosophy to product decision architecture:

- **Preserve Non-Chosen Branches**: Structured capture of *why it was kept*, *why not now*, and the exact *revisit trigger*.
- **Explicit Human Confirmation**: No silent saves, no AI auto-decisions. Every parked branch is confirmed by the builder.
- **Clean Resume Protocol**: Restores context and next actionable questions into fresh tasks without baggage or context drift.

## Install

### Codex

Requirements: Node.js 18+ and Python 3.10+.

Install the current GitHub release:

```bash
codex plugin marketplace add isdou/branch-keeper@v0.2.0
codex plugin add branch-keeper@branch-keeper
```

Restart Codex, enable **Branch Keeper** in the Plugins directory, and start a
new task.

If Python is not on your `PATH`:

```bash
export BRANCH_KEEPER_PYTHON=/absolute/path/to/python3
```

### Antigravity

Clone the repository and use the [`plugins/branch-keeper`](plugins/branch-keeper)
directory as the plugin package:

```bash
git clone https://github.com/isdou/branch-keeper.git
```

## Start using it

In a product conversation, ask:

```text
Find the valuable product directions we are not pursuing right now.
Do not save anything until I confirm them.
```

After reviewing the suggestions:

```text
Save the confirmed directions with why we are keeping them,
why we are parking them, the next question, and the revisit trigger.
```

Later, in a new task:

```text
Show me my unfinished product branches and resume the one about [direction].
```

The Skill is globally available because useful branches can appear in any
product conversation. It suggests selectively and asks for confirmation before
saving anything.

## What it keeps

- The product direction
- Why it is worth keeping
- Why it is not the current path
- The next question or action
- The condition for revisiting it
- Project and conversation context

## Privacy

Branch Keeper runs locally. The core plugin does not upload branch content and
does not require an account, API key, or cloud service.

Data is stored in a local SQLite database:

```text
~/.branch-keeper/branches.sqlite3
```

The optional Codex Companion adds a local board and sidebar-style entry. It is
not required for the core workflow and is currently macOS-first.

## Links

- [Latest release](https://github.com/isdou/branch-keeper/releases)
- [Plugin documentation](plugins/branch-keeper/README.md)
- [Issues](https://github.com/isdou/branch-keeper/issues)

## License

MIT
