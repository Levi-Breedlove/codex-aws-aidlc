"""Design schema, interfaces, states, walking skeleton, and aggregate projection.

Canonical inputs are caller-observed project records. Outputs are immutable
Design projections or ordered validation issues. This module performs no I/O,
routing, mutation, approval, authorization, or owner-facing rendering.
"""

from __future__ import annotations


import hashlib
import re
from dataclasses import replace
from typing import Any, Callable, Sequence

from ..core.contracts import (
    ContractTable,
    _heading_section_lines,
    contract_table_after_heading,
    contract_table_in_section,
    markdown_tables,
    table_after_heading,
    without_fenced_code,
)
from ..core.ids import (
    EVIDENCE_PLACEHOLDER_PATTERN,
    STABLE_CONTRACT_ID,
    canonical_id_list,
    clean_cell,
    explicit_value,
    unresolved,
)
from .architecture import _derive_architecture_contract
from .diagrams import (
    DIAGRAM_CONTRACT_HEADERS,
    DIAGRAM_CONTRACT_HEADING,
    _derive_current_diagram_contract,
    is_diagram_presentation_issue,
)
from .harness import HARNESS_ID, derive_harness_contract
from .models import (
    APPLICATION_SOURCE_DISPOSITION_FIELD,
    ARCHITECTURE_ID,
    ApplicationSourceDisposition,
    DesignContract,
    FirstWaveContract,
    HarnessContract,
    ProjectDesignContract,
    PropertyExecution,
    SpikeContract,
    TechnologyDecision,
)
from .source import (
    parse_application_source_disposition,
    validate_application_source_disposition,
)
from .support import (
    LEGACY_REQUIRED_TECHNOLOGY_CONCERNS,
    PROPERTY_APPLICABILITY_HEADERS,
    PROPERTY_DEFINITION_HEADERS,
    PROPERTY_EXECUTION_HEADERS,
    PROPERTY_EXECUTION_HEADING,
    PROPERTY_ID,
    PROPERTY_SPECIFICATION_HEADING,
    PROPERTY_TEST_EVIDENCE_DESTINATION,
    REQUIRED_TECHNOLOGY_CONCERNS,
    TECHNOLOGY_CONCERN,
    TECHNOLOGY_DECISION_HEADERS,
    TECHNOLOGY_DECISION_HEADING,
    TECHNOLOGY_DECISION_ID,
    TECHNOLOGY_SOURCES,
    _exact_property_ids,
    architecture_trace_declaration_issues,
    current_prd_basis_ids,
    derive_design_support_records,
    derive_example_scenario_contract,
    machine_comparable_property_version_policy,
    parse_property_run_target,
    technology_contract_value_is_unresolved,
    technology_reasoning_parts,
    technology_value_is_not_applicable,
    valid_property_execution_command,
    valid_replay_format_contract,
    valid_technology_basis_ids,
    valid_technology_selection,
    valid_technology_version_policy,
)


PROJECT_DESIGN_CONTRACT_SCHEMA = "7"


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


INTERFACE_HEADING = "## 16. Interfaces and contracts"


INTERFACE_HEADERS = (
    "Contract ID",
    "Kind",
    "Requirement basis",
    "Producer",
    "Consumer",
    "Schema or protocol",
    "Authentication",
    "Authorization",
    "Input validation",
    "Success output/status",
    "Error and recovery behavior",
    "Compatibility/versioning",
    "Idempotency/concurrency",
    "Timeout bound",
    "Rate bound",
    "Performance bound",
)


LEGACY_INTERFACE_HEADERS_V4 = (
    "Contract ID",
    "Producer",
    "Consumer",
    "Schema or protocol",
    "Authentication",
    "Versioning",
    "Idempotency",
)


INTERFACE_ID = re.compile(r"(?:API|EVENT|CLI|FILE)-\d{3,}")


INTERFACE_KINDS = {"API", "EVENT", "CLI", "FILE"}


LAYER_BOUNDARY_HEADING = "### Layer boundaries"


LAYER_BOUNDARY_HEADERS = (
    "Boundary ID",
    "Outer adapter/layer",
    "Inner domain layer",
    "Boundary DTO/schema",
    "Explicit mapping",
    "Dependency direction",
    "Authorization enforcement",
    "External anti-corruption adapter",
    "Requirement IDs",
    "Validation IDs",
)


BOUNDARY_ID = re.compile(r"BOUNDARY-\d{3,}")


STATE_APPLICABILITY_HEADING = "### State-model applicability"


STATE_APPLICABILITY_HEADERS = (
    "Subject ID",
    "Applicability",
    "Trigger basis IDs",
    "State model IDs",
)


STATE_REGISTER_HEADING = "### State register"


STATE_REGISTER_HEADERS = (
    "State model ID",
    "Subject ID",
    "States",
    "Initial state",
    "Allowed transitions",
    "Terminal states",
    "Invalid-transition behavior",
    "Requirement IDs",
    "Validation IDs",
)


STATE_ID = re.compile(r"STATE-\d{3,}")


RICH_TO_STATE_TRIGGER = {
    "ASYNCHRONOUS_WORK": "ASYNCHRONOUS_WORK",
    "MIGRATION_OR_CUTOVER": "MIGRATION_OR_CUTOVER",
    "PARTIAL_FAILURE": "RETRY_OR_RESUME",
}


FIRST_WAVE_HEADING = "### First construction wave"


FIRST_WAVE_HEADERS = (
    "Wave contract ID",
    "Work kind",
    "Walking-skeleton journey ID",
    "Requirement IDs",
    "Acceptance/test IDs",
    "End-to-end Harness ID",
    "Blocking spike ID",
)


WAVE_ID = re.compile(r"WAVE-\d{3,}")


SPIKE_HEADING = "### Blocking spike"


SPIKE_HEADERS = (
    "Spike ID",
    "Blocking technical unknown",
    "Time box",
    "Disposable output boundary",
    "Exit criterion",
    "Required next action",
)


SPIKE_ID = re.compile(r"SPIKE-\d{3,}")


MEASURABLE_INTERFACE_BOUND = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*(?:ns|nanoseconds?|us|microseconds?|ms|"
    r"milliseconds?|s|secs?|seconds?|minutes?|hours?|days?|weeks?|bytes?|"
    r"kib|mib|gib|kb|mb|gb|tb|requests?|operations?|events?|items?|records?|"
    r"users?|transactions?|messages?|files?|rps|qps|tps|percent)\b|"
    r"\b\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*/\s*(?:s|sec(?:ond)?s?|"
    r"m|min(?:ute)?s?|h|hours?)\b|\b\d+(?:\.\d+)?\s+per\s+"
    r"(?:second|minute|hour|day)\b)",
    re.IGNORECASE,
)


UNDEFINED_QUALITY_TERM = re.compile(
    r"\b(?:fast|secure|scalable|user[- ]friendly|appropriate)\b",
    re.IGNORECASE,
)


def _contract_table_or_issue(
    text: str,
    heading: str,
    headers: tuple[str, ...],
    issues: list[str],
    missing_records: list[str],
) -> ContractTable | None:
    """Return one exact table while preserving current missing-record ordering."""

    try:
        table = contract_table_after_heading(text, heading, headers)
    except ValueError as exc:
        table, message = None, f"{heading}: {exc}"
    else:
        message = f"Missing {heading}" if table is None else None
    if table is None:
        issues.append(message)
        missing_records.append(heading)
    return table


