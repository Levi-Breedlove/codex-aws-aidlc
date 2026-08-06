"""Adaptive coverage and change-impact evaluation for Fastlane Define.

Canonical inputs are current PRD text and caller-supplied project selections.
Returned contracts and issue strings are deterministic and compatible with the
characterized Engine behavior. This pure module performs no I/O, routing,
mutation, approval, or authorization.
"""

from __future__ import annotations

import hashlib
import re

from ..core.contracts import contract_table_after_heading
from ..core.ids import STABLE_CONTRACT_ID, canonical_id_list, clean_cell
from ..core.ids import explicit_value, unresolved
from .models import (
    ChangeImpactContract,
    ChangeImpactRow,
    CoverageContract,
    CoverageOmission,
)
from .requirements import authoritative_requirement_ids


PROJECT_MODES = {"greenfield", "brownfield"}
DELIVERY_PROFILES = {"quick-mvp", "standard", "high-risk"}
WORK_KINDS = {
    "NEW_BUILD",
    "FEATURE",
    "BUGFIX",
    "REFACTOR",
    "MIGRATION",
    "INFRASTRUCTURE",
    "SECURITY_FIX",
}
ARCHITECTURE_DISPOSITIONS = {"SELECT", "AMEND", "PRESERVE"}
COVERAGE_DOMAINS = (
    "REQUIREMENTS",
    "ARCHITECTURE_COMPARISON",
    "AWS_EVIDENCE",
    "DATA",
    "SECURITY_PRIVACY",
    "RELIABILITY_RECOVERY",
    "COST",
    "HARNESS",
    "TASKS",
    "OPERATIONS",
)
ALWAYS_REQUIRED_COVERAGE = {
    "REQUIREMENTS",
    "SECURITY_PRIVACY",
    "COST",
    "HARNESS",
    "TASKS",
    "OPERATIONS",
}
COVERAGE_PLAN_HEADING = "### Adaptive coverage plan"
COVERAGE_PLAN_HEADERS = (
    "Work kind",
    "Delivery profile",
    "Architecture disposition",
    "Required sections",
    "Omitted sections and reasons",
    "Basis IDs",
)
CHANGE_IMPACT_HEADING = "### Change impact record"
CHANGE_IMPACT_HEADERS = (
    "Change ID",
    "Changed basis IDs",
    "Affected IDs",
    "Preserved IDs",
    "Required revalidation",
)
CHANGE_ID = re.compile(r"CHANGE-\d{4,}")
DESIGN_CONTROLLED_ID = re.compile(r"^(?:DRV|CAND|ARCH|TECH|HARNESS|AWS-EV)-")


def _none_with_reason(value: str) -> bool:
    cleaned = clean_cell(value)
    return bool(re.fullmatch(r"NONE\s+(?:-|—)\s+\S.*", cleaned)) and not unresolved(
        cleaned
    )


def _coverage_domain_list(value: str, field_name: str) -> list[str]:
    cleaned = clean_cell(value)
    if unresolved(cleaned):
        raise ValueError(f"{field_name} is unresolved")
    values = [item.strip() for item in cleaned.split(",")]
    if not values or any(item not in COVERAGE_DOMAINS for item in values):
        raise ValueError(
            f"{field_name} must use comma-separated canonical coverage domains"
        )
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} contains duplicate domains")
    if cleaned != ", ".join(values):
        raise ValueError(f"{field_name} must use comma-space-separated domains")
    return values


def _coverage_omissions(value: str) -> list[CoverageOmission]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return []
    if unresolved(cleaned):
        raise ValueError("Omitted sections and reasons is unresolved")
    omissions: list[CoverageOmission] = []
    seen: set[str] = set()
    for item in cleaned.split("; "):
        section, separator, reason = item.partition(": ")
        if not separator or section not in COVERAGE_DOMAINS:
            raise ValueError(
                "Omissions must use SECTION: concrete reason entries separated by semicolon-space"
            )
        if section in seen:
            raise ValueError(f"Omitted section {section} is duplicated")
        if not explicit_value(reason, allow_none=False):
            raise ValueError(f"Omitted section {section} requires a concrete reason")
        seen.add(section)
        omissions.append(CoverageOmission(section, reason))
    return omissions


