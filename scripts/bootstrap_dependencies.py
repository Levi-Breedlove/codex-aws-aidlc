#!/usr/bin/env python3
"""Validate Fastlane repository assets and its official AWS Core contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
try:
    from fastlane_stdio import configure_utf8_standard_streams
except ModuleNotFoundError:  # pragma: no cover - package-style test import
    from scripts.fastlane_stdio import configure_utf8_standard_streams

from typing import Any


AWS_TOOLKIT_REPOSITORY = "https://github.com/aws/agent-toolkit-for-aws"
AWS_TOOLKIT_MARKETPLACE = "aws/agent-toolkit-for-aws"
AWS_CORE_PLUGIN_ID = "aws-core@agent-toolkit-for-aws"
AWS_CORE_MANAGEMENT_COMMAND = "/plugins"
AWS_CORE_RUNTIME_COMMAND = "uvx"
AWS_CORE_RUNTIME_PACKAGE = "uv"
AWS_CORE_REQUIRED_CAPABILITIES = ("retrieve_skill", "search_documentation")
SETUP_ASSISTANT_SCRIPT = "scripts/setup_assistant.py"
SETUP_STATES = (
    "PREREQUISITES_REQUIRED",
    "CODEX_LOGIN_REQUIRED",
    "PLATFORM_SANDBOX_REQUIRED",
    "UV_REQUIRED",
    "AWS_CORE_REQUIRED",
    "AWS_CORE_NATIVE_TRUST_REQUIRED",
    "PREREQUISITES_READY",
)

REQUIRED_SKILLS = (
    "build-fastlane",
    "explain-fastlane",
    "fastlane",
    "launch-fastlane",
    "maintain-fastlane",
    "operate-fastlane-aws",
    "plan-fastlane",
)
SKILL_IMPLICIT_POLICY = {
    "build-fastlane": "false",
    "explain-fastlane": "false",
    "fastlane": "true",
    "launch-fastlane": "false",
    "maintain-fastlane": "true",
    "operate-fastlane-aws": "false",
    "plan-fastlane": "false",
}


def diagnostic(code: str, message: str, path: str | None = None) -> dict[str, str]:
    item = {"code": code, "message": message}
    if path is not None:
        item["path"] = path
    return item


def inspect_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    diagnostics: list[dict[str, str]] = []
    setup_assistant_path = root / SETUP_ASSISTANT_SCRIPT
    if not setup_assistant_path.is_file() or setup_assistant_path.is_symlink():
        diagnostics.append(
            diagnostic(
                "FASTLANE_SETUP_ASSISTANT_MISSING",
                "The instruction-only setup assistant is missing or unsafe.",
                SETUP_ASSISTANT_SCRIPT,
            )
        )
    skill_states: dict[str, str] = {}
    skill_descriptions: dict[str, str] = {}
    for name in REQUIRED_SKILLS:
        skill_root = root / ".agents" / "skills" / name
        required = (skill_root / "SKILL.md", skill_root / "agents" / "openai.yaml")
        state = "READY"
        for path in required:
            if not path.is_file() or path.is_symlink():
                state = "BLOCKED"
                diagnostics.append(
                    diagnostic(
                        "FASTLANE_SKILL_MISSING",
                        f"Required repo skill asset is missing or unsafe for {name}.",
                        path.relative_to(root).as_posix(),
                    )
                )
        if state == "READY":
            relative_skill = f".agents/skills/{name}/SKILL.md"
            try:
                skill_text = required[0].read_text(encoding="utf-8")
                yaml_text = required[1].read_text(encoding="utf-8")
                if not skill_text.startswith("---\n") or "\n---\n" not in skill_text[4:]:
                    raise ValueError("SKILL.md must begin with complete YAML frontmatter")
                frontmatter = skill_text.split("---", 2)[1]
                name_match = re.search(r"^name:\s*([^\r\n]+)$", frontmatter, re.MULTILINE)
                description_match = re.search(
                    r"^description:\s*([^\r\n]+)$", frontmatter, re.MULTILINE
                )
                if name_match is None or name_match.group(1).strip() != name:
                    raise ValueError("SKILL.md frontmatter name must match its directory")
                if description_match is None or not description_match.group(1).strip():
                    raise ValueError("SKILL.md requires a non-empty trigger description")
                skill_descriptions[name] = description_match.group(1).strip()
                for field in ("display_name", "short_description", "default_prompt"):
                    if re.search(rf"^\s*{field}:\s*.+$", yaml_text, re.MULTILINE) is None:
                        raise ValueError(f"openai.yaml is missing {field}")
                policy = SKILL_IMPLICIT_POLICY[name]
                if (
                    re.search(
                        rf"^\s*allow_implicit_invocation:\s*{policy}\s*$",
                        yaml_text,
                        re.MULTILINE,
                    )
                    is None
                ):
                    raise ValueError(
                        f"openai.yaml allow_implicit_invocation must be {policy}"
                    )
                if name == "fastlane" and "init template" not in yaml_text:
                    raise ValueError("fastlane default prompt must expose init template")
            except (OSError, ValueError) as exc:
                state = "BLOCKED"
                diagnostics.append(
                    diagnostic("FASTLANE_SKILL_INVALID", str(exc), relative_skill)
                )
        skill_states[name] = state

    if len(set(skill_descriptions.values())) != len(skill_descriptions):
        diagnostics.append(
            diagnostic(
                "FASTLANE_SKILL_TRIGGER_COLLISION",
                "Repo skill trigger descriptions must be distinct.",
                ".agents/skills",
            )
        )

    ready = not diagnostics
    return {
        "schema_version": 2,
        "status": "READY" if ready else "BLOCKED",
        "aws_agent_toolkit": {
            "repository": AWS_TOOLKIT_REPOSITORY,
            "dependency_policy": "OFFICIAL_CURRENT",
            "marketplace": "agent-toolkit-for-aws",
            "marketplace_slug": AWS_TOOLKIT_MARKETPLACE,
            "marketplace_registration_command": [
                "codex",
                "plugin",
                "marketplace",
                "add",
                AWS_TOOLKIT_MARKETPLACE,
            ],
            "plugin_identity": AWS_CORE_PLUGIN_ID,
            "plugin": "aws-core",
            "installation_policy": "OWNER_MANAGED",
            "setup_mode": "INSTRUCTIONS_ONLY",
            "availability_policy": "REQUIRED_FOR_FRESH_INITIALIZATION",
            "version_policy": "OFFICIAL_CURRENT_NO_TEMPLATE_PIN",
            "setup_assistant": {
                "status": "SETUP_ASSISTANCE_AVAILABLE",
                "mode": "INSTRUCTIONS_ONLY",
                "script": SETUP_ASSISTANT_SCRIPT,
                "states": list(SETUP_STATES),
                "automatic_runtime_installation": False,
                "package_manager_execution": False,
                "runtime_probe_execution": True,
                "user_state_persisted_in_repository": False,
                "initialized_resume_skips_prerequisites": True,
            },
            "runtime_verification": {
                "status": "NOT_CHECKED",
                "management_command": AWS_CORE_MANAGEMENT_COMMAND,
                "expected_plugin_identity": AWS_CORE_PLUGIN_ID,
                "required_capabilities": list(AWS_CORE_REQUIRED_CAPABILITIES),
                "automatic_marketplace_registration": False,
                "automatic_session_launch": False,
                "required_runtime_command": AWS_CORE_RUNTIME_COMMAND,
                "runtime_package": AWS_CORE_RUNTIME_PACKAGE,
                "automatic_runtime_installation": False,
                "required_at_boot": True,
                "required_only_for_fresh_initialization": True,
                "required_evidence_phases": ["DESIGN-10", "AWS-10"],
            },
        },
        "fastlane_skills": {
            "status": "READY" if all(state == "READY" for state in skill_states.values()) else "BLOCKED",
            "items": skill_states,
        },
        "diagnostics": diagnostics,
    }


def print_human(report: dict[str, Any]) -> None:
    toolkit = report["aws_agent_toolkit"]
    print(f"Bootstrap dependencies: {report['status']}")
    print(f"Fastlane skills: {report['fastlane_skills']['status']}")
    print(
        "AWS Core dependency: OFFICIAL_CURRENT_NO_TEMPLATE_PIN from "
        f"{toolkit['marketplace_slug']}"
    )
    runtime = toolkit["runtime_verification"]
    print(
        "AWS Core runtime: NOT CHECKED; manage with "
        f"{runtime['management_command']} during fresh-template prerequisites; "
        f"runtime {runtime['required_runtime_command']} is owner managed"
    )
    for item in report["diagnostics"]:
        location = f" ({item['path']})" if "path" in item else ""
        print(f"- {item['code']}: {item['message']}{location}")


def main(argv: list[str] | None = None) -> int:
    configure_utf8_standard_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = inspect_repository(args.root)
    except OSError as exc:
        print(f"Dependency check failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
    return 0 if report["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
