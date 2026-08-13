#!/usr/bin/env python3
"""Render deterministic Fastlane owner updates from machine-derived state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from typing import Any, Mapping, Sequence

try:
    from fastlane_engine.api import ARCHITECTURE_DIAGRAM_SKILL_IDENTITY
    from fastlane_engine.core.ids import TASK_ID
    from fastlane_owner_briefs import (
        GATE_B_NAVIGATION_LOCATOR_KEYS,
        finalize_owner_decision_brief,
        finalize_owner_decision_inventory,
    )
    from intake_response import intake_reply_token
    from fastlane_stdio import configure_utf8_standard_streams
except ModuleNotFoundError:  # Loaded as scripts.fastlane_presenter in unit tests.
    from scripts.fastlane_engine.api import ARCHITECTURE_DIAGRAM_SKILL_IDENTITY
    from scripts.fastlane_engine.core.ids import TASK_ID
    from scripts.fastlane_owner_briefs import (
        GATE_B_NAVIGATION_LOCATOR_KEYS,
        finalize_owner_decision_brief,
        finalize_owner_decision_inventory,
    )
    from scripts.intake_response import intake_reply_token
    from scripts.fastlane_stdio import configure_utf8_standard_streams


class PresentationError(RuntimeError):
    """Raised when state cannot be rendered as a routine owner update."""


STATUS_TEXT = {
    "UNCONFIGURED_TEMPLATE": "This template has not been initialized.",
    "INTAKE_REQUIRED": "Ready to define the project.",
    "REQUIREMENTS_ANALYSIS": "Requirements are ready for analysis.",
    "REQUIREMENTS_STALE": "Approved requirements need review after a change.",
    "WAITING_GATE_A": "Requirements are ready for your Gate A decision.",
    "DESIGN_REQUIRED": "The technical design is ready to be developed.",
    "DESIGN_STALE": "The technical design must be refreshed.",
    "WAITING_GATE_B": "The design is ready for your Gate B decision.",
    "TASK_PLAN_REQUIRED": "The approved design is ready for task planning.",
    "TASK_REPLAN_REQUIRED": "The current task plan needs a bounded correction.",
    "CONSTRUCTION_SINGLE": "Approved local construction can continue.",
    "CONSTRUCTION_AUTONOMOUS": "Approved local construction is in progress.",
    "RELEASE_REVIEW": "Local construction is ready for release review.",
    "RELEASE_REVIEW_BLOCKED": (
        "Deployment reconciliation is acknowledged, but the release remains not ready."
    ),
    "AWS_GUIDANCE_REQUIRED": "Current AWS guidance is needed before deployment planning.",
    "AWS_READ_SCOPE_REQUIRED": "Read-only AWS preflight needs your authorization.",
    "AWS_PREFLIGHT_RUNNING": "Authorized read-only AWS preflight is in progress.",
    "AWS_PREFLIGHT_READY": "Read-only AWS preflight is complete.",
    "WAITING_AWS_MUTATION_AUTH": (
        "Read-only AWS preflight is complete; deployment needs separate authorization."
    ),
    "AWS_DEPLOYMENT_ACTION_TERMINAL": (
        "An interrupted AWS deployment attempt needs a terminal journal result."
    ),
    "AWS_TEARDOWN_ACTION_TERMINAL": (
        "An interrupted AWS teardown attempt needs a terminal journal result."
    ),
    "AWS_DEPLOYMENT_RECONCILIATION": (
        "An AWS deployment attempt needs read-only reconciliation."
    ),
    "AWS_RESIDUAL_REVIEW": "Authorized read-only AWS residual review is in progress.",
    "WAITING_AWS_TEARDOWN_AUTH": (
        "Read-only residual review is complete; teardown needs separate authorization."
    ),
    "AWS_RESIDUAL_REVIEW_COMPLETE": (
        "Read-only AWS residual review is complete; no unexpected resources remain."
    ),
    "AWS_RESIDUALS_RETAINED": (
        "You chose to retain the listed residual AWS resources."
    ),
    "AWS_RESIDUALS_REMAIN": (
        "Read-only AWS review found a residual-resource set that needs one decision."
    ),
    "AWS_RESIDUAL_REVIEW_BLOCKED": (
        "Read-only AWS residual review stopped at a safety boundary."
    ),
    "AWS_TEARDOWN_COMPLETE": (
        "Authorized AWS teardown and read-only reconciliation are complete."
    ),
    "AWS_PREFLIGHT_REQUIRED": "Deployment planning needs current AWS evidence.",
    "RELEASE_VERIFIED": "The approved local workflow is complete.",
    "BLOCKED": "Fastlane stopped at a validation boundary.",
}

ACTION_TEXT = {
    "COMPLETE_PREREQUISITE_CHECKLIST": (
        "Complete the prerequisite checklist, then send `init template` again."
    ),
    "ANSWER_OPEN_DECISIONS": "Answer the pending project questions.",
    "APPROVE_GATE_A": "Review and decide the Gate A requirements receipt.",
    "ENABLE_AWS_CORE": "Enable official AWS Core, then continue the affected AWS step.",
    "APPROVE_GATE_B": "Review and decide the Gate B design and construction receipt.",
    "AUTHORIZE_AWS_READ_PREFLIGHT": (
        "Review the exact read-only AWS preflight receipt. It grants no mutation."
    ),
    "AUTHORIZE_AWS_OPERATION": (
        "Review the exact AWS deployment receipt before any AWS mutation."
    ),
    "AUTHORIZE_AWS_TEARDOWN": (
        "Review the exact AWS teardown receipt before any resource is removed."
    ),
    "CHOOSE_AWS_RESIDUAL_DISPOSITION": (
        "Choose one outcome for the current residual set: RETAIN, INVESTIGATE, "
        "or REMOVE."
    ),
    "FIX_VALIDATION_FAILURE": "Resolve the listed validation failure, then continue Fastlane.",
    "REVIEW_SAFETY_BLOCKER": "Review the reported safety blocker before Fastlane changes anything.",
    "NONE_CONTINUE_AUTOMATICALLY": "Nothing.",
}

NEXT_TEXT = {
    "UNCONFIGURED_TEMPLATE": (
        "Codex will verify prerequisites before asking project questions."
    ),
    "INTAKE_REQUIRED": "Codex will record your answers and continue guided definition.",
    "REQUIREMENTS_ANALYSIS": "Codex will analyze the complete requirement set.",
    "REQUIREMENTS_STALE": "Codex will reconcile the changed requirement basis.",
    "WAITING_GATE_A": "After approval, Codex will begin technical design.",
    "DESIGN_REQUIRED": "Codex will compare complete architecture candidates.",
    "DESIGN_STALE": "Codex will refresh design evidence and the proposal.",
    "WAITING_GATE_B": "After approval, Codex will generate tasks and build locally.",
    "TASK_PLAN_REQUIRED": "Codex will generate the dependency-aware task plan.",
    "TASK_REPLAN_REQUIRED": (
        "Codex will replan the affected tasks while preserving completed evidence."
    ),
    "CONSTRUCTION_SINGLE": "Codex will execute the next ready local task.",
    "CONSTRUCTION_AUTONOMOUS": "Codex will continue approved local tasks.",
    "RELEASE_REVIEW": "Codex will validate evidence and release readiness.",
    "RELEASE_REVIEW_BLOCKED": (
        "Review the release blockers before approving a correction or new deployment path."
    ),
    "AWS_PREFLIGHT_REQUIRED": "Codex will collect documentation evidence without accessing an AWS account.",
    "AWS_GUIDANCE_REQUIRED": (
        "Codex will collect current AWS guidance without accessing an AWS account."
    ),
    "AWS_READ_SCOPE_REQUIRED": (
        "After authorization, Codex will inspect only the named AWS account scope "
        "read-only."
    ),
    "AWS_PREFLIGHT_RUNNING": (
        "Codex will complete the authorized named-account read-only checks and "
        "record what it observes."
    ),
    "AWS_PREFLIGHT_READY": (
        "Codex will route the observed preflight result without changing AWS resources."
    ),
    "WAITING_AWS_MUTATION_AUTH": (
        "After authorization, Codex may perform only the exact approved AWS mutation."
    ),
    "AWS_DEPLOYMENT_ACTION_TERMINAL": (
        "Codex will append UNKNOWN for the interrupted attempt before any "
        "read-only reconciliation."
    ),
    "AWS_TEARDOWN_ACTION_TERMINAL": (
        "Codex will append UNKNOWN for the interrupted teardown attempt before "
        "read-only residual review."
    ),
    "AWS_DEPLOYMENT_RECONCILIATION": (
        "Codex will inspect only the authorized deployment target read-only, record "
        "what it observes, then return to release review."
    ),
    "AWS_RESIDUAL_REVIEW": (
        "Codex will complete only the authorized read-only residual checks and record "
        "what it observes."
    ),
    "WAITING_AWS_TEARDOWN_AUTH": (
        "After authorization, Codex may remove only the exact approved resources."
    ),
    "AWS_RESIDUAL_REVIEW_COMPLETE": (
        "No teardown is required; the verified release remains unchanged."
    ),
    "AWS_RESIDUALS_RETAINED": (
        "Fastlane stops here; retained resources may continue to incur cost, and "
        "no AWS access or mutation was authorized."
    ),
    "AWS_RESIDUALS_REMAIN": (
        "Fastlane will record the choice locally. AWS access or resource removal "
        "still requires the separate authorization for that path."
    ),
    "AWS_RESIDUAL_REVIEW_BLOCKED": (
        "Codex will not inspect further or mutate resources until the safety blocker "
        "is resolved."
    ),
    "AWS_TEARDOWN_COMPLETE": "No further AWS action is required.",
    "RELEASE_VERIFIED": "No further action is required.",
    "BLOCKED": "Codex will resume only after the named blocker is resolved.",
}

COPYABLE_REPLIES = {
    "ANSWER_OPEN_DECISIONS": "Reply with your answers to the questions below.",
    "ENABLE_AWS_CORE": "CONTINUE FASTLANE",
    "FIX_VALIDATION_FAILURE": "CONTINUE FASTLANE",
    "CHOOSE_AWS_RESIDUAL_DISPOSITION": (
        "AWS residual decision: <RETAIN | INVESTIGATE | REMOVE>"
    ),
}


def _interaction(report: Mapping[str, Any]) -> Mapping[str, Any]:
    value = report.get("interaction")
    if not isinstance(value, Mapping):
        raise PresentationError("Fastlane Engine report is missing interaction state")
    return value


AWS_PROGRESS_STATES = {
    "AWS_GUIDANCE_REQUIRED",
    "AWS_READ_SCOPE_REQUIRED",
    "AWS_PREFLIGHT_RUNNING",
    "AWS_PREFLIGHT_READY",
    "WAITING_AWS_MUTATION_AUTH",
}

AWS_TEARDOWN_STATES = {
    "AWS_TEARDOWN_ACTION_TERMINAL",
    "AWS_RESIDUAL_REVIEW",
    "WAITING_AWS_TEARDOWN_AUTH",
    "AWS_RESIDUAL_REVIEW_COMPLETE",
    "AWS_RESIDUALS_RETAINED",
    "AWS_RESIDUALS_REMAIN",
    "AWS_RESIDUAL_REVIEW_BLOCKED",
    "AWS_TEARDOWN_COMPLETE",
}


def _teardown_blocker_reason(report: Mapping[str, Any]) -> str:
    """Return one safe, exact blocker from the validated teardown projection."""

    teardown = report.get("aws_teardown")
    if not isinstance(teardown, Mapping):
        raise PresentationError("blocked AWS residual review is missing teardown state")
    raw = teardown.get("blocker_or_stale_reason")
    if not isinstance(raw, str):
        raise PresentationError(
            "blocked AWS residual review is missing its exact reason"
        )
    reason = raw.strip()
    if (
        reason in {"", "NONE"}
        or len(reason) > 500
        or re.search(r"[\r\n\x00-\x1f\x7f]", reason) is not None
    ):
        raise PresentationError("blocked AWS residual review has an unsafe reason")
    return reason


def _validate_deployment_closure_capability(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> None:
    """Fail closed if a restricted deployment closure exceeds VERIFY evidence."""

    closure = report.get("deployment_journal_closure_authority")
    if closure is None:
        return
    if not isinstance(closure, Mapping):
        raise PresentationError("deployment closure capability is invalid")
    if closure.get("valid") is not True:
        return
    deployment = report.get("aws_deployment")
    authorizations = report.get("authorizations")
    writes = report.get("write_authority")
    external = report.get("external_authority")
    if (
        not isinstance(deployment, Mapping)
        or not isinstance(authorizations, Mapping)
        or not isinstance(writes, Mapping)
        or not isinstance(external, Mapping)
        or closure.get("kind") != "AWS_DEPLOYMENT_JOURNAL_CLOSURE"
        or closure.get("authorization_id") != "AWS_DEPLOYMENT_JOURNAL_CLOSURE"
        or closure.get("mode") != "BOUNDED_EVIDENCE_CLOSURE"
        or closure.get("allowed_write_paths") != ["docs/project/VERIFY.md"]
        or closure.get("construction_authorization") != "NONE"
        or closure.get("aws_mutation_authority") != "NONE"
        or authorizations.get("construction") != "NONE"
        or writes.get("valid") is not False
        or external.get("kind") in {"AWS_DEPLOYMENT", "AWS_TEARDOWN", "FAST_DEV_GATE_B"}
        or closure.get("attempt_id") != deployment.get("attempt_id")
    ):
        raise PresentationError("deployment closure capability exceeds its boundary")
    expected = {
        ("ACTION_TERMINAL_REQUIRED", "AWS-20"): (
            ["## AWS deployment action and reconciliation evidence"],
            ["APPEND_ACTION_TERMINAL_ROW"],
            [],
        ),
        ("RECONCILIATION_REQUIRED", "AWS-30"): (
            [
                "bootstrap:aws-read-preflight-receipt",
                "## Action authorization provenance",
                "## AWS deployment action and reconciliation evidence",
            ],
            [
                "RECORD_RECONCILIATION_READ_AUTHORITY",
                "APPEND_RECONCILIATION_ROW",
            ],
            [],
        ),
        ("RECONCILED", "RELEASE-10"): (
            ["## Current release decision"],
            ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
            (
                ["NOT_READY"]
                if deployment.get("basis_stale") is True
                else ["NOT_READY", "RELEASE_VERIFIED"]
            ),
        ),
        ("BLOCKED", "RELEASE-10"): (
            ["## Current release decision"],
            ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
            ["NOT_READY"],
        ),
    }.get((deployment.get("status"), report.get("next_prompt")))
    if (
        expected is None
        or (
            closure.get("allowed_sections"),
            closure.get("allowed_operations"),
            closure.get("allowed_release_states"),
        )
        != expected
    ):
        raise PresentationError("deployment closure operation is not route-bounded")


def _validate_teardown_closure_capability(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> None:
    """Fail closed if a restricted teardown closure exceeds VERIFY evidence."""

    closure = report.get("teardown_journal_closure_authority")
    reason = str(interaction.get("route_reason_code", ""))
    if closure is None:
        if reason == "AWS_TEARDOWN_ACTION_TERMINAL":
            raise PresentationError("teardown closure capability is missing")
        return
    if not isinstance(closure, Mapping):
        raise PresentationError("teardown closure capability is invalid")
    if closure.get("valid") is not True:
        if reason == "AWS_TEARDOWN_ACTION_TERMINAL":
            raise PresentationError("teardown closure capability is not current")
        return
    teardown = report.get("aws_teardown")
    authorizations = report.get("authorizations")
    writes = report.get("write_authority")
    external = report.get("external_authority")
    if (
        not isinstance(teardown, Mapping)
        or not isinstance(authorizations, Mapping)
        or not isinstance(writes, Mapping)
        or not isinstance(external, Mapping)
        or closure.get("kind") != "AWS_TEARDOWN_JOURNAL_CLOSURE"
        or closure.get("authorization_id") != "AWS_TEARDOWN_JOURNAL_CLOSURE"
        or closure.get("mode") != "BOUNDED_EVIDENCE_CLOSURE"
        or closure.get("allowed_write_paths") != ["docs/project/VERIFY.md"]
        or closure.get("allowed_sections")
        != ["## AWS teardown action and residual evidence"]
        or closure.get("allowed_operations") != ["APPEND_TEARDOWN_TERMINAL_ROW"]
        or closure.get("construction_authorization") != "NONE"
        or closure.get("aws_mutation_authority") != "NONE"
        or authorizations.get("construction") != "NONE"
        or writes.get("valid") is not False
        or external.get("kind") not in {"NONE", "AWS_READ_ONLY"}
        or closure.get("attempt_id") != teardown.get("attempt_id")
        or closure.get("evidence_id") != teardown.get("evidence_id")
        or teardown.get("status") != "ACTION_TERMINAL_REQUIRED"
        or report.get("next_prompt") != "AWS-50"
        or reason != "AWS_TEARDOWN_ACTION_TERMINAL"
    ):
        raise PresentationError("teardown closure capability exceeds its boundary")
    if (
        re.fullmatch(r"AWS-TEARDOWN-\d{4,}", str(teardown.get("attempt_id", "")))
        is None
        or re.fullmatch(r"EV-\d{4,}", str(teardown.get("evidence_id", ""))) is None
    ):
        raise PresentationError("teardown closure identifiers are invalid")


def _validate_aws_residual_disposition(
    report: Mapping[str, Any], reason: str
) -> Mapping[str, Any] | None:
    """Validate one evidence-bound, non-authorizing residual-set choice."""

    value = report.get("aws_residual_disposition")
    projection_required = reason in {
        "AWS_RESIDUALS_REMAIN",
        "AWS_RESIDUALS_RETAINED",
    }
    if value is None:
        if projection_required:
            raise PresentationError("AWS residual disposition projection is missing")
        return None
    if not isinstance(value, Mapping):
        raise PresentationError("AWS residual disposition projection is malformed")
    if (
        value.get("authorizes_aws_access") is not False
        or value.get("authorizes_mutation") is not False
    ):
        raise PresentationError(
            "AWS residual disposition exceeds its no-authority boundary"
        )
    issues = value.get("issues")
    if not isinstance(issues, list) or issues:
        raise PresentationError("AWS residual disposition contains unresolved issues")
    status = value.get("status")
    disposition = value.get("value")
    if status == "INVALID":
        raise PresentationError("AWS residual disposition is invalid")
    if status == "NOT_APPLICABLE":
        if disposition != "NONE":
            raise PresentationError("inactive AWS residual disposition is malformed")
        return value
    if status not in {"PENDING", "CURRENT"}:
        raise PresentationError("AWS residual disposition status is unknown")
    if (
        re.fullmatch(r"EV-\d{4,}", str(value.get("basis_evidence_id", ""))) is None
        or value.get("basis_status") not in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}
        or not _timezone_aware_timestamp(value.get("basis_observed_at"))
    ):
        raise PresentationError("AWS residual disposition basis is malformed")
    recorded_at = value.get("recorded_at")
    if recorded_at != "NONE" and not _timezone_aware_timestamp(recorded_at):
        raise PresentationError("AWS residual disposition timestamp is malformed")
    if status == "PENDING" and disposition != "NONE":
        raise PresentationError("pending AWS residual disposition claims a decision")
    if status == "CURRENT" and (
        disposition not in {"RETAIN", "INVESTIGATE", "REMOVE"}
        or not _timezone_aware_timestamp(recorded_at)
    ):
        raise PresentationError("current AWS residual disposition is malformed")
    if reason == "AWS_RESIDUALS_REMAIN" and status != "PENDING":
        raise PresentationError("AWS residual choice route lacks a pending disposition")
    if reason == "AWS_RESIDUALS_RETAINED" and (
        status != "CURRENT" or disposition != "RETAIN"
    ):
        raise PresentationError("retained AWS residual route conflicts with its choice")
    if reason == "WAITING_AWS_TEARDOWN_AUTH" and (
        status != "CURRENT" or disposition != "REMOVE"
    ):
        raise PresentationError("AWS teardown route lacks a current REMOVE choice")
    if (
        reason == "AWS_RESIDUAL_REVIEW"
        and status == "CURRENT"
        and disposition not in {"INVESTIGATE", "REMOVE"}
    ):
        raise PresentationError("AWS residual review conflicts with its current choice")
    return value


def _validate_aws_teardown_interaction(
    report: Mapping[str, Any],
    interaction: Mapping[str, Any],
) -> bool:
    """Validate teardown states before deployment-progress compatibility checks."""

    reason = str(interaction.get("route_reason_code", ""))
    action = str(interaction.get("owner_action_kind", ""))
    if reason not in AWS_TEARDOWN_STATES:
        if action in {"AUTHORIZE_AWS_TEARDOWN", "CHOOSE_AWS_RESIDUAL_DISPOSITION"}:
            raise PresentationError(
                "AWS teardown action is requested in the wrong state"
            )
        return False

    _validate_aws_residual_disposition(report, reason)
    required = interaction.get("owner_action_required") is True
    automatic = interaction.get("automatic_continuation_allowed") is True
    formal = interaction.get("formal_receipt_required") is True

    if reason == "AWS_TEARDOWN_ACTION_TERMINAL":
        teardown = report.get("aws_teardown")
        if (
            not isinstance(teardown, Mapping)
            or teardown.get("status") != "ACTION_TERMINAL_REQUIRED"
            or report.get("next_prompt") != "AWS-50"
            or action != "NONE_CONTINUE_AUTOMATICALLY"
            or required
            or not automatic
            or formal
        ):
            raise PresentationError(
                "AWS teardown terminalization conflicts with its attempt state"
            )
    elif reason == "AWS_RESIDUAL_REVIEW":
        awaiting = action == "AUTHORIZE_AWS_READ_PREFLIGHT"
        continuing = action == "NONE_CONTINUE_AUTOMATICALLY"
        if awaiting:
            if not required or automatic or not formal:
                raise PresentationError(
                    "AWS residual read authority state is inconsistent"
                )
        elif continuing:
            if required or not automatic or formal:
                raise PresentationError(
                    "automatic AWS residual review state is inconsistent"
                )
        else:
            raise PresentationError("invalid AWS residual-review action")
    elif reason == "WAITING_AWS_TEARDOWN_AUTH":
        awaiting = action == "AUTHORIZE_AWS_TEARDOWN"
        continuing = action == "NONE_CONTINUE_AUTOMATICALLY"
        if awaiting:
            if not required or automatic or not formal:
                raise PresentationError("AWS teardown authority state is inconsistent")
        elif continuing:
            if required or not automatic or formal:
                raise PresentationError("authorized AWS teardown state is inconsistent")
        else:
            raise PresentationError("invalid AWS teardown-wait action")
    elif reason in {
        "AWS_RESIDUAL_REVIEW_COMPLETE",
        "AWS_RESIDUALS_RETAINED",
        "AWS_TEARDOWN_COMPLETE",
    }:
        if action != "NONE_CONTINUE_AUTOMATICALLY" or required or automatic or formal:
            raise PresentationError("terminal AWS teardown state is inconsistent")
        if reason == "AWS_RESIDUALS_RETAINED" and (
            interaction.get("state") != "COMPLETE"
            or report.get("next_prompt") != "STOP"
        ):
            raise PresentationError("retained AWS residual state is not terminal")
    elif reason == "AWS_RESIDUALS_REMAIN":
        if (
            action != "CHOOSE_AWS_RESIDUAL_DISPOSITION"
            or not required
            or automatic
            or formal
            or interaction.get("state") != "NEEDS_INPUT"
            or report.get("next_prompt") != "STOP"
        ):
            raise PresentationError("AWS residual disposition state is inconsistent")
    elif reason == "AWS_RESIDUAL_REVIEW_BLOCKED":
        if action != "REVIEW_SAFETY_BLOCKER" or not required or automatic or formal:
            raise PresentationError("blocked AWS residual review state is inconsistent")
    return True


def _validate_aws_deployment_interaction(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> bool:
    """Validate AWS-30 as a separate read-only authority boundary."""

    reason = str(interaction.get("route_reason_code", ""))
    if reason not in {
        "AWS_DEPLOYMENT_ACTION_TERMINAL",
        "AWS_DEPLOYMENT_RECONCILIATION",
    }:
        return False
    deployment = report.get("aws_deployment")
    if not isinstance(deployment, Mapping):
        raise PresentationError(
            "AWS deployment reconciliation is missing its attempt projection"
        )
    attempt_id = deployment.get("attempt_id")
    if (
        not isinstance(attempt_id, str)
        or re.fullmatch(r"AWS-DEPLOY-\d{4,}", attempt_id) is None
    ):
        raise PresentationError("AWS deployment attempt identifier is invalid")
    action = str(interaction.get("owner_action_kind", ""))
    required = interaction.get("owner_action_required") is True
    automatic = interaction.get("automatic_continuation_allowed") is True
    formal = interaction.get("formal_receipt_required") is True
    external = report.get("external_authority")
    if not isinstance(external, Mapping):
        raise PresentationError("AWS deployment authority state is missing")
    if reason == "AWS_DEPLOYMENT_ACTION_TERMINAL":
        if (
            deployment.get("status") != "ACTION_TERMINAL_REQUIRED"
            or report.get("next_prompt") != "AWS-20"
            or action != "NONE_CONTINUE_AUTOMATICALLY"
            or required
            or not automatic
            or formal
            or external.get("kind") != "NONE"
            or external.get("validity") != "NONE"
        ):
            raise PresentationError(
                "AWS deployment terminalization conflicts with its attempt state"
            )
        return True
    if (
        deployment.get("status") != "RECONCILIATION_REQUIRED"
        or report.get("next_prompt") != "AWS-30"
    ):
        raise PresentationError(
            "AWS deployment reconciliation conflicts with its attempt state"
        )
    if action == "AUTHORIZE_AWS_READ_PREFLIGHT":
        if (
            not required
            or automatic
            or not formal
            or external.get("kind") != "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
            or external.get("validity") != "REQUIRED"
        ):
            raise PresentationError(
                "AWS deployment reconciliation read authority is inconsistent"
            )
    elif action == "NONE_CONTINUE_AUTOMATICALLY":
        if (
            required
            or not automatic
            or formal
            or external.get("kind") != "AWS_READ_ONLY"
            or external.get("validity") != "CURRENT"
        ):
            raise PresentationError(
                "automatic AWS deployment reconciliation is inconsistent"
            )
    else:
        raise PresentationError("invalid AWS deployment reconciliation action")
    return True


def _validate_aws_progress_interaction(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> None:
    """Fail closed when AWS guidance, read, and mutation boundaries conflict."""

    _validate_deployment_closure_capability(report, interaction)
    _validate_teardown_closure_capability(report, interaction)
    reason = str(interaction.get("route_reason_code", ""))
    action = str(interaction.get("owner_action_kind", ""))
    required = interaction.get("owner_action_required") is True
    automatic = interaction.get("automatic_continuation_allowed") is True
    formal = interaction.get("formal_receipt_required") is True
    if _validate_aws_teardown_interaction(report, interaction):
        return
    if _validate_aws_deployment_interaction(report, interaction):
        return

    execution = report.get("aws_execution")
    progress = (
        str(execution.get("progress_state", ""))
        if isinstance(execution, Mapping)
        else ""
    )
    lane = str(execution.get("lane", "")) if isinstance(execution, Mapping) else ""

    if reason in AWS_PROGRESS_STATES:
        if not isinstance(execution, Mapping) or progress != reason:
            raise PresentationError(
                "AWS progress state conflicts with interaction route"
            )
    elif progress in AWS_PROGRESS_STATES:
        if (
            interaction.get("response_mode") == "BLOCKER"
            and action in {"FIX_VALIDATION_FAILURE", "REVIEW_SAFETY_BLOCKER"}
            and required
            and not automatic
            and not formal
        ):
            return
        raise PresentationError("AWS interaction route conflicts with progress state")

    if action == "AUTHORIZE_AWS_READ_PREFLIGHT" and reason != "AWS_READ_SCOPE_REQUIRED":
        raise PresentationError(
            "read-only AWS authority is requested in the wrong state"
        )
    if action == "AUTHORIZE_AWS_OPERATION" and reason != "WAITING_AWS_MUTATION_AUTH":
        raise PresentationError(
            "AWS mutation authority is requested before preflight readiness"
        )

    if reason == "AWS_READ_SCOPE_REQUIRED":
        if (
            action != "AUTHORIZE_AWS_READ_PREFLIGHT"
            or not required
            or automatic
            or not formal
        ):
            raise PresentationError("read-only AWS authority state is inconsistent")
    elif reason in {"AWS_GUIDANCE_REQUIRED", "AWS_PREFLIGHT_RUNNING"}:
        if (
            action != "NONE_CONTINUE_AUTOMATICALLY"
            or required
            or not automatic
            or formal
        ):
            raise PresentationError("automatic AWS progress state is inconsistent")
    elif reason == "AWS_PREFLIGHT_READY":
        if lane in {"documentation-only", "read-only"}:
            expected_automatic = False
        else:
            raise PresentationError("AWS preflight readiness has an unsupported lane")
        if (
            action != "NONE_CONTINUE_AUTOMATICALLY"
            or required
            or formal
            or automatic is not expected_automatic
        ):
            raise PresentationError("terminal AWS preflight state is inconsistent")
    elif reason == "WAITING_AWS_MUTATION_AUTH":
        awaiting = action == "AUTHORIZE_AWS_OPERATION"
        continuing = action == "NONE_CONTINUE_AUTOMATICALLY"
        external = report.get("external_authority")
        if not isinstance(external, Mapping):
            raise PresentationError("AWS mutation authority projection is missing")
        if awaiting:
            if (
                not required
                or automatic
                or not formal
                or external.get("kind") != "AWS_ACTION_RECEIPT_REQUIRED"
                or external.get("validity") != "REQUIRED"
            ):
                raise PresentationError("AWS mutation authority state is inconsistent")
        elif continuing:
            if (
                required
                or not automatic
                or formal
                or external.get("kind") != "AWS_DEPLOYMENT"
                or external.get("validity") != "CURRENT"
            ):
                raise PresentationError(
                    "authorized AWS continuation state is inconsistent"
                )
        else:
            raise PresentationError("invalid AWS mutation-wait action")


def _remediation_text(report: Mapping[str, Any]) -> tuple[str | None, str | None]:
    value = report.get("remediation")
    if value is None:
        return None, None
    if not isinstance(value, Mapping):
        raise PresentationError("Fastlane Engine report has invalid remediation state")
    next_action = value.get("next_action")
    if not isinstance(next_action, Mapping):
        raise PresentationError(
            "Fastlane Engine report has invalid remediation next action"
        )
    action_kind = str(next_action.get("action_kind", ""))
    party = str(next_action.get("responsible_party", ""))
    automatic = next_action.get("automatic_continuation_allowed") is True
    if action_kind == "REPLAN_TASKS":
        if (
            party != "CODEX"
            or not automatic
            or next_action.get("preserve_done_evidence") is not True
        ):
            raise PresentationError("unsafe automatic task-replan state")
        return (
            "Fastlane found a task-plan coverage defect.",
            "Codex will replan only the affected tasks and preserve completed evidence.",
        )
    if action_kind == "CORRECT_AND_REVALIDATE":
        if party != "CODEX" or not automatic:
            raise PresentationError("unsafe automatic remediation state")
        return (
            "Fastlane found an in-scope validation defect.",
            "Codex will correct the reported in-scope failure and rerun validation.",
        )
    if action_kind == "REVIEW_SAFETY_BLOCKER":
        if party != "HUMAN_REVIEWER" or automatic:
            raise PresentationError("unsafe manual remediation state")
        return None, None
    if action_kind not in {
        "ANSWER_OPEN_DECISIONS",
        "APPROVE_GATE_A",
        "APPROVE_GATE_B",
        "AUTHORIZE_AWS_READ_PREFLIGHT",
        "AUTHORIZE_AWS_OPERATION",
        "AUTHORIZE_AWS_TEARDOWN",
        "CHOOSE_AWS_RESIDUAL_DISPOSITION",
        "COMPLETE_PREREQUISITE_CHECKLIST",
        "CONTINUE_CURRENT_ROUTE",
        "ENABLE_AWS_CORE",
    }:
        raise PresentationError("unknown remediation next action")
    return None, None


def _task_details(report: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = report.get("tasks")
    return value if isinstance(value, Mapping) else None


TASK_ID_PATTERN = TASK_ID
AWS_DISCOVERY_ID_PATTERN = re.compile(r"AWS-DISC-\d{4,}")
AWS_SKILL_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]*")
AWS_OFFICIAL_REFERENCE_PATTERN = re.compile(
    r"https://(?:docs\.aws\.amazon\.com|aws\.amazon\.com)/\S+", re.IGNORECASE
)


def _task_ids(tasks: Mapping[str, Any], field: str) -> list[str]:
    value = tasks.get(field)
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PresentationError("invalid deterministic task identifiers")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or TASK_ID_PATTERN.fullmatch(item) is None:
            raise PresentationError("invalid deterministic task identifiers")
        result.append(item)
    if len(result) != len(set(result)):
        raise PresentationError("duplicate deterministic task identifiers")
    return result


def _task_count(tasks: Mapping[str, Any], field: str) -> int:
    value = tasks.get(field, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PresentationError("invalid deterministic task progress")
    return value


def _delivery_status(report: Mapping[str, Any], reason: str) -> str | None:
    if reason not in {"CONSTRUCTION_SINGLE", "CONSTRUCTION_AUTONOMOUS"}:
        return None
    tasks = _task_details(report)
    if tasks is None:
        return None
    total = _task_count(tasks, "total")
    completed = _task_count(tasks, "completed")
    skipped = _task_count(tasks, "skipped")
    blocked = _task_count(tasks, "blocked")
    ready_count = _task_count(tasks, "ready")
    active_count = _task_count(tasks, "in_progress")
    active = _task_ids(tasks, "active_ids")
    ready = _task_ids(tasks, "ready_ids")
    if (
        total < 1
        or sum((completed, skipped, blocked, ready_count, active_count)) > total
    ):
        raise PresentationError("invalid deterministic task progress")
    if "active_ids" in tasks and len(active) != active_count:
        raise PresentationError("active task count does not match task identifiers")
    if "ready_ids" in tasks and len(ready) != ready_count:
        raise PresentationError("ready task count does not match task identifiers")
    if "blocked_ids" in tasks:
        blocked_ids = _task_ids(tasks, "blocked_ids")
        if len(blocked_ids) != blocked:
            raise PresentationError(
                "blocked task count does not match task identifiers"
            )
    status = f"{completed} of {total} tasks complete"
    if skipped:
        status += f"; {skipped} skipped with an approved record"
    if active:
        status += "; working on " + ", ".join(active)
    elif ready:
        status += f"; {ready[0]} is ready next"
    return status + "."


def _delivery_next(report: Mapping[str, Any], reason: str) -> str | None:
    if reason not in {"CONSTRUCTION_SINGLE", "CONSTRUCTION_AUTONOMOUS"}:
        return None
    tasks = _task_details(report)
    if tasks is None:
        return None
    active = _task_ids(tasks, "active_ids")
    ready = _task_ids(tasks, "ready_ids")
    if active:
        return "Codex will finish and validate " + ", ".join(active) + "."
    if ready:
        return f"Codex will continue with {ready[0]}."
    return None


def _coverage_next(report: Mapping[str, Any], reason: str) -> str | None:
    if reason not in {"DESIGN_REQUIRED", "DESIGN_STALE"}:
        return None
    value = report.get("coverage_plan")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise PresentationError("invalid deterministic coverage plan")
    if value.get("status") != "READY":
        return None
    disposition = value.get("architecture_disposition")
    if disposition == "SELECT":
        return "Codex will compare complete architecture candidates."
    if disposition == "AMEND":
        return (
            "Codex will reconsider only architecture decisions affected by this change."
        )
    if disposition == "PRESERVE":
        return (
            "Codex will verify that the existing architecture remains valid "
            "for this bounded change."
        )
    raise PresentationError("invalid deterministic architecture disposition")


def _aws_core_audit(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> str | None:
    """Render AWS Core attribution only from the doctor's observed projection."""

    core = interaction.get("aws_core")
    if not isinstance(core, Mapping):
        return None
    evidence_status = core.get("evidence_status")
    materiality = core.get("materiality")
    if evidence_status != "CURRENT":
        return None
    if materiality != "MATERIAL":
        raise PresentationError(
            "current AWS Core evidence requires a material doctor projection"
        )
    stage = str(interaction.get("owner_stage", ""))
    next_prompt = str(report.get("next_prompt", ""))
    if stage == "DEFINE" and next_prompt in {"REQ-10", "INTAKE-20"}:
        phase = "REQ-10"
    elif stage == "DESIGN":
        phase = "DESIGN-10"
    elif next_prompt.startswith("AWS-"):
        phase = "AWS-10"
    else:
        return None
    evidence = report.get("aws_core_evidence")
    if not isinstance(evidence, Mapping):
        return None
    observed = evidence.get("observed_usage")
    if not isinstance(observed, Mapping):
        return None
    usage = observed.get(phase)
    if not isinstance(usage, Mapping) or usage.get("status") != "OBSERVED":
        return None
    chains = usage.get("chains")
    if (
        not isinstance(chains, Sequence)
        or isinstance(chains, (str, bytes))
        or not chains
    ):
        raise PresentationError("invalid observed AWS Core attribution")
    skills: list[str] = []
    references: list[str] = []
    for chain in chains:
        if not isinstance(chain, Mapping):
            raise PresentationError("invalid observed AWS Core attribution")
        discovery_id = chain.get("discovery_id")
        skill = chain.get("skill_identifier")
        refs = chain.get("official_references")
        if (
            not isinstance(discovery_id, str)
            or AWS_DISCOVERY_ID_PATTERN.fullmatch(discovery_id) is None
            or not isinstance(skill, str)
            or AWS_SKILL_IDENTIFIER_PATTERN.fullmatch(skill) is None
            or chain.get("credentials_inspected") is not False
            or chain.get("aws_account_accessed") is not False
            or not isinstance(refs, Sequence)
            or isinstance(refs, (str, bytes))
            or not refs
        ):
            raise PresentationError("invalid observed AWS Core attribution")
        skills.append(skill)
        for reference in refs:
            if (
                not isinstance(reference, str)
                or AWS_OFFICIAL_REFERENCE_PATTERN.fullmatch(reference) is None
            ):
                raise PresentationError("invalid observed AWS Core attribution")
            references.append(reference)
    skill_text = ", ".join(dict.fromkeys(skills))
    reference_text = ", ".join(dict.fromkeys(references))
    return (
        f"AWS Core returned {skill_text} for this decision and supplied "
        f"{reference_text}. No AWS account was accessed."
    )


