from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "fastlane_presenter.py"
SPEC = importlib.util.spec_from_file_location("fastlane_presenter", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT}")
presenter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(presenter)


def report(**updates: object) -> dict[str, object]:
    interaction: dict[str, object] = {
        "owner_stage": "DEFINE",
        "response_mode": "OWNER_UPDATE",
        "state": "NEEDS_INPUT",
        "route_reason_code": "INTAKE_REQUIRED",
        "owner_action_required": True,
        "owner_action_kind": "ANSWER_OPEN_DECISIONS",
        "blocking_ids": [],
        "automatic_continuation_allowed": False,
        "formal_receipt_required": False,
        "aws_core": {"materiality": "NOT_MATERIAL", "evidence_status": "NOT_REQUIRED"},
    }
    interaction.update(updates)
    return {"interaction": interaction}


class FastlanePresenterTests(unittest.TestCase):
    def test_owner_update_has_one_action_and_no_internal_prompt_id(self) -> None:
        rendered = presenter.render_owner_update(report())
        self.assertTrue(rendered.startswith("FASTLANE \u00b7 DEFINE"))
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn("Copyable reply:", rendered)
        self.assertNotIn("INTAKE-10", rendered)
        self.assertNotIn("NONE", rendered)
        self.assertNotIn("Audit:", rendered)

    def test_automatic_update_says_nothing_and_continues(self) -> None:
        rendered = presenter.render_owner_update(
            report(
                owner_stage="DESIGN",
                state="WORKING",
                route_reason_code="DESIGN_REQUIRED",
                owner_action_required=False,
                owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
                automatic_continuation_allowed=True,
            ),
            updated="Gate A was approved.",
        )
        self.assertIn("FASTLANE \u00b7 DESIGN", rendered)
        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn("compare complete architecture candidates", rendered)

    def test_formal_receipt_cannot_use_routine_presenter(self) -> None:
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(
                report(
                    response_mode="GATE_A",
                    formal_receipt_required=True,
                    owner_action_kind="APPROVE_GATE_A",
                )
            )

    def test_prerequisite_renderer_has_one_action_and_all_steps(self) -> None:
        rendered = presenter.render_prerequisite_update(
            {
                "state": "PREREQUISITES_REQUIRED",
                "checklist": [
                    {"label": "Install Codex", "commands": ["codex --version"]},
                    {"label": "Install uv", "commands": ["uvx --version"]},
                ],
            }
        )
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn("Install Codex", rendered)
        self.assertIn("Install uv", rendered)

    def test_unconfigured_template_owner_update_routes_to_prerequisites(self) -> None:
        rendered = presenter.render_owner_update(
            report(
                owner_stage="DEFINE",
                response_mode="BLOCKER",
                state="BLOCKED",
                route_reason_code="UNCONFIGURED_TEMPLATE",
                owner_action_required=True,
                owner_action_kind="COMPLETE_PREREQUISITE_CHECKLIST",
                automatic_continuation_allowed=False,
            )
        )

        self.assertTrue(rendered.startswith("FASTLANE \u00b7 DEFINE"))
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn("This template has not been initialized.", rendered)
        self.assertIn("Complete the prerequisite checklist", rendered)
        self.assertIn("verify prerequisites before asking project questions", rendered)
        self.assertNotIn("Resolve the listed validation failure", rendered)

    def test_delivery_progress_uses_doctor_task_fields(self) -> None:
        current = report(
            owner_stage="DELIVER",
            state="WORKING",
            route_reason_code="CONSTRUCTION_AUTONOMOUS",
            owner_action_required=False,
            owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
            automatic_continuation_allowed=True,
        )
        current["tasks"] = {
            "total": 7,
            "completed": 3,
            "skipped": 0,
            "blocked": 0,
            "ready": 1,
            "in_progress": 1,
            "ready_ids": ["TASK-0005"],
            "active_ids": ["TASK-0004"],
            "blocked_ids": [],
        }
        rendered = presenter.render_owner_update(current)
        self.assertIn(
            "Status: 3 of 7 tasks complete; working on TASK-0004.", rendered
        )
        self.assertIn("Next: Codex will finish and validate TASK-0004.", rendered)

    def test_invalid_delivery_progress_fails_closed(self) -> None:
        current = report(
            owner_stage="DELIVER",
            state="WORKING",
            route_reason_code="CONSTRUCTION_SINGLE",
            owner_action_required=False,
            owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
            automatic_continuation_allowed=True,
        )
        current["tasks"] = {"total": 1, "completed": 2, "skipped": 0}
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)

        current["tasks"] = {
            "total": 1,
            "completed": 0,
            "skipped": 0,
            "blocked": 0,
            "ready": 0,
            "in_progress": 1,
            "ready_ids": [],
            "active_ids": ["not-a-task"],
        }
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)

    def test_side_question_restores_gate_action_without_receipt(self) -> None:
        pending = report(
            response_mode="GATE_A",
            state="AWAITING_APPROVAL",
            route_reason_code="WAITING_GATE_A",
            owner_action_kind="APPROVE_GATE_A",
            formal_receipt_required=True,
        )
        rendered = presenter.render_side_question_response(
            pending,
            answer="CloudFront is optional unless the approved requirements need edge delivery.",
        )
        self.assertTrue(rendered.startswith("CloudFront is optional"))
        self.assertIn("Project state changed: No.", rendered)
        self.assertIn(
            "Pending owner action: Review and decide the Gate A requirements receipt.",
            rendered,
        )
        self.assertNotIn("APPROVE REQUIREMENTS GATE A", rendered)

    def test_side_question_restores_automatic_continuation(self) -> None:
        working = report(
            owner_stage="DESIGN",
            state="WORKING",
            route_reason_code="DESIGN_REQUIRED",
            owner_action_required=False,
            owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
            automatic_continuation_allowed=True,
        )
        rendered = presenter.render_side_question_response(
            working,
            answer="No architecture decision changed.",
        )
        self.assertIn("Pending owner action: Nothing.", rendered)
        self.assertIn("Next: Codex will compare complete architecture candidates.", rendered)

    def test_public_cli_reads_one_json_object_from_stdin(self) -> None:
        payload = {
            "report": report(
                owner_stage="DESIGN",
                state="WORKING",
                route_reason_code="DESIGN_REQUIRED",
                owner_action_required=False,
                owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
                automatic_continuation_allowed=True,
            ),
            "updated": "Gate A was approved.",
        }
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "owner", "--input-stdin"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FASTLANE \u00b7 DESIGN", result.stdout)
        self.assertIn("Updated: Gate A was approved.", result.stdout)

    def test_unknown_or_conflicting_state_fails_closed(self) -> None:
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(report(route_reason_code="UNKNOWN"))
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(
                report(owner_action_required=False, owner_action_kind="ANSWER_OPEN_DECISIONS")
            )


if __name__ == "__main__":
    unittest.main()
