"""Compose immutable Fastlane evaluation state from validated domain results.

Canonical inputs are immutable domain results and one bounded project observation.
Returns an EngineEvaluation containing policy, authority, routing, remediation,
interaction, context, and owner projections before report serialization. Side
effects are prohibited; this module never writes state, performs an external action,
approves a gate, or broadens authority.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from typing import Any, Mapping

from .authority.aws import derive_external_authority
from .authority.github import (
    _aws_action_transition_projection,
    derive_aws_mode_boundary,
    derive_request_match,
)
from .authority.write import (
    derive_aws_lifecycle_intent_write_authority,
    derive_deployment_journal_closure_authority,
    derive_teardown_journal_closure_authority,
    derive_write_authority,
)
from .authority.models import (
    AuthorityEvaluationInput,
    ConstructionWriteInput,
    GateBAuthorityBounds,
    LifecycleIntentWriteInput,
)
from .aws import (
    AWS_TEARDOWN_ATTEMPT_ID,
    AWS_TEARDOWN_TERMINAL_STATUSES,
    aws_deployment_teardown_sequence_conflict,
    derive_aws_residual_disposition,
    release_lifecycle_intent_boundary_is_settled,
)
from .core.contracts import table_after_heading
from .core.ids import clean_cell, explicit_value, validate_relative_path
from .define.models import (
    CoverageContract,
    IntakeFoundationContract,
    RequirementsContract,
)
from .define.requirements import authoritative_requirement_ids
from .design import (
    DesignContract,
    diagram_remediation_headings,
    diagram_patterns_required,
)
from .design.diagrams import filter_diagram_slices
from .evaluation import EngineEvaluation
from .deliver import (
    TaskSummary,
    inspect_task_blocks,
    parse_task_completion_evidence,
    parse_verification_matrix,
    task_remediation_validation_evidence,
)
from .owner_decisions import (
    derive_owner_answer_confirmation,
    derive_owner_decision_brief,
)
from .project_inspection import (
    BUGFIX_FILE,
    DOCUMENT_SUMMARY_FILES,
    PRD_FILE,
    RUNBOOK_FILE,
    TASKS_FILE,
    TASK_ID,
    VERIFY_FILE,
    Context,
    _heading_title_span,
    safe_read_text,
)
from .remediation import (
    _owner_stage_from_gates,
    derive_interaction,
    derive_remediation,
    derive_unconfigured_template_interaction,
)
from .report import serialize_evaluation

try:
    from fastlane_adr import empty_adr_rationale
except ModuleNotFoundError:
    from scripts.fastlane_adr import empty_adr_rationale
try:
    from fastlane_context import SliceRequest, SourceSpan, resolve_context_packet
except ModuleNotFoundError:
    from scripts.fastlane_context import (
        SliceRequest,
        SourceSpan,
        resolve_context_packet,
    )
try:
    from fastlane_contracts import split_markdown_table_row, without_fenced_code
except ModuleNotFoundError:
    from scripts.fastlane_contracts import split_markdown_table_row, without_fenced_code
try:
    from fastlane_document_summaries import (
        build_summary_specifications,
        canonical_bytes_without_generated_summary,
        project_document_summaries,
    )
except ModuleNotFoundError:
    from scripts.fastlane_document_summaries import (
        build_summary_specifications,
        canonical_bytes_without_generated_summary,
        project_document_summaries,
    )
try:
    from fastlane_owner_briefs import finalize_owner_decision_brief
except ModuleNotFoundError:
    from scripts.fastlane_owner_briefs import finalize_owner_decision_brief

CONTEXT_MAXIMUM_INITIAL_BYTES = 12_000


def _context_selector_span(request: SliceRequest, text: str) -> SourceSpan:
    """Resolve one selector through the doctor's canonical Markdown helpers."""

    if request.selector_kind == "WHOLE_FILE":
        if not text:
            raise ValueError("whole-file source is empty")
        return SourceSpan(0, len(text))
    if request.selector_kind == "HEADING":
        return _heading_title_span(text, request.selector)
    if request.selector_kind == "TASK_ID":
        matches = [
            task
            for task in inspect_task_blocks(text)
            if task.task_id == request.selector
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one task {request.selector!r}; found {len(matches)}"
            )
        start = text.find(matches[0].block)
        if start < 0:
            raise ValueError(f"task {request.selector!r} has no canonical source range")
        return SourceSpan(start, start + len(matches[0].block))
    if request.selector_kind == "RECORD_ID":
        structural_lines = without_fenced_code(text).splitlines(keepends=True)
        source_lines = text.splitlines(keepends=True)
        token = re.compile(rf"(?<![A-Z0-9-]){re.escape(request.selector)}(?![A-Z0-9-])")
        matches: list[SourceSpan] = []
        offset = 0
        for source_line, structural_line in zip(source_lines, structural_lines):
            cells = (
                split_markdown_table_row(source_line.rstrip("\r\n"))
                if structural_line.strip().startswith("|")
                else None
            )
            if cells is not None and any(
                token.search(clean_cell(cell)) for cell in cells
            ):
                matches.append(SourceSpan(offset, offset + len(source_line)))
            offset += len(source_line)
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one table record {request.selector!r}; found {len(matches)}"
            )
        return matches[0]
    raise ValueError(f"unsupported selector kind {request.selector_kind!r}")


def _context_request(
    value: str,
    active_ids: list[str],
    *,
    initial: bool,
) -> SliceRequest:
    path, marker, selector = value.partition("#")
    if not marker:
        selector_kind = "WHOLE_FILE"
        selector = path
        priority = 0
        reason = "Current phase procedure"
    elif TASK_ID.fullmatch(selector):
        selector_kind = "TASK_ID"
        priority = 2
        reason = "Active task and dependencies"
    else:
        selector_kind = "HEADING"
        if path == TASKS_FILE:
            priority = 2
            reason = "Active task and dependencies"
        elif path == PRD_FILE:
            priority = 3
            reason = "Controlling PRD record"
        elif path.startswith(".agents/skills/fastlane/references/"):
            priority = 0
            reason = "Current phase procedure"
        else:
            priority = 4
            reason = "Consequential evidence or authority"
    required_selectors = {
        "Document status",
        "Active execution snapshot",
        "AWS Core evidence",
        "Read-only AWS preflight evidence",
        "Read-only AWS preflight",
        "Action authorization provenance",
        "AWS deployment action and reconciliation evidence",
        "Conditional AWS action receipts",
        "Teardown reconciliation evidence",
        "13. Teardown and decommissioning",
        "14. Residual-resource and billing verification",
    }
    # A phase procedure is complete guidance, not one atomic lifecycle record.
    # It may move on demand as a whole when current required state needs the
    # initial budget; the coordinator loads it later only when the current
    # decision requires it. Task blocks and controlling state records remain
    # atomic and required.
    required = initial and (
        selector_kind == "TASK_ID"
        or selector in required_selectors
        or (
            selector_kind == "HEADING"
            and path.startswith(".agents/skills/fastlane/references/")
        )
    )
    return SliceRequest(
        path=path,
        selector_kind=selector_kind,
        selector=selector,
        priority=priority if initial else 5,
        reason=reason if initial else "On-demand canonical source",
        required=required,
        active_ids=tuple(active_ids),
    )


def _resolve_context_metadata(
    source_slices: list[str],
    on_demand_slices: list[str],
    active_ids: list[str],
    source_texts: Mapping[str, str],
) -> tuple[dict[str, object], list[dict[str, str]]]:
    initial_requests = [
        _context_request(value, active_ids, initial=True) for value in source_slices
    ]
    on_demand_requests = [
        _context_request(value, active_ids, initial=False) for value in on_demand_slices
    ]
    return resolve_context_packet(
        initial_requests,
        on_demand_requests,
        source_texts,
        _context_selector_span,
        maximum_initial_source_bytes=CONTEXT_MAXIMUM_INITIAL_BYTES,
    )


