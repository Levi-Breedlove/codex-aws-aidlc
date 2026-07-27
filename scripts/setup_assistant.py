#!/usr/bin/env python3
"""Check Fastlane prerequisites and render instruction-only owner guidance.

The checker runs only bounded version and login-status probes. It never installs
software, changes Codex plugin state, approves hooks, reads credentials, or
accesses an AWS account. Codex-session capability observations may be supplied
through the allowlisted, ephemeral stdin interface.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fastlane_presenter import PresentationError, render_prerequisite_update


OFFICIAL_AWS_MARKETPLACE = "aws/agent-toolkit-for-aws"
OFFICIAL_AWS_MARKETPLACE_NAME = "agent-toolkit-for-aws"
OFFICIAL_AWS_CORE_IDENTITY = "aws-core@agent-toolkit-for-aws"

CODEX_GUIDE = "https://learn.chatgpt.com/docs/codex/cli#getting-started"
UV_GUIDE = "https://docs.astral.sh/uv/getting-started/installation/"
PYTHON_GUIDE = "https://www.python.org/downloads/"
GIT_GUIDE = "https://git-scm.com/downloads"
AWS_PLUGIN_GUIDE = (
    "https://docs.aws.amazon.com/agent-toolkit/latest/userguide/plugins.html"
)
MARKETPLACE_COMMAND = "codex plugin marketplace add aws/agent-toolkit-for-aws"

SETUP_STATES = (
    "PREREQUISITES_REQUIRED",
    "CODEX_LOGIN_REQUIRED",
    "PLATFORM_SANDBOX_REQUIRED",
    "UV_REQUIRED",
    "AWS_CORE_REQUIRED",
    "AWS_CORE_NATIVE_TRUST_REQUIRED",
    "PREREQUISITES_READY",
)
MAX_EVIDENCE_BYTES = 1_000_000
MAX_OUTPUT_BYTES = 16_384
CAPABILITY_RESULTS = {"PASS", "FAIL", "UNAVAILABLE"}
RUNTIME_DISCOVERY_FIELD = "aws_core_runtime_discovery"
RUNTIME_DISCOVERY_KEYS = frozenset(
    {
        "search_status",
        "search_query",
        "search_observed_at",
        "discovered_skill_identifiers",
        "selected_skill_identifier",
        "retrieve_status",
        "retrieved_skill_identifier",
        "retrieve_observed_at",
        "credentials_inspected",
        "aws_account_accessed",
    }
)
CANONICAL_SKILL_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]*")

BOOLEAN_EVIDENCE_FIELDS = frozenset(
    {
        "official_plugin_installed",
        "official_plugin_enabled",
        "official_plugin_loaded_in_session",
        "official_plugin_source_verified",
        "native_hook_review_required",
        "native_hook_review_attested",
        "credentials_inspected",
        "aws_account_accessed",
    }
)
STRING_EVIDENCE_FIELDS = frozenset(
    {
        "observed_marketplace_repository",
        "observed_plugin_source",
        "observed_plugin_identity",
        "retrieve_skill_result",
        "retrieve_skill_identifier",
        "search_documentation_result",
        "search_documentation_query",
    }
)
STRING_LIST_EVIDENCE_FIELDS = frozenset({"search_documentation_references"})
SESSION_EVIDENCE_FIELDS = frozenset(
    BOOLEAN_EVIDENCE_FIELDS
    | STRING_EVIDENCE_FIELDS
    | STRING_LIST_EVIDENCE_FIELDS
    | {RUNTIME_DISCOVERY_FIELD}
)

Which = Callable[[str], str | None]
Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class SetupError(RuntimeError):
    """Raised when setup input is missing, malformed, or unsafe."""


def _safe_text(value: str, label: str, *, maximum: int = 500) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum or any(ord(char) < 32 for char in cleaned):
        raise SetupError(f"stdin evidence field {label!r} is invalid")
    if re.search(r"(?:secret|token|password|access[_-]?key)\s*[:=]", cleaned, re.I):
        raise SetupError(f"stdin evidence field {label!r} may contain secret material")
    return cleaned


def _parse_runtime_discovery(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != RUNTIME_DISCOVERY_KEYS:
        raise SetupError(
            "aws_core_runtime_discovery must contain the exact runtime discovery fields"
        )
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"credentials_inspected", "aws_account_accessed"}:
            if not isinstance(item, bool):
                raise SetupError(f"stdin evidence field {key!r} must be boolean")
            result[key] = item
        elif key == "discovered_skill_identifiers":
            if not isinstance(item, list) or not all(isinstance(entry, str) for entry in item):
                raise SetupError(f"stdin evidence field {key!r} must be a string list")
            identifiers = [_safe_text(entry, key) for entry in item]
            if len(identifiers) != len(set(identifiers)):
                raise SetupError("discovered_skill_identifiers must not contain duplicates")
            if any(CANONICAL_SKILL_IDENTIFIER.fullmatch(entry) is None for entry in identifiers):
                raise SetupError("discovered_skill_identifiers must contain canonical identifiers")
            result[key] = identifiers
        else:
            if not isinstance(item, str):
                raise SetupError(f"stdin evidence field {key!r} must be a string")
            result[key] = _safe_text(item, key)
    for key in ("search_status", "retrieve_status"):
        if result[key] not in CAPABILITY_RESULTS:
            raise SetupError(f"stdin evidence field {key!r} must be PASS, FAIL, or UNAVAILABLE")
    for key in ("selected_skill_identifier", "retrieved_skill_identifier"):
        if CANONICAL_SKILL_IDENTIFIER.fullmatch(result[key]) is None:
            raise SetupError(f"stdin evidence field {key!r} must be a canonical identifier")
    return result


def _observed_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return observed if observed.tzinfo is not None else None


def _runtime_discovery_ready(evidence: Mapping[str, Any]) -> bool:
    discovery = evidence.get(RUNTIME_DISCOVERY_FIELD)
    if not isinstance(discovery, Mapping):
        return False
    discovered = discovery.get("discovered_skill_identifiers")
    selected = discovery.get("selected_skill_identifier")
    searched_at = _observed_datetime(discovery.get("search_observed_at"))
    retrieved_at = _observed_datetime(discovery.get("retrieve_observed_at"))
    return bool(
        discovery.get("search_status") == "PASS"
        and discovery.get("search_query") == "AWS skills"
        and isinstance(discovered, list)
        and discovered
        and selected in discovered
        and discovery.get("retrieve_status") == "PASS"
        and discovery.get("retrieved_skill_identifier") == selected
        and searched_at is not None
        and retrieved_at is not None
        and searched_at <= retrieved_at
        and discovery.get("credentials_inspected") is False
        and discovery.get("aws_account_accessed") is False
    )


def read_session_evidence(stream: Any) -> dict[str, Any]:
    """Read allowlisted, non-sensitive Codex-session observations."""

    payload = stream.read(MAX_EVIDENCE_BYTES + 1)
    if not isinstance(payload, str) or not payload.strip():
        raise SetupError("--evidence-stdin requires one JSON object on stdin")
    if len(payload.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise SetupError("stdin evidence exceeds the 1 MB limit")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SetupError("stdin evidence is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise SetupError("stdin evidence must be a JSON object")
    unknown = sorted(set(parsed) - SESSION_EVIDENCE_FIELDS)
    if unknown:
        raise SetupError("stdin evidence contains unknown field(s): " + ", ".join(unknown))

    result: dict[str, Any] = {}
    for key, value in parsed.items():
        if key == RUNTIME_DISCOVERY_FIELD:
            result[key] = _parse_runtime_discovery(value)
        elif key in BOOLEAN_EVIDENCE_FIELDS:
            if not isinstance(value, bool):
                raise SetupError(f"stdin evidence field {key!r} must be boolean")
            result[key] = value
        elif key in STRING_EVIDENCE_FIELDS:
            if not isinstance(value, str):
                raise SetupError(f"stdin evidence field {key!r} must be a string")
            result[key] = _safe_text(value, key)
        else:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise SetupError(f"stdin evidence field {key!r} must be a string list")
            result[key] = [_safe_text(item, key, maximum=2_000) for item in value]

    for field in ("retrieve_skill_result", "search_documentation_result"):
        if field in result and result[field] not in CAPABILITY_RESULTS:
            raise SetupError(f"stdin evidence field {field!r} must be PASS, FAIL, or UNAVAILABLE")
    for reference in result.get("search_documentation_references", []):
        if re.fullmatch(r"https://(?:docs\.)?aws\.amazon\.com/\S+", reference) is None:
            raise SetupError("search_documentation_references must use official AWS HTTPS URLs")
    return result


def canonical_root(root: Path) -> Path:
    """Resolve a repository root with a safe Fastlane manifest."""

    try:
        resolved = root.expanduser().resolve(strict=True)
    except OSError as exc:
        raise SetupError("Repository root does not exist") from exc
    if not resolved.is_dir():
        raise SetupError("Repository root must be a directory")
    manifest = resolved / "bootstrap.manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise SetupError("bootstrap.manifest.json is missing or unsafe")
    try:
        parsed = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SetupError("bootstrap.manifest.json is unreadable or invalid") from exc
    if not isinstance(parsed, dict):
        raise SetupError("bootstrap.manifest.json must contain an object")
    return resolved


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _default_runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=None,
    )


def _probe(
    name: str,
    arguments: Sequence[str],
    root: Path,
    *,
    which: Which,
    runner: Runner,
) -> tuple[bool, bool, str]:
    candidate = which(name)
    if not candidate:
        return False, False, ""
    try:
        resolved = Path(candidate).expanduser().resolve(strict=True)
    except OSError:
        return False, False, ""
    if not resolved.is_file() or is_within(resolved, root):
        return False, False, ""
    try:
        completed = runner([str(resolved), *arguments])
    except (OSError, subprocess.SubprocessError):
        return True, False, ""
    combined = f"{completed.stdout or ''}\n{completed.stderr or ''}".strip()
    encoded = combined.encode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES]
    return True, completed.returncode == 0, encoded.decode("utf-8", errors="replace")


def _version_at_least(output: str, minimum: tuple[int, ...]) -> bool:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?", output)
    if match is None:
        return False
    observed = tuple(int(part or 0) for part in match.groups())
    padded = observed + (0,) * max(0, len(minimum) - len(observed))
    return padded[: len(minimum)] >= minimum


def inspect_local_prerequisites(
    root: Path,
    *,
    which: Which = shutil.which,
    runner: Runner = _default_runner,
    system: str | None = None,
    release: str | None = None,
) -> dict[str, Any]:
    """Run only allowlisted read-only local prerequisite probes."""

    checked_root = canonical_root(root)
    system_name = (system or platform.system()).upper()
    release_name = (release or platform.release()).casefold()
    is_wsl = system_name == "LINUX" and "microsoft" in release_name
    is_wsl2 = is_wsl and "wsl2" in release_name

    codex_available, codex_ok, codex_output = _probe(
        "codex", ["--version"], checked_root, which=which, runner=runner
    )
    login_available, login_ok, _ = _probe(
        "codex", ["login", "status"], checked_root, which=which, runner=runner
    )
    git_available, git_ok, _ = _probe(
        "git", ["--version"], checked_root, which=which, runner=runner
    )

    python_names = (
        ("python3", "python", "py")
        if system_name.startswith("WINDOWS")
        else ("python3", "python")
    )
    python_available = False
    python_supported = False
    for name in python_names:
        arguments = ["-3", "--version"] if name == "py" else ["--version"]
        available, ok, output = _probe(name, arguments, checked_root, which=which, runner=runner)
        if not available:
            continue
        python_available = True
        if ok and _version_at_least(output, (3, 11)):
            python_supported = True
            break

    uv_available, uv_ok, _ = _probe(
        "uvx", ["--version"], checked_root, which=which, runner=runner
    )
    bubblewrap_required = system_name == "LINUX"
    bwrap_available, bwrap_ok, _ = (
        _probe("bwrap", ["--version"], checked_root, which=which, runner=runner)
        if bubblewrap_required
        else (True, True, "")
    )
    return {
        "repository_ready": True,
        "codex_cli_available": codex_available,
        "codex_cli_supported": codex_available and codex_ok and _version_at_least(codex_output, (0, 1)),
        "codex_login_status_supported": login_available,
        "codex_login_ready": login_available and login_ok,
        "git_available": git_available and git_ok,
        "python_available": python_available,
        "python_version_supported": python_supported,
        "uvx_available": uv_available and uv_ok,
        "bubblewrap_required": bubblewrap_required,
        "bubblewrap_available": bwrap_available and bwrap_ok,
        "platform_supported": not is_wsl or is_wsl2,
        "platform_family": "WINDOWS" if system_name.startswith("WINDOWS") else "MACOS" if system_name == "DARWIN" else "LINUX",
        "is_wsl2": is_wsl2,
        "pipx_available": bool(which("pipx")),
        "winget_available": bool(which("winget")),
        "brew_available": bool(which("brew")),
        "safe_probes_executed": True,
    }


def _codex_step(platform_family: str) -> dict[str, Any]:
    if platform_family == "WINDOWS":
        commands = ["irm https://chatgpt.com/codex/install.ps1 | iex", "codex --version"]
    else:
        commands = ["curl -fsSL https://chatgpt.com/codex/install.sh | sh", "codex --version"]
    return {"label": "Install or update Codex CLI", "commands": commands, "guide": CODEX_GUIDE}


def _uv_step(evidence: Mapping[str, Any]) -> dict[str, Any]:
    family = str(evidence.get("platform_family", "LINUX"))
    if evidence.get("pipx_available") is True:
        install = "pipx install uv"
    elif family == "WINDOWS" and evidence.get("winget_available") is True:
        install = "winget install --id astral-sh.uv --exact --source winget"
    elif family == "WINDOWS":
        install = 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    elif family == "MACOS" and evidence.get("brew_available") is True:
        install = "brew install uv"
    else:
        install = "curl -LsSf https://astral.sh/uv/install.sh | sh"
    return {"label": "Install Astral uv", "commands": [install, "uvx --version"], "guide": UV_GUIDE}


def _aws_core_step() -> dict[str, Any]:
    return {
        "label": "Enable official AWS Core",
        "commands": [MARKETPLACE_COMMAND],
        "guide": AWS_PLUGIN_GUIDE,
        "instruction": (
            "Open `/plugins`, select AWS Core under Agent Toolkit for AWS, restart Codex, "
            "then send `init template`. Codex will search the runtime AWS skill catalog "
            "and retrieve one returned skill without AWS credentials."
        ),
    }


def _missing_categories(evidence: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    family = str(evidence.get("platform_family", "LINUX"))
    missing: list[tuple[str, dict[str, Any]]] = []
    if not evidence.get("codex_cli_available") or not evidence.get("codex_cli_supported"):
        missing.append(("CODEX", _codex_step(family)))
    elif not evidence.get("codex_login_ready"):
        missing.append(
            (
                "LOGIN",
                {
                    "label": "Sign in to Codex CLI",
                    "commands": ["codex login", "codex login status"],
                    "guide": CODEX_GUIDE,
                },
            )
        )
    if not evidence.get("git_available"):
        missing.append(("LOCAL", {"label": "Install Git", "commands": ["git --version"], "guide": GIT_GUIDE}))
    if not evidence.get("python_available") or not evidence.get("python_version_supported"):
        missing.append(
            ("LOCAL", {"label": "Install Python 3.11 or newer", "commands": ["python3 --version", "python --version"], "guide": PYTHON_GUIDE})
        )
    if not evidence.get("platform_supported"):
        missing.append(
            (
                "SANDBOX",
                {
                    "label": "Use WSL2 instead of WSL1",
                    "commands": ["wsl --set-version <distribution> 2"],
                    "guide": CODEX_GUIDE,
                },
            )
        )
    elif evidence.get("bubblewrap_required") and not evidence.get("bubblewrap_available"):
        missing.append(
            (
                "SANDBOX",
                {
                    "label": "Install the Linux Codex sandbox prerequisite",
                    "commands": ["sudo apt update", "sudo apt install bubblewrap", "command -v bwrap", "bwrap --version"],
                    "guide": CODEX_GUIDE,
                },
            )
        )
    if not evidence.get("uvx_available"):
        missing.append(("UV", _uv_step(evidence)))

    official_source = (
        evidence.get("official_plugin_loaded_in_session") is True
        and evidence.get("official_plugin_source_verified") is True
        and evidence.get("observed_marketplace_repository") == OFFICIAL_AWS_MARKETPLACE
        and evidence.get("observed_plugin_source") == OFFICIAL_AWS_MARKETPLACE_NAME
        and evidence.get("observed_plugin_identity") == OFFICIAL_AWS_CORE_IDENTITY
    )
    if not official_source:
        missing.append(("AWS_CORE", _aws_core_step()))
    elif evidence.get("native_hook_review_required") is True and evidence.get("native_hook_review_attested") is not True:
        missing.append(
            (
                "TRUST",
                {
                    "label": "Review the official AWS Core hook in Codex",
                    "commands": [],
                    "guide": AWS_PLUGIN_GUIDE,
                    "instruction": "Open `/hooks`, verify the source is official AWS Core, and personally accept or reject Codex's native trust prompt.",
                },
            )
        )
    else:
        no_account_access = (
            evidence.get("credentials_inspected") is False
            and evidence.get("aws_account_accessed") is False
        )
        if not (_runtime_discovery_ready(evidence) and no_account_access):
            missing.append(("AWS_CORE", _aws_core_step()))
    return missing


def reduce_prerequisites(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce local and ephemeral observations to one deterministic setup state."""

    missing = _missing_categories(evidence)
    categories = {category for category, _ in missing}
    if not missing:
        state = "PREREQUISITES_READY"
    elif len(categories) > 1 or "LOCAL" in categories or "CODEX" in categories:
        state = "PREREQUISITES_REQUIRED"
    elif categories == {"LOGIN"}:
        state = "CODEX_LOGIN_REQUIRED"
    elif categories == {"SANDBOX"}:
        state = "PLATFORM_SANDBOX_REQUIRED"
    elif categories == {"UV"}:
        state = "UV_REQUIRED"
    elif categories == {"TRUST"}:
        state = "AWS_CORE_NATIVE_TRUST_REQUIRED"
    else:
        state = "AWS_CORE_REQUIRED"

    return {
        "schema_version": 4,
        "mode": "INSTRUCTIONS_ONLY",
        "state": state,
        "owner_action_id": (
            "ANSWER_PROJECT_SETUP_QUESTIONS"
            if state == "PREREQUISITES_READY"
            else "COMPLETE_PREREQUISITE_CHECKLIST"
        ),
        "owner_action_required": True,
        "checklist": [step for _, step in missing],
        "aws_core_status": "AVAILABLE" if state == "PREREQUISITES_READY" else "REQUIRED",
        "aws_core_runtime_discovery": "CURRENT" if state == "PREREQUISITES_READY" else "REQUIRED",
        "aws_credentials": "NOT_INSPECTED",
        "aws_access": "NOT_USED",
        "aws_authorization": "NONE",
        "executed_external_commands": "READ_ONLY_VERSION_AND_LOGIN_STATUS_ONLY",
        "repository_writes": "NONE",
        "user_state_persisted_in_repository": False,
    }


