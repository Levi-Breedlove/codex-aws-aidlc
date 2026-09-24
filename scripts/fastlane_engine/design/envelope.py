"""Construction-envelope parsing and deterministic boundary validation.

Canonical inputs are caller-observed project records. Outputs are immutable
Design projections or ordered validation issues. This module performs no I/O,
routing, mutation, approval, authorization, or owner-facing rendering.
"""

from __future__ import annotations


import hashlib
import re
from datetime import datetime

from ..core.contracts import (
    SHELL_CONTROL,
    fenced_command_payloads,
    parse_task_external_state,
    parse_task_write_set,
    path_boundaries_overlap,
    path_boundary_contains,
    without_fenced_code,
)
from ..core.ids import TASK_ID, clean_cell, explicit_value, parse_exact_id_list
from .models import (
    APPLICATION_SOURCE_GREENFIELD,
    APPLICATION_SOURCE_NOT_APPLICABLE,
    ApplicationSourceDisposition,
)


AUTHORIZED_ID = re.compile(r"[A-Z][A-Z0-9_]*-\d+")


GITHUB_CONSTRAINT = re.compile(
    r"REPO: (?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+); "
    r"BRANCH: (?P<branch>[A-Za-z0-9._/-]+); MERGE: (?P<merge>ALLOWED|PROHIBITED)"
)


AWS_ENVIRONMENT = re.compile(
    r"ENVIRONMENT: (?P<name>[^;\r\n]+); CLASS: (?P<class>NON_PRODUCTION|PRODUCTION)"
)


AWS_EXACT_ARTIFACT = re.compile(r"EXACT_DIGEST: sha256:[0-9a-f]{64}")


AWS_DERIVED_ARTIFACT = re.compile(r"DERIVED_FROM_AUTHORIZED_SOURCE: (?P<rule>[^\r\n]+)")


TASK_BOUNDARY_DERIVED = "DERIVED_FROM_AUTHORIZED_IDS_AND_WRITE_SET"


def canonical_envelope_sha256(prd_text: str) -> str:
    heading = "## 28. Construction envelope"
    structural = without_fenced_code(prd_text)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*$", structural, re.MULTILINE)
    )
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one heading {heading!r}")
    lines = prd_text[matches[0].end() :].splitlines()
    structural_lines = structural[matches[0].end() :].splitlines()
    start = next(
        (index for index, line in enumerate(structural_lines) if line.startswith("|")),
        None,
    )
    if start is None:
        raise ValueError("Construction envelope Markdown table is missing")
    table_lines: list[str] = []
    for line, structural_line in zip(lines[start:], structural_lines[start:]):
        if not structural_line.startswith("|"):
            break
        table_lines.append(line.rstrip())
    if len(table_lines) < 3:
        raise ValueError("Construction envelope Markdown table is malformed")
    payload = ("\n".join(table_lines) + "\n").encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def parse_authorized_ids(value: str) -> list[str]:
    cleaned = clean_cell(value)
    match = re.fullmatch(
        r"REQ: (?P<req>REQ-\d{4,}); DES: (?P<des>DES-\d{4,}); SCOPE_IDS: (?P<scope>.+)",
        cleaned,
    )
    if match is None:
        raise ValueError(
            "Authorized requirement and design IDs must use "
            "REQ: REQ-0001; DES: DES-0001; SCOPE_IDS: FR-001, SEC-001"
        )
    scope = parse_exact_id_list(
        match.group("scope"), AUTHORIZED_ID, "Authorized SCOPE_IDS"
    )
    if not scope:
        raise ValueError("Authorized SCOPE_IDS cannot be NONE")
    ids = [match.group("req"), match.group("des"), *scope]
    if len(ids) != len(set(ids)):
        raise ValueError("Authorized requirement and design IDs contain duplicates")
    return ids


def parse_envelope_paths(value: str, label: str, *, allow_none: bool) -> list[str]:
    cleaned = clean_cell(value)
    if allow_none and cleaned == "NONE":
        return []
    prefix = "PATHS: "
    if not cleaned.startswith(prefix):
        raise ValueError(
            f"{label} must use PATHS: path; path" + (" or NONE" if allow_none else "")
        )
    items = [item.strip() for item in cleaned[len(prefix) :].split(";")]
    return parse_task_write_set(",".join(items), label)


