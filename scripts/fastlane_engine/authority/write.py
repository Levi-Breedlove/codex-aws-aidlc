"""Deterministic repository-ledger write authority projections.

Canonical inputs are current routes, task state, external authority, and AWS journal
projections. Returns exact repository write allowances only. Side effects are
prohibited; this module never writes a ledger or executes an external action.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..aws import (
    AWS_DEPLOYMENT_ATTEMPT_ID,
    AWS_DEPLOYMENT_EVIDENCE_HEADING,
    AWS_TEARDOWN_ATTEMPT_ID,
    AWS_TEARDOWN_EVIDENCE_HEADING,
    release_lifecycle_intent_boundary_is_settled,
)
from ..core.ids import clean_cell
from ..deliver.models import TaskSummary
from ..design import parse_envelope_paths
from ..project_inspection import Context, VERIFY_FILE


def derive_write_authority(
    ctx: Context,
    envelope: dict[str, str],
    tasks: TaskSummary,
    construction_authorization: str,
) -> dict[str, Any]:
    """Project the current Gate B and active-task write boundaries for hooks."""

    result: dict[str, Any] = {
        "valid": False,
        "authorization_id": "NONE",
        "approved_write_roots": [],
        "exclusions": [],
        "protected_paths": [],
        "active_task": "NONE",
        "active_task_write_set": [],
    }
    if ctx.has_errors or construction_authorization == "NONE":
        return result
    try:
        roots = parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
        )
        exclusions = parse_envelope_paths(
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
        return result
    active_task = tasks.active[0] if len(tasks.active) == 1 else "NONE"
    active_write_set = (
        tasks.write_sets.get(active_task, []) if active_task != "NONE" else []
    )
    return {
        "valid": True,
        "authorization_id": construction_authorization,
        "approved_write_roots": roots,
        "exclusions": exclusions,
        "protected_paths": protected,
        "active_task": active_task,
        "active_task_write_set": active_write_set,
    }


def derive_deployment_journal_closure_authority(
    deployment_sequence: Mapping[str, Any],
    next_prompt: str,
    *,
    restricted_closure: bool,
) -> dict[str, Any]:
    """Expose only the exact local VERIFY closure operation for one attempt."""

    empty: dict[str, Any] = {
        "valid": False,
        "kind": "NONE",
        "authorization_id": "NONE",
        "mode": "BOUNDED_EVIDENCE_CLOSURE",
        "allowed_write_paths": [],
        "allowed_sections": [],
        "allowed_operations": [],
        "allowed_release_states": [],
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }
    if not restricted_closure or deployment_sequence.get("issues"):
        return empty
    status = clean_cell(deployment_sequence.get("status", ""))
    contract = {
        ("ACTION_TERMINAL_REQUIRED", "AWS-20"): (
            [AWS_DEPLOYMENT_EVIDENCE_HEADING],
            ["APPEND_ACTION_TERMINAL_ROW"],
            [],
        ),
        ("RECONCILIATION_REQUIRED", "AWS-30"): (
            [
                "bootstrap:aws-read-preflight-receipt",
                "## Action authorization provenance",
                AWS_DEPLOYMENT_EVIDENCE_HEADING,
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
                if deployment_sequence.get("basis_stale") is True
                else ["NOT_READY", "RELEASE_VERIFIED"]
            ),
        ),
        ("BLOCKED", "RELEASE-10"): (
            ["## Current release decision"],
            ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
            ["NOT_READY"],
        ),
    }.get((status, next_prompt))
    if contract is None:
        return empty
    attempt_id = clean_cell(deployment_sequence.get("attempt_id", ""))
    evidence_id = clean_cell(deployment_sequence.get("evidence_id", ""))
    if AWS_DEPLOYMENT_ATTEMPT_ID.fullmatch(attempt_id) is None:
        return empty
    if next_prompt == "RELEASE-10" and re.fullmatch(r"EV-\d{4,}", evidence_id) is None:
        return empty
    sections, operations, allowed_release_states = contract
    return {
        **empty,
        "valid": True,
        "kind": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
        "authorization_id": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
        "allowed_write_paths": [VERIFY_FILE],
        "allowed_sections": sections,
        "allowed_operations": operations,
        "allowed_release_states": allowed_release_states,
        "attempt_id": attempt_id,
        "evidence_id": evidence_id if evidence_id else "NONE",
    }


def derive_teardown_journal_closure_authority(
    teardown_sequence: Mapping[str, Any],
    next_prompt: str,
    *,
    restricted_closure: bool,
) -> dict[str, Any]:
    """Expose one exact VERIFY-only UNKNOWN closure for a lone STARTED row."""

    empty: dict[str, Any] = {
        "valid": False,
        "kind": "NONE",
        "authorization_id": "NONE",
        "mode": "BOUNDED_EVIDENCE_CLOSURE",
        "allowed_write_paths": [],
        "allowed_sections": [],
        "allowed_operations": [],
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }
    if (
        not restricted_closure
        or teardown_sequence.get("issues")
        or clean_cell(teardown_sequence.get("status", "")) != "ACTION_TERMINAL_REQUIRED"
        or next_prompt != "AWS-50"
    ):
        return empty
    attempt_id = clean_cell(teardown_sequence.get("attempt_id", ""))
    evidence_id = clean_cell(teardown_sequence.get("evidence_id", ""))
    if (
        AWS_TEARDOWN_ATTEMPT_ID.fullmatch(attempt_id) is None
        or re.fullmatch(r"EV-\d{4,}", evidence_id) is None
    ):
        return empty
    return {
        **empty,
        "valid": True,
        "kind": "AWS_TEARDOWN_JOURNAL_CLOSURE",
        "authorization_id": "AWS_TEARDOWN_JOURNAL_CLOSURE",
        "allowed_write_paths": [VERIFY_FILE],
        "allowed_sections": [AWS_TEARDOWN_EVIDENCE_HEADING],
        "allowed_operations": ["APPEND_TEARDOWN_TERMINAL_ROW"],
        "attempt_id": attempt_id,
        "evidence_id": evidence_id,
    }


def lifecycle_intent_record_boundary_is_settled(
    tasks: TaskSummary,
    release_decision: str,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> bool:
    """Return whether one local owner-intent record may be updated."""

    return bool(
        (
            tasks.terminal
            or clean_cell(deployment_sequence.get("status", "")) == "CONSUMED"
        )
        and release_lifecycle_intent_boundary_is_settled(
            release_decision, deployment_sequence
        )
        and clean_cell(teardown_sequence.get("status", ""))
        in {
            "NOT_ACTIVE",
            "STALE",
            "READY_FOR_TEARDOWN",
            "VERIFIED_CLEAN",
            "RESIDUALS_REMAIN",
        }
        and not teardown_sequence.get("issues")
    )


def derive_aws_lifecycle_intent_write_authority(
    ctx: Context,
    tasks: TaskSummary,
    release_decision: str,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
    external_authority: Mapping[str, Any],
    *,
    lifecycle_intent: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose one exact local owner-intent update and no AWS authority."""

    empty: dict[str, Any] = {
        "valid": False,
        "kind": "NONE",
        "authorization_id": "NONE",
        "mode": "BOUNDED_RELEASE_INTENT_RECORD",
        "allowed_write_paths": [],
        "allowed_sections": [],
        "allowed_operations": [],
        "allowed_values": [],
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }
    intent_value = clean_cell((lifecycle_intent or {}).get("value", "NONE"))
    teardown_status = clean_cell(teardown_sequence.get("status", "NOT_ACTIVE"))
    allowed_values = (
        ["RETAIN", "RESIDUAL_REVIEW", "TEARDOWN"]
        if teardown_status in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}
        else ["NONE", "RESIDUAL_REVIEW", "TEARDOWN"]
    )
    intent_route_active = bool(
        intent_value in {"RESIDUAL_REVIEW", "TEARDOWN"}
        and teardown_status in {"NOT_ACTIVE", "STALE"}
    )
    if (
        ctx.has_errors
        or intent_route_active
        or not lifecycle_intent_record_boundary_is_settled(
            tasks,
            release_decision,
            deployment_sequence,
            teardown_sequence,
        )
        or clean_cell(external_authority.get("validity", "NONE")) == "CURRENT"
    ):
        return empty
    return {
        **empty,
        "valid": True,
        "kind": "AWS_LIFECYCLE_INTENT_RECORD",
        "authorization_id": "AWS_LIFECYCLE_INTENT_RECORD",
        "allowed_write_paths": [VERIFY_FILE],
        "allowed_sections": ["## Current release decision"],
        "allowed_operations": ["UPDATE_AWS_LIFECYCLE_INTENT"],
        "allowed_values": allowed_values,
    }
