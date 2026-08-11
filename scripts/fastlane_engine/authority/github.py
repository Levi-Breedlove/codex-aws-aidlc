"""GitHub/request matching and current prompt capability projections.

Canonical inputs are normalized external authority and reviewed execution records.
Returns deterministic request matches and maximum prompt modes. Side effects are
prohibited; the module never calls GitHub/AWS or turns capability into authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from ..core.contracts import markdown_tables
from ..core.ids import clean_cell, explicit_value, unresolved
from ..project_inspection import AWS_BOUNDARIES, AWS_LANES, VERIFY_FILE, Context
from .models import (
    AWS_DEPLOYMENT_ATTEMPT_ID,
    AWS_TEARDOWN_ATTEMPT_ID,
    _iso_datetime,
    _split_authority_values,
)

AWS_EXECUTION_CONTRACT_HEADERS = (
    "Execution ID",
    "Authority kind",
    "Authorization ID",
    "Receipt digest",
    "Script SHA-256",
    "Immutable artifact SHA-256",
    "Expected operations",
    "Resources",
    "Account",
    "Region",
    "Environment",
    "Role or profile",
    "Artifact digest",
    "Plan binding",
    "Cost ceiling",
    "Rollback boundary",
    "Valid until",
    "Evidence destination",
    "Status",
)


PROMPT_DOCS_ONLY_AWS_MODES = frozenset({"REQ-10", "DESIGN-10", "BUG-10"})


PROMPT_READ_ONLY_AWS_MODES = frozenset({"AWS-10", "AWS-30", "AWS-40"})


PROMPT_MUTATION_AWS_MODES = frozenset({"AWS-20", "AWS-50"})


def _machine_value(value: Any, *labels: str) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = clean_cell(value)
    if cleaned == "NONE" or unresolved(cleaned) or cleaned.startswith("NOT_APPLICABLE"):
        return None
    for label in labels:
        prefix = label + ":"
        if cleaned.startswith(prefix):
            candidate = clean_cell(cleaned[len(prefix) :])
            return candidate if explicit_value(candidate) else None
    return cleaned if explicit_value(cleaned) else None


def _machine_list(values: Any, label: str) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        normalized = _machine_value(value, label)
        if normalized is not None and normalized not in result:
            result.append(normalized)
    return result


def _machine_cost(value: Any) -> dict[str, str] | None:
    normalized = _machine_value(value)
    if normalized is None:
        return None
    match = re.fullmatch(
        r"(?P<currency>[A-Z]{3}):\s*(?P<amount>\d+(?:\.\d{1,2})?)", normalized
    )
    if match is None:
        return None
    try:
        amount = Decimal(match.group("amount"))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return {"currency": match.group("currency"), "amount": f"{amount:.2f}"}


def _execution_contract_rows(verify_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    expected = list(AWS_EXECUTION_CONTRACT_HEADERS)
    for table in markdown_tables(verify_text):
        if not table or table[0] != expected:
            continue
        for cells in table[2:]:
            if len(cells) == len(expected):
                rows.append(dict(zip(expected, cells)))
    return rows


def _reviewed_script_contract(
    ctx: Context, request_match: dict[str, Any]
) -> dict[str, Any] | None:
    """SAFETY: require a reviewed script contract to match the request exactly."""

    rows = [
        row
        for row in _execution_contract_rows(ctx.texts.get(VERIFY_FILE, ""))
        if re.fullmatch(r"AWS-EXEC-\d{4,}", clean_cell(row["Execution ID"]))
    ]
    if not rows:
        return None
    ids = [clean_cell(row["Execution ID"]) for row in rows]
    if len(ids) != len(set(ids)):
        ctx.warning(
            "AWS_EXECUTION_CONTRACT_INVALID",
            "Reviewed AWS execution contracts contain a duplicate AWS-EXEC ID",
            VERIFY_FILE,
        )
        return None
    authorization_id = request_match.get("authorization_id") or "NONE"
    candidates = [
        row for row in rows if clean_cell(row["Authorization ID"]) == authorization_id
    ]
    if len(candidates) != 1:
        ctx.warning(
            "AWS_EXECUTION_CONTRACT_INVALID",
            f"Expected one current AWS-EXEC contract for {authorization_id}; found {len(candidates)}",
            VERIFY_FILE,
        )
        return None
    row = candidates[0]
    execution_id = clean_cell(row["Execution ID"])
    issues: list[str] = []

    expected_scalars = {
        "Authority kind": request_match.get("authority_kind") or "NONE",
        "Receipt digest": request_match.get("receipt_digest") or "NONE",
        "Account": request_match.get("account") or "NONE",
        "Region": request_match.get("region") or "NONE",
        "Environment": request_match.get("environment") or "NONE",
        "Role or profile": request_match.get("role_or_profile") or "NONE",
        "Artifact digest": request_match.get("artifact_digest") or "NONE",
        "Plan binding": request_match.get("plan_binding") or "NONE",
        "Rollback boundary": request_match.get("rollback_boundary") or "NONE",
    }
    cost = request_match.get("cost_ceiling")
    expected_scalars["Cost ceiling"] = (
        f"{cost['currency']}: {cost['amount']}" if isinstance(cost, dict) else "NONE"
    )
    for field_name, expected_value in expected_scalars.items():
        if clean_cell(row[field_name]) != expected_value:
            issues.append(f"{field_name} does not match current authority")

    operations = _split_authority_values(row["Expected operations"])
    resources = _split_authority_values(row["Resources"])
    if not operations or not set(operations).issubset(set(request_match["operations"])):
        issues.append("Expected operations exceed current authority")
    if not resources or not set(resources).issubset(set(request_match["resources"])):
        issues.append("Resources exceed current authority")

    script_digest = clean_cell(row["Script SHA-256"])
    artifact_digest = clean_cell(row["Immutable artifact SHA-256"])
    digest_pattern = re.compile(r"sha256:[0-9a-f]{64}")
    bindings = [
        ("SCRIPT_SHA256", script_digest),
        ("IMMUTABLE_ARTIFACT_SHA256", artifact_digest),
    ]
    valid_bindings = [item for item in bindings if digest_pattern.fullmatch(item[1])]
    other_values = [value for _kind, value in bindings if value != "NONE"]
    if len(valid_bindings) != 1 or len(other_values) != 1:
        issues.append(
            "exactly one reviewed script or immutable artifact digest is required"
        )

    valid_until = _iso_datetime(row["Valid until"])
    authority_expiry = _iso_datetime(request_match.get("expires_at") or "")
    if (
        valid_until is None
        or authority_expiry is None
        or valid_until <= ctx.observed_at
        or valid_until > authority_expiry
    ):
        issues.append("Valid until is expired or exceeds current authority")
    evidence_destination = clean_cell(row["Evidence destination"])
    if re.fullmatch(r"EV-[0-9]{4,}", evidence_destination) is None:
        issues.append("Evidence destination must be one stable EV ID")
    if clean_cell(row["Status"]) != "CURRENT":
        issues.append("Status must be CURRENT")

    if issues:
        ctx.warning(
            "AWS_EXECUTION_CONTRACT_INVALID",
            f"{execution_id}: " + "; ".join(issues),
            VERIFY_FILE,
        )
        return None
    binding_kind, binding_digest = valid_bindings[0]
    return {
        "execution_id": execution_id,
        "content_binding": {"kind": binding_kind, "sha256": binding_digest},
        "expected_operations": operations,
        "resources": resources,
        "valid_until": clean_cell(row["Valid until"]),
        "evidence_destination": evidence_destination,
    }


def derive_request_match(ctx: Context, authority: dict[str, Any]) -> dict[str, Any]:
    raw_validity = clean_cell(str(authority.get("validity", "NONE")))
    validity = (
        raw_validity
        if raw_validity in {"CURRENT", "NONE", "STALE", "BLOCKED"}
        else "BLOCKED"
    )
    binding = authority.get("artifact_plan_binding")
    binding = binding if isinstance(binding, dict) else {}
    raw_teardown_binding = authority.get("teardown_ready_binding")
    request_match: dict[str, Any] = {
        "schema_version": 1,
        "validity": validity,
        "authority_kind": _machine_value(authority.get("kind")),
        "authorization_id": _machine_value(authority.get("authorization_id")),
        "receipt_digest": _machine_value(authority.get("receipt_digest")),
        "account": _machine_value(authority.get("account"), "ACCOUNT"),
        "region": _machine_value(authority.get("region"), "REGION"),
        "environment": _machine_value(authority.get("environment"), "ENVIRONMENT"),
        "role_or_profile": _machine_value(authority.get("role_or_profile"), "ROLE"),
        "resources": _machine_list(authority.get("resources"), "RESOURCES"),
        "operations": _machine_list(authority.get("operations"), "OPERATIONS"),
        "artifact_digest": _machine_value(binding.get("artifact"), "EXACT_DIGEST"),
        "plan_binding": _machine_value(binding.get("plan"), "STACK"),
        "cost_ceiling": _machine_cost(authority.get("cost_ceiling")),
        "rollback_boundary": _machine_value(
            authority.get("rollback_boundary"), "ROLLBACK"
        ),
        "expires_at": _machine_value(authority.get("expiration")),
        "allowed_execution_lanes": [],
        "reviewed_script": None,
        "teardown_ready_binding": None,
    }
    if request_match["authority_kind"] == "AWS_TEARDOWN" and isinstance(
        raw_teardown_binding, Mapping
    ):
        request_match["teardown_ready_binding"] = {
            "evidence_id": _machine_value(raw_teardown_binding.get("evidence_id")),
            "read_authorization": _machine_value(
                raw_teardown_binding.get("read_authorization")
            ),
            "read_role_or_profile": _machine_value(
                raw_teardown_binding.get("read_role_or_profile"), "ROLE"
            ),
            "read_receipt_digest": _machine_value(
                raw_teardown_binding.get("read_receipt_digest")
            ),
            "read_valid_until": _machine_value(
                raw_teardown_binding.get("read_valid_until")
            ),
            "read_authority_source": _machine_value(
                raw_teardown_binding.get("read_authority_source")
            ),
            "expected_manifest_or_stack": _machine_value(
                raw_teardown_binding.get("expected_manifest_or_stack")
            ),
            "resources_retained": _machine_list(
                raw_teardown_binding.get("resources_retained"), "RESOURCES"
            ),
            "shared_dependencies": _machine_list(
                raw_teardown_binding.get("shared_dependencies"), "RESOURCES"
            ),
            "cost_effect": _machine_value(raw_teardown_binding.get("cost_effect")),
            "post_teardown_verification": _machine_value(
                raw_teardown_binding.get("post_teardown_verification")
            ),
        }
    if validity != "CURRENT":
        return request_match
    request_match["allowed_execution_lanes"] = ["STRUCTURED_API"]
    reviewed_script = _reviewed_script_contract(ctx, request_match)
    if reviewed_script is not None:
        request_match["allowed_execution_lanes"].append("REVIEWED_SCRIPT")
        request_match["reviewed_script"] = reviewed_script
    return request_match


def _aws_action_transition_projection(
    request_match: Mapping[str, Any] | None,
    sequence: Mapping[str, Any],
    *,
    authority_kind: str,
    authorization_field: str,
    receipt_digest_field: str,
) -> dict[str, Any]:
    """Bind one consumed journal attempt to its exact pre-call request ceiling.

    This projection is not mutation authority. It exists only so the optional
    hook can prove that the same-session call following STARTED is identical to
    the request that was current immediately before the journal append.
    """

    empty: dict[str, Any] = {
        "schema_version": 1,
        "status": "NONE",
        "attempt_id": "NONE",
        "authority_kind": "NONE",
        "request_match_sha256": "NONE",
        "request_match": {},
    }
    if (
        clean_cell(sequence.get("status", "")) != "ACTION_TERMINAL_REQUIRED"
        or sequence.get("issues")
        or not isinstance(request_match, Mapping)
        or request_match.get("schema_version") != 1
        or request_match.get("validity") != "CURRENT"
        or request_match.get("authority_kind") != authority_kind
        or clean_cell(request_match.get("authorization_id", ""))
        != clean_cell(sequence.get(authorization_field, ""))
        or clean_cell(request_match.get("receipt_digest", ""))
        != clean_cell(sequence.get(receipt_digest_field, ""))
    ):
        return empty
    attempt_id = clean_cell(sequence.get("attempt_id", ""))
    pattern = (
        AWS_TEARDOWN_ATTEMPT_ID
        if authority_kind == "AWS_TEARDOWN"
        else AWS_DEPLOYMENT_ATTEMPT_ID
    )
    if pattern.fullmatch(attempt_id) is None:
        return empty
    normalized = dict(request_match)
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                normalized,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
    )
    return {
        **empty,
        "status": "BOUND",
        "attempt_id": attempt_id,
        "authority_kind": authority_kind,
        "request_match_sha256": digest,
        "request_match": normalized,
    }


def derive_current_prompt_aws_mode(next_prompt: str) -> str:
    """Return the maximum phase mode; authority is projected separately."""

    if next_prompt in PROMPT_DOCS_ONLY_AWS_MODES:
        return "DOCS_ONLY"
    if next_prompt in PROMPT_READ_ONLY_AWS_MODES:
        return "READ_ONLY"
    if next_prompt in PROMPT_MUTATION_AWS_MODES:
        return "MUTATION"
    return "NONE"


def derive_aws_mode_boundary(
    lane: str | None,
    envelope: Mapping[str, str],
    next_prompt: str,
    external_authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Separate planned ceilings, prompt capability, and current authority."""

    project_lane = lane if lane in AWS_LANES else "NONE"
    proposed_gate_b = clean_cell(envelope.get("AWS boundary", "NONE")).upper()
    gate_b_maximum = proposed_gate_b if proposed_gate_b in AWS_BOUNDARIES else "NONE"
    local_task_modes = ["NONE"] if gate_b_maximum == "NONE" else ["NONE", "DOCS_ONLY"]
    current_prompt_mode = derive_current_prompt_aws_mode(next_prompt)
    external_kind = clean_cell(external_authority.get("kind", "NONE")) or "NONE"
    external_validity = clean_cell(external_authority.get("validity", "NONE")) or "NONE"
    read_authorized = (
        current_prompt_mode == "READ_ONLY"
        and external_kind == "AWS_READ_ONLY"
        and external_validity == "CURRENT"
    )
    mutation_authorized = (
        current_prompt_mode == "MUTATION"
        and external_kind in {"AWS_DEPLOYMENT", "AWS_TEARDOWN"}
        and external_validity == "CURRENT"
    )
    return {
        "project_lane": project_lane,
        "local_task_modes": local_task_modes,
        "current_prompt_mode": current_prompt_mode,
        "gate_b_maximum": gate_b_maximum,
        "external_authority_kind": external_kind,
        "external_authority_validity": external_validity,
        "account_access_authorized": read_authorized or mutation_authorized,
        "mutation_authorized": mutation_authorized,
    }