def _selection_issues(
    work_kind: str,
    profile: str,
    disposition: str,
    delivery_profile: str | None,
    owner_work_context: str | None,
) -> list[str]:
    issues: list[str] = []
    if work_kind not in WORK_KINDS:
        issues.append(f"Adaptive coverage has invalid work kind {work_kind!r}")
    if owner_work_context == "NEW_APPLICATION" and work_kind != "NEW_BUILD":
        issues.append("NEW_APPLICATION owner work context requires work kind NEW_BUILD")
    if profile not in DELIVERY_PROFILES:
        issues.append(f"Adaptive coverage has invalid delivery profile {profile!r}")
    elif profile != delivery_profile:
        issues.append("Adaptive coverage delivery profile must match Document status")
    if disposition not in ARCHITECTURE_DISPOSITIONS:
        issues.append(
            f"Adaptive coverage has invalid architecture disposition {disposition!r}"
        )
    if work_kind == "NEW_BUILD" and disposition != "SELECT":
        issues.append("NEW_BUILD requires architecture disposition SELECT")
    return issues


def _partition_issues(
    required_sections: list[str], omissions: list[CoverageOmission]
) -> list[str]:
    issues: list[str] = []
    for omission in omissions:
        if (
            STABLE_CONTRACT_ID.search(omission.reason) is None
            and "REPOSITORY_BASELINE" not in omission.reason
        ):
            issues.append(
                f"Omitted section {omission.section} requires a requirement ID or REPOSITORY_BASELINE basis"
            )
    omitted_sections = {item.section for item in omissions}
    if set(required_sections) & omitted_sections:
        issues.append("Coverage domains cannot be both required and omitted")
    if set(required_sections) | omitted_sections != set(COVERAGE_DOMAINS):
        issues.append(
            "Required and omitted coverage domains must partition every canonical domain"
        )
    return issues


def _minimum_coverage_issues(
    text: str,
    required_sections: list[str],
    disposition: str,
    effective_risk: str | None,
    aws_lane: str | None,
) -> list[str]:
    minimum = set(ALWAYS_REQUIRED_COVERAGE)
    if disposition in {"SELECT", "AMEND"}:
        minimum.update({"ARCHITECTURE_COMPARISON", "AWS_EVIDENCE"})
    if effective_risk in {"high", "critical"}:
        minimum.update(COVERAGE_DOMAINS)
    if aws_lane in {"read-only", "fast-dev", "explicit-gate"}:
        minimum.add("AWS_EVIDENCE")
    missing_minimum = sorted(minimum - set(required_sections))
    requirement_ids = authoritative_requirement_ids(text)
    if any(identifier.startswith("DATA-") for identifier in requirement_ids):
        minimum.add("DATA")
    if any(identifier.startswith("REL-") for identifier in requirement_ids):
        minimum.add("RELIABILITY_RECOVERY")
    if not missing_minimum:
        return []
    return ["Adaptive coverage omits mandatory domains: " + ", ".join(missing_minimum)]


