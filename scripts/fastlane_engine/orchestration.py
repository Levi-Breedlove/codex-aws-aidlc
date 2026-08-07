"""Fixed-order Fastlane Engine project orchestration.

Canonical inputs are one bounded Context observation and current project records.
Returns the stable version-2 report after invoking domain evaluators in deterministic
order. Read-only file access occurs only through Context; this module never writes,
executes AWS/GitHub actions, approves gates, or broadens authority.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Mapping

from .authority.aws import _read_preflight_receipt_authority
from .authority.closure import (
    derive_aws_execution_projection,
    derive_deployment_sequence_state,
    derive_read_preflight_state,
    derive_teardown_sequence_state,
)
from .aws import (
    AwsCoreEvidenceRow,
    aws_core_evidence_diagnostic_code,
    aws_core_phase_evidence_issues,
    aws_deployment_teardown_sequence_conflict,
    aws_lifecycle_intent_route_is_eligible,
    derive_aws_core_observed_usage,
    derive_aws_delivery_route,
    derive_aws_residual_disposition,
    derive_teardown_route,
    parse_aws_core_evidence,
)
from .core.contracts import table_after_heading
from .core.ids import clean_cell, explicit_value
from .project_delivery import (
    validate_aws_lifecycle_intent_record,
    validate_release_decision_record,
    validate_tasks,
)
from .deliver.models import TaskSummary
from .project_inspection import (
    MANIFEST_FILE,
    PRD_FILE,
    STATE_FILE,
    VERIFY_FILE,
    Context,
    capture_engine_snapshot,
    load_json_document,
    require_aws_core_phase_evidence,
    safe_read_text,
)
from .project_validation import (
    validate_manifest,
    validate_placeholders,
    validate_prd,
    validate_prompt_pack,
    validate_state_schema,
)
from .remediation import _owner_stage_for_aws_core_phases, _owner_stage_from_gates
from .report import build_report
from .routing import (
    derive_route,
    preserve_expired_authority_for_deployment_closure as _preserve_deployment_closure,
    preserve_expired_authority_for_teardown_closure as _preserve_teardown_closure,
    preserve_specialized_teardown_block as _preserve_teardown_block,
)

try:
    from fastlane_adr import derive_adr_rationale_from_snapshot
except ModuleNotFoundError:
    from scripts.fastlane_adr import derive_adr_rationale_from_snapshot


def _preserve_expired_authority_for_deployment_closure(
    ctx: Context,
    deployment_sequence: Mapping[str, Any],
    release_decision: str,
) -> None:
    _preserve_deployment_closure(ctx.diagnostics, deployment_sequence, release_decision)


def _preserve_expired_authority_for_teardown_closure(
    ctx: Context, teardown_sequence: Mapping[str, Any]
) -> None:
    """Keep only the local UNKNOWN closure after a valid teardown STARTED row."""

    _preserve_teardown_closure(ctx.diagnostics, teardown_sequence)


def _preserve_specialized_teardown_block(ctx: Context, lifecycle_state: str) -> bool:
    """Keep the teardown safety route only when every error belongs to it."""

    return _preserve_teardown_block(ctx.diagnostics, lifecycle_state)


def inspect_project(
    root: Path,
    *,
    template_source: bool = False,
    prior_remediation_fingerprint: str | None = None,
) -> dict[str, Any]:
    """SAFETY: observe once and compose domains in historical order."""

    root = root.resolve()
    snapshot = capture_engine_snapshot(root)
    ctx = Context(
        root=root,
        template_source=template_source,
        observed_snapshot=snapshot,
        prior_remediation_fingerprint=prior_remediation_fingerprint,
    )
    if not root.is_dir():
        ctx.error("PROJECT_ROOT", "Project root is not a directory", str(root))
        return build_report(ctx, "BLOCKED", "STOP", {}, TaskSummary())

    manifest = load_json_document(ctx, MANIFEST_FILE, "MANIFEST_PARSE")
    state = load_json_document(ctx, STATE_FILE, "STATE_PARSE")
    if manifest is None or state is None:
        return build_report(
            ctx,
            "BLOCKED",
            "STOP",
            {},
            TaskSummary(),
            manifest=manifest,
            state=state,
        )

    ctx.manifest_document = manifest
    ctx.bootstrap_state_document = state

    validate_manifest(ctx, manifest)
    state_sections_valid = validate_state_schema(ctx, state)
    validate_prompt_pack(ctx, manifest, state)
    if not state_sections_valid:
        validate_placeholders(ctx)
        return build_report(
            ctx,
            "BLOCKED",
            "STOP",
            {},
            TaskSummary(),
            manifest=manifest,
            state=state,
        )
    (
        prd_fields,
        envelope,
        selections,
        requirements_present,
        design_contract,
        coverage_contract,
        intake_contract,
        requirements_contract,
    ) = validate_prd(ctx, state)
    adr_rationale, adr_rationale_issues, adr_sources = (
        derive_adr_rationale_from_snapshot(
            snapshot,
            design_contract.to_dict(),
            ctx.texts.get(PRD_FILE, ""),
        )
    )
    for issue in adr_rationale_issues:
        ctx.error(
            str(issue.get("code", "ADR_RATIONALE_MALFORMED")),
            str(issue.get("message", "ADR rationale is invalid")),
            str(issue["path"]) if issue.get("path") else None,
        )
    for relative, expected_text in adr_sources.items():
        observed_text = safe_read_text(ctx, relative)
        if observed_text is not None and observed_text != expected_text:
            ctx.error(
                "ADR_RATIONALE_STALE",
                "ADR content changed during Engine inspection; rerun validation.",
                relative,
            )
    allow_legacy_design_discovery = bool(
        prd_fields.get("gate_b") == "APPROVED_FOR_CONSTRUCTION"
        and design_contract.architecture.schema_version < 4
    )
    aws_core_rows: dict[tuple[str, str, str], AwsCoreEvidenceRow] = {}
    blocking_aws_core_phases: set[str] = set()
    verify_text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    if verify_text is not None:
        try:
            active_scope = table_after_heading(verify_text, "## Active evidence scope")
        except ValueError:
            active_scope = {}
        verify_name = html.unescape(clean_cell(active_scope.get("Workload", "")))
        if verify_name and state.get("project", {}).get("name") != verify_name:
            ctx.error(
                "STATE_VERIFY_DRIFT",
                "project.name does not match the VERIFY Workload value",
                VERIFY_FILE,
            )
        try:
            aws_core_rows = parse_aws_core_evidence(
                verify_text,
                allow_legacy=allow_legacy_design_discovery,
            )
        except ValueError as exc:
            ctx.error("AWS_CORE_EVIDENCE_GENERATED_INVALID", str(exc), VERIFY_FILE)
    tasks = validate_tasks(
        ctx,
        state,
        prd_fields,
        envelope,
        requirements_contract,
        design_contract,
    )
    release_record = validate_release_decision_record(ctx)
    release_decision = release_record["release_state"]
    release_evidence_cutoff = release_record["active_evidence_cutoff"]
    aws_lifecycle_intent_record = validate_aws_lifecycle_intent_record(ctx)
    aws_lifecycle_intent = str(aws_lifecycle_intent_record["value"])
    validate_placeholders(ctx)

    gate_a = prd_fields.get("gate_a", "BLOCKED")
    gate_b = prd_fields.get("gate_b", "BLOCKED")
    prd_text = ctx.texts.get(PRD_FILE, "")
    gate_a_agent_ready = False
    gate_b_agent_ready = False
    try:
        gate_a_agent = table_after_heading(
            prd_text, "### Gate A — agent analysis record"
        )
        gate_b_agent = table_after_heading(
            prd_text, "## 27. Gate B agent review record"
        )
        gate_a_agent_ready = gate_a_agent.get("Agent recommendation") in {
            "READY_WITH_PROPOSED_ASSUMPTIONS",
            "READY_FOR_OWNER_APPROVAL",
        }
        gate_b_agent_ready = (
            gate_b_agent.get("Agent recommendation")
            == "READY_FOR_CONSTRUCTION_APPROVAL"
        )
    except ValueError:
        pass
    approved_tech_ids = {
        decision.decision_id for decision in design_contract.technology_decisions
    }
    req_materiality_raw = prd_fields.get("req_aws_materiality")
    req_materiality: Mapping[str, Any] = (
        req_materiality_raw
        if isinstance(req_materiality_raw, Mapping)
        else {
            "materiality": "OPTIONAL",
            "status": "UNASSESSED",
            "basis_ids": [],
            "discovery_ids": [],
            "unresolved_fact_ids": [],
        }
    )
    req_materiality_value = str(req_materiality.get("materiality", "OPTIONAL"))
    declared_req_discovery_ids = {
        str(item) for item in req_materiality.get("discovery_ids", [])
    }
    observed_req_discovery_ids = {
        discovery_id
        for row_phase, discovery_id, _capability in aws_core_rows
        if row_phase == "REQ-10"
    }
    req_aws_core_issues: list[str] = []
    if req_materiality_value == "REQUIRED" or declared_req_discovery_ids:
        req_aws_core_issues = aws_core_phase_evidence_issues(
            aws_core_rows,
            "REQ-10",
            expected_binding=prd_fields.get("requirements_revision"),
            expected_basis_ids={
                str(item) for item in req_materiality.get("basis_ids", [])
            },
        )
        if declared_req_discovery_ids != observed_req_discovery_ids:
            req_aws_core_issues.append(
                "REQ-10 AWS Core discovery IDs must exactly match the current "
                "Gate A materiality record"
            )
    req_aws_core_ready = not req_aws_core_issues
    if (
        gate_a_agent_ready
        or gate_a in {"PENDING_OWNER_APPROVAL", "APPROVED_FOR_DESIGN"}
    ) and req_materiality_value == "REQUIRED":
        if req_aws_core_issues:
            blocking_aws_core_phases.add("REQ-10")
        for issue in req_aws_core_issues:
            ctx.error(aws_core_evidence_diagnostic_code(issue), issue, VERIFY_FILE)
    design_aws_core_issues = aws_core_phase_evidence_issues(
        aws_core_rows,
        "DESIGN-10",
        expected_binding=prd_fields.get("design_revision"),
        expected_design_revision=prd_fields.get("design_revision"),
        approved_tech_ids=approved_tech_ids,
        allow_legacy_discovery=allow_legacy_design_discovery,
    )
    material_discovery_issues: list[str] = []
    if not allow_legacy_design_discovery:
        design_discovery_ids = {
            discovery_id
            for row_phase, discovery_id, _capability in aws_core_rows
            if row_phase == "DESIGN-10"
        }
        for evidence in design_contract.architecture.aws_evidence:
            if evidence.discovery_id not in design_discovery_ids:
                issue = (
                    f"{evidence.evidence_id} must cite a current DESIGN-10 "
                    f"AWS-DISC chain"
                )
                material_discovery_issues.append(issue)
                design_aws_core_issues.append(issue)
    design_aws_core_ready = not design_aws_core_issues
    design_evidence_enforced = gate_b_agent_ready or gate_b in {
        "PENDING_OWNER_APPROVAL",
        "APPROVED_FOR_CONSTRUCTION",
    }
    if design_evidence_enforced:
        if design_aws_core_issues:
            blocking_aws_core_phases.add("DESIGN-10")
        require_aws_core_phase_evidence(
            ctx,
            aws_core_rows,
            "DESIGN-10",
            expected_binding=prd_fields.get("design_revision"),
            expected_design_revision=prd_fields.get("design_revision"),
            approved_tech_ids=approved_tech_ids,
            allow_legacy_discovery=allow_legacy_design_discovery,
        )
        for issue in material_discovery_issues:
            ctx.error("AWS_CORE_EVIDENCE_REQUIRED", issue, PRD_FILE)
    lifecycle_state, next_prompt = derive_route(
        gate_a,
        gate_b,
        requirements_present,
        gate_b_agent_ready,
        tasks,
        envelope.get("Autonomous construction") == "ALLOWED",
        state.get("execution", {}).get("mode", "NONE"),
        release_decision,
    )
    if (
        gate_a == "BLOCKED"
        and not ctx.has_errors
        and any(value is None for value in selections.values())
    ):
        lifecycle_state, next_prompt = "INTAKE_REQUIRED", "INTAKE-10"
    artifact_binding = ""
    aws_10_issues = ["AWS-10 active artifact binding is unresolved"]
    if verify_text is not None:
        try:
            active_scope = table_after_heading(verify_text, "## Active evidence scope")
            artifact_binding = clean_cell(
                active_scope.get("Commit, tag, or image digest", "")
            )
        except ValueError:
            artifact_binding = ""
        if explicit_value(artifact_binding, allow_none=False):
            aws_10_issues = aws_core_phase_evidence_issues(
                aws_core_rows,
                "AWS-10",
                expected_binding=artifact_binding,
                expected_design_revision=prd_fields.get("design_revision"),
                approved_tech_ids={
                    decision.decision_id
                    for decision in design_contract.technology_decisions
                },
            )
    aws_guidance_ready = not aws_10_issues
    construction_authorization = (
        str(prd_fields.get("construction_authorization", "NONE"))
        if gate_b == "APPROVED_FOR_CONSTRUCTION"
        else "NONE"
    )
    read_authority = (
        _read_preflight_receipt_authority(
            verify_text or "",
            construction_authorization,
            str(state.get("project", {}).get("cost_posture", "")),
            envelope,
            artifact_binding,
            observed_at=ctx.observed_at,
        )
        if construction_authorization != "NONE"
        else None
    )
    preflight = derive_read_preflight_state(
        verify_text or "",
        read_authority,
        requirements_revision=str(prd_fields.get("requirements_revision", "")),
        design_revision=str(prd_fields.get("design_revision", "")),
        construction_authorization=construction_authorization,
        artifact_binding=artifact_binding,
        observed_at=ctx.observed_at,
    )
    deployment_sequence = derive_deployment_sequence_state(
        verify_text or "",
        read_authority,
        requirements_revision=str(prd_fields.get("requirements_revision", "")),
        design_revision=str(prd_fields.get("design_revision", "")),
        construction_authorization=construction_authorization,
        envelope=envelope,
        lane=selections.get("aws_lane"),
        artifact_binding=artifact_binding,
        release_evidence_cutoff=release_evidence_cutoff,
        release_state=release_decision,
        gate_b_authority_source=str(prd_fields.get("gate_b_authorization_source", "")),
        gate_b_authorized_at=str(prd_fields.get("gate_b_authorized_at", "")),
        cost_posture=str(state.get("project", {}).get("cost_posture", "")),
        restricted_closure=(
            gate_b != "APPROVED_FOR_CONSTRUCTION"
            or any(item.code == "GATE_B_AUTHORITY_EXPIRED" for item in ctx.diagnostics)
        ),
        observed_at=ctx.observed_at,
    )
    _preserve_expired_authority_for_deployment_closure(
        ctx, deployment_sequence, release_decision
    )
    teardown_sequence = derive_teardown_sequence_state(
        verify_text or "",
        read_authority,
        requirements_revision=str(prd_fields.get("requirements_revision", "")),
        design_revision=str(prd_fields.get("design_revision", "")),
        construction_authorization=construction_authorization,
        envelope=envelope,
        restricted_closure=(
            gate_b != "APPROVED_FOR_CONSTRUCTION"
            or any(item.code == "GATE_B_AUTHORITY_EXPIRED" for item in ctx.diagnostics)
        ),
        cost_posture=str(state.get("project", {}).get("cost_posture", "")),
        active_artifact=artifact_binding,
        observed_at=ctx.observed_at,
    )
    _preserve_expired_authority_for_teardown_closure(ctx, teardown_sequence)
    aws_sequence_conflict = aws_deployment_teardown_sequence_conflict(
        deployment_sequence, teardown_sequence
    )
    if aws_sequence_conflict:
        ctx.error(
            "AWS_DEPLOYMENT_TEARDOWN_CONFLICT",
            "Open deployment and teardown journal epochs cannot coexist; close one sequence before continuing",
            VERIFY_FILE,
        )
    aws_execution = derive_aws_execution_projection(
        req_materiality,
        release_decision=release_decision,
        guidance_ready=aws_guidance_ready,
        read_authority=read_authority,
        preflight=preflight,
        lane=selections.get("aws_lane"),
    )
    if deployment_sequence.get("status") not in {"NOT_ACTIVE", "CONSUMED"}:
        aws_execution = {
            **aws_execution,
            "active": False,
            "progress_state": "NOT_ACTIVE",
        }
    elif (
        deployment_sequence.get("status") == "CONSUMED"
        and release_decision == "READY_TO_DEPLOY"
        and deployment_sequence.get("current_mutation_authority_status") == "CONSUMED"
    ):
        aws_execution = {
            **aws_execution,
            "progress_state": "WAITING_AWS_MUTATION_AUTH",
        }
        if selections.get("aws_lane") == "fast-dev":
            ctx.error(
                "AWS_DEPLOYMENT_AUTHORITY_REPLAY",
                "A fast-dev retry requires a freshly approved Gate B construction authorization",
                PRD_FILE,
            )
    aws_execution_planning_ready = preflight.get("status") == "READY"
    aws_delivery_route = derive_aws_delivery_route(
        release_decision,
        aws_execution,
        deployment_sequence,
        selections.get("aws_lane"),
        release_evidence_cutoff,
    )
    residual_disposition = derive_aws_residual_disposition(
        aws_lifecycle_intent_record, teardown_sequence
    )
    if residual_disposition.get("status") == "INVALID":
        ctx.error(
            "AWS_RESIDUAL_DISPOSITION_INVALID",
            "; ".join(str(item) for item in residual_disposition.get("issues", [])),
            VERIFY_FILE,
        )
    teardown_recovery_route = derive_teardown_route(
        aws_lifecycle_intent, teardown_sequence, residual_disposition
    )
    teardown_status = clean_cell(teardown_sequence.get("status", ""))
    if aws_sequence_conflict:
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
    elif (
        not ctx.has_errors
        and teardown_status in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}
        and not teardown_sequence.get("issues")
        and teardown_recovery_route is not None
    ):
        lifecycle_state, next_prompt = teardown_recovery_route
    elif (
        teardown_status in {"ACTION_TERMINAL_REQUIRED", "POST_ACTION_REVIEW", "BLOCKED"}
        and not teardown_sequence.get("issues")
        and teardown_recovery_route is not None
    ):
        lifecycle_state, next_prompt = teardown_recovery_route
    elif (
        not ctx.has_errors
        and aws_lifecycle_intent_route_is_eligible(
            aws_lifecycle_intent,
            lifecycle_state,
            release_decision,
            tasks,
            deployment_sequence,
            teardown_sequence,
        )
        and teardown_recovery_route is not None
    ):
        lifecycle_state, next_prompt = teardown_recovery_route
    elif aws_delivery_route is not None and not ctx.has_errors:
        lifecycle_state, next_prompt = aws_delivery_route
    if next_prompt == "AWS-10" and not aws_guidance_ready:
        ctx.warning(
            "AWS_CORE_AWS10_EVIDENCE_REQUIRED",
            "AWS-10 must record a fresh linked search_documentation then "
            "retrieve_skill discovery chain bound to the current artifact before "
            "AWS execution planning: " + "; ".join(aws_10_issues),
            VERIFY_FILE,
        )
    if preflight.get("issues"):
        ctx.error(
            "AWS_PREFLIGHT_EVIDENCE_INVALID",
            "; ".join(str(item) for item in preflight["issues"]),
            VERIFY_FILE,
        )
    # A stale attempted basis never authorizes new mutation, but read-only
    # reconciliation still proceeds so the observed action can be closed.
    if deployment_sequence.get("issues"):
        ctx.error(
            "AWS_DEPLOYMENT_EVIDENCE_INVALID",
            "; ".join(str(item) for item in deployment_sequence["issues"]),
            VERIFY_FILE,
        )
    if teardown_sequence.get("issues"):
        ctx.error(
            "AWS_TEARDOWN_EVIDENCE_INVALID",
            "; ".join(str(item) for item in teardown_sequence["issues"]),
            VERIFY_FILE,
        )
    aws_core_usage = {
        "REQ-10": derive_aws_core_observed_usage(
            aws_core_rows,
            "REQ-10",
            issues=req_aws_core_issues,
        ),
        "DESIGN-10": derive_aws_core_observed_usage(
            aws_core_rows,
            "DESIGN-10",
            issues=design_aws_core_issues,
        ),
        "AWS-10": derive_aws_core_observed_usage(
            aws_core_rows,
            "AWS-10",
            issues=aws_10_issues,
        ),
    }
    specialized_teardown_block = _preserve_specialized_teardown_block(
        ctx, lifecycle_state
    )
    if ctx.has_errors and not specialized_teardown_block:
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
    owner_stage_hint = _owner_stage_for_aws_core_phases(
        blocking_aws_core_phases,
        _owner_stage_from_gates(gate_a, gate_b),
    )
    if any(
        item.code == "APPLICATION_SOURCE_DISPOSITION_CONFLICT"
        for item in ctx.diagnostics
    ):
        owner_stage_hint = "DEFINE"
    return build_report(
        ctx,
        lifecycle_state,
        next_prompt,
        prd_fields,
        tasks,
        manifest=manifest,
        state=state,
        release_decision=release_decision,
        envelope=envelope,
        aws_execution_planning_ready=aws_execution_planning_ready,
        design_aws_core_ready=design_aws_core_ready,
        design_contract=design_contract,
        adr_rationale=adr_rationale,
        intake_contract=intake_contract,
        coverage_contract=coverage_contract,
        aws_execution=aws_execution,
        requirements_contract=requirements_contract,
        aws_core_usage=aws_core_usage,
        owner_stage_hint=owner_stage_hint,
        active_artifact=artifact_binding,
        deployment_sequence=deployment_sequence,
        teardown_sequence=teardown_sequence,
        req_aws_core_materiality=req_materiality_value,
        req_aws_core_ready=req_aws_core_ready,
        aws_lifecycle_intent_record=aws_lifecycle_intent_record,
        release_evidence_cutoff=release_evidence_cutoff,
    )
