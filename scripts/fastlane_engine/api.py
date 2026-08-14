"""Supported read-only entry points for the Fastlane Engine foundation.

Inputs are repository-relative paths and caller-supplied observation policy.
Outputs are immutable snapshots, Define, Design, Delivery, or AWS projections.
Snapshot capture may read bounded regular files; domain evaluators consume
caller-supplied text and perform no I/O. The API never writes, runs Git, invokes
AWS, approves a gate, or grants authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
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
    path_boundaries_overlap,
    path_boundary_contains,
    table_after_heading,
)
from .core.ids import clean_cell, validate_relative_path
from .core.snapshot import ObservationError, ProjectSnapshot, SnapshotObserver
from .define import (
    IntakeFoundationContract,
    RequirementsContract,
    SOURCE_BRIEF_MAX_BYTES,
    blocked_source_assist_preview,
    derive_change_impact_contract,
    derive_coverage_contract,
    derive_intake_foundation_contract,
    derive_req_aws_materiality,
    derive_requirements_contract,
    derive_source_assist_preview,
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
    HarnessEvidenceRow,
    HarnessExecutionRow,
    InspectedTask,
    PropertyExecutionRow,
    TaskGraphValidationResult,
    TaskSnapshot,
    TaskWaiver,
    compute_task_waves,
    derive_ready_task_ids,
    derive_task_requirement_coverage,
    inspect_task_blocks,
    parse_checkpoint_rows as parse_delivery_checkpoint_rows,
    parse_harness_projection_rows,
    parse_harness_evidence,
    parse_property_execution_rows,
    parse_task_external_targets as parse_delivery_task_external_targets,
    parse_task_snapshot,
    parse_task_write_boundary as parse_delivery_task_write_boundary,
    parse_task_waivers,
    parse_property_test_evidence,
    parse_task_completion_evidence,
    task_requirement_evidence_dispositions,
    task_requirement_rules,
    task_dependency_satisfied as delivery_task_dependency_satisfied,
    validate_done_property_evidence,
    validate_gate_b_execution_binding,
    validate_done_harness_evidence,
    validate_harness_projections,
    validate_task_graph,
    validate_task_completion_evidence,
    validate_task_property_projection,
    validate_task_snapshot,
)
from .evaluation import EngineEvaluation

ARCHITECTURE_DIAGRAM_SKILL_IDENTITY = {
    "name": "aws-architecture-diagrams",
    "version": "1.3.1",
    "contract_id": "aws-architecture-diagrams/v1.3",
    "source_model_schema_version": 2,
    "tree_sha256": "sha256:3482ba7a5cb5f8b9db12f4eb25700f257e04f5fedb50eb2c8d64d5ff00062977",
    "release_sha256": "sha256:ffa17e5905bfb83ce7b302894760745b192a625eafa7ea7261613df9a0134d4",
}
ARCHITECTURE_BOARD_OWNER_REQUEST = "Generate the planned AWS architecture board."

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


_BOARD_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_BOARD_RECORDS = {
    "DIAGRAM-0001": ("SYSTEM_CONTEXT", "proposed-system-at-a-glance"),
    "DIAGRAM-0008": ("AWS_IMPLEMENTATION", "aws-implementation-at-a-glance"),
}


def _architecture_board_record(
    diagrams: Mapping[str, Any], diagram_id: str
) -> dict[str, Any] | None:
    rows = [
        row
        for row in diagrams.get("records", [])
        if isinstance(row, Mapping) and row.get("diagram_id") == diagram_id
    ]
    if len(rows) != 1:
        return None
    row = rows[0]
    kind, anchor = _BOARD_RECORDS[diagram_id]
    valid = (
        row.get("kind") == kind
        and row.get("applicability") == "REQUIRED"
        and row.get("status") == "CURRENT"
        and row.get("anchor") == anchor
        and isinstance(row.get("relationships"), list)
        and bool(row["relationships"])
        and all(isinstance(edge, Mapping) for edge in row["relationships"])
        and all(
            _BOARD_SHA256.fullmatch(str(row.get(key, "")))
            for key in ("semantic_sha256", "rendered_sha256")
        )
    )
    return dict(row) if valid else None


def _architecture_board_report_current(
    report: Mapping[str, Any], parts: tuple[Any, ...]
) -> bool:
    if not all(isinstance(item, Mapping) for item in parts):
        return False
    gates, design, project, diagrams, authority, auth, external = parts
    return bool(
        report.get("schema_version") == 2
        and report.get("ok") is True
        and gates.get("gate_a") == "APPROVED_FOR_DESIGN"
        and gates.get("gate_b") == "APPROVED_FOR_CONSTRUCTION"
        and design.get("schema_version") == project.get("schema_version") == 7
        and design.get("status") == project.get("status") == "READY"
        and not any(project.get(f"grandfathered_v{version}") for version in (4, 5, 6))
        and diagrams.get("status") == "CURRENT"
        and diagrams.get("grandfathered_schema5") is False
        and authority.get("valid") is True
        and authority.get("active_task") == "NONE"
        and authority.get("authorization_id") == auth.get("construction")
        and auth.get("construction") != "NONE"
        and auth.get("aws") == "NONE"
        and external.get("kind") == external.get("validity") == "NONE"
    )


def _architecture_board_conflict(
    diagrams: Mapping[str, Any] | None,
    primary: Mapping[str, Any] | None,
    cross_check: Mapping[str, Any] | None,
) -> bool:
    if diagrams is None or primary is None or cross_check is None:
        return False

    primary_edges = {(e["from_id"], e["to_id"]) for e in primary["relationships"]}
    cross_edges = {(e["from_id"], e["to_id"]) for e in cross_check["relationships"]}

    def reaches(source: str, target: str) -> bool:
        frontier = {right for left, right in primary_edges if left == source}
        for _ in primary.get("referenced_ids", []):
            frontier |= {right for left, right in primary_edges if left in frontier}
        return target in frontier

    basis = diagrams.get("architecture_basis_id")
    return bool(
        basis not in primary.get("basis_ids", [])
        or basis not in cross_check.get("basis_ids", [])
        or not set(cross_check.get("referenced_ids", [])).issubset(
            primary.get("referenced_ids", [])
        )
        or any(not reaches(source, target) for source, target in cross_edges)
    )


def _architecture_board_output(
    design: Mapping[str, Any] | None,
    primary: Mapping[str, Any] | None,
    authority: Mapping[str, Any] | None,
) -> tuple[str | None, str | None, bool]:
    revision = str(design.get("design_revision", "")) if design else ""
    semantic = str(primary.get("semantic_sha256", "")) if primary else ""
    root = (
        f"dist/architecture/{revision}-{semantic[7:]}"
        if re.fullmatch(r"DES-\d{4,}", revision) and _BOARD_SHA256.fullmatch(semantic)
        else None
    )
    boundary = f"{root}/**" if root else None
    roots = authority.get("approved_write_roots", []) if authority else []
    blocked = [
        *(authority.get("exclusions", []) if authority else []),
        *(authority.get("protected_paths", []) if authority else []),
    ]
    authorized = bool(
        boundary
        and all(isinstance(path, str) for path in [*roots, *blocked])
        and any(path_boundary_contains(path, boundary) for path in roots)
        and not any(path_boundaries_overlap(path, boundary) for path in blocked)
    )
    return root, boundary, authorized


def derive_architecture_board_handoff(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the request-scoped planned-board capability; never infer a plugin."""

    gates, design = report.get("gates"), report.get("design_contract")
    project = design.get("project_contract") if isinstance(design, Mapping) else None
    diagrams = design.get("diagram_contract") if isinstance(design, Mapping) else None
    authority, auth = report.get("write_authority"), report.get("authorizations")
    external = report.get("external_authority")
    parts = (gates, design, project, diagrams, authority, auth, external)
    current = _architecture_board_report_current(report, parts)
    if isinstance(diagrams, Mapping):
        primary = _architecture_board_record(diagrams, "DIAGRAM-0001")
        cross_check = _architecture_board_record(diagrams, "DIAGRAM-0008")
    else:
        primary = cross_check = None
    conflict = _architecture_board_conflict(diagrams, primary, cross_check)
    root, boundary, authorized = _architecture_board_output(
        design if isinstance(design, Mapping) else None,
        primary,
        authority if isinstance(authority, Mapping) else None,
    )
    issues = [
        *([] if current else ["CURRENT_GATE_B_REQUIRED"]),
        *([] if primary else ["SYSTEM_CONTEXT_DIAGRAM_REQUIRED"]),
        *([] if cross_check else ["AWS_IMPLEMENTATION_DIAGRAM_REQUIRED"]),
        *(["DIAGRAM_CROSS_CHECK_CONFLICT"] if conflict else []),
        *([] if root else ["DIAGRAM_OUTPUT_IDENTITY_INVALID"]),
        *([] if authorized else ["DIAGRAM_OUTPUT_NOT_AUTHORIZED"]),
    ]
    status = (
        "SEMANTIC_CONFLICT" if conflict else ("ELIGIBLE", "INELIGIBLE")[bool(issues)]
    )
    return {
        "status": status,
        "eligible": not issues,
        "issues": issues,
        "source_path": "docs/project/PRD.md",
        "source": primary,
        "cross_check": cross_check,
        "output_root": root,
        "failure_route": "DESIGN-10" if conflict else None,
        "aws_authority": "NONE",
        "external_authority": "NONE",
    }


