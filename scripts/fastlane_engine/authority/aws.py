"""Exact AWS and external authority intersection.

Canonical inputs are approved Gate B envelopes, exact owner receipts, and observed
AWS journals. Returns bounded current or reconciliation-only authority. Side effects
are prohibited; the module never invokes AWS or broadens an owner-approved scope.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .models import (
    AWS_DEPLOYMENT_RECEIPT_FIELDS,
    AWS_PLAN_BINDING,
    AWS_PREFLIGHT_ID,
    AWS_READ_AUTHORIZATION_ID,
    AWS_READ_ONLY_OPERATION,
    AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
    AWS_TEARDOWN_RECEIPT_FIELDS,
    AuthorityEvaluationInput,
    AwsAuthorityPolicy,
    GateBAuthorityBounds,
    _action_authorization_rows,
    _authorization_valid_until,
    _exact_receipt_fields,
    _gate_b_rollback_value,
    _iso_datetime,
    _mutation_cost_within_gate_b,
    _parse_cost_ceiling,
    _read_bound_honors_cost_posture,
    _receipt_artifact_matches_gate_b,
    _receipt_identity_matches_gate_b,
    _receipt_scope_within_gate_b,
    _receipt_validity_within_gate_b,
    _split_authority_values,
    explicit_human_approver,
)
from ..core.ids import clean_cell, explicit_timestamp, explicit_value, unresolved
from .receipts import marked_receipt


def _read_preflight_receipt_authority(
    authority_input: AuthorityEvaluationInput,
    bounds: GateBAuthorityBounds,
    construction_authorization: str,
    *,
    allow_one_operation: bool = True,
    allow_expired: bool = False,
) -> dict[str, Any] | None:
    """SAFETY: project one exact owner-authored read-only preflight scope."""

    evaluation_time = authority_input.observed_at
    verify_text = authority_input.verify_text
    try:
        receipt = marked_receipt(verify_text, "aws-read-preflight")
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS READ-ONLY PREFLIGHT",
        AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
    )
    row = _action_authorization_rows(verify_text).get("Read-only preflight")
    if fields is None or row is None or unresolved(receipt):
        return None
    authorization_id = fields["Read authorization"]
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    result = clean_cell(row.get("Result", ""))
    valid_until = _receipt_validity_within_gate_b(
        fields["Valid until"],
        result,
        bounds,
        observed_at=evaluation_time,
        allow_expired=allow_expired,
    )
    if valid_until == "ONE_OPERATION" and not allow_one_operation:
        return None
    cost_validity = clean_cell(row.get("Cost ceiling and validity", ""))
    cost_match = re.fullmatch(
        r"COST: (?P<effect>.+?); BOUNDED_BY: (?P<bound>.+?); VALID_UNTIL: (?P<until>.+)",
        cost_validity,
    )
    valid_cost_provenance = bool(
        cost_match
        and explicit_value(cost_match.group("effect"), allow_none=False)
        and explicit_value(cost_match.group("bound"), allow_none=False)
        and not clean_cell(cost_match.group("effect")).startswith("NOT_APPLICABLE")
        and not clean_cell(cost_match.group("bound")).startswith("NOT_APPLICABLE")
        and _read_bound_honors_cost_posture(
            cost_match.group("bound"),
            bounds,
        )
        and clean_cell(cost_match.group("until")) == fields["Valid until"]
    )
    read_cost = (
        f"EXPECTED: {clean_cell(cost_match.group('effect'))}; "
        f"BOUNDED_BY: {clean_cell(cost_match.group('bound'))}"
        if cost_match
        else "NONE"
    )
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    expected_resources = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed read-only operations']}"
    )
    observed_at = clean_cell(row.get("Observed at", ""))
    if (
        AWS_READ_AUTHORIZATION_ID.fullmatch(authorization_id) is None
        or fields["Construction authorization"] != construction_authorization
        or fields["Prohibited operations"] != "ALL_MUTATIONS"
        or row.get("Authorization ID") != authorization_id
        or row.get("Construction AUTH") != construction_authorization
        or row.get("Role or profile") != fields["Profile or role"]
        or row.get("Artifact digest") != fields["Artifact digest"]
        or row.get("Account / Region / environment") != expected_scope
        or row.get("Resources and operations") != expected_resources
        or row.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(row.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(row.get("Stable owner-message source", ""))
        or not explicit_timestamp(observed_at)
        or clean_cell(row.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or not valid_cost_provenance
        or valid_until is None
        or result not in {"AUTHORIZED", "RUNNING", "READY"}
    ):
        return None
    resources = _split_authority_values(fields["Stack, application, and resources"])
    operations = _split_authority_values(fields["Allowed read-only operations"])
    if (
        not resources
        or not operations
        or any(AWS_READ_ONLY_OPERATION.fullmatch(item) is None for item in operations)
        or not _receipt_identity_matches_gate_b(fields, bounds)
        or not _receipt_scope_within_gate_b(resources, operations, bounds)
        or not _receipt_artifact_matches_gate_b(fields["Artifact digest"], bounds)
    ):
        return None
    return {
        "kind": "AWS_READ_ONLY",
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "account": fields["Account"],
        "region": fields["Region"],
        "environment": fields["Environment"],
        "role_or_profile": fields["Profile or role"],
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {
            "artifact": fields["Artifact digest"],
            "plan": "NONE",
        },
        "cost_ceiling": read_cost,
        "rollback_boundary": "NONE",
        "expiration": valid_until,
        "authorized_at": observed_at,
        "authority_source": clean_cell(row.get("Stable owner-message source", "")),
    }


def _deployment_values(
    value: str,
    label: str,
    *,
    allow_none: bool,
) -> list[str]:
    """Return a unique wildcard-free list for historical authority checks."""

    cleaned = clean_cell(value)
    if allow_none and cleaned == "NONE":
        return []
    values = _split_authority_values(cleaned)
    if (
        not values
        or len(values) != len(set(values))
        or any("*" in item for item in values)
    ):
        raise ValueError(f"{label} must be a unique wildcard-free exact list")
    return values


def _deployment_reconciliation_read_authority(
    authority_input: AuthorityEvaluationInput,
    bounds: GateBAuthorityBounds,
    group: list[dict[str, str]],
    *,
    allow_expired: bool = False,
    require_post_action_freshness: bool = False,
) -> dict[str, Any] | None:
    """SAFETY: project exact read-only scope for current or restricted reconciliation."""

    evaluation_time = authority_input.observed_at
    verify_text = authority_input.verify_text
    if not group:
        return None
    first = group[0]
    basis_match = re.fullmatch(
        r"REQ-\d{4,} / DES-\d{4,} / (?P<auth>AUTH-\d{4,})",
        clean_cell(first.get("REQ / DES / AUTH", "")),
    )
    scope_match = re.fullmatch(
        r"ACCOUNT: (?P<account>[^;]+); REGION: (?P<region>[^;]+); "
        r"ENVIRONMENT: (?P<environment>[^;]+)",
        clean_cell(first.get("Account / Region / environment", "")),
    )
    if basis_match is None or scope_match is None:
        return None
    account = clean_cell(scope_match.group("account"))
    region = clean_cell(scope_match.group("region"))
    environment = clean_cell(scope_match.group("environment"))
    artifact = clean_cell(first.get("Artifact digest", ""))
    if (
        any(
            not explicit_value(value, allow_none=False) or "*" in value
            for value in (account, region, environment)
        )
        or re.fullmatch(r"sha256:[0-9a-f]{64}", artifact) is None
    ):
        return None
    try:
        attempted_resources = _deployment_values(
            first.get("Resources", ""), "Resources", allow_none=False
        )
        receipt = marked_receipt(verify_text, "aws-read-preflight")
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS READ-ONLY PREFLIGHT",
        AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
    )
    row = _action_authorization_rows(verify_text).get("Read-only preflight")
    if fields is None or row is None or unresolved(receipt):
        return None
    authorization_id = fields["Read authorization"]
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    result = clean_cell(row.get("Result", ""))
    valid_until = _authorization_valid_until(
        fields["Valid until"],
        result,
        observed_at=evaluation_time,
        allow_expired=allow_expired,
    )
    if valid_until in {None, "ONE_OPERATION"}:
        return None
    cost_validity = clean_cell(row.get("Cost ceiling and validity", ""))
    cost_match = re.fullmatch(
        r"COST: (?P<effect>.+?); BOUNDED_BY: (?P<bound>.+?); VALID_UNTIL: (?P<until>.+)",
        cost_validity,
    )
    valid_cost_provenance = bool(
        cost_match
        and explicit_value(cost_match.group("effect"), allow_none=False)
        and explicit_value(cost_match.group("bound"), allow_none=False)
        and not clean_cell(cost_match.group("effect")).startswith("NOT_APPLICABLE")
        and not clean_cell(cost_match.group("bound")).startswith("NOT_APPLICABLE")
        and _read_bound_honors_cost_posture(
            cost_match.group("bound"),
            bounds,
            require_gate_ceiling=False,
        )
        and clean_cell(cost_match.group("until")) == fields["Valid until"]
    )
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    expected_resources = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed read-only operations']}"
    )
    observed_at = clean_cell(row.get("Observed at", ""))
    authorized_at = _iso_datetime(observed_at)
    if (
        AWS_READ_AUTHORIZATION_ID.fullmatch(authorization_id) is None
        or fields["Construction authorization"] != basis_match.group("auth")
        or fields["Prohibited operations"] != "ALL_MUTATIONS"
        or fields["Account"] != account
        or fields["Region"] != region
        or fields["Environment"] != environment
        or fields["Artifact digest"] != artifact
        or row.get("Authorization ID") != authorization_id
        or row.get("Construction AUTH") != basis_match.group("auth")
        or row.get("Role or profile") != fields["Profile or role"]
        or row.get("Artifact digest") != artifact
        or row.get("Account / Region / environment") != expected_scope
        or row.get("Resources and operations") != expected_resources
        or row.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(row.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(
            row.get("Stable owner-message source", ""), allow_none=False
        )
        or "*" in clean_cell(row.get("Stable owner-message source", ""))
        or authorized_at is None
        or clean_cell(row.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or not valid_cost_provenance
        or result not in {"AUTHORIZED", "RUNNING", "READY"}
    ):
        return None
    resources = _split_authority_values(fields["Stack, application, and resources"])
    operations = _split_authority_values(fields["Allowed read-only operations"])
    if (
        not resources
        or not operations
        or len(resources) != len(set(resources))
        or len(operations) != len(set(operations))
        or any("*" in item for item in resources + operations)
        or set(resources) != set(attempted_resources)
        or any(AWS_READ_ONLY_OPERATION.fullmatch(item) is None for item in operations)
    ):
        return None

    if require_post_action_freshness:
        terminal_reconciliation = (
            group[-1]
            if clean_cell(group[-1].get("Phase", "")) == "AWS-30"
            and clean_cell(group[-1].get("Status", "")) in {"COMPLETE", "BLOCKED"}
            else None
        )
        if terminal_reconciliation is None:
            prior_times = [_iso_datetime(item.get("Observed at", "")) for item in group]
            if any(item is None for item in prior_times) or authorized_at <= max(
                prior_times
            ):
                return None
        else:
            prior_times = [
                _iso_datetime(item.get("Observed at", "")) for item in group[:-1]
            ]
            terminal_at = _iso_datetime(terminal_reconciliation.get("Observed at", ""))
            if (
                not prior_times
                or any(item is None for item in prior_times)
                or terminal_at is None
                or authorized_at <= max(prior_times)
                or authorized_at > terminal_at
            ):
                return None

    read_cost = (
        f"EXPECTED: {clean_cell(cost_match.group('effect'))}; "
        f"BOUNDED_BY: {clean_cell(cost_match.group('bound'))}"
        if cost_match
        else "NONE"
    )
    return {
        "kind": "AWS_READ_ONLY",
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "account": account,
        "region": region,
        "environment": environment,
        "role_or_profile": fields["Profile or role"],
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {"artifact": artifact, "plan": "NONE"},
        "cost_ceiling": read_cost,
        "rollback_boundary": "NONE",
        "expiration": valid_until,
        "authorized_at": observed_at,
        "authority_source": clean_cell(row.get("Stable owner-message source", "")),
        "reconciliation_only": require_post_action_freshness,
        "attempt_id": clean_cell(first.get("Attempt ID", "")),
    }


def _teardown_reconciliation_read_authority(
    authority_input: AuthorityEvaluationInput,
    bounds: GateBAuthorityBounds,
    group: list[dict[str, str]],
    attempt_id: str,
    *,
    restricted_closure: bool,
) -> dict[str, Any] | None:
    """Project current read authority for one immutable teardown attempt."""

    if not group:
        return None
    try:
        receipt = marked_receipt(authority_input.verify_text, "aws-read-preflight")
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS READ-ONLY PREFLIGHT",
        AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
    )
    if fields is None:
        return None
    synthetic_group = [
        {
            **row,
            "Artifact digest": fields["Artifact digest"],
            "Resources": row.get("Resources proposed to remove", ""),
        }
        for row in group
    ]
    authority = _deployment_reconciliation_read_authority(
        authority_input,
        bounds,
        synthetic_group,
        allow_expired=False,
        require_post_action_freshness=restricted_closure,
    )
    if authority is None:
        return None
    return {
        **authority,
        "attempt_id": attempt_id,
        "reconciliation_only": restricted_closure,
    }


def build_aws_authority_policy(
    authority_input: AuthorityEvaluationInput | None = None,
    bounds: GateBAuthorityBounds | None = None,
    *,
    parse_verification_matrix: Callable[[str], list[dict[str, str]]] | None = None,
) -> AwsAuthorityPolicy:
    """Bind AWS evaluators to one immutable normalized authority basis."""

    if authority_input is None:
        authority_input = AuthorityEvaluationInput(
            has_errors=False,
            observed_at=datetime.now(timezone.utc),
            verify_text="",
        )
    if bounds is None:
        bounds = GateBAuthorityBounds()
    verification_parser = parse_verification_matrix or (lambda _text: [])

    def envelope_scalar(
        _envelope: Mapping[str, str], field: str, _label: str
    ) -> str | None:
        return {
            "AWS account": bounds.account,
            "AWS Region": bounds.region,
            "AWS role or profile": bounds.role_or_profile,
        }.get(field)

    def envelope_values(
        _envelope: Mapping[str, str], field: str, _label: str
    ) -> list[str]:
        return list(
            {
                "AWS resource allowlist": bounds.resources,
                "AWS allowed operations": bounds.operations,
            }.get(field, ())
        )

    def deployment_reconciliation(
        _verify_text: str,
        _cost_posture: str,
        group: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        return _deployment_reconciliation_read_authority(
            authority_input, bounds, group, **kwargs
        )

    def teardown_reconciliation(
        _verify_text: str,
        _cost_posture: str,
        group: list[dict[str, str]],
        attempt_id: str,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        return _teardown_reconciliation_read_authority(
            authority_input, bounds, group, attempt_id, **kwargs
        )

    return AwsAuthorityPolicy(
        bounds=bounds,
        split_authority_values=_split_authority_values,
        action_authorization_rows=_action_authorization_rows,
        exact_receipt_fields=_exact_receipt_fields,
        envelope_scalar=envelope_scalar,
        envelope_values=envelope_values,
        receipt_identity_matches_gate_b=lambda fields, _envelope: (
            _receipt_identity_matches_gate_b(fields, bounds)
        ),
        receipt_scope_within_gate_b=lambda resources, operations, _envelope: (
            _receipt_scope_within_gate_b(resources, operations, bounds)
        ),
        receipt_artifact_matches_gate_b=lambda artifact, _envelope, _active: (
            _receipt_artifact_matches_gate_b(artifact, bounds)
        ),
        gate_b_rollback_value=lambda _envelope: _gate_b_rollback_value(bounds),
        deployment_reconciliation_read_authority=deployment_reconciliation,
        teardown_reconciliation_read_authority=teardown_reconciliation,
        parse_verification_matrix=verification_parser,
        explicit_human_approver=explicit_human_approver,
        marked_receipt=marked_receipt,
        parse_aws_environment=lambda _value: (
            bounds.environment or "",
            "NORMALIZED",
        ),
    )


def _receipt_external_authority(
    authority_input: AuthorityEvaluationInput,
    bounds: GateBAuthorityBounds,
    action: str,
    construction_authorization: str,
    *,
    preflight: Mapping[str, Any] | None = None,
    teardown_review: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """SAFETY: intersect one exact mutation receipt with the Gate B envelope."""

    evaluation_time = authority_input.observed_at
    verify_text = authority_input.verify_text
    if action not in {"Deployment", "Teardown"}:
        return None
    deployment = action == "Deployment"
    gate = "aws-deployment" if deployment else "aws-teardown"
    title = "AUTHORIZE AWS DEPLOYMENT" if deployment else "AUTHORIZE AWS TEARDOWN"
    expected_fields = (
        AWS_DEPLOYMENT_RECEIPT_FIELDS if deployment else AWS_TEARDOWN_RECEIPT_FIELDS
    )
    allow_none_fields = (
        frozenset({"Rollback boundary"})
        if deployment
        else frozenset({"Resources and data to retain", "Shared dependencies"})
    )
    try:
        receipt = marked_receipt(verify_text, gate)
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        title,
        expected_fields,
        allow_none_fields=allow_none_fields,
    )
    row = _action_authorization_rows(verify_text).get(action)
    if fields is None or row is None or unresolved(receipt):
        return None
    auth_key = "AWS authorization" if deployment else "Teardown authorization"
    authorization_id = fields.get(auth_key, "")
    expected_pattern = r"AWS-AUTH-\d{4,}" if deployment else r"TEARDOWN-AUTH-\d{4,}"
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    result = clean_cell(row.get("Result", ""))
    valid_until = _receipt_validity_within_gate_b(
        fields.get("Valid until", ""),
        result,
        bounds,
        observed_at=evaluation_time,
    )
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    resources_field = (
        "Stack, application, and resources"
        if deployment
        else "Stack, application, and resources to remove"
    )
    operations_field = (
        "Allowed operations" if deployment else "Allowed deletion operations"
    )
    resources = _split_authority_values(fields[resources_field])
    operations = _split_authority_values(fields[operations_field])
    expected_resources = (
        f"RESOURCES: {fields[resources_field]}; OPERATIONS: {fields[operations_field]}"
    )
    observed_at = clean_cell(row.get("Observed at", ""))
    if (
        re.fullmatch(expected_pattern, authorization_id) is None
        or fields.get("Construction authorization") != construction_authorization
        or row.get("Authorization ID") != authorization_id
        or row.get("Construction AUTH") != construction_authorization
        or row.get("Role or profile") != fields.get("Profile or role")
        or row.get("Approver") != fields.get("Approver")
        or not explicit_human_approver(fields.get("Approver", ""))
        or clean_cell(row.get("Verbatim receipt SHA-256", "")) != digest
        or clean_cell(row.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or row.get("Account / Region / environment") != expected_scope
        or row.get("Resources and operations") != expected_resources
        or not explicit_value(
            row.get("Stable owner-message source", ""), allow_none=False
        )
        or not explicit_timestamp(observed_at)
        or valid_until is None
        or result not in {"AUTHORIZED", "READY"}
        or not _receipt_identity_matches_gate_b(fields, bounds)
        or not _receipt_scope_within_gate_b(resources, operations, bounds)
    ):
        return None
    if deployment:
        artifact = fields["Artifact digest"]
        plan = fields["IaC plan/change-set binding"]
        cost_ceiling = fields["Cost ceiling"]
        rollback = fields["Rollback boundary"]
        preflight_id = clean_cell(
            preflight.get("preflight_id", "") if preflight else ""
        )
        expected_cost_validity = (
            f"COST: {cost_ceiling}; VALID_UNTIL: {fields['Valid until']}"
        )
        if (
            preflight is None
            or preflight.get("status") != "READY"
            or preflight.get("account_access") != "READ_ONLY_OBSERVED"
            or AWS_PREFLIGHT_ID.fullmatch(preflight_id) is None
            or clean_cell(row.get("Preflight evidence", "")) != preflight_id
            or row.get("Artifact digest") != artifact
            or row.get("IaC plan/change-set binding") != plan
            or row.get("Cost ceiling and validity") != expected_cost_validity
            or row.get("Rollback boundary") != rollback
            or AWS_PLAN_BINDING.fullmatch(plan) is None
            or not _receipt_artifact_matches_gate_b(artifact, bounds)
            or not _mutation_cost_within_gate_b(cost_ceiling, bounds)
            or rollback != _gate_b_rollback_value(bounds)
        ):
            return None
        kind = "AWS_DEPLOYMENT"
        retained_resources: list[str] = []
        shared_dependencies: list[str] = []
        cost_effect = "NONE"
        post_action_verification = "NONE"
        teardown_ready_binding = None
    else:
        teardown_review = teardown_review or {}
        evidence_id = clean_cell(teardown_review.get("evidence_id", ""))
        retained_resources = _split_authority_values(
            fields["Resources and data to retain"]
        )
        shared_dependencies = _split_authority_values(fields["Shared dependencies"])
        cost_effect = fields["Cost effect"]
        post_action_verification = fields["Post-teardown verification"]
        expected_cost_validity = (
            f"COST: {cost_effect}; VALID_UNTIL: {fields['Valid until']}"
        )
        teardown_artifact = "NOT_APPLICABLE — teardown binds the observed inventory"
        teardown_plan = "NOT_APPLICABLE — teardown uses its removal/retention manifest"
        overlap = (
            set(resources).intersection(retained_resources)
            or set(resources).intersection(shared_dependencies)
            or set(retained_resources).intersection(shared_dependencies)
        )
        unsafe_lists = any(
            "*" in item
            for item in resources
            + operations
            + retained_resources
            + shared_dependencies
        )
        if (
            teardown_review.get("status") != "READY_FOR_TEARDOWN"
            or re.fullmatch(r"EV-\d{4,}", evidence_id) is None
            or clean_cell(row.get("Preflight evidence", "")) != evidence_id
            or row.get("Artifact digest") != teardown_artifact
            or row.get("IaC plan/change-set binding") != teardown_plan
            or row.get("Cost ceiling and validity") != expected_cost_validity
            or row.get("Rollback boundary") != post_action_verification
            or resources != list(teardown_review.get("resources_to_remove", []))
            or operations != list(teardown_review.get("allowed_operations", []))
            or retained_resources
            != list(teardown_review.get("resources_to_retain", []))
            or shared_dependencies
            != list(teardown_review.get("shared_dependencies", []))
            or cost_effect != teardown_review.get("cost_effect")
            or post_action_verification
            != teardown_review.get("post_action_verification")
            or fields["Profile or role"] != teardown_review.get("role_or_profile")
            or fields["Account"] != teardown_review.get("account")
            or fields["Region"] != teardown_review.get("region")
            or fields["Environment"] != teardown_review.get("environment")
            or clean_cell(teardown_review.get("identity_and_boundary_match", ""))
            not in {"PASS", "VERIFIED"}
            or overlap
            or unsafe_lists
            or len(retained_resources) != len(set(retained_resources))
            or len(shared_dependencies) != len(set(shared_dependencies))
        ):
            return None
        artifact = teardown_artifact
        plan = teardown_plan
        cost_ceiling = bounds.aws_cost_ceiling_raw
        rollback = (
            f"ROLLBACK: {bounds.rollback_boundary}"
            if bounds.rollback_boundary
            else "NONE"
        )
        if (
            _parse_cost_ceiling(cost_ceiling) is None
            or _gate_b_rollback_value(bounds) is None
        ):
            return None
        kind = "AWS_TEARDOWN"
        teardown_ready_binding = {
            "evidence_id": evidence_id,
            "read_authorization": clean_cell(
                teardown_review.get("read_authorization", "")
            ),
            "read_role_or_profile": clean_cell(
                teardown_review.get("read_role_or_profile", "")
            ),
            "read_receipt_digest": clean_cell(
                teardown_review.get("read_receipt_digest", "")
            ),
            "read_valid_until": clean_cell(teardown_review.get("read_valid_until", "")),
            "read_authority_source": clean_cell(
                teardown_review.get("read_authority_source", "")
            ),
            "expected_manifest_or_stack": clean_cell(
                teardown_review.get("expected_manifest_or_stack", "")
            ),
            "resources_retained": retained_resources,
            "shared_dependencies": shared_dependencies,
            "cost_effect": cost_effect,
            "post_teardown_verification": post_action_verification,
        }
    return {
        "kind": kind,
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "account": fields["Account"],
        "region": fields["Region"],
        "environment": fields["Environment"],
        "role_or_profile": fields["Profile or role"],
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {"artifact": artifact, "plan": plan},
        "cost_ceiling": cost_ceiling,
        "rollback_boundary": rollback,
        "expiration": valid_until,
        "retained_resources": retained_resources,
        "shared_dependencies": shared_dependencies,
        "cost_effect": cost_effect,
        "post_action_verification": post_action_verification,
        "teardown_ready_binding": teardown_ready_binding,
    }


def derive_external_authority(
    authority_input: AuthorityEvaluationInput,
    bounds: GateBAuthorityBounds,
    lane: str | None,
    construction_authorization: str,
    *,
    aws_progress_state: str | None = None,
    preflight: Mapping[str, Any] | None = None,
    aws_action_phase: str | None = None,
    teardown_review: Mapping[str, Any] | None = None,
    deployment_sequence: Mapping[str, Any] | None = None,
    read_authority_deriver: Callable[..., dict[str, Any] | None] | None = None,
    action_authority_deriver: Callable[..., dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """SAFETY: project exact current AWS authority without creating authority."""

    if read_authority_deriver is None:

        def read_authority_fn(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
            return _read_preflight_receipt_authority(*args, **kwargs)
    else:
        read_authority_fn = read_authority_deriver
    if action_authority_deriver is None:

        def action_authority(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
            return _receipt_external_authority(*args, **kwargs)
    else:
        action_authority = action_authority_deriver
    empty: dict[str, Any] = {
        "kind": "NONE",
        "validity": "NONE",
        "authorization_id": "NONE",
        "receipt_digest": "NONE",
        "account": "NONE",
        "region": "NONE",
        "environment": "NONE",
        "role_or_profile": "NONE",
        "resources": [],
        "operations": [],
        "artifact_plan_binding": {"artifact": "NONE", "plan": "NONE"},
        "cost_ceiling": "NONE",
        "rollback_boundary": "NONE",
        "expiration": "NONE",
    }
    if aws_action_phase == "AWS-30" and deployment_sequence is not None:
        if authority_input.has_errors or deployment_sequence.get("issues"):
            return empty
        reconciliation_authority = deployment_sequence.get(
            "reconciliation_read_authority"
        )
        if (
            isinstance(reconciliation_authority, Mapping)
            and reconciliation_authority.get("kind") == "AWS_READ_ONLY"
            and reconciliation_authority.get("validity") == "CURRENT"
            and reconciliation_authority.get("reconciliation_only") in {True, False}
            and reconciliation_authority.get("attempt_id")
            == deployment_sequence.get("attempt_id")
        ):
            return dict(reconciliation_authority)
        if (
            clean_cell(deployment_sequence.get("status", ""))
            == "RECONCILIATION_REQUIRED"
        ):
            required = dict(empty)
            required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
            required["validity"] = "REQUIRED"
            return required
        return empty
    if (
        aws_action_phase == "AWS-40"
        and teardown_review is not None
        and clean_cell(teardown_review.get("status", "")) == "POST_ACTION_REVIEW"
    ):
        if authority_input.has_errors or teardown_review.get("issues"):
            return empty
        reconciliation_authority = teardown_review.get("reconciliation_read_authority")
        if (
            isinstance(reconciliation_authority, Mapping)
            and reconciliation_authority.get("kind") == "AWS_READ_ONLY"
            and reconciliation_authority.get("validity") == "CURRENT"
            and reconciliation_authority.get("reconciliation_only") in {True, False}
            and reconciliation_authority.get("attempt_id")
            == teardown_review.get("attempt_id")
        ):
            return dict(reconciliation_authority)
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if (
        authority_input.has_errors
        or not bounds.valid
        or construction_authorization == "NONE"
    ):
        return empty
    if aws_action_phase not in {"AWS-10", "AWS-20", "AWS-30", "AWS-40", "AWS-50"}:
        return empty
    if aws_action_phase == "AWS-10" and aws_progress_state == "AWS_READ_SCOPE_REQUIRED":
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if aws_action_phase == "AWS-10" and aws_progress_state == "AWS_PREFLIGHT_RUNNING":
        read_authority = read_authority_fn(
            authority_input,
            bounds,
            construction_authorization,
        )
        if read_authority is not None:
            return read_authority
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if (
        aws_action_phase == "AWS-10"
        and aws_progress_state == "AWS_PREFLIGHT_READY"
        and lane == "read-only"
    ):
        read_authority = read_authority_fn(
            authority_input,
            bounds,
            construction_authorization,
        )
        return read_authority if read_authority is not None else empty
    if aws_action_phase in {"AWS-30", "AWS-40"}:
        read_authority = read_authority_fn(
            authority_input,
            bounds,
            construction_authorization,
            allow_one_operation=False,
        )
        if read_authority is not None:
            return read_authority
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    boundary = bounds.boundary
    if boundary not in {"READ_ONLY", "MUTATE_LISTED_RESOURCES"}:
        return empty
    if boundary == "READ_ONLY":
        # Gate B bounds the project but never substitutes for the exact
        # owner-authored preflight receipt required for authenticated reads.
        return empty
    if aws_action_phase == "AWS-50":
        if clean_cell((teardown_review or {}).get("status", "")) in {
            "ACTION_TERMINAL_REQUIRED",
            "POST_ACTION_REVIEW",
            "VERIFIED_CLEAN",
            "RESIDUALS_REMAIN",
            "BLOCKED",
        }:
            return empty
        authority = action_authority(
            authority_input,
            bounds,
            "Teardown",
            construction_authorization,
            teardown_review=teardown_review,
        )
        if authority is not None:
            return authority
        required = dict(empty)
        required["kind"] = "AWS_ACTION_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if aws_action_phase != "AWS-20":
        return empty
    preflight_ready = bool(
        preflight is not None
        and preflight.get("status") == "READY"
        and preflight.get("account_access") == "READ_ONLY_OBSERVED"
        and AWS_PREFLIGHT_ID.fullmatch(clean_cell(preflight.get("preflight_id", "")))
        is not None
    )
    if lane == "explicit-gate" and boundary == "MUTATE_LISTED_RESOURCES":
        if aws_progress_state != "WAITING_AWS_MUTATION_AUTH" or not preflight_ready:
            return empty
        candidates = [
            item
            for item in (
                action_authority(
                    authority_input,
                    bounds,
                    "Deployment",
                    construction_authorization,
                    preflight=preflight,
                ),
            )
            if item is not None
        ]
        if len(candidates) == 1:
            candidate = candidates[0]
            consumed = deployment_sequence or {}
            same_consumed_authority = (
                clean_cell(consumed.get("status", "")) == "CONSUMED"
                and clean_cell(consumed.get("deployment_authorization", ""))
                == clean_cell(candidate.get("authorization_id", ""))
                and clean_cell(consumed.get("deployment_receipt_digest", ""))
                == clean_cell(candidate.get("receipt_digest", ""))
            )
            if not same_consumed_authority:
                return candidate
            candidates = []
        required = dict(empty)
        required["kind"] = "AWS_ACTION_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED" if not candidates else "CONFLICTING"
        return required
    if boundary != "MUTATE_LISTED_RESOURCES" or lane != "fast-dev":
        return empty
    if aws_progress_state != "AWS_PREFLIGHT_READY" or not preflight_ready:
        return empty
    expiration = bounds.aws_authorization_expires_at
    if expiration is None or expiration <= authority_input.observed_at:
        return empty
    environment_name = bounds.environment
    account = bounds.account
    region = bounds.region
    role = bounds.role_or_profile
    resources = list(bounds.resources)
    allowed_operations = list(bounds.operations)
    operations = [
        operation
        for operation in allowed_operations
        if AWS_READ_ONLY_OPERATION.fullmatch(operation) is None
    ]
    if (
        account is None
        or not operations
        or region is None
        or role is None
        or clean_cell(preflight.get("account", "")) != account
        or clean_cell(preflight.get("region", "")) != region
        or clean_cell(preflight.get("environment", "")) != environment_name
        or not _receipt_artifact_matches_gate_b(bounds.active_artifact, bounds)
        or not _receipt_scope_within_gate_b(resources, operations, bounds)
    ):
        return empty
    kind = "FAST_DEV_GATE_B"
    cost_ceiling = bounds.aws_cost_ceiling_raw
    if not _mutation_cost_within_gate_b(cost_ceiling, bounds):
        return empty
    parsed_cost = _parse_cost_ceiling(cost_ceiling)
    if parsed_cost is None:
        return empty
    currency, amount = parsed_cost
    cost_ceiling = f"{currency}: {amount:.2f}"
    return {
        "kind": kind,
        "validity": "CURRENT",
        "authorization_id": construction_authorization,
        "receipt_digest": "NONE",
        "account": account,
        "region": region,
        "environment": environment_name,
        "role_or_profile": role,
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {
            "artifact": bounds.active_artifact,
            "plan": bounds.stack_or_application,
        },
        "cost_ceiling": cost_ceiling,
        "rollback_boundary": (
            f"ROLLBACK: {bounds.rollback_boundary}"
            if bounds.rollback_boundary
            else "NONE"
        ),
        "expiration": expiration.isoformat(),
    }
