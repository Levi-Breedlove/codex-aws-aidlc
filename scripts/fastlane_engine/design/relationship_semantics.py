"""Deterministic semantic categories for human architecture relationships."""

from __future__ import annotations

import re
from typing import Any


_RELATION_CATEGORY_PATTERNS = (
    (
        "OBSERVABILITY",
        re.compile(
            r"\b(?:emit\w*|publish\w*|record\w*|send\w*)\b.*"
            r"\b(?:telemetr\w*|signal\w*|metric\w*|log\w*|trace\w*)\b"
            r"|\bobservab\w*\b"
        ),
    ),
    (
        "MESSAGING",
        re.compile(
            r"\b(?:publish\w*|send\w*|emit\w*|produc\w*|consum\w*)\b.*"
            r"\b(?:event\w*|message\w*|queue\w*|topic\w*|stream\w*)\b"
            r"|\b(?:enqueue\w*|dequeue\w*)\b"
        ),
    ),
    ("RECOVERY", re.compile(r"\b(?:restore\w*|recover\w*|rollback\w*)\b")),
    ("TRUST", re.compile(r"\b(?:trust\w*|issuer\w*|token\w*)\b")),
    ("PROTECTION", re.compile(r"\b(?:protect\w*|secur\w*|encrypt\w*|isolat\w*)\b")),
    ("DEPLOYMENT", re.compile(r"\b(?:deploy\w*|provision\w*|release\w*)\b")),
    (
        "DELIVERY_DEFINITION",
        re.compile(r"\b(?:define\w*|describe\w*)\b.*\bchange\w*\b"),
    ),
    ("RUNTIME", re.compile(r"\b(?:run\w*|host\w*|execut\w*)\b")),
    ("IMPLEMENTATION", re.compile(r"\b(?:implement\w*|realiz\w*)\b")),
    (
        "DATA_ACCESS",
        re.compile(r"\b(?:store\w*|read\w*|writ\w*|persist\w*|quer\w*|fetch\w*)\b"),
    ),
    (
        "REQUEST_FLOW",
        re.compile(
            r"\b(?:invok\w*|rout\w*|submit\w*|forward\w*|call\w*)\b"
            r"|\ballow\w*\b.*\brequest\w*\b"
            r"|\bsend\w*\b.*\b(?:request\w*|review\w*|command\w*)\b"
            r"|\breturn\w*\b.*\b(?:review\w*|response\w*|result\w*)\b"
        ),
    ),
)


def diagram_relation_category(value: Any) -> str | None:
    """Return one controlled category, rejecting empty or ambiguous prose."""

    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).casefold()
    if not normalized:
        return None
    matches = {
        category
        for category, pattern in _RELATION_CATEGORY_PATTERNS
        if pattern.search(normalized) is not None
    }
    if "OBSERVABILITY" in matches:
        matches.discard("MESSAGING")
    return next(iter(matches)) if len(matches) == 1 else None
