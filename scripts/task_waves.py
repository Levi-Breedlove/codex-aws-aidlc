#!/usr/bin/env python3
"""Validate, claim, and safely group Fastlane construction tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
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
    from fastlane_engine.api import (
        ApprovedDeliveryContract,
        ApprovedSpikeContract,
        ApprovedTaskContract,
        HarnessExecutionRow,
        PropertyExecutionRow,
        compute_task_contract_waves as engine_compute_task_waves,
        derive_approved_task_contract,
        derive_current_design_contract,
        derive_task_ready_ids as engine_task_ready_ids,
        derive_task_requirement_coverage as engine_task_requirement_coverage,  # noqa: F401
        parse_task_contracts as engine_parse_task_contracts,
        parse_task_checkpoint_records as engine_parse_task_checkpoints,
        parse_task_completion_records as engine_parse_task_completion,
        parse_task_dependency_waivers as engine_parse_task_waivers,
        parse_task_execution_snapshot as engine_parse_task_snapshot,
        parse_task_external_targets as engine_parse_task_external_targets,
        parse_task_harness_projection as engine_parse_harness_projection,
        parse_task_harness_evidence as engine_parse_harness_evidence,
        parse_task_property_projection as engine_parse_property_projection,
        parse_task_write_boundary as engine_parse_task_write_boundary,
        task_dependency_is_satisfied as engine_task_dependency_satisfied,
        validate_approved_property_evidence,
        validate_task_contracts as engine_validate_task_contracts,
        validate_task_done_completion_evidence as engine_validate_done_completion,
        validate_task_done_harness_evidence as engine_validate_done_harness,
        validate_task_execution_basis,
        validate_task_harness_contracts as engine_validate_harness_contracts,
        validate_task_property_contract as engine_validate_property_contract,
        validate_task_snapshot_contract as engine_validate_snapshot,
    )
except ModuleNotFoundError:  # pragma: no cover - package-style test import
    from scripts.fastlane_engine.api import (
        ApprovedDeliveryContract,
        ApprovedSpikeContract as ApprovedSpikeContract,
        ApprovedTaskContract,
        HarnessExecutionRow,
        PropertyExecutionRow,
        compute_task_contract_waves as engine_compute_task_waves,
        derive_approved_task_contract,
        derive_current_design_contract as derive_current_design_contract,
        derive_task_ready_ids as engine_task_ready_ids,
        derive_task_requirement_coverage as engine_task_requirement_coverage,  # noqa: F401
        parse_task_contracts as engine_parse_task_contracts,
        parse_task_checkpoint_records as engine_parse_task_checkpoints,
        parse_task_completion_records as engine_parse_task_completion,
        parse_task_dependency_waivers as engine_parse_task_waivers,
        parse_task_execution_snapshot as engine_parse_task_snapshot,
        parse_task_external_targets as engine_parse_task_external_targets,
        parse_task_harness_projection as engine_parse_harness_projection,
        parse_task_harness_evidence as engine_parse_harness_evidence,
        parse_task_property_projection as engine_parse_property_projection,
        parse_task_write_boundary as engine_parse_task_write_boundary,
        task_dependency_is_satisfied as engine_task_dependency_satisfied,
        validate_approved_property_evidence,
        validate_task_contracts as engine_validate_task_contracts,
        validate_task_done_completion_evidence as engine_validate_done_completion,
        validate_task_done_harness_evidence as engine_validate_done_harness,
        validate_task_execution_basis,
        validate_task_harness_contracts as engine_validate_harness_contracts,
        validate_task_property_contract as engine_validate_property_contract,
        validate_task_snapshot_contract as engine_validate_snapshot,
    )

try:
    from fastlane_contracts import (
        ContractParseError,
        external_targets_overlap,
        parse_checkpoint_git_receipt_value,
        path_boundaries_overlap,
        path_boundary_base,
        path_boundary_contains,
        split_markdown_table_row,  # noqa: F401
        without_fenced_code,
    )
except ModuleNotFoundError:  # pragma: no cover - package-style test import
    from scripts.fastlane_contracts import (
        ContractParseError,
        external_targets_overlap,
        parse_checkpoint_git_receipt_value,
        path_boundaries_overlap,
        path_boundary_base,
        path_boundary_contains,
        split_markdown_table_row,  # noqa: F401
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
    parsed = engine_parse_task_snapshot(strip_generated_summary(text))
    return Snapshot(dict(parsed.fields), set(parsed.duplicates))


def parse_tasks(text: str) -> list[Task]:
    return [
        Task(
            task_id=task.task_id,
            title=task.title,
            start=task.start,
            end=task.end,
            block=task.block,
            metadata=dict(task.metadata),
            duplicate_metadata=set(task.duplicates),
        )
        for task in engine_parse_task_contracts(strip_generated_summary(text))
    ]


def parse_waivers(text: str) -> dict[str, Waiver]:
    return {
        waiver_id: Waiver(
            waiver.waiver_id,
            waiver.skipped_task,
            waiver.applies_to,
            waiver.authority,
            waiver.rationale,
            waiver.recorded_at,
        )
        for waiver_id, waiver in engine_parse_task_waivers(
            strip_generated_summary(text)
        ).items()
    }


def parse_checkpoint_rows(text: str) -> list[CheckpointRow]:
    return [
        CheckpointRow(
            row.checkpoint_id,
            row.run_id,
            row.recorded_at,
            row.basis,
            row.commit_and_dirty,
            row.task_outcomes,
            row.evidence_and_external,
            row.blockers_and_next,
        )
        for row in engine_parse_task_checkpoints(strip_generated_summary(text))
    ]


def validate_write_boundary(raw: str, task_id: str) -> list[str]:
    """COMPATIBILITY: delegate path-boundary grammar to Delivery."""

    return engine_parse_task_write_boundary(raw, task_id)


def parse_external_state(raw: str, task_id: str) -> list[str]:
    """COMPATIBILITY: delegate external-target grammar to Delivery."""

    return engine_parse_task_external_targets(raw, task_id)


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
    """COMPATIBILITY: delegate property grammar to the Engine Delivery API."""

    return engine_parse_property_projection(text, label)


def parse_harness_projection_rows(
    text: str,
    label: str,
) -> tuple[dict[str, HarnessExecutionRow], bool]:
    """COMPATIBILITY: delegate Harness grammar to the Engine Delivery API."""

    return engine_parse_harness_projection(text, label)


def validate_property_execution_projection(
    task: Task,
    approved_property_execution: dict[str, PropertyExecutionRow] | None,
) -> list[str]:
    """COMPATIBILITY: delegate property interpretation to Delivery."""

    try:
        technology_refs = task.technology_refs
    except ValueError as exc:
        return [str(exc)]
    return engine_validate_property_contract(
        task,
        technology_refs,
        approved_property_execution,
    )


def validate_harness_projections(
    tasks: list[Task],
    approved_harness: dict[str, HarnessExecutionRow] | None,
    *,
    current_plan: bool,
) -> list[str]:
    """COMPATIBILITY: delegate Harness interpretation to Delivery."""

    return engine_validate_harness_contracts(
        tasks,
        approved_harness,
        current_plan=current_plan,
    )


def parse_harness_evidence(text: str) -> list[HarnessEvidenceRow]:
    """COMPATIBILITY: delegate Harness evidence grammar to Delivery."""

    return [
        HarnessEvidenceRow(
            row.evidence_id,
            row.harness_id,
            row.layer,
            row.basis_ids,
            row.exact_command,
            row.artifact_environment,
            row.observed_result,
            row.observed_at,
            row.durable_source,
            row.status,
        )
        for row in engine_parse_harness_evidence(strip_generated_summary(text))
    ]


def validate_done_harness_evidence(
    verify_text: str,
    task: Task,
    snapshot: Snapshot,
    approved_harness: dict[str, HarnessExecutionRow] | None,
) -> None:
    """COMPATIBILITY: validate DONE Harness evidence through Delivery."""

    engine_validate_done_harness(
        strip_generated_summary(verify_text),
        task,
        snapshot,
        approved_harness,
    )


def parse_task_completion_evidence(text: str) -> list[TaskCompletionEvidenceRow]:
    """COMPATIBILITY: delegate completion evidence grammar to Delivery."""

    return [
        TaskCompletionEvidenceRow(
            row.evidence_id,
            row.task_id,
            row.command_or_observation,
            row.result,
            row.actor,
            row.observed_at,
            row.commit_worktree_artifact,
            row.durable_source,
            row.status,
        )
        for row in engine_parse_task_completion(strip_generated_summary(text))
    ]


def validate_property_done_evidence(
    verify_text: str,
    task: Task,
    snapshot: Snapshot,
    approved_property_execution: dict[str, PropertyExecutionRow] | None,
) -> None:
    """Delegate observed property evidence to the pure Delivery API."""

    property_ids = PROPERTY_ID_PATTERN.findall(
        clean(task.metadata.get("Requirements", ""))
    )
    if not property_ids:
        return
    if approved_property_execution is None:
        raise ValueError(
            f"{task.task_id}: approved PRD property execution contract is unavailable"
        )
    validate_approved_property_evidence(
        verify_text,
        task_id=task.task_id,
        title=task.title,
        block=task.block,
        metadata=task.metadata,
        duplicate_metadata=task.duplicate_metadata,
        snapshot_fields={key: clean(value) for key, value in snapshot.fields.items()},
        approved_property_execution=approved_property_execution,
    )


def validate_done_evidence_file(
    tasks_path: Path,
    task: Task,
    approved_property_execution: dict[str, PropertyExecutionRow] | None = None,
    approved_harness: dict[str, HarnessExecutionRow] | None = None,
    tasks_text: str | None = None,
) -> None:
    """Observe VERIFY once, then delegate every evidence decision to Delivery."""

    references = evidence_references(task.metadata.get("Evidence", ""))
    if not references:
        raise ValueError(f"{task.task_id}: DONE requires an Evidence reference")
    local_references = [
        reference
        for reference in references
        if TASK_EVIDENCE_ID_PATTERN.fullmatch(reference) is not None
    ]
    if not local_references:
        raise ValueError(
            f"{task.task_id}: DONE requires at least one exact local Evidence "
            "reference in EV-nnnn form"
        )
    if len(local_references) != len(set(local_references)):
        raise ValueError(
            f"{task.task_id}: DONE has duplicate local Evidence references"
        )
    verify_path = tasks_path.with_name("VERIFY.md")
    if not verify_path.is_file() or verify_path.is_symlink():
        raise ValueError(f"{task.task_id}: local Evidence requires a regular VERIFY.md")
    verify_text = strip_generated_summary(verify_path.read_text(encoding="utf-8"))
    engine_validate_done_completion(verify_text, task)
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
    """COMPATIBILITY: validate through the Engine Delivery API."""

    engine_validate_snapshot(snapshot)


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
    """SAFETY: validate through the shared read-only Engine task contract."""

    contract_supplied = any(
        value is not None
        for value in (
            approved_tech_ids,
            approved_property_execution,
            approved_harness,
            approved_delivery,
            approved_requirement_rules,
            approved_requirement_evidence,
        )
    )
    approved_contract = (
        ApprovedTaskContract(
            frozenset(approved_tech_ids or ()),
            dict(approved_property_execution or {}),
            dict(approved_harness or {}),
            approved_delivery,
            approved_requirement_rules,
            approved_requirement_evidence,
        )
        if contract_supplied
        else None
    )
    try:
        result = engine_validate_task_contracts(
            tasks,
            snapshot,
            waivers,
            approved_contract=approved_contract,
            technology_contract_available=approved_tech_ids is not None,
            property_contract_available=approved_property_execution is not None,
            harness_contract_available=approved_harness is not None,
            task_surface_compatibility=True,
        )
    except ValueError as exc:
        # COMPATIBILITY: historical callers validate cycles when requesting waves.
        if str(exc).startswith("Dependency cycle detected:"):
            return {task.task_id: task for task in tasks}
        raise
    return {task.task_id: task for task in result.tasks}


def compute_waves(tasks: list[Task], by_id: dict[str, Task]) -> dict[str, int]:
    """Return waves from the same pure task contract used by Engine evaluation."""

    del by_id  # COMPATIBILITY: retain the historical public call signature.
    return engine_compute_task_waves(tasks)


def dependency_satisfied(
    task: Task,
    dependency: Task,
    waivers: dict[str, Waiver],
) -> bool:
    """COMPATIBILITY: delegate one readiness decision to Delivery."""

    return engine_task_dependency_satisfied(task, dependency, waivers)


def ready_tasks(
    tasks: list[Task],
    by_id: dict[str, Task],
    waivers: dict[str, Waiver] | None = None,
) -> list[Task]:
    del by_id  # COMPATIBILITY: retain the historical public call signature.
    ready_ids = set(engine_task_ready_ids(tasks, waivers))
    return [task for task in tasks if task.task_id in ready_ids]


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


def validate_gate_b_design_contract_binding(
    tasks_path: Path,
    tasks_text: str,
    prd_text: str,
) -> None:
    """Reject a current plan whose Gate B hash no longer matches its PRD."""

    root = project_root_for_tasks(tasks_path)
    manifest_path = root / "bootstrap.manifest.json"
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
    validate_task_execution_basis(prd_text, tasks_text)


def approved_contract_for_tasks(
    tasks_path: Path,
    tasks_text: str | None = None,
) -> ApprovedTaskContract | None:
    """Read the immutable approved construction contract for one task ledger."""

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
    full_template = (root / "bootstrap.manifest.json").exists()
    verify_text: str | None = None
    if full_template:
        verify_path = tasks_path.with_name("VERIFY.md")
        if verify_path.exists():
            if not verify_path.is_file() or verify_path.is_symlink():
                raise ValueError("docs/project/VERIFY.md must be a regular file")
            verify_text = strip_generated_summary(
                verify_path.read_text(encoding="utf-8")
            )
    return derive_approved_task_contract(
        prd_text,
        tasks_text,
        verify_text,
        full_template=full_template,
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
