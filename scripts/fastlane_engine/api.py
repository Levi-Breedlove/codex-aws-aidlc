"""Supported read-only entry points for the Fastlane Engine foundation.

Inputs are repository-relative paths and caller-supplied observation policy.
Outputs are immutable snapshots, Define, Design, Delivery, or AWS projections.
Snapshot capture may read bounded regular files; domain evaluators consume caller-supplied text and
perform no I/O. The API never writes, runs Git, invokes AWS, approves a gate, or
grants authority.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

from .aws import (
    AwsAuthorityPolicy,
    AwsCoreEvidenceRow,
    aws_core_phase_evidence_issues,
    derive_aws_core_observed_usage,
    derive_aws_execution_projection,
    derive_deployment_sequence_state,
    derive_read_preflight_state,
    derive_teardown_sequence_state,
    parse_aws_core_evidence,
)

from .core.contracts import (
    contract_table_after_heading,
    parse_task_write_set,
    table_after_heading,
)
from .core.ids import clean_cell
from .core.snapshot import ProjectSnapshot, SnapshotObserver
from .define import (
    IntakeFoundationContract,
    RequirementsContract,
    derive_change_impact_contract,
    derive_coverage_contract,
    derive_intake_foundation_contract,
    derive_req_aws_materiality,
    derive_requirements_contract,
)
from .design import (
    PROPERTY_EXECUTION_HEADERS,
    PROPERTY_ID,
    TECHNOLOGY_DECISION_HEADERS,
    TECHNOLOGY_DECISION_HEADING,
    DesignContract,
    PropertyExecution,
    TechnologyDecision,
    canonical_envelope_sha256,
    derive_design_contract,
    evaluate_adr_rationale,
    parse_property_run_target,
    parsed_numeric_version,
    technology_contract_value_is_unresolved,
    valid_property_execution_command,
    validation_commands,
)
from .define.intake import PROJECT_MODES
from .define.requirements import _schema_13_requirement_rows, _state_trigger_map
from .define.requirements import authoritative_requirement_ids
from .deliver import (
    ApprovedDeliveryContract,
    ApprovedSpikeContract,
    ApprovedTaskContract,
    DeliveryValidationPolicy,
    HarnessExecutionRow,
    InspectedTask,
    PropertyExecutionRow,
    derive_task_requirement_coverage,
    parse_property_test_evidence,
    parse_task_completion_evidence,
    task_requirement_evidence_dispositions,
    task_requirement_rules,
    validate_done_property_evidence,
    validate_gate_b_execution_binding,
)


DELIVERY_VALIDATION_POLICY = DeliveryValidationPolicy(
    property_id=PROPERTY_ID,
    valid_property_execution_command=valid_property_execution_command,
    validation_commands=validation_commands,
    parse_property_run_target=parse_property_run_target,
    parsed_numeric_version=parsed_numeric_version,
    technology_contract_value_is_unresolved=technology_contract_value_is_unresolved,
)


def capture_project_snapshot(
    root: Path,
    paths: Iterable[str],
    *,
    text_paths: Iterable[str] = (),
    canonicalize_text: Callable[[str, str], str] | None = None,
) -> ProjectSnapshot:
    """SAFETY: capture one bounded snapshot without deriving lifecycle policy.

    Every requested path is opened at most once. Observation failures raise the
    fail-closed ``ObservationError`` supplied by ``core.snapshot``; callers map
    that error to their existing diagnostic surface.
    """

    text_set = frozenset(text_paths)
    observer = SnapshotObserver(root, canonicalize_text=canonicalize_text)
    for relative in paths:
        if relative in text_set:
            observer.observe_text(relative)
        else:
            observer.observe_binary(relative)
    return observer.freeze()


def derive_current_design_contract(
    text: str,
    design_revision: str | None,
    *,
    required: bool = False,
    grandfather_approved_v1: bool = False,
) -> tuple[DesignContract, list[str]]:
    """COMPATIBILITY: compose Define inputs for the current Design contract."""

    initial_issues: list[str] = []
    try:
        document = table_after_heading(text, "## Document status")
    except ValueError:
        document = {}
    repository_mode = clean_cell(document.get("Project mode", "")).lower()
    intake_contract, _intake_issues = derive_intake_foundation_contract(
        text,
        repository_mode if repository_mode in PROJECT_MODES else None,
        grandfather_current_gate_a=grandfather_approved_v1,
    )
    coverage_contract, coverage_issues = derive_coverage_contract(
        text,
        clean_cell(document.get("Current requirements revision", "")) or None,
        clean_cell(document.get("Delivery profile", "")) or None,
        clean_cell(document.get("Effective risk", "")) or None,
        clean_cell(document.get("AWS lane", "")) or None,
        required=required,
        grandfather_current_gate_a=grandfather_approved_v1,
        owner_work_context=intake_contract.owner_work_context,
    )
    requirements_contract, requirement_issues = derive_requirements_contract(
        text,
        clean_cell(document.get("Effective risk", "")) or None,
        intake_contract,
        required=required,
        grandfather_current_gate_a=grandfather_approved_v1,
    )
    if required:
        initial_issues.extend(coverage_issues)
        initial_issues.extend(issue for _code, issue in requirement_issues)
    return derive_design_contract(
        text,
        design_revision,
        required=required,
        grandfather_approved_v1=grandfather_approved_v1,
        coverage_contract=coverage_contract,
        requirements_contract=requirements_contract,
        authoritative_requirement_ids=authoritative_requirement_ids(text),
        change_impact_deriver=derive_change_impact_contract,
        state_trigger_mapper=_state_trigger_map,
        initial_issues=initial_issues,
    )


def validate_task_execution_basis(
    prd_text: str,
    tasks_text: str,
) -> tuple[dict[str, str], DesignContract]:
    """SAFETY: require a current task plan to bind the exact approved Gate B."""

    snapshot = table_after_heading(tasks_text, "## Active execution snapshot")
    if snapshot.get("Task-plan state") != "CURRENT":
        contract, _issues = derive_current_design_contract(
            prd_text,
            snapshot.get("Design revision"),
            grandfather_approved_v1=True,
        )
        return snapshot, contract
    contract, issues = derive_current_design_contract(
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
    validate_gate_b_execution_binding(
        prd_text,
        snapshot,
        contract,
        canonical_envelope_sha256(prd_text),
    )
    return snapshot, contract


def _technology_decisions(prd_text: str) -> tuple[TechnologyDecision, ...]:
    try:
        table = contract_table_after_heading(
            prd_text,
            TECHNOLOGY_DECISION_HEADING,
            TECHNOLOGY_DECISION_HEADERS,
        )
    except ValueError as exc:
        raise ValueError(
            f"docs/project/PRD.md technology decision register: {exc}"
        ) from exc
    if table is None:
        raise ValueError(
            "docs/project/PRD.md must contain exactly one technology decision register"
        )
    decisions = tuple(TechnologyDecision(*row) for row in table.rows)
    identifiers = [decision.decision_id for decision in decisions]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("docs/project/PRD.md has duplicate technology decision IDs")
    return decisions


def _property_execution_rows(prd_text: str) -> tuple[PropertyExecution, ...]:
    """CANONICALIZATION: parse uniquely ordered property execution rows."""

    try:
        table = contract_table_after_heading(
            prd_text,
            "### Property execution contract",
            PROPERTY_EXECUTION_HEADERS,
        )
    except ValueError as exc:
        raise ValueError(
            f"docs/project/PRD.md: property execution projection {exc}"
        ) from exc
    if table is None:
        return ()
    rows = tuple(PropertyExecution(*row) for row in table.rows)
    identifiers = [row.property_id for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("docs/project/PRD.md: duplicate property execution ID")
    for row in rows:
        if PROPERTY_ID.fullmatch(row.property_id) is None:
            raise ValueError(
                f"docs/project/PRD.md: invalid property execution ID {row.property_id!r}"
            )
        if not valid_property_execution_command(row.exact_command):
            raise ValueError(
                f"docs/project/PRD.md: {row.property_id} Exact command must be a concrete command"
            )
    return rows


def derive_approved_task_contract(
    prd_text: str,
    tasks_text: str,
    verify_text: str | None = None,
    *,
    full_template: bool,
) -> ApprovedTaskContract:
    """SAFETY: derive the bounded contract consumed by the sole task mutator."""

    technologies = _technology_decisions(prd_text)
    approved = [decision.decision_id for decision in technologies]
    technology_by_id = {decision.decision_id: decision for decision in technologies}
    property_rows = _property_execution_rows(prd_text)
    unknown_frameworks = sorted(
        {
            row.framework_tech_id
            for row in property_rows
            if row.framework_tech_id not in technology_by_id
        }
    )
    if unknown_frameworks:
        raise ValueError(
            "docs/project/PRD.md property execution rows reference unknown TECH IDs: "
            + ", ".join(unknown_frameworks)
        )
    enriched: dict[str, PropertyExecutionRow] = {}
    for execution in property_rows:
        framework = technology_by_id[execution.framework_tech_id]
        if framework.concern != "PROPERTY_TESTING":
            raise ValueError(
                f"docs/project/PRD.md {execution.property_id} Framework TECH ID must reference "
                "the PROPERTY_TESTING decision"
            )
        enriched[execution.property_id] = PropertyExecutionRow(
            execution.property_id,
            execution.framework_tech_id,
            execution.exact_command,
            execution.run_target_time_bound,
            execution.seed_or_reproduction_format,
            execution.evidence_destination,
            framework.selection,
            framework.version_policy,
        )
    if not full_template:
        return ApprovedTaskContract(frozenset(approved), enriched, {})

    snapshot, design_contract = validate_task_execution_basis(prd_text, tasks_text)
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
    source_kind = source_disposition.kind if source_disposition is not None else None
    source_paths = source_disposition.paths if source_disposition is not None else ()
    if project_contract.grandfathered_v4:
        delivery = ApprovedDeliveryContract(grandfathered=True)
    elif project_contract.first_wave is None:
        delivery = ApprovedDeliveryContract(
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
            approved_spike = ApprovedSpikeContract(
                spike_id=spike.spike_id,
                max_attempts=int(match.group(1)),
                disposable_boundaries=tuple(
                    parse_task_write_set(
                        spike.disposable_boundary,
                        f"docs/project/PRD.md {spike.spike_id}",
                    )
                ),
                exit_criterion=spike.exit_criterion,
            )
        delivery = ApprovedDeliveryContract(
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

    document = table_after_heading(prd_text, "## Document status")
    repository_mode = clean_cell(document.get("Repository mode", "")).lower()
    intake_contract, _intake_issues = derive_intake_foundation_contract(
        prd_text,
        repository_mode if repository_mode in PROJECT_MODES else None,
        grandfather_current_gate_a=True,
    )
    requirements_contract, requirement_issues = derive_requirements_contract(
        prd_text,
        clean_cell(document.get("Effective risk", "")) or None,
        intake_contract,
        required=True,
        grandfather_current_gate_a=True,
    )
    if requirement_issues or requirements_contract.status not in {
        "READY",
        "GRANDFATHERED",
    }:
        issue_text = (
            "; ".join(f"{code}: {message}" for code, message in requirement_issues)
            or f"status={requirements_contract.status}"
        )
        raise ValueError(
            "docs/project/PRD.md requirements contract is not current: " + issue_text
        )
    requirement_rules = task_requirement_rules(
        prd_text,
        requirements_contract,
        _schema_13_requirement_rows,
    )
    requirement_evidence, evidence_issues = task_requirement_evidence_dispositions(
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
    if evidence_issues:
        raise ValueError(
            "docs/project/VERIFY.md requirement evidence is invalid: "
            + "; ".join(evidence_issues)
        )
    return ApprovedTaskContract(
        frozenset(approved),
        enriched,
        approved_harness,
        delivery,
        requirement_rules,
        requirement_evidence,
    )


def validate_approved_property_evidence(
    verify_text: str,
    *,
    task_id: str,
    title: str,
    block: str,
    metadata: dict[str, str],
    duplicate_metadata: set[str],
    snapshot_fields: dict[str, str],
    approved_property_execution: dict[str, PropertyExecutionRow],
) -> None:
    """SAFETY: validate DONE property evidence without loading the doctor CLI."""

    property_ids = PROPERTY_ID.findall(clean_cell(metadata.get("Requirements", "")))
    if not property_ids:
        return
    rows = parse_property_test_evidence(verify_text, DELIVERY_VALIDATION_POLICY)
    completion_rows = parse_task_completion_evidence(verify_text)
    task = InspectedTask(task_id, title, block, metadata, duplicate_metadata)
    for property_id in property_ids:
        contract = approved_property_execution.get(property_id)
        if contract is None:
            raise ValueError(
                f"{task_id}: {property_id} is not approved by the PRD property execution contract"
            )
        if (
            contract.framework_selection is None
            or contract.framework_version_policy is None
        ):
            raise ValueError(
                f"{task_id}: {property_id} approved framework selection and version policy are unavailable"
            )
        expected = PropertyExecution(
            contract.property_id,
            contract.framework_tech_id,
            contract.exact_command,
            contract.run_target_time_bound,
            contract.seed_or_reproduction_format,
            contract.evidence_destination,
        )
        technology = TechnologyDecision(
            contract.framework_tech_id,
            "PROPERTY_TESTING",
            contract.framework_selection,
            contract.framework_version_policy,
            "REPOSITORY_FACT",
            snapshot_fields.get("Design revision", ""),
            "Validated by the current PRD",
            "NONE",
            "Observed property evidence",
        )
        validate_done_property_evidence(
            rows,
            task,
            snapshot_fields,
            expected,
            technology,
            completion_rows,
            DELIVERY_VALIDATION_POLICY,
        )


__all__ = (
    "IntakeFoundationContract",
    "DesignContract",
    "ApprovedDeliveryContract",
    "ApprovedSpikeContract",
    "ApprovedTaskContract",
    "AwsAuthorityPolicy",
    "AwsCoreEvidenceRow",
    "DELIVERY_VALIDATION_POLICY",
    "HarnessExecutionRow",
    "PropertyExecutionRow",
    "ProjectSnapshot",
    "RequirementsContract",
    "capture_project_snapshot",
    "aws_core_phase_evidence_issues",
    "derive_change_impact_contract",
    "derive_aws_core_observed_usage",
    "derive_aws_execution_projection",
    "derive_coverage_contract",
    "derive_design_contract",
    "derive_deployment_sequence_state",
    "derive_current_design_contract",
    "derive_approved_task_contract",
    "derive_task_requirement_coverage",
    "derive_intake_foundation_contract",
    "derive_req_aws_materiality",
    "derive_read_preflight_state",
    "derive_requirements_contract",
    "derive_teardown_sequence_state",
    "evaluate_adr_rationale",
    "parse_aws_core_evidence",
    "validate_approved_property_evidence",
    "validate_task_execution_basis",
)
