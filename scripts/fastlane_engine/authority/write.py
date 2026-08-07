"""Deterministic repository-ledger write authority projections.

Canonical inputs are immutable normalized task, lifecycle, and journal facts.
Returns exact repository write allowances only. Side effects are prohibited;
this module never parses a lifecycle-domain record, writes a ledger, or executes
an external action.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..core.ids import clean_cell
from .models import (
    AWS_DEPLOYMENT_ATTEMPT_ID,
    AWS_TEARDOWN_ATTEMPT_ID,
    ConstructionWriteInput,
    LifecycleIntentWriteInput,
)

VERIFY_FILE = "docs/project/VERIFY.md"
AWS_DEPLOYMENT_EVIDENCE_HEADING = "## AWS deployment action and reconciliation evidence"
AWS_TEARDOWN_EVIDENCE_HEADING = "## Teardown reconciliation evidence"


def derive_write_authority(
    write_input: ConstructionWriteInput,
    construction_authorization: str,
) -> dict[str, Any]:
    """Project current Gate B and active-task write boundaries for hooks."""

    result: dict[str, Any] = {
        "valid": False,
        "authorization_id": "NONE",
        "approved_write_roots": [],
        "exclusions": [],
        "protected_paths": [],
        "active_task": "NONE",
        "active_task_write_set": [],
    }
    if write_input.has_errors or construction_authorization == "NONE":
        return result
    return {
        **result,
        "valid": True,
        "authorization_id": construction_authorization,
        "approved_write_roots": list(write_input.approved_write_roots),
        "exclusions": list(write_input.exclusions),
        "protected_paths": list(write_input.protected_paths),
        "active_task": write_input.active_task or "NONE",
        "active_task_write_set": list(write_input.active_task_write_set),
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
    write_input: LifecycleIntentWriteInput,
) -> bool:
    """Return whether one local owner-intent record may be updated."""

    return bool(
        (write_input.tasks_terminal or write_input.deployment_status == "CONSUMED")
        and write_input.deployment_boundary_settled
        and write_input.teardown_status
        in {
            "NOT_ACTIVE",
            "STALE",
            "READY_FOR_TEARDOWN",
            "VERIFIED_CLEAN",
            "RESIDUALS_REMAIN",
        }
        and not write_input.teardown_has_issues
    )


def derive_aws_lifecycle_intent_write_authority(
    write_input: LifecycleIntentWriteInput,
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
    allowed_values = (
        ["RETAIN", "RESIDUAL_REVIEW", "TEARDOWN"]
        if write_input.teardown_status in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}
        else ["NONE", "RESIDUAL_REVIEW", "TEARDOWN"]
    )
    intent_route_active = bool(
        write_input.intent_value in {"RESIDUAL_REVIEW", "TEARDOWN"}
        and write_input.teardown_status in {"NOT_ACTIVE", "STALE"}
    )
    if (
        write_input.has_errors
        or intent_route_active
        or not lifecycle_intent_record_boundary_is_settled(write_input)
        or write_input.external_authority_current
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
