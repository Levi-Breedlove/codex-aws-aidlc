"""Stable Fastlane report, context-plan, and document-summary assembly.

Canonical inputs are immutable domain results and the bounded project observation.
Returns the version-2 Engine report and non-authoritative owner projections. Side
effects are prohibited; this module never reads new files, routes policy, writes
state, approves gates, or grants GitHub/AWS authority.
"""

from __future__ import annotations

import hashlib
import re
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
from .aws import (
    AWS_TEARDOWN_ATTEMPT_ID,
    AWS_TEARDOWN_TERMINAL_STATUSES,
    aws_deployment_teardown_sequence_conflict,
    derive_aws_residual_disposition,
)
from .core.contracts import contract_table_after_heading, table_after_heading
from .core.ids import clean_cell, explicit_value, validate_relative_path
from .define.models import (
    CoverageContract,
    IntakeFoundationContract,
    RequirementsContract,
)
from .define.requirements import authoritative_requirement_ids
from .design import (
    DIAGRAM_CONTRACT_HEADERS,
    DIAGRAM_CONTRACT_HEADING,
    DesignContract,
    required_diagram_kinds,
)
from .deliver import TaskSummary, inspect_task_blocks
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
    inspect_git_baseline,
    safe_read_text,
)
from .remediation import (
    _owner_stage_from_gates,
    derive_interaction,
    derive_remediation,
    derive_unconfigured_template_interaction,
)

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
) -> dict[str, Any]:
    """SAFETY: select an ephemeral, route-bounded canonical context packet."""

    stage = interaction.get("owner_stage")
    reason = interaction.get("route_reason_code")
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
    if stage == "DESIGN" and source_texts is not None:
        prd_source = source_texts.get(PRD_FILE)
        if isinstance(prd_source, str):
            try:
                diagram_table = contract_table_after_heading(
                    prd_source, DIAGRAM_CONTRACT_HEADING, DIAGRAM_CONTRACT_HEADERS
                )
            except ValueError:
                diagram_table = None
            required_kinds = required_diagram_kinds(
                prd_source,
                authoritative_requirement_ids(prd_source),
                coverage.work_kind,
            )
            if diagram_table is not None and any(
                row[1] in required_kinds and row[3] != "CURRENT"
                for row in diagram_table.rows
            ):
                on_demand_slices.append(
                    ".agents/skills/fastlane/references/diagram-patterns.md"
                )
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
    updated = next(
        (
            value
            for value in (
                cutoff if cutoff != "Not yet recorded" else "",
                checkpoint if checkpoint != "None" else "",
                design_id,
                requirements_id,
            )
            if value
        ),
        "Current canonical records",
    )

    observed_ids: set[str] = set()
    failed_ids: set[str] = set()
    for line in verify_text.splitlines():
        evidence_ids = re.findall(r"\b(?:AWS-)?EV-\d{4,}\b", line)
        if not evidence_ids:
            continue
        upper = line.upper()
        if any(status in upper for status in ("VERIFIED", "PASSED", "OBSERVED")):
            observed_ids.update(evidence_ids)
        if any(status in upper for status in ("FAILED", "STALE", "BLOCKED")):
            failed_ids.update(evidence_ids)

    local_observed = release_decision in {"READY_TO_DEPLOY", "RELEASE_VERIFIED"}
    deployment_status = clean_cell(deployment_sequence.get("status", "NOT_ACTIVE"))
    deployment_observed = deployment_status == "RECONCILED"
    requirements_approved = gate_a == "APPROVED_FOR_DESIGN"
    design_approved = gate_b == "APPROVED_FOR_CONSTRUCTION"
    guidance_ready = not any(
        item.code.startswith("AWS_CORE_") and item.severity == "ERROR"
        for item in ctx.diagnostics
    )
    # fmt: off
    claim_rows = (
        ("Requirements are approved", requirements_approved, ("Owner confirmed", requirements_id, "Does not approve construction"), ("Not yet observed", "None", "Gate A is not approved")),
        ("Technical design is approved", design_approved, ("Owner confirmed", design_id, "Does not authorize AWS account work"), ("Not yet observed", "None", "Gate B is not approved")),
        ("Current AWS guidance informed the plan", guidance_ready and not template_like, ("Source verified", "Current AWS Core evidence", "Source guidance is not deployment evidence"), ("Not yet observed", "None", "Source guidance is not deployment evidence")),
        ("Local release checks passed", local_observed, ("Locally observed", release_decision, "Local evidence does not prove AWS behavior"), ("Not yet observed", "None", "Local evidence does not prove AWS behavior")),
        ("Application is deployed", deployment_observed, ("Deployed observed", "Deployment reconciliation", "Bound to the observed environment"), ("Not authorized", "None", "No deployment evidence or authority")),
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

    task_progress = (
        f"{len(tasks.done)} of {tasks.total} tasks complete"
        if tasks.total
        else "No tasks generated"
    )
    bug_title = _summary_bullet(bugfix_text, "Title")
    bug_active = active_artifact == BUGFIX_FILE or explicit_value(bug_title)
    bugfix = {
        "status": "Active bounded defect" if bug_active else "No active bounded defect",
        "defect": _summary_value(bug_title, "None") if bug_active else "None",
        "impact": "Recorded in the defect contract" if bug_active else "None",
        "reproduction": "Pending evidence" if bug_active else "Not active",
        "root_cause": "Pending evidence" if bug_active else "Not active",
        "repair": "Not started" if bug_active else "Not active",
        "regression": "Pending evidence" if bug_active else "Not active",
        "architecture": "Not yet assessed" if bug_active else "None",
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
    account_access = external_authority.get(
        "validity"
    ) == "CURRENT" and external_authority.get("kind") in {
        "AWS_READ_ONLY",
        "AWS_DEPLOYMENT",
        "AWS_TEARDOWN",
        "FAST_DEV_GATE_B",
    }
    environment = _summary_value(
        runbook_boundary.get("Region and environment"),
        (
            f"Development in {project.get('region')}"
            if project.get("region")
            else "Development"
        ),
    )
    # fmt: off
    return build_summary_specifications({
        "template_like": template_like, "lifecycle_state": lifecycle_state, "next_prompt": next_prompt,
        "owner_stage": interaction.get("owner_stage"), "action_kind": interaction.get("action_kind"),
        "automatic_continuation_allowed": interaction.get("automatic_continuation_allowed"),
        "gate_a": gate_a, "gate_b": gate_b, "requirements_revision": requirements_id,
        "design_revision": design_id, "construction_authorization": authorization_id,
        "aws_authorization": aws_authorization, "aws_account_access_authorized": account_access,
        "updated": updated, "product_outcome": _summary_value(prd_card.get("Outcome"), "Not yet confirmed"),
        "release_boundary": _summary_value(prd_card.get("Scope"), "Not yet confirmed"),
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
            "unobserved": "Recovery and teardown" if deployment_observed else "AWS deployment, recovery, and teardown" if local_observed else "Local build, AWS deployment, recovery, and teardown",
            "cutoff": _summary_value(verify_scope.get("Evidence cutoff"), cutoff),
            "updated": cutoff if cutoff != "Not yet recorded" else updated, "claims": claims,
        },
        "operations": {
            "environment": environment,
            "deployment_state": "Deployment observed" if deployment_observed else "Not deployed" if deployment_status in {"", "NOT_ACTIVE", "NONE"} else deployment_status.replace("_", " ").title(),
            "authority": str(external_authority.get("kind", "None")).replace("_", " ").title() if account_access else "None",
            "safe_action": "Only the exact authorized AWS operation" if account_access else "Local validation only",
            "deployment_approval": "Authorized only for the current deployment" if account_access and external_authority.get("kind") in {"AWS_DEPLOYMENT", "FAST_DEV_GATE_B"} else "Not authorized",
            "teardown_approval": "Authorized only for the current teardown" if account_access and external_authority.get("kind") == "AWS_TEARDOWN" else "Not authorized",
            "recovery_state": "Not yet observed",
            "emergency_state": "Follow the current runbook and authority" if deployment_observed else "No deployed environment exists",
            "updated": updated,
        },
        "bugfix": bugfix,
    })


def build_report(
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
) -> dict[str, Any]:
    """SAFETY: assemble schema-2 output without changing canonical state."""

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
        "fast-dev": "AUTHORIZED_BOUNDARY_REQUIRED",
        "explicit-gate": "EXACT_AUTHORIZATION_REQUIRED",
    }.get(lane, "NOT_USED")
    gate_a = prd_fields.get("gate_a") or lifecycle.get("gate_a") or "BLOCKED"
    gate_b = prd_fields.get("gate_b") or lifecycle.get("gate_b") or "BLOCKED"
    resolved_owner_stage = (
        owner_stage_hint
        if owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}
        else _owner_stage_from_gates(gate_a, gate_b)
    )
    authorization_id = prd_fields.get("construction_authorization") or lifecycle.get(
        "construction_authorization"
    )
    gate_b_authorization = (
        authorization_id
        if not ctx.has_errors and gate_b == "APPROVED_FOR_CONSTRUCTION"
        else "NONE"
    )
    deployment_status = clean_cell(deployment_sequence_projection.get("status", ""))
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
    deployment_authority_restricted = bool(
        not ctx.has_errors
        and not deployment_sequence_projection.get("issues")
        and auditable_status
    )
    teardown_status = clean_cell(teardown_sequence_projection.get("status", ""))
    teardown_attempt_id = clean_cell(teardown_sequence_projection.get("attempt_id", ""))
    teardown_action_status = clean_cell(
        teardown_sequence_projection.get("action_status", "")
    )
    teardown_attempt_unreconciled = bool(
        AWS_TEARDOWN_ATTEMPT_ID.fullmatch(teardown_attempt_id)
        and teardown_action_status in {"STARTED", *AWS_TEARDOWN_TERMINAL_STATUSES}
        and teardown_status
        in {"ACTION_TERMINAL_REQUIRED", "POST_ACTION_REVIEW", "BLOCKED"}
    )
    teardown_authority_restricted = bool(teardown_attempt_unreconciled)
    restricted_construction_authorization = (
        "NONE"
        if deployment_authority_restricted or teardown_authority_restricted
        else gate_b_authorization
    )
    aws_authorization = "NONE"
    deployment_journal_closure_authority = derive_deployment_journal_closure_authority(
        deployment_sequence_projection,
        next_prompt,
        restricted_closure=deployment_authority_restricted,
    )
    teardown_journal_closure_authority = derive_teardown_journal_closure_authority(
        teardown_sequence_projection,
        next_prompt,
        restricted_closure=teardown_authority_restricted,
    )
    external_authority = derive_external_authority(
        ctx,
        envelope,
        lane,
        restricted_construction_authorization,
        cost_posture=str(project.get("cost_posture", "")),
        aws_progress_state=aws_progress_state,
        active_artifact=active_artifact,
        aws_action_phase=next_prompt,
        teardown_review=teardown_sequence_projection,
        deployment_sequence=deployment_sequence_projection,
        preflight=(
            aws_execution_projection.get("preflight")
            if isinstance(aws_execution_projection.get("preflight"), Mapping)
            else None
        ),
    )
    aws_lifecycle_intent_write_authority = derive_aws_lifecycle_intent_write_authority(
        ctx,
        tasks,
        release_decision,
        deployment_sequence_projection,
        teardown_sequence_projection,
        external_authority,
        lifecycle_intent=lifecycle_intent_projection,
    )
    construction_authorization = (
        "NONE"
        if aws_lifecycle_intent_write_authority.get("valid") is True
        else restricted_construction_authorization
    )
    write_authority = derive_write_authority(
        ctx, envelope, tasks, construction_authorization
    )
    if external_authority.get("validity") == "CURRENT" and external_authority.get(
        "kind"
    ) in {"AWS_READ_ONLY", "AWS_DEPLOYMENT", "AWS_TEARDOWN", "FAST_DEV_GATE_B"}:
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
            ctx,
            envelope,
            lane,
            gate_b_authorization,
            cost_posture=str(project.get("cost_posture", "")),
            aws_progress_state=aws_progress_state,
            active_artifact=active_artifact,
            aws_action_phase="AWS-20",
            teardown_review=teardown_sequence_projection,
            deployment_sequence={},
            preflight=(
                aws_execution_projection.get("preflight")
                if isinstance(aws_execution_projection.get("preflight"), Mapping)
                else None
            ),
        )
        transition_sequence = deployment_sequence_projection
        transition_kind = clean_cell(transition_authority.get("kind", ""))
        transition_authorization_field = "deployment_authorization"
        transition_receipt_field = "deployment_receipt_digest"
    elif not aws_sequence_conflict and teardown_status == "ACTION_TERMINAL_REQUIRED":
        transition_review = {
            **teardown_sequence_projection,
            "status": "READY_FOR_TEARDOWN",
            "evidence_id": teardown_sequence_projection.get(
                "ready_evidence_id", "NONE"
            ),
        }
        transition_authority = derive_external_authority(
            ctx,
            envelope,
            lane,
            gate_b_authorization,
            cost_posture=str(project.get("cost_posture", "")),
            aws_progress_state=aws_progress_state,
            active_artifact=active_artifact,
            aws_action_phase="AWS-50",
            teardown_review=transition_review,
            deployment_sequence=deployment_sequence_projection,
            preflight=(
                aws_execution_projection.get("preflight")
                if isinstance(aws_execution_projection.get("preflight"), Mapping)
                else None
            ),
        )
        transition_sequence = teardown_sequence_projection
        transition_kind = "AWS_TEARDOWN"
        transition_authorization_field = "teardown_authorization"
        transition_receipt_field = "teardown_receipt_digest"
    transition_request_match = (
        derive_request_match(ctx, transition_authority)
        if transition_kind != "NONE"
        else None
    )
    aws_action_transition = _aws_action_transition_projection(
        transition_request_match,
        transition_sequence,
        authority_kind=transition_kind,
        authorization_field=transition_authorization_field,
        receipt_digest_field=transition_receipt_field,
    )
    (owner_decision_brief, owner_decision_inventory, owner_brief_issues) = (
        derive_owner_decision_brief(
            ctx.texts.get(PRD_FILE, ""),
            prd_fields,
            intake_contract,
            requirements_contract,
            design_contract,
            envelope,
            has_errors=ctx.has_errors,
            enabled=classification not in {"TEMPLATE_SOURCE", "UNCONFIGURED_TEMPLATE"},
        )
    )
    for code, message in owner_brief_issues:
        if code == "OWNER_BRIEF_SOURCE_STALE":
            ctx.warning(code, message, PRD_FILE)
        else:
            ctx.error(code, message, PRD_FILE)
    owner_answer_confirmation = derive_owner_answer_confirmation(
        ctx.texts.get(PRD_FILE, ""), intake_contract
    )
    diagnostic_codes = [item.code for item in ctx.diagnostics]
    aws_mutation_authority_ready = external_authority.get(
        "validity"
    ) == "CURRENT" and external_authority.get("kind") in {
        "AWS_DEPLOYMENT",
        "AWS_TEARDOWN",
        "FAST_DEV_GATE_B",
    }
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
    context_plan = derive_context_plan(
        interaction,
        tasks,
        coverage_contract,
        next_prompt=next_prompt,
        restricted_deployment_closure=deployment_authority_restricted,
        restricted_teardown_closure=teardown_authority_restricted,
        source_texts=ctx.texts,
        adr_rationale=adr_rationale_projection,
    )
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
        write_authority = derive_write_authority(ctx, envelope, tasks, "NONE")
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
            ctx,
            envelope,
            lane,
            "NONE",
            cost_posture=str(project.get("cost_posture", "")),
            aws_progress_state=aws_progress_state,
            active_artifact=active_artifact,
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
                ctx,
                tasks,
                release_decision,
                deployment_sequence_projection,
                teardown_sequence_projection,
                external_authority,
                lifecycle_intent=lifecycle_intent_projection,
            )
        )
        (owner_decision_brief, owner_decision_inventory, _owner_brief_issues) = (
            derive_owner_decision_brief(
                ctx.texts.get(PRD_FILE, ""),
                prd_fields,
                intake_contract,
                requirements_contract,
                design_contract,
                envelope,
                has_errors=ctx.has_errors,
                enabled=classification
                not in {"TEMPLATE_SOURCE", "UNCONFIGURED_TEMPLATE"},
            )
        )
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
        context_plan = derive_context_plan(
            interaction,
            tasks,
            coverage_contract,
            next_prompt=next_prompt,
            restricted_deployment_closure=False,
            restricted_teardown_closure=False,
            source_texts=ctx.texts,
            adr_rationale=adr_rationale_projection,
        )
        context_plan.pop("_resolution_issues", None)
    summary_sources: dict[str, str] = {}
    for summary_path in DOCUMENT_SUMMARY_FILES:
        summary_text = ctx.presentation_texts.get(summary_path)
        if summary_text is None:
            safe_read_text(ctx, summary_path)
            summary_text = ctx.presentation_texts.get(summary_path)
        if summary_text is not None:
            summary_sources[summary_path] = summary_text
    # fmt: off
    summary_specifications = derive_document_summary_specifications(ctx, classification=classification, lifecycle_state=lifecycle_state, next_prompt=next_prompt, project=project, prd_fields=prd_fields, gate_a=gate_a, gate_b=gate_b, tasks=tasks, release_decision=release_decision, release_evidence_cutoff=release_evidence_cutoff, aws_authorization=aws_authorization, external_authority=external_authority, interaction=interaction, active_artifact=active_artifact, deployment_sequence=deployment_sequence_projection)
    # fmt: on
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
        context_plan = derive_context_plan(
            interaction,
            tasks,
            coverage_contract,
            next_prompt=next_prompt,
            restricted_deployment_closure=deployment_authority_restricted,
            restricted_teardown_closure=teardown_authority_restricted,
            source_texts=ctx.texts,
            adr_rationale=adr_rationale_projection,
        )
        context_plan.pop("_resolution_issues", None)

    aws_mode_boundary = derive_aws_mode_boundary(
        lane,
        envelope,
        next_prompt,
        external_authority,
    )
    return {
        "schema_version": 2,
        "bootstrap_version": manifest.get(
            "bootstrap_version", state.get("bootstrap_version")
        ),
        "status": status,
        "classification": classification,
        "ok": not ctx.has_errors,
        "lifecycle_state": lifecycle_state,
        "resume_safe": not ctx.has_errors,
        "next_prompt": next_prompt,
        "interaction": interaction,
        "remediation": remediation,
        "context_plan": context_plan,
        "project": {
            "name": project.get("name"),
            "region": project.get("region"),
            "cost_posture": project.get("cost_posture"),
            "mode": project.get("mode"),
            "delivery_profile": project.get("delivery_profile"),
        },
        "git_baseline": inspect_git_baseline(ctx.root),
        "aws_access": aws_access,
        "aws_mode_boundary": aws_mode_boundary,
        "gates": {
            "gate_a": gate_a,
            "gate_b": gate_b,
        },
        "evidence_state": release_decision,
        "release_evidence_cutoff": release_evidence_cutoff,
        "aws_core_evidence": {
            "aws_execution_planning": (
                "READY" if aws_execution_planning_ready else "BLOCKED"
            ),
            "observed_usage": dict(aws_core_usage or {}),
        },
        "authorizations": {
            "construction": construction_authorization,
            "aws": aws_authorization,
        },
        "write_authority": write_authority,
        "deployment_journal_closure_authority": (deployment_journal_closure_authority),
        "teardown_journal_closure_authority": (teardown_journal_closure_authority),
        "aws_lifecycle_intent": lifecycle_intent_projection,
        "aws_residual_disposition": residual_disposition_projection,
        "aws_lifecycle_intent_write_authority": aws_lifecycle_intent_write_authority,
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
        "basis": {
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
        "document_summaries": document_summaries,
        "owner_decision_brief": owner_decision_brief,
        "owner_decision_inventory": owner_decision_inventory,
        "owner_answer_confirmation": owner_answer_confirmation,
        "intake_foundation": intake_contract.to_dict(),
        "requirements_contract": requirements_contract.to_dict(),
        "coverage_plan": coverage_contract.to_dict(),
        "design_contract": design_contract.to_dict(),
        "adr_rationale": adr_rationale_projection,
        "tasks": {
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
        },
        "diagnostics": [
            item.to_dict(f"DGN-{index:04d}")
            for index, item in enumerate(ctx.diagnostics, start=1)
        ],
    }
