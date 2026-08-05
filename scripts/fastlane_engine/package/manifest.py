"""Deterministic package-manifest and prompt-pack validation.

Canonical inputs are the manifest, bootstrap state, and caller-observed file
bytes. Diagnostics are appended through the supplied compatibility context.
This module performs no independent I/O, lifecycle routing, or authorization.
Its ordering and messages remain compatible with the 1.2.11 Engine façade.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from ..core.ids import validate_relative_path


class ManifestContext(Protocol):
    root: Path
    template_source: bool
    texts: dict[str, str]
    presentation_texts: dict[str, str]
    source_file_bytes: dict[str, bytes]

    def error(self, code: str, message: str, path: str | None = None) -> None: ...


@dataclass(frozen=True)
class ManifestPolicy:
    manifest_file: str
    prompt_file: str
    mandatory_required_files: frozenset[str]
    control_hash_files: frozenset[str]
    canonical_placeholders: frozenset[str]
    max_required_files: int = 512
    binary_required_suffixes: frozenset[str] = frozenset({".png"})


ReadBinary = Callable[[ManifestContext, str], bytes | None]
ReadText = Callable[[ManifestContext, str], str | None]
SymlinkCheck = Callable[[Path, str], bool]


def validate_manifest(
    ctx: ManifestContext,
    manifest: dict[str, Any],
    *,
    policy: ManifestPolicy,
    read_binary: ReadBinary,
    read_text: ReadText,
    has_symlink_component: SymlinkCheck,
) -> None:
    """Validate inventory and hashes in the historical diagnostic order."""

    seen = _validate_inventory(ctx, manifest, policy, read_binary, read_text)
    if seen is None:
        return
    _validate_source_hashes(
        ctx,
        manifest,
        policy,
        seen,
        has_symlink_component,
    )
    _validate_control_hashes(ctx, manifest, policy, has_symlink_component)


def _validate_inventory(
    ctx: ManifestContext,
    manifest: Mapping[str, Any],
    policy: ManifestPolicy,
    read_binary: ReadBinary,
    read_text: ReadText,
) -> set[str] | None:
    expected_fields = {
        "schema_version",
        "bootstrap_version",
        "python_requires",
        "required_files",
        "canonical_prompt_ids",
        "template_placeholders",
        "control_sha256",
        "source_sha256",
    }
    if set(manifest) != expected_fields:
        ctx.error(
            "MANIFEST_SCHEMA",
            f"Manifest fields must be exactly {sorted(expected_fields)}",
            policy.manifest_file,
        )
    if manifest.get("schema_version") != 1:
        ctx.error(
            "MANIFEST_SCHEMA",
            "Unsupported manifest schema_version",
            policy.manifest_file,
        )
    version = manifest.get("bootstrap_version")
    if not isinstance(version, str) or re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        ctx.error(
            "MANIFEST_VERSION",
            "bootstrap_version must be semantic version text",
            policy.manifest_file,
        )

    files = manifest.get("required_files")
    if not isinstance(files, list):
        ctx.error(
            "MANIFEST_REQUIRED_FILES",
            "required_files must be an array",
            policy.manifest_file,
        )
        return None
    if len(files) > policy.max_required_files:
        ctx.error(
            "MANIFEST_REQUIRED_FILES_LIMIT",
            f"required_files exceeds the {policy.max_required_files}-entry limit",
            policy.manifest_file,
        )
        return None

    seen: set[str] = set()
    folded: set[str] = set()
    for item in files:
        relative = validate_relative_path(item)
        if relative is None:
            ctx.error(
                "MANIFEST_UNSAFE_PATH",
                f"Unsafe required_files entry: {item!r}",
                policy.manifest_file,
            )
            continue
        if relative in seen or relative.casefold() in folded:
            ctx.error(
                "MANIFEST_DUPLICATE_PATH",
                f"Duplicate required path: {relative}",
                policy.manifest_file,
            )
            continue
        seen.add(relative)
        folded.add(relative.casefold())
        if PurePosixPath(relative).suffix.lower() in policy.binary_required_suffixes:
            read_binary(ctx, relative)
        else:
            read_text(ctx, relative)

    missing_mandatory = sorted(policy.mandatory_required_files - seen)
    if missing_mandatory:
        ctx.error(
            "MANIFEST_REQUIRED_BASELINE",
            "Manifest omits mandatory control files: " + ", ".join(missing_mandatory),
            policy.manifest_file,
        )
    missing_controls = sorted(policy.control_hash_files - seen)
    if missing_controls:
        ctx.error(
            "MANIFEST_CONTROL_REQUIRED_FILES",
            "Manifest control files must also be required files: "
            + ", ".join(missing_controls),
            policy.manifest_file,
        )
    if set(manifest.get("template_placeholders", [])) != policy.canonical_placeholders:
        ctx.error(
            "MANIFEST_PLACEHOLDERS",
            "template_placeholders must contain the canonical render tokens",
            policy.manifest_file,
        )
    return seen


def _validate_source_hashes(
    ctx: ManifestContext,
    manifest: Mapping[str, Any],
    policy: ManifestPolicy,
    seen: set[str],
    has_symlink_component: SymlinkCheck,
) -> None:
    source_hashes = manifest.get("source_sha256")
    expected_paths = seen - {policy.manifest_file}
    if not isinstance(source_hashes, dict) or set(source_hashes) != expected_paths:
        ctx.error(
            "MANIFEST_SOURCE_HASHES",
            "source_sha256 must map every required file except the manifest itself",
            policy.manifest_file,
        )
        return
    for relative in sorted(expected_paths):
        expected = source_hashes.get(relative)
        if (
            not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
        ):
            ctx.error(
                "MANIFEST_SOURCE_HASHES",
                f"Invalid source SHA-256 for {relative}",
                policy.manifest_file,
            )
            continue
        if not ctx.template_source or has_symlink_component(ctx.root, relative):
            continue
        source_bytes = ctx.source_file_bytes.get(relative)
        if source_bytes is None:
            source_text = ctx.presentation_texts.get(relative) or ctx.texts.get(
                relative
            )
            if source_text is None:
                continue
            source_bytes = source_text.encode("utf-8")
        actual = hashlib.sha256(source_bytes).hexdigest()
        if actual != expected:
            ctx.error(
                "MANIFEST_SOURCE_HASHES",
                f"Template source hash mismatch for {relative}",
                relative,
            )


def _validate_control_hashes(
    ctx: ManifestContext,
    manifest: Mapping[str, Any],
    policy: ManifestPolicy,
    has_symlink_component: SymlinkCheck,
) -> None:
    controls = manifest.get("control_sha256")
    if not isinstance(controls, dict) or set(controls) != policy.control_hash_files:
        ctx.error(
            "MANIFEST_CONTROL_HASHES",
            "control_sha256 must map exactly the trusted runtime control files",
            policy.manifest_file,
        )
        return
    for relative in sorted(policy.control_hash_files):
        expected = controls.get(relative)
        if (
            not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
        ):
            ctx.error(
                "MANIFEST_CONTROL_HASHES",
                f"Invalid SHA-256 for trusted control {relative}",
                policy.manifest_file,
            )
            continue
        if has_symlink_component(ctx.root, relative):
            continue
        control_text = ctx.texts.get(relative)
        if control_text is None:
            continue
        actual = hashlib.sha256(control_text.encode("utf-8")).hexdigest()
        if actual != expected:
            ctx.error(
                "CONTROL_HASH_MISMATCH",
                f"Trusted runtime control hash mismatch: expected {expected}, observed {actual}",
                relative,
            )


def validate_prompt_pack(
    ctx: ManifestContext,
    manifest: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    policy: ManifestPolicy,
    read_text: ReadText,
) -> None:
    """Validate prompt version and canonical heading order without parsing routes."""

    text = ctx.texts.get(policy.prompt_file) or read_text(ctx, policy.prompt_file)
    if text is None:
        return
    version_match = re.search(
        r"^\*\*Pack version:\*\*\s*(\d+\.\d+\.\d+)\s*$", text, re.MULTILINE
    )
    if version_match is None:
        ctx.error(
            "PROMPT_VERSION_MISSING",
            "Prompt pack version is missing",
            policy.prompt_file,
        )
    else:
        versions = {
            str(manifest.get("bootstrap_version")),
            str(state.get("bootstrap_version")),
            version_match.group(1),
        }
        if len(versions) != 1:
            ctx.error(
                "BOOTSTRAP_VERSION_DRIFT",
                f"Version values disagree: {sorted(versions)}",
            )

    expected = manifest.get("canonical_prompt_ids")
    actual = re.findall(r"^##\s+([A-Z]+-\d{2})\s+", text, re.MULTILINE)
    if not isinstance(expected, list) or not all(
        isinstance(item, str) for item in expected
    ):
        ctx.error(
            "PROMPT_IDS_MANIFEST",
            "canonical_prompt_ids must be an array of strings",
            policy.manifest_file,
        )
    elif actual != expected:
        ctx.error(
            "PROMPT_IDS_DRIFT",
            f"Prompt headings do not match manifest order: {actual}",
            policy.prompt_file,
        )
    elif len(actual) != len(set(actual)):
        ctx.error(
            "PROMPT_IDS_DUPLICATE",
            "Canonical prompt IDs must be unique",
            policy.prompt_file,
        )


def validate_placeholders(ctx: ManifestContext, *, policy: ManifestPolicy) -> None:
    """Reject unresolved template tokens in initialized project content."""

    if ctx.template_source:
        return
    excluded = {
        policy.manifest_file,
        "bootstrap.py",
        "scripts/bootstrap_doctor.py",
        "scripts/fastlane_project_identity.py",
    }
    for relative, text in sorted(ctx.texts.items()):
        if relative in excluded or relative.startswith("tests/"):
            continue
        for token in sorted(policy.canonical_placeholders):
            if token in text:
                ctx.error(
                    "PLACEHOLDER_UNRESOLVED",
                    f"Unresolved bootstrap placeholder {token!r}",
                    relative,
                )
