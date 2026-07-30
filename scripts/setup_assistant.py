#!/usr/bin/env python3
"""Check Fastlane prerequisites and render instruction-only owner guidance.

The checker runs only bounded capability, version, and login-status probes. It never installs
software, changes Codex plugin state, approves hooks, reads credentials, or
accesses an AWS account. Codex-session capability observations may be supplied
through the allowlisted, ephemeral stdin interface.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fastlane_stdio import configure_utf8_standard_streams
from fastlane_presenter import PresentationError, render_prerequisite_update
from fastlane_process import resolve_trusted_git


OFFICIAL_AWS_MARKETPLACE = "aws/agent-toolkit-for-aws"
OFFICIAL_AWS_MARKETPLACE_NAME = "agent-toolkit-for-aws"
OFFICIAL_AWS_CORE_IDENTITY = "aws-core@agent-toolkit-for-aws"
HOOK_EXAMPLE_RELATIVE = Path(".codex/hooks.fastlane.example.json")
HOOK_CONFIG_RELATIVE = Path(".codex/hooks.json")
MAX_HOOK_CONFIG_BYTES = 128 * 1024
HOOK_EVENT_MODES = {
    "SessionStart": "session-start",
    "PreToolUse": "pre-tool-use",
    "PermissionRequest": "permission-request",
    "PostToolUse": "post-tool-use",
    "Stop": "stop",
}
HOOK_LAUNCHER_CODE = (
    "import pathlib,runpy,sys; "
    "roots=[p for p in (pathlib.Path.cwd(),*pathlib.Path.cwd().parents) "
    "if (p/'bootstrap.manifest.json').is_file() and "
    "(p/'scripts/bootstrap_doctor.py').is_file()]; "
    "len(roots)==1 or sys.exit('Fastlane root is missing or ambiguous'); "
    "hook=roots[0]/'.codex/hooks/fastlane_hook.py'; "
    "hook.is_file() or sys.exit('Fastlane hook is missing'); "
    "sys.argv=[str(hook),sys.argv[1]]; "
    "runpy.run_path(str(hook),run_name='__main__')"
)
WINDOWS_HOOK_SHELL_META = frozenset('&|<>^%!()"\r\n')

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
MAX_PREREQUISITE_REPORT_BYTES = 16_384
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


READY_PREREQUISITE_REPORT: dict[str, Any] = {
    "schema_version": 4,
    "mode": "INSTRUCTIONS_ONLY",
    "state": "PREREQUISITES_READY",
    "owner_action_id": "ANSWER_PROJECT_SETUP_QUESTIONS",
    "owner_action_required": True,
    "checklist": [],
    "aws_core_status": "AVAILABLE",
    "aws_core_runtime_discovery": "CURRENT",
    "aws_credentials": "NOT_INSPECTED",
    "aws_access": "NOT_USED",
    "aws_authorization": "NONE",
    "executed_external_commands": "READ_ONLY_VERSION_AND_LOGIN_STATUS_ONLY",
    "repository_writes": "NONE",
    "user_state_persisted_in_repository": False,
}


def validate_ready_prerequisite_report(value: object) -> dict[str, Any]:
    """Validate the exact credential-free setup reduction accepted by bootstrap."""

    if not isinstance(value, dict) or set(value) != set(READY_PREREQUISITE_REPORT):
        raise SetupError("prerequisite report must use the exact current ready schema")
    for key, expected in READY_PREREQUISITE_REPORT.items():
        observed = value[key]
        if type(observed) is not type(expected) or observed != expected:
            raise SetupError(
                f"prerequisite report field {key!r} does not prove current readiness"
            )
    return dict(value)


def read_ready_prerequisite_report(stream: Any) -> dict[str, Any]:
    """Read one bounded ready report without persisting session observations."""

    payload = stream.read(MAX_PREREQUISITE_REPORT_BYTES + 1)
    if not isinstance(payload, str) or not payload.strip():
        raise SetupError("--prerequisite-report-stdin requires one JSON object")
    if len(payload.encode("utf-8")) > MAX_PREREQUISITE_REPORT_BYTES:
        raise SetupError("prerequisite report exceeds the 16 KB limit")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SetupError("prerequisite report is not valid JSON") from exc
    return validate_ready_prerequisite_report(parsed)


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
            if not isinstance(item, list) or not all(
                isinstance(entry, str) for entry in item
            ):
                raise SetupError(f"stdin evidence field {key!r} must be a string list")
            identifiers = [_safe_text(entry, key) for entry in item]
            if len(identifiers) != len(set(identifiers)):
                raise SetupError(
                    "discovered_skill_identifiers must not contain duplicates"
                )
            if any(
                CANONICAL_SKILL_IDENTIFIER.fullmatch(entry) is None
                for entry in identifiers
            ):
                raise SetupError(
                    "discovered_skill_identifiers must contain canonical identifiers"
                )
            result[key] = identifiers
        else:
            if not isinstance(item, str):
                raise SetupError(f"stdin evidence field {key!r} must be a string")
            result[key] = _safe_text(item, key)
    for key in ("search_status", "retrieve_status"):
        if result[key] not in CAPABILITY_RESULTS:
            raise SetupError(
                f"stdin evidence field {key!r} must be PASS, FAIL, or UNAVAILABLE"
            )
    for key in ("selected_skill_identifier", "retrieved_skill_identifier"):
        if CANONICAL_SKILL_IDENTIFIER.fullmatch(result[key]) is None:
            raise SetupError(
                f"stdin evidence field {key!r} must be a canonical identifier"
            )
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
        raise SetupError(
            "stdin evidence contains unknown field(s): " + ", ".join(unknown)
        )

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
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise SetupError(f"stdin evidence field {key!r} must be a string list")
            result[key] = [_safe_text(item, key, maximum=2_000) for item in value]

    for field in ("retrieve_skill_result", "search_documentation_result"):
        if field in result and result[field] not in CAPABILITY_RESULTS:
            raise SetupError(
                f"stdin evidence field {field!r} must be PASS, FAIL, or UNAVAILABLE"
            )
    for reference in result.get("search_documentation_references", []):
        if re.fullmatch(r"https://(?:docs\.)?aws\.amazon\.com/\S+", reference) is None:
            raise SetupError(
                "search_documentation_references must use official AWS HTTPS URLs"
            )
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


def _is_link_or_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SetupError("Unable to inspect local hook configuration path") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(file_attributes & reparse_flag)


def _trusted_hook_interpreter(root: Path, interpreter: Path) -> Path:
    raw = interpreter.expanduser()
    if not raw.is_absolute():
        raise SetupError("Fastlane hooks require an absolute trusted Python")
    try:
        lexical = Path(os.path.abspath(os.fspath(raw)))
        resolved = lexical.resolve(strict=True)
        cwd_lexical = Path(os.path.abspath(os.fspath(Path.cwd())))
        cwd_resolved = cwd_lexical.resolve(strict=True)
    except OSError as exc:
        raise SetupError("Fastlane hooks require an available trusted Python") from exc
    if not resolved.is_file() or any(
        is_within(candidate, boundary)
        for candidate in (lexical, resolved)
        for boundary in (root, cwd_lexical, cwd_resolved)
    ):
        raise SetupError(
            "Fastlane hooks require trusted Python outside the project and current working directory"
        )
    if any(character in WINDOWS_HOOK_SHELL_META for character in str(resolved)):
        raise SetupError(
            "Fastlane hooks require a trusted Python path without shell metacharacters"
        )
    return resolved


def _hook_configuration_text(root: Path, interpreter: Path) -> str:
    codex_directory = root / ".codex"
    example = root / HOOK_EXAMPLE_RELATIVE
    if (
        not codex_directory.is_dir()
        or _is_link_or_reparse_point(codex_directory)
        or not example.is_file()
        or _is_link_or_reparse_point(example)
    ):
        raise SetupError("Fastlane hook template path is missing or unsafe")
    try:
        with example.open("rb") as stream:
            raw = stream.read(MAX_HOOK_CONFIG_BYTES + 1)
    except OSError as exc:
        raise SetupError("Fastlane hook template is unreadable") from exc
    if len(raw) > MAX_HOOK_CONFIG_BYTES:
        raise SetupError("Fastlane hook template exceeds its size limit")
    try:
        configured = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SetupError("Fastlane hook template is invalid") from exc
    hooks = configured.get("hooks") if isinstance(configured, dict) else None
    if not isinstance(hooks, dict):
        raise SetupError("Fastlane hook template has no hook map")

    trusted = str(_trusted_hook_interpreter(root, interpreter))
    counts = {"command": 0, "commandWindows": 0}
    try:
        if set(hooks) != set(HOOK_EVENT_MODES):
            raise SetupError("Fastlane hook template event map is invalid")
        for event, groups in hooks.items():
            mode = HOOK_EVENT_MODES[event]
            commands = {
                "command": shlex.join([trusted, "-c", HOOK_LAUNCHER_CODE, mode]),
                "commandWindows": subprocess.list2cmdline(
                    [trusted, "-c", HOOK_LAUNCHER_CODE, mode]
                ),
            }
            for group in groups:
                for hook in group["hooks"]:
                    for field, command in commands.items():
                        if hook[field] != "":
                            raise SetupError(
                                "Fastlane hook template command must remain disabled"
                            )
                        hook[field] = command
                        counts[field] += 1
    except (KeyError, TypeError) as exc:
        raise SetupError("Fastlane hook template structure is invalid") from exc
    if not counts["command"] or counts["command"] != counts["commandWindows"]:
        raise SetupError("Fastlane hook template is incomplete")
    return json.dumps(configured, indent=2, ensure_ascii=False) + "\n"


def configure_local_hooks(
    root: Path,
    *,
    interpreter: Path = Path(sys.executable),
    replace: bool = False,
) -> Path:
    """Generate ignored local hooks with one absolute trusted interpreter."""

    checked_root = canonical_root(root)
    content = _hook_configuration_text(checked_root, interpreter)
    codex_directory = checked_root / ".codex"
    target = checked_root / HOOK_CONFIG_RELATIVE
    target_is_link = _is_link_or_reparse_point(target)
    if target_is_link or (target.exists() and not target.is_file()):
        raise SetupError("Local Fastlane hook configuration path is unsafe")
    if target.exists() and not replace:
        raise SetupError("Local Fastlane hook configuration already exists")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".hooks.", suffix=".tmp", dir=codex_directory
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        if _is_link_or_reparse_point(codex_directory):
            raise SetupError("Local Fastlane hook directory became unsafe")
        if _is_link_or_reparse_point(target) or (
            target.exists() and (not replace or not target.is_file())
        ):
            raise SetupError("Local Fastlane hook configuration changed before write")
        os.replace(temporary, target)
    except OSError as exc:
        raise SetupError("Unable to write local Fastlane hook configuration") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return target


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


def _probe_git(
    root: Path,
    *,
    which: Which,
    runner: Runner,
) -> tuple[bool, bool, str]:
    try:
        candidate = resolve_trusted_git(root, locator=which)
    except OSError:
        return False, False, ""
    try:
        completed = runner([candidate, "--version"])
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

    codex_available, codex_ok, _ = _probe(
        "codex", ["--version"], checked_root, which=which, runner=runner
    )
    login_available, login_ok, _ = _probe(
        "codex", ["login", "status"], checked_root, which=which, runner=runner
    )
    git_available, git_ok, _ = _probe_git(checked_root, which=which, runner=runner)

    python_names = (
        ("python3", "python", "py")
        if system_name.startswith("WINDOWS")
        else ("python3", "python")
    )
    python_available = False
    python_supported = False
    for name in python_names:
        arguments = ["-3", "--version"] if name == "py" else ["--version"]
        available, ok, output = _probe(
            name, arguments, checked_root, which=which, runner=runner
        )
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
        "codex_cli_supported": codex_available and codex_ok,
        "codex_login_status_supported": login_available,
        "codex_login_ready": login_available and login_ok,
        "git_available": git_available and git_ok,
        "python_available": python_available,
        "python_version_supported": python_supported,
        "uvx_available": uv_available and uv_ok,
        "bubblewrap_required": bubblewrap_required,
        "bubblewrap_available": bwrap_available and bwrap_ok,
        "platform_supported": not is_wsl or is_wsl2,
        "platform_family": "WINDOWS"
        if system_name.startswith("WINDOWS")
        else "MACOS"
        if system_name == "DARWIN"
        else "LINUX",
        "is_wsl2": is_wsl2,
        "pipx_available": bool(which("pipx")),
        "winget_available": bool(which("winget")),
        "brew_available": bool(which("brew")),
        "safe_probes_executed": True,
    }


def _checklist_step(
    label: str,
    *,
    install: Sequence[str] = (),
    action: Sequence[str] = (),
    verify: Sequence[str] = (),
    guide: str | None = None,
    instruction: str | None = None,
) -> dict[str, Any]:
    """Return a compatible checklist row with explicit owner and verification work."""

    result: dict[str, Any] = {
        "label": label,
        "commands": [*install, *action, *verify],
        "install_commands": list(install),
        "action_commands": list(action),
        "verification_commands": list(verify),
    }
    if guide:
        result["guide"] = guide
    if instruction:
        result["instruction"] = instruction
    return result


def _codex_step(platform_family: str) -> dict[str, Any]:
    if platform_family == "WINDOWS":
        install = ["irm https://chatgpt.com/codex/install.ps1 | iex"]
    else:
        install = ["curl -fsSL https://chatgpt.com/codex/install.sh | sh"]
    return _checklist_step(
        "Install or update interactive Codex CLI",
        install=install,
        verify=["codex --version"],
        guide=CODEX_GUIDE,
    )


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
    return _checklist_step(
        "Install Astral uv",
        install=[install],
        verify=["uvx --version"],
        guide=UV_GUIDE,
    )


def _aws_core_step() -> dict[str, Any]:
    return _checklist_step(
        "Enable official AWS Core",
        install=[MARKETPLACE_COMMAND],
        verify=["init template"],
        guide=AWS_PLUGIN_GUIDE,
        instruction=(
            "Open `/plugins`, select AWS Core under Agent Toolkit for AWS, restart Codex, "
            "then send `init template`. Codex will search the runtime AWS skill catalog "
            "and retrieve one returned skill without AWS credentials."
        ),
    )


def _missing_categories(
    evidence: Mapping[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    family = str(evidence.get("platform_family", "LINUX"))
    missing: list[tuple[str, dict[str, Any]]] = []
    if not evidence.get("codex_cli_available") or not evidence.get(
        "codex_cli_supported"
    ):
        missing.append(("CODEX", _codex_step(family)))
    elif not evidence.get("codex_login_ready"):
        missing.append(
            (
                "LOGIN",
                _checklist_step(
                    "Sign in to Codex CLI",
                    action=["codex login"],
                    verify=["codex login status"],
                    guide=CODEX_GUIDE,
                ),
            )
        )
    if not evidence.get("git_available"):
        missing.append(
            (
                "LOCAL",
                _checklist_step(
                    "Install Git",
                    verify=["git --version"],
                    guide=GIT_GUIDE,
                ),
            )
        )
    if not evidence.get("python_available") or not evidence.get(
        "python_version_supported"
    ):
        python_checks = (
            ["py -3 --version", "python --version"]
            if family == "WINDOWS"
            else ["python3 --version", "python --version"]
        )
        missing.append(
            (
                "LOCAL",
                _checklist_step(
                    "Install Python 3.11 or newer",
                    verify=python_checks,
                    guide=PYTHON_GUIDE,
                ),
            )
        )
    if not evidence.get("platform_supported"):
        missing.append(
            (
                "SANDBOX",
                _checklist_step(
                    "Use WSL2 instead of WSL1",
                    action=["wsl --set-version <distribution> 2"],
                    verify=["wsl -l -v"],
                    guide=CODEX_GUIDE,
                ),
            )
        )
    elif evidence.get("bubblewrap_required") and not evidence.get(
        "bubblewrap_available"
    ):
        missing.append(
            (
                "SANDBOX",
                _checklist_step(
                    "Install the Linux Codex sandbox prerequisite",
                    install=["sudo apt update", "sudo apt install bubblewrap"],
                    verify=["command -v bwrap", "bwrap --version"],
                    guide=CODEX_GUIDE,
                ),
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
    elif (
        evidence.get("native_hook_review_required") is True
        and evidence.get("native_hook_review_attested") is not True
    ):
        missing.append(
            (
                "TRUST",
                _checklist_step(
                    "Review the official AWS Core hook in Codex",
                    action=["Open /hooks and review the native trust prompt"],
                    guide=AWS_PLUGIN_GUIDE,
                    instruction="Verify the source is official AWS Core, then personally accept or reject Codex's native trust prompt.",
                ),
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
        "aws_core_status": "AVAILABLE"
        if state == "PREREQUISITES_READY"
        else "REQUIRED",
        "aws_core_runtime_discovery": "CURRENT"
        if state == "PREREQUISITES_READY"
        else "REQUIRED",
        "aws_credentials": "NOT_INSPECTED",
        "aws_access": "NOT_USED",
        "aws_authorization": "NONE",
        "executed_external_commands": "READ_ONLY_VERSION_AND_LOGIN_STATUS_ONLY",
        "repository_writes": "NONE",
        "user_state_persisted_in_repository": False,
    }


def opening_greeting() -> str:
    return """Welcome to AWS Codex Fastlane.