def _contract_ids(value: str, pattern: re.Pattern[str], field_name: str) -> list[str]:
    """Parse one canonical, duplicate-free contract-ID list."""

    return canonical_id_list(clean_cell(value), pattern, field_name)


def _explicit_not_applicable_section(text: str, heading: str) -> bytes | None:
    section = _heading_section_lines(text, heading)
    if section is None:
        return None
    lines, structural_lines = section
    visible_lines = [
        line.strip()
        for line, structural in zip(lines, structural_lines)
        if structural.strip() and not structural.strip().startswith("|")
    ]
    for line in visible_lines:
        match = re.fullmatch(
            r"NOT_APPLICABLE\s+(?:\u2014|-)\s+(?P<reason>[^\r\n]+)",
            line,
        )
        if match is None:
            continue
        if explicit_value(match.group("reason"), allow_none=False):
            return (
                f"{heading}\nNOT_APPLICABLE - {match.group('reason').strip()}\n"
            ).encode("utf-8")
    return None


def _explicit_not_applicable_value(value: str) -> bool:
    match = re.fullmatch(
        r"NOT_APPLICABLE\s+(?:\u2014|-)\s+(?P<reason>.+)", clean_cell(value)
    )
    return bool(match and explicit_value(match.group("reason"), allow_none=False))


def _server_side_authorization_or_not_applicable(value: str) -> bool:
    cleaned = clean_cell(value)
    if _explicit_not_applicable_value(cleaned):
        return True
    normalized = re.sub(r"[\s-]+", "_", cleaned.upper())
    return "SERVER_SIDE" in normalized or bool(
        re.search(
            r"\bserver(?:-side)?\b.*\b(?:authoriz\w*|enforc\w*|verif\w*|den\w*|reject\w*)\b",
            cleaned,
            re.IGNORECASE,
        )
    )


def _measurable_interface_bound_or_not_applicable(value: str) -> bool:
    cleaned = clean_cell(value)
    return _explicit_not_applicable_value(cleaned) or bool(
        explicit_value(cleaned, allow_none=False)
        and UNDEFINED_QUALITY_TERM.search(cleaned) is None
        and MEASURABLE_INTERFACE_BOUND.search(cleaned)
    )


def _design_reference_issues(
    identifier: str,
    requirement_value: str,
    validation_value: str,
    requirement_ids: set[str],
    validation_ids: set[str],
) -> list[str]:
    issues: list[str] = []
    try:
        refs = set(
            _contract_ids(
                requirement_value, STABLE_CONTRACT_ID, f"{identifier} Requirement IDs"
            )
        )
        unknown = sorted(refs - requirement_ids)
        if unknown:
            issues.append(
                f"{identifier}: unknown requirement IDs: " + ", ".join(unknown)
            )
        refs = set(
            _contract_ids(
                validation_value, STABLE_CONTRACT_ID, f"{identifier} Validation IDs"
            )
        )
        unknown = sorted(refs - validation_ids)
        if unknown:
            issues.append(
                f"{identifier}: unknown Validation IDs: " + ", ".join(unknown)
            )
    except ValueError as exc:
        issues.append(str(exc))
    return issues


def _project_schema_state(
    text: str,
    legacy_design_ids: set[str],
    *,
    required: bool,
    grandfather_approved_v4: bool,
) -> tuple[
    dict[str, str],
    bool,
    bool,
    list[str],
    tuple[ProjectDesignContract, list[str]] | None,
]:
    """COMPATIBILITY: Select current, grandfathered, or migration semantics."""

    issues: list[str] = []
    try:
        document = table_after_heading(text, "## Document status")
    except ValueError as exc:
        document = {}
        if required:
            issues.append(str(exc))
    design_schema = clean_cell(document.get("Project design contract schema", ""))
    grandfather_schema_6 = bool(design_schema == "6" and grandfather_approved_v4)
    grandfather_schema_5 = bool(
        design_schema == "5"
        and grandfather_approved_v4
        and DIAGRAM_CONTRACT_HEADING not in without_fenced_code(text)
    )
    if (
        design_schema == PROJECT_DESIGN_CONTRACT_SCHEMA
        or grandfather_schema_6
        or grandfather_schema_5
    ):
        return document, grandfather_schema_5, grandfather_schema_6, issues, None

    observed_tables = [table for table in markdown_tables(text) if table]
    observed_headers = {tuple(table[0]) for table in observed_tables}
    current_headers = {
        INTERFACE_HEADERS,
        LAYER_BOUNDARY_HEADERS,
        STATE_APPLICABILITY_HEADERS,
        STATE_REGISTER_HEADERS,
        FIRST_WAVE_HEADERS,
        SPIKE_HEADERS,
        DIAGRAM_CONTRACT_HEADERS,
    }
    legacy_interface_tables = [
        table
        for table in observed_tables
        if tuple(table[0]) == LEGACY_INTERFACE_HEADERS_V4
    ]
    legacy_interface_ids = [
        clean_cell(row[0])
        for table in legacy_interface_tables
        for row in table[2:]
        if len(row) == len(LEGACY_INTERFACE_HEADERS_V4)
    ]
    structural_text = without_fenced_code(text)
    schema_five_only_headings = (
        LAYER_BOUNDARY_HEADING,
        STATE_APPLICABILITY_HEADING,
        STATE_REGISTER_HEADING,
        FIRST_WAVE_HEADING,
        SPIKE_HEADING,
    )
    exact_legacy_shape = bool(
        not design_schema
        and len(legacy_interface_tables) == 1
        and legacy_interface_ids
        and all(INTERFACE_ID.fullmatch(item) for item in legacy_interface_ids)
        and not (observed_headers & current_headers)
        and not any(
            re.search(rf"^{re.escape(heading)}[ \t]*$", structural_text, re.MULTILINE)
            for heading in schema_five_only_headings
        )
        and any(ARCHITECTURE_ID.fullmatch(item) for item in legacy_design_ids)
        and any(TECHNOLOGY_DECISION_ID.fullmatch(item) for item in legacy_design_ids)
        and any(PROPERTY_ID.fullmatch(item) for item in legacy_design_ids)
        and any(HARNESS_ID.fullmatch(item) for item in legacy_design_ids)
    )
    if grandfather_approved_v4 and exact_legacy_shape:
        return (
            document,
            False,
            False,
            [],
            (
                ProjectDesignContract(
                    schema_version=4, status="GRANDFATHERED", grandfathered_v4=True
                ),
                [],
            ),
        )
    if not required:
        return (
            document,
            False,
            False,
            [],
            (
                ProjectDesignContract(status="UNINITIALIZED"),
                [],
            ),
        )
    return (
        document,
        False,
        False,
        [],
        (
            ProjectDesignContract(
                status="MIGRATION_REQUIRED",
                missing_records=(
                    "Project design contract schema 7",
                    APPLICATION_SOURCE_DISPOSITION_FIELD,
                    INTERFACE_HEADING,
                    LAYER_BOUNDARY_HEADING,
                    STATE_APPLICABILITY_HEADING,
                    STATE_REGISTER_HEADING,
                    FIRST_WAVE_HEADING,
                    SPIKE_HEADING,
                    DIAGRAM_CONTRACT_HEADING,
                ),
            ),
            [
                "Project design contract schema 7 requires an application source "
                "disposition plus current interface, layer-boundary, state-applicability, "
                "first-wave, spike, and diagram records"
            ],
        ),
    )


