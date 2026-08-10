"""Immutable Fastlane Design domain projections and records.

Canonical inputs are caller-observed project records. Outputs are immutable
Design projections or ordered validation issues. This module performs no I/O,
routing, mutation, approval, authorization, or owner-facing rendering.
"""

from __future__ import annotations


import re
from dataclasses import dataclass, field
from typing import Any, Protocol


APPLICATION_SOURCE_DISPOSITION_FIELD = "Application source disposition"


APPLICATION_SOURCE_GREENFIELD = "GREENFIELD_APP_ROOT"


APPLICATION_SOURCE_BROWNFIELD = "BROWNFIELD_PRESERVE"


APPLICATION_SOURCE_NOT_APPLICABLE = "NOT_APPLICABLE"


APPLICATION_SOURCE_INFRASTRUCTURE_ONLY = "NOT_APPLICABLE — INFRASTRUCTURE_ONLY"


APPLICATION_SOURCE_DIAGNOSTIC_CODES = frozenset(
    {
        "APPLICATION_SOURCE_DISPOSITION_MISSING",
        "APPLICATION_SOURCE_DISPOSITION_INVALID",
        "APPLICATION_SOURCE_DISPOSITION_CONFLICT",
        "APPLICATION_SOURCE_PARALLEL_ROOT",
    }
)

ARCHITECTURE_ID = re.compile(r"ARCH-\d{4,}")
ARCHITECTURE_DESIGN_ID = re.compile(
    r"(?:ARCH|COMP|API|EVENT|CLI|FILE|DATA|CTRL|BOUNDARY|STATE)-\d{3,}"
)
ARCHITECTURE_TEST_ID = re.compile(r"(?:PROP|EX|TEST)-\d{3,}")


@dataclass(frozen=True)
class TechnologyDecision:
    decision_id: str
    concern: str
    selection: str
    version_policy: str
    source: str
    basis_ids: str
    alternatives_and_rationale: str
    compatibility_migration: str
    validation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "decision_id": self.decision_id,
            "concern": self.concern,
            "selection": self.selection,
            "version_policy": self.version_policy,
            "source": self.source,
            "basis_ids": self.basis_ids,
            "alternatives_and_rationale": self.alternatives_and_rationale,
            "compatibility_migration": self.compatibility_migration,
            "validation": self.validation,
        }


@dataclass(frozen=True)
class PropertyExecution:
    property_id: str
    framework_tech_id: str
    exact_command: str
    run_target_time_bound: str
    seed_or_reproduction_format: str
    evidence_destination: str

    def to_dict(self) -> dict[str, str]:
        return {
            "property_id": self.property_id,
            "framework_tech_id": self.framework_tech_id,
            "exact_command": self.exact_command,
            "run_target_time_bound": self.run_target_time_bound,
            "seed_or_reproduction_format": self.seed_or_reproduction_format,
            "evidence_destination": self.evidence_destination,
        }


@dataclass(frozen=True)
class ArchitectureDriver:
    driver_id: str
    requirement_basis: str
    driver_class: str
    decision_implication: str
    validation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "driver_id": self.driver_id,
            "requirement_basis": self.requirement_basis,
            "class": self.driver_class,
            "decision_implication": self.decision_implication,
            "validation": self.validation,
        }


@dataclass(frozen=True)
class ArchitectureCandidate:
    candidate_id: str
    architecture_summary: str
    requirement_coverage: str
    aws_evidence: str
    eligibility: str
    failed_constraints: str
    tradeoffs: str

    def to_dict(self) -> dict[str, str]:
        return {
            "candidate_id": self.candidate_id,
            "architecture_summary": self.architecture_summary,
            "requirement_coverage": self.requirement_coverage,
            "aws_evidence": self.aws_evidence,
            "eligibility": self.eligibility,
            "failed_constraints": self.failed_constraints,
            "tradeoffs": self.tradeoffs,
        }


@dataclass(frozen=True)
class ArchitectureSelection:
    architecture_id: str
    selected_candidate: str
    requirement_and_driver_basis: str
    rationale: str
    rejected_alternatives: str
    risks: str
    mitigations: str
    security_impact: str
    reliability_impact: str
    operational_burden: str
    cost_effect: str
    breakpoints: str
    migration_path: str
    revisit_triggers: str
    validation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "architecture_id": self.architecture_id,
            "selected_candidate": self.selected_candidate,
            "requirement_and_driver_basis": self.requirement_and_driver_basis,
            "rationale": self.rationale,
            "rejected_alternatives": self.rejected_alternatives,
            "risks": self.risks,
            "mitigations": self.mitigations,
            "security_impact": self.security_impact,
            "reliability_impact": self.reliability_impact,
            "operational_burden": self.operational_burden,
            "cost_effect": self.cost_effect,
            "breakpoints": self.breakpoints,
            "migration_path": self.migration_path,
            "revisit_triggers": self.revisit_triggers,
            "validation": self.validation,
        }