Fastlane turns your idea into a clear AWS application plan and a tested local
build. Describe the outcome in plain language; Codex asks focused questions,
uses current AWS guidance through AWS Core, recommends the technical approach,
and builds inside the boundaries you approve. You do not need to choose AWS
services.

You approve two checkpoints: Gate A confirms what should be built, and Gate B
confirms the design and build boundaries. Setup never authorizes AWS changes:
Fast Dev stays inside the exact approved non-production Gate B envelope after
read-only preflight; Explicit Gate requires its own exact action receipt.

Setup did not inspect AWS credentials or access an AWS account.

Reply once with:
- Project name: (one line; ordinary punctuation and international text are supported)
- Preferred AWS Region: (use an ID such as us-west-2, or "recommend one")
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
    configure_utf8_standard_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("welcome", help="Print the post-prerequisite welcome")
    prerequisites = subparsers.add_parser(
        "prerequisites", help="Run read-only prerequisite checks"
    )
    prerequisites.add_argument("--root", type=Path, default=Path.cwd())
    prerequisites.add_argument("--json", action="store_true")
    prerequisites.add_argument("--evidence-stdin", action="store_true")
    configure_hooks = subparsers.add_parser(
        "configure-hooks",
        help="Generate ignored local hooks with the current trusted Python",
    )
    configure_hooks.add_argument("--root", type=Path, default=Path.cwd())
    configure_hooks.add_argument("--replace", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "welcome":
        print(opening_greeting())
        return 0
    if args.command == "configure-hooks":
        try:
            configure_local_hooks(args.root, replace=args.replace)
        except SetupError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(
            "Configured local Fastlane hooks. Restart Codex and review the native hook trust prompt."
        )
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
