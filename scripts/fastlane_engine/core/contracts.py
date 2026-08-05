"""Exact Markdown contract parsing shared by Engine domains.

Canonical inputs are normalized Markdown bytes from a ProjectSnapshot. Returned
rows retain exact order. This module performs no I/O and derives no readiness,
routing, mutation, or authority. The top-level ``fastlane_contracts`` module
remains a compatibility façade over this implementation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence


TASK_COMPLETION_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Task",
    "Command or observation",
    "Result",
    "Actor",
    "Observed at",
    "Commit / worktree / artifact",
    "Durable source",
    "Status",
)

CHECKPOINT_HEADERS = (
    "Checkpoint",
    "Run",
    "Time",
    "REQ / DES / AUTH",
    "Commit and protected dirty paths",
    "Task outcomes and attempts",
    "Evidence and external actions",
    "Blockers and next safe action",
)

SEPARATOR_CELL = re.compile(r":?-{3,}:?")
CHECKPOINT_GIT_RECEIPT = re.compile(
    r"\s*Commit\s*:\s*`?([0-9a-fA-F]{7,64})`?\s*;\s*"
    r"Dirty\s*:\s*(.+?)\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ContractParseError(ValueError):
    """Structured internal parse failure that adapters translate for callers."""

    reason: str

    def __str__(self) -> str:
        return self.reason


@lru_cache(maxsize=64)
def without_fenced_code(text: str) -> str:
    """Mask fenced examples while preserving every character offset and newline."""

    result: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        ending = line[len(content) :]
        match = re.match(r"^[ \t]*(`{3,}|~{3,})", content)
        if match:
            marker = match.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            result.append(" " * len(content) + ending)
        elif fence_character is None:
            result.append(line)
        else:
            result.append(" " * len(content) + ending)
    return "".join(result)


def split_markdown_table_row(line: str) -> list[str] | None:
    """Split a pipe table row while honoring escaped pipes and backslashes."""

    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells: list[str] = []
    current: list[str] = []
    content = stripped[1:-1]
    index = 0
    while index < len(content):
        character = content[index]
        if (
            character == "\\"
            and index + 1 < len(content)
            and content[index + 1] in {"\\", "|"}
        ):
            current.append(content[index + 1])
            index += 2
            continue
        if character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
        index += 1
    cells.append("".join(current).strip())
    return cells


def _section_lines(text: str, heading: str) -> tuple[list[str], list[str]]:
    structural = without_fenced_code(text)
    headings = list(
        re.finditer(rf"^## {re.escape(heading)}[ \t]*$", structural, re.MULTILINE)
    )
    if len(headings) != 1:
        raise ContractParseError("section_count")
    following = re.search(r"^##\s+", structural[headings[0].end() :], re.MULTILINE)
    end = headings[0].end() + following.start() if following else len(structural)
    raw_lines = text[headings[0].end() : end].splitlines()
    structural_lines = structural[headings[0].end() : end].splitlines()
    return raw_lines, structural_lines


def parse_exact_section_table(
    text: str,
    *,
    heading: str,
    headers: Sequence[str],
) -> list[tuple[str, ...]]:
    """Parse one exact, unfenced, contiguous table from an H2 section."""

    raw_lines, structural_lines = _section_lines(text, heading)
    header_indexes = [
        index
        for index, (raw_line, structural_line) in enumerate(
            zip(raw_lines, structural_lines)
        )
        if structural_line.strip().startswith("|")
        and split_markdown_table_row(raw_line) == list(headers)
    ]
    if len(header_indexes) != 1:
        raise ContractParseError("header_count")

    header_index = header_indexes[0]
    if header_index + 1 >= len(raw_lines):
        raise ContractParseError("separator_missing")
    separator = split_markdown_table_row(raw_lines[header_index + 1])
    if (
        separator is None
        or len(separator) != len(headers)
        or any(SEPARATOR_CELL.fullmatch(cell) is None for cell in separator)
    ):
        raise ContractParseError("separator_invalid")

    rows: list[tuple[str, ...]] = []
    table_ended = False
    for raw_line, structural_line in zip(
        raw_lines[header_index + 2 :], structural_lines[header_index + 2 :]
    ):
        cells = (
            split_markdown_table_row(raw_line)
            if structural_line.strip().startswith("|")
            else None
        )
        if cells is None:
            if rows:
                table_ended = True
            continue
        if len(cells) != len(headers):
            if not table_ended:
                raise ContractParseError("row_width")
            continue
        if table_ended:
            raise ContractParseError("discontiguous_rows")
        rows.append(tuple(cells))
    return rows


def parse_task_completion_evidence_cells(text: str) -> list[tuple[str, ...]]:
    return parse_exact_section_table(
        text,
        heading="Task completion evidence",
        headers=TASK_COMPLETION_EVIDENCE_HEADERS,
    )


def parse_checkpoint_cells(text: str) -> list[tuple[str, ...]]:
    return parse_exact_section_table(
        text,
        heading="Checkpoints and resume",
        headers=CHECKPOINT_HEADERS,
    )


def parse_checkpoint_git_receipt_value(value: str) -> tuple[str, str]:
    match = CHECKPOINT_GIT_RECEIPT.fullmatch(value)
    if match is None:
        raise ContractParseError("git_receipt")
    return match.group(1), match.group(2).replace("`", "").strip()


def path_boundary_base(value: str) -> tuple[str, bool]:
    normalized = value.casefold()
    return (
        (normalized[:-3], True) if normalized.endswith("/**") else (normalized, False)
    )


def path_boundary_contains(allowed: str, requested: str) -> bool:
    allowed_base, broad = path_boundary_base(allowed)
    requested_base, requested_broad = path_boundary_base(requested)
    if broad:
        return requested_base == allowed_base or requested_base.startswith(
            allowed_base + "/"
        )
    return allowed_base == requested_base and not requested_broad


def path_boundaries_overlap(first: str, second: str) -> bool:
    first_base, _first_broad = path_boundary_base(first)
    second_base, _second_broad = path_boundary_base(second)
    return (
        first_base == second_base
        or first_base.startswith(second_base + "/")
        or second_base.startswith(first_base + "/")
    )


def external_targets_overlap(first: str, second: str) -> bool:
    first_normalized = first.casefold().rstrip("/:#")
    second_normalized = second.casefold().rstrip("/:#")
    if first_normalized == second_normalized:
        return True
    return any(
        first_normalized.startswith(second_normalized + separator)
        or second_normalized.startswith(first_normalized + separator)
        for separator in ("/", ":", "#")
    )


__all__ = (
    "CHECKPOINT_GIT_RECEIPT",
    "CHECKPOINT_HEADERS",
    "ContractParseError",
    "SEPARATOR_CELL",
    "TASK_COMPLETION_EVIDENCE_HEADERS",
    "external_targets_overlap",
    "parse_checkpoint_cells",
    "parse_checkpoint_git_receipt_value",
    "parse_exact_section_table",
    "parse_task_completion_evidence_cells",
    "path_boundaries_overlap",
    "path_boundary_base",
    "path_boundary_contains",
    "split_markdown_table_row",
    "without_fenced_code",
)
