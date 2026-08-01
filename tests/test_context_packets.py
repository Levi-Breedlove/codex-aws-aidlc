from __future__ import annotations

import hashlib
import re
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import bootstrap_doctor as doctor
from fastlane_context import (
    SliceRequest,
    canonical_source_bytes,
    resolve_context_packet,
)


def request(
    path: str,
    selector_kind: str,
    selector: str,
    *,
    priority: int = 0,
    required: bool = False,
) -> SliceRequest:
    return SliceRequest(
        path=path,
        selector_kind=selector_kind,
        selector=selector,
        priority=priority,
        reason="test basis",
        required=required,
    )


class ContextPacketTests(unittest.TestCase):
    def test_canonical_source_bytes_and_heading_range_are_digest_bound(self) -> None:
        text = "# Target\r\nvalue\r\n\r\n# Later\r\nignored\r\n"
        packet, issues = resolve_context_packet(
            [request("doc.md", "HEADING", "Target", required=True)],
            [],
            {"doc.md": text},
            doctor._context_selector_span,
            maximum_initial_source_bytes=12_000,
        )
        self.assertEqual(issues, [])
        self.assertEqual(packet["budget_status"], "WITHIN_LIMIT")
        selected = packet["resolved_initial_slices"][0]
        canonical = canonical_source_bytes("# Target\r\nvalue\r\n\r\n")
        self.assertEqual(selected["start_line"], 1)
        self.assertEqual(selected["end_line"], 3)
        self.assertEqual(selected["source_bytes"], len(canonical))
        self.assertEqual(
            selected["canonical_sha256"],
            "sha256:" + hashlib.sha256(canonical).hexdigest(),
        )
        self.assertTrue(canonical.endswith(b"\n"))
        self.assertFalse(canonical.endswith(b"\n\n"))

    def test_budget_moves_lower_priority_and_reports_one_required_overflow(
        self,
    ) -> None:
        sources = {"a.md": "alpha\n", "b.md": "bravo\n"}
        first = request("a.md", "WHOLE_FILE", "a.md", required=True)
        second = request("b.md", "WHOLE_FILE", "b.md", priority=1, required=False)
        packet, issues = resolve_context_packet(
            [first, second],
            [],
            sources,
            doctor._context_selector_span,
            maximum_initial_source_bytes=7,
        )
        self.assertEqual(issues, [])
        self.assertEqual(packet["budget_status"], "WITHIN_LIMIT")
        self.assertEqual(
            [item["path"] for item in packet["resolved_initial_slices"]],
            ["a.md"],
        )
        self.assertEqual(
            [item["path"] for item in packet["resolved_on_demand_slices"]],
            ["b.md"],
        )

        required_second = request(
            "b.md", "WHOLE_FILE", "b.md", priority=1, required=True
        )
        overflow, issues = resolve_context_packet(
            [first, required_second],
            [],
            sources,
            doctor._context_selector_span,
            maximum_initial_source_bytes=7,
        )
        self.assertEqual(issues, [])
        self.assertEqual(overflow["budget_status"], "OVERSIZED_REQUIRED_RECORD")
        self.assertGreater(overflow["actual_initial_source_bytes"], 7)
        self.assertEqual(len(overflow["overflow_records"]), 1)

        duplicate, issues = resolve_context_packet(
            [first],
            [first],
            sources,
            doctor._context_selector_span,
            maximum_initial_source_bytes=7,
        )
        self.assertEqual(issues, [])
        self.assertEqual(duplicate["resolved_on_demand_slices"], [])

        third = request("c.md", "WHOLE_FILE", "c.md", priority=2, required=True)
        invalid, issues = resolve_context_packet(
            [first, required_second, third],
            [],
            {**sources, "c.md": "charlie\n"},
            doctor._context_selector_span,
            maximum_initial_source_bytes=7,
        )
        self.assertEqual(invalid["budget_status"], "SOURCE_INVALID")
        self.assertTrue(any("more than one" in item["reason"] for item in issues))

    def test_required_state_precedes_optional_phase_guidance(self) -> None:
        sources = {
            "phase.md": "complete procedural guidance\n",
            "state.md": "state\n",
        }
        phase = request(
            "phase.md",
            "WHOLE_FILE",
            "phase.md",
            priority=0,
            required=False,
        )
        state = request(
            "state.md",
            "WHOLE_FILE",
            "state.md",
            priority=2,
            required=True,
        )

        packet, issues = resolve_context_packet(
            [phase, state],
            [],
            sources,
            doctor._context_selector_span,
            maximum_initial_source_bytes=7,
        )

        self.assertEqual(issues, [])
        self.assertEqual(packet["budget_status"], "WITHIN_LIMIT")
        self.assertEqual(
            [item["path"] for item in packet["resolved_initial_slices"]],
            ["state.md"],
        )
        self.assertEqual(
            [item["path"] for item in packet["resolved_on_demand_slices"]],
            ["phase.md"],
        )
        self.assertEqual(packet["actual_initial_source_bytes"], 6)

    def test_missing_ambiguous_and_overlapping_sources_fail_closed(self) -> None:
        missing, issues = resolve_context_packet(
            [request("missing.md", "WHOLE_FILE", "missing.md", required=True)],
            [],
            {},
            doctor._context_selector_span,
            maximum_initial_source_bytes=12_000,
        )
        self.assertEqual(missing["budget_status"], "SOURCE_INVALID")
        self.assertIn("unavailable", issues[0]["reason"])

        duplicate = "# Same\none\n# Same\ntwo\n"
        ambiguous, issues = resolve_context_packet(
            [request("duplicate.md", "HEADING", "Same", required=True)],
            [],
            {"duplicate.md": duplicate},
            doctor._context_selector_span,
            maximum_initial_source_bytes=12_000,
        )
        self.assertEqual(ambiguous["budget_status"], "SOURCE_INVALID")
        self.assertIn("found 2", issues[0]["reason"])

        nested = "# Outer\nvalue\n## Inner\nvalue\n"
        overlapping, issues = resolve_context_packet(
            [request("nested.md", "HEADING", "Outer", required=True)],
            [request("nested.md", "HEADING", "Inner")],
            {"nested.md": nested},
            doctor._context_selector_span,
            maximum_initial_source_bytes=12_000,
        )
        self.assertEqual(overlapping["budget_status"], "SOURCE_INVALID")
        self.assertTrue(any("overlapping" in item["reason"] for item in issues))

    def test_aws40_and_aws50_context_packets_defer_full_procedures(self) -> None:
        tasks = doctor.TaskSummary(
            statuses={"TASK-0001": "DONE"},
        )

        def assert_deferred(plan: dict[str, object], path: str, selector: str) -> None:
            reference = f"{path}#{selector}"
            self.assertNotIn(reference, plan["source_slices"])
            self.assertIn(reference, plan["on_demand_slices"])
            resolved = next(
                item
                for item in plan["resolved_on_demand_slices"]
                if item["path"] == path and item["selector"] == selector
            )
            self.assertGreaterEqual(resolved["start_line"], 1)
            self.assertGreaterEqual(resolved["end_line"], resolved["start_line"])
            self.assertRegex(resolved["canonical_sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertGreater(resolved["source_bytes"], 0)

        coverage = doctor.CoverageContract(
            status="READY",
            basis_ids=("REQ-0001", "SEC-001"),
        )
        source_texts = {
            path: (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
            for path in (
                ".agents/skills/fastlane/references/deliver.md",
                doctor.PRD_FILE,
                doctor.TASKS_FILE,
                doctor.VERIFY_FILE,
                doctor.RUNBOOK_FILE,
            )
        }
        aws_40 = doctor.derive_context_plan(
            {
                "owner_stage": "DELIVER",
                "route_reason_code": "AWS_RESIDUAL_REVIEW",
                "blocking_ids": [],
            },
            tasks,
            coverage,
            next_prompt="AWS-40",
            source_texts=source_texts,
        )
        aws_50 = doctor.derive_context_plan(
            {
                "owner_stage": "DELIVER",
                "route_reason_code": "WAITING_AWS_TEARDOWN_AUTH",
                "blocking_ids": [],
            },
            tasks,
            coverage,
            next_prompt="AWS-50",
            source_texts=source_texts,
        )

        self.assertIn(
            f"{doctor.VERIFY_FILE}#Teardown reconciliation evidence",
            aws_40["source_slices"],
        )
        assert_deferred(
            aws_40,
            doctor.RUNBOOK_FILE,
            "14. Residual-resource and billing verification",
        )
        self.assertIn(
            f"{doctor.VERIFY_FILE}#Teardown reconciliation evidence",
            aws_50["source_slices"],
        )
        assert_deferred(aws_50, doctor.VERIFY_FILE, "Action authorization provenance")
        assert_deferred(aws_50, doctor.RUNBOOK_FILE, "Conditional AWS action receipts")
        assert_deferred(aws_50, doctor.RUNBOOK_FILE, "13. Teardown and decommissioning")
        for reason in (
            "AWS_RESIDUAL_REVIEW_COMPLETE",
            "AWS_RESIDUALS_REMAIN",
            "AWS_RESIDUAL_REVIEW_BLOCKED",
            "AWS_TEARDOWN_COMPLETE",
        ):
            with self.subTest(reason=reason):
                terminal = doctor.derive_context_plan(
                    {
                        "owner_stage": "DELIVER",
                        "route_reason_code": reason,
                        "blocking_ids": [],
                    },
                    tasks,
                    coverage,
                    next_prompt="STOP",
                    source_texts=source_texts,
                )
                self.assertIn(
                    f"{doctor.VERIFY_FILE}#Teardown reconciliation evidence",
                    terminal["source_slices"],
                )
                assert_deferred(
                    terminal,
                    doctor.RUNBOOK_FILE,
                    "14. Residual-resource and billing verification",
                )
        self.assertEqual(
            len(aws_40["source_slices"]), len(set(aws_40["source_slices"]))
        )
        self.assertEqual(
            len(aws_50["source_slices"]), len(set(aws_50["source_slices"]))
        )

    def test_context_source_failure_uses_remediation_contract(self) -> None:
        ctx = doctor.Context(REPOSITORY_ROOT)
        report = doctor.build_report(
            ctx,
            "INTAKE_REQUIRED",
            "INTAKE-10",
            {"gate_a": "BLOCKED", "gate_b": "BLOCKED"},
            doctor.TaskSummary(),
            state={
                "setup": {"status": "CONFIGURED"},
                "project": {"mode": "greenfield", "aws_lane": "documentation-only"},
            },
            coverage_contract=doctor.CoverageContract(status="READY"),
        )
        self.assertEqual(report["context_plan"]["budget_status"], "SOURCE_INVALID")
        item = next(
            item
            for item in report["remediation"]["items"]
            if item["diagnostic_code"] == "CONTEXT_SOURCE_INVALID"
        )
        self.assertEqual(item["responsible_party"], "HUMAN_REVIEWER")
        self.assertEqual(item["category"], "MANUAL_SAFETY_REVIEW")
        self.assertFalse(item["automatic_correction_allowed"])
        self.assertEqual(
            report["remediation"]["next_action"]["action_kind"],
            "REVIEW_SAFETY_BLOCKER",
        )

    def test_aws30_context_is_deployment_specific_and_read_only(self) -> None:
        plan = doctor.derive_context_plan(
            {
                "owner_stage": "DELIVER",
                "route_reason_code": "AWS_DEPLOYMENT_RECONCILIATION",
                "blocking_ids": [],
            },
            doctor.TaskSummary(statuses={"TASK-0001": "DONE"}),
            doctor.CoverageContract(status="READY", basis_ids=("REQ-0001", "SEC-001")),
            next_prompt="AWS-30",
        )
        source_slices = plan["source_slices"]
        on_demand_slices = plan["on_demand_slices"]
        for required in (
            f"{doctor.VERIFY_FILE}#AWS deployment action and reconciliation evidence",
            f"{doctor.VERIFY_FILE}#Verification matrix",
            f"{doctor.VERIFY_FILE}#Current release decision",
        ):
            self.assertIn(required, source_slices)
        for historical_authority in (
            f"{doctor.VERIFY_FILE}#Action authorization provenance",
            f"{doctor.VERIFY_FILE}#Read-only AWS preflight evidence",
            f"{doctor.RUNBOOK_FILE}#Conditional AWS action receipts",
            f"{doctor.RUNBOOK_FILE}#Read-only AWS preflight",
        ):
            self.assertIn(historical_authority, on_demand_slices)
            self.assertNotIn(historical_authority, source_slices)
        for excluded in (
            f"{doctor.VERIFY_FILE}#Teardown reconciliation evidence",
            f"{doctor.RUNBOOK_FILE}#13. Teardown and decommissioning",
        ):
            self.assertNotIn(excluded, source_slices)
            self.assertNotIn(excluded, on_demand_slices)
        self.assertEqual(len(source_slices), len(set(source_slices)))
        self.assertEqual(len(on_demand_slices), len(set(on_demand_slices)))

    def test_post_aws30_release_context_preserves_attempt_and_decision_basis(
        self,
    ) -> None:
        plan = doctor.derive_context_plan(
            {
                "owner_stage": "DELIVER",
                "route_reason_code": "RELEASE_REVIEW",
                "blocking_ids": [],
            },
            doctor.TaskSummary(statuses={"TASK-0001": "DONE"}),
            doctor.CoverageContract(status="READY", basis_ids=("REQ-0001", "SEC-001")),
            next_prompt="RELEASE-10",
        )
        source_slices = plan["source_slices"]
        for required in (
            f"{doctor.VERIFY_FILE}#Verification matrix",
            f"{doctor.VERIFY_FILE}#AWS deployment action and reconciliation evidence",
            f"{doctor.VERIFY_FILE}#Current release decision",
        ):
            self.assertIn(required, source_slices)
        self.assertEqual(len(source_slices), len(set(source_slices)))

    def test_design_loads_exact_subsections_and_patterns_only_when_required(
        self,
    ) -> None:
        design_path = ".agents/skills/fastlane/references/design.md"
        patterns_path = ".agents/skills/fastlane/references/diagram-patterns.md"
        prd = (REPOSITORY_ROOT / doctor.PRD_FILE).read_text(encoding="utf-8")
        source_texts = {
            design_path: (REPOSITORY_ROOT / design_path).read_text(encoding="utf-8"),
            patterns_path: (REPOSITORY_ROOT / patterns_path).read_text(
                encoding="utf-8"
            ),
            doctor.PRD_FILE: prd,
            doctor.VERIFY_FILE: (REPOSITORY_ROOT / doctor.VERIFY_FILE).read_text(
                encoding="utf-8"
            ),
        }
        interaction = {
            "owner_stage": "DESIGN",
            "route_reason_code": "DESIGN_REQUIRED",
            "blocking_ids": [],
        }
        coverage = doctor.CoverageContract(
            status="READY",
            work_kind="NEW_BUILD",
            basis_ids=("REQ-0001",),
        )

        incomplete = doctor.derive_context_plan(
            interaction,
            doctor.TaskSummary(),
            coverage,
            next_prompt="DESIGN-10",
            source_texts=source_texts,
        )
        self.assertIn(
            f"{design_path}#Architecture selection and records",
            incomplete["source_slices"],
        )
        self.assertNotIn(design_path, incomplete["source_slices"])
        self.assertIn(patterns_path, incomplete["on_demand_slices"])
        self.assertNotIn(patterns_path, incomplete["source_slices"])
        self.assertLessEqual(incomplete["actual_initial_source_bytes"], 12_000)

        current = prd
        for diagram_id in (
            "DIAGRAM-0001",
            "DIAGRAM-0002",
            "DIAGRAM-0003",
            "DIAGRAM-0004",
        ):
            pattern = (
                rf"(?m)^(\| {diagram_id} \| [^\n]+ \|) NOT_YET_CREATED (\| [^\n]+)$"
            )
            current, count = re.subn(pattern, r"\1 CURRENT \2", current, count=1)
            self.assertEqual(count, 1, diagram_id)
        complete = doctor.derive_context_plan(
            interaction,
            doctor.TaskSummary(),
            coverage,
            next_prompt="DESIGN-10",
            source_texts={**source_texts, doctor.PRD_FILE: current},
        )
        self.assertNotIn(patterns_path, complete["on_demand_slices"])


if __name__ == "__main__":
    unittest.main()
