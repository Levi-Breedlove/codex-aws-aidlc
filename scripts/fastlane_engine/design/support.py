"""Technology, property-specification, and design-support validation.

Canonical inputs are caller-observed project records. Outputs are immutable
Design projections or ordered validation issues. This module performs no I/O,
routing, mutation, approval, authorization, or owner-facing rendering.
"""

from __future__ import annotations


import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping

from ..core.contracts import (
    ContractTable,
    SHELL_CONTROL,
    contract_table_after_heading,
    markdown_tables,
    table_after_heading,
)
from ..core.ids import (
    EVIDENCE_PLACEHOLDER_PATTERN,
    STABLE_CONTRACT_ID,
    canonical_id_list,
    clean_cell,
    explicit_value,
    none_with_reason,
    unresolved,
)
from .models import (
    ARCHITECTURE_DESIGN_ID,
    ARCHITECTURE_TEST_ID,
    ArchitectureContract,
    ProjectDesignContract,
    TechnologyDecision,
)


TECHNOLOGY_DECISION_HEADING = "### Technology and toolchain decision register"


TECHNOLOGY_DECISION_HEADERS = (
    "Decision ID",
    "Concern",
    "Selection",
    "Version policy",
    "Source",
    "Basis IDs",
    "Alternatives and rationale",
    "Compatibility/migration",
    "Validation",
)


LEGACY_REQUIRED_TECHNOLOGY_CONCERNS = (
    "APPLICATION_RUNTIME",
    "APPLICATION_FRAMEWORK",
    "FRONTEND_FRAMEWORK",
    "INFRASTRUCTURE_AS_CODE",
    "PACKAGE_BUILD_TOOLING",
    "TEST_TOOLING",
    "PROPERTY_TESTING",
    "SECURITY_VALIDATION",
    "DEPLOYMENT_TOOLING",
)


REQUIRED_TECHNOLOGY_CONCERNS = (
    *LEGACY_REQUIRED_TECHNOLOGY_CONCERNS,
    "IDENTITY_AUTHORIZATION",
    "DATA_STORAGE",
    "MESSAGING_RETRIES",
    "EDGE_NETWORKING",
    "OBSERVABILITY_INCIDENT_RESPONSE",
    "RELIABILITY_RECOVERY",
)


TECHNOLOGY_DECISION_ID = re.compile(r"TECH-\d{4}")


TECHNOLOGY_CONCERN = re.compile(r"[A-Z][A-Z0-9_]*")


TECHNOLOGY_SOURCES = {
    "OWNER_CONSTRAINT",
    "REPOSITORY_FACT",
    "AGENT_RECOMMENDATION",
}


HARNESS_LAYERS = {
    "Static",
    "Unit",
    "Integration",
    "End-to-end",
    "Property",
    "Security and privacy",
    "Reliability and recovery",
    "Performance and scalability",
    "IaC and policy",
    "AWS environment and operations",
}


EXAMPLE_SCENARIO_HEADING = "## 23. Example-based scenarios"


EXAMPLE_SCENARIO_HEADERS = (
    "Test ID",
    "Scenario",
    "Expected result",
    "Layer",
)


EXAMPLE_SCENARIO_ID = re.compile(r"EX-\d{3,}")


ERROR_HANDLING_HEADING = "## 19. Error handling strategy"


ERROR_HANDLING_HEADERS = (
    "Error class",
    "Example",
    "Retry?",
    "User-visible behavior",
    "Logging or metric",
    "Recovery",
)


REQUIRED_ERROR_CLASSES = (
    "Validation",
    "Transient dependency",
    "Permanent dependency",
    "Concurrency conflict",
    "Internal defect",
)


AWS_SERVICE_DECISION_HEADING = "## 20. AWS implementation approach"


AWS_SERVICE_DECISION_HEADERS = (
    "Concern",
    "Decision IDs",
    "AWS service or mechanism",
    "Rationale",
    "Tradeoff",
)


