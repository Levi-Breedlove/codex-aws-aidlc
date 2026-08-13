from __future__ import annotations

import ast
import hashlib
import inspect
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

from scripts import bootstrap_doctor as doctor
from scripts import fastlane_adr
from scripts.fastlane_engine import api as engine_api
from scripts.fastlane_engine import design
from scripts.fastlane_engine.define.models import RequirementsContract
from scripts.fastlane_engine.design import adr as design_adr
from scripts.fastlane_engine.design import diagrams as design_diagrams
from scripts.fastlane_engine.design.models import (
    ArchitectureSelection,
    ProjectDesignContract,
)
from tests import test_adr_rationale as adr_fixtures
from tests import test_bootstrap_doctor as doctor_fixtures


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PACKAGE = REPOSITORY_ROOT / "scripts/fastlane_engine/design"


class EngineDesignTests(unittest.TestCase):
    def test_architecture_board_handoff_is_current_bound_and_non_authorizing(
        self,
    ) -> None:
        fixture = json.loads(
            (REPOSITORY_ROOT / "tests/fixtures/engine_parity_v1.json").read_text(
                encoding="utf-8"
            )
        )
        report = fixture["report_cases"]["gate_b_approved"]["report"]
        original = json.dumps(report, sort_keys=True)
        self.assertIn(
            "DIAGRAM_OUTPUT_NOT_AUTHORIZED",
            engine_api.derive_architecture_board_handoff(report)["issues"],
        )
        report["write_authority"]["approved_write_roots"].append("dist/architecture/**")
        handoff = engine_api.derive_architecture_board_handoff(report)
        semantic = report["design_contract"]["diagram_contract"]["records"][0][
            "semantic_sha256"
        ][7:]
        self.assertTrue(handoff["eligible"])
        self.assertEqual(
            handoff["output_root"], f"dist/architecture/DES-0001-{semantic}"
        )
        self.assertEqual(handoff["source"]["diagram_id"], "DIAGRAM-0001")
        self.assertEqual(handoff["cross_check"]["diagram_id"], "DIAGRAM-0008")
        self.assertEqual(
            (handoff["aws_authority"], handoff["external_authority"]),
            ("NONE", "NONE"),
        )
        report["write_authority"]["approved_write_roots"].pop()
        self.assertEqual(json.dumps(report, sort_keys=True), original)

    def test_architecture_board_handoff_fails_closed_without_changing_route(
        self,
    ) -> None:
        fixture = json.loads(
            (REPOSITORY_ROOT / "tests/fixtures/engine_parity_v1.json").read_text(
                encoding="utf-8"
            )
        )["report_cases"]["gate_b_approved"]["report"]
        fixture["write_authority"]["approved_write_roots"].append(
            "dist/architecture/**"
        )
        cases = {
            "stale-gate": lambda row: row["gates"].update(gate_b="STALE"),
            "legacy": lambda row: row["design_contract"]["diagram_contract"].update(
                grandfathered_schema5=True
            ),
            "active-task": lambda row: row["write_authority"].update(
                active_task="TASK-0001"
            ),
            "excluded": lambda row: row["write_authority"]["exclusions"].append(
                "dist/**"
            ),
            "protected": lambda row: row["write_authority"]["protected_paths"].append(
                "dist/architecture/**"
            ),
            "no-aws-view": lambda row: row["design_contract"]["diagram_contract"][
                "records"
            ][7].update(status="NOT_APPLICABLE"),
            "bad-digest": lambda row: row["design_contract"]["diagram_contract"][
                "records"
            ][0].update(semantic_sha256="sha256:bad"),
            "empty-relationships": lambda row: row["design_contract"][
                "diagram_contract"
            ]["records"][0].update(relationships=[]),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                candidate = json.loads(json.dumps(fixture))
                route = candidate["next_prompt"]
                mutate(candidate)
                self.assertFalse(
                    engine_api.derive_architecture_board_handoff(candidate)["eligible"]
                )
                self.assertEqual(candidate["next_prompt"], route)

        conflict = json.loads(json.dumps(fixture))
        diagrams = conflict["design_contract"]["diagram_contract"]
        diagrams["records"][7]["referenced_ids"].append("ACT-001")
        diagrams["records"][7]["relationships"] = [
            {"from_id": "TECH-0013", "relation": "reverses", "to_id": "ACT-001"}
        ]
        handoff = engine_api.derive_architecture_board_handoff(conflict)
        self.assertEqual(handoff["status"], "SEMANTIC_CONFLICT")
        self.assertEqual(handoff["failure_route"], "DESIGN-10")

        redirect = json.loads(json.dumps(fixture))
        redirect["design_contract"]["diagram_contract"]["records"][7]["relationships"][
            0
        ]["to_id"] = "TECH-0009"
        handoff = engine_api.derive_architecture_board_handoff(redirect)
        self.assertEqual(handoff["status"], "SEMANTIC_CONFLICT")
        self.assertEqual(handoff["failure_route"], "DESIGN-10")

    def test_architecture_board_source_is_exactly_the_approved_mermaid(self) -> None:
        source = (
            "# Record\n\n## Proposed system at a glance\n\n"
            "```mermaid\nflowchart TB\n    A --> B\n```\n\n## Next\n"
        )
        rendered = b"```mermaid\nflowchart TB\n    A --> B\n```\n"
        handoff = {
            "eligible": True,
            "source": {
                "anchor": "proposed-system-at-a-glance",
                "rendered_sha256": "sha256:" + hashlib.sha256(rendered).hexdigest(),
            },
        }
        self.assertEqual(
            engine_api.architecture_board_mermaid_source(source, handoff),
            "flowchart TB\n    A --> B\n",
        )
        handoff["source"]["rendered_sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "presentation digest changed"):
            engine_api.architecture_board_mermaid_source(source, handoff)

    def test_mermaid_claim_guard_allows_real_verified_names_and_states(self) -> None:
        for value in (
            "AWS Verified Access",
            "Amazon Verified Permissions",
            "Verified Permissions",
            "Amazon Verified<br/>Permissions",
            "Amazon Verified Permissions<br/>policy evaluation",
            "AWS Verified Access<br/>application access",
            "Amazon API Gateway",
            "AWS Lambda function",
            "Amazon Relational Database Service",
            "AWS CloudFormation stack",
            "Application Load Balancer",
            "AWS Systems Manager",
            "AWS CodeBuild",
            "AWS Config",
            "VERIFIED",
            "AWS SAM CLI deployment and change sets",
            "Infrastructure as code",
            "Recovery path",
            "Recovery plan",
            "Production environment",
            "Release review",
            "Construction envelope",
            "AWS account boundary",
            "Planned deployment path",
            "Account access scope",
            "Proposed account architecture",
            "Deployment validation strategy",
            "Planned deployment and recovery flow",
            "Tests exercise the planned recovery path",
            "Deployment requires separate authorization",
            "Construction permission pending",
            "Gate B approval required",
            "No deployment has occurred",
            "Tests not yet run",
            "Recovery not observed",
            "Recovery not yet observed",
            "AWS access requires owner authorization",
            "Deployment not authorized",
            "No AWS account was accessed",
            "AWS access is not authorized",
            "AWS account access boundary",
            "Deployment will be validated before release",
            "System will be live after deployment",
            "Tests must pass before release",
            "Tests should pass before release",
            "Recovery must be validated",
            "Infrastructure is to be provisioned",
            "AWS access will be authorized separately",
            "Gate B must be approved by the owner",
            "Cloud resources may be created later",
            "Application should remain ready",
            "AWS Budgets",
            "AWS Cost Explorer",
            "AWS Billing and Cost Management",
            "Cost alerts",
            "Monthly cost cap",
            "Budget threshold",
            "Spending limit",
            "Billing boundary",
            "Approval required",
            "Authorization pending",
            "Permission boundary",
            "Consent required",
            "Sign-off pending",
            "Access boundary",
            "Access path",
            "Access request",
            "Access not authorized",
            "Access will be granted",
            "Quality gate required",
            "Authority boundary",
            "Signoff pending",
            "Go-ahead required",
            "Green light pending",
            "R&amp;D boundary",
            "Documented deployment plan",
            "Deployment plan documented",
            "Documented consent workflow",
            "Consent workflow documented",
            "Documented approval path",
            "Approval path documented",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    design_diagrams._unsafe_visible_mermaid_issues(
                        "DIAGRAM-0001",
                        "node label",
                        value,
                        allow_breaks="<br" in value,
                    ),
                    [],
                )

        for value in (
            "The architecture was deployed and verified",
            "The owner granted AWS access",
            "AWS access was granted",
            "The system is live in AWS",
            "Deployment successful",
            "AWS access confirmed",
            "Gate B passed",
            "Owner consented to AWS deployment",
            "Production operational",
            "AWS account connected",
            "Construction permission active",
            "AWS access enabled",
            "AWS access established",
            "Gate B accepted",
            "Gate B cleared",
            "Owner gave permission for AWS deployment",
            "Deployment worked",
            "Deployment finished",
            "Released to production",
            "AWS resources provisioned",
            "Infrastructure created in AWS",
            "AWS deployment complete",
            "Construction greenlit",
            "Owner signed off AWS deployment",
            "Tests pass",
            "Recovery proven",
            "AWS access available",
            "AWS account linked",
            "Gate B signed off",
            "Owner okayed AWS deployment",
            "Deployment done",
            "Released successfully",
            "Tests green",
            "Recovery validated",
            "Infrastructure ready",
            "Production healthy",
            "AWS session authenticated",
            "Deployment validated",
            "Gate B complete",
            "AWS access ready",
            "Cloud resources running",
            "Planned deployment was successful",
            "Proposed system is live in AWS",
            "Planned AWS access was granted",
            "Proposed Gate B accepted",
            "Planned infrastructure was created in AWS",
            "Planned tests pass",
            "The request was deployed and verified through the runtime",
            "Successful planned deployment",
            "Deployed architecture",
            "Verified architecture",
            "Running cloud resources",
            "Passed tests",
            "Created AWS resources",
            "Gate B approval recorded",
            "Owner approval received",
            "Deployment successful pending review",
            "Tests passed, approval pending",
            "System live while deployment not authorized",
            "AWS access pending and active",
            "Gate B pending and accepted",
            "Deployment not authorized and successful",
            "No AWS access and connected",
            "Architecture and deployed",
            "The architecture is stable and deployed",
            "Planned deployment and successful",
            "AWS access granted while owner approval pending",
            "Deployment was successful without evidence",
            "Deployment was not only successful but verified",
            "AWS access was not only granted but active",
            "No deployment needed because system is live",
            "Deployment complete proposed architecture",
            "Gate B complete planned deployment",
            "AWS access complete proposed state",
            "Deployment not authorized yet successful",
            "Tests not run yet system live",
            "Deployment will fail yet system live",
            "Deployment not authorized though tests passed",
            "Deployment not authorized whereas tests passed",
            "Deployment not authorized nevertheless tests passed",
            "No deployment nonetheless AWS access granted",
            "Deployment not authorized even though tests passed",
            "AWS access verified",
            "AWS access validated",
            "AWS session operational",
            "AWS account verified",
            "AWS credentials active",
            "Cloud account connected",
            "Implementation built",
            "Deployment configured",
            "Application launched",
            "Service started",
            "Production serving traffic",
            "System responding",
            "Application reachable",
            "Service accessible",
            "System functioning",
            "Deployment working",
            "Tests passing",
            "System recovered",
            "Recovery restored",
            "Deployment rolled back",
            "Release published",
            "Infrastructure applied",
            "AWS resources allocated",
            "AWS stack created",
            "Stack deployed",
            "Lambda deployed",
            "API live",
            "Website live",
            "Database ready",
            "Deployment validated result",
            "Tests validated result",
            "System validated result",
            "Deployment validated stack",
            "Recovery validated stack",
            "AWS spend observed",
            "Monthly spending verified",
            "Budget approved",
            "Costs confirmed",
            "AWS charges incurred",
            "Bill paid",
            "Budget available",
            "Cost controls active",
            "Spending reconciled",
            "Approval granted",
            "Authorization confirmed",
            "Permission received",
            "Consent recorded",
            "Sign-off obtained",
            "Owner agreed to deployment",
            "Owner endorsed deployment",
            "Owner signed the approval",
            "Owner permission given",
            "Owner approval documented",
            "Gate B finalized",
            "Owner selected deployment",
            "Owner chose the architecture",
            "Owner waived the restriction",
            "Owner acknowledged approval",
            "Owner-selected deployment mechanism",
            "Owner's selected deployment mechanism",
            "Owner’s selected deployment mechanism",
            "Access granted",
            "Access authorized",
            "Access available",
            "Amazon Cognito<br/>access granted",
            "AWS Verified Access<br/>access granted",
            "Amazon Verified Permissions<br/>access granted",
            "Gate approved",
            "Quality gate passed",
            "Authority granted",
            "Authority confirmed",
            "Signoff obtained",
            "Signoff granted",
            "Go-ahead received",
            "Green light given",
            "Proposed deployment l&#105;ve in AWS",
            "Proposed deployment li\u200bve in AWS",
            "Proposed deployment \uff4c\uff49\uff56\uff45 in AWS",
            "Amazon Verified Permissions AWS access granted",
            "AWS Verified Access deployment successful",
        ):
            with self.subTest(value=value):
                self.assertTrue(
                    design_diagrams._unsafe_visible_mermaid_issues(
                        "DIAGRAM-0001",
                        "node label",
                        value,
                        allow_breaks="<br" in value,
                    )
                )

        for value in (
            "Deployment<br/>successful",
            "AWS access<br/>granted",
            "System<br/>live in AWS",
            "Tests<br/>pass",
            "Recovery<br/>validated",
            "Cloud resources<br/>running",
            "The architecture<br/>was deployed and verified",
            "No deployment<br/>AWS access granted",
            "Deployment not authorized<br/>Tests passed",
            "Recovery not observed<br/>Deployment successful",
            "Tests not run<br/>System live",
            "Deployment will be tested<br/>System live",
            "Tests must pass<br/>AWS access granted",
        ):
            with self.subTest(value=value):
                self.assertTrue(
                    design_diagrams._unsafe_visible_mermaid_issues(
                        "DIAGRAM-0001",
                        "node label",
                        value,
                        allow_breaks=True,
                    )
                )

    def test_digest_neutral_presentation_fields_preserve_1234_positional_models(
        self,
    ) -> None:
        requirements_bytes = b"legacy requirements bytes\n"
        requirements = RequirementsContract(
            "1.4",
            "READY",
            ("ACT-001",),
            ("FR-001",),
            ("JOURNEY-001",),
            ("AC-FR-001",),
            (),
            (),
            (),
            None,
            (),
            (),
            "sha256:" + "a" * 64,
            False,
            requirements_bytes,
        )
        self.assertEqual(requirements.canonical_bytes, requirements_bytes)
        self.assertEqual(requirements.presentation_labels, ())

        project_bytes = b"legacy project design bytes\n"
        project = ProjectDesignContract(
            7,
            "READY",
            None,
            ("API-001",),
            ("BOUNDARY-001",),
            (),
            None,
            None,
            (),
            "sha256:" + "b" * 64,
            False,
            False,
            False,
            project_bytes,
        )
        self.assertEqual(project.canonical_bytes, project_bytes)
        self.assertEqual(project.presentation_labels, ())

    def test_pre_aws_diagram_payload_preserves_exact_1234_shape(self) -> None:
        legacy = design_diagrams._diagram_semantic_payload(
            "SYSTEM_CONTEXT",
            ("ARCH-0001", "FR-001"),
            ("ACT-001", "ARCH-0001"),
            (
                ("ARCH-0001", "DASHED", "serves", "ACT-001"),
                ("ACT-001", "DASHED", "uses", "ARCH-0001"),
                ("ACT-001", "SOLID", "uses", "ARCH-0001"),
            ),
            "flowchart LR\nACT-001 -->|uses| ARCH-0001",
            modern_contract=False,
        )
        self.assertEqual(
            legacy,
            {
                "kind": "SYSTEM_CONTEXT",
                "basis_ids": ["ARCH-0001", "FR-001"],
                "referenced_ids": ["ACT-001", "ARCH-0001"],
                "relationships": [
                    {
                        "from_id": "ACT-001",
                        "relation": "uses",
                        "to_id": "ARCH-0001",
                    },
                ],
            },
        )
        self.assertNotIn("containment", legacy)
        self.assertNotIn("edge_kind", legacy["relationships"][0])
        canonical = (
            json.dumps(
                legacy,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            "2287bc06dffd89d05c847c96c6e336714f984135bd3a19bdecc7567c624a820c",
        )

    def test_legacy_diagram_contract_ignores_dashed_edges_and_keeps_row_order(
        self,
    ) -> None:
        source = """## Document status

| Field | Value |
|---|---|
| Project mode | greenfield |

### Project diagram contract

| Diagram ID | Kind | Applicability | Status | Anchor | Basis IDs | Referenced IDs |
|---|---|---|---|---|---|---|
| DIAGRAM-0002 | PRIMARY_OUTCOME | REQUIRED | CURRENT | primary-view | ARCH-0001 | ACT-001, ARCH-0001 |
| DIAGRAM-0001 | SYSTEM_CONTEXT | REQUIRED | CURRENT | system-view | ARCH-0001 | ACT-001, ARCH-0001 |

### Primary view

```mermaid
flowchart LR
ACT-001 -->|uses| ARCH-0001
ARCH-0001 -. "trusts" .-> ACT-001
```

### System view

```mermaid
flowchart LR
ARCH-0001 -->|serves| ACT-001
ACT-001 -. "trusts" .-> ARCH-0001
```
"""
        architecture = design.ArchitectureContract(
            selection=ArchitectureSelection(
                architecture_id="ARCH-0001",
                selected_candidate="CAND-0001",
                requirement_and_driver_basis="FR-001",
                rationale="Selected legacy design",
                rejected_alternatives="NONE",
                risks="NONE",
                mitigations="NONE",
                security_impact="NONE",
                reliability_impact="NONE",
                operational_burden="NONE",
                cost_effect="NONE",
                breakpoints="NONE",
                migration_path="NONE",
                revisit_triggers="NONE",
                validation="NONE",
            )
        )
        contract, issues = design.derive_diagram_contract(
            source,
            architecture,
            RequirementsContract(requirement_ids=("FR-001",)),
            doctor.CoverageContract(work_kind="NEW_BUILD"),
            required=True,
            grandfathered_schema5=False,
        )

        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "CURRENT")
        self.assertEqual(
            [record.diagram_id for record in contract.records],
            ["DIAGRAM-0002", "DIAGRAM-0001"],
        )
        self.assertEqual(
            contract.records[0].relationships,
            (("ACT-001", "uses", "ARCH-0001"),),
        )
        self.assertEqual(
            contract.records[1].relationships,
            (("ARCH-0001", "serves", "ACT-001"),),
        )
        self.assertEqual(
            [row[0] for row in json.loads(contract.canonical_bytes or b"[]")],
            ["DIAGRAM-0002", "DIAGRAM-0001"],
        )

    def test_migration_diagram_requires_preservation_basis_and_real_design_roles(
        self,
    ) -> None:
        context = design_diagrams._DiagramPresentationContext(
            architecture_id="ARCH-0001",
            requirement_ids=("FR-001",),
            actor_ids=("ACT-001",),
            journey_ids=("JOURNEY-001",),
            use_case_ids=(),
            interface_ids=("API-001",),
            boundary_ids=("BOUNDARY-001",),
            state_ids=(),
            all_aws_ids=frozenset({"TECH-0004", "TECH-0014"}),
            applicable_aws_ids=frozenset({"TECH-0004", "TECH-0014"}),
            current_ids=frozenset(
                {
                    "ARCH-0001",
                    "BOUNDARY-001",
                    "PRES-001",
                    "TECH-0004",
                    "TECH-0014",
                }
            ),
            labels_by_id={},
            styles_by_id={},
            technology_ids_by_concern={},
        )
        unrelated = design_diagrams._diagram_kind_semantic_issues(
            "DIAGRAM-0005",
            "MIGRATION",
            ("PRES-001",),
            {"TECH-0004", "TECH-0014"},
            context,
        )
        self.assertEqual(
            unrelated,
            [
                "DIAGRAM-0005: MIGRATION must show a project boundary",
                "DIAGRAM-0005: MIGRATION must show the selected architecture",
            ],
        )
        self.assertEqual(
            design_diagrams._diagram_kind_semantic_issues(
                "DIAGRAM-0005",
                "MIGRATION",
                ("PRES-001",),
                {"BOUNDARY-001", "ARCH-0001"},
                context,
            ),
            [],
        )

    def test_truthful_long_canonical_label_is_not_an_impossible_gate_blocker(
        self,
    ) -> None:
        label = (
            "Amazon service selected under an owner constraint with a deliberately "
            "long but truthful canonical technical description"
        )
        normalized, issues = design_diagrams._mermaid_label_issues(
            "DIAGRAM-0008", "TECH-0001", label
        )
        self.assertEqual(normalized, label)
        self.assertEqual(issues, [])

        _normalized, issues = design_diagrams._mermaid_label_issues(
            "DIAGRAM-0004",
            "STATE-001",
            "DRAFT<br/>VALIDATED<br/>PUBLISHED<br/>EXPIRED",
        )
        self.assertTrue(any("at most three visual lines" in issue for issue in issues))

        issues = design_diagrams._mermaid_relationship_issues(
            "DIAGRAM-0004",
            (
                "STATE-001 -->|permits only<br/>recorded publication<br/>transitions| STATE-001",
            ),
            presentation_only=True,
        )
        self.assertTrue(
            any("at most two visual lines" in issue for issue in issues),
            issues,
        )

    def test_visible_text_distinguishes_standards_and_plain_colons_from_uris(
        self,
    ) -> None:
        current_ids = ("ACT-001", "TECH-0001")
        for label in (
            "ISO-27001 reviewer",
            "RFC-7231 response handling",
            "Data: owner records",
            "File: upload owner",
            "JavaScript: framework guidance",
        ):
            with self.subTest(safe=label):
                normalized, issues = design_diagrams._mermaid_label_issues(
                    "DIAGRAM-0001",
                    "ACT-001",
                    label,
                    current_ids,
                )
                self.assertEqual(normalized, label)
                self.assertEqual(issues, [])

        for label in (
            "https://example.invalid/track",
            "file:/private/path",
            "javascript:alert(1)",
            "data:text/html,unsafe",
            "www.example.invalid",
        ):
            with self.subTest(unsafe=label):
                _normalized, issues = design_diagrams._mermaid_label_issues(
                    "DIAGRAM-0001",
                    "ACT-001",
                    label,
                    current_ids,
                )
                self.assertTrue(
                    any("external or active URI" in issue for issue in issues),
                    issues,
                )

        _normalized, issues = design_diagrams._mermaid_label_issues(
            "DIAGRAM-0001",
            "ACT-001",
            "Current TECH-0001 runtime",
            current_ids,
        )
        self.assertTrue(any("canonical record ID" in issue for issue in issues))

    def test_public_diagram_evaluator_preserves_1234_call_contract(self) -> None:
        signature = inspect.signature(design.derive_diagram_contract)
        self.assertEqual(
            tuple(signature.parameters),
            (
                "text",
                "architecture",
                "requirements",
                "coverage",
                "required",
                "grandfathered_schema5",
            ),
        )
        contract, issues = design.derive_diagram_contract(
            (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8"),
            design.ArchitectureContract(),
            doctor.RequirementsContract(),
            doctor.CoverageContract(),
            required=False,
            grandfathered_schema5=False,
        )
        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "TEMPLATE")

    def test_doctor_facade_delegates_complete_design_to_pure_engine(self) -> None:
        source = doctor_fixtures.complete_design_contract(
            (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        captured: dict[str, object] = {}
        evaluator = doctor._derive_design_contract_core

        def capture(*args: object, **kwargs: object):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return evaluator(*args, **kwargs)

        with mock.patch.object(
            doctor, "_derive_design_contract_core", side_effect=capture
        ):
            facade_contract, facade_issues = doctor.derive_design_contract(
                source, "DES-0001", required=True
            )

        core_contract, core_issues = evaluator(
            *captured["args"],
            **captured["kwargs"],  # type: ignore[arg-type]
        )
        self.assertEqual(facade_issues, [])
        self.assertEqual(core_issues, facade_issues)
        self.assertEqual(core_contract.to_dict(), facade_contract.to_dict())
        self.assertIs(evaluator, design.derive_design_contract)
        with self.assertRaises(FrozenInstanceError):
            facade_contract.status = "BLOCKED"  # type: ignore[misc]

    def test_adr_facade_and_observed_source_evaluator_are_exactly_equal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adr_directory = root / "docs/adr"
            adr_directory.mkdir(parents=True)
            (adr_directory / "0001-runtime.md").write_text(
                adr_fixtures.adr_text(), encoding="utf-8"
            )
            contract = adr_fixtures.design_contract()
            facade = fastlane_adr.derive_adr_rationale(root, contract, "")
            inventory, inventory_issues = fastlane_adr._safe_adr_inventory(root)
            sources: dict[str, str] = {}
            source_issues: dict[str, dict[str, str]] = {}
            for relative in inventory.values():
                text, issue = fastlane_adr._read_adr(root, relative)
                if issue is not None:
                    source_issues[relative] = issue
                elif text is not None:
                    sources[relative] = text
            pure = design_adr.derive_adr_rationale(
                contract,
                "",
                inventory,
                sources,
                inventory_issues=inventory_issues,
                source_issues=source_issues,
            )
        self.assertEqual(pure, facade)
        self.assertEqual(pure[0]["status"], "CURRENT")
        self.assertFalse(pure[0]["authoritative"])

    def test_design_domain_has_no_observation_or_sibling_domain_imports(self) -> None:
        forbidden_imports = {
            "boto3",
            "os",
            "requests",
            "socket",
            "subprocess",
            "urllib",
        }
        forbidden_calls = {
            "open",
            "iterdir",
            "read_bytes",
            "read_text",
            "stat",
            "write_bytes",
            "write_text",
        }
        sibling_domains = {"authority", "aws", "define", "deliver"}
        failures: list[str] = []
        for path in sorted(DESIGN_PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_imports:
                            failures.append(f"{path.name}: imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.split(".")[0] in forbidden_imports:
                        failures.append(f"{path.name}: imports {module}")
                    if any(part in sibling_domains for part in module.split(".")):
                        failures.append(f"{path.name}: imports sibling {module}")
                elif isinstance(node, ast.Call):
                    if (
                        isinstance(node.func, ast.Name)
                        and node.func.id in forbidden_calls
                    ):
                        failures.append(f"{path.name}: calls {node.func.id}")
                    elif (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr in forbidden_calls
                    ):
                        failures.append(f"{path.name}: calls {node.func.attr}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
