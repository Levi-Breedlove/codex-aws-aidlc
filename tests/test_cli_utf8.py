from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FORCED_LEGACY_ENVIRONMENT = {
    **os.environ,
    "PYTHONIOENCODING": "cp1252",
    "PYTHONUTF8": "0",
}
LOCAL_ROOT_BYTES = str(REPOSITORY_ROOT).encode("utf-8")


def run_cli(
    *arguments: str,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=REPOSITORY_ROOT,
        env=FORCED_LEGACY_ENVIRONMENT,
        input=input_bytes,
        capture_output=True,
        check=False,
    )


class FastlaneCliUtf8Tests(unittest.TestCase):
    def assert_utf8_without_local_root(self, output: bytes) -> str:
        self.assertNotIn(LOCAL_ROOT_BYTES, output)
        return output.decode("utf-8", errors="strict")

    def test_importing_stdio_helper_does_not_reconfigure_streams(self) -> None:
        completed = run_cli(
            "-c",
            (
                "import sys; "
                "before=(sys.stdin.encoding,sys.stdout.encoding,sys.stderr.encoding); "
                "import scripts.fastlane_stdio; "
                "after=(sys.stdin.encoding,sys.stdout.encoding,sys.stderr.encoding); "
                "print('UNCHANGED' if before == after else 'CHANGED')"
            ),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), b"UNCHANGED")
        self.assertEqual(completed.stderr, b"")

    def test_helper_configures_stdin_stdout_and_stderr(self) -> None:
        completed = run_cli(
            "-c",
            (
                "import sys; "
                "from scripts.fastlane_stdio import configure_utf8_standard_streams; "
                "configure_utf8_standard_streams(); "
                "value=sys.stdin.read(); "
                "print(value,end=''); "
                "print('diagnostic—stream',file=sys.stderr)"
            ),
            input_bytes="input—stream".encode("utf-8"),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            self.assert_utf8_without_local_root(completed.stdout),
            "input—stream",
        )
        self.assertEqual(
            self.assert_utf8_without_local_root(completed.stderr).strip(),
            "diagnostic—stream",
        )

    def test_setup_welcome_is_utf8_under_legacy_windows_encoding(self) -> None:
        completed = run_cli("scripts/setup_assistant.py", "welcome")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        stdout = self.assert_utf8_without_local_root(completed.stdout)
        self.assertIn("Setup never authorizes AWS changes", stdout)
        self.assertEqual(completed.stderr, b"")

    def test_bootstrap_argparse_error_is_utf8_under_legacy_windows_encoding(
        self,
    ) -> None:
        completed = run_cli(
            "bootstrap.py",
            "--target",
            "synthetic-target",
            "--project-name",
            "Synthetic Project",
            "--unknown—option",
        )
        self.assertEqual(completed.returncode, 2)
        stderr = self.assert_utf8_without_local_root(completed.stderr)
        self.assertIn("--unknown—option", stderr)
        self.assertEqual(completed.stdout, b"")

    def test_dependency_argparse_error_is_utf8_under_legacy_windows_encoding(
        self,
    ) -> None:
        completed = run_cli("scripts/bootstrap_dependencies.py", "--unknown—option")
        self.assertEqual(completed.returncode, 2)
        stderr = self.assert_utf8_without_local_root(completed.stderr)
        self.assertIn("--unknown—option", stderr)
        self.assertEqual(completed.stdout, b"")

    def test_doctor_argparse_error_is_utf8_under_legacy_windows_encoding(self) -> None:
        completed = run_cli("scripts/bootstrap_doctor.py", "--unknown—option")
        self.assertEqual(completed.returncode, 2)
        stderr = self.assert_utf8_without_local_root(completed.stderr)
        self.assertIn("--unknown—option", stderr)
        self.assertEqual(completed.stdout, b"")

    def test_engine_help_is_utf8_and_uses_public_terminology(self) -> None:
        completed = run_cli("scripts/bootstrap_doctor.py", "--help")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        stdout = self.assert_utf8_without_local_root(completed.stdout)
        self.assertIn("Read-only AWS Codex Fastlane Engine", stdout)
        self.assertNotIn("project doctor", stdout.casefold())
        self.assertEqual(completed.stderr, b"")

    def test_engine_human_banner_is_utf8_and_public(self) -> None:
        completed = run_cli(
            "scripts/bootstrap_doctor.py",
            "--root",
            ".",
            "--template-source",
        )
        self.assertIn(completed.returncode, (0, 1), completed.stderr)
        stdout = self.assert_utf8_without_local_root(completed.stdout)
        self.assertIn("AWS Codex Fastlane Engine:", stdout)
        self.assertNotIn("Fastlane Doctor:", stdout)

    def test_presenter_output_is_utf8_under_legacy_windows_encoding(self) -> None:
        payload = {
            "report": {
                "interaction": {
                    "owner_stage": "DESIGN",
                    "response_mode": "OWNER_UPDATE",
                    "state": "WORKING",
                    "route_reason_code": "DESIGN_REQUIRED",
                    "owner_action_required": False,
                    "owner_action_kind": "NONE_CONTINUE_AUTOMATICALLY",
                    "blocking_ids": [],
                    "automatic_continuation_allowed": True,
                    "formal_receipt_required": False,
                    "aws_core": {
                        "materiality": "NOT_MATERIAL",
                        "evidence_status": "NOT_REQUIRED",
                    },
                }
            },
            "updated": "Gate A was approved—automatically.",
        }
        completed = run_cli(
            "scripts/fastlane_presenter.py",
            "owner",
            "--input-stdin",
            input_bytes=json.dumps(payload).encode("utf-8"),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        stdout = self.assert_utf8_without_local_root(completed.stdout)
        self.assertIn("FASTLANE · DESIGN", stdout)
        self.assertIn("approved—automatically", stdout)
        self.assertEqual(completed.stderr, b"")

    def test_task_error_is_utf8_under_legacy_windows_encoding(self) -> None:
        completed = run_cli("scripts/task_waves.py", "synthetic—task.md")
        self.assertEqual(completed.returncode, 2)
        stderr = self.assert_utf8_without_local_root(completed.stderr)
        self.assertIn("synthetic—task.md", stderr)
        self.assertEqual(completed.stdout, b"")


if __name__ == "__main__":
    unittest.main()
