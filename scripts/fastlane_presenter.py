#!/usr/bin/env python3
"""Render deterministic Fastlane owner updates from machine-derived state."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Mapping, Sequence

try:
    from intake_response import intake_reply_token
    from fastlane_stdio import configure_utf8_standard_streams
except ModuleNotFoundError:  # Loaded as scripts.fastlane_presenter in unit tests.
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
    "CONSTRUCTION_SINGLE": "Approved local construction can continue.",
    "CONSTRUCTION_AUTONOMOUS": "Approved local construction is in progress.",
    "RELEASE_REVIEW": "Local construction is ready for release review.",
    "AWS_GUIDANCE_REQUIRED": "Current AWS guidance is needed before deployment planning.",
    "AWS_READ_SCOPE_REQUIRED": "Read-only AWS preflight needs your authorization.",
    "AWS_PREFLIGHT_RUNNING": "Authorized read-only AWS preflight is in progress.",
    "AWS_PREFLIGHT_READY": "Read-only AWS preflight is complete.",
    "WAITING_AWS_MUTATION_AUTH": (
        "Read-only AWS preflight is complete; deployment needs separate authorization."
    ),
    "AWS_RESIDUAL_REVIEW": "Authorized read-only AWS residual review is in progress.",
    "WAITING_AWS_TEARDOWN_AUTH": (
        "Read-only residual review is complete; teardown needs separate authorization."
    ),
    "AWS_RESIDUAL_REVIEW_COMPLETE": (
        "Read-only AWS residual review is complete; no unexpected resources remain."
    ),
    "AWS_RESIDUALS_REMAIN": (
        "Read-only AWS review found residual resources that need your decision."
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
    "ANSWER_OPEN_DECISIONS": "Answer the next one to three project questions.",
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
    "REVIEW_AWS_RESIDUALS": (
        "Review the remaining AWS resources and decide which to retain, remove, "
        "or investigate."
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
    "CONSTRUCTION_SINGLE": "Codex will execute the next ready local task.",
    "CONSTRUCTION_AUTONOMOUS": "Codex will continue approved local tasks.",
    "RELEASE_REVIEW": "Codex will validate evidence and release readiness.",
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
    "AWS_RESIDUALS_REMAIN": (
        "Codex will continue only after you decide how the listed residuals should "
        "be handled."
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
    "REVIEW_AWS_RESIDUALS": (
        "For each listed residual: RETAIN, REMOVE under new authorization, or "
        "INVESTIGATE."
    ),
}


def _interaction(report: Mapping[str, Any]) -> Mapping[str, Any]:
    value = report.get("interaction")
    if not isinstance(value, Mapping):
        raise PresentationError("doctor report is missing interaction state")
    return value

AWS_PROGRESS_STATES = {
    "AWS_GUIDANCE_REQUIRED",
    "AWS_READ_SCOPE_REQUIRED",
    "AWS_PREFLIGHT_RUNNING",
    "AWS_PREFLIGHT_READY",
    "WAITING_AWS_MUTATION_AUTH",
}

AWS_TEARDOWN_STATES = {
    "AWS_RESIDUAL_REVIEW",
    "WAITING_AWS_TEARDOWN_AUTH",
    "AWS_RESIDUAL_REVIEW_COMPLETE",
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
        raise PresentationError("blocked AWS residual review is missing its exact reason")
    reason = raw.strip()
    if (
        reason in {"", "NONE"}
        or len(reason) > 500
        or re.search(r"[\r\n\x00-\x1f\x7f]", reason) is not None
    ):
        raise PresentationError("blocked AWS residual review has an unsafe reason")
    return reason


def _validate_aws_teardown_interaction(
    interaction: Mapping[str, Any],
) -> bool:
    """Validate teardown states before deployment-progress compatibility checks."""

    reason = str(interaction.get("route_reason_code", ""))
    action = str(interaction.get("owner_action_kind", ""))
    if reason not in AWS_TEARDOWN_STATES:
        if action in {"AUTHORIZE_AWS_TEARDOWN", "REVIEW_AWS_RESIDUALS"}:
            raise PresentationError("AWS teardown action is requested in the wrong state")
        return False

    required = interaction.get("owner_action_required") is True
    automatic = interaction.get("automatic_continuation_allowed") is True
    formal = interaction.get("formal_receipt_required") is True

    if reason == "AWS_RESIDUAL_REVIEW":
        awaiting = action == "AUTHORIZE_AWS_READ_PREFLIGHT"
        continuing = action == "NONE_CONTINUE_AUTOMATICALLY"
        if awaiting:
            if not required or automatic or not formal:
                raise PresentationError("AWS residual read authority state is inconsistent")
        elif continuing:
            if required or not automatic or formal:
                raise PresentationError("automatic AWS residual review state is inconsistent")
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
    elif reason in {"AWS_RESIDUAL_REVIEW_COMPLETE", "AWS_TEARDOWN_COMPLETE"}:
        if action != "NONE_CONTINUE_AUTOMATICALLY" or required or automatic or formal:
            raise PresentationError("terminal AWS teardown state is inconsistent")
    elif reason == "AWS_RESIDUALS_REMAIN":
        if action != "REVIEW_AWS_RESIDUALS" or not required or automatic or formal:
            raise PresentationError("AWS residual disposition state is inconsistent")
    elif reason == "AWS_RESIDUAL_REVIEW_BLOCKED":
        if action != "REVIEW_SAFETY_BLOCKER" or not required or automatic or formal:
            raise PresentationError("blocked AWS residual review state is inconsistent")
    return True



def _validate_aws_progress_interaction(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> None:
    """Fail closed when AWS guidance, read, and mutation boundaries conflict."""

    reason = str(interaction.get("route_reason_code", ""))
    action = str(interaction.get("owner_action_kind", ""))
    required = interaction.get("owner_action_required") is True
    automatic = interaction.get("automatic_continuation_allowed") is True
    formal = interaction.get("formal_receipt_required") is True
    if _validate_aws_teardown_interaction(interaction):
        return

    execution = report.get("aws_execution")
    progress = (
        str(execution.get("progress_state", ""))
        if isinstance(execution, Mapping)
        else ""
    )
    lane = (
        str(execution.get("lane", ""))
        if isinstance(execution, Mapping)
        else ""
    )

    if reason in AWS_PROGRESS_STATES:
        if not isinstance(execution, Mapping) or progress != reason:
            raise PresentationError("AWS progress state conflicts with interaction route")
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
        raise PresentationError("read-only AWS authority is requested in the wrong state")
    if action == "AUTHORIZE_AWS_OPERATION" and reason != "WAITING_AWS_MUTATION_AUTH":
        raise PresentationError("AWS mutation authority is requested before preflight readiness")

    if reason == "AWS_READ_SCOPE_REQUIRED":
        if (
            action != "AUTHORIZE_AWS_READ_PREFLIGHT"
            or not required
            or automatic
            or not formal
        ):
            raise PresentationError("read-only AWS authority state is inconsistent")
    elif reason in {"AWS_GUIDANCE_REQUIRED", "AWS_PREFLIGHT_RUNNING"}:
        if action != "NONE_CONTINUE_AUTOMATICALLY" or required or not automatic or formal:
            raise PresentationError("automatic AWS progress state is inconsistent")
    elif reason == "AWS_PREFLIGHT_READY":
        if lane == "fast-dev":
            expected_automatic = True
        elif lane in {"documentation-only", "read-only"}:
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
        if awaiting:
            if not required or automatic or not formal:
                raise PresentationError("AWS mutation authority state is inconsistent")
        elif continuing:
            if required or not automatic or formal:
                raise PresentationError("authorized AWS continuation state is inconsistent")
        else:
            raise PresentationError("invalid AWS mutation-wait action")


def _remediation_text(report: Mapping[str, Any]) -> tuple[str | None, str | None]:
    value = report.get("remediation")
    if value is None:
        return None, None
    if not isinstance(value, Mapping):
        raise PresentationError("doctor report has invalid remediation state")
    next_action = value.get("next_action")
    if not isinstance(next_action, Mapping):
        raise PresentationError("doctor report has invalid remediation next action")
    action_kind = str(next_action.get("action_kind", ""))
    party = str(next_action.get("responsible_party", ""))
    automatic = next_action.get("automatic_continuation_allowed") is True
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
        "REVIEW_AWS_RESIDUALS",
        "COMPLETE_PREREQUISITE_CHECKLIST",
        "CONTINUE_CURRENT_ROUTE",
        "ENABLE_AWS_CORE",
    }:
        raise PresentationError("unknown remediation next action")
    return None, None


def _task_details(report: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = report.get("tasks")
    return value if isinstance(value, Mapping) else None


TASK_ID_PATTERN = re.compile(r"TASK-\d{4,}")
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
    if total < 1 or sum(
        (completed, skipped, blocked, ready_count, active_count)
    ) > total:
        raise PresentationError("invalid deterministic task progress")
    if "active_ids" in tasks and len(active) != active_count:
        raise PresentationError("active task count does not match task identifiers")
    if "ready_ids" in tasks and len(ready) != ready_count:
        raise PresentationError("ready task count does not match task identifiers")
    if "blocked_ids" in tasks:
        blocked_ids = _task_ids(tasks, "blocked_ids")
        if len(blocked_ids) != blocked:
            raise PresentationError("blocked task count does not match task identifiers")
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
            "Codex will reconsider only architecture decisions affected by "
            "this change."
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
    if not isinstance(core, Mapping) or core.get("evidence_status") != "CURRENT":
        return None
    stage = str(interaction.get("owner_stage", ""))
    next_prompt = str(report.get("next_prompt", ""))
    if stage == "DESIGN":
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
        raise PresentationError("AWS preflight state is missing its execution projection")
    preflight = execution.get("preflight")
    if not isinstance(preflight, Mapping):
        raise PresentationError("AWS preflight state is missing its evidence projection")
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
        return "Documentation-only AWS guidance is complete. No AWS account was accessed."

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
        raise PresentationError("AWS preflight running state is not safely attributable")

    if status != "READY" or account_access != "READ_ONLY_OBSERVED":
        raise PresentationError("AWS preflight readiness is not supported by observed access")
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
    if lane == "fast-dev":
        return (
            "Read-only AWS preflight and the bounded Gate B authority are current.",
            "Codex will perform only the exact Gate-B-authorized non-production mutation.",
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
        or not 1 <= len(questions) <= 3
        or not isinstance(exact_reply, str)
        or not exact_reply.strip()
        or not isinstance(digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        or not isinstance(reply_token, str)
        or re.fullmatch(r"R-[0-9A-F]{12}", reply_token) is None
        or not isinstance(card.get("accept_all_allowed"), bool)
    ):
        raise PresentationError("invalid deterministic intake card")
    if reply_token != intake_reply_token(card_id, revision, digest) or not exact_reply.startswith(reply_token + "; "):
        raise PresentationError("intake copyable reply is not bound to its current card")
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


def _intake_question_lines(card: Mapping[str, Any]) -> list[str]:
    questions = card["questions"]
    lines: list[str] = []
    for question in questions:
        reply_key = str(question["reply_key"])
        lines.extend(("", f"{reply_key}. {question['prompt']}"))
        if question["kind"] == "DECISION":
            options = question["options"]
            recommended = question["recommended"]
            required = set(question["required_detail_for"])
            for choice in ("A", "B", "C"):
                prefix = "Recommended \u2014 " if recommended == choice else ""
                lines.append(f"{choice}. {prefix}{options[choice]}")
                if choice in required:
                    lines.append(
                        f"   If you choose {choice}: {question['detail_prompt']}"
                    )
            if recommended is None:
                lines.append(
                    "No recommendation—choose the option that matches your situation."
                )
        else:
            lines.append(f"Reply: {question['detail_prompt']}")
    return lines


def _render_intake_card(
    report: Mapping[str, Any],
    card: Mapping[str, Any],
    *,
    updated: str,
) -> str:
    question_count = len(card["questions"])
    if question_count == 1:
        status = "1 question remains before requirements analysis."
    else:
        status = (
            f"{question_count} questions remain before requirements analysis."
        )
    lines = [
        "FASTLANE \u00b7 DEFINE",
        "",
        f"Status: {status}",
        f"Updated: {updated}",
        "Need from you: Answer the questions below.",
    ]
    lines.extend(_intake_question_lines(card))
    lines.extend(
        (
            "",
            "Next: Codex will record only your confirmed answers, validate them, "
            "and continue definition.",
        )
    )
    if card["accept_all_allowed"]:
        lines.append(f"You may also reply `{card['reply_token']}; Accept all recommendations.`")
    lines.extend(("", "Copyable reply:", str(card["exact_reply"])))
    return "\n".join(lines)
def render_owner_update(
    report: Mapping[str, Any],
    *,
    updated: str = "Nothing.",
) -> str:
    """Render one concise non-receipt lifecycle update."""

    interaction = _interaction(report)
    if interaction.get("formal_receipt_required") is True:
        raise PresentationError("formal gate and AWS receipts use canonical receipt renderers")
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
    expected_boundary = required and not (
        interaction.get("automatic_continuation_allowed") is True
    )
    if boundary is not None and boundary is not expected_boundary:
        raise PresentationError("owner turn boundary conflicts with interaction state")
    if action_kind == "ANSWER_OPEN_DECISIONS":
        card = _pending_intake_card(report)
        if card is not None:
            return _render_intake_card(report, card, updated=updated)

    remediation_status, remediation_next = _remediation_text(report)
    status_text = remediation_status or _delivery_status(report, reason) or STATUS_TEXT[reason]
    next_text = (
        remediation_next or _delivery_next(report, reason)
        or _coverage_next(report, reason) or NEXT_TEXT[reason]
    )
    ready_copy = _aws_ready_owner_copy(report, reason)
    if ready_copy is not None:
        status_text, next_text = ready_copy
    if reason == "WAITING_AWS_MUTATION_AUTH" and action_kind == "NONE_CONTINUE_AUTOMATICALLY":
        status_text = (
            "Read-only AWS preflight and the exact deployment authorization are current."
        )
        next_text = "Codex will perform only the exact authorized AWS mutation."
    if reason == "WAITING_AWS_TEARDOWN_AUTH" and action_kind == "NONE_CONTINUE_AUTOMATICALLY":
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
    preflight_audit = _aws_preflight_audit(report, interaction)
    audit_parts = [item for item in (audit, preflight_audit) if item is not None]
    if audit_parts:
        lines.append("Audit: " + " ".join(audit_parts))
    reply = COPYABLE_REPLIES.get(action_kind)
    if required and reply:
        lines.extend(("", "Copyable reply:", reply))
    return "\n".join(lines)


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
        f"Pending next action: {ACTION_TEXT[action_kind]}",
    ]
    reason = str(interaction.get("route_reason_code", ""))
    if reason == "AWS_RESIDUAL_REVIEW_BLOCKED":
        lines.append(f"Safety blocker: {_teardown_blocker_reason(report)}")
    if required and action_kind == "ANSWER_OPEN_DECISIONS":
        card = _pending_intake_card(report)
        if card is not None:
            lines.extend(("", "The pending questions are unchanged:"))
            lines.extend(_intake_question_lines(card))
            if card["accept_all_allowed"]:
                lines.append(f"You may also reply `{card['reply_token']}; Accept all recommendations.`")
            lines.extend(("", "Copyable reply:", str(card["exact_reply"])))
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
            next_text = "Codex will remove only the exact resources authorized for teardown."
        lines.append(f"Next: {next_text}")
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
        raise PresentationError("blocked prerequisites require at least one checklist step")
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


def main(argv: list[str] | None = None) -> int:
    configure_utf8_standard_streams()
    parser = argparse.ArgumentParser(
        description="Render Fastlane owner conversation from JSON on stdin"
    )
    parser.add_argument("mode", choices=("owner", "side-question"))
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
        report = payload.get("report")
        if not isinstance(report, Mapping):
            raise PresentationError("input is missing report")
        if args.mode == "owner":
            if "audit" in payload:
                raise PresentationError(
                    "audit text is derived from the doctor report, not caller prose"
                )
            output = render_owner_update(
                report,
                updated=str(payload.get("updated", "Nothing.")),
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
