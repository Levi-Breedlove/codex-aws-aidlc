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
SPEC = importlib.util.spec_from_file_location(
    "model_roleplay_eval_preview", SCRIPT_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
model_roleplay_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model_roleplay_eval)


EXPECTED_COMMIT = "a" * 40
PROMPT_DIGEST = "sha256:" + "b" * 64
EXPECTED_PROMPT_CONTRACT_PATHS = (
    "AGENTS.md",
    ".codex/hooks/AGENTS.md",
    "docs/project/AGENTS.md",
    "infrastructure/AGENTS.md",
    "scripts/AGENTS.md",
    "scripts/fastlane_engine/AGENTS.md",
    "tests/AGENTS.md",
    ".agents/skills/fastlane/SKILL.md",
    ".agents/skills/fastlane/agents/openai.yaml",
    ".agents/skills/fastlane/references/define.md",
    ".agents/skills/fastlane/references/source-assisted-define.md",
    ".agents/skills/fastlane/references/design.md",
    ".agents/skills/fastlane/references/diagram-patterns.md",
    ".agents/skills/fastlane/references/deliver.md",
    ".agents/skills/fastlane/references/owner-responses.md",
    ".agents/skills/fastlane/references/authorization-receipts.md",
    ".agents/skills/explain-fastlane/SKILL.md",
    ".agents/skills/explain-fastlane/agents/openai.yaml",
    ".agents/skills/operate-fastlane-aws/SKILL.md",
    ".agents/skills/operate-fastlane-aws/agents/openai.yaml",
    "prompts/CODEX-PROMPTS.md",
)


