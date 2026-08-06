"""Pure AWS Core evidence parsing and projection.

Canonical input is already-observed VERIFY Markdown. Results describe current
AWS guidance evidence only; they never approve a gate, access an account, or
grant AWS authority. This module performs no I/O or mutation.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ..core.contracts import (
    contract_table_after_heading,
    split_markdown_table_row,
    without_fenced_code,
)
from ..core.ids import (
    STABLE_CONTRACT_ID,
    canonical_id_list,
    clean_cell,
    explicit_timestamp,
    explicit_value,
    require_explicit_evidence_value,
)
from .models import (
    AWS_CORE_CANONICAL_SKILL_IDENTIFIER_PATTERN,
    AWS_CORE_EVIDENCE_HEADERS,
    AWS_CORE_EVIDENCE_HEADERS_V1,
    AWS_CORE_EVIDENCE_PHASES,
    AWS_CORE_EVIDENCE_STATUSES,
    AWS_CORE_OBSERVATION_ACTOR,
    AWS_CORE_OFFICIAL_DOCUMENTATION_REFERENCE_PATTERN,
    AWS_CORE_OFFICIAL_DOCUMENTATION_URL_PATTERN,
    AWS_CORE_OFFICIAL_IDENTITY,
    AWS_CORE_OFFICIAL_SOURCE,
    AWS_CORE_PLUGIN_VERSION_PATTERN,
    AWS_CORE_REQUIRED_CAPABILITIES,
    AWS_DISCOVERY_ID,
    AWS_DEPLOYMENT_EVIDENCE_HEADERS,
    AWS_DEPLOYMENT_EVIDENCE_HEADING,
    AWS_READ_PREFLIGHT_HEADERS,
    AWS_READ_PREFLIGHT_HEADING,
    AWS_TEARDOWN_EVIDENCE_HEADERS,
    AWS_TEARDOWN_EVIDENCE_HEADING,
    TECHNOLOGY_DECISION_ID,
    AwsCoreEvidenceRow,
)


def parse_read_preflight_evidence(text: str) -> list[dict[str, str]]:
    """Parse the exact read-only AWS preflight table."""

    table = contract_table_after_heading(
        text, AWS_READ_PREFLIGHT_HEADING, AWS_READ_PREFLIGHT_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def parse_teardown_reconciliation_evidence(text: str) -> list[dict[str, str]]:
    """Parse the append-only AWS-40/AWS-50 journal."""

    table = contract_table_after_heading(
        text, AWS_TEARDOWN_EVIDENCE_HEADING, AWS_TEARDOWN_EVIDENCE_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def parse_deployment_reconciliation_evidence(
    text: str,
) -> list[dict[str, str]]:
    """Parse the append-only AWS-20/AWS-30 deployment journal."""

    table = contract_table_after_heading(
        text, AWS_DEPLOYMENT_EVIDENCE_HEADING, AWS_DEPLOYMENT_EVIDENCE_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def parse_aws_core_evidence(
    text: str,
    *,
    allow_legacy: bool = False,
) -> dict[tuple[str, str, str], AwsCoreEvidenceRow]:
    """SAFETY: parse linked runtime skill-discovery evidence chains."""

    structural = without_fenced_code(text)
    headings = list(
        re.finditer(r"^## AWS Core evidence[ \t]*$", structural, re.MULTILINE)
    )
    if len(headings) != 1:
        raise ValueError("VERIFY.md requires exactly one AWS Core evidence section")
    following = re.search(r"^##\s+", structural[headings[0].end() :], re.MULTILINE)
    end = headings[0].end() + following.start() if following else len(structural)
    lines = structural[headings[0].end() : end].splitlines()

    headers = AWS_CORE_EVIDENCE_HEADERS
    header_indexes = [
        index
        for index, line in enumerate(lines)
        if split_markdown_table_row(line) == list(headers)
    ]
    legacy = False
    if len(header_indexes) != 1 and allow_legacy:
        headers = AWS_CORE_EVIDENCE_HEADERS_V1
        header_indexes = [
            index
            for index, line in enumerate(lines)
            if split_markdown_table_row(line) == list(headers)
        ]
        legacy = len(header_indexes) == 1
    if len(header_indexes) != 1:
        raise ValueError("VERIFY.md requires one exact AWS Core evidence table")
    header = header_indexes[0]
    separator = (
        split_markdown_table_row(lines[header + 1]) if header + 1 < len(lines) else None
    )
    if (
        separator is None
        or len(separator) != len(headers)
        or any(re.fullmatch(r":?-{3,}:?", cell) is None for cell in separator)
    ):
        raise ValueError("VERIFY.md AWS Core evidence separator is invalid")

    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow] = {}
    discovery_phases: dict[str, str] = {}
    for line in lines[header + 2 :]:
        if not line.strip():
            if rows:
                break
            continue
        cells = split_markdown_table_row(line)
        if cells is None:
            if rows:
                break
            raise ValueError("VERIFY.md AWS Core evidence row is missing")
        if len(cells) != len(headers):
            raise ValueError(
                f"VERIFY.md AWS Core evidence row must have {len(headers)} cells"
            )
        cleaned = tuple(clean_cell(cell) for cell in cells)
        if legacy:
            row = AwsCoreEvidenceRow(
                cleaned[0],
                "",
                "",
                *cleaned[1:9],
                "",
                *cleaned[9:],
            )
        else:
            row = AwsCoreEvidenceRow(*cleaned)
        if row.phase not in AWS_CORE_EVIDENCE_PHASES:
            raise ValueError(
                f"VERIFY.md AWS Core evidence has unknown phase {row.phase!r}"
            )
        capability = row.capability.replace("`", "").strip()
        if capability not in AWS_CORE_REQUIRED_CAPABILITIES:
            raise ValueError(
                f"{row.phase} AWS Core evidence has unknown capability {capability!r}"
            )
        if not legacy and AWS_DISCOVERY_ID.fullmatch(row.discovery_id) is None:
            raise ValueError(
                f"{row.phase} AWS Core evidence has invalid Discovery ID {row.discovery_id!r}"
            )
        owner = discovery_phases.setdefault(row.discovery_id, row.phase)
        if row.discovery_id and owner != row.phase:
            raise ValueError(
                f"{row.discovery_id} AWS Core discovery ID is reused across phases"
            )
        key = (row.phase, row.discovery_id, capability)
        if key in rows:
            raise ValueError(
                f"VERIFY.md AWS Core evidence duplicates {row.phase} "
                f"{row.discovery_id or 'legacy'} {capability}"
            )
        if row.observed_status not in AWS_CORE_EVIDENCE_STATUSES:
            raise ValueError(
                f"{row.phase} {capability} AWS Core evidence has invalid status"
            )
        rows[key] = row

    missing: list[str] = []
    present_phases = sorted(
        {row_phase for row_phase, _discovery_id, _capability in rows}
    )
    for phase in present_phases:
        discovery_ids = sorted(
            {discovery_id for row_phase, discovery_id, _ in rows if row_phase == phase}
        )
        if not discovery_ids:
            missing.append(f"{phase} discovery chain")
            continue
        for discovery_id in discovery_ids:
            for capability in AWS_CORE_REQUIRED_CAPABILITIES:
                if (phase, discovery_id, capability) not in rows:
                    missing.append(f"{phase} {discovery_id or 'legacy'} {capability}")
    if missing:
        raise ValueError(
            "VERIFY.md AWS Core evidence is missing linked rows: " + ", ".join(missing)
        )
    return rows


def validate_advisory_design_binding(
    value: str,
    phase: str,
    *,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
) -> None:
    """SAFETY: reject advisory evidence that selects or mismatches a design."""

    cleaned = clean_cell(value)
    if phase == "REQ-10":
        expected = (
            "NOT_APPLICABLE \u2014 requirements feasibility only; "
            "no architecture selected"
        )
        if cleaned != expected:
            raise ValueError(
                "REQ-10 Advisory Design binding must prove requirements feasibility "
                "without selecting an architecture"
            )
        return
    not_applicable_prefix = "NOT_APPLICABLE — "
    if cleaned.startswith(not_applicable_prefix):
        if phase not in {"REQ-10", "AWS-10"} or not explicit_value(
            cleaned[len(not_applicable_prefix) :], allow_none=False
        ):
            raise ValueError(
                f"{phase} Advisory Design binding has invalid NOT_APPLICABLE form"
            )
        return
    match = re.fullmatch(r"(?P<design>DES-\d{4,}); TECH: (?P<technology>.+)", cleaned)
    if match is None:
        raise ValueError(
            f"{phase} Advisory Design binding must use DES-nnnn; TECH: <TECH IDs> "
            "or DES-nnnn; TECH: NONE — <reason>"
        )
    design_revision = match.group("design")
    if (
        expected_design_revision is not None
        and design_revision != expected_design_revision
    ):
        raise ValueError(
            f"{phase} Advisory Design binding must reference {expected_design_revision}"
        )
    technology = match.group("technology")
    none_prefix = "NONE — "
    if technology.startswith(none_prefix):
        if not explicit_value(technology[len(none_prefix) :], allow_none=False):
            raise ValueError(
                f"{phase} Advisory Design binding requires a concrete NONE reason"
            )
        return
    identifiers = [item.strip() for item in technology.split(",")]
    if not identifiers or any(
        TECHNOLOGY_DECISION_ID.fullmatch(item) is None for item in identifiers
    ):
        raise ValueError(
            f"{phase} Advisory Design binding TECH values must be comma-separated TECH-nnnn IDs"
        )
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{phase} Advisory Design binding contains duplicate TECH IDs")
    if approved_tech_ids is not None:
        unknown = sorted(set(identifiers) - approved_tech_ids)
        if unknown:
            raise ValueError(
                f"{phase} Advisory Design binding references unapproved TECH IDs: "
                + ", ".join(unknown)
            )


def _unlinked_aws_core_phase_evidence_issues(
    rows: dict[tuple[str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    expected_binding: str | None = None,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
) -> list[str]:
    """SAFETY: explain why current official AWS evidence is not ready."""

    issues: list[str] = []
    observed_versions: set[str] = set()
    for capability in AWS_CORE_REQUIRED_CAPABILITIES:
        row = rows.get((phase, capability))
        label = f"{phase} {capability}"
        if row is None or row.observed_status not in {"PASS", "VERIFIED"}:
            issues.append(f"{label} requires fresh PASS evidence")
            continue
        if row.plugin_source != AWS_CORE_OFFICIAL_SOURCE:
            issues.append(f"{label} plugin source must be {AWS_CORE_OFFICIAL_SOURCE}")
        if row.invoked_plugin_identity != AWS_CORE_OFFICIAL_IDENTITY:
            issues.append(
                f"{label} invoked plugin identity must be {AWS_CORE_OFFICIAL_IDENTITY}"
            )
        version = clean_cell(row.observed_plugin_version)
        if AWS_CORE_PLUGIN_VERSION_PATTERN.fullmatch(version) is None:
            issues.append(
                f"{label} Observed plugin version must be an observed semantic version"
            )
        else:
            observed_versions.add(version)
        if row.observation_actor != AWS_CORE_OBSERVATION_ACTOR:
            issues.append(
                f"{label} Observation actor must be {AWS_CORE_OBSERVATION_ACTOR}"
            )
        if row.credentials_inspected != "NO":
            issues.append(f"{label} Credentials inspected must be NO")
        if row.aws_account_accessed != "NO":
            issues.append(f"{label} AWS account accessed must be NO")
        try:
            validate_advisory_design_binding(
                row.advisory_design_binding,
                phase,
                expected_design_revision=expected_design_revision,
                approved_tech_ids=approved_tech_ids,
            )
        except ValueError as exc:
            issues.append(str(exc))
        if capability == "retrieve_skill":
            try:
                require_explicit_evidence_value(
                    row.requested_skill, f"{label} Requested skill"
                )
            except ValueError as exc:
                issues.append(str(exc))
            try:
                returned_identifier = require_explicit_evidence_value(
                    row.returned_skill_identifier,
                    f"{label} Returned skill identifier",
                )
            except ValueError as exc:
                issues.append(str(exc))
            else:
                if (
                    AWS_CORE_CANONICAL_SKILL_IDENTIFIER_PATTERN.fullmatch(
                        returned_identifier
                    )
                    is None
                ):
                    issues.append(
                        f"{label} Returned skill identifier must be canonical"
                    )
        else:
            try:
                require_explicit_evidence_value(
                    row.documentation_query, f"{label} Documentation query"
                )
            except ValueError as exc:
                issues.append(str(exc))
            try:
                source_references = require_explicit_evidence_value(
                    row.source_references, f"{label} Source references"
                )
            except ValueError as exc:
                issues.append(str(exc))
            else:
                if (
                    AWS_CORE_OFFICIAL_DOCUMENTATION_REFERENCE_PATTERN.search(
                        source_references
                    )
                    is None
                ):
                    issues.append(
                        f"{label} Source references must include returned "
                        "official AWS documentation"
                    )
        if not explicit_timestamp(row.observed_at):
            issues.append(f"{label} Observed at must be ISO 8601 with timezone")
        try:
            binding = require_explicit_evidence_value(
                row.evidence_binding, f"{label} Evidence binding"
            )
        except ValueError as exc:
            issues.append(str(exc))
        else:
            if expected_binding is not None and binding != clean_cell(expected_binding):
                issues.append(
                    f"{label} Evidence binding does not match current "
                    f"{clean_cell(expected_binding)}"
                )
    if len(observed_versions) > 1:
        issues.append(
            f"{phase} capability rows must record one observed plugin version"
        )
    return issues


def aws_core_phase_evidence_issues(
    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    expected_binding: str | None = None,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
    expected_basis_ids: set[str] | None = None,
    allow_legacy_discovery: bool = False,
) -> list[str]:
    """SAFETY: validate ordered, source-attributed AWS evidence chains."""

    discovery_ids = sorted(
        {discovery_id for row_phase, discovery_id, _ in rows if row_phase == phase}
    )
    if not discovery_ids:
        return [f"{phase} requires at least one AWS-DISC discovery chain"]
    if "" in discovery_ids:
        if not allow_legacy_discovery or len(discovery_ids) != 1:
            return [f"{phase} legacy AWS Core evidence requires discovery migration"]
        legacy = {
            (phase, capability): rows[(phase, "", capability)]
            for capability in AWS_CORE_REQUIRED_CAPABILITIES
            if (phase, "", capability) in rows
        }
        return _unlinked_aws_core_phase_evidence_issues(
            legacy,
            phase,
            expected_binding=expected_binding,
            expected_design_revision=expected_design_revision,
            approved_tech_ids=approved_tech_ids,
        )

    issues: list[str] = []
    for discovery_id in discovery_ids:
        chain = {
            (phase, capability): rows[(phase, discovery_id, capability)]
            for capability in AWS_CORE_REQUIRED_CAPABILITIES
            if (phase, discovery_id, capability) in rows
        }
        issues.extend(
            _unlinked_aws_core_phase_evidence_issues(
                chain,
                phase,
                expected_binding=expected_binding,
                expected_design_revision=expected_design_revision,
                approved_tech_ids=approved_tech_ids,
            )
        )
        search = chain.get((phase, "search_documentation"))
        retrieve = chain.get((phase, "retrieve_skill"))
        if search is None or retrieve is None:
            issues.append(
                f"{phase} {discovery_id} requires linked search and retrieve rows"
            )
            continue

        try:
            basis_ids = canonical_id_list(
                search.basis_ids,
                STABLE_CONTRACT_ID,
                f"{phase} {discovery_id} Basis IDs",
            )
        except ValueError as exc:
            issues.append(str(exc))
            basis_ids = []
        if expected_basis_ids is not None and set(basis_ids) != expected_basis_ids:
            issues.append(
                f"{phase} {discovery_id} Basis IDs must exactly match the current "
                "AWS materiality basis IDs"
            )
        if expected_design_revision and expected_design_revision not in basis_ids:
            issues.append(
                f"{phase} {discovery_id} Basis IDs must include {expected_design_revision}"
            )

        try:
            discovered = canonical_id_list(
                search.discovered_skill_identifiers,
                AWS_CORE_CANONICAL_SKILL_IDENTIFIER_PATTERN,
                f"{phase} {discovery_id} Discovered skill identifiers",
            )
        except ValueError as exc:
            issues.append(str(exc))
            discovered = []

        shared = (
            "basis_ids",
            "plugin_source",
            "invoked_plugin_identity",
            "observed_plugin_version",
            "observation_actor",
            "discovered_skill_identifiers",
            "advisory_design_binding",
            "credentials_inspected",
            "aws_account_accessed",
            "evidence_binding",
        )
        for field_name in shared:
            if getattr(search, field_name) != getattr(retrieve, field_name):
                issues.append(f"{phase} {discovery_id} rows must share {field_name}")
        if retrieve.requested_skill != retrieve.returned_skill_identifier:
            issues.append(
                f"{phase} {discovery_id} retrieved identifier must equal the selected identifier"
            )
        if retrieve.returned_skill_identifier not in discovered:
            issues.append(
                f"{phase} {discovery_id} retrieved identifier was not returned by search"
            )

        if explicit_timestamp(search.observed_at) and explicit_timestamp(
            retrieve.observed_at
        ):
            searched_at = datetime.fromisoformat(
                search.observed_at.replace("Z", "+00:00")
            )
            retrieved_at = datetime.fromisoformat(
                retrieve.observed_at.replace("Z", "+00:00")
            )
            if retrieved_at < searched_at:
                issues.append(
                    f"{phase} {discovery_id} retrieve timestamp precedes search"
                )
    return issues


def derive_aws_core_observed_usage(
    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    issues: Sequence[str],
) -> dict[str, Any]:
    """Project only validated observable AWS Core use into owner-safe fields."""

    unobserved: dict[str, Any] = {
        "status": "UNOBSERVED",
        "phase": phase,
        "chains": [],
    }
    if issues:
        return unobserved
    chains: list[dict[str, Any]] = []
    discovery_ids = sorted(
        {
            discovery_id
            for row_phase, discovery_id, _capability in rows
            if row_phase == phase and discovery_id
        }
    )
    for discovery_id in discovery_ids:
        search = rows.get((phase, discovery_id, "search_documentation"))
        retrieve = rows.get((phase, discovery_id, "retrieve_skill"))
        if search is None or retrieve is None:
            continue
        references = sorted(
            set(
                AWS_CORE_OFFICIAL_DOCUMENTATION_URL_PATTERN.findall(
                    search.source_references
                )
            )
        )
        if not references:
            continue
        chains.append(
            {
                "discovery_id": discovery_id,
                "skill_identifier": retrieve.returned_skill_identifier,
                "official_references": references,
                "credentials_inspected": False,
                "aws_account_accessed": False,
            }
        )
    if not chains:
        return unobserved
    return {"status": "OBSERVED", "phase": phase, "chains": chains}


def aws_core_evidence_diagnostic_code(issue: str) -> str:
    """Classify generated AWS evidence gaps without assigning them to the owner."""

    if (
        "requires at least one AWS-DISC discovery chain" in issue
        or "requires linked search and retrieve rows" in issue
    ):
        return "AWS_CORE_DISCOVERY_REQUIRED"
    if any(
        marker in issue
        for marker in (
            "does not match current",
            "must exactly match the current",
            "must include DES-",
        )
    ):
        return "AWS_CORE_EVIDENCE_STALE"
    return "AWS_CORE_EVIDENCE_GENERATED_INVALID"


__all__ = (
    "aws_core_evidence_diagnostic_code",
    "aws_core_phase_evidence_issues",
    "derive_aws_core_observed_usage",
    "parse_deployment_reconciliation_evidence",
    "parse_aws_core_evidence",
    "parse_read_preflight_evidence",
    "parse_teardown_reconciliation_evidence",
    "validate_advisory_design_binding",
)
