from __future__ import annotations

import importlib.util
import io
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT_PATH = SCRIPTS / "setup_assistant.py"
SPEC = importlib.util.spec_from_file_location("setup_assistant", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


def official_session_evidence(**updates: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "official_plugin_installed": True,
        "official_plugin_enabled": True,
        "official_plugin_loaded_in_session": True,
        "official_plugin_source_verified": True,
        "observed_marketplace_repository": setup.OFFICIAL_AWS_MARKETPLACE,
        "observed_plugin_source": setup.OFFICIAL_AWS_MARKETPLACE_NAME,
        "observed_plugin_identity": setup.OFFICIAL_AWS_CORE_IDENTITY,
        "native_hook_review_required": False,
        "native_hook_review_attested": False,
        "aws_core_runtime_discovery": {
            "search_status": "PASS",
            "search_query": "AWS skills",
            "search_observed_at": "2026-07-26T12:00:00Z",
            "discovered_skill_identifiers": ["aws-serverless", "aws-iam"],
            "selected_skill_identifier": "aws-serverless",
            "retrieve_status": "PASS",
            "retrieved_skill_identifier": "aws-serverless",
            "retrieve_observed_at": "2026-07-26T12:00:01Z",
            "credentials_inspected": False,
            "aws_account_accessed": False,
        },
        "credentials_inspected": False,
        "aws_account_accessed": False,
    }
    evidence.update(updates)
    return evidence


def local_ready(**updates: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "repository_ready": True,
        "codex_cli_available": True,
        "codex_cli_supported": True,
        "codex_login_status_supported": True,
        "codex_login_ready": True,
        "git_available": True,
        "python_available": True,
        "python_version_supported": True,
        "uvx_available": True,
        "bubblewrap_required": True,
        "bubblewrap_available": True,
        "platform_supported": True,
        "platform_family": "LINUX",
        "is_wsl2": False,
        "pipx_available": True,
        "winget_available": False,
        "brew_available": False,
        "safe_probes_executed": True,
    }
    evidence.update(official_session_evidence())
    evidence.update(updates)
    return evidence


class FakeEnvironment:
    def __init__(self, outputs: dict[tuple[str, ...], tuple[int, str]] | None = None):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.commands = {"codex", "git", "python", "python3", "uvx", "bwrap", "pipx"}
        for name in self.commands:
            (self.root / name).write_text("test", encoding="utf-8")
        self.outputs = outputs or {
            ("codex", "--version"): (0, "codex-cli 0.144.6"),
            ("codex", "login", "status"): (0, "Logged in"),
            ("git", "--version"): (0, "git version 2.50.0"),
            ("python3", "--version"): (0, "Python 3.12.1"),
            ("python", "--version"): (0, "Python 3.10.0"),
            ("uvx", "--version"): (0, "uvx 0.11.29"),
            ("bwrap", "--version"): (0, "bubblewrap 0.11.0"),
        }
        self.calls: list[tuple[str, ...]] = []

    def close(self) -> None:
        self.temporary.cleanup()

    def which(self, name: str) -> str | None:
        candidate = self.root / name
        return str(candidate) if candidate.exists() else None

    def runner(self, args: setup.Sequence[str]) -> subprocess.CompletedProcess[str]:
        key = (Path(args[0]).name, *args[1:])
        self.calls.append(key)
        returncode, output = self.outputs.get(key, (1, "unsupported"))
        return subprocess.CompletedProcess(args, returncode, stdout=output, stderr="")


class SetupAssistantTests(unittest.TestCase):
    def test_public_state_model_matches_setup_first_contract(self) -> None:
        self.assertEqual(
            setup.SETUP_STATES,
            (
                "PREREQUISITES_REQUIRED",
                "CODEX_LOGIN_REQUIRED",
                "PLATFORM_SANDBOX_REQUIRED",
                "UV_REQUIRED",
                "AWS_CORE_REQUIRED",
                "AWS_CORE_NATIVE_TRUST_REQUIRED",
                "PREREQUISITES_READY",
            ),
        )

    def test_local_probes_are_bounded_and_supported_python3_wins(self) -> None:
        environment = FakeEnvironment()
        try:
            observed = setup.inspect_local_prerequisites(
                REPOSITORY_ROOT,
                which=environment.which,
                runner=environment.runner,
                system="Linux",
                release="6.8.0-generic",
            )
        finally:
            environment.close()
        self.assertTrue(observed["python_version_supported"])
        self.assertIn(("python3", "--version"), environment.calls)
        self.assertNotIn(("python", "--version"), environment.calls)
        self.assertEqual(
            set(environment.calls),
            {
                ("codex", "--version"),
                ("codex", "login", "status"),
                ("git", "--version"),
                ("python3", "--version"),
                ("uvx", "--version"),
                ("bwrap", "--version"),
            },
        )
        serialized = "\n".join(" ".join(call) for call in environment.calls)
        for forbidden in ("install", "marketplace", "plugin", "aws configure"):
            self.assertNotIn(forbidden, serialized.casefold())

    def test_git_probe_rejects_project_local_resolution_without_execution(self) -> None:
        environment = FakeEnvironment()
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            (project / "bootstrap.manifest.json").write_text("{}", encoding="utf-8")
            local_git = project / "git"
            local_git.write_text("untrusted", encoding="utf-8")

            def which(name: str) -> str | None:
                return str(local_git) if name == "git" else environment.which(name)

            try:
                observed = setup.inspect_local_prerequisites(
                    project,
                    which=which,
                    runner=environment.runner,
                    system="Linux",
                    release="6.8.0-generic",
                )
            finally:
                environment.close()
        self.assertFalse(observed["git_available"])
        self.assertNotIn(("git", "--version"), environment.calls)
        self.assertIn(("codex", "--version"), environment.calls)

    def test_hook_configuration_uses_an_external_absolute_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            codex = root / ".codex"
            codex.mkdir(parents=True)
            (root / "bootstrap.manifest.json").write_text("{}", encoding="utf-8")
            (root / "scripts").mkdir()
            (root / "scripts" / "bootstrap_doctor.py").write_text(
                "# marker\n", encoding="utf-8"
            )
            (codex / "hooks").mkdir()
            (codex / "hooks" / "fastlane_hook.py").write_text(
                "import sys\nprint(sys.argv[1])\n", encoding="utf-8"
            )
            (codex / "hooks.fastlane.example.json").write_bytes(
                (
                    REPOSITORY_ROOT / ".codex" / "hooks.fastlane.example.json"
                ).read_bytes()
            )

            target = setup.configure_local_hooks(root, interpreter=Path(sys.executable))
            self.assertEqual(target, (codex / "hooks.json").resolve())
            configured = json.loads(target.read_text(encoding="utf-8"))
            commands = [
                hook[field]
                for groups in configured["hooks"].values()
                for group in groups
                for hook in group["hooks"]
                for field in ("command", "commandWindows")
            ]
            expected = str(Path(sys.executable).resolve())
            self.assertTrue(commands)
            for command in commands:
                self.assertIn(expected, command)
                self.assertNotIn("__FASTLANE_PYTHON_", command)
                self.assertNotRegex(command, r"(?i)^(?:python3|py)(?:\s|$)")
            nested = root / "nested" / "deeper"
            nested.mkdir(parents=True)
            session_command = configured["hooks"]["SessionStart"][0]["hooks"][0][
                "command"
            ]
            completed = subprocess.run(
                shlex.split(session_command),
                cwd=nested,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), "session-start")
            (nested / "scripts").mkdir()
            (nested / "bootstrap.manifest.json").write_text("{}", encoding="utf-8")
            (nested / "scripts" / "bootstrap_doctor.py").write_text(
                "# deceptive nested marker\n", encoding="utf-8"
            )
            ambiguous = subprocess.run(
                shlex.split(session_command),
                cwd=nested,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(ambiguous.returncode, 0)
            with self.assertRaisesRegex(setup.SetupError, "already exists"):
                setup.configure_local_hooks(root, interpreter=Path(sys.executable))
            self.assertEqual(
                setup.configure_local_hooks(
                    root, interpreter=Path(sys.executable), replace=True
                ),
                target,
            )

    def test_hook_configuration_rejects_project_local_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            codex = root / ".codex"
            codex.mkdir(parents=True)
            (root / "bootstrap.manifest.json").write_text("{}", encoding="utf-8")
            (codex / "hooks.fastlane.example.json").write_bytes(
                (
                    REPOSITORY_ROOT / ".codex" / "hooks.fastlane.example.json"
                ).read_bytes()
            )
            local_python = root / "python.exe"
            local_python.write_bytes(b"untrusted")
            with self.assertRaisesRegex(setup.SetupError, "trusted Python"):
                setup.configure_local_hooks(root, interpreter=local_python)
            self.assertFalse((codex / "hooks.json").exists())

    def test_hook_configuration_rejects_windows_shell_metacharacters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            codex = root / ".codex"
            codex.mkdir(parents=True)
            (root / "bootstrap.manifest.json").write_text("{}", encoding="utf-8")
            (codex / "hooks.fastlane.example.json").write_bytes(
                (
                    REPOSITORY_ROOT / ".codex" / "hooks.fastlane.example.json"
                ).read_bytes()
            )
            for character in ("&", "%", "^", "!"):
                with self.subTest(character=character):
                    interpreter = Path(temporary) / f"external{character}python.exe"
                    interpreter.write_bytes(b"trusted fixture")
                    with self.assertRaisesRegex(
                        setup.SetupError, "shell metacharacters"
                    ):
                        setup.configure_local_hooks(root, interpreter=interpreter)
                    self.assertFalse((codex / "hooks.json").exists())

    def test_codex_readiness_uses_capabilities_not_semantic_version(self) -> None:
        current = FakeEnvironment()
        current.outputs[("codex", "--version")] = (0, "codex-cli current")
        try:
            observed = setup.inspect_local_prerequisites(
                REPOSITORY_ROOT,
                which=current.which,
                runner=current.runner,
                system="Linux",
                release="6.8.0-generic",
            )
        finally:
            current.close()
        self.assertTrue(observed["codex_cli_available"])
        self.assertTrue(observed["codex_cli_supported"])
        self.assertTrue(observed["codex_login_status_supported"])
        self.assertTrue(observed["codex_login_ready"])

        unsupported = FakeEnvironment()
        unsupported.outputs[("codex", "--version")] = (1, "unsupported")
        try:
            failed = setup.inspect_local_prerequisites(
                REPOSITORY_ROOT,
                which=unsupported.which,
                runner=unsupported.runner,
                system="Linux",
                release="6.8.0-generic",
            )
        finally:
            unsupported.close()
        self.assertTrue(failed["codex_cli_available"])
        self.assertFalse(failed["codex_cli_supported"])

    def test_windows_prefers_supported_python3_when_python_is_old(self) -> None:
        environment = FakeEnvironment()
        try:
            observed = setup.inspect_local_prerequisites(
                REPOSITORY_ROOT,
                which=environment.which,
                runner=environment.runner,
                system="Windows",
                release="11",
            )
        finally:
            environment.close()
        self.assertTrue(observed["python_version_supported"])
        self.assertIn(("python3", "--version"), environment.calls)
        self.assertNotIn(("python", "--version"), environment.calls)
        self.assertFalse(observed["bubblewrap_required"])

    def test_wsl1_is_unsupported_and_wsl2_requires_bubblewrap(self) -> None:
        environment = FakeEnvironment()
        try:
            wsl1 = setup.inspect_local_prerequisites(
                REPOSITORY_ROOT,
                which=environment.which,
                runner=environment.runner,
                system="Linux",
                release="4.4.0-microsoft-standard",
            )
            wsl2 = setup.inspect_local_prerequisites(
                REPOSITORY_ROOT,
                which=lambda name: None if name == "bwrap" else environment.which(name),
                runner=environment.runner,
                system="Linux",
                release="5.15.0-microsoft-standard-WSL2",
            )
        finally:
            environment.close()
        self.assertFalse(wsl1["platform_supported"])
        self.assertTrue(wsl2["platform_supported"])
        self.assertTrue(wsl2["bubblewrap_required"])
        self.assertFalse(wsl2["bubblewrap_available"])
        rendered = setup.render_setup_response(
            setup.reduce_prerequisites({**local_ready(), **wsl2})
        )
        self.assertIn("sudo apt install bubblewrap", rendered)

    def test_every_state_is_reachable(self) -> None:
        cases = (
            (local_ready(codex_cli_available=False), "PREREQUISITES_REQUIRED"),
            (local_ready(codex_login_ready=False), "CODEX_LOGIN_REQUIRED"),
            (local_ready(bubblewrap_available=False), "PLATFORM_SANDBOX_REQUIRED"),
            (local_ready(uvx_available=False), "UV_REQUIRED"),
            (local_ready(official_plugin_loaded_in_session=False), "AWS_CORE_REQUIRED"),
            (
                local_ready(
                    native_hook_review_required=True, native_hook_review_attested=False
                ),
                "AWS_CORE_NATIVE_TRUST_REQUIRED",
            ),
            (local_ready(), "PREREQUISITES_READY"),
        )
        for evidence, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    setup.reduce_prerequisites(evidence)["state"], expected
                )

    def test_multiple_missing_tools_produce_one_complete_checklist_action(self) -> None:
        report = setup.reduce_prerequisites(
            local_ready(
                codex_cli_available=False,
                codex_cli_supported=False,
                git_available=False,
                python_available=False,
                python_version_supported=False,
                uvx_available=False,
                bubblewrap_available=False,
                official_plugin_loaded_in_session=False,
            )
        )
        self.assertEqual(report["state"], "PREREQUISITES_REQUIRED")
        self.assertEqual(report["owner_action_id"], "COMPLETE_PREREQUISITE_CHECKLIST")
        self.assertGreaterEqual(len(report["checklist"]), 5)
        rendered = setup.render_setup_response(report)
        self.assertEqual(rendered.count("Need from you:"), 1)
        self.assertIn("Owner-run install:", rendered)
        self.assertIn("Verify:", rendered)
        self.assertIn("Official guide:", rendered)
        for step in report["checklist"]:
            self.assertEqual(
                step["commands"],
                [
                    *step["install_commands"],
                    *step["action_commands"],
                    *step["verification_commands"],
                ],
            )
            self.assertTrue(step["verification_commands"])
            self.assertTrue(step["install_commands"] or step.get("guide"))
        for phrase in (
            "Codex CLI",
            "Git",
            "Python 3.11",
            "bubblewrap",
            "Astral uv",
            "official AWS Core",
        ):
            self.assertIn(phrase, rendered)

    def test_platform_specific_checklists_are_exact_and_owner_run(self) -> None:
        linux = setup.render_setup_response(
            setup.reduce_prerequisites(local_ready(bubblewrap_available=False))
        )
        for command in (
            "sudo apt update",
            "sudo apt install bubblewrap",
            "command -v bwrap",
            "bwrap --version",
        ):
            self.assertIn(command, linux)
        uv = setup.render_setup_response(
            setup.reduce_prerequisites(local_ready(uvx_available=False))
        )
        self.assertIn("pipx install uv", uv)
        self.assertIn("uvx --version", uv)

    def test_ready_welcome_collects_three_values_once(self) -> None:
        report = setup.reduce_prerequisites(local_ready())
        self.assertEqual(report["state"], "PREREQUISITES_READY")
        self.assertEqual(report["owner_action_id"], "ANSWER_PROJECT_SETUP_QUESTIONS")
        greeting = setup.render_setup_response(report)
        self.assertTrue(greeting.startswith("Welcome to AWS Codex Fastlane."))
        for label in ("Project name:", "Preferred AWS Region:", "Development budget:"):
            self.assertEqual(greeting.count(label), 1)
        self.assertIn(
            "did not inspect AWS credentials or access an AWS account", greeting
        )

    def test_final_onboarding_docs_and_instruction_headroom(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        setup_doc = (REPOSITORY_ROOT / "docs/SETUP.md").read_text(encoding="utf-8")
        combined = readme + "\n" + setup_doc
        self.assertIn("one consolidated checklist", combined)
        self.assertNotIn("one copyable checklist", combined)
        self.assertIn("signed-in interactive Codex CLI", combined)
        self.assertIn("Fastlane requires the official AWS Core plugin", readme)
        self.assertIn("runtime skills", setup_doc)
        self.assertIn("does not copy AWS skills into the\nrepository", readme)
        self.assertIn("does not require separately installed AWS skills", setup_doc)
        self.assertIn("Other Agent Toolkit plugins are optional", setup_doc)
        self.assertIn(
            "Ordinary requirements and\ndesign need no AWS credentials or AWS account",
            readme,
        )
        self.assertIn(
            "Deployment and teardown retain separate exact Fastlane authority",
            setup_doc,
        )
        self.assertLessEqual(len(readme.splitlines()), 90)
        self.assertLessEqual(len((REPOSITORY_ROOT / "AGENTS.md").read_bytes()), 7_200)

        prompts = (REPOSITORY_ROOT / "prompts/CODEX-PROMPTS.md").read_text(
            encoding="utf-8"
        )
        design_start = prompts.index("## DESIGN-10")
        design_end = prompts.index("## DESIGN-20", design_start)
        self.assertLessEqual(
            len(prompts[design_start:design_end].encode("utf-8")),
            8_000,
        )

    def test_official_source_and_linked_runtime_discovery_are_required(self) -> None:
        def observed(**updates: object) -> dict[str, object]:
            evidence = local_ready()
            discovery = dict(evidence[setup.RUNTIME_DISCOVERY_FIELD])
            discovery.update(updates)
            evidence[setup.RUNTIME_DISCOVERY_FIELD] = discovery
            return evidence

        no_runtime = local_ready()
        no_runtime.pop(setup.RUNTIME_DISCOVERY_FIELD)
        blocked = (
            local_ready(observed_plugin_identity="aws-agents@agent-toolkit-for-aws"),
            observed(search_status="FAIL"),
            observed(discovered_skill_identifiers=[]),
            observed(selected_skill_identifier="aws-databases"),
            observed(retrieved_skill_identifier="aws-iam"),
            observed(
                search_observed_at="2026-07-26T12:00:02Z",
                retrieve_observed_at="2026-07-26T12:00:01Z",
            ),
            observed(credentials_inspected=True),
            observed(aws_account_accessed=True),
            local_ready(credentials_inspected=True),
            local_ready(aws_account_accessed=True),
            no_runtime,
        )
        for evidence in blocked:
            with self.subTest(evidence=evidence):
                self.assertEqual(
                    setup.reduce_prerequisites(evidence)["state"],
                    "AWS_CORE_REQUIRED",
                )

        ready = setup.reduce_prerequisites(local_ready())
        self.assertEqual(ready["aws_core_status"], "AVAILABLE")
        self.assertEqual(ready["aws_core_runtime_discovery"], "CURRENT")
        self.assertNotIn("plugin_version", json.dumps(ready))
        self.assertNotIn("plugin_commit", json.dumps(ready))
        self.assertNotIn("aws-serverless", json.dumps(ready))

    def test_ready_prerequisite_report_handoff_is_exact_and_ephemeral(self) -> None:
        ready = setup.reduce_prerequisites(local_ready())
        self.assertEqual(ready, setup.READY_PREREQUISITE_REPORT)
        self.assertEqual(setup.validate_ready_prerequisite_report(ready), ready)
        self.assertEqual(
            setup.read_ready_prerequisite_report(io.StringIO(json.dumps(ready))),
            ready,
        )

        invalid = (
            {},
            {**ready, "state": "AWS_CORE_REQUIRED"},
            {**ready, "repository_writes": "OBSERVED"},
            {**ready, "aws_access": "USED"},
            {**ready, "session_identifier": "forbidden"},
        )
        for report in invalid:
            with self.subTest(report=report):
                with self.assertRaises(setup.SetupError):
                    setup.validate_ready_prerequisite_report(report)

        with self.assertRaises(setup.SetupError):
            setup.read_ready_prerequisite_report(io.StringIO("{"))

    def test_evidence_stdin_is_strict_ephemeral_and_non_secret(self) -> None:
        parsed = setup.read_session_evidence(
            io.StringIO(json.dumps(official_session_evidence()))
        )
        self.assertEqual(
            parsed[setup.RUNTIME_DISCOVERY_FIELD]["retrieve_status"],
            "PASS",
        )
        invalid_discovery = official_session_evidence()
        invalid_discovery[setup.RUNTIME_DISCOVERY_FIELD] = {
            **invalid_discovery[setup.RUNTIME_DISCOVERY_FIELD],
            "retrieved_skill_identifier": "token=secret",
        }
        for payload in (
            '{"hook_trust_database": true}',
            '{"AWS_SECRET_ACCESS_KEY": "secret"}',
            '{"official_plugin_enabled": "yes"}',
            '{"retrieve_skill_result": "MAYBE"}',
            '{"retrieve_skill_identifier": "token=secret"}',
            '{"search_documentation_references": ["https://example.com/not-aws"]}',
            json.dumps(invalid_discovery),
            "[]",
            "",
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(setup.SetupError):
                    setup.read_session_evidence(io.StringIO(payload))

    def test_script_contains_no_installer_or_plugin_mutation_execution(self) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("subprocess.run", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("Popen(", source)
        self.assertNotIn("approval-digest", source)
        self.assertNotIn("execute", setup.main.__doc__ or "")

    def test_cli_prerequisites_is_machine_readable_without_paths(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "prerequisites",
                "--root",
                str(REPOSITORY_ROOT),
                "--json",
            ],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertIn(completed.returncode, {0, 1})
        report = json.loads(completed.stdout)
        self.assertIn(report["state"], setup.SETUP_STATES)
        serialized = json.dumps(report)
        self.assertNotIn(str(REPOSITORY_ROOT), serialized)
        self.assertNotIn(str(Path(sys.executable).parent), serialized)
        self.assertEqual(report["repository_writes"], "NONE")
        self.assertFalse(report["user_state_persisted_in_repository"])

    def test_json_evidence_interface_does_not_write_repository(self) -> None:
        before = (REPOSITORY_ROOT / "bootstrap.yaml").read_bytes()
        with mock.patch.object(
            setup,
            "inspect_local_prerequisites",
            return_value={
                key: value
                for key, value in local_ready().items()
                if key not in setup.SESSION_EVIDENCE_FIELDS
            },
        ):
            with mock.patch.object(
                sys, "stdin", io.StringIO(json.dumps(official_session_evidence()))
            ):
                with mock.patch("builtins.print") as printer:
                    exit_code = setup.main(
                        [
                            "prerequisites",
                            "--root",
                            str(REPOSITORY_ROOT),
                            "--evidence-stdin",
                            "--json",
                        ]
                    )
        self.assertEqual(exit_code, 0)
        report = json.loads(printer.call_args.args[0])
        self.assertEqual(report["state"], "PREREQUISITES_READY")
        self.assertEqual((REPOSITORY_ROOT / "bootstrap.yaml").read_bytes(), before)

    def test_hostile_manifest_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            try:
                (root / "bootstrap.manifest.json").symlink_to(SCRIPT_PATH)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            with self.assertRaises(setup.SetupError):
                setup.canonical_root(root)

    def test_ready_welcome_explains_fastlane_and_owner_boundaries_once(self) -> None:
        greeting = setup.render_setup_response(
            setup.reduce_prerequisites(local_ready())
        )
        compact = " ".join(greeting.split())
        for phrase in (
            "clear AWS application plan and a tested local build",
            "You do not need to choose AWS services.",
            "Gate A confirms what should be built",
            "Gate B confirms the design and build boundaries",
            "Setup never authorizes AWS changes",
            "Fast Dev stays inside the exact approved non-production Gate B envelope",
            "Explicit Gate requires its own exact action receipt",
            "Setup did not inspect AWS credentials or access an AWS account.",
        ):
            self.assertIn(phrase, compact)
        for label in ("Project name:", "Preferred AWS Region:", "Development budget:"):
            self.assertEqual(greeting.count(label), 1)
        self.assertEqual(greeting.count("Welcome to AWS Codex Fastlane."), 1)


if __name__ == "__main__":
    unittest.main()
