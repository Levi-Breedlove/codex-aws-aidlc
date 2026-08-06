from __future__ import annotations

import copy
import re
import unittest
from pathlib import Path

from scripts import bootstrap_doctor as doctor
from scripts.fastlane_engine.report import derive_document_summary_specifications
from scripts.fastlane_document_summaries import (
    SUMMARY_AUTHORITY,
    SUMMARY_BEGIN,
    SUMMARY_END,
    build_summary_specifications,
    canonical_bytes_without_generated_summary,
    project_document_summaries,
    render_summary_markdown,
    strip_generated_summary,
    wrapped_summary_markdown,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

BASELINE_VISIBLE_LINES = {
    "docs/project/PRD.md": 1292,
    "docs/project/TASKS.md": 361,
    "docs/project/VERIFY.md": 649,
    "docs/project/RUNBOOK.md": 612,
}
BASELINE_COMBINED_CHARACTERS = 198_572
PRE_PR2_COMBINED_BYTES = 170_342
PR2_REQUIRED_REDUCTION_BYTES = 25_000
HUMAN_FIRST_RECORDS = tuple(BASELINE_VISIBLE_LINES)


def visible_markdown_lines(markdown: str) -> list[str]:
    """Return nonblank rendered lines while hiding closed disclosure bodies."""

    visible: list[str] = []
    in_details = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("<!--") and line.endswith("-->"):
            continue
        if line == "<details>":
            in_details = True
            continue
        if in_details:
            if line.startswith("<summary>") and line.endswith("</summary>"):
                visible.append(line)
            elif line == "</details>":
                in_details = False
            continue
        if line:
            visible.append(line)
    return visible


class DocumentSummaryReadabilityTests(unittest.TestCase):
    def test_visible_line_helper_counts_only_disclosure_summary(self) -> None:
        markdown = """# Record

Visible

<details>
<summary>Exact records</summary>

Hidden row

</details>

Visible again
"""
        self.assertEqual(
            visible_markdown_lines(markdown),
            [
                "# Record",
                "Visible",
                "<summary>Exact records</summary>",
                "Visible again",
            ],
        )

    def test_final_readability_thresholds_are_explicit(self) -> None:
        rules = (REPOSITORY_ROOT / "docs/project/AGENTS.md").read_text(encoding="utf-8")
        evaluation = (
            REPOSITORY_ROOT
            / ".agents/skills/maintain-fastlane/references/evaluation.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "within 45 visible PRD lines",
            "within 35 TASKS lines",
            "within 30 VERIFY lines",
            "within 45 RUNBOOK lines",
            "at most 80 lines",
            "at most 140 lines",
            "at least 35 percent",
            "at least 20,000 characters",
        ):
            self.assertIn(phrase, rules + "\n" + evaluation)
        self.assertIn("balanced, labeled `<details>`", rules)


DOCUMENT_PATHS = (
    "docs/project/README.md",
    "docs/project/PRD.md",
    "docs/project/TASKS.md",
    "docs/project/VERIFY.md",
    "docs/project/RUNBOOK.md",
    "docs/project/BUGFIX.md",
)


def template_specifications() -> list[dict[str, object]]:
    return build_summary_specifications(
        {
            "template_like": True,
            "lifecycle_state": "UNCONFIGURED_TEMPLATE",
            "next_prompt": "BOOT-00",
            "gate_a": "BLOCKED",
            "gate_b": "BLOCKED",
            "tasks": {},
            "verify": {
                "claims": [
                    {
                        "claim": "Requirements are approved",
                        "maturity": "Not yet observed",
                        "evidence": "None",
                        "limitation": "Gate A is not approved",
                    },
                    {
                        "claim": "Technical design is approved",
                        "maturity": "Not yet observed",
                        "evidence": "None",
                        "limitation": "Gate B is not approved",
                    },
                    {
                        "claim": "Current AWS guidance informed the plan",
                        "maturity": "Not yet observed",
                        "evidence": "None",
                        "limitation": "Source guidance is not deployment evidence",
                    },
                    {
                        "claim": "Local release checks passed",
                        "maturity": "Not yet observed",
                        "evidence": "None",
                        "limitation": "Local evidence does not prove AWS behavior",
                    },
                    {
                        "claim": "Application is deployed",
                        "maturity": "Not authorized",
                        "evidence": "None",
                        "limitation": "No deployment evidence or authority",
                    },
                    {
                        "claim": "Teardown is complete",
                        "maturity": "Not authorized",
                        "evidence": "None",
                        "limitation": "No teardown evidence or authority",
                    },
                ]
            },
            "operations": {},
            "bugfix": {"status": "No active bounded defect"},
        }
    )


def canonical_sources() -> dict[str, str]:
    return {
        path: (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
        for path in DOCUMENT_PATHS
    }


def first_screen(markdown: str) -> list[str]:
    end = markdown.index(SUMMARY_END) + len(SUMMARY_END)
    return visible_markdown_lines(markdown[:end])


def visible_position(markdown: str, expected: str) -> int:
    for index, line in enumerate(visible_markdown_lines(markdown), 1):
        if expected in line:
            return index
    raise AssertionError(f"Missing visible content: {expected}")


def visible_section_size(markdown: str, start: str, end: str) -> int:
    lines = visible_markdown_lines(markdown)
    start_index = lines.index(start)
    end_index = lines.index(end, start_index + 1)
    return end_index - start_index


class HumanFirstDocumentQualificationTests(unittest.TestCase):
    def test_visible_reading_path_meets_the_exact_reduction_contract(self) -> None:
        current_sources = {
            path: (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
            for path in HUMAN_FIRST_RECORDS
        }
        current_visible = {
            path: len(visible_markdown_lines(source))
            for path, source in current_sources.items()
        }
        baseline_total = sum(BASELINE_VISIBLE_LINES.values())
        current_total = sum(current_visible.values())
        self.assertGreaterEqual(
            (baseline_total - current_total) / baseline_total,
            0.35,
            current_visible,
        )
        self.assertLessEqual(
            sum(len(source) for source in current_sources.values()),
            BASELINE_COMBINED_CHARACTERS - 20_000,
        )
        current_bytes = sum(
            len(source.encode("utf-8")) for source in current_sources.values()
        )
        self.assertLessEqual(
            current_bytes,
            PRE_PR2_COMBINED_BYTES - PR2_REQUIRED_REDUCTION_BYTES,
        )

    def test_runbook_active_boundary_is_a_compact_operational_table(self) -> None:
        runbook = (REPOSITORY_ROOT / "docs/project/RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "<summary>View the detailed AWS authority record</summary>\n\n## Active operational boundary",
            runbook,
        )
        section = runbook.split("## Active operational boundary", 1)[1].split(
            "\n## ", 1
        )[0]
        data_rows = [line for line in section.splitlines() if line.startswith("| ")][1:]
        self.assertGreaterEqual(len(data_rows), 6)
        self.assertLessEqual(len(data_rows), 8)

    def test_owner_surfaces_arrive_within_their_visible_line_budgets(self) -> None:
        sources = {
            path: (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
            for path in HUMAN_FIRST_RECORDS
        }
        self.assertLessEqual(
            visible_position(sources["docs/project/PRD.md"], "# Product Agreement"),
            45,
        )
        self.assertLessEqual(
            visible_position(sources["docs/project/TASKS.md"], "## Current progress"),
            35,
        )
        self.assertLessEqual(
            visible_position(sources["docs/project/VERIFY.md"], "### Important claims"),
            30,
        )
        for destination in (
            "[Before deploying]",
            "[Deploy]",
            "[Verify]",
            "[Roll back]",
            "[Recover]",
            "[Tear down]",
        ):
            self.assertLessEqual(
                visible_position(sources["docs/project/RUNBOOK.md"], destination), 45
            )
        self.assertLessEqual(
            visible_section_size(
                sources["docs/project/PRD.md"], "# Gate A Review", "# Technical Plan"
            ),
            80,
        )
        self.assertLessEqual(
            visible_section_size(
                sources["docs/project/PRD.md"],
                "# Gate B Review",
                "# Contract Appendices",
            ),
            140,
        )

    def test_inactive_bugfix_mirrors_the_global_engine_owner_action(self) -> None:
        specifications = build_summary_specifications(
            {
                "template_like": False,
                "lifecycle_state": "WAITING_GATE_A",
                "next_prompt": "INTAKE-20",
                "gate_a": "PENDING_OWNER_APPROVAL",
                "gate_b": "BLOCKED",
                "action_kind": "APPROVE_GATE_A",
                "automatic_continuation_allowed": False,
                "tasks": {},
                "verify": {},
                "operations": {},
                "bugfix": {"status": "No active bounded defect"},
            }
        )
        by_path = {item["path"]: item for item in specifications}
        expected_need = by_path["docs/project/PRD.md"]["need_from_owner"]
        expected_next = by_path["docs/project/PRD.md"]["next_action"]
        self.assertEqual(
            by_path["docs/project/BUGFIX.md"]["need_from_owner"], expected_need
        )
        self.assertEqual(
            by_path["docs/project/BUGFIX.md"]["next_action"], expected_next
        )
        self.assertEqual(
            {item["need_from_owner"] for item in specifications}, {expected_need}
        )


class DocumentSummaryProjectionTests(unittest.TestCase):
    def test_independently_authored_owner_summary_truth_matrix(self) -> None:
        """Compare production output with literal owner meaning, not itself."""

        cases = (
            (
                "untouched template",
                {
                    "template_like": True,
                    "action_kind": "ANSWER_OPEN_DECISIONS",
                    "automatic_continuation_allowed": False,
                    "next_prompt": "BOOT-00",
                },
                "Run `init template`.",
                "Codex will verify prerequisites and initialize the project.",
            ),
            (
                "prerequisites blocked",
                {
                    "action_kind": "COMPLETE_PREREQUISITE_CHECKLIST",
                    "automatic_continuation_allowed": False,
                    "next_prompt": "BOOT-00",
                },
                "Complete the prerequisite checklist.",
                "Codex will verify prerequisites and initialize the project.",
            ),
            (
                "intake pending",
                {
                    "action_kind": "ANSWER_OPEN_DECISIONS",
                    "automatic_continuation_allowed": False,
                    "next_prompt": "INTAKE-10",
                },
                "Answer the current project question.",
                "Codex will record the answer and ask the next material question.",
            ),
            (
                "requirements analysis running",
                {
                    "action_kind": "NONE_CONTINUE_AUTOMATICALLY",
                    "automatic_continuation_allowed": True,
                    "next_prompt": "REQ-10",
                },
                "Nothing",
                "Codex will complete and validate the product requirements.",
            ),
            (
                "Gate A pending",
                {
                    "action_kind": "APPROVE_GATE_A",
                    "automatic_continuation_allowed": False,
                    "next_prompt": "INTAKE-20",
                },
                "Review the requirements and approve them or request a correction.",
                "After your decision, Codex will continue to technical design or "
                "apply your correction.",
            ),
            (
                "Gate A approved and Design active",
                {
                    "action_kind": "NONE_CONTINUE_AUTOMATICALLY",
                    "automatic_continuation_allowed": True,
                    "next_prompt": "DESIGN-10",
                },
                "Nothing",
                "Codex will complete the technical design and supporting evidence.",
            ),
            (
                "Gate B pending",
                {
                    "action_kind": "APPROVE_GATE_B",
                    "automatic_continuation_allowed": False,
                    "next_prompt": "DESIGN-20",
                },
                "Review the technical plan and approve it or request a correction.",
                "After your decision, Codex will create the construction tasks or "
                "apply your correction.",
            ),
            (
                "Gate B approved and tasks active",
                {
                    "action_kind": "NONE_CONTINUE_AUTOMATICALLY",
                    "automatic_continuation_allowed": True,
                    "next_prompt": "TASK-10",
                },
                "Nothing",
                "Codex will derive the approved construction tasks.",
            ),
            (
                "build blocked by owner decision",
                {
                    "action_kind": "ANSWER_OPEN_DECISIONS",
                    "automatic_continuation_allowed": False,
                    "next_prompt": "BUILD-10",
                },
                "Answer the current project question.",
                "After your answer, Codex will resume the active local construction "
                "task.",
            ),
            (
                "safe agent correction",
                {
                    "action_kind": "NONE_CONTINUE_AUTOMATICALLY",
                    "automatic_continuation_allowed": True,
                    "automatic_action_kind": "CORRECT_AND_REVALIDATE",
                    "next_prompt": "REQ-10",
                },
                "Nothing",
                "Codex will repair the derived record and revalidate it.",
            ),
            (
                "manual safety review",
                {
                    "action_kind": "REVIEW_SAFETY_BLOCKER",
                    "automatic_continuation_allowed": False,
                    "next_prompt": "STOP",
                },
                "Review the reported safety boundary.",
                "After your direction, Codex will revalidate the safety boundary.",
            ),
            (
                "release ready",
                {
                    "action_kind": "NONE_CONTINUE_AUTOMATICALLY",
                    "automatic_continuation_allowed": True,
                    "next_prompt": "AWS-10",
                    "route_reason_code": "AWS_PREFLIGHT_RUNNING",
                },
                "Nothing",
                "Codex will complete the read-only AWS preflight.",
            ),
            (
                "AWS read authorization pending",
                {
                    "action_kind": "AUTHORIZE_AWS_READ_PREFLIGHT",
                    "automatic_continuation_allowed": False,
                    "next_prompt": "AWS-10",
                },
                "Review the exact read-only AWS authorization.",
                "After your authorization, Codex will perform only the exact "
                "read-only AWS preflight.",
            ),
            (
                "preflight running",
                {
                    "action_kind": "NONE_CONTINUE_AUTOMATICALLY",
                    "automatic_continuation_allowed": True,
                    "next_prompt": "AWS-10",
                },
                "Nothing",
                "Codex will prepare the read-only AWS preflight.",
            ),
            (
                "deployment authorization pending",
                {
                    "action_kind": "AUTHORIZE_AWS_OPERATION",
                    "automatic_continuation_allowed": False,
                    "next_prompt": "AWS-20",
                },
                "Review the exact AWS operation authorization.",
                "After your authorization, Codex will perform only the exact AWS "
                "operation.",
            ),
            (
                "teardown authorization pending",
                {
                    "action_kind": "AUTHORIZE_AWS_TEARDOWN",
                    "automatic_continuation_allowed": False,
                    "next_prompt": "AWS-50",
                },
                "Review the exact teardown authorization.",
                "After your authorization, Codex will perform only the exact "
                "teardown.",
            ),
        )
        base_state = {
            "template_like": False,
            "lifecycle_state": "BLOCKED",
            "gate_a": "BLOCKED",
            "gate_b": "BLOCKED",
        }
        for name, state, expected_need, expected_next in cases:
            with self.subTest(state=name):
                documents = build_summary_specifications(
                    {**base_state, **state}
                )
                self.assertEqual(
                    {item["need_from_owner"] for item in documents},
                    {expected_need},
                )
                self.assertEqual(
                    {item["next_action"] for item in documents},
                    {expected_next},
                )

    def test_blocking_owner_actions_use_specific_plain_language(self) -> None:
        expected = {
            "ENABLE_AWS_CORE": (
                "Enable and verify AWS Core, then continue.",
                "After AWS Core is enabled and verified, Codex will rerun the "
                "prerequisite check.",
            ),
            "FIX_VALIDATION_FAILURE": (
                "Review the validation failure and provide direction.",
                "After your direction, Codex will revalidate the current records.",
            ),
        }
        for action, (need, next_action) in expected.items():
            with self.subTest(action=action):
                specifications = build_summary_specifications(
                    {
                        "template_like": False,
                        "lifecycle_state": "BLOCKED",
                        "next_prompt": "STOP",
                        "action_kind": action,
                        "automatic_continuation_allowed": False,
                    }
                )
                self.assertEqual(
                    {item["need_from_owner"] for item in specifications}, {need}
                )
                self.assertEqual(
                    {item["next_action"] for item in specifications}, {next_action}
                )

    def summary_specifications(
        self,
        *,
        deployment_sequence: dict[str, object] | None = None,
        teardown_sequence: dict[str, object] | None = None,
        aws_core_usage: dict[str, object] | None = None,
        req_aws_core_materiality: str = "NOT_MATERIAL",
        bugfix_text: str | None = None,
        verify_text: str | None = None,
        release_decision: str = "NOT_READY",
        project_region: str | None = "us-west-2",
        external_authority: dict[str, object] | None = None,
    ) -> dict[str, dict[str, object]]:
        context = doctor.Context(REPOSITORY_ROOT)
        context.texts = canonical_sources()
        if bugfix_text is not None:
            context.texts["docs/project/BUGFIX.md"] = bugfix_text
        if verify_text is not None:
            context.texts["docs/project/VERIFY.md"] = verify_text
        specifications = derive_document_summary_specifications(
            context,
            classification="ACTIVE_GREENFIELD",
            lifecycle_state="WAITING_GATE_A",
            next_prompt="INTAKE-20",
            project={
                "region": project_region,
                "cost_posture": "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
            },
            prd_fields={
                "requirements_revision": "REQ-0001",
                "design_revision": "DES-0001",
                "construction_authorization": "AUTH-0001",
            },
            gate_a="PENDING_OWNER_APPROVAL",
            gate_b="BLOCKED",
            tasks=doctor.TaskSummary(),
            release_decision=release_decision,
            release_evidence_cutoff="NONE",
            aws_authorization="NONE",
            external_authority=(
                external_authority or {"kind": "NONE", "validity": "NONE"}
            ),
            interaction={
                "owner_stage": "DEFINE",
                "owner_action_kind": "APPROVE_GATE_A",
                "automatic_continuation_allowed": False,
            },
            active_artifact=(
                "docs/project/BUGFIX.md" if bugfix_text is not None else ""
            ),
            deployment_sequence=deployment_sequence or {},
            teardown_sequence=teardown_sequence or {},
            aws_core_usage=aws_core_usage or {},
            req_aws_core_materiality=req_aws_core_materiality,
            write_authority={"valid": False, "authorization_id": "NONE"},
            remediation={},
        )
        return {str(item["path"]): item for item in specifications}

    def test_reconciled_unsuccessful_deployment_is_not_presented_as_deployed(
        self,
    ) -> None:
        expected = {
            "FAILED": (
                "Failed deployment attempt reconciled; deployment not verified"
            ),
            "PARTIAL": (
                "Partial deployment reconciled; expected release not fully observed"
            ),
            "UNKNOWN": (
                "Deployment attempt reconciled, but terminal success remains unknown"
            ),
        }
        for action_status, expected_state in expected.items():
            with self.subTest(action_status=action_status):
                by_path = self.summary_specifications(
                    deployment_sequence={
                        "status": "RECONCILED",
                        "action_status": action_status,
                        "reconciliation_status": "COMPLETE",
                        "acceptance_evidence_ids": ["EV-0104"],
                    }
                )
                runbook = {
                    item["label"]: item["value"]
                    for item in by_path["docs/project/RUNBOOK.md"]["fields"]
                }
                claims = by_path["docs/project/VERIFY.md"]["claims"]
                deployment_claim = next(
                    item
                    for item in claims
                    if item["claim"] == "Application is deployed"
                )
                self.assertEqual(runbook["Deployment state"], expected_state)
                self.assertEqual(deployment_claim["maturity"], "Not yet observed")
                self.assertEqual(deployment_claim["limitation"], expected_state)

    def test_started_deployment_is_pending_reconciliation(self) -> None:
        by_path = self.summary_specifications(
            deployment_sequence={
                "status": "ACTION_TERMINAL_REQUIRED",
                "action_status": "STARTED",
                "reconciliation_status": "NONE",
                "acceptance_evidence_ids": [],
            }
        )
        runbook = {
            item["label"]: item["value"]
            for item in by_path["docs/project/RUNBOOK.md"]["fields"]
        }
        self.assertEqual(
            runbook["Deployment state"], "Deployment outcome pending reconciliation"
        )

        inconsistent = self.summary_specifications(
            deployment_sequence={
                "status": "RECONCILED",
                "action_status": "FAILED",
                "reconciliation_status": "NONE",
                "acceptance_evidence_ids": [],
            }
        )
        fields = {
            item["label"]: item["value"]
            for item in inconsistent["docs/project/RUNBOOK.md"]["fields"]
        }
        self.assertEqual(
            fields["Deployment state"],
            "Deployment outcome pending reconciliation",
        )

    def test_construction_status_uses_current_write_authority(self) -> None:
        base = {
            "template_like": False,
            "gate_a": "APPROVED_FOR_DESIGN",
            "gate_b": "APPROVED_FOR_CONSTRUCTION",
            "construction_authorization": "AUTH-0001",
            "action_kind": "NONE_CONTINUE_AUTOMATICALLY",
            "automatic_continuation_allowed": True,
            "next_prompt": "TASK-10",
        }
        expected_by_validity = {
            False: "Not approved (boundary record AUTH-0001)",
            True: "Approved (AUTH-0001)",
        }
        for valid, expected in expected_by_validity.items():
            with self.subTest(valid=valid):
                documents = build_summary_specifications(
                    {**base, "construction_authority_valid": valid}
                )
                by_path = {
                    str(item["path"]): {
                        field["label"]: field["value"]
                        for field in item["fields"]
                    }
                    for item in documents
                }
                self.assertEqual(
                    by_path["docs/project/PRD.md"]["Construction authorization"],
                    expected,
                )
                self.assertEqual(
                    by_path["docs/project/TASKS.md"]["Construction approval"],
                    expected,
                )
                self.assertEqual(
                    by_path["docs/project/RUNBOOK.md"]["Construction approval"],
                    expected,
                )

    def test_current_aws_authority_uses_plain_exact_scope(self) -> None:
        by_path = self.summary_specifications(
            external_authority={"kind": "AWS_READ_ONLY", "validity": "CURRENT"}
        )
        fields = {
            item["label"]: item["value"]
            for item in by_path["docs/project/RUNBOOK.md"]["fields"]
        }
        self.assertEqual(fields["Current AWS authority"], "Read-only AWS access")
        self.assertEqual(
            fields["Safest available operation"],
            "Only the exact authorized AWS operation",
        )

    def test_engine_template_derivation_matches_the_committed_generated_views(
        self,
    ) -> None:
        context = doctor.Context(REPOSITORY_ROOT, template_source=True)
        context.texts = canonical_sources()
        specifications = derive_document_summary_specifications(
            context,
            classification="TEMPLATE_SOURCE",
            lifecycle_state="UNCONFIGURED_TEMPLATE",
            next_prompt="BOOT-00",
            project={},
            prd_fields={},
            gate_a="BLOCKED",
            gate_b="BLOCKED",
            tasks=doctor.TaskSummary(),
            release_decision="NOT_READY",
            release_evidence_cutoff="NONE",
            aws_authorization="NONE",
            external_authority={"kind": "NONE", "validity": "NONE"},
            interaction={
                "owner_stage": "DEFINE",
                "owner_action_kind": "COMPLETE_PREREQUISITE_CHECKLIST",
                "automatic_continuation_allowed": False,
            },
            active_artifact="",
            deployment_sequence={},
            teardown_sequence={},
            aws_core_usage={},
            req_aws_core_materiality="OPTIONAL",
            write_authority={"valid": False, "authorization_id": "NONE"},
            remediation={},
        )
        projection, issues = project_document_summaries(
            canonical_sources(), specifications
        )
        self.assertEqual(issues, [])
        self.assertEqual(projection["status"], "CURRENT")

    def test_successful_reconciled_deployment_requires_acceptance_evidence(
        self,
    ) -> None:
        by_path = self.summary_specifications(
            deployment_sequence={
                "status": "RECONCILED",
                "action_status": "SUCCEEDED",
                "reconciliation_status": "COMPLETE",
                "acceptance_evidence_ids": ["EV-0104"],
            }
        )
        runbook = {
            item["label"]: item["value"]
            for item in by_path["docs/project/RUNBOOK.md"]["fields"]
        }
        deployment_claim = next(
            item
            for item in by_path["docs/project/VERIFY.md"]["claims"]
            if item["claim"] == "Application is deployed"
        )
        self.assertEqual(runbook["Deployment state"], "Deployment observed")
        self.assertEqual(deployment_claim["maturity"], "Deployed observed")
        self.assertEqual(deployment_claim["evidence"], "EV-0104")
        self.assertEqual(
            deployment_claim["limitation"], "Bound to Development in us-west-2"
        )

        without_acceptance = self.summary_specifications(
            deployment_sequence={
                "status": "RECONCILED",
                "action_status": "SUCCEEDED",
                "reconciliation_status": "COMPLETE",
                "acceptance_evidence_ids": [],
            }
        )
        claim = next(
            item
            for item in without_acceptance["docs/project/VERIFY.md"]["claims"]
            if item["claim"] == "Application is deployed"
        )
        self.assertNotEqual(claim["maturity"], "Deployed observed")

        without_environment = self.summary_specifications(
            deployment_sequence={
                "status": "RECONCILED",
                "action_status": "SUCCEEDED",
                "reconciliation_status": "COMPLETE",
                "acceptance_evidence_ids": ["EV-0104"],
            },
            project_region=None,
        )
        claim = next(
            item
            for item in without_environment["docs/project/VERIFY.md"]["claims"]
            if item["claim"] == "Application is deployed"
        )
        self.assertNotEqual(claim["maturity"], "Deployed observed")

    def test_completed_reconciled_teardown_is_observed(self) -> None:
        by_path = self.summary_specifications(
            teardown_sequence={
                "status": "VERIFIED_CLEAN",
                "action_status": "SUCCEEDED",
                "evidence_id": "AWS-EV-0042",
            }
        )
        claim = next(
            item
            for item in by_path["docs/project/VERIFY.md"]["claims"]
            if item["claim"] == "Teardown is complete"
        )
        self.assertEqual(claim["maturity"], "Teardown observed")
        self.assertEqual(claim["evidence"], "AWS-EV-0042")
        self.assertEqual(claim["limitation"], "Bound to Development in us-west-2")
        verify_fields = {
            item["label"]: item["value"]
            for item in by_path["docs/project/VERIFY.md"]["fields"]
        }
        self.assertNotIn("teardown", verify_fields["Still unobserved"])

    def test_every_owner_visible_value_has_typed_internal_provenance(self) -> None:
        by_path = self.summary_specifications()
        expected_examples = {
            ("docs/project/PRD.md", "First-release boundary"):
                "define.gate_a_readiness.scope_and_non_goals",
            ("docs/project/PRD.md", "Construction authorization"):
                "authority.write.valid + authority.write.authorization_id",
            ("docs/project/VERIFY.md", "Locally observed evidence"):
                "deliver.evidence.task_completion",
            ("docs/project/RUNBOOK.md", "Deployment state"):
                (
                    "aws.deployment.action_status + "
                    "aws.deployment.reconciliation_status + "
                    "aws.deployment.acceptance_evidence_ids + "
                    "runbook.active_boundary + project.region"
                ),
        }
        for path, document in by_path.items():
            with self.subTest(path=path):
                self.assertEqual(
                    document["provenance"]["need_from_owner"],
                    "interaction.owner_action_kind",
                )
                self.assertIn(
                    "routing.next_prompt", document["provenance"]["next_action"]
                )
                self.assertTrue(all(item["source"] for item in document["fields"]))
                self.assertTrue(all(item["source"] for item in document["claims"]))
        for (path, label), source in expected_examples.items():
            field = next(
                item for item in by_path[path]["fields"] if item["label"] == label
            )
            self.assertEqual(field["source"], source)
        deployment_claim = next(
            item
            for item in by_path["docs/project/VERIFY.md"]["claims"]
            if item["claim"] == "Application is deployed"
        )
        self.assertIn("acceptance_evidence_ids", deployment_claim["source"])

    def test_local_evidence_counts_use_typed_canonical_rows(self) -> None:
        verify = canonical_sources()["docs/project/VERIFY.md"]
        verify = re.sub(
            r"(?m)^\| EV-0001 \|.*$",
            (
                "| EV-0001 | TASK-001 | python -m unittest | passed | alice | "
                "2026-07-17T12:00:00-07:00 | commit: "
                + "a" * 40
                + " | docs/project/VERIFY.md#ev-0001 | LOCAL_PASS |"
            ),
            verify,
            count=1,
        )
        verify = re.sub(
            r"(?m)^\| EV-0101 \|.*$",
            (
                "| EV-0101 | FR-001 | TASK-001 | Primary outcome succeeds | "
                "failed local check | NOT_APPLICABLE | current artifact | FAILED |"
            ),
            verify,
            count=1,
        )
        by_path = self.summary_specifications(
            verify_text=verify,
            release_decision="READY_TO_DEPLOY",
        )
        fields = {
            item["label"]: item["value"]
            for item in by_path["docs/project/VERIFY.md"]["fields"]
        }
        self.assertEqual(fields["Locally observed evidence"], "1")
        self.assertEqual(fields["Failed or stale evidence"], "1")
        claim = next(
            item
            for item in by_path["docs/project/VERIFY.md"]["claims"]
            if item["claim"] == "Local release checks passed"
        )
        self.assertEqual(claim["maturity"], "Locally observed")
        self.assertEqual(claim["evidence"], "EV-0001")

    def test_aws_guidance_requires_observed_canonical_evidence(self) -> None:
        unobserved = self.summary_specifications()
        claim = next(
            item
            for item in unobserved["docs/project/VERIFY.md"]["claims"]
            if item["claim"] == "Current AWS guidance informed the plan"
        )
        self.assertEqual(claim["maturity"], "Not yet observed")
        self.assertEqual(claim["evidence"], "None")

        observed = self.summary_specifications(
            aws_core_usage={
                "DESIGN-10": {
                    "status": "OBSERVED",
                    "phase": "DESIGN-10",
                    "chains": [
                        {
                            "discovery_id": "AWS-DISC-0002",
                            "skill_identifier": "aws-architecture",
                            "official_references": [
                                "https://docs.aws.amazon.com/wellarchitected/"
                                "latest/framework/welcome.html"
                            ],
                        }
                    ],
                }
            },
            req_aws_core_materiality="REQUIRED",
        )
        claim = next(
            item
            for item in observed["docs/project/VERIFY.md"]["claims"]
            if item["claim"] == "Current AWS guidance informed the plan"
        )
        self.assertEqual(claim["maturity"], "Source verified")
        self.assertEqual(claim["evidence"], "AWS-DISC-0002")

    def test_active_bugfix_summary_uses_recorded_defect_state(self) -> None:
        source = canonical_sources()["docs/project/BUGFIX.md"]
        source = source.replace("- Title: TODO", "- Title: Uploads remain queued", 1)
        source = source.replace(
            "- Environment: TODO", "- Environment: Development", 1
        )
        source = source.replace(
            "- Related PRD requirements: TODO",
            "- Related PRD requirements: FR-001",
            1,
        )
        source = source.replace(
            "- User impact: TODO",
            "- User impact: Users cannot view the uploaded file",
            1,
        )
        source = source.replace(
            "### Actual result\n\nTODO",
            "### Actual result\n\nThe upload remains queued.",
            1,
        )
        source = source.replace(
            "### Confirmed evidence\n\n- TODO",
            "### Confirmed evidence\n\n- The worker never receives the queued item.",
            1,
        )
        source = source.replace(
            "- Allowed scope: TODO", "- Allowed scope: app/upload_worker.py", 1
        )
        source = source.replace(
            "- [ ] Root cause is supported by evidence",
            "- [x] Root cause is supported by evidence",
            1,
        )
        by_path = self.summary_specifications(bugfix_text=source)
        fields = {
            item["label"]: item["value"]
            for item in by_path["docs/project/BUGFIX.md"]["fields"]
        }
        self.assertEqual(fields["Defect"], "Uploads remain queued")
        self.assertEqual(
            fields["User impact"], "Users cannot view the uploaded file"
        )
        self.assertEqual(fields["Reproduction"], "Recorded")
        self.assertEqual(fields["Root cause"], "Confirmed")
        self.assertEqual(fields["Repair"], "Bounded")
        self.assertEqual(fields["Regression evidence"], "In progress")

    def test_untouched_template_summaries_are_current_and_deterministic(self) -> None:
        specifications = template_specifications()
        first, first_issues = project_document_summaries(
            canonical_sources(), specifications
        )
        second, second_issues = project_document_summaries(
            canonical_sources(), specifications
        )

        self.assertEqual(first_issues, [])
        self.assertEqual(second_issues, [])
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], 1)
        self.assertEqual(first["authority"], SUMMARY_AUTHORITY)
        self.assertEqual(first["status"], "CURRENT")
        self.assertIsNone(first["repair"])
        self.assertEqual(
            [document["path"] for document in first["documents"]],
            list(DOCUMENT_PATHS),
        )
        for document in first["documents"]:
            self.assertEqual(document["status"], "CURRENT")
            self.assertEqual(document["authority"], SUMMARY_AUTHORITY)
            self.assertNotIn("canonical_sha256", document)
            self.assertRegex(document["summary_basis_sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(document["rendered_sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(document["heading"], "Current state")

    def test_each_first_screen_is_compact_current_and_owner_safe(self) -> None:
        for path in DOCUMENT_PATHS:
            with self.subTest(path=path):
                source = canonical_sources()[path]
                lines = first_screen(source)
                self.assertGreaterEqual(len(lines), 25)
                self.assertLessEqual(len(lines), 40)
                self.assertEqual(
                    sum(line.startswith("| Need from you |") for line in lines),
                    1,
                )
                visible = "\n".join(lines)
                summary = source[
                    source.index(SUMMARY_BEGIN) : source.index(SUMMARY_END)
                ]
                self.assertNotIn("{{", summary)
                self.assertNotIn("sha256:", visible)
                self.assertNotIn("R-", visible)
                private_paths = (
                    r"[A-Z]:\\" + "Users" + r"\\|/" + "Users" + r"/|/" + "home" + r"/"
                )
                self.assertNotRegex(visible, private_paths)

    def test_document_specific_fields_and_verify_claims_are_rendered(self) -> None:
        projected, _ = project_document_summaries(
            canonical_sources(), template_specifications()
        )
        by_path = {document["path"]: document for document in projected["documents"]}
        required = {
            "docs/project/README.md": {
                "Phase",
                "Overall status",
                "Last completed milestone",
                "Gate A",
                "Gate B",
                "AWS deployment",
            },
            "docs/project/PRD.md": {
                "Product outcome",
                "First-release boundary",
                "Requirements",
                "Technical design",
                "Region and cost",
                "Construction authorization",
            },
            "docs/project/TASKS.md": {
                "Progress",
                "Current wave",
                "Active task",
                "Blocker",
                "Last passing checkpoint",
            },
            "docs/project/VERIFY.md": {
                "Release result",
                "Locally observed evidence",
                "Failed or stale evidence",
                "Still unobserved",
            },
            "docs/project/RUNBOOK.md": {
                "Environment",
                "Deployment state",
                "Current AWS authority",
                "Deployment approval",
                "Teardown approval",
            },
            "docs/project/BUGFIX.md": {
                "Status",
                "Defect",
                "User impact",
                "Environment",
                "Related requirements",
            },
        }
        for path, labels in required.items():
            actual = {field["label"] for field in by_path[path]["fields"]}
            self.assertTrue(labels.issubset(actual), (path, labels - actual))

        task_labels = {
            field["label"] for field in by_path["docs/project/TASKS.md"]["fields"]
        }
        self.assertNotIn("Last known-green commit", task_labels)

        verify_source = canonical_sources()["docs/project/VERIFY.md"]
        self.assertIn(
            "| Claim | Current maturity | Evidence | Limitation |", verify_source
        )
        self.assertIn("Application is deployed", verify_source)
        self.assertIn("Not yet observed", verify_source)

    def test_stale_summary_is_agent_correctable(self) -> None:
        sources = canonical_sources()
        sources["docs/project/PRD.md"] = sources["docs/project/PRD.md"].replace(
            "| Product outcome | Not yet confirmed |",
            "| Product outcome | Hand-edited value |",
            1,
        )
        projected, issues = project_document_summaries(
            sources, template_specifications()
        )
        self.assertEqual(projected["status"], "STALE")
        self.assertEqual(
            projected["repair"],
            {
                "responsible_party": "CODEX",
                "action_kind": "CORRECT_AND_REVALIDATE",
                "automatic_continuation_allowed": True,
            },
        )
        self.assertEqual(
            [(issue["code"], issue["path"]) for issue in issues],
            [("DOCUMENT_SUMMARY_STALE", "docs/project/PRD.md")],
        )

        context = doctor.Context(REPOSITORY_ROOT)
        context.error(
            "DOCUMENT_SUMMARY_STALE",
            "Visible project summary differs from canonical state",
            "docs/project/PRD.md",
        )
        remediation = doctor.derive_remediation(
            context,
            classification="UNCONFIGURED_TEMPLATE",
            gate_a="BLOCKED",
            gate_b="BLOCKED",
            envelope={},
            tasks=doctor.TaskSummary(),
            owner_stage_hint="DEFINE",
        )
        self.assertEqual(
            remediation["next_action"],
            {
                "responsible_party": "CODEX",
                "action_kind": "CORRECT_AND_REVALIDATE",
                "automatic_continuation_allowed": True,
            },
        )
        self.assertEqual(remediation["items"][0]["category"], "AGENT_CORRECTION")

    def test_missing_ambiguous_and_private_sources_fail_closed(self) -> None:
        specifications = template_specifications()

        missing_sources = canonical_sources()
        del missing_sources["docs/project/BUGFIX.md"]
        projected, issues = project_document_summaries(missing_sources, specifications)
        self.assertEqual(projected["status"], "BLOCKED")
        self.assertEqual(issues[0]["code"], "DOCUMENT_SUMMARY_SOURCE_INVALID")

        duplicate_sources = canonical_sources()
        duplicate_sources["docs/project/README.md"] += "\n" + SUMMARY_BEGIN + "\n"
        projected, issues = project_document_summaries(
            duplicate_sources, specifications
        )
        self.assertEqual(projected["status"], "BLOCKED")
        self.assertEqual(issues[0]["code"], "DOCUMENT_SUMMARY_UNSAFE")

        unsafe = copy.deepcopy(specifications)
        unsafe[0]["fields"][0]["value"] = "C:" + "\\Users\\owner\\private"
        projected, issues = project_document_summaries(canonical_sources(), unsafe)
        self.assertEqual(projected["status"], "BLOCKED")
        self.assertEqual(issues[0]["code"], "DOCUMENT_SUMMARY_UNSAFE")

    def test_generated_block_is_masked_and_excluded_from_canonical_bytes(
        self,
    ) -> None:
        first = (
            "# Project\n"
            + SUMMARY_BEGIN
            + "\n## Injected canonical heading\n| Gate A | APPROVED |\n"
            + SUMMARY_END
            + "\n## Canonical record\nValue\n"
        )
        second = (
            "# Project\n"
            + SUMMARY_BEGIN
            + "\nA much longer generated value\n\nwith another line\n"
            + SUMMARY_END
            + "\n## Canonical record\nValue\n"
        )
        masked = strip_generated_summary(first)
        self.assertEqual(len(masked), len(first))
        self.assertEqual(masked.count("\n"), first.count("\n"))
        self.assertNotIn("Injected canonical heading", masked)
        self.assertIn("## Canonical record", masked)
        self.assertEqual(
            canonical_bytes_without_generated_summary(first),
            canonical_bytes_without_generated_summary(second),
        )
        reversed_markers = (
            "## Injected\n"
            + SUMMARY_END
            + "\n## More injected state\n"
            + SUMMARY_BEGIN
            + "\n"
        )
        masked_reversed = strip_generated_summary(reversed_markers)
        self.assertNotIn("Injected", masked_reversed)
        self.assertNotIn("More injected state", masked_reversed)

    def test_rendering_is_lf_normalized_and_wrapped_once(self) -> None:
        specification = template_specifications()[0]
        rendered = render_summary_markdown(specification)
        wrapped = wrapped_summary_markdown(specification)
        self.assertNotIn("\r", rendered)
        self.assertTrue(rendered.endswith("\n"))
        self.assertEqual(wrapped.count(SUMMARY_BEGIN), 1)
        self.assertEqual(wrapped.count(SUMMARY_END), 1)
        self.assertIn(rendered, wrapped)

    def test_project_rules_define_the_first_screen_contract(self) -> None:
        project_rules = (REPOSITORY_ROOT / "docs" / "project" / "AGENTS.md").read_text(
            encoding="utf-8"
        )
        workflow = (REPOSITORY_ROOT / "docs" / "WORKFLOW.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("25-40 visible nonblank lines", project_rules)
        self.assertIn("Engine-derived `Current state`", project_rules)
        self.assertIn("one owner need or `Nothing`", workflow)
