"""One immutable structural index for a canonical Markdown document.

Inputs are already-observed normalized text. Outputs preserve character, line,
heading, table, record-ID, and Mermaid spans plus section digests. The module is
pure: it does not interpret domain meaning, derive readiness, or grant authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import split_markdown_table_row, without_fenced_code
from .digests import lf_normalized_bytes, sha256_prefixed


@dataclass(frozen=True)
class MarkdownSpan:
    start: int
    end: int
    start_line: int
    end_line: int


@dataclass(frozen=True)
class HeadingSpan:
    level: int
    title: str
    raw: str
    span: MarkdownSpan
    section: MarkdownSpan
    section_sha256: str


@dataclass(frozen=True)
class TableSpan:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    span: MarkdownSpan


@dataclass(frozen=True)
class MermaidSpan:
    text: str
    span: MarkdownSpan
    rendered_sha256: str


@dataclass(frozen=True)
class MarkdownDocumentIndex:
    text: str
    structural_text: str
    headings: tuple[HeadingSpan, ...]
    tables: tuple[TableSpan, ...]
    record_ids: tuple[tuple[str, MarkdownSpan], ...]
    mermaid: tuple[MermaidSpan, ...]

    @classmethod
    def build(cls, text: str) -> "MarkdownDocumentIndex":
        """Index one document with one canonical fenced-code mask."""

        structural = without_fenced_code(text)
        line_starts = _line_starts(text)
        headings = _headings(text, structural, line_starts)
        tables = _tables(text, structural, line_starts)
        record_ids = tuple(
            (match.group(0), _span(match.start(), match.end(), line_starts))
            for match in re.finditer(r"\b[A-Z][A-Z0-9_]*-\d{2,}\b", structural)
        )
        mermaid = _mermaid(text, line_starts)
        return cls(text, structural, headings, tables, record_ids, mermaid)

    def headings_named(self, title: str) -> tuple[HeadingSpan, ...]:
        return tuple(heading for heading in self.headings if heading.title == title)

    def unique_heading(self, title: str) -> HeadingSpan:
        matches = self.headings_named(title)
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one heading title {title!r}; found {len(matches)}"
            )
        return matches[0]


def _line_starts(text: str) -> tuple[int, ...]:
    return (0,) + tuple(match.end() for match in re.finditer("\n", text))


def _line_number(offset: int, starts: tuple[int, ...]) -> int:
    import bisect

    return bisect.bisect_right(starts, offset)


def _span(start: int, end: int, starts: tuple[int, ...]) -> MarkdownSpan:
    end_probe = max(start, end - 1)
    return MarkdownSpan(
        start, end, _line_number(start, starts), _line_number(end_probe, starts)
    )


def _headings(
    text: str, structural: str, starts: tuple[int, ...]
) -> tuple[HeadingSpan, ...]:
    matches = list(
        re.finditer(
            r"^(?P<marks>#{1,6})[ \t]+(?P<title>.+?)[ \t]*\r?$",
            structural,
            re.MULTILINE,
        )
    )
    result: list[HeadingSpan] = []
    for index, match in enumerate(matches):
        level = len(match.group("marks"))
        end = len(text)
        for following in matches[index + 1 :]:
            if len(following.group("marks")) <= level:
                end = following.start()
                break
        section_text = text[match.start() : end]
        result.append(
            HeadingSpan(
                level=level,
                title=match.group("title").strip(),
                raw=text[match.start() : match.end()].rstrip("\r"),
                span=_span(match.start(), match.end(), starts),
                section=_span(match.start(), end, starts),
                section_sha256=sha256_prefixed(
                    lf_normalized_bytes(section_text, trailing_lf=True)
                ),
            )
        )
    return tuple(result)


def _tables(
    text: str, structural: str, starts: tuple[int, ...]
) -> tuple[TableSpan, ...]:
    raw_lines = text.splitlines(keepends=True)
    structural_lines = structural.splitlines(keepends=True)
    result: list[TableSpan] = []
    offset = 0
    index = 0
    while index < len(raw_lines):
        line_start = offset
        if not structural_lines[index].strip().startswith("|"):
            offset += len(raw_lines[index])
            index += 1
            continue
        rows: list[list[str]] = []
        while index < len(raw_lines) and structural_lines[index].strip().startswith(
            "|"
        ):
            parsed = split_markdown_table_row(raw_lines[index].rstrip("\r\n"))
            if parsed is None:
                offset += len(raw_lines[index])
                index += 1
                break
            rows.append(parsed)
            offset += len(raw_lines[index])
            index += 1
        if len(rows) >= 2:
            body = (
                rows[2:]
                if all(re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1])
                else rows[1:]
            )
            result.append(
                TableSpan(
                    headers=tuple(rows[0]),
                    rows=tuple(tuple(row) for row in body),
                    span=_span(line_start, offset, starts),
                )
            )
    return tuple(result)


def _mermaid(text: str, starts: tuple[int, ...]) -> tuple[MermaidSpan, ...]:
    result: list[MermaidSpan] = []
    for match in re.finditer(
        r"^[ \t]*```mermaid[ \t]*\r?\n(?P<body>.*?^[ \t]*```[ \t]*\r?$)",
        text,
        re.MULTILINE | re.DOTALL,
    ):
        complete = text[match.start() : match.end()]
        result.append(
            MermaidSpan(
                complete,
                _span(match.start(), match.end(), starts),
                sha256_prefixed(lf_normalized_bytes(complete, trailing_lf=True)),
            )
        )
    return tuple(result)
