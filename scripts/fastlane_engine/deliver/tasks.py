"""Pure Delivery task graph and requirement-coverage validation.

Canonical inputs are caller-supplied TASKS, VERIFY, and normalized Define or
Design projections. Results are immutable records or deterministic failures.
This module performs no I/O, mutation, routing, approval, or authorization.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..core.contracts import (
    parse_task_external_state,
    parse_task_write_set,
    path_boundary_contains,
    split_table_row,
    table_after_heading,
    without_fenced_code,
)
from ..core.ids import (
    STABLE_CONTRACT_ID,
    canonical_id_list,
    clean_cell,
    explicit_timestamp,
    explicit_value,
    unresolved,
)
from .evidence import (
    EVIDENCE_PATTERN,
    PROPERTY_TEST_EVIDENCE_HEADING,
    fenced_command_lines,
    parse_harness_projection_rows,
    parse_property_execution_rows,
    parse_property_test_evidence,
    parse_task_completion_evidence,
    parse_verification_matrix,
    validate_done_evidence,
    task_check_projection,
    task_acceptance_check_issues,
    validate_done_property_evidence,
    validate_harness_projections,
    validate_task_property_projection,
    validate_task_property_execution_projection,
)
from .models import (
    ApprovedDeliveryContract,
    ApprovedTaskContract,
    DeliveryValidationPolicy,
    HarnessExecutionRow,
    InspectedTask,
    PropertyTestEvidenceRow,
    TaskCompletionEvidenceRow,
    TaskRequirementCoverage,
    TaskRequirementCoverageResult,
    TaskGraphValidationResult,
    TaskSnapshot,
    TaskSummary,
    TaskWaiver,
)

REQ_ID = re.compile(r"REQ-\d{4,}")
DES_ID = re.compile(r"DES-\d{4,}")
AUTH_ID = re.compile(r"AUTH-\d{4,}")
CHECKPOINT_ID = re.compile(r"CP-\d{4,}")
ACCEPTANCE_ID = re.compile(r"AC-[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
TASK_METADATA_KEYS = (
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
TASK_HEADER_PATTERN = re.compile(r"^###\s+(TASK-\d+)\s+[—-]\s+(.+?)\s*$", re.MULTILINE)
TASK_META_PATTERN = re.compile(
    rf"^- (?P<key>{'|'.join(re.escape(key) for key in TASK_METADATA_KEYS)}):"
    r"\s*(?P<value>.+?)\s*$",
    re.MULTILINE,
)
TASK_STATUSES = {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE", "SKIPPED"}
TASK_AWS_MODES = {"NONE", "DOCS_ONLY"}
TASK_PLAN_STATES = {"UNINITIALIZED", "CURRENT", "STALE"}
TASK_RUN_STATES = {"NOT_STARTED", "RUNNING", "PAUSED", "BLOCKED", "COMPLETE"}
TASK_SNAPSHOT_FIELDS = (
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
TASK_RUN_ID = re.compile(r"RUN-\d{4,}")
TASK_PLAN_ID = re.compile(r"PLAN-\d{4,}")
OWNER_DECISION_ID = re.compile(r"OWNER-DECISION-\d+")
WAVE_ID = re.compile(r"(?<![A-Za-z0-9_-])WAVE-\d{3,}(?![A-Za-z0-9_-])")
SPIKE_ID = re.compile(r"(?<![A-Za-z0-9_-])SPIKE-\d{3,}(?![A-Za-z0-9_-])")
TASK_DESIGN_TRACE_PATTERN = re.compile(
    r"^(?P<design>DES-\d{4}); TECH: "
    r"(?:(?P<none>NONE — no technology/toolchain impact)|"
    r"(?P<technologies>TECH-\d{4}(?:, TECH-\d{4})*))$"
)


def inspect_task_blocks(text: str) -> list[InspectedTask]:
    """CANONICALIZATION: parse ordered task blocks and exact metadata."""

    structural = without_fenced_code(text)
    matches = list(TASK_HEADER_PATTERN.finditer(structural))
    tasks: list[InspectedTask] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end]
        structural_block = structural[match.start() : end]
        metadata: dict[str, str] = {}
        duplicates: set[str] = set()
        for found in TASK_META_PATTERN.finditer(structural_block):
            key = found.group("key")
            if key in metadata:
                duplicates.add(key)
            metadata[key] = found.group("value")
        tasks.append(
            InspectedTask(
                match.group(1),
                match.group(2).strip(),
                block,
                metadata,
                duplicates,
                start=match.start(),
                end=end,
            )
        )
    return tasks


def inspect_task_sections(block: str) -> tuple[dict[str, str], set[str]]:
    structural = without_fenced_code(block)
    pattern = re.compile(
        r"^####[ \t]+(Outcome|Acceptance criteria|Validation|Execution log)[ \t]*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(structural))
    sections: dict[str, str] = {}
    duplicates: set[str] = set()
    for index, match in enumerate(matches):
        name = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
        if name in sections:
            duplicates.add(name)
        sections[name] = block[match.end() : end]
    return sections, duplicates


def task_remediation_validation_evidence(
    tasks_text: str, tasks: TaskSummary
) -> tuple[dict[str, str], ...]:
    """Project only the sole active task's exact current validation contract."""

    if len(tasks.active) != 1:
        return ()
    active_task = tasks.active[0]
    matches = [
        task for task in inspect_task_blocks(tasks_text) if task.task_id == active_task
    ]
    if len(matches) != 1:
        return ()
    sections, duplicates = inspect_task_sections(matches[0].block)
    if "Validation" in duplicates:
        return ()
    validation = sections.get("Validation", "")
    commands = fenced_command_lines(validation)
    try:
        property_rows, _ = parse_property_execution_rows(validation, active_task)
    except ValueError:
        property_rows = {}
    try:
        harness_rows, _ = parse_harness_projection_rows(validation, active_task)
    except ValueError:
        harness_rows = {}
    projections: dict[str, list[tuple[str, str]]] = {}
    for row in property_rows.values():
        projections.setdefault(row.exact_command, []).append(
            (row.property_id, row.evidence_destination)
        )
    for row in harness_rows.values():
        projections.setdefault(row.exact_command, []).append(
            (row.harness_id, row.evidence_destination)
        )
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for command in commands:
        bindings = projections.get(
            command,
            [("TASK-COMPLETION", "docs/project/VERIFY.md#task-completion-evidence")],
        )
        for validation_id, destination in bindings:
            key = (validation_id, command, destination)
            if key in seen:
                continue
            seen.add(key)
            result.append(
                {
                    "validation_id": validation_id,
                    "command": command,
                    "evidence_destination": destination,
                }
            )
    return tuple(result)


