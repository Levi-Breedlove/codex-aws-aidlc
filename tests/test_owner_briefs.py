from __future__ import annotations

import unittest

from scripts import fastlane_owner_briefs as briefs
from scripts import fastlane_presenter as presenter


class OwnerBriefProjectionTests(unittest.TestCase):
    def gate_b_navigation_locators(self) -> list[dict[str, object]]:
        specifications = (
            (
                briefs.GATE_B_NAVIGATION_LOCATOR_KEYS[0],
                "Complete proposed architecture",
                "Proposed system at a glance",
            ),
            (
                briefs.GATE_B_NAVIGATION_LOCATOR_KEYS[1],
                "AWS implementation diagram",
                "AWS implementation at a glance",
            ),
            (
                briefs.GATE_B_NAVIGATION_LOCATOR_KEYS[2],
                "Project diagram guide",
                "Diagram guide",
            ),
        )
        return [
            briefs.source_locator(
                key=key,
                label=label,
                path="docs/project/PRD.md",
                heading=heading,
                start_line=31 + index,
                end_line=31 + index,
                section_text=f"## {heading}\n",
            )
            for index, (key, label, heading) in enumerate(specifications)
        ]

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

    def ready_gate_a_inventory(self) -> dict[str, object]:
        projection = {
            "schema_version": 1,
            "kind": "GATE_A",
            "status": "READY",
            "required_domains": [],
            "decisions": [
                {
                    "decision_id": "INTAKE-0001",
                    "domain": "product",
                    "title": "Starting point",
                    "selection": "A new application",
                    "source": "Validated owner intake",
                    "maturity": "CONFIRMED_BY_OWNER",
                    "owner_effect": "Fastlane can create one new application.",
                    "why": "The owner confirmed this starting point.",
                    "alternatives": "This is an owner fact, not an agent selection.",
                    "tradeoff": "Existing behavior is not assumed.",
                    "risk_and_mitigation": "A change requires Gate A revalidation.",
                    "evidence_status": "CONFIRMED_BY_OWNER",
                    "reconsider_when": "The owner changes the starting point.",
                    "basis_ids": ["INTAKE-0001"],
                    "evidence_ids": [],
                    "source_locator_keys": ["gate-a-readiness"],
                }
            ],
        }
        finalized, issues = briefs.finalize_owner_decision_inventory(projection)
        self.assertEqual(issues, [])
        return finalized

    def ready_gate_b_inventory(self) -> dict[str, object]:
        decisions = []
        for index, domain in enumerate(briefs.TECHNICAL_DOMAIN_ORDER, start=1):
            decisions.append(
                {
                    "decision_id": f"OWNER-DES-{index:04d}",
                    "domain": domain,
                    "title": domain.replace("/", " and ").title(),
                    "selection": f"Selected {domain} approach",
                    "source": "Canonical Design-7 records",
                    "maturity": "PLANNED_AFTER_APPROVAL",
                    "owner_effect": f"This defines the {domain} boundary.",
                    "why": "It satisfies the current requirement basis.",
                    "alternatives": "A broader option was rejected as unnecessary.",
                    "tradeoff": "The bounded choice favors simplicity.",
                    "risk_and_mitigation": "The recorded validation limits risk.",
                    "evidence_status": "PLANNED_AFTER_APPROVAL",
                    "reconsider_when": "A measurable design basis changes.",
                    "basis_ids": ["REQ-0001", "DES-0001"],
                    "evidence_ids": [],
                    "source_locator_keys": ["selected-architecture"],
                }
            )
        projection = {
            "schema_version": 1,
            "kind": "GATE_B",
            "status": "READY",
            "required_domains": list(briefs.TECHNICAL_DOMAIN_ORDER),
            "decisions": decisions,
        }
        finalized, issues = briefs.finalize_owner_decision_inventory(projection)
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
        report = {
            "owner_decision_brief": brief,
            "owner_decision_inventory": self.ready_gate_a_inventory(),
        }
        rendered = presenter.render_owner_decision_brief(report, "GATE_A")
        self.assertIn("Gate A Owner Decision Brief", rendered)
        self.assertIn("| Starting point | A new application |", rendered)
        self.assertIn(
            "Validated owner intake — [Gate A readiness]"
            "(docs/project/PRD.md#gate-a-readiness)",
            rendered,
        )
        self.assertIn("Not authorized", rendered)
        self.assertIn("docs/project/PRD.md#gate-a-readiness", rendered)

        changed = dict(brief)
        changed["status"] = "STALE"
        with self.assertRaisesRegex(presenter.PresentationError, "digest"):
            presenter.render_owner_decision_brief(
                {
                    "owner_decision_brief": changed,
                    "owner_decision_inventory": self.ready_gate_a_inventory(),
                },
                "GATE_A",
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
            ),
            *self.gate_b_navigation_locators(),
        ]
        inventory = self.ready_gate_b_inventory()
        projection["technical_decision_groups"] = [
            {
                "domain": decision["domain"],
                "decisions": [
                    {
                        "decision_id": decision["decision_id"],
                        "decision": decision["title"],
                        "owner_effect": decision["owner_effect"],
                        "selection": decision["selection"],
                        "requirement_basis": "REQ-0001 and DES-0001",
                        "why": decision["why"],
                        "alternatives": decision["alternatives"],
                        "tradeoff": decision["tradeoff"],
                        "risk_and_mitigation": decision["risk_and_mitigation"],
                        "evidence_status": decision["evidence_status"],
                        "reconsider_when": decision["reconsider_when"],
                        "basis_ids": ["REQ-0001", "DES-0001"],
                        "evidence_ids": [],
                        "source_locator_keys": ["selected-architecture"],
                    }
                ],
            }
            for decision in inventory["decisions"]
        ]
        finalized, issues = briefs.finalize_owner_decision_brief(projection)
        self.assertEqual(issues, [])
        report = {
            "owner_decision_brief": finalized,
            "owner_decision_inventory": inventory,
            "aws_mode_boundary": {
                "gate_b_maximum": "MUTATE_LISTED_RESOURCES",
                "external_authority_kind": "NONE",
                "external_authority_validity": "NONE",
                "account_access_authorized": False,
                "mutation_authorized": False,
            },
        }
        rendered = presenter.render_owner_decision_brief(report, "GATE_B")
        for label in (
            "Meaning and selection:",
            "Basis and rationale:",
            "Alternatives and tradeoffs:",
            "Risks and safeguards:",
            "Evidence and revisit trigger:",
            "Exact source:",
        ):
            self.assertIn(label, rendered)
        self.assertIn("Change the design: <correction>.", rendered)
        self.assertIn(
            "Current AWS authority: NONE — planned maximum only",
            rendered,
        )
        current_authority = dict(report)
        current_authority["aws_mode_boundary"] = {
            **report["aws_mode_boundary"],
            "external_authority_kind": "AWS_READ_ONLY",
            "external_authority_validity": "CURRENT",
            "account_access_authorized": True,
        }
        with self.assertRaisesRegex(
            presenter.PresentationError, "current exact AWS authority"
        ):
            presenter.render_owner_decision_brief(current_authority, "GATE_B")
        self.assertIn("docs/project/PRD.md#selected-architecture", rendered)
        expected_links = (
            "[View the complete proposed architecture]"
            "(docs/project/PRD.md#proposed-system-at-a-glance)",
            "[View the AWS implementation diagram]"
            "(docs/project/PRD.md#aws-implementation-at-a-glance)",
            "[Browse all project diagrams](docs/project/PRD.md#diagram-guide)",
        )
        positions = [rendered.index(link) for link in expected_links]
        self.assertEqual(positions, sorted(positions))
        for link in expected_links:
            self.assertEqual(rendered.count(link), 1)
        for anchor in (
            "#proposed-system-at-a-glance",
            "#aws-implementation-at-a-glance",
            "#diagram-guide",
        ):
            self.assertEqual(rendered.count(anchor), 1)
        self.assertEqual(
            [item["domain"] for item in inventory["decisions"]],
            list(briefs.TECHNICAL_DOMAIN_ORDER),
        )
        self.assertLessEqual(
            len([line for line in rendered.splitlines() if line.strip()]), 140
        )

        for missing_key in briefs.GATE_B_NAVIGATION_LOCATOR_KEYS:
            with self.subTest(missing_navigation=missing_key):
                missing = dict(projection)
                missing.pop("canonical_sha256", None)
                missing["source_locators"] = [
                    locator
                    for locator in projection["source_locators"]
                    if locator["key"] != missing_key
                ]
                _blocked, missing_issues = briefs.finalize_owner_decision_brief(missing)
                self.assertTrue(
                    any(missing_key in issue for issue in missing_issues),
                    missing_issues,
                )

    def test_gate_b_inventory_fails_when_any_promised_domain_is_missing(self) -> None:
        complete = self.ready_gate_b_inventory()
        for missing_domain in briefs.TECHNICAL_DOMAIN_ORDER:
            with self.subTest(domain=missing_domain):
                candidate = dict(complete)
                candidate.pop("canonical_sha256", None)
                candidate["decisions"] = [
                    decision
                    for decision in complete["decisions"]
                    if decision["domain"] != missing_domain
                ]
                finalized, issues = briefs.finalize_owner_decision_inventory(candidate)
                self.assertIn(
                    (
                        "Gate B must contain exactly one decision for every "
                        "technical domain"
                    ),
                    issues,
                )
                self.assertIsNone(finalized["canonical_sha256"])

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
