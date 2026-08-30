"""Pure shared grammar and additive semantic projections for Mermaid diagrams."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .relationship_semantics import diagram_relation_category


DIAGRAM_MEMBERSHIP_SUBGRAPH = re.compile(
    r"^\s*subgraph\s+(?P<id>[A-Z][A-Z0-9_]*)(?:\[[^\]\r\n]*\])?\s*$", re.I
)
DIAGRAM_MEMBERSHIP_NODE = re.compile(r"^\s*(?P<id>[A-Z][A-Z0-9_]*-\d{3,})\s*(?:\[|\()")


def semantic_subgraph_memberships(
    lines: Iterable[str], referenced_ids: Iterable[str]
) -> list[list[str]]:
    """Bind modern containment without labels, layout order, or group IDs."""

    included = set(referenced_ids)
    stack: list[str] = []
    descendants: dict[str, set[str]] = {}
    for line in lines:
        if (subgraph := DIAGRAM_MEMBERSHIP_SUBGRAPH.fullmatch(line)) is not None:
            identifier = subgraph.group("id").upper()
            descendants.setdefault(identifier, set())
            stack.append(identifier)
        elif line.strip().casefold() == "end":
            if stack:
                stack.pop()
        elif (node := DIAGRAM_MEMBERSHIP_NODE.match(line)) is not None:
            if node.group("id") not in included:
                continue
            for identifier in stack:
                descendants[identifier].add(node.group("id"))
    return [
        list(members)
        for members in sorted(
            {
                tuple(sorted(identifiers))
                for identifiers in descendants.values()
                if identifiers
            }
        )
    ]


def controlled_relationship_category_issues(
    diagram_id: str,
    kind: str,
    relationships: Iterable[tuple[str, str, str]],
    *,
    required: bool,
) -> list[str]:
    if not required or kind not in {"SYSTEM_CONTEXT", "AWS_IMPLEMENTATION"}:
        return []
    uncontrolled = sorted(
        {
            relation
            for _source, relation, _target in relationships
            if diagram_relation_category(relation) is None
        }
    )
    if not uncontrolled:
        return []
    return [
        f"{diagram_id}: board relationship labels require one controlled "
        "semantic category: " + ", ".join(uncontrolled)
    ]


def diagram_record_semantics(
    relationships: Iterable[tuple[str, str, str, str]],
    body: str,
    referenced_ids: Iterable[str],
    *,
    modern_contract: bool,
) -> tuple[tuple[tuple[str, str, str, str], ...], tuple[tuple[str, ...], ...]]:
    if not modern_contract:
        return (), ()
    semantic_relationships = tuple(sorted(relationships))
    containment = tuple(
        tuple(group)
        for group in semantic_subgraph_memberships(body.splitlines(), referenced_ids)
    )
    return semantic_relationships, containment
