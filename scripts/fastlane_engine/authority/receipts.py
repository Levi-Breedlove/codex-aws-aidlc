"""Exact Fastlane gate receipt parsing and validation.

Canonical inputs are current PRD bytes and caller-supplied receipt candidates.
Returns exact gate contracts and validation results. Read-only bounded PRD access
is delegated to project observation; this module never writes or grants authority.
Receipt bytes and validation behavior remain compatible with Fastlane 1.2.16.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from ..core.contracts import table_after_heading
from ..core.ids import clean_cell, parse_exact_id_list, unresolved
from ..design.envelope import canonical_envelope_sha256
from ..project_inspection import (
    AUTH_ID,
    DES_ID,
    MAX_GATE_RECEIPT_CHARACTERS,
    PRD_FILE,
    REQ_ID,
    Context,
    bounded_prd_snapshot,
    explicit_human_approver,
    parse_cost_posture,
)


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
    root: Path, report: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the exact receipt proposal for the currently pending owner gate."""

    lifecycle_state = str(report.get("lifecycle_state", ""))
    next_prompt = str(report.get("next_prompt", ""))
    if lifecycle_state == "WAITING_GATE_A" and next_prompt == "INTAKE-20":
        gate = "GATE_A"
        owner_action_kind = "APPROVE_GATE_A"
    elif lifecycle_state == "WAITING_GATE_B" and next_prompt == "DESIGN-20":
        gate = "GATE_B"
        owner_action_kind = "APPROVE_GATE_B"
    else:
        raise ValueError("The project is not waiting for a Gate A or Gate B receipt")

    try:
        basis = report.get("basis")
        if not isinstance(basis, Mapping):
            raise ValueError("Current gate basis is missing")
        text, _ = bounded_prd_snapshot(
            root, clean_cell(basis.get("prd_snapshot_sha256", ""))
        )
        requirements_revision = clean_cell(basis.get("requirements_revision", ""))
        if REQ_ID.fullmatch(requirements_revision) is None:
            raise ValueError("Current requirements revision is invalid")
        if gate == "GATE_A":
            gate_a_agent = table_after_heading(
                text, "### Gate A — agent analysis record"
            )
            gate_a_card = table_after_heading(text, "### Gate A — readiness card")
            assumption_ids = parse_exact_id_list(
                gate_a_agent.get("Proposed assumption IDs required to proceed", ""),
                re.compile(r"ASM-\d+"),
                "Gate A proposed assumptions",
            )
            assumptions = ", ".join(assumption_ids) if assumption_ids else "NONE"
            cost_posture = clean_cell(gate_a_card.get("Cost posture", ""))
            parse_cost_posture(cost_posture)
            fixed_lines = [
                "APPROVE REQUIREMENTS GATE A",
                f"Requirements revision: {requirements_revision}",
                f"Cost posture: {cost_posture}",
                f"Accepted assumptions: {assumptions}",
            ]
            fields = {
                "requirements_revision": requirements_revision,
                "cost_posture": cost_posture,
                "accepted_assumptions": assumptions,
            }
        else:
            design_revision = clean_cell(basis.get("design_revision", ""))
            authorization_id = clean_cell(basis.get("construction_authorization", ""))
            if DES_ID.fullmatch(design_revision) is None:
                raise ValueError("Current design revision is invalid")
            if AUTH_ID.fullmatch(authorization_id) is None:
                raise ValueError("Current construction authorization is invalid")
            envelope_digest = canonical_envelope_sha256(text)
            fixed_lines = [
                "APPROVE PRD AND CONSTRUCTION GATE B",
                f"Requirements revision: {requirements_revision}",
                f"Design revision: {design_revision}",
                f"Construction authorization: {authorization_id}",
                f"Construction envelope SHA-256: {envelope_digest}",
                "Use the proposed construction envelope above.",
            ]
            fields = {
                "requirements_revision": requirements_revision,
                "design_revision": design_revision,
                "construction_authorization": authorization_id,
                "construction_envelope_sha256": envelope_digest,
            }
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("The current pending gate contract is invalid") from exc

    return {
        "gate": gate,
        "lifecycle_state": lifecycle_state,
        "next_prompt": next_prompt,
        "owner_action_kind": owner_action_kind,
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
    ctx: Context,
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
