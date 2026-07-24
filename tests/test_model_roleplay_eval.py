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
SPEC = importlib.util.spec_from_file_location("model_roleplay_eval_preview", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
model_roleplay_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model_roleplay_eval)


EXPECTED_COMMIT = "a" * 40
PROMPT_DIGEST = "sha256:" + "b" * 64


def write_artifact(root: Path, relative: str, payload: dict[str, object]) -> dict[str, str]:
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
            ("rater-alpha", "rater-beta")
            if mode == "RELEASE"
            else ("rater-alpha",)
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

    def score(
        self, payload: object, root: Path
    ) -> tuple[dict[str, object], bool]:
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
        self.assertEqual(plan["evidence_bundle"]["claim_scope"], model_roleplay_eval.CLAIM_SCOPE)
        self.assertFalse(plan["constraints"]["ordinary_ci_invokes_live_model"])
        self.assertFalse(plan["constraints"]["release_readiness_claimed_by_scorer"])

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

    def test_release_requires_independent_bound_scorecard_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.safe_payload(root)
            payload["runs"][0]["scorecards"] = payload["runs"][0]["scorecards"][:1]
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(any("at least 2 independent" in error for error in result["errors"]))

            payload = self.safe_payload(root)
            payload["runs"][0]["scorecards"][1] = dict(payload["runs"][0]["scorecards"][0])
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(any("reuses an artifact" in error for error in result["errors"]))

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
            any("authorization_integrity must be 5" in error for error in result["errors"])
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
            self.assertTrue(any("adjudication artifact" in error for error in result["errors"]))

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
            self.assertTrue(any("does not match the artifact bytes" in error for error in result["errors"]))

            payload = self.safe_payload(root)
            payload["runs"][0]["transcript"]["path"] = "transcripts/missing.json"
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(
                any("must resolve inside the evidence bundle" in error for error in result["errors"])
            )

            payload = self.safe_payload(root)
            payload["runs"][0]["transcript"]["path"] = "../outside.json"
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(any("inside the evidence bundle" in error for error in result["errors"]))

            payload = self.safe_payload(root)
            payload["runs"][0]["expected_commit"] = "c" * 40
            result, passed = self.score(payload, root)
            self.assertFalse(passed)
            self.assertTrue(any("requested commit" in error for error in result["errors"]))

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
            self.assertTrue(any("reuses an artifact" in error for error in result["errors"]))

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
        self.assertTrue(any("must not traverse a symlink" in error for error in result["errors"]))

    def test_schema_three_is_rejected_with_a_migration_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result, passed = self.score(
                {"schema_version": 3, "evaluation_mode": "RELEASE", "runs": []},
                Path(temporary),
            )
        self.assertFalse(passed)
        self.assertTrue(any("cannot be auto-converted" in error for error in result["errors"]))

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

    def test_evaluator_has_no_live_model_network_or_process_execution_path(self) -> None:
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
