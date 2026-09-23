"""Bound maintainer checks to repository source or an extracted package inventory."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path, PurePosixPath

from scripts.fastlane_process import resolve_trusted_git


def source_files(root: Path) -> tuple[Path, ...]:
    root = root.resolve()
    if (root / ".git").exists():
        result = subprocess.run(
            [
                resolve_trusted_git(root),
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            check=True,
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
        names = set(result.stdout.rstrip("\0").split("\0")) - {""}
    else:
        manifest = json.loads(
            (root / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        names = set(manifest["required_files"]) | {"bootstrap.manifest.json"}
    files = []
    for name in sorted(names):
        relative = PurePosixPath(name)
        path = root.joinpath(*relative.parts)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or ":" in name
            or not path.resolve().is_relative_to(root)
        ):
            raise ValueError(f"Source inventory path escapes the repository: {name}")
        if path.is_file():
            files.append(path)
    return tuple(files)
