"""Requirements, journeys, assumptions, and Gate A method evaluation.

Canonical input is the current PRD plus an already-derived intake projection.
Outputs are immutable requirements projections and ordered issue records. This
module performs no I/O, routing, mutation, approval, authorization, or owner
rendering. Requirements 1.4 and approved legacy grandfathering remain exactly
compatible with the characterized pre-extraction behavior.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..core.contracts import (
    ContractTable,
    contract_table_after_heading,
    markdown_tables,
    table_after_heading,
    without_fenced_code,
)
from ..core.ids import (
    STABLE_CONTRACT_ID,
    clean_cell,
    explicit_value,
    parse_exact_id_list,
    unresolved,
)
from .intake import PROJECT_MODES, derive_intake_foundation_contract
from .models import (
    AssumptionLifecycleRecord,
    IntakeFoundationContract,
    RequirementsChangeLineage,
    RequirementsContract,
)


NORMATIVE_REQUIREMENT_HEADERS = (
    "ID",
    "Requirement",
    "EARS form",
    "Acceptance ID",
    "Acceptance criteria",
    "Acceptance form",
)
LEGACY_NORMATIVE_REQUIREMENT_HEADERS = (
    "ID",
    "Requirement",
    "EARS form",
    "Acceptance criteria",
    "Acceptance form",
)
LEGACY_REQUIREMENT_HEADERS = ("ID", "Requirement", "Acceptance criteria")
PROJECT_CONTRACT_SCHEMA = "1.4"
REQUIREMENTS_CHANGE_LINEAGE_HEADING = "### Requirements change lineage"
REQUIREMENTS_CHANGE_LINEAGE_HEADERS = (
    "Current revision",
    "Prior revision",
    "Trigger",
    "Added IDs",
    "Changed IDs",
    "Removed IDs",
    "Preserved IDs",
    "Stale reason",
    "Required revalidation",
)
ASSUMPTION_LIFECYCLE_HEADING = "### Assumption lifecycle"
ASSUMPTION_LIFECYCLE_HEADERS = (
    "Assumption ID",
    "Assumption",
    "Status",
    "Basis IDs",
    "Validation or successor",
)
ASSUMPTION_STATUSES = {
    "PROPOSED",
    "ACCEPTED",
    "VALIDATED",
    "INVALIDATED",
    "SUPERSEDED",
}
REQUIREMENTS_REVISION_ID = re.compile(r"REQ-\d{4,}")
ASSUMPTION_ID = re.compile(r"ASM-\d{3,}")
ACTOR_HEADING = "## 4. Users and outcomes"
ACTOR_HEADERS = (
    "Actor ID",
    "Actor or external system",
    "Kind",
    "Desired outcome or responsibility",
    "Permission/data boundary",
    "Intake basis IDs",
)
ACTOR_KINDS = {"PRIMARY_USER", "SECONDARY_USER", "OPERATOR", "EXTERNAL_SYSTEM"}
ACTOR_ID = re.compile(r"ACT-\d{3,}")
ACCEPTANCE_ID = re.compile(r"AC-[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
ACCEPTANCE_TEST_BINDING_ID = re.compile(r"\b(?:TEST|PROP|EV)-\d{3,}\b")
JOURNEY_HEADING = "### Journey register"
JOURNEY_HEADERS = (
    "Journey ID",
    "Actor IDs",
    "Goal",
    "Trigger",
    "Main success outcome",
    "Alternate/failure behavior",
    "Requirement IDs",
    "Rich-use-case triggers",
)
JOURNEY_ID = re.compile(r"JOURNEY-\d{3,}")
RICH_USE_CASE_TRIGGERS = {
    "DISTINCT_PERMISSIONED_ACTORS",
    "CONFIDENTIAL_OR_REGULATED_MUTATION",
    "MONEY_OR_ENTITLEMENT",
    "IRREVERSIBLE_ACTION",
    "MIGRATION_OR_CUTOVER",
    "ASYNCHRONOUS_WORK",
    "PARTIAL_FAILURE",
}
RICH_USE_CASE_APPLICABILITY_HEADING = "### Rich-use-case applicability"
RICH_USE_CASE_APPLICABILITY_HEADERS = (
    "Applicability",
    "Trigger basis",
    "Use-case IDs",
)
RICH_USE_CASE_HEADING = "### Rich use cases"
RICH_USE_CASE_HEADERS = (
    "Use case ID",
    "Journey ID",
    "Primary actor ID",
    "Stakeholder interests",
    "Preconditions",
    "Success guarantee",
    "Minimum failure guarantee",
    "Business rule IDs",
    "Requirement IDs",
)
USE_CASE_ID = re.compile(r"USECASE-\d{3,}")
BUSINESS_RULE_HEADING = "### Business rules"
BUSINESS_RULE_HEADERS = (
    "Rule ID",
    "Rule",
    "Basis IDs",
    "Journey/use-case IDs",
    "Validation ID",
)
BUSINESS_RULE_ID = re.compile(r"BR-\d{3,}")
REQUIREMENT_COVERAGE_HEADING = "### Requirement coverage"
REQUIREMENT_COVERAGE_HEADERS = (
    "Requirement ID",
    "Intake basis IDs",
    "Actor IDs",
    "Journey IDs",
    "Acceptance/test IDs",
    "Approved success measure ID",
)
EARS_FORMS = {
    "UBIQUITOUS",
    "EVENT_DRIVEN",
    "STATE_DRIVEN",
    "UNWANTED_BEHAVIOR",
    "OPTIONAL_FEATURE",
    "COMPLEX",
}
EARS_PATTERNS = {
    "UBIQUITOUS": re.compile(r"The (?P<subject>.+?) SHALL (?P<response>.+)\."),
    "EVENT_DRIVEN": re.compile(
        r"WHEN (?P<trigger>.+), the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "STATE_DRIVEN": re.compile(
        r"WHILE (?P<state>.+), the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "UNWANTED_BEHAVIOR": re.compile(
        r"IF (?P<condition>.+), THEN the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "OPTIONAL_FEATURE": re.compile(
        r"WHERE (?P<feature>.+), the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "COMPLEX": re.compile(
        r"WHILE (?P<state>.+), WHEN (?P<trigger>.+), the "
        r"(?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
}
CONCRETE_SUBJECT = re.compile(r"[A-Za-z][A-Za-z0-9 _./'()-]*")
NON_CONCRETE_SUBJECTS = {
    "it",
    "something",
    "thing",
    "system subject",
    "placeholder",
    "unknown",
}
ACCEPTANCE_FORMS = {"GHERKIN", "MEASURABLE"}
GHERKIN_ACCEPTANCE = re.compile(
    r"GIVEN (?P<precondition>.+), WHEN (?P<trigger>.+), THEN (?P<result>.+)\."
)
MEASURABLE_EXPECTED_RESULT = re.compile(
    r"\b(?:allow|allows|cite|cites|contain|contains|confirm|confirms|cover|covers|"
    r"demonstrate|demonstrates|deny|denied|equal|equals|exceed|exceeds|fail|fails|find|finds|"
    r"identify|identifies|link|links|map|maps|match|matches|meet|meets|name|names|"
    r"pass|passes|preserve|preserves|prove|proves|record|records|reject|rejects|"
    r"restore|restores|show|shows|stay|stays|succeed|succeeds)\b|"
    r"(?:<=|>=|==|<|>)",
    re.IGNORECASE,
)
MEASURABLE_BINDING = re.compile(
    r"\b(?:at least|at most|bounded|calculation|configured|configuration|"
    r"every|each|exact|exactly|maximum|minimum|normal and peak|policy|"
    r"percentile|RPO|RTO|threshold|time-bounded|zero|one|all five|bound|"
    r"generated-case bound|pass condition|traceability check|runbook check|"
    r"owner decision|observed measurement|recorded [A-Za-z0-9 -]+ boundary|"
    r"approved (?:[A-Za-z0-9-]+ )?(?:boundary|case|control|environment|limit|"
    r"outcome|requirement|result|target|trigger|workload))\b|"
    r"\b(?:TEST|PROP|EV)-\d{3,}\b|"
    r"`[^`\r\n]+`|"
    r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/\S+|"
    r"\b(?:python|pytest|npm|pnpm|yarn|cargo|go test|dotnet test)\b|"
    r"\d+(?:\.\d+)?\s*(?:%|ms|s|seconds?|minutes?|hours?|requests?/s)?",
    re.IGNORECASE,
)
UNDEFINED_QUALITY_TERM = re.compile(
    r"\b(?:fast|secure|scalable|user[- ]friendly|appropriate)\b", re.IGNORECASE
)
QAS_HEADERS = (
    "QAS ID",
    "Requirement IDs",
    "Source",
    "Stimulus",
    "Environment",
    "Artifact",
    "Response",
    "Response measure",
)
QAS_ID = re.compile(r"QAS-\d{3,}")
STATE_MODEL_TRIGGERS = (
    "LIFECYCLE_RESOURCE",
    "ASYNCHRONOUS_WORK",
    "RETRY_OR_RESUME",
    "APPROVAL_FLOW",
    "MIGRATION_OR_CUTOVER",
    "OTHER_MEANINGFUL_TRANSITION",
)


def authoritative_requirement_ids(text: str) -> set[str]:
    """Return every stable ID in an authoritative requirement table."""

    identifiers: set[str] = set()
    for table in markdown_tables(text):
        if not table or tuple(table[0]) not in {
            NORMATIVE_REQUIREMENT_HEADERS,
            LEGACY_REQUIREMENT_HEADERS,
            LEGACY_NORMATIVE_REQUIREMENT_HEADERS,
        }:
            continue
        expected_cells = len(table[0])
        for row in table[2:]:
            if (
                len(row) == expected_cells
                and STABLE_CONTRACT_ID.fullmatch(row[0]) is not None
            ):
                identifiers.add(row[0])
    return identifiers


def concrete_requirement_subject(value: str) -> bool:
    subject = clean_cell(value)
    return bool(
        CONCRETE_SUBJECT.fullmatch(subject)
        and subject.casefold() not in NON_CONCRETE_SUBJECTS
        and not unresolved(subject)
        and not any(character in subject for character in "<>{}")
    )


def observable_requirement_response(value: str) -> bool:
    response = clean_cell(value)
    return bool(
        not unresolved(response)
        and re.search(r"[A-Za-z]", response)
        and not any(character in response for character in "<>{}")
        and response.casefold()
        not in {"be appropriate", "be fast", "be scalable", "be secure", "work"}
    )


def measurable_acceptance_is_bound(value: str) -> bool:
    words = re.findall(r"[A-Za-z0-9]+", value)
    return bool(
        len(words) >= 6
        and MEASURABLE_EXPECTED_RESULT.search(value)
        and MEASURABLE_BINDING.search(value)
        and UNDEFINED_QUALITY_TERM.search(value) is None
    )


def requirement_method_issues(
    requirement_id: str,
    requirement: str,
    ears_form: str,
    acceptance_criteria: str,
    acceptance_form: str,
) -> list[str]:
    """SAFETY: Return ordered EARS and acceptance issues for one requirement."""

    issues: list[str] = []
    values = {
        "requirement": requirement,
        "EARS form": ears_form,
        "acceptance criteria": acceptance_criteria,
        "acceptance form": acceptance_form,
    }
    for field_name, value in values.items():
        if unresolved(value):
            issues.append(f"{requirement_id}: {field_name} is unresolved")
    if issues:
        return issues
    if ears_form not in EARS_FORMS:
        issues.append(
            f"{requirement_id}: EARS form must be one of "
            + ", ".join(sorted(EARS_FORMS))
        )
        return issues
    shall_count = len(re.findall(r"\bSHALL\b", requirement))
    if shall_count == 0:
        issues.append(f"{requirement_id}: requirement is missing SHALL")
    elif shall_count != 1:
        issues.append(
            f"{requirement_id}: requirement must contain exactly one uppercase SHALL"
        )
    grammar = EARS_PATTERNS[ears_form].fullmatch(requirement)
    if grammar is None:
        issues.append(
            f"{requirement_id}: requirement does not match {ears_form} clause order"
        )
    elif not concrete_requirement_subject(grammar.group("subject")):
        issues.append(
            f"{requirement_id}: requirement subject must be concrete and non-placeholder"
        )
    elif not observable_requirement_response(grammar.group("response")):
        issues.append(
            f"{requirement_id}: requirement response must be concrete and observable"
        )
    vague_requirement = UNDEFINED_QUALITY_TERM.search(requirement)
    if vague_requirement is not None:
        issues.append(
            f"{requirement_id}: requirement contains undefined qualitative term "
            f"{vague_requirement.group(0)!r}"
        )
    if acceptance_form not in ACCEPTANCE_FORMS:
        issues.append(
            f"{requirement_id}: Acceptance form must be GHERKIN or MEASURABLE"
        )
        return issues
    if acceptance_form == "GHERKIN":
        if (
            GHERKIN_ACCEPTANCE.fullmatch(acceptance_criteria) is None
            or len(re.findall(r"\bGIVEN\b", acceptance_criteria)) != 1
            or len(re.findall(r"\bWHEN\b", acceptance_criteria)) != 1
            or len(re.findall(r"\bTHEN\b", acceptance_criteria)) != 1
        ):
            issues.append(
                f"{requirement_id}: GHERKIN acceptance must use GIVEN, one WHEN, "
                "and THEN in canonical order"
            )
    elif not measurable_acceptance_is_bound(acceptance_criteria):
        issues.append(
            f"{requirement_id}: MEASURABLE acceptance requires an observable expected "
            "result plus a bound, policy/configuration check, exact command/API, or "
            "stable TEST/PROP/EV binding"
        )
    return issues


def quality_attribute_scenario_issues(
    text: str, requirement_ids: set[str]
) -> list[str]:
    """SAFETY: Preserve ordered quality-attribute completeness diagnostics."""

    structural = without_fenced_code(text)
    heading = re.search(
        r"^### Quality attribute scenarios\s*$", structural, re.MULTILINE
    )
    if heading is None:
        return ["QAS-SECTION: Quality attribute scenarios section is missing"]
    following = re.search(r"^#{1,3}\s+", structural[heading.end() :], re.MULTILINE)
    end = heading.end() + following.start() if following else len(structural)
    section = structural[heading.end() : end]
    tables = [
        table
        for table in markdown_tables(section)
        if table and tuple(table[0]) == QAS_HEADERS
    ]
    if not tables:
        non_applicable = re.search(
            r"^NOT_APPLICABLE — (?P<reason>.+)$", section, re.MULTILINE
        )
        if non_applicable is None or unresolved(non_applicable.group("reason")):
            return [
                "QAS-SECTION: require one complete QAS table or "
                "NOT_APPLICABLE — <concrete reason>"
            ]
        return []
    if len(tables) != 1:
        return [
            "QAS-SECTION: exactly one Quality attribute scenarios table is required"
        ]
    issues: list[str] = []
    seen: set[str] = set()
    for row in tables[0][2:]:
        row_id = clean_cell(row[0]) if row else "QAS-UNKNOWN"
        if len(row) != len(QAS_HEADERS):
            issues.append(
                f"{row_id}: QAS row must have exactly {len(QAS_HEADERS)} fields"
            )
            continue
        if QAS_ID.fullmatch(row_id) is None:
            issues.append(f"{row_id}: QAS ID must use QAS-nnn")
            continue
        if row_id in seen:
            issues.append(f"{row_id}: QAS ID is duplicated")
        seen.add(row_id)
        for field_name, value in zip(QAS_HEADERS[1:], row[1:]):
            if unresolved(value):
                issues.append(f"{row_id}: {field_name} is unresolved")
        try:
            basis = parse_exact_id_list(row[1], STABLE_CONTRACT_ID, "Requirement IDs")
        except ValueError as exc:
            issues.append(f"{row_id}: {exc}")
        else:
            unknown = sorted(set(basis) - requirement_ids)
            if unknown:
                issues.append(
                    f"{row_id}: Requirement IDs reference unknown requirements: "
                    + ", ".join(unknown)
                )
        if not unresolved(row[7]) and not measurable_acceptance_is_bound(row[7]):
            issues.append(
                f"{row_id}: Response measure requires an explicit observable bound"
            )
    return issues


def gate_a_method_contract_issues(
    text: str, *, grandfather_approved_v1: bool = False
) -> list[tuple[str, str]]:
    """SAFETY: Return ordered Gate A method diagnostics without mutation."""

    issues: list[tuple[str, str]] = []
    found = False
    legacy_rows: list[str] = []
    legacy_header_shapes: set[tuple[str, ...]] = set()
    modern_tables = 0
    for table in markdown_tables(text):
        if not table:
            continue
        headers = tuple(table[0])
        if headers in {
            LEGACY_NORMATIVE_REQUIREMENT_HEADERS,
            LEGACY_REQUIREMENT_HEADERS,
        }:
            found = True
            legacy_header_shapes.add(headers)
            legacy_rows.extend(
                clean_cell(row[0]) if row else "REQ-UNKNOWN" for row in table[2:]
            )
            continue
        if headers != NORMATIVE_REQUIREMENT_HEADERS:
            continue
        found = True
        modern_tables += 1
        for row in table[2:]:
            row_id = clean_cell(row[0]) if row else "REQ-UNKNOWN"
            if len(row) != len(NORMATIVE_REQUIREMENT_HEADERS):
                issues.append(
                    (
                        "REQUIREMENT_METHOD_CONTRACT",
                        f"{row_id}: normative requirement row must have exactly six fields",
                    )
                )
                continue
            acceptance_id = clean_cell(row[3])
            expected_acceptance_id = f"AC-{row_id}"
            if (
                ACCEPTANCE_ID.fullmatch(acceptance_id) is None
                or acceptance_id != expected_acceptance_id
            ):
                issues.append(
                    (
                        "REQUIREMENT_METHOD_CONTRACT",
                        f"{row_id}: Acceptance ID must be exactly {expected_acceptance_id}",
                    )
                )
            issues.extend(
                ("REQUIREMENT_METHOD_CONTRACT", issue)
                for issue in requirement_method_issues(
                    row[0], row[1], row[2], row[4], row[5]
                )
            )
    if not found:
        return [
            (
                "REQUIREMENT_METHOD_CONTRACT",
                "REQ-SECTION: no authoritative normative requirement table was found",
            )
        ]
    legacy_is_grandfathered = bool(
        grandfather_approved_v1
        and legacy_rows
        and modern_tables == 0
        and len(legacy_header_shapes) == 1
    )
    if legacy_rows and not legacy_is_grandfathered:
        issues.extend(
            (
                "REQUIREMENT_METHOD_MIGRATION_REQUIRED",
                f"{row_id}: migrate the complete normative table to the Fastlane "
                "EARS Contract before Gate A can become ready",
            )
            for row_id in legacy_rows
        )
    if legacy_is_grandfathered:
        return issues
    requirement_ids = authoritative_requirement_ids(text)
    issues.extend(
        ("QAS_CONTRACT", issue)
        for issue in quality_attribute_scenario_issues(text, requirement_ids)
    )
    return issues


def _schema_13_requirement_rows(
    text: str,
) -> tuple[list[tuple[str, ...]], dict[str, str], list[str]]:
    rows: list[tuple[str, ...]] = []
    acceptance_by_requirement: dict[str, str] = {}
    legacy_ids: list[str] = []
    for table in markdown_tables(text):
        if not table:
            continue
        headers = tuple(table[0])
        if headers in {
            LEGACY_NORMATIVE_REQUIREMENT_HEADERS,
            LEGACY_REQUIREMENT_HEADERS,
        }:
            legacy_ids.extend(
                clean_cell(row[0]) if row else "REQ-UNKNOWN" for row in table[2:]
            )
            continue
        if headers != NORMATIVE_REQUIREMENT_HEADERS:
            continue
        for row in table[2:]:
            if len(row) != len(NORMATIVE_REQUIREMENT_HEADERS):
                continue
            normalized = tuple(clean_cell(cell) for cell in row)
            rows.append(normalized)
            acceptance_by_requirement[normalized[0]] = normalized[3]
    return rows, acceptance_by_requirement, legacy_ids


def _contract_table_or_issue(
    text: str,
    heading: str,
    headers: tuple[str, ...],
    issues: list[Any],
    missing_records: list[str],
    code: str | None = None,
) -> ContractTable | None:
    try:
        table = contract_table_after_heading(text, heading, headers)
    except ValueError as exc:
        table, message = None, f"{heading}: {exc}"
    else:
        message = f"Missing {heading}" if table is None else None
    if table is None:
        issues.append((code, message) if code else message)
        missing_records.append(heading)
    return table


def _canonical_id_list(
    value: str, pattern: re.Pattern[str], field_name: str
) -> list[str]:
    identifiers = parse_exact_id_list(value, pattern, field_name)
    if clean_cell(value) != ", ".join(identifiers):
        raise ValueError(f"{field_name} must use comma-space-separated IDs")
    return identifiers


def _contract_ids(value: str, pattern: re.Pattern[str], field_name: str) -> list[str]:
    return _canonical_id_list(clean_cell(value), pattern, field_name)


def _rich_trigger_list(value: str, journey_id: str) -> list[str]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return []
    if unresolved(cleaned):
        raise ValueError(f"{journey_id}: Rich-use-case triggers is unresolved")
    triggers = cleaned.split(", ")
    if cleaned != ", ".join(triggers):
        raise ValueError(
            f"{journey_id}: Rich-use-case triggers must use comma-space separation"
        )
    unknown = sorted(set(triggers) - RICH_USE_CASE_TRIGGERS)
    if unknown:
        raise ValueError(
            f"{journey_id}: unknown Rich-use-case triggers: " + ", ".join(unknown)
        )
    if len(triggers) != len(set(triggers)):
        raise ValueError(f"{journey_id}: Rich-use-case triggers contains duplicates")
    return triggers


def _state_trigger_map(value: str, subject_id: str) -> dict[str, tuple[str, ...]]:
    cleaned = clean_cell(value)
    segments = cleaned.split("; ")
    if unresolved(cleaned) or cleaned != "; ".join(segments):
        raise ValueError(
            f"{subject_id}: State trigger basis must use canonical '; ' segments"
        )
    result: dict[str, tuple[str, ...]] = {}
    for segment in segments:
        parts = segment.split(": ", 1)
        if len(parts) != 2 or parts[0] not in STATE_MODEL_TRIGGERS:
            raise ValueError(f"{subject_id}: invalid State trigger category")
        category, basis_value = parts
        if category in result:
            raise ValueError(
                f"{subject_id}: duplicate State trigger category {category}"
            )
        result[category] = tuple(
            _contract_ids(
                basis_value,
                STABLE_CONTRACT_ID,
                f"{subject_id} {category} basis IDs",
            )
        )
    if list(result) != [item for item in STATE_MODEL_TRIGGERS if item in result]:
        raise ValueError(
            f"{subject_id}: State trigger categories are not in canonical order"
        )
    return result


def _current_contract_schema(
    text: str,
    required: bool,
    grandfather_current_gate_a: bool,
) -> tuple[
    dict[str, str],
    list[tuple[str, ...]],
    dict[str, str],
    list[str],
    bool,
    RequirementsContract | None,
    list[tuple[str, str]],
]:
    """COMPATIBILITY: Select current, grandfathered, or migration semantics.

    Schema recognition, early-return status, and diagnostic order remain one
    fail-closed decision because existing approved Gate A records depend on it.
    """

    issues: list[tuple[str, str]] = []
    try:
        document = table_after_heading(text, "## Document status")
    except ValueError as exc:
        document = {}
        if required:
            issues.append(("PROJECT_CONTRACT_MIGRATION_REQUIRED", str(exc)))
    project_schema = clean_cell(document.get("Project contract schema", ""))
    requirement_rows, acceptance_by_requirement, legacy_ids = (
        _schema_13_requirement_rows(text)
    )
    observed_headers = {tuple(table[0]) for table in markdown_tables(text) if table}
    current_header_map = {
        NORMATIVE_REQUIREMENT_HEADERS: "Six-column normative requirements",
        ACTOR_HEADERS: ACTOR_HEADING,
        JOURNEY_HEADERS: JOURNEY_HEADING,
        RICH_USE_CASE_APPLICABILITY_HEADERS: RICH_USE_CASE_APPLICABILITY_HEADING,
        RICH_USE_CASE_HEADERS: RICH_USE_CASE_HEADING,
        BUSINESS_RULE_HEADERS: BUSINESS_RULE_HEADING,
        REQUIREMENT_COVERAGE_HEADERS: REQUIREMENT_COVERAGE_HEADING,
        REQUIREMENTS_CHANGE_LINEAGE_HEADERS: REQUIREMENTS_CHANGE_LINEAGE_HEADING,
        ASSUMPTION_LIFECYCLE_HEADERS: ASSUMPTION_LIFECYCLE_HEADING,
    }
    current_present_headers = observed_headers & set(current_header_map)
    for heading, headers in (
        (ACTOR_HEADING, ACTOR_HEADERS),
        (JOURNEY_HEADING, JOURNEY_HEADERS),
        (RICH_USE_CASE_APPLICABILITY_HEADING, RICH_USE_CASE_APPLICABILITY_HEADERS),
        (RICH_USE_CASE_HEADING, RICH_USE_CASE_HEADERS),
        (BUSINESS_RULE_HEADING, BUSINESS_RULE_HEADERS),
        (REQUIREMENT_COVERAGE_HEADING, REQUIREMENT_COVERAGE_HEADERS),
        (REQUIREMENTS_CHANGE_LINEAGE_HEADING, REQUIREMENTS_CHANGE_LINEAGE_HEADERS),
        (ASSUMPTION_LIFECYCLE_HEADING, ASSUMPTION_LIFECYCLE_HEADERS),
    ):
        try:
            if contract_table_after_heading(text, heading, headers) is not None:
                current_present_headers.add(headers)
        except ValueError:
            pass
    grandfather_schema_13 = bool(project_schema == "1.3" and grandfather_current_gate_a)
    if project_schema == PROJECT_CONTRACT_SCHEMA or grandfather_schema_13:
        return (
            document,
            requirement_rows,
            acceptance_by_requirement,
            legacy_ids,
            grandfather_schema_13,
            None,
            issues,
        )

    legacy_headers = observed_headers & {
        LEGACY_NORMATIVE_REQUIREMENT_HEADERS,
        LEGACY_REQUIREMENT_HEADERS,
    }
    real_legacy_ids = [
        identifier
        for identifier in legacy_ids
        if STABLE_CONTRACT_ID.fullmatch(identifier)
    ]
    exact_legacy_shape = bool(
        not project_schema
        and real_legacy_ids
        and len(real_legacy_ids) == len(legacy_ids)
        and len(real_legacy_ids) == len(set(real_legacy_ids))
        and len(legacy_headers) == 1
        and not current_present_headers
    )
    if grandfather_current_gate_a and exact_legacy_shape:
        approved_ids = tuple(sorted(real_legacy_ids))
        legacy_rows = [
            tuple(clean_cell(cell) for cell in row)
            for table in markdown_tables(text)
            if table
            and tuple(table[0])
            in {LEGACY_NORMATIVE_REQUIREMENT_HEADERS, LEGACY_REQUIREMENT_HEADERS}
            for row in table[2:]
        ]
        canonical_bytes = (
            b"PROJECT_CONTRACT_SCHEMA: 1.2\n"
            + json.dumps(
                (
                    clean_cell(document.get("Current requirements revision", "")),
                    legacy_rows,
                ),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        contract = RequirementsContract(
            schema_version="1.2",
            status="GRANDFATHERED",
            requirement_ids=approved_ids,
            acceptance_ids=tuple(f"AC-{item}" for item in approved_ids),
            canonical_sha256="sha256:" + hashlib.sha256(canonical_bytes).hexdigest(),
            canonical_bytes=canonical_bytes,
            grandfathered_approved_gate_a=True,
        )
        return (
            document,
            requirement_rows,
            acceptance_by_requirement,
            legacy_ids,
            False,
            contract,
            [],
        )
    if not required:
        return (
            document,
            requirement_rows,
            acceptance_by_requirement,
            legacy_ids,
            False,
            RequirementsContract(status="UNINITIALIZED"),
            [],
        )
    migration_targets = ["Project contract schema 1.4"]
    migration_targets.extend(
        label
        for headers, label in current_header_map.items()
        if headers not in current_present_headers
    )
    contract = RequirementsContract(
        status="MIGRATION_REQUIRED", missing_records=tuple(migration_targets)
    )
    migration_issue = (
        "PROJECT_CONTRACT_MIGRATION_REQUIRED",
        "Project contract schema 1.4 is required before Gate A readiness; "
        "migrate only the listed generated records without inventing owner facts: "
        + ", ".join(migration_targets),
    )
    return (
        document,
        requirement_rows,
        acceptance_by_requirement,
        legacy_ids,
        False,
        contract,
        [migration_issue],
    )


def _requirements_presentation_labels(
    actors: ContractTable | None,
    journeys: ContractTable | None,
    use_cases: ContractTable | None,
) -> tuple[tuple[str, str], ...]:
    """Project canonical human names without entering requirements digests."""

    labels = [
        *((row[0], row[1]) for row in (actors.rows if actors else ())),
        *((row[0], row[2]) for row in (journeys.rows if journeys else ())),
        *((row[0], row[5]) for row in (use_cases.rows if use_cases else ())),
    ]
    return tuple((identifier, clean_cell(label)) for identifier, label in labels)


def derive_requirements_contract(
    text: str,
    effective_risk: str | None,
    intake_contract: IntakeFoundationContract | None = None,
    *,
    required: bool,
    grandfather_current_gate_a: bool,
) -> tuple[RequirementsContract, list[tuple[str, str]]]:
    """SAFETY: Derive the owner-grounded schema 1.4 requirements projection.

    The remaining ordered validation pipeline stays cohesive in this extraction
    because diagnostic ordering is a public compatibility contract. Subsequent
    internal splits must retain the frozen parity oracle.
    """

    (
        document,
        requirement_rows,
        acceptance_by_requirement,
        legacy_ids,
        grandfather_schema_13,
        early_contract,
        issues,
    ) = _current_contract_schema(text, required, grandfather_current_gate_a)
    if early_contract is not None:
        return early_contract, issues

    def add(code: str, message: str) -> None:
        issues.append((code, message))

    missing_records: list[str] = []
    requirement_row_by_id = {row[0]: row for row in requirement_rows}
    if intake_contract is None:
        repository_mode = clean_cell(document.get("Project mode", "")).lower()
        intake_contract, _intake_issues = derive_intake_foundation_contract(
            text,
            repository_mode if repository_mode in PROJECT_MODES else None,
            grandfather_current_gate_a=grandfather_current_gate_a,
        )
    confirmed_intake_ids = set(intake_contract.basis_ids)
    if required and intake_contract.status != "READY_FOR_REQUIREMENTS":
        add(
            "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
            "Schema 1.4 actor and success-measure bases require a complete confirmed intake foundation",
        )

    table_specs = (
        (ACTOR_HEADING, ACTOR_HEADERS, "ACTOR_CONTRACT_INVALID"),
        (JOURNEY_HEADING, JOURNEY_HEADERS, "JOURNEY_CONTRACT_INVALID"),
        (
            RICH_USE_CASE_APPLICABILITY_HEADING,
            RICH_USE_CASE_APPLICABILITY_HEADERS,
            "RICH_USE_CASE_INVALID",
        ),
        (RICH_USE_CASE_HEADING, RICH_USE_CASE_HEADERS, "RICH_USE_CASE_INVALID"),
        (BUSINESS_RULE_HEADING, BUSINESS_RULE_HEADERS, "BUSINESS_RULE_INVALID"),
        (
            REQUIREMENT_COVERAGE_HEADING,
            REQUIREMENT_COVERAGE_HEADERS,
            "REQUIREMENT_COVERAGE_INVALID",
        ),
    )
    tables = tuple(
        _contract_table_or_issue(text, heading, headers, issues, missing_records, code)
        for heading, headers, code in table_specs
    )
    actors, journeys, applicability, use_cases, business_rules, coverage = tables
    lineage_table: ContractTable | None = None
    assumption_table: ContractTable | None = None
    if not grandfather_schema_13:
        lineage_table = _contract_table_or_issue(
            text,
            REQUIREMENTS_CHANGE_LINEAGE_HEADING,
            REQUIREMENTS_CHANGE_LINEAGE_HEADERS,
            issues,
            missing_records,
            "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
        )
        assumption_table = _contract_table_or_issue(
            text,
            ASSUMPTION_LIFECYCLE_HEADING,
            ASSUMPTION_LIFECYCLE_HEADERS,
            issues,
            missing_records,
            "ASSUMPTION_LIFECYCLE_INVALID",
        )
    contract_tables = (*tables, lineage_table, assumption_table)
    if grandfather_schema_13:
        contract_tables = tables
    if legacy_ids:
        add(
            "PROJECT_CONTRACT_MIGRATION_REQUIRED",
            "Migrate legacy normative rows to schema 1.4: " + ", ".join(legacy_ids),
        )
        missing_records.extend(legacy_ids)
    requirement_ids = [row[0] for row in requirement_rows]
    duplicate_requirements = sorted(
        identifier
        for identifier in set(requirement_ids)
        if requirement_ids.count(identifier) > 1
    )
    if duplicate_requirements:
        add(
            "REQUIREMENT_COVERAGE_INVALID",
            "Duplicate authoritative requirement IDs: "
            + ", ".join(duplicate_requirements),
        )
    if not requirement_rows:
        add(
            "REQUIREMENT_COVERAGE_INVALID",
            "Schema 1.4 requires at least one normative requirement",
        )
    acceptance_ids: list[str] = []
    for row in requirement_rows:
        requirement_id = row[0]
        acceptance_id = row[3]
        if STABLE_CONTRACT_ID.fullmatch(requirement_id) is None:
            add(
                "REQUIREMENT_COVERAGE_INVALID",
                f"Invalid requirement ID {requirement_id!r}",
            )
        expected_acceptance = f"AC-{requirement_id}"
        if (
            ACCEPTANCE_ID.fullmatch(acceptance_id) is None
            or acceptance_id != expected_acceptance
        ):
            add(
                "REQUIREMENT_COVERAGE_INVALID",
                f"{requirement_id}: Acceptance ID must be exactly {expected_acceptance}",
            )
        acceptance_ids.append(acceptance_id)
    duplicate_acceptance = sorted(
        identifier
        for identifier in set(acceptance_ids)
        if acceptance_ids.count(identifier) > 1
    )
    if duplicate_acceptance:
        add(
            "REQUIREMENT_COVERAGE_INVALID",
            "Duplicate acceptance IDs: " + ", ".join(duplicate_acceptance),
        )
    requirement_set = set(requirement_ids)
    change_lineage: RequirementsChangeLineage | None = None
    assumptions: list[AssumptionLifecycleRecord] = []
    if lineage_table is not None:
        if len(lineage_table.rows) != 1:
            add(
                "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                "Requirements change lineage requires exactly one current-revision row",
            )
        else:
            raw = lineage_table.rows[0]
            (
                current,
                prior,
                trigger,
                added,
                changed,
                removed,
                preserved,
                stale,
                revalidate,
            ) = raw
            parsed_lists: dict[str, list[str]] = {}
            for label, value in (
                ("Added IDs", added),
                ("Changed IDs", changed),
                ("Removed IDs", removed),
                ("Preserved IDs", preserved),
            ):
                try:
                    parsed_lists[label] = parse_exact_id_list(
                        value, STABLE_CONTRACT_ID, label
                    )
                except ValueError as exc:
                    add("REQUIREMENTS_CHANGE_LINEAGE_INVALID", str(exc))
                    parsed_lists[label] = []
            if revalidate == "FULL_REVALIDATION":
                revalidation_ids: list[str] = []
            else:
                try:
                    revalidation_ids = parse_exact_id_list(
                        revalidate, STABLE_CONTRACT_ID, "Required revalidation"
                    )
                except ValueError as exc:
                    add("REQUIREMENTS_CHANGE_LINEAGE_INVALID", str(exc))
                    revalidation_ids = []
            expected_revision = clean_cell(
                document.get("Current requirements revision", "")
            )
            if (
                current != expected_revision
                or REQUIREMENTS_REVISION_ID.fullmatch(current) is None
            ):
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Current lineage revision must match Document status",
                )
            if prior != "NONE" and REQUIREMENTS_REVISION_ID.fullmatch(prior) is None:
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Prior revision must be REQ-nnnn or NONE",
                )
            if prior == current:
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Prior and current requirements revisions must differ",
                )
            if not explicit_value(trigger, allow_none=False) or not explicit_value(
                stale, allow_none=True
            ):
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Lineage trigger and stale reason must be explicit",
                )
            classified = [
                identifier
                for label in (
                    "Added IDs",
                    "Changed IDs",
                    "Removed IDs",
                    "Preserved IDs",
                )
                for identifier in parsed_lists[label]
            ]
            duplicates = sorted(
                identifier
                for identifier in set(classified)
                if classified.count(identifier) > 1
            )
            if duplicates:
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Lineage IDs appear in multiple dispositions: "
                    + ", ".join(duplicates),
                )
            current_declared = (
                set(parsed_lists["Added IDs"])
                | set(parsed_lists["Changed IDs"])
                | set(parsed_lists["Preserved IDs"])
            )
            if current_declared != requirement_set:
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Added, changed, and preserved IDs must enumerate the current requirement set",
                )
            change_lineage = RequirementsChangeLineage(
                current_revision=current,
                prior_revision=prior,
                trigger=trigger,
                added_ids=tuple(parsed_lists["Added IDs"]),
                changed_ids=tuple(parsed_lists["Changed IDs"]),
                removed_ids=tuple(parsed_lists["Removed IDs"]),
                preserved_ids=tuple(parsed_lists["Preserved IDs"]),
                stale_reason=stale,
                required_revalidation=tuple(revalidation_ids),
            )
    if assumption_table is not None:
        seen_assumptions: set[str] = set()
        for (
            assumption_id,
            statement,
            status,
            basis_value,
            validation,
        ) in assumption_table.rows:
            if (
                ASSUMPTION_ID.fullmatch(assumption_id) is None
                or assumption_id in seen_assumptions
            ):
                add(
                    "ASSUMPTION_LIFECYCLE_INVALID",
                    f"Invalid or duplicate assumption ID {assumption_id!r}",
                )
            seen_assumptions.add(assumption_id)
            if status not in ASSUMPTION_STATUSES:
                add(
                    "ASSUMPTION_LIFECYCLE_INVALID",
                    f"{assumption_id}: invalid assumption status {status!r}",
                )
            if not explicit_value(statement, allow_none=False) or not explicit_value(
                validation, allow_none=False
            ):
                add(
                    "ASSUMPTION_LIFECYCLE_INVALID",
                    f"{assumption_id}: statement and validation/successor must be explicit",
                )
            try:
                basis_ids = parse_exact_id_list(
                    basis_value, STABLE_CONTRACT_ID, f"{assumption_id} Basis IDs"
                )
            except ValueError as exc:
                add("ASSUMPTION_LIFECYCLE_INVALID", str(exc))
                basis_ids = []
            assumptions.append(
                AssumptionLifecycleRecord(
                    assumption_id=assumption_id,
                    assumption=statement,
                    status=status,
                    basis_ids=tuple(basis_ids),
                    validation_or_successor=validation,
                )
            )

    if not required and (
        any(table is None for table in contract_tables)
        or any(
            unresolved(cell)
            for table in contract_tables
            if table
            for row in table.rows
            for cell in row
        )
        or any(unresolved(cell) for row in requirement_rows for cell in row)
    ):
        return RequirementsContract(status="UNINITIALIZED"), []

    actor_ids: list[str] = []
    if actors is not None:
        if not actors.rows:
            add("ACTOR_CONTRACT_INVALID", "Actor contract has no rows")
        for actor_id, name, kind, outcome, boundary, basis_value in actors.rows:
            if ACTOR_ID.fullmatch(actor_id) is None:
                add("ACTOR_CONTRACT_INVALID", f"Invalid actor ID {actor_id!r}")
                continue
            if actor_id in actor_ids:
                add("ACTOR_CONTRACT_INVALID", f"Duplicate actor ID {actor_id}")
            actor_ids.append(actor_id)
            if kind not in ACTOR_KINDS:
                add(
                    "ACTOR_CONTRACT_INVALID", f"{actor_id}: invalid actor kind {kind!r}"
                )
            for label, value in (
                ("Actor or external system", name),
                ("Desired outcome or responsibility", outcome),
                ("Permission/data boundary", boundary),
            ):
                if not explicit_value(value, allow_none=False):
                    add(
                        "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
                        f"{actor_id}: {label} requires an owner-grounded value",
                    )
            try:
                basis_ids = _contract_ids(
                    basis_value,
                    re.compile(r"INTAKE-\d{4}"),
                    f"{actor_id} Intake basis IDs",
                )
                unknown = sorted(set(basis_ids) - confirmed_intake_ids)
                if unknown:
                    add(
                        "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
                        f"{actor_id}: intake basis IDs are not currently confirmed: "
                        + ", ".join(unknown),
                    )
            except ValueError as exc:
                add("ACTOR_CONTRACT_INVALID", str(exc))

    journey_ids: list[str] = []
    journey_requirements: dict[str, set[str]] = {}
    journey_actors: dict[str, set[str]] = {}
    declared_rich_triggers: set[str] = set()
    triggered_journey_ids: set[str] = set()
    if journeys is not None:
        if not journeys.rows:
            add("JOURNEY_CONTRACT_INVALID", "Journey register has no rows")
        for row in journeys.rows:
            (
                journey_id,
                actor_value,
                goal,
                trigger,
                success,
                failure,
                requirement_value,
                trigger_value,
            ) = row
            if JOURNEY_ID.fullmatch(journey_id) is None:
                add("JOURNEY_CONTRACT_INVALID", f"Invalid journey ID {journey_id!r}")
                continue
            if journey_id in journey_ids:
                add("JOURNEY_CONTRACT_INVALID", f"Duplicate journey ID {journey_id}")
            journey_ids.append(journey_id)
            for label, value in (
                ("Goal", goal),
                ("Trigger", trigger),
                ("Main success outcome", success),
                ("Alternate/failure behavior", failure),
            ):
                if not explicit_value(value, allow_none=False):
                    add(
                        "JOURNEY_CONTRACT_INVALID",
                        f"{journey_id}: {label} requires a concrete generated value grounded in approved requirements",
                    )
            try:
                refs = _contract_ids(actor_value, ACTOR_ID, f"{journey_id} Actor IDs")
                journey_actors[journey_id] = set(refs)
                unknown = sorted(set(refs) - set(actor_ids))
                if unknown:
                    add(
                        "JOURNEY_CONTRACT_INVALID",
                        f"{journey_id}: unknown actor IDs: " + ", ".join(unknown),
                    )
            except ValueError as exc:
                add("JOURNEY_CONTRACT_INVALID", str(exc))
            try:
                refs = _contract_ids(
                    requirement_value,
                    STABLE_CONTRACT_ID,
                    f"{journey_id} Requirement IDs",
                )
                journey_requirements[journey_id] = set(refs)
                unknown = sorted(set(refs) - requirement_set)
                if unknown:
                    add(
                        "JOURNEY_CONTRACT_INVALID",
                        f"{journey_id}: unknown requirement IDs: " + ", ".join(unknown),
                    )
            except ValueError as exc:
                add("JOURNEY_CONTRACT_INVALID", str(exc))
            try:
                journey_triggers = _rich_trigger_list(trigger_value, journey_id)
                declared_rich_triggers.update(journey_triggers)
                if journey_triggers:
                    triggered_journey_ids.add(journey_id)
            except ValueError as exc:
                add("JOURNEY_CONTRACT_INVALID", str(exc))

    high_or_critical = effective_risk in {"high", "critical"}
    required_rich_journey_ids = (
        set(journey_ids) if high_or_critical else set(triggered_journey_ids)
    )
    policy_requires_rich = bool(required_rich_journey_ids)
    rich_required = policy_requires_rich
    required_use_case_ids: list[str] = []
    if applicability is not None:
        if len(applicability.rows) != 1:
            add(
                "RICH_USE_CASE_INVALID",
                "Rich-use-case applicability requires exactly one row",
            )
        else:
            status, trigger_basis, use_case_value = applicability.rows[0]
            if status == "REQUIRED":
                rich_required = True
                if not explicit_value(trigger_basis, allow_none=False):
                    add(
                        "RICH_USE_CASE_INVALID",
                        "Rich-use-case trigger basis is unresolved",
                    )
                try:
                    required_use_case_ids = _contract_ids(
                        use_case_value, USE_CASE_ID, "Rich use-case IDs"
                    )
                except ValueError as exc:
                    add("RICH_USE_CASE_INVALID", str(exc))
            elif status == "NOT_APPLICABLE":
                if policy_requires_rich:
                    add(
                        "RICH_USE_CASE_REQUIRED",
                        "High/critical risk or a declared material journey trigger requires rich use cases",
                    )
                if not trigger_basis.startswith("NOT_APPLICABLE") or unresolved(
                    trigger_basis
                ):
                    add(
                        "RICH_USE_CASE_INVALID",
                        "NOT_APPLICABLE requires a concrete trigger-basis reason",
                    )
                if use_case_value != "NONE":
                    add(
                        "RICH_USE_CASE_INVALID",
                        "Non-applicable rich use cases require Use-case IDs NONE",
                    )
            else:
                add(
                    "RICH_USE_CASE_INVALID",
                    "Applicability must be REQUIRED or NOT_APPLICABLE",
                )

    if not rich_required:
        if use_cases is not None and use_cases.rows:
            add(
                "RICH_USE_CASE_INVALID",
                "NOT_APPLICABLE rich use cases require an empty rich-use-case table",
            )
        if business_rules is not None and business_rules.rows:
            add(
                "BUSINESS_RULE_INVALID",
                "NOT_APPLICABLE rich use cases require an empty business-rule table",
            )

    use_case_ids: list[str] = []
    use_case_journey_ids: set[str] = set()
    referenced_business_rules: set[str] = set()
    if use_cases is not None and rich_required:
        for row in use_cases.rows:
            (
                use_case_id,
                journey_id,
                primary_actor,
                interests,
                preconditions,
                success,
                minimum_failure,
                rules_value,
                requirements_value,
            ) = row
            if USE_CASE_ID.fullmatch(use_case_id) is None:
                add("RICH_USE_CASE_INVALID", f"Invalid use-case ID {use_case_id!r}")
                continue
            if use_case_id in use_case_ids:
                add("RICH_USE_CASE_INVALID", f"Duplicate use-case ID {use_case_id}")
            use_case_ids.append(use_case_id)
            if journey_id not in journey_ids:
                add(
                    "RICH_USE_CASE_INVALID",
                    f"{use_case_id}: unknown journey {journey_id}",
                )
            else:
                use_case_journey_ids.add(journey_id)
            if primary_actor not in journey_actors.get(journey_id, set()):
                add(
                    "RICH_USE_CASE_INVALID",
                    f"{use_case_id}: primary actor is not part of {journey_id}",
                )
            for label, value in (
                ("Stakeholder interests", interests),
                ("Preconditions", preconditions),
                ("Success guarantee", success),
                ("Minimum failure guarantee", minimum_failure),
            ):
                if not explicit_value(value, allow_none=False):
                    add(
                        "RICH_USE_CASE_INVALID",
                        f"{use_case_id}: {label} must be concrete",
                    )
            try:
                referenced_business_rules.update(
                    _contract_ids(
                        rules_value,
                        BUSINESS_RULE_ID,
                        f"{use_case_id} Business rule IDs",
                    )
                )
            except ValueError as exc:
                add("RICH_USE_CASE_INVALID", str(exc))
            try:
                refs = set(
                    _contract_ids(
                        requirements_value,
                        STABLE_CONTRACT_ID,
                        f"{use_case_id} Requirement IDs",
                    )
                )
                unknown = sorted(refs - requirement_set)
                if unknown:
                    add(
                        "RICH_USE_CASE_INVALID",
                        f"{use_case_id}: unknown requirement IDs: "
                        + ", ".join(unknown),
                    )
                journey_basis = journey_requirements.get(journey_id, set())
                outside_journey = sorted(refs - journey_basis)
                if outside_journey:
                    add(
                        "RICH_USE_CASE_INVALID",
                        f"{use_case_id}: requirement IDs are not part of {journey_id}: "
                        + ", ".join(outside_journey),
                    )
            except ValueError as exc:
                add("RICH_USE_CASE_INVALID", str(exc))
        if use_case_ids != required_use_case_ids:
            add(
                "RICH_USE_CASE_INVALID",
                "Rich use-case rows must exactly match the applicability record",
            )

    missing_rich_journey_ids = sorted(required_rich_journey_ids - use_case_journey_ids)
    if missing_rich_journey_ids:
        scope = (
            "every journey at high/critical risk"
            if high_or_critical
            else "every journey declaring a material rich-use-case trigger"
        )
        add(
            "RICH_USE_CASE_REQUIRED",
            f"Rich use cases must cover {scope}; missing="
            + ",".join(missing_rich_journey_ids),
        )

    business_rule_ids: list[str] = []
    if business_rules is not None and rich_required:
        for (
            rule_id,
            rule,
            basis_value,
            journey_use_case_value,
            validation_id,
        ) in business_rules.rows:
            if BUSINESS_RULE_ID.fullmatch(rule_id) is None:
                add("BUSINESS_RULE_INVALID", f"Invalid business-rule ID {rule_id!r}")
                continue
            if rule_id in business_rule_ids:
                add("BUSINESS_RULE_INVALID", f"Duplicate business-rule ID {rule_id}")
            business_rule_ids.append(rule_id)
            if not explicit_value(rule, allow_none=False):
                add("BUSINESS_RULE_INVALID", f"{rule_id}: Rule must be concrete")
            try:
                basis_refs = set(
                    _contract_ids(
                        basis_value, STABLE_CONTRACT_ID, f"{rule_id} Basis IDs"
                    )
                )
                refs = set(
                    _contract_ids(
                        journey_use_case_value,
                        STABLE_CONTRACT_ID,
                        f"{rule_id} Journey/use-case IDs",
                    )
                )
                unknown = sorted(refs - set(journey_ids) - set(use_case_ids))
                if unknown:
                    add(
                        "BUSINESS_RULE_INVALID",
                        f"{rule_id}: unknown journey/use-case IDs: "
                        + ", ".join(unknown),
                    )
                allowed_basis = (
                    requirement_set
                    | confirmed_intake_ids
                    | set(journey_ids)
                    | set(use_case_ids)
                )
                unknown_basis = sorted(basis_refs - allowed_basis)
                if unknown_basis:
                    add(
                        "BUSINESS_RULE_INVALID",
                        f"{rule_id}: unknown basis IDs: " + ", ".join(unknown_basis),
                    )
            except ValueError as exc:
                add("BUSINESS_RULE_INVALID", str(exc))
            if validation_id not in set(acceptance_ids):
                add(
                    "BUSINESS_RULE_INVALID",
                    f"{rule_id}: Validation ID must reference a current acceptance ID",
                )
        missing_rules = sorted(referenced_business_rules - set(business_rule_ids))
        extra_rules = sorted(set(business_rule_ids) - referenced_business_rules)
        if missing_rules or extra_rules:
            add(
                "BUSINESS_RULE_INVALID",
                "Business-rule rows must exactly match rich-use-case references; missing="
                + ",".join(missing_rules)
                + "; extra="
                + ",".join(extra_rules),
            )

    covered_requirements: list[str] = []
    covered_actor_ids: set[str] = set()
    covered_journey_ids: set[str] = set()
    if coverage is not None:
        for (
            requirement_id,
            intake_value,
            actor_value,
            journey_value,
            acceptance_value,
            success_measure,
        ) in coverage.rows:
            if requirement_id in covered_requirements:
                add(
                    "REQUIREMENT_COVERAGE_INVALID",
                    f"Duplicate coverage row for {requirement_id}",
                )
            covered_requirements.append(requirement_id)
            if requirement_id not in requirement_set:
                add(
                    "REQUIREMENT_COVERAGE_INVALID",
                    f"Coverage references unknown requirement {requirement_id}",
                )
            try:
                intake_refs = set(
                    _contract_ids(
                        intake_value,
                        re.compile(r"INTAKE-\d{4}"),
                        f"{requirement_id} Intake basis IDs",
                    )
                )
                actor_refs = set(
                    _contract_ids(actor_value, ACTOR_ID, f"{requirement_id} Actor IDs")
                )
                journey_refs = set(
                    _contract_ids(
                        journey_value, JOURNEY_ID, f"{requirement_id} Journey IDs"
                    )
                )
                acceptance_refs = _contract_ids(
                    acceptance_value,
                    STABLE_CONTRACT_ID,
                    f"{requirement_id} Acceptance/test IDs",
                )
                if not intake_refs <= confirmed_intake_ids:
                    add(
                        "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
                        f"{requirement_id}: coverage cites intake basis IDs that are not currently confirmed",
                    )
                if not actor_refs <= set(actor_ids):
                    add(
                        "REQUIREMENT_COVERAGE_INVALID",
                        f"{requirement_id}: unknown actor IDs",
                    )
                if not journey_refs <= set(journey_ids):
                    add(
                        "REQUIREMENT_COVERAGE_INVALID",
                        f"{requirement_id}: unknown journey IDs",
                    )
                expected_acceptance = acceptance_by_requirement.get(requirement_id)
                requirement_row = requirement_row_by_id.get(requirement_id)
                if expected_acceptance is not None and requirement_row is not None:
                    criterion_bindings = list(
                        dict.fromkeys(
                            ACCEPTANCE_TEST_BINDING_ID.findall(requirement_row[4])
                        )
                    )
                    expected_refs = [expected_acceptance, *criterion_bindings]
                else:
                    expected_refs = []
                if acceptance_refs != expected_refs:
                    add(
                        "REQUIREMENT_COVERAGE_INVALID",
                        f"{requirement_id}: Acceptance/test IDs must exactly match "
                        "the canonical acceptance ID followed by test IDs explicitly "
                        "bound in that requirement's acceptance criterion; expected="
                        + ",".join(expected_refs),
                    )
                if requirement_id in requirement_set:
                    covered_actor_ids.update(actor_refs)
                    covered_journey_ids.update(journey_refs)
                if any(
                    requirement_id not in journey_requirements.get(item, set())
                    for item in journey_refs
                ):
                    add(
                        "REQUIREMENT_COVERAGE_INVALID",
                        f"{requirement_id}: cited journey does not include the requirement",
                    )
                journey_actor_union = set().union(
                    *(journey_actors.get(item, set()) for item in journey_refs)
                )
                if not actor_refs <= journey_actor_union:
                    add(
                        "REQUIREMENT_COVERAGE_INVALID",
                        f"{requirement_id}: every coverage actor must participate in a cited journey",
                    )
            except ValueError as exc:
                add("REQUIREMENT_COVERAGE_INVALID", str(exc))
            if (
                success_measure != "INTAKE-0006"
                or "INTAKE-0006" not in confirmed_intake_ids
            ):
                add(
                    "REQUIREMENT_COVERAGE_INVALID",
                    f"{requirement_id}: Approved success measure ID must be INTAKE-0006",
                )
        if covered_requirements != sorted(requirement_set):
            missing = sorted(requirement_set - set(covered_requirements))
            extra = sorted(set(covered_requirements) - requirement_set)
            add(
                "REQUIREMENT_COVERAGE_INVALID",
                "Coverage must enumerate every requirement exactly once in sorted order; missing="
                + ",".join(missing)
                + "; extra="
                + ",".join(extra),
            )
        uncovered_actor_ids = sorted(set(actor_ids) - covered_actor_ids)
        if uncovered_actor_ids:
            add(
                "ACTOR_CONTRACT_INVALID",
                "Every declared actor must participate in first-release requirement coverage; uncovered="
                + ",".join(uncovered_actor_ids),
            )
        uncovered_journey_ids = sorted(set(journey_ids) - covered_journey_ids)
        if uncovered_journey_ids:
            add(
                "JOURNEY_CONTRACT_INVALID",
                "Every declared journey must participate in first-release requirement coverage; uncovered="
                + ",".join(uncovered_journey_ids),
            )

    canonical_bytes: bytes | None = None
    canonical_sha256: str | None = None
    if all(table is not None for table in contract_tables):
        requirement_payload = (
            json.dumps(
                requirement_rows, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            + b"\n"
        )
        canonical_bytes = (
            ("1.3" if grandfather_schema_13 else PROJECT_CONTRACT_SCHEMA).encode(
                "utf-8"
            )
            + b"\n"
            + requirement_payload
            + b"".join(
                table.canonical_bytes for table in contract_tables if table is not None
            )
        )
        canonical_sha256 = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
    return RequirementsContract(
        schema_version="1.3" if grandfather_schema_13 else PROJECT_CONTRACT_SCHEMA,
        status=(
            "GRANDFATHERED"
            if grandfather_schema_13 and not issues
            else "READY"
            if not issues
            else "BLOCKED"
        ),
        actor_ids=tuple(actor_ids),
        journey_ids=tuple(journey_ids),
        acceptance_ids=tuple(
            acceptance_by_requirement.get(item, "") for item in sorted(requirement_set)
        ),
        use_case_ids=tuple(use_case_ids),
        business_rule_ids=tuple(business_rule_ids),
        requirement_ids=tuple(sorted(requirement_set)),
        rich_use_case_triggers=tuple(sorted(declared_rich_triggers)),
        change_lineage=change_lineage,
        assumptions=tuple(assumptions),
        missing_records=tuple(dict.fromkeys(missing_records)),
        canonical_sha256=canonical_sha256,
        grandfathered_approved_gate_a=grandfather_schema_13,
        presentation_labels=_requirements_presentation_labels(
            actors, journeys, use_cases
        ),
        canonical_bytes=canonical_bytes,
    ), issues


__all__ = (
    "ACCEPTANCE_FORMS",
    "ACCEPTANCE_ID",
    "ACTOR_HEADERS",
    "ACTOR_HEADING",
    "ACTOR_ID",
    "ASSUMPTION_ID",
    "ASSUMPTION_LIFECYCLE_HEADERS",
    "ASSUMPTION_LIFECYCLE_HEADING",
    "ASSUMPTION_STATUSES",
    "BUSINESS_RULE_HEADERS",
    "BUSINESS_RULE_HEADING",
    "BUSINESS_RULE_ID",
    "EARS_FORMS",
    "EARS_PATTERNS",
    "JOURNEY_HEADERS",
    "JOURNEY_HEADING",
    "JOURNEY_ID",
    "LEGACY_NORMATIVE_REQUIREMENT_HEADERS",
    "LEGACY_REQUIREMENT_HEADERS",
    "NORMATIVE_REQUIREMENT_HEADERS",
    "PROJECT_CONTRACT_SCHEMA",
    "QAS_HEADERS",
    "REQUIREMENT_COVERAGE_HEADERS",
    "REQUIREMENT_COVERAGE_HEADING",
    "REQUIREMENTS_CHANGE_LINEAGE_HEADERS",
    "REQUIREMENTS_CHANGE_LINEAGE_HEADING",
    "RICH_USE_CASE_APPLICABILITY_HEADERS",
    "RICH_USE_CASE_APPLICABILITY_HEADING",
    "RICH_USE_CASE_HEADERS",
    "RICH_USE_CASE_HEADING",
    "RICH_USE_CASE_TRIGGERS",
    "USE_CASE_ID",
    "authoritative_requirement_ids",
    "concrete_requirement_subject",
    "derive_requirements_contract",
    "gate_a_method_contract_issues",
    "measurable_acceptance_is_bound",
    "observable_requirement_response",
    "quality_attribute_scenario_issues",
    "requirement_method_issues",
)
