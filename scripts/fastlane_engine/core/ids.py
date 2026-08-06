"""Project-relative path and canonical cell primitives.

The functions are pure and preserve the existing Markdown/path grammar. They do
not determine whether a domain record is ready or authorized.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Pattern


STABLE_CONTRACT_ID = re.compile(r"[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
TASK_ID = re.compile(r"TASK-\d+")
UNRESOLVED_TOKEN = re.compile(
    r"(?<![A-Z0-9])(?:TODO|TBD|TBC|UNKNOWN|UNASSIGNED)(?![A-Z0-9])",
    re.IGNORECASE,
)
EVIDENCE_PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:TODO|TBD|TBC|UNKNOWN|UNASSIGNED|PENDING|PLACEHOLDER|"
    r"NOT[ _-]*STARTED|NONE|N/?A)\b|<[^>]+>",
    re.IGNORECASE,
)


def clean_cell(value: Any) -> str:
    """Remove surrounding whitespace and one Markdown code-span wrapper."""

    text = str(value).strip()
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        text = text[1:-1].strip()
    return text


def unresolved(value: str) -> bool:
    """Return whether a canonical value is empty, templated, or unresolved."""

    cleaned = clean_cell(value)
    return (
        not cleaned
        or UNRESOLVED_TOKEN.search(cleaned) is not None
        or "<" in cleaned
        or ">" in cleaned
    )


def explicit_value(value: str, *, allow_none: bool = False) -> bool:
    """Return whether a value is concrete under the current contract grammar."""

    cleaned = clean_cell(value)
    if unresolved(cleaned):
        return False
    return allow_none or cleaned not in {"NONE", "NOT_RECORDED", "UNASSIGNED"}


def none_with_reason(value: str) -> bool:
    """Recognize the existing exact NONE-with-reason compatibility form."""

    cleaned = clean_cell(value)
    return bool(re.fullmatch(r"NONE\s+(?:-|â€”)\s+\S.*", cleaned)) and not unresolved(
        cleaned
    )


def parse_exact_id_list(
    value: str, pattern: Pattern[str], field_name: str
) -> list[str]:
    """Parse a duplicate-free comma-separated ID list or ``NONE``."""

    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return []
    if unresolved(cleaned):
        raise ValueError(f"{field_name} is unresolved")
    items = [item.strip() for item in cleaned.split(",")]
    if any(pattern.fullmatch(item) is None for item in items):
        raise ValueError(
            f"{field_name} must contain comma-separated {pattern.pattern} IDs or NONE"
        )
    if len(items) != len(set(items)):
        raise ValueError(f"{field_name} contains duplicate IDs")
    return items


def canonical_id_list(value: str, pattern: Pattern[str], field_name: str) -> list[str]:
    """Parse IDs and require their exact comma-space canonical representation."""

    identifiers = parse_exact_id_list(value, pattern, field_name)
    if clean_cell(value) != ", ".join(identifiers):
        raise ValueError(f"{field_name} must use comma-space-separated IDs")
    return identifiers


def validate_relative_path(value: Any) -> str | None:
    """Return one safe repository-relative POSIX path or ``None``."""

    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        return None
    return value


__all__ = (
    "EVIDENCE_PLACEHOLDER_PATTERN",
    "STABLE_CONTRACT_ID",
    "TASK_ID",
    "UNRESOLVED_TOKEN",
    "canonical_id_list",
    "clean_cell",
    "explicit_value",
    "none_with_reason",
    "parse_exact_id_list",
    "unresolved",
    "validate_relative_path",
)
