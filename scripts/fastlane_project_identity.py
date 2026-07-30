#!/usr/bin/env python3
"""Canonical Fastlane project-name and AWS Region syntax contract."""

from __future__ import annotations

import re
import unicodedata


PROJECT_NAME_TOKEN = "{{PROJECT_NAME}}"
PROJECT_NAME_MAX_CHARACTERS = 100
PROJECT_NAME_MAX_UTF8_BYTES = 400
AWS_REGION_MAX_CHARACTERS = 63
AWS_REGION_PATTERN = re.compile(
    r"[a-z]{2,8}(?:-[a-z]+)+-[1-9][0-9]*",
    re.ASCII,
)
RESERVED_RENDER_TOKENS = frozenset(
    {
        PROJECT_NAME_TOKEN,
        "{{AWS_REGION}}",
        "{{COST_POSTURE}}",
        "{{SETUP_METHOD}}",
        "{{SETUP_STATUS}}",
    }
)
ALLOWED_FORMAT_CHARACTERS = {"\u200c", "\u200d"}
MARKDOWN_INLINE_ENTITIES = {
    "&": "&#38;",
    "<": "&#60;",
    ">": "&#62;",
    "\\": "&#92;",
    "`": "&#96;",
    "|": "&#124;",
    "[": "&#91;",
    "]": "&#93;",
    "*": "&#42;",
    "_": "&#95;",
}


def normalize_project_name(raw: str) -> str:
    """Return one visible, single-line NFC project name or fail closed."""

    if not isinstance(raw, str):
        raise ValueError("--project-name must contain visible text")
    normalized = unicodedata.normalize("NFC", raw)
    for character in normalized:
        category = unicodedata.category(character)
        if category in {"Zl", "Zp"} or category in {"Cc", "Cs", "Co", "Cn"}:
            raise ValueError(
                "--project-name must be one line and cannot contain control, "
                "private-use, unassigned, or direction-formatting characters"
            )
        if category == "Cf" and character not in ALLOWED_FORMAT_CHARACTERS:
            raise ValueError(
                "--project-name must be one line and cannot contain control, "
                "private-use, unassigned, or direction-formatting characters"
            )
    normalized = normalized.strip()
    if not normalized or not any(not character.isspace() for character in normalized):
        raise ValueError("--project-name must contain visible text")
    if (
        len(normalized) > PROJECT_NAME_MAX_CHARACTERS
        or len(normalized.encode("utf-8")) > PROJECT_NAME_MAX_UTF8_BYTES
    ):
        raise ValueError(
            "--project-name must be at most 100 Unicode characters and 400 UTF-8 bytes"
        )
    if any(token in normalized for token in RESERVED_RENDER_TOKENS):
        raise ValueError("--project-name contains a reserved Fastlane render token")
    if not any(
        unicodedata.category(character)[0] in {"L", "N", "S"}
        for character in normalized
    ):
        raise ValueError("--project-name must contain visible text")
    return normalized


def normalize_aws_region(raw: str) -> str:
    """Normalize one canonical Region-shaped identifier; availability is external."""

    if not isinstance(raw, str):
        raise ValueError(
            "--region must be a canonical AWS Region identifier such as us-west-2; "
            "current availability is verified later with AWS Core"
        )
    normalized = raw.strip(" ").lower()
    if (
        len(normalized) > AWS_REGION_MAX_CHARACTERS
        or AWS_REGION_PATTERN.fullmatch(normalized) is None
    ):
        raise ValueError(
            "--region must be a canonical AWS Region identifier such as us-west-2; "
            "current availability is verified later with AWS Core"
        )
    return normalized


def markdown_inline(value: str) -> str:
    """Encode structural Markdown/HTML characters without changing display text."""

    return "".join(
        MARKDOWN_INLINE_ENTITIES.get(character, character) for character in value
    )