def _project_presentation_labels(
    interfaces: ContractTable | None,
    boundaries: ContractTable | None,
    states: ContractTable | None,
) -> tuple[tuple[str, str], ...]:
    """Project concise component names without entering Design digests."""

    labels = [
        *(
            (row[0], f"{row[3]} to {row[4]}")
            for row in (interfaces.rows if interfaces else ())
        ),
        *(
            (row[0], f"{row[1]} to {row[2]}")
            for row in (boundaries.rows if boundaries else ())
        ),
        *((row[0], row[2]) for row in (states.rows if states else ())),
    ]
    return tuple((identifier, clean_cell(label)) for identifier, label in labels)


def derive_project_design_contract(
    text: str,
    requirements_contract: Any,
    coverage_contract: Any,
    authoritative_requirement_ids: set[str],
    allowed_basis_ids: set[str],
    harness: HarnessContract,
    legacy_design_ids: set[str],
    state_trigger_mapper: Callable[[str, str], dict[str, tuple[str, ...]]],
    *,
    required: bool,
    grandfather_approved_v4: bool,
) -> tuple[ProjectDesignContract, list[str]]:
    """SAFETY: Validate the complete project design before Gate B readiness."""

    (
        document,
        grandfather_schema_5,
        grandfather_schema_6,
        issues,
        early_result,
    ) = _project_schema_state(
        text,
        legacy_design_ids,
        required=required,
        grandfather_approved_v4=grandfather_approved_v4,
    )
    if early_result is not None:
        return early_result
    add = issues.append
    missing_records: list[str] = []

    source_disposition: ApplicationSourceDisposition | None = None
    if not (grandfather_schema_5 or grandfather_schema_6):
        try:
            envelope = table_after_heading(text, "## 28. Construction envelope")
        except ValueError as exc:
            envelope = {}
            if required:
                add(
                    "APPLICATION_SOURCE_DISPOSITION_MISSING: unable to read the "
                    f"construction envelope: {exc}"
                )
        raw_disposition = clean_cell(
            envelope.get(APPLICATION_SOURCE_DISPOSITION_FIELD, "")
        )
        if not raw_disposition or unresolved(raw_disposition):
            if required:
                add(
                    "APPLICATION_SOURCE_DISPOSITION_MISSING: schema 7 requires "
                    "Application source disposition before Gate B"
                )
                missing_records.append(APPLICATION_SOURCE_DISPOSITION_FIELD)
        else:
            try:
                source_disposition = parse_application_source_disposition(
                    raw_disposition
                )
            except ValueError as exc:
                add(f"APPLICATION_SOURCE_DISPOSITION_INVALID: {exc}")
            if source_disposition is not None:
                issues.extend(
                    validate_application_source_disposition(
                        source_disposition,
                        project_mode=clean_cell(
                            document.get("Project mode", "")
                        ).lower()
                        or None,
                        work_kind=coverage_contract.work_kind,
                        prd_text=text,
                    )
                )

    interfaces, boundaries, state_applicability, states = (
        _contract_table_or_issue(text, heading, headers, issues, missing_records)
        for heading, headers in (
            (INTERFACE_HEADING, INTERFACE_HEADERS),
            (LAYER_BOUNDARY_HEADING, LAYER_BOUNDARY_HEADERS),
            (STATE_APPLICABILITY_HEADING, STATE_APPLICABILITY_HEADERS),
            (STATE_REGISTER_HEADING, STATE_REGISTER_HEADERS),
        )
    )

    requirement_ids = set(requirements_contract.requirement_ids) or set(
        authoritative_requirement_ids
    )
    current_validation_ids = (
        set(allowed_basis_ids)
        | set(requirements_contract.acceptance_ids)
        | set(harness.required_ids)
    )
    journey_requirement_ids: dict[str, set[str]] = {}
    try:
        journey_table = contract_table_after_heading(
            text, JOURNEY_HEADING, JOURNEY_HEADERS
        )
    except ValueError:
        journey_table = None
    if journey_table is not None:
        for journey_row in journey_table.rows:
            journey_id = journey_row[0]
            if JOURNEY_ID.fullmatch(journey_id) is None:
                continue
            try:
                journey_requirement_ids[journey_id] = set(
                    _contract_ids(
                        journey_row[6],
                        STABLE_CONTRACT_ID,
                        f"{journey_id} Requirement IDs",
                    )
                )
            except ValueError:
                continue
    interface_ids: list[str] = []
    if interfaces is not None:
        if not interfaces.rows and coverage_contract.work_kind == "NEW_BUILD":
            add("NEW_BUILD requires at least one material interface contract")
        for row in interfaces.rows:
            contract_id, kind, requirement_value, *details = row
            if INTERFACE_ID.fullmatch(contract_id) is None:
                add(f"Invalid material interface ID {contract_id!r}")
                continue
            if contract_id in interface_ids:
                add(f"Duplicate material interface ID {contract_id}")
            interface_ids.append(contract_id)
            if kind not in INTERFACE_KINDS or not contract_id.startswith(kind + "-"):
                add(f"{contract_id}: Kind must match its API/EVENT/CLI/FILE prefix")
            try:
                refs = set(
                    _contract_ids(
                        requirement_value,
                        STABLE_CONTRACT_ID,
                        f"{contract_id} Requirement basis",
                    )
                )
                unknown = sorted(refs - requirement_ids)
                if unknown:
                    add(
                        f"{contract_id}: unknown requirement basis IDs: "
                        + ", ".join(unknown)
                    )
            except ValueError as exc:
                add(str(exc))
            for header, value in zip(INTERFACE_HEADERS[3:], details):
                if not explicit_value(value, allow_none=False):
                    add(f"{contract_id}: {header} must be concrete")
            detail_values = dict(zip(INTERFACE_HEADERS[3:], details))
            if not _server_side_authorization_or_not_applicable(
                detail_values["Authorization"]
            ):
                add(
                    f"{contract_id}: Authorization must be server-side or use "
                    "NOT_APPLICABLE - <reason>"
                )
            for header in ("Timeout bound", "Rate bound", "Performance bound"):
                if not _measurable_interface_bound_or_not_applicable(
                    detail_values[header]
                ):
                    add(
                        f"{contract_id}: {header} must contain a numeric measurable "
                        "bound or use NOT_APPLICABLE - <reason>"
                    )

    boundary_ids: list[str] = []
    if boundaries is not None:
        if not boundaries.rows and coverage_contract.work_kind == "NEW_BUILD":
            add("NEW_BUILD requires at least one explicit layer boundary")
        for row in boundaries.rows:
            (
                boundary_id,
                outer,
                inner,
                dto,
                mapping,
                direction,
                authorization,
                adapter,
                requirement_value,
                validation_value,
            ) = row
            if BOUNDARY_ID.fullmatch(boundary_id) is None:
                add(f"Invalid boundary ID {boundary_id!r}")
                continue
            if boundary_id in boundary_ids:
                add(f"Duplicate boundary ID {boundary_id}")
            boundary_ids.append(boundary_id)
            for header, value in zip(
                LAYER_BOUNDARY_HEADERS[1:8],
                (outer, inner, dto, mapping, direction, authorization, adapter),
            ):
                if not explicit_value(value, allow_none=False):
                    add(f"{boundary_id}: {header} must be concrete")
            if "INWARD" not in direction.upper():
                add(f"{boundary_id}: Dependency direction must explicitly point inward")
            normalized_authorization = authorization.upper().replace("-", "_")
            if "SERVER_SIDE" not in normalized_authorization:
                add(f"{boundary_id}: Authorization enforcement must be server-side")
            issues.extend(
                _design_reference_issues(
                    boundary_id,
                    requirement_value,
                    validation_value,
                    requirement_ids,
                    current_validation_ids,
                )
            )

    applicable_state_ids: set[str] = set()
    state_subjects: dict[str, str] = {}
    declared_state_triggers: set[str] = set()
    required_state_triggers = {
        RICH_TO_STATE_TRIGGER[item]
        for item in requirements_contract.rich_use_case_triggers
        if item in RICH_TO_STATE_TRIGGER
    }
    if state_applicability is not None:
        if not state_applicability.rows:
            add("State-model applicability requires at least one row")
        for (
            subject_id,
            applicability,
            trigger_basis,
            state_value,
        ) in state_applicability.rows:
            if STABLE_CONTRACT_ID.fullmatch(subject_id) is None:
                add(f"Invalid state subject ID {subject_id!r}")
            if applicability == "APPLICABLE":
                try:
                    refs = _contract_ids(
                        state_value, STATE_ID, f"{subject_id} State model IDs"
                    )
                    for state_id in refs:
                        applicable_state_ids.add(state_id)
                        state_subjects[state_id] = subject_id
                    trigger_map = state_trigger_mapper(trigger_basis, subject_id)
                    declared_state_triggers.update(trigger_map)
                    trigger_refs = {
                        item for values in trigger_map.values() for item in values
                    }
                    unknown_trigger = sorted(
                        trigger_refs - current_validation_ids - requirement_ids
                    )
                    if unknown_trigger:
                        add(
                            f"{subject_id}: unknown State trigger basis IDs: "
                            + ", ".join(unknown_trigger)
                        )
                except ValueError as exc:
                    add(str(exc))
            elif applicability == "NOT_APPLICABLE":
                if (
                    not trigger_basis.startswith("NOT_APPLICABLE")
                    or not explicit_value(trigger_basis, allow_none=False)
                    or state_value != "NONE"
                ):
                    add(
                        f"{subject_id}: NOT_APPLICABLE requires a concrete reason and State model IDs NONE"
                    )
            else:
                add(
                    f"{subject_id}: State applicability must be APPLICABLE or NOT_APPLICABLE"
                )
    missing_state_triggers = sorted(required_state_triggers - declared_state_triggers)
    if missing_state_triggers:
        add(
            "Journey triggers require applicable state categories: "
            + ", ".join(missing_state_triggers)
        )
    if requirements_contract.grandfathered_approved_gate_a and not applicable_state_ids:
        add("A grandfathered Gate A design requires an applicable state model")

    state_ids: list[str] = []
    if states is not None:
        for row in states.rows:
            (
                state_id,
                subject_id,
                state_value,
                initial_state,
                transitions,
                terminal_value,
                invalid_behavior,
                requirement_value,
                validation_value,
            ) = row
            if STATE_ID.fullmatch(state_id) is None:
                add(f"Invalid state model ID {state_id!r}")
                continue
            if state_id in state_ids:
                add(f"Duplicate state model ID {state_id}")
            state_ids.append(state_id)
            if state_id not in applicable_state_ids:
                add(f"{state_id}: state row is not declared APPLICABLE")
            if state_subjects.get(state_id) != subject_id:
                add(f"{state_id}: Subject ID does not match state applicability")
            declared_states = [
                item.strip() for item in state_value.split(",") if item.strip()
            ]
            if (
                not declared_states
                or state_value != ", ".join(declared_states)
                or initial_state not in declared_states
            ):
                add(
                    f"{state_id}: States must be canonical and contain the initial state"
                )
            if terminal_value != "NONE":
                terminal_states = [
                    item.strip() for item in terminal_value.split(",") if item.strip()
                ]
                if not set(terminal_states) <= set(declared_states):
                    add(f"{state_id}: Terminal states must be declared states or NONE")
            for label, value in (
                ("Allowed transitions", transitions),
                ("Invalid-transition behavior", invalid_behavior),
            ):
                if not explicit_value(value, allow_none=False):
                    add(f"{state_id}: {label} must be concrete")
            issues.extend(
                _design_reference_issues(
                    state_id,
                    requirement_value,
                    validation_value,
                    requirement_ids,
                    current_validation_ids,
                )
            )
        missing_states = sorted(applicable_state_ids - set(state_ids))
        if missing_states:
            add(
                "Applicable state models have no state row: "
                + ", ".join(missing_states)
            )

    first_wave_table: ContractTable | None = None
    first_wave_sentinel = _explicit_not_applicable_section(text, FIRST_WAVE_HEADING)
    try:
        first_wave_table = contract_table_after_heading(
            text, FIRST_WAVE_HEADING, FIRST_WAVE_HEADERS
        )
    except ValueError as exc:
        if first_wave_sentinel is None:
            add(f"{FIRST_WAVE_HEADING}: {exc}")
            missing_records.append(FIRST_WAVE_HEADING)
    first_wave: FirstWaveContract | None = None
    work_kind = coverage_contract.work_kind
    if work_kind == "NEW_BUILD":
        if first_wave_table is None or len(first_wave_table.rows) != 1:
            add("NEW_BUILD requires exactly one first construction wave row")
        else:
            (
                wave_id,
                row_work_kind,
                journey_id,
                requirement_value,
                acceptance_value,
                harness_id,
                spike_value,
            ) = first_wave_table.rows[0]
            if WAVE_ID.fullmatch(wave_id) is None:
                add(f"Invalid first-wave ID {wave_id!r}")
            if row_work_kind != "NEW_BUILD":
                add("First-wave Work kind must exactly match NEW_BUILD")
            legacy_bridge = requirements_contract.grandfathered_approved_gate_a
            journey_reference: str | None = None if legacy_bridge else journey_id
            if legacy_bridge and journey_id != "NONE":
                add(
                    f"{wave_id}: grandfathered Gate A walking-skeleton journey must be NONE"
                )
            elif not legacy_bridge and journey_id not in set(
                requirements_contract.journey_ids
            ):
                add(f"{wave_id}: walking-skeleton journey is not a current JOURNEY ID")
            try:
                wave_requirements = tuple(
                    _contract_ids(
                        requirement_value,
                        STABLE_CONTRACT_ID,
                        f"{wave_id} Requirement IDs",
                    )
                )
                unknown = sorted(set(wave_requirements) - requirement_ids)
                if unknown:
                    add(f"{wave_id}: unknown requirement IDs: " + ", ".join(unknown))
                selected_journey_requirements = journey_requirement_ids.get(
                    journey_reference or ""
                )
                if selected_journey_requirements is not None:
                    outside_journey = sorted(
                        set(wave_requirements) - selected_journey_requirements
                    )
                    if outside_journey:
                        add(
                            f"{wave_id}: first-wave requirement IDs are not owned by {journey_reference}: "
                            + ", ".join(outside_journey)
                        )
                acceptance_ids = tuple(
                    _contract_ids(
                        acceptance_value,
                        STABLE_CONTRACT_ID,
                        f"{wave_id} Acceptance/test IDs",
                    )
                )
                expected_acceptance = {f"AC-{item}" for item in wave_requirements}
                missing_acceptance = sorted(expected_acceptance - set(acceptance_ids))
                if missing_acceptance:
                    add(
                        f"{wave_id}: missing acceptance IDs: "
                        + ", ".join(missing_acceptance)
                    )
                unknown_acceptance = sorted(
                    set(acceptance_ids) - current_validation_ids
                )
                if unknown_acceptance:
                    add(
                        f"{wave_id}: unknown acceptance/test IDs: "
                        + ", ".join(unknown_acceptance)
                    )
            except ValueError as exc:
                wave_requirements = ()
                acceptance_ids = ()
                add(str(exc))
            harness_row = next(
                (row for row in harness.rows if row.harness_id == harness_id), None
            )
            if (
                harness_row is None
                or harness_row.layer != "End-to-end"
                or harness_id not in set(harness.required_ids)
            ):
                add(
                    f"{wave_id}: End-to-end Harness ID must reference a current required end-to-end check"
                )
            else:
                harness_basis = set(
                    canonical_id_list(
                        harness_row.basis_ids,
                        STABLE_CONTRACT_ID,
                        f"{harness_id} Basis IDs",
                    )
                )
                required_harness_basis = (
                    {wave_id, *wave_requirements}
                    if legacy_bridge
                    else {wave_id, journey_id}
                )
                if not required_harness_basis <= harness_basis:
                    message = (
                        "include the wave and every selected requirement"
                        if legacy_bridge
                        else f"include both {journey_id} and {wave_id}"
                    )
                    add(f"{wave_id}: {harness_id} Basis IDs must {message}")
            spike_id: str | None
            if spike_value == "NONE":
                spike_id = None
            elif SPIKE_ID.fullmatch(spike_value) is None:
                spike_id = None
                add(f"{wave_id}: invalid Blocking spike ID {spike_value!r}")
            else:
                spike_id = spike_value
            first_wave = FirstWaveContract(
                wave_contract_id=wave_id,
                work_kind=row_work_kind,
                journey_id=journey_reference,
                requirement_ids=wave_requirements,
                acceptance_test_ids=acceptance_ids,
                harness_id=harness_id,
                blocking_spike_id=spike_id,
            )
    elif first_wave_sentinel is None:
        add("Non-NEW_BUILD work requires an explicit NOT_APPLICABLE first-wave reason")

    spike_table: ContractTable | None = None
    spike_sentinel = _explicit_not_applicable_section(text, SPIKE_HEADING)
    try:
        spike_table = contract_table_after_heading(text, SPIKE_HEADING, SPIKE_HEADERS)
    except ValueError as exc:
        if spike_sentinel is None:
            issues.append(f"{SPIKE_HEADING}: {exc}")
            missing_records.append(SPIKE_HEADING)
    spike: SpikeContract | None = None
    expected_spike_id = first_wave.blocking_spike_id if first_wave is not None else None
    if expected_spike_id is None:
        if spike_sentinel is None:
            add(
                "A first wave without a blocking spike requires an explicit NOT_APPLICABLE spike reason"
            )
    elif spike_table is None or len(spike_table.rows) != 1:
        add("A referenced blocking spike requires exactly one spike row")
    else:
        spike_id, unknown, time_box, disposable, exit_criterion, next_action = (
            spike_table.rows[0]
        )
        if spike_id != expected_spike_id:
            add("Blocking spike row must exactly match the first-wave spike ID")
        if not explicit_value(unknown, allow_none=False):
            add(f"{spike_id}: Blocking technical unknown must be concrete")
        if re.fullmatch(r"MAX_ATTEMPTS: [1-9]\d*", time_box) is None:
            add(f"{spike_id}: Time box must use MAX_ATTEMPTS: <positive integer>")
        for label, value in (
            ("Disposable output boundary", disposable),
            ("Exit criterion", exit_criterion),
        ):
            if not explicit_value(value, allow_none=False):
                add(f"{spike_id}: {label} must be concrete")
        if not valid_property_execution_command(exit_criterion):
            add(
                f"{spike_id}: Exit criterion must be one explicit local command, "
                "not prose, shell control, or placeholder content"
            )
        if next_action != "DISCARD_AND_BUILD_WALKING_SKELETON":
            add(
                f"{spike_id}: Required next action must be DISCARD_AND_BUILD_WALKING_SKELETON"
            )
        spike = SpikeContract(
            spike_id=spike_id,
            technical_unknown=unknown,
            time_box=time_box,
            disposable_boundary=disposable,
            exit_criterion=exit_criterion,
            required_next_action=next_action,
        )

    canonical_parts: list[bytes] = [
        f"PROJECT_DESIGN_CONTRACT_SCHEMA: "
        f"{'5' if grandfather_schema_5 else '6' if grandfather_schema_6 else PROJECT_DESIGN_CONTRACT_SCHEMA}\n".encode(
            "utf-8"
        )
    ]
    if source_disposition is not None:
        canonical_parts.append(
            (
                "APPLICATION_SOURCE_DISPOSITION: "
                + source_disposition.canonical_value
                + "\n"
            ).encode("utf-8")
        )
    if (
        requirements_contract.grandfathered_approved_gate_a
        and requirements_contract.canonical_sha256 is None
    ):
        add(
            "Grandfathered Gate A design requires a canonical legacy requirements projection"
        )
    elif requirements_contract.grandfathered_approved_gate_a:
        canonical_parts.append(
            f"LEGACY_GATE_A_BRIDGE: {requirements_contract.canonical_sha256}\n".encode(
                "utf-8"
            )
        )
    for table in (interfaces, boundaries, state_applicability, states):
        if table is not None:
            canonical_parts.append(table.canonical_bytes)
    if first_wave_table is not None:
        canonical_parts.append(first_wave_table.canonical_bytes)
    elif first_wave_sentinel is not None:
        canonical_parts.append(first_wave_sentinel)
    if spike_table is not None and expected_spike_id is not None:
        canonical_parts.append(spike_table.canonical_bytes)
    elif spike_sentinel is not None:
        canonical_parts.append(spike_sentinel)
    canonical_bytes = b"".join(canonical_parts)
    canonical_sha256 = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
    if not required and any(
        unresolved(cell)
        for table in (interfaces, boundaries, state_applicability, states)
        if table is not None
        for row in table.rows
        for cell in row
    ):
        return ProjectDesignContract(status="UNINITIALIZED"), []
    return (
        ProjectDesignContract(
            schema_version=(
                5 if grandfather_schema_5 else 6 if grandfather_schema_6 else 7
            ),
            status=(
                "GRANDFATHERED"
                if (grandfather_schema_5 or grandfather_schema_6) and not issues
                else "READY"
                if not issues
                else "BLOCKED"
            ),
            application_source_disposition=source_disposition,
            interface_ids=tuple(interface_ids),
            boundary_ids=tuple(boundary_ids),
            state_ids=tuple(state_ids),
            presentation_labels=_project_presentation_labels(
                interfaces, boundaries, states
            ),
            first_wave=first_wave,
            spike=spike,
            missing_records=tuple(dict.fromkeys(missing_records)),
            canonical_sha256=canonical_sha256,
            grandfathered_v5=grandfather_schema_5,
            grandfathered_v6=grandfather_schema_6,
            canonical_bytes=canonical_bytes,
        ),
        issues,
    )