AWS_SERVICE_TECH_CONCERNS = {
    "Compute": ("APPLICATION_RUNTIME", "APPLICATION_FRAMEWORK"),
    "API and edge": ("APPLICATION_FRAMEWORK", "EDGE_NETWORKING"),
    "Identity": ("IDENTITY_AUTHORIZATION",),
    "Data": ("DATA_STORAGE",),
    "Messaging": ("MESSAGING_RETRIES",),
    "Observability": ("OBSERVABILITY_INCIDENT_RESPONSE",),
    "Deployment": (
        "INFRASTRUCTURE_AS_CODE",
        "DEPLOYMENT_TOOLING",
        "RELIABILITY_RECOVERY",
    ),
    "Secrets and encryption": ("SECURITY_VALIDATION",),
}


@dataclass(frozen=True)
class AwsImplementationDecision:
    """Private validated input for owner-facing AWS design diagrams."""

    concern: str
    decision_ids: tuple[str, ...]
    mechanism: str
    rationale: str
    tradeoff: str
    applicable_decision_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    decision_labels: tuple[tuple[str, str], ...]


IAC_VALIDATION_HEADING = "### IaC and delivery validation contract"


IAC_VALIDATION_HEADERS = (
    "Validation path",
    "Applicability",
    "TECH binding",
    "Required local/static validation",
    "AWS planning validation",
    "Evidence destination",
)


IAC_VALIDATION_PATHS = (
    "CloudFormation / SAM / CDK",
    "Terraform",
    "Container delivery",
    "Other approved delivery path",
)


IAC_VALIDATION_TECH_CONCERNS = {
    "INFRASTRUCTURE_AS_CODE",
    "SECURITY_VALIDATION",
    "DEPLOYMENT_TOOLING",
}


IAC_VALIDATION_EVIDENCE_DESTINATION = "docs/project/VERIFY.md#iac-validation-evidence"


PROPERTY_EXECUTION_HEADING = "### Property execution contract"


PROPERTY_EXECUTION_HEADERS = (
    "Property ID",
    "Framework TECH ID",
    "Exact command",
    "Run target/time bound",
    "Seed or reproduction format",
    "Evidence destination",
)


PROPERTY_APPLICABILITY_HEADERS = (
    "Requirement ID",
    "Applicability",
    "Reason or property IDs",
)


PROPERTY_DEFINITION_HEADERS = (
    "Property ID",
    "Requirement IDs",
    "Invariant",
    "Generated inputs or state",
    "Preconditions",
    "Oracle",
    "Boundary or shrink focus",
    "Layer",
)


PROPERTY_SPECIFICATION_HEADING = "## 24. Property-based testing specification"


PROPERTY_ID = re.compile(r"PROP-\d{3,}")


PROPERTY_TEST_EVIDENCE_DESTINATION = (
    "docs/project/VERIFY.md#property-based-test-evidence"
)


PROPERTY_COMMAND_EXECUTABLE = re.compile(
    r"(?:[a-z0-9][a-z0-9_.+-]*|\.{0,2}/[A-Za-z0-9_./+-]+|/[A-Za-z0-9_./+-]+)"
)


PROPERTY_COMMAND_PROSE_VERBS = {
    "check",
    "execute",
    "record",
    "run",
    "test",
    "use",
    "validate",
    "verify",
}


def parse_property_run_target(value: str) -> tuple[int | None, Decimal | None]:
    """Parse the canonical minimum-case and/or maximum-duration execution target."""

    cleaned = clean_cell(value)
    match = re.fullmatch(
        r"(?:MIN_CASES: (?P<cases>[1-9]\d*)"
        r"(?:; MAX_SECONDS: (?P<case_seconds>[1-9]\d*))?"
        r"|MAX_SECONDS: (?P<seconds>[1-9]\d*))",
        cleaned,
    )
    if match is None:
        raise ValueError(
            "run target/time bound must be MIN_CASES: <positive integer>, "
            "MAX_SECONDS: <positive number>, or both in that order"
        )
    minimum_cases = int(match.group("cases")) if match.group("cases") else None
    seconds_text = match.group("case_seconds") or match.group("seconds")
    maximum_seconds = Decimal(seconds_text) if seconds_text is not None else None
    if maximum_seconds is not None and (
        not maximum_seconds.is_finite() or maximum_seconds <= 0
    ):
        raise ValueError("MAX_SECONDS must be finite and greater than zero")
    return minimum_cases, maximum_seconds


def parsed_numeric_version(value: str) -> tuple[int, ...] | None:
    """Return the numeric release tuple for one exact package version."""

    cleaned = clean_cell(value)
    match = re.fullmatch(r"v?(?P<numeric>\d+(?:\.\d+)*)", cleaned)
    if match is None:
        return None
    return tuple(int(part) for part in match.group("numeric").split("."))


