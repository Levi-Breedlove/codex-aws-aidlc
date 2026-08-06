"""Compatibility façade for Fastlane's canonical Markdown contract parser.

New Engine code imports :mod:`fastlane_engine.core.contracts`. Existing callers
may continue importing this module without behavior or exception changes.
"""

from __future__ import annotations

if __package__:
    from .fastlane_engine.core.contracts import (
        CHECKPOINT_GIT_RECEIPT,
        CHECKPOINT_HEADERS,
        SEPARATOR_CELL,
        TASK_COMPLETION_EVIDENCE_HEADERS,
        ContractTable,
        ContractParseError,
        contract_table_after_heading,
        contract_table_in_section,
        external_targets_overlap,
        markdown_tables,
        parse_checkpoint_cells,
        parse_checkpoint_git_receipt_value,
        parse_exact_section_table,
        parse_task_completion_evidence_cells,
        path_boundaries_overlap,
        path_boundary_base,
        path_boundary_contains,
        split_markdown_table_row,
        split_table_row,
        table_after_heading,
        without_fenced_code,
    )
else:  # Executed or imported directly from scripts/.
    from fastlane_engine.core.contracts import (
        CHECKPOINT_GIT_RECEIPT,
        CHECKPOINT_HEADERS,
        SEPARATOR_CELL,
        TASK_COMPLETION_EVIDENCE_HEADERS,
        ContractTable,
        ContractParseError,
        contract_table_after_heading,
        contract_table_in_section,
        external_targets_overlap,
        markdown_tables,
        parse_checkpoint_cells,
        parse_checkpoint_git_receipt_value,
        parse_exact_section_table,
        parse_task_completion_evidence_cells,
        path_boundaries_overlap,
        path_boundary_base,
        path_boundary_contains,
        split_markdown_table_row,
        split_table_row,
        table_after_heading,
        without_fenced_code,
    )

__all__ = (
    "CHECKPOINT_GIT_RECEIPT",
    "CHECKPOINT_HEADERS",
    "SEPARATOR_CELL",
    "TASK_COMPLETION_EVIDENCE_HEADERS",
    "ContractTable",
    "ContractParseError",
    "contract_table_after_heading",
    "contract_table_in_section",
    "external_targets_overlap",
    "markdown_tables",
    "parse_checkpoint_cells",
    "parse_checkpoint_git_receipt_value",
    "parse_exact_section_table",
    "parse_task_completion_evidence_cells",
    "path_boundaries_overlap",
    "path_boundary_base",
    "path_boundary_contains",
    "split_markdown_table_row",
    "split_table_row",
    "table_after_heading",
    "without_fenced_code",
)
