from __future__ import annotations

import unittest

from scripts import bootstrap_doctor as doctor
from scripts import fastlane_contracts as contracts
from scripts import task_waves
from scripts.fastlane_engine import api
from scripts.fastlane_engine.core.contracts import fenced_command_payloads
from scripts.fastlane_engine.design.harness import HARNESS_HEADERS, HARNESS_HEADING
from scripts.fastlane_engine.deliver import parse_harness_evidence
from tests.test_task_waves import harness_evidence_document, harness_evidence_row


TASK_HEADERS = " | ".join(contracts.TASK_COMPLETION_EVIDENCE_HEADERS)
CHECKPOINT_HEADERS = " | ".join(contracts.CHECKPOINT_HEADERS)


def task_evidence_document(*rows: str) -> str:
    separator = (
        "|" + "|".join("---" for _ in contracts.TASK_COMPLETION_EVIDENCE_HEADERS) + "|"
    )
    body = "\n".join(rows)
    return (
        "# Verification\n\n"
        "## Task completion evidence\n\n"
        f"| {TASK_HEADERS} |\n"
        f"{separator}\n"
        f"{body}\n\n"
        "## Verification matrix\n"
    )


def task_evidence_row(
    evidence_id: str = "EV-0001",
    command: str = "python -m unittest",
) -> str:
    return (
        f"| {evidence_id} | TASK-0001 | {command} | passed | coordinator | "
        "2026-08-04T12:00:00+00:00 | "
        "commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa | "
        "docs/project/VERIFY.md#ev-0001 | LOCAL_PASS |"
    )


def checkpoint_document(*rows: str) -> str:
    separator = "|" + "|".join("---" for _ in contracts.CHECKPOINT_HEADERS) + "|"
    body = "\n".join(rows)
    return (
        "# Tasks\n\n"
        "## Checkpoints and resume\n\n"
        f"| {CHECKPOINT_HEADERS} |\n"
        f"{separator}\n"
        f"{body}\n\n"
        "### Archived task-plan registry\n\n"
        "| Plan revision | Plan state | REQ / DES / AUTH | Archive commit | "
        "Reason replaced |\n"
        "|---|---|---|---|---|\n"
        "| NONE | UNINITIALIZED | REQ-0001 / DES-0001 / AUTH-0001 | NONE | none |\n\n"
        "## Task definitions\n"
    )


def checkpoint_row(
    checkpoint_id: str = "CP-0001",
    dirty: str = "NONE",
    blockers: str = "continue",
) -> str:
    return (
        f"| {checkpoint_id} | RUN-0001 | 2026-08-04T12:00:00+00:00 | "
        "REQ-0001 / DES-0001 / AUTH-0001 | "
        f"Commit: `abcdef1`; Dirty: {dirty} | TASK-0001 DONE attempts=1/2 | "
        f"EV-0001; external: NONE | {blockers} |"
    )