def valid_replay_format_contract(value: str) -> bool:
    """Require a property plan to declare a machine-checkable replay mode."""

    cleaned = clean_cell(value)
    if unresolved(cleaned):
        return False
    lowered = cleaned.casefold()
    return "seed" in lowered or "command" in lowered


def valid_property_execution_command(value: str) -> bool:
    """Recognize one explicit local command rather than prose or a sentinel."""

    cleaned = clean_cell(value)
    if (
        unresolved(cleaned)
        or EVIDENCE_PLACEHOLDER_PATTERN.search(cleaned) is not None
        or SHELL_CONTROL.search(cleaned) is not None
        or cleaned.startswith(("-", "#"))
    ):
        return False
    executable = cleaned.split(maxsplit=1)[0].strip("'\"")
    return bool(
        PROPERTY_COMMAND_EXECUTABLE.fullmatch(executable)
        and executable.casefold() not in PROPERTY_COMMAND_PROSE_VERBS
    )


def valid_technology_version_policy(value: str) -> bool:
    cleaned = clean_cell(value)
    if technology_contract_value_is_unresolved(cleaned):
        return False
    if cleaned.startswith("COMPATIBLE_MAJOR: "):
        return re.fullmatch(r"COMPATIBLE_MAJOR: [1-9]\d*", cleaned) is not None
    if cleaned.startswith("CURRENT_LTS_AS_OF: "):
        match = re.fullmatch(r"CURRENT_LTS_AS_OF: (\d{4}-\d{2}-\d{2})", cleaned)
        if match is None:
            return False
        try:
            datetime.strptime(match.group(1), "%Y-%m-%d")
        except ValueError:
            return False
        return True
    if cleaned.startswith("EXACT: "):
        return explicit_value(cleaned.removeprefix("EXACT: "), allow_none=False)
    if cleaned.startswith("MINIMUM: "):
        minimum = cleaned.removeprefix("MINIMUM: ")
        return (
            explicit_value(minimum, allow_none=False)
            and parsed_numeric_version(minimum) is not None
        )
    if cleaned.startswith("ORG_MANAGED: "):
        return explicit_value(cleaned.removeprefix("ORG_MANAGED: "), allow_none=False)
    prefix = "NOT_APPLICABLE — "
    return cleaned.startswith(prefix) and explicit_value(
        cleaned[len(prefix) :], allow_none=False
    )


def machine_comparable_property_version_policy(value: str) -> bool:
    """Require an active property framework policy with deterministic comparison."""

    cleaned = clean_cell(value)
    if not valid_technology_version_policy(cleaned):
        return False
    if cleaned.startswith("EXACT: "):
        return explicit_value(cleaned.removeprefix("EXACT: "), allow_none=False)
    if cleaned.startswith("COMPATIBLE_MAJOR: "):
        return re.fullmatch(r"COMPATIBLE_MAJOR: [1-9]\d*", cleaned) is not None
    if cleaned.startswith("MINIMUM: "):
        return parsed_numeric_version(cleaned.removeprefix("MINIMUM: ")) is not None
    return False


def technology_value_is_not_applicable(value: str) -> bool:
    return clean_cell(value).startswith("NOT_APPLICABLE — ")


def technology_contract_value_is_unresolved(value: str) -> bool:
    """Reject the complete contract sentinel vocabulary in technology cells."""

    cleaned = clean_cell(value)
    return (
        unresolved(cleaned) or EVIDENCE_PLACEHOLDER_PATTERN.search(cleaned) is not None
    )


def technology_reasoning_parts(value: str) -> tuple[str, str]:
    """Split the canonical reasoning cell without duplicating its prose."""

    cleaned = clean_cell(value)
    prefix = "RATIONALE: "
    separator = "; REJECTED: "
    if not cleaned.startswith(prefix) or separator not in cleaned:
        raise ValueError(
            "Alternatives and rationale must use "
            "RATIONALE: <selection reason>; REJECTED: <alternatives and reasons>"
        )
    rationale, rejected = cleaned[len(prefix) :].split(separator, 1)
    if not explicit_value(rationale, allow_none=False) or not explicit_value(
        rejected, allow_none=False
    ):
        raise ValueError(
            "Technology rationale and rejected alternatives must be concrete"
        )
    return rationale, rejected


