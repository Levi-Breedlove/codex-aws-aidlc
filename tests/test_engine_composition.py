from __future__ import annotations

import ast
import builtins
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts import bootstrap_doctor as doctor
from scripts.fastlane_engine import api
from scripts.fastlane_engine.evaluation import EngineEvaluation
from scripts.fastlane_engine.report import serialize_evaluation


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "scripts" / "fastlane_engine" / "report.py"
COMPOSITION_PATH = ROOT / "scripts" / "fastlane_engine" / "composition.py"


def synthetic_schema2_report() -> dict[str, object]:
    """Independently authored serializer fixture with every public report field."""

    return {
        "schema_version": 2,
        "bootstrap_version": "1.2.22",
        "status": "READY",
        "classification": "ACTIVE_GREENFIELD",
        "ok": True,
        "lifecycle_state": "INTAKE_REQUIRED",
        "resume_safe": True,
        "next_prompt": "INTAKE-10",
        "interaction": {"owner_action_kind": "ANSWER_OPEN_DECISIONS"},
        "remediation": {"responsible_party": "OWNER"},
        "context_plan": {"status": "CURRENT", "requests": []},
        "project": {"name": "Synthetic"},
        "git_baseline": {"status": "CLEAN"},
        "aws_access": "NOT_USED",
        "aws_mode_boundary": {"mode": "NONE"},
        "gates": {"gate_a": "BLOCKED", "gate_b": "BLOCKED"},
        "evidence_state": "NOT_READY",
        "release_evidence_cutoff": "NONE",
        "aws_core_evidence": {"aws_execution_planning": "BLOCKED"},
        "authorizations": {"construction": "NONE", "aws": "NONE"},
        "write_authority": {"valid": False},
        "deployment_journal_closure_authority": {"valid": False},
        "teardown_journal_closure_authority": {"valid": False},
        "aws_lifecycle_intent": {"value": "NONE"},
        "aws_residual_disposition": {"status": "NOT_APPLICABLE"},
        "aws_lifecycle_intent_write_authority": {"valid": False},
        "external_authority": {"kind": "NONE", "validity": "NONE"},
        "hook_constraints": {"GitHub boundary": "NONE"},
        "aws_action_transition": {"status": "NOT_ACTIVE"},
        "aws_execution": {"active": False},
        "aws_deployment": {"status": "NOT_ACTIVE"},
        "aws_teardown": {"status": "NOT_ACTIVE"},
        "basis": {"requirements_revision": "REQ-0001"},
        "document_summaries": {"schema_version": 1, "documents": []},
        "owner_decision_brief": {"status": "NOT_READY"},
        "owner_decision_inventory": {"gate_a": [], "gate_b": []},
        "owner_answer_confirmation": {"status": "NOT_READY"},
        "intake_foundation": {"status": "INCOMPLETE"},
        "requirements_contract": {"status": "INCOMPLETE"},
        "coverage_plan": {"status": "INCOMPLETE"},
        "design_contract": {"status": "INCOMPLETE"},
        "adr_rationale": {"status": "NOT_APPLICABLE"},
        "tasks": {"total": 0, "ready_ids": []},
        "diagnostics": [
            {
                "diagnostic_id": "DGN-0001",
                "code": "SYNTHETIC",
                "severity": "WARNING",
                "message": "Synthetic fixture",
            }
        ],
    }


class EngineCompositionTests(unittest.TestCase):
    def test_public_evaluation_serializes_to_the_existing_report(self) -> None:
        evaluation = api.evaluate_project(ROOT, template_source=True)
        self.assertIsInstance(evaluation, EngineEvaluation)
        expected = api.inspect_project(ROOT, template_source=True)
        self.assertEqual(serialize_evaluation(evaluation), expected)
        self.assertEqual(expected, doctor.inspect_project(ROOT, template_source=True))

    def test_evaluation_is_deeply_immutable(self) -> None:
        evaluation = EngineEvaluation.from_schema2(synthetic_schema2_report())
        with self.assertRaises(TypeError):
            evaluation.project["name"] = "Changed"  # type: ignore[index]
        with self.assertRaises(TypeError):
            evaluation.aws["aws_deployment"]["status"] = "SUCCEEDED"  # type: ignore[index]
        with self.assertRaises(AttributeError):
            evaluation.diagnostics.append({})  # type: ignore[attr-defined]
        with self.assertRaises(AttributeError):
            evaluation.status = "BLOCKED"  # type: ignore[misc]

    def test_report_serializes_without_observation_clock_or_policy(self) -> None:
        source = synthetic_schema2_report()
        evaluation = EngineEvaluation.from_schema2(source)
        unavailable = AssertionError("serializer attempted a prohibited dependency")
        with (
            mock.patch.object(builtins, "open", side_effect=unavailable),
            mock.patch.object(Path, "read_text", side_effect=unavailable),
            mock.patch.object(subprocess, "run", side_effect=unavailable),
            mock.patch.object(time, "time", side_effect=unavailable),
        ):
            observed = serialize_evaluation(evaluation)
        self.assertEqual(observed, source)
        self.assertIsNot(observed, source)
        self.assertIsNot(observed["project"], source["project"])

    def test_report_module_imports_only_the_evaluation_model(self) -> None:
        tree = ast.parse(REPORT_PATH.read_text(encoding="utf-8"))
        relative_imports = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level
        }
        self.assertEqual(relative_imports, {"evaluation"})
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertFalse(
            called
            & {
                "open",
                "run",
                "time",
                "derive_route",
                "derive_remediation",
                "derive_interaction",
                "derive_external_authority",
                "resolve_context_packet",
                "project_document_summaries",
            }
        )

    def test_composition_builds_evaluation_before_schema_serialization(self) -> None:
        tree = ast.parse(COMPOSITION_PATH.read_text(encoding="utf-8"))
        schema_round_trips = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "from_schema2"
        }
        self.assertEqual(schema_round_trips, set())


if __name__ == "__main__":
    unittest.main()
