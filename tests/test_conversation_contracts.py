from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str, filename: str):
    path = SCRIPTS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


setup = load("conversation_setup_assistant", "setup_assistant.py")
doctor = load("conversation_bootstrap_doctor", "bootstrap_doctor.py")
presenter = load("conversation_fastlane_presenter", "fastlane_presenter.py")


def ready_evidence(**updates: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "repository_ready": True,
        "codex_cli_available": True,
        "codex_cli_supported": True,
        "codex_login_status_supported": True,
        "codex_login_ready": True,
        "git_available": True,
        "python_available": True,
        "python_version_supported": True,
        "uvx_available": True,
        "bubblewrap_required": True,
        "bubblewrap_available": True,
        "platform_supported": True,
        "platform_family": "LINUX",
        "is_wsl2": False,
        "pipx_available": True,
        "winget_available": False,
        "brew_available": False,
        "safe_probes_executed": True,
        "official_plugin_installed": True,
        "official_plugin_enabled": True,
        "official_plugin_loaded_in_session": True,
        "official_plugin_source_verified": True,
        "observed_marketplace_repository": setup.OFFICIAL_AWS_MARKETPLACE,
        "observed_plugin_source": setup.OFFICIAL_AWS_MARKETPLACE_NAME,
        "observed_plugin_identity": setup.OFFICIAL_AWS_CORE_IDENTITY,
        "native_hook_review_required": False,
        "native_hook_review_attested": False,
        "retrieve_skill_result": "PASS",
        "retrieve_skill_identifier": "aws-serverless",
        "search_documentation_result": "PASS",
        "search_documentation_query": "AWS serverless security guidance",
        "search_documentation_references": [
            "https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html"
        ],
        "credentials_inspected": False,
        "aws_account_accessed": False,
    }
    evidence.update(updates)
    return evidence


