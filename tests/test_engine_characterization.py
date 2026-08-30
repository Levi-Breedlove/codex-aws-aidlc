from __future__ import annotations

import ast
import json
import os
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from tests import engine_parity_cases as parity


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def script_import_graph() -> dict[str, set[str]]:
    scripts = {path.stem: path for path in (REPOSITORY_ROOT / "scripts").glob("*.py")}
    graph = {name: set() for name in scripts}
    for name, path in scripts.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported.extend(alias.name.split(".")[-1] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module.split(".")[-1])
            graph[name].update(item for item in imported if item in scripts)
    return graph


def import_cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    cycles: set[tuple[str, ...]] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in path:
            cycle = path[path.index(node) :] + [node]
            rotations = [
                tuple(cycle[index:-1] + cycle[:index] + [cycle[index]])
                for index in range(len(cycle) - 1)
            ]
            cycles.add(min(rotations))
            return
        for dependency in sorted(graph[node]):
            visit(dependency, [*path, node])

    for node in sorted(graph):
        visit(node, [])
    return sorted(cycles)


class EngineCharacterizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.oracle = json.loads(parity.ORACLE_PATH.read_text(encoding="utf-8"))
        cls.configuration = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["tool"]["fastlane"]["engine_characterization"]

    def test_monolith_ast_inventory_matches_the_locked_baseline(self) -> None:
        expected = self.oracle["doctor_characterization"]
        current = parity.doctor_characterization()
        engine_package = REPOSITORY_ROOT / "scripts/fastlane_engine"
        if not engine_package.exists():
            self.assertEqual(current, expected)
        else:
            self.assertLess(current["line_count"], expected["line_count"])
            self.assertLess(current["function_count"], expected["function_count"])
        self.assertEqual(expected["function_count"], 264)
        self.assertEqual(expected["class_count"], 39)
        self.assertGreater(expected["line_count"], 20_000)
        self.assertEqual(len(expected["source_sha256"]), 64)
        self.assertEqual(len(expected["structure_sha256"]), 64)

    def test_current_static_script_import_graph_has_no_cycles(self) -> None:
        graph = script_import_graph()
        self.assertEqual(import_cycles(graph), [])
        self.assertNotIn("tests", graph)

    def test_task_wave_has_eliminated_dynamic_doctor_loading(self) -> None:
        text = (REPOSITORY_ROOT / "scripts/task_waves.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        calls = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "load_bootstrap_doctor"
        )
        self.assertEqual(calls, 0)
        self.assertNotIn("spec_from_file_location(module_name", text)
        self.assertNotIn("import importlib.util", text)

    def test_characterization_thresholds_are_explicit_and_non_runtime(self) -> None:
        self.assertEqual(self.configuration["baseline_commit"], parity.BASELINE_COMMIT)
        self.assertEqual(self.configuration["maximum_warm_median_ms"], 964)
        self.assertEqual(self.configuration["preferred_warm_median_ms"], 700)
        self.assertEqual(self.configuration["maximum_peak_memory_mib"], 30)
        self.assertEqual(self.configuration["doctor_hard_review_lines"], 1200)
        self.assertEqual(self.configuration["module_hard_review_lines"], 1800)
        self.assertEqual(self.configuration["function_review_lines"], 100)
        self.assertEqual(self.configuration["complexity_review"], 15)

    def test_same_process_benchmark_is_ephemeral_and_strict_when_requested(
        self,
    ) -> None:
        strict = os.environ.get("FASTLANE_ENFORCE_PERFORMANCE_BUDGET") == "1"
        result = parity.benchmark_engine_scenarios(
            warmups=2 if strict else 1,
            iterations=10 if strict else 1,
        )
        self.assertEqual(result["warmups"], 2 if strict else 1)
        self.assertEqual(result["iterations"], 10 if strict else 1)
        expected = {
            "template": ("INTAKE_REQUIRED", 0, 0),
            "gate_a": ("WAITING_GATE_A", 0, 0),
            "gate_b": ("WAITING_GATE_B", 0, 0),
            "eight_task_plan": ("CONSTRUCTION_AUTONOMOUS", 8, 8),
        }
        self.assertEqual(set(result["scenarios"]), set(expected))
        for name, (lifecycle, total, ready) in expected.items():
            with self.subTest(scenario=name):
                scenario = result["scenarios"][name]
                self.assertEqual(scenario["lifecycle_state"], lifecycle)
                self.assertEqual(scenario["task_total"], total)
                self.assertEqual(scenario["task_ready"], ready)
                self.assertGreater(scenario["warm_median_wall_ms"], 0)
                self.assertGreater(scenario["warm_median_cpu_ms"], 0)
                self.assertLess(
                    scenario["peak_memory_mib"],
                    self.configuration["maximum_peak_memory_mib"],
                )
                if strict:
                    self.assertLessEqual(
                        scenario["warm_median_wall_ms"],
                        self.configuration["maximum_warm_median_ms"],
                    )
        if strict:
            self.assertEqual(result["iterations"], 10)
            self.assertEqual(result["platform"]["system"], "Linux")
            self.assertEqual(result["platform"]["distribution"], "ubuntu")
            self.assertRegex(result["platform"]["python_version"], r"^3\.12\.")
        tracked_results = list(REPOSITORY_ROOT.glob("*benchmark*.json"))
        self.assertEqual(tracked_results, [])

    def test_benchmark_defaults_and_positive_counts_are_explicit(self) -> None:
        with (
            mock.patch.object(
                parity,
                "benchmark_engine_scenarios",
                return_value={"scenarios": {}},
            ) as benchmark,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(parity.main(["--benchmark"]), 0)
        benchmark.assert_called_once_with(warmups=2, iterations=10)
        with self.assertRaisesRegex(ValueError, "warmups must be positive"):
            parity.benchmark_engine_scenarios(warmups=0, iterations=1)
        with self.assertRaisesRegex(ValueError, "iterations must be positive"):
            parity.benchmark_engine_scenarios(warmups=1, iterations=0)


if __name__ == "__main__":
    unittest.main()