def opening_greeting() -> str:
    return """Welcome to AWS Codex Fastlane.

Fastlane turns your idea into approved requirements, a current AWS-informed
technical design, and an autonomous local build inside the boundary you approve.
Setup did not inspect AWS credentials or access an AWS account.

Reply once with:
- Project name:
- Preferred AWS Region: (or "recommend one")
- Development budget: (a currency cap, or "minimize cost; no hard cap")"""


def render_setup_response(report: Mapping[str, Any]) -> str:
    if report.get("state") == "PREREQUISITES_READY":
        return opening_greeting()
    return render_prerequisite_update(report)


def _error_report(message: str) -> dict[str, Any]:
    return {
        "schema_version": 4,
        "mode": "INSTRUCTIONS_ONLY",
        "state": "PREREQUISITES_REQUIRED",
        "owner_action_id": "COMPLETE_PREREQUISITE_CHECKLIST",
        "owner_action_required": True,
        "checklist": [
            {
                "label": "Open a complete Fastlane repository",
                "commands": [],
                "instruction": message,
            }
        ],
        "aws_core_status": "NOT_CHECKED",
        "aws_credentials": "NOT_INSPECTED",
        "aws_access": "NOT_USED",
        "aws_authorization": "NONE",
        "executed_external_commands": "NONE",
        "repository_writes": "NONE",
        "user_state_persisted_in_repository": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("welcome", help="Print the post-prerequisite welcome")
    prerequisites = subparsers.add_parser(
        "prerequisites", help="Run read-only prerequisite checks"
    )
    prerequisites.add_argument("--root", type=Path, default=Path.cwd())
    prerequisites.add_argument("--json", action="store_true")
    prerequisites.add_argument("--evidence-stdin", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "welcome":
        print(opening_greeting())
        return 0
    try:
        evidence = inspect_local_prerequisites(args.root)
        if args.evidence_stdin:
            evidence.update(read_session_evidence(sys.stdin))
        report = reduce_prerequisites(evidence)
    except (SetupError, PresentationError) as exc:
        report = _error_report(str(exc))
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(render_setup_response(report), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_setup_response(report))
    return 0 if report["state"] == "PREREQUISITES_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
