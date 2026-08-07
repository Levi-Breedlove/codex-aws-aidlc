"""Observe ADR files, then delegate pure rationale evaluation to Design.

This compatibility façade performs bounded, read-only filesystem observation.
It never changes canonical project state, selects architecture, approves Gate B,
or grants construction or AWS authority.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Mapping

try:
    from fastlane_engine.design.adr import (
        ADR_AUTHORITY,
        ADR_DIRECTORY,
        ADR_FILE,
        MAX_ADR_BYTES,
        MAX_ADR_FILES,
        UNSAFE_CONTENT,
        _issue,
        _normalized_text,
        derive_adr_rationale as evaluate_adr_rationale,
        empty_adr_rationale,
    )
except ModuleNotFoundError:  # Loaded as scripts.fastlane_adr in unit tests.
    from scripts.fastlane_engine.design.adr import (
        ADR_AUTHORITY,
        ADR_DIRECTORY,
        ADR_FILE,
        MAX_ADR_BYTES,
        MAX_ADR_FILES,
        UNSAFE_CONTENT,
        _issue,
        _normalized_text,
        derive_adr_rationale as evaluate_adr_rationale,
        empty_adr_rationale,
    )

try:
    from fastlane_engine.core.snapshot import ProjectSnapshot
except ModuleNotFoundError:  # Loaded as scripts.fastlane_adr in unit tests.
    from scripts.fastlane_engine.core.snapshot import ProjectSnapshot


def _safe_adr_inventory(root: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Observe safe ADR filenames without following filesystem indirection."""

    issues: list[dict[str, str]] = []
    directory = root / "docs" / "adr"
    for path in (root / "docs", directory):
        if path.is_symlink():
            return {}, [
                _issue(
                    "ADR_RATIONALE_UNSAFE",
                    "The ADR directory must not traverse a symbolic link.",
                    ADR_DIRECTORY,
                )
            ]
    if not directory.is_dir():
        return {}, issues
    paths = sorted(
        path for path in directory.iterdir() if path.name != "0000-template.md"
    )
    if len(paths) > MAX_ADR_FILES:
        return {}, [
            _issue(
                "ADR_RATIONALE_UNSAFE",
                f"At most {MAX_ADR_FILES} ADR files may be evaluated at once.",
                ADR_DIRECTORY,
            )
        ]
    by_id: dict[str, str] = {}
    for path in paths:
        relative = PurePosixPath(ADR_DIRECTORY, path.name).as_posix()
        match = ADR_FILE.fullmatch(path.name)
        if match is None:
            issues.append(
                _issue(
                    "ADR_RATIONALE_UNSAFE",
                    "ADR filenames must use NNNN-lowercase-slug.md.",
                    relative,
                )
            )
            continue
        if path.is_symlink() or not path.is_file():
            issues.append(
                _issue(
                    "ADR_RATIONALE_UNSAFE",
                    "ADR files must be regular files.",
                    ADR_DIRECTORY,
                )
            )
            continue
        adr_id = f"ADR-{match.group('number')}"
        if adr_id in by_id:
            issues.append(
                _issue(
                    "ADR_RATIONALE_DUPLICATE",
                    f"{adr_id} appears in more than one ADR filename.",
                    ADR_DIRECTORY,
                )
            )
        else:
            by_id[adr_id] = relative
    return by_id, issues


def _read_adr(root: Path, relative: str) -> tuple[str | None, dict[str, str] | None]:
    """Read one bounded regular UTF-8 ADR without traversing a symlink."""

    path = root.joinpath(*PurePosixPath(relative).parts)
    try:
        size = path.stat().st_size
        if size > MAX_ADR_BYTES:
            raise ValueError(f"ADR exceeds the {MAX_ADR_BYTES}-byte limit")
        raw = path.read_bytes()
        if len(raw) != size:
            raise ValueError("ADR changed while it was being read")
        text = raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        return None, _issue("ADR_RATIONALE_MALFORMED", str(exc), relative)
    if "\x00" in text or UNSAFE_CONTENT.search(text):
        return None, _issue(
            "ADR_RATIONALE_UNSAFE",
            "ADR content contains unsafe machine, credential, or private-path data.",
            relative,
        )
    return _normalized_text(text), None


