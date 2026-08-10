"""Project diagram applicability, semantic binding, and rendering validation.

Canonical inputs are caller-observed project records. Outputs are immutable
Design projections or ordered validation issues. This module performs no I/O,
routing, mutation, approval, authorization, or owner-facing rendering.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ..core.contracts import (
    _heading_section_offsets,
    contract_table_after_heading,
    table_after_heading,
    without_fenced_code,
)
from ..core.ids import STABLE_CONTRACT_ID, clean_cell, parse_exact_id_list, unresolved
from .models import (
    ArchitectureContract,
    DiagramContract,
    DiagramRecord,
    ProjectDesignContract,
    TechnologyDecision,
)
from .support import AwsImplementationDecision

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
    "AWS_IMPLEMENTATION",
}

LEGACY_DIAGRAM_KINDS = DIAGRAM_KINDS - {"AWS_IMPLEMENTATION"}

DIAGRAM_APPLICABILITY = {"REQUIRED", "CONDITIONAL", "NOT_APPLICABLE"}

DIAGRAM_STATUSES = {"NOT_YET_CREATED", "CURRENT", "STALE", "NOT_APPLICABLE"}

DIAGRAM_PRESENTATION_DIAGNOSTIC = "DIAGRAM_PRESENTATION_STALE"

DIAGRAM_OWNER_SECTIONS = {
    "SYSTEM_CONTEXT": "## 14. Architecture overview",
    "AWS_IMPLEMENTATION": "## 20. AWS implementation approach",
}

DIAGRAM_REQUIRED_KINDS = {
    "SYSTEM_CONTEXT",
    "PRIMARY_OUTCOME",
    "AWS_IMPLEMENTATION",
}

DIAGRAM_HEADING_TITLES = {
    "SYSTEM_CONTEXT": "Proposed system at a glance",
    "PRIMARY_OUTCOME": "Sequence — primary outcome",
    "DATA_LIFECYCLE": "Data lifecycle view",
    "FAILURE_RECOVERY": "Sequence — failure and recovery",
    "MIGRATION": "Migration view",
    "JOURNEY": "Journey view",
    "STATE": "State view",
    "AWS_IMPLEMENTATION": "AWS implementation at a glance",
}

LEGACY_DIAGRAM_REQUIRED_KINDS = {"SYSTEM_CONTEXT", "PRIMARY_OUTCOME"}

DIAGRAM_CONDITIONAL_KINDS = DIAGRAM_KINDS - DIAGRAM_REQUIRED_KINDS

DIAGRAM_NODE = re.compile(
    r"^\s*(?P<id>[A-Z][A-Z0-9_]*-\d{3,})\s*"
    r'(?:\["(?P<rect>[^"\r\n]+)"\]|'
    r'\[\("(?P<data>[^"\r\n]+)"\)\]|'
    r'\("(?P<round>[^"\r\n]+)"\))'
    r"(?:\s*:::(?P<style>[a-z][a-z0-9_-]*))?\s*$"
)

DIAGRAM_FLOWCHART = re.compile(
    r"^\s*flowchart\s+(?P<direction>TB|TD|LR|RL|BT)\s*$", re.I
)

DIAGRAM_ACC_TITLE = re.compile(r"^\s*accTitle:\s*(?P<value>.+?)\s*$", re.I)

DIAGRAM_ACC_DESCRIPTION = re.compile(r"^\s*accDescr:\s*(?P<value>.+?)\s*$", re.I)

DIAGRAM_SUBGRAPH = re.compile(
    r'^\s*subgraph\s+(?P<id>[A-Z][A-Z0-9_]*)\["(?P<label>[^"\r\n]+)"\]\s*$', re.I
)

DIAGRAM_MEMBERSHIP_SUBGRAPH = re.compile(
    r"^\s*subgraph\s+(?P<id>[A-Z][A-Z0-9_]*)(?:\[[^\]\r\n]*\])?\s*$", re.I
)

DIAGRAM_MEMBERSHIP_NODE = re.compile(r"^\s*(?P<id>[A-Z][A-Z0-9_]*-\d{3,})\s*(?:\[|\()")

DIAGRAM_CLASS_DEF = re.compile(
    r"^\s*classDef\s+(?P<name>[a-z][a-z0-9_-]*)\s+(?P<body>.+?);?\s*$", re.I
)

DIAGRAM_DIRECTION = re.compile(r"^\s*direction\s+(?:TB|TD|LR|RL|BT)\s*$", re.I)

GENERIC_DIAGRAM_LABELS = {
    "actor",
    "approved data lifecycle",
    "approved interface",
    "boundary",
    "component",
    "data",
    "managed application",
    "project next state",
    "service",
    "state",
    "system",
    "user",
}

DIAGRAM_ROLE_COLORS = {
    "actor": ("#ffffff", "#232f3e"),
    "entry": ("#eaf3ff", "#147eba"),
    "compute": ("#fff1e8", "#d86613"),
    "data": ("#edf7ed", "#248814"),
    "event": ("#f3ecff", "#8c4fff"),
    "ops": ("#fff7df", "#d38b00"),
}

AWS_CONCERN_STYLES = {
    "Compute": "compute",
    "API and edge": "entry",
    "Identity": "entry",
    "Data": "data",
    "Messaging": "event",
    "Observability": "ops",
    "Deployment": "ops",
    "Secrets and encryption": "event",
}

DIAGRAM_RELATIONSHIP = re.compile(
    r"^\s*(?P<from>[A-Z][A-Z0-9_]*-\d{3,})\s*"
    r"(?:-->\|(?P<solid>[^|\r\n]+)\||"
    r"-\.\s*\"(?P<dotted>[^\"\r\n]+)\"\s*\.->)\s*"
    r"(?P<to>[A-Z][A-Z0-9_]*-\d{3,})\s*$"
)

LEGACY_DIAGRAM_RELATIONSHIP = re.compile(
    r"^\s*(?P<from>[A-Z][A-Z0-9_]*-\d{3,})\s*"
    r"-->\|(?P<solid>[^|\r\n]+)\|\s*(?P<to>[A-Z][A-Z0-9_]*-\d{3,})\s*$"
)

DIAGRAM_RELATIONSHIP_PATTERNS = {
    False: DIAGRAM_RELATIONSHIP,
    True: LEGACY_DIAGRAM_RELATIONSHIP,
}

DIAGRAM_EDGE_OPERATOR = re.compile(r"(?:-->|-\.|==>|---|~~~|--[ox]|<--)")

UNSAFE_MERMAID_URI = re.compile(
    r"(?:\b(?:https?|file|javascript|data):[^\s]|\bwww\.)",
    re.IGNORECASE,
)

ENCODED_MERMAID_TAG = re.compile(r"&(?:lt|gt|#0*60|#0*62|#x0*3c|#x0*3e);", re.I)

UNSAFE_LEGACY_MERMAID_CONTENT = re.compile(
    r"(?im)^\s*(?:click|callback|href)\b|^\s*%%\{|\burl\s*\(|"
    r"<\s*/?\s*[A-Za-z][^>\r\n]*>"
)

_DIAGRAM_AUTHORITY_TOPIC = re.compile(
    r"\b(?:gate\s*[ab]|(?:aws|account)\s+access|aws\s+(?:account|session|credentials|"
    r"authority)|cloud\s+account|access|owner|gates?|authority|approvals?|"
    r"authori[sz]ations?|permissions?|consents?|sign[- ]?offs?|go[- ]ahead|green\s+light|"
    r"construction|deployment)\b",
    re.IGNORECASE,
)
_DIAGRAM_AUTHORITY_RESULT = re.compile(
    r"\b(?:approved?|authori[sz]ed?|grants?|granted|permits?|permitted|consented|"
    r"signed\s+off|gave\s+permission|okay(?:ed|s)?|accepted|cleared|enabled|established|"
    r"confirmed|verified|validated|operational|passed|connected|linked|accessed|"
    r"authenticated|recorded|received|obtained|agreed|endorsed|signed|given|documented|"
    r"finalized|waived|acknowledged|active|greenlit|available|"
    r"ready|complete)\b",
    re.IGNORECASE,
)
_DIAGRAM_OWNER_SELECTION_CLAIM = re.compile(
    r"\bowner(?:['’]s)?(?:[-\s]+[a-z][\w-]*){0,3}[-\s]+(?:selected|chose|chosen)\b|"
    r"\b(?:selected|chosen)\s+by\s+(?:the\s+)?owner\b",
    re.IGNORECASE,
)
_DIAGRAM_EXECUTION_TOPIC = re.compile(
    r"\b(?:architecture|deployment|implementation|tests?|recovery|release|production|"
    r"infrastructure|(?:aws|cloud)\s+resources?|system|application|service|environment|"
    r"construction|stacks?|lambda|api|website|database|workload|functions?|endpoint)\b",
    re.IGNORECASE,
)
_DIAGRAM_EXECUTION_RESULT_WORD = (
    r"(?:observed|verified|deployed|implemented|tested|reconciled|completed|succeeded|"
    r"successful|confirmed|passed|pass|worked|finished|proven|provisioned|created|"
    r"released|shipped|operational|online|live|running|done|green|validated|healthy|"
    r"occurred|executed|exists?|ready|available|linked|authenticated|enabled|established|"
    r"accepted|cleared|complete|active|built|configured|launched|started|serving|responding|"
    r"reachable|accessible|functioning|working|passing|recovered|restored|rolled\s+back|"
    r"published|applied|allocated)"
)
_DIAGRAM_EXECUTION_RESULT = re.compile(
    rf"\b{_DIAGRAM_EXECUTION_RESULT_WORD}\b", re.IGNORECASE
)
_DIAGRAM_COST_TOPIC = re.compile(
    r"\b(?:costs?|spend(?:ing)?|budgets?|charges?|bills?|billing)\b", re.IGNORECASE
)
_DIAGRAM_COST_RESULT = re.compile(
    r"\b(?:approved|observed|verified|confirmed|incurred|paid|spent|charged|available|"
    r"active|reconciled)\b",
    re.IGNORECASE,
)
_DIAGRAM_OFFICIAL_SERVICE_NAME = re.compile(
    r"\b(?:amazon\s+)?verified[\s,]+permissions\b|\baws\s+verified[\s,]+access\b",
    re.IGNORECASE,
)
_DIAGRAM_DOCUMENTED_PLAN = re.compile(
    r"\b(?:documented\s+(?:approval|authorization|permission|consent|sign[- ]off|"
    r"deployment|construction)\s+(?:plan|workflow|path|strategy|procedure|mechanism|"
    r"boundary|request|requirement)|(?:approval|authorization|permission|consent|"
    r"sign[- ]off|deployment|construction)\s+(?:plan|workflow|path|strategy|procedure|"
    r"mechanism|boundary|request|requirement)\s+documented)\b",
    re.IGNORECASE,
)
_DIAGRAM_RESULT_BOUNDARY = re.compile(
    r"[,;]|\b(?:and|but|however|because|while|although|though|whereas|nevertheless|"
    r"nonetheless)\b|(?<!not\s)\byet\b",
    re.IGNORECASE,
)
_DIAGRAM_RESULT_NEGATION = re.compile(
    r"(?:\bnot(?!\s+only\b)(?:\s+[a-z][\w-]*){0,4}|^\s*no(?:\s+[a-z][\w-]*){0,5})\s*$",
    re.IGNORECASE,
)
_DIAGRAM_RESULT_FUTURE = re.compile(
    r"\b(?:will|shall|must|should|may|might|can|could|would)"
    r"(?:\s+[a-z][\w-]*){0,3}\s*$|"
    r"\b(?:is|are|was|were)\s+(?:expected|planned|proposed|required)\s+to"
    r"(?:\s+[a-z][\w-]*){0,2}\s*$|"
    r"\b(?:is|are|needs?|expects?|plans?)\s+to(?:\s+[a-z][\w-]*){0,2}\s*$",
    re.IGNORECASE,
)
_DIAGRAM_IMPLICIT_RESULT_PREFIX = re.compile(
    r"\b(?:is|are|was|were|has\s+been|have\s+been)\s+(?:successfully\s+)?$",
    re.IGNORECASE,
)
_DIAGRAM_IMPLICIT_RESULT_SUFFIX = re.compile(
    rf"^\s+(?:and\s+{_DIAGRAM_EXECUTION_RESULT_WORD}|successfully|to\s+production|in\s+aws)\b",
    re.IGNORECASE,
)


def _diagram_result_is_non_current(sentence: str, result: re.Match[str]) -> bool:
    """Return whether grammar makes this one result future or explicitly negative."""

    local_prefix = _DIAGRAM_RESULT_BOUNDARY.split(sentence[: result.start()])[-1]
    if _DIAGRAM_RESULT_NEGATION.search(local_prefix) or _DIAGRAM_RESULT_FUTURE.search(
        local_prefix
    ):
        return True
    suffix = sentence[result.end() :]
    if result.group().casefold() == "validated" and (
        (
            re.search(r"\breceives?\s+the\s*$", sentence[: result.start()], re.I)
            and re.match(r"\s+result\b", suffix, re.I)
        )
        or (
            re.search(
                r"\brollback\s+to\s+the(?:,\s*|\s+)last\s*$",
                sentence[: result.start()],
                re.I,
            )
            and re.match(r"\s+stack\b", suffix, re.I)
        )
    ):
        return True
    if result.group().casefold() == "documented" and _DIAGRAM_DOCUMENTED_PLAN.search(
        sentence
    ):
        return True
    return (
        result.group().casefold() == "complete"
        and not sentence[: result.start()].strip()
        and re.match(
            r"\s+(?:planned|proposed)\b", sentence[result.end() :], re.IGNORECASE
        )
        is not None
    )


def _unsupported_diagram_claim(value: str) -> bool:
    """Reject current authority or execution claims while retaining plans and limits."""

    value = unicodedata.normalize("NFKC", html.unescape(value))
    value = "".join(char for char in value if unicodedata.category(char)[0] != "C")
    value = _DIAGRAM_OFFICIAL_SERVICE_NAME.sub("managed service", value)
    for sentence in re.split(r"[.;]", value):
        if _DIAGRAM_OWNER_SELECTION_CLAIM.search(sentence):
            return True
        authority_topic = _DIAGRAM_AUTHORITY_TOPIC.search(sentence)
        for result in _DIAGRAM_AUTHORITY_RESULT.finditer(sentence):
            if authority_topic and not _diagram_result_is_non_current(sentence, result):
                return True
        execution_topic = _DIAGRAM_EXECUTION_TOPIC.search(sentence)
        for result in _DIAGRAM_EXECUTION_RESULT.finditer(sentence):
            if _diagram_result_is_non_current(sentence, result):
                continue
            prefix = sentence[: result.start()]
            suffix = sentence[result.end() :]
            if (
                execution_topic
                or _DIAGRAM_IMPLICIT_RESULT_PREFIX.search(prefix)
                or _DIAGRAM_IMPLICIT_RESULT_SUFFIX.search(suffix)
            ):
                return True
        cost_topic = _DIAGRAM_COST_TOPIC.search(sentence)
        for result in _DIAGRAM_COST_RESULT.finditer(sentence):
            if cost_topic and not _diagram_result_is_non_current(sentence, result):
                return True
    return False


def _mermaid_claim_issues(diagram_id: str, body: str) -> list[str]:
    """Reject unsafe legacy presentation without changing semantic bytes."""

    normalized = unicodedata.normalize("NFKC", html.unescape(body))
    normalized = "".join(
        char for char in normalized if unicodedata.category(char) != "Cf"
    )
    markup_free = re.sub(r"<br\s*/?>", "", normalized, flags=re.I)
    if UNSAFE_MERMAID_URI.search(normalized) or UNSAFE_LEGACY_MERMAID_CONTENT.search(
        markup_free
    ):
        return [
            f"{diagram_id}: legacy Mermaid must not contain active directives, external URIs, or unsupported markup"
        ]

    for line in normalized.splitlines():
        visible = line.strip()
        if not visible or visible.startswith("%%"):
            continue
        if visible.partition(" ")[0].casefold() in {
            "flowchart",
            "direction",
            "classdef",
            "class",
            "style",
            "linkstyle",
            "end",
        }:
            continue
        visible = re.sub(r"<br\s*/?>", ", ", visible, flags=re.I)
        visible = STABLE_CONTRACT_ID.sub("NODE", visible)
        visible = re.sub(r"^(?:accTitle|accDescr):\s*", "", visible, flags=re.I)
        visible = re.sub(r"^subgraph\s+[A-Z][A-Z0-9_]*\s*", "", visible, flags=re.I)
        visible = " ".join(re.sub(r'[][(){}"|<>=.:-]+', " ", visible).split())
        if _unsupported_diagram_claim(visible):
            return [
                f"{diagram_id}: visible Mermaid text must not claim approval, authorization, access, or observed execution evidence"
            ]
    return []


def _presentation_issues(messages: Iterable[str]) -> list[str]:
    """Tag safe display corrections without changing canonical Design state."""

    return [f"{DIAGRAM_PRESENTATION_DIAGNOSTIC}: {message}" for message in messages]


def is_diagram_presentation_issue(message: str) -> bool:
    """Return whether an issue affects only the derived owner-visible rendering."""

    return message.startswith(f"{DIAGRAM_PRESENTATION_DIAGNOSTIC}: ")


def diagram_remediation_headings(
    contract: DiagramContract | None = None,
) -> tuple[str, ...]:
    """Return every bounded canonical PRD section a diagram repair may need."""

    kinds = (
        {record.kind for record in contract.records if record.status == "CURRENT"}
        if contract is not None and contract.status == "CURRENT"
        else DIAGRAM_HEADING_TITLES
    )
    return (
        "Project diagram contract",
        *(title for kind, title in DIAGRAM_HEADING_TITLES.items() if kind in kinds),
    )


def filter_diagram_slices(
    slices: Iterable[str], prd_path: str, source: str | None
) -> list[str]:
    """Omit missing diagram targets while retaining ambiguous source for review."""

    if source is None:
        return list(slices)
    structural = without_fenced_code(source)
    headings = diagram_remediation_headings()
    pattern = re.compile(
        rf"^#{{1,6}}[ \t]+(?:\d+(?:\.\d+)*\.?[ \t]+)?"
        rf"(?P<title>{'|'.join(map(re.escape, headings))})[ \t]*\r?$",
        re.MULTILINE,
    )
    existing = {
        f"{prd_path}#{match.group('title')}" for match in pattern.finditer(structural)
    }
    targets = {f"{prd_path}#{heading}" for heading in headings}
    return [item for item in slices if item not in targets or item in existing]


@dataclass(frozen=True)
class _DiagramPresentationContext:
    """Normalized canonical endpoints used only to validate owner-visible views."""

    architecture_id: str | None
    requirement_ids: tuple[str, ...]
    actor_ids: tuple[str, ...]
    journey_ids: tuple[str, ...]
    use_case_ids: tuple[str, ...]
    interface_ids: tuple[str, ...]
    boundary_ids: tuple[str, ...]
    state_ids: tuple[str, ...]
    all_aws_ids: frozenset[str]
    applicable_aws_ids: frozenset[str]
    current_ids: frozenset[str]
    labels_by_id: Mapping[str, str]
    styles_by_id: Mapping[str, str]
    technology_ids_by_concern: Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class _ParsedDiagramRow:
    """Normalized identity and bindings for one diagram-contract row."""

    diagram_id: str
    kind: str
    applicability: str
    status: str
    anchor: str
    basis_ids: tuple[str, ...]
    referenced_ids: tuple[str, ...]


def required_diagram_kinds(
    text: str,
    requirement_ids: Iterable[str],
    work_kind: str | None,
    *,
    journey_ids: Iterable[str] = (),
    use_case_ids: Iterable[str] = (),
    state_ids: Iterable[str] = (),
    modern_contract: bool = True,
) -> set[str]:
    """Return diagram kinds required by the current canonical project records."""

    required = set(
        DIAGRAM_REQUIRED_KINDS if modern_contract else LEGACY_DIAGRAM_REQUIRED_KINDS
    )
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
    journeys = set(journey_ids)
    use_cases = set(use_case_ids)
    states = set(state_ids)
    if modern_contract and (len(journeys) > 1 or use_cases):
        required.add("JOURNEY")
    if modern_contract and states:
        required.add("STATE")
    return required


def diagram_patterns_required(
    text: str,
    requirement_ids: Iterable[str],
    work_kind: str | None,
    *,
    journey_ids: Iterable[str] = (),
    use_case_ids: Iterable[str] = (),
    state_ids: Iterable[str] = (),
) -> bool:
    """Return whether Design must load the on-demand diagram procedure."""

    try:
        table = contract_table_after_heading(
            text, DIAGRAM_CONTRACT_HEADING, DIAGRAM_CONTRACT_HEADERS
        )
    except ValueError:
        return True
    if table is None:
        return True
    required = required_diagram_kinds(
        text,
        requirement_ids,
        work_kind,
        journey_ids=journey_ids,
        use_case_ids=use_case_ids,
        state_ids=state_ids,
    )
    observed_kinds = {row[1] for row in table.rows}
    return bool(required - observed_kinds) or any(
        (row[1] in required or row[2] == "REQUIRED") and row[3] != "CURRENT"
        for row in table.rows
    )


def _plain_mermaid_label(value: str) -> str:
    """Return the owner-visible Mermaid label without presentation markup."""

    without_breaks = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    without_tags = re.sub(r"<[^>]+>", " ", without_breaks)
    return clean_cell(without_tags)


def _exposed_current_contract_id(
    value: str,
    current_ids: Iterable[str],
) -> str | None:
    """Return an exact current ID exposed in owner text, not ISO/RFC-like prose."""

    label = _plain_mermaid_label(value)
    for identifier in sorted(set(current_ids), key=lambda item: (-len(item), item)):
        if re.search(
            rf"(?<![A-Z0-9-]){re.escape(identifier)}(?![A-Z0-9-])",
            label,
            re.IGNORECASE,
        ):
            return identifier
    return None


def _unsafe_visible_mermaid_issues(
    diagram_id: str,
    field: str,
    value: str,
    *,
    allow_breaks: bool,
) -> list[str]:
    """Reject active, external, or unsupported markup in visible Mermaid text."""

    candidate = re.sub(r"<br\s*/?>", ", ", value, flags=re.I) if allow_breaks else value
    if any(unicodedata.category(char)[0] == "C" for char in candidate):
        return [f"{diagram_id}: {field} must not contain control or format characters"]
    if "<" in candidate or ">" in candidate or ENCODED_MERMAID_TAG.search(candidate):
        return [
            f"{diagram_id}: {field} may use only plain text and supported line breaks"
        ]
    if UNSAFE_MERMAID_URI.search(candidate):
        return [f"{diagram_id}: {field} must not contain an external or active URI"]
    if _unsupported_diagram_claim(candidate):
        return [
            f"{diagram_id}: {field} must not claim approval, authorization, access, or observed execution evidence"
        ]
    return []


def _diagram_node_label(match: re.Match[str]) -> str:
    """Return the quoted label from one supported Mermaid node shape."""

    return next(
        value
        for name in ("rect", "data", "round")
        if (value := match.group(name)) is not None
    )


def _mermaid_label_issues(
    diagram_id: str,
    identifier: str,
    raw_label: str,
    current_ids: Iterable[str] = (),
) -> tuple[str, list[str]]:
    """Validate one concise owner-visible node label."""

    issues = _unsafe_visible_mermaid_issues(
        diagram_id, f"{identifier} label", raw_label, allow_breaks=True
    )
    label = _plain_mermaid_label(raw_label)
    if not label:
        return label, [
            *issues,
            f"{diagram_id}: {identifier} has no owner-visible label",
        ]
    if _exposed_current_contract_id(label, current_ids) is not None:
        return label, [
            *issues,
            f"{diagram_id}: {identifier} label must not expose a canonical record ID",
        ]
    if label.casefold() in GENERIC_DIAGRAM_LABELS:
        return label, [
            *issues,
            f"{diagram_id}: {identifier} label {label!r} is generic; name the real actor, component, service, state, or outcome",
        ]
    return label, issues


def _mermaid_node_inventory_issues(
    diagram_id: str,
    node_counts: Mapping[str, int],
    referenced_ids: Iterable[str],
) -> list[str]:
    """Require exactly one displayed node for every canonical endpoint."""

    issues = [
        f"{diagram_id}: referenced endpoint {identifier} must have exactly one quoted human label; found {node_counts.get(identifier, 0)}"
        for identifier in sorted(set(referenced_ids))
        if node_counts.get(identifier, 0) != 1
    ]
    extra_nodes = sorted(set(node_counts) - set(referenced_ids))
    if extra_nodes:
        issues.append(
            f"{diagram_id}: Mermaid declares unreferenced nodes: "
            + ", ".join(extra_nodes)
        )
    return issues


def _mermaid_expected_label_issues(
    diagram_id: str,
    observed_labels: Mapping[str, str],
    expected_labels: Mapping[str, str],
) -> list[str]:
    """Bind selected AWS mechanisms to their owner-visible diagram labels."""

    return [
        f"{diagram_id}: {identifier} label must match its selected technical value {expected!r}"
        for identifier, expected in sorted(expected_labels.items())
        if (observed := observed_labels.get(identifier)) is not None
        and observed != _plain_mermaid_label(expected)
    ]


def _mermaid_node_issues(
    diagram_id: str,
    kind: str,
    lines: list[str],
    referenced_ids: Iterable[str],
    expected_labels: Mapping[str, str] | None = None,
    current_ids: Iterable[str] = (),
) -> tuple[dict[str, int], dict[str, str | None], list[str]]:
    """Validate readable canonical nodes and return their style assignments."""

    issues: list[str] = []
    node_matches = [
        match for line in lines if (match := DIAGRAM_NODE.fullmatch(line)) is not None
    ]
    node_counts: dict[str, int] = {}
    observed_labels: dict[str, str] = {}
    observed_styles: dict[str, str | None] = {}
    for match in node_matches:
        identifier = match.group("id")
        node_counts[identifier] = node_counts.get(identifier, 0) + 1
        raw_label = _diagram_node_label(match)
        label, label_issues = _mermaid_label_issues(
            diagram_id, identifier, raw_label, current_ids
        )
        observed_labels[identifier] = label
        observed_styles[identifier] = match.group("style")
        issues.extend(label_issues)
    issues.extend(
        _mermaid_node_inventory_issues(diagram_id, node_counts, referenced_ids)
    )
    issues.extend(
        _mermaid_expected_label_issues(
            diagram_id, observed_labels, expected_labels or {}
        )
    )
    return node_counts, observed_styles, issues


def _mermaid_relationship_issues(
    diagram_id: str,
    relationships: tuple[tuple[str, str, str], ...],
    current_ids: Iterable[str] = (),
) -> list[str]:
    """Validate concise human relationship labels and explicit containment."""

    issues: list[str] = []
    for _source, relation, _target in relationships:
        issues.extend(
            _unsafe_visible_mermaid_issues(
                diagram_id, "relationship label", relation, allow_breaks=False
            )
        )
        if _exposed_current_contract_id(relation, current_ids) is not None:
            issues.append(
                f"{diagram_id}: relationship labels must not expose canonical record IDs"
            )
        if len(relation) > 72:
            issues.append(
                f"{diagram_id}: relationship label exceeds 72 visible characters"
            )
        if relation.casefold() == "includes":
            issues.append(
                f"{diagram_id}: containment must use a subgraph, not an includes arrow"
            )
    return issues


def _unsupported_mermaid_edge_issues(
    diagram_id: str,
    lines: list[str],
) -> list[str]:
    """Reject every visible edge outside the bound canonical relationship form."""

    unsupported = [
        line.strip()
        for line in lines
        if DIAGRAM_EDGE_OPERATOR.search(line)
        and DIAGRAM_RELATIONSHIP.fullmatch(line) is None
        and not line.lstrip().startswith("%%")
    ]
    if not unsupported:
        return []
    return [
        f"{diagram_id}: every visible relationship must connect labeled canonical component nodes; unsupported edge {unsupported[0]!r}"
    ]


def _unsupported_mermaid_statement_issues(
    diagram_id: str,
    lines: list[str],
) -> list[str]:
    """Reject interactive, renderer-specific, or unbound Mermaid statements."""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("%%"):
            if not stripped.startswith("%%{"):
                continue
        elif (
            DIAGRAM_FLOWCHART.fullmatch(line)
            or DIAGRAM_ACC_TITLE.fullmatch(line)
            or DIAGRAM_ACC_DESCRIPTION.fullmatch(line)
            or DIAGRAM_SUBGRAPH.fullmatch(line)
            or DIAGRAM_DIRECTION.fullmatch(line)
            or DIAGRAM_NODE.fullmatch(line)
            or DIAGRAM_RELATIONSHIP.fullmatch(line)
            or DIAGRAM_CLASS_DEF.fullmatch(line)
            or stripped.casefold() == "end"
        ):
            continue
        return [
            f"{diagram_id}: unsupported Mermaid statement {stripped!r}; use only the portable bound diagram grammar"
        ]
    return []


def _mermaid_accessibility_issues(
    diagram_id: str,
    lines: list[str],
    current_ids: Iterable[str] = (),
) -> list[str]:
    """Require one useful accessible title and description without record IDs."""

    issues: list[str] = []
    titles = [
        match.group("value")
        for line in lines
        if (match := DIAGRAM_ACC_TITLE.fullmatch(line))
    ]
    descriptions = [
        match.group("value")
        for line in lines
        if (match := DIAGRAM_ACC_DESCRIPTION.fullmatch(line))
    ]
    if len(titles) != 1 or not _plain_mermaid_label(titles[0] if titles else ""):
        issues.append(f"{diagram_id}: Mermaid requires one meaningful accTitle")
    if len(descriptions) != 1 or not _plain_mermaid_label(
        descriptions[0] if descriptions else ""
    ):
        issues.append(f"{diagram_id}: Mermaid requires one meaningful accDescr")
    for label, name in ((titles, "accTitle"), (descriptions, "accDescr")):
        if label:
            issues.extend(
                _unsafe_visible_mermaid_issues(
                    diagram_id, name, label[0], allow_breaks=False
                )
            )
        if label and _exposed_current_contract_id(label[0], current_ids):
            issues.append(f"{diagram_id}: Mermaid {name} must not expose record IDs")
    return issues


def _planned_diagram_language_issues(
    diagram_id: str,
    kind: str,
    lines: list[str],
) -> list[str]:
    """Keep Design diagrams explicit about planned rather than observed state."""

    if kind not in {"SYSTEM_CONTEXT", "AWS_IMPLEMENTATION"}:
        return []
    values = [
        match.group("value")
        for line in lines
        for pattern in (DIAGRAM_ACC_TITLE, DIAGRAM_ACC_DESCRIPTION)
        if (match := pattern.fullmatch(line)) is not None
    ]
    values.extend(
        match.group("label")
        for line in lines
        if (match := DIAGRAM_SUBGRAPH.fullmatch(line)) is not None
    )
    combined = " ".join(_plain_mermaid_label(value) for value in values)
    if re.search(r"\b(?:planned|proposed)\b", combined, re.IGNORECASE) is None:
        return [
            f"{diagram_id}: broad Design diagram must identify the architecture as planned or proposed"
        ]
    return []


def _mermaid_subgraph_issues(
    diagram_id: str,
    lines: list[str],
    *,
    maximum_depth_allowed: int | None,
    current_ids: Iterable[str] = (),
) -> tuple[int, list[str]]:
    """Validate labeled, balanced broad-view containment."""

    issues: list[str] = []
    subgraph_lines = [
        line for line in lines if re.match(r"^\s*subgraph\s+", line, re.I)
    ]
    subgraphs = [
        match
        for line in subgraph_lines
        if (match := DIAGRAM_SUBGRAPH.fullmatch(line)) is not None
    ]
    if len(subgraph_lines) != len(subgraphs):
        issues.append(f"{diagram_id}: every subgraph requires one quoted human label")
    for match in subgraphs:
        raw_label = match.group("label")
        issues.extend(
            _unsafe_visible_mermaid_issues(
                diagram_id, "subgraph label", raw_label, allow_breaks=False
            )
        )
        label = _plain_mermaid_label(raw_label)
        if not label or _exposed_current_contract_id(label, current_ids):
            issues.append(
                f"{diagram_id}: subgraph labels must be meaningful and hide record IDs"
            )
    depth = 0
    maximum_depth = 0
    unmatched_end = False
    for line in lines:
        if re.match(r"^\s*subgraph\s+", line, re.I):
            depth += 1
            maximum_depth = max(maximum_depth, depth)
        elif line.strip().casefold() == "end":
            if depth:
                depth -= 1
            else:
                unmatched_end = True
    if depth or unmatched_end:
        issues.append(f"{diagram_id}: Mermaid subgraph boundaries must be balanced")
    if maximum_depth_allowed is not None and maximum_depth > maximum_depth_allowed:
        issues.append(
            f"{diagram_id}: broad architecture boundaries may be no more than {maximum_depth_allowed} levels deep"
        )
    return len(subgraphs), issues


def _mermaid_structure_issues(
    diagram_id: str,
    kind: str,
    lines: list[str],
    current_ids: Iterable[str] = (),
) -> list[str]:
    """Require one portable flowchart and structurally valid optional grouping."""

    flowcharts = [
        match
        for line in lines
        if (match := DIAGRAM_FLOWCHART.fullmatch(line)) is not None
    ]
    issues = (
        []
        if len(flowcharts) == 1
        else [
            f"{diagram_id}: Mermaid requires exactly one supported flowchart declaration"
        ]
    )
    first_statement = next(
        (line for line in lines if line.strip() and not line.lstrip().startswith("%%")),
        "",
    )
    if DIAGRAM_FLOWCHART.fullmatch(first_statement) is None:
        issues.append(
            f"{diagram_id}: flowchart declaration must be the first statement"
        )
    _count, subgraph_issues = _mermaid_subgraph_issues(
        diagram_id,
        lines,
        maximum_depth_allowed=(
            3 if kind in {"SYSTEM_CONTEXT", "AWS_IMPLEMENTATION"} else None
        ),
        current_ids=current_ids,
    )
    return [*issues, *subgraph_issues]


def _mermaid_class_definitions(
    diagram_id: str,
    style_matches: Iterable[re.Match[str]],
) -> tuple[dict[str, dict[str, list[str]]], list[str]]:
    """Parse restrained Mermaid class definitions without accepting active values."""

    issues: list[str] = []
    definitions: dict[str, dict[str, list[str]]] = {}
    for match in style_matches:
        properties: dict[str, list[str]] = {}
        for declaration in match.group("body").rstrip(";").split(","):
            name, separator, value = declaration.partition(":")
            if not separator:
                issues.append(
                    f"{diagram_id}: Mermaid classDef contains an invalid declaration"
                )
                continue
            properties.setdefault(name.strip().casefold(), []).append(
                value.strip().casefold()
            )
        definitions[match.group("name").casefold()] = properties
    return definitions, issues


def _mermaid_palette_issues(
    diagram_id: str,
    definitions: Mapping[str, Mapping[str, list[str]]],
) -> list[str]:
    """Require every declared class to use one approved static semantic palette."""

    issues: list[str] = []
    for role, definition in sorted(definitions.items()):
        if role not in DIAGRAM_ROLE_COLORS:
            issues.append(f"{diagram_id}: unsupported Mermaid classDef {role!r}")
            continue
        fill, stroke = DIAGRAM_ROLE_COLORS[role]
        if (
            definition.get("fill") != [fill]
            or definition.get("stroke") != [stroke]
            or definition.get("color") != ["#232f3e"]
            or any(
                name not in {"fill", "stroke", "color", "stroke-width"}
                or len(values) != 1
                for name, values in definition.items()
            )
            or (
                definition.get("stroke-width") != ["2px"]
                if role == "actor"
                else definition.get("stroke-width") not in (None, ["1px"])
            )
        ):
            issues.append(
                f"{diagram_id}: {role} classDef must use the approved readable semantic palette"
            )
    return issues


def _mermaid_style_issues(
    diagram_id: str,
    lines: list[str],
    node_styles: Mapping[str, str | None],
    expected_styles: Mapping[str, str],
    *,
    require_node_styles: bool,
) -> list[str]:
    """Require one restrained, fully declared role palette."""

    issues: list[str] = []
    unstyled = sorted(
        identifier for identifier, style in node_styles.items() if not style
    )
    if require_node_styles and unstyled:
        issues.append(
            f"{diagram_id}: broad architecture nodes require role styles: "
            + ", ".join(unstyled)
        )
    style_matches = [
        match
        for line in lines
        if (match := DIAGRAM_CLASS_DEF.fullmatch(line)) is not None
    ]
    style_names = [match.group("name").casefold() for match in style_matches]
    if len(style_names) != len(set(style_names)):
        issues.append(f"{diagram_id}: Mermaid classDef names must be unique")
    defined_styles = set(style_names)
    used_styles = {style for style in node_styles.values() if style}
    missing_styles = sorted(used_styles - defined_styles)
    if missing_styles:
        issues.append(
            f"{diagram_id}: Mermaid styles are used without classDef declarations: "
            + ", ".join(missing_styles)
        )
    unused_styles = sorted(defined_styles - used_styles)
    if unused_styles:
        issues.append(
            f"{diagram_id}: Mermaid classDef styles must be used by displayed nodes: "
            + ", ".join(unused_styles)
        )
    if len(defined_styles) > 6:
        issues.append(f"{diagram_id}: Mermaid may define at most six semantic styles")
    wrong_roles = sorted(
        identifier
        for identifier, expected in expected_styles.items()
        if node_styles.get(identifier) not in {None, expected}
    )
    if wrong_roles:
        issues.append(
            f"{diagram_id}: nodes use a color role that conflicts with canonical meaning: "
            + ", ".join(wrong_roles)
        )
    definitions, definition_issues = _mermaid_class_definitions(
        diagram_id, style_matches
    )
    issues.extend(definition_issues)
    issues.extend(_mermaid_palette_issues(diagram_id, definitions))
    return issues


def _mermaid_membership_inventory(
    lines: list[str],
) -> tuple[dict[str, int], dict[str, tuple[str, ...]], set[str]]:
    """Return subgraph descendants and canonical-node containment."""

    stack: list[str] = []
    descendant_counts: dict[str, int] = {}
    memberships: dict[str, tuple[str, ...]] = {}
    duplicate_subgraphs: set[str] = set()
    for line in lines:
        if (subgraph := DIAGRAM_MEMBERSHIP_SUBGRAPH.fullmatch(line)) is not None:
            subgraph_id = subgraph.group("id").upper()
            if subgraph_id in descendant_counts:
                duplicate_subgraphs.add(subgraph_id)
            descendant_counts.setdefault(subgraph_id, 0)
            stack.append(subgraph_id)
        elif line.strip().casefold() == "end":
            if stack:
                stack.pop()
        elif (node := DIAGRAM_MEMBERSHIP_NODE.match(line)) is not None:
            identifier = node.group("id")
            memberships[identifier] = tuple(stack)
            for subgraph_id in stack:
                descendant_counts[subgraph_id] += 1
    return descendant_counts, memberships, duplicate_subgraphs


def _actor_containment_issues(
    diagram_id: str,
    memberships: Mapping[str, tuple[str, ...]],
    expected_styles: Mapping[str, str],
) -> list[str]:
    """Keep external actors outside every component-containing boundary."""

    internal_subgraphs = {
        subgraph_id
        for identifier, role in expected_styles.items()
        if role != "actor"
        for subgraph_id in memberships.get(identifier, ())
    }
    enclosed = sorted(
        identifier
        for identifier, role in expected_styles.items()
        if role == "actor"
        and internal_subgraphs.intersection(memberships.get(identifier, ()))
    )
    if not enclosed:
        return []
    return [
        f"{diagram_id}: external actors must remain outside the system boundary: "
        + ", ".join(enclosed)
    ]


def _mermaid_membership_issues(
    diagram_id: str,
    lines: list[str],
) -> list[str]:
    """Require broad-view groups to contain their displayed components."""

    descendant_counts, _memberships, duplicate_subgraphs = (
        _mermaid_membership_inventory(lines)
    )
    issues: list[str] = []
    if duplicate_subgraphs:
        issues.append(
            f"{diagram_id}: Mermaid subgraph IDs must be unique: "
            + ", ".join(sorted(duplicate_subgraphs))
        )
    empty = sorted(
        subgraph_id for subgraph_id, count in descendant_counts.items() if count == 0
    )
    if empty:
        issues.append(
            f"{diagram_id}: broad architecture contains empty subgraphs: "
            + ", ".join(empty)
        )
    return issues


def _semantic_mermaid_membership_issues(
    diagram_id: str,
    kind: str,
    lines: list[str],
    expected_styles: Mapping[str, str],
) -> list[str]:
    """Bind actor and component placement that changes the planned architecture."""

    if kind not in {"SYSTEM_CONTEXT", "AWS_IMPLEMENTATION"}:
        return []
    _counts, memberships, _duplicates = _mermaid_membership_inventory(lines)
    issues = _actor_containment_issues(diagram_id, memberships, expected_styles)
    minimum_depth = 2 if kind == "AWS_IMPLEMENTATION" else 1
    misplaced = sorted(
        identifier
        for identifier, role in expected_styles.items()
        if role != "actor" and len(memberships.get(identifier, ())) < minimum_depth
    )
    if misplaced:
        issues.append(
            f"{diagram_id}: broad architecture components must remain inside their organized boundaries: "
            + ", ".join(misplaced)
        )
    return issues


def _mermaid_layout_issues(
    diagram_id: str,
    kind: str,
    lines: list[str],
    node_styles: Mapping[str, str | None],
    expected_styles: Mapping[str, str],
) -> list[str]:
    """Require portable top-down grouping and defined role styles for broad views."""

    broad_view = kind in {"SYSTEM_CONTEXT", "AWS_IMPLEMENTATION"}
    issues = _mermaid_style_issues(
        diagram_id,
        lines,
        node_styles,
        expected_styles,
        require_node_styles=broad_view,
    )
    if not broad_view:
        return issues
    flowcharts = [
        match for line in lines if (match := DIAGRAM_FLOWCHART.fullmatch(line))
    ]
    if flowcharts and flowcharts[0].group("direction").upper() not in {"TB", "TD"}:
        issues.append(f"{diagram_id}: {kind} must use one top-to-bottom flowchart")
    subgraph_count = sum(DIAGRAM_SUBGRAPH.fullmatch(line) is not None for line in lines)
    grouping_threshold = 8 if kind == "SYSTEM_CONTEXT" else 6
    if len(node_styles) >= grouping_threshold and subgraph_count < 2:
        issues.append(
            f"{diagram_id}: {kind} needs labeled subgraphs to organize this many components"
        )
    issues.extend(_mermaid_membership_issues(diagram_id, lines))
    return issues


def _mermaid_presentation_issues(
    diagram_id: str,
    kind: str,
    body: str,
    referenced_ids: Iterable[str],
    relationships: tuple[tuple[str, str, str], ...],
    expected_labels: Mapping[str, str] | None = None,
    expected_styles: Mapping[str, str] | None = None,
    current_ids: Iterable[str] = (),
) -> list[str]:
    """Validate readable, portable Mermaid without deriving design semantics."""

    lines = body.splitlines()
    _counts, node_styles, node_issues = _mermaid_node_issues(
        diagram_id,
        kind,
        lines,
        referenced_ids,
        expected_labels,
        current_ids,
    )
    return [
        *node_issues,
        *_mermaid_accessibility_issues(diagram_id, lines, current_ids),
        *_planned_diagram_language_issues(diagram_id, kind, lines),
        *_mermaid_structure_issues(diagram_id, kind, lines, current_ids),
        *_mermaid_layout_issues(
            diagram_id, kind, lines, node_styles, expected_styles or {}
        ),
    ]


def _diagram_endpoint_sets(
    kind: str,
    ctx: _DiagramPresentationContext,
) -> tuple[set[str], set[str]]:
    """Return required and allowed canonical endpoints for one diagram kind."""

    architecture = {ctx.architecture_id} if ctx.architecture_id else set()
    actors = set(ctx.actor_ids) | set(ctx.journey_ids) | set(ctx.use_case_ids)
    design = architecture.union(
        ctx.interface_ids, ctx.boundary_ids, ctx.state_ids, ctx.applicable_aws_ids
    )
    if kind == "SYSTEM_CONTEXT":
        endpoints = set(ctx.actor_ids) | design
        return endpoints, endpoints
    if kind == "AWS_IMPLEMENTATION":
        endpoints = set(ctx.applicable_aws_ids) | architecture
        return endpoints, endpoints
    if kind == "JOURNEY":
        return actors, actors | design
    if kind == "STATE":
        return set(ctx.state_ids), design
    if kind == "PRIMARY_OUTCOME":
        return set(), actors | design
    if kind in {"DATA_LIFECYCLE", "FAILURE_RECOVERY", "MIGRATION"}:
        return set(), design
    return set(), set()


def _diagram_kind_requirements(
    kind: str,
    context: _DiagramPresentationContext,
) -> tuple[tuple[tuple[str, frozenset[str]], ...], frozenset[str]]:
    """Return declarative endpoint groups and basis records for one focused view."""

    project_entry = (
        set(context.interface_ids)
        | set(context.boundary_ids)
        | ({context.architecture_id} if context.architecture_id else set())
    )
    if kind == "SYSTEM_CONTEXT":
        return (
            (
                (
                    "the selected architecture",
                    frozenset(
                        {context.architecture_id} if context.architecture_id else set()
                    ),
                ),
            ),
            frozenset(context.requirement_ids),
        )
    if kind == "AWS_IMPLEMENTATION":
        return (
            (
                (
                    "the selected architecture",
                    frozenset(
                        {context.architecture_id} if context.architecture_id else set()
                    ),
                ),
            ),
            frozenset(
                identifier
                for identifier in context.current_ids
                if identifier.startswith("DES-")
            ),
        )
    if kind == "PRIMARY_OUTCOME":
        if not any((context.actor_ids, context.journey_ids, context.use_case_ids)):
            return (
                (("a current project interface", frozenset(context.interface_ids)),),
                frozenset(context.requirement_ids),
            )
        return (
            (
                ("an approved actor", frozenset(context.actor_ids)),
                ("a current project interface", frozenset(context.interface_ids)),
            ),
            frozenset((*context.journey_ids, *context.use_case_ids)),
        )
    concern_by_kind = {
        "DATA_LIFECYCLE": ("DATA_STORAGE", "DATA-", "data-storage"),
        "FAILURE_RECOVERY": (
            "RELIABILITY_RECOVERY",
            "REL-",
            "recovery",
        ),
    }
    if kind in concern_by_kind:
        concern, basis_prefix, label = concern_by_kind[kind]
        return (
            (
                (
                    "a project entry or architecture component",
                    frozenset(project_entry),
                ),
                (
                    f"the selected {label} mechanism",
                    context.technology_ids_by_concern.get(concern, frozenset()),
                ),
            ),
            frozenset(
                identifier
                for identifier in context.current_ids
                if identifier.startswith(basis_prefix)
            ),
        )
    if kind == "MIGRATION":
        return (
            (
                ("a project boundary", frozenset(context.boundary_ids)),
                (
                    "the selected architecture",
                    frozenset(
                        {context.architecture_id} if context.architecture_id else set()
                    ),
                ),
            ),
            frozenset(
                identifier
                for identifier in context.current_ids
                if identifier.startswith("PRES-")
            ),
        )
    return (), frozenset()


def _diagram_kind_semantic_issues(
    diagram_id: str,
    kind: str,
    basis_ids: Iterable[str],
    endpoint_ids: set[str],
    context: _DiagramPresentationContext,
) -> list[str]:
    """Require each focused view to contain the canonical roles its purpose names."""

    required_groups, required_basis = _diagram_kind_requirements(kind, context)
    issues: list[str] = []
    for label, candidates in required_groups:
        if not candidates or not endpoint_ids.intersection(candidates):
            issues.append(f"{diagram_id}: {kind} must show {label}")
    if required_groups and (
        not required_basis or not set(basis_ids).intersection(required_basis)
    ):
        issues.append(f"{diagram_id}: {kind} lacks its canonical purpose basis")
    return issues


def _diagram_connectivity_issues(
    diagram_id: str,
    kind: str,
    endpoint_ids: set[str],
    relationships: tuple[tuple[str, str, str], ...],
) -> list[str]:
    """Require one connected owner story where the diagram kind promises one view."""

    if kind == "STATE" or not endpoint_ids:
        return []
    self_loops = sorted(
        source for source, _relation, target in relationships if source == target
    )
    issues = (
        [f"{diagram_id}: {kind} must not contain self-loop " + ", ".join(self_loops)]
        if self_loops
        else []
    )
    if kind == "JOURNEY":
        return issues
    adjacent = {identifier: set() for identifier in endpoint_ids}
    for source, _relation, target in relationships:
        adjacent.setdefault(source, set()).add(target)
        adjacent.setdefault(target, set()).add(source)
    reached: set[str] = set()
    pending = [min(endpoint_ids)]
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(adjacent.get(current, ()) - reached)
    if reached != endpoint_ids:
        issues.append(f"{diagram_id}: {kind} must present one connected owner view")
    return issues


def _semantic_subgraph_memberships(
    lines: Iterable[str], referenced_ids: Iterable[str]
) -> list[list[str]]:
    """Bind modern containment without binding labels, layout order, or group IDs."""

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


def _diagram_semantic_payload(
    kind: str,
    basis_ids: Iterable[str],
    referenced_ids: Iterable[str],
    relationships: Iterable[tuple[str, str, str, str]],
    body: str,
    *,
    modern_contract: bool,
) -> dict[str, object]:
    """Preserve exact legacy bytes while binding modern edge kind and containment."""

    parsed = tuple(relationships)
    payload: dict[str, object] = {
        "kind": kind,
        "basis_ids": sorted(basis_ids),
        "referenced_ids": sorted(referenced_ids),
    }
    if modern_contract:
        payload["containment"] = _semantic_subgraph_memberships(
            body.splitlines(), referenced_ids
        )
        payload["relationships"] = [
            {
                "from_id": source,
                "edge_kind": edge_kind,
                "relation": relation,
                "to_id": target,
            }
            for source, edge_kind, relation, target in sorted(parsed)
        ]
    else:
        payload["relationships"] = [
            {"from_id": source, "relation": relation, "to_id": target}
            for source, relation, target in sorted(
                {
                    (source, relation, target)
                    for source, edge_kind, relation, target in parsed
                    if edge_kind == "SOLID"
                }
            )
        ]
    return payload


def _modern_diagram_issues(
    diagram_id: str,
    kind: str,
    body: str,
    basis_ids: Iterable[str],
    referenced_ids: Iterable[str],
    relationships: tuple[tuple[str, str, str], ...],
    endpoint_ids: set[str],
    context: _DiagramPresentationContext,
) -> tuple[list[str], list[str]]:
    """Validate the modern human view against normalized canonical design facts."""

    expected_labels = {
        identifier: context.labels_by_id[identifier]
        for identifier in referenced_ids
        if identifier in context.labels_by_id
    }
    expected_styles = {
        identifier: context.styles_by_id[identifier]
        for identifier in referenced_ids
        if identifier in context.styles_by_id
    }
    presentation_issues = _mermaid_presentation_issues(
        diagram_id,
        kind,
        body,
        referenced_ids,
        relationships,
        expected_labels,
        expected_styles,
        context.current_ids,
    )
    presentation_issues.extend(
        _unsupported_mermaid_statement_issues(diagram_id, body.splitlines())
    )
    lines = body.splitlines()
    semantic_issues = [
        *_unsupported_mermaid_edge_issues(diagram_id, lines),
        *_mermaid_relationship_issues(diagram_id, relationships, context.current_ids),
        *_semantic_mermaid_membership_issues(diagram_id, kind, lines, expected_styles),
    ]
    if any(not relation for _source, relation, _target in relationships):
        semantic_issues.append(f"{diagram_id}: relationship labels must not be empty")
    missing_labels = sorted(set(referenced_ids) - set(context.labels_by_id))
    if missing_labels:
        semantic_issues.append(
            f"{diagram_id}: referenced endpoints lack canonical human labels: "
            + ", ".join(missing_labels)
        )
    required_endpoints, allowed_endpoints = _diagram_endpoint_sets(kind, context)
    unexpected = sorted(endpoint_ids - allowed_endpoints)
    if unexpected:
        semantic_issues.append(
            f"{diagram_id}: {kind} contains unrelated canonical endpoints: "
            + ", ".join(unexpected)
        )
    missing = sorted(required_endpoints - endpoint_ids)
    if missing:
        semantic_issues.append(
            f"{diagram_id}: {kind} diagram omits required project endpoints: "
            + ", ".join(missing)
        )
    semantic_issues.extend(
        _diagram_kind_semantic_issues(
            diagram_id, kind, basis_ids, endpoint_ids, context
        )
    )
    semantic_issues.extend(
        _diagram_connectivity_issues(diagram_id, kind, endpoint_ids, relationships)
    )
    return semantic_issues, presentation_issues


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


def _diagram_section_issues(text: str, kind: str, anchor: str) -> list[str]:
    """Keep every current view visible and broad views in their owner sections."""

    try:
        diagram_heading = _diagram_heading_for_anchor(text, anchor)
    except ValueError as exc:
        return [str(exc)]
    diagram_offsets = _heading_section_offsets(text, diagram_heading)
    if diagram_offsets is None:
        return [f"{kind} diagram has no source section"]
    diagram_start, body_start, diagram_end = diagram_offsets
    mermaid = re.search(r"(?m)^```mermaid[ \t]*\r?$", text[body_start:diagram_end])
    inspected_offsets = [diagram_start]
    if mermaid is not None:
        inspected_offsets.append(body_start + mermaid.start())
    for offset in inspected_offsets:
        masked_prefix = without_fenced_code(text[:offset])
        disclosure_depth = len(re.findall(r"(?im)^\s*<details>\s*$", masked_prefix))
        disclosure_depth -= len(re.findall(r"(?im)^\s*</details>\s*$", masked_prefix))
        if disclosure_depth:
            return [f"{kind} diagram must remain visible outside disclosures"]
    owner_heading = DIAGRAM_OWNER_SECTIONS.get(kind)
    if owner_heading is None:
        return []
    owner_offsets = _heading_section_offsets(text, owner_heading)
    if owner_offsets is None:
        return [f"{kind} diagram requires owner section {owner_heading}"]
    start, _body_start, end = owner_offsets
    if diagram_start < start or diagram_start >= end:
        return [f"{kind} diagram must remain inside {owner_heading}"]
    if mermaid is None:
        return [f"{kind} diagram must remain visible outside disclosures"]
    return []


def _diagram_role_styles(
    architecture_id: str | None,
    requirements: Any,
    project_contract: ProjectDesignContract,
    aws_decisions: tuple[AwsImplementationDecision, ...],
) -> dict[str, str]:
    """Derive stable semantic color roles from canonical record kinds."""

    styles = {identifier: "actor" for identifier in requirements.actor_ids}
    styles.update({identifier: "actor" for identifier in requirements.journey_ids})
    styles.update({identifier: "actor" for identifier in requirements.use_case_ids})
    styles.update(
        {identifier: "compute" for identifier in project_contract.interface_ids}
    )
    styles.update({identifier: "entry" for identifier in project_contract.boundary_ids})
    styles.update({identifier: "event" for identifier in project_contract.state_ids})
    for identifier in requirements.requirement_ids:
        prefix = identifier.split("-", 1)[0]
        styles[identifier] = {
            "DATA": "data",
            "REL": "event",
            "SEC": "event",
            "OPS": "ops",
            "COST": "ops",
        }.get(prefix, "compute")
    for decision in aws_decisions:
        role = AWS_CONCERN_STYLES[decision.concern]
        for identifier in decision.decision_ids:
            styles.setdefault(identifier, role)
    if architecture_id:
        styles[architecture_id] = "compute"
    return styles


def _diagram_contract_context(
    text: str,
    architecture: ArchitectureContract,
    requirements: Any,
    coverage: Any,
    project_contract: ProjectDesignContract,
    aws_decisions: tuple[AwsImplementationDecision, ...],
    technology_decisions: Mapping[str, TechnologyDecision],
    current_ids: Iterable[str],
    *,
    modern_contract: bool,
) -> tuple[str | None, set[str], _DiagramPresentationContext]:
    """Build one normalized applicability and presentation context."""

    architecture_id = (
        architecture.selection.architecture_id
        if architecture.selection is not None
        else None
    )
    expected_required = required_diagram_kinds(
        text,
        requirements.requirement_ids,
        coverage.work_kind,
        journey_ids=requirements.journey_ids,
        use_case_ids=requirements.use_case_ids,
        state_ids=project_contract.state_ids,
        modern_contract=modern_contract,
    )
    all_aws_ids = {
        identifier for decision in aws_decisions for identifier in decision.decision_ids
    }
    applicable_aws_ids = {
        identifier
        for decision in aws_decisions
        for identifier in decision.applicable_decision_ids
    }
    labels = dict(
        (*requirements.presentation_labels, *project_contract.presentation_labels)
    )
    labels.update(
        {
            identifier: label
            for decision in aws_decisions
            for identifier, label in decision.decision_labels
        }
    )
    if architecture.selection is not None:
        selected = next(
            (
                candidate.architecture_summary
                for candidate in architecture.candidates
                if candidate.candidate_id == architecture.selection.selected_candidate
            ),
            architecture.selection.selected_candidate,
        )
        labels[architecture.selection.architecture_id] = (
            clean_cell(selected.split(":", 1)[0]).replace("_", " ").title()
        )
    styles = _diagram_role_styles(
        architecture_id, requirements, project_contract, aws_decisions
    )
    technology_ids_by_concern = {
        concern: frozenset(
            identifier
            for identifier, decision in technology_decisions.items()
            if decision.concern == concern and identifier in applicable_aws_ids
        )
        for concern in {decision.concern for decision in technology_decisions.values()}
    }
    return (
        architecture_id,
        expected_required,
        _DiagramPresentationContext(
            architecture_id=architecture_id,
            requirement_ids=tuple(requirements.requirement_ids),
            actor_ids=tuple(requirements.actor_ids),
            journey_ids=tuple(requirements.journey_ids),
            use_case_ids=tuple(requirements.use_case_ids),
            interface_ids=tuple(project_contract.interface_ids),
            boundary_ids=tuple(project_contract.boundary_ids),
            state_ids=tuple(project_contract.state_ids),
            all_aws_ids=frozenset(all_aws_ids),
            applicable_aws_ids=frozenset(applicable_aws_ids),
            current_ids=frozenset(current_ids),
            labels_by_id=labels,
            styles_by_id=styles,
            technology_ids_by_concern=technology_ids_by_concern,
        ),
    )


def _diagram_row_state_issues(
    diagram_id: str,
    kind: str,
    applicability: str,
    status: str,
) -> list[str]:
    """Validate the exact kind, applicability, and status combination."""

    issues: list[str] = []
    if applicability not in DIAGRAM_APPLICABILITY:
        issues.append(f"{diagram_id}: invalid applicability {applicability!r}")
    if status not in DIAGRAM_STATUSES:
        issues.append(f"{diagram_id}: invalid status {status!r}")
    if kind in DIAGRAM_REQUIRED_KINDS and applicability != "REQUIRED":
        issues.append(f"{diagram_id}: {kind} applicability must be REQUIRED")
    if kind in DIAGRAM_CONDITIONAL_KINDS and applicability not in {
        "CONDITIONAL",
        "NOT_APPLICABLE",
    }:
        issues.append(
            f"{diagram_id}: {kind} applicability must be CONDITIONAL or NOT_APPLICABLE"
        )
    if (applicability == "NOT_APPLICABLE") != (status == "NOT_APPLICABLE"):
        issues.append(
            f"{diagram_id}: NOT_APPLICABLE applicability and status must be used together"
        )
    return issues


def _parse_diagram_bindings(
    diagram_id: str,
    basis_value: str,
    referenced_value: str,
    current_ids: frozenset[str],
    *,
    modern_contract: bool,
    status: str,
) -> tuple[list[tuple[str, ...]], list[str]]:
    """Parse exact basis and endpoint IDs and bind them to current records."""

    issues: list[str] = []
    parsed_ids: list[tuple[str, ...]] = []
    for value, pattern, label in (
        (basis_value, STABLE_CONTRACT_ID, f"{diagram_id} Basis IDs"),
        (referenced_value, STABLE_CONTRACT_ID, f"{diagram_id} Referenced IDs"),
    ):
        try:
            parsed_ids.append(tuple(parse_exact_id_list(value, pattern, label)))
        except ValueError as exc:
            issues.append(str(exc))
            parsed_ids.append(())
    if modern_contract:
        for field, identifiers in zip(("Basis IDs", "Referenced IDs"), parsed_ids):
            unknown = sorted(set(identifiers) - current_ids)
            if unknown:
                issues.append(
                    f"{diagram_id}: {field} are not current canonical IDs: "
                    + ", ".join(unknown)
                )
        if status in {"NOT_YET_CREATED", "NOT_APPLICABLE"} and any(parsed_ids):
            issues.append(
                f"{diagram_id}: {status} rows must use NONE basis and referenced IDs"
            )
    return parsed_ids, issues


def _parse_diagram_row(
    text: str,
    raw: tuple[str, ...],
    seen_ids: set[str],
    seen_kinds: set[str],
    current_ids: frozenset[str],
    *,
    modern_contract: bool,
    legacy_public_compatibility: bool = False,
) -> tuple[_ParsedDiagramRow, list[str]]:
    """Validate and normalize one exact diagram-contract row."""

    diagram_id, kind, applicability, status, anchor, basis_value, referenced_value = raw
    issues: list[str] = []
    if DIAGRAM_ID.fullmatch(diagram_id) is None or diagram_id in seen_ids:
        issues.append(f"Invalid or duplicate diagram ID {diagram_id!r}")
    seen_ids.add(diagram_id)
    allowed_kinds = (
        LEGACY_DIAGRAM_KINDS if legacy_public_compatibility else DIAGRAM_KINDS
    )
    if kind not in allowed_kinds or kind in seen_kinds:
        issues.append(f"Invalid or duplicate diagram kind {kind!r}")
    seen_kinds.add(kind)
    if modern_contract:
        issues.extend(
            _diagram_row_state_issues(diagram_id, kind, applicability, status)
        )
    else:
        if applicability not in DIAGRAM_APPLICABILITY:
            issues.append(f"{diagram_id}: invalid applicability {applicability!r}")
        if status not in DIAGRAM_STATUSES:
            issues.append(f"{diagram_id}: invalid status {status!r}")
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", anchor) is None:
        issues.append(f"{diagram_id}: invalid stable anchor {anchor!r}")
    if modern_contract and status == "CURRENT":
        issues.extend(_presentation_issues(_diagram_section_issues(text, kind, anchor)))
    parsed_ids, binding_issues = _parse_diagram_bindings(
        diagram_id,
        basis_value,
        referenced_value,
        current_ids,
        modern_contract=modern_contract,
        status=status,
    )
    issues.extend(binding_issues)
    return _ParsedDiagramRow(
        diagram_id,
        kind,
        applicability,
        status,
        anchor,
        parsed_ids[0],
        parsed_ids[1],
    ), issues


def _derive_current_diagram_contract(
    text: str,
    architecture: ArchitectureContract,
    requirements: Any,
    coverage: Any,
    project_contract: ProjectDesignContract,
    aws_implementation_decisions: Iterable[AwsImplementationDecision],
    technology_decisions: Mapping[str, TechnologyDecision],
    current_ids: Iterable[str],
    *,
    required: bool,
    grandfathered_schema5: bool,
    grandfathered_pre_aws_diagrams: bool,
    legacy_public_compatibility: bool = False,
) -> tuple[DiagramContract, list[str]]:
    """Validate current typed Mermaid views without making them design authority."""
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

    aws_diagram_is_current = any(
        row[1] == "AWS_IMPLEMENTATION" and row[3] == "CURRENT" for row in table.rows
    )
    modern_contract = (
        False
        if legacy_public_compatibility
        else not grandfathered_pre_aws_diagrams or aws_diagram_is_current
    )
    aws_decisions = tuple(aws_implementation_decisions)
    architecture_id, expected_required, presentation_context = (
        _diagram_contract_context(
            text,
            architecture,
            requirements,
            coverage,
            project_contract,
            aws_decisions,
            technology_decisions,
            current_ids,
            modern_contract=modern_contract,
        )
    )

    records: list[DiagramRecord] = []
    seen_ids: set[str] = set()
    seen_kinds: set[str] = set()
    semantic_rows: list[tuple[str, str]] = []
    stale = False
    incomplete = False
    for raw in table.rows:
        row, row_issues = _parse_diagram_row(
            text,
            raw,
            seen_ids,
            seen_kinds,
            presentation_context.current_ids,
            modern_contract=modern_contract,
            legacy_public_compatibility=legacy_public_compatibility,
        )
        issues.extend(row_issues)
        diagram_id, kind, applicability, status, anchor = (
            row.diagram_id,
            row.kind,
            row.applicability,
            row.status,
            row.anchor,
        )
        basis_ids, referenced_ids = row.basis_ids, row.referenced_ids
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
                relationship_pattern = DIAGRAM_RELATIONSHIP_PATTERNS[
                    legacy_public_compatibility
                ]
                parsed_relationships_with_kind = [
                    (
                        match.group("from"),
                        "SOLID" if match.group("solid") is not None else "DASHED",
                        clean_cell(
                            match.group("solid") or match.groupdict().get("dotted")
                        ),
                        match.group("to"),
                    )
                    for line in body.splitlines()
                    if (match := relationship_pattern.fullmatch(line)) is not None
                ]
                parsed_relationships = [
                    (source, relation, target)
                    for source, _edge_kind, relation, target in parsed_relationships_with_kind
                ]
                if modern_contract and len(parsed_relationships) != len(
                    set(parsed_relationships)
                ):
                    issues.append(
                        f"{diagram_id}: Mermaid relationships must not be duplicated"
                    )
                relationships = tuple(sorted(set(parsed_relationships)))
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
                if modern_contract:
                    semantic_issues, presentation_issues = _modern_diagram_issues(
                        diagram_id,
                        kind,
                        body,
                        basis_ids,
                        referenced_ids,
                        relationships,
                        endpoint_ids,
                        presentation_context,
                    )
                    issues.extend(semantic_issues)
                    issues.extend(_presentation_issues(presentation_issues))
                else:
                    issues.extend(
                        _presentation_issues(_mermaid_claim_issues(diagram_id, body))
                    )
                semantic_payload = _diagram_semantic_payload(
                    kind,
                    basis_ids,
                    referenced_ids,
                    parsed_relationships_with_kind,
                    body,
                    modern_contract=modern_contract,
                )
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
    blocking_issues = [
        issue
        for issue in issues
        if not is_diagram_presentation_issue(issue)
        and not issue.endswith("rendered project diagram is STALE")
    ]
    if not blocking_issues:
        canonical_semantic_rows = {
            False: sorted(semantic_rows),
            True: semantic_rows,
        }[legacy_public_compatibility]
        canonical_bytes = (
            json.dumps(
                canonical_semantic_rows,
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
        if blocking_issues and not incomplete
        else "INCOMPLETE"
        if blocking_issues
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


def derive_diagram_contract(
    text: str,
    architecture: ArchitectureContract,
    requirements: Any,
    coverage: Any,
    *,
    required: bool,
    grandfathered_schema5: bool,
) -> tuple[DiagramContract, list[str]]:
    """Preserve the 1.2.34 public diagram-evaluator compatibility surface."""

    return _derive_current_diagram_contract(
        text,
        architecture,
        requirements,
        coverage,
        ProjectDesignContract(),
        (),
        {},
        (),
        required=required,
        grandfathered_schema5=grandfathered_schema5,
        grandfathered_pre_aws_diagrams=True,
        legacy_public_compatibility=True,
    )