def architecture_board_mermaid_source(text: str, handoff: Mapping[str, Any]) -> str:
    from .design.diagrams import _canonical_mermaid_block

    source = handoff.get("source")
    if handoff.get("eligible") is not True or not isinstance(source, Mapping):
        raise ValueError("architecture board handoff is not eligible")
    rendered_bytes, rendered = _canonical_mermaid_block(text, str(source.get("anchor")))
    observed = "sha256:" + hashlib.sha256(rendered_bytes).hexdigest()
    if observed != source.get("rendered_sha256"):
        raise ValueError("approved Mermaid presentation digest changed")
    return rendered.removeprefix("```mermaid\n").removesuffix("```\n")


def _architecture_board_request_manifest(
    handoff: Mapping[str, Any],
    design: Mapping[str, Any],
    project: Mapping[str, Any],
    construction: str,
    mermaid_path: str,
    mermaid_sha256: str,
    source_model_path: str,
) -> dict[str, Any]:
    source, cross_check = handoff["source"], handoff["cross_check"]
    output_root = str(handoff["output_root"])
    return {
        "schema_version": 1,
        "kind": "FASTLANE_ARCHITECTURE_BOARD_REQUEST",
        "request": ARCHITECTURE_BOARD_OWNER_REQUEST,
        "status": "CURRENT",
        "architecture_status": "PLANNED",
        "project": {"name": project.get("name"), "region": project.get("region")},
        "lifecycle": {"route": "TASK-10", "resume_route": "TASK-10"},
        "authority": {
            "construction_authorization_id": construction,
            "permitted_output_boundary": f"{output_root}/**",
            "aws": "NONE",
            "external": "NONE",
        },
        "design": {
            "revision": design.get("design_revision"),
            "canonical_sha256": design.get("canonical_sha256"),
        },
        "approved_mermaid": {
            "prd_path": handoff.get("source_path"),
            "anchor": source.get("anchor"),
            "diagram_id": source.get("diagram_id"),
            "semantic_sha256": source.get("semantic_sha256"),
            "rendered_sha256": source.get("rendered_sha256"),
            "target_path": mermaid_path,
            "sha256": mermaid_sha256,
        },
        "mandatory_cross_check": {
            "diagram_id": cross_check.get("diagram_id"),
            "semantic_sha256": cross_check.get("semantic_sha256"),
            "rendered_sha256": cross_check.get("rendered_sha256"),
        },
        "source_model": {
            "mode": "NEW_DERIVATION",
            "state": "PENDING_DERIVATION",
            "schema_version": 2,
            "target_path": source_model_path,
            "target_must_be_absent": True,
        },
        "skill": dict(ARCHITECTURE_DIAGRAM_SKILL_IDENTITY),
        "output": {
            "directory": output_root,
            "required": [
                "architecture-board.drawio",
                "architecture-board.svg",
                "architecture-board.png",
                "architecture-board.md",
                "architecture-board-manifest.json",
                "architecture-board-validation.json",
                "architecture-board-render.json",
                "visual-review-receipt.json",
                "qa-tiles/qa-tiles-manifest.json",
            ],
        },
    }


