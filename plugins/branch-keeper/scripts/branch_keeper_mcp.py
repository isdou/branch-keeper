#!/usr/bin/env python3
"""Stdlib-only MCP server for Branch Keeper.

Branch Keeper stores product decision branches locally. The data model keeps
the business lifecycle separate from review state, attention state, resume
operations, and the event history that explains how a branch got here.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SERVER_NAME = "branch-keeper"
SERVER_VERSION = "0.2.0"

LIFECYCLE_STATUSES = {"parked", "exploring", "adopted", "merged", "abandoned"}
LEGACY_STATUS_ALIASES = {"decided": "adopted", "converted": "adopted"}
RESOLVED_STATUSES = {"adopted", "merged", "abandoned"}
REVIEW_STATES = {"confirmed", "needs_review"}
ATTENTION_STATES = {"normal", "due", "stale", "blocked"}
OPERATION_STATUSES = {"idle", "prompt_ready", "task_launching", "succeeded", "failed"}
RESUME_RESULT_STATUSES = {"succeeded", "failed"}
ACTIVE_STATUSES = {"parked", "exploring"}
SOFT_BATCH_LIMIT = 5
SOFT_PROJECT_LIMIT = 15
STALE_AFTER_DAYS = 30

ALLOWED_TRANSITIONS = {
    "parked": {"exploring", "adopted", "merged", "abandoned"},
    "exploring": {"parked", "adopted", "merged", "abandoned"},
    "adopted": {"parked", "exploring"},
    "merged": {"parked"},
    "abandoned": {"parked"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid.uuid4())


def data_home() -> Path:
    configured = os.environ.get("BRANCH_KEEPER_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".branch-keeper"


def database_path() -> Path:
    configured = os.environ.get("BRANCH_KEEPER_DB_PATH")
    return Path(configured).expanduser() if configured else data_home() / "branches.sqlite3"


def normalize_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    status = LEGACY_STATUS_ALIASES.get(status, status)
    if status not in LIFECYCLE_STATUSES:
        raise ValueError(f"unsupported lifecycle status: {value}")
    return status


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        raw = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)).strip()


def branch_fingerprint(item: dict[str, Any]) -> str:
    parts = [
        normalize_text(item.get("project_name")),
        normalize_text(item.get("title")),
        normalize_text(item.get("why_saved")),
        normalize_text(item.get("next_question")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def connection_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_column(connection: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    if name not in connection_columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")  # noqa: S608


def migrate_schema(connection: sqlite3.Connection) -> None:
    branch_columns = {
        "review_state": "TEXT NOT NULL DEFAULT 'confirmed'",
        "attention_state": "TEXT NOT NULL DEFAULT 'normal'",
        "operation_status": "TEXT NOT NULL DEFAULT 'idle'",
        "blocked_reason": "TEXT",
        "blocked_by": "TEXT",
        "review_at": "TEXT",
        "snooze_until": "TEXT",
        "last_resumed_at": "TEXT",
        "last_activity_at": "TEXT",
        "execution_link": "TEXT",
        "duplicate_of": "TEXT",
        "supersedes": "TEXT",
        "merged_into": "TEXT",
        "outcome_type": "TEXT",
        "workspace_path": "TEXT",
        "repo_fingerprint": "TEXT",
        "fingerprint": "TEXT",
    }
    for name, definition in branch_columns.items():
        ensure_column(connection, "branches", name, definition)

    event_columns = {
        "actor_type": "TEXT NOT NULL DEFAULT 'system'",
        "from_status": "TEXT",
        "to_status": "TEXT",
        "related_branch_id": "TEXT",
        "related_task_id": "TEXT",
        "correlation_id": "TEXT",
    }
    for name, definition in event_columns.items():
        ensure_column(connection, "events", name, definition)

    connection.execute(
        "UPDATE branches SET status = 'adopted' WHERE kind = 'direction' AND status = 'decided'"
    )
    connection.execute(
        """
        UPDATE branches
        SET status = 'adopted', operation_status = 'succeeded'
        WHERE kind = 'direction' AND status = 'converted'
        """
    )
    connection.execute(
        """
        UPDATE branches
        SET last_activity_at = COALESCE(last_activity_at, updated_at, created_at)
        WHERE last_activity_at IS NULL
        """
    )
    connection.execute("UPDATE branches SET review_state = 'confirmed' WHERE review_state IS NULL")
    connection.execute("UPDATE branches SET operation_status = 'idle' WHERE operation_status IS NULL")
    connection.execute("PRAGMA user_version = 2")


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS branches (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('context', 'direction')),
            type TEXT NOT NULL DEFAULT 'product-direction',
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            parent_id TEXT REFERENCES branches(id) ON DELETE SET NULL,
            project_id TEXT,
            project_name TEXT,
            source_host TEXT,
            source_conversation_id TEXT,
            source_url TEXT,
            source_excerpt TEXT,
            why_saved TEXT,
            why_not_now TEXT,
            next_question TEXT,
            next_action TEXT,
            revisit_trigger TEXT,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            confidence REAL,
            outcome TEXT,
            outcome_rationale TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            review_state TEXT NOT NULL DEFAULT 'confirmed',
            attention_state TEXT NOT NULL DEFAULT 'normal',
            operation_status TEXT NOT NULL DEFAULT 'idle',
            blocked_reason TEXT,
            blocked_by TEXT,
            review_at TEXT,
            snooze_until TEXT,
            last_resumed_at TEXT,
            last_activity_at TEXT,
            execution_link TEXT,
            duplicate_of TEXT,
            supersedes TEXT,
            merged_into TEXT,
            outcome_type TEXT,
            workspace_path TEXT,
            repo_fingerprint TEXT,
            fingerprint TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_branches_status ON branches(status);
        CREATE INDEX IF NOT EXISTS idx_branches_parent ON branches(parent_id);
        CREATE INDEX IF NOT EXISTS idx_branches_project ON branches(project_name);
        CREATE INDEX IF NOT EXISTS idx_branches_source ON branches(source_conversation_id);

        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            branch_id TEXT NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            actor_type TEXT NOT NULL DEFAULT 'system',
            from_status TEXT,
            to_status TEXT,
            related_branch_id TEXT,
            related_task_id TEXT,
            correlation_id TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_events_branch ON events(branch_id);
        CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

        CREATE TABLE IF NOT EXISTS resume_sessions (
            id TEXT PRIMARY KEY,
            branch_id TEXT NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
            task_id TEXT,
            resume_mode TEXT NOT NULL DEFAULT 'discussion',
            operation_status TEXT NOT NULL,
            prompt_snapshot TEXT NOT NULL,
            result_summary TEXT,
            proposed_status TEXT,
            proposed_next_action TEXT,
            proposed_outcome TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_resume_branch ON resume_sessions(branch_id);
        CREATE INDEX IF NOT EXISTS idx_resume_created ON resume_sessions(created_at);
        """
    )
    migrate_schema(connection)
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_branches_attention ON branches(attention_state);
        CREATE INDEX IF NOT EXISTS idx_branches_fingerprint ON branches(fingerprint);
        """
    )
    connection.commit()
    return connection


def as_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def compute_attention_state(branch: dict[str, Any]) -> str:
    if branch.get("kind") == "context" or branch.get("status") in RESOLVED_STATUSES:
        return "normal"
    if branch.get("blocked_reason"):
        return "blocked"
    snooze_until = parse_datetime(branch.get("snooze_until"))
    if snooze_until and snooze_until > datetime.now(timezone.utc):
        return "normal"
    if branch.get("review_state") == "needs_review":
        return "due"
    review_at = parse_datetime(branch.get("review_at"))
    if review_at and review_at <= datetime.now(timezone.utc):
        return "due"
    last_activity = parse_datetime(branch.get("last_activity_at") or branch.get("updated_at"))
    if last_activity and datetime.now(timezone.utc) - last_activity >= timedelta(days=STALE_AFTER_DAYS):
        return "stale"
    return "normal"


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    result = dict(row)
    try:
        result["evidence"] = json.loads(result.pop("evidence_json"))
    except (TypeError, json.JSONDecodeError):
        result["evidence"] = []
    result["lifecycle_status"] = None if result.get("kind") == "context" else result.get("status")
    result["attention_state"] = compute_attention_state(result)
    return result


def get_events(
    connection: sqlite3.Connection,
    branch_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    rows = connection.execute(
        "SELECT * FROM events WHERE branch_id = ? ORDER BY created_at DESC LIMIT ?",
        (branch_id, safe_limit),
    ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        try:
            event["payload"] = json.loads(event.pop("payload_json"))
        except (TypeError, json.JSONDecodeError):
            event["payload"] = {}
        events.append(event)
    return events


def get_branch(
    connection: sqlite3.Connection,
    branch_id: str,
    *,
    include_events: bool = False,
    include_sessions: bool = False,
) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM branches WHERE id = ?", (branch_id,)).fetchone()
    branch = row_to_dict(row)
    if not branch:
        return None
    if include_events:
        branch["events"] = get_events(connection, branch_id)
    if include_sessions:
        branch["resume_sessions"] = get_resume_sessions(connection, branch_id)
    return branch


def get_resume_sessions(connection: sqlite3.Connection, branch_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM resume_sessions WHERE branch_id = ? ORDER BY created_at DESC LIMIT ?",
        (branch_id, max(1, min(int(limit), 200))),
    ).fetchall()
    return [dict(row) for row in rows]


def add_event(
    connection: sqlite3.Connection,
    branch_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    actor_type: str = "system",
    from_status: str | None = None,
    to_status: str | None = None,
    related_branch_id: str | None = None,
    related_task_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    event_id = new_id()
    timestamp = now_iso()
    connection.execute(
        """
        INSERT INTO events (
            id, branch_id, event_type, actor_type, from_status, to_status,
            related_branch_id, related_task_id, correlation_id, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            branch_id,
            event_type,
            actor_type,
            from_status,
            to_status,
            related_branch_id,
            related_task_id,
            correlation_id,
            as_json(payload or {}),
            timestamp,
        ),
    )
    connection.execute(
        "UPDATE branches SET updated_at = ?, last_activity_at = ? WHERE id = ?",
        (timestamp, timestamp, branch_id),
    )
    return event_id


