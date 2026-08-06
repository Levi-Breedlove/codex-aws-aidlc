from __future__ import annotations

import ast
import dataclasses
import unittest
from pathlib import Path

from scripts import bootstrap_doctor as doctor
from scripts.fastlane_engine import api
from scripts.fastlane_engine import aws
from scripts.fastlane_engine.aws import deployment


ROOT = Path(__file__).resolve().parents[1]
AWS_ROOT = ROOT / "scripts" / "fastlane_engine" / "aws"


class EngineAwsTests(unittest.TestCase):
    def test_doctor_facade_uses_pure_aws_evidence_and_lifecycle_contracts(self) -> None:
        direct = {
            "parse_aws_core_evidence": aws.parse_aws_core_evidence,
            "aws_core_phase_evidence_issues": aws.aws_core_phase_evidence_issues,
            "derive_aws_core_observed_usage": aws.derive_aws_core_observed_usage,
            "derive_teardown_route": aws.derive_teardown_route,
            "derive_aws_residual_disposition": aws.derive_aws_residual_disposition,
            "derive_aws_delivery_route": aws.derive_aws_delivery_route,
            "derive_aws_execution_projection": doctor.derive_aws_execution_projection,
        }
        for name, implementation in direct.items():
            if name == "derive_aws_execution_projection":
                self.assertEqual(
                    implementation(
                        {},
                        release_decision="NOT_READY",
                        guidance_ready=False,
                        read_authority=None,
                        preflight={},
                    ),
                    aws.derive_aws_execution_projection(
                        {},
                        release_decision="NOT_READY",
                        guidance_ready=False,
                        read_authority=None,
                        preflight={},
                    ),
                )
            else:
                self.assertIs(getattr(doctor, name), implementation, name)
        self.assertIs(doctor.AwsCoreEvidenceRow, aws.AwsCoreEvidenceRow)
        self.assertIs(
            doctor._format_deployment_read_provenance,
            deployment._format_deployment_read_provenance,
        )

    def test_state_machine_facades_preserve_empty_journal_results(self) -> None:
        verify_text = (ROOT / "docs" / "project" / "VERIFY.md").read_text(
            encoding="utf-8"
        )
        policy = doctor._aws_authority_policy()
        deployment_kwargs = {
            "requirements_revision": "REQ-0000",
            "design_revision": "DES-0000",
            "construction_authorization": "NONE",
            "envelope": {},
            "lane": None,
            "artifact_binding": "NONE",
        }
        self.assertEqual(
            doctor.derive_deployment_sequence_state(
                verify_text, None, **deployment_kwargs
            ),
            api.derive_deployment_sequence_state(
                verify_text, None, policy=policy, **deployment_kwargs
            ),
        )
        teardown_kwargs = {
            "requirements_revision": "REQ-0000",
            "design_revision": "DES-0000",
            "construction_authorization": "NONE",
            "envelope": {},
        }
        self.assertEqual(
            doctor.derive_teardown_sequence_state(verify_text, None, **teardown_kwargs),
            api.derive_teardown_sequence_state(
                verify_text, None, policy=policy, **teardown_kwargs
            ),
        )

    def test_aws_policy_and_rows_are_immutable_non_authoritative_inputs(self) -> None:
        policy = doctor._aws_authority_policy()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            policy.marked_receipt = lambda _text, _gate: ""  # type: ignore[misc]
        row = aws.AwsCoreEvidenceRow(*(["NONE"] * 19))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            row.phase = "AWS-10"  # type: ignore[misc]

    def test_aws_modules_have_no_observation_or_sibling_domain_imports(self) -> None:
        forbidden_import_roots = {
            "boto3",
            "botocore",
            "http",
            "os",
            "pathlib",
            "requests",
            "shutil",
            "socket",
            "subprocess",
            "tempfile",
            "time",
            "urllib",
        }
        forbidden_calls = {
            "__import__",
            "eval",
            "exec",
            "open",
            "read_bytes",
            "read_text",
            "write_bytes",
            "write_text",
        }
        sibling_domains = {"authority", "define", "deliver", "design"}
        failures: list[str] = []
        for path in sorted(AWS_ROOT.glob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            self.assertTrue(ast.get_docstring(tree), relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".", 1)[0] in forbidden_import_roots:
                            failures.append(f"{relative}: imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.split(".", 1)[0] in forbidden_import_roots:
                        failures.append(f"{relative}: imports {module}")
                    if any(part in sibling_domains for part in module.split(".")):
                        failures.append(f"{relative}: imports sibling {module}")
                elif isinstance(node, ast.Call):
                    if (
                        isinstance(node.func, ast.Name)
                        and node.func.id in forbidden_calls
                    ):
                        failures.append(f"{relative}: calls {node.func.id}")
                    elif (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr in forbidden_calls
                    ):
                        failures.append(f"{relative}: calls {node.func.attr}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