def derive_architecture_board_request_packet(
    report: Mapping[str, Any],
    prd_text: str,
    skill_identity: Mapping[str, Any],
    *,
    owner_request: str,
    source_model_target_exists: bool,
) -> dict[str, Any]:
    """Derive one local DIAGRAM-10 request packet without writing project state."""

    expected_identity = {
        **ARCHITECTURE_DIAGRAM_SKILL_IDENTITY,
        "valid": True,
        "issues": [],
    }
    if owner_request != ARCHITECTURE_BOARD_OWNER_REQUEST:
        raise ValueError("architecture board requires the exact owner request")
    if dict(skill_identity) != expected_identity:
        raise ValueError("architecture diagram skill identity is not current")
    if source_model_target_exists is not False:
        raise ValueError("NEW_DERIVATION requires an absent source-model target")

    handoff = derive_architecture_board_handoff(report)
    interaction = report.get("interaction")
    if (
        handoff.get("eligible") is not True
        or report.get("next_prompt") != "TASK-10"
        or not isinstance(interaction, Mapping)
        or interaction.get("owner_action_required") is not False
        or interaction.get("automatic_continuation_allowed") is not True
    ):
        raise ValueError("architecture board request is not currently eligible")

    design = report.get("design_contract")
    authorizations = report.get("authorizations")
    project = report.get("project")
    source, cross_check = handoff.get("source"), handoff.get("cross_check")
    if not all(
        isinstance(item, Mapping)
        for item in (design, authorizations, project, source, cross_check)
    ):
        raise ValueError("architecture board request evidence is malformed")
    if any(
        not isinstance(project.get(field), str) or not project[field].strip()
        for field in ("name", "region")
    ):
        raise ValueError("architecture board project identity is malformed")
    construction = str(authorizations.get("construction", ""))
    if not _BOARD_SHA256.fullmatch(
        str(design.get("canonical_sha256", ""))
    ) or not re.fullmatch(r"AUTH-\d{4,}", construction):
        raise ValueError("architecture board authority binding is malformed")

    output_root = str(handoff["output_root"])
    manifest_path = f"{output_root}/architecture-board-task-manifest.json"
    mermaid_path = f"{output_root}/architecture-source.mmd"
    source_model_path = f"{output_root}/source-model.json"
    mermaid_text = architecture_board_mermaid_source(prd_text, handoff)
    mermaid_sha256 = (
        "sha256:" + hashlib.sha256(mermaid_text.encode("utf-8")).hexdigest()
    )
    manifest = _architecture_board_request_manifest(
        handoff,
        design,
        project,
        construction,
        mermaid_path,
        mermaid_sha256,
        source_model_path,
    )
    return {
        "status": "READY",
        "manifest_path": manifest_path,
        "manifest": manifest,
        "manifest_text": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        "mermaid_path": mermaid_path,
        "mermaid_text": mermaid_text,
        "source_model_path": source_model_path,
        "resume_route": "TASK-10",
        "aws_authority": "NONE",
        "external_authority": "NONE",
    }


