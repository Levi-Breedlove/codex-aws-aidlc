"""Supported read-only entry points for the Fastlane Engine foundation.

Inputs are repository-relative paths and caller-supplied observation policy.
Outputs are immutable snapshots, Define, Design, Delivery, or AWS projections.
Snapshot capture may read bounded regular files; domain evaluators consume caller-supplied text and
perform no I/O. The API never writes, runs Git, invokes AWS, approves a gate, or
grants authority.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .aws import (
    AwsAuthorityPolicy,
    AwsCoreEvidenceRow,
    aws_core_phase_evidence_issues,
    derive_aws_core_observed_usage,
    derive_aws_execution_projection as _derive_aws_execution_projection_core,
    derive_deployment_sequence_state as _derive_deployment_sequence_state_core,
    derive_read_preflight_state as _derive_read_preflight_state_core,
    derive_teardown_sequence_state as _derive_teardown_sequence_state_core,
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
    valid_property_execution_command,
)
from .define.intake import PROJECT_MODES
from .define.requirements import _schema_13_requirement_rows, _state_trigger_map
from .define.requirements import authoritative_requirement_ids
from .deliver import (
    ApprovedDeliveryContract,
    ApprovedSpikeContract,
    ApprovedTaskContract,
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
from .evaluation import EngineEvaluation

if TYPE_CHECKING:
    from .project_delivery import DELIVERY_VALIDATION_POLICY


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


def _compatibility_aws_policy(
    verify_text: str,
    envelope: Mapping[str, str] | None,
    cost_posture: str,
    active_artifact: str,
    observed_at: datetime | None,
):
    """COMPATIBILITY: adapt legacy raw inputs at the public API boundary."""

    from .authority.aws import build_aws_authority_policy
    from .authority.models import AuthorityEvaluationInput
    from .orchestration import normalize_gate_b_authority_bounds
    from .deliver import parse_verification_matrix

    evaluation_time = observed_at or datetime.now(timezone.utc)
    return build_aws_authority_policy(
        AuthorityEvaluationInput(
            has_errors=False,
            observed_at=evaluation_time,
            verify_text=verify_text,
        ),
        normalize_gate_b_authority_bounds(
            envelope or {},
            cost_posture=cost_posture,
            active_artifact=active_artifact,
        ),
        parse_verification_matrix=parse_verification_matrix,
    )


def derive_deployment_sequence_state(
    verify_text: str,
    read_authority: Mapping[str, Any] | None,
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    envelope: Mapping[str, str],
    lane: str | None,
    artifact_binding: str,
    release_evidence_cutoff: str = "NONE",
    release_state: str = "READY_TO_DEPLOY",
    gate_b_authority_source: str = "",
    gate_b_authorized_at: str = "",
    cost_posture: str = "",
    restricted_closure: bool = False,
    observed_at: datetime | None = None,
    policy: AwsAuthorityPolicy | None = None,
) -> dict[str, Any]:
    """COMPATIBILITY: evaluate deployment through the pure AWS domain."""

    return _derive_deployment_sequence_state_core(
        verify_text,
        read_authority,
        policy=policy
        or _compatibility_aws_policy(
            verify_text, envelope, cost_posture, artifact_binding, observed_at
        ),
        requirements_revision=requirements_revision,
        design_revision=design_revision,
        construction_authorization=construction_authorization,
        envelope=envelope,
        lane=lane,
        artifact_binding=artifact_binding,
        release_evidence_cutoff=release_evidence_cutoff,
        release_state=release_state,
        gate_b_authority_source=gate_b_authority_source,
        gate_b_authorized_at=gate_b_authorized_at,
        cost_posture=cost_posture,
        restricted_closure=restricted_closure,
    )


def derive_teardown_sequence_state(
    verify_text: str,
    read_authority: Mapping[str, Any] | None,
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    envelope: Mapping[str, str],
    restricted_closure: bool = False,
    cost_posture: str = "",
    active_artifact: str = "",
    observed_at: datetime | None = None,
    policy: AwsAuthorityPolicy | None = None,
) -> dict[str, Any]:
    """COMPATIBILITY: evaluate teardown through the pure AWS domain."""

    return _derive_teardown_sequence_state_core(
        verify_text,
        read_authority,
        policy=policy
        or _compatibility_aws_policy(
            verify_text, envelope, cost_posture, active_artifact, observed_at
        ),
        requirements_revision=requirements_revision,
        design_revision=design_revision,
        construction_authorization=construction_authorization,
        envelope=envelope,
        restricted_closure=restricted_closure,
        cost_posture=cost_posture,
        active_artifact=active_artifact,
    )


def derive_read_preflight_state(
    verify_text: str,
    authority: Mapping[str, Any] | None,
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    artifact_binding: str,
    observed_at: datetime | None = None,
    policy: AwsAuthorityPolicy | None = None,
) -> dict[str, Any]:
    """COMPATIBILITY: evaluate read preflight through the pure AWS domain."""

    return _derive_read_preflight_state_core(
        verify_text,
        authority,
        policy=policy
        or _compatibility_aws_policy(
            verify_text, {}, "", artifact_binding, observed_at
        ),
        requirements_revision=requirements_revision,
        design_revision=design_revision,
        construction_authorization=construction_authorization,
        artifact_binding=artifact_binding,
    )


def derive_aws_execution_projection(
    materiality: Mapping[str, Any],
    *,
    release_decision: str,
    guidance_ready: bool,
    read_authority: Mapping[str, Any] | None,
    preflight: Mapping[str, Any],
    lane: str | None = None,
) -> dict[str, Any]:
    """COMPATIBILITY: expose the stable aggregate AWS projection."""

    return _derive_aws_execution_projection_core(
        materiality,
        release_decision=release_decision,
        guidance_ready=guidance_ready,
        read_authority=read_authority,
        preflight=preflight,
        lane=lane,
    )


def derive_write_authority(
    ctx: Any,
    envelope: Mapping[str, str],
    tasks: Any,
    construction_authorization: str,
) -> dict[str, Any]:
    """COMPATIBILITY: normalize Design and Deliver facts before Authority."""

    from .authority.write import derive_write_authority as _derive_write_authority
    from .composition import _normalize_construction_write_input

    return _derive_write_authority(
        _normalize_construction_write_input(ctx, envelope, tasks),
        construction_authorization,
    )


def _lifecycle_intent_write_input(
    ctx: Any,
    tasks: Any,
    release_decision: str,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
    external_authority: Mapping[str, Any],
    lifecycle_intent: Mapping[str, Any] | None,
):
    """Translate sibling-domain results into one Authority-owned input."""

    from .authority.models import LifecycleIntentWriteInput
    from .aws import release_lifecycle_intent_boundary_is_settled

    return LifecycleIntentWriteInput(
        has_errors=ctx.has_errors,
        tasks_terminal=tasks.terminal,
        release_decision=release_decision,
        deployment_status=clean_cell(deployment_sequence.get("status", "")),
        deployment_boundary_settled=release_lifecycle_intent_boundary_is_settled(
            release_decision, deployment_sequence
        ),
        teardown_status=clean_cell(teardown_sequence.get("status", "")),
        teardown_has_issues=bool(teardown_sequence.get("issues")),
        external_authority_current=(
            clean_cell(external_authority.get("validity", "")) == "CURRENT"
        ),
        intent_value=clean_cell((lifecycle_intent or {}).get("value", "NONE")),
    )


def lifecycle_intent_record_boundary_is_settled(
    tasks: Any,
    release_decision: str,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> bool:
    """COMPATIBILITY: preserve the historical normalized boundary query."""

    from .authority.write import (
        lifecycle_intent_record_boundary_is_settled as _boundary_is_settled,
    )

    class _NoErrors:
        has_errors = False

    return _boundary_is_settled(
        _lifecycle_intent_write_input(
            _NoErrors(),
            tasks,
            release_decision,
            deployment_sequence,
            teardown_sequence,
            {},
            None,
        )
    )


def derive_aws_lifecycle_intent_write_authority(
    ctx: Any,
    tasks: Any,
    release_decision: str,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
    external_authority: Mapping[str, Any],
    *,
    lifecycle_intent: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """COMPATIBILITY: normalize lifecycle facts before Authority evaluation."""

    from .authority.write import (
        derive_aws_lifecycle_intent_write_authority as _derive_write_authority,
    )

    return _derive_write_authority(
        _lifecycle_intent_write_input(
            ctx,
            tasks,
            release_decision,
            deployment_sequence,
            teardown_sequence,
            external_authority,
            lifecycle_intent,
        )
    )


def current_gate_receipt_contract(
    root: Path,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """COMPATIBILITY: observe and normalize one pending gate before Authority."""

    from .authority.models import PendingGateReceiptInput
    from .authority.receipts import (
        current_gate_receipt_contract as _current_gate_receipt_contract,
    )
    from .core.contracts import table_after_heading
    from .core.ids import parse_exact_id_list
    from .project_inspection import (
        AUTH_ID,
        DES_ID,
        REQ_ID,
        bounded_prd_snapshot,
        parse_cost_posture,
    )

    lifecycle_state = str(report.get("lifecycle_state", ""))
    next_prompt = str(report.get("next_prompt", ""))
    if lifecycle_state == "WAITING_GATE_A" and next_prompt == "INTAKE-20":
        gate = "GATE_A"
        owner_action_kind = "APPROVE_GATE_A"
    elif lifecycle_state == "WAITING_GATE_B" and next_prompt == "DESIGN-20":
        gate = "GATE_B"
        owner_action_kind = "APPROVE_GATE_B"
    else:
        raise ValueError("The project is not waiting for a Gate A or Gate B receipt")
    try:
        basis = report.get("basis")
        if not isinstance(basis, Mapping):
            raise ValueError("Current gate basis is missing")
        text, _digest = bounded_prd_snapshot(
            root, clean_cell(basis.get("prd_snapshot_sha256", ""))
        )
        requirements_revision = clean_cell(basis.get("requirements_revision", ""))
        if REQ_ID.fullmatch(requirements_revision) is None:
            raise ValueError("Current requirements revision is invalid")
        if gate == "GATE_A":
            gate_a_agent = table_after_heading(
                text, "### Gate A — agent analysis record"
            )
            gate_a_card = table_after_heading(text, "### Gate A — readiness card")
            assumption_ids = tuple(
                parse_exact_id_list(
                    gate_a_agent.get("Proposed assumption IDs required to proceed", ""),
                    re.compile(r"ASM-\d+"),
                    "Gate A proposed assumptions",
                )
            )
            cost_posture = clean_cell(gate_a_card.get("Cost posture", ""))
            parse_cost_posture(cost_posture)
            normalized = PendingGateReceiptInput(
                gate=gate,
                lifecycle_state=lifecycle_state,
                next_prompt=next_prompt,
                owner_action_kind=owner_action_kind,
                requirements_revision=requirements_revision,
                cost_posture=cost_posture,
                accepted_assumptions=assumption_ids,
            )
        else:
            design_revision = clean_cell(basis.get("design_revision", ""))
            authorization_id = clean_cell(basis.get("construction_authorization", ""))
            if DES_ID.fullmatch(design_revision) is None:
                raise ValueError("Current design revision is invalid")
            if AUTH_ID.fullmatch(authorization_id) is None:
                raise ValueError("Current construction authorization is invalid")
            normalized = PendingGateReceiptInput(
                gate=gate,
                lifecycle_state=lifecycle_state,
                next_prompt=next_prompt,
                owner_action_kind=owner_action_kind,
                requirements_revision=requirements_revision,
                design_revision=design_revision,
                construction_authorization=authorization_id,
                construction_envelope_sha256=canonical_envelope_sha256(text),
            )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("The current pending gate contract is invalid") from exc
    return _current_gate_receipt_contract(normalized)


def _read_preflight_receipt_authority(
    verify_text: str,
    construction_authorization: str,
    cost_posture: str,
    envelope: Mapping[str, str],
    active_artifact: str,
    *,
    observed_at: datetime | None = None,
    allow_one_operation: bool = True,
    allow_expired: bool = False,
) -> dict[str, Any] | None:
    """COMPATIBILITY: normalize one legacy read receipt request."""

    from .authority.aws import (
        _read_preflight_receipt_authority as _derive_read_authority,
    )
    from .authority.models import AuthorityEvaluationInput
    from .orchestration import normalize_gate_b_authority_bounds

    return _derive_read_authority(
        AuthorityEvaluationInput(
            has_errors=False,
            observed_at=observed_at or datetime.now(timezone.utc),
            verify_text=verify_text,
        ),
        normalize_gate_b_authority_bounds(
            envelope,
            cost_posture=cost_posture,
            active_artifact=active_artifact,
        ),
        construction_authorization,
        allow_one_operation=allow_one_operation,
        allow_expired=allow_expired,
    )


def _receipt_external_authority(
    verify_text: str,
    action: str,
    construction_authorization: str,
    *,
    observed_at: datetime | None = None,
    envelope: Mapping[str, str],
    cost_posture: str,
    active_artifact: str,
    preflight: Mapping[str, Any] | None = None,
    teardown_review: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """COMPATIBILITY: normalize one legacy mutation receipt request."""

    from .authority.aws import _receipt_external_authority as _derive_authority
    from .authority.models import AuthorityEvaluationInput
    from .orchestration import normalize_gate_b_authority_bounds

    return _derive_authority(
        AuthorityEvaluationInput(
            has_errors=False,
            observed_at=observed_at or datetime.now(timezone.utc),
            verify_text=verify_text,
        ),
        normalize_gate_b_authority_bounds(
            envelope,
            cost_posture=cost_posture,
            active_artifact=active_artifact,
        ),
        action,
        construction_authorization,
        preflight=preflight,
        teardown_review=teardown_review,
    )


def derive_external_authority(
    ctx: Any,
    envelope: Mapping[str, str],
    lane: str | None,
    construction_authorization: str,
    *,
    cost_posture: str = "",
    aws_progress_state: str | None = None,
    active_artifact: str = "",
    preflight: Mapping[str, Any] | None = None,
    aws_action_phase: str | None = None,
    teardown_review: Mapping[str, Any] | None = None,
    deployment_sequence: Mapping[str, Any] | None = None,
    read_authority_deriver: Callable[..., dict[str, Any] | None] | None = None,
    action_authority_deriver: Callable[..., dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """COMPATIBILITY: adapt legacy project inputs to normalized Authority facts."""

    from .authority.aws import derive_external_authority as _derive_authority
    from .authority.models import AuthorityEvaluationInput
    from .orchestration import normalize_gate_b_authority_bounds

    authority_input = AuthorityEvaluationInput(
        has_errors=ctx.has_errors,
        observed_at=ctx.observed_at,
        verify_text=ctx.texts.get("docs/project/VERIFY.md", ""),
    )
    bounds = normalize_gate_b_authority_bounds(
        envelope,
        cost_posture=cost_posture,
        active_artifact=active_artifact,
    )
    if (read_authority_deriver or action_authority_deriver) and not bounds.valid:
        # COMPATIBILITY: historical monkeypatch seams intentionally supplied the
        # receipt decision while using only the phase boundary under test.
        from dataclasses import replace

        bounds = replace(
            bounds,
            valid=True,
            boundary=clean_cell(envelope.get("AWS boundary", "NONE")),
        )

    normalized_read_deriver = None
    if read_authority_deriver is not None:

        def normalized_read_deriver(
            _authority_input: Any,
            _bounds: Any,
            authorization: str,
            **kwargs: Any,
        ) -> dict[str, Any] | None:
            return read_authority_deriver(
                authority_input.verify_text,
                authorization,
                cost_posture,
                envelope,
                active_artifact,
                **kwargs,
            )

    normalized_action_deriver = None
    if action_authority_deriver is not None:

        def normalized_action_deriver(
            _authority_input: Any,
            _bounds: Any,
            action: str,
            authorization: str,
            **kwargs: Any,
        ) -> dict[str, Any] | None:
            return action_authority_deriver(
                authority_input.verify_text,
                action,
                authorization,
                envelope=envelope,
                cost_posture=cost_posture,
                active_artifact=active_artifact,
                **kwargs,
            )

    return _derive_authority(
        authority_input,
        bounds,
        lane,
        construction_authorization,
        aws_progress_state=aws_progress_state,
        preflight=preflight,
        aws_action_phase=aws_action_phase,
        teardown_review=teardown_review,
        deployment_sequence=deployment_sequence,
        read_authority_deriver=normalized_read_deriver,
        action_authority_deriver=normalized_action_deriver,
    )


def _delivery_validation_policy():
    """Return the composed Delivery policy without an import-time API cycle."""

    from .project_delivery import DELIVERY_VALIDATION_POLICY

    return DELIVERY_VALIDATION_POLICY


def __getattr__(name: str):
    """COMPATIBILITY: lazily retain the former public policy export."""

    if name == "DELIVERY_VALIDATION_POLICY":
        return _delivery_validation_policy()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def evaluate_project(
    root: Path,
    *,
    template_source: bool = False,
    prior_remediation_fingerprint: str | None = None,
) -> EngineEvaluation:
    """Return one immutable whole-project evaluation without serializing it."""

    from .orchestration import evaluate_project as _evaluate_project

    return _evaluate_project(
        root,
        template_source=template_source,
        prior_remediation_fingerprint=prior_remediation_fingerprint,
    )


def inspect_project(
    root: Path,
    *,
    template_source: bool = False,
    prior_remediation_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Return the stable schema-2 report through the modular orchestrator.

    The import is intentionally lazy so Delivery validation can consume this
    public API without creating a cycle back through whole-project routing.
    """

    from .orchestration import inspect_project as _inspect_project

    return _inspect_project(
        root,
        template_source=template_source,
        prior_remediation_fingerprint=prior_remediation_fingerprint,
    )


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
    policy = _delivery_validation_policy()
    rows = parse_property_test_evidence(verify_text, policy)
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
            policy,
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
    "EngineEvaluation",
    "RequirementsContract",
    "capture_project_snapshot",
    "evaluate_project",
    "inspect_project",
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
