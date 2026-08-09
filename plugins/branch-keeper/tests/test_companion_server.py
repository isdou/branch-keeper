import json
import os
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "companion"))

import branch_keeper_server as companion  # noqa: E402
import branch_keeper_mcp as branch_keeper  # noqa: E402


class CompanionServerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_home = os.environ.get("BRANCH_KEEPER_HOME")
        os.environ["BRANCH_KEEPER_HOME"] = self.temp_dir.name
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), companion.BoardHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = HTTPConnection("127.0.0.1", self.server.server_port)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        if self.previous_home is None:
            os.environ.pop("BRANCH_KEEPER_HOME", None)
        else:
            os.environ["BRANCH_KEEPER_HOME"] = self.previous_home
        self.temp_dir.cleanup()

    def request_json(self, method, path, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        self.connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = self.connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        return response.status, data

    def test_board_api_lists_and_resumes_branch(self):
        parked = branch_keeper.park_branches(
            {
                "context": {"title": "Companion test", "project_name": "Branch Keeper"},
                "branches": [
                    {
                        "title": "Native sidebar",
                        "why_saved": "Makes the board discoverable.",
                        "next_question": "Which Codex marker is stable enough?",
                    }
                ],
            }
        )
        branch_id = parked["branches"][0]["id"]

        status, listed = self.request_json("GET", "/api/branches")
        self.assertEqual(status, 200)
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["branches"][0]["id"], branch_id)

        status, resumed = self.request_json("POST", f"/api/branches/{branch_id}/resume", {})
        self.assertEqual(status, 200)
        self.assertIn("Which Codex marker", resumed["continuation_prompt"])
        self.assertTrue(resumed["resume_id"])

        status, detail = self.request_json("GET", f"/api/branches/{branch_id}")
        self.assertEqual(status, 200)
        self.assertIn("events", detail["branch"])
        self.assertIn("resume_sessions", detail["branch"])

        status, handed_off = self.request_json(
            "POST",
            f"/api/resumes/{resumed['resume_id']}/result",
            {"result_status": "succeeded", "task_id": "task-from-companion"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(handed_off["branch"]["lifecycle_status"], "exploring")
        self.assertEqual(handed_off["resume_session"]["task_id"], "task-from-companion")

        status, updated = self.request_json(
            "POST", f"/api/branches/{branch_id}/status", {"status": "exploring"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["branch"]["status"], "exploring")

    def test_board_page_is_served(self):
        self.connection.request("GET", "/")
        response = self.connection.getresponse()
        body = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Branch Keeper", body)
        self.assertIn("branch-keeper:resume", body)


if __name__ == "__main__":
    unittest.main()
