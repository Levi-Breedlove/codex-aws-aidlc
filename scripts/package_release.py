#!/usr/bin/env python3
"""Build or verify the deterministic AWS Codex Fastlane release archive."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIRECTORY = "."
MANIFEST_FILE = "bootstrap.manifest.json"
ARCHIVE_NAME = "aws-codex-fastlane-bootstrap.zip"
ARCHIVE_ROOT = "aws-codex-fastlane-bootstrap"
DEFAULT_OUTPUT_DIRECTORY = "dist"
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
SEMVER_PATTERN = re.compile(r"\d+\.\d+\.\d+")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REQUIRED_SETUP_ASSETS = {
    "docs/DEPENDENCY-POLICY.md",
    "docs/SETUP.md",
    "docs/TROUBLESHOOTING.md",
    "docs/WORKFLOW.md",
    "scripts/setup_assistant.py",
}
REQUIRED_CONTROL_FILES = {
    "bootstrap.py",
    "scripts/bootstrap_dependencies.py",
    "scripts/bootstrap_doctor.py",
    "scripts/fastlane_stdio.py",
    "scripts/setup_assistant.py",
    "scripts/task_waves.py",
}


class PackagingError(ValueError):
    """Raised when release inputs or generated artifacts are unsafe or stale."""


def checksum_path(archive_path: Path) -> Path:
    """Return the checksum sidecar path for an archive."""

    return archive_path.with_name(f"{archive_path.name}.sha256")


def validate_relative_path(raw: object) -> str:
    """Return one canonical, safe, repository-relative POSIX path."""

    if (
        not isinstance(raw, str)
        or not raw
        or raw == "."
        or "\\" in raw
        or "\x00" in raw
        or any(character in raw for character in "*?[]{}")
    ):
        raise PackagingError(f"Unsafe manifest path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(
        part in {"", ".", ".."} or part.casefold() == ".git"
        for part in path.parts
    ):
        raise PackagingError(f"Unsafe manifest path: {raw!r}")
    canonical = path.as_posix()
    if canonical != raw:
        raise PackagingError(f"Non-canonical manifest path: {raw!r}")
    return canonical


def has_symlink_component(root: Path, relative: str) -> bool:
    """Return whether a manifest path traverses or names a symbolic link."""

    current = root
    if current.is_symlink():
        return True
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def validate_manifest_hashes(
    manifest: dict[str, object],
    files: list[tuple[str, bytes]],
) -> None:
    """Require exact, current source and control hashes in the manifest."""

    contents = dict(files)
    expected_sources = set(contents) - {MANIFEST_FILE}
    missing_controls = sorted(REQUIRED_CONTROL_FILES - set(contents))
    if missing_controls:
        raise PackagingError(
            "Manifest omits required control files: " + ", ".join(missing_controls)
        )

    def require_hashes(field: str, expected_paths: set[str]) -> dict[str, object]:
        hashes = manifest.get(field)
        if not isinstance(hashes, dict):
            raise PackagingError(f"Manifest {field} must be an object")
        actual_paths = set(hashes)
        if actual_paths != expected_paths:
            missing = sorted(expected_paths - actual_paths)
            unexpected = sorted(actual_paths - expected_paths)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            raise PackagingError(
                f"Manifest {field} inventory is incorrect: " + "; ".join(details)
            )
        for relative in sorted(expected_paths):
            stored = hashes[relative]
            if not isinstance(stored, str) or SHA256_PATTERN.fullmatch(stored) is None:
                raise PackagingError(f"Manifest {field} hash is invalid: {relative}")
            actual = hashlib.sha256(contents[relative]).hexdigest()
            if stored != actual:
                label = "source" if field == "source_sha256" else "control"
                raise PackagingError(f"Manifest {label} hash mismatch: {relative}")
        return hashes

    source_hashes = require_hashes("source_sha256", expected_sources)
    control_hashes = require_hashes("control_sha256", REQUIRED_CONTROL_FILES)
    for relative in sorted(REQUIRED_CONTROL_FILES):
        if control_hashes[relative] != source_hashes[relative]:
            raise PackagingError(
                f"Manifest source and control hashes disagree: {relative}"
            )


def load_release_files(repo_root: Path = REPOSITORY_ROOT) -> tuple[str, list[tuple[str, bytes]]]:
    """Load the manifest version and exact release file bytes."""

    repo_root = repo_root.resolve()
    template_root = (repo_root / TEMPLATE_DIRECTORY).resolve()
    manifest_path = template_root / MANIFEST_FILE
    if template_root.is_symlink() or not template_root.is_dir():
        raise PackagingError(f"Template directory is missing or unsafe: {template_root}")
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PackagingError(f"Manifest is missing or unsafe: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagingError(f"Unable to read release manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PackagingError("Release manifest must be a JSON object")
    version = manifest.get("bootstrap_version")
    if not isinstance(version, str) or SEMVER_PATTERN.fullmatch(version) is None:
        raise PackagingError(
            "bootstrap.manifest.json bootstrap_version must contain one semantic version"
        )
    raw_files = manifest.get("required_files")
    if not isinstance(raw_files, list) or not raw_files:
        raise PackagingError("Manifest required_files must be a non-empty array")
    if tuple(int(part) for part in version.split(".")) >= (1, 1, 0):
        inventory = {item for item in raw_files if isinstance(item, str)}
        missing_setup = sorted(REQUIRED_SETUP_ASSETS - inventory)
        if missing_setup:
            raise PackagingError(
                "Manifest omits official AWS Core setup assets: "
                + ", ".join(missing_setup)
            )
    files: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    folded: set[str] = set()
    for raw in raw_files:
        relative = validate_relative_path(raw)
        if relative in seen or relative.casefold() in folded:
            raise PackagingError(f"Duplicate or case-colliding manifest path: {relative}")
        seen.add(relative)
        folded.add(relative.casefold())
        source = template_root.joinpath(*PurePosixPath(relative).parts)
        if has_symlink_component(template_root, relative) or not source.is_file():
            raise PackagingError(f"Release file is missing or unsafe: {relative}")
        files.append((relative, source.read_bytes()))

    if [path for path, _ in files] != sorted(seen):
        raise PackagingError("Manifest required_files must be sorted canonically")
    validate_manifest_hashes(manifest, files)
    return version, files


def archive_member(relative: str) -> str:
    """Return the fixed archive member name for one template path."""

    return f"{ARCHIVE_ROOT}/{relative}"


def build_release_bytes(repo_root: Path = REPOSITORY_ROOT) -> bytes:
    """Build deterministic ZIP bytes from the exact manifest inventory."""

    _version, files = load_release_files(repo_root)
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for relative, content in files:
            info = zipfile.ZipInfo(archive_member(relative), date_time=FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.create_version = 20
            info.extract_version = 20
            info.flag_bits = 0x800
            info.internal_attr = 0
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, content)
    payload = output.getvalue()
    validate_archive_bytes(payload, files)
    return payload


def validate_archive_bytes(payload: bytes, files: list[tuple[str, bytes]]) -> None:
    """Prove archive inventory, metadata, and content match the release inputs."""

    expected_names = [archive_member(relative) for relative, _ in files]
    with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
        if archive.testzip() is not None:
            raise PackagingError("Generated archive failed its CRC integrity check")
        infos = archive.infolist()
        if [info.filename for info in infos] != expected_names:
            raise PackagingError("Generated archive inventory or ordering is incorrect")
        for info, (_relative, expected) in zip(infos, files, strict=True):
            if (
                info.date_time != FIXED_TIMESTAMP
                or info.compress_type != zipfile.ZIP_STORED
                or info.create_system != 3
                or info.external_attr >> 16 != stat.S_IFREG | 0o644
                or info.extra
                or info.comment
            ):
                raise PackagingError(f"Non-deterministic metadata: {info.filename}")
            if info.flag_bits & 0x1:
                raise PackagingError(f"Encrypted archive member: {info.filename}")
            if archive.read(info) != expected:
                raise PackagingError(f"Archive content mismatch: {info.filename}")


def checksum_line(payload: bytes, archive_name: str = ARCHIVE_NAME) -> bytes:
    """Return a standard SHA-256 checksum sidecar line."""

    digest = hashlib.sha256(payload).hexdigest()
    return f"{digest}  {archive_name}\n".encode("ascii")


def atomic_write(path: Path, content: bytes) -> None:
    """Replace one artifact atomically without following an output symlink."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def expected_artifacts(
    repo_root: Path = REPOSITORY_ROOT,
    archive_name: str = ARCHIVE_NAME,
) -> tuple[bytes, bytes]:
    """Return exact expected archive and checksum bytes."""

    payload = build_release_bytes(repo_root)
    return payload, checksum_line(payload, archive_name)


