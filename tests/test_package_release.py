from __future__ import annotations

import hashlib
import io
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "package_release.py"
TEMPLATE_SOURCE_MODE = "{{SETUP_STATUS}}" in (
    REPOSITORY_ROOT / "bootstrap.yaml"
).read_text(encoding="utf-8")
source_template_only = unittest.skipUnless(
    TEMPLATE_SOURCE_MODE,
    "maintainer source-integrity test is not applicable after project configuration",
)
SPEC = importlib.util.spec_from_file_location("package_release", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
package_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_release)


class PackageReleaseTests(unittest.TestCase):
    def test_ci_workflow_is_read_only_hosted_and_immutably_pinned(self) -> None:
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        checkout = (
            "actions/checkout@8e8c483db84b4bee98b60c0593521ed34d9990e8 "
            "# v6.0.1"
        )
        setup_python = (
            "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 "
            "# v6.3.0"
        )
        action_uses = [
            line.split("uses:", 1)[1].strip()
            for line in workflow.splitlines()
            if "uses:" in line
        ]

        self.assertEqual(
            action_uses,
            [checkout, setup_python, checkout, setup_python, checkout, setup_python],
        )
        self.assertEqual(workflow.count("persist-credentials: false"), 3)
        self.assertIn("permissions:\n  contents: read\n", workflow)
        for forbidden in (
            "self-hosted",
            "secrets.",
            "upload-artifact",
            "pull_request_target",
            "contents: write",
            "actions: write",
            "id-token: write",
        ):
            self.assertNotIn(forbidden, workflow)

    def test_active_project_documents_are_grouped_under_docs_project(self) -> None:
        document_names = ("BUGFIX.md", "PRD.md", "RUNBOOK.md", "TASKS.md", "VERIFY.md")
        manifest = json.loads(
            (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        for name in document_names:
            canonical = f"docs/project/{name}"
            self.assertTrue((REPOSITORY_ROOT / canonical).is_file(), canonical)
            self.assertIn(canonical, manifest["required_files"])
            self.assertFalse((REPOSITORY_ROOT / name).exists(), name)

    def test_manifest_is_the_only_internal_version_source(self) -> None:
        manifest = json.loads(
            (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["bootstrap_version"], "1.0.1")
        self.assertIn("README.md", manifest["required_files"])
        for removed in ("VERSION", "CONTRIBUTING.md", "CHANGELOG.md"):
            self.assertFalse((REPOSITORY_ROOT / removed).exists())
            self.assertNotIn(removed, manifest["required_files"])
            self.assertNotIn(
                removed,
                (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8"),
            )

    def test_readme_release_links_match_manifest_version(self) -> None:
        manifest = json.loads(
            (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        linked_versions = re.findall(r"releases/(?:download|tag)/v(\d+\.\d+\.\d+)", readme)
        self.assertTrue(
            all(version == manifest["bootstrap_version"] for version in linked_versions),
            linked_versions,
        )

    def test_release_contains_official_aws_core_setup_assets(self) -> None:
        _version, files = package_release.load_release_files(REPOSITORY_ROOT)
        inventory = {path for path, _content in files}
        for required in (
            "docs/SETUP.md",
            "docs/TROUBLESHOOTING.md",
            "docs/DEPENDENCY-POLICY.md",
            "docs/WORKFLOW.md",
            "scripts/setup_assistant.py",
            "tests/test_setup_assistant.py",
        ):
            self.assertIn(required, inventory)

    def test_manifest_is_the_exact_template_file_inventory(self) -> None:
        template = REPOSITORY_ROOT
        actual = {
            path.relative_to(template).as_posix()
            for path in template.rglob("*")
            if path.is_file()
            and ".git" not in path.parts
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
            and "dist" not in path.parts
        }
        manifest = json.loads(
            (template / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        expected = set(manifest["required_files"])
        self.assertEqual(actual, expected)
        self.assertEqual(manifest["required_files"], sorted(expected))

    def test_archive_is_an_exact_deterministic_projection(self) -> None:
        first = package_release.build_release_bytes(REPOSITORY_ROOT)
        second = package_release.build_release_bytes(REPOSITORY_ROOT)
        self.assertEqual(first, second)

        _version, files = package_release.load_release_files(REPOSITORY_ROOT)
        expected_names = [
            package_release.archive_member(relative) for relative, _content in files
        ]
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            infos = archive.infolist()
            self.assertEqual([info.filename for info in infos], expected_names)
            self.assertIsNone(archive.testzip())
            for info, (_relative, content) in zip(infos, files, strict=True):
                self.assertEqual(info.date_time, package_release.FIXED_TIMESTAMP)
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.create_system, 3)
                self.assertEqual(info.external_attr >> 16, stat.S_IFREG | 0o644)
                self.assertEqual(info.extra, b"")
                self.assertEqual(info.comment, b"")
                self.assertEqual(archive.read(info), content)
                self.assertFalse(info.filename.endswith((".zip", ".zip.sha256")))

    def test_extracted_release_configures_in_place_and_passes_doctor(self) -> None:
        payload = package_release.build_release_bytes(REPOSITORY_ROOT)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                archive.extractall(destination)
            project = destination / package_release.ARCHIVE_ROOT
            setup = subprocess.run(
                [
                    sys.executable,
                    "bootstrap.py",
                    "--target",
                    str(project),
                    "--project-name",
                    "Release ZIP Example",
                    "--region",
                    "us-west-2",
                    "--cost-posture",
                    "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                    "--in-place-template-instance",
                ],
                cwd=project,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
            dependencies = subprocess.run(
                [
                    sys.executable,
                    "scripts/bootstrap_dependencies.py",
                    "--root",
                    str(project),
                    "--json",
                ],
                cwd=project,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                dependencies.returncode,
                0,
                dependencies.stdout + dependencies.stderr,
            )
            dependency_report = json.loads(dependencies.stdout)
            self.assertEqual(dependency_report["status"], "READY")
            doctor = subprocess.run(
                [
                    sys.executable,
                    "scripts/bootstrap_doctor.py",
                    "--root",
                    str(project),
                    "--json",
                ],
                cwd=project,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
            report = json.loads(doctor.stdout)
            self.assertEqual(report["classification"], "ACTIVE_GREENFIELD")
            self.assertEqual(report["status"], "READY")
            self.assertEqual(report["next_prompt"], "INTAKE-10")

    @source_template_only
    def test_manifest_hashes_are_current(self) -> None:
        manifest_check = subprocess.run(
            [sys.executable, "scripts/update_manifest.py", "--check"],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            manifest_check.returncode,
            0,
            manifest_check.stdout + manifest_check.stderr,
        )

    def test_public_template_has_no_demo_or_simulation_entrypoint(self) -> None:
        self.assertFalse((REPOSITORY_ROOT / "scripts" / "run_demo.py").exists())
        manifest = json.loads(
            (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("scripts/run_demo.py", manifest["required_files"])
        self.assertNotIn(
            "docs/demo/internal-change-request-api.md",
            manifest["required_files"],
        )
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("run_demo.py", readme)
        self.assertNotIn("docs/demo/", readme)

    def test_written_checksum_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / package_release.ARCHIVE_NAME
            digest = package_release.write_release(REPOSITORY_ROOT, archive_path)
            self.assertEqual(digest, hashlib.sha256(archive_path.read_bytes()).hexdigest())
            self.assertEqual(
                package_release.checksum_path(archive_path).read_text(encoding="ascii"),
                f"{digest}  {archive_path.name}\n",
            )

    def test_check_cli_validates_without_committed_artifacts(self) -> None:
        self.assertFalse((REPOSITORY_ROOT / package_release.ARCHIVE_NAME).exists())
        self.assertFalse(
            (REPOSITORY_ROOT / f"{package_release.ARCHIVE_NAME}.sha256").exists()
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--check"],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Release package verified in memory", result.stdout)

    def test_default_output_is_ignored_dist_directory(self) -> None:
        default_output = (
            REPOSITORY_ROOT
            / package_release.DEFAULT_OUTPUT_DIRECTORY
            / package_release.ARCHIVE_NAME
        )
        self.assertEqual(default_output.parent.name, "dist")
        gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/dist/", gitignore.splitlines())

    def test_check_release_rejects_non_deterministic_builds(self) -> None:
        with mock.patch.object(
            package_release,
            "build_release_bytes",
            side_effect=[b"first", b"second"],
        ):
            with self.assertRaisesRegex(
                package_release.PackagingError,
                "different bytes",
            ):
                package_release.check_release(REPOSITORY_ROOT)

    def test_check_cli_rejects_stale_manifest_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            shutil.copytree(
                REPOSITORY_ROOT,
                root,
                ignore=shutil.ignore_patterns(
                    ".git", "__pycache__", "*.pyc", "dist"
                ),
            )
            refresh = subprocess.run(
                [sys.executable, "scripts/update_manifest.py", "--write"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(refresh.returncode, 0, refresh.stdout + refresh.stderr)
            readme = root / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8") + "\nSynthetic stale hash.\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, "scripts/package_release.py", "--check"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "Manifest source hash mismatch: README.md",
                result.stdout,
            )

    def test_check_cli_rejects_stale_control_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            shutil.copytree(
                REPOSITORY_ROOT,
                root,
                ignore=shutil.ignore_patterns(
                    ".git", "__pycache__", "*.pyc", "dist"
                ),
            )
            refresh = subprocess.run(
                [sys.executable, "scripts/update_manifest.py", "--write"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(refresh.returncode, 0, refresh.stdout + refresh.stderr)
            manifest_path = root / "bootstrap.manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["control_sha256"]["bootstrap.py"] = "0" * 64
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, "scripts/package_release.py", "--check"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "Manifest control hash mismatch: bootstrap.py",
                result.stdout,
            )

    def test_custom_output_checksum_names_custom_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "custom-fastlane.zip"
            digest = package_release.write_release(REPOSITORY_ROOT, archive_path)
            self.assertEqual(
                package_release.checksum_path(archive_path).read_text(encoding="ascii"),
                f"{digest}  {archive_path.name}\n",
            )
            self.assertEqual(
                package_release.expected_artifacts(
                    REPOSITORY_ROOT,
                    archive_path.name,
                ),
                (
                    archive_path.read_bytes(),
                    package_release.checksum_path(archive_path).read_bytes(),
                ),
            )

    def test_unsafe_manifest_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bootstrap.manifest.json").write_text(
                json.dumps(
                    {
                        "bootstrap_version": "1.0.0",
                        "required_files": ["../outside"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(package_release.PackagingError, "Unsafe"):
                package_release.load_release_files(root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_symlinked_release_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root
            outside = root / "outside"
            outside.write_text("not release content", encoding="utf-8")
            try:
                (template / "README.md").symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"Symbolic links are unavailable: {exc}")
            (template / "bootstrap.manifest.json").write_text(
                json.dumps(
                    {
                        "bootstrap_version": "1.0.0",
                        "required_files": ["README.md"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(package_release.PackagingError, "unsafe"):
                package_release.load_release_files(root)

    def test_invalid_manifest_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root
            (template / "bootstrap.manifest.json").write_text(
                json.dumps(
                    {
                        "bootstrap_version": "personal",
                        "required_files": ["bootstrap.manifest.json"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(package_release.PackagingError, "semantic version"):
                package_release.load_release_files(root)

    def test_current_release_text_rejects_stale_versions_except_fixtures(self) -> None:
        stale_product_version = "1" + ".2.0"
        stale_versions = ("1" + ".0.0", "2" + ".0.0", stale_product_version)
        negative_fixture_marker = f'"bootstrap_version": "{stale_versions[0]}"'
        text_suffixes = {".md", ".json", ".yaml", ".yml", ".py", ".txt"}
        allowed_negative_fixtures = 0
        allowed_aws_version_observations = 0
        violations: list[str] = []
        for path in REPOSITORY_ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if path.suffix not in text_suffixes:
                continue
            content = path.read_text(encoding="utf-8")
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            for line_number, line in enumerate(content.splitlines(), start=1):
                for version in stale_versions:
                    if version not in line:
                        continue
                    if (
                        relative == "tests/test_package_release.py"
                        and version == stale_versions[0]
                        and negative_fixture_marker in line
                    ):
                        allowed_negative_fixtures += 1
                        continue
                    if (
                        relative == "tests/test_bootstrap_doctor.py"
                        and version == stale_product_version
                        and "plugin_version: str =" in line
                    ):
                        allowed_aws_version_observations += 1
                        continue
                    violations.append(f"{relative}:{line_number}:{version}")
        self.assertEqual(allowed_negative_fixtures, 2)
        self.assertEqual(allowed_aws_version_observations, 2)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
