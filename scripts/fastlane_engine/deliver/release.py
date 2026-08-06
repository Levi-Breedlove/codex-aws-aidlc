"""Pure Delivery release-decision parsing.

Canonical input is already-observed VERIFY Markdown. The result and ordered
issues are non-authoritative validation output. This module performs no I/O,
mutation, routing, approval, deployment, or external action.
"""

from __future__ import annotations

import re

from ..core.ids import clean_cell


def parse_release_decision_record(
    text: str | None,
) -> tuple[dict[str, str], tuple[tuple[str, str], ...]]:
    """CANONICALIZATION: return release state and exact ordered issues."""

    fallback = {"release_state": "NOT_READY", "active_evidence_cutoff": "NONE"}
    if text is None:
        return fallback, ()
    heading = "## Current release decision"
    matches = list(re.finditer(rf"^{re.escape(heading)}[ \t]*$", text, re.MULTILINE))
    if len(matches) != 1:
        return fallback, (("RELEASE_DECISION", f"Expected exactly one {heading!r}"),)
    section = text[matches[0].end() :]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    issues: list[tuple[str, str]] = []
    decisions = re.findall(r"^- Release state:\s*`([^`]+)`\s*$", section, re.MULTILINE)
    release_state = decisions[0] if len(decisions) == 1 else "NOT_READY"
    if len(decisions) != 1 or decisions[0] not in {
        "NOT_READY",
        "READY_TO_DEPLOY",
        "RELEASE_VERIFIED",
    }:
        issues.append(
            (
                "RELEASE_DECISION",
                "Release decision must be exactly NOT_READY, READY_TO_DEPLOY, or RELEASE_VERIFIED",
            )
        )
        release_state = "NOT_READY"
    cutoff_rows = re.findall(
        r"^- Active evidence cutoff:\s*(?P<value>[^\r\n]+?)\s*$",
        section,
        re.MULTILINE,
    )
    cutoff = clean_cell(cutoff_rows[0]) if len(cutoff_rows) == 1 else "NONE"
    if len(cutoff_rows) != 1 or (
        cutoff not in {"TODO", "NONE"} and re.fullmatch(r"EV-\d{4,}", cutoff) is None
    ):
        issues.append(
            (
                "RELEASE_EVIDENCE_CUTOFF",
                "Active evidence cutoff must appear exactly once and be TODO, NONE, "
                "or one canonical EV-* ID",
            )
        )
        cutoff = "NONE"
    return {
        "release_state": release_state,
        "active_evidence_cutoff": cutoff,
    }, tuple(issues)


__all__ = ("parse_release_decision_record",)
