from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.fastlane_process import resolve_trusted_git
from tests.repository_sources import source_files


class RepositorySourcesTests(unittest.TestCase):
    def test_git_inventory_keeps_tracked_and_new_source_but_not_ignored_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = resolve_trusted_git(root)
            subprocess.run([git, "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text(
                "tmp/\ndist/\n*.local.md\n", encoding="utf-8"
            )
            (root / "tracked.md").write_text("# Current source", encoding="utf-8")
            subprocess.run([git, "-C", str(root), "add", "tracked.md"], check=True)
            (root / "new.md").write_text("[Broken](missing.md)", encoding="utf-8")
            for name in ("tmp/AGENTS.md", "dist/README.md", "notes.local.md"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("[Old backup](old.md)", encoding="utf-8")
            self.assertEqual(
                {path.relative_to(root).as_posix() for path in source_files(root)},
                {".gitignore", "tracked.md", "new.md"},
            )
            subprocess.run(
                [git, "-C", str(root), "add", "-f", "notes.local.md"], check=True
            )
            self.assertIn(root / "notes.local.md", source_files(root))

    def test_extracted_inventory_uses_manifest_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "bootstrap.manifest.json"
            (root / "README.md").write_text("# Package", encoding="utf-8")
            (root / "backup.md").write_text("# Old copy", encoding="utf-8")
            manifest.write_text(
                json.dumps({"required_files": ["README.md"]}), encoding="utf-8"
            )
            self.assertEqual(set(source_files(root)), {manifest, root / "README.md"})
            manifest.write_text(
                json.dumps({"required_files": ["../escape.md"]}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "escapes"):
                source_files(root)
