"""Pure Delivery evidence parsing and validation.

Canonical inputs are caller-supplied TASKS and VERIFY text plus an explicit
Design validation policy. Returned rows and failures preserve Fastlane 1.2.14.
This module performs no I/O, mutation, routing, approval, or authorization.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Any

from ..core.contracts import (
    ContractParseError,
    ContractTable,
    _parse_contract_table_lines,
    contract_table_after_heading,
    parse_task_completion_evidence_cells,
    split_markdown_table_row,
    without_fenced_code,
)
from ..core.ids import (
    EVIDENCE_PLACEHOLDER_PATTERN,
    clean_cell,
    explicit_timestamp,
    require_explicit_evidence_value,
    unresolved,
)
from .models import (
    DeliveryValidationPolicy,
    HarnessEvidenceRow,
    HarnessExecutionRow,
    InspectedTask,
    PropertyExecutionRow,
    PropertyTestEvidenceRow,
    TaskCompletionEvidenceRow,
)

HARNESS_HEADERS = (
    "Harness ID",
    "Layer",
    "Selected check or tool",
    "Trigger",
    "Basis IDs",
    "Exact command or API",
    "Evidence destination",
    "Required or conditional status",
)
HARNESS_ID = re.compile(r"HARNESS-\d{3,}")
HARNESS_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Harness ID",
    "Layer",
    "Basis IDs",
    "Exact command or API",
    "Artifact / environment",
    "Observed result",
    "Observed at",
    "Durable source",
    "Status",
)
HARNESS_PASS_STATUSES = {"LOCAL_PASS", "VERIFIED"}
HARNESS_FAILURE_STATUS = "FAILED"
COMMAND_PROSE = re.compile(
    r"^(?:(?:please\s+)?(?:run|execute|invoke|perform|use|enter|provide|"
    r"replace|record|describe|add|write|insert|verify|validate)\b|"
    r"(?:the\s+)?(?:exact\s+)?(?:command|tests?|testing|validation)\b)",
    re.IGNORECASE,
)
COMMAND_EXECUTABLE = re.compile(
    r"^(?:\"[^\"\r\n]+\"|'[^'\r\n]+'|[A-Za-z0-9_.$/\\:+@=-]+)(?:\s|$)"
)
PROPERTY_EXECUTION_PLACEHOLDER = re.compile(
    r"(?:<[^>]+>|(?<![A-Za-z0-9_])(?:TODO|TBD|TBC|UNKNOWN|UNASSIGNED|"
    r"NONE|PENDING|PLACEHOLDER|NOT[ _-]*STARTED|N/?A)(?![A-Za-z0-9_]))",
    re.IGNORECASE,
)

PROPERTY_EXECUTION_HEADERS = (
    "Property ID",
    "Framework TECH ID",
    "Exact command",
    "Run target/time bound",
    "Seed or reproduction format",
    "Evidence destination",
)
PROPERTY_TEST_EVIDENCE_HEADING = "## Property-based test evidence"
PROPERTY_TEST_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Task ID",
    "REQ / DES / AUTH",
    "Property ID",
    "Framework TECH ID",
    "Framework selection",
    "Observed exact version",
    "Exact command",
    "Observed run",
    "Replay seed or exact command",
    "Minimized counterexample",
    "Failure class / resolution",
    "Result",
    "Observed at",
    "Commit / worktree / artifact",
    "Durable source",
)
PROPERTY_TEST_RESULTS = {"NOT_STARTED", "PASS", "FAIL"}
PROPERTY_TEST_FAILURE_CLASSES = {
    "IMPLEMENTATION_DEFECT",
    "SPECIFICATION_AMBIGUITY_OR_DEFECT",
    "GENERATOR_OR_ORACLE_DEFECT",
    "ENVIRONMENT_DEFECT",
}
PROPERTY_TEST_EVIDENCE_DESTINATION = (
    "docs/project/VERIFY.md#property-based-test-evidence"
)
TASK_COMPLETION_EVIDENCE_STATUSES = {"LOCAL_PASS", "VERIFIED"}
LOCAL_EVIDENCE_ID = re.compile(r"\bEV-\d{4,}\b")
LOCAL_EVIDENCE_LIKE = re.compile(r"\b(?:EV|EVIDENCE)-[A-Za-z0-9._-]+\b", re.IGNORECASE)
EVIDENCE_PATTERN = re.compile(
    r"(?:\b(?:EV|EVIDENCE)-[A-Z0-9][A-Z0-9._-]*\b|"
    r"\bVERIFY\.md#[A-Za-z0-9._-]+\b|https?://\S+)",
    re.IGNORECASE,
)
VERIFICATION_MATRIX_HEADING = "## Verification matrix"
VERIFICATION_MATRIX_HEADERS = (
    "Evidence ID",
    "PRD / property IDs",
    "Task IDs",
    "Requirement or invariant",
    "Automated evidence",
    "AWS/manual evidence",
    "Artifact/environment",
    "Status",
)


def fenced_command_lines(text: str) -> list[str]:
    """Return exact non-empty lines inside Markdown code fences."""

    commands: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in text.splitlines():
        match = re.match(r"^[ \t]*(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            continue
        if fence_character is not None and line.strip():
            commands.append(line.strip())
    return commands


def normalize_harness_command(value: str) -> str:
    """Normalize insignificant whitespace without changing command tokens."""

    return " ".join(clean_cell(value).split())


def harness_rows_equivalent(
    observed: HarnessExecutionRow,
    expected: HarnessExecutionRow,
) -> bool:
    return (
        observed.harness_id == expected.harness_id
        and observed.layer == expected.layer
        and observed.selected_check == expected.selected_check
        and observed.trigger == expected.trigger
        and observed.basis_ids == expected.basis_ids
        and normalize_harness_command(observed.exact_command)
        == normalize_harness_command(expected.exact_command)
        and observed.evidence_destination == expected.evidence_destination
        and observed.requirement_status == expected.requirement_status
    )


def parse_harness_projection_rows(
    text: str,
    label: str,
) -> tuple[dict[str, HarnessExecutionRow], bool]:
    """SAFETY: parse one exact non-fenced Harness projection fail closed."""

    structural = without_fenced_code(text)
    raw_lines = text.splitlines()
    structural_lines = structural.splitlines()
    header_indexes = [
        index
        for index, line in enumerate(structural_lines)
        if split_markdown_table_row(line) == list(HARNESS_HEADERS)
    ]
    if len(header_indexes) > 1:
        raise ValueError(f"{label}: duplicate Harness projection tables")
    if not header_indexes:
        return {}, False
    header_index = header_indexes[0]
    if header_index + 1 >= len(raw_lines):
        raise ValueError(f"{label}: Harness projection has no separator")
    separators = split_markdown_table_row(raw_lines[header_index + 1])
    if (
        separators is None
        or len(separators) != len(HARNESS_HEADERS)
        or any(re.fullmatch(r":?-{3,}:?", cell) is None for cell in separators)
    ):
        raise ValueError(f"{label}: Harness projection separator is malformed")

    rows: dict[str, HarnessExecutionRow] = {}
    for raw_line, structural_line in zip(
        raw_lines[header_index + 2 :],
        structural_lines[header_index + 2 :],
    ):
        if not structural_line.strip().startswith("|"):
            break
        cells = split_markdown_table_row(raw_line)
        if cells is None or len(cells) != len(HARNESS_HEADERS):
            raise ValueError(
                f"{label}: Harness projection row must have exactly eight cells"
            )
        row = HarnessExecutionRow(*(clean_cell(cell) for cell in cells))
        if HARNESS_ID.fullmatch(row.harness_id) is None:
            raise ValueError(f"{label}: invalid Harness ID {row.harness_id!r}")
        if row.harness_id in rows:
            raise ValueError(f"{label}: duplicate Harness ID {row.harness_id}")
        if any(
            unresolved(value)
            for value in (
                row.layer,
                row.selected_check,
                row.trigger,
                row.basis_ids,
                row.exact_command,
                row.evidence_destination,
                row.requirement_status,
            )
        ):
            raise ValueError(f"{label}: {row.harness_id} projection is unresolved")
        if row.requirement_status != "REQUIRED":
            raise ValueError(
                f"{label}: {row.harness_id} projected status must be REQUIRED"
            )
        if (
            "\n" in row.exact_command
            or "\r" in row.exact_command
            or COMMAND_PROSE.match(row.exact_command) is not None
            or COMMAND_EXECUTABLE.match(row.exact_command) is None
        ):
            raise ValueError(
                f"{label}: {row.harness_id} Exact command or API must be concrete"
            )
        rows[row.harness_id] = row
    return rows, True


def parse_property_execution_rows(
    text: str,
    label: str,
) -> tuple[dict[str, PropertyExecutionRow], bool]:
    """SAFETY: parse one exact non-fenced property projection fail closed."""

    structural = without_fenced_code(text)
    raw_lines = text.splitlines()
    structural_lines = structural.splitlines()
    header_indexes = [
        index
        for index, line in enumerate(structural_lines)
        if split_markdown_table_row(line) == list(PROPERTY_EXECUTION_HEADERS)
    ]
    if len(header_indexes) > 1:
        raise ValueError(f"{label}: duplicate property execution projection tables")
    if not header_indexes:
        return {}, False
    header_index = header_indexes[0]
    if header_index + 1 >= len(raw_lines):
        raise ValueError(f"{label}: property execution projection has no separator")
    separators = split_markdown_table_row(raw_lines[header_index + 1])
    if (
        separators is None
        or len(separators) != len(PROPERTY_EXECUTION_HEADERS)
        or any(re.fullmatch(r":?-{3,}:?", cell) is None for cell in separators)
    ):
        raise ValueError(
            f"{label}: property execution projection separator is malformed"
        )

    rows: dict[str, PropertyExecutionRow] = {}
    for raw_line, structural_line in zip(
        raw_lines[header_index + 2 :],
        structural_lines[header_index + 2 :],
    ):
        if not structural_line.strip().startswith("|"):
            break
        cells = split_markdown_table_row(raw_line)
        if cells is None or len(cells) != len(PROPERTY_EXECUTION_HEADERS):
            raise ValueError(
                f"{label}: property execution projection row must have exactly six cells"
            )
        row = PropertyExecutionRow(*(clean_cell(cell) for cell in cells))
        if re.fullmatch(r"PROP-\d{3,}", row.property_id) is None:
            raise ValueError(
                f"{label}: invalid property execution ID {row.property_id!r}"
            )
        if re.fullmatch(r"TECH-\d{4}", row.framework_tech_id) is None:
            raise ValueError(
                f"{label}: {row.property_id} has invalid Framework TECH ID"
            )
        if any(
            not value or PROPERTY_EXECUTION_PLACEHOLDER.search(value) is not None
            for value in (
                row.exact_command,
                row.run_target_time_bound,
                row.seed_or_reproduction_format,
                row.evidence_destination,
            )
        ):
            raise ValueError(
                f"{label}: {row.property_id} property execution row is unresolved"
            )
        if (
            "\n" in row.exact_command
            or "\r" in row.exact_command
            or COMMAND_PROSE.match(row.exact_command) is not None
            or COMMAND_EXECUTABLE.match(row.exact_command) is None
        ):
            raise ValueError(
                f"{label}: {row.property_id} Exact command must be a concrete command"
            )
        if row.property_id in rows:
            raise ValueError(
                f"{label}: duplicate property execution ID {row.property_id}"
            )
        rows[row.property_id] = row
    return rows, True


def _task_subsection(task: Any, heading: str) -> str | None:
    structural = without_fenced_code(task.block)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*$", structural, re.MULTILINE)
    )
    if len(matches) != 1:
        return None
    start = matches[0].end()
    following = re.search(r"^####\s+", structural[start:], re.MULTILINE)
    end = start + following.start() if following else len(task.block)
    return task.block[start:end]


def validate_task_property_projection(
    task: Any,
    technology_refs: Sequence[str],
    approved_property_execution: Mapping[str, PropertyExecutionRow] | None,
) -> list[str]:
    """SAFETY: reject task property projections that diverge from Design."""

    errors: list[str] = []
    property_ids = re.findall(
        r"PROP-\d{3,}", clean_cell(task.metadata.get("Requirements", ""))
    )
    duplicates = sorted(
        property_id
        for property_id in set(property_ids)
        if property_ids.count(property_id) > 1
    )
    if duplicates:
        errors.append(
            f"{task.task_id}: duplicate PROP references in Requirements: "
            + ", ".join(duplicates)
        )
    validation = _task_subsection(task, "#### Validation")
    if validation is None:
        return errors
    try:
        projected, table_present = parse_property_execution_rows(
            validation, task.task_id
        )
    except ValueError as exc:
        errors.append(str(exc))
        return errors

    referenced = set(property_ids)
    projected_ids = set(projected)
    if not referenced:
        if table_present and projected_ids:
            errors.append(
                f"{task.task_id}: Validation contains unreferenced property "
                "execution rows: " + ", ".join(sorted(projected_ids))
            )
        return errors
    if not table_present:
        errors.append(
            f"{task.task_id}: Validation is missing the property execution projection"
        )
        return errors
    missing = sorted(referenced - projected_ids)
    extra = sorted(projected_ids - referenced)
    if missing:
        errors.append(
            f"{task.task_id}: missing property execution rows: " + ", ".join(missing)
        )
    if extra:
        errors.append(
            f"{task.task_id}: unreferenced property execution rows: " + ", ".join(extra)
        )
    if not missing and not extra and list(projected) != property_ids:
        errors.append(
            f"{task.task_id}: property execution projection order must exactly match "
            "Requirements"
        )
    if approved_property_execution is None:
        errors.append(
            f"{task.task_id}: approved PRD property execution contract is unavailable"
        )
        return errors

    commands = fenced_command_lines(validation)
    technology_ids = set(technology_refs)
    for property_id in sorted(referenced & projected_ids):
        observed = projected[property_id]
        expected = approved_property_execution.get(property_id)
        if expected is None:
            errors.append(
                f"{task.task_id}: {property_id} is not approved by the PRD property "
                "execution contract"
            )
            continue
        if observed != expected:
            errors.append(
                f"{task.task_id}: {property_id} property execution projection does not "
                "exactly match the approved PRD row"
            )
        if observed.framework_tech_id not in technology_ids:
            errors.append(
                f"{task.task_id}: {property_id} Framework TECH ID is missing from Design"
            )
        count = commands.count(observed.exact_command)
        if count != 1:
            errors.append(
                f"{task.task_id}: {property_id} Exact command must appear unchanged "
                f"exactly once in Validation code fences; found {count}"
            )
    return errors


def validate_harness_projections(
    tasks: Sequence[Any],
    approved_harness: Mapping[str, HarnessExecutionRow] | None,
    *,
    current_plan: bool,
) -> list[str]:
    """Require each approved Harness row in exactly one owning task."""

    errors: list[str] = []
    owners: dict[str, list[str]] = {}
    if approved_harness is None:
        return errors
    for task in tasks:
        contract_bound = task.status in {"READY", "IN_PROGRESS", "BLOCKED", "DONE"} or (
            task.status == "BACKLOG" and current_plan
        )
        if not contract_bound:
            continue
        validation = _task_subsection(task, "#### Validation")
        if validation is None:
            continue
        try:
            projected, _present = parse_harness_projection_rows(
                validation, task.task_id
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue
        commands = fenced_command_lines(validation)
        for harness_id, observed in projected.items():
            owners.setdefault(harness_id, []).append(task.task_id)
            expected = approved_harness.get(harness_id)
            if expected is None:
                errors.append(
                    f"{task.task_id}: {harness_id} is not a REQUIRED current PRD Harness row"
                )
                continue
            if not harness_rows_equivalent(observed, expected):
                errors.append(
                    f"{task.task_id}: {harness_id} projection does not match "
                    "the approved PRD Harness row after command normalization"
                )
            count = sum(
                normalize_harness_command(command)
                == normalize_harness_command(observed.exact_command)
                for command in commands
            )
            if count != 1:
                errors.append(
                    f"{task.task_id}: {harness_id} Exact command must appear "
                    f"unchanged exactly once in Validation code fences; found {count}"
                )
    for harness_id in sorted(approved_harness):
        task_ids = owners.get(harness_id, [])
        if len(task_ids) != 1:
            errors.append(
                f"{harness_id}: REQUIRED Harness row must have exactly one owning "
                f"task; found {len(task_ids)}"
            )
    return errors


def parse_harness_evidence(text: str) -> list[HarnessEvidenceRow]:
    """SAFETY: parse the append-only Harness evidence ledger fail closed."""

    masked = without_fenced_code(text)
    headings = list(
        re.finditer(r"^## Harness execution evidence[ \t]*$", masked, re.MULTILINE)
    )
    if len(headings) != 1:
        raise ValueError(
            "VERIFY.md requires exactly one `## Harness execution evidence` section"
        )
    heading = headings[0]
    following = re.search(r"^##\s+", masked[heading.end() :], re.MULTILINE)
    end = heading.end() + following.start() if following else len(masked)
    lines = masked[heading.end() : end].splitlines()
    header_indexes = [
        index
        for index, line in enumerate(lines)
        if split_markdown_table_row(line) == list(HARNESS_EVIDENCE_HEADERS)
    ]
    if len(header_indexes) != 1:
        raise ValueError(
            "VERIFY.md Harness execution evidence requires exactly one exact table header"
        )
    header_index = header_indexes[0]
    if header_index + 1 >= len(lines):
        raise ValueError("VERIFY.md Harness execution evidence has no separator")
    separators = split_markdown_table_row(lines[header_index + 1])
    if (
        separators is None
        or len(separators) != len(HARNESS_EVIDENCE_HEADERS)
        or any(re.fullmatch(r":?-{3,}:?", cell) is None for cell in separators)
    ):
        raise ValueError("VERIFY.md Harness execution evidence separator is malformed")
    rows: list[HarnessEvidenceRow] = []
    seen: set[str] = set()
    for line in lines[header_index + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = split_markdown_table_row(line)
        if cells is None or len(cells) != len(HARNESS_EVIDENCE_HEADERS):
            raise ValueError(
                "VERIFY.md Harness execution evidence row must have exactly ten cells"
            )
        row = HarnessEvidenceRow(*(clean_cell(cell) for cell in cells))
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError(
                f"VERIFY.md Harness evidence has invalid Evidence ID {row.evidence_id!r}"
            )
        if row.evidence_id in seen:
            raise ValueError(
                f"VERIFY.md Harness evidence has duplicate Evidence ID {row.evidence_id}"
            )
        seen.add(row.evidence_id)
        if HARNESS_ID.fullmatch(row.harness_id) is None:
            raise ValueError(
                f"VERIFY.md Harness evidence has invalid Harness ID {row.harness_id!r}"
            )
        rows.append(row)
    return rows


def _task_timestamp(value: str, label: str) -> datetime:
    normalized = clean_cell(value)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}: invalid ISO 8601 timestamp {normalized!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label}: timestamp must include a UTC offset")
    return parsed


def _task_durable_evidence_source(value: str, label: str) -> None:
    normalized = require_explicit_evidence_value(value, label)
    if re.fullmatch(r"VERIFY\.md#[A-Za-z0-9._-]+", normalized):
        return
    if re.fullmatch(r"git:[0-9a-fA-F]{7,64}", normalized, re.IGNORECASE):
        return
    candidate = re.sub(r"^artifact\s*:\s*", "", normalized, flags=re.IGNORECASE)
    if (
        re.fullmatch(
            r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+(?:#[A-Za-z0-9._-]+)?",
            candidate,
        )
        and ".." not in PurePosixPath(candidate.split("#", 1)[0]).parts
    ):
        return
    raise ValueError(f"{label} is not a durable source reference")


def validate_done_harness_evidence(
    verify_text: str,
    task: Any,
    snapshot: Any,
    approved_harness: Mapping[str, HarnessExecutionRow] | None,
) -> None:
    """SAFETY: bind DONE Harness claims to current passing evidence."""

    validation = _task_subsection(task, "#### Validation")
    if validation is None:
        return
    projected, present = parse_harness_projection_rows(validation, task.task_id)
    if not present or not projected:
        return
    if approved_harness is None:
        raise ValueError(
            f"{task.task_id}: approved PRD Harness contract is unavailable"
        )
    ledger = parse_harness_evidence(verify_text)
    task_evidence_ids = {
        match.group(0)
        for match in EVIDENCE_PATTERN.finditer(
            clean_cell(task.metadata.get("Evidence", ""))
        )
    }
    expected_basis = {
        task.task_id,
        snapshot.get("Requirements revision"),
        snapshot.get("Design revision"),
        snapshot.get("Construction authorization"),
    }
    for harness_id, projected_row in projected.items():
        expected = approved_harness.get(harness_id)
        if expected is None or not harness_rows_equivalent(projected_row, expected):
            raise ValueError(
                f"{task.task_id}: {harness_id} does not match the current PRD Harness contract"
            )
        observations = [row for row in ledger if row.harness_id == harness_id]
        if not observations:
            raise ValueError(
                f"{task.task_id}: {harness_id} requires current PASS evidence"
            )
        prior_time: datetime | None = None
        for row in observations:
            label = f"{task.task_id} Harness evidence {row.evidence_id}"
            if row.layer != expected.layer:
                raise ValueError(
                    f"{label} Layer does not match the approved Harness row"
                )
            if normalize_harness_command(
                row.exact_command
            ) != normalize_harness_command(expected.exact_command):
                raise ValueError(
                    f"{label} command/API does not match the approved Harness row"
                )
            observed_basis = set(
                re.findall(
                    r"(?:TASK|REQ|DES|AUTH)-\d{3,}|HARNESS-\d{3,}|"
                    r"TECH-\d{4}|PROP-\d{3,}",
                    row.basis_ids,
                )
            )
            if not expected_basis.issubset(observed_basis):
                raise ValueError(
                    f"{label} Basis IDs must include the current task and REQ/DES/AUTH"
                )
            require_explicit_evidence_value(
                row.artifact_environment, f"{label} Artifact / environment"
            )
            require_explicit_evidence_value(
                row.observed_result, f"{label} Observed result"
            )
            observed_time = _task_timestamp(row.observed_at, f"{label} Observed at")
            if prior_time is not None and observed_time <= prior_time:
                raise ValueError(
                    f"{task.task_id}: {harness_id} evidence must be append-only "
                    "in chronological order"
                )
            prior_time = observed_time
            _task_durable_evidence_source(row.durable_source, f"{label} Durable source")
            if row.status not in {HARNESS_FAILURE_STATUS, *HARNESS_PASS_STATUSES}:
                raise ValueError(
                    f"{label} Status must be FAILED, LOCAL_PASS, or VERIFIED"
                )
        latest = observations[-1]
        if latest.status not in HARNESS_PASS_STATUSES:
            raise ValueError(
                f"{task.task_id}: {harness_id} latest observation must be a current PASS"
            )
        if latest.evidence_id not in task_evidence_ids:
            raise ValueError(
                f"{task.task_id}: Evidence must cite latest {harness_id} result "
                f"{latest.evidence_id}"
            )


def parse_task_completion_evidence(
    text: str,
    *,
    task_surface_compatibility: bool = False,
) -> list[TaskCompletionEvidenceRow]:
    """CANONICALIZATION: parse unique ordered completion evidence rows."""

    try:
        parsed_rows = parse_task_completion_evidence_cells(text)
    except ContractParseError as exc:
        messages = (
            {
                "section_count": "VERIFY.md requires exactly one `## Task completion evidence` section",
                "header_count": "VERIFY.md Task completion evidence requires exactly one exact table header",
                "separator_missing": "VERIFY.md Task completion evidence table has no separator row",
                "separator_invalid": "VERIFY.md Task completion evidence has an invalid separator row",
                "row_width": "VERIFY.md Task completion evidence row must have exactly nine cells",
                "discontiguous_rows": "VERIFY.md Task completion evidence rows must form one contiguous table",
            }
            if task_surface_compatibility
            else {
                "section_count": "VERIFY.md requires exactly one Task completion evidence section",
                "header_count": "VERIFY.md requires one exact Task completion evidence table",
                "separator_missing": "VERIFY.md Task completion evidence separator is invalid",
                "separator_invalid": "VERIFY.md Task completion evidence separator is invalid",
                "row_width": "VERIFY.md Task completion evidence row must have nine cells",
                "discontiguous_rows": "VERIFY.md Task completion evidence rows must form one contiguous table",
            }
        )
        raise ValueError(
            messages.get(exc.reason, "VERIFY.md Task completion evidence is invalid")
        ) from exc
    rows: list[TaskCompletionEvidenceRow] = []
    for cells in parsed_rows:
        row = TaskCompletionEvidenceRow(*(clean_cell(cell) for cell in cells))
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError(
                "VERIFY.md Task completion evidence row has an invalid Evidence ID"
                if task_surface_compatibility
                else "VERIFY.md Task completion Evidence ID must be EV-nnnn"
            )
        rows.append(row)
    identifiers = [row.evidence_id for row in rows]
    if len(identifiers) != len(set(identifiers)):
        duplicates = sorted(
            identifier
            for identifier in set(identifiers)
            if identifiers.count(identifier) > 1
        )
        raise ValueError(
            "VERIFY.md Task completion Evidence IDs must be unique: "
            + ", ".join(duplicates)
            if task_surface_compatibility
            else "VERIFY.md Task completion Evidence IDs must be unique"
        )
    return rows


def _task_evidence_material(value: str, label: str) -> None:
    normalized = require_explicit_evidence_value(value, label)
    commit = re.fullmatch(r"`?[0-9a-fA-F]{7,64}`?", normalized) or re.search(
        r"\bcommit\s*[:=]\s*`?[0-9a-fA-F]{7,64}`?",
        normalized,
        re.IGNORECASE,
    )
    worktree_or_artifact = re.search(
        r"\b(?:worktree|artifact)\s*[:=]\s*`?[^`\s;,]+`?",
        normalized,
        re.IGNORECASE,
    )
    if commit is None and worktree_or_artifact is None:
        raise ValueError(
            f"{label} requires an explicit commit, worktree, or artifact reference"
        )


def validate_task_completion_evidence(text: str, task: Any) -> None:
    """SAFETY: validate task-facing DONE evidence with historical messages."""

    references = [
        match.group(0)
        for match in EVIDENCE_PATTERN.finditer(
            clean_cell(task.metadata.get("Evidence", ""))
        )
    ]
    local = [
        reference
        for reference in references
        if re.fullmatch(r"EV-\d{4,}", reference) is not None
    ]
    if not local:
        raise ValueError(
            f"{task.task_id}: DONE requires at least one exact local Evidence "
            "reference in EV-nnnn form"
        )
    if len(local) != len(set(local)):
        raise ValueError(
            f"{task.task_id}: DONE has duplicate local Evidence references"
        )
    rows = parse_task_completion_evidence(
        text,
        task_surface_compatibility=True,
    )
    for evidence_id in local:
        matching = [row for row in rows if row.evidence_id == evidence_id]
        if len(matching) != 1:
            raise ValueError(
                f"{task.task_id}: Evidence is not recorded in VERIFY.md: {evidence_id}"
            )
        row = matching[0]
        if row.task_id != task.task_id:
            raise ValueError(
                f"{task.task_id}: Evidence row names the wrong task {row.task_id!r}"
            )
        label = f"{task.task_id} Evidence {row.evidence_id}"
        require_explicit_evidence_value(
            row.command_or_observation, f"{label} Command or observation"
        )
        require_explicit_evidence_value(row.result, f"{label} Result")
        require_explicit_evidence_value(row.actor, f"{label} Actor")
        _task_timestamp(row.observed_at, f"{label} Observed at")
        _task_evidence_material(
            row.commit_worktree_artifact,
            f"{label} Commit / worktree / artifact",
        )
        _task_durable_evidence_source(
            row.durable_source,
            f"{label} Durable source",
        )
        if row.status not in TASK_COMPLETION_EVIDENCE_STATUSES:
            raise ValueError(f"{label} Status must be LOCAL_PASS or VERIFIED")


def require_durable_evidence_source(value: str, label: str) -> str:
    """SAFETY: require one safe durable evidence reference."""

    source = require_explicit_evidence_value(value, label)
    candidate = re.sub(r"^artifact\s*:\s*", "", source, flags=re.IGNORECASE)
    candidate_path = candidate.split("#", 1)[0]
    path_source = bool(
        re.fullmatch(
            r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+(?:#[A-Za-z0-9._-]+)?",
            candidate,
        )
        and ".." not in PurePosixPath(candidate_path).parts
    )
    if (
        re.fullmatch(r"VERIFY\.md#[A-Za-z0-9._-]+", source) is None
        and re.fullmatch(r"git:[0-9a-fA-F]{7,64}", source, re.IGNORECASE) is None
        and re.fullmatch(r"(?:https?|s3)://\S+", source, re.IGNORECASE) is None
        and not path_source
    ):
        raise ValueError(f"{label} is not a local durable reference")
    return source


def _validate_completion_evidence_row(
    task: InspectedTask,
    reference: str,
    rows: list[TaskCompletionEvidenceRow],
) -> None:
    """SAFETY: validate one exact durable row without weakening DONE evidence."""

    matching = [row for row in rows if row.evidence_id == reference]
    if len(matching) != 1:
        raise ValueError(
            f"{task.task_id}: Evidence is not recorded in VERIFY.md: {reference}"
        )
    row = matching[0]
    if row.task_id != task.task_id:
        raise ValueError(
            f"{task.task_id}: Evidence row names the wrong task {row.task_id!r}"
        )
    label = f"{task.task_id} Evidence {row.evidence_id}"
    require_explicit_evidence_value(row.command_or_observation, f"{label} command")
    require_explicit_evidence_value(row.result, f"{label} result")
    require_explicit_evidence_value(row.actor, f"{label} actor")
    if not explicit_timestamp(row.observed_at):
        raise ValueError(f"{label} observed time must be ISO 8601 with timezone")
    material = require_explicit_evidence_value(
        row.commit_worktree_artifact, f"{label} commit/worktree/artifact"
    )
    if (
        re.search(r"\b[0-9a-fA-F]{7,64}\b", material) is None
        and re.search(r"\b(?:worktree|artifact)\s*[:=]\s*\S+", material, re.IGNORECASE)
        is None
    ):
        raise ValueError(f"{label} requires an explicit commit, worktree, or artifact")
    require_durable_evidence_source(row.durable_source, f"{label} durable source")
    if row.status not in TASK_COMPLETION_EVIDENCE_STATUSES:
        raise ValueError(f"{label} status must be LOCAL_PASS or VERIFIED")


def validate_done_evidence(verify_text: str | None, task: InspectedTask) -> None:
    """SAFETY: require every DONE citation to resolve to one durable passing row."""

    evidence = clean_cell(task.metadata.get("Evidence", ""))
    references = [match.group(0) for match in EVIDENCE_PATTERN.finditer(evidence)]
    local = [
        reference for reference in references if re.fullmatch(r"EV-\d{4,}", reference)
    ]
    invalid_local = [
        reference
        for reference in references
        if LOCAL_EVIDENCE_LIKE.fullmatch(reference) is not None
        and re.fullmatch(r"EV-\d{4,}", reference) is None
    ]
    if invalid_local:
        raise ValueError(
            f"{task.task_id}: invalid local Evidence ID: {', '.join(invalid_local)}"
        )
    if not local:
        raise ValueError(
            f"{task.task_id}: DONE requires at least one local Evidence reference"
        )
    if len(local) != len(set(local)):
        raise ValueError(f"{task.task_id}: local Evidence references must be unique")
    if verify_text is None:
        raise ValueError(f"{task.task_id}: local Evidence requires VERIFY.md")
    rows = parse_task_completion_evidence(verify_text)
    for reference in local:
        _validate_completion_evidence_row(task, reference, rows)


def task_property_execution_table(
    validation_section: str, task_id: str
) -> ContractTable | None:
    """CANONICALIZATION: return the one exact visible property projection."""

    structural = without_fenced_code(validation_section)
    source_lines = validation_section.splitlines()
    structural_lines = structural.splitlines()
    matches: list[ContractTable] = []
    index = 0
    while index < len(source_lines):
        if not structural_lines[index].strip().startswith("|"):
            index += 1
            continue
        raw_lines: list[str] = []
        while index < len(source_lines) and structural_lines[index].strip().startswith(
            "|"
        ):
            raw_lines.append(source_lines[index])
            index += 1
        header = split_markdown_table_row(raw_lines[0])
        if header is None or not header or clean_cell(header[0]) != "Property ID":
            continue
        try:
            matches.append(
                _parse_contract_table_lines(raw_lines, PROPERTY_EXECUTION_HEADERS)
            )
        except ValueError as exc:
            raise ValueError(f"{task_id}: property execution projection {exc}") from exc
    if len(matches) > 1:
        raise ValueError(
            f"{task_id}: Validation must contain exactly one property execution projection"
        )
    return matches[0] if matches else None


def validate_task_property_execution_projection(
    validation_section: str,
    task_id: str,
    requirements: str,
    technology_refs: list[str],
    property_execution_by_id: Mapping[str, Any] | None,
    policy: DeliveryValidationPolicy,
) -> None:
    """SAFETY: require an exact PRD projection and command for each property."""

    property_ids = policy.property_id.findall(clean_cell(requirements))
    if len(property_ids) != len(set(property_ids)):
        raise ValueError(f"{task_id}: Requirements contains duplicate PROP IDs")
    table = task_property_execution_table(validation_section, task_id)
    if not property_ids:
        if table is not None:
            raise ValueError(
                f"{task_id}: Validation has a property execution projection without a PROP requirement"
            )
        return
    if property_execution_by_id is None:
        raise ValueError(
            f"{task_id}: property execution contract is unavailable for PROP validation"
        )
    unknown = [item for item in property_ids if item not in property_execution_by_id]
    if unknown:
        raise ValueError(
            f"{task_id}: Requirements references unknown PROP IDs: "
            + ", ".join(unknown)
        )
    if table is None:
        raise ValueError(
            f"{task_id}: Validation requires the exact property execution projection"
        )
    projected_ids = [row[0] for row in table.rows]
    if projected_ids != property_ids or len(projected_ids) != len(set(projected_ids)):
        raise ValueError(
            f"{task_id}: property execution projection IDs must exactly match Requirements"
        )
    for row in table.rows:
        expected = property_execution_by_id[row[0]]
        if not policy.valid_property_execution_command(expected.exact_command):
            raise ValueError(
                f"{task_id}: {row[0]} Exact command is not an executable local command"
            )
        if not policy.valid_property_execution_command(row[2]):
            raise ValueError(
                f"{task_id}: projected {row[0]} Exact command is not an executable "
                "local command"
            )
        expected_row = (
            expected.property_id,
            expected.framework_tech_id,
            expected.exact_command,
            expected.run_target_time_bound,
            expected.seed_or_reproduction_format,
            expected.evidence_destination,
        )
        if row != expected_row:
            raise ValueError(
                f"{task_id}: property execution projection for {row[0]} does not match the PRD contract"
            )
        if expected.framework_tech_id not in technology_refs:
            raise ValueError(
                f"{task_id}: Design must reference {expected.framework_tech_id} for {row[0]}"
            )
    commands = policy.validation_commands(validation_section, task_id)
    for command in dict.fromkeys(
        property_execution_by_id[item].exact_command for item in property_ids
    ):
        if commands.count(command) != 1:
            raise ValueError(
                f"{task_id}: property command {command!r} must appear exactly once in Validation"
            )


def parse_property_test_evidence(
    text: str, policy: DeliveryValidationPolicy
) -> list[PropertyTestEvidenceRow]:
    """CANONICALIZATION: parse exact durable property-test evidence rows."""

    table = contract_table_after_heading(
        text,
        PROPERTY_TEST_EVIDENCE_HEADING,
        PROPERTY_TEST_EVIDENCE_HEADERS,
    )
    if table is None:
        raise ValueError(
            "VERIFY.md requires exactly one Property-based test evidence section"
        )
    rows: list[PropertyTestEvidenceRow] = []
    seen_evidence_ids: set[str] = set()
    for cells in table.rows:
        row = PropertyTestEvidenceRow(*cells)
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError(
                "VERIFY.md Property-based test evidence Evidence ID must be EV-nnnn"
            )
        if row.evidence_id in seen_evidence_ids:
            raise ValueError(
                "VERIFY.md Property-based test evidence Evidence IDs must be unique"
            )
        seen_evidence_ids.add(row.evidence_id)
        if policy.property_id.fullmatch(row.property_id) is None:
            raise ValueError(
                "VERIFY.md Property-based test evidence Property ID must be PROP-nnn"
            )
        if row.result not in PROPERTY_TEST_RESULTS:
            raise ValueError(
                f"{row.property_id}: property-test Result must be NOT_STARTED, PASS, or FAIL"
            )
        rows.append(row)
    return rows


def parse_observed_property_run(value: str) -> tuple[int, Decimal]:
    """Parse one exact observed case count and elapsed duration."""

    match = re.fullmatch(
        r"CASES: (?P<cases>[1-9]\d*); "
        r"ELAPSED_SECONDS: (?P<seconds>\d+(?:\.\d+)?)",
        clean_cell(value),
    )
    if match is None:
        raise ValueError(
            "Observed run must be CASES: <positive integer>; "
            "ELAPSED_SECONDS: <nonnegative number>"
        )
    elapsed = Decimal(match.group("seconds"))
    if not elapsed.is_finite() or elapsed < 0:
        raise ValueError("ELAPSED_SECONDS must be finite and nonnegative")
    return int(match.group("cases")), elapsed


def technology_version_policy_allows(
    version_policy: str,
    observed: str,
    policy: DeliveryValidationPolicy,
) -> bool:
    """SAFETY: check an observed version against the approved policy grammar."""

    if policy.technology_contract_value_is_unresolved(
        version_policy
    ) or policy.technology_contract_value_is_unresolved(observed):
        return False
    if version_policy.startswith("EXACT: "):
        return observed == version_policy.removeprefix("EXACT: ")
    observed_parts = policy.parsed_numeric_version(observed)
    if observed_parts is None:
        return False
    if version_policy.startswith("COMPATIBLE_MAJOR: "):
        return observed_parts[0] == int(
            version_policy.removeprefix("COMPATIBLE_MAJOR: ")
        )
    if version_policy.startswith("MINIMUM: "):
        minimum = policy.parsed_numeric_version(
            version_policy.removeprefix("MINIMUM: ")
        )
        if minimum is None:
            return False
        width = max(len(observed_parts), len(minimum))
        return observed_parts + (0,) * (width - len(observed_parts)) >= minimum + (
            0,
        ) * (width - len(minimum))
    return False


def replay_evidence_matches_contract(
    approved_format: str,
    observed_replay: str,
    exact_command: str,
) -> bool:
    """SAFETY: bind replay evidence to the approved reproduction contract."""

    approved = clean_cell(approved_format)
    observed = clean_cell(observed_replay)
    if unresolved(approved) or unresolved(observed):
        return False
    lowered_approved = approved.casefold()
    lowered_observed = observed.casefold()
    if EVIDENCE_PLACEHOLDER_PATTERN.search(observed) is not None or re.search(
        r"\b(?:unavailable|missing|not[ _-]*recorded|not[ _-]*captured)\b",
        lowered_observed,
    ):
        return False
    if "seed" in lowered_approved:
        match = re.fullmatch(
            r"(?:seed\s*[:=]\s*|.*(?:^|\s)--seed(?:=|\s+))(?P<seed>\S+)",
            observed,
            re.IGNORECASE,
        )
        if match is None:
            return False
        seed = match.group("seed").strip("'\"")
        if not seed or EVIDENCE_PLACEHOLDER_PATTERN.fullmatch(seed) is not None:
            return False
        if "integer" in lowered_approved and re.fullmatch(r"\d+", seed) is None:
            return False
        return True
    if "command" in lowered_approved:
        return observed == exact_command
    return observed == approved


def evidence_timestamp(value: str, label: str) -> datetime:
    if not explicit_timestamp(value):
        raise ValueError(f"{label} must be ISO 8601 with timezone")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_done_property_evidence(
    rows: list[PropertyTestEvidenceRow],
    task: InspectedTask,
    snapshot: dict[str, str],
    expected: Any,
    technology: Any,
    completion_rows: list[TaskCompletionEvidenceRow],
    policy: DeliveryValidationPolicy,
    *,
    require_done_pass: bool = True,
) -> None:
    """SAFETY: preserve property failures and require a latest passing DONE run."""

    task_id = task.task_id
    if expected.evidence_destination != PROPERTY_TEST_EVIDENCE_DESTINATION:
        raise ValueError(
            f"{task_id}: {expected.property_id} PRD evidence destination does not "
            "identify the exact VERIFY.md property evidence section"
        )
    observed = [
        row
        for row in rows
        if row.task_id == task_id
        and row.property_id == expected.property_id
        and row.result in {"PASS", "FAIL"}
    ]
    if not observed and require_done_pass:
        raise ValueError(
            f"{task_id}: DONE {expected.property_id} requires observed property-test evidence"
        )
    if not observed:
        return
    expected_basis = (
        f"{snapshot.get('Requirements revision', '')} / "
        f"{snapshot.get('Design revision', '')} / "
        f"{snapshot.get('Construction authorization', '')}"
    )
    completion_by_id = {row.evidence_id: row for row in completion_rows}
    task_evidence_ids = set(
        LOCAL_EVIDENCE_ID.findall(clean_cell(task.metadata.get("Evidence", "")))
    )
    passing = False
    timestamps: list[tuple[datetime, PropertyTestEvidenceRow]] = []
    for index, row in enumerate(observed, start=1):
        label = f"{task_id} {expected.property_id} evidence row {index}"
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError(f"{label} Evidence ID must be EV-nnnn")
        if row.requirements_design_authorization != expected_basis:
            raise ValueError(f"{label} REQ / DES / AUTH is not current")
        if row.framework_tech_id != expected.framework_tech_id:
            raise ValueError(
                f"{label} Framework TECH ID does not match the current PRD property contract"
            )
        if row.framework_selection != technology.selection:
            raise ValueError(
                f"{label} Framework selection does not match {technology.decision_id}"
            )
        observed_version = require_explicit_evidence_value(
            row.observed_exact_version,
            f"{label} observed exact version",
        )
        if not technology_version_policy_allows(
            technology.version_policy, observed_version, policy
        ):
            raise ValueError(
                f"{label} observed exact version does not satisfy "
                f"{technology.version_policy}"
            )
        if row.exact_command != expected.exact_command:
            raise ValueError(
                f"{label} Exact command does not match the current PRD property contract"
            )
        try:
            observed_cases, observed_seconds = parse_observed_property_run(
                row.observed_run
            )
            minimum_cases, maximum_seconds = policy.parse_property_run_target(
                expected.run_target_time_bound
            )
        except ValueError as exc:
            raise ValueError(f"{label} {exc}") from exc
        replay = require_explicit_evidence_value(
            row.replay_seed_or_exact_command,
            f"{label} replay seed or exact command",
        )
        if not replay_evidence_matches_contract(
            expected.seed_or_reproduction_format,
            replay,
            expected.exact_command,
        ):
            raise ValueError(
                f"{label} replay evidence does not match the approved PRD "
                "Seed or reproduction format"
            )
        observed_at = evidence_timestamp(row.observed_at, f"{label} Observed at")
        timestamps.append((observed_at, row))
        material = require_explicit_evidence_value(
            row.commit_worktree_artifact,
            f"{label} commit/worktree/artifact",
        )
        require_durable_evidence_source(row.durable_source, f"{label} durable source")
        completion = completion_by_id.get(row.evidence_id)
        if completion is None:
            raise ValueError(
                f"{label} Evidence ID is missing from Task completion evidence"
            )
        if (
            completion.task_id != task_id
            or completion.command_or_observation != row.exact_command
            or completion.observed_at != row.observed_at
            or completion.commit_worktree_artifact != material
            or completion.durable_source != row.durable_source
        ):
            raise ValueError(
                f"{label} does not match its Task completion evidence binding"
            )
        require_explicit_evidence_value(
            completion.result,
            f"{label} Task completion result",
        )
        require_explicit_evidence_value(
            completion.actor,
            f"{label} Task completion actor",
        )
        if row.result == "PASS":
            passing = True
            if require_done_pass and row.evidence_id not in task_evidence_ids:
                raise ValueError(
                    f"{label} PASS Evidence ID is not cited by the DONE task"
                )
            if completion.status not in TASK_COMPLETION_EVIDENCE_STATUSES:
                raise ValueError(
                    f"{label} PASS completion status must be LOCAL_PASS or VERIFIED"
                )
            if minimum_cases is not None and observed_cases < minimum_cases:
                raise ValueError(
                    f"{label} observed cases do not meet MIN_CASES: {minimum_cases}"
                )
            if maximum_seconds is not None and observed_seconds > maximum_seconds:
                raise ValueError(
                    f"{label} elapsed time exceeds MAX_SECONDS: {maximum_seconds}"
                )
            if row.minimized_counterexample != "NONE":
                raise ValueError(
                    f"{label} PASS must record Minimized counterexample as NONE"
                )
            if row.failure_class_resolution != "NONE":
                raise ValueError(
                    f"{label} PASS must record Failure class / resolution as NONE"
                )
            continue
        if completion.status != "FAILED":
            raise ValueError(f"{label} FAIL completion status must be FAILED")
        counterexample = require_explicit_evidence_value(
            row.minimized_counterexample,
            f"{label} minimized counterexample",
        )
        if counterexample == "NONE":
            raise ValueError(f"{label} FAIL requires a minimized counterexample")
        failure_match = re.fullmatch(
            "(?P<class>"
            + "|".join(sorted(PROPERTY_TEST_FAILURE_CLASSES))
            + r") — (?P<resolution>.+)",
            row.failure_class_resolution,
        )
        if failure_match is None:
            raise ValueError(
                f"{label} FAIL requires one supported failure class and a concrete "
                "resolution separated by an em dash"
            )
        try:
            require_explicit_evidence_value(
                failure_match.group("resolution"),
                f"{label} failure resolution",
            )
        except ValueError as exc:
            raise ValueError(
                f"{label} FAIL requires one supported failure class and a concrete "
                "resolution separated by an em dash"
            ) from exc
    if len({stamp for stamp, _row in timestamps}) != len(timestamps):
        raise ValueError(
            f"{task_id}: {expected.property_id} observed timestamps must be unique"
        )
    if require_done_pass and not passing:
        raise ValueError(
            f"{task_id}: DONE {expected.property_id} requires preserved failure rows "
            "and a later PASS row"
        )
    latest = max(timestamps, key=lambda item: item[0])[1]
    if require_done_pass and latest.result != "PASS":
        raise ValueError(
            f"{task_id}: DONE {expected.property_id} requires the latest observed "
            "property-test result to be PASS"
        )


def parse_verification_matrix(text: str) -> list[dict[str, str]]:
    """Parse the canonical release acceptance registry."""

    table = contract_table_after_heading(
        text, VERIFICATION_MATRIX_HEADING, VERIFICATION_MATRIX_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


__all__ = (
    "EVIDENCE_PATTERN",
    "HARNESS_HEADERS",
    "HARNESS_EVIDENCE_HEADERS",
    "PROPERTY_EXECUTION_HEADERS",
    "PROPERTY_TEST_EVIDENCE_HEADING",
    "PROPERTY_TEST_EVIDENCE_DESTINATION",
    "TASK_COMPLETION_EVIDENCE_STATUSES",
    "evidence_timestamp",
    "fenced_command_lines",
    "harness_rows_equivalent",
    "normalize_harness_command",
    "parse_harness_projection_rows",
    "parse_harness_evidence",
    "parse_property_execution_rows",
    "parse_observed_property_run",
    "parse_property_test_evidence",
    "parse_task_completion_evidence",
    "parse_verification_matrix",
    "replay_evidence_matches_contract",
    "require_durable_evidence_source",
    "require_explicit_evidence_value",
    "task_property_execution_table",
    "technology_version_policy_allows",
    "validate_done_evidence",
    "validate_done_harness_evidence",
    "validate_done_property_evidence",
    "validate_harness_projections",
    "validate_task_property_projection",
    "validate_task_completion_evidence",
    "validate_task_property_execution_projection",
)
