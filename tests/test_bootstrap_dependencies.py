from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "bootstrap_dependencies.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_dependencies", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
dependencies = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dependencies)


class BootstrapDependencyTests(unittest.TestCase):
    def test_repository_declares_official_current_aws_core_without_pin(self) -> None:
        report = dependencies.inspect_repository(REPOSITORY_ROOT)
        self.assertEqual(report["status"], "READY", report["diagnostics"])
        toolkit = report["aws_agent_toolkit"]
        self.assertEqual(toolkit["dependency_policy"], "OFFICIAL_CURRENT")
        self.assertEqual(toolkit["marketplace_slug"], "aws/agent-toolkit-for-aws")
        self.assertEqual(toolkit["plugin_identity"], "aws-core@agent-toolkit-for-aws")
        self.assertEqual(toolkit["version_policy"], "OFFICIAL_CURRENT_NO_TEMPLATE_PIN")
        self.assertEqual(
            toolkit["availability_policy"], "REQUIRED_FOR_FRESH_INITIALIZATION"
        )
        self.assertNotIn("last_tested_version", toolkit)
        self.assertEqual(toolkit["installation_policy"], "OWNER_MANAGED")
        self.assertEqual(toolkit["setup_mode"], "INSTRUCTIONS_ONLY")
        self.assertEqual(
            toolkit["marketplace_registration_command"],
            ["codex", "plugin", "marketplace", "add", "aws/agent-toolkit-for-aws"],
        )

        setup = toolkit["setup_assistant"]
        self.assertEqual(
            setup["states"],
            [
                "PREREQUISITES_REQUIRED",
                "CODEX_LOGIN_REQUIRED",
                "PLATFORM_SANDBOX_REQUIRED",
                "UV_REQUIRED",
                "AWS_CORE_REQUIRED",
                "AWS_CORE_NATIVE_TRUST_REQUIRED",
                "PREREQUISITES_READY",
            ],
        )
        self.assertFalse(setup["automatic_runtime_installation"])
        self.assertFalse(setup["package_manager_execution"])
        self.assertTrue(setup["runtime_probe_execution"])
        self.assertTrue(setup["initialized_resume_skips_prerequisites"])

        runtime = toolkit["runtime_verification"]
        self.assertTrue(runtime["required_at_boot"])
        self.assertTrue(runtime["required_only_for_fresh_initialization"])
        self.assertEqual(
            runtime["required_evidence_phases"],
            ["DESIGN-10", "AWS-10"],
        )
        self.assertEqual(
            runtime["required_capabilities"],
            ["retrieve_skill", "search_documentation"],
        )
        self.assertNotIn("hook_review", toolkit)
        self.assertEqual(report["fastlane_skills"]["status"], "READY")

    def test_optional_challengers_are_read_only_and_do_not_override_model_or_mcp(
        self,
    ) -> None:
        for name in (
            "fastlane-requirements-challenger",
            "fastlane-architecture-challenger",
        ):
            content = (
                REPOSITORY_ROOT / ".codex" / "agents" / f"{name}.toml"
            ).read_text(encoding="utf-8")
            self.assertIn('sandbox_mode = "read-only"', content)
            for forbidden in (
                "approval_policy",
                "model =",
                "model_reasoning_effort",
                "mcp_servers",
            ):
                self.assertNotIn(forbidden, content)
            self.assertIn("Never", content)

        report = dependencies.inspect_repository(REPOSITORY_ROOT)
        self.assertNotIn("project_agents", report)
        self.assertEqual(
            set(report["fastlane_skills"]["items"]),
            {
                "build-fastlane",
                "explain-fastlane",
                "fastlane",
                "launch-fastlane",
                "maintain-fastlane",
                "operate-fastlane-aws",
                "plan-fastlane",
            },
        )

    def test_coordinator_skill_keeps_plain_language_init_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            shutil.copytree(REPOSITORY_ROOT, project)
            path = project / ".agents/skills/fastlane/agents/openai.yaml"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "init template", "begin setup"
                ),
                encoding="utf-8",
            )
            report = dependencies.inspect_repository(project)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn(
            "FASTLANE_SKILL_INVALID",
            {item["code"] for item in report["diagnostics"]},
        )

    def test_repository_hooks_are_not_fastlane_dependency_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            shutil.copytree(REPOSITORY_ROOT, project)
            config = project / ".codex" / "config.toml"
            config.write_text("[features]\nhooks = false\n", encoding="utf-8")
            report = dependencies.inspect_repository(project)
        self.assertEqual(report["status"], "READY", report["diagnostics"])
        self.assertNotIn("hook_review", report["aws_agent_toolkit"])


if __name__ == "__main__":
    unittest.main()
