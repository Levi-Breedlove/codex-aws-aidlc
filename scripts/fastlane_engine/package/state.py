"""Pure validation of the bootstrap-state mirror.

Canonical inputs are the decoded state object and an explicit immutable policy.
Diagnostics append through the caller's compatibility context. This module does
not read files, route lifecycle work, mutate state, or grant any authority.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class StateContext(Protocol):
    template_source: bool

    def error(self, code: str, message: str, path: str | None = None) -> None: ...


@dataclass(frozen=True)
class StatePolicy:
    state_file: str
    project_name_token: str
    setup_status_token: str
    setup_method_token: str
    aws_region_token: str
    cost_posture_token: str
    project_modes: frozenset[str]
    delivery_profiles: frozenset[str]
    risk_levels: frozenset[str]
    aws_lanes: frozenset[str]
    brownfield_states: frozenset[str]
    gate_a_states: frozenset[str]
    gate_b_states: frozenset[str]
    run_modes: frozenset[str]
    run_states: frozenset[str]
    req_id: re.Pattern[str]
    des_id: re.Pattern[str]
    auth_id: re.Pattern[str]
    plan_id: re.Pattern[str]
    task_id: re.Pattern[str]
    run_id: re.Pattern[str]
    checkpoint_id: re.Pattern[str]


def validate_state_schema(
    ctx: StateContext,
    state: dict[str, Any],
    *,
    policy: StatePolicy,
    normalize_project_name: Callable[[str], str],
    normalize_aws_region: Callable[[str], str],
    parse_cost_posture: Callable[[str], object],
    unresolved: Callable[[str], bool],
) -> bool:
    """Validate bootstrap.yaml with the exact historical diagnostic sequence."""

    expected_top = {
        "schema_version",
        "bootstrap_version",
        "setup",
        "project",
        "lifecycle",
        "execution",
    }
    if set(state) != expected_top:
        ctx.error(
            "STATE_SCHEMA",
            f"State keys must be exactly {sorted(expected_top)}",
            policy.state_file,
        )
    if state.get("schema_version") != 1:
        ctx.error("STATE_SCHEMA", "Unsupported state schema_version", policy.state_file)

    setup = state.get("setup")
    project = state.get("project")
    lifecycle = state.get("lifecycle")
    execution = state.get("execution")
    if not all(
        isinstance(value, dict) for value in (setup, project, lifecycle, execution)
    ):
        ctx.error(
            "STATE_SCHEMA",
            "setup, project, lifecycle, and execution must be objects",
            policy.state_file,
        )
        return False

    _validate_mapping_keys(ctx, setup, project, lifecycle, execution, policy)
    _validate_setup(ctx, setup, policy)
    _validate_project(
        ctx,
        project,
        policy,
        normalize_project_name,
        normalize_aws_region,
        parse_cost_posture,
    )
    _validate_lifecycle(ctx, lifecycle, policy)
    _validate_execution(ctx, execution, policy, unresolved)
    return True


def _validate_mapping_keys(
    ctx: StateContext,
    setup: Mapping[str, Any],
    project: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    execution: Mapping[str, Any],
    policy: StatePolicy,
) -> None:
    expected = (
        ("setup", setup, {"status", "method"}),
        (
            "project",
            project,
            {
                "name",
                "region",
                "cost_posture",
                "mode",
                "delivery_profile",
                "effective_risk",
                "aws_lane",
                "brownfield_baseline",
            },
        ),
        (
            "lifecycle",
            lifecycle,
            {
                "requirements_revision",
                "design_revision",
                "construction_authorization",
                "gate_a",
                "gate_b",
            },
        ),
        (
            "execution",
            execution,
            {
                "plan_revision",
                "plan_state",
                "run_id",
                "coordinator",
                "mode",
                "state",
                "basis",
                "active_tasks",
                "attempts",
                "last_checkpoint",
            },
        ),
    )
    for name, value, required_keys in expected:
        if set(value) != required_keys:
            ctx.error(
                "STATE_SCHEMA",
                f"{name} keys must be exactly {sorted(required_keys)}",
                policy.state_file,
            )


def _validate_setup(
    ctx: StateContext, setup: Mapping[str, Any], policy: StatePolicy
) -> None:
    allowed_statuses = {"UNCONFIGURED_TEMPLATE", "CONFIGURED"}
    allowed_methods = {"IN_PLACE", "EXTERNAL_COPY"}
    if ctx.template_source:
        allowed_statuses.add(policy.setup_status_token)
        allowed_methods.add(policy.setup_method_token)
    if setup.get("status") not in allowed_statuses:
        ctx.error("STATE_SETUP", "Invalid setup.status", policy.state_file)
    if setup.get("method") not in allowed_methods:
        ctx.error("STATE_SETUP", "Invalid setup.method", policy.state_file)


def _validate_project(
    ctx: StateContext,
    project: Mapping[str, Any],
    policy: StatePolicy,
    normalize_project_name: Callable[[str], str],
    normalize_aws_region: Callable[[str], str],
    parse_cost_posture: Callable[[str], object],
) -> None:
    _validate_project_identity(
        ctx,
        project,
        policy,
        normalize_project_name,
        normalize_aws_region,
        parse_cost_posture,
    )
    _validate_project_vocabulary(ctx, project, policy)


def _validate_project_identity(
    ctx: StateContext,
    project: Mapping[str, Any],
    policy: StatePolicy,
    normalize_project_name: Callable[[str], str],
    normalize_aws_region: Callable[[str], str],
    parse_cost_posture: Callable[[str], object],
) -> None:
    """COMPATIBILITY: preserve the established identity diagnostic sequence."""

    for key in ("name", "region", "cost_posture"):
        value = project.get(key)
        if not isinstance(value, str) or not value.strip():
            ctx.error(
                "PROJECT_IDENTITY",
                f"project.{key} must be non-empty text",
                policy.state_file,
            )

    name = project.get("name")
    if (
        isinstance(name, str)
        and name.strip()
        and not (ctx.template_source and name == policy.project_name_token)
    ):
        try:
            canonical_name = normalize_project_name(name)
        except ValueError as exc:
            ctx.error("PROJECT_IDENTITY", str(exc), policy.state_file)
        else:
            if canonical_name != name:
                ctx.error(
                    "PROJECT_IDENTITY",
                    "project.name must use its canonical normalized value",
                    policy.state_file,
                )

    region = project.get("region")
    if (
        isinstance(region, str)
        and region.strip()
        and not (ctx.template_source and region == policy.aws_region_token)
    ):
        try:
            canonical_region = normalize_aws_region(region)
        except ValueError as exc:
            ctx.error("PROJECT_IDENTITY", str(exc), policy.state_file)
        else:
            if canonical_region != region:
                ctx.error(
                    "PROJECT_IDENTITY",
                    "project.region must use its canonical lowercase value",
                    policy.state_file,
                )

    cost_posture = project.get("cost_posture")
    if isinstance(cost_posture, str) and not (
        ctx.template_source and cost_posture == policy.cost_posture_token
    ):
        try:
            parse_cost_posture(cost_posture)
        except ValueError as exc:
            ctx.error("PROJECT_COST_POSTURE", str(exc), policy.state_file)


def _validate_project_vocabulary(
    ctx: StateContext,
    project: Mapping[str, Any],
    policy: StatePolicy,
) -> None:
    for key, allowed in (
        ("mode", policy.project_modes),
        ("delivery_profile", policy.delivery_profiles),
        ("effective_risk", policy.risk_levels),
        ("aws_lane", policy.aws_lanes),
    ):
        value = project.get(key)
        if value is not None and (not isinstance(value, str) or value not in allowed):
            ctx.error(
                "PROJECT_VOCABULARY",
                f"Invalid project.{key}: {value!r}",
                policy.state_file,
            )
    baseline_state = project.get("brownfield_baseline")
    if (
        not isinstance(baseline_state, str)
        or baseline_state not in policy.brownfield_states
    ):
        ctx.error(
            "PROJECT_VOCABULARY",
            "Invalid brownfield_baseline state",
            policy.state_file,
        )


def _validate_lifecycle(
    ctx: StateContext, lifecycle: Mapping[str, Any], policy: StatePolicy
) -> None:
    if policy.req_id.fullmatch(str(lifecycle.get("requirements_revision"))) is None:
        ctx.error(
            "STATE_REVISION_ID", "Invalid requirements revision", policy.state_file
        )
    if policy.des_id.fullmatch(str(lifecycle.get("design_revision"))) is None:
        ctx.error("STATE_REVISION_ID", "Invalid design revision", policy.state_file)
    if (
        policy.auth_id.fullmatch(str(lifecycle.get("construction_authorization")))
        is None
    ):
        ctx.error(
            "STATE_REVISION_ID",
            "Invalid construction authorization",
            policy.state_file,
        )
    gate_a = lifecycle.get("gate_a")
    gate_b = lifecycle.get("gate_b")
    if (
        not isinstance(gate_a, str)
        or gate_a not in policy.gate_a_states
        or not isinstance(gate_b, str)
        or gate_b not in policy.gate_b_states
    ):
        ctx.error("STATE_GATE", "Invalid derived gate state", policy.state_file)


def _validate_execution(
    ctx: StateContext,
    execution: Mapping[str, Any],
    policy: StatePolicy,
    unresolved: Callable[[str], bool],
) -> None:
    run_state = _validate_execution_plan_and_tasks(ctx, execution, policy)
    _validate_execution_identity(ctx, execution, policy, unresolved, run_state)


def _validate_execution_plan_and_tasks(
    ctx: StateContext,
    execution: Mapping[str, Any],
    policy: StatePolicy,
) -> str:
    """COMPATIBILITY: keep interdependent plan/task diagnostics in exact order."""

    run_mode = execution.get("mode")
    run_state_value = execution.get("state")
    if (
        not isinstance(run_mode, str)
        or run_mode not in policy.run_modes
        or not isinstance(run_state_value, str)
        or run_state_value not in policy.run_states
    ):
        ctx.error("STATE_RUN", "Invalid execution mode or state", policy.state_file)
    plan = execution.get("plan_revision")
    if plan is not None and policy.plan_id.fullmatch(str(plan)) is None:
        ctx.error(
            "STATE_RUN",
            "plan_revision must be null or PLAN-nnnn",
            policy.state_file,
        )
    plan_state = execution.get("plan_state")
    if not isinstance(plan_state, str) or plan_state not in {
        "UNINITIALIZED",
        "CURRENT",
        "STALE",
    }:
        ctx.error(
            "STATE_RUN",
            "plan_state must be UNINITIALIZED, CURRENT, or STALE",
            policy.state_file,
        )
    if (plan is None) != (plan_state == "UNINITIALIZED"):
        ctx.error(
            "STATE_RUN",
            "plan_revision and plan_state are inconsistent",
            policy.state_file,
        )
    active = execution.get("active_tasks")
    if not isinstance(active, list) or not all(
        isinstance(item, str) and policy.task_id.fullmatch(item) for item in active
    ):
        ctx.error(
            "STATE_RUN", "active_tasks must contain only TASK IDs", policy.state_file
        )
    elif len(active) != len(set(active)):
        ctx.error("STATE_RUN", "active_tasks contains duplicates", policy.state_file)
    attempts = execution.get("attempts")
    if not isinstance(attempts, dict) or any(
        policy.task_id.fullmatch(str(key)) is None
        or not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for key, value in (attempts.items() if isinstance(attempts, dict) else [])
    ):
        ctx.error(
            "STATE_RUN",
            "attempts must map TASK IDs to non-negative integers",
            policy.state_file,
        )
    return run_state_value if isinstance(run_state_value, str) else ""


def _validate_execution_identity(
    ctx: StateContext,
    execution: Mapping[str, Any],
    policy: StatePolicy,
    unresolved: Callable[[str], bool],
    run_state: str,
) -> None:
    """SAFETY: evaluate resume identity and checkpoint closure as one boundary."""

    run_id = execution.get("run_id")
    coordinator = execution.get("coordinator")
    basis = execution.get("basis")
    if run_id is not None and policy.run_id.fullmatch(str(run_id)) is None:
        ctx.error("STATE_RUN", "run_id must be null or RUN-nnnn", policy.state_file)
    if run_state == "IDLE":
        if (
            run_id is not None
            or coordinator is not None
            or execution.get("mode") != "NONE"
            or execution.get("active_tasks")
        ):
            ctx.error(
                "STATE_RUN",
                "IDLE execution cannot have a coordinator, run ID, run mode, or active tasks",
                policy.state_file,
            )
    else:
        if run_id is None or coordinator is None or execution.get("mode") == "NONE":
            ctx.error(
                "STATE_RUN",
                "A non-IDLE execution requires a coordinator, run ID, and run mode",
                policy.state_file,
            )
        expected_basis_keys = {
            "requirements_revision",
            "design_revision",
            "construction_authorization",
        }
        if not isinstance(basis, dict) or set(basis) != expected_basis_keys:
            ctx.error(
                "STATE_RUN",
                "A non-IDLE execution requires a complete revision basis",
                policy.state_file,
            )

    checkpoint = execution.get("last_checkpoint")
    if checkpoint is not None:
        checkpoint_keys = {"id", "at", "evidence_ref"}
        if not isinstance(checkpoint, dict) or set(checkpoint) != checkpoint_keys:
            ctx.error(
                "STATE_RUN", "last_checkpoint has an invalid shape", policy.state_file
            )
        elif (
            policy.checkpoint_id.fullmatch(str(checkpoint.get("id"))) is None
            or unresolved(str(checkpoint.get("at", "")))
            or unresolved(str(checkpoint.get("evidence_ref", "")))
        ):
            ctx.error(
                "STATE_RUN",
                "last_checkpoint fields must be explicit",
                policy.state_file,
            )
    if run_state in {"CHECKPOINTED", "BLOCKED", "COMPLETE"} and checkpoint is None:
        ctx.error(
            "STATE_RUN",
            f"{run_state} execution requires a checkpoint",
            policy.state_file,
        )
    if run_state == "COMPLETE" and execution.get("active_tasks"):
        ctx.error(
            "STATE_RUN",
            "COMPLETE execution cannot have active tasks",
            policy.state_file,
        )
    if execution.get("state") == "RUNNING":
        ctx.error(
            "RUN_UNCLEAN_INTERRUPTION",
            "Persisted RUNNING state is not safe to resume; reconcile partial work and checkpoint first",
            policy.state_file,
        )