def preview_source_brief(root: Path, source_path: str) -> dict[str, Any]:
    """Return one bounded non-authoritative source-assisted Define preview.

    SAFETY: the source is observed once as a repository-relative regular UTF-8
    file. The preview performs no canonical write, lifecycle transition, gate
    approval, architecture selection, or authority derivation.
    """

    observed_at = datetime.now(timezone.utc)
    display_path = (
        source_path
        if validate_relative_path(source_path) is not None
        else "UNSAFE_OR_UNAVAILABLE_SOURCE"
    )
    observer = SnapshotObserver(
        root,
        observed_at=observed_at,
        max_files=1,
        max_file_bytes=SOURCE_BRIEF_MAX_BYTES,
        max_source_bytes=SOURCE_BRIEF_MAX_BYTES,
    )
    try:
        source = observer.observe_text(source_path, markdown=True)
    except ObservationError as exc:
        issue = {
            "MANIFEST_UNSAFE_PATH": (
                "SOURCE_BRIEF_PATH_UNSAFE",
                "The source path must be a safe repository-relative POSIX path.",
            ),
            "REQUIRED_FILE_SYMLINK": (
                "SOURCE_BRIEF_SYMLINK",
                "The source path may not contain or resolve through a symbolic link.",
            ),
            "REQUIRED_FILE_MISSING": (
                "SOURCE_BRIEF_MISSING",
                "The source brief does not exist at the supplied "
                "repository-relative path.",
            ),
            "REQUIRED_FILE_NOT_REGULAR": (
                "SOURCE_BRIEF_NOT_REGULAR",
                "The supplied source path is not a regular file.",
            ),
            "REQUIRED_FILE_TOO_LARGE": (
                "SOURCE_BRIEF_TOO_LARGE",
                f"The source brief exceeds the {SOURCE_BRIEF_MAX_BYTES}-byte limit.",
            ),
            "PROJECT_SOURCE_LIMIT": (
                "SOURCE_BRIEF_TOO_LARGE",
                f"The source brief exceeds the {SOURCE_BRIEF_MAX_BYTES}-byte limit.",
            ),
            "REQUIRED_FILE_UNREADABLE": (
                "SOURCE_BRIEF_UNREADABLE",
                "The source brief is not readable UTF-8 text.",
            ),
        }.get(
            exc.code,
            (
                "SOURCE_BRIEF_OBSERVATION_FAILED",
                "Fastlane could not safely observe the supplied source brief.",
            ),
        )
        return blocked_source_assist_preview(
            display_path,
            observed_at,
            code=issue[0],
            message=issue[1] + " No canonical project record was changed.",
        )
    snapshot = observer.freeze()
    return derive_source_assist_preview(
        source_path,
        source.canonical_text or "",
        source.byte_sha256,
        snapshot.observed_at,
        markdown=snapshot.markdown.get(source_path),
    )