def _aws_deployment_audit(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> str | None:
    """Describe a journaled attempt without implying deployment success."""

    reason = interaction.get("route_reason_code")
    if reason not in {
        "AWS_DEPLOYMENT_ACTION_TERMINAL",
        "AWS_DEPLOYMENT_RECONCILIATION",
    }:
        return None
    deployment = report.get("aws_deployment")
    if not isinstance(deployment, Mapping):
        raise PresentationError("AWS deployment attempt projection is missing")
    attempt_id = deployment.get("attempt_id")
    action_status = deployment.get("action_status")
    if (
        not isinstance(attempt_id, str)
        or re.fullmatch(r"AWS-DEPLOY-\d{4,}", attempt_id) is None
        or action_status not in {"STARTED", "SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN"}
    ):
        raise PresentationError("AWS deployment attempt projection is invalid")
    if reason == "AWS_DEPLOYMENT_ACTION_TERMINAL":
        return (
            f"Deployment attempt {attempt_id} is append-only journaled with action "
            "status STARTED. Codex must record terminal UNKNOWN before read-only "
            "reconciliation; no further mutation is authorized."
        )
    return (
        f"Deployment attempt {attempt_id} is append-only journaled with action "
        f"status {action_status}. Reconciliation uses separate read-only authority; "
        "no further mutation is authorized."
    )


def _deployment_closure_audit(report: Mapping[str, Any]) -> str | None:
    closure = report.get("deployment_journal_closure_authority")
    if not isinstance(closure, Mapping) or closure.get("valid") is not True:
        return None
    allowed_states = closure.get("allowed_release_states")
    if isinstance(allowed_states, list) and allowed_states:
        return (
            "Local changes are limited to the exact release decision and evidence "
            "cutoff in VERIFY.md, with allowed release states "
            + ", ".join(str(item) for item in allowed_states)
            + "; construction and AWS mutation remain unauthorized."
        )
    return (
        "Local changes are limited to the exact deployment-evidence closure in "
        "VERIFY.md; construction and AWS mutation remain unauthorized."
    )


def _teardown_closure_audit(report: Mapping[str, Any]) -> str | None:
    closure = report.get("teardown_journal_closure_authority")
    if not isinstance(closure, Mapping) or closure.get("valid") is not True:
        return None
    teardown = report.get("aws_teardown")
    if not isinstance(teardown, Mapping):
        raise PresentationError("AWS teardown attempt projection is missing")
    return (
        f"Teardown attempt {teardown.get('attempt_id')} is append-only journaled "
        "with action status STARTED. Codex may append only terminal UNKNOWN to "
        "the teardown evidence in VERIFY.md; construction and AWS mutation remain "
        "unauthorized."
    )


AWS_LIFECYCLE_INTENT_SOURCE_PATTERN = re.compile(
    r"owner-message MSG-AWS-LIFECYCLE-\d{4,}"
)
AWS_LIFECYCLE_INTENT_ROUTES = {
    "RETAIN": {
        "AWS_RESIDUALS_RETAINED",
    },
    "RESIDUAL_REVIEW": {
        "AWS_RESIDUAL_REVIEW",
        "AWS_RESIDUAL_REVIEW_COMPLETE",
        "AWS_RESIDUALS_REMAIN",
        "AWS_RESIDUAL_REVIEW_BLOCKED",
    },
    "TEARDOWN": {
        "AWS_RESIDUAL_REVIEW",
        "AWS_RESIDUAL_REVIEW_COMPLETE",
        "AWS_RESIDUALS_REMAIN",
        "AWS_RESIDUAL_REVIEW_BLOCKED",
        "WAITING_AWS_TEARDOWN_AUTH",
        "AWS_TEARDOWN_ACTION_TERMINAL",
        "AWS_TEARDOWN_COMPLETE",
    },
}


def _timezone_aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _aws_lifecycle_intent_audit(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> str | None:
    """Render only a current, non-authorizing owner lifecycle intent."""

    residual_disposition = report.get("aws_residual_disposition")
    if isinstance(residual_disposition, Mapping) and (
        residual_disposition.get("status") == "PENDING"
    ):
        return None
    if "aws_lifecycle_intent" not in report:
        # Older report fixtures and initialized projects remain renderable until
        # the Engine emits the new canonical projection.
        return None
    intent = report.get("aws_lifecycle_intent")
    if not isinstance(intent, Mapping):
        raise PresentationError("AWS lifecycle intent projection is malformed")
    value = intent.get("value")
    source = intent.get("source")
    recorded_at = intent.get("recorded_at")
    provenance_status = intent.get("provenance_status")
    if (
        intent.get("authorizes_aws_access") is not False
        or intent.get("authorizes_mutation") is not False
    ):
        raise PresentationError(
            "AWS lifecycle intent exceeds its no-authority boundary"
        )
    if value == "NONE":
        if (
            source != "NONE"
            or recorded_at != "NONE"
            or provenance_status not in {"CURRENT", "LEGACY_NONE"}
        ):
            raise PresentationError("AWS lifecycle intent NONE provenance is malformed")
        return None
    if (
        value not in AWS_LIFECYCLE_INTENT_ROUTES
        or not isinstance(source, str)
        or AWS_LIFECYCLE_INTENT_SOURCE_PATTERN.fullmatch(source) is None
        or not _timezone_aware_timestamp(recorded_at)
        or provenance_status != "CURRENT"
    ):
        raise PresentationError("AWS lifecycle intent provenance is malformed")
    choice = {
        "RETAIN": "RETAIN",
        "RESIDUAL_REVIEW": "INVESTIGATE",
        "TEARDOWN": "REMOVE",
    }[value]
    if isinstance(residual_disposition, Mapping) and (
        residual_disposition.get("status") == "CURRENT"
        and residual_disposition.get("value") != choice
    ):
        raise PresentationError(
            "AWS lifecycle intent conflicts with residual disposition"
        )
    reason = str(interaction.get("route_reason_code", ""))
    if reason not in AWS_LIFECYCLE_INTENT_ROUTES[value]:
        raise PresentationError("AWS lifecycle intent conflicts with the current route")
    if choice == "RETAIN":
        return (
            f"Owner chose RETAIN at {recorded_at}; this records intentional retention "
            "and grants no AWS access or mutation."
        )
    if choice == "INVESTIGATE":
        return (
            f"Owner chose INVESTIGATE at {recorded_at}; this selects a read-only "
            "residual review and grants no AWS access or mutation."
        )
    return (
        f"Owner chose REMOVE at {recorded_at}; this requests the teardown path but "
        "grants no AWS access or mutation; a separate exact teardown authorization "
        "is still required."
    )


def _aws_preflight_audit(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> str | None:
    """Describe account access only from the validated AWS execution projection."""

    reason = str(interaction.get("route_reason_code", ""))
    if reason not in {
        "AWS_PREFLIGHT_RUNNING",
        "AWS_PREFLIGHT_READY",
        "WAITING_AWS_MUTATION_AUTH",
    }:
        return None
    execution = report.get("aws_execution")
    if not isinstance(execution, Mapping):
        raise PresentationError(
            "AWS preflight state is missing its execution projection"
        )
    preflight = execution.get("preflight")
    if not isinstance(preflight, Mapping):
        raise PresentationError(
            "AWS preflight state is missing its evidence projection"
        )
    status = str(preflight.get("status", ""))
    account_access = str(preflight.get("account_access", ""))
    lane = str(execution.get("lane", ""))
    if reason == "AWS_PREFLIGHT_READY" and lane == "documentation-only":
        if (
            status != "NOT_APPLICABLE"
            or account_access != "NOT_USED"
            or any(
                preflight.get(field) != "NONE"
                for field in ("account", "region", "environment")
            )
        ):
            raise PresentationError(
                "documentation-only readiness conflicts with its no-account boundary"
            )
        return (
            "Documentation-only AWS guidance is complete. No AWS account was accessed."
        )

    for field in ("account", "region", "environment"):
        value = preflight.get(field)
        if not isinstance(value, str) or not value.strip():
            raise PresentationError("AWS preflight scope is incomplete")

    if reason == "AWS_PREFLIGHT_RUNNING":
        if status == "NOT_STARTED" and account_access == "NOT_OBSERVED":
            return (
                "The authorized preflight will access only the owner-approved named "
                "AWS account scope read-only. No mutation is authorized."
            )
        if status == "RUNNING" and account_access == "READ_ONLY_OBSERVED":
            return (
                "Authenticated preflight accessed the owner-approved named AWS account "
                "scope read-only and is still running. No mutation was performed."
            )
        raise PresentationError(
            "AWS preflight running state is not safely attributable"
        )

    if status != "READY" or account_access != "READ_ONLY_OBSERVED":
        raise PresentationError(
            "AWS preflight readiness is not supported by observed access"
        )
    return (
        "Authenticated preflight accessed the owner-approved named AWS account scope "
        "read-only. No mutation was performed."
    )


def _aws_ready_owner_copy(
    report: Mapping[str, Any], reason: str
) -> tuple[str, str] | None:
    """Return lane-specific terminal copy without changing authority."""

    if reason != "AWS_PREFLIGHT_READY":
        return None
    execution = report.get("aws_execution")
    if not isinstance(execution, Mapping):
        raise PresentationError("AWS readiness is missing its execution projection")
    lane = str(execution.get("lane", ""))
    if lane == "documentation-only":
        return (
            "Documentation-only AWS guidance is complete.",
            "No AWS account or resource action will occur.",
        )
    if lane == "read-only":
        return (
            "The authorized read-only AWS inspection is complete.",
            "No AWS resource mutation will occur.",
        )
    raise PresentationError("AWS preflight readiness has an unsupported lane")


def _pending_intake_card(report: Mapping[str, Any]) -> Mapping[str, Any] | None:
    foundation = report.get("intake_foundation")
    if foundation is None:
        return None
    if not isinstance(foundation, Mapping):
        raise PresentationError("invalid deterministic intake foundation")
    card = foundation.get("pending_card")
    if card is None:
        return None
    if not isinstance(card, Mapping):
        raise PresentationError("invalid deterministic intake card")
    card_id = card.get("card_id")
    revision = card.get("revision")
    questions = card.get("questions")
    owner_reply = card.get("owner_reply")
    exact_reply = card.get("exact_reply")
    reply_token = card.get("reply_token")
    digest = card.get("canonical_sha256")
    if (
        not isinstance(card_id, str)
        or re.fullmatch(r"INTAKE-CARD-\d{4,}", card_id) is None
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
        or not isinstance(questions, Sequence)
        or isinstance(questions, (str, bytes))
        or len(questions) != 1
        or not isinstance(owner_reply, str)
        or not owner_reply.strip()
        or not isinstance(exact_reply, str)
        or not exact_reply.strip()
        or not isinstance(digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        or not isinstance(reply_token, str)
        or re.fullmatch(r"R-[0-9A-F]{12}", reply_token) is None
        or not isinstance(card.get("accept_all_allowed"), bool)
    ):
        raise PresentationError("invalid deterministic intake card")
    if (
        reply_token != intake_reply_token(card_id, revision, digest)
        or exact_reply != reply_token + "; " + owner_reply
    ):
        raise PresentationError(
            "intake copyable reply is not bound to its current card"
        )
    reply_keys: set[str] = set()
    for question in questions:
        if not isinstance(question, Mapping):
            raise PresentationError("invalid deterministic intake question")
        reply_key = question.get("reply_key")
        kind = question.get("kind")
        prompt = question.get("prompt")
        options = question.get("options")
        recommended = question.get("recommended")
        required = question.get("required_detail_for")
        if (
            reply_key not in {"1", "2", "3"}
            or reply_key in reply_keys
            or kind not in {"FACT", "DECISION"}
            or not isinstance(prompt, str)
            or not prompt.strip()
            or not isinstance(required, Sequence)
            or isinstance(required, (str, bytes))
        ):
            raise PresentationError("invalid deterministic intake question")
        reply_keys.add(str(reply_key))
        if kind == "DECISION":
            required_values = tuple(required)
            if (
                not isinstance(options, Mapping)
                or set(options) != {"A", "B", "C"}
                or any(
                    not isinstance(options[key], str) or not options[key].strip()
                    for key in ("A", "B", "C")
                )
                or recommended not in {None, "A"}
                or any(value not in {"A", "B", "C"} for value in required_values)
                or len(required_values) != len(set(required_values))
            ):
                raise PresentationError("invalid deterministic intake choices")
            if required_values:
                if (
                    not isinstance(question.get("detail_prompt"), str)
                    or not question["detail_prompt"].strip()
                ):
                    raise PresentationError(
                        "intake choices requiring detail need a concrete prompt"
                    )
            elif question.get("detail_prompt") is not None:
                raise PresentationError(
                    "intake choices without required detail cannot add a detail prompt"
                )
        elif (
            options != {}
            or recommended is not None
            or tuple(required) != ("RESPONSE",)
            or not isinstance(question.get("detail_prompt"), str)
            or not question["detail_prompt"].strip()
        ):
            raise PresentationError(
                "factual intake questions require one concrete response prompt"
            )
    return card


def _intake_current_understanding(report: Mapping[str, Any]) -> tuple[str, ...]:
    foundation = report.get("intake_foundation")
    if foundation is None:
        return ()
    if not isinstance(foundation, Mapping):
        raise PresentationError("invalid deterministic intake foundation")
    schema_version = foundation.get("schema_version", 1)
    if schema_version == 1:
        return ()
    if schema_version != 2:
        raise PresentationError("unsupported deterministic intake foundation schema")
    summary = foundation.get("current_understanding")
    if (
        not isinstance(summary, Sequence)
        or isinstance(summary, (str, bytes))
        or len(summary) > 5
    ):
        raise PresentationError("invalid deterministic current-understanding summary")
    normalized: list[str] = []
    for item in summary:
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            raise PresentationError(
                "invalid deterministic current-understanding summary"
            )
        normalized.append(item)
    return tuple(normalized)


def _intake_consultation(
    report: Mapping[str, Any], card: Mapping[str, Any]
) -> tuple[str, tuple[str, ...], str]:
    """Return owner-safe wording from the Engine's current question guidance."""

    foundation = report.get("intake_foundation")
    if not isinstance(foundation, Mapping):
        raise PresentationError("intake consultation requires the current foundation")
    if foundation.get("schema_version") == 1:
        question = card["questions"][0]
        return "", (), str(question["prompt"])
    guidance = foundation.get("next_question_guidance")
    if not isinstance(guidance, Mapping) or guidance.get("schema_version") != 1:
        raise PresentationError("intake consultation guidance is invalid")
    if (
        guidance.get("status")
        not in {
            "STARTING_POINT_REQUIRED",
            "QUESTION_REQUIRED",
        }
        or guidance.get("owner_action_required") is not True
    ):
        raise PresentationError("intake consultation is not awaiting one owner answer")
    objective = guidance.get("objective")
    fields = guidance.get("fields")
    target_ids = guidance.get("target_ids")
    if (
        not isinstance(objective, str)
        or not objective.strip()
        or len(objective) > 400
        or not isinstance(fields, Sequence)
        or isinstance(fields, (str, bytes))
        or not 1 <= len(fields) <= 3
        or any(
            not isinstance(field, str)
            or re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", field) is None
            for field in fields
        )
        or not isinstance(target_ids, Sequence)
        or isinstance(target_ids, (str, bytes))
    ):
        raise PresentationError("intake consultation guidance is malformed")
    question = card["questions"][0]
    if tuple(target_ids) != tuple(question.get("basis_ids", ())):
        raise PresentationError(
            "intake consultation does not bind the current question"
        )
    owner_objective = _owner_consultation_objective(objective)
    prompt = str(question["prompt"])
    if tuple(fields) == ("OWNER_WORK_CONTEXT",):
        prompt = "What kind of project are we starting together?"
    return owner_objective, tuple(str(field) for field in fields), prompt


def _owner_consultation_objective(objective: str) -> str:
    replacements = (
        ("Learn whether the owner is ", "This tells Fastlane whether you are "),
        ("Understand ", "This helps Fastlane understand "),
        ("Define ", "This helps define "),
        ("Identify ", "This identifies "),
        ("Clarify ", "This clarifies "),
    )
    rendered = objective.strip()
    for prefix, replacement in replacements:
        if rendered.startswith(prefix):
            rendered = replacement + rendered[len(prefix) :]
            break
    if re.search(r"(?:INTAKE|REQ|DES|AUTH)-|\b(?:digest|parser|schema)\b", rendered):
        raise PresentationError("intake consultation exposes internal terminology")
    return rendered


def _intake_project_effect(fields: tuple[str, ...]) -> str:
    field_set = set(fields)
    if field_set == {"OWNER_WORK_CONTEXT"}:
        return (
            "Your answer tells Fastlane whether existing behavior, data, and "
            "migration risk must be protected."
        )
    if field_set & {"PRIMARY_USERS", "OWNER_STATED_PROBLEM", "OBSERVABLE_OUTCOME"}:
        return (
            "Your answer establishes who the product serves, the problem to solve, "
            "and the first useful result."
        )
    if field_set & {"FIRST_RELEASE_BOUNDARY", "SUCCESS_MEASURE"}:
        return (
            "Your answer sets the smallest useful first release and how its result "
            "will be recognized."
        )
    if field_set & {"DATA_TYPES", "DATA_SENSITIVITY"}:
        return (
            "Your answer shapes the product's data, access, privacy, and security "
            "requirements."
        )
    return (
        "Your answer sets the first audience and any location boundary that the "
        "Product Agreement must preserve."
    )


def _intake_question_lines(
    card: Mapping[str, Any], *, prompt: str | None = None
) -> list[str]:
    questions = card["questions"]
    lines: list[str] = []
    for question in questions:
        reply_key = str(question["reply_key"])
        owner_prompt = prompt or str(question["prompt"])
        lines.extend(("", f"{reply_key}. {owner_prompt}"))
        if question["kind"] == "DECISION":
            options = question["options"]
            recommended = question["recommended"]
            required = set(question["required_detail_for"])
            for choice in ("A", "B", "C"):
                prefix = "Recommended \u2014 " if recommended == choice else ""
                lines.extend(("", f"{choice}. {prefix}{options[choice]}"))
                if choice in required:
                    lines.append(
                        f"   If you choose {choice}: {question['detail_prompt']}"
                    )
            if recommended is None:
                lines.extend(
                    (
                        "",
                        "No recommendation—choose the option that matches your situation.",
                    )
                )
        else:
            lines.append(f"Reply: {question['detail_prompt']}")
    return lines


def _intake_reply_guidance(card: Mapping[str, Any]) -> list[str]:
    """Return copyable values only when the displayed value is a valid reply."""

    questions = card["questions"]
    if card["accept_all_allowed"] or all(
        question["kind"] == "DECISION" and question["recommended"] is not None
        for question in questions
    ):
        recommendation = questions[0]["recommended"]
        if recommendation not in {"A", "B", "C"}:
            raise PresentationError(
                "copyable decision reply requires a current recommendation"
            )
        return ["Copyable reply:", str(recommendation)]
    if len(questions) == 1 and questions[0]["kind"] == "DECISION":
        question = questions[0]
        required = set(question["required_detail_for"])
        lines = ["Reply with one of:"]
        for choice in ("A", "B", "C"):
            example = choice
            if choice in required:
                example += ": <required detail>"
            lines.extend(("", f"- `{example}`"))
        return lines
    return ["Reply in your own words—no prefix is needed."]


def _render_intake_card(
    report: Mapping[str, Any],
    card: Mapping[str, Any],
    *,
    updated: str,
) -> str:
    lines = [
        "FASTLANE \u00b7 DEFINE",
        "",
        "Status: 1 question remains before requirements analysis.",
        f"Updated: {updated}",
    ]
    objective, fields, prompt = _intake_consultation(report, card)
    if objective:
        lines.extend(("", "Why this matters", "", objective))
    current_understanding = _intake_current_understanding(report)
    if current_understanding:
        lines.extend(("", "What Fastlane already knows", ""))
        lines.extend(f"- {item}" for item in current_understanding)
    lines.extend(("", "Need from you: Answer this remaining question."))
    lines.extend(_intake_question_lines(card, prompt=prompt))
    if fields:
        lines.extend(
            ("", "What your answer changes", "", _intake_project_effect(fields))
        )
    lines.extend(
        (
            "",
            "Next: Codex will record only your confirmed answers, validate them, "
            "and continue definition.",
        )
    )
    if card["accept_all_allowed"]:
        lines.append("You may also reply `Accept all recommendations.`")
    lines.extend(("", *_intake_reply_guidance(card)))
    return "\n".join(lines)


def _owner_project_setting(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 160
        or any(character in value for character in "\r\n`{}")
    ):
        raise PresentationError(f"project-ready {label} is invalid")
    return value


def _owner_cost_posture(value: Any) -> str:
    posture = _owner_project_setting(value, "cost posture")
    if posture == "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED":
        return "Minimize total development cost; no hard cap stated."
    match = re.fullmatch(
        r"MINIMIZE_TOTAL_COST; HARD_CAP: ([A-Z]{3}) ([0-9]+(?:\.[0-9]{1,2})?)",
        posture,
    )
    if match is None:
        raise PresentationError("project-ready cost posture is not canonical")
    return (
        f"Minimize total development cost; hard cap {match.group(1)} {match.group(2)}."
    )


def render_project_ready(report: Mapping[str, Any]) -> str:
    """Render the one post-initialization handoff before ordinary resume mode."""

    interaction = _interaction(report)
    if (
        interaction.get("owner_stage") != "DEFINE"
        or interaction.get("response_mode") != "OWNER_UPDATE"
        or interaction.get("state") != "NEEDS_INPUT"
        or interaction.get("route_reason_code") != "INTAKE_REQUIRED"
        or interaction.get("owner_action_kind") != "ANSWER_OPEN_DECISIONS"
        or interaction.get("owner_action_required") is not True
        or interaction.get("automatic_continuation_allowed") is not False
        or interaction.get("formal_receipt_required") is not False
        or interaction.get("turn_boundary_required") is not True
        or interaction.get("blocking_ids") != []
    ):
        raise PresentationError("project-ready requires the first Define owner action")
    project = report.get("project")
    authorizations = report.get("authorizations")
    if not isinstance(project, Mapping) or authorizations != {
        "construction": "NONE",
        "aws": "NONE",
    }:
        raise PresentationError("project-ready cannot imply current authority")
    name = _owner_project_setting(project.get("name"), "project name")
    region = _owner_project_setting(project.get("region"), "Region")
    cost = _owner_cost_posture(project.get("cost_posture"))
    card = _pending_intake_card(report)
    if (
        card is None
        or card.get("card_id") != "INTAKE-CARD-0001"
        or card.get("revision") != 1
    ):
        raise PresentationError("project-ready requires the first current intake card")
    objective, fields, prompt = _intake_consultation(report, card)
    if fields != ("OWNER_WORK_CONTEXT",) or _intake_current_understanding(report):
        raise PresentationError(
            "project-ready is available only immediately after initialization"
        )
    lines = [
        "FASTLANE · PROJECT READY",
        "",
        f"{name} is initialized and ready for product definition.",
        "",
        "Project settings",
        "",
        f"- Preferred AWS Region: `{region}`",
        f"- Development cost posture: {cost}",
        "- AWS account access: Not authorized.",
        "",
        "How consultation works",
        "",
        "Fastlane asks one consequential project question at a time. Codex explains "
        "why it matters, recommends an option only when current evidence supports "
        "one, and confirms what changed after each answer.",
        "",
        "You can ask for an explanation or correct an earlier answer at any time. "
        "Fastlane handles its internal planning configuration automatically.",
        "",
        "Need from you: Answer the first project question.",
        "",
        "Why this matters",
        "",
        objective,
    ]
    lines.extend(_intake_question_lines(card, prompt=prompt))
    lines.extend(
        (
            "",
            "What your answer changes",
            "",
            _intake_project_effect(fields),
            "",
            "Next: Codex will record only your confirmed answer, validate it, and "
            "continue the guided consultation.",
            "",
            *_intake_reply_guidance(card),
        )
    )
    return "\n".join(lines)


def _current_diagram_kinds(report: Mapping[str, Any]) -> set[str]:
    """Return only diagram views that the evaluated project says are current."""

    design = report.get("design_contract")
    diagram = design.get("diagram_contract") if isinstance(design, Mapping) else None
    records = diagram.get("records") if isinstance(diagram, Mapping) else None
    if not isinstance(records, list):
        return set()
    return {
        str(record.get("kind"))
        for record in records
        if isinstance(record, Mapping) and record.get("status") == "CURRENT"
    }


def _post_gate_navigation(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> tuple[str, ...]:
    """Return links only for the first automatic continuation after a gate."""

    if interaction.get("automatic_continuation_allowed") is not True:
        return ()
    gates = report.get("gates")
    if not isinstance(gates, Mapping):
        return ()
    next_prompt = str(report.get("next_prompt", ""))
    if (
        next_prompt == "DESIGN-10"
        and gates.get("gate_a") == "APPROVED_FOR_DESIGN"
        and gates.get("gate_b") != "APPROVED_FOR_CONSTRUCTION"
    ):
        return (
            "- [Gate A decision](docs/project/PRD.md#gate-a-review)",
            "- [Technical Plan](docs/project/PRD.md#technical-plan)",
        )
    if next_prompt == "TASK-10" and gates.get("gate_b") == "APPROVED_FOR_CONSTRUCTION":
        current_diagrams = _current_diagram_kinds(report)
        links = [
            "- [Gate B decision](docs/project/PRD.md#gate-b-review)",
        ]
        if "SYSTEM_CONTEXT" in current_diagrams:
            links.append(
                "- [View the complete proposed architecture]"
                "(docs/project/PRD.md#proposed-system-at-a-glance)"
            )
        if "AWS_IMPLEMENTATION" in current_diagrams:
            links.extend(
                (
                    "- [View the AWS implementation diagram]"
                    "(docs/project/PRD.md#aws-implementation-at-a-glance)",
                    "- [Browse all project diagrams](docs/project/PRD.md#diagram-guide)",
                )
            )
        links.append(
            "- [Current construction progress](docs/project/TASKS.md#current-progress)"
        )
        return tuple(links)
    return ()


def render_owner_update(
    report: Mapping[str, Any],
    *,
    updated: str = "Nothing.",
) -> str:
    """Render one concise non-receipt lifecycle update."""

    interaction = _interaction(report)
    if interaction.get("formal_receipt_required") is True:
        raise PresentationError(
            "formal gate and AWS receipts use canonical receipt renderers"
        )
    stage = str(interaction.get("owner_stage", ""))
    if stage not in {"DEFINE", "DESIGN", "DELIVER"}:
        raise PresentationError("invalid owner stage")
    reason = str(interaction.get("route_reason_code", ""))
    action_kind = str(interaction.get("owner_action_kind", ""))
    if reason not in STATUS_TEXT or reason not in NEXT_TEXT:
        raise PresentationError("unknown route reason code")
    if action_kind not in ACTION_TEXT:
        raise PresentationError("unknown owner action kind")
    _validate_aws_progress_interaction(report, interaction)
    required = interaction.get("owner_action_required") is True
    if required == (action_kind == "NONE_CONTINUE_AUTOMATICALLY"):
        raise PresentationError("owner action requirement conflicts with action kind")
    boundary = interaction.get("turn_boundary_required")
    expected_boundary = (
        required and interaction.get("automatic_continuation_allowed") is not True
    )
    if boundary is not None and boundary is not expected_boundary:
        raise PresentationError("owner turn boundary conflicts with interaction state")
    if action_kind == "ANSWER_OPEN_DECISIONS":
        card = _pending_intake_card(report)
        if card is not None:
            return _render_intake_card(report, card, updated=updated)

    remediation_status, remediation_next = _remediation_text(report)
    status_text = (
        remediation_status or _delivery_status(report, reason) or STATUS_TEXT[reason]
    )
    next_text = (
        remediation_next
        or _delivery_next(report, reason)
        or _coverage_next(report, reason)
        or NEXT_TEXT[reason]
    )
    ready_copy = _aws_ready_owner_copy(report, reason)
    if ready_copy is not None:
        status_text, next_text = ready_copy
    if (
        reason == "WAITING_AWS_MUTATION_AUTH"
        and action_kind == "NONE_CONTINUE_AUTOMATICALLY"
    ):
        status_text = "Read-only AWS preflight and the exact deployment authorization are current."
        next_text = "Codex will perform only the exact authorized AWS mutation."
    if (
        reason == "WAITING_AWS_TEARDOWN_AUTH"
        and action_kind == "NONE_CONTINUE_AUTOMATICALLY"
    ):
        status_text = (
            "Read-only residual review and the exact teardown authorization are "
            "current."
        )
        next_text = (
            "Codex will remove only the exact resources authorized for teardown."
        )
    if reason == "AWS_RESIDUAL_REVIEW_BLOCKED":
        blocker = _teardown_blocker_reason(report)
        status_text = f"Read-only AWS residual review stopped: {blocker}"

    lines = [
        f"FASTLANE · {stage}",
        "",
        f"Status: {status_text}",
        f"Updated: {updated}",
        f"Need from you: {ACTION_TEXT[action_kind]}",
        f"Next: {next_text}",
    ]
    audit = _aws_core_audit(report, interaction)
    deployment_audit = _aws_deployment_audit(report, interaction)
    preflight_audit = _aws_preflight_audit(report, interaction)
    closure_audit = _deployment_closure_audit(report)
    teardown_closure_audit = _teardown_closure_audit(report)
    lifecycle_intent_audit = _aws_lifecycle_intent_audit(report, interaction)
    audit_parts = [
        item
        for item in (
            audit,
            deployment_audit,
            preflight_audit,
            closure_audit,
            teardown_closure_audit,
            lifecycle_intent_audit,
        )
        if item is not None
    ]
    if audit_parts:
        lines.append("Audit: " + " ".join(audit_parts))
    navigation = _post_gate_navigation(report, interaction)
    if navigation:
        lines.extend(("", "Continue in:", *navigation))
    reply = COPYABLE_REPLIES.get(action_kind)
    if required and reply:
        lines.extend(("", "Copyable reply:", reply))
    return "\n".join(lines)


def render_architecture_board_offer(
    report: Mapping[str, Any],
    handoff: Mapping[str, Any],
    skill_identity: Mapping[str, Any],
    transition: str,
) -> str:
    interaction = _interaction(report)
    if (
        transition != "GATE_B_ACCEPTED"
        or report.get("next_prompt") != "TASK-10"
        or interaction.get("route_reason_code") != "TASK_PLAN_REQUIRED"
        or interaction.get("owner_action_required") is not False
        or interaction.get("automatic_continuation_allowed") is not True
    ):
        raise PresentationError("architecture-board offer requires Gate B continuation")
    base = render_owner_update(report, updated="Gate B was accepted.")
    identity = {**ARCHITECTURE_DIAGRAM_SKILL_IDENTITY, "valid": True, "issues": []}
    if dict(skill_identity) != identity or handoff.get("eligible") is not True:
        return base
    if (
        handoff.get("status") != "ELIGIBLE"
        or handoff.get("issues") != []
        or (handoff.get("aws_authority"), handoff.get("external_authority"))
        != ("NONE", "NONE")
        or not all(
            isinstance(handoff.get(key), Mapping) for key in ("source", "cross_check")
        )
        or handoff.get("source", {}).get("diagram_id") != "DIAGRAM-0001"
        or handoff.get("cross_check", {}).get("diagram_id") != "DIAGRAM-0008"
        or re.fullmatch(
            r"dist/architecture/DES-\d{4,}-[0-9a-f]{64}",
            str(handoff.get("output_root", "")),
        )
        is None
    ):
        raise PresentationError("architecture-board handoff is malformed")
    return base + (
        "\n\nOptional planned architecture board\n\n"
        "Would you like Fastlane to compile a professional AWS architecture board "
        "from the approved Mermaid design?\n"
        "Optional reply: `Generate the planned AWS architecture board.`\n"
        "Fastlane will continue TASK-10 either way. This creates local planned-design "
        "files only; it does not inspect credentials, access AWS, or authorize deployment."
    )


def render_side_question_response(
    report: Mapping[str, Any],
    *,
    answer: str,
    project_state_changed: bool = False,
) -> str:
    """Answer directly, then restore the current deterministic owner action."""

    cleaned_answer = answer.strip()
    if not cleaned_answer:
        raise PresentationError("side-question answer must not be empty")
    interaction = _interaction(report)
    _validate_aws_progress_interaction(report, interaction)
    _remediation_status, remediation_next = _remediation_text(report)
    action_kind = str(interaction.get("owner_action_kind", ""))
    if action_kind not in ACTION_TEXT:
        raise PresentationError("unknown owner action kind")
    required = interaction.get("owner_action_required") is True
    if required == (action_kind == "NONE_CONTINUE_AUTOMATICALLY"):
        raise PresentationError("owner action requirement conflicts with action kind")
    lines = [
        cleaned_answer,
        "",
        "Project state changed: " + ("Yes." if project_state_changed else "No."),
    ]
    current_understanding = _intake_current_understanding(report)
    if current_understanding:
        lines.append("Current understanding:")
        lines.extend(f"- {item}" for item in current_understanding)
    pending_action = ACTION_TEXT[action_kind]
    if required and action_kind == "ANSWER_OPEN_DECISIONS":
        card = _pending_intake_card(report)
        if card is not None:
            count = len(card["questions"])
            pending_action = (
                "Answer the remaining project question."
                if count == 1
                else f"Answer the {count} remaining project questions."
            )
    lines.append(f"Pending next action: {pending_action}")
    reason = str(interaction.get("route_reason_code", ""))
    lifecycle_intent_audit = _aws_lifecycle_intent_audit(report, interaction)
    if reason == "AWS_RESIDUAL_REVIEW_BLOCKED":
        lines.append(f"Safety blocker: {_teardown_blocker_reason(report)}")
    if required and action_kind == "ANSWER_OPEN_DECISIONS":
        card = _pending_intake_card(report)
        if card is not None:
            _objective, _fields, prompt = _intake_consultation(report, card)
            lines.extend(("", "The pending questions are unchanged:"))
            lines.extend(_intake_question_lines(card, prompt=prompt))
            if card["accept_all_allowed"]:
                lines.append("You may also reply `Accept all recommendations.`")
            lines.extend(("", *_intake_reply_guidance(card)))
    if required and action_kind == "CHOOSE_AWS_RESIDUAL_DISPOSITION":
        lines.extend(("", "Copyable reply:", COPYABLE_REPLIES[action_kind]))
    if not required:
        if reason not in NEXT_TEXT:
            raise PresentationError("unknown route reason code")
        next_text = remediation_next or NEXT_TEXT[reason]
        ready_copy = _aws_ready_owner_copy(report, reason)
        if ready_copy is not None:
            _status_text, next_text = ready_copy
        elif (
            reason == "WAITING_AWS_MUTATION_AUTH"
            and action_kind == "NONE_CONTINUE_AUTOMATICALLY"
        ):
            next_text = "Codex will perform only the exact authorized AWS mutation."
        elif (
            reason == "WAITING_AWS_TEARDOWN_AUTH"
            and action_kind == "NONE_CONTINUE_AUTOMATICALLY"
        ):
            next_text = (
                "Codex will remove only the exact resources authorized for teardown."
            )
        lines.append(f"Next: {next_text}")
    if lifecycle_intent_audit is not None:
        lines.append(f"Audit: {lifecycle_intent_audit}")
    return "\n".join(lines)


def render_prerequisite_update(report: Mapping[str, Any]) -> str:
    """Render one prerequisite action with one consolidated owner checklist."""

    state = str(report.get("state", ""))
    if state == "PREREQUISITES_READY":
        raise PresentationError("ready prerequisites route to the welcome renderer")
    checklist = report.get("checklist")
    if not isinstance(checklist, Sequence) or isinstance(checklist, (str, bytes)):
        raise PresentationError("prerequisite report is missing its checklist")
    steps = [item for item in checklist if isinstance(item, Mapping)]
    if not steps:
        raise PresentationError(
            "blocked prerequisites require at least one checklist step"
        )
    lines = [
        "FASTLANE · PREREQUISITES",
        "",
        "Status: Required local setup is incomplete.",
        "Updated: Nothing.",
        "Need from you: Complete the checklist below, then send `init template` again.",
        "Next: Codex will verify everything together before asking project questions.",
        "",
        "Checklist:",
    ]
    for index, step in enumerate(steps, start=1):
        label = str(step.get("label", "Required step"))
        lines.append(f"{index}. {label}")
        grouped = any(
            key in step
            for key in (
                "install_commands",
                "action_commands",
                "verification_commands",
            )
        )
        if grouped:
            for heading, key in (
                ("Owner-run install", "install_commands"),
                ("Owner action", "action_commands"),
                ("Verify", "verification_commands"),
            ):
                commands = step.get(key, [])
                if isinstance(commands, Sequence) and not isinstance(
                    commands, (str, bytes)
                ):
                    for command in commands:
                        lines.append(f"   {heading}: `{command}`")
        else:
            commands = step.get("commands", [])
            if isinstance(commands, Sequence) and not isinstance(
                commands, (str, bytes)
            ):
                for command in commands:
                    lines.append(f"   `{command}`")
        guide = step.get("guide")
        if guide:
            lines.append(f"   Official guide: {guide}")
        instruction = step.get("instruction")
        if instruction:
            lines.append(f"   {instruction}")
    return "\n".join(lines)


OWNER_MATURITY_LABELS = {
    "CONFIRMED_BY_OWNER": "Confirmed by you",
    "OBSERVED_IN_REPOSITORY": "Observed in the repository",
    "SOURCE_VERIFIED": "Verified from current sources",
    "LOCALLY_OBSERVED": "Observed in local validation",
    "AWS_READ_OBSERVED": "Observed through authorized AWS read access",
    "DEPLOYED_OBSERVED": "Observed after deployment",
    "RECOVERY_OBSERVED": "Observed during recovery",
    "PLANNED_AFTER_APPROVAL": "Planned after approval",
    "NOT_YET_OBSERVED": "Not yet observed",
    "NOT_AUTHORIZED": "Not authorized",
}


def _canonical_projection_digest(projection: Mapping[str, Any]) -> str:
    canonical = dict(projection)
    canonical.pop("canonical_sha256", None)
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
    )


def _validated_owner_decision_brief(
    report: Mapping[str, Any], expected_kind: str
) -> Mapping[str, Any]:
    brief = report.get("owner_decision_brief")
    if not isinstance(brief, Mapping):
        raise PresentationError(
            "Fastlane Engine report is missing the Owner Decision Brief"
        )
    finalized, validation_issues = finalize_owner_decision_brief(dict(brief))
    if validation_issues or finalized.get("canonical_sha256") != brief.get(
        "canonical_sha256"
    ):
        raise PresentationError(
            "Owner Decision Brief does not satisfy the canonical derived contract or digest"
        )
    if brief.get("schema_version") != 1 or brief.get("kind") != expected_kind:
        raise PresentationError(
            "Owner Decision Brief kind does not match the requested gate"
        )
    if brief.get("status") not in {"BUILDING", "READY", "STALE", "BLOCKED"}:
        raise PresentationError("Owner Decision Brief has an invalid status")
    digest = brief.get("canonical_sha256")
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        or digest != _canonical_projection_digest(brief)
    ):
        raise PresentationError(
            "Owner Decision Brief digest does not match its content"
        )
    sections = brief.get("executive_sections")
    if (
        not isinstance(sections, Sequence)
        or isinstance(sections, (str, bytes))
        or not sections
    ):
        raise PresentationError(
            "Owner Decision Brief has no executive decision sections"
        )
    for section in sections:
        if not isinstance(section, Mapping) or any(
            not isinstance(section.get(field), str) or not section.get(field)
            for field in ("section_id", "title")
        ):
            raise PresentationError("Owner Decision Brief contains an invalid section")
        items = section.get("items")
        if (
            not isinstance(items, Sequence)
            or isinstance(items, (str, bytes))
            or not items
            or any(not isinstance(item, str) or not item for item in items)
        ):
            raise PresentationError("Owner Decision Brief section content is invalid")
    groups = brief.get("technical_decision_groups")
    if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)):
        raise PresentationError("Owner Decision Brief decision index is invalid")
    if expected_kind == "GATE_B" and brief.get("status") == "READY" and not groups:
        raise PresentationError("Ready Gate B brief has no technical decision index")
    for group in groups:
        if not isinstance(group, Mapping) or not isinstance(group.get("domain"), str):
            raise PresentationError(
                "Owner Decision Brief contains an invalid decision group"
            )
        decisions = group.get("decisions")
        if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes)):
            raise PresentationError(
                "Owner Decision Brief contains an invalid decision list"
            )
        for decision in decisions:
            if not isinstance(decision, Mapping) or any(
                not isinstance(decision.get(field), str) or not decision.get(field)
                for field in (
                    "decision_id",
                    "decision",
                    "owner_effect",
                    "selection",
                    "requirement_basis",
                    "why",
                    "alternatives",
                    "tradeoff",
                    "risk_and_mitigation",
                    "evidence_status",
                    "reconsider_when",
                )
            ):
                raise PresentationError(
                    "Owner Decision Brief contains an incomplete technical decision"
                )
    claims = brief.get("claims")
    if not isinstance(claims, Sequence) or isinstance(claims, (str, bytes)):
        raise PresentationError("Owner Decision Brief claims are invalid")
    for claim in claims:
        if (
            not isinstance(claim, Mapping)
            or claim.get("maturity") not in OWNER_MATURITY_LABELS
            or not isinstance(claim.get("text"), str)
            or not claim.get("text")
        ):
            raise PresentationError("Owner Decision Brief claim is invalid")
    locators = brief.get("source_locators")
    if not isinstance(locators, Sequence) or isinstance(locators, (str, bytes)):
        raise PresentationError("Owner Decision Brief source locations are invalid")
    for locator in locators:
        if not isinstance(locator, Mapping) or any(
            not isinstance(locator.get(field), expected)
            for field, expected in (
                ("key", str),
                ("label", str),
                ("path", str),
                ("heading", str),
                ("start_line", int),
                ("end_line", int),
                ("section_sha256", str),
                ("required", bool),
            )
        ):
            raise PresentationError("Owner Decision Brief source location is invalid")
        path = str(locator["path"])
        if (
            path.startswith(("/", "\\"))
            or "\\" in path
            or ".." in path.split("/")
            or re.match(r"^[A-Za-z]:", path)
        ):
            raise PresentationError(
                "Owner Decision Brief source location is not repository-relative"
            )
    authorization = brief.get("authorization_effect")
    if not isinstance(authorization, Mapping):
        raise PresentationError("Owner Decision Brief approval boundary is missing")
    for field in ("approves", "does_not_approve"):
        values = authorization.get(field)
        if (
            not isinstance(values, Sequence)
            or isinstance(values, (str, bytes))
            or not values
            or any(not isinstance(value, str) or not value for value in values)
        ):
            raise PresentationError("Owner Decision Brief approval boundary is invalid")
    if brief.get("formal_receipt_required") is not (brief.get("status") == "READY"):
        raise PresentationError(
            "Owner Decision Brief receipt state conflicts with readiness"
        )
    return brief


