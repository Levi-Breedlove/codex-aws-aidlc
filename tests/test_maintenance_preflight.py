from __future__ import annotations

import importlib.util
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
