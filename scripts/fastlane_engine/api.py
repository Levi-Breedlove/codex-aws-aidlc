"""Supported read-only entry points for the Fastlane Engine foundation.

Inputs are repository-relative paths and caller-supplied observation policy.
Outputs are immutable snapshots, Define projections, or Design projections.
Snapshot capture may read bounded regular files; domain evaluators consume caller-supplied text and
perform no I/O. The API never writes, runs Git, invokes AWS, approves a gate, or
grants authority.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from .core.snapshot import ProjectSnapshot, SnapshotObserver
from .define import (
    IntakeFoundationContract,
    RequirementsContract,
    derive_change_impact_contract,
    derive_coverage_contract,
    derive_intake_foundation_contract,
    derive_req_aws_materiality,
    derive_requirements_contract,
)
from .design import (
    DesignContract,
    derive_design_contract,
    evaluate_adr_rationale,
)


def capture_project_snapshot(
    root: Path,
    paths: Iterable[str],
    *,
    text_paths: Iterable[str] = (),
    canonicalize_text: Callable[[str, str], str] | None = None,
) -> ProjectSnapshot:
    """Capture one bounded immutable snapshot without deriving lifecycle policy.

    Every requested path is opened at most once. Observation failures raise the
    fail-closed ``ObservationError`` supplied by ``core.snapshot``; callers map
    that error to their existing diagnostic surface.
    """

    text_set = frozenset(text_paths)
    observer = SnapshotObserver(root, canonicalize_text=canonicalize_text)
    for relative in paths:
        if relative in text_set:
            observer.observe_text(relative)
        else:
            observer.observe_binary(relative)
    return observer.freeze()


__all__ = (
    "IntakeFoundationContract",
    "DesignContract",
    "ProjectSnapshot",
    "RequirementsContract",
    "capture_project_snapshot",
    "derive_change_impact_contract",
    "derive_coverage_contract",
    "derive_design_contract",
    "derive_intake_foundation_contract",
    "derive_req_aws_materiality",
    "derive_requirements_contract",
    "evaluate_adr_rationale",
)
