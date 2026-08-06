from __future__ import annotations

import ast
import dataclasses
import unittest
from pathlib import Path

from scripts import bootstrap_doctor as doctor
from scripts import task_waves
from scripts.fastlane_engine import api
from scripts.fastlane_engine import deliver


ROOT = Path(__file__).resolve().parents[1]
DELIVER_ROOT = ROOT / "scripts" / "fastlane_engine" / "deliver"


class EngineDeliverTests(unittest.TestCase):
    def test_doctor_facade_uses_the_extracted_delivery_contracts(self) -> None:
        direct_functions = {
            "declared_task_waivers": deliver.declared_task_waivers,
            "evidence_timestamp": deliver.evidence_timestamp,
            "external_target_contains": deliver.external_target_contains,
            "inspect_task_blocks": deliver.inspect_task_blocks,
            "inspect_task_sections": deliver.inspect_task_sections,
            "parse_checkpoint_git_receipt": deliver.parse_checkpoint_git_receipt,
            "parse_checkpoint_rows": deliver.parse_checkpoint_rows,
            "parse_observed_property_run": deliver.parse_observed_property_run,
            "parse_task_completion_evidence": deliver.parse_task_completion_evidence,
            "parse_verification_matrix": deliver.parse_verification_matrix,
            "replay_evidence_matches_contract": deliver.replay_evidence_matches_contract,
            "require_durable_evidence_source": deliver.require_durable_evidence_source,
            "require_explicit_evidence_value": deliver.require_explicit_evidence_value,
            "task_property_execution_table": deliver.task_property_execution_table,
            "task_requirement_evidence_dispositions": (
                deliver.task_requirement_evidence_dispositions
            ),
            "task_waiver_rows": deliver.task_waiver_rows,
            "validate_done_evidence": deliver.validate_done_evidence,
        }
        for name, implementation in direct_functions.items():
            self.assertIs(getattr(doctor, name), implementation, name)

        for name in (
            "InspectedTask",
            "TaskCompletionEvidenceRow",
            "TaskRequirementCoverage",
            "TaskRequirementCoverageResult",
            "TaskSummary",
        ):
            self.assertIs(getattr(doctor, name), getattr(deliver, name), name)

    def test_task_mutator_consumes_public_delivery_api_without_doctor_loading(
        self,
    ) -> None:
        source = (ROOT / "scripts" / "task_waves.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules: set[str] = set()
        function_names = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

        self.assertNotIn("importlib.util", imported_modules)
        self.assertNotIn("load_bootstrap_doctor", function_names)
        self.assertIn("fastlane_engine.api", imported_modules)
        self.assertEqual(
            task_waves.ApprovedTaskContract.__qualname__,
            api.ApprovedTaskContract.__qualname__,
        )
        self.assertTrue(
            task_waves.engine_task_requirement_coverage.__module__.endswith(
                "fastlane_engine.deliver.tasks"
            )
        )

    def test_delivery_models_are_immutable_non_authoritative_results(self) -> None:
        coverage = deliver.TaskRequirementCoverage(
            requirement_id="REQ-0001",
            acceptance_id="AC-EXAMPLE-001",
            disposition="TASKS",
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            coverage.disposition = "EVIDENCE"  # type: ignore[misc]

    def test_delivery_modules_have_no_observation_or_sibling_domain_imports(
        self,
    ) -> None:
        forbidden_import_roots = {
            "boto3",
            "botocore",
            "http",
            "os",
            "requests",
            "shutil",
            "socket",
            "subprocess",
            "tempfile",
            "time",
            "urllib",
        }
        forbidden_calls = {
            "__import__",
            "eval",
            "exec",
            "open",
            "read_bytes",
            "read_text",
            "write_bytes",
            "write_text",
        }
        sibling_domains = {"authority", "aws", "define", "design"}
        failures: list[str] = []

        for path in sorted(DELIVER_ROOT.glob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            self.assertTrue(ast.get_docstring(tree), relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".", 1)[0] in forbidden_import_roots:
                            failures.append(f"{relative}: imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.split(".", 1)[0] in forbidden_import_roots:
                        failures.append(f"{relative}: imports {module}")
                    if any(part in sibling_domains for part in module.split(".")):
                        failures.append(f"{relative}: imports sibling {module}")
                elif isinstance(node, ast.Call):
                    if (
                        isinstance(node.func, ast.Name)
                        and node.func.id in forbidden_calls
                    ):
                        failures.append(f"{relative}: calls {node.func.id}")
                    elif (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr in forbidden_calls
                    ):
                        failures.append(f"{relative}: calls {node.func.attr}")

        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
