from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_SOURCE_MODE = "{{SETUP_STATUS}}" in (
    REPOSITORY_ROOT / "bootstrap.yaml"
).read_text(encoding="utf-8")
source_template_only = unittest.skipUnless(
    TEMPLATE_SOURCE_MODE,
    "maintainer source-integrity test is not applicable after project configuration",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = load_module("bootstrap_under_test", REPOSITORY_ROOT / "bootstrap.py")
setup_assistant = sys.modules["scripts.setup_assistant"]


def ready_prerequisite_report() -> str:
    return json.dumps(setup_assistant.READY_PREREQUISITE_REPORT)


def copy_manifest_template(destination: Path) -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
    )
    for relative in manifest["required_files"]:
        source = REPOSITORY_ROOT.joinpath(*PurePosixPath(relative).parts)
        target = destination.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def adoption_decision(
    relative: str,
    action: str,
    target_content: bytes,
    template_content: bytes,
) -> dict[str, str]:
    return {
        "path": relative,
        "action": action,
        "expected_target_sha256": bootstrap.sha256_bytes(target_content),
        "expected_template_sha256": bootstrap.sha256_bytes(template_content),
    }


def write_adoption_map(
    path: Path,
    source: Path,
    target: Path,
    decisions: list[dict[str, str]],
    *,
    authorize_adoption: bool = True,
    **extra_fields: object,
) -> Path:
    has_destructive_decision = any(
        decision.get("action") == "ADOPT_TEMPLATE" for decision in decisions
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "source_root": str(source.resolve()),
        "target_root": str(target.resolve()),
        "decisions": decisions,
        "authorization": (
            {
                "authorized_by": "Project Owner",
                "authorized_at": "2026-07-17T12:00:00Z",
                "authorization_source": "OWNER_CONFIRMATION",
                "plan_sha256": bootstrap.canonical_adoption_plan_sha256(
                    source,
                    target,
                    decisions,
                ),
            }
            if authorize_adoption and has_destructive_decision
            else None
        ),
    }
    payload.update(extra_fields)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class BootstrapSafetyTests(unittest.TestCase):
    def test_maintainer_test_sources_are_never_rendered(self) -> None:
        manifest = json.loads(
            (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        test_paths = [
            relative
            for relative in manifest["required_files"]
            if relative.startswith("tests/")
        ]
        self.assertTrue(test_paths)
        self.assertTrue(
            all(not bootstrap.should_render_path(relative) for relative in test_paths)
        )

    @source_template_only
    def test_in_place_template_setup_is_atomic_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "project"
            project.mkdir()
            copy_manifest_template(project)
            values = dict(bootstrap.PLACEHOLDERS)
            values.update(
                {
                    "{{PROJECT_NAME}}": "Direct Action Project",
                    "{{AWS_REGION}}": "us-west-2",
                    "{{COST_POSTURE}}": "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                }
            )

            original_state = (project / "bootstrap.yaml").read_bytes()
            original_tests = {
                path.relative_to(project): path.read_bytes()
                for path in (project / "tests").glob("test_*.py")
            }
            preview = bootstrap.initialize_template_in_place(
                project,
                values,
                dry_run=True,
            )
            self.assertGreater(preview.planned, 0)
            self.assertEqual((project / "bootstrap.yaml").read_bytes(), original_state)

            report = bootstrap.initialize_template_in_place(project, values)

            self.assertGreater(report.written, 0)
            state = json.loads((project / "bootstrap.yaml").read_text(encoding="utf-8"))
            self.assertEqual(
                state["setup"], {"status": "CONFIGURED", "method": "IN_PLACE"}
            )
            self.assertEqual(state["project"]["name"], "Direct Action Project")
            self.assertEqual(state["project"]["region"], "us-west-2")
            self.assertEqual(
                state["project"]["cost_posture"],
                "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
            )
            self.assertEqual(
                {
                    path.relative_to(project): path.read_bytes()
                    for path in (project / "tests").glob("test_*.py")
                },
                original_tests,
            )
            doctor_ok, doctor_output = bootstrap.run_generated_doctor(project)
            self.assertTrue(doctor_ok, doctor_output)

            user_file = project / "app" / "implemented_after_setup.py"
            user_file.write_text("VALUE = 1\n", encoding="utf-8")
            resumed = bootstrap.initialize_template_in_place(project, values)
            self.assertEqual(resumed.written, 0)
            self.assertGreater(resumed.unchanged, 0)
            self.assertEqual(user_file.read_text(encoding="utf-8"), "VALUE = 1\n")

    @source_template_only
    def test_in_place_setup_rejects_modified_template_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "project"
            project.mkdir()
            copy_manifest_template(project)
            (project / "docs/project/PRD.md").write_text(
                "owner-modified", encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "source hash mismatch"):
                bootstrap.initialize_template_in_place(
                    project,
                    dict(bootstrap.PLACEHOLDERS),
                )

    @source_template_only
    def test_in_place_setup_rejects_unmanifested_user_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "project"
            project.mkdir()
            copy_manifest_template(project)
            extra = project / "owner-notes.md"
            extra.write_text("do not overwrite", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unexpected: owner-notes.md"):
                bootstrap.initialize_template_in_place(
                    project,
                    dict(bootstrap.PLACEHOLDERS),
                )

            self.assertEqual(extra.read_text(encoding="utf-8"), "do not overwrite")
            state = (project / "bootstrap.yaml").read_text(encoding="utf-8")
            self.assertIn("{{SETUP_STATUS}}", state)

    def test_in_place_setup_rolls_back_when_doctor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "project"
            project.mkdir()
            copy_manifest_template(project)
            original = (project / "bootstrap.yaml").read_bytes()
            values = dict(bootstrap.PLACEHOLDERS)
            values["{{PROJECT_NAME}}"] = "Rollback Example"

            with mock.patch.object(
                bootstrap,
                "run_generated_doctor",
                return_value=(False, "forced doctor failure"),
            ):
                with self.assertRaisesRegex(
                    ValueError, "Fastlane Engine validation failed"
                ):
                    bootstrap.initialize_template_in_place(project, values)

            self.assertEqual((project / "bootstrap.yaml").read_bytes(), original)

    def test_in_place_setup_protects_official_source_and_dirty_clones(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "project"
            project.mkdir()
            (project / ".git").mkdir()
            with mock.patch.object(
                bootstrap,
                "git_text",
                return_value="git@github.com:Levi-Breedlove/aws-bootstrap.git",
            ):
                with self.assertRaisesRegex(
                    ValueError, "official maintainer repository"
                ):
                    bootstrap.validate_in_place_repository(project)

            with mock.patch.object(
                bootstrap,
                "git_text",
                side_effect=[
                    "https://github.com/example/project.git",
                    " M docs/project/PRD.md",
                ],
            ):
                with self.assertRaisesRegex(ValueError, "untouched, clean"):
                    bootstrap.validate_in_place_repository(project)

    def test_runtime_control_hashes_fail_closed_on_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source"
            (source / "scripts").mkdir(parents=True)
            controls = {
                "bootstrap.py": b"bootstrap",
                "scripts/bootstrap_dependencies.py": b"dependencies",
                "scripts/bootstrap_doctor.py": b"doctor",
                "scripts/fastlane_contracts.py": b"contracts",
                "scripts/fastlane_process.py": b"process",
                "scripts/fastlane_project_identity.py": b"identity",
                "scripts/fastlane_stdio.py": b"stdio",
                "scripts/setup_assistant.py": b"setup-assistant",
                "scripts/task_waves.py": b"tasks",
            }
            for relative, content in controls.items():
                (source / relative).write_bytes(content)
            manifest = {
                "control_sha256": {
                    relative: bootstrap.sha256_bytes(content)
                    for relative, content in controls.items()
                }
            }
            manifest_path = source / "bootstrap.manifest.json"
            manifest_path.write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            bootstrap.validate_template_control_hashes(source)
            (source / "scripts" / "task_waves.py").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Runtime control hash mismatch"):
                bootstrap.validate_template_control_hashes(source)

            (source / "scripts" / "task_waves.py").write_bytes(
                controls["scripts/task_waves.py"]
            )
            manifest["control_sha256"]["bootstrap.py"] = "A" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid control_sha256"):
                bootstrap.validate_template_control_hashes(source)

            manifest["control_sha256"]["bootstrap.py"] = bootstrap.sha256_bytes(
                controls["bootstrap.py"]
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (source / "scripts" / "bootstrap_dependencies.py").write_bytes(
                b"tampered dependency validator"
            )
            with mock.patch.object(bootstrap.subprocess, "run") as run:
                with self.assertRaisesRegex(
                    ValueError, "Runtime control hash mismatch"
                ):
                    bootstrap.validate_repository_dependencies(source)
            run.assert_not_called()

    def test_main_stops_before_setup_when_dependency_validation_fails(self) -> None:
        with (
            mock.patch.object(
                bootstrap,
                "validate_repository_dependencies",
                side_effect=ValueError("dependency policy mismatch"),
            ) as dependency_check,
            mock.patch.object(sys, "stdin", io.StringIO(ready_prerequisite_report())),
            mock.patch.object(bootstrap, "initialize_template_in_place") as initialize,
        ):
            result = bootstrap.main(
                [
                    "--target",
                    str(REPOSITORY_ROOT),
                    "--project-name",
                    "Dependency Stop",
                    "--in-place-template-instance",
                    "--prerequisite-report-stdin",
                ]
            )
        self.assertEqual(result, 2)
        dependency_check.assert_called_once_with(REPOSITORY_ROOT)
        initialize.assert_not_called()

    def test_main_requires_exact_ready_report_before_dependency_or_write(self) -> None:
        base = [
            "--target",
            str(REPOSITORY_ROOT),
            "--project-name",
            "Readiness Boundary",
            "--in-place-template-instance",
        ]
        blocked = [
            ("missing", base, ""),
            ("malformed", [*base, "--prerequisite-report-stdin"], "{"),
            (
                "non-ready",
                [*base, "--prerequisite-report-stdin"],
                json.dumps(
                    {
                        **setup_assistant.READY_PREREQUISITE_REPORT,
                        "state": "AWS_CORE_REQUIRED",
                    }
                ),
            ),
            (
                "extra-field",
                [*base, "--prerequisite-report-stdin"],
                json.dumps(
                    {
                        **setup_assistant.READY_PREREQUISITE_REPORT,
                        "session": "not-allowed",
                    }
                ),
            ),
        ]
        for label, arguments, payload in blocked:
            with (
                self.subTest(label=label),
                mock.patch.object(sys, "stdin", io.StringIO(payload)),
                mock.patch.object(
                    bootstrap, "validate_repository_dependencies"
                ) as dependency_check,
                mock.patch.object(
                    bootstrap, "initialize_template_in_place"
                ) as initialize,
            ):
                self.assertEqual(bootstrap.main(arguments), 2)
                dependency_check.assert_not_called()
                initialize.assert_not_called()

    def test_current_ready_report_permits_dry_run_and_initialization(self) -> None:
        for dry_run in (True, False):
            arguments = [
                "--target",
                str(REPOSITORY_ROOT),
                "--project-name",
                "Ready Bootstrap",
                "--in-place-template-instance",
                "--prerequisite-report-stdin",
            ]
            if dry_run:
                arguments.append("--dry-run")
            with (
                self.subTest(dry_run=dry_run),
                mock.patch.object(
                    sys, "stdin", io.StringIO(ready_prerequisite_report())
                ),
                mock.patch.object(bootstrap, "validate_repository_dependencies"),
                mock.patch.object(
                    bootstrap,
                    "initialize_template_in_place",
                    return_value=bootstrap.CopyReport(planned=1),
                ) as initialize,
            ):
                self.assertEqual(bootstrap.main(arguments), 0)
                initialize.assert_called_once_with(
                    REPOSITORY_ROOT, mock.ANY, dry_run=dry_run
                )

    def test_main_rejects_noncanonical_cost_posture_before_any_setup(self) -> None:
        with (
            mock.patch.object(
                bootstrap, "validate_repository_dependencies"
            ) as dependency_check,
            mock.patch.object(bootstrap, "initialize_template_in_place") as initialize,
        ):
            result = bootstrap.main(
                [
                    "--target",
                    str(REPOSITORY_ROOT),
                    "--project-name",
                    "Cost Boundary Stop",
                    "--cost-posture",
                    "unlimited",
                    "--in-place-template-instance",
                ]
            )
        self.assertEqual(result, 2)
        dependency_check.assert_not_called()
        initialize.assert_not_called()

    def test_main_rejects_non_iso_currency_before_any_setup(self) -> None:
        with (
            mock.patch.object(
                bootstrap, "validate_repository_dependencies"
            ) as dependency_check,
            mock.patch.object(bootstrap, "initialize_template_in_place") as initialize,
        ):
            result = bootstrap.main(
                [
                    "--target",
                    str(REPOSITORY_ROOT),
                    "--project-name",
                    "Currency Boundary Stop",
                    "--cost-posture",
                    "MINIMIZE_TOTAL_COST; HARD_CAP: ZZZ 20.00",
                    "--in-place-template-instance",
                ]
            )
        self.assertEqual(result, 2)
        dependency_check.assert_not_called()
        initialize.assert_not_called()

    def test_rejects_target_inside_source_before_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source"
            source.mkdir()
            (source / "template.txt").write_text("template", encoding="utf-8")
            target = source / "generated" / "project"

            with self.assertRaisesRegex(ValueError, "must not overlap"):
                bootstrap.copy_template(source, target, {}, force=False)

            self.assertFalse(target.exists())

    def test_rejects_source_inside_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory) / "parent"
            source = target / "source"
            source.mkdir(parents=True)

            with self.assertRaisesRegex(ValueError, "must not overlap"):
                bootstrap.validate_non_overlapping_paths(source, target)

    def test_dry_run_does_not_create_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "PRD.md").write_text("{{PROJECT_NAME}}", encoding="utf-8")

            report = bootstrap.copy_template(
                source,
                target,
                {"{{PROJECT_NAME}}": "Example"},
                force=False,
                dry_run=True,
            )

            self.assertEqual(report.planned, 1)
            self.assertEqual(report.written, 0)
            self.assertFalse(target.exists())

    def test_collision_free_copy_renders_and_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "nested").mkdir()
            (source / "nested" / "PRD.md").write_text(
                "{{PROJECT_NAME}}",
                encoding="utf-8",
            )

            report = bootstrap.copy_template(
                source,
                target,
                {"{{PROJECT_NAME}}": "Example"},
                force=False,
            )

            self.assertEqual(report.planned, 1)
            self.assertEqual(report.written, 1)
            self.assertEqual(
                (target / "nested" / "PRD.md").read_text(encoding="utf-8"),
                "Example",
            )

    def test_existing_user_file_is_preserved_as_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "PRD.md").write_text("generated", encoding="utf-8")
            (source / "new.txt").write_text("new", encoding="utf-8")
            destination = target / "PRD.md"
            destination.write_text("user content", encoding="utf-8")

            report = bootstrap.copy_template(source, target, {}, force=False)

            self.assertEqual(report.collisions, 1)
            self.assertEqual(report.written, 0)
            self.assertEqual(destination.read_text(encoding="utf-8"), "user content")
            self.assertFalse((target / "new.txt").exists())

    def test_blanket_force_is_rejected_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "same.txt").write_text("same", encoding="utf-8")
            (source / "new.txt").write_text("new", encoding="utf-8")
            destination = target / "same.txt"
            destination.write_text("same", encoding="utf-8")
            original_stat = destination.stat()

            with self.assertRaisesRegex(ValueError, "Blanket --force is disabled"):
                bootstrap.copy_template(source, target, {}, force=True)

            self.assertEqual(destination.read_text(encoding="utf-8"), "same")
            self.assertEqual(destination.stat().st_mtime_ns, original_stat.st_mtime_ns)
            self.assertFalse((target / "new.txt").exists())

    def test_source_symlink_is_rejected_before_target_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            outside = root / "outside.txt"
            source.mkdir()
            outside.write_text("secret", encoding="utf-8")
            try:
                os.symlink(outside, source / "linked.txt")
            except OSError as exc:
                self.skipTest(f"Symbolic links are unavailable: {exc}")

            with self.assertRaisesRegex(ValueError, "unsupported symbolic link"):
                bootstrap.copy_template(source, target, {}, force=False)

            self.assertFalse(target.exists())

    def test_git_metadata_and_generated_cache_names_are_skipped_case_insensitively(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            (source / ".GIT").mkdir(parents=True)
            (source / "__PYCACHE__").mkdir()
            (source / ".GIT" / "config").write_text("secret", encoding="utf-8")
            (source / "__PYCACHE__" / "module.PYC").write_bytes(b"cache")
            (source / "safe.txt").write_text("safe", encoding="utf-8")

            report = bootstrap.copy_template(source, target, {})

            self.assertEqual(report.written, 1)
            self.assertEqual((target / "safe.txt").read_text(encoding="utf-8"), "safe")
            self.assertFalse((target / ".GIT").exists())
            self.assertFalse((target / "__PYCACHE__").exists())

    def test_case_insensitive_source_collision_fails_before_target_creation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "Policy.md").write_text("first", encoding="utf-8")
            (source / "policy.md").write_text("second", encoding="utf-8")
            if len(list(source.iterdir())) != 2:
                self.skipTest(
                    "The current filesystem cannot create case-colliding source names"
                )

            with self.assertRaisesRegex(ValueError, "case-insensitive filesystem"):
                bootstrap.copy_template(source, target, {})

            self.assertFalse(target.exists())

    def test_adoption_paths_are_strict_repository_relative_paths(self) -> None:
        invalid_paths = [
            "",
            ".",
            "../outside.txt",
            "nested/../outside.txt",
            "./file.txt",
            "nested//file.txt",
            "nested/file.txt/",
            "/absolute.txt",
            ".git/config",
            ".GIT/config",
            "windows\\path.txt",
        ]

        for raw in invalid_paths:
            with self.subTest(path=raw):
                with self.assertRaisesRegex(ValueError, "Invalid|not canonical"):
                    bootstrap.validate_relative_path(raw)

        self.assertEqual(
            bootstrap.validate_relative_path("nested/file.txt"),
            "nested/file.txt",
        )

    def test_filesystem_root_and_home_targets_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source"
            source.mkdir()

            for target in (Path(source.anchor), Path.home()):
                with self.subTest(target=target):
                    with self.assertRaisesRegex(
                        ValueError,
                        "filesystem root or home directory",
                    ):
                        bootstrap.validate_non_overlapping_paths(source, target)

            target = Path(temporary_directory) / "target"
            with self.assertRaisesRegex(
                ValueError,
                "Staging target must not be a filesystem root or home directory",
            ):
                bootstrap.copy_template(
                    source,
                    target,
                    {},
                    staging_target=Path.home(),
                )

    def test_git_metadata_target_is_rejected_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()

            for target in (root / ".git", root / ".GIT" / "nested"):
                with self.subTest(target=target):
                    with self.assertRaisesRegex(ValueError, "inside Git metadata"):
                        bootstrap.validate_non_overlapping_paths(source, target)

    def test_adoption_map_schema_roots_actions_and_digests_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            map_path = root / "adoption.json"
            digest = "0" * 64
            valid_decision = {
                "path": "file.txt",
                "action": "PRESERVE",
                "expected_target_sha256": digest,
                "expected_template_sha256": digest,
            }
            base_payload = {
                "schema_version": 1,
                "source_root": str(source),
                "target_root": str(target),
                "decisions": [],
                "authorization": None,
            }

            cases: list[tuple[str, dict[str, object], str]] = [
                (
                    "extra top-level field",
                    {**base_payload, "unexpected": True},
                    "fields must be exactly",
                ),
                (
                    "wrong source root",
                    {
                        **base_payload,
                        "source_root": str(root / "other-source"),
                    },
                    "does not match",
                ),
                (
                    "decision extra field",
                    {
                        **base_payload,
                        "decisions": [{**valid_decision, "unexpected": True}],
                    },
                    "exactly four fields",
                ),
                (
                    "unknown action",
                    {
                        **base_payload,
                        "decisions": [{**valid_decision, "action": "OVERWRITE"}],
                    },
                    "invalid adoption action",
                ),
                (
                    "invalid digest",
                    {
                        **base_payload,
                        "decisions": [
                            {
                                **valid_decision,
                                "expected_target_sha256": "not-a-digest",
                            }
                        ],
                    },
                    "invalid expected_target_sha256",
                ),
            ]

            for name, payload, error in cases:
                with self.subTest(case=name):
                    map_path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, error):
                        bootstrap.load_adoption_plan(map_path, source, target)

    def test_template_adoption_requires_exact_owner_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            decision = adoption_decision(
                "file.txt",
                "ADOPT_TEMPLATE",
                b"target",
                b"template",
            )

            missing_receipt = write_adoption_map(
                root / "missing.json",
                source,
                target,
                [decision],
                authorize_adoption=False,
            )
            with self.assertRaisesRegex(ValueError, "owner-confirmation receipt"):
                bootstrap.load_adoption_plan(missing_receipt, source, target)

            payload = json.loads(missing_receipt.read_text(encoding="utf-8"))
            payload["authorization"] = {
                "authorized_by": "Project Owner",
                "authorized_at": "2026-07-17T12:00:00Z",
                "authorization_source": "OWNER_CONFIRMATION",
                "plan_sha256": "0" * 64,
            }
            missing_receipt.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match the complete plan"):
                bootstrap.load_adoption_plan(missing_receipt, source, target)

            plan_digest = bootstrap.canonical_adoption_plan_sha256(
                source,
                target,
                [decision],
            )
            invalid_authorizations = [
                (
                    "agent owner",
                    {
                        "authorized_by": "Codex",
                        "authorized_at": "2026-07-17T12:00:00Z",
                        "authorization_source": "OWNER_CONFIRMATION",
                        "plan_sha256": plan_digest,
                    },
                    "named human owner",
                ),
                (
                    "compound agent owner",
                    {
                        "authorized_by": "Codex Agent",
                        "authorized_at": "2026-07-17T12:00:00Z",
                        "authorization_source": "OWNER_CONFIRMATION",
                        "plan_sha256": plan_digest,
                    },
                    "named human owner",
                ),
                (
                    "automation bot owner",
                    {
                        "authorized_by": "automation bot",
                        "authorized_at": "2026-07-17T12:00:00Z",
                        "authorization_source": "OWNER_CONFIRMATION",
                        "plan_sha256": plan_digest,
                    },
                    "named human owner",
                ),
                (
                    "placeholder owner",
                    {
                        "authorized_by": "TBD",
                        "authorized_at": "2026-07-17T12:00:00Z",
                        "authorization_source": "OWNER_CONFIRMATION",
                        "plan_sha256": plan_digest,
                    },
                    "named human owner",
                ),
                (
                    "timestamp without timezone",
                    {
                        "authorized_by": "Project Owner",
                        "authorized_at": "2026-07-17T12:00:00",
                        "authorization_source": "OWNER_CONFIRMATION",
                        "plan_sha256": plan_digest,
                    },
                    "requires an RFC3339 timestamp",
                ),
                (
                    "timestamp with a non-RFC3339 separator",
                    {
                        "authorized_by": "Project Owner",
                        "authorized_at": "2026-07-17 12:00:00+00:00",
                        "authorization_source": "OWNER_CONFIRMATION",
                        "plan_sha256": plan_digest,
                    },
                    "requires an RFC3339 timestamp",
                ),
                (
                    "non-owner source",
                    {
                        "authorized_by": "Project Owner",
                        "authorized_at": "2026-07-17T12:00:00Z",
                        "authorization_source": "AGENT_INFERENCE",
                        "plan_sha256": plan_digest,
                    },
                    "must be OWNER_CONFIRMATION",
                ),
            ]
            for name, authorization, error in invalid_authorizations:
                with self.subTest(case=name):
                    payload["authorization"] = authorization
                    missing_receipt.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, error):
                        bootstrap.load_adoption_plan(missing_receipt, source, target)

    def test_adoption_confirmation_cannot_be_replayed_for_another_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            first_target = root / "first-target"
            second_target = root / "second-target"
            source.mkdir()
            first_target.mkdir()
            second_target.mkdir()
            decision = adoption_decision(
                "file.txt",
                "ADOPT_TEMPLATE",
                b"target",
                b"template",
            )
            map_path = write_adoption_map(
                root / "adoption.json",
                source,
                first_target,
                [decision],
            )
            payload = json.loads(map_path.read_text(encoding="utf-8"))
            payload["target_root"] = str(second_target.resolve())
            map_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "complete plan"):
                bootstrap.load_adoption_plan(map_path, source, second_target)

    def test_programmatic_adoption_plan_cannot_bypass_owner_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "file.txt").write_text("template", encoding="utf-8")
            (target / "file.txt").write_text("target", encoding="utf-8")
            decision = bootstrap.AdoptionDecision(
                path="file.txt",
                action="ADOPT_TEMPLATE",
                expected_target_sha256=bootstrap.sha256_bytes(b"target"),
                expected_template_sha256=bootstrap.sha256_bytes(b"template"),
            )
            plan = bootstrap.AdoptionPlan(
                source.resolve(),
                target.resolve(),
                {"file.txt": decision},
            )

            with self.assertRaisesRegex(ValueError, "named human owner"):
                bootstrap.copy_template(source, target, {}, adoption_plan=plan)

            authorized_payload = bootstrap.adoption_decision_payload(plan.decisions)
            synthetic_owner_plan = bootstrap.AdoptionPlan(
                source.resolve(),
                target.resolve(),
                plan.decisions,
                "automation bot",
                "2026-07-17T12:00:00Z",
                "OWNER_CONFIRMATION",
                bootstrap.canonical_adoption_plan_sha256(
                    source,
                    target,
                    authorized_payload,
                ),
            )
            with self.assertRaisesRegex(ValueError, "named human owner"):
                bootstrap.copy_template(
                    source,
                    target,
                    {},
                    adoption_plan=synthetic_owner_plan,
                )

    def test_programmatic_plan_key_cannot_disagree_with_hashed_decision_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "file.txt").write_text("template", encoding="utf-8")
            (target / "file.txt").write_text("target", encoding="utf-8")
            decision = bootstrap.AdoptionDecision(
                path="different.txt",
                action="ADOPT_TEMPLATE",
                expected_target_sha256=bootstrap.sha256_bytes(b"target"),
                expected_template_sha256=bootstrap.sha256_bytes(b"template"),
            )
            decisions = {"file.txt": decision}
            plan = bootstrap.AdoptionPlan(
                source.resolve(),
                target.resolve(),
                decisions,
                "Project Owner",
                "2026-07-17T12:00:00Z",
                "OWNER_CONFIRMATION",
                bootstrap.canonical_adoption_plan_sha256(
                    source,
                    target,
                    bootstrap.adoption_decision_payload(decisions),
                ),
            )

            with self.assertRaisesRegex(ValueError, "does not match its lookup key"):
                bootstrap.copy_template(source, target, {}, adoption_plan=plan)

            self.assertEqual((target / "file.txt").read_bytes(), b"target")

    def test_programmatic_plan_rejects_invalid_actions_and_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            invalid_action = bootstrap.AdoptionPlan(
                source.resolve(),
                target.resolve(),
                {
                    "file.txt": bootstrap.AdoptionDecision(
                        path="file.txt",
                        action="REPLACE_ANYWAY",
                        expected_target_sha256="0" * 64,
                        expected_template_sha256="1" * 64,
                    )
                },
            )
            with self.assertRaisesRegex(ValueError, "invalid adoption action"):
                bootstrap.copy_template(
                    source, target, {}, adoption_plan=invalid_action
                )

            invalid_digest = bootstrap.AdoptionPlan(
                source.resolve(),
                target.resolve(),
                {
                    "file.txt": bootstrap.AdoptionDecision(
                        path="file.txt",
                        action="PRESERVE",
                        expected_target_sha256="A" * 64,
                        expected_template_sha256="1" * 64,
                    )
                },
            )
            with self.assertRaisesRegex(ValueError, "invalid expected_target_sha256"):
                bootstrap.copy_template(
                    source, target, {}, adoption_plan=invalid_digest
                )

    def test_incomplete_adoption_preflight_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "a.txt").write_text("template a", encoding="utf-8")
            (source / "b.txt").write_text("template b", encoding="utf-8")
            (source / "new.txt").write_text("new", encoding="utf-8")
            (target / "a.txt").write_text("user a", encoding="utf-8")
            (target / "b.txt").write_text("user b", encoding="utf-8")
            decision = adoption_decision(
                "a.txt",
                "PRESERVE",
                b"user a",
                b"template a",
            )
            map_path = write_adoption_map(
                root / "adoption.json",
                source,
                target,
                [decision],
            )
            plan = bootstrap.load_adoption_plan(map_path, source, target)

            report = bootstrap.copy_template(
                source,
                target,
                {},
                adoption_plan=plan,
            )

            self.assertEqual(report.unresolved, 1)
            self.assertEqual(report.written, 0)
            self.assertEqual((target / "a.txt").read_bytes(), b"user a")
            self.assertEqual((target / "b.txt").read_bytes(), b"user b")
            self.assertFalse((target / "new.txt").exists())

    def test_complete_hash_bound_plan_can_preserve_and_adopt_selectively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "keep.txt").write_text("template keep", encoding="utf-8")
            (source / "replace.txt").write_text(
                "template replacement", encoding="utf-8"
            )
            (target / "keep.txt").write_text("user keep", encoding="utf-8")
            (target / "replace.txt").write_text("old replacement", encoding="utf-8")
            decisions = [
                adoption_decision(
                    "keep.txt",
                    "PRESERVE",
                    b"user keep",
                    b"template keep",
                ),
                adoption_decision(
                    "replace.txt",
                    "ADOPT_TEMPLATE",
                    b"old replacement",
                    b"template replacement",
                ),
            ]
            map_path = write_adoption_map(
                root / "adoption.json",
                source,
                target,
                decisions,
            )
            plan = bootstrap.load_adoption_plan(map_path, source, target)

            report = bootstrap.copy_template(
                source,
                target,
                {},
                adoption_plan=plan,
            )

            self.assertEqual(report.unresolved, 0)
            self.assertEqual(report.preserved, 1)
            self.assertEqual(report.adopted, 1)
            self.assertEqual(report.written, 1)
            self.assertEqual((target / "keep.txt").read_bytes(), b"user keep")
            self.assertEqual(
                (target / "replace.txt").read_bytes(),
                b"template replacement",
            )

    def test_target_drift_aborts_before_any_planned_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "00-new.txt").write_text("new", encoding="utf-8")
            (source / "zz-collision.txt").write_text("template", encoding="utf-8")
            collision = target / "zz-collision.txt"
            collision.write_text("reviewed target", encoding="utf-8")
            decision = adoption_decision(
                "zz-collision.txt",
                "ADOPT_TEMPLATE",
                b"reviewed target",
                b"template",
            )
            map_path = write_adoption_map(
                root / "adoption.json",
                source,
                target,
                [decision],
            )
            plan = bootstrap.load_adoption_plan(map_path, source, target)
            collision.write_text("changed after review", encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError, "target changed after adoption review"
            ):
                bootstrap.copy_template(source, target, {}, adoption_plan=plan)

            self.assertEqual(collision.read_bytes(), b"changed after review")
            self.assertFalse((target / "00-new.txt").exists())

    def test_rendered_template_drift_aborts_before_any_planned_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "00-new.txt").write_text("new", encoding="utf-8")
            template = source / "zz-collision.txt"
            template.write_text("reviewed template", encoding="utf-8")
            collision = target / "zz-collision.txt"
            collision.write_text("target", encoding="utf-8")
            decision = adoption_decision(
                "zz-collision.txt",
                "ADOPT_TEMPLATE",
                b"target",
                b"reviewed template",
            )
            map_path = write_adoption_map(
                root / "adoption.json",
                source,
                target,
                [decision],
            )
            plan = bootstrap.load_adoption_plan(map_path, source, target)
            template.write_text("changed after review", encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "rendered template changed after adoption review",
            ):
                bootstrap.copy_template(source, target, {}, adoption_plan=plan)

            self.assertEqual(collision.read_bytes(), b"target")
            self.assertFalse((target / "00-new.txt").exists())

    def test_complete_recheck_happens_before_first_adoption_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "a-adopt.txt").write_text("template", encoding="utf-8")
            (source / "z-new.txt").write_text("new", encoding="utf-8")
            adopted = target / "a-adopt.txt"
            adopted.write_text("owner bytes", encoding="utf-8")
            decision = adoption_decision(
                "a-adopt.txt",
                "ADOPT_TEMPLATE",
                b"owner bytes",
                b"template",
            )
            map_path = write_adoption_map(
                root / "adoption.json",
                source,
                target,
                [decision],
            )
            plan = bootstrap.load_adoption_plan(map_path, source, target)
            original_validate = bootstrap.validate_copy_operation

            def introduce_late_collision(operation, operation_root):
                if operation.relative == "z-new.txt":
                    operation.destination.write_text("appeared", encoding="utf-8")
                return original_validate(operation, operation_root)

            with mock.patch.object(
                bootstrap,
                "validate_copy_operation",
                side_effect=introduce_late_collision,
            ):
                with self.assertRaisesRegex(ValueError, "appeared after preflight"):
                    bootstrap.copy_template(source, target, {}, adoption_plan=plan)

            self.assertEqual(adopted.read_bytes(), b"owner bytes")

    def test_duplicate_adoption_decisions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            decision = adoption_decision(
                "file.txt",
                "PRESERVE",
                b"target",
                b"template",
            )
            map_path = write_adoption_map(
                root / "adoption.json",
                source,
                target,
                [decision, decision],
            )

            with self.assertRaisesRegex(ValueError, "Duplicate adoption decision"):
                bootstrap.load_adoption_plan(map_path, source, target)

    def test_unknown_adoption_decision_aborts_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "new.txt").write_text("new", encoding="utf-8")
            decision = adoption_decision(
                "not-a-collision.txt",
                "PRESERVE",
                b"target",
                b"template",
            )
            map_path = write_adoption_map(
                root / "adoption.json",
                source,
                target,
                [decision],
            )
            plan = bootstrap.load_adoption_plan(map_path, source, target)

            with self.assertRaisesRegex(ValueError, "not current collisions"):
                bootstrap.copy_template(source, target, {}, adoption_plan=plan)

            self.assertFalse((target / "new.txt").exists())

    def test_staging_target_must_not_overlap_source_or_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "file.txt").write_text("template", encoding="utf-8")

            for staging_target in (source / "stage", target / "stage"):
                with self.subTest(staging_target=staging_target):
                    with self.assertRaisesRegex(ValueError, "must be separate"):
                        bootstrap.copy_template(
                            source,
                            target,
                            {},
                            staging_target=staging_target,
                        )

            git_staging = root / "other" / ".GIT" / "staged"
            with self.assertRaisesRegex(ValueError, "inside Git metadata"):
                bootstrap.copy_template(
                    source,
                    target,
                    {},
                    staging_target=git_staging,
                )
            self.assertFalse(git_staging.exists())

    def test_preserving_core_control_file_marks_partial_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "AGENTS.md").write_text("fastlane contract", encoding="utf-8")
            (target / "AGENTS.md").write_text("user contract", encoding="utf-8")
            decision = adoption_decision(
                "AGENTS.md",
                "PRESERVE",
                b"user contract",
                b"fastlane contract",
            )
            map_path = write_adoption_map(
                root / "adoption.json",
                source,
                target,
                [decision],
            )
            plan = bootstrap.load_adoption_plan(map_path, source, target)

            report = bootstrap.copy_template(source, target, {}, adoption_plan=plan)

            self.assertEqual(report.unresolved, 0)
            self.assertTrue(report.partial_adoption)
            self.assertEqual(report.preserved, 1)
            self.assertEqual((target / "AGENTS.md").read_bytes(), b"user contract")

    def test_preserving_nested_agents_file_marks_partial_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            (source / "infrastructure").mkdir(parents=True)
            (target / "infrastructure").mkdir(parents=True)
            (source / "infrastructure" / "AGENTS.md").write_text(
                "fastlane contract",
                encoding="utf-8",
            )
            (target / "infrastructure" / "AGENTS.md").write_text(
                "user contract",
                encoding="utf-8",
            )
            decision = adoption_decision(
                "infrastructure/AGENTS.md",
                "PRESERVE",
                b"user contract",
                b"fastlane contract",
            )
            map_path = write_adoption_map(
                root / "adoption.json",
                source,
                target,
                [decision],
            )
            plan = bootstrap.load_adoption_plan(map_path, source, target)

            report = bootstrap.copy_template(source, target, {}, adoption_plan=plan)

            self.assertTrue(report.partial_adoption)

    def test_target_only_nested_agents_file_marks_partial_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (target / "custom").mkdir(parents=True)
            (source / "safe.txt").write_text("safe", encoding="utf-8")
            target_agents = target / "custom" / "AGENTS.md"
            target_agents.write_text("owner instructions", encoding="utf-8")

            report = bootstrap.copy_template(source, target, {})

            self.assertTrue(report.partial_adoption)
            self.assertEqual(report.written, 1)
            self.assertEqual(
                target_agents.read_text(encoding="utf-8"), "owner instructions"
            )

    def test_runtime_control_files_are_not_placeholder_rendered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "scripts").mkdir()
            original = b"{{PROJECT_NAME}} {{AWS_REGION}} {{COST_POSTURE}}"
            (source / "bootstrap.py").write_bytes(original)
            (source / "bootstrap.manifest.json").write_bytes(original)
            (source / "scripts" / "bootstrap_doctor.py").write_bytes(original)
            (source / "scripts" / "task_waves.py").write_bytes(original)
            (source / "PRD.md").write_bytes(original)

            report = bootstrap.copy_template(
                source,
                target,
                {
                    "{{PROJECT_NAME}}": "Example",
                    "{{AWS_REGION}}": "us-east-1",
                    "{{COST_POSTURE}}": "MINIMIZE_TOTAL_COST; HARD_CAP: USD 25.00",
                },
            )

            self.assertEqual(report.written, 5)
            self.assertEqual((target / "bootstrap.py").read_bytes(), original)
            self.assertEqual(
                (target / "bootstrap.manifest.json").read_bytes(),
                original,
            )
            self.assertEqual(
                (target / "scripts" / "bootstrap_doctor.py").read_bytes(),
                original,
            )
            self.assertEqual(
                (target / "scripts" / "task_waves.py").read_bytes(),
                original,
            )
            self.assertEqual(
                (target / "PRD.md").read_text(encoding="utf-8"),
                "Example us-east-1 MINIMIZE_TOTAL_COST; HARD_CAP: USD 25.00",
            )


if __name__ == "__main__":
    unittest.main()
