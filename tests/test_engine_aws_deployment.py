from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tests import test_bootstrap_doctor as support
from tests.test_bootstrap_doctor import (
    PROJECT_ROOT,
    aws_authority_envelope,
    doctor,
    rebind_gate_b_envelope,
    refresh_control_hashes,
    replace_contract_table,
    set_receipt,
    set_table_value,
)


class AwsDeploymentReconciliationRegressionTests(unittest.TestCase):
    _DEPLOYMENT_ARTIFACT = "sha256:" + "a" * 64
    _DEPLOYMENT_PLAN = (
        "TYPE: CLOUDFORMATION_CHANGE_SET; IDENTIFIER: canary-change-set; "
        "DIGEST: sha256:" + "b" * 64
    )
    _DEPLOYMENT_OPERATIONS = (
        "cloudformation:CreateChangeSet",
        "cloudformation:ExecuteChangeSet",
    )
    _VERIFICATION_MATRIX_HEADERS = (
        "Evidence ID",
        "PRD / property IDs",
        "Task IDs",
        "Requirement or invariant",
        "Automated evidence",
        "AWS/manual evidence",
        "Artifact/environment",
        "Status",
    )

    def deployment_envelope(self) -> dict[str, str]:
        return aws_authority_envelope(
            role="fastlane-deployment-role",
            account="111122223333",
            region="us-west-2",
            environment="development",
            resources=["fastlane-stack"],
            operations=list(self._DEPLOYMENT_OPERATIONS),
            artifact=self._DEPLOYMENT_ARTIFACT,
            rollback="rollback fastlane-stack",
        )

    def deployment_read_authority(self) -> dict[str, object]:
        return {
            "kind": "AWS_READ_ONLY",
            "validity": "CURRENT",
            "authorization_id": "AWS-READ-AUTH-0001",
            "receipt_digest": "sha256:" + "c" * 64,
            "account": "111122223333",
            "region": "us-west-2",
            "environment": "development",
            "role_or_profile": "fastlane-read-role",
            "resources": ["fastlane-stack"],
            "operations": ["cloudformation:DescribeStacks"],
            "artifact_plan_binding": {
                "artifact": self._DEPLOYMENT_ARTIFACT,
                "plan": "NONE",
            },
            "cost_ceiling": "USD: 20.00",
            "rollback_boundary": "NONE",
            "expiration": "2099-01-01T00:00:00Z",
            "authorized_at": "2026-12-31T23:59:59Z",
            "authority_source": "owner-message MSG-AWS-READ-0001",
        }

    def bind_explicit_deployment_receipt(
        self,
        verify_text: str,
        *,
        authorization_id: str = "AWS-AUTH-0001",
        valid_until: str = "2099-01-01T00:00:00Z",
        authorized_at: str = "2027-01-01T00:00:00Z",
    ) -> tuple[str, str]:
        receipt = "\n".join(
            [
                "AUTHORIZE AWS DEPLOYMENT",
                f"AWS authorization: {authorization_id}",
                "Construction authorization: AUTH-0001",
                "Profile or role: fastlane-deployment-role",
                "Account: 111122223333",
                "Region: us-west-2",
                "Environment: development",
                f"Artifact digest: {self._DEPLOYMENT_ARTIFACT}",
                f"IaC plan/change-set binding: {self._DEPLOYMENT_PLAN}",
                "Stack, application, and resources: fastlane-stack",
                "Allowed operations: " + ", ".join(self._DEPLOYMENT_OPERATIONS),
                "Cost ceiling: USD: 20.00",
                "Rollback boundary: rollback fastlane-stack",
                f"Valid until: {valid_until}",
                "Approver: alice",
            ]
        )
        digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        verify_text = set_receipt(verify_text, "aws-deployment", receipt)
        lines = verify_text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if line.startswith("| Deployment | TODO |"):
                suffix = "\n" if line.endswith("\n") else ""
                lines[index] = (
                    f"| Deployment | {authorization_id} | AUTH-0001 | "
                    f"fastlane-deployment-role | {self._DEPLOYMENT_ARTIFACT} | "
                    f"{self._DEPLOYMENT_PLAN} | ACCOUNT: 111122223333; "
                    "REGION: us-west-2; ENVIRONMENT: development | "
                    "RESOURCES: fastlane-stack; OPERATIONS: "
                    + ", ".join(self._DEPLOYMENT_OPERATIONS)
                    + f" | COST: USD: 20.00; VALID_UNTIL: {valid_until} | "
                    "rollback fastlane-stack | owner-message MSG-AWS-0001 | "
                    f"alice | {authorized_at} | "
                    f"{digest} | AWS-PREFLIGHT-0001 | PASS | READY |{suffix}"
                )
                break
        else:
            self.fail("Deployment authorization provenance row not found")
        return "".join(lines), digest

    def bind_read_receipt(
        self,
        verify_text: str,
        *,
        construction_authorization: str = "AUTH-0001",
        authorization_id: str = "AWS-READ-AUTH-0001",
        role_or_profile: str = "fastlane-deployment-role",
        account: str = "111122223333",
        region: str = "us-west-2",
        environment: str = "development",
        resources: tuple[str, ...] = ("fastlane-stack",),
        operations: tuple[str, ...] = ("cloudformation:DescribeStacks",),
        valid_until: str = "2099-01-01T00:00:00Z",
        authorized_at: str = "2027-01-01T00:00:00Z",
        authority_source: str = "owner-message MSG-AWS-READ-0001",
    ) -> tuple[str, dict[str, object]]:
        resource_text = ", ".join(resources)
        operation_text = ", ".join(operations)
        receipt = "\n".join(
            [
                "AUTHORIZE AWS READ-ONLY PREFLIGHT",
                f"Read authorization: {authorization_id}",
                f"Construction authorization: {construction_authorization}",
                f"Profile or role: {role_or_profile}",
                f"Account: {account}",
                f"Region: {region}",
                f"Environment: {environment}",
                f"Stack, application, and resources: {resource_text}",
                f"Allowed read-only operations: {operation_text}",
                f"Artifact digest: {self._DEPLOYMENT_ARTIFACT}",
                "Prohibited operations: ALL_MUTATIONS",
                f"Valid until: {valid_until}",
                "Approver: alice",
            ]
        )
        digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        verify_text = set_receipt(verify_text, "aws-read-preflight", receipt)
        lines = verify_text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if line.startswith("| Read-only preflight | TODO |"):
                suffix = "\n" if line.endswith("\n") else ""
                lines[index] = (
                    f"| Read-only preflight | {authorization_id} | "
                    f"{construction_authorization} | {role_or_profile} | "
                    f"{self._DEPLOYMENT_ARTIFACT} | "
                    "NOT_APPLICABLE — read-only preflight creates no plan | "
                    f"ACCOUNT: {account}; REGION: {region}; "
                    f"ENVIRONMENT: {environment} | RESOURCES: {resource_text}; "
                    f"OPERATIONS: {operation_text} | COST: expected low-volume "
                    "request charges under USD 0.01; BOUNDED_BY: USD: 20.00; "
                    f"VALID_UNTIL: {valid_until} | NOT_APPLICABLE — no mutation | "
                    f"{authority_source} | alice | {authorized_at} | {digest} | "
                    f"NONE | PASS | AUTHORIZED |{suffix}"
                )
                break
        else:
            self.fail("Read-only authorization provenance row not found")
        return "".join(lines), {
            "kind": "AWS_READ_ONLY",
            "validity": "CURRENT",
            "authorization_id": authorization_id,
            "receipt_digest": digest,
            "account": account,
            "region": region,
            "environment": environment,
            "role_or_profile": role_or_profile,
            "resources": list(resources),
            "operations": list(operations),
            "artifact_plan_binding": {
                "artifact": self._DEPLOYMENT_ARTIFACT,
                "plan": "NONE",
            },
            "cost_ceiling": "EXPECTED: low-volume under USD 0.01; BOUNDED_BY: USD: 20.00",
            "rollback_boundary": "NONE",
            "expiration": valid_until,
            "authorized_at": authorized_at,
            "authority_source": authority_source,
        }

    def assert_closure_context_is_resolved(self, report: dict[str, object]) -> None:
        diagnostic_codes = {
            str(item["code"])
            for item in report["diagnostics"]
            if isinstance(item, dict) and "code" in item
        }
        self.assertNotIn("CONTEXT_SOURCE_INVALID", diagnostic_codes, report)
        plan = report["context_plan"]
        self.assertIn(
            plan["budget_status"],
            {"WITHIN_LIMIT", "OVERSIZED_REQUIRED_RECORD"},
            plan,
        )
        if plan["budget_status"] == "OVERSIZED_REQUIRED_RECORD":
            self.assertEqual(len(plan["overflow_records"]), 1, plan)
        else:
            self.assertLessEqual(
                plan["actual_initial_source_bytes"],
                plan["maximum_initial_source_bytes"],
                plan,
            )

    def assert_no_external_mutation_authority(self, report: dict[str, object]) -> None:
        forbidden_kinds = {"AWS_DEPLOYMENT", "AWS_TEARDOWN", "FAST_DEV_GATE_B"}
        external = report["external_authority"]
        self.assertNotIn(external["kind"], forbidden_kinds, external)
        self.assertNotIn(
            external["request_match"]["authority_kind"],
            forbidden_kinds,
            external["request_match"],
        )
        self.assertEqual(
            report["deployment_journal_closure_authority"]["aws_mutation_authority"],
            "NONE",
        )

    def assert_exact_closure_authority(
        self,
        report: dict[str, object],
        *,
        sections: list[str],
        operations: list[str],
        release_states: list[str] | None = None,
    ) -> None:
        closure = report["deployment_journal_closure_authority"]
        self.assertEqual(
            {
                "valid": closure["valid"],
                "kind": closure["kind"],
                "authorization_id": closure["authorization_id"],
                "mode": closure["mode"],
                "allowed_write_paths": closure["allowed_write_paths"],
                "allowed_sections": closure["allowed_sections"],
                "allowed_operations": closure["allowed_operations"],
                "allowed_release_states": closure["allowed_release_states"],
                "construction_authorization": closure["construction_authorization"],
                "aws_mutation_authority": closure["aws_mutation_authority"],
            },
            {
                "valid": True,
                "kind": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
                "authorization_id": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
                "mode": "BOUNDED_EVIDENCE_CLOSURE",
                "allowed_write_paths": [doctor.VERIFY_FILE],
                "allowed_sections": sections,
                "allowed_operations": operations,
                "allowed_release_states": release_states or [],
                "construction_authorization": "NONE",
                "aws_mutation_authority": "NONE",
            },
            closure,
        )

    def assert_no_closure_authority(self, report: dict[str, object]) -> None:
        closure = report["deployment_journal_closure_authority"]
        self.assertFalse(closure["valid"], closure)
        self.assertEqual(closure["kind"], "NONE", closure)
        self.assertEqual(closure["allowed_write_paths"], [], closure)
        self.assertEqual(closure["allowed_sections"], [], closure)
        self.assertEqual(closure["allowed_operations"], [], closure)
        self.assertEqual(closure["allowed_release_states"], [], closure)
        self.assertEqual(closure["construction_authorization"], "NONE", closure)
        self.assertEqual(closure["aws_mutation_authority"], "NONE", closure)

    def deployment_row(
        self,
        *,
        evidence_id: str,
        attempt_id: str = "AWS-DEPLOY-0001",
        phase: str,
        status: str,
        observed_at: str,
        lane: str = "fast-dev",
        basis: str = "REQ-0001 / DES-0001 / AUTH-0001",
        read_authority: dict[str, object] | None = None,
        receipt_digest: str = "NONE",
        deployment_authorization: str | None = None,
        deployment_valid_until: str | None = None,
        deployment_authority_source: str | None = None,
        artifact: str | None = None,
        plan_binding: str | None = None,
        account_scope: str | None = None,
        deployment_role: str = "fastlane-deployment-role",
        identity_and_boundary_match: str = "PASS",
        operation_result: str | None = None,
        acceptance_evidence_ids: str | None = None,
    ) -> tuple[str, ...]:
        is_read = phase == "AWS-30"
        blocked = status in {"BLOCKED", "STALE"}
        receipt_backed = receipt_digest != "NONE"
        authorization = deployment_authorization or (
            "AWS-AUTH-0001" if receipt_backed else "AUTH-0001"
        )
        plan = self._DEPLOYMENT_PLAN if receipt_backed else "STACK: fastlane-stack"
        read = read_authority or self.deployment_read_authority()
        values = {
            "Evidence ID": evidence_id,
            "Attempt ID": attempt_id,
            "Phase": phase,
            "REQ / DES / AUTH": basis,
            "Deployment authorization": authorization,
            "Deployment receipt digest": receipt_digest,
            "Deployment valid until": deployment_valid_until
            or ("2099-01-01T00:00:00Z" if receipt_backed else "2099-12-31T23:59:59Z"),
            "Deployment authority source": deployment_authority_source
            or (
                "owner-message MSG-AWS-0001"
                if receipt_backed
                else "owner-message MSG-GATE-B-0001"
            ),
            "Read authorization": (
                str(read["authorization_id"]) if is_read else "NONE"
            ),
            "Deployment role or profile": deployment_role,
            "Read role or profile": (
                str(read["role_or_profile"]) if is_read else "NONE"
            ),
            "Read receipt digest": (str(read["receipt_digest"]) if is_read else "NONE"),
            "Read valid until": (str(read["expiration"]) if is_read else "NONE"),
            "Read authority source": (
                doctor._format_deployment_read_provenance(
                    str(read["authority_source"]),
                    str(read["authorized_at"]),
                    read["resources"],
                    read["operations"],
                )
                if is_read
                else "NONE"
            ),
            "Artifact digest": artifact or self._DEPLOYMENT_ARTIFACT,
            "Plan/change-set binding": plan_binding or plan,
            "Resources": "fastlane-stack",
            "Mutation operations": ", ".join(self._DEPLOYMENT_OPERATIONS),
            "Read operations observed": (
                "cloudformation:DescribeStacks" if is_read else "NONE"
            ),
            "Account / Region / environment": account_scope
            or ("ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development"),
            "Operation identifiers and direct result": operation_result
            or (
                doctor.AWS_DEPLOYMENT_PRECALL_RESULT
                if status == "STARTED"
                else f"IDENTIFIERS: request-{evidence_id.lower()}; RESULT: terminal action evidence recorded"
            ),
            "Rollback result": "NONE",
            "Acceptance evidence IDs": (
                acceptance_evidence_ids
                if acceptance_evidence_ids is not None
                else "EV-9001"
                if status == "COMPLETE"
                else "NONE"
            ),
            "Observed at": observed_at,
            "Durable source": f"logs/{evidence_id.lower()}.json",
            "Identity and boundary match": identity_and_boundary_match,
            "Blocker or stale reason": (
                f"deployment reconciliation reported {status.lower()}"
                if blocked
                else "NONE"
            ),
            "Status": status,
        }
        return tuple(
            values[header] for header in doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS
        )

    def deployment_verify_text(
        self,
        rows: list[tuple[str, ...]],
        *,
        lane: str,
        verification_rows: list[tuple[str, ...]] | None = None,
        explicit_authorization_id: str = "AWS-AUTH-0001",
    ) -> tuple[str, str]:
        verify_text = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        if verification_rows is None:
            verification_rows = [
                (
                    "EV-9001",
                    "FR-001",
                    "TASK-001",
                    "FR-001 primary outcome passes after deployment",
                    "EV-0001 local suite passed",
                    "DescribeStacks returned UPDATE_COMPLETE",
                    f"ARTIFACT: {self._DEPLOYMENT_ARTIFACT}; "
                    "ACCOUNT: 111122223333; REGION: us-west-2; "
                    "ENVIRONMENT: development",
                    "VERIFIED",
                )
            ]
        verify_text = replace_contract_table(
            verify_text,
            "## Verification matrix",
            self._VERIFICATION_MATRIX_HEADERS,
            verification_rows,
        )
        receipt_digest = "NONE"
        if lane in {"fast-dev", "explicit-gate"}:
            verify_text, receipt_digest = self.bind_explicit_deployment_receipt(
                verify_text, authorization_id=explicit_authorization_id
            )
        if doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING in verify_text:
            verify_text = replace_contract_table(
                verify_text,
                doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
                doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS,
                rows,
            )
        else:
            verify_text += "\n" + "\n".join(
                [
                    doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
                    "",
                    "| " + " | ".join(doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS) + " |",
                    "|"
                    + "|".join("---" for _ in doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS)
                    + "|",
                    *("| " + " | ".join(row) + " |" for row in rows),
                    "",
                ]
            )
        return verify_text, receipt_digest

    def derive_deployment(
        self,
        rows: list[tuple[str, ...]],
        *,
        lane: str = "fast-dev",
        read_authority: dict[str, object] | None = None,
        verification_rows: list[tuple[str, ...]] | None = None,
        release_evidence_cutoff: str = "NONE",
        release_state: str = "READY_TO_DEPLOY",
        construction_authorization: str = "AUTH-0001",
        gate_b_authorized_at: str = "2026-12-31T23:59:59Z",
        explicit_authorization_id: str = "AWS-AUTH-0001",
        envelope: dict[str, str] | None = None,
    ) -> dict[str, object]:
        verify_text, _digest = self.deployment_verify_text(
            rows,
            lane=lane,
            verification_rows=verification_rows,
            explicit_authorization_id=explicit_authorization_id,
        )
        return doctor.derive_deployment_sequence_state(
            verify_text,
            read_authority,
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            construction_authorization=construction_authorization,
            envelope=envelope or self.deployment_envelope(),
            lane=lane,
            artifact_binding=self._DEPLOYMENT_ARTIFACT,
            release_evidence_cutoff=release_evidence_cutoff,
            release_state=release_state,
            gate_b_authority_source="owner-message MSG-GATE-B-0001",
            gate_b_authorized_at=gate_b_authorized_at,
        )

    def test_started_only_requires_automatic_terminal_record_before_aws30(self) -> None:
        started = self.deployment_row(
            evidence_id="EV-2000",
            phase="AWS-20",
            status="STARTED",
            observed_at="2027-01-01T00:00:00Z",
        )
        result = self.derive_deployment([started])
        self.assertEqual(result["status"], "ACTION_TERMINAL_REQUIRED", result)
        self.assertEqual(result["action_status"], "STARTED")
        self.assertEqual(
            doctor.derive_aws_delivery_route(
                "READY_TO_DEPLOY",
                {"progress_state": "AWS_PREFLIGHT_READY"},
                result,
                "fast-dev",
            ),
            ("AWS_DEPLOYMENT_ACTION_TERMINAL", "AWS-20"),
        )
        interaction = doctor.derive_interaction(
            "AWS_DEPLOYMENT_ACTION_TERMINAL",
            "AWS-20",
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=True,
            aws_execution_planning_ready=True,
            aws_lane="fast-dev",
            aws_read_authority_required=False,
        )
        self.assertEqual(
            interaction["owner_action_kind"], "NONE_CONTINUE_AUTOMATICALLY"
        )
        self.assertFalse(interaction["owner_action_required"])
        self.assertTrue(interaction["automatic_continuation_allowed"])
        self.assertFalse(interaction["formal_receipt_required"])

    def test_complete_reconciliation_acceptance_ids_bind_verified_exact_target(
        self,
    ) -> None:
        read = self.deployment_read_authority()
        action_rows = [
            self.deployment_row(
                evidence_id="EV-2301",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2302",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:01:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2303",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-01T00:02:00Z",
                read_authority=read,
            ),
        ]

        def matrix_row(
            evidence_id: str = "EV-9001",
            *,
            status: str = "VERIFIED",
            artifact: str | None = None,
        ) -> tuple[str, ...]:
            return (
                evidence_id,
                "FR-001",
                "TASK-001",
                "FR-001 primary outcome passes after deployment",
                "EV-0001 local suite passed",
                "DescribeStacks returned UPDATE_COMPLETE",
                f"ARTIFACT: {artifact or self._DEPLOYMENT_ARTIFACT}; "
                "ACCOUNT: 111122223333; REGION: us-west-2; "
                "ENVIRONMENT: development",
                status,
            )

        cases = {
            "nonexistent": ([matrix_row("EV-9002")], ("EV-9001", "exactly once")),
            "failed": ([matrix_row(status="FAILED")], ("EV-9001", "VERIFIED")),
            "stale": ([matrix_row(status="STALE")], ("EV-9001", "VERIFIED")),
            "wrong artifact": (
                [matrix_row(artifact="sha256:" + "f" * 64)],
                ("EV-9001", "artifact/account/Region/environment"),
            ),
        }
        for label, (verification_rows, expected_tokens) in cases.items():
            with self.subTest(label=label):
                result = self.derive_deployment(
                    action_rows,
                    read_authority=read,
                    verification_rows=verification_rows,
                )
                self.assertEqual(result["status"], "BLOCKED", result)
                joined = " ".join(str(issue) for issue in result["issues"])
                for token in expected_tokens:
                    self.assertIn(token.casefold(), joined.casefold(), result)

    def test_malformed_historical_group_cannot_hide_behind_valid_current_attempt(
        self,
    ) -> None:
        read = self.deployment_read_authority()
        old_basis = "REQ-0000 / DES-0000 / AUTH-0000"
        invalid_artifact = "artifact-without-sha256"
        rows = [
            self.deployment_row(
                evidence_id="EV-2311",
                attempt_id="AWS-DEPLOY-0001",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
                basis=old_basis,
                deployment_authorization="AUTH-0000",
                artifact=invalid_artifact,
            ),
            self.deployment_row(
                evidence_id="EV-2312",
                attempt_id="AWS-DEPLOY-0001",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:01:00Z",
                basis=old_basis,
                deployment_authorization="AUTH-0000",
                artifact=invalid_artifact,
            ),
            self.deployment_row(
                evidence_id="EV-2313",
                attempt_id="AWS-DEPLOY-0001",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-01T00:02:00Z",
                basis=old_basis,
                deployment_authorization="AUTH-0000",
                artifact=invalid_artifact,
                read_authority=read,
            ),
            self.deployment_row(
                evidence_id="EV-2314",
                attempt_id="AWS-DEPLOY-0002",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:03:00Z",
            ),
        ]
        result = self.derive_deployment(
            rows,
            read_authority=read,
            release_evidence_cutoff="EV-2313",
        )
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(
            any(
                "historical" in issue.casefold() and "artifact" in issue.casefold()
                for issue in result["issues"]
            ),
            result,
        )

    def test_non_started_rows_require_exact_identifiers_result_grammar(self) -> None:
        rows = [
            self.deployment_row(
                evidence_id="EV-2321",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2322",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:01:00Z",
                operation_result="request-123 succeeded",
            ),
        ]
        result = self.derive_deployment(rows)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(
            any(
                "IDENTIFIERS" in issue and "RESULT" in issue
                for issue in result["issues"]
            ),
            result,
        )

    def test_deployment_journal_schema_is_exact_and_complete(self) -> None:
        expected = (
            "Evidence ID",
            "Attempt ID",
            "Phase",
            "REQ / DES / AUTH",
            "Deployment authorization",
            "Deployment receipt digest",
            "Deployment valid until",
            "Deployment authority source",
            "Read authorization",
            "Deployment role or profile",
            "Read role or profile",
            "Read receipt digest",
            "Read valid until",
            "Read authority source",
            "Artifact digest",
            "Plan/change-set binding",
            "Resources",
            "Mutation operations",
            "Read operations observed",
            "Account / Region / environment",
            "Operation identifiers and direct result",
            "Rollback result",
            "Acceptance evidence IDs",
            "Observed at",
            "Durable source",
            "Identity and boundary match",
            "Blocker or stale reason",
            "Status",
        )
        self.assertEqual(doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS, expected)
        self.assertEqual(len(expected), 28)
        row = self.deployment_row(
            evidence_id="EV-2330",
            phase="AWS-20",
            status="STARTED",
            observed_at="2027-01-01T00:00:00Z",
        )
        self.assertEqual(len(row), 28)

    def test_unacknowledged_terminal_requires_current_read_receipt(self) -> None:
        current_read = self.deployment_read_authority()
        forged_read = {
            **current_read,
            "authorization_id": "AWS-READ-AUTH-0002",
            "receipt_digest": "sha256:" + "d" * 64,
            "role_or_profile": "fastlane-read-role-2",
            "authority_source": "owner-message MSG-AWS-READ-0002",
        }
        rows = [
            self.deployment_row(
                evidence_id="EV-2331",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2332",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:01:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2333",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-01T00:02:00Z",
                read_authority=forged_read,
            ),
        ]
        for label, authority in (
            ("missing", None),
            ("different canonical receipt", current_read),
        ):
            with self.subTest(label=label):
                result = self.derive_deployment(rows, read_authority=authority)
                self.assertEqual(result["status"], "BLOCKED", result)
                self.assertTrue(
                    any(
                        "read" in issue.casefold()
                        and (
                            "current" in issue.casefold()
                            or "marked" in issue.casefold()
                        )
                        for issue in result["issues"]
                    ),
                    result,
                )

        acknowledged = self.derive_deployment(
            rows,
            read_authority=current_read,
            release_state="RELEASE_VERIFIED",
            release_evidence_cutoff="EV-2333",
        )
        self.assertEqual(acknowledged["status"], "CONSUMED", acknowledged)
        self.assertTrue(acknowledged["acknowledged"])
        self.assertEqual(acknowledged["acknowledged_evidence_id"], "EV-2333")

    def test_unacknowledged_terminal_requires_current_deployment_receipt(self) -> None:
        read = self.deployment_read_authority()
        forged_digest = "sha256:" + "e" * 64
        rows = [
            self.deployment_row(
                evidence_id="EV-2341",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
                lane="explicit-gate",
                deployment_authorization="AWS-AUTH-0002",
                receipt_digest=forged_digest,
            ),
            self.deployment_row(
                evidence_id="EV-2342",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:01:00Z",
                lane="explicit-gate",
                deployment_authorization="AWS-AUTH-0002",
                receipt_digest=forged_digest,
            ),
            self.deployment_row(
                evidence_id="EV-2343",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-01T00:02:00Z",
                lane="explicit-gate",
                deployment_authorization="AWS-AUTH-0002",
                receipt_digest=forged_digest,
                read_authority=read,
            ),
        ]
        result = self.derive_deployment(rows, lane="explicit-gate", read_authority=read)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(
            any(
                "deployment" in issue.casefold()
                and ("authority" in issue.casefold() or "receipt" in issue.casefold())
                for issue in result["issues"]
            ),
            result,
        )

        acknowledged = self.derive_deployment(
            rows,
            lane="explicit-gate",
            read_authority=read,
            release_state="RELEASE_VERIFIED",
            release_evidence_cutoff="EV-2343",
        )
        self.assertEqual(acknowledged["status"], "CONSUMED", acknowledged)

    def test_release_cutoff_consumes_only_exact_terminal_aws30(self) -> None:
        read = self.deployment_read_authority()
        started = self.deployment_row(
            evidence_id="EV-2351",
            phase="AWS-20",
            status="STARTED",
            observed_at="2027-01-01T00:00:00Z",
        )
        terminal = self.deployment_row(
            evidence_id="EV-2352",
            phase="AWS-20",
            status="SUCCEEDED",
            observed_at="2027-01-01T00:01:00Z",
        )
        reconciled = self.deployment_row(
            evidence_id="EV-2353",
            phase="AWS-30",
            status="COMPLETE",
            observed_at="2027-01-01T00:02:00Z",
            read_authority=read,
        )
        rows = [started, terminal, reconciled]

        matrix_cutoff_before_ack = self.derive_deployment(
            rows,
            read_authority=read,
            release_state="READY_TO_DEPLOY",
            release_evidence_cutoff="EV-9001",
        )
        self.assertEqual(
            matrix_cutoff_before_ack["status"],
            "RECONCILED",
            matrix_cutoff_before_ack,
        )
        self.assertEqual(
            doctor.derive_aws_delivery_route(
                "READY_TO_DEPLOY",
                {"progress_state": "AWS_PREFLIGHT_READY"},
                matrix_cutoff_before_ack,
                "fast-dev",
                "EV-9001",
            ),
            ("RELEASE_REVIEW", "RELEASE-10"),
        )

        missing = self.derive_deployment(
            rows,
            read_authority=read,
            release_state="RELEASE_VERIFIED",
            release_evidence_cutoff="EV-9999",
        )
        self.assertEqual(missing["status"], "BLOCKED", missing)
        self.assertIn(
            "Active evidence cutoff must resolve exactly once",
            " ".join(missing["issues"]),
        )

        nonterminal = self.derive_deployment(
            rows,
            read_authority=read,
            release_state="RELEASE_VERIFIED",
            release_evidence_cutoff="EV-2351",
        )
        self.assertEqual(nonterminal["status"], "BLOCKED", nonterminal)
        self.assertIn("nonterminal deployment row", " ".join(nonterminal["issues"]))

        deleted_terminal = self.derive_deployment(
            [started, terminal],
            read_authority=read,
            release_state="RELEASE_VERIFIED",
            release_evidence_cutoff="EV-2353",
        )
        self.assertEqual(deleted_terminal["status"], "BLOCKED", deleted_terminal)
        self.assertIn(
            "Active evidence cutoff must resolve exactly once",
            " ".join(deleted_terminal["issues"]),
        )

        matrix_only_after_terminal = self.derive_deployment(
            rows,
            read_authority=read,
            release_state="RELEASE_VERIFIED",
            release_evidence_cutoff="EV-9001",
        )
        self.assertEqual(
            matrix_only_after_terminal["status"],
            "BLOCKED",
            matrix_only_after_terminal,
        )
        self.assertIn(
            "exact terminal AWS-30 evidence cutoff",
            " ".join(matrix_only_after_terminal["issues"]),
        )

        acknowledged = self.derive_deployment(
            rows,
            read_authority=read,
            release_state="RELEASE_VERIFIED",
            release_evidence_cutoff="EV-2353",
        )
        self.assertEqual(acknowledged["status"], "CONSUMED", acknowledged)
        self.assertEqual(acknowledged["release_evidence_cutoff"], "EV-2353")

    def test_aws30_stale_cannot_precede_the_terminal_action(self) -> None:
        old_read = self.deployment_read_authority()
        new_read = {
            **old_read,
            "authorization_id": "AWS-READ-AUTH-0002",
            "receipt_digest": "sha256:" + "d" * 64,
            "authority_source": "owner-message MSG-AWS-READ-0002",
        }
        rows = [
            self.deployment_row(
                evidence_id="EV-2361",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2362",
                phase="AWS-30",
                status="STALE",
                observed_at="2027-01-01T00:01:00Z",
                read_authority=old_read,
            ),
            self.deployment_row(
                evidence_id="EV-2363",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:02:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2364",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-01T00:03:00Z",
                read_authority=new_read,
            ),
        ]
        result = self.derive_deployment(rows, read_authority=new_read)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(
            any(
                "AWS-30" in issue and "terminal" in issue.casefold()
                for issue in result["issues"]
            ),
            result,
        )

    def test_second_receipt_backed_attempt_requires_prior_cutoff_and_fresh_authority(
        self,
    ) -> None:
        read = self.deployment_read_authority()
        for lane in ("fast-dev", "explicit-gate"):
            with self.subTest(lane=lane):
                _unused, current_digest = self.deployment_verify_text(
                    [], lane=lane, explicit_authorization_id="AWS-AUTH-0002"
                )
                historical_digest = "sha256:" + "e" * 64
                rows = [
                    self.deployment_row(
                        evidence_id="EV-2371",
                        attempt_id="AWS-DEPLOY-0001",
                        phase="AWS-20",
                        status="STARTED",
                        observed_at="2027-01-01T00:00:00Z",
                        lane=lane,
                        deployment_authorization="AWS-AUTH-0001",
                        receipt_digest=historical_digest,
                    ),
                    self.deployment_row(
                        evidence_id="EV-2372",
                        attempt_id="AWS-DEPLOY-0001",
                        phase="AWS-20",
                        status="SUCCEEDED",
                        observed_at="2027-01-01T00:01:00Z",
                        lane=lane,
                        deployment_authorization="AWS-AUTH-0001",
                        receipt_digest=historical_digest,
                    ),
                    self.deployment_row(
                        evidence_id="EV-2373",
                        attempt_id="AWS-DEPLOY-0001",
                        phase="AWS-30",
                        status="COMPLETE",
                        observed_at="2027-01-01T00:02:00Z",
                        lane=lane,
                        deployment_authorization="AWS-AUTH-0001",
                        receipt_digest=historical_digest,
                        read_authority=read,
                    ),
                    self.deployment_row(
                        evidence_id="EV-2374",
                        attempt_id="AWS-DEPLOY-0002",
                        phase="AWS-20",
                        status="STARTED",
                        observed_at="2027-01-01T00:03:00Z",
                        lane=lane,
                        deployment_authorization="AWS-AUTH-0002",
                        receipt_digest=current_digest,
                    ),
                ]
                for cutoff in ("NONE", "EV-9001"):
                    blocked = self.derive_deployment(
                        rows,
                        lane=lane,
                        read_authority=read,
                        release_evidence_cutoff=cutoff,
                        explicit_authorization_id="AWS-AUTH-0002",
                    )
                    self.assertEqual(blocked["status"], "BLOCKED", blocked)
                    self.assertTrue(
                        any(
                            "prior" in issue.casefold() and "cutoff" in issue.casefold()
                            for issue in blocked["issues"]
                        ),
                        blocked,
                    )

                allowed = self.derive_deployment(
                    rows,
                    lane=lane,
                    read_authority=read,
                    release_evidence_cutoff="EV-2373",
                    explicit_authorization_id="AWS-AUTH-0002",
                )
                self.assertEqual(allowed["status"], "ACTION_TERMINAL_REQUIRED", allowed)
                self.assertEqual(allowed["attempt_id"], "AWS-DEPLOY-0002")
                self.assertEqual(allowed["deployment_authorization"], "AWS-AUTH-0002")

    def test_deployment_and_read_observations_cannot_precede_authorization(
        self,
    ) -> None:
        started = self.deployment_row(
            evidence_id="EV-2381",
            phase="AWS-20",
            status="STARTED",
            observed_at="2027-01-01T00:00:00Z",
        )
        too_early = self.derive_deployment(
            [started], gate_b_authorized_at="2027-01-01T00:00:30Z"
        )
        self.assertEqual(too_early["status"], "BLOCKED", too_early)
        self.assertTrue(
            any(
                "precedes" in issue.casefold() and "authorization" in issue.casefold()
                for issue in too_early["issues"]
            ),
            too_early,
        )

        read = {
            **self.deployment_read_authority(),
            "authorized_at": "2027-01-01T00:03:00Z",
        }
        rows = [
            started,
            self.deployment_row(
                evidence_id="EV-2382",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:01:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2383",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-01T00:02:00Z",
                read_authority=read,
            ),
        ]
        read_too_early = self.derive_deployment(rows, read_authority=read)
        self.assertEqual(read_too_early["status"], "BLOCKED", read_too_early)
        self.assertTrue(
            any(
                "read" in issue.casefold() and "precedes" in issue.casefold()
                for issue in read_too_early["issues"]
            ),
            read_too_early,
        )

    def test_historical_fast_dev_rows_require_canonical_basis_validity_and_scope(
        self,
    ) -> None:
        read = self.deployment_read_authority()

        def history(**overrides: str) -> list[tuple[str, ...]]:
            common = {
                "lane": "fast-dev",
                "basis": "REQ-0000 / DES-0000 / AUTH-0000",
                "deployment_authorization": "AUTH-0000",
                **overrides,
            }
            return [
                self.deployment_row(
                    evidence_id="EV-2391",
                    attempt_id="AWS-DEPLOY-0001",
                    phase="AWS-20",
                    status="STARTED",
                    observed_at="2027-01-01T00:00:00Z",
                    **common,
                ),
                self.deployment_row(
                    evidence_id="EV-2392",
                    attempt_id="AWS-DEPLOY-0001",
                    phase="AWS-20",
                    status="SUCCEEDED",
                    observed_at="2027-01-01T00:01:00Z",
                    **common,
                ),
                self.deployment_row(
                    evidence_id="EV-2393",
                    attempt_id="AWS-DEPLOY-0001",
                    phase="AWS-30",
                    status="COMPLETE",
                    observed_at="2027-01-01T00:02:00Z",
                    read_authority=read,
                    **common,
                ),
                self.deployment_row(
                    evidence_id="EV-2394",
                    attempt_id="AWS-DEPLOY-0002",
                    phase="AWS-20",
                    status="STARTED",
                    observed_at="2027-01-01T00:03:00Z",
                ),
            ]

        cases = {
            "noncanonical basis": {"basis": "REQ-0000 / not-a-design / AUTH-0000"},
            "one-operation validity": {"deployment_valid_until": "ONE_OPERATION"},
            "unresolved account": {
                "account_scope": (
                    "ACCOUNT: TODO; REGION: us-west-2; ENVIRONMENT: development"
                )
            },
            "unresolved region": {
                "account_scope": (
                    "ACCOUNT: 111122223333; REGION: TODO; ENVIRONMENT: development"
                )
            },
            "unresolved environment": {
                "account_scope": (
                    "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: TODO"
                )
            },
            "wildcard role": {"deployment_role": "fastlane-*"},
        }
        for label, overrides in cases.items():
            with self.subTest(label=label):
                result = self.derive_deployment(
                    history(**overrides),
                    read_authority=read,
                    release_evidence_cutoff="EV-2393",
                )
                self.assertEqual(result["status"], "BLOCKED", result)
                self.assertTrue(result["issues"], result)

    def test_historical_explicit_plan_binding_must_be_canonical(self) -> None:
        read = self.deployment_read_authority()
        _unused, current_digest = self.deployment_verify_text([], lane="explicit-gate")
        historical_digest = "sha256:" + "e" * 64
        common = {
            "lane": "explicit-gate",
            "basis": "REQ-0000 / DES-0000 / AUTH-0000",
            "deployment_authorization": "AWS-AUTH-0000",
            "receipt_digest": historical_digest,
            "plan_binding": "not-a-canonical-plan-binding",
        }
        rows = [
            self.deployment_row(
                evidence_id="EV-2401",
                attempt_id="AWS-DEPLOY-0001",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
                **common,
            ),
            self.deployment_row(
                evidence_id="EV-2402",
                attempt_id="AWS-DEPLOY-0001",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:01:00Z",
                **common,
            ),
            self.deployment_row(
                evidence_id="EV-2403",
                attempt_id="AWS-DEPLOY-0001",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-01T00:02:00Z",
                read_authority=read,
                **common,
            ),
            self.deployment_row(
                evidence_id="EV-2404",
                attempt_id="AWS-DEPLOY-0002",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:03:00Z",
                lane="explicit-gate",
                receipt_digest=current_digest,
            ),
        ]
        result = self.derive_deployment(
            rows,
            lane="explicit-gate",
            read_authority=read,
            release_evidence_cutoff="EV-2403",
        )
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(
            any(
                "plan" in issue.casefold() and "canonical" in issue.casefold()
                for issue in result["issues"]
            ),
            result,
        )

    def test_independently_authorized_read_receipt_may_use_same_role(self) -> None:
        read = {
            **self.deployment_read_authority(),
            "role_or_profile": "fastlane-deployment-role",
        }
        rows = [
            self.deployment_row(
                evidence_id="EV-2411",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2412",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:01:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2413",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-01T00:02:00Z",
                read_authority=read,
            ),
        ]
        result = self.derive_deployment(rows, read_authority=read)
        self.assertEqual(result["status"], "RECONCILED", result)
        self.assertEqual(result["read_role_or_profile"], "fastlane-deployment-role")

    def test_stale_reconciliation_requires_resolved_identity_boundary(self) -> None:
        read = self.deployment_read_authority()
        rows = [
            self.deployment_row(
                evidence_id="EV-2421",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2422",
                phase="AWS-20",
                status="UNKNOWN",
                observed_at="2027-01-01T00:01:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2423",
                phase="AWS-30",
                status="STALE",
                observed_at="2027-01-01T00:02:00Z",
                read_authority=read,
                identity_and_boundary_match="TODO",
            ),
        ]
        result = self.derive_deployment(rows, read_authority=read)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(
            any(
                "identity" in issue.casefold() and "boundary" in issue.casefold()
                for issue in result["issues"]
            ),
            result,
        )

    def test_stale_basis_terminal_reconciliation_is_recoverable(self) -> None:
        template = (PROJECT_ROOT / doctor.VERIFY_FILE).read_text(encoding="utf-8")
        verify_text, read = self.bind_read_receipt(
            template,
            construction_authorization="AUTH-0000",
            authorized_at="2027-01-01T00:01:30Z",
        )
        old = {
            "basis": "REQ-0000 / DES-0000 / AUTH-0000",
            "deployment_authorization": "AUTH-0000",
        }
        rows = [
            self.deployment_row(
                evidence_id="EV-2431",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
                **old,
            ),
            self.deployment_row(
                evidence_id="EV-2432",
                phase="AWS-20",
                status="UNKNOWN",
                observed_at="2027-01-01T00:01:00Z",
                **old,
            ),
            self.deployment_row(
                evidence_id="EV-2433",
                phase="AWS-30",
                status="BLOCKED",
                observed_at="2027-01-01T00:02:00Z",
                read_authority=read,
                **old,
            ),
        ]
        verify_text = replace_contract_table(
            verify_text,
            doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
            doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS,
            rows,
        )
        result = doctor.derive_deployment_sequence_state(
            verify_text,
            None,
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            construction_authorization="AUTH-0001",
            envelope=self.deployment_envelope(),
            lane="fast-dev",
            artifact_binding=self._DEPLOYMENT_ARTIFACT,
            gate_b_authority_source="owner-message MSG-GATE-B-0001",
            gate_b_authorized_at="2026-12-31T23:59:59Z",
            restricted_closure=True,
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
        )
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(result["basis_stale"])
        self.assertEqual(result["reconciliation_status"], "BLOCKED")
        self.assertEqual(
            doctor.derive_aws_delivery_route(
                "READY_TO_DEPLOY",
                {"progress_state": "AWS_PREFLIGHT_READY"},
                result,
                "fast-dev",
            ),
            ("RELEASE_REVIEW", "RELEASE-10"),
        )

    def test_terminal_acknowledgment_survives_later_authority_expiry(self) -> None:
        read = {
            **self.deployment_read_authority(),
            "authorized_at": "2025-01-01T00:00:00Z",
            "expiration": "2026-01-01T00:00:00Z",
        }
        envelope = self.deployment_envelope()
        envelope["AWS authorization validity"] = (
            "Expires at 2026-01-01T00:00:00Z; "
            "earlier completion: authorized AWS action ends"
        )
        rows = [
            self.deployment_row(
                evidence_id="EV-2441",
                phase="AWS-20",
                status="STARTED",
                observed_at="2025-12-31T23:55:00Z",
                deployment_valid_until="2026-01-01T00:00:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2442",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2025-12-31T23:56:00Z",
                deployment_valid_until="2026-01-01T00:00:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2443",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2025-12-31T23:57:00Z",
                deployment_valid_until="2026-01-01T00:00:00Z",
                read_authority=read,
            ),
        ]
        current = self.derive_deployment(
            rows,
            read_authority=read,
            envelope=envelope,
            gate_b_authorized_at="2025-01-01T00:00:00Z",
        )
        self.assertEqual(current["status"], "RECONCILED", current)
        acknowledged = self.derive_deployment(
            rows,
            read_authority=None,
            envelope=envelope,
            gate_b_authorized_at="2025-01-01T00:00:00Z",
            release_state="RELEASE_VERIFIED",
            release_evidence_cutoff="EV-2443",
        )
        self.assertEqual(acknowledged["status"], "CONSUMED", acknowledged)

    def test_deployment_sequence_routes_through_release_cutoff_and_residual_review(
        self,
    ) -> None:
        read = self.deployment_read_authority()
        started = self.deployment_row(
            evidence_id="EV-2451",
            phase="AWS-20",
            status="STARTED",
            observed_at="2027-01-01T00:00:00Z",
        )
        action_pending = self.derive_deployment([started])
        self.assertEqual(action_pending["status"], "ACTION_TERMINAL_REQUIRED")
        self.assertEqual(
            doctor.derive_aws_delivery_route(
                "READY_TO_DEPLOY",
                {"progress_state": "AWS_PREFLIGHT_READY"},
                action_pending,
                "fast-dev",
            ),
            ("AWS_DEPLOYMENT_ACTION_TERMINAL", "AWS-20"),
        )

        terminal = self.deployment_row(
            evidence_id="EV-2452",
            phase="AWS-20",
            status="SUCCEEDED",
            observed_at="2027-01-01T00:01:00Z",
        )
        reconciliation_pending = self.derive_deployment([started, terminal])
        self.assertEqual(reconciliation_pending["status"], "RECONCILIATION_REQUIRED")
        self.assertEqual(
            doctor.derive_aws_delivery_route(
                "READY_TO_DEPLOY",
                {"progress_state": "AWS_PREFLIGHT_READY"},
                reconciliation_pending,
                "fast-dev",
            ),
            ("AWS_DEPLOYMENT_RECONCILIATION", "AWS-30"),
        )

        reconciliation = self.deployment_row(
            evidence_id="EV-2453",
            phase="AWS-30",
            status="COMPLETE",
            observed_at="2027-01-01T00:02:00Z",
            read_authority=read,
        )
        reconciled = self.derive_deployment(
            [started, terminal, reconciliation], read_authority=read
        )
        self.assertEqual(reconciled["status"], "RECONCILED")
        self.assertEqual(
            doctor.derive_aws_delivery_route(
                "READY_TO_DEPLOY",
                {"progress_state": "AWS_PREFLIGHT_READY"},
                reconciled,
                "fast-dev",
            ),
            ("RELEASE_REVIEW", "RELEASE-10"),
        )

        consumed = self.derive_deployment(
            [started, terminal, reconciliation],
            read_authority=read,
            release_state="RELEASE_VERIFIED",
            release_evidence_cutoff="EV-2453",
        )
        self.assertEqual(consumed["status"], "CONSUMED")
        self.assertIsNone(
            doctor.derive_aws_delivery_route(
                "RELEASE_VERIFIED",
                {"progress_state": "AWS_PREFLIGHT_READY"},
                consumed,
                "fast-dev",
                "EV-2453",
            )
        )
        terminal_tasks = doctor.TaskSummary(
            plan_revision="PLAN-0001",
            plan_state="CURRENT",
            statuses={"TASK-001": "DONE"},
        )
        self.assertEqual(
            doctor.derive_route(
                "APPROVED_FOR_DESIGN",
                "APPROVED_FOR_CONSTRUCTION",
                True,
                True,
                terminal_tasks,
                True,
                "NONE",
                "RELEASE_VERIFIED",
            ),
            ("RELEASE_VERIFIED", "STOP"),
        )
        self.assertEqual(
            doctor.derive_teardown_route("RESIDUAL_REVIEW", {"status": "NOT_ACTIVE"}),
            ("AWS_RESIDUAL_REVIEW", "AWS-40"),
        )

    def test_started_and_every_terminal_action_require_aws30(self) -> None:
        for lane in ("fast-dev", "explicit-gate"):
            base_text, receipt_digest = self.deployment_verify_text([], lane=lane)
            del base_text
            for action_status in (
                "STARTED",
                "SUCCEEDED",
                "FAILED",
                "PARTIAL",
                "UNKNOWN",
            ):
                with self.subTest(lane=lane, action_status=action_status):
                    rows = [
                        self.deployment_row(
                            evidence_id="EV-2001",
                            phase="AWS-20",
                            status="STARTED",
                            observed_at="2027-01-01T00:00:00Z",
                            lane=lane,
                            receipt_digest=receipt_digest,
                        )
                    ]
                    if action_status != "STARTED":
                        rows.append(
                            self.deployment_row(
                                evidence_id="EV-2002",
                                phase="AWS-20",
                                status=action_status,
                                observed_at="2027-01-01T00:01:00Z",
                                lane=lane,
                                receipt_digest=receipt_digest,
                            )
                        )
                    result = self.derive_deployment(rows, lane=lane)
                    expected_status = (
                        "ACTION_TERMINAL_REQUIRED"
                        if action_status == "STARTED"
                        else "RECONCILIATION_REQUIRED"
                    )
                    self.assertEqual(result["status"], expected_status)
                    self.assertEqual(result["action_status"], action_status)
                    self.assertEqual(result["reconciliation_status"], "NONE")
                    self.assertEqual(result["phase"], "AWS-20")
                    expected_route = (
                        ("AWS_DEPLOYMENT_ACTION_TERMINAL", "AWS-20")
                        if action_status == "STARTED"
                        else ("AWS_DEPLOYMENT_RECONCILIATION", "AWS-30")
                    )
                    self.assertEqual(
                        doctor.derive_aws_delivery_route(
                            "READY_TO_DEPLOY",
                            {"progress_state": "AWS_PREFLIGHT_READY"},
                            result,
                            lane,
                        ),
                        expected_route,
                    )

    def test_started_row_has_exact_pre_call_sentinel_and_no_result(self) -> None:
        started = self.deployment_row(
            evidence_id="EV-2051",
            phase="AWS-20",
            status="STARTED",
            observed_at="2027-01-01T00:00:00Z",
        )
        result_index = doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS.index(
            "Operation identifiers and direct result"
        )
        self.assertEqual(
            doctor.AWS_DEPLOYMENT_PRECALL_RESULT,
            "NOT_OBSERVED — pre-call journal only",
        )
        self.assertEqual(started[result_index], "NOT_OBSERVED — pre-call journal only")
        valid = self.derive_deployment([started])
        self.assertEqual(valid["status"], "ACTION_TERMINAL_REQUIRED", valid)

        claimed = list(started)
        claimed[result_index] = "request-123 already succeeded"
        claimed_result = self.derive_deployment([tuple(claimed)])
        self.assertEqual(claimed_result["status"], "BLOCKED", claimed_result)

        terminal = list(
            self.deployment_row(
                evidence_id="EV-2052",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:01:00Z",
            )
        )
        terminal[result_index] = "NOT_OBSERVED — pre-call journal only"
        terminal_result = self.derive_deployment([started, tuple(terminal)])
        self.assertEqual(terminal_result["status"], "BLOCKED", terminal_result)

    def test_stale_reconciliation_can_refresh_to_either_terminal_outcome(self) -> None:
        old_read = self.deployment_read_authority()
        new_read = {
            **old_read,
            "authorization_id": "AWS-READ-AUTH-0002",
            "receipt_digest": "sha256:" + "d" * 64,
            "role_or_profile": "fastlane-read-role-2",
        }
        for terminal_status, expected_status in (
            ("COMPLETE", "RECONCILED"),
            ("BLOCKED", "BLOCKED"),
        ):
            with self.subTest(terminal_status=terminal_status):
                rows = [
                    self.deployment_row(
                        evidence_id="EV-2151",
                        phase="AWS-20",
                        status="STARTED",
                        observed_at="2027-01-01T00:00:00Z",
                    ),
                    self.deployment_row(
                        evidence_id="EV-2152",
                        phase="AWS-20",
                        status="SUCCEEDED",
                        observed_at="2027-01-01T00:01:00Z",
                    ),
                    self.deployment_row(
                        evidence_id="EV-2153",
                        phase="AWS-30",
                        status="STALE",
                        observed_at="2027-01-01T00:02:00Z",
                        read_authority=old_read,
                    ),
                    self.deployment_row(
                        evidence_id="EV-2154",
                        phase="AWS-30",
                        status=terminal_status,
                        observed_at="2027-01-01T00:03:00Z",
                        read_authority=new_read,
                    ),
                ]
                result = self.derive_deployment(rows, read_authority=new_read)
                self.assertEqual(result["status"], expected_status, result)
                self.assertEqual(result["issues"], [], result)
                self.assertEqual(result["reconciliation_status"], terminal_status)
                self.assertEqual(result["read_authorization"], "AWS-READ-AUTH-0002")
                self.assertEqual(result["read_role_or_profile"], "fastlane-read-role-2")

    def test_reconciliation_refresh_replay_and_post_terminal_rows_fail_closed(
        self,
    ) -> None:
        old_read = self.deployment_read_authority()
        new_read = {
            **old_read,
            "authorization_id": "AWS-READ-AUTH-0002",
            "receipt_digest": "sha256:" + "d" * 64,
            "role_or_profile": "fastlane-read-role-2",
        }
        start = self.deployment_row(
            evidence_id="EV-2161",
            phase="AWS-20",
            status="STARTED",
            observed_at="2027-01-01T00:00:00Z",
        )
        terminal = self.deployment_row(
            evidence_id="EV-2162",
            phase="AWS-20",
            status="SUCCEEDED",
            observed_at="2027-01-01T00:01:00Z",
        )
        stale_old = self.deployment_row(
            evidence_id="EV-2163",
            phase="AWS-30",
            status="STALE",
            observed_at="2027-01-01T00:02:00Z",
            read_authority=old_read,
        )
        stale_new = self.deployment_row(
            evidence_id="EV-2164",
            phase="AWS-30",
            status="STALE",
            observed_at="2027-01-01T00:03:00Z",
            read_authority=new_read,
        )
        complete_old = self.deployment_row(
            evidence_id="EV-2164",
            phase="AWS-30",
            status="COMPLETE",
            observed_at="2027-01-01T00:03:00Z",
            read_authority=old_read,
        )
        complete_new = self.deployment_row(
            evidence_id="EV-2164",
            phase="AWS-30",
            status="COMPLETE",
            observed_at="2027-01-01T00:03:00Z",
            read_authority=new_read,
        )
        post_terminal = self.deployment_row(
            evidence_id="EV-2165",
            phase="AWS-30",
            status="STALE",
            observed_at="2027-01-01T00:04:00Z",
            read_authority=old_read,
        )
        cases = {
            "second stale": [start, terminal, stale_old, stale_new],
            "same read authorization reused": [
                start,
                terminal,
                stale_old,
                complete_old,
            ],
            "row after terminal reconciliation": [
                start,
                terminal,
                stale_old,
                complete_new,
                post_terminal,
            ],
        }
        for label, rows in cases.items():
            with self.subTest(label=label):
                result = self.derive_deployment(rows, read_authority=new_read)
                self.assertEqual(result["status"], "BLOCKED", result)
                self.assertTrue(result["issues"], result)

    def test_unreconciled_stale_basis_attempt_cannot_disappear(self) -> None:
        old_attempt = self.deployment_row(
            evidence_id="EV-2171",
            phase="AWS-20",
            status="STARTED",
            observed_at="2027-01-01T00:00:00Z",
            basis="REQ-0000 / DES-0000 / AUTH-0000",
        )
        result = self.derive_deployment([old_attempt])
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(result["basis_stale"])
        self.assertTrue(
            any(
                "original Gate B authorization provenance" in issue
                for issue in result["issues"]
            ),
            result,
        )
        terminal = self.deployment_row(
            evidence_id="EV-2172",
            phase="AWS-20",
            status="UNKNOWN",
            observed_at="2027-01-01T00:01:00Z",
            basis="REQ-0000 / DES-0000 / AUTH-0000",
        )
        result = self.derive_deployment([old_attempt, terminal])
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(result["basis_stale"])
        self.assertTrue(
            any(
                "original Gate B authorization provenance" in issue
                for issue in result["issues"]
            ),
            result,
        )

    def test_fast_dev_construction_authorization_cannot_be_replayed(self) -> None:
        read = self.deployment_read_authority()
        rows = [
            self.deployment_row(
                evidence_id="EV-2181",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2182",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-01T00:01:00Z",
            ),
            self.deployment_row(
                evidence_id="EV-2183",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-01T00:02:00Z",
                read_authority=read,
            ),
            self.deployment_row(
                evidence_id="EV-2184",
                attempt_id="AWS-DEPLOY-0002",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:03:00Z",
            ),
        ]
        result = self.derive_deployment(rows, read_authority=read)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(
            any(
                "replays a deployment authorization" in issue.casefold()
                for issue in result["issues"]
            ),
            result,
        )

    def test_aws30_complete_blocked_and_stale_have_distinct_states(self) -> None:
        read = self.deployment_read_authority()
        expected = {
            "COMPLETE": "RECONCILED",
            "BLOCKED": "BLOCKED",
            "STALE": "RECONCILIATION_REQUIRED",
        }
        for lane in ("fast-dev", "explicit-gate"):
            _base, receipt_digest = self.deployment_verify_text([], lane=lane)
            for reconciliation_status, projection_status in expected.items():
                with self.subTest(
                    lane=lane, reconciliation_status=reconciliation_status
                ):
                    rows = [
                        self.deployment_row(
                            evidence_id="EV-2101",
                            phase="AWS-20",
                            status="STARTED",
                            observed_at="2027-01-01T00:00:00Z",
                            lane=lane,
                            receipt_digest=receipt_digest,
                        ),
                        self.deployment_row(
                            evidence_id="EV-2102",
                            phase="AWS-20",
                            status="SUCCEEDED",
                            observed_at="2027-01-01T00:01:00Z",
                            lane=lane,
                            receipt_digest=receipt_digest,
                        ),
                        self.deployment_row(
                            evidence_id="EV-2103",
                            phase="AWS-30",
                            status=reconciliation_status,
                            observed_at="2027-01-01T00:02:00Z",
                            lane=lane,
                            read_authority=read,
                            receipt_digest=receipt_digest,
                        ),
                    ]
                    result = self.derive_deployment(
                        rows, lane=lane, read_authority=read
                    )
                    self.assertEqual(result["status"], projection_status)
                    self.assertEqual(
                        result["reconciliation_status"], reconciliation_status
                    )
                    self.assertEqual(result["phase"], "AWS-30")
                    self.assertEqual(
                        result["deployment_role_or_profile"],
                        "fastlane-deployment-role",
                    )
                    self.assertEqual(
                        result["read_role_or_profile"], "fastlane-read-role"
                    )

                    expected_route = (
                        ("AWS_DEPLOYMENT_RECONCILIATION", "AWS-30")
                        if reconciliation_status == "STALE"
                        else ("RELEASE_REVIEW", "RELEASE-10")
                    )
                    self.assertEqual(
                        doctor.derive_aws_delivery_route(
                            "READY_TO_DEPLOY",
                            {"progress_state": "AWS_PREFLIGHT_READY"},
                            result,
                            lane,
                        ),
                        expected_route,
                    )

    def test_attempt_journal_mismatch_duplicate_order_and_replay_fail_closed(
        self,
    ) -> None:
        read = self.deployment_read_authority()
        started = self.deployment_row(
            evidence_id="EV-2201",
            phase="AWS-20",
            status="STARTED",
            observed_at="2027-01-01T00:00:00Z",
        )
        terminal = self.deployment_row(
            evidence_id="EV-2202",
            phase="AWS-20",
            status="SUCCEEDED",
            observed_at="2027-01-01T00:01:00Z",
        )
        reconciliation = self.deployment_row(
            evidence_id="EV-2203",
            phase="AWS-30",
            status="COMPLETE",
            observed_at="2027-01-01T00:02:00Z",
            read_authority=read,
        )
        cases = {
            "duplicate evidence": [started, started],
            "mismatched immutable binding": [
                started,
                self.deployment_row(
                    evidence_id="EV-2202",
                    phase="AWS-20",
                    status="SUCCEEDED",
                    observed_at="2027-01-01T00:01:00Z",
                    artifact="sha256:" + "f" * 64,
                ),
            ],
            "out of order": [reconciliation, started],
            "duplicate reconciliation": [
                started,
                terminal,
                reconciliation,
                self.deployment_row(
                    evidence_id="EV-2204",
                    phase="AWS-30",
                    status="BLOCKED",
                    observed_at="2027-01-01T00:03:00Z",
                    read_authority=read,
                ),
            ],
            "noncontiguous replay": [
                started,
                terminal,
                reconciliation,
                self.deployment_row(
                    evidence_id="EV-2204",
                    attempt_id="AWS-DEPLOY-0002",
                    phase="AWS-20",
                    status="STARTED",
                    observed_at="2027-01-01T00:03:00Z",
                ),
                self.deployment_row(
                    evidence_id="EV-2205",
                    attempt_id="AWS-DEPLOY-0001",
                    phase="AWS-20",
                    status="STARTED",
                    observed_at="2027-01-01T00:04:00Z",
                ),
            ],
            "mismatched revision": [
                started,
                self.deployment_row(
                    evidence_id="EV-2202",
                    phase="AWS-20",
                    status="SUCCEEDED",
                    observed_at="2027-01-01T00:01:00Z",
                    basis="REQ-9999 / DES-0001 / AUTH-0001",
                ),
            ],
        }
        for label, rows in cases.items():
            with self.subTest(label=label):
                result = self.derive_deployment(rows, read_authority=read)
                self.assertEqual(result["status"], "BLOCKED", result)
                self.assertTrue(result["issues"], result)

    def test_attempt_is_not_inferred_from_receipt_provenance_or_iac(self) -> None:
        verify_text, _digest = self.deployment_verify_text([], lane="explicit-gate")
        result = doctor.derive_deployment_sequence_state(
            verify_text,
            self.deployment_read_authority(),
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            construction_authorization="AUTH-0001",
            envelope=self.deployment_envelope(),
            lane="explicit-gate",
            artifact_binding=self._DEPLOYMENT_ARTIFACT,
        )
        self.assertEqual(result["status"], "NOT_ACTIVE")
        self.assertEqual(result["attempt_id"], "NONE")
        self.assertEqual(result["action_status"], "NONE")

        self.assertEqual(
            doctor.derive_aws_delivery_route(
                "READY_TO_DEPLOY",
                {"progress_state": "WAITING_AWS_MUTATION_AUTH"},
                result,
                "explicit-gate",
            ),
            ("WAITING_AWS_MUTATION_AUTH", "AWS-20"),
        )
        self.assertNotEqual(result["phase"], "AWS-20")

    def test_aws30_projects_only_separate_reusable_read_authority(self) -> None:
        context = doctor.Context(PROJECT_ROOT)
        context.texts[doctor.VERIFY_FILE] = "verification"
        read = self.deployment_read_authority()
        calls: list[tuple[str, bool]] = []
        original_read = doctor._read_preflight_receipt_authority
        original_action = doctor._receipt_external_authority

        def fake_read(
            _text: str,
            _authorization: str,
            _cost: str,
            _envelope: dict[str, str],
            _artifact: str,
            *,
            allow_one_operation: bool = True,
        ) -> dict[str, object]:
            calls.append(("read", allow_one_operation))
            return read

        def forbidden_action(*_args: object, **_kwargs: object) -> None:
            calls.append(("deployment", True))
            return None

        doctor._read_preflight_receipt_authority = fake_read
        doctor._receipt_external_authority = forbidden_action
        try:
            authority = doctor.derive_external_authority(
                context,
                self.deployment_envelope(),
                "explicit-gate",
                "AUTH-0001",
                cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
                active_artifact=self._DEPLOYMENT_ARTIFACT,
                aws_action_phase="AWS-30",
            )
        finally:
            doctor._read_preflight_receipt_authority = original_read
            doctor._receipt_external_authority = original_action
        self.assertEqual(calls, [("read", False)])
        self.assertEqual(authority["kind"], "AWS_READ_ONLY")
        self.assertEqual(authority["authorization_id"], "AWS-READ-AUTH-0001")
        self.assertEqual(authority["role_or_profile"], "fastlane-read-role")
        self.assertNotEqual(authority["role_or_profile"], "fastlane-deployment-role")

    def test_expired_gate_b_closes_attempt_without_reviving_broad_authority(
        self,
    ) -> None:
        fixture = support.BootstrapDoctorTests()
        with tempfile.TemporaryDirectory() as directory:
            project = fixture.copy_project(Path(directory))
            manifest_path = project / "bootstrap.manifest.json"
            state_path = project / "bootstrap.yaml"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            manifest["bootstrap_version"] = state["bootstrap_version"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            refresh_control_hashes(project)
            fixture.approve_project(project)

            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"]["aws_lane"] = "explicit-gate"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            prd_path = project / "docs/project/PRD.md"
            prd_text = prd_path.read_text(encoding="utf-8")
            prd_text = set_table_value(
                prd_text,
                "## Document status",
                "## 1. Workload profile",
                "AWS lane",
                "`explicit-gate`",
            )
            expired_at = "2026-07-18T18:00:00Z"
            envelope_values = {
                "Project AWS lane": "`explicit-gate`",
                "AWS boundary": "`MUTATE_LISTED_RESOURCES`",
                "AWS account": "`ACCOUNT: 111122223333`",
                "AWS role or profile": "`ROLE: fastlane-deployment-role`",
                "AWS Region": "`REGION: us-west-2`",
                "AWS environment": (
                    "`ENVIRONMENT: development; CLASS: NON_PRODUCTION`"
                ),
                "AWS stack or application": "`STACK: fastlane-stack`",
                "AWS resource allowlist": "`RESOURCES: fastlane-stack`",
                "AWS allowed operations": (
                    "`OPERATIONS: cloudformation:DescribeStacks, "
                    "cloudformation:CreateChangeSet, "
                    "cloudformation:ExecuteChangeSet`"
                ),
                "AWS cost ceiling": "`USD: 20.00`",
                "AWS prohibited operations": (
                    "`PROHIBITED: wildcard resources, IAM broadening, "
                    "destructive replacement`"
                ),
                "AWS artifact authorization and provenance": (
                    f"`EXACT_DIGEST: {self._DEPLOYMENT_ARTIFACT}`"
                ),
                "AWS rollback boundary": "`ROLLBACK: rollback fastlane-stack`",
                "AWS authorization validity": (
                    f"`Expires at {expired_at}; earlier completion: "
                    "authorized AWS action ends`"
                ),
                "Authorization expiry or completion condition": (
                    f"`Expires at {expired_at}; earlier completion: release review`"
                ),
            }
            for field, value in envelope_values.items():
                prd_text = set_table_value(
                    prd_text,
                    "## 28. Construction envelope",
                    "## 29. Gate B owner authorization record",
                    field,
                    value,
                )
            prd_path.write_text(rebind_gate_b_envelope(prd_text), encoding="utf-8")

            verify_path = project / "docs/project/VERIFY.md"
            verify_text = verify_path.read_text(encoding="utf-8")
            verify_text = replace_contract_table(
                verify_text,
                "## Verification matrix",
                self._VERIFICATION_MATRIX_HEADERS,
                [
                    (
                        "EV-9001",
                        "FR-001",
                        "TASK-001",
                        "FR-001 primary outcome passes after deployment",
                        "EV-0001 local suite passed",
                        "DescribeStacks returned UPDATE_COMPLETE",
                        f"ARTIFACT: {self._DEPLOYMENT_ARTIFACT}; "
                        "ACCOUNT: 111122223333; REGION: us-west-2; "
                        "ENVIRONMENT: development",
                        "VERIFIED",
                    )
                ],
            )
            verify_text, deployment_digest = self.bind_explicit_deployment_receipt(
                verify_text,
                valid_until=expired_at,
                authorized_at="2026-07-17T18:00:00Z",
            )
            verify_text = set_table_value(
                verify_text,
                "## Active evidence scope",
                "## Evidence status vocabulary",
                "Commit, tag, or image digest",
                f"`{self._DEPLOYMENT_ARTIFACT}`",
            )
            verify_text = verify_text.replace(
                "- Release state: `NOT_READY`",
                "- Release state: `READY_TO_DEPLOY`",
                1,
            ).replace(
                "- Active evidence cutoff: TODO",
                "- Active evidence cutoff: NONE",
                1,
            )

            started = self.deployment_row(
                evidence_id="EV-9501",
                phase="AWS-20",
                status="STARTED",
                observed_at="2026-07-17T18:30:00Z",
                lane="explicit-gate",
                receipt_digest=deployment_digest,
                deployment_valid_until=expired_at,
            )

            def write_rows(*rows: tuple[str, ...]) -> None:
                current = verify_path.read_text(encoding="utf-8")
                verify_path.write_text(
                    replace_contract_table(
                        current,
                        doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
                        doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS,
                        list(rows),
                    ),
                    encoding="utf-8",
                )

            verify_path.write_text(verify_text, encoding="utf-8")
            write_rows(started)
            started_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(started_report)
            self.assert_no_external_mutation_authority(started_report)

            self.assertTrue(started_report["ok"], started_report["diagnostics"])
            self.assertEqual(
                (started_report["lifecycle_state"], started_report["next_prompt"]),
                ("AWS_DEPLOYMENT_ACTION_TERMINAL", "AWS-20"),
            )
            self.assertEqual(
                started_report["interaction"]["owner_action_kind"],
                "NONE_CONTINUE_AUTOMATICALLY",
            )
            self.assertTrue(
                started_report["interaction"]["automatic_continuation_allowed"]
            )
            self.assertEqual(started_report["authorizations"]["construction"], "NONE")
            self.assertFalse(started_report["write_authority"]["valid"])
            self.assertEqual(started_report["external_authority"]["kind"], "NONE")
            closure = started_report["deployment_journal_closure_authority"]
            self.assertTrue(closure["valid"], closure)
            self.assertEqual(closure["mode"], "BOUNDED_EVIDENCE_CLOSURE")
            self.assertEqual(closure["allowed_write_paths"], [doctor.VERIFY_FILE])
            self.assertEqual(
                closure["allowed_sections"],
                [doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING],
            )
            self.assertEqual(
                closure["allowed_operations"],
                ["APPEND_ACTION_TERMINAL_ROW"],
            )
            self.assertEqual(closure["construction_authorization"], "NONE")
            self.assertEqual(closure["aws_mutation_authority"], "NONE")

            unknown = self.deployment_row(
                evidence_id="EV-9502",
                phase="AWS-20",
                status="UNKNOWN",
                observed_at="2026-07-29T00:01:00Z",
                lane="explicit-gate",
                receipt_digest=deployment_digest,
                deployment_valid_until=expired_at,
            )
            write_rows(started, unknown)
            missing_read_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(missing_read_report)
            self.assert_no_external_mutation_authority(missing_read_report)
            self.assertTrue(
                missing_read_report["ok"], missing_read_report["diagnostics"]
            )
            self.assertEqual(
                (
                    missing_read_report["lifecycle_state"],
                    missing_read_report["next_prompt"],
                ),
                ("AWS_DEPLOYMENT_RECONCILIATION", "AWS-30"),
            )
            self.assertEqual(
                missing_read_report["external_authority"]["kind"],
                "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED",
            )
            self.assertEqual(
                missing_read_report["interaction"]["owner_action_kind"],
                "AUTHORIZE_AWS_READ_PREFLIGHT",
            )
            self.assertFalse(missing_read_report["write_authority"]["valid"])
            self.assertEqual(
                missing_read_report["authorizations"]["construction"], "NONE"
            )
            closure = missing_read_report["deployment_journal_closure_authority"]
            self.assertEqual(
                closure["allowed_sections"],
                [
                    "bootstrap:aws-read-preflight-receipt",
                    "## Action authorization provenance",
                    doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
                ],
            )
            self.assertEqual(
                closure["allowed_operations"],
                [
                    "RECORD_RECONCILIATION_READ_AUTHORITY",
                    "APPEND_RECONCILIATION_ROW",
                ],
            )

            before_read = verify_path.read_text(encoding="utf-8")
            wildcard_read, _wildcard = self.bind_read_receipt(
                before_read,
                operations=("cloudformation:*",),
                authorized_at="2026-07-29T00:02:00Z",
            )
            verify_path.write_text(wildcard_read, encoding="utf-8")
            wildcard_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(wildcard_report)
            self.assert_no_external_mutation_authority(wildcard_report)
            self.assertEqual(
                wildcard_report["external_authority"]["kind"],
                "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED",
            )
            self.assertEqual(wildcard_report["authorizations"]["aws"], "NONE")

            read_bound, read_authority = self.bind_read_receipt(
                before_read,
                authorized_at="2026-07-29T00:02:00Z",
            )
            expired_read, _expired_authority = self.bind_read_receipt(
                before_read,
                authorized_at="2026-07-29T00:02:00Z",
                valid_until="2026-07-29T00:02:30Z",
            )
            verify_path.write_text(expired_read, encoding="utf-8")
            expired_read_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(expired_read_report)
            self.assert_no_external_mutation_authority(expired_read_report)
            self.assertEqual(
                expired_read_report["external_authority"]["kind"],
                "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED",
            )
            self.assertFalse(
                expired_read_report["interaction"]["automatic_continuation_allowed"]
            )
            verify_path.write_text(read_bound, encoding="utf-8")
            read_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(read_report)
            self.assert_no_external_mutation_authority(read_report)
            self.assertTrue(read_report["ok"], read_report["diagnostics"])
            self.assertEqual(read_report["external_authority"]["kind"], "AWS_READ_ONLY")
            self.assertEqual(
                read_report["external_authority"]["operations"],
                ["cloudformation:DescribeStacks"],
            )
            self.assertEqual(
                read_report["interaction"]["owner_action_kind"],
                "NONE_CONTINUE_AUTOMATICALLY",
            )
            self.assertFalse(read_report["write_authority"]["valid"])
            self.assertEqual(read_report["authorizations"]["construction"], "NONE")
            self.assertNotIn(
                "cloudformation:ExecuteChangeSet",
                read_report["external_authority"]["operations"],
            )

            terminal = self.deployment_row(
                evidence_id="EV-9503",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2026-07-29T00:03:00Z",
                lane="explicit-gate",
                receipt_digest=deployment_digest,
                deployment_valid_until=expired_at,
                read_authority=read_authority,
            )
            write_rows(started, unknown, terminal)
            terminal_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(terminal_report)
            self.assert_no_external_mutation_authority(terminal_report)
            self.assertTrue(terminal_report["ok"], terminal_report["diagnostics"])
            self.assertEqual(
                (terminal_report["lifecycle_state"], terminal_report["next_prompt"]),
                ("RELEASE_REVIEW", "RELEASE-10"),
            )
            self.assertEqual(terminal_report["aws_deployment"]["status"], "RECONCILED")
            self.assertFalse(terminal_report["write_authority"]["valid"])
            self.assertEqual(terminal_report["external_authority"]["kind"], "NONE")
            closure = terminal_report["deployment_journal_closure_authority"]
            self.assertEqual(
                closure["allowed_sections"], ["## Current release decision"]
            )
            self.assertEqual(
                closure["allowed_operations"],
                ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
            )
            self.assertEqual(
                closure["allowed_release_states"],
                ["NOT_READY", "RELEASE_VERIFIED"],
            )

            terminal_text = verify_path.read_text(encoding="utf-8")
            terminal_text = terminal_text.replace(
                "- Release state: `READY_TO_DEPLOY`",
                "- Release state: `RELEASE_VERIFIED`",
                1,
            ).replace(
                "- Active evidence cutoff: NONE",
                "- Active evidence cutoff: EV-9503",
                1,
            )
            verify_path.write_text(terminal_text, encoding="utf-8")
            consumed_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(consumed_report)
            self.assert_no_external_mutation_authority(consumed_report)
            self.assertTrue(consumed_report["ok"], consumed_report["diagnostics"])
            self.assertEqual(consumed_report["aws_deployment"]["status"], "CONSUMED")
            self.assert_no_closure_authority(consumed_report)
            self.assertFalse(consumed_report["write_authority"]["valid"])
            self.assertEqual(consumed_report["authorizations"]["construction"], "NONE")
            self.assertEqual(consumed_report["external_authority"]["kind"], "NONE")

    def test_stale_gate_b_closes_historical_attempt_without_reapproval(self) -> None:
        fixture = support.BootstrapDoctorTests()
        with tempfile.TemporaryDirectory() as directory:
            project = fixture.copy_project(Path(directory))
            manifest_path = project / "bootstrap.manifest.json"
            state_path = project / "bootstrap.yaml"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            manifest["bootstrap_version"] = state["bootstrap_version"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            refresh_control_hashes(project)
            fixture.approve_project(project)

            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"]["aws_lane"] = "explicit-gate"
            state["lifecycle"]["design_revision"] = "DES-0002"
            state["lifecycle"]["gate_b"] = "STALE"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            prd_path = project / "docs/project/PRD.md"
            prd_text = prd_path.read_text(encoding="utf-8")
            for field, value in {
                "Current design revision": "`DES-0002`",
                "Gate B derived status": "`STALE`",
                "AWS lane": "`explicit-gate`",
            }.items():
                prd_text = set_table_value(
                    prd_text,
                    "## Document status",
                    "## 1. Workload profile",
                    field,
                    value,
                )
            prd_text = set_table_value(
                prd_text,
                "## 27. Gate B agent review record",
                "## 28. Construction envelope",
                "Agent recommendation",
                "`BLOCKED`",
            )
            envelope_values = {
                "Project AWS lane": "`explicit-gate`",
                "AWS boundary": "`MUTATE_LISTED_RESOURCES`",
                "AWS account": "`ACCOUNT: 111122223333`",
                "AWS role or profile": "`ROLE: replacement-deployment-role`",
                "AWS Region": "`REGION: us-east-1`",
                "AWS environment": ("`ENVIRONMENT: redesign; CLASS: NON_PRODUCTION`"),
                "AWS stack or application": "`STACK: replacement-stack`",
                "AWS resource allowlist": "`RESOURCES: replacement-stack`",
                "AWS allowed operations": (
                    "`OPERATIONS: lambda:GetFunction, lambda:UpdateFunctionCode`"
                ),
                "AWS cost ceiling": "`USD: 20.00`",
                "AWS prohibited operations": (
                    "`PROHIBITED: wildcard resources, IAM broadening, "
                    "destructive replacement`"
                ),
                "AWS artifact authorization and provenance": (
                    "`EXACT_DIGEST: sha256:" + "f" * 64 + "`"
                ),
                "AWS rollback boundary": "`ROLLBACK: rollback replacement-stack`",
                "AWS authorization validity": (
                    "`Expires at 2099-01-01T00:00:00Z; earlier completion: "
                    "authorized AWS action ends`"
                ),
                "Authorization expiry or completion condition": (
                    "`Expires at 2099-01-01T00:00:00Z; earlier completion: "
                    "release review`"
                ),
            }
            for field, value in envelope_values.items():
                prd_text = set_table_value(
                    prd_text,
                    "## 28. Construction envelope",
                    "## 29. Gate B owner authorization record",
                    field,
                    value,
                )
            prd_path.write_text(prd_text, encoding="utf-8")

            tasks_path = project / "docs/project/TASKS.md"
            tasks_text = tasks_path.read_text(encoding="utf-8")
            tasks_text = set_table_value(
                tasks_text,
                "## Active execution snapshot",
                "## Dependencies, waivers, and waves",
                "Design revision",
                "`DES-0002`",
            )
            tasks_text = set_table_value(
                tasks_text,
                "## Active execution snapshot",
                "## Dependencies, waivers, and waves",
                "Gate B state",
                "`STALE`",
            )
            tasks_path.write_text(tasks_text, encoding="utf-8")

            verify_path = project / "docs/project/VERIFY.md"
            verify_text = verify_path.read_text(encoding="utf-8")
            verify_text = replace_contract_table(
                verify_text,
                "## Verification matrix",
                self._VERIFICATION_MATRIX_HEADERS,
                [
                    (
                        "EV-9001",
                        "FR-001",
                        "TASK-001",
                        "FR-001 primary outcome passes after deployment",
                        "EV-0001 local suite passed",
                        "DescribeStacks returned UPDATE_COMPLETE",
                        f"ARTIFACT: {self._DEPLOYMENT_ARTIFACT}; "
                        "ACCOUNT: 111122223333; REGION: us-west-2; "
                        "ENVIRONMENT: development",
                        "VERIFIED",
                    )
                ],
            )
            verify_text, deployment_digest = self.bind_explicit_deployment_receipt(
                verify_text,
                authorized_at="2026-07-17T18:00:00Z",
            )
            verify_text = set_table_value(
                verify_text,
                "## Active evidence scope",
                "## Evidence status vocabulary",
                "Commit, tag, or image digest",
                f"`{self._DEPLOYMENT_ARTIFACT}`",
            )
            verify_text = verify_text.replace(
                "- Release state: `NOT_READY`",
                "- Release state: `READY_TO_DEPLOY`",
                1,
            ).replace(
                "- Active evidence cutoff: TODO",
                "- Active evidence cutoff: NONE",
                1,
            )
            verify_path.write_text(verify_text, encoding="utf-8")

            started = self.deployment_row(
                evidence_id="EV-9601",
                phase="AWS-20",
                status="STARTED",
                observed_at="2026-07-18T00:00:00Z",
                lane="explicit-gate",
                receipt_digest=deployment_digest,
            )

            def write_rows(*rows: tuple[str, ...]) -> None:
                current = verify_path.read_text(encoding="utf-8")
                verify_path.write_text(
                    replace_contract_table(
                        current,
                        doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
                        doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS,
                        list(rows),
                    ),
                    encoding="utf-8",
                )

            write_rows(started)
            started_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(started_report)
            self.assertTrue(started_report["ok"], started_report["diagnostics"])
            self.assertEqual(started_report["gates"]["gate_b"], "STALE")
            self.assertEqual(
                (started_report["lifecycle_state"], started_report["next_prompt"]),
                ("AWS_DEPLOYMENT_ACTION_TERMINAL", "AWS-20"),
            )
            self.assertTrue(started_report["aws_deployment"]["basis_stale"])
            self.assertEqual(started_report["authorizations"]["construction"], "NONE")
            self.assertFalse(started_report["write_authority"]["valid"])
            self.assertEqual(started_report["external_authority"]["kind"], "NONE")
            self.assert_no_external_mutation_authority(started_report)
            self.assert_exact_closure_authority(
                started_report,
                sections=[doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING],
                operations=["APPEND_ACTION_TERMINAL_ROW"],
            )

            unknown = self.deployment_row(
                evidence_id="EV-9602",
                phase="AWS-20",
                status="UNKNOWN",
                observed_at="2026-07-29T01:00:00Z",
                lane="explicit-gate",
                receipt_digest=deployment_digest,
            )
            write_rows(started, unknown)
            no_read_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(no_read_report)
            self.assertTrue(no_read_report["ok"], no_read_report["diagnostics"])
            self.assertEqual(
                (no_read_report["lifecycle_state"], no_read_report["next_prompt"]),
                ("AWS_DEPLOYMENT_RECONCILIATION", "AWS-30"),
            )
            self.assertEqual(
                no_read_report["external_authority"]["kind"],
                "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED",
            )
            self.assertEqual(no_read_report["authorizations"]["construction"], "NONE")
            self.assert_no_external_mutation_authority(no_read_report)
            self.assert_exact_closure_authority(
                no_read_report,
                sections=[
                    "bootstrap:aws-read-preflight-receipt",
                    "## Action authorization provenance",
                    doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
                ],
                operations=[
                    "RECORD_RECONCILIATION_READ_AUTHORITY",
                    "APPEND_RECONCILIATION_ROW",
                ],
            )

            read_bound, read_authority = self.bind_read_receipt(
                verify_path.read_text(encoding="utf-8"),
                construction_authorization="AUTH-0001",
                authorized_at="2026-07-29T01:01:00Z",
            )
            verify_path.write_text(read_bound, encoding="utf-8")
            read_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(read_report)
            self.assertTrue(read_report["ok"], read_report["diagnostics"])
            self.assertEqual(read_report["external_authority"]["kind"], "AWS_READ_ONLY")
            self.assertEqual(
                read_report["external_authority"]["account"], "111122223333"
            )
            self.assertEqual(read_report["external_authority"]["region"], "us-west-2")
            self.assertEqual(
                read_report["external_authority"]["resources"], ["fastlane-stack"]
            )
            self.assertEqual(
                read_report["external_authority"]["artifact_plan_binding"]["artifact"],
                self._DEPLOYMENT_ARTIFACT,
            )
            self.assertEqual(read_report["authorizations"]["construction"], "NONE")
            self.assertFalse(read_report["write_authority"]["valid"])
            self.assert_no_external_mutation_authority(read_report)
            self.assert_exact_closure_authority(
                read_report,
                sections=[
                    "bootstrap:aws-read-preflight-receipt",
                    "## Action authorization provenance",
                    doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
                ],
                operations=[
                    "RECORD_RECONCILIATION_READ_AUTHORITY",
                    "APPEND_RECONCILIATION_ROW",
                ],
            )

            terminal = self.deployment_row(
                evidence_id="EV-9603",
                phase="AWS-30",
                status="BLOCKED",
                observed_at="2026-07-29T01:02:00Z",
                lane="explicit-gate",
                receipt_digest=deployment_digest,
                read_authority=read_authority,
            )
            write_rows(started, unknown, terminal)
            terminal_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(terminal_report)
            self.assertTrue(terminal_report["ok"], terminal_report["diagnostics"])
            self.assertEqual(
                (terminal_report["lifecycle_state"], terminal_report["next_prompt"]),
                ("RELEASE_REVIEW", "RELEASE-10"),
            )
            self.assertTrue(terminal_report["aws_deployment"]["basis_stale"])
            self.assertEqual(
                terminal_report["aws_deployment"]["reconciliation_status"],
                "BLOCKED",
            )
            self.assertEqual(terminal_report["authorizations"]["construction"], "NONE")
            self.assertEqual(terminal_report["external_authority"]["kind"], "NONE")
            self.assert_no_external_mutation_authority(terminal_report)
            self.assert_exact_closure_authority(
                terminal_report,
                sections=["## Current release decision"],
                operations=["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
                release_states=["NOT_READY"],
            )

            release_text = verify_path.read_text(encoding="utf-8")
            release_text = release_text.replace(
                "- Release state: `READY_TO_DEPLOY`",
                "- Release state: `NOT_READY`",
                1,
            ).replace(
                "- Active evidence cutoff: NONE",
                "- Active evidence cutoff: EV-9603",
                1,
            )
            verify_path.write_text(release_text, encoding="utf-8")
            consumed_report = doctor.inspect_project(project)
            self.assert_closure_context_is_resolved(consumed_report)
            self.assertTrue(consumed_report["ok"], consumed_report["diagnostics"])
            self.assertEqual(consumed_report["aws_deployment"]["status"], "CONSUMED")
            self.assertFalse(consumed_report["write_authority"]["valid"])
            self.assertEqual(consumed_report["authorizations"]["construction"], "NONE")
            self.assert_no_external_mutation_authority(consumed_report)
            self.assert_no_closure_authority(consumed_report)

    def test_stale_basis_aws30_requires_read_authority_not_mutation(self) -> None:
        stale_started = self.deployment_row(
            evidence_id="EV-2191",
            phase="AWS-20",
            status="STARTED",
            observed_at="2027-01-01T00:00:00Z",
            basis="REQ-0000 / DES-0000 / AUTH-0000",
            deployment_authorization="AUTH-0000",
        )
        stale_terminal = self.deployment_row(
            evidence_id="EV-2192",
            phase="AWS-20",
            status="UNKNOWN",
            observed_at="2027-01-01T00:01:00Z",
            basis="REQ-0000 / DES-0000 / AUTH-0000",
            deployment_authorization="AUTH-0000",
        )
        verify_text, _digest = self.deployment_verify_text(
            [stale_started, stale_terminal], lane="fast-dev"
        )
        sequence = doctor.derive_deployment_sequence_state(
            verify_text,
            None,
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            construction_authorization="AUTH-0001",
            envelope=self.deployment_envelope(),
            lane="fast-dev",
            artifact_binding=self._DEPLOYMENT_ARTIFACT,
            gate_b_authority_source="owner-message MSG-GATE-B-0001",
            gate_b_authorized_at="2026-12-31T23:59:59Z",
        )
        self.assertTrue(sequence["basis_stale"])
        self.assertEqual(sequence["status"], "RECONCILIATION_REQUIRED")
        self.assertEqual(
            doctor.derive_aws_delivery_route(
                "READY_TO_DEPLOY",
                {"progress_state": "AWS_PREFLIGHT_READY"},
                sequence,
                "fast-dev",
            ),
            ("AWS_DEPLOYMENT_RECONCILIATION", "AWS-30"),
        )

        context = doctor.Context(PROJECT_ROOT)
        context.texts[doctor.VERIFY_FILE] = verify_text
        authority = doctor.derive_external_authority(
            context,
            self.deployment_envelope(),
            "fast-dev",
            "AUTH-0001",
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            active_artifact=self._DEPLOYMENT_ARTIFACT,
            aws_action_phase="AWS-30",
        )
        self.assertEqual(authority["kind"], "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED")
        self.assertEqual(authority["validity"], "REQUIRED")
        self.assertNotEqual(authority["kind"], "FAST_DEV_GATE_B")
        interaction = doctor.derive_interaction(
            "AWS_DEPLOYMENT_RECONCILIATION",
            "AWS-30",
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=True,
            aws_execution_planning_ready=True,
            aws_lane="fast-dev",
            aws_read_authority_required=True,
        )
        self.assertEqual(
            interaction["owner_action_kind"], "AUTHORIZE_AWS_READ_PREFLIGHT"
        )
        self.assertFalse(interaction["automatic_continuation_allowed"])
        self.assertTrue(interaction["formal_receipt_required"])

    def test_stale_started_before_original_authorization_fails_closed(self) -> None:
        template = (PROJECT_ROOT / doctor.VERIFY_FILE).read_text(encoding="utf-8")
        verify_text, deployment_digest = self.bind_explicit_deployment_receipt(
            template,
            authorized_at="2027-01-01T00:00:00Z",
        )
        started = self.deployment_row(
            evidence_id="EV-9701",
            phase="AWS-20",
            status="STARTED",
            observed_at="2026-12-31T23:59:00Z",
            lane="explicit-gate",
            basis="REQ-0000 / DES-0000 / AUTH-0001",
            receipt_digest=deployment_digest,
        )
        verify_text = replace_contract_table(
            verify_text,
            doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
            doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS,
            [started],
        )
        result = doctor.derive_deployment_sequence_state(
            verify_text,
            None,
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            construction_authorization="AUTH-0001",
            envelope=self.deployment_envelope(),
            lane="explicit-gate",
            artifact_binding=self._DEPLOYMENT_ARTIFACT,
            gate_b_authority_source="owner-message MSG-GATE-B-0001",
            gate_b_authorized_at="2026-12-31T23:58:00Z",
            restricted_closure=True,
        )
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertIn(
            "precedes its original authorization provenance",
            " ".join(result["issues"]),
        )

    def test_normal_gate_b_reuses_exact_aws10_receipt_end_to_end(self) -> None:
        envelope = aws_authority_envelope(
            role="fastlane-deployment-role",
            account="111122223333",
            region="us-west-2",
            environment="development",
            resources=["fastlane-stack"],
            operations=[
                "cloudformation:DescribeStacks",
                *self._DEPLOYMENT_OPERATIONS,
            ],
            artifact=self._DEPLOYMENT_ARTIFACT,
            rollback="rollback fastlane-stack",
        )
        template = (PROJECT_ROOT / doctor.VERIFY_FILE).read_text(encoding="utf-8")
        verify_text, deployment_digest = self.bind_explicit_deployment_receipt(
            template,
            authorized_at="2026-12-31T23:58:00Z",
        )
        verify_text, read = self.bind_read_receipt(
            verify_text,
            authorized_at="2026-12-31T23:59:00Z",
        )
        rows = [
            self.deployment_row(
                evidence_id="EV-9711",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
                lane="explicit-gate",
                receipt_digest=deployment_digest,
            ),
            self.deployment_row(
                evidence_id="EV-9712",
                phase="AWS-20",
                status="UNKNOWN",
                observed_at="2027-01-01T00:01:00Z",
                lane="explicit-gate",
                receipt_digest=deployment_digest,
            ),
        ]
        verify_text = replace_contract_table(
            verify_text,
            doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
            doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS,
            rows,
        )
        sequence = doctor.derive_deployment_sequence_state(
            verify_text,
            read,
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            construction_authorization="AUTH-0001",
            envelope=envelope,
            lane="explicit-gate",
            artifact_binding=self._DEPLOYMENT_ARTIFACT,
            gate_b_authority_source="owner-message MSG-GATE-B-0001",
            gate_b_authorized_at="2026-12-31T23:57:00Z",
            restricted_closure=False,
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
        )
        self.assertEqual(sequence["status"], "RECONCILIATION_REQUIRED", sequence)
        projected = sequence["reconciliation_read_authority"]
        self.assertEqual(projected["authorization_id"], read["authorization_id"])
        self.assertFalse(projected["reconciliation_only"])
        context = doctor.Context(PROJECT_ROOT)
        context.texts[doctor.VERIFY_FILE] = verify_text
        authority = doctor.derive_external_authority(
            context,
            envelope,
            "explicit-gate",
            "AUTH-0001",
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            active_artifact=self._DEPLOYMENT_ARTIFACT,
            aws_action_phase="AWS-30",
            deployment_sequence=sequence,
        )
        self.assertEqual(authority["kind"], "AWS_READ_ONLY", authority)
        self.assertEqual(authority["authorization_id"], read["authorization_id"])

    def test_stale_complete_can_only_acknowledge_not_ready(self) -> None:
        template = (PROJECT_ROOT / doctor.VERIFY_FILE).read_text(encoding="utf-8")
        verify_text, read = self.bind_read_receipt(
            template,
            construction_authorization="AUTH-0000",
            authorized_at="2027-01-01T00:01:30Z",
        )
        verify_text = replace_contract_table(
            verify_text,
            "## Verification matrix",
            self._VERIFICATION_MATRIX_HEADERS,
            [
                (
                    "EV-9001",
                    "FR-001",
                    "TASK-001",
                    "FR-001 primary outcome passes after deployment",
                    "EV-0001 local suite passed",
                    "DescribeStacks returned UPDATE_COMPLETE",
                    f"ARTIFACT: {self._DEPLOYMENT_ARTIFACT}; "
                    "ACCOUNT: 111122223333; REGION: us-west-2; "
                    "ENVIRONMENT: development",
                    "VERIFIED",
                )
            ],
        )
        old = {
            "basis": "REQ-0000 / DES-0000 / AUTH-0000",
            "deployment_authorization": "AUTH-0000",
        }
        rows = [
            self.deployment_row(
                evidence_id="EV-9721",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
                **old,
            ),
            self.deployment_row(
                evidence_id="EV-9722",
                phase="AWS-20",
                status="UNKNOWN",
                observed_at="2027-01-01T00:01:00Z",
                **old,
            ),
            self.deployment_row(
                evidence_id="EV-9723",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-01T00:02:00Z",
                read_authority=read,
                **old,
            ),
        ]
        verify_text = replace_contract_table(
            verify_text,
            doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
            doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS,
            rows,
        )
        common = dict(
            verify_text=verify_text,
            read_authority=None,
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            construction_authorization="AUTH-0001",
            envelope=self.deployment_envelope(),
            lane="fast-dev",
            artifact_binding=self._DEPLOYMENT_ARTIFACT,
            gate_b_authority_source="owner-message MSG-GATE-B-0001",
            gate_b_authorized_at="2026-12-31T23:59:59Z",
            restricted_closure=True,
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            release_evidence_cutoff="EV-9723",
        )
        rejected = doctor.derive_deployment_sequence_state(
            release_state="RELEASE_VERIFIED", **common
        )
        self.assertEqual(rejected["status"], "BLOCKED", rejected)
        accepted = doctor.derive_deployment_sequence_state(
            release_state="NOT_READY", **common
        )
        self.assertEqual(accepted["status"], "CONSUMED", accepted)

    def test_expired_blocked_acknowledgement_stops_without_release_loop(self) -> None:
        fixture = support.BootstrapDoctorTests()
        with tempfile.TemporaryDirectory() as directory:
            project = fixture.copy_project(Path(directory))
            manifest_path = project / "bootstrap.manifest.json"
            state_path = project / "bootstrap.yaml"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            manifest["bootstrap_version"] = state["bootstrap_version"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            refresh_control_hashes(project)
            fixture.approve_project(project)

            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"]["aws_lane"] = "explicit-gate"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            expired_at = "2026-07-18T18:00:00Z"
            prd_path = project / doctor.PRD_FILE
            prd_text = prd_path.read_text(encoding="utf-8")
            prd_text = set_table_value(
                prd_text,
                "## Document status",
                "## 1. Workload profile",
                "AWS lane",
                "`explicit-gate`",
            )
            envelope_values = {
                "Project AWS lane": "`explicit-gate`",
                "AWS boundary": "`MUTATE_LISTED_RESOURCES`",
                "AWS account": "`ACCOUNT: 111122223333`",
                "AWS role or profile": "`ROLE: fastlane-deployment-role`",
                "AWS Region": "`REGION: us-west-2`",
                "AWS environment": "`ENVIRONMENT: development; CLASS: NON_PRODUCTION`",
                "AWS stack or application": "`STACK: fastlane-stack`",
                "AWS resource allowlist": "`RESOURCES: fastlane-stack`",
                "AWS allowed operations": (
                    "`OPERATIONS: cloudformation:DescribeStacks, "
                    "cloudformation:CreateChangeSet, cloudformation:ExecuteChangeSet`"
                ),
                "AWS cost ceiling": "`USD: 20.00`",
                "AWS prohibited operations": (
                    "`PROHIBITED: wildcard resources, IAM broadening, destructive replacement`"
                ),
                "AWS artifact authorization and provenance": (
                    f"`EXACT_DIGEST: {self._DEPLOYMENT_ARTIFACT}`"
                ),
                "AWS rollback boundary": "`ROLLBACK: rollback fastlane-stack`",
                "AWS authorization validity": (
                    f"`Expires at {expired_at}; earlier completion: authorized AWS action ends`"
                ),
                "Authorization expiry or completion condition": (
                    f"`Expires at {expired_at}; earlier completion: release review`"
                ),
            }
            for field, value in envelope_values.items():
                prd_text = set_table_value(
                    prd_text,
                    "## 28. Construction envelope",
                    "## 29. Gate B owner authorization record",
                    field,
                    value,
                )
            prd_path.write_text(rebind_gate_b_envelope(prd_text), encoding="utf-8")

            verify_path = project / doctor.VERIFY_FILE
            verify_text = verify_path.read_text(encoding="utf-8")
            verify_text, deployment_digest = self.bind_explicit_deployment_receipt(
                verify_text,
                valid_until=expired_at,
                authorized_at="2026-07-17T18:00:00Z",
            )
            verify_text, read = self.bind_read_receipt(
                verify_text,
                authorized_at="2026-07-29T00:02:00Z",
            )
            verify_text = set_table_value(
                verify_text,
                "## Active evidence scope",
                "## Evidence status vocabulary",
                "Commit, tag, or image digest",
                f"`{self._DEPLOYMENT_ARTIFACT}`",
            )
            verify_text = verify_text.replace(
                "- Release state: `NOT_READY`",
                "- Release state: `NOT_READY`",
                1,
            ).replace(
                "- Active evidence cutoff: TODO",
                "- Active evidence cutoff: EV-9733",
                1,
            )
            rows = [
                self.deployment_row(
                    evidence_id="EV-9731",
                    phase="AWS-20",
                    status="STARTED",
                    observed_at="2026-07-17T18:30:00Z",
                    lane="explicit-gate",
                    receipt_digest=deployment_digest,
                    deployment_valid_until=expired_at,
                ),
                self.deployment_row(
                    evidence_id="EV-9732",
                    phase="AWS-20",
                    status="UNKNOWN",
                    observed_at="2026-07-29T00:01:00Z",
                    lane="explicit-gate",
                    receipt_digest=deployment_digest,
                    deployment_valid_until=expired_at,
                ),
                self.deployment_row(
                    evidence_id="EV-9733",
                    phase="AWS-30",
                    status="BLOCKED",
                    observed_at="2026-07-29T00:03:00Z",
                    lane="explicit-gate",
                    receipt_digest=deployment_digest,
                    deployment_valid_until=expired_at,
                    read_authority=read,
                ),
            ]
            verify_text = replace_contract_table(
                verify_text,
                doctor.AWS_DEPLOYMENT_EVIDENCE_HEADING,
                doctor.AWS_DEPLOYMENT_EVIDENCE_HEADERS,
                rows,
            )
            verify_path.write_text(verify_text, encoding="utf-8")
            result = doctor.inspect_project(project)
            self.assertTrue(result["ok"], result["diagnostics"])
            self.assertEqual(result["aws_deployment"]["status"], "CONSUMED")
            self.assertEqual(
                (result["lifecycle_state"], result["next_prompt"]),
                ("RELEASE_REVIEW_BLOCKED", "STOP"),
            )
            self.assertEqual(
                result["interaction"]["owner_action_kind"],
                "REVIEW_SAFETY_BLOCKER",
            )
            self.assertFalse(result["interaction"]["automatic_continuation_allowed"])
            self.assert_no_closure_authority(result)
            self.assert_no_external_mutation_authority(result)

            verify_text = verify_text.replace(
                "- AWS lifecycle intent: `NONE`\n"
                "- AWS lifecycle intent source: `NONE`\n"
                "- AWS lifecycle intent recorded at: `NONE`",
                "- AWS lifecycle intent: `RESIDUAL_REVIEW`\n"
                "- AWS lifecycle intent source: `owner-message MSG-AWS-LIFECYCLE-0001`\n"
                "- AWS lifecycle intent recorded at: `2026-07-29T12:00:00Z`",
                1,
            )
            verify_path.write_text(verify_text, encoding="utf-8")
            residual = doctor.inspect_project(project)
            self.assertTrue(residual["ok"], residual["diagnostics"])
            self.assertEqual(
                (residual["lifecycle_state"], residual["next_prompt"]),
                ("AWS_RESIDUAL_REVIEW", "AWS-40"),
                residual,
            )
            self.assertEqual(
                residual["aws_lifecycle_intent"]["provenance_status"], "CURRENT"
            )
            self.assertFalse(residual["aws_lifecycle_intent"]["authorizes_aws_access"])
            self.assertFalse(residual["aws_lifecycle_intent"]["authorizes_mutation"])
            self.assertFalse(residual["aws_lifecycle_intent_write_authority"]["valid"])
            self.assert_no_external_mutation_authority(residual)


if __name__ == "__main__":
    unittest.main()