@dataclass(frozen=True)
class ArchitectureTrace:
    requirement_id: str
    design_ids: str
    property_test_ids: str
    evidence_ids: str

    def to_dict(self) -> dict[str, str]:
        return {
            "requirement_id": self.requirement_id,
            "design_ids": self.design_ids,
            "property_test_ids": self.property_test_ids,
            "evidence_ids": self.evidence_ids,
        }


@dataclass(frozen=True)
class MaterialAwsEvidence:
    evidence_id: str
    discovery_id: str
    design_ids: str
    material_claim: str
    capability: str
    official_reference: str
    observed_date: str

    def to_dict(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "discovery_id": self.discovery_id,
            "design_ids": self.design_ids,
            "material_claim": self.material_claim,
            "capability": self.capability,
            "official_reference": self.official_reference,
            "observed_date": self.observed_date,
        }


@dataclass(frozen=True)
class HarnessRow:
    harness_id: str
    layer: str
    selected_check: str
    trigger: str
    basis_ids: str
    exact_command: str
    evidence_destination: str
    requirement_status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "harness_id": self.harness_id,
            "layer": self.layer,
            "selected_check": self.selected_check,
            "trigger": self.trigger,
            "basis_ids": self.basis_ids,
            "exact_command": self.exact_command,
            "evidence_destination": self.evidence_destination,
            "requirement_status": self.requirement_status,
        }


@dataclass(frozen=True)
class HarnessContract:
    schema_version: int = 1
    status: str = "UNINITIALIZED"
    rows: tuple[HarnessRow, ...] = ()
    required_ids: tuple[str, ...] = ()
    canonical_sha256: str | None = None
    grandfathered_v1: bool = False
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "rows": [row.to_dict() for row in self.rows],
            "required_ids": list(self.required_ids),
            "canonical_sha256": self.canonical_sha256,
            "grandfathered_v1": self.grandfathered_v1,
        }


@dataclass(frozen=True)
class ArchitectureContract:
    schema_version: int = 1
    status: str = "UNINITIALIZED"
    drivers: tuple[ArchitectureDriver, ...] = ()
    candidates: tuple[ArchitectureCandidate, ...] = ()
    selection: ArchitectureSelection | None = None
    traceability: tuple[ArchitectureTrace, ...] = ()
    aws_evidence: tuple[MaterialAwsEvidence, ...] = ()
    canonical_sha256: str | None = None
    grandfathered_v1: bool = False
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "drivers": [item.to_dict() for item in self.drivers],
            "candidates": [item.to_dict() for item in self.candidates],
            "selection": self.selection.to_dict() if self.selection else None,
            "traceability": [item.to_dict() for item in self.traceability],
            "aws_evidence": [item.to_dict() for item in self.aws_evidence],
            "canonical_sha256": self.canonical_sha256,
            "grandfathered_v1": self.grandfathered_v1,
        }


@dataclass(frozen=True)
class FirstWaveContract:
    wave_contract_id: str
    work_kind: str
    journey_id: str | None
    requirement_ids: tuple[str, ...]
    acceptance_test_ids: tuple[str, ...]
    harness_id: str
    blocking_spike_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "wave_contract_id": self.wave_contract_id,
            "work_kind": self.work_kind,
            "journey_id": self.journey_id,
            "requirement_ids": list(self.requirement_ids),
            "acceptance_test_ids": list(self.acceptance_test_ids),
            "harness_id": self.harness_id,
            "blocking_spike_id": self.blocking_spike_id,
        }


@dataclass(frozen=True)
class SpikeContract:
    spike_id: str
    technical_unknown: str
    time_box: str
    disposable_boundary: str
    exit_criterion: str
    required_next_action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "spike_id": self.spike_id,
            "technical_unknown": self.technical_unknown,
            "time_box": self.time_box,
            "disposable_boundary": self.disposable_boundary,
            "exit_criterion": self.exit_criterion,
            "required_next_action": self.required_next_action,
        }


@dataclass(frozen=True)
class DiagramRecord:
    diagram_id: str
    kind: str
    applicability: str
    status: str
    anchor: str
    basis_ids: tuple[str, ...]
    referenced_ids: tuple[str, ...]
    relationships: tuple[tuple[str, str, str], ...]
    semantic_sha256: str | None
    rendered_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagram_id": self.diagram_id,
            "kind": self.kind,
            "applicability": self.applicability,
            "status": self.status,
            "anchor": self.anchor,
            "basis_ids": list(self.basis_ids),
            "referenced_ids": list(self.referenced_ids),
            "relationships": [
                {"from_id": source, "relation": relation, "to_id": target}
                for source, relation, target in self.relationships
            ],
            "semantic_sha256": self.semantic_sha256,
            "rendered_sha256": self.rendered_sha256,
        }


