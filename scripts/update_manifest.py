#!/usr/bin/env python3
"""Regenerate or verify the Fastlane manifest's control and source hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "bootstrap.manifest.json"
CONTROL_FILES = (
    "bootstrap.py",
    "scripts/bootstrap_dependencies.py",
    "scripts/bootstrap_doctor.py",
    "scripts/fastlane_adr.py",
    "scripts/fastlane_contracts.py",
    "scripts/fastlane_engine/__init__.py",
    "scripts/fastlane_engine/api.py",
    "scripts/fastlane_engine/core/__init__.py",
    "scripts/fastlane_engine/core/contracts.py",
    "scripts/fastlane_engine/core/diagnostics.py",
    "scripts/fastlane_engine/core/digests.py",
    "scripts/fastlane_engine/core/ids.py",
    "scripts/fastlane_engine/core/markdown_index.py",
    "scripts/fastlane_engine/core/snapshot.py",
    "scripts/fastlane_engine/define/__init__.py",
    "scripts/fastlane_engine/define/coverage.py",
    "scripts/fastlane_engine/define/intake.py",
    "scripts/fastlane_engine/define/models.py",
    "scripts/fastlane_engine/define/project.py",
    "scripts/fastlane_engine/define/requirements.py",
    "scripts/fastlane_engine/design/__init__.py",
    "scripts/fastlane_engine/design/adr.py",
    "scripts/fastlane_engine/design/architecture.py",
    "scripts/fastlane_engine/design/diagrams.py",
    "scripts/fastlane_engine/design/envelope.py",
    "scripts/fastlane_engine/design/harness.py",
    "scripts/fastlane_engine/design/models.py",
    "scripts/fastlane_engine/design/project.py",
    "scripts/fastlane_engine/design/source.py",
    "scripts/fastlane_engine/design/support.py",
    "scripts/fastlane_engine/package/__init__.py",
    "scripts/fastlane_engine/package/manifest.py",
    "scripts/fastlane_engine/package/state.py",
    "scripts/fastlane_process.py",
    "scripts/fastlane_project_identity.py",
    "scripts/fastlane_stdio.py",
    "scripts/setup_assistant.py",
    "scripts/task_waves.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict[str, object]:
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("bootstrap.manifest.json must contain one JSON object")
    return value


def required_paths(manifest: dict[str, object]) -> list[str]:
    raw = manifest.get("required_files")
    if (
        not isinstance(raw, list)
        or not raw
        or not all(isinstance(item, str) for item in raw)
    ):
        raise ValueError("required_files must be a non-empty list of strings")
    required = list(raw)
    if required != sorted(set(required)):
        raise ValueError("required_files must be unique and canonically sorted")
    for relative in required:
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or relative != pure.as_posix():
            raise ValueError(f"unsafe required_files entry: {relative}")
        path = ROOT.joinpath(*pure.parts)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"required file is missing or unsafe: {relative}")
    return required


def expected_hashes(
    manifest: dict[str, object],
) -> tuple[dict[str, str], dict[str, str]]:
    required = required_paths(manifest)
    missing_controls = sorted(set(CONTROL_FILES) - set(required))
    if missing_controls:
        raise ValueError(
            "control files missing from required_files: " + ", ".join(missing_controls)
        )
    controls = {
        relative: sha256(ROOT.joinpath(*PurePosixPath(relative).parts))
        for relative in CONTROL_FILES
    }
    sources = {
        relative: sha256(ROOT.joinpath(*PurePosixPath(relative).parts))
        for relative in required
        if relative != "bootstrap.manifest.json"
    }
    return controls, sources


def render_manifest(manifest: dict[str, object]) -> str:
    controls, sources = expected_hashes(manifest)
    updated = dict(manifest)
    updated["control_sha256"] = controls
    updated["source_sha256"] = sources
    return json.dumps(updated, indent=2, ensure_ascii=False) + "\n"


def write_atomic(text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".bootstrap.manifest.",
        suffix=".tmp",
        dir=ROOT,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, MANIFEST_PATH)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true", help="Fail if stored hashes differ"
    )
    mode.add_argument(
        "--write", action="store_true", help="Atomically write current hashes"
    )
    args = parser.parse_args()
    try:
        manifest = load_manifest()
        rendered = render_manifest(manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Manifest error: {exc}")
        return 1
    if args.check:
        current = MANIFEST_PATH.read_text(encoding="utf-8")
        if current != rendered:
            print("Manifest hashes are stale; run scripts/update_manifest.py --write")
            return 1
        print("Manifest source and control hashes are current.")
        return 0
    write_atomic(rendered)
    print("Updated bootstrap.manifest.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
