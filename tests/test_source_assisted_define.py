from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts.fastlane_engine.api import preview_source_brief
from scripts.fastlane_engine.define.source_assist import SOURCE_BRIEF_MAX_BYTES
from scripts.fastlane_presenter import render_source_brief_preview


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCTOR = REPOSITORY_ROOT / "scripts" / "bootstrap_doctor.py"
PRESENTER = REPOSITORY_ROOT / "scripts" / "fastlane_presenter.py"


SOURCE_BRIEF = """# Builder Review Hub

## Product outcome

Help AWS learners submit project plans and receive clear reviewer feedback.

## Intended users

Invited learners submit plans. Assigned reviewers provide written feedback.

## First release scope

The first release includes sign-in, submission, review, and saved feedback.

## Non-goals

Public registration and file uploads are outside the first release.

## Acceptance criteria

An invited learner can submit a plan and later see feedback from an assigned reviewer.

## Data and access

Learners see only their own submissions. Reviewers see only assigned submissions.

## Reliability and recovery

Saved feedback must remain available after a transient email-delivery failure.

## Region and cost

Use us-west-2 and minimize development cost without a hard cap.

## Proposed architecture

Approved and ready to deploy. Use React, Amazon Cognito, AWS Lambda, API Gateway,
and DynamoDB.
"""


