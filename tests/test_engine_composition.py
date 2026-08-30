from __future__ import annotations

import ast
import builtins
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts import bootstrap_doctor as doctor
from scripts.fastlane_engine import api
from scripts.fastlane_engine.aws.models import AWS_DEPLOYMENT_EVIDENCE_HEADERS
from scripts.fastlane_engine.completion import (
    derive_project_release_claim,
    required_done_task_evidence,
)
from scripts.fastlane_engine.core.diagnostics import Diagnostic
from scripts.fastlane_engine.deliver import task_remediation_validation_evidence
from scripts.fastlane_engine.deliver.release import (
    derive_release_claim_projection,
    validate_release_claim_projection,
)
from scripts.fastlane_engine.deliver.models import TaskSummary
from scripts.fastlane_engine.evaluation import EngineEvaluation
from scripts.fastlane_engine.report import serialize_evaluation
from tests import test_bootstrap_doctor as doctor_fixtures


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "scripts" / "fastlane_engine" / "report.py"
COMPOSITION_PATH = ROOT / "scripts" / "fastlane_engine" / "composition.py"


def synthetic_schema2_report() -> dict[str, object]:
    """Independently authored serializer fixture with every public report field."""

    return {
        "schema_version": 2,
        "bootstrap_version": "1.2.24",
        "status": "READY",
        "classification": "ACTIVE_GREENFIELD",
        "ok": True,
        "lifecycle_state": "INTAKE_REQUIRED",
        "resume_safe": True,
        "next_prompt": "INTAKE-10",
        "interaction": {"owner_action_kind": "ANSWER_OPEN_DECISIONS"},
        "remediation": {"responsible_party": "OWNER"},
        "context_plan": {"status": "CURRENT", "requests": []},
        "project": {"name": "Synthetic"},
        "git_baseline": {"status": "CLEAN"},
        "aws_access": "NOT_USED",
        "aws_mode_boundary": {"mode": "NONE"},
        "gates": {"gate_a": "BLOCKED", "gate_b": "BLOCKED"},
        "evidence_state": "NOT_READY",
        "release_evidence_cutoff": "NONE",
        "aws_core_evidence": {"aws_execution_planning": "BLOCKED"},
        "authorizations": {"construction": "NONE", "aws": "NONE"},
        "write_authority": {"valid": False},
        "deployment_journal_closure_authority": {"valid": False},
        "teardown_journal_closure_authority": {"valid": False},
        "aws_lifecycle_intent": {"value": "NONE"},
        "aws_residual_disposition": {"status": "NOT_APPLICABLE"},
        "aws_lifecycle_intent_write_authority": {"valid": False},
        "external_authority": {"kind": "NONE", "validity": "NONE"},
        "hook_constraints": {"GitHub boundary": "NONE"},
        "aws_action_transition": {"status": "NOT_ACTIVE"},
        "aws_execution": {"active": False},
        "aws_deployment": {"status": "NOT_ACTIVE"},
        "aws_teardown": {"status": "NOT_ACTIVE"},
        "basis": {"requirements_revision": "REQ-0001"},
        "document_summaries": {"schema_version": 1, "documents": []},
        "owner_decision_brief": {"status": "NOT_READY"},
        "owner_decision_inventory": {"gate_a": [], "gate_b": []},
        "owner_answer_confirmation": {"status": "NOT_READY"},
        "intake_foundation": {"status": "INCOMPLETE"},
        "requirements_contract": {"status": "INCOMPLETE"},
        "coverage_plan": {"status": "INCOMPLETE"},
        "design_contract": {"status": "INCOMPLETE"},
        "adr_rationale": {"status": "NOT_APPLICABLE"},
        "tasks": {"total": 0, "ready_ids": []},
        "diagnostics": [
            {
                "diagnostic_id": "DGN-0001",
                "code": "SYNTHETIC",
                "severity": "WARNING",
                "message": "Synthetic fixture",
            }
        ],
    }


