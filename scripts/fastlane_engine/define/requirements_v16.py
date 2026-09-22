"""Pure explicit recovery and input contracts for Requirements 1.6.

Applicability is an owner-reviewed declaration, never inferred from free prose.
Checks prove structural consistency and example membership, not completeness of
arbitrary natural-language requirements.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ..core.contracts import (
    ContractTable,
    _heading_section_lines,
    contract_table_after_heading,
)
from ..core.ids import explicit_value, parse_exact_id_list

RECOVERY_HEADING = "### Recovery applicability"
RECOVERY_HEADERS = (
    "Dataset ID",
    "Requirement IDs",
    "Scenario IDs",
    "Recovery mode",
    "Recovery time minutes",
    "Data loss minutes",
    "Decision basis",
)
SCENARIO_HEADING = "### Recovery scenario classification"
SCENARIO_HEADERS = ("QAS ID", "Kind", "Dataset IDs", "Decision basis")
APPLICABILITY_HEADING = "### Input applicability"
APPLICABILITY_HEADERS = ("Requirement ID", "Constraint IDs", "Decision basis")
INPUT_HEADING = "### Input boundaries"
INPUT_HEADERS = (
    "Constraint ID",
    "Requirement IDs",
    "Subject",
    "Kind",
    "Minimum",
    "Maximum",
    "Allowed values JSON",
    "Valid example JSON",
    "Invalid example JSON",
    "Rejection behavior",
)
DETAIL_HEADERS = {
    RECOVERY_HEADERS: RECOVERY_HEADING,
    SCENARIO_HEADERS: SCENARIO_HEADING,
    APPLICABILITY_HEADERS: APPLICABILITY_HEADING,
    INPUT_HEADERS: INPUT_HEADING,
}
INPUT_ID = re.compile(r"INPUT-\d{3,}")
REQUIREMENT_ID = re.compile(r"[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
SCENARIO_ID = re.compile(r"QAS-\d{3,}")
QAS_HEADING = "### Quality attribute scenarios"
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


@dataclass(frozen=True)
class Requirements16Extension:
    canonical_tables: tuple[ContractTable, ...] = ()

    def to_dict(self) -> dict[str, object]:
        names = (
            "recoveries",
            "recovery_scenarios",
            "input_applicability",
            "inputs",
            "quality_scenarios",
        )
        return {
            name: [dict(zip(table.headers, row)) for row in table.rows]
            for name, table in zip(names, self.canonical_tables)
        }


def _number(value: str) -> Decimal:
    if len(value) > 32:
        raise ValueError("numeric value is too long")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("value must be a finite number") from exc
    if not number.is_finite() or number.copy_abs() > 1_000_000_000:
        raise ValueError("value must be finite with magnitude at most one billion")
    return number


def valid_recovery_measure(value: str) -> bool:
    """Recognize the exact typed numeric recovery promise shared with QAS checks."""
    match = re.fullmatch(r"RTO (\S+) minutes and RPO (\S+) minutes", value)
    if match is None:
        return False
    try:
        return _number(match[1]) > 0 and _number(match[2]) >= 0
    except ValueError:
        return False


def _refs(
    value: str, pattern: re.Pattern[str], known: set[str], label: str
) -> tuple[str, ...]:
    refs = tuple(parse_exact_id_list(value, pattern, label))
    if not refs or set(refs) - known or list(refs) != sorted(set(refs)):
        raise ValueError(f"{label} must bind sorted, unique current IDs")
    return refs


def _single_table(text: str, heading: str, headers: tuple[str, ...]) -> ContractTable:
    table = contract_table_after_heading(text, heading, headers)
    section = _heading_section_lines(text, heading)
    if table is None or section is None:
        raise ValueError(f"{heading} is required by Requirements 1.6")
    lines = section[1]
    starts = sum(
        line.strip().startswith("|")
        and (i == 0 or not lines[i - 1].strip().startswith("|"))
        for i, line in enumerate(lines)
    )
    if starts != 1:
        raise ValueError(f"{heading} must contain exactly one authoritative table")
    return table


def _recovery_row(
    row: tuple[str, ...],
    datasets: dict[str, tuple[str, tuple[str, ...]]],
    requirements: set[str],
    scenarios: dict[str, tuple[str, ...]],
) -> tuple[str, tuple[str, ...]]:
    dataset, basis, qas, mode, recovery_time, loss, decision = row
    requirement_ids = _refs(
        basis, REQUIREMENT_ID, requirements, f"{dataset} Requirement IDs"
    )
    mechanism, dataset_basis = datasets.get(dataset, ("", ()))
    if not set(requirement_ids) <= set(dataset_basis):
        raise ValueError(
            f"{dataset}: recovery requirements must belong to this dataset"
        )
    if mode not in {"RESTORE", "RECREATE", "NONE"} or not explicit_value(
        decision, allow_none=False
    ):
        raise ValueError(
            f"{dataset}: recovery requires a mode and concrete decision basis"
        )
    if not mechanism.startswith(mode + ": ") or not explicit_value(
        mechanism[len(mode) + 2 :], allow_none=False
    ):
        raise ValueError(
            f"{dataset}: inventory Recovery must begin '{mode}: ' and explain the mechanism"
        )
    if mode == "NONE":
        if (qas, recovery_time, loss) != ("NONE", "NOT_APPLICABLE", "NOT_APPLICABLE"):
            raise ValueError(
                f"{dataset}: NONE recovery cannot claim a scenario or recovery bounds"
            )
        return dataset, ()
    if _number(recovery_time) <= 0 or _number(loss) < 0:
        raise ValueError(
            f"{dataset}: recovery time must be positive and data loss nonnegative"
        )
    refs = _refs(qas, SCENARIO_ID, set(scenarios), f"{dataset} Scenario IDs")
    for scenario in refs:
        record = scenarios[scenario]
        scenario_basis = _refs(
            record[1], REQUIREMENT_ID, requirements, f"{scenario} Requirement IDs"
        )
        if not set(scenario_basis) <= set(requirement_ids) or not record[6].startswith(
            mode + ": "
        ):
            raise ValueError(
                f"{dataset}: {scenario} must bind its recovery requirements and {mode} response"
            )
        if record[7] != f"RTO {recovery_time} minutes and RPO {loss} minutes":
            raise ValueError(
                f"{dataset}: {scenario} response measure must exactly match its recovery bounds"
            )
    return dataset, refs


def _recovery_inventory_issues(recovery, quality, datasets):
    issues: list[str] = []
    scenario_ids = [row[0] for row in quality.rows]
    if scenario_ids != sorted(set(scenario_ids)) or any(
        SCENARIO_ID.fullmatch(identifier) is None for identifier in scenario_ids
    ):
        issues.append("Quality scenarios require sorted unique current QAS IDs")
    if datasets and [row[0] for row in recovery.rows] != sorted(datasets):
        issues.append(
            "Recovery applicability must enumerate each dataset exactly once in sorted order"
        )
    if not datasets and recovery.rows != (("NO PERSISTENT DATA", *("NONE",) * 6),):
        issues.append("No-data recovery requires the exact NO PERSISTENT DATA/NONE row")
    return issues


def _recovery_issues(
    tables: tuple[ContractTable, ...], datasets, requirements
) -> list[str]:
    recovery, classification, _, _, quality = tables
    scenarios = {row[0]: row for row in quality.rows}
    issues: list[str] = []
    issues.extend(_recovery_inventory_issues(recovery, quality, datasets))
    bindings: dict[str, set[str]] = {identifier: set() for identifier in scenarios}
    for row in recovery.rows if datasets else ():
        try:
            dataset, refs = _recovery_row(row, datasets, requirements, scenarios)
            for ref in refs:
                bindings[ref].add(dataset)
        except ValueError as exc:
            issues.append(str(exc))
    issues.extend(_recovery_classification_issues(classification, scenarios, bindings))
    return issues


def _recovery_classification_issues(classification, scenarios, bindings) -> list[str]:
    issues: list[str] = []
    if [row[0] for row in classification.rows] != sorted(scenarios):
        issues.append(
            "Recovery classification must enumerate every QAS exactly once in sorted order"
        )
    for identifier, kind, dataset_ids, reason in classification.rows:
        expected = bindings.get(identifier, set())
        expected_kind = "RECOVERY" if expected else "OTHER"
        if kind != expected_kind or dataset_ids != (
            ", ".join(sorted(expected)) or "NONE"
        ):
            issues.append(
                f"{identifier}: recovery classification disagrees with dataset/scenario bindings"
            )
        if not explicit_value(reason, allow_none=False):
            issues.append(
                f"{identifier}: classification requires a concrete decision basis"
            )
        response = scenarios.get(identifier, ("",) * 8)[6]
        if not expected and response.startswith(("RESTORE:", "RECREATE:")):
            issues.append(
                f"{identifier}: a typed recovery response cannot be classified OTHER"
            )
    return issues


def _literal(value: str):
    try:
        parsed = json.loads(value, parse_float=Decimal, parse_int=Decimal)
    except (ValueError, RecursionError) as exc:
        raise ValueError(
            "input examples and enum values require JSON literals"
        ) from exc
    if isinstance(parsed, float) or (
        isinstance(parsed, Decimal) and not parsed.is_finite()
    ):
        raise ValueError("input examples require finite JSON numbers")
    if isinstance(parsed, (dict, list)):
        raise ValueError("input examples must be scalar JSON literals")
    return parsed


def _enum_examples(identifier, minimum, maximum, allowed, accepted, rejected):
    try:
        values = json.loads(allowed)
    except (ValueError, RecursionError) as exc:
        raise ValueError(
            f"{identifier}: enum requires an explicit JSON string array"
        ) from exc
    if (
        not isinstance(values, list)
        or len(values) < 2
        or not all(isinstance(v, str) for v in values)
    ):
        raise ValueError(f"{identifier}: enum requires at least two string values")
    if len(set(values)) != len(values) or (minimum, maximum) != ("NOT_APPLICABLE",) * 2:
        raise ValueError(
            f"{identifier}: enum values must be distinct with NOT_APPLICABLE bounds"
        )
    return accepted in values, rejected not in values


def _range_examples(identifier, kind, minimum, maximum, allowed, accepted, rejected):
    lower, upper = _number(minimum), _number(maximum)
    if upper < lower or allowed != "NOT_APPLICABLE":
        raise ValueError(
            f"{identifier}: range is reversed or enum values are ambiguous"
        )
    if kind == "TEXT_LENGTH":
        if lower < 0 or lower != int(lower) or upper != int(upper):
            raise ValueError(f"{identifier}: text bounds must be nonnegative integers")
        return (
            isinstance(accepted, str) and lower <= len(accepted) <= upper,
            not isinstance(rejected, str) or not lower <= len(rejected) <= upper,
        )
    return (
        isinstance(accepted, Decimal) and lower <= accepted <= upper,
        not isinstance(rejected, Decimal) or not lower <= rejected <= upper,
    )


def _examples(row: tuple[str, ...]) -> None:
    (
        identifier,
        _,
        subject,
        kind,
        minimum,
        maximum,
        allowed,
        valid,
        invalid,
        rejection,
    ) = row
    if not all(
        explicit_value(value, allow_none=False) for value in (subject, rejection)
    ):
        raise ValueError(
            f"{identifier}: subject and rejection behavior must be concrete"
        )
    accepted, rejected = _literal(valid), _literal(invalid)
    if kind == "ENUM":
        fits, fails = _enum_examples(
            identifier, minimum, maximum, allowed, accepted, rejected
        )
    elif kind in {"TEXT_LENGTH", "NUMBER_RANGE"}:
        fits, fails = _range_examples(
            identifier, kind, minimum, maximum, allowed, accepted, rejected
        )
    else:
        raise ValueError(
            f"{identifier}: kind must be ENUM, TEXT_LENGTH, or NUMBER_RANGE"
        )
    if not fits or not fails:
        raise ValueError(
            f"{identifier}: examples do not demonstrate the declared boundary"
        )


def _input_issues(
    tables: tuple[ContractTable, ...], requirements: set[str]
) -> list[str]:
    _, _, applicability, inputs, _ = tables
    issues: list[str] = []
    bindings: dict[str, set[str]] = {identifier: set() for identifier in requirements}
    ids = [row[0] for row in inputs.rows]
    if ids != sorted(set(ids)):
        issues.append("Input boundaries require sorted unique constraint IDs")
    for row in inputs.rows:
        try:
            if INPUT_ID.fullmatch(row[0]) is None:
                raise ValueError(f"Invalid input constraint ID {row[0]!r}")
            for requirement in _refs(
                row[1], REQUIREMENT_ID, requirements, f"{row[0]} Requirement IDs"
            ):
                bindings[requirement].add(row[0])
            _examples(row)
        except ValueError as exc:
            issues.append(str(exc))
    if [row[0] for row in applicability.rows] != sorted(requirements):
        issues.append(
            "Input applicability must enumerate every requirement exactly once in sorted order"
        )
    for identifier, constraints, reason in applicability.rows:
        if constraints != (
            ", ".join(sorted(bindings.get(identifier, set()))) or "NONE"
        ):
            issues.append(
                f"{identifier}: input applicability and boundary requirement bindings disagree"
            )
        if not explicit_value(reason, allow_none=False):
            issues.append(
                f"{identifier}: input applicability requires a concrete basis, including NONE"
            )
    return issues


def derive_requirements_16_extension(
    text: str,
    datasets: dict[str, tuple[str, tuple[str, ...]]],
    requirement_ids: set[str],
) -> tuple[Requirements16Extension, list[str]]:
    tables: list[ContractTable] = []
    issues: list[str] = []
    for headers, heading in (*DETAIL_HEADERS.items(), (QAS_HEADERS, QAS_HEADING)):
        try:
            tables.append(_single_table(text, heading, headers))
        except ValueError as exc:
            issues.append(str(exc))
    if len(tables) != 5:
        return Requirements16Extension(), issues
    canonical = tuple(tables)
    issues.extend(_recovery_issues(canonical, datasets, requirement_ids))
    issues.extend(_input_issues(canonical, requirement_ids))
    return Requirements16Extension(canonical), issues
