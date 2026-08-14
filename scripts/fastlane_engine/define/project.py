"""Brownfield, Gate A readiness, and AWS materiality Define contracts.

Canonical inputs are caller-supplied PRD text or already-parsed Gate A records.
Outputs are ordered issue records and a derived materiality projection. This
module is pure and cannot read files, mutate state, approve Gate A, call AWS, or
grant external authority. Diagnostic text retains the characterized contract.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ..core.contracts import (
    _heading_section_lines,
    markdown_tables,
    table_after_heading,
)
from ..core.ids import (
    STABLE_CONTRACT_ID,
    canonical_id_list,
    clean_cell,
    explicit_value,
)


REQ_ID = re.compile(r"REQ-\d{4,}")
RA_ID = re.compile(r"RA-\d{3,}")
DEC_ID = re.compile(r"DEC-\d{3,}")
AWS_DISCOVERY_ID = re.compile(r"AWS-DISC-\d{4,}")
AWS_CORE_MATERIALITY_VALUES = {"REQUIRED", "OPTIONAL", "NOT_MATERIAL"}
BROWNFIELD_BASELINE_FIELDS = {
    "Repository and baseline commit",
    "Deployed environments and observed versions",
    "Existing architecture and ownership",
    "Current interfaces, schemas, and consumers",
    "Current data stores and migration constraints",
    "Existing security and compliance controls",
    "Baseline verification commands",
    "Baseline evidence location",
    "Known defects and accepted debt",
    "Repository-to-environment drift",
    "Dirty or user-owned working-tree changes",
    "Protected files and components",
    "Unresolved bootstrap overlay collisions",
}
GATE_A_READINESS_FIELDS = {
    "Outcome",
    "Owner and users",
    "Scope and non-goals",
    "Measurable requirement/acceptance IDs",
    "Data boundary",
    "Identity/security boundary",
    "Environment/Region",
    "Failure/recovery",
    "Cost posture",
    "Intake provenance",
}


def _section_body(text: str, heading: str) -> str:
    section = _heading_section_lines(text, heading)
    return "\n".join(section[1]) if section else ""


def gate_a_product_truth_issues(
    text: str,
    gate_a_agent: Mapping[str, str],
    current_requirement_ids: set[str],
) -> list[tuple[str, str]]:
    """Validate the owner-visible Product Agreement before Gate A can advance."""

    issues: list[tuple[str, str]] = []
    try:
        workload = table_after_heading(text, "## 1. Workload profile")
    except ValueError:
        workload = {}
    unresolved_workload = sorted(
        field
        for field, value in workload.items()
        if not explicit_value(value, allow_none=True)
    )
    if not workload or unresolved_workload:
        issues.append(
            (
                "GATE_A_READINESS_CARD",
                "Workload profile has unresolved fields: "
                + (", ".join(unresolved_workload) or "profile table missing"),
            )
        )
    for heading in ("## 2. Product statement", "## 3. Problem and opportunity"):
        body = " ".join(_section_body(text, heading).split())
        if not explicit_value(body, allow_none=False):
            issues.append(("GATE_A_READINESS_CARD", f"{heading} is unresolved"))
    for heading in ("### Goals", "### Non-goals"):
        entries = re.findall(
            r"(?m)^\s*(?:\d+\.|-)\s+(.+)$",
            _section_body(text, heading),
        )
        if not any(explicit_value(entry, allow_none=False) for entry in entries):
            issues.append(("GATE_A_READINESS_CARD", f"{heading} is unresolved"))
    story_tables = markdown_tables(_section_body(text, "### User stories"))
    stories = story_tables[0][2:] if story_tables else []
    if not any(
        len(row) >= 4
        and explicit_value(row[1], allow_none=False)
        and set(STABLE_CONTRACT_ID.findall(row[3])) <= current_requirement_ids
        and any(
            identifier in current_requirement_ids
            for identifier in STABLE_CONTRACT_ID.findall(row[3])
        )
        for row in stories
    ):
        issues.append(
            ("GATE_A_READINESS_CARD", "User stories lack a current requirement link")
        )

    finding_tables = markdown_tables(_section_body(text, "### Findings"))
    decision_tables = markdown_tables(_section_body(text, "### Open decisions"))
    open_findings = {
        row[0]
        for row in (finding_tables[0][2:] if finding_tables else [])
        if len(row) >= 7
        and RA_ID.fullmatch(row[0])
        and clean_cell(row[5]).casefold() == "yes"
        and clean_cell(row[6]).casefold() not in {"closed", "resolved", "accepted"}
    }
    open_decisions = {
        row[0]
        for row in (decision_tables[0][2:] if decision_tables else [])
        if len(row) >= 6
        and DEC_ID.fullmatch(row[0])
        and clean_cell(row[4]).casefold() == "yes"
        and not explicit_value(row[5], allow_none=False)
    }
    for field, actual, pattern in (
        ("Open blocking finding IDs", open_findings, RA_ID),
        ("Open blocking decision IDs", open_decisions, DEC_ID),
    ):
        raw = clean_cell(gate_a_agent.get(field, ""))
        try:
            declared = (
                set() if raw == "NONE" else set(canonical_id_list(raw, pattern, field))
            )
        except ValueError:
            declared = None
        if declared != actual:
            issues.append(
                (
                    "GATE_A_BLOCKER",
                    f"{field} must exactly match detailed open blockers",
                )
            )
    return issues


def brownfield_contract_issues(text: str) -> list[tuple[str, str]]:
    """SAFETY: Return ordered brownfield baseline and preservation issues."""

    issues: list[tuple[str, str]] = []
    heading = "### 1.2 Brownfield baseline and preservation contract"
    matches = list(re.finditer(rf"^{re.escape(heading)}\s*$", text, re.MULTILINE))
    if len(matches) != 1:
        return [("BROWNFIELD_PRD_BASELINE", f"Expected exactly one {heading!r}")]
    next_heading = re.search(r"^##\s+2\.", text[matches[0].end() :], re.MULTILINE)
    end = matches[0].end() + next_heading.start() if next_heading else len(text)
    tables = markdown_tables(text[matches[0].end() : end])
    if len(tables) < 2:
        return [
            (
                "BROWNFIELD_PRD_BASELINE",
                "Brownfield approval requires both baseline and preservation tables",
            )
        ]
    baseline: dict[str, str] = {}
    for row in tables[0][2:]:
        if len(row) >= 2:
            if row[0] in baseline:
                issues.append(
                    (
                        "BROWNFIELD_PRD_BASELINE",
                        f"Duplicate brownfield field {row[0]!r}",
                    )
                )
            baseline[row[0]] = row[1]
    missing = sorted(BROWNFIELD_BASELINE_FIELDS - set(baseline))
    if missing:
        issues.append(
            (
                "BROWNFIELD_PRD_BASELINE",
                "Brownfield baseline is missing fields: " + ", ".join(missing),
            )
        )
    unresolved_fields = sorted(
        field
        for field in BROWNFIELD_BASELINE_FIELDS
        if not explicit_value(baseline.get(field, ""), allow_none=True)
    )
    if unresolved_fields:
        issues.append(
            (
                "BROWNFIELD_PRD_BASELINE",
                "Brownfield baseline has unresolved fields: "
                + ", ".join(unresolved_fields),
            )
        )
    preservation_rows = [
        row
        for row in tables[1][2:]
        if row and re.fullmatch(r"PRES-\d+", row[0]) is not None
    ]
    if not preservation_rows:
        issues.append(
            (
                "BROWNFIELD_PRD_PRESERVATION",
                "Brownfield approval requires at least one explicit PRES record",
            )
        )
    for row in preservation_rows:
        if len(row) < 5 or any(
            not explicit_value(value, allow_none=False) for value in row[1:5]
        ):
            issues.append(
                (
                    "BROWNFIELD_PRD_PRESERVATION",
                    f"{row[0]} must explicitly define the preserved behavior and change boundary",
                )
            )
    return issues


def gate_a_readiness_card_issues(
    card: Mapping[str, str],
) -> list[tuple[str, str]]:
    """Validate the exact current Gate A readiness-card fields."""

    issues: list[tuple[str, str]] = []
    if set(card) != GATE_A_READINESS_FIELDS:
        issues.append(
            (
                "GATE_A_READINESS_CARD",
                "GATE A readiness-card fields must be exact",
            )
        )
    for field_name in sorted(GATE_A_READINESS_FIELDS):
        value = clean_cell(card.get(field_name, ""))
        if field_name == "Outstanding gaps" and value == "NONE":
            continue
        if value.startswith("NOT_APPLICABLE — ") and explicit_value(
            value.removeprefix("NOT_APPLICABLE — ")
        ):
            continue
        if not explicit_value(value, allow_none=False):
            issues.append(
                (
                    "GATE_A_READINESS_CARD",
                    f"{field_name} is not an explicit current decision basis",
                )
            )
    return issues


def derive_req_aws_materiality(
    gate_a_agent: Mapping[str, str],
    requirements_revision: str,
    *,
    required: bool,
    grandfather_current_gate_a: bool,
) -> tuple[dict[str, Any], list[str]]:
    """SAFETY: Derive ordered AWS materiality without inventing AWS facts."""

    raw_materiality = clean_cell(gate_a_agent.get("AWS Core materiality", ""))
    raw_basis = clean_cell(gate_a_agent.get("AWS materiality basis IDs", ""))
    raw_discovery = clean_cell(gate_a_agent.get("AWS Core discovery IDs", ""))
    raw_unresolved = clean_cell(
        gate_a_agent.get("Unresolved material AWS fact IDs", "")
    )
    issues: list[str] = []
    if raw_materiality not in AWS_CORE_MATERIALITY_VALUES:
        if grandfather_current_gate_a:
            return (
                {
                    "materiality": "OPTIONAL",
                    "status": "GRANDFATHERED",
                    "source": "LEGACY_UNRECORDED",
                    "basis_ids": [requirements_revision]
                    if REQ_ID.fullmatch(requirements_revision)
                    else [],
                    "discovery_ids": [],
                    "unresolved_fact_ids": [],
                },
                [],
            )
        if not required:
            return (
                {
                    "materiality": "OPTIONAL",
                    "status": "UNASSESSED",
                    "source": "CURRENT_PRD",
                    "basis_ids": [],
                    "discovery_ids": [],
                    "unresolved_fact_ids": [],
                },
                [],
            )
        issues.append(
            "AWS Core materiality must be exactly REQUIRED, OPTIONAL, or NOT_MATERIAL"
        )

    def ids_or_none(
        value: str, pattern: re.Pattern[str], label: str
    ) -> tuple[list[str], bool]:
        if value == "NONE" or value.startswith("NONE — "):
            reason = value[6:].strip() if value.startswith("NONE — ") else ""
            if value.startswith("NONE — ") and not explicit_value(reason):
                raise ValueError(f"{label} NONE form requires a concrete reason")
            return [], True
        return canonical_id_list(value, pattern, label), False

    basis_ids: list[str] = []
    discovery_ids: list[str] = []
    unresolved_ids: list[str] = []
    basis_none = discovery_none = unresolved_none = False
    try:
        basis_ids, basis_none = ids_or_none(
            raw_basis, STABLE_CONTRACT_ID, "AWS materiality basis IDs"
        )
    except ValueError as exc:
        issues.append(str(exc))
    try:
        discovery_ids, discovery_none = ids_or_none(
            raw_discovery, AWS_DISCOVERY_ID, "AWS Core discovery IDs"
        )
    except ValueError as exc:
        issues.append(str(exc))
    try:
        unresolved_ids, unresolved_none = ids_or_none(
            raw_unresolved,
            STABLE_CONTRACT_ID,
            "Unresolved material AWS fact IDs",
        )
    except ValueError as exc:
        issues.append(str(exc))
    basis_none_with_reason = raw_basis.startswith("NONE — ")
    discovery_none_with_reason = raw_discovery.startswith("NONE — ")
    if (
        not basis_none
        and requirements_revision
        and requirements_revision not in basis_ids
    ):
        issues.append(f"AWS materiality basis IDs must include {requirements_revision}")
    if raw_materiality == "REQUIRED":
        if basis_none or not basis_ids:
            issues.append("REQUIRED AWS materiality needs current basis IDs")
        if discovery_none or not discovery_ids:
            issues.append("REQUIRED AWS materiality needs current AWS-DISC evidence")
        if not unresolved_none or unresolved_ids:
            issues.append(
                "REQUIRED AWS materiality cannot retain unresolved AWS fact IDs at Gate A"
            )
    elif raw_materiality == "OPTIONAL":
        if basis_none and not basis_none_with_reason:
            issues.append(
                "OPTIONAL AWS materiality needs basis IDs or NONE with a reason"
            )
        if discovery_none and not discovery_none_with_reason:
            issues.append(
                "OPTIONAL AWS materiality needs AWS-DISC IDs or NONE with a reason"
            )
        if not unresolved_none or unresolved_ids:
            issues.append(
                "OPTIONAL AWS materiality cannot retain unresolved material AWS fact IDs"
            )
    elif raw_materiality == "NOT_MATERIAL":
        if not basis_none or basis_ids or not basis_none_with_reason:
            issues.append(
                "NOT_MATERIAL requires AWS materiality basis IDs NONE with a reason"
            )
        if not discovery_none or discovery_ids or not discovery_none_with_reason:
            issues.append(
                "NOT_MATERIAL requires AWS Core discovery IDs NONE with a reason"
            )
        if not unresolved_none or unresolved_ids:
            issues.append("NOT_MATERIAL cannot retain unresolved AWS fact IDs")
    return (
        {
            "materiality": raw_materiality
            if raw_materiality in AWS_CORE_MATERIALITY_VALUES
            else "OPTIONAL",
            "status": "CURRENT" if not issues else "BLOCKED",
            "source": "CURRENT_PRD",
            "basis_ids": basis_ids,
            "discovery_ids": discovery_ids,
            "unresolved_fact_ids": unresolved_ids,
        },
        issues,
    )


__all__ = (
    "AWS_CORE_MATERIALITY_VALUES",
    "BROWNFIELD_BASELINE_FIELDS",
    "GATE_A_READINESS_FIELDS",
    "brownfield_contract_issues",
    "derive_req_aws_materiality",
    "gate_a_product_truth_issues",
    "gate_a_readiness_card_issues",
)
