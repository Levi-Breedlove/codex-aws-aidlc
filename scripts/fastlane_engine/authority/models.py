"""Pure helpers for exact owner and external authority intersections.

Canonical inputs are normalized receipt, envelope, cost, and time values. Returns
parsed values and boolean intersections. Side effects are prohibited; these helpers
never read files, execute external actions, or broaden authority.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from ..core.contracts import split_table_row
from ..core.ids import clean_cell, explicit_value, iso_datetime

try:
    from fastlane_contracts import without_fenced_code
except ModuleNotFoundError:
    from scripts.fastlane_contracts import without_fenced_code


AWS_READ_PREFLIGHT_RECEIPT_FIELDS = (
    "Read authorization",
    "Construction authorization",
    "Profile or role",
    "Account",
    "Region",
    "Environment",
    "Stack, application, and resources",
    "Allowed read-only operations",
    "Artifact digest",
    "Prohibited operations",
    "Valid until",
    "Approver",
)
AWS_DEPLOYMENT_RECEIPT_FIELDS = (
    "AWS authorization",
    "Construction authorization",
    "Profile or role",
    "Account",
    "Region",
    "Environment",
    "Artifact digest",
    "IaC plan/change-set binding",
    "Stack, application, and resources",
    "Allowed operations",
    "Cost ceiling",
    "Rollback boundary",
    "Valid until",
    "Approver",
)
AWS_TEARDOWN_RECEIPT_FIELDS = (
    "Teardown authorization",
    "Construction authorization",
    "Profile or role",
    "Account",
    "Region",
    "Environment",
    "Stack, application, and resources to remove",
    "Resources and data to retain",
    "Allowed deletion operations",
    "Shared dependencies",
    "Cost effect",
    "Post-teardown verification",
    "Valid until",
    "Approver",
)
AWS_PLAN_BINDING = re.compile(
    r"TYPE: (?P<type>CLOUDFORMATION_CHANGE_SET|TERRAFORM_PLAN|CONTAINER_IMAGE|OTHER); "
    r"IDENTIFIER: (?P<identifier>[^;\r\n]+); DIGEST: (?P<digest>sha256:[0-9a-f]{64})"
)
AWS_READ_ONLY_OPERATION = re.compile(
    r"(?i)^(?:[a-z0-9-]+[.:])?(?:BatchGet|Check|Describe|Detect|Estimate|Get|"
    r"Head|List|Lookup|Preview|Search|Simulate|Validate)[A-Za-z0-9]*$"
)
AWS_READ_AUTHORIZATION_ID = re.compile(r"AWS-READ-AUTH-\d{4,}")
AWS_PREFLIGHT_ID = re.compile(r"AWS-PREFLIGHT-\d{4,}")
AWS_DEPLOYMENT_ATTEMPT_ID = re.compile(r"AWS-DEPLOY-\d{4,}")
AWS_TEARDOWN_ATTEMPT_ID = re.compile(r"AWS-TEARDOWN-\d{4,}")
AWS_COST_CEILING = re.compile(
    r"(?P<currency>[A-Z]{3}): (?P<amount>[1-9]\d*(?:\.\d{1,2})?)"
)
NON_HUMAN_APPROVER = re.compile(
    r"(?:^|[^a-z0-9])(?:ai|agent|assistant|automated|automation|bot|chatbot|"
    r"chatgpt|codex|gpt(?:-[0-9]+(?:\.[0-9]+)?)?|lambda|llm|model|openai|robot|"
    r"service|system|workflow|aws[ _-]*(?:core|lambda)|pending|placeholder|"
    r"not[ _-]*started)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GateBAuthorityBounds:
    """Normalized Gate B facts that Authority may intersect but never expand."""

    valid: bool = False
    boundary: str = "NONE"
    account: str | None = None
    region: str | None = None
    environment: str | None = None
    role_or_profile: str | None = None
    resources: tuple[str, ...] = ()
    operations: tuple[str, ...] = ()
    active_artifact: str = "NONE"
    artifact_authorized: bool = False
    cost_posture: str = ""
    owner_cost_cap: tuple[str, Decimal] | None = None
    aws_cost_ceiling: tuple[str, Decimal] | None = None
    aws_cost_ceiling_raw: str = "NONE"
    rollback_boundary: str | None = None
    authorization_expires_at: datetime | None = None
    aws_authorization_expires_at: datetime | None = None
    stack_or_application: str = "NONE"


@dataclass(frozen=True)
class AuthorityEvaluationInput:
    """One immutable observation basis for an Authority evaluation."""

    has_errors: bool
    observed_at: datetime
    verify_text: str


@dataclass(frozen=True)
class ConstructionWriteInput:
    """Already-normalized repository and active-task write facts."""

    has_errors: bool
    approved_write_roots: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    protected_paths: tuple[str, ...] = ()
    active_task: str | None = None
    active_task_write_set: tuple[str, ...] = ()


@dataclass(frozen=True)
class LifecycleIntentWriteInput:
    """Normalized lifecycle facts used only for a local owner-intent update."""

    has_errors: bool
    tasks_terminal: bool
    release_decision: str
    deployment_status: str
    deployment_boundary_settled: bool
    teardown_status: str
    teardown_has_issues: bool
    external_authority_current: bool
    intent_value: str = "NONE"


@dataclass(frozen=True)
class PendingGateReceiptInput:
    """Normalized current owner-gate facts used to construct one exact receipt."""

    gate: str
    lifecycle_state: str
    next_prompt: str
    owner_action_kind: str
    requirements_revision: str
    cost_posture: str = ""
    accepted_assumptions: tuple[str, ...] = ()
    design_revision: str = ""
    construction_authorization: str = ""
    construction_envelope_sha256: str = ""


@dataclass(frozen=True)
class AwsAuthorityPolicy:
    """Immutable authority callbacks and normalized Gate B bounds for AWS state."""

    bounds: GateBAuthorityBounds | None
    split_authority_values: Callable[[str], list[str]]
    action_authorization_rows: Callable[[str], dict[str, dict[str, str]]]
    exact_receipt_fields: Callable[..., dict[str, str] | None]
    envelope_scalar: Callable[..., str | None]
    envelope_values: Callable[..., list[str]]
    receipt_identity_matches_gate_b: Callable[..., bool]
    receipt_scope_within_gate_b: Callable[..., bool]
    receipt_artifact_matches_gate_b: Callable[..., bool]
    gate_b_rollback_value: Callable[..., str | None]
    deployment_reconciliation_read_authority: Callable[..., dict[str, Any] | None]
    teardown_reconciliation_read_authority: Callable[..., dict[str, Any] | None]
    parse_verification_matrix: Callable[[str], list[dict[str, str]]]
    explicit_human_approver: Callable[[str], bool]
    marked_receipt: Callable[[str, str], str]
    parse_aws_environment: Callable[[str], tuple[str, str]]


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


def _authorization_expiry_ceiling(
    value: str, *, observed_at: datetime, allow_expired: bool
) -> datetime:
    """Parse one canonical Gate B expiry against the bounded Engine clock."""

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
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("Observed time must include a timezone")
    if not allow_expired and expires_at <= observed_at:
        raise ValueError("Construction authorization is expired")
    return expires_at


def _parse_cost_ceiling(value: str) -> tuple[str, Decimal] | None:
    """Return one canonical finite AWS cost ceiling or None."""

    match = AWS_COST_CEILING.fullmatch(clean_cell(value))
    if match is None:
        return None
    try:
        amount = Decimal(match.group("amount"))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return match.group("currency"), amount


def _cost_at_most(candidate: tuple[str, Decimal], ceiling: tuple[str, Decimal]) -> bool:
    return candidate[0] == ceiling[0] and candidate[1] <= ceiling[1]


def _read_bound_honors_cost_posture(
    bound: str,
    bounds: GateBAuthorityBounds,
    *,
    require_gate_ceiling: bool = True,
) -> bool:
    """Bind read-only billing exposure to Gate A and any Gate B ceiling."""

    cleaned_bound = clean_cell(bound)
    if cleaned_bound == clean_cell(bounds.cost_posture):
        candidate = bounds.owner_cost_cap
    else:
        candidate = _parse_cost_ceiling(cleaned_bound)
        if candidate is None:
            return False
        if bounds.owner_cost_cap is not None and not _cost_at_most(
            candidate, bounds.owner_cost_cap
        ):
            return False
    if clean_cell(bounds.aws_cost_ceiling_raw).startswith("NOT_APPLICABLE"):
        return True
    if not require_gate_ceiling:
        return True
    return (
        candidate is not None
        and bounds.aws_cost_ceiling is not None
        and _cost_at_most(candidate, bounds.aws_cost_ceiling)
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
    fields: Mapping[str, str], bounds: GateBAuthorityBounds
) -> bool:
    expected = {
        "Profile or role": bounds.role_or_profile,
        "Account": bounds.account,
        "Region": bounds.region,
        "Environment": bounds.environment,
    }
    return all(
        expected_value is not None and fields.get(field) == expected_value
        for field, expected_value in expected.items()
    )


def _receipt_scope_within_gate_b(
    resources: list[str],
    operations: list[str],
    bounds: GateBAuthorityBounds,
) -> bool:
    allowed_resources = set(bounds.resources)
    allowed_operations = set(bounds.operations)
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
    bounds: GateBAuthorityBounds,
) -> bool:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", artifact) is None:
        return False
    return bool(
        bounds.artifact_authorized and artifact == clean_cell(bounds.active_artifact)
    )


def _receipt_validity_within_gate_b(
    valid_until: str,
    result: str,
    bounds: GateBAuthorityBounds,
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
    ceilings = [bounds.authorization_expires_at]
    if bounds.aws_authorization_expires_at is not None:
        ceilings.append(bounds.aws_authorization_expires_at)
    if any(item is None for item in ceilings):
        return None
    if current == "ONE_OPERATION":
        return current
    expires = _iso_datetime(current)
    if expires is None:
        return None
    return (
        current if all(expires <= ceiling for ceiling in ceilings if ceiling) else None
    )


def _gate_b_rollback_value(bounds: GateBAuthorityBounds) -> str | None:
    return bounds.rollback_boundary


def _mutation_cost_within_gate_b(
    value: str,
    bounds: GateBAuthorityBounds,
) -> bool:
    candidate = _parse_cost_ceiling(value)
    return (
        candidate is not None
        and bounds.aws_cost_ceiling is not None
        and _cost_at_most(candidate, bounds.aws_cost_ceiling)
        and (
            bounds.owner_cost_cap is None
            or _cost_at_most(candidate, bounds.owner_cost_cap)
        )
    )


def explicit_human_approver(value: str) -> bool:
    """Require an explicit owner identity that is not an agent or automation."""

    cleaned = clean_cell(value)
    return explicit_value(cleaned) and NON_HUMAN_APPROVER.search(cleaned) is None


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