@dataclass(frozen=True)
class DiagramContract:
    schema_version: int = 1
    status: str = "TEMPLATE"
    architecture_basis_id: str | None = None
    records: tuple[DiagramRecord, ...] = ()
    canonical_sha256: str | None = None
    grandfathered_schema5: bool = False
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "architecture_basis_id": self.architecture_basis_id,
            "records": [item.to_dict() for item in self.records],
            "canonical_sha256": self.canonical_sha256,
            "grandfathered_schema5": self.grandfathered_schema5,
        }


@dataclass(frozen=True)
class ApplicationSourceDisposition:
    kind: str
    paths: tuple[str, ...] = ()

    @property
    def canonical_value(self) -> str:
        if self.kind == APPLICATION_SOURCE_NOT_APPLICABLE:
            return APPLICATION_SOURCE_INFRASTRUCTURE_ONLY
        return f"{self.kind}: {'; '.join(self.paths)}"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "paths": list(self.paths)}


@dataclass(frozen=True)
class ProjectDesignContract:
    schema_version: int = 7
    status: str = "UNINITIALIZED"
    application_source_disposition: ApplicationSourceDisposition | None = None
    interface_ids: tuple[str, ...] = ()
    boundary_ids: tuple[str, ...] = ()
    state_ids: tuple[str, ...] = ()
    first_wave: FirstWaveContract | None = None
    spike: SpikeContract | None = None
    missing_records: tuple[str, ...] = ()
    canonical_sha256: str | None = None
    grandfathered_v4: bool = False
    grandfathered_v5: bool = False
    grandfathered_v6: bool = False
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)
    presentation_labels: tuple[tuple[str, str], ...] = field(
        default=(), repr=False, compare=False
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "application_source_disposition": (
                self.application_source_disposition.to_dict()
                if self.application_source_disposition is not None
                else None
            ),
            "interface_ids": list(self.interface_ids),
            "boundary_ids": list(self.boundary_ids),
            "state_ids": list(self.state_ids),
            "first_wave": self.first_wave.to_dict() if self.first_wave else None,
            "spike": self.spike.to_dict() if self.spike else None,
            "missing_records": list(self.missing_records),
            "canonical_sha256": self.canonical_sha256,
            "grandfathered_v4": self.grandfathered_v4,
            "grandfathered_v5": self.grandfathered_v5,
            "grandfathered_v6": self.grandfathered_v6,
        }


class ChangeImpactProjection(Protocol):
    """Structural boundary for the Define-owned change-impact projection."""

    def to_dict(self) -> dict[str, Any]:
        """Return the existing schema-1 report projection."""


@dataclass(frozen=True)
class _EmptyChangeImpactContract:
    """Compatibility default without importing the sibling Define domain."""

    schema_version: int = 1
    status: str = "UNINITIALIZED"
    rows: tuple[object, ...] = ()
    stale_targets: tuple[str, ...] = ()
    canonical_sha256: str | None = None
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "rows": [],
            "stale_targets": list(self.stale_targets),
            "canonical_sha256": self.canonical_sha256,
        }


@dataclass(frozen=True)
class DesignContract:
    schema_version: int = 1
    status: str = "UNINITIALIZED"
    design_revision: str | None = None
    technology_decisions: tuple[TechnologyDecision, ...] = ()
    property_execution: tuple[PropertyExecution, ...] = ()
    architecture: ArchitectureContract = field(default_factory=ArchitectureContract)
    harness: HarnessContract = field(default_factory=HarnessContract)
    change_impact: ChangeImpactProjection = field(
        default_factory=_EmptyChangeImpactContract
    )
    diagram_contract: DiagramContract = field(default_factory=DiagramContract)
    canonical_sha256: str | None = None
    project_contract: ProjectDesignContract = field(
        default_factory=ProjectDesignContract
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "design_revision": self.design_revision,
            "technology_decisions": [
                item.to_dict() for item in self.technology_decisions
            ],
            "property_execution": [item.to_dict() for item in self.property_execution],
            "architecture": self.architecture.to_dict(),
            "harness": self.harness.to_dict(),
            "change_impact": self.change_impact.to_dict(),
            "diagram_contract": self.diagram_contract.to_dict(),
            "canonical_sha256": self.canonical_sha256,
            "project_contract": self.project_contract.to_dict(),
            "application_source_disposition": (
                self.project_contract.application_source_disposition.to_dict()
                if self.project_contract.application_source_disposition is not None
                else None
            ),
        }