def _validated_owner_decision_inventory(
    report: Mapping[str, Any], expected_kind: str
) -> Mapping[str, Any]:
    inventory = report.get("owner_decision_inventory")
    if not isinstance(inventory, Mapping):
        raise PresentationError(
            "Fastlane Engine report is missing the owner decision inventory"
        )
    finalized, issues = finalize_owner_decision_inventory(dict(inventory))
    if issues or finalized.get("canonical_sha256") != inventory.get("canonical_sha256"):
        raise PresentationError(
            "Owner decision inventory does not satisfy its derived contract"
        )
    if inventory.get("schema_version") != 1 or inventory.get("kind") != expected_kind:
        raise PresentationError(
            "Owner decision inventory kind does not match the requested gate"
        )
    if inventory.get("status") not in {"BUILDING", "READY", "STALE", "BLOCKED"}:
        raise PresentationError("Owner decision inventory has an invalid status")
    return inventory


def _markdown_table_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _decision_source_links(
    decision: Mapping[str, Any], locator_by_key: Mapping[str, Mapping[str, Any]]
) -> str:
    sources: list[str] = []
    for key in decision["source_locator_keys"]:
        locator = locator_by_key[str(key)]
        anchor = _markdown_anchor(str(locator["heading"]))
        sources.append(f"[{locator['label']}]({locator['path']}#{anchor})")
    return ", ".join(sources)