def write_artifact(
    root: Path, relative: str, payload: dict[str, object]
) -> dict[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(content)
    return {"path": relative, "sha256": model_roleplay_eval._digest(content)}


def rewrite_artifact(
    root: Path,
    reference: dict[str, str],
    update: object,
) -> dict[str, object]:
    path = root / reference["path"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    update(payload)
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(content)
    reference["sha256"] = model_roleplay_eval._digest(content)
    return payload


class ModelRoleplayEvaluationTests(unittest.TestCase):
    def write_prompt_contract_root(self, root: Path, newline: bytes = b"\r\n") -> None:
        for index, relative in enumerate(EXPECTED_PROMPT_CONTRACT_PATHS):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"{index}:{relative}".encode("utf-8") + newline)

    def binding(self, scenario: str, iteration: int) -> dict[str, object]:
        return {
            "schema_version": model_roleplay_eval.ARTIFACT_SCHEMA_VERSION,
            "scenario_id": scenario,
            "iteration": iteration,
            "expected_commit": EXPECTED_COMMIT,
            "prompt_contract_sha256": PROMPT_DIGEST,
            "model_reference": "observed-model-family",
            "credentials_inspected": False,
            "aws_account_accessed": False,
        }

    def safe_payload(self, root: Path, mode: str = "RELEASE") -> dict[str, object]:
        runs: list[dict[str, object]] = []
        rater_ids = (
            ("rater-alpha", "rater-beta") if mode == "RELEASE" else ("rater-alpha",)
        )
        for scenario in model_roleplay_eval.SCENARIOS:
            scenario_id = scenario["id"]
            for iteration in range(1, model_roleplay_eval.REQUIRED_RUNS + 1):
                binding = self.binding(scenario_id, iteration)
                transcript = write_artifact(
                    root,
                    f"transcripts/{scenario_id}-{iteration}.json",
                    {
                        **binding,
                        "artifact_type": "MODEL_TRANSCRIPT",
                        "turns": [
                            {"role": "owner", "text": "Synthetic owner request."},
                            {"role": "codex", "text": "Synthetic bounded response."},
                        ],
                    },
                )
                scorecards = []
                for rater_id in rater_ids:
                    scorecards.append(
                        write_artifact(
                            root,
                            f"scorecards/{scenario_id}-{iteration}-{rater_id}.json",
                            {
                                **binding,
                                "artifact_type": "RATER_SCORECARD",
                                "transcript_sha256": transcript["sha256"],
                                "rater_id": rater_id,
                                "scores": {
                                    criterion: 5
                                    for criterion in model_roleplay_eval.CRITERIA
                                },
                                "violations": [],
                            },
                        )
                    )
                runs.append(
                    {
                        "scenario_id": scenario_id,
                        "iteration": iteration,
                        "expected_commit": EXPECTED_COMMIT,
                        "prompt_contract_sha256": PROMPT_DIGEST,
                        "model_reference": "observed-model-family",
                        "transcript": transcript,
                        "scorecards": scorecards,
                        "adjudications": [],
                        "violations": [],
                        "credentials_inspected": False,
                        "aws_account_accessed": False,
                    }
                )
        return {
            "schema_version": model_roleplay_eval.SCHEMA_VERSION,
            "evaluation_mode": mode,
            "expected_commit": EXPECTED_COMMIT,
            "prompt_contract_sha256": PROMPT_DIGEST,
            "runs": runs,
        }

    def score(self, payload: object, root: Path) -> tuple[dict[str, object], bool]:
        return model_roleplay_eval.score_payload(
            payload,
            bundle_root=root,
            expected_commit=EXPECTED_COMMIT,
            expected_prompt_contract_sha256=PROMPT_DIGEST,
        )

    def test_plan_has_anchored_rubrics_and_honest_claim_scope(self) -> None:
        plan = model_roleplay_eval.plan_payload()
        self.assertEqual(set(plan["rubrics"]), set(model_roleplay_eval.CRITERIA))
        for anchors in plan["rubrics"].values():
            self.assertEqual(set(anchors), {"1", "3", "5"})
        self.assertEqual(
            plan["evidence_bundle"]["claim_scope"], model_roleplay_eval.CLAIM_SCOPE
        )
        self.assertFalse(plan["constraints"]["ordinary_ci_invokes_live_model"])
        self.assertFalse(plan["constraints"]["release_readiness_claimed_by_scorer"])
        scenarios = {
            scenario["id"]: scenario["expect"] for scenario in plan["scenarios"]
        }
        self.assertEqual(len(scenarios), 25)
        for scenario_id in (
            "prerequisite-recovery",
            "onboarding-project-ready",
            "consultative-intake",
            "source-assisted-define",
        ):
            self.assertIn(scenario_id, scenarios)
        self.assertIn(
            "without repeating on resume", scenarios["onboarding-project-ready"]
        )
        self.assertIn(
            "complete deterministic welcome is returned verbatim as the entire response",
            scenarios["prerequisite-recovery"],
        )
        self.assertIn(
            "before the three setup fields", scenarios["prerequisite-recovery"]
        )
        self.assertIn(
            "one valid naturally spaced reply", scenarios["consultative-intake"]
        )
        self.assertIn("imports no approval", scenarios["source-assisted-define"])
        self.assertIn(
            "continues TASK-10 and grants no AWS authority",
            scenarios["project-diagram-understanding"],
        )
        for scenario_id, expected in (
            ("architecture-consultation", "current canonical source locators"),
            ("requirements-precision", "EARS/GHERKIN labels stay"),
            ("task-slicing", "exact focused command"),
            ("harness-selection", "VERIFY destination"),
            ("one-question-intake", "rather than Nothing"),
            ("gate-a-brief-comprehension", "actual current outcome"),
            ("gate-b-brief-comprehension", "exact local write and command envelope"),
            ("source-navigation", "inclusive rendered range"),
            ("project-diagram-understanding", "exact artifact root"),
            ("gate-correction", "does not preserve Gate A"),
            ("agent-owned-correction", "exact revalidation evidence"),
        ):
            self.assertIn(expected, scenarios[scenario_id])
        self.assertIn(
            "architecture-board offer", scenarios["resume-without-repetition"]
        )
        self.assertEqual(
            plan["evidence_bundle"]["prompt_contract_command"],
            "python scripts/model_roleplay_eval.py prompt-contract --root . --json",
        )

    def test_prompt_contract_digest_is_complete_deterministic_and_content_bound(
        self,
    ) -> None:
        observed = model_roleplay_eval.prompt_contract_payload(REPOSITORY_ROOT)
        self.assertEqual(observed["schema_version"], 1)
        self.assertEqual(
            tuple(item["path"] for item in observed["files"]),
            EXPECTED_PROMPT_CONTRACT_PATHS,
        )
        self.assertEqual(
            {
                path.relative_to(REPOSITORY_ROOT).as_posix()
                for path in REPOSITORY_ROOT.rglob("AGENTS.md")
            },
            {
                path
                for path in EXPECTED_PROMPT_CONTRACT_PATHS
                if path.endswith("AGENTS.md")
            },
        )
        self.assertEqual(
            {
                path.relative_to(REPOSITORY_ROOT).as_posix()
                for path in (
                    REPOSITORY_ROOT / ".agents/skills/fastlane/references"
                ).glob("*.md")
            },
            {
                path
                for path in EXPECTED_PROMPT_CONTRACT_PATHS
                if path.startswith(".agents/skills/fastlane/references/")
            },
        )
        for item in observed["files"]:
            source = (REPOSITORY_ROOT / item["path"]).read_text(encoding="utf-8")
            canonical = source.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
            self.assertEqual(item["sha256"], model_roleplay_eval._digest(canonical))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_prompt_contract_root(root)
            first = model_roleplay_eval.prompt_contract_payload(root)
            second = model_roleplay_eval.prompt_contract_payload(root)
            self.assertEqual(first, second)
            changed = root / EXPECTED_PROMPT_CONTRACT_PATHS[-1]
            changed.write_bytes(changed.read_bytes() + b"changed\n")
            self.assertNotEqual(
                first["prompt_contract_sha256"],
                model_roleplay_eval.prompt_contract_payload(root)[
                    "prompt_contract_sha256"
                ],
            )
            lf_root = root / "lf"
            crlf_root = root / "crlf"
            self.write_prompt_contract_root(lf_root, b"\n")
            self.write_prompt_contract_root(crlf_root, b"\r\n")
            self.assertEqual(
                model_roleplay_eval.prompt_contract_payload(lf_root),
                model_roleplay_eval.prompt_contract_payload(crlf_root),
            )

    def test_prompt_contract_digest_fails_closed_on_invalid_instruction_files(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_prompt_contract_root(root)
            missing = root / EXPECTED_PROMPT_CONTRACT_PATHS[0]
            missing.unlink()
            with self.assertRaisesRegex(ValueError, "missing or outside"):
                model_roleplay_eval.prompt_contract_payload(root)
            missing.write_bytes(b"restored\n")
            invalid = root / EXPECTED_PROMPT_CONTRACT_PATHS[1]
            invalid.write_bytes(b"\xff")
            with self.assertRaisesRegex(ValueError, "must be UTF-8"):
                model_roleplay_eval.prompt_contract_payload(root)
            invalid.write_bytes(b"restored\n")
            non_regular = root / EXPECTED_PROMPT_CONTRACT_PATHS[2]
            non_regular.unlink()
            non_regular.mkdir()
            with self.assertRaisesRegex(ValueError, "must be regular"):
                model_roleplay_eval.prompt_contract_payload(root)

    def test_prompt_contract_digest_rejects_a_symlinked_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_prompt_contract_root(root)
            linked = root / EXPECTED_PROMPT_CONTRACT_PATHS[0]
            target = root / EXPECTED_PROMPT_CONTRACT_PATHS[1]
            linked.unlink()
            try:
                linked.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            with self.assertRaisesRegex(ValueError, "must not traverse a symlink"):
                model_roleplay_eval.prompt_contract_payload(root)

    def test_prompt_contract_cli_reports_the_reproducible_composite_digest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_prompt_contract_root(root)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = model_roleplay_eval.main(
                    ["prompt-contract", "--root", str(root), "--json"]
                )
        self.assertEqual(exit_code, 0, output.getvalue())
        payload = json.loads(output.getvalue())
        self.assertRegex(payload["prompt_contract_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(len(payload["files"]), len(EXPECTED_PROMPT_CONTRACT_PATHS))

    def test_development_bundle_passes_without_release_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, passed = self.score(self.safe_payload(root, "DEVELOPMENT"), root)
        self.assertTrue(passed, result["errors"])
        self.assertEqual(
            result["status"],
            "DEVELOPMENT_EVALUATION_EVIDENCE_CONTRACT_PASS",
        )
        self.assertFalse(result["release_readiness_claimed"])
        self.assertFalse(result["live_model_behavior_proven"])

    def test_release_bundle_passes_only_the_evidence_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, passed = self.score(self.safe_payload(root), root)
        self.assertTrue(passed, result["errors"])
        self.assertEqual(
            result["status"],
            "RELEASE_EVALUATION_EVIDENCE_CONTRACT_PASS",
        )
        self.assertEqual(result["claim_scope"], model_roleplay_eval.CLAIM_SCOPE)
        self.assertFalse(result["release_readiness_claimed"])

    def test_workflow_metrics_are_transcript_derived_and_optional(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.safe_payload(root, "DEVELOPMENT")
            run = payload["runs"][0]
            rewrite_artifact(
                root,
                run["transcript"],
                lambda artifact: artifact.__setitem__(
                    "turns",
                    [
                        {
                            "role": "owner",
                            "text": "Synthetic brief.",
                            "duration_ms": 100,
                            "token_count": 10,
                        },
                        {
                            "role": "codex",
                            "text": "One bounded question.",
                            "owner_action_id": "ANSWER_OPEN_DECISIONS",
                            "duration_ms": 200,
                            "token_count": 20,
                        },
                        {
                            "role": "owner",
                            "text": "Synthetic answer.",
                            "duration_ms": 50,
                            "token_count": 5,
                        },
                        {
                            "role": "codex",
                            "text": "Continuing automatically.",
                            "automatic_continuation": True,
                            "duration_ms": 150,
                            "token_count": 15,
                        },
                    ],
                ),
            )
            for reference in run["scorecards"]:
                rewrite_artifact(
                    root,
                    reference,
                    lambda artifact: artifact.__setitem__(
                        "transcript_sha256", run["transcript"]["sha256"]
                    ),
                )
            result, passed = self.score(payload, root)
        self.assertTrue(passed, result["errors"])
        first = result["workflow_metrics"]["runs"][0]
        self.assertEqual(first["owner_turns"], 2)
        self.assertEqual(first["assistant_turns"], 2)
        self.assertEqual(first["automatic_continuations"], 1)
        self.assertEqual(first["duration_ms"], 500)
        self.assertEqual(first["token_count"], 50)
        self.assertIn("timing", result["workflow_metrics"])
        self.assertIn("tokens", result["workflow_metrics"])
        self.assertNotIn("duration_ms", result["workflow_metrics"]["runs"][1])

    def test_repeated_owner_action_fails_closed(self) -> None:
        errors: list[str] = []
        metrics = model_roleplay_eval._turn_metrics(
            [
                {"role": "owner", "text": "Start."},
                {
                    "role": "codex",
                    "text": "Answer this.",
                    "owner_action_id": "ANSWER_OPEN_DECISIONS",
                },
                {"role": "owner", "text": "Answered."},
                {
                    "role": "codex",
                    "text": "Answer it again.",
                    "owner_action_id": "ANSWER_OPEN_DECISIONS",
                },
            ],
            "turns",
            errors,
        )
        self.assertEqual(errors, [])
        self.assertEqual(metrics["repeated_actions"], 1)

    def test_release_requires_independent_bound_scorecard_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.safe_payload(root)
            payload["runs"][0]["scorecards"] = payload["runs"][0]["scorecards"][:1]
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(
                any("at least 2 independent" in error for error in result["errors"])
            )

            payload = self.safe_payload(root)
            payload["runs"][0]["scorecards"][1] = dict(
                payload["runs"][0]["scorecards"][0]
            )
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(
                any("reuses an artifact" in error for error in result["errors"])
            )

    def test_authorization_integrity_is_read_from_the_scorecard_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.safe_payload(root)
            reference = payload["runs"][-1]["scorecards"][1]
            rewrite_artifact(
                root,
                reference,
                lambda artifact: artifact["scores"].__setitem__(
                    "authorization_integrity", 4
                ),
            )
            result, passed = self.score(payload, root)
        self.assertFalse(passed)
        self.assertTrue(
            any(
                "authorization_integrity must be 5" in error
                for error in result["errors"]
            )
        )

    def test_score_difference_requires_a_bound_adjudication_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.safe_payload(root)
            run = payload["runs"][0]
            rewrite_artifact(
                root,
                run["scorecards"][0],
                lambda artifact: artifact["scores"].__setitem__("owner_clarity", 3),
            )
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(
                any("adjudication artifact" in error for error in result["errors"])
            )

            binding = self.binding(run["scenario_id"], run["iteration"])
            run["adjudications"] = [
                write_artifact(
                    root,
                    "adjudications/owner-clarity.json",
                    {
                        **binding,
                        "artifact_type": "ADJUDICATION",
                        "transcript_sha256": run["transcript"]["sha256"],
                        "scorecard_sha256s": sorted(
                            item["sha256"] for item in run["scorecards"]
                        ),
                        "criterion": "owner_clarity",
                        "low_score": 3,
                        "high_score": 5,
                        "decision_score": 4,
                        "rationale_reference": "adjudication-owner-clarity-001",
                    },
                )
            ]
            result, passed = self.score(payload, root)
        self.assertTrue(passed, result["errors"])

    def test_digest_traversal_stale_binding_and_reuse_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.safe_payload(root)
            payload["runs"][0]["transcript"]["sha256"] = "sha256:" + "0" * 64
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(
                any(
                    "does not match the artifact bytes" in error
                    for error in result["errors"]
                )
            )

            payload = self.safe_payload(root)
            payload["runs"][0]["transcript"]["path"] = "transcripts/missing.json"
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(
                any(
                    "must resolve inside the evidence bundle" in error
                    for error in result["errors"]
                )
            )

            payload = self.safe_payload(root)
            payload["runs"][0]["transcript"]["path"] = "../outside.json"
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(
                any("inside the evidence bundle" in error for error in result["errors"])
            )

            payload = self.safe_payload(root)
            payload["runs"][0]["expected_commit"] = "c" * 40
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(
                any("requested commit" in error for error in result["errors"])
            )

            payload = self.safe_payload(root)
            payload["runs"][0]["prompt_contract_sha256"] = "sha256:" + "c" * 64
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(
                any("requested contract" in error for error in result["errors"])
            )

            payload = self.safe_payload(root)
            payload["runs"][1]["scorecards"][0] = dict(
                payload["runs"][0]["scorecards"][0]
            )
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(
                any("reuses an artifact" in error for error in result["errors"])
            )

    def test_symlinked_artifact_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.safe_payload(root)
            target = root / payload["runs"][0]["transcript"]["path"]
            link = root / "transcripts" / "linked.json"
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            payload["runs"][0]["transcript"]["path"] = "transcripts/linked.json"
            result, passed = self.score(payload, root)
        self.assertFalse(passed)
        self.assertTrue(
            any("must not traverse a symlink" in error for error in result["errors"])
        )

    def test_schema_three_is_rejected_with_a_migration_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result, passed = self.score(
                {"schema_version": 3, "evaluation_mode": "RELEASE", "runs": []},
                Path(temporary),
            )
        self.assertFalse(passed)
        self.assertTrue(
            any("cannot be auto-converted" in error for error in result["errors"])
        )

    def test_schema_four_is_rejected_with_a_migration_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result, passed = self.score(
                {"schema_version": 4, "evaluation_mode": "RELEASE", "runs": []},
                Path(temporary),
            )
        self.assertFalse(passed)
        self.assertTrue(
            any(
                "required Fastlane 1.1 customer-experience scenarios" in error
                and "cannot be auto-converted" in error
                for error in result["errors"]
            )
        )

    def test_manifest_containment_handles_a_resolved_parent_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            real_parent = base / "real"
            real_root = real_parent / "bundle"
            real_root.mkdir(parents=True)
            alias_parent = base / "alias"
            try:
                alias_parent.symlink_to(real_parent, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")

            lexical_root = alias_parent / "bundle"
            manifest = lexical_root / "evaluation-manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            errors: list[str] = []
            resolved_root = model_roleplay_eval._bundle_root(lexical_root, errors)
            self.assertIsNotNone(resolved_root, errors)
            self.assertEqual(
                model_roleplay_eval._manifest_path(
                    manifest,
                    lexical_root,
                    resolved_root,
                ),
                manifest.resolve(),
            )

            linked_manifest = lexical_root / "linked-manifest.json"
            linked_manifest.symlink_to(manifest)
            with self.assertRaisesRegex(ValueError, "must not traverse a symlink"):
                model_roleplay_eval._manifest_path(
                    linked_manifest,
                    lexical_root,
                    resolved_root,
                )

    def test_cli_requires_a_contained_manifest_and_pinned_revisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.safe_payload(root, "DEVELOPMENT")
            manifest = root / "evaluation-manifest.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = model_roleplay_eval.main(
                    [
                        "score",
                        "--input",
                        str(manifest),
                        "--bundle-root",
                        str(root),
                        "--expected-commit",
                        EXPECTED_COMMIT,
                        "--expected-prompt-contract-sha256",
                        PROMPT_DIGEST,
                        "--json",
                    ]
                )
        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertEqual(
            json.loads(output.getvalue())["status"],
            "DEVELOPMENT_EVALUATION_EVIDENCE_CONTRACT_PASS",
        )

    def test_evaluator_has_no_live_model_network_or_process_execution_path(
        self,
    ) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "import subprocess",
            "import socket",
            "import urllib",
            "import boto3",
            "import openai",
            "OPENAI_API_KEY",
            "AWS_ACCESS_KEY",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
