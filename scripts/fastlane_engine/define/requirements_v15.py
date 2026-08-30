"""Pure Requirements 1.5 completion, outcome, data, obligation, and risk rules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.contracts import ContractTable, contract_table_after_heading
from ..core.ids import (
    STABLE_CONTRACT_ID,
    clean_cell,
    explicit_value,
    parse_exact_id_list,
)
from .models import (
    CrossCuttingRisk,
    DatasetObligation,
    ExternalObligation,
    OutcomeMetric,
)


PROJECT_COMPLETION_TARGETS = ("LOCAL", "AWS_READ", "DEPLOYED", "RECOVERY")
OUTCOME_METRIC_HEADING = "### Product outcome measurement"
OUTCOME_METRIC_HEADERS = (
    "Metric ID",
    "Applicability",
    "Outcome basis IDs",
    "Metric",
    "Baseline",
    "Target",
    "Measurement window",
    "Evidence source",
    "Accountable role",
    "Guardrail",
    "Missed-target action",
)
DATASET_HEADING = "### Project data inventory"
DATASET_HEADERS = (
    "Dataset ID",
    "Dataset/category",
    "Purpose",
    "Classification",
    "Source of truth",
    "Access boundary",
    "Retention",
    "Deletion",
    "Recovery",
    "Residency",
    "Migration",
    "Audit obligation",
    "Accountable role",
    "Requirement basis IDs",
)
EXTERNAL_OBLIGATION_HEADING = "### External obligations"
EXTERNAL_OBLIGATION_HEADERS = (
    "Obligation ID",
    "Obligation",
    "Source/basis",
    "Applicability",
    "Affected users/data/journeys",
    "Required behavior",
    "Accountable role",
    "Requirement IDs",
    "Evidence requirement",
    "Review/expiration trigger",
)
CROSS_CUTTING_RISK_HEADING = "### Cross-cutting risk register"
CROSS_CUTTING_RISK_HEADERS = (
    "Risk ID",
    "Category",
    "Cross-cutting risk",
    "Likelihood",
    "Impact",
    "Accountable role",
    "Mitigation",
    "Revisit trigger",
    "Requirement IDs",
    "Status",
)

METRIC_ID = re.compile(r"METRIC-\d{3,}")
DATASET_ID = re.compile(r"DATASET-\d{3,}")
OBLIGATION_ID = re.compile(r"OBL-\d{3,}")
RISK_ID = re.compile(r"RISK-\d{3,}")
OUTCOME_BASIS_ID = re.compile(rf"(?:INTAKE-\d{{4}}|{STABLE_CONTRACT_ID.pattern})")
METRIC_APPLICABILITY = {"APPLICABLE", "NOT_APPLICABLE"}
DATA_CLASSIFICATIONS = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "REGULATED", "NONE"}
OBLIGATION_APPLICABILITY = {"APPLICABLE", "NONE_IDENTIFIED"}
RISK_LIKELIHOODS = {"LOW", "MEDIUM", "HIGH"}
RISK_IMPACTS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
RISK_STATUSES = {"OPEN", "MITIGATING", "MONITORING", "MATERIALIZED", "CLOSED"}
NO_PERSISTENT_DATA_ROW = ("NO PERSISTENT DATA", *("NONE",) * 12)
NO_EXTERNAL_OBLIGATION_FIELDS = ("NONE",) * 5
EXTENSION_TABLE_SPECS = (
    (OUTCOME_METRIC_HEADING, OUTCOME_METRIC_HEADERS, "OUTCOME_METRIC_INVALID"),
    (DATASET_HEADING, DATASET_HEADERS, "DATASET_CONTRACT_INVALID"),
    (
        EXTERNAL_OBLIGATION_HEADING,
        EXTERNAL_OBLIGATION_HEADERS,
        "EXTERNAL_OBLIGATION_INVALID",
    ),
    (
        CROSS_CUTTING_RISK_HEADING,
        CROSS_CUTTING_RISK_HEADERS,
        "CROSS_CUTTING_RISK_INVALID",
    ),
)


@dataclass(frozen=True)
class Requirements15Extension:
    completion_target: str | None = None
    outcome_metrics: tuple[OutcomeMetric, ...] = ()
    datasets: tuple[DatasetObligation, ...] = ()
    external_obligations: tuple[ExternalObligation, ...] = ()
    cross_cutting_risks: tuple[CrossCuttingRisk, ...] = ()
    canonical_tables: tuple[ContractTable, ...] = field(
        default=(), repr=False, compare=False
    )
    presentation_labels: tuple[tuple[str, str], ...] = field(
        default=(), repr=False, compare=False
    )


def _table(
    text: str,
    heading: str,
    headers: tuple[str, ...],
    code: str,
    issues: list[tuple[str, str]],
    missing: list[str],
) -> ContractTable | None:
    try:
        table = contract_table_after_heading(text, heading, headers)
    except ValueError as exc:
        issues.append((code, str(exc)))
        missing.append(heading)
        return None
    if table is None:
        issues.append((code, f"{heading} is required by Requirements 1.5"))
        missing.append(heading)
    return table


def _ordered_ids(
    rows: tuple[tuple[str, ...], ...],
    pattern: re.Pattern[str],
    label: str,
    code: str,
    issues: list[tuple[str, str]],
) -> None:
    identifiers = [row[0] for row in rows]
    if not identifiers:
        issues.append((code, f"{label} requires at least one row"))
        return
    invalid = [item for item in identifiers if pattern.fullmatch(item) is None]
    if invalid:
        issues.append((code, f"Invalid {label} IDs: " + ", ".join(invalid)))
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        issues.append((code, f"Duplicate {label} IDs: " + ", ".join(duplicates)))
    if identifiers != sorted(identifiers):
        issues.append((code, f"{label} rows must be sorted by ID"))


def _explicit_row(
    identifier: str,
    fields: tuple[tuple[str, str], ...],
    code: str,
    issues: list[tuple[str, str]],
    *,
    allow_none: bool = False,
) -> bool:
    invalid = [
        label
        for label, value in fields
        if not explicit_value(value, allow_none=allow_none)
    ]
    if invalid:
        issues.append((code, f"{identifier}: unresolved fields: " + ", ".join(invalid)))
        return False
    return True


def _references(
    value: str,
    pattern: re.Pattern[str],
    known: set[str],
    label: str,
    code: str,
    issues: list[tuple[str, str]],
    *,
    allow_none: bool = False,
) -> tuple[str, ...]:
    try:
        identifiers = parse_exact_id_list(value, pattern, label)
    except ValueError as exc:
        issues.append((code, str(exc)))
        return ()
    if not identifiers and not allow_none:
        issues.append((code, f"{label} must name at least one current ID"))
    if identifiers and clean_cell(value) != ", ".join(identifiers):
        issues.append((code, f"{label} must use canonical comma-space ID order"))
    if identifiers != sorted(identifiers):
        issues.append((code, f"{label} IDs must be sorted"))
    unknown = sorted(set(identifiers) - known)
    if unknown:
        issues.append((code, f"{label} references unknown IDs: " + ", ".join(unknown)))
    return tuple(identifiers)


def _outcome_metrics(
    table: ContractTable | None,
    known_basis_ids: set[str],
    issues: list[tuple[str, str]],
) -> tuple[OutcomeMetric, ...]:
    if table is None:
        return ()
    code = "OUTCOME_METRIC_INVALID"
    _ordered_ids(table.rows, METRIC_ID, "outcome metric", code, issues)
    result: list[OutcomeMetric] = []
    applicable = 0
    for row in table.rows:
        (
            metric_id,
            applicability,
            basis,
            metric,
            baseline,
            target,
            window,
            evidence_source,
            role,
            guardrail,
            missed_action,
        ) = row
        if applicability not in METRIC_APPLICABILITY:
            issues.append(
                (
                    code,
                    f"{metric_id}: Applicability must be APPLICABLE or NOT_APPLICABLE",
                )
            )
        if applicability == "APPLICABLE":
            applicable += 1
        _explicit_row(
            metric_id,
            (
                ("Metric", metric),
                ("Baseline", baseline),
                ("Target", target),
                ("Measurement window", window),
                ("Evidence source", evidence_source),
                ("Accountable role", role),
                ("Guardrail", guardrail),
                ("Missed-target action", missed_action),
            ),
            code,
            issues,
        )
        basis_ids = _references(
            basis,
            OUTCOME_BASIS_ID,
            known_basis_ids,
            f"{metric_id} Outcome basis IDs",
            code,
            issues,
        )
        result.append(
            OutcomeMetric(
                metric_id,
                applicability,
                basis_ids,
                metric,
                baseline,
                target,
                window,
                evidence_source,
                role,
                guardrail,
                missed_action,
            )
        )
    if table.rows and not applicable:
        issues.append((code, "Requirements 1.5 requires one applicable outcome metric"))
    return tuple(result)


def _datasets(
    table: ContractTable | None,
    requirement_ids: set[str],
    issues: list[tuple[str, str]],
) -> tuple[DatasetObligation, ...]:
    if table is None:
        return ()
    code = "DATASET_CONTRACT_INVALID"
    _ordered_ids(table.rows, DATASET_ID, "dataset", code, issues)
    result: list[DatasetObligation] = []
    for row in table.rows:
        dataset_id = row[0]
        classification = row[3]
        no_persistent_data = classification == "NONE"
        if classification not in DATA_CLASSIFICATIONS:
            issues.append(
                (
                    code,
                    f"{dataset_id}: Classification must be one of "
                    + ", ".join(sorted(DATA_CLASSIFICATIONS)),
                )
            )
        _explicit_row(
            dataset_id,
            tuple(zip(DATASET_HEADERS[1:-1], row[1:-1])),
            code,
            issues,
            allow_none=no_persistent_data,
        )
        basis_ids = _references(
            row[-1],
            STABLE_CONTRACT_ID,
            requirement_ids,
            f"{dataset_id} Requirement basis IDs",
            code,
            issues,
            allow_none=no_persistent_data,
        )
        if no_persistent_data and (
            len(table.rows) != 1 or row[1:] != NO_PERSISTENT_DATA_ROW
        ):
            issues.append(
                (
                    code,
                    f"{dataset_id}: Classification NONE requires the single canonical no-persistent-data row",
                )
            )
        result.append(
            DatasetObligation(
                dataset_id,
                *row[1:-1],
                requirement_basis_ids=basis_ids,
            )
        )
    return tuple(result)


def _external_obligations(
    table: ContractTable | None,
    requirement_ids: set[str],
    issues: list[tuple[str, str]],
) -> tuple[ExternalObligation, ...]:
    if table is None:
        return ()
    code = "EXTERNAL_OBLIGATION_INVALID"
    _ordered_ids(table.rows, OBLIGATION_ID, "external obligation", code, issues)
    result: list[ExternalObligation] = []
    for row in table.rows:
        (
            obligation_id,
            obligation,
            source_basis,
            applicability,
            affected_scope,
            required_behavior,
            role,
            requirement_value,
            evidence_requirement,
            review_trigger,
        ) = row
        if applicability not in OBLIGATION_APPLICABILITY:
            issues.append(
                (
                    code,
                    f"{obligation_id}: Applicability must be APPLICABLE or NONE_IDENTIFIED",
                )
            )
        _explicit_row(
            obligation_id,
            (
                ("Obligation", obligation),
                ("Source/basis", source_basis),
                ("Affected users/data/journeys", affected_scope),
                ("Required behavior", required_behavior),
                ("Accountable role", role),
                ("Evidence requirement", evidence_requirement),
                ("Review/expiration trigger", review_trigger),
            ),
            code,
            issues,
            allow_none=applicability == "NONE_IDENTIFIED",
        )
        allow_none = applicability == "NONE_IDENTIFIED"
        linked_ids = _references(
            requirement_value,
            STABLE_CONTRACT_ID,
            requirement_ids,
            f"{obligation_id} Requirement IDs",
            code,
            issues,
            allow_none=allow_none,
        )
        if allow_none and (
            obligation != "NONE IDENTIFIED"
            or not explicit_value(source_basis)
            or (
                affected_scope,
                required_behavior,
                role,
                requirement_value,
                evidence_requirement,
            )
            != NO_EXTERNAL_OBLIGATION_FIELDS
            or not explicit_value(review_trigger)
        ):
            issues.append(
                (
                    code,
                    f"{obligation_id}: NONE_IDENTIFIED requires the canonical no-obligation row with a concrete basis and review trigger",
                )
            )
        result.append(
            ExternalObligation(
                obligation_id,
                obligation,
                source_basis,
                applicability,
                affected_scope,
                required_behavior,
                role,
                linked_ids,
                evidence_requirement,
                review_trigger,
            )
        )
    return tuple(result)


def _risks(
    table: ContractTable | None,
    requirement_ids: set[str],
    issues: list[tuple[str, str]],
) -> tuple[CrossCuttingRisk, ...]:
    if table is None:
        return ()
    code = "CROSS_CUTTING_RISK_INVALID"
    _ordered_ids(table.rows, RISK_ID, "cross-cutting risk", code, issues)
    result: list[CrossCuttingRisk] = []
    for row in table.rows:
        (
            risk_id,
            category,
            risk,
            likelihood,
            impact,
            role,
            mitigation,
            revisit_trigger,
            requirement_value,
            status,
        ) = row
        if likelihood not in RISK_LIKELIHOODS:
            issues.append((code, f"{risk_id}: invalid likelihood {likelihood!r}"))
        if impact not in RISK_IMPACTS:
            issues.append((code, f"{risk_id}: invalid impact {impact!r}"))
        if status not in RISK_STATUSES:
            issues.append((code, f"{risk_id}: invalid status {status!r}"))
        _explicit_row(
            risk_id,
            (
                ("Category", category),
                ("Cross-cutting risk", risk),
                ("Accountable role", role),
                ("Mitigation", mitigation),
                ("Revisit trigger", revisit_trigger),
            ),
            code,
            issues,
        )
        linked_ids = _references(
            requirement_value,
            STABLE_CONTRACT_ID,
            requirement_ids,
            f"{risk_id} Requirement IDs",
            code,
            issues,
        )
        result.append(
            CrossCuttingRisk(
                risk_id,
                category,
                risk,
                likelihood,
                impact,
                role,
                mitigation,
                revisit_trigger,
                linked_ids,
                status,
            )
        )
    return tuple(result)


def derive_requirements_15_extension(
    text: str,
    document: dict[str, str],
    requirement_ids: set[str],
    confirmed_intake_ids: set[str],
) -> tuple[Requirements15Extension, tuple[str, ...], list[tuple[str, str]]]:
    """Return one fail-closed typed Requirements 1.5 extension."""

    issues: list[tuple[str, str]] = []
    missing: list[str] = []
    completion_target = clean_cell(document.get("Project completion target", ""))
    if completion_target not in PROJECT_COMPLETION_TARGETS:
        issues.append(
            (
                "PROJECT_COMPLETION_TARGET_INVALID",
                "Project completion target must be LOCAL, AWS_READ, DEPLOYED, or RECOVERY",
            )
        )
        missing.append("Project completion target")
    tables = tuple(
        _table(text, *spec, issues, missing) for spec in EXTENSION_TABLE_SPECS
    )
    metrics = _outcome_metrics(
        tables[0], requirement_ids | confirmed_intake_ids, issues
    )
    datasets = _datasets(tables[1], requirement_ids, issues)
    obligations = _external_obligations(tables[2], requirement_ids, issues)
    risks = _risks(tables[3], requirement_ids, issues)
    labels = (
        *((item.metric_id, item.metric) for item in metrics),
        *((item.dataset_id, item.dataset_category) for item in datasets),
        *((item.obligation_id, item.obligation) for item in obligations),
        *((item.risk_id, item.risk) for item in risks),
    )
    extension = Requirements15Extension(
        completion_target=(
            completion_target
            if completion_target in PROJECT_COMPLETION_TARGETS
            else None
        ),
        outcome_metrics=metrics,
        datasets=datasets,
        external_obligations=obligations,
        cross_cutting_risks=risks,
        canonical_tables=tuple(table for table in tables if table is not None),
        presentation_labels=labels,
    )
    return extension, tuple(dict.fromkeys(missing)), issues


__all__ = (
    "CROSS_CUTTING_RISK_HEADERS",
    "CROSS_CUTTING_RISK_HEADING",
    "DATASET_HEADERS",
    "DATASET_HEADING",
    "EXTERNAL_OBLIGATION_HEADERS",
    "EXTERNAL_OBLIGATION_HEADING",
    "OUTCOME_METRIC_HEADERS",
    "OUTCOME_METRIC_HEADING",
    "PROJECT_COMPLETION_TARGETS",
    "Requirements15Extension",
    "derive_requirements_15_extension",
)
