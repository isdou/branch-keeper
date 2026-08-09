---
name: branch-keeper
description: Proactively detect valuable product directions that are not being pursued, ask for confirmation, save structured branches locally, and resume them in a clean task later.
---

# Branch Keeper

Branch Keeper is globally available in Codex and Antigravity conversations. It
keeps product directions that are temporarily not being pursued, together with
the reason, the next question, and the condition that should bring them back.
It is not a general AI memory or a transcript clipping tool.

## Core behavior

Use this skill throughout relevant conversations, especially when the user is
discussing a product, requirement, business model, user segment, feature
direction, or implementation strategy.

The skill is globally enabled, but it must be selectively interruptive:

- Look for at least two distinct, concrete, actionable directions.
- Treat a direction as distinct when it changes the target user, problem, value
  proposition, product form, business model, or major trade-off.
- Do not treat wording variants, ordinary implementation steps, or small
  technical alternatives as separate product branches.
- Do not surface a suggestion in a purely factual, debugging, or already-
  decided conversation.
- Do not interrupt while the user is in the middle of a detailed path. Prefer a
  compact suggestion after a substantive answer or at a natural topic boundary.

## Suggestion and confirmation

When the threshold is met, show one compact batch suggestion. Include every
valuable candidate you detected, with:

- a short title;
- why it is worth preserving;
- why it is not being pursued now, when inferable;
- the next question or action;
- the current lifecycle status;
- the source conversation and project, when available.

Ask the user to edit or confirm. Never call `park_branches` or
`park_branches`-equivalent writes before the user confirms. Saving all
candidates after one confirmation is allowed. Soft-limit warnings are useful
context, not a reason to silently drop candidates or block the save.

If the user dismisses the suggestion, do not repeat the same suggestion in the
same task unless the user asks. Offer a quiet or snooze path when the host
supports it.

## Saving branches

After confirmation, call `park_branches` once for the batch whenever possible.
Create one `context` root for the current task/conversation and one `direction`
child for each confirmed candidate.

Required fields for each direction:

- `title`
- `why_saved`
- `next_question`

Populate when available:

- `why_not_now`
- `next_action`
- `revisit_trigger`
- `source_excerpt`
- `evidence`
- `project_name`
- `source_host`
- `source_conversation_id`
- `workspace_path`
- `review_at`

Keep the saved excerpt user-selected or explicitly approved. Do not save an
entire transcript. After saving, inspect `warnings` and
`duplicate_suggestions`; duplicates are suggestions for review, never automatic
merges or deletions.

## State model

Keep these dimensions separate:

- Lifecycle: `parked`, `exploring`, `adopted`, `merged`, `abandoned`.
- Review: `confirmed` or `needs_review`.
- Attention: computed as `normal`, `due`, `stale`, or `blocked`.
- Operation: `idle`, `prompt_ready`, `task_launching`, `succeeded`, or `failed`.

`blocked` is an attention state backed by `blocked_reason` and optionally
`blocked_by`; it is not a replacement lifecycle. `resumed` is an event/action,
not a lifecycle status. `converted` and legacy `decided` inputs are accepted as
compatibility aliases but should not be presented as new statuses.

Normal lifecycle changes are user-confirmed. Resolved states require a reason
or `outcome_rationale`; `merged` also requires `merged_into`. Reopening a
resolved branch returns it to `parked` and preserves the previous outcome and
history. Do not erase the decision trail when reopening.

## Listing and board views

Use `list_branches` for the unfinished inbox, current-conversation branches,
project views, and lifecycle filters. Use `search_branches` for text lookup.
Filter `review_state` or `attention_state` when the user asks what needs review,
what is blocked, or what has gone stale. Use `get_branch` when the user needs a
single branch's event timeline or resume history. Use `render_branch_board`
when the user asks for a visual board, tree, or summary that can be rendered as
Markdown/HTML/Artifact content.

The default view is unfinished branches. A project detail view may show the
context root and its direction children. Keep the board scannable: lifecycle,
attention/review badge, next question/action, blocker, last activity, and
revisit trigger matter more than full evidence.

## Resuming a branch

When the user asks to continue a branch:

1. Call `resume_branch`.
2. Use its structured record and selected source excerpt to create a clean
   continuation prompt or host task.
3. Start with the branch's `next_question`.
4. Do not modify files or start implementation unless the user explicitly asks.
5. After the host actually prepares the new task/composer, call
   `record_resume_result` with `result_status: "succeeded"`. If the handoff
   fails, call it with `result_status: "failed"` so the fallback is visible.

Requesting a resume does not itself change lifecycle. A successful handoff
moves a `parked` branch to `exploring`; a failed handoff leaves it `parked`.
Any proposed outcome, status, or next action returned by the resumed task is a
proposal until the user confirms it with `update_branch`.

The continuation prompt should contain:

- the branch title;
- why it was preserved;
- why it was paused;
- current lifecycle and blocker, if any;
- next question/action;
- revisit trigger;
- selected source excerpt;
- linked project/workspace context, if present.

## Resolving and recording outcomes

Use `update_branch` after the user confirms a meaningful outcome. Record the
chosen direction, rejected alternatives, rationale, evidence, and next action
whenever available. Use `outcome_type`, `outcome`, and `outcome_rationale` for
the durable decision record; use `merged_into`, `duplicate_of`, or `supersedes`
to preserve branch relationships. Do not silently write an ADR, `project.md`,
issue, commit, or external task.

The event timeline should explain what happened: creation, edits, resume
requests and handoff results, lifecycle transitions, reopening, review changes,
blocking/unblocking, snoozing, merges, and other relationship changes.

## Privacy and safety

- Local storage is the default; never send branch data to a remote service
  without explicit configuration.
- Query only the records relevant to the current request rather than injecting
  the whole database.
- Ask for confirmation before writes and before saving sensitive excerpts.
- Redact obvious credentials, access tokens, and personal secrets from excerpts
  when possible.
- Do not silently create external issues, commits, or code changes.