class ConversationContractTests(unittest.TestCase):
    def test_raw_doctor_and_presenter_keep_untouched_template_in_setup(self) -> None:
        report = doctor.inspect_project(REPOSITORY_ROOT)
        rendered = presenter.render_owner_update(report)

        self.assertEqual(report["classification"], "UNCONFIGURED_TEMPLATE")
        self.assertEqual(report["interaction"]["owner_stage"], "DEFINE")
        self.assertEqual(
            report["interaction"]["owner_action_kind"],
            "COMPLETE_PREREQUISITE_CHECKLIST",
        )
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn("send `init template` again", rendered)
        self.assertNotIn("DELIVER", rendered)
        self.assertEqual(report["aws_access"], "NOT_USED")
        self.assertEqual(report["authorizations"]["aws"], "NONE")

    def test_missing_prerequisites_return_one_complete_action_then_ready_welcome(self) -> None:
        blocked = setup.reduce_prerequisites(
            ready_evidence(
                codex_cli_available=False,
                codex_cli_supported=False,
                uvx_available=False,
                official_plugin_loaded_in_session=False,
            )
        )
        rendered = setup.render_setup_response(blocked)
        self.assertEqual(blocked["owner_action_id"], "COMPLETE_PREREQUISITE_CHECKLIST")
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn("Codex CLI", rendered)
        self.assertIn("Astral uv", rendered)
        self.assertIn("official AWS Core", rendered)

        ready = setup.reduce_prerequisites(ready_evidence())
        welcome = setup.render_setup_response(ready)
        self.assertEqual(ready["state"], "PREREQUISITES_READY")
        for label in ("Project name:", "Preferred AWS Region:", "Development budget:"):
            self.assertEqual(welcome.count(label), 1)

    def test_initialized_intake_resume_does_not_repeat_setup(self) -> None:
        interaction = doctor.derive_interaction(
            "INTAKE_REQUIRED",
            "INTAKE-10",
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=False,
            aws_execution_planning_ready=False,
        )
        rendered = presenter.render_owner_update({"interaction": interaction})
        self.assertTrue(rendered.startswith("FASTLANE · DEFINE"))
        self.assertEqual(rendered.count("Need from you:"), 1)
        for forbidden in (
            "Welcome to AWS Codex Fastlane",
            "Project name:",
            "Preferred AWS Region:",
            "Development budget:",
            "init template",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_formal_gate_state_cannot_be_rendered_as_routine_status(self) -> None:
        interaction = doctor.derive_interaction(
            "WAITING_GATE_A",
            "INTAKE-20",
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=False,
            aws_execution_planning_ready=False,
        )
        self.assertTrue(interaction["formal_receipt_required"])
        with self.assertRaises(presenter.PresentationError):
            presenter.render_owner_update({"interaction": interaction})

    def test_setup_evidence_never_becomes_repository_or_aws_authority(self) -> None:
        report = setup.reduce_prerequisites(ready_evidence())
        self.assertEqual(report["repository_writes"], "NONE")
        self.assertEqual(report["aws_credentials"], "NOT_INSPECTED")
        self.assertEqual(report["aws_access"], "NOT_USED")
        self.assertEqual(report["aws_authorization"], "NONE")
        self.assertFalse(report["user_state_persisted_in_repository"])

    def test_missing_design_evidence_stays_in_design_with_one_aws_core_action(self) -> None:
        interaction = doctor.derive_interaction(
            "BLOCKED",
            "STOP",
            has_errors=True,
            diagnostic_codes=["AWS_CORE_EVIDENCE_REQUIRED"],
            design_aws_core_ready=False,
            aws_execution_planning_ready=False,
        )
        rendered = presenter.render_owner_update({"interaction": interaction})
        self.assertEqual(interaction["owner_stage"], "DESIGN")
        self.assertEqual(interaction["owner_action_kind"], "ENABLE_AWS_CORE")
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn("Enable official AWS Core", rendered)
        self.assertFalse(interaction["automatic_continuation_allowed"])
        self.assertFalse(interaction["formal_receipt_required"])

    def test_golden_define_design_deliver_route_has_only_two_product_stops(self) -> None:
        sequence = (
            ("REQUIREMENTS_ANALYSIS", "REQ-10", "DEFINE", "OWNER_UPDATE"),
            ("WAITING_GATE_A", "INTAKE-20", "DEFINE", "GATE_A"),
            ("DESIGN_REQUIRED", "DESIGN-10", "DESIGN", "OWNER_UPDATE"),
            ("WAITING_GATE_B", "DESIGN-20", "DESIGN", "GATE_B"),
            ("TASK_PLAN_REQUIRED", "TASK-10", "DELIVER", "OWNER_UPDATE"),
            (
                "CONSTRUCTION_AUTONOMOUS",
                "BUILD-20",
                "DELIVER",
                "OWNER_UPDATE",
            ),
            ("RELEASE_REVIEW", "RELEASE-10", "DELIVER", "OWNER_UPDATE"),
        )
        observed: list[tuple[str, str, str]] = []
        for lifecycle, prompt, stage, mode in sequence:
            routed = doctor.derive_interaction(
                lifecycle,
                prompt,
                has_errors=False,
                diagnostic_codes=[],
                design_aws_core_ready=lifecycle not in {"DESIGN_REQUIRED"},
                aws_execution_planning_ready=False,
            )
            observed.append(
                (
                    str(routed["owner_stage"]),
                    str(routed["response_mode"]),
                    str(routed["owner_action_kind"]),
                )
            )
            self.assertEqual(routed["owner_stage"], stage)
            self.assertEqual(routed["response_mode"], mode)
            if mode == "OWNER_UPDATE":
                self.assertTrue(routed["automatic_continuation_allowed"])
                self.assertEqual(
                    routed["owner_action_kind"], "NONE_CONTINUE_AUTOMATICALLY"
                )
                rendered = presenter.render_owner_update({"interaction": routed})
                self.assertEqual(rendered.count("Need from you:"), 1)
                self.assertIn("Need from you: Nothing.", rendered)
                self.assertNotIn(prompt, rendered)
            else:
                self.assertFalse(routed["automatic_continuation_allowed"])
                self.assertTrue(routed["formal_receipt_required"])

        self.assertEqual(
            [item[2] for item in observed if item[1] != "OWNER_UPDATE"],
            ["APPROVE_GATE_A", "APPROVE_GATE_B"],
        )

        side = presenter.render_side_question_response(
            {
                "interaction": doctor.derive_interaction(
                    "DESIGN_REQUIRED",
                    "DESIGN-10",
                    has_errors=False,
                    diagnostic_codes=[],
                    design_aws_core_ready=True,
                    aws_execution_planning_ready=False,
                )
            },
            answer="The project remains in Design; no approved artifact changed.",
        )
        self.assertIn("Project state changed: No.", side)
        self.assertIn("Pending next action: Nothing.", side)

    def test_mixed_diagnostics_repair_safe_codex_items_first(self) -> None:
        ctx = doctor.Context(root=REPOSITORY_ROOT)
        ctx.error(
            "TASK_GRAPH_INVALID",
            "Generated task status is invalid",
            "docs/project/TASKS.md",
        )
        ctx.error(
            "PROJECT_SELECTION_REQUIRED",
            "A product decision is unresolved",
            "docs/project/PRD.md",
        )
        tasks = doctor.TaskSummary(
            plan_revision="PLAN-0001",
            plan_state="CURRENT",
        )
        envelope = {
            "Allowed repository write set": "PATHS: app/**; tests/**",
            "Excluded or owner-only write set": "NONE",
            "Protected dirty paths": "NONE",
        }

        remediation = doctor.derive_remediation(
            ctx,
            classification="ACTIVE_GREENFIELD",
            gate_a="APPROVED_FOR_DESIGN",
            gate_b="APPROVED_FOR_CONSTRUCTION",
            envelope=envelope,
            tasks=tasks,
        )

        self.assertEqual(
            [item["diagnostic_id"] for item in remediation["items"]],
            ["DGN-0001", "DGN-0002"],
        )
        self.assertEqual(
            remediation["items"][0],
            {
                "diagnostic_id": "DGN-0001",
                "diagnostic_code": "TASK_GRAPH_INVALID",
                "path": "docs/project/TASKS.md",
                "responsible_party": "CODEX",
                "category": "AGENT_CORRECTION",
                "automatic_correction_allowed": True,
            },
        )
        self.assertEqual(
            remediation["items"][1]["responsible_party"], "OWNER"
        )
        self.assertEqual(
            remediation["next_action"],
            {
                "responsible_party": "CODEX",
                "action_kind": "CORRECT_AND_REVALIDATE",
                "automatic_continuation_allowed": True,
            },
        )
        routed = doctor.derive_interaction(
            "BLOCKED",
            "STOP",
            has_errors=True,
            diagnostic_codes=["TASK_GRAPH_INVALID", "PROJECT_SELECTION_REQUIRED"],
            design_aws_core_ready=True,
            aws_execution_planning_ready=False,
            remediation=remediation,
            owner_stage_hint="DELIVER",
        )
        self.assertFalse(routed["owner_action_required"])
        self.assertEqual(
            routed["owner_action_kind"], "NONE_CONTINUE_AUTOMATICALLY"
        )
        self.assertTrue(routed["automatic_continuation_allowed"])

    def test_unknown_and_protected_diagnostics_require_human_review(self) -> None:
        envelope = {
            "Allowed repository write set": "PATHS: app/**; tests/**",
            "Excluded or owner-only write set": "NONE",
            "Protected dirty paths": "PATHS: docs/project/TASKS.md",
        }
        tasks = doctor.TaskSummary(plan_revision="PLAN-0001", plan_state="CURRENT")
        for code in ("TASK_GRAPH_INVALID", "UNKNOWN_DIAGNOSTIC"):
            with self.subTest(code=code):
                ctx = doctor.Context(root=REPOSITORY_ROOT)
                ctx.error(code, "Review required", "docs/project/TASKS.md")
                remediation = doctor.derive_remediation(
                    ctx,
                    classification="ACTIVE_GREENFIELD",
                    gate_a="APPROVED_FOR_DESIGN",
                    gate_b="APPROVED_FOR_CONSTRUCTION",
                    envelope=envelope,
                    tasks=tasks,
                )
                self.assertEqual(
                    remediation["items"][0]["responsible_party"],
                    "HUMAN_REVIEWER",
                )
                self.assertEqual(
                    remediation["items"][0]["category"],
                    "MANUAL_SAFETY_REVIEW",
                )
                self.assertFalse(
                    remediation["items"][0]["automatic_correction_allowed"]
                )
                self.assertEqual(
                    remediation["next_action"]["action_kind"],
                    "REVIEW_SAFETY_BLOCKER",
                )





if __name__ == "__main__":
    unittest.main()