def prepare_source_brief_request(
    root: Path,
    source_path: str,
    json_output: bool,
    owner_input_mode_count: int,
) -> tuple[dict[str, Any], int]:
    """Prepare the source-preview payload and stable CLI exit status.

    Invalid mode combinations fail closed without observing the source. A
    successful result is still non-authoritative and grants no project action.
    """

    if owner_input_mode_count or not json_output:
        return (
            {
                "schema_version": 1,
                "status": "FAIL",
                "issues": [
                    {
                        "code": "SOURCE_BRIEF_USAGE",
                        "message": (
                            "Source-assisted Define requires --json and may not "
                            "be combined with an owner-input parser mode."
                        ),
                    }
                ],
            },
            1,
        )
    preview = preview_source_brief(root, source_path)
    return preview, 0 if preview["status"] == "READY_FOR_CONFIRMATION" else 2


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


def parse_task_contracts(text: str) -> tuple[InspectedTask, ...]:
    """Return the canonical ordered task records without observing or writing files."""

    return tuple(inspect_task_blocks(text))


def parse_task_execution_snapshot(text: str) -> TaskSnapshot:
    """Return the typed active execution snapshot from caller-supplied text."""

    return parse_task_snapshot(text)


def parse_task_write_boundary(value: str, task_id: str) -> list[str]:
    """Parse a task-facing write boundary through Delivery's shared grammar."""

    return parse_delivery_task_write_boundary(
        value,
        task_id,
        task_surface_compatibility=True,
    )


def parse_task_external_targets(value: str, task_id: str) -> list[str]:
    """Parse task-facing external targets through Delivery's shared grammar."""

    return parse_delivery_task_external_targets(
        value,
        task_id,
        task_surface_compatibility=True,
    )


def parse_task_dependency_waivers(text: str) -> dict[str, TaskWaiver]:
    """Return the canonical dependency-waiver registry from supplied text."""

    return parse_task_waivers(text)


def parse_task_property_projection(
    text: str,
    label: str,
) -> tuple[dict[str, PropertyExecutionRow], bool]:
    """Parse a task Validation property projection through Delivery."""

    return parse_property_execution_rows(text, label)


def parse_task_harness_projection(
    text: str,
    label: str,
) -> tuple[dict[str, HarnessExecutionRow], bool]:
    """Parse a task Validation Harness projection through Delivery."""

    return parse_harness_projection_rows(text, label)


def validate_task_property_contract(
    task: Any,
    technology_refs: Sequence[str],
    approved_property_execution: Mapping[str, PropertyExecutionRow] | None,
) -> list[str]:
    """Return task-facing property projection issues without mutation."""

    return validate_task_property_projection(
        task,
        technology_refs,
        approved_property_execution,
    )


def validate_task_harness_contracts(
    tasks: Sequence[Any],
    approved_harness: Mapping[str, HarnessExecutionRow] | None,
    *,
    current_plan: bool,
) -> list[str]:
    """Return Harness ownership/projection issues without mutation."""

    return validate_harness_projections(
        tasks,
        approved_harness,
        current_plan=current_plan,
    )


def validate_task_snapshot_contract(snapshot: TaskSnapshot) -> None:
    """Validate one typed execution snapshot without observing project files."""

    validate_task_snapshot(snapshot, task_surface_compatibility=True)


def task_dependency_is_satisfied(
    task: Any,
    dependency: Any,
    waivers: Mapping[str, TaskWaiver],
) -> bool:
    """Return whether one task dependency permits mutation now."""

    return delivery_task_dependency_satisfied(task, dependency, waivers)


def derive_task_ready_ids(
    tasks: Sequence[Any],
    waivers: Mapping[str, TaskWaiver] | None = None,
) -> tuple[str, ...]:
    """Return the shared ordered READY-task decision without mutation."""

    return derive_ready_task_ids(tasks, waivers)