def validate_application_source_root(
    paths: list[str], project_mode: str | None
) -> None:
    """Compatibility validator for the legacy inferred greenfield source root."""

    if project_mode != "greenfield":
        return
    top_level = {path.split("/", 1)[0].casefold() for path in paths}
    if top_level & {"apps", "src"}:
        raise ValueError(
            "Greenfield application source must use singular app/**; "
            "apps/** and src/** are not allowed"
        )
    if "app" not in top_level:
        raise ValueError(
            "Greenfield Allowed repository write set must include application source under app/**"
        )


def validate_application_source_write_set(
    disposition: ApplicationSourceDisposition,
    paths: list[str],
) -> None:
    """SAFETY: Bind the Gate B source decision to the construction write set."""

    top_level = {path.split("/", 1)[0].casefold() for path in paths}
    if disposition.kind == APPLICATION_SOURCE_NOT_APPLICABLE:
        if top_level & {"app", "apps", "src"}:
            raise ValueError(
                "APPLICATION_SOURCE_PARALLEL_ROOT: infrastructure-only work "
                "cannot authorize app/**, apps/**, or src/**"
            )
        return
    if disposition.kind == APPLICATION_SOURCE_GREENFIELD:
        if top_level & {"apps", "src"}:
            raise ValueError(
                "APPLICATION_SOURCE_PARALLEL_ROOT: greenfield work cannot "
                "authorize apps/** or src/** alongside app/**"
            )
        if not any(
            path_boundary_contains("app/**", path)
            or path_boundary_contains(path, "app/**")
            for path in paths
        ):
            raise ValueError(
                "APPLICATION_SOURCE_DISPOSITION_INVALID: greenfield Allowed "
                "repository write set must include application source under app/**"
            )
        return
    missing = [
        source
        for source in disposition.paths
        if not any(path_boundaries_overlap(source, path) for path in paths)
    ]
    if missing:
        raise ValueError(
            "APPLICATION_SOURCE_DISPOSITION_INVALID: Allowed repository write "
            "set does not cover approved brownfield source roots: " + ", ".join(missing)
        )
    for path in paths:
        if path.split("/", 1)[0].casefold() not in {"app", "apps", "src"}:
            continue
        if not any(
            path_boundaries_overlap(source, path) for source in disposition.paths
        ):
            raise ValueError(
                "APPLICATION_SOURCE_PARALLEL_ROOT: brownfield write set adds "
                "an unapproved parallel application root: " + path
            )


def parse_envelope_targets(value: str) -> list[str]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return []
    prefix = "TARGETS: "
    if not cleaned.startswith(prefix):
        raise ValueError(
            "Allowed external-state targets must use TARGETS: target; target or NONE"
        )
    items = [item.strip() for item in cleaned[len(prefix) :].split(";")]
    return parse_task_external_state(",".join(items), "Gate B envelope")


def parse_task_boundary(value: str) -> tuple[str, set[str]]:
    cleaned = clean_cell(value)
    if cleaned == TASK_BOUNDARY_DERIVED:
        return "DERIVED", set()
    prefix = "TASK_IDS: "
    if not cleaned.startswith(prefix):
        raise ValueError(
            "Task boundary must be exactly DERIVED_FROM_AUTHORIZED_IDS_AND_WRITE_SET "
            "or TASK_IDS: TASK-001, TASK-002"
        )
    values = [item.strip() for item in cleaned[len(prefix) :].split(",")]
    if not values or any(TASK_ID.fullmatch(item) is None for item in values):
        raise ValueError("TASK_IDS must contain only comma-separated TASK IDs")
    if len(values) != len(set(values)):
        raise ValueError("TASK_IDS contains duplicates")
    return "EXPLICIT", set(values)


def parse_command_prefixes(value: str) -> list[str]:
    cleaned = clean_cell(value)
    prefix = "ALLOW_PREFIXES: "
    if not cleaned.startswith(prefix):
        raise ValueError(
            "Local command boundary must use ALLOW_PREFIXES: prefix; prefix"
        )
    values = [item.strip() for item in cleaned[len(prefix) :].split(";")]
    if not values or any(not item for item in values):
        raise ValueError("Local command boundary contains an empty prefix")
    if any(
        SHELL_CONTROL.search(item) or item.startswith(("-", "#")) for item in values
    ):
        raise ValueError("Local command prefixes cannot contain shell-control syntax")
    if len(values) != len(set(values)):
        raise ValueError("Local command boundary contains duplicate prefixes")
    return values


