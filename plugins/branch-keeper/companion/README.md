# Branch Keeper Codex Companion

This directory contains the macOS-first Companion that gives Branch Keeper a Codex sidebar entry and board UI.

## Run

From the plugin root:

```bash
node companion/codex-injector.mjs --launch --watch
```

The launcher starts a separate Codex profile with a loopback CDP port, starts the local board server, and injects `codex-inject.user.js` into Codex pages. The first launch may require signing into the separate profile.

To attach to an existing Codex process, start that process with a loopback remote debugging port and run:

```bash
node companion/codex-injector.mjs --port 9232 --watch
```

The board server only binds to `127.0.0.1`. The injected iframe receives a per-run capability token, and the parent page accepts messages only from that iframe with the matching token.

## Scope

- Clones the native-looking Plugins sidebar row when available.
- Falls back to a small floating entry when Codex's sidebar markers are not found.
- Mounts the local board in the Codex main content area.
- Lets users update lifecycle status, review blockers/attention badges, resume a branch, and prepare a continuation prompt in a new Codex task.
- Records whether the Codex composer handoff succeeded or failed; a successful
  handoff moves a parked branch to exploring, while a failed handoff keeps it
  parked and leaves a fallback event.
- Branch detail APIs expose the event timeline and resume-session history.
- Does not auto-submit prompts, modify the Codex app bundle, or silently write branch records.
