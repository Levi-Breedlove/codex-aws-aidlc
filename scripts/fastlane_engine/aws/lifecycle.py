"""Pure AWS lifecycle intent, routing inputs, and progress projections.

Canonical inputs are already-validated lifecycle records and immutable domain
results. Returned projections never authorize AWS access or mutation and this
module performs no I/O, routing side effect, or state write.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..core.ids import clean_cell, iso_datetime
from .models import AWS_LIFECYCLE_INTENT_SOURCE, AWS_LIFECYCLE_INTENT_VALUES


def parse_aws_lifecycle_intent_record(
    text: str | None,
) -> tuple[dict[str, Any], tuple[tuple[str, str], ...]]:
    """Validate one atomic, explicitly non-authorizing owner intent record."""

    legacy_none: dict[str, Any] = {
        "value": "NONE",
        "source": "NONE",
        "recorded_at": "NONE",
        "provenance_status": "LEGACY_NONE",
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
    }
    if text is None:
        return legacy_none, ()
    heading = "## Current release decision"
    headings = list(re.finditer(rf"^{re.escape(heading)}[ \t]*$", text, re.MULTILINE))
    if len(headings) != 1:
        return legacy_none, ()
    section = text[headings[0].end() :]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    value_lines = list(
        re.finditer(r"^- AWS lifecycle intent:\s*`([^`]+)`\s*$", section, re.MULTILINE)
    )
    source_lines = list(
        re.finditer(
            r"^- AWS lifecycle intent source:\s*`([^`]+)`\s*$",
            section,
            re.MULTILINE,
        )
    )
    recorded_lines = list(
        re.finditer(
            r"^- AWS lifecycle intent recorded at:\s*`([^`]+)`\s*$",
            section,
            re.MULTILINE,
        )
    )
    if not value_lines and not source_lines and not recorded_lines:
        return legacy_none, ()
    if (
        len(value_lines) == 1
        and value_lines[0].group(1) == "NONE"
        and not source_lines
        and not recorded_lines
    ):
        return legacy_none, ()
    exact_record = re.search(
        r"^- AWS lifecycle intent:\s*`([^`]+)`\s*\r?\n"
        r"- AWS lifecycle intent source:\s*`([^`]+)`\s*\r?\n"
        r"- AWS lifecycle intent recorded at:\s*`([^`]+)`\s*$",
        section,
        re.MULTILINE,
    )
    message = (
        "AWS lifecycle intent must be one exact ordered value/source/recorded-at triple"
    )
    if (
        len(value_lines) != 1
        or len(source_lines) != 1
        or len(recorded_lines) != 1
        or exact_record is None
    ):
        return legacy_none, (("AWS_LIFECYCLE_INTENT_PROVENANCE", message),)
    value, source, recorded_at = exact_record.groups()
    valid = value in AWS_LIFECYCLE_INTENT_VALUES
    if value == "NONE":
        valid = valid and source == "NONE" and recorded_at == "NONE"
    else:
        valid = bool(
            valid
            and AWS_LIFECYCLE_INTENT_SOURCE.fullmatch(source)
            and iso_datetime(recorded_at) is not None
        )
    if not valid:
        return legacy_none, (
            (
                "AWS_LIFECYCLE_INTENT_PROVENANCE",
                "Non-NONE AWS lifecycle intent requires an owner-message source and "
                "timezone-aware recorded-at value; NONE requires NONE provenance",
            ),
        )
    return (
        {
            "value": value,
            "source": source,
            "recorded_at": recorded_at,
            "provenance_status": "CURRENT",
            "authorizes_aws_access": False,
            "authorizes_mutation": False,
        },
        (),
    )


def derive_teardown_route(
    intent: str,
    teardown_sequence: Mapping[str, Any],
    residual_disposition: Mapping[str, Any] | None = None,
) -> tuple[str, str] | None:
    """SAFETY: route teardown intent without treating it as authority."""

    status = clean_cell(teardown_sequence.get("status", "NOT_ACTIVE"))
    if status == "ACTION_TERMINAL_REQUIRED":
        return "AWS_TEARDOWN_ACTION_TERMINAL", "AWS-50"
    if status == "POST_ACTION_REVIEW":
        return "AWS_RESIDUAL_REVIEW", "AWS-40"
    if status == "BLOCKED":
        return "AWS_RESIDUAL_REVIEW_BLOCKED", "STOP"
    disposition = residual_disposition or {}
    disposition_status = clean_cell(disposition.get("status", "NOT_APPLICABLE"))
    disposition_value = clean_cell(disposition.get("value", "NONE"))
    if status in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}:
        if disposition_status != "CURRENT":
            return "AWS_RESIDUALS_REMAIN", "STOP"
        if disposition_status == "CURRENT":
            if disposition_value == "RETAIN":
                return "AWS_RESIDUALS_RETAINED", "STOP"
            if disposition_value == "INVESTIGATE":
                return "AWS_RESIDUAL_REVIEW", "AWS-40"
            if disposition_value == "REMOVE":
                return (
                    ("WAITING_AWS_TEARDOWN_AUTH", "AWS-50")
                    if status == "READY_FOR_TEARDOWN"
                    else ("AWS_RESIDUAL_REVIEW", "AWS-40")
                )
    if intent == "NONE":
        return None
    if intent == "RESIDUAL_REVIEW":
        if status == "VERIFIED_CLEAN":
            return "AWS_RESIDUAL_REVIEW_COMPLETE", "STOP"
        return "AWS_RESIDUAL_REVIEW", "AWS-40"
    if intent == "TEARDOWN":
        if status == "VERIFIED_CLEAN":
            return (
                ("AWS_TEARDOWN_COMPLETE", "STOP")
                if teardown_sequence.get("post_action_bound") is True
                else ("AWS_RESIDUAL_REVIEW_COMPLETE", "STOP")
            )
        return "AWS_RESIDUAL_REVIEW", "AWS-40"
    return None


def derive_aws_residual_disposition(
    intent_record: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one non-authorizing residual choice to the latest AWS-40 evidence."""

    base: dict[str, Any] = {
        "status": "NOT_APPLICABLE",
        "value": "NONE",
        "basis_evidence_id": "NONE",
        "basis_status": "NONE",
        "basis_observed_at": "NONE",
        "recorded_at": clean_cell(intent_record.get("recorded_at", "NONE")),
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
        "issues": [],
    }
    basis_status = clean_cell(teardown_sequence.get("status", "NOT_ACTIVE"))
    intent = clean_cell(intent_record.get("value", "NONE"))
    if basis_status not in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}:
        if intent == "RETAIN":
            return {
                **base,
                "status": "INVALID",
                "issues": ["RETAIN requires current residual-resource evidence"],
            }
        return base
    basis_observed_at = clean_cell(teardown_sequence.get("observed_at", ""))
    basis_time = iso_datetime(basis_observed_at)
    recorded_at = clean_cell(intent_record.get("recorded_at", ""))
    record_time = iso_datetime(recorded_at)
    projection = {
        **base,
        "status": "PENDING",
        "basis_evidence_id": clean_cell(teardown_sequence.get("evidence_id", "NONE")),
        "basis_status": basis_status,
        "basis_observed_at": basis_observed_at or "NONE",
        "recorded_at": recorded_at or "NONE",
    }
    if basis_time is None:
        return {
            **projection,
            "status": "INVALID",
            "issues": ["Residual disposition basis lacks an exact observed timestamp"],
        }
    mapped = {
        "RETAIN": "RETAIN",
        "RESIDUAL_REVIEW": "INVESTIGATE",
        "TEARDOWN": "REMOVE",
    }.get(intent)
    if (
        mapped is None
        or intent_record.get("provenance_status") != "CURRENT"
        or record_time is None
    ):
        return projection
    if basis_status == "RESIDUALS_REMAIN" and record_time <= basis_time:
        return projection
    if (
        basis_status == "READY_FOR_TEARDOWN"
        and intent != "TEARDOWN"
        and record_time <= basis_time
    ):
        return projection
    return {**projection, "status": "CURRENT", "value": mapped}


