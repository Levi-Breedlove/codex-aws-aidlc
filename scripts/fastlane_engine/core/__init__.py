"""Pure shared foundations for Fastlane Engine domains."""

from .diagnostics import Diagnostic, DiagnosticCollector, DiagnosticDefinition
from .snapshot import (
    DirectoryEntrySnapshot,
    DirectorySnapshot,
    FileSnapshot,
    GitObserver,
    GitQueryKey,
    GitQueryResult,
    GitSnapshot,
    ProjectSnapshot,
    SnapshotObserver,
)

__all__ = (
    "Diagnostic",
    "DiagnosticCollector",
    "DiagnosticDefinition",
    "DirectoryEntrySnapshot",
    "DirectorySnapshot",
    "FileSnapshot",
    "GitObserver",
    "GitQueryKey",
    "GitQueryResult",
    "GitSnapshot",
    "ProjectSnapshot",
    "SnapshotObserver",
)
