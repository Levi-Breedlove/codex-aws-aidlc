"""Fixed-order Fastlane Engine project orchestration.

Canonical inputs are one bounded Context observation and current project records.
Returns the stable version-2 report after invoking domain evaluators in deterministic
order. Read-only file access occurs only through Context; this module never writes,
executes AWS/GitHub actions, approves gates, or broadens authority.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .authority.aws import (
    _read_preflight_receipt_authority,
    build_aws_authority_policy,
)
from .authority.models import (
    AuthorityEvaluationInput,
    ConstructionWriteInput,
    GateBAuthorityBounds,
)
from .aws import (
    AwsCoreEvidenceRow,
    aws_core_evidence_diagnostic_code,
    aws_core_phase_evidence_issues,
    aws_deployment_teardown_sequence_conflict,
    aws_lifecycle_intent_route_is_eligible,
    derive_aws_core_observed_usage,
    derive_aws_delivery_route,
    derive_aws_execution_projection,
    derive_aws_residual_disposition,
    derive_deployment_sequence_state,
    derive_read_preflight_state,
    derive_teardown_route,
    derive_teardown_sequence_state,
    parse_aws_core_evidence,
)
from .core.contracts import table_after_heading
from .core.ids import clean_cell, explicit_value, iso_datetime
from .composition import build_evaluation
from .design import (
    AWS_DERIVED_ARTIFACT,
    AWS_EXACT_ARTIFACT,
    parse_aws_environment,
    parse_envelope_paths,
    validate_aws_artifact,
)
from .evaluation import EngineEvaluation
from .project_delivery import (
    validate_aws_lifecycle_intent_record,
    validate_release_decision_record,
    validate_tasks,
)
from .deliver import parse_verification_matrix
from .deliver.models import TaskSummary
from .project_inspection import (
    AWS_COST_CEILING,
    MANIFEST_FILE,
    PRD_FILE,
    STATE_FILE,
    VERIFY_FILE,
    Context,
    capture_engine_snapshot,
    load_json_document,
    parse_cost_posture,
    parse_positive_cost,
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
from .report import serialize_evaluation
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


def _normalized_envelope_scalar(
    envelope: Mapping[str, str], field: str, label: str
) -> str | None:
    value = clean_cell(envelope.get(field, ""))
    prefix = label + ":"
    if not value.startswith(prefix):
        return None
    candidate = clean_cell(value[len(prefix) :])
    return candidate if explicit_value(candidate, allow_none=False) else None


def _normalized_envelope_values(
    envelope: Mapping[str, str], field: str, label: str
) -> tuple[str, ...]:
    value = _normalized_envelope_scalar(envelope, field, label)
    if value is None:
        return ()
    values = tuple(item.strip() for item in re.split(r"[,;]", value) if item.strip())
    if (
        not values
        or len(values) != len(set(values))
        or any("*" in item for item in values)
    ):
        return ()
    return values


def _normalized_authority_expiry(value: str) -> datetime | None:
    match = re.fullmatch(
        r"Expires at (?P<timestamp>[^\s;]+); earlier completion: (?P<condition>[^\r\n]+)",
        clean_cell(value),
    )
    if match is None or not explicit_value(match.group("condition"), allow_none=False):
        return None
    return iso_datetime(match.group("timestamp"))


def normalize_gate_b_authority_bounds(
    envelope: Mapping[str, str],
    *,
    cost_posture: str,
    active_artifact: str,
) -> GateBAuthorityBounds:
    """SAFETY: narrow validated Design fields into immutable Authority facts."""

    boundary = clean_cell(envelope.get("AWS boundary", "NONE"))
    account = _normalized_envelope_scalar(envelope, "AWS account", "ACCOUNT")
    region = _normalized_envelope_scalar(envelope, "AWS Region", "REGION")
    role = _normalized_envelope_scalar(envelope, "AWS role or profile", "ROLE")
    resources = _normalized_envelope_values(
        envelope, "AWS resource allowlist", "RESOURCES"
    )
    operations = _normalized_envelope_values(
        envelope, "AWS allowed operations", "OPERATIONS"
    )
    try:
        environment, _environment_class = parse_aws_environment(
            envelope.get("AWS environment", "")
        )
    except ValueError:
        environment = None
    approved_artifact = clean_cell(
        envelope.get("AWS artifact authorization and provenance", "")
    )
    normalized_artifact = clean_cell(active_artifact)
    artifact_authorized = False
    if re.fullmatch(r"sha256:[0-9a-f]{64}", normalized_artifact):
        if approved_artifact.startswith("NOT_APPLICABLE"):
            artifact_authorized = boundary == "READ_ONLY"
        elif AWS_EXACT_ARTIFACT.fullmatch(approved_artifact):
            artifact_authorized = normalized_artifact == approved_artifact.removeprefix(
                "EXACT_DIGEST: "
            )
        else:
            try:
                validate_aws_artifact(
                    approved_artifact,
                    clean_cell(envelope.get("Authorized baseline commit", "")),
                )
            except ValueError:
                pass
            else:
                artifact_authorized = bool(
                    AWS_DERIVED_ARTIFACT.fullmatch(approved_artifact)
                )
    try:
        owner_cost_cap = parse_cost_posture(cost_posture)
    except ValueError:
        owner_cost_cap = None
        cost_posture_valid = False
    else:
        cost_posture_valid = True
    raw_cost_ceiling = clean_cell(envelope.get("AWS cost ceiling", "NONE"))
    try:
        aws_cost_ceiling = parse_positive_cost(
            raw_cost_ceiling, AWS_COST_CEILING, "AWS cost ceiling"
        )
    except ValueError:
        aws_cost_ceiling = None
    rollback_value = clean_cell(envelope.get("AWS rollback boundary", ""))
    rollback = (
        clean_cell(rollback_value.removeprefix("ROLLBACK:"))
        if rollback_value.startswith("ROLLBACK:")
        else None
    )
    authorization_expiry = _normalized_authority_expiry(
        envelope.get("Authorization expiry or completion condition", "")
    )
    aws_validity = clean_cell(envelope.get("AWS authorization validity", ""))
    aws_authorization_expiry = (
        None
        if aws_validity.startswith("NOT_APPLICABLE")
        else _normalized_authority_expiry(aws_validity)
    )
    valid = bool(
        boundary in {"READ_ONLY", "MUTATE_LISTED_RESOURCES"}
        and account
        and region
        and environment
        and role
        and resources
        and operations
        and artifact_authorized
        and cost_posture_valid
        and authorization_expiry is not None
        and (
            boundary == "READ_ONLY"
            or (
                aws_cost_ceiling is not None
                and rollback
                and aws_authorization_expiry is not None
            )
        )
    )
    return GateBAuthorityBounds(
        valid=valid,
        boundary=boundary,
        account=account,
        region=region,
        environment=environment,
        role_or_profile=role,
        resources=resources,
        operations=operations,
        active_artifact=normalized_artifact,
        artifact_authorized=artifact_authorized,
        cost_posture=clean_cell(cost_posture),
        owner_cost_cap=owner_cost_cap,
        aws_cost_ceiling=aws_cost_ceiling,
        aws_cost_ceiling_raw=raw_cost_ceiling,
        rollback_boundary=rollback,
        authorization_expires_at=authorization_expiry,
        aws_authorization_expires_at=aws_authorization_expiry,
        stack_or_application=clean_cell(
            envelope.get("AWS stack or application", "NONE")
        ),
    )


def _normalize_construction_write_input(
    ctx: Context,
    envelope: Mapping[str, str],
    tasks: TaskSummary,
) -> ConstructionWriteInput:
    """SAFETY: narrow Design and Deliver results into immutable write facts."""

    try:
        roots = tuple(
            parse_envelope_paths(
                envelope.get("Allowed repository write set", ""),
                "Allowed repository write set",
                allow_none=False,
            )
        )
        exclusions = tuple(
            parse_envelope_paths(
                envelope.get("Excluded or owner-only write set", ""),
                "Excluded or owner-only write set",
                allow_none=True,
            )
        )
        protected = tuple(
            parse_envelope_paths(
                envelope.get("Protected dirty paths", ""),
                "Protected dirty paths",
                allow_none=True,
            )
        )
    except ValueError:
        return ConstructionWriteInput(has_errors=True)
    active_task = tasks.active[0] if len(tasks.active) == 1 else None
    active_write_set = (
        tuple(tasks.write_sets.get(active_task, ())) if active_task else ()
    )
    return ConstructionWriteInput(
        has_errors=ctx.has_errors,
        approved_write_roots=roots,
        exclusions=exclusions,
        protected_paths=protected,
        active_task=active_task,
        active_task_write_set=active_write_set,
    )


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


def evaluate_project(
    root: Path,
    *,
    template_source: bool = False,
    prior_remediation_fingerprint: str | None = None,
) -> EngineEvaluation:
    """SAFETY: observe once and compose immutable domains in historical order."""

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
        return build_evaluation(ctx, "BLOCKED", "STOP", {}, TaskSummary())

    manifest = load_json_document(ctx, MANIFEST_FILE, "MANIFEST_PARSE")
    state = load_json_document(ctx, STATE_FILE, "STATE_PARSE")
    if manifest is None or state is None:
        return build_evaluation(
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
        return build_evaluation(
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
        and intake_contract.status == "READY_FOR_REQUIREMENTS"
    ):
        lifecycle_state, next_prompt = "REQUIREMENTS_ANALYSIS", "REQ-10"
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
    authority_bounds = normalize_gate_b_authority_bounds(
        envelope,
        cost_posture=str(state.get("project", {}).get("cost_posture", "")),
        active_artifact=artifact_binding,
    )
    authority_input = AuthorityEvaluationInput(
        has_errors=ctx.has_errors,
        observed_at=ctx.observed_at,
        verify_text=verify_text or "",
    )
    aws_authority_policy = build_aws_authority_policy(
        authority_input,
        authority_bounds,
        parse_verification_matrix=parse_verification_matrix,
    )
    read_authority = (
        _read_preflight_receipt_authority(
            authority_input,
            authority_bounds,
            construction_authorization,
        )
        if construction_authorization != "NONE"
        else None
    )
    preflight = derive_read_preflight_state(
        verify_text or "",
        read_authority,
        policy=aws_authority_policy,
        requirements_revision=str(prd_fields.get("requirements_revision", "")),
        design_revision=str(prd_fields.get("design_revision", "")),
        construction_authorization=construction_authorization,
        artifact_binding=artifact_binding,
    )
    deployment_sequence = derive_deployment_sequence_state(
        verify_text or "",
        read_authority,
        policy=aws_authority_policy,
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
    )
    _preserve_expired_authority_for_deployment_closure(
        ctx, deployment_sequence, release_decision
    )
    teardown_sequence = derive_teardown_sequence_state(
        verify_text or "",
        read_authority,
        policy=aws_authority_policy,
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
    return build_evaluation(
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
        authority_bounds=authority_bounds,
        construction_write_input=_normalize_construction_write_input(
            ctx, envelope, tasks
        ),
    )


def inspect_project(
    root: Path,
    *,
    template_source: bool = False,
    prior_remediation_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Return the stable schema-2 serialization of one complete evaluation."""

    return serialize_evaluation(
        evaluate_project(
            root,
            template_source=template_source,
            prior_remediation_fingerprint=prior_remediation_fingerprint,
        )
    )