def _document_section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$", text, re.MULTILINE)
    if match is None:
        return ""
    following = re.search(r"^##\s+", text[match.end() :], re.MULTILINE)
    end = match.end() + following.start() if following else len(text)
    return text[match.end() : end]


def parse_task_snapshot(text: str) -> TaskSnapshot:
    """CANONICALIZATION: parse the exact active execution snapshot once."""

    body = _document_section(without_fenced_code(text), "Active execution snapshot")
    fields: dict[str, str] = {}
    duplicates: set[str] = set()
    allowed = set(TASK_SNAPSHOT_FIELDS)
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2 or cells[0] not in allowed:
            continue
        if cells[0] in fields:
            duplicates.add(cells[0])
        fields[cells[0]] = cells[1]
    return TaskSnapshot(fields, duplicates)


def parse_task_waivers(text: str) -> dict[str, TaskWaiver]:
    """CANONICALIZATION: return typed dependency-waiver records."""

    return {
        waiver_id: TaskWaiver(waiver_id, *values)
        for waiver_id, values in task_waiver_rows(text).items()
    }


def _parse_nonnegative_int(value: str, *, minimum: int = 0) -> int:
    normalized = clean_cell(value)
    if not normalized.isdigit() or int(normalized) < minimum:
        raise ValueError(f"expected integer >= {minimum}, got {normalized!r}")
    return int(normalized)


def _parse_design_trace(value: str, task_id: str) -> tuple[str, list[str]]:
    normalized = clean_cell(value)
    match = TASK_DESIGN_TRACE_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(
            f"{task_id}: Design must exactly match "
            "DES-nnnn; TECH: TECH-nnnn[, TECH-nnnn...] or "
            "DES-nnnn; TECH: NONE â€” no technology/toolchain impact"
        )
    technologies = match.group("technologies")
    references = technologies.split(", ") if technologies else []
    if len(references) != len(set(references)):
        raise ValueError(f"{task_id}: duplicate TECH reference in Design")
    return match.group("design"), references


def parse_task_write_boundary(
    value: str,
    task_id: str,
    *,
    task_surface_compatibility: bool = False,
) -> list[str]:
    """Parse one task write boundary through the shared repository grammar."""

    normalized = clean_cell(value)
    if task_surface_compatibility and normalized.upper() == "UNASSIGNED":
        raise ValueError(f"{task_id}: unresolved Write set")
    return parse_task_write_set(normalized, task_id)


def parse_task_external_targets(
    value: str,
    task_id: str,
    *,
    task_surface_compatibility: bool = False,
) -> list[str]:
    """Parse one task external-state boundary without granting authority."""

    normalized = clean_cell(value)
    if task_surface_compatibility and (
        normalized.upper() == "UNASSIGNED"
        or "\x00" in normalized
        or "\r" in normalized
        or "\n" in normalized
    ):
        raise ValueError(f"{task_id}: ambiguous External state")
    targets = parse_task_external_state(normalized, task_id)
    if task_surface_compatibility and any(
        target.upper() == "ALL" for target in targets
    ):
        raise ValueError(f"{task_id}: ambiguous External state")
    return targets


def _evidence_references(value: str) -> list[str]:
    return [match.group(0) for match in EVIDENCE_PATTERN.finditer(clean_cell(value))]


def validate_task_snapshot(
    snapshot: TaskSnapshot,
    *,
    task_surface_compatibility: bool = False,
) -> None:
    """SAFETY: reject incomplete or contradictory execution snapshots."""

    errors = [
        f"Execution snapshot: missing {key}"
        for key in TASK_SNAPSHOT_FIELDS
        if key not in snapshot.fields
    ]
    errors.extend(
        f"Execution snapshot: duplicate {key}" for key in sorted(snapshot.duplicates)
    )
    if errors:
        raise ValueError("\n".join(errors))
    run_state = snapshot.get("Run state")
    if run_state not in TASK_RUN_STATES:
        raise ValueError(f"Execution snapshot: invalid Run state {run_state!r}")
    plan_state = snapshot.get("Task-plan state")
    plan_revision = snapshot.get("Task-plan revision")
    if plan_state not in TASK_PLAN_STATES:
        raise ValueError(f"Execution snapshot: invalid Task-plan state {plan_state!r}")
    if plan_state == "UNINITIALIZED":
        if plan_revision != "UNINITIALIZED":
            raise ValueError(
                "Execution snapshot: UNINITIALIZED state requires UNINITIALIZED revision"
            )
    elif TASK_PLAN_ID.fullmatch(plan_revision) is None:
        raise ValueError(
            "Execution snapshot: initialized plan requires a PLAN-nnnn revision"
        )
    maximum_workers = _parse_nonnegative_int(snapshot.get("Maximum workers"), minimum=1)
    if maximum_workers != 1:
        raise ValueError("Execution snapshot: Maximum workers must be exactly 1")
    active_run = snapshot.get("Active run ID")
    coordinator = snapshot.get("Coordinator")
    if run_state == "NOT_STARTED":
        if active_run != "NONE" or coordinator != "UNASSIGNED":
            raise ValueError(
                "Execution snapshot: NOT_STARTED requires no active run or coordinator"
            )
    elif TASK_RUN_ID.fullmatch(active_run) is None or coordinator in {
        "",
        "NONE",
        "UNASSIGNED",
        "TODO",
    }:
        raise ValueError(
            "Execution snapshot: active state requires a RUN ID and coordinator"
        )
    current_wave = snapshot.get("Current wave")
    if current_wave != "NONE":
        _parse_nonnegative_int(current_wave, minimum=1)
    parse_task_write_boundary(
        snapshot.get("Protected dirty paths"),
        "Execution snapshot Protected dirty paths",
        task_surface_compatibility=task_surface_compatibility,
    )
    checkpoint = snapshot.get("Last checkpoint")
    if checkpoint != "NONE" and CHECKPOINT_ID.fullmatch(checkpoint) is None:
        raise ValueError(f"Execution snapshot: invalid Last checkpoint {checkpoint!r}")
    if checkpoint == "NONE" and run_state in {"PAUSED", "BLOCKED", "COMPLETE"}:
        raise ValueError(
            f"Execution snapshot: {run_state} requires a valid Last checkpoint"
        )


def task_waiver_rows(text: str) -> dict[str, tuple[str, str, str, str, str]]:
    marker = "### Dependency waiver registry"
    if text.count(marker) != 1:
        raise ValueError("Expected exactly one dependency waiver registry")
    body = text.split(marker, 1)[1].split("\n## ", 1)[0]
    result: dict[str, tuple[str, str, str, str, str]] = {}
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [clean_cell(item) for item in split_table_row(line)]
        if len(cells) != 6 or cells[0] in {"Waiver ID", "---", "NONE"}:
            continue
        if re.fullmatch(r"WAIVER-\d+", cells[0]) is None:
            continue
        if cells[0] in result:
            raise ValueError(f"Duplicate waiver ID: {cells[0]}")
        result[cells[0]] = (cells[1], cells[2], cells[3], cells[4], cells[5])
    return result


