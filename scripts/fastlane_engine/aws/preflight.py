"""Pure read-only AWS preflight state derivation.

Canonical input is already-observed VERIFY Markdown plus an explicit current
read-authority projection. The result records evidence maturity only and grants
no account access or mutation authority. This module performs no I/O.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..core.ids import canonical_id_list, clean_cell, iso_datetime
from .evidence import parse_read_preflight_evidence
from .models import AWS_PREFLIGHT_ID, AwsAuthorityPolicy


def derive_read_preflight_state(
    verify_text: str,
    authority: Mapping[str, Any] | None,
    *,
    policy: AwsAuthorityPolicy,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    artifact_binding: str,
) -> dict[str, Any]:
    """SAFETY: keep observed account evidence separate from AWS guidance."""

    base: dict[str, Any] = {
        "status": "NOT_STARTED",
        "preflight_id": "NONE",
        "read_authorization": (
            authority.get("authorization_id", "NONE") if authority else "NONE"
        ),
        "account": authority.get("account", "NONE") if authority else "NONE",
        "region": authority.get("region", "NONE") if authority else "NONE",
        "environment": (authority.get("environment", "NONE") if authority else "NONE"),
        "account_access": "NOT_OBSERVED",
        "evidence_ids": [],
        "issues": [],
    }
    if authority is None or authority.get("validity") != "CURRENT":
        return base
    try:
        rows = parse_read_preflight_evidence(verify_text)
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    concrete = [
        row
        for row in rows
        if AWS_PREFLIGHT_ID.fullmatch(clean_cell(row.get("Preflight ID", "")))
    ]
    identifiers = [clean_cell(row["Preflight ID"]) for row in concrete]
    if len(identifiers) != len(set(identifiers)):
        return {
            **base,
            "status": "BLOCKED",
            "issues": ["Read-only preflight evidence contains duplicate Preflight IDs"],
        }
    candidates = [
        row
        for row in concrete
        if clean_cell(row.get("Read authorization", ""))
        == authority.get("authorization_id")
    ]
    if not candidates:
        return {**base, "status": "RUNNING"}
    if len(candidates) != 1:
        return {
            **base,
            "status": "BLOCKED",
            "issues": [
                "Expected exactly one preflight row for the current read authorization"
            ],
        }
    row = candidates[0]
    preflight_id = clean_cell(row["Preflight ID"])
    result = clean_cell(row.get("Result", ""))
    expected_basis = (
        f"{requirements_revision} / {design_revision} / {construction_authorization}"
    )
    expected_scalars = {
        "REQ / DES / AUTH": expected_basis,
        "Artifact digest": artifact_binding,
        "Role or profile": authority.get("role_or_profile"),
        "Account": authority.get("account"),
        "Region": authority.get("region"),
        "Environment": authority.get("environment"),
    }
    issues = [
        f"{field_name} does not match current read scope"
        for field_name, expected in expected_scalars.items()
        if clean_cell(row.get(field_name, "")) != expected
    ]
    authority_binding = authority.get("artifact_plan_binding")
    authorized_artifact = (
        authority_binding.get("artifact")
        if isinstance(authority_binding, Mapping)
        else None
    )
    if authorized_artifact != artifact_binding:
        issues.append(
            "Read receipt artifact binding does not match the current artifact"
        )
    resources = policy.split_authority_values(row.get("Resources", ""))
    operations = policy.split_authority_values(row.get("Operations observed", ""))
    if len(operations) != len(set(operations)):
        issues.append("Operations observed must not contain duplicates")
    if resources != list(authority.get("resources", [])):
        issues.append("Resources do not exactly match current read scope")
    if not operations or not set(operations).issubset(
        set(authority.get("operations", []))
    ):
        issues.append("Operations observed are empty or exceed current read scope")
    try:
        evidence_ids = canonical_id_list(
            row.get("AWS evidence IDs", ""),
            re.compile(r"EV-\d{4,}"),
            "AWS evidence IDs",
        )
    except ValueError as exc:
        evidence_ids = []
        issues.append(str(exc))
    if clean_cell(row.get("Account access", "")) != "READ_ONLY_OBSERVED":
        issues.append("Account access must be READ_ONLY_OBSERVED")
    for label in ("Caller identity evidence", "Boundary and drift evidence"):
        value = clean_cell(row.get(label, ""))
        if re.fullmatch(r"EV-\d{4,}", value) is None:
            issues.append(f"{label} must reference one EV ID")
        elif value not in evidence_ids:
            issues.append(f"{label} must be included in AWS evidence IDs")
    started = iso_datetime(row.get("Started at", ""))
    completed = iso_datetime(row.get("Completed at", ""))
    if started is None:
        issues.append("Started at must be ISO 8601 with timezone")
    if result == "READY":
        if completed is None or (started is not None and completed < started):
            issues.append("Completed at must be current and not precede Started at")
        if clean_cell(row.get("Identity and boundary match", "")) not in {
            "PASS",
            "VERIFIED",
        }:
            issues.append("Identity and boundary match must be PASS or VERIFIED")
    if issues:
        return {
            **base,
            "status": "STALE" if result in {"READY", "RUNNING"} else "BLOCKED",
            "preflight_id": preflight_id,
            "evidence_ids": evidence_ids,
            "issues": issues,
            "account_access": "NOT_VERIFIED",
        }
    if result not in {"RUNNING", "READY", "BLOCKED", "STALE"}:
        return {
            **base,
            "status": "BLOCKED",
            "preflight_id": preflight_id,
            "issues": ["Preflight Result is not canonical"],
            "account_access": "NOT_VERIFIED",
        }
    return {
        **base,
        "status": result,
        "preflight_id": preflight_id,
        "evidence_ids": evidence_ids,
        "account_access": "READ_ONLY_OBSERVED",
    }


__all__ = ("derive_read_preflight_state",)
