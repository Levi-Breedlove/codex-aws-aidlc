"""Pure Delivery checkpoint and Gate B execution-basis validation.

Inputs are already-observed TASKS and PRD text plus immutable Design results.
The module returns parsed records or deterministic failures and performs no I/O,
Git invocation, mutation, approval, or authority grant.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ..core.contracts import (
    ContractParseError,
    parse_checkpoint_cells,
    parse_checkpoint_git_receipt_value,
    parse_task_write_set,
    table_after_heading,
)
from ..core.ids import clean_cell, explicit_timestamp, explicit_value
from .models import CheckpointReceiptRow

CHECKPOINT_ID = re.compile(r"CP-\d{4,}")
NON_HUMAN_APPROVER = re.compile(
    r"(?:^|[^a-z0-9])(?:ai|agent|assistant|automated|automation|bot|chatbot|"
    r"chatgpt|codex|gpt(?:-[0-9]+(?:\.[0-9]+)?)?|lambda|llm|model|openai|robot|"
    r"service|system|workflow|aws[ _-]*(?:core|lambda)|pending|placeholder|"
    r"not[ _-]*started)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)


def marked_receipt(text: str, gate: str) -> str:
    """Return one exact marked receipt without interpreting its authority."""

    start = f"<!-- bootstrap:{gate}-receipt:start -->"
    end = f"<!-- bootstrap:{gate}-receipt:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"Expected exactly one marked {gate} receipt block")
    body = text.split(start, 1)[1].split(end, 1)[0].strip()
    match = re.fullmatch(r"```text\s*\n(?P<receipt>.*?)\n```", body, re.DOTALL)
    if match is None:
        raise ValueError(f"Marked {gate} receipt must contain one text fence")
    return match.group("receipt").replace("\r\n", "\n").strip()


def explicit_human_approver(value: str) -> bool:
    """Require a concrete human owner identity."""

    cleaned = clean_cell(value)
    return explicit_value(cleaned) and NON_HUMAN_APPROVER.search(cleaned) is None


def validate_gate_b_execution_binding(
    prd_text: str,
    snapshot: Mapping[str, str],
    design_contract: Any,
    envelope_digest: str,
) -> None:
    """SAFETY: fail closed unless tasks bind the exact current Gate B approval."""

    if design_contract.status != "READY" or design_contract.canonical_sha256 is None:
        raise ValueError(
            "Current PRD design contract is not ready for task execution: "
            + design_contract.status
        )
    envelope = table_after_heading(prd_text, "## 28. Construction envelope")
    observed_hash = clean_cell(envelope.get("Design contract SHA-256", ""))
    if observed_hash != design_contract.canonical_sha256:
        raise ValueError(
            "Gate B design contract hash is stale; rerun DESIGN-10 and obtain "
            "current Gate B approval before task execution"
        )
    document = table_after_heading(prd_text, "## Document status")
    agent = table_after_heading(prd_text, "## 27. Gate B agent review record")
    owner = table_after_heading(prd_text, "## 29. Gate B owner authorization record")
    expected_revisions = {
        "Requirements revision reviewed": snapshot.get("Requirements revision"),
        "Design revision reviewed": snapshot.get("Design revision"),
        "Construction authorization ID reviewed": snapshot.get(
            "Construction authorization"
        ),
    }
    expected_owner_revisions = {
        "Authorized requirements revision": snapshot.get("Requirements revision"),
        "Authorized design revision": snapshot.get("Design revision"),
        "Authorized construction authorization ID": snapshot.get(
            "Construction authorization"
        ),
    }
    binding_valid = (
        document.get("Gate A derived status") == "APPROVED_FOR_DESIGN"
        and document.get("Gate B derived status") == "APPROVED_FOR_CONSTRUCTION"
        and all(agent.get(key) == value for key, value in expected_revisions.items())
        and agent.get("Construction envelope SHA-256 reviewed") == envelope_digest
        and agent.get("Agent recommendation") == "READY_FOR_CONSTRUCTION_APPROVAL"
        and all(
            agent.get(key) == "NONE"
            for key in (
                "PRD completeness gaps",
                "Requirement-to-design-and-test traceability gaps",
                "Unresolved risk or preservation gaps",
            )
        )
        and owner.get("Owner decision") == "APPROVED"
        and all(
            owner.get(key) == value for key, value in expected_owner_revisions.items()
        )
        and owner.get("Authorized construction envelope SHA-256") == envelope_digest
        and owner.get("Derived Gate B state") == "APPROVED_FOR_CONSTRUCTION"
        and owner.get("Verbatim owner receipt") == "RECORDED_BELOW"
        and explicit_human_approver(owner.get("Approver", ""))
        and explicit_timestamp(owner.get("Authorization provided at", ""))
        and explicit_value(owner.get("Authorization source", ""))
    )
    expected_receipt = "\n".join(
        [
            "APPROVE PRD AND CONSTRUCTION GATE B",
            f"Requirements revision: {snapshot.get('Requirements revision')}",
            f"Design revision: {snapshot.get('Design revision')}",
            "Construction authorization: "
            + str(snapshot.get("Construction authorization")),
            f"Construction envelope SHA-256: {envelope_digest}",
            "Use the proposed construction envelope above.",
            f"Approver: {owner.get('Approver', '')}",
        ]
    )
    try:
        receipt_matches = marked_receipt(prd_text, "gate-b") == expected_receipt
    except ValueError:
        receipt_matches = False
    if not binding_valid or not receipt_matches:
        raise ValueError(
            "Gate B approval binding is stale; rerun DESIGN-20 and obtain current "
            "owner approval before task execution"
        )


def external_target_contains(allowed: str, requested: str) -> bool:
    allowed = allowed.casefold()
    requested = requested.casefold()
    if allowed == requested:
        return True
    return any(
        requested.startswith(allowed + separator) for separator in ("/", ":", "#")
    )


def parse_checkpoint_rows(
    tasks_text: str,
    *,
    task_surface_compatibility: bool = False,
) -> list[CheckpointReceiptRow]:
    """CANONICALIZATION: parse uniquely ordered checkpoint receipt rows."""

    try:
        parsed_rows = parse_checkpoint_cells(tasks_text)
    except ContractParseError as exc:
        messages = {
            "section_count": "TASKS requires exactly one Checkpoints and resume section",
            "header_count": "TASKS requires one exact checkpoint table header",
            "separator_missing": "TASKS checkpoint table separator is invalid",
            "separator_invalid": "TASKS checkpoint table separator is invalid",
            "row_width": "TASKS checkpoint rows must have exactly eight cells",
            "discontiguous_rows": "TASKS checkpoint rows must form one contiguous table",
        }
        raise ValueError(
            messages.get(exc.reason, "TASKS checkpoint table is invalid")
        ) from exc
    rows: list[CheckpointReceiptRow] = []
    for cells in parsed_rows:
        cleaned = [clean_cell(cell) for cell in cells]
        if cleaned[0] == "NONE":
            continue
        if CHECKPOINT_ID.fullmatch(cleaned[0]) is None:
            raise ValueError(f"Invalid checkpoint table ID: {cleaned[0]!r}")
        rows.append(CheckpointReceiptRow(*cleaned))
    identifiers = [row.checkpoint_id for row in rows]
    if len(identifiers) != len(set(identifiers)):
        duplicates = sorted(
            identifier
            for identifier in set(identifiers)
            if identifiers.count(identifier) > 1
        )
        raise ValueError(
            "Checkpoint IDs may not be reused: " + ", ".join(duplicates)
            if task_surface_compatibility
            else "Checkpoint table IDs must be unique"
        )
    ordinals = [int(identifier.split("-", 1)[1]) for identifier in identifiers]
    if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
        raise ValueError(
            "Checkpoint IDs must be strictly increasing in table order"
            if task_surface_compatibility
            else "Checkpoint table IDs must be strictly monotonic"
        )
    return rows


def parse_checkpoint_git_receipt(
    tasks_text: str,
    checkpoint_id: str,
) -> tuple[str, list[str]]:
    """CANONICALIZATION: parse the exact checkpoint Git receipt grammar."""

    rows = parse_checkpoint_rows(tasks_text)
    matches = [row for row in rows if row.checkpoint_id == checkpoint_id]
    if not rows or len(matches) != 1 or rows[-1].checkpoint_id != checkpoint_id:
        raise ValueError(f"{checkpoint_id}: must be the unique newest checkpoint row")
    try:
        commit, dirty_value = parse_checkpoint_git_receipt_value(
            matches[0].commit_and_dirty
        )
    except ContractParseError as exc:
        raise ValueError(
            f"{checkpoint_id}: commit receipt must use Commit: <sha>; Dirty: <paths|NONE>"
        ) from exc
    dirty = (
        []
        if dirty_value == "NONE"
        else parse_task_write_set(
            dirty_value, f"{checkpoint_id} checkpoint Dirty paths"
        )
    )
    return commit, dirty


__all__ = (
    "explicit_human_approver",
    "external_target_contains",
    "marked_receipt",
    "parse_checkpoint_git_receipt",
    "parse_checkpoint_rows",
    "validate_gate_b_execution_binding",
)
