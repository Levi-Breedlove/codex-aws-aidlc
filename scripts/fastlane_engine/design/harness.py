"""Layered Harness selection and evidence-destination contracts.

Canonical inputs are caller-observed project records. Outputs are immutable
Design projections or ordered validation issues. This module performs no I/O,
routing, mutation, approval, authorization, or owner-facing rendering.
"""

from __future__ import annotations


import hashlib
import re

from ..core.contracts import contract_table_after_heading
from ..core.ids import STABLE_CONTRACT_ID, canonical_id_list, clean_cell, unresolved
from .models import HarnessContract, HarnessRow
from .support import HARNESS_LAYERS, valid_property_execution_command


HARNESS_HEADING = "### Gate B Harness Profile"


HARNESS_HEADERS = (
    "Harness ID",
    "Layer",
    "Selected check or tool",
    "Trigger",
    "Basis IDs",
    "Exact command or API",
    "Evidence destination",
    "Required or conditional status",
)


HARNESS_ID = re.compile(r"HARNESS-\d{3,}")


HARNESS_EVIDENCE_DESTINATION = "docs/project/VERIFY.md#harness-execution-evidence"


def harness_status_parts(value: str) -> tuple[str, str | None]:
    cleaned = clean_cell(value)
    if cleaned == "REQUIRED":
        return "REQUIRED", None
    for prefix in ("CONDITIONAL", "NOT_APPLICABLE"):
        if not cleaned.startswith(prefix):
            continue
        suffix = cleaned[len(prefix) :].strip()
        if suffix.startswith("—"):
            suffix = suffix[1:].strip()
        elif suffix.startswith("-"):
            suffix = suffix[1:].strip()
        if suffix and not unresolved(suffix):
            return prefix, suffix
    return "INVALID", None


def derive_harness_contract(
    text: str,
    allowed_basis_ids: set[str],
    *,
    required: bool,
    grandfather_approved_v1: bool,
) -> tuple[HarnessContract, list[str]]:
    """SAFETY: Validate the complete Gate B Harness Profile before readiness."""

    issues: list[str] = []
    try:
        table = contract_table_after_heading(text, HARNESS_HEADING, HARNESS_HEADERS)
    except ValueError as exc:
        table = None
        issues.append(f"Harness Profile: {exc}")
    if table is None:
        if grandfather_approved_v1:
            return (
                HarnessContract(
                    status="GRANDFATHERED_V1",
                    grandfathered_v1=True,
                ),
                [],
            )
        return HarnessContract(), [f"Missing {HARNESS_HEADING}"]

    rows: list[HarnessRow] = []
    required_ids: list[str] = []
    seen: set[str] = set()
    for raw in table.rows:
        row = HarnessRow(*raw)
        rows.append(row)
        if HARNESS_ID.fullmatch(row.harness_id) is None:
            issues.append(f"{row.harness_id}: invalid Harness ID")
        elif row.harness_id in seen:
            issues.append(f"{row.harness_id}: duplicate Harness ID")
        seen.add(row.harness_id)
        if row.layer not in HARNESS_LAYERS:
            issues.append(f"{row.harness_id}: invalid Harness layer {row.layer!r}")
        if unresolved(row.trigger):
            issues.append(f"{row.harness_id}: Trigger is unresolved")
        try:
            basis = canonical_id_list(
                row.basis_ids,
                STABLE_CONTRACT_ID,
                f"{row.harness_id} Basis IDs",
            )
        except ValueError as exc:
            issues.append(str(exc))
            basis = []
        unknown = sorted(set(basis) - allowed_basis_ids)
        if unknown:
            issues.append(
                f"{row.harness_id}: Basis IDs are not current design IDs: "
                + ", ".join(unknown)
            )

        status, reason = harness_status_parts(row.requirement_status)
        if status == "INVALID":
            issues.append(
                f"{row.harness_id}: status must be REQUIRED, CONDITIONAL — "
                "<trigger>, or NOT_APPLICABLE — <reason>"
            )
            continue
        if status == "NOT_APPLICABLE":
            if any(
                clean_cell(value) != "NOT_APPLICABLE"
                for value in (
                    row.selected_check,
                    row.exact_command,
                    row.evidence_destination,
                )
            ):
                issues.append(
                    f"{row.harness_id}: NOT_APPLICABLE rows must use "
                    "NOT_APPLICABLE for check, command/API, and evidence destination"
                )
            if reason is None:
                issues.append(
                    f"{row.harness_id}: NOT_APPLICABLE requires a concrete reason"
                )
            continue

        if unresolved(row.selected_check):
            issues.append(f"{row.harness_id}: Selected check or tool is unresolved")
        if not valid_property_execution_command(row.exact_command):
            issues.append(
                f"{row.harness_id}: Exact command or API must be one concrete command"
            )
        if row.evidence_destination != HARNESS_EVIDENCE_DESTINATION:
            issues.append(
                f"{row.harness_id}: Evidence destination must be exactly "
                f"{HARNESS_EVIDENCE_DESTINATION}"
            )
        if status == "CONDITIONAL":
            if reason is None:
                issues.append(
                    f"{row.harness_id}: CONDITIONAL requires a concrete trigger"
                )
            if required:
                issues.append(
                    f"{row.harness_id}: CONDITIONAL must resolve to REQUIRED or "
                    "NOT_APPLICABLE before Gate B"
                )
        else:
            required_ids.append(row.harness_id)

    canonical = table.canonical_bytes
    digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return (
        HarnessContract(
            schema_version=2,
            status="READY" if not issues else "BLOCKED",
            rows=tuple(rows),
            required_ids=tuple(required_ids),
            canonical_sha256=digest,
            canonical_bytes=canonical,
        ),
        issues,
    )