def declared_task_waivers(task: InspectedTask) -> dict[str, str]:
    raw = clean_cell(task.metadata.get("Dependency waivers", "NONE"))
    if raw in {"", "NONE", "-"}:
        return {}
    result: dict[str, str] = {}
    for entry in raw.split(","):
        pair = [item.strip() for item in entry.split("=", 1)]
        if (
            len(pair) != 2
            or re.fullmatch(r"TASK-\d+", pair[0]) is None
            or re.fullmatch(r"WAIVER-\d+", pair[1]) is None
        ):
            raise ValueError(f"{task.task_id}: invalid dependency waiver {entry!r}")
        result[pair[0]] = pair[1]
    return result


def _task_contract_ids(task: Any) -> list[str]:
    return STABLE_CONTRACT_ID.findall(clean_cell(task.metadata.get("Requirements", "")))


def _transitively_depends_on(
    task: Any,
    ancestor_id: str,
    by_id: Mapping[str, Any],
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
    tasks: Sequence[Any],
    by_id: Mapping[str, Any],
    approved_delivery: ApprovedDeliveryContract | None,
    approved_harness: Mapping[str, HarnessExecutionRow] | None,
    *,
    current_plan: bool,
    task_surface_compatibility: bool = False,
) -> list[str]:
    """SAFETY: bind a modern new-build graph to its approved first wave."""

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
    references = {task.task_id: _task_contract_ids(task) for task in tasks}

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

    def sole_owner(identifier: str, noun: str, skipped: str) -> Any | None:
        owners = [
            task
            for task in tasks
            for reference in references[task.task_id]
            if reference == identifier
        ]
        if len(owners) != 1:
            errors.append(
                f"{identifier}: current NEW_BUILD task plan requires exactly one "
                f"{noun} task; found {len(owners)}"
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

    unexpected = sorted(set(matching_ids(WAVE_ID)) - {wave_id})
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
                walking_writes = parse_task_write_boundary(
                    walking_task.metadata.get("Write set", ""),
                    walking_task.task_id,
                    task_surface_compatibility=task_surface_compatibility,
                )
                writes_application_source = any(
                    path_boundary_contains(source, path)
                    or path_boundary_contains(path, source)
                    for source in delivery.application_source_paths
                    for path in walking_writes
                )
                reject(
                    not writes_application_source,
                    f"{walking_task.task_id}: walking-skeleton Write set must include "
                    "approved application source under app/**",
                )
            except ValueError as exc:
                errors.append(str(exc))

        sections, _duplicates = inspect_task_sections(walking_task.block)
        projected_harness: dict[str, HarnessExecutionRow] = {}
        validation = sections.get("Validation")
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
                f"{walking_task.task_id}: walking-skeleton Validation must own "
                f"approved end-to-end {harness_id}",
            )

    approved_spike = delivery.spike
    observed_spike_ids = matching_ids(SPIKE_ID)
    spike_task: Any | None = None
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
        if reject(
            walking_task is not None
            and spike_task is not None
            and spike_task.task_id == walking_task.task_id,
            f"{approved_spike.spike_id}: spike and walking skeleton must be separate tasks",
        ):
            spike_task = None
    if spike_task is not None and approved_spike is not None:
        reject(
            spike_task.attempt_budget > approved_spike.max_attempts,
            f"{spike_task.task_id}: Attempt budget exceeds approved "
            f"{approved_spike.spike_id} maximum {approved_spike.max_attempts}",
        )
        try:
            spike_writes = parse_task_write_boundary(
                spike_task.metadata.get("Write set", ""),
                spike_task.task_id,
                task_surface_compatibility=task_surface_compatibility,
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
                f"{spike_task.task_id}: spike Write set exceeds the approved "
                "disposable boundary: " + ", ".join(outside),
            )
        except ValueError as exc:
            errors.append(str(exc))
        reject(
            clean_cell(spike_task.metadata.get("External state", "")) != "NONE",
            f"{spike_task.task_id}: blocking spike requires External state NONE",
        )
        reject(
            clean_cell(spike_task.metadata.get("AWS mode", "")).upper()
            not in {"NONE", "DOCS_ONLY"},
            f"{spike_task.task_id}: blocking spike AWS mode must be NONE or DOCS_ONLY",
        )
        sections, _duplicates = inspect_task_sections(spike_task.block)
        validation = sections.get("Validation", "")
        exit_count = fenced_command_lines(validation).count(
            approved_spike.exit_criterion
        )
        reject(
            exit_count != 1,
            f"{spike_task.task_id}: approved spike exit criterion must appear "
            "unchanged exactly once in Validation code fences; "
            f"found {exit_count}",
        )

    if walking_task is None or not all(
        dependency in by_id and dependency != task.task_id
        for task in tasks
        for dependency in task.dependencies
    ):
        return errors
    try:
        waves = compute_task_waves(tasks, by_id)
    except ValueError as exc:
        errors.append(str(exc))
        return errors
    active_tasks = [task for task in tasks if task.status != "SKIPPED"]

    def tasks_in_wave(number: int) -> list[str]:
        return sorted(
            task.task_id for task in active_tasks if waves[task.task_id] == number
        )

    if approved_spike is None:
        reject(
            bool(walking_task.dependencies),
            f"{walking_task.task_id}: walking skeleton without a spike must use "
            "Depends on NONE",
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
            f"{walking_task.task_id}: walking skeleton must depend directly and only "
            f"on {spike_task.task_id}",
        )
        reject(
            tasks_in_wave(1) != [spike_task.task_id],
            f"{approved_spike.spike_id}: spike must be the sole active structural wave 1 task",
        )
        reject(
            tasks_in_wave(2) != [walking_task.task_id],
            f"{wave_id}: walking skeleton must be the sole active structural wave 2 "
            "task after the spike",
        )

    excluded = {
        walking_task.task_id,
        *(task.task_id for task in (spike_task,) if task),
    }
    bypassing = sorted(
        task.task_id
        for task in active_tasks
        if task.task_id not in excluded
        and not _transitively_depends_on(task, walking_task.task_id, by_id)
    )
    reject(
        bool(bypassing),
        f"{wave_id}: active tasks must be transitively downstream of the walking "
        "skeleton: " + ", ".join(bypassing),
    )
    return errors


def compute_task_waves(
    tasks: Sequence[Any],
    by_id: Mapping[str, Any],
) -> dict[str, int]:
    """CANONICALIZATION: derive deterministic structural task waves."""

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


