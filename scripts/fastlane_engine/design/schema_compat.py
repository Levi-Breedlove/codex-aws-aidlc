"""Pure project-Design schema selection and frozen compatibility handling."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re
from typing import Any

from ..core.contracts import markdown_tables, table_after_heading, without_fenced_code
from ..core.ids import clean_cell
from .models import ProjectDesignContract


@dataclass(frozen=True)
class ProjectSchemaCompatibility:
    """Describe current records and the exact frozen pre-current shapes."""

    current_schema: str
    diagram_heading: str
    diagram_headers: tuple[str, ...]
    partial_upgrade_headings: tuple[str, ...]
    partial_upgrade_headers: tuple[tuple[str, ...], ...]
    current_headers: tuple[tuple[str, ...], ...]
    legacy_interface_headers: tuple[str, ...]
    interface_id: re.Pattern[str]
    pre_schema_seven_fields: tuple[str, ...]
    schema_five_only_headings: tuple[str, ...]
    legacy_required_ids: tuple[re.Pattern[str], ...]
    migration_records: tuple[str, ...]
    migration_issue: str


SchemaState = tuple[
    dict[str, str],
    bool,
    bool,
    bool,
    list[str],
    tuple[ProjectDesignContract, list[str]] | None,
]


def _has_heading(structural_text: str, heading: str) -> bool:
    return bool(
        re.search(rf"^{re.escape(heading)}[ \t]*$", structural_text, re.MULTILINE)
    )


def _has_header(structural_text: str, headers: tuple[str, ...]) -> bool:
    pattern = (
        r"^\|[ \t]*"
        + r"[ \t]*\|[ \t]*".join(re.escape(cell) for cell in headers)
        + r"[ \t]*\|[ \t]*$"
    )
    return re.search(pattern, structural_text, re.MULTILINE) is not None


def _document_status(text: str, required: bool) -> tuple[dict[str, str], list[str]]:
    try:
        return table_after_heading(text, "## Document status"), []
    except ValueError as exc:
        return {}, [str(exc)] if required else []


def _schema_flags(
    design_schema: str,
    structural_text: str,
    grandfather_approved: bool,
    compatibility: ProjectSchemaCompatibility,
) -> tuple[bool, bool, bool]:
    observed_headers = {
        tuple(table[0]) for table in markdown_tables(structural_text) if table
    }
    partial_upgrade = bool(
        observed_headers & set(compatibility.partial_upgrade_headers)
        or any(
            _has_header(structural_text, headers)
            for headers in compatibility.partial_upgrade_headers
        )
        or any(
            _has_heading(structural_text, heading)
            for heading in compatibility.partial_upgrade_headings
        )
    )
    diagram_present = bool(
        _has_heading(structural_text, compatibility.diagram_heading)
        or _has_header(structural_text, compatibility.diagram_headers)
        or compatibility.diagram_headers in observed_headers
    )
    pre_schema_seven_present = any(
        re.search(
            rf"^\|[ \t]*{re.escape(field)}[ \t]*\|",
            structural_text,
            re.MULTILINE,
        )
        for field in compatibility.pre_schema_seven_fields
    )
    grandfather_schema_6 = bool(
        design_schema == "6"
        and grandfather_approved
        and not partial_upgrade
        and not pre_schema_seven_present
    )
    grandfather_schema_5 = bool(
        design_schema == "5"
        and grandfather_approved
        and not diagram_present
        and not partial_upgrade
        and not pre_schema_seven_present
    )
    approved_schema_7 = bool(
        design_schema == "7" and grandfather_approved and not partial_upgrade
    )
    return grandfather_schema_5, grandfather_schema_6, approved_schema_7


def _legacy_interface_rows(
    observed_tables: tuple[tuple[tuple[str, ...], ...], ...],
    headers: tuple[str, ...],
) -> tuple[tuple[tuple[str, ...], ...], tuple[str, ...]]:
    tables = tuple(table for table in observed_tables if tuple(table[0]) == headers)
    identifiers = tuple(
        clean_cell(row[0])
        for table in tables
        for row in table[2:]
        if len(row) == len(headers)
    )
    return tables, identifiers


def _exact_legacy_shape(
    text: str,
    structural_text: str,
    legacy_design_ids: set[str],
    compatibility: ProjectSchemaCompatibility,
) -> bool:
    observed_tables = tuple(
        tuple(tuple(row) for row in table) for table in markdown_tables(text) if table
    )
    observed_headers = {tuple(table[0]) for table in observed_tables}
    legacy_tables, legacy_ids = _legacy_interface_rows(
        observed_tables, compatibility.legacy_interface_headers
    )
    return bool(
        len(legacy_tables) == 1
        and legacy_ids
        and all(compatibility.interface_id.fullmatch(item) for item in legacy_ids)
        and not (observed_headers & set(compatibility.current_headers))
        and not (observed_headers & set(compatibility.partial_upgrade_headers))
        and not any(
            _has_header(structural_text, headers)
            for headers in compatibility.partial_upgrade_headers
        )
        and not any(
            re.search(
                rf"^\|[ \t]*{re.escape(field)}[ \t]*\|",
                structural_text,
                re.MULTILINE,
            )
            for field in compatibility.pre_schema_seven_fields
        )
        and not any(
            _has_heading(structural_text, heading)
            for heading in (
                *compatibility.schema_five_only_headings,
                *compatibility.partial_upgrade_headings,
            )
        )
        and all(
            any(pattern.fullmatch(item) for item in legacy_design_ids)
            for pattern in compatibility.legacy_required_ids
        )
    )


def project_schema_state(
    text: str,
    legacy_design_ids: set[str],
    *,
    required: bool,
    grandfather_approved: bool,
    compatibility: ProjectSchemaCompatibility,
) -> SchemaState:
    """Select current, exact grandfathered, or migration-required semantics."""

    document, issues = _document_status(text, required)
    design_schema = clean_cell(document.get("Project design contract schema", ""))
    structural_text = without_fenced_code(text)
    schema_5, schema_6, approved_schema_7 = _schema_flags(
        design_schema, structural_text, grandfather_approved, compatibility
    )
    if design_schema == compatibility.current_schema or any(
        (schema_5, schema_6, approved_schema_7)
    ):
        return document, schema_5, schema_6, approved_schema_7, issues, None

    if (
        grandfather_approved
        and not design_schema
        and _exact_legacy_shape(text, structural_text, legacy_design_ids, compatibility)
    ):
        return (
            document,
            False,
            False,
            False,
            [],
            (
                ProjectDesignContract(
                    schema_version=4, status="GRANDFATHERED", grandfathered_v4=True
                ),
                [],
            ),
        )
    if not required:
        return (
            document,
            False,
            False,
            False,
            [],
            (ProjectDesignContract(status="UNINITIALIZED"), []),
        )
    return (
        document,
        False,
        False,
        False,
        [],
        (
            ProjectDesignContract(
                status="MIGRATION_REQUIRED",
                missing_records=compatibility.migration_records,
            ),
            [compatibility.migration_issue],
        ),
    )


def _aggregate_design_ready(
    *,
    technology_table: Any,
    applicability_table: Any,
    definition_table: Any,
    execution_table: Any,
    architecture: Any,
    harness: Any,
    change_impact: Any,
    project_contract: ProjectDesignContract,
    example_table: Any,
    diagram_contract: Any,
    design_support_bytes: bytes | None,
    bind_design_support: bool,
    grandfather_approved: bool,
) -> bool:
    required_tables = (
        technology_table,
        applicability_table,
        definition_table,
        execution_table,
    )
    return bool(
        all(table is not None for table in required_tables)
        and (harness.canonical_bytes is not None or harness.grandfathered_v1)
        and (change_impact.canonical_bytes is not None or grandfather_approved)
        and (
            project_contract.canonical_bytes is not None
            or project_contract.grandfathered_v4
        )
        and (example_table is not None or project_contract.grandfathered_v4)
        and (
            diagram_contract.canonical_bytes is not None
            or project_contract.grandfathered_v4
            or project_contract.grandfathered_v5
        )
        and (design_support_bytes is not None or not bind_design_support)
    )


def _aggregate_design_payload(
    *,
    technology_table: Any,
    applicability_table: Any,
    definition_table: Any,
    execution_table: Any,
    architecture: Any,
    harness: Any,
    change_impact: Any,
    project_contract: ProjectDesignContract,
    example_table: Any,
    diagram_contract: Any,
    design_support_bytes: bytes | None,
    bind_design_support: bool,
) -> bytes:
    return b"".join(
        (
            architecture.canonical_bytes or b"",
            harness.canonical_bytes or b"",
            change_impact.canonical_bytes or b"",
            project_contract.canonical_bytes or b"",
            diagram_contract.canonical_bytes or b"",
            technology_table.canonical_bytes,
            example_table.canonical_bytes if example_table is not None else b"",
            applicability_table.canonical_bytes,
            definition_table.canonical_bytes,
            execution_table.canonical_bytes,
            design_support_bytes
            if bind_design_support and design_support_bytes is not None
            else b"",
        )
    )


def aggregate_design_sha256(
    *,
    technology_table: Any,
    applicability_table: Any,
    definition_table: Any,
    execution_table: Any,
    architecture: Any,
    harness: Any,
    change_impact: Any,
    project_contract: ProjectDesignContract,
    example_table: Any,
    diagram_contract: Any,
    design_support_bytes: bytes | None,
    bind_design_support: bool,
    grandfather_approved: bool,
) -> str | None:
    """Return the aggregate Design identity only when every input is canonical."""

    values = locals()
    if not _aggregate_design_ready(**values):
        return None
    payload_args = {
        key: value for key, value in values.items() if key != "grandfather_approved"
    }
    payload = _aggregate_design_payload(**payload_args)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def bind_approved_schema7_compatibility(
    text: str,
    project_contract: ProjectDesignContract,
    canonical_sha256: str | None,
    *,
    grandfather_approved: bool,
    design8_headings: tuple[str, ...],
) -> tuple[ProjectDesignContract, list[str]]:
    """Bind frozen Design 7 only to its exact approved aggregate digest."""

    compatibility_candidate = bool(
        project_contract.schema_version == 7
        and not any(
            (
                project_contract.grandfathered_v4,
                project_contract.grandfathered_v5,
                project_contract.grandfathered_v6,
            )
        )
    )
    if not compatibility_candidate:
        return project_contract, []
    try:
        envelope = table_after_heading(text, "## 28. Construction envelope")
        approved_digest = clean_cell(envelope.get("Design contract SHA-256", ""))
    except ValueError:
        approved_digest = ""
    if (
        grandfather_approved
        and project_contract.status == "READY"
        and canonical_sha256 is not None
        and approved_digest == canonical_sha256
    ):
        return replace(project_contract, approved_schema7_compatibility=True), []
    issue = (
        "PROJECT_DESIGN_SCHEMA_MIGRATION_REQUIRED: Design 7 remains compatible "
        "only when its current approved aggregate digest exactly matches the stored "
        "Gate B construction envelope; migrate this design to schema 8"
    )
    missing = tuple(
        dict.fromkeys(
            (
                *project_contract.missing_records,
                "Project design contract schema 8",
                *sorted(design8_headings),
            )
        )
    )
    return (
        replace(
            project_contract,
            status="MIGRATION_REQUIRED",
            missing_records=missing,
        ),
        [issue],
    )


__all__ = (
    "ProjectSchemaCompatibility",
    "SchemaState",
    "aggregate_design_sha256",
    "bind_approved_schema7_compatibility",
    "project_schema_state",
)
