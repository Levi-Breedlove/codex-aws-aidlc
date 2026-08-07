from __future__ import annotations

import ast
import dataclasses
import inspect
import unittest
from pathlib import Path

from scripts.fastlane_engine.authority.aws import derive_external_authority
from scripts.fastlane_engine.authority.models import (
    AuthorityEvaluationInput,
    ConstructionWriteInput,
    GateBAuthorityBounds,
    LifecycleIntentWriteInput,
    PendingGateReceiptInput,
)
from scripts.fastlane_engine.authority.receipts import current_gate_receipt_contract
from scripts.fastlane_engine.authority.write import (
    derive_aws_lifecycle_intent_write_authority,
    derive_write_authority,
)
from scripts.fastlane_engine.orchestration import normalize_gate_b_authority_bounds


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_ROOT = ROOT / "scripts" / "fastlane_engine" / "authority"


class EngineAuthorityTests(unittest.TestCase):
    def test_authority_imports_no_sibling_lifecycle_domain(self) -> None:
        siblings = {"aws", "define", "deliver", "design"}
        failures: list[str] = []
        for path in sorted(AUTHORITY_ROOT.glob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level >= 2:
                    imported = (node.module or "").split(".", 1)[0]
                    if imported in siblings:
                        failures.append(f"{relative}: imports sibling {node.module}")
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "import_module"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    target = node.args[0].value.strip(".").split(".", 1)[0]
                    if target in siblings:
                        failures.append(
                            f"{relative}: loads sibling {node.args[0].value}"
                        )
        self.assertEqual(failures, [])

    def test_authority_core_accepts_normalized_inputs_only(self) -> None:
        self.assertEqual(
            list(inspect.signature(derive_external_authority).parameters)[:4],
            [
                "authority_input",
                "bounds",
                "lane",
                "construction_authorization",
            ],
        )
        self.assertNotIn(
            "envelope", inspect.signature(derive_external_authority).parameters
        )
        self.assertEqual(
            list(inspect.signature(derive_write_authority).parameters),
            ["write_input", "construction_authorization"],
        )
        self.assertEqual(
            list(inspect.signature(current_gate_receipt_contract).parameters),
            ["receipt_input"],
        )
        self.assertEqual(
            list(
                inspect.signature(
                    derive_aws_lifecycle_intent_write_authority
                ).parameters
            ),
            ["write_input"],
        )

    def test_authority_input_models_are_deeply_stable_at_the_boundary(self) -> None:
        models = (
            AuthorityEvaluationInput,
            ConstructionWriteInput,
            GateBAuthorityBounds,
            LifecycleIntentWriteInput,
            PendingGateReceiptInput,
        )
        for model in models:
            with self.subTest(model=model.__name__):
                self.assertTrue(dataclasses.is_dataclass(model))
                self.assertTrue(model.__dataclass_params__.frozen)

        envelope = {
            "AWS boundary": "READ_ONLY",
            "AWS account": "ACCOUNT: 111122223333",
            "AWS Region": "REGION: us-west-2",
            "AWS role or profile": "ROLE: review-role",
            "AWS resource allowlist": "RESOURCES: example-stack",
            "AWS allowed operations": "OPERATIONS: cloudformation:DescribeStacks",
            "AWS artifact authorization and provenance": (
                "NOT_APPLICABLE — read-only planning"
            ),
            "Authorization expiry or completion condition": (
                "Expires at 2099-01-01T00:00:00Z; earlier completion: owner revokes"
            ),
            "AWS stack or application": "STACK: example-stack",
        }
        bounds = normalize_gate_b_authority_bounds(
            envelope,
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
            active_artifact="sha256:" + "a" * 64,
        )
        envelope["AWS account"] = "ACCOUNT: 123456789012"
        self.assertEqual(bounds.account, "111122223333")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            bounds.account = "123456789012"  # type: ignore[misc]

    def test_normalized_write_and_receipt_outputs_preserve_public_shape(self) -> None:
        write = derive_write_authority(
            ConstructionWriteInput(
                has_errors=False,
                approved_write_roots=("app/**",),
                exclusions=("docs/project/**",),
                active_task="TASK-0001",
                active_task_write_set=("app/example.py",),
            ),
            "AUTH-0001",
        )
        self.assertEqual(write["authorization_id"], "AUTH-0001")
        self.assertEqual(write["approved_write_roots"], ["app/**"])
        self.assertEqual(write["active_task_write_set"], ["app/example.py"])

        contract = current_gate_receipt_contract(
            PendingGateReceiptInput(
                gate="GATE_B",
                lifecycle_state="WAITING_GATE_B",
                next_prompt="DESIGN-20",
                owner_action_kind="APPROVE_GATE_B",
                requirements_revision="REQ-0001",
                design_revision="DES-0001",
                construction_authorization="AUTH-0001",
                construction_envelope_sha256="sha256:" + "b" * 64,
            )
        )
        self.assertEqual(contract["gate"], "GATE_B")
        self.assertEqual(
            contract["expected_receipt"].splitlines()[-1],
            "Approver: <name/handle>",
        )


if __name__ == "__main__":
    unittest.main()