def task_dependency_satisfied(
    task: Any,
    dependency: Any,
    waivers: Mapping[str, TaskWaiver],
) -> bool:
    """Return whether one dependency permits the task to run now."""

    if dependency.status == "DONE":
        return True
    if dependency.status != "SKIPPED":
        return False
    declared = declared_task_waivers(task)
    waiver = waivers.get(declared.get(dependency.task_id, ""))
    return bool(
        waiver is not None
        and waiver.skipped_task == dependency.task_id
        and waiver.applies_to == task.task_id
    )


def validate_task_check_bindings(
    task, delivery: ApprovedDeliveryContract | None
) -> list[str]:
    if delivery is None or not delivery.validation_checks:
        return []
    issues: list[str] = []
    try:
        rows = task_check_projection(task.block)
    except ValueError as exc:
        return [f"{task.task_id}: {exc}"]
    approved = {row[0]: row for row in delivery.validation_checks}
    selected = {row[0]: row for row in rows}
    if len(selected) != len(rows) or not rows:
        issues.append(
            f"{task.task_id}: validation requires unique current check bindings"
        )
    sections, _ = inspect_task_sections(task.block)
    commands = fenced_command_lines(sections.get("Validation", ""))
    for identifier, row in selected.items():
        if (
            row != approved.get(identifier)
            or row[2] != "LOCAL_BUILD"
            or row[3] not in commands
        ):
            issues.append(
                f"{task.task_id}: {identifier} must exactly project a current LOCAL_BUILD check and executable command"
            )
    issues.extend(task_acceptance_check_issues(task, delivery, rows, sections))
    return issues


def task_check_coverage_issues(
    tasks, delivery: ApprovedDeliveryContract | None
) -> list[str]:
    if delivery is None or not delivery.validation_checks:
        return []
    expected = {row[0] for row in delivery.validation_checks if row[2] == "LOCAL_BUILD"}
    covered: set[str] = set()
    for task in tasks:
        if task.status == "SKIPPED":
            continue
        try:
            covered.update(row[0] for row in task_check_projection(task.block))
        except ValueError:
            continue  # The task-specific diagnostic owns malformed projections.
    return (
        [
            "Current task plan does not cover validation checks: "
            + ", ".join(sorted(expected - covered))
        ]
        if expected - covered
        else []
    )


def derive_ready_task_ids(
    tasks: Sequence[Any],
    waivers: Mapping[str, TaskWaiver] | None = None,
) -> tuple[str, ...]:
    """Derive READY tasks whose declared dependencies are satisfied."""

    by_id = {task.task_id: task for task in tasks}
    waivers = waivers or {}
    return tuple(
        task.task_id
        for task in tasks
        if task.status == "READY"
        and all(
            dependency_id in by_id
            and task_dependency_satisfied(task, by_id[dependency_id], waivers)
            for dependency_id in task.dependencies
        )
    )


