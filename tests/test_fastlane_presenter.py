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
        "schema_version": 2,
        "status": "FOUNDATION_REQUIRED",
        "repository_mode": "GREENFIELD",
        "owner_work_context": None,
        "current_understanding": [],
        "basis_ids": [],
        "missing_fields": ["OWNER_WORK_CONTEXT", "PRIMARY_USERS"],
        "grandfathered_approved_gate_a": False,
        "pending_card": {
            "card_id": "INTAKE-CARD-0001",
            "revision": 1,
            "accept_all_allowed": False,
            "owner_reply": "1: <choose A, B, or C>",
            "exact_reply": f"{token}; 1: <choose A, B, or C>",
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
                }
            ],
        },
    }


def factual_intake_foundation() -> dict[str, object]:
    foundation = intake_foundation()
    card = foundation["pending_card"]
    assert isinstance(card, dict)
    card["owner_reply"] = "1: <your answer>"
    card["exact_reply"] = f"{card['reply_token']}; 1: <your answer>"
    card["questions"] = [
        {
            "reply_key": "1",
            "question_id": "INTAKE-Q-0002",
            "kind": "FACT",
            "basis_ids": ["INTAKE-0002", "INTAKE-0003"],
            "prompt": (
                "Tell me about the app in your own words: who is it for, "
                "what is hard today, and what should become easier?"
            ),
            "options": {},
            "recommended": None,
            "required_detail_for": ["RESPONSE"],
            "detail_prompt": (
                "Describe the people, their current problem, and the useful result "
                "you want. More detail is welcome."
            ),
            "selection": "PENDING",
            "selection_detail": None,
        }
    ]
    return foundation

def aws_progress_report(
    progress_state: str,
    *,
    action_kind: str = "NONE_CONTINUE_AUTOMATICALLY",
    owner_action_required: bool = False,
    automatic_continuation_allowed: bool = True,
    formal_receipt_required: bool = False,
    preflight_status: str = "NOT_STARTED",
    account_access: str = "NOT_OBSERVED",
    lane: str = "read-only",
) -> dict[str, object]:
    current = report(
        owner_stage="DELIVER",
        response_mode="AWS_RECEIPT" if formal_receipt_required else "OWNER_UPDATE",
        state="AWAITING_APPROVAL" if formal_receipt_required else "WORKING",
        route_reason_code=progress_state,
        owner_action_required=owner_action_required,
        owner_action_kind=action_kind,
        automatic_continuation_allowed=automatic_continuation_allowed,
        formal_receipt_required=formal_receipt_required,
    )
    current["next_prompt"] = "AWS-10"
    current["aws_execution"] = {
        "schema_version": 1,
        "active": True,
        "lane": lane,
        "progress_state": progress_state,
        "preflight": {
            "status": preflight_status,
            "account_access": account_access,
            "account": "123456789012",
            "region": "us-west-2",
            "environment": "development",
        },
    }
    return current


def aws_teardown_report(
    reason: str,
    *,
    action_kind: str = "NONE_CONTINUE_AUTOMATICALLY",
    owner_action_required: bool = False,
    automatic_continuation_allowed: bool = True,
    formal_receipt_required: bool = False,
) -> dict[str, object]:
    current = report(
        owner_stage="DELIVER",
        response_mode="AWS_RECEIPT" if formal_receipt_required else "OWNER_UPDATE",
        state=(
            "AWAITING_APPROVAL"
            if formal_receipt_required
            else "NEEDS_INPUT"
            if owner_action_required
            else "WORKING"
        ),
        route_reason_code=reason,
        owner_action_required=owner_action_required,
        owner_action_kind=action_kind,
        automatic_continuation_allowed=automatic_continuation_allowed,
        formal_receipt_required=formal_receipt_required,
    )
    if reason in {"AWS_RESIDUALS_REMAIN", "AWS_RESIDUALS_RETAINED"}:
        current["next_prompt"] = "STOP"
    else:
        current["next_prompt"] = (
            "AWS-50"
            if reason in {"WAITING_AWS_TEARDOWN_AUTH", "AWS_TEARDOWN_ACTION_TERMINAL"}
            else "AWS-40"
        )
    current["aws_execution"] = {
        "schema_version": 1,
        "active": False,
        "lane": "explicit-gate",
        "progress_state": "NOT_ACTIVE",
    }
    if reason == "AWS_RESIDUAL_REVIEW_BLOCKED":
        current["aws_teardown"] = {
            "blocker_or_stale_reason": "caller identity could not be verified"
        }
    return current


def teardown_terminal_closure_report() -> dict[str, object]:
    current = aws_teardown_report("AWS_TEARDOWN_ACTION_TERMINAL")
    current["aws_teardown"] = {
        "status": "ACTION_TERMINAL_REQUIRED",
        "attempt_id": "AWS-TEARDOWN-0001",
        "evidence_id": "EV-7001",
        "action_status": "STARTED",
    }
    current["authorizations"] = {"construction": "NONE", "aws": "NONE"}
    current["write_authority"] = {"valid": False}
    current["external_authority"] = {"kind": "NONE", "validity": "NONE"}
    current["teardown_journal_closure_authority"] = {
        "valid": True,
        "kind": "AWS_TEARDOWN_JOURNAL_CLOSURE",
        "authorization_id": "AWS_TEARDOWN_JOURNAL_CLOSURE",
        "mode": "BOUNDED_EVIDENCE_CLOSURE",
        "allowed_write_paths": ["docs/project/VERIFY.md"],
        "allowed_sections": ["## AWS teardown action and residual evidence"],
        "allowed_operations": ["APPEND_TEARDOWN_TERMINAL_ROW"],
        "attempt_id": "AWS-TEARDOWN-0001",
        "evidence_id": "EV-7001",
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }
    return current


