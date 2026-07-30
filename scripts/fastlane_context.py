"""Deterministic, read-only resolution of ephemeral Fastlane source context."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence


BUDGET_STATUSES = {
    "WITHIN_LIMIT",
    "OVERSIZED_REQUIRED_RECORD",
    "SOURCE_INVALID",
}
SELECTOR_KINDS = {"HEADING", "RECORD_ID", "TASK_ID", "WHOLE_FILE"}


@dataclass(frozen=True)
class SliceRequest:
    path: str
    selector_kind: str
    selector: str
    priority: int
    reason: str
    required: bool = False
    active_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceSpan:
    start: int
    end: int


SelectorResolver = Callable[[SliceRequest, str], SourceSpan]


def canonical_source_bytes(value: str) -> bytes:
    """Return LF-normalized UTF-8 bytes ending in exactly one LF."""

    normalized = value.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    return (normalized + "\n").encode("utf-8")


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _resolved(
    request: SliceRequest,
    text: str,
    span: SourceSpan,
) -> dict[str, object]:
    if span.start < 0 or span.end <= span.start or span.end > len(text):
        raise ValueError("selector returned an invalid source range")
    selected = text[span.start : span.end]
    canonical = canonical_source_bytes(selected)
    present_ids = [item for item in request.active_ids if item in selected]
    return {
        "path": request.path,
        "selector_kind": request.selector_kind,
        "selector": request.selector,
        "start_line": _line_number(text, span.start),
        "end_line": _line_number(text, span.end - 1),
        "active_ids": sorted(set(present_ids)),
        "canonical_sha256": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "source_bytes": len(canonical),
        "reason": request.reason,
        "_priority": request.priority,
        "_required": request.required,
        "_start": span.start,
        "_end": span.end,
    }


def _public(item: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in item.items() if not key.startswith("_")}


def _sort_key(item: Mapping[str, object]) -> tuple[object, ...]:
    return (
        not bool(item["_required"]),
        int(item["_priority"]),
        str(item["path"]),
        int(item["start_line"]),
        str(item["selector_kind"]),
        str(item["selector"]),
    )


def _overlap_issues(items: Sequence[Mapping[str, object]]) -> list[str]:
    issues: list[str] = []
    ordered = sorted(
        items,
        key=lambda item: (str(item["path"]), int(item["_start"]), int(item["_end"])),
    )
    for previous, current in zip(ordered, ordered[1:]):
        if previous["path"] != current["path"]:
            continue
        if int(current["_start"]) < int(previous["_end"]):
            previous_key = (
                previous["path"],
                previous["_start"],
                previous["_end"],
            )
            current_key = (current["path"], current["_start"], current["_end"])
            if previous_key != current_key:
                issues.append(
                    f"overlapping context selectors for {current['path']}: "
                    f"{previous['selector']} and {current['selector']}"
                )
    return issues


def resolve_context_packet(
    initial_requests: Sequence[SliceRequest],
    on_demand_requests: Sequence[SliceRequest],
    source_texts: Mapping[str, str],
    resolver: SelectorResolver,
    *,
    maximum_initial_source_bytes: int,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    """Resolve selectors, measure canonical bytes, and enforce one source budget."""

    issues: list[dict[str, str]] = []

    def resolve_many(requests: Sequence[SliceRequest]) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        seen: set[tuple[str, int, int]] = set()
        for request in requests:
            if request.selector_kind not in SELECTOR_KINDS:
                issues.append({"path": request.path, "reason": "unknown selector kind"})
                continue
            text = source_texts.get(request.path)
            if text is None:
                issues.append(
                    {"path": request.path, "reason": "required source is unavailable"}
                )
                continue
            try:
                item = _resolved(request, text, resolver(request, text))
            except ValueError as exc:
                issues.append({"path": request.path, "reason": str(exc)})
                continue
            key = (request.path, int(item["_start"]), int(item["_end"]))
            if key not in seen:
                seen.add(key)
                result.append(item)
        return sorted(result, key=_sort_key)

    initial_candidates = resolve_many(initial_requests)
    on_demand = resolve_many(on_demand_requests)
    initial_ranges = {
        (item["path"], item["_start"], item["_end"]) for item in initial_candidates
    }
    on_demand = [
        item
        for item in on_demand
        if (item["path"], item["_start"], item["_end"]) not in initial_ranges
    ]
    for reason in _overlap_issues([*initial_candidates, *on_demand]):
        issues.append({"path": "NONE", "reason": reason})

    selected: list[dict[str, object]] = []
    moved: list[dict[str, object]] = []
    overflow_records: list[dict[str, object]] = []
    actual = 0
    for item in initial_candidates:
        size = int(item["source_bytes"])
        if actual + size <= maximum_initial_source_bytes:
            selected.append(item)
            actual += size
        elif bool(item["_required"]) and not overflow_records:
            selected.append(item)
            actual += size
            overflow_records.append(
                {
                    "path": item["path"],
                    "selector_kind": item["selector_kind"],
                    "selector": item["selector"],
                    "source_bytes": size,
                    "reason": "Complete required record exceeds the remaining source-byte budget",
                }
            )
        elif bool(item["_required"]):
            issues.append(
                {
                    "path": str(item["path"]),
                    "reason": "more than one required record would exceed the source-byte budget",
                }
            )
            moved.append(item)
        else:
            moved.append(item)

    on_demand = sorted([*on_demand, *moved], key=_sort_key)
    budget_status = (
        "SOURCE_INVALID"
        if issues
        else "OVERSIZED_REQUIRED_RECORD"
        if overflow_records
        else "WITHIN_LIMIT"
    )
    return (
        {
            "maximum_initial_source_bytes": maximum_initial_source_bytes,
            "actual_initial_source_bytes": actual,
            "budget_status": budget_status,
            "resolved_initial_slices": [_public(item) for item in selected],
            "resolved_on_demand_slices": [_public(item) for item in on_demand],
            "overflow_records": overflow_records,
        },
        issues,
    )
