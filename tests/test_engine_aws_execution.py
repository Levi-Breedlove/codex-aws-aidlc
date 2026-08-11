from __future__ import annotations

import hashlib
import re
import unittest
from datetime import datetime, timedelta
from typing import Mapping

from tests.test_bootstrap_doctor import (
    PROJECT_ROOT,
    REPOSITORY_ROOT,
    aws_authority_envelope,
    doctor,
    ready_preflight,
    record_aws_core_evidence,
    set_receipt,
)


class AwsExecutionContractRegressionTests(unittest.TestCase):
    def test_req_materiality_modes_and_unresolved_required_fact(self) -> None:
        cases = (
            (
                {
                    "AWS Core materiality": "REQUIRED",
                    "AWS materiality basis IDs": "REQ-0001, SEC-0001",
                    "AWS Core discovery IDs": "AWS-DISC-0001",
                    "Unresolved material AWS fact IDs": "NONE",
                },
                "REQUIRED",
            ),
            (
                {
                    "AWS Core materiality": "OPTIONAL",
                    "AWS materiality basis IDs": "NONE — current AWS facts do not block Gate A",
                    "AWS Core discovery IDs": "NONE — live evidence is optional for this decision",
                    "Unresolved material AWS fact IDs": "NONE",
                },
                "OPTIONAL",
            ),
            (
                {
                    "AWS Core materiality": "NOT_MATERIAL",
                    "AWS materiality basis IDs": "NONE — no AWS-specific fact affects Gate A",
                    "AWS Core discovery IDs": "NONE — AWS evidence is not material to Gate A",
                    "Unresolved material AWS fact IDs": "NONE",
                },
                "NOT_MATERIAL",
            ),
        )
        for fields, expected in cases:
            with self.subTest(materiality=expected):
                result, issues = doctor.derive_req_aws_materiality(
                    fields,
                    "REQ-0001",
                    required=True,
                    grandfather_current_gate_a=False,
                )
                self.assertEqual(issues, [])
                self.assertEqual(result["materiality"], expected)
                self.assertEqual(result["status"], "CURRENT")

        blocked, issues = doctor.derive_req_aws_materiality(
            {
                "AWS Core materiality": "REQUIRED",
                "AWS materiality basis IDs": "REQ-0001, SEC-0001",
                "AWS Core discovery IDs": "AWS-DISC-0001",
                "Unresolved material AWS fact IDs": "SEC-0002",
            },
            "REQ-0001",
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertTrue(any("unresolved" in issue.lower() for issue in issues), issues)

    def test_req_evidence_matches_exact_basis_without_selecting_architecture(
        self,
    ) -> None:
        verify_text = (REPOSITORY_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        passed = record_aws_core_evidence(
            verify_text,
            "REQ-10",
            binding="REQ-0001",
            discovery_id="AWS-DISC-0001",
            basis_ids="REQ-0001, SEC-0001",
            advisory_design_binding=(
                "NOT_APPLICABLE — requirements feasibility only; no architecture selected"
            ),
        )
        rows = doctor.parse_aws_core_evidence(passed)
        self.assertEqual(
            doctor.aws_core_phase_evidence_issues(
                rows,
                "REQ-10",
                expected_binding="REQ-0001",
                expected_basis_ids={"REQ-0001", "SEC-0001"},
            ),
            [],
        )
        wrong_basis = doctor.aws_core_phase_evidence_issues(
            rows,
            "REQ-10",
            expected_binding="REQ-0001",
            expected_basis_ids={"REQ-0001", "SEC-0002"},
        )
        self.assertTrue(any("exactly match" in issue for issue in wrong_basis))

        premature = record_aws_core_evidence(
            verify_text,
            "REQ-10",
            binding="REQ-0001",
            discovery_id="AWS-DISC-0001",
            basis_ids="REQ-0001, SEC-0001",
            advisory_design_binding="DES-0001; TECH: TECH-0001",
        )
        premature_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(premature),
            "REQ-10",
            expected_binding="REQ-0001",
            expected_basis_ids={"REQ-0001", "SEC-0001"},
        )
        self.assertTrue(any("without selecting" in issue for issue in premature_issues))

    def test_all_four_lanes_have_deterministic_progression(self) -> None:
        materiality = {"materiality": "OPTIONAL", "status": "CURRENT"}
        authority = {
            "validity": "CURRENT",
            "authorization_id": "AWS-READ-AUTH-0001",
        }
        ready = {"status": "READY", "account_access": "READ_ONLY_OBSERVED"}
        not_started = {"status": "NOT_STARTED", "account_access": "NOT_OBSERVED"}

        documentation = doctor.derive_aws_execution_projection(
            materiality,
            release_decision="READY_TO_DEPLOY",
            guidance_ready=True,
            read_authority=None,
            preflight=not_started,
            lane="documentation-only",
        )
        self.assertEqual(documentation["progress_state"], "AWS_PREFLIGHT_READY")
        self.assertEqual(documentation["preflight"]["account_access"], "NOT_USED")

        for lane, expected in (
            ("read-only", "AWS_PREFLIGHT_READY"),
            ("fast-dev", "WAITING_AWS_MUTATION_AUTH"),
            ("explicit-gate", "WAITING_AWS_MUTATION_AUTH"),
        ):
            with self.subTest(lane=lane):
                projected = doctor.derive_aws_execution_projection(
                    materiality,
                    release_decision="READY_TO_DEPLOY",
                    guidance_ready=True,
                    read_authority=authority,
                    preflight=ready,
                    lane=lane,
                )
                self.assertEqual(projected["progress_state"], expected)

        guidance = doctor.derive_aws_execution_projection(
            materiality,
            release_decision="READY_TO_DEPLOY",
            guidance_ready=False,
            read_authority=None,
            preflight=not_started,
            lane="read-only",
        )
        self.assertEqual(guidance["progress_state"], "AWS_GUIDANCE_REQUIRED")

    def test_remediation_fingerprint_binds_revisions_and_escalates_repeat(self) -> None:
        first_context = doctor.Context(PROJECT_ROOT)
        first_context.error(
            "AWS_CORE_DISCOVERY_REQUIRED",
            "Fresh discovery evidence is required",
            doctor.VERIFY_FILE,
        )
        first = doctor.derive_remediation(
            first_context,
            classification="ACTIVE_GREENFIELD",
            gate_a="BLOCKED",
            gate_b="BLOCKED",
            envelope={},
            tasks=doctor.TaskSummary(),
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
        )
        self.assertEqual(first["next_action"]["responsible_party"], "CODEX")
        self.assertEqual(first["retry_state"], "FIRST_OR_NONE")

        repeated_context = doctor.Context(
            PROJECT_ROOT,
            prior_remediation_fingerprint=first["fingerprint"],
        )
        repeated_context.error(
            "AWS_CORE_DISCOVERY_REQUIRED",
            "Fresh discovery evidence is required",
            doctor.VERIFY_FILE,
        )
        repeated = doctor.derive_remediation(
            repeated_context,
            classification="ACTIVE_GREENFIELD",
            gate_a="BLOCKED",
            gate_b="BLOCKED",
            envelope={},
            tasks=doctor.TaskSummary(),
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
        )
        self.assertEqual(repeated["retry_state"], "REPEATED")
        self.assertEqual(repeated["next_action"]["responsible_party"], "HUMAN_REVIEWER")

        changed_revision_context = doctor.Context(
            PROJECT_ROOT,
            prior_remediation_fingerprint=first["fingerprint"],
        )
        changed_revision_context.error(
            "AWS_CORE_DISCOVERY_REQUIRED",
            "Fresh discovery evidence is required",
            doctor.VERIFY_FILE,
        )
        changed_revision = doctor.derive_remediation(
            changed_revision_context,
            classification="ACTIVE_GREENFIELD",
            gate_a="BLOCKED",
            gate_b="BLOCKED",
            envelope={},
            tasks=doctor.TaskSummary(),
            requirements_revision="REQ-0001",
            design_revision="DES-0002",
        )
        self.assertNotEqual(changed_revision["fingerprint"], first["fingerprint"])
        self.assertEqual(changed_revision["next_action"]["responsible_party"], "CODEX")

    def test_aws_evidence_remediation_ownership_is_precise(self) -> None:
        cases = (
            ("AWS_CORE_CAPABILITY_UNAVAILABLE", "OWNER"),
            ("AWS_CORE_EVIDENCE_REQUIRED", "CODEX"),
            ("AWS_CORE_EVIDENCE_STRUCTURE", "HUMAN_REVIEWER"),
        )
        for code, expected in cases:
            with self.subTest(code=code):
                context = doctor.Context(PROJECT_ROOT)
                context.error(code, "evidence problem", doctor.VERIFY_FILE)
                result = doctor.derive_remediation(
                    context,
                    classification="ACTIVE_GREENFIELD",
                    gate_a="APPROVED_FOR_DESIGN",
                    gate_b="BLOCKED",
                    envelope={},
                    tasks=doctor.TaskSummary(),
                    requirements_revision="REQ-0001",
                    design_revision="DES-0001",
                )
                self.assertEqual(result["next_action"]["responsible_party"], expected)

    def test_post_gate_b_aws_evidence_repairs_preserve_approved_prd(self) -> None:
        cases = (
            (
                "AWS_CORE_EVIDENCE_GENERATED_INVALID",
                doctor.VERIFY_FILE,
                "CODEX",
            ),
            (
                "AWS_CORE_EVIDENCE_GENERATED_INVALID",
                doctor.PRD_FILE,
                "HUMAN_REVIEWER",
            ),
            (
                "AWS_CORE_EVIDENCE_STRUCTURE",
                doctor.VERIFY_FILE,
                "HUMAN_REVIEWER",
            ),
        )
        for code, path, expected in cases:
            with self.subTest(code=code, path=path):
                context = doctor.Context(PROJECT_ROOT)
                context.error(code, "evidence problem", path)
                result = doctor.derive_remediation(
                    context,
                    classification="ACTIVE_GREENFIELD",
                    gate_a="APPROVED_FOR_DESIGN",
                    gate_b="APPROVED_FOR_CONSTRUCTION",
                    envelope={},
                    tasks=doctor.TaskSummary(),
                    requirements_revision="REQ-0001",
                    design_revision="DES-0001",
                    owner_stage_hint="DESIGN",
                )
                self.assertEqual(result["next_action"]["responsible_party"], expected)
                if expected == "CODEX":
                    repeated_context = doctor.Context(
                        PROJECT_ROOT,
                        prior_remediation_fingerprint=result["fingerprint"],
                    )
                    repeated_context.error(code, "evidence problem", path)
                    repeated = doctor.derive_remediation(
                        repeated_context,
                        classification="ACTIVE_GREENFIELD",
                        gate_a="APPROVED_FOR_DESIGN",
                        gate_b="APPROVED_FOR_CONSTRUCTION",
                        envelope={},
                        tasks=doctor.TaskSummary(),
                        requirements_revision="REQ-0001",
                        design_revision="DES-0001",
                        owner_stage_hint="DESIGN",
                    )
                    self.assertEqual(
                        repeated["next_action"]["responsible_party"],
                        "HUMAN_REVIEWER",
                    )

    def test_teardown_receipt_cannot_satisfy_deployment_wait(self) -> None:
        context = doctor.Context(PROJECT_ROOT)
        context.texts[doctor.VERIFY_FILE] = "verification"
        calls: list[str] = []
        original = doctor._receipt_external_authority

        def fake_receipt(
            _text: str, action: str, _construction_authorization: str, **_kwargs: object
        ) -> dict[str, object] | None:
            calls.append(action)
            if action == "Teardown":
                return {"kind": "AWS_TEARDOWN", "validity": "CURRENT"}
            return None

        doctor._receipt_external_authority = fake_receipt
        try:
            result = doctor.derive_external_authority(
                context,
                {"AWS boundary": "MUTATE_LISTED_RESOURCES"},
                "explicit-gate",
                "AUTH-0001",
                aws_progress_state="WAITING_AWS_MUTATION_AUTH",
                aws_action_phase="AWS-20",
                preflight={
                    "status": "READY",
                    "preflight_id": "AWS-PREFLIGHT-0001",
                    "account_access": "READ_ONLY_OBSERVED",
                },
            )
        finally:
            doctor._receipt_external_authority = original
        self.assertEqual(calls, ["Deployment"])
        self.assertEqual(result["kind"], "AWS_ACTION_RECEIPT_REQUIRED")
        self.assertEqual(result["validity"], "REQUIRED")

    def test_read_preflight_artifact_mismatch_is_stale(self) -> None:
        artifact_a = "sha256:" + ("a" * 64)
        artifact_b = "sha256:" + ("b" * 64)
        authority = {
            "validity": "CURRENT",
            "authorization_id": "AWS-READ-AUTH-0001",
            "account": "123456789012",
            "region": "us-west-2",
            "environment": "development",
            "role_or_profile": "audit-role",
            "resources": ["bucket-a"],
            "operations": ["s3:GetObject"],
            "artifact_plan_binding": {"artifact": artifact_a, "plan": "NONE"},
        }
        values = (
            "AWS-PREFLIGHT-0001",
            "AWS-READ-AUTH-0001",
            "REQ-0001 / DES-0001 / AUTH-0001",
            artifact_b,
            "audit-role",
            "123456789012",
            "us-west-2",
            "development",
            "bucket-a",
            "s3:GetObject",
            "EV-0001",
            "READ_ONLY_OBSERVED",
            "EV-0002",
            "EV-0003",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:01:00+00:00",
            "PASS",
            "READY",
        )
        table = "\n".join(
            (
                doctor.AWS_READ_PREFLIGHT_HEADING,
                "| " + " | ".join(doctor.AWS_READ_PREFLIGHT_HEADERS) + " |",
                "|" + "|".join("---" for _ in doctor.AWS_READ_PREFLIGHT_HEADERS) + "|",
                "| " + " | ".join(values) + " |",
            )
        )
        result = doctor.derive_read_preflight_state(
            table,
            authority,
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            construction_authorization="AUTH-0001",
            artifact_binding=artifact_b,
        )
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["account_access"], "NOT_VERIFIED")
        self.assertTrue(
            any("receipt artifact" in issue.lower() for issue in result["issues"])
        )

    def test_read_authority_requires_bounded_cost_provenance(self) -> None:
        receipt_lines = [
            "AUTHORIZE AWS READ-ONLY PREFLIGHT",
            "Read authorization: AWS-READ-AUTH-0001",
            "Construction authorization: AUTH-0001",
            "Profile or role: audit-role",
            "Account: 123456789012",
            "Region: us-west-2",
            "Environment: development",
            "Stack, application, and resources: bucket-a",
            "Allowed read-only operations: s3:GetObject",
            "Artifact digest: sha256:" + ("a" * 64),
            "Prohibited operations: ALL_MUTATIONS",
            "Valid until: ONE_OPERATION",
            "Approver: owner-handle",
        ]
        receipt = "\n".join(receipt_lines)
        digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        headers = (
            "Action",
            "Authorization ID",
            "Construction AUTH",
            "Role or profile",
            "Artifact digest",
            "IaC plan/change-set binding",
            "Account / Region / environment",
            "Resources and operations",
            "Cost ceiling and validity",
            "Rollback boundary",
            "Stable owner-message source",
            "Approver",
            "Observed at",
            "Verbatim receipt SHA-256",
            "Preflight evidence",
            "Identity and boundary match",
            "Result",
        )

        def document(cost: str) -> str:
            row = (
                "Read-only preflight",
                "AWS-READ-AUTH-0001",
                "AUTH-0001",
                "audit-role",
                "sha256:" + ("a" * 64),
                "NOT_APPLICABLE — read-only preflight creates no plan",
                "ACCOUNT: 123456789012; REGION: us-west-2; ENVIRONMENT: development",
                "RESOURCES: bucket-a; OPERATIONS: s3:GetObject",
                cost,
                "NOT_APPLICABLE — no mutation",
                "owner-message-1",
                "owner-handle",
                "2026-01-01T00:00:00+00:00",
                digest,
                "NONE",
                "PASS",
                "AUTHORIZED",
            )
            return "\n".join(
                (
                    "<!-- bootstrap:aws-read-preflight-receipt:start -->",
                    "```text",
                    receipt,
                    "```",
                    "<!-- bootstrap:aws-read-preflight-receipt:end -->",
                    "## Action authorization provenance",
                    "| " + " | ".join(headers) + " |",
                    "|" + "|".join("---" for _ in headers) + "|",
                    "| " + " | ".join(row) + " |",
                    "| Deployment | " + " | ".join("TODO" for _ in headers[1:]) + " |",
                )
            )

        cost_posture = "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00"
        active_artifact = "sha256:" + ("a" * 64)
        envelope = aws_authority_envelope(
            role="audit-role",
            account="123456789012",
            region="us-west-2",
            environment="development",
            resources=["bucket-a"],
            operations=["s3:GetObject"],
            artifact=active_artifact,
            rollback="NONE",
            boundary="READ_ONLY",
        )

        valid = document(
            "COST: expected low-volume request charges under USD 0.01; "
            f"BOUNDED_BY: {cost_posture}; "
            "VALID_UNTIL: ONE_OPERATION"
        )
        authority = doctor._read_preflight_receipt_authority(
            valid, "AUTH-0001", cost_posture, envelope, active_artifact
        )
        self.assertIsNotNone(authority)
        self.assertIn("BOUNDED_BY", authority["cost_ceiling"])
        invalid = document(
            "COST: NOT_APPLICABLE — read-only; BOUNDED_BY: USD 20.00; "
            "VALID_UNTIL: ONE_OPERATION"
        )
        self.assertIsNone(
            doctor._read_preflight_receipt_authority(
                invalid, "AUTH-0001", cost_posture, envelope, active_artifact
            )
        )
        nonhuman_receipt = receipt.replace("Approver: owner-handle", "Approver: Codex")
        nonhuman_digest = (
            "sha256:" + hashlib.sha256(nonhuman_receipt.encode("utf-8")).hexdigest()
        )
        nonhuman = set_receipt(valid, "aws-read-preflight", nonhuman_receipt)
        nonhuman = nonhuman.replace(" | owner-handle | ", " | Codex | ", 1).replace(
            digest, nonhuman_digest, 1
        )
        self.assertIsNone(
            doctor._read_preflight_receipt_authority(
                nonhuman, "AUTH-0001", cost_posture, envelope, active_artifact
            )
        )

        for operation in (
            "ec2:RunInstances",
            "iam:AttachRolePolicy",
            "dynamodb:BatchWriteItem",
            "s3:RestoreObject",
        ):
            with self.subTest(operation=operation):
                mutation_receipt = receipt.replace("s3:GetObject", operation)
                mutation_digest = (
                    "sha256:"
                    + hashlib.sha256(mutation_receipt.encode("utf-8")).hexdigest()
                )
                mutation = set_receipt(valid, "aws-read-preflight", mutation_receipt)
                mutation = mutation.replace(
                    "RESOURCES: bucket-a; OPERATIONS: s3:GetObject",
                    f"RESOURCES: bucket-a; OPERATIONS: {operation}",
                    1,
                ).replace(digest, mutation_digest, 1)
                self.assertIsNone(
                    doctor._read_preflight_receipt_authority(
                        mutation,
                        "AUTH-0001",
                        cost_posture,
                        envelope,
                        active_artifact,
                    )
                )

    def test_teardown_authority_requires_an_explicit_human_approver(self) -> None:
        verify_text = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )

        def document(approver: str) -> str:
            receipt = "\n".join(
                (
                    "AUTHORIZE AWS TEARDOWN",
                    "Teardown authorization: TEARDOWN-AUTH-0001",
                    "Construction authorization: AUTH-0001",
                    "Profile or role: cleanup-role",
                    "Account: 111122223333",
                    "Region: us-west-2",
                    "Environment: development",
                    "Stack, application, and resources to remove: fastlane-stack",
                    "Resources and data to retain: NONE",
                    "Allowed deletion operations: cloudformation:DeleteStack",
                    "Shared dependencies: NONE",
                    "Cost effect: removes stack billing",
                    "Post-teardown verification: cloudformation:DescribeStacks",
                    "Valid until: 2099-01-01T00:00:00Z",
                    f"Approver: {approver}",
                )
            )
            digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
            row = (
                "Teardown",
                "TEARDOWN-AUTH-0001",
                "AUTH-0001",
                "cleanup-role",
                "NOT_APPLICABLE — teardown binds the observed inventory",
                "NOT_APPLICABLE — teardown uses its removal/retention manifest",
                "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
                "RESOURCES: fastlane-stack; OPERATIONS: cloudformation:DeleteStack",
                "COST: removes stack billing; VALID_UNTIL: 2099-01-01T00:00:00Z",
                "cloudformation:DescribeStacks",
                "owner-message-2",
                approver,
                "2027-01-01T00:00:00Z",
                digest,
                "EV-0040",
                "PASS",
                "READY",
            )
            rendered = set_receipt(verify_text, "aws-teardown", receipt)
            lines = rendered.splitlines()
            for index, line in enumerate(lines):
                if line.startswith("| Teardown | TODO |"):
                    lines[index] = "| " + " | ".join(row) + " |"
                    break
            else:
                self.fail("Teardown authorization provenance row not found")
            return "\n".join(lines) + "\n"

        envelope = aws_authority_envelope(
            role="cleanup-role",
            account="111122223333",
            region="us-west-2",
            environment="development",
            resources=["fastlane-stack"],
            operations=["cloudformation:DeleteStack"],
            artifact="sha256:" + "a" * 64,
            rollback="restore stack from approved IaC",
        )
        teardown_review = {
            "status": "READY_FOR_TEARDOWN",
            "evidence_id": "EV-0040",
            "read_authorization": "AWS-READ-AUTH-0001",
            "read_role_or_profile": "inventory-role",
            "read_receipt_digest": "sha256:" + "b" * 64,
            "read_valid_until": "2099-01-01T00:00:00Z",
            "read_authority_source": "owner-message-read-1",
            "resources_to_remove": ["fastlane-stack"],
            "allowed_operations": ["cloudformation:DeleteStack"],
            "resources_to_retain": [],
            "shared_dependencies": [],
            "cost_effect": "removes stack billing",
            "post_action_verification": "cloudformation:DescribeStacks",
            "role_or_profile": "cleanup-role",
            "account": "111122223333",
            "region": "us-west-2",
            "environment": "development",
            "identity_and_boundary_match": "PASS",
        }
        authority = doctor._receipt_external_authority(
            document("Alice Rivera"),
            "Teardown",
            "AUTH-0001",
            envelope=envelope,
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            active_artifact="sha256:" + "a" * 64,
            teardown_review=teardown_review,
        )
        self.assertIsNotNone(authority)
        self.assertEqual(authority["kind"], "AWS_TEARDOWN")
        self.assertEqual(authority["cost_ceiling"], "USD: 20.00")
        self.assertNotEqual(authority["cost_ceiling"], "removes stack billing")
        self.assertEqual(
            authority["rollback_boundary"],
            "ROLLBACK: restore stack from approved IaC",
        )
        self.assertNotEqual(
            authority["rollback_boundary"], "cloudformation:DescribeStacks"
        )
        teardown_binding = doctor.derive_request_match(
            doctor.Context(PROJECT_ROOT), authority
        )["teardown_ready_binding"]
        self.assertEqual(teardown_binding["read_role_or_profile"], "inventory-role")
        self.assertEqual(teardown_binding["read_receipt_digest"], "sha256:" + "b" * 64)
        self.assertEqual(teardown_binding["read_valid_until"], "2099-01-01T00:00:00Z")
        self.assertEqual(
            teardown_binding["read_authority_source"], "owner-message-read-1"
        )
        self.assertIsNone(
            doctor._receipt_external_authority(
                document("Codex"),
                "Teardown",
                "AUTH-0001",
                envelope=envelope,
                cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
                active_artifact="sha256:" + "a" * 64,
                teardown_review=teardown_review,
            )
        )

    def test_teardown_sequence_routes_by_current_phase_evidence(self) -> None:
        envelope = aws_authority_envelope(
            role="cleanup-role",
            account="111122223333",
            region="us-west-2",
            environment="development",
            resources=["fastlane-stack"],
            operations=["cloudformation:DeleteStack"],
            artifact="sha256:" + "a" * 64,
            rollback="restore stack from approved IaC",
        )
        read_receipt_digest = "sha256:" + "b" * 64
        read_authority = {
            "kind": "AWS_READ_ONLY",
            "validity": "CURRENT",
            "authorization_id": "AWS-READ-AUTH-0001",
            "receipt_digest": read_receipt_digest,
            "role_or_profile": "inventory-role",
            "account": "111122223333",
            "region": "us-west-2",
            "environment": "development",
            "resources": ["fastlane-stack"],
            "operations": ["cloudformation:DescribeStacks"],
            "expiration": "2099-01-01T00:00:00Z",
            "authority_source": "owner-message-read-1",
            "authorized_at": "2026-12-31T00:00:00Z",
        }

        receipt = "\n".join(
            (
                "AUTHORIZE AWS TEARDOWN",
                "Teardown authorization: TEARDOWN-AUTH-0001",
                "Construction authorization: AUTH-0001",
                "Profile or role: cleanup-role",
                "Account: 111122223333",
                "Region: us-west-2",
                "Environment: development",
                "Stack, application, and resources to remove: fastlane-stack",
                "Resources and data to retain: NONE",
                "Allowed deletion operations: cloudformation:DeleteStack",
                "Shared dependencies: NONE",
                "Cost effect: removes stack billing",
                "Post-teardown verification: cloudformation:DescribeStacks",
                "Valid until: 2099-01-01T00:00:00Z",
                "Approver: Alice Rivera",
            )
        )
        receipt_digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        provenance_headers = (
            "Action",
            "Authorization ID",
            "Construction AUTH",
            "Role or profile",
            "Artifact digest",
            "IaC plan/change-set binding",
            "Account / Region / environment",
            "Resources and operations",
            "Cost ceiling and validity",
            "Rollback boundary",
            "Stable owner-message source",
            "Approver",
            "Observed at",
            "Verbatim receipt SHA-256",
            "Preflight evidence",
            "Identity and boundary match",
            "Result",
        )
        provenance_row = (
            "Teardown",
            "TEARDOWN-AUTH-0001",
            "AUTH-0001",
            "cleanup-role",
            "NOT_APPLICABLE \u2014 teardown binds the observed inventory",
            "NOT_APPLICABLE \u2014 teardown uses its removal/retention manifest",
            "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
            "RESOURCES: fastlane-stack; OPERATIONS: cloudformation:DeleteStack",
            "COST: removes stack billing; VALID_UNTIL: 2099-01-01T00:00:00Z",
            "cloudformation:DescribeStacks",
            "owner-message-2",
            "Alice Rivera",
            "2027-01-01T00:00:00Z",
            receipt_digest,
            "EV-0040",
            "PASS",
            "READY",
        )

        def evidence_row(
            phase: str,
            status: str,
            *,
            evidence_id: str = "EV-0040",
            observed_at: str = "2027-01-01T00:00:00Z",
            read_authorization: str = "AWS-READ-AUTH-0001",
            read_role_or_profile: str = "inventory-role",
            read_digest: str = read_receipt_digest,
            read_valid_until: str = "2099-01-01T00:00:00Z",
            read_authority_source: str = (
                "SOURCE: owner-message-read-1; AUTHORIZED_AT: 2026-12-31T00:00:00Z"
            ),
            teardown_authorization: str | None = None,
            teardown_receipt_digest: str | None = None,
            terminal_status: str | None = None,
            resources_removed: str | None = None,
            residual_resources: str | None = None,
            blocker_or_stale_reason: str | None = None,
        ) -> str:
            action_phase = phase == "AWS-50"
            if teardown_authorization is None:
                teardown_authorization = (
                    "TEARDOWN-AUTH-0001" if action_phase else "NONE"
                )
            if teardown_receipt_digest is None:
                teardown_receipt_digest = receipt_digest if action_phase else "NONE"
            if terminal_status is None:
                terminal_status = {
                    "SUCCEEDED": "DELETE_COMPLETE",
                    "FAILED": "DELETE_FAILED",
                    "PARTIAL": "PARTIAL_DELETE",
                    "UNKNOWN": "TERMINAL_STATUS_UNDETERMINED",
                    "VERIFIED_CLEAN": "STACK_ABSENT",
                    "RESIDUALS_REMAIN": "STACK_OR_RESOURCES_REMAIN",
                }.get(status, "NONE")
            if resources_removed is None:
                resources_removed = (
                    "fastlane-stack"
                    if status in {"SUCCEEDED", "VERIFIED_CLEAN"}
                    else "NONE"
                )
            if residual_resources is None:
                residual_resources = (
                    "fastlane-stack"
                    if status in {"FAILED", "PARTIAL", "UNKNOWN", "RESIDUALS_REMAIN"}
                    else "NONE"
                )
            if blocker_or_stale_reason is None:
                blocker_or_stale_reason = (
                    "caller identity could not be verified"
                    if status == "BLOCKED"
                    else "read evidence no longer matches the current basis"
                    if status == "STALE"
                    else "NONE"
                )
            values = {
                "Evidence ID": evidence_id,
                "Attempt ID": (
                    "AWS-TEARDOWN-0001"
                    if action_phase or teardown_authorization != "NONE"
                    else "NONE"
                ),
                "Phase": phase,
                "REQ / DES / AUTH": "REQ-0001 / DES-0001 / AUTH-0001",
                "Read authorization": read_authorization,
                "Read role or profile": read_role_or_profile,
                "Read receipt digest": read_digest,
                "Read valid until": read_valid_until,
                "Read authority source": read_authority_source,
                "Teardown authorization": teardown_authorization,
                "Teardown receipt digest": teardown_receipt_digest,
                "Role or profile": "cleanup-role",
                "Expected manifest or stack": "fastlane-stack",
                "Resources proposed to remove": "fastlane-stack",
                "Allowed deletion operations": "cloudformation:DeleteStack",
                "Resources retained": "NONE",
                "Shared dependencies": "NONE",
                "Cost effect": "removes stack billing",
                "Post-teardown verification": "cloudformation:DescribeStacks",
                "Stack events and terminal status": terminal_status,
                "Resources removed": resources_removed,
                "Snapshots and backups": "NONE",
                "Residual resources": residual_resources,
                "Inventory or discovery limits": "CloudFormation stack scope",
                "Account / Region / environment": (
                    "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development"
                ),
                "Observed at": observed_at,
                "Durable source": f"docs/project/VERIFY.md#{evidence_id.lower()}",
                "Identity and boundary match": "PASS",
                "Blocker or stale reason": blocker_or_stale_reason,
                "Status": status,
            }
            return (
                "| "
                + " | ".join(
                    values[field] for field in doctor.AWS_TEARDOWN_EVIDENCE_HEADERS
                )
                + " |"
            )

        def document(*rows: str, duplicate_provenance: bool = False) -> str:
            headers = doctor.AWS_TEARDOWN_EVIDENCE_HEADERS
            rendered_provenance = "| " + " | ".join(provenance_row) + " |"
            placeholder_provenance = (
                "| Read-only preflight | "
                + " | ".join("TODO" for _ in provenance_headers[1:])
                + " |"
            )
            provenance_rows = [placeholder_provenance, rendered_provenance]
            if duplicate_provenance:
                provenance_rows.append(rendered_provenance)
            expanded_rows: list[str] = []
            for rendered in rows:
                for rendered_row in rendered.splitlines():
                    cells = [cell.strip() for cell in rendered_row[1:-1].split("|")]
                    row_values = dict(zip(headers, cells))
                    if (
                        row_values["Phase"] == "AWS-50"
                        and row_values["Status"] != "STARTED"
                    ):
                        started = dict(row_values)
                        evidence_digits = re.fullmatch(
                            r"EV-(\d{4,})", row_values["Evidence ID"]
                        )
                        suffix = (
                            evidence_digits.group(1)[-3:] if evidence_digits else "999"
                        )
                        started["Evidence ID"] = "EV-9" + suffix
                        observed = datetime.fromisoformat(
                            row_values["Observed at"].replace("Z", "+00:00")
                        ) - timedelta(seconds=1)
                        started["Observed at"] = observed.isoformat().replace(
                            "+00:00", "Z"
                        )
                        started["Stack events and terminal status"] = (
                            doctor.AWS_TEARDOWN_PRECALL_RESULT
                        )
                        started["Resources removed"] = "NONE"
                        started["Snapshots and backups"] = "NONE"
                        started["Residual resources"] = "NONE"
                        started["Inventory or discovery limits"] = (
                            doctor.AWS_TEARDOWN_PRECALL_RESULT
                        )
                        started["Durable source"] = "pre-call teardown journal"
                        started["Blocker or stale reason"] = "NONE"
                        started["Status"] = "STARTED"
                        expanded_rows.append(
                            "| "
                            + " | ".join(started[field] for field in headers)
                            + " |"
                        )
                    expanded_rows.append(rendered_row)
            return "\n".join(
                (
                    "<!-- bootstrap:aws-teardown-receipt:start -->",
                    "```text",
                    receipt,
                    "```",
                    "<!-- bootstrap:aws-teardown-receipt:end -->",
                    "",
                    "## Action authorization provenance",
                    "| " + " | ".join(provenance_headers) + " |",
                    "|" + "|".join("---" for _ in provenance_headers) + "|",
                    *provenance_rows,
                    "",
                    doctor.AWS_TEARDOWN_EVIDENCE_HEADING,
                    "",
                    "| " + " | ".join(headers) + " |",
                    "|" + "|".join("---" for _ in headers) + "|",
                    *expanded_rows,
                )
            )

        def derive(
            text: str,
            authority: Mapping[str, object] | None = read_authority,
        ) -> dict[str, object]:
            return doctor.derive_teardown_sequence_state(
                text,
                authority,
                requirements_revision="REQ-0001",
                design_revision="DES-0001",
                construction_authorization="AUTH-0001",
                envelope=envelope,
                cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
                active_artifact="sha256:" + "a" * 64,
            )

        self.assertEqual(derive(document())["status"], "NOT_ACTIVE")
        running = derive(document(evidence_row("AWS-40", "RUNNING")))
        self.assertEqual(running["status"], "RUNNING")
        ready_row = evidence_row("AWS-40", "READY_FOR_TEARDOWN")
        ready = derive(document(ready_row))
        self.assertEqual(ready["status"], "READY_FOR_TEARDOWN")
        self.assertEqual(ready["resources_to_remove"], ["fastlane-stack"])
        blocked = derive(document(evidence_row("AWS-40", "BLOCKED")))
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertEqual(
            blocked["blocker_or_stale_reason"],
            "caller identity could not be verified",
        )
        self.assertEqual(blocked["issues"], [])

        latest_epoch = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-40",
                    "BLOCKED",
                    evidence_id="EV-0041",
                    observed_at="2027-01-01T00:00:01Z",
                ),
            )
        )
        self.assertEqual(latest_epoch["status"], "BLOCKED")
        self.assertEqual(latest_epoch["evidence_id"], "EV-0041")

        nonadjacent_ready = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-40",
                    "RUNNING",
                    evidence_id="EV-0042",
                    observed_at="2027-01-01T00:00:01Z",
                ),
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0043",
                    observed_at="2027-01-01T00:00:03Z",
                ),
            )
        )
        self.assertEqual(nonadjacent_ready["status"], "BLOCKED")
        self.assertTrue(
            any("immediately follow" in issue for issue in nonadjacent_ready["issues"])
        )

        tampered_read_tuple = derive(
            document(
                evidence_row(
                    "AWS-40",
                    "READY_FOR_TEARDOWN",
                    evidence_id="EV-0044",
                    read_role_or_profile="cleanup-role",
                )
            )
        )
        self.assertEqual(tampered_read_tuple["status"], "BLOCKED")
        self.assertTrue(
            any("read role" in issue for issue in tampered_read_tuple["issues"])
        )

        action_results: dict[str, dict[str, object]] = {}
        action_cases = (
            ("SUCCEEDED", "EV-0050", "2027-01-02T00:00:00Z"),
            ("FAILED", "EV-0051", "2027-01-02T00:00:01Z"),
            ("PARTIAL", "EV-0052", "2027-01-02T00:00:02Z"),
            ("UNKNOWN", "EV-0053", "2027-01-02T00:00:03Z"),
        )
        for action_status, evidence_id, observed_at in action_cases:
            with self.subTest(action_status=action_status):
                post_action = derive(
                    document(
                        ready_row,
                        evidence_row(
                            "AWS-50",
                            action_status,
                            evidence_id=evidence_id,
                            observed_at=observed_at,
                        ),
                    )
                )
                action_results[action_status] = post_action
                self.assertEqual(
                    post_action["status"], "POST_ACTION_REVIEW", post_action["issues"]
                )
                self.assertEqual(post_action["action_status"], action_status)
                self.assertEqual(
                    post_action["teardown_authorization"],
                    "TEARDOWN-AUTH-0001",
                )
                self.assertEqual(post_action["teardown_receipt_digest"], receipt_digest)
                self.assertEqual(
                    post_action["read_receipt_digest"], read_receipt_digest
                )

        post_action_authority = doctor.derive_external_authority(
            doctor.Context(PROJECT_ROOT),
            envelope,
            "explicit-gate",
            "NONE",
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            active_artifact="sha256:" + "a" * 64,
            aws_action_phase="AWS-40",
            teardown_review=action_results["SUCCEEDED"],
        )
        self.assertEqual(post_action_authority["kind"], "AWS_READ_ONLY")
        self.assertEqual(post_action_authority["attempt_id"], "AWS-TEARDOWN-0001")

        verified_document = document(
            ready_row,
            evidence_row(
                "AWS-50",
                "SUCCEEDED",
                evidence_id="EV-0060",
                observed_at="2027-01-03T00:00:00Z",
            ),
            evidence_row(
                "AWS-40",
                "VERIFIED_CLEAN",
                evidence_id="EV-0061",
                observed_at="2027-01-03T00:00:01Z",
                teardown_authorization="TEARDOWN-AUTH-0001",
                teardown_receipt_digest=receipt_digest,
            ),
        )
        verified = derive(verified_document)
        self.assertEqual(verified["status"], "VERIFIED_CLEAN", verified["issues"])
        residuals = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "PARTIAL",
                    evidence_id="EV-0062",
                    observed_at="2027-01-03T00:00:02Z",
                ),
                evidence_row(
                    "AWS-40",
                    "RESIDUALS_REMAIN",
                    evidence_id="EV-0063",
                    observed_at="2027-01-03T00:00:03Z",
                    teardown_authorization="TEARDOWN-AUTH-0001",
                    teardown_receipt_digest=receipt_digest,
                ),
            )
        )
        self.assertEqual(residuals["status"], "RESIDUALS_REMAIN", residuals["issues"])

        missing_terminal_read_proof = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-6060",
                    observed_at="2027-01-03T00:01:00Z",
                ),
                evidence_row(
                    "AWS-40",
                    "VERIFIED_CLEAN",
                    evidence_id="EV-6061",
                    observed_at="2027-01-03T00:01:01Z",
                    read_authority_source="owner-message-read-1",
                    teardown_authorization="TEARDOWN-AUTH-0001",
                    teardown_receipt_digest=receipt_digest,
                ),
            )
        )
        self.assertEqual(missing_terminal_read_proof["status"], "BLOCKED")
        self.assertTrue(
            any(
                "source and ISO authorization timestamp" in issue
                for issue in missing_terminal_read_proof["issues"]
            )
        )

        mismatched_terminal_read_proof = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-6062",
                    observed_at="2027-01-03T00:02:00Z",
                ),
                evidence_row(
                    "AWS-40",
                    "VERIFIED_CLEAN",
                    evidence_id="EV-6063",
                    observed_at="2027-01-03T00:02:01Z",
                    read_authority_source=(
                        "SOURCE: owner-message-read-1; "
                        "AUTHORIZED_AT: 2026-12-30T00:00:00Z"
                    ),
                    teardown_authorization="TEARDOWN-AUTH-0001",
                    teardown_receipt_digest=receipt_digest,
                ),
            )
        )
        self.assertEqual(mismatched_terminal_read_proof["status"], "BLOCKED")
        self.assertTrue(
            any(
                "read authorization timestamp is tampered" in issue
                for issue in mismatched_terminal_read_proof["issues"]
            )
        )

        mismatched_terminal_scope = derive(
            verified_document,
            {
                **read_authority,
                "resources": ["fastlane-stack", "unrelated-stack"],
            },
        )
        self.assertEqual(mismatched_terminal_scope["status"], "BLOCKED")
        self.assertTrue(
            any(
                "recorded resources do not match exact read scope" in issue
                for issue in mismatched_terminal_scope["issues"]
            )
        )

        expired_terminal_proof = derive(
            verified_document,
            {**read_authority, "validity": "EXPIRED"},
        )
        self.assertEqual(
            expired_terminal_proof["status"],
            "VERIFIED_CLEAN",
            expired_terminal_proof["issues"],
        )
        replacement_authority = {
            **read_authority,
            "authorization_id": "AWS-READ-AUTH-0002",
            "receipt_digest": "sha256:" + "c" * 64,
            "authority_source": "owner-message-read-2",
            "authorized_at": "2027-01-03T00:00:30Z",
        }
        replaced_terminal_proof = derive(verified_document, replacement_authority)
        self.assertEqual(
            replaced_terminal_proof["status"],
            "VERIFIED_CLEAN",
            replaced_terminal_proof["issues"],
        )

        fresh_review_after_closed_attempt = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0064",
                    observed_at="2027-01-03T00:00:04Z",
                ),
                evidence_row(
                    "AWS-40",
                    "VERIFIED_CLEAN",
                    evidence_id="EV-0065",
                    observed_at="2027-01-03T00:00:05Z",
                    teardown_authorization="TEARDOWN-AUTH-0001",
                    teardown_receipt_digest=receipt_digest,
                ),
                evidence_row(
                    "AWS-40",
                    "RUNNING",
                    evidence_id="EV-0066",
                    observed_at="2027-01-03T00:00:06Z",
                ),
            )
        )
        self.assertEqual(
            fresh_review_after_closed_attempt["status"],
            "RUNNING",
            fresh_review_after_closed_attempt["issues"],
        )
        self.assertEqual(fresh_review_after_closed_attempt["evidence_id"], "EV-0066")

        invalid_cases = (
            (
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0070",
                    observed_at="2027-01-04T00:00:00Z",
                    teardown_authorization="TEARDOWN-AUTH-9999",
                ),
                "exact teardown receipt",
            ),
            (
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0071",
                    observed_at="2027-01-04T00:00:01Z",
                    teardown_receipt_digest="sha256:" + "f" * 64,
                ),
                "exact teardown receipt",
            ),
            (
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0072",
                    observed_at="2027-01-04T00:00:02Z",
                    terminal_status="NONE",
                ),
                "Stack events and terminal status",
            ),
            (
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0073",
                    observed_at="2027-01-04T00:00:03Z",
                    residual_resources="fastlane-stack",
                ),
                "cannot retain residuals",
            ),
            (
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0074",
                    observed_at="2027-01-04T00:00:04Z",
                    resources_removed="NONE",
                ),
                "must reconcile every removal",
            ),
        )
        for invalid_row, expected_issue in invalid_cases:
            with self.subTest(expected_issue=expected_issue):
                invalid = derive(document(ready_row, invalid_row))
                self.assertEqual(invalid["status"], "BLOCKED")
                self.assertTrue(
                    any(expected_issue in issue for issue in invalid["issues"]),
                    invalid["issues"],
                )

        malformed_id = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-BAD",
                    observed_at="2027-01-04T00:00:05Z",
                ),
            )
        )
        self.assertEqual(malformed_id["status"], "BLOCKED")
        self.assertTrue(
            any("noncanonical" in issue for issue in malformed_id["issues"])
        )
        partial_placeholder = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="TODO",
                    observed_at="2027-01-04T00:00:06Z",
                ),
            )
        )
        self.assertEqual(partial_placeholder["status"], "BLOCKED")
        wrong_read_authority = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0075",
                    observed_at="2027-01-04T00:00:07Z",
                    read_authorization="AWS-READ-AUTH-9999",
                ),
            )
        )
        self.assertEqual(wrong_read_authority["status"], "BLOCKED")
        self.assertTrue(
            any(
                "READY_FOR_TEARDOWN" in issue
                for issue in wrong_read_authority["issues"]
            )
        )
        missing_blocker = derive(
            document(
                evidence_row(
                    "AWS-40",
                    "BLOCKED",
                    evidence_id="EV-0076",
                    observed_at="2027-01-04T00:00:08Z",
                    blocker_or_stale_reason="NONE",
                )
            )
        )
        self.assertEqual(missing_blocker["status"], "BLOCKED")
        self.assertTrue(
            any("exact blocker" in issue for issue in missing_blocker["issues"])
        )
        replayed_action = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "PARTIAL",
                    evidence_id="EV-0077",
                    observed_at="2027-01-04T00:00:09Z",
                ),
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0078",
                    observed_at="2027-01-04T00:00:10Z",
                ),
            )
        )
        self.assertEqual(replayed_action["status"], "BLOCKED")
        self.assertTrue(
            any(
                "requires exactly one first AWS-50 STARTED row" in issue
                for issue in replayed_action["issues"]
            )
        )
        different_authority_retry = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "FAILED",
                    evidence_id="EV-0079",
                    observed_at="2027-01-04T00:00:10Z",
                    teardown_authorization="TEARDOWN-AUTH-9999",
                    teardown_receipt_digest="sha256:" + "f" * 64,
                ),
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0088",
                    observed_at="2027-01-04T00:00:11Z",
                ),
            )
        )
        self.assertEqual(different_authority_retry["status"], "BLOCKED")
        self.assertTrue(
            any(
                "requires exactly one first AWS-50 STARTED row" in issue
                for issue in different_authority_retry["issues"]
            )
        )

        premature_binding = derive(
            document(
                evidence_row(
                    "AWS-40",
                    "READY_FOR_TEARDOWN",
                    evidence_id="EV-0080",
                    teardown_authorization="TEARDOWN-AUTH-0001",
                    teardown_receipt_digest=receipt_digest,
                )
            )
        )
        self.assertEqual(premature_binding["status"], "BLOCKED")
        orphan_terminal = derive(
            document(
                evidence_row(
                    "AWS-40",
                    "VERIFIED_CLEAN",
                    evidence_id="EV-0081",
                    teardown_authorization="TEARDOWN-AUTH-0001",
                    teardown_receipt_digest=receipt_digest,
                )
            )
        )
        self.assertEqual(orphan_terminal["status"], "BLOCKED")

        residual_only_clean = derive(
            document(
                evidence_row(
                    "AWS-40",
                    "VERIFIED_CLEAN",
                    evidence_id="EV-0085",
                    observed_at="2027-01-05T00:00:01Z",
                )
            )
        )
        self.assertEqual(residual_only_clean["status"], "VERIFIED_CLEAN")
        self.assertFalse(residual_only_clean["post_action_bound"])
        self.assertEqual(
            doctor.derive_teardown_route("TEARDOWN", residual_only_clean),
            ("AWS_RESIDUAL_REVIEW_COMPLETE", "STOP"),
        )

        erased_binding = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0086",
                    observed_at="2027-01-05T00:00:02Z",
                ),
                evidence_row(
                    "AWS-40",
                    "VERIFIED_CLEAN",
                    evidence_id="EV-0087",
                    observed_at="2027-01-05T00:00:03Z",
                ),
            )
        )
        self.assertEqual(erased_binding["status"], "BLOCKED")
        self.assertTrue(
            any("cannot erase" in issue for issue in erased_binding["issues"])
        )

        partial_pairs = (
            ("TEARDOWN-AUTH-0001", "NONE"),
            ("NONE", receipt_digest),
            ("NOT-CANONICAL", receipt_digest),
            ("TEARDOWN-AUTH-0001", "sha256:not-a-digest"),
        )
        for index, (authorization_id, digest_value) in enumerate(partial_pairs):
            with self.subTest(
                authorization_id=authorization_id, digest_value=digest_value
            ):
                malformed = derive(
                    document(
                        evidence_row(
                            "AWS-40",
                            "VERIFIED_CLEAN",
                            evidence_id=f"EV-{8090 + index}",
                            observed_at=f"2027-01-05T00:01:0{index}Z",
                            teardown_authorization=authorization_id,
                            teardown_receipt_digest=digest_value,
                        )
                    )
                )
                self.assertEqual(malformed["status"], "BLOCKED")

        replayed_attempt = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0094",
                    observed_at="2027-01-05T00:02:00Z",
                ),
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0095",
                    observed_at="2027-01-05T00:02:01Z",
                ),
                evidence_row(
                    "AWS-40",
                    "VERIFIED_CLEAN",
                    evidence_id="EV-0096",
                    observed_at="2027-01-05T00:02:02Z",
                    teardown_authorization="TEARDOWN-AUTH-0001",
                    teardown_receipt_digest=receipt_digest,
                ),
            )
        )
        self.assertEqual(replayed_attempt["status"], "BLOCKED")
        self.assertTrue(
            any(
                "requires exactly one first AWS-50 STARTED row" in issue
                or "more than one AWS-50 terminal row" in issue
                for issue in replayed_attempt["issues"]
            )
        )

        duplicate_id = derive(
            document(
                evidence_row("AWS-40", "RUNNING"),
                evidence_row(
                    "AWS-40",
                    "READY_FOR_TEARDOWN",
                    observed_at="2027-01-02T00:00:00Z",
                ),
            )
        )
        self.assertEqual(duplicate_id["status"], "BLOCKED")
        self.assertTrue(
            any("duplicate IDs" in issue for issue in duplicate_id["issues"])
        )
        duplicate_timestamp = derive(
            document(
                evidence_row("AWS-40", "RUNNING", evidence_id="EV-0082"),
                evidence_row(
                    "AWS-40",
                    "READY_FOR_TEARDOWN",
                    evidence_id="EV-0083",
                ),
            )
        )
        self.assertEqual(duplicate_timestamp["status"], "BLOCKED")
        self.assertTrue(
            any(
                "timestamps must be unique" in issue
                for issue in duplicate_timestamp["issues"]
            )
        )
        duplicate_provenance = derive(
            document(
                ready_row,
                evidence_row(
                    "AWS-50",
                    "SUCCEEDED",
                    evidence_id="EV-0084",
                    observed_at="2027-01-05T00:00:00Z",
                ),
                duplicate_provenance=True,
            )
        )
        self.assertEqual(duplicate_provenance["status"], "BLOCKED")
        self.assertTrue(
            any(
                "one exact owner-authored teardown receipt" in issue
                for issue in duplicate_provenance["issues"]
            )
        )

        pending = {"status": "PENDING", "value": "NONE"}
        retain = {"status": "CURRENT", "value": "RETAIN"}
        investigate = {"status": "CURRENT", "value": "INVESTIGATE"}
        remove = {"status": "CURRENT", "value": "REMOVE"}
        route_cases = (
            (
                "RESIDUAL_REVIEW",
                ready,
                pending,
                ("AWS_RESIDUALS_REMAIN", "STOP"),
            ),
            (
                "RESIDUAL_REVIEW",
                verified,
                None,
                ("AWS_RESIDUAL_REVIEW_COMPLETE", "STOP"),
            ),
            (
                "RESIDUAL_REVIEW",
                residuals,
                pending,
                ("AWS_RESIDUALS_REMAIN", "STOP"),
            ),
            (
                "RESIDUAL_REVIEW",
                blocked,
                None,
                ("AWS_RESIDUAL_REVIEW_BLOCKED", "STOP"),
            ),
            (
                "TEARDOWN",
                ready,
                remove,
                ("WAITING_AWS_TEARDOWN_AUTH", "AWS-50"),
            ),
            (
                "TEARDOWN",
                verified,
                None,
                ("AWS_TEARDOWN_COMPLETE", "STOP"),
            ),
            (
                "TEARDOWN",
                residuals,
                pending,
                ("AWS_RESIDUALS_REMAIN", "STOP"),
            ),
            (
                "TEARDOWN",
                blocked,
                None,
                ("AWS_RESIDUAL_REVIEW_BLOCKED", "STOP"),
            ),
            (
                "TEARDOWN",
                action_results["SUCCEEDED"],
                None,
                ("AWS_RESIDUAL_REVIEW", "AWS-40"),
            ),
            (
                "TEARDOWN",
                running,
                None,
                ("AWS_RESIDUAL_REVIEW", "AWS-40"),
            ),
            (
                "RETAIN",
                residuals,
                retain,
                ("AWS_RESIDUALS_RETAINED", "STOP"),
            ),
            (
                "RESIDUAL_REVIEW",
                residuals,
                investigate,
                ("AWS_RESIDUAL_REVIEW", "AWS-40"),
            ),
            (
                "TEARDOWN",
                residuals,
                remove,
                ("AWS_RESIDUAL_REVIEW", "AWS-40"),
            ),
        )
        for intent, sequence, disposition, expected_route in route_cases:
            with self.subTest(intent=intent, status=sequence["status"]):
                self.assertEqual(
                    doctor.derive_teardown_route(intent, sequence, disposition),
                    expected_route,
                )
        self.assertEqual(
            doctor.derive_teardown_route("NONE", ready),
            ("AWS_RESIDUALS_REMAIN", "STOP"),
        )
        self.assertIsNone(
            doctor.derive_teardown_route("NONE", {"status": "NOT_ACTIVE"})
        )

        fresh_record = {
            "value": "RETAIN",
            "recorded_at": "2098-01-01T00:00:00Z",
            "provenance_status": "CURRENT",
        }
        retained = doctor.derive_aws_residual_disposition(fresh_record, residuals)
        self.assertEqual(retained["status"], "CURRENT")
        self.assertEqual(retained["value"], "RETAIN")
        self.assertFalse(retained["authorizes_aws_access"])
        self.assertFalse(retained["authorizes_mutation"])
        stale = doctor.derive_aws_residual_disposition(
            {
                "value": "TEARDOWN",
                "recorded_at": "2020-01-01T00:00:00Z",
                "provenance_status": "CURRENT",
            },
            residuals,
        )
        self.assertEqual(stale["status"], "PENDING")
        prior_remove = doctor.derive_aws_residual_disposition(
            {
                "value": "TEARDOWN",
                "recorded_at": "2020-01-01T00:00:00Z",
                "provenance_status": "CURRENT",
            },
            ready,
        )
        self.assertEqual(prior_remove["status"], "CURRENT")
        self.assertEqual(prior_remove["value"], "REMOVE")
        invalid_retain = doctor.derive_aws_residual_disposition(
            fresh_record,
            {"status": "NOT_ACTIVE"},
        )
        self.assertEqual(invalid_retain["status"], "INVALID")
        specialized = doctor.derive_interaction(
            "AWS_RESIDUAL_REVIEW_BLOCKED",
            "STOP",
            has_errors=True,
            diagnostic_codes=["AWS_TEARDOWN_EVIDENCE_INVALID"],
            design_aws_core_ready=True,
            aws_execution_planning_ready=True,
            remediation={
                "next_action": {
                    "action_kind": "FIX_VALIDATION_FAILURE",
                }
            },
        )
        self.assertEqual(
            specialized["owner_action_kind"],
            "REVIEW_SAFETY_BLOCKER",
        )
        self.assertEqual(
            specialized["route_reason_code"], "AWS_RESIDUAL_REVIEW_BLOCKED"
        )
        teardown_context = doctor.Context(PROJECT_ROOT)
        teardown_context.error(
            "AWS_TEARDOWN_EVIDENCE_INVALID",
            "residual review blocked",
            doctor.VERIFY_FILE,
        )
        self.assertTrue(
            doctor._preserve_specialized_teardown_block(
                teardown_context, "AWS_RESIDUAL_REVIEW_BLOCKED"
            )
        )
        teardown_context.error("UNRELATED_VALIDATION", "separate error")
        self.assertFalse(
            doctor._preserve_specialized_teardown_block(
                teardown_context, "AWS_RESIDUAL_REVIEW_BLOCKED"
            )
        )

        self.assertTrue(
            doctor.aws_deployment_teardown_sequence_conflict(
                {"status": "ACTION_TERMINAL_REQUIRED"},
                {"status": "READY_FOR_TEARDOWN"},
            )
        )
        self.assertFalse(
            doctor.aws_deployment_teardown_sequence_conflict(
                {"status": "CONSUMED"},
                {"status": "READY_FOR_TEARDOWN"},
            )
        )
        self.assertFalse(
            doctor.aws_deployment_teardown_sequence_conflict(
                {"status": "RECONCILED"},
                {"status": "VERIFIED_CLEAN"},
            )
        )

    def test_action_receipts_are_phase_isolated(self) -> None:
        context = doctor.Context(PROJECT_ROOT)
        context.texts[doctor.VERIFY_FILE] = "verification"
        calls: list[str] = []
        original = doctor._receipt_external_authority

        def fake_receipt(
            _text: str, action: str, _authorization: str, **_kwargs: object
        ) -> dict[str, object]:
            calls.append(action)
            return {"kind": f"AWS_{action.upper()}", "validity": "CURRENT"}

        doctor._receipt_external_authority = fake_receipt
        try:
            teardown = doctor.derive_external_authority(
                context,
                {"AWS boundary": "MUTATE_LISTED_RESOURCES"},
                "explicit-gate",
                "AUTH-0001",
                aws_action_phase="AWS-50",
                teardown_review={"status": "READY_FOR_TEARDOWN"},
            )
            self.assertEqual(calls, ["Teardown"])
            calls.clear()
            deployment = doctor.derive_external_authority(
                context,
                {"AWS boundary": "MUTATE_LISTED_RESOURCES"},
                "explicit-gate",
                "AUTH-0001",
                aws_action_phase="AWS-20",
                aws_progress_state="WAITING_AWS_MUTATION_AUTH",
                preflight={
                    "status": "READY",
                    "preflight_id": "AWS-PREFLIGHT-0001",
                    "account_access": "READ_ONLY_OBSERVED",
                },
            )
            self.assertEqual(calls, ["Deployment"])
        finally:
            doctor._receipt_external_authority = original
        self.assertEqual(teardown["kind"], "AWS_TEARDOWN")
        self.assertEqual(deployment["kind"], "AWS_DEPLOYMENT")

    def test_fast_dev_mutation_requires_observed_preflight_and_exact_receipt(
        self,
    ) -> None:
        artifact = "sha256:" + "a" * 64
        envelope = aws_authority_envelope(
            role="deploy-role",
            account="111122223333",
            region="us-west-2",
            environment="development",
            resources=["fastlane-stack"],
            operations=["cloudformation:ExecuteChangeSet"],
            artifact=artifact,
            rollback="rollback fastlane-stack",
        )
        context = doctor.Context(PROJECT_ROOT)
        context.texts[doctor.VERIFY_FILE] = "verification"
        common = {
            "cost_posture": "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            "aws_progress_state": "WAITING_AWS_MUTATION_AUTH",
            "active_artifact": artifact,
        }
        self.assertEqual(
            doctor.derive_external_authority(
                context, envelope, "fast-dev", "AUTH-0001", **common
            )["kind"],
            "NONE",
        )
        self.assertEqual(
            doctor.derive_external_authority(
                context,
                envelope,
                "fast-dev",
                "AUTH-0001",
                aws_action_phase="AWS-20",
                **common,
            )["kind"],
            "NONE",
        )
        required = doctor.derive_external_authority(
            context,
            envelope,
            "fast-dev",
            "AUTH-0001",
            aws_action_phase="AWS-20",
            preflight=ready_preflight(
                account="111122223333",
                region="us-west-2",
                environment="development",
            ),
            **common,
        )
        self.assertEqual(required["kind"], "AWS_ACTION_RECEIPT_REQUIRED")
        self.assertEqual(required["validity"], "REQUIRED")


if __name__ == "__main__":
    unittest.main()
