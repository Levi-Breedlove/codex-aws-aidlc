"""Pure eligibility and semantic cross-checks for architecture-board handoff."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .relationship_semantics import diagram_relation_category


_BOARD_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_BOARD_RECORDS = {
    "DIAGRAM-0001": ("SYSTEM_CONTEXT", "proposed-system-at-a-glance"),
    "DIAGRAM-0008": ("AWS_IMPLEMENTATION", "aws-implementation-at-a-glance"),
}
_EDGE_KEYS = {"from_id", "edge_kind", "relation", "to_id"}


def _semantic_edge(
    edge: object, referenced_ids: set[str]
) -> tuple[str, str, str] | None:
    if not isinstance(edge, Mapping) or set(edge) != _EDGE_KEYS:
        return None
    source = edge.get("from_id")
    relation = edge.get("relation")
    target = edge.get("to_id")
    values = (source, relation, target)
    if not all(isinstance(value, str) and value for value in values):
        return None
    if (
        edge.get("edge_kind") not in {"SOLID", "DASHED"}
        or source == target
        or source not in referenced_ids
        or target not in referenced_ids
    ):
        return None
    return source, relation, target


def _relationships_are_canonical(
    row: Mapping[str, Any], referenced_ids: set[str]
) -> bool:
    semantic = row.get("semantic_relationships")
    legacy = row.get("relationships")
    if not isinstance(semantic, list) or not semantic or not isinstance(legacy, list):
        return False
    semantic_rows: list[tuple[str, str, str]] = []
    for edge in semantic:
        projection = _semantic_edge(edge, referenced_ids)
        if projection is None:
            return False
        semantic_rows.append(projection)
    legacy_rows = {
        (edge.get("from_id"), edge.get("relation"), edge.get("to_id"))
        for edge in legacy
        if isinstance(edge, Mapping)
    }
    return bool(
        len(semantic_rows) == len(set(semantic_rows))
        and len(legacy_rows) == len(legacy)
        and set(semantic_rows) == legacy_rows
    )


def _containment_is_canonical(value: object, referenced_ids: set[str]) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for group in value:
        if (
            not isinstance(group, list)
            or not group
            or len(group) != len(set(group))
            or not all(
                isinstance(item, str) and item in referenced_ids for item in group
            )
        ):
            return False
    rows = [tuple(sorted(group)) for group in value]
    return len(rows) == len(set(rows))


def _architecture_board_record_semantics(row: Mapping[str, Any]) -> bool:
    referenced = row.get("referenced_ids")
    if not isinstance(referenced, list) or not referenced:
        return False
    referenced_ids = set(referenced)
    if len(referenced_ids) != len(referenced) or not all(
        isinstance(identifier, str) and identifier for identifier in referenced
    ):
        return False
    return _relationships_are_canonical(
        row, referenced_ids
    ) and _containment_is_canonical(row.get("containment"), referenced_ids)


def _architecture_board_record(
    diagrams: Mapping[str, Any], diagram_id: str
) -> dict[str, Any] | None:
    rows = [
        row
        for row in diagrams.get("records", [])
        if isinstance(row, Mapping) and row.get("diagram_id") == diagram_id
    ]
    if len(rows) != 1:
        return None
    row = rows[0]
    kind, anchor = _BOARD_RECORDS[diagram_id]
    valid = (
        row.get("kind") == kind
        and row.get("applicability") == "REQUIRED"
        and row.get("status") == "CURRENT"
        and row.get("anchor") == anchor
        and _architecture_board_record_semantics(row)
        and all(
            _BOARD_SHA256.fullmatch(str(row.get(key, "")))
            for key in ("semantic_sha256", "rendered_sha256")
        )
    )
    return dict(row) if valid else None


def _supported_design_schema(
    design: Mapping[str, Any], project: Mapping[str, Any]
) -> bool:
    schema_version = design.get("schema_version")
    if schema_version != project.get("schema_version") or schema_version not in {7, 8}:
        return False
    if schema_version == 7:
        return True
    design_v8 = project.get("design_v8")
    return bool(
        isinstance(design_v8, Mapping)
        and design_v8.get("schema_version") == 8
        and design_v8.get("status") == "READY"
    )


def _architecture_board_report_current(
    report: Mapping[str, Any], parts: tuple[Any, ...]
) -> bool:
    if not all(isinstance(item, Mapping) for item in parts):
        return False
    gates, design, project, diagrams, authority, auth, external = parts
    return bool(
        report.get("schema_version") == 2
        and report.get("ok") is True
        and gates.get("gate_a") == "APPROVED_FOR_DESIGN"
        and gates.get("gate_b") == "APPROVED_FOR_CONSTRUCTION"
        and _supported_design_schema(design, project)
        and design.get("status") == project.get("status") == "READY"
        and not any(project.get(f"grandfathered_v{version}") for version in (4, 5, 6))
        and diagrams.get("status") == "CURRENT"
        and diagrams.get("grandfathered_schema5") is False
        and authority.get("valid") is True
        and authority.get("active_task") == "NONE"
        and authority.get("authorization_id") == auth.get("construction")
        and auth.get("construction") != "NONE"
        and auth.get("aws") == "NONE"
        and external.get("kind") == external.get("validity") == "NONE"
    )


def _unique_directed_path(
    edges: list[Mapping[str, Any]], source: str, target: str
) -> list[Mapping[str, Any]] | None:
    adjacent: dict[str, list[Mapping[str, Any]]] = {}
    for edge in edges:
        adjacent.setdefault(str(edge["from_id"]), []).append(edge)
    for rows in adjacent.values():
        rows.sort(
            key=lambda item: (
                str(item["to_id"]),
                str(item["edge_kind"]),
                str(item["relation"]),
            )
        )

    def find_path(
        blocked: Mapping[str, Any] | None = None,
    ) -> list[Mapping[str, Any]] | None:
        pending = [source]
        visited = {source}
        predecessor: dict[str, tuple[str, Mapping[str, Any]]] = {}
        while pending:
            current = pending.pop()
            for edge in adjacent.get(current, []):
                if edge is blocked:
                    continue
                next_id = str(edge["to_id"])
                if next_id in visited:
                    continue
                visited.add(next_id)
                predecessor[next_id] = (current, edge)
                if next_id == target:
                    path: list[Mapping[str, Any]] = []
                    cursor = target
                    while cursor != source:
                        cursor, path_edge = predecessor[cursor]
                        path.append(path_edge)
                    return list(reversed(path))
                pending.append(next_id)
        return None

    path = find_path()
    if path is None or any(find_path(edge) is not None for edge in path):
        return None
    return path


def _containment_signature(
    record: Mapping[str, Any], common_ids: set[str]
) -> frozenset[frozenset[str]]:
    return frozenset(
        intersected
        for group in record["containment"]
        if (intersected := frozenset(group).intersection(common_ids))
        and intersected != common_ids
    )


def _semantic_relationships_match(
    primary: Mapping[str, Any], cross_check: Mapping[str, Any]
) -> bool:
    primary_edges = list(primary["semantic_relationships"])
    for cross_edge in cross_check["semantic_relationships"]:
        path = _unique_directed_path(
            primary_edges,
            str(cross_edge["from_id"]),
            str(cross_edge["to_id"]),
        )
        family = diagram_relation_category(cross_edge["relation"])
        if (
            path is None
            or family is None
            or any(edge["edge_kind"] != cross_edge["edge_kind"] for edge in path)
            or any(
                diagram_relation_category(edge["relation"]) != family for edge in path
            )
        ):
            return False
    return True


def _architecture_board_conflict(
    diagrams: Mapping[str, Any] | None,
    primary: Mapping[str, Any] | None,
    cross_check: Mapping[str, Any] | None,
) -> bool:
    if diagrams is None or primary is None or cross_check is None:
        return False
    basis = diagrams.get("architecture_basis_id")
    cross_ids = set(cross_check.get("referenced_ids", []))
    return bool(
        basis not in primary.get("basis_ids", [])
        or basis not in cross_check.get("basis_ids", [])
        or not cross_ids.issubset(primary.get("referenced_ids", []))
        or _containment_signature(primary, cross_ids)
        != _containment_signature(cross_check, cross_ids)
        or not _semantic_relationships_match(primary, cross_check)
    )