def derive_coverage_contract(
    text: str,
    requirements_revision: str | None,
    delivery_profile: str | None,
    effective_risk: str | None,
    aws_lane: str | None,
    *,
    required: bool,
    grandfather_current_gate_a: bool,
    owner_work_context: str | None = None,
) -> tuple[CoverageContract, list[str]]:
    """SAFETY: Derive one ordered adaptive-coverage contract without I/O.

    Selection, partition, minimum coverage, and basis diagnostics intentionally
    remain sequenced because their public order is compatibility-sensitive.
    """

    issues: list[str] = []
    try:
        table = contract_table_after_heading(
            text, COVERAGE_PLAN_HEADING, COVERAGE_PLAN_HEADERS
        )
    except ValueError as exc:
        table = None
        issues.append(f"{COVERAGE_PLAN_HEADING}: {exc}")
    if table is None:
        if grandfather_current_gate_a and not issues:
            return CoverageContract(
                status="READY",
                required_sections=COVERAGE_DOMAINS,
                compatibility_full_coverage=True,
            ), []
        if required and not issues:
            issues.append(f"Missing {COVERAGE_PLAN_HEADING}")
        return CoverageContract(
            status="BLOCKED" if required else "UNINITIALIZED"
        ), issues
    if len(table.rows) != 1:
        issues.append("Adaptive coverage plan must contain exactly one row")
        return CoverageContract(
            status="BLOCKED", canonical_bytes=table.canonical_bytes
        ), issues

    row = table.rows[0]
    if not required and any(unresolved(cell) for cell in row):
        return CoverageContract(
            status="UNINITIALIZED", canonical_bytes=table.canonical_bytes
        ), []
    work_kind, profile, disposition, required_value, omitted_value, basis_value = row
    issues.extend(
        _selection_issues(
            work_kind,
            profile,
            disposition,
            delivery_profile,
            owner_work_context,
        )
    )
    required_sections: list[str] = []
    omissions: list[CoverageOmission] = []
    try:
        required_sections = _coverage_domain_list(required_value, "Required sections")
    except ValueError as exc:
        issues.append(str(exc))
    try:
        omissions = _coverage_omissions(omitted_value)
    except ValueError as exc:
        issues.append(str(exc))
    issues.extend(_partition_issues(required_sections, omissions))
    issues.extend(
        _minimum_coverage_issues(
            text, required_sections, disposition, effective_risk, aws_lane
        )
    )

    basis_ids: list[str] = []
    try:
        basis_ids = canonical_id_list(
            basis_value, STABLE_CONTRACT_ID, "Adaptive coverage Basis IDs"
        )
        expected = [
            identifier
            for identifier in [
                requirements_revision,
                *sorted(authoritative_requirement_ids(text)),
            ]
            if identifier
        ]
        if basis_ids != expected:
            issues.append(
                "Adaptive coverage Basis IDs must exactly bind the current requirements: "
                + ", ".join(expected)
            )
    except ValueError as exc:
        issues.append(str(exc))

    digest = "sha256:" + hashlib.sha256(table.canonical_bytes).hexdigest()
    return CoverageContract(
        status="READY" if not issues else "BLOCKED",
        work_kind=work_kind,
        delivery_profile=profile,
        architecture_disposition=disposition,
        required_sections=tuple(required_sections),
        omissions=tuple(omissions),
        basis_ids=tuple(basis_ids),
        canonical_sha256=digest,
        canonical_bytes=table.canonical_bytes,
    ), issues


def _change_impact_row_issues(
    row: ChangeImpactRow,
    allowed_ids: set[str],
    requirement_ids: set[str],
    disposition: str | None,
    seen: set[str],
) -> tuple[list[str], set[str]]:
    """SAFETY: Validate one change row in its historical diagnostic order."""

    issues: list[str] = []
    stale_targets: set[str] = set()
    if CHANGE_ID.fullmatch(row.change_id) is None:
        issues.append(f"Invalid change-impact ID {row.change_id!r}")
    elif row.change_id in seen:
        issues.append(f"Duplicate change-impact ID {row.change_id}")
    seen.add(row.change_id)
    parsed: dict[str, list[str]] = {}
    for label, value in (
        ("Changed basis IDs", row.changed_basis_ids),
        ("Affected IDs", row.affected_ids),
    ):
        try:
            parsed[label] = canonical_id_list(value, STABLE_CONTRACT_ID, label)
            unknown = sorted(set(parsed[label]) - allowed_ids)
            if unknown:
                issues.append(
                    f"{row.change_id}: {label} contains unknown IDs: "
                    + ", ".join(unknown)
                )
        except ValueError as exc:
            issues.append(f"{row.change_id}: {exc}")
            parsed[label] = []
    if row.preserved_ids == "NONE":
        parsed["Preserved IDs"] = []
    else:
        try:
            parsed["Preserved IDs"] = canonical_id_list(
                row.preserved_ids, STABLE_CONTRACT_ID, "Preserved IDs"
            )
            unknown = sorted(set(parsed["Preserved IDs"]) - allowed_ids)
            if unknown:
                issues.append(
                    f"{row.change_id}: Preserved IDs contains unknown IDs: "
                    + ", ".join(unknown)
                )
        except ValueError as exc:
            issues.append(f"{row.change_id}: {exc}")
            parsed["Preserved IDs"] = []
    overlap = sorted(set(parsed["Affected IDs"]) & set(parsed["Preserved IDs"]))
    if overlap:
        issues.append(
            f"{row.change_id}: IDs cannot be both affected and preserved: "
            + ", ".join(overlap)
        )
    if row.required_revalidation == "FULL_REVALIDATION":
        stale_targets.update({"GATE_A", "GATE_B", "TASKS", "AWS_AUTHORITY"})
    else:
        try:
            revalidation_ids = canonical_id_list(
                row.required_revalidation,
                STABLE_CONTRACT_ID,
                "Required revalidation",
            )
            unknown = sorted(set(revalidation_ids) - allowed_ids)
            if unknown:
                issues.append(
                    f"{row.change_id}: Required revalidation contains unknown IDs: "
                    + ", ".join(unknown)
                )
        except ValueError as exc:
            issues.append(f"{row.change_id}: {exc}")
    changed = set(parsed["Changed basis IDs"])
    affected = set(parsed["Affected IDs"])
    if any(identifier in requirement_ids for identifier in changed):
        stale_targets.update({"GATE_A", "GATE_B", "TASKS", "AWS_AUTHORITY"})
    elif changed or affected:
        stale_targets.update({"GATE_B", "TASKS", "AWS_AUTHORITY"})
    if disposition == "PRESERVE":
        controlled = sorted(
            identifier
            for identifier in changed | affected
            if DESIGN_CONTROLLED_ID.match(identifier)
        )
        if controlled:
            issues.append(
                f"{row.change_id}: PRESERVE cannot change architecture-controlled IDs: "
                + ", ".join(controlled)
            )
    if disposition == "AMEND" and not any(
        DESIGN_CONTROLLED_ID.match(identifier) for identifier in affected
    ):
        issues.append(
            f"{row.change_id}: AMEND must identify at least one affected design ID"
        )
    return issues, stale_targets


