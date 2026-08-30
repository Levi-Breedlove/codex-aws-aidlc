from __future__ import annotations

import contextlib
import importlib.util
import io
import json
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
        dependency = (REPOSITORY_ROOT / "docs" / "DEPENDENCY-POLICY.md").read_text(
            encoding="utf-8"
        )
        combined = security + "\n" + dependency
        stale_missing_policy = "Missing AWS Core never " + "blocks initialization"
        stale_optional_policy = "AWS Core is optional during " + "BOOT-00"
        self.assertNotIn(stale_missing_policy, combined)
        self.assertNotIn(stale_optional_policy, combined)
        expected = (
            "Fresh templates require current official AWS Core before initialization"
        )
        self.assertIn(expected, security)
        self.assertIn(expected, dependency)
        self.assertIn("Initialized projects skip the prerequisite gate", combined)

    def test_maintenance_governance_separates_read_edit_and_publish_authority(
        self,
    ) -> None:
        skill = (
            REPOSITORY_ROOT / ".agents/skills/maintain-fastlane/SKILL.md"
        ).read_text(encoding="utf-8")
        qualification = (
            REPOSITORY_ROOT
            / ".agents/skills/maintain-fastlane/references/qualification.md"
        ).read_text(encoding="utf-8")
        security = (REPOSITORY_ROOT / "SECURITY.md").read_text(encoding="utf-8")
        skill_words = " ".join(skill.split())
        for mode in ("AUDIT", "PLAN", "IMPLEMENT", "PUBLISH"):
            self.assertIn(f"`{mode}`", skill)
        self.assertIn("If any field is missing", skill_words)
        self.assertIn("Publication authority never implies", skill_words)
        self.assertNotIn("Delegate to `$fastlane`", skill)
        self.assertIn("pull request targeting only `fast-lane`", skill_words)
        self.assertIn(
            "direct push to `fast-lane` requires explicit emergency", skill_words
        )
        self.assertIn("Never force-push or delete", skill_words)
        self.assertIn("live `fast-lane` customer branch", skill_words)
        self.assertIn("The protected `fast-lane-foundation` branch", skill)
        self.assertIn("protected `fast-lane-foundation` branch", security)
        for stale_branch in ("`fast-lane-maint`", "`legacy`", "`Legacy`"):
            self.assertNotIn(stale_branch, skill)
            self.assertNotIn(stale_branch, security)
        self.assertIn("separate repository-setting action", skill_words)
        self.assertIn(
            "intentionally ships no recurring GitHub Actions workflow", skill_words
        )
        self.assertIn("exact-head local release qualification", skill_words)
        self.assertIn("is not a GitHub status check", skill_words)
        self.assertIn("must not require retired workflow contexts", skill_words)
        self.assertIn("compatibility contract", qualification)
        self.assertIn("must name each advertised combination", qualification)
        self.assertIn(
            "must never be described as cross-platform coverage", qualification
        )
        for retired_check in (
            "safety-tests (3.11)",
            "safety-tests (3.12)",
            "safety-tests (3.13)",
            "windows-smoke",
            "macos-setup-smoke",
        ):
            self.assertNotIn(retired_check, skill)

    def test_maintenance_preflight_is_read_only_and_routed_only_to_maintenance(
        self,
    ) -> None:
        skill = (
            REPOSITORY_ROOT / ".agents/skills/maintain-fastlane/SKILL.md"
        ).read_text(encoding="utf-8")
        script = (REPOSITORY_ROOT / "scripts/maintenance_preflight.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("maintenance_preflight.py", skill)
        self.assertIn(
            "Validate a Fastlane maintenance scope contract read-only", script
        )
        for forbidden in (
            "boto3",
            "openai",
            "AWS_ACCESS_KEY",
            "codex login",
            "git push",
        ):
            self.assertNotIn(forbidden, script)

    def test_deterministic_workflow_corpus_is_the_mandatory_baseline(self) -> None:
        evaluation = (
            REPOSITORY_ROOT
            / ".agents/skills/maintain-fastlane/references/evaluation.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Golden Project Corpus", evaluation)
        self.assertIn("tests/test_product_journeys.py", evaluation)
        self.assertRegex(evaluation, r"mandatory deterministic\s+workflow baseline")

    def test_fastlane_13_completion_policy_names_each_evidence_level(self) -> None:
        qualification = (
            REPOSITORY_ROOT
            / ".agents/skills/maintain-fastlane/references/qualification.md"
        ).read_text(encoding="utf-8")
        evaluation = (
            REPOSITORY_ROOT
            / ".agents/skills/maintain-fastlane/references/evaluation.md"
        ).read_text(encoding="utf-8")
        combined = " ".join((qualification + "\n" + evaluation).split())
        for claim in (
            "FRAMEWORK_RELEASE_QUALIFIED",
            "PROJECT_TARGET_COMPLETE(target)",
            "AWS_LANE_FIELD_QUALIFIED(lane)",
            "PRODUCT_FIELD_VALIDATED",
        ):
            self.assertIn(f"`{claim}`", combined)
        for target, evidence in (
            ("LOCAL", "E2"),
            ("AWS_READ", "E2 + E3"),
            ("DEPLOYED", "E2 + E3 + E4"),
            ("RECOVERY", "E2 + E3 + E4 + E5"),
        ):
            self.assertIn(f"`{target}` requires {evidence}", combined)
        self.assertIn("5-8 first-time, non-author participants", combined)
        self.assertIn("at least 80 percent", combined)
        self.assertIn("at least 4/5", combined)
        self.assertIn("No safety-critical misunderstanding", combined)
        self.assertIn("AWS_SAM_CLOUDFORMATION_NONPROD", combined)
        self.assertIn("`us-west-2`", combined)
        self.assertIn("USD 20.00", combined)
        self.assertIn("no open P0/P1 truth defect", combined)
        self.assertIn("no expired complexity exception", combined)
        self.assertIn("creates no lifecycle gate", combined)
        self.assertIn("does not change task-level `DONE`", combined)
        self.assertIn("teardown-only evidence does not qualify `RECOVERY`", combined)

    def test_field_qualification_replaces_fixed_canary_subsystem(self) -> None:
        retired_doc = "AWS-" + "CANARY"
        retired_script = "aws_" + "canary_eval"
        for relative in (
            "docs/" + retired_doc + ".md",
            "scripts/" + retired_script + ".py",
            "tests/test_" + retired_script + ".py",
        ):
            self.assertFalse((REPOSITORY_ROOT / relative).exists())
        manifest = json.loads(
            (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        inventory = json.dumps(manifest, sort_keys=True)
        self.assertNotIn(retired_doc, inventory)
        self.assertNotIn(retired_script, inventory)
        evaluation = (
            REPOSITORY_ROOT
            / ".agents/skills/maintain-fastlane/references/evaluation.md"
        ).read_text(encoding="utf-8")
        evaluation_words = " ".join(evaluation.split())
        self.assertIn("Codex selects the smallest disposable", evaluation)
        self.assertIn("using current AWS Core guidance", evaluation)
        self.assertNotIn("AWS Core selects the smallest disposable", evaluation)
        self.assertIn(
            "AWS Core does not choose the product architecture or grant authority",
            evaluation_words,
        )
        self.assertIn(
            "The owner authorizes; IAM enforces; observed evidence proves",
            evaluation_words,
        )
        self.assertIn(
            "introduces no scorer, lifecycle stage, gate, or routine",
            evaluation_words,
        )
        self.assertIn(
            "AWS-10, AWS-20, AWS-30, AWS-40, and AWS-50",
            evaluation_words,
        )

    def test_model_roleplay_plan_is_complete_and_non_operational(self) -> None:
        plan = model_roleplay_eval.plan_payload()
        self.assertEqual(len(plan["scenarios"]), 25)
        scenario_ids = {scenario["id"] for scenario in plan["scenarios"]}
        self.assertTrue(
            {
                "one-question-intake",
                "onboarding-project-ready",
                "consultative-intake",
                "source-assisted-define",
                "answer-confirmation",
                "gate-a-brief-comprehension",
                "gate-b-brief-comprehension",
                "source-navigation",
                "project-diagram-understanding",
                "gate-correction",
                "resume-without-repetition",
                "agent-owned-correction",
            }.issubset(scenario_ids)
        )
        self.assertEqual(set(plan["criteria"]), set(model_roleplay_eval.CRITERIA))
        self.assertFalse(plan["constraints"]["ordinary_ci_invokes_live_model"])
        self.assertTrue(plan["constraints"]["live_execution_is_opt_in"])
        self.assertFalse(plan["constraints"]["release_readiness_claimed_by_scorer"])
        self.assertEqual(plan["schema_version"], 5)
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

    def test_model_roleplay_schema_four_requires_explicit_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result, passed = model_roleplay_eval.score_payload(
                {"schema_version": 4, "evaluation_mode": "RELEASE", "runs": []},
                bundle_root=Path(temporary),
                expected_commit="a" * 40,
                expected_prompt_contract_sha256="sha256:" + "b" * 64,
            )
        self.assertFalse(passed)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any(
                "required Fastlane 1.1 customer-experience scenarios" in error
                for error in result["errors"]
            )
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
            self.assertTrue(any(scenario["id"] in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
