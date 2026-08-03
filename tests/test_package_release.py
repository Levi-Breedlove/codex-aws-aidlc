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

from scripts import setup_assistant

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_PACKAGE_VERSION = "1" + ".0.1"

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
    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _create_directory_link(self, link: Path, target: Path) -> None:
        """Create a directory symlink or a Windows junction for link tests."""

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

    def _write_synthetic_package(
        self,
        root: Path,
        version: str,
        marker: str,
        *,
        historical_controls: bool = False,
        extra_path: str | None = None,
    ) -> None:
        controls = set(package_release.REQUIRED_CONTROL_FILES)
        if historical_controls:
            controls.remove("scripts/fastlane_stdio.py")
            controls.remove("scripts/fastlane_process.py")
            controls.remove("scripts/fastlane_project_identity.py")
        contents = {
            relative: f"{relative}: {marker}\n".encode("utf-8") for relative in controls
        }
        contents["README.md"] = f"synthetic package: {marker}\n".encode("utf-8")
        if extra_path:
            contents[extra_path] = f"extra: {marker}\n".encode("utf-8")
        for relative, payload in contents.items():
            path = root.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        expected = {"bootstrap.manifest.json", *contents}
        manifest = {
            "schema_version": 1,
            "bootstrap_version": version,
            "python_requires": ">=3.11",
            "control_sha256": {
                relative: hashlib.sha256(contents[relative]).hexdigest()
                for relative in sorted(controls)
            },
            "source_sha256": {
                relative: hashlib.sha256(contents[relative]).hexdigest()
                for relative in sorted(contents)
            },
            "required_files": sorted(expected),
        }
        (root / "bootstrap.manifest.json").write_bytes(
            (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
        )

    def _synthetic_repository(
        self, *, historical_controls: bool = False
    ) -> tuple[Path, tempfile.TemporaryDirectory[str], str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        self._git(root, "init", "-b", "maintenance")
        self._git(root, "config", "user.name", "Synthetic Test")
        self._git(root, "config", "user.email", "test@example.invalid")
        self._write_synthetic_package(
            root,
            PREVIOUS_PACKAGE_VERSION,
            "base",
            historical_controls=historical_controls,
        )
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "base package")
        return root, temporary, self._git(root, "rev-parse", "HEAD")

    def test_ci_workflow_is_read_only_hosted_and_immutably_pinned(self) -> None:
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        def action_identities(document: str) -> list[str]:
            uses = [
                line.split("uses:", 1)[1].strip()
                for line in document.splitlines()
                if "uses:" in line
            ]
            immutable_pin = re.compile(
                r"^(?P<identity>[a-z0-9_.-]+/[a-z0-9_.-]+)"
                r"@(?P<sha>[0-9a-f]{40}) # v[0-9][0-9A-Za-z.-]*$"
            )
            matches = [immutable_pin.fullmatch(value) for value in uses]
            self.assertTrue(all(match is not None for match in matches))
            return [match.group("identity") for match in matches if match is not None]

        expected_identities = [
            "actions/checkout",
            "actions/setup-python",
            "astral-sh/ruff-action",
        ] + ["actions/checkout", "actions/setup-python"] * 3
        self.assertEqual(action_identities(workflow), expected_identities)

        current_checkout = re.search(r"actions/checkout@([0-9a-f]{40})", workflow)
        self.assertIsNotNone(current_checkout)
        assert current_checkout is not None
        synthetic_update = workflow.replace(
            current_checkout.group(0),
            "actions/checkout@" + "1" * 40,
            1,
        )
        self.assertEqual(action_identities(synthetic_update), expected_identities)
        for job in ("safety-tests:", "windows-smoke:", "macos-setup-smoke:"):
            self.assertIn(job, synthetic_update)
        self.assertEqual(workflow.count("persist-credentials: false"), 4)
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

    def test_ci_push_branches_and_precheck_order_are_exact(self) -> None:
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "push:\n    branches:\n      - fast-lane\n      - Legacy\n",
            workflow,
        )
        self.assertNotIn("      - main\n", workflow)
        self.assertEqual(workflow.count("needs: repository-precheck"), 3)
        self.assertEqual(workflow.count("if: ${{ always() }}"), 3)
        self.assertEqual(
            workflow.count("name: Require successful repository precheck"), 3
        )
        self.assertEqual(
            workflow.count("needs.repository-precheck.result != 'success'"), 3
        )
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn(
            "FASTLANE_BASE_COMMIT: "
            "${{ github.event.pull_request.base.sha || github.event.before }}",
            workflow,
        )
        self.assertNotIn("github.event.repository.is_template", workflow)
        self.assertIn(
            "(github.event_name == 'pull_request' && github.base_ref == "
            "'fast-lane') || (github.event_name == 'push' && "
            "github.ref_name == 'fast-lane')",
            workflow,
        )
        self.assertIn(
            'package_release.py --check --base-commit "${FASTLANE_BASE_COMMIT}"',
            workflow,
        )
        ordered_steps = (
            "Validate Python syntax and indentation",
            "Run Ruff lint",
            "Verify Ruff formatting",
            "Run repository governance monitors",
            "Verify template manifest hashes",
            "Enforce customer package version identity",
            "Verify deterministic release package",
        )
        positions = [workflow.index(f"name: {name}") for name in ordered_steps]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(workflow.count('version: "0.16.0"'), 1)
        self.assertIn("args: check --no-cache", workflow)
        self.assertIn(
            "src: >-\n"
            "            bootstrap.py\n"
            "            scripts\n"
            "            tests\n"
            "            .codex/hooks\n",
            workflow,
        )
        self.assertIn(
            "ruff format --check --no-cache bootstrap.py scripts tests .codex/hooks",
            workflow,
        )
        for forbidden in (
            "git fetch",
            "git tag",
            "git push",
            "gh release",
            "upload-artifact",
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

    def test_template_reserves_singular_app_root_without_nested_agent_authority(
        self,
    ) -> None:
        manifest = json.loads(
            (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        self.assertIn("app/.gitkeep", manifest["required_files"])
        self.assertIn("app/.gitkeep", manifest["source_sha256"])
        self.assertNotIn("app/AGENTS.md", manifest["required_files"])
        self.assertNotIn("app/AGENTS.md", manifest["source_sha256"])
        self.assertEqual((REPOSITORY_ROOT / "app/.gitkeep").read_bytes(), b"")
        self.assertFalse((REPOSITORY_ROOT / "app/AGENTS.md").exists())

    def test_manifest_is_the_only_internal_version_source(self) -> None:
        manifest = json.loads(
            (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["bootstrap_version"], "1.2.1")
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
        linked_versions = re.findall(
            r"releases/(?:download|tag)/v(\d+\.\d+\.\d+)", readme
        )
        self.assertTrue(
            all(
                version == manifest["bootstrap_version"] for version in linked_versions
            ),
            linked_versions,
        )

    def test_release_contains_official_aws_core_setup_assets(self) -> None:
        _version, files = package_release.load_release_files(REPOSITORY_ROOT)
        inventory = {path for path, _content in files}
        for required in (
            "docs/AGENTS.md",
            "docs/README.md",
            "docs/SETUP.md",
            "docs/TROUBLESHOOTING.md",
            "docs/DEPENDENCY-POLICY.md",
            "docs/WORKFLOW.md",
            ".codex/hooks/AGENTS.md",
            ".agents/skills/maintain-fastlane/references/documentation-governance.md",
            "scripts/setup_assistant.py",
            "tests/test_setup_assistant.py",
            ".github/dependabot.yml",
            "pyproject.toml",
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
            and ".ruff_cache" not in path.parts
            and path.suffix != ".pyc"
            and "dist" not in path.parts
        }
        manifest = json.loads(
            (template / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        expected = set(manifest["required_files"])
        self.assertEqual(actual, expected)
        self.assertEqual(manifest["required_files"], sorted(expected))

    def test_release_manifest_inventory_must_include_itself(self) -> None:
        manifest = {
            "bootstrap_version": "1.0.2",
            "required_files": ["README.md"],
        }
        with self.assertRaisesRegex(
            package_release.PackagingError,
            "must include bootstrap.manifest.json",
        ):
            package_release.release_manifest_values(manifest)

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
                    "--prerequisite-report-stdin",
                ],
                cwd=project,
                input=json.dumps(setup_assistant.READY_PREREQUISITE_REPORT),
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
            self.assertEqual(
                digest, hashlib.sha256(archive_path.read_bytes()).hexdigest()
            )
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
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "dist"),
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
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "dist"),
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

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_cli_rejects_direct_symlink_output_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside-sentinel.txt"
            outside.write_bytes(b"outside sentinel")
            output = root / "release.zip"
            try:
                output.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"File symlinks are unavailable: {exc}")

            with (
                mock.patch.object(
                    package_release,
                    "expected_artifacts",
                    return_value=(b"archive", b"checksum"),
                ),
                mock.patch("builtins.print"),
            ):
                result = package_release.main(["--output", str(output)])

            self.assertEqual(result, 1)
            self.assertEqual(outside.read_bytes(), b"outside sentinel")
            self.assertTrue(output.is_symlink())
            self.assertFalse(outside.with_name(f"{outside.name}.sha256").exists())

    def test_cli_writes_an_explicit_external_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "external" / "release.zip"
            with (
                mock.patch.object(
                    package_release,
                    "expected_artifacts",
                    return_value=(b"archive", b"checksum"),
                ),
                mock.patch("builtins.print"),
            ):
                result = package_release.main(["--output", str(output)])

            self.assertEqual(result, 0)
            self.assertEqual(output.read_bytes(), b"archive")
            self.assertEqual(
                package_release.checksum_path(output).read_bytes(),
                b"checksum",
            )

    @unittest.skipIf(os.name == "nt", "POSIX path semantics are required")
    def test_verified_darwin_root_alias_is_canonicalized_without_descendants(
        self,
    ) -> None:
        self.assertEqual(
            package_release.DARWIN_SYSTEM_ROOT_ALIASES,
            {"/tmp": "/private/tmp", "/var": "/private/var"},
        )
        source = Path("/var/folders/example/linked-output/release.zip")

        with (
            mock.patch.object(package_release.sys, "platform", "darwin"),
            mock.patch.object(
                package_release,
                "_is_link_or_reparse_point",
                side_effect=lambda path: path == Path("/var"),
            ),
            mock.patch.object(
                package_release.os.path,
                "realpath",
                return_value="/private/var",
            ) as realpath,
        ):
            validated = package_release.validate_output_path(source)

        self.assertEqual(
            validated,
            Path("/private/var/folders/example/linked-output/release.zip"),
        )
        realpath.assert_called_once_with(Path("/var"))

    @unittest.skipIf(os.name == "nt", "POSIX path semantics are required")
    def test_unexpected_darwin_root_alias_target_remains_rejected(self) -> None:
        with (
            mock.patch.object(package_release.sys, "platform", "darwin"),
            mock.patch.object(
                package_release,
                "_is_link_or_reparse_point",
                side_effect=lambda path: path == Path("/var"),
            ),
            mock.patch.object(
                package_release.os.path,
                "realpath",
                return_value="/unexpected/var",
            ),
            self.assertRaisesRegex(
                package_release.PackagingError,
                "symlink or reparse point",
            ),
        ):
            package_release.validate_output_path(Path("/var/folders/release.zip"))

    def test_cli_rejects_linked_output_ancestor_without_writing_outside(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_bytes(b"outside sentinel")
            linked_parent = root / "linked-output"
            self._create_directory_link(linked_parent, outside)
            try:
                output = linked_parent / "release.zip"
                with (
                    mock.patch.object(
                        package_release,
                        "expected_artifacts",
                        return_value=(b"archive", b"checksum"),
                    ),
                    mock.patch("builtins.print"),
                ):
                    result = package_release.main(["--output", str(output)])

                self.assertEqual(result, 1)
                self.assertEqual(sentinel.read_bytes(), b"outside sentinel")
                self.assertFalse((outside / "release.zip").exists())
                self.assertFalse((outside / "release.zip.sha256").exists())
            finally:
                self._remove_directory_link(linked_parent)

    def test_atomic_write_rechecks_output_path_before_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_parent = root / "output"
            output_parent.mkdir()
            displaced_parent = root / "displaced-output"
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_bytes(b"outside sentinel")
            output = output_parent / "release.zip"
            real_validate = package_release.validate_output_path
            validation_calls = 0

            def link_before_final_validation(path: Path) -> Path:
                nonlocal validation_calls
                validation_calls += 1
                if validation_calls == 3:
                    output_parent.rename(displaced_parent)
                    self._create_directory_link(output_parent, outside)
                return real_validate(path)

            try:
                with (
                    mock.patch.object(
                        package_release,
                        "validate_output_path",
                        side_effect=link_before_final_validation,
                    ),
                    self.assertRaisesRegex(
                        package_release.PackagingError,
                        "symlink or reparse point",
                    ),
                ):
                    package_release.atomic_write(output, b"archive")
                self.assertEqual(validation_calls, 3)
                self.assertEqual(sentinel.read_bytes(), b"outside sentinel")
                self.assertFalse((outside / "release.zip").exists())
            finally:
                self._remove_directory_link(output_parent)

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
                        "required_files": [
                            "README.md",
                            "bootstrap.manifest.json",
                        ],
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
            with self.assertRaisesRegex(
                package_release.PackagingError, "semantic version"
            ):
                package_release.load_release_files(root)

    def test_package_version_guard_requires_a_strict_bump_for_changed_bytes(
        self,
    ) -> None:
        root, temporary, base = self._synthetic_repository()
        self.addCleanup(temporary.cleanup)
        self.assertFalse(package_release.check_versioned_package_change(root, base))

        self._write_synthetic_package(root, PREVIOUS_PACKAGE_VERSION, "changed")
        with self.assertRaisesRegex(
            package_release.PackagingError,
            "without a strictly greater",
        ):
            package_release.check_versioned_package_change(root, base)

        self._write_synthetic_package(root, "1.0.2", "changed")
        self.assertTrue(package_release.check_versioned_package_change(root, base))

    def test_package_version_guard_detects_inventory_changes_and_regression(
        self,
    ) -> None:
        root, temporary, base = self._synthetic_repository()
        self.addCleanup(temporary.cleanup)
        self._write_synthetic_package(
            root,
            PREVIOUS_PACKAGE_VERSION,
            "base",
            extra_path="docs/new-contract.md",
        )
        with self.assertRaisesRegex(
            package_release.PackagingError,
            "without a strictly greater",
        ):
            package_release.check_versioned_package_change(root, base)

        self._write_synthetic_package(root, "1" + ".0.0", "regressed")
        with self.assertRaisesRegex(
            package_release.PackagingError,
            "version regressed",
        ):
            package_release.check_versioned_package_change(root, base)

    def test_package_version_guard_accepts_historical_control_inventory(self) -> None:
        root, temporary, base = self._synthetic_repository(historical_controls=True)
        self.addCleanup(temporary.cleanup)
        self._write_synthetic_package(root, "1.0.2", "current")
        self.assertTrue(package_release.check_versioned_package_change(root, base))

    def test_package_version_guard_fails_closed_for_unavailable_base(self) -> None:
        root, temporary, _base = self._synthetic_repository()
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(
            package_release.PackagingError,
            "exact lowercase Git object ID",
        ):
            package_release.check_versioned_package_change(root, "main")
        with self.assertRaisesRegex(
            package_release.PackagingError,
            "unavailable in this checkout",
        ):
            package_release.check_versioned_package_change(root, "0" * 40)

    def test_package_version_guard_cli_requires_check_mode(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            package_release.main(["--base-commit", "0" * 40])
        self.assertEqual(raised.exception.code, 2)

    def test_current_release_text_rejects_stale_versions_except_fixtures(self) -> None:
        aws_plugin_fixture_version = "1" + ".2.0"
        stale_versions = (
            "1" + ".0.0",
            PREVIOUS_PACKAGE_VERSION,
            "1" + ".1.3",
            "1" + ".1.5",
            "1" + ".2.0",
            "2" + ".0.0",
        )
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
                if (
                    relative == "tests/test_bootstrap_doctor.py"
                    and aws_plugin_fixture_version in line
                    and "plugin_version: str =" in line
                ):
                    allowed_aws_version_observations += 1
                    continue
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
                    violations.append(f"{relative}:{line_number}:{version}")
        self.assertEqual(allowed_negative_fixtures, 2)
        self.assertEqual(allowed_aws_version_observations, 2)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
