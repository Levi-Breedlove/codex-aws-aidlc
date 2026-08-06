"""Project diagram applicability, semantic binding, and rendering validation.

Canonical inputs are caller-observed project records. Outputs are immutable
Design projections or ordered validation issues. This module performs no I/O,
routing, mutation, approval, authorization, or owner-facing rendering.
"""

from __future__ import annotations


import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any

from ..core.contracts import (
    _heading_section_offsets,
    contract_table_after_heading,
    table_after_heading,
    without_fenced_code,
)
from ..core.ids import STABLE_CONTRACT_ID, clean_cell, parse_exact_id_list, unresolved
from .models import ArchitectureContract, DiagramContract, DiagramRecord


DIAGRAM_CONTRACT_HEADING = "### Project diagram contract"


DIAGRAM_CONTRACT_HEADERS = (
    "Diagram ID",
    "Kind",
    "Applicability",
    "Status",
    "Anchor",
    "Basis IDs",
    "Referenced IDs",
)


DIAGRAM_ID = re.compile(r"DIAGRAM-\d{4,}")


DIAGRAM_KINDS = {
    "SYSTEM_CONTEXT",
    "PRIMARY_OUTCOME",
    "DATA_LIFECYCLE",
    "FAILURE_RECOVERY",
    "MIGRATION",
    "JOURNEY",
    "STATE",
}


DIAGRAM_APPLICABILITY = {"REQUIRED", "CONDITIONAL", "NOT_APPLICABLE"}


DIAGRAM_STATUSES = {"NOT_YET_CREATED", "CURRENT", "STALE", "NOT_APPLICABLE"}


DIAGRAM_REQUIRED_KINDS = {"SYSTEM_CONTEXT", "PRIMARY_OUTCOME"}


DIAGRAM_RELATIONSHIP = re.compile(
    r"^\s*(?P<from>[A-Z][A-Z0-9_]*-\d{3,})\s*"
    r"-->\|(?P<relation>[^|\r\n]+)\|\s*"
    r"(?P<to>[A-Z][A-Z0-9_]*-\d{3,})\s*$"
)


def required_diagram_kinds(
    text: str,
    requirement_ids: Iterable[str],
    work_kind: str | None,
) -> set[str]:
    """Return diagram kinds required by the current canonical project records."""

    required = set(DIAGRAM_REQUIRED_KINDS)
    identifiers = set(requirement_ids)
    if any(identifier.startswith("DATA-") for identifier in identifiers):
        required.add("DATA_LIFECYCLE")
    if any(identifier.startswith("REL-") for identifier in identifiers):
        required.add("FAILURE_RECOVERY")
    try:
        document = table_after_heading(text, "## Document status")
    except ValueError:
        document = {}
    if (
        work_kind == "MIGRATION"
        or clean_cell(document.get("Project mode", "")).lower() == "brownfield"
    ):
        required.add("MIGRATION")
    return required


def _diagram_heading_for_anchor(text: str, anchor: str) -> str:
    """Resolve one stable Markdown anchor through the shared fenced-code rules."""

    structural = without_fenced_code(text)
    matches: list[str] = []
    for match in re.finditer(
        r"^(#{1,6})[ \t]+(.+?)[ \t]*\r?$", structural, re.MULTILINE
    ):
        title = re.sub(r"^\d+(?:\.\d+)*\.?[ \t]+", "", match.group(2)).strip()
        candidate = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        if candidate == anchor:
            matches.append(match.group(0).rstrip("\r"))
    if len(matches) != 1:
        raise ValueError(
            f"diagram anchor {anchor!r} must resolve to exactly one heading; found {len(matches)}"
        )
    return matches[0]


