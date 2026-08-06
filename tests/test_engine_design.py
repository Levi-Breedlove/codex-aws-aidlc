from __future__ import annotations

import ast
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

from scripts import bootstrap_doctor as doctor
from scripts import fastlane_adr
from scripts.fastlane_engine import design
from scripts.fastlane_engine.design import adr as design_adr
from tests import test_adr_rationale as adr_fixtures
from tests import test_bootstrap_doctor as doctor_fixtures


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PACKAGE = REPOSITORY_ROOT / "scripts/fastlane_engine/design"


class EngineDesignTests(unittest.TestCase):
    def test_doctor_facade_delegates_complete_design_to_pure_engine(self) -> None:
        source = doctor_fixtures.complete_design_contract(
            (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        captured: dict[str, object] = {}
        evaluator = doctor._derive_design_contract_core

        def capture(*args: object, **kwargs: object):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return evaluator(*args, **kwargs)

        with mock.patch.object(
            doctor, "_derive_design_contract_core", side_effect=capture
        ):
            facade_contract, facade_issues = doctor.derive_design_contract(
                source, "DES-0001", required=True
            )

        core_contract, core_issues = evaluator(
            *captured["args"],
            **captured["kwargs"],  # type: ignore[arg-type]
        )
        self.assertEqual(facade_issues, [])
        self.assertEqual(core_issues, facade_issues)
        self.assertEqual(core_contract.to_dict(), facade_contract.to_dict())
        self.assertIs(evaluator, design.derive_design_contract)
        with self.assertRaises(FrozenInstanceError):
            facade_contract.status = "BLOCKED"  # type: ignore[misc]

    def test_adr_facade_and_observed_source_evaluator_are_exactly_equal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adr_directory = root / "docs/adr"
            adr_directory.mkdir(parents=True)
            (adr_directory / "0001-runtime.md").write_text(
                adr_fixtures.adr_text(), encoding="utf-8"
            )
            contract = adr_fixtures.design_contract()
            facade = fastlane_adr.derive_adr_rationale(root, contract, "")
            inventory, inventory_issues = fastlane_adr._safe_adr_inventory(root)
            sources: dict[str, str] = {}
            source_issues: dict[str, dict[str, str]] = {}
            for relative in inventory.values():
                text, issue = fastlane_adr._read_adr(root, relative)
                if issue is not None:
                    source_issues[relative] = issue
                elif text is not None:
                    sources[relative] = text
            pure = design_adr.derive_adr_rationale(
                contract,
                "",
                inventory,
                sources,
                inventory_issues=inventory_issues,
                source_issues=source_issues,
            )
        self.assertEqual(pure, facade)
        self.assertEqual(pure[0]["status"], "CURRENT")
        self.assertFalse(pure[0]["authoritative"])

    def test_design_domain_has_no_observation_or_sibling_domain_imports(self) -> None:
        forbidden_imports = {
            "boto3",
            "os",
            "requests",
            "socket",
            "subprocess",
            "urllib",
        }
        forbidden_calls = {
            "open",
            "iterdir",
            "read_bytes",
            "read_text",
            "stat",
            "write_bytes",
            "write_text",
        }
        sibling_domains = {"authority", "aws", "define", "deliver"}
        failures: list[str] = []
        for path in sorted(DESIGN_PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_imports:
                            failures.append(f"{path.name}: imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.split(".")[0] in forbidden_imports:
                        failures.append(f"{path.name}: imports {module}")
                    if any(part in sibling_domains for part in module.split(".")):
                        failures.append(f"{path.name}: imports sibling {module}")
                elif isinstance(node, ast.Call):
                    if (
                        isinstance(node.func, ast.Name)
                        and node.func.id in forbidden_calls
                    ):
                        failures.append(f"{path.name}: calls {node.func.id}")
                    elif (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr in forbidden_calls
                    ):
                        failures.append(f"{path.name}: calls {node.func.attr}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
