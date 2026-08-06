"""Deterministic Fastlane lifecycle routing.

Canonical inputs are immutable gate, task, release, and AWS-state projections.
The module returns routes or narrows existing diagnostics for safe journal
closure. It performs no file, Git, network, AWS, mutation, approval, authority,
or report-rendering work. Route behavior preserves Fastlane 1.2.16 exactly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .aws import AWS_DEPLOYMENT_TERMINAL_STATUSES
from .core.diagnostics import Diagnostic
from .core.ids import clean_cell


class TaskRouteState(Protocol):
    """Minimal immutable task state consumed by lifecycle routing."""

    plan_state: str
    active: Sequence[str]
    ready: Sequence[str]
    terminal: bool


class DiagnosticRouteState(Protocol):
    """Minimal diagnostic surface used to preserve safe closure routes."""

    diagnostics: list[Diagnostic]


def derive_route(
    gate_a: str,
    gate_b: str,
    requirements_present: bool,
    gate_b_agent_ready: bool,
    tasks: TaskRouteState,
    autonomous_allowed: bool,
    execution_mode: str,
    release_decision: str = "NOT_READY",
) -> tuple[str, str]:
    """SAFETY: return the exact next route and prompt without side effects."""

    if gate_a == "STALE":
        return (
            ("REQUIREMENTS_STALE", "REQ-10")
            if requirements_present
            else ("INTAKE_REQUIRED", "INTAKE-10")
        )
    if gate_a == "BLOCKED":
        return (
            ("REQUIREMENTS_ANALYSIS", "REQ-10")
            if requirements_present
            else ("INTAKE_REQUIRED", "INTAKE-10")
        )
    if gate_a == "PENDING_OWNER_APPROVAL":
        return "WAITING_GATE_A", "INTAKE-20"
    if gate_a != "APPROVED_FOR_DESIGN":
        return "BLOCKED", "STOP"
    if gate_b == "STALE":
        return "DESIGN_STALE", "DESIGN-10"
    if gate_b == "BLOCKED":
        return (
            ("WAITING_GATE_B", "DESIGN-20")
            if gate_b_agent_ready
            else ("DESIGN_REQUIRED", "DESIGN-10")
        )
    if gate_b == "PENDING_OWNER_APPROVAL":
        return "WAITING_GATE_B", "DESIGN-20"
    if gate_b != "APPROVED_FOR_CONSTRUCTION":
        return "BLOCKED", "STOP"
    if tasks.plan_state in {"UNINITIALIZED", "STALE"}:
        return "TASK_PLAN_REQUIRED", "TASK-10"
    if tasks.active:
        if execution_mode == "AUTONOMOUS" and autonomous_allowed:
            return "CONSTRUCTION_AUTONOMOUS", "BUILD-20"
        if len(tasks.active) == 1:
            return "CONSTRUCTION_SINGLE", "BUILD-10"
        return "BLOCKED", "STOP"
    if len(tasks.ready) == 1:
        return "CONSTRUCTION_SINGLE", "BUILD-10"
    if len(tasks.ready) > 1:
        if autonomous_allowed:
            return "CONSTRUCTION_AUTONOMOUS", "BUILD-20"
        return "BLOCKED", "STOP"
    if tasks.terminal:
        if release_decision == "READY_TO_DEPLOY":
            return "AWS_PREFLIGHT_REQUIRED", "AWS-10"
        if release_decision == "RELEASE_VERIFIED":
            return "RELEASE_VERIFIED", "STOP"
        return "RELEASE_REVIEW", "RELEASE-10"
    return "BLOCKED", "STOP"


def preserve_expired_authority_for_deployment_closure(
    diagnostics: list[Diagnostic],
    deployment_sequence: Mapping[str, Any],
    release_decision: str,
) -> None:
    """SAFETY: narrow an expired Gate B error only for auditable closure."""

    status = clean_cell(deployment_sequence.get("status", ""))
    terminal_reconciliation = bool(
        (
            status in {"RECONCILED", "BLOCKED"}
            or (status == "CONSUMED" and release_decision != "READY_TO_DEPLOY")
        )
        and not deployment_sequence.get("issues")
        and clean_cell(deployment_sequence.get("phase", "")) == "AWS-30"
        and clean_cell(deployment_sequence.get("reconciliation_status", ""))
        in {"COMPLETE", "BLOCKED"}
    )
    read_only_reconciliation = bool(
        status == "RECONCILIATION_REQUIRED"
        and not deployment_sequence.get("issues")
        and clean_cell(deployment_sequence.get("action_status", ""))
        in AWS_DEPLOYMENT_TERMINAL_STATUSES
    )
    completed_without_attempt = bool(
        status == "NOT_ACTIVE" and release_decision == "RELEASE_VERIFIED"
    )
    if (
        status != "ACTION_TERMINAL_REQUIRED"
        and not read_only_reconciliation
        and not terminal_reconciliation
        and not completed_without_attempt
    ):
        return
    diagnostics[:] = [
        Diagnostic(item.code, item.message, item.path, "WARNING")
        if item.code == "GATE_B_AUTHORITY_EXPIRED"
        else item
        for item in diagnostics
    ]


def preserve_expired_authority_for_teardown_closure(
    diagnostics: list[Diagnostic], teardown_sequence: Mapping[str, Any]
) -> None:
    """SAFETY: retain local UNKNOWN closure after a valid teardown attempt."""

    if clean_cell(teardown_sequence.get("status", "")) not in {
        "ACTION_TERMINAL_REQUIRED",
        "POST_ACTION_REVIEW",
    } or teardown_sequence.get("issues"):
        return
    diagnostics[:] = [
        Diagnostic(item.code, item.message, item.path, "WARNING")
        if item.code == "GATE_B_AUTHORITY_EXPIRED"
        else item
        for item in diagnostics
    ]


def preserve_specialized_teardown_block(
    diagnostics: Sequence[Diagnostic], lifecycle_state: str
) -> bool:
    """SAFETY: keep a teardown route only when every error belongs to it."""

    return lifecycle_state == "AWS_RESIDUAL_REVIEW_BLOCKED" and all(
        item.severity != "ERROR" or item.code == "AWS_TEARDOWN_EVIDENCE_INVALID"
        for item in diagnostics
    )


__all__ = (
    "DiagnosticRouteState",
    "TaskRouteState",
    "derive_route",
    "preserve_expired_authority_for_deployment_closure",
    "preserve_expired_authority_for_teardown_closure",
    "preserve_specialized_teardown_block",
)