def valid_technology_selection(value: str) -> bool:
    """Accept one concrete selection or the one canonical non-applicable form."""

    cleaned = clean_cell(value)
    if technology_contract_value_is_unresolved(cleaned):
        return False
    if technology_value_is_not_applicable(cleaned):
        reason = cleaned.removeprefix("NOT_APPLICABLE — ")
        return (
            explicit_value(reason, allow_none=False)
            and EVIDENCE_PLACEHOLDER_PATTERN.search(reason) is None
        )
    normalized = re.sub(r"[\s_-]+", "_", cleaned.upper())
    if cleaned.startswith("NOT_APPLICABLE") or normalized in {
        "N/A",
        "NA",
        "NONE",
        "NOT_APPLICABLE",
        "DOES_NOT_APPLY",
    }:
        return False
    return explicit_value(cleaned, allow_none=False)


def valid_technology_basis_ids(value: str) -> bool:
    """Require a canonical, duplicate-free comma-space stable-ID list."""

    cleaned = clean_cell(value)
    if unresolved(cleaned):
        return False
    identifiers = cleaned.split(", ")
    return (
        bool(identifiers)
        and all(
            STABLE_CONTRACT_ID.fullmatch(identifier) is not None
            for identifier in identifiers
        )
        and len(identifiers) == len(set(identifiers))
    )


def current_prd_basis_ids(
    text: str,
    design_revision: str | None,
    requirement_ids: set[str],
) -> set[str]:
    """Return stable IDs actually declared outside the technology register."""

    identifiers = set(requirement_ids)
    if design_revision is not None:
        identifiers.add(design_revision)
    try:
        document = table_after_heading(text, "## Document status")
    except ValueError:
        document = {}
    for field_name in (
        "Current requirements revision",
        "Current design revision",
        "Current construction authorization ID",
    ):
        value = clean_cell(document.get(field_name, ""))
        if STABLE_CONTRACT_ID.fullmatch(value) is not None:
            identifiers.add(value)
    technology_headers = list(TECHNOLOGY_DECISION_HEADERS)
    for table in markdown_tables(text):
        if not table or table[0] == technology_headers:
            continue
        for row in table[2:]:
            if row and STABLE_CONTRACT_ID.fullmatch(row[0]) is not None:
                identifiers.add(row[0])
    return identifiers


def _exact_property_ids(value: str) -> list[str]:
    cleaned = clean_cell(value)
    if unresolved(cleaned):
        raise ValueError("property IDs are unresolved")
    identifiers = [item.strip() for item in cleaned.split(",")]
    if not identifiers or any(
        PROPERTY_ID.fullmatch(item) is None for item in identifiers
    ):
        raise ValueError("property IDs must be comma-separated PROP-nnn IDs")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("property ID list contains duplicates")
    return identifiers


def derive_example_scenario_contract(
    text: str,
) -> tuple[ContractTable | None, set[str], list[str]]:
    """Parse the authoritative example-scenario declarations."""

    issues: list[str] = []
    try:
        table = contract_table_after_heading(
            text, EXAMPLE_SCENARIO_HEADING, EXAMPLE_SCENARIO_HEADERS
        )
    except ValueError as exc:
        return None, set(), [f"{EXAMPLE_SCENARIO_HEADING}: {exc}"]
    if table is None:
        return None, set(), [f"Missing {EXAMPLE_SCENARIO_HEADING}"]
    if not table.rows:
        issues.append("Example-based scenarios has no stored rows")
    identifiers: set[str] = set()
    for test_id, scenario, expected_result, layer in table.rows:
        if EXAMPLE_SCENARIO_ID.fullmatch(test_id) is None:
            issues.append(f"Invalid example scenario ID {test_id!r}")
        elif test_id in identifiers:
            issues.append(f"Duplicate example scenario ID {test_id}")
        identifiers.add(test_id)
        if not explicit_value(scenario, allow_none=False):
            issues.append(f"{test_id}: Scenario must be concrete")
        if not explicit_value(expected_result, allow_none=False):
            issues.append(f"{test_id}: Expected result must be concrete")
        if layer not in HARNESS_LAYERS:
            issues.append(f"{test_id}: invalid Harness layer {layer!r}")
    return table, identifiers, issues