def derive_context_plan(
    interaction: Mapping[str, Any],
    tasks: TaskSummary,
    coverage: CoverageContract,
    *,
    next_prompt: str = "",
    restricted_deployment_closure: bool = False,
    restricted_teardown_closure: bool = False,
    source_texts: Mapping[str, str] | None = None,
    adr_rationale: Mapping[str, Any] | None = None,
    requirements_contract: RequirementsContract | None = None,
    design_contract: DesignContract | None = None,
    diagram_remediation_required: bool = False,
) -> dict[str, Any]:
    """SAFETY: select an ephemeral, route-bounded canonical context packet."""
    stage = interaction.get("owner_stage")
    reason = interaction.get("route_reason_code")
    prd_source = source_texts.get(PRD_FILE) if source_texts is not None else None
    deployment_closure_context = restricted_deployment_closure and next_prompt in {
        "AWS-20",
        "AWS-30",
        "RELEASE-10",
    }
    teardown_closure_context = restricted_teardown_closure and next_prompt in {
        "AWS-40",
        "AWS-50",
    }
    closure_context = deployment_closure_context or teardown_closure_context
    if teardown_closure_context:
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#Teardown and residuals",
            f"{VERIFY_FILE}#Teardown reconciliation evidence",
        ]
        on_demand_slices = [
            f"{TASKS_FILE}#Active execution snapshot",
            f"{PRD_FILE}#Construction envelope",
            f"{VERIFY_FILE}#Action authorization provenance",
            f"{VERIFY_FILE}#Read-only AWS preflight evidence",
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
            f"{RUNBOOK_FILE}#Conditional AWS action receipts",
            f"{RUNBOOK_FILE}#Read-only AWS preflight",
            f"{RUNBOOK_FILE}#13. Teardown and decommissioning",
            f"{RUNBOOK_FILE}#14. Residual-resource and billing verification",
        ]
    elif deployment_closure_context:
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#AWS handoff and reconciliation",
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
        ]
        on_demand_slices = [
            f"{TASKS_FILE}#Active execution snapshot",
            f"{PRD_FILE}#Construction envelope",
            f"{VERIFY_FILE}#Action authorization provenance",
            f"{VERIFY_FILE}#Read-only AWS preflight evidence",
            f"{RUNBOOK_FILE}#Conditional AWS action receipts",
            f"{RUNBOOK_FILE}#Read-only AWS preflight",
        ]
        if next_prompt in {"AWS-30", "RELEASE-10"}:
            on_demand_slices.extend(
                [
                    f"{VERIFY_FILE}#Verification matrix",
                    f"{VERIFY_FILE}#Current release decision",
                ]
            )
    elif stage == "DEFINE":
        source_slices = [
            ".agents/skills/fastlane/references/define.md#Setup and intake",
            f"{PRD_FILE}#Document status",
            f"{PRD_FILE}#Product Agreement",
        ]
        on_demand_slices = [
            ".agents/skills/fastlane/references/define.md#Requirements and Gate A",
            ".agents/skills/fastlane/references/define.md#Review and AWS evidence",
            f"{PRD_FILE}#Gate A Review",
            BUGFIX_FILE,
        ]
    elif stage == "DESIGN":
        source_slices = [
            ".agents/skills/fastlane/references/design.md#Architecture selection and records",
            f"{PRD_FILE}#Adaptive coverage plan",
            f"{PRD_FILE}#Architecture drivers",
            f"{PRD_FILE}#Whole-system candidates",
            f"{PRD_FILE}#Selected architecture",
            f"{VERIFY_FILE}#AWS Core evidence",
        ]
        on_demand_slices = [
            ".agents/skills/fastlane/references/design.md#Architecture and AWS evidence",
            ".agents/skills/fastlane/references/design.md#Validation, diagrams, and Gate B",
            ".agents/skills/fastlane/references/design.md#Challenger and approval",
            f"{PRD_FILE}#Architecture traceability",
            f"{PRD_FILE}#Change impact record",
            f"{PRD_FILE}#Project diagram contract",
            f"{PRD_FILE}#Proposed system at a glance",
            f"{PRD_FILE}#AWS implementation at a glance",
            f"{PRD_FILE}#Gate B Harness Profile",
            f"{PRD_FILE}#Construction envelope",
        ]
    elif stage == "DELIVER":
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#Tasks and local construction",
            f"{TASKS_FILE}#Active execution snapshot",
        ]
        on_demand_slices = [
            ".agents/skills/fastlane/references/deliver.md#AWS handoff and reconciliation",
            ".agents/skills/fastlane/references/deliver.md#Teardown and residuals",
            f"{PRD_FILE}#Construction envelope",
            f"{VERIFY_FILE}#Task completion evidence",
            f"{VERIFY_FILE}#Construction and release readiness checks",
            f"{RUNBOOK_FILE}#Active operational boundary",
        ]
    else:
        raise ValueError("context plan requires a known owner stage")

    active_ids: list[str] = []
    task_context_ids: list[str] = []
    if stage == "DELIVER":
        task_context_ids.extend(tasks.active)
        if not task_context_ids and tasks.ready:
            task_context_ids.append(tasks.ready[0])
        active_ids.extend(task_context_ids)
    else:
        active_ids.extend(coverage.basis_ids)
    blockers = interaction.get("blocking_ids")
    if isinstance(blockers, list):
        active_ids.extend(item for item in blockers if isinstance(item, str))
    active_ids = sorted(set(active_ids))

    if stage == "DELIVER" and task_context_ids:
        source_slices.append(f"{TASKS_FILE}#" + task_context_ids[0])
    aws_phase = next_prompt if next_prompt.startswith("AWS-") else ""
    teardown_context_reasons = {
        "AWS_RESIDUAL_REVIEW",
        "AWS_RESIDUAL_REVIEW_COMPLETE",
        "AWS_RESIDUALS_RETAINED",
        "AWS_RESIDUALS_REMAIN",
        "AWS_RESIDUAL_REVIEW_BLOCKED",
        "AWS_TEARDOWN_COMPLETE",
        "AWS_TEARDOWN_ACTION_TERMINAL",
    }
    teardown_phase_context = (
        aws_phase in {"AWS-40", "AWS-50"} or reason in teardown_context_reasons
    )
    if teardown_phase_context and not closure_context:
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#Teardown and residuals",
            f"{VERIFY_FILE}#Teardown reconciliation evidence",
        ]
        on_demand_slices.extend(
            [
                f"{TASKS_FILE}#Active execution snapshot",
                f"{PRD_FILE}#Construction envelope",
                f"{VERIFY_FILE}#Action authorization provenance",
                f"{VERIFY_FILE}#Read-only AWS preflight evidence",
                f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
                f"{VERIFY_FILE}#AWS Core evidence",
                f"{RUNBOOK_FILE}#Conditional AWS action receipts",
                f"{RUNBOOK_FILE}#Read-only AWS preflight",
                f"{RUNBOOK_FILE}#13. Teardown and decommissioning",
                f"{RUNBOOK_FILE}#14. Residual-resource and billing verification",
            ]
        )
        if task_context_ids:
            on_demand_slices.append(f"{TASKS_FILE}#" + task_context_ids[0])
    common_aws_slices = [
        f"{VERIFY_FILE}#Action authorization provenance",
        f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
        f"{RUNBOOK_FILE}#Conditional AWS action receipts",
        f"{VERIFY_FILE}#AWS Core evidence",
        f"{VERIFY_FILE}#Read-only AWS preflight evidence",
        f"{RUNBOOK_FILE}#Read-only AWS preflight",
    ]
    if closure_context:
        pass
    elif teardown_phase_context:
        pass
    elif reason == "AWS_DEPLOYMENT_ACTION_TERMINAL":
        source_slices.append(
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence"
        )
        on_demand_slices.extend(common_aws_slices)
    elif reason == "AWS_DEPLOYMENT_RECONCILIATION":
        source_slices.append(
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence"
        )
        on_demand_slices.extend(common_aws_slices)
    elif aws_phase or (isinstance(reason, str) and reason.startswith("AWS_")):
        source_slices.extend(common_aws_slices)
    if aws_phase == "AWS-30" and not closure_context:
        source_slices.extend(
            [
                f"{VERIFY_FILE}#Verification matrix",
                f"{VERIFY_FILE}#Current release decision",
            ]
        )
    if next_prompt == "RELEASE-10" and not closure_context:
        source_slices.extend(
            [
                f"{VERIFY_FILE}#Verification matrix",
                f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
                f"{VERIFY_FILE}#Current release decision",
            ]
        )
    if stage == "DESIGN" or diagram_remediation_required:
        reqs, design = requirements_contract, design_contract
        if isinstance(prd_source, str) and (
            diagram_remediation_required
            or diagram_patterns_required(
                prd_source,
                authoritative_requirement_ids(prd_source),
                coverage.work_kind,
                journey_ids=reqs.journey_ids if reqs else (),
                use_case_ids=reqs.use_case_ids if reqs else (),
                state_ids=design.project_contract.state_ids if design else (),
            )
        ):
            on_demand_slices.append(
                ".agents/skills/fastlane/references/diagram-patterns.md"
            )
    if diagram_remediation_required and design_contract is not None:
        headings = diagram_remediation_headings(design_contract.diagram_contract)
        on_demand_slices.extend(f"{PRD_FILE}#{heading}" for heading in headings)
    on_demand_slices = filter_diagram_slices(on_demand_slices, PRD_FILE, prd_source)
    if stage in {"DESIGN", "DELIVER"} and isinstance(adr_rationale, Mapping):
        records = adr_rationale.get("records")
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                relative = validate_relative_path(record.get("path"))
                if relative is not None and relative.startswith("docs/adr/"):
                    on_demand_slices.append(relative)
    source_slices = list(dict.fromkeys(source_slices))
    on_demand_slices = list(dict.fromkeys(on_demand_slices))

    plan: dict[str, Any] = {
        "source_slices": source_slices,
        "active_ids": active_ids,
        "on_demand_slices": on_demand_slices,
        "maximum_initial_bytes": CONTEXT_MAXIMUM_INITIAL_BYTES,
    }
    if source_texts is not None:
        metadata, issues = _resolve_context_metadata(
            source_slices,
            on_demand_slices,
            active_ids,
            source_texts,
        )
        plan.update(metadata)
        plan["_resolution_issues"] = issues
    return plan


