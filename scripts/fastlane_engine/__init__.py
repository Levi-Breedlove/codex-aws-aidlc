"""Fastlane's read-only canonical validation Engine.

Canonical inputs are immutable project snapshots and existing project records.
The package returns diagnostics and derived projections without writing project
state, authorizing an action, or rendering owner conversation. Public CLI
compatibility remains in :mod:`scripts.bootstrap_doctor`.
"""

from .api import (
    IntakeFoundationContract,
    RequirementsContract,
    capture_project_snapshot,
    derive_change_impact_contract,
    derive_coverage_contract,
    derive_intake_foundation_contract,
    derive_req_aws_materiality,
    derive_requirements_contract,
)
from .core.diagnostics import Diagnostic, DiagnosticCollector
from .core.snapshot import ProjectSnapshot

__all__ = (
    "Diagnostic",
    "DiagnosticCollector",
    "IntakeFoundationContract",
    "ProjectSnapshot",
    "RequirementsContract",
    "capture_project_snapshot",
    "derive_change_impact_contract",
    "derive_coverage_contract",
    "derive_intake_foundation_contract",
    "derive_req_aws_materiality",
    "derive_requirements_contract",
)
