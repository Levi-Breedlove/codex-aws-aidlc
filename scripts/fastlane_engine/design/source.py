"""Application-source disposition and protected-root validation.

Canonical inputs are caller-observed project records. Outputs are immutable
Design projections or ordered validation issues. This module performs no I/O,
routing, mutation, approval, authorization, or owner-facing rendering.
"""

from __future__ import annotations


import re

from ..core.contracts import (
    markdown_tables,
    parse_task_write_set,
    without_fenced_code,
)
from ..core.ids import clean_cell
from .models import (
    APPLICATION_SOURCE_BROWNFIELD,
    APPLICATION_SOURCE_DISPOSITION_FIELD,
    APPLICATION_SOURCE_GREENFIELD,
    APPLICATION_SOURCE_INFRASTRUCTURE_ONLY,
    APPLICATION_SOURCE_NOT_APPLICABLE,
    ApplicationSourceDisposition,
)


def parse_application_source_disposition(
    value: str,
) -> ApplicationSourceDisposition:
    """Parse the exact schema-7 application-source decision grammar."""

    normalized = clean_cell(value)
    if normalized == APPLICATION_SOURCE_INFRASTRUCTURE_ONLY:
        return ApplicationSourceDisposition(APPLICATION_SOURCE_NOT_APPLICABLE)
    for kind in (APPLICATION_SOURCE_GREENFIELD, APPLICATION_SOURCE_BROWNFIELD):
        prefix = f"{kind}: "
        if not normalized.startswith(prefix):
            continue
        raw_paths = [item.strip() for item in normalized[len(prefix) :].split(";")]
        try:
            paths = tuple(
                parse_task_write_set(
                    ",".join(raw_paths), APPLICATION_SOURCE_DISPOSITION_FIELD
                )
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if not paths:
            raise ValueError("Application source disposition has no source paths")
        if kind == APPLICATION_SOURCE_GREENFIELD and paths != ("app/**",):
            raise ValueError(
                "GREENFIELD_APP_ROOT must be exactly GREENFIELD_APP_ROOT: app/**"
            )
        return ApplicationSourceDisposition(kind, paths)
    raise ValueError(
        "Application source disposition must use GREENFIELD_APP_ROOT: app/**, "
        "BROWNFIELD_PRESERVE: path/**; another/path/**, or "
        "NOT_APPLICABLE — INFRASTRUCTURE_ONLY"
    )


def _brownfield_source_contract_section(text: str) -> str:
    heading = "### 1.2 Brownfield baseline and preservation contract"
    structural = without_fenced_code(text)
    matches = list(re.finditer(rf"^{re.escape(heading)}\s*$", structural, re.MULTILINE))
    if len(matches) != 1:
        return ""
    following = structural[matches[0].end() :]
    next_heading = re.search(r"^##\s+2\.", following, re.MULTILINE)
    end = matches[0].end() + (next_heading.start() if next_heading else len(following))
    return text[matches[0].end() : end]


def _contains_exact_source_path(value: str, path: str) -> bool:
    """Match one recorded source path without accepting a longer lookalike."""

    return (
        re.search(
            rf"(?<![A-Za-z0-9._/*-]){re.escape(path)}(?![A-Za-z0-9._/*-])",
            value,
            re.IGNORECASE,
        )
        is not None
    )


def validate_application_source_disposition(
    disposition: ApplicationSourceDisposition,
    *,
    project_mode: str | None,
    work_kind: str | None,
    prd_text: str,
) -> list[str]:
    """SAFETY: Reject source dispositions that could create a competing app."""

    issues: list[str] = []
    if disposition.kind == APPLICATION_SOURCE_NOT_APPLICABLE:
        if work_kind != "INFRASTRUCTURE":
            issues.append(
                "APPLICATION_SOURCE_DISPOSITION_INVALID: "
                "NOT_APPLICABLE — INFRASTRUCTURE_ONLY requires Work kind INFRASTRUCTURE"
            )
        return issues
    if disposition.kind == APPLICATION_SOURCE_GREENFIELD:
        if project_mode != "greenfield":
            issues.append(
                "APPLICATION_SOURCE_DISPOSITION_INVALID: GREENFIELD_APP_ROOT "
                "requires greenfield project mode"
            )
        if work_kind == "INFRASTRUCTURE":
            issues.append(
                "APPLICATION_SOURCE_DISPOSITION_INVALID: infrastructure-only work "
                "must use NOT_APPLICABLE — INFRASTRUCTURE_ONLY"
            )
        return issues
    if disposition.kind != APPLICATION_SOURCE_BROWNFIELD:
        issues.append(
            "APPLICATION_SOURCE_DISPOSITION_INVALID: unknown application source disposition kind"
        )
        return issues
    if project_mode != "brownfield":
        issues.append(
            "APPLICATION_SOURCE_DISPOSITION_INVALID: BROWNFIELD_PRESERVE requires brownfield project mode"
        )
        return issues
    preserved_section = _brownfield_source_contract_section(prd_text)
    tables = markdown_tables(preserved_section)
    protected_paths = ""
    preservation_rows: list[list[str]] = []
    for table in tables:
        headers = table[0]
        if headers == ["Field", "Brownfield baseline"]:
            protected_paths = next(
                (
                    row[1]
                    for row in table[2:]
                    if len(row) == 2 and row[0] == "Protected files and components"
                ),
                "",
            )
        elif headers == [
            "Preservation ID",
            "Behavior, asset, or constraint to preserve",
            "How it is verified before change",
            "Allowed change",
            "Explicitly prohibited or approval-required change",
        ]:
            preservation_rows = table[2:]

    missing_baseline = [
        path
        for path in disposition.paths
        if not _contains_exact_source_path(protected_paths, path)
    ]
    missing_preservation = [
        path
        for path in disposition.paths
        if not any(
            _contains_exact_source_path(" | ".join(row[1:]), path)
            for row in preservation_rows
        )
    ]
    if missing_baseline or missing_preservation:
        details: list[str] = []
        if missing_baseline:
            details.append(
                "Protected files and components: " + ", ".join(missing_baseline)
            )
        if missing_preservation:
            details.append("matching PRES record: " + ", ".join(missing_preservation))
        issues.append(
            "APPLICATION_SOURCE_DISPOSITION_CONFLICT: brownfield source roots must "
            "appear unchanged in both Gate A brownfield records; missing from "
            + "; ".join(details)
        )
    return issues