def _markdown_anchor(heading: str) -> str:
    value = re.sub(r"[^\w -]", "", heading.lower(), flags=re.UNICODE)
    return re.sub(r"[\s-]+", "-", value).strip("-")


def _owner_source_link(
    locator_by_key: Mapping[str, Mapping[str, Any]],
    key: str,
    *,
    link_label: str | None = None,
) -> str:
    """Return one required content-bound owner-navigation link."""

    locator = locator_by_key.get(key)
    if locator is None:
        raise PresentationError(f"Owner brief is missing required source {key}")
    path = locator.get("path")
    heading = locator.get("heading")
    label = locator.get("label")
    if not all(isinstance(value, str) and value for value in (path, heading, label)):
        raise PresentationError(f"Owner brief source {key} is malformed")
    return f"[{link_label or label}]({path}#{_markdown_anchor(heading)})"


def render_owner_decision_brief(report: Mapping[str, Any], expected_kind: str) -> str:
    """Render one deterministic Gate A or Gate B owner decision view."""

    brief = _validated_owner_decision_brief(report, expected_kind)
    inventory = _validated_owner_decision_inventory(report, expected_kind)
    stage = "DEFINE" if expected_kind == "GATE_A" else "DESIGN"
    name = (
        "Gate A Owner Decision Brief"
        if expected_kind == "GATE_A"
        else "Gate B Technical Owner Decision Brief"
    )
    status_copy = {
        "BUILDING": "This decision brief is still being prepared.",
        "READY": "This decision brief is ready for your review.",
        "STALE": "This decision brief changed and must be refreshed before approval.",
        "BLOCKED": "Validation found an issue that must be resolved before approval.",
    }[str(brief["status"])]
    lines = [f"FASTLANE · {stage}", "", name, "", f"Status: {status_copy}"]
    for section in brief["executive_sections"]:
        lines.extend(("", f"## {section['title']}"))
        lines.extend(f"- {item}" for item in section["items"])

    inventory_decisions = inventory["decisions"]
    locator_by_key = {
        str(locator["key"]): locator for locator in brief["source_locators"]
    }
    if expected_kind == "GATE_A":
        lines.extend(
            (
                "",
                "## Your recorded decisions",
                "",
                "| Decision | Recorded answer | Source | Status |",
                "|---|---|---|---|",
            )
        )
        for decision in inventory_decisions:
            lines.append(
                "| "
                + " | ".join(
                    _markdown_table_cell(value)
                    for value in (
                        decision["title"],
                        decision["selection"],
                        (
                            f"{decision['source']} — "
                            f"{_decision_source_links(decision, locator_by_key)}"
                        ),
                        OWNER_MATURITY_LABELS[str(decision["maturity"])],
                    )
                )
                + " |"
            )

    groups = brief["technical_decision_groups"]
    if groups:
        brief_ids = [
            decision["decision_id"]
            for group in groups
            for decision in group["decisions"]
        ]
        inventory_ids = [decision["decision_id"] for decision in inventory_decisions]
        if brief_ids != inventory_ids:
            raise PresentationError(
                "Gate B brief does not match the complete decision inventory"
            )
        lines.extend(
            (
                "",
                "## Technical decision index",
                "",
                "| Domain | Decision | Selected approach |",
                "|---|---|---|",
            )
        )
        for group in groups:
            for decision in group["decisions"]:
                lines.append(
                    "| "
                    + " | ".join(
                        _markdown_table_cell(value)
                        for value in (
                            str(group["domain"]).replace("/", " and ").title(),
                            decision["decision"],
                            decision["selection"],
                        )
                    )
                    + " |"
                )
        architecture_links = [
            _owner_source_link(
                locator_by_key,
                key,
                link_label=label,
            )
            for key, label in zip(
                GATE_B_NAVIGATION_LOCATOR_KEYS,
                (
                    "View the complete proposed architecture",
                    "View the AWS implementation diagram",
                    "Browse all project diagrams",
                ),
            )
        ]
        lines.extend(
            (
                "",
                "## Architecture diagrams",
                "",
                f"- {architecture_links[0]}",
                f"- {architecture_links[1]}",
                f"- {architecture_links[2]}",
            )
        )
        lines.extend(
            (
                "",
                "<details>",
                "<summary>Decision reasoning, tradeoffs, risks, and sources</summary>",
                "",
            )
        )
        for group in groups:
            for decision in group["decisions"]:
                sources = _decision_source_links(decision, locator_by_key)
                lines.extend(
                    (
                        f"### {decision['decision']} ({decision['decision_id']})",
                        (
                            f"- Meaning and selection: {decision['owner_effect']} "
                            f"Selected: {decision['selection']}"
                        ),
                        (
                            f"- Basis and rationale: {decision['requirement_basis']}. "
                            f"{decision['why']}"
                        ),
                        (
                            "- Alternatives and tradeoffs: "
                            f"{decision['alternatives']} Tradeoffs: {decision['tradeoff']}"
                        ),
                        (f"- Risks and safeguards: {decision['risk_and_mitigation']}"),
                        (
                            f"- Evidence and revisit trigger: {decision['evidence_status']} "
                            f"Reconsider when: {decision['reconsider_when']}"
                        ),
                        f"- Exact source: {sources}",
                    )
                )
        lines.extend(("", "</details>"))

    lines.extend(("", "## Evidence and authorization"))
    for claim in brief["claims"]:
        lines.append(
            f"- {OWNER_MATURITY_LABELS[str(claim['maturity'])]}: {claim['text']}"
        )
    lines.extend(("", "## Approval boundary", "", "This approval covers:"))
    lines.extend(f"- {item}" for item in brief["authorization_effect"]["approves"])
    lines.extend(("", "This approval does not cover:"))
    lines.extend(
        f"- {item}" for item in brief["authorization_effect"]["does_not_approve"]
    )

    lines.extend(("", "## Correct or approve"))
    if expected_kind == "GATE_A":
        lines.extend(
            (
                "- To correct anything, reply `Change the requirements: <correction>.`",
                (
                    "- After approval, Codex continues automatically into "
                    "AWS Core-informed technical design."
                ),
            )
        )
    else:
        lines.extend(
            (
                "- To correct anything, reply `Change the design: <correction>.`",
                (
                    "- After approval, Codex generates the task plan and begins "
                    "bounded local construction automatically."
                ),
            )
        )

    lines.extend(("", "## Review the exact sources"))
    for locator in brief["source_locators"]:
        if locator["key"] in GATE_B_NAVIGATION_LOCATOR_KEYS:
            continue
        anchor = _markdown_anchor(str(locator["heading"]))
        lines.append(
            f"- [{locator['label']}]({locator['path']}#{anchor}) "
            f"(lines {locator['start_line']}–{locator['end_line']})"
        )
    lines.extend(
        (
            "",
            (
                "Next: Review the exact approval receipt shown after this brief."
                if brief["status"] == "READY"
                else "Next: Codex will resolve the reported issue and refresh this brief."
            ),
        )
    )
    return "\n".join(lines)