def write_release(repo_root: Path, archive_path: Path) -> str:
    """Write the deterministic archive and checksum and return its digest."""

    payload, sidecar = expected_artifacts(repo_root, archive_path.name)
    atomic_write(archive_path, payload)
    atomic_write(checksum_path(archive_path), sidecar)
    return hashlib.sha256(payload).hexdigest()


def check_release(repo_root: Path = REPOSITORY_ROOT) -> str:
    """Build twice in memory and require byte-for-byte deterministic output."""

    first = build_release_bytes(repo_root)
    second = build_release_bytes(repo_root)
    if first != second:
        raise PackagingError("Repeated release builds produced different bytes")
    return hashlib.sha256(first).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify the deterministic Fastlane release package."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the manifest and deterministic archive bytes without writing files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / DEFAULT_OUTPUT_DIRECTORY / ARCHIVE_NAME,
        help=(
            "Archive output path "
            f"(default: {DEFAULT_OUTPUT_DIRECTORY}/{ARCHIVE_NAME})"
        ),
    )
    args = parser.parse_args(argv)
    archive_path = args.output.expanduser().resolve()
    try:
        if args.check:
            digest = check_release(REPOSITORY_ROOT)
            print("Release package verified in memory")
            print(f"SHA-256: {digest}")
            return 0
        else:
            digest = write_release(REPOSITORY_ROOT, archive_path)
    except (OSError, PackagingError, zipfile.BadZipFile) as exc:
        print(f"Release package failed: {exc}")
        return 1

    print(f"Release package wrote: {archive_path}")
    print(f"SHA-256: {digest}")
    print(f"Checksum: {checksum_path(archive_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
