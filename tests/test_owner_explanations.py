from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import bootstrap_doctor as doctor, fastlane_presenter as presenter
from scripts.fastlane_engine.api import (
    capture_project_snapshot,
    explain_project_validation,
)
from scripts.fastlane_engine.evaluation import thaw_evaluation_value
from scripts.fastlane_engine.orchestration import evaluate_project
from scripts.fastlane_engine.owner_explanations import derive_validation_explanation
from scripts.fastlane_engine.project_inspection import capture_engine_snapshot
from scripts.fastlane_engine.report import serialize_evaluation
from tests.test_bootstrap_doctor import (
    approve_gate_a,
    complete_design_contract,
    ready_task,
    set_table_value,
)
from tests.test_fastlane_presenter import report as presenter_report

ROOT = Path(__file__).resolve().parents[1]


class OwnerExplanationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prd = complete_design_contract(
            approve_gate_a((ROOT / "docs/project/PRD.md").read_text(encoding="utf-8"))
        )
        cls.prd = set_table_value(
            cls.prd,
            "## 28. Construction envelope",
            "## 29. Gate B owner authorization record",
            "Local command boundary",
            "ALLOW_PREFIXES: python -m unittest",
        )
        cls.design, issues = doctor.derive_design_contract(
            cls.prd, "DES-0001", required=True
        )
        assert not issues, issues
        cls.requirements, issues = doctor.derive_requirements_contract(
            cls.prd, "low", required=True, grandfather_current_gate_a=True
        )
        assert not issues, issues

    def make_explanation(self, root):
        records = {
            "docs/project/PRD.md": self.prd,
            "docs/project/TASKS.md": ready_task(),
            "docs/project/VERIFY.md": "## Task completion evidence\n\n| Evidence ID | Task | Command or observation | Result | Actor | Observed at | Commit / worktree / artifact | Durable source | Status |\n|---|---|---|---|---|---|---|---|---|\n",
        }
        for relative, text in records.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        snapshot = capture_project_snapshot(root, records, text_paths=records)
        report = presenter_report(
            owner_stage="DELIVER",
            state="RUNNING",
            route_reason_code="CONSTRUCTION_SINGLE",
            owner_action_required=False,
            owner_action_kind="NONE_CONTINUE_AUTOMATICALLY",
            automatic_continuation_allowed=True,
        )
        report["design_contract"] = self.design.to_dict()
        report["requirements_contract"] = self.requirements.to_dict()
        report.update(next_prompt="BUILD-10", lifecycle_state="CONSTRUCTION_SINGLE")
        evaluation = SimpleNamespace(
            ok=True,
            design={"design_contract": self.design.to_dict()},
            define={
                "requirements_contract": self.requirements.to_dict(),
                "coverage_plan": {"delivery_profile": "quick-mvp"},
            },
            deliver={
                "tasks": {"ready": 1, "ready_ids": ["TASK-001"], "active_ids": []},
                "evidence_state": "UNOBSERVED",
            },
            authority={"authorizations": {"construction": "NONE", "aws": "NONE"}},
            route={"next_prompt": "BUILD-10", "lifecycle_state": "CONSTRUCTION_SINGLE"},
            interaction=report["interaction"],
        )
        explanation = thaw_evaluation_value(
            derive_validation_explanation(snapshot, evaluation).values
        )
        return explanation, report, records

    def test_explanation_collects_profile_property_iac_and_ready_task_without_grant(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            explanation, report, records = self.make_explanation(root)
            self.assertEqual(explanation["errors"], [])
            self.assertEqual(explanation["route"]["next_prompt"], "BUILD-10")
            self.assertEqual(explanation["authority"]["authorizations"]["aws"], "NONE")
            kinds = {check["kind"] for check in explanation["checks"]}
            self.assertEqual(kinds, {"SPECIFICATION", "PROPERTY", "PROFILE", "TASK"})
            prop = next(
                check for check in explanation["checks"] if check["kind"] == "PROPERTY"
            )
            self.assertIn("run_target_time_bound", prop)
            self.assertIn("seed_or_reproduction_format", prop)
            sam = next(
                check
                for check in explanation["checks"]
                if check["command"].startswith("sam validate")
            )
            self.assertEqual(
                sam["evidence_destination"],
                "docs/project/VERIFY.md#iac-validation-evidence",
            )
            self.assertFalse(sam["declared_local_prefix_match"])
            self.assertIn(sam["id"], explanation["permission_conflicts"])
            self.assertTrue(
                any(
                    check["requires_separate_aws_authority"]
                    for check in explanation["checks"]
                )
            )
            self.assertTrue(
                all(
                    check["execution_performed"] is False
                    for check in explanation["checks"]
                )
            )
            self.assertEqual(
                sam["source"]["source_sha256"],
                "sha256:"
                + hashlib.sha256(
                    (root / "docs/project/PRD.md").read_bytes()
                ).hexdigest(),
            )
            self.assertEqual(
                {path: (root / path).read_text(encoding="utf-8") for path in records},
                records,
            )
            rendered = presenter.render_validation_explanation(report, explanation)
            self.assertIn("sam validate", rendered)
            self.assertIn("execute the next ready local task", rendered)
            self.assertNotIn("resume planning", rendered)
            self.assertNotIn("TASK-10", rendered)

    def test_public_explanation_uses_real_ready_task_ids_without_mutation(self):
        from tests.test_bootstrap_doctor import (
            BootstrapDoctorTests,
            MODERN_TASK_REQUIREMENT_TRACE,
            property_execution_projection,
            refresh_document_summaries,
        )

        fixture = BootstrapDoctorTests()
        with tempfile.TemporaryDirectory() as directory:
            project = fixture.copy_project(Path(directory))
            fixture.approve_project(project)
            fixture.set_non_material_req_evidence(project)
            fixture.initialize_task_plan(
                project,
                ready_task(
                    requirements=MODERN_TASK_REQUIREMENT_TRACE + "; PROP-001",
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    command="python -m unittest tests.test_properties",
                    property_projection=property_execution_projection(),
                ),
            )
            refresh_document_summaries(project)
            paths = [
                project / "docs/project" / name
                for name in ("PRD.md", "TASKS.md", "VERIFY.md", "RUNBOOK.md")
            ] + [project / "bootstrap.yaml"]
            before = {path: path.read_bytes() for path in paths}
            observed = explain_project_validation(project)
            self.assertTrue(observed["report"]["ok"], observed["report"]["diagnostics"])
            self.assertEqual(observed["report"]["tasks"]["ready"], 1)
            self.assertEqual(observed["report"]["tasks"]["ready_ids"], ["TASK-001"])
            checks = [
                row
                for row in observed["validation_explanation"]["checks"]
                if row["kind"] == "TASK"
            ]
            self.assertTrue(checks)
            self.assertEqual({row["selected_task_state"] for row in checks}, {"READY"})
            self.assertTrue(all(row["execution_performed"] is False for row in checks))
            self.assertEqual({path: path.read_bytes() for path in paths}, before)

    def test_presenter_rejects_mismatched_current_basis(self):
        with tempfile.TemporaryDirectory() as temporary:
            explanation, report, _ = self.make_explanation(Path(temporary))
            for key in ("design_digest", "requirements_digest"):
                changed = {**explanation, key: "sha256:" + "f" * 64}
                with (
                    self.subTest(key=key),
                    self.assertRaises(presenter.PresentationError),
                ):
                    presenter.render_validation_explanation(report, changed)
            for key, value in (
                ("next_prompt", "TASK-10"),
                ("lifecycle_state", "WAITING_GATE_A"),
            ):
                changed = {**explanation, "route": {**explanation["route"], key: value}}
                with (
                    self.subTest(key=key),
                    self.assertRaises(presenter.PresentationError),
                ):
                    presenter.render_validation_explanation(report, changed)

    def test_explicit_api_captures_once_and_preserves_the_default_report(self):
        snapshot = capture_engine_snapshot(ROOT)
        expected = serialize_evaluation(
            evaluate_project(ROOT, template_source=True, _observed_snapshot=snapshot)
        )
        with mock.patch(
            "scripts.fastlane_engine.project_inspection.capture_engine_snapshot",
            return_value=snapshot,
        ) as capture:
            result = explain_project_validation(ROOT, template_source=True)
        capture.assert_called_once_with(ROOT.resolve())
        self.assertEqual(result["report"], expected)


if __name__ == "__main__":
    unittest.main()
