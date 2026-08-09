import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import branch_keeper_mcp as branch_keeper  # noqa: E402


class BranchKeeperTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["BRANCH_KEEPER_HOME"] = self.temp_dir.name

    def tearDown(self):
        os.environ.pop("BRANCH_KEEPER_HOME", None)
        self.temp_dir.cleanup()

    def test_batch_parking_creates_context_and_children(self):
        result = branch_keeper.park_branches(
            {
                "context": {
                    "title": "Pricing discussion",
                    "source_host": "codex",
                    "project_name": "Example App",
                },
                "branches": [
                    {
                        "title": "Usage-based pricing",
                        "why_saved": "Could fit high-frequency users.",
                        "why_not_now": "Need usage data first.",
                        "next_question": "What usage event should be billable?",
                    },
                    {
                        "title": "One-time purchase",
                        "why_saved": "Lower adoption friction.",
                        "next_question": "Would support costs remain sustainable?",
                    },
                ],
            }
        )
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["root"]["kind"], "context")
        self.assertTrue(all(item["parent_id"] == result["root"]["id"] for item in result["branches"]))

        listed = branch_keeper.select_branches({})
        self.assertEqual(len(listed), 2)
        self.assertEqual({item["status"] for item in listed}, {"parked"})
        self.assertEqual({item["lifecycle_status"] for item in listed}, {"parked"})
        self.assertEqual({item["review_state"] for item in listed}, {"confirmed"})
        self.assertEqual({item["attention_state"] for item in listed}, {"normal"})

    def test_resume_records_event_without_status_change(self):
        result = branch_keeper.park_branches(
            {
                "branches": [
                    {
                        "title": "Partner-led distribution",
                        "why_saved": "Could reduce acquisition cost.",
                        "next_question": "Which partner reaches the first segment?",
                    }
                ]
            }
        )
        branch_id = result["branches"][0]["id"]
        resumed = branch_keeper.resume_branch({"branch_id": branch_id})
        self.assertEqual(resumed["branch"]["status"], "parked")
        self.assertIn("Which partner reaches", resumed["continuation_prompt"])
        self.assertEqual(resumed["operation_status"], "prompt_ready")
        self.assertTrue(resumed["resume_id"])
        self.assertTrue(resumed["resumed_event_id"])

    def test_successful_resume_handoff_moves_parked_to_exploring(self):
        result = branch_keeper.park_branches(
            {
                "branches": [
                    {
                        "title": "Research-led onboarding",
                        "why_saved": "Could reduce early churn.",
                        "next_question": "Which activation moment should we validate first?",
                    }
                ]
            }
        )
        branch_id = result["branches"][0]["id"]
        resumed = branch_keeper.resume_branch({"branch_id": branch_id, "task_id": "task-1"})
        completed = branch_keeper.record_resume_result(
            {
                "resume_id": resumed["resume_id"],
                "result_status": "succeeded",
                "task_id": "task-1",
                "result_summary": "New Codex task prepared.",
            }
        )
        self.assertEqual(completed["branch"]["lifecycle_status"], "exploring")
        self.assertEqual(completed["branch"]["operation_status"], "succeeded")
        self.assertEqual(completed["resume_session"]["operation_status"], "succeeded")
        self.assertIn(
            "lifecycle_transitioned",
            {event["event_type"] for event in completed["branch"]["events"]},
        )
        repeated = branch_keeper.record_resume_result(
            {"resume_id": resumed["resume_id"], "result_status": "succeeded"}
        )
        self.assertEqual(repeated["message"], "Resume result was already recorded.")
        self.assertEqual(
            len(
                [
                    event
                    for event in repeated["branch"]["events"]
                    if event["event_type"] == "lifecycle_transitioned"
                ]
            ),
            1,
        )
        with self.assertRaises(ValueError):
            branch_keeper.record_resume_result(
                {"resume_id": resumed["resume_id"], "result_status": "failed"}
            )

    def test_failed_resume_handoff_keeps_branch_parked(self):
        result = branch_keeper.park_branches(
            {
                "branches": [
                    {
                        "title": "Usage-based pricing",
                        "why_saved": "May align revenue with value.",
                        "next_question": "What usage event should be billable?",
                    }
                ]
            }
        )
        branch_id = result["branches"][0]["id"]
        resumed = branch_keeper.resume_branch({"branch_id": branch_id})
        failed = branch_keeper.record_resume_result(
            {
                "resume_id": resumed["resume_id"],
                "result_status": "failed",
                "result_summary": "Composer was not available.",
            }
        )
        self.assertEqual(failed["branch"]["lifecycle_status"], "parked")
        self.assertEqual(failed["branch"]["operation_status"], "failed")
        self.assertIn(
            "resume_handoff_failed",
            {event["event_type"] for event in failed["branch"]["events"]},
        )

    def test_search_and_update(self):
        result = branch_keeper.park_branches(
            {
                "branches": [
                    {
                        "title": "Community launch",
                        "why_saved": "The first users may recruit each other.",
                        "next_question": "Which community should we test?",
                    }
                ]
            }
        )
        branch_id = result["branches"][0]["id"]
        found = branch_keeper.select_branches({"query": "community"}, search=True)
        self.assertEqual(len(found), 1)
        updated = branch_keeper.update_branch(
            {"branch_id": branch_id, "status": "exploring", "next_action": "Interview three users."}
        )
        self.assertEqual(updated["branch"]["status"], "exploring")
        self.assertEqual(updated["branch"]["next_action"], "Interview three users.")

    def test_blocker_is_orthogonal_and_recorded(self):
        result = branch_keeper.park_branches(
            {
                "branches": [
                    {
                        "title": "Enterprise plan",
                        "why_saved": "Could unlock larger contracts.",
                        "next_question": "Which procurement constraint matters first?",
                    }
                ]
            }
        )
        branch_id = result["branches"][0]["id"]
        blocked = branch_keeper.update_branch(
            {
                "branch_id": branch_id,
                "blocked_reason": "Waiting for customer interviews.",
                "blocked_by": "user-research",
            }
        )
        self.assertEqual(blocked["branch"]["status"], "parked")
        self.assertEqual(blocked["branch"]["attention_state"], "blocked")
        self.assertIn("blocked", {event["event_type"] for event in blocked["branch"]["events"]})

        unblocked = branch_keeper.update_branch(
            {"branch_id": branch_id, "blocked_reason": None, "blocked_by": None}
        )
        self.assertEqual(unblocked["branch"]["attention_state"], "normal")
        self.assertIn("unblocked", {event["event_type"] for event in unblocked["branch"]["events"]})

    def test_resolved_transition_requires_reason_and_reopen_preserves_history(self):
        result = branch_keeper.park_branches(
            {
                "branches": [
                    {
                        "title": "Self-serve expansion",
                        "why_saved": "Could widen the market.",
                        "next_question": "What segment should we test?",
                    }
                ]
            }
        )
        branch_id = result["branches"][0]["id"]
        with self.assertRaises(ValueError):
            branch_keeper.update_branch({"branch_id": branch_id, "status": "adopted"})

        adopted = branch_keeper.update_branch(
            {
                "branch_id": branch_id,
                "status": "adopted",
                "reason": "The interviews confirmed this is the strongest path.",
                "outcome": "Proceed with a validation experiment.",
                "outcome_rationale": "The interviews confirmed this is the strongest path.",
            }
        )
        self.assertEqual(adopted["branch"]["lifecycle_status"], "adopted")
        self.assertEqual(adopted["branch"]["attention_state"], "normal")

        reopened = branch_keeper.update_branch({"branch_id": branch_id, "status": "parked"})
        self.assertEqual(reopened["branch"]["lifecycle_status"], "parked")
        self.assertEqual(reopened["branch"]["outcome"], "Proceed with a validation experiment.")
        self.assertIn("reopened", {event["event_type"] for event in reopened["branch"]["events"]})

    def test_soft_limit_warns_without_blocking_and_suggests_duplicates(self):
        branches = [
            {
                "title": f"Direction {index}",
                "why_saved": "A distinct product opportunity.",
                "next_question": f"What should we validate for direction {index}?",
            }
            for index in range(6)
        ]
        result = branch_keeper.park_branches({"branches": branches})
        self.assertEqual(result["count"], 6)
        self.assertTrue(result["warnings"])
        self.assertEqual(result["soft_limits"]["batch"], 5)

        duplicate = branch_keeper.park_branches(
            {
                "branches": [
                    {
                        "title": "Direction 0",
                        "why_saved": "A distinct product opportunity.",
                        "next_question": "What should we validate for direction 0?",
                    }
                ]
            }
        )
        self.assertTrue(duplicate["duplicate_suggestions"])

    def test_json_rpc_tools_list(self):
        response = branch_keeper.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {item["name"] for item in response["result"]["tools"]}
        self.assertIn("park_branches", names)
        self.assertIn("resume_branch", names)


if __name__ == "__main__":
    unittest.main()
