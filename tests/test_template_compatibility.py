from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "model_roleplay_eval.py"
SPEC = importlib.util.spec_from_file_location("model_roleplay_eval", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
model_roleplay_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model_roleplay_eval)


class TemplateCompatibilityTests(unittest.TestCase):
    def test_setup_policy_matches_setup_first_runtime(self) -> None:
        security = (REPOSITORY_ROOT / "SECURITY.md").read_text(encoding="utf-8")
        dependency = (
            REPOSITORY_ROOT / "docs" / "DEPENDENCY-POLICY.md"
        ).read_text(encoding="utf-8")
        combined = security + "\n" + dependency
        stale_missing_policy = "Missing AWS Core never " + "blocks initialization"
        stale_optional_policy = "AWS Core is optional during " + "BOOT-00"
        self.assertNotIn(stale_missing_policy, combined)
        self.assertNotIn(stale_optional_policy, combined)
        expected = "Fresh templates require current official AWS Core before initialization"
        self.assertIn(expected, security)
        self.assertIn(expected, dependency)
        self.assertIn("Initialized projects skip the prerequisite gate", combined)

    def test_maintenance_governance_separates_read_edit_and_publish_authority(self) -> None:
        skill = (
            REPOSITORY_ROOT / ".agents/skills/maintain-fastlane/SKILL.md"
        ).read_text(encoding="utf-8")
        workflow = (REPOSITORY_ROOT / "docs/WORKFLOW.md").read_text(
            encoding="utf-8"
        )
        for mode in ("AUDIT", "PLAN", "IMPLEMENT", "PUBLISH"):
            self.assertIn(f"`{mode}`", skill)
            self.assertIn(f"`{mode}`", workflow)
        self.assertIn("Missing implementation scope stops", workflow)
        self.assertIn("publication never", workflow)
        self.assertNotIn("Delegate to `$fastlane`", skill)
        self.assertIn("pull requests targeting only that preview branch", workflow)
        self.assertIn("direct push to `fast-lane-maint` requires explicit emergency", workflow)
        self.assertIn("Force pushes and deletion", workflow)
        self.assertIn("separate repository-setting action", workflow)
        for check in (
            "safety-tests (3.11)",
            "safety-tests (3.12)",
            "safety-tests (3.13)",
            "windows-smoke",
            "macos-setup-smoke",
        ):
            self.assertIn(f"`{check}`", workflow)

    def test_model_roleplay_plan_is_complete_and_non_operational(self) -> None:
        plan = model_roleplay_eval.plan_payload()
        self.assertEqual(len(plan["scenarios"]), 13)
        self.assertEqual(set(plan["criteria"]), set(model_roleplay_eval.CRITERIA))
        self.assertFalse(plan["constraints"]["ordinary_ci_invokes_live_model"])
        self.assertTrue(plan["constraints"]["live_execution_is_opt_in"])
        self.assertFalse(plan["constraints"]["release_readiness_claimed_by_scorer"])
        self.assertEqual(plan["schema_version"], 4)
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "subprocess",
            "OPENAI_API_KEY",
            "AWS_ACCESS_KEY",
            "boto3",
            "urllib",
            "socket",
        ):
            self.assertNotIn(forbidden, source)

    def test_model_roleplay_score_requires_bundle_and_revision_pins(self) -> None:
        parser = model_roleplay_eval.build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["score", "--input", "manifest.json", "--json"])
        args = parser.parse_args(
            [
                "score",
                "--input",
                "manifest.json",
                "--bundle-root",
                "evidence",
                "--expected-commit",
                "a" * 40,
                "--expected-prompt-contract-sha256",
                "sha256:" + "b" * 64,
                "--json",
            ]
        )
        self.assertEqual(args.command, "score")

    def test_model_roleplay_schema_three_requires_explicit_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result, passed = model_roleplay_eval.score_payload(
                {"schema_version": 3, "evaluation_mode": "RELEASE", "runs": []},
                bundle_root=Path(temporary),
                expected_commit="a" * 40,
                expected_prompt_contract_sha256="sha256:" + "b" * 64,
            )
        self.assertFalse(passed)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any("cannot be auto-converted" in error for error in result["errors"])
        )

    def test_model_roleplay_score_rejects_missing_scenarios(self) -> None:
        commit = "a" * 40
        prompt_digest = "sha256:" + "b" * 64
        with tempfile.TemporaryDirectory() as temporary:
            result, passed = model_roleplay_eval.score_payload(
                {
                    "schema_version": model_roleplay_eval.SCHEMA_VERSION,
                    "evaluation_mode": "DEVELOPMENT",
                    "expected_commit": commit,
                    "prompt_contract_sha256": prompt_digest,
                    "runs": [],
                },
                bundle_root=Path(temporary),
                expected_commit=commit,
                expected_prompt_contract_sha256=prompt_digest,
            )
        self.assertFalse(passed)
        for scenario in model_roleplay_eval.SCENARIOS:
            self.assertTrue(
                any(scenario["id"] in error for error in result["errors"])
            )


if __name__ == "__main__":
    unittest.main()
