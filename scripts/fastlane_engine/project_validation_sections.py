"""Pure Requirements and Gate A project-validation sections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .core.ids import clean_cell
from .define.models import RequirementsContract
from .define.project import gate_a_product_truth_issues
from .project_inspection import PRD_FILE, STATE_FILE, parse_cost_posture


def current_requirements_gate_issues(
    text: str,
    gate_a_agent: Mapping[str, str],
    contract: RequirementsContract,
    contract_issues: Sequence[tuple[str, str]],
    *,
    required: bool,
) -> list[tuple[str, str]]:
    """Return current Requirements diagnostics in their canonical order."""

    if not required:
        return []
    issues = list(contract_issues)
    if contract.status != "GRANDFATHERED":
        issues.extend(
            gate_a_product_truth_issues(
                text,
                gate_a_agent,
                set(contract.requirement_ids),
            )
        )
    if contract.status not in {"READY", "GRANDFATHERED"}:
        issues.append(
            (
                "PROJECT_CONTRACT_MIGRATION_REQUIRED",
                "Gate A requires a complete Requirements 1.5 contract or an unchanged approved compatible contract",
            )
        )
    if (
        contract.schema_version in {"1.5", "1.6"}
        and gate_a_agent.get("Requirements contract SHA-256 analyzed")
        != contract.canonical_sha256
    ):
        issues.append(
            (
                "GATE_A_REQUIREMENTS_CONTRACT_HASH",
                "Gate A analysis does not match the current Requirements 1.5 contract digest",
            )
        )
    return issues


def gate_a_readiness_projection_issues(
    card_cost_posture: str,
    gate_a_card: Mapping[str, str],
    contract: RequirementsContract,
    state_cost_posture: Any,
) -> list[tuple[str, str, str]]:
    """Validate the card's Requirements target and bootstrap cost mirror."""

    issues: list[tuple[str, str, str]] = []
    if (
        contract.schema_version in {"1.5", "1.6"}
        and clean_cell(gate_a_card.get("Project completion target", ""))
        != contract.completion_target
    ):
        issues.append(
            (
                "GATE_A_READINESS_CARD",
                "Gate A Project completion target must match the current Requirements 1.5 contract",
                PRD_FILE,
            )
        )
    try:
        parse_cost_posture(card_cost_posture)
    except ValueError as exc:
        issues.append(("GATE_A_COST_POSTURE", str(exc), PRD_FILE))
    if card_cost_posture != state_cost_posture:
        issues.append(
            (
                "STATE_PRD_DRIFT",
                "Gate A Cost posture does not match bootstrap state",
                STATE_FILE,
            )
        )
    return issues


__all__ = (
    "current_requirements_gate_issues",
    "gate_a_readiness_projection_issues",
)
