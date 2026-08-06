"""Immutable Delivery-domain records for Fastlane task and evidence validation.

Canonical inputs are caller-supplied TASKS, VERIFY, PRD, and snapshot fields.
Returned models are non-authoritative validation results or normalized records.
This module performs no I/O or mutation and grants no task, GitHub, or AWS authority.
Public field names and serialization preserve the Fastlane 1.2.14 contracts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Pattern
from typing import Any

from ..core.ids import clean_cell


@dataclass
class TaskSummary:
    plan_revision: str | None = None
    plan_state: str = "UNINITIALIZED"
    statuses: dict[str, str] = field(default_factory=dict)
    ready: list[str] = field(default_factory=list)
    active: list[str] = field(default_factory=list)
    write_sets: dict[str, list[str]] = field(default_factory=dict)
    attempts_used: dict[str, int] = field(default_factory=dict)
    attempt_budgets: dict[str, int] = field(default_factory=dict)
    requirement_coverage_complete: bool = False
    requirement_coverage: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing_requirement_ids: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.statuses)

    @property
    def done(self) -> list[str]:
        return sorted(
            task_id for task_id, status in self.statuses.items() if status == "DONE"
        )

    @property
    def skipped(self) -> list[str]:
        return sorted(
            task_id for task_id, status in self.statuses.items() if status == "SKIPPED"
        )

    @property
    def blocked(self) -> list[str]:
        return sorted(
            task_id for task_id, status in self.statuses.items() if status == "BLOCKED"
        )

    @property
    def terminal(self) -> bool:
        return bool(self.statuses) and all(
            status in {"DONE", "SKIPPED"} for status in self.statuses.values()
        )


@dataclass(frozen=True)
class TaskRequirementCoverage:
    requirement_id: str
    acceptance_id: str
    disposition: str
    task_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "acceptance_id": self.acceptance_id,
            "disposition": self.disposition,
            "task_ids": list(self.task_ids),
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class TaskRequirementCoverageResult:
    records: tuple[TaskRequirementCoverage, ...] = ()
    trace_issues: tuple[str, ...] = ()
    evidence_issues: tuple[str, ...] = ()
    missing_requirement_ids: tuple[str, ...] = ()


@dataclass
class InspectedTask:
    task_id: str
    title: str
    block: str
    metadata: dict[str, str]
    duplicates: set[str]

    @property
    def status(self) -> str:
        return clean_cell(self.metadata.get("Status", "")).upper()

    @property
    def dependencies(self) -> list[str]:
        raw = clean_cell(self.metadata.get("Depends on", "NONE"))
        return (
            []
            if raw in {"", "NONE", "-"}
            else [item.strip() for item in raw.split(",")]
        )

    @property
    def attempts_used(self) -> int:
        return int(clean_cell(self.metadata["Attempts used"]))

    @property
    def attempt_budget(self) -> int:
        return int(clean_cell(self.metadata["Attempt budget"]))


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
class PropertyTestEvidenceRow:
    evidence_id: str
    task_id: str
    requirements_design_authorization: str
    property_id: str
    framework_tech_id: str
    framework_selection: str
    observed_exact_version: str
    exact_command: str
    observed_run: str
    replay_seed_or_exact_command: str
    minimized_counterexample: str
    failure_class_resolution: str
    result: str
    observed_at: str
    commit_worktree_artifact: str
    durable_source: str


@dataclass(frozen=True)
class CheckpointReceiptRow:
    checkpoint_id: str
    run_id: str
    recorded_at: str
    basis: str
    commit_and_dirty: str
    task_outcomes: str
    evidence_and_external: str
    blockers_and_next: str


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


@dataclass(frozen=True)
class DeliveryValidationPolicy:
    """Design-owned grammar explicitly supplied to Delivery validation.

    This keeps lifecycle domains independent while ensuring task evidence is
    checked against the same property and command contracts selected by Design.
    """

    property_id: Pattern[str]
    valid_property_execution_command: Callable[[str], bool]
    validation_commands: Callable[[str, str], list[str]]
    parse_property_run_target: Callable[[str], tuple[int | None, Decimal | None]]
    parsed_numeric_version: Callable[[str], tuple[int, ...] | None]
    technology_contract_value_is_unresolved: Callable[[str], bool]


__all__ = (
    "TaskSummary",
    "TaskRequirementCoverage",
    "TaskRequirementCoverageResult",
    "InspectedTask",
    "TaskCompletionEvidenceRow",
    "PropertyTestEvidenceRow",
    "CheckpointReceiptRow",
    "PropertyExecutionRow",
    "HarnessExecutionRow",
    "ApprovedSpikeContract",
    "ApprovedDeliveryContract",
    "ApprovedTaskContract",
    "DeliveryValidationPolicy",
)
