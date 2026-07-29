#!/usr/bin/env python3
"""Optional Fastlane lifecycle guardrails for native Codex hooks.

This module is intentionally standard-library-only. It reads one bounded JSON
event from stdin, emits only Codex hook JSON, and never writes project or client
state. Fastlane's doctor and project contracts remain authoritative.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


MAX_EVENT_BYTES = 1_048_576
MAX_CONTEXT_CHARS = 280
EVENT_NAMES = {
    "session-start": "SessionStart",
    "pre-tool-use": "PreToolUse",
    "permission-request": "PermissionRequest",
    "post-tool-use": "PostToolUse",
    "stop": "Stop",
}

AWS_DOCUMENTATION_MARKERS = (
    "retrieve_skill",
    "search_documentation",
    "read_documentation",
    "recommend",
    "list_regions",
    "get_regional_availability",
)
AWS_COMPATIBILITY_TOOL_MARKERS = (
    "call_aws",
    "use_aws",
    "execute_aws",
    "aws_api",
)
AWS_SCRIPT_TOOL_MARKERS = ("run_script",)
AWS_PRESIGNED_TOOL_MARKERS = ("get_presigned_url",)
AWS_TASK_TOOL_MARKERS = ("get_tasks",)
AWS_MUTATION_COMMANDS = (
    "cdk deploy",
    "cdk destroy",
    "sam deploy",
    "sam delete",
    "serverless deploy",
    "serverless remove",
    "terraform apply",
    "terraform destroy",
    "cloudformation deploy",
    "cloudformation execute-change-set",
    "cloudformation delete-stack",
)
AWS_READ_PREFIXES = (
    "batch_get",
    "describe",
    "detect",
    "get",
    "head",
    "list",
    "lookup",
    "preview",
    "search",
    "validate",
)
GITHUB_TOOL_MARKERS = (
    "add_issue_comment",
    "create_branch",
    "create_commit",
    "create_issue",
    "create_or_update_file",
    "create_pull_request",
    "create_ref",
    "create_release",
    "delete_ref",
    "merge_pull_request",
    "push_files",
    "request_review",
    "update_issue",
    "update_ref",
    "upload_release",
)
PATH_KEYS = {
    "cwd",
    "directory",
    "file",
    "file_path",
    "path",
    "root",
    "target",
    "target_file",
    "workdir",
}
PATCH_PATH = re.compile(r"^\*\*\* (?:Add|Delete|Update) File: (.+)$", re.MULTILINE)
GITHUB_BOUNDARIES = {"NONE", "READ_ONLY", "ISSUES", "BRANCH_AND_PR", "MERGE_WHEN_GREEN"}
AWS_BOUNDARIES = {"NONE", "DOCS_ONLY", "READ_ONLY", "MUTATE_LISTED_RESOURCES"}


class HookInputError(ValueError):
    """Raised when a native hook event is malformed or too large."""


def read_event(stream: Any) -> dict[str, Any]:
    """Read one bounded UTF-8 JSON object without retaining its raw bytes."""

    raw = stream.buffer.read(MAX_EVENT_BYTES + 1) if hasattr(stream, "buffer") else stream.read(MAX_EVENT_BYTES + 1)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > MAX_EVENT_BYTES:
        raise HookInputError("event exceeds the Fastlane hook size limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HookInputError("event is not a valid UTF-8 JSON object") from exc
    if not isinstance(payload, dict):
        raise HookInputError("event must be a JSON object")
    return payload


def resolve_repository_root(cwd: str | os.PathLike[str]) -> Path:
    """Resolve the Fastlane root without trusting the current subdirectory."""

    start = Path(cwd).resolve()
    if start.is_file():
        start = start.parent
    for candidate in (start, *start.parents):
        if (
            (candidate / "bootstrap.manifest.json").is_file()
            and (candidate / "scripts" / "bootstrap_doctor.py").is_file()
        ):
            return candidate
    raise HookInputError("Fastlane repository root could not be resolved")


def _bounded_text(value: object, limit: int = MAX_CONTEXT_CHARS) -> str:
    text = " ".join(str(value).split())
    return text[:limit]


def _doctor_command(root: Path) -> list[str]:
    return [
        sys.executable,
        str(root / "scripts" / "bootstrap_doctor.py"),
        "--root",
        str(root),
        "--json",
    ]


def run_doctor(root: Path) -> dict[str, Any]:
    """Run the existing doctor read-only and return only its JSON report."""

    completed = subprocess.run(
        _doctor_command(root),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise HookInputError("Fastlane Engine did not return JSON") from exc
    if not isinstance(report, dict):
        raise HookInputError("Fastlane Engine returned an invalid report")
    return report


def load_construction_envelope(root: Path) -> dict[str, str]:
    """Reuse the doctor's canonical PRD table parser instead of defining one."""

    scripts = str(root / "scripts")
    inserted = scripts not in sys.path
    if inserted:
        sys.path.insert(0, scripts)
    try:
        import bootstrap_doctor  # type: ignore[import-not-found]

        text = (root / "docs" / "project" / "PRD.md").read_text(encoding="utf-8")
        envelope = bootstrap_doctor.table_after_heading(
            text, "## 28. Construction envelope"
        )
    finally:
        if inserted:
            sys.path.remove(scripts)
    return envelope if isinstance(envelope, dict) else {}