def _support_value_is_concrete(value: str) -> bool:
    cleaned = clean_cell(value)
    return (
        explicit_value(cleaned, allow_none=False)
        and EVIDENCE_PLACEHOLDER_PATTERN.search(cleaned) is None
    )


def _not_applicable_reason(value: str) -> str | None:
    match = re.fullmatch(r"NOT_APPLICABLE (?:\u2014|-) (.+)", clean_cell(value))
    if match is None or not _support_value_is_concrete(match.group(1)):
        return None
    return match.group(1)


def _error_handling_contract(text: str) -> tuple[ContractTable | None, list[str]]:
    issues: list[str] = []
    try:
        error_table = contract_table_after_heading(
            text, ERROR_HANDLING_HEADING, ERROR_HANDLING_HEADERS
        )
    except ValueError as exc:
        error_table = None
        issues.append(f"Error handling contract: {exc}")
    if error_table is None:
        issues.append(f"Missing {ERROR_HANDLING_HEADING}")
    else:
        counts: dict[str, int] = {}
        for row in error_table.rows:
            error_class, _example, retry, *_remainder = row
            counts[error_class] = counts.get(error_class, 0) + 1
            if any(not _support_value_is_concrete(cell) for cell in row):
                issues.append(
                    f"{error_class or 'Error handling row'}: every error-handling "
                    "field must be concrete"
                )
            retry_value = clean_cell(retry)
            if not re.search(
                r"\b(?:no|bounded|fresh state|max(?:imum)?)\b", retry_value, re.I
            ):
                issues.append(
                    f"{error_class or 'Error handling row'}: retry posture must "
                    "explicitly deny or bound retry"
                )
            if re.search(r"\b(?:unbounded|unlimited|forever)\b", retry_value, re.I):
                issues.append(
                    f"{error_class or 'Error handling row'}: retry posture is unbounded"
                )
        for error_class in REQUIRED_ERROR_CLASSES:
            count = counts.get(error_class, 0)
            if count != 1:
                issues.append(
                    f"Error class {error_class} must appear exactly once; found {count}"
                )
        unexpected = sorted(set(counts) - set(REQUIRED_ERROR_CLASSES))
        if unexpected:
            issues.append("Unexpected error classes: " + ", ".join(unexpected))
    return error_table, issues


def _aws_evidence_by_design_id(
    architecture: ArchitectureContract,
) -> dict[str, set[str]]:
    """Index current material AWS evidence by its normalized Design binding."""

    result: dict[str, set[str]] = {}
    for evidence in architecture.aws_evidence:
        for identifier in clean_cell(evidence.design_ids).split(", "):
            if STABLE_CONTRACT_ID.fullmatch(identifier) is not None:
                result.setdefault(identifier, set()).add(evidence.evidence_id)
    return result


def _aws_row_bindings(
    concern: str,
    decision_ids: str,
    technology_by_id: Mapping[str, TechnologyDecision],
    technology_by_concern: Mapping[str, TechnologyDecision],
) -> tuple[tuple[str, ...], tuple[TechnologyDecision, ...], list[str]]:
    """Return exact row IDs and their canonical controlling decisions."""

    issues: list[str] = []
    try:
        identifiers = tuple(
            canonical_id_list(
                decision_ids,
                TECHNOLOGY_DECISION_ID,
                f"{concern} AWS decision IDs",
            )
        )
    except ValueError as exc:
        issues.append(str(exc))
        identifiers = ()
    unknown = [item for item in identifiers if item not in technology_by_id]
    if unknown:
        issues.append(
            f"{concern}: AWS decision IDs are not current technology IDs: "
            + ", ".join(unknown)
        )
    controlling = tuple(
        technology_by_concern[item]
        for item in AWS_SERVICE_TECH_CONCERNS.get(concern, ())
        if item in technology_by_concern
    )
    expected_ids = tuple(decision.decision_id for decision in controlling)
    if identifiers != expected_ids:
        issues.append(
            f"{concern}: AWS decision IDs must exactly match the ordered "
            "controlling decisions: "
            + (", ".join(expected_ids) if expected_ids else "NONE")
        )
    return identifiers, controlling, issues


