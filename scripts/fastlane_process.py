#!/usr/bin/env python3
"""Trusted local-process resolution shared by Fastlane runtime controls."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path


def _lexical_absolute(path: Path) -> Path:
    """Return an absolute path without following filesystem links."""

    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _is_within(path: Path, boundary: Path) -> bool:
    try:
        path.relative_to(boundary)
    except ValueError:
        return False
    return True


def _git_candidates_from_absolute_path_entries() -> Iterator[str]:
    """Yield Git candidates without allowing implicit current-directory search."""

    for raw_entry in os.environ.get("PATH", "").split(os.pathsep):
        entry_text = os.path.expandvars(raw_entry.strip().strip('"'))
        if not entry_text:
            continue
        entry = Path(entry_text).expanduser()
        if not entry.is_absolute():
            continue
        located = shutil.which(os.fspath(entry / "git"))
        if located:
            yield located


def resolve_trusted_git(
    project_root: Path,
    *,
    locator: Callable[[str], str | None] | None = None,
) -> str:
    """Resolve Git to one absolute regular file outside untrusted work trees."""

    try:
        root_lexical = _lexical_absolute(project_root)
        root_resolved = root_lexical.resolve(strict=True)
        cwd_lexical = _lexical_absolute(Path.cwd())
        cwd_resolved = cwd_lexical.resolve(strict=True)
    except OSError as exc:
        raise OSError("Trusted Git executable is unavailable or unsafe") from exc

    if locator is not None:
        located = locator("git")
        candidate_values = () if not located else (located,)
    else:
        candidate_values = _git_candidates_from_absolute_path_entries()

    for candidate_value in candidate_values:
        try:
            raw_candidate = Path(candidate_value).expanduser()
            if not raw_candidate.is_absolute():
                continue
            candidate_lexical = _lexical_absolute(raw_candidate)
            candidate_resolved = candidate_lexical.resolve(strict=True)
        except OSError:
            continue
        if not candidate_resolved.is_file():
            continue
        if any(
            _is_within(candidate, boundary)
            for candidate in (candidate_lexical, candidate_resolved)
            for boundary in (
                root_lexical,
                root_resolved,
                cwd_lexical,
                cwd_resolved,
            )
        ):
            continue
        return str(candidate_resolved)
    raise OSError("Trusted Git executable is unavailable or unsafe")
