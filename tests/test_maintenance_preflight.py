from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "maintenance_preflight.py"
SPEC = importlib.util.spec_from_file_location("maintenance_preflight", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT}")
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class MaintenancePreflightTests(unittest.TestCase):
    def repository(self, root: Path) -> str:
        subprocess.run(
            ["git", "init", "-b", "maintenance"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Synthetic Test"], cwd=root, check=True
        )
        (root / "tracked.txt").write_text("baseline\n", encoding="utf-8", newline="\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "baseline"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def contract(self, commit: str, mode: str = "IMPLEMENT") -> dict[str, object]:
        return {
            "schema_version": 1,
            "mode": mode,
            "branch": "maintenance",
            "commit": commit,
            "outcome": "Prove one bounded maintenance outcome.",
            "non_goals": ["No lifecycle changes."],
            "allowed_files": ["change.txt"] if mode == "IMPLEMENT" else [],
            "acceptance_criteria": ["The read-only preflight reports exact scope."],
            "maximum_changed_files": 1 if mode == "IMPLEMENT" else 0,
            "maximum_net_production_lines": 5 if mode == "IMPLEMENT" else 0,
            "publication": None,
        }

    def publication(
        self, commit: str, operations: tuple[str, ...] = ("COMMIT",)
    ) -> dict[str, object]:
        payload = self.contract(commit, "PUBLISH")
        payload["publication"] = {
            "operations": list(operations),
            "targets": ["maintenance"],
            "authorization_reference": "owner-request-001",
        }
        return payload

    def test_implement_accepts_only_declared_changes_and_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.repository(root)
            (root / "change.txt").write_text("one\ntwo\n", encoding="utf-8")
            result, passed = preflight.validate_contract(self.contract(commit), root)
            self.assertTrue(passed, result["errors"])
            self.assertEqual(result["changed_files"], ["change.txt"])
            self.assertEqual(result["net_production_lines"], 2)

            (root / "outside.txt").write_text("outside\n", encoding="utf-8")
            result, passed = preflight.validate_contract(self.contract(commit), root)
            self.assertFalse(passed)
            self.assertTrue(
                any("exceed the allowlist" in item for item in result["errors"])
            )

    def test_read_only_modes_and_publication_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.repository(root)
            audit, passed = preflight.validate_contract(
                self.contract(commit, "AUDIT"), root
            )
            self.assertTrue(passed, audit["errors"])

            invalid = self.contract(commit, "IMPLEMENT")
            invalid["publication"] = {
                "operations": ["PUSH"],
                "targets": ["fast-lane"],
                "authorization_reference": "owner-request-001",
            }
            result, passed = preflight.validate_contract(invalid, root)
            self.assertFalse(passed)
            self.assertTrue(
                any("must not contain publication" in item for item in result["errors"])
            )

            publish = self.contract(commit, "PUBLISH")
            publish["publication"] = {
                "operations": ["PUSH"],
                "targets": ["fast-lane"],
                "authorization_reference": "owner-request-001",
            }
            result, passed = preflight.validate_contract(publish, root)
            self.assertTrue(passed, result["errors"])

            mixed = self.publication(commit, ("PUSH", "OPEN_PR", "MERGE"))
            result, passed = preflight.validate_contract(mixed, root)
            self.assertFalse(passed)
            self.assertTrue(
                any("only one operation" in item for item in result["errors"])
            )

    def test_missing_scope_and_wrong_baseline_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.repository(root)
            payload = self.contract(commit)
            del payload["acceptance_criteria"]
            result, passed = preflight.validate_contract(payload, root)
            self.assertFalse(passed)
            self.assertTrue(any("missing fields" in item for item in result["errors"]))

            payload = self.contract("f" * 40)
            result, passed = preflight.validate_contract(payload, root)
            self.assertFalse(passed)
            self.assertTrue(any("baseline" in item for item in result["errors"]))

    def test_public_api_rejects_observation_injection(self) -> None:
        with self.assertRaises(TypeError):
            preflight.validate_contract(
                {}, Path.cwd(), _observed=("maintenance", "f" * 40, [], 0, ())
            )

    def test_commit_requires_exact_fully_staged_implementation_and_emits_receipt(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = self.repository(root)
            (root / "change.txt").write_text("candidate\n", encoding="utf-8")
            subprocess.run(["git", "add", "change.txt"], cwd=root, check=True)
            before = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            result, passed = preflight.validate_contract(
                self.publication(baseline), root, self.contract(baseline)
            )
            after = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertTrue(passed, result["errors"])
            self.assertEqual(before, after)
            self.assertRegex(
                result["implementation_contract_sha256"], r"^sha256:[0-9a-f]{64}$"
            )
            self.assertRegex(result["staged_diff_sha256"], r"^sha256:[0-9a-f]{64}$")
            with tempfile.TemporaryDirectory() as contract_directory:
                publish_path = Path(contract_directory) / "publish.json"
                implement_path = Path(contract_directory) / "implement.json"
                publish_path.write_text(
                    json.dumps(self.publication(baseline)), encoding="utf-8"
                )
                implement_path.write_text(
                    json.dumps(self.contract(baseline)), encoding="utf-8"
                )
                cli = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--contract",
                        str(publish_path),
                        "--implementation-contract",
                        str(implement_path),
                        "--root",
                        str(root),
                        "--json",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)
            self.assertEqual(json.loads(cli.stdout)["status"], "PASS")

            subprocess.run(
                ["git", "commit", "-m", "candidate"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            parent = subprocess.run(
                ["git", "rev-parse", "HEAD^"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            patch = subprocess.run(
                [
                    "git",
                    "diff",
                    "--binary",
                    "--full-index",
                    "--no-ext-diff",
                    "HEAD^",
                    "HEAD",
                    "--",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            digest = "sha256:" + hashlib.sha256(patch.encode()).hexdigest()
            self.assertEqual(parent, baseline)
            self.assertEqual(digest, result["staged_diff_sha256"])
            self.assertEqual(
                subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout,
                "",
            )

    def test_commit_rejects_partial_staging_mixed_operations_and_wrong_scope(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = self.repository(root)
            change = root / "change.txt"
            change.write_text("staged\n", encoding="utf-8")
            subprocess.run(["git", "add", "change.txt"], cwd=root, check=True)
            change.write_text("staged\nunstaged\n", encoding="utf-8")
            result, passed = preflight.validate_contract(
                self.publication(baseline), root, self.contract(baseline)
            )
            self.assertFalse(passed)
            self.assertTrue(any("unstaged" in item for item in result["errors"]))

            mixed, passed = preflight.validate_contract(
                self.publication(baseline, ("COMMIT", "PUSH")),
                root,
                self.contract(baseline),
            )
            self.assertFalse(passed)
            self.assertTrue(
                any("only one operation" in item for item in mixed["errors"])
            )

            wrong = self.contract("f" * 40)
            result, passed = preflight.validate_contract(
                self.publication(baseline), root, wrong
            )
            self.assertFalse(passed)
            self.assertTrue(any("branch/baseline" in item for item in result["errors"]))

    def test_commit_rejects_empty_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = self.repository(root)
            result, passed = preflight.validate_contract(
                self.publication(baseline), root, self.contract(baseline)
            )
            self.assertFalse(passed)
            self.assertTrue(any("nonempty staged" in item for item in result["errors"]))

    def test_commit_rejects_unmerged_and_active_git_operation_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.repository(root)
            subprocess.run(["git", "switch", "-c", "other"], cwd=root, check=True)
            (root / "tracked.txt").write_text("other\n", encoding="utf-8")
            subprocess.run(["git", "commit", "-am", "other"], cwd=root, check=True)
            subprocess.run(["git", "switch", "maintenance"], cwd=root, check=True)
            (root / "tracked.txt").write_text("maintenance\n", encoding="utf-8")
            subprocess.run(
                ["git", "commit", "-am", "maintenance"], cwd=root, check=True
            )
            baseline = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            merge = subprocess.run(
                ["git", "merge", "other"], cwd=root, check=False, capture_output=True
            )
            self.assertNotEqual(merge.returncode, 0)
            implementation = self.contract(baseline)
            implementation["allowed_files"] = ["tracked.txt"]
            result, passed = preflight.validate_contract(
                self.publication(baseline), root, implementation
            )
            self.assertFalse(passed)
            self.assertTrue(any("unmerged" in item for item in result["errors"]))
            self.assertTrue(
                any("active Git operation" in item for item in result["errors"])
            )

    def test_implementation_contract_is_rejected_for_non_commit_publication(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = self.repository(root)
            result, passed = preflight.validate_contract(
                self.publication(baseline, ("PUSH",)),
                root,
                self.contract(baseline),
            )
            self.assertFalse(passed)
            self.assertTrue(
                any("allowed only for COMMIT" in item for item in result["errors"])
            )

    def test_cli_is_read_only_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit = self.repository(root)
            contract = root / "contract.json"
            contract.write_text(
                json.dumps(self.contract(commit, "AUDIT")), encoding="utf-8"
            )
            before = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--contract",
                    str(contract),
                    "--root",
                    str(root),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            after = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        self.assertEqual(result.returncode, 2)
        self.assertEqual(before, after)
        self.assertEqual(json.loads(result.stdout)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
