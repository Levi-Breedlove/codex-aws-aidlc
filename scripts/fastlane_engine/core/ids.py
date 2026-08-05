"""Project-relative path and canonical cell primitives.

The functions are pure and preserve the existing Markdown/path grammar. They do
not determine whether a domain record is ready or authorized.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


def clean_cell(value: Any) -> str:
    """Remove surrounding whitespace and one Markdown code-span wrapper."""

    text = str(value).strip()
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        text = text[1:-1].strip()
    return text


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
