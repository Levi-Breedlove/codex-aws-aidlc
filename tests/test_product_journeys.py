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
from tests import test_fastlane_presenter as presenter_fixtures
from tests import test_setup_assistant as setup_fixtures
from tests import test_task_waves as task_fixtures

import bootstrap_doctor as doctor
import fastlane_owner_briefs as briefs
import fastlane_presenter as presenter
import fastlane_context as context_runtime
import package_release
import setup_assistant as setup
import task_waves
from scripts.fastlane_engine import api as engine_api


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
                "--prerequisite-report-stdin",
            ],
            cwd=project,
            input=json.dumps(setup.reduce_prerequisites(setup_fixtures.local_ready())),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def make_gate_a_pending(self, project: Path) -> None:
        """Create complete requirements that still await Gate A approval."""

        fixture = doctor_fixtures.BootstrapDoctorTests()
        fixture.approve_project(project, gate_b=False)
        fixture.set_non_material_req_evidence(project)
        prd_path = project / "docs/project/PRD.md"
        text = prd_path.read_text(encoding="utf-8")
        text = doctor_fixtures.set_table_value(
            text,
            "## Document status",
            "## 1. Workload profile",
            "Gate A derived status",
            "`PENDING_OWNER_APPROVAL`",
        )
        for field, value in {
            "Approver": "TODO",
            "Owner decision": "`PENDING`",
            "Authorized requirements revision": "`TODO`",
            "Authorized cost posture": "`TODO`",
            "Explicitly accepted assumption IDs": "`TODO`",
            "Authorization provided at": "`TODO`",
            "Authorization source": "`TODO`",
            "Verbatim owner receipt": "`PENDING`",
            "Derived Gate A state": "`PENDING_OWNER_APPROVAL`",
        }.items():
            text = doctor_fixtures.set_table_value(
                text,
                "### Gate A — owner acceptance record",
                "### Gate A validation and invalidation rules",
                field,
                value,
            )
        text = doctor_fixtures.set_receipt(
            text,
            "gate-a",
            "\n".join(
                [
                    "APPROVE REQUIREMENTS GATE A",
                    "Requirements revision: REQ-0001",
                    "Cost posture: MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                    "Accepted assumptions: NONE",
                    "Approver: <name/handle>",
                ]
            ),
        )
        prd_path.write_text(text, encoding="utf-8")
        state_path = project / "bootstrap.yaml"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["lifecycle"]["gate_a"] = "PENDING_OWNER_APPROVAL"
        state["lifecycle"]["gate_b"] = "BLOCKED"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        doctor_fixtures.refresh_document_summaries(project)

    def authorize_issue_sync(self, project: Path) -> dict[str, str]:
        """Allow issue synchronization while keeping merge prohibited."""

        prd_path = project / "docs/project/PRD.md"
        text = prd_path.read_text(encoding="utf-8")
        for field, value in {
            "GitHub boundary": "`ISSUES`",
            "GitHub repository, branch, and merge constraints": (
                "`REPO: Levi-Breedlove/aws-bootstrap; "
                "BRANCH: fast-lane; MERGE: PROHIBITED`"
            ),
        }.items():
            text = doctor_fixtures.set_table_value(
                text,
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                field,
                value,
            )
        text = doctor_fixtures.rebind_gate_b_envelope(text)
        prd_path.write_text(text, encoding="utf-8")
        return doctor.table_after_heading(text, "## 28. Construction envelope")

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

    def append_checkpoint_row(self, tasks_path: Path, row: str) -> None:
        text = tasks_path.read_text(encoding="utf-8")
        heading_start = text.index("## Checkpoints and resume")
        table_start = text.index("| Checkpoint |", heading_start)
        table_end = text.index("\n\n", table_start)
        table = text[table_start:table_end]
        tasks_path.write_text(
            text[:table_start] + table.rstrip() + "\n" + row + text[table_end:],
            encoding="utf-8",
        )

    def test_extracted_template_setup_initializes_once_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            project = self.extract_template(temporary, "fresh")
            self.assertTrue((project / "app").is_dir())
            app_readme = (project / "app/README.md").read_text(encoding="utf-8")
            self.assertIn("single application-code root", app_readme)
            self.assertIn("parallel top-level `apps/` or `src/`", app_readme)
            self.assertFalse((project / "app/AGENTS.md").exists())
            self.assertFalse((project / "apps").exists())

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
            self.assertEqual(untouched["document_summaries"]["schema_version"], 1)
            self.assertEqual(untouched["document_summaries"]["status"], "CURRENT")
            self.assertEqual(len(untouched["document_summaries"]["documents"]), 6)
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
                    "FASTLANE:DOCUMENT_SUMMARY" in selected,
                    False,
                )
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
            self.assertEqual(
                first_resume["document_summaries"],
                second_resume["document_summaries"],
            )
            self.assertEqual(first_resume["document_summaries"]["schema_version"], 1)
            self.assertEqual(first_resume["document_summaries"]["status"], "STALE")
            without_summaries = json.loads(json.dumps(first_resume))
            without_summaries.pop("document_summaries")
            self.assertEqual(
                presenter.render_owner_update(first_resume),
                presenter.render_owner_update(without_summaries),
            )
            foundation = first_resume["intake_foundation"]
            self.assertEqual(foundation["schema_version"], 2)
            self.assertEqual(foundation["current_understanding"], [])
            self.assertEqual(foundation["repository_mode"], "GREENFIELD")
            self.assertIsNone(foundation["owner_work_context"])
            self.assertEqual(foundation["status"], "FOUNDATION_REQUIRED")
            self.assertEqual(
                foundation["next_question_guidance"]["status"],
                "STARTING_POINT_REQUIRED",
            )
            self.assertEqual(
                foundation["next_question_guidance"]["target_ids"],
                ["INTAKE-0001"],
            )
            self.assertFalse(
                foundation["project_configuration"]["owner_action_required"]
            )
            self.assertEqual(
                foundation["project_configuration"]["safest_current_aws_lane"],
                "documentation-only",
            )
            self.assertTrue(first_resume["interaction"]["turn_boundary_required"])
            self.assertEqual(foundation, second_resume["intake_foundation"])
            card = foundation["pending_card"]
            self.assertEqual(len(card["questions"]), 1)
            self.assertFalse(card["accept_all_allowed"])
            self.assertEqual(
                card["owner_reply"],
                "1: <choose A, B, or C>",
            )
            self.assertEqual(
                card["exact_reply"],
                f"{card['reply_token']}; {card['owner_reply']}",
            )
            project_ready = presenter.render_project_ready(first_resume)
            self.assertTrue(project_ready.startswith("FASTLANE · PROJECT READY"))
            self.assertIn("Journey Test Project is initialized", project_ready)
            self.assertIn("Preferred AWS Region: `us-west-2`", project_ready)
            self.assertIn("AWS account access: Not authorized.", project_ready)
            self.assertIn("How consultation works", project_ready)
            self.assertEqual(project_ready.count("Need from you:"), 1)
            self.assertIn(
                "1. What kind of project are we starting together?", project_ready
            )
            resumed = presenter.render_owner_update(first_resume)
            self.assertNotIn("What Fastlane already knows", resumed)
            self.assertIn("Why this matters", resumed)
            self.assertIn("1. What kind of project are we starting together?", resumed)
            self.assertIn("A. A new application", resumed)
            self.assertIn("B. A change to an existing application", resumed)
            self.assertIn("C. A repair", resumed)
            self.assertIn(
                "No recommendation\u2014choose the option that matches your situation.",
                resumed,
            )
            self.assertNotIn("Accept all recommendations.", resumed)
            self.assertNotIn("INTAKE-CARD", resumed)
            self.assertNotIn(str(card["reply_token"]), resumed)
            for internal_configuration in (
                "Project configuration",
                "Delivery profile",
                "Effective risk",
                "AWS lane",
                "Documentation-only",
                "Explicit-gate",
            ):
                self.assertNotIn(internal_configuration, resumed)
            parsed = doctor.parse_intake_owner_response(
                "A",
                card,
                expected_card_id=str(card["card_id"]),
                expected_revision=int(card["revision"]),
                expected_sha256=str(card["canonical_sha256"]),
                owner_response_id="OWNER-MSG-0001",
            )
            self.assertEqual(parsed.status, "PASS", parsed.to_dict())
            self.assertEqual(parsed.unresolved_reply_keys, ())
            self.assertEqual(resumed.count("Need from you:"), 1)
            for setup_text in (
                "FASTLANE · WELCOME",
                "Welcome to Fastlane.",
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

    def test_owner_briefs_and_diagrams_use_real_project_artifacts(self) -> None:
        fixture = doctor_fixtures.BootstrapDoctorTests()

        def verify_source_locators(project: Path, brief: dict[str, object]) -> None:
            locators = brief["source_locators"]
            self.assertTrue(locators)
            locator_keys = {locator["key"] for locator in locators}
            hidden_machine_headings = {
                "Technology and toolchain decision register",
                "Gate B Harness Profile",
                "28. Construction envelope",
            }
            for locator in locators:
                self.assertEqual(locator["path"], "docs/project/PRD.md")
                self.assertNotIn(locator["heading"], hidden_machine_headings)
                source = (project / locator["path"]).read_text(encoding="utf-8")
                depth = 0
                for line in source.splitlines()[: locator["start_line"] - 1]:
                    depth += line.strip() == "<details>"
                    depth -= line.strip() == "</details>"
                self.assertEqual(depth, 0, locator)
                selected = "\n".join(
                    source.splitlines()[locator["start_line"] - 1 : locator["end_line"]]
                )
                canonical = context_runtime.canonical_source_bytes(selected)
                self.assertEqual(
                    locator["section_sha256"],
                    "sha256:" + hashlib.sha256(canonical).hexdigest(),
                )
            decision_ids: list[str] = []
            for group in brief.get("technical_decision_groups", []):
                for decision in group["decisions"]:
                    decision_ids.append(decision["decision_id"])
                    self.assertTrue(decision["source_locator_keys"])
                    self.assertTrue(
                        set(decision["source_locator_keys"]).issubset(locator_keys),
                        decision,
                    )
            self.assertEqual(len(decision_ids), len(set(decision_ids)))

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)

            gate_a_project = self.extract_template(temporary, "gate-a-brief")
            self.initialize(gate_a_project)
            fixture.pending_gate_a(gate_a_project)
            gate_a = doctor.inspect_project(gate_a_project)
            self.assertTrue(gate_a["ok"], gate_a["diagnostics"])
            gate_a_brief = gate_a["owner_decision_brief"]
            self.assertEqual(gate_a_brief["kind"], "GATE_A")
            self.assertEqual(gate_a_brief["status"], "READY")
            self.assertTrue(gate_a_brief["formal_receipt_required"])
            self.assertTrue(gate_a_brief["canonical_sha256"])
            verify_source_locators(gate_a_project, gate_a_brief)
            gate_a_inventory = gate_a["owner_decision_inventory"]
            self.assertEqual(gate_a_inventory["kind"], "GATE_A")
            self.assertEqual(gate_a_inventory["status"], "READY")
            gate_a_decision_ids = [
                decision["decision_id"] for decision in gate_a_inventory["decisions"]
            ]
            self.assertEqual(len(gate_a_decision_ids), len(set(gate_a_decision_ids)))
            self.assertTrue(
                set(gate_a["intake_foundation"]["basis_ids"]).issubset(
                    gate_a_decision_ids
                )
            )
            rendered_gate_a = presenter.render_owner_decision_brief(gate_a, "GATE_A")
            self.assertIn("Gate A Owner Decision Brief", rendered_gate_a)
            self.assertIn("## Your recorded decisions", rendered_gate_a)
            self.assertIn("First-release journey: JOURNEY-001", rendered_gate_a)
            self.assertIn("Not authorized", rendered_gate_a)
            for locator in gate_a_brief["source_locators"]:
                anchor = presenter._markdown_anchor(str(locator["heading"]))
                self.assertIn(f"({locator['path']}#{anchor})", rendered_gate_a)

            confirmation = gate_a["owner_answer_confirmation"]
            self.assertEqual(confirmation["status"], "READY")
            rendered_confirmation = presenter.render_answer_confirmation(
                gate_a, confirmation["owner_response_id"]
            )
            self.assertIn("Recorded:", rendered_confirmation)
            self.assertIn("Project effect:", rendered_confirmation)
            self.assertIn("Correct it:", rendered_confirmation)
            with self.assertRaises(presenter.PresentationError):
                presenter.render_answer_confirmation(gate_a, "OWNER-MSG-0001")

            gate_b_project = self.extract_template(temporary, "gate-b-brief")
            self.initialize(gate_b_project)
            fixture.pending_gate_b(gate_b_project)
            gate_b = doctor.inspect_project(gate_b_project)
            self.assertTrue(gate_b["ok"], gate_b["diagnostics"])
            gate_b_brief = gate_b["owner_decision_brief"]
            self.assertEqual(gate_b_brief["kind"], "GATE_B")
            self.assertEqual(gate_b_brief["status"], "READY")
            self.assertTrue(gate_b_brief["technical_decision_groups"])
            verify_source_locators(gate_b_project, gate_b_brief)
            rendered_gate_b = presenter.render_owner_decision_brief(gate_b, "GATE_B")
            self.assertIn("Gate B Technical Owner Decision Brief", rendered_gate_b)
            self.assertIn("Technical decision index", rendered_gate_b)
            navigation_keys = set(briefs.GATE_B_NAVIGATION_LOCATOR_KEYS)
            self.assertTrue(
                navigation_keys.issubset(
                    {locator["key"] for locator in gate_b_brief["source_locators"]}
                )
            )
            expected_diagram_links = (
                "[View the complete proposed architecture]"
                "(docs/project/PRD.md#proposed-system-at-a-glance)",
                "[View the AWS implementation diagram]"
                "(docs/project/PRD.md#aws-implementation-at-a-glance)",
                "[Browse all project diagrams](docs/project/PRD.md#diagram-guide)",
            )
            link_positions = [
                rendered_gate_b.index(link) for link in expected_diagram_links
            ]
            self.assertEqual(link_positions, sorted(link_positions))
            for link in expected_diagram_links:
                self.assertEqual(rendered_gate_b.count(link), 1)
            extracted_presenter = subprocess.run(
                [
                    sys.executable,
                    "scripts/fastlane_presenter.py",
                    "gate-b-brief",
                    "--input-stdin",
                ],
                cwd=gate_b_project,
                input=json.dumps({"report": gate_b}),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                extracted_presenter.returncode, 0, extracted_presenter.stderr
            )
            self.assertEqual(extracted_presenter.stderr, "")
            for link in expected_diagram_links:
                self.assertIn(link, extracted_presenter.stdout)
            self.assertFalse((gate_b_project / ".codex/hooks.json").exists())
            self.assertIn(
                "(docs/project/PRD.md#20-aws-implementation-approach)",
                rendered_gate_b,
            )
            for label in (
                "Meaning and selection:",
                "Basis and rationale:",
                "Alternatives and tradeoffs:",
                "Risks and safeguards:",
                "Evidence and revisit trigger:",
                "Exact source:",
            ):
                self.assertIn(label, rendered_gate_b)
            self.assertIn("Change the design: <correction>.", rendered_gate_b)
            self.assertIn(
                "begins bounded local construction automatically",
                rendered_gate_b,
            )
            for locator in gate_b_brief["source_locators"]:
                anchor = presenter._markdown_anchor(str(locator["heading"]))
                self.assertIn(f"({locator['path']}#{anchor})", rendered_gate_b)
            gate_b_inventory = gate_b["owner_decision_inventory"]
            self.assertEqual(gate_b_inventory["kind"], "GATE_B")
            self.assertEqual(gate_b_inventory["status"], "READY")
            self.assertEqual(
                gate_b_inventory["required_domains"],
                list(briefs.TECHNICAL_DOMAIN_ORDER),
            )
            actual_decisions = [
                decision["decision_id"]
                for group in gate_b_brief["technical_decision_groups"]
                for decision in group["decisions"]
            ]
            self.assertEqual(len(actual_decisions), len(set(actual_decisions)))
            self.assertEqual(
                actual_decisions,
                [item["decision_id"] for item in gate_b_inventory["decisions"]],
            )
            self.assertEqual(
                [item["domain"] for item in gate_b_inventory["decisions"]],
                list(briefs.TECHNICAL_DOMAIN_ORDER),
            )
            self.assertLessEqual(
                len([line for line in rendered_gate_b.splitlines() if line.strip()]),
                140,
            )
            self.assertIn("Application And Runtime", rendered_gate_b)
            self.assertIn(
                "Application source: GREENFIELD_APP_ROOT: app/**", rendered_gate_b
            )
            design_contract = gate_b["design_contract"]

            diagram_contract = design_contract["diagram_contract"]
            self.assertEqual(diagram_contract["schema_version"], 1)
            self.assertEqual(diagram_contract["status"], "CURRENT")
            records = {item["kind"]: item for item in diagram_contract["records"]}
            for kind in ("SYSTEM_CONTEXT", "PRIMARY_OUTCOME", "AWS_IMPLEMENTATION"):
                self.assertEqual(records[kind]["applicability"], "REQUIRED")
                self.assertEqual(records[kind]["status"], "CURRENT")
                self.assertRegex(
                    records[kind]["semantic_sha256"], r"^sha256:[0-9a-f]{64}$"
                )
                self.assertRegex(
                    records[kind]["rendered_sha256"], r"^sha256:[0-9a-f]{64}$"
                )
            prd_text = (gate_b_project / "docs/project/PRD.md").read_text(
                encoding="utf-8"
            )
            for forbidden_label in (
                '["ACT-001"]',
                '["API-001"]',
                '["STATE-001"]',
                '["TECH-0001"]',
            ):
                self.assertNotIn(forbidden_label, prd_text)
            for selected_service in (
                "Python 3.12 on AWS Lambda",
                "Amazon API Gateway regional HTTPS endpoint",
                "Amazon Cognito with server-side authorization",
                "Amazon DynamoDB with per-owner records",
                "Amazon CloudWatch logs, metrics, and alarms",
            ):
                self.assertIn(selected_service, prd_text)

    def test_extracted_brownfield_and_infrastructure_only_reach_task_readiness(
        self,
    ) -> None:
        fixture = doctor_fixtures.BootstrapDoctorTests()
        cases = (
            (
                "brownfield-feature",
                "FEATURE",
                "legacy/existing.txt",
                "preserved legacy behavior\n",
                {"kind": "BROWNFIELD_PRESERVE", "paths": ["legacy/**"]},
                ["legacy/**", "tests/**", "dist/architecture/**"],
            ),
            (
                "infrastructure-only",
                "INFRASTRUCTURE",
                "infrastructure/template.yaml",
                "Resources: {}\n",
                {"kind": "NOT_APPLICABLE", "paths": []},
                ["infrastructure/**", "tests/**", "dist/architecture/**"],
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            for (
                name,
                work_kind,
                protected_path,
                protected_source,
                expected_disposition,
                expected_roots,
            ) in cases:
                with self.subTest(work_kind=work_kind):
                    project = self.extract_template(temporary, name)
                    self.initialize(project)
                    protected = project / protected_path
                    protected.parent.mkdir(parents=True, exist_ok=True)
                    protected.write_text(protected_source, encoding="utf-8")

                    baseline = fixture.approve_existing_project(
                        project,
                        work_kind=work_kind,
                        architecture_board=True,
                    )
                    exit_code, report = self.run_doctor_cli(project)

                    self.assertEqual(exit_code, 0, report["diagnostics"])
                    self.assertTrue(report["ok"], report["diagnostics"])
                    self.assertEqual(report["classification"], "ACTIVE_BROWNFIELD")
                    self.assertEqual(report["lifecycle_state"], "TASK_PLAN_REQUIRED")
                    self.assertEqual(report["next_prompt"], "TASK-10")
                    self.assertEqual(report["diagnostics"], [])
                    self.assertEqual(report["coverage_plan"]["work_kind"], work_kind)
                    design = report["design_contract"]
                    self.assertEqual(design["status"], "READY")
                    self.assertEqual(design["change_impact"]["status"], "READY")
                    self.assertEqual(
                        design["diagram_contract"]["status"],
                        "CURRENT",
                    )
                    self.assertIsNone(design["project_contract"]["first_wave"])
                    self.assertEqual(
                        design["application_source_disposition"],
                        expected_disposition,
                    )
                    self.assertEqual(
                        report["write_authority"]["approved_write_roots"],
                        expected_roots,
                    )
                    self.assertNotIn(
                        "app/**",
                        report["write_authority"]["approved_write_roots"],
                    )
                    self.assertEqual(report["authorizations"]["aws"], "NONE")
                    self.assertEqual(report["external_authority"]["kind"], "NONE")
                    handoff = engine_api.derive_architecture_board_handoff(report)
                    self.assertTrue(handoff["eligible"], handoff["issues"])
                    self.assertEqual(handoff["aws_authority"], "NONE")
                    self.assertEqual(
                        protected.read_text(encoding="utf-8"), protected_source
                    )
                    self.assertEqual(
                        subprocess.run(
                            ["git", "-C", str(project), "rev-parse", "HEAD"],
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout.strip(),
                        baseline,
                    )

                    task_path = (
                        "infrastructure/template.yaml"
                        if work_kind == "INFRASTRUCTURE"
                        else "legacy/change.py"
                    )
                    task_design = (
                        "DES-0001; TECH: TECH-0004, TECH-0007, TECH-0009, TECH-0015"
                        if work_kind == "INFRASTRUCTURE"
                        else "DES-0001; TECH: TECH-0001, TECH-0007"
                    )
                    fixture.initialize_task_plan(
                        project,
                        doctor_fixtures.ready_task(
                            task_path,
                            requirements=(
                                f"{doctor_fixtures.MODERN_TASK_REQUIREMENT_TRACE}; "
                                "PROP-001"
                            ),
                            design=task_design,
                            command="python -m unittest tests.test_properties",
                            property_projection=(
                                doctor_fixtures.property_execution_projection()
                            ),
                        ),
                    )
                    doctor_fixtures.refresh_document_summaries(project)
                    build_exit, build_report = self.run_doctor_cli(project)

                    self.assertEqual(build_exit, 0, build_report["diagnostics"])
                    self.assertTrue(build_report["ok"], build_report["diagnostics"])
                    self.assertEqual(
                        (build_report["lifecycle_state"], build_report["next_prompt"]),
                        ("CONSTRUCTION_SINGLE", "BUILD-10"),
                    )
                    self.assertEqual(build_report["tasks"]["ready"], 1)
                    self.assertEqual(build_report["tasks"]["ready_ids"], ["TASK-001"])
                    owner_update = presenter.render_owner_update(build_report)
                    self.assertIn("TASK-001 is ready next", owner_update)
                    self.assertIn("Need from you: Nothing.", owner_update)
                    self.assertIn(
                        "Next: Codex will continue with TASK-001.", owner_update
                    )
                    self.assertEqual(
                        build_report["authorizations"]["construction"], "AUTH-0001"
                    )
                    self.assertEqual(build_report["authorizations"]["aws"], "NONE")
                    self.assertEqual(build_report["external_authority"]["kind"], "NONE")
                    self.assertEqual(
                        build_report["write_authority"]["approved_write_roots"],
                        expected_roots,
                    )
                    self.assertEqual(
                        build_report["design_contract"][
                            "application_source_disposition"
                        ],
                        expected_disposition,
                    )
                    self.assertEqual(
                        build_report["design_contract"]["diagram_contract"]["status"],
                        "CURRENT",
                    )
                    migration = next(
                        record
                        for record in build_report["design_contract"][
                            "diagram_contract"
                        ]["records"]
                        if record["kind"] == "MIGRATION"
                    )
                    self.assertEqual(migration["status"], "CURRENT")
                    self.assertIn("PRES-001", migration["basis_ids"])
                    self.assertEqual(
                        protected.read_text(encoding="utf-8"), protected_source
                    )
                    self.assertEqual(
                        subprocess.run(
                            ["git", "-C", str(project), "rev-parse", "HEAD"],
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout.strip(),
                        baseline,
                    )

    def test_extracted_task_coverage_gap_renders_automatic_replan(self) -> None:
        fixture = doctor_fixtures.BootstrapDoctorTests()
        with tempfile.TemporaryDirectory() as directory:
            project = self.extract_template(Path(directory), "task-replan")
            self.initialize(project)
            protected = project / "legacy/existing.txt"
            protected.parent.mkdir(parents=True, exist_ok=True)
            protected.write_text("preserved legacy behavior\n", encoding="utf-8")
            fixture.approve_existing_project(project, work_kind="FEATURE")
            fixture.initialize_task_plan(
                project,
                doctor_fixtures.ready_task(
                    "legacy/change.py",
                    requirements=(
                        f"{doctor_fixtures.MODERN_TASK_REQUIREMENT_TRACE}; PROP-001"
                    ),
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    command="python -m unittest tests.test_properties",
                    property_projection=(
                        doctor_fixtures.property_execution_projection()
                    ),
                ),
            )
            doctor_fixtures.refresh_document_summaries(project)
            current = doctor.inspect_project(project)
            self.assertTrue(current["ok"], current["diagnostics"])
            self.assertEqual(current["authorizations"]["construction"], "AUTH-0001")

            tasks_path = project / "docs/project/TASKS.md"
            tasks = tasks_path.read_text(encoding="utf-8")
            coverage_gap = tasks.replace(
                f"{doctor_fixtures.MODERN_TASK_REQUIREMENT_TRACE}; PROP-001",
                "REQ-0001; PROP-001",
                1,
            )
            self.assertNotEqual(coverage_gap, tasks)
            tasks_path.write_text(coverage_gap, encoding="utf-8")
            doctor_fixtures.refresh_document_summaries(project)
            replan = doctor.inspect_project(project)

        self.assertFalse(replan["ok"])
        self.assertEqual(
            replan["interaction"]["route_reason_code"],
            "TASK_REPLAN_REQUIRED",
        )
        self.assertEqual(
            replan["remediation"]["next_action"]["action_kind"],
            "REPLAN_TASKS",
        )
        self.assertTrue(replan["remediation"]["next_action"]["preserve_done_evidence"])
        self.assertEqual(replan["authorizations"]["construction"], "NONE")
        self.assertEqual(replan["authorizations"]["aws"], "NONE")
        self.assertEqual(replan["external_authority"]["kind"], "NONE")
        replan_update = presenter.render_owner_update(replan)
        self.assertIn("Need from you: Nothing.", replan_update)
        self.assertIn("preserve completed evidence", replan_update)

    def test_gate_evidence_and_construction_routes_use_real_project_artifacts(
        self,
    ) -> None:
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
            after_gate_a_update = presenter.render_owner_update(
                after_gate_a, updated="Gate A was approved."
            )
            self.assertIn("(docs/project/PRD.md#gate-a-review)", after_gate_a_update)
            self.assertIn("(docs/project/PRD.md#technical-plan)", after_gate_a_update)

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
            fixture.approve_project(
                deliver_project, gate_b=True, architecture_board=True
            )
            current = doctor.inspect_project(deliver_project)
            self.assertTrue(current["ok"], current["diagnostics"])
            self.assertEqual(current["next_prompt"], "TASK-10")
            self.assertTrue(current["interaction"]["automatic_continuation_allowed"])
            after_gate_b_update = presenter.render_owner_update(
                current, updated="Gate B was approved."
            )
            self.assertIn("(docs/project/PRD.md#gate-b-review)", after_gate_b_update)
            self.assertIn(
                "(docs/project/PRD.md#proposed-system-at-a-glance)",
                after_gate_b_update,
            )
            self.assertIn(
                "(docs/project/PRD.md#aws-implementation-at-a-glance)",
                after_gate_b_update,
            )
            self.assertIn("(docs/project/PRD.md#diagram-guide)", after_gate_b_update)
            self.assertIn(
                "(docs/project/TASKS.md#current-progress)", after_gate_b_update
            )
            handoff = engine_api.derive_architecture_board_handoff(current)
            identity = {
                **presenter.ARCHITECTURE_DIAGRAM_SKILL_IDENTITY,
                "valid": True,
                "issues": [],
            }
            offer = presenter.render_architecture_board_offer(
                current, handoff, identity, transition="GATE_B_ACCEPTED"
            )
            self.assertTrue(handoff["eligible"], handoff["issues"])
            self.assertIn("Generate the planned AWS architecture board.", offer)
            self.assertIn("Need from you: Nothing.", offer)
            self.assertNotIn(
                "Optional planned architecture board",
                presenter.render_owner_update(current),
            )

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
                missing["interaction"]["owner_action_kind"],
                "NONE_CONTINUE_AUTOMATICALLY",
            )
            self.assertEqual(missing["interaction"]["owner_stage"], "DESIGN")
            repair_update = presenter.render_owner_update(missing)
            self.assertEqual(repair_update.count("Need from you:"), 1)
            self.assertIn("Need from you: Nothing.", repair_update)
            self.assertIn("Codex will correct", repair_update)
            side_answer = presenter.render_side_question_response(
                missing,
                answer="Official AWS Core evidence is needed only for this material design step.",
            )
            self.assertIn("Project state changed: No.", side_answer)
            self.assertIn("Pending next action: Nothing.", side_answer)
            self.assertIn(
                "Next: Codex will correct the reported in-scope failure and rerun "
                "validation.",
                side_answer,
            )

            verify_path.write_text(current_evidence, encoding="utf-8")
            recovered = doctor.inspect_project(deliver_project)
            self.assertTrue(recovered["ok"], recovered["diagnostics"])
            self.assertEqual(recovered["next_prompt"], "TASK-10")

            harness_projection = "\n".join(
                [
                    "| Harness ID | Layer | Selected check or tool | Trigger | Basis IDs | Exact command or API | Evidence destination | Required or conditional status |",
                    "|---|---|---|---|---|---|---|---|",
                    "| HARNESS-004 | End-to-end | unittest journey validation | NEW_BUILD first outcome | DES-0001, FR-001, JOURNEY-001, WAVE-001 | python -m unittest tests.test_product_journeys | docs/project/VERIFY.md#harness-execution-evidence | REQUIRED |",
                ]
            )
            fixture.initialize_task_plan(
                deliver_project,
                doctor_fixtures.ready_task(
                    requirements=(
                        f"{doctor_fixtures.MODERN_TASK_REQUIREMENT_TRACE}; "
                        "JOURNEY-001; WAVE-001; PROP-001"
                    ),
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    command=(
                        "python -m unittest tests.test_properties\n"
                        "python -m unittest tests.test_product_journeys"
                    ),
                    property_projection=(
                        doctor_fixtures.property_execution_projection()
                        + "\n\n"
                        + harness_projection
                    ),
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
            self.assertFalse(generated_defect["interaction"]["owner_action_required"])
            repair_update = presenter.render_owner_update(generated_defect)
            self.assertIn("Need from you: Nothing.", repair_update)
            self.assertIn("Codex will correct", repair_update)

            tasks_path.write_text(valid_tasks, encoding="utf-8")
            after_repair = doctor.inspect_project(deliver_project)
            self.assertTrue(after_repair["ok"], after_repair["diagnostics"])
            self.assertTrue(
                after_repair["interaction"]["automatic_continuation_allowed"]
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(deliver_project),
                    "add",
                    "docs/project/PRD.md",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(deliver_project),
                    "commit",
                    "-qm",
                    "record approved product and design",
                ],
                check=True,
            )
            known_green = subprocess.run(
                ["git", "-C", str(deliver_project), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            tasks_text = tasks_path.read_text(encoding="utf-8")
            tasks_path.write_text(
                doctor_fixtures.set_table_value(
                    tasks_text,
                    "## Active execution snapshot",
                    "## Dependencies, waivers, and waves",
                    "Last known-green commit",
                    f"`{known_green}`",
                ),
                encoding="utf-8",
            )

            task_waves.mutate_run_snapshot(
                tasks_path,
                operation="start",
                run_id="RUN-0001",
                coordinator="codex-coordinator",
                run_mode="SINGLE_TASK",
            )
            task_waves.claim_task_file(
                tasks_path,
                "TASK-001",
                owner="codex-coordinator",
                coordinator="codex-coordinator",
                run_id="RUN-0001",
                checkpoint="CP-0000",
            )
            claimed_tasks = tasks_path.read_text(encoding="utf-8")
            task_start = claimed_tasks.index("### TASK-001")
            tasks_path.write_text(
                claimed_tasks[:task_start]
                + task_fixtures.observed_task_text(claimed_tasks[task_start:]),
                encoding="utf-8",
            )

            verify_text = verify_path.read_text(encoding="utf-8")
            completion_placeholder = (
                "| EV-0001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | "
                "`NOT_STARTED` |"
            )
            property_placeholder = (
                "| EV-0001 | TASK-0001 | REQ-0001 / DES-0001 / AUTH-0001 | "
                "PROP-001 | TECH-0007 | TODO | TODO | TODO | TODO | TODO | `NONE` | "
                "`NONE` | `NOT_STARTED` | TODO | TODO | TODO |"
            )
            harness_placeholder = (
                "| EV-0401 | HARNESS-001 | TODO | TODO | TODO | TODO | TODO | "
                "TODO | TODO | `NOT_STARTED` |"
            )
            self.assertIn(completion_placeholder, verify_text)
            self.assertIn(property_placeholder, verify_text)
            self.assertIn(harness_placeholder, verify_text)
            verify_text = (
                verify_text.replace(
                    completion_placeholder,
                    "\n".join(
                        [
                            task_fixtures.completion_evidence_row(
                                evidence_id="EV-0001",
                                command_or_observation=(
                                    "python -m unittest tests.test_properties"
                                ),
                                result="exit=0; property validation passed",
                                material=(
                                    "Worktree: abc1234; artifact: "
                                    "tests/artifacts/property-PROP-001.json"
                                ),
                                durable_source=(
                                    "tests/artifacts/property-PROP-001.json"
                                ),
                            ),
                            task_fixtures.completion_evidence_row(
                                evidence_id="EV-0401",
                                command_or_observation=(
                                    "python -m unittest tests.test_product_journeys"
                                ),
                                result="exit=0; journey validation passed",
                                material=f"Commit: {known_green}",
                                durable_source="docs/project/VERIFY.md#ev-0401",
                            ),
                        ]
                    ),
                    1,
                )
                .replace(
                    property_placeholder,
                    task_fixtures.property_evidence_row(evidence_id="EV-0001"),
                    1,
                )
                .replace(
                    harness_placeholder,
                    task_fixtures.harness_evidence_row(
                        evidence_id="EV-0401",
                        status="LOCAL_PASS",
                        observed_at="2026-07-17T00:00:00+00:00",
                        observed_result="exit=0; journey validation passed",
                        harness_id="HARNESS-004",
                        layer="End-to-end",
                        command="python -m unittest tests.test_product_journeys",
                        artifact_environment=f"Commit: {known_green}",
                    ),
                    1,
                )
            )
            verify_path.write_text(verify_text, encoding="utf-8")
            task_waves.update_task_file(
                tasks_path,
                "TASK-001",
                coordinator="codex-coordinator",
                status="DONE",
                evidence="EV-0001, EV-0401",
                run_id="RUN-0001",
                checkpoint="CP-0001",
            )

            self.append_checkpoint_row(
                tasks_path,
                task_fixtures.checkpoint_row(
                    "CP-0002",
                    commit=known_green,
                    outcomes="TASK-001 DONE attempts=1/3",
                    evidence="EV-0001, EV-0401",
                    next_action="resume the checkpointed run",
                ),
            )
            with verify_path.open("a", encoding="utf-8") as file:
                file.write("\n\n### CP-0002\n\nPause checkpoint evidence recorded.\n")
            task_waves.mutate_run_snapshot(
                tasks_path,
                operation="pause",
                run_id="RUN-0001",
                coordinator="codex-coordinator",
                checkpoint="CP-0002",
            )
            checkpointed_state = json.loads(
                (deliver_project / "bootstrap.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(checkpointed_state["execution"]["state"], "CHECKPOINTED")
            self.assertEqual(
                checkpointed_state["execution"]["last_checkpoint"]["id"],
                "CP-0002",
            )
            paused_exit, paused_report = self.run_doctor_cli(deliver_project)
            self.assertEqual(paused_exit, 0, paused_report)
            self.assertTrue(paused_report["ok"], paused_report["diagnostics"])
            self.assertEqual(
                paused_report["authorizations"]["construction"], "AUTH-0001"
            )
            self.assertEqual(paused_report["authorizations"]["aws"], "NONE")
            self.assertFalse(paused_report["interaction"]["owner_action_required"])
            self.assertTrue(paused_report["resume_safe"])
            self.assertEqual(
                (paused_report["lifecycle_state"], paused_report["next_prompt"]),
                ("RELEASE_REVIEW", "RELEASE-10"),
            )

            task_waves.mutate_run_snapshot(
                tasks_path,
                operation="resume",
                run_id="RUN-0001",
                coordinator="codex-coordinator",
            )
            self.assertEqual(
                json.loads(
                    (deliver_project / "bootstrap.yaml").read_text(encoding="utf-8")
                )["execution"]["state"],
                "RUNNING",
            )
            self.assertEqual(
                task_waves.parse_snapshot(tasks_path.read_text(encoding="utf-8")).get(
                    "Run state"
                ),
                "RUNNING",
            )
            self.append_checkpoint_row(
                tasks_path,
                task_fixtures.checkpoint_row(
                    "CP-0003",
                    commit=known_green,
                    outcomes="TASK-001 DONE attempts=1/3",
                    evidence="EV-0001, EV-0401",
                    next_action="review release readiness",
                ),
            )
            with verify_path.open("a", encoding="utf-8") as file:
                file.write(
                    "\n### CP-0003\n\nCompletion checkpoint evidence recorded.\n"
                )
            task_waves.mutate_run_snapshot(
                tasks_path,
                operation="complete",
                run_id="RUN-0001",
                coordinator="codex-coordinator",
                checkpoint="CP-0003",
            )
            release_ready = doctor.inspect_project(deliver_project)
            self.assertTrue(release_ready["ok"], release_ready["diagnostics"])
            self.assertEqual(
                (release_ready["lifecycle_state"], release_ready["next_prompt"]),
                ("RELEASE_REVIEW", "RELEASE-10"),
            )
            self.assertTrue(release_ready["resume_safe"])
            self.assertEqual(
                release_ready["interaction"]["owner_action_kind"],
                "NONE_CONTINUE_AUTOMATICALLY",
            )
            self.assertEqual(release_ready["authorizations"]["aws"], "NONE")
            self.assertEqual(
                (
                    release_ready["evidence_state"],
                    release_ready["external_authority"]["kind"],
                ),
                ("NOT_READY", "NONE"),
            )
            final_execution = json.loads(
                (deliver_project / "bootstrap.yaml").read_text(encoding="utf-8")
            )["execution"]
            self.assertEqual(final_execution["state"], "COMPLETE")
            self.assertEqual(final_execution["last_checkpoint"]["id"], "CP-0003")

    def test_gate_review_summaries_match_the_canonical_owner_action(self) -> None:
        fixture = doctor_fixtures.BootstrapDoctorTests()
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)

            gate_a_project = self.extract_template(temporary, "gate-a-summary")
            self.initialize(gate_a_project)
            fixture.pending_gate_a(gate_a_project)
            gate_a = doctor.inspect_project(gate_a_project)
            self.assertEqual(
                gate_a["interaction"]["owner_action_kind"], "APPROVE_GATE_A"
            )
            self.assertFalse(gate_a["interaction"]["automatic_continuation_allowed"])
            gate_a_documents = gate_a["document_summaries"]["documents"]
            self.assertEqual(
                {item["need_from_owner"] for item in gate_a_documents},
                {"Review the requirements and approve them or request a correction."},
            )
            self.assertEqual(
                {item["next_action"] for item in gate_a_documents},
                {
                    "After your decision, Codex will continue to technical design "
                    "or apply your correction."
                },
            )
            gate_a_prd = next(
                item
                for item in gate_a_documents
                if item["path"] == "docs/project/PRD.md"
            )
            gate_a_fields = {
                item["label"]: item["value"] for item in gate_a_prd["fields"]
            }
            prd_text = (gate_a_project / "docs/project/PRD.md").read_text(
                encoding="utf-8"
            )
            readiness = doctor.table_after_heading(
                prd_text, "### Gate A \u2014 readiness card"
            )
            self.assertEqual(
                gate_a_fields["First-release boundary"],
                readiness["Scope and non-goals"],
            )
            self.assertEqual(gate_a_fields["Updated"], "REQ-0001")
            self.assertEqual(
                gate_a_fields["Construction authorization"],
                "Not approved (boundary record AUTH-0001)",
            )

            gate_b_project = self.extract_template(temporary, "gate-b-summary")
            self.initialize(gate_b_project)
            fixture.pending_gate_b(gate_b_project)
            gate_b = doctor.inspect_project(gate_b_project)
            self.assertEqual(
                gate_b["interaction"]["owner_action_kind"], "APPROVE_GATE_B"
            )
            gate_b_documents = gate_b["document_summaries"]["documents"]
            self.assertEqual(
                {item["need_from_owner"] for item in gate_b_documents},
                {"Review the technical plan and approve it or request a correction."},
            )
            self.assertEqual(
                {item["next_action"] for item in gate_b_documents},
                {
                    "After your decision, Codex will create the construction tasks "
                    "or apply your correction."
                },
            )
            gate_b_prd = next(
                item
                for item in gate_b_documents
                if item["path"] == "docs/project/PRD.md"
            )
            gate_b_fields = {
                item["label"]: item["value"] for item in gate_b_prd["fields"]
            }
            self.assertEqual(gate_b_fields["Updated"], "DES-0001")
            self.assertEqual(
                gate_b_fields["Construction authorization"],
                "Not approved (boundary record AUTH-0001)",
            )

    def test_hook_preserves_documentation_and_distinct_aws_authority_lanes(
        self,
    ) -> None:
        hook_fixtures.fastlane_hook._clear_transition(REPOSITORY_ROOT)
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

        legacy_fast_dev = hook_fixtures.authority(
            "FAST_DEV_GATE_B", ["cloudformation:CreateStack"]
        )
        legacy_denied = hook_fixtures.fastlane_hook.handle_event(
            "pre-tool-use",
            hook_fixtures.payload(
                "PreToolUse",
                REPOSITORY_ROOT,
                tool_name="aws___call_aws",
                tool_input=hook_fixtures.aws_request("CreateStack"),
            ),
            root=REPOSITORY_ROOT,
            doctor_report=hook_fixtures.report(
                aws="AUTH-0001", external_authority=legacy_fast_dev
            ),
            envelope={
                "AWS boundary": "MUTATE_LISTED_RESOURCES",
                "GitHub boundary": "NONE",
            },
        )
        self.assertIn(
            "exact current mutation authority is absent",
            legacy_denied["hookSpecificOutput"]["permissionDecisionReason"],
        )

        lanes = (
            ("AWS_DEPLOYMENT", "UpdateStack", "AWS-AUTH-0001"),
            ("AWS_TEARDOWN", "DeleteStack", "TEARDOWN-AUTH-0001"),
        )
        for kind, operation, authorization_id in lanes:
            with self.subTest(kind=kind):
                hook_fixtures.fastlane_hook._clear_transition(REPOSITORY_ROOT)
                external = (
                    hook_fixtures.deployment_authority([f"cloudformation:{operation}"])
                    if kind == "AWS_DEPLOYMENT"
                    else hook_fixtures.authority(
                        kind,
                        [f"cloudformation:{operation}"],
                        authorization_id=authorization_id,
                    )
                )
                current = hook_fixtures.report(
                    aws=authorization_id, external_authority=external
                )
                tool_input = hook_fixtures.aws_request(operation)
                pre_event = hook_fixtures.payload(
                    "PreToolUse",
                    REPOSITORY_ROOT,
                    tool_name="aws___call_aws",
                    tool_input=tool_input,
                    session_id=f"session-{kind}",
                    turn_id=f"turn-{kind}",
                    tool_use_id=f"tool-{kind}",
                )
                event = hook_fixtures.payload(
                    "PermissionRequest",
                    REPOSITORY_ROOT,
                    tool_name="aws___call_aws",
                    tool_input=tool_input,
                    session_id=f"session-{kind}",
                    turn_id=f"turn-{kind}",
                )
                missing_started = hook_fixtures.fastlane_hook.handle_event(
                    "pre-tool-use",
                    pre_event,
                    root=REPOSITORY_ROOT,
                    doctor_report=current,
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIn(
                    "STARTED journal row",
                    missing_started["hookSpecificOutput"]["permissionDecisionReason"],
                )

                identity = hook_fixtures.fastlane_hook._tool_identity(pre_event)
                self.assertIsNotNone(identity)
                match = current["external_authority"]["request_match"]
                attempt_id = (
                    "AWS-TEARDOWN-0001" if kind == "AWS_TEARDOWN" else "AWS-DEPLOY-0001"
                )
                authority_digest = hook_fixtures.fastlane_hook._canonical_digest(match)
                state = hook_fixtures.fastlane_hook._empty_transition_state(
                    stage="START_BOUND",
                    action_kind=kind,
                    identity=identity,
                    tool_name="apply_patch",
                    attempt_sha256=hook_fixtures.fastlane_hook._value_digest(
                        attempt_id
                    ),
                    authority_sha256=authority_digest,
                    start_patch_sha256="sha256:" + "e" * 64,
                )
                hook_fixtures.fastlane_hook._store_transition(REPOSITORY_ROOT, state)
                transition = {
                    "schema_version": 1,
                    "status": "BOUND",
                    "attempt_id": attempt_id,
                    "authority_kind": kind,
                    "request_match_sha256": authority_digest,
                    "request_match": match,
                }
                current["aws_action_transition"] = transition
                mismatched = {
                    **current,
                    "aws_action_transition": {
                        **transition,
                        "attempt_id": "AWS-TEARDOWN-9999"
                        if kind == "AWS_TEARDOWN"
                        else "AWS-DEPLOY-9999",
                    },
                }
                changed = hook_fixtures.fastlane_hook.handle_event(
                    "pre-tool-use",
                    pre_event,
                    root=REPOSITORY_ROOT,
                    doctor_report=mismatched,
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIn(
                    "binding is absent or changed",
                    changed["hookSpecificOutput"]["permissionDecisionReason"],
                )
                self.assertIsNone(
                    hook_fixtures.fastlane_hook._load_transition(REPOSITORY_ROOT)
                )
                hook_fixtures.fastlane_hook._store_transition(REPOSITORY_ROOT, state)
                pre_allowed = hook_fixtures.fastlane_hook.handle_event(
                    "pre-tool-use",
                    pre_event,
                    root=REPOSITORY_ROOT,
                    doctor_report=current,
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIsNone(pre_allowed)
                allowed = hook_fixtures.fastlane_hook.handle_event(
                    "permission-request",
                    event,
                    root=REPOSITORY_ROOT,
                    doctor_report=current,
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIsNone(allowed)
                replay = hook_fixtures.fastlane_hook.handle_event(
                    "pre-tool-use",
                    hook_fixtures.payload(
                        "PreToolUse",
                        REPOSITORY_ROOT,
                        tool_name="aws___call_aws",
                        tool_input=tool_input,
                        session_id=f"session-{kind}",
                        turn_id=f"replay-{kind}",
                        tool_use_id=f"tool-{kind}",
                    ),
                    root=REPOSITORY_ROOT,
                    doctor_report=current,
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIn(
                    "another turn or session",
                    replay["hookSpecificOutput"]["permissionDecisionReason"],
                )
                hook_fixtures.fastlane_hook._clear_transition(REPOSITORY_ROOT)
        hook_fixtures.fastlane_hook._clear_transition(REPOSITORY_ROOT)

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
                    tool_input={
                        "script": reviewed_script,
                        "aws_profile": "fastlane-role",
                    },
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
        self.assertIn(
            "blocked", opaque["hookSpecificOutput"]["permissionDecisionReason"]
        )

    def test_aws_guidance_read_scope_preflight_and_mutation_wait_are_serial(
        self,
    ) -> None:
        materiality = {"materiality": "REQUIRED", "status": "CURRENT"}
        no_preflight = {
            "status": "NOT_STARTED",
            "account_access": "NOT_OBSERVED",
            "account": "NONE",
            "region": "NONE",
            "environment": "NONE",
        }
        read_authority = {
            "validity": "CURRENT",
            "authorization_id": "AWS-READ-AUTH-0001",
        }
        observed = {
            "status": "READY",
            "account_access": "READ_ONLY_OBSERVED",
            "account": "111122223333",
            "region": "us-west-2",
            "environment": "development",
        }
        guidance = doctor.derive_aws_execution_projection(
            materiality,
            release_decision="READY_TO_DEPLOY",
            guidance_ready=False,
            read_authority=None,
            preflight=no_preflight,
            lane="explicit-gate",
        )
        read_scope = doctor.derive_aws_execution_projection(
            materiality,
            release_decision="READY_TO_DEPLOY",
            guidance_ready=True,
            read_authority=None,
            preflight=no_preflight,
            lane="explicit-gate",
        )
        running = doctor.derive_aws_execution_projection(
            materiality,
            release_decision="READY_TO_DEPLOY",
            guidance_ready=True,
            read_authority=read_authority,
            preflight=no_preflight,
            lane="explicit-gate",
        )
        ready = doctor.derive_aws_execution_projection(
            materiality,
            release_decision="READY_TO_DEPLOY",
            guidance_ready=True,
            read_authority=read_authority,
            preflight=observed,
            lane="read-only",
        )
        mutation_wait = doctor.derive_aws_execution_projection(
            materiality,
            release_decision="READY_TO_DEPLOY",
            guidance_ready=True,
            read_authority=read_authority,
            preflight=observed,
            lane="explicit-gate",
        )
        self.assertEqual(
            [
                guidance["progress_state"],
                read_scope["progress_state"],
                running["progress_state"],
                ready["progress_state"],
                mutation_wait["progress_state"],
            ],
            [
                "AWS_GUIDANCE_REQUIRED",
                "AWS_READ_SCOPE_REQUIRED",
                "AWS_PREFLIGHT_RUNNING",
                "AWS_PREFLIGHT_READY",
                "WAITING_AWS_MUTATION_AUTH",
            ],
        )
        self.assertFalse(
            bool(
                guidance.get("preflight", {}).get("account_access")
                == "READ_ONLY_OBSERVED"
            )
        )
        self.assertIn("AWS_PREFLIGHT_READY", mutation_wait["completed_states"])

        guidance_text = presenter.render_owner_update(
            presenter_fixtures.aws_progress_report("AWS_GUIDANCE_REQUIRED")
        )
        self.assertIn("without accessing an AWS account", guidance_text)
        read_scope_text = presenter.render_side_question_response(
            presenter_fixtures.aws_progress_report(
                "AWS_READ_SCOPE_REQUIRED",
                action_kind="AUTHORIZE_AWS_READ_PREFLIGHT",
                owner_action_required=True,
                automatic_continuation_allowed=False,
                formal_receipt_required=True,
            ),
            answer="The preflight can inspect only the exact named scope.",
        )
        self.assertIn("It grants no mutation.", read_scope_text)
        running_text = presenter.render_owner_update(
            presenter_fixtures.aws_progress_report("AWS_PREFLIGHT_RUNNING")
        )
        self.assertIn("Need from you: Nothing.", running_text)
        self.assertIn("No mutation is authorized.", running_text)
        ready_text = presenter.render_owner_update(
            presenter_fixtures.aws_progress_report(
                "AWS_PREFLIGHT_READY",
                preflight_status="READY",
                account_access="READ_ONLY_OBSERVED",
                automatic_continuation_allowed=False,
            )
        )
        self.assertIn("authorized read-only AWS inspection is complete", ready_text)
        self.assertIn("No AWS resource mutation will occur.", ready_text)
        mutation_text = presenter.render_side_question_response(
            presenter_fixtures.aws_progress_report(
                "WAITING_AWS_MUTATION_AUTH",
                action_kind="AUTHORIZE_AWS_OPERATION",
                owner_action_required=True,
                automatic_continuation_allowed=False,
                formal_receipt_required=True,
                preflight_status="READY",
                account_access="READ_ONLY_OBSERVED",
            ),
            answer="The preflight does not authorize deployment.",
        )
        self.assertIn("deployment receipt", mutation_text)
        self.assertNotIn("teardown receipt", mutation_text)

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
                owner="lead",
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
            completed = task_waves.parse_tasks(tasks_path.read_text(encoding="utf-8"))[
                0
            ]
            self.assertEqual(completed.status, "DONE")
            self.assertIn("EV-0001", verify_path.read_text(encoding="utf-8"))

    def test_bug_adjunct_preserves_pending_gate_and_implicit_write_is_denied(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.extract_template(Path(directory), "bug-adjunct")
            self.initialize(project)
            self.make_gate_a_pending(project)

            before = doctor.inspect_project(project)
            self.assertTrue(before["ok"], before["diagnostics"])
            self.assertEqual(before["lifecycle_state"], "WAITING_GATE_A")
            self.assertEqual(before["next_prompt"], "INTAKE-20")
            self.assertEqual(before["gates"]["gate_a"], "PENDING_OWNER_APPROVAL")
            self.assertEqual(before["gates"]["gate_b"], "BLOCKED")
            self.assertEqual(
                before["interaction"]["owner_action_kind"], "APPROVE_GATE_A"
            )
            self.assertTrue(before["interaction"]["formal_receipt_required"])

            side_question = presenter.render_side_question_response(
                before,
                answer=(
                    "BUG-10 can analyze a bounded defect without replacing the "
                    "requirements approval that is already waiting."
                ),
            )
            self.assertIn("Project state changed: No.", side_question)
            self.assertIn("Pending next action:", side_question)
            self.assertNotIn("\nAPPROVE REQUIREMENTS GATE A\n", side_question)

            denied = hook_fixtures.fastlane_hook.handle_event(
                "pre-tool-use",
                hook_fixtures.payload(
                    "PreToolUse",
                    project,
                    tool_name="apply_patch",
                    tool_input=hook_fixtures.patch_input("docs/project/BUGFIX.md"),
                ),
                root=project,
                doctor_report=before,
                envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
            )
            decision = denied["hookSpecificOutput"]
            self.assertEqual(decision["permissionDecision"], "deny")
            self.assertIn(
                "Gate B write authority is absent",
                decision["permissionDecisionReason"],
            )

            protected_paths = (
                "docs/project/TASKS.md",
                "docs/project/VERIFY.md",
                "docs/project/RUNBOOK.md",
                "bootstrap.yaml",
            )
            protected = {
                path: (project / path).read_bytes() for path in protected_paths
            }
            bugfix_path = project / "docs/project/BUGFIX.md"
            bugfix_text = bugfix_path.read_text(encoding="utf-8")
            bugfix_text = bugfix_text.replace(
                "- Title: TODO",
                "- Title: Gate A decision remains visible after a side question",
                1,
            ).replace(
                "- Related PRD requirements: TODO",
                "- Related PRD requirements: FR-001",
                1,
            )
            bugfix_path.write_text(bugfix_text, encoding="utf-8")
            doctor_fixtures.refresh_document_summaries(project)

            after = doctor.inspect_project(project)
            self.assertTrue(after["ok"], after["diagnostics"])
            for field in ("lifecycle_state", "next_prompt", "gates", "authorizations"):
                self.assertEqual(after[field], before[field])
            self.assertEqual(after["interaction"], before["interaction"])
            for path, expected in protected.items():
                self.assertEqual((project / path).read_bytes(), expected)

    def test_sync_adjunct_reconciles_only_named_issue_and_restores_build_route(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.extract_template(Path(directory), "sync-adjunct")
            self.initialize(project)
            fixture = doctor_fixtures.BootstrapDoctorTests()
            fixture.approve_project(project, gate_b=True)
            envelope = self.authorize_issue_sync(project)
            fixture.initialize_task_plan(
                project,
                doctor_fixtures.ready_task(
                    requirements=(
                        f"{doctor_fixtures.MODERN_TASK_REQUIREMENT_TRACE}; PROP-001"
                    ),
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    command="python -m unittest tests.test_properties",
                    property_projection=doctor_fixtures.property_execution_projection(),
                ),
            )

            before = doctor.inspect_project(project)
            self.assertTrue(before["ok"], before["diagnostics"])
            self.assertEqual(before["next_prompt"], "BUILD-10")
            self.assertEqual(
                before["interaction"]["owner_action_kind"],
                "NONE_CONTINUE_AUTOMATICALLY",
            )
            self.assertEqual(before["authorizations"]["aws"], "NONE")

            implicit = dict(before)
            implicit["authorizations"] = dict(before["authorizations"])
            implicit["authorizations"]["construction"] = "NONE"
            issue_input = {
                "owner": "Levi-Breedlove",
                "repo": "aws-bootstrap",
                "title": "Synchronize TASK-001",
            }
            denied_implicit = hook_fixtures.fastlane_hook.handle_event(
                "pre-tool-use",
                hook_fixtures.payload(
                    "PreToolUse",
                    project,
                    tool_name="mcp__github__create_issue",
                    tool_input=issue_input,
                ),
                root=project,
                doctor_report=implicit,
                envelope=envelope,
            )
            self.assertIn(
                "construction authority is absent",
                denied_implicit["hookSpecificOutput"]["permissionDecisionReason"],
            )
            denied_merge = hook_fixtures.fastlane_hook.handle_event(
                "pre-tool-use",
                hook_fixtures.payload(
                    "PreToolUse",
                    project,
                    tool_name="mcp__github__merge_pull_request",
                    tool_input={
                        "owner": "Levi-Breedlove",
                        "repo": "aws-bootstrap",
                        "number": 51,
                    },
                ),
                root=project,
                doctor_report=before,
                envelope=envelope,
            )
            self.assertIn(
                "exceeds the current GitHub boundary",
                denied_merge["hookSpecificOutput"]["permissionDecisionReason"],
            )
            allowed_issue = hook_fixtures.fastlane_hook.handle_event(
                "pre-tool-use",
                hook_fixtures.payload(
                    "PreToolUse",
                    project,
                    tool_name="mcp__github__create_issue",
                    tool_input=issue_input,
                ),
                root=project,
                doctor_report=before,
                envelope=envelope,
            )
            self.assertIsNone(allowed_issue)

            tasks_path = project / "docs/project/TASKS.md"
            tasks_text = tasks_path.read_text(encoding="utf-8")
            wrong_issue = "https://github.com/example/other/issues/51"
            tasks_path.write_text(
                tasks_text.replace(
                    "- GitHub issue: `PENDING_SYNC`",
                    f"- GitHub issue: `{wrong_issue}`",
                    1,
                ),
                encoding="utf-8",
            )
            wrong = doctor.inspect_project(project)
            self.assertIn(
                "TASK_GITHUB_BOUNDARY",
                doctor_fixtures.codes(wrong),
            )
            correct_issue = "https://github.com/Levi-Breedlove/aws-bootstrap/issues/51"
            tasks_path.write_text(
                tasks_path.read_text(encoding="utf-8").replace(
                    f"- GitHub issue: `{wrong_issue}`",
                    f"- GitHub issue: `{correct_issue}`",
                    1,
                ),
                encoding="utf-8",
            )

            after = doctor.inspect_project(project)
            self.assertTrue(after["ok"], after["diagnostics"])
            self.assertEqual(after["lifecycle_state"], before["lifecycle_state"])
            self.assertEqual(after["next_prompt"], before["next_prompt"])
            self.assertEqual(after["gates"], before["gates"])
            self.assertEqual(after["interaction"], before["interaction"])
            self.assertEqual(after["authorizations"]["aws"], "NONE")

    def test_residual_disposition_is_fresh_set_level_and_non_authorizing(
        self,
    ) -> None:
        residuals = {
            "status": "RESIDUALS_REMAIN",
            "evidence_id": "EV-9100",
            "observed_at": "2098-01-01T00:00:00Z",
            "issues": [],
        }
        stale_remove_record = {
            "value": "TEARDOWN",
            "recorded_at": "2097-01-01T00:00:00Z",
            "provenance_status": "CURRENT",
        }
        pending = doctor.derive_aws_residual_disposition(
            stale_remove_record,
            residuals,
        )
        self.assertEqual(pending["status"], "PENDING")
        pending_route = doctor.derive_teardown_route(
            "TEARDOWN",
            residuals,
            pending,
        )
        self.assertEqual(pending_route, ("AWS_RESIDUALS_REMAIN", "STOP"))
        pending_interaction = doctor.derive_interaction(
            *pending_route,
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=True,
            aws_execution_planning_ready=True,
        )
        self.assertEqual(
            pending_interaction["owner_action_kind"],
            "CHOOSE_AWS_RESIDUAL_DISPOSITION",
        )
        self.assertTrue(pending_interaction["owner_action_required"])
        self.assertFalse(pending_interaction["formal_receipt_required"])
        pending_report = presenter_fixtures.aws_teardown_report(
            "AWS_RESIDUALS_REMAIN",
            action_kind="CHOOSE_AWS_RESIDUAL_DISPOSITION",
            owner_action_required=True,
            automatic_continuation_allowed=False,
        )
        pending_report["interaction"] = pending_interaction
        pending_report["aws_residual_disposition"] = pending
        pending_text = presenter.render_owner_update(pending_report)
        self.assertIn("one decision", pending_text)
        self.assertIn(
            "AWS residual decision: <RETAIN | INVESTIGATE | REMOVE>",
            pending_text,
        )

        fresh_records = {
            "RETAIN": {
                "value": "RETAIN",
                "recorded_at": "2098-01-01T00:00:01Z",
                "provenance_status": "CURRENT",
            },
            "INVESTIGATE": {
                "value": "RESIDUAL_REVIEW",
                "recorded_at": "2098-01-01T00:00:01Z",
                "provenance_status": "CURRENT",
            },
            "REMOVE": {
                "value": "TEARDOWN",
                "recorded_at": "2098-01-01T00:00:01Z",
                "provenance_status": "CURRENT",
            },
        }
        projections = {
            choice: doctor.derive_aws_residual_disposition(record, residuals)
            for choice, record in fresh_records.items()
        }
        for choice, projection in projections.items():
            with self.subTest(choice=choice):
                self.assertEqual(projection["status"], "CURRENT")
                self.assertEqual(projection["value"], choice)
                self.assertFalse(projection["authorizes_aws_access"])
                self.assertFalse(projection["authorizes_mutation"])

        retained_route = doctor.derive_teardown_route(
            "RETAIN", residuals, projections["RETAIN"]
        )
        self.assertEqual(retained_route, ("AWS_RESIDUALS_RETAINED", "STOP"))
        retained_interaction = doctor.derive_interaction(
            *retained_route,
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=True,
            aws_execution_planning_ready=True,
        )
        retained_report = presenter_fixtures.aws_teardown_report(
            "AWS_RESIDUALS_RETAINED",
            automatic_continuation_allowed=False,
        )
        retained_report["interaction"] = retained_interaction
        retained_report["aws_lifecycle_intent"] = presenter_fixtures.lifecycle_intent(
            "RETAIN"
        )
        retained_report["aws_residual_disposition"] = projections["RETAIN"]
        retained_text = presenter.render_owner_update(retained_report)
        self.assertIn("may continue to incur cost", retained_text)
        self.assertIn("no AWS access or mutation was authorized", retained_text)
        self.assertNotIn("no unexpected resources remain", retained_text)

        for choice, intent in (
            ("INVESTIGATE", "RESIDUAL_REVIEW"),
            ("REMOVE", "TEARDOWN"),
        ):
            with self.subTest(choice=choice, basis="residuals"):
                route = doctor.derive_teardown_route(
                    intent,
                    residuals,
                    projections[choice],
                )
                self.assertEqual(route, ("AWS_RESIDUAL_REVIEW", "AWS-40"))
                interaction = doctor.derive_interaction(
                    *route,
                    has_errors=False,
                    diagnostic_codes=[],
                    design_aws_core_ready=True,
                    aws_execution_planning_ready=True,
                    aws_read_authority_required=True,
                )
                self.assertEqual(
                    interaction["owner_action_kind"],
                    "AUTHORIZE_AWS_READ_PREFLIGHT",
                )
                self.assertTrue(interaction["formal_receipt_required"])

        ready = {
            "status": "READY_FOR_TEARDOWN",
            "evidence_id": "EV-9101",
            "observed_at": "2098-01-02T00:00:00Z",
            "issues": [],
        }
        carried_remove = doctor.derive_aws_residual_disposition(
            fresh_records["REMOVE"], ready
        )
        self.assertEqual(carried_remove["status"], "CURRENT")
        self.assertEqual(carried_remove["value"], "REMOVE")
        teardown_route = doctor.derive_teardown_route("TEARDOWN", ready, carried_remove)
        self.assertEqual(teardown_route, ("WAITING_AWS_TEARDOWN_AUTH", "AWS-50"))
        teardown_interaction = doctor.derive_interaction(
            *teardown_route,
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=True,
            aws_execution_planning_ready=True,
        )
        self.assertEqual(
            teardown_interaction["owner_action_kind"], "AUTHORIZE_AWS_TEARDOWN"
        )
        self.assertTrue(teardown_interaction["formal_receipt_required"])

        later_residuals = {
            **residuals,
            "evidence_id": "EV-9102",
            "observed_at": "2098-01-03T00:00:00Z",
        }
        reopened = doctor.derive_aws_residual_disposition(
            fresh_records["REMOVE"], later_residuals
        )
        self.assertEqual(reopened["status"], "PENDING")

        stale_investigate = doctor.derive_aws_residual_disposition(
            fresh_records["INVESTIGATE"], ready
        )
        self.assertEqual(stale_investigate["status"], "PENDING")
        refreshed_investigate = doctor.derive_aws_residual_disposition(
            {
                **fresh_records["INVESTIGATE"],
                "recorded_at": "2098-01-02T00:00:01Z",
            },
            ready,
        )
        self.assertEqual(refreshed_investigate["status"], "CURRENT")
        self.assertEqual(refreshed_investigate["value"], "INVESTIGATE")

    def test_adjuncts_cannot_replace_aws50_terminal_or_post_action_routes(
        self,
    ) -> None:
        terminal = {
            "status": "ACTION_TERMINAL_REQUIRED",
            "attempt_id": "AWS-TEARDOWN-0001",
            "evidence_id": "EV-9001",
            "issues": [],
        }
        post_action = {"status": "POST_ACTION_REVIEW"}
        for intent in ("NONE", "RETAIN", "RESIDUAL_REVIEW", "TEARDOWN"):
            with self.subTest(intent=intent):
                self.assertEqual(
                    doctor.derive_teardown_route(intent, terminal),
                    ("AWS_TEARDOWN_ACTION_TERMINAL", "AWS-50"),
                )
                self.assertEqual(
                    doctor.derive_teardown_route(intent, post_action),
                    ("AWS_RESIDUAL_REVIEW", "AWS-40"),
                )

        interaction = doctor.derive_interaction(
            "AWS_TEARDOWN_ACTION_TERMINAL",
            "AWS-50",
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=True,
            aws_execution_planning_ready=True,
        )
        self.assertEqual(
            interaction["owner_action_kind"], "NONE_CONTINUE_AUTOMATICALLY"
        )
        self.assertTrue(interaction["automatic_continuation_allowed"])
        self.assertFalse(interaction["formal_receipt_required"])

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            report = hook_fixtures.report(
                construction="NONE",
                aws="NONE",
                automatic=True,
                owner_action=False,
            )
            report["interaction"] = interaction
            report["teardown_journal_closure_authority"] = (
                doctor.derive_teardown_journal_closure_authority(
                    terminal,
                    "AWS-50",
                    restricted_closure=True,
                )
            )
            for tool_name, tool_input in (
                (
                    "apply_patch",
                    hook_fixtures.patch_input("docs/project/BUGFIX.md"),
                ),
                (
                    "mcp__github__create_issue",
                    {
                        "owner": "Levi-Breedlove",
                        "repo": "aws-bootstrap",
                        "title": "Do not displace AWS-50",
                    },
                ),
            ):
                with self.subTest(tool_name=tool_name):
                    denied = hook_fixtures.fastlane_hook.handle_event(
                        "pre-tool-use",
                        hook_fixtures.payload(
                            "PreToolUse",
                            project,
                            tool_name=tool_name,
                            tool_input=tool_input,
                        ),
                        root=project,
                        doctor_report=report,
                        envelope={
                            "AWS boundary": "NONE",
                            "GitHub boundary": "ISSUES",
                        },
                    )
                    self.assertEqual(
                        denied["hookSpecificOutput"]["permissionDecision"],
                        "deny",
                    )

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
        foundation = report["intake_foundation"]
        self.assertEqual(foundation["schema_version"], 2)
        self.assertEqual(foundation["current_understanding"], [])
        self.assertEqual(foundation["repository_mode"], "GREENFIELD")
        self.assertIsNone(foundation["owner_work_context"])
        self.assertEqual(foundation["status"], "FOUNDATION_REQUIRED")
        self.assertEqual(
            foundation["next_question_guidance"]["status"],
            "STARTING_POINT_REQUIRED",
        )
        self.assertFalse(foundation["project_configuration"]["owner_action_required"])
        self.assertEqual(len(foundation["pending_card"]["questions"]), 1)
        self.assertTrue(report["interaction"]["turn_boundary_required"])
        self.assertNotIn("What Fastlane already knows", rendered)
        self.assertIn("Why this matters", rendered)
        self.assertIn("1. What kind of project are we starting together?", rendered)
        self.assertIn("A. A new application", rendered)
        self.assertIn("B. A change to an existing application", rendered)
        self.assertIn("C. A repair", rendered)
        self.assertIn(
            "No recommendation\u2014choose the option that matches your situation.",
            rendered,
        )
        self.assertIn("Reply with one of:", rendered)
        self.assertIn("Reply with one of:\n\n- `A`", rendered)
        self.assertIn("\n\n- `B: <required detail>`", rendered)
        self.assertIn("\n\n- `C: <required detail>`", rendered)
        self.assertIn("\n\nA. A new application", rendered)
        self.assertIn("\n\nB. A change to an existing application", rendered)
        self.assertIn("\n\nC. A repair", rendered)
        self.assertNotIn("<choose A, B, or C>", rendered)
        self.assertNotIn("Accept all recommendations.", rendered)
        self.assertNotIn("validation boundary", rendered)
        self.assertNotIn("FASTLANE · WELCOME", rendered)
        self.assertNotIn("Welcome to Fastlane.", rendered)


if __name__ == "__main__":
    unittest.main()
