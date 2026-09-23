from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import bootstrap_doctor as doctor
from scripts.fastlane_engine.design.contract_v9 import (
    VALIDATION_CHECK_HEADERS,
    VALIDATION_CHECK_HEADING,
)
from scripts.fastlane_engine.deliver.models import ApprovedDeliveryContract
from scripts.fastlane_engine.deliver.tasks import (
    inspect_task_blocks,
    validate_task_check_bindings,
)
from scripts.fastlane_engine.deliver.evidence import validate_done_evidence
from tests.test_bootstrap_doctor import (
    approve_gate_a,
    complete_design_contract,
    ready_task,
    replace_contract_table,
    set_table_value,
    task_completion_evidence_section,
    refresh_control_hashes,
)
from tests import test_bootstrap_doctor as doctor_fixtures

ROOT = Path(__file__).resolve().parents[1]


class Design9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = complete_design_contract(
            approve_gate_a((ROOT / "docs/project/PRD.md").read_text(encoding="utf-8"))
        )
        cls.contract, cls.issues = doctor.derive_design_contract(
            cls.source, "DES-0001", required=True
        )

    def test_complete_design_binds_each_obligation_and_its_stage(self):
        self.assertEqual(self.issues, [])
        project = self.contract.project_contract
        self.assertEqual(project.schema_version, 9)
        rows = {row[1]: row for row in project.validation_checks}
        self.assertEqual(
            rows["AC-FR-001"][6],
            "A rendered-output test confirms the approved outcome is displayed.",
        )
        self.assertEqual(
            rows["INPUT-001"][6],
            '["INPUT-001","FR-002","Request outcome selector","ENUM","NOT_APPLICABLE","NOT_APPLICABLE","[\\"current\\", \\"previous\\"]","\\"current\\"","\\"unknown\\"","Reject the request without changing approved state"]',
        )
        self.assertEqual(
            rows["IAC-L-00101"][2:4],
            (
                "LOCAL_RELEASE",
                "sam validate --lint --template-file infrastructure/template.yaml",
            ),
        )
        self.assertEqual(rows["IAC-A-00101"][2], "AWS_READ")

    def test_generic_outcome_missing_check_and_wrong_iac_command_block(self):
        table = doctor.contract_table_after_heading(
            self.source, VALIDATION_CHECK_HEADING, VALIDATION_CHECK_HEADERS
        )
        assert table is not None
        cases = [table.rows[1:]]
        for obligation, column, value in (
            ("INPUT-001", 6, "The tests pass"),
            ("QAS-001", 6, "Restore data"),
            ("API-001", 1, "API-001, INPUT-001"),
            ("IAC-L-00101", 3, "python -m unittest"),
            ("IAC-A-00101", 2, "LOCAL_BUILD"),
        ):
            rows = [list(row) for row in table.rows]
            next(row for row in rows if row[1] == obligation)[column] = value
            cases.append(rows)
        for rows in cases:
            candidate = replace_contract_table(
                self.source, VALIDATION_CHECK_HEADING, VALIDATION_CHECK_HEADERS, rows
            )
            contract, issues = doctor.derive_design_contract(
                candidate, "DES-0001", required=True
            )
            self.assertEqual(contract.status, "BLOCKED")
            self.assertTrue(issues)

    def test_nonexistent_or_wrong_stage_evidence_destination_blocks_design(self):
        table = doctor.contract_table_after_heading(
            self.source, VALIDATION_CHECK_HEADING, VALIDATION_CHECK_HEADERS
        )
        for destination in (
            "docs/project/VERIFY.md#section-does-not-exist",
            "docs/project/VERIFY.md#iac-validation-evidence",
        ):
            with self.subTest(destination=destination):
                rows = [list(row) for row in table.rows]
                next(row for row in rows if row[1] == "AC-FR-001")[5] = destination
                candidate = replace_contract_table(
                    self.source,
                    VALIDATION_CHECK_HEADING,
                    VALIDATION_CHECK_HEADERS,
                    rows,
                )
                contract, issues = doctor.derive_design_contract(
                    candidate, "DES-0001", required=True
                )
                self.assertEqual(contract.status, "BLOCKED")
                self.assertTrue(
                    any("evidence destination" in issue for issue in issues)
                )

    def test_linear_diagrams_preserve_semantics_and_reject_active_configuration(self):
        from scripts.fastlane_engine.design.diagrams import LINEAR_DIAGRAM_CONFIG

        plain = self.source.replace(LINEAR_DIAGRAM_CONFIG + "\n", "")
        styled = plain.replace(
            "```mermaid\nflowchart",
            "```mermaid\n" + LINEAR_DIAGRAM_CONFIG + "\nflowchart",
        )
        baseline, baseline_issues = doctor.derive_design_contract(
            plain, "DES-0001", required=True
        )
        current, issues = doctor.derive_design_contract(
            styled, "DES-0001", required=True
        )
        self.assertEqual(baseline_issues, [])
        self.assertEqual(issues, [])
        self.assertEqual(current.canonical_sha256, baseline.canonical_sha256)
        self.assertEqual(
            current.diagram_contract.canonical_sha256,
            baseline.diagram_contract.canonical_sha256,
        )
        self.assertNotEqual(
            current.diagram_contract.records[0].rendered_sha256,
            baseline.diagram_contract.records[0].rendered_sha256,
        )
        for directive in (
            '%%{init: {"securityLevel": "loose"}}%%',
            LINEAR_DIAGRAM_CONFIG + "\n" + LINEAR_DIAGRAM_CONFIG,
            '%%{init: {"flowchart": {"htmlLabels": true}}}%%',
        ):
            with self.subTest(directive=directive):
                _, errors = doctor.derive_design_contract(
                    styled.replace(LINEAR_DIAGRAM_CONFIG, directive, 1),
                    "DES-0001",
                    required=True,
                )
                self.assertTrue(errors)

    def test_engine_blocks_missing_duplicate_and_fenced_only_evidence_headings(self):
        fixture = doctor_fixtures.BootstrapDoctorTests()
        with tempfile.TemporaryDirectory() as directory:
            project = fixture.copy_project(Path(directory))
            fixture.approve_project(project)
            fixture.set_non_material_req_evidence(project)
            refresh_control_hashes(project)
            baseline = doctor.inspect_project(project)
            self.assertTrue(baseline["ok"], baseline["diagnostics"])
            path = project / "docs/project/VERIFY.md"
            original = path.read_text(encoding="utf-8")
            heading = "## Task completion evidence"
            for replacement in (
                "## Lost task evidence",
                heading + "\n\n" + heading,
                "```text\n" + heading + "\n```",
            ):
                with self.subTest(replacement=replacement):
                    path.write_text(
                        original.replace(heading, replacement), encoding="utf-8"
                    )
                    report = doctor.inspect_project(project)
                    self.assertFalse(report["ok"])
                    self.assertEqual(report["design_contract"]["status"], "BLOCKED")
                    self.assertTrue(
                        any(
                            "requires exactly one 'Task completion evidence'"
                            in item["message"]
                            for item in report["diagnostics"]
                        )
                    )
                    self.assertFalse(report["write_authority"]["valid"])

    def test_current_recovery_fixture_agrees_and_durable_restore_remains_valid(self):
        self.assertIn("RTO: 60 minutes; RPO: 0 minutes", self.source)
        self.assertIn("| Versioned synthetic fixture | RECREATE:", self.source)
        self.assertNotIn("| Durable data store | RECREATE:", self.source)
        self.assertEqual(self.issues, [])
        from tests.alpha_project_fixture import complete_alpha_design

        source = self.source.replace(
            "| Versioned synthetic fixture | RECREATE: Regenerate synthetic records from the versioned local fixture |",
            "| Durable data store | RESTORE: Restore the latest approved backup |",
        )
        source = source.replace("| RECREATE | 60 | 0 |", "| RESTORE | 60 | 0 |")
        source = source.replace(
            "Synthetic records are regenerated from versioned fixtures; no backup is promised",
            "Restore the durable data store from the approved backup",
        )
        source = source.replace(
            "RECREATE: Regenerate synthetic records from the versioned local fixture",
            "RESTORE: Restore the latest approved backup",
        )
        contract, issues = doctor.derive_design_contract(
            complete_alpha_design(source), "DES-0001", required=True
        )
        self.assertEqual(contract.status, "READY", issues)

    def test_exact_approved_design8_preserves_digest_and_partial_upgrade_fails(self):
        frozen = json.loads(
            (ROOT / "tests/fixtures/local_alpha_project_v1.json").read_text(
                encoding="utf-8"
            )
        )
        text = set_table_value(
            frozen["design_prd"],
            "## 28. Construction envelope",
            "## 29. Gate B owner authorization record",
            "Design contract SHA-256",
            frozen["design_sha256"],
        )
        contract, issues = doctor.derive_design_contract(
            text, "DES-0001", required=True, grandfather_approved_v1=True
        )
        self.assertEqual(issues, [])
        self.assertEqual(contract.canonical_sha256, frozen["design_sha256"])
        self.assertEqual(contract.project_contract.schema_version, 8)
        for suffix in (
            "\n### Validation check bindings\n",
            "\n  | Check ID | Broken |\n",
        ):
            changed, errors = doctor.derive_design_contract(
                text + suffix, "DES-0001", required=True, grandfather_approved_v1=True
            )
            self.assertEqual(changed.status, "BLOCKED")
            self.assertTrue(errors)

    def test_malformed_input_and_interface_basis_block_without_exception(self):
        for before, after in (
            ("| INPUT-001 | FR-002 |", "| INPUT-001 | TODO |"),
            ("| API-001 | API | FR-001, FR-002 |", "| API-001 | API | TODO |"),
        ):
            self.assertIn(before, self.source)
            contract, errors = doctor.derive_design_contract(
                self.source.replace(before, after), "DES-0001", required=True
            )
            self.assertEqual(contract.status, "BLOCKED")
            self.assertTrue(errors)

    def test_interface_requires_input_binding_even_without_comma_spaces(self):
        candidate = self.source.replace("FR-001, FR-002", "FR-001,FR-002")
        candidate = candidate.replace(
            "| INPUT-001 | Return the approved outcome",
            "| NONE: No external input | Return the approved outcome",
        )
        contract, errors = doctor.derive_design_contract(
            candidate, "DES-0001", required=True
        )
        self.assertEqual(contract.status, "BLOCKED")
        self.assertTrue(any("Input validation" in error for error in errors))

    def test_task_requires_exact_acceptance_check_and_matching_passing_command(self):
        project = self.contract.project_contract
        check = next(row for row in project.validation_checks if row[1] == "AC-FR-001")
        delivery = ApprovedDeliveryContract(
            False,
            validation_checks=project.validation_checks,
            acceptance_criteria=project.acceptance_criteria,
        )
        task_text = ready_task(requirements="FR-001")
        task = inspect_task_blocks(task_text)[0]
        self.assertTrue(validate_task_check_bindings(task, delivery))
        line = f"- [ ] AC-FR-001: {check[6]} [CHECK: {check[0]}]"
        table = "\n".join(
            [
                "| " + " | ".join(VALIDATION_CHECK_HEADERS) + " |",
                "|" + "---|" * 7,
                "| " + " | ".join(check) + " |",
            ]
        )
        task_text = task_text.replace(
            "#### Validation", line + "\n\n#### Validation\n\n" + table
        )
        task = inspect_task_blocks(task_text)[0]
        self.assertEqual(validate_task_check_bindings(task, delivery), [])
        task.metadata["Evidence"] = "EV-0001"
        evidence = task_completion_evidence_section(
            (
                "EV-0001",
                "python -m unittest",
                "2026-07-17T12:00:00-07:00",
                "commit: " + "a" * 40,
                "docs/project/VERIFY.md#ev-0001",
                "LOCAL_PASS",
            )
        )
        from scripts.fastlane_engine.deliver.evidence import (
            TASK_CHECK_HEADERS,
            validate_task_completion_evidence,
        )
        import hashlib

        fingerprint = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    ["FASTLANE_CHECK_V1", *check],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        )
        task.metadata.update(
            {"Attempts used": "1", "Last updated": "2026-07-17T12:03:00-07:00"}
        )
        task.block += "\n- Check attempt 1: RUN=RUN-0001; STARTED=2026-07-17T11:00:00-07:00; ENDED=2026-07-17T12:03:00-07:00\n"
        basis = " / ".join(
            task.metadata[key].strip("`")
            for key in ("Requirements", "Design", "Authorization")
        )
        row = (
            check[0],
            "TASK-001",
            fingerprint,
            basis,
            "RUN-0001",
            "1",
            "EV-0001",
            "2",
        )
        table = (
            "\n\n### Exact task check results\n\n| "
            + " | ".join(TASK_CHECK_HEADERS)
            + " |\n|"
            + "---|" * len(TASK_CHECK_HEADERS)
            + "\n| "
            + " | ".join(row)
            + " |\n"
        )
        evidence += table
        for validator in (validate_done_evidence, validate_task_completion_evidence):
            validator(evidence, task)
            for before, after in (
                ("python -m unittest", "python unrelated.py"),
                (fingerprint, "sha256:" + "b" * 64),
                ("| 2 |", "| 121 |"),
                ("| RUN-0001 |", "| RUN-0002 |"),
                ("12:00:00-07:00", "10:00:00-07:00"),
            ):
                with (
                    self.subTest(validator=validator.__name__, boundary=after),
                    self.assertRaises(ValueError),
                ):
                    validator(evidence.replace(before, after), task)
            failed_ev = (
                "| EV-0002 | TASK-001 | python -m unittest | failed check | alice | 2026-07-17T12:02:00-07:00 | commit: "
                + "a" * 40
                + " | docs/project/VERIFY.md#ev-0002 | FAILED |\n"
            )
            failed_result = "| " + " | ".join((*row[:6], "EV-0002", "2")) + " |\n"
            later_failure = (
                evidence.replace(
                    "\n\n### Exact task check results",
                    "\n" + failed_ev + "\n### Exact task check results",
                )
                + failed_result
            )
            with self.assertRaisesRegex(ValueError, "latest current result"):
                validator(later_failure, task)
            with self.assertRaisesRegex(ValueError, "unindexed current attempt"):
                validator(later_failure.removesuffix(failed_result), task)
            with self.assertRaisesRegex(ValueError, "execution began before"):
                validator(evidence.replace("12:00:00-07:00", "11:00:01-07:00"), task)
            with self.assertRaisesRegex(ValueError, "preserved completion"):
                original = task.block
                task.block = task.block.replace("; ENDED=2026-07-17T12:03:00-07:00", "")
                try:
                    validator(evidence, task)
                finally:
                    task.block = original

    def test_release_checks_bind_current_artifact_command_timing_and_latest_result(
        self,
    ):
        from datetime import datetime, timezone
        from scripts.fastlane_engine.deliver.evidence import (
            RELEASE_CHECK_HEADERS,
            release_check_evidence_issues,
        )

        project = self.contract.project_contract
        check = next(
            row for row in project.validation_checks if row[2] == "LOCAL_RELEASE"
        )
        digest = self.contract.canonical_sha256
        artifact = "commit: " + "a" * 40
        anchor = task_completion_evidence_section(
            (
                "EV-0001",
                "python -m unittest",
                "2026-07-17T12:00:00-07:00",
                artifact,
                "docs/project/VERIFY.md#ev-0001",
                "LOCAL_PASS",
            )
        )
        row = (
            check[0],
            digest,
            "EV-0001",
            check[3],
            "2.5",
            artifact,
            "2026-07-17T12:01:00-07:00",
            "docs/project/VERIFY.md#iac-validation-evidence",
            "LOCAL_PASS",
            "REQ-0001 / DES-0001 / AUTH-0001",
        )
        prefix = (
            anchor
            + "\n\n## IaC validation evidence\n\n### Exact local check results\n\n| "
            + " | ".join(RELEASE_CHECK_HEADERS)
            + " |\n|"
            + "---|" * len(RELEASE_CHECK_HEADERS)
            + "\n"
        )

        def render(values):
            return "| " + " | ".join(values) + " |\n"

        now = datetime(2026, 7, 18, tzinfo=timezone.utc)

        def validate(text):
            return release_check_evidence_issues(
                text, project.validation_checks, digest, row[9], artifact, now
            )

        self.assertEqual(validate(prefix + render(row)), [])
        for index, value in (
            (1, "sha256:" + "b" * 64),
            (2, "EV-0002"),
            (3, "python unrelated.py"),
            (4, "121"),
            (5, "commit: " + "b" * 40),
            (6, "2027-07-17T12:01:00-07:00"),
            (8, "FAILED"),
            (9, "REQ-0001 / DES-0001 / AUTH-0002"),
            (9, "NONE"),
        ):
            changed = list(row)
            changed[index] = value
            self.assertTrue(validate(prefix + render(changed)), (index, value))
        failed = list(row)
        failed[4], failed[6], failed[8] = "121", "2026-07-17T12:00:30-07:00", "FAILED"
        self.assertEqual(validate(prefix + render(failed) + render(row)), [])
        failed[6] = "2026-07-17T12:02:00-07:00"
        self.assertTrue(validate(prefix + render(row) + render(failed)))
        second_table = (
            "\n| "
            + " | ".join(RELEASE_CHECK_HEADERS)
            + " |\n|"
            + "---|" * len(RELEASE_CHECK_HEADERS)
            + "\n"
            + render(failed)
        )
        self.assertTrue(validate(prefix + render(row) + second_table))
        self.assertTrue(validate((prefix + render(row)).replace(artifact, "NONE")))
        contradictory = list(failed)
        contradictory[5] = "commit: " + "c" * 40
        self.assertTrue(validate(prefix + render(row) + render(contradictory)))
        ambiguous = list(row)
        ambiguous[2] = "EV-0002"
        self.assertTrue(validate(prefix + render(row) + render(ambiguous)))
        self.assertTrue(validate(prefix))
        self.assertTrue(validate((prefix + render(row)).replace(row[9], "")))
        self.assertTrue(
            release_check_evidence_issues(
                prefix + render(row),
                project.validation_checks,
                digest,
                "NONE",
                artifact,
                now,
            )
        )

    def test_current_design_claim_completion_and_evidence_updates_are_atomic(self):
        from datetime import datetime, timezone
        import hashlib
        import tempfile
        from unittest import mock
        from tests.test_bootstrap_doctor import (
            MODERN_TASK_REQUIREMENT_TRACE,
            property_execution_projection,
            property_test_evidence_section,
        )
        from tests.test_task_waves import (
            document,
            harness_evidence_document,
            harness_evidence_row,
            write_gate_b_bound_project,
            task_waves,
        )
        from scripts.fastlane_engine import api
        from scripts.fastlane_engine.deliver.evidence import (
            TASK_CHECK_HEADERS,
            task_check_projection,
        )

        harness = "\n".join(
            (
                "| Harness ID | Layer | Selected check or tool | Trigger | Basis IDs | Exact command or API | Evidence destination | Required or conditional status |",
                "|---|---|---|---|---|---|---|---|",
                "| HARNESS-004 | End-to-end | unittest journey validation | NEW_BUILD first outcome | DES-0001, FR-001, JOURNEY-001, WAVE-001 | python -m unittest tests.test_product_journeys | docs/project/VERIFY.md#harness-execution-evidence | REQUIRED |",
            )
        )
        task_text = ready_task(
            requirements=MODERN_TASK_REQUIREMENT_TRACE
            + "; PROP-001; JOURNEY-001; WAVE-001",
            design="DES-0001; TECH: TECH-0001, TECH-0007",
            command="python -m unittest tests.test_properties\npython -m unittest tests.test_product_journeys",
            property_projection=property_execution_projection() + "\n\n" + harness,
        )
        claimed = datetime(2026, 7, 17, 12, 0, 0, 100000, tzinfo=timezone.utc)
        observed_at = "2026-07-17T12:00:10.100000+00:00"
        completed = datetime(2026, 7, 17, 12, 0, 10, 200000, tzinfo=timezone.utc)
        artifact = "commit: " + "a" * 40
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(task_waves, "datetime", wraps=datetime) as clock,
        ):
            path, state_path = write_gate_b_bound_project(
                Path(directory), document([task_text])
            )
            clock.now.return_value = claimed
            task_waves.mutate_run_snapshot(
                path, operation="start", run_id="RUN-0001", coordinator="lead"
            )
            task_waves.claim_task_file(
                path,
                "TASK-001",
                owner="lead",
                coordinator="lead",
                run_id="RUN-0001",
                checkpoint="CP-0000",
            )
            claim = "- Check attempt 1: RUN=RUN-0001; STARTED=" + claimed.isoformat()
            current = path.read_text(encoding="utf-8")
            self.assertIn(claim, current)
            current = current.replace("- [ ]", "- [x]").replace(
                "Not started.", "Coordinator observed all synthetic validation results."
            )
            # An earlier example must not absorb the structural completion edit.
            current = current.replace(
                "#### Outcome\n", "#### Outcome\n\n```text\n" + claim + "\n```\n"
            )
            path.write_text(current, encoding="utf-8")
            task = task_waves.parse_tasks(current)[0]
            basis = " / ".join(
                task_waves.clean(task.metadata[key])
                for key in ("Requirements", "Design", "Authorization")
            )
            checks = task_check_projection(task.block)
            self.assertGreater(len(checks), 0)
            index_rows = []
            for check in checks:
                fingerprint = (
                    "sha256:"
                    + hashlib.sha256(
                        json.dumps(
                            ["FASTLANE_CHECK_V1", *check],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                )
                index_rows.append(
                    "| "
                    + " | ".join(
                        (
                            check[0],
                            "TASK-001",
                            fingerprint,
                            basis,
                            "RUN-0001",
                            "1",
                            "EV-0001",
                            "2",
                        )
                    )
                    + " |"
                )
            indexed = (
                "\n\n### Exact task check results\n\n| "
                + " | ".join(TASK_CHECK_HEADERS)
                + " |\n|"
                + "---|" * 8
                + "\n"
                + "\n".join(index_rows)
                + "\n"
            )
            evidence = (
                task_completion_evidence_section(
                    *(
                        (
                            evidence_id,
                            command,
                            observed_at,
                            artifact,
                            "docs/project/VERIFY.md#" + evidence_id.lower(),
                            "LOCAL_PASS",
                        )
                        for evidence_id, command in (
                            ("EV-0001", "python -m unittest"),
                            ("EV-0002", "python -m unittest tests.test_properties"),
                            (
                                "EV-0003",
                                "python -m unittest tests.test_product_journeys",
                            ),
                        )
                    )
                )
                + indexed
            )
            evidence += "\n" + property_test_evidence_section(
                evidence_id="EV-0002",
                observed_at=observed_at,
                material=artifact,
                source="docs/project/VERIFY.md#ev-0002",
            )
            evidence += "\n" + harness_evidence_document(
                harness_evidence_row(
                    evidence_id="EV-0003",
                    status="LOCAL_PASS",
                    observed_at=observed_at,
                    observed_result="Synthetic journey passed",
                    harness_id="HARNESS-004",
                    layer="End-to-end",
                    command="python -m unittest tests.test_product_journeys",
                    artifact_environment=artifact,
                )
            )
            evidence = "\n".join(
                (
                    "## Active evidence scope",
                    "",
                    "| Field | Value |",
                    "|---|---|",
                    "| Requirements revision | REQ-0001 |",
                    "| Design revision | DES-0001 |",
                    "| Construction authorization | AUTH-0001 |",
                    "",
                    "## Verification matrix",
                    "",
                    "| Evidence ID | PRD / property IDs | Task IDs | Requirement or invariant | Automated evidence | AWS/manual evidence | Artifact/environment | Status |",
                    "|---|---|---|---|---|---|---|---|",
                    "",
                    evidence,
                )
            )
            verify = path.with_name("VERIFY.md")
            clock.now.return_value = completed

            def finish():
                return task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-0001, EV-0002, EV-0003",
                    run_id="RUN-0001",
                    checkpoint="CP-0001",
                )

            before_tasks, before_state = path.read_bytes(), state_path.read_bytes()
            late_failure = (
                "| EV-0004 | TASK-001 | python -m unittest | check failed | alice | 2026-07-17T12:00:10.150000+00:00 | "
                + artifact
                + " | docs/project/VERIFY.md#ev-0004 | FAILED |\n"
            )
            for bad_evidence, expected in (
                (
                    evidence.replace(
                        "\n\n### Exact task check results",
                        "\n" + late_failure + "\n### Exact task check results",
                    ),
                    "unindexed current attempt",
                ),
                (
                    evidence.replace(observed_at, "2026-07-17T12:00:01.100000+00:00"),
                    "execution began before",
                ),
                (
                    evidence.replace(observed_at, "2026-07-17T12:00:00.050000+00:00"),
                    "outside its preserved attempt",
                ),
            ):
                verify.write_text(bad_evidence, encoding="utf-8")
                with (
                    self.subTest(expected=expected),
                    self.assertRaisesRegex(ValueError, expected),
                ):
                    finish()
                self.assertEqual(path.read_bytes(), before_tasks)
                self.assertEqual(state_path.read_bytes(), before_state)
            verify.write_text(evidence, encoding="utf-8")
            self.assertTrue(finish())
            done_text = path.read_text(encoding="utf-8")
            done = task_waves.parse_tasks(done_text)[0]
            self.assertEqual(done.status, "DONE")
            self.assertIn(claim + "; ENDED=" + completed.isoformat(), done.block)
            self.assertIn("```text\n" + claim + "\n```", done.block)
            api.validate_task_done_completion_evidence(evidence, done)
            before_tasks, before_state = path.read_bytes(), state_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "not recorded in VERIFY"):
                task_waves.update_task_file(
                    path, "TASK-001", coordinator="lead", evidence="EV-0999"
                )
            self.assertEqual(path.read_bytes(), before_tasks)
            self.assertEqual(state_path.read_bytes(), before_state)
            clock.now.return_value = datetime(2026, 7, 18, tzinfo=timezone.utc)
            self.assertTrue(
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    issue="https://github.com/example/project/issues/17",
                )
            )
            revised = task_waves.parse_tasks(path.read_text(encoding="utf-8"))[0]
            self.assertIn("; ENDED=" + completed.isoformat(), revised.block)
            self.assertNotEqual(
                task_waves.clean(revised.metadata["Last updated"]),
                completed.isoformat(),
            )
            api.validate_task_done_completion_evidence(evidence, revised)


if __name__ == "__main__":
    unittest.main()
