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

from .ids import clean_cell


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


@dataclass(frozen=True)
class ContractTable:
    """One exact canonical Markdown table and its normalized cell values."""

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    canonical_bytes: bytes


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


def split_table_row(line: str) -> list[str]:
    """Preserve the legacy simple-table splitter used by lifecycle contracts."""

    return [part.strip() for part in line.strip().strip("|").split("|")]


def markdown_tables(text: str) -> list[list[list[str]]]:
    """Return simple Markdown tables without evaluating project meaning."""

    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    structural = without_fenced_code(text)
    for raw_line, structural_line in zip(text.splitlines(), structural.splitlines()):
        if structural_line.strip().startswith("|"):
            current.append([clean_cell(cell) for cell in split_table_row(raw_line)])
        elif current:
            if len(current) >= 3:
                tables.append(current)
            current = []
    if len(current) >= 3:
        tables.append(current)
    return tables


def _canonical_contract_table(raw_lines: list[str]) -> bytes:
    return ("\n".join(line.rstrip() for line in raw_lines) + "\n").encode("utf-8")


def _parse_contract_table_lines(
    raw_lines: list[str], expected_headers: tuple[str, ...]
) -> ContractTable:
    if len(raw_lines) < 2:
        raise ValueError("Markdown contract table requires a header and separator")
    parsed: list[tuple[str, ...]] = []
    for raw_line in raw_lines:
        cells = split_markdown_table_row(raw_line)
        if cells is None:
            raise ValueError("Malformed Markdown contract table row")
        parsed.append(tuple(clean_cell(cell) for cell in cells))
    if parsed[0] != expected_headers:
        raise ValueError(
            "Contract table headers must be exactly: " + " | ".join(expected_headers)
        )
    if len(parsed[1]) != len(expected_headers) or any(
        re.fullmatch(r":?-{3,}:?", cell) is None for cell in parsed[1]
    ):
        raise ValueError("Contract table separator is malformed")
    for row in parsed[2:]:
        if len(row) != len(expected_headers):
            raise ValueError(
                f"Contract table row has {len(row)} cells; expected {len(expected_headers)}"
            )
    return ContractTable(
        headers=expected_headers,
        rows=tuple(parsed[2:]),
        canonical_bytes=_canonical_contract_table(raw_lines),
    )


def _heading_section_offsets(text: str, heading: str) -> tuple[int, int, int] | None:
    structural = without_fenced_code(text)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*\r?$", structural, re.MULTILINE)
    )
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one heading {heading!r}; found {len(matches)}"
        )
    level = len(heading) - len(heading.lstrip("#"))
    following = re.search(
        rf"^#{{1,{level}}}[ \t]+", structural[matches[0].end() :], re.MULTILINE
    )
    end = matches[0].end() + following.start() if following else len(text)
    return matches[0].start(), matches[0].end(), end


def _heading_section_lines(
    text: str, heading: str
) -> tuple[list[str], list[str]] | None:
    offsets = _heading_section_offsets(text, heading)
    if offsets is None:
        return None
    _, body_start, end = offsets
    structural = without_fenced_code(text)
    return text[body_start:end].splitlines(), structural[body_start:end].splitlines()


def contract_table_after_heading(
    text: str, heading: str, expected_headers: tuple[str, ...]
) -> ContractTable | None:
    """Return the first exact table in one uniquely identified heading section."""

    section = _heading_section_lines(text, heading)
    if section is None:
        return None
    lines, structural_lines = section
    start = next(
        (
            index
            for index, structural_line in enumerate(structural_lines)
            if structural_line.strip().startswith("|")
        ),
        None,
    )
    if start is None:
        raise ValueError(f"No Markdown table after {heading!r}")
    raw_lines: list[str] = []
    for line, structural_line in zip(lines[start:], structural_lines[start:]):
        if not structural_line.strip().startswith("|"):
            break
        raw_lines.append(line)
    return _parse_contract_table_lines(raw_lines, expected_headers)


def contract_table_in_section(
    text: str, heading: str, expected_headers: tuple[str, ...]
) -> ContractTable | None:
    """Return the unique table matching headers anywhere in one section."""

    section = _heading_section_lines(text, heading)
    if section is None:
        return None
    lines, structural_lines = section
    matches: list[ContractTable] = []
    index = 0
    while index < len(lines):
        if not structural_lines[index].strip().startswith("|"):
            index += 1
            continue
        raw_lines: list[str] = []
        while index < len(lines) and structural_lines[index].strip().startswith("|"):
            raw_lines.append(lines[index])
            index += 1
        header = split_markdown_table_row(raw_lines[0])
        if (
            header is None
            or tuple(clean_cell(cell) for cell in header) != expected_headers
        ):
            continue
        matches.append(_parse_contract_table_lines(raw_lines, expected_headers))
    if len(matches) > 1:
        raise ValueError(
            f"Expected one table with headers {' | '.join(expected_headers)} after {heading!r}"
        )
    return matches[0] if matches else None


def table_after_heading(text: str, heading: str) -> dict[str, str]:
    """Parse the legacy two-column key/value table after one exact heading."""

    structural = without_fenced_code(text)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*$", structural, re.MULTILINE)
    )
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one heading {heading!r}; found {len(matches)}"
        )
    lines = text[matches[0].end() :].splitlines()
    structural_lines = structural[matches[0].end() :].splitlines()
    start = next(
        (
            index
            for index, line in enumerate(structural_lines)
            if line.strip().startswith("|")
        ),
        None,
    )
    if start is None:
        raise ValueError(f"No Markdown table after {heading!r}")
    table_lines: list[str] = []
    for line, structural_line in zip(lines[start:], structural_lines[start:]):
        if not structural_line.strip().startswith("|"):
            break
        table_lines.append(line)
    if len(table_lines) < 3:
        raise ValueError(f"Malformed Markdown table after {heading!r}")
    result: dict[str, str] = {}
    for line in table_lines[2:]:
        cells = split_table_row(line)
        if len(cells) < 2:
            continue
        key = clean_cell(cells[0])
        if key in result:
            raise ValueError(f"Duplicate field {key!r} after {heading!r}")
        result[key] = clean_cell(cells[1])
    return result


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
    "ContractTable",
    "SEPARATOR_CELL",
    "TASK_COMPLETION_EVIDENCE_HEADERS",
    "contract_table_after_heading",
    "contract_table_in_section",
    "external_targets_overlap",
    "markdown_tables",
    "parse_checkpoint_cells",
    "parse_checkpoint_git_receipt_value",
    "parse_exact_section_table",
    "parse_task_completion_evidence_cells",
    "path_boundaries_overlap",
    "path_boundary_base",
    "path_boundary_contains",
    "split_markdown_table_row",
    "split_table_row",
    "table_after_heading",
    "without_fenced_code",
)