def _validated_answer_confirmation(
    report: Mapping[str, Any], owner_response_id: str
) -> Mapping[str, Any]:
    confirmation = report.get("owner_answer_confirmation")
    if not isinstance(confirmation, Mapping):
        raise PresentationError("Fastlane Engine report is missing Answer Confirmation")
    if confirmation.get("schema_version") != 1:
        raise PresentationError("Answer Confirmation schema is unsupported")
    if confirmation.get("status") != "READY":
        raise PresentationError("No validated owner answer is ready to confirm")
    if confirmation.get("owner_response_id") != owner_response_id:
        raise PresentationError(
            "Answer Confirmation does not match the current owner response"
        )
    digest = confirmation.get("canonical_sha256")
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        or digest != _canonical_projection_digest(confirmation)
    ):
        raise PresentationError("Answer Confirmation digest does not match its content")
    binding = confirmation.get("card_binding")
    if (
        not isinstance(binding, Mapping)
        or not isinstance(binding.get("card_id"), str)
        or not isinstance(binding.get("revision"), int)
        or not isinstance(binding.get("presented_sha256"), str)
    ):
        raise PresentationError("Answer Confirmation card binding is invalid")
    recorded = confirmation.get("recorded")
    if (
        not isinstance(recorded, Sequence)
        or isinstance(recorded, (str, bytes))
        or not recorded
        or any(not isinstance(item, str) or not item for item in recorded)
    ):
        raise PresentationError("Answer Confirmation has no recorded value")
    for field in ("project_effect", "correction_prompt"):
        if not isinstance(confirmation.get(field), str) or not confirmation.get(field):
            raise PresentationError(f"Answer Confirmation {field} is missing")
    return confirmation


