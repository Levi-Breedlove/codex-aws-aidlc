from __future__ import annotations

import hashlib
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
from fastlane_context import SliceRequest, canonical_source_bytes, resolve_context_packet


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

    def test_budget_moves_lower_priority_and_reports_one_required_overflow(self) -> None:
        sources = {"a.md": "alpha\n", "b.md": "bravo\n"}
        first = request("a.md", "WHOLE_FILE", "a.md", required=True)
        second = request(
            "b.md", "WHOLE_FILE", "b.md", priority=1, required=False
        )
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

    def test_aws40_and_aws50_context_packets_are_phase_specific(self) -> None:
        tasks = doctor.TaskSummary(
            statuses={"TASK-0001": "DONE"},
        )
        coverage = doctor.CoverageContract(
            status="READY",
            basis_ids=("REQ-0001", "SEC-001"),
        )
        aws_40 = doctor.derive_context_plan(
            {
                "owner_stage": "DELIVER",
                "route_reason_code": "AWS_RESIDUAL_REVIEW",
                "blocking_ids": [],
            },
            tasks,
            coverage,
            next_prompt="AWS-40",
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
        )

        self.assertIn(
            f"{doctor.VERIFY_FILE}#Teardown reconciliation evidence",
            aws_40["source_slices"],
        )
        self.assertIn(
            f"{doctor.RUNBOOK_FILE}#14. Residual-resource and billing verification",
            aws_40["source_slices"],
        )
        self.assertIn(
            f"{doctor.VERIFY_FILE}#Action authorization provenance",
            aws_50["source_slices"],
        )
        self.assertIn(
            f"{doctor.VERIFY_FILE}#Teardown reconciliation evidence",
            aws_50["source_slices"],
        )
        self.assertIn(
            f"{doctor.RUNBOOK_FILE}#Conditional AWS action receipts",
            aws_50["source_slices"],
        )
        self.assertIn(
            f"{doctor.RUNBOOK_FILE}#13. Teardown and decommissioning",
            aws_50["source_slices"],
        )
        self.assertNotEqual(aws_40["source_slices"], aws_50["source_slices"])
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
                )
                self.assertIn(
                    f"{doctor.VERIFY_FILE}#Teardown reconciliation evidence",
                    terminal["source_slices"],
                )
                self.assertIn(
                    f"{doctor.RUNBOOK_FILE}#14. Residual-resource and billing verification",
                    terminal["source_slices"],
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


if __name__ == "__main__":
    unittest.main()