class SharedMarkdownGrammarTests(unittest.TestCase):
    def test_command_payload_round_trip_through_prd_task_fence_and_evidence(
        self,
    ) -> None:
        commands = (
            'python -c "a  b"',
            'python -c "a\tb"',
            'python -c "a\u00a0b"',
            'python -c "a|b"',
            r'python -c "C:\\work\file"',
            'pwsh -Command "Write-Output `"a`""',
            "python -m unittest\u00a0",
            "python -m unittest ",
        )
        for command in commands:
            for newline in ("\n", "\r\n"):
                with self.subTest(command=command, newline=repr(newline)):
                    encoded = (
                        "`" + command.replace("\\", "\\\\").replace("|", "\\|") + "`"
                    )
                    values = (
                        "HARNESS-001",
                        "Unit",
                        "Python unittest",
                        "Before completion",
                        "REQ-0001, DES-0001, TECH-0001",
                        encoded,
                        "docs/project/VERIFY.md#harness-execution-evidence",
                        "REQUIRED",
                    )
                    table = newline.join(
                        (
                            "| " + " | ".join(HARNESS_HEADERS) + " |",
                            "|" + "---|" * len(HARNESS_HEADERS),
                            "|\t" + "\t|\t".join(values) + "\t|",
                        )
                    )
                    prd, issues = doctor.derive_harness_contract(
                        HARNESS_HEADING + newline * 2 + table,
                        {"REQ-0001", "DES-0001", "TECH-0001"},
                        required=True,
                        grandfather_approved_v1=False,
                    )
                    expected_issues = (
                        [
                            "HARNESS-001: Exact command or API must be one concrete command"
                        ]
                        if command in commands[3:6]
                        else []
                    )
                    self.assertEqual(issues, expected_issues)
                    self.assertEqual(prd.rows[0].exact_command, command)
                    projected, present = api.parse_task_harness_projection(
                        table, "TASK-001"
                    )
                    self.assertTrue(present)
                    self.assertEqual(projected["HARNESS-001"].exact_command, command)
                    fenced = newline.join(("  ~~~powershell", "  " + command, "  ~~~~"))
                    self.assertEqual(fenced_command_payloads(fenced), [command])
                    evidence = harness_evidence_document(
                        harness_evidence_row(
                            evidence_id="EV-2002",
                            status="LOCAL_PASS",
                            layer="Unit",
                            observed_at="2026-07-17T00:01:00+00:00",
                            observed_result="exit=0",
                            command=encoded,
                        )
                    ).replace("\n", newline)
                    self.assertEqual(
                        parse_harness_evidence(evidence)[0].exact_command, command
                    )

    def test_fence_extraction_preserves_literal_markers_and_requires_closure(
        self,
    ) -> None:
        payload = '`python -c "a  b"`\u00a0'
        self.assertEqual(fenced_command_payloads(f"```text\n{payload}\n```"), [payload])
        self.assertEqual(fenced_command_payloads(f"```text\n{payload}"), [])
        self.assertEqual(
            fenced_command_payloads("~~~~text\n```\n~~~\n~~~~"), ["```", "~~~"]
        )

    def test_fence_masking_accepts_longer_matching_closer(self) -> None:
        source = (
            "before\r\n"
            "```markdown\r\n"
            "## Task completion evidence\r\n"
            "````\r\n"
            "## Task completion evidence\r\n"
        )
        masked = contracts.without_fenced_code(source)
        self.assertEqual(len(masked), len(source))
        self.assertEqual(masked.count("## Task completion evidence"), 1)
        self.assertEqual(masked, doctor.without_fenced_code(source))
        self.assertEqual(masked, task_waves.without_fenced_code(source))

    def test_fence_masking_ignores_mismatched_or_shorter_markers(self) -> None:
        source = "~~~~text\n```\n~~~\n## still fenced\n~~~~\n## visible\n"
        masked = contracts.without_fenced_code(source)
        self.assertNotIn("still fenced", masked)
        self.assertIn("## visible", masked)

    def test_table_splitter_honors_only_markdown_escapes(self) -> None:
        line = r"| one\|two | C:\temp\file | slash\\value |"
        expected = ["one|two", r"C:\temp\file", r"slash\value"]
        self.assertEqual(contracts.split_markdown_table_row(line), expected)
        self.assertEqual(doctor.split_markdown_table_row(line), expected)
        self.assertEqual(task_waves.split_markdown_table_row(line), expected)


