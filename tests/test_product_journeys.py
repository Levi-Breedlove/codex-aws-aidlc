from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from tests import test_bootstrap_doctor as doctor_fixtures
from tests import test_fastlane_hooks as hook_fixtures
from tests import test_setup_assistant as setup_fixtures
from tests import test_task_waves as task_fixtures

import bootstrap_doctor as doctor
import fastlane_presenter as presenter
import fastlane_context as context_runtime
import package_release
import setup_assistant as setup
import task_waves


class ProductJourneyTests(unittest.TestCase):
    def extract_template(self, destination: Path, name: str) -> Path:
        payload = package_release.build_release_bytes(REPOSITORY_ROOT)
        root = destination / name
        root.mkdir()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            archive.extractall(root)
        return root / package_release.ARCHIVE_ROOT

    def initialize(self, project: Path) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "bootstrap.py",
                "--target",
                str(project),
                "--project-name",
                "Journey Test Project",
                "--region",
                "us-west-2",
                "--cost-posture",
                "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                "--in-place-template-instance",
            ],
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def run_doctor_cli(self, project: Path) -> tuple[int, dict[str, object]]:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/bootstrap_doctor.py",
                "--root",
                str(project),
                "--json",
            ],
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.returncode, json.loads(completed.stdout)

    def test_extracted_template_setup_initializes_once_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            project = self.extract_template(temporary, "fresh")

            exit_code, untouched = self.run_doctor_cli(project)
            self.assertEqual(exit_code, 1)
            self.assertEqual(untouched["classification"], "UNCONFIGURED_TEMPLATE")
            self.assertEqual(untouched["interaction"]["owner_stage"], "DEFINE")
            self.assertEqual(
                untouched["interaction"]["owner_action_kind"],
                "COMPLETE_PREREQUISITE_CHECKLIST",
            )
            self.assertEqual(untouched["gates"]["gate_a"], "BLOCKED")
            self.assertEqual(untouched["gates"]["gate_b"], "BLOCKED")
            self.assertEqual(untouched["authorizations"]["aws"], "NONE")
            packet = untouched["context_plan"]
            self.assertEqual(packet["maximum_initial_source_bytes"], 12_000)
            self.assertEqual(
                packet["actual_initial_source_bytes"],
                sum(item["source_bytes"] for item in packet["resolved_initial_slices"]),
            )
            self.assertIn(
                packet["budget_status"],
                {"WITHIN_LIMIT", "OVERSIZED_REQUIRED_RECORD"},
            )
            for item in packet["resolved_initial_slices"]:
                source = (project / item["path"]).read_text(encoding="utf-8")
                selected = "\n".join(
                    source.splitlines()[item["start_line"] - 1 : item["end_line"]]
                )
                canonical = context_runtime.canonical_source_bytes(selected)
                self.assertEqual(item["source_bytes"], len(canonical))
                self.assertEqual(
                    item["canonical_sha256"],
                    "sha256:" + hashlib.sha256(canonical).hexdigest(),
                )
            owner_update = presenter.render_owner_update(untouched)
            self.assertIn("This template has not been initialized.", owner_update)
            self.assertEqual(owner_update.count("Need from you:"), 1)
            self.assertNotIn("DELIVER", owner_update)

            session_context = hook_fixtures.fastlane_hook.handle_event(
                "session-start",
                hook_fixtures.payload("SessionStart", project),
                root=project,
                doctor_report=untouched,
            )
            context = session_context["hookSpecificOutput"]["additionalContext"]
            self.assertIn("prerequisite checklist", context)
            self.assertNotIn("stage=DELIVER", context)

            blocked = setup.reduce_prerequisites(
                setup_fixtures.local_ready(
                    uvx_available=False,
                    official_plugin_loaded_in_session=False,
                )
            )
            checklist = setup.render_setup_response(blocked)
            self.assertEqual(
                blocked["owner_action_id"], "COMPLETE_PREREQUISITE_CHECKLIST"
            )
            self.assertEqual(checklist.count("Need from you:"), 1)
            self.assertIn("Astral uv", checklist)
            self.assertIn("official AWS Core", checklist)

            ready = setup.reduce_prerequisites(setup_fixtures.local_ready())
            welcome = setup.render_setup_response(ready)
            for label in (
                "Project name:",
                "Preferred AWS Region:",
                "Development budget:",
            ):
                self.assertEqual(welcome.count(label), 1)

            self.initialize(project)
            first_exit, first_resume = self.run_doctor_cli(project)
            second_exit, second_resume = self.run_doctor_cli(project)
            self.assertEqual(first_exit, 0)
            self.assertEqual(second_exit, 0)
            self.assertEqual(first_resume["classification"], "ACTIVE_GREENFIELD")
            self.assertEqual(first_resume["next_prompt"], "INTAKE-10")
            self.assertEqual(first_resume["interaction"], second_resume["interaction"])
            self.assertEqual(
                first_resume["context_plan"], second_resume["context_plan"]
            )
            resumed = presenter.render_owner_update(first_resume)
            for setup_text in (
                "Welcome to AWS Codex Fastlane",
                "Project name:",
                "Preferred AWS Region:",
                "Development budget:",
                "prerequisite checklist",
            ):
                self.assertNotIn(setup_text, resumed)

            state_text = (project / "bootstrap.yaml").read_text(encoding="utf-8")
            for forbidden in (
                str(temporary),
                "codex_login_ready",
                "official_plugin_enabled",
                "native_hook_review_attested",
                "credentials_inspected",
                "aws_account_accessed",
                "resolved_initial_slices",
                "actual_initial_source_bytes",
            ):
                self.assertNotIn(forbidden, state_text)

    def test_gate_evidence_and_construction_routes_use_real_project_artifacts(self) -> None:
        fixture = doctor_fixtures.BootstrapDoctorTests()
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)

            define_project = self.extract_template(temporary, "define")
            self.initialize(define_project)
            fixture.approve_project(define_project, gate_b=False)
            after_gate_a = doctor.inspect_project(define_project)
            self.assertTrue(after_gate_a["ok"], after_gate_a["diagnostics"])
            self.assertEqual(after_gate_a["next_prompt"], "DESIGN-10")
            self.assertEqual(after_gate_a["interaction"]["owner_stage"], "DESIGN")
            self.assertTrue(
                after_gate_a["interaction"]["automatic_continuation_allowed"]
            )
            self.assertFalse(after_gate_a["interaction"]["formal_receipt_required"])

            current_design = doctor.derive_interaction(
                "DESIGN_REQUIRED",
                "DESIGN-10",
                has_errors=False,
                diagnostic_codes=[],
                design_aws_core_ready=True,
                aws_execution_planning_ready=False,
            )
            self.assertEqual(current_design["aws_core"]["evidence_status"], "CURRENT")
            self.assertTrue(current_design["automatic_continuation_allowed"])

            deliver_project = self.extract_template(temporary, "deliver")
            self.initialize(deliver_project)
            fixture.approve_project(deliver_project, gate_b=True)
            current = doctor.inspect_project(deliver_project)
            self.assertTrue(current["ok"], current["diagnostics"])
            self.assertEqual(current["next_prompt"], "TASK-10")
            self.assertTrue(current["interaction"]["automatic_continuation_allowed"])

            verify_path = deliver_project / "docs/project/VERIFY.md"
            current_evidence = verify_path.read_text(encoding="utf-8")
            verify_path.write_text(
                doctor_fixtures.record_aws_core_evidence(
                    current_evidence, "DESIGN-10", "NOT_STARTED"
                ),
                encoding="utf-8",
            )
            missing = doctor.inspect_project(deliver_project)
            self.assertFalse(missing["ok"])
            self.assertEqual(
                missing["interaction"]["owner_action_kind"], "ENABLE_AWS_CORE"
            )
            self.assertEqual(missing["interaction"]["owner_stage"], "DESIGN")
            self.assertEqual(
                presenter.render_owner_update(missing).count("Need from you:"), 1
            )
            side_answer = presenter.render_side_question_response(
                missing,
                answer="Official AWS Core evidence is needed only for this material design step.",
            )
            self.assertIn("Project state changed: No.", side_answer)
            self.assertIn("Pending next action: Enable official AWS Core", side_answer)

            verify_path.write_text(current_evidence, encoding="utf-8")
            recovered = doctor.inspect_project(deliver_project)
            self.assertTrue(recovered["ok"], recovered["diagnostics"])
            self.assertEqual(recovered["next_prompt"], "TASK-10")

            fixture.initialize_task_plan(
                deliver_project,
                doctor_fixtures.ready_task(
                    requirements="REQ-0001; FR-001; PROP-001",
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    command="python -m unittest tests.test_properties",
                    property_projection=doctor_fixtures.property_execution_projection(),
                ),
            )
            construction = doctor.inspect_project(deliver_project)
            self.assertTrue(construction["ok"], construction["diagnostics"])
            self.assertEqual(construction["next_prompt"], "BUILD-10")
            self.assertEqual(construction["interaction"]["owner_stage"], "DELIVER")
            self.assertTrue(
                construction["interaction"]["automatic_continuation_allowed"]
            )

            tasks_path = deliver_project / "docs/project/TASKS.md"
            valid_tasks = tasks_path.read_text(encoding="utf-8")
            malformed_tasks = valid_tasks.replace(
                "- Status: `READY`", "- Status: `BROKEN`", 1
            )
            self.assertNotEqual(malformed_tasks, valid_tasks)
            tasks_path.write_text(malformed_tasks, encoding="utf-8")

            generated_defect = doctor.inspect_project(deliver_project)
            self.assertFalse(generated_defect["ok"])
            defect_item = next(
                item
                for item in generated_defect["remediation"]["items"]
                if item["diagnostic_code"] == "TASK_GRAPH_INVALID"
            )
            self.assertEqual(defect_item["responsible_party"], "CODEX")
            self.assertEqual(defect_item["category"], "AGENT_CORRECTION")
            self.assertTrue(defect_item["automatic_correction_allowed"])
            self.assertEqual(
                generated_defect["remediation"]["next_action"]["action_kind"],
                "CORRECT_AND_REVALIDATE",
            )
            self.assertFalse(
                generated_defect["interaction"]["owner_action_required"]
            )
            repair_update = presenter.render_owner_update(generated_defect)
            self.assertIn("Need from you: Nothing.", repair_update)
            self.assertIn("Codex will correct", repair_update)

            tasks_path.write_text(valid_tasks, encoding="utf-8")
            after_repair = doctor.inspect_project(deliver_project)
            self.assertTrue(after_repair["ok"], after_repair["diagnostics"])
            self.assertTrue(
                after_repair["interaction"]["automatic_continuation_allowed"]
            )

    def test_hook_preserves_documentation_and_distinct_aws_authority_lanes(self) -> None:
        documentation = hook_fixtures.fastlane_hook.handle_event(
            "pre-tool-use",
            hook_fixtures.payload(
                "PreToolUse",
                REPOSITORY_ROOT,
                tool_name="aws___search_documentation",
                tool_input={"query": "Lambda security guidance"},
            ),
            root=REPOSITORY_ROOT,
            doctor_report=hook_fixtures.report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIsNone(documentation)

        no_authority = hook_fixtures.fastlane_hook.handle_event(
            "pre-tool-use",
            hook_fixtures.payload(
                "PreToolUse",
                REPOSITORY_ROOT,
                tool_name="aws___call_aws",
                tool_input=hook_fixtures.aws_request("CreateStack"),
            ),
            root=REPOSITORY_ROOT,
            doctor_report=hook_fixtures.report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "external authority is absent",
            no_authority["hookSpecificOutput"]["permissionDecisionReason"],
        )

        lanes = (
            ("FAST_DEV_GATE_B", "CreateStack", "AUTH-0001"),
            ("AWS_DEPLOYMENT", "UpdateStack", "AWS-AUTH-0001"),
            ("AWS_TEARDOWN", "DeleteStack", "TEARDOWN-AUTH-0001"),
        )
        for kind, operation, authorization_id in lanes:
            with self.subTest(kind=kind):
                external = hook_fixtures.authority(
                    kind, [f"cloudformation:{operation}"],
                    authorization_id=authorization_id,
                )
                allowed = hook_fixtures.fastlane_hook.handle_event(
                    "permission-request",
                    hook_fixtures.payload(
                        "PermissionRequest",
                        REPOSITORY_ROOT,
                        tool_name="aws___call_aws",
                        tool_input=hook_fixtures.aws_request(operation),
                    ),
                    root=REPOSITORY_ROOT,
                    doctor_report=hook_fixtures.report(
                        aws=authorization_id, external_authority=external
                    ),
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIsNone(allowed)

        deployment = hook_fixtures.authority(
            "AWS_DEPLOYMENT",
            ["cloudformation:UpdateStack"],
            authorization_id="AWS-AUTH-0001",
        )
        denied_teardown = hook_fixtures.fastlane_hook.handle_event(
            "pre-tool-use",
            hook_fixtures.payload(
                "PreToolUse",
                REPOSITORY_ROOT,
                tool_name="aws___call_aws",
                tool_input=hook_fixtures.aws_request("DeleteStack"),
            ),
            root=REPOSITORY_ROOT,
            doctor_report=hook_fixtures.report(
                aws="AWS-AUTH-0001", external_authority=deployment
            ),
            envelope={
                "AWS boundary": "MUTATE_LISTED_RESOURCES",
                "GitHub boundary": "NONE",
            },
        )
        self.assertIn(
            "distinct current teardown receipt",
            denied_teardown["hookSpecificOutput"]["permissionDecisionReason"],
        )

        reviewed_script = "print('reviewed Fastlane deployment')"
        reviewed = hook_fixtures.reviewed_authority(reviewed_script)
        self.assertIsNone(
            hook_fixtures.fastlane_hook.handle_event(
                "permission-request",
                hook_fixtures.payload(
                    "PermissionRequest",
                    REPOSITORY_ROOT,
                    tool_name="aws___run_script",
                    tool_input={"script": reviewed_script, "aws_profile": "fastlane-role"},
                ),
                root=REPOSITORY_ROOT,
                doctor_report=hook_fixtures.report(
                    aws="AWS-AUTH-0001", external_authority=reviewed
                ),
                envelope={
                    "AWS boundary": "MUTATE_LISTED_RESOURCES",
                    "GitHub boundary": "NONE",
                },
            )
        )
        opaque = hook_fixtures.fastlane_hook.handle_event(
            "pre-tool-use",
            hook_fixtures.payload(
                "PreToolUse",
                REPOSITORY_ROOT,
                tool_name="aws___run_script",
                tool_input={"description": "deploy the stack"},
            ),
            root=REPOSITORY_ROOT,
            doctor_report=hook_fixtures.report(
                aws="AWS-AUTH-0001", external_authority=reviewed
            ),
            envelope={
                "AWS boundary": "MUTATE_LISTED_RESOURCES",
                "GitHub boundary": "NONE",
            },
        )
        self.assertIn("blocked", opaque["hookSpecificOutput"]["permissionDecisionReason"])

    def test_failed_task_evidence_cannot_produce_false_done(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = task_fixtures.initialize_git(root)
            tasks_text = task_fixtures.document(
                [task_fixtures.task_block("TASK-001", "READY")],
                snapshot_text=task_fixtures.snapshot(
                    baseline_commit=commit,
                    last_known_green_commit=commit,
                    protected_dirty_paths="NONE",
                ),
            )
            tasks_path, state_path = task_fixtures.write_task_project(root, tasks_text)
            task_waves.mutate_run_snapshot(
                tasks_path,
                operation="start",
                run_id="RUN-0001",
                coordinator="lead",
                run_mode="SINGLE_TASK",
            )
            task_waves.claim_task_file(
                tasks_path,
                "TASK-001",
                owner="worker-a",
                coordinator="lead",
                run_id="RUN-0001",
                checkpoint="CP-0000",
            )
            tasks_path.write_text(
                task_fixtures.observed_task_text(
                    tasks_path.read_text(encoding="utf-8")
                ),
                encoding="utf-8",
            )

            verify_path = root / "VERIFY.md"
            failure = task_fixtures.completion_evidence_row(
                evidence_id="EV-0001",
                result="exit=1; 1 focused test failed",
                status="FAILED",
            )
            verify_path.write_text(
                task_fixtures.completion_evidence_document(failure),
                encoding="utf-8",
            )
            original_tasks = tasks_path.read_text(encoding="utf-8")
            original_state = state_path.read_text(encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "LOCAL_PASS or VERIFIED"):
                task_waves.update_task_file(
                    tasks_path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-0001",
                    run_id="RUN-0001",
                    checkpoint="CP-0001",
                )
            self.assertEqual(tasks_path.read_text(encoding="utf-8"), original_tasks)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)

            success = task_fixtures.completion_evidence_row(
                evidence_id="EV-0002",
                result="exit=0; focused test passed",
                observed_at="2026-07-17T00:01:00+00:00",
                durable_source="VERIFY.md#ev-0002",
                status="LOCAL_PASS",
            )
            verify_path.write_text(
                task_fixtures.completion_evidence_document(failure, success),
                encoding="utf-8",
            )
            task_waves.update_task_file(
                tasks_path,
                "TASK-001",
                coordinator="lead",
                status="DONE",
                evidence="EV-0002",
                run_id="RUN-0001",
                checkpoint="CP-0001",
            )
            completed = task_waves.parse_tasks(
                tasks_path.read_text(encoding="utf-8")
            )[0]
            self.assertEqual(completed.status, "DONE")
            self.assertIn("EV-0001", verify_path.read_text(encoding="utf-8"))


    def test_partial_high_risk_intake_remains_a_plain_owner_consultation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.extract_template(Path(directory), "partial-intake")
            self.initialize(project)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            for label, value in (
                ("Project mode", "`greenfield`"),
                ("Delivery profile", "`high-risk`"),
                ("Effective risk", "`high`"),
            ):
                text = doctor_fixtures.set_table_value(
                    text,
                    "## Document status",
                    "## 1. Workload profile",
                    label,
                    value,
                )
            prd_path.write_text(text, encoding="utf-8")
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"].update(
                {
                    "mode": "greenfield",
                    "delivery_profile": "high-risk",
                    "effective_risk": "high",
                    "brownfield_baseline": "NOT_APPLICABLE",
                }
            )
            state_path.write_text(json.dumps(state), encoding="utf-8")

            report = doctor.inspect_project(project)
            rendered = presenter.render_owner_update(report)

        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["next_prompt"], "INTAKE-10")
        self.assertEqual(report["interaction"]["state"], "NEEDS_INPUT")
        self.assertEqual(
            report["interaction"]["owner_action_kind"], "ANSWER_OPEN_DECISIONS"
        )
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn("next one to three project questions", rendered)
        self.assertNotIn("validation boundary", rendered)
        self.assertNotIn("Welcome to AWS Codex Fastlane", rendered)

if __name__ == "__main__":
    unittest.main()