def render_answer_confirmation(
    report: Mapping[str, Any], owner_response_id: str
) -> str:
    """Render a confirmation only for the matching newly processed owner turn."""

    confirmation = _validated_answer_confirmation(report, owner_response_id)
    lines = ["FASTLANE · DEFINE", ""]
    for item in confirmation["recorded"]:
        lines.append(f"Recorded: {item}")
    lines.extend(
        (
            "",
            f"Project effect: {confirmation['project_effect']}",
            "",
            f"Correct it: Say `{confirmation['correction_prompt']}`",
            "",
            "Next: Codex will continue with the next unanswered project decision.",
        )
    )
    return "\n".join(lines)


def _source_brief_sequence(preview: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = preview.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PresentationError(f"source-assisted Define {key} is invalid")
    return value


def _source_brief_summary_lines(items: Sequence[Any], kind: str) -> list[str]:
    lines: list[str] = []
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("summary"), str):
            raise PresentationError(f"source-assisted Define {kind} is invalid")
        lines.append(f"- {item['summary']}")
    return lines


def _source_brief_choice_lines(confirmation: Mapping[str, Any]) -> list[str]:
    options = _source_brief_sequence(confirmation, "options")
    keys = [option.get("key") for option in options if isinstance(option, Mapping)]
    if keys != ["A", "B", "C"]:
        raise PresentationError("source-assisted Define choices must be A, B, and C")
    lines: list[str] = []
    for option in options:
        if not isinstance(option, Mapping):
            raise PresentationError("source-assisted Define choice is invalid")
        label, effect = option.get("label"), option.get("effect")
        if not isinstance(label, str) or not isinstance(effect, str):
            raise PresentationError("source-assisted Define choice text is invalid")
        prefix = f"{option['key']}."
        if option.get("recommended") is True:
            prefix += " Recommended —"
        lines.extend((f"**{prefix} {label}**", "", effect, ""))
    lines.append("Reply with A, B, or C—or answer in your own words.")
    return lines


