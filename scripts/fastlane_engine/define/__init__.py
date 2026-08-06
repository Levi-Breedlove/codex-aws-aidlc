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
    IntakeCard,
    IntakeFoundationContract,
    IntakeQuestion,
    NormalizedOwnerResponse,
    RequirementsChangeLineage,
    RequirementsContract,
)
from .project import (
    brownfield_contract_issues,
    derive_req_aws_materiality,
    gate_a_readiness_card_issues,
)
from .requirements import (
    authoritative_requirement_ids,
    derive_requirements_contract,
    gate_a_method_contract_issues,
)

__all__ = (
    "AssumptionLifecycleRecord",
    "ChangeImpactContract",
    "ChangeImpactRow",
    "CoverageContract",
    "CoverageOmission",
    "IntakeCard",
    "IntakeFoundationContract",
    "IntakeQuestion",
    "NormalizedOwnerResponse",
    "RequirementsChangeLineage",
    "RequirementsContract",
    "authoritative_requirement_ids",
    "brownfield_contract_issues",
    "derive_change_impact_contract",
    "derive_coverage_contract",
    "derive_intake_foundation_contract",
    "derive_req_aws_materiality",
    "derive_requirements_contract",
    "gate_a_method_contract_issues",
    "gate_a_readiness_card_issues",
)