def derive_change_impact_contract(
    text: str,
    coverage: CoverageContract,
    allowed_ids: set[str],
    *,
    required: bool,
) -> tuple[ChangeImpactContract, list[str]]:
    """Derive current change impact and its deterministic staleness targets."""

    issues: list[str] = []
    try:
        table = contract_table_after_heading(
            text, CHANGE_IMPACT_HEADING, CHANGE_IMPACT_HEADERS
        )
    except ValueError as exc:
        table = None
        issues.append(f"{CHANGE_IMPACT_HEADING}: {exc}")
    if table is None:
        if required and not issues:
            issues.append(f"Missing {CHANGE_IMPACT_HEADING}")
        return ChangeImpactContract(
            status="BLOCKED" if required else "UNINITIALIZED"
        ), issues
    if not required and any(unresolved(cell) for row in table.rows for cell in row):
        return ChangeImpactContract(
            status="UNINITIALIZED", canonical_bytes=table.canonical_bytes
        ), []

    rows: list[ChangeImpactRow] = []
    seen: set[str] = set()
    stale_targets: set[str] = set()
    disposition = coverage.architecture_disposition
    if required and disposition in {"AMEND", "PRESERVE"} and not table.rows:
        issues.append(f"{disposition} requires at least one change-impact row")
    requirement_ids = authoritative_requirement_ids(text)
    for raw_row in table.rows:
        row = ChangeImpactRow(*raw_row)
        rows.append(row)
        row_issues, row_stale_targets = _change_impact_row_issues(
            row, allowed_ids, requirement_ids, disposition, seen
        )
        issues.extend(row_issues)
        stale_targets.update(row_stale_targets)

    digest = "sha256:" + hashlib.sha256(table.canonical_bytes).hexdigest()
    return ChangeImpactContract(
        status="READY" if not issues else "BLOCKED",
        rows=tuple(rows),
        stale_targets=tuple(sorted(stale_targets)),
        canonical_sha256=digest,
        canonical_bytes=table.canonical_bytes,
    ), issues


__all__ = (
    "ALWAYS_REQUIRED_COVERAGE",
    "ARCHITECTURE_DISPOSITIONS",
    "CHANGE_ID",
    "CHANGE_IMPACT_HEADERS",
    "CHANGE_IMPACT_HEADING",
    "COVERAGE_DOMAINS",
    "COVERAGE_PLAN_HEADERS",
    "COVERAGE_PLAN_HEADING",
    "DELIVERY_PROFILES",
    "PROJECT_MODES",
    "WORK_KINDS",
    "derive_change_impact_contract",
    "derive_coverage_contract",
)
