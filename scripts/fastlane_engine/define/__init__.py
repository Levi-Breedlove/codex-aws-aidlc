"""Fastlane Define contracts for intake, requirements, and Gate A readiness.

The package consumes already-observed canonical Markdown and caller-supplied
project selections. It returns immutable projections and issue records without
I/O, routing, mutation, approval, authorization, or owner-facing rendering.
"""

from .coverage import derive_change_impact_contract, derive_coverage_contract
from .intake import derive_intake_foundation_contract
from .models import (
    AssumptionLifecycleRecord,
    ChangeImpactContract,
    ChangeImpactRow,
    CoverageContract,
    CoverageOmission,
    CrossCuttingRisk,
    DatasetObligation,
    ExternalObligation,
    IntakeCard,
    IntakeFoundationContract,
    IntakeQuestion,
    NormalizedOwnerResponse,
    OutcomeMetric,
    RequirementsChangeLineage,
    RequirementsContract,
)
from .project import (
    brownfield_contract_issues,
    derive_req_aws_materiality,
    gate_a_readiness_card_issues,
)
from .requirements import (
    PROJECT_COMPLETION_TARGETS,
    authoritative_requirement_ids,
    derive_requirements_contract,
    gate_a_method_contract_issues,
)
from .source_assist import (
    SOURCE_BRIEF_MAX_BYTES,
    blocked_source_assist_preview,
    derive_source_assist_preview,
)

__all__ = (
    "AssumptionLifecycleRecord",
    "ChangeImpactContract",
    "ChangeImpactRow",
    "CoverageContract",
    "CoverageOmission",
    "CrossCuttingRisk",
    "DatasetObligation",
    "ExternalObligation",
    "IntakeCard",
    "IntakeFoundationContract",
    "IntakeQuestion",
    "NormalizedOwnerResponse",
    "OutcomeMetric",
    "PROJECT_COMPLETION_TARGETS",
    "RequirementsChangeLineage",
    "RequirementsContract",
    "SOURCE_BRIEF_MAX_BYTES",
    "authoritative_requirement_ids",
    "brownfield_contract_issues",
    "blocked_source_assist_preview",
    "derive_change_impact_contract",
    "derive_coverage_contract",
    "derive_intake_foundation_contract",
    "derive_req_aws_materiality",
    "derive_requirements_contract",
    "derive_source_assist_preview",
    "gate_a_method_contract_issues",
    "gate_a_readiness_card_issues",
)