def _plan_completeness_issues(
    tasks,
    snapshot,
    contract,
    enforce_plan_completeness,
    harness_contract_available,
    property_contract_available,
    policy,
):
    errors: list[str] = []
    current = snapshot is not None and snapshot.get("Task-plan state") == "CURRENT"
    if enforce_plan_completeness and current:
        errors.extend(
            validate_harness_projections(
                tasks,
                contract.harness if harness_contract_available else None,
                current_plan=True,
            )
        )

    if enforce_plan_completeness and current and property_contract_available:
        referenced_property_ids = {
            property_id
            for task in tasks
            if task.status in {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE"}
            for property_id in policy.property_id.findall(
                clean_cell(task.metadata.get("Requirements", ""))
            )
        }
        missing_property_ids = sorted(
            set(contract.property_execution) - referenced_property_ids
        )
        if missing_property_ids:
            errors.append(
                "Current task plan does not cover approved property execution IDs: "
                + ", ".join(missing_property_ids)
            )

    if enforce_plan_completeness and current and contract.requirement_rules is not None:
        requirement_coverage = derive_task_requirement_coverage(
            tasks,
            snapshot.get("Task-plan state"),
            contract.requirement_rules,
            contract.requirement_evidence or {},
        )
        errors.extend(requirement_coverage.trace_issues)
        errors.extend(requirement_coverage.evidence_issues)
        if requirement_coverage.missing_requirement_ids:
            errors.append(
                "Current task plan does not cover approved requirement IDs: "
                + ", ".join(requirement_coverage.missing_requirement_ids)
            )

    if current:
        errors.extend(task_check_coverage_issues(tasks, contract.delivery))
    return errors


def validate_task_graph(
    tasks: Sequence[Any],
    snapshot: TaskSnapshot | None = None,
    waivers: Mapping[str, TaskWaiver] | None = None,
    *,
    approved_contract: ApprovedTaskContract | None = None,
    technology_contract_available: bool | None = None,
    property_contract_available: bool | None = None,
    harness_contract_available: bool | None = None,
    task_surface_compatibility: bool = False,
    validate_snapshot_structure: bool = True,
    enforce_plan_completeness: bool = True,
    policy: DeliveryValidationPolicy,
) -> TaskGraphValidationResult:
    """SAFETY: return one pure task graph, wave, and readiness decision."""

    errors: list[str] = []
    by_id: dict[str, Any] = {}
    waivers = waivers or {}
    contract_supplied = approved_contract is not None
    contract = approved_contract or ApprovedTaskContract(frozenset(), {}, {})
    technology_contract_available = (
        contract_supplied
        if technology_contract_available is None
        else technology_contract_available
    )
    property_contract_available = (
        contract_supplied
        if property_contract_available is None
        else property_contract_available
    )
    harness_contract_available = (
        contract_supplied
        if harness_contract_available is None
        else harness_contract_available
    )
    if snapshot is not None and validate_snapshot_structure:
        validate_task_snapshot(
            snapshot,
            task_surface_compatibility=task_surface_compatibility,
        )

    for task in tasks:
        if task.task_id in by_id:
            errors.append(f"Duplicate task ID: {task.task_id}")
        by_id[task.task_id] = task
        for key in sorted(task.duplicate_metadata):
            errors.append(f"{task.task_id}: duplicate {key} metadata")
        for key in TASK_METADATA_KEYS:
            if key not in task.metadata:
                errors.append(f"{task.task_id}: missing {key} metadata")
        if task.status not in TASK_STATUSES:
            errors.append(
                f"{task.task_id}: invalid status {task.status!r}; "
                f"allowed={sorted(TASK_STATUSES)}"
            )
            continue
        try:
            budget = _parse_nonnegative_int(
                task.metadata.get("Attempt budget", ""), minimum=1
            )
            used = _parse_nonnegative_int(task.metadata.get("Attempts used", ""))
            if used > budget:
                errors.append(f"{task.task_id}: Attempts used exceeds Attempt budget")
        except ValueError as exc:
            errors.append(f"{task.task_id}: invalid attempt metadata: {exc}")
            budget = used = 0

        aws_mode = clean_cell(task.metadata.get("AWS mode", "")).upper()
        if aws_mode not in TASK_AWS_MODES:
            errors.append(f"{task.task_id}: invalid AWS mode {aws_mode!r}")

        contract_bound = task.status in {
            "READY",
            "IN_PROGRESS",
            "BLOCKED",
            "DONE",
        } or (
            task.status == "BACKLOG"
            and snapshot is not None
            and snapshot.get("Task-plan state") == "CURRENT"
        )
        technology_refs: list[str] = []
        if contract_bound:
            requirement = REQ_ID.search(
                clean_cell(task.metadata.get("Requirements", ""))
            )
            authorization = AUTH_ID.search(
                clean_cell(task.metadata.get("Authorization", ""))
            )
            try:
                design_revision, technology_refs = _parse_design_trace(
                    task.metadata.get("Design", ""), task.task_id
                )
                unknown = [
                    tech_id
                    for tech_id in technology_refs
                    if tech_id not in contract.technology_ids
                ]
                if technology_contract_available and unknown:
                    errors.append(
                        f"{task.task_id}: Design references unapproved TECH IDs: "
                        + ", ".join(unknown)
                    )
            except ValueError as exc:
                errors.append(str(exc))
                design_revision = None
            if requirement is None or authorization is None:
                errors.append(f"{task.task_id}: unresolved REQ/DES/AUTH trace")
            if snapshot is not None:
                expected = (
                    snapshot.get("Requirements revision"),
                    snapshot.get("Design revision"),
                    snapshot.get("Construction authorization"),
                )
                observed = (
                    requirement.group(0) if requirement is not None else None,
                    design_revision,
                    authorization.group(0) if authorization is not None else None,
                )
                if design_revision is not None and observed != expected:
                    errors.append(
                        f"{task.task_id}: REQ/DES/AUTH trace does not match "
                        "execution snapshot"
                    )
                if snapshot.get("Gate B state") != "APPROVED_FOR_CONSTRUCTION":
                    errors.append(
                        f"{task.task_id}: Gate B is not approved for construction"
                    )
                if (
                    not task_surface_compatibility
                    and task.status in {"READY", "IN_PROGRESS"}
                    and snapshot.get("Task-plan state") != "CURRENT"
                ):
                    errors.append(f"{task.task_id}: task plan is not CURRENT")
            try:
                parse_task_write_boundary(
                    task.metadata.get("Write set", ""),
                    task.task_id,
                    task_surface_compatibility=task_surface_compatibility,
                )
                parse_task_external_targets(
                    task.metadata.get("External state", ""),
                    task.task_id,
                    task_surface_compatibility=task_surface_compatibility,
                )
            except ValueError as exc:
                errors.append(str(exc))
            if used >= budget and task.status == "READY":
                errors.append(f"{task.task_id}: attempt budget exhausted")

        run_id = clean_cell(task.metadata.get("Run ID", "NONE"))
        if task.status == "IN_PROGRESS":
            owner = clean_cell(task.metadata.get("Owner", ""))
            checkpoint = clean_cell(task.metadata.get("Last checkpoint", ""))
            if unresolved(owner) or owner == "NONE":
                errors.append(f"{task.task_id}: IN_PROGRESS requires an assigned Owner")
            if unresolved(run_id) or run_id == "NONE":
                errors.append(f"{task.task_id}: IN_PROGRESS requires a Run ID")
            if CHECKPOINT_ID.fullmatch(checkpoint) is None:
                errors.append(
                    f"{task.task_id}: IN_PROGRESS requires a valid Last checkpoint"
                )
            if used < 1:
                errors.append(f"{task.task_id}: IN_PROGRESS requires a claimed attempt")
            if snapshot is not None and (
                snapshot.get("Run state") != "RUNNING"
                or snapshot.get("Active run ID") != run_id
            ):
                errors.append(
                    f"{task.task_id}: Run ID does not match the active RUNNING run"
                )
        elif run_id not in {"", "NONE"}:
            errors.append(f"{task.task_id}: non-IN_PROGRESS task must use Run ID NONE")

        if task.status == "DONE":
            evidence = clean_cell(task.metadata.get("Evidence", ""))
            if task_surface_compatibility:
                local = [
                    reference
                    for reference in _evidence_references(evidence)
                    if re.fullmatch(r"EV-\d{4,}", reference) is not None
                ]
                if unresolved(evidence) or evidence == "NONE" or not local:
                    errors.append(
                        f"{task.task_id}: DONE requires an Evidence reference"
                    )
                elif len(local) != len(set(local)):
                    errors.append(
                        f"{task.task_id}: DONE has duplicate local Evidence references"
                    )
            elif (
                evidence in {"", "NONE", "TODO"}
                or EVIDENCE_PATTERN.search(evidence) is None
            ):
                errors.append(f"{task.task_id}: DONE requires Evidence")
        if task.status == "BLOCKED" and (
            unresolved(clean_cell(task.metadata.get("Blocker", "")))
            or clean_cell(task.metadata.get("Blocker", "")) == "NONE"
        ):
            errors.append(f"{task.task_id}: BLOCKED requires a blocker and next action")
        if task.status == "SKIPPED" and (
            unresolved(clean_cell(task.metadata.get("Skip record", "")))
            or clean_cell(task.metadata.get("Skip record", "")) == "NONE"
        ):
            errors.append(f"{task.task_id}: SKIPPED requires a Skip record")

        if contract_bound:
            errors.extend(validate_task_check_bindings(task, contract.delivery))
            sections, duplicate_sections = inspect_task_sections(task.block)
            for name in sorted(duplicate_sections):
                errors.append(f"{task.task_id}: duplicate required section #### {name}")
            for name in (
                "Outcome",
                "Acceptance criteria",
                "Validation",
                "Execution log",
            ):
                if name not in sections:
                    errors.append(
                        f"{task.task_id}: missing required section #### {name}"
                    )
            outcome = sections.get("Outcome", "")
            if not outcome.strip() or any(
                marker in outcome.upper() for marker in ("TODO", "TBD")
            ):
                errors.append(f"{task.task_id}: unresolved Outcome")
            acceptance = sections.get("Acceptance criteria", "")
            if re.search(r"^- \[[ xX]\]\s+\S", acceptance, re.MULTILINE) is None or any(
                marker in acceptance.upper() for marker in ("TODO", "TBD")
            ):
                errors.append(
                    f"{task.task_id}: objective acceptance criteria are required"
                )
            if task.status == "DONE" and re.search(
                r"^- \[ \]", acceptance, re.MULTILINE
            ):
                errors.append(
                    f"{task.task_id}: DONE has incomplete acceptance criteria"
                )
            validation = sections.get("Validation", "")
            if "```" not in validation or any(
                marker in validation.upper() for marker in ("TODO", "TBD")
            ):
                errors.append(
                    f"{task.task_id}: executable validation commands are required"
                )
            property_contract = (
                contract.property_execution if property_contract_available else None
            )
            if task_surface_compatibility:
                errors.extend(
                    validate_task_property_projection(
                        task,
                        technology_refs,
                        property_contract,
                    )
                )
            else:
                try:
                    validate_task_property_execution_projection(
                        validation,
                        task.task_id,
                        task.metadata.get("Requirements", ""),
                        technology_refs,
                        property_contract,
                        policy,
                    )
                except ValueError as exc:
                    errors.append(str(exc))
            execution_log = sections.get("Execution log", "")
            normalized_log = execution_log.strip().upper().replace("_", " ")
            if not execution_log.strip() or "TODO" in execution_log.upper():
                errors.append(f"{task.task_id}: execution log must be explicit")
            if task.status == "DONE" and any(
                marker in normalized_log
                for marker in (
                    "TODO",
                    "TBD",
                    "NOT STARTED",
                    "NO EXECUTION HAS BEEN RECORDED",
                )
            ):
                errors.append(
                    f"{task.task_id}: DONE requires an observed Execution log"
                )

        updated = clean_cell(task.metadata.get("Last updated", ""))
        if not unresolved(updated) and not explicit_timestamp(updated):
            errors.append(
                f"{task.task_id}: Last updated must be ISO 8601 with timezone"
            )
        try:
            declared = declared_task_waivers(task)
            for dependency_id, waiver_id in declared.items():
                waiver = waivers.get(waiver_id)
                if waiver is None:
                    errors.append(
                        f"{task.task_id}: unknown dependency waiver {waiver_id}"
                    )
                elif (
                    waiver.skipped_task != dependency_id
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

    if enforce_plan_completeness:
        errors.extend(
            validate_new_build_delivery_order(
                tasks,
                by_id,
                contract.delivery if contract_supplied else None,
                contract.harness if harness_contract_available else None,
                current_plan=(
                    snapshot is not None
                    and snapshot.get("Task-plan state") == "CURRENT"
                ),
                task_surface_compatibility=task_surface_compatibility,
            )
        )

    current_authorization = (
        snapshot.get("Construction authorization") if snapshot is not None else ""
    )
    for waiver in waivers.values():
        if waiver.skipped_task not in by_id or waiver.applies_to not in by_id:
            errors.append(f"{waiver.waiver_id}: references an unknown task")
            continue
        if by_id[waiver.skipped_task].status != "SKIPPED":
            errors.append(f"{waiver.waiver_id}: dependency is not SKIPPED")
        if waiver.skipped_task not in by_id[waiver.applies_to].dependencies:
            errors.append(f"{waiver.waiver_id}: skipped task is not a dependency")
        authority_pattern = (
            re.compile(
                rf"{re.escape(current_authorization)}(?:\s+clause\s+[A-Za-z0-9._:-]+)?"
            )
            if current_authorization
            else None
        )
        if not (
            authority_pattern is not None
            and authority_pattern.fullmatch(waiver.authority)
            or OWNER_DECISION_ID.fullmatch(waiver.authority)
        ):
            errors.append(
                f"{waiver.waiver_id}: authority is not an exact current authority"
            )
        if (
            unresolved(waiver.rationale)
            or EVIDENCE_PATTERN.search(waiver.rationale) is None
        ):
            errors.append(
                f"{waiver.waiver_id}: missing rationale or preserved evidence"
            )
        if not explicit_timestamp(waiver.recorded_at):
            errors.append(
                (
                    f"{waiver.waiver_id}: timestamp must include a UTC offset"
                    if task_surface_compatibility
                    else f"{waiver.waiver_id}: Recorded at must be ISO 8601 with timezone"
                )
            )

    errors.extend(
        _plan_completeness_issues(
            tasks,
            snapshot,
            contract,
            enforce_plan_completeness,
            harness_contract_available,
            property_contract_available,
            policy,
        )
    )
    if errors:
        raise ValueError("\n".join(errors))
    try:
        waves = compute_task_waves(tasks, by_id)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    ready = derive_ready_task_ids(tasks, waivers)
    return TaskGraphValidationResult(
        tasks=tuple(tasks),
        ready_task_ids=ready,
        waves=tuple(sorted(waves.items())),
    )


def validate_task_records(
    text: str,
    snapshot: dict[str, str],
    verify_text: str | None = None,
    approved_tech_ids: set[str] | None = None,
    property_execution_by_id: Mapping[str, Any] | None = None,
    technology_decisions_by_id: Mapping[str, Any] | None = None,
    policy: DeliveryValidationPolicy | None = None,
    *,
    approved_harness: Mapping[str, HarnessExecutionRow] | None = None,
    approved_delivery: ApprovedDeliveryContract | None = None,
    requirement_rules: Mapping[str, tuple[str, str]] | None = None,
    requirement_evidence: Mapping[str, tuple[str, tuple[str, ...]]] | None = None,
) -> tuple[list[InspectedTask], dict[str, InspectedTask], list[str]]:
    """COMPATIBILITY: preserve Engine task and evidence validation semantics."""

    if policy is None:
        raise ValueError("Delivery validation policy is required")
    tasks = inspect_task_blocks(text)
    contract = ApprovedTaskContract(
        frozenset(approved_tech_ids or set()),
        dict(property_execution_by_id or {}),
        dict(approved_harness or {}),
        approved_delivery,
        dict(requirement_rules) if requirement_rules is not None else None,
        dict(requirement_evidence) if requirement_evidence is not None else None,
    )
    graph = validate_task_graph(
        tasks,
        TaskSnapshot(dict(snapshot), set()),
        parse_task_waivers(text),
        approved_contract=contract,
        technology_contract_available=approved_tech_ids is not None,
        property_contract_available=property_execution_by_id is not None,
        harness_contract_available=approved_harness is not None,
        # COMPATIBILITY: whole-project evaluation keeps its later domain-specific
        # diagnostic codes, while task mutation uses the stricter complete plan.
        validate_snapshot_structure=False,
        enforce_plan_completeness=False,
        policy=policy,
    )
    errors: list[str] = []
    for task in tasks:
        if task.status != "DONE":
            continue
        try:
            validate_done_evidence(verify_text, task)
        except ValueError as exc:
            errors.append(str(exc))

    done_property_pairs = {
        (task.task_id, property_id)
        for task in tasks
        if task.status == "DONE"
        for property_id in policy.property_id.findall(
            clean_cell(task.metadata.get("Requirements", ""))
        )
    }
    property_rows: list[PropertyTestEvidenceRow] = []
    completion_rows: list[TaskCompletionEvidenceRow] = []
    property_section_present = bool(
        verify_text is not None
        and re.search(
            rf"^{re.escape(PROPERTY_TEST_EVIDENCE_HEADING)}[ \t]*$",
            without_fenced_code(verify_text),
            re.MULTILINE,
        )
    )
    if verify_text is not None and property_section_present:
        try:
            property_rows = parse_property_test_evidence(verify_text, policy)
        except ValueError as exc:
            errors.append(str(exc))
    observed_property_pairs = {
        (row.task_id, row.property_id)
        for row in property_rows
        if row.result in {"PASS", "FAIL"}
    }
    if done_property_pairs or observed_property_pairs:
        if verify_text is None:
            errors.append(
                "DONE property tasks require VERIFY.md property-test evidence"
            )
        elif not property_section_present:
            errors.append(
                "VERIFY.md requires exactly one Property-based test evidence section"
            )
        else:
            try:
                completion_rows = parse_task_completion_evidence(verify_text)
            except ValueError as exc:
                errors.append(str(exc))

    by_id = graph.by_id
    for task_id, property_id in sorted(observed_property_pairs | done_property_pairs):
        task = by_id.get(task_id)
        if task is None:
            errors.append(
                f"{task_id} {property_id}: observed property-test evidence "
                "references an unknown current task"
            )
            continue
        task_property_ids = set(
            policy.property_id.findall(
                clean_cell(task.metadata.get("Requirements", ""))
            )
        )
        if property_id not in task_property_ids:
            errors.append(
                f"{task_id} {property_id}: observed property-test evidence is not "
                "linked by the current task Requirements"
            )
            continue
        expected = (property_execution_by_id or {}).get(property_id)
        if expected is None:
            errors.append(
                f"{task_id} {property_id}: current property execution contract is "
                "unavailable"
            )
            continue
        technology = (technology_decisions_by_id or {}).get(expected.framework_tech_id)
        if technology is None:
            errors.append(
                f"{task_id}: {property_id} requires its current PROPERTY_TESTING "
                "technology decision"
            )
            continue
        try:
            validate_done_property_evidence(
                property_rows,
                task,
                snapshot,
                expected,
                technology,
                completion_rows,
                policy,
                require_done_pass=task.status == "DONE",
            )
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError("\n".join(errors))
    return list(graph.tasks), graph.by_id, list(graph.ready_task_ids)


def missing_current_property_task_coverage(
    tasks: list[InspectedTask],
    plan_state: str,
    property_execution_by_id: Mapping[str, Any],
    policy: DeliveryValidationPolicy,
) -> list[str]:
    """Return approved properties omitted from a current task plan."""

    if plan_state != "CURRENT":
        return []
    covered_property_ids = {
        property_id
        for task in tasks
        if task.status in {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE"}
        for property_id in policy.property_id.findall(
            clean_cell(task.metadata.get("Requirements", ""))
        )
    }
    return sorted(set(property_execution_by_id) - covered_property_ids)


def task_requirement_rules(
    prd_text: str,
    requirements_contract: Any,
    schema_13_requirement_rows: Callable[
        [str], tuple[list[tuple[str, ...]], dict[str, str], set[str]]
    ],
) -> dict[str, tuple[str, str]]:
    """SAFETY: bind each current requirement to its exact acceptance rule."""

    if requirements_contract.grandfathered_approved_gate_a:
        return {}
    rows, acceptance_by_requirement, _legacy_ids = schema_13_requirement_rows(prd_text)
    row_by_id = {row[0]: row for row in rows}
    expected_requirements = set(requirements_contract.requirement_ids)
    if set(row_by_id) != expected_requirements:
        raise ValueError(
            "Task requirement rules do not match the current requirements contract"
        )
    expected_acceptance = set(requirements_contract.acceptance_ids)
    observed_acceptance = {
        acceptance_by_requirement.get(requirement_id, "")
        for requirement_id in expected_requirements
    }
    if observed_acceptance != expected_acceptance:
        raise ValueError(
            "Task acceptance rules do not match the current requirements contract"
        )
    return {
        requirement_id: (
            acceptance_by_requirement[requirement_id],
            row_by_id[requirement_id][2],
        )
        for requirement_id in sorted(expected_requirements)
    }


def task_requirement_evidence_dispositions(
    verify_text: str | None,
    expected_basis: Mapping[str, str],
    rules: Mapping[str, tuple[str, str]],
) -> tuple[
    dict[str, tuple[str, tuple[str, ...]]],
    tuple[str, ...],
]:
    """SAFETY: resolve no-task dispositions only from current exact evidence."""

    if verify_text is None or not rules:
        return {}, ()
    try:
        active_scope = table_after_heading(verify_text, "## Active evidence scope")
        rows = parse_verification_matrix(verify_text)
    except ValueError as exc:
        return {}, (str(exc),)
    for key in (
        "Requirements revision",
        "Design revision",
        "Construction authorization",
    ):
        if clean_cell(active_scope.get(key, "")) != clean_cell(
            expected_basis.get(key, "")
        ):
            return {}, ()

    issues: list[str] = []
    by_requirement: dict[str, dict[str, list[str]]] = {}
    seen_evidence_ids: set[str] = set()
    for row in rows:
        status = clean_cell(row.get("Status", "")).upper()
        if status not in {"LOCAL_PASS", "VERIFIED", "NOT_APPLICABLE"}:
            continue
        if clean_cell(row.get("Task IDs", "")).upper() != "NONE":
            continue
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id) is None:
            issues.append(
                "No-task requirement evidence requires an EV-nnnn Evidence ID"
            )
            continue
        if evidence_id in seen_evidence_ids:
            issues.append(f"Duplicate no-task requirement evidence ID {evidence_id}")
            continue
        seen_evidence_ids.add(evidence_id)
        try:
            basis_ids = canonical_id_list(
                row.get("PRD / property IDs", ""),
                STABLE_CONTRACT_ID,
                f"{evidence_id} PRD / property IDs",
            )
        except ValueError as exc:
            issues.append(str(exc))
            continue
        matching_requirements = [
            requirement_id
            for requirement_id, (acceptance_id, _ears_form) in rules.items()
            if basis_ids == [requirement_id, acceptance_id]
        ]
        if len(matching_requirements) != 1:
            issues.append(
                f"{evidence_id}: no-task evidence must bind exactly one current "
                "requirement and its canonical acceptance ID"
            )
            continue
        requirement_id = matching_requirements[0]
        acceptance_id, ears_form = rules[requirement_id]
        requirement_or_invariant = clean_cell(row.get("Requirement or invariant", ""))
        artifact = clean_cell(row.get("Artifact/environment", ""))
        automated = clean_cell(row.get("Automated evidence", ""))
        manual = clean_cell(row.get("AWS/manual evidence", ""))
        if not explicit_value(requirement_or_invariant, allow_none=False):
            issues.append(
                f"{evidence_id}: no-task evidence requires a concrete requirement or invariant"
            )
        if not explicit_value(artifact, allow_none=False):
            issues.append(
                f"{evidence_id}: no-task evidence requires a concrete artifact/environment"
            )
        if not (
            explicit_value(automated, allow_none=False)
            or explicit_value(manual, allow_none=False)
        ):
            issues.append(
                f"{evidence_id}: no-task evidence requires automated or AWS/manual evidence"
            )
        disposition = (
            "NOT_APPLICABLE" if status == "NOT_APPLICABLE" else "ALREADY_SATISFIED"
        )
        if disposition == "NOT_APPLICABLE" and ears_form != "OPTIONAL_FEATURE":
            issues.append(
                f"{evidence_id}: NOT_APPLICABLE is allowed only for OPTIONAL_FEATURE requirements"
            )
            continue
        by_requirement.setdefault(requirement_id, {}).setdefault(
            disposition, []
        ).append(evidence_id)
        if acceptance_id not in basis_ids:
            issues.append(
                f"{evidence_id}: missing canonical acceptance ID {acceptance_id}"
            )

    dispositions: dict[str, tuple[str, tuple[str, ...]]] = {}
    for requirement_id, observed in sorted(by_requirement.items()):
        if len(observed) != 1:
            issues.append(
                f"{requirement_id}: conflicting no-task evidence dispositions"
            )
            continue
        disposition, evidence_ids = next(iter(observed.items()))
        dispositions[requirement_id] = (
            disposition,
            tuple(sorted(evidence_ids)),
        )
    return dispositions, tuple(issues)


def derive_task_requirement_coverage(
    tasks: Sequence[Any],
    plan_state: str,
    rules: Mapping[str, tuple[str, str]],
    evidence_dispositions: Mapping[str, tuple[str, tuple[str, ...]]],
) -> TaskRequirementCoverageResult:
    """SAFETY: derive exactly one coverage disposition per approved requirement."""

    if plan_state != "CURRENT" or not rules:
        return TaskRequirementCoverageResult()
    counted_statuses = {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE"}
    acceptance_owner = {
        acceptance_id: requirement_id
        for requirement_id, (acceptance_id, _ears_form) in rules.items()
    }
    requirement_families = {
        requirement_id.rsplit("-", 1)[0] for requirement_id in rules
    }
    covered_by_task: dict[str, set[str]] = {
        requirement_id: set() for requirement_id in rules
    }
    trace_issues: list[str] = []
    evidence_issues: list[str] = []
    for task in tasks:
        task_id = str(getattr(task, "task_id", "TASK-UNKNOWN"))
        status = clean_cell(getattr(task, "status", "")).upper()
        metadata = getattr(task, "metadata", {})
        requirements_value = clean_cell(metadata.get("Requirements", ""))
        tokens = STABLE_CONTRACT_ID.findall(requirements_value)
        relevant_tokens = [
            token
            for token in tokens
            if token in rules
            or token in acceptance_owner
            or ACCEPTANCE_ID.fullmatch(token) is not None
            or token.rsplit("-", 1)[0] in requirement_families
        ]
        duplicates = sorted(
            token for token in set(relevant_tokens) if relevant_tokens.count(token) > 1
        )
        if duplicates:
            trace_issues.append(
                f"{task_id}: duplicate requirement/acceptance IDs: "
                + ", ".join(duplicates)
            )
        unknown_acceptance = sorted(
            {
                token
                for token in relevant_tokens
                if ACCEPTANCE_ID.fullmatch(token) is not None
                and token not in acceptance_owner
            }
        )
        if unknown_acceptance:
            trace_issues.append(
                f"{task_id}: unknown acceptance IDs: " + ", ".join(unknown_acceptance)
            )
        unknown_requirements = sorted(
            {
                token
                for token in relevant_tokens
                if ACCEPTANCE_ID.fullmatch(token) is None
                and token not in rules
                and token.rsplit("-", 1)[0] in requirement_families
            }
        )
        if unknown_requirements:
            trace_issues.append(
                f"{task_id}: unknown approved-requirement references: "
                + ", ".join(unknown_requirements)
            )
        token_set = set(relevant_tokens)
        valid_pairs: set[str] = set()
        for requirement_id, (acceptance_id, _ears_form) in rules.items():
            has_requirement = requirement_id in token_set
            has_acceptance = acceptance_id in token_set
            if has_requirement and not has_acceptance:
                trace_issues.append(
                    f"{task_id}: {requirement_id} requires {acceptance_id}"
                )
            if has_acceptance and not has_requirement:
                trace_issues.append(
                    f"{task_id}: {acceptance_id} requires owning requirement {requirement_id}"
                )
            if has_requirement and has_acceptance:
                valid_pairs.add(requirement_id)
        if status in counted_statuses:
            for requirement_id in valid_pairs:
                covered_by_task[requirement_id].add(task_id)

    records: list[TaskRequirementCoverage] = []
    missing: list[str] = []
    for requirement_id, (acceptance_id, _ears_form) in sorted(rules.items()):
        task_ids = tuple(sorted(covered_by_task[requirement_id]))
        evidence = evidence_dispositions.get(requirement_id)
        if task_ids:
            if evidence is not None and evidence[0] == "NOT_APPLICABLE":
                evidence_issues.append(
                    f"{requirement_id}: task coverage conflicts with NOT_APPLICABLE evidence"
                )
            records.append(
                TaskRequirementCoverage(
                    requirement_id,
                    acceptance_id,
                    "TASK_COVERED",
                    task_ids=task_ids,
                )
            )
        elif evidence is not None:
            records.append(
                TaskRequirementCoverage(
                    requirement_id,
                    acceptance_id,
                    evidence[0],
                    evidence_ids=evidence[1],
                )
            )
        else:
            missing.append(requirement_id)
    return TaskRequirementCoverageResult(
        records=tuple(records),
        trace_issues=tuple(trace_issues),
        evidence_issues=tuple(evidence_issues),
        missing_requirement_ids=tuple(missing),
    )


__all__ = (
    "TASK_AWS_MODES",
    "TASK_METADATA_KEYS",
    "TASK_STATUSES",
    "compute_task_waves",
    "declared_task_waivers",
    "derive_ready_task_ids",
    "derive_task_requirement_coverage",
    "inspect_task_blocks",
    "inspect_task_sections",
    "missing_current_property_task_coverage",
    "parse_task_snapshot",
    "parse_task_external_targets",
    "parse_task_write_boundary",
    "parse_task_waivers",
    "task_dependency_satisfied",
    "task_requirement_evidence_dispositions",
    "task_requirement_rules",
    "task_waiver_rows",
    "validate_new_build_delivery_order",
    "validate_task_graph",
    "validate_task_records",
    "validate_task_snapshot",
)
