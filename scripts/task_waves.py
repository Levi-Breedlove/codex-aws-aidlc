#!/usr/bin/env python3
"""Validate, claim, and safely group Fastlane construction tasks."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    from fastlane_process import resolve_trusted_git
except ModuleNotFoundError:  # pragma: no cover - package-style test import
    from scripts.fastlane_process import resolve_trusted_git

try:
    from fastlane_stdio import configure_utf8_standard_streams
except ModuleNotFoundError:  # pragma: no cover - package-style test import
    from scripts.fastlane_stdio import configure_utf8_standard_streams

try:
    from fastlane_document_summaries import strip_generated_summary
except ModuleNotFoundError:  # pragma: no cover - package-style test import
    from scripts.fastlane_document_summaries import strip_generated_summary

try:
    from fastlane_contracts import (
        ContractParseError,
        external_targets_overlap,
        parse_checkpoint_cells,
        parse_checkpoint_git_receipt_value,
        parse_task_completion_evidence_cells,
        path_boundaries_overlap,
        path_boundary_base,
        path_boundary_contains,
        split_markdown_table_row,
        without_fenced_code,
    )
except ModuleNotFoundError:  # pragma: no cover - package-style test import
    from scripts.fastlane_contracts import (
        ContractParseError,
        external_targets_overlap,
        parse_checkpoint_cells,
        parse_checkpoint_git_receipt_value,
        parse_task_completion_evidence_cells,
        path_boundaries_overlap,
        path_boundary_base,
        path_boundary_contains,
        split_markdown_table_row,
        without_fenced_code,
    )

from pathlib import Path, PurePosixPath
from typing import Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl

TASK_HEADER = re.compile(r"^###\s+(TASK-\d+)\s+[—-]\s+(.+?)\s*$", re.MULTILINE)
REQUIRED_METADATA = (
    "Status",
    "Requirements",
    "Design",
    "Authorization",
    "Depends on",
    "Dependency waivers",
    "Owner",
    "Run ID",
    "Risk",
    "Write set",
    "External state",
    "AWS mode",
    "Attempt budget",
    "Attempts used",
    "Evidence",
    "Blocker",
    "Skip record",
    "GitHub issue",
    "Last checkpoint",
    "Last updated",
)
META_LINE = re.compile(
    rf"^- (?P<key>{'|'.join(re.escape(key) for key in REQUIRED_METADATA)}):"
    r"\s*(?P<value>.+?)\s*$",
    re.MULTILINE,
)
SNAPSHOT_FIELDS = (
    "Task-plan revision",
    "Task-plan state",
    "Requirements revision",
    "Design revision",
    "Construction authorization",
    "Gate B state",
    "Run state",
    "Active run ID",
    "Baseline commit",
    "Protected dirty paths",
    "Coordinator",
    "Maximum workers",
    "Current wave",
    "Last checkpoint",
    "Last known-green commit",
    "Next safe action",
)
ALLOWED_STATUSES = {
    "BACKLOG",
    "READY",
    "IN_PROGRESS",
    "BLOCKED",
    "DONE",
    "SKIPPED",
}
ALLOWED_TRANSITIONS = {
    "BACKLOG": {"READY", "BLOCKED", "SKIPPED"},
    "READY": {"BACKLOG", "IN_PROGRESS", "BLOCKED", "SKIPPED"},
    "IN_PROGRESS": {"BLOCKED", "DONE"},
    "BLOCKED": {"BACKLOG", "READY", "SKIPPED"},
    "DONE": set(),
    "SKIPPED": set(),
}
ALLOWED_AWS_MODES = {"NONE", "DOCS_ONLY"}
ALLOWED_RUN_STATES = {"NOT_STARTED", "RUNNING", "PAUSED", "BLOCKED", "COMPLETE"}
ALLOWED_PLAN_STATES = {"UNINITIALIZED", "CURRENT", "STALE"}
UNRESOLVED = {"", "TODO", "TBD", "UNKNOWN", "UNASSIGNED"}
CONTROL_PATHS = {
    "AGENTS.md",
    "docs/project/BUGFIX.md",
    "docs/project/PRD.md",
    "docs/project/TASKS.md",
    "docs/project/VERIFY.md",
    "docs/project/RUNBOOK.md",
    "bootstrap.manifest.json",
    "bootstrap.yaml",
    "bootstrap.py",
    "scripts/bootstrap_doctor.py",
    "scripts/task_waves.py",
}
CONTROL_FILENAMES = {
    "agents.md",
    "bugfix.md",
    "prd.md",
    "runbook.md",
    "tasks.md",
    "verify.md",
}
CANONICAL_TASKS_PATH = PurePosixPath("docs/project/TASKS.md")
RUN_ID_PATTERN = re.compile(r"RUN-\d{4,}")
CHECKPOINT_PATTERN = re.compile(r"CP-\d{4,}")
OWNER_DECISION_PATTERN = re.compile(r"OWNER-DECISION-\d+")
TASK_EVIDENCE_ID_PATTERN = re.compile(r"EV-\d{4,}")
DESIGN_TRACE_PATTERN = re.compile(
    r"^(?P<design>DES-\d{4}); TECH: "
    r"(?:(?P<none>NONE — no technology/toolchain impact)|"
    r"(?P<technologies>TECH-\d{4}(?:, TECH-\d{4})*))$"
)
PROPERTY_ID_PATTERN = re.compile(r"PROP-\d{3,}")
PROPERTY_EXECUTION_HEADERS = (
    "Property ID",
    "Framework TECH ID",
    "Exact command",
    "Run target/time bound",
    "Seed or reproduction format",
    "Evidence destination",
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
HARNESS_ID_PATTERN = re.compile(r"HARNESS-\d{3,}")
HARNESS_PASS_STATUSES = {"LOCAL_PASS", "VERIFIED"}
HARNESS_FAILURE_STATUS = "FAILED"
WAVE_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])WAVE-\d{3,}(?![A-Za-z0-9_-])")
SPIKE_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])SPIKE-\d{3,}(?![A-Za-z0-9_-])")
CONTRACT_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+(?![A-Za-z0-9_-])"
)
PROPERTY_EXECUTION_PLACEHOLDER_PATTERN = re.compile(
    r"(?:<[^>]+>|(?<![A-Za-z0-9_])(?:TODO|TBD|TBC|UNKNOWN|UNASSIGNED|"
    r"NONE|PENDING|PLACEHOLDER|NOT[ _-]*STARTED|N/?A)(?![A-Za-z0-9_]))",
    re.IGNORECASE,
)
PROPERTY_COMMAND_PROSE_PATTERN = re.compile(
    r"^(?:(?:please\s+)?(?:run|execute|invoke|perform|use|enter|provide|"
    r"replace|record|describe|add|write|insert|verify|validate)\b|"
    r"(?:the\s+)?(?:exact\s+)?(?:command|tests?|testing|validation)\b)",
    re.IGNORECASE,
)
PROPERTY_COMMAND_EXECUTABLE_PATTERN = re.compile(
    r"^(?:\"[^\"\r\n]+\"|'[^'\r\n]+'|[A-Za-z0-9_.$/\\:+@=-]+)(?:\s|$)"
)
EVIDENCE_PATTERN = re.compile(
    r"(?:(?<![A-Za-z0-9._-])EV-\d{4,}(?![A-Za-z0-9._-])|"
    r"\bVERIFY\.md#[A-Za-z0-9._-]+\b|https?://\S+)",
    re.IGNORECASE,
)
TASK_COMPLETION_EVIDENCE_STATUSES = {"LOCAL_PASS", "VERIFIED"}
EVIDENCE_PLACEHOLDER_PATTERN = re.compile(
    r"(?:<[^>]+>|\b(?:TODO|TBD|TBC|UNKNOWN|UNASSIGNED|PLACEHOLDER|"
    r"PENDING(?:[ _-][A-Z]+)?|NOT[ _-]*STARTED)\b|"
    r"^\s*`?(?:(?:command|observation|result|actor|observed at|commit|worktree|"
    r"artifact|durable source|source|status)\s*:\s*)?(?:NONE|N/?A)`?\s*$)",
    re.IGNORECASE,
)


@dataclass
class Task:
    task_id: str
    title: str
    start: int
    end: int
    block: str
    metadata: dict[str, str]
    duplicate_metadata: set[str]

    @property
    def status(self) -> str:
        return clean(self.metadata.get("Status", "")).upper()

    @property
    def dependencies(self) -> list[str]:
        raw = clean(self.metadata.get("Depends on", "NONE"))
        if raw.upper() in {"NONE", "-", ""}:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def issue(self) -> str:
        return clean(self.metadata.get("GitHub issue", "PENDING_SYNC"))

    @property
    def attempt_budget(self) -> int:
        return parse_nonnegative_int(self.metadata.get("Attempt budget", ""), minimum=1)

    @property
    def attempts_used(self) -> int:
        return parse_nonnegative_int(self.metadata.get("Attempts used", ""))

    @property
    def run_id(self) -> str:
        return clean(self.metadata.get("Run ID", "NONE"))

    @property
    def aws_mode(self) -> str:
        return clean(self.metadata.get("AWS mode", "")).upper()

    @property
    def design_revision(self) -> str:
        revision, _technology_refs = parse_design_trace(
            self.metadata.get("Design", ""), self.task_id
        )
        return revision

    @property
    def technology_refs(self) -> list[str]:
        _revision, technology_refs = parse_design_trace(
            self.metadata.get("Design", ""), self.task_id
        )
        return technology_refs


@dataclass(frozen=True)
class Snapshot:
    fields: dict[str, str]
    duplicates: set[str]

    def get(self, key: str) -> str:
        return clean(self.fields.get(key, ""))


@dataclass(frozen=True)
class Waiver:
    waiver_id: str
    skipped_task: str
    applies_to: str
    authority: str
    rationale: str
    recorded_at: str


@dataclass(frozen=True)
class CheckpointRow:
    checkpoint_id: str
    run_id: str
    recorded_at: str
    basis: str
    commit_and_dirty: str
    task_outcomes: str
    evidence_and_external: str
    blockers_and_next: str


@dataclass(frozen=True)
class TaskCompletionEvidenceRow:
    evidence_id: str
    task_id: str
    command_or_observation: str
    result: str
    actor: str
    observed_at: str
    commit_worktree_artifact: str
    durable_source: str
    status: str


@dataclass(frozen=True)
class PropertyExecutionRow:
    property_id: str
    framework_tech_id: str
    exact_command: str
    run_target_time_bound: str
    seed_or_reproduction_format: str
    evidence_destination: str
    framework_selection: str | None = field(default=None, compare=False)
    framework_version_policy: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class HarnessExecutionRow:
    harness_id: str
    layer: str
    selected_check: str
    trigger: str
    basis_ids: str
    exact_command: str
    evidence_destination: str
    requirement_status: str


@dataclass(frozen=True)
class HarnessEvidenceRow:
    evidence_id: str
    harness_id: str
    layer: str
    basis_ids: str
    exact_command: str
    artifact_environment: str
    observed_result: str
    observed_at: str
    durable_source: str
    status: str


@dataclass(frozen=True)
class ApprovedSpikeContract:
    spike_id: str
    max_attempts: int
    disposable_boundaries: tuple[str, ...]
    exit_criterion: str


@dataclass(frozen=True)
class ApprovedDeliveryContract:
    grandfathered: bool
    application_source_kind: str | None = None
    application_source_paths: tuple[str, ...] = ()
    wave_contract_id: str | None = None
    journey_id: str | None = None
    requirement_ids: tuple[str, ...] = ()
    acceptance_test_ids: tuple[str, ...] = ()
    harness_id: str | None = None
    spike: ApprovedSpikeContract | None = None


@dataclass(frozen=True)
class ApprovedTaskContract:
    technology_ids: frozenset[str]
    property_execution: dict[str, PropertyExecutionRow]
    harness: dict[str, HarnessExecutionRow]
    delivery: ApprovedDeliveryContract | None = None
    requirement_rules: dict[str, tuple[str, str]] | None = None
    requirement_evidence: dict[str, tuple[str, tuple[str, ...]]] | None = None


def clean(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "`":
        return value[1:-1]
    return value


def parse_nonnegative_int(value: str, *, minimum: int = 0) -> int:
    normalized = clean(value)
    if not normalized.isdigit() or int(normalized) < minimum:
        raise ValueError(f"expected integer >= {minimum}, got {normalized!r}")
    return int(normalized)


def parse_design_trace(value: str, task_id: str) -> tuple[str, list[str]]:
    normalized = clean(value)
    match = DESIGN_TRACE_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(
            f"{task_id}: Design must exactly match "
            "DES-nnnn; TECH: TECH-nnnn[, TECH-nnnn...] or "
            "DES-nnnn; TECH: NONE — no technology/toolchain impact"
        )
    technologies = match.group("technologies")
    technology_refs = technologies.split(", ") if technologies else []
    if len(technology_refs) != len(set(technology_refs)):
        raise ValueError(f"{task_id}: duplicate TECH reference in Design")
    return match.group("design"), technology_refs


def section(text: str, heading: str) -> str:
    text = strip_generated_summary(text)
    match = re.search(rf"^## {re.escape(heading)}\s*$", text, re.MULTILINE)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", text[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end]


def parse_snapshot(text: str) -> Snapshot:
    body = section(without_fenced_code(text), "Active execution snapshot")
    fields: dict[str, str] = {}
    duplicates: set[str] = set()
    allowed = set(SNAPSHOT_FIELDS)
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2 or cells[0] not in allowed:
            continue
        if cells[0] in fields:
            duplicates.add(cells[0])
        fields[cells[0]] = cells[1]
    return Snapshot(fields, duplicates)


def parse_tasks(text: str) -> list[Task]:
    text = strip_generated_summary(text)
    structural = without_fenced_code(text)
    matches = list(TASK_HEADER.finditer(structural))
    tasks: list[Task] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]
        structural_block = structural[start:end]
        metadata: dict[str, str] = {}
        duplicate_metadata: set[str] = set()
        for metadata_match in META_LINE.finditer(structural_block):
            key = metadata_match.group("key")
            if key in metadata:
                duplicate_metadata.add(key)
            metadata[key] = metadata_match.group("value")
        tasks.append(
            Task(
                task_id=match.group(1),
                title=match.group(2).strip(),
                start=start,
                end=end,
                block=block,
                metadata=metadata,
                duplicate_metadata=duplicate_metadata,
            )
        )
    return tasks


def parse_waivers(text: str) -> dict[str, Waiver]:
    body = section(without_fenced_code(text), "Dependencies, waivers, and waves")
    waivers: dict[str, Waiver] = {}
    in_registry = False
    for line in body.splitlines():
        if line.strip() == "### Dependency waiver registry":
            in_registry = True
            continue
        if not in_registry or not line.startswith("|"):
            continue
        cells = [clean(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6 or cells[0] in {"Waiver ID", "---", "NONE"}:
            continue
        if not re.fullmatch(r"WAIVER-\d+", cells[0]):
            continue
        if cells[0] in waivers:
            raise ValueError(f"Duplicate waiver ID: {cells[0]}")
        waivers[cells[0]] = Waiver(*cells)
    return waivers


def parse_checkpoint_rows(text: str) -> list[CheckpointRow]:
    text = strip_generated_summary(text)
    try:
        parsed_rows = parse_checkpoint_cells(text)
    except ContractParseError as exc:
        messages = {
            "section_count": "TASKS requires exactly one Checkpoints and resume section",
            "header_count": "TASKS requires one exact checkpoint table header",
            "separator_missing": "TASKS checkpoint table separator is invalid",
            "separator_invalid": "TASKS checkpoint table separator is invalid",
            "row_width": "TASKS checkpoint rows must have exactly eight cells",
            "discontiguous_rows": "TASKS checkpoint rows must form one contiguous table",
        }
        raise ValueError(messages.get(exc.reason, "TASKS checkpoint table is invalid")) from exc
    rows: list[CheckpointRow] = []
    for cells in parsed_rows:
        cleaned = [clean(cell) for cell in cells]
        if cleaned[0] == "NONE":
            continue
        if CHECKPOINT_PATTERN.fullmatch(cleaned[0]) is None:
            raise ValueError(f"Invalid checkpoint table ID: {cleaned[0]!r}")
        rows.append(CheckpointRow(*cleaned))
    identifiers = [row.checkpoint_id for row in rows]
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        raise ValueError("Checkpoint IDs may not be reused: " + ", ".join(duplicates))
    ordinals = [int(row.checkpoint_id.split("-", 1)[1]) for row in rows]
    if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
        raise ValueError("Checkpoint IDs must be strictly increasing in table order")
    return rows


def parse_dependency_waivers(task: Task) -> dict[str, str]:
    raw = clean(task.metadata.get("Dependency waivers", "NONE"))
    if raw.upper() in {"NONE", "-", ""}:
        return {}
    result: dict[str, str] = {}
    for entry in raw.split(","):
        parts = [part.strip() for part in entry.split("=", 1)]
        if (
            len(parts) != 2
            or not re.fullmatch(r"TASK-\d+", parts[0])
            or not re.fullmatch(r"WAIVER-\d+", parts[1])
        ):
            raise ValueError(
                f"{task.task_id}: invalid Dependency waivers entry {entry.strip()!r}"
            )
        if parts[0] in result:
            raise ValueError(f"{task.task_id}: duplicate waiver for {parts[0]}")
        result[parts[0]] = parts[1]
    return result


def task_subsection(task: Task, heading: str) -> str | None:
    structural = without_fenced_code(task.block)
    pattern = re.compile(rf"^{re.escape(heading)}[ \t]*$", re.MULTILINE)
    matches = list(pattern.finditer(structural))
    if len(matches) != 1:
        return None
    start = matches[0].end()
    following = re.search(r"^####\s+", structural[start:], re.MULTILINE)
    end = start + following.start() if following else len(task.block)
    return task.block[start:end]


def validate_task_sections(task: Task) -> list[str]:
    errors: list[str] = []
    sections = {
        heading: task_subsection(task, heading)
        for heading in (
            "#### Outcome",
            "#### Acceptance criteria",
            "#### Validation",
            "#### Execution log",
        )
    }
    for heading, body in sections.items():
        if body is None:
            errors.append(f"{task.task_id}: missing required section {heading}")
    outcome = sections["#### Outcome"]
    if outcome is not None and (
        not outcome.strip() or "TODO" in outcome.upper() or "TBD" in outcome.upper()
    ):
        errors.append(f"{task.task_id}: unresolved Outcome")
    acceptance = sections["#### Acceptance criteria"]
    if acceptance is not None:
        if re.search(r"^- \[[ xX]\]\s+\S", acceptance, re.MULTILINE) is None or any(
            marker in acceptance.upper() for marker in ("TODO", "TBD")
        ):
            errors.append(f"{task.task_id}: objective acceptance criteria are required")
        if task.status == "DONE" and re.search(r"^- \[ \]", acceptance, re.MULTILINE):
            errors.append(f"{task.task_id}: DONE has incomplete acceptance criteria")
    validation = sections["#### Validation"]
    if validation is not None and (
        "```" not in validation
        and "~~~" not in validation
        or any(marker in validation.upper() for marker in ("TODO", "TBD"))
    ):
        errors.append(f"{task.task_id}: executable validation commands are required")
    execution_log = sections["#### Execution log"]
    if task.status == "DONE" and execution_log is not None:
        normalized_log = execution_log.strip().upper().replace("_", " ")
        placeholders = (
            "TODO",
            "TBD",
            "NOT STARTED",
            "NO EXECUTION HAS BEEN RECORDED",
        )
        if not normalized_log or any(
            marker in normalized_log for marker in placeholders
        ):
            errors.append(f"{task.task_id}: DONE requires an observed Execution log")
    return errors


def first_revision(value: str, prefix: str) -> str | None:
    match = re.search(rf"\b{prefix}-\d{{4}}\b", clean(value))
    return match.group(0) if match else None


def validate_write_boundary(raw: str, task_id: str) -> list[str]:
    value = clean(raw)
    if value.upper() in UNRESOLVED:
        raise ValueError(f"{task_id}: unresolved Write set")
    if value == "NONE":
        return []
    result: list[str] = []
    for entry in (part.strip() for part in value.split(",")):
        if not entry or "\\" in entry or entry.startswith("/"):
            raise ValueError(f"{task_id}: unsafe Write set entry {entry!r}")
        broad = entry.endswith("/**")
        base = entry[:-3] if broad else entry
        path = PurePosixPath(base)
        if (
            not base
            or path.is_absolute()
            or any(part.casefold() in {"", ".", "..", ".git"} for part in path.parts)
            or any(char in base for char in "*?[]{}")
            or path.as_posix() != base
        ):
            raise ValueError(f"{task_id}: unsafe Write set entry {entry!r}")
        result.append(entry)
    if len(result) != len({item.casefold() for item in result}):
        raise ValueError(f"{task_id}: duplicate Write set entry")
    return result


def parse_external_state(raw: str, task_id: str) -> list[str]:
    value = clean(raw)
    if value.upper() in UNRESOLVED:
        raise ValueError(f"{task_id}: unresolved External state")
    if value == "NONE":
        return []
    result = [part.strip() for part in value.split(",")]
    if any(
        not item
        or item.upper() in {"*", "ALL", "TODO", "TBD", "UNKNOWN"}
        or any(character in item for character in "\r\n\0")
        or any(character in item for character in "*?[]{}")
        for item in result
    ):
        raise ValueError(f"{task_id}: ambiguous External state")
    if len(result) != len({item.casefold() for item in result}):
        raise ValueError(f"{task_id}: duplicate External state entry")
    return result


def validate_checkpoint(value: str, label: str) -> None:
    if CHECKPOINT_PATTERN.fullmatch(clean(value)) is None:
        raise ValueError(f"{label}: invalid checkpoint {clean(value)!r}")


def checkpoint_ordinal(value: str) -> int:
    normalized = clean(value)
    if CHECKPOINT_PATTERN.fullmatch(normalized) is None:
        return -1
    return int(normalized.split("-", 1)[1])


def validate_iso_timestamp(value: str, label: str) -> None:
    normalized = clean(value)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}: invalid ISO 8601 timestamp {normalized!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label}: timestamp must include a UTC offset")


def evidence_references(value: str) -> list[str]:
    return [match.group(0) for match in EVIDENCE_PATTERN.finditer(clean(value))]


def parse_property_execution_rows(
    text: str,
    label: str,
) -> tuple[dict[str, PropertyExecutionRow], bool]:
    """Parse one exact, non-fenced property-execution projection table."""

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
        row = PropertyExecutionRow(*(clean(cell) for cell in cells))
        if PROPERTY_ID_PATTERN.fullmatch(row.property_id) is None:
            raise ValueError(
                f"{label}: invalid property execution ID {row.property_id!r}"
            )
        if re.fullmatch(r"TECH-\d{4}", row.framework_tech_id) is None:
            raise ValueError(
                f"{label}: {row.property_id} has invalid Framework TECH ID"
            )
        if any(
            not value
            or PROPERTY_EXECUTION_PLACEHOLDER_PATTERN.search(value) is not None
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
            or PROPERTY_COMMAND_PROSE_PATTERN.match(row.exact_command) is not None
            or PROPERTY_COMMAND_EXECUTABLE_PATTERN.match(row.exact_command) is None
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


def parse_harness_projection_rows(
    text: str,
    label: str,
) -> tuple[dict[str, HarnessExecutionRow], bool]:
    """Parse one exact, non-fenced Harness projection table."""

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
        row = HarnessExecutionRow(*(clean(cell) for cell in cells))
        if HARNESS_ID_PATTERN.fullmatch(row.harness_id) is None:
            raise ValueError(f"{label}: invalid Harness ID {row.harness_id!r}")
        if row.harness_id in rows:
            raise ValueError(f"{label}: duplicate Harness ID {row.harness_id}")
        if any(
            not value
            or PROPERTY_EXECUTION_PLACEHOLDER_PATTERN.search(value) is not None
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
            or PROPERTY_COMMAND_PROSE_PATTERN.match(row.exact_command) is not None
            or PROPERTY_COMMAND_EXECUTABLE_PATTERN.match(row.exact_command) is None
        ):
            raise ValueError(
                f"{label}: {row.harness_id} Exact command or API must be concrete"
            )
        rows[row.harness_id] = row
    return rows, True


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


def validate_property_execution_projection(
    task: Task,
    approved_property_execution: dict[str, PropertyExecutionRow] | None,
) -> list[str]:
    """Require task Validation to copy every referenced approved PROP row exactly."""

    errors: list[str] = []
    requirement_value = clean(task.metadata.get("Requirements", ""))
    property_ids = PROPERTY_ID_PATTERN.findall(requirement_value)
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
    validation = task_subsection(task, "#### Validation")
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
                f"{task.task_id}: Validation contains unreferenced property execution rows: "
                + ", ".join(sorted(projected_ids))
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
            f"{task.task_id}: property execution projection order must exactly match Requirements"
        )
    if approved_property_execution is None:
        errors.append(
            f"{task.task_id}: approved PRD property execution contract is unavailable"
        )
        return errors

    fenced_commands = fenced_command_lines(validation)
    try:
        task_technology_refs = set(task.technology_refs)
    except ValueError as exc:
        errors.append(str(exc))
        task_technology_refs = set()
    for property_id in sorted(referenced & projected_ids):
        observed = projected[property_id]
        expected = approved_property_execution.get(property_id)
        if expected is None:
            errors.append(
                f"{task.task_id}: {property_id} is not approved by the PRD property execution contract"
            )
            continue
        if observed != expected:
            errors.append(
                f"{task.task_id}: {property_id} property execution projection does not exactly match the approved PRD row"
            )
        if observed.framework_tech_id not in task_technology_refs:
            errors.append(
                f"{task.task_id}: {property_id} Framework TECH ID is missing from Design"
            )
        command_count = fenced_commands.count(observed.exact_command)
        if command_count != 1:
            errors.append(
                f"{task.task_id}: {property_id} Exact command must appear unchanged exactly once in Validation code fences; found {command_count}"
            )
    return errors


def validate_harness_projections(
    tasks: list[Task],
    approved_harness: dict[str, HarnessExecutionRow] | None,
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
        validation = task_subsection(task, "#### Validation")
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


def normalize_harness_command(value: str) -> str:
    """Normalize insignificant whitespace without changing command tokens."""

    return " ".join(clean(value).split())


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


def task_contract_ids(task: Task) -> list[str]:
    """Return exact stable contract IDs from the existing Requirements field."""

    return CONTRACT_ID_PATTERN.findall(clean(task.metadata.get("Requirements", "")))


def transitively_depends_on(
    task: Task,
    ancestor_id: str,
    by_id: dict[str, Task],
) -> bool:
    pending = list(task.dependencies)
    visited: set[str] = set()
    while pending:
        dependency_id = pending.pop()
        if dependency_id == ancestor_id:
            return True
        if dependency_id in visited:
            continue
        visited.add(dependency_id)
        dependency = by_id.get(dependency_id)
        if dependency is not None:
            pending.extend(dependency.dependencies)
    return False


def validate_new_build_delivery_order(
    tasks: list[Task],
    by_id: dict[str, Task],
    approved_delivery: ApprovedDeliveryContract | None,
    approved_harness: dict[str, HarnessExecutionRow] | None,
    *,
    current_plan: bool,
) -> list[str]:
    """Bind a modern NEW_BUILD task graph to its approved first-wave contract."""

    errors: list[str] = []
    delivery = approved_delivery
    if (
        not current_plan
        or delivery is None
        or delivery.grandfathered
        or delivery.wave_contract_id is None
    ):
        return errors
    wave_id = delivery.wave_contract_id
    references = {task.task_id: task_contract_ids(task) for task in tasks}

    def matching_ids(pattern: re.Pattern[str]) -> list[str]:
        return [
            identifier
            for values in references.values()
            for identifier in values
            if pattern.fullmatch(identifier)
        ]

    def reject(condition: bool, message: str) -> bool:
        if condition:
            errors.append(message)
        return condition

    def sole_owner(identifier: str, noun: str, skipped: str) -> Task | None:
        owners = [
            task
            for task in tasks
            for reference in references[task.task_id]
            if reference == identifier
        ]
        if len(owners) != 1:
            errors.append(
                f"{identifier}: current NEW_BUILD task plan requires exactly one {noun} task; found {len(owners)}"
            )
            return None
        owner = owners[0]
        return (
            None
            if reject(
                owner.status == "SKIPPED",
                f"{owner.task_id}: {skipped} cannot be SKIPPED",
            )
            else owner
        )

    unexpected = sorted(set(matching_ids(WAVE_ID_PATTERN)) - {wave_id})
    reject(
        bool(unexpected),
        "Current NEW_BUILD task plan references unapproved first-wave IDs: "
        + ", ".join(unexpected),
    )
    walking_task = sole_owner(wave_id, "walking-skeleton", "walking-skeleton task")
    if walking_task is not None:
        required_ids = {
            wave_id,
            *delivery.requirement_ids,
            *delivery.acceptance_test_ids,
        }
        if delivery.journey_id is not None:
            required_ids.add(delivery.journey_id)
        missing_ids = sorted(required_ids - set(references[walking_task.task_id]))
        reject(
            bool(missing_ids),
            f"{walking_task.task_id}: walking-skeleton Requirements are missing "
            + ", ".join(missing_ids),
        )
        if delivery.application_source_kind == "GREENFIELD_APP_ROOT":
            try:
                walking_writes = validate_write_boundary(
                    walking_task.metadata.get("Write set", ""),
                    walking_task.task_id,
                )
                writes_application_source = any(
                    path_boundary_contains(source, path)
                    or path_boundary_contains(path, source)
                    for source in delivery.application_source_paths
                    for path in walking_writes
                )
                reject(
                    not writes_application_source,
                    f"{walking_task.task_id}: walking-skeleton Write set must include approved application source under app/**",
                )
            except ValueError as exc:
                errors.append(str(exc))

        projected_harness: dict[str, HarnessExecutionRow] = {}
        validation = task_subsection(walking_task, "#### Validation")
        if validation is not None:
            try:
                projected_harness, _present = parse_harness_projection_rows(
                    validation, walking_task.task_id
                )
            except ValueError as exc:
                errors.append(str(exc))
        harness_id = delivery.harness_id
        unavailable = (
            harness_id is None
            or approved_harness is None
            or harness_id not in approved_harness
        )
        if not reject(
            unavailable,
            f"{wave_id}: approved end-to-end Harness contract is unavailable",
        ):
            reject(
                harness_id not in projected_harness,
                f"{walking_task.task_id}: walking-skeleton Validation must own approved end-to-end {harness_id}",
            )

    approved_spike = delivery.spike
    observed_spike_ids = matching_ids(SPIKE_ID_PATTERN)
    spike_task: Task | None = None
    if approved_spike is None:
        reject(
            bool(observed_spike_ids),
            "Current NEW_BUILD task plan references an unapproved blocking spike: "
            + ", ".join(sorted(set(observed_spike_ids))),
        )
    else:
        unexpected = sorted(set(observed_spike_ids) - {approved_spike.spike_id})
        reject(
            bool(unexpected),
            "Current NEW_BUILD task plan references unapproved spike IDs: "
            + ", ".join(unexpected),
        )
        spike_task = sole_owner(approved_spike.spike_id, "spike", "blocking spike")
        same_task = (
            walking_task is not None
            and spike_task is not None
            and spike_task.task_id == walking_task.task_id
        )
        if reject(
            same_task,
            f"{approved_spike.spike_id}: spike and walking skeleton must be separate tasks",
        ):
            spike_task = None
    if spike_task is not None and approved_spike is not None:
        reject(
            spike_task.attempt_budget > approved_spike.max_attempts,
            f"{spike_task.task_id}: Attempt budget exceeds approved {approved_spike.spike_id} maximum {approved_spike.max_attempts}",
        )
        try:
            spike_writes = validate_write_boundary(
                spike_task.metadata.get("Write set", ""), spike_task.task_id
            )
            outside = [
                path
                for path in spike_writes
                if not any(
                    path_boundary_contains(boundary, path)
                    for boundary in approved_spike.disposable_boundaries
                )
            ]
            reject(
                bool(outside),
                f"{spike_task.task_id}: spike Write set exceeds the approved disposable boundary: "
                + ", ".join(outside),
            )
        except ValueError as exc:
            errors.append(str(exc))
        reject(
            clean(spike_task.metadata.get("External state", "")) != "NONE",
            f"{spike_task.task_id}: blocking spike requires External state NONE",
        )
        reject(
            spike_task.aws_mode not in {"NONE", "DOCS_ONLY"},
            f"{spike_task.task_id}: blocking spike AWS mode must be NONE or DOCS_ONLY",
        )
        validation = task_subsection(spike_task, "#### Validation") or ""
        exit_count = fenced_command_lines(validation).count(
            approved_spike.exit_criterion
        )
        reject(
            exit_count != 1,
            f"{spike_task.task_id}: approved spike exit criterion must appear unchanged exactly once in Validation code fences; found {exit_count}",
        )

    if walking_task is None or not all(
        dependency in by_id and dependency != task.task_id
        for task in tasks
        for dependency in task.dependencies
    ):
        return errors
    try:
        waves = compute_waves(tasks, by_id)
    except ValueError as exc:
        errors.append(str(exc))
        return errors
    active_tasks = [
        task for task in tasks if task.status in ALLOWED_STATUSES - {"SKIPPED"}
    ]

    def tasks_in_wave(number: int) -> list[str]:
        return sorted(
            task.task_id for task in active_tasks if waves[task.task_id] == number
        )

    if approved_spike is None:
        reject(
            bool(walking_task.dependencies),
            f"{walking_task.task_id}: walking skeleton without a spike must use Depends on NONE",
        )
        reject(
            tasks_in_wave(1) != [walking_task.task_id],
            f"{wave_id}: walking skeleton must be the sole active structural wave 1 task",
        )
    elif spike_task is not None:
        reject(
            bool(spike_task.dependencies),
            f"{spike_task.task_id}: blocking spike must use Depends on NONE",
        )
        reject(
            walking_task.dependencies != [spike_task.task_id],
            f"{walking_task.task_id}: walking skeleton must depend directly and only on {spike_task.task_id}",
        )
        reject(
            tasks_in_wave(1) != [spike_task.task_id],
            f"{approved_spike.spike_id}: spike must be the sole active structural wave 1 task",
        )
        reject(
            tasks_in_wave(2) != [walking_task.task_id],
            f"{wave_id}: walking skeleton must be the sole active structural wave 2 task after the spike",
        )

    excluded = {walking_task.task_id, *(task.task_id for task in (spike_task,) if task)}
    bypassing = sorted(
        task.task_id
        for task in active_tasks
        if task.task_id not in excluded
        and not transitively_depends_on(task, walking_task.task_id, by_id)
    )
    reject(
        bool(bypassing),
        f"{wave_id}: active tasks must be transitively downstream of the walking skeleton: "
        + ", ".join(bypassing),
    )
    return errors


def parse_harness_evidence(text: str) -> list[HarnessEvidenceRow]:
    """Parse the append-only Harness execution evidence ledger."""

    masked = without_fenced_code(text)
    headings = list(
        re.finditer(r"^## Harness execution evidence[ \t]*$", masked, re.MULTILINE)
    )
    if len(headings) != 1:
        raise ValueError(
            "VERIFY.md requires exactly one `## Harness execution evidence` section"
        )
    heading = headings[0]
    next_heading = re.search(r"^##\s+", masked[heading.end() :], re.MULTILINE)
    end = heading.end() + next_heading.start() if next_heading else len(masked)
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
    seen_evidence_ids: set[str] = set()
    for line in lines[header_index + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = split_markdown_table_row(line)
        if cells is None or len(cells) != len(HARNESS_EVIDENCE_HEADERS):
            raise ValueError(
                "VERIFY.md Harness execution evidence row must have exactly ten cells"
            )
        row = HarnessEvidenceRow(*(clean(cell) for cell in cells))
        if TASK_EVIDENCE_ID_PATTERN.fullmatch(row.evidence_id) is None:
            raise ValueError(
                f"VERIFY.md Harness evidence has invalid Evidence ID {row.evidence_id!r}"
            )
        if row.evidence_id in seen_evidence_ids:
            raise ValueError(
                f"VERIFY.md Harness evidence has duplicate Evidence ID {row.evidence_id}"
            )
        seen_evidence_ids.add(row.evidence_id)
        if HARNESS_ID_PATTERN.fullmatch(row.harness_id) is None:
            raise ValueError(
                f"VERIFY.md Harness evidence has invalid Harness ID {row.harness_id!r}"
            )
        rows.append(row)
    return rows


def validate_done_harness_evidence(
    verify_text: str,
    task: Task,
    snapshot: Snapshot,
    approved_harness: dict[str, HarnessExecutionRow] | None,
) -> None:
    validation = task_subsection(task, "#### Validation")
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
    task_evidence_ids = set(evidence_references(task.metadata.get("Evidence", "")))
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
                    r"(?:TASK|REQ|DES|AUTH)-\d{3,}|HARNESS-\d{3,}|TECH-\d{4}|PROP-\d{3,}",
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
            validate_iso_timestamp(row.observed_at, f"{label} Observed at")
            observed_time = datetime.fromisoformat(
                row.observed_at.replace("Z", "+00:00")
            )
            if prior_time is not None and observed_time <= prior_time:
                raise ValueError(
                    f"{task.task_id}: {harness_id} evidence must be append-only in chronological order"
                )
            prior_time = observed_time
            validate_durable_evidence_source(
                row.durable_source, f"{label} Durable source"
            )
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
                f"{task.task_id}: Evidence must cite latest {harness_id} result {latest.evidence_id}"
            )


def parse_task_completion_evidence(text: str) -> list[TaskCompletionEvidenceRow]:
    text = strip_generated_summary(text)
    try:
        parsed_rows = parse_task_completion_evidence_cells(text)
    except ContractParseError as exc:
        messages = {
            "section_count": "VERIFY.md requires exactly one `## Task completion evidence` section",
            "header_count": "VERIFY.md Task completion evidence requires exactly one exact table header",
            "separator_missing": "VERIFY.md Task completion evidence table has no separator row",
            "separator_invalid": "VERIFY.md Task completion evidence has an invalid separator row",
            "row_width": "VERIFY.md Task completion evidence row must have exactly nine cells",
            "discontiguous_rows": "VERIFY.md Task completion evidence rows must form one contiguous table",
        }
        raise ValueError(
            messages.get(exc.reason, "VERIFY.md Task completion evidence is invalid")
        ) from exc
    rows: list[TaskCompletionEvidenceRow] = []
    for cells in parsed_rows:
        row = TaskCompletionEvidenceRow(*(clean(cell) for cell in cells))
        if TASK_EVIDENCE_ID_PATTERN.fullmatch(row.evidence_id) is None:
            raise ValueError(
                "VERIFY.md Task completion evidence row has an invalid Evidence ID"
            )
        rows.append(row)
    identifiers = [row.evidence_id for row in rows]
    duplicates = sorted(
        identifier
        for identifier in set(identifiers)
        if identifiers.count(identifier) > 1
    )
    if duplicates:
        raise ValueError(
            "VERIFY.md Task completion Evidence IDs must be unique: "
            + ", ".join(duplicates)
        )
    return rows


def require_explicit_evidence_value(value: str, label: str) -> str:
    normalized = clean(value)
    if (
        not normalized
        or any(character in normalized for character in "\r\n")
        or EVIDENCE_PLACEHOLDER_PATTERN.search(normalized) is not None
    ):
        raise ValueError(f"{label} is unresolved or placeholder evidence")
    return normalized


def validate_evidence_material(value: str, label: str) -> None:
    normalized = require_explicit_evidence_value(value, label)
    commit = re.fullmatch(
        r"`?[0-9a-fA-F]{7,64}`?",
        normalized,
    ) or re.search(
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


def validate_durable_evidence_source(value: str, label: str) -> None:
    normalized = require_explicit_evidence_value(value, label)
    if re.fullmatch(r"VERIFY\.md#[A-Za-z0-9._-]+", normalized):
        return
    if re.fullmatch(r"git:[0-9a-fA-F]{7,64}", normalized, re.IGNORECASE):
        return
    candidate = re.sub(r"^artifact\s*:\s*", "", normalized, flags=re.IGNORECASE)
    if (
        re.fullmatch(
            r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+(?:#[A-Za-z0-9._-]+)?", candidate
        )
        and ".." not in PurePosixPath(candidate.split("#", 1)[0]).parts
    ):
        return
    raise ValueError(f"{label} is not a durable source reference")


def validate_property_done_evidence(
    verify_text: str,
    task: Task,
    snapshot: Snapshot,
    approved_property_execution: dict[str, PropertyExecutionRow] | None,
) -> None:
    property_ids = PROPERTY_ID_PATTERN.findall(
        clean(task.metadata.get("Requirements", ""))
    )
    if not property_ids:
        return
    if approved_property_execution is None:
        raise ValueError(
            f"{task.task_id}: approved PRD property execution contract is unavailable"
        )
    doctor = load_bootstrap_doctor()
    rows = doctor.parse_property_test_evidence(verify_text)
    completion_rows = doctor.parse_task_completion_evidence(verify_text)
    inspected_task = doctor.InspectedTask(
        task.task_id,
        task.title,
        task.block,
        task.metadata,
        task.duplicate_metadata,
    )
    snapshot_fields = {key: clean(value) for key, value in snapshot.fields.items()}
    for property_id in property_ids:
        contract = approved_property_execution.get(property_id)
        if contract is None:
            raise ValueError(
                f"{task.task_id}: {property_id} is not approved by the PRD property execution contract"
            )
        if (
            contract.framework_selection is None
            or contract.framework_version_policy is None
        ):
            raise ValueError(
                f"{task.task_id}: {property_id} approved framework selection and version policy are unavailable"
            )
        expected = doctor.PropertyExecution(
            contract.property_id,
            contract.framework_tech_id,
            contract.exact_command,
            contract.run_target_time_bound,
            contract.seed_or_reproduction_format,
            contract.evidence_destination,
        )
        technology = doctor.TechnologyDecision(
            contract.framework_tech_id,
            "PROPERTY_TESTING",
            contract.framework_selection,
            contract.framework_version_policy,
            "REPOSITORY_FACT",
            snapshot.get("Design revision"),
            "Validated by the current PRD",
            "NONE",
            "Observed property evidence",
        )
        doctor.validate_done_property_evidence(
            rows,
            inspected_task,
            snapshot_fields,
            expected,
            technology,
            completion_rows,
        )


def validate_done_evidence_file(
    tasks_path: Path,
    task: Task,
    approved_property_execution: dict[str, PropertyExecutionRow] | None = None,
    approved_harness: dict[str, HarnessExecutionRow] | None = None,
    tasks_text: str | None = None,
) -> None:
    references = evidence_references(task.metadata.get("Evidence", ""))
    if not references:
        raise ValueError(f"{task.task_id}: DONE requires an Evidence reference")
    verify_path = tasks_path.with_name("VERIFY.md")
    task_evidence_ids = [
        reference
        for reference in references
        if TASK_EVIDENCE_ID_PATTERN.fullmatch(reference) is not None
    ]
    if not task_evidence_ids:
        raise ValueError(
            f"{task.task_id}: DONE requires at least one exact local Evidence reference "
            "in EV-nnnn form"
        )
    if len(task_evidence_ids) != len(set(task_evidence_ids)):
        raise ValueError(
            f"{task.task_id}: DONE has duplicate local Evidence references"
        )
    if not verify_path.is_file() or verify_path.is_symlink():
        raise ValueError(f"{task.task_id}: local Evidence requires a regular VERIFY.md")
    verify_text = strip_generated_summary(verify_path.read_text(encoding="utf-8"))
    rows = parse_task_completion_evidence(verify_text)
    for evidence_id in task_evidence_ids:
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
        validate_iso_timestamp(row.observed_at, f"{label} Observed at")
        validate_evidence_material(
            row.commit_worktree_artifact, f"{label} Commit / worktree / artifact"
        )
        validate_durable_evidence_source(row.durable_source, f"{label} Durable source")
        if row.status not in TASK_COMPLETION_EVIDENCE_STATUSES:
            raise ValueError(f"{label} Status must be LOCAL_PASS or VERIFIED")
    if tasks_text is None:
        tasks_text = tasks_path.read_text(encoding="utf-8")
    snapshot = parse_snapshot(tasks_text)
    validate_property_done_evidence(
        verify_text,
        task,
        snapshot,
        approved_property_execution,
    )
    validate_done_harness_evidence(
        verify_text,
        task,
        snapshot,
        approved_harness,
    )


def validate_snapshot(snapshot: Snapshot) -> None:
    errors: list[str] = []
    for key in SNAPSHOT_FIELDS:
        if key not in snapshot.fields:
            errors.append(f"Execution snapshot: missing {key}")
    for key in sorted(snapshot.duplicates):
        errors.append(f"Execution snapshot: duplicate {key}")
    if errors:
        raise ValueError("\n".join(errors))
    if snapshot.get("Run state") not in ALLOWED_RUN_STATES:
        raise ValueError(
            f"Execution snapshot: invalid Run state {snapshot.get('Run state')!r}"
        )
    plan_state = snapshot.get("Task-plan state")
    plan_revision = snapshot.get("Task-plan revision")
    if plan_state not in ALLOWED_PLAN_STATES:
        raise ValueError(f"Execution snapshot: invalid Task-plan state {plan_state!r}")
    if plan_state == "UNINITIALIZED" and plan_revision != "UNINITIALIZED":
        raise ValueError(
            "Execution snapshot: UNINITIALIZED plan state requires no plan revision"
        )
    if (
        plan_state in {"CURRENT", "STALE"}
        and re.fullmatch(r"PLAN-\d{4,}", plan_revision) is None
    ):
        raise ValueError(f"Execution snapshot: {plan_state} requires a PLAN revision")
    try:
        maximum_workers = parse_nonnegative_int(
            snapshot.get("Maximum workers"), minimum=1
        )
    except ValueError as exc:
        raise ValueError(f"Execution snapshot: invalid Maximum workers: {exc}") from exc
    if maximum_workers != 1:
        raise ValueError("Execution snapshot: Maximum workers must be exactly 1")
    active_run = snapshot.get("Active run ID")
    run_state = snapshot.get("Run state")
    coordinator = snapshot.get("Coordinator")
    if run_state == "NOT_STARTED":
        if active_run != "NONE":
            raise ValueError(
                "Execution snapshot: NOT_STARTED requires Active run ID NONE"
            )
    else:
        if RUN_ID_PATTERN.fullmatch(active_run) is None:
            raise ValueError("Execution snapshot: active run ID is invalid")
        if coordinator in {"", "NONE", "UNASSIGNED", "TODO"}:
            raise ValueError("Execution snapshot: active run requires a coordinator")
    current_wave = snapshot.get("Current wave")
    if current_wave != "NONE":
        try:
            parse_nonnegative_int(current_wave, minimum=1)
        except ValueError as exc:
            raise ValueError(
                f"Execution snapshot: invalid Current wave: {exc}"
            ) from exc
    validate_write_boundary(
        snapshot.get("Protected dirty paths"),
        "Execution snapshot Protected dirty paths",
    )
    last_checkpoint = snapshot.get("Last checkpoint")
    if last_checkpoint != "NONE":
        validate_checkpoint(last_checkpoint, "Execution snapshot")
    elif run_state in {"PAUSED", "BLOCKED", "COMPLETE"}:
        raise ValueError(
            f"Execution snapshot: {run_state} requires a valid Last checkpoint"
        )


def validate(
    tasks: list[Task],
    snapshot: Snapshot | None = None,
    waivers: dict[str, Waiver] | None = None,
    *,
    approved_tech_ids: set[str] | None = None,
    approved_property_execution: dict[str, PropertyExecutionRow] | None = None,
    approved_harness: dict[str, HarnessExecutionRow] | None = None,
    approved_delivery: ApprovedDeliveryContract | None = None,
    approved_requirement_rules: dict[str, tuple[str, str]] | None = None,
    approved_requirement_evidence: dict[str, tuple[str, tuple[str, ...]]] | None = None,
) -> dict[str, Task]:
    by_id: dict[str, Task] = {}
    errors: list[str] = []
    waivers = waivers or {}
    if snapshot is not None:
        validate_snapshot(snapshot)

    for task in tasks:
        if task.task_id in by_id:
            errors.append(f"Duplicate task ID: {task.task_id}")
        by_id[task.task_id] = task
        for key in sorted(task.duplicate_metadata):
            errors.append(f"{task.task_id}: duplicate {key} metadata")
        for key in REQUIRED_METADATA:
            if key not in task.metadata:
                errors.append(f"{task.task_id}: missing {key} metadata")
        if task.status not in ALLOWED_STATUSES:
            errors.append(
                f"{task.task_id}: invalid status {task.status!r}; "
                f"allowed={sorted(ALLOWED_STATUSES)}"
            )
            continue
        try:
            budget = task.attempt_budget
            used = task.attempts_used
            if used > budget:
                errors.append(f"{task.task_id}: Attempts used exceeds Attempt budget")
        except ValueError as exc:
            errors.append(f"{task.task_id}: invalid attempt metadata: {exc}")
            budget = used = 0

        if task.aws_mode not in ALLOWED_AWS_MODES:
            errors.append(f"{task.task_id}: invalid AWS mode {task.aws_mode!r}")

        contract_bound = task.status in {"READY", "IN_PROGRESS", "BLOCKED", "DONE"} or (
            task.status == "BACKLOG"
            and snapshot is not None
            and snapshot.get("Task-plan state") == "CURRENT"
        )
        if contract_bound:
            req = first_revision(task.metadata.get("Requirements", ""), "REQ")
            auth = first_revision(task.metadata.get("Authorization", ""), "AUTH")
            try:
                des, technology_refs = parse_design_trace(
                    task.metadata.get("Design", ""), task.task_id
                )
                if approved_tech_ids is not None:
                    unknown_tech_ids = [
                        tech_id
                        for tech_id in technology_refs
                        if tech_id not in approved_tech_ids
                    ]
                    if unknown_tech_ids:
                        errors.append(
                            f"{task.task_id}: Design references unapproved TECH IDs: "
                            + ", ".join(unknown_tech_ids)
                        )
            except ValueError as exc:
                errors.append(str(exc))
                des = None
            if not req or not auth:
                errors.append(f"{task.task_id}: unresolved REQ/DES/AUTH trace")
            if snapshot is not None:
                expected = (
                    snapshot.get("Requirements revision"),
                    snapshot.get("Design revision"),
                    snapshot.get("Construction authorization"),
                )
                if des is not None and (req, des, auth) != expected:
                    errors.append(
                        f"{task.task_id}: REQ/DES/AUTH trace does not match execution snapshot"
                    )
                if snapshot.get("Gate B state") != "APPROVED_FOR_CONSTRUCTION":
                    errors.append(
                        f"{task.task_id}: Gate B is not approved for construction"
                    )
            try:
                validate_write_boundary(
                    task.metadata.get("Write set", ""), task.task_id
                )
                parse_external_state(
                    task.metadata.get("External state", ""), task.task_id
                )
            except ValueError as exc:
                errors.append(str(exc))
            if used >= budget and task.status == "READY":
                errors.append(f"{task.task_id}: attempt budget exhausted")

        if task.status == "IN_PROGRESS":
            owner = clean(task.metadata.get("Owner", ""))
            checkpoint = clean(task.metadata.get("Last checkpoint", ""))
            if owner in UNRESOLVED or owner == "NONE":
                errors.append(f"{task.task_id}: IN_PROGRESS requires an assigned Owner")
            if task.run_id in UNRESOLVED or task.run_id == "NONE":
                errors.append(f"{task.task_id}: IN_PROGRESS requires a Run ID")
            if CHECKPOINT_PATTERN.fullmatch(checkpoint) is None:
                errors.append(
                    f"{task.task_id}: IN_PROGRESS requires a valid Last checkpoint"
                )
            if used < 1:
                errors.append(f"{task.task_id}: IN_PROGRESS requires a claimed attempt")
            if snapshot is not None and (
                snapshot.get("Run state") != "RUNNING"
                or snapshot.get("Active run ID") != task.run_id
            ):
                errors.append(
                    f"{task.task_id}: Run ID does not match the active RUNNING run"
                )
        elif task.run_id not in {"", "NONE"}:
            errors.append(f"{task.task_id}: non-IN_PROGRESS task must use Run ID NONE")

        if task.status == "DONE":
            evidence = clean(task.metadata.get("Evidence", ""))
            exact_task_evidence = [
                reference
                for reference in evidence_references(evidence)
                if TASK_EVIDENCE_ID_PATTERN.fullmatch(reference) is not None
            ]
            if evidence.upper() in {*UNRESOLVED, "NONE"} or not exact_task_evidence:
                errors.append(f"{task.task_id}: DONE requires an Evidence reference")
            elif len(exact_task_evidence) != len(set(exact_task_evidence)):
                errors.append(
                    f"{task.task_id}: DONE has duplicate local Evidence references"
                )
        if task.status == "BLOCKED" and clean(task.metadata.get("Blocker", "")) in {
            *UNRESOLVED,
            "NONE",
        }:
            errors.append(f"{task.task_id}: BLOCKED requires a blocker and next action")
        if task.status == "SKIPPED" and clean(task.metadata.get("Skip record", "")) in {
            *UNRESOLVED,
            "NONE",
        }:
            errors.append(f"{task.task_id}: SKIPPED requires a Skip record")
        if contract_bound:
            errors.extend(validate_task_sections(task))
            errors.extend(
                validate_property_execution_projection(
                    task, approved_property_execution
                )
            )
        last_updated = clean(task.metadata.get("Last updated", ""))
        if last_updated.upper() not in UNRESOLVED:
            try:
                validate_iso_timestamp(last_updated, task.task_id)
            except ValueError as exc:
                errors.append(str(exc))

        try:
            declared_waivers = parse_dependency_waivers(task)
            for dependency, waiver_id in declared_waivers.items():
                waiver = waivers.get(waiver_id)
                if waiver is None:
                    errors.append(
                        f"{task.task_id}: unknown dependency waiver {waiver_id}"
                    )
                elif (
                    waiver.skipped_task != dependency
                    or waiver.applies_to != task.task_id
                ):
                    errors.append(
                        f"{task.task_id}: waiver {waiver_id} does not match its task pair"
                    )
        except ValueError as exc:
            errors.append(str(exc))

    for task in tasks:
        for dependency in task.dependencies:
            if dependency not in by_id:
                errors.append(f"{task.task_id}: missing dependency {dependency}")
            if dependency == task.task_id:
                errors.append(f"{task.task_id}: cannot depend on itself")

    errors.extend(
        validate_new_build_delivery_order(
            tasks,
            by_id,
            approved_delivery,
            approved_harness,
            current_plan=(
                snapshot is not None and snapshot.get("Task-plan state") == "CURRENT"
            ),
        )
    )

    for waiver in waivers.values():
        if waiver.skipped_task not in by_id or waiver.applies_to not in by_id:
            errors.append(f"{waiver.waiver_id}: references an unknown task")
            continue
        if by_id[waiver.skipped_task].status != "SKIPPED":
            errors.append(f"{waiver.waiver_id}: dependency is not SKIPPED")
        if waiver.skipped_task not in by_id[waiver.applies_to].dependencies:
            errors.append(f"{waiver.waiver_id}: skipped task is not a dependency")
        current_auth = snapshot.get("Construction authorization") if snapshot else ""
        auth_pattern = (
            re.compile(rf"{re.escape(current_auth)}(?:\s+clause\s+[A-Za-z0-9._:-]+)?")
            if current_auth
            else None
        )
        authority_is_current = bool(
            (auth_pattern and auth_pattern.fullmatch(waiver.authority))
            or OWNER_DECISION_PATTERN.fullmatch(waiver.authority)
        )
        if not authority_is_current:
            errors.append(
                f"{waiver.waiver_id}: authority is not an exact current authority"
            )
        if (
            waiver.rationale.upper() in UNRESOLVED
            or waiver.rationale == "No waivers recorded"
            or EVIDENCE_PATTERN.search(waiver.rationale) is None
        ):
            errors.append(
                f"{waiver.waiver_id}: missing rationale or preserved evidence"
            )
        try:
            validate_iso_timestamp(waiver.recorded_at, waiver.waiver_id)
        except ValueError as exc:
            errors.append(str(exc))

    if snapshot is not None:
        errors.extend(
            validate_harness_projections(
                tasks,
                approved_harness,
                current_plan=snapshot.get("Task-plan state") == "CURRENT",
            )
        )

    if (
        snapshot is not None
        and snapshot.get("Task-plan state") == "CURRENT"
        and approved_property_execution is not None
    ):
        referenced_property_ids = {
            property_id
            for task in tasks
            if task.status in {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE"}
            for property_id in PROPERTY_ID_PATTERN.findall(
                clean(task.metadata.get("Requirements", ""))
            )
        }
        missing_property_ids = sorted(
            set(approved_property_execution) - referenced_property_ids
        )
        if missing_property_ids:
            errors.append(
                "Current task plan does not cover approved property execution IDs: "
                + ", ".join(missing_property_ids)
            )
    if (
        snapshot is not None
        and snapshot.get("Task-plan state") == "CURRENT"
        and approved_requirement_rules is not None
    ):
        requirement_coverage = load_bootstrap_doctor().derive_task_requirement_coverage(
            tasks,
            snapshot.get("Task-plan state"),
            approved_requirement_rules,
            approved_requirement_evidence or {},
        )
        errors.extend(requirement_coverage.trace_issues)
        errors.extend(requirement_coverage.evidence_issues)
        if requirement_coverage.missing_requirement_ids:
            errors.append(
                "Current task plan does not cover approved requirement IDs: "
                + ", ".join(requirement_coverage.missing_requirement_ids)
            )

    if errors:
        raise ValueError("\n".join(errors))
    return by_id


def compute_waves(tasks: list[Task], by_id: dict[str, Task]) -> dict[str, int]:
    waves: dict[str, int] = {}
    visiting: set[str] = set()
    stack: list[str] = []

    def assign(task_id: str) -> int:
        if task_id in waves:
            return waves[task_id]
        if task_id in visiting:
            start = stack.index(task_id)
            cycle = " -> ".join([*stack[start:], task_id])
            raise ValueError(f"Dependency cycle detected: {cycle}")
        visiting.add(task_id)
        stack.append(task_id)
        dependencies = by_id[task_id].dependencies
        wave = 1 if not dependencies else 1 + max(assign(dep) for dep in dependencies)
        stack.pop()
        visiting.remove(task_id)
        waves[task_id] = wave
        return wave

    for task in sorted(tasks, key=lambda item: item.task_id):
        assign(task.task_id)
    return waves


def dependency_satisfied(
    task: Task,
    dependency: Task,
    waivers: dict[str, Waiver],
) -> bool:
    if dependency.status == "DONE":
        return True
    if dependency.status != "SKIPPED":
        return False
    declared = parse_dependency_waivers(task)
    waiver_id = declared.get(dependency.task_id)
    waiver = waivers.get(waiver_id or "")
    return bool(
        waiver
        and waiver.skipped_task == dependency.task_id
        and waiver.applies_to == task.task_id
    )


def ready_tasks(
    tasks: list[Task],
    by_id: dict[str, Task],
    waivers: dict[str, Waiver] | None = None,
) -> list[Task]:
    waivers = waivers or {}
    ready: list[Task] = []
    for task in tasks:
        if task.status != "READY":
            continue
        if all(
            dependency_satisfied(task, by_id[dep], waivers) for dep in task.dependencies
        ):
            ready.append(task)
    return ready


boundary_base = path_boundary_base
write_boundaries_overlap = path_boundaries_overlap


def is_control_boundary(value: str) -> bool:
    base, _broad = boundary_base(value)
    return (
        base in {path.casefold() for path in CONTROL_PATHS}
        or PurePosixPath(base).name.casefold() in CONTROL_FILENAMES
    )


def require_active_coordinator(
    snapshot: Snapshot,
    supplied: str,
    action: str,
) -> str:
    coordinator = supplied.strip()
    if (
        not coordinator
        or coordinator in {"NONE", "UNASSIGNED", "TODO"}
        or any(character in coordinator for character in "\r\n")
    ):
        raise ValueError(f"{action} requires an explicit --coordinator")
    if coordinator != snapshot.get("Coordinator"):
        raise ValueError(
            f"{action} coordinator does not match the active run coordinator"
        )
    return coordinator


def require_current_plan(snapshot: Snapshot, action: str) -> None:
    if snapshot.get("Task-plan state") != "CURRENT":
        raise ValueError(
            f"{action} requires Task-plan state CURRENT; "
            f"observed {snapshot.get('Task-plan state')!r}"
        )


def explicit_checkpoint_value(value: str, *, allow_none: bool = False) -> bool:
    normalized = clean(value)
    if allow_none and normalized == "NONE":
        return True
    upper = normalized.upper()
    return bool(normalized) and not any(
        marker in upper for marker in ("TODO", "TBD", "UNKNOWN", "UNASSIGNED", "<", ">")
    )


def parse_checkpoint_git_receipt(
    row: CheckpointRow, checkpoint_id: str
) -> tuple[str, list[str]]:
    try:
        commit, dirty_value = parse_checkpoint_git_receipt_value(row.commit_and_dirty)
    except ContractParseError as exc:
        raise ValueError(
            f"{checkpoint_id}: commit receipt must use `Commit: <sha>; Dirty: <paths|NONE>`"
        ) from exc
    dirty_paths = validate_write_boundary(
        dirty_value, f"{checkpoint_id} checkpoint Dirty paths"
    )
    return commit, dirty_paths


def validate_checkpoint_receipt(
    tasks_path: Path,
    tasks_text: str,
    checkpoint_id: str,
    run_id: str,
    tasks: list[Task],
    snapshot: Snapshot,
    *,
    require_advance: bool = True,
) -> CheckpointRow:
    rows = parse_checkpoint_rows(tasks_text)
    matching = [row for row in rows if row.checkpoint_id == checkpoint_id]
    if len(matching) != 1:
        raise ValueError(
            f"{checkpoint_id}: requires exactly one existing checkpoint row"
        )
    row = matching[0]
    requested_ordinal = int(checkpoint_id.split("-", 1)[1])
    previous = snapshot.get("Last checkpoint")
    previous_ordinal = (
        int(previous.split("-", 1)[1])
        if CHECKPOINT_PATTERN.fullmatch(previous) is not None
        else -1
    )
    if require_advance and requested_ordinal <= previous_ordinal:
        raise ValueError(
            f"{checkpoint_id}: checkpoint must advance and may not be reused"
        )
    if rows[-1].checkpoint_id != checkpoint_id:
        raise ValueError(f"{checkpoint_id}: checkpoint must be the newest table row")
    if row.run_id != run_id:
        raise ValueError(
            f"{checkpoint_id}: checkpoint row does not match the active run"
        )
    validate_iso_timestamp(row.recorded_at, checkpoint_id)

    expected_basis = (
        snapshot.get("Requirements revision"),
        snapshot.get("Design revision"),
        snapshot.get("Construction authorization"),
    )
    actual_basis = tuple(
        re.findall(rf"\b{prefix}-\d{{4}}\b", row.basis)
        for prefix in ("REQ", "DES", "AUTH")
    )
    if actual_basis != tuple([value] for value in expected_basis):
        raise ValueError(
            f"{checkpoint_id}: checkpoint REQ/DES/AUTH basis is not current"
        )

    if not explicit_checkpoint_value(row.commit_and_dirty):
        raise ValueError(f"{checkpoint_id}: commit and dirty paths are unresolved")
    checkpoint_commit, receipt_dirty = parse_checkpoint_git_receipt(row, checkpoint_id)
    known_green = snapshot.get("Last known-green commit")
    if (
        re.fullmatch(r"[0-9a-fA-F]{7,64}", known_green) is None
        or checkpoint_commit.casefold() != known_green.casefold()
    ):
        raise ValueError(f"{checkpoint_id}: checkpoint commit is not explicit/current")
    protected = validate_write_boundary(
        snapshot.get("Protected dirty paths"),
        "Execution snapshot Protected dirty paths",
    )
    if {path.casefold() for path in receipt_dirty} != {
        path.casefold() for path in protected
    }:
        raise ValueError(
            f"{checkpoint_id}: checkpoint dirty paths do not exactly match "
            "Protected dirty paths"
        )

    if not explicit_checkpoint_value(row.task_outcomes):
        raise ValueError(f"{checkpoint_id}: task outcomes and attempts are unresolved")
    for task in tasks:
        task_token = re.compile(
            rf"(?<![A-Za-z0-9-]){re.escape(task.task_id)}(?![A-Za-z0-9-])"
        )
        segments = [
            segment.strip()
            for segment in re.split(r"[;\n]", row.task_outcomes)
            if task_token.search(segment) is not None
        ]
        if len(segments) != 1:
            raise ValueError(f"{checkpoint_id}: missing outcome for {task.task_id}")
        segment = segments[0]
        if (
            re.match(
                rf"^{re.escape(task.task_id)}\s+{re.escape(task.status)}(?:\s|$)",
                segment,
            )
            is None
        ):
            raise ValueError(
                f"{checkpoint_id}: status for {task.task_id} is not current"
            )
        attempt_pattern = re.compile(
            rf"\battempts?(?:\s+used)?\s*[=:]\s*{task.attempts_used}"
            rf"\s*/\s*{task.attempt_budget}(?!\d)\b",
            re.IGNORECASE,
        )
        if attempt_pattern.search(segment) is None:
            raise ValueError(
                f"{checkpoint_id}: attempts for {task.task_id} are not explicit"
            )

    if (
        not explicit_checkpoint_value(row.evidence_and_external, allow_none=True)
        or re.search(r"\bevidence\b", row.evidence_and_external, re.IGNORECASE) is None
        or re.search(r"\bexternal\b", row.evidence_and_external, re.IGNORECASE) is None
    ):
        raise ValueError(
            f"{checkpoint_id}: evidence and external actions must be explicit"
        )
    evidence_cell = row.evidence_and_external.casefold()
    for task in tasks:
        task_evidence = evidence_references(task.metadata.get("Evidence", ""))
        if any(
            re.search(
                rf"(?<![A-Za-z0-9._-]){re.escape(reference.casefold())}"
                rf"(?![A-Za-z0-9._-])",
                evidence_cell,
            )
            is None
            for reference in task_evidence
        ):
            raise ValueError(
                f"{checkpoint_id}: evidence for {task.task_id} is incomplete"
            )
    if (
        not explicit_checkpoint_value(row.blockers_and_next, allow_none=True)
        or re.search(r"\bblockers?\b", row.blockers_and_next, re.IGNORECASE) is None
        or re.search(r"\bnext\b", row.blockers_and_next, re.IGNORECASE) is None
    ):
        raise ValueError(
            f"{checkpoint_id}: blockers and next safe action must be explicit"
        )

    verify_path = tasks_path.with_name("VERIFY.md")
    if not verify_path.is_file() or verify_path.is_symlink():
        raise ValueError(f"{checkpoint_id}: checkpoint requires a regular VERIFY.md")
    verify_text = without_fenced_code(
        strip_generated_summary(verify_path.read_text(encoding="utf-8"))
    )
    if (
        re.search(
            rf"(?<![A-Za-z0-9-]){re.escape(checkpoint_id)}(?![A-Za-z0-9-])",
            verify_text,
        )
        is None
    ):
        raise ValueError(f"{checkpoint_id}: checkpoint is not referenced in VERIFY.md")
    return row


def git_read(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return subprocess.run(
        [
            resolve_trusted_git(root),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(root),
            *arguments,
        ],
        check=False,
        capture_output=True,
        env=environment,
        timeout=10,
    )


def reconcile_git_state(
    tasks_path: Path,
    snapshot: Snapshot,
    *,
    action: str,
    checkpoint_row: CheckpointRow | None = None,
) -> None:
    """Conservatively prove a run receipt matches read-only Git state."""

    baseline = snapshot.get("Baseline commit")
    known_green = snapshot.get("Last known-green commit")
    for label, value in (
        ("Baseline commit", baseline),
        ("Last known-green commit", known_green),
    ):
        if re.fullmatch(r"[0-9a-fA-F]{7,64}", value) is None:
            raise ValueError(
                f"{action} Git reconciliation: {label} is not an explicit commit ID"
            )
    checkpoint_commit: str | None = None
    checkpoint_dirty: list[str] | None = None
    if checkpoint_row is not None:
        checkpoint_commit, checkpoint_dirty = parse_checkpoint_git_receipt(
            checkpoint_row, checkpoint_row.checkpoint_id
        )
    root = project_root_for_tasks(tasks_path)
    try:
        inside_result = git_read(root, "rev-parse", "--is-inside-work-tree")
        bare_result = git_read(root, "rev-parse", "--is-bare-repository")
        head_result = git_read(root, "rev-parse", "--verify", "HEAD^{commit}")
        baseline_result = git_read(
            root, "rev-parse", "--verify", f"{baseline}^{{commit}}"
        )
        green_result = git_read(
            root, "rev-parse", "--verify", f"{known_green}^{{commit}}"
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"{action} Git reconciliation unavailable: {exc}") from exc
    if (
        inside_result.returncode != 0
        or inside_result.stdout.strip() != b"true"
        or bare_result.returncode != 0
        or bare_result.stdout.strip() != b"false"
    ):
        raise ValueError(f"{action} Git reconciliation: not a regular Git worktree")
    if any(
        result.returncode != 0
        for result in (head_result, baseline_result, green_result)
    ):
        raise ValueError(
            f"{action} Git reconciliation: checkpoint commits are not resolvable"
        )
    checkpoint_result: subprocess.CompletedProcess[bytes] | None = None
    if checkpoint_commit is not None:
        try:
            checkpoint_result = git_read(
                root, "rev-parse", "--verify", f"{checkpoint_commit}^{{commit}}"
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"{action} Git reconciliation unavailable: {exc}") from exc
        if checkpoint_result.returncode != 0:
            raise ValueError(
                f"{action} Git reconciliation: checkpoint commits are not resolvable"
            )
    resolved_green = green_result.stdout.decode("ascii", errors="replace").strip()
    if checkpoint_result is not None:
        resolved_checkpoint = checkpoint_result.stdout.decode(
            "ascii", errors="replace"
        ).strip()
        if resolved_checkpoint != resolved_green:
            raise ValueError(
                f"{action} Git reconciliation: checkpoint commit does not match "
                "Last known-green commit"
            )
    try:
        baseline_ancestor = git_read(
            root, "merge-base", "--is-ancestor", baseline, known_green
        )
        green_ancestor = git_read(
            root, "merge-base", "--is-ancestor", known_green, "HEAD"
        )
        committed = git_read(
            root,
            "diff",
            "--name-only",
            "-z",
            "--relative",
            f"{known_green}..HEAD",
            "--",
            ".",
        )
        tracked = git_read(
            root, "diff", "--name-only", "-z", "--relative", "HEAD", "--", "."
        )
        untracked = git_read(
            root, "ls-files", "--others", "--exclude-standard", "-z", "--", "."
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"{action} Git reconciliation unavailable: {exc}") from exc
    if baseline_ancestor.returncode != 0:
        raise ValueError(
            f"{action} Git reconciliation: baseline is not an ancestor of "
            "Last known-green commit"
        )
    if green_ancestor.returncode != 0:
        raise ValueError(
            f"{action} Git reconciliation: Last known-green commit is not an ancestor of HEAD"
        )
    if (
        committed.returncode != 0
        or tracked.returncode != 0
        or untracked.returncode != 0
    ):
        raise ValueError(
            f"{action} Git reconciliation: worktree paths cannot be enumerated"
        )
    committed_paths = {
        item.decode("utf-8", errors="surrogateescape")
        for item in committed.stdout.split(b"\0")
        if item
    }
    coordinator_ledgers = coordinator_ledger_paths(tasks_path)
    unauthorized_committed = sorted(committed_paths - coordinator_ledgers)
    if unauthorized_committed:
        raise ValueError(
            f"{action} Git reconciliation: commits after Last known-green contain "
            "non-ledger paths=" + ", ".join(unauthorized_committed)
        )
    observed = {
        item.decode("utf-8", errors="surrogateescape")
        for payload in (tracked.stdout, untracked.stdout)
        for item in payload.split(b"\0")
        if item
    }
    observed_nonledger = observed - coordinator_ledgers
    protected = validate_write_boundary(
        snapshot.get("Protected dirty paths"),
        "Execution snapshot Protected dirty paths",
    )
    if checkpoint_dirty is not None and {
        path.casefold() for path in checkpoint_dirty
    } != {path.casefold() for path in protected}:
        raise ValueError(
            f"{action} Git reconciliation: checkpoint Dirty paths do not match "
            "Protected dirty paths"
        )
    uncovered = sorted(
        path
        for path in observed_nonledger
        if not any(path_boundary_contains(boundary, path) for boundary in protected)
    )
    unused = sorted(
        boundary
        for boundary in protected
        if not any(
            path_boundary_contains(boundary, path) for path in observed_nonledger
        )
    )
    if uncovered or unused:
        details: list[str] = []
        if uncovered:
            details.append("unrecorded dirty paths=" + ", ".join(uncovered))
        if unused:
            details.append("recorded paths not dirty=" + ", ".join(unused))
        raise ValueError(
            f"{action} Git reconciliation: Protected dirty paths do not exactly match; "
            + "; ".join(details)
        )


def tasks_conflict(first: Task, second: Task) -> bool:
    first_writes = validate_write_boundary(first.metadata["Write set"], first.task_id)
    second_writes = validate_write_boundary(
        second.metadata["Write set"], second.task_id
    )
    if any(is_control_boundary(path) for path in [*first_writes, *second_writes]):
        return True
    if any(write_boundaries_overlap(a, b) for a in first_writes for b in second_writes):
        return True

    first_external = parse_external_state(
        first.metadata["External state"], first.task_id
    )
    second_external = parse_external_state(
        second.metadata["External state"], second.task_id
    )
    if any(
        external_targets_overlap(a, b) for a in first_external for b in second_external
    ):
        return True
    if first.aws_mode == "MUTATION" or second.aws_mode == "MUTATION":
        return True
    return False


def safe_execution_groups(
    candidates: list[Task],
    waves: dict[str, int],
    *,
    isolated_worktrees: bool,
    maximum_workers: int | None = None,
) -> list[list[Task]]:
    if maximum_workers not in {None, 1}:
        raise ValueError("Maximum workers must be exactly 1")
    return [[task] for task in candidates]


def replace_metadata(text: str, task: Task, key: str, value: str) -> str:
    block = text[task.start : task.end]
    pattern = re.compile(rf"^- {re.escape(key)}:\s*.+?$", re.MULTILINE)
    replacement = f"- {key}: `{value}`"
    if not pattern.search(block):
        raise ValueError(f"{task.task_id}: missing {key} metadata")
    new_block = pattern.sub(lambda _match: replacement, block, count=1)
    return text[: task.start] + new_block + text[task.end :]


def replace_snapshot_field(text: str, key: str, value: str) -> str:
    body = section(text, "Active execution snapshot")
    if not body:
        raise ValueError("Missing Active execution snapshot")
    pattern = re.compile(rf"^\| {re.escape(key)} \| .+? \|$", re.MULTILINE)
    if len(pattern.findall(body)) != 1:
        raise ValueError(f"Execution snapshot: expected one {key} field")
    new_body = pattern.sub(f"| {key} | `{value}` |", body, count=1)
    start = text.index(body)
    return text[:start] + new_body + text[start + len(body) :]


def validate_status_transition(
    task: Task,
    new_status: str,
    by_id: dict[str, Task],
    waivers: dict[str, Waiver] | None = None,
) -> None:
    if new_status == task.status:
        return
    if new_status not in ALLOWED_TRANSITIONS[task.status]:
        raise ValueError(
            f"{task.task_id}: illegal status transition {task.status} -> {new_status}"
        )
    if new_status in {"READY", "IN_PROGRESS"}:
        waivers = waivers or {}
        incomplete = [
            dependency
            for dependency in task.dependencies
            if not dependency_satisfied(task, by_id[dependency], waivers)
        ]
        if incomplete:
            raise ValueError(
                f"{task.task_id}: cannot become {new_status}; incomplete dependencies: "
                + ", ".join(incomplete)
            )


def atomic_write_text(path: Path, text: str) -> None:
    original_mode = stat.S_IMODE(path.stat().st_mode)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary_path, original_mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def project_root_for_tasks(tasks_path: Path) -> Path:
    """Return the project root for the canonical or a standalone task ledger."""

    resolved = tasks_path.resolve()
    folded_tail = tuple(part.casefold() for part in resolved.parts[-3:])
    canonical_tail = tuple(part.casefold() for part in CANONICAL_TASKS_PATH.parts)
    if folded_tail == canonical_tail:
        return resolved.parents[2]
    return resolved.parent


def load_bootstrap_doctor():
    """Load the sibling doctor so both runtimes use one contract grammar."""

    module_name = "_fastlane_bootstrap_doctor_for_task_waves"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    module_path = Path(__file__).resolve().with_name("bootstrap_doctor.py")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ValueError("Unable to load scripts/bootstrap_doctor.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def validate_gate_b_design_contract_binding(
    tasks_path: Path,
    tasks_text: str,
    prd_text: str,
) -> None:
    """Reject a current plan whose Gate B hash no longer matches its PRD."""

    root = project_root_for_tasks(tasks_path)
    manifest_path = root / "bootstrap.manifest.json"
    # Standalone task-ledger fixtures intentionally exercise the reusable engine
    # without the full template surface. Canonical Fastlane projects always carry
    # the manifest, so only those projects can claim Gate B hash freshness.
    if not manifest_path.exists():
        if (root / "bootstrap.py").exists() or (root / "AGENTS.md").exists():
            raise ValueError(
                "bootstrap.manifest.json is required for Fastlane task execution"
            )
        return
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("bootstrap.manifest.json must be a regular file")
    snapshot = parse_snapshot(tasks_text)
    if snapshot.get("Task-plan state") != "CURRENT":
        return
    doctor = load_bootstrap_doctor()
    contract, issues = doctor.derive_design_contract(
        prd_text,
        snapshot.get("Design revision"),
        required=True,
        grandfather_approved_v1=True,
    )
    if issues or contract.status != "READY" or contract.canonical_sha256 is None:
        detail = "; ".join(issues) if issues else contract.status
        raise ValueError(
            "Current PRD design contract is not ready for task execution: " + detail
        )
    envelope = doctor.table_after_heading(prd_text, "## 28. Construction envelope")
    observed_hash = doctor.clean_cell(envelope.get("Design contract SHA-256", ""))
    if observed_hash != contract.canonical_sha256:
        raise ValueError(
            "Gate B design contract hash is stale; rerun DESIGN-10 and obtain "
            "current Gate B approval before task execution"
        )
    envelope_digest = doctor.canonical_envelope_sha256(prd_text)
    document = doctor.table_after_heading(prd_text, "## Document status")
    agent = doctor.table_after_heading(prd_text, "## 27. Gate B agent review record")
    owner = doctor.table_after_heading(
        prd_text, "## 29. Gate B owner authorization record"
    )
    expected_revisions = {
        "Requirements revision reviewed": snapshot.get("Requirements revision"),
        "Design revision reviewed": snapshot.get("Design revision"),
        "Construction authorization ID reviewed": snapshot.get(
            "Construction authorization"
        ),
    }
    expected_owner_revisions = {
        "Authorized requirements revision": snapshot.get("Requirements revision"),
        "Authorized design revision": snapshot.get("Design revision"),
        "Authorized construction authorization ID": snapshot.get(
            "Construction authorization"
        ),
    }
    gate_b_binding_valid = (
        document.get("Gate A derived status") == "APPROVED_FOR_DESIGN"
        and document.get("Gate B derived status") == "APPROVED_FOR_CONSTRUCTION"
        and all(agent.get(key) == value for key, value in expected_revisions.items())
        and agent.get("Construction envelope SHA-256 reviewed") == envelope_digest
        and agent.get("Agent recommendation") == "READY_FOR_CONSTRUCTION_APPROVAL"
        and all(
            agent.get(key) == "NONE"
            for key in (
                "PRD completeness gaps",
                "Requirement-to-design-and-test traceability gaps",
                "Unresolved risk or preservation gaps",
            )
        )
        and owner.get("Owner decision") == "APPROVED"
        and all(
            owner.get(key) == value for key, value in expected_owner_revisions.items()
        )
        and owner.get("Authorized construction envelope SHA-256") == envelope_digest
        and owner.get("Derived Gate B state") == "APPROVED_FOR_CONSTRUCTION"
        and owner.get("Verbatim owner receipt") == "RECORDED_BELOW"
        and doctor.explicit_human_approver(owner.get("Approver", ""))
        and doctor.explicit_timestamp(owner.get("Authorization provided at", ""))
        and doctor.explicit_value(owner.get("Authorization source", ""))
    )
    expected_receipt = "\n".join(
        [
            "APPROVE PRD AND CONSTRUCTION GATE B",
            f"Requirements revision: {snapshot.get('Requirements revision')}",
            f"Design revision: {snapshot.get('Design revision')}",
            "Construction authorization: " + snapshot.get("Construction authorization"),
            f"Construction envelope SHA-256: {envelope_digest}",
            "Use the proposed construction envelope above.",
            f"Approver: {owner.get('Approver', '')}",
        ]
    )
    try:
        receipt_matches = doctor.marked_receipt(prd_text, "gate-b") == expected_receipt
    except ValueError:
        receipt_matches = False
    if not gate_b_binding_valid or not receipt_matches:
        raise ValueError(
            "Gate B approval binding is stale; rerun DESIGN-20 and obtain current "
            "owner approval before task execution"
        )


def approved_contract_for_tasks(
    tasks_path: Path,
    tasks_text: str | None = None,
) -> ApprovedTaskContract | None:
    """Read approved TECH and property execution rows for a Fastlane ledger."""

    root = project_root_for_tasks(tasks_path)
    prd_path = root / "docs" / "project" / "PRD.md"
    if not prd_path.exists():
        if (root / "bootstrap.manifest.json").exists() or (
            root / "bootstrap.py"
        ).exists():
            raise ValueError(
                "docs/project/PRD.md is required for Fastlane task execution"
            )
        return None
    if not prd_path.is_file() or prd_path.is_symlink():
        raise ValueError("docs/project/PRD.md must be a regular file")
    prd_text = strip_generated_summary(prd_path.read_text(encoding="utf-8"))
    if tasks_text is None:
        if not tasks_path.is_file() or tasks_path.is_symlink():
            raise ValueError("TASKS.md must be a regular file")
        tasks_text = tasks_path.read_text(encoding="utf-8")
    validate_gate_b_design_contract_binding(tasks_path, tasks_text, prd_text)
    doctor = load_bootstrap_doctor()
    try:
        technology_table = doctor.contract_table_after_heading(
            prd_text,
            doctor.TECHNOLOGY_DECISION_HEADING,
            doctor.TECHNOLOGY_DECISION_HEADERS,
        )
    except ValueError as exc:
        raise ValueError(
            f"docs/project/PRD.md technology decision register: {exc}"
        ) from exc
    if technology_table is None:
        raise ValueError(
            "docs/project/PRD.md must contain exactly one technology decision register"
        )
    technology_decisions = [
        doctor.TechnologyDecision(*row) for row in technology_table.rows
    ]
    approved = [decision.decision_id for decision in technology_decisions]
    if len(approved) != len(set(approved)):
        raise ValueError("docs/project/PRD.md has duplicate technology decision IDs")
    technology_by_id = {
        decision.decision_id: decision for decision in technology_decisions
    }
    property_execution, _table_present = parse_property_execution_rows(
        prd_text, "docs/project/PRD.md"
    )
    unknown_frameworks = sorted(
        {
            row.framework_tech_id
            for row in property_execution.values()
            if row.framework_tech_id not in approved
        }
    )
    if unknown_frameworks:
        raise ValueError(
            "docs/project/PRD.md property execution rows reference unknown TECH IDs: "
            + ", ".join(unknown_frameworks)
        )
    enriched_property_execution: dict[str, PropertyExecutionRow] = {}
    for property_id, execution in property_execution.items():
        framework = technology_by_id[execution.framework_tech_id]
        if framework.concern != "PROPERTY_TESTING":
            raise ValueError(
                f"docs/project/PRD.md {property_id} Framework TECH ID must reference "
                "the PROPERTY_TESTING decision"
            )
        enriched_property_execution[property_id] = PropertyExecutionRow(
            execution.property_id,
            execution.framework_tech_id,
            execution.exact_command,
            execution.run_target_time_bound,
            execution.seed_or_reproduction_format,
            execution.evidence_destination,
            framework.selection,
            framework.version_policy,
        )
    approved_harness: dict[str, HarnessExecutionRow] = {}
    requirement_rules: dict[str, tuple[str, str]] | None = None
    requirement_evidence: dict[str, tuple[str, tuple[str, ...]]] | None = None
    approved_delivery: ApprovedDeliveryContract | None = None
    if (root / "bootstrap.manifest.json").exists():
        execution_snapshot = parse_snapshot(tasks_text)
        design_revision = execution_snapshot.get("Design revision")
        design_contract, design_issues = doctor.derive_design_contract(
            prd_text,
            design_revision,
            required=True,
            grandfather_approved_v1=True,
        )
        if design_issues:
            raise ValueError(
                "docs/project/PRD.md design contract is not current: "
                + "; ".join(design_issues)
            )
        approved_harness = {
            row.harness_id: HarnessExecutionRow(
                row.harness_id,
                row.layer,
                row.selected_check,
                row.trigger,
                row.basis_ids,
                row.exact_command,
                row.evidence_destination,
                row.requirement_status,
            )
            for row in design_contract.harness.rows
            if row.harness_id in design_contract.harness.required_ids
        }
        project_contract = design_contract.project_contract
        source_disposition = project_contract.application_source_disposition
        source_kind = (
            source_disposition.kind if source_disposition is not None else None
        )
        source_paths = (
            source_disposition.paths if source_disposition is not None else ()
        )
        if project_contract.grandfathered_v4:
            approved_delivery = ApprovedDeliveryContract(grandfathered=True)
        elif project_contract.first_wave is None:
            approved_delivery = ApprovedDeliveryContract(
                grandfathered=False,
                application_source_kind=source_kind,
                application_source_paths=source_paths,
            )
        else:
            first_wave = project_contract.first_wave
            approved_spike: ApprovedSpikeContract | None = None
            if first_wave.blocking_spike_id is not None:
                spike = project_contract.spike
                if spike is None or spike.spike_id != first_wave.blocking_spike_id:
                    raise ValueError(
                        "docs/project/PRD.md approved blocking spike is unavailable"
                    )
                match = re.fullmatch(r"MAX_ATTEMPTS: ([1-9]\d*)", spike.time_box)
                if match is None:
                    raise ValueError(
                        f"docs/project/PRD.md {spike.spike_id} has an invalid time box"
                    )
                disposable_boundaries = tuple(
                    validate_write_boundary(
                        spike.disposable_boundary,
                        f"docs/project/PRD.md {spike.spike_id}",
                    )
                )
                approved_spike = ApprovedSpikeContract(
                    spike_id=spike.spike_id,
                    max_attempts=int(match.group(1)),
                    disposable_boundaries=disposable_boundaries,
                    exit_criterion=spike.exit_criterion,
                )
            approved_delivery = ApprovedDeliveryContract(
                grandfathered=False,
                wave_contract_id=first_wave.wave_contract_id,
                journey_id=first_wave.journey_id,
                requirement_ids=first_wave.requirement_ids,
                acceptance_test_ids=first_wave.acceptance_test_ids,
                harness_id=first_wave.harness_id,
                application_source_kind=source_kind,
                application_source_paths=source_paths,
                spike=approved_spike,
            )
        try:
            requirements_document = doctor.table_after_heading(
                prd_text, "## Document status"
            )
        except ValueError:
            requirements_document = {}
        repository_mode = doctor.clean_cell(
            requirements_document.get("Repository mode", "")
        ).lower()
        intake_contract, _intake_issues = doctor.derive_intake_foundation_contract(
            prd_text,
            repository_mode if repository_mode in doctor.PROJECT_MODES else None,
            grandfather_current_gate_a=True,
        )
        requirements_contract, requirements_issues = (
            doctor.derive_requirements_contract(
                prd_text,
                doctor.clean_cell(requirements_document.get("Effective risk", ""))
                or None,
                intake_contract,
                required=True,
                grandfather_current_gate_a=True,
            )
        )
        if requirements_issues or requirements_contract.status not in {
            "READY",
            "GRANDFATHERED",
        }:
            issue_text = "; ".join(
                f"{code}: {message}" for code, message in requirements_issues
            )
            if not issue_text:
                issue_text = f"status={requirements_contract.status}"
            raise ValueError(
                "docs/project/PRD.md requirements contract is not current: "
                + issue_text
            )
        requirement_rules = doctor.task_requirement_rules(
            prd_text, requirements_contract
        )
        verify_path = tasks_path.with_name("VERIFY.md")
        verify_text: str | None = None
        if verify_path.exists():
            if not verify_path.is_file() or verify_path.is_symlink():
                raise ValueError("docs/project/VERIFY.md must be a regular file")
            verify_text = strip_generated_summary(
                verify_path.read_text(encoding="utf-8")
            )
        requirement_evidence, evidence_issues = (
            doctor.task_requirement_evidence_dispositions(
                verify_text,
                {
                    "Requirements revision": execution_snapshot.get(
                        "Requirements revision"
                    ),
                    "Design revision": execution_snapshot.get("Design revision"),
                    "Construction authorization": execution_snapshot.get(
                        "Construction authorization"
                    ),
                },
                requirement_rules,
            )
        )
        if evidence_issues:
            raise ValueError(
                "docs/project/VERIFY.md requirement evidence is invalid: "
                + "; ".join(evidence_issues)
            )
    return ApprovedTaskContract(
        frozenset(approved),
        enriched_property_execution,
        approved_harness,
        approved_delivery,
        requirement_rules,
        requirement_evidence,
    )


def approved_tech_ids_for_tasks(
    tasks_path: Path,
    tasks_text: str | None = None,
) -> set[str] | None:
    """Compatibility view of the approved technology IDs."""

    contract = approved_contract_for_tasks(tasks_path, tasks_text)
    return set(contract.technology_ids) if contract is not None else None


def approved_contract_values(
    tasks_path: Path,
    tasks_text: str | None = None,
) -> tuple[set[str] | None, dict[str, PropertyExecutionRow] | None]:
    """Compatibility view retained for callers that do not consume Harness rows."""

    contract = approved_contract_for_tasks(tasks_path, tasks_text)
    if contract is None:
        return None, None
    return set(contract.technology_ids), contract.property_execution


def approved_contract_components(
    tasks_path: Path,
    tasks_text: str | None = None,
) -> tuple[
    set[str] | None,
    dict[str, PropertyExecutionRow] | None,
    dict[str, HarnessExecutionRow] | None,
]:
    contract = approved_contract_for_tasks(tasks_path, tasks_text)
    if contract is None:
        return None, None, None
    return (
        set(contract.technology_ids),
        contract.property_execution,
        contract.harness,
    )


def execution_contract_components(
    contract: ApprovedTaskContract | None,
) -> tuple[
    set[str] | None,
    dict[str, PropertyExecutionRow] | None,
    dict[str, HarnessExecutionRow] | None,
    ApprovedDeliveryContract | None,
]:
    if contract is None:
        return None, None, None, None
    return (
        set(contract.technology_ids),
        contract.property_execution,
        contract.harness,
        contract.delivery,
    )


def execution_contract_kwargs(
    contract: ApprovedTaskContract | None,
) -> dict[str, object]:
    keys = (
        "approved_tech_ids",
        "approved_property_execution",
        "approved_harness",
        "approved_delivery",
    )
    kwargs = dict(zip(keys, execution_contract_components(contract)))
    kwargs["approved_requirement_rules"] = (
        contract.requirement_rules if contract is not None else None
    )
    kwargs["approved_requirement_evidence"] = (
        contract.requirement_evidence if contract is not None else None
    )
    return kwargs


def coordinator_ledger_paths(tasks_path: Path) -> set[str]:
    """Return the exact project-relative files a coordinator may reconcile."""

    root = project_root_for_tasks(tasks_path)
    verify_path = tasks_path.with_name("VERIFY.md").resolve()
    try:
        tasks_relative = tasks_path.resolve().relative_to(root).as_posix()
        verify_relative = verify_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("Task ledger is outside its derived project root") from exc
    return {tasks_relative, verify_relative, "bootstrap.yaml"}


def canonical_verify_reference(tasks_path: Path, fragment: str) -> str:
    """Return a project-relative evidence reference for the paired ledger."""

    root = project_root_for_tasks(tasks_path)
    verify_path = tasks_path.with_name("VERIFY.md").resolve()
    try:
        relative = verify_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(
            "Verification ledger is outside its derived project root"
        ) from exc
    return f"{relative}#{fragment}"


def read_bootstrap_state(tasks_path: Path) -> tuple[Path, dict[str, object]]:
    state_path = project_root_for_tasks(tasks_path) / "bootstrap.yaml"
    if not state_path.exists():
        raise ValueError("bootstrap.yaml is required for every ledger mutation")
    if not state_path.is_file() or state_path.is_symlink():
        raise ValueError("bootstrap.yaml must be a regular file for ledger mutations")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read bootstrap.yaml: {exc}") from exc
    if not isinstance(state, dict) or not isinstance(state.get("execution"), dict):
        raise ValueError("bootstrap.yaml execution state is malformed")
    if not isinstance(state.get("lifecycle"), dict):
        raise ValueError("bootstrap.yaml lifecycle state is malformed")
    return state_path, state


def expected_execution_fields(tasks_text: str) -> dict[str, object]:
    snapshot = parse_snapshot(tasks_text)
    tasks = parse_tasks(tasks_text)
    validate_snapshot(snapshot)
    plan = snapshot.get("Task-plan revision")
    active_run = snapshot.get("Active run ID")
    coordinator = snapshot.get("Coordinator")
    state_map = {
        "NOT_STARTED": "IDLE",
        "RUNNING": "RUNNING",
        "PAUSED": "CHECKPOINTED",
        "BLOCKED": "BLOCKED",
        "COMPLETE": "COMPLETE",
    }
    return {
        "plan_revision": None if plan == "UNINITIALIZED" else plan,
        "plan_state": snapshot.get("Task-plan state"),
        "run_id": None if active_run == "NONE" else active_run,
        "coordinator": None
        if coordinator in {"NONE", "UNASSIGNED", ""}
        else coordinator,
        "state": state_map[snapshot.get("Run state")],
        "active_tasks": sorted(
            task.task_id for task in tasks if task.status == "IN_PROGRESS"
        ),
        "attempts": {task.task_id: task.attempts_used for task in tasks},
    }


def preflight_state_matches_tasks(
    tasks_path: Path,
    tasks_text: str,
) -> ApprovedTaskContract | None:
    """Refuse mutations when a prior partial write or manual edit caused drift."""

    loaded = read_bootstrap_state(tasks_path)
    _state_path, state = loaded
    execution = state["execution"]
    lifecycle = state["lifecycle"]
    assert isinstance(execution, dict)
    assert isinstance(lifecycle, dict)
    snapshot = parse_snapshot(tasks_text)
    tasks = parse_tasks(tasks_text)
    approved_contract = approved_contract_for_tasks(tasks_path, tasks_text)
    contract_kwargs = execution_contract_kwargs(approved_contract)
    validate(tasks, snapshot, parse_waivers(tasks_text), **contract_kwargs)
    for task in tasks:
        if task.status == "DONE":
            validate_done_evidence_file(
                tasks_path,
                task,
                contract_kwargs["approved_property_execution"],
                contract_kwargs["approved_harness"],
                tasks_text,
            )

    snapshot_lifecycle = {
        "requirements_revision": snapshot.get("Requirements revision"),
        "design_revision": snapshot.get("Design revision"),
        "construction_authorization": snapshot.get("Construction authorization"),
        "gate_b": snapshot.get("Gate B state"),
    }
    lifecycle_drift = [
        key for key, value in snapshot_lifecycle.items() if lifecycle.get(key) != value
    ]
    expected = expected_execution_fields(tasks_text)
    execution_drift = [
        key for key, value in expected.items() if execution.get(key) != value
    ]

    state_name = expected["state"]
    if state_name == "IDLE":
        if execution.get("mode") != "NONE" or execution.get("basis") is not None:
            execution_drift.extend(["mode", "basis"])
        if execution.get("last_checkpoint") is not None:
            execution_drift.append("last_checkpoint")
    else:
        if execution.get("mode") not in {"SINGLE_TASK", "AUTONOMOUS"}:
            execution_drift.append("mode")
        expected_basis = {
            "requirements_revision": lifecycle.get("requirements_revision"),
            "design_revision": lifecycle.get("design_revision"),
            "construction_authorization": lifecycle.get("construction_authorization"),
        }
        if execution.get("basis") != expected_basis:
            execution_drift.append("basis")
        checkpoint = execution.get("last_checkpoint")
        checkpoint_id = checkpoint.get("id") if isinstance(checkpoint, dict) else None
        snapshot_checkpoint = snapshot.get("Last checkpoint")
        if state_name in {"CHECKPOINTED", "BLOCKED", "COMPLETE"}:
            if checkpoint_id != snapshot_checkpoint:
                execution_drift.append("last_checkpoint")
        elif checkpoint is not None and checkpoint_id != snapshot_checkpoint:
            execution_drift.append("last_checkpoint")

    drift = [*(f"lifecycle.{key}" for key in lifecycle_drift), *execution_drift]
    if drift:
        raise ValueError(
            "TASKS.md does not match bootstrap.yaml; reconcile before mutation: "
            + ", ".join(sorted(set(drift)))
        )
    return approved_contract


def mirror_state_text(
    tasks_path: Path,
    tasks_text: str,
    *,
    run_mode: str | None = None,
) -> tuple[Path, str]:
    """Build the derived bootstrap state matching a validated TASKS document."""

    loaded = read_bootstrap_state(tasks_path)
    state_path, state = loaded

    snapshot = parse_snapshot(tasks_text)
    tasks = parse_tasks(tasks_text)
    execution = state["execution"]
    lifecycle = state["lifecycle"]
    assert isinstance(execution, dict)
    assert isinstance(lifecycle, dict)
    snapshot_lifecycle = {
        "requirements_revision": snapshot.get("Requirements revision"),
        "design_revision": snapshot.get("Design revision"),
        "construction_authorization": snapshot.get("Construction authorization"),
        "gate_b": snapshot.get("Gate B state"),
    }
    if any(lifecycle.get(key) != value for key, value in snapshot_lifecycle.items()):
        raise ValueError("TASKS snapshot does not match bootstrap.yaml lifecycle")
    plan = snapshot.get("Task-plan revision")
    execution["plan_revision"] = None if plan == "UNINITIALIZED" else plan
    execution["plan_state"] = snapshot.get("Task-plan state")
    active_run = snapshot.get("Active run ID")
    execution["run_id"] = None if active_run == "NONE" else active_run
    coordinator = snapshot.get("Coordinator")
    execution["coordinator"] = (
        None if coordinator in {"NONE", "UNASSIGNED", ""} else coordinator
    )
    state_map = {
        "NOT_STARTED": "IDLE",
        "RUNNING": "RUNNING",
        "PAUSED": "CHECKPOINTED",
        "BLOCKED": "BLOCKED",
        "COMPLETE": "COMPLETE",
    }
    execution["state"] = state_map[snapshot.get("Run state")]
    if execution["state"] == "IDLE":
        execution["mode"] = "NONE"
        execution["basis"] = None
        execution["active_tasks"] = []
        execution["last_checkpoint"] = None
    else:
        if run_mode is not None:
            execution["mode"] = run_mode
        elif execution.get("mode") not in {"SINGLE_TASK", "AUTONOMOUS"}:
            raise ValueError("Active run has no valid persisted execution mode")
        execution["basis"] = {
            "requirements_revision": lifecycle.get("requirements_revision"),
            "design_revision": lifecycle.get("design_revision"),
            "construction_authorization": lifecycle.get("construction_authorization"),
        }
        execution["active_tasks"] = sorted(
            task.task_id for task in tasks if task.status == "IN_PROGRESS"
        )
        checkpoint = snapshot.get("Last checkpoint")
        if execution["state"] in {
            "CHECKPOINTED",
            "BLOCKED",
            "COMPLETE",
        } and checkpoint in {
            "",
            "NONE",
        }:
            raise ValueError("Checkpointed run requires a Last checkpoint")
        if checkpoint not in {"", "NONE"}:
            if CHECKPOINT_PATTERN.fullmatch(checkpoint) is None:
                raise ValueError("Active run has an invalid Last checkpoint")
            execution["last_checkpoint"] = {
                "id": checkpoint,
                "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "evidence_ref": canonical_verify_reference(
                    tasks_path, checkpoint.lower()
                ),
            }
    execution["attempts"] = {task.task_id: task.attempts_used for task in tasks}
    return state_path, json.dumps(state, indent=2, sort_keys=False) + "\n"


def write_state_mirror(
    tasks_path: Path, tasks_text: str, *, run_mode: str | None = None
) -> None:
    mirror = mirror_state_text(tasks_path, tasks_text, run_mode=run_mode)
    atomic_write_text(*mirror)


@contextmanager
def task_file_lock(path: Path) -> Iterator[None]:
    lock_key = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / f"task-waves-{lock_key}.lock"
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        try:
            if os.name == "nt":
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError(f"Task file is already being updated: {path}") from exc
        try:
            yield
        finally:
            lock_file.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def load_contract(
    text: str,
    *,
    approved_tech_ids: set[str] | None = None,
    approved_property_execution: dict[str, PropertyExecutionRow] | None = None,
    approved_harness: dict[str, HarnessExecutionRow] | None = None,
    approved_delivery: ApprovedDeliveryContract | None = None,
    approved_requirement_rules: dict[str, tuple[str, str]] | None = None,
    approved_requirement_evidence: dict[str, tuple[str, tuple[str, ...]]] | None = None,
) -> tuple[list[Task], Snapshot, dict[str, Waiver], dict[str, Task]]:
    tasks = parse_tasks(text)
    snapshot = parse_snapshot(text)
    waivers = parse_waivers(text)
    by_id = validate(
        tasks,
        snapshot,
        waivers,
        approved_tech_ids=approved_tech_ids,
        approved_property_execution=approved_property_execution,
        approved_harness=approved_harness,
        approved_delivery=approved_delivery,
        approved_requirement_rules=approved_requirement_rules,
        approved_requirement_evidence=approved_requirement_evidence,
    )
    compute_waves(tasks, by_id)
    return tasks, snapshot, waivers, by_id


def synchronize_current_wave(
    text: str,
    *,
    approved_tech_ids: set[str] | None = None,
    approved_property_execution: dict[str, PropertyExecutionRow] | None = None,
    approved_harness: dict[str, HarnessExecutionRow] | None = None,
    approved_delivery: ApprovedDeliveryContract | None = None,
    approved_requirement_rules: dict[str, tuple[str, str]] | None = None,
    approved_requirement_evidence: dict[str, tuple[str, tuple[str, ...]]] | None = None,
) -> str:
    """Advance the coordinator snapshot to the lowest runnable/active wave."""

    tasks, snapshot, waivers, by_id = load_contract(
        text,
        approved_tech_ids=approved_tech_ids,
        approved_property_execution=approved_property_execution,
        approved_harness=approved_harness,
        approved_delivery=approved_delivery,
        approved_requirement_rules=approved_requirement_rules,
        approved_requirement_evidence=approved_requirement_evidence,
    )
    if snapshot.get("Run state") != "RUNNING":
        return text
    waves = compute_waves(tasks, by_id)
    candidates = [
        *[task for task in tasks if task.status == "IN_PROGRESS"],
        *ready_tasks(tasks, by_id, waivers),
    ]
    next_wave = (
        str(min(waves[task.task_id] for task in candidates)) if candidates else "NONE"
    )
    if snapshot.get("Current wave") == next_wave:
        return text
    return replace_snapshot_field(text, "Current wave", next_wave)


def task_write_set_conflicts_with_paths(task: Task, paths: list[str]) -> bool:
    writes = validate_write_boundary(task.metadata["Write set"], task.task_id)
    return any(
        write_boundaries_overlap(write, protected)
        for write in writes
        for protected in paths
    )


def validate_claim_safety(
    task: Task,
    tasks: list[Task],
    snapshot: Snapshot,
    waves: dict[str, int],
    *,
    owner: str,
    coordinator: str,
    isolated_worktrees: bool,
) -> None:
    expected_coordinator = snapshot.get("Coordinator")
    if expected_coordinator in {"", "NONE", "UNASSIGNED", "TODO"}:
        raise ValueError("Claim requires an assigned run coordinator")
    if coordinator != expected_coordinator:
        raise ValueError("Claim coordinator does not match the active run coordinator")
    maximum_workers = parse_nonnegative_int(snapshot.get("Maximum workers"), minimum=1)
    if maximum_workers != 1:
        raise ValueError("Claim requires Maximum workers = 1")
    if owner != expected_coordinator:
        raise ValueError("Mutable task claims require coordinator ownership")
    active = [item for item in tasks if item.status == "IN_PROGRESS"]
    if active:
        raise ValueError("A mutable task is already IN_PROGRESS; serialize task claims")
    protected = validate_write_boundary(
        snapshot.get("Protected dirty paths"),
        "Execution snapshot Protected dirty paths",
    )
    if task_write_set_conflicts_with_paths(task, protected):
        raise ValueError(f"{task.task_id}: Write set overlaps Protected dirty paths")
    writes = validate_write_boundary(task.metadata["Write set"], task.task_id)
    if (
        any(is_control_boundary(path) for path in writes)
        and owner != expected_coordinator
    ):
        raise ValueError(
            f"{task.task_id}: shared control paths require coordinator ownership"
        )
    current_wave = snapshot.get("Current wave")
    task_wave = str(waves[task.task_id])
    if current_wave != task_wave:
        raise ValueError(
            f"{task.task_id}: structural wave {task_wave} is outside Current wave {current_wave}"
        )


def safe_ready_candidates(
    tasks: list[Task],
    by_id: dict[str, Task],
    waivers: dict[str, Waiver],
    snapshot: Snapshot,
    waves: dict[str, int],
    *,
    isolated_worktrees: bool,
) -> tuple[list[Task], int]:
    active = [task for task in tasks if task.status == "IN_PROGRESS"]
    maximum_workers = parse_nonnegative_int(snapshot.get("Maximum workers"), minimum=1)
    if maximum_workers != 1:
        raise ValueError("Maximum workers must be exactly 1")
    available_slots = 0 if active else 1
    if not available_slots:
        return [], available_slots
    protected = validate_write_boundary(
        snapshot.get("Protected dirty paths"),
        "Execution snapshot Protected dirty paths",
    )
    current_wave = snapshot.get("Current wave")
    candidates = [
        task
        for task in ready_tasks(tasks, by_id, waivers)
        if str(waves[task.task_id]) == current_wave
        and not task_write_set_conflicts_with_paths(task, protected)
        and all(not tasks_conflict(task, running) for running in active)
    ]
    return candidates, available_slots


def mutate_task_file(
    path: Path,
    task_id: str,
    updates: dict[str, str],
    *,
    coordinator: str,
    new_status: str | None = None,
    expected_run_id: str | None = None,
) -> bool:
    with task_file_lock(path):
        text = path.read_text(encoding="utf-8")
        approved_contract = preflight_state_matches_tasks(path, text)
        contract_kwargs = execution_contract_kwargs(approved_contract)
        tasks, snapshot, waivers, by_id = load_contract(text, **contract_kwargs)
        require_current_plan(snapshot, "Task mutation")
        require_active_coordinator(snapshot, coordinator, "Task mutation")
        if task_id not in by_id:
            raise ValueError(f"Unknown task ID: {task_id}")
        task = by_id[task_id]
        if task.status == "IN_PROGRESS" and new_status and new_status != "IN_PROGRESS":
            if (
                expected_run_id is None
                or expected_run_id != task.run_id
                or snapshot.get("Active run ID") != task.run_id
                or snapshot.get("Run state") != "RUNNING"
            ):
                raise ValueError(
                    f"{task_id}: --run-id must match the active run that owns the task"
                )
            if new_status.upper() in {"DONE", "BLOCKED"}:
                next_checkpoint = clean(updates.get("Last checkpoint", ""))
                if CHECKPOINT_PATTERN.fullmatch(next_checkpoint) is None:
                    raise ValueError(
                        f"{task_id}: IN_PROGRESS reconciliation requires a new --checkpoint"
                    )
                if next_checkpoint == clean(task.metadata.get("Last checkpoint", "")):
                    raise ValueError(
                        f"{task_id}: reconciliation checkpoint must advance"
                    )
                prior_checkpoints = [
                    snapshot.get("Last checkpoint"),
                    *(
                        clean(item.metadata.get("Last checkpoint", ""))
                        for item in tasks
                    ),
                    *(row.checkpoint_id for row in parse_checkpoint_rows(text)),
                ]
                if checkpoint_ordinal(next_checkpoint) <= max(
                    (checkpoint_ordinal(value) for value in prior_checkpoints),
                    default=-1,
                ):
                    raise ValueError(
                        f"{task_id}: reconciliation checkpoint must be globally monotonic and unused"
                    )
        if new_status:
            new_status = new_status.upper()
            if new_status not in ALLOWED_STATUSES:
                raise ValueError(f"Invalid status {new_status!r}")
            validate_status_transition(task, new_status, by_id, waivers)
            updates = {**updates, "Status": new_status}
        if all(
            clean(task.metadata.get(key, "")) == value for key, value in updates.items()
        ):
            return False
        for key, value in updates.items():
            current_tasks = parse_tasks(text)
            current = next(item for item in current_tasks if item.task_id == task_id)
            text = replace_metadata(text, current, key, value)
        current_tasks = parse_tasks(text)
        current = next(item for item in current_tasks if item.task_id == task_id)
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        text = replace_metadata(text, current, "Last updated", timestamp)
        if (
            task.status == "IN_PROGRESS"
            and new_status is not None
            and new_status.upper() in {"DONE", "BLOCKED"}
        ):
            text = replace_snapshot_field(
                text, "Last checkpoint", clean(updates["Last checkpoint"])
            )
        if new_status is not None and new_status.upper() == "DONE":
            updated_task = next(
                item for item in parse_tasks(text) if item.task_id == task_id
            )
            validate_done_evidence_file(
                path,
                updated_task,
                contract_kwargs["approved_property_execution"],
                contract_kwargs["approved_harness"],
                text,
            )
        text = synchronize_current_wave(text, **contract_kwargs)
        load_contract(text, **contract_kwargs)
        # State is replaced first. If the subsequent TASKS replacement fails,
        # doctor detects the mismatch and requires reconciliation rather than
        # allowing a silently divergent run.
        write_state_mirror(path, text)
        atomic_write_text(path, text)
        return True


def update_task_file(
    path: Path,
    task_id: str,
    *,
    coordinator: str,
    status: str | None = None,
    issue: str | None = None,
    evidence: str | None = None,
    blocker: str | None = None,
    skip_record: str | None = None,
    run_id: str | None = None,
    checkpoint: str | None = None,
) -> bool:
    updates: dict[str, str] = {}
    if run_id is not None:
        run_id = run_id.strip()
        if RUN_ID_PATTERN.fullmatch(run_id) is None:
            raise ValueError(f"Invalid run ID: {run_id!r}")
    if issue is not None:
        issue = issue.strip()
        if not issue or "\n" in issue or "\r" in issue:
            raise ValueError("GitHub issue must be a non-empty single-line value")
        updates["GitHub issue"] = issue
    for key, value in (
        ("Evidence", evidence),
        ("Blocker", blocker),
        ("Skip record", skip_record),
        ("Last checkpoint", checkpoint),
    ):
        if value is not None:
            value = value.strip()
            if not value or "\n" in value or "\r" in value:
                raise ValueError(f"{key} must be a non-empty single-line value")
            if key == "Last checkpoint" and CHECKPOINT_PATTERN.fullmatch(value) is None:
                raise ValueError(f"Invalid checkpoint: {value!r}")
            updates[key] = value
    if status and status.upper() in {"DONE", "BLOCKED"}:
        updates["Run ID"] = "NONE"
    if status and status.upper() in {"BACKLOG", "READY", "SKIPPED"}:
        updates["Run ID"] = "NONE"
        updates["Owner"] = "UNASSIGNED"
    return mutate_task_file(
        path,
        task_id,
        updates,
        coordinator=coordinator,
        new_status=status,
        expected_run_id=run_id,
    )


def claim_task_file(
    path: Path,
    task_id: str,
    *,
    owner: str,
    coordinator: str,
    run_id: str,
    checkpoint: str,
    isolated_worktrees: bool = False,
) -> bool:
    owner = owner.strip()
    coordinator = coordinator.strip()
    run_id = run_id.strip()
    checkpoint = checkpoint.strip()
    for label, value in (
        ("owner", owner),
        ("coordinator", coordinator),
        ("run ID", run_id),
        ("checkpoint", checkpoint),
    ):
        if (
            not value
            or value in {"NONE", "UNASSIGNED"}
            or "\n" in value
            or "\r" in value
        ):
            raise ValueError(f"Invalid {label}: {value!r}")
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError(f"Invalid run ID: {run_id!r}")
    if CHECKPOINT_PATTERN.fullmatch(checkpoint) is None:
        raise ValueError(f"Invalid checkpoint: {checkpoint!r}")
    with task_file_lock(path):
        text = path.read_text(encoding="utf-8")
        approved_contract = preflight_state_matches_tasks(path, text)
        contract_kwargs = execution_contract_kwargs(approved_contract)
        tasks, snapshot, waivers, by_id = load_contract(text, **contract_kwargs)
        require_current_plan(snapshot, "Claim")
        if task_id not in by_id:
            raise ValueError(f"Unknown task ID: {task_id}")
        task = by_id[task_id]
        if (
            snapshot.get("Run state") != "RUNNING"
            or snapshot.get("Active run ID") != run_id
        ):
            raise ValueError("Claim run ID does not match the active RUNNING run")
        snapshot_checkpoint = snapshot.get("Last checkpoint")
        base_checkpoint = (
            "CP-0000" if snapshot_checkpoint == "NONE" else snapshot_checkpoint
        )
        if checkpoint != base_checkpoint:
            raise ValueError(
                f"{task_id}: claim checkpoint must equal current base {base_checkpoint}; "
                f"observed {checkpoint}"
            )
        if task.status != "READY":
            raise ValueError(f"{task_id}: only READY tasks may be claimed")
        validate_status_transition(task, "IN_PROGRESS", by_id, waivers)
        if task.attempts_used >= task.attempt_budget:
            raise ValueError(f"{task_id}: attempt budget exhausted")
        waves = compute_waves(tasks, by_id)
        validate_claim_safety(
            task,
            tasks,
            snapshot,
            waves,
            owner=owner,
            coordinator=coordinator,
            isolated_worktrees=isolated_worktrees,
        )
        updates = {
            "Owner": owner,
            "Run ID": run_id,
            "Attempts used": str(task.attempts_used + 1),
            "Last checkpoint": checkpoint,
            "Status": "IN_PROGRESS",
        }
        for key, value in updates.items():
            current = next(
                item for item in parse_tasks(text) if item.task_id == task_id
            )
            text = replace_metadata(text, current, key, value)
        current = next(item for item in parse_tasks(text) if item.task_id == task_id)
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        text = replace_metadata(text, current, "Last updated", timestamp)
        load_contract(text, **contract_kwargs)
        write_state_mirror(path, text)
        atomic_write_text(path, text)
        return True


def mutate_run_snapshot(
    path: Path,
    *,
    operation: str,
    run_id: str,
    coordinator: str,
    checkpoint: str | None = None,
    run_mode: str | None = None,
) -> None:
    coordinator = coordinator.strip()
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError(f"Invalid run ID: {run_id!r}")
    if checkpoint is not None and CHECKPOINT_PATTERN.fullmatch(checkpoint) is None:
        raise ValueError(f"Invalid checkpoint: {checkpoint!r}")
    if operation not in {"start", "resume", "pause", "complete"}:
        raise ValueError(f"Unknown run operation: {operation!r}")
    if operation != "start" and run_mode is not None:
        raise ValueError("Run mode may be selected only when starting a run")
    with task_file_lock(path):
        text = path.read_text(encoding="utf-8")
        approved_contract = preflight_state_matches_tasks(path, text)
        contract_kwargs = execution_contract_kwargs(approved_contract)
        tasks, snapshot, waivers, by_id = load_contract(text, **contract_kwargs)
        require_current_plan(snapshot, operation.capitalize())
        active = snapshot.get("Active run ID")
        state = snapshot.get("Run state")
        if operation == "start":
            if snapshot.get("Task-plan revision") == "UNINITIALIZED":
                raise ValueError(
                    "Cannot start a run before TASK-10 creates a task plan"
                )
            if snapshot.get("Gate B state") != "APPROVED_FOR_CONSTRUCTION":
                raise ValueError("Cannot start a run without current Gate B")
            if active != "NONE" or state != "NOT_STARTED":
                raise ValueError("A run already exists or requires reconciliation")
            if snapshot.get("Last checkpoint") != "NONE":
                raise ValueError("A new run requires Last checkpoint NONE")
            if not coordinator or coordinator in {"NONE", "UNASSIGNED"}:
                raise ValueError("Starting a run requires a coordinator")
            if "\n" in coordinator or "\r" in coordinator:
                raise ValueError("Coordinator must be a single-line identity")
            if not tasks:
                raise ValueError("Cannot start a run without generated tasks")
            selected_mode = run_mode or "AUTONOMOUS"
            if selected_mode not in {"SINGLE_TASK", "AUTONOMOUS"}:
                raise ValueError(f"Invalid run mode: {selected_mode!r}")
            runnable = ready_tasks(tasks, by_id, waivers)
            if not runnable:
                raise ValueError("Cannot start a run without a runtime-ready task")
            waves = compute_waves(tasks, by_id)
            current_wave = str(min(waves[task.task_id] for task in runnable))
            text = replace_snapshot_field(text, "Active run ID", run_id)
            text = replace_snapshot_field(text, "Coordinator", coordinator)
            text = replace_snapshot_field(text, "Run state", "RUNNING")
            text = replace_snapshot_field(text, "Current wave", current_wave)
            run_mode = selected_mode
        elif operation == "resume":
            require_active_coordinator(snapshot, coordinator, "Resume")
            if snapshot.get("Gate B state") != "APPROVED_FOR_CONSTRUCTION":
                raise ValueError("Cannot resume without current Gate B")
            if active != run_id or state not in {"PAUSED", "BLOCKED"}:
                raise ValueError("Only the same checkpointed run may resume")
            if any(task.status == "IN_PROGRESS" for task in tasks):
                raise ValueError("Reconcile IN_PROGRESS tasks before resuming")
            persisted_checkpoint = snapshot.get("Last checkpoint")
            checkpoint_row = validate_checkpoint_receipt(
                path,
                text,
                persisted_checkpoint,
                run_id,
                tasks,
                snapshot,
                require_advance=False,
            )
            reconcile_git_state(
                path,
                snapshot,
                action="Resume",
                checkpoint_row=checkpoint_row,
            )
            text = replace_snapshot_field(text, "Run state", "RUNNING")
        else:
            require_active_coordinator(snapshot, coordinator, operation.capitalize())
            if active != run_id or state != "RUNNING":
                raise ValueError("Run ID does not match the active RUNNING run")
            if any(task.status == "IN_PROGRESS" for task in tasks):
                raise ValueError(
                    "Checkpoint requires all active tasks to be reconciled"
                )
            if not checkpoint or checkpoint == "NONE":
                raise ValueError("Checkpoint ID is required")
            terminal = operation == "complete"
            if terminal and any(
                task.status not in {"DONE", "SKIPPED"} for task in tasks
            ):
                raise ValueError("Cannot complete a run with non-terminal tasks")
            checkpoint_row = validate_checkpoint_receipt(
                path,
                text,
                checkpoint,
                run_id,
                tasks,
                snapshot,
            )
            reconcile_git_state(
                path,
                snapshot,
                action=operation.capitalize(),
                checkpoint_row=checkpoint_row,
            )
            text = replace_snapshot_field(text, "Last checkpoint", checkpoint)
            text = replace_snapshot_field(
                text, "Run state", "COMPLETE" if terminal else "PAUSED"
            )
        load_contract(text, **contract_kwargs)
        write_state_mirror(path, text, run_mode=run_mode)
        atomic_write_text(path, text)


def task_to_dict(task: Task, wave: int) -> dict[str, object]:
    try:
        technology_refs = task.technology_refs
    except ValueError:
        technology_refs = []
    return {
        "id": task.task_id,
        "title": task.title,
        "status": task.status,
        "dependencies": task.dependencies,
        "wave": wave,
        "write_set": validate_write_boundary(task.metadata["Write set"], task.task_id),
        "external_state": parse_external_state(
            task.metadata["External state"], task.task_id
        ),
        "aws_mode": task.aws_mode,
        "technology_refs": technology_refs,
        "attempts_used": task.attempts_used,
        "attempt_budget": task.attempt_budget,
        "attempts_remaining": task.attempt_budget - task.attempts_used,
        "github_issue": task.issue,
    }


def print_waves(tasks: list[Task], waves: dict[str, int]) -> None:
    grouped: dict[int, list[Task]] = {}
    for task in tasks:
        grouped.setdefault(waves[task.task_id], []).append(task)
    for wave in sorted(grouped):
        print(f"Structural wave {wave}")
        for task in grouped[wave]:
            deps = ", ".join(task.dependencies) or "NONE"
            print(f"  {task.task_id} [{task.status}] {task.title} (depends on: {deps})")


def validate_cli_contract(args: argparse.Namespace) -> None:
    mutation_names = {
        "start": args.start_run,
        "resume": args.resume_run,
        "pause": args.pause_run,
        "complete": args.complete_run,
        "claim": args.claim,
        "set-status": args.set_status,
        "set-issue": args.set_issue,
    }
    selected = [name for name, value in mutation_names.items() if value is not None]
    if len(selected) > 1:
        raise ValueError("Choose exactly one mutating action per invocation")
    action = selected[0] if selected else None

    queries = [args.ready, args.safe_ready, args.task is not None]
    if sum(bool(value) for value in queries) > 1:
        raise ValueError("Choose only one of --ready, --safe-ready, or --task")
    if action and any(queries):
        raise ValueError("Do not combine a mutating action with a read query")

    allowed_auxiliaries: dict[str | None, set[str]] = {
        "start": {"coordinator", "run_mode"},
        "resume": {"coordinator"},
        "pause": {"coordinator", "checkpoint"},
        "complete": {"coordinator", "checkpoint"},
        "claim": {
            "owner",
            "coordinator",
            "run_id",
            "checkpoint",
            "isolated_worktrees",
        },
        "set-status": {
            "coordinator",
            "evidence",
            "blocker",
            "skip_record",
            "run_id",
            "checkpoint",
        },
        "set-issue": {"coordinator"},
        None: {"isolated_worktrees"} if args.safe_ready else set(),
    }
    provided = {
        name
        for name, value in {
            "coordinator": args.coordinator,
            "run_mode": args.run_mode,
            "owner": args.owner,
            "run_id": args.run_id,
            "checkpoint": args.checkpoint,
            "evidence": args.evidence,
            "blocker": args.blocker,
            "skip_record": args.skip_record,
            "isolated_worktrees": args.isolated_worktrees,
        }.items()
        if value not in {None, False}
    }
    ignored = sorted(provided - allowed_auxiliaries[action])
    if ignored:
        raise ValueError(
            "Options are not valid for this action: "
            + ", ".join(f"--{name.replace('_', '-')}" for name in ignored)
        )

    if action == "claim" and not all(
        (args.owner, args.coordinator, args.run_id, args.checkpoint)
    ):
        raise ValueError(
            "--claim requires --owner, --coordinator, --run-id, and --checkpoint"
        )
    if action == "start" and not args.coordinator:
        raise ValueError("--start-run requires --coordinator")
    if action == "resume" and not args.coordinator:
        raise ValueError("--resume-run requires --coordinator")
    if action in {"pause", "complete"} and not all((args.coordinator, args.checkpoint)):
        raise ValueError(f"--{action}-run requires --coordinator and --checkpoint")
    if action in {"set-status", "set-issue"} and not args.coordinator:
        raise ValueError(f"--{action} requires --coordinator")
    if action == "set-status":
        status = args.set_status[1].upper()
        status_aux = {
            "evidence": args.evidence,
            "blocker": args.blocker,
            "skip_record": args.skip_record,
        }
        permitted_by_status = {
            "DONE": {"evidence"},
            "BLOCKED": {"blocker"},
            "SKIPPED": {"skip_record"},
        }.get(status, set())
        invalid = [
            name
            for name, value in status_aux.items()
            if value and name not in permitted_by_status
        ]
        if invalid:
            raise ValueError(
                f"Auxiliary records do not apply to status {status}: "
                + ", ".join(f"--{name.replace('_', '-')}" for name in invalid)
            )


def main() -> int:
    configure_utf8_standard_streams()
    parser = argparse.ArgumentParser(
        description="Validate TASKS.md and perform coordinator-owned atomic updates."
    )
    parser.add_argument("tasks_file", type=Path)
    parser.add_argument(
        "--ready", action="store_true", help="Show runtime-ready candidates"
    )
    parser.add_argument(
        "--safe-ready", action="store_true", help="Show ordered safe candidates"
    )
    parser.add_argument(
        "--isolated-worktrees",
        action="store_true",
        help="Compatibility flag; never authorizes concurrent mutable task claims",
    )
    parser.add_argument("--task", help="Show one task block")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--set-status", nargs=2, metavar=("TASK_ID", "STATUS"))
    parser.add_argument("--set-issue", nargs=2, metavar=("TASK_ID", "ISSUE_URL"))
    parser.add_argument(
        "--evidence", help="Evidence reference required when setting DONE"
    )
    parser.add_argument("--blocker", help="Observed blocker and next action")
    parser.add_argument("--skip-record", help="Explicit skip decision record")
    parser.add_argument(
        "--run-id", help="Active RUN-nnnn identity for task reconciliation"
    )
    parser.add_argument(
        "--checkpoint",
        help="New CP-nnnn ID; pause/complete require its TASKS row and VERIFY reference",
    )
    parser.add_argument(
        "--claim", metavar="TASK_ID", help="Atomically claim one READY task"
    )
    parser.add_argument(
        "--owner", help="Coordinator identity for a claim (legacy option name)"
    )
    parser.add_argument(
        "--start-run", metavar="RUN_ID", help="Start a new coordinator run"
    )
    parser.add_argument(
        "--run-mode",
        choices=("SINGLE_TASK", "AUTONOMOUS"),
        default=None,
    )
    parser.add_argument(
        "--coordinator",
        help="Exact active coordinator identity; required for every ledger mutation",
    )
    parser.add_argument(
        "--resume-run", metavar="RUN_ID", help="Resume a safe checkpointed run"
    )
    parser.add_argument(
        "--pause-run", metavar="RUN_ID", help="Pause a reconciled running run"
    )
    parser.add_argument(
        "--complete-run", metavar="RUN_ID", help="Complete a terminal running run"
    )
    args = parser.parse_args()

    path: Path = args.tasks_file
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2

    try:
        validate_cli_contract(args)
        if args.start_run:
            mutate_run_snapshot(
                path,
                operation="start",
                run_id=args.start_run,
                coordinator=args.coordinator,
                run_mode=args.run_mode or "AUTONOMOUS",
            )
        elif args.resume_run:
            mutate_run_snapshot(
                path,
                operation="resume",
                run_id=args.resume_run,
                coordinator=args.coordinator,
            )
        elif args.pause_run:
            mutate_run_snapshot(
                path,
                operation="pause",
                run_id=args.pause_run,
                coordinator=args.coordinator,
                checkpoint=args.checkpoint,
            )
        elif args.complete_run:
            mutate_run_snapshot(
                path,
                operation="complete",
                run_id=args.complete_run,
                coordinator=args.coordinator,
                checkpoint=args.checkpoint,
            )

        if args.claim:
            claim_task_file(
                path,
                args.claim,
                owner=args.owner,
                coordinator=args.coordinator,
                run_id=args.run_id,
                checkpoint=args.checkpoint,
                isolated_worktrees=args.isolated_worktrees,
            )

        mutation_task_ids = {
            pair[0] for pair in (args.set_status, args.set_issue) if pair is not None
        }
        if mutation_task_ids:
            task_id = next(iter(mutation_task_ids))
            update_task_file(
                path,
                task_id,
                coordinator=args.coordinator,
                status=args.set_status[1] if args.set_status else None,
                issue=args.set_issue[1] if args.set_issue else None,
                evidence=args.evidence,
                blocker=args.blocker,
                skip_record=args.skip_record,
                run_id=args.run_id,
                checkpoint=args.checkpoint,
            )

        text = path.read_text(encoding="utf-8")
        tasks = parse_tasks(text)
        snapshot = parse_snapshot(text)
        waivers = parse_waivers(text)
        if not tasks and snapshot.get("Task-plan revision") == "UNINITIALIZED":
            if args.json:
                print(json.dumps({"task_plan": "UNINITIALIZED", "tasks": []}, indent=2))
            else:
                print("Task plan is UNINITIALIZED; run TASK-10 after current Gate B.")
            return 0
        if not tasks:
            raise ValueError("No task blocks found for an initialized task plan")
        approved_contract = approved_contract_for_tasks(path, text)
        contract_kwargs = execution_contract_kwargs(approved_contract)
        by_id = validate(tasks, snapshot, waivers, **contract_kwargs)
        for task in tasks:
            if task.status == "DONE":
                validate_done_evidence_file(
                    path,
                    task,
                    contract_kwargs["approved_property_execution"],
                    contract_kwargs["approved_harness"],
                    text,
                )
        waves = compute_waves(tasks, by_id)

        if args.task:
            if args.task not in by_id:
                raise ValueError(f"Unknown task ID: {args.task}")
            print(by_id[args.task].block.rstrip())
            return 0

        candidates = ready_tasks(tasks, by_id, waivers) if args.ready else tasks
        available_slots = parse_nonnegative_int(
            snapshot.get("Maximum workers"), minimum=1
        )
        if args.safe_ready:
            candidates, available_slots = safe_ready_candidates(
                tasks,
                by_id,
                waivers,
                snapshot,
                waves,
                isolated_worktrees=args.isolated_worktrees,
            )
        if args.safe_ready:
            groups = (
                safe_execution_groups(
                    candidates,
                    waves,
                    isolated_worktrees=args.isolated_worktrees,
                    maximum_workers=available_slots,
                )
                if candidates
                else []
            )
            payload = [
                [task_to_dict(task, waves[task.task_id]) for task in group]
                for group in groups
            ]
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print("Ordered safe candidates")
                for index, group in enumerate(groups, start=1):
                    print(
                        f"  Candidate {index}: "
                        + ", ".join(task.task_id for task in group)
                    )
        elif args.json:
            print(
                json.dumps(
                    [task_to_dict(task, waves[task.task_id]) for task in candidates],
                    indent=2,
                )
            )
        elif args.ready:
            if not candidates:
                print("No runtime-ready candidates.")
            else:
                print("Runtime-ready candidates (not a parallel-safe batch)")
                for task in candidates:
                    print(f"  {task.task_id} [Wave {waves[task.task_id]}] {task.title}")
        else:
            print_waves(tasks, waves)
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
