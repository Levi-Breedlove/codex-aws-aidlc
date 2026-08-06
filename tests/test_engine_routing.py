from __future__ import annotations

import ast
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

from scripts import bootstrap_doctor as doctor
from scripts.fastlane_engine import api


ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT / "scripts" / "fastlane_engine"
DOCTOR_PATH = ROOT / "scripts" / "bootstrap_doctor.py"
LIFECYCLE_DOMAINS = {"define", "design", "deliver", "aws"}


def module_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append((node.level, node.module or ""))
    return imports


class EngineRoutingTests(unittest.TestCase):
    def test_doctor_is_a_bounded_compatibility_facade(self) -> None:
        source = DOCTOR_PATH.read_text(encoding="utf-8")
        self.assertLessEqual(len(source.splitlines()), 1200)
        definitions = {
            node.name
            for node in ast.parse(source).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(
            {
                "main",
                "print_human",
                "_parse_current_intake_response",
                "_validate_current_gate_receipt",
            }.issubset(definitions)
        )
        self.assertFalse(
            {
                "inspect_project",
                "derive_route",
                "derive_remediation",
                "derive_interaction",
                "derive_context_plan",
                "build_report",
            }
            & definitions
        )

    def test_direct_file_loader_preserves_package_import_surface(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "doctor_routing_direct_loader", DOCTOR_PATH
        )
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        direct = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = direct
        try:
            spec.loader.exec_module(direct)
        finally:
            sys.modules.pop(spec.name, None)
        missing = sorted(
            name
            for name in doctor.__dict__
            if not name.startswith("__") and not hasattr(direct, name)
        )
        self.assertEqual(missing, [])

    def test_public_api_and_doctor_return_the_same_report(self) -> None:
        expected = doctor.inspect_project(ROOT, template_source=True)
        observed = api.inspect_project(ROOT, template_source=True)
        self.assertEqual(observed, expected)
        self.assertEqual(observed["schema_version"], 2)

    def test_core_and_package_import_boundaries_are_one_way(self) -> None:
        for path in sorted((ENGINE_ROOT / "core").glob("*.py")):
            with self.subTest(path=path.name):
                for level, module in module_imports(path):
                    if level:
                        self.assertFalse(module.startswith(tuple(LIFECYCLE_DOMAINS)))
        for path in sorted((ENGINE_ROOT / "package").glob("*.py")):
            with self.subTest(path=path.name):
                for level, module in module_imports(path):
                    if level >= 2:
                        self.assertTrue(module == "core" or module.startswith("core."))

    def test_lifecycle_domains_do_not_import_sibling_domains(self) -> None:
        for domain in sorted(LIFECYCLE_DOMAINS):
            for path in sorted((ENGINE_ROOT / domain).glob("*.py")):
                with self.subTest(domain=domain, path=path.name):
                    for level, module in module_imports(path):
                        if level < 2:
                            continue
                        imported_domain = module.split(".", 1)[0]
                        self.assertFalse(
                            imported_domain in LIFECYCLE_DOMAINS
                            and imported_domain != domain,
                            f"{path} imports sibling lifecycle domain {module}",
                        )

    def test_domain_modules_do_not_call_observation_or_mutation_apis(self) -> None:
        prohibited = {
            "open",
            "run",
            "Popen",
            "check_call",
            "check_output",
            "write_text",
            "write_bytes",
            "unlink",
        }
        for domain in sorted(LIFECYCLE_DOMAINS):
            for path in sorted((ENGINE_ROOT / domain).glob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                called = {
                    node.func.id
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                }
                called.update(
                    node.func.attr
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                )
                with self.subTest(domain=domain, path=path.name):
                    self.assertEqual(sorted(called & prohibited), [])

    def test_public_engine_import_has_no_cycle(self) -> None:
        module = importlib.import_module("scripts.fastlane_engine")
        self.assertIs(module.inspect_project, api.inspect_project)


if __name__ == "__main__":
    unittest.main()
