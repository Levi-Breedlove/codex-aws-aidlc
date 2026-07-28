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

from scripts import intake_response


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



def intake_foundation() -> dict[str, object]:
    digest = "sha256:" + "a" * 64
    token = presenter.intake_reply_token("INTAKE-CARD-0001", 1, digest)
    return {
        "schema_version": 1,
        "status": "FOUNDATION_REQUIRED",
        "repository_mode": "GREENFIELD",
        "owner_work_context": None,
        "basis_ids": [],
        "missing_fields": ["OWNER_WORK_CONTEXT", "PRIMARY_USERS"],
        "grandfathered_approved_gate_a": False,
        "pending_card": {
            "card_id": "INTAKE-CARD-0001",
            "revision": 1,
            "accept_all_allowed": False,
            "exact_reply": (
                f"{token}; 1: <choose A, B, or C>; 2: <your answer>; 3: <your answer>"
            ),
            "canonical_sha256": digest,
            "reply_token": token,
            "questions": [
                {
                    "reply_key": "1",
                    "question_id": "INTAKE-Q-0001",
                    "kind": "DECISION",
                    "basis_ids": ["INTAKE-0001"],
                    "prompt": "What are you starting with?",
                    "options": {
                        "A": "A new application.",
                        "B": "A change to an existing application.",
                        "C": "A repair or migration.",
                    },
                    "recommended": None,
                    "required_detail_for": ["B", "C"],
                    "detail_prompt": "Name the existing application.",
                    "selection": "PENDING",
                    "selection_detail": None,
                },
                {
                    "reply_key": "2",
                    "question_id": "INTAKE-Q-0002",
                    "kind": "FACT",
                    "basis_ids": ["INTAKE-0002", "INTAKE-0003"],
                    "prompt": "Who needs this, and what problem should it solve?",
                    "options": {},
                    "recommended": None,
                    "required_detail_for": ["RESPONSE"],
                    "detail_prompt": "Name the primary users and their problem.",
                    "selection": "PENDING",
                    "selection_detail": None,
                },
                {
                    "reply_key": "3",
                    "question_id": "INTAKE-Q-0003",
                    "kind": "FACT",
                    "basis_ids": ["INTAKE-0004", "INTAKE-0005"],
                    "prompt": "What is the first useful result?",
                    "options": {},
                    "recommended": None,
                    "required_detail_for": ["RESPONSE"],
                    "detail_prompt": "Describe the first-release outcome.",
                    "selection": "PENDING",
                    "selection_detail": None,
                },
            ],
        },
    }

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


    def test_aws_core_audit_requires_observed_doctor_projection(self) -> None:
        current = report(
            owner_stage="DESIGN",
            state="WORKING",
            route_reason_code="DESIGN_REQUIRED",
            owner_action_required=False,
            owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
            automatic_continuation_allowed=True,
            aws_core={"materiality": "MATERIAL", "evidence_status": "CURRENT"},
        )
        current["aws_core_evidence"] = {
            "observed_usage": {
                "DESIGN-10": {
                    "status": "OBSERVED",
                    "phase": "DESIGN-10",
                    "chains": [
                        {
                            "discovery_id": "AWS-DISC-0001",
                            "skill_identifier": "aws-architecture",
                            "official_references": [
                                "https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html"
                            ],
                            "credentials_inspected": False,
                            "aws_account_accessed": False,
                        }
                    ],
                }
            }
        }

        rendered = presenter.render_owner_update(current)
        self.assertIn(
            "Audit: AWS Core returned aws-architecture for this decision and supplied "
            "https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html. "
            "No AWS account was accessed.",
            rendered,
        )

        current["aws_core_evidence"]["observed_usage"]["DESIGN-10"] = {
            "status": "UNOBSERVED",
            "phase": "DESIGN-10",
            "chains": [],
        }
        self.assertNotIn("Audit:", presenter.render_owner_update(current))

    def test_malformed_aws_core_audit_projection_fails_closed(self) -> None:
        current = report(
            owner_stage="DESIGN",
            state="WORKING",
            route_reason_code="DESIGN_REQUIRED",
            owner_action_required=False,
            owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
            automatic_continuation_allowed=True,
            aws_core={"materiality": "MATERIAL", "evidence_status": "CURRENT"},
        )
        current["aws_core_evidence"] = {
            "observed_usage": {
                "DESIGN-10": {
                    "status": "OBSERVED",
                    "phase": "DESIGN-10",
                    "chains": [
                        {
                            "discovery_id": "AWS-DISC-0001",
                            "skill_identifier": "aws-architecture",
                            "official_references": ["https://docs.aws.amazon.com/"],
                            "credentials_inspected": True,
                            "aws_account_accessed": False,
                        }
                    ],
                }
            }
        }
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)


    def test_agent_correction_needs_nothing_and_continues(self) -> None:
        current = report(
            owner_stage="DELIVER",
            response_mode="OWNER_UPDATE",
            state="WORKING",
            route_reason_code="BLOCKED",
            owner_action_required=False,
            owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
            automatic_continuation_allowed=True,
        )
        current["remediation"] = {
            "items": [
                {
                    "diagnostic_id": "DGN-0001",
                    "diagnostic_code": "TASK_GRAPH_INVALID",
                    "path": "docs/project/TASKS.md",
                    "responsible_party": "CODEX",
                    "category": "AGENT_CORRECTION",
                    "automatic_correction_allowed": True,
                }
            ],
            "next_action": {
                "responsible_party": "CODEX",
                "action_kind": "CORRECT_AND_REVALIDATE",
                "automatic_continuation_allowed": True,
            },
        }

        rendered = presenter.render_owner_update(current)
        self.assertIn("Status: Fastlane found an in-scope validation defect.", rendered)
        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn(
            "Next: Codex will correct the reported in-scope failure and rerun validation.",
            rendered,
        )
        self.assertNotIn("Resolve the listed validation failure", rendered)

    def test_human_safety_review_is_one_genuine_action(self) -> None:
        current = report(
            response_mode="BLOCKER",
            state="BLOCKED",
            route_reason_code="BLOCKED",
            owner_action_kind="REVIEW_SAFETY_BLOCKER",
        )
        current["remediation"] = {
            "items": [],
            "next_action": {
                "responsible_party": "HUMAN_REVIEWER",
                "action_kind": "REVIEW_SAFETY_BLOCKER",
                "automatic_continuation_allowed": False,
            },
        }
        rendered = presenter.render_owner_update(current)
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn("Review the reported safety blocker", rendered)

    def test_coverage_plan_is_rendered_without_internal_method_terms(self) -> None:
        expected = {
            "SELECT": "compare complete architecture candidates",
            "AMEND": "reconsider only architecture decisions affected",
            "PRESERVE": "existing architecture remains valid",
        }
        for disposition, phrase in expected.items():
            with self.subTest(disposition=disposition):
                current = report(
                    owner_stage="DESIGN",
                    state="WORKING",
                    route_reason_code="DESIGN_REQUIRED",
                    owner_action_required=False,
                    owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
                    automatic_continuation_allowed=True,
                )
                current["coverage_plan"] = {
                    "status": "READY",
                    "architecture_disposition": disposition,
                }
                rendered = presenter.render_owner_update(current)
                self.assertIn(phrase, rendered)
                for internal_term in (
                    "Adaptive Coverage Plan",
                    "SELECT",
                    "AMEND",
                    "PRESERVE",
                    "EARS",
                    "Harness",
                    "context_plan",
                ):
                    self.assertNotIn(internal_term, rendered)

        invalid = report(owner_stage="DESIGN", route_reason_code="DESIGN_REQUIRED")
        invalid["coverage_plan"] = {
            "status": "READY",
            "architecture_disposition": "UNKNOWN",
        }
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(invalid)
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
            "Pending next action: Review and decide the Gate A requirements receipt.",
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
        self.assertIn("Pending next action: Nothing.", rendered)
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

    def test_public_cli_rejects_caller_supplied_audit_prose(self) -> None:
        payload = {
            "report": report(),
            "audit": "AWS Core was used because the caller says so.",
        }
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "owner", "--input-stdin"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "audit text is derived from the doctor report, not caller prose",
            result.stderr,
        )
        self.assertNotIn("Audit:", result.stdout)

    def test_grounded_intake_card_uses_uppercase_choices_and_exact_reply(self) -> None:
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = intake_foundation()

        rendered = presenter.render_owner_update(
            current, updated="I recorded the project brief you supplied."
        )

        self.assertTrue(rendered.startswith("FASTLANE \u00b7 DEFINE"))
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn("1. What are you starting with?", rendered)
        self.assertIn("A. A new application.", rendered)
        self.assertIn("B. A change to an existing application.", rendered)
        self.assertIn("C. A repair or migration.", rendered)
        self.assertIn("If you choose B: Name the existing application.", rendered)
        self.assertIn(
            "No recommendation—choose the option that matches your situation.",
            rendered,
        )
        self.assertIn("Reply: Name the primary users and their problem.", rendered)
        foundation = current["intake_foundation"]
        assert isinstance(foundation, dict)
        card = foundation["pending_card"]
        assert isinstance(card, dict)
        self.assertIn(
            f"Copyable reply:\n{card['reply_token']}; 1: <choose A, B, or C>; "
            "2: <your answer>; 3: <your answer>",
            rendered,
        )
        self.assertNotIn("Accept all recommendations.", rendered)
        self.assertNotIn("INTAKE-CARD", rendered)
        self.assertNotIn("sha256:", rendered)

    def test_accept_all_is_rendered_only_for_complete_recommendations(self) -> None:
        foundation = intake_foundation()
        card = foundation["pending_card"]
        assert isinstance(card, dict)
        question = card["questions"][0]
        question["recommended"] = "A"
        question["required_detail_for"] = []
        question["detail_prompt"] = None
        card["questions"] = [question]
        card["accept_all_allowed"] = True
        card["exact_reply"] = f"{card['reply_token']}; 1A"
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = foundation

        rendered = presenter.render_owner_update(current)

        self.assertEqual(rendered.count("Accept all recommendations."), 1)
        self.assertIn("A. Recommended \u2014 A new application.", rendered)
        self.assertIn(
            f"You may also reply `{card['reply_token']}; Accept all recommendations.`",
            rendered,
        )
        self.assertIn(f"Copyable reply:\n{card['reply_token']}; 1A", rendered)
        accepted = intake_response.parse_intake_owner_response(
            f"{card['reply_token']}; Accept all recommendations.",
            card,
            expected_card_id=str(card["card_id"]),
            expected_revision=int(card["revision"]),
            expected_sha256=str(card["canonical_sha256"]),
            owner_response_id="OWNER-MSG-0001",
        )
        self.assertEqual(accepted.status, "PASS", accepted.to_dict())
        self.assertEqual(accepted.answers[0].selection, "A")

    def test_presenter_rejects_tokenless_or_mismatched_copyable_reply(self) -> None:
        for field, value in (("reply_token", None), ("exact_reply", "1A")):
            foundation = intake_foundation()
            card = foundation["pending_card"]
            assert isinstance(card, dict)
            card[field] = value
            current = report(turn_boundary_required=True)
            current["intake_foundation"] = foundation
            with self.subTest(field=field), self.assertRaises(presenter.PresentationError):
                presenter.render_owner_update(current)

    def test_side_question_explains_without_resolving_or_replacing_card(self) -> None:
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = intake_foundation()

        rendered = presenter.render_side_question_response(
            current,
            answer=(
                "An existing-application change keeps the current product and alters "
                "only the outcome you describe."
            ),
        )

        self.assertIn("Project state changed: No.", rendered)
        self.assertIn("The pending questions are unchanged:", rendered)
        self.assertIn("1. What are you starting with?", rendered)
        self.assertIn("A. A new application.", rendered)
        self.assertIn(
            "No recommendation—choose the option that matches your situation.",
            rendered,
        )
        self.assertIn(
            "1: <choose A, B, or C>; 2: <your answer>; 3: <your answer>",
            rendered,
        )

    def test_intake_status_uses_exact_singular_and_plural_question_copy(self) -> None:
        foundation = intake_foundation()
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = foundation

        plural = presenter.render_owner_update(current)
        self.assertIn(
            "Status: 3 questions remain before requirements analysis.", plural
        )

        card = foundation["pending_card"]
        assert isinstance(card, dict)
        card["questions"] = [card["questions"][1]]
        card["exact_reply"] = f"{card['reply_token']}; 2: <your answer>"
        singular = presenter.render_owner_update(current)
        self.assertIn(
            "Status: 1 question remains before requirements analysis.", singular
        )
        self.assertNotIn("1 decision remain", singular)

    def test_fact_question_requires_response_marker_and_concrete_prompt(self) -> None:
        foundation = intake_foundation()
        card = foundation["pending_card"]
        assert isinstance(card, dict)
        fact = card["questions"][1]
        card["questions"] = [fact]
        card["exact_reply"] = f"{card['reply_token']}; 2: <your answer>"
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = foundation

        fact["required_detail_for"] = []
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)

        fact["required_detail_for"] = ["RESPONSE"]
        fact["detail_prompt"] = "   "
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)

    def test_decision_detail_contract_fails_closed_on_inconsistent_rules(self) -> None:
        foundation = intake_foundation()
        card = foundation["pending_card"]
        assert isinstance(card, dict)
        decision = card["questions"][0]
        card["questions"] = [decision]
        card["exact_reply"] = f"{card['reply_token']}; 1: <choose A, B, or C>"
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = foundation

        decision["required_detail_for"] = ["B", "B"]
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)

        decision["required_detail_for"] = ["B"]
        decision["detail_prompt"] = None
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)

        decision["required_detail_for"] = []
        decision["detail_prompt"] = "Unexpected detail request."
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)

    def test_owner_card_requires_a_final_turn_boundary(self) -> None:
        current = report(turn_boundary_required=False)
        current["intake_foundation"] = intake_foundation()

        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)


    def test_unknown_or_conflicting_state_fails_closed(self) -> None:
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(report(route_reason_code="UNKNOWN"))
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(
                report(owner_action_required=False, owner_action_kind="ANSWER_OPEN_DECISIONS")
            )


if __name__ == "__main__":
    unittest.main()
