"""Pure Delivery evidence parsing and validation.

Canonical inputs are caller-supplied TASKS and VERIFY text plus an explicit
Design validation policy. Returned rows and failures preserve Fastlane 1.2.14.
This module performs no I/O, mutation, routing, approval, or authorization.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
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
    unresolved,
)
from .models import (
    DeliveryValidationPolicy,
    InspectedTask,
    PropertyTestEvidenceRow,
    TaskCompletionEvidenceRow,
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


def parse_task_completion_evidence(text: str) -> list[TaskCompletionEvidenceRow]:
    """CANONICALIZATION: parse unique ordered completion evidence rows."""

    try:
        parsed_rows = parse_task_completion_evidence_cells(text)
    except ContractParseError as exc:
        messages = {
            "section_count": "VERIFY.md requires exactly one Task completion evidence section",
            "header_count": "VERIFY.md requires one exact Task completion evidence table",
            "separator_missing": "VERIFY.md Task completion evidence separator is invalid",
            "separator_invalid": "VERIFY.md Task completion evidence separator is invalid",
            "row_width": "VERIFY.md Task completion evidence row must have nine cells",
            "discontiguous_rows": "VERIFY.md Task completion evidence rows must form one contiguous table",
        }
        raise ValueError(
            messages.get(exc.reason, "VERIFY.md Task completion evidence is invalid")
        ) from exc
    rows: list[TaskCompletionEvidenceRow] = []
    for cells in parsed_rows:
        row = TaskCompletionEvidenceRow(*(clean_cell(cell) for cell in cells))
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError("VERIFY.md Task completion Evidence ID must be EV-nnnn")
        rows.append(row)
    identifiers = [row.evidence_id for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("VERIFY.md Task completion Evidence IDs must be unique")
    return rows


def require_explicit_evidence_value(value: str, label: str) -> str:
    cleaned = clean_cell(value)
    if (
        not cleaned
        or any(character in cleaned for character in "\r\n")
        or EVIDENCE_PLACEHOLDER_PATTERN.search(cleaned) is not None
    ):
        raise ValueError(f"{label} is unresolved or placeholder evidence")
    return cleaned


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
    "PROPERTY_EXECUTION_HEADERS",
    "PROPERTY_TEST_EVIDENCE_HEADING",
    "PROPERTY_TEST_EVIDENCE_DESTINATION",
    "TASK_COMPLETION_EVIDENCE_STATUSES",
    "evidence_timestamp",
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
    "validate_done_property_evidence",
    "validate_task_property_execution_projection",
)
