from __future__ import annotations

import unittest
from pathlib import Path

from scripts import bootstrap_doctor as doctor
from scripts.fastlane_engine.define import requirements
from scripts.fastlane_engine.design.models import DesignContract
from scripts.fastlane_engine.owner_decisions import derive_owner_decision_brief
from tests.test_bootstrap_doctor import approve_gate_a, replace_contract_table


ROOT = Path(__file__).resolve().parents[1]
PRD = ROOT / "docs" / "project" / "PRD.md"
LEGACY_14 = ROOT / "tests" / "fixtures" / "legacy_schema6_approved_prd.md"


def ready_contract(text: str):
    intake, intake_issues = doctor.derive_intake_foundation_contract(
        text,
        "greenfield",
        grandfather_current_gate_a=False,
    )
    if intake_issues:
        raise AssertionError(intake_issues)
    return doctor.derive_requirements_contract(
        text,
        "low",
        intake,
        required=True,
        grandfather_current_gate_a=False,
    )


class Requirements15Tests(unittest.TestCase):
    def test_complete_contract_projects_typed_side_registries(self) -> None:
        contract, issues = ready_contract(
            approve_gate_a(PRD.read_text(encoding="utf-8"))
        )

        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "READY")
        self.assertEqual(contract.schema_version, "1.5")
        self.assertEqual(contract.completion_target, "LOCAL")
        self.assertEqual(
            [item.metric_id for item in contract.outcome_metrics], ["METRIC-001"]
        )
        self.assertEqual(
            [item.dataset_id for item in contract.datasets], ["DATASET-001"]
        )
        self.assertEqual(
            [item.obligation_id for item in contract.external_obligations],
            ["OBL-001"],
        )
        self.assertEqual(
            [item.risk_id for item in contract.cross_cutting_risks], ["RISK-001"]
        )
        self.assertFalse(
            set(contract.requirement_ids)
            & {"METRIC-001", "DATASET-001", "OBL-001", "RISK-001"}
        )
        projection = contract.to_dict()
        self.assertEqual(projection["completion_target"], "LOCAL")
        self.assertEqual(
            projection["outcome_metrics"][0]["accountable_role"], "Product owner"
        )
        self.assertEqual(projection["datasets"][0]["classification"], "INTERNAL")
        self.assertEqual(
            projection["external_obligations"][0]["applicability"],
            "NONE_IDENTIFIED",
        )
        self.assertEqual(projection["cross_cutting_risks"][0]["impact"], "MEDIUM")

    def test_completion_target_is_closed_and_digest_bound(self) -> None:
        source = approve_gate_a(PRD.read_text(encoding="utf-8"))
        digests: set[str | None] = set()
        for target in requirements.PROJECT_COMPLETION_TARGETS:
            candidate = source.replace(
                "| Project completion target | `LOCAL` |",
                f"| Project completion target | `{target}` |",
                1,
            )
            contract, issues = ready_contract(candidate)
            self.assertEqual(issues, [], target)
            self.assertEqual(contract.completion_target, target)
            digests.add(contract.canonical_sha256)
        self.assertEqual(len(digests), len(requirements.PROJECT_COMPLETION_TARGETS))

        invalid, issues = ready_contract(
            source.replace(
                "| Project completion target | `LOCAL` |",
                "| Project completion target | `PRODUCTION` |",
                1,
            )
        )
        self.assertEqual(invalid.status, "BLOCKED")
        self.assertIn(
            "PROJECT_COMPLETION_TARGET_INVALID",
            {code for code, _message in issues},
        )

    def test_registry_bytes_are_validated_and_digest_bound(self) -> None:
        source = approve_gate_a(PRD.read_text(encoding="utf-8"))
        baseline, baseline_issues = ready_contract(source)
        self.assertEqual(baseline_issues, [])

        mutations = (
            (
                "at least 80 percent",
                "at least 81 percent",
                "OUTCOME_METRIC_INVALID",
                False,
            ),
            ("DATASET-001", "DATASET-999", "DATASET_CONTRACT_INVALID", False),
            (
                "| OBL-001 | NONE IDENTIFIED | Owner review of intended users, data, and geography found no applicable external obligation | NONE_IDENTIFIED |",
                "| OBL-001 | NONE IDENTIFIED | Owner review of intended users, data, and geography found no applicable external obligation | UNKNOWN |",
                "EXTERNAL_OBLIGATION_INVALID",
                True,
            ),
            ("RISK-001", "RISK-999", "CROSS_CUTTING_RISK_INVALID", False),
        )
        for before, after, code, invalid in mutations:
            with self.subTest(before=before, after=after):
                candidate = source.replace(before, after, 1)
                contract, issues = ready_contract(candidate)
                if invalid:
                    self.assertEqual(contract.status, "BLOCKED")
                    self.assertIn(code, {item for item, _message in issues})
                else:
                    self.assertEqual(issues, [])
                    self.assertNotEqual(
                        contract.canonical_sha256,
                        baseline.canonical_sha256,
                    )

    def test_registry_shape_references_and_enums_fail_closed(self) -> None:
        source = approve_gate_a(PRD.read_text(encoding="utf-8"))
        cases: list[tuple[str, str]] = []
        metric = doctor.contract_table_after_heading(
            source,
            requirements.OUTCOME_METRIC_HEADING,
            requirements.OUTCOME_METRIC_HEADERS,
        )
        dataset = doctor.contract_table_after_heading(
            source,
            requirements.DATASET_HEADING,
            requirements.DATASET_HEADERS,
        )
        obligation = doctor.contract_table_after_heading(
            source,
            requirements.EXTERNAL_OBLIGATION_HEADING,
            requirements.EXTERNAL_OBLIGATION_HEADERS,
        )
        risk = doctor.contract_table_after_heading(
            source,
            requirements.CROSS_CUTTING_RISK_HEADING,
            requirements.CROSS_CUTTING_RISK_HEADERS,
        )
        assert metric and dataset and obligation and risk
        cases.append(
            (
                replace_contract_table(
                    source,
                    requirements.OUTCOME_METRIC_HEADING,
                    requirements.OUTCOME_METRIC_HEADERS,
                    [metric.rows[0], metric.rows[0]],
                ),
                "OUTCOME_METRIC_INVALID",
            )
        )
        cases.append(
            (
                replace_contract_table(
                    source,
                    requirements.DATASET_HEADING,
                    requirements.DATASET_HEADERS,
                    [dataset.rows[0][:-1] + ("DATA-999",)],
                ),
                "DATASET_CONTRACT_INVALID",
            )
        )
        cases.append(
            (
                replace_contract_table(
                    source,
                    requirements.EXTERNAL_OBLIGATION_HEADING,
                    requirements.EXTERNAL_OBLIGATION_HEADERS,
                    [obligation.rows[0][:3] + ("UNKNOWN",) + obligation.rows[0][4:]],
                ),
                "EXTERNAL_OBLIGATION_INVALID",
            )
        )
        cases.append(
            (
                replace_contract_table(
                    source,
                    requirements.CROSS_CUTTING_RISK_HEADING,
                    requirements.CROSS_CUTTING_RISK_HEADERS,
                    [risk.rows[0][:4] + ("CATASTROPHIC",) + risk.rows[0][5:]],
                ),
                "CROSS_CUTTING_RISK_INVALID",
            )
        )
        for candidate, code in cases:
            with self.subTest(code=code):
                contract, issues = ready_contract(candidate)
                self.assertEqual(contract.status, "BLOCKED")
                self.assertIn(code, {item for item, _message in issues})

    def test_no_data_and_no_obligation_rows_are_canonical_and_noncontradictory(
        self,
    ) -> None:
        source = approve_gate_a(PRD.read_text(encoding="utf-8"))
        no_data = (
            "DATASET-001",
            "NO PERSISTENT DATA",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
        )
        no_data_source = replace_contract_table(
            source,
            requirements.DATASET_HEADING,
            requirements.DATASET_HEADERS,
            [no_data],
        )
        contract, issues = ready_contract(no_data_source)
        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "READY")
        self.assertEqual(contract.datasets[0].classification, "NONE")
        self.assertEqual(contract.external_obligations[0].requirement_ids, ())

        contradictory_data = list(no_data)
        contradictory_data[1] = "Customer records"
        blocked, blocked_issues = ready_contract(
            replace_contract_table(
                source,
                requirements.DATASET_HEADING,
                requirements.DATASET_HEADERS,
                [tuple(contradictory_data)],
            )
        )
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertIn(
            "DATASET_CONTRACT_INVALID",
            {code for code, _message in blocked_issues},
        )

        obligation = doctor.contract_table_after_heading(
            source,
            requirements.EXTERNAL_OBLIGATION_HEADING,
            requirements.EXTERNAL_OBLIGATION_HEADERS,
        )
        assert obligation is not None
        contradictory_obligation = list(obligation.rows[0])
        contradictory_obligation[4:9] = [
            "Development users",
            "Retain records for seven years",
            "Product owner",
            "FR-001",
            "Retention audit",
        ]
        blocked, blocked_issues = ready_contract(
            replace_contract_table(
                source,
                requirements.EXTERNAL_OBLIGATION_HEADING,
                requirements.EXTERNAL_OBLIGATION_HEADERS,
                [tuple(contradictory_obligation)],
            )
        )
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertIn(
            "EXTERNAL_OBLIGATION_INVALID",
            {code for code, _message in blocked_issues},
        )

    def test_partially_upgraded_schema_14_cannot_use_compatibility(self) -> None:
        source = approve_gate_a(PRD.read_text(encoding="utf-8")).replace(
            "| Project contract schema | `1.5` |",
            "| Project contract schema | `1.4` |",
            1,
        )
        intake, intake_issues = doctor.derive_intake_foundation_contract(
            source,
            "greenfield",
            grandfather_current_gate_a=True,
        )
        self.assertEqual(intake_issues, [])
        contract, issues = doctor.derive_requirements_contract(
            source,
            "low",
            intake,
            required=True,
            grandfather_current_gate_a=True,
        )
        self.assertEqual(contract.status, "MIGRATION_REQUIRED")
        self.assertIn(
            "PROJECT_CONTRACT_MIGRATION_REQUIRED",
            {code for code, _message in issues},
        )

    def test_approved_schema_14_keeps_exact_digest_without_legacy_bridge(self) -> None:
        text = LEGACY_14.read_text(encoding="utf-8")
        intake, intake_issues = doctor.derive_intake_foundation_contract(
            text,
            "greenfield",
            grandfather_current_gate_a=True,
        )
        self.assertEqual(intake_issues, [])
        compatible, issues = doctor.derive_requirements_contract(
            text,
            "low",
            intake,
            required=True,
            grandfather_current_gate_a=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(compatible.status, "READY")
        self.assertEqual(compatible.schema_version, "1.4")
        self.assertEqual(
            compatible.canonical_sha256,
            "sha256:3e976ff7e632de5ea50e799c9215b40108513e848c805c3fedda044fef00903d",
        )
        self.assertTrue(compatible.approved_schema_14_compatibility)
        self.assertFalse(compatible.grandfathered_approved_gate_a)

        migration, migration_issues = doctor.derive_requirements_contract(
            text,
            "low",
            intake,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(migration.status, "MIGRATION_REQUIRED")
        self.assertIn(
            "PROJECT_CONTRACT_MIGRATION_REQUIRED",
            {code for code, _message in migration_issues},
        )

    def test_gate_a_brief_exposes_target_and_typed_owner_records(self) -> None:
        text = approve_gate_a(PRD.read_text(encoding="utf-8"))
        intake, intake_issues = doctor.derive_intake_foundation_contract(
            text,
            "greenfield",
            grandfather_current_gate_a=False,
        )
        requirements_contract, requirement_issues = doctor.derive_requirements_contract(
            text,
            "low",
            intake,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual([*intake_issues, *requirement_issues], [])
        brief, _inventory, issues = derive_owner_decision_brief(
            text,
            {
                "requirements_revision": "REQ-0001",
                "design_revision": "DES-0001",
                "construction_authorization": "AUTH-0001",
                "gate_a": "PENDING_OWNER_APPROVAL",
                "gate_b": "BLOCKED",
            },
            intake,
            requirements_contract,
            DesignContract(),
            {},
            has_errors=False,
            enabled=True,
        )
        self.assertEqual(issues, [])
        rendered = "\n".join(
            line for section in brief["executive_sections"] for line in section["items"]
        )
        for expected in (
            "Completion target: LOCAL",
            "METRIC-001",
            "DATASET-001",
            "OBL-001",
            "RISK-001",
        ):
            self.assertIn(expected, rendered)
        self.assertIn(
            "Gate A does not authorize technical design selection, construction, publication, deployment, or teardown.",
            {claim["text"] for claim in brief["claims"]},
        )


if __name__ == "__main__":
    unittest.main()