def lifecycle_intent(
    value: str,
    *,
    source: str = "owner-message MSG-AWS-LIFECYCLE-0001",
    recorded_at: str = "2026-07-29T12:00:00+00:00",
    provenance_status: str = "CURRENT",
) -> dict[str, object]:
    return {
        "value": value,
        "source": "NONE" if value == "NONE" else source,
        "recorded_at": "NONE" if value == "NONE" else recorded_at,
        "provenance_status": provenance_status,
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
    }


def residual_disposition(
    status: str,
    value: str,
    *,
    basis_status: str = "RESIDUALS_REMAIN",
    recorded_at: str | None = None,
) -> dict[str, object]:
    if recorded_at is None:
        recorded_at = "2026-07-29T12:00:00+00:00" if status == "CURRENT" else "NONE"
    return {
        "status": status,
        "value": value,
        "basis_evidence_id": "EV-7002",
        "basis_status": basis_status,
        "basis_observed_at": "2026-07-29T11:00:00+00:00",
        "recorded_at": recorded_at,
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
        "issues": [],
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

    def test_routine_owner_mode_ignores_additive_neutral_owner_projections(
        self,
    ) -> None:
        baseline = report()
        enriched = json.loads(json.dumps(baseline))
        enriched["schema_version"] = 2
        enriched["owner_decision_brief"] = {
            "schema_version": 1,
            "kind": "NONE",
            "status": "NONE",
        }
        enriched["owner_answer_confirmation"] = {
            "schema_version": 1,
            "status": "NONE",
        }

        self.assertEqual(
            presenter.render_owner_update(enriched),
            presenter.render_owner_update(baseline),
        )
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

    def test_aws_guidance_is_automatic_and_credential_free(self) -> None:
        rendered = presenter.render_owner_update(
            aws_progress_report("AWS_GUIDANCE_REQUIRED")
        )

        self.assertIn("Status: Current AWS guidance is needed", rendered)
        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn("without accessing an AWS account", rendered)
        self.assertNotIn("deployment receipt", rendered)

    def test_read_scope_restores_only_the_read_only_receipt_action(self) -> None:
        current = aws_progress_report(
            "AWS_READ_SCOPE_REQUIRED",
            action_kind="AUTHORIZE_AWS_READ_PREFLIGHT",
            owner_action_required=True,
            automatic_continuation_allowed=False,
            formal_receipt_required=True,
        )

        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)
        rendered = presenter.render_side_question_response(
            current,
            answer="The requested preflight can inspect only the named scope.",
        )
        self.assertIn(
            "Pending next action: Review the exact read-only AWS preflight receipt. "
            "It grants no mutation.",
            rendered,
        )
        self.assertNotIn("deployment receipt", rendered)

    def test_preflight_running_names_read_only_scope_without_owner_work(self) -> None:
        rendered = presenter.render_owner_update(
            aws_progress_report("AWS_PREFLIGHT_RUNNING")
        )

        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn("named-account read-only checks", rendered)
        self.assertIn("named AWS account scope read-only", rendered)
        self.assertIn("No mutation is authorized.", rendered)

    def test_preflight_ready_requires_observed_read_only_access(self) -> None:
        current = aws_progress_report(
            "AWS_PREFLIGHT_READY",
            automatic_continuation_allowed=False,
            preflight_status="READY",
            account_access="READ_ONLY_OBSERVED",
        )
        rendered = presenter.render_owner_update(current)

        self.assertIn("authorized read-only AWS inspection is complete", rendered)
        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn("No AWS resource mutation will occur.", rendered)
        self.assertIn("No mutation was performed.", rendered)

        current["aws_execution"]["preflight"]["account_access"] = "NOT_VERIFIED"
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)

    def test_documentation_only_ready_states_no_account_access(self) -> None:
        current = aws_progress_report(
            "AWS_PREFLIGHT_READY",
            automatic_continuation_allowed=False,
            preflight_status="NOT_APPLICABLE",
            account_access="NOT_USED",
            lane="documentation-only",
        )
        current["aws_execution"]["preflight"].update(
            {"account": "NONE", "region": "NONE", "environment": "NONE"}
        )
        rendered = presenter.render_owner_update(current)
        self.assertIn("Status: Documentation-only AWS guidance is complete.", rendered)
        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn("Next: No AWS account or resource action will occur.", rendered)
        self.assertIn("No AWS account was accessed.", rendered)
        self.assertNotIn("Authenticated preflight accessed", rendered)
        self.assertNotIn("Read-only AWS preflight", rendered)
        self.assertNotIn("observed preflight", rendered)

    def test_fast_dev_ready_uses_bounded_nonproduction_mutation_copy(self) -> None:
        current = aws_progress_report(
            "AWS_PREFLIGHT_READY",
            preflight_status="READY",
            account_access="READ_ONLY_OBSERVED",
            lane="fast-dev",
        )
        rendered = presenter.render_owner_update(current)
        side_question = presenter.render_side_question_response(
            current,
            answer="The preflight itself remained read-only.",
        )
        expected = "exact Gate-B-authorized non-production mutation"
        self.assertIn(expected, rendered)
        self.assertIn(expected, side_question)
        self.assertIn("No mutation was performed.", rendered)
        self.assertNotIn("without changing AWS resources", rendered)

    def test_preflight_ready_rejects_lane_continuation_mismatch(self) -> None:
        cases = (
            ("documentation-only", True, "NOT_APPLICABLE", "NOT_USED"),
            ("read-only", True, "READY", "READ_ONLY_OBSERVED"),
            ("fast-dev", False, "READY", "READ_ONLY_OBSERVED"),
        )
        for lane, automatic, preflight_status, account_access in cases:
            with self.subTest(lane=lane, automatic=automatic):
                current = aws_progress_report(
                    "AWS_PREFLIGHT_READY",
                    automatic_continuation_allowed=automatic,
                    preflight_status=preflight_status,
                    account_access=account_access,
                    lane=lane,
                )
                if lane == "documentation-only":
                    current["aws_execution"]["preflight"].update(
                        {
                            "account": "NONE",
                            "region": "NONE",
                            "environment": "NONE",
                        }
                    )

                with self.assertRaisesRegex(
                    presenter.PresentationError,
                    "terminal AWS preflight state is inconsistent",
                ):
                    presenter.render_owner_update(current)

    def test_blocked_or_stale_preflight_renders_the_safety_stop(self) -> None:
        for preflight_status in ("BLOCKED", "STALE"):
            with self.subTest(preflight_status=preflight_status):
                current = aws_progress_report(
                    "AWS_PREFLIGHT_RUNNING",
                    action_kind="REVIEW_SAFETY_BLOCKER",
                    owner_action_required=True,
                    automatic_continuation_allowed=False,
                    preflight_status=preflight_status,
                    account_access="NOT_VERIFIED",
                )
                current["interaction"].update(
                    {
                        "response_mode": "BLOCKER",
                        "state": "BLOCKED",
                        "route_reason_code": "BLOCKED",
                    }
                )
                rendered = presenter.render_owner_update(current)
                self.assertIn(
                    "Status: Fastlane stopped at a validation boundary.", rendered
                )
                self.assertIn(
                    "Need from you: Review the reported safety blocker", rendered
                )
                self.assertNotIn("Authenticated preflight accessed", rendered)
                self.assertNotIn("preflight is complete", rendered)
                self.assertNotIn("preflight is in progress", rendered)

    def test_current_mutation_authority_reports_automatic_bounded_execution(
        self,
    ) -> None:
        current = aws_progress_report(
            "WAITING_AWS_MUTATION_AUTH",
            preflight_status="READY",
            account_access="READ_ONLY_OBSERVED",
            lane="explicit-gate",
        )
        rendered = presenter.render_owner_update(current)
        side_question = presenter.render_side_question_response(
            current,
            answer="The accepted receipt remains limited to its exact resource boundary.",
        )
        self.assertIn("exact deployment authorization are current", rendered)
        self.assertIn(
            "Codex will perform only the exact authorized AWS mutation.", rendered
        )
        self.assertNotIn("needs separate authorization", rendered)
        self.assertNotIn("After authorization", rendered)
        self.assertIn(
            "Codex will perform only the exact authorized AWS mutation.", side_question
        )

    def test_mutation_receipt_action_is_limited_to_mutation_wait_state(self) -> None:
        current = aws_progress_report(
            "WAITING_AWS_MUTATION_AUTH",
            action_kind="AUTHORIZE_AWS_OPERATION",
            owner_action_required=True,
            automatic_continuation_allowed=False,
            formal_receipt_required=True,
            preflight_status="READY",
            account_access="READ_ONLY_OBSERVED",
        )
        rendered = presenter.render_side_question_response(
            current,
            answer="Preflight is complete; deployment remains separately gated.",
        )
        self.assertIn(
            "Pending next action: Review the exact AWS deployment receipt before any "
            "AWS mutation.",
            rendered,
        )

        current["interaction"]["route_reason_code"] = "AWS_PREFLIGHT_RUNNING"
        current["aws_execution"]["progress_state"] = "AWS_PREFLIGHT_RUNNING"
        with self.assertRaises(presenter.PresentationError):
            presenter.render_side_question_response(current, answer="Still running.")

    def test_residual_review_renders_before_deployment_progress(self) -> None:
        current = aws_teardown_report("AWS_RESIDUAL_REVIEW")
        current["aws_execution"] = {
            "schema_version": 1,
            "active": True,
            "lane": "explicit-gate",
            "progress_state": "WAITING_AWS_MUTATION_AUTH",
        }

        rendered = presenter.render_owner_update(current)
        side_question = presenter.render_side_question_response(
            current,
            answer="The residual check remains read-only.",
        )

        self.assertIn("Authorized read-only AWS residual review", rendered)
        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn("authorized read-only residual checks", rendered)
        self.assertNotIn("deployment authorization", rendered)
        self.assertIn("authorized read-only residual checks", side_question)

    def test_residual_review_restores_read_authorization_action(self) -> None:
        current = aws_teardown_report(
            "AWS_RESIDUAL_REVIEW",
            action_kind="AUTHORIZE_AWS_READ_PREFLIGHT",
            owner_action_required=True,
            automatic_continuation_allowed=False,
            formal_receipt_required=True,
        )

        rendered = presenter.render_side_question_response(
            current,
            answer="The review cannot remove resources.",
        )

        self.assertIn(
            "Pending next action: Review the exact read-only AWS preflight receipt. "
            "It grants no mutation.",
            rendered,
        )
        self.assertNotIn("deployment receipt", rendered)
        self.assertNotIn("teardown receipt", rendered)

    def test_teardown_receipt_action_is_distinct_from_deployment(self) -> None:
        current = aws_teardown_report(
            "WAITING_AWS_TEARDOWN_AUTH",
            action_kind="AUTHORIZE_AWS_TEARDOWN",
            owner_action_required=True,
            automatic_continuation_allowed=False,
            formal_receipt_required=True,
        )

        rendered = presenter.render_side_question_response(
            current,
            answer="Deployment approval cannot authorize cleanup.",
        )

        self.assertIn(
            "Pending next action: Review the exact AWS teardown receipt before any "
            "resource is removed.",
            rendered,
        )
        self.assertNotIn("deployment receipt", rendered)

    def test_current_teardown_authority_continues_exact_cleanup(self) -> None:
        current = aws_teardown_report("WAITING_AWS_TEARDOWN_AUTH")

        rendered = presenter.render_owner_update(current)
        side_question = presenter.render_side_question_response(
            current,
            answer="The teardown remains bounded by the accepted receipt.",
        )

        self.assertIn("exact teardown authorization are current", rendered)
        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn(
            "Codex will remove only the exact resources authorized for teardown.",
            rendered,
        )
        self.assertIn(
            "Codex will remove only the exact resources authorized for teardown.",
            side_question,
        )
        self.assertNotIn("deployment authorization", rendered)

    def test_teardown_terminal_closure_is_verify_only_and_automatic(self) -> None:
        current = teardown_terminal_closure_report()
        current["aws_lifecycle_intent"] = lifecycle_intent("TEARDOWN")

        rendered = presenter.render_owner_update(current)
        side_question = presenter.render_side_question_response(
            current,
            answer="The interrupted teardown remains journaled as STARTED.",
        )

        self.assertIn(
            "Status: An interrupted AWS teardown attempt needs a terminal journal result.",
            rendered,
        )
        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn(
            "Next: Codex will append UNKNOWN for the interrupted teardown attempt "
            "before read-only residual review.",
            rendered,
        )
        self.assertIn(
            "Audit: Teardown attempt AWS-TEARDOWN-0001 is append-only journaled "
            "with action status STARTED.",
            rendered,
        )
        self.assertIn(
            "append only terminal UNKNOWN to the teardown evidence in VERIFY.md",
            rendered,
        )
        self.assertIn("construction and AWS mutation remain unauthorized", rendered)
        self.assertIn("Owner chose REMOVE at 2026-07-29T12:00:00+00:00", rendered)
        self.assertIn("Pending next action: Nothing.", side_question)
        self.assertIn(
            "Next: Codex will append UNKNOWN for the interrupted teardown attempt "
            "before read-only residual review.",
            side_question,
        )

    def test_teardown_terminal_closure_fails_closed_on_broadened_authority(
        self,
    ) -> None:
        cases = [
            (
                "kind",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"kind": "AWS_DEPLOYMENT_JOURNAL_CLOSURE"}
                ),
            ),
            (
                "authorization",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"authorization_id": "AWS-TEARDOWN-0001"}
                ),
            ),
            (
                "mode",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"mode": "MUTATION"}
                ),
            ),
            (
                "closure-construction",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"construction_authorization": "AUTH-0001"}
                ),
            ),
            (
                "closure-mutation",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"aws_mutation_authority": "AWS-TEARDOWN-0001"}
                ),
            ),
            (
                "path",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"allowed_write_paths": ["docs/project/RUNBOOK.md"]}
                ),
            ),
            (
                "section",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"allowed_sections": ["## Current release decision"]}
                ),
            ),
            (
                "operation",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"allowed_operations": ["DELETE_RESOURCE"]}
                ),
            ),
            (
                "construction",
                lambda current: current["authorizations"].update(
                    {"construction": "AUTH-0001"}
                ),
            ),
            (
                "write",
                lambda current: current["write_authority"].update({"valid": True}),
            ),
            (
                "deployment",
                lambda current: current["external_authority"].update(
                    {"kind": "AWS_DEPLOYMENT", "validity": "CURRENT"}
                ),
            ),
            (
                "teardown",
                lambda current: current["external_authority"].update(
                    {"kind": "AWS_TEARDOWN", "validity": "CURRENT"}
                ),
            ),
            (
                "fast-dev",
                lambda current: current["external_authority"].update(
                    {"kind": "FAST_DEV_GATE_B", "validity": "CURRENT"}
                ),
            ),
            (
                "unknown-authority",
                lambda current: current["external_authority"].update(
                    {"kind": "UNKNOWN", "validity": "CURRENT"}
                ),
            ),
        ]
        for label, mutate in cases:
            current = teardown_terminal_closure_report()
            mutate(current)
            with (
                self.subTest(label=label),
                self.assertRaises(presenter.PresentationError),
            ):
                presenter.render_owner_update(current)

    def test_teardown_terminal_closure_fails_closed_on_mismatched_projection(
        self,
    ) -> None:
        cases = [
            (
                "invalid-type",
                lambda current: current.update(
                    {"teardown_journal_closure_authority": "INVALID"}
                ),
            ),
            (
                "not-current",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"valid": False}
                ),
            ),
            (
                "missing",
                lambda current: current.pop("teardown_journal_closure_authority"),
            ),
            (
                "attempt",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"attempt_id": "AWS-TEARDOWN-9999"}
                ),
            ),
            (
                "evidence",
                lambda current: current["teardown_journal_closure_authority"].update(
                    {"evidence_id": "EV-9999"}
                ),
            ),
            (
                "status",
                lambda current: current["aws_teardown"].update(
                    {"status": "POST_ACTION_REVIEW"}
                ),
            ),
            (
                "invalid-attempt-identifier",
                lambda current: (
                    current["teardown_journal_closure_authority"].update(
                        {"attempt_id": "AWS-TEARDOWN-X"}
                    ),
                    current["aws_teardown"].update({"attempt_id": "AWS-TEARDOWN-X"}),
                ),
            ),
            ("prompt", lambda current: current.update({"next_prompt": "AWS-40"})),
            (
                "route",
                lambda current: current["interaction"].update(
                    {"route_reason_code": "AWS_RESIDUAL_REVIEW"}
                ),
            ),
        ]
        for label, mutate in cases:
            current = teardown_terminal_closure_report()
            mutate(current)
            with (
                self.subTest(label=label),
                self.assertRaises(presenter.PresentationError),
            ):
                presenter.render_owner_update(current)

    def test_terminal_residual_and_teardown_states_are_explicit(self) -> None:
        cases = (
            (
                "AWS_RESIDUAL_REVIEW_COMPLETE",
                "no unexpected resources remain",
                "No teardown is required",
            ),
            (
                "AWS_TEARDOWN_COMPLETE",
                "teardown and read-only reconciliation are complete",
                "No further AWS action is required",
            ),
        )
        for reason, status, next_text in cases:
            with self.subTest(reason=reason):
                current = aws_teardown_report(
                    reason,
                    automatic_continuation_allowed=False,
                )
                current["interaction"]["state"] = "COMPLETE"

                rendered = presenter.render_owner_update(current)
                side_question = presenter.render_side_question_response(
                    current,
                    answer="The recorded terminal state is unchanged.",
                )

                self.assertIn(status, rendered)
                self.assertIn("Need from you: Nothing.", rendered)
                self.assertIn(next_text, rendered)
                self.assertIn(next_text, side_question)

    def test_residuals_remaining_require_one_owner_disposition(self) -> None:
        current = aws_teardown_report(
            "AWS_RESIDUALS_REMAIN",
            action_kind="CHOOSE_AWS_RESIDUAL_DISPOSITION",
            owner_action_required=True,
            automatic_continuation_allowed=False,
        )
        current["aws_residual_disposition"] = residual_disposition("PENDING", "NONE")

        rendered = presenter.render_owner_update(current)
        side_question = presenter.render_side_question_response(
            current,
            answer="Residual resources can continue generating cost.",
        )

        expected = (
            "Choose one outcome for the current residual set: RETAIN, INVESTIGATE, "
            "or REMOVE."
        )
        self.assertIn("residual-resource set that needs one decision", rendered)
        self.assertIn(f"Need from you: {expected}", rendered)
        self.assertIn("Copyable reply:", rendered)
        self.assertIn(
            "AWS residual decision: <RETAIN | INVESTIGATE | REMOVE>", rendered
        )
        self.assertIn("separate authorization for that path", rendered)
        self.assertIn(f"Pending next action: {expected}", side_question)
        self.assertIn(
            "AWS residual decision: <RETAIN | INVESTIGATE | REMOVE>", side_question
        )
        self.assertNotIn("For each listed residual", rendered)

    def test_retained_residuals_are_terminal_and_non_authorizing(self) -> None:
        current = aws_teardown_report(
            "AWS_RESIDUALS_RETAINED",
            automatic_continuation_allowed=False,
        )
        current["interaction"]["state"] = "COMPLETE"
        current["aws_lifecycle_intent"] = lifecycle_intent("RETAIN")
        current["aws_residual_disposition"] = residual_disposition("CURRENT", "RETAIN")

        rendered = presenter.render_owner_update(current)

        self.assertIn("retain the listed residual AWS resources", rendered)
        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn("may continue to incur cost", rendered)
        self.assertIn("no AWS access or mutation was authorized", rendered)
        self.assertIn("Owner chose RETAIN", rendered)
        self.assertNotIn("no unexpected resources remain", rendered)
        self.assertNotIn("resources were removed", rendered)

    def test_blocked_residual_review_requires_safety_review(self) -> None:
        current = aws_teardown_report(
            "AWS_RESIDUAL_REVIEW_BLOCKED",
            action_kind="REVIEW_SAFETY_BLOCKER",
            owner_action_required=True,
            automatic_continuation_allowed=False,
        )
        current["interaction"].update({"response_mode": "BLOCKER", "state": "BLOCKED"})

        rendered = presenter.render_owner_update(current)
        side_question = presenter.render_side_question_response(
            current,
            answer="No AWS resource will be changed while review is blocked.",
        )

        self.assertIn(
            "Read-only AWS residual review stopped: caller identity could not be verified",
            rendered,
        )
        self.assertIn("Need from you: Review the reported safety blocker", rendered)
        self.assertIn(
            "Pending next action: Review the reported safety blocker", side_question
        )
        self.assertIn(
            "Safety blocker: caller identity could not be verified", side_question
        )

    def test_blocked_residual_review_rejects_unsafe_reason(self) -> None:
        for reason in ("NONE", "line one\nline two"):
            with self.subTest(reason=reason):
                current = aws_teardown_report(
                    "AWS_RESIDUAL_REVIEW_BLOCKED",
                    action_kind="REVIEW_SAFETY_BLOCKER",
                    owner_action_required=True,
                    automatic_continuation_allowed=False,
                )
                current["interaction"].update(
                    {"response_mode": "BLOCKER", "state": "BLOCKED"}
                )
                current["aws_teardown"] = {"blocker_or_stale_reason": reason}
                with self.assertRaises(presenter.PresentationError):
                    presenter.render_owner_update(current)

    def test_teardown_actions_fail_closed_outside_exact_states(self) -> None:
        cases = (
            report(
                owner_stage="DELIVER",
                state="AWAITING_APPROVAL",
                route_reason_code="WAITING_AWS_MUTATION_AUTH",
                owner_action_required=True,
                owner_action_kind="AUTHORIZE_AWS_TEARDOWN",
                automatic_continuation_allowed=False,
                formal_receipt_required=True,
            ),
            aws_teardown_report(
                "WAITING_AWS_TEARDOWN_AUTH",
                action_kind="AUTHORIZE_AWS_OPERATION",
                owner_action_required=True,
                automatic_continuation_allowed=False,
                formal_receipt_required=True,
            ),
            aws_teardown_report(
                "AWS_RESIDUALS_REMAIN",
                automatic_continuation_allowed=False,
            ),
        )
        for current in cases:
            with self.subTest(reason=current["interaction"]["route_reason_code"]):
                with self.assertRaises(presenter.PresentationError):
                    presenter.render_side_question_response(current, answer="Explain.")

    def test_lifecycle_intent_audit_is_explicit_and_non_authorizing(self) -> None:
        cases = (
            (
                "RESIDUAL_REVIEW",
                "AWS_RESIDUAL_REVIEW",
                "Owner chose INVESTIGATE at 2026-07-29T12:00:00+00:00; "
                "this selects AWS-40 and grants no AWS access or mutation.",
            ),
            (
                "TEARDOWN",
                "WAITING_AWS_TEARDOWN_AUTH",
                "Owner chose REMOVE at 2026-07-29T12:00:00+00:00; this requests "
                "the teardown path but grants no AWS access or mutation; AWS-50 "
                "still requires the exact teardown authorization.",
            ),
        )
        for value, reason, expected in cases:
            with self.subTest(value=value, reason=reason):
                current = aws_teardown_report(reason)
                current["aws_lifecycle_intent"] = lifecycle_intent(value)
                rendered = presenter.render_owner_update(current)
                self.assertIn(f"Audit: {expected}", rendered)
                self.assertNotIn("authorized AWS access", rendered)

    def test_side_question_restores_lifecycle_intent_audit(self) -> None:
        current = aws_teardown_report("AWS_RESIDUAL_REVIEW")
        current["aws_lifecycle_intent"] = lifecycle_intent("TEARDOWN")

        rendered = presenter.render_side_question_response(
            current,
            answer="The review remains read-only.",
        )

        self.assertIn(
            "Audit: Owner chose REMOVE at 2026-07-29T12:00:00+00:00; this "
            "requests the teardown path but grants no AWS access or mutation; "
            "AWS-50 still requires the exact teardown authorization.",
            rendered,
        )

    def test_none_lifecycle_intent_adds_no_audit_copy(self) -> None:
        for provenance_status in ("CURRENT", "LEGACY_NONE"):
            with self.subTest(provenance_status=provenance_status):
                current = report()
                current["aws_lifecycle_intent"] = lifecycle_intent(
                    "NONE", provenance_status=provenance_status
                )

                rendered = presenter.render_owner_update(current)

                self.assertNotIn("AWS lifecycle intent", rendered)
                self.assertNotIn("selects AWS-40", rendered)

    def test_lifecycle_intent_projection_fails_closed(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = []
        bad_source = aws_teardown_report("AWS_RESIDUAL_REVIEW")
        bad_source["aws_lifecycle_intent"] = lifecycle_intent(
            "RESIDUAL_REVIEW", source="agent-generated"
        )
        cases.append(("source", bad_source))

        unzoned = aws_teardown_report("AWS_RESIDUAL_REVIEW")
        unzoned["aws_lifecycle_intent"] = lifecycle_intent(
            "RESIDUAL_REVIEW", recorded_at="2026-07-29T12:00:00"
        )
        cases.append(("timestamp", unzoned))

        access = aws_teardown_report("AWS_RESIDUAL_REVIEW")
        access_intent = lifecycle_intent("RESIDUAL_REVIEW")
        access_intent["authorizes_aws_access"] = True
        access["aws_lifecycle_intent"] = access_intent
        cases.append(("access", access))

        mutation = aws_teardown_report("AWS_RESIDUAL_REVIEW")
        mutation_intent = lifecycle_intent("RESIDUAL_REVIEW")
        mutation_intent["authorizes_mutation"] = True
        mutation["aws_lifecycle_intent"] = mutation_intent
        cases.append(("mutation", mutation))

        legacy_non_none = aws_teardown_report("AWS_RESIDUAL_REVIEW")
        legacy_non_none["aws_lifecycle_intent"] = lifecycle_intent(
            "RESIDUAL_REVIEW", provenance_status="LEGACY_NONE"
        )
        cases.append(("legacy", legacy_non_none))

        route_mismatch = aws_teardown_report("WAITING_AWS_TEARDOWN_AUTH")
        route_mismatch["aws_lifecycle_intent"] = lifecycle_intent("RESIDUAL_REVIEW")
        cases.append(("route", route_mismatch))

        malformed_none = report()
        none_intent = lifecycle_intent("NONE")
        none_intent["recorded_at"] = "2026-07-29T12:00:00+00:00"
        malformed_none["aws_lifecycle_intent"] = none_intent
        cases.append(("none", malformed_none))

        for label, current in cases:
            with (
                self.subTest(label=label),
                self.assertRaises(presenter.PresentationError),
            ):
                presenter.render_owner_update(current)

    def test_residual_disposition_projection_fails_closed(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = []
        missing = aws_teardown_report(
            "AWS_RESIDUALS_REMAIN",
            action_kind="CHOOSE_AWS_RESIDUAL_DISPOSITION",
            owner_action_required=True,
            automatic_continuation_allowed=False,
        )
        cases.append(("missing", missing))

        for label, field, bad_value in (
            ("access", "authorizes_aws_access", True),
            ("mutation", "authorizes_mutation", True),
            ("evidence", "basis_evidence_id", "EV-bad"),
            ("timestamp", "basis_observed_at", "2026-07-29T11:00:00"),
            ("basis", "basis_status", "VERIFIED_CLEAN"),
        ):
            current = aws_teardown_report(
                "AWS_RESIDUALS_REMAIN",
                action_kind="CHOOSE_AWS_RESIDUAL_DISPOSITION",
                owner_action_required=True,
                automatic_continuation_allowed=False,
            )
            projection = residual_disposition("PENDING", "NONE")
            projection[field] = bad_value
            current["aws_residual_disposition"] = projection
            cases.append((label, current))

        mismatch = aws_teardown_report(
            "AWS_RESIDUALS_RETAINED",
            automatic_continuation_allowed=False,
        )
        mismatch["interaction"]["state"] = "COMPLETE"
        mismatch["aws_residual_disposition"] = residual_disposition("CURRENT", "REMOVE")
        cases.append(("route", mismatch))

        for label, current in cases:
            with (
                self.subTest(label=label),
                self.assertRaises(presenter.PresentationError),
            ):
                presenter.render_owner_update(current)

    def test_legacy_aws_preflight_reason_remains_renderable(self) -> None:
        rendered = presenter.render_owner_update(
            report(
                owner_stage="DELIVER",
                state="WORKING",
                route_reason_code="AWS_PREFLIGHT_REQUIRED",
                owner_action_required=False,
                owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
                automatic_continuation_allowed=True,
            )
        )
        self.assertIn(
            "documentation evidence without accessing an AWS account", rendered
        )

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

        requirements = report(
            owner_stage="DEFINE",
            state="WORKING",
            route_reason_code="REQUIREMENTS_ANALYSIS",
            owner_action_required=False,
            owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
            automatic_continuation_allowed=True,
            aws_core={"materiality": "MATERIAL", "evidence_status": "CURRENT"},
        )
        requirements["next_prompt"] = "REQ-10"
        requirements["aws_core_evidence"] = {
            "observed_usage": {
                "REQ-10": {
                    **current["aws_core_evidence"]["observed_usage"]["DESIGN-10"],
                    "phase": "REQ-10",
                }
            }
        }
        requirements_rendered = presenter.render_owner_update(requirements)
        self.assertIn(
            "Audit: AWS Core returned aws-architecture", requirements_rendered
        )
        self.assertIn("No AWS account was accessed.", requirements_rendered)
        self.assertNotIn("DESIGN-10", requirements_rendered)

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

        current["interaction"]["aws_core"] = {
            "materiality": "NOT_MATERIAL",
            "evidence_status": "CURRENT",
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
        self.assertIn("Status: 3 of 7 tasks complete; working on TASK-0004.", rendered)
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
        self.assertIn(
            "Next: Codex will compare complete architecture candidates.", rendered
        )

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
            encoding="utf-8",
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
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "audit text is derived from the Fastlane Engine report, not caller prose",
            result.stderr,
        )
        self.assertNotIn("Audit:", result.stdout)

    def test_public_cli_emits_strict_utf8_bytes(self) -> None:
        payload = {
            "report": report(
                owner_stage="DESIGN",
                state="WORKING",
                route_reason_code="DESIGN_REQUIRED",
                owner_action_required=False,
                owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
                automatic_continuation_allowed=True,
            )
        }
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "owner", "--input-stdin"],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        output = result.stdout.decode("utf-8", errors="strict")
        self.assertIn("FASTLANE \u00b7 DESIGN", output)

    def test_grounded_intake_card_uses_uppercase_choices_and_plain_reply(self) -> None:
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = intake_foundation()

        rendered = presenter.render_owner_update(
            current, updated="I recorded the project brief you supplied."
        )

        self.assertTrue(rendered.startswith("FASTLANE · DEFINE"))
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn(
            "Status: 1 question remains before requirements analysis.", rendered
        )
        self.assertIn("1. What are you starting with?", rendered)
        self.assertIn("A. A new application.", rendered)
        self.assertIn("B. A change to an existing application.", rendered)
        self.assertIn("C. A repair or migration.", rendered)
        self.assertIn("If you choose B: Name the existing application.", rendered)
        self.assertIn(
            "No recommendation—choose the option that matches your situation.",
            rendered,
        )
        self.assertIn(
            "Copyable reply:\n1: <choose A, B, or C>",
            rendered,
        )
        self.assertNotIn("2.", rendered)
        foundation = current["intake_foundation"]
        assert isinstance(foundation, dict)
        card = foundation["pending_card"]
        assert isinstance(card, dict)
        self.assertNotIn(str(card["reply_token"]), rendered)
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
        card["owner_reply"] = "1A"
        card["exact_reply"] = f"{card['reply_token']}; 1A"
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = foundation

        rendered = presenter.render_owner_update(current)

        self.assertEqual(rendered.count("Accept all recommendations."), 1)
        self.assertIn("A. Recommended \u2014 A new application.", rendered)
        self.assertIn("You may also reply `Accept all recommendations.`", rendered)
        self.assertIn("Copyable reply:\n1A", rendered)
        self.assertNotIn(str(card["reply_token"]), rendered)
        accepted = intake_response.parse_intake_owner_response(
            "Accept all recommendations.",
            card,
            expected_card_id=str(card["card_id"]),
            expected_revision=int(card["revision"]),
            expected_sha256=str(card["canonical_sha256"]),
            owner_response_id="OWNER-MSG-0001",
        )
        self.assertEqual(accepted.status, "PASS", accepted.to_dict())
        self.assertEqual(accepted.answers[0].selection, "A")
        legacy = intake_response.parse_intake_owner_response(
            f"{card['reply_token']}; Accept all recommendations.",
            card,
            expected_card_id=str(card["card_id"]),
            expected_revision=int(card["revision"]),
            expected_sha256=str(card["canonical_sha256"]),
            owner_response_id="OWNER-MSG-0002",
        )
        self.assertEqual(legacy.status, "PASS", legacy.to_dict())
        self.assertEqual(legacy.answers[0].selection, "A")

    def test_presenter_rejects_mismatched_internal_reply_contract(self) -> None:
        for field, value in (
            ("reply_token", None),
            ("owner_reply", ""),
            ("exact_reply", "1A"),
        ):
            foundation = intake_foundation()
            card = foundation["pending_card"]
            assert isinstance(card, dict)
            card[field] = value
            current = report(turn_boundary_required=True)
            current["intake_foundation"] = foundation
            with (
                self.subTest(field=field),
                self.assertRaises(presenter.PresentationError),
            ):
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
        self.assertIn("1: <choose A, B, or C>", rendered)
        self.assertNotIn("2: <your answer>", rendered)

    def test_current_understanding_is_bounded_restored_and_backward_compatible(
        self,
    ) -> None:
        foundation = intake_foundation()
        foundation["current_understanding"] = [
            "Starting point: a new application.",
            "Users and problem: invited testers — scattered project decisions",
        ]
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = foundation

        rendered = presenter.render_owner_update(
            current, updated="I recorded two confirmed facts."
        )
        self.assertIn("Current understanding:", rendered)
        self.assertIn("- Starting point: a new application.", rendered)
        self.assertLess(
            rendered.index("Updated:"), rendered.index("Current understanding:")
        )
        self.assertLess(
            rendered.index("Current understanding:"), rendered.index("Need from you:")
        )

        side = presenter.render_side_question_response(
            current,
            answer="That choice changes which existing behavior must be preserved.",
        )
        self.assertIn("Current understanding:", side)
        self.assertLess(
            side.index("Current understanding:"), side.index("Pending next action:")
        )

        for invalid in (
            "not-a-list",
            [""],
            ["one", "two", "three", "four", "five", "six"],
        ):
            malformed = intake_foundation()
            malformed["current_understanding"] = invalid
            malformed_report = report(turn_boundary_required=True)
            malformed_report["intake_foundation"] = malformed
            with (
                self.subTest(invalid=invalid),
                self.assertRaises(presenter.PresentationError),
            ):
                presenter.render_owner_update(malformed_report)

        legacy = intake_foundation()
        legacy["schema_version"] = 1
        legacy.pop("current_understanding")
        legacy_report = report(turn_boundary_required=True)
        legacy_report["intake_foundation"] = legacy
        self.assertNotIn(
            "Current understanding:", presenter.render_owner_update(legacy_report)
        )

    def test_intake_status_is_singular_and_multi_question_cards_fail_closed(
        self,
    ) -> None:
        foundation = intake_foundation()
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = foundation

        rendered = presenter.render_owner_update(current)
        self.assertIn(
            "Status: 1 question remains before requirements analysis.", rendered
        )
        self.assertNotIn("questions remain", rendered)

        malformed = intake_foundation()
        card = malformed["pending_card"]
        assert isinstance(card, dict)
        other = factual_intake_foundation()["pending_card"]
        assert isinstance(other, dict)
        card["questions"].append(other["questions"][0])
        malformed_report = report(turn_boundary_required=True)
        malformed_report["intake_foundation"] = malformed
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(malformed_report)

    def test_fact_question_requires_response_marker_and_concrete_prompt(self) -> None:
        foundation = factual_intake_foundation()
        card = foundation["pending_card"]
        assert isinstance(card, dict)
        fact = card["questions"][0]
        current = report(turn_boundary_required=True)
        current["intake_foundation"] = foundation

        rendered = presenter.render_owner_update(current)
        self.assertIn("Tell me about the app in your own words", rendered)
        self.assertIn("More detail is welcome.", rendered)
        self.assertIn("Copyable reply:\n1: <your answer>", rendered)

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
        card["owner_reply"] = "1: <choose A, B, or C>"
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
                report(
                    owner_action_required=False,
                    owner_action_kind="ANSWER_OPEN_DECISIONS",
                )
            )

    def test_deployment_reconciliation_is_read_only_and_restores_one_action(
        self,
    ) -> None:
        current = aws_progress_report(
            "AWS_DEPLOYMENT_RECONCILIATION",
            lane="explicit-gate",
        )
        current["next_prompt"] = "AWS-30"
        current["aws_deployment"] = {
            "status": "RECONCILIATION_REQUIRED",
            "attempt_id": "AWS-DEPLOY-0001",
            "action_status": "SUCCEEDED",
            "reconciliation_status": "NONE",
        }
        current["external_authority"] = {
            "kind": "AWS_READ_ONLY",
            "validity": "CURRENT",
        }
        rendered = presenter.render_owner_update(current)
        normalized = rendered.casefold()
        self.assertIn("deployment", normalized)
        self.assertIn("reconciliation", normalized)
        self.assertIn("read-only", normalized)
        self.assertIn("Need from you: Nothing.", rendered)
        self.assertIn("no further mutation", normalized)
        self.assertNotIn("Review the exact AWS deployment receipt", rendered)

        missing_read = aws_progress_report(
            "AWS_DEPLOYMENT_RECONCILIATION",
            action_kind="AUTHORIZE_AWS_READ_PREFLIGHT",
            owner_action_required=True,
            automatic_continuation_allowed=False,
            formal_receipt_required=True,
            lane="explicit-gate",
        )
        missing_read["next_prompt"] = "AWS-30"
        missing_read["aws_deployment"] = current["aws_deployment"]
        missing_read["external_authority"] = {
            "kind": "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED",
            "validity": "REQUIRED",
        }
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(missing_read)
        side = presenter.render_side_question_response(
            missing_read,
            answer="Reconciliation verifies the observed deployment result.",
        )
        self.assertIn(
            "Pending next action: Review the exact read-only AWS preflight receipt. "
            "It grants no mutation.",
            side,
        )
        self.assertNotIn("Review the exact AWS deployment receipt", side)

    def test_release_closure_projects_only_allowed_release_states(self) -> None:
        current = aws_progress_report("RELEASE_REVIEW", lane="explicit-gate")
        current["next_prompt"] = "RELEASE-10"
        current["aws_deployment"] = {
            "status": "BLOCKED",
            "attempt_id": "AWS-DEPLOY-0001",
            "basis_stale": False,
        }
        current["authorizations"] = {"construction": "NONE", "aws": "NONE"}
        current["write_authority"] = {"valid": False}
        current["external_authority"] = {"kind": "NONE", "validity": "NONE"}
        current["deployment_journal_closure_authority"] = {
            "valid": True,
            "kind": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
            "authorization_id": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
            "mode": "BOUNDED_EVIDENCE_CLOSURE",
            "allowed_write_paths": ["docs/project/VERIFY.md"],
            "allowed_sections": ["## Current release decision"],
            "allowed_operations": ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
            "allowed_release_states": ["NOT_READY"],
            "attempt_id": "AWS-DEPLOY-0001",
            "evidence_id": "EV-9733",
            "construction_authorization": "NONE",
            "aws_mutation_authority": "NONE",
        }
        rendered = presenter.render_owner_update(current)
        self.assertIn("allowed release states NOT_READY", rendered)

        current["deployment_journal_closure_authority"]["allowed_release_states"] = [
            "RELEASE_VERIFIED"
        ]
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update(current)


if __name__ == "__main__":
    unittest.main()