def synthetic_release_claim() -> dict[str, object]:
    artifact = "sha256:" + "a" * 64
    claim_codes = {
        target: f"PROJECT_TARGET_COMPLETE({target})"
        for target in ("LOCAL", "AWS_READ", "DEPLOYED", "RECOVERY")
    }
    claims: dict[str, object] = {}
    for target, evidence in (
        ("LOCAL", ["EV-1001"]),
        ("AWS_READ", ["EV-1001", "EV-1002"]),
        ("DEPLOYED", ["EV-1001", "EV-1002", "EV-1003"]),
        ("RECOVERY", ["EV-1001", "EV-1002", "EV-1003", "EV-1004"]),
    ):
        claims[target] = {
            "applicability": "APPLICABLE",
            "status": "CURRENT" if target != "RECOVERY" else "NOT_PROVEN",
            "evidence_ids": evidence if target != "RECOVERY" else [],
            "limitations": ["Current evidence proves only this named project target."],
            "allowed_claims": [claim_codes[target]] if target != "RECOVERY" else [],
            "prohibited_claims": (
                [] if target != "RECOVERY" else [claim_codes[target]]
            ),
        }
    return {
        "schema_version": 1,
        "basis": {
            "requirements_revision": "REQ-0001",
            "design_revision": "DES-0001",
            "construction_authorization": "AUTH-0001",
            "artifact_sha256": artifact,
            "account": "123456789012",
            "region": "us-west-2",
            "environment": "development",
            "lane": "AWS_SAM_CLOUDFORMATION_NONPROD",
            "evidence_cutoff": "EV-1003",
        },
        "claims": claims,
        "authority_effect": "NONE",
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
    }


def release_claim_inputs(
    completion_target: str = "RECOVERY",
) -> dict[str, object]:
    artifact = "sha256:" + "a" * 64
    return {
        "requirements_schema": "1.5",
        "completion_target": completion_target,
        "requirements_revision": "REQ-0001",
        "design_revision": "DES-0001",
        "construction_authorization": "AUTH-0001",
        "artifact_sha256": artifact,
        "environment": "development",
        "lane": "AWS_SAM_CLOUDFORMATION_NONPROD",
        "release_state": "RELEASE_VERIFIED",
        "evidence_cutoff": "EV-1003",
        "local_evidence_ids": ["EV-1001"],
        "preflight": {
            "status": "READY",
            "account_access": "READ_ONLY_OBSERVED",
            "account": "123456789012",
            "region": "us-west-2",
            "environment": "development",
            "evidence_ids": ["EV-1002"],
            "issues": [],
        },
        "deployment": {
            "status": "RECONCILED",
            "action_status": "SUCCEEDED",
            "reconciliation_status": "COMPLETE",
            "artifact_digest": artifact,
            "identity_and_boundary_match": "PASS",
            "basis_stale": False,
            "issues": [],
            "acceptance_evidence_ids": ["EV-1003"],
            "evidence_id": "EV-1003",
            "acknowledged": True,
            "acknowledged_evidence_id": "EV-1003",
            "release_evidence_cutoff": "EV-1003",
        },
        "recovery_evidence_ids": ["EV-1004"],
        "local_ready": True,
        "has_errors": False,
    }


def release_claim_verify_text(rollback_result: str | None = None) -> str:
    artifact = "sha256:" + "a" * 64
    sections = [
        "\n".join(
            (
                "## Active evidence scope",
                "",
                "| Field | Value |",
                "|---|---|",
                "| Requirements revision | REQ-0001 |",
                "| Design revision | DES-0001 |",
                "| Construction authorization | AUTH-0001 |",
                f"| Commit, tag, or image digest | {artifact} |",
                "| Release state | RELEASE_VERIFIED |",
                "| Environment | development |",
            )
        ),
        "\n".join(
            (
                "## Task completion evidence",
                "",
                "| Evidence ID | Task | Command or observation | Result | Actor | Observed at | Commit / worktree / artifact | Durable source | Status |",
                "|---|---|---|---|---|---|---|---|---|",
                f"| EV-1001 | TASK-001 | tests | PASS | owner | 2026-08-28T12:00:00Z | {artifact} | test log | LOCAL_PASS |",
            )
        ),
    ]
    if rollback_result is not None:
        values = {header: "NONE" for header in AWS_DEPLOYMENT_EVIDENCE_HEADERS}
        values.update(
            {
                "Evidence ID": "EV-1003",
                "Attempt ID": "AWS-DEPLOY-0001",
                "Phase": "AWS-30",
                "REQ / DES / AUTH": "REQ-0001 / DES-0001 / AUTH-0001",
                "Artifact digest": artifact,
                "Account / Region / environment": (
                    "123456789012 / us-west-2 / development"
                ),
                "Rollback result": rollback_result,
                "Acceptance evidence IDs": "EV-1003, EV-1004",
                "Identity and boundary match": "PASS",
                "Status": "COMPLETE",
            }
        )
        header = "| " + " | ".join(AWS_DEPLOYMENT_EVIDENCE_HEADERS) + " |"
        separator = "|" + "|".join("---" for _ in values) + "|"
        row = "| " + " | ".join(values[item] for item in values) + " |"
        sections.append(
            "\n".join(
                (
                    "## AWS deployment action and reconciliation evidence",
                    "",
                    header,
                    separator,
                    row,
                )
            )
        )
    return "\n\n".join(sections) + "\n"


