from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import bootstrap_doctor as doctor
from scripts.fastlane_engine.define.requirements_v16 import (
    APPLICABILITY_HEADERS,
    APPLICABILITY_HEADING,
    INPUT_HEADERS,
    INPUT_HEADING,
    RECOVERY_HEADERS,
    RECOVERY_HEADING,
    SCENARIO_HEADERS,
    SCENARIO_HEADING,
)
from tests.test_bootstrap_doctor import approve_gate_a, replace_contract_table

ROOT = Path(__file__).resolve().parents[1]


def derive(text: str, approved: bool = False):
    return doctor.derive_requirements_contract(
        text,
        "low",
        required=True,
        grandfather_current_gate_a=approved,
    )


class Requirements16Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = approve_gate_a(
            (ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )

    def test_gate_a_fixture_keeps_its_recreation_targets_consistent(self):
        self.assertIn(
            "| Recovery target | `RTO: 60 minutes; RPO: 0 minutes` |", self.source
        )
        self.assertNotIn("RPO: 15 minutes", self.source)
        self.assertIn("RTO 60 minutes and RPO 0 minutes", self.source)
        self.assertIn("| RECREATE | 60 | 0 |", self.source)
        self.assertNotIn("| Durable data store | RECREATE:", self.source)

    def test_typed_recovery_measure_is_an_observable_bound(self):
        for value in (
            "RTO 60 minutes and RPO 0 minutes",
            "RTO 1.5 minutes and RPO 0.1 minutes",
        ):
            self.assertTrue(doctor.measurable_acceptance_is_bound(value))
        for value in (
            "RTO 0 minutes and RPO 0 minutes",
            "RTO NaN minutes and RPO 0 minutes",
            "RTO 60 minutes and RPO -1 minutes",
            "RTO 60 minutes and RPO 0 minutes or later",
        ):
            self.assertFalse(doctor.measurable_acceptance_is_bound(value))
        contract, errors = derive(self.source)
        self.assertEqual(errors, [])
        self.assertEqual(
            doctor.quality_attribute_scenario_issues(
                self.source, set(contract.requirement_ids)
            ),
            [],
        )

    def test_complete_contract_binds_recovery_and_input_details(self):
        contract, issues = derive(self.source)
        self.assertEqual(issues, [])
        self.assertEqual((contract.status, contract.schema_version), ("READY", "1.6"))
        detail = contract.to_dict()["requirements_v16"]
        self.assertEqual(detail["recoveries"][0]["Recovery mode"], "RECREATE")
        self.assertEqual(detail["inputs"][0]["Subject"], "Request outcome selector")

    def test_approved_legacy_digest_is_unchanged_and_changes_require_migration(self):
        fixture = json.loads(
            (ROOT / "tests/fixtures/local_alpha_project_v1.json").read_text(
                encoding="utf-8"
            )
        )
        contract, issues = derive(fixture["requirements_prd"], approved=True)
        self.assertEqual(issues, [])
        self.assertEqual(contract.schema_version, "1.5")
        self.assertEqual(contract.canonical_sha256, fixture["requirements_sha256"])
        self.assertNotIn("requirements_v16", contract.to_dict())
        for candidate, approved in (
            (fixture["requirements_prd"], False),
            (
                fixture["requirements_prd"].replace(
                    "at least 80 percent", "at least 81 percent"
                ),
                True,
            ),
            (fixture["requirements_prd"] + "\n" + INPUT_HEADING + "\n", True),
        ):
            with self.subTest(approved=approved, tail=candidate[-60:]):
                rejected, errors = derive(candidate, approved)
                self.assertEqual(rejected.status, "MIGRATION_REQUIRED")
                self.assertIn(
                    "PROJECT_CONTRACT_MIGRATION_REQUIRED", {code for code, _ in errors}
                )

    def test_missing_conflicting_and_duplicate_detail_records_block(self):
        source = self.source
        cases = (
            source.replace(RECOVERY_HEADING, "### Missing recovery record"),
            source.replace("| RECREATE | 60 | 0 |", "| RESTORE | 60 | 0 |"),
            source.replace(
                "RTO 60 minutes and RPO 0 minutes |",
                "RTO 60 minutes and RPO 0 minutes; RTO 600 minutes |",
            ),
            source.replace(
                "| QAS-001 | RECOVERY | DATASET-001 |", "| QAS-001 | OTHER | NONE |"
            ),
            source.replace("| FR-002 | INPUT-001 |", "| FR-002 | NONE |"),
            source.replace(
                '"unknown" | Reject the request', '"current" | Reject the request'
            ),
            source.replace('["current", "previous"]', "TODO, previous"),
            source.replace(
                INPUT_HEADING, INPUT_HEADING + "\n\n| Extra |\n|---|\n| Ambiguous |\n"
            ),
        )
        for candidate in cases:
            with self.subTest(candidate=candidate[-100:]):
                contract, issues = derive(candidate)
                self.assertEqual(contract.status, "BLOCKED")
                self.assertIn(
                    "REQUIREMENT_DETAIL_INVALID", {code for code, _ in issues}
                )

    def test_all_quality_scenario_fields_change_current_digest(self):
        baseline, issues = derive(self.source)
        self.assertEqual(issues, [])
        for old, new in (
            ("Primary data store becomes unavailable", "Primary data store is deleted"),
            (
                "Development recovery rehearsal",
                "Development isolated recovery rehearsal",
            ),
            ("Versioned synthetic fixture", "Reviewed versioned synthetic fixture"),
            ("versioned local fixture", "reviewed versioned local fixture"),
        ):
            self.assertIn(old, self.source)
            changed, errors = derive(self.source.replace(old, new))
            self.assertEqual(errors, [])
            self.assertNotEqual(changed.canonical_sha256, baseline.canonical_sha256)

    def test_scalar_boundaries_accept_empty_and_negative_examples(self):
        cases = (
            ("TEXT_LENGTH", "1", "20", "NOT_APPLICABLE", '"valid"', '""'),
            ("NUMBER_RANGE", "-20", "20", "NOT_APPLICABLE", "-3", "21"),
            (
                "ENUM",
                "NOT_APPLICABLE",
                "NOT_APPLICABLE",
                '["", "active"]',
                '""',
                '"unknown"',
            ),
        )
        for kind, minimum, maximum, allowed, valid, invalid in cases:
            candidate = replace_contract_table(
                self.source,
                INPUT_HEADING,
                INPUT_HEADERS,
                [
                    (
                        "INPUT-001",
                        "FR-002",
                        "Request selector",
                        kind,
                        minimum,
                        maximum,
                        allowed,
                        valid,
                        invalid,
                        "Reject without changing approved state",
                    )
                ],
            )
            contract, issues = derive(candidate)
            self.assertEqual(issues, [], kind)
            self.assertEqual(contract.status, "READY")

    def test_none_recovery_cannot_leave_a_linked_recovery_promise(self):
        candidate = replace_contract_table(
            self.source,
            RECOVERY_HEADING,
            RECOVERY_HEADERS,
            [
                (
                    "DATASET-001",
                    "DATA-004, REL-004",
                    "NONE",
                    "NONE",
                    "NOT_APPLICABLE",
                    "NOT_APPLICABLE",
                    "Synthetic data can be discarded",
                )
            ],
        )
        candidate = candidate.replace(
            "RECREATE: Regenerate synthetic records from the versioned local fixture",
            "NONE: Synthetic data can be discarded",
            1,
        )
        contract, errors = derive(candidate)
        self.assertEqual(contract.status, "BLOCKED")
        self.assertTrue(
            any(
                "classification" in error or "typed recovery" in error
                for _, error in errors
            )
        )

    def test_input_coverage_requires_every_requirement_and_exact_backreferences(self):
        for heading, headers in (
            (APPLICABILITY_HEADING, APPLICABILITY_HEADERS),
            (SCENARIO_HEADING, SCENARIO_HEADERS),
        ):
            candidate = replace_contract_table(self.source, heading, headers, [])
            contract, errors = derive(candidate)
            self.assertEqual(contract.status, "BLOCKED")
            self.assertTrue(any("enumerate every" in error for _, error in errors))


if __name__ == "__main__":
    unittest.main()