def _aws_row_value_issues(
    concern: str,
    mechanism: str,
    rationale: str,
    tradeoff: str,
    controlling: tuple[TechnologyDecision, ...],
) -> list[str]:
    """Validate concrete owner wording and its selected mechanism binding."""

    issues: list[str] = []
    for label, value in (
        ("AWS service or mechanism", mechanism),
        ("Rationale", rationale),
        ("Tradeoff", tradeoff),
    ):
        if not _support_value_is_concrete(value):
            issues.append(f"{concern or 'AWS decision row'}: {label} is unresolved")
    expected_mechanism = "; ".join(decision.selection for decision in controlling)
    if expected_mechanism and clean_cell(mechanism) != expected_mechanism:
        issues.append(
            f"{concern}: AWS service or mechanism must exactly reproduce "
            f"the controlling TECH selections: {expected_mechanism}"
        )
    return issues


def _aws_applicability_issues(
    concern: str,
    mechanism: str,
    controlling: tuple[TechnologyDecision, ...],
) -> tuple[tuple[TechnologyDecision, ...], list[str]]:
    """Require AWS-row applicability to match its controlling decisions."""

    issues: list[str] = []
    applicable = tuple(
        decision
        for decision in controlling
        if not technology_value_is_not_applicable(decision.selection)
    )
    not_applicable_reason = _not_applicable_reason(mechanism)
    if clean_cell(mechanism).startswith("NOT_APPLICABLE") and not not_applicable_reason:
        issues.append(f"{concern}: NOT_APPLICABLE requires a concrete reason")
    if applicable and not_applicable_reason:
        issues.append(
            f"{concern}: an applicable TECH selection cannot use a "
            "NOT_APPLICABLE AWS mechanism"
        )
    if controlling and not applicable and not not_applicable_reason:
        issues.append(
            f"{concern}: all controlling TECH selections are NOT_APPLICABLE, "
            "so the AWS mechanism must also be NOT_APPLICABLE"
        )
    return applicable, issues


def _aws_evidence_issues(
    concern: str,
    applicable: tuple[TechnologyDecision, ...],
    evidence_by_design_id: Mapping[str, set[str]],
) -> list[str]:
    """Require current AWS evidence for every applicable selection."""

    issues: list[str] = []
    missing_evidence = [
        decision.decision_id
        for decision in applicable
        if not evidence_by_design_id.get(decision.decision_id)
    ]
    if missing_evidence:
        issues.append(
            f"{concern}: applicable TECH decisions lack current material "
            "AWS evidence: " + ", ".join(missing_evidence)
        )
    return issues


def _aws_row_content_issues(
    concern: str,
    mechanism: str,
    rationale: str,
    tradeoff: str,
    controlling: tuple[TechnologyDecision, ...],
    evidence_by_design_id: Mapping[str, set[str]],
) -> tuple[tuple[TechnologyDecision, ...], list[str]]:
    """Validate one owner-readable AWS row against selected Design truth."""

    applicable, applicability_issues = _aws_applicability_issues(
        concern, mechanism, controlling
    )
    return applicable, [
        *_aws_row_value_issues(concern, mechanism, rationale, tradeoff, controlling),
        *applicability_issues,
        *_aws_evidence_issues(concern, applicable, evidence_by_design_id),
    ]


def _aws_row_projection(
    row: tuple[str, ...],
    technology_by_id: Mapping[str, TechnologyDecision],
    technology_by_concern: Mapping[str, TechnologyDecision],
    evidence_by_design_id: Mapping[str, set[str]],
) -> tuple[AwsImplementationDecision, list[str]]:
    """Build one deterministic diagram input from a canonical section-20 row."""

    concern, decision_ids, mechanism, rationale, tradeoff = row
    identifiers, controlling, issues = _aws_row_bindings(
        concern, decision_ids, technology_by_id, technology_by_concern
    )
    applicable, content_issues = _aws_row_content_issues(
        concern,
        mechanism,
        rationale,
        tradeoff,
        controlling,
        evidence_by_design_id,
    )
    issues.extend(content_issues)
    evidence_ids = {
        evidence_id
        for decision in applicable
        for evidence_id in evidence_by_design_id.get(decision.decision_id, set())
    }
    labels = tuple(
        (
            decision.decision_id,
            (
                f"{_not_applicable_reason(decision.selection)} (not applicable)"
                if _not_applicable_reason(decision.selection)
                else clean_cell(decision.selection)
            ),
        )
        for decision in controlling
    )
    return (
        AwsImplementationDecision(
            concern=concern,
            decision_ids=identifiers,
            mechanism=clean_cell(mechanism),
            rationale=clean_cell(rationale),
            tradeoff=clean_cell(tradeoff),
            applicable_decision_ids=tuple(item.decision_id for item in applicable),
            evidence_ids=tuple(sorted(evidence_ids)),
            decision_labels=labels,
        ),
        issues,
    )


