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
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
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
SHELL_COMMAND_BOUNDARY = r"(?:^|[;&|]\s*|\r?\n\s*)"
SHELL_WRAPPER_PREFIX = (
    r"(?:(?:(?:command|builtin|exec)\s+)|"
    r"(?:env(?:\s+(?:--?[A-Za-z0-9_-]+|"
    r"[A-Za-z_][A-Za-z0-9_]*=[^\s;&|]+))*\s+))*"
)
GITHUB_CONNECTOR_TOOL_PREFIXES = (
    "mcp__codex_apps__github_",
    "mcp__github__",
)
GITHUB_READ_ONLY_CAPABILITIES = frozenset(
    {
        "compare_commits",
        "download_user_content",
        "download_workflow_artifact",
        "fetch",
        "fetch_blob",
        "fetch_commit",
        "fetch_commit_workflow_runs",
        "fetch_file",
        "fetch_issue",
        "fetch_issue_comments",
        "fetch_pr",
        "fetch_pr_comments",
        "fetch_pr_file_patch",
        "fetch_pr_patch",
        "fetch_workflow_job_logs",
        "fetch_workflow_job_steps",
        "fetch_workflow_run_artifacts",
        "fetch_workflow_run_jobs",
        "get_commit_combined_status",
        "get_issue_comment_reactions",
        "get_pr_diff",
        "get_pr_info",
        "get_pr_reactions",
        "get_pr_review_comment_reactions",
        "get_profile",
        "get_repo",
        "get_repo_collaborator_permission",
        "get_user_login",
        "get_users_recent_prs_in_repo",
        "list_installations",
        "list_installed_accounts",
        "list_pr_changed_filenames",
        "list_pull_request_review_threads",
        "list_pull_request_reviews",
        "list_recent_issues",
        "list_repositories",
        "list_repositories_by_affiliation",
        "list_repositories_by_installation",
        "list_user_org_memberships",
        "list_user_orgs",
        "search",
        "search_branches",
        "search_commits",
        "search_installed_repositories_v2",
        "search_issues",
        "search_prs",
        "search_repositories",
    }
)
GITHUB_ISSUE_MUTATION_CAPABILITIES = frozenset(
    {
        "add_comment_to_issue",
        "add_issue_assignees",
        "add_issue_labels",
        "add_reaction_to_issue_comment",
        "add_reaction_to_pr",
        "add_reaction_to_pr_review_comment",
        "add_review_to_pr",
        "create_issue",
        "dismiss_pull_request_review",
        "label_pr",
        "lock_issue_conversation",
        "remove_issue_assignees",
        "remove_issue_label",
        "remove_pull_request_reviewers",
        "remove_reaction_from_issue_comment",
        "remove_reaction_from_pr",
        "remove_reaction_from_pr_review_comment",
        "reply_to_review_comment",
        "request_pull_request_reviewers",
        "resolve_review_thread",
        "unlock_issue_conversation",
        "unresolve_review_thread",
        "update_issue",
        "update_issue_comment",
        "update_review_comment",
    }
)
GITHUB_BRANCH_PR_MUTATION_CAPABILITIES = frozenset(
    {
        "convert_pull_request_to_draft",
        "create_blob",
        "create_branch",
        "create_commit",
        "create_file",
        "create_or_update_file",
        "create_pull_request",
        "create_ref",
        "create_tree",
        "delete_file",
        "mark_pull_request_ready_for_review",
        "push_files",
        "update_file",
        "update_pull_request",
        "update_ref",
    }
)
GITHUB_MERGE_MUTATION_CAPABILITIES = frozenset(
    {
        "create_release",
        "delete_ref",
        "enable_auto_merge",
        "merge_pull_request",
        "rerun_failed_workflow_run_jobs",
        "rerun_workflow_job",
        "update_release",
        "upload_release",
    }
)
GITHUB_DIRECT_BRANCH_CAPABILITIES = frozenset(
    {
        "create_branch",
        "create_file",
        "create_or_update_file",
        "create_ref",
        "delete_ref",
        "delete_file",
        "push_files",
        "update_file",
        "update_ref",
    }
)
GITHUB_BRANCH_REQUIRED_CAPABILITIES = GITHUB_DIRECT_BRANCH_CAPABILITIES | {
    "create_pull_request",
    "create_release",
}
GITHUB_BRANCH_IF_PRESENT_CAPABILITIES = frozenset({"update_pull_request"})
GITHUB_UNOBSERVABLE_PROTECTED_CAPABILITIES = frozenset(
    {
        "enable_auto_merge",
        "merge_pull_request",
        "rerun_failed_workflow_run_jobs",
        "rerun_workflow_job",
        "update_release",
        "upload_release",
    }
)
GITHUB_REPOSITORY_ONLY_MUTATION_CAPABILITIES = GITHUB_ISSUE_MUTATION_CAPABILITIES | {
    "convert_pull_request_to_draft",
    "create_blob",
    "create_commit",
    "create_tree",
    "mark_pull_request_ready_for_review",
}
GITHUB_REPOSITORY_NAME = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]+"
)
GITHUB_REPOSITORY_URL = re.compile(
    r"https://github\.com/(?P<repository>"
    r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+?)"
    r"(?:\.git)?/?",
    re.IGNORECASE,
)
GITHUB_CONSTRAINTS = re.compile(
    r"REPO: (?P<repository>[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+); "
    r"BRANCH: (?P<branch>[^;\r\n]+); MERGE: (?P<merge>ALLOWED|PROHIBITED)"
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
BOOTSTRAP_MARKER = re.compile(
    r"^<!-- bootstrap:(?P<name>[a-z0-9][a-z0-9-]*):(?P<boundary>start|end) -->$"
)
LIFECYCLE_INTENT_SECTION = "## Current release decision"
LIFECYCLE_INTENT_PREFIXES = (
    "- AWS lifecycle intent: ",
    "- AWS lifecycle intent source: ",
    "- AWS lifecycle intent recorded at: ",
)
LIFECYCLE_INTENT_VALUES = ["NONE", "RESIDUAL_REVIEW", "TEARDOWN"]
RESIDUAL_CHOICE_VALUES = ["RETAIN", "RESIDUAL_REVIEW", "TEARDOWN"]
LIFECYCLE_INTENT_PARSE_VALUES = frozenset(
    LIFECYCLE_INTENT_VALUES + RESIDUAL_CHOICE_VALUES
)
LIFECYCLE_INTENT_SOURCE = re.compile(r"owner-message MSG-AWS-LIFECYCLE-\d{4,}")
GITHUB_BOUNDARIES = {"NONE", "READ_ONLY", "ISSUES", "BRANCH_AND_PR", "MERGE_WHEN_GREEN"}
AWS_BOUNDARIES = {"NONE", "DOCS_ONLY", "READ_ONLY", "MUTATE_LISTED_RESOURCES"}


class HookInputError(ValueError):
    """Raised when a native hook event is malformed or too large."""


def read_event(stream: Any) -> dict[str, Any]:
    """Read one bounded UTF-8 JSON object without retaining its raw bytes."""

    raw = (
        stream.buffer.read(MAX_EVENT_BYTES + 1)
        if hasattr(stream, "buffer")
        else stream.read(MAX_EVENT_BYTES + 1)
    )
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
        if (candidate / "bootstrap.manifest.json").is_file() and (
            candidate / "scripts" / "bootstrap_doctor.py"
        ).is_file():
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


def load_hook_constraints(report: Mapping[str, Any]) -> dict[str, str]:
    """Use only the doctor's validated, content-bound hook projection."""

    defaults = {
        "GitHub boundary": "NONE",
        "GitHub repository, branch, and merge constraints": "NONE",
    }
    projected = report.get("hook_constraints")
    if not isinstance(projected, Mapping):
        return defaults
    values = {key: projected.get(key) for key in defaults}
    if not all(isinstance(value, str) for value in values.values()):
        return defaults
    return {key: str(value) for key, value in values.items()}


def _event_tool(payload: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(name, str) or not name.strip():
        raise HookInputError("tool event is missing tool_name")
    if not isinstance(tool_input, Mapping):
        raise HookInputError("tool event is missing a JSON tool_input object")
    return name, tool_input


TRANSITION_DIRECTORY = "fastlane-hook-transitions-v1"
TRANSITION_MAX_AGE_SECONDS = 900
TRANSITION_STAGES = {
    "START_PATCH_PENDING",
    "START_BOUND",
    "AWS_CALL_PENDING",
    "AWS_RESULT_BOUND",
    "TERMINAL_PATCH_PENDING",
}
TRANSITION_ACTIONS = {"AWS_DEPLOYMENT", "AWS_TEARDOWN"}
TRANSITION_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
DEPLOYMENT_JOURNAL = "## AWS deployment action and reconciliation evidence"
TEARDOWN_JOURNAL = "## Teardown reconciliation evidence"
DEPLOYMENT_PRECALL_RESULT = "NOT_OBSERVED — pre-call journal only"
TEARDOWN_PRECALL_RESULT = "NOT_OBSERVED — pre-call journal only"
TEARDOWN_RESUME_UNKNOWN_RESULT = (
    "UNKNOWN — result unavailable after interrupted attempt"
)
TEARDOWN_RESUME_UNKNOWN_RESIDUALS = "UNKNOWN — no post-call inventory observed"


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _value_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _transition_path(root: Path) -> Path:
    repository_hash = hashlib.sha256(
        str(root.resolve()).casefold().encode("utf-8")
    ).hexdigest()
    return (
        Path(tempfile.gettempdir())
        / TRANSITION_DIRECTORY
        / repository_hash
        / "transition.json"
    )


def _clear_transition(root: Path) -> None:
    path = _transition_path(root)
    for candidate in (path, path.with_suffix(".tmp")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _store_transition(root: Path, state: Mapping[str, str]) -> None:
    path = _transition_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(state), separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    if len(encoded) > 8_192:
        raise HookInputError("Fastlane transition state exceeds its bounded schema")
    temporary = path.with_suffix(".tmp")
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    descriptor = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    try:
        os.write(descriptor, encoded)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _load_transition(root: Path) -> dict[str, str] | None:
    path = _transition_path(root)
    try:
        stat = path.stat()
        if (
            datetime.now(timezone.utc).timestamp() - stat.st_mtime
            > TRANSITION_MAX_AGE_SECONDS
        ):
            _clear_transition(root)
            return None
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    if len(raw) > 8_192:
        _clear_transition(root)
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _clear_transition(root)
        return None
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        _clear_transition(root)
        return None
    required = {
        "schema_version",
        "stage",
        "action_kind",
        "session_sha256",
        "turn_sha256",
        "attempt_sha256",
        "authority_sha256",
        "start_patch_sha256",
        "start_tool_name_sha256",
        "start_tool_sha256",
        "request_sha256",
        "aws_tool_name_sha256",
        "aws_tool_sha256",
        "response_sha256",
        "terminal_patch_sha256",
        "terminal_tool_name_sha256",
        "terminal_tool_sha256",
    }
    if (
        set(value) != required
        or value["schema_version"] != "2"
        or value["stage"] not in TRANSITION_STAGES
        or value["action_kind"] not in TRANSITION_ACTIONS
        or any(
            value[key] != "NONE" and TRANSITION_DIGEST.fullmatch(value[key]) is None
            for key in required - {"schema_version", "stage", "action_kind"}
        )
    ):
        _clear_transition(root)
        return None
    return value


def _turn_identity(payload: Mapping[str, Any]) -> dict[str, str] | None:
    result: dict[str, str] = {}
    for destination, key in (
        ("session_sha256", "session_id"),
        ("turn_sha256", "turn_id"),
    ):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        result[destination] = _value_digest(value.strip())
    return result


def _tool_identity(payload: Mapping[str, Any]) -> dict[str, str] | None:
    result = _turn_identity(payload)
    tool_use_id = payload.get("tool_use_id")
    if result is None or not isinstance(tool_use_id, str) or not tool_use_id.strip():
        return None
    result["tool_sha256"] = _value_digest(tool_use_id.strip())
    return result


def _tool_name_digest(tool_name: str) -> str:
    return _value_digest(tool_name.strip().casefold())


def _event_matches_transition(
    state: Mapping[str, str], identity: Mapping[str, str]
) -> bool:
    return bool(
        state.get("session_sha256") == identity.get("session_sha256")
        and state.get("turn_sha256") == identity.get("turn_sha256")
    )


def _empty_transition_state(
    *,
    stage: str,
    action_kind: str,
    identity: Mapping[str, str],
    tool_name: str,
    attempt_sha256: str,
    authority_sha256: str,
    start_patch_sha256: str,
) -> dict[str, str]:
    return {
        "schema_version": "2",
        "stage": stage,
        "action_kind": action_kind,
        "session_sha256": identity["session_sha256"],
        "turn_sha256": identity["turn_sha256"],
        "attempt_sha256": attempt_sha256,
        "authority_sha256": authority_sha256,
        "start_patch_sha256": start_patch_sha256,
        "start_tool_name_sha256": _tool_name_digest(tool_name),
        "start_tool_sha256": identity["tool_sha256"],
        "request_sha256": "NONE",
        "aws_tool_name_sha256": "NONE",
        "aws_tool_sha256": "NONE",
        "response_sha256": "NONE",
        "terminal_patch_sha256": "NONE",
        "terminal_tool_name_sha256": "NONE",
        "terminal_tool_sha256": "NONE",
    }


def _row_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value]


def _csv_values(value: str) -> list[str]:
    cleaned = value.strip().strip("`")
    if cleaned == "NONE":
        return []
    values = [item.strip() for item in cleaned.split(",") if item.strip()]
    return values if len(values) == len(set(values)) else []


def _report_basis(report: Mapping[str, Any]) -> str | None:
    basis = report.get("basis")
    authorizations = report.get("authorizations")
    if not isinstance(basis, Mapping) or not isinstance(authorizations, Mapping):
        return None
    values = (
        basis.get("requirements_revision"),
        basis.get("design_revision"),
        authorizations.get("construction"),
    )
    if not all(isinstance(item, str) and item.strip() for item in values):
        return None
    return " / ".join(str(item).strip() for item in values)


def _expected_scope(match: Mapping[str, Any]) -> str:
    return (
        f"ACCOUNT: {match.get('account')}; REGION: {match.get('region')}; "
        f"ENVIRONMENT: {match.get('environment')}"
    )


def _transition_patch_delta(
    tool_name: str,
    tool_input: Mapping[str, Any],
    root: Path,
) -> dict[str, Any] | None:
    if "apply_patch" not in tool_name.casefold():
        return None
    command = _tool_command(tool_input)
    raw_paths = _candidate_paths(tool_input)
    relative = {
        candidate
        for raw in raw_paths
        if (candidate := _relative_candidate(raw, root, root)) is not None
    }
    if relative != {"docs/project/VERIFY.md"}:
        return None
    try:
        current = (root / "docs/project/VERIFY.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    delta = _closure_patch_delta(command, current)
    if delta is None:
        return None
    delta["command_sha256"] = _value_digest(command)
    delta["current_text"] = current
    return delta


def _started_patch_candidate(
    tool_name: str,
    tool_input: Mapping[str, Any],
    report: Mapping[str, Any],
    root: Path,
) -> tuple[bool, dict[str, str] | None, str | None]:
    delta = _transition_patch_delta(tool_name, tool_input, root)
    if delta is None:
        return False, None, None
    journals = set(delta["changed_sections"]).intersection(
        {DEPLOYMENT_JOURNAL, TEARDOWN_JOURNAL}
    )
    if not journals:
        return False, None, None
    if len(journals) != 1:
        return (
            True,
            None,
            "Fastlane blocked a transition patch spanning multiple AWS journals.",
        )
    journal = next(iter(journals))
    changes = delta["changes"].get(journal, {})
    additions = changes.get("additions", [])
    deletions = changes.get("deletions", [])
    expected_cells = 28 if journal == DEPLOYMENT_JOURNAL else 30
    cells = (
        _markdown_cells(additions[0], expected_cells) if len(additions) == 1 else None
    )
    if cells is None or cells[-1] != "STARTED":
        return False, None, None
    malformed = "Fastlane blocked an AWS STARTED patch that is not exactly bound to current authority."
    if delta["changed_sections"] != {journal} or deletions:
        return True, None, malformed
    match = _request_match(report)
    external = report.get("external_authority")
    basis = _report_basis(report)
    if (
        match is None
        or match.get("validity") != "CURRENT"
        or not isinstance(external, Mapping)
        or basis is None
        or cells[3] != basis
        or re.fullmatch(r"EV-\d{4,}", cells[0]) is None
    ):
        return True, None, malformed
    attempt_pattern = (
        r"AWS-DEPLOY-\d{4,}"
        if journal == DEPLOYMENT_JOURNAL
        else r"AWS-TEARDOWN-\d{4,}"
    )
    if re.fullmatch(attempt_pattern, cells[1]) is None:
        return True, None, malformed
    resources = _row_values(match.get("resources"))
    operations = _row_values(match.get("operations"))
    common_valid = bool(
        cells[-3] in {"PASS", "VERIFIED"}
        and cells[-2] == "NONE"
        and cells[-4]
        and cells[-4] != "NONE"
        and _parse_utc_datetime(cells[-5]) is not None
    )
    if journal == DEPLOYMENT_JOURNAL:
        action_kind = str(match.get("authority_kind"))
        valid = bool(
            action_kind == "AWS_DEPLOYMENT"
            and cells[2] == "AWS-20"
            and cells[4] == str(match.get("authorization_id") or "NONE")
            and cells[5] == str(match.get("receipt_digest") or "NONE")
            and cells[6] == str(match.get("expires_at") or "NONE")
            and cells[8] == "NONE"
            and cells[9] == str(match.get("role_or_profile") or "NONE")
            and all(cells[index] == "NONE" for index in (10, 11, 12, 13, 18, 21, 22))
            and cells[14] == str(match.get("artifact_digest") or "NONE")
            and cells[15] == str(match.get("plan_binding") or "NONE")
            and _csv_values(cells[16]) == resources
            and _csv_values(cells[17]) == operations
            and cells[19] == _expected_scope(match)
            and cells[20] == DEPLOYMENT_PRECALL_RESULT
            and common_valid
        )
    else:
        action_kind = "AWS_TEARDOWN"
        ready_binding = match.get("teardown_ready_binding")
        if not isinstance(ready_binding, Mapping):
            return True, None, malformed
        valid = bool(
            match.get("authority_kind") == action_kind
            and cells[2] == "AWS-50"
            and cells[4] == str(ready_binding.get("read_authorization") or "NONE")
            and cells[5] == str(ready_binding.get("read_role_or_profile") or "NONE")
            and cells[6] == str(ready_binding.get("read_receipt_digest") or "NONE")
            and cells[7] == str(ready_binding.get("read_valid_until") or "NONE")
            and cells[8] == str(ready_binding.get("read_authority_source") or "NONE")
            and cells[9] == str(match.get("authorization_id") or "NONE")
            and cells[10] == str(match.get("receipt_digest") or "NONE")
            and cells[11] == str(match.get("role_or_profile") or "NONE")
            and cells[12]
            == str(ready_binding.get("expected_manifest_or_stack") or "NONE")
            and _csv_values(cells[13]) == resources
            and _csv_values(cells[14]) == operations
            and _csv_values(cells[15])
            == _row_values(ready_binding.get("resources_retained"))
            and _csv_values(cells[16])
            == _row_values(ready_binding.get("shared_dependencies"))
            and cells[17] == str(ready_binding.get("cost_effect") or "NONE")
            and cells[18]
            == str(ready_binding.get("post_teardown_verification") or "NONE")
            and cells[19] == TEARDOWN_PRECALL_RESULT
            and all(cells[index] == "NONE" for index in (20, 21, 22))
            and cells[23] == TEARDOWN_PRECALL_RESULT
            and cells[24] == _expected_scope(match)
            and common_valid
        )
    if not valid:
        return True, None, malformed
    return (
        True,
        {
            "action_kind": action_kind,
            "attempt_sha256": _value_digest(cells[1]),
            "authority_sha256": _canonical_digest(match),
            "patch_sha256": str(delta["command_sha256"]),
        },
        None,
    )


def _transition_projection(
    report: Mapping[str, Any], state: Mapping[str, str]
) -> Mapping[str, Any] | None:
    transition = report.get("aws_action_transition")
    if (
        not isinstance(transition, Mapping)
        or transition.get("schema_version") != 1
        or transition.get("status") != "BOUND"
        or transition.get("authority_kind") != state.get("action_kind")
        or _value_digest(str(transition.get("attempt_id", "")))
        != state.get("attempt_sha256")
    ):
        return None
    match = transition.get("request_match")
    if (
        not isinstance(match, Mapping)
        or _canonical_digest(match) != state.get("authority_sha256")
        or transition.get("request_match_sha256") != state.get("authority_sha256")
    ):
        return None
    return match


def _start_transition_decision(
    event_key: str,
    payload: Mapping[str, Any],
    tool_name: str,
    candidate: Mapping[str, str],
    root: Path,
) -> str | None:
    identity = (
        _tool_identity(payload)
        if event_key == "pre-tool-use"
        else _turn_identity(payload)
    )
    if identity is None:
        required = (
            "session, turn, and tool"
            if event_key == "pre-tool-use"
            else "session and turn"
        )
        _clear_transition(root)
        return (
            "Fastlane blocked AWS STARTED because hook "
            f"{required} identity is required."
        )
    state = _load_transition(root)
    if event_key == "pre-tool-use":
        expected = _empty_transition_state(
            stage="START_PATCH_PENDING",
            action_kind=candidate["action_kind"],
            identity=identity,
            tool_name=tool_name,
            attempt_sha256=candidate["attempt_sha256"],
            authority_sha256=candidate["authority_sha256"],
            start_patch_sha256=candidate["patch_sha256"],
        )
        if state is None:
            _store_transition(root, expected)
            return None
        if state != expected:
            _clear_transition(root)
            return "Fastlane blocked AWS STARTED because another transition is already active."
        return None
    if (
        state is None
        or state.get("stage") != "START_PATCH_PENDING"
        or not _event_matches_transition(state, identity)
        or state.get("start_tool_name_sha256") != _tool_name_digest(tool_name)
        or state.get("start_patch_sha256") != candidate["patch_sha256"]
        or state.get("attempt_sha256") != candidate["attempt_sha256"]
        or state.get("authority_sha256") != candidate["authority_sha256"]
    ):
        _clear_transition(root)
        return "Fastlane blocked AWS STARTED permission because its PreToolUse binding is absent or changed."
    return None


def _mutable_aws_transition_decision(
    event_key: str,
    payload: Mapping[str, Any],
    tool_name: str,
    request: Mapping[str, Any],
    report: Mapping[str, Any],
    root: Path,
) -> str | None:
    state = _load_transition(root)
    if state is None:
        authority_reason = _aws_authority_denial(request, report, root)
        if authority_reason is not None:
            return authority_reason
        if request.get("lane") != "STRUCTURED_API" or not _is_aws_account_tool(
            tool_name
        ):
            return "Fastlane blocked AWS STARTED because only one exact structured AWS request is supported."
        return "Fastlane blocked AWS mutation until one exact STARTED journal row is appended first."
    identity = (
        _tool_identity(payload)
        if event_key == "pre-tool-use"
        else _turn_identity(payload)
    )
    if identity is None:
        _clear_transition(root)
        required = (
            "session, turn, and tool"
            if event_key == "pre-tool-use"
            else "session and turn"
        )
        return (
            "Fastlane blocked AWS mutation because hook "
            f"{required} identity is required."
        )
    if request.get("lane") != "STRUCTURED_API" or not _is_aws_account_tool(tool_name):
        _clear_transition(root)
        return "Fastlane blocked the post-STARTED action because only one exact structured AWS request is permitted."
    if not _event_matches_transition(state, identity):
        _clear_transition(root)
        return "Fastlane blocked AWS mutation because the STARTED binding belongs to another turn or session."
    match = _transition_projection(report, state)
    if match is None:
        _clear_transition(root)
        return "Fastlane blocked AWS mutation because the consumed STARTED authority binding is absent or changed."
    expected_kind = "TEARDOWN" if state["action_kind"] == "AWS_TEARDOWN" else "MUTATE"
    if request.get("kind") != expected_kind:
        _clear_transition(root)
        return "Fastlane blocked AWS mutation because its action class does not match STARTED."
    synthetic = {"external_authority": {"request_match": dict(match)}}
    authority_reason = _aws_authority_denial(request, synthetic, root)
    if authority_reason is not None:
        _clear_transition(root)
        return authority_reason
    request_sha256 = _canonical_digest(request)
    tool_name_sha256 = _tool_name_digest(tool_name)
    if event_key == "pre-tool-use":
        if state["stage"] == "START_BOUND":
            state.update(
                {
                    "stage": "AWS_CALL_PENDING",
                    "request_sha256": request_sha256,
                    "aws_tool_name_sha256": tool_name_sha256,
                    "aws_tool_sha256": identity["tool_sha256"],
                }
            )
            _store_transition(root, state)
            return None
        if (
            state["stage"] == "AWS_CALL_PENDING"
            and state["request_sha256"] == request_sha256
            and state["aws_tool_name_sha256"] == tool_name_sha256
            and state["aws_tool_sha256"] == identity["tool_sha256"]
        ):
            return None
        _clear_transition(root)
        return "Fastlane blocked a replay or changed AWS request for the active STARTED attempt."
    if (
        state["stage"] != "AWS_CALL_PENDING"
        or state["request_sha256"] != request_sha256
        or state["aws_tool_name_sha256"] != tool_name_sha256
    ):
        _clear_transition(root)
        return "Fastlane blocked AWS permission because its matching PreToolUse binding is absent or changed."
    return None


def _journal_data_rows(text: str, heading: str, expected_cells: int) -> list[list[str]]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == heading]
    if len(starts) != 1:
        return []
    result: list[list[str]] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## "):
            break
        cells = _markdown_cells(line, expected_cells)
        if (
            cells is not None
            and cells[0] != "Evidence ID"
            and not set(cells) <= {"---", ""}
        ):
            result.append(cells)
    return result


def _terminal_patch_candidate(
    tool_name: str,
    tool_input: Mapping[str, Any],
    report: Mapping[str, Any],
    root: Path,
    state: Mapping[str, str],
) -> tuple[bool, dict[str, str] | None, str | None]:
    delta = _transition_patch_delta(tool_name, tool_input, root)
    if delta is None:
        return False, None, None
    journal = (
        DEPLOYMENT_JOURNAL
        if state.get("action_kind") == "AWS_DEPLOYMENT"
        else TEARDOWN_JOURNAL
    )
    if journal not in delta["changed_sections"]:
        return False, None, None
    changes = delta["changes"].get(journal, {})
    additions = changes.get("additions", [])
    deletions = changes.get("deletions", [])
    expected_cells = 28 if journal == DEPLOYMENT_JOURNAL else 30
    cells = (
        _markdown_cells(additions[0], expected_cells) if len(additions) == 1 else None
    )
    terminal_statuses = {"SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN"}
    if cells is None or cells[-1] not in terminal_statuses:
        return False, None, None
    malformed = "Fastlane blocked an AWS terminal patch that is not exactly bound to the observed tool result."
    if (
        delta["changed_sections"] != {journal}
        or deletions
        or _value_digest(cells[1]) != state.get("attempt_sha256")
        or re.fullmatch(r"EV-\d{4,}", cells[0]) is None
        or cells[-4]
        != (
            "HOOK_RESULT: TOOL_USE_SHA256="
            + state.get("aws_tool_sha256", "")
            + "; RESPONSE_SHA256="
            + state.get("response_sha256", "")
        )
        or _parse_utc_datetime(cells[-5]) is None
    ):
        return True, None, malformed
    current_rows = _journal_data_rows(
        str(delta["current_text"]), journal, expected_cells
    )
    started = [
        row
        for row in current_rows
        if row[-1] == "STARTED" and _value_digest(row[1]) == state.get("attempt_sha256")
    ]
    if len(started) != 1 or cells[0] == started[0][0]:
        return True, None, malformed
    immutable = (
        tuple(range(1, 20)) if journal == DEPLOYMENT_JOURNAL else (1, *range(3, 19), 24)
    )
    if any(cells[index] != started[0][index] for index in immutable):
        return True, None, malformed
    if journal == DEPLOYMENT_JOURNAL:
        if cells[2] != "AWS-20" or cells[20] == DEPLOYMENT_PRECALL_RESULT:
            return True, None, malformed
    elif (
        cells[2] != "AWS-50"
        or cells[19] == TEARDOWN_PRECALL_RESULT
        or cells[23] == TEARDOWN_PRECALL_RESULT
    ):
        return True, None, malformed
    projection = _transition_projection(report, state)
    if projection is None:
        return True, None, malformed
    return (
        True,
        {
            "patch_sha256": str(delta["command_sha256"]),
            "status": cells[-1],
        },
        None,
    )


def _terminal_transition_decision(
    event_key: str,
    payload: Mapping[str, Any],
    tool_name: str,
    candidate: Mapping[str, str],
    root: Path,
    state: dict[str, str],
) -> str | None:
    identity = (
        _tool_identity(payload)
        if event_key == "pre-tool-use"
        else _turn_identity(payload)
    )
    if identity is None or not _event_matches_transition(state, identity):
        _clear_transition(root)
        return "Fastlane blocked AWS terminal evidence because its session and turn binding is absent."
    tool_name_sha256 = _tool_name_digest(tool_name)
    if event_key == "pre-tool-use":
        if state["stage"] == "AWS_RESULT_BOUND":
            state.update(
                {
                    "stage": "TERMINAL_PATCH_PENDING",
                    "terminal_patch_sha256": candidate["patch_sha256"],
                    "terminal_tool_name_sha256": tool_name_sha256,
                    "terminal_tool_sha256": identity["tool_sha256"],
                }
            )
            _store_transition(root, state)
            return None
        if (
            state["stage"] == "TERMINAL_PATCH_PENDING"
            and state["terminal_patch_sha256"] == candidate["patch_sha256"]
            and state["terminal_tool_name_sha256"] == tool_name_sha256
            and state["terminal_tool_sha256"] == identity["tool_sha256"]
        ):
            return None
        _clear_transition(root)
        return "Fastlane blocked duplicate or changed terminal evidence for this AWS attempt."
    if (
        state["stage"] != "TERMINAL_PATCH_PENDING"
        or state["terminal_patch_sha256"] != candidate["patch_sha256"]
        or state["terminal_tool_name_sha256"] != tool_name_sha256
    ):
        _clear_transition(root)
        return "Fastlane blocked terminal-evidence permission because its PreToolUse binding is absent or changed."
    return None


def _transition_pre_decision(
    event_key: str,
    payload: Mapping[str, Any],
    tool_name: str,
    tool_input: Mapping[str, Any],
    report: Mapping[str, Any],
    root: Path,
) -> tuple[str, str | None]:
    state = _load_transition(root)
    if state is not None and state.get("stage") in {
        "AWS_RESULT_BOUND",
        "TERMINAL_PATCH_PENDING",
    }:
        recognized, candidate, reason = _terminal_patch_candidate(
            tool_name, tool_input, report, root, state
        )
        if recognized:
            if reason is not None or candidate is None:
                return "TERMINAL", reason
            return "TERMINAL", _terminal_transition_decision(
                event_key, payload, tool_name, candidate, root, state
            )
    request = _aws_request_details(tool_name, tool_input)
    if request is not None and request.get("kind") in {"MUTATE", "TEARDOWN"}:
        return "AWS", _mutable_aws_transition_decision(
            event_key, payload, tool_name, request, report, root
        )
    recognized, candidate, reason = _started_patch_candidate(
        tool_name, tool_input, report, root
    )
    if recognized:
        if reason is not None or candidate is None:
            return "START", reason
        return "START", _start_transition_decision(
            event_key, payload, tool_name, candidate, root
        )
    return "NONE", None


def _tool_response_succeeded(payload: Mapping[str, Any]) -> bool:
    response = payload.get("tool_response")
    if not isinstance(response, Mapping):
        return False
    if response.get("isError") is True or response.get("success") is False:
        return False
    return not bool(response.get("error"))


def _transition_post_message(
    payload: Mapping[str, Any],
    tool_name: str,
    tool_input: Mapping[str, Any],
    report: Mapping[str, Any],
    root: Path,
) -> str | None:
    state = _load_transition(root)
    if state is None:
        return None
    identity = _tool_identity(payload)
    if identity is None or not _event_matches_transition(state, identity):
        _clear_transition(root)
        return "Fastlane cleared an AWS transition whose session or turn identity changed; append UNKNOWN only."
    if state["stage"] == "START_PATCH_PENDING":
        if (
            state["start_tool_sha256"] != identity["tool_sha256"]
            or state["start_tool_name_sha256"] != _tool_name_digest(tool_name)
            or state["start_patch_sha256"] != _value_digest(_tool_command(tool_input))
            or not _tool_response_succeeded(payload)
        ):
            _clear_transition(root)
            return "Fastlane could not bind STARTED; no AWS call is permitted."
        if _transition_projection(report, state) is None:
            _clear_transition(root)
            return "Fastlane rejected STARTED after Engine validation; no AWS call is permitted."
        state["stage"] = "START_BOUND"
        _store_transition(root, state)
        return "Fastlane bound STARTED. Continue with the one exact AWS request in this turn."
    request = _aws_request_details(tool_name, tool_input)
    if state["stage"] == "AWS_CALL_PENDING" and request is not None:
        if (
            state["aws_tool_sha256"] != identity["tool_sha256"]
            or state["aws_tool_name_sha256"] != _tool_name_digest(tool_name)
            or state["request_sha256"] != _canonical_digest(request)
            or "tool_response" not in payload
        ):
            _clear_transition(root)
            return "Fastlane lost the exact AWS result binding; append UNKNOWN only."
        state["stage"] = "AWS_RESULT_BOUND"
        state["response_sha256"] = _canonical_digest(payload["tool_response"])
        _store_transition(root, state)
        return (
            "Fastlane observed the AWS result. Append one terminal row now with "
            "Durable source: HOOK_RESULT: TOOL_USE_SHA256="
            + state["aws_tool_sha256"]
            + "; RESPONSE_SHA256="
            + state["response_sha256"]
        )
    if state["stage"] == "TERMINAL_PATCH_PENDING":
        valid_tool = (
            state["terminal_tool_sha256"] == identity["tool_sha256"]
            and state["terminal_tool_name_sha256"] == _tool_name_digest(tool_name)
            and state["terminal_patch_sha256"]
            == _value_digest(_tool_command(tool_input))
        )
        succeeded = valid_tool and _tool_response_succeeded(payload)
        _clear_transition(root)
        if not succeeded:
            return "Fastlane could not close the AWS result journal; append UNKNOWN on resume."
        sequence_name = (
            "aws_deployment"
            if state["action_kind"] == "AWS_DEPLOYMENT"
            else "aws_teardown"
        )
        sequence = report.get(sequence_name)
        if (
            not isinstance(sequence, Mapping)
            or _value_digest(str(sequence.get("attempt_id", "")))
            != state["attempt_sha256"]
            or sequence.get("status") == "ACTION_TERMINAL_REQUIRED"
            or sequence.get("issues")
        ):
            return "Fastlane applied terminal evidence but Engine validation requires review before any further AWS action."
        return "Fastlane closed the AWS attempt. Continue with the required read-only reconciliation."
    return None


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
    try:
        resolved_root = root.resolve(strict=False)
        resolved_cwd = cwd.resolve(strict=False)
    except OSError:
        return None
    cleaned = raw.strip().strip("'\"")
    windows_candidate = PureWindowsPath(cleaned)
    if os.name != "nt" and (windows_candidate.drive or "\\" in cleaned):
        # A Windows drive, UNC target, or backslash is ambiguous on POSIX.
        # Fail closed instead of reinterpreting a literal POSIX filename as a
        # nested path that could appear to fall within broader write authority.
        return None
    candidate = Path(cleaned)
    if not candidate.is_absolute():
        candidate = resolved_cwd / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return None
    if not _is_within(resolved, resolved_root):
        return None
    return resolved.relative_to(resolved_root).as_posix()


def _path_contains(boundary: str, requested: str) -> bool:
    boundary = boundary.replace("\\", "/").strip("/")
    requested = requested.replace("\\", "/").strip("/")
    base = boundary[:-3] if boundary.endswith("/**") else boundary
    return requested == base or requested.startswith(base + "/")


def _paths_overlap(first: str, second: str) -> bool:
    return _path_contains(first, second) or _path_contains(second, first)


def _is_file_write_tool(tool_name: str) -> bool:
    if _github_connector_capability(tool_name) is not None:
        return False
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
        rf"{SHELL_COMMAND_BOUNDARY}(?:rm|mv|cp|touch|mkdir|rmdir|sed\s+-i|tee|"
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
    file_write = _is_file_write_tool(tool_name)
    is_write = file_write or shell_write
    if not is_write:
        return None
    # File-write payloads may legitimately add strings such as ``-Path``.
    # Their exact targets come from the file tool contract, not shell parsing.
    raw_paths = _candidate_paths(tool_input) + ([] if file_write else shell_paths)
    if not raw_paths:
        return "Fastlane blocked an ambiguous file mutation because its exact target path is not observable."
    relative_paths: list[str] = []
    for raw in raw_paths:
        cleaned = raw.strip().strip("'\"")
        if os.name != "nt" and "\\" in cleaned:
            return "Fastlane blocked a file mutation with an ambiguous non-native path separator."
        relative = _relative_candidate(raw, root, cwd)
        if relative is None:
            return "Fastlane blocked a write outside the current repository boundary."
        relative_paths.append(relative)
    intent_matched, intent_denial = _bounded_lifecycle_intent_write_decision(
        tool_name,
        tool_input,
        command,
        relative_paths,
        report,
        root,
    )
    if intent_matched:
        # Lifecycle intent is owner provenance, not an ordinary Gate B write.
        # Classify it before broad write roots so those roots cannot bypass the
        # exact atomic record contract.
        return intent_denial
    authority = report.get("write_authority")
    if not isinstance(authority, Mapping) or authority.get("valid") is not True:
        closure_matched, closure_denial = _bounded_closure_write_decision(
            tool_name,
            command,
            shell_write,
            relative_paths,
            report,
            root,
        )
        if closure_matched:
            return closure_denial
        return "Fastlane blocked a file mutation because current Gate B write authority is absent."
    roots = authority.get("approved_write_roots")
    exclusions = authority.get("exclusions")
    protected = authority.get("protected_paths")
    active_set = authority.get("active_task_write_set")
    if not all(
        isinstance(value, list) for value in (roots, exclusions, protected, active_set)
    ):
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


def _verify_structure(
    lines: Sequence[str],
) -> tuple[list[str], dict[str, tuple[str, ...]]] | None:
    """Label headings and every bootstrap block, rejecting ambiguous markers."""

    labels: list[str] = []
    blocks: dict[str, tuple[str, ...]] = {}
    heading = "NONE"
    active_name: str | None = None
    active_lines: list[str] = []
    for line in lines:
        marker = BOOTSTRAP_MARKER.fullmatch(line)
        if line.startswith("<!-- bootstrap:") and marker is None:
            return None
        if marker is not None:
            name = marker.group("name")
            boundary = marker.group("boundary")
            label = f"bootstrap:{name}"
            if boundary == "start":
                if active_name is not None or name in blocks:
                    return None
                active_name = name
                active_lines = []
                labels.append(label)
                continue
            if active_name != name:
                return None
            labels.append(label)
            blocks[name] = tuple(active_lines)
            active_name = None
            active_lines = []
            continue
        if active_name is not None:
            labels.append(f"bootstrap:{active_name}")
            active_lines.append(line)
            continue
        if line.startswith("## "):
            heading = line
        labels.append(heading)
    if active_name is not None:
        return None
    return labels, blocks


def _closure_patch_delta(command: str, current_text: str) -> dict[str, Any] | None:
    """Resolve exact per-section deltas and the resulting canonical VERIFY text."""

    patch_lines = command.splitlines()
    if (
        not patch_lines
        or patch_lines[0] != "*** Begin Patch"
        or patch_lines[-1] != "*** End Patch"
        or sum(line.startswith("*** Update File:") for line in patch_lines) != 1
        or any(
            line.startswith(("*** Add File:", "*** Delete File:", "*** Move to:"))
            for line in patch_lines
        )
    ):
        return None
    update_index = next(
        index
        for index, line in enumerate(patch_lines)
        if line.startswith("*** Update File:")
    )
    body = patch_lines[update_index + 1 : -1]
    hunk_starts = [index for index, line in enumerate(body) if line.startswith("@@")]
    if not hunk_starts:
        return None
    current_lines = current_text.splitlines()
    current_structure = _verify_structure(current_lines)
    if current_structure is None:
        return None
    labels, old_blocks = current_structure
    changes: dict[str, dict[str, list[str]]] = {}
    replacements: list[tuple[int, int, list[str]]] = []
    used_ranges: list[tuple[int, int]] = []

    def record(label: str, kind: str, value: str) -> None:
        bucket = changes.setdefault(label, {"additions": [], "deletions": []})
        bucket[kind].append(value)

    for hunk_number, hunk_start in enumerate(hunk_starts):
        hunk_end = (
            hunk_starts[hunk_number + 1]
            if hunk_number + 1 < len(hunk_starts)
            else len(body)
        )
        entries = body[hunk_start + 1 : hunk_end]
        if (
            not entries
            or any(not line or line[0] not in {" ", "+", "-"} for line in entries)
            or not any(line.startswith(("+", "-")) for line in entries)
        ):
            return None
        old_lines = [line[1:] for line in entries if not line.startswith("+")]
        if not old_lines:
            return None
        matches = [
            index
            for index in range(0, len(current_lines) - len(old_lines) + 1)
            if current_lines[index : index + len(old_lines)] == old_lines
            and not any(
                index < used_end and index + len(old_lines) > used_start
                for used_start, used_end in used_ranges
            )
        ]
        if len(matches) != 1:
            return None
        start = matches[0]
        end = start + len(old_lines)
        used_ranges.append((start, end))
        replacements.append(
            (start, end, [line[1:] for line in entries if not line.startswith("-")])
        )
        pointer = start
        for entry in entries:
            prefix, value = entry[0], entry[1:]
            if prefix == " ":
                pointer += 1
                continue
            if value.startswith("## ") or value.startswith("<!-- bootstrap:"):
                return None
            if prefix == "-":
                if pointer >= len(labels) or labels[pointer] == "NONE":
                    return None
                record(labels[pointer], "deletions", value)
                pointer += 1
                continue
            left = labels[pointer - 1] if pointer > 0 else "NONE"
            right = labels[pointer] if pointer < len(labels) else left
            if left == "NONE" or (right != "NONE" and left != right):
                return None
            record(left, "additions", value)

    new_lines = list(current_lines)
    for start, end, replacement_lines in sorted(replacements, reverse=True):
        new_lines[start:end] = replacement_lines
    new_structure = _verify_structure(new_lines)
    if new_structure is None:
        return None
    _new_labels, new_blocks = new_structure
    if set(old_blocks) != set(new_blocks):
        return None
    return {
        "changes": changes,
        "changed_sections": set(changes),
        "old_blocks": old_blocks,
        "new_blocks": new_blocks,
        "new_text": "\n".join(new_lines)
        + ("\n" if current_text.endswith("\n") else ""),
    }


def _lifecycle_intent_fields(lines: Sequence[str]) -> dict[str, str] | None:
    """Parse the exact ordered three-line owner lifecycle-intent record."""

    names = ("value", "source", "recorded_at")
    if len(lines) != len(LIFECYCLE_INTENT_PREFIXES):
        return None
    result: dict[str, str] = {}
    for name, prefix, line in zip(names, LIFECYCLE_INTENT_PREFIXES, lines):
        match = re.fullmatch(re.escape(prefix) + r"`([^`]+)`", line)
        if match is None:
            return None
        result[name] = match.group(1)
    return result


def _lifecycle_intent_values_are_valid(fields: Mapping[str, str]) -> bool:
    value = fields.get("value")
    source = fields.get("source")
    recorded_at = fields.get("recorded_at")
    if value not in LIFECYCLE_INTENT_PARSE_VALUES:
        return False
    if value == "NONE":
        return source == "NONE" and recorded_at == "NONE"
    return bool(
        isinstance(source, str)
        and LIFECYCLE_INTENT_SOURCE.fullmatch(source)
        and _parse_utc_datetime(recorded_at) is not None
    )


def _lifecycle_intent_write_is_attempted(
    tool_name: str, tool_input: Mapping[str, Any], command: str
) -> bool:
    """Recognize a mutation of the three fields without matching context lines."""

    if "apply_patch" in tool_name.casefold():
        return any(
            line.startswith(("+" + prefix, "-" + prefix))
            for line in command.splitlines()
            for prefix in LIFECYCLE_INTENT_PREFIXES
        )
    try:
        serialized = json.dumps(
            tool_input, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
    except (TypeError, ValueError):
        return False
    return any(prefix in serialized for prefix in LIFECYCLE_INTENT_PREFIXES)


def _bounded_lifecycle_intent_write_decision(
    tool_name: str,
    tool_input: Mapping[str, Any],
    command: str,
    relative_paths: Sequence[str],
    report: Mapping[str, Any],
    root: Path,
) -> tuple[bool, str | None]:
    """Permit only the Engine-projected atomic owner-intent record update."""

    if not _lifecycle_intent_write_is_attempted(tool_name, tool_input, command):
        return False, None
    malformed = (
        "Fastlane blocked the AWS lifecycle-intent update because its exact "
        "non-authorizing owner-record capability is absent or malformed."
    )
    capability = report.get("aws_lifecycle_intent_write_authority")
    record = report.get("aws_lifecycle_intent")
    authorizations = report.get("authorizations")
    external = report.get("external_authority")
    allowed_values = (
        capability.get("allowed_values") if isinstance(capability, Mapping) else None
    )
    if allowed_values == LIFECYCLE_INTENT_VALUES:
        active_profile = LIFECYCLE_INTENT_VALUES
    elif allowed_values == RESIDUAL_CHOICE_VALUES:
        active_profile = RESIDUAL_CHOICE_VALUES
    else:
        active_profile = None
    if (
        not isinstance(capability, Mapping)
        or capability.get("valid") is not True
        or capability.get("kind") != "AWS_LIFECYCLE_INTENT_RECORD"
        or capability.get("authorization_id") != "AWS_LIFECYCLE_INTENT_RECORD"
        or capability.get("mode") != "BOUNDED_RELEASE_INTENT_RECORD"
        or capability.get("allowed_write_paths") != ["docs/project/VERIFY.md"]
        or capability.get("allowed_sections") != [LIFECYCLE_INTENT_SECTION]
        or capability.get("allowed_operations") != ["UPDATE_AWS_LIFECYCLE_INTENT"]
        or active_profile is None
        or capability.get("construction_authorization") != "NONE"
        or capability.get("aws_mutation_authority") != "NONE"
        or not isinstance(record, Mapping)
        or record.get("authorizes_aws_access") is not False
        or record.get("authorizes_mutation") is not False
        or not isinstance(authorizations, Mapping)
        or authorizations.get("construction") != "NONE"
        or authorizations.get("aws") != "NONE"
        or not isinstance(external, Mapping)
        or external.get("validity") == "CURRENT"
    ):
        return True, malformed
    if "apply_patch" not in tool_name.casefold():
        return True, (
            "Fastlane lifecycle intent permits only an exact file patch, not a "
            "shell or whole-file mutation."
        )
    if set(relative_paths) != {"docs/project/VERIFY.md"}:
        return True, (
            "Fastlane lifecycle intent permits writes only to docs/project/VERIFY.md."
        )
    try:
        current_text = (root / "docs/project/VERIFY.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return True, (
            "Fastlane lifecycle intent could not read the canonical VERIFY file."
        )
    delta = _closure_patch_delta(command, current_text)
    if delta is None:
        return True, (
            "Fastlane lifecycle intent requires an exact, unambiguous apply_patch hunk."
        )
    if delta["changed_sections"] != {LIFECYCLE_INTENT_SECTION}:
        return True, (
            "Fastlane lifecycle-intent patch changes VERIFY sections outside "
            "its exact authority."
        )
    changes = delta["changes"].get(LIFECYCLE_INTENT_SECTION, {})
    additions = changes.get("additions", [])
    deletions = changes.get("deletions", [])
    added = _lifecycle_intent_fields(additions)
    if (
        added is None
        or not _lifecycle_intent_values_are_valid(added)
        or added.get("value") not in active_profile
    ):
        return True, (
            "Fastlane lifecycle intent must atomically write the exact value, "
            "owner-message source, and timezone-aware recorded-at contract."
        )

    old_value = record.get("value")
    old_source = record.get("source")
    old_recorded_at = record.get("recorded_at")
    provenance_status = record.get("provenance_status")
    if provenance_status == "LEGACY_NONE":
        legacy_line = "- AWS lifecycle intent: `NONE`"
        if (
            old_value != "NONE"
            or old_source != "NONE"
            or old_recorded_at != "NONE"
            or deletions != [legacy_line]
            or re.search(
                r"^- AWS lifecycle intent (?:source|recorded at):",
                current_text,
                re.MULTILINE,
            )
            is not None
        ):
            return True, malformed
    elif provenance_status == "CURRENT":
        deleted = _lifecycle_intent_fields(deletions)
        expected_old = {
            "value": old_value,
            "source": old_source,
            "recorded_at": old_recorded_at,
        }
        if (
            deleted is None
            or deleted != expected_old
            or not all(isinstance(value, str) for value in expected_old.values())
            or not _lifecycle_intent_values_are_valid(expected_old)
        ):
            return True, malformed
    else:
        return True, malformed
    return True, None


def _markdown_cells(line: str, expected: int) -> list[str] | None:
    if not line.startswith("|") or not line.endswith("|"):
        return None
    cells = [cell.strip().strip("`") for cell in line[1:-1].split("|")]
    return cells if len(cells) == expected else None


def _unresolved_closure_value(value: str) -> bool:
    return bool(re.search(r"(?:\bTODO\b|NOT_STARTED|<[^>]+>)", value))


def _canonical_authority_values(value: str) -> list[str] | None:
    values = [item.strip() for item in re.split(r"[,;]", value) if item.strip()]
    if (
        not values
        or len(values) != len(set(values))
        or any("*" in item or "|" in item for item in values)
    ):
        return None
    return values


def _deployment_read_authority_source(
    source: str, authorized_at: str, receipt: Mapping[str, str]
) -> str | None:
    resources = _canonical_authority_values(
        receipt.get("Stack, application, and resources", "")
    )
    operations = _canonical_authority_values(
        receipt.get("Allowed read-only operations", "")
    )
    if (
        resources is None
        or operations is None
        or not source
        or any(marker in source for marker in (";", "|", "\r", "\n", "*"))
        or _parse_utc_datetime(authorized_at) is None
    ):
        return None
    return (
        f"SOURCE: {source}; AUTHORIZED_AT: {authorized_at}; "
        f"RESOURCES: {', '.join(resources)}; OPERATIONS: {', '.join(operations)}"
    )


def _read_receipt_contract(
    block: Sequence[str],
) -> tuple[dict[str, str], str] | None:
    fields = (
        "Read authorization",
        "Construction authorization",
        "Profile or role",
        "Account",
        "Region",
        "Environment",
        "Stack, application, and resources",
        "Allowed read-only operations",
        "Artifact digest",
        "Prohibited operations",
        "Valid until",
        "Approver",
    )
    if (
        len(block) != len(fields) + 3
        or block[0] != "```text"
        or block[1] != "AUTHORIZE AWS READ-ONLY PREFLIGHT"
        or block[-1] != "```"
    ):
        return None
    result: dict[str, str] = {}
    for expected, line in zip(fields, block[2:-1]):
        prefix = f"{expected}: "
        if not line.startswith(prefix):
            return None
        value = line[len(prefix) :].strip()
        if not value or _unresolved_closure_value(value):
            return None
        result[expected] = value
    if (
        re.fullmatch(r"AWS-READ-AUTH-\d{4,}", result["Read authorization"]) is None
        or re.fullmatch(r"AUTH-\d{4,}", result["Construction authorization"]) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", result["Artifact digest"]) is None
        or result["Prohibited operations"] != "ALL_MUTATIONS"
        or "*" in result["Allowed read-only operations"]
        or re.search(r"(?:codex|assistant|agent)", result["Approver"], re.IGNORECASE)
    ):
        return None
    receipt = "\n".join(block[1:-1]).strip()
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    return result, digest


def _receipt_field_replacement_is_exact(
    additions: Sequence[str], deletions: Sequence[str]
) -> bool:
    def names(lines: Sequence[str]) -> list[str] | None:
        result: list[str] = []
        for line in lines:
            name, marker, _value = line.partition(": ")
            if not marker or name in result:
                return None
            result.append(name)
        return result

    added_names = names(additions)
    deleted_names = names(deletions)
    return bool(
        added_names
        and added_names == deleted_names
        and "Read authorization" in added_names
    )


def _valid_read_provenance_row(
    line: str, receipt: Mapping[str, str], digest: str
) -> bool:
    cells = _markdown_cells(line, 17)
    if cells is None or any(_unresolved_closure_value(cell) for cell in cells):
        return False
    expected_scope = (
        f"ACCOUNT: {receipt['Account']}; REGION: {receipt['Region']}; "
        f"ENVIRONMENT: {receipt['Environment']}"
    )
    expected_resources = (
        f"RESOURCES: {receipt['Stack, application, and resources']}; "
        f"OPERATIONS: {receipt['Allowed read-only operations']}"
    )
    return bool(
        cells[0] == "Read-only preflight"
        and cells[1] == receipt["Read authorization"]
        and cells[2] == receipt["Construction authorization"]
        and cells[3] == receipt["Profile or role"]
        and cells[4] == receipt["Artifact digest"]
        and cells[5].startswith("NOT_APPLICABLE")
        and cells[6] == expected_scope
        and cells[7] == expected_resources
        and "VALID_UNTIL: " + receipt["Valid until"] in cells[8]
        and cells[9].startswith("NOT_APPLICABLE")
        and cells[10] not in {"", "NONE"}
        and cells[11] == receipt["Approver"]
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T[^ ]+", cells[12]) is not None
        and cells[13] == digest
        and cells[15] in {"PASS", "VERIFIED"}
        and cells[16] in {"AUTHORIZED", "RUNNING", "READY"}
    )


def _valid_aws20_unknown_row(line: str, attempt_id: str, evidence_id: str) -> bool:
    cells = _markdown_cells(line, 28)
    return bool(
        cells is not None
        and not any(_unresolved_closure_value(cell) for cell in cells)
        and cells[0] == evidence_id
        and cells[1] == attempt_id
        and cells[2] == "AWS-20"
        and cells[27] == "UNKNOWN"
    )


def _valid_aws30_row(
    line: str,
    attempt_id: str,
    evidence_id: str,
    receipt: Mapping[str, str],
    digest: str,
    authority_source: str,
) -> bool:
    cells = _markdown_cells(line, 28)
    expected_resources = _canonical_authority_values(
        receipt.get("Stack, application, and resources", "")
    )
    allowed_operations = _canonical_authority_values(
        receipt.get("Allowed read-only operations", "")
    )
    observed_operations = (
        _canonical_authority_values(cells[18]) if cells is not None else None
    )
    authorized_match = re.fullmatch(
        r"SOURCE: [^;|\r\n]+; AUTHORIZED_AT: (?P<at>[^;|\r\n]+); "
        r"RESOURCES: [^;|\r\n]+; OPERATIONS: [^;|\r\n]+",
        authority_source,
    )
    authorized_at = (
        _parse_utc_datetime(authorized_match.group("at"))
        if authorized_match is not None
        else None
    )
    observed_at = _parse_utc_datetime(cells[23]) if cells is not None else None
    expires_at = _parse_utc_datetime(receipt.get("Valid until"))
    expected_scope = (
        f"ACCOUNT: {receipt['Account']}; REGION: {receipt['Region']}; "
        f"ENVIRONMENT: {receipt['Environment']}"
    )
    return bool(
        cells is not None
        and not any(_unresolved_closure_value(cell) for cell in cells)
        and cells[0] == evidence_id
        and cells[1] == attempt_id
        and cells[2] == "AWS-30"
        and cells[8] == receipt["Read authorization"]
        and cells[10] == receipt["Profile or role"]
        and cells[11] == digest
        and cells[12] == receipt["Valid until"]
        and cells[13] == authority_source
        and expected_resources is not None
        and cells[16] == ", ".join(expected_resources)
        and allowed_operations is not None
        and observed_operations is not None
        and set(observed_operations).issubset(set(allowed_operations))
        and authorized_at is not None
        and observed_at is not None
        and expires_at is not None
        and authorized_at <= observed_at <= expires_at
        and cells[19] == expected_scope
        and cells[27] in {"COMPLETE", "BLOCKED", "STALE"}
    )


def _valid_aws50_unknown_row(
    line: str,
    *,
    attempt_id: str,
    started_evidence_id: str,
    started: Sequence[str],
) -> bool:
    cells = _markdown_cells(line, 30)
    if (
        cells is None
        or re.fullmatch(r"EV-\d{4,}", cells[0]) is None
        or cells[0] == started_evidence_id
        or cells[1] != attempt_id
        or cells[2] != "AWS-50"
        or cells[19] != TEARDOWN_RESUME_UNKNOWN_RESULT
        or any(cells[index] != "NONE" for index in (20, 21))
        or cells[22] != TEARDOWN_RESUME_UNKNOWN_RESIDUALS
        or cells[23] != TEARDOWN_RESUME_UNKNOWN_RESULT
        or cells[26]
        != (
            "RESUME_CLOSURE: STARTED_EVIDENCE="
            + started_evidence_id
            + "; RESULT=UNOBSERVED"
        )
        or cells[27] not in {"PASS", "VERIFIED"}
        or cells[28] != "NONE"
        or cells[29] != "UNKNOWN"
        or _parse_utc_datetime(cells[25]) is None
        or _parse_utc_datetime(started[25]) is None
        or (_parse_utc_datetime(cells[25]) or datetime.min.replace(tzinfo=timezone.utc))
        <= (
            _parse_utc_datetime(started[25])
            or datetime.max.replace(tzinfo=timezone.utc)
        )
    ):
        return False
    immutable = (1, *range(3, 19), 24)
    return all(cells[index] == started[index] for index in immutable)


def _bounded_teardown_closure_write_decision(
    tool_name: str,
    command: str,
    relative_paths: Sequence[str],
    report: Mapping[str, Any],
    root: Path,
) -> tuple[bool, str | None]:
    closure = report.get("teardown_journal_closure_authority")
    if not isinstance(closure, Mapping) or closure.get("valid") is not True:
        return False, None
    malformed = (
        "Fastlane blocked a file mutation because teardown closure authority "
        "is malformed."
    )
    authorizations = report.get("authorizations")
    construction = (
        authorizations.get("construction")
        if isinstance(authorizations, Mapping)
        else None
    )
    attempt_id = str(closure.get("attempt_id", ""))
    started_evidence_id = str(closure.get("evidence_id", ""))
    if (
        closure.get("kind") != "AWS_TEARDOWN_JOURNAL_CLOSURE"
        or closure.get("authorization_id") != "AWS_TEARDOWN_JOURNAL_CLOSURE"
        or closure.get("mode") != "BOUNDED_EVIDENCE_CLOSURE"
        or closure.get("construction_authorization") != "NONE"
        or closure.get("aws_mutation_authority") != "NONE"
        or construction != "NONE"
        or closure.get("allowed_write_paths") != ["docs/project/VERIFY.md"]
        or closure.get("allowed_sections") != [TEARDOWN_JOURNAL]
        or closure.get("allowed_operations") != ["APPEND_TEARDOWN_TERMINAL_ROW"]
        or re.fullmatch(r"AWS-TEARDOWN-\d{4,}", attempt_id) is None
        or re.fullmatch(r"EV-\d{4,}", started_evidence_id) is None
    ):
        return True, malformed
    if "apply_patch" not in tool_name.casefold():
        return True, (
            "Fastlane teardown closure permits only an exact file patch, not a "
            "shell mutation."
        )
    if set(relative_paths) != {"docs/project/VERIFY.md"}:
        return True, (
            "Fastlane teardown closure permits writes only to docs/project/VERIFY.md."
        )
    try:
        current_text = (root / "docs/project/VERIFY.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return True, (
            "Fastlane teardown closure could not read the canonical VERIFY file."
        )
    delta = _closure_patch_delta(command, current_text)
    if delta is None:
        return True, (
            "Fastlane teardown closure requires an exact, unambiguous apply_patch hunk."
        )
    if delta["changed_sections"] != {TEARDOWN_JOURNAL}:
        return True, (
            "Fastlane teardown closure patch changes VERIFY sections outside "
            "its exact authority."
        )
    changes = delta["changes"].get(TEARDOWN_JOURNAL, {})
    additions = changes.get("additions", [])
    deletions = changes.get("deletions", [])
    started = [
        row
        for row in _journal_data_rows(current_text, TEARDOWN_JOURNAL, 30)
        if row[0] == started_evidence_id
        and row[1] == attempt_id
        and row[2] == "AWS-50"
        and row[29] == "STARTED"
    ]
    if (
        deletions
        or len(additions) != 1
        or len(started) != 1
        or not _valid_aws50_unknown_row(
            additions[0],
            attempt_id=attempt_id,
            started_evidence_id=started_evidence_id,
            started=started[0],
        )
    ):
        return True, (
            "Fastlane teardown closure must append exactly one immutable-bound "
            "AWS-50 UNKNOWN row and preserve all prior evidence."
        )
    return True, None


def _bounded_closure_write_decision(
    tool_name: str,
    command: str,
    _shell_write: bool,
    relative_paths: Sequence[str],
    report: Mapping[str, Any],
    root: Path,
) -> tuple[bool, str | None]:
    """Fail closed around the Engine's exact VERIFY-only closure capability."""

    teardown_matched, teardown_denial = _bounded_teardown_closure_write_decision(
        tool_name, command, relative_paths, report, root
    )
    if teardown_matched:
        return True, teardown_denial

    closure = report.get("deployment_journal_closure_authority")
    if not isinstance(closure, Mapping) or closure.get("valid") is not True:
        return False, None
    malformed = (
        "Fastlane blocked a file mutation because deployment closure authority "
        "is malformed."
    )
    expected_contracts = {
        ("## AWS deployment action and reconciliation evidence",): (
            "APPEND_ACTION_TERMINAL_ROW",
        ),
        (
            "bootstrap:aws-read-preflight-receipt",
            "## Action authorization provenance",
            "## AWS deployment action and reconciliation evidence",
        ): (
            "RECORD_RECONCILIATION_READ_AUTHORITY",
            "APPEND_RECONCILIATION_ROW",
        ),
        ("## Current release decision",): (
            "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF",
        ),
    }
    sections = closure.get("allowed_sections")
    operations = closure.get("allowed_operations")
    paths = closure.get("allowed_write_paths")
    allowed_release_states = closure.get("allowed_release_states")
    release_contract = tuple(operations or ()) == (
        "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF",
    )
    release_states_valid = (
        allowed_release_states in (["NOT_READY"], ["NOT_READY", "RELEASE_VERIFIED"])
        if release_contract
        else allowed_release_states == []
    )
    authorizations = report.get("authorizations")
    construction = (
        authorizations.get("construction")
        if isinstance(authorizations, Mapping)
        else None
    )
    if (
        closure.get("kind") != "AWS_DEPLOYMENT_JOURNAL_CLOSURE"
        or closure.get("authorization_id") != "AWS_DEPLOYMENT_JOURNAL_CLOSURE"
        or closure.get("mode") != "BOUNDED_EVIDENCE_CLOSURE"
        or closure.get("construction_authorization") != "NONE"
        or closure.get("aws_mutation_authority") != "NONE"
        or construction != "NONE"
        or not isinstance(sections, list)
        or not all(isinstance(item, str) for item in sections)
        or not isinstance(operations, list)
        or not all(isinstance(item, str) for item in operations)
        or paths != ["docs/project/VERIFY.md"]
        or tuple(operations) != expected_contracts.get(tuple(sections))
        or not release_states_valid
        or re.fullmatch(r"AWS-DEPLOY-\d{4,}", str(closure.get("attempt_id", "")))
        is None
    ):
        return True, malformed
    if "apply_patch" not in tool_name.casefold():
        return True, (
            "Fastlane closure permits only an exact file patch, not a shell mutation."
        )
    if set(relative_paths) != {"docs/project/VERIFY.md"}:
        return True, ("Fastlane closure permits writes only to docs/project/VERIFY.md.")
    verify_path = root / "docs/project/VERIFY.md"
    try:
        current_text = verify_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return True, (
            "Fastlane closure could not read the current canonical VERIFY file."
        )
    delta = _closure_patch_delta(command, current_text)
    if delta is None:
        return True, "Fastlane closure requires an exact, unambiguous apply_patch hunk."
    if delta["changed_sections"] != set(sections):
        return True, (
            "Fastlane closure patch changes VERIFY sections outside its exact authority."
        )
    changes = delta["changes"]
    attempt_id = str(closure.get("attempt_id"))
    evidence_id = str(closure.get("evidence_id", ""))
    operation_tuple = tuple(operations)
    journal = "## AWS deployment action and reconciliation evidence"
    if operation_tuple == ("APPEND_ACTION_TERMINAL_ROW",):
        journal_delta = changes.get(journal, {})
        additions = journal_delta.get("additions", [])
        deletions = journal_delta.get("deletions", [])
        if (
            deletions
            or len(additions) != 1
            or not _valid_aws20_unknown_row(additions[0], attempt_id, evidence_id)
        ):
            return True, (
                "Fastlane closure patch must append exactly one AWS-20 UNKNOWN "
                "row and preserve all prior evidence."
            )
    elif operation_tuple == (
        "RECORD_RECONCILIATION_READ_AUTHORITY",
        "APPEND_RECONCILIATION_ROW",
    ):
        receipt_label = "bootstrap:aws-read-preflight-receipt"
        provenance_label = "## Action authorization provenance"
        receipt_delta = changes.get(receipt_label, {})
        provenance_delta = changes.get(provenance_label, {})
        journal_delta = changes.get(journal, {})
        receipt_additions = receipt_delta.get("additions", [])
        receipt_deletions = receipt_delta.get("deletions", [])
        provenance_additions = provenance_delta.get("additions", [])
        provenance_deletions = provenance_delta.get("deletions", [])
        journal_additions = journal_delta.get("additions", [])
        journal_deletions = journal_delta.get("deletions", [])
        new_blocks = delta["new_blocks"]
        receipt_contract = _read_receipt_contract(
            new_blocks.get("aws-read-preflight-receipt", ())
        )
        if (
            not _receipt_field_replacement_is_exact(
                receipt_additions, receipt_deletions
            )
            or receipt_contract is None
            or len(provenance_additions) != 1
            or len(provenance_deletions) != 1
            or len(journal_additions) != 1
            or journal_deletions
        ):
            return True, (
                "Fastlane closure patch must replace one exact read receipt and "
                "provenance row, append one reconciliation row, and preserve prior evidence."
            )
        receipt, digest = receipt_contract
        old_provenance = _markdown_cells(provenance_deletions[0], 17)
        new_provenance_cells = _markdown_cells(provenance_additions[0], 17) or [""] * 17
        authority_source = _deployment_read_authority_source(
            new_provenance_cells[10], new_provenance_cells[12], receipt
        )
        if (
            old_provenance is None
            or old_provenance[0] != "Read-only preflight"
            or old_provenance[16] != "NOT_STARTED"
            or not any(_unresolved_closure_value(cell) for cell in old_provenance)
            or not _valid_read_provenance_row(provenance_additions[0], receipt, digest)
            or authority_source is None
            or not _valid_aws30_row(
                journal_additions[0],
                attempt_id,
                evidence_id,
                receipt,
                digest,
                authority_source,
            )
        ):
            return True, (
                "Fastlane closure patch does not bind one exact AWS-30 read "
                "receipt, provenance row, and reconciliation row."
            )
    else:
        release_delta = changes.get("## Current release decision", {})
        additions = release_delta.get("additions", [])
        deletions = release_delta.get("deletions", [])

        def release_fields(lines: Sequence[str]) -> dict[str, str] | None:
            expected = {
                "Release state": "- Release state: ",
                "Active evidence cutoff": "- Active evidence cutoff: ",
            }
            result: dict[str, str] = {}
            for line in lines:
                matches = [
                    (name, prefix)
                    for name, prefix in expected.items()
                    if line.startswith(prefix)
                ]
                if len(matches) != 1:
                    return None
                name, prefix = matches[0]
                if name in result:
                    return None
                result[name] = line.removeprefix(prefix).strip().strip("`")
            return result if set(result) == set(expected) else None

        added_fields = release_fields(additions)
        deleted_fields = release_fields(deletions)
        if (
            re.fullmatch(r"EV-\d{4,}", evidence_id) is None
            or added_fields is None
            or deleted_fields is None
            or added_fields["Release state"] not in allowed_release_states
            or added_fields["Active evidence cutoff"] != evidence_id
        ):
            return True, (
                "Fastlane closure patch must update exactly the permitted "
                "release state and terminal evidence cutoff together."
            )
    return True, None


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
    return lowered.startswith("mcp__codex_apps__aws_documentation_aws___")


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
        part == "aws" or part.startswith("aws-") or part.startswith("aws_")
        for part in lowered.split("__")[1:]
    )


def _string_values(value: object) -> list[str]:
    candidates = value if isinstance(value, list) else [value]
    return [
        item.strip() for item in candidates if isinstance(item, str) and item.strip()
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
    raw_direction = (
        _first_string(tool_input, ("direction", "operation", "action", "method")) or ""
    )
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
        re.search(
            rf"{SHELL_COMMAND_BOUNDARY}(?:aws(?:\.exe)?|cdk|sam|terraform|serverless)\s+",
            lowered_command,
        )
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
        operations = [" ".join(item for item in match if item) for match in matches]
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
        marker in normalized for marker in ("delete", "destroy", "remove", "terminate")
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
    profile_match = re.search(
        r"--profile\s+['\"]?([^'\"\s;&|]+)", command, re.IGNORECASE
    )
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
        marker in normalized for marker in ("delete", "destroy", "remove", "terminate")
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
            observed_digest = (
                "sha256:" + hashlib.sha256(script.encode("utf-8")).hexdigest()
            )
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
            observed_digest = (
                "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest()
            )
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
    if authority_kind not in {
        "AWS_READ_ONLY",
        "AWS_DEPLOYMENT",
        "AWS_TEARDOWN",
    }:
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
    if (
        not isinstance(expires_in, int)
        or isinstance(expires_in, bool)
        or expires_in <= 0
    ):
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
        if authority_kind not in {
            "AWS_READ_ONLY",
            "AWS_DEPLOYMENT",
            "AWS_TEARDOWN",
        }:
            return "Fastlane blocked AWS read access because the current read-authority contract does not cover it."
    elif kind == "TEARDOWN":
        if authority_kind != "AWS_TEARDOWN":
            return "Fastlane blocked teardown because a distinct current teardown receipt is absent."
    elif authority_kind != "AWS_DEPLOYMENT":
        return "Fastlane blocked AWS mutation because exact current mutation authority is absent."
    operations = authority.get("operations")
    resources = authority.get("resources")
    if not isinstance(operations, list) or not _value_allowed(
        str(request.get("operation", "")), operations
    ):
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
        if observed is not None and (
            not expected_text or str(observed).casefold() != expected_text.casefold()
        ):
            return f"Fastlane blocked the AWS request because {key.replace('_', ' ')} does not match current authority."
    for request_key, authority_key in (
        ("artifact", "artifact_digest"),
        ("plan", "plan_binding"),
    ):
        observed = request.get(request_key)
        expected = authority.get(authority_key)
        if observed is not None and (
            not isinstance(expected, str) or str(observed) != expected
        ):
            return f"Fastlane blocked the AWS request because its {request_key} binding does not match current authority."
    if request.get("presigned_url") is True:
        return _presigned_url_expiration_denial(request, authority)
    return None


def _github_connector_capability(tool_name: str) -> str | None:
    """Return a current GitHub connector capability, if this is that connector."""

    lowered = tool_name.casefold()
    for prefix in GITHUB_CONNECTOR_TOOL_PREFIXES:
        if lowered.startswith(prefix):
            capability = lowered.removeprefix(prefix)
            if re.fullmatch(r"search_installed_reposito_[0-9a-f]{12}", capability):
                return "search_installed_repositories_v2"
            return capability or "UNKNOWN"
    return None


def _github_request_kind(tool_name: str, tool_input: Mapping[str, Any]) -> str | None:
    capability = _github_connector_capability(tool_name)
    if capability is not None:
        if capability in GITHUB_READ_ONLY_CAPABILITIES:
            return "READ"
        if capability in GITHUB_ISSUE_MUTATION_CAPABILITIES:
            return "ISSUE"
        if capability in GITHUB_BRANCH_PR_MUTATION_CAPABILITIES:
            return "BRANCH_PR"
        if capability in GITHUB_MERGE_MUTATION_CAPABILITIES:
            return "MERGE"
        return "UNKNOWN"

    command = _tool_command(tool_input).casefold()
    prefix = rf"{SHELL_COMMAND_BOUNDARY}{SHELL_WRAPPER_PREFIX}"
    if re.search(rf"{prefix}git(?:\.exe)?\s+push(?:\s|$)", command):
        return "BRANCH_PR"
    if re.search(rf"{prefix}gh(?:\.exe)?\s+(?:pr\s+merge|release\s+)", command):
        return "MERGE"
    if re.search(rf"{prefix}gh(?:\.exe)?\s+issue\s+", command):
        return "ISSUE"
    if re.search(
        rf"{prefix}gh(?:\.exe)?\s+pr\s+"
        r"(?:create|edit|close|reopen|ready|review|comment)(?:\s|$)",
        command,
    ):
        return "BRANCH_PR"
    if re.search(rf"{prefix}gh(?:\.exe)?\s+api(?:\s|$)", command):
        mutating_method = re.search(
            r"(?:--method|-X)(?:=|\s+)(?:POST|PUT|PATCH|DELETE)(?:\s|$)",
            command,
            re.IGNORECASE,
        )
        form_field = re.search(
            r"(?:^|\s)(?:-f|-F|--field|--raw-field)(?:=|\s)", command
        )
        if mutating_method or form_field:
            return "BRANCH_PR"
    return None


def _github_repository(tool_input: Mapping[str, Any]) -> str | None:
    """Return one unambiguous, safely encoded owner/name target."""

    repositories: set[str] = set()
    for key in ("repo_full_name", "repository_full_name", "repository", "repo"):
        value = tool_input.get(key)
        if isinstance(value, str) and GITHUB_REPOSITORY_NAME.fullmatch(value.strip()):
            repositories.add(value.strip())
    for key in ("repository_url", "repo_url"):
        value = tool_input.get(key)
        if isinstance(value, str):
            match = GITHUB_REPOSITORY_URL.fullmatch(value.strip())
            if match is not None:
                repositories.add(match.group("repository"))
            elif value.strip():
                return None
    owner = tool_input.get("owner")
    repo = tool_input.get("repo")
    if (
        isinstance(owner, str)
        and isinstance(repo, str)
        and "/" not in repo
        and GITHUB_REPOSITORY_NAME.fullmatch(f"{owner.strip()}/{repo.strip()}")
    ):
        repositories.add(f"{owner.strip()}/{repo.strip()}")
    return next(iter(repositories)) if len(repositories) == 1 else None


def _github_constraints(envelope: Mapping[str, str]) -> dict[str, str] | None:
    raw = str(
        envelope.get("GitHub repository, branch, and merge constraints", "NONE")
    ).strip()
    match = GITHUB_CONSTRAINTS.fullmatch(raw)
    return match.groupdict() if match is not None else None


def _github_branch(tool_input: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    values: set[str] = set()
    for key in keys:
        if key not in tool_input:
            continue
        value = tool_input.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        values.add(value.strip().removeprefix("refs/heads/"))
    return next(iter(values)) if len(values) == 1 else None


def _github_scope_denial(
    tool_name: str,
    tool_input: Mapping[str, Any],
    github_kind: str,
    envelope: Mapping[str, str],
) -> str | None:
    """Require connector mutations to match the exact approved GitHub scope."""

    capability = _github_connector_capability(tool_name)
    if capability is None:
        return (
            "Fastlane blocked shell-based GitHub publication because its exact "
            "repository and branch are not observable; use a structured GitHub "
            "connector request."
        )
    if github_kind == "UNKNOWN":
        return "Fastlane blocked an unrecognized GitHub connector capability."
    if github_kind == "READ":
        return None
    constraints = _github_constraints(envelope)
    if constraints is None:
        return "Fastlane blocked GitHub publication because exact repository constraints are absent or malformed."
    repository = _github_repository(tool_input)
    if repository is None:
        return "Fastlane blocked GitHub publication because its exact repository is not observable."
    if repository.casefold() != constraints["repository"].casefold():
        return "Fastlane blocked GitHub publication because its repository does not match current authority."
    if github_kind == "MERGE" and constraints["merge"] != "ALLOWED":
        return (
            "Fastlane blocked GitHub merge or release because it exceeds the "
            "current GitHub boundary and current constraints prohibit it."
        )
    if capability in GITHUB_UNOBSERVABLE_PROTECTED_CAPABILITIES:
        return (
            "Fastlane blocked this GitHub operation because its exact target "
            "branch is not observable."
        )

    branch_keys: Sequence[str] | None = None
    if capability == "create_pull_request":
        branch_keys = ("base", "base_branch")
    elif capability == "create_release":
        branch_keys = ("target_commitish",)
    elif capability == "update_pull_request" and any(
        key in tool_input for key in ("base", "base_branch")
    ):
        branch_keys = ("base", "base_branch")
    elif capability in GITHUB_DIRECT_BRANCH_CAPABILITIES:
        branch_keys = ("branch", "branch_name", "ref")
    if branch_keys is not None:
        branch = _github_branch(tool_input, branch_keys)
        if branch is None:
            return "Fastlane blocked GitHub publication because its exact branch is not observable."
        if branch != constraints["branch"]:
            return "Fastlane blocked GitHub publication because its branch does not match current authority."

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
    # A permitted file-tool payload is data, not an AWS or GitHub command.
    # Do not reinterpret receipt text inside apply_patch as external access.
    if _is_file_write_tool(tool_name):
        return None

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
    if github_kind in {None, "READ"}:
        return None
    if construction_authorization == "NONE":
        return "Fastlane blocked GitHub publication because current construction authority is absent."
    scope_denial = _github_scope_denial(tool_name, tool_input, github_kind, envelope)
    if scope_denial is not None:
        return scope_denial
    allowed_github = {
        "ISSUE": {"ISSUES", "BRANCH_AND_PR", "MERGE_WHEN_GREEN"},
        "BRANCH_PR": {"BRANCH_AND_PR", "MERGE_WHEN_GREEN"},
        "MERGE": {"MERGE_WHEN_GREEN"},
        "UNKNOWN": set(),
    }
    if github_boundary not in allowed_github[github_kind]:
        return "Fastlane blocked GitHub publication because it exceeds the current GitHub boundary."
    return None


def _broad_escalation(
    payload: Mapping[str, Any], tool_input: Mapping[str, Any]
) -> bool:
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
    argv = list(command)
    if not argv or not Path(argv[0]).is_absolute():
        return False
    completed = subprocess.run(
        argv,
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
        try:
            trusted_git = _resolve_trusted_git(root)
        except OSError:
            return (
                "Fastlane validation could not resolve trusted Git. Review local "
                "Git setup before continuing."
            )
        if not runner(root, [trusted_git, "diff", "--check"]):
            return (
                "Fastlane validation found a diff-format problem. Run git diff --check."
            )
    if "update_manifest.py" in command and "--write" in command:
        check = [
            sys.executable,
            str(root / "scripts" / "update_manifest.py"),
            "--check",
        ]
        if not runner(root, check):
            return "Fastlane manifest validation did not pass. Run the manifest check before continuing."
    return None


def _resolve_trusted_git(root: Path) -> str:
    scripts = str(root / "scripts")
    inserted = scripts not in sys.path
    if inserted:
        sys.path.insert(0, scripts)
    try:
        from fastlane_process import resolve_trusted_git

        return resolve_trusted_git(root)
    finally:
        if inserted:
            sys.path.remove(scripts)


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
        _clear_transition(root)
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
        authority_envelope = envelope or load_hook_constraints(report)
        transition_mode, reason = _transition_pre_decision(
            event_key, payload, tool_name, tool_input, report, root
        )
        if reason is None and transition_mode not in {"AWS", "TERMINAL"}:
            reason = _authority_denial(
                tool_name, tool_input, report, authority_envelope, root, cwd
            )
            if reason is not None and transition_mode == "START":
                _clear_transition(root)
        if (
            event_key == "permission-request"
            and reason is None
            and _broad_escalation(payload, tool_input)
        ):
            reason = "Fastlane blocked a broad escalation that exceeds the current project boundary."
        if reason is None:
            return None
        return (
            pre_tool_denial(reason)
            if event_key == "pre-tool-use"
            else permission_denial(reason)
        )

    if event_key == "post-tool-use":
        tool_name, tool_input = _event_tool(payload)
        messages: list[str] = []
        validation_message = _post_validation(
            tool_name, tool_input, root, validation_runner
        )
        if validation_message:
            messages.append(validation_message)
        if _load_transition(root) is not None:
            report = doctor_report or run_doctor(root)
            transition_message = _transition_post_message(
                payload, tool_name, tool_input, report, root
            )
            if transition_message:
                messages.append(transition_message)
        message = _bounded_text(" ".join(messages)) if messages else None
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
