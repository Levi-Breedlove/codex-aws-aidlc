"""Pure helpers for exact owner and external authority intersections.

Canonical inputs are normalized receipt, envelope, cost, and time values. Returns
parsed values and boolean intersections. Side effects are prohibited; these helpers
never read files, execute external actions, or broaden authority.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Mapping

from ..core.contracts import split_table_row
from ..core.ids import clean_cell, explicit_value, iso_datetime, unresolved
from ..design import (
    AWS_DERIVED_ARTIFACT,
    AWS_EXACT_ARTIFACT,
    parse_aws_environment,
    validate_aws_artifact,
)
from ..project_inspection import (
    AWS_COST_CEILING,
    parse_cost_posture,
    parse_future_expiry,
    parse_positive_cost,
    validate_aws_cost_ceiling,
)

try:
    from fastlane_contracts import without_fenced_code
except ModuleNotFoundError:
    from scripts.fastlane_contracts import without_fenced_code


def _split_authority_values(value: str) -> list[str]:
    """Return conservative exact values from a comma- or semicolon-list."""

    cleaned = clean_cell(value)
    if not explicit_value(cleaned, allow_none=False):
        return []
    return [item.strip() for item in re.split(r"[,;]", cleaned) if item.strip()]


def _action_authorization_rows(text: str) -> dict[str, dict[str, str]]:
    heading = "## Action authorization provenance"
    structural = without_fenced_code(text)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*$", structural, re.MULTILINE)
    )
    if len(matches) != 1:
        return {}
    original_lines = text[matches[0].end() :].splitlines()
    structural_lines = structural[matches[0].end() :].splitlines()
    start = next(
        (
            index
            for index, line in enumerate(structural_lines)
            if line.strip().startswith("|")
        ),
        None,
    )
    if start is None:
        return {}
    table: list[str] = []
    for original, visible in zip(original_lines[start:], structural_lines[start:]):
        if not visible.strip().startswith("|"):
            break
        table.append(original)
    if len(table) < 4:
        return {}
    headers = [clean_cell(cell) for cell in split_table_row(table[0])]
    result: dict[str, dict[str, str]] = {}
    for line in table[2:]:
        cells = [clean_cell(cell) for cell in split_table_row(line)]
        if len(cells) != len(headers):
            continue
        row = dict(zip(headers, cells))
        action = row.get("Action", "")
        if action in {"Read-only preflight", "Deployment", "Teardown"}:
            if action in result:
                # Conflicting or repeated provenance is never first-row-wins.
                return {}
            result[action] = row
    return result


def _receipt_fields(receipt: str, expected_title: str) -> dict[str, str] | None:
    lines = receipt.splitlines()
    if not lines or lines[0].strip() != expected_title:
        return None
    result: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            return None
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in result or not explicit_value(value, allow_none=True):
            return None
        result[key] = value
    return result


def _authorization_valid_until(
    value: str,
    result: str,
    *,
    observed_at: datetime,
    allow_expired: bool = False,
) -> str | None:
    cleaned = clean_cell(value)
    normalized = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        expires = datetime.fromisoformat(normalized)
    except ValueError:
        if cleaned == "ONE_OPERATION" and result in {"AUTHORIZED", "RUNNING", "READY"}:
            return cleaned
        return cleaned if explicit_value(cleaned) and result == "NOT_STARTED" else None
    if expires.tzinfo is None or expires.utcoffset() is None:
        return None
    return cleaned if allow_expired or expires > observed_at else None


def _parse_cost_ceiling(value: str) -> tuple[str, Decimal] | None:
    """Return one canonical finite AWS cost ceiling or None."""

    try:
        return parse_positive_cost(value, AWS_COST_CEILING, "AWS cost ceiling")
    except ValueError:
        return None


def _cost_at_most(candidate: tuple[str, Decimal], ceiling: tuple[str, Decimal]) -> bool:
    return candidate[0] == ceiling[0] and candidate[1] <= ceiling[1]


def _read_bound_honors_cost_posture(
    bound: str,
    cost_posture: str,
    gate_b_cost_ceiling: str,
) -> bool:
    """Bind read-only billing exposure to Gate A and any Gate B ceiling."""

    cleaned_bound = clean_cell(bound)
    approved_posture = clean_cell(cost_posture)
    try:
        owner_cap = parse_cost_posture(approved_posture)
    except ValueError:
        return False
    if cleaned_bound == approved_posture:
        candidate = owner_cap
    else:
        try:
            validate_aws_cost_ceiling(cleaned_bound, approved_posture)
        except ValueError:
            return False
        candidate = _parse_cost_ceiling(cleaned_bound)
    gate_value = clean_cell(gate_b_cost_ceiling)
    if gate_value.startswith("NOT_APPLICABLE"):
        return True
    gate_cap = _parse_cost_ceiling(gate_value)
    return (
        candidate is not None
        and gate_cap is not None
        and _cost_at_most(candidate, gate_cap)
    )


def _envelope_scalar(envelope: Mapping[str, str], field: str, label: str) -> str | None:
    value = clean_cell(envelope.get(field, ""))
    prefix = label + ":"
    if not value.startswith(prefix):
        return None
    candidate = clean_cell(value[len(prefix) :])
    return candidate if explicit_value(candidate, allow_none=False) else None


def _envelope_values(envelope: Mapping[str, str], field: str, label: str) -> list[str]:
    value = clean_cell(envelope.get(field, ""))
    prefix = label + ":"
    if not value.startswith(prefix):
        return []
    return _split_authority_values(value[len(prefix) :])


def _receipt_identity_matches_gate_b(
    fields: Mapping[str, str], envelope: Mapping[str, str]
) -> bool:
    try:
        environment, _environment_class = parse_aws_environment(
            envelope.get("AWS environment", "")
        )
    except ValueError:
        return False
    expected = {
        "Profile or role": _envelope_scalar(envelope, "AWS role or profile", "ROLE"),
        "Account": _envelope_scalar(envelope, "AWS account", "ACCOUNT"),
        "Region": _envelope_scalar(envelope, "AWS Region", "REGION"),
        "Environment": environment,
    }
    return all(
        expected_value is not None and fields.get(field) == expected_value
        for field, expected_value in expected.items()
    )


def _receipt_scope_within_gate_b(
    resources: list[str],
    operations: list[str],
    envelope: Mapping[str, str],
) -> bool:
    allowed_resources = set(
        _envelope_values(envelope, "AWS resource allowlist", "RESOURCES")
    )
    allowed_operations = set(
        _envelope_values(envelope, "AWS allowed operations", "OPERATIONS")
    )
    unsafe = any("*" in item for item in resources + operations)
    return bool(
        resources
        and operations
        and not unsafe
        and len(resources) == len(set(resources))
        and len(operations) == len(set(operations))
        and set(resources).issubset(allowed_resources)
        and set(operations).issubset(allowed_operations)
    )


def _receipt_artifact_matches_gate_b(
    artifact: str,
    envelope: Mapping[str, str],
    active_artifact: str,
) -> bool:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", artifact) is None:
        return False
    if artifact != clean_cell(active_artifact):
        return False
    approved = clean_cell(envelope.get("AWS artifact authorization and provenance", ""))
    if approved.startswith("NOT_APPLICABLE"):
        return envelope.get("AWS boundary") == "READ_ONLY"
    if AWS_EXACT_ARTIFACT.fullmatch(approved) is not None:
        return artifact == approved.removeprefix("EXACT_DIGEST: ")
    try:
        validate_aws_artifact(
            approved, clean_cell(envelope.get("Authorized baseline commit", ""))
        )
    except ValueError:
        return False
    return AWS_DERIVED_ARTIFACT.fullmatch(approved) is not None


def _authorization_expiry_ceiling(
    value: str, *, observed_at: datetime, allow_expired: bool
) -> datetime:
    if not allow_expired:
        return parse_future_expiry(value, observed_at=observed_at)
    cleaned = clean_cell(value)
    match = re.fullmatch(
        r"Expires at (?P<timestamp>[^\s;]+); earlier completion: (?P<condition>[^\r\n]+)",
        cleaned,
    )
    if match is None or not explicit_value(match.group("condition"), allow_none=False):
        raise ValueError("Authorization expiry is not canonical")
    expires_at = _iso_datetime(match.group("timestamp"))
    if expires_at is None:
        raise ValueError("Authorization expiry timestamp is not ISO 8601 with timezone")
    return expires_at


def _receipt_validity_within_gate_b(
    valid_until: str,
    result: str,
    envelope: Mapping[str, str],
    *,
    observed_at: datetime,
    allow_expired: bool = False,
) -> str | None:
    current = _authorization_valid_until(
        valid_until,
        result,
        observed_at=observed_at,
        allow_expired=allow_expired,
    )
    if current is None:
        return None
    try:
        ceilings = [
            _authorization_expiry_ceiling(
                envelope.get("Authorization expiry or completion condition", ""),
                observed_at=observed_at,
                allow_expired=allow_expired,
            )
        ]
    except ValueError:
        return None
    aws_validity = clean_cell(envelope.get("AWS authorization validity", ""))
    if not aws_validity.startswith("NOT_APPLICABLE"):
        try:
            ceilings.append(
                _authorization_expiry_ceiling(
                    aws_validity,
                    observed_at=observed_at,
                    allow_expired=allow_expired,
                )
            )
        except ValueError:
            return None
    if current == "ONE_OPERATION":
        return current
    expires = _iso_datetime(current)
    if expires is None:
        return None
    return current if all(expires <= ceiling for ceiling in ceilings) else None


def _gate_b_rollback_value(envelope: Mapping[str, str]) -> str | None:
    value = clean_cell(envelope.get("AWS rollback boundary", ""))
    prefix = "ROLLBACK:"
    if not value.startswith(prefix):
        return None
    candidate = clean_cell(value[len(prefix) :])
    if unresolved(candidate) or not candidate:
        return None
    return candidate


def _mutation_cost_within_gate_b(
    value: str,
    envelope: Mapping[str, str],
    cost_posture: str,
) -> bool:
    try:
        validate_aws_cost_ceiling(value, cost_posture)
    except ValueError:
        return False
    candidate = _parse_cost_ceiling(value)
    gate_cap = _parse_cost_ceiling(envelope.get("AWS cost ceiling", ""))
    return (
        candidate is not None
        and gate_cap is not None
        and _cost_at_most(candidate, gate_cap)
    )


def _exact_receipt_fields(
    receipt: str,
    expected_title: str,
    expected_fields: tuple[str, ...],
    *,
    allow_none_fields: frozenset[str] = frozenset(),
) -> dict[str, str] | None:
    lines = receipt.splitlines()
    if len(lines) != len(expected_fields) + 1 or lines[0].strip() != expected_title:
        return None
    result: dict[str, str] = {}
    for line, expected in zip(lines[1:], expected_fields):
        if ":" not in line:
            return None
        key, value = line.split(":", 1)
        if key.strip() != expected:
            return None
        value = value.strip()
        if not explicit_value(value, allow_none=expected in allow_none_fields):
            return None
        result[expected] = value
    return result


def _iso_datetime(value: str) -> datetime | None:
    """COMPATIBILITY: retain the former façade name for authority callers."""

    return iso_datetime(value)
