"""Compatibility projections over cohesive AWS lifecycle state machines.

Canonical inputs are immutable evidence and exact authority intersections. Returns
AWS preflight, deployment, teardown, and aggregate projections. Side effects are
prohibited and no projection grants or executes AWS authority.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from ..aws import (
    derive_aws_execution_projection as _derive_aws_execution_projection_core,
    derive_deployment_sequence_state as _derive_deployment_sequence_state_core,
    derive_read_preflight_state as _derive_read_preflight_state_core,
    derive_teardown_sequence_state as _derive_teardown_sequence_state_core,
)
from .aws import build_aws_authority_policy


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
) -> dict[str, Any]:
    """COMPATIBILITY: evaluate deployment through the modular AWS domain."""

    return _derive_deployment_sequence_state_core(
        verify_text,
        read_authority,
        policy=build_aws_authority_policy(observed_at),
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
) -> dict[str, Any]:
    """COMPATIBILITY: evaluate teardown through the modular AWS domain."""

    return _derive_teardown_sequence_state_core(
        verify_text,
        read_authority,
        policy=build_aws_authority_policy(observed_at),
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
) -> dict[str, Any]:
    """COMPATIBILITY: evaluate preflight through the modular AWS domain."""

    return _derive_read_preflight_state_core(
        verify_text,
        authority,
        policy=build_aws_authority_policy(observed_at),
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
    """COMPATIBILITY: expose the stable AWS execution projection."""

    return _derive_aws_execution_projection_core(
        materiality,
        release_decision=release_decision,
        guidance_ready=guidance_ready,
        read_authority=read_authority,
        preflight=preflight,
        lane=lane,
    )