def _summary_table(ctx: Context, path: str, heading: str) -> dict[str, str]:
    text = ctx.texts.get(path, "")
    if not text:
        return {}
    try:
        return table_after_heading(text, heading)
    except ValueError:
        return {}


def _summary_value(value: object, fallback: str) -> str:
    cleaned = clean_cell(value)
    return cleaned if explicit_value(cleaned, allow_none=False) else fallback


def _summary_bullet(text: str, label: str) -> str:
    match = re.search(rf"(?m)^- {re.escape(label)}:[ \t]*(?P<value>.+?)[ \t]*$", text)
    return clean_cell(match.group("value")) if match else ""


def _summary_section(text: str, heading: str) -> str:
    """Return one Markdown section without treating its content as policy."""

    level = len(heading) - len(heading.lstrip("#"))
    if level < 1:
        return ""
    pattern = (
        rf"(?ms)^{re.escape(heading)}[ \t]*\r?$\n"
        rf"(?P<body>.*?)(?=^#{{1,{level}}}[ \t]+|\Z)"
    )
    match = re.search(pattern, text)
    return match.group("body").strip() if match else ""


def _summary_section_has_value(text: str, heading: str) -> bool:
    section = _summary_section(text, heading)
    if not section:
        return False
    values = [
        clean_cell(re.sub(r"^(?:[-*]|\d+\.)[ \t]+", "", line))
        for line in section.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return any(explicit_value(value, allow_none=False) for value in values)


def _summary_evidence_ids(verify_text: str) -> tuple[set[str], set[str]]:
    """Derive local passing and failed IDs from typed canonical evidence rows."""

    passing: set[str] = set()
    failed: set[str] = set()
    try:
        completion_rows = parse_task_completion_evidence(verify_text)
    except ValueError:
        completion_rows = []
    for row in completion_rows:
        status = clean_cell(row.status).upper()
        if status in {"LOCAL_PASS", "VERIFIED"}:
            passing.add(row.evidence_id)
        elif status in {"FAILED", "STALE", "BLOCKED"}:
            failed.add(row.evidence_id)

    try:
        matrix_rows = parse_verification_matrix(verify_text)
    except ValueError:
        matrix_rows = []
    for row in matrix_rows:
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        status = clean_cell(row.get("Status", "")).upper()
        if re.fullmatch(r"EV-\d{4,}", evidence_id) is None:
            continue
        if status in {"FAILED", "STALE", "BLOCKED"}:
            failed.add(evidence_id)
    return passing, failed


def _summary_aws_core_evidence(
    aws_core_usage: Mapping[str, Any],
) -> tuple[bool, str]:
    """Project only observed canonical AWS Core discovery chains."""

    discovery_ids: set[str] = set()
    for phase in ("REQ-10", "DESIGN-10", "AWS-10"):
        usage = aws_core_usage.get(phase)
        if not isinstance(usage, Mapping) or usage.get("status") != "OBSERVED":
            continue
        chains = usage.get("chains")
        if not isinstance(chains, list):
            continue
        for chain in chains:
            if not isinstance(chain, Mapping):
                continue
            discovery_id = clean_cell(chain.get("discovery_id", ""))
            if re.fullmatch(r"AWS-DISC-\d{4,}", discovery_id):
                discovery_ids.add(discovery_id)
    return bool(discovery_ids), ", ".join(sorted(discovery_ids)) or "None"


def _summary_updated_basis(
    *,
    lifecycle_state: str,
    gate_b: str,
    requirements_id: str | None,
    design_id: str | None,
    checkpoint: str,
    cutoff: str,
) -> str:
    """Choose the latest material canonical identity for the current stage."""

    if lifecycle_state in {"INTAKE_REQUIRED", "REQUIREMENTS_STALE", "WAITING_GATE_A"}:
        return requirements_id or design_id or "Current canonical records"
    if gate_b in {"PENDING_OWNER_APPROVAL", "STALE"}:
        return design_id or requirements_id or "Current canonical records"
    if cutoff != "Not yet recorded":
        return cutoff
    if checkpoint != "None":
        return checkpoint
    if gate_b == "APPROVED_FOR_CONSTRUCTION":
        return design_id or requirements_id or "Current canonical records"
    return requirements_id or design_id or "Current canonical records"


def _summary_deployment_observation(
    sequence: Mapping[str, Any],
    environment: str,
) -> dict[str, Any]:
    """SAFETY: distinguish reconciliation from observed deployment success."""

    status = clean_cell(sequence.get("status", "NOT_ACTIVE"))
    action = clean_cell(sequence.get("action_status", "NONE"))
    reconciliation = clean_cell(sequence.get("reconciliation_status", "NONE"))
    raw_evidence = sequence.get("acceptance_evidence_ids", [])
    evidence = (
        [str(item) for item in raw_evidence] if isinstance(raw_evidence, list) else []
    )
    observed = bool(
        status == "RECONCILED"
        and action == "SUCCEEDED"
        and reconciliation == "COMPLETE"
        and evidence
        and explicit_value(environment, allow_none=False)
        and environment not in {"Not yet initialized", "Not yet recorded"}
    )
    if observed:
        state = "Deployment observed"
        emergency = "Follow the current runbook and authority"
    elif status == "RECONCILED" and reconciliation == "COMPLETE" and action == "FAILED":
        state = "Failed deployment attempt reconciled; deployment not verified"
        emergency = "No successful deployment is recorded"
    elif (
        status == "RECONCILED" and reconciliation == "COMPLETE" and action == "PARTIAL"
    ):
        state = "Partial deployment reconciled; expected release not fully observed"
        emergency = "Environment state is only partially observed"
    elif (
        status == "RECONCILED" and reconciliation == "COMPLETE" and action == "UNKNOWN"
    ):
        state = "Deployment attempt reconciled, but terminal success remains unknown"
        emergency = "Environment state is not proven"
    elif action == "STARTED" or action in {"FAILED", "PARTIAL", "UNKNOWN"}:
        state = "Deployment outcome pending reconciliation"
        emergency = "Environment state is not proven"
    elif (
        status == "RECONCILED"
        and reconciliation == "COMPLETE"
        and action == "SUCCEEDED"
    ):
        state = "Deployment reconciled; acceptance evidence is incomplete"
        emergency = "Deployment acceptance is not proven"
    elif status in {"", "NOT_ACTIVE", "NONE"}:
        state = "Not deployed"
        emergency = "No deployed environment exists"
    else:
        state = status.replace("_", " ").title()
        emergency = "No successful deployment is recorded"
    return {
        "observed": observed,
        "state": state,
        "emergency": emergency,
        "evidence_ids": evidence,
        "environment": environment,
        "inactive": action in {"", "NONE"} and status in {"", "NOT_ACTIVE", "NONE"},
    }


def _summary_teardown_observation(
    sequence: Mapping[str, Any], environment: str
) -> dict[str, Any]:
    """SAFETY: project teardown only from a validated terminal review."""

    status = clean_cell(sequence.get("status", "NOT_ACTIVE"))
    action = clean_cell(sequence.get("action_status", "NONE"))
    evidence_id = clean_cell(sequence.get("evidence_id", "NONE"))
    observed = bool(
        status == "VERIFIED_CLEAN"
        and action == "SUCCEEDED"
        and explicit_value(evidence_id, allow_none=False)
        and explicit_value(environment, allow_none=False)
        and environment not in {"Not yet initialized", "Not yet recorded"}
    )
    if observed:
        state = "Teardown observed"
    elif status == "RESIDUALS_REMAIN":
        state = "Teardown incomplete; residual resources remain"
    elif action == "STARTED" or status in {
        "ACTION_TERMINAL_REQUIRED",
        "POST_ACTION_REVIEW",
    }:
        state = "Teardown outcome pending reconciliation"
    elif action in {"FAILED", "PARTIAL", "UNKNOWN"}:
        state = "Teardown attempt not verified"
    else:
        state = "Not yet observed"
    return {
        "observed": observed,
        "state": state,
        "evidence_id": evidence_id if evidence_id != "NONE" else "None",
        "environment": environment,
        "inactive": status in {"", "NOT_ACTIVE", "NONE"},
    }


def derive_document_summary_specifications(
    ctx: Context,
    *,
    classification: str,
    lifecycle_state: str,
    next_prompt: str,
    project: Mapping[str, Any],
    prd_fields: Mapping[str, str],
    gate_a: str,
    gate_b: str,
    tasks: TaskSummary,
    release_decision: str,
    release_evidence_cutoff: str,
    aws_authorization: str,
    external_authority: Mapping[str, Any],
    interaction: Mapping[str, Any],
    active_artifact: str,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
    aws_core_usage: Mapping[str, Any],
    req_aws_core_materiality: str,
    write_authority: Mapping[str, Any],
    remediation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    # fmt: on
    """SAFETY: normalize canonical values for presentation-only summaries."""

    template_like = classification in {"TEMPLATE_SOURCE", "UNCONFIGURED_TEMPLATE"}
    prd_card = _summary_table(ctx, PRD_FILE, "### Gate A — readiness card")
    task_snapshot = _summary_table(ctx, TASKS_FILE, "## Active execution snapshot")
    verify_scope = _summary_table(ctx, VERIFY_FILE, "## Active evidence scope")
    runbook_boundary = _summary_table(
        ctx, RUNBOOK_FILE, "## Active operational boundary"
    )
    verify_text = ctx.texts.get(VERIFY_FILE, "")
    bugfix_text = ctx.texts.get(BUGFIX_FILE, "")

    requirements_id = prd_fields.get("requirements_revision")
    design_id = prd_fields.get("design_revision")
    authorization_id = prd_fields.get("construction_authorization")
    checkpoint = _summary_value(task_snapshot.get("Last checkpoint"), "None")
    cutoff = _summary_value(release_evidence_cutoff, "Not yet recorded")
    environment = _summary_value(
        runbook_boundary.get("Region and environment"),
        (
            f"Development in {project.get('region')}"
            if project.get("region")
            else "Not yet recorded"
        ),
    )
    updated = _summary_updated_basis(
        lifecycle_state=lifecycle_state,
        gate_b=gate_b,
        requirements_id=requirements_id,
        design_id=design_id,
        checkpoint=checkpoint,
        cutoff=cutoff,
    )

    observed_ids, failed_ids = _summary_evidence_ids(verify_text)

    local_observed = bool(observed_ids) and release_decision in {
        "READY_TO_DEPLOY",
        "RELEASE_VERIFIED",
    }
    deployment = _summary_deployment_observation(deployment_sequence, environment)
    teardown = _summary_teardown_observation(teardown_sequence, environment)
    deployment_observed = bool(deployment["observed"])
    teardown_observed = bool(teardown["observed"])
    requirements_approved = gate_a == "APPROVED_FOR_DESIGN"
    design_approved = gate_b == "APPROVED_FOR_CONSTRUCTION"
    guidance_ready, guidance_evidence = _summary_aws_core_evidence(aws_core_usage)
    guidance_limitation = (
        "Source guidance is not deployment evidence"
        if template_like
        else "No current AWS Core evidence was required or recorded"
        if req_aws_core_materiality == "NOT_MATERIAL"
        else "Current AWS Core evidence has not been recorded"
    )
    deployment_pending = (
        ("Not authorized", "None", "No deployment evidence or authority")
        if deployment["inactive"]
        else (
            "Not yet observed",
            "None",
            str(deployment["state"]),
        )
    )
    teardown_pending = (
        ("Not authorized", "None", "No teardown evidence or authority")
        if teardown["inactive"]
        else ("Not yet observed", str(teardown["evidence_id"]), str(teardown["state"]))
    )
    # fmt: off
    claim_rows = (
        ("Requirements are approved", requirements_approved, ("Owner confirmed", requirements_id, "Does not approve construction"), ("Not yet observed", "None", "Gate A is not approved")),
        ("Technical design is approved", design_approved, ("Owner confirmed", design_id, "Does not authorize AWS account work"), ("Not yet observed", "None", "Gate B is not approved")),
        ("Current AWS guidance informed the plan", guidance_ready and not template_like, ("Source verified", guidance_evidence, "Source guidance is not deployment evidence"), ("Not yet observed", "None", guidance_limitation)),
        ("Local release checks passed", local_observed, ("Locally observed", ", ".join(sorted(observed_ids)), "Local evidence does not prove AWS behavior"), ("Not yet observed", "None", "Local evidence does not prove AWS behavior")),
        ("Application is deployed", deployment_observed, ("Deployed observed", ", ".join(deployment["evidence_ids"]), f"Bound to {deployment['environment']}"), deployment_pending),
        ("Teardown is complete", teardown_observed, ("Teardown observed", str(teardown["evidence_id"]), f"Bound to {teardown['environment']}"), teardown_pending),
    )
    # fmt: on
    claims = []
    for claim, ready, current, pending in claim_rows:
        maturity, evidence, limitation = current if ready else pending
        claims.append(
            {
                "claim": claim,
                "maturity": maturity,
                "evidence": evidence,
                "limitation": limitation,
            }
        )

    unobserved = []
    if not local_observed:
        unobserved.append("Local build")
    if not deployment_observed:
        unobserved.append("AWS deployment")
    unobserved.append("recovery")
    if not teardown_observed:
        unobserved.append("teardown")

    task_progress = (
        f"{len(tasks.done)} of {tasks.total} tasks complete"
        if tasks.total
        else "No tasks generated"
    )
    bug_title = _summary_bullet(bugfix_text, "Title")
    bug_active = active_artifact == BUGFIX_FILE or explicit_value(bug_title)
    bug_impact = _summary_bullet(bugfix_text, "User impact")
    bug_scope = _summary_bullet(bugfix_text, "Allowed scope")
    bug_aws_resources = _summary_bullet(bugfix_text, "AWS resources affected")
    checked_criteria = len(re.findall(r"(?m)^- \[[xX]\] ", bugfix_text))
    total_criteria = len(re.findall(r"(?m)^- \[[ xX]\] ", bugfix_text))
    regression_status = (
        "Passed"
        if checked_criteria and checked_criteria == total_criteria
        else "In progress"
        if checked_criteria
        else "Pending evidence"
    )
    architecture_impact = "Not yet assessed"
    if explicit_value(bug_aws_resources, allow_none=True):
        architecture_impact = (
            "No AWS architecture change recorded"
            if clean_cell(bug_aws_resources).upper() == "NONE"
            else f"AWS resources affected: {clean_cell(bug_aws_resources)}"
        )
    bugfix = {
        "status": "Active bounded defect" if bug_active else "No active bounded defect",
        "defect": _summary_value(bug_title, "None") if bug_active else "None",
        "impact": (
            _summary_value(bug_impact, "Not yet recorded") if bug_active else "None"
        ),
        "reproduction": (
            "Recorded"
            if bug_active
            and _summary_section_has_value(bugfix_text, "### Actual result")
            else "Pending evidence"
            if bug_active
            else "Not active"
        ),
        "root_cause": (
            "Confirmed"
            if bug_active
            and _summary_section_has_value(bugfix_text, "### Confirmed evidence")
            else "Pending evidence"
            if bug_active
            else "Not active"
        ),
        "repair": (
            "Bounded"
            if bug_active and explicit_value(bug_scope)
            else "Not started"
            if bug_active
            else "Not active"
        ),
        "regression": regression_status if bug_active else "Not active",
        "architecture": architecture_impact if bug_active else "None",
        "environment": (
            _summary_value(_summary_bullet(bugfix_text, "Environment"), "Not recorded")
            if bug_active
            else "Not active"
        ),
        "requirements": (
            _summary_value(
                _summary_bullet(bugfix_text, "Related PRD requirements"), "None"
            )
            if bug_active
            else "None"
        ),
        "updated": updated,
    }
    authority_kind = str(external_authority.get("kind", "NONE"))
    account_access = external_authority.get(
        "validity"
    ) == "CURRENT" and authority_kind in {
        "AWS_READ_ONLY",
        "AWS_DEPLOYMENT",
        "AWS_TEARDOWN",
    }
    authority_label = {
        "AWS_READ_ONLY": "Read-only AWS access",
        "AWS_DEPLOYMENT": "AWS deployment authority",
        "AWS_TEARDOWN": "AWS teardown authority",
    }.get(authority_kind, "None")
    # fmt: off
    return build_summary_specifications({
        "template_like": template_like, "lifecycle_state": lifecycle_state, "next_prompt": next_prompt,
        "owner_stage": interaction.get("owner_stage"), "action_kind": interaction.get("owner_action_kind"),
        "route_reason_code": interaction.get("route_reason_code"),
        "automatic_continuation_allowed": interaction.get("automatic_continuation_allowed"),
        "automatic_action_kind": (
            remediation.get("next_action", {}).get("action_kind")
            if isinstance(remediation.get("next_action"), Mapping)
            else ""
        ),
        "gate_a": gate_a, "gate_b": gate_b, "requirements_revision": requirements_id,
        "design_revision": design_id, "construction_authorization": authorization_id,
        "construction_authority_valid": write_authority.get("valid") is True,
        "aws_authorization": aws_authorization, "aws_account_access_authorized": account_access,
        "updated": updated, "product_outcome": _summary_value(prd_card.get("Outcome"), "Not yet confirmed"),
        "release_boundary": _summary_value(prd_card.get("Scope and non-goals"), "Not yet confirmed"),
        "region_and_cost": "Not yet recorded" if template_like else f"{project.get('region') or 'Region not recorded'}; {project.get('cost_posture') or 'Cost posture not recorded'}",
        "record_identities": "Not yet initialized" if template_like else " / ".join(item for item in (requirements_id, design_id, authorization_id) if item),
        "tasks": {
            "progress": task_progress, "plan_revision": tasks.plan_revision,
            "wave": _summary_value(task_snapshot.get("Current wave"), "None"),
            "active": ", ".join(tasks.active) if tasks.active else "None",
            "readiness": tasks.plan_state.replace("_", " ").title(),
            "blocker": ", ".join(tasks.blocked) if tasks.blocked else "None",
            "checkpoint": checkpoint, "known_green": _summary_value(task_snapshot.get("Last known-green commit"), "None"),
            "updated": checkpoint if checkpoint != "None" else updated,
        },
        "verify": {
            "release_result": release_decision.replace("_", " ").title(),
            "observed_count": str(len(observed_ids)), "failed_count": str(len(failed_ids)),
            "unobserved": ", ".join(unobserved),
            "cutoff": _summary_value(verify_scope.get("Evidence cutoff"), cutoff),
            "updated": cutoff if cutoff != "Not yet recorded" else updated, "claims": claims,
        },
        "operations": {
            "environment": environment,
            "deployment_state": deployment["state"],
            "authority": authority_label if account_access else "None",
            "safe_action": "Only the exact authorized AWS operation" if account_access else "Local validation only",
            "deployment_approval": "Authorized only for the current deployment" if account_access and external_authority.get("kind") == "AWS_DEPLOYMENT" else "Not authorized",
            "teardown_approval": "Authorized only for the current teardown" if account_access and external_authority.get("kind") == "AWS_TEARDOWN" else "Not authorized",
            "recovery_state": "Not yet observed",
            "emergency_state": deployment["emergency"],
            "updated": updated,
        },
        "bugfix": bugfix,
    })


def _compose_authority_state(
    ctx: Context,
    *,
    authority_bounds: GateBAuthorityBounds,
    construction_write_input: ConstructionWriteInput,
    lane: str | None,
    tasks: TaskSummary,
    prd_fields: Mapping[str, str],
    lifecycle: Mapping[str, Any],
    gate_b: str,
    release_decision: str,
    aws_execution: Mapping[str, Any],
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
    lifecycle_intent: Mapping[str, Any],
    aws_progress_state: str | None,
    next_prompt: str,
    aws_sequence_conflict: bool,
) -> dict[str, Any]:
    """SAFETY: compose authority projections against one restriction basis.

    The order is intentional: each later projection consumes the already-derived
    route, lifecycle state, and restriction intersections. Splitting this sequence
    across independently callable helpers could evaluate authority against
    mismatched bases and accidentally broaden an external-action boundary.
    """

    authorization_id = prd_fields.get("construction_authorization") or lifecycle.get(
        "construction_authorization"
    )
    gate_b_authorization = (
        authorization_id
        if not ctx.has_errors and gate_b == "APPROVED_FOR_CONSTRUCTION"
        else "NONE"
    )
    deployment_status = clean_cell(deployment_sequence.get("status", ""))
    auditable_status = (
        deployment_status
        in {
            "ACTION_TERMINAL_REQUIRED",
            "RECONCILIATION_REQUIRED",
            "RECONCILED",
            "BLOCKED",
        }
        or (deployment_status == "CONSUMED" and release_decision != "READY_TO_DEPLOY")
        or (
            deployment_status == "NOT_ACTIVE" and release_decision == "RELEASE_VERIFIED"
        )
    )
    deployment_restricted = bool(
        not ctx.has_errors
        and not deployment_sequence.get("issues")
        and auditable_status
    )
    teardown_status = clean_cell(teardown_sequence.get("status", ""))
    teardown_attempt_id = clean_cell(teardown_sequence.get("attempt_id", ""))
    teardown_action_status = clean_cell(teardown_sequence.get("action_status", ""))
    teardown_restricted = bool(
        AWS_TEARDOWN_ATTEMPT_ID.fullmatch(teardown_attempt_id)
        and teardown_action_status in {"STARTED", *AWS_TEARDOWN_TERMINAL_STATUSES}
        and teardown_status
        in {"ACTION_TERMINAL_REQUIRED", "POST_ACTION_REVIEW", "BLOCKED"}
    )
    restricted_construction = (
        "NONE" if deployment_restricted or teardown_restricted else gate_b_authorization
    )
    authority_input = AuthorityEvaluationInput(
        has_errors=ctx.has_errors,
        observed_at=ctx.observed_at,
        verify_text=ctx.texts.get(VERIFY_FILE, ""),
    )
    deployment_closure = derive_deployment_journal_closure_authority(
        deployment_sequence,
        next_prompt,
        restricted_closure=deployment_restricted,
    )
    teardown_closure = derive_teardown_journal_closure_authority(
        teardown_sequence,
        next_prompt,
        restricted_closure=teardown_restricted,
    )
    preflight = (
        aws_execution.get("preflight")
        if isinstance(aws_execution.get("preflight"), Mapping)
        else None
    )
    external_authority = derive_external_authority(
        authority_input,
        authority_bounds,
        lane,
        restricted_construction,
        aws_progress_state=aws_progress_state,
        aws_action_phase=next_prompt,
        teardown_review=teardown_sequence,
        deployment_sequence=deployment_sequence,
        preflight=preflight,
    )
    lifecycle_write_input = LifecycleIntentWriteInput(
        has_errors=ctx.has_errors,
        tasks_terminal=tasks.terminal,
        release_decision=release_decision,
        deployment_status=deployment_status,
        deployment_boundary_settled=release_lifecycle_intent_boundary_is_settled(
            release_decision, deployment_sequence
        ),
        teardown_status=teardown_status,
        teardown_has_issues=bool(teardown_sequence.get("issues")),
        external_authority_current=(
            clean_cell(external_authority.get("validity", "")) == "CURRENT"
        ),
        intent_value=clean_cell(lifecycle_intent.get("value", "NONE")),
    )
    lifecycle_write_authority = derive_aws_lifecycle_intent_write_authority(
        lifecycle_write_input
    )
    construction_authorization = (
        "NONE"
        if lifecycle_write_authority.get("valid") is True
        else restricted_construction
    )
    write_authority = derive_write_authority(
        replace(construction_write_input, has_errors=ctx.has_errors),
        construction_authorization,
    )
    aws_authorization = "NONE"
    if external_authority.get("validity") == "CURRENT" and external_authority.get(
        "kind"
    ) in {"AWS_READ_ONLY", "AWS_DEPLOYMENT", "AWS_TEARDOWN"}:
        projected_authorization = external_authority.get("authorization_id")
        if isinstance(projected_authorization, str):
            aws_authorization = projected_authorization
    external_authority["request_match"] = derive_request_match(ctx, external_authority)

    transition_authority: dict[str, Any] = {
        "kind": "NONE",
        "validity": "NONE",
        "request_match": {},
    }
    transition_sequence: Mapping[str, Any] = {}
    transition_kind = "NONE"
    transition_authorization_field = ""
    transition_receipt_field = ""
    if not aws_sequence_conflict and deployment_status == "ACTION_TERMINAL_REQUIRED":
        transition_authority = derive_external_authority(
            authority_input,
            authority_bounds,
            lane,
            gate_b_authorization,
            aws_progress_state=aws_progress_state,
            aws_action_phase="AWS-20",
            teardown_review=teardown_sequence,
            deployment_sequence={},
            preflight=preflight,
        )
        transition_sequence = deployment_sequence
        transition_kind = clean_cell(transition_authority.get("kind", ""))
        transition_authorization_field = "deployment_authorization"
        transition_receipt_field = "deployment_receipt_digest"
    elif not aws_sequence_conflict and teardown_status == "ACTION_TERMINAL_REQUIRED":
        transition_review = {
            **teardown_sequence,
            "status": "READY_FOR_TEARDOWN",
            "evidence_id": teardown_sequence.get("ready_evidence_id", "NONE"),
        }
        transition_authority = derive_external_authority(
            authority_input,
            authority_bounds,
            lane,
            gate_b_authorization,
            aws_progress_state=aws_progress_state,
            aws_action_phase="AWS-50",
            teardown_review=transition_review,
            deployment_sequence=deployment_sequence,
            preflight=preflight,
        )
        transition_sequence = teardown_sequence
        transition_kind = "AWS_TEARDOWN"
        transition_authorization_field = "teardown_authorization"
        transition_receipt_field = "teardown_receipt_digest"
    transition_request_match = (
        derive_request_match(ctx, transition_authority)
        if transition_kind != "NONE"
        else None
    )
    transition = _aws_action_transition_projection(
        transition_request_match,
        transition_sequence,
        authority_kind=transition_kind,
        authorization_field=transition_authorization_field,
        receipt_digest_field=transition_receipt_field,
    )
    return {
        "construction_authorization": construction_authorization,
        "aws_authorization": aws_authorization,
        "write_authority": write_authority,
        "deployment_closure": deployment_closure,
        "teardown_closure": teardown_closure,
        "lifecycle_write_authority": lifecycle_write_authority,
        "external_authority": external_authority,
        "transition": transition,
        "aws_mutation_authority_ready": (
            external_authority.get("validity") == "CURRENT"
            and external_authority.get("kind") in {"AWS_DEPLOYMENT", "AWS_TEARDOWN"}
        ),
        "deployment_restricted": deployment_restricted,
        "teardown_restricted": teardown_restricted,
    }


def build_evaluation(
    ctx: Context,
    lifecycle_state: str,
    next_prompt: str,
    prd_fields: dict[str, str],
    tasks: TaskSummary,
    *,
    manifest: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    release_decision: str = "NOT_READY",
    envelope: dict[str, str] | None = None,
    aws_execution_planning_ready: bool = False,
    design_aws_core_ready: bool = False,
    design_contract: DesignContract | None = None,
    adr_rationale: Mapping[str, Any] | None = None,
    intake_contract: IntakeFoundationContract | None = None,
    coverage_contract: CoverageContract | None = None,
    requirements_contract: RequirementsContract | None = None,
    aws_core_usage: Mapping[str, Any] | None = None,
    aws_execution: Mapping[str, Any] | None = None,
    owner_stage_hint: str | None = None,
    active_artifact: str = "",
    deployment_sequence: Mapping[str, Any] | None = None,
    teardown_sequence: Mapping[str, Any] | None = None,
    release_evidence_cutoff: str = "NONE",
    req_aws_core_materiality: str = "OPTIONAL",
    req_aws_core_ready: bool = True,
    aws_lifecycle_intent_record: Mapping[str, Any] | None = None,
    authority_bounds: GateBAuthorityBounds | None = None,
    construction_write_input: ConstructionWriteInput | None = None,
) -> EngineEvaluation:
    """SAFETY: derive complete immutable state without changing canonical state."""

    manifest = manifest or {}
    state = state or {}
    setup = state.get("setup") if isinstance(state.get("setup"), dict) else {}
    project = state.get("project") if isinstance(state.get("project"), dict) else {}
    lifecycle = (
        state.get("lifecycle") if isinstance(state.get("lifecycle"), dict) else {}
    )
    envelope = envelope or {}
    aws_execution_projection = dict(aws_execution or {})
    deployment_sequence_projection = dict(deployment_sequence or {})
    teardown_sequence_projection = dict(teardown_sequence or {})
    adr_rationale_projection = dict(adr_rationale or empty_adr_rationale())
    aws_sequence_conflict = aws_deployment_teardown_sequence_conflict(
        deployment_sequence_projection, teardown_sequence_projection
    )
    if aws_sequence_conflict:
        if not any(
            item.code == "AWS_DEPLOYMENT_TEARDOWN_CONFLICT" for item in ctx.diagnostics
        ):
            ctx.error(
                "AWS_DEPLOYMENT_TEARDOWN_CONFLICT",
                "Open deployment and teardown journal epochs cannot coexist; close one sequence before continuing",
                VERIFY_FILE,
            )
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
    lifecycle_intent_projection = dict(
        aws_lifecycle_intent_record
        or {
            "value": "NONE",
            "source": "NONE",
            "recorded_at": "NONE",
            "provenance_status": "CURRENT",
            "authorizes_aws_access": False,
            "authorizes_mutation": False,
        }
    )
    residual_disposition_projection = derive_aws_residual_disposition(
        lifecycle_intent_projection, teardown_sequence_projection
    )
    aws_progress_state = (
        str(aws_execution_projection.get("progress_state"))
        if aws_execution_projection.get("active") is True
        else None
    )
    if design_contract is None:
        design_contract = DesignContract(
            design_revision=(
                prd_fields.get("design_revision") or lifecycle.get("design_revision")
            )
        )
    if coverage_contract is None:
        coverage_contract = CoverageContract()
    if intake_contract is None:
        intake_contract = IntakeFoundationContract()
    if requirements_contract is None:
        requirements_contract = RequirementsContract()
    if ctx.template_source:
        classification = "TEMPLATE_SOURCE"
    elif setup.get("status") in {
        "UNCONFIGURED_TEMPLATE",
        "{{SETUP_STATUS}}",
    }:
        classification = "UNCONFIGURED_TEMPLATE"
    elif project.get("mode") == "brownfield":
        classification = "ACTIVE_BROWNFIELD"
    else:
        classification = "ACTIVE_GREENFIELD"
    if ctx.has_errors:
        status = "BLOCKED"
    elif lifecycle_state == "INTAKE_REQUIRED":
        status = "READY"
    else:
        status = "RESUME"
    lane = project.get("aws_lane")
    aws_access = {
        None: "NOT_USED",
        "documentation-only": "DOCUMENTATION_ONLY",
        "read-only": "READ_ONLY",
        "fast-dev": "EXACT_AUTHORIZATION_REQUIRED",
        "explicit-gate": "EXACT_AUTHORIZATION_REQUIRED",
    }.get(lane, "NOT_USED")
    gate_a = prd_fields.get("gate_a") or lifecycle.get("gate_a") or "BLOCKED"
    gate_b = prd_fields.get("gate_b") or lifecycle.get("gate_b") or "BLOCKED"
    authority_bounds = authority_bounds or GateBAuthorityBounds()
    construction_write_input = construction_write_input or ConstructionWriteInput(
        has_errors=ctx.has_errors
    )
    resolved_owner_stage = (
        owner_stage_hint
        if owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}
        else _owner_stage_from_gates(gate_a, gate_b)
    )
    authority_state = _compose_authority_state(
        ctx,
        authority_bounds=authority_bounds,
        construction_write_input=construction_write_input,
        lane=lane,
        tasks=tasks,
        prd_fields=prd_fields,
        lifecycle=lifecycle,
        gate_b=gate_b,
        release_decision=release_decision,
        aws_execution=aws_execution_projection,
        deployment_sequence=deployment_sequence_projection,
        teardown_sequence=teardown_sequence_projection,
        lifecycle_intent=lifecycle_intent_projection,
        aws_progress_state=aws_progress_state,
        next_prompt=next_prompt,
        aws_sequence_conflict=aws_sequence_conflict,
    )
    construction_authorization = authority_state["construction_authorization"]
    aws_authorization = authority_state["aws_authorization"]
    write_authority = authority_state["write_authority"]
    deployment_journal_closure_authority = authority_state["deployment_closure"]
    teardown_journal_closure_authority = authority_state["teardown_closure"]
    aws_lifecycle_intent_write_authority = authority_state["lifecycle_write_authority"]
    external_authority = authority_state["external_authority"]
    aws_action_transition = authority_state["transition"]
    aws_mutation_authority_ready = authority_state["aws_mutation_authority_ready"]
    deployment_authority_restricted = authority_state["deployment_restricted"]
    teardown_authority_restricted = authority_state["teardown_restricted"]

    def _brief():
        return derive_owner_decision_brief(
            ctx.presentation_texts.get(PRD_FILE, ctx.texts.get(PRD_FILE, "")),
            prd_fields,
            intake_contract,
            requirements_contract,
            design_contract,
            envelope,
            has_errors=ctx.has_errors,
            enabled=classification not in {"TEMPLATE_SOURCE", "UNCONFIGURED_TEMPLATE"},
        )

    owner_decision_brief, owner_decision_inventory, owner_brief_issues = _brief()
    for code, message in owner_brief_issues:
        if code == "OWNER_BRIEF_SOURCE_STALE":
            ctx.warning(code, message, PRD_FILE)
        else:
            ctx.error(code, message, PRD_FILE)
    owner_answer_confirmation = derive_owner_answer_confirmation(
        ctx.texts.get(PRD_FILE, ""), intake_contract
    )
    ve = task_remediation_validation_evidence(ctx.texts.get(TASKS_FILE, ""), tasks)
    diagnostic_codes = [item.code for item in ctx.diagnostics]
    remediation = derive_remediation(
        ctx,
        classification=classification,
        gate_a=gate_a,
        gate_b=gate_b,
        envelope=envelope,
        tasks=tasks,
        requirements_revision=prd_fields.get("requirements_revision"),
        design_revision=prd_fields.get("design_revision"),
        owner_stage_hint=resolved_owner_stage,
        task_validation_evidence=ve,
    )
    interaction = derive_interaction(
        lifecycle_state,
        next_prompt,
        has_errors=ctx.has_errors,
        diagnostic_codes=diagnostic_codes,
        design_aws_core_ready=design_aws_core_ready,
        aws_execution_planning_ready=aws_execution_planning_ready,
        remediation=remediation,
        owner_stage_hint=resolved_owner_stage,
        aws_progress_state=aws_progress_state,
        aws_mutation_authority_ready=aws_mutation_authority_ready,
        aws_lane=lane,
        aws_read_authority_required=(
            external_authority.get("kind") == "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        ),
        req_aws_core_materiality=req_aws_core_materiality,
        req_aws_core_ready=req_aws_core_ready,
    )
    if (
        classification == "UNCONFIGURED_TEMPLATE"
        and remediation["next_action"]["action_kind"]
        == "COMPLETE_PREREQUISITE_CHECKLIST"
    ):
        interaction = derive_unconfigured_template_interaction(diagnostic_codes)
    diagram_remediation_required = (
        "DIAGRAM_PRESENTATION_STALE" in diagnostic_codes
        or design_contract.diagram_contract.status not in {"TEMPLATE", "CURRENT"}
    )

    restrictions = (deployment_authority_restricted, teardown_authority_restricted)

    def current_context_plan(restrictions: tuple[bool, bool]) -> dict[str, Any]:
        return derive_context_plan(
            interaction,
            tasks,
            coverage_contract,
            next_prompt=next_prompt,
            restricted_deployment_closure=restrictions[0],
            restricted_teardown_closure=restrictions[1],
            source_texts=ctx.texts,
            adr_rationale=adr_rationale_projection,
            requirements_contract=requirements_contract,
            design_contract=design_contract,
            diagram_remediation_required=diagram_remediation_required,
        )

    context_plan = current_context_plan(restrictions)
    context_issues = context_plan.pop("_resolution_issues", [])
    if context_issues:
        for issue in context_issues:
            issue_path = str(issue.get("path", ""))
            ctx.error(
                "CONTEXT_SOURCE_INVALID",
                str(issue.get("reason", "context source could not be resolved")),
                issue_path if issue_path != "NONE" else None,
            )
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
        status = "BLOCKED"
        construction_authorization = "NONE"
        aws_authorization = "NONE"
        write_authority = derive_write_authority(
            replace(construction_write_input, has_errors=ctx.has_errors), "NONE"
        )
        deployment_journal_closure_authority = (
            derive_deployment_journal_closure_authority(
                deployment_sequence_projection,
                next_prompt,
                restricted_closure=False,
            )
        )
        teardown_journal_closure_authority = derive_teardown_journal_closure_authority(
            teardown_sequence_projection,
            next_prompt,
            restricted_closure=False,
        )
        external_authority = derive_external_authority(
            AuthorityEvaluationInput(
                has_errors=ctx.has_errors,
                observed_at=ctx.observed_at,
                verify_text=ctx.texts.get(VERIFY_FILE, ""),
            ),
            authority_bounds,
            lane,
            "NONE",
            aws_progress_state=aws_progress_state,
            aws_action_phase=next_prompt,
            teardown_review=teardown_sequence_projection,
            deployment_sequence=deployment_sequence_projection,
            preflight=(
                aws_execution_projection.get("preflight")
                if isinstance(aws_execution_projection.get("preflight"), Mapping)
                else None
            ),
        )
        external_authority["request_match"] = derive_request_match(
            ctx, external_authority
        )
        aws_lifecycle_intent_write_authority = (
            derive_aws_lifecycle_intent_write_authority(
                LifecycleIntentWriteInput(
                    has_errors=ctx.has_errors,
                    tasks_terminal=tasks.terminal,
                    release_decision=release_decision,
                    deployment_status=clean_cell(
                        deployment_sequence_projection.get("status", "")
                    ),
                    deployment_boundary_settled=(
                        release_lifecycle_intent_boundary_is_settled(
                            release_decision, deployment_sequence_projection
                        )
                    ),
                    teardown_status=clean_cell(
                        teardown_sequence_projection.get("status", "")
                    ),
                    teardown_has_issues=bool(
                        teardown_sequence_projection.get("issues")
                    ),
                    external_authority_current=(
                        clean_cell(external_authority.get("validity", "")) == "CURRENT"
                    ),
                    intent_value=clean_cell(
                        lifecycle_intent_projection.get("value", "NONE")
                    ),
                )
            )
        )
        owner_decision_brief, owner_decision_inventory, _owner_brief_issues = _brief()
        diagnostic_codes = [item.code for item in ctx.diagnostics]
        remediation = derive_remediation(
            ctx,
            classification=classification,
            gate_a=gate_a,
            gate_b=gate_b,
            envelope=envelope,
            tasks=tasks,
            requirements_revision=prd_fields.get("requirements_revision"),
            design_revision=prd_fields.get("design_revision"),
            owner_stage_hint=resolved_owner_stage,
            task_validation_evidence=ve,
        )
        interaction = derive_interaction(
            lifecycle_state,
            next_prompt,
            has_errors=True,
            diagnostic_codes=diagnostic_codes,
            design_aws_core_ready=design_aws_core_ready,
            aws_execution_planning_ready=aws_execution_planning_ready,
            remediation=remediation,
            owner_stage_hint=resolved_owner_stage,
            aws_progress_state=aws_progress_state,
            aws_mutation_authority_ready=False,
            aws_lane=lane,
            aws_read_authority_required=False,
            req_aws_core_materiality=req_aws_core_materiality,
            req_aws_core_ready=req_aws_core_ready,
        )
        if (
            classification == "UNCONFIGURED_TEMPLATE"
            and remediation["next_action"]["action_kind"]
            == "COMPLETE_PREREQUISITE_CHECKLIST"
        ):
            interaction = derive_unconfigured_template_interaction(diagnostic_codes)
        context_plan = current_context_plan((False, False))
        context_plan.pop("_resolution_issues", None)
    summary_sources: dict[str, str] = {}
    for summary_path in DOCUMENT_SUMMARY_FILES:
        summary_text = ctx.presentation_texts.get(summary_path)
        if summary_text is None:
            safe_read_text(ctx, summary_path)
            summary_text = ctx.presentation_texts.get(summary_path)
        if summary_text is not None:
            summary_sources[summary_path] = summary_text
    summary_specifications = derive_document_summary_specifications(
        ctx,
        classification=classification,
        lifecycle_state=lifecycle_state,
        next_prompt=next_prompt,
        project=project,
        prd_fields=prd_fields,
        gate_a=gate_a,
        gate_b=gate_b,
        tasks=tasks,
        release_decision=release_decision,
        release_evidence_cutoff=release_evidence_cutoff,
        aws_authorization=aws_authorization,
        external_authority=external_authority,
        interaction=interaction,
        active_artifact=active_artifact,
        deployment_sequence=deployment_sequence_projection,
        teardown_sequence=teardown_sequence_projection,
        aws_core_usage=aws_core_usage or {},
        req_aws_core_materiality=req_aws_core_materiality,
        write_authority=write_authority,
        remediation=remediation,
    )
    document_summaries, summary_issues = project_document_summaries(
        summary_sources, summary_specifications
    )
    brief_was_ready = owner_decision_brief.get("status") == "READY"
    for issue in summary_issues:
        reporter = (
            ctx.warning
            if issue["code"] == "DOCUMENT_SUMMARY_STALE" and not brief_was_ready
            else ctx.error
        )
        reporter(
            str(issue["code"]),
            str(issue["message"]),
            str(issue["path"]),
        )
    if summary_issues and brief_was_ready:
        blocked_brief = dict(owner_decision_brief)
        blocked_brief["status"] = "BLOCKED"
        blocked_brief["formal_receipt_required"] = False
        owner_decision_brief, _ = finalize_owner_decision_brief(blocked_brief)
    if any(
        issue["code"] != "DOCUMENT_SUMMARY_STALE" or brief_was_ready
        for issue in summary_issues
    ):
        status = "BLOCKED"
        diagnostic_codes = [item.code for item in ctx.diagnostics]
        remediation = derive_remediation(
            ctx,
            classification=classification,
            gate_a=gate_a,
            gate_b=gate_b,
            envelope=envelope,
            tasks=tasks,
            requirements_revision=prd_fields.get("requirements_revision"),
            design_revision=prd_fields.get("design_revision"),
            owner_stage_hint=resolved_owner_stage,
            task_validation_evidence=ve,
        )
        interaction = derive_interaction(
            lifecycle_state,
            next_prompt,
            has_errors=True,
            diagnostic_codes=diagnostic_codes,
            design_aws_core_ready=design_aws_core_ready,
            aws_execution_planning_ready=aws_execution_planning_ready,
            remediation=remediation,
            owner_stage_hint=resolved_owner_stage,
            aws_progress_state=aws_progress_state,
            aws_mutation_authority_ready=aws_mutation_authority_ready,
            aws_lane=lane,
            aws_read_authority_required=(
                external_authority.get("kind") == "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
            ),
            req_aws_core_materiality=req_aws_core_materiality,
            req_aws_core_ready=req_aws_core_ready,
        )
        if (
            classification == "UNCONFIGURED_TEMPLATE"
            and remediation["next_action"]["action_kind"]
            == "COMPLETE_PREREQUISITE_CHECKLIST"
        ):
            interaction = derive_unconfigured_template_interaction(diagnostic_codes)
        context_plan = current_context_plan(restrictions)
        context_plan.pop("_resolution_issues", None)

    aws_mode_boundary = derive_aws_mode_boundary(
        lane,
        envelope,
        next_prompt,
        external_authority,
    )
    task_projection = {
        "total": tasks.total,
        "completed": len(tasks.done),
        "skipped": len(tasks.skipped),
        "blocked": len(tasks.blocked),
        "ready": len(tasks.ready),
        "in_progress": len(tasks.active),
        "ready_ids": tasks.ready,
        "active_ids": tasks.active,
        "blocked_ids": tasks.blocked,
        "requirement_coverage_complete": tasks.requirement_coverage_complete,
        "requirement_coverage": [
            tasks.requirement_coverage[requirement_id]
            for requirement_id in sorted(tasks.requirement_coverage)
        ],
        "missing_requirement_ids": tasks.missing_requirement_ids,
    }
    return EngineEvaluation(
        schema_version=2,
        package={
            "bootstrap_version": manifest.get(
                "bootstrap_version", state.get("bootstrap_version")
            )
        },
        status=status,
        classification=classification,
        ok=not ctx.has_errors,
        route={
            "lifecycle_state": lifecycle_state,
            "resume_safe": not ctx.has_errors,
            "next_prompt": next_prompt,
        },
        interaction=interaction,
        remediation=remediation,
        context_plan=context_plan,
        project={
            "name": project.get("name"),
            "region": project.get("region"),
            "cost_posture": project.get("cost_posture"),
            "mode": project.get("mode"),
            "delivery_profile": project.get("delivery_profile"),
        },
        git_baseline=ctx.git_baseline(),
        gates={"gate_a": gate_a, "gate_b": gate_b},
        define={
            "intake_foundation": intake_contract.to_dict(),
            "requirements_contract": requirements_contract.to_dict(),
            "coverage_plan": coverage_contract.to_dict(),
        },
        design={
            "design_contract": design_contract.to_dict(),
            "adr_rationale": adr_rationale_projection,
        },
        deliver={
            "evidence_state": release_decision,
            "release_evidence_cutoff": release_evidence_cutoff,
            "tasks": task_projection,
        },
        aws={
            "aws_access": aws_access,
            "aws_mode_boundary": aws_mode_boundary,
            "aws_core_evidence": {
                "aws_execution_planning": (
                    "READY" if aws_execution_planning_ready else "BLOCKED"
                ),
                "observed_usage": dict(aws_core_usage or {}),
            },
            "aws_lifecycle_intent": lifecycle_intent_projection,
            "aws_residual_disposition": residual_disposition_projection,
            "external_authority": external_authority,
            "hook_constraints": {
                "GitHub boundary": envelope.get("GitHub boundary", "NONE"),
                "GitHub repository, branch, and merge constraints": envelope.get(
                    "GitHub repository, branch, and merge constraints", "NONE"
                ),
            },
            "aws_action_transition": aws_action_transition,
            "aws_execution": aws_execution_projection,
            "aws_deployment": deployment_sequence_projection,
            "aws_teardown": teardown_sequence_projection,
        },
        authority={
            "authorizations": {
                "construction": construction_authorization,
                "aws": aws_authorization,
            },
            "write_authority": write_authority,
            "deployment_journal_closure_authority": (
                deployment_journal_closure_authority
            ),
            "teardown_journal_closure_authority": (teardown_journal_closure_authority),
            "aws_lifecycle_intent_write_authority": (
                aws_lifecycle_intent_write_authority
            ),
        },
        basis={
            "requirements_revision": prd_fields.get("requirements_revision"),
            "design_revision": prd_fields.get("design_revision"),
            "construction_authorization": prd_fields.get("construction_authorization"),
            "prd_snapshot_sha256": (
                "sha256:"
                + hashlib.sha256(
                    canonical_bytes_without_generated_summary(
                        ctx.presentation_texts[PRD_FILE]
                    )
                ).hexdigest()
                if PRD_FILE in ctx.presentation_texts
                else "NONE"
            ),
        },
        owner_decisions={
            "owner_decision_brief": owner_decision_brief,
            "owner_decision_inventory": owner_decision_inventory,
            "owner_answer_confirmation": owner_answer_confirmation,
        },
        document_summaries=document_summaries,
        diagnostics=tuple(
            item.to_dict(f"DGN-{index:04d}")
            for index, item in enumerate(ctx.diagnostics, start=1)
        ),
    )


def build_report(
    ctx: Context,
    lifecycle_state: str,
    next_prompt: str,
    prd_fields: dict[str, str],
    tasks: TaskSummary,
    **kwargs: Any,
) -> dict[str, Any]:
    """COMPATIBILITY: retain the historical report builder import surface."""

    return serialize_evaluation(
        build_evaluation(
            ctx,
            lifecycle_state,
            next_prompt,
            prd_fields,
            tasks,
            **kwargs,
        )
    )
