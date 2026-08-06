from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

import bootstrap
from scripts import bootstrap_doctor as doctor
from scripts import fastlane_contracts
from scripts import package_release, update_manifest
from scripts.fastlane_engine.core import contracts
from scripts.fastlane_engine.core.diagnostics import (
    Diagnostic,
    DiagnosticCollector,
    DiagnosticDefinition,
)
from scripts.fastlane_engine.core.markdown_index import MarkdownDocumentIndex
from scripts.fastlane_engine.core.snapshot import ObservationError, SnapshotObserver


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

    def test_new_engine_modules_respect_size_and_complexity_review_budgets(
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
        for path in sorted(ENGINE_ROOT.rglob("*.py")):
            relative = path.relative_to(ENGINE_ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            self.assertLessEqual(
                len(text.splitlines()),
                configuration["module_hard_review_lines"],
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
                label = f"{relative}:{node.lineno}:{node.name}"
                if (
                    line_count > configuration["function_review_lines"]
                    or complexity > configuration["complexity_review"]
                ):
                    docstring = ast.get_docstring(node) or ""
                    self.assertRegex(docstring, r"^(?:SAFETY|COMPATIBILITY):", label)


if __name__ == "__main__":
    unittest.main()