def derive_aws_implementation_decisions(
    text: str,
    technology_by_id: Mapping[str, TechnologyDecision],
    architecture: ArchitectureContract,
) -> tuple[ContractTable | None, tuple[AwsImplementationDecision, ...], list[str]]:
    """SAFETY: Normalize AWS rows from exact TECH and current evidence bindings."""

    issues: list[str] = []
    try:
        table = contract_table_after_heading(
            text, AWS_SERVICE_DECISION_HEADING, AWS_SERVICE_DECISION_HEADERS
        )
    except ValueError as exc:
        table = None
        issues.append(f"AWS service decision contract: {exc}")
    if table is None:
        return None, (), [*issues, f"Missing {AWS_SERVICE_DECISION_HEADING}"]
    technology_by_concern = {
        decision.concern: decision for decision in technology_by_id.values()
    }
    evidence_by_design_id = _aws_evidence_by_design_id(architecture)
    projections: list[AwsImplementationDecision] = []
    for row in table.rows:
        projection, row_issues = _aws_row_projection(
            row,
            technology_by_id,
            technology_by_concern,
            evidence_by_design_id,
        )
        projections.append(projection)
        issues.extend(row_issues)
    observed = tuple(item.concern for item in projections)
    for concern in AWS_SERVICE_TECH_CONCERNS:
        count = observed.count(concern)
        if count != 1:
            issues.append(
                f"AWS concern {concern} must appear exactly once; found {count}"
            )
    unexpected = sorted(set(observed) - set(AWS_SERVICE_TECH_CONCERNS))
    if unexpected:
        issues.append("Unexpected AWS decision concerns: " + ", ".join(unexpected))
    expected_order = tuple(AWS_SERVICE_TECH_CONCERNS)
    if observed != expected_order:
        issues.append(
            "AWS concerns must use the canonical order: " + ", ".join(expected_order)
        )
    return table, tuple(projections), issues


def _iac_validation_issues(
    text: str, technology_by_id: Mapping[str, TechnologyDecision]
) -> tuple[ContractTable | None, list[str]]:
    """SAFETY: Bind infrastructure validation to the selected delivery design."""

    issues: list[str] = []
    try:
        iac_table = contract_table_after_heading(
            text, IAC_VALIDATION_HEADING, IAC_VALIDATION_HEADERS
        )
    except ValueError as exc:
        iac_table = None
        issues.append(f"IaC and delivery validation contract: {exc}")
    if iac_table is None:
        issues.append(f"Missing {IAC_VALIDATION_HEADING}")
    else:
        counts: dict[str, int] = {}
        for row in iac_table.rows:
            (
                path,
                applicability,
                tech_binding,
                local_check,
                planning_check,
                destination,
            ) = row
            counts[path] = counts.get(path, 0) + 1
            for label, value in (
                ("TECH binding", tech_binding),
                ("Required local/static validation", local_check),
                ("AWS planning validation", planning_check),
            ):
                if not _support_value_is_concrete(value):
                    issues.append(
                        f"{path or 'IaC validation row'}: {label} is unresolved"
                    )
            if destination != IAC_VALIDATION_EVIDENCE_DESTINATION:
                issues.append(
                    f"{path}: Evidence destination must be exactly "
                    f"{IAC_VALIDATION_EVIDENCE_DESTINATION}"
                )
            if applicability == "APPLICABLE":
                try:
                    identifiers = canonical_id_list(
                        tech_binding,
                        TECHNOLOGY_DECISION_ID,
                        f"{path} TECH binding",
                    )
                except ValueError as exc:
                    issues.append(str(exc))
                    identifiers = []
                decisions = [
                    technology_by_id.get(identifier) for identifier in identifiers
                ]
                unknown = [
                    identifier
                    for identifier, decision in zip(identifiers, decisions)
                    if decision is None
                ]
                if unknown:
                    issues.append(
                        f"{path}: TECH binding references unknown IDs: "
                        + ", ".join(unknown)
                    )
                invalid_concerns = sorted(
                    {
                        decision.concern
                        for decision in decisions
                        if decision is not None
                        and decision.concern not in IAC_VALIDATION_TECH_CONCERNS
                    }
                )
                if invalid_concerns:
                    issues.append(
                        f"{path}: TECH binding uses unrelated concerns: "
                        + ", ".join(invalid_concerns)
                    )
                if decisions and not any(
                    decision is not None
                    and decision.concern
                    in {"INFRASTRUCTURE_AS_CODE", "DEPLOYMENT_TOOLING"}
                    for decision in decisions
                ):
                    issues.append(
                        f"{path}: TECH binding needs an infrastructure or deployment decision"
                    )
                for decision in decisions:
                    if decision is not None and technology_value_is_not_applicable(
                        decision.selection
                    ):
                        issues.append(
                            f"{path}: applicable validation cannot bind non-applicable "
                            f"technology decision {decision.decision_id}"
                        )
            elif _not_applicable_reason(applicability) is None:
                issues.append(
                    f"{path}: Applicability must be APPLICABLE or "
                    "NOT_APPLICABLE - <concrete reason>"
                )
        for path in IAC_VALIDATION_PATHS:
            count = counts.get(path, 0)
            if count != 1:
                issues.append(
                    f"IaC validation path {path} must appear exactly once; found {count}"
                )
        unexpected = sorted(set(counts) - set(IAC_VALIDATION_PATHS))
        if unexpected:
            issues.append("Unexpected IaC validation paths: " + ", ".join(unexpected))
    return iac_table, issues


