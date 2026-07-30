from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.fastlane_process import resolve_trusted_git


class TrustedGitResolutionTests(unittest.TestCase):
    def _create_directory_link(self, link: Path, target: Path) -> None:
        """Create a directory symlink or Windows junction for link tests."""

        try:
            link.symlink_to(target, target_is_directory=True)
            return
        except OSError as symlink_error:
            if os.name != "nt":
                self.skipTest(f"Directory links are unavailable: {symlink_error}")
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.skipTest("Directory symlinks and Windows junctions are unavailable")

    @staticmethod
    def _remove_directory_link(link: Path) -> None:
        """Remove a test link without traversing its target."""

        if link.is_symlink():
            link.unlink()
        elif link.exists():
            link.rmdir()

    def _file(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"trusted executable fixture")
        return path

    def test_external_regular_file_is_returned_as_an_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "project"
            root.mkdir()
            executable = self._file(base / "tools" / "git.exe")

            resolved = resolve_trusted_git(root, locator=lambda _name: str(executable))

            self.assertEqual(Path(resolved), executable.resolve(strict=True))
            self.assertTrue(Path(resolved).is_absolute())

    def test_missing_relative_or_project_local_git_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            local = self._file(root / "git.exe")
            for candidate in (None, str(local), "git.exe"):
                with (
                    self.subTest(candidate=candidate),
                    self.assertRaisesRegex(OSError, "Trusted Git executable"),
                ):
                    previous = Path.cwd()
                    try:
                        os.chdir(root)
                        resolve_trusted_git(root, locator=lambda _name: candidate)
                    finally:
                        os.chdir(previous)

    def test_sibling_process_cwd_executable_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "project"
            process_cwd = base / "process-cwd"
            root.mkdir()
            process_cwd.mkdir()
            local = self._file(process_cwd / "git.exe")
            previous = Path.cwd()
            try:
                os.chdir(process_cwd)
                with self.assertRaisesRegex(OSError, "Trusted Git executable"):
                    resolve_trusted_git(root, locator=lambda _name: str(local))
            finally:
                os.chdir(previous)

    def test_default_locator_never_falls_back_to_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "project"
            process_cwd = base / "process-cwd"
            root.mkdir()
            process_cwd.mkdir()
            self._file(process_cwd / "git.exe")
            previous = Path.cwd()
            try:
                os.chdir(process_cwd)
                with mock.patch.dict(os.environ, {"PATH": ""}, clear=False):
                    with self.assertRaisesRegex(OSError, "Trusted Git executable"):
                        resolve_trusted_git(root)
            finally:
                os.chdir(previous)

    def test_outside_directory_link_into_project_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "project"
            target_directory = root / "tools"
            target_directory.mkdir(parents=True)
            self._file(target_directory / "git.exe")
            link_directory = base / "outside-tools"
            self._create_directory_link(link_directory, target_directory)
            try:
                with self.assertRaisesRegex(OSError, "Trusted Git executable"):
                    resolve_trusted_git(
                        root, locator=lambda _name: str(link_directory / "git.exe")
                    )
            finally:
                self._remove_directory_link(link_directory)

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_outside_link_into_project_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "project"
            root.mkdir()
            local = self._file(root / "git.exe")
            link = base / "tools" / "git.exe"
            link.parent.mkdir()
            try:
                link.symlink_to(local)
            except OSError as exc:
                self.skipTest(f"File symlinks are unavailable: {exc}")
            with self.assertRaisesRegex(OSError, "Trusted Git executable"):
                resolve_trusted_git(root, locator=lambda _name: str(link))

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_external_link_to_external_git_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "project"
            root.mkdir()
            target = self._file(base / "system" / "git")
            link = base / "bin" / "git"
            link.parent.mkdir()
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"File symlinks are unavailable: {exc}")
            self.assertEqual(
                Path(resolve_trusted_git(root, locator=lambda _name: str(link))),
                target.resolve(strict=True),
            )


if __name__ == "__main__":
    unittest.main()
