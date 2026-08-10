from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bootstrap
from scripts import bootstrap_doctor as doctor
from scripts import fastlane_contracts
from scripts import package_release, update_manifest
from scripts.fastlane_engine import api
from scripts.fastlane_engine.core import contracts
from scripts.fastlane_engine.core.diagnostics import (
    Diagnostic,
    DiagnosticCollector,
    DiagnosticDefinition,
)
from scripts.fastlane_engine.core.markdown_index import MarkdownDocumentIndex
from scripts.fastlane_engine.core.snapshot import (
    GitObserver,
    GitQueryKey,
    ObservationError,
    SnapshotObserver,
)
from scripts.fastlane_engine.project_inspection import (
    Context,
    PRD_FILE,
    capture_engine_snapshot,
    safe_read_text,
)
from tests.engine_complexity_exceptions import (
    REVIEWED_COMPLEXITY_EXCEPTIONS,
    REVIEWED_MODULE_SIZE_EXCEPTIONS,
)


ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT / "scripts" / "fastlane_engine"


class EngineFoundationTests(unittest.TestCase):
    def test_contract_facade_reexports_the_single_implementation(self) -> None:
        names = (
            "without_fenced_code",
            "split_markdown_table_row",
            "parse_exact_section_table",
            "parse_task_completion_evidence_cells",
            "parse_checkpoint_cells",
            "parse_checkpoint_git_receipt_value",
            "path_boundary_contains",
            "path_boundaries_overlap",
            "external_targets_overlap",
        )
        for name in names:
            self.assertIs(getattr(fastlane_contracts, name), getattr(contracts, name))

        from scripts.fastlane_engine.project_delivery import (
            DELIVERY_VALIDATION_POLICY,
        )

        self.assertIs(api.DELIVERY_VALIDATION_POLICY, DELIVERY_VALIDATION_POLICY)

    def test_diagnostic_shape_and_order_remain_report_compatible(self) -> None:
        definitions = {
            "KNOWN": DiagnosticDefinition(
                code="KNOWN",
                category="CORE",
                default_owner="CODEX",
                remediation_category="SAFE_CORRECTION",
                automatic_correction_eligible=True,
            )
        }
        collector = DiagnosticCollector(definitions, strict=True)
        collector.error("KNOWN", "first", "one.md")
        collector.warning("KNOWN", "second")
        self.assertEqual(
            [
                item.to_dict(f"DGN-{index:04d}")
                for index, item in enumerate(collector, 1)
            ],
            [
                {
                    "code": "KNOWN",
                    "severity": "ERROR",
                    "message": "first",
                    "diagnostic_id": "DGN-0001",
                    "path": "one.md",
                },
                {
                    "code": "KNOWN",
                    "severity": "WARNING",
                    "message": "second",
                    "diagnostic_id": "DGN-0002",
                },
            ],
        )
        with self.assertRaisesRegex(ValueError, "Unknown diagnostic code"):
            collector.error("UNKNOWN", "blocked")
        self.assertIs(doctor.Diagnostic, Diagnostic)

    def test_snapshot_opens_and_indexes_each_requested_file_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "record.md").write_text(
                "# Record\n\n| ID | Value |\n|---|---|\n| REQ-0001 | Ready |\n",
                encoding="utf-8",
            )
            observer = SnapshotObserver(root)
            first = observer.observe_text("record.md")
            second = observer.observe_text("record.md")
            snapshot = observer.freeze(
                bootstrap_state={"project": {"name": "Example"}},
                manifest={"required_files": ["record.md"]},
            )
            self.assertIs(first, second)
            self.assertEqual(snapshot.observation_metrics.files_opened, 1)
            self.assertEqual(snapshot.observation_metrics.markdown_indexes, 1)
            self.assertEqual(snapshot.markdown["record.md"].headings[0].title, "Record")
            self.assertEqual(
                snapshot.markdown["record.md"].record_ids[0][0], "REQ-0001"
            )
            with self.assertRaises(ObservationError):
                observer.observe_text("../unsafe.md")
            with self.assertRaises(TypeError):
                snapshot.bootstrap_state["project"]["name"] = "Changed"  # type: ignore[index]
            self.assertEqual(snapshot.manifest["required_files"], ("record.md",))

    def test_engine_snapshot_is_complete_immutable_and_reuses_observed_text(
        self,
    ) -> None:
        observed_at = datetime(2030, 1, 2, 3, 4, tzinfo=timezone.utc)
        original_open = Path.open
        opens: dict[str, int] = {}
        resolved_root = ROOT.resolve()

        def counted_open(path: Path, *args, **kwargs):
            try:
                relative = path.resolve().relative_to(resolved_root).as_posix()
            except ValueError:
                pass
            else:
                opens[relative] = opens.get(relative, 0) + 1
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", counted_open):
            snapshot = capture_engine_snapshot(ROOT, observed_at=observed_at)

        required = set(snapshot.manifest["required_files"])
        binary_test_paths = sorted(
            path
            for path in required
            if path.startswith(("tests/engine_", "tests/fixtures/", "tests/test_"))
        )
        self.assertEqual(required, set(snapshot.files))
        self.assertTrue(binary_test_paths)
        self.assertEqual(snapshot.observed_at, observed_at)
        self.assertEqual(snapshot.observation_metrics.files_opened, len(required))
        self.assertEqual(
            snapshot.observation_metrics.markdown_indexes,
            sum(
                path.endswith(".md") and path not in binary_test_paths
                for path in required
            ),
        )
        self.assertEqual(snapshot.observation_metrics.git_processes, 1)
        self.assertEqual(snapshot.observation_metrics.duplicate_git_processes, 0)
        self.assertEqual(
            {path: opens[path] for path in required}, dict.fromkeys(required, 1)
        )
        for path in binary_test_paths:
            fixture = snapshot.files[path]
            self.assertIsNone(fixture.presentation_text)
            self.assertIsNone(fixture.canonical_text)
            self.assertEqual(
                fixture.byte_sha256,
                snapshot.manifest["source_sha256"][path],
            )
        self.assertIsNotNone(snapshot.files["tests/AGENTS.md"].canonical_text)
        self.assertIsNotNone(snapshot.files[PRD_FILE].canonical_text)

        context = Context(ROOT, template_source=True, observed_snapshot=snapshot)
        with mock.patch.object(
            Path, "open", side_effect=AssertionError("snapshot text was reread")
        ):
            self.assertEqual(
                safe_read_text(context, PRD_FILE),
                snapshot.files[PRD_FILE].canonical_text,
            )
        with self.assertRaises(TypeError):
            snapshot.files["new"] = snapshot.files[PRD_FILE]  # type: ignore[index]
        with self.assertRaises(TypeError):
            snapshot.git.query_results[GitQueryKey("new")] = next(  # type: ignore[index]
                iter(snapshot.git.query_results.values())
            )

    def test_git_observer_memoizes_exact_canonical_queries(self) -> None:
        head = "a" * 40
        other = "b" * 40
        calls: list[tuple[str, ...]] = []

        def run(command, **_kwargs):
            calls.append(tuple(command))
            if "status" in command:
                stdout = (
                    f"# branch.oid {head}\0"
                    "# branch.head fast-lane\0"
                    f"1 M. N... 100644 100644 100644 {head} {head} "
                    "docs/project/PRD.md\0"
                    "? notes.txt\0"
                ).encode()
            else:
                stdout = b""
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

        observer = GitObserver(ROOT, resolve_git=lambda _root: "git", run=run)
        observer.observe_repository_state()
        first = observer.query("merge-base", "--is-ancestor", head, other)
        second = observer.query("merge-base", "--is-ancestor", head, other)
        snapshot = observer.freeze()

        self.assertIs(first, second)
        self.assertEqual(len(calls), 2)
        self.assertEqual(snapshot.process_count, 2)
        self.assertEqual(snapshot.duplicate_processes, 0)
        self.assertEqual(snapshot.branch, "fast-lane")
        self.assertEqual(snapshot.head_sha, head)
        self.assertEqual(snapshot.tracked_changes, ("docs/project/PRD.md",))
        self.assertEqual(snapshot.staged_changes, ("docs/project/PRD.md",))
        self.assertEqual(snapshot.untracked_paths, ("notes.txt",))
        self.assertIs(
            snapshot.result("merge-base", "--is-ancestor", head, other), first
        )

    def test_complete_engine_evaluation_never_reopens_snapshot_files(self) -> None:
        required = set(
            json.loads((ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8"))[
                "required_files"
            ]
        )
        original_open = Path.open
        opens: dict[str, int] = {}
        resolved_root = ROOT.resolve()

        def counted_open(path: Path, *args, **kwargs):
            try:
                relative = path.resolve().relative_to(resolved_root).as_posix()
            except ValueError:
                pass
            else:
                opens[relative] = opens.get(relative, 0) + 1
            return original_open(path, *args, **kwargs)

        with (
            mock.patch.object(Path, "open", counted_open),
            mock.patch(
                "scripts.fastlane_engine.core.snapshot.subprocess.run",
                wraps=subprocess.run,
            ) as git_run,
        ):
            report = api.inspect_project(ROOT, template_source=True)

        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(
            {path: opens[path] for path in required}, dict.fromkeys(required, 1)
        )
        self.assertLessEqual(git_run.call_count, 2)

    def test_populated_project_stays_within_the_git_observation_budget(self) -> None:
        from tests import test_bootstrap_doctor as fixture_module

        with tempfile.TemporaryDirectory() as temporary:
            fixture = fixture_module.BootstrapDoctorTests(methodName="runTest")
            project = fixture.copy_project(Path(temporary))
            fixture.approve_project(project)
            with mock.patch(
                "scripts.fastlane_engine.core.snapshot.subprocess.run",
                wraps=subprocess.run,
            ) as git_run:
                report = api.inspect_project(project)
            snapshot = capture_engine_snapshot(project)

        self.assertEqual(report["schema_version"], 2)
        self.assertLessEqual(git_run.call_count, 6)
        self.assertLessEqual(snapshot.git.process_count, 6)
        self.assertEqual(snapshot.git.duplicate_processes, 0)
        self.assertIsNotNone(snapshot.git.head_sha)

    def test_normal_evaluation_uses_only_the_snapshot_clock(self) -> None:
        class DeniedClock:
            @classmethod
            def now(cls, *_args, **_kwargs):
                raise AssertionError("lifecycle evaluation requested a second clock")

        with (
            mock.patch("scripts.fastlane_engine.authority.aws.datetime", DeniedClock),
            mock.patch(
                "scripts.fastlane_engine.project_inspection.datetime", DeniedClock
            ),
        ):
            report = api.inspect_project(ROOT, template_source=True)
        self.assertEqual(report["schema_version"], 2)

    def test_markdown_index_ignores_fenced_headings_and_tables(self) -> None:
        text = (
            "# Visible\n\n"
            "```text\n# Hidden\n| Hidden | Table |\n|---|---|\n```\n\n"
            "## Decision\n\n| ID | Value |\n|---|---|\n| TECH-0001 | Selected |\n\n"
            "```mermaid\nflowchart LR\nA --> B\n```\n"
        )
        index = MarkdownDocumentIndex.build(text)
        self.assertEqual(
            [item.title for item in index.headings], ["Visible", "Decision"]
        )
        self.assertEqual(len(index.tables), 1)
        self.assertEqual(len(index.mermaid), 1)
        self.assertEqual(index.record_ids[0][0], "TECH-0001")

    def test_markdown_index_fails_safe_on_a_malformed_pipe_line(self) -> None:
        index = MarkdownDocumentIndex.build("# Record\n\n| incomplete\n")
        self.assertEqual(index.tables, ())

    def test_modular_package_validators_match_legacy_diagnostics(self) -> None:
        manifest = json.loads((ROOT / doctor.MANIFEST_FILE).read_text(encoding="utf-8"))
        state = json.loads((ROOT / doctor.STATE_FILE).read_text(encoding="utf-8"))

        legacy_manifest = doctor.Context(ROOT, template_source=True)
        doctor.validate_manifest(legacy_manifest, manifest)
        self.assertIsInstance(legacy_manifest.diagnostics, list)
        self.assertIn(doctor.MANIFEST_FILE, legacy_manifest.source_file_bytes)

        legacy_state = doctor.Context(ROOT, template_source=True)
        self.assertTrue(doctor.validate_state_schema(legacy_state, state))

        legacy_prompt = doctor.Context(ROOT, template_source=True)
        doctor.validate_prompt_pack(legacy_prompt, manifest, state)
        self.assertFalse(legacy_prompt.has_errors)

        legacy_placeholders = doctor.Context(ROOT)
        legacy_placeholders.texts = {"sample.md": "{{PROJECT_NAME}}"}
        doctor.validate_placeholders(legacy_placeholders)
        self.assertEqual(
            legacy_placeholders.diagnostics[0].code, "PLACEHOLDER_UNRESOLVED"
        )

    def test_foundation_import_boundaries_and_side_effects_are_enforced(self) -> None:
        for path in sorted(ENGINE_ROOT.rglob("*.py")):
            relative = path.relative_to(ENGINE_ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            imported: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            if relative != "core/snapshot.py":
                self.assertNotIn("subprocess", imported, relative)
            if relative.startswith("core/"):
                self.assertFalse(
                    any(
                        name.startswith(
                            ("define", "design", "deliver", "aws", "authority")
                        )
                        for name in imported
                    ),
                    relative,
                )
            if relative.startswith("package/"):
                self.assertFalse(
                    any(
                        name.startswith(
                            ("define", "design", "deliver", "aws", "authority")
                        )
                        for name in imported
                    ),
                    relative,
                )

    def test_every_engine_runtime_module_is_independently_control_protected(
        self,
    ) -> None:
        runtime = {
            path.relative_to(ROOT).as_posix() for path in ENGINE_ROOT.rglob("*.py")
        }
        manifest = json.loads((ROOT / doctor.MANIFEST_FILE).read_text(encoding="utf-8"))
        self.assertEqual(runtime, doctor.ENGINE_RUNTIME_CONTROL_FILES)
        self.assertTrue(runtime <= bootstrap.NO_RENDER_PATHS)
        self.assertTrue(runtime <= bootstrap.CORE_CONTROL_PATHS)
        self.assertTrue(runtime <= bootstrap.RUNTIME_CONTROL_PATHS)
        self.assertTrue(runtime <= set(update_manifest.CONTROL_FILES))
        self.assertTrue(runtime <= package_release.REQUIRED_CONTROL_FILES)
        self.assertTrue(runtime <= set(manifest["required_files"]))
        self.assertTrue(runtime <= set(manifest["control_sha256"]))
        self.assertTrue(runtime <= set(manifest["source_sha256"]))
        self.assertIn("scripts/fastlane_engine/AGENTS.md", manifest["required_files"])

    def test_engine_complexity_overages_require_explicit_reviewed_exceptions(
        self,
    ) -> None:
        configuration = {
            "module_hard_review_lines": 1_800,
            "function_review_lines": 100,
            "complexity_review": 15,
        }
        branch_nodes = (
            ast.If,
            ast.For,
            ast.While,
            ast.Try,
            ast.With,
            ast.BoolOp,
            ast.IfExp,
            ast.comprehension,
            ast.Match,
        )
        observed: dict[str, dict[str, int]] = {}
        observed_modules: dict[str, int] = {}
        for path in sorted(ENGINE_ROOT.rglob("*.py")):
            relative = path.relative_to(ENGINE_ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            module_lines = len(text.splitlines())
            if module_lines > configuration["module_hard_review_lines"]:
                observed_modules[relative] = module_lines
            module_limit = int(
                REVIEWED_MODULE_SIZE_EXCEPTIONS.get(relative, {}).get(
                    "maximum_lines", configuration["module_hard_review_lines"]
                )
            )
            self.assertLessEqual(
                module_lines,
                module_limit,
                relative,
            )
            tree = ast.parse(text, filename=relative)
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                line_count = node.end_lineno - node.lineno + 1
                complexity = 1 + sum(
                    isinstance(item, branch_nodes) for item in ast.walk(node)
                )
                if (
                    line_count > configuration["function_review_lines"]
                    or complexity > configuration["complexity_review"]
                ):
                    observed[f"{relative}:{node.name}"] = {
                        "lines": line_count,
                        "complexity": complexity,
                    }

        self.assertEqual(
            set(observed_modules),
            set(REVIEWED_MODULE_SIZE_EXCEPTIONS),
            "Engine module-size exceptions must be explicit, current, and complete",
        )
        for key, line_count in observed_modules.items():
            with self.subTest(module=key):
                exception = REVIEWED_MODULE_SIZE_EXCEPTIONS[key]
                self.assertEqual(exception["reviewed_lines"], line_count)
                self.assertTrue(str(exception["reason"]).strip())
                self.assertRegex(
                    str(exception["reviewed_in"]), r"^[0-9]+\.[0-9]+\.[0-9]+$"
                )
                self.assertRegex(
                    str(exception["expires"]),
                    r"^(?:PERMANENT|[0-9]+\.[0-9]+\.[0-9]+)$",
                )

        self.assertEqual(
            set(observed),
            set(REVIEWED_COMPLEXITY_EXCEPTIONS),
            "Engine complexity exceptions must be explicit, current, and complete",
        )
        for key, metrics in observed.items():
            with self.subTest(symbol=key):
                exception = REVIEWED_COMPLEXITY_EXCEPTIONS[key]
                self.assertRegex(
                    str(exception["reviewed_in"]),
                    r"^[0-9]+\.[0-9]+\.[0-9]+$",
                )
                self.assertTrue(str(exception["reason"]).strip())
                self.assertRegex(
                    str(exception["expires"]),
                    r"^(?:PERMANENT|[0-9]+\.[0-9]+\.[0-9]+)$",
                )
                self.assertEqual(exception["reviewed_lines"], metrics["lines"])
                self.assertEqual(
                    exception["reviewed_complexity"], metrics["complexity"]
                )
                self.assertLessEqual(metrics["lines"], exception["maximum_lines"])
                self.assertLessEqual(
                    metrics["complexity"], exception["maximum_complexity"]
                )


if __name__ == "__main__":
    unittest.main()
