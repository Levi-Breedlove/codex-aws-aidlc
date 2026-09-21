"""Pure AWS deployment and reconciliation state machine.

Canonical input is the append-only VERIFY journal plus explicit current design
and authority projections. The evaluator performs no AWS call, file read, or
state write and cannot broaden authority. The cohesive state machine remains
large because journal chronology and fail-closed replay checks must preserve
their exact diagnostic order during the modular extraction.
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
from .evidence import parse_deployment_reconciliation_evidence
from .models import (
    AWS_DEPLOYMENT_ACTION_STATUSES,
    AWS_DEPLOYMENT_ATTEMPT_ID,
    AWS_DEPLOYMENT_EVIDENCE_HEADERS,
    AWS_DEPLOYMENT_PRECALL_RESULT,
    AWS_DEPLOYMENT_READ_PROVENANCE,
    AWS_DEPLOYMENT_RECEIPT_FIELDS,
    AWS_DEPLOYMENT_RECONCILIATION_STATUSES,
    AWS_DEPLOYMENT_TERMINAL_STATUSES,
    AWS_PLAN_BINDING,
    AWS_PREFLIGHT_ID,
    AWS_READ_AUTHORIZATION_ID,
    AWS_READ_ONLY_OPERATION,
    AwsAuthorityPolicy,
)


def _deployment_acceptance_evidence_issues(
    policy: AwsAuthorityPolicy,
    verify_text: str,
    evidence_ids: list[str],
    expected: Mapping[str, Any],
) -> list[str]:
    """Resolve AWS-30 COMPLETE IDs to current VERIFIED target-bound evidence."""

    try:
        rows = policy.parse_verification_matrix(verify_text)
    except ValueError as exc:
        return [str(exc)]
    by_id: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id):
            by_id.setdefault(evidence_id, []).append(row)
    expected_target = (
        f"ARTIFACT: {expected.get('artifact')}; ACCOUNT: {expected.get('account')}; "
        f"REGION: {expected.get('region')}; ENVIRONMENT: {expected.get('environment')}"
    )
    issues: list[str] = []
    for evidence_id in evidence_ids:
        matching = by_id.get(evidence_id, [])
        if len(matching) != 1:
            issues.append(
                f"{evidence_id} must resolve exactly once in the Verification matrix"
            )
            continue
        row = matching[0]
        if clean_cell(row.get("Status", "")) != "VERIFIED":
            issues.append(f"{evidence_id} Verification matrix status must be VERIFIED")
        requirement = clean_cell(row.get("Requirement or invariant", ""))
        manual_evidence = clean_cell(row.get("AWS/manual evidence", ""))
        if not explicit_value(requirement, allow_none=False) or "*" in requirement:
            issues.append(f"{evidence_id} requires a concrete requirement or invariant")
        if (
            not explicit_value(manual_evidence, allow_none=False)
            or "*" in manual_evidence
        ):
            issues.append(f"{evidence_id} requires concrete AWS/manual evidence")
        if clean_cell(row.get("Artifact/environment", "")) != expected_target:
            issues.append(
                f"{evidence_id} does not bind the exact artifact/account/Region/environment"
            )
    return issues


def _deployment_operation_result_issues(
    value: str, evidence_id: str, *, started: bool
) -> list[str]:
    """Validate the machine-readable operation identifier and direct-result grammar."""

    cleaned = clean_cell(value)
    if started:
        return (
            []
            if cleaned == AWS_DEPLOYMENT_PRECALL_RESULT
            else [f"{evidence_id} STARTED must use the exact pre-call result sentinel"]
        )
    match = re.fullmatch(
        r"IDENTIFIERS: (?P<identifiers>.+); RESULT: (?P<result>.+)", cleaned
    )
    if match is None:
        return [
            f"{evidence_id} post-call result must use IDENTIFIERS: <list or NONE reason>; RESULT: <direct result>"
        ]
    identifiers = clean_cell(match.group("identifiers"))
    result = clean_cell(match.group("result"))
    none_match = re.fullmatch(r"NONE \u2014 (?P<reason>.+)", identifiers)
    if none_match is not None:
        reason = clean_cell(none_match.group("reason"))
        if not explicit_value(reason, allow_none=False) or "*" in reason:
            return [f"{evidence_id} NONE identifiers require a concrete reason"]
    else:
        values = [item.strip() for item in identifiers.split(",")]
        if (
            not values
            or len(values) != len(set(values))
            or any(
                not explicit_value(item, allow_none=False)
                or "*" in item
                or re.search(r"[\r\n\x00-\x1f\x7f]", item) is not None
                for item in values
            )
        ):
            return [
                f"{evidence_id} operation identifiers must be a unique exact wildcard-free list"
            ]
    if not explicit_value(result, allow_none=False) or "*" in result:
        return [f"{evidence_id} requires a concrete direct result"]
    return []


def _deployment_values(
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


def _deployment_evidence_ids(
    policy: AwsAuthorityPolicy, value: str, *, allow_none: bool
) -> list[str]:
    values = _deployment_values(
        policy, value, "Acceptance evidence IDs", allow_none=allow_none
    )
    if any(re.fullmatch(r"EV-\d{4,}", item) is None for item in values):
        raise ValueError(
            "Acceptance evidence IDs must be a unique comma-separated EV list or NONE"
        )
    return values


def _deployment_expected_binding(
    policy: AwsAuthorityPolicy,
    verify_text: str,
    *,
    construction_authorization: str,
    envelope: Mapping[str, str],
    lane: str | None,
    artifact_binding: str,
    gate_b_authority_source: str = "",
    gate_b_authorized_at: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """SAFETY: derive the mutation ceiling without treating it as an attempt."""

    issues: list[str] = []
    if construction_authorization == "NONE":
        return {}, ["deployment evidence requires a current construction authorization"]
    if lane not in {"fast-dev", "explicit-gate"}:
        return {}, ["deployment evidence is not permitted for the selected AWS lane"]
    try:
        environment, _environment_class = policy.parse_aws_environment(
            envelope.get("AWS environment", "")
        )
    except ValueError:
        environment = ""
    account = policy.envelope_scalar(envelope, "AWS account", "ACCOUNT")
    region = policy.envelope_scalar(envelope, "AWS Region", "REGION")
    deployment_role = policy.envelope_scalar(envelope, "AWS role or profile", "ROLE")
    resources = policy.envelope_values(envelope, "AWS resource allowlist", "RESOURCES")
    allowed_operations = policy.envelope_values(
        envelope, "AWS allowed operations", "OPERATIONS"
    )
    operations = (
        [
            operation
            for operation in allowed_operations
            if AWS_READ_ONLY_OPERATION.fullmatch(operation) is None
        ]
        if lane == "fast-dev"
        else allowed_operations
    )
    for label, value in (
        ("AWS account", account),
        ("AWS Region", region),
        ("AWS environment", environment),
        ("AWS role or profile", deployment_role),
    ):
        if not value:
            issues.append(f"deployment evidence requires exact {label}")
    if not resources or not operations:
        issues.append(
            "deployment evidence requires exact Gate B resources and operations"
        )
    if not policy.receipt_artifact_matches_gate_b(
        artifact_binding, envelope, artifact_binding
    ):
        issues.append("deployment evidence artifact is outside current Gate B")
    expected: dict[str, Any] = {
        "authorization_id": construction_authorization,
        "receipt_digest": "NONE",
        "authorized_at": clean_cell(gate_b_authorized_at),
        "valid_until": "NONE",
        "deployment_role": deployment_role or "NONE",
        "deployment_authority_source": clean_cell(gate_b_authority_source),
        "artifact": artifact_binding,
        "plan": clean_cell(envelope.get("AWS stack or application", "")),
        "account": account or "NONE",
        "region": region or "NONE",
        "environment": environment or "NONE",
        "resources": resources,
        "operations": operations,
        "verify_text": verify_text,
    }
    try:
        receipt = policy.marked_receipt(verify_text, "aws-deployment")
        provenance = policy.action_authorization_rows(verify_text).get("Deployment")
    except ValueError:
        receipt = ""
        provenance = None
    fields = policy.exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS DEPLOYMENT",
        AWS_DEPLOYMENT_RECEIPT_FIELDS,
        allow_none_fields=frozenset({"Rollback boundary"}),
    )
    digest = (
        "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        if receipt
        else "NONE"
    )
    if fields is None or provenance is None or unresolved(receipt):
        issues.append("deployment evidence requires one exact owner-authored receipt")
        return expected, issues
    receipt_resources = policy.split_authority_values(
        fields["Stack, application, and resources"]
    )
    receipt_operations = policy.split_authority_values(fields["Allowed operations"])
    receipt_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    receipt_resources_and_operations = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed operations']}"
    )
    expected.update(
        {
            "authorization_id": fields["AWS authorization"],
            "receipt_digest": digest,
            "authorized_at": clean_cell(provenance.get("Observed at", "")),
            "valid_until": fields["Valid until"],
            "deployment_role": fields["Profile or role"],
            "deployment_authority_source": clean_cell(
                provenance.get("Stable owner-message source", "")
            ),
            "artifact": fields["Artifact digest"],
            "plan": fields["IaC plan/change-set binding"],
            "account": fields["Account"],
            "region": fields["Region"],
            "environment": fields["Environment"],
            "resources": receipt_resources,
            "operations": receipt_operations,
        }
    )
    receipt_binding_invalid = (
        re.fullmatch(r"AWS-AUTH-\d{4,}", fields["AWS authorization"]) is None
        or fields["Construction authorization"] != construction_authorization
        or AWS_PLAN_BINDING.fullmatch(fields["IaC plan/change-set binding"]) is None
        or not policy.receipt_identity_matches_gate_b(fields, envelope)
        or not policy.receipt_scope_within_gate_b(
            receipt_resources, receipt_operations, envelope
        )
        or not policy.receipt_artifact_matches_gate_b(
            fields["Artifact digest"], envelope, artifact_binding
        )
        or fields["Rollback boundary"] != policy.gate_b_rollback_value(envelope)
    )
    provenance_invalid = (
        provenance.get("Authorization ID") != fields["AWS authorization"]
        or provenance.get("Construction AUTH") != construction_authorization
        or provenance.get("Role or profile") != fields["Profile or role"]
        or provenance.get("Artifact digest") != fields["Artifact digest"]
        or provenance.get("IaC plan/change-set binding")
        != fields["IaC plan/change-set binding"]
        or provenance.get("Account / Region / environment") != receipt_scope
        or provenance.get("Resources and operations")
        != receipt_resources_and_operations
        or provenance.get("Approver") != fields["Approver"]
        or not policy.explicit_human_approver(fields["Approver"])
        or clean_cell(provenance.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(
            provenance.get("Stable owner-message source", ""), allow_none=False
        )
        or not explicit_timestamp(provenance.get("Observed at", ""))
        or clean_cell(provenance.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or clean_cell(provenance.get("Result", ""))
        not in {"AUTHORIZED", "RUNNING", "READY"}
        or AWS_PREFLIGHT_ID.fullmatch(
            clean_cell(provenance.get("Preflight evidence", ""))
        )
        is None
    )
    if receipt_binding_invalid:
        issues.append(
            "deployment receipt does not match current Gate B identity, scope, "
            "artifact, plan, or rollback boundary"
        )
    if provenance_invalid:
        issues.append(
            "deployment receipt does not match its exact authorization provenance"
        )
    return expected, issues


def _deployment_row_binding_issues(
    policy: AwsAuthorityPolicy,
    row: Mapping[str, str],
    expected: Mapping[str, Any],
    read_authority: Mapping[str, Any] | None,
    *,
    historical: bool = False,
) -> list[str]:
    """SAFETY: compare one journal row with its exact authorized binding."""

    evidence_id = clean_cell(row.get("Evidence ID", "")) or "deployment row"
    phase = clean_cell(row.get("Phase", ""))
    status = clean_cell(row.get("Status", ""))
    issues: list[str] = []
    expected_scope = (
        f"ACCOUNT: {expected.get('account')}; REGION: {expected.get('region')}; "
        f"ENVIRONMENT: {expected.get('environment')}"
    )
    scalar_fields = {
        "Deployment authorization": expected.get("authorization_id"),
        "Deployment receipt digest": expected.get("receipt_digest"),
        "Deployment valid until": expected.get("valid_until"),
        "Deployment authority source": expected.get("deployment_authority_source"),
        "Deployment role or profile": expected.get("deployment_role"),
        "Artifact digest": expected.get("artifact"),
        "Plan/change-set binding": expected.get("plan"),
        "Account / Region / environment": expected_scope,
    }
    for field_name, value in scalar_fields.items():
        if clean_cell(row.get(field_name, "")) != clean_cell(value):
            issues.append(f"{evidence_id} {field_name} does not match its authority")
    try:
        resources = _deployment_values(
            policy, row.get("Resources", ""), "Resources", allow_none=False
        )
        operations = _deployment_values(
            policy,
            row.get("Mutation operations", ""),
            "Mutation operations",
            allow_none=False,
        )
    except ValueError as exc:
        issues.append(str(exc))
        resources, operations = [], []
    if set(resources) != set(expected.get("resources", [])):
        issues.append(f"{evidence_id} Resources do not match the attempted scope")
    if set(operations) != set(expected.get("operations", [])):
        issues.append(
            f"{evidence_id} Mutation operations do not match the attempted scope"
        )
    started = phase == "AWS-20" and status == "STARTED"
    operation_result = clean_cell(
        row.get("Operation identifiers and direct result", "")
    )
    issues.extend(
        _deployment_operation_result_issues(
            operation_result, evidence_id, started=started
        )
    )
    rollback_result = clean_cell(row.get("Rollback result", ""))
    if started and rollback_result != "NONE":
        issues.append(f"{evidence_id} STARTED must use Rollback result = NONE")
    for field_name, allow_none in (
        ("Rollback result", True),
        ("Durable source", False),
    ):
        if not explicit_value(row.get(field_name, ""), allow_none=allow_none):
            issues.append(f"{evidence_id} requires {field_name}")
    blocker_reason = clean_cell(row.get("Blocker or stale reason", ""))
    if status in {"BLOCKED", "STALE"}:
        if not explicit_value(blocker_reason, allow_none=False):
            issues.append(f"{evidence_id} requires an exact blocker or stale reason")
    elif blocker_reason != "NONE":
        issues.append(f"{evidence_id} must use Blocker or stale reason = NONE")
    identity = clean_cell(row.get("Identity and boundary match", ""))
    if phase == "AWS-20":
        for field_name in (
            "Read authorization",
            "Read role or profile",
            "Read receipt digest",
            "Read valid until",
            "Read authority source",
            "Read operations observed",
            "Acceptance evidence IDs",
        ):
            if clean_cell(row.get(field_name, "")) != "NONE":
                issues.append(f"{evidence_id} AWS-20 requires {field_name} = NONE")
        if identity not in {"PASS", "VERIFIED"}:
            issues.append(
                f"{evidence_id} AWS-20 requires verified identity and boundary"
            )
        return issues

    read_id = clean_cell(row.get("Read authorization", ""))
    read_role = clean_cell(row.get("Read role or profile", ""))
    read_digest = clean_cell(row.get("Read receipt digest", ""))
    read_valid_until = clean_cell(row.get("Read valid until", ""))
    read_source = clean_cell(row.get("Read authority source", ""))
    read_provenance = _parse_deployment_read_provenance(policy, read_source)
    if AWS_READ_AUTHORIZATION_ID.fullmatch(read_id) is None:
        issues.append(f"{evidence_id} AWS-30 requires a separate read authorization")
    if not explicit_value(read_role, allow_none=False):
        issues.append(f"{evidence_id} AWS-30 requires a separate read role")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", read_digest) is None:
        issues.append(f"{evidence_id} AWS-30 requires an exact read receipt digest")
    read_expiry = iso_datetime(read_valid_until)
    observed_at = iso_datetime(row.get("Observed at", ""))
    if read_valid_until == "ONE_OPERATION" or read_expiry is None:
        issues.append(f"{evidence_id} AWS-30 requires reusable ISO read validity")
    elif observed_at is not None and observed_at > read_expiry:
        issues.append(f"{evidence_id} AWS-30 was observed after read authority expiry")
    if read_provenance is None:
        issues.append(
            f"{evidence_id} AWS-30 requires the exact durable read authority "
            "source, authorization time, resources, and operations envelope"
        )
    try:
        observed_reads = _deployment_values(
            policy,
            row.get("Read operations observed", ""),
            "Read operations observed",
            allow_none=status == "STALE",
        )
        acceptance_ids = _deployment_evidence_ids(
            policy,
            row.get("Acceptance evidence IDs", ""),
            allow_none=status != "COMPLETE",
        )
    except ValueError as exc:
        issues.append(str(exc))
        observed_reads, acceptance_ids = [], []
    if read_provenance is not None:
        read_authorized_at = iso_datetime(read_provenance["authorized_at"])
        if (
            observed_at is not None
            and read_authorized_at is not None
            and observed_at < read_authorized_at
        ):
            issues.append(
                f"{evidence_id} AWS-30 observation precedes read authorization"
            )
        if resources != read_provenance["resources"]:
            issues.append(
                f"{evidence_id} Resources do not match the durable read authorization"
            )
        if not set(observed_reads).issubset(set(read_provenance["operations"])):
            issues.append(
                f"{evidence_id} observed reads exceed the durable read authorization"
            )
    if status in {"COMPLETE", "BLOCKED"} and identity not in {"PASS", "VERIFIED"}:
        issues.append(f"{evidence_id} AWS-30 requires verified identity and boundary")
    if status == "STALE" and not explicit_value(identity, allow_none=False):
        issues.append(
            f"{evidence_id} STALE requires a concrete identity and boundary result"
        )
    if (
        status in {"COMPLETE", "BLOCKED"}
        and not historical
        and read_authority is not None
    ):
        same_read_id = read_id == clean_cell(read_authority.get("authorization_id", ""))
        if not same_read_id:
            issues.append(
                f"{evidence_id} read authorization does not match current authority"
            )
        else:
            read_scope = (
                f"ACCOUNT: {read_authority.get('account')}; "
                f"REGION: {read_authority.get('region')}; "
                f"ENVIRONMENT: {read_authority.get('environment')}"
            )
            read_authorized_at = iso_datetime(read_authority.get("authorized_at", ""))
            if read_authorized_at is None:
                issues.append(f"{evidence_id} read authorization timestamp is invalid")
            elif observed_at is not None and observed_at < read_authorized_at:
                issues.append(
                    f"{evidence_id} AWS-30 observation precedes read authorization"
                )
            if read_role != clean_cell(read_authority.get("role_or_profile", "")):
                issues.append(f"{evidence_id} read role does not match its receipt")
            if read_digest != clean_cell(read_authority.get("receipt_digest", "")):
                issues.append(f"{evidence_id} read receipt digest is tampered")
            if read_valid_until != clean_cell(read_authority.get("expiration", "")):
                issues.append(f"{evidence_id} read validity is tampered")
            expected_read_source = _format_deployment_read_provenance(
                clean_cell(read_authority.get("authority_source", "")),
                clean_cell(read_authority.get("authorized_at", "")),
                read_authority.get("resources", []),
                read_authority.get("operations", []),
            )
            if read_source != expected_read_source:
                issues.append(f"{evidence_id} read authority provenance is tampered")
            if expected_scope != read_scope:
                issues.append(f"{evidence_id} read account boundary is stale")
            if resources != list(read_authority.get("resources", [])):
                issues.append(
                    f"{evidence_id} attempted resources do not match read scope"
                )
            if not set(observed_reads).issubset(
                set(read_authority.get("operations", []))
            ):
                issues.append(
                    f"{evidence_id} observed reads exceed the read authorization"
                )
    if status == "COMPLETE":
        if not acceptance_ids:
            issues.append(f"{evidence_id} COMPLETE requires acceptance evidence IDs")
        else:
            issues.extend(
                _deployment_acceptance_evidence_issues(
                    policy,
                    str(expected.get("verify_text", "")),
                    acceptance_ids,
                    expected,
                )
            )
    return issues


def _format_deployment_read_provenance(
    source: str,
    authorized_at: str,
    resources: Any,
    operations: Any,
) -> str:
    """Format the exact durable AWS-30 read-authorization envelope."""

    resource_values = list(resources) if isinstance(resources, (list, tuple)) else []
    operation_values = list(operations) if isinstance(operations, (list, tuple)) else []
    return (
        f"SOURCE: {clean_cell(source)}; AUTHORIZED_AT: {clean_cell(authorized_at)}; "
        f"RESOURCES: {', '.join(clean_cell(item) for item in resource_values)}; "
        f"OPERATIONS: {', '.join(clean_cell(item) for item in operation_values)}"
    )


def _parse_deployment_read_provenance(
    policy: AwsAuthorityPolicy, value: str
) -> dict[str, Any] | None:
    """Parse one canonical AWS-30 envelope without reviving its authority."""

    cleaned = clean_cell(value)
    match = AWS_DEPLOYMENT_READ_PROVENANCE.fullmatch(cleaned)
    if match is None:
        return None
    source = clean_cell(match.group("source"))
    authorized_at = clean_cell(match.group("authorized_at"))
    try:
        resources = _deployment_values(
            policy,
            match.group("resources"),
            "Read-authorized resources",
            allow_none=False,
        )
        operations = _deployment_values(
            policy,
            match.group("operations"),
            "Read-authorized operations",
            allow_none=False,
        )
    except ValueError:
        return None
    if (
        not explicit_value(source, allow_none=False)
        or "*" in source
        or iso_datetime(authorized_at) is None
        or any(AWS_READ_ONLY_OPERATION.fullmatch(item) is None for item in operations)
    ):
        return None
    canonical = _format_deployment_read_provenance(
        source, authorized_at, resources, operations
    )
    if cleaned != canonical:
        return None
    return {
        "source": source,
        "authorized_at": authorized_at,
        "resources": resources,
        "operations": operations,
    }


def _deployment_historical_authority_proof_issues(
    policy: AwsAuthorityPolicy,
    group: list[dict[str, str]],
    verify_text: str,
    *,
    gate_b_authority_source: str,
    gate_b_authorized_at: str,
) -> list[str]:
    """SAFETY: prove a stale STARTED row followed its durable original authority."""

    first = group[0]
    issues: list[str] = []
    basis = clean_cell(first.get("REQ / DES / AUTH", ""))
    basis_match = re.fullmatch(
        r"REQ-\d{4,} / DES-\d{4,} / (?P<auth>AUTH-\d{4,})", basis
    )
    started_at = iso_datetime(first.get("Observed at", ""))
    if basis_match is None or started_at is None:
        return ["historical deployment authorization timing proof is unavailable"]

    authorization_id = clean_cell(first.get("Deployment authorization", ""))
    receipt_digest = clean_cell(first.get("Deployment receipt digest", ""))
    authority_source = clean_cell(first.get("Deployment authority source", ""))
    if receipt_digest == "NONE":
        authorized_at = iso_datetime(gate_b_authorized_at)
        if (
            authorization_id != basis_match.group("auth")
            or authorized_at is None
            or authority_source != clean_cell(gate_b_authority_source)
            or not explicit_value(authority_source, allow_none=False)
        ):
            issues.append(
                "historical fast-dev STARTED lacks its original Gate B authorization provenance"
            )
        elif started_at < authorized_at:
            issues.append(
                "historical deployment STARTED precedes its original authorization provenance"
            )
        return issues

    try:
        receipt = policy.marked_receipt(verify_text, "aws-deployment")
        provenance = policy.action_authorization_rows(verify_text).get("Deployment")
    except ValueError:
        receipt = ""
        provenance = None
    fields = policy.exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS DEPLOYMENT",
        AWS_DEPLOYMENT_RECEIPT_FIELDS,
        allow_none_fields=frozenset({"Rollback boundary"}),
    )
    if fields is None or provenance is None or unresolved(receipt):
        return [
            "historical explicit-gate STARTED lacks its durable original receipt and provenance"
        ]
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    receipt_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    receipt_resources_and_operations = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed operations']}"
    )
    authorized_at = iso_datetime(provenance.get("Observed at", ""))
    binding_invalid = (
        fields["AWS authorization"] != authorization_id
        or fields["Construction authorization"] != basis_match.group("auth")
        or digest != receipt_digest
        or fields["Valid until"] != clean_cell(first.get("Deployment valid until", ""))
        or fields["Profile or role"]
        != clean_cell(first.get("Deployment role or profile", ""))
        or fields["Artifact digest"] != clean_cell(first.get("Artifact digest", ""))
        or fields["IaC plan/change-set binding"]
        != clean_cell(first.get("Plan/change-set binding", ""))
        or receipt_scope != clean_cell(first.get("Account / Region / environment", ""))
        or set(
            policy.split_authority_values(fields["Stack, application, and resources"])
        )
        != set(
            _deployment_values(
                policy, first.get("Resources", ""), "Resources", allow_none=False
            )
        )
        or set(policy.split_authority_values(fields["Allowed operations"]))
        != set(
            _deployment_values(
                policy,
                first.get("Mutation operations", ""),
                "Mutation operations",
                allow_none=False,
            )
        )
        or provenance.get("Authorization ID") != authorization_id
        or provenance.get("Construction AUTH") != basis_match.group("auth")
        or provenance.get("Role or profile") != fields["Profile or role"]
        or provenance.get("Artifact digest") != fields["Artifact digest"]
        or provenance.get("IaC plan/change-set binding")
        != fields["IaC plan/change-set binding"]
        or provenance.get("Account / Region / environment") != receipt_scope
        or provenance.get("Resources and operations")
        != receipt_resources_and_operations
        or clean_cell(provenance.get("Stable owner-message source", ""))
        != authority_source
        or provenance.get("Approver") != fields["Approver"]
        or not policy.explicit_human_approver(fields["Approver"])
        or clean_cell(provenance.get("Verbatim receipt SHA-256", "")) != digest
        or authorized_at is None
        or clean_cell(provenance.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or clean_cell(provenance.get("Result", ""))
        not in {"AUTHORIZED", "RUNNING", "READY"}
    )
    if binding_invalid:
        issues.append(
            "historical explicit-gate STARTED does not bind its durable original receipt and provenance"
        )
    elif started_at < authorized_at:
        issues.append(
            "historical deployment STARTED precedes its original authorization provenance"
        )
    return issues


def _deployment_historical_group_issues(
    policy: AwsAuthorityPolicy,
    group: list[dict[str, str]],
    verify_text: str,
    *,
    current_read_authority: Mapping[str, Any] | None = None,
    require_authorization_proof: bool = False,
    gate_b_authority_source: str = "",
    gate_b_authorized_at: str = "",
) -> list[str]:
    """SAFETY: validate historical rows without reviving their authority."""

    first = group[0]
    issues: list[str] = []
    scope = clean_cell(first.get("Account / Region / environment", ""))
    scope_match = re.fullmatch(
        r"ACCOUNT: (?P<account>[^;]+); REGION: (?P<region>[^;]+); "
        r"ENVIRONMENT: (?P<environment>[^;]+)",
        scope,
    )
    try:
        resources = _deployment_values(
            policy, first.get("Resources", ""), "Resources", allow_none=False
        )
        operations = _deployment_values(
            policy,
            first.get("Mutation operations", ""),
            "Mutation operations",
            allow_none=False,
        )
    except ValueError as exc:
        return [str(exc)]
    basis = clean_cell(first.get("REQ / DES / AUTH", ""))
    if re.fullmatch(r"REQ-\d{4,} / DES-\d{4,} / AUTH-\d{4,}", basis) is None:
        issues.append(
            "historical deployment attempt has a noncanonical REQ / DES / AUTH basis"
        )
    authorization_id = clean_cell(first.get("Deployment authorization", ""))
    digest = clean_cell(first.get("Deployment receipt digest", ""))
    deployment_valid_until = clean_cell(first.get("Deployment valid until", ""))
    deployment_source = clean_cell(first.get("Deployment authority source", ""))
    fast_dev = digest == "NONE"
    if fast_dev:
        if re.fullmatch(r"AUTH-\d{4,}", authorization_id) is None:
            issues.append("historical fast-dev attempt has noncanonical authority")
    elif (
        re.fullmatch(r"AWS-AUTH-\d{4,}", authorization_id) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
    ):
        issues.append("historical explicit-gate attempt has noncanonical authority")
    expires_at = iso_datetime(deployment_valid_until)
    started_at = iso_datetime(first.get("Observed at", ""))
    if fast_dev and expires_at is None:
        issues.append("historical fast-dev validity must be an ISO 8601 timestamp")
    elif (
        not fast_dev
        and deployment_valid_until != "ONE_OPERATION"
        and expires_at is None
    ):
        issues.append(
            "historical explicit-gate validity must be ISO 8601 or ONE_OPERATION"
        )
    elif started_at is not None and expires_at is not None and started_at > expires_at:
        issues.append("historical deployment STARTED occurred after authority expiry")
    if (
        not explicit_value(deployment_source, allow_none=False)
        or "*" in deployment_source
    ):
        issues.append("historical deployment authority source is unresolved")
    if scope_match is None:
        issues.append("historical deployment attempt has a noncanonical account scope")
        account = region = environment = "NONE"
    else:
        account = clean_cell(scope_match.group("account"))
        region = clean_cell(scope_match.group("region"))
        environment = clean_cell(scope_match.group("environment"))
        for label, value in (
            ("account", account),
            ("Region", region),
            ("environment", environment),
        ):
            if not explicit_value(value, allow_none=False) or "*" in value:
                issues.append(
                    f"historical deployment {label} must be concrete and wildcard-free"
                )
    deployment_role = clean_cell(first.get("Deployment role or profile", ""))
    artifact = clean_cell(first.get("Artifact digest", ""))
    plan = clean_cell(first.get("Plan/change-set binding", ""))
    if not explicit_value(deployment_role, allow_none=False) or "*" in deployment_role:
        issues.append(
            "historical deployment attempt requires a concrete deployment role"
        )
    if re.fullmatch(r"sha256:[0-9a-f]{64}", artifact) is None:
        issues.append("historical deployment attempt requires an exact artifact digest")
    if fast_dev:
        if not explicit_value(plan, allow_none=False) or "*" in plan:
            issues.append("historical fast-dev attempt requires an exact plan binding")
    elif AWS_PLAN_BINDING.fullmatch(plan) is None:
        issues.append(
            "historical explicit-gate attempt requires a canonical plan binding"
        )
    expected = {
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "valid_until": deployment_valid_until,
        "deployment_authority_source": deployment_source,
        "deployment_role": deployment_role,
        "artifact": artifact,
        "plan": plan,
        "account": account,
        "region": region,
        "environment": environment,
        "resources": resources,
        "operations": operations,
        "verify_text": verify_text,
    }
    if require_authorization_proof:
        issues.extend(
            _deployment_historical_authority_proof_issues(
                policy,
                group,
                verify_text,
                gate_b_authority_source=gate_b_authority_source,
                gate_b_authorized_at=gate_b_authorized_at,
            )
        )
    for row in group:
        issues.extend(
            _deployment_row_binding_issues(
                policy,
                row,
                expected,
                current_read_authority,
                historical=current_read_authority is None,
            )
        )
    return issues


def _deployment_group_projection(
    policy: AwsAuthorityPolicy,
    base: Mapping[str, Any],
    attempt_id: str,
    group: list[dict[str, str]],
) -> dict[str, Any]:
    """SAFETY: project one attempt group without expanding its authority."""

    action_rows = [row for row in group if row["Phase"] == "AWS-20"]
    terminal_rows = [
        row for row in action_rows if row["Status"] in AWS_DEPLOYMENT_TERMINAL_STATUSES
    ]
    action = terminal_rows[0] if terminal_rows else action_rows[0]
    reconciliation_rows = [row for row in group if row["Phase"] == "AWS-30"]
    reconciliation = reconciliation_rows[-1] if reconciliation_rows else None
    latest = reconciliation or action
    try:
        resources = _deployment_values(
            policy, latest["Resources"], "Resources", allow_none=False
        )
        operations = _deployment_values(
            policy,
            latest["Mutation operations"],
            "Mutation operations",
            allow_none=False,
        )
        observed_reads = (
            _deployment_values(
                policy,
                latest["Read operations observed"],
                "Read operations observed",
                allow_none=latest["Status"] == "STALE",
            )
            if latest["Phase"] == "AWS-30"
            else []
        )
        acceptance_ids = (
            _deployment_evidence_ids(
                policy,
                latest["Acceptance evidence IDs"],
                allow_none=latest["Status"] != "COMPLETE",
            )
            if latest["Phase"] == "AWS-30"
            else []
        )
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    reconciliation_status = (
        clean_cell(reconciliation["Status"]) if reconciliation else "NONE"
    )
    read_provenance = (
        _parse_deployment_read_provenance(policy, latest["Read authority source"])
        if latest["Phase"] == "AWS-30"
        else None
    )
    status = (
        "ACTION_TERMINAL_REQUIRED"
        if clean_cell(action["Status"]) == "STARTED" and reconciliation is None
        else {
            "COMPLETE": "RECONCILED",
            "BLOCKED": "BLOCKED",
            "STALE": "RECONCILIATION_REQUIRED",
            "NONE": "RECONCILIATION_REQUIRED",
        }[reconciliation_status]
    )
    return {
        **base,
        "status": status,
        "attempt_id": attempt_id,
        "evidence_id": clean_cell(latest["Evidence ID"]),
        "phase": clean_cell(latest["Phase"]),
        "action_status": clean_cell(action["Status"]),
        "reconciliation_status": reconciliation_status,
        "deployment_authorization": clean_cell(latest["Deployment authorization"]),
        "deployment_receipt_digest": clean_cell(latest["Deployment receipt digest"]),
        "deployment_valid_until": clean_cell(latest["Deployment valid until"]),
        "deployment_authority_source": clean_cell(
            latest["Deployment authority source"]
        ),
        "read_authorization": clean_cell(latest["Read authorization"]),
        "deployment_role_or_profile": clean_cell(latest["Deployment role or profile"]),
        "read_role_or_profile": clean_cell(latest["Read role or profile"]),
        "read_receipt_digest": clean_cell(latest["Read receipt digest"]),
        "read_valid_until": clean_cell(latest["Read valid until"]),
        "read_authorized_at": (
            read_provenance["authorized_at"] if read_provenance else "NONE"
        ),
        "read_authorized_resources": (
            read_provenance["resources"] if read_provenance else []
        ),
        "read_authorized_operations": (
            read_provenance["operations"] if read_provenance else []
        ),
        "read_authority_source": clean_cell(latest["Read authority source"]),
        "artifact_digest": clean_cell(latest["Artifact digest"]),
        "plan_binding": clean_cell(latest["Plan/change-set binding"]),
        "resources": resources,
        "mutation_operations": operations,
        "read_operations_observed": observed_reads,
        "acceptance_evidence_ids": acceptance_ids,
        "operation_result": clean_cell(
            latest["Operation identifiers and direct result"]
        ),
        "rollback_result": clean_cell(latest["Rollback result"]),
        "identity_and_boundary_match": clean_cell(
            latest["Identity and boundary match"]
        ),
        "blocker_or_stale_reason": clean_cell(latest["Blocker or stale reason"]),
    }


def _deployment_authority_timing_issues(
    group: list[dict[str, str]], expected: Mapping[str, Any]
) -> list[str]:
    """Validate that mutation began within the exact recorded authority window."""

    issues: list[str] = []
    started_at = iso_datetime(group[0].get("Observed at", ""))
    authorized_at = iso_datetime(expected.get("authorized_at", ""))
    valid_until = clean_cell(expected.get("valid_until", ""))
    expires_at = None if valid_until == "ONE_OPERATION" else iso_datetime(valid_until)
    if started_at is None:
        issues.append("deployment STARTED timestamp is invalid")
    if authorized_at is None:
        issues.append("deployment authorization timestamp is invalid")
    elif started_at is not None and started_at < authorized_at:
        issues.append("deployment STARTED precedes its authorization provenance")
    if valid_until != "ONE_OPERATION" and expires_at is None:
        issues.append("deployment authority has a noncanonical validity boundary")
    elif started_at is not None and expires_at is not None and started_at > expires_at:
        issues.append("deployment STARTED occurred after authority expiry")
    return issues


def derive_deployment_sequence_state(
    verify_text: str,
    read_authority: Mapping[str, Any] | None,
    *,
    policy: AwsAuthorityPolicy,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    envelope: Mapping[str, str],
    lane: str | None,
    artifact_binding: str,
    release_evidence_cutoff: str = "NONE",
    release_state: str = "READY_TO_DEPLOY",
    gate_b_authority_source: str = "",
    gate_b_authorized_at: str = "",
    cost_posture: str = "",
    restricted_closure: bool = False,
) -> dict[str, Any]:
    """SAFETY: derive AWS-20/AWS-30 sequencing without inferring an action."""

    base: dict[str, Any] = {
        "status": "NOT_ACTIVE",
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "phase": "NONE",
        "action_status": "NONE",
        "reconciliation_status": "NONE",
        "deployment_authorization": "NONE",
        "deployment_receipt_digest": "NONE",
        "deployment_valid_until": "NONE",
        "deployment_authority_source": "NONE",
        "read_authorization": "NONE",
        "deployment_role_or_profile": "NONE",
        "read_role_or_profile": "NONE",
        "read_receipt_digest": "NONE",
        "read_valid_until": "NONE",
        "read_authorized_at": "NONE",
        "read_authorized_resources": [],
        "read_authorized_operations": [],
        "read_authority_source": "NONE",
        "artifact_digest": "NONE",
        "plan_binding": "NONE",
        "resources": [],
        "mutation_operations": [],
        "read_operations_observed": [],
        "acceptance_evidence_ids": [],
        "operation_result": "NONE",
        "rollback_result": "NONE",
        "identity_and_boundary_match": "NONE",
        "blocker_or_stale_reason": "NONE",
        "basis_stale": False,
        "acknowledged": False,
        "acknowledged_evidence_id": "NONE",
        "release_evidence_cutoff": release_evidence_cutoff,
        "current_mutation_authority_status": "UNAVAILABLE",
        "issues": [],
    }
    try:
        rows = parse_deployment_reconciliation_evidence(verify_text)
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    concrete: list[dict[str, str]] = []
    invalid_identifiers: list[str] = []
    for row in rows:
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id):
            concrete.append(row)
            continue
        status = clean_cell(row.get("Status", ""))
        placeholder = (
            unresolved(evidence_id)
            and status in {"", "NOT_STARTED"}
            and all(
                unresolved(row.get(header, ""))
                for header in AWS_DEPLOYMENT_EVIDENCE_HEADERS
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
                "AWS deployment evidence has noncanonical or partially populated IDs: "
                + ", ".join(sorted(invalid_identifiers))
            ],
        }
    if not concrete:
        return base
    evidence_ids = [clean_cell(row["Evidence ID"]) for row in concrete]
    if len(evidence_ids) != len(set(evidence_ids)):
        return {
            **base,
            "status": "BLOCKED",
            "issues": ["AWS deployment evidence contains duplicate Evidence IDs"],
        }
    structural_issues: list[str] = []
    timestamps: list[datetime] = []
    groups: dict[str, list[dict[str, str]]] = {}
    attempt_order: list[str] = []
    closed_attempts: set[str] = set()
    active_attempt = ""
    for row in concrete:
        evidence_id = clean_cell(row["Evidence ID"])
        attempt_id = clean_cell(row.get("Attempt ID", ""))
        phase = clean_cell(row.get("Phase", ""))
        status = clean_cell(row.get("Status", ""))
        observed_at = iso_datetime(row.get("Observed at", ""))
        if AWS_DEPLOYMENT_ATTEMPT_ID.fullmatch(attempt_id) is None:
            structural_issues.append(f"{evidence_id} has a noncanonical Attempt ID")
        if phase == "AWS-20" and status not in AWS_DEPLOYMENT_ACTION_STATUSES:
            structural_issues.append(
                f"{evidence_id} has invalid AWS-20 status {status or 'EMPTY'}"
            )
        elif phase == "AWS-30" and status not in AWS_DEPLOYMENT_RECONCILIATION_STATUSES:
            structural_issues.append(
                f"{evidence_id} has invalid AWS-30 status {status or 'EMPTY'}"
            )
        elif phase not in {"AWS-20", "AWS-30"}:
            structural_issues.append(
                f"{evidence_id} phase must be exactly AWS-20 or AWS-30"
            )
        if observed_at is None:
            structural_issues.append(
                f"{evidence_id} Observed at must be ISO 8601 with timezone"
            )
        else:
            timestamps.append(observed_at)
        if attempt_id != active_attempt:
            if attempt_id in closed_attempts:
                structural_issues.append(
                    f"{evidence_id} reopens a noncontiguous deployment attempt"
                )
            if active_attempt:
                closed_attempts.add(active_attempt)
            active_attempt = attempt_id
            attempt_order.append(attempt_id)
        groups.setdefault(attempt_id, []).append(row)
    if len(timestamps) != len(set(timestamps)):
        structural_issues.append("AWS deployment evidence timestamps must be unique")
    if len(timestamps) == len(concrete) and timestamps != sorted(timestamps):
        structural_issues.append(
            "AWS deployment evidence must be appended in observed-time order"
        )
    replayed_authorization_ids: set[str] = set()
    replayed_receipt_digests: set[str] = set()
    for index, attempt_id in enumerate(attempt_order):
        group = groups.get(attempt_id, [])
        started = [
            row
            for row in group
            if row.get("Phase") == "AWS-20" and row.get("Status") == "STARTED"
        ]
        terminal = [
            row
            for row in group
            if row.get("Phase") == "AWS-20"
            and row.get("Status") in AWS_DEPLOYMENT_TERMINAL_STATUSES
        ]
        reconciliations = [row for row in group if row.get("Phase") == "AWS-30"]
        if len(started) != 1 or not group or group[0] not in started:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} requires exactly one first AWS-20 STARTED row"
            )
        if len(terminal) > 1:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} has more than one AWS-20 terminal row"
            )
        if reconciliations and len(terminal) != 1:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} AWS-30 requires one prior AWS-20 terminal row"
            )
        elif reconciliations:
            terminal_index = group.index(terminal[0])
            if any(group.index(row) < terminal_index for row in reconciliations):
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} AWS-30 must follow the AWS-20 terminal row"
                )
        stale_reconciliations = [
            row for row in reconciliations if row.get("Status") == "STALE"
        ]
        terminal_reconciliations = [
            row
            for row in reconciliations
            if row.get("Status") in {"COMPLETE", "BLOCKED"}
        ]
        if (
            len(reconciliations) > 2
            or len(stale_reconciliations) > 1
            or len(terminal_reconciliations) > 1
        ):
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} exceeds the bounded AWS-30 retry sequence"
            )
        if len(reconciliations) == 2:
            if reconciliations[0].get("Status") != "STALE" or reconciliations[1].get(
                "Status"
            ) not in {"COMPLETE", "BLOCKED"}:
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} AWS-30 recovery must be STALE then terminal"
                )
            if clean_cell(
                reconciliations[0].get("Read authorization", "")
            ) == clean_cell(reconciliations[1].get("Read authorization", "")):
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} AWS-30 recovery requires a fresh read authorization"
                )
        if reconciliations and group[-1] not in reconciliations:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} AWS-30 reconciliation must be last"
            )
        immutable_fields = (
            "REQ / DES / AUTH",
            "Deployment authorization",
            "Deployment receipt digest",
            "Deployment valid until",
            "Deployment authority source",
            "Deployment role or profile",
            "Artifact digest",
            "Plan/change-set binding",
            "Resources",
            "Mutation operations",
            "Account / Region / environment",
        )
        if group:
            first = group[0]
            for row in group[1:]:
                for field_name in immutable_fields:
                    if clean_cell(row.get(field_name, "")) != clean_cell(
                        first.get(field_name, "")
                    ):
                        structural_issues.append(
                            f"{attempt_id or 'EMPTY'} changes immutable {field_name}"
                        )
        authority_row = started[0] if started else group[0]
        authorization_id = clean_cell(authority_row.get("Deployment authorization", ""))
        receipt_digest = clean_cell(authority_row.get("Deployment receipt digest", ""))
        if authorization_id in replayed_authorization_ids:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} replays a deployment authorization ID"
            )
        replayed_authorization_ids.add(authorization_id)
        if receipt_digest != "NONE":
            if receipt_digest in replayed_receipt_digests:
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} replays a deployment receipt digest"
                )
            replayed_receipt_digests.add(receipt_digest)
        if index < len(attempt_order) - 1:
            if not terminal_reconciliations:
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} was not reconciled before the next attempt"
                )
    if structural_issues:
        return {**base, "status": "BLOCKED", "issues": structural_issues}

    deployment_rows_by_id = {clean_cell(row["Evidence ID"]): row for row in concrete}
    if re.fullmatch(r"EV-\d{4,}", release_evidence_cutoff):
        cutoff_row = deployment_rows_by_id.get(release_evidence_cutoff)
        try:
            verification_rows = policy.parse_verification_matrix(verify_text)
        except ValueError as exc:
            return {**base, "status": "BLOCKED", "issues": [str(exc)]}
        verification_matches = [
            row
            for row in verification_rows
            if clean_cell(row.get("Evidence ID", "")) == release_evidence_cutoff
        ]
        if (1 if cutoff_row is not None else 0) + len(verification_matches) != 1:
            return {
                **base,
                "status": "BLOCKED",
                "issues": [
                    "Active evidence cutoff must resolve exactly once across the "
                    "deployment journal and Verification matrix"
                ],
            }
        if cutoff_row is not None and not (
            cutoff_row.get("Phase") == "AWS-30"
            and cutoff_row.get("Status") in {"COMPLETE", "BLOCKED"}
        ):
            return {
                **base,
                "status": "BLOCKED",
                "issues": ["Active evidence cutoff names a nonterminal deployment row"],
            }

    if len(attempt_order) > 1:
        previous_group = groups[attempt_order[-2]]
        previous_terminal = next(
            (
                row
                for row in reversed(previous_group)
                if row.get("Phase") == "AWS-30"
                and row.get("Status") in {"COMPLETE", "BLOCKED"}
            ),
            None,
        )
        latest_group = groups[attempt_order[-1]]
        latest_terminal = next(
            (
                row
                for row in reversed(latest_group)
                if row.get("Phase") == "AWS-30"
                and row.get("Status") in {"COMPLETE", "BLOCKED"}
            ),
            None,
        )
        allowed_cutoffs = (
            {clean_cell(previous_terminal.get("Evidence ID", ""))}
            if previous_terminal is not None
            else set()
        )
        if latest_terminal is not None:
            allowed_cutoffs.add(clean_cell(latest_terminal.get("Evidence ID", "")))
        if release_evidence_cutoff not in allowed_cutoffs:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_order[-1],
                "issues": [
                    "A later deployment attempt requires the prior terminal "
                    "AWS-30 evidence cutoff acknowledged by RELEASE-10"
                ],
            }

    for historical_attempt_id in attempt_order[:-1]:
        historical_issues = _deployment_historical_group_issues(
            policy, groups[historical_attempt_id], verify_text
        )
        if historical_issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": historical_attempt_id,
                "issues": historical_issues,
            }

    expected_basis = (
        f"{requirements_revision} / {design_revision} / {construction_authorization}"
    )
    attempt_id = attempt_order[-1]
    group = groups[attempt_id]
    legacy_fast_dev = (
        lane == "fast-dev"
        and clean_cell(group[0].get("Deployment receipt digest", "")) == "NONE"
    )
    projection = _deployment_group_projection(policy, base, attempt_id, group)
    terminal_reconciliation = next(
        (
            row
            for row in reversed(group)
            if row.get("Phase") == "AWS-30"
            and row.get("Status") in {"COMPLETE", "BLOCKED"}
        ),
        None,
    )
    if terminal_reconciliation is not None:
        terminal_id = clean_cell(terminal_reconciliation["Evidence ID"])
        if (
            release_state != "READY_TO_DEPLOY"
            and release_evidence_cutoff != terminal_id
        ):
            return {
                **projection,
                "status": "BLOCKED",
                "issues": [
                    "Post-reconciliation release state requires the exact terminal AWS-30 evidence cutoff"
                ],
            }
        acknowledged = release_evidence_cutoff == terminal_id
        terminal_basis_stale = False
        if acknowledged:
            allowed_release_states = (
                {"NOT_READY"}
                if clean_cell(terminal_reconciliation.get("Status", "")) == "BLOCKED"
                or clean_cell(group[0].get("REQ / DES / AUTH", "")) != expected_basis
                else {"NOT_READY", "RELEASE_VERIFIED"}
            )
            if release_state not in allowed_release_states:
                return {
                    **projection,
                    "status": "BLOCKED",
                    "basis_stale": (
                        clean_cell(group[0].get("REQ / DES / AUTH", ""))
                        != expected_basis
                    ),
                    "issues": [
                        "Terminal AWS-30 acknowledgement must update release state "
                        "and evidence cutoff together within the reconciliation result"
                    ],
                }
            terminal_issues = _deployment_historical_group_issues(
                policy, group, verify_text
            )
        else:
            terminal_basis_stale = (
                clean_cell(group[0].get("REQ / DES / AUTH", "")) != expected_basis
            )
            restricted_read = restricted_closure or terminal_basis_stale
            terminal_read_authority = None if restricted_read else read_authority
            if terminal_read_authority is None:
                terminal_read_authority = (
                    policy.deployment_reconciliation_read_authority(
                        verify_text,
                        cost_posture,
                        group,
                        allow_expired=restricted_read,
                        require_post_action_freshness=restricted_read,
                    )
                )
            current_expected, current_binding_issues = _deployment_expected_binding(
                policy,
                verify_text,
                construction_authorization=construction_authorization,
                envelope=envelope,
                lane=lane,
                artifact_binding=artifact_binding,
                gate_b_authority_source=gate_b_authority_source,
                gate_b_authorized_at=gate_b_authorized_at,
            )
            group_key = (
                clean_cell(group[0].get("Deployment authorization", "")),
                clean_cell(group[0].get("Deployment receipt digest", "")),
            )
            current_key = (
                clean_cell(current_expected.get("authorization_id", "")),
                clean_cell(current_expected.get("receipt_digest", "")),
            )
            if terminal_basis_stale or legacy_fast_dev:
                terminal_issues = _deployment_historical_group_issues(
                    policy,
                    group,
                    verify_text,
                    current_read_authority=terminal_read_authority,
                    require_authorization_proof=True,
                    gate_b_authority_source=gate_b_authority_source,
                    gate_b_authorized_at=gate_b_authorized_at,
                )
            else:
                terminal_issues = list(current_binding_issues)
                terminal_issues.extend(
                    _deployment_authority_timing_issues(group, current_expected)
                )
                for row in group:
                    terminal_issues.extend(
                        _deployment_row_binding_issues(
                            policy,
                            row,
                            current_expected,
                            terminal_read_authority,
                        )
                    )
            if terminal_read_authority is None:
                terminal_issues.append(
                    "Unacknowledged terminal AWS-30 evidence requires its exact marked read receipt"
                )
        if terminal_issues:
            return {
                **projection,
                "status": "BLOCKED",
                "basis_stale": terminal_basis_stale,
                "issues": terminal_issues,
            }
        current_expected, current_issues = _deployment_expected_binding(
            policy,
            verify_text,
            construction_authorization=construction_authorization,
            envelope=envelope,
            lane=lane,
            artifact_binding=artifact_binding,
            gate_b_authority_source=gate_b_authority_source,
            gate_b_authorized_at=gate_b_authorized_at,
        )
        consumed_key = (
            clean_cell(group[0].get("Deployment authorization", "")),
            clean_cell(group[0].get("Deployment receipt digest", "")),
        )
        current_key = (
            clean_cell(current_expected.get("authorization_id", "")),
            clean_cell(current_expected.get("receipt_digest", "")),
        )
        if current_issues or not all(current_key):
            authority_status = "UNAVAILABLE"
        elif current_key == consumed_key:
            authority_status = "CONSUMED"
        else:
            authority_status = "FRESH"
        return {
            **projection,
            "status": "CONSUMED" if acknowledged else projection["status"],
            "acknowledged": acknowledged,
            "acknowledged_evidence_id": terminal_id if acknowledged else "NONE",
            "release_evidence_cutoff": release_evidence_cutoff,
            "current_mutation_authority_status": authority_status,
            "basis_stale": terminal_basis_stale,
        }

    group_basis = clean_cell(group[0].get("REQ / DES / AUTH", ""))
    basis_stale = group_basis != expected_basis
    reconciliation_read_authority = None
    if projection.get("status") == "RECONCILIATION_REQUIRED":
        restricted_read = restricted_closure or basis_stale
        reconciliation_read_authority = None if restricted_read else read_authority
        if reconciliation_read_authority is None:
            reconciliation_read_authority = (
                policy.deployment_reconciliation_read_authority(
                    verify_text,
                    cost_posture,
                    group,
                    allow_expired=False,
                    require_post_action_freshness=restricted_read,
                )
            )
        elif not restricted_read:
            reconciliation_read_authority = {
                **dict(reconciliation_read_authority),
                "reconciliation_only": False,
                "attempt_id": attempt_id,
            }
    if basis_stale or legacy_fast_dev:
        historical_issues = _deployment_historical_group_issues(
            policy,
            group,
            verify_text,
            current_read_authority=(
                reconciliation_read_authority
                if any(row.get("Phase") == "AWS-30" for row in group)
                else None
            ),
            require_authorization_proof=True,
            gate_b_authority_source=gate_b_authority_source,
            gate_b_authorized_at=gate_b_authorized_at,
        )
        if historical_issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "basis_stale": True,
                "issues": historical_issues,
            }
        if projection.get("status") == "ACTION_TERMINAL_REQUIRED":
            return {**projection, "basis_stale": basis_stale}
        return {
            **projection,
            "status": "RECONCILIATION_REQUIRED",
            "basis_stale": basis_stale,
            "reconciliation_read_authority": (
                dict(reconciliation_read_authority)
                if reconciliation_read_authority is not None
                else {}
            ),
            "blocker_or_stale_reason": (
                projection.get("blocker_or_stale_reason")
                if projection.get("reconciliation_status") == "STALE"
                else (
                    "Current REQ / DES / AUTH differs from the attempted action"
                    if basis_stale
                    else "Legacy fast-dev attempt requires reconciliation before new authority"
                )
            ),
        }

    expected, binding_issues = _deployment_expected_binding(
        policy,
        verify_text,
        construction_authorization=construction_authorization,
        envelope=envelope,
        lane=lane,
        artifact_binding=artifact_binding,
        gate_b_authority_source=gate_b_authority_source,
        gate_b_authorized_at=gate_b_authorized_at,
    )
    group_key = (
        clean_cell(group[0].get("Deployment authorization", "")),
        clean_cell(group[0].get("Deployment receipt digest", "")),
    )
    expected_key = (
        clean_cell(expected.get("authorization_id", "")),
        clean_cell(expected.get("receipt_digest", "")),
    )
    if group_key != expected_key:
        historical_issues = _deployment_historical_group_issues(
            policy,
            group,
            verify_text,
            require_authorization_proof=True,
            gate_b_authority_source=gate_b_authority_source,
            gate_b_authorized_at=gate_b_authorized_at,
        )
        if historical_issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "issues": historical_issues,
            }
        return {
            **projection,
            "reconciliation_read_authority": (
                dict(reconciliation_read_authority)
                if reconciliation_read_authority is not None
                else {}
            ),
        }
    binding_issues.extend(_deployment_authority_timing_issues(group, expected))
    for row in group:
        if clean_cell(row.get("REQ / DES / AUTH", "")) != expected_basis:
            binding_issues.append(
                f"{row['Evidence ID']} does not match current REQ / DES / AUTH"
            )
        binding_issues.extend(
            _deployment_row_binding_issues(
                policy, row, expected, reconciliation_read_authority
            )
        )
    if binding_issues:
        return {
            **base,
            "status": "BLOCKED",
            "attempt_id": attempt_id,
            "issues": binding_issues,
        }
    return {
        **projection,
        "reconciliation_read_authority": (
            dict(reconciliation_read_authority)
            if reconciliation_read_authority is not None
            else {}
        ),
    }


__all__ = ("derive_deployment_sequence_state",)
