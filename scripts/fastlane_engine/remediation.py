"""Deterministic remediation ownership and owner-interaction projection.

Canonical inputs: immutable diagnostics, gate/task state, and current route facts.
Returns: non-authoritative remediation and interaction projections.
Side effects: none. This module never reads files, writes state, routes lifecycle,
or grants owner, GitHub, or AWS authority. Public values preserve Fastlane 1.2.16.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Protocol, Sequence

from .core.diagnostics import Diagnostic
from .core.ids import validate_relative_path
from .deliver.models import TaskSummary
from .design.envelope import parse_envelope_paths

try:
    from fastlane_contracts import path_boundaries_overlap, path_boundary_contains
except ModuleNotFoundError:  # Loaded as scripts.fastlane_engine in unit tests.
    from scripts.fastlane_contracts import (
        path_boundaries_overlap,
        path_boundary_contains,
    )


class RemediationContext(Protocol):
    diagnostics: list[Diagnostic]
    prior_remediation_fingerprint: str | None


DOCUMENT_SUMMARY_FILES = (
    "docs/project/README.md",
    "docs/project/PRD.md",
    "docs/project/TASKS.md",
    "docs/project/VERIFY.md",
    "docs/project/RUNBOOK.md",
    "docs/project/BUGFIX.md",
)
PRD_FILE = "docs/project/PRD.md"
VERIFY_FILE = "docs/project/VERIFY.md"
COORDINATOR_LEDGER_PATHS = {
    "docs/project/TASKS.md",
    VERIFY_FILE,
    "bootstrap.yaml",
}

DEFINE_AGENT_DIAGNOSTICS = frozenset(
    {
        "ADAPTIVE_COVERAGE_INVALID",
        "PROJECT_CONTRACT_MIGRATION_REQUIRED",
        "ACTOR_CONTRACT_INVALID",
        "JOURNEY_CONTRACT_INVALID",
        "RICH_USE_CASE_REQUIRED",
        "RICH_USE_CASE_INVALID",
        "BUSINESS_RULE_INVALID",
        "REQUIREMENT_COVERAGE_INVALID",
        "INTAKE_CARD_REQUIRED",
        "INTAKE_CARD_INVALID",
        "INTAKE_CARD_MIGRATION_REQUIRED",
        "INTAKE_CONTRACT_MIGRATION_REQUIRED",
        "INTAKE_SELECTION_PROVENANCE_INVALID",
        "INTAKE_FOUNDATION_PROVENANCE_INVALID",
        "INTAKE_RESPONSE_REGISTER_INVALID",
        "OWNER_BRIEF_SOURCE_STALE",
        "OWNER_BRIEF_COVERAGE_INCOMPLETE",
        "OWNER_BRIEF_SOURCE_MISMATCH",
        "OWNER_BRIEF_OUTPUT_BUDGET_UNRESOLVED",
        "GATE_A_LIFECYCLE_TRANSITION",
        "GATE_A_READINESS_CARD",
        "GATE_A_RECOMMENDATION",
        "PROJECT_CONFIGURATION_CONFLICT",
        "PROJECT_RISK_PROFILE",
        "REQ_AWS_MATERIALITY_INVALID",
        "AWS_CORE_REQ10_EVIDENCE_REQUIRED",
        "AWS_CORE_DISCOVERY_REQUIRED",
        "AWS_CORE_EVIDENCE_STALE",
        "AWS_CORE_EVIDENCE_GENERATED_INVALID",
    }
)
DESIGN_AGENT_DIAGNOSTICS = frozenset(
    {
        "ADR_RATIONALE_DUPLICATE",
        "ADR_RATIONALE_MALFORMED",
        "ADR_RATIONALE_MISMATCH",
        "ADR_RATIONALE_MISSING",
        "ADR_RATIONALE_STALE",
        "ADR_RATIONALE_SUPERSESSION_INVALID",
        "ADR_RATIONALE_UNSAFE",
        "APPLICATION_SOURCE_DISPOSITION_INVALID",
        "APPLICATION_SOURCE_DISPOSITION_MISSING",
        "APPLICATION_SOURCE_PARALLEL_ROOT",
        "AWS_LANE_BOUNDARY",
        "DESIGN_CONTRACT_INVALID",
        "DIAGRAM_PRESENTATION_STALE",
        "GATE_B_DESIGN_CONTRACT_HASH",
        "GATE_B_ENVELOPE",
        "GATE_B_ENVELOPE_HASH",
        "GATE_B_GAP",
        "GATE_B_LIFECYCLE_TRANSITION",
        "GATE_B_PROJECT_DRIFT",
        "GATE_B_READINESS_CARD",
        "GATE_B_RECOMMENDATION",
        "GATE_B_REVISION_MISMATCH",
        "OWNER_BRIEF_SOURCE_STALE",
        "OWNER_BRIEF_COVERAGE_INCOMPLETE",
        "OWNER_BRIEF_SOURCE_MISMATCH",
        "OWNER_BRIEF_OUTPUT_BUDGET_UNRESOLVED",
        "AWS_CORE_EVIDENCE_REQUIRED",
        "AWS_CORE_DISCOVERY_REQUIRED",
        "AWS_CORE_EVIDENCE_STALE",
        "AWS_CORE_EVIDENCE_GENERATED_INVALID",
    }
)
DELIVER_AGENT_DIAGNOSTICS = frozenset(
    {
        "ACTIVE_TASK_CONFLICT",
        "AUTONOMY_OUTSIDE_AUTH",
        "STATE_TASK_DRIFT",
        "TASK_ATTEMPT_BOUNDARY",
        "TASK_AWS_BOUNDARY",
        "TASK_AWS_MODE_REPLAN_REQUIRED",
        "TASK_BASELINE_DRIFT",
        "TASK_COMMAND_BOUNDARY",
        "TASK_EXCLUDED_WRITE",
        "TASK_EXTERNAL_STATE_BOUNDARY",
        "TASK_GITHUB_BOUNDARY",
        "TASK_GRAPH_INVALID",
        "TASK_ID_OUTSIDE_AUTH",
        "TASK_LIMIT_EXCEEDED",
        "TASK_OUTSIDE_TASK_BOUNDARY",
        "TASK_OUTSIDE_WRITE_BOUNDARY",
        "TASK_PLAN_STATE",
        "TASK_PROPERTY_COVERAGE",
        "TASK_REQUIREMENT_TRACE_INVALID",
        "TASK_REQUIREMENT_COVERAGE",
        "TASK_REQUIREMENT_COVERAGE_EVIDENCE_INVALID",
        "TASK_SNAPSHOT",
        "WORKER_LIMIT_EXCEEDED",
    }
)
TASK_REPLAN_DIAGNOSTICS = frozenset(
    {
        "TASK_AWS_MODE_REPLAN_REQUIRED",
        "TASK_REQUIREMENT_TRACE_INVALID",
        "TASK_REQUIREMENT_COVERAGE",
        "TASK_REQUIREMENT_COVERAGE_EVIDENCE_INVALID",
    }
)
OWNER_DECISION_DIAGNOSTICS = frozenset(
    {
        "APPLICATION_SOURCE_DISPOSITION_CONFLICT",
        "BROWNFIELD_PRD_BASELINE",
        "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
        "BROWNFIELD_PRD_PRESERVATION",
        "BROWNFIELD_STATE",
        "GATE_A_ASSUMPTIONS",
        "GATE_A_BLOCKER",
        "GATE_A_COST_POSTURE",
        "INTAKE_FOUNDATION_REQUIRED",
        "PLACEHOLDER_UNRESOLVED",
        "PROJECT_COST_POSTURE",
        "PROJECT_IDENTITY",
        "PROJECT_SELECTION_REQUIRED",
        "REQUIREMENT_METHOD_MIGRATION_REQUIRED",
    }
)
OWNER_SETUP_DIAGNOSTICS = frozenset(
    {
        "AWS_CORE_CAPABILITY_UNAVAILABLE",
    }
)
OWNER_AUTHORIZATION_DIAGNOSTICS = frozenset(
    {
        "GATE_A_COST_AUTHORIZATION",
        "GATE_A_HUMAN_APPROVER",
        "GATE_A_OWNER_RECORD",
        "GATE_A_RECEIPT_MISMATCH",
        "GATE_B_HUMAN_APPROVER",
        "GATE_B_OWNER_RECORD",
        "GATE_B_RECEIPT_MISMATCH",
        "GATE_B_WITHOUT_GATE_A",
        "GATE_B_AUTHORITY_EXPIRED",
    }
)
UNCONFIGURED_SETUP_DIAGNOSTICS = frozenset(
    {
        "PLACEHOLDER_UNRESOLVED",
        "PROJECT_COST_POSTURE",
        "PROJECT_IDENTITY",
        "STATE_SETUP",
    }
)


AWS_CORE_GENERATED_DIAGNOSTICS = frozenset(
    {
        "AWS_CORE_REQ10_EVIDENCE_REQUIRED",
        "AWS_CORE_EVIDENCE_REQUIRED",
        "AWS_CORE_DISCOVERY_REQUIRED",
        "AWS_CORE_EVIDENCE_STALE",
        "AWS_CORE_EVIDENCE_GENERATED_INVALID",
    }
)


def _owner_stage_from_gates(gate_a: str, gate_b: str) -> str:
    if gate_a != "APPROVED_FOR_DESIGN":
        return "DEFINE"
    if gate_b != "APPROVED_FOR_CONSTRUCTION":
        return "DESIGN"
    return "DELIVER"


def _owner_stage_for_aws_core_phases(phases: set[str], fallback: str) -> str:
    """Return the earliest owner stage affected by enforced AWS evidence."""

    if "REQ-10" in phases:
        return "DEFINE"
    if "DESIGN-10" in phases:
        return "DESIGN"
    if "AWS-10" in phases:
        return "DELIVER"
    return fallback


def _agent_correction_is_safe(
    diagnostic: Diagnostic,
    owner_stage: str,
    gate_b: str,
    envelope: Mapping[str, str],
    tasks: TaskSummary,
) -> bool:
    """SAFETY: return whether a generated defect is safely repairable."""

    relative = validate_relative_path(diagnostic.path)
    if relative is None:
        return False
    if diagnostic.code == "DOCUMENT_SUMMARY_STALE":
        return relative in DOCUMENT_SUMMARY_FILES
    if diagnostic.code.startswith("ADR_RATIONALE_"):
        return bool(
            re.fullmatch(r"docs/adr/\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md", relative)
        )
    if diagnostic.code == "DIAGRAM_PRESENTATION_STALE":
        return relative == PRD_FILE

    if owner_stage == "DEFINE":
        if diagnostic.code not in DEFINE_AGENT_DIAGNOSTICS:
            return False
        if diagnostic.code in AWS_CORE_GENERATED_DIAGNOSTICS:
            return relative in {PRD_FILE, VERIFY_FILE}
        return relative == PRD_FILE
    if owner_stage == "DESIGN":
        if diagnostic.code not in DESIGN_AGENT_DIAGNOSTICS:
            return False
        if diagnostic.code in AWS_CORE_GENERATED_DIAGNOSTICS:
            return relative == VERIFY_FILE or (
                gate_b != "APPROVED_FOR_CONSTRUCTION" and relative == PRD_FILE
            )
        if gate_b == "APPROVED_FOR_CONSTRUCTION":
            return False
        return relative == PRD_FILE
    if diagnostic.code not in DELIVER_AGENT_DIAGNOSTICS:
        return False
    if gate_b != "APPROVED_FOR_CONSTRUCTION":
        return False
    try:
        allowed = parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
        )
        excluded = parse_envelope_paths(
            envelope.get("Excluded or owner-only write set", ""),
            "Excluded or owner-only write set",
            allow_none=True,
        )
        protected = parse_envelope_paths(
            envelope.get("Protected dirty paths", ""),
            "Protected dirty paths",
            allow_none=True,
        )
    except ValueError:
        return False
    if any(path_boundaries_overlap(relative, item) for item in excluded + protected):
        return False
    if relative in COORDINATOR_LEDGER_PATHS:
        return True
    if len(tasks.active) != 1:
        return False
    active_task = tasks.active[0]
    if tasks.attempts_used.get(active_task, 0) >= tasks.attempt_budgets.get(
        active_task, 0
    ):
        return False
    return any(path_boundary_contains(item, relative) for item in allowed) and any(
        path_boundary_contains(item, relative)
        for item in tasks.write_sets.get(active_task, [])
    )


def _owner_authorization_action(items: list[dict[str, Any]]) -> str:
    codes = {str(item.get("diagnostic_code", "")) for item in items}
    if any(code.startswith("GATE_A_") for code in codes):
        return "APPROVE_GATE_A"
    if any(code.startswith("GATE_B_") for code in codes):
        return "APPROVE_GATE_B"
    return "AUTHORIZE_AWS_OPERATION"


def _resolved_owner_stage(owner_stage_hint: str | None, gate_a: str, gate_b: str) -> str:
    return (
        owner_stage_hint
        if owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}
        else _owner_stage_from_gates(gate_a, gate_b)
    )


def _agent_correction_action(
    items: list[dict[str, Any]],
    tasks: TaskSummary,
    task_validation_evidence: Sequence[Mapping[str, str]],
    remediation_fingerprint: str,
) -> dict[str, Any]:
    corrections: list[dict[str, Any]] = []
    active_task = tasks.active[0] if len(tasks.active) == 1 else None
    active_write_set = list(tasks.write_sets.get(active_task, ())) if active_task else []
    for item in items:
        diagnostic_path = str(item.get("path") or "NONE")
        ledger_task_owned = bool(
            active_task
            and item["diagnostic_code"] in DELIVER_AGENT_DIAGNOSTICS
            and diagnostic_path in COORDINATOR_LEDGER_PATHS
            and task_validation_evidence
        )
        task_owned = bool(
            ledger_task_owned
            or (
                active_task
                and diagnostic_path not in COORDINATOR_LEDGER_PATHS
                and any(
                    path_boundary_contains(boundary, diagnostic_path)
                    for boundary in active_write_set
                )
            )
        )
        write_boundary = (
            list(dict.fromkeys([*active_write_set, diagnostic_path]))
            if ledger_task_owned
            else active_write_set if task_owned else [diagnostic_path]
        )
        corrections.append(
            {
                "diagnostic_id": item["diagnostic_id"],
                "cause": item["cause"],
                "path": diagnostic_path,
                "task_id": active_task if task_owned else "NONE",
                "write_boundary": write_boundary,
                "validation_evidence": (
                    [dict(row) for row in task_validation_evidence]
                    if task_owned
                    else []
                ),
            }
        )
    command = (
        "python scripts/bootstrap_doctor.py --root . --json "
        "--prior-remediation-fingerprint " + remediation_fingerprint
    )
    return {
        "responsible_party": "CODEX",
        "action_kind": "CORRECT_AND_REVALIDATE",
        "automatic_continuation_allowed": True,
        "corrections": corrections,
        "engine_rerun": {"command": command, "fingerprint": remediation_fingerprint},
    }


def derive_remediation(
    ctx: RemediationContext,
    *,
    classification: str,
    gate_a: str,
    gate_b: str,
    envelope: Mapping[str, str],
    tasks: TaskSummary,
    requirements_revision: str | None = None,
    design_revision: str | None = None,
    owner_stage_hint: str | None = None,
    task_validation_evidence: Sequence[Mapping[str, str]] = (),
) -> dict[str, Any]:
    """SAFETY: classify errors and derive one deterministic next action."""

    owner_stage = _resolved_owner_stage(
        owner_stage_hint,
        gate_a,
        gate_b,
    )
    items: list[dict[str, Any]] = []
    for index, diagnostic in enumerate(ctx.diagnostics, start=1):
        if diagnostic.severity != "ERROR":
            continue
        responsible_party = "HUMAN_REVIEWER"
        category = "MANUAL_SAFETY_REVIEW"
        automatic = False
        if (
            classification == "UNCONFIGURED_TEMPLATE"
            and diagnostic.code in UNCONFIGURED_SETUP_DIAGNOSTICS
        ):
            responsible_party = "OWNER"
            category = "OWNER_SETUP"
        elif diagnostic.code in OWNER_SETUP_DIAGNOSTICS:
            responsible_party = "OWNER"
            category = "OWNER_SETUP"
        elif diagnostic.code in OWNER_DECISION_DIAGNOSTICS:
            responsible_party = "OWNER"
            category = "OWNER_DECISION"
        elif diagnostic.code in OWNER_AUTHORIZATION_DIAGNOSTICS:
            responsible_party = "OWNER"
            category = "OWNER_AUTHORIZATION"
        elif diagnostic.code in TASK_REPLAN_DIAGNOSTICS and _agent_correction_is_safe(
            diagnostic, owner_stage, gate_b, envelope, tasks
        ):
            responsible_party = "CODEX"
            category = "AGENT_REPLAN"
            automatic = True
        elif _agent_correction_is_safe(
            diagnostic, owner_stage, gate_b, envelope, tasks
        ):
            responsible_party = "CODEX"
            category = "AGENT_CORRECTION"
            automatic = True
        item = {
            "diagnostic_id": f"DGN-{index:04d}",
            "diagnostic_code": diagnostic.code,
            "path": diagnostic.path,
            "responsible_party": responsible_party,
            "category": category,
            "automatic_correction_allowed": automatic,
        }
        if category in {"AGENT_CORRECTION", "AGENT_REPLAN"}:
            item["cause"] = re.sub(r"\s+", " ", diagnostic.message).strip()
        items.append(item)

    codex_payload: list[dict[str, str]] = []
    for item in items:
        if item["category"] not in {"AGENT_CORRECTION", "AGENT_REPLAN"}:
            continue
        diagnostic_index = int(str(item["diagnostic_id"]).rsplit("-", 1)[1]) - 1
        diagnostic = ctx.diagnostics[diagnostic_index]
        codex_payload.append(
            {
                "code": diagnostic.code,
                "path": diagnostic.path or "NONE",
                "cause": re.sub(r"\s+", " ", diagnostic.message).strip(),
                "requirements_revision": requirements_revision or "NONE",
                "design_revision": design_revision or "NONE",
            }
        )
    remediation_fingerprint = "NONE"
    if codex_payload:
        canonical = json.dumps(
            codex_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        remediation_fingerprint = "sha256:" + hashlib.sha256(canonical).hexdigest()
    repeated_fingerprint = (
        remediation_fingerprint != "NONE"
        and ctx.prior_remediation_fingerprint == remediation_fingerprint
    )
    if repeated_fingerprint:
        for item in items:
            if item["category"] in {"AGENT_CORRECTION", "AGENT_REPLAN"}:
                item["responsible_party"] = "HUMAN_REVIEWER"
                item["category"] = "MANUAL_SAFETY_REVIEW"
                item["automatic_correction_allowed"] = False

    manual = [item for item in items if item["category"] == "MANUAL_SAFETY_REVIEW"]
    codex = [item for item in items if item["category"] == "AGENT_CORRECTION"]
    replans = [item for item in items if item["category"] == "AGENT_REPLAN"]
    owner_decisions = [item for item in items if item["category"] == "OWNER_DECISION"]
    owner_setup = [item for item in items if item["category"] == "OWNER_SETUP"]
    owner_authorization = [
        item for item in items if item["category"] == "OWNER_AUTHORIZATION"
    ]
    if manual:
        next_action = {
            "responsible_party": "HUMAN_REVIEWER",
            "action_kind": "REVIEW_SAFETY_BLOCKER",
            "automatic_continuation_allowed": False,
        }
    elif replans:
        next_action = {
            "responsible_party": "CODEX",
            "action_kind": "REPLAN_TASKS",
            "automatic_continuation_allowed": True,
            "preserve_done_evidence": True,
        }
    elif codex:
        next_action = _agent_correction_action(
            codex, tasks, task_validation_evidence, remediation_fingerprint
        )
    elif owner_decisions:
        next_action = {
            "responsible_party": "OWNER",
            "action_kind": "ANSWER_OPEN_DECISIONS",
            "automatic_continuation_allowed": False,
        }
    elif owner_setup:
        next_action = {
            "responsible_party": "OWNER",
            "action_kind": (
                "COMPLETE_PREREQUISITE_CHECKLIST"
                if classification == "UNCONFIGURED_TEMPLATE"
                else "ENABLE_AWS_CORE"
            ),
            "automatic_continuation_allowed": False,
        }
    elif owner_authorization:
        next_action = {
            "responsible_party": "OWNER",
            "action_kind": _owner_authorization_action(owner_authorization),
            "automatic_continuation_allowed": False,
        }
    else:
        next_action = {
            "responsible_party": "CODEX",
            "action_kind": "CONTINUE_CURRENT_ROUTE",
            "automatic_continuation_allowed": True,
        }
    return {
        "items": items,
        "next_action": next_action,
        "fingerprint": remediation_fingerprint,
        "retry_state": "REPEATED" if repeated_fingerprint else "FIRST_OR_NONE",
    }


def derive_interaction(
    lifecycle_state: str,
    next_prompt: str,
    *,
    has_errors: bool,
    diagnostic_codes: list[str],
    design_aws_core_ready: bool,
    aws_execution_planning_ready: bool,
    remediation: Mapping[str, Any] | None = None,
    owner_stage_hint: str | None = None,
    aws_progress_state: str | None = None,
    aws_mutation_authority_ready: bool = False,
    aws_lane: str | None = None,
    aws_read_authority_required: bool = False,
    req_aws_core_materiality: str = "OPTIONAL",
    req_aws_core_ready: bool = True,
) -> dict[str, Any]:
    """SAFETY: derive stable owner interaction metadata without prose."""

    aws_core_capability_unavailable = (
        "AWS_CORE_CAPABILITY_UNAVAILABLE" in diagnostic_codes
    )

    if lifecycle_state in {
        "INTAKE_REQUIRED",
        "REQUIREMENTS_ANALYSIS",
        "REQUIREMENTS_STALE",
        "WAITING_GATE_A",
    }:
        owner_stage = "DEFINE"
    elif lifecycle_state in {"DESIGN_REQUIRED", "DESIGN_STALE", "WAITING_GATE_B"}:
        owner_stage = "DESIGN"
    else:
        owner_stage = "DELIVER"
    if owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}:
        owner_stage = owner_stage_hint

    route_reason_code = lifecycle_state
    if lifecycle_state in {
        "AWS_RESIDUAL_REVIEW_BLOCKED",
        "RELEASE_REVIEW_BLOCKED",
    }:
        response_mode = "BLOCKER"
        state = "BLOCKED"
        action_kind = "REVIEW_SAFETY_BLOCKER"
        automatic = False
        formal_receipt = False
    elif has_errors or lifecycle_state == "BLOCKED":
        next_action = remediation.get("next_action") if remediation else None
        remediation_action = (
            str(next_action.get("action_kind", ""))
            if isinstance(next_action, Mapping)
            else ""
        )
        if remediation_action in {"CORRECT_AND_REVALIDATE", "REPLAN_TASKS"}:
            response_mode = "OWNER_UPDATE"
            state = "WORKING"
            action_kind = "NONE_CONTINUE_AUTOMATICALLY"
            automatic = True
            if remediation_action == "REPLAN_TASKS":
                route_reason_code = "TASK_REPLAN_REQUIRED"
        elif remediation_action == "ANSWER_OPEN_DECISIONS":
            response_mode = "OWNER_UPDATE"
            state = "NEEDS_INPUT"
            action_kind = remediation_action
            automatic = False
            route_reason_code = "INTAKE_REQUIRED"
        elif remediation_action in {
            "APPROVE_GATE_A",
            "APPROVE_GATE_B",
            "AUTHORIZE_AWS_OPERATION",
            "COMPLETE_PREREQUISITE_CHECKLIST",
            "ENABLE_AWS_CORE",
            "REVIEW_SAFETY_BLOCKER",
        }:
            response_mode = "BLOCKER"
            state = "BLOCKED"
            action_kind = remediation_action
            automatic = False
        else:
            response_mode = "BLOCKER"
            state = "BLOCKED"
            action_kind = (
                "ENABLE_AWS_CORE"
                if aws_core_capability_unavailable
                else "FIX_VALIDATION_FAILURE"
            )
            automatic = False
        formal_receipt = False
    elif lifecycle_state in {
        "AWS_DEPLOYMENT_ACTION_TERMINAL",
        "AWS_TEARDOWN_ACTION_TERMINAL",
    }:
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif lifecycle_state in {
        "AWS_DEPLOYMENT_RECONCILIATION",
        "AWS_RESIDUAL_REVIEW",
    }:
        response_mode = "AWS_RECEIPT" if aws_read_authority_required else "OWNER_UPDATE"
        state = "AWAITING_APPROVAL" if aws_read_authority_required else "WORKING"
        action_kind = (
            "AUTHORIZE_AWS_READ_PREFLIGHT"
            if aws_read_authority_required
            else "NONE_CONTINUE_AUTOMATICALLY"
        )
        automatic = not aws_read_authority_required
        formal_receipt = aws_read_authority_required
    elif lifecycle_state == "WAITING_AWS_TEARDOWN_AUTH":
        response_mode = (
            "OWNER_UPDATE" if aws_mutation_authority_ready else "AWS_RECEIPT"
        )
        state = "WORKING" if aws_mutation_authority_ready else "AWAITING_APPROVAL"
        action_kind = (
            "NONE_CONTINUE_AUTOMATICALLY"
            if aws_mutation_authority_ready
            else "AUTHORIZE_AWS_TEARDOWN"
        )
        automatic = aws_mutation_authority_ready
        formal_receipt = not aws_mutation_authority_ready
    elif lifecycle_state in {
        "AWS_RESIDUAL_REVIEW_COMPLETE",
        "AWS_RESIDUALS_RETAINED",
        "AWS_TEARDOWN_COMPLETE",
    }:
        response_mode = "OWNER_UPDATE"
        state = "COMPLETE"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = False
        formal_receipt = False
    elif lifecycle_state == "AWS_RESIDUALS_REMAIN":
        response_mode = "BLOCKER"
        state = "NEEDS_INPUT"
        action_kind = "CHOOSE_AWS_RESIDUAL_DISPOSITION"
        automatic = False
        formal_receipt = False
    elif aws_progress_state == "AWS_GUIDANCE_REQUIRED":
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif aws_progress_state == "AWS_READ_SCOPE_REQUIRED":
        response_mode = "AWS_RECEIPT"
        state = "AWAITING_APPROVAL"
        action_kind = "AUTHORIZE_AWS_READ_PREFLIGHT"
        automatic = False
        formal_receipt = True
    elif aws_progress_state == "AWS_PREFLIGHT_RUNNING":
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif aws_progress_state == "AWS_PREFLIGHT_READY":
        response_mode = "OWNER_UPDATE"
        state = "COMPLETE"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = False
        formal_receipt = False
    elif aws_progress_state == "WAITING_AWS_MUTATION_AUTH":
        response_mode = (
            "OWNER_UPDATE" if aws_mutation_authority_ready else "AWS_RECEIPT"
        )
        state = "WORKING" if aws_mutation_authority_ready else "AWAITING_APPROVAL"
        action_kind = (
            "NONE_CONTINUE_AUTOMATICALLY"
            if aws_mutation_authority_ready
            else "AUTHORIZE_AWS_OPERATION"
        )
        automatic = aws_mutation_authority_ready
        formal_receipt = not aws_mutation_authority_ready
    elif lifecycle_state == "WAITING_GATE_A":
        response_mode = "GATE_A"
        state = "AWAITING_APPROVAL"
        action_kind = "APPROVE_GATE_A"
        automatic = False
        formal_receipt = True
    elif lifecycle_state == "WAITING_GATE_B":
        response_mode = "GATE_B"
        state = "AWAITING_APPROVAL"
        action_kind = "APPROVE_GATE_B"
        automatic = False
        formal_receipt = True
    elif next_prompt == "AWS-50":
        response_mode = (
            "OWNER_UPDATE" if aws_mutation_authority_ready else "AWS_RECEIPT"
        )
        state = "WORKING" if aws_mutation_authority_ready else "AWAITING_APPROVAL"
        action_kind = (
            "NONE_CONTINUE_AUTOMATICALLY"
            if aws_mutation_authority_ready
            else "AUTHORIZE_AWS_TEARDOWN"
        )
        automatic = aws_mutation_authority_ready
        formal_receipt = not aws_mutation_authority_ready
    elif next_prompt in {"AWS-30", "AWS-40"} and aws_read_authority_required:
        response_mode = "AWS_RECEIPT"
        state = "AWAITING_APPROVAL"
        action_kind = "AUTHORIZE_AWS_READ_PREFLIGHT"
        automatic = False
        formal_receipt = True
    elif next_prompt in {"AWS-30", "AWS-40"}:
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif next_prompt.startswith("AWS-") and aws_execution_planning_ready:
        response_mode = "AWS_RECEIPT"
        state = "AWAITING_APPROVAL"
        action_kind = "AUTHORIZE_AWS_OPERATION"
        automatic = False
        formal_receipt = True
    elif next_prompt.startswith("AWS-"):
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif lifecycle_state in {"INTAKE_REQUIRED", "REQUIREMENTS_STALE"}:
        response_mode = "OWNER_UPDATE"
        state = "NEEDS_INPUT"
        action_kind = "ANSWER_OPEN_DECISIONS"
        automatic = False
        formal_receipt = False
    elif lifecycle_state == "RELEASE_VERIFIED":
        response_mode = "OWNER_UPDATE"
        state = "COMPLETE"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = False
        formal_receipt = False
    else:
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False

    req_core_material = bool(
        owner_stage == "DEFINE"
        and next_prompt in {"REQ-10", "INTAKE-20"}
        and req_aws_core_materiality == "REQUIRED"
    )
    material = (
        req_core_material
        or owner_stage == "DESIGN"
        or next_prompt.startswith("AWS-")
        or aws_progress_state is not None
    )
    if not material:
        evidence_status = "NOT_REQUIRED"
    elif req_core_material:
        evidence_status = (
            "CURRENT"
            if req_aws_core_ready
            else ("BLOCKED" if has_errors else "REQUIRED")
        )
    elif aws_progress_state is not None:
        evidence_status = (
            "REQUIRED" if aws_progress_state == "AWS_GUIDANCE_REQUIRED" else "CURRENT"
        )
    elif next_prompt.startswith("AWS-"):
        evidence_status = (
            "CURRENT"
            if aws_execution_planning_ready
            else ("BLOCKED" if has_errors else "REQUIRED")
        )
    else:
        evidence_status = (
            "CURRENT"
            if design_aws_core_ready
            else ("BLOCKED" if has_errors else "REQUIRED")
        )

    blocking_ids: list[str] = []
    if state == "BLOCKED" and remediation:
        remediation_items = remediation.get("items")
        if isinstance(remediation_items, list):
            blocking_ids = [
                str(item["diagnostic_id"])
                for item in remediation_items
                if isinstance(item, Mapping) and "diagnostic_id" in item
            ]
    if state == "BLOCKED" and not blocking_ids:
        blocking_ids = sorted(set(diagnostic_codes))

    return {
        "owner_stage": owner_stage,
        "response_mode": response_mode,
        "state": state,
        "route_reason_code": route_reason_code,
        "owner_action_required": action_kind != "NONE_CONTINUE_AUTOMATICALLY",
        "owner_action_kind": action_kind,
        "blocking_ids": blocking_ids,
        "automatic_continuation_allowed": automatic,
        "turn_boundary_required": (
            action_kind != "NONE_CONTINUE_AUTOMATICALLY" and not automatic
        ),
        "formal_receipt_required": formal_receipt,
        "aws_core": {
            "materiality": "MATERIAL" if material else "NOT_MATERIAL",
            "evidence_status": evidence_status,
        },
    }


def derive_unconfigured_template_interaction(
    diagnostic_codes: list[str],
) -> dict[str, Any]:
    """Return honest setup-first metadata for an untouched adopter template."""

    return {
        "owner_stage": "DEFINE",
        "response_mode": "BLOCKER",
        "state": "BLOCKED",
        "route_reason_code": "UNCONFIGURED_TEMPLATE",
        "owner_action_required": True,
        "owner_action_kind": "COMPLETE_PREREQUISITE_CHECKLIST",
        "blocking_ids": sorted(set(diagnostic_codes)),
        "automatic_continuation_allowed": False,
        "turn_boundary_required": True,
        "formal_receipt_required": False,
        "aws_core": {
            "materiality": "NOT_MATERIAL",
            "evidence_status": "NOT_REQUIRED",
        },
    }
