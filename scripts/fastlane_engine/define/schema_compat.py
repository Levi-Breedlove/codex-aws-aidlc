"""Requirements schema selection and canonical result construction."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from ..core.contracts import (
    ContractTable,
    contract_table_after_heading,
    markdown_tables,
    without_fenced_code,
)
from ..core.ids import clean_cell
from .models import RequirementsChangeLineage, RequirementsContract
from .requirements_v15 import Requirements15Extension


SchemaSelection = tuple[
    dict[str, str],
    list[tuple[str, ...]],
    dict[str, str],
    list[str],
    bool,
    bool,
    RequirementsContract | None,
    list[tuple[str, str]],
]


def _present_current_headers(
    text: str,
    observed_headers: set[tuple[str, ...]],
    current_header_map: Mapping[tuple[str, ...], str],
) -> set[tuple[str, ...]]:
    present = observed_headers & set(current_header_map)
    for headers, heading in current_header_map.items():
        try:
            if contract_table_after_heading(text, heading, headers) is not None:
                present.add(headers)
        except ValueError:
            pass
    return present


def _contract_surface_present(
    structural_text: str,
    observed_headers: set[tuple[str, ...]],
    header_map: Mapping[tuple[str, ...], str],
    headers: set[tuple[str, ...]],
) -> bool:
    return bool(
        observed_headers & headers
        or any(
            re.search(
                rf"^{re.escape(header_map[item])}[ \t]*$",
                structural_text,
                re.MULTILINE,
            )
            for item in headers
        )
        or any(
            re.search(
                r"^\|[ \t]*"
                + r"[ \t]*\|[ \t]*".join(re.escape(cell) for cell in item)
                + r"[ \t]*\|[ \t]*$",
                structural_text,
                re.MULTILINE,
            )
            for item in headers
        )
    )


def _legacy_contract(
    text: str,
    document: Mapping[str, str],
    approved_ids: Sequence[str],
    legacy_headers: set[tuple[str, ...]],
) -> RequirementsContract:
    rows = [
        tuple(clean_cell(cell) for cell in row)
        for table in markdown_tables(text)
        if table and tuple(table[0]) in legacy_headers
        for row in table[2:]
    ]
    canonical_bytes = (
        b"PROJECT_CONTRACT_SCHEMA: 1.2\n"
        + json.dumps(
            (clean_cell(document.get("Current requirements revision", "")), rows),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    return RequirementsContract(
        schema_version="1.2",
        status="GRANDFATHERED",
        requirement_ids=tuple(sorted(approved_ids)),
        acceptance_ids=tuple(f"AC-{item}" for item in sorted(approved_ids)),
        canonical_sha256="sha256:" + hashlib.sha256(canonical_bytes).hexdigest(),
        canonical_bytes=canonical_bytes,
        grandfathered_approved_gate_a=True,
    )


def _exact_legacy_ids(
    project_schema: str,
    legacy_ids: Sequence[str],
    observed_headers: set[tuple[str, ...]],
    legacy_headers: set[tuple[str, ...]],
    current_present: set[tuple[str, ...]],
    stable_contract_id: re.Pattern[str],
) -> list[str]:
    real_ids = [
        identifier
        for identifier in legacy_ids
        if stable_contract_id.fullmatch(identifier)
    ]
    exact = bool(
        not project_schema
        and real_ids
        and len(real_ids) == len(legacy_ids)
        and len(real_ids) == len(set(real_ids))
        and len(observed_headers & legacy_headers) == 1
        and not current_present
    )
    return real_ids if exact else []


def _migration_selection(
    document: dict[str, str],
    requirement_rows: list[tuple[str, ...]],
    acceptance_by_requirement: dict[str, str],
    legacy_ids: list[str],
    current_header_map: Mapping[tuple[str, ...], str],
    current_present: set[tuple[str, ...]],
    current_schema: str,
) -> SchemaSelection:
    migration_targets = [f"Project contract schema {current_schema}"]
    if not clean_cell(document.get("Project completion target", "")):
        migration_targets.append("Project completion target")
    migration_targets.extend(
        label
        for headers, label in current_header_map.items()
        if headers not in current_present
    )
    contract = RequirementsContract(
        status="MIGRATION_REQUIRED", missing_records=tuple(migration_targets)
    )
    issue = (
        "PROJECT_CONTRACT_MIGRATION_REQUIRED",
        f"Project contract schema {current_schema} is required before Gate A readiness; "
        "migrate only the listed generated records without inventing owner facts: "
        + ", ".join(migration_targets),
    )
    return (
        document,
        requirement_rows,
        acceptance_by_requirement,
        legacy_ids,
        False,
        False,
        contract,
        [issue],
    )


def _requirements_surfaces(
    text,
    document,
    observed_headers,
    current_header_map,
    schema_14_headers,
    extension_headers,
    detail_headers,
):
    structural_text = without_fenced_code(text)
    schema_14_present = _contract_surface_present(
        structural_text, observed_headers, current_header_map, schema_14_headers
    )
    detail_present = _contract_surface_present(
        structural_text, observed_headers, current_header_map, detail_headers
    )
    extension_present = bool(
        detail_present
        or clean_cell(document.get("Project completion target", ""))
        or _contract_surface_present(
            structural_text, observed_headers, current_header_map, extension_headers
        )
    )
    return schema_14_present, detail_present, extension_present


def _approved_schema_flags(
    project_schema,
    current_schema,
    grandfather_current_gate_a,
    schema_14_present,
    extension_present,
    detail_present,
):
    grandfather_schema_13 = bool(
        project_schema == "1.3"
        and grandfather_current_gate_a
        and not schema_14_present
        and not extension_present
    )
    compatible_schema_14 = bool(
        project_schema == "1.4" and grandfather_current_gate_a and not extension_present
    )
    compatible = (
        project_schema in {current_schema}
        or (
            project_schema == "1.5"
            and grandfather_current_gate_a
            and not detail_present
        )
        or compatible_schema_14
        or grandfather_schema_13
    )
    return compatible, grandfather_schema_13, compatible_schema_14


def select_requirements_schema(
    text: str,
    *,
    required: bool,
    grandfather_current_gate_a: bool,
    document: dict[str, str],
    document_issues: list[tuple[str, str]],
    requirement_rows: list[tuple[str, ...]],
    acceptance_by_requirement: dict[str, str],
    legacy_ids: list[str],
    current_schema: str,
    current_header_map: Mapping[tuple[str, ...], str],
    schema_14_headers: set[tuple[str, ...]],
    extension_headers: set[tuple[str, ...]],
    detail_headers: set[tuple[str, ...]],
    legacy_headers: set[tuple[str, ...]],
    stable_contract_id: re.Pattern[str],
) -> SchemaSelection:
    """Select current, approved compatibility, or fail-closed migration state."""

    project_schema = clean_cell(document.get("Project contract schema", ""))
    observed_headers = {tuple(table[0]) for table in markdown_tables(text) if table}
    current_present = _present_current_headers(
        text, observed_headers, current_header_map
    )
    schema_14_present, detail_present, extension_present = _requirements_surfaces(
        text,
        document,
        observed_headers,
        current_header_map,
        schema_14_headers,
        extension_headers,
        detail_headers,
    )
    compatible, grandfather_schema_13, compatible_schema_14 = _approved_schema_flags(
        project_schema,
        current_schema,
        grandfather_current_gate_a,
        schema_14_present,
        extension_present,
        detail_present,
    )
    if compatible:
        return (
            document,
            requirement_rows,
            acceptance_by_requirement,
            legacy_ids,
            grandfather_schema_13,
            compatible_schema_14,
            None,
            document_issues,
        )

    exact_legacy_ids = _exact_legacy_ids(
        project_schema,
        legacy_ids,
        observed_headers,
        legacy_headers,
        current_present,
        stable_contract_id,
    )
    if (
        grandfather_current_gate_a
        and exact_legacy_ids
        and not schema_14_present
        and not extension_present
    ):
        return (
            document,
            requirement_rows,
            acceptance_by_requirement,
            legacy_ids,
            False,
            False,
            _legacy_contract(text, document, exact_legacy_ids, legacy_headers),
            [],
        )
    if not required and project_schema not in {"1.3", "1.4", "1.5", "1.6"}:
        return (
            document,
            requirement_rows,
            acceptance_by_requirement,
            legacy_ids,
            False,
            False,
            RequirementsContract(status="UNINITIALIZED"),
            [],
        )

    return _migration_selection(
        document,
        requirement_rows,
        acceptance_by_requirement,
        legacy_ids,
        current_header_map,
        current_present,
        current_schema,
    )


def _canonical_requirements_bytes(
    *,
    schema_version: str,
    requirement_rows: list[tuple[str, ...]],
    contract_tables: Sequence[ContractTable | None],
    extension: Requirements15Extension,
    grandfather_schema_13: bool,
    compatible_schema_14: bool,
) -> tuple[bytes | None, str | None]:
    extension_complete = bool(
        grandfather_schema_13
        or compatible_schema_14
        or len(extension.canonical_tables) == 4
    )
    if (
        not all(table is not None for table in contract_tables)
        or not extension_complete
    ):
        return None, None
    requirement_payload = (
        json.dumps(requirement_rows, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )
    target_bytes = (
        b""
        if grandfather_schema_13 or compatible_schema_14
        else f"PROJECT_COMPLETION_TARGET: {extension.completion_target or 'INVALID'}\n".encode(
            "utf-8"
        )
    )
    canonical_bytes = (
        schema_version.encode("utf-8")
        + b"\n"
        + target_bytes
        + requirement_payload
        + b"".join(
            table.canonical_bytes for table in contract_tables if table is not None
        )
        + b"".join(table.canonical_bytes for table in extension.canonical_tables)
    )
    return canonical_bytes, "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()


def finalize_requirements_contract(
    *,
    requirement_rows: list[tuple[str, ...]],
    contract_tables: Sequence[ContractTable | None],
    extension: Requirements15Extension,
    grandfather_schema_13: bool,
    compatible_schema_14: bool,
    issues: list[tuple[str, str]],
    actor_ids: Sequence[str],
    journey_ids: Sequence[str],
    acceptance_by_requirement: Mapping[str, str],
    requirement_ids: set[str],
    use_case_ids: Sequence[str],
    business_rule_ids: Sequence[str],
    rich_use_case_triggers: set[str],
    change_lineage: RequirementsChangeLineage | None,
    assumptions: Sequence[Any],
    missing_records: Sequence[str],
    presentation_labels: Sequence[tuple[str, str]],
    current_schema: str,
) -> RequirementsContract:
    """Build the immutable requirements result after ordered validation."""

    schema_version = (
        "1.3"
        if grandfather_schema_13
        else "1.4"
        if compatible_schema_14
        else current_schema
    )
    canonical_bytes, canonical_sha256 = _canonical_requirements_bytes(
        schema_version=schema_version,
        requirement_rows=requirement_rows,
        contract_tables=contract_tables,
        extension=extension,
        grandfather_schema_13=grandfather_schema_13,
        compatible_schema_14=compatible_schema_14,
    )
    return RequirementsContract(
        schema_version=schema_version,
        status=(
            "GRANDFATHERED"
            if grandfather_schema_13 and not issues
            else "READY"
            if not issues
            else "BLOCKED"
        ),
        completion_target=extension.completion_target,
        actor_ids=tuple(actor_ids),
        journey_ids=tuple(journey_ids),
        acceptance_ids=tuple(
            acceptance_by_requirement.get(item, "") for item in sorted(requirement_ids)
        ),
        use_case_ids=tuple(use_case_ids),
        business_rule_ids=tuple(business_rule_ids),
        requirement_ids=tuple(sorted(requirement_ids)),
        rich_use_case_triggers=tuple(sorted(rich_use_case_triggers)),
        change_lineage=change_lineage,
        assumptions=tuple(assumptions),
        outcome_metrics=extension.outcome_metrics,
        datasets=extension.datasets,
        external_obligations=extension.external_obligations,
        cross_cutting_risks=extension.cross_cutting_risks,
        missing_records=tuple(dict.fromkeys(missing_records)),
        canonical_sha256=canonical_sha256,
        grandfathered_approved_gate_a=grandfather_schema_13,
        approved_schema_14_compatibility=compatible_schema_14,
        presentation_labels=tuple(presentation_labels),
        canonical_bytes=canonical_bytes,
    )


__all__ = (
    "SchemaSelection",
    "finalize_requirements_contract",
    "select_requirements_schema",
)
