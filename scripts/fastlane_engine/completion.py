"""Pure evidence-bound project completion projection without authority."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .aws.evidence import parse_deployment_reconciliation_evidence
from .core.contracts import table_after_heading
from .core.ids import clean_cell, explicit_value
from .deliver.evidence import (
    parse_task_completion_evidence,
    parse_verification_matrix,
)
from .deliver.release import (
    RELEASE_RECOVERY_OBSERVATION,
    derive_release_claim_projection,
)
from .deliver.tasks import inspect_task_blocks


_HIGHER_TARGET_DIAGNOSTIC_CODES = frozenset(
    {
        "AWS_DEPLOYMENT_EVIDENCE_INVALID",
        "AWS_DEPLOYMENT_TEARDOWN_CONFLICT",
        "AWS_PREFLIGHT_EVIDENCE_INVALID",
        "AWS_RESIDUAL_DISPOSITION_INVALID",
        "AWS_TEARDOWN_EVIDENCE_INVALID",
    }
)


def classify_local_evidence_ids(verify_text: str) -> tuple[list[str], list[str]]:
    """Classify exact local evidence IDs for claims and presentation facades."""

    passing: set[str] = set()
    failed: set[str] = set()
    try:
        task_rows = parse_task_completion_evidence(verify_text)
    except ValueError:
        task_rows = []
    for row in task_rows:
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
        if status in {"LOCAL_PASS", "VERIFIED"}:
            passing.add(evidence_id)
        elif status in {"FAILED", "STALE", "BLOCKED"}:
            failed.add(evidence_id)
    return sorted(passing - failed), sorted(failed)


def _current_local_evidence_ids(
    verify_text: str,
    *,
    artifact_sha256: str,
    environment: str,
    required_task_evidence: Any = None,
) -> tuple[list[str], bool]:
    """Select only current local E2 evidence bound to this target."""

    passing, failed, task_rows = _current_task_evidence(
        verify_text,
        artifact_sha256=artifact_sha256,
    )
    matrix_passing, matrix_failed = _current_matrix_evidence(
        verify_text,
        artifact_sha256=artifact_sha256,
        environment=environment,
    )
    task_current = passing - failed - matrix_failed
    passing.update(matrix_passing)
    failed.update(matrix_failed)
    current = passing - failed
    required = _normalize_required_task_evidence(
        required_task_evidence,
        task_rows,
    )
    if required:
        complete = _required_task_evidence_current(
            required,
            task_rows,
            task_current,
        )
    else:
        complete = bool(matrix_passing - failed)
    return sorted(current), complete


def _current_task_evidence(
    verify_text: str,
    *,
    artifact_sha256: str,
) -> tuple[set[str], set[str], dict[str, Any]]:
    passing: set[str] = set()
    failed: set[str] = set()
    try:
        task_rows = parse_task_completion_evidence(verify_text)
    except ValueError:
        task_rows = []
    rows_by_id = {row.evidence_id: row for row in task_rows}
    for row in task_rows:
        status = clean_cell(row.status).upper()
        if status in {"FAILED", "STALE", "BLOCKED"}:
            failed.add(row.evidence_id)
        elif status in {"LOCAL_PASS", "VERIFIED"} and _artifact_binding_matches(
            row.commit_worktree_artifact,
            artifact_sha256=artifact_sha256,
        ):
            passing.add(row.evidence_id)
    return passing, failed, rows_by_id


def _normalize_required_task_evidence(
    required: Any,
    rows_by_id: Mapping[str, Any],
) -> dict[str, set[str]]:
    if required is None:
        inferred: dict[str, set[str]] = {}
        for evidence_id, row in rows_by_id.items():
            inferred.setdefault(row.task_id, set()).add(evidence_id)
        return inferred
    if not isinstance(required, Mapping):
        return {"INVALID": set()}
    return {
        clean_cell(task_id): {
            clean_cell(item)
            for item in evidence_ids
            if isinstance(item, str) and re.fullmatch(r"EV-\d{4,}", clean_cell(item))
        }
        for task_id, evidence_ids in required.items()
        if isinstance(task_id, str)
        and isinstance(evidence_ids, (list, tuple, set, frozenset))
    }


def _required_task_evidence_current(
    required: Mapping[str, set[str]],
    rows_by_id: Mapping[str, Any],
    current: set[str],
) -> bool:
    return all(
        evidence_ids
        and all(
            evidence_id in current
            and evidence_id in rows_by_id
            and rows_by_id[evidence_id].task_id == task_id
            for evidence_id in evidence_ids
        )
        for task_id, evidence_ids in required.items()
    )


def required_done_task_evidence(
    tasks_text: str,
    done_task_ids: Any,
) -> dict[str, list[str]]:
    """Project every exact local EV citation owned by each DONE task."""

    done = {clean_cell(item) for item in done_task_ids if isinstance(item, str)}
    blocks = {task.task_id: task for task in inspect_task_blocks(tasks_text)}
    return {
        task_id: sorted(
            set(
                re.findall(
                    r"EV-\d{4,}",
                    clean_cell(blocks[task_id].metadata.get("Evidence", "")),
                )
            )
        )
        if task_id in blocks
        else []
        for task_id in sorted(done)
    }


def derive_deliver_projection(
    *,
    tasks: Any,
    tasks_text: str,
    verify_text: str,
    requirements_schema: str,
    completion_target: str,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    artifact_sha256: str,
    lane: str,
    release_state: str,
    evidence_cutoff: str,
    preflight: Any,
    deployment: Mapping[str, Any],
    diagnostics: Any,
) -> dict[str, Any]:
    """Compose task and completion claims without widening release authority."""

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
    preflight_projection = preflight if isinstance(preflight, Mapping) else {}
    release_claim = derive_project_release_claim(
        verify_text,
        requirements_schema=requirements_schema,
        completion_target=completion_target,
        requirements_revision=requirements_revision,
        design_revision=design_revision,
        construction_authorization=construction_authorization,
        artifact_sha256=artifact_sha256,
        lane=lane,
        release_state=release_state,
        evidence_cutoff=evidence_cutoff,
        preflight=preflight_projection,
        deployment=deployment,
        local_ready=(tasks.terminal or tasks.total == 0)
        and tasks.requirement_coverage_complete,
        required_task_evidence=required_done_task_evidence(tasks_text, tasks.done),
        diagnostics=diagnostics,
    )
    return {
        "evidence_state": release_state,
        "release_evidence_cutoff": evidence_cutoff,
        **({"release_claim": release_claim} if release_claim is not None else {}),
        "tasks": task_projection,
    }


def _current_matrix_evidence(
    verify_text: str,
    *,
    artifact_sha256: str,
    environment: str,
) -> tuple[set[str], set[str]]:
    passing: set[str] = set()
    failed: set[str] = set()
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
            continue
        artifact_environment = clean_cell(row.get("Artifact/environment", ""))
        if (
            status in {"LOCAL_PASS", "VERIFIED"}
            and explicit_value(row.get("Automated evidence", ""), allow_none=False)
            and _artifact_environment_matches(
                artifact_environment,
                artifact_sha256=artifact_sha256,
                environment=environment,
            )
        ):
            passing.add(evidence_id)
    return passing, failed


def _artifact_environment_matches(
    value: str,
    *,
    artifact_sha256: str,
    environment: str,
) -> bool:
    """Match one exact digest and a terminal canonical environment token."""

    environment_suffix = re.search(
        rf"(?:^|[/;,]|environment\s*[:=])\s*{re.escape(environment)}\s*$",
        value,
    )
    return (
        _artifact_binding_matches(value, artifact_sha256=artifact_sha256)
        and environment_suffix is not None
    )


def _artifact_binding_matches(value: str, *, artifact_sha256: str) -> bool:
    return re.findall(r"sha256:[0-9a-f]{64}", clean_cell(value)) == [artifact_sha256]


def _recovery_row_matches(
    row: Mapping[str, str],
    *,
    expected_basis: str,
    expected_target: str,
    artifact_sha256: str,
    evidence_id: str,
) -> bool:
    acceptance_ids = set(
        re.findall(r"EV-\d{4,}", clean_cell(row.get("Acceptance evidence IDs", "")))
    )
    return bool(
        evidence_id in acceptance_ids
        and evidence_id != clean_cell(row.get("Evidence ID", ""))
        and clean_cell(row.get("Status", "")) == "COMPLETE"
        and clean_cell(row.get("Phase", "")) == "AWS-30"
        and clean_cell(row.get("REQ / DES / AUTH", "")) == expected_basis
        and clean_cell(row.get("Artifact digest", "")) == artifact_sha256
        and clean_cell(row.get("Account / Region / environment", "")) == expected_target
        and clean_cell(row.get("Identity and boundary match", ""))
        in {"PASS", "VERIFIED"}
    )


def _recovery_evidence_ids(
    verify_text: str,
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    artifact_sha256: str,
    preflight: Mapping[str, Any],
    deployment: Mapping[str, Any],
) -> list[str]:
    if deployment.get("issues") or deployment.get("basis_stale"):
        return []
    try:
        rows = parse_deployment_reconciliation_evidence(verify_text)
    except ValueError:
        return []
    expected_basis = (
        f"{requirements_revision} / {design_revision} / {construction_authorization}"
    )
    expected_target = (
        f"{clean_cell(preflight.get('account', ''))} / "
        f"{clean_cell(preflight.get('region', ''))} / "
        f"{clean_cell(preflight.get('environment', ''))}"
    )
    result: set[str] = set()
    for row in rows:
        match = RELEASE_RECOVERY_OBSERVATION.fullmatch(
            clean_cell(row.get("Rollback result", ""))
        )
        evidence_id = match.group("evidence") if match else ""
        if evidence_id and _recovery_row_matches(
            row,
            expected_basis=expected_basis,
            expected_target=expected_target,
            artifact_sha256=artifact_sha256,
            evidence_id=evidence_id,
        ):
            result.add(evidence_id)
    return sorted(result)


def _local_completion_has_errors(diagnostics: Any) -> bool:
    """Keep higher-target evidence failures from erasing proven local work."""

    return any(
        getattr(item, "severity", "ERROR") == "ERROR"
        and getattr(item, "code", "") not in _HIGHER_TARGET_DIAGNOSTIC_CODES
        for item in diagnostics
    )


def _scope_matches_current_basis(
    scope: Mapping[str, str],
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    artifact_sha256: str,
    release_state: str,
) -> bool:
    expected = {
        "Requirements revision": requirements_revision,
        "Design revision": design_revision,
        "Construction authorization": construction_authorization,
        "Commit, tag, or image digest": artifact_sha256,
        "Release state": release_state,
    }
    return all(
        clean_cell(scope.get(field, "")) == value for field, value in expected.items()
    )


def derive_project_release_claim(
    verify_text: str,
    *,
    requirements_schema: str,
    completion_target: str | None,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    artifact_sha256: str,
    lane: str,
    release_state: str,
    evidence_cutoff: str,
    preflight: Mapping[str, Any],
    deployment: Mapping[str, Any],
    local_ready: bool = False,
    required_task_evidence: Any = None,
    diagnostics: Any = (),
) -> dict[str, Any] | None:
    """Bind a schema-2 claim to exact current canonical project evidence."""

    try:
        active_scope = table_after_heading(verify_text, "## Active evidence scope")
    except ValueError:
        return None
    if not _scope_matches_current_basis(
        active_scope,
        requirements_revision=requirements_revision,
        design_revision=design_revision,
        construction_authorization=construction_authorization,
        artifact_sha256=artifact_sha256,
        release_state=release_state,
    ):
        return None
    recovery = _recovery_evidence_ids(
        verify_text,
        requirements_revision=requirements_revision,
        design_revision=design_revision,
        construction_authorization=construction_authorization,
        artifact_sha256=artifact_sha256,
        preflight=preflight,
        deployment=deployment,
    )
    local_evidence, evidence_complete = _current_local_evidence_ids(
        verify_text,
        artifact_sha256=artifact_sha256,
        environment=clean_cell(active_scope.get("Environment", "")),
        required_task_evidence=required_task_evidence,
    )
    return derive_release_claim_projection(
        requirements_schema=requirements_schema,
        completion_target=completion_target,
        requirements_revision=requirements_revision,
        design_revision=design_revision,
        construction_authorization=construction_authorization,
        artifact_sha256=artifact_sha256,
        environment=clean_cell(active_scope.get("Environment", "")),
        lane=lane,
        release_state=release_state,
        evidence_cutoff=evidence_cutoff,
        local_evidence_ids=local_evidence,
        preflight=preflight,
        deployment=deployment,
        recovery_evidence_ids=recovery,
        local_ready=local_ready and evidence_complete,
        has_errors=_local_completion_has_errors(diagnostics),
    )


__all__ = (
    "classify_local_evidence_ids",
    "derive_project_release_claim",
    "required_done_task_evidence",
)