class EngineCompositionTests(unittest.TestCase):
    def test_remediation_uses_only_the_active_tasks_exact_validation_binding(
        self,
    ) -> None:
        command = "python -m unittest tests.test_properties"
        tasks_text = doctor_fixtures.ready_task(
            command=command,
            property_projection=doctor_fixtures.property_execution_projection(),
        )
        active = TaskSummary(statuses={"TASK-001": "IN_PROGRESS"}, active=["TASK-001"])

        self.assertEqual(
            task_remediation_validation_evidence(tasks_text, active),
            (
                {
                    "validation_id": "PROP-001",
                    "command": command,
                    "evidence_destination": (
                        "docs/project/VERIFY.md#property-based-test-evidence"
                    ),
                },
            ),
        )
        self.assertEqual(
            task_remediation_validation_evidence(
                tasks_text,
                TaskSummary(statuses={"TASK-001": "READY"}, ready=["TASK-001"]),
            ),
            (),
        )

    def test_ledger_correction_preserves_the_active_task_validation_contract(
        self,
    ) -> None:
        command = "python -m unittest tests.test_product_journeys"
        harness = "\n".join(
            (
                "| Harness ID | Layer | Selected check or tool | Trigger | Basis IDs | Exact command or API | Evidence destination | Required or conditional status |",
                "|---|---|---|---|---|---|---|---|",
                "| HARNESS-004 | End-to-end | unittest journey validation | active task correction | DES-0001, FR-001 | "
                + command
                + " | docs/project/VERIFY.md#harness-execution-evidence | REQUIRED |",
            )
        )
        tasks_text = doctor_fixtures.ready_task(command=command).replace(
            "- Status: `READY`", "- Status: `IN_PROGRESS`", 1
        )
        tasks_text = tasks_text.replace(
            "#### Validation\n\n", "#### Validation\n\n" + harness + "\n\n", 1
        )
        tasks = TaskSummary(
            statuses={"TASK-001": "IN_PROGRESS"},
            active=["TASK-001"],
            write_sets={"TASK-001": ["app/main.py"]},
            attempts_used={"TASK-001": 0},
            attempt_budgets={"TASK-001": 3},
        )
        evidence = task_remediation_validation_evidence(tasks_text, tasks)
        expected_evidence = (
            {
                "validation_id": "HARNESS-004",
                "command": command,
                "evidence_destination": (
                    "docs/project/VERIFY.md#harness-execution-evidence"
                ),
            },
        )
        self.assertEqual(evidence, expected_evidence)

        context = doctor.Context(ROOT)
        context.error(
            "TASK_GRAPH_INVALID",
            "TASK-001 active task ledger differs from its current task contract",
            "docs/project/TASKS.md",
        )
        common = {
            "classification": "ACTIVE_GREENFIELD",
            "gate_a": "APPROVED_FOR_DESIGN",
            "gate_b": "APPROVED_FOR_CONSTRUCTION",
            "envelope": {
                "Allowed repository write set": "PATHS: app/**",
                "Excluded or owner-only write set": "NONE",
                "Protected dirty paths": "NONE",
            },
            "tasks": tasks,
            "requirements_revision": "REQ-0001",
            "design_revision": "DES-0001",
            "owner_stage_hint": "DELIVER",
        }
        remediation = doctor.derive_remediation(
            context, task_validation_evidence=evidence, **common
        )
        self.assertEqual(
            remediation["next_action"]["corrections"],
            [
                {
                    "diagnostic_id": "DGN-0001",
                    "cause": (
                        "TASK-001 active task ledger differs from its current task contract"
                    ),
                    "path": "docs/project/TASKS.md",
                    "task_id": "TASK-001",
                    "write_boundary": ["app/main.py", "docs/project/TASKS.md"],
                    "validation_evidence": list(expected_evidence),
                }
            ],
        )
        self.assertEqual(
            remediation["next_action"]["engine_rerun"],
            {
                "command": (
                    "python scripts/bootstrap_doctor.py --root . --json "
                    "--prior-remediation-fingerprint " + remediation["fingerprint"]
                ),
                "fingerprint": remediation["fingerprint"],
            },
        )

        evidence_free = doctor.derive_remediation(context, **common)
        self.assertEqual(
            evidence_free["next_action"]["corrections"][0]["task_id"], "NONE"
        )
        self.assertEqual(
            evidence_free["next_action"]["corrections"][0]["write_boundary"],
            ["docs/project/TASKS.md"],
        )

        unrelated = doctor.Context(ROOT)
        unrelated.error(
            "DOCUMENT_SUMMARY_STALE",
            "Generated task summary differs from canonical state",
            "docs/project/TASKS.md",
        )
        unrelated_remediation = doctor.derive_remediation(
            unrelated, task_validation_evidence=evidence, **common
        )
        self.assertEqual(
            unrelated_remediation["next_action"]["corrections"][0]["task_id"],
            "NONE",
        )

    def test_public_evaluation_serializes_to_the_existing_report(self) -> None:
        evaluation = api.evaluate_project(ROOT, template_source=True)
        self.assertIsInstance(evaluation, EngineEvaluation)
        expected = api.inspect_project(ROOT, template_source=True)
        self.assertEqual(serialize_evaluation(evaluation), expected)
        self.assertEqual(expected, doctor.inspect_project(ROOT, template_source=True))

    def test_evaluation_is_deeply_immutable(self) -> None:
        evaluation = EngineEvaluation.from_schema2(synthetic_schema2_report())
        with self.assertRaises(TypeError):
            evaluation.project["name"] = "Changed"  # type: ignore[index]
        with self.assertRaises(TypeError):
            evaluation.aws["aws_deployment"]["status"] = "SUCCEEDED"  # type: ignore[index]
        with self.assertRaises(AttributeError):
            evaluation.diagnostics.append({})  # type: ignore[attr-defined]
        with self.assertRaises(AttributeError):
            evaluation.status = "BLOCKED"  # type: ignore[misc]

    def test_report_serializes_without_observation_clock_or_policy(self) -> None:
        source = synthetic_schema2_report()
        evaluation = EngineEvaluation.from_schema2(source)
        unavailable = AssertionError("serializer attempted a prohibited dependency")
        with (
            mock.patch.object(builtins, "open", side_effect=unavailable),
            mock.patch.object(Path, "read_text", side_effect=unavailable),
            mock.patch.object(subprocess, "run", side_effect=unavailable),
            mock.patch.object(time, "time", side_effect=unavailable),
        ):
            observed = serialize_evaluation(evaluation)
        self.assertEqual(observed, source)
        self.assertEqual(list(observed), list(source))
        self.assertIsNot(observed, source)
        self.assertIsNot(observed["project"], source["project"])

    def test_optional_release_claim_round_trips_and_remains_immutable(self) -> None:
        source = synthetic_schema2_report()
        source["release_claim"] = synthetic_release_claim()
        evaluation = EngineEvaluation.from_schema2(source)

        observed = serialize_evaluation(evaluation)

        self.assertEqual(observed, source)
        self.assertEqual(
            list(observed).index("release_claim"),
            list(observed).index("release_evidence_cutoff") + 1,
        )
        self.assertEqual(
            [key for key in observed if key != "release_claim"],
            list(synthetic_schema2_report()),
        )
        self.assertEqual(
            validate_release_claim_projection(observed["release_claim"]),
            observed["release_claim"],
        )
        with self.assertRaises(TypeError):
            evaluation.deliver["release_claim"]["claims"]["LOCAL"]["status"] = "FAILED"  # type: ignore[index]

    def test_release_claim_validator_rejects_overclaim_and_noncanonical_evidence(
        self,
    ) -> None:
        claim = synthetic_release_claim()
        claim["claims"]["RECOVERY"]["status"] = "CURRENT"  # type: ignore[index]
        claim["claims"]["RECOVERY"]["allowed_claims"] = [  # type: ignore[index]
            "PROJECT_TARGET_COMPLETE(RECOVERY)"
        ]
        claim["claims"]["RECOVERY"]["prohibited_claims"] = []  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "current claim requires evidence"):
            validate_release_claim_projection(claim)

        malformed = synthetic_release_claim()
        malformed["claims"]["AWS_READ"]["evidence_ids"] = [  # type: ignore[index]
            "EV-1002",
            "EV-1002",
        ]
        with self.assertRaisesRegex(ValueError, "sorted unique cumulative"):
            validate_release_claim_projection(malformed)

        missing_scope = synthetic_release_claim()
        missing_scope["basis"]["account"] = "NONE"  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "require account and region"):
            validate_release_claim_projection(missing_scope)

        wrong_cutoff = synthetic_release_claim()
        wrong_cutoff["claims"]["DEPLOYED"]["evidence_ids"] = [  # type: ignore[index]
            "EV-1001",
            "EV-1002",
            "EV-1005",
        ]
        with self.assertRaisesRegex(ValueError, "current evidence cutoff"):
            validate_release_claim_projection(wrong_cutoff)

    def test_release_claim_keeps_historical_truth_without_current_completion(
        self,
    ) -> None:
        claim = synthetic_release_claim()
        deployed = claim["claims"]["DEPLOYED"]  # type: ignore[index]
        deployed["status"] = "HISTORICAL"
        deployed["allowed_claims"] = []
        deployed["prohibited_claims"] = ["PROJECT_TARGET_COMPLETE(DEPLOYED)"]

        observed = validate_release_claim_projection(claim)

        self.assertEqual(observed["claims"]["DEPLOYED"]["status"], "HISTORICAL")
        self.assertEqual(observed["claims"]["LOCAL"]["status"], "CURRENT")
        self.assertNotIn(
            "PROJECT_TARGET_COMPLETE(RECOVERY)",
            observed["claims"]["RECOVERY"]["allowed_claims"],
        )

    def test_release_claim_derives_each_cumulative_target_without_authority(
        self,
    ) -> None:
        targets = ("LOCAL", "AWS_READ", "DEPLOYED", "RECOVERY")
        for target_index, completion_target in enumerate(targets):
            with self.subTest(target=completion_target):
                claim = derive_release_claim_projection(
                    **release_claim_inputs(completion_target)
                )

                self.assertIsNotNone(claim)
                assert claim is not None
                for index, target in enumerate(targets):
                    expected = "CURRENT" if index <= target_index else "NOT_APPLICABLE"
                    self.assertEqual(claim["claims"][target]["status"], expected)
                self.assertEqual(claim["authority_effect"], "NONE")
                self.assertIs(claim["authorizes_aws_access"], False)
                self.assertIs(claim["authorizes_mutation"], False)

    def test_release_claim_legacy_and_malformed_higher_evidence_fail_closed(
        self,
    ) -> None:
        legacy = release_claim_inputs("LOCAL")
        legacy["requirements_schema"] = "1.4"
        self.assertIsNone(derive_release_claim_projection(**legacy))

        malformed = release_claim_inputs("AWS_READ")
        malformed["preflight"]["region"] = "US-WEST-2"  # type: ignore[index]
        claim = derive_release_claim_projection(**malformed)

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim["basis"]["account"], "NONE")
        self.assertEqual(claim["basis"]["region"], "NONE")
        self.assertEqual(claim["claims"]["LOCAL"]["status"], "CURRENT")
        self.assertEqual(claim["claims"]["AWS_READ"]["status"], "NOT_PROVEN")

    def test_failed_deployment_keeps_current_local_and_read_claims(self) -> None:
        inputs = release_claim_inputs("DEPLOYED")
        inputs["deployment"]["issues"] = ["stale deployment"]  # type: ignore[index]

        claim = derive_release_claim_projection(**inputs)

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim["claims"]["LOCAL"]["status"], "CURRENT")
        self.assertEqual(claim["claims"]["AWS_READ"]["status"], "CURRENT")
        self.assertEqual(claim["claims"]["DEPLOYED"]["status"], "NOT_PROVEN")

    def test_deployed_claim_requires_acknowledged_exact_terminal_cutoff(self) -> None:
        inputs = release_claim_inputs("DEPLOYED")
        inputs["deployment"]["acknowledged"] = False  # type: ignore[index]

        claim = derive_release_claim_projection(**inputs)

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim["claims"]["LOCAL"]["status"], "CURRENT")
        self.assertEqual(claim["claims"]["AWS_READ"]["status"], "CURRENT")
        self.assertEqual(claim["claims"]["DEPLOYED"]["status"], "NOT_PROVEN")

    def test_release_claim_requires_new_evidence_at_each_higher_target(self) -> None:
        claim = synthetic_release_claim()
        claim["claims"]["AWS_READ"]["evidence_ids"] = [  # type: ignore[index]
            "EV-1001"
        ]

        with self.assertRaisesRegex(ValueError, "requires new target evidence"):
            validate_release_claim_projection(claim)

    def test_nonterminal_project_cannot_claim_local_completion(self) -> None:
        inputs = release_claim_inputs("LOCAL")
        inputs["local_ready"] = False

        claim = derive_release_claim_projection(**inputs)

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim["claims"]["LOCAL"]["status"], "NOT_PROVEN")

    def test_project_release_claim_requires_exact_active_scope_basis(self) -> None:
        inputs = release_claim_inputs("LOCAL")
        claim = derive_project_release_claim(
            release_claim_verify_text(),
            requirements_schema=str(inputs["requirements_schema"]),
            completion_target=str(inputs["completion_target"]),
            requirements_revision=str(inputs["requirements_revision"]),
            design_revision=str(inputs["design_revision"]),
            construction_authorization=str(inputs["construction_authorization"]),
            artifact_sha256=str(inputs["artifact_sha256"]),
            lane=str(inputs["lane"]),
            release_state=str(inputs["release_state"]),
            evidence_cutoff=str(inputs["evidence_cutoff"]),
            preflight={},
            deployment={},
            local_ready=True,
        )
        stale_text = release_claim_verify_text().replace(
            "sha256:" + "a" * 64,
            "sha256:" + "b" * 64,
        )
        stale = derive_project_release_claim(
            stale_text,
            requirements_schema=str(inputs["requirements_schema"]),
            completion_target=str(inputs["completion_target"]),
            requirements_revision=str(inputs["requirements_revision"]),
            design_revision=str(inputs["design_revision"]),
            construction_authorization=str(inputs["construction_authorization"]),
            artifact_sha256=str(inputs["artifact_sha256"]),
            lane=str(inputs["lane"]),
            release_state=str(inputs["release_state"]),
            evidence_cutoff=str(inputs["evidence_cutoff"]),
            preflight={},
            deployment={},
            local_ready=True,
        )

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim["claims"]["LOCAL"]["status"], "CURRENT")
        self.assertIsNone(stale)

    def test_project_release_claim_requires_rollback_or_restore_for_recovery(
        self,
    ) -> None:
        inputs = release_claim_inputs("RECOVERY")
        common = {
            "requirements_schema": inputs["requirements_schema"],
            "completion_target": inputs["completion_target"],
            "requirements_revision": inputs["requirements_revision"],
            "design_revision": inputs["design_revision"],
            "construction_authorization": inputs["construction_authorization"],
            "artifact_sha256": inputs["artifact_sha256"],
            "lane": inputs["lane"],
            "release_state": inputs["release_state"],
            "evidence_cutoff": inputs["evidence_cutoff"],
            "preflight": inputs["preflight"],
            "deployment": inputs["deployment"],
            "local_ready": True,
        }
        rollback = derive_project_release_claim(
            release_claim_verify_text("ROLLBACK_OBSERVED: EV-1004; RESULT: PASS"),
            **common,
        )
        teardown = derive_project_release_claim(
            release_claim_verify_text("TEARDOWN_OBSERVED: EV-1004; RESULT: PASS"),
            **common,
        )
        reused_row_id = derive_project_release_claim(
            release_claim_verify_text("ROLLBACK_OBSERVED: EV-1003; RESULT: PASS"),
            **common,
        )

        self.assertIsNotNone(rollback)
        self.assertIsNotNone(teardown)
        self.assertIsNotNone(reused_row_id)
        assert (
            rollback is not None and teardown is not None and reused_row_id is not None
        )
        self.assertEqual(rollback["claims"]["RECOVERY"]["status"], "CURRENT")
        self.assertEqual(teardown["claims"]["RECOVERY"]["status"], "NOT_PROVEN")
        self.assertEqual(
            reused_row_id["claims"]["RECOVERY"]["status"],
            "NOT_PROVEN",
        )

    def test_higher_target_diagnostic_does_not_erase_current_lower_claims(self) -> None:
        inputs = release_claim_inputs("DEPLOYED")
        inputs["deployment"]["issues"] = ["stale deployment"]  # type: ignore[index]
        claim = derive_project_release_claim(
            release_claim_verify_text(),
            requirements_schema=str(inputs["requirements_schema"]),
            completion_target=str(inputs["completion_target"]),
            requirements_revision=str(inputs["requirements_revision"]),
            design_revision=str(inputs["design_revision"]),
            construction_authorization=str(inputs["construction_authorization"]),
            artifact_sha256=str(inputs["artifact_sha256"]),
            lane=str(inputs["lane"]),
            release_state=str(inputs["release_state"]),
            evidence_cutoff=str(inputs["evidence_cutoff"]),
            preflight=inputs["preflight"],  # type: ignore[arg-type]
            deployment=inputs["deployment"],  # type: ignore[arg-type]
            local_ready=True,
            diagnostics=[
                Diagnostic(
                    "AWS_DEPLOYMENT_EVIDENCE_INVALID",
                    "stale deployment",
                )
            ],
        )

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim["claims"]["LOCAL"]["status"], "CURRENT")
        self.assertEqual(claim["claims"]["AWS_READ"]["status"], "CURRENT")
        self.assertEqual(claim["claims"]["DEPLOYED"]["status"], "NOT_PROVEN")

    def test_failed_duplicate_evidence_id_cannot_qualify_local(self) -> None:
        inputs = release_claim_inputs("LOCAL")
        matrix = "\n".join(
            (
                "## Verification matrix",
                "",
                "| Evidence ID | PRD / property IDs | Task IDs | Requirement or invariant | Automated evidence | AWS/manual evidence | Artifact/environment | Status |",
                "|---|---|---|---|---|---|---|---|",
                "| EV-1001 | FR-001 | TASK-001 | outcome | tests | NONE | sha256:"
                + "a" * 64
                + " / development | FAILED |",
            )
        )
        claim = derive_project_release_claim(
            release_claim_verify_text() + "\n" + matrix + "\n",
            requirements_schema=str(inputs["requirements_schema"]),
            completion_target=str(inputs["completion_target"]),
            requirements_revision=str(inputs["requirements_revision"]),
            design_revision=str(inputs["design_revision"]),
            construction_authorization=str(inputs["construction_authorization"]),
            artifact_sha256=str(inputs["artifact_sha256"]),
            lane=str(inputs["lane"]),
            release_state=str(inputs["release_state"]),
            evidence_cutoff=str(inputs["evidence_cutoff"]),
            preflight={},
            deployment={},
            local_ready=True,
        )

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim["claims"]["LOCAL"]["status"], "NOT_PROVEN")

    def test_environment_substring_cannot_qualify_local_evidence(self) -> None:
        inputs = release_claim_inputs("LOCAL")
        artifact = "sha256:" + "a" * 64
        stale_artifact = "sha256:" + "b" * 64
        verify_text = release_claim_verify_text().replace(
            f"| {artifact} | test log | LOCAL_PASS |",
            f"| {stale_artifact} | test log | LOCAL_PASS |",
        )
        matrix = "\n".join(
            (
                "## Verification matrix",
                "",
                "| Evidence ID | PRD / property IDs | Task IDs | Requirement or invariant | Automated evidence | AWS/manual evidence | Artifact/environment | Status |",
                "|---|---|---|---|---|---|---|---|",
                f"| EV-1005 | FR-001 | TASK-001 | outcome | tests | NONE | {artifact} / development-old | LOCAL_PASS |",
            )
        )
        claim = derive_project_release_claim(
            verify_text + "\n" + matrix + "\n",
            requirements_schema=str(inputs["requirements_schema"]),
            completion_target=str(inputs["completion_target"]),
            requirements_revision=str(inputs["requirements_revision"]),
            design_revision=str(inputs["design_revision"]),
            construction_authorization=str(inputs["construction_authorization"]),
            artifact_sha256=str(inputs["artifact_sha256"]),
            lane=str(inputs["lane"]),
            release_state=str(inputs["release_state"]),
            evidence_cutoff=str(inputs["evidence_cutoff"]),
            preflight={},
            deployment={},
            local_ready=True,
            required_task_evidence={"TASK-001": ["EV-1001"]},
        )

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim["claims"]["LOCAL"]["status"], "NOT_PROVEN")

    def test_matrix_row_cannot_rescue_stale_done_task_evidence(self) -> None:
        inputs = release_claim_inputs("LOCAL")
        artifact = "sha256:" + "a" * 64
        stale_artifact = "sha256:" + "b" * 64
        verify_text = release_claim_verify_text().replace(
            f"| {artifact} | test log | LOCAL_PASS |",
            f"| {stale_artifact} | test log | LOCAL_PASS |",
        )
        matrix = "\n".join(
            (
                "## Verification matrix",
                "",
                "| Evidence ID | PRD / property IDs | Task IDs | Requirement or invariant | Automated evidence | AWS/manual evidence | Artifact/environment | Status |",
                "|---|---|---|---|---|---|---|---|",
                f"| EV-1001 | FR-001 | TASK-001 | outcome | tests | NONE | {artifact} / development | LOCAL_PASS |",
            )
        )
        claim = derive_project_release_claim(
            verify_text + "\n" + matrix + "\n",
            requirements_schema=str(inputs["requirements_schema"]),
            completion_target=str(inputs["completion_target"]),
            requirements_revision=str(inputs["requirements_revision"]),
            design_revision=str(inputs["design_revision"]),
            construction_authorization=str(inputs["construction_authorization"]),
            artifact_sha256=str(inputs["artifact_sha256"]),
            lane=str(inputs["lane"]),
            release_state=str(inputs["release_state"]),
            evidence_cutoff=str(inputs["evidence_cutoff"]),
            preflight={},
            deployment={},
            local_ready=True,
            required_task_evidence={"TASK-001": ["EV-1001"]},
        )

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim["claims"]["LOCAL"]["status"], "NOT_PROVEN")

    def test_every_cited_done_evidence_id_must_match_the_current_artifact(self) -> None:
        inputs = release_claim_inputs("LOCAL")
        artifact = "sha256:" + "a" * 64
        stale_artifact = "sha256:" + "b" * 64
        first_row = (
            f"| EV-1001 | TASK-001 | tests | PASS | owner | "
            f"2026-08-28T12:00:00Z | {artifact} | test log | LOCAL_PASS |"
        )
        second_row = (
            f"| EV-1006 | TASK-001 | integration | PASS | owner | "
            f"2026-08-28T12:01:00Z | {stale_artifact} | test log | VERIFIED |"
        )
        verify_text = release_claim_verify_text().replace(
            first_row,
            first_row + "\n" + second_row,
        )
        task_evidence = {"TASK-001": ["EV-1001", "EV-1006"]}
        tasks_text = doctor_fixtures.ready_task().replace(
            "- Evidence: `NONE`",
            "- Evidence: `EV-1001, EV-1006`",
            1,
        )
        self.assertEqual(
            required_done_task_evidence(tasks_text, ["TASK-001"]),
            task_evidence,
        )
        common = {
            "requirements_schema": str(inputs["requirements_schema"]),
            "completion_target": str(inputs["completion_target"]),
            "requirements_revision": str(inputs["requirements_revision"]),
            "design_revision": str(inputs["design_revision"]),
            "construction_authorization": str(inputs["construction_authorization"]),
            "artifact_sha256": str(inputs["artifact_sha256"]),
            "lane": str(inputs["lane"]),
            "release_state": str(inputs["release_state"]),
            "evidence_cutoff": str(inputs["evidence_cutoff"]),
            "preflight": {},
            "deployment": {},
            "local_ready": True,
            "required_task_evidence": task_evidence,
        }

        stale = derive_project_release_claim(verify_text, **common)
        current = derive_project_release_claim(
            verify_text.replace(stale_artifact, artifact),
            **common,
        )

        self.assertIsNotNone(stale)
        self.assertIsNotNone(current)
        assert stale is not None and current is not None
        self.assertEqual(stale["claims"]["LOCAL"]["status"], "NOT_PROVEN")
        self.assertEqual(current["claims"]["LOCAL"]["status"], "CURRENT")

    def test_zero_task_completion_requires_exact_current_matrix_evidence(self) -> None:
        inputs = release_claim_inputs("LOCAL")
        artifact = "sha256:" + "a" * 64
        active_scope = release_claim_verify_text().split(
            "\n\n## Task completion evidence",
            1,
        )[0]
        matrix = "\n".join(
            (
                "## Verification matrix",
                "",
                "| Evidence ID | PRD / property IDs | Task IDs | Requirement or invariant | Automated evidence | AWS/manual evidence | Artifact/environment | Status |",
                "|---|---|---|---|---|---|---|---|",
                f"| EV-1007 | FR-001 | NONE | already satisfied | review passed | NONE | {artifact} / development | VERIFIED |",
            )
        )
        claim = derive_project_release_claim(
            active_scope + "\n\n" + matrix + "\n",
            requirements_schema=str(inputs["requirements_schema"]),
            completion_target=str(inputs["completion_target"]),
            requirements_revision=str(inputs["requirements_revision"]),
            design_revision=str(inputs["design_revision"]),
            construction_authorization=str(inputs["construction_authorization"]),
            artifact_sha256=str(inputs["artifact_sha256"]),
            lane=str(inputs["lane"]),
            release_state=str(inputs["release_state"]),
            evidence_cutoff=str(inputs["evidence_cutoff"]),
            preflight={},
            deployment={},
            local_ready=True,
            required_task_evidence={},
        )

        self.assertEqual(required_done_task_evidence("", []), {})
        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim["claims"]["LOCAL"]["status"], "CURRENT")

    def test_report_module_imports_only_the_evaluation_model(self) -> None:
        tree = ast.parse(REPORT_PATH.read_text(encoding="utf-8"))
        relative_imports = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level
        }
        self.assertEqual(relative_imports, {"evaluation"})
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertFalse(
            called
            & {
                "open",
                "run",
                "time",
                "derive_route",
                "derive_remediation",
                "derive_interaction",
                "derive_external_authority",
                "resolve_context_packet",
                "project_document_summaries",
            }
        )

    def test_composition_builds_evaluation_before_schema_serialization(self) -> None:
        tree = ast.parse(COMPOSITION_PATH.read_text(encoding="utf-8"))
        schema_round_trips = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "from_schema2"
        }
        self.assertEqual(schema_round_trips, set())


if __name__ == "__main__":
    unittest.main()