def aws_deployment_teardown_sequence_conflict(
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> bool:
    """Reject simultaneous open deployment and teardown journal epochs."""

    deployment_status = clean_cell(deployment_sequence.get("status", ""))
    teardown_status = clean_cell(teardown_sequence.get("status", ""))
    deployment_open = deployment_status not in {"", "NONE", "NOT_ACTIVE", "CONSUMED"}
    teardown_open = teardown_status not in {
        "",
        "NONE",
        "NOT_ACTIVE",
        "VERIFIED_CLEAN",
        "RESIDUALS_REMAIN",
    }
    return deployment_open and teardown_open


def release_lifecycle_intent_boundary_is_settled(
    release_decision: str, deployment_sequence: Mapping[str, Any]
) -> bool:
    """Allow elective post-release intent only at an auditable boundary."""

    deployment_status = clean_cell(deployment_sequence.get("status", ""))
    return bool(
        not deployment_sequence.get("issues")
        and (
            (
                release_decision == "RELEASE_VERIFIED"
                and deployment_status in {"NOT_ACTIVE", "CONSUMED"}
            )
            or (release_decision == "NOT_READY" and deployment_status == "CONSUMED")
        )
    )


def aws_lifecycle_intent_route_is_eligible(
    intent: str,
    lifecycle_state: str,
    release_decision: str,
    tasks: Any,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> bool:
    """Return whether elective owner intent may enter AWS-40 now."""

    return bool(
        intent in {"RESIDUAL_REVIEW", "TEARDOWN"}
        and (
            lifecycle_state in {"RELEASE_REVIEW", "RELEASE_VERIFIED"}
            or clean_cell(deployment_sequence.get("status", "")) == "CONSUMED"
        )
        and (
            tasks.terminal
            or clean_cell(deployment_sequence.get("status", "")) == "CONSUMED"
        )
        and release_lifecycle_intent_boundary_is_settled(
            release_decision, deployment_sequence
        )
        and clean_cell(teardown_sequence.get("status", ""))
        not in {"ACTION_TERMINAL_REQUIRED", "POST_ACTION_REVIEW"}
        and not teardown_sequence.get("issues")
    )


def derive_aws_delivery_route(
    release_decision: str,
    aws_execution: Mapping[str, Any],
    deployment_sequence: Mapping[str, Any],
    lane: str | None,
    release_evidence_cutoff: str = "NONE",
) -> tuple[str, str] | None:
    """SAFETY: route a release without inferring an attempted AWS action."""

    deployment_status = clean_cell(deployment_sequence.get("status", ""))
    if deployment_sequence.get("issues"):
        return "BLOCKED", "STOP"
    if deployment_status == "ACTION_TERMINAL_REQUIRED":
        return "AWS_DEPLOYMENT_ACTION_TERMINAL", "AWS-20"
    if deployment_status == "RECONCILIATION_REQUIRED":
        return "AWS_DEPLOYMENT_RECONCILIATION", "AWS-30"
    if deployment_status in {"RECONCILED", "BLOCKED"}:
        terminal_evidence = clean_cell(deployment_sequence.get("evidence_id", ""))
        if release_evidence_cutoff != terminal_evidence:
            return "RELEASE_REVIEW", "RELEASE-10"
    if deployment_status == "CONSUMED":
        if release_decision == "NOT_READY":
            return "RELEASE_REVIEW_BLOCKED", "STOP"
        if release_decision != "READY_TO_DEPLOY":
            return None
        if (
            clean_cell(deployment_sequence.get("current_mutation_authority_status", ""))
            == "UNAVAILABLE"
        ):
            return None
    if release_decision != "READY_TO_DEPLOY":
        return None
    progress_state = clean_cell(aws_execution.get("progress_state", ""))
    if progress_state == "WAITING_AWS_MUTATION_AUTH":
        return "WAITING_AWS_MUTATION_AUTH", "AWS-20"
    if progress_state == "AWS_PREFLIGHT_READY":
        return "AWS_PREFLIGHT_READY", "STOP"
    return progress_state or "AWS_PREFLIGHT_REQUIRED", "AWS-10"


def derive_aws_execution_projection(
    materiality: Mapping[str, Any],
    *,
    release_decision: str,
    guidance_ready: bool,
    read_authority: Mapping[str, Any] | None,
    preflight: Mapping[str, Any],
    lane: str | None = None,
) -> dict[str, Any]:
    """SAFETY: project AWS state without granting or extending authority."""

    active = release_decision == "READY_TO_DEPLOY"
    preflight_projection = dict(preflight)
    read_scope_current = bool(
        read_authority is not None and read_authority.get("validity") == "CURRENT"
    )
    if not active:
        progress = "NOT_ACTIVE"
    elif lane == "documentation-only" and guidance_ready:
        progress = "AWS_PREFLIGHT_READY"
        preflight_projection.update(
            {
                "status": "NOT_APPLICABLE",
                "account": "NONE",
                "region": "NONE",
                "environment": "NONE",
                "account_access": "NOT_USED",
                "issues": [],
            }
        )
    elif not guidance_ready:
        progress = "AWS_GUIDANCE_REQUIRED"
    elif not read_scope_current:
        progress = "AWS_READ_SCOPE_REQUIRED"
    elif preflight.get("status") != "READY":
        progress = "AWS_PREFLIGHT_RUNNING"
    elif lane in {"fast-dev", "explicit-gate"}:
        progress = "WAITING_AWS_MUTATION_AUTH"
    else:
        progress = "AWS_PREFLIGHT_READY"
    completed: list[str] = []
    if active:
        if guidance_ready:
            completed.append("AWS_GUIDANCE_REQUIRED")
        if read_scope_current:
            completed.append("AWS_READ_SCOPE_REQUIRED")
        if preflight.get("status") in {"RUNNING", "READY"}:
            completed.append("AWS_PREFLIGHT_RUNNING")
        if preflight.get("status") == "READY" or (
            lane == "documentation-only" and guidance_ready
        ):
            completed.append("AWS_PREFLIGHT_READY")
    return {
        "schema_version": 1,
        "active": active,
        "lane": lane or "NONE",
        "requirements_materiality": dict(materiality),
        "guidance": {
            "status": "CURRENT" if guidance_ready else "REQUIRED",
        },
        "read_scope": {
            "status": (
                "NOT_APPLICABLE"
                if lane == "documentation-only"
                else "CURRENT"
                if read_scope_current
                else "REQUIRED"
            ),
            "authorization_id": (
                read_authority.get("authorization_id", "NONE")
                if read_scope_current and read_authority is not None
                else "NONE"
            ),
        },
        "preflight": preflight_projection,
        "completed_states": completed,
        "progress_state": progress,
    }


__all__ = (
    "aws_deployment_teardown_sequence_conflict",
    "aws_lifecycle_intent_route_is_eligible",
    "derive_aws_delivery_route",
    "derive_aws_execution_projection",
    "derive_aws_residual_disposition",
    "derive_teardown_route",
    "parse_aws_lifecycle_intent_record",
    "release_lifecycle_intent_boundary_is_settled",
)
