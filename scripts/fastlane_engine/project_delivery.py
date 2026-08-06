"""Project-level delivery, task, repository, and release orchestration.

Canonical inputs are the task/evidence ledgers plus approved requirements, design,
and construction envelope. Returns diagnostics and immutable task projections.
Read-only Git observation is delegated to the snapshot boundary; this module never
mutates tasks, writes files, routes, approves, or grants external authority.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .api import DELIVERY_VALIDATION_POLICY
from .aws import (
    parse_aws_lifecycle_intent_record as _parse_aws_lifecycle_intent_record_core,
)
from .core.contracts import table_after_heading
from .core.ids import clean_cell, explicit_timestamp, explicit_value
from .define.models import RequirementsContract
from .define.requirements import _schema_13_requirement_rows
from .design import (
    TECHNOLOGY_DECISION_ID,
    command_matches_prefix,
    parse_authorized_ids,
    parse_command_prefixes,
    parse_envelope_paths,
    parse_envelope_targets,
    parse_github_constraints,
    parse_task_boundary,
    validation_commands,
)
from .design.models import DesignContract, PropertyExecution, TechnologyDecision
from .deliver import (
    InspectedTask,
    PropertyTestEvidenceRow,
    TaskCompletionEvidenceRow,
    TaskRequirementCoverageResult,
    TaskSummary,
    derive_task_requirement_coverage as _derive_task_requirement_coverage_core,
    external_target_contains,
    inspect_task_sections,
    missing_current_property_task_coverage as _missing_property_coverage_core,
    parse_checkpoint_git_receipt,
    parse_checkpoint_rows,
    parse_property_test_evidence as _parse_property_test_evidence_core,
    parse_release_decision_record as _parse_release_decision_record_core,
    task_requirement_evidence_dispositions,
    task_requirement_rules as _task_requirement_rules_core,
    technology_version_policy_allows as _technology_version_policy_allows_core,
    validate_done_property_evidence as _validate_done_property_evidence_core,
    validate_task_property_execution_projection as _validate_property_projection_core,
    validate_task_records as _validate_task_records_core,
)
from .core.snapshot import GitObservationError, git_read
from .project_inspection import (
    CHECKPOINT_ID,
    COORDINATOR_LEDGER_PATHS,
    EVIDENCE_PATTERN,
    GITHUB_ISSUE_URL,
    ID_LIKE,
    PLAN_ID,
    PRD_FILE,
    RUN_ID,
    SNAPSHOT_FIELDS,
    SNAPSHOT_RUN_STATES,
    STATE_FILE,
    TASKS_FILE,
    VERIFY_FILE,
    Context,
    parse_future_expiry,
    parse_task_external_state,
    parse_task_write_set,
    safe_read_text,
)

try:
    from fastlane_contracts import (
        external_targets_overlap,
        path_boundaries_overlap,
        path_boundary_contains,
        without_fenced_code,
    )
except ModuleNotFoundError:
    from scripts.fastlane_contracts import (
        external_targets_overlap,
        path_boundaries_overlap,
        path_boundary_contains,
        without_fenced_code,
    )


def validate_task_property_execution_projection(
    validation_section: str,
    task_id: str,
    requirements: str,
    technology_refs: list[str],
    property_execution_by_id: dict[str, PropertyExecution] | None,
) -> None:
    """COMPATIBILITY: supply the current Design grammar to Delivery validation."""

    _validate_property_projection_core(
        validation_section,
        task_id,
        requirements,
        technology_refs,
        property_execution_by_id,
        DELIVERY_VALIDATION_POLICY,
    )


def parse_property_test_evidence(text: str) -> list[PropertyTestEvidenceRow]:
    """COMPATIBILITY: parse property evidence with the current Design grammar."""

    return _parse_property_test_evidence_core(text, DELIVERY_VALIDATION_POLICY)


def technology_version_policy_allows(policy: str, observed: str) -> bool:
    """COMPATIBILITY: preserve the public Delivery evidence helper."""

    return _technology_version_policy_allows_core(
        policy, observed, DELIVERY_VALIDATION_POLICY
    )


def validate_done_property_evidence(
    rows: list[PropertyTestEvidenceRow],
    task: InspectedTask,
    snapshot: dict[str, str],
    expected: PropertyExecution,
    technology: TechnologyDecision,
    completion_rows: list[TaskCompletionEvidenceRow],
    *,
    require_done_pass: bool = True,
) -> None:
    """COMPATIBILITY: validate evidence through the pure Delivery domain."""

    _validate_done_property_evidence_core(
        rows,
        task,
        snapshot,
        expected,
        technology,
        completion_rows,
        DELIVERY_VALIDATION_POLICY,
        require_done_pass=require_done_pass,
    )


def validate_task_records(
    text: str,
    snapshot: dict[str, str],
    verify_text: str | None = None,
    approved_tech_ids: set[str] | None = None,
    property_execution_by_id: dict[str, PropertyExecution] | None = None,
    technology_decisions_by_id: dict[str, TechnologyDecision] | None = None,
) -> tuple[list[InspectedTask], dict[str, InspectedTask], list[str]]:
    """COMPATIBILITY: preserve the historical task-graph validator signature."""

    return _validate_task_records_core(
        text,
        snapshot,
        verify_text,
        approved_tech_ids,
        property_execution_by_id,
        technology_decisions_by_id,
        DELIVERY_VALIDATION_POLICY,
    )


def missing_current_property_task_coverage(
    tasks: list[InspectedTask],
    plan_state: str,
    property_execution_by_id: dict[str, PropertyExecution],
) -> list[str]:
    return _missing_property_coverage_core(
        tasks, plan_state, property_execution_by_id, DELIVERY_VALIDATION_POLICY
    )


def task_requirement_rules(
    prd_text: str,
    requirements_contract: RequirementsContract,
) -> dict[str, tuple[str, str]]:
    return _task_requirement_rules_core(
        prd_text, requirements_contract, _schema_13_requirement_rows
    )


def derive_task_requirement_coverage(
    tasks: Sequence[Any],
    plan_state: str,
    requirement_rules: Mapping[str, tuple[str, str]],
    evidence_dispositions: Mapping[str, tuple[str, tuple[str, ...]]],
) -> TaskRequirementCoverageResult:
    return _derive_task_requirement_coverage_core(
        tasks, plan_state, requirement_rules, evidence_dispositions
    )


def validate_tasks_against_envelope(
    ctx: Context,
    tasks: list[InspectedTask],
    snapshot: dict[str, str],
    state: dict[str, Any],
    envelope: dict[str, str],
) -> None:
    """SAFETY: intersect every task with the construction envelope."""

    try:
        maximum_tasks = int(envelope.get("Maximum generated tasks", ""))
        maximum_workers = int(envelope.get("Maximum parallel workers", ""))
        maximum_attempts = int(envelope.get("Attempt budget", ""))
        snapshot_workers = int(snapshot.get("Maximum workers", ""))
        allowed_writes = parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
        )
        excluded_writes = parse_envelope_paths(
            envelope.get("Excluded or owner-only write set", ""),
            "Excluded or owner-only write set",
            allow_none=True,
        )
        allowed_external = parse_envelope_targets(
            envelope.get("Allowed external-state targets", "")
        )
        authorized_protected = parse_envelope_paths(
            envelope.get("Protected dirty paths", ""),
            "Protected dirty paths",
            allow_none=True,
        )
        authorized_ids = set(
            parse_authorized_ids(
                envelope.get("Authorized requirement and design IDs", "")
            )
        )
        authorized_ids.update(ID_LIKE.findall(envelope.get("Authorized outcome", "")))
        boundary_mode, explicit_task_ids = parse_task_boundary(
            envelope.get("Task boundary", "")
        )
        command_prefixes = parse_command_prefixes(
            envelope.get("Local command boundary", "")
        )
        github_repo = parse_github_constraints(
            envelope.get("GitHub repository, branch, and merge constraints", ""),
            envelope.get("GitHub boundary", ""),
        )
        parse_future_expiry(
            envelope.get("Authorization expiry or completion condition", "")
        )
    except (ValueError, TypeError) as exc:
        if str(exc) == "Construction authorization is expired":
            ctx.error(
                "GATE_B_AUTHORITY_EXPIRED",
                "Gate B authority expired; the owner must reapprove the current "
                "design boundary before any new local or AWS operation",
                PRD_FILE,
            )
        else:
            ctx.error(
                "GATE_B_ENVELOPE",
                f"Cannot validate task boundaries: {exc}",
                PRD_FILE,
            )
        return
    if len(tasks) > maximum_tasks:
        ctx.error(
            "TASK_LIMIT_EXCEEDED",
            f"{len(tasks)} tasks exceed AUTH maximum {maximum_tasks}",
            TASKS_FILE,
        )
    if snapshot_workers > maximum_workers:
        ctx.error(
            "WORKER_LIMIT_EXCEEDED", "TASKS Maximum workers exceeds AUTH", TASKS_FILE
        )
    if maximum_workers != 1:
        ctx.error(
            "GATE_B_ENVELOPE",
            "Current AUTH must permit exactly one parallel worker",
            PRD_FILE,
        )
    if snapshot.get("Baseline commit") != envelope.get("Authorized baseline commit"):
        ctx.error(
            "TASK_BASELINE_DRIFT",
            "TASKS baseline commit does not match AUTH",
            TASKS_FILE,
        )
    snapshot_protected = snapshot.get("Protected dirty paths", "NONE")
    try:
        task_protected = (
            []
            if snapshot_protected == "NONE"
            else parse_task_write_set(snapshot_protected, "Protected dirty paths")
        )
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
        task_protected = []
    if [item.casefold() for item in task_protected] != [
        item.casefold() for item in authorized_protected
    ]:
        ctx.error(
            "TASK_BASELINE_DRIFT",
            "TASKS protected dirty paths do not match AUTH",
            TASKS_FILE,
        )

    execution = (
        state.get("execution") if isinstance(state.get("execution"), dict) else {}
    )
    if (
        execution.get("mode") == "AUTONOMOUS"
        and envelope.get("Autonomous construction") != "ALLOWED"
    ):
        ctx.error(
            "AUTONOMY_OUTSIDE_AUTH",
            "AUTONOMOUS run is not allowed by Gate B",
            STATE_FILE,
        )
    if not tasks:
        return

    github_boundary = envelope.get("GitHub boundary", "NONE")
    aws_boundary = envelope.get("AWS boundary", "NONE")
    protected = snapshot.get("Protected dirty paths", "NONE")
    try:
        protected_paths = (
            []
            if protected == "NONE"
            else parse_task_write_set(protected, "Protected dirty paths")
        )
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
        protected_paths = []

    for task in tasks:
        try:
            writes = parse_task_write_set(task.metadata["Write set"], task.task_id)
            external_targets = parse_task_external_state(
                task.metadata["External state"], task.task_id
            )
        except (KeyError, ValueError):
            continue
        for requested in writes:
            if not any(
                path_boundary_contains(allowed, requested) for allowed in allowed_writes
            ):
                ctx.error(
                    "TASK_OUTSIDE_WRITE_BOUNDARY",
                    f"{task.task_id} write {requested!r} is outside AUTH",
                    TASKS_FILE,
                )
            if any(
                path_boundaries_overlap(requested, excluded)
                for excluded in excluded_writes
            ):
                ctx.error(
                    "TASK_EXCLUDED_WRITE",
                    f"{task.task_id} overlaps excluded path {requested!r}",
                    TASKS_FILE,
                )
            if task.status in {"READY", "IN_PROGRESS"} and any(
                path_boundaries_overlap(requested, dirty) for dirty in protected_paths
            ):
                ctx.error(
                    "TASK_PROTECTED_DIRTY_OVERLAP",
                    f"{task.task_id} overlaps protected dirty path {requested!r}",
                    TASKS_FILE,
                )
        for target in external_targets:
            if not any(
                external_target_contains(allowed, target)
                for allowed in allowed_external
            ):
                ctx.error(
                    "TASK_EXTERNAL_STATE_BOUNDARY",
                    f"{task.task_id} external target {target!r} is outside AUTH",
                    TASKS_FILE,
                )
        if boundary_mode == "EXPLICIT" and task.task_id not in explicit_task_ids:
            ctx.error(
                "TASK_OUTSIDE_TASK_BOUNDARY",
                f"{task.task_id} is not listed by AUTH",
                TASKS_FILE,
            )

        sections, _duplicates = inspect_task_sections(task.block)
        referenced_ids = set(ID_LIKE.findall(task.metadata.get("Requirements", "")))
        referenced_ids.update(
            item
            for item in ID_LIKE.findall(task.metadata.get("Design", ""))
            if TECHNOLOGY_DECISION_ID.fullmatch(item) is None
        )
        referenced_ids.update(ID_LIKE.findall(sections.get("Outcome", "")))
        outside_ids = sorted(referenced_ids - authorized_ids)
        if outside_ids:
            ctx.error(
                "TASK_ID_OUTSIDE_AUTH",
                f"{task.task_id} references unauthorized IDs: {', '.join(outside_ids)}",
                TASKS_FILE,
            )
        if task.status in {"READY", "IN_PROGRESS", "DONE"}:
            try:
                commands = validation_commands(
                    sections.get("Validation", ""), task.task_id
                )
                for command in commands:
                    if not any(
                        command_matches_prefix(command, prefix)
                        for prefix in command_prefixes
                    ):
                        ctx.error(
                            "TASK_COMMAND_BOUNDARY",
                            f"{task.task_id} command {command!r} is outside AUTH",
                            TASKS_FILE,
                        )
            except ValueError as exc:
                ctx.error("TASK_COMMAND_BOUNDARY", str(exc), TASKS_FILE)
        try:
            if task.attempt_budget > maximum_attempts:
                ctx.error(
                    "TASK_ATTEMPT_BOUNDARY",
                    f"{task.task_id} attempt budget exceeds AUTH",
                    TASKS_FILE,
                )
        except (KeyError, ValueError):
            pass
        aws_mode = clean_cell(task.metadata.get("AWS mode", "NONE")).upper()
        allowed_aws_modes = {
            "NONE": {"NONE"},
            "DOCS_ONLY": {"NONE", "DOCS_ONLY"},
            "READ_ONLY": {"NONE", "DOCS_ONLY"},
            "MUTATE_LISTED_RESOURCES": {"NONE", "DOCS_ONLY"},
        }
        if aws_mode not in allowed_aws_modes.get(aws_boundary, set()):
            ctx.error(
                "TASK_AWS_BOUNDARY",
                f"{task.task_id} AWS mode exceeds the local-task ceiling",
                TASKS_FILE,
            )
        issue = clean_cell(task.metadata.get("GitHub issue", "PENDING_SYNC"))
        if github_boundary in {"NONE", "READ_ONLY"} and issue != "PENDING_SYNC":
            ctx.error(
                "TASK_GITHUB_BOUNDARY",
                f"{task.task_id} has a GitHub write result outside AUTH",
                TASKS_FILE,
            )
        elif github_boundary not in {"NONE", "READ_ONLY"} and issue != "PENDING_SYNC":
            match = GITHUB_ISSUE_URL.fullmatch(issue)
            if (
                match is None
                or github_repo is None
                or match.group("repo").casefold() != github_repo.casefold()
            ):
                ctx.error(
                    "TASK_GITHUB_BOUNDARY",
                    f"{task.task_id} issue URL does not match the authorized GitHub repository",
                    TASKS_FILE,
                )

    active = [task for task in tasks if task.status == "IN_PROGRESS"]
    if len(active) > min(maximum_workers, snapshot_workers):
        ctx.error(
            "WORKER_LIMIT_EXCEEDED",
            "IN_PROGRESS tasks exceed the active worker limit",
            TASKS_FILE,
        )
    for index, first in enumerate(active):
        first_writes = parse_task_write_set(first.metadata["Write set"], first.task_id)
        first_external = parse_task_external_state(
            first.metadata["External state"], first.task_id
        )
        for second in active[index + 1 :]:
            second_writes = parse_task_write_set(
                second.metadata["Write set"], second.task_id
            )
            second_external = parse_task_external_state(
                second.metadata["External state"], second.task_id
            )
            conflict = any(
                path_boundaries_overlap(a, b)
                for a in first_writes
                for b in second_writes
            )
            conflict |= any(
                external_targets_overlap(a, b)
                for a in first_external
                for b in second_external
            )
            conflict |= clean_cell(first.metadata["AWS mode"]).upper() == "MUTATION"
            conflict |= clean_cell(second.metadata["AWS mode"]).upper() == "MUTATION"
            if conflict:
                ctx.error(
                    "ACTIVE_TASK_CONFLICT",
                    f"{first.task_id} conflicts with {second.task_id}",
                    TASKS_FILE,
                )


LEGACY_TASK_AWS_MODE = re.compile(
    r"^(?P<task>TASK-\d+): invalid AWS mode '(?:READ_ONLY|MUTATION)'$"
)


def validate_checkpoint_record(
    ctx: Context,
    tasks_text: str,
    snapshot: dict[str, str],
    tasks: list[InspectedTask],
    verify_text: str | None,
) -> None:
    """SAFETY: validate one exact resumable checkpoint and its evidence."""

    checkpoint_id = snapshot.get("Last checkpoint", "")
    try:
        rows = parse_checkpoint_rows(tasks_text)
        matching = [row for row in rows if row.checkpoint_id == checkpoint_id]
        if not rows or len(matching) != 1 or rows[-1].checkpoint_id != checkpoint_id:
            raise ValueError(
                f"{checkpoint_id}: must be the unique newest checkpoint row"
            )
        row = matching[0]
        if row.run_id != snapshot.get("Active run ID"):
            raise ValueError(
                f"{checkpoint_id}: checkpoint run does not match the snapshot"
            )
        if not explicit_timestamp(row.recorded_at):
            raise ValueError(
                f"{checkpoint_id}: checkpoint time must be ISO 8601 with timezone"
            )
        for prefix, expected in (
            ("REQ", snapshot.get("Requirements revision", "")),
            ("DES", snapshot.get("Design revision", "")),
            ("AUTH", snapshot.get("Construction authorization", "")),
        ):
            if re.findall(rf"\b{prefix}-\d{{4,}}\b", row.basis) != [expected]:
                raise ValueError(
                    f"{checkpoint_id}: checkpoint REQ/DES/AUTH basis is not current"
                )
        parse_checkpoint_git_receipt(tasks_text, checkpoint_id)
        if not explicit_value(row.task_outcomes):
            raise ValueError(
                f"{checkpoint_id}: task outcomes and attempts are unresolved"
            )
        for task in tasks:
            token = re.compile(
                rf"(?<![A-Za-z0-9-]){re.escape(task.task_id)}(?![A-Za-z0-9-])"
            )
            segments = [
                segment.strip()
                for segment in re.split(r"[;\n]", row.task_outcomes)
                if token.search(segment) is not None
            ]
            if (
                len(segments) != 1
                or re.search(rf"\b{re.escape(task.status)}\b", segments[0]) is None
            ):
                raise ValueError(
                    f"{checkpoint_id}: outcome for {task.task_id} is not current"
                )
            attempt = re.compile(
                rf"\battempts?(?:\s+used)?\s*[=:]\s*{task.attempts_used}"
                rf"(?:\s*/\s*{task.attempt_budget})?(?!\s*/\s*\d)\b",
                re.IGNORECASE,
            )
            if attempt.search(segments[0]) is None:
                raise ValueError(
                    f"{checkpoint_id}: attempts for {task.task_id} are not current"
                )
        if (
            not explicit_value(row.evidence_and_external)
            or re.search(r"\bevidence\b", row.evidence_and_external, re.IGNORECASE)
            is None
            or re.search(r"\bexternal\b", row.evidence_and_external, re.IGNORECASE)
            is None
        ):
            raise ValueError(
                f"{checkpoint_id}: evidence and external actions are unresolved"
            )
        evidence_cell = row.evidence_and_external
        for task in tasks:
            references = [
                match.group(0)
                for match in EVIDENCE_PATTERN.finditer(
                    clean_cell(task.metadata.get("Evidence", ""))
                )
            ]
            if any(
                re.search(
                    rf"(?<![A-Za-z0-9._-]){re.escape(reference)}(?![A-Za-z0-9._-])",
                    evidence_cell,
                    re.IGNORECASE,
                )
                is None
                for reference in references
            ):
                raise ValueError(
                    f"{checkpoint_id}: evidence for {task.task_id} is incomplete"
                )
        if (
            not explicit_value(row.blockers_and_next)
            or re.search(r"\bblockers?\b", row.blockers_and_next, re.IGNORECASE) is None
            or re.search(r"\bnext\b", row.blockers_and_next, re.IGNORECASE) is None
        ):
            raise ValueError(
                f"{checkpoint_id}: blockers and next action are unresolved"
            )
        structural_verify = (
            without_fenced_code(verify_text) if verify_text is not None else ""
        )
        if (
            re.search(
                rf"(?<![A-Za-z0-9-]){re.escape(checkpoint_id)}(?![A-Za-z0-9-])",
                structural_verify,
            )
            is None
        ):
            raise ValueError(
                f"{checkpoint_id}: checkpoint is not referenced in VERIFY.md"
            )
    except (KeyError, ValueError) as exc:
        ctx.error("CONSTRUCTION_CHECKPOINT_UNVERIFIED", str(exc), TASKS_FILE)


def validate_construction_repository(
    ctx: Context,
    snapshot: dict[str, str],
    *,
    tasks_text: str | None,
    reconcile_worktree: bool,
) -> None:
    """SAFETY: prove construction history and checkpoint dirty state."""

    baseline = snapshot.get("Baseline commit", "")
    known_green = snapshot.get("Last known-green commit", "")
    for label, value in (
        ("Baseline commit", baseline),
        ("Last known-green commit", known_green),
    ):
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
            ctx.error(
                "CONSTRUCTION_GIT_UNVERIFIED",
                f"{label} must be a full lowercase Git commit ID",
                TASKS_FILE,
            )
            return

    checkpoint_commit: str | None = None
    checkpoint_dirty: list[str] | None = None
    if reconcile_worktree and tasks_text is not None:
        checkpoint_id = snapshot.get("Last checkpoint", "")
        if CHECKPOINT_ID.fullmatch(checkpoint_id) is None:
            ctx.error(
                "CONSTRUCTION_CHECKPOINT_UNVERIFIED",
                "Checkpointed construction requires a current checkpoint receipt",
                TASKS_FILE,
            )
            return
        try:
            checkpoint_commit, checkpoint_dirty = parse_checkpoint_git_receipt(
                tasks_text, checkpoint_id
            )
        except ValueError as exc:
            ctx.error("CONSTRUCTION_CHECKPOINT_UNVERIFIED", str(exc), TASKS_FILE)
            return

    try:
        inside = git_read(ctx.root, "rev-parse", "--is-inside-work-tree")
        bare = git_read(ctx.root, "rev-parse", "--is-bare-repository")
        head_result = git_read(ctx.root, "rev-parse", "--verify", "HEAD^{commit}")
        baseline_result = git_read(
            ctx.root, "rev-parse", "--verify", f"{baseline}^{{commit}}"
        )
        green_result = git_read(
            ctx.root, "rev-parse", "--verify", f"{known_green}^{{commit}}"
        )
        checkpoint_result = (
            git_read(
                ctx.root, "rev-parse", "--verify", f"{checkpoint_commit}^{{commit}}"
            )
            if checkpoint_commit is not None
            else None
        )
    except GitObservationError as exc:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            f"Unable to inspect construction Git state read-only: {exc}",
            TASKS_FILE,
        )
        return
    if (
        inside.returncode != 0
        or inside.stdout.strip() != b"true"
        or bare.returncode != 0
        or bare.stdout.strip() != b"false"
    ):
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Construction requires a regular local Git worktree",
            TASKS_FILE,
        )
        return
    commit_results = [head_result, baseline_result, green_result]
    if checkpoint_result is not None:
        commit_results.append(checkpoint_result)
    if any(result.returncode != 0 for result in commit_results):
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Authorized baseline, last-known-green, or checkpoint commit cannot be resolved",
            TASKS_FILE,
        )
        return
    resolved_baseline = baseline_result.stdout.decode("ascii", errors="replace").strip()
    resolved_green = green_result.stdout.decode("ascii", errors="replace").strip()
    if resolved_baseline != baseline or resolved_green != known_green:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Construction commit identities must be exact full hashes",
            TASKS_FILE,
        )
        return
    if checkpoint_result is not None and (
        checkpoint_result.stdout.decode("ascii", errors="replace").strip()
        != resolved_green
    ):
        ctx.error(
            "CONSTRUCTION_CHECKPOINT_UNVERIFIED",
            "Checkpoint receipt commit does not match Last known-green commit",
            TASKS_FILE,
        )
        return

    try:
        baseline_ancestor = git_read(
            ctx.root, "merge-base", "--is-ancestor", baseline, known_green
        )
        green_ancestor = git_read(
            ctx.root, "merge-base", "--is-ancestor", known_green, "HEAD"
        )
        committed = git_read(
            ctx.root,
            "diff",
            "--name-only",
            "-z",
            "--relative",
            f"{known_green}..HEAD",
            "--",
            ".",
        )
    except GitObservationError as exc:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            f"Unable to compare construction Git history: {exc}",
            TASKS_FILE,
        )
        return
    if baseline_ancestor.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Authorized baseline is not an ancestor of Last known-green commit",
            TASKS_FILE,
        )
    if green_ancestor.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Last known-green commit is not an ancestor of current HEAD",
            TASKS_FILE,
        )
    if committed.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Unable to enumerate commits after Last known-green",
            TASKS_FILE,
        )
        return
    committed_paths = {
        item.decode("utf-8", errors="surrogateescape")
        for item in committed.stdout.split(b"\0")
        if item
    }
    unauthorized_committed = sorted(committed_paths - COORDINATOR_LEDGER_PATHS)
    if unauthorized_committed:
        ctx.error(
            "CONSTRUCTION_GIT_DRIFT",
            "Commits after Last known-green contain non-ledger paths: "
            + ", ".join(unauthorized_committed),
            TASKS_FILE,
        )

    if not reconcile_worktree:
        return
    try:
        tracked = git_read(
            ctx.root, "diff", "--name-only", "-z", "--relative", "HEAD", "--", "."
        )
        untracked = git_read(
            ctx.root, "ls-files", "--others", "--exclude-standard", "-z", "--", "."
        )
    except GitObservationError as exc:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            f"Unable to enumerate the checkpoint worktree: {exc}",
            TASKS_FILE,
        )
        return
    if tracked.returncode != 0 or untracked.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Unable to enumerate the checkpoint worktree",
            TASKS_FILE,
        )
        return
    observed = {
        item.decode("utf-8", errors="surrogateescape")
        for payload in (tracked.stdout, untracked.stdout)
        for item in payload.split(b"\0")
        if item
    }
    observed_nonledger = observed - COORDINATOR_LEDGER_PATHS
    protected_value = snapshot.get("Protected dirty paths", "NONE")
    try:
        protected = (
            []
            if protected_value == "NONE"
            else parse_task_write_set(protected_value, "Protected dirty paths")
        )
    except ValueError as exc:
        ctx.error("CONSTRUCTION_GIT_UNVERIFIED", str(exc), TASKS_FILE)
        return
    if checkpoint_dirty is not None and {
        item.casefold() for item in checkpoint_dirty
    } != {item.casefold() for item in protected}:
        ctx.error(
            "CONSTRUCTION_CHECKPOINT_UNVERIFIED",
            "Checkpoint Dirty paths do not match Protected dirty paths",
            TASKS_FILE,
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
        ctx.error(
            "CONSTRUCTION_WORKTREE_DRIFT",
            "Checkpoint protected paths do not exactly match the worktree: "
            + "; ".join(details),
            TASKS_FILE,
        )


def validate_resume_repository(
    ctx: Context,
    snapshot: dict[str, str],
    tasks_text: str | None = None,
) -> None:
    """Compatibility entry point for conservative checkpoint reconciliation."""

    validate_construction_repository(
        ctx,
        snapshot,
        tasks_text=tasks_text,
        reconcile_worktree=True,
    )


def record_task_graph_validation_errors(ctx: Context, message: str) -> None:
    """Project legacy authenticated task modes as a fail-closed replan."""

    issues = [line.strip() for line in message.splitlines() if line.strip()]
    legacy = [line for line in issues if LEGACY_TASK_AWS_MODE.fullmatch(line)]
    remaining = [line for line in issues if line not in legacy]
    if legacy:
        task_ids = sorted(
            {
                match.group("task")
                for line in legacy
                if (match := LEGACY_TASK_AWS_MODE.fullmatch(line)) is not None
            }
        )
        ctx.error(
            "TASK_AWS_MODE_REPLAN_REQUIRED",
            "Legacy authenticated task AWS mode requires replanning local work "
            f"for {', '.join(task_ids)}; preserve every DONE completion and "
            "append-only VERIFY evidence row rather than rewriting observed evidence",
            TASKS_FILE,
        )
    if remaining:
        ctx.error("TASK_GRAPH_INVALID", "\n".join(remaining), TASKS_FILE)


def validate_tasks(
    ctx: Context,
    state: dict[str, Any],
    prd_fields: dict[str, str],
    envelope: dict[str, str],
    requirements_contract: RequirementsContract,
    design_contract: DesignContract,
) -> TaskSummary:
    """SAFETY: validate the complete canonical task plan without mutation."""

    summary = TaskSummary()
    text = ctx.texts.get(TASKS_FILE) or safe_read_text(ctx, TASKS_FILE)
    if text is None:
        return summary
    try:
        snapshot = table_after_heading(text, "## Active execution snapshot")
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
        return summary

    if set(snapshot) != SNAPSHOT_FIELDS:
        missing = sorted(SNAPSHOT_FIELDS - set(snapshot))
        extra = sorted(set(snapshot) - SNAPSHOT_FIELDS)
        details: list[str] = []
        if missing:
            details.append("missing=" + ", ".join(missing))
        if extra:
            details.append("unexpected=" + ", ".join(extra))
        ctx.error(
            "TASK_SNAPSHOT",
            "Active execution snapshot fields must be exact: " + "; ".join(details),
            TASKS_FILE,
        )

    run_state = snapshot.get("Run state", "")
    if run_state not in SNAPSHOT_RUN_STATES:
        ctx.error("TASK_SNAPSHOT", f"Invalid Run state {run_state!r}", TASKS_FILE)
    try:
        snapshot_workers = int(snapshot.get("Maximum workers", ""))
        if snapshot_workers < 1:
            raise ValueError
    except ValueError:
        ctx.error(
            "TASK_SNAPSHOT", "Maximum workers must be a positive integer", TASKS_FILE
        )
    active_run_id = snapshot.get("Active run ID", "")
    coordinator = snapshot.get("Coordinator", "")
    if run_state == "NOT_STARTED":
        if active_run_id != "NONE" or coordinator != "UNASSIGNED":
            ctx.error(
                "TASK_SNAPSHOT",
                "NOT_STARTED requires no run ID and an unassigned coordinator",
                TASKS_FILE,
            )
    else:
        if RUN_ID.fullmatch(active_run_id) is None or coordinator in {
            "",
            "NONE",
            "UNASSIGNED",
            "TODO",
        }:
            ctx.error(
                "TASK_SNAPSHOT",
                "An active or checkpointed run requires a RUN ID and coordinator",
                TASKS_FILE,
            )
    current_wave = snapshot.get("Current wave", "")
    if current_wave != "NONE" and re.fullmatch(r"[1-9]\d*", current_wave) is None:
        ctx.error(
            "TASK_SNAPSHOT",
            "Current wave must be NONE or a positive integer",
            TASKS_FILE,
        )
    checkpoint = snapshot.get("Last checkpoint", "")
    if run_state in {"PAUSED", "BLOCKED", "COMPLETE"}:
        if CHECKPOINT_ID.fullmatch(checkpoint) is None:
            ctx.error(
                "TASK_SNAPSHOT", f"{run_state} requires a checkpoint ID", TASKS_FILE
            )
    elif checkpoint != "NONE":
        ctx.error(
            "TASK_SNAPSHOT",
            f"{run_state or 'unknown run state'} must not claim a checkpoint",
            TASKS_FILE,
        )
    try:
        if snapshot.get("Protected dirty paths") != "NONE":
            parse_task_write_set(
                snapshot.get("Protected dirty paths", ""), "Protected dirty paths"
            )
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
    if not explicit_value(snapshot.get("Next safe action", ""), allow_none=False):
        ctx.error("TASK_SNAPSHOT", "Next safe action must be explicit", TASKS_FILE)
    if snapshot.get("Gate B state") == "APPROVED_FOR_CONSTRUCTION":
        for key in ("Baseline commit", "Last known-green commit"):
            if (
                re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", snapshot.get(key, ""))
                is None
            ):
                ctx.error(
                    "TASK_SNAPSHOT",
                    f"Current Gate B requires a full lowercase {key}",
                    TASKS_FILE,
                )

    raw_plan = snapshot.get("Task-plan revision", "")
    summary.plan_state = snapshot.get("Task-plan state", "")
    summary.plan_revision = None if raw_plan == "UNINITIALIZED" else raw_plan
    if (
        summary.plan_revision is not None
        and PLAN_ID.fullmatch(summary.plan_revision) is None
    ):
        ctx.error(
            "TASK_PLAN_STATE",
            "Task-plan revision must be UNINITIALIZED or PLAN-nnnn",
            TASKS_FILE,
        )
    if summary.plan_state not in {"UNINITIALIZED", "CURRENT", "STALE"}:
        ctx.error(
            "TASK_PLAN_STATE",
            "Task-plan state must be UNINITIALIZED, CURRENT, or STALE",
            TASKS_FILE,
        )
    if summary.plan_revision is None and summary.plan_state != "UNINITIALIZED":
        ctx.error(
            "TASK_PLAN_STATE",
            "UNINITIALIZED revision requires UNINITIALIZED plan state",
            TASKS_FILE,
        )
    if summary.plan_revision is not None and summary.plan_state == "UNINITIALIZED":
        ctx.error(
            "TASK_PLAN_STATE",
            "Initialized revision cannot have UNINITIALIZED plan state",
            TASKS_FILE,
        )
    execution = (
        state.get("execution") if isinstance(state.get("execution"), dict) else {}
    )
    lifecycle = (
        state.get("lifecycle") if isinstance(state.get("lifecycle"), dict) else {}
    )
    if summary.plan_revision != execution.get("plan_revision"):
        ctx.error(
            "STATE_TASK_DRIFT",
            "Task-plan revision does not match bootstrap state",
            TASKS_FILE,
        )
    if summary.plan_state != execution.get("plan_state"):
        ctx.error(
            "STATE_TASK_DRIFT",
            "Task-plan state does not match bootstrap state",
            TASKS_FILE,
        )
    snapshot_pairs = {
        "Requirements revision": "requirements_revision",
        "Design revision": "design_revision",
        "Construction authorization": "construction_authorization",
        "Gate B state": "gate_b",
    }
    for snapshot_key, lifecycle_key in snapshot_pairs.items():
        if snapshot.get(snapshot_key) != lifecycle.get(lifecycle_key):
            ctx.error(
                "STATE_TASK_DRIFT",
                f"{snapshot_key} does not match lifecycle state",
                TASKS_FILE,
            )

    run_map = {
        "IDLE": "NOT_STARTED",
        "RUNNING": "RUNNING",
        "CHECKPOINTED": "PAUSED",
        "BLOCKED": "BLOCKED",
        "COMPLETE": "COMPLETE",
    }
    execution_state = (
        execution.get("state") if isinstance(execution.get("state"), str) else ""
    )
    expected_run = run_map.get(execution_state)
    if expected_run is not None and snapshot.get("Run state") != expected_run:
        ctx.error(
            "STATE_TASK_DRIFT", "Run state does not match bootstrap state", TASKS_FILE
        )
    expected_run_id = execution.get("run_id") or "NONE"
    if snapshot.get("Active run ID") != expected_run_id:
        ctx.error(
            "STATE_TASK_DRIFT",
            "Active run ID does not match bootstrap state",
            TASKS_FILE,
        )
    expected_coordinator = execution.get("coordinator") or "UNASSIGNED"
    if snapshot.get("Coordinator") != expected_coordinator:
        ctx.error(
            "STATE_TASK_DRIFT", "Coordinator does not match bootstrap state", TASKS_FILE
        )

    verify_text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    try:
        approved_tech_ids = {
            decision.decision_id for decision in design_contract.technology_decisions
        }
        property_execution_by_id = {
            execution.property_id: execution
            for execution in design_contract.property_execution
        }
        technology_decisions_by_id = {
            decision.decision_id: decision
            for decision in design_contract.technology_decisions
        }
        tasks, _by_id, ready = validate_task_records(
            text,
            snapshot,
            verify_text,
            approved_tech_ids,
            property_execution_by_id,
            technology_decisions_by_id,
        )
    except ValueError as exc:
        record_task_graph_validation_errors(ctx, str(exc))
        return summary

    missing_property_ids = missing_current_property_task_coverage(
        tasks,
        summary.plan_state,
        property_execution_by_id,
    )
    if missing_property_ids:
        ctx.error(
            "TASK_PROPERTY_COVERAGE",
            "CURRENT task plan does not cover approved property execution IDs: "
            + ", ".join(missing_property_ids),
            TASKS_FILE,
        )
    try:
        requirement_rules = (
            task_requirement_rules(ctx.texts.get(PRD_FILE, ""), requirements_contract)
            if summary.plan_state == "CURRENT"
            else {}
        )
        requirement_evidence, requirement_evidence_issues = (
            task_requirement_evidence_dispositions(
                verify_text,
                {
                    "Requirements revision": snapshot.get("Requirements revision", ""),
                    "Design revision": snapshot.get("Design revision", ""),
                    "Construction authorization": snapshot.get(
                        "Construction authorization", ""
                    ),
                },
                requirement_rules,
            )
        )
        requirement_coverage = derive_task_requirement_coverage(
            tasks,
            summary.plan_state,
            requirement_rules,
            requirement_evidence,
        )
    except ValueError as exc:
        ctx.error("TASK_REQUIREMENT_TRACE_INVALID", str(exc), TASKS_FILE)
    else:
        summary.requirement_coverage = {
            record.requirement_id: record.to_dict()
            for record in requirement_coverage.records
        }
        summary.missing_requirement_ids = list(
            requirement_coverage.missing_requirement_ids
        )
        summary.requirement_coverage_complete = bool(
            summary.plan_state == "CURRENT"
            and not requirement_coverage.trace_issues
            and not requirement_evidence_issues
            and not requirement_coverage.evidence_issues
            and not requirement_coverage.missing_requirement_ids
        )
        if requirement_coverage.trace_issues:
            ctx.error(
                "TASK_REQUIREMENT_TRACE_INVALID",
                "\n".join(requirement_coverage.trace_issues),
                TASKS_FILE,
            )
        all_evidence_issues = [
            *requirement_evidence_issues,
            *requirement_coverage.evidence_issues,
        ]
        if all_evidence_issues:
            ctx.error(
                "TASK_REQUIREMENT_COVERAGE_EVIDENCE_INVALID",
                "\n".join(all_evidence_issues),
                VERIFY_FILE,
            )
        if requirement_coverage.missing_requirement_ids:
            ctx.error(
                "TASK_REQUIREMENT_COVERAGE",
                "CURRENT task plan does not cover approved requirement IDs: "
                + ", ".join(requirement_coverage.missing_requirement_ids),
                TASKS_FILE,
            )

    if summary.plan_revision is None and tasks:
        ctx.error(
            "TASK_PLAN_STATE",
            "UNINITIALIZED task plan contains task blocks",
            TASKS_FILE,
        )
    if summary.plan_revision is not None and not tasks:
        ctx.error(
            "TASK_PLAN_STATE",
            "Initialized task plan contains no task blocks",
            TASKS_FILE,
        )
    if (
        summary.plan_state == "CURRENT"
        and prd_fields.get("gate_b") != "APPROVED_FOR_CONSTRUCTION"
    ):
        ctx.error(
            "TASK_PLAN_STATE", "CURRENT task plan requires current Gate B", TASKS_FILE
        )
    if summary.plan_state == "STALE" and any(
        task.status in {"READY", "IN_PROGRESS"} for task in tasks
    ):
        ctx.error(
            "TASK_PLAN_STATE",
            "STALE task plan cannot contain runnable or active tasks",
            TASKS_FILE,
        )

    summary.statuses = {task.task_id: task.status for task in tasks}
    summary.active = sorted(
        task.task_id for task in tasks if task.status == "IN_PROGRESS"
    )
    summary.ready = sorted(ready)
    summary.attempts_used = {task.task_id: task.attempts_used for task in tasks}
    summary.attempt_budgets = {task.task_id: task.attempt_budget for task in tasks}
    for task in tasks:
        try:
            summary.write_sets[task.task_id] = parse_task_write_set(
                task.metadata.get("Write set", ""), task.task_id
            )
        except ValueError:
            summary.write_sets[task.task_id] = []

    state_active_value = execution.get("active_tasks")
    state_active = (
        sorted(state_active_value)
        if isinstance(state_active_value, list)
        and all(isinstance(item, str) for item in state_active_value)
        else []
    )
    if summary.active != state_active:
        ctx.error(
            "STATE_TASK_DRIFT",
            "active_tasks does not match IN_PROGRESS task records",
            STATE_FILE,
        )
    task_attempts = {task.task_id: task.attempts_used for task in tasks}
    if execution.get("attempts") != task_attempts:
        ctx.error(
            "STATE_TASK_DRIFT", "attempt counters do not match task records", STATE_FILE
        )
    state_checkpoint = execution.get("last_checkpoint")
    expected_checkpoint = (
        state_checkpoint.get("id") if isinstance(state_checkpoint, dict) else "NONE"
    )
    if snapshot.get("Last checkpoint") != expected_checkpoint:
        ctx.error(
            "STATE_TASK_DRIFT",
            "Last checkpoint does not match bootstrap state",
            TASKS_FILE,
        )

    basis = execution.get("basis")
    if basis is not None:
        expected_basis = {
            "requirements_revision": prd_fields.get("requirements_revision"),
            "design_revision": prd_fields.get("design_revision"),
            "construction_authorization": prd_fields.get("construction_authorization"),
        }
        if basis != expected_basis:
            ctx.error(
                "RUN_BASIS_STALE",
                "Execution basis does not match current PRD revisions",
                STATE_FILE,
            )
    if prd_fields.get("gate_b") == "APPROVED_FOR_CONSTRUCTION" or tasks:
        validate_tasks_against_envelope(ctx, tasks, snapshot, state, envelope)
    construction_states = {"RUNNING", "CHECKPOINTED", "BLOCKED", "COMPLETE"}
    if execution_state in {"CHECKPOINTED", "BLOCKED", "COMPLETE"}:
        validate_checkpoint_record(ctx, text, snapshot, tasks, verify_text)
    if (
        prd_fields.get("gate_b") == "APPROVED_FOR_CONSTRUCTION"
        or execution_state in construction_states
    ):
        validate_construction_repository(
            ctx,
            snapshot,
            tasks_text=text,
            reconcile_worktree=execution_state
            in {"CHECKPOINTED", "BLOCKED", "COMPLETE"},
        )
    return summary


def validate_release_decision_record(ctx: Context) -> dict[str, str]:
    """Observe VERIFY and delegate release validation to Delivery."""

    relative = VERIFY_FILE
    text = ctx.texts.get(relative) or safe_read_text(ctx, relative)
    record, issues = _parse_release_decision_record_core(text)
    for code, message in issues:
        ctx.error(code, message, relative)
    return record


def validate_release_decision(ctx: Context) -> str:
    """Compatibility wrapper returning only the validated release state."""

    return validate_release_decision_record(ctx)["release_state"]


def validate_aws_lifecycle_intent_record(ctx: Context) -> dict[str, Any]:
    """Observe VERIFY and delegate non-authorizing lifecycle intent parsing."""

    text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    record, issues = _parse_aws_lifecycle_intent_record_core(text)
    for code, message in issues:
        ctx.error(code, message, VERIFY_FILE)
    return record


def validate_aws_lifecycle_intent(ctx: Context) -> str:
    """Compatibility wrapper returning only the validated intent value."""

    return str(validate_aws_lifecycle_intent_record(ctx)["value"])