def _current_design_support_records(
    text: str,
    technology_by_id: dict[str, TechnologyDecision],
    architecture: Any,
) -> tuple[tuple[Any, ...], bytes | None, list[str]]:
    """Return exact modern support inputs before compatibility policy is applied."""

    return derive_design_support_records(text, technology_by_id, architecture)


def _current_diagram_contract(
    text: str,
    architecture: Any,
    requirements: Any,
    coverage: Any,
    project_contract: ProjectDesignContract,
    aws_decisions: tuple[Any, ...],
    technology_by_id: dict[str, TechnologyDecision],
    current_ids: set[str],
    *,
    required: bool,
    grandfathered: bool,
) -> tuple[Any, list[str]]:
    """Evaluate current project diagrams with legacy Design compatibility."""

    return _derive_current_diagram_contract(
        text,
        architecture,
        requirements,
        coverage,
        project_contract,
        aws_decisions,
        technology_by_id,
        current_ids,
        required=required,
        grandfathered_schema5=(
            project_contract.grandfathered_v4 or project_contract.grandfathered_v5
        ),
        grandfathered_pre_aws_diagrams=grandfathered,
        legacy_public_compatibility=project_contract.grandfathered_v6,
    )


def _bind_current_design_support(
    project_contract: ProjectDesignContract,
    diagram_contract: Any,
    *,
    grandfathered: bool,
) -> bool:
    """Keep pre-support schema-six Design bytes exact while binding modern rows."""

    return not project_contract.grandfathered_v6 and (
        not grandfathered
        or any(
            record.kind == "AWS_IMPLEMENTATION" and record.status == "CURRENT"
            for record in diagram_contract.records
        )
    )