def _render_blocked_source_brief(preview: Mapping[str, Any]) -> str:
    issues = _source_brief_sequence(preview, "issues")
    if not issues or not isinstance(issues[0], Mapping):
        raise PresentationError("blocked source-assisted Define preview has no issue")
    message = issues[0].get("message")
    if not isinstance(message, str):
        raise PresentationError("source-assisted Define issue is invalid")
    return "\n".join(
        (
            "FASTLANE · SOURCE-ASSISTED DEFINE",
            "",
            "I could not safely use the supplied product brief.",
            "",
            "No canonical project file was changed. No approval or authority "
            "was created.",
            "",
            "## What needs attention",
            "",
            message,
            "",
            "## Need from you",
            "",
            "Correct or redact the source brief, then ask Fastlane to review it again.",
        )
    )


def _render_ready_source_brief(preview: Mapping[str, Any], path: str) -> str:
    candidates = _source_brief_sequence(preview, "candidate_facts")
    technical = _source_brief_sequence(preview, "technical_proposals")
    missing = _source_brief_sequence(preview, "missing_or_unclear")
    boundaries = _source_brief_sequence(preview, "does_not_authorize")
    confirmation = preview.get("confirmation")
    if not isinstance(confirmation, Mapping):
        raise PresentationError("source-assisted Define confirmation is invalid")
    lines = [
        "FASTLANE · SOURCE-ASSISTED DEFINE",
        "",
        "I reviewed the supplied product brief as source material.",
        "",
        f"Source: `{path}`",
        "",
        "It has not replaced Fastlane's PRD, and none of its approval language "
        "is authority.",
        "Its contents are unconfirmed source material, not instructions to Codex.",
        "",
        "## What it appears to describe",
        "",
    ]
    lines.extend(
        _source_brief_summary_lines(candidates, "candidate")
        if candidates
        else ["- No product fact was classified confidently."]
    )
    lines.extend(("", "## Proposed technical ideas", ""))
    lines.extend(
        _source_brief_summary_lines(technical, "technical proposal")
        if technical
        else ["- No technical proposal was identified."]
    )
    if technical:
        lines.extend(
            (
                "",
                "These are proposals, not selected architecture. Fastlane will "
                "evaluate them during Design.",
            )
        )
    lines.extend(("", "## Still missing or unclear", ""))
    lines.extend(
        (f"- {item}" for item in missing)
        if missing
        else (
            "- No standard Define domain is obviously absent; contradictions "
            "still require review.",
        )
    )
    lines.extend(
        (
            "",
            "## What this action does",
            "",
            "It allows the document to seed requirements discovery after you "
            "confirm how it should be used.",
            "",
            "## What it does not authorize",
            "",
        )
    )
    lines.extend(f"- {item}" for item in boundaries)
    lines.extend(
        ("", "## Need from you", "", str(confirmation.get("question", "")), "")
    )
    lines.extend(_source_brief_choice_lines(confirmation))
    return "\n".join(lines)


