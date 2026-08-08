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
        cls.qualification_oracle = json.loads(
            parity.QUALIFICATION_ORACLE_PATH.read_text(encoding="utf-8")
        )

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
        self.assertEqual(
            self.oracle["approved_behavior_changes"],
            parity.APPROVED_BEHAVIOR_CHANGES,
        )
        self.assertEqual(
            parity.frozen_doctor_characterization(),
            self.oracle["doctor_characterization"],
        )

    def test_report_cases_preserve_truthful_summary_semantics(self) -> None:
        reports = parity.build_parity_reports()
        expected = {
            "template_source": (
                "ANSWER_OPEN_DECISIONS",
                "Run `init template`.",
                "Not yet confirmed",
                "Not yet initialized",
                "None",
            ),
            "unconfigured_template": (
                "COMPLETE_PREREQUISITE_CHECKLIST",
                "Run `init template`.",
                "Not yet confirmed",
                "Not yet initialized",
                "None",
            ),
            "rendered_intake": (
                "ANSWER_OPEN_DECISIONS",
                "Answer the current project question.",
                "Not yet confirmed",
                "REQ-0001",
                "Not approved (boundary record AUTH-0001)",
            ),
            "gate_a_pending": (
                "APPROVE_GATE_A",
                "Review the requirements and approve them or request a correction.",
                "FR-001 in scope; production is out of scope",
                "REQ-0001",
                "Not approved (boundary record AUTH-0001)",
            ),
            "gate_a_approved": (
                "NONE_CONTINUE_AUTOMATICALLY",
                "Nothing",
                "FR-001 in scope; production is out of scope",
                "REQ-0001",
                "Not approved (boundary record AUTH-0001)",
            ),
            "gate_b_pending": (
                "APPROVE_GATE_B",
                "Review the technical plan and approve it or request a correction.",
                "FR-001 in scope; production is out of scope",
                "DES-0001",
                "Not approved (boundary record AUTH-0001)",
            ),
            "gate_b_approved": (
                "NONE_CONTINUE_AUTOMATICALLY",
                "Nothing",
                "FR-001 in scope; production is out of scope",
                "DES-0001",
                "Approved (AUTH-0001)",
            ),
        }
        for name, values in expected.items():
            with self.subTest(case=name):
                action, need, boundary, updated, construction = values
                report = reports[name]["report"]
                self.assertEqual(report["interaction"]["owner_action_kind"], action)
                documents = report["document_summaries"]["documents"]
                self.assertEqual(
                    {item["need_from_owner"] for item in documents}, {need}
                )
                self.assertEqual(len({item["next_action"] for item in documents}), 1)
                prd = next(
                    item for item in documents if item["path"] == "docs/project/PRD.md"
                )
                fields = {item["label"]: item["value"] for item in prd["fields"]}
                self.assertEqual(fields["First-release boundary"], boundary)
                self.assertEqual(fields["Updated"], updated)
                self.assertEqual(fields["Construction authorization"], construction)

    def test_summary_truth_change_preserves_every_other_report_contract(self) -> None:
        reports = parity.build_parity_reports()
        observed = {
            name: parity.canonical_digest(parity.summary_truth_compatibility_case(case))
            for name, case in reports.items()
        }
        self.assertEqual(observed, parity.SUMMARY_TRUTH_COMPATIBILITY_DIGESTS)
        self.assertEqual(
            self.oracle["summary_truth_compatibility"]["report_case_digests"],
            parity.SUMMARY_TRUTH_COMPATIBILITY_DIGESTS,
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
                    self.assertIn(
                        parity.current_scenario_selector(selector), discovered
                    )

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

    def test_current_architecture_reports_match_independent_owner_meaning(self) -> None:
        reports = parity.build_qualification_reports()
        expected = {
            "stale_gate_a_summary": {
                "ok": False,
                "lifecycle_state": "WAITING_GATE_A",
                "next_prompt": "INTAKE-20",
                "owner_action_kind": "NONE_CONTINUE_AUTOMATICALLY",
                "summary_status": "STALE",
                "brief_status": "BLOCKED",
                "remediation_action": "CORRECT_AND_REVALIDATE",
                "authorizations": {"construction": "NONE", "aws": "NONE"},
            },
            "task_ready": {
                "ok": True,
                "lifecycle_state": "CONSTRUCTION_SINGLE",
                "next_prompt": "BUILD-10",
                "owner_action_kind": "NONE_CONTINUE_AUTOMATICALLY",
                "summary_status": "CURRENT",
                "brief_status": "NONE",
                "remediation_action": "CONTINUE_CURRENT_ROUTE",
                "authorizations": {"construction": "AUTH-0001", "aws": "NONE"},
            },
        }
        for name, meaning in expected.items():
            with self.subTest(case=name):
                report = reports[name]["report"]
                observed = {
                    "ok": report["ok"],
                    "lifecycle_state": report["lifecycle_state"],
                    "next_prompt": report["next_prompt"],
                    "owner_action_kind": report["interaction"]["owner_action_kind"],
                    "summary_status": report["document_summaries"]["status"],
                    "brief_status": report["owner_decision_brief"]["status"],
                    "remediation_action": report["remediation"]["next_action"][
                        "action_kind"
                    ],
                    "authorizations": report["authorizations"],
                }
                self.assertEqual(observed, meaning)

    def test_current_architecture_reports_match_qualification_oracle(self) -> None:
        oracle = self.qualification_oracle
        self.assertEqual(oracle["schema_version"], 1)
        self.assertEqual(oracle["baseline"]["commit"], parity.QUALIFICATION_BASE_COMMIT)
        self.assertEqual(
            oracle["baseline"]["package_version"],
            parity.QUALIFICATION_BASE_PACKAGE_VERSION,
        )
        self.assertEqual(oracle["baseline"]["report_schema_version"], 2)
        observed = parity.build_qualification_reports()
        self.assertEqual(tuple(observed), parity.QUALIFICATION_REPORT_CASES)
        for name in parity.QUALIFICATION_REPORT_CASES:
            with self.subTest(case=name):
                difference = first_difference(
                    oracle["report_cases"][name], observed[name]
                )
                self.assertIsNone(difference, difference)
                self.assertEqual(
                    parity.canonical_digest(observed[name]),
                    oracle["report_case_digests"][name],
                )

    def test_deployment_terminals_match_independent_evidence_meaning(self) -> None:
        expected: dict[str, dict[str, Any]] = {
            "action_started": {
                "status": "ACTION_TERMINAL_REQUIRED",
                "action_status": "STARTED",
                "reconciliation_status": "NONE",
                "phase": "AWS-20",
                "route": ["AWS_DEPLOYMENT_ACTION_TERMINAL", "AWS-20"],
                "issues": [],
            },
            **{
                f"action_{status.casefold()}": {
                    "status": "RECONCILIATION_REQUIRED",
                    "action_status": status,
                    "reconciliation_status": "NONE",
                    "phase": "AWS-20",
                    "route": ["AWS_DEPLOYMENT_RECONCILIATION", "AWS-30"],
                    "issues": [],
                }
                for status in ("SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN")
            },
            **{
                f"reconciled_{status.casefold()}": {
                    "status": "RECONCILED",
                    "action_status": status,
                    "reconciliation_status": "COMPLETE",
                    "phase": "AWS-30",
                    "route": ["RELEASE_REVIEW", "RELEASE-10"],
                    "issues": [],
                }
                for status in ("SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN")
            },
            "reconciliation_blocked": {
                "status": "BLOCKED",
                "action_status": "SUCCEEDED",
                "reconciliation_status": "BLOCKED",
                "phase": "AWS-30",
                "route": ["RELEASE_REVIEW", "RELEASE-10"],
                "issues": [],
            },
            "reconciliation_stale": {
                "status": "RECONCILIATION_REQUIRED",
                "action_status": "SUCCEEDED",
                "reconciliation_status": "STALE",
                "phase": "AWS-30",
                "route": ["AWS_DEPLOYMENT_RECONCILIATION", "AWS-30"],
                "issues": [],
            },
        }
        observed = parity.build_deployment_qualification_cases()
        self.assertEqual(observed, expected)
        self.assertEqual(observed, self.qualification_oracle["deployment_cases"])
        self.assertEqual(
            {name: parity.canonical_digest(case) for name, case in observed.items()},
            self.qualification_oracle["deployment_case_digests"],
        )

    def test_qualification_aws_states_are_bound_to_split_regressions(self) -> None:
        expected = {
            name: list(selectors)
            for name, selectors in parity.QUALIFICATION_AWS_SCENARIO_COVERAGE.items()
        }
        self.assertEqual(self.qualification_oracle["aws_scenario_coverage"], expected)
        discovered = discovered_test_selectors()
        for scenario, selectors in expected.items():
            self.assertTrue(selectors, scenario)
            for selector in selectors:
                with self.subTest(scenario=scenario, selector=selector):
                    self.assertIn(selector, discovered)

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
        for path in (parity.ORACLE_PATH, parity.QUALIFICATION_ORACLE_PATH):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
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

        for oracle in (self.oracle, self.qualification_oracle):
            for value in strings(oracle):
                self.assertIsNone(ACCOUNT_ID.fullmatch(value), value)
                self.assertNotIn("arn:aws", value.casefold())


if __name__ == "__main__":
    unittest.main()
