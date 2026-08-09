#!/usr/bin/env python3
"""Local HTTP board for the Branch Keeper Codex companion.

The companion deliberately reuses the plugin's stdlib-only SQLite/MCP module
instead of introducing a second database or a cloud dependency.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


COMPANION_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = COMPANION_DIR.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import branch_keeper_mcp as branch_keeper  # noqa: E402


BOARD_FILE = COMPANION_DIR / "board.html"


def query_value(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name) or []
    return values[0] if values else None


def bool_query(query: dict[str, list[str]], name: str, default: bool = False) -> bool:
    value = query_value(query, name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def branch_from_id(branch_id: str) -> dict[str, Any] | None:
    connection = branch_keeper.connect()
    try:
        return branch_keeper.get_branch(connection, branch_id)
    finally:
        connection.close()


class BoardHandler(BaseHTTPRequestHandler):
    server_version = "BranchKeeperCompanion/0.2"

    def log_message(self, format: str, *args: object) -> None:
        if getattr(self.server, "verbose", False):
            super().log_message(format, *args)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, PUT, OPTIONS")
        super().end_headers()

    def send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value: Any, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_bytes(body, "application/json; charset=utf-8", status)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"error": message}, status)

    def read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("invalid content length") from error
        if length > 1_000_000:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be an object")
        return value

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path in {"/", "/index.html"}:
            try:
                self.send_bytes(BOARD_FILE.read_bytes(), "text/html; charset=utf-8")
            except OSError as error:
                self.send_error_json(f"board unavailable: {error}", 500)
            return

        if parsed.path == "/health":
            self.send_json({"ok": True, "service": "branch-keeper-companion", "version": "0.2.0"})
            return

        if parsed.path == "/api/branches":
            arguments: dict[str, Any] = {
                "status": query_value(query, "status"),
                "lifecycle_status": query_value(query, "lifecycle_status"),
                "review_state": query_value(query, "review_state"),
                "attention_state": query_value(query, "attention_state"),
                "project_name": query_value(query, "project_name"),
                "source_host": query_value(query, "source_host"),
                "source_conversation_id": query_value(query, "source_conversation_id"),
                "parent_id": query_value(query, "parent_id"),
                "include_context": bool_query(query, "include_context"),
                "include_resolved": bool_query(query, "include_resolved"),
                "limit": query_value(query, "limit") or 200,
            }
            search_query = query_value(query, "q") or query_value(query, "query")
            if search_query:
                arguments["query"] = search_query
                branches = branch_keeper.select_branches(arguments, search=True)
            else:
                branches = branch_keeper.select_branches(arguments)
            self.send_json({"branches": branches, "count": len(branches)})
            return

        if parsed.path.startswith("/api/branches/"):
            branch_id = parsed.path.removeprefix("/api/branches/").strip("/")
            if branch_id and "/" not in branch_id:
                connection = branch_keeper.connect()
                try:
                    branch = branch_keeper.get_branch(
                        connection,
                        branch_id,
                        include_events=True,
                        include_sessions=True,
                    )
                finally:
                    connection.close()
                if branch:
                    self.send_json({"branch": branch})
                else:
                    self.send_error_json("branch not found", 404)
                return

        self.send_error_json("not found", 404)

    def do_POST(self) -> None:  # noqa: N802
        self.handle_branch_mutation()

    def do_PATCH(self) -> None:  # noqa: N802
        self.handle_branch_mutation()

    def do_PUT(self) -> None:  # noqa: N802
        self.handle_branch_mutation()

    def handle_branch_mutation(self) -> None:
        parsed = urlparse(self.path)
        resume_prefix = "/api/resumes/"
        if parsed.path.startswith(resume_prefix):
            suffix = parsed.path.removeprefix(resume_prefix).strip("/").split("/")
            if suffix and suffix[0] and len(suffix) > 1 and suffix[1] == "result":
                try:
                    payload = self.read_json()
                    result = branch_keeper.record_resume_result(
                        {**payload, "resume_id": suffix[0]}
                    )
                    self.send_json(result)
                except (ValueError, TypeError, OSError) as error:
                    self.send_error_json(str(error), 400)
                except Exception as error:  # pragma: no cover - defensive HTTP boundary
                    self.send_error_json(str(error), 500)
                return

        prefix = "/api/branches/"
        if not parsed.path.startswith(prefix):
            self.send_error_json("not found", 404)
            return

        suffix = parsed.path.removeprefix(prefix).strip("/").split("/")
        if not suffix or not suffix[0]:
            self.send_error_json("branch id is required")
            return

        branch_id = suffix[0]
        action = suffix[1] if len(suffix) > 1 else "update"
        try:
            payload = self.read_json()
            if action == "resume" and self.command == "POST":
                result = branch_keeper.resume_branch({**payload, "branch_id": branch_id})
            elif action == "resume" and self.command in {"PATCH", "PUT"}:
                result = branch_keeper.record_resume_result({"resume_id": payload.get("resume_id"), **payload})
            elif action == "status" and self.command == "POST":
                result = branch_keeper.update_branch(
                    {**payload, "branch_id": branch_id}
                )
            elif action == "update":
                result = branch_keeper.update_branch({**payload, "branch_id": branch_id})
            else:
                self.send_error_json("unsupported branch action", 405)
                return
            self.send_json(result)
        except (ValueError, TypeError, OSError) as error:
            self.send_error_json(str(error), 400)
        except Exception as error:  # pragma: no cover - defensive HTTP boundary
            self.send_error_json(str(error), 500)


def main() -> None:
    parser = argparse.ArgumentParser(description="Branch Keeper local companion board server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), BoardHandler)
    server.verbose = args.verbose
    host, port = server.server_address
    print(
        json.dumps(
            {
                "ready": True,
                "host": host,
                "port": port,
                "url": f"http://{host}:{port}/",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
