"""Fastlane's read-only canonical validation Engine.

Canonical inputs are immutable project snapshots and existing project records.
The package returns diagnostics and derived projections without writing project
state, authorizing an action, or rendering owner conversation. Public CLI
compatibility remains in :mod:`scripts.bootstrap_doctor`.
"""

from .api import (
    AwsAuthorityPolicy,
    AwsCoreEvidenceRow,
    DesignContract,
    IntakeFoundationContract,
    RequirementsContract,
    capture_project_snapshot,
    inspect_project,
    aws_core_phase_evidence_issues,
    derive_change_impact_contract,
    derive_aws_core_observed_usage,
    derive_aws_execution_projection,
    derive_coverage_contract,
    derive_design_contract,
    derive_deployment_sequence_state,
    derive_intake_foundation_contract,
    derive_req_aws_materiality,
    derive_read_preflight_state,
    derive_requirements_contract,
    derive_teardown_sequence_state,
    evaluate_adr_rationale,
    parse_aws_core_evidence,
)
from .core.diagnostics import Diagnostic, DiagnosticCollector
from .core.snapshot import ProjectSnapshot

__all__ = (
    "Diagnostic",
    "DiagnosticCollector",
    "AwsAuthorityPolicy",
    "AwsCoreEvidenceRow",
    "DesignContract",
    "IntakeFoundationContract",
    "ProjectSnapshot",
    "RequirementsContract",
    "capture_project_snapshot",
    "inspect_project",
    "aws_core_phase_evidence_issues",
    "derive_change_impact_contract",
    "derive_aws_core_observed_usage",
    "derive_aws_execution_projection",
    "derive_coverage_contract",
    "derive_design_contract",
    "derive_deployment_sequence_state",
    "derive_intake_foundation_contract",
    "derive_req_aws_materiality",
    "derive_read_preflight_state",
    "derive_requirements_contract",
    "derive_teardown_sequence_state",
    "evaluate_adr_rationale",
    "parse_aws_core_evidence",
)
