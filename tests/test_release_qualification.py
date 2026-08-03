from __future__ import annotations

import importlib
import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = REPOSITORY_ROOT / "docs" / "QUALIFICATION.md"
QUALIFICATION_IDS = [f"QUAL-{number:02d}" for number in range(1, 16)]
EVIDENCE_IDS = [f"QTEST-{number:02d}" for number in range(1, 16)]
RELEASE_CLAIM = (
    "Repository contracts, deterministic tests, and owner/AI journeys passed. "
    "Independent adopter evidence has not yet been collected. "
    "Real AWS deployment, rollback, recovery, and teardown remain unobserved "
    "unless separately field-qualified."
)


class ReleaseQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = QUALIFICATION.read_text(encoding="utf-8")

    def qualification_rows(self) -> list[list[str]]:
        rows: list[list[str]] = []
        for line in self.text.splitlines():
            if not line.startswith("| QUAL-"):
                continue
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
        return rows

    def evidence_mappings(self) -> dict[str, list[str]]:
        mappings: dict[str, list[str]] = {}
        pattern = re.compile(r"^- (QTEST-\d{2}): (.+)$", re.MULTILINE)
        for evidence_id, payload in pattern.findall(self.text):
            mappings[evidence_id] = re.findall(r"`(tests\.[^`]+)`", payload)
        return mappings

    def test_exact_fifteen_owner_journeys_are_deterministically_qualified(
        self,
    ) -> None:
        rows = self.qualification_rows()
        self.assertEqual([row[0] for row in rows], QUALIFICATION_IDS)
        self.assertEqual([row[2] for row in rows], EVIDENCE_IDS)
        self.assertTrue(all(row[3] == "`DETERMINISTIC_PASS`" for row in rows))
        self.assertTrue(all(len(row) == 4 for row in rows))

    def test_every_qualification_reference_names_an_executable_unittest(
        self,
    ) -> None:
        mappings = self.evidence_mappings()
        self.assertEqual(sorted(mappings), EVIDENCE_IDS)
        referenced: list[str] = []
        for evidence_id in EVIDENCE_IDS:
            references = mappings[evidence_id]
            self.assertTrue(references, evidence_id)
            for reference in references:
                module_name, class_name, method_name = reference.rsplit(".", 2)
                module = importlib.import_module(module_name)
                test_class = getattr(module, class_name)
                method = getattr(test_class, method_name)
                self.assertTrue(callable(method), reference)
                referenced.append(reference)
        self.assertEqual(len(referenced), len(set(referenced)))

    def test_release_claim_is_exact_and_truthfully_bounded(self) -> None:
        normalized = " ".join(
            line.removeprefix("> ").strip()
            for line in self.text.splitlines()
            if line.startswith("> ")
        )
        self.assertEqual(normalized, RELEASE_CLAIM)
        prose = " ".join(self.text.split())
        for phrase in (
            "External model role-play:",
            "`NOT_RUN`",
            "No live model or independent-rater evidence is claimed.",
            "Independent adopter testing",
            "Real AWS deployment, rollback, recovery, and teardown",
            "Unauthorized by this qualification",
            "tag or release publication",
        ):
            self.assertIn(phrase, prose)

    def test_walkthrough_preserves_two_gates_and_separate_aws_authority(
        self,
    ) -> None:
        blocks = re.findall(r"```mermaid\s*\n(.*?)```", self.text, re.DOTALL)
        self.assertEqual(len(blocks), 1)
        diagram = blocks[0]
        for label in (
            "Gate A: approve the complete product agreement",
            "AWS Core-informed design",
            "Gate B: approve the technical plan and build boundary",
            "Separate AWS authorization, only when requested",
        ):
            self.assertIn(label, diagram)
        prose = " ".join(self.text.split())
        for phrase in (
            "exactly one owner question per turn",
            "`search_documentation`",
            "`retrieve_skill`",
            "receipt is the final block",
            "Greenfield application code goes under `app/`",
            "neither inspects AWS credentials nor accesses an AWS account",
        ):
            self.assertIn(phrase, prose)

    def test_public_navigation_reaches_the_qualification_page(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        docs_index = (REPOSITORY_ROOT / "docs" / "README.md").read_text(
            encoding="utf-8"
        )
        evaluation = (REPOSITORY_ROOT / "docs" / "EVALUATION.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("](docs/QUALIFICATION.md)", readme)
        self.assertIn("](QUALIFICATION.md)", docs_index)
        self.assertIn("](QUALIFICATION.md)", evaluation)
        for target in (
            "project/PRD.md",
            "project/TASKS.md",
            "project/VERIFY.md",
            "project/RUNBOOK.md",
            "WORKFLOW.md",
            "EVALUATION.md",
        ):
            self.assertIn(f"]({target})", self.text)


if __name__ == "__main__":
    unittest.main()
