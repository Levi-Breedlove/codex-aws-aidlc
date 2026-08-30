"""Pure owner-brief section and additive Design-8 decision projections."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .define.models import IntakeFoundationContract, RequirementsContract
from .design import Design8Extension, TechnologyDecision, technology_reasoning_parts


@dataclass(frozen=True)
class OwnerDecisionAdditions:
    selections: tuple[str, ...] = ()
    rationales: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    tradeoffs: tuple[str, ...] = ()
    safeguards: tuple[str, ...] = ()
    reconsider: tuple[str, ...] = ()
    basis_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    source_evidence_complete: bool = True


def technology_owner_reasoning(
    technologies: Sequence[TechnologyDecision],
    *,
    required: bool,
) -> tuple[list[str], list[str], list[str]]:
    """Return ordered rationale, rejected alternative, and parse diagnostics."""

    rationales: list[str] = []
    alternatives: list[str] = []
    issues: list[str] = []
    for technology in technologies:
        try:
            rationale, rejected = technology_reasoning_parts(
                technology.alternatives_and_rationale
            )
        except ValueError as exc:
            if required:
                issues.append(f"{technology.decision_id}: {exc}")
            continue
        rationales.append(rationale)
        alternatives.append(rejected)
    return rationales, alternatives, issues


def group_owner_technologies(
    technologies: Sequence[TechnologyDecision],
    domains: Sequence[str],
    domain_for: Callable[[str], str],
) -> dict[str, list[TechnologyDecision]]:
    grouped = {domain: [] for domain in domains}
    for technology in technologies:
        grouped[domain_for(technology.concern)].append(technology)
    return grouped


def _data_additions(extension: Design8Extension) -> OwnerDecisionAdditions:
    selections: list[str] = []
    rationales: list[str] = []
    alternatives: list[str] = []
    safeguards: list[str] = []
    reconsider: list[str] = []
    basis_ids: set[str] = set()
    for item in extension.dataset_implementations:
        selections.append(
            f"{item.dataset_id}: {item.store_component}; "
            f"access/encryption {item.access_encryption}; "
            f"retention/deletion {item.retention_deletion}; "
            f"backup/recovery {item.backup_recovery}; "
            f"residency/migration {item.residency_migration}; "
            f"audit {item.audit_mechanism}"
        )
        rationales.append(
            "The dataset mapping implements the exact current Gate A data obligation."
        )
        alternatives.append(
            "A different store or lifecycle mechanism requires a new Design digest and Gate B review."
        )
        safeguards.extend((item.access_encryption, item.audit_mechanism))
        reconsider.append(
            "Revisit when the linked dataset obligation or implementation IDs change."
        )
        basis_ids.update(
            {item.dataset_id, *item.implementation_ids, *item.validation_ids}
        )
    return OwnerDecisionAdditions(
        selections=tuple(selections),
        rationales=tuple(rationales),
        alternatives=tuple(alternatives),
        safeguards=tuple(safeguards),
        reconsider=tuple(reconsider),
        basis_ids=tuple(sorted(basis_ids)),
    )


def _deployment_additions(extension: Design8Extension) -> OwnerDecisionAdditions:
    selections: list[str] = []
    safeguards: list[str] = []
    reconsider: list[str] = []
    basis_ids: set[str] = set()
    evidence_ids: list[str] = []
    for item in extension.environments:
        selections.append(
            f"{item.environment_id} {item.environment_class}: {item.purpose}; "
            f"artifact {item.artifact_boundary}; promotion from {item.promotion_source}"
        )
        safeguards.extend(
            (
                item.configuration_secrets_data,
                item.promotion_criteria_evidence,
                item.rollback_teardown_boundary,
            )
        )
        basis_ids.update({item.environment_id, *item.basis_ids, *item.validation_ids})
    for item in extension.well_architected:
        selections.append(
            f"{item.pillar}: {item.applicability}; {item.consideration_tradeoff}"
        )
        safeguards.append(item.safeguard)
        reconsider.append(item.revisit_trigger)
        basis_ids.update(
            {*item.basis_ids, *item.design_ids, *item.validation_evidence_ids}
        )
        evidence_ids.extend(
            identifier
            for identifier in item.validation_evidence_ids
            if item.evidence_maturity == "SOURCE_VERIFIED"
            and identifier.startswith("AWS-EV-")
        )
    return OwnerDecisionAdditions(
        selections=tuple(selections),
        rationales=(
            "The environment graph preserves one immutable artifact, while the six consideration rows expose material tradeoffs without claiming an official AWS review.",
        ),
        alternatives=(
            "Environment topology and safeguards adapt to the approved target and risk instead of imposing a universal production path.",
        ),
        safeguards=tuple(safeguards),
        reconsider=tuple(reconsider),
        basis_ids=tuple(sorted(basis_ids)),
        evidence_ids=tuple(evidence_ids),
        source_evidence_complete=not any(
            item.evidence_maturity == "PLANNED" for item in extension.well_architected
        ),
    )


def _validation_additions(extension: Design8Extension) -> OwnerDecisionAdditions:
    selections: list[str] = []
    safeguards: list[str] = []
    basis_ids: set[str] = set()
    if extension.acquisition_prohibited:
        selections.append("Dependency acquisition: DENY_UNDECLARED")
        safeguards.append(
            "An allowed local command prefix cannot override dependency denial."
        )
    else:
        for item in extension.dependency_additions:
            selections.append(
                f"{item.dependency_id}: {item.ecosystem_package} "
                f"{item.immutable_version} from {item.approved_source}; "
                f"exact command {item.exact_acquisition_command}"
            )
            safeguards.extend(
                (
                    item.integrity_rule,
                    item.lifecycle_scripts,
                    item.build_network,
                    item.license_disposition,
                )
            )
            basis_ids.update({item.dependency_id, item.technology_id})
    return OwnerDecisionAdditions(
        selections=tuple(selections),
        rationales=(
            "The dependency policy is an independent necessary boundary for acquisition.",
        ),
        alternatives=(
            "Undeclared additions remain prohibited until a new Design digest and Gate B review.",
        ),
        safeguards=tuple(safeguards),
        reconsider=(
            "Revisit when a package, version, source, lockfile, script, network, license, or acquisition command changes.",
        ),
        basis_ids=tuple(sorted(basis_ids)),
    )


def design8_owner_decision_additions(
    domain: str,
    extension: Design8Extension,
    *,
    enabled: bool,
) -> OwnerDecisionAdditions:
    """Return only the Design-8 additions for one canonical owner domain."""

    if not enabled:
        return OwnerDecisionAdditions()
    if domain == "data":
        return _data_additions(extension)
    if domain == "deployment/recovery":
        return _deployment_additions(extension)
    if domain == "validation/construction":
        return _validation_additions(extension)
    return OwnerDecisionAdditions()


def owner_decision_record(
    *,
    decision_id: str,
    domain: str,
    title: str,
    owner_effect: str,
    selections: Sequence[str],
    rationales: Sequence[str],
    alternatives: Sequence[str],
    tradeoffs: Sequence[str],
    safeguards: Sequence[str],
    reconsider: Sequence[str],
    basis_ids: Sequence[str],
    evidence_ids: Sequence[str],
    source_evidence_complete: bool,
    source_keys: Sequence[str],
    schema_version: int,
    unique_text: Callable[[Iterable[str]], list[str]],
) -> dict[str, Any]:
    source_verified = bool(evidence_ids) and source_evidence_complete
    maturity = "SOURCE_VERIFIED" if source_verified else "PLANNED_AFTER_APPROVAL"
    if source_verified:
        evidence_status = "SOURCE_VERIFIED — " + ", ".join(evidence_ids)
    elif evidence_ids:
        evidence_status = (
            "PLANNED_AFTER_APPROVAL — source evidence "
            + ", ".join(evidence_ids)
            + " verifies only part of this combined decision; remaining elements are planned."
        )
    else:
        evidence_status = "PLANNED_AFTER_APPROVAL — this canonical design decision has not been observed in a deployed environment."
    return {
        "decision_id": decision_id,
        "domain": domain,
        "title": title,
        "selection": "; ".join(unique_text(selections)),
        "source": (
            f"Canonical Design-{schema_version} architecture, technology, and project records"
        ),
        "maturity": maturity,
        "owner_effect": owner_effect,
        "why": " ".join(unique_text(rationales)),
        "alternatives": " ".join(unique_text(alternatives)),
        "tradeoff": " ".join(unique_text(tradeoffs)),
        "risk_and_mitigation": " ".join(unique_text(safeguards)),
        "evidence_status": evidence_status,
        "reconsider_when": " ".join(unique_text(reconsider)),
        "basis_ids": list(basis_ids),
        "evidence_ids": list(evidence_ids),
        "source_locator_keys": list(source_keys),
    }


def finalize_gate_b_inventory(
    status: str,
    required_domains: Sequence[str],
    decisions: Sequence[Mapping[str, Any]],
    issues: Sequence[str],
    finalize: Callable[[Mapping[str, Any]], tuple[dict[str, Any], list[str]]],
) -> tuple[dict[str, Any], list[str]]:
    projection = {
        "schema_version": 1,
        "kind": "GATE_B",
        "status": status,
        "required_domains": list(required_domains),
        "decisions": list(decisions),
    }
    finalized, validation_issues = finalize(projection)
    return finalized, [*issues, *validation_issues]


def _gate_a_outcome_boundary_sections(
    section: Callable[..., dict[str, Any]],
    requirements_revision: str,
    intake: IntakeFoundationContract,
    requirements: RequirementsContract,
    gate_a_card: Mapping[str, str],
    readable_journeys: Sequence[str],
    outcome_text: str,
    boundary_text: str,
    dataset_text: str,
    obligation_text: str,
) -> list[dict[str, Any]]:
    return [
        section(
            "GATE-A-OUTCOME",
            "Outcome, users, and first useful journey",
            [
                "Outcome: " + outcome_text,
                "Owner and users: "
                + gate_a_card.get("Owner and users", "Not yet recorded."),
                "First-release journey: "
                + ("; ".join(readable_journeys) or "Not yet recorded."),
            ],
            [requirements_revision, *intake.basis_ids],
        ),
        section(
            "GATE-A-BOUNDARY",
            "First-release boundary",
            [
                "First-release boundary: " + boundary_text,
                "Completion target: "
                + (requirements.completion_target or "Not yet recorded."),
                "Scope and non-goals: "
                + gate_a_card.get("Scope and non-goals", "Not yet recorded."),
                "Data and access: "
                + gate_a_card.get("Data boundary", "Not yet recorded.")
                + " "
                + gate_a_card.get("Identity/security boundary", "Not yet recorded."),
                "Data categories: " + dataset_text,
                "External obligations: " + obligation_text,
            ],
            [
                requirements_revision,
                *requirements.requirement_ids,
                *(item.dataset_id for item in requirements.datasets),
                *(item.obligation_id for item in requirements.external_obligations),
            ],
        ),
    ]


def _gate_a_success_risk_sections(
    section: Callable[..., dict[str, Any]],
    requirements_revision: str,
    requirements: RequirementsContract,
    gate_a_card: Mapping[str, str],
    gate_a_analysis: Mapping[str, str],
    success_text: str,
    metric_text: str,
    risk_text: str,
) -> list[dict[str, Any]]:
    return [
        section(
            "GATE-A-SUCCESS",
            "Success, resilience, Region, and cost",
            [
                "Success measures: " + success_text,
                "Outcome measurements: " + metric_text,
                "Recovery, Region, and cost: "
                + gate_a_card.get("Failure/recovery", "Not yet recorded.")
                + "; "
                + gate_a_card.get("Environment/Region", "Not yet recorded.")
                + "; "
                + gate_a_card.get("Cost posture", "Not yet recorded."),
            ],
            [
                requirements_revision,
                *requirements.acceptance_ids,
                *(item.metric_id for item in requirements.outcome_metrics),
            ],
        ),
        section(
            "GATE-A-RISK",
            "Assumptions, risks, and change impact",
            [
                "Assumptions: " + gate_a_card.get("Assumptions", "None recorded."),
                "Open decisions or findings: "
                + gate_a_analysis.get("Open blocking decision IDs", "None recorded.")
                + "; "
                + gate_a_analysis.get("Open blocking finding IDs", "None recorded."),
                "Brownfield preservation: "
                + gate_a_card.get(
                    "Brownfield baseline and preservation", "Not applicable."
                ),
                "Cross-cutting risks: " + risk_text,
            ],
            [
                requirements_revision,
                *requirements.requirement_ids,
                *(item.risk_id for item in requirements.cross_cutting_risks),
            ],
        ),
    ]


def gate_a_owner_sections(
    *,
    section: Callable[..., dict[str, Any]],
    requirements_revision: str,
    intake: IntakeFoundationContract,
    requirements: RequirementsContract,
    gate_a_card: Mapping[str, str],
    gate_a_analysis: Mapping[str, str],
    readable_journeys: Sequence[str],
    outcome_text: str,
    boundary_text: str,
    success_text: str,
    metric_text: str,
    dataset_text: str,
    obligation_text: str,
    risk_text: str,
) -> list[dict[str, Any]]:
    return [
        *_gate_a_outcome_boundary_sections(
            section,
            requirements_revision,
            intake,
            requirements,
            gate_a_card,
            readable_journeys,
            outcome_text,
            boundary_text,
            dataset_text,
            obligation_text,
        ),
        *_gate_a_success_risk_sections(
            section,
            requirements_revision,
            requirements,
            gate_a_card,
            gate_a_analysis,
            success_text,
            metric_text,
            risk_text,
        ),
    ]


def gate_b_technical_groups(inventory: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project the canonical inventory into the brief's grouped compatibility shape."""

    return [
        {
            "domain": decision["domain"],
            "decisions": [
                {
                    "decision_id": decision["decision_id"],
                    "decision": decision["title"],
                    "owner_effect": decision["owner_effect"],
                    "selection": decision["selection"],
                    "requirement_basis": ", ".join(decision["basis_ids"]),
                    "why": decision["why"],
                    "alternatives": decision["alternatives"],
                    "tradeoff": decision["tradeoff"],
                    "risk_and_mitigation": decision["risk_and_mitigation"],
                    "evidence_status": decision["evidence_status"],
                    "reconsider_when": decision["reconsider_when"],
                    "basis_ids": decision["basis_ids"],
                    "evidence_ids": decision["evidence_ids"],
                    "source_locator_keys": decision["source_locator_keys"],
                }
            ],
        }
        for decision in inventory.get("decisions", [])
    ]


__all__ = (
    "OwnerDecisionAdditions",
    "design8_owner_decision_additions",
    "finalize_gate_b_inventory",
    "gate_a_owner_sections",
    "gate_b_technical_groups",
    "group_owner_technologies",
    "owner_decision_record",
    "technology_owner_reasoning",
)