def _current_project_contract(
    text: str,
    requirements: Any,
    coverage: Any,
    requirement_ids: set[str],
    allowed_basis_ids: set[str],
    technology_by_id: dict[str, TechnologyDecision],
    executions: list[PropertyExecution],
    harness: HarnessContract,
    architecture: Any,
    state_trigger_mapper: Callable[[str, str], dict[str, tuple[str, ...]]],
    *,
    required: bool,
    grandfathered: bool,
) -> tuple[ProjectDesignContract, list[str]]:
    """Derive project Design records from the current validated support IDs."""

    available_ids = (
        set(technology_by_id)
        | {execution.property_id for execution in executions}
        | {row.harness_id for row in harness.rows}
    )
    if architecture.selection is not None:
        available_ids.add(architecture.selection.architecture_id)
    return derive_project_design_contract(
        text,
        requirements,
        coverage,
        requirement_ids,
        allowed_basis_ids | set(technology_by_id),
        harness,
        available_ids,
        state_trigger_mapper,
        required=required,
        grandfather_approved_v4=grandfathered,
    )


def derive_design_contract(
    text: str,
    design_revision: str | None,
    *,
    required: bool = False,
    grandfather_approved_v1: bool = False,
    coverage_contract: Any,
    requirements_contract: Any,
    authoritative_requirement_ids: set[str],
    change_impact_deriver: Callable[..., tuple[Any, list[str]]],
    state_trigger_mapper: Callable[[str, str], dict[str, tuple[str, ...]]],
    initial_issues: Sequence[str] = (),
) -> tuple[DesignContract, list[str]]:
    """SAFETY: Derive one complete Design result from explicit Define inputs."""
    issues = list(initial_issues)
    try:
        technology_table = contract_table_after_heading(
            text, TECHNOLOGY_DECISION_HEADING, TECHNOLOGY_DECISION_HEADERS
        )
    except ValueError as exc:
        technology_table = None
        issues.append(f"Technology decision register: {exc}")
    try:
        execution_table = contract_table_after_heading(
            text, PROPERTY_EXECUTION_HEADING, PROPERTY_EXECUTION_HEADERS
        )
    except ValueError as exc:
        execution_table = None
        issues.append(f"Property execution contract: {exc}")
    example_table, example_ids, example_issues = derive_example_scenario_contract(text)

    both_missing = technology_table is None and execution_table is None and not issues
    if technology_table is None:
        issues.append(f"Missing {TECHNOLOGY_DECISION_HEADING}")
    if execution_table is None:
        issues.append(f"Missing {PROPERTY_EXECUTION_HEADING}")

    technologies: list[TechnologyDecision] = []
    seen_technology_ids: set[str] = set()
    concern_counts: dict[str, int] = {}
    allowed_basis_ids = current_prd_basis_ids(
        text, design_revision, authoritative_requirement_ids
    ) | set(
        requirements_contract.actor_ids
        + requirements_contract.journey_ids
        + requirements_contract.acceptance_ids
    )
    if technology_table is not None:
        if not technology_table.rows:
            issues.append("Technology decision register has no stored rows")
        for row in technology_table.rows:
            decision = TechnologyDecision(*row)
            technologies.append(decision)
            if TECHNOLOGY_DECISION_ID.fullmatch(decision.decision_id) is None:
                issues.append(
                    f"Invalid technology decision ID {decision.decision_id!r}"
                )
            elif decision.decision_id in seen_technology_ids:
                issues.append(
                    f"Duplicate technology decision ID {decision.decision_id}"
                )
            seen_technology_ids.add(decision.decision_id)
            if TECHNOLOGY_CONCERN.fullmatch(decision.concern) is None:
                issues.append(
                    f"{decision.decision_id}: invalid technology concern {decision.concern!r}"
                )
            concern_counts[decision.concern] = (
                concern_counts.get(decision.concern, 0) + 1
            )
            if any(technology_contract_value_is_unresolved(cell) for cell in row):
                issues.append(
                    f"{decision.decision_id}: unresolved technology decision cell"
                )
            elif not grandfather_approved_v1:
                try:
                    technology_reasoning_parts(decision.alternatives_and_rationale)
                except ValueError as exc:
                    issues.append(f"{decision.decision_id}: {exc}")
            if not unresolved(decision.selection) and not valid_technology_selection(
                decision.selection
            ):
                issues.append(
                    f"{decision.decision_id}: invalid selection {decision.selection!r}; "
                    "use NOT_APPLICABLE — <reason> when the concern does not apply"
                )
            if not unresolved(
                decision.version_policy
            ) and not valid_technology_version_policy(decision.version_policy):
                issues.append(
                    f"{decision.decision_id}: invalid version policy {decision.version_policy!r}"
                )
            if (
                not unresolved(decision.selection)
                and not unresolved(decision.version_policy)
                and technology_value_is_not_applicable(decision.selection)
                != technology_value_is_not_applicable(decision.version_policy)
            ):
                issues.append(
                    f"{decision.decision_id}: Selection and Version policy must both "
                    "use NOT_APPLICABLE — <reason>, or both be applicable"
                )
            if (
                not unresolved(decision.source)
                and decision.source not in TECHNOLOGY_SOURCES
            ):
                issues.append(
                    f"{decision.decision_id}: invalid source {decision.source!r}"
                )
            if not unresolved(decision.basis_ids):
                if not valid_technology_basis_ids(decision.basis_ids):
                    issues.append(
                        f"{decision.decision_id}: Basis IDs must be exact comma-separated "
                        "stable IDs without prose or duplicates"
                    )
                else:
                    basis_ids = decision.basis_ids.split(", ")
                    unknown_basis_ids = [
                        identifier
                        for identifier in basis_ids
                        if identifier not in allowed_basis_ids
                    ]
                    if unknown_basis_ids:
                        issues.append(
                            f"{decision.decision_id}: Basis IDs are not current PRD IDs: "
                            + ", ".join(unknown_basis_ids)
                        )
                    if design_revision is not None and design_revision not in basis_ids:
                        issues.append(
                            f"{decision.decision_id}: Basis IDs must include current "
                            f"design revision {design_revision}"
                        )
        required_concerns = (
            LEGACY_REQUIRED_TECHNOLOGY_CONCERNS
            if grandfather_approved_v1
            else REQUIRED_TECHNOLOGY_CONCERNS
        )
        for concern in required_concerns:
            count = concern_counts.get(concern, 0)
            if count != 1:
                issues.append(
                    f"Technology concern {concern} must appear exactly once; found {count}"
                )

    executions: list[PropertyExecution] = []
    seen_execution_ids: set[str] = set()
    if execution_table is not None:
        for row in execution_table.rows:
            execution = PropertyExecution(*row)
            executions.append(execution)
            if PROPERTY_ID.fullmatch(execution.property_id) is None:
                issues.append(
                    f"Invalid property execution ID {execution.property_id!r}"
                )
            elif execution.property_id in seen_execution_ids:
                issues.append(
                    f"Duplicate property execution ID {execution.property_id}"
                )
            seen_execution_ids.add(execution.property_id)
            if TECHNOLOGY_DECISION_ID.fullmatch(execution.framework_tech_id) is None:
                issues.append(
                    f"{execution.property_id}: invalid Framework TECH ID {execution.framework_tech_id!r}"
                )
            if any(unresolved(cell) for cell in row):
                issues.append(
                    f"{execution.property_id}: unresolved property execution cell"
                )
            if not valid_property_execution_command(execution.exact_command):
                issues.append(
                    f"{execution.property_id}: Exact command must be one explicit "
                    "local command, not prose or placeholder content"
                )
            if not unresolved(execution.run_target_time_bound):
                try:
                    parse_property_run_target(execution.run_target_time_bound)
                except ValueError as exc:
                    issues.append(f"{execution.property_id}: {exc}")
            if not unresolved(
                execution.seed_or_reproduction_format
            ) and not valid_replay_format_contract(
                execution.seed_or_reproduction_format
            ):
                issues.append(
                    f"{execution.property_id}: Seed or reproduction format must "
                    "declare a seed or exact-command replay mode"
                )
            if execution.evidence_destination != PROPERTY_TEST_EVIDENCE_DESTINATION:
                issues.append(
                    f"{execution.property_id}: Evidence destination must be exactly "
                    f"{PROPERTY_TEST_EVIDENCE_DESTINATION}"
                )

    technology_by_id = {decision.decision_id: decision for decision in technologies}
    architecture, architecture_issues = _derive_architecture_contract(
        text,
        design_revision,
        set(technology_by_id),
        authoritative_requirement_ids,
        required=required,
        grandfather_approved_v1=grandfather_approved_v1,
        architecture_disposition=coverage_contract.architecture_disposition,
    )
    support_issue_index = len(issues)
    (
        aws_implementation_decisions,
        design_support_bytes,
        aws_support_issues,
    ) = _current_design_support_records(
        text,
        technology_by_id,
        architecture,
    )
    for execution in executions:
        property_technology = technology_by_id.get(execution.framework_tech_id)
        if (
            property_technology is None
            or property_technology.concern != "PROPERTY_TESTING"
        ):
            issues.append(
                f"{execution.property_id}: Framework TECH ID must reference the PROPERTY_TESTING decision"
            )
            continue
        if technology_value_is_not_applicable(
            property_technology.selection
        ) or technology_value_is_not_applicable(property_technology.version_policy):
            issues.append(
                f"{property_technology.decision_id}: active property execution cannot "
                "use a NOT_APPLICABLE PROPERTY_TESTING selection or version policy"
            )
        elif not machine_comparable_property_version_policy(
            property_technology.version_policy
        ):
            issues.append(
                f"{property_technology.decision_id}: active property execution "
                "requires an EXACT, COMPATIBLE_MAJOR, or numeric MINIMUM version policy"
            )

    try:
        applicability_table = contract_table_in_section(
            text, PROPERTY_SPECIFICATION_HEADING, PROPERTY_APPLICABILITY_HEADERS
        )
        definition_table = contract_table_in_section(
            text, PROPERTY_SPECIFICATION_HEADING, PROPERTY_DEFINITION_HEADERS
        )
    except ValueError as exc:
        applicability_table = definition_table = None
        issues.append(f"Property-based testing specification: {exc}")
    if applicability_table is None:
        issues.append("Missing exact property applicability table")
    if definition_table is None:
        issues.append("Missing exact property definition table")

    applicable_property_ids: set[str] = set()
    applicable_requirements_by_property: dict[str, set[str]] = {}
    classified_requirement_ids: set[str] = set()
    if applicability_table is not None:
        seen_requirements: set[str] = set()
        for requirement_id, applicability, reason_or_ids in applicability_table.rows:
            if (
                unresolved(requirement_id)
                or unresolved(applicability)
                or unresolved(reason_or_ids)
            ):
                issues.append("Property applicability row contains unresolved cells")
                continue
            if requirement_id in seen_requirements:
                issues.append(
                    f"Duplicate property applicability requirement {requirement_id}"
                )
            seen_requirements.add(requirement_id)
            if STABLE_CONTRACT_ID.fullmatch(requirement_id) is None:
                issues.append(
                    f"Invalid property applicability requirement ID {requirement_id!r}"
                )
                continue
            classified_requirement_ids.add(requirement_id)
            if applicability == "APPLICABLE":
                try:
                    property_ids = _exact_property_ids(reason_or_ids)
                    applicable_property_ids.update(property_ids)
                    for property_id in property_ids:
                        applicable_requirements_by_property.setdefault(
                            property_id, set()
                        ).add(requirement_id)
                except ValueError as exc:
                    issues.append(f"{requirement_id}: {exc}")
            elif applicability == "NOT_APPLICABLE":
                if (
                    not explicit_value(reason_or_ids, allow_none=False)
                    or EVIDENCE_PLACEHOLDER_PATTERN.search(reason_or_ids) is not None
                ):
                    issues.append(
                        f"{requirement_id}: NOT_APPLICABLE requires a concrete reason"
                    )
            else:
                issues.append(
                    f"{requirement_id}: applicability must be APPLICABLE or NOT_APPLICABLE"
                )
        required_classifications = set(authoritative_requirement_ids)
        missing_classifications = sorted(
            required_classifications - classified_requirement_ids
        )
        unknown_classifications = sorted(
            classified_requirement_ids - required_classifications
        )
        if missing_classifications:
            issues.append(
                "Property applicability is missing current requirement IDs: "
                + ", ".join(missing_classifications)
            )
        if unknown_classifications:
            issues.append(
                "Property applicability references non-requirement IDs: "
                + ", ".join(unknown_classifications)
            )

    definitions: dict[str, tuple[str, ...]] = {}
    if definition_table is not None:
        for row in definition_table.rows:
            property_id = row[0]
            if PROPERTY_ID.fullmatch(property_id) is None:
                issues.append(f"Invalid property definition ID {property_id!r}")
                continue
            if property_id in definitions:
                issues.append(f"Duplicate property definition ID {property_id}")
            definitions[property_id] = row
            for header, value in zip(PROPERTY_DEFINITION_HEADERS[2:], row[2:]):
                if (
                    not explicit_value(value, allow_none=False)
                    or EVIDENCE_PLACEHOLDER_PATTERN.search(value) is not None
                ):
                    issues.append(
                        f"{property_id}: {header} must be concrete semantic content, "
                        "not a placeholder or sentinel"
                    )
    extra_definition_ids = sorted(set(definitions) - applicable_property_ids)
    if extra_definition_ids:
        issues.append(
            "Property definitions are not referenced as APPLICABLE: "
            + ", ".join(extra_definition_ids)
        )
    for property_id in sorted(applicable_property_ids):
        definition = definitions.get(property_id)
        if definition is None:
            issues.append(f"{property_id}: applicable property has no definition")
        elif any(unresolved(cell) for cell in definition):
            issues.append(
                f"{property_id}: applicable property definition is unresolved"
            )
        else:
            expected_requirement_ids = sorted(
                applicable_requirements_by_property.get(property_id, set())
            )
            expected_requirement_value = ", ".join(expected_requirement_ids)
            if definition[1] != expected_requirement_value:
                issues.append(
                    f"{property_id}: Requirement IDs must exactly match the "
                    "applicability table's current inverse mapping: "
                    f"{expected_requirement_value}"
                )

    execution_ids = {execution.property_id for execution in executions}
    for property_id in sorted(applicable_property_ids - execution_ids):
        issues.append(f"{property_id}: applicable property has no execution row")
    for property_id in sorted(execution_ids - applicable_property_ids):
        issues.append(f"{property_id}: execution row is not referenced as APPLICABLE")

    declared_property_ids = applicable_property_ids & set(definitions) & execution_ids
    declared_property_test_ids = declared_property_ids | example_ids

    issues.extend(architecture_issues)
    harness, harness_issues = derive_harness_contract(
        text,
        allowed_basis_ids | set(technology_by_id),
        required=required,
        grandfather_approved_v1=(
            grandfather_approved_v1 or architecture.grandfathered_v1
        ),
    )
    issues.extend(harness_issues)
    change_impact, change_impact_issues = change_impact_deriver(
        text,
        coverage_contract,
        allowed_basis_ids | set(technology_by_id),
        required=required and not grandfather_approved_v1,
    )
    if required:
        issues.extend(change_impact_issues)
    project_contract, project_contract_issues = _current_project_contract(
        text,
        requirements_contract,
        coverage_contract,
        authoritative_requirement_ids,
        allowed_basis_ids,
        technology_by_id,
        executions,
        harness,
        architecture,
        state_trigger_mapper,
        required=required,
        grandfathered=grandfather_approved_v1,
    )
    if required:
        issues.extend(project_contract_issues)
    diagram_contract, diagram_issues = _current_diagram_contract(
        text,
        architecture,
        requirements_contract,
        coverage_contract,
        project_contract,
        aws_implementation_decisions,
        technology_by_id,
        allowed_basis_ids | set(technology_by_id),
        required=required,
        grandfathered=grandfather_approved_v1,
    )
    if required:
        issues.extend(diagram_issues)
    bind_design_support = _bind_current_design_support(
        project_contract,
        diagram_contract,
        grandfathered=grandfather_approved_v1,
    )
    if bind_design_support:
        issues[support_issue_index:support_issue_index] = aws_support_issues

    if not project_contract.grandfathered_v4:
        issues.extend(example_issues)
        trace_issues = architecture_trace_declaration_issues(
            architecture,
            project_contract,
            declared_property_test_ids,
        )
        issues.extend(trace_issues)
        if trace_issues:
            architecture = replace(architecture, status="BLOCKED")

    canonical_sha256: str | None = None
    if (
        technology_table is not None
        and applicability_table is not None
        and definition_table is not None
        and execution_table is not None
        and (harness.canonical_bytes is not None or harness.grandfathered_v1)
        and (change_impact.canonical_bytes is not None or grandfather_approved_v1)
        and (
            project_contract.canonical_bytes is not None
            or project_contract.grandfathered_v4
        )
        and (example_table is not None or project_contract.grandfathered_v4)
        and (
            diagram_contract.canonical_bytes is not None
            or project_contract.grandfathered_v4
            or project_contract.grandfathered_v5
        )
        and (design_support_bytes is not None or not bind_design_support)
    ):
        architecture_bytes = architecture.canonical_bytes or b""
        harness_bytes = harness.canonical_bytes or b""
        change_impact_bytes = change_impact.canonical_bytes or b""
        project_contract_bytes = project_contract.canonical_bytes or b""
        diagram_contract_bytes = diagram_contract.canonical_bytes or b""
        canonical_sha256 = (
            "sha256:"
            + hashlib.sha256(
                architecture_bytes
                + harness_bytes
                + change_impact_bytes
                + project_contract_bytes
                + diagram_contract_bytes
                + technology_table.canonical_bytes
                + (example_table.canonical_bytes if example_table is not None else b"")
                + applicability_table.canonical_bytes
                + definition_table.canonical_bytes
                + execution_table.canonical_bytes
                + (
                    design_support_bytes
                    if bind_design_support and design_support_bytes is not None
                    else b""
                )
            ).hexdigest()
        )
    blocking_issues = [
        issue for issue in issues if not is_diagram_presentation_issue(issue)
    ]
    status = (
        "UNINITIALIZED"
        if both_missing and not required
        else "READY"
        if not blocking_issues
        else "BLOCKED"
    )
    return (
        DesignContract(
            schema_version=(
                max(4, architecture.schema_version)
                if project_contract.grandfathered_v4
                else 5
                if project_contract.grandfathered_v5
                else 6
                if project_contract.grandfathered_v6
                else 7
            ),
            status=status,
            design_revision=design_revision,
            technology_decisions=tuple(technologies),
            property_execution=tuple(executions),
            architecture=architecture,
            harness=harness,
            canonical_sha256=canonical_sha256,
            change_impact=change_impact,
            diagram_contract=diagram_contract,
            project_contract=project_contract,
        ),
        issues,
    )
