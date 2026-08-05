from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path
from typing import Any

from tests import engine_parity_cases as parity


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
ACCOUNT_ID = re.compile(r"\d{12}")


def first_difference(expected: Any, actual: Any, path: str = "$") -> str | None:
    if type(expected) is not type(actual):
        return f"{path}: {type(expected).__name__} != {type(actual).__name__}"
    if isinstance(expected, dict):
        expected_keys = list(expected)
        actual_keys = list(actual)
        if expected_keys != actual_keys:
            return f"{path}: keys {expected_keys!r} != {actual_keys!r}"
        for key in expected:
            difference = first_difference(expected[key], actual[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}: length {len(expected)} != {len(actual)}"
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            difference = first_difference(
                expected_item, actual_item, f"{path}[{index}]"
            )
            if difference:
                return difference
        return None
    if expected != actual:
        return f"{path}: {expected!r} != {actual!r}"
    return None


def discovered_test_selectors() -> set[str]:
    selectors: set[str] = set()
    for path in sorted((REPOSITORY_ROOT / "tests").glob("test_*.py")):
        module = f"tests.{path.stem}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name.startswith(
                    "test_"
                ):
                    selectors.add(f"{module}.{node.name}.{child.name}")
    return selectors


class EngineParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.oracle = json.loads(parity.ORACLE_PATH.read_text(encoding="utf-8"))

    def test_oracle_is_bound_to_the_exact_pre_refactor_baseline(self) -> None:
        self.assertEqual(self.oracle["schema_version"], 1)
        self.assertEqual(self.oracle["baseline"]["commit"], parity.BASELINE_COMMIT)
        self.assertEqual(
            self.oracle["baseline"]["package_version"],
            "1" + ".2.10",
        )
        self.assertEqual(self.oracle["baseline"]["report_schema_version"], 2)
        self.assertEqual(
            self.oracle["normalization"]["allowed"],
            [
                "package version",
                "repository or synthetic Git commit identity",
            ],
        )
        self.assertIn(
            "canonical projections or receipts",
            self.oracle["normalization"]["forbidden"],
        )

    def test_required_scenarios_are_bound_to_existing_regressions(self) -> None:
        expected = {
            name: list(selectors)
            for name, selectors in parity.SCENARIO_COVERAGE.items()
        }
        self.assertEqual(self.oracle["scenario_coverage"], expected)
        discovered = discovered_test_selectors()
        for scenario, selectors in expected.items():
            self.assertTrue(selectors, scenario)
            for selector in selectors:
                with self.subTest(scenario=scenario, selector=selector):
                    self.assertIn(selector, discovered)

    def test_complete_normalized_reports_match_the_frozen_oracle(self) -> None:
        observed = parity.build_parity_reports()
        self.assertEqual(tuple(observed), parity.REPORT_CASES)
        for name in parity.REPORT_CASES:
            with self.subTest(case=name):
                expected_case = self.oracle["report_cases"][name]
                difference = first_difference(expected_case, observed[name])
                self.assertIsNone(difference, difference)
                self.assertEqual(
                    parity.canonical_digest(observed[name]),
                    self.oracle["report_case_digests"][name],
                )

    def test_exact_gate_and_aws_receipts_match_the_frozen_oracle(self) -> None:
        observed = parity.receipt_contracts()
        self.assertEqual(observed, self.oracle["receipt_contracts"])
        self.assertEqual(
            tuple(observed),
            (
                "APPROVE REQUIREMENTS GATE A",
                "APPROVE PRD AND CONSTRUCTION GATE B",
                "AUTHORIZE AWS READ-ONLY PREFLIGHT",
                "AUTHORIZE AWS DEPLOYMENT",
                "AUTHORIZE AWS TEARDOWN",
            ),
        )

    def test_oracle_contains_only_synthetic_repository_relative_data(self) -> None:
        text = parity.ORACLE_PATH.read_text(encoding="utf-8")
        self.assertIsNone(WINDOWS_PATH.search(text))
        self.assertNotIn("/Users/", text)
        self.assertNotIn("/home/", text)
        self.assertNotIn("OneDrive", text)
        self.assertNotIn("AWS_ACCESS_KEY", text)
        self.assertNotIn("SECRET_ACCESS_KEY", text)

        def strings(value: Any):
            if isinstance(value, dict):
                for item in value.values():
                    yield from strings(item)
            elif isinstance(value, list):
                for item in value:
                    yield from strings(item)
            elif isinstance(value, str):
                yield value

        for value in strings(self.oracle):
            self.assertIsNone(ACCOUNT_ID.fullmatch(value), value)
            self.assertNotIn("arn:aws", value.casefold())


if __name__ == "__main__":
    unittest.main()