class SharedEvidenceAndCheckpointTests(unittest.TestCase):
    def test_task_evidence_parity_with_escaped_pipe_and_fenced_decoy(self) -> None:
        row = task_evidence_row(command=r"python -c \"print('a\|b')\"")
        document = (
            "```markdown\n"
            + task_evidence_document(task_evidence_row("EV-9999"))
            + "````\n"
            + task_evidence_document(row)
        )
        doctor_rows = doctor.parse_task_completion_evidence(document)
        task_rows = task_waves.parse_task_completion_evidence(document)
        self.assertEqual(
            [tuple(vars(row).values()) for row in doctor_rows],
            [tuple(vars(row).values()) for row in task_rows],
        )
        self.assertIn("a|b", doctor_rows[0].command_or_observation)

    def test_discontiguous_task_evidence_rows_fail_in_both_components(self) -> None:
        document = task_evidence_document(
            task_evidence_row("EV-0001"),
            "",
            task_evidence_row("EV-0002"),
        )
        parsers = (
            doctor.parse_task_completion_evidence,
            task_waves.parse_task_completion_evidence,
        )
        for parser in parsers:
            with self.subTest(parser=parser.__module__), self.assertRaises(ValueError):
                parser(document)

    def test_checkpoint_parity_handles_fence_and_escaped_pipe(self) -> None:
        document = (
            "~~~markdown\n"
            + checkpoint_document(checkpoint_row("CP-9999"))
            + "~~~~\n"
            + checkpoint_document(checkpoint_row(blockers=r"retry\|then continue"))
        )
        doctor_rows = doctor.parse_checkpoint_rows(document)
        task_rows = task_waves.parse_checkpoint_rows(document)
        self.assertEqual(
            [tuple(vars(row).values()) for row in doctor_rows],
            [tuple(vars(row).values()) for row in task_rows],
        )
        self.assertEqual(doctor_rows[0].blockers_and_next, "retry|then continue")

    def test_malformed_or_discontiguous_checkpoints_fail(self) -> None:
        malformed = checkpoint_document(checkpoint_row()).replace(
            f"| {CHECKPOINT_HEADERS} |",
            "| Checkpoint | Run | Time | wrong | Commit | Outcomes | Evidence | Next |",
        )
        discontiguous = checkpoint_document(
            checkpoint_row("CP-0001"),
            "",
            checkpoint_row("CP-0002"),
        )
        for document in (malformed, discontiguous):
            for parser in (
                doctor.parse_checkpoint_rows,
                task_waves.parse_checkpoint_rows,
            ):
                with (
                    self.subTest(parser=parser.__module__),
                    self.assertRaises(ValueError),
                ):
                    parser(document)

    def test_checkpoint_git_receipt_parity(self) -> None:
        document = checkpoint_document(
            checkpoint_row(dirty="app/**, docs/project/VERIFY.md")
        )
        doctor_result = doctor.parse_checkpoint_git_receipt(document, "CP-0001")
        task_row = task_waves.parse_checkpoint_rows(document)[0]
        task_result = task_waves.parse_checkpoint_git_receipt(task_row, "CP-0001")
        self.assertEqual(doctor_result, task_result)


class SharedBoundaryGrammarTests(unittest.TestCase):
    def test_path_boundaries_are_case_insensitive_and_hierarchical(self) -> None:
        cases = (
            ("app/**", "APP/service/main.py", True),
            ("app/main.py", "app/main.py", True),
            ("app/main.py", "app/main.py/**", False),
            ("app/**", "apps/main.py", False),
        )
        for allowed, requested, expected in cases:
            with self.subTest(allowed=allowed, requested=requested):
                self.assertEqual(
                    doctor.path_boundary_contains(allowed, requested), expected
                )
                self.assertEqual(
                    task_waves.path_boundary_contains(allowed, requested), expected
                )

        overlap_cases = (
            ("app", "app/service/main.py", True),
            ("app/**", "app/service/**", True),
            ("app-one/**", "app-two/**", False),
        )
        for first, second, expected in overlap_cases:
            with self.subTest(first=first, second=second):
                self.assertEqual(
                    doctor.path_boundaries_overlap(first, second), expected
                )
                self.assertEqual(
                    task_waves.write_boundaries_overlap(first, second), expected
                )

    def test_external_targets_normalize_trailing_separators(self) -> None:
        cases = (
            ("aws:stack/", "AWS:STACK", True),
            ("github:repo#", "github:repo#issues", True),
            ("aws:stack/dev", "aws:stack/prod", False),
        )
        for first, second, expected in cases:
            with self.subTest(first=first, second=second):
                self.assertEqual(
                    doctor.external_targets_overlap(first, second), expected
                )
                self.assertEqual(
                    task_waves.external_targets_overlap(first, second), expected
                )


if __name__ == "__main__":
    unittest.main()
