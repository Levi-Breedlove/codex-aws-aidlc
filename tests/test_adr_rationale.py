from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.fastlane_adr import ADR_AUTHORITY, derive_adr_rationale


def design_contract(
    *,
    validation: str = "[ADR-0001](../adr/0001-runtime.md)",
    decision_id: str = "TECH-0001",
) -> dict[str, object]:
    return {
        "schema_version": 7,
        "status": "READY",
        "design_revision": "DES-0001",
        "technology_decisions": [
            {
                "decision_id": decision_id,
                "concern": "APPLICATION_RUNTIME",
                "selection": "Python 3.12",
                "version_policy": "EXACT: 3.12",
                "source": "OWNER_AND_REPOSITORY",
                "basis_ids": "REQ-0001, DES-0001",
                "alternatives_and_rationale": "RATIONALE: fit; REJECTED: Java",
                "compatibility_migration": "No migration",
                "validation": validation,
            }
        ],
        "architecture": {
            "selection": {
                "architecture_id": "ARCH-0001",
                "selected_candidate": "CAND-0001",
                "requirement_and_driver_basis": "REQ-0001, DRV-0001",
                "validation": "Architecture validation",
            },
            "aws_evidence": [
                {
                    "evidence_id": "AWS-EV-0001",
                    "discovery_id": "AWS-DISC-0001",
                    "design_ids": decision_id,
                }
            ],
        },
        "canonical_sha256": "sha256:" + "a" * 64,
    }


def adr_text(
    *,
    number: str = "0001",
    status: str = "Accepted",
    design_revision: str = "DES-0001",
    decision_id: str = "TECH-0001",
    decision_value: str = "Python 3.12",
    basis_ids: str = "REQ-0001, DES-0001",
    prd_heading: str = "Technology and toolchain decision register",
    maturity: str = "SOURCE_VERIFIED",
    evidence_ids: str = "AWS-EV-0001",
    supersedes: str = "NONE",
    superseded_by: str = "NONE",
    context: str = "The application needs a supported runtime with a small operations burden.",
) -> str:
    return f"""# ADR-{number}: Application runtime

## Decision record

| Field | Current value |
|---|---|
| Status | {status} |
| Design revision | {design_revision} |
| Primary decision | {decision_id} |
| Decision value | {decision_value} |
| Related basis IDs | {basis_ids} |
| Canonical PRD section | {prd_heading} |
| Evidence maturity | {maturity} |
| Evidence IDs | {evidence_ids} |
| Supersedes | {supersedes} |
| Superseded by | {superseded_by} |
| Authority | {ADR_AUTHORITY} |

## Context

{context}

## Decision

Use the selected runtime for the bounded application release.

## Alternatives considered

Java was rejected because it adds avoidable packaging and operating work.

## Consequences

The team accepts the selected runtime lifecycle and dependency constraints.

## Evidence and validation

The current source evidence and local compatibility checks support this choice.

## Revisit when

Reconsider if support, performance, or compatibility requirements materially change.
"""


class AdrRationaleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "docs/adr").mkdir(parents=True)

    def write(self, name: str, text: str) -> None:
        (self.root / "docs/adr" / name).write_text(text, encoding="utf-8")

    def derive(self, design: dict[str, object] | None = None):
        return derive_adr_rationale(self.root, design or design_contract(), "")

    @staticmethod
    def codes(issues: list[dict[str, str]]) -> set[str]:
        return {item["code"] for item in issues}

    def test_no_reference_keeps_projects_unchanged(self) -> None:
        self.write("notes.md", "This unreferenced note is not a Fastlane ADR.\n")
        design = design_contract(validation="Local runtime tests")
        projection, issues, sources = self.derive(design)
        self.assertEqual(projection["status"], "NONE")
        self.assertFalse(projection["authoritative"])
        self.assertEqual(issues, [])
        self.assertEqual(sources, {})

    def test_current_accepted_adr_matches_canonical_decision(self) -> None:
        self.write("0001-runtime.md", adr_text())
        projection, issues, sources = self.derive()
        self.assertEqual(issues, [])
        self.assertEqual(projection["status"], "CURRENT")
        self.assertEqual(projection["records"][0]["primary_decision"], "TECH-0001")
        self.assertEqual(projection["records"][0]["evidence_ids"], ["AWS-EV-0001"])
        self.assertIn("docs/adr/0001-runtime.md", sources)

    def test_architecture_adr_matches_the_selected_canonical_candidate(self) -> None:
        design = design_contract()
        design["technology_decisions"] = []
        architecture = design["architecture"]
        assert isinstance(architecture, dict)
        selection = architecture["selection"]
        assert isinstance(selection, dict)
        selection["validation"] = "[ADR-0001](../adr/0001-runtime.md)"
        evidence = architecture["aws_evidence"]
        assert isinstance(evidence, list)
        evidence[0]["design_ids"] = "ARCH-0001"
        self.write(
            "0001-runtime.md",
            adr_text(
                decision_id="ARCH-0001",
                decision_value="CAND-0001",
                basis_ids="REQ-0001, DRV-0001",
                prd_heading="Selected architecture",
            ),
        )
        projection, issues, _sources = self.derive(design)
        self.assertEqual(issues, [])
        self.assertEqual(projection["status"], "CURRENT")
        self.assertEqual(projection["records"][0]["primary_decision"], "ARCH-0001")

    def test_missing_and_unsafe_links_fail_closed(self) -> None:
        _projection, issues, _sources = self.derive()
        self.assertIn("ADR_RATIONALE_MISSING", self.codes(issues))

        unsafe = design_contract(validation="[ADR-0001](../../outside.md)")
        _projection, issues, _sources = self.derive(unsafe)
        self.assertIn("ADR_RATIONALE_UNSAFE", self.codes(issues))

    def test_stale_revision_is_distinct_from_canonical_mismatch(self) -> None:
        self.write("0001-runtime.md", adr_text(design_revision="DES-0000"))
        projection, issues, _sources = self.derive()
        self.assertEqual(projection["status"], "STALE")
        self.assertEqual(self.codes(issues), {"ADR_RATIONALE_STALE"})

        self.write("0001-runtime.md", adr_text(decision_value="Java 21"))
        projection, issues, _sources = self.derive()
        self.assertEqual(projection["status"], "BLOCKED")
        self.assertIn("ADR_RATIONALE_MISMATCH", self.codes(issues))

    def test_basis_evidence_heading_and_maturity_must_match(self) -> None:
        self.write(
            "0001-runtime.md",
            adr_text(
                basis_ids="REQ-0002, DES-0001",
                prd_heading="Selected architecture",
                maturity="PLANNED_AFTER_APPROVAL",
                evidence_ids="NONE",
            ),
        )
        _projection, issues, _sources = self.derive()
        self.assertIn("ADR_RATIONALE_MISMATCH", self.codes(issues))
        self.assertIn("basis IDs", issues[0]["message"])

    def test_invalid_metadata_is_rejected_before_canonical_binding(self) -> None:
        invalid_values = (
            {"design_revision": "DES-1"},
            {"decision_id": "REQ-0001"},
            {"decision_value": "TODO"},
            {"basis_ids": "REQ-0001, REQ-0001"},
            {"prd_heading": "Gate B Review"},
            {"maturity": "OBSERVED"},
            {"evidence_ids": "not-an-evidence-id"},
            {"supersedes": "ADR-one"},
        )
        for values in invalid_values:
            with self.subTest(values=values):
                self.write("0001-runtime.md", adr_text(**values))
                projection, issues, _sources = self.derive()
                self.assertEqual(projection["status"], "BLOCKED")
                self.assertIn("ADR_RATIONALE_MALFORMED", self.codes(issues))

    def test_duplicate_id_fails_closed(self) -> None:
        self.write("0001-runtime.md", adr_text())
        self.write("0001-runtime-copy.md", adr_text())
        projection, issues, _sources = self.derive()
        self.assertEqual(projection["status"], "BLOCKED")
        self.assertIn("ADR_RATIONALE_DUPLICATE", self.codes(issues))

    def test_valid_supersession_chain_and_cycle_detection(self) -> None:
        design = design_contract(validation="[ADR-0002](../adr/0002-runtime.md)")
        self.write(
            "0001-runtime.md",
            adr_text(
                number="0001",
                status="Superseded",
                superseded_by="ADR-0002",
            ),
        )
        self.write(
            "0002-runtime.md",
            adr_text(number="0002", supersedes="ADR-0001"),
        )
        projection, issues, _sources = self.derive(design)
        self.assertEqual(issues, [])
        self.assertEqual(projection["status"], "CURRENT")
        self.assertEqual(len(projection["records"]), 2)

        self.write(
            "0001-runtime.md",
            adr_text(
                number="0001",
                status="Superseded",
                supersedes="ADR-0002",
                superseded_by="ADR-0002",
            ),
        )
        _projection, issues, _sources = self.derive(design)
        self.assertIn("ADR_RATIONALE_SUPERSESSION_INVALID", self.codes(issues))

    def test_supersession_chain_cannot_cross_canonical_decisions(self) -> None:
        design = design_contract(validation="[ADR-0002](../adr/0002-runtime.md)")
        self.write(
            "0001-runtime.md",
            adr_text(
                number="0001",
                status="Superseded",
                decision_id="TECH-0002",
                superseded_by="ADR-0002",
            ),
        )
        self.write(
            "0002-runtime.md",
            adr_text(number="0002", supersedes="ADR-0001"),
        )
        projection, issues, _sources = self.derive(design)
        self.assertEqual(projection["status"], "BLOCKED")
        self.assertIn("ADR_RATIONALE_SUPERSESSION_INVALID", self.codes(issues))
        self.assertTrue(
            any("does not belong" in issue["message"] for issue in issues), issues
        )

    def test_rationale_change_changes_only_non_authoritative_projection(self) -> None:
        design = design_contract()
        canonical_before = json.dumps(design, sort_keys=True)
        self.write("0001-runtime.md", adr_text())
        first, first_issues, _sources = self.derive(design)
        self.write(
            "0001-runtime.md",
            adr_text(
                context="The same decision now has clearer supporting context for reviewers."
            ),
        )
        second, second_issues, _sources = self.derive(design)
        self.assertEqual(first_issues, [])
        self.assertEqual(second_issues, [])
        self.assertNotEqual(first["projection_sha256"], second["projection_sha256"])
        self.assertEqual(canonical_before, json.dumps(design, sort_keys=True))
        self.assertEqual(design["canonical_sha256"], "sha256:" + "a" * 64)


if __name__ == "__main__":
    unittest.main()