def derive_adr_rationale(
    root: Path,
    design_contract: Mapping[str, Any],
    prd_text: str,
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, str]]:
    """Preserve the public ADR API while keeping evaluation filesystem-pure."""

    inventory, inventory_issues = _safe_adr_inventory(root)
    sources: dict[str, str] = {}
    source_issues: dict[str, dict[str, str]] = {}
    for relative in sorted(inventory.values()):
        text, issue = _read_adr(root, relative)
        if issue is not None:
            source_issues[relative] = issue
        elif text is not None:
            sources[relative] = text
    return evaluate_adr_rationale(
        design_contract,
        prd_text,
        inventory,
        sources,
        inventory_issues=inventory_issues,
        source_issues=source_issues,
    )


def derive_adr_rationale_from_snapshot(
    snapshot: ProjectSnapshot,
    design_contract: Mapping[str, Any],
    prd_text: str,
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, str]]:
    """Evaluate ADR rationale from the Engine's already observed bytes."""

    directory = snapshot.directories.get(ADR_DIRECTORY)
    if directory is not None and directory.is_symlink:
        issue = _issue(
            "ADR_RATIONALE_UNSAFE",
            "The ADR directory must not traverse a symbolic link.",
            ADR_DIRECTORY,
        )
        return evaluate_adr_rationale(
            design_contract, prd_text, {}, {}, inventory_issues=[issue]
        )
    if directory is None or not directory.exists or not directory.is_directory:
        return evaluate_adr_rationale(design_contract, prd_text, {}, {})
    paths = [entry for entry in directory.entries if entry.name != "0000-template.md"]
    if len(paths) > MAX_ADR_FILES:
        issue = _issue(
            "ADR_RATIONALE_UNSAFE",
            f"At most {MAX_ADR_FILES} ADR files may be evaluated at once.",
            ADR_DIRECTORY,
        )
        return evaluate_adr_rationale(
            design_contract, prd_text, {}, {}, inventory_issues=[issue]
        )

    inventory: dict[str, str] = {}
    inventory_issues: list[dict[str, str]] = []
    entries_by_path = {entry.path: entry for entry in paths}
    for entry in paths:
        match = ADR_FILE.fullmatch(entry.name)
        if match is None:
            inventory_issues.append(
                _issue(
                    "ADR_RATIONALE_UNSAFE",
                    "ADR filenames must use NNNN-lowercase-slug.md.",
                    entry.path,
                )
            )
            continue
        if entry.is_symlink or not entry.is_file:
            inventory_issues.append(
                _issue(
                    "ADR_RATIONALE_UNSAFE",
                    "ADR files must be regular files.",
                    ADR_DIRECTORY,
                )
            )
            continue
        adr_id = f"ADR-{match.group('number')}"
        if adr_id in inventory:
            inventory_issues.append(
                _issue(
                    "ADR_RATIONALE_DUPLICATE",
                    f"{adr_id} appears in more than one ADR filename.",
                    ADR_DIRECTORY,
                )
            )
        else:
            inventory[adr_id] = entry.path

    sources: dict[str, str] = {}
    source_issues: dict[str, dict[str, str]] = {}
    for relative in sorted(inventory.values()):
        entry = entries_by_path[relative]
        observed = snapshot.file(relative)
        error = snapshot.text_errors.get(relative) or snapshot.file_errors.get(relative)
        if entry.byte_size > MAX_ADR_BYTES:
            source_issues[relative] = _issue(
                "ADR_RATIONALE_MALFORMED",
                f"ADR exceeds the {MAX_ADR_BYTES}-byte limit",
                relative,
            )
            continue
        if error is not None:
            source_issues[relative] = _issue(
                "ADR_RATIONALE_MALFORMED", error.message, relative
            )
            continue
        if observed is None or observed.byte_size != entry.byte_size:
            source_issues[relative] = _issue(
                "ADR_RATIONALE_MALFORMED",
                "ADR changed while it was being read",
                relative,
            )
            continue
        try:
            text = observed.raw_bytes.decode("utf-8")
        except UnicodeError as exc:
            source_issues[relative] = _issue(
                "ADR_RATIONALE_MALFORMED", str(exc), relative
            )
            continue
        if "\x00" in text or UNSAFE_CONTENT.search(text):
            source_issues[relative] = _issue(
                "ADR_RATIONALE_UNSAFE",
                "ADR content contains unsafe machine, credential, or private-path data.",
                relative,
            )
            continue
        sources[relative] = _normalized_text(text)
    return evaluate_adr_rationale(
        design_contract,
        prd_text,
        inventory,
        sources,
        inventory_issues=inventory_issues,
        source_issues=source_issues,
    )


__all__ = (
    "ADR_AUTHORITY",
    "derive_adr_rationale",
    "derive_adr_rationale_from_snapshot",
    "empty_adr_rationale",
)