def validation_commands(section: str, task_id: str) -> list[str]:
    commands: list[str] = []
    for command in fenced_command_payloads(section):
        if command.lstrip(" \t").startswith("#"):
            continue
        if SHELL_CONTROL.search(command):
            raise ValueError(
                f"{task_id}: Validation command contains shell-control syntax"
            )
        commands.append(command)
    if not commands:
        raise ValueError(f"{task_id}: Validation requires at least one fenced command")
    return commands


def command_matches_prefix(command: str, prefix: str) -> bool:
    return command == prefix or command.startswith(prefix + " ")


def parse_github_constraints(value: str, boundary: str) -> str | None:
    cleaned = clean_cell(value)
    if boundary in {"NONE", "READ_ONLY"}:
        if cleaned != "NONE":
            raise ValueError(f"GitHub boundary {boundary} requires constraints NONE")
        return None
    match = GITHUB_CONSTRAINT.fullmatch(cleaned)
    if match is None:
        raise ValueError(
            "GitHub write constraints must be exactly "
            "REPO: owner/name; BRANCH: branch; MERGE: ALLOWED|PROHIBITED"
        )
    branch = match.group("branch")
    if (
        branch.startswith(("/", "-"))
        or branch.endswith("/")
        or "//" in branch
        or ".." in branch
        or "@{" in branch
    ):
        raise ValueError("GitHub branch constraint is unsafe")
    merge = match.group("merge")
    expected_merge = "ALLOWED" if boundary == "MERGE_WHEN_GREEN" else "PROHIBITED"
    if merge != expected_merge:
        raise ValueError(f"GitHub boundary {boundary} requires MERGE: {expected_merge}")
    return match.group("repo")


def parse_future_expiry_at(value: str, observed_at: datetime) -> datetime:
    """Parse an expiry relative to the invocation's single observed clock."""

    cleaned = clean_cell(value)
    match = re.fullmatch(
        r"Expires at (?P<timestamp>[^\s;]+); earlier completion: (?P<condition>[^\r\n]+)",
        cleaned,
    )
    if match is None:
        raise ValueError(
            "Authorization expiry must use Expires at <ISO8601>; earlier completion: <exact condition>"
        )
    if not explicit_value(match.group("condition"), allow_none=False):
        raise ValueError("Authorization earlier-completion condition must be explicit")
    candidate = match.group("timestamp")
    normalized = candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate
    try:
        expires_at = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Authorization expiry timestamp is not ISO 8601") from exc
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValueError("Authorization expiry timestamp must include a timezone")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("Observed time must include a timezone")
    if expires_at <= observed_at:
        raise ValueError("Construction authorization is expired")
    return expires_at


def parse_aws_environment(value: str) -> tuple[str, str]:
    cleaned = clean_cell(value)
    match = AWS_ENVIRONMENT.fullmatch(cleaned)
    if match is None or not explicit_value(match.group("name")):
        raise ValueError(
            "AWS environment must use "
            "ENVIRONMENT: <exact>; CLASS: NON_PRODUCTION|PRODUCTION"
        )
    return match.group("name"), match.group("class")


def validate_aws_artifact(value: str, baseline: str) -> None:
    cleaned = clean_cell(value)
    if AWS_EXACT_ARTIFACT.fullmatch(cleaned) is not None:
        return
    match = AWS_DERIVED_ARTIFACT.fullmatch(cleaned)
    if match is None:
        raise ValueError(
            "AWS artifact authorization must use EXACT_DIGEST: sha256:<64 lowercase> "
            "or DERIVED_FROM_AUTHORIZED_SOURCE: <deterministic rule>"
        )
    rule = match.group("rule")
    if (
        not explicit_value(rule)
        or baseline not in rule
        or "sha256" not in rule.casefold()
    ):
        raise ValueError(
            "Derived AWS artifact authorization must bind the authorized baseline "
            "commit and an exact SHA-256 derivation rule"
        )