def active_count(connection: sqlite3.Connection, project_name: str | None) -> int:
    if project_name:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM branches WHERE kind = 'direction' AND project_name = ? AND status IN (?, ?)",
            (project_name, "parked", "exploring"),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM branches WHERE kind = 'direction' AND project_name IS NULL AND status IN (?, ?)",
            ("parked", "exploring"),
        ).fetchone()
    return int(row["count"]) if row else 0


def find_duplicate_candidates(
    connection: sqlite3.Connection,
    item: dict[str, Any],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    project_name = item.get("project_name")
    if project_name:
        rows = connection.execute(
            """
            SELECT * FROM branches
            WHERE kind = 'direction' AND project_name = ? AND status IN (?, ?)
            ORDER BY updated_at DESC LIMIT 200
            """,
            (project_name, "parked", "exploring"),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM branches
            WHERE kind = 'direction' AND status IN (?, ?)
            ORDER BY updated_at DESC LIMIT 200
            """,
            ("parked", "exploring"),
        ).fetchall()

    target_fp = branch_fingerprint(item)
    target_text = " ".join(
        normalize_text(item.get(key)) for key in ("title", "why_saved", "next_question")
    )
    matches: list[dict[str, Any]] = []
    for row in rows:
        branch = row_to_dict(row) or {}
        candidate_text = " ".join(
            normalize_text(branch.get(key)) for key in ("title", "why_saved", "next_question")
        )
        similarity = 1.0 if target_fp and target_fp == branch.get("fingerprint") else difflib.SequenceMatcher(
            None,
            target_text,
            candidate_text,
        ).ratio()
        if similarity >= 0.82:
            matches.append(
                {
                    "branch_id": branch.get("id"),
                    "title": branch.get("title"),
                    "similarity": round(similarity, 3),
                    "project_name": branch.get("project_name"),
                }
            )
    return sorted(matches, key=lambda item: item["similarity"], reverse=True)[:limit]


def insert_branch(
    connection: sqlite3.Connection,
    item: dict[str, Any],
    *,
    kind: str,
    parent_id: str | None = None,
    default_status: str = "parked",
) -> dict[str, Any]:
    title = str(item.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    if kind not in {"context", "direction"}:
        raise ValueError("kind must be context or direction")

    if kind == "direction":
        status = normalize_status(item.get("status") or default_status)
        review_state = str(item.get("review_state") or "confirmed").strip()
        if review_state not in REVIEW_STATES:
            raise ValueError(f"unsupported review state: {review_state}")
    else:
        status = "context"
        review_state = "confirmed"

    branch_id = str(item.get("id") or new_id())
    timestamp = now_iso()
    evidence = item.get("evidence", [])
    if not isinstance(evidence, (list, dict)):
        evidence = [str(evidence)]
    fingerprint = str(item.get("fingerprint") or (branch_fingerprint(item) if kind == "direction" else ""))

    connection.execute(
        """
        INSERT INTO branches (
            id, kind, type, title, status, parent_id, project_id, project_name,
            source_host, source_conversation_id, source_url, source_excerpt,
            why_saved, why_not_now, next_question, next_action, revisit_trigger,
            evidence_json, confidence, outcome, outcome_rationale, created_at, updated_at,
            review_state, attention_state, operation_status, blocked_reason, blocked_by,
            review_at, snooze_until, last_resumed_at, last_activity_at, execution_link,
            duplicate_of, supersedes, merged_into, outcome_type, workspace_path,
            repo_fingerprint, fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            branch_id,
            kind,
            str(item.get("type") or "product-direction"),
            title,
            status,
            parent_id,
            item.get("project_id"),
            item.get("project_name"),
            item.get("source_host"),
            item.get("source_conversation_id"),
            item.get("source_url"),
            item.get("source_excerpt"),
            item.get("why_saved"),
            item.get("why_not_now"),
            item.get("next_question"),
            item.get("next_action"),
            item.get("revisit_trigger"),
            as_json(evidence),
            item.get("confidence"),
            item.get("outcome"),
            item.get("outcome_rationale"),
            timestamp,
            timestamp,
            review_state,
            "normal",
            "idle",
            item.get("blocked_reason"),
            item.get("blocked_by"),
            item.get("review_at"),
            item.get("snooze_until"),
            item.get("last_resumed_at"),
            timestamp,
            item.get("execution_link"),
            item.get("duplicate_of"),
            item.get("supersedes"),
            item.get("merged_into"),
            item.get("outcome_type"),
            item.get("workspace_path"),
            item.get("repo_fingerprint"),
            fingerprint,
        ),
    )
    add_event(
        connection,
        branch_id,
        "branch_created",
        {"kind": kind, "review_state": review_state},
        actor_type="user",
        to_status=None if kind == "context" else status,
    )
    return get_branch(connection, branch_id)  # type: ignore[return-value]


def park_branches(arguments: dict[str, Any]) -> dict[str, Any]:
    items = arguments.get("branches")
    if not isinstance(items, list) or not items:
        raise ValueError("branches must be a non-empty list")

    root_input = arguments.get("context") or {}
    if not isinstance(root_input, dict):
        raise ValueError("context must be an object")
    root_title = str(root_input.get("title") or "Discussion context").strip()

    connection = connect()
    try:
        warnings: list[str] = []
        if len(items) > SOFT_BATCH_LIMIT:
            warnings.append(
                f"This batch contains {len(items)} directions; the soft limit is {SOFT_BATCH_LIMIT}. Saving is still allowed."
            )

        project_counts: dict[str | None, int] = {}
        duplicate_suggestions: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("each branch must be an object")
            project_name = item.get("project_name") or root_input.get("project_name")
            project_counts[project_name] = active_count(connection, project_name)
            matches = find_duplicate_candidates(connection, {**root_input, **item, "project_name": project_name})
            if matches:
                duplicate_suggestions.append(
                    {
                        "title": item.get("title"),
                        "matches": matches,
                        "message": "Possible duplicate; review before merging.",
                    }
                )

        root = insert_branch(
            connection,
            {
                **root_input,
                "title": root_title,
                "type": "discussion-context",
            },
            kind="context",
            default_status="context",
        )
        branches = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("each branch must be an object")
            branch = insert_branch(
                connection,
                {
                    **root_input,
                    **item,
                    "review_state": "confirmed",
                },
                kind="direction",
                parent_id=root["id"],
            )
            branches.append(branch)

        for project_name, count in project_counts.items():
            projected = count + sum(
                1
                for item in items
                if (item.get("project_name") or root_input.get("project_name")) == project_name
            )
            if projected > SOFT_PROJECT_LIMIT:
                label = project_name or "unassigned"
                warnings.append(
                    f"Project '{label}' will have {projected} active branches; the soft limit is {SOFT_PROJECT_LIMIT}. "
                    "Consider reviewing duplicates or stale branches."
                )

        connection.commit()
        return {
            "root": root,
            "branches": branches,
            "count": len(branches),
            "warnings": warnings,
            "duplicate_suggestions": duplicate_suggestions,
            "soft_limits": {
                "batch": SOFT_BATCH_LIMIT,
                "project_active": SOFT_PROJECT_LIMIT,
            },
            "message": f"Saved {len(branches)} product direction(s) under '{root['title']}'.",
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def select_branches(arguments: dict[str, Any], *, search: bool = False) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[Any] = []

    if not arguments.get("include_context", False):
        clauses.append("kind = 'direction'")
    status_value = arguments.get("lifecycle_status", arguments.get("status"))
    normalized_status = None
    if status_value:
        normalized_status = normalize_status(status_value)
        clauses.append("status = ?")
        values.append(normalized_status)
    if arguments.get("project_name"):
        clauses.append("project_name = ?")
        values.append(arguments["project_name"])
    if arguments.get("source_host"):
        clauses.append("source_host = ?")
        values.append(arguments["source_host"])
    if arguments.get("source_conversation_id"):
        clauses.append("source_conversation_id = ?")
        values.append(arguments["source_conversation_id"])
    if arguments.get("parent_id"):
        clauses.append("parent_id = ?")
        values.append(arguments["parent_id"])
    if arguments.get("review_state"):
        if arguments["review_state"] not in REVIEW_STATES:
            raise ValueError(f"unsupported review state: {arguments['review_state']}")
        clauses.append("review_state = ?")
        values.append(arguments["review_state"])
    if not arguments.get("include_resolved", False) and normalized_status not in RESOLVED_STATUSES:
        placeholders = ",".join("?" for _ in RESOLVED_STATUSES)
        clauses.append(f"status NOT IN ({placeholders})")
        values.extend(sorted(RESOLVED_STATUSES))
    if search and arguments.get("query"):
        query = f"%{arguments['query']}%"
        clauses.append(
            """
            (
                title LIKE ? OR why_saved LIKE ? OR why_not_now LIKE ?
                OR next_question LIKE ? OR next_action LIKE ?
                OR revisit_trigger LIKE ? OR source_excerpt LIKE ?
                OR blocked_reason LIKE ?
            )
            """
        )
        values.extend([query] * 8)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        limit = max(1, min(int(arguments.get("limit", 50)), 200))
    except (TypeError, ValueError):
        limit = 50

    connection = connect()
    try:
        rows = connection.execute(
            f"SELECT * FROM branches {where} ORDER BY updated_at DESC LIMIT ?",  # noqa: S608
            (*values, limit),
        ).fetchall()
        branches = [row_to_dict(row) for row in rows]
        attention = arguments.get("attention_state")
        if attention:
            if attention not in ATTENTION_STATES:
                raise ValueError(f"unsupported attention state: {attention}")
            branches = [branch for branch in branches if branch and branch["attention_state"] == attention]
        return [branch for branch in branches if branch]
    finally:
        connection.close()


def resume_prompt(branch: dict[str, Any], *, resume_mode: str = "discussion") -> str:
    source_excerpt = branch.get("source_excerpt") or "No excerpt saved."
    return """
You are resuming a previously parked product direction.

Branch: {title}
Resume mode: {resume_mode}
Why it was preserved: {why_saved}
Why it was not pursued then: {why_not_now}
Current lifecycle: {status}
Next question: {next_question}
Next action: {next_action}
Revisit trigger: {revisit_trigger}
Project: {project_name}
Workspace: {workspace_path}
Known blocker: {blocked_reason}

Selected source excerpt:
{source_excerpt}

Start by answering the next question and clarifying the decision. Do not modify
code or begin implementation unless the user explicitly asks. At the end,
propose a concise status, outcome, and next action for user confirmation.
""".format(
        title=branch.get("title") or "Untitled branch",
        resume_mode=resume_mode,
        why_saved=branch.get("why_saved") or "Not recorded",
        why_not_now=branch.get("why_not_now") or "Not recorded",
        status=branch.get("lifecycle_status") or branch.get("status") or "parked",
        next_question=branch.get("next_question") or "Not recorded",
        next_action=branch.get("next_action") or "Not recorded",
        revisit_trigger=branch.get("revisit_trigger") or "Not recorded",
        project_name=branch.get("project_name") or "Not linked",
        workspace_path=branch.get("workspace_path") or "Not bound",
        blocked_reason=branch.get("blocked_reason") or "None",
        source_excerpt=source_excerpt,
    ).strip()


def resume_branch(arguments: dict[str, Any]) -> dict[str, Any]:
    branch_id = str(arguments.get("branch_id") or "").strip()
    if not branch_id:
        raise ValueError("branch_id is required")
    resume_mode = str(arguments.get("resume_mode") or "discussion").strip()

    connection = connect()
    try:
        branch = get_branch(connection, branch_id)
        if not branch:
            raise ValueError(f"branch not found: {branch_id}")
        if branch.get("status") in RESOLVED_STATUSES:
            raise ValueError("reopen the branch before resuming a resolved direction")

        prompt = resume_prompt(branch, resume_mode=resume_mode)
        resume_id = new_id()
        timestamp = now_iso()
        connection.execute(
            """
            INSERT INTO resume_sessions (
                id, branch_id, task_id, resume_mode, operation_status,
                prompt_snapshot, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resume_id,
                branch_id,
                arguments.get("task_id"),
                resume_mode,
                "prompt_ready",
                prompt,
                timestamp,
            ),
        )
        connection.execute(
            """
            UPDATE branches
            SET operation_status = 'prompt_ready',
                last_resumed_at = ?,
                updated_at = ?,
                last_activity_at = ?
            WHERE id = ?
            """,
            (timestamp, timestamp, timestamp, branch_id),
        )
        event_id = add_event(
            connection,
            branch_id,
            "resume_requested",
            {"resume_id": resume_id, "resume_mode": resume_mode},
            actor_type="user",
            related_task_id=arguments.get("task_id"),
            correlation_id=resume_id,
        )
        connection.commit()
        return {
            "branch": get_branch(connection, branch_id, include_sessions=True),
            "resume_id": resume_id,
            "resumed_event_id": event_id,
            "operation_status": "prompt_ready",
            "continuation_prompt": prompt,
            "message": "Prepared a continuation prompt; lifecycle status remains unchanged until handoff succeeds.",
        }
    finally:
        connection.close()


def record_resume_result(arguments: dict[str, Any]) -> dict[str, Any]:
    resume_id = str(arguments.get("resume_id") or "").strip()
    result_status = str(arguments.get("result_status") or "").strip().lower()
    if not resume_id:
        raise ValueError("resume_id is required")
    if result_status not in RESUME_RESULT_STATUSES:
        raise ValueError(f"unsupported resume result status: {result_status}")

    connection = connect()
    try:
        session_row = connection.execute(
            "SELECT * FROM resume_sessions WHERE id = ?", (resume_id,)
        ).fetchone()
        if not session_row:
            raise ValueError(f"resume session not found: {resume_id}")
        session = dict(session_row)
        branch = get_branch(connection, session["branch_id"])
        if not branch:
            raise ValueError(f"branch not found: {session['branch_id']}")

        if session.get("completed_at"):
            if session.get("operation_status") == result_status:
                return {
                    "resume_session": session,
                    "branch": get_branch(
                        connection,
                        branch["id"],
                        include_events=True,
                        include_sessions=True,
                    ),
                    "message": "Resume result was already recorded.",
                }
            raise ValueError("resume session already has a different result")

        task_id = arguments.get("task_id") or session.get("task_id")
        result_summary = arguments.get("result_summary")
        proposed_status = arguments.get("proposed_status")
        if proposed_status:
            proposed_status = normalize_status(proposed_status)
        timestamp = now_iso()
        connection.execute(
            """
            UPDATE resume_sessions
            SET task_id = ?, operation_status = ?, result_summary = ?,
                proposed_status = ?, proposed_next_action = ?, proposed_outcome = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (
                task_id,
                result_status,
                result_summary,
                proposed_status,
                arguments.get("proposed_next_action"),
                arguments.get("proposed_outcome"),
                timestamp,
                resume_id,
            ),
        )
        connection.execute(
            """
            UPDATE branches
            SET operation_status = ?, execution_link = COALESCE(?, execution_link),
                updated_at = ?, last_activity_at = ?
            WHERE id = ?
            """,
            (
                result_status,
                arguments.get("execution_link"),
                timestamp,
                timestamp,
                branch["id"],
            ),
        )

        if result_status == "succeeded":
            current_status = branch.get("status")
            if current_status == "parked":
                connection.execute(
                    "UPDATE branches SET status = 'exploring' WHERE id = ?",
                    (branch["id"],),
                )
                add_event(
                    connection,
                    branch["id"],
                    "lifecycle_transitioned",
                    {"resume_id": resume_id, "reason": "continuation handoff succeeded"},
                    actor_type="system",
                    from_status="parked",
                    to_status="exploring",
                    related_task_id=task_id,
                    correlation_id=resume_id,
                )
            else:
                add_event(
                    connection,
                    branch["id"],
                    "resume_handoff_succeeded",
                    {"resume_id": resume_id},
                    actor_type="system",
                    related_task_id=task_id,
                    correlation_id=resume_id,
                )
        else:
            add_event(
                connection,
                branch["id"],
                "resume_handoff_failed",
                {
                    "resume_id": resume_id,
                    "result_summary": result_summary,
                    "fallback": "copy continuation prompt",
                },
                actor_type="system",
                related_task_id=task_id,
                correlation_id=resume_id,
            )

        connection.commit()
        return {
            "resume_session": dict(
                connection.execute(
                    "SELECT * FROM resume_sessions WHERE id = ?", (resume_id,)
                ).fetchone()
            ),
            "branch": get_branch(connection, branch["id"], include_events=True, include_sessions=True),
            "message": (
                "Resume handoff succeeded; branch is now exploring."
                if result_status == "succeeded" and branch.get("status") == "parked"
                else "Resume result recorded; branch remains available for review."
            ),
        }
    finally:
        connection.close()


def update_branch(arguments: dict[str, Any]) -> dict[str, Any]:
    branch_id = str(arguments.get("branch_id") or "").strip()
    if not branch_id:
        raise ValueError("branch_id is required")

    allowed = {
        "title",
        "project_id",
        "project_name",
        "source_host",
        "source_conversation_id",
        "source_url",
        "source_excerpt",
        "why_saved",
        "why_not_now",
        "next_question",
        "next_action",
        "revisit_trigger",
        "outcome",
        "outcome_rationale",
        "confidence",
        "evidence",
        "status",
        "lifecycle_status",
        "review_state",
        "operation_status",
        "blocked_reason",
        "blocked_by",
        "review_at",
        "snooze_until",
        "execution_link",
        "duplicate_of",
        "supersedes",
        "merged_into",
        "outcome_type",
        "workspace_path",
        "repo_fingerprint",
    }
    updates = {key: value for key, value in arguments.items() if key in allowed}
    if "lifecycle_status" in updates and "status" not in updates:
        updates["status"] = updates.pop("lifecycle_status")
    if not updates:
        raise ValueError("at least one branch field is required")

    if "status" in updates:
        updates["status"] = normalize_status(updates["status"])
    if "review_state" in updates and updates["review_state"] not in REVIEW_STATES:
        raise ValueError(f"unsupported review state: {updates['review_state']}")
    if "operation_status" in updates and updates["operation_status"] not in OPERATION_STATUSES:
        raise ValueError(f"unsupported operation status: {updates['operation_status']}")
    if "evidence" in updates:
        updates["evidence_json"] = as_json(updates.pop("evidence"))

    connection = connect()
    try:
        current = get_branch(connection, branch_id)
        if not current:
            raise ValueError(f"branch not found: {branch_id}")
        if current.get("kind") == "context" and "status" in updates:
            raise ValueError("context roots do not have a lifecycle status")

        previous_status = current.get("status")
        next_status = updates.get("status", previous_status)
        reason = str(arguments.get("reason") or "").strip()
        if "status" in updates and next_status != previous_status:
            allowed_next = ALLOWED_TRANSITIONS.get(str(previous_status), set())
            if next_status not in allowed_next:
                raise ValueError(f"invalid lifecycle transition: {previous_status} -> {next_status}")
            if next_status in RESOLVED_STATUSES and not (
                reason
                or updates.get("outcome_rationale")
                or current.get("outcome_rationale")
            ):
                raise ValueError(f"{next_status} requires outcome_rationale or reason")
            if next_status == "merged" and not (updates.get("merged_into") or current.get("merged_into")):
                raise ValueError("merged requires merged_into")
            if next_status == "adopted" and not updates.get("outcome_type"):
                updates["outcome_type"] = "adopted"
            if next_status == "abandoned" and not updates.get("outcome_type"):
                updates["outcome_type"] = "abandoned"

        column_names = list(updates)
        set_clause = ", ".join(f"{name} = ?" for name in column_names)
        values = [updates[name] for name in column_names]
        timestamp = now_iso()
        values.extend([timestamp, timestamp, branch_id])
        connection.execute(
            f"UPDATE branches SET {set_clause}, updated_at = ?, last_activity_at = ? WHERE id = ?",  # noqa: S608
            values,
        )

        actor_type = str(arguments.get("actor_type") or "user")
        related_task_id = arguments.get("related_task_id")
        correlation_id = arguments.get("correlation_id")
        status_changed = "status" in updates and updates["status"] != previous_status
        review_changed = "review_state" in updates and updates["review_state"] != current.get("review_state")
        blocked_changed = "blocked_reason" in updates and updates["blocked_reason"] != current.get("blocked_reason")

        if status_changed:
            event_type = "reopened" if next_status == "parked" and previous_status in RESOLVED_STATUSES else "lifecycle_transitioned"
            event_id = add_event(
                connection,
                branch_id,
                event_type,
                {"reason": reason, "changed_fields": sorted(updates)},
                actor_type=actor_type,
                from_status=previous_status,
                to_status=next_status,
                related_task_id=related_task_id,
                correlation_id=correlation_id,
            )
        elif review_changed:
            event_id = add_event(
                connection,
                branch_id,
                "review_state_changed",
                {"from": current.get("review_state"), "to": updates["review_state"]},
                actor_type=actor_type,
                related_task_id=related_task_id,
                correlation_id=correlation_id,
            )
        elif blocked_changed:
            event_id = add_event(
                connection,
                branch_id,
                "blocked" if updates["blocked_reason"] else "unblocked",
                {"reason": updates["blocked_reason"] or reason},
                actor_type=actor_type,
                related_task_id=related_task_id,
                correlation_id=correlation_id,
            )
        elif "snooze_until" in updates:
            event_id = add_event(
                connection,
                branch_id,
                "snoozed",
                {"snooze_until": updates["snooze_until"]},
                actor_type=actor_type,
                related_task_id=related_task_id,
                correlation_id=correlation_id,
            )
        else:
            event_id = add_event(
                connection,
                branch_id,
                "edited",
                {"fields": sorted(updates)},
                actor_type=actor_type,
                related_task_id=related_task_id,
                correlation_id=correlation_id,
            )
        connection.commit()
        return {
            "branch": get_branch(connection, branch_id, include_events=True, include_sessions=True),
            "event_id": event_id,
            "message": "Branch updated.",
        }
    finally:
        connection.close()


def render_branch_board(arguments: dict[str, Any]) -> dict[str, Any]:
    branches = select_branches(
        {
            **arguments,
            "include_resolved": arguments.get("include_resolved", False),
        }
    )
    groups: dict[str, list[dict[str, Any]]] = {}
    for branch in branches:
        key = branch.get("project_name") or "Unassigned"
        groups.setdefault(key, []).append(branch)

    lines = ["# Branch Keeper Board", ""]
    if not branches:
        lines.append("No unfinished product branches found.")
    for project, project_branches in groups.items():
        lines.extend([f"## {project}", ""])
        for branch in project_branches:
            status = branch.get("lifecycle_status") or branch.get("status")
            lines.append(f"- {branch['title']} · {status} · {branch.get('attention_state', 'normal')}")
            if branch.get("next_question"):
                lines.append(f"  - Next question: {branch['next_question']}")
            if branch.get("next_action"):
                lines.append(f"  - Next action: {branch['next_action']}")
            if branch.get("why_not_now"):
                lines.append(f"  - Why parked: {branch['why_not_now']}")
            if branch.get("blocked_reason"):
                lines.append(f"  - Blocked by: {branch['blocked_reason']}")
            if branch.get("review_at"):
                lines.append(f"  - Review at: {branch['review_at']}")
            lines.append(f"  - ID: {branch['id']}")
        lines.append("")

    return {
        "format": "markdown",
        "count": len(branches),
        "groups": groups,
        "markdown": "\n".join(lines).strip(),
    }


TOOL_DEFINITIONS = [
    {
        "name": "park_branches",
        "description": "After explicit user confirmation, save confirmed product directions under one discussion context root. Returns soft-limit warnings and duplicate suggestions without blocking the save.",
        "inputSchema": {
            "type": "object",
            "required": ["branches"],
            "properties": {
                "context": {"type": "object", "description": "Current task/conversation metadata."},
                "branches": {"type": "array", "description": "Confirmed direction records."},
            },
        },
    },
    {
        "name": "list_branches",
        "description": "List unfinished or filtered product direction branches. Supports lifecycle, review, attention, project, host, source, and root filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": sorted(LIFECYCLE_STATUSES | set(LEGACY_STATUS_ALIASES))},
                "lifecycle_status": {"type": "string", "enum": sorted(LIFECYCLE_STATUSES)},
                "review_state": {"type": "string", "enum": sorted(REVIEW_STATES)},
                "attention_state": {"type": "string", "enum": sorted(ATTENTION_STATES)},
                "project_name": {"type": "string"},
                "source_host": {"type": "string"},
                "source_conversation_id": {"type": "string"},
                "parent_id": {"type": "string"},
                "include_context": {"type": "boolean"},
                "include_resolved": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "get_branch",
        "description": "Get one branch with its event timeline and resume sessions.",
        "inputSchema": {
            "type": "object",
            "required": ["branch_id"],
            "properties": {"branch_id": {"type": "string"}},
        },
    },
    {
        "name": "search_branches",
        "description": "Search local product direction branches by title, rationale, next question, action, blocker, or saved excerpt.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "include_resolved": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "resume_branch",
        "description": "Create a resume session, record a resume_requested event, and generate a clean continuation prompt. Lifecycle status changes only after record_resume_result reports a successful handoff.",
        "inputSchema": {
            "type": "object",
            "required": ["branch_id"],
            "properties": {
                "branch_id": {"type": "string"},
                "resume_mode": {"type": "string", "enum": ["discussion", "validation", "comparison"]},
                "task_id": {"type": "string"},
            },
        },
    },
    {
        "name": "record_resume_result",
        "description": "Record whether a continuation handoff succeeded or failed. A successful handoff moves parked to exploring; a failure keeps the branch parked and records a fallback.",
        "inputSchema": {
            "type": "object",
            "required": ["resume_id", "result_status"],
            "properties": {
                "resume_id": {"type": "string"},
                "result_status": {"type": "string", "enum": sorted(RESUME_RESULT_STATUSES)},
                "task_id": {"type": "string"},
                "result_summary": {"type": "string"},
                "execution_link": {"type": "string"},
                "proposed_status": {"type": "string", "enum": sorted(LIFECYCLE_STATUSES)},
                "proposed_next_action": {"type": "string"},
                "proposed_outcome": {"type": "string"},
            },
        },
    },
    {
        "name": "update_branch",
        "description": "Edit a branch or confirm a lifecycle, review, blocker, relation, outcome, or execution-link change. Resolved transitions require a reason or outcome rationale.",
        "inputSchema": {
            "type": "object",
            "required": ["branch_id"],
            "properties": {
                "branch_id": {"type": "string"},
                "status": {"type": "string", "enum": sorted(LIFECYCLE_STATUSES | set(LEGACY_STATUS_ALIASES))},
                "lifecycle_status": {"type": "string", "enum": sorted(LIFECYCLE_STATUSES)},
                "review_state": {"type": "string", "enum": sorted(REVIEW_STATES)},
                "operation_status": {"type": "string", "enum": sorted(OPERATION_STATUSES)},
                "project_name": {"type": "string"},
                "why_saved": {"type": "string"},
                "why_not_now": {"type": "string"},
                "next_question": {"type": "string"},
                "next_action": {"type": "string"},
                "revisit_trigger": {"type": "string"},
                "review_at": {"type": "string"},
                "snooze_until": {"type": "string"},
                "blocked_reason": {"type": "string"},
                "blocked_by": {"type": "string"},
                "outcome": {"type": "string"},
                "outcome_rationale": {"type": "string"},
                "outcome_type": {"type": "string"},
                "execution_link": {"type": "string"},
                "duplicate_of": {"type": "string"},
                "supersedes": {"type": "string"},
                "merged_into": {"type": "string"},
                "source_excerpt": {"type": "string"},
                "evidence": {"type": "array"},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
                "related_task_id": {"type": "string"},
            },
        },
    },
    {
        "name": "render_branch_board",
        "description": "Render unfinished branches as a Markdown board grouped by project with lifecycle, attention, next action, blocker, and review information.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "attention_state": {"type": "string", "enum": sorted(ATTENTION_STATES)},
                "include_resolved": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
]


def result_payload(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}]}


def dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "park_branches":
        return park_branches(arguments)
    if name == "list_branches":
        branches = select_branches(arguments)
        return {"branches": branches, "count": len(branches)}
    if name == "get_branch":
        connection = connect()
        try:
            branch = get_branch(
                connection,
                str(arguments.get("branch_id") or ""),
                include_events=True,
                include_sessions=True,
            )
            if not branch:
                raise ValueError("branch not found")
            return {"branch": branch}
        finally:
            connection.close()
    if name == "search_branches":
        branches = select_branches(arguments, search=True)
        return {"branches": branches, "count": len(branches)}
    if name == "resume_branch":
        return resume_branch(arguments)
    if name == "record_resume_result":
        return record_resume_result(arguments)
    if name == "update_branch":
        return update_branch(arguments)
    if name == "render_branch_board":
        return render_branch_board(arguments)
    raise ValueError(f"unknown tool: {name}")


def rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOL_DEFINITIONS}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            return {"jsonrpc": "2.0", "id": request_id, "result": result_payload(dispatch_tool(name, arguments))}
        except (ValueError, TypeError, sqlite3.Error) as error:
            return rpc_error(request_id, -32602, str(error))
    if request_id is None:
        return None
    return rpc_error(request_id, -32601, f"method not found: {method}")


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            response = handle_message(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as error:
            sys.stdout.write(json.dumps(rpc_error(None, -32700, str(error))) + "\n")
            sys.stdout.flush()
        except Exception as error:  # pragma: no cover - final process guard
            print(f"branch-keeper MCP error: {error}", file=sys.stderr, flush=True)
            sys.stdout.write(json.dumps(rpc_error(None, -32603, str(error))) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
