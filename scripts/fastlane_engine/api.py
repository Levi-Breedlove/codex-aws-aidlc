"""Supported read-only entry points for the Fastlane Engine foundation.

Inputs are repository-relative paths and caller-supplied observation policy.
Outputs are immutable snapshots. The API may read bounded regular files through
the snapshot observer; it never writes, runs Git, invokes AWS, or grants
authority. Later domain APIs build on this stable observation boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from .core.snapshot import ProjectSnapshot, SnapshotObserver


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