def derive_design_support_records(
    text: str,
    technology_by_id: Mapping[str, TechnologyDecision],
    architecture: ArchitectureContract,
) -> tuple[tuple[AwsImplementationDecision, ...], bytes | None, list[str]]:
    """Return normalized AWS decisions, exact support bytes, and ordered issues."""

    error_table, error_issues = _error_handling_contract(text)
    aws_table, decisions, aws_issues = derive_aws_implementation_decisions(
        text, technology_by_id, architecture
    )
    iac_table, iac_issues = _iac_validation_issues(text, technology_by_id)
    tables = (error_table, aws_table, iac_table)
    canonical_bytes = (
        b"".join(table.canonical_bytes for table in tables if table is not None)
        if all(table is not None for table in tables)
        else None
    )
    return (
        () if aws_issues else decisions,
        canonical_bytes,
        [*error_issues, *aws_issues, *iac_issues],
    )


def architecture_trace_declaration_issues(
    architecture: ArchitectureContract,
    project_contract: ProjectDesignContract,
    declared_property_test_ids: set[str],
) -> list[str]:
    """Require every architecture trace ID to resolve to a current declaration."""

    declared_design_ids = set(project_contract.interface_ids)
    declared_design_ids.update(project_contract.boundary_ids)
    declared_design_ids.update(project_contract.state_ids)
    if architecture.selection is not None:
        declared_design_ids.add(architecture.selection.architecture_id)

    issues: list[str] = []
    for trace in architecture.traceability:
        try:
            design_ids = canonical_id_list(
                trace.design_ids,
                ARCHITECTURE_DESIGN_ID,
                f"{trace.requirement_id} architecture traceability design IDs",
            )
        except ValueError:
            pass
        else:
            undeclared_design_ids = sorted(set(design_ids) - declared_design_ids)
            if undeclared_design_ids:
                issues.append(
                    f"{trace.requirement_id}: architecture traceability references "
                    "undeclared design IDs: " + ", ".join(undeclared_design_ids)
                )

        if none_with_reason(trace.property_test_ids):
            continue
        try:
            property_test_ids = canonical_id_list(
                trace.property_test_ids,
                ARCHITECTURE_TEST_ID,
                f"{trace.requirement_id} property/test IDs",
            )
        except ValueError:
            continue
        undeclared_property_test_ids = sorted(
            set(property_test_ids) - declared_property_test_ids
        )
        if undeclared_property_test_ids:
            issues.append(
                f"{trace.requirement_id}: architecture traceability references "
                "undeclared property/test IDs: "
                + ", ".join(undeclared_property_test_ids)
            )
    return issues