def parse_task_checkpoint_records(text: str):
    """Return canonical checkpoint rows from caller-supplied TASKS text."""

    return tuple(parse_delivery_checkpoint_rows(text, task_surface_compatibility=True))


def parse_task_completion_records(text: str):
    """Return canonical completion evidence from caller-supplied VERIFY text."""

    return tuple(parse_task_completion_evidence(text, task_surface_compatibility=True))


def parse_task_harness_evidence(text: str) -> tuple[HarnessEvidenceRow, ...]:
    """Return canonical Harness evidence from caller-supplied VERIFY text."""

    return tuple(parse_harness_evidence(text))


def validate_task_done_completion_evidence(text: str, task: Any) -> None:
    """Validate task-facing DONE completion evidence without file access."""

    validate_task_completion_evidence(text, task)


def validate_task_done_harness_evidence(
    text: str,
    task: Any,
    snapshot: TaskSnapshot,
    approved_harness: Mapping[str, HarnessExecutionRow] | None,
) -> None:
    """Validate task-facing DONE Harness evidence without file access."""

    validate_done_harness_evidence(text, task, snapshot, approved_harness)


def validate_task_contracts(
    tasks: Sequence[Any],
    snapshot: TaskSnapshot | None = None,
    waivers: Mapping[str, TaskWaiver] | None = None,
    *,
    approved_contract: ApprovedTaskContract | None = None,
    technology_contract_available: bool | None = None,
    property_contract_available: bool | None = None,
    harness_contract_available: bool | None = None,
    task_surface_compatibility: bool = False,
) -> TaskGraphValidationResult:
    """SAFETY: derive one read-only task readiness and wave decision.

    This is the supported shared boundary for whole-project evaluation and the
    sole task mutator. It performs no observation, task claim, or state write.
    """

    return validate_task_graph(
        tasks,
        snapshot,
        waivers,
        approved_contract=approved_contract,
        technology_contract_available=technology_contract_available,
        property_contract_available=property_contract_available,
        harness_contract_available=harness_contract_available,
        task_surface_compatibility=task_surface_compatibility,
        policy=_delivery_validation_policy(),
    )


def compute_task_contract_waves(tasks: Sequence[Any]) -> dict[str, int]:
    """Return deterministic task waves using the same canonical dependency graph."""

    by_id = {task.task_id: task for task in tasks}
    return compute_task_waves(tasks, by_id)


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
    from .project_delivery import approved_delivery_contract_from_design

    delivery = approved_delivery_contract_from_design(design_contract)

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
    "ARCHITECTURE_BOARD_OWNER_REQUEST",
    "ARCHITECTURE_DIAGRAM_SKILL_IDENTITY",
    "DesignContract",
    "ApprovedDeliveryContract",
    "ApprovedSpikeContract",
    "ApprovedTaskContract",
    "AwsAuthorityPolicy",
    "AwsCoreEvidenceRow",
    "DELIVERY_VALIDATION_POLICY",
    "HarnessExecutionRow",
    "HarnessEvidenceRow",
    "PropertyExecutionRow",
    "TaskGraphValidationResult",
    "TaskSnapshot",
    "TaskWaiver",
    "ProjectSnapshot",
    "EngineEvaluation",
    "RequirementsContract",
    "capture_project_snapshot",
    "architecture_board_mermaid_source",
    "derive_architecture_board_request_packet",
    "evaluate_project",
    "inspect_project",
    "aws_core_phase_evidence_issues",
    "derive_change_impact_contract",
    "derive_architecture_board_handoff",
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
    "parse_task_contracts",
    "parse_task_checkpoint_records",
    "parse_task_completion_records",
    "parse_task_dependency_waivers",
    "parse_task_execution_snapshot",
    "parse_task_external_targets",
    "parse_task_harness_projection",
    "parse_task_harness_evidence",
    "parse_task_property_projection",
    "parse_task_write_boundary",
    "prepare_source_brief_request",
    "preview_source_brief",
    "compute_task_contract_waves",
    "derive_task_ready_ids",
    "task_dependency_is_satisfied",
    "validate_approved_property_evidence",
    "validate_task_execution_basis",
    "validate_task_contracts",
    "validate_task_harness_contracts",
    "validate_task_done_completion_evidence",
    "validate_task_done_harness_evidence",
    "validate_task_property_contract",
    "validate_task_snapshot_contract",
)
