"""Exact Fastlane gate receipt parsing and validation.

Canonical inputs are current PRD bytes and caller-supplied receipt candidates.
Returns exact gate contracts and validation results. Read-only bounded PRD access
is delegated to project observation; this module never writes or grants authority.
Receipt bytes and validation behavior remain compatible with Fastlane 1.2.16.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Protocol

from ..core.ids import clean_cell, unresolved
from .models import PendingGateReceiptInput, explicit_human_approver

MAX_GATE_RECEIPT_CHARACTERS = 4096
PRD_FILE = "docs/project/PRD.md"


class _DiagnosticSink(Protocol):
    """Minimum compatibility surface needed by exact selection validation."""

    def error(self, code: str, message: str, path: str | None = None) -> None: ...


def marked_receipt(text: str, gate: str) -> str:
    start = f"<!-- bootstrap:{gate}-receipt:start -->"
    end = f"<!-- bootstrap:{gate}-receipt:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"Expected exactly one marked {gate} receipt block")
    body = text.split(start, 1)[1].split(end, 1)[0].strip()
    match = re.fullmatch(r"```text\s*\n(?P<receipt>.*?)\n```", body, re.DOTALL)
    if match is None:
        raise ValueError(f"Marked {gate} receipt must contain one text fence")
    return match.group("receipt").replace("\r\n", "\n").strip()


def current_gate_receipt_contract(
    receipt_input: PendingGateReceiptInput,
) -> dict[str, Any]:
    """Return the exact receipt proposal from normalized current gate facts."""

    if receipt_input.gate == "GATE_A":
        assumptions = (
            ", ".join(receipt_input.accepted_assumptions)
            if receipt_input.accepted_assumptions
            else "NONE"
        )
        fixed_lines = [
            "APPROVE REQUIREMENTS GATE A",
            f"Requirements revision: {receipt_input.requirements_revision}",
            f"Cost posture: {receipt_input.cost_posture}",
            f"Accepted assumptions: {assumptions}",
        ]
        fields = {
            "requirements_revision": receipt_input.requirements_revision,
            "cost_posture": receipt_input.cost_posture,
            "accepted_assumptions": assumptions,
        }
    elif receipt_input.gate == "GATE_B":
        fixed_lines = [
            "APPROVE PRD AND CONSTRUCTION GATE B",
            f"Requirements revision: {receipt_input.requirements_revision}",
            f"Design revision: {receipt_input.design_revision}",
            f"Construction authorization: {receipt_input.construction_authorization}",
            "Construction envelope SHA-256: "
            f"{receipt_input.construction_envelope_sha256}",
            "Use the proposed construction envelope above.",
        ]
        fields = {
            "requirements_revision": receipt_input.requirements_revision,
            "design_revision": receipt_input.design_revision,
            "construction_authorization": receipt_input.construction_authorization,
            "construction_envelope_sha256": (
                receipt_input.construction_envelope_sha256
            ),
        }
    else:
        raise ValueError("The current pending gate contract is invalid")

    return {
        "gate": receipt_input.gate,
        "lifecycle_state": receipt_input.lifecycle_state,
        "next_prompt": receipt_input.next_prompt,
        "owner_action_kind": receipt_input.owner_action_kind,
        "fixed_lines": fixed_lines,
        "fields": fields,
        "expected_receipt": "\n".join([*fixed_lines, "Approver: <name/handle>"]),
    }


def validate_gate_receipt_candidate(
    candidate: str, contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one owner receipt without writing or echoing rejected content."""

    common = {
        "schema_version": 1,
        "gate": contract["gate"],
        "lifecycle_state": contract["lifecycle_state"],
        "next_prompt": contract["next_prompt"],
        "owner_action_kind": contract["owner_action_kind"],
        "formal_receipt_required": True,
        "project_state_changed": False,
        "expected_receipt": contract["expected_receipt"],
    }

    def rejected(code: str, message: str) -> dict[str, Any]:
        return {
            **common,
            "status": "FAIL",
            "candidate_accepted": False,
            "errors": [{"code": code, "message": message}],
        }

    if len(candidate) > MAX_GATE_RECEIPT_CHARACTERS:
        return rejected(
            "GATE_RECEIPT_TOO_LONG",
            "The owner receipt exceeds the bounded receipt length",
        )
    normalized = re.sub(r"\r+\n", "\n", candidate).replace("\r", "\n").strip()
    if not normalized or any(
        ord(character) < 32 and character != "\n" for character in normalized
    ):
        return rejected(
            "GATE_RECEIPT_FORMAT_INVALID",
            "The owner receipt contains invalid or missing text",
        )
    lines = normalized.split("\n")
    fixed_lines = contract.get("fixed_lines")
    if not isinstance(fixed_lines, list) or not all(
        isinstance(line, str) for line in fixed_lines
    ):
        return rejected(
            "GATE_RECEIPT_CONTRACT_INVALID",
            "The current gate receipt contract is invalid",
        )
    if len(lines) != len(fixed_lines) + 1:
        return rejected(
            "GATE_RECEIPT_FORMAT_INVALID",
            "The owner receipt must contain the complete exact ordered block",
        )
    if lines[:-1] != fixed_lines:
        return rejected(
            "GATE_RECEIPT_BASIS_MISMATCH",
            "The owner receipt does not match the current exact gate proposal",
        )
    approver_prefix = "Approver: "
    if not lines[-1].startswith(approver_prefix):
        return rejected(
            "GATE_RECEIPT_FORMAT_INVALID",
            "The final owner receipt line must be the Approver field",
        )
    approver = lines[-1][len(approver_prefix) :]
    if not explicit_human_approver(approver):
        return rejected(
            "GATE_RECEIPT_APPROVER_INVALID",
            "The approver must be an explicit human owner identity",
        )
    return {
        **common,
        "status": "PASS",
        "candidate_accepted": True,
        "normalized_receipt": normalized,
        "fields": {**dict(contract.get("fields", {})), "approver": approver},
        "errors": [],
    }


def exact_selection(
    ctx: _DiagnosticSink,
    value: str,
    allowed: set[str],
    code: str,
    field_name: str,
    *,
    allow_unselected: bool,
) -> str | None:
    cleaned = clean_cell(value)
    if cleaned in allowed:
        return cleaned
    if allow_unselected and any(item in cleaned for item in allowed):
        return None
    ctx.error(code, f"{field_name} must be exactly one of {sorted(allowed)}", PRD_FILE)
    return None


def unselected_selection(value: str, allowed: set[str]) -> bool:
    """Return whether a selection cell still represents an unanswered choice."""

    cleaned = clean_cell(value)
    if unresolved(cleaned):
        return True
    parts = [part.strip() for part in str(value).strip().split("/")]
    if len(parts) <= 1:
        return False
    choices: list[str] = []
    for part in parts:
        match = re.fullmatch(r"`?([a-z][a-z0-9-]*)`?", part)
        if match is None:
            return False
        choices.append(match.group(1))
    return len(choices) == len(allowed) and set(choices) == allowed
