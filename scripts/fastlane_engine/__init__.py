"""Fastlane's read-only canonical validation Engine.

Canonical inputs are immutable project snapshots and existing project records.
The package returns diagnostics and derived projections without writing project
state, authorizing an action, or rendering owner conversation. Public CLI
compatibility remains in :mod:`scripts.bootstrap_doctor`.
"""

from .api import capture_project_snapshot
from .core.diagnostics import Diagnostic, DiagnosticCollector
from .core.snapshot import ProjectSnapshot

__all__ = (
    "Diagnostic",
    "DiagnosticCollector",
    "ProjectSnapshot",
    "capture_project_snapshot",
)
