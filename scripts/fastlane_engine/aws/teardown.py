"""Pure AWS residual-review and teardown state machine.

Canonical input is the append-only VERIFY journal plus explicit current design
and authority projections. The evaluator performs no AWS call, file read, or
state write and cannot broaden deletion authority. The cohesive chronology is
kept together to preserve fail-closed replay and diagnostic ordering.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Mapping

from ..core.ids import (
    clean_cell,
    explicit_timestamp,
    explicit_value,
    iso_datetime,
    unresolved,
)
from .evidence import parse_teardown_reconciliation_evidence
from .models import (
    AWS_READ_AUTHORIZATION_ID,
    AWS_TEARDOWN_ACTION_STATUSES,
    AWS_TEARDOWN_ATTEMPT_ID,
    AWS_TEARDOWN_EVIDENCE_HEADERS,
    AWS_TEARDOWN_PRECALL_RESULT,
    AWS_TEARDOWN_READ_PROVENANCE,
    AWS_TEARDOWN_RECEIPT_FIELDS,
    AWS_TEARDOWN_REVIEW_STATUSES,
    AWS_TEARDOWN_TERMINAL_STATUSES,
    AwsAuthorityPolicy,
)


def _teardown_values(
    policy: AwsAuthorityPolicy, value: str, label: str, *, allow_none: bool
) -> list[str]:
    cleaned = clean_cell(value)
    if allow_none and cleaned == "NONE":
        return []
    values = policy.split_authority_values(cleaned)
    if (
        not values
        or len(values) != len(set(values))
        or any("*" in item for item in values)
    ):
        raise ValueError(f"{label} must be a unique wildcard-free exact list")
    return values


def _teardown_receipt_row_issues(
    policy: AwsAuthorityPolicy,
    row: Mapping[str, str],
    verify_text: str,
    *,
    construction_authorization: str,
    envelope: Mapping[str, str],
    require_row_role_match: bool = True,
    historical: bool = False,
) -> tuple[dict[str, str] | None, str, list[str]]:
    """Validate one evidence row against the exact current teardown receipt."""

    try:
        receipt = policy.marked_receipt(verify_text, "aws-teardown")
    except ValueError:
        receipt = ""
    fields = policy.exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS TEARDOWN",
        AWS_TEARDOWN_RECEIPT_FIELDS,
        allow_none_fields=frozenset(
            {"Resources and data to retain", "Shared dependencies"}
        ),
    )
    provenance = policy.action_authorization_rows(verify_text).get("Teardown")
    digest = (
        "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        if receipt
        else "NONE"
    )
    issues: list[str] = []
    if fields is None or provenance is None or unresolved(receipt):
        return (
            None,
            digest,
            ["evidence requires one exact owner-authored teardown receipt"],
        )
    action_authorization = clean_cell(row.get("Teardown authorization", ""))
    action_digest = clean_cell(row.get("Teardown receipt digest", ""))
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    if (
        action_authorization != fields["Teardown authorization"]
        or action_digest != digest
        or fields["Construction authorization"] != construction_authorization
        or (
            require_row_role_match
            and fields["Profile or role"] != clean_cell(row.get("Role or profile", ""))
        )
        or fields["Stack, application, and resources to remove"]
        != clean_cell(row.get("Resources proposed to remove", ""))
        or fields["Resources and data to retain"]
        != clean_cell(row.get("Resources retained", ""))
        or fields["Allowed deletion operations"]
        != clean_cell(row.get("Allowed deletion operations", ""))
        or fields["Shared dependencies"]
        != clean_cell(row.get("Shared dependencies", ""))
        or fields["Cost effect"] != clean_cell(row.get("Cost effect", ""))
        or fields["Post-teardown verification"]
        != clean_cell(row.get("Post-teardown verification", ""))
        or clean_cell(row.get("Account / Region / environment", "")) != expected_scope
        or (
            not historical
            and not policy.receipt_identity_matches_gate_b(fields, envelope)
        )
        or provenance.get("Authorization ID") != action_authorization
        or provenance.get("Construction AUTH") != construction_authorization
        or provenance.get("Role or profile") != fields["Profile or role"]
        or provenance.get("Account / Region / environment") != expected_scope
        or provenance.get("Approver") != fields["Approver"]
        or not policy.explicit_human_approver(fields["Approver"])
        or clean_cell(provenance.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(provenance.get("Stable owner-message source", ""))
        or not explicit_timestamp(provenance.get("Observed at", ""))
        or clean_cell(provenance.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or clean_cell(provenance.get("Result", ""))
        not in {"AUTHORIZED", "RUNNING", "READY"}
    ):
        issues.append("evidence does not bind the exact teardown receipt")
    return fields, digest, issues


def _teardown_action_attempt_row_issues(
    policy: AwsAuthorityPolicy,
    row: Mapping[str, str],
    envelope: Mapping[str, str],
    *,
    historical: bool = False,
) -> list[str]:
    """SAFETY: validate one direct AWS-50 STARTED or terminal journal row."""

    issues: list[str] = []
    status = clean_cell(row.get("Status", ""))
    if status not in AWS_TEARDOWN_ACTION_STATUSES:
        return ["matching AWS-50 attempt has an invalid action status"]
    try:
        resources = _teardown_values(
            policy,
            row.get("Resources proposed to remove", ""),
            "Resources proposed to remove",
            allow_none=False,
        )
        operations = _teardown_values(
            policy,
            row.get("Allowed deletion operations", ""),
            "Allowed deletion operations",
            allow_none=False,
        )
        retained = _teardown_values(
            policy,
            row.get("Resources retained", ""),
            "Resources retained",
            allow_none=True,
        )
        shared = _teardown_values(
            policy,
            row.get("Shared dependencies", ""),
            "Shared dependencies",
            allow_none=True,
        )
        removed = _teardown_values(
            policy,
            row.get("Resources removed", ""),
            "Resources removed",
            allow_none=True,
        )
        residuals = _teardown_values(
            policy,
            row.get("Residual resources", ""),
            "Residual resources",
            allow_none=True,
        )
    except ValueError as exc:
        return [str(exc)]
    if not historical and not policy.receipt_scope_within_gate_b(
        resources, operations, envelope
    ):
        issues.append("matching AWS-50 attempt exceeds Gate B")
    if (
        set(resources).intersection(retained)
        or set(resources).intersection(shared)
        or set(retained).intersection(shared)
    ):
        issues.append("matching AWS-50 removal, retention, and shared sets overlap")
    for field_name, allow_none in (
        ("Expected manifest or stack", False),
        ("Cost effect", False),
        ("Post-teardown verification", False),
        ("Stack events and terminal status", False),
        ("Resources removed", True),
        ("Snapshots and backups", True),
        ("Residual resources", True),
        ("Inventory or discovery limits", False),
    ):
        if not explicit_value(row.get(field_name, ""), allow_none=allow_none):
            issues.append(f"matching AWS-50 attempt requires {field_name}")
    if clean_cell(row.get("Identity and boundary match", "")) not in {
        "PASS",
        "VERIFIED",
    }:
        issues.append("matching AWS-50 attempt requires verified identity and boundary")
    direct_fields = (
        "Stack events and terminal status",
        "Resources removed",
        "Snapshots and backups",
        "Residual resources",
        "Inventory or discovery limits",
    )
    if status == "STARTED":
        if (
            clean_cell(row.get("Stack events and terminal status", ""))
            != AWS_TEARDOWN_PRECALL_RESULT
        ):
            issues.append("AWS-50 STARTED must use the exact pre-call sentinel")
        if (
            clean_cell(row.get("Inventory or discovery limits", ""))
            != AWS_TEARDOWN_PRECALL_RESULT
        ):
            issues.append(
                "AWS-50 STARTED inventory must use the exact pre-call sentinel"
            )
        for field_name in (
            "Resources removed",
            "Snapshots and backups",
            "Residual resources",
        ):
            if clean_cell(row.get(field_name, "")) != "NONE":
                issues.append(f"AWS-50 STARTED must use {field_name} = NONE")
        return issues
    if any(
        clean_cell(row.get(field_name, "")) == AWS_TEARDOWN_PRECALL_RESULT
        for field_name in direct_fields
    ):
        issues.append("AWS-50 terminal evidence cannot reuse the pre-call sentinel")
    if status == "SUCCEEDED":
        if residuals:
            issues.append("matching SUCCEEDED AWS-50 attempt cannot retain residuals")
        if set(removed) != set(resources):
            issues.append(
                "matching SUCCEEDED AWS-50 attempt must reconcile every removal"
            )
    return issues


def _teardown_basis_authorization(row: Mapping[str, str]) -> str | None:
    parts = [
        clean_cell(item)
        for item in clean_cell(row.get("REQ / DES / AUTH", "")).split(" / ")
    ]
    if (
        len(parts) != 3
        or re.fullmatch(r"REQ-\d{4,}", parts[0]) is None
        or re.fullmatch(r"DES-\d{4,}", parts[1]) is None
        or re.fullmatch(r"AUTH-\d{4,}", parts[2]) is None
    ):
        return None
    return parts[2]


def _teardown_attempt_timing_issues(
    started: Mapping[str, str], fields: Mapping[str, str], provenance: Mapping[str, str]
) -> list[str]:
    """Prove the one-operation receipt was current when STARTED was appended."""

    issues: list[str] = []
    started_at = iso_datetime(started.get("Observed at", ""))
    authorized_at = iso_datetime(provenance.get("Observed at", ""))
    valid_until = clean_cell(fields.get("Valid until", ""))
    expires_at = None if valid_until == "ONE_OPERATION" else iso_datetime(valid_until)
    if started_at is None:
        issues.append("teardown STARTED timestamp is invalid")
    if authorized_at is None:
        issues.append("teardown authorization timestamp is invalid")
    elif started_at is not None and started_at < authorized_at:
        issues.append("teardown STARTED precedes its authorization provenance")
    if valid_until != "ONE_OPERATION" and expires_at is None:
        issues.append("teardown authority has a noncanonical validity boundary")
    elif started_at is not None and expires_at is not None and started_at > expires_at:
        issues.append("teardown STARTED occurred after authority expiry")
    return issues


def _teardown_read_row_issues(
    policy: AwsAuthorityPolicy,
    row: Mapping[str, str],
    authority: Mapping[str, Any] | None,
    *,
    require_authority: bool,
    require_exact_scope: bool = False,
) -> list[str]:
    """SAFETY: validate AWS-40 read provenance without reviving authority."""

    evidence_id = clean_cell(row.get("Evidence ID", "")) or "AWS-40 row"
    read_id = clean_cell(row.get("Read authorization", ""))
    read_role = clean_cell(row.get("Read role or profile", ""))
    read_digest = clean_cell(row.get("Read receipt digest", ""))
    read_valid_until = clean_cell(row.get("Read valid until", ""))
    read_source_proof = clean_cell(row.get("Read authority source", ""))
    source_match = AWS_TEARDOWN_READ_PROVENANCE.fullmatch(read_source_proof)
    read_source = clean_cell(source_match.group("source")) if source_match else ""
    read_authorized_at_value = (
        clean_cell(source_match.group("authorized_at")) if source_match else ""
    )
    observed_at = iso_datetime(row.get("Observed at", ""))
    read_authorized_at = iso_datetime(read_authorized_at_value)
    expires_at = iso_datetime(read_valid_until)
    issues: list[str] = []
    if AWS_READ_AUTHORIZATION_ID.fullmatch(read_id) is None:
        issues.append(f"{evidence_id} AWS-40 requires a canonical read authorization")
    if not explicit_value(read_role, allow_none=False) or "*" in read_role:
        issues.append(f"{evidence_id} AWS-40 requires a concrete read role")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", read_digest) is None:
        issues.append(f"{evidence_id} AWS-40 requires an exact read receipt digest")
    if read_valid_until == "ONE_OPERATION" or expires_at is None:
        issues.append(f"{evidence_id} AWS-40 requires reusable ISO read validity")
    elif observed_at is not None and observed_at > expires_at:
        issues.append(f"{evidence_id} AWS-40 was observed after read authority expiry")
    if (
        source_match is None
        or not explicit_value(read_source, allow_none=False)
        or "*" in read_source
        or read_authorized_at is None
    ):
        issues.append(
            f"{evidence_id} AWS-40 requires a durable read authority source "
            "and ISO authorization timestamp"
        )
    elif observed_at is not None and observed_at < read_authorized_at:
        issues.append(f"{evidence_id} AWS-40 observation precedes read authorization")
    if authority is None:
        if require_authority:
            issues.append(
                f"{evidence_id} AWS-40 requires its exact current read receipt"
            )
        return issues

    expected_scope = (
        f"ACCOUNT: {authority.get('account')}; REGION: {authority.get('region')}; "
        f"ENVIRONMENT: {authority.get('environment')}"
    )
    if read_id != clean_cell(authority.get("authorization_id", "")):
        issues.append(
            f"{evidence_id} read authorization does not match current authority"
        )
    if read_role != clean_cell(authority.get("role_or_profile", "")):
        issues.append(f"{evidence_id} read role does not match its receipt")
    if read_digest != clean_cell(authority.get("receipt_digest", "")):
        issues.append(f"{evidence_id} read receipt digest is tampered")
    if read_valid_until != clean_cell(authority.get("expiration", "")):
        issues.append(f"{evidence_id} read validity is tampered")
    if read_source != clean_cell(authority.get("authority_source", "")):
        issues.append(f"{evidence_id} read authority source is tampered")
    if read_authorized_at_value != clean_cell(authority.get("authorized_at", "")):
        issues.append(f"{evidence_id} read authorization timestamp is tampered")
    if clean_cell(row.get("Account / Region / environment", "")) != expected_scope:
        issues.append(f"{evidence_id} read account boundary is stale")
    authority_authorized_at = iso_datetime(authority.get("authorized_at", ""))
    if authority_authorized_at is None:
        issues.append(f"{evidence_id} read authorization timestamp is invalid")
    elif observed_at is not None and observed_at < authority_authorized_at:
        issues.append(f"{evidence_id} AWS-40 observation precedes read authorization")
    try:
        observed_resources: set[str] = set()
        for field_name in (
            "Resources proposed to remove",
            "Resources retained",
            "Shared dependencies",
            "Residual resources",
        ):
            observed_resources.update(
                _teardown_values(
                    policy, row.get(field_name, ""), field_name, allow_none=True
                )
            )
        observed_operations = _teardown_values(
            policy,
            row.get("Post-teardown verification", ""),
            "Post-teardown verification",
            allow_none=clean_cell(row.get("Status", ""))
            in {"RUNNING", "BLOCKED", "STALE"},
        )
    except ValueError as exc:
        issues.append(str(exc))
        observed_resources, observed_operations = set(), []
    authorized_resources = set(authority.get("resources", []))
    authorized_operations = set(authority.get("operations", []))
    if require_exact_scope and observed_resources != authorized_resources:
        issues.append(f"{evidence_id} recorded resources do not match exact read scope")
    elif observed_resources and not observed_resources.issubset(authorized_resources):
        issues.append(f"{evidence_id} observed resources exceed read scope")
    if require_exact_scope and set(observed_operations) != authorized_operations:
        issues.append(
            f"{evidence_id} recorded operations do not match exact read scope"
        )
    elif observed_operations and not set(observed_operations).issubset(
        authorized_operations
    ):
        issues.append(f"{evidence_id} observed operations exceed read scope")
    return issues


def derive_teardown_sequence_state(
    verify_text: str,
    read_authority: Mapping[str, Any] | None,
    *,
    policy: AwsAuthorityPolicy,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    envelope: Mapping[str, str],
    restricted_closure: bool = False,
    cost_posture: str = "",
    active_artifact: str = "",
) -> dict[str, Any]:
    """SAFETY: derive AWS-40/AWS-50 sequencing without replay authority."""

    base: dict[str, Any] = {
        "status": "NOT_ACTIVE",
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "observed_at": "NONE",
        "ready_evidence_id": "NONE",
        "read_authorization": "NONE",
        "read_role_or_profile": "NONE",
        "read_receipt_digest": "NONE",
        "read_valid_until": "NONE",
        "read_authority_source": "NONE",
        "expected_manifest_or_stack": "NONE",
        "account": "NONE",
        "region": "NONE",
        "environment": "NONE",
        "phase": "NONE",
        "action_status": "NONE",
        "review_status": "NONE",
        "issues": [],
        "resources_to_remove": [],
        "allowed_operations": [],
        "resources_to_retain": [],
        "shared_dependencies": [],
        "resources_removed": [],
        "residual_resources": [],
        "cost_effect": "NONE",
        "post_action_verification": "NONE",
        "terminal_status": "NONE",
        "snapshots_and_backups": "NONE",
        "inventory_limits": "NONE",
        "identity_and_boundary_match": "NONE",
        "teardown_authorization": "NONE",
        "teardown_receipt_digest": "NONE",
        "blocker_or_stale_reason": "NONE",
        "basis_stale": False,
        "post_action_bound": False,
        "current_mutation_authority_status": "UNAVAILABLE",
        "reconciliation_read_authority": {},
    }
    try:
        rows = parse_teardown_reconciliation_evidence(verify_text)
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    concrete: list[dict[str, str]] = []
    invalid_identifiers: list[str] = []
    for row in rows:
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id):
            concrete.append({key: clean_cell(value) for key, value in row.items()})
            continue
        status = clean_cell(row.get("Status", ""))
        placeholder = (
            unresolved(evidence_id)
            and status in {"", "NOT_STARTED"}
            and all(
                unresolved(row.get(header, ""))
                for header in AWS_TEARDOWN_EVIDENCE_HEADERS
                if header not in {"Evidence ID", "Status"}
            )
        )
        if not placeholder:
            invalid_identifiers.append(evidence_id or "EMPTY")
    if invalid_identifiers:
        return {
            **base,
            "status": "BLOCKED",
            "issues": [
                "Teardown reconciliation evidence has noncanonical or partially "
                "populated IDs: " + ", ".join(sorted(invalid_identifiers))
            ],
        }
    if not concrete:
        return base
    identifiers = [row["Evidence ID"] for row in concrete]
    structural_issues: list[str] = []
    if len(identifiers) != len(set(identifiers)):
        structural_issues.append(
            "Teardown reconciliation evidence contains duplicate IDs"
        )
    timestamps: list[datetime] = []
    attempts: dict[str, list[dict[str, str]]] = {}
    attempt_order: list[str] = []
    closed_attempts: set[str] = set()
    active_attempt = ""
    for row in concrete:
        evidence_id = row["Evidence ID"]
        attempt_id = row.get("Attempt ID", "")
        phase = row.get("Phase", "")
        status = row.get("Status", "")
        observed_at = iso_datetime(row.get("Observed at", ""))
        if phase == "AWS-40":
            if status not in AWS_TEARDOWN_REVIEW_STATUSES:
                structural_issues.append(
                    f"{evidence_id} has invalid AWS-40 status {status or 'EMPTY'}"
                )
            if (
                attempt_id != "NONE"
                and AWS_TEARDOWN_ATTEMPT_ID.fullmatch(attempt_id) is None
            ):
                structural_issues.append(f"{evidence_id} has a noncanonical Attempt ID")
            structural_issues.extend(
                _teardown_read_row_issues(policy, row, None, require_authority=False)
            )
        elif phase == "AWS-50":
            if status not in AWS_TEARDOWN_ACTION_STATUSES:
                structural_issues.append(
                    f"{evidence_id} has invalid AWS-50 status {status or 'EMPTY'}"
                )
            if AWS_TEARDOWN_ATTEMPT_ID.fullmatch(attempt_id) is None:
                structural_issues.append(f"{evidence_id} has a noncanonical Attempt ID")
        else:
            structural_issues.append(
                f"{evidence_id} phase must be exactly AWS-40 or AWS-50"
            )
        if observed_at is None:
            structural_issues.append(
                f"{evidence_id} Observed at must be ISO 8601 with timezone"
            )
        else:
            timestamps.append(observed_at)
        if not explicit_value(row.get("Durable source", ""), allow_none=False):
            structural_issues.append(f"{evidence_id} requires a durable source")
        blocker_reason = row.get("Blocker or stale reason", "")
        if phase == "AWS-40" and status in {"BLOCKED", "STALE"}:
            if not explicit_value(blocker_reason, allow_none=False):
                structural_issues.append(
                    f"{evidence_id} requires an exact blocker or stale reason"
                )
        elif blocker_reason != "NONE":
            structural_issues.append(
                f"{evidence_id} must use Blocker or stale reason = NONE"
            )
        if attempt_id != "NONE":
            if attempt_id != active_attempt:
                if attempt_id in closed_attempts:
                    structural_issues.append(
                        f"{evidence_id} reopens a noncontiguous teardown attempt"
                    )
                if active_attempt:
                    closed_attempts.add(active_attempt)
                active_attempt = attempt_id
                attempt_order.append(attempt_id)
            attempts.setdefault(attempt_id, []).append(row)
        elif phase == "AWS-50":
            structural_issues.append(
                f"{evidence_id} AWS-50 requires a canonical Attempt ID"
            )
        elif active_attempt:
            active_rows = attempts.get(active_attempt, [])
            active_has_terminal_review = any(
                item.get("Phase") == "AWS-40"
                and item.get("Status")
                in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
                for item in active_rows
            )
            if phase == "AWS-40" and not active_has_terminal_review:
                structural_issues.append(
                    f"{evidence_id} AWS-40 cannot erase active teardown attempt "
                    f"binding {active_attempt}"
                )
            closed_attempts.add(active_attempt)
            active_attempt = ""
    if len(timestamps) != len(set(timestamps)):
        structural_issues.append(
            "Teardown reconciliation evidence timestamps must be unique"
        )
    if len(timestamps) == len(concrete) and timestamps != sorted(timestamps):
        structural_issues.append(
            "Teardown reconciliation evidence must be appended in observed-time order"
        )
    replayed_authorizations: set[str] = set()
    replayed_digests: set[str] = set()
    for index, attempt_id in enumerate(attempt_order):
        group = attempts[attempt_id]
        starts = [
            row
            for row in group
            if row.get("Phase") == "AWS-50" and row.get("Status") == "STARTED"
        ]
        terminals = [
            row
            for row in group
            if row.get("Phase") == "AWS-50"
            and row.get("Status") in AWS_TEARDOWN_TERMINAL_STATUSES
        ]
        reviews = [row for row in group if row.get("Phase") == "AWS-40"]
        if len(starts) != 1 or group[0] not in starts:
            structural_issues.append(
                f"{attempt_id} requires exactly one first AWS-50 STARTED row"
            )
        if len(terminals) > 1:
            structural_issues.append(
                f"{attempt_id} has more than one AWS-50 terminal row"
            )
        if terminals and group.index(terminals[0]) != 1:
            structural_issues.append(
                f"{attempt_id} AWS-50 terminal row must immediately follow STARTED"
            )
        if reviews and len(terminals) != 1:
            structural_issues.append(
                f"{attempt_id} AWS-40 requires one prior AWS-50 terminal row"
            )
        if (
            reviews
            and terminals
            and any(group.index(row) < group.index(terminals[0]) for row in reviews)
        ):
            structural_issues.append(
                f"{attempt_id} AWS-40 must follow the AWS-50 terminal row"
            )
        if len(reviews) > 2:
            structural_issues.append(
                f"{attempt_id} exceeds the bounded AWS-40 retry sequence"
            )
        if (
            len(reviews) == 2
            and reviews[0].get("Status") == "STALE"
            and reviews[0].get("Read authorization")
            == reviews[1].get("Read authorization")
        ):
            structural_issues.append(
                f"{attempt_id} AWS-40 recovery requires fresh read authority"
            )
        if len(reviews) == 2 and (
            reviews[0].get("Status") not in {"RUNNING", "STALE"}
            or reviews[1].get("Status")
            not in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
        ):
            structural_issues.append(
                f"{attempt_id} AWS-40 recovery must be RUNNING or STALE then terminal"
            )
        immutable_fields = (
            "REQ / DES / AUTH",
            "Read authorization",
            "Read role or profile",
            "Read receipt digest",
            "Read valid until",
            "Read authority source",
            "Teardown authorization",
            "Teardown receipt digest",
            "Role or profile",
            "Expected manifest or stack",
            "Resources proposed to remove",
            "Allowed deletion operations",
            "Resources retained",
            "Shared dependencies",
            "Cost effect",
            "Post-teardown verification",
            "Account / Region / environment",
        )
        action_rows = [row for row in group if row.get("Phase") == "AWS-50"]
        if action_rows:
            first = action_rows[0]
            for row in action_rows[1:]:
                for field_name in immutable_fields:
                    if row.get(field_name) != first.get(field_name):
                        structural_issues.append(
                            f"{attempt_id} changes immutable {field_name}"
                        )
        authority_row = starts[0] if starts else group[0]
        authorization_id = authority_row.get("Teardown authorization", "")
        receipt_digest = authority_row.get("Teardown receipt digest", "")
        if authorization_id in replayed_authorizations:
            structural_issues.append(
                f"{attempt_id} replays a teardown authorization ID"
            )
        replayed_authorizations.add(authorization_id)
        if receipt_digest in replayed_digests:
            structural_issues.append(f"{attempt_id} replays a teardown receipt digest")
        replayed_digests.add(receipt_digest)
        if index < len(attempt_order) - 1:
            terminal_reviews = [
                row
                for row in reviews
                if row.get("Status")
                in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
            ]
            if len(terminals) != 1 or len(terminal_reviews) != 1:
                structural_issues.append(
                    f"{attempt_id} was not reconciled before the next teardown attempt"
                )
    if structural_issues:
        return {**base, "status": "BLOCKED", "issues": structural_issues}

    expected_basis = (
        f"{requirements_revision} / {design_revision} / {construction_authorization}"
    )
    current_read = bool(
        read_authority is not None and read_authority.get("validity") == "CURRENT"
    )
    selected_attempt_id = clean_cell(concrete[-1].get("Attempt ID", ""))
    if selected_attempt_id != "NONE":
        if selected_attempt_id not in attempts:
            return {
                **base,
                "status": "BLOCKED",
                "issues": ["Latest teardown epoch is malformed"],
            }
        attempt_id = selected_attempt_id
        group = attempts[attempt_id]
        started = group[0]
        terminal = next(
            (
                row
                for row in group
                if row.get("Phase") == "AWS-50"
                and row.get("Status") in AWS_TEARDOWN_TERMINAL_STATUSES
            ),
            None,
        )
        reviews = [row for row in group if row.get("Phase") == "AWS-40"]
        latest = reviews[-1] if reviews else terminal or started
        group_basis = started.get("REQ / DES / AUTH", "")
        basis_authorization = _teardown_basis_authorization(started)
        basis_stale = group_basis != expected_basis
        historical = (
            restricted_closure or basis_stale or construction_authorization == "NONE"
        )
        issues: list[str] = []
        if basis_authorization is None:
            issues.append(f"{attempt_id} has a noncanonical REQ / DES / AUTH basis")
        started_index = concrete.index(started)
        ready = concrete[started_index - 1] if started_index > 0 else None
        if not (
            ready is not None
            and ready.get("Phase") == "AWS-40"
            and ready.get("Attempt ID") == "NONE"
            and ready.get("Status") == "READY_FOR_TEARDOWN"
        ):
            issues.append(
                f"{attempt_id} must immediately follow the latest READY_FOR_TEARDOWN evidence"
            )
            ready = None
        else:
            for field_name in (
                "REQ / DES / AUTH",
                "Read authorization",
                "Read role or profile",
                "Read receipt digest",
                "Read valid until",
                "Read authority source",
                "Role or profile",
                "Expected manifest or stack",
                "Resources proposed to remove",
                "Allowed deletion operations",
                "Resources retained",
                "Shared dependencies",
                "Cost effect",
                "Post-teardown verification",
                "Account / Region / environment",
            ):
                if ready.get(field_name) != started.get(field_name):
                    issues.append(
                        f"{attempt_id} does not match READY_FOR_TEARDOWN {field_name}"
                    )
            issues.extend(
                _teardown_read_row_issues(policy, ready, None, require_authority=False)
            )
        if basis_authorization is not None:
            fields, digest, receipt_issues = _teardown_receipt_row_issues(
                policy,
                started,
                verify_text,
                construction_authorization=basis_authorization,
                envelope=envelope,
                historical=historical,
            )
            issues.extend(receipt_issues)
            provenance = policy.action_authorization_rows(verify_text).get("Teardown")
            if fields is not None and provenance is not None:
                issues.extend(
                    _teardown_attempt_timing_issues(started, fields, provenance)
                )
            if digest != started.get("Teardown receipt digest"):
                issues.append(f"{attempt_id} has a stale teardown receipt digest")
        issues.extend(
            _teardown_action_attempt_row_issues(
                policy, started, envelope, historical=historical
            )
        )
        if terminal is not None:
            issues.extend(
                _teardown_action_attempt_row_issues(
                    policy, terminal, envelope, historical=historical
                )
            )
        if issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "evidence_id": latest.get("Evidence ID", "NONE"),
                "phase": latest.get("Phase", "NONE"),
                "action_status": terminal.get("Status", "STARTED")
                if terminal
                else "STARTED",
                "basis_stale": basis_stale,
                "issues": issues,
            }
        try:
            resources = _teardown_values(
                policy,
                started["Resources proposed to remove"],
                "Resources proposed to remove",
                allow_none=False,
            )
            operations = _teardown_values(
                policy,
                started["Allowed deletion operations"],
                "Allowed deletion operations",
                allow_none=False,
            )
            retained = _teardown_values(
                policy,
                started["Resources retained"],
                "Resources retained",
                allow_none=True,
            )
            shared = _teardown_values(
                policy,
                started["Shared dependencies"],
                "Shared dependencies",
                allow_none=True,
            )
            removed = _teardown_values(
                policy,
                latest["Resources removed"],
                "Resources removed",
                allow_none=True,
            )
            residuals = _teardown_values(
                policy,
                latest["Residual resources"],
                "Residual resources",
                allow_none=True,
            )
        except ValueError as exc:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "issues": [str(exc)],
            }
        reconciliation_read_authority: dict[str, Any] = {}
        if terminal is not None:
            restricted_read = (
                restricted_closure
                or basis_stale
                or construction_authorization == "NONE"
            )
            candidate = None if restricted_read else read_authority
            if candidate is not None and candidate.get("validity") == "CURRENT":
                reconciliation_read_authority = {
                    **dict(candidate),
                    "attempt_id": attempt_id,
                    "reconciliation_only": False,
                }
            else:
                recovered = policy.teardown_reconciliation_read_authority(
                    verify_text,
                    cost_posture,
                    group,
                    attempt_id,
                    restricted_closure=restricted_read,
                )
                if recovered is not None:
                    reconciliation_read_authority = recovered
        projection = {
            **base,
            "attempt_id": attempt_id,
            "evidence_id": latest.get("Evidence ID", "NONE"),
            "observed_at": latest.get("Observed at", "NONE"),
            "ready_evidence_id": ready.get("Evidence ID", "NONE"),
            "read_authorization": started["Read authorization"],
            "read_role_or_profile": started["Read role or profile"],
            "read_receipt_digest": started["Read receipt digest"],
            "read_valid_until": started["Read valid until"],
            "read_authority_source": started["Read authority source"],
            "expected_manifest_or_stack": started["Expected manifest or stack"],
            "account": fields["Account"],
            "region": fields["Region"],
            "environment": fields["Environment"],
            "phase": latest.get("Phase", "NONE"),
            "action_status": terminal.get("Status", "STARTED")
            if terminal
            else "STARTED",
            "basis_stale": basis_stale,
            "teardown_authorization": started["Teardown authorization"],
            "teardown_receipt_digest": started["Teardown receipt digest"],
            "role_or_profile": started["Role or profile"],
            "resources_to_remove": resources,
            "allowed_operations": operations,
            "resources_to_retain": retained,
            "shared_dependencies": shared,
            "resources_removed": removed,
            "residual_resources": residuals,
            "cost_effect": started["Cost effect"],
            "post_action_verification": started["Post-teardown verification"],
            "terminal_status": latest["Stack events and terminal status"],
            "snapshots_and_backups": latest["Snapshots and backups"],
            "inventory_limits": latest["Inventory or discovery limits"],
            "identity_and_boundary_match": latest["Identity and boundary match"],
            "blocker_or_stale_reason": latest["Blocker or stale reason"],
            "current_mutation_authority_status": "CONSUMED",
            "reconciliation_read_authority": reconciliation_read_authority,
        }
        if terminal is None:
            return {**projection, "status": "ACTION_TERMINAL_REQUIRED"}
        if not reviews:
            return {**projection, "status": "POST_ACTION_REVIEW"}
        review = reviews[-1]
        review_issues: list[str] = []
        terminal_time = iso_datetime(terminal.get("Observed at", ""))
        review_time = iso_datetime(review.get("Observed at", ""))
        if terminal_time is None or review_time is None or review_time <= terminal_time:
            review_issues.append(
                "post-action AWS-40 evidence must follow the terminal AWS-50 row"
            )
        if review.get("Teardown authorization") != started.get(
            "Teardown authorization"
        ):
            review_issues.append("post-action AWS-40 changes teardown authorization")
        if review.get("Teardown receipt digest") != started.get(
            "Teardown receipt digest"
        ):
            review_issues.append("post-action AWS-40 changes teardown receipt digest")
        for field_name in (
            "REQ / DES / AUTH",
            "Role or profile",
            "Expected manifest or stack",
            "Resources proposed to remove",
            "Allowed deletion operations",
            "Resources retained",
            "Shared dependencies",
            "Cost effect",
            "Post-teardown verification",
            "Account / Region / environment",
        ):
            if review.get(field_name) != started.get(field_name):
                review_issues.append(
                    f"post-action AWS-40 changes immutable {field_name}"
                )
        review_status = review.get("Status", "")
        review_authority = (
            reconciliation_read_authority
            if clean_cell(reconciliation_read_authority.get("authorization_id", ""))
            == clean_cell(review.get("Read authorization", ""))
            else None
        )
        review_issues.extend(
            _teardown_read_row_issues(
                policy,
                review,
                review_authority,
                require_authority=review_status in {"RUNNING", "STALE"},
                require_exact_scope=(
                    review_status in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
                    and review_authority is not None
                ),
            )
        )
        if review_status in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN"} and review.get(
            "Identity and boundary match"
        ) not in {"PASS", "VERIFIED"}:
            review_issues.append(
                "post-action AWS-40 requires verified identity and boundary"
            )
        if review_status == "VERIFIED_CLEAN":
            if residuals:
                review_issues.append(
                    "VERIFIED_CLEAN requires Residual resources = NONE"
                )
            if set(removed) != set(resources):
                review_issues.append(
                    "VERIFIED_CLEAN must reconcile every proposed removal"
                )
        if review_status == "RESIDUALS_REMAIN" and not residuals:
            review_issues.append(
                "RESIDUALS_REMAIN requires an exact residual-resource list"
            )
        if review_issues:
            return {**projection, "status": "BLOCKED", "issues": review_issues}
        common_review = {
            **projection,
            "review_status": review_status,
            "evidence_id": review["Evidence ID"],
            "observed_at": review["Observed at"],
            "phase": "AWS-40",
            "read_authorization": review["Read authorization"],
            "read_role_or_profile": review["Read role or profile"],
            "read_receipt_digest": review["Read receipt digest"],
            "read_valid_until": review["Read valid until"],
            "read_authority_source": review["Read authority source"],
            "identity_and_boundary_match": review["Identity and boundary match"],
            "blocker_or_stale_reason": review["Blocker or stale reason"],
        }
        if review_status in {"RUNNING", "STALE"}:
            return {**common_review, "status": "POST_ACTION_REVIEW"}
        return {
            **common_review,
            "status": review_status,
            "post_action_bound": review_status
            in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"},
        }

    standalone_rows = [row for row in concrete if row.get("Attempt ID") == "NONE"]
    if not standalone_rows:
        return base
    latest = standalone_rows[-1]
    evidence_id = latest["Evidence ID"]
    status = latest["Status"]
    basis_stale = latest.get("REQ / DES / AUTH") != expected_basis
    authority_for_row = read_authority if current_read and not basis_stale else None
    require_current_read = bool(not basis_stale and status not in {"BLOCKED", "STALE"})
    issues = _teardown_read_row_issues(
        policy,
        latest,
        authority_for_row,
        require_authority=require_current_read,
    )
    if (
        latest.get("Teardown authorization") != "NONE"
        or latest.get("Teardown receipt digest") != "NONE"
    ):
        issues.append("pre-action AWS-40 evidence cannot claim teardown authority")
    if status in {
        "READY_FOR_TEARDOWN",
        "VERIFIED_CLEAN",
        "RESIDUALS_REMAIN",
    } and latest.get("Identity and boundary match") not in {"PASS", "VERIFIED"}:
        issues.append(f"{evidence_id} requires a verified identity and boundary match")
    if issues:
        return {
            **base,
            "status": "BLOCKED",
            "evidence_id": evidence_id,
            "phase": "AWS-40",
            "basis_stale": basis_stale,
            "issues": issues,
        }
    projection = {
        **base,
        "status": status,
        "evidence_id": evidence_id,
        "observed_at": latest["Observed at"],
        "phase": "AWS-40",
        "read_authorization": latest["Read authorization"],
        "read_role_or_profile": latest["Read role or profile"],
        "read_receipt_digest": latest["Read receipt digest"],
        "read_valid_until": latest["Read valid until"],
        "read_authority_source": latest["Read authority source"],
        "expected_manifest_or_stack": latest["Expected manifest or stack"],
        "role_or_profile": latest["Role or profile"],
        "account": authority_for_row.get("account", "NONE")
        if authority_for_row
        else "NONE",
        "region": authority_for_row.get("region", "NONE")
        if authority_for_row
        else "NONE",
        "environment": authority_for_row.get("environment", "NONE")
        if authority_for_row
        else "NONE",
        "identity_and_boundary_match": latest["Identity and boundary match"],
        "blocker_or_stale_reason": latest["Blocker or stale reason"],
        "basis_stale": basis_stale,
    }
    if basis_stale or not current_read or construction_authorization == "NONE":
        return {**projection, "status": "BLOCKED" if status == "BLOCKED" else "STALE"}
    if status in {"RUNNING", "STALE"}:
        return projection
    if status == "BLOCKED":
        return projection
    allow_empty = status in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN"}
    try:
        resources = _teardown_values(
            policy,
            latest["Resources proposed to remove"],
            "Resources proposed to remove",
            allow_none=allow_empty,
        )
        operations = _teardown_values(
            policy,
            latest["Allowed deletion operations"],
            "Allowed deletion operations",
            allow_none=allow_empty,
        )
        retained = _teardown_values(
            policy, latest["Resources retained"], "Resources retained", allow_none=True
        )
        shared = _teardown_values(
            policy,
            latest["Shared dependencies"],
            "Shared dependencies",
            allow_none=True,
        )
        removed = _teardown_values(
            policy, latest["Resources removed"], "Resources removed", allow_none=True
        )
        residuals = _teardown_values(
            policy, latest["Residual resources"], "Residual resources", allow_none=True
        )
    except ValueError as exc:
        return {**projection, "status": "BLOCKED", "issues": [str(exc)]}
    if bool(resources) != bool(operations):
        issues.append(
            "Removal resources and deletion operations must both be present or NONE"
        )
    elif resources and not policy.receipt_scope_within_gate_b(
        resources, operations, envelope
    ):
        issues.append("AWS-40 removal scope exceeds Gate B")
    if (
        set(resources).intersection(retained)
        or set(resources).intersection(shared)
        or set(retained).intersection(shared)
    ):
        issues.append("AWS-40 removal, retention, and shared sets overlap")
    for field_name, allow_none in (
        ("Expected manifest or stack", False),
        ("Cost effect", False),
        ("Post-teardown verification", False),
    ):
        if not explicit_value(latest.get(field_name, ""), allow_none=allow_none):
            issues.append(f"AWS-40 requires {field_name}")
    if status == "VERIFIED_CLEAN":
        if residuals:
            issues.append("VERIFIED_CLEAN requires Residual resources = NONE")
        if set(removed) != set(resources):
            issues.append("VERIFIED_CLEAN must reconcile every proposed removal")
    if status == "RESIDUALS_REMAIN" and not residuals:
        issues.append("RESIDUALS_REMAIN requires an exact residual-resource list")
    if issues:
        return {**projection, "status": "BLOCKED", "issues": issues}
    return {
        **projection,
        "resources_to_remove": resources,
        "allowed_operations": operations,
        "resources_to_retain": retained,
        "shared_dependencies": shared,
        "resources_removed": removed,
        "residual_resources": residuals,
        "cost_effect": latest["Cost effect"],
        "post_action_verification": latest["Post-teardown verification"],
        "terminal_status": latest["Stack events and terminal status"],
        "snapshots_and_backups": latest["Snapshots and backups"],
        "inventory_limits": latest["Inventory or discovery limits"],
    }


__all__ = ("derive_teardown_sequence_state",)