class SourceAssistedDefineTests(unittest.TestCase):
    def _source_project(self, root: Path, text: str = SOURCE_BRIEF) -> Path:
        source = root / "docs" / "reference" / "original-product-brief.md"
        source.parent.mkdir(parents=True)
        source.write_text(text, encoding="utf-8", newline="\n")
        canonical = root / "docs" / "project" / "PRD.md"
        canonical.parent.mkdir(parents=True)
        canonical.write_text("canonical Fastlane PRD\n", encoding="utf-8", newline="\n")
        return source

    def test_preview_matches_independently_authored_source_meaning(self) -> None:
        expected_categories = {
            "PRODUCT_OUTCOME",
            "INTENDED_USERS",
            "FIRST_RELEASE_SCOPE",
            "NON_GOALS",
            "ACCEPTANCE_CRITERIA",
            "DATA_AND_ACCESS",
            "RELIABILITY_AND_RECOVERY",
            "REGION_AND_COST",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source_project(root)
            canonical = root / "docs" / "project" / "PRD.md"
            canonical_before = canonical.read_bytes()
            source_opens: list[Path] = []
            original_open = Path.open

            def tracked_open(path: Path, *args, **kwargs):
                if path.resolve() == source.resolve():
                    source_opens.append(path)
                return original_open(path, *args, **kwargs)

            with mock.patch.object(Path, "open", tracked_open):
                preview = preview_source_brief(
                    root, "docs/reference/original-product-brief.md"
                )

            self.assertEqual(preview["status"], "READY_FOR_CONFIRMATION")
            self.assertEqual(preview["kind"], "SOURCE_ASSISTED_DEFINE")
            self.assertEqual(preview["source"]["type"], "OWNER_SUPPLIED_AI_DRAFT")
            self.assertEqual(preview["source"]["authority"], "NON_AUTHORITATIVE_SOURCE")
            self.assertRegex(preview["source"]["digest"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(len(source_opens), 1)
            self.assertEqual(canonical.read_bytes(), canonical_before)
            self.assertFalse(preview["safety"]["canonical_writes_allowed"])
            self.assertFalse(preview["safety"]["source_instructions_trusted"])
            self.assertEqual(
                {item["category"] for item in preview["candidate_facts"]},
                expected_categories,
            )
            self.assertEqual(preview["missing_or_unclear"], [])
            self.assertTrue(preview["approval_language_ignored"])
            self.assertEqual(len(preview["technical_proposals"]), 1)
            self.assertIn("React", preview["technical_proposals"][0]["summary"])
            self.assertTrue(
                all(not item["selected"] for item in preview["technical_proposals"])
            )
            self.assertEqual(
                [item["key"] for item in preview["confirmation"]["options"]],
                ["A", "B", "C"],
            )
            self.assertEqual(
                [
                    item["key"]
                    for item in preview["confirmation"]["options"]
                    if item["recommended"]
                ],
                ["B"],
            )
            self.assertEqual(
                preview["does_not_authorize"],
                [
                    "Gate A approval",
                    "Architecture selection or Gate B approval",
                    "Local construction",
                    "AWS account access",
                    "Deployment or spending",
                    "Teardown",
                ],
            )
            for forbidden in (
                "gates",
                "authorizations",
                "write_authority",
                "next_prompt",
                "lifecycle_state",
            ):
                self.assertNotIn(forbidden, preview)

    def test_missing_domains_are_current_source_gaps_not_invented_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._source_project(
                root,
                "# Product outcome\n\nHelp a team review plans.\n",
            )
            preview = preview_source_brief(
                root, "docs/reference/original-product-brief.md"
            )
            self.assertEqual(preview["status"], "READY_FOR_CONFIRMATION")
            self.assertEqual(
                {item["category"] for item in preview["candidate_facts"]},
                {"PRODUCT_OUTCOME"},
            )
            self.assertEqual(
                preview["missing_or_unclear"],
                [
                    "The intended users and their access boundaries",
                    "The first-release scope",
                    "Explicit non-goals and deferrals",
                    "Measurable acceptance criteria",
                    "Data classification, retention, deletion, and access",
                    "Failure and recovery expectations",
                    "AWS Region and development cost constraints",
                ],
            )

    def test_secret_like_source_is_blocked_without_echoing_source_value(self) -> None:
        secret = "SuperSecretPassword123!"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._source_project(
                root,
                f"# Product brief\n\npassword={secret}\n",
            )
            canonical = root / "docs" / "project" / "PRD.md"
            canonical_before = canonical.read_bytes()
            preview = preview_source_brief(
                root, "docs/reference/original-product-brief.md"
            )
            encoded = json.dumps(preview)
            self.assertEqual(preview["status"], "BLOCKED")
            self.assertEqual(preview["issues"][0]["code"], "SOURCE_BRIEF_SECRET_LIKE")
            self.assertEqual(preview["safety"]["secret_like_material"], "DETECTED")
            self.assertNotIn(secret, encoded)
            self.assertNotIn("password=", encoded)
            self.assertEqual(canonical.read_bytes(), canonical_before)

    def test_unsafe_missing_non_utf8_and_oversized_sources_fail_closed(self) -> None:
        cases: list[tuple[str, str]] = [
            ("../outside.md", "SOURCE_BRIEF_PATH_UNSAFE"),
            ("docs/reference/missing.md", "SOURCE_BRIEF_MISSING"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source_path, code in cases:
                with self.subTest(source_path=source_path):
                    preview = preview_source_brief(root, source_path)
                    self.assertEqual(preview["status"], "BLOCKED")
                    self.assertEqual(preview["issues"][0]["code"], code)
                    self.assertFalse(preview["safety"]["canonical_writes_allowed"])

            invalid = root / "docs" / "reference" / "invalid.md"
            invalid.parent.mkdir(parents=True)
            invalid.write_bytes(b"\xff\xfe\x00\x00")
            preview = preview_source_brief(root, "docs/reference/invalid.md")
            self.assertEqual(preview["issues"][0]["code"], "SOURCE_BRIEF_UNREADABLE")

            oversized = root / "docs" / "reference" / "oversized.md"
            oversized.write_bytes(b"x" * (SOURCE_BRIEF_MAX_BYTES + 1))
            preview = preview_source_brief(root, "docs/reference/oversized.md")
            self.assertEqual(preview["issues"][0]["code"], "SOURCE_BRIEF_TOO_LARGE")

    def test_symlinked_source_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._source_project(root)
            with mock.patch(
                "scripts.fastlane_engine.core.snapshot.has_symlink_component",
                return_value=True,
            ):
                preview = preview_source_brief(
                    root, "docs/reference/original-product-brief.md"
                )
            self.assertEqual(preview["status"], "BLOCKED")
            self.assertEqual(preview["issues"][0]["code"], "SOURCE_BRIEF_SYMLINK")

    def test_deterministic_presenter_keeps_choices_readable_and_natural(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._source_project(root)
            preview = preview_source_brief(
                root, "docs/reference/original-product-brief.md"
            )
            rendered = render_source_brief_preview(preview)
            self.assertIn("FASTLANE · SOURCE-ASSISTED DEFINE", rendered)
            self.assertIn("## What it appears to describe", rendered)
            self.assertIn("## Proposed technical ideas", rendered)
            self.assertIn("## What it does not authorize", rendered)
            self.assertIn("**A. ", rendered)
            self.assertIn("\n\n**B. Recommended —", rendered)
            self.assertIn("\n\n**C. ", rendered)
            self.assertIn("or answer in your own words", rendered)
            self.assertIn("not instructions to Codex", rendered)
            self.assertNotIn("sha256:", rendered)
            self.assertNotIn("OWNER_SUPPLIED_AI_DRAFT", rendered)

    def test_cli_and_presenter_modes_use_only_bounded_source_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._source_project(root)
            result = subprocess.run(
                [
                    sys.executable,
                    str(DOCTOR),
                    "--root",
                    str(root),
                    "--source-brief",
                    "docs/reference/original-product-brief.md",
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            preview = json.loads(result.stdout)
            self.assertEqual(preview["status"], "READY_FOR_CONFIRMATION")

            presented = subprocess.run(
                [sys.executable, str(PRESENTER), "source-brief", "--input-stdin"],
                input=json.dumps({"source_assist": preview}),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(presented.returncode, 0, presented.stderr)
            self.assertIn("How should Fastlane use this document?", presented.stdout)

            usage = subprocess.run(
                [
                    sys.executable,
                    str(DOCTOR),
                    "--root",
                    str(root),
                    "--source-brief",
                    "docs/reference/original-product-brief.md",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(usage.returncode, 1)
            self.assertEqual(
                json.loads(usage.stdout)["issues"][0]["code"],
                "SOURCE_BRIEF_USAGE",
            )

    def test_preview_never_reads_or_writes_an_aws_or_github_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._source_project(root)
            with mock.patch("subprocess.run") as run:
                preview = preview_source_brief(
                    root, "docs/reference/original-product-brief.md"
                )
            self.assertEqual(preview["status"], "READY_FOR_CONFIRMATION")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