def _event_tool(payload: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(name, str) or not name.strip():
        raise HookInputError("tool event is missing tool_name")
    if not isinstance(tool_input, Mapping):
        raise HookInputError("tool event is missing a JSON tool_input object")
    return name, tool_input


def _tool_command(tool_input: Mapping[str, Any]) -> str:
    value = tool_input.get("command")
    return value if isinstance(value, str) and value.strip() else ""


def _first_string(tool_input: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _script_source(tool_input: Mapping[str, Any]) -> str | None:
    sources = {
        value
        for key in ("script", "code", "python", "python_code", "source")
        if isinstance((value := tool_input.get(key)), str) and value
    }
    return next(iter(sources)) if len(sources) == 1 else None


def _parameter_resources(parameters: object) -> list[str]:
    if not isinstance(parameters, Mapping):
        return []
    keys = {
        "application",
        "applicationname",
        "cluster",
        "clustername",
        "functionname",
        "identifier",
        "name",
        "resource",
        "resourcearn",
        "resourcearns",
        "resourceid",
        "stack",
        "stackid",
        "stackname",
        "tablename",
        "target",
    }
    values: list[str] = []
    for key, value in parameters.items():
        if re.sub(r"[^a-z0-9]", "", str(key).casefold()) not in keys:
            continue
        candidates = value if isinstance(value, list) else [value]
        values.extend(
            str(item).strip()
            for item in candidates
            if isinstance(item, str) and item.strip()
        )
    return values


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _candidate_paths(tool_input: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key, value in tool_input.items():
        if key.casefold() in PATH_KEYS and isinstance(value, str):
            values.append(value)
    command = _tool_command(tool_input)
    values.extend(match.strip() for match in PATCH_PATH.findall(command))
    return values


def _relative_candidate(raw: str, root: Path, cwd: Path) -> str | None:
    candidate = Path(raw.strip().strip("'\""))
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return None
    if not _is_within(resolved, root):
        return None
    return resolved.relative_to(root).as_posix()


def _path_contains(boundary: str, requested: str) -> bool:
    boundary = boundary.replace("\\", "/").strip("/")
    requested = requested.replace("\\", "/").strip("/")
    base = boundary[:-3] if boundary.endswith("/**") else boundary
    return requested == base or requested.startswith(base + "/")


def _paths_overlap(first: str, second: str) -> bool:
    return _path_contains(first, second) or _path_contains(second, first)


def _is_file_write_tool(tool_name: str) -> bool:
    lowered = tool_name.casefold()
    return any(
        marker in lowered
        for marker in (
            "apply_patch",
            "create_file",
            "delete_file",
            "edit_file",
            "move_file",
            "rename_file",
            "replace_file",
            "update_file",
            "write_file",
        )
    ) or lowered in {"edit", "write"}


def _shell_write_candidates(command: str) -> tuple[bool, list[str]]:
    write_marker = re.search(
        r"(?:^|[;&|]\s*)(?:rm|mv|cp|touch|mkdir|rmdir|sed\s+-i|tee|"
        r"set-content|add-content|out-file|remove-item|move-item|copy-item|"
        r"new-item)(?:\s|$)|(?:^|[^>])>{1,2}(?!=)",
        command,
        re.IGNORECASE,
    )
    values = [match.strip() for match in PATCH_PATH.findall(command)]
    values.extend(
        match.strip("'\"")
        for match in re.findall(
            r"(?:>|>>|--file|-LiteralPath|-Path)\s*['\"]?([^'\"\s;&|]+)",
            command,
            re.IGNORECASE,
        )
    )
    return write_marker is not None or bool(values), values


def _write_denial(
    tool_name: str,
    tool_input: Mapping[str, Any],
    report: Mapping[str, Any],
    root: Path,
    cwd: Path,
) -> str | None:
    command = _tool_command(tool_input)
    shell_write, shell_paths = _shell_write_candidates(command)
    is_write = _is_file_write_tool(tool_name) or shell_write
    if not is_write:
        return None
    raw_paths = _candidate_paths(tool_input) + shell_paths
    if not raw_paths:
        return "Fastlane blocked an ambiguous file mutation because its exact target path is not observable."
    relative_paths: list[str] = []
    for raw in raw_paths:
        relative = _relative_candidate(raw, root, cwd)
        if relative is None:
            return "Fastlane blocked a write outside the current repository boundary."
        relative_paths.append(relative)
    authority = report.get("write_authority")
    if not isinstance(authority, Mapping) or authority.get("valid") is not True:
        return "Fastlane blocked a file mutation because current Gate B write authority is absent."
    roots = authority.get("approved_write_roots")
    exclusions = authority.get("exclusions")
    protected = authority.get("protected_paths")
    active_set = authority.get("active_task_write_set")
    if not all(isinstance(value, list) for value in (roots, exclusions, protected, active_set)):
        return "Fastlane blocked a file mutation because write authority is malformed."
    active_task = str(authority.get("active_task", "NONE"))
    for relative in relative_paths:
        if not any(_path_contains(str(boundary), relative) for boundary in roots):
            return f"Fastlane blocked {relative} because it is outside the current Gate B write roots."
        if any(_paths_overlap(str(boundary), relative) for boundary in exclusions):
            return f"Fastlane blocked {relative} because it overlaps an excluded write path."
        if any(_paths_overlap(str(boundary), relative) for boundary in protected):
            return f"Fastlane blocked {relative} because it overlaps a protected dirty path."
        if active_task != "NONE" and not any(
            _path_contains(str(boundary), relative) for boundary in active_set
        ):
            return f"Fastlane blocked {relative} because it is outside {active_task}'s active write set."
    return None


def _tool_capability_name(tool_name: str) -> str:
    lowered = tool_name.casefold()
    if "___" in lowered:
        return lowered.rsplit("___", 1)[-1]
    if lowered.startswith("mcp__"):
        return lowered.rsplit("__", 1)[-1]
    return lowered


def _is_aws_documentation_tool(tool_name: str) -> bool:
    lowered = tool_name.casefold()
    if _tool_capability_name(tool_name) in AWS_DOCUMENTATION_MARKERS:
        return True
    return lowered.startswith(
        "mcp__codex_apps__aws_documentation_aws___"
    )


def _normalized_operation(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _is_aws_account_tool(tool_name: str) -> bool:
    lowered = tool_name.casefold()
    capability = _tool_capability_name(tool_name)
    if capability in AWS_COMPATIBILITY_TOOL_MARKERS:
        return True
    if lowered.startswith("aws___"):
        return True
    if not lowered.startswith("mcp__"):
        return False
    return any(
        part == "aws"
        or part.startswith("aws-")
        or part.startswith("aws_")
        for part in lowered.split("__")[1:]
    )


def _string_values(value: object) -> list[str]:
    candidates = value if isinstance(value, list) else [value]
    return [
        item.strip()
        for item in candidates
        if isinstance(item, str) and item.strip()
    ]


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _task_poll_request(tool_input: Mapping[str, Any]) -> dict[str, Any]:
    task_ids: list[str] = []
    for key in ("task_id", "task_ids", "id", "ids"):
        task_ids.extend(_string_values(tool_input.get(key)))
    return {
        "lane": "TASK_POLL",
        "task_ids": sorted(set(task_ids)),
        "role_or_profile": _first_string(
            tool_input, ("aws_profile", "profile", "role")
        ),
    }


def _presigned_url_request(tool_input: Mapping[str, Any]) -> dict[str, Any]:
    raw_direction = _first_string(
        tool_input, ("direction", "operation", "action", "method")
    ) or ""
    direction = _normalized_operation(raw_direction)
    if direction in {"download", "get", "getobject", "read", "s3getobject"}:
        operation = "s3:GetObject"
        kind = "READ"
    elif direction in {"upload", "put", "putobject", "write", "s3putobject"}:
        operation = "s3:PutObject"
        kind = "MUTATE"
    else:
        operation = raw_direction
        kind = "AMBIGUOUS"

    bucket = _first_string(tool_input, ("bucket", "bucket_name"))
    key = _first_string(tool_input, ("key", "object", "object_key"))
    resources = (
        [f"arn:aws:s3:::{bucket}/{key.lstrip('/')}"]
        if bucket is not None and key is not None
        else []
    )
    expires_in = None
    for field in ("expires_in", "expires_in_seconds", "expiration", "ttl_seconds"):
        expires_in = _positive_int(tool_input.get(field))
        if expires_in is not None:
            break
    request: dict[str, Any] = {
        "lane": "STRUCTURED_API",
        "kind": kind,
        "operation": operation,
        "resources": resources,
        "presigned_url": True,
        "expires_in_seconds": expires_in,
    }
    for destination, keys in {
        "region": ("region",),
        "role_or_profile": ("aws_profile", "profile", "role"),
    }.items():
        observed = _first_string(tool_input, keys)
        if observed is not None:
            request[destination] = observed
    return request


def _aws_request_details(
    tool_name: str, tool_input: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Classify one attributable AWS request without treating docs as account use."""

    if _is_aws_documentation_tool(tool_name):
        return None
    capability = _tool_capability_name(tool_name)
    if capability in AWS_SCRIPT_TOOL_MARKERS:
        return {
            "lane": "REVIEWED_SCRIPT",
            "script": _script_source(tool_input),
            "artifact_path": _first_string(
                tool_input, ("script_path", "artifact_path", "file_path", "path")
            ),
            "role_or_profile": _first_string(
                tool_input, ("aws_profile", "profile", "role")
            ),
        }
    if capability in AWS_TASK_TOOL_MARKERS:
        return _task_poll_request(tool_input)
    if capability in AWS_PRESIGNED_TOOL_MARKERS:
        return _presigned_url_request(tool_input)

    command = _first_string(tool_input, ("command", "cli_command")) or ""
    lowered_command = command.casefold()
    is_external_tool = _is_aws_account_tool(tool_name)
    is_shell_aws = bool(
        re.search(r"(?:^|[;&|]\s*)(?:aws(?:\.exe)?|cdk|sam|terraform|serverless)\s+", lowered_command)
    ) or any(marker in lowered_command for marker in AWS_MUTATION_COMMANDS)
    if not is_external_tool and not is_shell_aws:
        return None
    service = _first_string(tool_input, ("service", "service_name")) or ""
    operation = ""
    for key in ("operation", "operation_name", "api", "action"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            operation = value.strip()
            break
    if not operation:
        matches = re.findall(
            r"(?:aws(?:\.exe)?\s+([a-z0-9_-]+)\s+([a-z0-9_-]+)|"
            r"(cdk|sam|terraform|serverless)\s+([a-z0-9_-]+))",
            lowered_command,
        )
        operations = [
            " ".join(item for item in match if item)
            for match in matches
        ]
        operations = [item for item in operations if item]
        if len(set(operations)) == 1:
            operation = operations[0]
        elif len(set(operations)) > 1:
            return {
                "lane": "STRUCTURED_API",
                "kind": "AMBIGUOUS",
                "operation": "MIXED_COMMAND_CHAIN",
                "resources": [],
            }
    if service and operation and ":" not in operation:
        operation = f"{service}:{operation}"
    normalized = _normalized_operation(operation.rsplit(":", 1)[-1])
    teardown = any(
        marker in normalized
        for marker in ("delete", "destroy", "remove", "terminate")
    )
    if normalized and normalized.startswith(
        tuple(_normalized_operation(item) for item in AWS_READ_PREFIXES)
    ):
        kind = "READ"
    elif teardown:
        kind = "TEARDOWN"
    elif normalized:
        kind = "MUTATE"
    else:
        kind = "AMBIGUOUS"
    resources: list[str] = []
    for key in (
        "resource",
        "resource_arn",
        "resource_id",
        "stack",
        "stack_name",
        "application",
        "identifier",
        "target",
    ):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            resources.append(value.strip())
    resources.extend(
        match.strip("'\"")
        for match in re.findall(
            r"--(?:stack-name|function-name|table-name|resource-arn|cluster|service|name)\s+['\"]?([^'\"\s;&|]+)",
            command,
            re.IGNORECASE,
        )
    )
    resources.extend(_parameter_resources(tool_input.get("parameters")))
    details: dict[str, Any] = {
        "lane": "STRUCTURED_API",
        "kind": kind,
        "operation": operation,
        "resources": sorted(set(resources)),
    }
    key_map = {
        "account": ("account", "account_id"),
        "region": ("region",),
        "environment": ("environment",),
        "role_or_profile": ("aws_profile", "profile", "role", "role_arn"),
        "artifact": ("artifact", "artifact_digest", "digest"),
        "plan": ("plan", "plan_binding", "change_set", "change_set_name"),
    }
    for destination, keys in key_map.items():
        for key in keys:
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                details[destination] = value.strip()
                break
    region_match = re.search(r"--region\s+['\"]?([^'\"\s;&|]+)", command, re.IGNORECASE)
    profile_match = re.search(r"--profile\s+['\"]?([^'\"\s;&|]+)", command, re.IGNORECASE)
    if region_match:
        details["region"] = region_match.group(1)
    if profile_match:
        details["role_or_profile"] = profile_match.group(1)
    return details

def _value_allowed(value: str, allowed: Sequence[object]) -> bool:
    normalized = value.strip().casefold()
    return bool(normalized) and any(
        normalized == str(item).strip().casefold() for item in allowed
    )


def _exact_value_allowed(value: str, allowed: Sequence[object]) -> bool:
    return bool(value.strip()) and any(
        value.strip() == str(item).strip() for item in allowed
    )


def _request_match(report: Mapping[str, Any]) -> Mapping[str, Any] | None:
    authority = report.get("external_authority")
    if not isinstance(authority, Mapping):
        return None
    match = authority.get("request_match")
    if not isinstance(match, Mapping) or match.get("schema_version") != 1:
        return None
    return match


def _operation_class(operation: str) -> str:
    normalized = _normalized_operation(operation.rsplit(":", 1)[-1])
    if any(
        marker in normalized
        for marker in ("delete", "destroy", "remove", "terminate")
    ):
        return "TEARDOWN"
    if normalized.startswith(
        tuple(_normalized_operation(item) for item in AWS_READ_PREFIXES)
    ):
        return "READ"
    return "MUTATE" if normalized else "AMBIGUOUS"


def _reviewed_script_denial(
    request: Mapping[str, Any], match: Mapping[str, Any], root: Path
) -> str | None:
    lanes = match.get("allowed_execution_lanes")
    contract = match.get("reviewed_script")
    if (
        not isinstance(lanes, list)
        or "REVIEWED_SCRIPT" not in lanes
        or not isinstance(contract, Mapping)
    ):
        return "Fastlane blocked an unbound AWS account script because no current reviewed execution contract exists."
    binding = contract.get("content_binding")
    if not isinstance(binding, Mapping):
        return "Fastlane blocked the AWS account script because its reviewed content binding is malformed."
    expected_digest = binding.get("sha256")
    if (
        not isinstance(expected_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest) is None
    ):
        return "Fastlane blocked the AWS account script because its reviewed digest is malformed."

    observed_digest: str | None = None
    if binding.get("kind") == "SCRIPT_SHA256":
        script = request.get("script")
        if isinstance(script, str):
            observed_digest = "sha256:" + hashlib.sha256(script.encode("utf-8")).hexdigest()
    elif binding.get("kind") == "IMMUTABLE_ARTIFACT_SHA256":
        raw_path = request.get("artifact_path")
        if isinstance(raw_path, str) and raw_path.strip():
            candidate = Path(raw_path.strip())
            candidate = candidate if candidate.is_absolute() else root / candidate
            try:
                if candidate.is_symlink():
                    return "Fastlane blocked a symlinked reviewed-script artifact."
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, ValueError):
                return "Fastlane blocked a reviewed-script artifact outside the repository boundary."
            if not resolved.is_file():
                return "Fastlane blocked a reviewed-script artifact that is not a regular file."
            observed_digest = "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest()
    if observed_digest != expected_digest:
        return "Fastlane blocked the AWS account script because its exact reviewed digest is not observable or does not match."

    expected_profile = match.get("role_or_profile")
    observed_profile = request.get("role_or_profile")
    if observed_profile is not None and str(observed_profile) != str(expected_profile):
        return "Fastlane blocked the AWS account script because its profile does not match current authority."
    operations = contract.get("expected_operations")
    if not isinstance(operations, list) or not operations:
        return "Fastlane blocked the AWS account script because expected operations are absent."
    classes = {_operation_class(str(operation)) for operation in operations}
    authority_kind = str(match.get("authority_kind", "NONE"))
    if "TEARDOWN" in classes and authority_kind != "AWS_TEARDOWN":
        return "Fastlane blocked teardown because a distinct current teardown receipt is absent."
    if authority_kind == "AWS_TEARDOWN" and "MUTATE" in classes:
        return "Fastlane blocked creation or update because teardown authority is separate."
    if authority_kind == "AWS_READ_ONLY" and classes - {"READ"}:
        return "Fastlane blocked mutation because current authority is read-only."
    if authority_kind not in {"AWS_READ_ONLY", "FAST_DEV_GATE_B", "AWS_DEPLOYMENT", "AWS_TEARDOWN"}:
        return "Fastlane blocked the AWS account script because current external authority is unsuitable."
    return None


def _task_poll_denial(
    request: Mapping[str, Any], match: Mapping[str, Any]
) -> str | None:
    task_ids = request.get("task_ids")
    if not isinstance(task_ids, list) or not task_ids:
        return "Fastlane blocked AWS task polling because an exact task identifier is not observable."
    allowed = match.get("task_ids")
    contract = match.get("reviewed_script")
    if not isinstance(allowed, list) and isinstance(contract, Mapping):
        allowed = contract.get("task_ids")
    if not isinstance(allowed, list) or not allowed:
        return "Fastlane blocked AWS task polling because the task is not bound by the current Fastlane Engine authority."
    if any(not _exact_value_allowed(str(task_id), allowed) for task_id in task_ids):
        return "Fastlane blocked AWS task polling because a task identifier is outside current authority."
    expected_profile = match.get("role_or_profile")
    observed_profile = request.get("role_or_profile")
    if observed_profile is not None and str(observed_profile) != str(expected_profile):
        return "Fastlane blocked AWS task polling because its profile does not match current authority."
    return None


def _parse_utc_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _presigned_url_expiration_denial(
    request: Mapping[str, Any], match: Mapping[str, Any]
) -> str | None:
    expires_in = request.get("expires_in_seconds")
    if not isinstance(expires_in, int) or isinstance(expires_in, bool) or expires_in <= 0:
        return "Fastlane blocked the presigned URL because its positive expiration is not observable."
    authority_expiry = _parse_utc_datetime(match.get("expires_at"))
    now = datetime.now(timezone.utc)
    if authority_expiry is None or authority_expiry <= now:
        return "Fastlane blocked the presigned URL because current authority is expired or malformed."
    if expires_in > int((authority_expiry - now).total_seconds()):
        return "Fastlane blocked the presigned URL because its expiration exceeds current authority."
    return None

def _aws_authority_denial(
    request: Mapping[str, Any], report: Mapping[str, Any], root: Path
) -> str | None:
    authority = _request_match(report)
    if authority is None or authority.get("validity") != "CURRENT":
        return "Fastlane blocked AWS account access because normalized current external authority is absent."
    if request.get("lane") == "TASK_POLL":
        return _task_poll_denial(request, authority)
    if request.get("lane") == "REVIEWED_SCRIPT":
        return _reviewed_script_denial(request, authority, root)
    lanes = authority.get("allowed_execution_lanes")
    if not isinstance(lanes, list) or "STRUCTURED_API" not in lanes:
        return "Fastlane blocked the structured AWS request because its execution lane is not current."
    kind = str(request.get("kind", "AMBIGUOUS"))
    if kind == "AMBIGUOUS":
        return "Fastlane blocked an ambiguous mutation-capable AWS request because its operation is not exact."
    authority_kind = str(authority.get("authority_kind", "NONE"))
    if kind == "READ":
        if authority_kind not in {"AWS_READ_ONLY", "FAST_DEV_GATE_B", "AWS_DEPLOYMENT", "AWS_TEARDOWN"}:
            return "Fastlane blocked AWS read access because the current read-authority contract does not cover it."
    elif kind == "TEARDOWN":
        if authority_kind != "AWS_TEARDOWN":
            return "Fastlane blocked teardown because a distinct current teardown receipt is absent."
    elif authority_kind not in {"FAST_DEV_GATE_B", "AWS_DEPLOYMENT"}:
        return "Fastlane blocked AWS mutation because exact current mutation authority is absent."
    operations = authority.get("operations")
    resources = authority.get("resources")
    if not isinstance(operations, list) or not _value_allowed(str(request.get("operation", "")), operations):
        return "Fastlane blocked the AWS request because its exact operation is outside the authorized operation list."
    requested_resources = request.get("resources")
    if (kind in {"MUTATE", "TEARDOWN"} or request.get("presigned_url") is True) and (
        not isinstance(requested_resources, list) or not requested_resources
    ):
        return "Fastlane blocked the AWS request because its exact resource target is not observable."
    if isinstance(requested_resources, list) and isinstance(resources, list):
        for requested in requested_resources:
            if not _exact_value_allowed(str(requested), resources):
                return "Fastlane blocked the AWS request because a resource target is outside the authorized boundary."
    for key in ("account", "region", "environment", "role_or_profile"):
        observed = request.get(key)
        expected = authority.get(key)
        expected_text = str(expected or "").strip()
        if observed is not None and (not expected_text or str(observed).casefold() != expected_text.casefold()):
            return f"Fastlane blocked the AWS request because {key.replace('_', ' ')} does not match current authority."
    for request_key, authority_key in (("artifact", "artifact_digest"), ("plan", "plan_binding")):
        observed = request.get(request_key)
        expected = authority.get(authority_key)
        if observed is not None and (not isinstance(expected, str) or str(observed) != expected):
            return f"Fastlane blocked the AWS request because its {request_key} binding does not match current authority."
    if request.get("presigned_url") is True:
        return _presigned_url_expiration_denial(request, authority)
    return None


def _github_request_kind(tool_name: str, tool_input: Mapping[str, Any]) -> str | None:
    lowered_name = tool_name.casefold()
    command = _tool_command(tool_input).casefold()
    marker = next((item for item in GITHUB_TOOL_MARKERS if item in lowered_name), None)
    if marker:
        if "merge" in marker or "release" in marker or "delete_ref" in marker:
            return "MERGE"
        if "issue" in marker or "comment" in marker:
            return "ISSUE"
        return "BRANCH_PR"
    if re.search(r"(?:^|[;&|]\s*)git\s+push(?:\s|$)", command):
        return "BRANCH_PR"
    if re.search(r"(?:^|[;&|]\s*)gh\s+(?:pr\s+merge|release\s+)", command):
        return "MERGE"
    if re.search(r"(?:^|[;&|]\s*)gh\s+issue\s+", command):
        return "ISSUE"
    if re.search(r"(?:^|[;&|]\s*)gh\s+pr\s+create(?:\s|$)", command):
        return "BRANCH_PR"
    if re.search(r"(?:^|[;&|]\s*)gh\s+api(?:\s|$)", command):
        mutating_method = re.search(
            r"(?:--method|-X)(?:=|\s+)(?:POST|PUT|PATCH|DELETE)(?:\s|$)",
            command,
            re.IGNORECASE,
        )
        form_field = re.search(r"(?:^|\s)(?:-f|-F|--field|--raw-field)(?:=|\s)", command)
        if mutating_method or form_field:
            return "BRANCH_PR"
    return None


def _authority_denial(
    tool_name: str,
    tool_input: Mapping[str, Any],
    report: Mapping[str, Any],
    envelope: Mapping[str, str],
    root: Path,
    cwd: Path,
) -> str | None:
    write_reason = _write_denial(tool_name, tool_input, report, root, cwd)
    if write_reason is not None:
        return write_reason

    aws_request = _aws_request_details(tool_name, tool_input)
    if aws_request is not None:
        aws_reason = _aws_authority_denial(aws_request, report, root)
        if aws_reason is not None:
            return aws_reason

    authorizations = report.get("authorizations")
    if not isinstance(authorizations, Mapping):
        authorizations = {}
    construction_authorization = str(authorizations.get("construction", "NONE"))
    github_boundary = str(envelope.get("GitHub boundary", "NONE"))
    if github_boundary not in GITHUB_BOUNDARIES:
        github_boundary = "NONE"

    github_kind = _github_request_kind(tool_name, tool_input)
    if github_kind is not None and construction_authorization == "NONE":
        return "Fastlane blocked GitHub publication because current construction authority is absent."
    allowed_github = {
        "ISSUE": {"ISSUES", "BRANCH_AND_PR", "MERGE_WHEN_GREEN"},
        "BRANCH_PR": {"BRANCH_AND_PR", "MERGE_WHEN_GREEN"},
        "MERGE": {"MERGE_WHEN_GREEN"},
    }
    if github_kind is not None and github_boundary not in allowed_github[github_kind]:
        return "Fastlane blocked GitHub publication because it exceeds the current GitHub boundary."
    return None


def _broad_escalation(payload: Mapping[str, Any], tool_input: Mapping[str, Any]) -> bool:
    if str(payload.get("permission_mode", "")).casefold() == "bypasspermissions":
        return True
    description = tool_input.get("description")
    if not isinstance(description, str):
        return False
    lowered = description.casefold()
    return any(
        marker in lowered
        for marker in (
            "bypass approvals",
            "disable sandbox",
            "full disk access",
            "unrestricted access",
        )
    )


def pre_tool_denial(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _bounded_text(reason),
        }
    }


def permission_denial(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": "deny",
                "message": _bounded_text(reason),
            },
        }
    }


def _is_unconfigured_template(report: Mapping[str, Any]) -> bool:
    diagnostics = report.get("diagnostics")
    if not isinstance(diagnostics, list):
        return False
    codes = {
        item.get("code")
        for item in diagnostics
        if isinstance(item, Mapping) and isinstance(item.get("code"), str)
    }
    return {"PLACEHOLDER_UNRESOLVED", "STATE_SETUP"}.issubset(codes)


def _session_context(report: Mapping[str, Any]) -> str:
    if _is_unconfigured_template(report):
        return _bounded_text(
            "Fastlane optional guardrail context: template is not initialized; complete "
            "the prerequisite checklist, then rerun init template. Hooks are defense in "
            "depth and grant no authority."
        )
    gates = report.get("gates") if isinstance(report.get("gates"), Mapping) else {}
    interaction = (
        report.get("interaction")
        if isinstance(report.get("interaction"), Mapping)
        else {}
    )
    authorizations = (
        report.get("authorizations")
        if isinstance(report.get("authorizations"), Mapping)
        else {}
    )
    return _bounded_text(
        "Fastlane optional guardrail context: "
        f"stage={interaction.get('owner_stage', 'UNKNOWN')}; "
        f"Gate A={gates.get('gate_a', 'UNKNOWN')}; "
        f"Gate B={gates.get('gate_b', 'UNKNOWN')}; "
        f"AWS authority={authorizations.get('aws', 'NONE')}; "
        f"owner action={interaction.get('owner_action_kind', 'UNKNOWN')}. "
        "Hooks are defense in depth and grant no authority."
    )


def _run_validation(root: Path, command: Sequence[str]) -> bool:
    completed = subprocess.run(
        list(command),
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )
    return completed.returncode == 0


def _post_validation(
    tool_name: str,
    tool_input: Mapping[str, Any],
    root: Path,
    runner: Callable[[Path, Sequence[str]], bool],
) -> str | None:
    command = _tool_command(tool_input)
    lowered_name = tool_name.casefold()
    if lowered_name in {"apply_patch", "edit", "write"}:
        if not runner(root, ["git", "diff", "--check"]):
            return "Fastlane validation found a diff-format problem. Run git diff --check."
    if "update_manifest.py" in command and "--write" in command:
        check = [
            sys.executable,
            str(root / "scripts" / "update_manifest.py"),
            "--check",
        ]
        if not runner(root, check):
            return "Fastlane manifest validation did not pass. Run the manifest check before continuing."
    return None


def handle_event(
    event_key: str,
    payload: Mapping[str, Any],
    *,
    root: Path | None = None,
    doctor_report: Mapping[str, Any] | None = None,
    envelope: Mapping[str, str] | None = None,
    validation_runner: Callable[[Path, Sequence[str]], bool] = _run_validation,
) -> dict[str, Any] | None:
    expected = EVENT_NAMES.get(event_key)
    if expected is None:
        raise HookInputError("unknown Fastlane hook event")
    if payload.get("hook_event_name") != expected:
        raise HookInputError("hook_event_name does not match the configured handler")
    cwd_value = payload.get("cwd")
    if not isinstance(cwd_value, str) or not cwd_value:
        raise HookInputError("hook event is missing cwd")
    cwd = Path(cwd_value).resolve()
    root = root.resolve() if root is not None else resolve_repository_root(cwd)

    if event_key == "session-start":
        report = doctor_report or run_doctor(root)
        return {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": _session_context(report),
            }
        }

    if event_key in {"pre-tool-use", "permission-request"}:
        tool_name, tool_input = _event_tool(payload)
        report = doctor_report or run_doctor(root)
        authority_envelope = envelope or load_construction_envelope(root)
        reason = _authority_denial(
            tool_name, tool_input, report, authority_envelope, root, cwd
        )
        if event_key == "permission-request" and reason is None and _broad_escalation(payload, tool_input):
            reason = "Fastlane blocked a broad escalation that exceeds the current project boundary."
        if reason is None:
            return None
        return pre_tool_denial(reason) if event_key == "pre-tool-use" else permission_denial(reason)

    if event_key == "post-tool-use":
        tool_name, tool_input = _event_tool(payload)
        message = _post_validation(tool_name, tool_input, root, validation_runner)
        return {"systemMessage": message} if message else None

    if bool(payload.get("stop_hook_active")):
        return None
    report = doctor_report or run_doctor(root)
    interaction = report.get("interaction")
    if not isinstance(interaction, Mapping):
        return None
    should_continue = (
        interaction.get("automatic_continuation_allowed") is True
        and interaction.get("owner_action_required") is False
        and interaction.get("formal_receipt_required") is False
    )
    if not should_continue:
        return None
    return {
        "decision": "block",
        "reason": (
            "The Fastlane Engine permits automatic continuation. Continue the current "
            "lifecycle phase, run its required validation, checkpoint, and rerun the Engine."
        ),
    }


def malformed_response(event_key: str) -> dict[str, Any]:
    reason = "Fastlane hook received malformed event data and could not verify the requested boundary."
    if event_key == "pre-tool-use":
        return pre_tool_denial(reason)
    if event_key == "permission-request":
        return permission_denial(reason)
    return {
        "continue": False,
        "stopReason": reason,
        "systemMessage": reason,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    event_key = arguments[0] if len(arguments) == 1 else ""
    try:
        payload = read_event(sys.stdin)
        response = handle_event(event_key, payload)
    except (HookInputError, OSError, subprocess.SubprocessError, ValueError):
        response = malformed_response(event_key)
    if response is not None:
        json.dump(response, sys.stdout, separators=(",", ":"), sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