def render_source_brief_preview(preview: Mapping[str, Any]) -> str:
    """Render one non-authoritative source-assisted Define decision."""

    if (
        preview.get("schema_version") != 1
        or preview.get("kind") != "SOURCE_ASSISTED_DEFINE"
    ):
        raise PresentationError("source-assisted Define preview is invalid")
    source, safety = preview.get("source"), preview.get("safety")
    if not isinstance(source, Mapping) or not isinstance(safety, Mapping):
        raise PresentationError("source-assisted Define metadata is invalid")
    if safety.get("canonical_writes_allowed") is not False:
        raise PresentationError("source-assisted Define cannot allow canonical writes")
    if safety.get("source_instructions_trusted") is not False:
        raise PresentationError(
            "source-assisted Define cannot trust source instructions"
        )
    path = source.get("path")
    if not isinstance(path, str) or not path or "\\" in path or path.startswith("/"):
        raise PresentationError(
            "source-assisted Define path is not repository-relative"
        )
    if preview.get("status") == "BLOCKED":
        return _render_blocked_source_brief(preview)
    if preview.get("status") != "READY_FOR_CONFIRMATION":
        raise PresentationError("source-assisted Define status is unsupported")
    return _render_ready_source_brief(preview, path)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_standard_streams()
    parser = argparse.ArgumentParser(
        description="Render Fastlane owner conversation from JSON on stdin"
    )
    parser.add_argument(
        "mode",
        choices=(
            "owner",
            "project-ready",
            "side-question",
            "gate-a-brief",
            "gate-b-brief",
            "answer-confirmation",
            "architecture-board-offer",
            "source-brief",
        ),
    )
    parser.add_argument(
        "--input-stdin",
        action="store_true",
        help="Read one JSON object containing report and presentation fields",
    )
    args = parser.parse_args(argv)
    if not args.input_stdin:
        parser.error("--input-stdin is required")
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, Mapping):
            raise PresentationError("input must be a JSON object")
        if args.mode == "source-brief":
            preview = payload.get("source_assist")
            if not isinstance(preview, Mapping):
                raise PresentationError("input is missing source_assist")
            print(render_source_brief_preview(preview))
            return 0
        report = payload.get("report")
        if not isinstance(report, Mapping):
            raise PresentationError("input is missing report")
        if args.mode == "project-ready":
            output = render_project_ready(report)
        elif args.mode == "owner":
            if "audit" in payload:
                raise PresentationError(
                    "audit text is derived from the Fastlane Engine report, not caller prose"
                )
            output = render_owner_update(
                report,
                updated=str(payload.get("updated", "Nothing.")),
            )
        elif args.mode == "architecture-board-offer":
            handoff = payload.get("architecture_board_handoff")
            identity = payload.get("skill_identity")
            if not isinstance(handoff, Mapping) or not isinstance(identity, Mapping):
                raise PresentationError("input is missing architecture-board evidence")
            output = render_architecture_board_offer(
                report,
                handoff,
                identity,
                transition=str(payload.get("transition", "")),
            )
        elif args.mode == "gate-a-brief":
            output = render_owner_decision_brief(report, "GATE_A")
        elif args.mode == "gate-b-brief":
            output = render_owner_decision_brief(report, "GATE_B")
        elif args.mode == "answer-confirmation":
            output = render_answer_confirmation(
                report, str(payload.get("owner_response_id", ""))
            )
        else:
            output = render_side_question_response(
                report,
                answer=str(payload.get("answer", "")),
                project_state_changed=payload.get("project_state_changed") is True,
            )
    except (json.JSONDecodeError, PresentationError) as exc:
        print(f"Fastlane presentation blocked: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