def _canonical_mermaid_block(text: str, anchor: str) -> tuple[bytes, str]:
    heading = _diagram_heading_for_anchor(text, anchor)
    offsets = _heading_section_offsets(text, heading)
    if offsets is None:
        raise ValueError(f"diagram anchor {anchor!r} has no source section")
    _, body_start, end = offsets
    section = text[body_start:end]
    matches = list(
        re.finditer(r"(?ms)^```mermaid[ \t]*\r?\n.*?^```[ \t]*\r?$", section)
    )
    if len(matches) != 1:
        raise ValueError(
            f"diagram anchor {anchor!r} requires exactly one Mermaid block; found {len(matches)}"
        )
    block = matches[0].group(0).replace("\r\n", "\n").replace("\r", "\n")
    canonical = block.rstrip("\n") + "\n"
    return canonical.encode("utf-8"), canonical


def derive_diagram_contract(
    text: str,
    architecture: ArchitectureContract,
    requirements: Any,
    coverage: Any,
    *,
    required: bool,
    grandfathered_schema5: bool,
) -> tuple[DiagramContract, list[str]]:
    """SAFETY: Validate Mermaid views without making them design authority."""

    if grandfathered_schema5:
        return (
            DiagramContract(status="CURRENT", grandfathered_schema5=True),
            [],
        )
    issues: list[str] = []
    try:
        table = contract_table_after_heading(
            text, DIAGRAM_CONTRACT_HEADING, DIAGRAM_CONTRACT_HEADERS
        )
    except ValueError as exc:
        table = None
        issues.append(str(exc))
    if table is None:
        if not required:
            return DiagramContract(status="TEMPLATE"), []
        return DiagramContract(status="INVALID"), [
            f"Missing {DIAGRAM_CONTRACT_HEADING}"
        ]
    if not required and (
        any(unresolved(cell) for row in table.rows for cell in row)
        or all(row[3] in {"NOT_YET_CREATED", "NOT_APPLICABLE"} for row in table.rows)
    ):
        return DiagramContract(status="TEMPLATE"), []

    architecture_id = (
        architecture.selection.architecture_id
        if architecture.selection is not None
        else None
    )
    expected_required = required_diagram_kinds(
        text,
        requirements.requirement_ids,
        coverage.work_kind,
    )

    records: list[DiagramRecord] = []
    seen_ids: set[str] = set()
    seen_kinds: set[str] = set()
    semantic_rows: list[tuple[str, str]] = []
    stale = False
    incomplete = False
    for raw in table.rows:
        (
            diagram_id,
            kind,
            applicability,
            status,
            anchor,
            basis_value,
            referenced_value,
        ) = raw
        if DIAGRAM_ID.fullmatch(diagram_id) is None or diagram_id in seen_ids:
            issues.append(f"Invalid or duplicate diagram ID {diagram_id!r}")
        seen_ids.add(diagram_id)
        if kind not in DIAGRAM_KINDS or kind in seen_kinds:
            issues.append(f"Invalid or duplicate diagram kind {kind!r}")
        seen_kinds.add(kind)
        if applicability not in DIAGRAM_APPLICABILITY:
            issues.append(f"{diagram_id}: invalid applicability {applicability!r}")
        if status not in DIAGRAM_STATUSES:
            issues.append(f"{diagram_id}: invalid status {status!r}")
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", anchor) is None:
            issues.append(f"{diagram_id}: invalid stable anchor {anchor!r}")
        try:
            basis_ids = parse_exact_id_list(
                basis_value, STABLE_CONTRACT_ID, f"{diagram_id} Basis IDs"
            )
        except ValueError as exc:
            issues.append(str(exc))
            basis_ids = []
        try:
            referenced_ids = parse_exact_id_list(
                referenced_value, STABLE_CONTRACT_ID, f"{diagram_id} Referenced IDs"
            )
        except ValueError as exc:
            issues.append(str(exc))
            referenced_ids = []
        must_be_current = kind in expected_required or status == "CURRENT"
        if kind in expected_required and applicability == "NOT_APPLICABLE":
            issues.append(
                f"{diagram_id}: {kind} is required by current canonical records"
            )
        if kind in expected_required and status != "CURRENT":
            incomplete = True
            issues.append(f"{diagram_id}: required {kind} diagram is not CURRENT")
        if status == "STALE":
            stale = True
            issues.append(f"{diagram_id}: rendered project diagram is STALE")

        relationships: tuple[tuple[str, str, str], ...] = ()
        semantic_sha256: str | None = None
        rendered_sha256: str | None = None
        if must_be_current and status == "CURRENT":
            if architecture_id is None or architecture_id not in basis_ids:
                issues.append(
                    f"{diagram_id}: CURRENT diagram must cite the selected ARCH-* basis"
                )
            if not referenced_ids:
                issues.append(f"{diagram_id}: CURRENT diagram requires referenced IDs")
            try:
                rendered_bytes, rendered_text = _canonical_mermaid_block(text, anchor)
                rendered_sha256 = "sha256:" + hashlib.sha256(rendered_bytes).hexdigest()
                body = rendered_text.split("\n", 1)[1].rsplit("\n```", 1)[0]
                if re.search(r"\b(?:TODO|PLACEHOLDER|GENERIC)\b", body, re.IGNORECASE):
                    issues.append(
                        f"{diagram_id}: Mermaid block contains generic placeholder content"
                    )
                parsed_relationships = sorted(
                    {
                        (
                            match.group("from"),
                            clean_cell(match.group("relation")),
                            match.group("to"),
                        )
                        for line in body.splitlines()
                        if (match := DIAGRAM_RELATIONSHIP.fullmatch(line)) is not None
                    }
                )
                relationships = tuple(parsed_relationships)
                if not relationships:
                    issues.append(
                        f"{diagram_id}: Mermaid block has no canonical relationships"
                    )
                endpoint_ids = {
                    identifier
                    for source, _relation, target in relationships
                    for identifier in (source, target)
                }
                if endpoint_ids != set(referenced_ids):
                    issues.append(
                        f"{diagram_id}: Referenced IDs must exactly match Mermaid relationship endpoints"
                    )
                for identifier in referenced_ids:
                    if (
                        re.search(
                            rf"(?<![A-Z0-9-]){re.escape(identifier)}(?![A-Z0-9-])",
                            body,
                        )
                        is None
                    ):
                        issues.append(
                            f"{diagram_id}: referenced ID {identifier} is absent from Mermaid"
                        )
                semantic_payload = {
                    "kind": kind,
                    "basis_ids": sorted(basis_ids),
                    "referenced_ids": sorted(referenced_ids),
                    "relationships": [
                        {"from_id": source, "relation": relation, "to_id": target}
                        for source, relation, target in relationships
                    ],
                }
                semantic_bytes = (
                    json.dumps(
                        semantic_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    + b"\n"
                )
                semantic_sha256 = "sha256:" + hashlib.sha256(semantic_bytes).hexdigest()
                semantic_rows.append((diagram_id, semantic_sha256))
            except ValueError as exc:
                issues.append(f"{diagram_id}: {exc}")
        records.append(
            DiagramRecord(
                diagram_id=diagram_id,
                kind=kind,
                applicability=applicability,
                status=status,
                anchor=anchor,
                basis_ids=tuple(basis_ids),
                referenced_ids=tuple(referenced_ids),
                relationships=relationships,
                semantic_sha256=semantic_sha256,
                rendered_sha256=rendered_sha256,
            )
        )

    missing_kinds = sorted(expected_required - seen_kinds)
    if missing_kinds:
        incomplete = True
        issues.append("Missing required diagram kinds: " + ", ".join(missing_kinds))
    canonical_bytes: bytes | None = None
    canonical_sha256: str | None = None
    if not issues or all(
        issue.endswith("rendered project diagram is STALE") for issue in issues
    ):
        canonical_bytes = (
            json.dumps(
                semantic_rows,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        canonical_sha256 = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
    status_value = (
        "STALE"
        if stale
        else "INVALID"
        if issues and not incomplete
        else "INCOMPLETE"
        if issues
        else "CURRENT"
    )
    return (
        DiagramContract(
            status=status_value,
            architecture_basis_id=architecture_id,
            records=tuple(records),
            canonical_sha256=canonical_sha256,
            canonical_bytes=canonical_bytes,
        ),
        issues,
    )
