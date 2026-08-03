from __future__ import annotations

import unittest

from scripts import fastlane_owner_briefs as briefs
from scripts import fastlane_presenter as presenter


class OwnerBriefProjectionTests(unittest.TestCase):
    def ready_gate_a(self) -> dict[str, object]:
        projection = {
            "schema_version": 1,
            "kind": "GATE_A",
            "status": "READY",
            "basis": {
                "requirements_revision": "REQ-0001",
                "design_revision": None,
                "construction_authorization": None,
                "design_contract_sha256": None,
            },
            "executive_sections": [
                {
                    "section_id": "GATE-A-OUTCOME",
                    "title": "Outcome and users",
                    "items": ["Outcome: A useful first release."],
                    "basis_ids": ["REQ-0001"],
                }
            ],
            "technical_decision_groups": [],
            "claims": [
                briefs.claim(
                    "Deployment has not been authorized.",
                    "NOT_AUTHORIZED",
                    basis_ids=["REQ-0001"],
                )
            ],
            "source_locators": [
                briefs.source_locator(
                    key="gate-a-readiness",
                    label="Gate A readiness",
                    path="docs/project/PRD.md",
                    heading="Gate A readiness",
                    start_line=10,
                    end_line=12,
                    section_text="## Gate A readiness\r\n\r\nReady.\r\n",
                )
            ],
            "authorization_effect": {
                "approves": ["The current requirements."],
                "does_not_approve": ["Construction or deployment."],
            },
            "formal_receipt_required": True,
        }
        finalized, issues = briefs.finalize_owner_decision_brief(projection)
        self.assertEqual(issues, [])
        return finalized

    def test_source_locator_is_repository_relative_and_digest_bound(self) -> None:
        locator = briefs.source_locator(
            key="section",
            label="Section",
            path="docs/project/PRD.md",
            heading="Section",
            start_line=1,
            end_line=2,
            section_text="## Section\r\nvalue\r\n\r\n",
        )
        self.assertEqual(locator["start_line"], 1)
        self.assertEqual(locator["end_line"], 2)
        self.assertRegex(locator["section_sha256"], r"^sha256:[0-9a-f]{64}$")
        with self.assertRaisesRegex(ValueError, "repository-relative"):
            briefs.source_locator(
                key="unsafe",
                label="Unsafe",
                path="Q:/outside/PRD.md",
                heading="Unsafe",
                start_line=1,
                end_line=1,
                section_text="unsafe",
            )

    def test_owner_decision_brief_is_digest_bound_and_presentable(self) -> None:
        brief = self.ready_gate_a()
        report = {"owner_decision_brief": brief}
        rendered = presenter.render_owner_decision_brief(report, "GATE_A")
        self.assertIn("Gate A Owner Decision Brief", rendered)
        self.assertIn("Not authorized", rendered)
        self.assertIn("docs/project/PRD.md#gate-a-readiness", rendered)

        changed = dict(brief)
        changed["status"] = "STALE"
        with self.assertRaisesRegex(presenter.PresentationError, "digest"):
            presenter.render_owner_decision_brief(
                {"owner_decision_brief": changed}, "GATE_A"
            )

    def test_ready_gate_b_requires_a_technical_decision_index(self) -> None:
        projection = self.ready_gate_a()
        projection["kind"] = "GATE_B"
        projection.pop("canonical_sha256", None)
        _finalized, issues = briefs.finalize_owner_decision_brief(projection)
        self.assertIn("Gate B has no technical decision index", issues)

    def test_answer_confirmation_requires_matching_new_owner_response(self) -> None:
        confirmation = briefs.answer_confirmation(
            status="READY",
            owner_response_id="OWNER-MSG-0002",
            card_id="INTAKE-CARD-0002",
            revision=2,
            presented_sha256="sha256:" + "a" * 64,
            recorded=["First useful outcome: Submit a request."],
            project_effect="This shapes the next requirements.",
            correction_prompt="Change first useful outcome to <new value>.",
            basis_ids=["INTAKE-0004"],
        )
        report = {"owner_answer_confirmation": confirmation}
        rendered = presenter.render_answer_confirmation(report, "OWNER-MSG-0002")
        self.assertIn("Recorded: First useful outcome", rendered)
        self.assertIn("Project effect:", rendered)
        self.assertIn("Correct it: Say `Change first useful outcome", rendered)
        with self.assertRaisesRegex(presenter.PresentationError, "current owner"):
            presenter.render_answer_confirmation(report, "OWNER-MSG-0001")

    def test_gate_b_decisions_require_resolving_source_locations(self) -> None:
        projection = self.ready_gate_a()
        projection.pop("canonical_sha256", None)
        projection["kind"] = "GATE_B"
        projection["technical_decision_groups"] = [
            {
                "domain": "application/runtime",
                "decisions": [
                    {
                        "decision_id": "ARCH-0001",
                        "decision": "Application architecture",
                        "owner_effect": "The application uses managed building blocks.",
                        "selection": "Managed service design",
                        "requirement_basis": "REQ-0001 requires the first release.",
                        "why": "It satisfies the approved requirements.",
                        "alternatives": (
                            "A self-managed design adds unsupported operations."
                        ),
                        "tradeoff": "It depends on managed service behavior.",
                        "risk_and_mitigation": (
                            "Service limits are tested and monitored."
                        ),
                        "evidence_status": "Planned from the current design record.",
                        "reconsider_when": (
                            "Revisit if a measured hard constraint is missed."
                        ),
                        "basis_ids": ["REQ-0001"],
                        "evidence_ids": [],
                        "source_locator_keys": ["missing-architecture"],
                    }
                ],
            }
        ]

        _finalized, issues = briefs.finalize_owner_decision_brief(projection)

        self.assertIn(
            "technical decisions reference missing source locations: missing-architecture",
            issues,
        )

    def test_gate_b_renders_every_human_decision_field_and_source(self) -> None:
        projection = self.ready_gate_a()
        projection.pop("canonical_sha256", None)
        projection["kind"] = "GATE_B"
        projection["source_locators"] = [
            briefs.source_locator(
                key="selected-architecture",
                label="Selected architecture",
                path="docs/project/PRD.md",
                heading="Selected architecture",
                start_line=20,
                end_line=30,
                section_text="## Selected architecture\n\nARCH-0001\n",
            )
        ]
        projection["technical_decision_groups"] = [
            {
                "domain": "application/runtime",
                "decisions": [
                    {
                        "decision_id": "ARCH-0001",
                        "decision": "Application architecture",
                        "owner_effect": "The owner receives a managed application.",
                        "selection": "Managed service design",
                        "requirement_basis": "REQ-0001 and FR-001",
                        "why": "It satisfies the approved first release.",
                        "alternatives": (
                            "Self-managed hosting was rejected for operations."
                        ),
                        "tradeoff": "Lower operations with provider dependency.",
                        "risk_and_mitigation": "Limits are measured and monitored.",
                        "evidence_status": (
                            "Source verified; implementation unobserved."
                        ),
                        "reconsider_when": (
                            "Revisit if latency exceeds its approved target."
                        ),
                        "basis_ids": ["REQ-0001", "FR-001"],
                        "evidence_ids": ["AWS-EV-0001"],
                        "source_locator_keys": ["selected-architecture"],
                    }
                ],
            }
        ]
        finalized, issues = briefs.finalize_owner_decision_brief(projection)
        self.assertEqual(issues, [])
        rendered = presenter.render_owner_decision_brief(
            {"owner_decision_brief": finalized}, "GATE_B"
        )
        for label in (
            "What this means for you:",
            "Selected:",
            "Requirement basis:",
            "Why selected:",
            "Alternatives and rejection reasons:",
            "Tradeoffs:",
            "Risks and safeguards:",
            "Evidence status:",
            "Reconsider when:",
            "Exact source:",
        ):
            self.assertIn(label, rendered)
        self.assertIn("Change the design: <correction>.", rendered)
        self.assertIn("docs/project/PRD.md#selected-architecture", rendered)

    def test_output_budget_blocks_instead_of_truncating_owner_content(self) -> None:
        projection = self.ready_gate_a()
        projection.pop("canonical_sha256", None)
        projection["executive_sections"][0]["items"] = [
            "Outcome: " + "x" * briefs.MAX_OWNER_BRIEF_OUTPUT_BYTES
        ]

        finalized, issues = briefs.finalize_owner_decision_brief(projection)

        self.assertTrue(any("output budget" in issue for issue in issues), issues)
        self.assertIsNone(finalized["canonical_sha256"])


if __name__ == "__main__":
    unittest.main()
