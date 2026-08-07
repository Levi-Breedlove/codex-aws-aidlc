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


def engine_module_graph() -> dict[str, set[str]]:
    """Resolve the complete Engine AST import graph, including local imports."""

    paths = sorted(ENGINE_ROOT.rglob("*.py"))
    modules: dict[str, Path] = {}
    for path in paths:
        relative = path.relative_to(ROOT).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules[".".join(parts)] = path

    graph = {name: set() for name in modules}
    for module_name, path in modules.items():
        package = (
            module_name
            if path.name == "__init__.py"
            else module_name.rpartition(".")[0]
        )
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                reference = "." * node.level + (node.module or "")
                candidates.append(
                    importlib.util.resolve_name(reference, package)
                    if node.level
                    else reference
                )
            for candidate in candidates:
                if candidate in graph:
                    graph[module_name].add(candidate)
    return graph


def import_cycle(graph: dict[str, set[str]]) -> tuple[str, ...]:
    visited: set[str] = set()
    active: list[str] = []
    active_set: set[str] = set()

    def visit(module: str) -> tuple[str, ...]:
        if module in active_set:
            start = active.index(module)
            return (*active[start:], module)
        if module in visited:
            return ()
        active.append(module)
        active_set.add(module)
        for dependency in sorted(graph[module]):
            cycle = visit(dependency)
            if cycle:
                return cycle
        active.pop()
        active_set.remove(module)
        visited.add(module)
        return ()

    for module in sorted(graph):
        cycle = visit(module)
        if cycle:
            return cycle
    return ()


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

    def test_full_engine_ast_import_graph_has_no_cycle(self) -> None:
        cycle = import_cycle(engine_module_graph())
        self.assertEqual(cycle, (), " -> ".join(cycle))

    def test_evaluation_modules_do_not_observe_git_after_snapshot_capture(
        self,
    ) -> None:
        prohibited = {"git_read", "inspect_git_baseline"}
        for relative in (
            "composition.py",
            "project_delivery.py",
            "project_validation.py",
            "report.py",
        ):
            path = ENGINE_ROOT / relative
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            calls = {
                node.func.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            self.assertEqual(calls & prohibited, set(), relative)

        delivery_imports = {
            module
            for _level, module in module_imports(ENGINE_ROOT / "project_delivery.py")
        }
        self.assertNotIn("api", delivery_imports)


if __name__ == "__main__":
    unittest.main()
