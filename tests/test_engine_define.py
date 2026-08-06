from __future__ import annotations

import ast
import dataclasses
import unittest
from pathlib import Path

from scripts import bootstrap_doctor as doctor
from scripts import fastlane_contracts
from scripts.fastlane_engine import api
from scripts.fastlane_engine.core import contracts
from scripts.fastlane_engine.define import coverage, intake, project, requirements
from scripts.fastlane_engine.define.models import RequirementsContract


ROOT = Path(__file__).resolve().parents[1]
DEFINE_ROOT = ROOT / "scripts" / "fastlane_engine" / "define"


class EngineDefineTests(unittest.TestCase):
    def test_public_facades_share_the_extracted_define_implementations(self) -> None:
        functions = {
            "derive_change_impact_contract": coverage.derive_change_impact_contract,
            "derive_coverage_contract": coverage.derive_coverage_contract,
            "derive_intake_foundation_contract": intake.derive_intake_foundation_contract,
            "derive_req_aws_materiality": project.derive_req_aws_materiality,
            "derive_requirements_contract": requirements.derive_requirements_contract,
        }
        for name, implementation in functions.items():
            self.assertIs(getattr(doctor, name), implementation)
            self.assertIs(getattr(api, name), implementation)

        self.assertIs(doctor.RequirementsContract, RequirementsContract)
        self.assertIs(api.RequirementsContract, RequirementsContract)

    def test_contract_facade_includes_the_moved_markdown_primitives(self) -> None:
        names = (
            "ContractTable",
            "contract_table_after_heading",
            "contract_table_in_section",
            "markdown_tables",
            "split_table_row",
            "table_after_heading",
        )
        for name in names:
            self.assertIs(getattr(fastlane_contracts, name), getattr(contracts, name))

    def test_define_models_are_immutable_non_authoritative_results(self) -> None:
        contract = RequirementsContract(status="READY")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            contract.status = "BLOCKED"  # type: ignore[misc]

    def test_define_modules_have_no_observation_or_mutation_dependencies(self) -> None:
        forbidden_import_roots = {
            "boto3",
            "botocore",
            "http",
            "os",
            "pathlib",
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
            "compile",
            "eval",
            "exec",
            "open",
        }
        sibling_domains = {"authority", "aws", "deliver", "design"}

        for path in sorted(DEFINE_ROOT.glob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            module_docstring = ast.get_docstring(tree) or ""
            self.assertTrue(module_docstring, relative)

            imported_roots: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots.update(
                        alias.name.split(".", 1)[0] for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_roots.add(node.module.split(".", 1)[0])
                    self.assertFalse(
                        any(part in sibling_domains for part in node.module.split(".")),
                        relative,
                    )
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in forbidden_calls
                ):
                    self.fail(f"{relative} calls forbidden {node.func.id}()")

            self.assertEqual(imported_roots & forbidden_import_roots, set(), relative)

    def test_doctor_no_longer_defines_extracted_define_contracts(self) -> None:
        tree = ast.parse(
            (ROOT / "scripts" / "bootstrap_doctor.py").read_text(encoding="utf-8")
        )
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.ClassDef)
        }
        extracted = {
            "AssumptionLifecycleRecord",
            "ChangeImpactContract",
            "CoverageContract",
            "IntakeFoundationContract",
            "RequirementsChangeLineage",
            "RequirementsContract",
            "derive_change_impact_contract",
            "derive_coverage_contract",
            "derive_intake_foundation_contract",
            "derive_req_aws_materiality",
            "derive_requirements_contract",
        }
        self.assertEqual(definitions & extracted, set())


if __name__ == "__main__":
    unittest.main()
