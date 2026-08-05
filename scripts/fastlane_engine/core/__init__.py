"""Pure shared foundations for Fastlane Engine domains."""

from .diagnostics import Diagnostic, DiagnosticCollector, DiagnosticDefinition
from .snapshot import FileSnapshot, ProjectSnapshot, SnapshotObserver

__all__ = (
    "Diagnostic",
    "DiagnosticCollector",
    "DiagnosticDefinition",
    "FileSnapshot",
    "ProjectSnapshot",
    "SnapshotObserver",
)
