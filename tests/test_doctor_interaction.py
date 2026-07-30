from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "bootstrap_doctor.py"
SPEC = importlib.util.spec_from_file_location("doctor_interaction_under_test", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT}")
doctor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = doctor
SPEC.loader.exec_module(doctor)


def interaction(
    lifecycle: str,
    prompt: str,
    *,
    errors: bool = False,
    diagnostics: list[str] | None = None,
    design_ready: bool = False,
    aws_ready: bool = False,
    req_materiality: str = "OPTIONAL",
    req_ready: bool = True,
) -> dict[str, object]:
    return doctor.derive_interaction(
        lifecycle,
        prompt,
        has_errors=errors,
        diagnostic_codes=diagnostics or [],
        design_aws_core_ready=design_ready,
        aws_execution_planning_ready=aws_ready,
        req_aws_core_materiality=req_materiality,
        req_aws_core_ready=req_ready,
    )


class DoctorInteractionTests(unittest.TestCase):
    def test_template_report_keeps_existing_fields_and_adds_interaction(self) -> None:
        report = doctor.inspect_project(REPOSITORY_ROOT, template_source=True)
        self.assertEqual(report["schema_version"], 2)
        for field in (
            "bootstrap_version",
            "status",
            "classification",
            "ok",
            "lifecycle_state",
            "next_prompt",
            "project",
            "gates",
            "authorizations",
            "aws_mode_boundary",
            "tasks",
            "diagnostics",
            "interaction",
        ):
            self.assertIn(field, report)
        self.assertIn(
            report["interaction"]["owner_stage"], {"DEFINE", "DESIGN", "DELIVER"}
        )
        for task_field in (
            "completed",
            "skipped",
            "blocked",
            "ready_ids",
            "active_ids",
            "blocked_ids",
        ):
            self.assertIn(task_field, report["tasks"])

    def test_aws_mode_boundary_separates_phase_ceiling_and_authority(self) -> None:
        expected_modes = {
            "BOOT-00": "NONE",
            "INTAKE-10": "NONE",
            "REQ-10": "DOCS_ONLY",
            "INTAKE-20": "NONE",
            "DESIGN-10": "DOCS_ONLY",
            "DESIGN-20": "NONE",
            "BUG-10": "DOCS_ONLY",
            "TASK-10": "NONE",
            "BUILD-10": "NONE",
            "BUILD-20": "NONE",
            "SYNC-10": "NONE",
            "RELEASE-10": "NONE",
            "AWS-10": "READ_ONLY",
            "AWS-20": "MUTATION",
            "AWS-30": "READ_ONLY",
            "AWS-40": "READ_ONLY",
            "AWS-50": "MUTATION",
            "STOP": "NONE",
        }
        for prompt, expected in expected_modes.items():
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    doctor.derive_current_prompt_aws_mode(prompt), expected
                )

        no_authority = {"kind": "NONE", "validity": "NONE"}
        none_boundary = doctor.derive_aws_mode_boundary(
            "documentation-only",
            {"AWS boundary": "NONE"},
            "REQ-10",
            no_authority,
        )
        self.assertEqual(
            set(none_boundary),
            {
                "project_lane",
                "local_task_modes",
                "current_prompt_mode",
                "gate_b_maximum",
                "external_authority_kind",
                "external_authority_validity",
                "account_access_authorized",
                "mutation_authorized",
            },
        )
        self.assertEqual(none_boundary["local_task_modes"], ["NONE"])
        self.assertFalse(none_boundary["account_access_authorized"])
        self.assertFalse(none_boundary["mutation_authorized"])

        for maximum in ("DOCS_ONLY", "READ_ONLY", "MUTATE_LISTED_RESOURCES"):
            with self.subTest(maximum=maximum):
                boundary = doctor.derive_aws_mode_boundary(
                    "explicit-gate",
                    {"AWS boundary": maximum},
                    "BUILD-20",
                    no_authority,
                )
                self.assertEqual(boundary["local_task_modes"], ["NONE", "DOCS_ONLY"])
                self.assertEqual(boundary["current_prompt_mode"], "NONE")
                self.assertFalse(boundary["account_access_authorized"])
                self.assertFalse(boundary["mutation_authorized"])

        current_read = doctor.derive_aws_mode_boundary(
            "read-only",
            {"AWS boundary": "READ_ONLY"},
            "AWS-30",
            {"kind": "AWS_READ_ONLY", "validity": "CURRENT"},
        )
        self.assertTrue(current_read["account_access_authorized"])
        self.assertFalse(current_read["mutation_authorized"])

        current_mutation = doctor.derive_aws_mode_boundary(
            "explicit-gate",
            {"AWS boundary": "MUTATE_LISTED_RESOURCES"},
            "AWS-20",
            {"kind": "AWS_DEPLOYMENT", "validity": "CURRENT"},
        )
        self.assertTrue(current_mutation["account_access_authorized"])
        self.assertTrue(current_mutation["mutation_authorized"])

        wrong_phase = doctor.derive_aws_mode_boundary(
            "explicit-gate",
            {"AWS boundary": "MUTATE_LISTED_RESOURCES"},
            "DESIGN-10",
            {"kind": "AWS_DEPLOYMENT", "validity": "CURRENT"},
        )
        self.assertFalse(wrong_phase["account_access_authorized"])
        self.assertFalse(wrong_phase["mutation_authorized"])

    def test_gate_modes_are_formal_and_revision_receipts_remain_separate(self) -> None:
        gate_a = interaction("WAITING_GATE_A", "INTAKE-20")
        gate_b = interaction("WAITING_GATE_B", "DESIGN-20", design_ready=True)
        self.assertEqual(gate_a["response_mode"], "GATE_A")
        self.assertEqual(gate_a["owner_action_kind"], "APPROVE_GATE_A")
        self.assertTrue(gate_a["formal_receipt_required"])
        self.assertEqual(gate_b["response_mode"], "GATE_B")
        self.assertEqual(gate_b["owner_action_kind"], "APPROVE_GATE_B")
        self.assertTrue(gate_b["formal_receipt_required"])

    def test_safe_internal_routes_continue_without_owner_action(self) -> None:
        for lifecycle, prompt, stage in (
            ("REQUIREMENTS_ANALYSIS", "REQ-10", "DEFINE"),
            ("DESIGN_REQUIRED", "DESIGN-10", "DESIGN"),
            ("TASK_PLAN_REQUIRED", "TASK-10", "DELIVER"),
            ("CONSTRUCTION_AUTONOMOUS", "BUILD-20", "DELIVER"),
            ("RELEASE_REVIEW", "RELEASE-10", "DELIVER"),
        ):
            with self.subTest(lifecycle=lifecycle):
                result = interaction(lifecycle, prompt)
                self.assertEqual(result["owner_stage"], stage)
                self.assertEqual(
                    result["owner_action_kind"], "NONE_CONTINUE_AUTOMATICALLY"
                )
                self.assertFalse(result["owner_action_required"])
                self.assertTrue(result["automatic_continuation_allowed"])

    def test_accepted_gates_route_immediately_to_safe_internal_work(self) -> None:
        empty = doctor.TaskSummary()
        design_route = doctor.derive_route(
            "APPROVED_FOR_DESIGN",
            "BLOCKED",
            True,
            False,
            empty,
            False,
            "NONE",
        )
        self.assertEqual(design_route, ("DESIGN_REQUIRED", "DESIGN-10"))

        task_route = doctor.derive_route(
            "APPROVED_FOR_DESIGN",
            "APPROVED_FOR_CONSTRUCTION",
            True,
            True,
            empty,
            True,
            "NONE",
        )
        self.assertEqual(task_route, ("TASK_PLAN_REQUIRED", "TASK-10"))

        planned = doctor.TaskSummary(
            plan_state="CURRENT",
            statuses={"TASK-0001": "READY"},
            ready=["TASK-0001"],
        )
        build_route = doctor.derive_route(
            "APPROVED_FOR_DESIGN",
            "APPROVED_FOR_CONSTRUCTION",
            True,
            True,
            planned,
            False,
            "SINGLE_TASK",
        )
        self.assertEqual(build_route, ("CONSTRUCTION_SINGLE", "BUILD-10"))

        for lifecycle, prompt in (design_route, task_route, build_route):
            routed = interaction(lifecycle, prompt, design_ready=True)
            self.assertEqual(routed["owner_action_kind"], "NONE_CONTINUE_AUTOMATICALLY")
            self.assertTrue(routed["automatic_continuation_allowed"])

    def test_intake_current_aws_and_validation_each_have_one_stable_action(
        self,
    ) -> None:
        intake = interaction("INTAKE_REQUIRED", "INTAKE-10")
        aws = interaction("AWS_PREFLIGHT_REQUIRED", "AWS-10", aws_ready=True)
        blocked = interaction("BLOCKED", "STOP", errors=True, diagnostics=["PRD_PARSE"])
        aws_blocked = interaction(
            "BLOCKED",
            "STOP",
            errors=True,
            diagnostics=["AWS_CORE_EVIDENCE_REQUIRED"],
        )
        aws_unavailable = interaction(
            "BLOCKED",
            "STOP",
            errors=True,
            diagnostics=["AWS_CORE_CAPABILITY_UNAVAILABLE"],
        )
        self.assertEqual(intake["owner_action_kind"], "ANSWER_OPEN_DECISIONS")
        self.assertEqual(aws["owner_action_kind"], "AUTHORIZE_AWS_OPERATION")
        self.assertEqual(blocked["owner_action_kind"], "FIX_VALIDATION_FAILURE")
        self.assertEqual(aws_blocked["owner_action_kind"], "FIX_VALIDATION_FAILURE")
        self.assertEqual(aws_unavailable["owner_action_kind"], "ENABLE_AWS_CORE")
        for value in (intake, aws, blocked, aws_blocked, aws_unavailable):
            self.assertTrue(value["owner_action_required"])

    def test_aws_preflight_collects_evidence_before_requesting_authority(self) -> None:
        result = interaction("AWS_PREFLIGHT_REQUIRED", "AWS-10")
        self.assertEqual(result["response_mode"], "OWNER_UPDATE")
        self.assertEqual(result["state"], "WORKING")
        self.assertEqual(result["owner_action_kind"], "NONE_CONTINUE_AUTOMATICALLY")
        self.assertFalse(result["formal_receipt_required"])
        self.assertTrue(result["automatic_continuation_allowed"])

    def test_aws_core_materiality_and_evidence_are_machine_derived(self) -> None:
        define = interaction("INTAKE_REQUIRED", "INTAKE-10")
        design_missing = interaction("DESIGN_REQUIRED", "DESIGN-10")
        design_current = interaction("DESIGN_REQUIRED", "DESIGN-10", design_ready=True)
        aws_missing = interaction("AWS_PREFLIGHT_REQUIRED", "AWS-10")
        self.assertEqual(
            define["aws_core"],
            {"materiality": "NOT_MATERIAL", "evidence_status": "NOT_REQUIRED"},
        )
        self.assertEqual(design_missing["aws_core"]["evidence_status"], "REQUIRED")
        self.assertEqual(design_current["aws_core"]["evidence_status"], "CURRENT")
        self.assertEqual(aws_missing["aws_core"]["evidence_status"], "REQUIRED")

        req_current = interaction(
            "REQUIREMENTS_ANALYSIS",
            "REQ-10",
            req_materiality="REQUIRED",
            req_ready=True,
        )
        req_missing = interaction(
            "REQUIREMENTS_ANALYSIS",
            "REQ-10",
            req_materiality="REQUIRED",
            req_ready=False,
        )
        req_blocked = interaction(
            "REQUIREMENTS_ANALYSIS",
            "REQ-10",
            errors=True,
            diagnostics=["AWS_CORE_EVIDENCE_REQUIRED"],
            req_materiality="REQUIRED",
            req_ready=False,
        )
        self.assertEqual(
            req_current["aws_core"],
            {"materiality": "MATERIAL", "evidence_status": "CURRENT"},
        )
        self.assertEqual(
            req_missing["aws_core"],
            {"materiality": "MATERIAL", "evidence_status": "REQUIRED"},
        )
        self.assertEqual(
            req_blocked["aws_core"],
            {"materiality": "MATERIAL", "evidence_status": "BLOCKED"},
        )
        for non_material in ("OPTIONAL", "NOT_MATERIAL"):
            with self.subTest(non_material=non_material):
                projected = interaction(
                    "REQUIREMENTS_ANALYSIS",
                    "REQ-10",
                    req_materiality=non_material,
                )
                self.assertEqual(
                    projected["aws_core"],
                    {
                        "materiality": "NOT_MATERIAL",
                        "evidence_status": "NOT_REQUIRED",
                    },
                )

    def test_blocking_ids_are_stable_codes_only_when_blocked(self) -> None:
        blocked = interaction(
            "BLOCKED",
            "STOP",
            errors=True,
            diagnostics=["Z_LAST", "A_FIRST", "A_FIRST"],
        )
        working = interaction(
            "DESIGN_REQUIRED",
            "DESIGN-10",
            diagnostics=["NON_BLOCKING_WARNING"],
        )
        self.assertEqual(blocked["blocking_ids"], ["A_FIRST", "Z_LAST"])
        self.assertEqual(working["blocking_ids"], [])

    def test_aws30_owner_action_depends_only_on_separate_read_authority(self) -> None:
        current_read = doctor.derive_interaction(
            "AWS_DEPLOYMENT_RECONCILIATION",
            "AWS-30",
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=True,
            aws_execution_planning_ready=True,
            aws_mutation_authority_ready=False,
            aws_lane="explicit-gate",
            aws_read_authority_required=False,
        )
        missing_read = doctor.derive_interaction(
            "AWS_DEPLOYMENT_RECONCILIATION",
            "AWS-30",
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=True,
            aws_execution_planning_ready=True,
            aws_mutation_authority_ready=True,
            aws_lane="explicit-gate",
            aws_read_authority_required=True,
        )

        self.assertEqual(current_read["owner_stage"], "DELIVER")
        self.assertEqual(current_read["response_mode"], "OWNER_UPDATE")
        self.assertEqual(
            current_read["owner_action_kind"], "NONE_CONTINUE_AUTOMATICALLY"
        )
        self.assertFalse(current_read["owner_action_required"])
        self.assertTrue(current_read["automatic_continuation_allowed"])
        self.assertFalse(current_read["formal_receipt_required"])

        self.assertEqual(missing_read["response_mode"], "AWS_RECEIPT")
        self.assertEqual(
            missing_read["owner_action_kind"], "AUTHORIZE_AWS_READ_PREFLIGHT"
        )
        self.assertTrue(missing_read["owner_action_required"])
        self.assertFalse(missing_read["automatic_continuation_allowed"])
        self.assertTrue(missing_read["formal_receipt_required"])
        self.assertNotEqual(
            missing_read["owner_action_kind"], "AUTHORIZE_AWS_OPERATION"
        )


if __name__ == "__main__":
    unittest.main()
