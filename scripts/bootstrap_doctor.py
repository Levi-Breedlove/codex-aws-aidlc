#!/usr/bin/env python3
"""Read-only structural and lifecycle checks for AWS Codex Fastlane projects.

``bootstrap.yaml`` intentionally uses JSON syntax. JSON is a YAML 1.2 subset,
so the state ledger remains portable while this doctor can use only Python's
standard library and reject ambiguous YAML constructs.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

if __package__:
    from .fastlane_engine.core.contracts import (
        ContractTable,
        _parse_contract_table_lines,
        contract_table_after_heading,
        markdown_tables,
        split_table_row,
        table_after_heading,
    )
    from .fastlane_engine.core.diagnostics import Diagnostic, DiagnosticCollector
    from .fastlane_engine.core.ids import (
        canonical_id_list,
        clean_cell,
        explicit_value,
        parse_exact_id_list,
        unresolved,
        validate_relative_path,
    )
    from .fastlane_engine.core.snapshot import (
        ObservationError,
        ProjectSnapshot,
        SnapshotObserver,
        has_symlink_component,
    )
    from .fastlane_engine.package.manifest import (
        ManifestPolicy,
        validate_manifest as validate_package_manifest,
        validate_placeholders as validate_package_placeholders,
        validate_prompt_pack as validate_package_prompt_pack,
    )
    from .fastlane_engine.package.state import (
        StatePolicy,
        validate_state_schema as validate_package_state_schema,
    )
    from .fastlane_engine.define.coverage import (
        derive_change_impact_contract,
        derive_coverage_contract,
    )
    from .fastlane_engine.define.intake import (
        _parse_intake_response_register,
        derive_intake_foundation_contract,
    )
    from .fastlane_engine.define.models import (
        AssumptionLifecycleRecord,
        ChangeImpactRow,
        CoverageContract,
        CoverageOmission,
        IntakeCard,
        IntakeFoundationContract,
        IntakeQuestion,
        NormalizedOwnerResponse,
        RequirementsChangeLineage,
        RequirementsContract,
    )
    from .fastlane_engine.define.project import (
        brownfield_contract_issues,
        derive_req_aws_materiality,
        gate_a_readiness_card_issues,
    )
    from .fastlane_engine.define.requirements import (
        _schema_13_requirement_rows,
        _state_trigger_map,
        authoritative_requirement_ids,
        concrete_requirement_subject,
        derive_requirements_contract,
        gate_a_method_contract_issues,
        measurable_acceptance_is_bound,
        observable_requirement_response,
        quality_attribute_scenario_issues,
        requirement_method_issues,
    )
    from .fastlane_engine.design import (
        APPLICATION_SOURCE_BROWNFIELD,
        APPLICATION_SOURCE_DIAGNOSTIC_CODES,
        APPLICATION_SOURCE_DISPOSITION_FIELD,
        APPLICATION_SOURCE_GREENFIELD,
        APPLICATION_SOURCE_NOT_APPLICABLE as APPLICATION_SOURCE_NOT_APPLICABLE,
        ARCHITECTURE_CANDIDATE_HEADING as ARCHITECTURE_CANDIDATE_HEADING,
        ARCHITECTURE_DRIVER_HEADING as ARCHITECTURE_DRIVER_HEADING,
        ARCHITECTURE_SELECTION_HEADING as ARCHITECTURE_SELECTION_HEADING,
        ARCHITECTURE_TRACEABILITY_HEADERS as ARCHITECTURE_TRACEABILITY_HEADERS,
        ARCHITECTURE_TRACEABILITY_HEADING as ARCHITECTURE_TRACEABILITY_HEADING,
        AWS_SERVICE_DECISION_HEADERS as AWS_SERVICE_DECISION_HEADERS,
        AWS_SERVICE_DECISION_HEADING as AWS_SERVICE_DECISION_HEADING,
        AWS_DERIVED_ARTIFACT,
        AWS_DISCOVERY_ID,
        AWS_EXACT_ARTIFACT,
        DIAGRAM_CONTRACT_HEADERS,
        DIAGRAM_CONTRACT_HEADING,
        ERROR_HANDLING_HEADERS as ERROR_HANDLING_HEADERS,
        ERROR_HANDLING_HEADING as ERROR_HANDLING_HEADING,
        FIRST_WAVE_HEADERS as FIRST_WAVE_HEADERS,
        FIRST_WAVE_HEADING as FIRST_WAVE_HEADING,
        HARNESS_HEADING as HARNESS_HEADING,
        IAC_VALIDATION_EVIDENCE_DESTINATION as IAC_VALIDATION_EVIDENCE_DESTINATION,
        IAC_VALIDATION_HEADERS as IAC_VALIDATION_HEADERS,
        IAC_VALIDATION_HEADING as IAC_VALIDATION_HEADING,
        INTERFACE_HEADERS as INTERFACE_HEADERS,
        INTERFACE_HEADING as INTERFACE_HEADING,
        JOURNEY_HEADERS,
        JOURNEY_HEADING,
        LAYER_BOUNDARY_HEADERS as LAYER_BOUNDARY_HEADERS,
        LAYER_BOUNDARY_HEADING as LAYER_BOUNDARY_HEADING,
        MATERIAL_AWS_EVIDENCE_HEADING as MATERIAL_AWS_EVIDENCE_HEADING,
        PROPERTY_EXECUTION_HEADERS,
        PROPERTY_EXECUTION_HEADING as PROPERTY_EXECUTION_HEADING,
        PROPERTY_ID,
        PROPERTY_TEST_EVIDENCE_DESTINATION,
        RICH_TO_STATE_TRIGGER as RICH_TO_STATE_TRIGGER,
        SPIKE_HEADING as SPIKE_HEADING,
        STATE_APPLICABILITY_HEADERS as STATE_APPLICABILITY_HEADERS,
        STATE_APPLICABILITY_HEADING as STATE_APPLICABILITY_HEADING,
        STATE_REGISTER_HEADERS as STATE_REGISTER_HEADERS,
        STATE_REGISTER_HEADING as STATE_REGISTER_HEADING,
        TECHNOLOGY_DECISION_ID,
        TECHNOLOGY_DECISION_HEADERS as TECHNOLOGY_DECISION_HEADERS,
        TECHNOLOGY_DECISION_HEADING as TECHNOLOGY_DECISION_HEADING,
        ApplicationSourceDisposition,
        ArchitectureContract,
        DesignContract,
        HarnessContract,
        HarnessRow as HarnessRow,
        PropertyExecution,
        ProjectDesignContract,
        TechnologyDecision,
        _derive_architecture_contract as _derive_architecture_contract_core,
        canonical_envelope_sha256,
        command_matches_prefix,
        current_prd_basis_ids as _current_prd_basis_ids_core,
        derive_design_contract as _derive_design_contract_core,
        derive_diagram_contract as derive_diagram_contract,
        derive_harness_contract as derive_harness_contract,
        derive_project_design_contract as _derive_project_design_contract_core,
        parse_application_source_disposition as parse_application_source_disposition,
        parse_authorized_ids,
        parse_aws_environment,
        parse_command_prefixes,
        parse_envelope_paths,
        parse_envelope_targets,
        parse_future_expiry_at,
        parse_github_constraints,
        parse_property_run_target,
        parse_task_boundary,
        parsed_numeric_version,
        required_diagram_kinds,
        technology_contract_value_is_unresolved,
        technology_reasoning_parts,
        machine_comparable_property_version_policy as machine_comparable_property_version_policy,
        valid_property_execution_command,
        valid_technology_selection as valid_technology_selection,
        valid_technology_version_policy as valid_technology_version_policy,
        validate_application_source_disposition as validate_application_source_disposition,
        validate_application_source_root,
        validate_application_source_write_set,
        validate_aws_artifact,
        validation_commands,
    )
else:  # Executed directly from scripts/.
    from fastlane_engine.core.contracts import (
        ContractTable,
        _parse_contract_table_lines,
        contract_table_after_heading,
        markdown_tables,
        split_table_row,
        table_after_heading,
    )
    from fastlane_engine.core.diagnostics import Diagnostic, DiagnosticCollector
    from fastlane_engine.core.ids import (
        canonical_id_list,
        clean_cell,
        explicit_value,
        parse_exact_id_list,
        unresolved,
        validate_relative_path,
    )
    from fastlane_engine.core.snapshot import (
        ObservationError,
        ProjectSnapshot,
        SnapshotObserver,
        has_symlink_component,
    )
    from fastlane_engine.package.manifest import (
        ManifestPolicy,
        validate_manifest as validate_package_manifest,
        validate_placeholders as validate_package_placeholders,
        validate_prompt_pack as validate_package_prompt_pack,
    )
    from fastlane_engine.package.state import (
        StatePolicy,
        validate_state_schema as validate_package_state_schema,
    )
    from fastlane_engine.define.coverage import (
        derive_change_impact_contract,
        derive_coverage_contract,
    )
    from fastlane_engine.define.intake import (
        _parse_intake_response_register,
        derive_intake_foundation_contract,
    )
    from fastlane_engine.define.models import (
        AssumptionLifecycleRecord,
        ChangeImpactRow,
        CoverageContract,
        CoverageOmission,
        IntakeCard,
        IntakeFoundationContract,
        IntakeQuestion,
        NormalizedOwnerResponse,
        RequirementsChangeLineage,
        RequirementsContract,
    )
    from fastlane_engine.define.project import (
        brownfield_contract_issues,
        derive_req_aws_materiality,
        gate_a_readiness_card_issues,
    )
    from fastlane_engine.define.requirements import (
        _schema_13_requirement_rows,
        _state_trigger_map,
        authoritative_requirement_ids,
        concrete_requirement_subject,
        derive_requirements_contract,
        gate_a_method_contract_issues,
        measurable_acceptance_is_bound,
        observable_requirement_response,
        quality_attribute_scenario_issues,
        requirement_method_issues,
    )
    from fastlane_engine.design import (
        APPLICATION_SOURCE_BROWNFIELD,
        APPLICATION_SOURCE_DIAGNOSTIC_CODES,
        APPLICATION_SOURCE_DISPOSITION_FIELD,
        APPLICATION_SOURCE_GREENFIELD,
        APPLICATION_SOURCE_NOT_APPLICABLE as APPLICATION_SOURCE_NOT_APPLICABLE,
        ARCHITECTURE_CANDIDATE_HEADING as ARCHITECTURE_CANDIDATE_HEADING,
        ARCHITECTURE_DRIVER_HEADING as ARCHITECTURE_DRIVER_HEADING,
        ARCHITECTURE_SELECTION_HEADING as ARCHITECTURE_SELECTION_HEADING,
        ARCHITECTURE_TRACEABILITY_HEADERS as ARCHITECTURE_TRACEABILITY_HEADERS,
        ARCHITECTURE_TRACEABILITY_HEADING as ARCHITECTURE_TRACEABILITY_HEADING,
        AWS_SERVICE_DECISION_HEADERS as AWS_SERVICE_DECISION_HEADERS,
        AWS_SERVICE_DECISION_HEADING as AWS_SERVICE_DECISION_HEADING,
        AWS_DERIVED_ARTIFACT,
        AWS_DISCOVERY_ID,
        AWS_EXACT_ARTIFACT,
        DIAGRAM_CONTRACT_HEADERS,
        DIAGRAM_CONTRACT_HEADING,
        ERROR_HANDLING_HEADERS as ERROR_HANDLING_HEADERS,
        ERROR_HANDLING_HEADING as ERROR_HANDLING_HEADING,
        FIRST_WAVE_HEADERS as FIRST_WAVE_HEADERS,
        FIRST_WAVE_HEADING as FIRST_WAVE_HEADING,
        HARNESS_HEADING as HARNESS_HEADING,
        IAC_VALIDATION_EVIDENCE_DESTINATION as IAC_VALIDATION_EVIDENCE_DESTINATION,
        IAC_VALIDATION_HEADERS as IAC_VALIDATION_HEADERS,
        IAC_VALIDATION_HEADING as IAC_VALIDATION_HEADING,
        INTERFACE_HEADERS as INTERFACE_HEADERS,
        INTERFACE_HEADING as INTERFACE_HEADING,
        JOURNEY_HEADERS,
        JOURNEY_HEADING,
        LAYER_BOUNDARY_HEADERS as LAYER_BOUNDARY_HEADERS,
        LAYER_BOUNDARY_HEADING as LAYER_BOUNDARY_HEADING,
        MATERIAL_AWS_EVIDENCE_HEADING as MATERIAL_AWS_EVIDENCE_HEADING,
        PROPERTY_EXECUTION_HEADERS,
        PROPERTY_EXECUTION_HEADING as PROPERTY_EXECUTION_HEADING,
        PROPERTY_ID,
        PROPERTY_TEST_EVIDENCE_DESTINATION,
        RICH_TO_STATE_TRIGGER as RICH_TO_STATE_TRIGGER,
        SPIKE_HEADING as SPIKE_HEADING,
        STATE_APPLICABILITY_HEADERS as STATE_APPLICABILITY_HEADERS,
        STATE_APPLICABILITY_HEADING as STATE_APPLICABILITY_HEADING,
        STATE_REGISTER_HEADERS as STATE_REGISTER_HEADERS,
        STATE_REGISTER_HEADING as STATE_REGISTER_HEADING,
        TECHNOLOGY_DECISION_ID,
        TECHNOLOGY_DECISION_HEADERS as TECHNOLOGY_DECISION_HEADERS,
        TECHNOLOGY_DECISION_HEADING as TECHNOLOGY_DECISION_HEADING,
        ApplicationSourceDisposition,
        ArchitectureContract,
        DesignContract,
        HarnessContract,
        HarnessRow as HarnessRow,
        PropertyExecution,
        ProjectDesignContract,
        TechnologyDecision,
        _derive_architecture_contract as _derive_architecture_contract_core,
        canonical_envelope_sha256,
        command_matches_prefix,
        current_prd_basis_ids as _current_prd_basis_ids_core,
        derive_design_contract as _derive_design_contract_core,
        derive_diagram_contract as derive_diagram_contract,
        derive_harness_contract as derive_harness_contract,
        derive_project_design_contract as _derive_project_design_contract_core,
        parse_application_source_disposition as parse_application_source_disposition,
        parse_authorized_ids,
        parse_aws_environment,
        parse_command_prefixes,
        parse_envelope_paths,
        parse_envelope_targets,
        parse_future_expiry_at,
        parse_github_constraints,
        parse_property_run_target,
        parse_task_boundary,
        parsed_numeric_version,
        required_diagram_kinds,
        technology_contract_value_is_unresolved,
        technology_reasoning_parts,
        machine_comparable_property_version_policy as machine_comparable_property_version_policy,
        valid_property_execution_command,
        valid_technology_selection as valid_technology_selection,
        valid_technology_version_policy as valid_technology_version_policy,
        validate_application_source_disposition as validate_application_source_disposition,
        validate_application_source_root,
        validate_application_source_write_set,
        validate_aws_artifact,
        validation_commands,
    )


def current_prd_basis_ids(text: str, design_revision: str | None) -> set[str]:
    """COMPATIBILITY: retain the doctor helper over the pure Design evaluator."""

    return _current_prd_basis_ids_core(
        text, design_revision, authoritative_requirement_ids(text)
    )


def _derive_architecture_contract(
    text: str,
    design_revision: str | None,
    technology_ids: set[str],
    *,
    required: bool,
    architecture_disposition: str | None = None,
    grandfather_approved_v1: bool = False,
) -> tuple[ArchitectureContract, list[str]]:
    """COMPATIBILITY: supply current Define IDs to pure architecture validation."""

    return _derive_architecture_contract_core(
        text,
        design_revision,
        technology_ids,
        authoritative_requirement_ids(text),
        required=required,
        architecture_disposition=architecture_disposition,
        grandfather_approved_v1=grandfather_approved_v1,
    )


def derive_project_design_contract(
    text: str,
    requirements_contract: RequirementsContract,
    coverage_contract: CoverageContract,
    allowed_basis_ids: set[str],
    harness: HarnessContract,
    legacy_design_ids: set[str],
    *,
    required: bool,
    grandfather_approved_v4: bool,
) -> tuple[ProjectDesignContract, list[str]]:
    """COMPATIBILITY: preserve the historical doctor signature."""

    return _derive_project_design_contract_core(
        text,
        requirements_contract,
        coverage_contract,
        authoritative_requirement_ids(text),
        allowed_basis_ids,
        harness,
        legacy_design_ids,
        _state_trigger_map,
        required=required,
        grandfather_approved_v4=grandfather_approved_v4,
    )


def derive_design_contract(
    text: str,
    design_revision: str | None,
    *,
    required: bool = False,
    grandfather_approved_v1: bool = False,
    coverage_contract: CoverageContract | None = None,
    requirements_contract: RequirementsContract | None = None,
) -> tuple[DesignContract, list[str]]:
    """COMPATIBILITY: preserve Design derivation while orchestration is extracted."""

    initial_issues: list[str] = []
    if coverage_contract is None:
        try:
            document = table_after_heading(text, "## Document status")
        except ValueError:
            document = {}
        repository_mode = clean_cell(document.get("Project mode", "")).lower()
        coverage_intake_contract, _coverage_intake_issues = (
            derive_intake_foundation_contract(
                text,
                repository_mode if repository_mode in PROJECT_MODES else None,
                grandfather_current_gate_a=grandfather_approved_v1,
            )
        )
        coverage_contract, coverage_issues = derive_coverage_contract(
            text,
            clean_cell(document.get("Current requirements revision", "")) or None,
            clean_cell(document.get("Delivery profile", "")) or None,
            clean_cell(document.get("Effective risk", "")) or None,
            clean_cell(document.get("AWS lane", "")) or None,
            required=required,
            grandfather_current_gate_a=grandfather_approved_v1,
            owner_work_context=coverage_intake_contract.owner_work_context,
        )
        if required:
            initial_issues.extend(coverage_issues)
    if requirements_contract is None:
        try:
            requirements_document = table_after_heading(text, "## Document status")
        except ValueError:
            requirements_document = {}
        repository_mode = clean_cell(
            requirements_document.get("Project mode", "")
        ).lower()
        intake_contract, _intake_issues = derive_intake_foundation_contract(
            text,
            repository_mode if repository_mode in PROJECT_MODES else None,
            grandfather_current_gate_a=grandfather_approved_v1,
        )
        requirements_contract, requirement_issues = derive_requirements_contract(
            text,
            clean_cell(requirements_document.get("Effective risk", "")) or None,
            intake_contract,
            required=required,
            grandfather_current_gate_a=grandfather_approved_v1,
        )
        if required:
            initial_issues.extend(issue for _code, issue in requirement_issues)
    return _derive_design_contract_core(
        text,
        design_revision,
        required=required,
        grandfather_approved_v1=grandfather_approved_v1,
        coverage_contract=coverage_contract,
        requirements_contract=requirements_contract,
        authoritative_requirement_ids=authoritative_requirement_ids(text),
        change_impact_deriver=derive_change_impact_contract,
        state_trigger_mapper=_state_trigger_map,
        initial_issues=initial_issues,
    )


def parse_future_expiry(value: str) -> datetime:
    """COMPATIBILITY: evaluate expiry against one façade-observed UTC clock."""

    return parse_future_expiry_at(value, datetime.now(timezone.utc))


try:
    from fastlane_adr import derive_adr_rationale, empty_adr_rationale
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_adr import derive_adr_rationale, empty_adr_rationale

try:
    from fastlane_context import (
        SliceRequest,
        SourceSpan,
        resolve_context_packet,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_context import (
        SliceRequest,
        SourceSpan,
        resolve_context_packet,
    )

try:
    from fastlane_contracts import (
        ContractParseError,
        external_targets_overlap,
        parse_checkpoint_cells,
        parse_checkpoint_git_receipt_value,
        parse_task_completion_evidence_cells,
        path_boundaries_overlap,
        path_boundary_contains,
        split_markdown_table_row,
        without_fenced_code,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_contracts import (
        ContractParseError,
        external_targets_overlap,
        parse_checkpoint_cells,
        parse_checkpoint_git_receipt_value,
        parse_task_completion_evidence_cells,
        path_boundaries_overlap,
        path_boundary_contains,
        split_markdown_table_row,
        without_fenced_code,
    )

try:
    from fastlane_owner_briefs import (
        TECHNICAL_DOMAIN_ORDER,
        answer_confirmation,
        claim as owner_claim,
        empty_owner_decision_inventory,
        empty_owner_decision_brief,
        finalize_owner_decision_inventory,
        finalize_owner_decision_brief,
        source_locator as owner_source_locator,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_owner_briefs import (
        TECHNICAL_DOMAIN_ORDER,
        answer_confirmation,
        claim as owner_claim,
        empty_owner_decision_inventory,
        empty_owner_decision_brief,
        finalize_owner_decision_inventory,
        finalize_owner_decision_brief,
        source_locator as owner_source_locator,
    )
try:
    from fastlane_document_summaries import (
        build_summary_specifications,
        canonical_bytes_without_generated_summary,
        project_document_summaries,
        strip_generated_summary,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_document_summaries import (
        build_summary_specifications,
        canonical_bytes_without_generated_summary,
        project_document_summaries,
        strip_generated_summary,
    )


try:
    from fastlane_process import resolve_trusted_git
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_process import resolve_trusted_git

try:
    from fastlane_project_identity import (
        PROJECT_NAME_TOKEN,
        normalize_aws_region,
        normalize_project_name,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_project_identity import (
        PROJECT_NAME_TOKEN,
        normalize_aws_region,
        normalize_project_name,
    )

try:
    from fastlane_stdio import configure_utf8_standard_streams
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_stdio import configure_utf8_standard_streams

try:
    from intake_response import (
        MAX_RESPONSE_CHARACTERS,
        intake_detail_safety_code,
        intake_reply_token,
        parse_intake_owner_response,
        parse_gate_correction,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.intake_response import (
        MAX_RESPONSE_CHARACTERS,
        intake_detail_safety_code,
        intake_reply_token,
        parse_intake_owner_response,
        parse_gate_correction,
    )


# COMPATIBILITY: Internal callers retain the historical private helper name.
_canonical_id_list = canonical_id_list

# COMPATIBILITY: These names remain importable from the stable doctor facade
# while new callers use ``fastlane_engine.api`` or the owning Define module.
_DEFINE_COMPATIBILITY_EXPORTS = (
    AssumptionLifecycleRecord,
    ChangeImpactRow,
    CoverageOmission,
    IntakeCard,
    IntakeQuestion,
    NormalizedOwnerResponse,
    RequirementsChangeLineage,
    concrete_requirement_subject,
    intake_detail_safety_code,
    intake_reply_token,
    measurable_acceptance_is_bound,
    observable_requirement_response,
    quality_attribute_scenario_issues,
    requirement_method_issues,
)


STATE_FILE = "bootstrap.yaml"
MANIFEST_FILE = "bootstrap.manifest.json"
PROJECT_DOCUMENT_DIRECTORY = "docs/project"
BUGFIX_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/BUGFIX.md"
PROJECT_README_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/README.md"
PRD_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/PRD.md"
RUNBOOK_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/RUNBOOK.md"
TASKS_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/TASKS.md"
VERIFY_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/VERIFY.md"
PROMPT_FILE = "prompts/CODEX-PROMPTS.md"
ENGINE_RUNTIME_CONTROL_FILES = {
    "scripts/fastlane_engine/__init__.py",
    "scripts/fastlane_engine/api.py",
    "scripts/fastlane_engine/core/__init__.py",
    "scripts/fastlane_engine/core/contracts.py",
    "scripts/fastlane_engine/core/diagnostics.py",
    "scripts/fastlane_engine/core/digests.py",
    "scripts/fastlane_engine/core/ids.py",
    "scripts/fastlane_engine/core/markdown_index.py",
    "scripts/fastlane_engine/core/snapshot.py",
    "scripts/fastlane_engine/define/__init__.py",
    "scripts/fastlane_engine/define/coverage.py",
    "scripts/fastlane_engine/define/intake.py",
    "scripts/fastlane_engine/define/models.py",
    "scripts/fastlane_engine/define/project.py",
    "scripts/fastlane_engine/define/requirements.py",
    "scripts/fastlane_engine/design/__init__.py",
    "scripts/fastlane_engine/design/adr.py",
    "scripts/fastlane_engine/design/architecture.py",
    "scripts/fastlane_engine/design/diagrams.py",
    "scripts/fastlane_engine/design/envelope.py",
    "scripts/fastlane_engine/design/harness.py",
    "scripts/fastlane_engine/design/models.py",
    "scripts/fastlane_engine/design/project.py",
    "scripts/fastlane_engine/design/source.py",
    "scripts/fastlane_engine/design/support.py",
    "scripts/fastlane_engine/package/__init__.py",
    "scripts/fastlane_engine/package/manifest.py",
    "scripts/fastlane_engine/package/state.py",
}
DOCUMENT_SUMMARY_FILES = (
    PROJECT_README_FILE,
    PRD_FILE,
    TASKS_FILE,
    VERIFY_FILE,
    RUNBOOK_FILE,
    BUGFIX_FILE,
)
REQ_ID = re.compile(r"REQ-\d{4,}")
DES_ID = re.compile(r"DES-\d{4,}")
AUTH_ID = re.compile(r"AUTH-\d{4,}")
PLAN_ID = re.compile(r"PLAN-\d{4,}")
TASK_ID = re.compile(r"TASK-\d+")
RUN_ID = re.compile(r"RUN-\d{4,}")
CHECKPOINT_ID = re.compile(r"CP-\d{4,}")
COST_AMOUNT = r"[1-9]\d*(?:\.\d{1,2})?"
AWS_COST_CEILING = re.compile(rf"(?P<currency>[A-Z]{{3}}): (?P<amount>{COST_AMOUNT})")
COST_POSTURE_WITH_CAP = re.compile(
    rf"MINIMIZE_TOTAL_COST; HARD_CAP: (?P<currency>[A-Z]{{3}}) (?P<amount>{COST_AMOUNT})"
)
DEFAULT_COST_POSTURE = "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED"
MAX_GATE_RECEIPT_CHARACTERS = 4096
# Current ISO 4217 List One currency and fund codes, excluding the testing
# code XTS and no-currency code XXX. Keep this equal to bootstrap.py so setup
# and machine-derived authorization enforce the same dependency-free grammar.
ISO_4217_CURRENCY_CODES = frozenset(
    """AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR XOF XPD XPF XPT XSU XUA YER ZAR ZMW ZWG""".split()
)

PROJECT_MODES = {"greenfield", "brownfield"}
DELIVERY_PROFILES = {"quick-mvp", "standard", "high-risk"}
RISK_LEVELS = {"low", "moderate", "high", "critical"}
AWS_LANES = {"documentation-only", "read-only", "fast-dev", "explicit-gate"}
WORK_KINDS = {
    "NEW_BUILD",
    "FEATURE",
    "BUGFIX",
    "REFACTOR",
    "MIGRATION",
    "INFRASTRUCTURE",
    "SECURITY_FIX",
}
ARCHITECTURE_DISPOSITIONS = {"SELECT", "AMEND", "PRESERVE"}
COVERAGE_DOMAINS = (
    "REQUIREMENTS",
    "ARCHITECTURE_COMPARISON",
    "AWS_EVIDENCE",
    "DATA",
    "SECURITY_PRIVACY",
    "RELIABILITY_RECOVERY",
    "COST",
    "HARNESS",
    "TASKS",
    "OPERATIONS",
)
ALWAYS_REQUIRED_COVERAGE = {
    "REQUIREMENTS",
    "SECURITY_PRIVACY",
    "COST",
    "HARNESS",
    "TASKS",
    "OPERATIONS",
}
COVERAGE_PLAN_HEADING = "### Adaptive coverage plan"
COVERAGE_PLAN_HEADERS = (
    "Work kind",
    "Delivery profile",
    "Architecture disposition",
    "Required sections",
    "Omitted sections and reasons",
    "Basis IDs",
)
CHANGE_IMPACT_HEADING = "### Change impact record"
CHANGE_IMPACT_HEADERS = (
    "Change ID",
    "Changed basis IDs",
    "Affected IDs",
    "Preserved IDs",
    "Required revalidation",
)
CHANGE_ID = re.compile(r"CHANGE-\d{4,}")
INTAKE_FOUNDATION_HEADING = "#### Intake foundation"
INTAKE_FOUNDATION_HEADERS = (
    "Intake ID",
    "Field",
    "Value",
    "Basis",
    "Status",
    "Owner response",
)
LEGACY_INTAKE_FOUNDATION_HEADERS = INTAKE_FOUNDATION_HEADERS[:-1]
INTAKE_FOUNDATION_FIELDS = (
    ("INTAKE-0001", "OWNER_WORK_CONTEXT"),
    ("INTAKE-0002", "PRIMARY_USERS"),
    ("INTAKE-0003", "OWNER_STATED_PROBLEM"),
    ("INTAKE-0004", "OBSERVABLE_OUTCOME"),
    ("INTAKE-0005", "FIRST_RELEASE_BOUNDARY"),
    ("INTAKE-0006", "SUCCESS_MEASURE"),
    ("INTAKE-0007", "DATA_TYPES"),
    ("INTAKE-0008", "DATA_SENSITIVITY"),
    ("INTAKE-0009", "RELEASE_AUDIENCE"),
    ("INTAKE-0010", "OPERATING_GEOGRAPHY"),
)
INTAKE_CORE_FIELDS = frozenset(
    {
        "OWNER_WORK_CONTEXT",
        "PRIMARY_USERS",
        "OWNER_STATED_PROBLEM",
        "OBSERVABLE_OUTCOME",
    }
)
OWNER_WORK_CONTEXTS = {
    "NEW_APPLICATION",
    "EXISTING_APPLICATION_CHANGE",
    "REPAIR_OR_MIGRATION",
}
OWNER_WORK_CONTEXT_SELECTIONS = {
    "A": "NEW_APPLICATION",
    "B": "EXISTING_APPLICATION_CHANGE",
    "C": "REPAIR_OR_MIGRATION",
}
INTAKE_BASES = {
    "OWNER_FACT",
    "REPOSITORY_FACT",
    "AGENT_RECOMMENDATION",
    "PROPOSED_ASSUMPTION",
    "OPEN_QUESTION",
}
INTAKE_CARD_HEADING = "#### Current intake decision card"
INTAKE_CARD_HEADERS = (
    "Card ID",
    "Revision",
    "Reply key",
    "Question ID",
    "Kind",
    "Basis IDs",
    "Prompt",
    "Option A",
    "Option B",
    "Option C",
    "Recommended",
    "Required detail for",
    "Detail prompt",
    "Selection",
    "Selection detail",
    "Owner response",
)
INTAKE_ID = re.compile(r"INTAKE-\d{4,}")
INTAKE_CARD_ID = re.compile(r"INTAKE-CARD-\d{4,}")
INTAKE_QUESTION_ID = re.compile(r"INTAKE-Q-\d{4,}")
OWNER_RESPONSE_ID = re.compile(r"OWNER-MSG-\d{4,}")
INTAKE_OWNER_RESPONSE = re.compile(
    r"OWNER_RESPONSE: (?P<message>OWNER-MSG-\d{4,}); "
    r"CARD: (?P<card>INTAKE-CARD-\d{4,}); REVISION: (?P<revision>[1-9]\d*); "
    r"SHA256: (?P<digest>sha256:[0-9a-f]{64}); "
    r"QUESTION: (?P<question>INTAKE-Q-\d{4,}); ANSWER: (?P<answer>A|B|C|RESPONSE)"
)
INTAKE_RESPONSE_REGISTER_HEADING = "#### Normalized owner response register"
INTAKE_RESPONSE_REGISTER_HEADERS = (
    "Owner response ID",
    "Card ID",
    "Revision",
    "Presented card digest",
    "Reply key",
    "Question ID",
    "Selection",
    "Selection detail",
    "Basis IDs",
)
STABLE_CONTRACT_ID = re.compile(r"[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
AWS_READ_AUTHORIZATION_ID = re.compile(r"AWS-READ-AUTH-\d{4,}")
AWS_PREFLIGHT_ID = re.compile(r"AWS-PREFLIGHT-\d{4,}")
NORMATIVE_REQUIREMENT_HEADERS = (
    "ID",
    "Requirement",
    "EARS form",
    "Acceptance ID",
    "Acceptance criteria",
    "Acceptance form",
)
LEGACY_NORMATIVE_REQUIREMENT_HEADERS = (
    "ID",
    "Requirement",
    "EARS form",
    "Acceptance criteria",
    "Acceptance form",
)
LEGACY_REQUIREMENT_HEADERS = ("ID", "Requirement", "Acceptance criteria")
PROJECT_CONTRACT_SCHEMA = "1.4"
REQUIREMENTS_CHANGE_LINEAGE_HEADING = "### Requirements change lineage"
REQUIREMENTS_CHANGE_LINEAGE_HEADERS = (
    "Current revision",
    "Prior revision",
    "Trigger",
    "Added IDs",
    "Changed IDs",
    "Removed IDs",
    "Preserved IDs",
    "Stale reason",
    "Required revalidation",
)
ASSUMPTION_LIFECYCLE_HEADING = "### Assumption lifecycle"
ASSUMPTION_LIFECYCLE_HEADERS = (
    "Assumption ID",
    "Assumption",
    "Status",
    "Basis IDs",
    "Validation or successor",
)
ASSUMPTION_STATUSES = {
    "PROPOSED",
    "ACCEPTED",
    "VALIDATED",
    "INVALIDATED",
    "SUPERSEDED",
}
REQUIREMENTS_REVISION_ID = re.compile(r"REQ-\d{4,}")
ASSUMPTION_ID = re.compile(r"ASM-\d{3,}")
ACTOR_HEADING = "## 4. Users and outcomes"
ACTOR_HEADERS = (
    "Actor ID",
    "Actor or external system",
    "Kind",
    "Desired outcome or responsibility",
    "Permission/data boundary",
    "Intake basis IDs",
)
ACTOR_KINDS = {"PRIMARY_USER", "SECONDARY_USER", "OPERATOR", "EXTERNAL_SYSTEM"}
ACTOR_ID = re.compile(r"ACT-\d{3,}")
ACCEPTANCE_ID = re.compile(r"AC-[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
ACCEPTANCE_TEST_BINDING_ID = re.compile(r"\b(?:TEST|PROP|EV)-\d{3,}\b")
RICH_USE_CASE_TRIGGERS = {
    "DISTINCT_PERMISSIONED_ACTORS",
    "CONFIDENTIAL_OR_REGULATED_MUTATION",
    "MONEY_OR_ENTITLEMENT",
    "IRREVERSIBLE_ACTION",
    "MIGRATION_OR_CUTOVER",
    "ASYNCHRONOUS_WORK",
    "PARTIAL_FAILURE",
}
RICH_USE_CASE_APPLICABILITY_HEADING = "### Rich-use-case applicability"
RICH_USE_CASE_APPLICABILITY_HEADERS = ("Applicability", "Trigger basis", "Use-case IDs")
RICH_USE_CASE_HEADING = "### Rich use cases"
RICH_USE_CASE_HEADERS = (
    "Use case ID",
    "Journey ID",
    "Primary actor ID",
    "Stakeholder interests",
    "Preconditions",
    "Success guarantee",
    "Minimum failure guarantee",
    "Business rule IDs",
    "Requirement IDs",
)
USE_CASE_ID = re.compile(r"USECASE-\d{3,}")
BUSINESS_RULE_HEADING = "### Business rules"
BUSINESS_RULE_HEADERS = (
    "Rule ID",
    "Rule",
    "Basis IDs",
    "Journey/use-case IDs",
    "Validation ID",
)
BUSINESS_RULE_ID = re.compile(r"BR-\d{3,}")
REQUIREMENT_COVERAGE_HEADING = "### Requirement coverage"
REQUIREMENT_COVERAGE_HEADERS = (
    "Requirement ID",
    "Intake basis IDs",
    "Actor IDs",
    "Journey IDs",
    "Acceptance/test IDs",
    "Approved success measure ID",
)
INTAKE_FOUNDATION_IDS = {f"INTAKE-{index:04d}" for index in range(1, 11)}
STATE_MODEL_TRIGGERS = (
    "LIFECYCLE_RESOURCE",
    "ASYNCHRONOUS_WORK",
    "RETRY_OR_RESUME",
    "APPROVAL_FLOW",
    "MIGRATION_OR_CUTOVER",
    "OTHER_MEANINGFUL_TRANSITION",
)
EARS_FORMS = {
    "UBIQUITOUS",
    "EVENT_DRIVEN",
    "STATE_DRIVEN",
    "UNWANTED_BEHAVIOR",
    "OPTIONAL_FEATURE",
    "COMPLEX",
}
# The Fastlane EARS Contract is a project-local normative schema. It does not
# redefine EARS outside this template.
EARS_PATTERNS = {
    "UBIQUITOUS": re.compile(r"The (?P<subject>.+?) SHALL (?P<response>.+)\."),
    "EVENT_DRIVEN": re.compile(
        r"WHEN (?P<trigger>.+), the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "STATE_DRIVEN": re.compile(
        r"WHILE (?P<state>.+), the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "UNWANTED_BEHAVIOR": re.compile(
        r"IF (?P<condition>.+), THEN the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "OPTIONAL_FEATURE": re.compile(
        r"WHERE (?P<feature>.+), the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "COMPLEX": re.compile(
        r"WHILE (?P<state>.+), WHEN (?P<trigger>.+), the "
        r"(?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
}
CONCRETE_SUBJECT = re.compile(r"[A-Za-z][A-Za-z0-9 _./'()-]*")
NON_CONCRETE_SUBJECTS = {
    "it",
    "something",
    "thing",
    "system subject",
    "placeholder",
    "unknown",
}
ACCEPTANCE_FORMS = {"GHERKIN", "MEASURABLE"}
GHERKIN_ACCEPTANCE = re.compile(
    r"GIVEN (?P<precondition>.+), WHEN (?P<trigger>.+), THEN (?P<result>.+)\."
)
MEASURABLE_EXPECTED_RESULT = re.compile(
    r"\b(?:allow|allows|cite|cites|contain|contains|confirm|confirms|cover|covers|"
    r"demonstrate|demonstrates|deny|denied|equal|equals|exceed|exceeds|fail|fails|find|finds|"
    r"identify|identifies|link|links|map|maps|match|matches|meet|meets|name|names|"
    r"pass|passes|preserve|preserves|prove|proves|record|records|reject|rejects|"
    r"restore|restores|show|shows|stay|stays|succeed|succeeds)\b|"
    r"(?:<=|>=|==|<|>)",
    re.IGNORECASE,
)
MEASURABLE_BINDING = re.compile(
    r"\b(?:at least|at most|bounded|calculation|configured|configuration|"
    r"every|each|exact|exactly|maximum|minimum|normal and peak|policy|"
    r"percentile|RPO|RTO|threshold|time-bounded|zero|one|all five|bound|"
    r"generated-case bound|pass condition|traceability check|runbook check|"
    r"owner decision|observed measurement|recorded [A-Za-z0-9 -]+ boundary|"
    r"approved (?:[A-Za-z0-9-]+ )?(?:boundary|case|control|environment|limit|"
    r"outcome|requirement|result|target|trigger|workload))\b|"
    r"\b(?:TEST|PROP|EV)-\d{3,}\b|"
    r"`[^`\r\n]+`|"
    r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/\S+|"
    r"\b(?:python|pytest|npm|pnpm|yarn|cargo|go test|dotnet test)\b|"
    r"\d+(?:\.\d+)?\s*(?:%|ms|s|seconds?|minutes?|hours?|requests?/s)?",
    re.IGNORECASE,
)
QAS_HEADERS = (
    "QAS ID",
    "Requirement IDs",
    "Source",
    "Stimulus",
    "Environment",
    "Artifact",
    "Response",
    "Response measure",
)
QAS_ID = re.compile(r"QAS-\d{3,}")
PROPERTY_TEST_EVIDENCE_HEADING = "## Property-based test evidence"
PROPERTY_TEST_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Task ID",
    "REQ / DES / AUTH",
    "Property ID",
    "Framework TECH ID",
    "Framework selection",
    "Observed exact version",
    "Exact command",
    "Observed run",
    "Replay seed or exact command",
    "Minimized counterexample",
    "Failure class / resolution",
    "Result",
    "Observed at",
    "Commit / worktree / artifact",
    "Durable source",
)
PROPERTY_TEST_RESULTS = {"NOT_STARTED", "PASS", "FAIL"}
PROPERTY_TEST_FAILURE_CLASSES = {
    "IMPLEMENTATION_DEFECT",
    "SPECIFICATION_AMBIGUITY_OR_DEFECT",
    "GENERATOR_OR_ORACLE_DEFECT",
    "ENVIRONMENT_DEFECT",
}
GATE_A_STATES = {
    "BLOCKED",
    "PENDING_OWNER_APPROVAL",
    "APPROVED_FOR_DESIGN",
    "STALE",
}
GATE_B_STATES = {
    "BLOCKED",
    "PENDING_OWNER_APPROVAL",
    "APPROVED_FOR_CONSTRUCTION",
    "STALE",
}
RUN_MODES = {"NONE", "SINGLE_TASK", "AUTONOMOUS"}
RUN_STATES = {"IDLE", "RUNNING", "CHECKPOINTED", "BLOCKED", "COMPLETE"}
BROWNFIELD_STATES = {"UNASSESSED", "NOT_APPLICABLE", "RECORDED", "STALE"}
CANONICAL_PLACEHOLDERS = {
    "{{PROJECT_NAME}}",
    "{{AWS_REGION}}",
    "{{COST_POSTURE}}",
    "{{SETUP_METHOD}}",
    "{{SETUP_STATUS}}",
}
MANDATORY_REQUIRED_FILES = (
    {
        ".github/ISSUE_TEMPLATE/aws-vertical-slice.yml",
        ".github/ISSUE_TEMPLATE/bugfix.yml",
        ".github/ISSUE_TEMPLATE/waf-risk.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".gitignore",
        ".agents/skills/build-fastlane/SKILL.md",
        ".agents/skills/explain-fastlane/SKILL.md",
        ".agents/skills/fastlane/SKILL.md",
        ".agents/skills/launch-fastlane/SKILL.md",
        ".agents/skills/maintain-fastlane/SKILL.md",
        ".agents/skills/operate-fastlane-aws/SKILL.md",
        ".agents/skills/plan-fastlane/SKILL.md",
        "AGENTS.md",
        BUGFIX_FILE,
        "LICENSE",
        PRD_FILE,
        "README.md",
        RUNBOOK_FILE,
        "SECURITY.md",
        TASKS_FILE,
        VERIFY_FILE,
        "app/README.md",
        "bootstrap.manifest.json",
        "bootstrap.py",
        "bootstrap.yaml",
        "docs/adr/0000-template.md",
        "docs/DEPENDENCY-POLICY.md",
        "docs/SETUP.md",
        "docs/TROUBLESHOOTING.md",
        "docs/WORKFLOW.md",
        "scripts/fastlane_document_summaries.py",
        "infrastructure/AGENTS.md",
        "infrastructure/README.md",
        "prompts/CODEX-PROMPTS.md",
        "scripts/bootstrap_doctor.py",
        "scripts/fastlane_adr.py",
        "scripts/fastlane_contracts.py",
        "scripts/fastlane_owner_briefs.py",
        "scripts/bootstrap_dependencies.py",
        "scripts/setup_assistant.py",
        "scripts/task_waves.py",
        "tests/AGENTS.md",
    }
    | ENGINE_RUNTIME_CONTROL_FILES
    | {"scripts/fastlane_engine/AGENTS.md"}
)


@dataclass
class Context:
    root: Path
    template_source: bool = False
    diagnostics: list[Diagnostic] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    presentation_texts: dict[str, str] = field(default_factory=dict)
    source_file_bytes: dict[str, bytes] = field(default_factory=dict)
    source_bytes_read: int = 0
    manifest_document: dict[str, Any] = field(default_factory=dict)
    bootstrap_state_document: dict[str, Any] = field(default_factory=dict)
    prior_remediation_fingerprint: str | None = None
    _observer: SnapshotObserver = field(init=False, repr=False)
    _diagnostic_collector: DiagnosticCollector = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._diagnostic_collector = DiagnosticCollector(backing=self.diagnostics)
        self._observer = SnapshotObserver(
            self.root,
            canonicalize_text=lambda relative, text: (
                strip_generated_summary(text)
                if relative in DOCUMENT_SUMMARY_FILES
                else text
            ),
            max_files=MAX_REQUIRED_FILES,
            max_file_bytes=MAX_REQUIRED_FILE_BYTES,
            max_source_bytes=MAX_PROJECT_SOURCE_BYTES,
        )

    def error(self, code: str, message: str, path: str | None = None) -> None:
        self._diagnostic_collector.error(code, message, path)

    def warning(self, code: str, message: str, path: str | None = None) -> None:
        self._diagnostic_collector.warning(code, message, path)

    @property
    def has_errors(self) -> bool:
        return self._diagnostic_collector.has_errors

    @property
    def snapshot(self) -> ProjectSnapshot:
        """Freeze the files and Markdown indexes observed by this invocation."""

        project = self.bootstrap_state_document.get("project", {})
        project_identity = (
            {key: str(project[key]) for key in ("name", "region") if key in project}
            if isinstance(project, dict)
            else {}
        )
        return self._observer.freeze(
            project_identity=project_identity,
            bootstrap_state=self.bootstrap_state_document,
            manifest=self.manifest_document,
        )


@dataclass
class TaskSummary:
    plan_revision: str | None = None
    plan_state: str = "UNINITIALIZED"
    statuses: dict[str, str] = field(default_factory=dict)
    ready: list[str] = field(default_factory=list)
    active: list[str] = field(default_factory=list)
    write_sets: dict[str, list[str]] = field(default_factory=dict)
    attempts_used: dict[str, int] = field(default_factory=dict)
    attempt_budgets: dict[str, int] = field(default_factory=dict)
    requirement_coverage_complete: bool = False
    requirement_coverage: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing_requirement_ids: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.statuses)

    @property
    def done(self) -> list[str]:
        return sorted(
            task_id for task_id, status in self.statuses.items() if status == "DONE"
        )

    @property
    def skipped(self) -> list[str]:
        return sorted(
            task_id for task_id, status in self.statuses.items() if status == "SKIPPED"
        )

    @property
    def blocked(self) -> list[str]:
        return sorted(
            task_id for task_id, status in self.statuses.items() if status == "BLOCKED"
        )

    @property
    def terminal(self) -> bool:
        return bool(self.statuses) and all(
            status in {"DONE", "SKIPPED"} for status in self.statuses.values()
        )


@dataclass(frozen=True)
class TaskRequirementCoverage:
    requirement_id: str
    acceptance_id: str
    disposition: str
    task_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "acceptance_id": self.acceptance_id,
            "disposition": self.disposition,
            "task_ids": list(self.task_ids),
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class TaskRequirementCoverageResult:
    records: tuple[TaskRequirementCoverage, ...] = ()
    trace_issues: tuple[str, ...] = ()
    evidence_issues: tuple[str, ...] = ()
    missing_requirement_ids: tuple[str, ...] = ()


TASK_METADATA_KEYS = (
    "Status",
    "Requirements",
    "Design",
    "Authorization",
    "Depends on",
    "Dependency waivers",
    "Owner",
    "Run ID",
    "Risk",
    "Write set",
    "External state",
    "AWS mode",
    "Attempt budget",
    "Attempts used",
    "Evidence",
    "Blocker",
    "Skip record",
    "GitHub issue",
    "Last checkpoint",
    "Last updated",
)
TASK_HEADER_PATTERN = re.compile(r"^###\s+(TASK-\d+)\s+[—-]\s+(.+?)\s*$", re.MULTILINE)
TASK_META_PATTERN = re.compile(
    rf"^- (?P<key>{'|'.join(re.escape(key) for key in TASK_METADATA_KEYS)}):"
    r"\s*(?P<value>.+?)\s*$",
    re.MULTILINE,
)
TASK_STATUSES = {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE", "SKIPPED"}
TASK_AWS_MODES = {"NONE", "DOCS_ONLY"}
TASK_DESIGN_TRACE_PATTERN = re.compile(
    r"^(?P<design>DES-\d{4}); TECH: "
    r"(?:(?P<none>NONE — no technology/toolchain impact)|"
    r"(?P<technologies>TECH-\d{4}(?:, TECH-\d{4})*))$"
)
EVIDENCE_PATTERN = re.compile(
    r"(?:\b(?:EV|EVIDENCE)-[A-Z0-9][A-Z0-9._-]*\b|"
    r"\bVERIFY\.md#[A-Za-z0-9._-]+\b|https?://\S+)",
    re.IGNORECASE,
)
LOCAL_EVIDENCE_ID = re.compile(r"\bEV-\d{4,}\b")
LOCAL_EVIDENCE_LIKE = re.compile(r"\b(?:EV|EVIDENCE)-[A-Za-z0-9._-]+\b", re.IGNORECASE)
TASK_COMPLETION_EVIDENCE_STATUSES = {"LOCAL_PASS", "VERIFIED"}
EVIDENCE_PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:TODO|TBD|TBC|UNKNOWN|UNASSIGNED|PENDING|PLACEHOLDER|"
    r"NOT[ _-]*STARTED|NONE|N/?A)\b|<[^>]+>",
    re.IGNORECASE,
)
UNRESOLVED_TOKEN = re.compile(
    r"(?<![A-Z0-9])(?:TODO|TBD|TBC|UNKNOWN|UNASSIGNED)(?![A-Z0-9])",
    re.IGNORECASE,
)
SNAPSHOT_FIELDS = {
    "Task-plan revision",
    "Task-plan state",
    "Requirements revision",
    "Design revision",
    "Construction authorization",
    "Gate B state",
    "Run state",
    "Active run ID",
    "Baseline commit",
    "Protected dirty paths",
    "Coordinator",
    "Maximum workers",
    "Current wave",
    "Last checkpoint",
    "Last known-green commit",
    "Next safe action",
}
SNAPSHOT_RUN_STATES = {"NOT_STARTED", "RUNNING", "PAUSED", "BLOCKED", "COMPLETE"}
GITHUB_BOUNDARIES = {"NONE", "READ_ONLY", "ISSUES", "BRANCH_AND_PR", "MERGE_WHEN_GREEN"}
AWS_BOUNDARIES = {"NONE", "DOCS_ONLY", "READ_ONLY", "MUTATE_LISTED_RESOURCES"}
AWS_DETAIL_FIELDS = {
    "AWS account",
    "AWS role or profile",
    "AWS Region",
    "AWS environment",
    "AWS stack or application",
    "AWS resource allowlist",
    "AWS allowed operations",
    "AWS cost ceiling",
    "AWS prohibited operations",
    "AWS artifact authorization and provenance",
    "AWS rollback boundary",
    "AWS authorization validity",
}
CONTROL_HASH_FILES = {
    "bootstrap.py",
    "scripts/bootstrap_dependencies.py",
    "scripts/bootstrap_doctor.py",
    "scripts/fastlane_adr.py",
    "scripts/fastlane_contracts.py",
    "scripts/fastlane_process.py",
    "scripts/fastlane_project_identity.py",
    "scripts/fastlane_stdio.py",
    "scripts/setup_assistant.py",
    "scripts/task_waves.py",
} | ENGINE_RUNTIME_CONTROL_FILES
COORDINATOR_LEDGER_PATHS = {TASKS_FILE, VERIFY_FILE, STATE_FILE}
ID_LIKE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*-\d+\b")
GITHUB_ISSUE_URL = re.compile(
    r"https://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/[1-9]\d*"
)
SHELL_CONTROL = re.compile(r"[;&|><`$()\\\r\n]")
NON_HUMAN_APPROVER = re.compile(
    r"(?:^|[^a-z0-9])(?:ai|agent|assistant|automated|automation|bot|chatbot|"
    r"chatgpt|codex|gpt(?:-[0-9]+(?:\.[0-9]+)?)?|lambda|llm|model|openai|robot|"
    r"service|system|workflow|aws[ _-]*(?:core|lambda)|pending|placeholder|"
    r"not[ _-]*started)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
ENVELOPE_EXPLICIT_FIELDS = {
    "Project mode",
    "Delivery profile and effective risk",
    "Project AWS lane",
    "Authorized outcome",
    "Authorized requirement and design IDs",
    "Design contract SHA-256",
    "Authorized baseline commit",
    "Protected dirty paths",
    "In-scope components and environments",
    "Allowed repository write set",
    "Excluded or owner-only write set",
    "Allowed external-state targets",
    "Task boundary",
    "Parallelism rule",
    "Checkpoint cadence",
    "Required checkpoint contents",
    "Local command boundary",
    "GitHub repository, branch, and merge constraints",
    *AWS_DETAIL_FIELDS,
    "Rollback, recovery, and teardown boundary",
    "Mandatory stop conditions",
    "Authorization expiry or completion condition",
}
BROWNFIELD_BASELINE_FIELDS = {
    "Repository and baseline commit",
    "Deployed environments and observed versions",
    "Existing architecture and ownership",
    "Current interfaces, schemas, and consumers",
    "Current data stores and migration constraints",
    "Existing security and compliance controls",
    "Baseline verification commands",
    "Baseline evidence location",
    "Known defects and accepted debt",
    "Repository-to-environment drift",
    "Dirty or user-owned working-tree changes",
    "Protected files and components",
    "Unresolved bootstrap overlay collisions",
}
GATE_A_READINESS_FIELDS = {
    "Outcome",
    "Owner and users",
    "Scope and non-goals",
    "Measurable requirement/acceptance IDs",
    "Data boundary",
    "Identity/security boundary",
    "Environment/Region",
    "Failure/recovery",
    "Cost posture",
    "Intake provenance",
}
GATE_B_READINESS_FIELDS = {
    "Design basis IDs",
    "Architecture/components",
    "Technology/toolchains/version policy",
    "Interfaces/data flow",
    "Identity/secrets",
    "Failure/retry/concurrency",
    "Deployment/operations",
    "Validation/evidence",
    "Rollback/recovery/teardown",
    "Brownfield compatibility/migration",
    "Outstanding gaps",
}
AWS_CORE_EVIDENCE_HEADERS = (
    "Phase",
    "Discovery ID",
    "Basis IDs",
    "Plugin source",
    "Invoked plugin identity",
    "Observed plugin version",
    "Capability",
    "Observation actor",
    "Requested skill",
    "Returned skill identifier",
    "Documentation query",
    "Discovered skill identifiers",
    "Source references",
    "Advisory Design binding",
    "Credentials inspected",
    "AWS account accessed",
    "Observed at",
    "Evidence binding",
    "Observed status",
)
AWS_CORE_EVIDENCE_HEADERS_V1 = tuple(
    header
    for header in AWS_CORE_EVIDENCE_HEADERS
    if header not in {"Discovery ID", "Basis IDs", "Discovered skill identifiers"}
)
AWS_CORE_EVIDENCE_PHASES = ("REQ-10", "DESIGN-10", "AWS-10")
AWS_CORE_REQUIRED_CAPABILITIES = ("search_documentation", "retrieve_skill")
AWS_CORE_MATERIALITY_VALUES = {"REQUIRED", "OPTIONAL", "NOT_MATERIAL"}
AWS_READ_PREFLIGHT_RECEIPT_FIELDS = (
    "Read authorization",
    "Construction authorization",
    "Profile or role",
    "Account",
    "Region",
    "Environment",
    "Stack, application, and resources",
    "Allowed read-only operations",
    "Artifact digest",
    "Prohibited operations",
    "Valid until",
    "Approver",
)
AWS_DEPLOYMENT_RECEIPT_FIELDS = (
    "AWS authorization",
    "Construction authorization",
    "Profile or role",
    "Account",
    "Region",
    "Environment",
    "Artifact digest",
    "IaC plan/change-set binding",
    "Stack, application, and resources",
    "Allowed operations",
    "Cost ceiling",
    "Rollback boundary",
    "Valid until",
    "Approver",
)
AWS_TEARDOWN_RECEIPT_FIELDS = (
    "Teardown authorization",
    "Construction authorization",
    "Profile or role",
    "Account",
    "Region",
    "Environment",
    "Stack, application, and resources to remove",
    "Resources and data to retain",
    "Allowed deletion operations",
    "Shared dependencies",
    "Cost effect",
    "Post-teardown verification",
    "Valid until",
    "Approver",
)
AWS_PLAN_BINDING = re.compile(
    r"TYPE: (?P<type>CLOUDFORMATION_CHANGE_SET|TERRAFORM_PLAN|CONTAINER_IMAGE|OTHER); "
    r"IDENTIFIER: (?P<identifier>[^;\r\n]+); DIGEST: (?P<digest>sha256:[0-9a-f]{64})"
)
AWS_READ_PREFLIGHT_HEADING = "## Read-only AWS preflight evidence"
AWS_READ_PREFLIGHT_HEADERS = (
    "Preflight ID",
    "Read authorization",
    "REQ / DES / AUTH",
    "Artifact digest",
    "Role or profile",
    "Account",
    "Region",
    "Environment",
    "Resources",
    "Operations observed",
    "AWS evidence IDs",
    "Account access",
    "Caller identity evidence",
    "Boundary and drift evidence",
    "Started at",
    "Completed at",
    "Identity and boundary match",
    "Result",
)
AWS_TEARDOWN_EVIDENCE_HEADING = "## Teardown reconciliation evidence"
AWS_TEARDOWN_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Attempt ID",
    "Phase",
    "REQ / DES / AUTH",
    "Read authorization",
    "Read role or profile",
    "Read receipt digest",
    "Read valid until",
    "Read authority source",
    "Teardown authorization",
    "Teardown receipt digest",
    "Role or profile",
    "Expected manifest or stack",
    "Resources proposed to remove",
    "Allowed deletion operations",
    "Resources retained",
    "Shared dependencies",
    "Cost effect",
    "Post-teardown verification",
    "Stack events and terminal status",
    "Resources removed",
    "Snapshots and backups",
    "Residual resources",
    "Inventory or discovery limits",
    "Account / Region / environment",
    "Observed at",
    "Durable source",
    "Identity and boundary match",
    "Blocker or stale reason",
    "Status",
)
AWS_TEARDOWN_REVIEW_STATUSES = {
    "RUNNING",
    "READY_FOR_TEARDOWN",
    "VERIFIED_CLEAN",
    "RESIDUALS_REMAIN",
    "BLOCKED",
    "STALE",
}
AWS_TEARDOWN_ACTION_STATUSES = {
    "STARTED",
    "SUCCEEDED",
    "FAILED",
    "PARTIAL",
    "UNKNOWN",
}
AWS_TEARDOWN_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN"}
AWS_TEARDOWN_ATTEMPT_ID = re.compile(r"AWS-TEARDOWN-\d{4,}")
AWS_TEARDOWN_READ_PROVENANCE = re.compile(
    r"SOURCE: (?P<source>[^;\r\n]+); "
    r"AUTHORIZED_AT: (?P<authorized_at>[^;\r\n]+)"
)
AWS_DEPLOYMENT_READ_PROVENANCE = re.compile(
    r"SOURCE: (?P<source>[^;|\r\n]+); "
    r"AUTHORIZED_AT: (?P<authorized_at>[^;|\r\n]+); "
    r"RESOURCES: (?P<resources>[^;|\r\n]+); "
    r"OPERATIONS: (?P<operations>[^;|\r\n]+)"
)
AWS_TEARDOWN_PRECALL_RESULT = "NOT_OBSERVED — pre-call journal only"
AWS_DEPLOYMENT_EVIDENCE_HEADING = "## AWS deployment action and reconciliation evidence"
AWS_DEPLOYMENT_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Attempt ID",
    "Phase",
    "REQ / DES / AUTH",
    "Deployment authorization",
    "Deployment receipt digest",
    "Deployment valid until",
    "Deployment authority source",
    "Read authorization",
    "Deployment role or profile",
    "Read role or profile",
    "Read receipt digest",
    "Read valid until",
    "Read authority source",
    "Artifact digest",
    "Plan/change-set binding",
    "Resources",
    "Mutation operations",
    "Read operations observed",
    "Account / Region / environment",
    "Operation identifiers and direct result",
    "Rollback result",
    "Acceptance evidence IDs",
    "Observed at",
    "Durable source",
    "Identity and boundary match",
    "Blocker or stale reason",
    "Status",
)
AWS_DEPLOYMENT_ATTEMPT_ID = re.compile(r"AWS-DEPLOY-\d{4,}")
AWS_DEPLOYMENT_ACTION_STATUSES = {
    "STARTED",
    "SUCCEEDED",
    "FAILED",
    "PARTIAL",
    "UNKNOWN",
}
AWS_DEPLOYMENT_TERMINAL_STATUSES = AWS_DEPLOYMENT_ACTION_STATUSES - {"STARTED"}
AWS_DEPLOYMENT_RECONCILIATION_STATUSES = {"COMPLETE", "BLOCKED", "STALE"}
AWS_DEPLOYMENT_PRECALL_RESULT = "NOT_OBSERVED \u2014 pre-call journal only"
VERIFICATION_MATRIX_HEADING = "## Verification matrix"
VERIFICATION_MATRIX_HEADERS = (
    "Evidence ID",
    "PRD / property IDs",
    "Task IDs",
    "Requirement or invariant",
    "Automated evidence",
    "AWS/manual evidence",
    "Artifact/environment",
    "Status",
)
AWS_READ_ONLY_OPERATION = re.compile(
    r"(?i)^(?:[a-z0-9-]+[.:])?(?:BatchGet|Check|Describe|Detect|Estimate|Get|"
    r"Head|List|Lookup|Preview|Search|Simulate|Validate)[A-Za-z0-9]*$"
)
AWS_CORE_OFFICIAL_SOURCE = "aws/agent-toolkit-for-aws"
AWS_CORE_OFFICIAL_IDENTITY = "aws-core@agent-toolkit-for-aws"
AWS_CORE_OBSERVATION_ACTOR = "CODEX_LIVE_TOOL_CALL"
AWS_CORE_PLUGIN_VERSION_PATTERN = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
)
AWS_CORE_CANONICAL_SKILL_IDENTIFIER_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:/@-]*"
)
AWS_CORE_OFFICIAL_DOCUMENTATION_REFERENCE_PATTERN = re.compile(
    r"https://(?:docs\.aws\.amazon\.com|aws\.amazon\.com)/\S+",
    re.IGNORECASE,
)
AWS_CORE_OFFICIAL_DOCUMENTATION_URL_PATTERN = re.compile(
    r"https://(?:docs\.aws\.amazon\.com|aws\.amazon\.com)/[^\s<>)\]|,;]+",
    re.IGNORECASE,
)
AWS_CORE_EVIDENCE_STATUSES = {
    "NOT_STARTED",
    "PASS",
    "VERIFIED",
    "FAILED",
    "BLOCKED",
    "STALE",
}


@dataclass
class InspectedTask:
    task_id: str
    title: str
    block: str
    metadata: dict[str, str]
    duplicates: set[str]

    @property
    def status(self) -> str:
        return clean_cell(self.metadata.get("Status", "")).upper()

    @property
    def dependencies(self) -> list[str]:
        raw = clean_cell(self.metadata.get("Depends on", "NONE"))
        return (
            []
            if raw in {"", "NONE", "-"}
            else [item.strip() for item in raw.split(",")]
        )

    @property
    def attempts_used(self) -> int:
        return int(clean_cell(self.metadata["Attempts used"]))

    @property
    def attempt_budget(self) -> int:
        return int(clean_cell(self.metadata["Attempt budget"]))


@dataclass(frozen=True)
class TaskCompletionEvidenceRow:
    evidence_id: str
    task_id: str
    command_or_observation: str
    result: str
    actor: str
    observed_at: str
    commit_worktree_artifact: str
    durable_source: str
    status: str


@dataclass(frozen=True)
class PropertyTestEvidenceRow:
    evidence_id: str
    task_id: str
    requirements_design_authorization: str
    property_id: str
    framework_tech_id: str
    framework_selection: str
    observed_exact_version: str
    exact_command: str
    observed_run: str
    replay_seed_or_exact_command: str
    minimized_counterexample: str
    failure_class_resolution: str
    result: str
    observed_at: str
    commit_worktree_artifact: str
    durable_source: str


@dataclass(frozen=True)
class AwsCoreEvidenceRow:
    phase: str
    discovery_id: str
    basis_ids: str
    plugin_source: str
    invoked_plugin_identity: str
    observed_plugin_version: str
    capability: str
    observation_actor: str
    requested_skill: str
    returned_skill_identifier: str
    documentation_query: str
    discovered_skill_identifiers: str
    source_references: str
    advisory_design_binding: str
    credentials_inspected: str
    aws_account_accessed: str
    observed_at: str
    evidence_binding: str
    observed_status: str


@dataclass(frozen=True)
class CheckpointReceiptRow:
    checkpoint_id: str
    run_id: str
    recorded_at: str
    basis: str
    commit_and_dirty: str
    task_outcomes: str
    evidence_and_external: str
    blockers_and_next: str


def inspect_task_blocks(text: str) -> list[InspectedTask]:
    structural = without_fenced_code(text)
    matches = list(TASK_HEADER_PATTERN.finditer(structural))
    tasks: list[InspectedTask] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end]
        structural_block = structural[match.start() : end]
        metadata: dict[str, str] = {}
        duplicates: set[str] = set()
        for found in TASK_META_PATTERN.finditer(structural_block):
            key = found.group("key")
            if key in metadata:
                duplicates.add(key)
            metadata[key] = found.group("value")
        tasks.append(
            InspectedTask(
                match.group(1), match.group(2).strip(), block, metadata, duplicates
            )
        )
    return tasks


def inspect_task_sections(block: str) -> tuple[dict[str, str], set[str]]:
    structural = without_fenced_code(block)
    pattern = re.compile(
        r"^####[ \t]+(Outcome|Acceptance criteria|Validation|Execution log)[ \t]*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(structural))
    sections: dict[str, str] = {}
    duplicates: set[str] = set()
    for index, match in enumerate(matches):
        name = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
        if name in sections:
            duplicates.add(name)
        sections[name] = block[match.end() : end]
    return sections, duplicates


def parse_task_completion_evidence(text: str) -> list[TaskCompletionEvidenceRow]:
    try:
        parsed_rows = parse_task_completion_evidence_cells(text)
    except ContractParseError as exc:
        messages = {
            "section_count": "VERIFY.md requires exactly one Task completion evidence section",
            "header_count": "VERIFY.md requires one exact Task completion evidence table",
            "separator_missing": "VERIFY.md Task completion evidence separator is invalid",
            "separator_invalid": "VERIFY.md Task completion evidence separator is invalid",
            "row_width": "VERIFY.md Task completion evidence row must have nine cells",
            "discontiguous_rows": "VERIFY.md Task completion evidence rows must form one contiguous table",
        }
        raise ValueError(
            messages.get(exc.reason, "VERIFY.md Task completion evidence is invalid")
        ) from exc
    rows: list[TaskCompletionEvidenceRow] = []
    for cells in parsed_rows:
        row = TaskCompletionEvidenceRow(*(clean_cell(cell) for cell in cells))
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError("VERIFY.md Task completion Evidence ID must be EV-nnnn")
        rows.append(row)
    identifiers = [row.evidence_id for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("VERIFY.md Task completion Evidence IDs must be unique")
    return rows


def parse_aws_core_evidence(
    text: str,
    *,
    allow_legacy: bool = False,
) -> dict[tuple[str, str, str], AwsCoreEvidenceRow]:
    """Parse linked runtime skill-discovery evidence chains."""

    structural = without_fenced_code(text)
    headings = list(
        re.finditer(r"^## AWS Core evidence[ \t]*$", structural, re.MULTILINE)
    )
    if len(headings) != 1:
        raise ValueError("VERIFY.md requires exactly one AWS Core evidence section")
    following = re.search(r"^##\s+", structural[headings[0].end() :], re.MULTILINE)
    end = headings[0].end() + following.start() if following else len(structural)
    lines = structural[headings[0].end() : end].splitlines()

    headers = AWS_CORE_EVIDENCE_HEADERS
    header_indexes = [
        index
        for index, line in enumerate(lines)
        if split_markdown_table_row(line) == list(headers)
    ]
    legacy = False
    if len(header_indexes) != 1 and allow_legacy:
        headers = AWS_CORE_EVIDENCE_HEADERS_V1
        header_indexes = [
            index
            for index, line in enumerate(lines)
            if split_markdown_table_row(line) == list(headers)
        ]
        legacy = len(header_indexes) == 1
    if len(header_indexes) != 1:
        raise ValueError("VERIFY.md requires one exact AWS Core evidence table")
    header = header_indexes[0]
    separator = (
        split_markdown_table_row(lines[header + 1]) if header + 1 < len(lines) else None
    )
    if (
        separator is None
        or len(separator) != len(headers)
        or any(re.fullmatch(r":?-{3,}:?", cell) is None for cell in separator)
    ):
        raise ValueError("VERIFY.md AWS Core evidence separator is invalid")

    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow] = {}
    discovery_phases: dict[str, str] = {}
    for line in lines[header + 2 :]:
        if not line.strip():
            if rows:
                break
            continue
        cells = split_markdown_table_row(line)
        if cells is None:
            if rows:
                break
            raise ValueError("VERIFY.md AWS Core evidence row is missing")
        if len(cells) != len(headers):
            raise ValueError(
                f"VERIFY.md AWS Core evidence row must have {len(headers)} cells"
            )
        cleaned = tuple(clean_cell(cell) for cell in cells)
        if legacy:
            row = AwsCoreEvidenceRow(
                cleaned[0],
                "",
                "",
                *cleaned[1:9],
                "",
                *cleaned[9:],
            )
        else:
            row = AwsCoreEvidenceRow(*cleaned)
        if row.phase not in AWS_CORE_EVIDENCE_PHASES:
            raise ValueError(
                f"VERIFY.md AWS Core evidence has unknown phase {row.phase!r}"
            )
        capability = row.capability.replace("`", "").strip()
        if capability not in AWS_CORE_REQUIRED_CAPABILITIES:
            raise ValueError(
                f"{row.phase} AWS Core evidence has unknown capability {capability!r}"
            )
        if not legacy and AWS_DISCOVERY_ID.fullmatch(row.discovery_id) is None:
            raise ValueError(
                f"{row.phase} AWS Core evidence has invalid Discovery ID {row.discovery_id!r}"
            )
        owner = discovery_phases.setdefault(row.discovery_id, row.phase)
        if row.discovery_id and owner != row.phase:
            raise ValueError(
                f"{row.discovery_id} AWS Core discovery ID is reused across phases"
            )
        key = (row.phase, row.discovery_id, capability)
        if key in rows:
            raise ValueError(
                f"VERIFY.md AWS Core evidence duplicates {row.phase} "
                f"{row.discovery_id or 'legacy'} {capability}"
            )
        if row.observed_status not in AWS_CORE_EVIDENCE_STATUSES:
            raise ValueError(
                f"{row.phase} {capability} AWS Core evidence has invalid status"
            )
        rows[key] = row

    missing: list[str] = []
    present_phases = sorted(
        {row_phase for row_phase, _discovery_id, _capability in rows}
    )
    for phase in present_phases:
        discovery_ids = sorted(
            {discovery_id for row_phase, discovery_id, _ in rows if row_phase == phase}
        )
        if not discovery_ids:
            missing.append(f"{phase} discovery chain")
            continue
        for discovery_id in discovery_ids:
            for capability in AWS_CORE_REQUIRED_CAPABILITIES:
                if (phase, discovery_id, capability) not in rows:
                    missing.append(f"{phase} {discovery_id or 'legacy'} {capability}")
    if missing:
        raise ValueError(
            "VERIFY.md AWS Core evidence is missing linked rows: " + ", ".join(missing)
        )
    return rows


def validate_advisory_design_binding(
    value: str,
    phase: str,
    *,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
) -> None:
    cleaned = clean_cell(value)
    if phase == "REQ-10":
        expected = (
            "NOT_APPLICABLE \u2014 requirements feasibility only; "
            "no architecture selected"
        )
        if cleaned != expected:
            raise ValueError(
                "REQ-10 Advisory Design binding must prove requirements feasibility "
                "without selecting an architecture"
            )
        return
    not_applicable_prefix = "NOT_APPLICABLE — "
    if cleaned.startswith(not_applicable_prefix):
        if phase not in {"REQ-10", "AWS-10"} or not explicit_value(
            cleaned[len(not_applicable_prefix) :], allow_none=False
        ):
            raise ValueError(
                f"{phase} Advisory Design binding has invalid NOT_APPLICABLE form"
            )
        return
    match = re.fullmatch(r"(?P<design>DES-\d{4,}); TECH: (?P<technology>.+)", cleaned)
    if match is None:
        raise ValueError(
            f"{phase} Advisory Design binding must use DES-nnnn; TECH: <TECH IDs> "
            "or DES-nnnn; TECH: NONE — <reason>"
        )
    design_revision = match.group("design")
    if (
        expected_design_revision is not None
        and design_revision != expected_design_revision
    ):
        raise ValueError(
            f"{phase} Advisory Design binding must reference {expected_design_revision}"
        )
    technology = match.group("technology")
    none_prefix = "NONE — "
    if technology.startswith(none_prefix):
        if not explicit_value(technology[len(none_prefix) :], allow_none=False):
            raise ValueError(
                f"{phase} Advisory Design binding requires a concrete NONE reason"
            )
        return
    identifiers = [item.strip() for item in technology.split(",")]
    if not identifiers or any(
        TECHNOLOGY_DECISION_ID.fullmatch(item) is None for item in identifiers
    ):
        raise ValueError(
            f"{phase} Advisory Design binding TECH values must be comma-separated TECH-nnnn IDs"
        )
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{phase} Advisory Design binding contains duplicate TECH IDs")
    if approved_tech_ids is not None:
        unknown = sorted(set(identifiers) - approved_tech_ids)
        if unknown:
            raise ValueError(
                f"{phase} Advisory Design binding references unapproved TECH IDs: "
                + ", ".join(unknown)
            )


def _unlinked_aws_core_phase_evidence_issues(
    rows: dict[tuple[str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    expected_binding: str | None = None,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
) -> list[str]:
    """Return deterministic reasons that current official evidence is not ready."""

    issues: list[str] = []
    observed_versions: set[str] = set()
    for capability in AWS_CORE_REQUIRED_CAPABILITIES:
        row = rows.get((phase, capability))
        label = f"{phase} {capability}"
        if row is None or row.observed_status not in {"PASS", "VERIFIED"}:
            issues.append(f"{label} requires fresh PASS evidence")
            continue
        if row.plugin_source != AWS_CORE_OFFICIAL_SOURCE:
            issues.append(f"{label} plugin source must be {AWS_CORE_OFFICIAL_SOURCE}")
        if row.invoked_plugin_identity != AWS_CORE_OFFICIAL_IDENTITY:
            issues.append(
                f"{label} invoked plugin identity must be {AWS_CORE_OFFICIAL_IDENTITY}"
            )
        version = clean_cell(row.observed_plugin_version)
        if AWS_CORE_PLUGIN_VERSION_PATTERN.fullmatch(version) is None:
            issues.append(
                f"{label} Observed plugin version must be an observed semantic version"
            )
        else:
            observed_versions.add(version)
        if row.observation_actor != AWS_CORE_OBSERVATION_ACTOR:
            issues.append(
                f"{label} Observation actor must be {AWS_CORE_OBSERVATION_ACTOR}"
            )
        if row.credentials_inspected != "NO":
            issues.append(f"{label} Credentials inspected must be NO")
        if row.aws_account_accessed != "NO":
            issues.append(f"{label} AWS account accessed must be NO")
        try:
            validate_advisory_design_binding(
                row.advisory_design_binding,
                phase,
                expected_design_revision=expected_design_revision,
                approved_tech_ids=approved_tech_ids,
            )
        except ValueError as exc:
            issues.append(str(exc))
        if capability == "retrieve_skill":
            try:
                require_explicit_evidence_value(
                    row.requested_skill, f"{label} Requested skill"
                )
            except ValueError as exc:
                issues.append(str(exc))
            try:
                returned_identifier = require_explicit_evidence_value(
                    row.returned_skill_identifier,
                    f"{label} Returned skill identifier",
                )
            except ValueError as exc:
                issues.append(str(exc))
            else:
                if (
                    AWS_CORE_CANONICAL_SKILL_IDENTIFIER_PATTERN.fullmatch(
                        returned_identifier
                    )
                    is None
                ):
                    issues.append(
                        f"{label} Returned skill identifier must be canonical"
                    )
        else:
            try:
                require_explicit_evidence_value(
                    row.documentation_query, f"{label} Documentation query"
                )
            except ValueError as exc:
                issues.append(str(exc))
            try:
                source_references = require_explicit_evidence_value(
                    row.source_references, f"{label} Source references"
                )
            except ValueError as exc:
                issues.append(str(exc))
            else:
                if (
                    AWS_CORE_OFFICIAL_DOCUMENTATION_REFERENCE_PATTERN.search(
                        source_references
                    )
                    is None
                ):
                    issues.append(
                        f"{label} Source references must include returned "
                        "official AWS documentation"
                    )
        if not explicit_timestamp(row.observed_at):
            issues.append(f"{label} Observed at must be ISO 8601 with timezone")
        try:
            binding = require_explicit_evidence_value(
                row.evidence_binding, f"{label} Evidence binding"
            )
        except ValueError as exc:
            issues.append(str(exc))
        else:
            if expected_binding is not None and binding != clean_cell(expected_binding):
                issues.append(
                    f"{label} Evidence binding does not match current "
                    f"{clean_cell(expected_binding)}"
                )
    if len(observed_versions) > 1:
        issues.append(
            f"{phase} capability rows must record one observed plugin version"
        )
    return issues


def aws_core_phase_evidence_issues(
    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    expected_binding: str | None = None,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
    expected_basis_ids: set[str] | None = None,
    allow_legacy_discovery: bool = False,
) -> list[str]:
    """Validate ordered, source-attributed runtime skill-discovery chains."""

    discovery_ids = sorted(
        {discovery_id for row_phase, discovery_id, _ in rows if row_phase == phase}
    )
    if not discovery_ids:
        return [f"{phase} requires at least one AWS-DISC discovery chain"]
    if "" in discovery_ids:
        if not allow_legacy_discovery or len(discovery_ids) != 1:
            return [f"{phase} legacy AWS Core evidence requires discovery migration"]
        legacy = {
            (phase, capability): rows[(phase, "", capability)]
            for capability in AWS_CORE_REQUIRED_CAPABILITIES
            if (phase, "", capability) in rows
        }
        return _unlinked_aws_core_phase_evidence_issues(
            legacy,
            phase,
            expected_binding=expected_binding,
            expected_design_revision=expected_design_revision,
            approved_tech_ids=approved_tech_ids,
        )

    issues: list[str] = []
    for discovery_id in discovery_ids:
        chain = {
            (phase, capability): rows[(phase, discovery_id, capability)]
            for capability in AWS_CORE_REQUIRED_CAPABILITIES
            if (phase, discovery_id, capability) in rows
        }
        issues.extend(
            _unlinked_aws_core_phase_evidence_issues(
                chain,
                phase,
                expected_binding=expected_binding,
                expected_design_revision=expected_design_revision,
                approved_tech_ids=approved_tech_ids,
            )
        )
        search = chain.get((phase, "search_documentation"))
        retrieve = chain.get((phase, "retrieve_skill"))
        if search is None or retrieve is None:
            issues.append(
                f"{phase} {discovery_id} requires linked search and retrieve rows"
            )
            continue

        try:
            basis_ids = _canonical_id_list(
                search.basis_ids,
                STABLE_CONTRACT_ID,
                f"{phase} {discovery_id} Basis IDs",
            )
        except ValueError as exc:
            issues.append(str(exc))
            basis_ids = []
        if expected_basis_ids is not None and set(basis_ids) != expected_basis_ids:
            issues.append(
                f"{phase} {discovery_id} Basis IDs must exactly match the current "
                "AWS materiality basis IDs"
            )
        if expected_design_revision and expected_design_revision not in basis_ids:
            issues.append(
                f"{phase} {discovery_id} Basis IDs must include {expected_design_revision}"
            )

        try:
            discovered = _canonical_id_list(
                search.discovered_skill_identifiers,
                AWS_CORE_CANONICAL_SKILL_IDENTIFIER_PATTERN,
                f"{phase} {discovery_id} Discovered skill identifiers",
            )
        except ValueError as exc:
            issues.append(str(exc))
            discovered = []

        shared = (
            "basis_ids",
            "plugin_source",
            "invoked_plugin_identity",
            "observed_plugin_version",
            "observation_actor",
            "discovered_skill_identifiers",
            "advisory_design_binding",
            "credentials_inspected",
            "aws_account_accessed",
            "evidence_binding",
        )
        for field_name in shared:
            if getattr(search, field_name) != getattr(retrieve, field_name):
                issues.append(f"{phase} {discovery_id} rows must share {field_name}")
        if retrieve.requested_skill != retrieve.returned_skill_identifier:
            issues.append(
                f"{phase} {discovery_id} retrieved identifier must equal the selected identifier"
            )
        if retrieve.returned_skill_identifier not in discovered:
            issues.append(
                f"{phase} {discovery_id} retrieved identifier was not returned by search"
            )

        if explicit_timestamp(search.observed_at) and explicit_timestamp(
            retrieve.observed_at
        ):
            searched_at = datetime.fromisoformat(
                search.observed_at.replace("Z", "+00:00")
            )
            retrieved_at = datetime.fromisoformat(
                retrieve.observed_at.replace("Z", "+00:00")
            )
            if retrieved_at < searched_at:
                issues.append(
                    f"{phase} {discovery_id} retrieve timestamp precedes search"
                )
    return issues


def derive_aws_core_observed_usage(
    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    issues: Sequence[str],
) -> dict[str, Any]:
    """Project only validated observable AWS Core use into owner-safe fields."""

    unobserved: dict[str, Any] = {
        "status": "UNOBSERVED",
        "phase": phase,
        "chains": [],
    }
    if issues:
        return unobserved
    chains: list[dict[str, Any]] = []
    discovery_ids = sorted(
        {
            discovery_id
            for row_phase, discovery_id, _capability in rows
            if row_phase == phase and discovery_id
        }
    )
    for discovery_id in discovery_ids:
        search = rows.get((phase, discovery_id, "search_documentation"))
        retrieve = rows.get((phase, discovery_id, "retrieve_skill"))
        if search is None or retrieve is None:
            continue
        references = sorted(
            set(
                AWS_CORE_OFFICIAL_DOCUMENTATION_URL_PATTERN.findall(
                    search.source_references
                )
            )
        )
        if not references:
            continue
        chains.append(
            {
                "discovery_id": discovery_id,
                "skill_identifier": retrieve.returned_skill_identifier,
                "official_references": references,
                "credentials_inspected": False,
                "aws_account_accessed": False,
            }
        )
    if not chains:
        return unobserved
    return {"status": "OBSERVED", "phase": phase, "chains": chains}


def aws_core_evidence_diagnostic_code(issue: str) -> str:
    """Classify generated AWS evidence gaps without assigning them to the owner."""

    if (
        "requires at least one AWS-DISC discovery chain" in issue
        or "requires linked search and retrieve rows" in issue
    ):
        return "AWS_CORE_DISCOVERY_REQUIRED"
    if any(
        marker in issue
        for marker in (
            "does not match current",
            "must exactly match the current",
            "must include DES-",
        )
    ):
        return "AWS_CORE_EVIDENCE_STALE"
    return "AWS_CORE_EVIDENCE_GENERATED_INVALID"


def require_aws_core_phase_evidence(
    ctx: Context,
    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    expected_binding: str | None = None,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
    expected_basis_ids: set[str] | None = None,
    allow_legacy_discovery: bool = False,
) -> None:
    """Block a phase boundary unless both official AWS Core calls are evidenced."""

    for issue in aws_core_phase_evidence_issues(
        rows,
        phase,
        expected_binding=expected_binding,
        expected_design_revision=expected_design_revision,
        approved_tech_ids=approved_tech_ids,
        expected_basis_ids=expected_basis_ids,
        allow_legacy_discovery=allow_legacy_discovery,
    ):
        ctx.error(aws_core_evidence_diagnostic_code(issue), issue, VERIFY_FILE)


def require_explicit_evidence_value(value: str, label: str) -> str:
    cleaned = clean_cell(value)
    if (
        not cleaned
        or any(character in cleaned for character in "\r\n")
        or EVIDENCE_PLACEHOLDER_PATTERN.search(cleaned) is not None
    ):
        raise ValueError(f"{label} is unresolved or placeholder evidence")
    return cleaned


def require_durable_evidence_source(value: str, label: str) -> str:
    """Require one safe local, git, artifact, HTTPS, or S3 evidence reference."""

    source = require_explicit_evidence_value(value, label)
    candidate = re.sub(r"^artifact\s*:\s*", "", source, flags=re.IGNORECASE)
    candidate_path = candidate.split("#", 1)[0]
    path_source = bool(
        re.fullmatch(
            r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+(?:#[A-Za-z0-9._-]+)?",
            candidate,
        )
        and ".." not in PurePosixPath(candidate_path).parts
    )
    if (
        re.fullmatch(r"VERIFY\.md#[A-Za-z0-9._-]+", source) is None
        and re.fullmatch(r"git:[0-9a-fA-F]{7,64}", source, re.IGNORECASE) is None
        and re.fullmatch(r"(?:https?|s3)://\S+", source, re.IGNORECASE) is None
        and not path_source
    ):
        raise ValueError(f"{label} is not a local durable reference")
    return source


def validate_done_evidence(verify_text: str | None, task: InspectedTask) -> None:
    evidence = clean_cell(task.metadata.get("Evidence", ""))
    references = [match.group(0) for match in EVIDENCE_PATTERN.finditer(evidence)]
    local = [
        reference for reference in references if re.fullmatch(r"EV-\d{4,}", reference)
    ]
    invalid_local = [
        reference
        for reference in references
        if LOCAL_EVIDENCE_LIKE.fullmatch(reference) is not None
        and re.fullmatch(r"EV-\d{4,}", reference) is None
    ]
    if invalid_local:
        raise ValueError(
            f"{task.task_id}: invalid local Evidence ID: {', '.join(invalid_local)}"
        )
    if not local:
        raise ValueError(
            f"{task.task_id}: DONE requires at least one local Evidence reference"
        )
    if len(local) != len(set(local)):
        raise ValueError(f"{task.task_id}: local Evidence references must be unique")
    if verify_text is None:
        raise ValueError(f"{task.task_id}: local Evidence requires VERIFY.md")
    rows = parse_task_completion_evidence(verify_text)
    for reference in local:
        matching = [row for row in rows if row.evidence_id == reference]
        if len(matching) != 1:
            raise ValueError(
                f"{task.task_id}: Evidence is not recorded in VERIFY.md: {reference}"
            )
        row = matching[0]
        if row.task_id != task.task_id:
            raise ValueError(
                f"{task.task_id}: Evidence row names the wrong task {row.task_id!r}"
            )
        label = f"{task.task_id} Evidence {row.evidence_id}"
        require_explicit_evidence_value(row.command_or_observation, f"{label} command")
        require_explicit_evidence_value(row.result, f"{label} result")
        require_explicit_evidence_value(row.actor, f"{label} actor")
        if not explicit_timestamp(row.observed_at):
            raise ValueError(f"{label} observed time must be ISO 8601 with timezone")
        material = require_explicit_evidence_value(
            row.commit_worktree_artifact, f"{label} commit/worktree/artifact"
        )
        if (
            re.search(r"\b[0-9a-fA-F]{7,64}\b", material) is None
            and re.search(
                r"\b(?:worktree|artifact)\s*[:=]\s*\S+", material, re.IGNORECASE
            )
            is None
        ):
            raise ValueError(
                f"{label} requires an explicit commit, worktree, or artifact"
            )
        require_durable_evidence_source(row.durable_source, f"{label} durable source")
        if row.status not in TASK_COMPLETION_EVIDENCE_STATUSES:
            raise ValueError(f"{label} status must be LOCAL_PASS or VERIFIED")


def parse_task_write_set(value: str, task_id: str) -> list[str]:
    value = clean_cell(value)
    if value in {"", "TODO", "TBD", "UNKNOWN"}:
        raise ValueError(f"{task_id}: unresolved Write set")
    if value == "NONE":
        return []
    result: list[str] = []
    for item in (part.strip() for part in value.split(",")):
        broad = item.endswith("/**")
        base = item[:-3] if broad else item
        pure = PurePosixPath(base)
        if (
            not base
            or pure.is_absolute()
            or "\\" in item
            or any(part.casefold() in {"", ".", "..", ".git"} for part in pure.parts)
            or any(character in base for character in "*?[]{}")
            or pure.as_posix() != base
        ):
            raise ValueError(f"{task_id}: unsafe Write set entry {item!r}")
        result.append(item)
    if len(result) != len({item.casefold() for item in result}):
        raise ValueError(f"{task_id}: duplicate Write set entry")
    return result


def parse_task_external_state(value: str, task_id: str) -> list[str]:
    value = clean_cell(value)
    if value in {"", "TODO", "TBD", "UNKNOWN"}:
        raise ValueError(f"{task_id}: unresolved External state")
    if value == "NONE":
        return []
    values = [item.strip() for item in value.split(",")]
    if any(
        not item or any(character in item for character in "*?[]{}") for item in values
    ):
        raise ValueError(f"{task_id}: ambiguous External state")
    if len(values) != len({item.casefold() for item in values}):
        raise ValueError(f"{task_id}: duplicate External state entry")
    return values


def task_waiver_rows(text: str) -> dict[str, tuple[str, str, str, str, str]]:
    marker = "### Dependency waiver registry"
    if text.count(marker) != 1:
        raise ValueError("Expected exactly one dependency waiver registry")
    body = text.split(marker, 1)[1].split("\n## ", 1)[0]
    result: dict[str, tuple[str, str, str, str, str]] = {}
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [clean_cell(item) for item in split_table_row(line)]
        if len(cells) != 6 or cells[0] in {"Waiver ID", "---", "NONE"}:
            continue
        if re.fullmatch(r"WAIVER-\d+", cells[0]) is None:
            continue
        if cells[0] in result:
            raise ValueError(f"Duplicate waiver ID: {cells[0]}")
        result[cells[0]] = (cells[1], cells[2], cells[3], cells[4], cells[5])
    return result


def declared_task_waivers(task: InspectedTask) -> dict[str, str]:
    raw = clean_cell(task.metadata.get("Dependency waivers", "NONE"))
    if raw in {"", "NONE", "-"}:
        return {}
    result: dict[str, str] = {}
    for entry in raw.split(","):
        pair = [item.strip() for item in entry.split("=", 1)]
        if (
            len(pair) != 2
            or re.fullmatch(r"TASK-\d+", pair[0]) is None
            or re.fullmatch(r"WAIVER-\d+", pair[1]) is None
        ):
            raise ValueError(f"{task.task_id}: invalid dependency waiver {entry!r}")
        result[pair[0]] = pair[1]
    return result


def validate_task_records(
    text: str,
    snapshot: dict[str, str],
    verify_text: str | None = None,
    approved_tech_ids: set[str] | None = None,
    property_execution_by_id: dict[str, PropertyExecution] | None = None,
    technology_decisions_by_id: dict[str, TechnologyDecision] | None = None,
) -> tuple[list[InspectedTask], dict[str, InspectedTask], list[str]]:
    tasks = inspect_task_blocks(text)
    by_id: dict[str, InspectedTask] = {}
    errors: list[str] = []
    waivers = task_waiver_rows(text)
    current_req = snapshot.get("Requirements revision", "")
    current_des = snapshot.get("Design revision", "")
    current_auth = snapshot.get("Construction authorization", "")
    done_property_ids = {
        property_id
        for task in tasks
        if task.status == "DONE"
        for property_id in PROPERTY_ID.findall(
            clean_cell(task.metadata.get("Requirements", ""))
        )
    }
    property_evidence_rows: list[PropertyTestEvidenceRow] = []
    completion_evidence_rows: list[TaskCompletionEvidenceRow] = []
    property_section_present = bool(
        verify_text is not None
        and re.search(
            rf"^{re.escape(PROPERTY_TEST_EVIDENCE_HEADING)}[ \t]*$",
            without_fenced_code(verify_text),
            re.MULTILINE,
        )
    )
    if verify_text is not None and property_section_present:
        try:
            property_evidence_rows = parse_property_test_evidence(verify_text)
        except ValueError as exc:
            errors.append(str(exc))
    observed_property_evidence = any(
        row.result in {"PASS", "FAIL"} for row in property_evidence_rows
    )
    if done_property_ids or observed_property_evidence:
        if verify_text is None:
            errors.append(
                "DONE property tasks require VERIFY.md property-test evidence"
            )
        elif not property_section_present:
            errors.append(
                "VERIFY.md requires exactly one Property-based test evidence section"
            )
        else:
            try:
                completion_evidence_rows = parse_task_completion_evidence(verify_text)
            except ValueError as exc:
                errors.append(str(exc))

    for task in tasks:
        execution_contract_required = task.status in {
            "READY",
            "IN_PROGRESS",
            "BLOCKED",
            "DONE",
        } or (task.status == "BACKLOG" and snapshot.get("Task-plan state") == "CURRENT")
        if task.task_id in by_id:
            errors.append(f"Duplicate task ID: {task.task_id}")
        by_id[task.task_id] = task
        for key in sorted(task.duplicates):
            errors.append(f"{task.task_id}: duplicate {key} metadata")
        for key in TASK_METADATA_KEYS:
            if key not in task.metadata:
                errors.append(f"{task.task_id}: missing {key} metadata")
        if task.status not in TASK_STATUSES:
            errors.append(f"{task.task_id}: invalid status {task.status!r}")
            continue
        try:
            budget = int(clean_cell(task.metadata.get("Attempt budget", "")))
            used = int(clean_cell(task.metadata.get("Attempts used", "")))
            if budget < 1 or used < 0 or used > budget:
                raise ValueError
        except ValueError:
            errors.append(f"{task.task_id}: invalid attempt counters")
            budget = used = 0
        aws_mode = clean_cell(task.metadata.get("AWS mode", "")).upper()
        if aws_mode not in TASK_AWS_MODES:
            errors.append(f"{task.task_id}: invalid AWS mode {aws_mode!r}")
        for field_name, expected, pattern in (
            ("Requirements", current_req, REQ_ID),
            ("Authorization", current_auth, AUTH_ID),
        ):
            match = pattern.search(clean_cell(task.metadata.get(field_name, "")))
            if match is None or match.group(0) != expected:
                errors.append(
                    f"{task.task_id}: {field_name} does not match current execution basis"
                )
        design_value = clean_cell(task.metadata.get("Design", ""))
        technology_refs: list[str] = []
        if execution_contract_required:
            design_match = TASK_DESIGN_TRACE_PATTERN.fullmatch(design_value)
            if design_match is None:
                errors.append(
                    f"{task.task_id}: Design must exactly match "
                    "DES-nnnn; TECH: TECH-nnnn[, TECH-nnnn...] or "
                    "DES-nnnn; TECH: NONE — no technology/toolchain impact"
                )
            else:
                if design_match.group("design") != current_des:
                    errors.append(
                        f"{task.task_id}: Design does not match current execution basis"
                    )
                technologies = design_match.group("technologies")
                technology_refs = technologies.split(", ") if technologies else []
                if len(technology_refs) != len(set(technology_refs)):
                    errors.append(f"{task.task_id}: duplicate TECH reference in Design")
                if approved_tech_ids is not None:
                    unknown = [
                        tech_id
                        for tech_id in technology_refs
                        if tech_id not in approved_tech_ids
                    ]
                    if unknown:
                        errors.append(
                            f"{task.task_id}: Design references unapproved TECH IDs: "
                            + ", ".join(unknown)
                        )
        else:
            design_match = DES_ID.search(design_value)
            if design_match is None or design_match.group(0) != current_des:
                errors.append(
                    f"{task.task_id}: Design does not match current execution basis"
                )
        if (
            task.status in {"READY", "IN_PROGRESS"}
            and snapshot.get("Gate B state") != "APPROVED_FOR_CONSTRUCTION"
        ):
            errors.append(f"{task.task_id}: Gate B is not approved for construction")
        if (
            task.status in {"READY", "IN_PROGRESS"}
            and snapshot.get("Task-plan state") != "CURRENT"
        ):
            errors.append(f"{task.task_id}: task plan is not CURRENT")
        try:
            parse_task_write_set(task.metadata.get("Write set", ""), task.task_id)
            parse_task_external_state(
                task.metadata.get("External state", ""), task.task_id
            )
        except ValueError as exc:
            errors.append(str(exc))
        run_id = clean_cell(task.metadata.get("Run ID", "NONE"))
        if task.status == "IN_PROGRESS":
            if (
                run_id != snapshot.get("Active run ID")
                or snapshot.get("Run state") != "RUNNING"
                or clean_cell(task.metadata.get("Owner", ""))
                in {"", "NONE", "UNASSIGNED"}
                or used < 1
                or CHECKPOINT_ID.fullmatch(
                    clean_cell(task.metadata.get("Last checkpoint", ""))
                )
                is None
            ):
                errors.append(f"{task.task_id}: invalid IN_PROGRESS claim")
        elif run_id != "NONE":
            errors.append(f"{task.task_id}: non-IN_PROGRESS task must use Run ID NONE")
        if task.status == "READY" and used >= budget:
            errors.append(f"{task.task_id}: attempt budget exhausted")
        if task.status == "DONE":
            evidence = clean_cell(task.metadata.get("Evidence", ""))
            if (
                evidence in {"", "NONE", "TODO"}
                or EVIDENCE_PATTERN.search(evidence) is None
            ):
                errors.append(f"{task.task_id}: DONE requires Evidence")
            try:
                validate_done_evidence(verify_text, task)
            except ValueError as exc:
                errors.append(str(exc))
        if task.status == "BLOCKED" and clean_cell(
            task.metadata.get("Blocker", "")
        ) in {"", "NONE", "TODO"}:
            errors.append(f"{task.task_id}: BLOCKED requires a blocker")
        if task.status == "SKIPPED" and clean_cell(
            task.metadata.get("Skip record", "")
        ) in {"", "NONE", "TODO"}:
            errors.append(f"{task.task_id}: SKIPPED requires a skip record")
        updated = clean_cell(task.metadata.get("Last updated", ""))
        if updated not in {"", "TODO"} and not explicit_timestamp(updated):
            errors.append(
                f"{task.task_id}: Last updated must be ISO 8601 with timezone"
            )
        try:
            declared = declared_task_waivers(task)
            for dependency_id, waiver_id in declared.items():
                waiver = waivers.get(waiver_id)
                if waiver is None:
                    errors.append(
                        f"{task.task_id}: unknown dependency waiver {waiver_id}"
                    )
                elif waiver[0] != dependency_id or waiver[1] != task.task_id:
                    errors.append(
                        f"{task.task_id}: waiver {waiver_id} does not match its task pair"
                    )
        except ValueError as exc:
            errors.append(str(exc))
        if execution_contract_required:
            sections, duplicate_sections = inspect_task_sections(task.block)
            for name in sorted(duplicate_sections):
                errors.append(f"{task.task_id}: duplicate required section #### {name}")
            for name in (
                "Outcome",
                "Acceptance criteria",
                "Validation",
                "Execution log",
            ):
                if name not in sections:
                    errors.append(
                        f"{task.task_id}: missing required section #### {name}"
                    )
            outcome = sections.get("Outcome", "")
            if not outcome.strip() or "TODO" in outcome.upper():
                errors.append(f"{task.task_id}: unresolved Outcome")
            acceptance = sections.get("Acceptance criteria", "")
            if "- [" not in acceptance or "TODO" in acceptance.upper():
                errors.append(
                    f"{task.task_id}: objective acceptance criteria are required"
                )
            validation = sections.get("Validation", "")
            if "```" not in validation or "TODO" in validation.upper():
                errors.append(
                    f"{task.task_id}: executable validation commands are required"
                )
            try:
                validate_task_property_execution_projection(
                    validation,
                    task.task_id,
                    task.metadata.get("Requirements", ""),
                    technology_refs,
                    property_execution_by_id,
                )
            except ValueError as exc:
                errors.append(str(exc))
            execution_log = sections.get("Execution log", "")
            normalized_log = execution_log.strip().upper().replace("_", " ")
            if not execution_log.strip() or "TODO" in execution_log.upper():
                errors.append(f"{task.task_id}: execution log must be explicit")
            if task.status == "DONE" and any(
                marker in normalized_log
                for marker in (
                    "TODO",
                    "TBD",
                    "NOT STARTED",
                    "NO EXECUTION HAS BEEN RECORDED",
                )
            ):
                errors.append(
                    f"{task.task_id}: DONE requires an observed Execution log"
                )
            if task.status == "DONE" and "- [ ]" in acceptance:
                errors.append(
                    f"{task.task_id}: DONE has incomplete acceptance criteria"
                )

    observed_property_pairs = {
        (row.task_id, row.property_id)
        for row in property_evidence_rows
        if row.result in {"PASS", "FAIL"}
    }
    done_property_pairs = {
        (task.task_id, property_id)
        for task in tasks
        if task.status == "DONE"
        for property_id in PROPERTY_ID.findall(
            clean_cell(task.metadata.get("Requirements", ""))
        )
    }
    for task_id, property_id in sorted(observed_property_pairs | done_property_pairs):
        task = by_id.get(task_id)
        if task is None:
            errors.append(
                f"{task_id} {property_id}: observed property-test evidence "
                "references an unknown current task"
            )
            continue
        task_property_ids = set(
            PROPERTY_ID.findall(clean_cell(task.metadata.get("Requirements", "")))
        )
        if property_id not in task_property_ids:
            errors.append(
                f"{task_id} {property_id}: observed property-test evidence is not "
                "linked by the current task Requirements"
            )
            continue
        if property_execution_by_id is None:
            errors.append(
                f"{task_id} {property_id}: current property execution contract is "
                "unavailable"
            )
            continue
        expected = property_execution_by_id.get(property_id)
        if expected is None:
            errors.append(
                f"{task_id} {property_id}: observed property-test evidence "
                "references an unknown current property contract"
            )
            continue
        technology = (technology_decisions_by_id or {}).get(expected.framework_tech_id)
        if technology is None:
            errors.append(
                f"{task_id}: {property_id} requires its current PROPERTY_TESTING "
                "technology decision"
            )
            continue
        try:
            validate_done_property_evidence(
                property_evidence_rows,
                task,
                snapshot,
                expected,
                technology,
                completion_evidence_rows,
                require_done_pass=task.status == "DONE",
            )
        except ValueError as exc:
            errors.append(str(exc))

    for task in tasks:
        for dependency in task.dependencies:
            if dependency not in by_id:
                errors.append(f"{task.task_id}: missing dependency {dependency}")
            elif dependency == task.task_id:
                errors.append(f"{task.task_id}: cannot depend on itself")

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            start = stack.index(task_id)
            raise ValueError(
                "Dependency cycle detected: " + " -> ".join([*stack[start:], task_id])
            )
        visiting.add(task_id)
        stack.append(task_id)
        for dependency in by_id[task_id].dependencies:
            if dependency in by_id:
                visit(dependency)
        stack.pop()
        visiting.remove(task_id)
        visited.add(task_id)

    try:
        for task_id in sorted(by_id):
            visit(task_id)
    except ValueError as exc:
        errors.append(str(exc))

    for waiver_id, waiver in waivers.items():
        skipped_id, applies_to, authority, rationale, recorded_at = waiver
        if skipped_id not in by_id or applies_to not in by_id:
            errors.append(f"{waiver_id}: references an unknown task")
            continue
        if by_id[skipped_id].status != "SKIPPED":
            errors.append(f"{waiver_id}: dependency is not SKIPPED")
        if skipped_id not in by_id[applies_to].dependencies:
            errors.append(f"{waiver_id}: skipped task is not a dependency")
        authority_is_current = bool(
            re.fullmatch(
                rf"{re.escape(current_auth)}(?:\s+clause\s+[A-Za-z0-9._:-]+)?",
                authority,
            )
            or re.fullmatch(r"OWNER-DECISION-\d+", authority)
        )
        if not authority_is_current:
            errors.append(f"{waiver_id}: authority is not an exact current authority")
        if not explicit_value(rationale) or EVIDENCE_PATTERN.search(rationale) is None:
            errors.append(f"{waiver_id}: missing rationale or preserved evidence")
        if not explicit_timestamp(recorded_at):
            errors.append(f"{waiver_id}: Recorded at must be ISO 8601 with timezone")

    ready: list[str] = []
    for task in tasks:
        if task.status != "READY":
            continue
        declared = declared_task_waivers(task)
        satisfied = True
        for dependency_id in task.dependencies:
            dependency = by_id.get(dependency_id)
            if dependency is None:
                satisfied = False
            elif dependency.status == "DONE":
                continue
            elif dependency.status == "SKIPPED":
                waiver_id = declared.get(dependency_id)
                waiver = waivers.get(waiver_id or "")
                if (
                    waiver is None
                    or waiver[0] != dependency_id
                    or waiver[1] != task.task_id
                ):
                    satisfied = False
                else:
                    authority, rationale, recorded_at = waiver[2], waiver[3], waiver[4]
                    current_auth_match = re.search(
                        rf"(?<![A-Z0-9-]){re.escape(current_auth)}(?!\d)", authority
                    )
                    owner_match = re.search(r"\bOWNER-DECISION-\d+\b", authority)
                    if (
                        (current_auth_match is None and owner_match is None)
                        or unresolved(rationale)
                        or rationale == "NONE"
                        or unresolved(recorded_at)
                    ):
                        satisfied = False
            else:
                satisfied = False
        if satisfied:
            ready.append(task.task_id)
    if errors:
        raise ValueError("\n".join(errors))
    return tasks, by_id, ready


def missing_current_property_task_coverage(
    tasks: list[InspectedTask],
    plan_state: str,
    property_execution_by_id: dict[str, PropertyExecution],
) -> list[str]:
    """Return approved properties omitted from a current task plan."""

    if plan_state != "CURRENT":
        return []
    covered_property_ids = {
        property_id
        for task in tasks
        if task.status in {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE"}
        for property_id in PROPERTY_ID.findall(
            clean_cell(task.metadata.get("Requirements", ""))
        )
    }
    return sorted(set(property_execution_by_id) - covered_property_ids)


def task_requirement_rules(
    prd_text: str,
    requirements_contract: RequirementsContract,
) -> dict[str, tuple[str, str]]:
    """Return current requirement ID to acceptance ID and EARS form."""

    if requirements_contract.grandfathered_approved_gate_a:
        return {}
    rows, acceptance_by_requirement, _legacy_ids = _schema_13_requirement_rows(prd_text)
    row_by_id = {row[0]: row for row in rows}
    expected_requirements = set(requirements_contract.requirement_ids)
    if set(row_by_id) != expected_requirements:
        raise ValueError(
            "Task requirement rules do not match the current requirements contract"
        )
    expected_acceptance = set(requirements_contract.acceptance_ids)
    observed_acceptance = {
        acceptance_by_requirement.get(requirement_id, "")
        for requirement_id in expected_requirements
    }
    if observed_acceptance != expected_acceptance:
        raise ValueError(
            "Task acceptance rules do not match the current requirements contract"
        )
    return {
        requirement_id: (
            acceptance_by_requirement[requirement_id],
            row_by_id[requirement_id][2],
        )
        for requirement_id in sorted(expected_requirements)
    }


def task_requirement_evidence_dispositions(
    verify_text: str | None,
    expected_basis: Mapping[str, str],
    rules: Mapping[str, tuple[str, str]],
) -> tuple[
    dict[str, tuple[str, tuple[str, ...]]],
    tuple[str, ...],
]:
    """Resolve current no-task requirement dispositions from VERIFY.md."""

    if verify_text is None or not rules:
        return {}, ()
    try:
        active_scope = table_after_heading(verify_text, "## Active evidence scope")
        rows = parse_verification_matrix(verify_text)
    except ValueError as exc:
        return {}, (str(exc),)
    for key in (
        "Requirements revision",
        "Design revision",
        "Construction authorization",
    ):
        if clean_cell(active_scope.get(key, "")) != clean_cell(
            expected_basis.get(key, "")
        ):
            return {}, ()

    issues: list[str] = []
    by_requirement: dict[str, dict[str, list[str]]] = {}
    seen_evidence_ids: set[str] = set()
    for row in rows:
        status = clean_cell(row.get("Status", "")).upper()
        if status not in {"LOCAL_PASS", "VERIFIED", "NOT_APPLICABLE"}:
            continue
        if clean_cell(row.get("Task IDs", "")).upper() != "NONE":
            continue
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id) is None:
            issues.append(
                "No-task requirement evidence requires an EV-nnnn Evidence ID"
            )
            continue
        if evidence_id in seen_evidence_ids:
            issues.append(f"Duplicate no-task requirement evidence ID {evidence_id}")
            continue
        seen_evidence_ids.add(evidence_id)
        try:
            basis_ids = _canonical_id_list(
                row.get("PRD / property IDs", ""),
                STABLE_CONTRACT_ID,
                f"{evidence_id} PRD / property IDs",
            )
        except ValueError as exc:
            issues.append(str(exc))
            continue
        matching_requirements = [
            requirement_id
            for requirement_id, (acceptance_id, _ears_form) in rules.items()
            if basis_ids == [requirement_id, acceptance_id]
        ]
        if len(matching_requirements) != 1:
            issues.append(
                f"{evidence_id}: no-task evidence must bind exactly one current "
                "requirement and its canonical acceptance ID"
            )
            continue
        requirement_id = matching_requirements[0]
        acceptance_id, ears_form = rules[requirement_id]
        requirement_or_invariant = clean_cell(row.get("Requirement or invariant", ""))
        artifact = clean_cell(row.get("Artifact/environment", ""))
        automated = clean_cell(row.get("Automated evidence", ""))
        manual = clean_cell(row.get("AWS/manual evidence", ""))
        if not explicit_value(requirement_or_invariant, allow_none=False):
            issues.append(
                f"{evidence_id}: no-task evidence requires a concrete requirement or invariant"
            )
        if not explicit_value(artifact, allow_none=False):
            issues.append(
                f"{evidence_id}: no-task evidence requires a concrete artifact/environment"
            )
        if not (
            explicit_value(automated, allow_none=False)
            or explicit_value(manual, allow_none=False)
        ):
            issues.append(
                f"{evidence_id}: no-task evidence requires automated or AWS/manual evidence"
            )
        disposition = (
            "NOT_APPLICABLE" if status == "NOT_APPLICABLE" else "ALREADY_SATISFIED"
        )
        if disposition == "NOT_APPLICABLE" and ears_form != "OPTIONAL_FEATURE":
            issues.append(
                f"{evidence_id}: NOT_APPLICABLE is allowed only for OPTIONAL_FEATURE requirements"
            )
            continue
        by_requirement.setdefault(requirement_id, {}).setdefault(
            disposition, []
        ).append(evidence_id)
        if acceptance_id not in basis_ids:
            issues.append(
                f"{evidence_id}: missing canonical acceptance ID {acceptance_id}"
            )

    dispositions: dict[str, tuple[str, tuple[str, ...]]] = {}
    for requirement_id, observed in sorted(by_requirement.items()):
        if len(observed) != 1:
            issues.append(
                f"{requirement_id}: conflicting no-task evidence dispositions"
            )
            continue
        disposition, evidence_ids = next(iter(observed.items()))
        dispositions[requirement_id] = (
            disposition,
            tuple(sorted(evidence_ids)),
        )
    return dispositions, tuple(issues)


def derive_task_requirement_coverage(
    tasks: Sequence[Any],
    plan_state: str,
    rules: Mapping[str, tuple[str, str]],
    evidence_dispositions: Mapping[str, tuple[str, tuple[str, ...]]],
) -> TaskRequirementCoverageResult:
    """Derive one complete disposition for every approved requirement."""

    if plan_state != "CURRENT" or not rules:
        return TaskRequirementCoverageResult()
    counted_statuses = {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE"}
    acceptance_owner = {
        acceptance_id: requirement_id
        for requirement_id, (acceptance_id, _ears_form) in rules.items()
    }
    requirement_families = {
        requirement_id.rsplit("-", 1)[0] for requirement_id in rules
    }
    covered_by_task: dict[str, set[str]] = {
        requirement_id: set() for requirement_id in rules
    }
    trace_issues: list[str] = []
    evidence_issues: list[str] = []
    for task in tasks:
        task_id = str(getattr(task, "task_id", "TASK-UNKNOWN"))
        status = clean_cell(getattr(task, "status", "")).upper()
        metadata = getattr(task, "metadata", {})
        requirements_value = clean_cell(metadata.get("Requirements", ""))
        tokens = STABLE_CONTRACT_ID.findall(requirements_value)
        relevant_tokens = [
            token
            for token in tokens
            if token in rules
            or token in acceptance_owner
            or ACCEPTANCE_ID.fullmatch(token) is not None
            or token.rsplit("-", 1)[0] in requirement_families
        ]
        duplicates = sorted(
            token for token in set(relevant_tokens) if relevant_tokens.count(token) > 1
        )
        if duplicates:
            trace_issues.append(
                f"{task_id}: duplicate requirement/acceptance IDs: "
                + ", ".join(duplicates)
            )
        unknown_acceptance = sorted(
            {
                token
                for token in relevant_tokens
                if ACCEPTANCE_ID.fullmatch(token) is not None
                and token not in acceptance_owner
            }
        )
        if unknown_acceptance:
            trace_issues.append(
                f"{task_id}: unknown acceptance IDs: " + ", ".join(unknown_acceptance)
            )
        unknown_requirements = sorted(
            {
                token
                for token in relevant_tokens
                if ACCEPTANCE_ID.fullmatch(token) is None
                and token not in rules
                and token.rsplit("-", 1)[0] in requirement_families
            }
        )
        if unknown_requirements:
            trace_issues.append(
                f"{task_id}: unknown approved-requirement references: "
                + ", ".join(unknown_requirements)
            )
        token_set = set(relevant_tokens)
        valid_pairs: set[str] = set()
        for requirement_id, (acceptance_id, _ears_form) in rules.items():
            has_requirement = requirement_id in token_set
            has_acceptance = acceptance_id in token_set
            if has_requirement and not has_acceptance:
                trace_issues.append(
                    f"{task_id}: {requirement_id} requires {acceptance_id}"
                )
            if has_acceptance and not has_requirement:
                trace_issues.append(
                    f"{task_id}: {acceptance_id} requires owning requirement {requirement_id}"
                )
            if has_requirement and has_acceptance:
                valid_pairs.add(requirement_id)
        if status in counted_statuses:
            for requirement_id in valid_pairs:
                covered_by_task[requirement_id].add(task_id)

    records: list[TaskRequirementCoverage] = []
    missing: list[str] = []
    for requirement_id, (acceptance_id, _ears_form) in sorted(rules.items()):
        task_ids = tuple(sorted(covered_by_task[requirement_id]))
        evidence = evidence_dispositions.get(requirement_id)
        if task_ids:
            if evidence is not None and evidence[0] == "NOT_APPLICABLE":
                evidence_issues.append(
                    f"{requirement_id}: task coverage conflicts with NOT_APPLICABLE evidence"
                )
            records.append(
                TaskRequirementCoverage(
                    requirement_id,
                    acceptance_id,
                    "TASK_COVERED",
                    task_ids=task_ids,
                )
            )
        elif evidence is not None:
            records.append(
                TaskRequirementCoverage(
                    requirement_id,
                    acceptance_id,
                    evidence[0],
                    evidence_ids=evidence[1],
                )
            )
        else:
            missing.append(requirement_id)
    return TaskRequirementCoverageResult(
        records=tuple(records),
        trace_issues=tuple(trace_issues),
        evidence_issues=tuple(evidence_issues),
        missing_requirement_ids=tuple(missing),
    )


def parse_positive_cost(
    value: str,
    pattern: re.Pattern[str],
    field_name: str,
) -> tuple[str, Decimal]:
    """Parse one finite positive ISO-currency amount in canonical form."""

    cleaned = clean_cell(value)
    match = pattern.fullmatch(cleaned)
    if match is None:
        raise ValueError(
            f"{field_name} must use a finite positive currency amount such as "
            "USD: 20.00"
        )
    try:
        amount = Decimal(match.group("amount"))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} amount is invalid") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"{field_name} amount must be finite and positive")
    currency = match.group("currency")
    if currency not in ISO_4217_CURRENCY_CODES:
        raise ValueError(
            f"{field_name} currency must be a current ISO 4217 List One code"
        )
    return currency, amount


def parse_cost_posture(value: str) -> tuple[str, Decimal] | None:
    """Return an optional owner hard cap from the canonical Gate A posture."""

    cleaned = clean_cell(value)
    if cleaned == DEFAULT_COST_POSTURE:
        return None
    match = COST_POSTURE_WITH_CAP.fullmatch(cleaned)
    if match is None:
        raise ValueError(
            "Cost posture must be MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED or "
            "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00"
        )
    return parse_positive_cost(
        f"{match.group('currency')}: {match.group('amount')}",
        AWS_COST_CEILING,
        "Cost posture hard cap",
    )


def validate_aws_cost_ceiling(value: str, cost_posture: str) -> None:
    """Require a finite mutation ceiling and honor any Gate A owner cap."""

    currency, amount = parse_positive_cost(
        value,
        AWS_COST_CEILING,
        "AWS cost ceiling",
    )
    owner_cap = parse_cost_posture(cost_posture)
    if owner_cap is None:
        return
    cap_currency, cap_amount = owner_cap
    if currency != cap_currency:
        raise ValueError(
            "AWS cost ceiling currency must match the Gate A owner hard cap"
        )
    if amount > cap_amount:
        raise ValueError("AWS cost ceiling exceeds the Gate A owner hard cap")


def explicit_timestamp(value: str) -> bool:
    cleaned = clean_cell(value)
    if unresolved(cleaned):
        return False
    candidate = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def explicit_human_approver(value: str) -> bool:
    """Require an explicit owner identity that is not an agent or automation."""

    cleaned = clean_cell(value)
    return explicit_value(cleaned) and NON_HUMAN_APPROVER.search(cleaned) is None


def task_property_execution_table(
    validation_section: str, task_id: str
) -> ContractTable | None:
    """Return the one exact property-execution projection outside code fences."""

    structural = without_fenced_code(validation_section)
    source_lines = validation_section.splitlines()
    structural_lines = structural.splitlines()
    matches: list[ContractTable] = []
    index = 0
    while index < len(source_lines):
        if not structural_lines[index].strip().startswith("|"):
            index += 1
            continue
        raw_lines: list[str] = []
        while index < len(source_lines) and structural_lines[index].strip().startswith(
            "|"
        ):
            raw_lines.append(source_lines[index])
            index += 1
        header = split_markdown_table_row(raw_lines[0])
        if header is None or not header or clean_cell(header[0]) != "Property ID":
            continue
        try:
            matches.append(
                _parse_contract_table_lines(raw_lines, PROPERTY_EXECUTION_HEADERS)
            )
        except ValueError as exc:
            raise ValueError(f"{task_id}: property execution projection {exc}") from exc
    if len(matches) > 1:
        raise ValueError(
            f"{task_id}: Validation must contain exactly one property execution projection"
        )
    return matches[0] if matches else None


def validate_task_property_execution_projection(
    validation_section: str,
    task_id: str,
    requirements: str,
    technology_refs: list[str],
    property_execution_by_id: dict[str, PropertyExecution] | None,
) -> None:
    """Require an exact PRD projection and one exact command per referenced property."""

    property_ids = PROPERTY_ID.findall(clean_cell(requirements))
    if len(property_ids) != len(set(property_ids)):
        raise ValueError(f"{task_id}: Requirements contains duplicate PROP IDs")
    table = task_property_execution_table(validation_section, task_id)
    if not property_ids:
        if table is not None:
            raise ValueError(
                f"{task_id}: Validation has a property execution projection without a PROP requirement"
            )
        return
    if property_execution_by_id is None:
        raise ValueError(
            f"{task_id}: property execution contract is unavailable for PROP validation"
        )
    unknown = [item for item in property_ids if item not in property_execution_by_id]
    if unknown:
        raise ValueError(
            f"{task_id}: Requirements references unknown PROP IDs: "
            + ", ".join(unknown)
        )
    if table is None:
        raise ValueError(
            f"{task_id}: Validation requires the exact property execution projection"
        )
    projected_ids = [row[0] for row in table.rows]
    if projected_ids != property_ids or len(projected_ids) != len(set(projected_ids)):
        raise ValueError(
            f"{task_id}: property execution projection IDs must exactly match Requirements"
        )
    for row in table.rows:
        expected = property_execution_by_id[row[0]]
        if not valid_property_execution_command(expected.exact_command):
            raise ValueError(
                f"{task_id}: {row[0]} Exact command is not an executable local command"
            )
        if not valid_property_execution_command(row[2]):
            raise ValueError(
                f"{task_id}: projected {row[0]} Exact command is not an executable "
                "local command"
            )
        expected_row = (
            expected.property_id,
            expected.framework_tech_id,
            expected.exact_command,
            expected.run_target_time_bound,
            expected.seed_or_reproduction_format,
            expected.evidence_destination,
        )
        if row != expected_row:
            raise ValueError(
                f"{task_id}: property execution projection for {row[0]} does not match the PRD contract"
            )
        if expected.framework_tech_id not in technology_refs:
            raise ValueError(
                f"{task_id}: Design must reference {expected.framework_tech_id} for {row[0]}"
            )
    commands = validation_commands(validation_section, task_id)
    for command in dict.fromkeys(
        property_execution_by_id[item].exact_command for item in property_ids
    ):
        if commands.count(command) != 1:
            raise ValueError(
                f"{task_id}: property command {command!r} must appear exactly once in Validation"
            )


def _heading_title_span(text: str, title: str) -> SourceSpan:
    """Resolve one visible Markdown heading title without inspecting fences."""

    structural = without_fenced_code(text)
    matches = list(
        re.finditer(
            rf"^(?P<marks>#{{1,6}})[ \t]+(?:\d+(?:\.\d+)*\.?[ \t]+)?{re.escape(title)}[ \t]*\r?$",
            structural,
            re.MULTILINE,
        )
    )
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one heading title {title!r}; found {len(matches)}"
        )
    level = len(matches[0].group("marks"))
    following = re.search(
        rf"^#{{1,{level}}}[ \t]+", structural[matches[0].end() :], re.MULTILINE
    )
    end = matches[0].end() + following.start() if following else len(text)
    return SourceSpan(matches[0].start(), end)


def parse_property_test_evidence(text: str) -> list[PropertyTestEvidenceRow]:
    """Parse the exact durable property-test evidence table from VERIFY.md."""

    table = contract_table_after_heading(
        text,
        PROPERTY_TEST_EVIDENCE_HEADING,
        PROPERTY_TEST_EVIDENCE_HEADERS,
    )
    if table is None:
        raise ValueError(
            "VERIFY.md requires exactly one Property-based test evidence section"
        )
    rows: list[PropertyTestEvidenceRow] = []
    seen_evidence_ids: set[str] = set()
    for cells in table.rows:
        row = PropertyTestEvidenceRow(*cells)
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError(
                "VERIFY.md Property-based test evidence Evidence ID must be EV-nnnn"
            )
        if row.evidence_id in seen_evidence_ids:
            raise ValueError(
                "VERIFY.md Property-based test evidence Evidence IDs must be unique"
            )
        seen_evidence_ids.add(row.evidence_id)
        if PROPERTY_ID.fullmatch(row.property_id) is None:
            raise ValueError(
                "VERIFY.md Property-based test evidence Property ID must be PROP-nnn"
            )
        if row.result not in PROPERTY_TEST_RESULTS:
            raise ValueError(
                f"{row.property_id}: property-test Result must be NOT_STARTED, PASS, or FAIL"
            )
        rows.append(row)
    return rows


def parse_observed_property_run(value: str) -> tuple[int, Decimal]:
    """Parse one exact observed case count and elapsed duration."""

    match = re.fullmatch(
        r"CASES: (?P<cases>[1-9]\d*); "
        r"ELAPSED_SECONDS: (?P<seconds>\d+(?:\.\d+)?)",
        clean_cell(value),
    )
    if match is None:
        raise ValueError(
            "Observed run must be CASES: <positive integer>; "
            "ELAPSED_SECONDS: <nonnegative number>"
        )
    elapsed = Decimal(match.group("seconds"))
    if not elapsed.is_finite() or elapsed < 0:
        raise ValueError("ELAPSED_SECONDS must be finite and nonnegative")
    return int(match.group("cases")), elapsed


def technology_version_policy_allows(policy: str, observed: str) -> bool:
    """Check an observed exact version against the machine-comparable policy forms."""

    if technology_contract_value_is_unresolved(
        policy
    ) or technology_contract_value_is_unresolved(observed):
        return False
    if policy.startswith("EXACT: "):
        return observed == policy.removeprefix("EXACT: ")
    observed_parts = parsed_numeric_version(observed)
    if observed_parts is None:
        return False
    if policy.startswith("COMPATIBLE_MAJOR: "):
        return observed_parts[0] == int(policy.removeprefix("COMPATIBLE_MAJOR: "))
    if policy.startswith("MINIMUM: "):
        minimum = parsed_numeric_version(policy.removeprefix("MINIMUM: "))
        if minimum is None:
            return False
        width = max(len(observed_parts), len(minimum))
        return observed_parts + (0,) * (width - len(observed_parts)) >= minimum + (
            0,
        ) * (width - len(minimum))
    # These policies require external evidence mapping the observed version to
    # the dated LTS release or organization constraint. A numeric-looking
    # version alone cannot prove either policy, so local validation fails closed.
    return False


def replay_evidence_matches_contract(
    approved_format: str,
    observed_replay: str,
    exact_command: str,
) -> bool:
    """Bind replay evidence to the current PRD reproduction-format contract."""

    approved = clean_cell(approved_format)
    observed = clean_cell(observed_replay)
    if unresolved(approved) or unresolved(observed):
        return False
    lowered_approved = approved.casefold()
    lowered_observed = observed.casefold()
    if EVIDENCE_PLACEHOLDER_PATTERN.search(observed) is not None or re.search(
        r"\b(?:unavailable|missing|not[ _-]*recorded|not[ _-]*captured)\b",
        lowered_observed,
    ):
        return False
    if "seed" in lowered_approved:
        match = re.fullmatch(
            r"(?:seed\s*[:=]\s*|.*(?:^|\s)--seed(?:=|\s+))(?P<seed>\S+)",
            observed,
            re.IGNORECASE,
        )
        if match is None:
            return False
        seed = match.group("seed").strip("'\"")
        if not seed or EVIDENCE_PLACEHOLDER_PATTERN.fullmatch(seed) is not None:
            return False
        if "integer" in lowered_approved and re.fullmatch(r"\d+", seed) is None:
            return False
        return True
    if "command" in lowered_approved:
        return observed == exact_command
    return observed == approved


def evidence_timestamp(value: str, label: str) -> datetime:
    if not explicit_timestamp(value):
        raise ValueError(f"{label} must be ISO 8601 with timezone")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_done_property_evidence(
    rows: list[PropertyTestEvidenceRow],
    task: InspectedTask,
    snapshot: dict[str, str],
    expected: PropertyExecution,
    technology: TechnologyDecision,
    completion_rows: list[TaskCompletionEvidenceRow],
    *,
    require_done_pass: bool = True,
) -> None:
    """Validate observed property history and, for DONE, require a final pass."""

    task_id = task.task_id
    if expected.evidence_destination != PROPERTY_TEST_EVIDENCE_DESTINATION:
        raise ValueError(
            f"{task_id}: {expected.property_id} PRD evidence destination does not "
            "identify the exact VERIFY.md property evidence section"
        )
    observed = [
        row
        for row in rows
        if row.task_id == task_id
        and row.property_id == expected.property_id
        and row.result in {"PASS", "FAIL"}
    ]
    if not observed and require_done_pass:
        raise ValueError(
            f"{task_id}: DONE {expected.property_id} requires observed property-test evidence"
        )
    if not observed:
        return
    expected_basis = (
        f"{snapshot.get('Requirements revision', '')} / "
        f"{snapshot.get('Design revision', '')} / "
        f"{snapshot.get('Construction authorization', '')}"
    )
    completion_by_id = {row.evidence_id: row for row in completion_rows}
    task_evidence_ids = set(
        LOCAL_EVIDENCE_ID.findall(clean_cell(task.metadata.get("Evidence", "")))
    )
    passing = False
    timestamps: list[tuple[datetime, PropertyTestEvidenceRow]] = []
    for index, row in enumerate(observed, start=1):
        label = f"{task_id} {expected.property_id} evidence row {index}"
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError(f"{label} Evidence ID must be EV-nnnn")
        if row.requirements_design_authorization != expected_basis:
            raise ValueError(f"{label} REQ / DES / AUTH is not current")
        if row.framework_tech_id != expected.framework_tech_id:
            raise ValueError(
                f"{label} Framework TECH ID does not match the current PRD property contract"
            )
        if row.framework_selection != technology.selection:
            raise ValueError(
                f"{label} Framework selection does not match {technology.decision_id}"
            )
        observed_version = require_explicit_evidence_value(
            row.observed_exact_version,
            f"{label} observed exact version",
        )
        if not technology_version_policy_allows(
            technology.version_policy, observed_version
        ):
            raise ValueError(
                f"{label} observed exact version does not satisfy "
                f"{technology.version_policy}"
            )
        if row.exact_command != expected.exact_command:
            raise ValueError(
                f"{label} Exact command does not match the current PRD property contract"
            )
        try:
            observed_cases, observed_seconds = parse_observed_property_run(
                row.observed_run
            )
            minimum_cases, maximum_seconds = parse_property_run_target(
                expected.run_target_time_bound
            )
        except ValueError as exc:
            raise ValueError(f"{label} {exc}") from exc
        replay = require_explicit_evidence_value(
            row.replay_seed_or_exact_command,
            f"{label} replay seed or exact command",
        )
        if not replay_evidence_matches_contract(
            expected.seed_or_reproduction_format,
            replay,
            expected.exact_command,
        ):
            raise ValueError(
                f"{label} replay evidence does not match the approved PRD "
                "Seed or reproduction format"
            )
        observed_at = evidence_timestamp(row.observed_at, f"{label} Observed at")
        timestamps.append((observed_at, row))
        material = require_explicit_evidence_value(
            row.commit_worktree_artifact,
            f"{label} commit/worktree/artifact",
        )
        require_durable_evidence_source(row.durable_source, f"{label} durable source")
        completion = completion_by_id.get(row.evidence_id)
        if completion is None:
            raise ValueError(
                f"{label} Evidence ID is missing from Task completion evidence"
            )
        if (
            completion.task_id != task_id
            or completion.command_or_observation != row.exact_command
            or completion.observed_at != row.observed_at
            or completion.commit_worktree_artifact != material
            or completion.durable_source != row.durable_source
        ):
            raise ValueError(
                f"{label} does not match its Task completion evidence binding"
            )
        require_explicit_evidence_value(
            completion.result,
            f"{label} Task completion result",
        )
        require_explicit_evidence_value(
            completion.actor,
            f"{label} Task completion actor",
        )
        if row.result == "PASS":
            passing = True
            if require_done_pass and row.evidence_id not in task_evidence_ids:
                raise ValueError(
                    f"{label} PASS Evidence ID is not cited by the DONE task"
                )
            if completion.status not in TASK_COMPLETION_EVIDENCE_STATUSES:
                raise ValueError(
                    f"{label} PASS completion status must be LOCAL_PASS or VERIFIED"
                )
            if minimum_cases is not None and observed_cases < minimum_cases:
                raise ValueError(
                    f"{label} observed cases do not meet MIN_CASES: {minimum_cases}"
                )
            if maximum_seconds is not None and observed_seconds > maximum_seconds:
                raise ValueError(
                    f"{label} elapsed time exceeds MAX_SECONDS: {maximum_seconds}"
                )
            if row.minimized_counterexample != "NONE":
                raise ValueError(
                    f"{label} PASS must record Minimized counterexample as NONE"
                )
            if row.failure_class_resolution != "NONE":
                raise ValueError(
                    f"{label} PASS must record Failure class / resolution as NONE"
                )
            continue
        if completion.status != "FAILED":
            raise ValueError(f"{label} FAIL completion status must be FAILED")
        counterexample = require_explicit_evidence_value(
            row.minimized_counterexample,
            f"{label} minimized counterexample",
        )
        if counterexample == "NONE":
            raise ValueError(f"{label} FAIL requires a minimized counterexample")
        failure_match = re.fullmatch(
            "(?P<class>"
            + "|".join(sorted(PROPERTY_TEST_FAILURE_CLASSES))
            + r") — (?P<resolution>.+)",
            row.failure_class_resolution,
        )
        if failure_match is None:
            raise ValueError(
                f"{label} FAIL requires one supported failure class and a concrete "
                "resolution separated by an em dash"
            )
        try:
            require_explicit_evidence_value(
                failure_match.group("resolution"),
                f"{label} failure resolution",
            )
        except ValueError as exc:
            raise ValueError(
                f"{label} FAIL requires one supported failure class and a concrete "
                "resolution separated by an em dash"
            ) from exc
    if len({stamp for stamp, _row in timestamps}) != len(timestamps):
        raise ValueError(
            f"{task_id}: {expected.property_id} observed timestamps must be unique"
        )
    if require_done_pass and not passing:
        raise ValueError(
            f"{task_id}: DONE {expected.property_id} requires preserved failure rows "
            "and a later PASS row"
        )
    latest = max(timestamps, key=lambda item: item[0])[1]
    if require_done_pass and latest.result != "PASS":
        raise ValueError(
            f"{task_id}: DONE {expected.property_id} requires the latest observed "
            "property-test result to be PASS"
        )


MAX_REQUIRED_FILES = 512
MAX_REQUIRED_FILE_BYTES = 16 * 1024 * 1024
MAX_PROJECT_SOURCE_BYTES = 64 * 1024 * 1024
BINARY_REQUIRED_SUFFIXES = frozenset({".png"})

MANIFEST_POLICY = ManifestPolicy(
    manifest_file=MANIFEST_FILE,
    prompt_file=PROMPT_FILE,
    mandatory_required_files=frozenset(MANDATORY_REQUIRED_FILES),
    control_hash_files=frozenset(CONTROL_HASH_FILES),
    canonical_placeholders=frozenset(CANONICAL_PLACEHOLDERS),
    max_required_files=MAX_REQUIRED_FILES,
    binary_required_suffixes=BINARY_REQUIRED_SUFFIXES,
)

STATE_POLICY = StatePolicy(
    state_file=STATE_FILE,
    project_name_token=PROJECT_NAME_TOKEN,
    setup_status_token="{{SETUP_STATUS}}",
    setup_method_token="{{SETUP_METHOD}}",
    aws_region_token="{{AWS_REGION}}",
    cost_posture_token="{{COST_POSTURE}}",
    project_modes=frozenset(PROJECT_MODES),
    delivery_profiles=frozenset(DELIVERY_PROFILES),
    risk_levels=frozenset(RISK_LEVELS),
    aws_lanes=frozenset(AWS_LANES),
    brownfield_states=frozenset(BROWNFIELD_STATES),
    gate_a_states=frozenset(GATE_A_STATES),
    gate_b_states=frozenset(GATE_B_STATES),
    run_modes=frozenset(RUN_MODES),
    run_states=frozenset(RUN_STATES),
    req_id=REQ_ID,
    des_id=DES_ID,
    auth_id=AUTH_ID,
    plan_id=PLAN_ID,
    task_id=TASK_ID,
    run_id=RUN_ID,
    checkpoint_id=CHECKPOINT_ID,
)


def safe_read_required_binary(
    ctx: Context, relative: str, *, required: bool = True
) -> bytes | None:
    """Read one explicitly supported binary package file within integrity bounds."""

    cached = ctx.source_file_bytes.get(relative)
    if cached is not None:
        return cached
    try:
        snapshot = ctx._observer.observe_binary(relative)
    except ObservationError as exc:
        if required or exc.code != "REQUIRED_FILE_MISSING":
            ctx.error(exc.code, exc.message, exc.path)
        return None
    ctx.source_bytes_read = ctx._observer.bytes_observed
    ctx.source_file_bytes[relative] = snapshot.raw_bytes
    return snapshot.raw_bytes


def safe_read_text(ctx: Context, relative: str, *, required: bool = True) -> str | None:
    cached = ctx.texts.get(relative)
    if cached is not None:
        return cached
    try:
        snapshot = ctx._observer.observe_text(relative)
    except ObservationError as exc:
        if required or exc.code != "REQUIRED_FILE_MISSING":
            ctx.error(exc.code, exc.message, exc.path)
        return None
    presentation_text = snapshot.presentation_text
    canonical_text = snapshot.canonical_text
    if presentation_text is None or canonical_text is None:
        ctx.error(
            "REQUIRED_FILE_UNREADABLE",
            "Unable to read UTF-8 text: snapshot did not contain text",
            relative,
        )
        return None
    ctx.source_file_bytes[relative] = snapshot.raw_bytes
    ctx.source_bytes_read = ctx._observer.bytes_observed
    ctx.presentation_texts[relative] = presentation_text
    ctx.texts[relative] = canonical_text
    return canonical_text


def bounded_prd_snapshot(
    root: Path, expected_sha256: str | None = None
) -> tuple[str, str]:
    """Read one normalized, size-bounded PRD snapshot and bind it by digest."""

    snapshot_context = Context(root=root.resolve())
    text = safe_read_text(snapshot_context, PRD_FILE)
    if text is None or snapshot_context.has_errors:
        raise ValueError("Unable to read a bounded PRD snapshot")
    raw_text = snapshot_context.presentation_texts.get(PRD_FILE, text)
    digest = (
        "sha256:"
        + hashlib.sha256(
            canonical_bytes_without_generated_summary(raw_text)
        ).hexdigest()
    )
    if expected_sha256 is not None and (
        re.fullmatch(r"sha256:[0-9a-f]{64}", expected_sha256) is None
        or digest != expected_sha256
    ):
        raise ValueError("PRD snapshot changed after project inspection")
    return text, digest


def load_json_document(ctx: Context, relative: str, code: str) -> dict[str, Any] | None:
    text = safe_read_text(ctx, relative)
    if text is None:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        ctx.error(code, f"Expected JSON-compatible YAML: {exc}", relative)
        return None
    if not isinstance(value, dict):
        ctx.error(code, "Top-level value must be an object", relative)
        return None
    return value


OWNER_CONFIRMATION_FIELDS = {
    "INTAKE-0001": "starting point",
    "INTAKE-0002": "users",
    "INTAKE-0003": "problem",
    "INTAKE-0004": "first useful outcome",
    "INTAKE-0005": "first-release boundary",
    "INTAKE-0006": "success measure",
    "INTAKE-0007": "data handled",
    "INTAKE-0008": "data access and sensitivity",
    "INTAKE-0009": "initial audience",
    "INTAKE-0010": "operating geography",
}


def _owner_locator_for_heading(
    text: str,
    *,
    key: str,
    label: str,
    heading: str,
    required: bool = True,
) -> dict[str, Any]:
    """Resolve a brief locator through the Engine's canonical heading parser."""

    span = _heading_title_span(text, heading)
    start_line = text.count("\n", 0, span.start) + 1
    end_offset = max(span.start, span.end - 1)
    end_line = text.count("\n", 0, end_offset) + 1
    return owner_source_locator(
        key=key,
        label=label,
        path=PRD_FILE,
        heading=heading,
        start_line=start_line,
        end_line=end_line,
        section_text=text[span.start : span.end],
        required=required,
    )


def _owner_decision_section(
    section_id: str,
    title: str,
    items: Sequence[str],
    basis_ids: Sequence[str],
) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "title": title,
        "items": [clean_cell(item) for item in items if clean_cell(item)],
        "basis_ids": sorted(
            {
                clean_cell(item)
                for item in basis_ids
                if explicit_value(clean_cell(item), allow_none=False)
            }
        ),
    }


OWNER_INTAKE_DECISION_METADATA = {
    "OWNER_WORK_CONTEXT": (
        "product",
        "Starting point",
        "This determines whether Fastlane creates a new application or preserves an existing system.",
    ),
    "PRIMARY_USERS": (
        "product",
        "Primary users",
        "This keeps the first release focused on the people who must receive value.",
    ),
    "OWNER_STATED_PROBLEM": (
        "product",
        "Problem to solve",
        "This is the user problem every first-release capability must address.",
    ),
    "OBSERVABLE_OUTCOME": (
        "product",
        "First useful outcome",
        "This defines the end-to-end result the application must make possible.",
    ),
    "FIRST_RELEASE_BOUNDARY": (
        "scope",
        "First-release boundary",
        "This separates essential first-release work from explicit deferrals.",
    ),
    "SUCCESS_MEASURE": (
        "success",
        "Success measure",
        "This gives the owner an observable way to decide whether the first release is useful.",
    ),
    "DATA_TYPES": (
        "data/access",
        "Data handled",
        "This determines the data the application must accept, generate, protect, and delete.",
    ),
    "DATA_SENSITIVITY": (
        "data/access",
        "Data sensitivity and access",
        "This sets the practical privacy and access boundary for the first release.",
    ),
    "RELEASE_AUDIENCE": (
        "scope",
        "Initial audience",
        "This limits who may use the first release and how broadly it may be shared.",
    ),
    "OPERATING_GEOGRAPHY": (
        "operations",
        "Operating geography",
        "This records any material service-area or data-location constraint.",
    ),
}

OWNER_TECHNICAL_DOMAIN_METADATA = {
    "application/runtime": (
        "OWNER-DES-0001",
        "Application and runtime",
        "This defines the application shape, runtime, framework, and one approved source location.",
        ("technology-register", "selected-architecture", "construction-boundary"),
    ),
    "identity": (
        "OWNER-DES-0002",
        "Identity and authorization",
        "This defines who can sign in and which data and actions each identity may access.",
        ("technology-register", "interfaces", "aws-implementation"),
    ),
    "data": (
        "OWNER-DES-0003",
        "Data and storage",
        "This defines where project data lives and how ownership, retention, deletion, and recovery are enforced.",
        ("technology-register", "data-lifecycle", "aws-implementation"),
    ),
    "messaging": (
        "OWNER-DES-0004",
        "Messaging and retries",
        "This defines whether work is synchronous or queued and how duplicate, delayed, and failed work is handled.",
        ("technology-register", "interfaces", "aws-implementation"),
    ),
    "edge/networking": (
        "OWNER-DES-0005",
        "Edge and networking",
        "This defines how users reach the application and which network boundaries remain private or public.",
        ("technology-register", "components", "aws-implementation"),
    ),
    "observability": (
        "OWNER-DES-0006",
        "Observability and incident response",
        "This defines what operators can see when the application is slow, failing, or being misused.",
        ("technology-register", "validation-strategy", "aws-implementation"),
    ),
    "deployment/recovery": (
        "OWNER-DES-0007",
        "Deployment and recovery",
        "This defines how the application is released, rolled back, restored, and eventually removed.",
        ("technology-register", "release-acceptance", "construction-boundary"),
    ),
    "validation/construction": (
        "OWNER-DES-0008",
        "Validation and construction",
        "This defines the checks and boundaries Codex must satisfy before calling local construction complete.",
        ("technology-register", "harness-profile", "construction-boundary"),
    ),
}

TECHNOLOGY_CONCERN_DOMAINS = {
    "APPLICATION_RUNTIME": "application/runtime",
    "APPLICATION_FRAMEWORK": "application/runtime",
    "FRONTEND_FRAMEWORK": "application/runtime",
    "IDENTITY_AUTHORIZATION": "identity",
    "DATA_STORAGE": "data",
    "MESSAGING_RETRIES": "messaging",
    "EDGE_NETWORKING": "edge/networking",
    "OBSERVABILITY_INCIDENT_RESPONSE": "observability",
    "INFRASTRUCTURE_AS_CODE": "deployment/recovery",
    "DEPLOYMENT_TOOLING": "deployment/recovery",
    "RELIABILITY_RECOVERY": "deployment/recovery",
    "PACKAGE_BUILD_TOOLING": "validation/construction",
    "TEST_TOOLING": "validation/construction",
    "PROPERTY_TESTING": "validation/construction",
    "SECURITY_VALIDATION": "validation/construction",
}


def _owner_technical_domain(concern: str) -> str:
    exact = TECHNOLOGY_CONCERN_DOMAINS.get(concern)
    if exact is not None:
        return exact
    lowered = concern.lower()
    groups = (
        ("identity", ("identity", "auth", "access", "secret")),
        ("data", ("data", "database", "storage", "schema")),
        ("messaging", ("message", "event", "queue", "stream")),
        ("edge/networking", ("edge", "network", "dns", "cdn", "api gateway")),
        ("observability", ("observ", "logging", "metric", "trace", "alarm")),
        (
            "deployment/recovery",
            ("deploy", "release", "rollback", "recover", "migration", "iac"),
        ),
        (
            "validation/construction",
            ("test", "validation", "build", "lint", "format", "harness"),
        ),
    )
    for domain, markers in groups:
        if any(marker in lowered for marker in markers):
            return domain
    return "application/runtime"


def _unique_owner_text(values: Iterable[str]) -> list[str]:
    return list(
        dict.fromkeys(clean_cell(value) for value in values if clean_cell(value))
    )


def _owner_stable_ids(values: Iterable[str]) -> list[str]:
    return sorted(
        {
            identifier
            for value in values
            for identifier in re.findall(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b", value)
        }
    )


def _owner_readable_journeys(prd_text: str, journey_ids: Sequence[str]) -> list[str]:
    try:
        table = contract_table_after_heading(prd_text, JOURNEY_HEADING, JOURNEY_HEADERS)
    except ValueError:
        return list(journey_ids)
    if table is None:
        return list(journey_ids)
    by_id = {row[0]: row for row in table.rows}
    readable: list[str] = []
    for journey_id in journey_ids:
        row = by_id.get(journey_id)
        if row is None:
            readable.append(journey_id)
            continue
        goal = clean_cell(row[2])
        outcome = clean_cell(row[4])
        readable.append(f"{journey_id} — {goal}; success means {outcome}")
    return readable


def _derive_gate_a_decision_inventory(
    prd_text: str,
    intake_contract: IntakeFoundationContract,
    requirements_contract: RequirementsContract,
    *,
    status: str,
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    decisions: list[dict[str, Any]] = []
    try:
        table = contract_table_after_heading(
            prd_text, INTAKE_FOUNDATION_HEADING, INTAKE_FOUNDATION_HEADERS
        )
    except ValueError as exc:
        table = None
        issues.append(f"Gate A owner decisions could not be resolved: {exc}")
    expected_ids = list(intake_contract.basis_ids)
    if table is not None:
        for intake_id, field_name, value, basis, row_status, _response in table.rows:
            if row_status != "CONFIRMED" or intake_id not in intake_contract.basis_ids:
                continue
            metadata = OWNER_INTAKE_DECISION_METADATA.get(field_name)
            if metadata is None:
                issues.append(f"{intake_id} has no owner-facing decision metadata")
                continue
            domain, title, owner_effect = metadata
            decisions.append(
                {
                    "decision_id": intake_id,
                    "domain": domain,
                    "title": title,
                    "selection": value,
                    "source": "Validated owner intake",
                    "maturity": "CONFIRMED_BY_OWNER",
                    "owner_effect": owner_effect,
                    "why": "This value was confirmed by the owner and bound to the current intake record.",
                    "alternatives": "Not applicable — this records the owner's answer rather than an agent-selected alternative.",
                    "tradeoff": owner_effect,
                    "risk_and_mitigation": "A later change requires requirements revalidation before Gate A can remain current.",
                    "evidence_status": "CONFIRMED_BY_OWNER — validated owner-response provenance is current.",
                    "reconsider_when": "Reconsider when the owner changes this answer or its requirement basis.",
                    "basis_ids": [intake_id],
                    "evidence_ids": [],
                    "source_locator_keys": ["owner-decisions"],
                }
            )
    active_assumptions = [
        item
        for item in requirements_contract.assumptions
        if item.status not in {"INVALIDATED", "SUPERSEDED"}
    ]
    expected_ids.extend(item.assumption_id for item in active_assumptions)
    for assumption in active_assumptions:
        maturity = (
            "CONFIRMED_BY_OWNER"
            if assumption.status in {"ACCEPTED", "VALIDATED"}
            else "PLANNED_AFTER_APPROVAL"
        )
        decisions.append(
            {
                "decision_id": assumption.assumption_id,
                "domain": "assumption",
                "title": "Assumption",
                "selection": assumption.assumption,
                "source": "Gate A assumption record",
                "maturity": maturity,
                "owner_effect": "Gate A either accepts this assumption explicitly or returns it for correction.",
                "why": "The requirements analysis identified this assumption as material to the first release.",
                "alternatives": "The owner may reject or replace the assumption before approving Gate A.",
                "tradeoff": "Accepting it enables design to proceed; changing it may alter scope or feasibility.",
                "risk_and_mitigation": f"Validation or successor: {assumption.validation_or_successor}",
                "evidence_status": f"{maturity} — assumption state {assumption.status}.",
                "reconsider_when": "Reconsider when its basis, validation result, or owner acceptance changes.",
                "basis_ids": [assumption.assumption_id, *assumption.basis_ids],
                "evidence_ids": [],
                "source_locator_keys": ["requirements"],
            }
        )
    actual_ids = [item["decision_id"] for item in decisions]
    if actual_ids != expected_ids:
        issues.append(
            "Gate A decision inventory must cover every confirmed intake and active assumption exactly once"
        )
    projection = {
        "schema_version": 1,
        "kind": "GATE_A",
        "status": status,
        "required_domains": [],
        "decisions": decisions,
    }
    finalized, validation_issues = finalize_owner_decision_inventory(projection)
    return finalized, [*issues, *validation_issues]


def _source_disposition_owner_parts(
    source_disposition: ApplicationSourceDisposition,
) -> tuple[str, str, str, str, str]:
    if source_disposition.kind == APPLICATION_SOURCE_GREENFIELD:
        return (
            "New application code has one predictable home under app/, with tests and infrastructure in their own roots.",
            "A singular application root prevents competing app, apps, or src trees.",
            "apps/** and src/** were rejected because parallel roots make ownership, imports, tests, and packaging ambiguous.",
            "The selected framework must fit under app/; approved root toolchain files remain allowed.",
            "Reopen only if an approved product or framework constraint cannot be satisfied under app/**.",
        )
    if source_disposition.kind == APPLICATION_SOURCE_BROWNFIELD:
        return (
            "Existing application source stays in the recorded preserved roots.",
            "Preserving the observed layout avoids an unapproved migration.",
            "A parallel app/** root was rejected unless the owner-approved preservation contract authorizes migration.",
            "The existing layout may be less uniform, but continuity takes priority.",
            "Reopen when the owner approves a source migration or the brownfield baseline changes.",
        )
    return (
        "This work changes infrastructure only and creates no application source tree.",
        "The approved work kind has no application runtime, so app/** would be misleading.",
        "Creating app/**, apps/**, or src/** was rejected because application behavior is outside scope.",
        "Application code requires a later design-controlled change.",
        "Reopen when application behavior enters the approved scope.",
    )


def _derive_gate_b_decision_inventory(
    design_contract: DesignContract,
    requirements_revision: str,
    design_revision: str,
    authorization_id: str,
    *,
    status: str,
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    grouped: dict[str, list[TechnologyDecision]] = {
        domain: [] for domain in TECHNICAL_DOMAIN_ORDER
    }
    for technology in design_contract.technology_decisions:
        grouped[_owner_technical_domain(technology.concern)].append(technology)

    selection = design_contract.architecture.selection
    source_disposition = design_contract.project_contract.application_source_disposition
    all_evidence = list(design_contract.architecture.aws_evidence)
    decisions: list[dict[str, Any]] = []
    for domain in TECHNICAL_DOMAIN_ORDER:
        technologies = grouped[domain]
        if not technologies:
            if status == "READY":
                issues.append(
                    f"Gate B decision domain {domain} has no canonical technology decision"
                )
            continue
        decision_id, title, owner_effect, locator_keys = (
            OWNER_TECHNICAL_DOMAIN_METADATA[domain]
        )
        rationales: list[str] = []
        alternatives: list[str] = []
        for technology in technologies:
            try:
                rationale, rejected = technology_reasoning_parts(
                    technology.alternatives_and_rationale
                )
            except ValueError as exc:
                if status == "READY":
                    issues.append(f"{technology.decision_id}: {exc}")
                continue
            rationales.append(rationale)
            alternatives.append(rejected)
        basis_ids = _owner_stable_ids(
            [requirements_revision, design_revision, authorization_id]
            + [technology.basis_ids for technology in technologies]
        )
        technology_ids = {technology.decision_id for technology in technologies}
        evidence = [
            item
            for item in all_evidence
            if technology_ids & set(re.findall(r"\bTECH-\d{4}\b", item.design_ids))
        ]
        selections = [
            f"{technology.concern.replace('_', ' ').title()}: {technology.selection}"
            for technology in technologies
        ]
        tradeoffs = [technology.compatibility_migration for technology in technologies]
        safeguards = [technology.validation for technology in technologies]
        reconsider = [
            f"{technology.concern.replace('_', ' ').title()} policy {technology.version_policy}"
            for technology in technologies
        ]
        source_keys = list(locator_keys)
        if domain == "application/runtime" and selection is not None:
            selections.insert(
                0, f"Whole-system architecture: {selection.selected_candidate}"
            )
            rationales.insert(0, selection.rationale)
            alternatives.insert(0, selection.rejected_alternatives)
            tradeoffs.extend([selection.operational_burden, selection.cost_effect])
            safeguards.extend([selection.risks, selection.mitigations])
            reconsider.extend([selection.revisit_triggers, selection.breakpoints])
            basis_ids = sorted(set(basis_ids) | {selection.architecture_id})
        if domain == "application/runtime" and source_disposition is not None:
            (
                source_effect,
                source_why,
                source_alternatives,
                source_tradeoff,
                source_reconsider,
            ) = _source_disposition_owner_parts(source_disposition)
            selections.append(
                f"Application source: {source_disposition.canonical_value}"
            )
            rationales.append(source_why)
            alternatives.append(source_alternatives)
            tradeoffs.append(source_tradeoff)
            safeguards.append(source_effect)
            reconsider.append(source_reconsider)
        if domain == "deployment/recovery" and selection is not None:
            safeguards.extend([selection.reliability_impact, selection.migration_path])
        if domain == "identity" and selection is not None:
            safeguards.append(selection.security_impact)
        if domain == "validation/construction" and design_contract.harness.rows:
            selections.append(
                f"Harness Profile: {len(design_contract.harness.rows)} recorded checks"
            )
            rationales.append(
                "The approved checks bind construction completion to executable evidence."
            )
            alternatives.append(
                "A check may be omitted only with a concrete NOT_APPLICABLE reason."
            )
            tradeoffs.append(
                "More validation takes time but reduces undetected defects."
            )
            safeguards.append(
                "Exact commands and durable evidence prevent overstated readiness."
            )
            reconsider.append(
                "Revisit when tooling, design, or applicable quality risks change."
            )
            basis_ids = sorted(
                set(basis_ids) | set(design_contract.harness.required_ids)
            )
        evidence_ids = [item.evidence_id for item in evidence]
        maturity = "SOURCE_VERIFIED" if evidence_ids else "PLANNED_AFTER_APPROVAL"
        evidence_status = (
            "SOURCE_VERIFIED — " + ", ".join(evidence_ids)
            if evidence_ids
            else "PLANNED_AFTER_APPROVAL — this canonical design decision has not been observed in a deployed environment."
        )
        decisions.append(
            {
                "decision_id": decision_id,
                "domain": domain,
                "title": title,
                "selection": "; ".join(_unique_owner_text(selections)),
                "source": "Canonical Design-7 architecture and technology records",
                "maturity": maturity,
                "owner_effect": owner_effect,
                "why": " ".join(_unique_owner_text(rationales)),
                "alternatives": " ".join(_unique_owner_text(alternatives)),
                "tradeoff": " ".join(_unique_owner_text(tradeoffs)),
                "risk_and_mitigation": " ".join(_unique_owner_text(safeguards)),
                "evidence_status": evidence_status,
                "reconsider_when": " ".join(_unique_owner_text(reconsider)),
                "basis_ids": basis_ids,
                "evidence_ids": evidence_ids,
                "source_locator_keys": source_keys,
            }
        )
    projection = {
        "schema_version": 1,
        "kind": "GATE_B",
        "status": status,
        "required_domains": list(TECHNICAL_DOMAIN_ORDER),
        "decisions": decisions,
    }
    finalized, validation_issues = finalize_owner_decision_inventory(projection)
    return finalized, [*issues, *validation_issues]


def derive_owner_decision_brief(
    prd_text: str,
    prd_fields: Mapping[str, str],
    intake_contract: IntakeFoundationContract,
    requirements_contract: RequirementsContract,
    design_contract: DesignContract,
    envelope: Mapping[str, str],
    *,
    has_errors: bool,
    enabled: bool,
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[str, str]]]:
    """Derive one fail-closed gate view and its complete decision inventory."""

    if not enabled:
        return empty_owner_decision_brief(), empty_owner_decision_inventory(), []
    requirements_revision = clean_cell(prd_fields.get("requirements_revision", ""))
    design_revision = clean_cell(prd_fields.get("design_revision", ""))
    authorization_id = clean_cell(prd_fields.get("construction_authorization", ""))
    gate_a = clean_cell(prd_fields.get("gate_a", "BLOCKED"))
    gate_b = clean_cell(prd_fields.get("gate_b", "BLOCKED"))
    if gate_a != "APPROVED_FOR_DESIGN":
        kind = "GATE_A"
    elif gate_b != "APPROVED_FOR_CONSTRUCTION":
        kind = "GATE_B"
    else:
        return empty_owner_decision_brief(), empty_owner_decision_inventory(), []

    basis = {
        "requirements_revision": requirements_revision
        if REQ_ID.fullmatch(requirements_revision)
        else None,
        "design_revision": design_revision
        if kind == "GATE_B" and DES_ID.fullmatch(design_revision)
        else None,
        "construction_authorization": authorization_id
        if kind == "GATE_B" and AUTH_ID.fullmatch(authorization_id)
        else None,
        "design_contract_sha256": design_contract.canonical_sha256
        if kind == "GATE_B"
        else None,
    }
    state_value = gate_a if kind == "GATE_A" else gate_b
    contract_ready = (
        requirements_contract.status in {"READY", "GRANDFATHERED"}
        if kind == "GATE_A"
        else design_contract.status == "READY"
    )
    if state_value == "STALE":
        status = "STALE"
    elif state_value == "PENDING_OWNER_APPROVAL":
        status = "READY" if contract_ready and not has_errors else "BLOCKED"
    else:
        status = "BUILDING"

    issues: list[tuple[str, str]] = []
    try:
        gate_a_card = table_after_heading(prd_text, "### Gate A — readiness card")
    except ValueError as exc:
        gate_a_card = {}
        issues.append(("OWNER_BRIEF_SOURCE_MISMATCH", str(exc)))
    sections: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    locators: list[dict[str, Any]] = []
    technical_groups: list[dict[str, Any]] = []

    if kind == "GATE_A":
        inventory, inventory_issues = _derive_gate_a_decision_inventory(
            prd_text, intake_contract, requirements_contract, status=status
        )
        try:
            gate_a_analysis = table_after_heading(
                prd_text, "### Gate A — agent analysis record"
            )
        except ValueError as exc:
            gate_a_analysis = {}
            issues.append(("OWNER_BRIEF_SOURCE_MISMATCH", str(exc)))
        readable_journeys = _owner_readable_journeys(
            prd_text, requirements_contract.journey_ids
        )
        sections = [
            _owner_decision_section(
                "GATE-A-OUTCOME",
                "Outcome, users, and first useful journey",
                [
                    "Outcome: " + gate_a_card.get("Outcome", "Not yet recorded."),
                    "Owner and users: "
                    + gate_a_card.get("Owner and users", "Not yet recorded."),
                    "First-release journey: "
                    + ("; ".join(readable_journeys) or "Not yet recorded."),
                ],
                [requirements_revision, *intake_contract.basis_ids],
            ),
            _owner_decision_section(
                "GATE-A-BOUNDARY",
                "First-release boundary",
                [
                    "Scope and non-goals: "
                    + gate_a_card.get("Scope and non-goals", "Not yet recorded."),
                    "Data and access: "
                    + gate_a_card.get("Data boundary", "Not yet recorded.")
                    + " "
                    + gate_a_card.get(
                        "Identity/security boundary", "Not yet recorded."
                    ),
                ],
                [requirements_revision, *requirements_contract.requirement_ids],
            ),
            _owner_decision_section(
                "GATE-A-SUCCESS",
                "Success, resilience, Region, and cost",
                [
                    "Success measures: "
                    + gate_a_card.get(
                        "Measurable requirement/acceptance IDs", "Not yet recorded."
                    ),
                    "Recovery, Region, and cost: "
                    + gate_a_card.get("Failure/recovery", "Not yet recorded.")
                    + "; "
                    + gate_a_card.get("Environment/Region", "Not yet recorded.")
                    + "; "
                    + gate_a_card.get("Cost posture", "Not yet recorded."),
                ],
                [requirements_revision, *requirements_contract.acceptance_ids],
            ),
            _owner_decision_section(
                "GATE-A-RISK",
                "Assumptions, risks, and change impact",
                [
                    "Assumptions: " + gate_a_card.get("Assumptions", "None recorded."),
                    "Open decisions or findings: "
                    + gate_a_analysis.get(
                        "Open blocking decision IDs", "None recorded."
                    )
                    + "; "
                    + gate_a_analysis.get(
                        "Open blocking finding IDs", "None recorded."
                    ),
                    "Brownfield preservation: "
                    + gate_a_card.get(
                        "Brownfield baseline and preservation", "Not applicable."
                    ),
                ],
                [requirements_revision, *requirements_contract.requirement_ids],
            ),
        ]
        claims = [
            owner_claim(
                "The recorded product direction and confirmed intake facts came from the owner.",
                "CONFIRMED_BY_OWNER",
                basis_ids=intake_contract.basis_ids,
            ),
            owner_claim(
                "The requirements are planned work; application behavior and AWS deployment have not been observed.",
                "NOT_YET_OBSERVED",
                basis_ids=requirements_contract.requirement_ids,
            ),
            owner_claim(
                "Gate A does not authorize technical design selection, construction, publication, deployment, or teardown.",
                "NOT_AUTHORIZED",
                basis_ids=[requirements_revision],
            ),
        ]
        locator_specs = (
            (
                "owner-decisions",
                "Owner decisions and sources",
                "Owner decisions and sources",
            ),
            ("product-statement", "Product statement", "2. Product statement"),
            (
                "requirements",
                "Features and measurable acceptance",
                "6. Feature specifications",
            ),
            (
                "journeys",
                "First-release journeys",
                "7. Primary, alternate, and failure flows",
            ),
            ("data-boundary", "Data requirements", "8. Data requirements"),
            (
                "security-boundary",
                "Security and privacy requirements",
                "9. Security and privacy requirements",
            ),
            ("reliability", "Reliability requirements", "10. Reliability requirements"),
            (
                "cost",
                "Performance and cost",
                "11. Performance, cost, and sustainability requirements",
            ),
            ("gate-a-readiness", "Gate A readiness", "Gate A — readiness card"),
            (
                "gate-a-acceptance",
                "Gate A acceptance record",
                "Gate A — owner acceptance record",
            ),
        )
        authorization = {
            "approves": [
                "The current product outcome, users, first-release boundary, requirements, constraints, and cost posture."
            ],
            "does_not_approve": [
                "A technical design, local construction, GitHub publication, AWS account access, deployment, or teardown."
            ],
        }
    else:
        try:
            table_after_heading(prd_text, "### Gate B — readiness card")
        except ValueError as exc:
            issues.append(("OWNER_BRIEF_SOURCE_MISMATCH", str(exc)))
        inventory, inventory_issues = _derive_gate_b_decision_inventory(
            design_contract,
            requirements_revision,
            design_revision,
            authorization_id,
            status=status,
        )
        selection = design_contract.architecture.selection
        sections = [
            _owner_decision_section(
                "GATE-B-EXECUTIVE",
                "Executive decision",
                [
                    "Recommendation: "
                    + (
                        selection.selected_candidate
                        if selection is not None
                        else "Not yet selected."
                    ),
                    "Why it fits: "
                    + (
                        selection.rationale
                        if selection is not None
                        else "The architecture analysis is still in progress."
                    ),
                    "Main tradeoff: "
                    + (
                        selection.risks
                        if selection is not None
                        else "Not yet recorded."
                    ),
                    "Construction boundary: "
                    + envelope.get("Authorized outcome", "Not yet recorded."),
                ],
                [
                    requirements_revision,
                    design_revision,
                    authorization_id,
                    *([selection.architecture_id] if selection is not None else []),
                ],
            )
        ]
        technical_groups = [
            {
                "domain": decision["domain"],
                "decisions": [
                    {
                        "decision_id": decision["decision_id"],
                        "decision": decision["title"],
                        "owner_effect": decision["owner_effect"],
                        "selection": decision["selection"],
                        "requirement_basis": ", ".join(decision["basis_ids"]),
                        "why": decision["why"],
                        "alternatives": decision["alternatives"],
                        "tradeoff": decision["tradeoff"],
                        "risk_and_mitigation": decision["risk_and_mitigation"],
                        "evidence_status": decision["evidence_status"],
                        "reconsider_when": decision["reconsider_when"],
                        "basis_ids": decision["basis_ids"],
                        "evidence_ids": decision["evidence_ids"],
                        "source_locator_keys": decision["source_locator_keys"],
                    }
                ],
            }
            for decision in inventory.get("decisions", [])
        ]
        evidence_ids = [
            item.evidence_id for item in design_contract.architecture.aws_evidence
        ]
        claims = []
        if evidence_ids:
            claims.append(
                owner_claim(
                    "Current official AWS references support the material AWS design claims recorded in the technical plan.",
                    "SOURCE_VERIFIED",
                    basis_ids=[design_revision],
                    evidence_ids=evidence_ids,
                )
            )
        claims.extend(
            (
                owner_claim(
                    "The recommended architecture, construction work, rollback, and operational procedures are planned after approval.",
                    "PLANNED_AFTER_APPROVAL",
                    basis_ids=[design_revision, authorization_id],
                ),
                owner_claim(
                    "Deployment, recovery, and teardown have not yet been observed.",
                    "NOT_YET_OBSERVED",
                    basis_ids=[design_revision],
                ),
                owner_claim(
                    "Gate B does not authorize GitHub publication, AWS account access, deployment, or teardown.",
                    "NOT_AUTHORIZED",
                    basis_ids=[authorization_id],
                ),
            )
        )
        locator_specs = (
            ("technical-plan", "Technical plan", "14. Architecture overview"),
            ("technology-register", "Technology decisions", "Technology decisions"),
            ("selected-architecture", "Selected architecture", "Selected architecture"),
            ("components", "Component design", "15. Component design"),
            ("interfaces", "Interfaces and contracts", "16. Interfaces and contracts"),
            (
                "data-lifecycle",
                "Data model and lifecycle",
                "17. Data model and lifecycle",
            ),
            (
                "aws-implementation",
                "AWS implementation approach",
                "20. AWS implementation approach",
            ),
            ("validation-strategy", "Validation strategy", "Validation strategy"),
            ("harness-profile", "Harness checks", "Validation strategy"),
            ("release-acceptance", "Release acceptance", "26. Release acceptance"),
            (
                "first-wave",
                "First construction wave",
                "21. Implementation boundaries and order",
            ),
            ("gate-b-readiness", "Gate B readiness", "Gate B — readiness card"),
            (
                "construction-boundary",
                "Construction boundary",
                "Construction and authorization boundary",
            ),
            (
                "gate-b-authorization",
                "Gate B authorization record",
                "29. Gate B owner authorization record",
            ),
        )
        authorization = {
            "approves": [
                "The complete technical design and the exact bounded local construction envelope."
            ],
            "does_not_approve": [
                "GitHub publication, AWS account access, deployment, rollback execution, or teardown."
            ],
        }

    if inventory_issues:
        status = "BLOCKED"
        for issue in inventory_issues:
            issues.append(("OWNER_BRIEF_COVERAGE_INCOMPLETE", issue))

    for key, label, heading in locator_specs:
        try:
            locators.append(
                _owner_locator_for_heading(
                    prd_text, key=key, label=label, heading=heading
                )
            )
        except ValueError as exc:
            issues.append(
                (
                    "OWNER_BRIEF_SOURCE_MISMATCH",
                    f"{label} source could not be resolved: {exc}",
                )
            )

    inventory_ids = [item.get("decision_id") for item in inventory.get("decisions", [])]
    if kind == "GATE_B":
        brief_ids = [
            decision.get("decision_id")
            for group in technical_groups
            for decision in group.get("decisions", [])
        ]
        if brief_ids != inventory_ids:
            issues.append(
                (
                    "OWNER_BRIEF_COVERAGE_INCOMPLETE",
                    "Gate B brief does not cover the complete decision inventory exactly once",
                )
            )

    projection = {
        "schema_version": 1,
        "kind": kind,
        "status": status,
        "basis": basis,
        "executive_sections": sections,
        "technical_decision_groups": technical_groups,
        "claims": claims,
        "source_locators": locators,
        "authorization_effect": authorization,
        "formal_receipt_required": status == "READY",
    }
    finalized, validation_issues = finalize_owner_decision_brief(projection)
    for issue in validation_issues:
        if "unsafe" in issue or "secret" in issue:
            code = "OWNER_BRIEF_UNSAFE_CONTENT"
        elif "output budget" in issue:
            code = "OWNER_BRIEF_OUTPUT_BUDGET_UNRESOLVED"
        else:
            code = "OWNER_BRIEF_COVERAGE_INCOMPLETE"
        issues.append((code, issue))
    if status == "STALE":
        issues.append(
            (
                "OWNER_BRIEF_SOURCE_STALE",
                "the gate basis is stale; regenerate the derived decision brief from current canonical records",
            )
        )
    return finalized, inventory, issues


def derive_owner_answer_confirmation(
    prd_text: str,
    intake_contract: IntakeFoundationContract,
) -> dict[str, Any]:
    """Project only the latest canonical normalized intake response."""

    if not intake_contract.normalized_responses:
        return answer_confirmation()
    latest_number = max(
        int(item.owner_response_id.rsplit("-", 1)[1])
        for item in intake_contract.normalized_responses
    )
    latest = [
        item
        for item in intake_contract.normalized_responses
        if int(item.owner_response_id.rsplit("-", 1)[1]) == latest_number
    ]
    identities = {
        (
            item.owner_response_id,
            item.card_id,
            item.revision,
            item.presented_card_digest,
        )
        for item in latest
    }
    if len(identities) != 1:
        return answer_confirmation(status="BLOCKED")
    question_by_id = {
        question.question_id: question for question in intake_contract.all_questions
    }
    recorded: list[str] = []
    fields: list[str] = []
    for response in latest:
        question = question_by_id.get(response.question_id)
        if question is None:
            return answer_confirmation(status="BLOCKED")
        if response.selection == "RESPONSE":
            value = response.selection_detail or ""
        else:
            value = {
                "A": question.option_a,
                "B": question.option_b,
                "C": question.option_c,
            }.get(response.selection, "")
            if response.selection_detail:
                value += f" ({response.selection_detail})"
        if not value:
            return answer_confirmation(status="BLOCKED")
        recorded.append(f"{question.prompt}: {value}")
        fields.extend(
            OWNER_CONFIRMATION_FIELDS.get(item, "project answer")
            for item in response.basis_ids
        )
    owner_response_id, card_id, revision, digest = next(iter(identities))
    try:
        locator = _owner_locator_for_heading(
            prd_text,
            key="intake-provenance",
            label="Recorded intake answers",
            heading="1.1 Intake provenance",
        )
    except ValueError:
        return answer_confirmation(status="BLOCKED")
    field_name = fields[0] if fields else "project answer"
    return answer_confirmation(
        status="READY",
        owner_response_id=owner_response_id,
        card_id=card_id,
        revision=revision,
        presented_sha256=digest,
        recorded=recorded,
        project_effect=(
            "Fastlane will use this confirmed answer to shape the next "
            "requirements. It does not approve construction, publication, or "
            "AWS changes."
        ),
        correction_prompt=f"Change {field_name} to <new value>.",
        basis_ids=[item for response in latest for item in response.basis_ids],
        source_locators=[locator],
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


def validate_manifest(ctx: Context, manifest: dict[str, Any]) -> None:
    """Compatibility façade for package-manifest validation."""

    validate_package_manifest(
        ctx,
        manifest,
        policy=MANIFEST_POLICY,
        read_binary=safe_read_required_binary,
        read_text=safe_read_text,
        has_symlink_component=has_symlink_component,
    )


def validate_prompt_pack(
    ctx: Context, manifest: dict[str, Any], state: dict[str, Any]
) -> None:
    """Compatibility façade for prompt-pack validation."""

    validate_package_prompt_pack(
        ctx,
        manifest,
        state,
        policy=MANIFEST_POLICY,
        read_text=safe_read_text,
    )


def validate_placeholders(ctx: Context) -> None:
    """Compatibility façade for unresolved-template validation."""

    validate_package_placeholders(ctx, policy=MANIFEST_POLICY)


def validate_state_schema(ctx: Context, state: dict[str, Any]) -> bool:
    """Compatibility façade for bootstrap-state validation."""

    return validate_package_state_schema(
        ctx,
        state,
        policy=STATE_POLICY,
        normalize_project_name=normalize_project_name,
        normalize_aws_region=normalize_aws_region,
        parse_cost_posture=parse_cost_posture,
        unresolved=unresolved,
    )


def validate_gate_a_method_contract(
    ctx: Context,
    text: str,
    *,
    grandfather_approved_v1: bool = False,
) -> None:
    """Compatibility façade for the pure Define method evaluator."""

    for code, message in gate_a_method_contract_issues(
        text, grandfather_approved_v1=grandfather_approved_v1
    ):
        ctx.error(code, message, PRD_FILE)


def validate_brownfield_contract(ctx: Context, text: str) -> None:
    """Compatibility façade for the pure brownfield evaluator."""

    for code, message in brownfield_contract_issues(text):
        ctx.error(code, message, PRD_FILE)


def validate_gate_a_readiness_card(ctx: Context, card: Mapping[str, str]) -> None:
    """Record pure Gate A readiness-card issues on the legacy Context."""

    for code, message in gate_a_readiness_card_issues(card):
        ctx.error(code, message, PRD_FILE)


def validate_construction_envelope(
    ctx: Context,
    envelope: dict[str, str],
    fields: dict[str, str],
    selections: dict[str, str | None],
    cost_posture: str,
    design_contract: DesignContract,
) -> None:
    required_fields = set(ENVELOPE_EXPLICIT_FIELDS)
    if any(
        (
            design_contract.project_contract.grandfathered_v4,
            design_contract.project_contract.grandfathered_v5,
            design_contract.project_contract.grandfathered_v6,
        )
    ):
        required_fields.discard(APPLICATION_SOURCE_DISPOSITION_FIELD)
    else:
        required_fields.add(APPLICATION_SOURCE_DISPOSITION_FIELD)
    missing = sorted(required_fields - set(envelope))
    if missing:
        ctx.error(
            "GATE_B_ENVELOPE",
            "Construction envelope is missing fields: " + ", ".join(missing),
            PRD_FILE,
        )
    unresolved_fields = sorted(
        field
        for field in required_fields
        if not explicit_value(
            envelope.get(field, ""),
            allow_none=field
            in {
                "Excluded or owner-only write set",
                "Allowed external-state targets",
                "Protected dirty paths",
                "GitHub repository, branch, and merge constraints",
            },
        )
    )
    if unresolved_fields:
        ctx.error(
            "GATE_B_ENVELOPE",
            "Construction envelope has unresolved fields: "
            + ", ".join(unresolved_fields),
            PRD_FILE,
        )

    if envelope.get("Construction authorization ID") != fields.get(
        "construction_authorization"
    ):
        ctx.error(
            "GATE_B_ENVELOPE", "Envelope AUTH does not match current AUTH", PRD_FILE
        )
    authorized_baseline = envelope.get("Authorized baseline commit", "")
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", authorized_baseline) is None:
        ctx.error(
            "GATE_B_ENVELOPE",
            "Authorized baseline commit must be a full lowercase Git commit hash",
            PRD_FILE,
        )
    else:
        validate_authorized_baseline_repository(ctx, authorized_baseline)
    expected_project_rows = {
        "Project mode": selections.get("mode"),
        "Delivery profile and effective risk": (
            f"{selections.get('delivery_profile')} / {selections.get('effective_risk')}"
            if selections.get("delivery_profile") and selections.get("effective_risk")
            else None
        ),
        "Project AWS lane": selections.get("aws_lane"),
    }
    for key, expected in expected_project_rows.items():
        if expected is None or envelope.get(key) != expected:
            ctx.error(
                "GATE_B_PROJECT_DRIFT",
                f"Envelope {key} does not exactly match Document status",
                PRD_FILE,
            )
    try:
        authorized_ids = parse_authorized_ids(
            envelope.get("Authorized requirement and design IDs", "")
        )
        if fields.get("requirements_revision") != authorized_ids[0]:
            ctx.error(
                "GATE_B_ENVELOPE",
                "Authorized ID basis must include the current REQ revision",
                PRD_FILE,
            )
        if fields.get("design_revision") != authorized_ids[1]:
            ctx.error(
                "GATE_B_ENVELOPE",
                "Authorized ID basis must include the current DES revision",
                PRD_FILE,
            )
        required_scope_ids = {
            decision.decision_id for decision in design_contract.technology_decisions
        }
        required_scope_ids.update(
            execution.property_id for execution in design_contract.property_execution
        )
        if design_contract.architecture.selection is not None:
            required_scope_ids.add(
                design_contract.architecture.selection.architecture_id
            )
        required_scope_ids.update(design_contract.harness.required_ids)
        if not design_contract.project_contract.grandfathered_v4:
            required_scope_ids.update(design_contract.project_contract.interface_ids)
            required_scope_ids.update(design_contract.project_contract.boundary_ids)
            required_scope_ids.update(design_contract.project_contract.state_ids)
            if design_contract.project_contract.first_wave is not None:
                required_scope_ids.add(
                    design_contract.project_contract.first_wave.wave_contract_id
                )
            if design_contract.project_contract.spike is not None:
                required_scope_ids.add(design_contract.project_contract.spike.spike_id)
        missing_scope_ids = sorted(required_scope_ids - set(authorized_ids[2:]))
        if missing_scope_ids:
            ctx.error(
                "GATE_B_ENVELOPE",
                "Authorized SCOPE_IDS are missing current design contract IDs: "
                + ", ".join(missing_scope_ids),
                PRD_FILE,
            )
    except ValueError as exc:
        ctx.error("GATE_B_ENVELOPE", str(exc), PRD_FILE)

    if (
        design_contract.status != "READY"
        or design_contract.canonical_sha256 is None
        or envelope.get("Design contract SHA-256") != design_contract.canonical_sha256
    ):
        ctx.error(
            "GATE_B_DESIGN_CONTRACT_HASH",
            "Construction envelope Design contract SHA-256 must equal the current derived design contract hash",
            PRD_FILE,
        )

    if envelope.get("Autonomous construction") not in {"ALLOWED", "PROHIBITED"}:
        ctx.error(
            "GATE_B_ENVELOPE",
            "Autonomous construction must be ALLOWED or PROHIBITED",
            PRD_FILE,
        )
    numeric: dict[str, int] = {}
    for key in (
        "Maximum generated tasks",
        "Maximum parallel workers",
        "Attempt budget",
    ):
        value = envelope.get(key, "")
        if re.fullmatch(r"[1-9]\d*", value) is None:
            ctx.error("GATE_B_ENVELOPE", f"{key} must be a positive integer", PRD_FILE)
        else:
            numeric[key] = int(value)
    if envelope.get("Eligible task status") != "READY":
        ctx.error("GATE_B_ENVELOPE", "Eligible task status must be READY", PRD_FILE)
    if envelope.get("GitHub boundary") not in GITHUB_BOUNDARIES:
        ctx.error("GATE_B_ENVELOPE", "GitHub boundary is not canonical", PRD_FILE)
    if envelope.get("AWS boundary") not in AWS_BOUNDARIES:
        ctx.error("GATE_B_ENVELOPE", "AWS boundary is not canonical", PRD_FILE)
    try:
        allowed_repository_paths = parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
        )
        source_disposition = (
            design_contract.project_contract.application_source_disposition
        )
        if source_disposition is None:
            validate_application_source_root(
                allowed_repository_paths, selections.get("mode")
            )
        else:
            validate_application_source_write_set(
                source_disposition, allowed_repository_paths
            )
        parse_envelope_paths(
            envelope.get("Excluded or owner-only write set", ""),
            "Excluded or owner-only write set",
            allow_none=True,
        )
        parse_envelope_paths(
            envelope.get("Protected dirty paths", ""),
            "Protected dirty paths",
            allow_none=True,
        )
        parse_envelope_targets(envelope.get("Allowed external-state targets", ""))
        parse_task_boundary(envelope.get("Task boundary", ""))
        parse_command_prefixes(envelope.get("Local command boundary", ""))
        parse_github_constraints(
            envelope.get("GitHub repository, branch, and merge constraints", ""),
            envelope.get("GitHub boundary", ""),
        )
        parse_future_expiry(
            envelope.get("Authorization expiry or completion condition", "")
        )
    except ValueError as exc:
        code = (
            "GATE_B_AUTHORITY_EXPIRED"
            if str(exc) == "Construction authorization is expired"
            else "APPLICATION_SOURCE_PARALLEL_ROOT"
            if str(exc).startswith("APPLICATION_SOURCE_PARALLEL_ROOT: ")
            else "APPLICATION_SOURCE_DISPOSITION_INVALID"
            if str(exc).startswith("APPLICATION_SOURCE_DISPOSITION_INVALID: ")
            else "GATE_B_ENVELOPE"
        )
        if code in APPLICATION_SOURCE_DIAGNOSTIC_CODES:
            message = str(exc).split(": ", 1)[1]
        else:
            message = (
                "Gate B authority expired; the owner must reapprove the current "
                "design boundary before any new local or AWS operation"
                if code == "GATE_B_AUTHORITY_EXPIRED"
                else str(exc)
            )
        ctx.error(code, message, PRD_FILE)
    if numeric.get("Maximum parallel workers") != 1:
        ctx.error(
            "GATE_B_ENVELOPE",
            "Maximum parallel workers must be exactly 1",
            PRD_FILE,
        )

    lane_boundaries = {
        "documentation-only": {"NONE", "DOCS_ONLY"},
        "read-only": {"NONE", "DOCS_ONLY", "READ_ONLY"},
        "fast-dev": {"NONE", "DOCS_ONLY", "READ_ONLY", "MUTATE_LISTED_RESOURCES"},
        "explicit-gate": {"NONE", "DOCS_ONLY", "READ_ONLY", "MUTATE_LISTED_RESOURCES"},
    }
    lane = selections.get("aws_lane")
    if (
        lane in lane_boundaries
        and envelope.get("AWS boundary") not in lane_boundaries[lane]
    ):
        ctx.error(
            "AWS_LANE_BOUNDARY",
            "AWS boundary does not match the selected project lane",
            PRD_FILE,
        )
    aws_boundary = envelope.get("AWS boundary")
    if aws_boundary in {"NONE", "DOCS_ONLY"}:
        expected = f"NOT_APPLICABLE — AWS boundary {aws_boundary} authorizes no authenticated action"
        for key in sorted(AWS_DETAIL_FIELDS):
            if envelope.get(key) != expected:
                ctx.error(
                    "GATE_B_ENVELOPE",
                    f"{key} must be exactly {expected!r} for {aws_boundary}",
                    PRD_FILE,
                )
    elif aws_boundary == "READ_ONLY":
        required_read = {
            "AWS account",
            "AWS role or profile",
            "AWS Region",
            "AWS environment",
            "AWS resource allowlist",
            "AWS allowed operations",
            "AWS prohibited operations",
            "AWS authorization validity",
        }
        for key in sorted(AWS_DETAIL_FIELDS):
            value = envelope.get(key, "")
            if key in required_read and (
                not explicit_value(value) or value.startswith("NOT_APPLICABLE — ")
            ):
                ctx.error(
                    "GATE_B_ENVELOPE",
                    f"{key} is required for READ_ONLY AWS authority",
                    PRD_FILE,
                )
            elif key not in required_read and not (
                explicit_value(value) or value.startswith("NOT_APPLICABLE — ")
            ):
                ctx.error(
                    "GATE_B_ENVELOPE",
                    f"{key} must be explicit for READ_ONLY AWS authority",
                    PRD_FILE,
                )
        try:
            parse_aws_environment(envelope.get("AWS environment", ""))
            parse_future_expiry(envelope.get("AWS authorization validity", ""))
        except ValueError as exc:
            code = (
                "GATE_B_AUTHORITY_EXPIRED"
                if str(exc) == "Construction authorization is expired"
                else "GATE_B_ENVELOPE"
            )
            message = (
                "Gate B authority expired; the owner must reapprove the current "
                "design boundary before any new local or AWS operation"
                if code == "GATE_B_AUTHORITY_EXPIRED"
                else str(exc)
            )
            ctx.error(code, message, PRD_FILE)
    elif aws_boundary == "MUTATE_LISTED_RESOURCES":
        for key in sorted(AWS_DETAIL_FIELDS):
            value = envelope.get(key, "")
            if not explicit_value(value) or value.startswith("NOT_APPLICABLE — "):
                ctx.error(
                    "GATE_B_ENVELOPE",
                    f"{key} is required for AWS mutation authority",
                    PRD_FILE,
                )
        try:
            _environment, environment_class = parse_aws_environment(
                envelope.get("AWS environment", "")
            )
            if lane == "fast-dev" and environment_class != "NON_PRODUCTION":
                raise ValueError(
                    "fast-dev AWS mutation authority must be NON_PRODUCTION"
                )
            validate_aws_artifact(
                envelope.get("AWS artifact authorization and provenance", ""),
                envelope.get("Authorized baseline commit", ""),
            )
            validate_aws_cost_ceiling(
                envelope.get("AWS cost ceiling", ""),
                cost_posture,
            )
            parse_future_expiry(envelope.get("AWS authorization validity", ""))
        except ValueError as exc:
            code = (
                "GATE_B_AUTHORITY_EXPIRED"
                if str(exc) == "Construction authorization is expired"
                else "GATE_B_ENVELOPE"
            )
            message = (
                "Gate B authority expired; the owner must reapprove the current "
                "design boundary before any new local or AWS operation"
                if code == "GATE_B_AUTHORITY_EXPIRED"
                else str(exc)
            )
            ctx.error(code, message, PRD_FILE)


def validate_readiness_card(
    ctx: Context,
    card: dict[str, str],
    expected_fields: set[str],
    gate: str,
) -> None:
    if set(card) != expected_fields:
        ctx.error(
            f"{gate}_READINESS_CARD",
            f"{gate.replace('_', ' ')} readiness-card fields must be exact",
            PRD_FILE,
        )
    for field_name in sorted(expected_fields):
        value = clean_cell(card.get(field_name, ""))
        if field_name == "Outstanding gaps" and value == "NONE":
            continue
        if value.startswith("NOT_APPLICABLE — ") and explicit_value(
            value.removeprefix("NOT_APPLICABLE — ")
        ):
            continue
        if not explicit_value(value, allow_none=False):
            ctx.error(
                f"{gate}_READINESS_CARD",
                f"{field_name} is not an explicit current decision basis",
                PRD_FILE,
            )


def validate_prd(
    ctx: Context,
    state: dict[str, Any],
) -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, str],
    bool,
    DesignContract,
    CoverageContract,
    IntakeFoundationContract,
    RequirementsContract,
]:
    text = ctx.texts.get(PRD_FILE) or safe_read_text(ctx, PRD_FILE)
    if text is None:
        return (
            {},
            {},
            {},
            False,
            DesignContract(),
            CoverageContract(),
            IntakeFoundationContract(),
            RequirementsContract(),
        )
    try:
        document = table_after_heading(text, "## Document status")
        workload = table_after_heading(text, "## 1. Workload profile")
        gate_a_agent = table_after_heading(text, "### Gate A — agent analysis record")
        gate_a_card = table_after_heading(text, "### Gate A — readiness card")
        gate_a_owner = table_after_heading(text, "### Gate A — owner acceptance record")
        gate_b_agent = table_after_heading(text, "## 27. Gate B agent review record")
        gate_b_card = table_after_heading(text, "### Gate B — readiness card")
        envelope = table_after_heading(text, "## 28. Construction envelope")
        gate_b_owner = table_after_heading(
            text, "## 29. Gate B owner authorization record"
        )
        envelope_digest = canonical_envelope_sha256(text)
        # Check marker structure even before either gate is approved.
        marked_receipt(text, "gate-a")
        marked_receipt(text, "gate-b")
    except ValueError as exc:
        ctx.error("PRD_STRUCTURE", str(exc), PRD_FILE)
        return (
            {},
            {},
            {},
            False,
            DesignContract(),
            CoverageContract(),
            IntakeFoundationContract(),
            RequirementsContract(),
        )

    project = state.get("project", {})
    lifecycle = state.get("lifecycle", {})
    prd_name = html.unescape(clean_cell(workload.get("Workload", "")))
    if project.get("name") != prd_name:
        ctx.error(
            "STATE_PRD_DRIFT",
            "project.name does not match the PRD Workload value",
            STATE_FILE,
        )
    prd_region = clean_cell(workload.get("Primary Region", ""))
    if project.get("region") != prd_region:
        ctx.error(
            "STATE_PRD_DRIFT",
            "project.region does not match the PRD Primary Region value",
            STATE_FILE,
        )
    selection_values = {
        "mode": document.get("Project mode", ""),
        "delivery_profile": document.get("Delivery profile", ""),
        "effective_risk": document.get("Effective risk", ""),
        "aws_lane": document.get("AWS lane", ""),
    }
    selection_options = {
        "mode": PROJECT_MODES,
        "delivery_profile": DELIVERY_PROFILES,
        "effective_risk": RISK_LEVELS,
        "aws_lane": AWS_LANES,
    }
    unselected_fields = {
        key: unselected_selection(selection_values[key], allowed)
        for key, allowed in selection_options.items()
    }
    selections = {
        "mode": exact_selection(
            ctx,
            selection_values["mode"],
            PROJECT_MODES,
            "PROJECT_VOCABULARY",
            "Project mode",
            allow_unselected=unselected_fields["mode"],
        ),
        "delivery_profile": exact_selection(
            ctx,
            selection_values["delivery_profile"],
            DELIVERY_PROFILES,
            "PROJECT_VOCABULARY",
            "Delivery profile",
            allow_unselected=unselected_fields["delivery_profile"],
        ),
        "effective_risk": exact_selection(
            ctx,
            selection_values["effective_risk"],
            RISK_LEVELS,
            "PROJECT_VOCABULARY",
            "Effective risk",
            allow_unselected=unselected_fields["effective_risk"],
        ),
        "aws_lane": exact_selection(
            ctx,
            selection_values["aws_lane"],
            AWS_LANES,
            "PROJECT_VOCABULARY",
            "AWS lane",
            allow_unselected=unselected_fields["aws_lane"],
        ),
    }
    for key, selected in selections.items():
        if unselected_fields[key] and project.get(key) is None:
            continue
        if project.get(key) != selected:
            ctx.error(
                "STATE_PRD_DRIFT",
                f"project.{key}={project.get(key)!r} does not match PRD value {selected!r}",
                STATE_FILE,
            )
    if (
        selections["effective_risk"] in {"high", "critical"}
        and selections["delivery_profile"] is not None
        and selections["delivery_profile"] != "high-risk"
    ):
        ctx.error(
            "PROJECT_RISK_PROFILE",
            "High or critical risk requires the high-risk profile",
            PRD_FILE,
        )

    fields = {
        "requirements_revision": document.get("Current requirements revision", ""),
        "design_revision": document.get("Current design revision", ""),
        "construction_authorization": document.get(
            "Current construction authorization ID", ""
        ),
        "gate_a": document.get("Gate A derived status", ""),
        "gate_b": document.get("Gate B derived status", ""),
    }
    patterns = {
        "requirements_revision": REQ_ID,
        "design_revision": DES_ID,
        "construction_authorization": AUTH_ID,
    }
    for key, pattern in patterns.items():
        if pattern.fullmatch(fields[key]) is None:
            ctx.error(
                "PRD_REVISION_ID", f"Invalid PRD {key}: {fields[key]!r}", PRD_FILE
            )
    if fields["gate_a"] not in GATE_A_STATES or fields["gate_b"] not in GATE_B_STATES:
        ctx.error("PRD_GATE", "Invalid PRD derived gate state", PRD_FILE)
    for key, value in fields.items():
        if lifecycle.get(key) != value:
            ctx.error(
                "STATE_PRD_DRIFT",
                f"lifecycle.{key}={lifecycle.get(key)!r} does not match PRD {value!r}",
                STATE_FILE,
            )
    fields["gate_b_authorization_source"] = clean_cell(
        gate_b_owner.get("Authorization source", "")
    )
    fields["gate_b_authorized_at"] = clean_cell(
        gate_b_owner.get("Authorization provided at", "")
    )

    gate_a_ready_or_current = fields["gate_a"] in {
        "PENDING_OWNER_APPROVAL",
        "APPROVED_FOR_DESIGN",
    }
    gate_b_ready_or_current = fields["gate_b"] in {
        "PENDING_OWNER_APPROVAL",
        "APPROVED_FOR_CONSTRUCTION",
    }
    gate_a_agent_ready = gate_a_agent.get("Agent recommendation") in {
        "READY_WITH_PROPOSED_ASSUMPTIONS",
        "READY_FOR_OWNER_APPROVAL",
    }
    gate_b_agent_ready = (
        gate_b_agent.get("Agent recommendation") == "READY_FOR_CONSTRUCTION_APPROVAL"
    )
    coverage_required = gate_a_agent_ready or gate_a_ready_or_current
    grandfather_approved_v1_requirements = bool(
        fields["gate_a"] == "APPROVED_FOR_DESIGN"
        and gate_a_agent.get("Requirements revision analyzed")
        == fields["requirements_revision"]
        and gate_a_owner.get("Authorized requirements revision")
        == fields["requirements_revision"]
    )
    req_aws_materiality, req_aws_materiality_issues = derive_req_aws_materiality(
        gate_a_agent,
        fields["requirements_revision"],
        required=gate_a_agent_ready or gate_a_ready_or_current,
        grandfather_current_gate_a=grandfather_approved_v1_requirements,
    )
    fields["req_aws_materiality"] = req_aws_materiality
    if gate_a_agent_ready or gate_a_ready_or_current:
        for issue in req_aws_materiality_issues:
            ctx.error("REQ_AWS_MATERIALITY_INVALID", issue, PRD_FILE)
    intake_repository_mode = selections.get("mode")
    setup_state = state.get("setup") if isinstance(state.get("setup"), dict) else {}
    if (
        intake_repository_mode is None
        and not ctx.template_source
        and setup_state.get("status")
        not in {"UNCONFIGURED_TEMPLATE", "{{SETUP_STATUS}}"}
    ):
        intake_repository_mode = "greenfield"
    intake_contract, intake_issues = derive_intake_foundation_contract(
        text,
        intake_repository_mode,
        grandfather_current_gate_a=grandfather_approved_v1_requirements,
    )
    for code, issue in intake_issues:
        ctx.error(code, issue, PRD_FILE)
    if gate_a_ready_or_current and intake_contract.status != "READY_FOR_REQUIREMENTS":
        ctx.error(
            "INTAKE_FOUNDATION_REQUIRED",
            "Gate A requires a complete owner-grounded intake foundation and no pending card",
            PRD_FILE,
        )
    coverage_contract, coverage_issues = derive_coverage_contract(
        text,
        fields.get("requirements_revision"),
        selections.get("delivery_profile"),
        selections.get("effective_risk"),
        selections.get("aws_lane"),
        required=coverage_required,
        grandfather_current_gate_a=grandfather_approved_v1_requirements,
        owner_work_context=intake_contract.owner_work_context,
    )
    if coverage_required:
        for issue in coverage_issues:
            ctx.error("ADAPTIVE_COVERAGE_INVALID", issue, PRD_FILE)
    requirements_contract, requirements_contract_issues = derive_requirements_contract(
        text,
        selections.get("effective_risk"),
        intake_contract,
        required=coverage_required,
        grandfather_current_gate_a=grandfather_approved_v1_requirements,
    )
    if coverage_required:
        for code, issue in requirements_contract_issues:
            ctx.error(code, issue, PRD_FILE)
        if requirements_contract.status not in {"READY", "GRANDFATHERED"}:
            ctx.error(
                "PROJECT_CONTRACT_MIGRATION_REQUIRED",
                "Gate A requires a complete schema 1.4 requirements contract or an unchanged approved legacy Gate A",
                PRD_FILE,
            )
    design_contract_required = gate_b_agent_ready or gate_b_ready_or_current
    grandfather_approved_v1_design = bool(
        fields["gate_b"] == "APPROVED_FOR_CONSTRUCTION"
        and gate_b_agent.get("Design revision reviewed") == fields["design_revision"]
        and gate_b_agent.get("Construction authorization ID reviewed")
        == fields["construction_authorization"]
        and gate_b_owner.get("Authorized design revision") == fields["design_revision"]
        and gate_b_owner.get("Authorized construction authorization ID")
        == fields["construction_authorization"]
    )
    design_contract, design_contract_issues = derive_design_contract(
        text,
        fields.get("design_revision"),
        required=design_contract_required,
        grandfather_approved_v1=grandfather_approved_v1_design,
        coverage_contract=coverage_contract,
        requirements_contract=requirements_contract,
    )
    if design_contract_required:
        for issue in design_contract_issues:
            code, separator, message = issue.partition(": ")
            if separator and code in APPLICATION_SOURCE_DIAGNOSTIC_CODES:
                ctx.error(code, message, PRD_FILE)
            else:
                ctx.error("DESIGN_CONTRACT_INVALID", issue, PRD_FILE)
    card_cost_posture = clean_cell(gate_a_card.get("Cost posture", ""))
    if gate_a_agent_ready or gate_a_ready_or_current:
        validate_gate_a_method_contract(
            ctx,
            text,
            grandfather_approved_v1=grandfather_approved_v1_requirements,
        )
        validate_gate_a_readiness_card(ctx, gate_a_card)
        try:
            parse_cost_posture(card_cost_posture)
        except ValueError as exc:
            ctx.error("GATE_A_COST_POSTURE", str(exc), PRD_FILE)
        if card_cost_posture != project.get("cost_posture"):
            ctx.error(
                "STATE_PRD_DRIFT",
                "Gate A Cost posture does not match bootstrap state",
                STATE_FILE,
            )
    if gate_b_agent_ready or gate_b_ready_or_current:
        validate_readiness_card(ctx, gate_b_card, GATE_B_READINESS_FIELDS, "GATE_B")
        expected_technology_ids = ", ".join(
            decision.decision_id for decision in design_contract.technology_decisions
        )
        if (
            not expected_technology_ids
            or gate_b_card.get("Technology/toolchains/version policy")
            != expected_technology_ids
        ):
            ctx.error(
                "GATE_B_READINESS_CARD",
                "Technology/toolchains/version policy must exactly enumerate the "
                "current technology decision IDs in register order: "
                + (expected_technology_ids or "NONE"),
                PRD_FILE,
            )
        if design_contract.architecture.selection is not None:
            selected_architecture = design_contract.architecture.selection
            expected_architecture = (
                selected_architecture.architecture_id
                if selected_architecture is not None
                else "NONE"
            )
            if gate_b_card.get("Architecture/components") != expected_architecture:
                ctx.error(
                    "GATE_B_READINESS_CARD",
                    "Architecture/components must equal the current selected ARCH ID: "
                    + expected_architecture,
                    PRD_FILE,
                )
        if gate_b_card.get("Outstanding gaps") != "NONE":
            ctx.error(
                "GATE_B_READINESS_CARD",
                "Gate B readiness requires Outstanding gaps NONE",
                PRD_FILE,
            )
    if gate_a_agent_ready and fields["gate_a"] == "BLOCKED":
        ctx.error(
            "GATE_A_LIFECYCLE_TRANSITION",
            "Agent-ready Gate A must atomically transition to PENDING_OWNER_APPROVAL",
            PRD_FILE,
        )
    if gate_b_agent_ready and fields["gate_b"] == "BLOCKED":
        ctx.error(
            "GATE_B_LIFECYCLE_TRANSITION",
            "Agent-ready Gate B must atomically transition to PENDING_OWNER_APPROVAL",
            PRD_FILE,
        )
    if gate_a_ready_or_current or gate_b_ready_or_current:
        missing_selections = sorted(
            key for key, value in selections.items() if value is None
        )
        if missing_selections:
            ctx.error(
                "PROJECT_SELECTION_REQUIRED",
                "Gate readiness requires explicit project selections: "
                + ", ".join(missing_selections),
                PRD_FILE,
            )
    if (
        selections["mode"] == "greenfield"
        and project.get("brownfield_baseline") != "NOT_APPLICABLE"
    ):
        ctx.error(
            "BROWNFIELD_STATE",
            "Greenfield mode requires NOT_APPLICABLE brownfield state",
            STATE_FILE,
        )
    if selections["mode"] == "brownfield" and gate_a_ready_or_current:
        if project.get("brownfield_baseline") != "RECORDED":
            ctx.error(
                "BROWNFIELD_STATE",
                "Brownfield mode requires a RECORDED baseline before Gate A is presented or approved",
                STATE_FILE,
            )
        validate_brownfield_contract(ctx, text)

    requirements_present = not unresolved(workload.get("Business outcome", ""))
    functional_match = re.search(
        r"^### Functional requirements\s*$.*?(?=^##\s+7\.)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if functional_match is not None:
        rows = re.findall(
            r"^\|\s*FR-\d+\s*\|(.+)$", functional_match.group(0), re.MULTILINE
        )
        requirements_present = requirements_present and any(
            "TODO" not in row.upper() for row in rows
        )
    requirements_present = (
        requirements_present and intake_contract.status == "READY_FOR_REQUIREMENTS"
    )

    if gate_a_ready_or_current:
        if (
            gate_a_agent.get("Requirements revision analyzed")
            != fields["requirements_revision"]
        ):
            ctx.error(
                "GATE_A_REVISION_MISMATCH",
                "Gate A analysis does not match current REQ",
                PRD_FILE,
            )
        if gate_a_agent.get("Agent recommendation") not in {
            "READY_WITH_PROPOSED_ASSUMPTIONS",
            "READY_FOR_OWNER_APPROVAL",
        }:
            ctx.error("GATE_A_RECOMMENDATION", "Gate A was not agent-ready", PRD_FILE)
        for key in ("Open blocking finding IDs", "Open blocking decision IDs"):
            if gate_a_agent.get(key) != "NONE":
                ctx.error(
                    "GATE_A_BLOCKER",
                    f"{key} must be NONE before owner approval",
                    PRD_FILE,
                )

    if fields["gate_a"] == "APPROVED_FOR_DESIGN":
        expected = "\n".join(
            [
                "APPROVE REQUIREMENTS GATE A",
                f"Requirements revision: {fields['requirements_revision']}",
                f"Cost posture: {card_cost_posture}",
                f"Accepted assumptions: {gate_a_owner.get('Explicitly accepted assumption IDs', '')}",
                f"Approver: {gate_a_owner.get('Approver', '')}",
            ]
        )
        if (
            gate_a_owner.get("Owner decision") != "APPROVED"
            or gate_a_owner.get("Authorized requirements revision")
            != fields["requirements_revision"]
        ):
            ctx.error(
                "GATE_A_OWNER_RECORD",
                "Gate A owner record is not current and approved",
                PRD_FILE,
            )
        if gate_a_owner.get("Authorized cost posture") != card_cost_posture:
            ctx.error(
                "GATE_A_COST_AUTHORIZATION",
                "Gate A owner record does not authorize the exact readiness-card cost posture",
                PRD_FILE,
            )
        if gate_a_owner.get("Derived Gate A state") != fields["gate_a"]:
            ctx.error(
                "GATE_A_OWNER_RECORD",
                "Detailed Gate A state does not match Document status",
                PRD_FILE,
            )
        if not explicit_human_approver(gate_a_owner.get("Approver", "")):
            ctx.error(
                "GATE_A_HUMAN_APPROVER",
                "Gate A approver must be an explicit human owner, not an agent or automation identity",
                PRD_FILE,
            )
        if not explicit_timestamp(gate_a_owner.get("Authorization provided at", "")):
            ctx.error(
                "GATE_A_OWNER_RECORD",
                "Gate A authorization time must be an explicit ISO 8601 timestamp with timezone",
                PRD_FILE,
            )
        if not explicit_value(gate_a_owner.get("Authorization source", "")):
            ctx.error(
                "GATE_A_OWNER_RECORD",
                "Gate A authorization source is unresolved",
                PRD_FILE,
            )
        if gate_a_owner.get("Verbatim owner receipt") != "RECORDED_BELOW":
            ctx.error(
                "GATE_A_OWNER_RECORD",
                "Approved Gate A must reference the marked receipt block",
                PRD_FILE,
            )
        try:
            required_ids = parse_exact_id_list(
                gate_a_agent.get("Proposed assumption IDs required to proceed", ""),
                re.compile(r"ASM-\d+"),
                "Gate A proposed assumptions",
            )
            accepted_ids = parse_exact_id_list(
                gate_a_owner.get("Explicitly accepted assumption IDs", ""),
                re.compile(r"ASM-\d+"),
                "Gate A accepted assumptions",
            )
            if required_ids != accepted_ids:
                ctx.error(
                    "GATE_A_ASSUMPTIONS",
                    "Accepted assumption IDs must exactly equal the required IDs in the same order",
                    PRD_FILE,
                )
        except ValueError as exc:
            ctx.error("GATE_A_ASSUMPTIONS", str(exc), PRD_FILE)
        try:
            actual = marked_receipt(text, "gate-a")
            if actual != expected:
                ctx.error(
                    "GATE_A_RECEIPT_MISMATCH",
                    "Marked Gate A receipt does not match structured fields",
                    PRD_FILE,
                )
        except ValueError as exc:
            ctx.error("GATE_A_RECEIPT_MISMATCH", str(exc), PRD_FILE)

    if gate_b_ready_or_current:
        reviewed = {
            "Requirements revision reviewed": fields["requirements_revision"],
            "Design revision reviewed": fields["design_revision"],
            "Construction authorization ID reviewed": fields[
                "construction_authorization"
            ],
        }
        for key, value in reviewed.items():
            if gate_b_agent.get(key) != value:
                ctx.error(
                    "GATE_B_REVISION_MISMATCH",
                    f"{key} does not match current state",
                    PRD_FILE,
                )
        if (
            gate_b_agent.get("Construction envelope SHA-256 reviewed")
            != envelope_digest
        ):
            ctx.error(
                "GATE_B_ENVELOPE_HASH",
                "Gate B agent review does not bind the complete current construction envelope",
                PRD_FILE,
            )
        if (
            gate_b_agent.get("Agent recommendation")
            != "READY_FOR_CONSTRUCTION_APPROVAL"
        ):
            ctx.error("GATE_B_RECOMMENDATION", "Gate B was not agent-ready", PRD_FILE)
        for key in (
            "PRD completeness gaps",
            "Requirement-to-design-and-test traceability gaps",
            "Unresolved risk or preservation gaps",
        ):
            if gate_b_agent.get(key) != "NONE":
                ctx.error(
                    "GATE_B_GAP", f"{key} must be NONE before owner approval", PRD_FILE
                )
        validate_construction_envelope(
            ctx,
            envelope,
            fields,
            selections,
            str(project.get("cost_posture", "")),
            design_contract,
        )

    if fields["gate_b"] == "APPROVED_FOR_CONSTRUCTION":
        if fields["gate_a"] != "APPROVED_FOR_DESIGN":
            ctx.error(
                "GATE_B_WITHOUT_GATE_A",
                "Gate B cannot be current while Gate A is not current",
                PRD_FILE,
            )
        if (
            gate_b_owner.get("Authorized construction envelope SHA-256")
            != envelope_digest
        ):
            ctx.error(
                "GATE_B_ENVELOPE_HASH",
                "Gate B owner authorization does not bind the complete current construction envelope",
                PRD_FILE,
            )
        expected = "\n".join(
            [
                "APPROVE PRD AND CONSTRUCTION GATE B",
                f"Requirements revision: {fields['requirements_revision']}",
                f"Design revision: {fields['design_revision']}",
                f"Construction authorization: {fields['construction_authorization']}",
                f"Construction envelope SHA-256: {envelope_digest}",
                "Use the proposed construction envelope above.",
                f"Approver: {gate_b_owner.get('Approver', '')}",
            ]
        )
        owner_values = {
            "Authorized requirements revision": fields["requirements_revision"],
            "Authorized design revision": fields["design_revision"],
            "Authorized construction authorization ID": fields[
                "construction_authorization"
            ],
        }
        if gate_b_owner.get("Owner decision") != "APPROVED":
            ctx.error(
                "GATE_B_OWNER_RECORD", "Gate B owner decision is not APPROVED", PRD_FILE
            )
        for key, value in owner_values.items():
            if gate_b_owner.get(key) != value:
                ctx.error(
                    "GATE_B_OWNER_RECORD",
                    f"{key} does not match current state",
                    PRD_FILE,
                )
        if not explicit_human_approver(gate_b_owner.get("Approver", "")):
            ctx.error(
                "GATE_B_HUMAN_APPROVER",
                "Gate B approver must be an explicit human owner, not an agent or automation identity",
                PRD_FILE,
            )
        if not explicit_timestamp(gate_b_owner.get("Authorization provided at", "")):
            ctx.error(
                "GATE_B_OWNER_RECORD",
                "Gate B authorization time must be an explicit ISO 8601 timestamp with timezone",
                PRD_FILE,
            )
        if not explicit_value(gate_b_owner.get("Authorization source", "")):
            ctx.error(
                "GATE_B_OWNER_RECORD",
                "Gate B authorization source is unresolved",
                PRD_FILE,
            )
        if gate_b_owner.get("Derived Gate B state") != fields["gate_b"]:
            ctx.error(
                "GATE_B_OWNER_RECORD",
                "Detailed Gate B state does not match Document status",
                PRD_FILE,
            )
        if gate_b_owner.get("Verbatim owner receipt") != "RECORDED_BELOW":
            ctx.error(
                "GATE_B_OWNER_RECORD",
                "Approved Gate B must reference the marked receipt block",
                PRD_FILE,
            )
        try:
            actual = marked_receipt(text, "gate-b")
            if actual != expected:
                ctx.error(
                    "GATE_B_RECEIPT_MISMATCH",
                    "Marked Gate B receipt does not match structured fields",
                    PRD_FILE,
                )
        except ValueError as exc:
            ctx.error("GATE_B_RECEIPT_MISMATCH", str(exc), PRD_FILE)

    return (
        fields,
        envelope,
        selections,
        requirements_present or gate_b_agent_ready,
        design_contract,
        coverage_contract,
        intake_contract,
        requirements_contract,
    )


def external_target_contains(allowed: str, requested: str) -> bool:
    allowed = allowed.casefold()
    requested = requested.casefold()
    if allowed == requested:
        return True
    return any(
        requested.startswith(allowed + separator) for separator in ("/", ":", "#")
    )


def validate_tasks_against_envelope(
    ctx: Context,
    tasks: list[InspectedTask],
    snapshot: dict[str, str],
    state: dict[str, Any],
    envelope: dict[str, str],
) -> None:
    try:
        maximum_tasks = int(envelope.get("Maximum generated tasks", ""))
        maximum_workers = int(envelope.get("Maximum parallel workers", ""))
        maximum_attempts = int(envelope.get("Attempt budget", ""))
        snapshot_workers = int(snapshot.get("Maximum workers", ""))
        allowed_writes = parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
        )
        excluded_writes = parse_envelope_paths(
            envelope.get("Excluded or owner-only write set", ""),
            "Excluded or owner-only write set",
            allow_none=True,
        )
        allowed_external = parse_envelope_targets(
            envelope.get("Allowed external-state targets", "")
        )
        authorized_protected = parse_envelope_paths(
            envelope.get("Protected dirty paths", ""),
            "Protected dirty paths",
            allow_none=True,
        )
        authorized_ids = set(
            parse_authorized_ids(
                envelope.get("Authorized requirement and design IDs", "")
            )
        )
        authorized_ids.update(ID_LIKE.findall(envelope.get("Authorized outcome", "")))
        boundary_mode, explicit_task_ids = parse_task_boundary(
            envelope.get("Task boundary", "")
        )
        command_prefixes = parse_command_prefixes(
            envelope.get("Local command boundary", "")
        )
        github_repo = parse_github_constraints(
            envelope.get("GitHub repository, branch, and merge constraints", ""),
            envelope.get("GitHub boundary", ""),
        )
        parse_future_expiry(
            envelope.get("Authorization expiry or completion condition", "")
        )
    except (ValueError, TypeError) as exc:
        if str(exc) == "Construction authorization is expired":
            ctx.error(
                "GATE_B_AUTHORITY_EXPIRED",
                "Gate B authority expired; the owner must reapprove the current "
                "design boundary before any new local or AWS operation",
                PRD_FILE,
            )
        else:
            ctx.error(
                "GATE_B_ENVELOPE",
                f"Cannot validate task boundaries: {exc}",
                PRD_FILE,
            )
        return
    if len(tasks) > maximum_tasks:
        ctx.error(
            "TASK_LIMIT_EXCEEDED",
            f"{len(tasks)} tasks exceed AUTH maximum {maximum_tasks}",
            TASKS_FILE,
        )
    if snapshot_workers > maximum_workers:
        ctx.error(
            "WORKER_LIMIT_EXCEEDED", "TASKS Maximum workers exceeds AUTH", TASKS_FILE
        )
    if maximum_workers != 1:
        ctx.error(
            "GATE_B_ENVELOPE",
            "Current AUTH must permit exactly one parallel worker",
            PRD_FILE,
        )
    if snapshot.get("Baseline commit") != envelope.get("Authorized baseline commit"):
        ctx.error(
            "TASK_BASELINE_DRIFT",
            "TASKS baseline commit does not match AUTH",
            TASKS_FILE,
        )
    snapshot_protected = snapshot.get("Protected dirty paths", "NONE")
    try:
        task_protected = (
            []
            if snapshot_protected == "NONE"
            else parse_task_write_set(snapshot_protected, "Protected dirty paths")
        )
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
        task_protected = []
    if [item.casefold() for item in task_protected] != [
        item.casefold() for item in authorized_protected
    ]:
        ctx.error(
            "TASK_BASELINE_DRIFT",
            "TASKS protected dirty paths do not match AUTH",
            TASKS_FILE,
        )

    execution = (
        state.get("execution") if isinstance(state.get("execution"), dict) else {}
    )
    if (
        execution.get("mode") == "AUTONOMOUS"
        and envelope.get("Autonomous construction") != "ALLOWED"
    ):
        ctx.error(
            "AUTONOMY_OUTSIDE_AUTH",
            "AUTONOMOUS run is not allowed by Gate B",
            STATE_FILE,
        )
    if not tasks:
        return

    github_boundary = envelope.get("GitHub boundary", "NONE")
    aws_boundary = envelope.get("AWS boundary", "NONE")
    protected = snapshot.get("Protected dirty paths", "NONE")
    try:
        protected_paths = (
            []
            if protected == "NONE"
            else parse_task_write_set(protected, "Protected dirty paths")
        )
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
        protected_paths = []

    for task in tasks:
        try:
            writes = parse_task_write_set(task.metadata["Write set"], task.task_id)
            external_targets = parse_task_external_state(
                task.metadata["External state"], task.task_id
            )
        except (KeyError, ValueError):
            continue
        for requested in writes:
            if not any(
                path_boundary_contains(allowed, requested) for allowed in allowed_writes
            ):
                ctx.error(
                    "TASK_OUTSIDE_WRITE_BOUNDARY",
                    f"{task.task_id} write {requested!r} is outside AUTH",
                    TASKS_FILE,
                )
            if any(
                path_boundaries_overlap(requested, excluded)
                for excluded in excluded_writes
            ):
                ctx.error(
                    "TASK_EXCLUDED_WRITE",
                    f"{task.task_id} overlaps excluded path {requested!r}",
                    TASKS_FILE,
                )
            if task.status in {"READY", "IN_PROGRESS"} and any(
                path_boundaries_overlap(requested, dirty) for dirty in protected_paths
            ):
                ctx.error(
                    "TASK_PROTECTED_DIRTY_OVERLAP",
                    f"{task.task_id} overlaps protected dirty path {requested!r}",
                    TASKS_FILE,
                )
        for target in external_targets:
            if not any(
                external_target_contains(allowed, target)
                for allowed in allowed_external
            ):
                ctx.error(
                    "TASK_EXTERNAL_STATE_BOUNDARY",
                    f"{task.task_id} external target {target!r} is outside AUTH",
                    TASKS_FILE,
                )
        if boundary_mode == "EXPLICIT" and task.task_id not in explicit_task_ids:
            ctx.error(
                "TASK_OUTSIDE_TASK_BOUNDARY",
                f"{task.task_id} is not listed by AUTH",
                TASKS_FILE,
            )

        sections, _duplicates = inspect_task_sections(task.block)
        referenced_ids = set(ID_LIKE.findall(task.metadata.get("Requirements", "")))
        referenced_ids.update(
            item
            for item in ID_LIKE.findall(task.metadata.get("Design", ""))
            if TECHNOLOGY_DECISION_ID.fullmatch(item) is None
        )
        referenced_ids.update(ID_LIKE.findall(sections.get("Outcome", "")))
        outside_ids = sorted(referenced_ids - authorized_ids)
        if outside_ids:
            ctx.error(
                "TASK_ID_OUTSIDE_AUTH",
                f"{task.task_id} references unauthorized IDs: {', '.join(outside_ids)}",
                TASKS_FILE,
            )
        if task.status in {"READY", "IN_PROGRESS", "DONE"}:
            try:
                commands = validation_commands(
                    sections.get("Validation", ""), task.task_id
                )
                for command in commands:
                    if not any(
                        command_matches_prefix(command, prefix)
                        for prefix in command_prefixes
                    ):
                        ctx.error(
                            "TASK_COMMAND_BOUNDARY",
                            f"{task.task_id} command {command!r} is outside AUTH",
                            TASKS_FILE,
                        )
            except ValueError as exc:
                ctx.error("TASK_COMMAND_BOUNDARY", str(exc), TASKS_FILE)
        try:
            if task.attempt_budget > maximum_attempts:
                ctx.error(
                    "TASK_ATTEMPT_BOUNDARY",
                    f"{task.task_id} attempt budget exceeds AUTH",
                    TASKS_FILE,
                )
        except (KeyError, ValueError):
            pass
        aws_mode = clean_cell(task.metadata.get("AWS mode", "NONE")).upper()
        allowed_aws_modes = {
            "NONE": {"NONE"},
            "DOCS_ONLY": {"NONE", "DOCS_ONLY"},
            "READ_ONLY": {"NONE", "DOCS_ONLY"},
            "MUTATE_LISTED_RESOURCES": {"NONE", "DOCS_ONLY"},
        }
        if aws_mode not in allowed_aws_modes.get(aws_boundary, set()):
            ctx.error(
                "TASK_AWS_BOUNDARY",
                f"{task.task_id} AWS mode exceeds the local-task ceiling",
                TASKS_FILE,
            )
        issue = clean_cell(task.metadata.get("GitHub issue", "PENDING_SYNC"))
        if github_boundary in {"NONE", "READ_ONLY"} and issue != "PENDING_SYNC":
            ctx.error(
                "TASK_GITHUB_BOUNDARY",
                f"{task.task_id} has a GitHub write result outside AUTH",
                TASKS_FILE,
            )
        elif github_boundary not in {"NONE", "READ_ONLY"} and issue != "PENDING_SYNC":
            match = GITHUB_ISSUE_URL.fullmatch(issue)
            if (
                match is None
                or github_repo is None
                or match.group("repo").casefold() != github_repo.casefold()
            ):
                ctx.error(
                    "TASK_GITHUB_BOUNDARY",
                    f"{task.task_id} issue URL does not match the authorized GitHub repository",
                    TASKS_FILE,
                )

    active = [task for task in tasks if task.status == "IN_PROGRESS"]
    if len(active) > min(maximum_workers, snapshot_workers):
        ctx.error(
            "WORKER_LIMIT_EXCEEDED",
            "IN_PROGRESS tasks exceed the active worker limit",
            TASKS_FILE,
        )
    for index, first in enumerate(active):
        first_writes = parse_task_write_set(first.metadata["Write set"], first.task_id)
        first_external = parse_task_external_state(
            first.metadata["External state"], first.task_id
        )
        for second in active[index + 1 :]:
            second_writes = parse_task_write_set(
                second.metadata["Write set"], second.task_id
            )
            second_external = parse_task_external_state(
                second.metadata["External state"], second.task_id
            )
            conflict = any(
                path_boundaries_overlap(a, b)
                for a in first_writes
                for b in second_writes
            )
            conflict |= any(
                external_targets_overlap(a, b)
                for a in first_external
                for b in second_external
            )
            conflict |= clean_cell(first.metadata["AWS mode"]).upper() == "MUTATION"
            conflict |= clean_cell(second.metadata["AWS mode"]).upper() == "MUTATION"
            if conflict:
                ctx.error(
                    "ACTIVE_TASK_CONFLICT",
                    f"{first.task_id} conflicts with {second.task_id}",
                    TASKS_FILE,
                )


def git_read(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return subprocess.run(
        [
            resolve_trusted_git(root),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(root),
            *arguments,
        ],
        check=False,
        capture_output=True,
        env=environment,
        timeout=10,
    )


def parse_checkpoint_rows(tasks_text: str) -> list[CheckpointReceiptRow]:
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
        raise ValueError("Checkpoint table IDs must be unique")
    ordinals = [int(identifier.split("-", 1)[1]) for identifier in identifiers]
    if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
        raise ValueError("Checkpoint table IDs must be strictly monotonic")
    return rows


def parse_checkpoint_git_receipt(
    tasks_text: str,
    checkpoint_id: str,
) -> tuple[str, list[str]]:
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


def validate_checkpoint_record(
    ctx: Context,
    tasks_text: str,
    snapshot: dict[str, str],
    tasks: list[InspectedTask],
    verify_text: str | None,
) -> None:
    checkpoint_id = snapshot.get("Last checkpoint", "")
    try:
        rows = parse_checkpoint_rows(tasks_text)
        matching = [row for row in rows if row.checkpoint_id == checkpoint_id]
        if not rows or len(matching) != 1 or rows[-1].checkpoint_id != checkpoint_id:
            raise ValueError(
                f"{checkpoint_id}: must be the unique newest checkpoint row"
            )
        row = matching[0]
        if row.run_id != snapshot.get("Active run ID"):
            raise ValueError(
                f"{checkpoint_id}: checkpoint run does not match the snapshot"
            )
        if not explicit_timestamp(row.recorded_at):
            raise ValueError(
                f"{checkpoint_id}: checkpoint time must be ISO 8601 with timezone"
            )
        for prefix, expected in (
            ("REQ", snapshot.get("Requirements revision", "")),
            ("DES", snapshot.get("Design revision", "")),
            ("AUTH", snapshot.get("Construction authorization", "")),
        ):
            if re.findall(rf"\b{prefix}-\d{{4,}}\b", row.basis) != [expected]:
                raise ValueError(
                    f"{checkpoint_id}: checkpoint REQ/DES/AUTH basis is not current"
                )
        parse_checkpoint_git_receipt(tasks_text, checkpoint_id)
        if not explicit_value(row.task_outcomes):
            raise ValueError(
                f"{checkpoint_id}: task outcomes and attempts are unresolved"
            )
        for task in tasks:
            token = re.compile(
                rf"(?<![A-Za-z0-9-]){re.escape(task.task_id)}(?![A-Za-z0-9-])"
            )
            segments = [
                segment.strip()
                for segment in re.split(r"[;\n]", row.task_outcomes)
                if token.search(segment) is not None
            ]
            if (
                len(segments) != 1
                or re.search(rf"\b{re.escape(task.status)}\b", segments[0]) is None
            ):
                raise ValueError(
                    f"{checkpoint_id}: outcome for {task.task_id} is not current"
                )
            attempt = re.compile(
                rf"\battempts?(?:\s+used)?\s*[=:]\s*{task.attempts_used}"
                rf"(?:\s*/\s*{task.attempt_budget})?(?!\s*/\s*\d)\b",
                re.IGNORECASE,
            )
            if attempt.search(segments[0]) is None:
                raise ValueError(
                    f"{checkpoint_id}: attempts for {task.task_id} are not current"
                )
        if (
            not explicit_value(row.evidence_and_external)
            or re.search(r"\bevidence\b", row.evidence_and_external, re.IGNORECASE)
            is None
            or re.search(r"\bexternal\b", row.evidence_and_external, re.IGNORECASE)
            is None
        ):
            raise ValueError(
                f"{checkpoint_id}: evidence and external actions are unresolved"
            )
        evidence_cell = row.evidence_and_external
        for task in tasks:
            references = [
                match.group(0)
                for match in EVIDENCE_PATTERN.finditer(
                    clean_cell(task.metadata.get("Evidence", ""))
                )
            ]
            if any(
                re.search(
                    rf"(?<![A-Za-z0-9._-]){re.escape(reference)}(?![A-Za-z0-9._-])",
                    evidence_cell,
                    re.IGNORECASE,
                )
                is None
                for reference in references
            ):
                raise ValueError(
                    f"{checkpoint_id}: evidence for {task.task_id} is incomplete"
                )
        if (
            not explicit_value(row.blockers_and_next)
            or re.search(r"\bblockers?\b", row.blockers_and_next, re.IGNORECASE) is None
            or re.search(r"\bnext\b", row.blockers_and_next, re.IGNORECASE) is None
        ):
            raise ValueError(
                f"{checkpoint_id}: blockers and next action are unresolved"
            )
        structural_verify = (
            without_fenced_code(verify_text) if verify_text is not None else ""
        )
        if (
            re.search(
                rf"(?<![A-Za-z0-9-]){re.escape(checkpoint_id)}(?![A-Za-z0-9-])",
                structural_verify,
            )
            is None
        ):
            raise ValueError(
                f"{checkpoint_id}: checkpoint is not referenced in VERIFY.md"
            )
    except (KeyError, ValueError) as exc:
        ctx.error("CONSTRUCTION_CHECKPOINT_UNVERIFIED", str(exc), TASKS_FILE)


def validate_authorized_baseline_repository(ctx: Context, baseline: str) -> None:
    """Prove Gate B's full authorized baseline resolves in a regular worktree."""

    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", baseline) is None:
        return
    try:
        inside = git_read(ctx.root, "rev-parse", "--is-inside-work-tree")
        bare = git_read(ctx.root, "rev-parse", "--is-bare-repository")
        resolved = git_read(ctx.root, "rev-parse", "--verify", f"{baseline}^{{commit}}")
    except (OSError, subprocess.SubprocessError) as exc:
        ctx.error(
            "GATE_B_GIT_UNVERIFIED",
            f"Unable to inspect the authorized Git baseline read-only: {exc}",
            PRD_FILE,
        )
        return
    if (
        inside.returncode != 0
        or inside.stdout.strip() != b"true"
        or bare.returncode != 0
        or bare.stdout.strip() != b"false"
    ):
        ctx.error(
            "GATE_B_GIT_UNVERIFIED",
            "Gate B requires a regular local Git worktree",
            PRD_FILE,
        )
        return
    if (
        resolved.returncode != 0
        or resolved.stdout.decode("ascii", errors="replace").strip() != baseline
    ):
        ctx.error(
            "GATE_B_GIT_UNVERIFIED",
            "Authorized baseline commit does not resolve exactly in this repository",
            PRD_FILE,
        )


def validate_construction_repository(
    ctx: Context,
    snapshot: dict[str, str],
    *,
    tasks_text: str | None,
    reconcile_worktree: bool,
) -> None:
    """Prove construction Git history and, at checkpoints, current dirty state."""

    baseline = snapshot.get("Baseline commit", "")
    known_green = snapshot.get("Last known-green commit", "")
    for label, value in (
        ("Baseline commit", baseline),
        ("Last known-green commit", known_green),
    ):
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
            ctx.error(
                "CONSTRUCTION_GIT_UNVERIFIED",
                f"{label} must be a full lowercase Git commit ID",
                TASKS_FILE,
            )
            return

    checkpoint_commit: str | None = None
    checkpoint_dirty: list[str] | None = None
    if reconcile_worktree and tasks_text is not None:
        checkpoint_id = snapshot.get("Last checkpoint", "")
        if CHECKPOINT_ID.fullmatch(checkpoint_id) is None:
            ctx.error(
                "CONSTRUCTION_CHECKPOINT_UNVERIFIED",
                "Checkpointed construction requires a current checkpoint receipt",
                TASKS_FILE,
            )
            return
        try:
            checkpoint_commit, checkpoint_dirty = parse_checkpoint_git_receipt(
                tasks_text, checkpoint_id
            )
        except ValueError as exc:
            ctx.error("CONSTRUCTION_CHECKPOINT_UNVERIFIED", str(exc), TASKS_FILE)
            return

    try:
        inside = git_read(ctx.root, "rev-parse", "--is-inside-work-tree")
        bare = git_read(ctx.root, "rev-parse", "--is-bare-repository")
        head_result = git_read(ctx.root, "rev-parse", "--verify", "HEAD^{commit}")
        baseline_result = git_read(
            ctx.root, "rev-parse", "--verify", f"{baseline}^{{commit}}"
        )
        green_result = git_read(
            ctx.root, "rev-parse", "--verify", f"{known_green}^{{commit}}"
        )
        checkpoint_result = (
            git_read(
                ctx.root, "rev-parse", "--verify", f"{checkpoint_commit}^{{commit}}"
            )
            if checkpoint_commit is not None
            else None
        )
    except (OSError, subprocess.SubprocessError) as exc:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            f"Unable to inspect construction Git state read-only: {exc}",
            TASKS_FILE,
        )
        return
    if (
        inside.returncode != 0
        or inside.stdout.strip() != b"true"
        or bare.returncode != 0
        or bare.stdout.strip() != b"false"
    ):
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Construction requires a regular local Git worktree",
            TASKS_FILE,
        )
        return
    commit_results = [head_result, baseline_result, green_result]
    if checkpoint_result is not None:
        commit_results.append(checkpoint_result)
    if any(result.returncode != 0 for result in commit_results):
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Authorized baseline, last-known-green, or checkpoint commit cannot be resolved",
            TASKS_FILE,
        )
        return
    resolved_baseline = baseline_result.stdout.decode("ascii", errors="replace").strip()
    resolved_green = green_result.stdout.decode("ascii", errors="replace").strip()
    if resolved_baseline != baseline or resolved_green != known_green:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Construction commit identities must be exact full hashes",
            TASKS_FILE,
        )
        return
    if checkpoint_result is not None and (
        checkpoint_result.stdout.decode("ascii", errors="replace").strip()
        != resolved_green
    ):
        ctx.error(
            "CONSTRUCTION_CHECKPOINT_UNVERIFIED",
            "Checkpoint receipt commit does not match Last known-green commit",
            TASKS_FILE,
        )
        return

    try:
        baseline_ancestor = git_read(
            ctx.root, "merge-base", "--is-ancestor", baseline, known_green
        )
        green_ancestor = git_read(
            ctx.root, "merge-base", "--is-ancestor", known_green, "HEAD"
        )
        committed = git_read(
            ctx.root,
            "diff",
            "--name-only",
            "-z",
            "--relative",
            f"{known_green}..HEAD",
            "--",
            ".",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            f"Unable to compare construction Git history: {exc}",
            TASKS_FILE,
        )
        return
    if baseline_ancestor.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Authorized baseline is not an ancestor of Last known-green commit",
            TASKS_FILE,
        )
    if green_ancestor.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Last known-green commit is not an ancestor of current HEAD",
            TASKS_FILE,
        )
    if committed.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Unable to enumerate commits after Last known-green",
            TASKS_FILE,
        )
        return
    committed_paths = {
        item.decode("utf-8", errors="surrogateescape")
        for item in committed.stdout.split(b"\0")
        if item
    }
    unauthorized_committed = sorted(committed_paths - COORDINATOR_LEDGER_PATHS)
    if unauthorized_committed:
        ctx.error(
            "CONSTRUCTION_GIT_DRIFT",
            "Commits after Last known-green contain non-ledger paths: "
            + ", ".join(unauthorized_committed),
            TASKS_FILE,
        )

    if not reconcile_worktree:
        return
    try:
        tracked = git_read(
            ctx.root, "diff", "--name-only", "-z", "--relative", "HEAD", "--", "."
        )
        untracked = git_read(
            ctx.root, "ls-files", "--others", "--exclude-standard", "-z", "--", "."
        )
    except (OSError, subprocess.SubprocessError) as exc:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            f"Unable to enumerate the checkpoint worktree: {exc}",
            TASKS_FILE,
        )
        return
    if tracked.returncode != 0 or untracked.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Unable to enumerate the checkpoint worktree",
            TASKS_FILE,
        )
        return
    observed = {
        item.decode("utf-8", errors="surrogateescape")
        for payload in (tracked.stdout, untracked.stdout)
        for item in payload.split(b"\0")
        if item
    }
    observed_nonledger = observed - COORDINATOR_LEDGER_PATHS
    protected_value = snapshot.get("Protected dirty paths", "NONE")
    try:
        protected = (
            []
            if protected_value == "NONE"
            else parse_task_write_set(protected_value, "Protected dirty paths")
        )
    except ValueError as exc:
        ctx.error("CONSTRUCTION_GIT_UNVERIFIED", str(exc), TASKS_FILE)
        return
    if checkpoint_dirty is not None and {
        item.casefold() for item in checkpoint_dirty
    } != {item.casefold() for item in protected}:
        ctx.error(
            "CONSTRUCTION_CHECKPOINT_UNVERIFIED",
            "Checkpoint Dirty paths do not match Protected dirty paths",
            TASKS_FILE,
        )
    uncovered = sorted(
        path
        for path in observed_nonledger
        if not any(path_boundary_contains(boundary, path) for boundary in protected)
    )
    unused = sorted(
        boundary
        for boundary in protected
        if not any(
            path_boundary_contains(boundary, path) for path in observed_nonledger
        )
    )
    if uncovered or unused:
        details: list[str] = []
        if uncovered:
            details.append("unrecorded dirty paths=" + ", ".join(uncovered))
        if unused:
            details.append("recorded paths not dirty=" + ", ".join(unused))
        ctx.error(
            "CONSTRUCTION_WORKTREE_DRIFT",
            "Checkpoint protected paths do not exactly match the worktree: "
            + "; ".join(details),
            TASKS_FILE,
        )


def validate_resume_repository(
    ctx: Context,
    snapshot: dict[str, str],
    tasks_text: str | None = None,
) -> None:
    """Compatibility entry point for conservative checkpoint reconciliation."""

    validate_construction_repository(
        ctx,
        snapshot,
        tasks_text=tasks_text,
        reconcile_worktree=True,
    )


LEGACY_TASK_AWS_MODE = re.compile(
    r"^(?P<task>TASK-\d+): invalid AWS mode '(?:READ_ONLY|MUTATION)'$"
)


def record_task_graph_validation_errors(ctx: Context, message: str) -> None:
    """Project legacy authenticated task modes as a fail-closed replan."""

    issues = [line.strip() for line in message.splitlines() if line.strip()]
    legacy = [line for line in issues if LEGACY_TASK_AWS_MODE.fullmatch(line)]
    remaining = [line for line in issues if line not in legacy]
    if legacy:
        task_ids = sorted(
            {
                match.group("task")
                for line in legacy
                if (match := LEGACY_TASK_AWS_MODE.fullmatch(line)) is not None
            }
        )
        ctx.error(
            "TASK_AWS_MODE_REPLAN_REQUIRED",
            "Legacy authenticated task AWS mode requires replanning local work "
            f"for {', '.join(task_ids)}; preserve every DONE completion and "
            "append-only VERIFY evidence row rather than rewriting observed evidence",
            TASKS_FILE,
        )
    if remaining:
        ctx.error("TASK_GRAPH_INVALID", "\n".join(remaining), TASKS_FILE)


def validate_tasks(
    ctx: Context,
    state: dict[str, Any],
    prd_fields: dict[str, str],
    envelope: dict[str, str],
    requirements_contract: RequirementsContract,
    design_contract: DesignContract,
) -> TaskSummary:
    summary = TaskSummary()
    text = ctx.texts.get(TASKS_FILE) or safe_read_text(ctx, TASKS_FILE)
    if text is None:
        return summary
    try:
        snapshot = table_after_heading(text, "## Active execution snapshot")
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
        return summary

    if set(snapshot) != SNAPSHOT_FIELDS:
        missing = sorted(SNAPSHOT_FIELDS - set(snapshot))
        extra = sorted(set(snapshot) - SNAPSHOT_FIELDS)
        details: list[str] = []
        if missing:
            details.append("missing=" + ", ".join(missing))
        if extra:
            details.append("unexpected=" + ", ".join(extra))
        ctx.error(
            "TASK_SNAPSHOT",
            "Active execution snapshot fields must be exact: " + "; ".join(details),
            TASKS_FILE,
        )

    run_state = snapshot.get("Run state", "")
    if run_state not in SNAPSHOT_RUN_STATES:
        ctx.error("TASK_SNAPSHOT", f"Invalid Run state {run_state!r}", TASKS_FILE)
    try:
        snapshot_workers = int(snapshot.get("Maximum workers", ""))
        if snapshot_workers < 1:
            raise ValueError
    except ValueError:
        ctx.error(
            "TASK_SNAPSHOT", "Maximum workers must be a positive integer", TASKS_FILE
        )
    active_run_id = snapshot.get("Active run ID", "")
    coordinator = snapshot.get("Coordinator", "")
    if run_state == "NOT_STARTED":
        if active_run_id != "NONE" or coordinator != "UNASSIGNED":
            ctx.error(
                "TASK_SNAPSHOT",
                "NOT_STARTED requires no run ID and an unassigned coordinator",
                TASKS_FILE,
            )
    else:
        if RUN_ID.fullmatch(active_run_id) is None or coordinator in {
            "",
            "NONE",
            "UNASSIGNED",
            "TODO",
        }:
            ctx.error(
                "TASK_SNAPSHOT",
                "An active or checkpointed run requires a RUN ID and coordinator",
                TASKS_FILE,
            )
    current_wave = snapshot.get("Current wave", "")
    if current_wave != "NONE" and re.fullmatch(r"[1-9]\d*", current_wave) is None:
        ctx.error(
            "TASK_SNAPSHOT",
            "Current wave must be NONE or a positive integer",
            TASKS_FILE,
        )
    checkpoint = snapshot.get("Last checkpoint", "")
    if run_state in {"PAUSED", "BLOCKED", "COMPLETE"}:
        if CHECKPOINT_ID.fullmatch(checkpoint) is None:
            ctx.error(
                "TASK_SNAPSHOT", f"{run_state} requires a checkpoint ID", TASKS_FILE
            )
    elif checkpoint != "NONE":
        ctx.error(
            "TASK_SNAPSHOT",
            f"{run_state or 'unknown run state'} must not claim a checkpoint",
            TASKS_FILE,
        )
    try:
        if snapshot.get("Protected dirty paths") != "NONE":
            parse_task_write_set(
                snapshot.get("Protected dirty paths", ""), "Protected dirty paths"
            )
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
    if not explicit_value(snapshot.get("Next safe action", ""), allow_none=False):
        ctx.error("TASK_SNAPSHOT", "Next safe action must be explicit", TASKS_FILE)
    if snapshot.get("Gate B state") == "APPROVED_FOR_CONSTRUCTION":
        for key in ("Baseline commit", "Last known-green commit"):
            if (
                re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", snapshot.get(key, ""))
                is None
            ):
                ctx.error(
                    "TASK_SNAPSHOT",
                    f"Current Gate B requires a full lowercase {key}",
                    TASKS_FILE,
                )

    raw_plan = snapshot.get("Task-plan revision", "")
    summary.plan_state = snapshot.get("Task-plan state", "")
    summary.plan_revision = None if raw_plan == "UNINITIALIZED" else raw_plan
    if (
        summary.plan_revision is not None
        and PLAN_ID.fullmatch(summary.plan_revision) is None
    ):
        ctx.error(
            "TASK_PLAN_STATE",
            "Task-plan revision must be UNINITIALIZED or PLAN-nnnn",
            TASKS_FILE,
        )
    if summary.plan_state not in {"UNINITIALIZED", "CURRENT", "STALE"}:
        ctx.error(
            "TASK_PLAN_STATE",
            "Task-plan state must be UNINITIALIZED, CURRENT, or STALE",
            TASKS_FILE,
        )
    if summary.plan_revision is None and summary.plan_state != "UNINITIALIZED":
        ctx.error(
            "TASK_PLAN_STATE",
            "UNINITIALIZED revision requires UNINITIALIZED plan state",
            TASKS_FILE,
        )
    if summary.plan_revision is not None and summary.plan_state == "UNINITIALIZED":
        ctx.error(
            "TASK_PLAN_STATE",
            "Initialized revision cannot have UNINITIALIZED plan state",
            TASKS_FILE,
        )
    execution = (
        state.get("execution") if isinstance(state.get("execution"), dict) else {}
    )
    lifecycle = (
        state.get("lifecycle") if isinstance(state.get("lifecycle"), dict) else {}
    )
    if summary.plan_revision != execution.get("plan_revision"):
        ctx.error(
            "STATE_TASK_DRIFT",
            "Task-plan revision does not match bootstrap state",
            TASKS_FILE,
        )
    if summary.plan_state != execution.get("plan_state"):
        ctx.error(
            "STATE_TASK_DRIFT",
            "Task-plan state does not match bootstrap state",
            TASKS_FILE,
        )
    snapshot_pairs = {
        "Requirements revision": "requirements_revision",
        "Design revision": "design_revision",
        "Construction authorization": "construction_authorization",
        "Gate B state": "gate_b",
    }
    for snapshot_key, lifecycle_key in snapshot_pairs.items():
        if snapshot.get(snapshot_key) != lifecycle.get(lifecycle_key):
            ctx.error(
                "STATE_TASK_DRIFT",
                f"{snapshot_key} does not match lifecycle state",
                TASKS_FILE,
            )

    run_map = {
        "IDLE": "NOT_STARTED",
        "RUNNING": "RUNNING",
        "CHECKPOINTED": "PAUSED",
        "BLOCKED": "BLOCKED",
        "COMPLETE": "COMPLETE",
    }
    execution_state = (
        execution.get("state") if isinstance(execution.get("state"), str) else ""
    )
    expected_run = run_map.get(execution_state)
    if expected_run is not None and snapshot.get("Run state") != expected_run:
        ctx.error(
            "STATE_TASK_DRIFT", "Run state does not match bootstrap state", TASKS_FILE
        )
    expected_run_id = execution.get("run_id") or "NONE"
    if snapshot.get("Active run ID") != expected_run_id:
        ctx.error(
            "STATE_TASK_DRIFT",
            "Active run ID does not match bootstrap state",
            TASKS_FILE,
        )
    expected_coordinator = execution.get("coordinator") or "UNASSIGNED"
    if snapshot.get("Coordinator") != expected_coordinator:
        ctx.error(
            "STATE_TASK_DRIFT", "Coordinator does not match bootstrap state", TASKS_FILE
        )

    verify_text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    try:
        approved_tech_ids = {
            decision.decision_id for decision in design_contract.technology_decisions
        }
        property_execution_by_id = {
            execution.property_id: execution
            for execution in design_contract.property_execution
        }
        technology_decisions_by_id = {
            decision.decision_id: decision
            for decision in design_contract.technology_decisions
        }
        tasks, _by_id, ready = validate_task_records(
            text,
            snapshot,
            verify_text,
            approved_tech_ids,
            property_execution_by_id,
            technology_decisions_by_id,
        )
    except ValueError as exc:
        record_task_graph_validation_errors(ctx, str(exc))
        return summary

    missing_property_ids = missing_current_property_task_coverage(
        tasks,
        summary.plan_state,
        property_execution_by_id,
    )
    if missing_property_ids:
        ctx.error(
            "TASK_PROPERTY_COVERAGE",
            "CURRENT task plan does not cover approved property execution IDs: "
            + ", ".join(missing_property_ids),
            TASKS_FILE,
        )
    try:
        requirement_rules = (
            task_requirement_rules(ctx.texts.get(PRD_FILE, ""), requirements_contract)
            if summary.plan_state == "CURRENT"
            else {}
        )
        requirement_evidence, requirement_evidence_issues = (
            task_requirement_evidence_dispositions(
                verify_text,
                {
                    "Requirements revision": snapshot.get("Requirements revision", ""),
                    "Design revision": snapshot.get("Design revision", ""),
                    "Construction authorization": snapshot.get(
                        "Construction authorization", ""
                    ),
                },
                requirement_rules,
            )
        )
        requirement_coverage = derive_task_requirement_coverage(
            tasks,
            summary.plan_state,
            requirement_rules,
            requirement_evidence,
        )
    except ValueError as exc:
        ctx.error("TASK_REQUIREMENT_TRACE_INVALID", str(exc), TASKS_FILE)
    else:
        summary.requirement_coverage = {
            record.requirement_id: record.to_dict()
            for record in requirement_coverage.records
        }
        summary.missing_requirement_ids = list(
            requirement_coverage.missing_requirement_ids
        )
        summary.requirement_coverage_complete = bool(
            summary.plan_state == "CURRENT"
            and not requirement_coverage.trace_issues
            and not requirement_evidence_issues
            and not requirement_coverage.evidence_issues
            and not requirement_coverage.missing_requirement_ids
        )
        if requirement_coverage.trace_issues:
            ctx.error(
                "TASK_REQUIREMENT_TRACE_INVALID",
                "\n".join(requirement_coverage.trace_issues),
                TASKS_FILE,
            )
        all_evidence_issues = [
            *requirement_evidence_issues,
            *requirement_coverage.evidence_issues,
        ]
        if all_evidence_issues:
            ctx.error(
                "TASK_REQUIREMENT_COVERAGE_EVIDENCE_INVALID",
                "\n".join(all_evidence_issues),
                VERIFY_FILE,
            )
        if requirement_coverage.missing_requirement_ids:
            ctx.error(
                "TASK_REQUIREMENT_COVERAGE",
                "CURRENT task plan does not cover approved requirement IDs: "
                + ", ".join(requirement_coverage.missing_requirement_ids),
                TASKS_FILE,
            )

    if summary.plan_revision is None and tasks:
        ctx.error(
            "TASK_PLAN_STATE",
            "UNINITIALIZED task plan contains task blocks",
            TASKS_FILE,
        )
    if summary.plan_revision is not None and not tasks:
        ctx.error(
            "TASK_PLAN_STATE",
            "Initialized task plan contains no task blocks",
            TASKS_FILE,
        )
    if (
        summary.plan_state == "CURRENT"
        and prd_fields.get("gate_b") != "APPROVED_FOR_CONSTRUCTION"
    ):
        ctx.error(
            "TASK_PLAN_STATE", "CURRENT task plan requires current Gate B", TASKS_FILE
        )
    if summary.plan_state == "STALE" and any(
        task.status in {"READY", "IN_PROGRESS"} for task in tasks
    ):
        ctx.error(
            "TASK_PLAN_STATE",
            "STALE task plan cannot contain runnable or active tasks",
            TASKS_FILE,
        )

    summary.statuses = {task.task_id: task.status for task in tasks}
    summary.active = sorted(
        task.task_id for task in tasks if task.status == "IN_PROGRESS"
    )
    summary.ready = sorted(ready)
    summary.attempts_used = {task.task_id: task.attempts_used for task in tasks}
    summary.attempt_budgets = {task.task_id: task.attempt_budget for task in tasks}
    for task in tasks:
        try:
            summary.write_sets[task.task_id] = parse_task_write_set(
                task.metadata.get("Write set", ""), task.task_id
            )
        except ValueError:
            summary.write_sets[task.task_id] = []

    state_active_value = execution.get("active_tasks")
    state_active = (
        sorted(state_active_value)
        if isinstance(state_active_value, list)
        and all(isinstance(item, str) for item in state_active_value)
        else []
    )
    if summary.active != state_active:
        ctx.error(
            "STATE_TASK_DRIFT",
            "active_tasks does not match IN_PROGRESS task records",
            STATE_FILE,
        )
    task_attempts = {task.task_id: task.attempts_used for task in tasks}
    if execution.get("attempts") != task_attempts:
        ctx.error(
            "STATE_TASK_DRIFT", "attempt counters do not match task records", STATE_FILE
        )
    state_checkpoint = execution.get("last_checkpoint")
    expected_checkpoint = (
        state_checkpoint.get("id") if isinstance(state_checkpoint, dict) else "NONE"
    )
    if snapshot.get("Last checkpoint") != expected_checkpoint:
        ctx.error(
            "STATE_TASK_DRIFT",
            "Last checkpoint does not match bootstrap state",
            TASKS_FILE,
        )

    basis = execution.get("basis")
    if basis is not None:
        expected_basis = {
            "requirements_revision": prd_fields.get("requirements_revision"),
            "design_revision": prd_fields.get("design_revision"),
            "construction_authorization": prd_fields.get("construction_authorization"),
        }
        if basis != expected_basis:
            ctx.error(
                "RUN_BASIS_STALE",
                "Execution basis does not match current PRD revisions",
                STATE_FILE,
            )
    if prd_fields.get("gate_b") == "APPROVED_FOR_CONSTRUCTION" or tasks:
        validate_tasks_against_envelope(ctx, tasks, snapshot, state, envelope)
    construction_states = {"RUNNING", "CHECKPOINTED", "BLOCKED", "COMPLETE"}
    if execution_state in {"CHECKPOINTED", "BLOCKED", "COMPLETE"}:
        validate_checkpoint_record(ctx, text, snapshot, tasks, verify_text)
    if (
        prd_fields.get("gate_b") == "APPROVED_FOR_CONSTRUCTION"
        or execution_state in construction_states
    ):
        validate_construction_repository(
            ctx,
            snapshot,
            tasks_text=text,
            reconcile_worktree=execution_state
            in {"CHECKPOINTED", "BLOCKED", "COMPLETE"},
        )
    return summary


def validate_release_decision_record(ctx: Context) -> dict[str, str]:
    """Validate the release state and its durable evidence acknowledgment."""

    relative = VERIFY_FILE
    text = ctx.texts.get(relative) or safe_read_text(ctx, relative)
    if text is None:
        return {"release_state": "NOT_READY", "active_evidence_cutoff": "NONE"}
    heading = "## Current release decision"
    matches = list(re.finditer(rf"^{re.escape(heading)}[ \t]*$", text, re.MULTILINE))
    if len(matches) != 1:
        ctx.error("RELEASE_DECISION", f"Expected exactly one {heading!r}", relative)
        return {"release_state": "NOT_READY", "active_evidence_cutoff": "NONE"}
    section = text[matches[0].end() :]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    decisions = re.findall(r"^- Release state:\s*`([^`]+)`\s*$", section, re.MULTILINE)
    release_state = decisions[0] if len(decisions) == 1 else "NOT_READY"
    if len(decisions) != 1 or decisions[0] not in {
        "NOT_READY",
        "READY_TO_DEPLOY",
        "RELEASE_VERIFIED",
    }:
        ctx.error(
            "RELEASE_DECISION",
            "Release decision must be exactly NOT_READY, READY_TO_DEPLOY, or RELEASE_VERIFIED",
            relative,
        )
        release_state = "NOT_READY"
    cutoff_rows = re.findall(
        r"^- Active evidence cutoff:\s*(?P<value>[^\r\n]+?)\s*$",
        section,
        re.MULTILINE,
    )
    cutoff = clean_cell(cutoff_rows[0]) if len(cutoff_rows) == 1 else "NONE"
    if len(cutoff_rows) != 1 or (
        cutoff not in {"TODO", "NONE"} and re.fullmatch(r"EV-\d{4,}", cutoff) is None
    ):
        ctx.error(
            "RELEASE_EVIDENCE_CUTOFF",
            "Active evidence cutoff must appear exactly once and be TODO, NONE, "
            "or one canonical EV-* ID",
            relative,
        )
        cutoff = "NONE"
    return {
        "release_state": release_state,
        "active_evidence_cutoff": cutoff,
    }


def validate_release_decision(ctx: Context) -> str:
    """Compatibility wrapper returning only the validated release state."""

    return validate_release_decision_record(ctx)["release_state"]


AWS_LIFECYCLE_INTENT_VALUES = {"NONE", "RESIDUAL_REVIEW", "TEARDOWN", "RETAIN"}
AWS_LIFECYCLE_INTENT_SOURCE = re.compile(r"owner-message MSG-AWS-LIFECYCLE-\d{4,}")


def validate_aws_lifecycle_intent_record(ctx: Context) -> dict[str, Any]:
    """Validate the atomic, non-authorizing owner lifecycle-intent record."""

    legacy_none = {
        "value": "NONE",
        "source": "NONE",
        "recorded_at": "NONE",
        "provenance_status": "LEGACY_NONE",
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
    }
    text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    if text is None:
        return legacy_none
    heading = "## Current release decision"
    headings = list(re.finditer(rf"^{re.escape(heading)}[ \t]*$", text, re.MULTILINE))
    if len(headings) != 1:
        # validate_release_decision_record owns the structural diagnostic.
        return legacy_none
    section = text[headings[0].end() :]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    value_lines = list(
        re.finditer(
            r"^- AWS lifecycle intent:\s*`([^`]+)`\s*$",
            section,
            re.MULTILINE,
        )
    )
    source_lines = list(
        re.finditer(
            r"^- AWS lifecycle intent source:\s*`([^`]+)`\s*$",
            section,
            re.MULTILINE,
        )
    )
    recorded_lines = list(
        re.finditer(
            r"^- AWS lifecycle intent recorded at:\s*`([^`]+)`\s*$",
            section,
            re.MULTILINE,
        )
    )
    if not value_lines and not source_lines and not recorded_lines:
        return legacy_none
    if (
        len(value_lines) == 1
        and value_lines[0].group(1) == "NONE"
        and not source_lines
        and not recorded_lines
    ):
        return legacy_none
    exact_record = re.search(
        r"^- AWS lifecycle intent:\s*`([^`]+)`\s*\r?\n"
        r"- AWS lifecycle intent source:\s*`([^`]+)`\s*\r?\n"
        r"- AWS lifecycle intent recorded at:\s*`([^`]+)`\s*$",
        section,
        re.MULTILINE,
    )
    if (
        len(value_lines) != 1
        or len(source_lines) != 1
        or len(recorded_lines) != 1
        or exact_record is None
    ):
        ctx.error(
            "AWS_LIFECYCLE_INTENT_PROVENANCE",
            "AWS lifecycle intent must be one exact ordered value/source/recorded-at triple",
            VERIFY_FILE,
        )
        return legacy_none
    value, source, recorded_at = exact_record.groups()
    valid = value in AWS_LIFECYCLE_INTENT_VALUES
    if value == "NONE":
        valid = valid and source == "NONE" and recorded_at == "NONE"
    else:
        valid = bool(
            valid
            and AWS_LIFECYCLE_INTENT_SOURCE.fullmatch(source)
            and _iso_datetime(recorded_at) is not None
        )
    if not valid:
        ctx.error(
            "AWS_LIFECYCLE_INTENT_PROVENANCE",
            "Non-NONE AWS lifecycle intent requires an owner-message source and timezone-aware recorded-at value; NONE requires NONE provenance",
            VERIFY_FILE,
        )
        return legacy_none
    return {
        "value": value,
        "source": source,
        "recorded_at": recorded_at,
        "provenance_status": "CURRENT",
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
    }


def validate_aws_lifecycle_intent(ctx: Context) -> str:
    """Compatibility wrapper returning only the validated intent value."""

    return str(validate_aws_lifecycle_intent_record(ctx)["value"])


def derive_teardown_route(
    intent: str,
    teardown_sequence: Mapping[str, Any],
    residual_disposition: Mapping[str, Any] | None = None,
) -> tuple[str, str] | None:
    """Route residual review and teardown without treating intent as authority."""

    status = clean_cell(teardown_sequence.get("status", "NOT_ACTIVE"))
    if status == "ACTION_TERMINAL_REQUIRED":
        return "AWS_TEARDOWN_ACTION_TERMINAL", "AWS-50"
    if status == "POST_ACTION_REVIEW":
        return "AWS_RESIDUAL_REVIEW", "AWS-40"
    if status == "BLOCKED":
        return "AWS_RESIDUAL_REVIEW_BLOCKED", "STOP"
    disposition = residual_disposition or {}
    disposition_status = clean_cell(disposition.get("status", "NOT_APPLICABLE"))
    disposition_value = clean_cell(disposition.get("value", "NONE"))
    if status in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}:
        if disposition_status != "CURRENT":
            return "AWS_RESIDUALS_REMAIN", "STOP"
        if disposition_status == "CURRENT":
            if disposition_value == "RETAIN":
                return "AWS_RESIDUALS_RETAINED", "STOP"
            if disposition_value == "INVESTIGATE":
                return "AWS_RESIDUAL_REVIEW", "AWS-40"
            if disposition_value == "REMOVE":
                return (
                    ("WAITING_AWS_TEARDOWN_AUTH", "AWS-50")
                    if status == "READY_FOR_TEARDOWN"
                    else ("AWS_RESIDUAL_REVIEW", "AWS-40")
                )
    if intent == "NONE":
        return None
    if intent == "RESIDUAL_REVIEW":
        if status == "VERIFIED_CLEAN":
            return "AWS_RESIDUAL_REVIEW_COMPLETE", "STOP"
        return "AWS_RESIDUAL_REVIEW", "AWS-40"
    if intent == "TEARDOWN":
        if status == "VERIFIED_CLEAN":
            return (
                ("AWS_TEARDOWN_COMPLETE", "STOP")
                if teardown_sequence.get("post_action_bound") is True
                else ("AWS_RESIDUAL_REVIEW_COMPLETE", "STOP")
            )
        return "AWS_RESIDUAL_REVIEW", "AWS-40"
    return None


def derive_aws_residual_disposition(
    intent_record: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one non-authorizing residual choice to the latest AWS-40 evidence."""

    base: dict[str, Any] = {
        "status": "NOT_APPLICABLE",
        "value": "NONE",
        "basis_evidence_id": "NONE",
        "basis_status": "NONE",
        "basis_observed_at": "NONE",
        "recorded_at": clean_cell(intent_record.get("recorded_at", "NONE")),
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
        "issues": [],
    }
    basis_status = clean_cell(teardown_sequence.get("status", "NOT_ACTIVE"))
    intent = clean_cell(intent_record.get("value", "NONE"))
    if basis_status not in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}:
        if intent == "RETAIN":
            return {
                **base,
                "status": "INVALID",
                "issues": ["RETAIN requires current residual-resource evidence"],
            }
        return base
    basis_observed_at = clean_cell(teardown_sequence.get("observed_at", ""))
    basis_time = _iso_datetime(basis_observed_at)
    recorded_at = clean_cell(intent_record.get("recorded_at", ""))
    record_time = _iso_datetime(recorded_at)
    projection = {
        **base,
        "status": "PENDING",
        "basis_evidence_id": clean_cell(teardown_sequence.get("evidence_id", "NONE")),
        "basis_status": basis_status,
        "basis_observed_at": basis_observed_at or "NONE",
        "recorded_at": recorded_at or "NONE",
    }
    if basis_time is None:
        return {
            **projection,
            "status": "INVALID",
            "issues": ["Residual disposition basis lacks an exact observed timestamp"],
        }
    mapped = {
        "RETAIN": "RETAIN",
        "RESIDUAL_REVIEW": "INVESTIGATE",
        "TEARDOWN": "REMOVE",
    }.get(intent)
    if (
        mapped is None
        or intent_record.get("provenance_status") != "CURRENT"
        or record_time is None
    ):
        return projection
    if basis_status == "RESIDUALS_REMAIN" and record_time <= basis_time:
        return projection
    if (
        basis_status == "READY_FOR_TEARDOWN"
        and intent != "TEARDOWN"
        and record_time <= basis_time
    ):
        return projection
    return {**projection, "status": "CURRENT", "value": mapped}


def aws_deployment_teardown_sequence_conflict(
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> bool:
    """Reject simultaneous open deployment and teardown journal epochs."""

    deployment_status = clean_cell(deployment_sequence.get("status", ""))
    teardown_status = clean_cell(teardown_sequence.get("status", ""))
    deployment_open = deployment_status not in {"", "NONE", "NOT_ACTIVE", "CONSUMED"}
    teardown_open = teardown_status not in {
        "",
        "NONE",
        "NOT_ACTIVE",
        "VERIFIED_CLEAN",
        "RESIDUALS_REMAIN",
    }
    return deployment_open and teardown_open


def release_lifecycle_intent_boundary_is_settled(
    release_decision: str, deployment_sequence: Mapping[str, Any]
) -> bool:
    """Allow elective post-release intent only at an auditable boundary."""

    deployment_status = clean_cell(deployment_sequence.get("status", ""))
    return bool(
        not deployment_sequence.get("issues")
        and (
            (
                release_decision == "RELEASE_VERIFIED"
                and deployment_status in {"NOT_ACTIVE", "CONSUMED"}
            )
            or (release_decision == "NOT_READY" and deployment_status == "CONSUMED")
        )
    )


def aws_lifecycle_intent_route_is_eligible(
    intent: str,
    lifecycle_state: str,
    release_decision: str,
    tasks: TaskSummary,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> bool:
    """Return whether elective owner intent may enter AWS-40 now."""

    return bool(
        intent in {"RESIDUAL_REVIEW", "TEARDOWN"}
        and (
            lifecycle_state in {"RELEASE_REVIEW", "RELEASE_VERIFIED"}
            or clean_cell(deployment_sequence.get("status", "")) == "CONSUMED"
        )
        and (
            tasks.terminal
            or clean_cell(deployment_sequence.get("status", "")) == "CONSUMED"
        )
        and release_lifecycle_intent_boundary_is_settled(
            release_decision, deployment_sequence
        )
        and clean_cell(teardown_sequence.get("status", ""))
        not in {"ACTION_TERMINAL_REQUIRED", "POST_ACTION_REVIEW"}
        and not teardown_sequence.get("issues")
    )


def derive_route(
    gate_a: str,
    gate_b: str,
    requirements_present: bool,
    gate_b_agent_ready: bool,
    tasks: TaskSummary,
    autonomous_allowed: bool,
    execution_mode: str,
    release_decision: str = "NOT_READY",
) -> tuple[str, str]:
    if gate_a == "STALE":
        return (
            ("REQUIREMENTS_STALE", "REQ-10")
            if requirements_present
            else ("INTAKE_REQUIRED", "INTAKE-10")
        )
    if gate_a == "BLOCKED":
        return (
            ("REQUIREMENTS_ANALYSIS", "REQ-10")
            if requirements_present
            else ("INTAKE_REQUIRED", "INTAKE-10")
        )
    if gate_a == "PENDING_OWNER_APPROVAL":
        return "WAITING_GATE_A", "INTAKE-20"
    if gate_a != "APPROVED_FOR_DESIGN":
        return "BLOCKED", "STOP"
    if gate_b == "STALE":
        return "DESIGN_STALE", "DESIGN-10"
    if gate_b == "BLOCKED":
        return (
            ("WAITING_GATE_B", "DESIGN-20")
            if gate_b_agent_ready
            else ("DESIGN_REQUIRED", "DESIGN-10")
        )
    if gate_b == "PENDING_OWNER_APPROVAL":
        return "WAITING_GATE_B", "DESIGN-20"
    if gate_b != "APPROVED_FOR_CONSTRUCTION":
        return "BLOCKED", "STOP"
    if tasks.plan_state in {"UNINITIALIZED", "STALE"}:
        return "TASK_PLAN_REQUIRED", "TASK-10"
    if tasks.active:
        if execution_mode == "AUTONOMOUS" and autonomous_allowed:
            return "CONSTRUCTION_AUTONOMOUS", "BUILD-20"
        if len(tasks.active) == 1:
            return "CONSTRUCTION_SINGLE", "BUILD-10"
        return "BLOCKED", "STOP"
    if len(tasks.ready) == 1:
        return "CONSTRUCTION_SINGLE", "BUILD-10"
    if len(tasks.ready) > 1:
        if autonomous_allowed:
            return "CONSTRUCTION_AUTONOMOUS", "BUILD-20"
        return "BLOCKED", "STOP"
    if tasks.terminal:
        if release_decision == "READY_TO_DEPLOY":
            return "AWS_PREFLIGHT_REQUIRED", "AWS-10"
        if release_decision == "RELEASE_VERIFIED":
            return "RELEASE_VERIFIED", "STOP"
        return "RELEASE_REVIEW", "RELEASE-10"
    return "BLOCKED", "STOP"


def derive_aws_delivery_route(
    release_decision: str,
    aws_execution: Mapping[str, Any],
    deployment_sequence: Mapping[str, Any],
    lane: str | None,
    release_evidence_cutoff: str = "NONE",
) -> tuple[str, str] | None:
    """Route a release without confusing authority with an attempted action."""

    deployment_status = clean_cell(deployment_sequence.get("status", ""))
    if deployment_sequence.get("issues"):
        return "BLOCKED", "STOP"
    if deployment_status == "ACTION_TERMINAL_REQUIRED":
        return "AWS_DEPLOYMENT_ACTION_TERMINAL", "AWS-20"
    if deployment_status == "RECONCILIATION_REQUIRED":
        return "AWS_DEPLOYMENT_RECONCILIATION", "AWS-30"
    if deployment_status in {"RECONCILED", "BLOCKED"}:
        terminal_evidence = clean_cell(deployment_sequence.get("evidence_id", ""))
        if release_evidence_cutoff != terminal_evidence:
            return "RELEASE_REVIEW", "RELEASE-10"
    if deployment_status == "CONSUMED":
        if release_decision == "NOT_READY":
            return "RELEASE_REVIEW_BLOCKED", "STOP"
        if release_decision != "READY_TO_DEPLOY":
            return None
        if (
            clean_cell(deployment_sequence.get("current_mutation_authority_status", ""))
            == "UNAVAILABLE"
        ):
            return None
    if release_decision != "READY_TO_DEPLOY":
        return None
    progress_state = clean_cell(aws_execution.get("progress_state", ""))
    if progress_state == "WAITING_AWS_MUTATION_AUTH":
        return "WAITING_AWS_MUTATION_AUTH", "AWS-20"
    if progress_state == "AWS_PREFLIGHT_READY" and lane == "fast-dev":
        return "AWS_PREFLIGHT_READY", "AWS-20"
    if progress_state == "AWS_PREFLIGHT_READY":
        return "AWS_PREFLIGHT_READY", "STOP"
    return progress_state or "AWS_PREFLIGHT_REQUIRED", "AWS-10"


def _preserve_expired_authority_for_deployment_closure(
    ctx: Context,
    deployment_sequence: Mapping[str, Any],
    release_decision: str,
) -> None:
    status = clean_cell(deployment_sequence.get("status", ""))
    terminal_reconciliation = bool(
        (
            status in {"RECONCILED", "BLOCKED"}
            or (status == "CONSUMED" and release_decision != "READY_TO_DEPLOY")
        )
        and not deployment_sequence.get("issues")
        and clean_cell(deployment_sequence.get("phase", "")) == "AWS-30"
        and clean_cell(deployment_sequence.get("reconciliation_status", ""))
        in {"COMPLETE", "BLOCKED"}
    )
    read_only_reconciliation = bool(
        status == "RECONCILIATION_REQUIRED"
        and not deployment_sequence.get("issues")
        and clean_cell(deployment_sequence.get("action_status", ""))
        in AWS_DEPLOYMENT_TERMINAL_STATUSES
    )
    completed_without_attempt = bool(
        status == "NOT_ACTIVE" and release_decision == "RELEASE_VERIFIED"
    )
    if (
        status != "ACTION_TERMINAL_REQUIRED"
        and not read_only_reconciliation
        and not terminal_reconciliation
        and not completed_without_attempt
    ):
        return
    ctx.diagnostics[:] = [
        Diagnostic(item.code, item.message, item.path, "WARNING")
        if item.code == "GATE_B_AUTHORITY_EXPIRED"
        else item
        for item in ctx.diagnostics
    ]


def _preserve_expired_authority_for_teardown_closure(
    ctx: Context, teardown_sequence: Mapping[str, Any]
) -> None:
    """Keep only the local UNKNOWN closure after a valid teardown STARTED row."""

    if clean_cell(teardown_sequence.get("status", "")) not in {
        "ACTION_TERMINAL_REQUIRED",
        "POST_ACTION_REVIEW",
    } or teardown_sequence.get("issues"):
        return
    ctx.diagnostics[:] = [
        Diagnostic(item.code, item.message, item.path, "WARNING")
        if item.code == "GATE_B_AUTHORITY_EXPIRED"
        else item
        for item in ctx.diagnostics
    ]


def _preserve_specialized_teardown_block(ctx: Context, lifecycle_state: str) -> bool:
    """Keep the teardown safety route only when every error belongs to it."""

    return lifecycle_state == "AWS_RESIDUAL_REVIEW_BLOCKED" and all(
        item.severity != "ERROR" or item.code == "AWS_TEARDOWN_EVIDENCE_INVALID"
        for item in ctx.diagnostics
    )


def inspect_project(
    root: Path,
    *,
    template_source: bool = False,
    prior_remediation_fingerprint: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    ctx = Context(
        root=root,
        template_source=template_source,
        prior_remediation_fingerprint=prior_remediation_fingerprint,
    )
    if not root.is_dir():
        ctx.error("PROJECT_ROOT", "Project root is not a directory", str(root))
        return build_report(ctx, "BLOCKED", "STOP", {}, TaskSummary())

    manifest = load_json_document(ctx, MANIFEST_FILE, "MANIFEST_PARSE")
    state = load_json_document(ctx, STATE_FILE, "STATE_PARSE")
    if manifest is None or state is None:
        return build_report(
            ctx,
            "BLOCKED",
            "STOP",
            {},
            TaskSummary(),
            manifest=manifest,
            state=state,
        )

    ctx.manifest_document = manifest
    ctx.bootstrap_state_document = state

    validate_manifest(ctx, manifest)
    state_sections_valid = validate_state_schema(ctx, state)
    validate_prompt_pack(ctx, manifest, state)
    if not state_sections_valid:
        validate_placeholders(ctx)
        return build_report(
            ctx,
            "BLOCKED",
            "STOP",
            {},
            TaskSummary(),
            manifest=manifest,
            state=state,
        )
    (
        prd_fields,
        envelope,
        selections,
        requirements_present,
        design_contract,
        coverage_contract,
        intake_contract,
        requirements_contract,
    ) = validate_prd(ctx, state)
    adr_rationale, adr_rationale_issues, adr_sources = derive_adr_rationale(
        root,
        design_contract.to_dict(),
        ctx.texts.get(PRD_FILE, ""),
    )
    for issue in adr_rationale_issues:
        ctx.error(
            str(issue.get("code", "ADR_RATIONALE_MALFORMED")),
            str(issue.get("message", "ADR rationale is invalid")),
            str(issue["path"]) if issue.get("path") else None,
        )
    for relative, expected_text in adr_sources.items():
        observed_text = safe_read_text(ctx, relative)
        if observed_text is not None and observed_text != expected_text:
            ctx.error(
                "ADR_RATIONALE_STALE",
                "ADR content changed during Engine inspection; rerun validation.",
                relative,
            )
    allow_legacy_design_discovery = bool(
        prd_fields.get("gate_b") == "APPROVED_FOR_CONSTRUCTION"
        and design_contract.architecture.schema_version < 4
    )
    aws_core_rows: dict[tuple[str, str, str], AwsCoreEvidenceRow] = {}
    blocking_aws_core_phases: set[str] = set()
    verify_text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    if verify_text is not None:
        try:
            active_scope = table_after_heading(verify_text, "## Active evidence scope")
        except ValueError:
            active_scope = {}
        verify_name = html.unescape(clean_cell(active_scope.get("Workload", "")))
        if verify_name and state.get("project", {}).get("name") != verify_name:
            ctx.error(
                "STATE_VERIFY_DRIFT",
                "project.name does not match the VERIFY Workload value",
                VERIFY_FILE,
            )
        try:
            aws_core_rows = parse_aws_core_evidence(
                verify_text,
                allow_legacy=allow_legacy_design_discovery,
            )
        except ValueError as exc:
            ctx.error("AWS_CORE_EVIDENCE_GENERATED_INVALID", str(exc), VERIFY_FILE)
    tasks = validate_tasks(
        ctx,
        state,
        prd_fields,
        envelope,
        requirements_contract,
        design_contract,
    )
    release_record = validate_release_decision_record(ctx)
    release_decision = release_record["release_state"]
    release_evidence_cutoff = release_record["active_evidence_cutoff"]
    aws_lifecycle_intent_record = validate_aws_lifecycle_intent_record(ctx)
    aws_lifecycle_intent = str(aws_lifecycle_intent_record["value"])
    validate_placeholders(ctx)

    gate_a = prd_fields.get("gate_a", "BLOCKED")
    gate_b = prd_fields.get("gate_b", "BLOCKED")
    prd_text = ctx.texts.get(PRD_FILE, "")
    gate_a_agent_ready = False
    gate_b_agent_ready = False
    try:
        gate_a_agent = table_after_heading(
            prd_text, "### Gate A — agent analysis record"
        )
        gate_b_agent = table_after_heading(
            prd_text, "## 27. Gate B agent review record"
        )
        gate_a_agent_ready = gate_a_agent.get("Agent recommendation") in {
            "READY_WITH_PROPOSED_ASSUMPTIONS",
            "READY_FOR_OWNER_APPROVAL",
        }
        gate_b_agent_ready = (
            gate_b_agent.get("Agent recommendation")
            == "READY_FOR_CONSTRUCTION_APPROVAL"
        )
    except ValueError:
        pass
    approved_tech_ids = {
        decision.decision_id for decision in design_contract.technology_decisions
    }
    req_materiality_raw = prd_fields.get("req_aws_materiality")
    req_materiality: Mapping[str, Any] = (
        req_materiality_raw
        if isinstance(req_materiality_raw, Mapping)
        else {
            "materiality": "OPTIONAL",
            "status": "UNASSESSED",
            "basis_ids": [],
            "discovery_ids": [],
            "unresolved_fact_ids": [],
        }
    )
    req_materiality_value = str(req_materiality.get("materiality", "OPTIONAL"))
    declared_req_discovery_ids = {
        str(item) for item in req_materiality.get("discovery_ids", [])
    }
    observed_req_discovery_ids = {
        discovery_id
        for row_phase, discovery_id, _capability in aws_core_rows
        if row_phase == "REQ-10"
    }
    req_aws_core_issues: list[str] = []
    if req_materiality_value == "REQUIRED" or declared_req_discovery_ids:
        req_aws_core_issues = aws_core_phase_evidence_issues(
            aws_core_rows,
            "REQ-10",
            expected_binding=prd_fields.get("requirements_revision"),
            expected_basis_ids={
                str(item) for item in req_materiality.get("basis_ids", [])
            },
        )
        if declared_req_discovery_ids != observed_req_discovery_ids:
            req_aws_core_issues.append(
                "REQ-10 AWS Core discovery IDs must exactly match the current "
                "Gate A materiality record"
            )
    req_aws_core_ready = not req_aws_core_issues
    if (
        gate_a_agent_ready
        or gate_a in {"PENDING_OWNER_APPROVAL", "APPROVED_FOR_DESIGN"}
    ) and req_materiality_value == "REQUIRED":
        if req_aws_core_issues:
            blocking_aws_core_phases.add("REQ-10")
        for issue in req_aws_core_issues:
            ctx.error(aws_core_evidence_diagnostic_code(issue), issue, VERIFY_FILE)
    design_aws_core_issues = aws_core_phase_evidence_issues(
        aws_core_rows,
        "DESIGN-10",
        expected_binding=prd_fields.get("design_revision"),
        expected_design_revision=prd_fields.get("design_revision"),
        approved_tech_ids=approved_tech_ids,
        allow_legacy_discovery=allow_legacy_design_discovery,
    )
    material_discovery_issues: list[str] = []
    if not allow_legacy_design_discovery:
        design_discovery_ids = {
            discovery_id
            for row_phase, discovery_id, _capability in aws_core_rows
            if row_phase == "DESIGN-10"
        }
        for evidence in design_contract.architecture.aws_evidence:
            if evidence.discovery_id not in design_discovery_ids:
                issue = (
                    f"{evidence.evidence_id} must cite a current DESIGN-10 "
                    f"AWS-DISC chain"
                )
                material_discovery_issues.append(issue)
                design_aws_core_issues.append(issue)
    design_aws_core_ready = not design_aws_core_issues
    design_evidence_enforced = gate_b_agent_ready or gate_b in {
        "PENDING_OWNER_APPROVAL",
        "APPROVED_FOR_CONSTRUCTION",
    }
    if design_evidence_enforced:
        if design_aws_core_issues:
            blocking_aws_core_phases.add("DESIGN-10")
        require_aws_core_phase_evidence(
            ctx,
            aws_core_rows,
            "DESIGN-10",
            expected_binding=prd_fields.get("design_revision"),
            expected_design_revision=prd_fields.get("design_revision"),
            approved_tech_ids=approved_tech_ids,
            allow_legacy_discovery=allow_legacy_design_discovery,
        )
        for issue in material_discovery_issues:
            ctx.error("AWS_CORE_EVIDENCE_REQUIRED", issue, PRD_FILE)
    lifecycle_state, next_prompt = derive_route(
        gate_a,
        gate_b,
        requirements_present,
        gate_b_agent_ready,
        tasks,
        envelope.get("Autonomous construction") == "ALLOWED",
        state.get("execution", {}).get("mode", "NONE"),
        release_decision,
    )
    if (
        gate_a == "BLOCKED"
        and not ctx.has_errors
        and any(value is None for value in selections.values())
    ):
        lifecycle_state, next_prompt = "INTAKE_REQUIRED", "INTAKE-10"
    artifact_binding = ""
    aws_10_issues = ["AWS-10 active artifact binding is unresolved"]
    if verify_text is not None:
        try:
            active_scope = table_after_heading(verify_text, "## Active evidence scope")
            artifact_binding = clean_cell(
                active_scope.get("Commit, tag, or image digest", "")
            )
        except ValueError:
            artifact_binding = ""
        if explicit_value(artifact_binding, allow_none=False):
            aws_10_issues = aws_core_phase_evidence_issues(
                aws_core_rows,
                "AWS-10",
                expected_binding=artifact_binding,
                expected_design_revision=prd_fields.get("design_revision"),
                approved_tech_ids={
                    decision.decision_id
                    for decision in design_contract.technology_decisions
                },
            )
    aws_guidance_ready = not aws_10_issues
    construction_authorization = (
        str(prd_fields.get("construction_authorization", "NONE"))
        if gate_b == "APPROVED_FOR_CONSTRUCTION"
        else "NONE"
    )
    read_authority = (
        _read_preflight_receipt_authority(
            verify_text or "",
            construction_authorization,
            str(state.get("project", {}).get("cost_posture", "")),
            envelope,
            artifact_binding,
        )
        if construction_authorization != "NONE"
        else None
    )
    preflight = derive_read_preflight_state(
        verify_text or "",
        read_authority,
        requirements_revision=str(prd_fields.get("requirements_revision", "")),
        design_revision=str(prd_fields.get("design_revision", "")),
        construction_authorization=construction_authorization,
        artifact_binding=artifact_binding,
    )
    deployment_sequence = derive_deployment_sequence_state(
        verify_text or "",
        read_authority,
        requirements_revision=str(prd_fields.get("requirements_revision", "")),
        design_revision=str(prd_fields.get("design_revision", "")),
        construction_authorization=construction_authorization,
        envelope=envelope,
        lane=selections.get("aws_lane"),
        artifact_binding=artifact_binding,
        release_evidence_cutoff=release_evidence_cutoff,
        release_state=release_decision,
        gate_b_authority_source=str(prd_fields.get("gate_b_authorization_source", "")),
        gate_b_authorized_at=str(prd_fields.get("gate_b_authorized_at", "")),
        cost_posture=str(state.get("project", {}).get("cost_posture", "")),
        restricted_closure=(
            gate_b != "APPROVED_FOR_CONSTRUCTION"
            or any(item.code == "GATE_B_AUTHORITY_EXPIRED" for item in ctx.diagnostics)
        ),
    )
    _preserve_expired_authority_for_deployment_closure(
        ctx, deployment_sequence, release_decision
    )
    teardown_sequence = derive_teardown_sequence_state(
        verify_text or "",
        read_authority,
        requirements_revision=str(prd_fields.get("requirements_revision", "")),
        design_revision=str(prd_fields.get("design_revision", "")),
        construction_authorization=construction_authorization,
        envelope=envelope,
        restricted_closure=(
            gate_b != "APPROVED_FOR_CONSTRUCTION"
            or any(item.code == "GATE_B_AUTHORITY_EXPIRED" for item in ctx.diagnostics)
        ),
        cost_posture=str(state.get("project", {}).get("cost_posture", "")),
        active_artifact=artifact_binding,
    )
    _preserve_expired_authority_for_teardown_closure(ctx, teardown_sequence)
    aws_sequence_conflict = aws_deployment_teardown_sequence_conflict(
        deployment_sequence, teardown_sequence
    )
    if aws_sequence_conflict:
        ctx.error(
            "AWS_DEPLOYMENT_TEARDOWN_CONFLICT",
            "Open deployment and teardown journal epochs cannot coexist; close one sequence before continuing",
            VERIFY_FILE,
        )
    aws_execution = derive_aws_execution_projection(
        req_materiality,
        release_decision=release_decision,
        guidance_ready=aws_guidance_ready,
        read_authority=read_authority,
        preflight=preflight,
        lane=selections.get("aws_lane"),
    )
    if deployment_sequence.get("status") not in {"NOT_ACTIVE", "CONSUMED"}:
        aws_execution = {
            **aws_execution,
            "active": False,
            "progress_state": "NOT_ACTIVE",
        }
    elif (
        deployment_sequence.get("status") == "CONSUMED"
        and release_decision == "READY_TO_DEPLOY"
        and deployment_sequence.get("current_mutation_authority_status") == "CONSUMED"
    ):
        aws_execution = {
            **aws_execution,
            "progress_state": "WAITING_AWS_MUTATION_AUTH",
        }
        if selections.get("aws_lane") == "fast-dev":
            ctx.error(
                "AWS_DEPLOYMENT_AUTHORITY_REPLAY",
                "A fast-dev retry requires a freshly approved Gate B construction authorization",
                PRD_FILE,
            )
    aws_execution_planning_ready = preflight.get("status") == "READY"
    aws_delivery_route = derive_aws_delivery_route(
        release_decision,
        aws_execution,
        deployment_sequence,
        selections.get("aws_lane"),
        release_evidence_cutoff,
    )
    residual_disposition = derive_aws_residual_disposition(
        aws_lifecycle_intent_record, teardown_sequence
    )
    if residual_disposition.get("status") == "INVALID":
        ctx.error(
            "AWS_RESIDUAL_DISPOSITION_INVALID",
            "; ".join(str(item) for item in residual_disposition.get("issues", [])),
            VERIFY_FILE,
        )
    teardown_recovery_route = derive_teardown_route(
        aws_lifecycle_intent, teardown_sequence, residual_disposition
    )
    teardown_status = clean_cell(teardown_sequence.get("status", ""))
    if aws_sequence_conflict:
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
    elif (
        not ctx.has_errors
        and teardown_status in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}
        and not teardown_sequence.get("issues")
        and teardown_recovery_route is not None
    ):
        lifecycle_state, next_prompt = teardown_recovery_route
    elif (
        teardown_status in {"ACTION_TERMINAL_REQUIRED", "POST_ACTION_REVIEW", "BLOCKED"}
        and not teardown_sequence.get("issues")
        and teardown_recovery_route is not None
    ):
        lifecycle_state, next_prompt = teardown_recovery_route
    elif (
        not ctx.has_errors
        and aws_lifecycle_intent_route_is_eligible(
            aws_lifecycle_intent,
            lifecycle_state,
            release_decision,
            tasks,
            deployment_sequence,
            teardown_sequence,
        )
        and teardown_recovery_route is not None
    ):
        lifecycle_state, next_prompt = teardown_recovery_route
    elif aws_delivery_route is not None and not ctx.has_errors:
        lifecycle_state, next_prompt = aws_delivery_route
    if next_prompt == "AWS-10" and not aws_guidance_ready:
        ctx.warning(
            "AWS_CORE_AWS10_EVIDENCE_REQUIRED",
            "AWS-10 must record a fresh linked search_documentation then "
            "retrieve_skill discovery chain bound to the current artifact before "
            "AWS execution planning: " + "; ".join(aws_10_issues),
            VERIFY_FILE,
        )
    if preflight.get("issues"):
        ctx.error(
            "AWS_PREFLIGHT_EVIDENCE_INVALID",
            "; ".join(str(item) for item in preflight["issues"]),
            VERIFY_FILE,
        )
    # A stale attempted basis never authorizes new mutation, but read-only
    # reconciliation still proceeds so the observed action can be closed.
    if deployment_sequence.get("issues"):
        ctx.error(
            "AWS_DEPLOYMENT_EVIDENCE_INVALID",
            "; ".join(str(item) for item in deployment_sequence["issues"]),
            VERIFY_FILE,
        )
    if teardown_sequence.get("issues"):
        ctx.error(
            "AWS_TEARDOWN_EVIDENCE_INVALID",
            "; ".join(str(item) for item in teardown_sequence["issues"]),
            VERIFY_FILE,
        )
    aws_core_usage = {
        "REQ-10": derive_aws_core_observed_usage(
            aws_core_rows,
            "REQ-10",
            issues=req_aws_core_issues,
        ),
        "DESIGN-10": derive_aws_core_observed_usage(
            aws_core_rows,
            "DESIGN-10",
            issues=design_aws_core_issues,
        ),
        "AWS-10": derive_aws_core_observed_usage(
            aws_core_rows,
            "AWS-10",
            issues=aws_10_issues,
        ),
    }
    specialized_teardown_block = _preserve_specialized_teardown_block(
        ctx, lifecycle_state
    )
    if ctx.has_errors and not specialized_teardown_block:
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
    owner_stage_hint = _owner_stage_for_aws_core_phases(
        blocking_aws_core_phases,
        _owner_stage_from_gates(gate_a, gate_b),
    )
    if any(
        item.code == "APPLICATION_SOURCE_DISPOSITION_CONFLICT"
        for item in ctx.diagnostics
    ):
        owner_stage_hint = "DEFINE"
    return build_report(
        ctx,
        lifecycle_state,
        next_prompt,
        prd_fields,
        tasks,
        manifest=manifest,
        state=state,
        release_decision=release_decision,
        envelope=envelope,
        aws_execution_planning_ready=aws_execution_planning_ready,
        design_aws_core_ready=design_aws_core_ready,
        design_contract=design_contract,
        adr_rationale=adr_rationale,
        intake_contract=intake_contract,
        coverage_contract=coverage_contract,
        aws_execution=aws_execution,
        requirements_contract=requirements_contract,
        aws_core_usage=aws_core_usage,
        owner_stage_hint=owner_stage_hint,
        active_artifact=artifact_binding,
        deployment_sequence=deployment_sequence,
        teardown_sequence=teardown_sequence,
        req_aws_core_materiality=req_materiality_value,
        req_aws_core_ready=req_aws_core_ready,
        aws_lifecycle_intent_record=aws_lifecycle_intent_record,
        release_evidence_cutoff=release_evidence_cutoff,
    )


def inspect_git_baseline(root: Path) -> str:
    """Return the current commit or PENDING without changing Git state."""

    try:
        result = subprocess.run(
            [
                resolve_trusted_git(root),
                "-C",
                str(root),
                "rev-parse",
                "--verify",
                "HEAD",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "PENDING"
    if result.returncode != 0:
        return "PENDING"
    commit = result.stdout.strip()
    return commit if re.fullmatch(r"[0-9a-fA-F]{40,64}", commit) else "PENDING"


DEFINE_AGENT_DIAGNOSTICS = frozenset(
    {
        "ADAPTIVE_COVERAGE_INVALID",
        "PROJECT_CONTRACT_MIGRATION_REQUIRED",
        "ACTOR_CONTRACT_INVALID",
        "JOURNEY_CONTRACT_INVALID",
        "RICH_USE_CASE_REQUIRED",
        "RICH_USE_CASE_INVALID",
        "BUSINESS_RULE_INVALID",
        "REQUIREMENT_COVERAGE_INVALID",
        "INTAKE_CARD_REQUIRED",
        "INTAKE_CARD_MIGRATION_REQUIRED",
        "INTAKE_CONTRACT_MIGRATION_REQUIRED",
        "INTAKE_SELECTION_PROVENANCE_INVALID",
        "INTAKE_FOUNDATION_PROVENANCE_INVALID",
        "INTAKE_RESPONSE_REGISTER_INVALID",
        "OWNER_BRIEF_SOURCE_STALE",
        "OWNER_BRIEF_COVERAGE_INCOMPLETE",
        "OWNER_BRIEF_SOURCE_MISMATCH",
        "OWNER_BRIEF_OUTPUT_BUDGET_UNRESOLVED",
        "GATE_A_LIFECYCLE_TRANSITION",
        "GATE_A_READINESS_CARD",
        "GATE_A_RECOMMENDATION",
        "REQ_AWS_MATERIALITY_INVALID",
        "AWS_CORE_REQ10_EVIDENCE_REQUIRED",
        "AWS_CORE_DISCOVERY_REQUIRED",
        "AWS_CORE_EVIDENCE_STALE",
        "AWS_CORE_EVIDENCE_GENERATED_INVALID",
    }
)
DESIGN_AGENT_DIAGNOSTICS = frozenset(
    {
        "ADR_RATIONALE_DUPLICATE",
        "ADR_RATIONALE_MALFORMED",
        "ADR_RATIONALE_MISMATCH",
        "ADR_RATIONALE_MISSING",
        "ADR_RATIONALE_STALE",
        "ADR_RATIONALE_SUPERSESSION_INVALID",
        "ADR_RATIONALE_UNSAFE",
        "APPLICATION_SOURCE_DISPOSITION_INVALID",
        "APPLICATION_SOURCE_DISPOSITION_MISSING",
        "APPLICATION_SOURCE_PARALLEL_ROOT",
        "AWS_LANE_BOUNDARY",
        "DESIGN_CONTRACT_INVALID",
        "GATE_B_DESIGN_CONTRACT_HASH",
        "GATE_B_ENVELOPE",
        "GATE_B_ENVELOPE_HASH",
        "GATE_B_GAP",
        "GATE_B_LIFECYCLE_TRANSITION",
        "GATE_B_PROJECT_DRIFT",
        "GATE_B_READINESS_CARD",
        "GATE_B_RECOMMENDATION",
        "GATE_B_REVISION_MISMATCH",
        "OWNER_BRIEF_SOURCE_STALE",
        "OWNER_BRIEF_COVERAGE_INCOMPLETE",
        "OWNER_BRIEF_SOURCE_MISMATCH",
        "OWNER_BRIEF_OUTPUT_BUDGET_UNRESOLVED",
        "AWS_CORE_EVIDENCE_REQUIRED",
        "AWS_CORE_DISCOVERY_REQUIRED",
        "AWS_CORE_EVIDENCE_STALE",
        "AWS_CORE_EVIDENCE_GENERATED_INVALID",
    }
)
DELIVER_AGENT_DIAGNOSTICS = frozenset(
    {
        "ACTIVE_TASK_CONFLICT",
        "AUTONOMY_OUTSIDE_AUTH",
        "STATE_TASK_DRIFT",
        "TASK_ATTEMPT_BOUNDARY",
        "TASK_AWS_BOUNDARY",
        "TASK_AWS_MODE_REPLAN_REQUIRED",
        "TASK_BASELINE_DRIFT",
        "TASK_COMMAND_BOUNDARY",
        "TASK_EXCLUDED_WRITE",
        "TASK_EXTERNAL_STATE_BOUNDARY",
        "TASK_GITHUB_BOUNDARY",
        "TASK_GRAPH_INVALID",
        "TASK_ID_OUTSIDE_AUTH",
        "TASK_LIMIT_EXCEEDED",
        "TASK_OUTSIDE_TASK_BOUNDARY",
        "TASK_OUTSIDE_WRITE_BOUNDARY",
        "TASK_PLAN_STATE",
        "TASK_PROPERTY_COVERAGE",
        "TASK_REQUIREMENT_TRACE_INVALID",
        "TASK_REQUIREMENT_COVERAGE",
        "TASK_REQUIREMENT_COVERAGE_EVIDENCE_INVALID",
        "TASK_SNAPSHOT",
        "WORKER_LIMIT_EXCEEDED",
    }
)
TASK_REPLAN_DIAGNOSTICS = frozenset(
    {
        "TASK_AWS_MODE_REPLAN_REQUIRED",
        "TASK_REQUIREMENT_TRACE_INVALID",
        "TASK_REQUIREMENT_COVERAGE",
        "TASK_REQUIREMENT_COVERAGE_EVIDENCE_INVALID",
    }
)
OWNER_DECISION_DIAGNOSTICS = frozenset(
    {
        "APPLICATION_SOURCE_DISPOSITION_CONFLICT",
        "BROWNFIELD_PRD_BASELINE",
        "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
        "BROWNFIELD_PRD_PRESERVATION",
        "BROWNFIELD_STATE",
        "GATE_A_ASSUMPTIONS",
        "GATE_A_BLOCKER",
        "GATE_A_COST_POSTURE",
        "INTAKE_FOUNDATION_REQUIRED",
        "PLACEHOLDER_UNRESOLVED",
        "PROJECT_COST_POSTURE",
        "PROJECT_IDENTITY",
        "PROJECT_RISK_PROFILE",
        "PROJECT_SELECTION_REQUIRED",
        "REQUIREMENT_METHOD_MIGRATION_REQUIRED",
    }
)
OWNER_SETUP_DIAGNOSTICS = frozenset(
    {
        "AWS_CORE_CAPABILITY_UNAVAILABLE",
    }
)
OWNER_AUTHORIZATION_DIAGNOSTICS = frozenset(
    {
        "GATE_A_COST_AUTHORIZATION",
        "GATE_A_HUMAN_APPROVER",
        "GATE_A_OWNER_RECORD",
        "GATE_A_RECEIPT_MISMATCH",
        "GATE_B_HUMAN_APPROVER",
        "GATE_B_OWNER_RECORD",
        "GATE_B_RECEIPT_MISMATCH",
        "GATE_B_WITHOUT_GATE_A",
        "GATE_B_AUTHORITY_EXPIRED",
    }
)
UNCONFIGURED_SETUP_DIAGNOSTICS = frozenset(
    {
        "PLACEHOLDER_UNRESOLVED",
        "PROJECT_COST_POSTURE",
        "PROJECT_IDENTITY",
        "STATE_SETUP",
    }
)


AWS_CORE_GENERATED_DIAGNOSTICS = frozenset(
    {
        "AWS_CORE_REQ10_EVIDENCE_REQUIRED",
        "AWS_CORE_EVIDENCE_REQUIRED",
        "AWS_CORE_DISCOVERY_REQUIRED",
        "AWS_CORE_EVIDENCE_STALE",
        "AWS_CORE_EVIDENCE_GENERATED_INVALID",
    }
)


def _owner_stage_from_gates(gate_a: str, gate_b: str) -> str:
    if gate_a != "APPROVED_FOR_DESIGN":
        return "DEFINE"
    if gate_b != "APPROVED_FOR_CONSTRUCTION":
        return "DESIGN"
    return "DELIVER"


def _owner_stage_for_aws_core_phases(phases: set[str], fallback: str) -> str:
    """Return the earliest owner stage affected by enforced AWS evidence."""

    if "REQ-10" in phases:
        return "DEFINE"
    if "DESIGN-10" in phases:
        return "DESIGN"
    if "AWS-10" in phases:
        return "DELIVER"
    return fallback


def _agent_correction_is_safe(
    diagnostic: Diagnostic,
    owner_stage: str,
    gate_b: str,
    envelope: Mapping[str, str],
    tasks: TaskSummary,
) -> bool:
    """Return whether one generated defect is repairable inside current boundaries."""

    relative = validate_relative_path(diagnostic.path)
    if relative is None:
        return False
    if diagnostic.code == "DOCUMENT_SUMMARY_STALE":
        return relative in DOCUMENT_SUMMARY_FILES
    if diagnostic.code.startswith("ADR_RATIONALE_"):
        return bool(
            re.fullmatch(r"docs/adr/\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md", relative)
        )

    if owner_stage == "DEFINE":
        if diagnostic.code not in DEFINE_AGENT_DIAGNOSTICS:
            return False
        if diagnostic.code in AWS_CORE_GENERATED_DIAGNOSTICS:
            return relative in {PRD_FILE, VERIFY_FILE}
        return relative == PRD_FILE
    if owner_stage == "DESIGN":
        if diagnostic.code not in DESIGN_AGENT_DIAGNOSTICS:
            return False
        if diagnostic.code in AWS_CORE_GENERATED_DIAGNOSTICS:
            return relative == VERIFY_FILE or (
                gate_b != "APPROVED_FOR_CONSTRUCTION" and relative == PRD_FILE
            )
        if gate_b == "APPROVED_FOR_CONSTRUCTION":
            return False
        return relative == PRD_FILE
    if diagnostic.code not in DELIVER_AGENT_DIAGNOSTICS:
        return False
    if gate_b != "APPROVED_FOR_CONSTRUCTION":
        return False
    try:
        allowed = parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
        )
        excluded = parse_envelope_paths(
            envelope.get("Excluded or owner-only write set", ""),
            "Excluded or owner-only write set",
            allow_none=True,
        )
        protected = parse_envelope_paths(
            envelope.get("Protected dirty paths", ""),
            "Protected dirty paths",
            allow_none=True,
        )
    except ValueError:
        return False
    if any(path_boundaries_overlap(relative, item) for item in excluded + protected):
        return False
    if relative in COORDINATOR_LEDGER_PATHS:
        return True
    if len(tasks.active) != 1:
        return False
    active_task = tasks.active[0]
    if tasks.attempts_used.get(active_task, 0) >= tasks.attempt_budgets.get(
        active_task, 0
    ):
        return False
    return any(path_boundary_contains(item, relative) for item in allowed) and any(
        path_boundary_contains(item, relative)
        for item in tasks.write_sets.get(active_task, [])
    )


def _owner_authorization_action(items: list[dict[str, Any]]) -> str:
    codes = {str(item.get("diagnostic_code", "")) for item in items}
    if any(code.startswith("GATE_A_") for code in codes):
        return "APPROVE_GATE_A"
    if any(code.startswith("GATE_B_") for code in codes):
        return "APPROVE_GATE_B"
    return "AUTHORIZE_AWS_OPERATION"


def derive_remediation(
    ctx: Context,
    *,
    classification: str,
    gate_a: str,
    gate_b: str,
    envelope: Mapping[str, str],
    tasks: TaskSummary,
    requirements_revision: str | None = None,
    design_revision: str | None = None,
    owner_stage_hint: str | None = None,
) -> dict[str, Any]:
    """Classify each error, then derive one deterministic next action."""

    owner_stage = (
        owner_stage_hint
        if owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}
        else _owner_stage_from_gates(gate_a, gate_b)
    )
    items: list[dict[str, Any]] = []
    for index, diagnostic in enumerate(ctx.diagnostics, start=1):
        if diagnostic.severity != "ERROR":
            continue
        responsible_party = "HUMAN_REVIEWER"
        category = "MANUAL_SAFETY_REVIEW"
        automatic = False
        if (
            classification == "UNCONFIGURED_TEMPLATE"
            and diagnostic.code in UNCONFIGURED_SETUP_DIAGNOSTICS
        ):
            responsible_party = "OWNER"
            category = "OWNER_SETUP"
        elif diagnostic.code in OWNER_SETUP_DIAGNOSTICS:
            responsible_party = "OWNER"
            category = "OWNER_SETUP"
        elif diagnostic.code in OWNER_DECISION_DIAGNOSTICS:
            responsible_party = "OWNER"
            category = "OWNER_DECISION"
        elif diagnostic.code in OWNER_AUTHORIZATION_DIAGNOSTICS:
            responsible_party = "OWNER"
            category = "OWNER_AUTHORIZATION"
        elif diagnostic.code in TASK_REPLAN_DIAGNOSTICS and _agent_correction_is_safe(
            diagnostic, owner_stage, gate_b, envelope, tasks
        ):
            responsible_party = "CODEX"
            category = "AGENT_REPLAN"
            automatic = True
        elif _agent_correction_is_safe(
            diagnostic, owner_stage, gate_b, envelope, tasks
        ):
            responsible_party = "CODEX"
            category = "AGENT_CORRECTION"
            automatic = True
        items.append(
            {
                "diagnostic_id": f"DGN-{index:04d}",
                "diagnostic_code": diagnostic.code,
                "path": diagnostic.path,
                "responsible_party": responsible_party,
                "category": category,
                "automatic_correction_allowed": automatic,
            }
        )

    codex_payload: list[dict[str, str]] = []
    for item in items:
        if item["category"] not in {"AGENT_CORRECTION", "AGENT_REPLAN"}:
            continue
        diagnostic_index = int(str(item["diagnostic_id"]).rsplit("-", 1)[1]) - 1
        diagnostic = ctx.diagnostics[diagnostic_index]
        codex_payload.append(
            {
                "code": diagnostic.code,
                "path": diagnostic.path or "NONE",
                "cause": re.sub(r"\s+", " ", diagnostic.message).strip(),
                "requirements_revision": requirements_revision or "NONE",
                "design_revision": design_revision or "NONE",
            }
        )
    remediation_fingerprint = "NONE"
    if codex_payload:
        canonical = json.dumps(
            codex_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        remediation_fingerprint = "sha256:" + hashlib.sha256(canonical).hexdigest()
    repeated_fingerprint = (
        remediation_fingerprint != "NONE"
        and ctx.prior_remediation_fingerprint == remediation_fingerprint
    )
    if repeated_fingerprint:
        for item in items:
            if item["category"] in {"AGENT_CORRECTION", "AGENT_REPLAN"}:
                item["responsible_party"] = "HUMAN_REVIEWER"
                item["category"] = "MANUAL_SAFETY_REVIEW"
                item["automatic_correction_allowed"] = False

    manual = [item for item in items if item["category"] == "MANUAL_SAFETY_REVIEW"]
    codex = [item for item in items if item["category"] == "AGENT_CORRECTION"]
    replans = [item for item in items if item["category"] == "AGENT_REPLAN"]
    owner_decisions = [item for item in items if item["category"] == "OWNER_DECISION"]
    owner_setup = [item for item in items if item["category"] == "OWNER_SETUP"]
    owner_authorization = [
        item for item in items if item["category"] == "OWNER_AUTHORIZATION"
    ]
    if manual:
        next_action = {
            "responsible_party": "HUMAN_REVIEWER",
            "action_kind": "REVIEW_SAFETY_BLOCKER",
            "automatic_continuation_allowed": False,
        }
    elif replans:
        next_action = {
            "responsible_party": "CODEX",
            "action_kind": "REPLAN_TASKS",
            "automatic_continuation_allowed": True,
            "preserve_done_evidence": True,
        }
    elif codex:
        next_action = {
            "responsible_party": "CODEX",
            "action_kind": "CORRECT_AND_REVALIDATE",
            "automatic_continuation_allowed": True,
        }
    elif owner_decisions:
        next_action = {
            "responsible_party": "OWNER",
            "action_kind": "ANSWER_OPEN_DECISIONS",
            "automatic_continuation_allowed": False,
        }
    elif owner_setup:
        next_action = {
            "responsible_party": "OWNER",
            "action_kind": (
                "COMPLETE_PREREQUISITE_CHECKLIST"
                if classification == "UNCONFIGURED_TEMPLATE"
                else "ENABLE_AWS_CORE"
            ),
            "automatic_continuation_allowed": False,
        }
    elif owner_authorization:
        next_action = {
            "responsible_party": "OWNER",
            "action_kind": _owner_authorization_action(owner_authorization),
            "automatic_continuation_allowed": False,
        }
    else:
        next_action = {
            "responsible_party": "CODEX",
            "action_kind": "CONTINUE_CURRENT_ROUTE",
            "automatic_continuation_allowed": True,
        }
    return {
        "items": items,
        "next_action": next_action,
        "fingerprint": remediation_fingerprint,
        "retry_state": "REPEATED" if repeated_fingerprint else "FIRST_OR_NONE",
    }


def derive_interaction(
    lifecycle_state: str,
    next_prompt: str,
    *,
    has_errors: bool,
    diagnostic_codes: list[str],
    design_aws_core_ready: bool,
    aws_execution_planning_ready: bool,
    remediation: Mapping[str, Any] | None = None,
    owner_stage_hint: str | None = None,
    aws_progress_state: str | None = None,
    aws_mutation_authority_ready: bool = False,
    aws_lane: str | None = None,
    aws_read_authority_required: bool = False,
    req_aws_core_materiality: str = "OPTIONAL",
    req_aws_core_ready: bool = True,
) -> dict[str, Any]:
    """Derive stable owner interaction metadata without conversational prose."""

    aws_core_capability_unavailable = (
        "AWS_CORE_CAPABILITY_UNAVAILABLE" in diagnostic_codes
    )

    if lifecycle_state in {
        "INTAKE_REQUIRED",
        "REQUIREMENTS_ANALYSIS",
        "REQUIREMENTS_STALE",
        "WAITING_GATE_A",
    }:
        owner_stage = "DEFINE"
    elif lifecycle_state in {"DESIGN_REQUIRED", "DESIGN_STALE", "WAITING_GATE_B"}:
        owner_stage = "DESIGN"
    else:
        owner_stage = "DELIVER"
    if owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}:
        owner_stage = owner_stage_hint

    route_reason_code = lifecycle_state
    if lifecycle_state in {
        "AWS_RESIDUAL_REVIEW_BLOCKED",
        "RELEASE_REVIEW_BLOCKED",
    }:
        response_mode = "BLOCKER"
        state = "BLOCKED"
        action_kind = "REVIEW_SAFETY_BLOCKER"
        automatic = False
        formal_receipt = False
    elif has_errors or lifecycle_state == "BLOCKED":
        next_action = remediation.get("next_action") if remediation else None
        remediation_action = (
            str(next_action.get("action_kind", ""))
            if isinstance(next_action, Mapping)
            else ""
        )
        if remediation_action in {"CORRECT_AND_REVALIDATE", "REPLAN_TASKS"}:
            response_mode = "OWNER_UPDATE"
            state = "WORKING"
            action_kind = "NONE_CONTINUE_AUTOMATICALLY"
            automatic = True
            if remediation_action == "REPLAN_TASKS":
                route_reason_code = "TASK_REPLAN_REQUIRED"
        elif remediation_action == "ANSWER_OPEN_DECISIONS":
            response_mode = "OWNER_UPDATE"
            state = "NEEDS_INPUT"
            action_kind = remediation_action
            automatic = False
            route_reason_code = "INTAKE_REQUIRED"
        elif remediation_action in {
            "APPROVE_GATE_A",
            "APPROVE_GATE_B",
            "AUTHORIZE_AWS_OPERATION",
            "COMPLETE_PREREQUISITE_CHECKLIST",
            "ENABLE_AWS_CORE",
            "REVIEW_SAFETY_BLOCKER",
        }:
            response_mode = "BLOCKER"
            state = "BLOCKED"
            action_kind = remediation_action
            automatic = False
        else:
            response_mode = "BLOCKER"
            state = "BLOCKED"
            action_kind = (
                "ENABLE_AWS_CORE"
                if aws_core_capability_unavailable
                else "FIX_VALIDATION_FAILURE"
            )
            automatic = False
        formal_receipt = False
    elif lifecycle_state in {
        "AWS_DEPLOYMENT_ACTION_TERMINAL",
        "AWS_TEARDOWN_ACTION_TERMINAL",
    }:
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif lifecycle_state in {
        "AWS_DEPLOYMENT_RECONCILIATION",
        "AWS_RESIDUAL_REVIEW",
    }:
        response_mode = "AWS_RECEIPT" if aws_read_authority_required else "OWNER_UPDATE"
        state = "AWAITING_APPROVAL" if aws_read_authority_required else "WORKING"
        action_kind = (
            "AUTHORIZE_AWS_READ_PREFLIGHT"
            if aws_read_authority_required
            else "NONE_CONTINUE_AUTOMATICALLY"
        )
        automatic = not aws_read_authority_required
        formal_receipt = aws_read_authority_required
    elif lifecycle_state == "WAITING_AWS_TEARDOWN_AUTH":
        response_mode = (
            "OWNER_UPDATE" if aws_mutation_authority_ready else "AWS_RECEIPT"
        )
        state = "WORKING" if aws_mutation_authority_ready else "AWAITING_APPROVAL"
        action_kind = (
            "NONE_CONTINUE_AUTOMATICALLY"
            if aws_mutation_authority_ready
            else "AUTHORIZE_AWS_TEARDOWN"
        )
        automatic = aws_mutation_authority_ready
        formal_receipt = not aws_mutation_authority_ready
    elif lifecycle_state in {
        "AWS_RESIDUAL_REVIEW_COMPLETE",
        "AWS_RESIDUALS_RETAINED",
        "AWS_TEARDOWN_COMPLETE",
    }:
        response_mode = "OWNER_UPDATE"
        state = "COMPLETE"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = False
        formal_receipt = False
    elif lifecycle_state == "AWS_RESIDUALS_REMAIN":
        response_mode = "BLOCKER"
        state = "NEEDS_INPUT"
        action_kind = "CHOOSE_AWS_RESIDUAL_DISPOSITION"
        automatic = False
        formal_receipt = False
    elif aws_progress_state == "AWS_GUIDANCE_REQUIRED":
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif aws_progress_state == "AWS_READ_SCOPE_REQUIRED":
        response_mode = "AWS_RECEIPT"
        state = "AWAITING_APPROVAL"
        action_kind = "AUTHORIZE_AWS_READ_PREFLIGHT"
        automatic = False
        formal_receipt = True
    elif aws_progress_state == "AWS_PREFLIGHT_RUNNING":
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif aws_progress_state == "AWS_PREFLIGHT_READY":
        response_mode = "OWNER_UPDATE"
        state = "WORKING" if aws_lane == "fast-dev" else "COMPLETE"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = aws_lane == "fast-dev"
        formal_receipt = False
    elif aws_progress_state == "WAITING_AWS_MUTATION_AUTH":
        response_mode = (
            "OWNER_UPDATE" if aws_mutation_authority_ready else "AWS_RECEIPT"
        )
        state = "WORKING" if aws_mutation_authority_ready else "AWAITING_APPROVAL"
        action_kind = (
            "NONE_CONTINUE_AUTOMATICALLY"
            if aws_mutation_authority_ready
            else "AUTHORIZE_AWS_OPERATION"
        )
        automatic = aws_mutation_authority_ready
        formal_receipt = not aws_mutation_authority_ready
    elif lifecycle_state == "WAITING_GATE_A":
        response_mode = "GATE_A"
        state = "AWAITING_APPROVAL"
        action_kind = "APPROVE_GATE_A"
        automatic = False
        formal_receipt = True
    elif lifecycle_state == "WAITING_GATE_B":
        response_mode = "GATE_B"
        state = "AWAITING_APPROVAL"
        action_kind = "APPROVE_GATE_B"
        automatic = False
        formal_receipt = True
    elif next_prompt == "AWS-50":
        response_mode = (
            "OWNER_UPDATE" if aws_mutation_authority_ready else "AWS_RECEIPT"
        )
        state = "WORKING" if aws_mutation_authority_ready else "AWAITING_APPROVAL"
        action_kind = (
            "NONE_CONTINUE_AUTOMATICALLY"
            if aws_mutation_authority_ready
            else "AUTHORIZE_AWS_TEARDOWN"
        )
        automatic = aws_mutation_authority_ready
        formal_receipt = not aws_mutation_authority_ready
    elif next_prompt in {"AWS-30", "AWS-40"} and aws_read_authority_required:
        response_mode = "AWS_RECEIPT"
        state = "AWAITING_APPROVAL"
        action_kind = "AUTHORIZE_AWS_READ_PREFLIGHT"
        automatic = False
        formal_receipt = True
    elif next_prompt in {"AWS-30", "AWS-40"}:
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif next_prompt.startswith("AWS-") and aws_execution_planning_ready:
        response_mode = "AWS_RECEIPT"
        state = "AWAITING_APPROVAL"
        action_kind = "AUTHORIZE_AWS_OPERATION"
        automatic = False
        formal_receipt = True
    elif next_prompt.startswith("AWS-"):
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif lifecycle_state in {"INTAKE_REQUIRED", "REQUIREMENTS_STALE"}:
        response_mode = "OWNER_UPDATE"
        state = "NEEDS_INPUT"
        action_kind = "ANSWER_OPEN_DECISIONS"
        automatic = False
        formal_receipt = False
    elif lifecycle_state == "RELEASE_VERIFIED":
        response_mode = "OWNER_UPDATE"
        state = "COMPLETE"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = False
        formal_receipt = False
    else:
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False

    req_core_material = bool(
        owner_stage == "DEFINE"
        and next_prompt in {"REQ-10", "INTAKE-20"}
        and req_aws_core_materiality == "REQUIRED"
    )
    material = (
        req_core_material
        or owner_stage == "DESIGN"
        or next_prompt.startswith("AWS-")
        or aws_progress_state is not None
    )
    if not material:
        evidence_status = "NOT_REQUIRED"
    elif req_core_material:
        evidence_status = (
            "CURRENT"
            if req_aws_core_ready
            else ("BLOCKED" if has_errors else "REQUIRED")
        )
    elif aws_progress_state is not None:
        evidence_status = (
            "REQUIRED" if aws_progress_state == "AWS_GUIDANCE_REQUIRED" else "CURRENT"
        )
    elif next_prompt.startswith("AWS-"):
        evidence_status = (
            "CURRENT"
            if aws_execution_planning_ready
            else ("BLOCKED" if has_errors else "REQUIRED")
        )
    else:
        evidence_status = (
            "CURRENT"
            if design_aws_core_ready
            else ("BLOCKED" if has_errors else "REQUIRED")
        )

    blocking_ids: list[str] = []
    if state == "BLOCKED" and remediation:
        remediation_items = remediation.get("items")
        if isinstance(remediation_items, list):
            blocking_ids = [
                str(item["diagnostic_id"])
                for item in remediation_items
                if isinstance(item, Mapping) and "diagnostic_id" in item
            ]
    if state == "BLOCKED" and not blocking_ids:
        blocking_ids = sorted(set(diagnostic_codes))

    return {
        "owner_stage": owner_stage,
        "response_mode": response_mode,
        "state": state,
        "route_reason_code": route_reason_code,
        "owner_action_required": action_kind != "NONE_CONTINUE_AUTOMATICALLY",
        "owner_action_kind": action_kind,
        "blocking_ids": blocking_ids,
        "automatic_continuation_allowed": automatic,
        "turn_boundary_required": (
            action_kind != "NONE_CONTINUE_AUTOMATICALLY" and not automatic
        ),
        "formal_receipt_required": formal_receipt,
        "aws_core": {
            "materiality": "MATERIAL" if material else "NOT_MATERIAL",
            "evidence_status": evidence_status,
        },
    }


def derive_unconfigured_template_interaction(
    diagnostic_codes: list[str],
) -> dict[str, Any]:
    """Return honest setup-first metadata for an untouched adopter template."""

    return {
        "owner_stage": "DEFINE",
        "response_mode": "BLOCKER",
        "state": "BLOCKED",
        "route_reason_code": "UNCONFIGURED_TEMPLATE",
        "owner_action_required": True,
        "owner_action_kind": "COMPLETE_PREREQUISITE_CHECKLIST",
        "blocking_ids": sorted(set(diagnostic_codes)),
        "automatic_continuation_allowed": False,
        "turn_boundary_required": True,
        "formal_receipt_required": False,
        "aws_core": {
            "materiality": "NOT_MATERIAL",
            "evidence_status": "NOT_REQUIRED",
        },
    }


CONTEXT_MAXIMUM_INITIAL_BYTES = 12_000


def _context_selector_span(request: SliceRequest, text: str) -> SourceSpan:
    """Resolve one selector through the doctor's canonical Markdown helpers."""

    if request.selector_kind == "WHOLE_FILE":
        if not text:
            raise ValueError("whole-file source is empty")
        return SourceSpan(0, len(text))
    if request.selector_kind == "HEADING":
        return _heading_title_span(text, request.selector)
    if request.selector_kind == "TASK_ID":
        matches = [
            task
            for task in inspect_task_blocks(text)
            if task.task_id == request.selector
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one task {request.selector!r}; found {len(matches)}"
            )
        start = text.find(matches[0].block)
        if start < 0:
            raise ValueError(f"task {request.selector!r} has no canonical source range")
        return SourceSpan(start, start + len(matches[0].block))
    if request.selector_kind == "RECORD_ID":
        structural_lines = without_fenced_code(text).splitlines(keepends=True)
        source_lines = text.splitlines(keepends=True)
        token = re.compile(rf"(?<![A-Z0-9-]){re.escape(request.selector)}(?![A-Z0-9-])")
        matches: list[SourceSpan] = []
        offset = 0
        for source_line, structural_line in zip(source_lines, structural_lines):
            cells = (
                split_markdown_table_row(source_line.rstrip("\r\n"))
                if structural_line.strip().startswith("|")
                else None
            )
            if cells is not None and any(
                token.search(clean_cell(cell)) for cell in cells
            ):
                matches.append(SourceSpan(offset, offset + len(source_line)))
            offset += len(source_line)
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one table record {request.selector!r}; found {len(matches)}"
            )
        return matches[0]
    raise ValueError(f"unsupported selector kind {request.selector_kind!r}")


def _context_request(
    value: str,
    active_ids: list[str],
    *,
    initial: bool,
) -> SliceRequest:
    path, marker, selector = value.partition("#")
    if not marker:
        selector_kind = "WHOLE_FILE"
        selector = path
        priority = 0
        reason = "Current phase procedure"
    elif TASK_ID.fullmatch(selector):
        selector_kind = "TASK_ID"
        priority = 2
        reason = "Active task and dependencies"
    else:
        selector_kind = "HEADING"
        if path == TASKS_FILE:
            priority = 2
            reason = "Active task and dependencies"
        elif path == PRD_FILE:
            priority = 3
            reason = "Controlling PRD record"
        elif path.startswith(".agents/skills/fastlane/references/"):
            priority = 0
            reason = "Current phase procedure"
        else:
            priority = 4
            reason = "Consequential evidence or authority"
    required_selectors = {
        "Document status",
        "Active execution snapshot",
        "AWS Core evidence",
        "Read-only AWS preflight evidence",
        "Read-only AWS preflight",
        "Action authorization provenance",
        "AWS deployment action and reconciliation evidence",
        "Conditional AWS action receipts",
        "Teardown reconciliation evidence",
        "13. Teardown and decommissioning",
        "14. Residual-resource and billing verification",
    }
    # A phase procedure is complete guidance, not one atomic lifecycle record.
    # It may move on demand as a whole when current required state needs the
    # initial budget; the coordinator loads it later only when the current
    # decision requires it. Task blocks and controlling state records remain
    # atomic and required.
    required = initial and (
        selector_kind == "TASK_ID"
        or selector in required_selectors
        or (
            selector_kind == "HEADING"
            and path.startswith(".agents/skills/fastlane/references/")
        )
    )
    return SliceRequest(
        path=path,
        selector_kind=selector_kind,
        selector=selector,
        priority=priority if initial else 5,
        reason=reason if initial else "On-demand canonical source",
        required=required,
        active_ids=tuple(active_ids),
    )


def _resolve_context_metadata(
    source_slices: list[str],
    on_demand_slices: list[str],
    active_ids: list[str],
    source_texts: Mapping[str, str],
) -> tuple[dict[str, object], list[dict[str, str]]]:
    initial_requests = [
        _context_request(value, active_ids, initial=True) for value in source_slices
    ]
    on_demand_requests = [
        _context_request(value, active_ids, initial=False) for value in on_demand_slices
    ]
    return resolve_context_packet(
        initial_requests,
        on_demand_requests,
        source_texts,
        _context_selector_span,
        maximum_initial_source_bytes=CONTEXT_MAXIMUM_INITIAL_BYTES,
    )


def derive_context_plan(
    interaction: Mapping[str, Any],
    tasks: TaskSummary,
    coverage: CoverageContract,
    *,
    next_prompt: str = "",
    restricted_deployment_closure: bool = False,
    restricted_teardown_closure: bool = False,
    source_texts: Mapping[str, str] | None = None,
    adr_rationale: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Select an ephemeral, route-bounded canonical context packet."""

    stage = interaction.get("owner_stage")
    reason = interaction.get("route_reason_code")
    deployment_closure_context = restricted_deployment_closure and next_prompt in {
        "AWS-20",
        "AWS-30",
        "RELEASE-10",
    }
    teardown_closure_context = restricted_teardown_closure and next_prompt in {
        "AWS-40",
        "AWS-50",
    }
    closure_context = deployment_closure_context or teardown_closure_context
    if teardown_closure_context:
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#Teardown and residuals",
            f"{VERIFY_FILE}#Teardown reconciliation evidence",
        ]
        on_demand_slices = [
            f"{TASKS_FILE}#Active execution snapshot",
            f"{PRD_FILE}#Construction envelope",
            f"{VERIFY_FILE}#Action authorization provenance",
            f"{VERIFY_FILE}#Read-only AWS preflight evidence",
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
            f"{RUNBOOK_FILE}#Conditional AWS action receipts",
            f"{RUNBOOK_FILE}#Read-only AWS preflight",
            f"{RUNBOOK_FILE}#13. Teardown and decommissioning",
            f"{RUNBOOK_FILE}#14. Residual-resource and billing verification",
        ]
    elif deployment_closure_context:
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#AWS handoff and reconciliation",
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
        ]
        on_demand_slices = [
            f"{TASKS_FILE}#Active execution snapshot",
            f"{PRD_FILE}#Construction envelope",
            f"{VERIFY_FILE}#Action authorization provenance",
            f"{VERIFY_FILE}#Read-only AWS preflight evidence",
            f"{RUNBOOK_FILE}#Conditional AWS action receipts",
            f"{RUNBOOK_FILE}#Read-only AWS preflight",
        ]
        if next_prompt in {"AWS-30", "RELEASE-10"}:
            on_demand_slices.extend(
                [
                    f"{VERIFY_FILE}#Verification matrix",
                    f"{VERIFY_FILE}#Current release decision",
                ]
            )
    elif stage == "DEFINE":
        source_slices = [
            ".agents/skills/fastlane/references/define.md#Setup and intake",
            f"{PRD_FILE}#Document status",
            f"{PRD_FILE}#Product Agreement",
        ]
        on_demand_slices = [
            ".agents/skills/fastlane/references/define.md#Requirements and Gate A",
            ".agents/skills/fastlane/references/define.md#Review and AWS evidence",
            f"{PRD_FILE}#Gate A Review",
            BUGFIX_FILE,
        ]
    elif stage == "DESIGN":
        source_slices = [
            ".agents/skills/fastlane/references/design.md#Architecture selection and records",
            f"{PRD_FILE}#Adaptive coverage plan",
            f"{PRD_FILE}#Architecture drivers",
            f"{PRD_FILE}#Whole-system candidates",
            f"{PRD_FILE}#Selected architecture",
            f"{VERIFY_FILE}#AWS Core evidence",
        ]
        on_demand_slices = [
            ".agents/skills/fastlane/references/design.md#Architecture and AWS evidence",
            ".agents/skills/fastlane/references/design.md#Validation, diagrams, and Gate B",
            ".agents/skills/fastlane/references/design.md#Challenger and approval",
            f"{PRD_FILE}#Architecture traceability",
            f"{PRD_FILE}#Change impact record",
            f"{PRD_FILE}#Project diagram contract",
            f"{PRD_FILE}#Gate B Harness Profile",
            f"{PRD_FILE}#Construction envelope",
        ]
    elif stage == "DELIVER":
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#Tasks and local construction",
            f"{TASKS_FILE}#Active execution snapshot",
        ]
        on_demand_slices = [
            ".agents/skills/fastlane/references/deliver.md#AWS handoff and reconciliation",
            ".agents/skills/fastlane/references/deliver.md#Teardown and residuals",
            f"{PRD_FILE}#Construction envelope",
            f"{VERIFY_FILE}#Task completion evidence",
            f"{VERIFY_FILE}#Construction and release readiness checks",
            f"{RUNBOOK_FILE}#Active operational boundary",
        ]
    else:
        raise ValueError("context plan requires a known owner stage")

    active_ids: list[str] = []
    task_context_ids: list[str] = []
    if stage == "DELIVER":
        task_context_ids.extend(tasks.active)
        if not task_context_ids and tasks.ready:
            task_context_ids.append(tasks.ready[0])
        active_ids.extend(task_context_ids)
    else:
        active_ids.extend(coverage.basis_ids)
    blockers = interaction.get("blocking_ids")
    if isinstance(blockers, list):
        active_ids.extend(item for item in blockers if isinstance(item, str))
    active_ids = sorted(set(active_ids))

    if stage == "DELIVER" and task_context_ids:
        source_slices.append(f"{TASKS_FILE}#" + task_context_ids[0])
    aws_phase = next_prompt if next_prompt.startswith("AWS-") else ""
    teardown_context_reasons = {
        "AWS_RESIDUAL_REVIEW",
        "AWS_RESIDUAL_REVIEW_COMPLETE",
        "AWS_RESIDUALS_RETAINED",
        "AWS_RESIDUALS_REMAIN",
        "AWS_RESIDUAL_REVIEW_BLOCKED",
        "AWS_TEARDOWN_COMPLETE",
        "AWS_TEARDOWN_ACTION_TERMINAL",
    }
    teardown_phase_context = (
        aws_phase in {"AWS-40", "AWS-50"} or reason in teardown_context_reasons
    )
    if teardown_phase_context and not closure_context:
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#Teardown and residuals",
            f"{VERIFY_FILE}#Teardown reconciliation evidence",
        ]
        on_demand_slices.extend(
            [
                f"{TASKS_FILE}#Active execution snapshot",
                f"{PRD_FILE}#Construction envelope",
                f"{VERIFY_FILE}#Action authorization provenance",
                f"{VERIFY_FILE}#Read-only AWS preflight evidence",
                f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
                f"{VERIFY_FILE}#AWS Core evidence",
                f"{RUNBOOK_FILE}#Conditional AWS action receipts",
                f"{RUNBOOK_FILE}#Read-only AWS preflight",
                f"{RUNBOOK_FILE}#13. Teardown and decommissioning",
                f"{RUNBOOK_FILE}#14. Residual-resource and billing verification",
            ]
        )
        if task_context_ids:
            on_demand_slices.append(f"{TASKS_FILE}#" + task_context_ids[0])
    common_aws_slices = [
        f"{VERIFY_FILE}#Action authorization provenance",
        f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
        f"{RUNBOOK_FILE}#Conditional AWS action receipts",
        f"{VERIFY_FILE}#AWS Core evidence",
        f"{VERIFY_FILE}#Read-only AWS preflight evidence",
        f"{RUNBOOK_FILE}#Read-only AWS preflight",
    ]
    if closure_context:
        pass
    elif teardown_phase_context:
        pass
    elif reason == "AWS_DEPLOYMENT_ACTION_TERMINAL":
        source_slices.append(
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence"
        )
        on_demand_slices.extend(common_aws_slices)
    elif reason == "AWS_DEPLOYMENT_RECONCILIATION":
        source_slices.append(
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence"
        )
        on_demand_slices.extend(common_aws_slices)
    elif aws_phase or (isinstance(reason, str) and reason.startswith("AWS_")):
        source_slices.extend(common_aws_slices)
    if aws_phase == "AWS-30" and not closure_context:
        source_slices.extend(
            [
                f"{VERIFY_FILE}#Verification matrix",
                f"{VERIFY_FILE}#Current release decision",
            ]
        )
    if next_prompt == "RELEASE-10" and not closure_context:
        source_slices.extend(
            [
                f"{VERIFY_FILE}#Verification matrix",
                f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
                f"{VERIFY_FILE}#Current release decision",
            ]
        )
    if stage == "DESIGN" and source_texts is not None:
        prd_source = source_texts.get(PRD_FILE)
        if isinstance(prd_source, str):
            try:
                diagram_table = contract_table_after_heading(
                    prd_source, DIAGRAM_CONTRACT_HEADING, DIAGRAM_CONTRACT_HEADERS
                )
            except ValueError:
                diagram_table = None
            required_kinds = required_diagram_kinds(
                prd_source,
                authoritative_requirement_ids(prd_source),
                coverage.work_kind,
            )
            if diagram_table is not None and any(
                row[1] in required_kinds and row[3] != "CURRENT"
                for row in diagram_table.rows
            ):
                on_demand_slices.append(
                    ".agents/skills/fastlane/references/diagram-patterns.md"
                )
    if stage in {"DESIGN", "DELIVER"} and isinstance(adr_rationale, Mapping):
        records = adr_rationale.get("records")
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                relative = validate_relative_path(record.get("path"))
                if relative is not None and relative.startswith("docs/adr/"):
                    on_demand_slices.append(relative)
    source_slices = list(dict.fromkeys(source_slices))
    on_demand_slices = list(dict.fromkeys(on_demand_slices))

    plan: dict[str, Any] = {
        "source_slices": source_slices,
        "active_ids": active_ids,
        "on_demand_slices": on_demand_slices,
        "maximum_initial_bytes": CONTEXT_MAXIMUM_INITIAL_BYTES,
    }
    if source_texts is not None:
        metadata, issues = _resolve_context_metadata(
            source_slices,
            on_demand_slices,
            active_ids,
            source_texts,
        )
        plan.update(metadata)
        plan["_resolution_issues"] = issues
    return plan


def _split_authority_values(value: str) -> list[str]:
    """Return conservative exact values from a comma- or semicolon-list."""

    cleaned = clean_cell(value)
    if not explicit_value(cleaned, allow_none=False):
        return []
    return [item.strip() for item in re.split(r"[,;]", cleaned) if item.strip()]


def derive_write_authority(
    ctx: Context,
    envelope: dict[str, str],
    tasks: TaskSummary,
    construction_authorization: str,
) -> dict[str, Any]:
    """Project the current Gate B and active-task write boundaries for hooks."""

    result: dict[str, Any] = {
        "valid": False,
        "authorization_id": "NONE",
        "approved_write_roots": [],
        "exclusions": [],
        "protected_paths": [],
        "active_task": "NONE",
        "active_task_write_set": [],
    }
    if ctx.has_errors or construction_authorization == "NONE":
        return result
    try:
        roots = parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
        )
        exclusions = parse_envelope_paths(
            envelope.get("Excluded or owner-only write set", ""),
            "Excluded or owner-only write set",
            allow_none=True,
        )
        protected = parse_envelope_paths(
            envelope.get("Protected dirty paths", ""),
            "Protected dirty paths",
            allow_none=True,
        )
    except ValueError:
        return result
    active_task = tasks.active[0] if len(tasks.active) == 1 else "NONE"
    active_write_set = (
        tasks.write_sets.get(active_task, []) if active_task != "NONE" else []
    )
    return {
        "valid": True,
        "authorization_id": construction_authorization,
        "approved_write_roots": roots,
        "exclusions": exclusions,
        "protected_paths": protected,
        "active_task": active_task,
        "active_task_write_set": active_write_set,
    }


def derive_deployment_journal_closure_authority(
    deployment_sequence: Mapping[str, Any],
    next_prompt: str,
    *,
    restricted_closure: bool,
) -> dict[str, Any]:
    """Expose only the exact local VERIFY closure operation for one attempt."""

    empty: dict[str, Any] = {
        "valid": False,
        "kind": "NONE",
        "authorization_id": "NONE",
        "mode": "BOUNDED_EVIDENCE_CLOSURE",
        "allowed_write_paths": [],
        "allowed_sections": [],
        "allowed_operations": [],
        "allowed_release_states": [],
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }
    if not restricted_closure or deployment_sequence.get("issues"):
        return empty
    status = clean_cell(deployment_sequence.get("status", ""))
    contract = {
        ("ACTION_TERMINAL_REQUIRED", "AWS-20"): (
            [AWS_DEPLOYMENT_EVIDENCE_HEADING],
            ["APPEND_ACTION_TERMINAL_ROW"],
            [],
        ),
        ("RECONCILIATION_REQUIRED", "AWS-30"): (
            [
                "bootstrap:aws-read-preflight-receipt",
                "## Action authorization provenance",
                AWS_DEPLOYMENT_EVIDENCE_HEADING,
            ],
            [
                "RECORD_RECONCILIATION_READ_AUTHORITY",
                "APPEND_RECONCILIATION_ROW",
            ],
            [],
        ),
        ("RECONCILED", "RELEASE-10"): (
            ["## Current release decision"],
            ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
            (
                ["NOT_READY"]
                if deployment_sequence.get("basis_stale") is True
                else ["NOT_READY", "RELEASE_VERIFIED"]
            ),
        ),
        ("BLOCKED", "RELEASE-10"): (
            ["## Current release decision"],
            ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
            ["NOT_READY"],
        ),
    }.get((status, next_prompt))
    if contract is None:
        return empty
    attempt_id = clean_cell(deployment_sequence.get("attempt_id", ""))
    evidence_id = clean_cell(deployment_sequence.get("evidence_id", ""))
    if AWS_DEPLOYMENT_ATTEMPT_ID.fullmatch(attempt_id) is None:
        return empty
    if next_prompt == "RELEASE-10" and re.fullmatch(r"EV-\d{4,}", evidence_id) is None:
        return empty
    sections, operations, allowed_release_states = contract
    return {
        **empty,
        "valid": True,
        "kind": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
        "authorization_id": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
        "allowed_write_paths": [VERIFY_FILE],
        "allowed_sections": sections,
        "allowed_operations": operations,
        "allowed_release_states": allowed_release_states,
        "attempt_id": attempt_id,
        "evidence_id": evidence_id if evidence_id else "NONE",
    }


def derive_teardown_journal_closure_authority(
    teardown_sequence: Mapping[str, Any],
    next_prompt: str,
    *,
    restricted_closure: bool,
) -> dict[str, Any]:
    """Expose one exact VERIFY-only UNKNOWN closure for a lone STARTED row."""

    empty: dict[str, Any] = {
        "valid": False,
        "kind": "NONE",
        "authorization_id": "NONE",
        "mode": "BOUNDED_EVIDENCE_CLOSURE",
        "allowed_write_paths": [],
        "allowed_sections": [],
        "allowed_operations": [],
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }
    if (
        not restricted_closure
        or teardown_sequence.get("issues")
        or clean_cell(teardown_sequence.get("status", "")) != "ACTION_TERMINAL_REQUIRED"
        or next_prompt != "AWS-50"
    ):
        return empty
    attempt_id = clean_cell(teardown_sequence.get("attempt_id", ""))
    evidence_id = clean_cell(teardown_sequence.get("evidence_id", ""))
    if (
        AWS_TEARDOWN_ATTEMPT_ID.fullmatch(attempt_id) is None
        or re.fullmatch(r"EV-\d{4,}", evidence_id) is None
    ):
        return empty
    return {
        **empty,
        "valid": True,
        "kind": "AWS_TEARDOWN_JOURNAL_CLOSURE",
        "authorization_id": "AWS_TEARDOWN_JOURNAL_CLOSURE",
        "allowed_write_paths": [VERIFY_FILE],
        "allowed_sections": [AWS_TEARDOWN_EVIDENCE_HEADING],
        "allowed_operations": ["APPEND_TEARDOWN_TERMINAL_ROW"],
        "attempt_id": attempt_id,
        "evidence_id": evidence_id,
    }


def lifecycle_intent_record_boundary_is_settled(
    tasks: TaskSummary,
    release_decision: str,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> bool:
    """Return whether one local owner-intent record may be updated."""

    return bool(
        (
            tasks.terminal
            or clean_cell(deployment_sequence.get("status", "")) == "CONSUMED"
        )
        and release_lifecycle_intent_boundary_is_settled(
            release_decision, deployment_sequence
        )
        and clean_cell(teardown_sequence.get("status", ""))
        in {
            "NOT_ACTIVE",
            "STALE",
            "READY_FOR_TEARDOWN",
            "VERIFIED_CLEAN",
            "RESIDUALS_REMAIN",
        }
        and not teardown_sequence.get("issues")
    )


def derive_aws_lifecycle_intent_write_authority(
    ctx: Context,
    tasks: TaskSummary,
    release_decision: str,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
    external_authority: Mapping[str, Any],
    *,
    lifecycle_intent: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose one exact local owner-intent update and no AWS authority."""

    empty: dict[str, Any] = {
        "valid": False,
        "kind": "NONE",
        "authorization_id": "NONE",
        "mode": "BOUNDED_RELEASE_INTENT_RECORD",
        "allowed_write_paths": [],
        "allowed_sections": [],
        "allowed_operations": [],
        "allowed_values": [],
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }
    intent_value = clean_cell((lifecycle_intent or {}).get("value", "NONE"))
    teardown_status = clean_cell(teardown_sequence.get("status", "NOT_ACTIVE"))
    allowed_values = (
        ["RETAIN", "RESIDUAL_REVIEW", "TEARDOWN"]
        if teardown_status in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}
        else ["NONE", "RESIDUAL_REVIEW", "TEARDOWN"]
    )
    intent_route_active = bool(
        intent_value in {"RESIDUAL_REVIEW", "TEARDOWN"}
        and teardown_status in {"NOT_ACTIVE", "STALE"}
    )
    if (
        ctx.has_errors
        or intent_route_active
        or not lifecycle_intent_record_boundary_is_settled(
            tasks,
            release_decision,
            deployment_sequence,
            teardown_sequence,
        )
        or clean_cell(external_authority.get("validity", "NONE")) == "CURRENT"
    ):
        return empty
    return {
        **empty,
        "valid": True,
        "kind": "AWS_LIFECYCLE_INTENT_RECORD",
        "authorization_id": "AWS_LIFECYCLE_INTENT_RECORD",
        "allowed_write_paths": [VERIFY_FILE],
        "allowed_sections": ["## Current release decision"],
        "allowed_operations": ["UPDATE_AWS_LIFECYCLE_INTENT"],
        "allowed_values": allowed_values,
    }


def _action_authorization_rows(text: str) -> dict[str, dict[str, str]]:
    heading = "## Action authorization provenance"
    structural = without_fenced_code(text)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*$", structural, re.MULTILINE)
    )
    if len(matches) != 1:
        return {}
    original_lines = text[matches[0].end() :].splitlines()
    structural_lines = structural[matches[0].end() :].splitlines()
    start = next(
        (
            index
            for index, line in enumerate(structural_lines)
            if line.strip().startswith("|")
        ),
        None,
    )
    if start is None:
        return {}
    table: list[str] = []
    for original, visible in zip(original_lines[start:], structural_lines[start:]):
        if not visible.strip().startswith("|"):
            break
        table.append(original)
    if len(table) < 4:
        return {}
    headers = [clean_cell(cell) for cell in split_table_row(table[0])]
    result: dict[str, dict[str, str]] = {}
    for line in table[2:]:
        cells = [clean_cell(cell) for cell in split_table_row(line)]
        if len(cells) != len(headers):
            continue
        row = dict(zip(headers, cells))
        action = row.get("Action", "")
        if action in {"Read-only preflight", "Deployment", "Teardown"}:
            if action in result:
                # Conflicting or repeated provenance is never first-row-wins.
                return {}
            result[action] = row
    return result


def _receipt_fields(receipt: str, expected_title: str) -> dict[str, str] | None:
    lines = receipt.splitlines()
    if not lines or lines[0].strip() != expected_title:
        return None
    result: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            return None
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in result or not explicit_value(value, allow_none=True):
            return None
        result[key] = value
    return result


def _authorization_valid_until(
    value: str, result: str, *, allow_expired: bool = False
) -> str | None:
    cleaned = clean_cell(value)
    normalized = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        expires = datetime.fromisoformat(normalized)
    except ValueError:
        if cleaned == "ONE_OPERATION" and result in {"AUTHORIZED", "RUNNING", "READY"}:
            return cleaned
        return cleaned if explicit_value(cleaned) and result == "NOT_STARTED" else None
    if expires.tzinfo is None or expires.utcoffset() is None:
        return None
    return cleaned if allow_expired or expires > datetime.now(timezone.utc) else None


def _parse_cost_ceiling(value: str) -> tuple[str, Decimal] | None:
    """Return one canonical finite AWS cost ceiling or None."""

    try:
        return parse_positive_cost(value, AWS_COST_CEILING, "AWS cost ceiling")
    except ValueError:
        return None


def _cost_at_most(candidate: tuple[str, Decimal], ceiling: tuple[str, Decimal]) -> bool:
    return candidate[0] == ceiling[0] and candidate[1] <= ceiling[1]


def _read_bound_honors_cost_posture(
    bound: str,
    cost_posture: str,
    gate_b_cost_ceiling: str,
) -> bool:
    """Bind read-only billing exposure to Gate A and any Gate B ceiling."""

    cleaned_bound = clean_cell(bound)
    approved_posture = clean_cell(cost_posture)
    try:
        owner_cap = parse_cost_posture(approved_posture)
    except ValueError:
        return False
    if cleaned_bound == approved_posture:
        candidate = owner_cap
    else:
        try:
            validate_aws_cost_ceiling(cleaned_bound, approved_posture)
        except ValueError:
            return False
        candidate = _parse_cost_ceiling(cleaned_bound)
    gate_value = clean_cell(gate_b_cost_ceiling)
    if gate_value.startswith("NOT_APPLICABLE"):
        return True
    gate_cap = _parse_cost_ceiling(gate_value)
    return (
        candidate is not None
        and gate_cap is not None
        and _cost_at_most(candidate, gate_cap)
    )


def _envelope_scalar(envelope: Mapping[str, str], field: str, label: str) -> str | None:
    value = clean_cell(envelope.get(field, ""))
    prefix = label + ":"
    if not value.startswith(prefix):
        return None
    candidate = clean_cell(value[len(prefix) :])
    return candidate if explicit_value(candidate, allow_none=False) else None


def _envelope_values(envelope: Mapping[str, str], field: str, label: str) -> list[str]:
    value = clean_cell(envelope.get(field, ""))
    prefix = label + ":"
    if not value.startswith(prefix):
        return []
    return _split_authority_values(value[len(prefix) :])


def _receipt_identity_matches_gate_b(
    fields: Mapping[str, str], envelope: Mapping[str, str]
) -> bool:
    try:
        environment, _environment_class = parse_aws_environment(
            envelope.get("AWS environment", "")
        )
    except ValueError:
        return False
    expected = {
        "Profile or role": _envelope_scalar(envelope, "AWS role or profile", "ROLE"),
        "Account": _envelope_scalar(envelope, "AWS account", "ACCOUNT"),
        "Region": _envelope_scalar(envelope, "AWS Region", "REGION"),
        "Environment": environment,
    }
    return all(
        expected_value is not None and fields.get(field) == expected_value
        for field, expected_value in expected.items()
    )


def _receipt_scope_within_gate_b(
    resources: list[str],
    operations: list[str],
    envelope: Mapping[str, str],
) -> bool:
    allowed_resources = set(
        _envelope_values(envelope, "AWS resource allowlist", "RESOURCES")
    )
    allowed_operations = set(
        _envelope_values(envelope, "AWS allowed operations", "OPERATIONS")
    )
    unsafe = any("*" in item for item in resources + operations)
    return bool(
        resources
        and operations
        and not unsafe
        and len(resources) == len(set(resources))
        and len(operations) == len(set(operations))
        and set(resources).issubset(allowed_resources)
        and set(operations).issubset(allowed_operations)
    )


def _receipt_artifact_matches_gate_b(
    artifact: str,
    envelope: Mapping[str, str],
    active_artifact: str,
) -> bool:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", artifact) is None:
        return False
    if artifact != clean_cell(active_artifact):
        return False
    approved = clean_cell(envelope.get("AWS artifact authorization and provenance", ""))
    if approved.startswith("NOT_APPLICABLE"):
        return envelope.get("AWS boundary") == "READ_ONLY"
    if AWS_EXACT_ARTIFACT.fullmatch(approved) is not None:
        return artifact == approved.removeprefix("EXACT_DIGEST: ")
    try:
        validate_aws_artifact(
            approved, clean_cell(envelope.get("Authorized baseline commit", ""))
        )
    except ValueError:
        return False
    return AWS_DERIVED_ARTIFACT.fullmatch(approved) is not None


def _authorization_expiry_ceiling(value: str, *, allow_expired: bool) -> datetime:
    if not allow_expired:
        return parse_future_expiry(value)
    cleaned = clean_cell(value)
    match = re.fullmatch(
        r"Expires at (?P<timestamp>[^\s;]+); earlier completion: (?P<condition>[^\r\n]+)",
        cleaned,
    )
    if match is None or not explicit_value(match.group("condition"), allow_none=False):
        raise ValueError("Authorization expiry is not canonical")
    expires_at = _iso_datetime(match.group("timestamp"))
    if expires_at is None:
        raise ValueError("Authorization expiry timestamp is not ISO 8601 with timezone")
    return expires_at


def _receipt_validity_within_gate_b(
    valid_until: str,
    result: str,
    envelope: Mapping[str, str],
    *,
    allow_expired: bool = False,
) -> str | None:
    current = _authorization_valid_until(
        valid_until, result, allow_expired=allow_expired
    )
    if current is None:
        return None
    try:
        ceilings = [
            _authorization_expiry_ceiling(
                envelope.get("Authorization expiry or completion condition", ""),
                allow_expired=allow_expired,
            )
        ]
    except ValueError:
        return None
    aws_validity = clean_cell(envelope.get("AWS authorization validity", ""))
    if not aws_validity.startswith("NOT_APPLICABLE"):
        try:
            ceilings.append(
                _authorization_expiry_ceiling(aws_validity, allow_expired=allow_expired)
            )
        except ValueError:
            return None
    if current == "ONE_OPERATION":
        return current
    expires = _iso_datetime(current)
    if expires is None:
        return None
    return current if all(expires <= ceiling for ceiling in ceilings) else None


def _gate_b_rollback_value(envelope: Mapping[str, str]) -> str | None:
    value = clean_cell(envelope.get("AWS rollback boundary", ""))
    prefix = "ROLLBACK:"
    if not value.startswith(prefix):
        return None
    candidate = clean_cell(value[len(prefix) :])
    if unresolved(candidate) or not candidate:
        return None
    return candidate


def _mutation_cost_within_gate_b(
    value: str,
    envelope: Mapping[str, str],
    cost_posture: str,
) -> bool:
    try:
        validate_aws_cost_ceiling(value, cost_posture)
    except ValueError:
        return False
    candidate = _parse_cost_ceiling(value)
    gate_cap = _parse_cost_ceiling(envelope.get("AWS cost ceiling", ""))
    return (
        candidate is not None
        and gate_cap is not None
        and _cost_at_most(candidate, gate_cap)
    )


def _exact_receipt_fields(
    receipt: str,
    expected_title: str,
    expected_fields: tuple[str, ...],
    *,
    allow_none_fields: frozenset[str] = frozenset(),
) -> dict[str, str] | None:
    lines = receipt.splitlines()
    if len(lines) != len(expected_fields) + 1 or lines[0].strip() != expected_title:
        return None
    result: dict[str, str] = {}
    for line, expected in zip(lines[1:], expected_fields):
        if ":" not in line:
            return None
        key, value = line.split(":", 1)
        if key.strip() != expected:
            return None
        value = value.strip()
        if not explicit_value(value, allow_none=expected in allow_none_fields):
            return None
        result[expected] = value
    return result


def _read_preflight_receipt_authority(
    verify_text: str,
    construction_authorization: str,
    cost_posture: str,
    envelope: Mapping[str, str],
    active_artifact: str,
    *,
    allow_one_operation: bool = True,
    allow_expired: bool = False,
) -> dict[str, Any] | None:
    """Project one exact owner-authored read-only preflight scope."""

    try:
        receipt = marked_receipt(verify_text, "aws-read-preflight")
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS READ-ONLY PREFLIGHT",
        AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
    )
    row = _action_authorization_rows(verify_text).get("Read-only preflight")
    if fields is None or row is None or unresolved(receipt):
        return None
    authorization_id = fields["Read authorization"]
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    result = clean_cell(row.get("Result", ""))
    valid_until = _receipt_validity_within_gate_b(
        fields["Valid until"],
        result,
        envelope,
        allow_expired=allow_expired,
    )
    if valid_until == "ONE_OPERATION" and not allow_one_operation:
        return None
    cost_validity = clean_cell(row.get("Cost ceiling and validity", ""))
    cost_match = re.fullmatch(
        r"COST: (?P<effect>.+?); BOUNDED_BY: (?P<bound>.+?); VALID_UNTIL: (?P<until>.+)",
        cost_validity,
    )
    valid_cost_provenance = bool(
        cost_match
        and explicit_value(cost_match.group("effect"), allow_none=False)
        and explicit_value(cost_match.group("bound"), allow_none=False)
        and not clean_cell(cost_match.group("effect")).startswith("NOT_APPLICABLE")
        and not clean_cell(cost_match.group("bound")).startswith("NOT_APPLICABLE")
        and _read_bound_honors_cost_posture(
            cost_match.group("bound"),
            cost_posture,
            envelope.get("AWS cost ceiling", ""),
        )
        and clean_cell(cost_match.group("until")) == fields["Valid until"]
    )
    read_cost = (
        f"EXPECTED: {clean_cell(cost_match.group('effect'))}; "
        f"BOUNDED_BY: {clean_cell(cost_match.group('bound'))}"
        if cost_match
        else "NONE"
    )
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    expected_resources = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed read-only operations']}"
    )
    observed_at = clean_cell(row.get("Observed at", ""))
    if (
        AWS_READ_AUTHORIZATION_ID.fullmatch(authorization_id) is None
        or fields["Construction authorization"] != construction_authorization
        or fields["Prohibited operations"] != "ALL_MUTATIONS"
        or row.get("Authorization ID") != authorization_id
        or row.get("Construction AUTH") != construction_authorization
        or row.get("Role or profile") != fields["Profile or role"]
        or row.get("Artifact digest") != fields["Artifact digest"]
        or row.get("Account / Region / environment") != expected_scope
        or row.get("Resources and operations") != expected_resources
        or row.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(row.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(row.get("Stable owner-message source", ""))
        or not explicit_timestamp(observed_at)
        or clean_cell(row.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or not valid_cost_provenance
        or valid_until is None
        or result not in {"AUTHORIZED", "RUNNING", "READY"}
    ):
        return None
    resources = _split_authority_values(fields["Stack, application, and resources"])
    operations = _split_authority_values(fields["Allowed read-only operations"])
    if (
        not resources
        or not operations
        or any(AWS_READ_ONLY_OPERATION.fullmatch(item) is None for item in operations)
        or not _receipt_identity_matches_gate_b(fields, envelope)
        or not _receipt_scope_within_gate_b(resources, operations, envelope)
        or not _receipt_artifact_matches_gate_b(
            fields["Artifact digest"], envelope, active_artifact
        )
    ):
        return None
    return {
        "kind": "AWS_READ_ONLY",
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "account": fields["Account"],
        "region": fields["Region"],
        "environment": fields["Environment"],
        "role_or_profile": fields["Profile or role"],
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {
            "artifact": fields["Artifact digest"],
            "plan": "NONE",
        },
        "cost_ceiling": read_cost,
        "rollback_boundary": "NONE",
        "expiration": valid_until,
        "authorized_at": observed_at,
        "authority_source": clean_cell(row.get("Stable owner-message source", "")),
    }


def _deployment_reconciliation_read_authority(
    verify_text: str,
    cost_posture: str,
    group: list[dict[str, str]],
    *,
    allow_expired: bool = False,
    require_post_action_freshness: bool = False,
) -> dict[str, Any] | None:
    """Project exact read-only scope for current or restricted reconciliation."""

    if not group:
        return None
    first = group[0]
    basis_match = re.fullmatch(
        r"REQ-\d{4,} / DES-\d{4,} / (?P<auth>AUTH-\d{4,})",
        clean_cell(first.get("REQ / DES / AUTH", "")),
    )
    scope_match = re.fullmatch(
        r"ACCOUNT: (?P<account>[^;]+); REGION: (?P<region>[^;]+); "
        r"ENVIRONMENT: (?P<environment>[^;]+)",
        clean_cell(first.get("Account / Region / environment", "")),
    )
    if basis_match is None or scope_match is None:
        return None
    account = clean_cell(scope_match.group("account"))
    region = clean_cell(scope_match.group("region"))
    environment = clean_cell(scope_match.group("environment"))
    artifact = clean_cell(first.get("Artifact digest", ""))
    if (
        any(
            not explicit_value(value, allow_none=False) or "*" in value
            for value in (account, region, environment)
        )
        or re.fullmatch(r"sha256:[0-9a-f]{64}", artifact) is None
    ):
        return None
    try:
        attempted_resources = _deployment_values(
            first.get("Resources", ""), "Resources", allow_none=False
        )
        receipt = marked_receipt(verify_text, "aws-read-preflight")
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS READ-ONLY PREFLIGHT",
        AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
    )
    row = _action_authorization_rows(verify_text).get("Read-only preflight")
    if fields is None or row is None or unresolved(receipt):
        return None
    authorization_id = fields["Read authorization"]
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    result = clean_cell(row.get("Result", ""))
    valid_until = _authorization_valid_until(
        fields["Valid until"], result, allow_expired=allow_expired
    )
    if valid_until in {None, "ONE_OPERATION"}:
        return None
    cost_validity = clean_cell(row.get("Cost ceiling and validity", ""))
    cost_match = re.fullmatch(
        r"COST: (?P<effect>.+?); BOUNDED_BY: (?P<bound>.+?); VALID_UNTIL: (?P<until>.+)",
        cost_validity,
    )
    valid_cost_provenance = bool(
        cost_match
        and explicit_value(cost_match.group("effect"), allow_none=False)
        and explicit_value(cost_match.group("bound"), allow_none=False)
        and not clean_cell(cost_match.group("effect")).startswith("NOT_APPLICABLE")
        and not clean_cell(cost_match.group("bound")).startswith("NOT_APPLICABLE")
        and _read_bound_honors_cost_posture(
            cost_match.group("bound"),
            cost_posture,
            "NOT_APPLICABLE — reconciliation receipt is the read-only ceiling",
        )
        and clean_cell(cost_match.group("until")) == fields["Valid until"]
    )
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    expected_resources = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed read-only operations']}"
    )
    observed_at = clean_cell(row.get("Observed at", ""))
    authorized_at = _iso_datetime(observed_at)
    if (
        AWS_READ_AUTHORIZATION_ID.fullmatch(authorization_id) is None
        or fields["Construction authorization"] != basis_match.group("auth")
        or fields["Prohibited operations"] != "ALL_MUTATIONS"
        or fields["Account"] != account
        or fields["Region"] != region
        or fields["Environment"] != environment
        or fields["Artifact digest"] != artifact
        or row.get("Authorization ID") != authorization_id
        or row.get("Construction AUTH") != basis_match.group("auth")
        or row.get("Role or profile") != fields["Profile or role"]
        or row.get("Artifact digest") != artifact
        or row.get("Account / Region / environment") != expected_scope
        or row.get("Resources and operations") != expected_resources
        or row.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(row.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(
            row.get("Stable owner-message source", ""), allow_none=False
        )
        or "*" in clean_cell(row.get("Stable owner-message source", ""))
        or authorized_at is None
        or clean_cell(row.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or not valid_cost_provenance
        or result not in {"AUTHORIZED", "RUNNING", "READY"}
    ):
        return None
    resources = _split_authority_values(fields["Stack, application, and resources"])
    operations = _split_authority_values(fields["Allowed read-only operations"])
    if (
        not resources
        or not operations
        or len(resources) != len(set(resources))
        or len(operations) != len(set(operations))
        or any("*" in item for item in resources + operations)
        or set(resources) != set(attempted_resources)
        or any(AWS_READ_ONLY_OPERATION.fullmatch(item) is None for item in operations)
    ):
        return None

    if require_post_action_freshness:
        terminal_reconciliation = (
            group[-1]
            if clean_cell(group[-1].get("Phase", "")) == "AWS-30"
            and clean_cell(group[-1].get("Status", "")) in {"COMPLETE", "BLOCKED"}
            else None
        )
        if terminal_reconciliation is None:
            prior_times = [_iso_datetime(item.get("Observed at", "")) for item in group]
            if any(item is None for item in prior_times) or authorized_at <= max(
                prior_times
            ):
                return None
        else:
            prior_times = [
                _iso_datetime(item.get("Observed at", "")) for item in group[:-1]
            ]
            terminal_at = _iso_datetime(terminal_reconciliation.get("Observed at", ""))
            if (
                not prior_times
                or any(item is None for item in prior_times)
                or terminal_at is None
                or authorized_at <= max(prior_times)
                or authorized_at > terminal_at
            ):
                return None

    read_cost = (
        f"EXPECTED: {clean_cell(cost_match.group('effect'))}; "
        f"BOUNDED_BY: {clean_cell(cost_match.group('bound'))}"
        if cost_match
        else "NONE"
    )
    return {
        "kind": "AWS_READ_ONLY",
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "account": account,
        "region": region,
        "environment": environment,
        "role_or_profile": fields["Profile or role"],
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {"artifact": artifact, "plan": "NONE"},
        "cost_ceiling": read_cost,
        "rollback_boundary": "NONE",
        "expiration": valid_until,
        "authorized_at": observed_at,
        "authority_source": clean_cell(row.get("Stable owner-message source", "")),
        "reconciliation_only": require_post_action_freshness,
        "attempt_id": clean_cell(first.get("Attempt ID", "")),
    }


def parse_read_preflight_evidence(text: str) -> list[dict[str, str]]:
    table = contract_table_after_heading(
        text, AWS_READ_PREFLIGHT_HEADING, AWS_READ_PREFLIGHT_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def parse_teardown_reconciliation_evidence(text: str) -> list[dict[str, str]]:
    table = contract_table_after_heading(
        text, AWS_TEARDOWN_EVIDENCE_HEADING, AWS_TEARDOWN_EVIDENCE_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def parse_deployment_reconciliation_evidence(
    text: str,
) -> list[dict[str, str]]:
    """Parse the append-only AWS-20/AWS-30 deployment operation journal."""

    table = contract_table_after_heading(
        text, AWS_DEPLOYMENT_EVIDENCE_HEADING, AWS_DEPLOYMENT_EVIDENCE_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def parse_verification_matrix(text: str) -> list[dict[str, str]]:
    """Parse the canonical release acceptance registry."""

    table = contract_table_after_heading(
        text, VERIFICATION_MATRIX_HEADING, VERIFICATION_MATRIX_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def _deployment_acceptance_evidence_issues(
    verify_text: str,
    evidence_ids: list[str],
    expected: Mapping[str, Any],
) -> list[str]:
    """Resolve AWS-30 COMPLETE IDs to current VERIFIED target-bound evidence."""

    try:
        rows = parse_verification_matrix(verify_text)
    except ValueError as exc:
        return [str(exc)]
    by_id: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id):
            by_id.setdefault(evidence_id, []).append(row)
    expected_target = (
        f"ARTIFACT: {expected.get('artifact')}; ACCOUNT: {expected.get('account')}; "
        f"REGION: {expected.get('region')}; ENVIRONMENT: {expected.get('environment')}"
    )
    issues: list[str] = []
    for evidence_id in evidence_ids:
        matching = by_id.get(evidence_id, [])
        if len(matching) != 1:
            issues.append(
                f"{evidence_id} must resolve exactly once in the Verification matrix"
            )
            continue
        row = matching[0]
        if clean_cell(row.get("Status", "")) != "VERIFIED":
            issues.append(f"{evidence_id} Verification matrix status must be VERIFIED")
        requirement = clean_cell(row.get("Requirement or invariant", ""))
        manual_evidence = clean_cell(row.get("AWS/manual evidence", ""))
        if not explicit_value(requirement, allow_none=False) or "*" in requirement:
            issues.append(f"{evidence_id} requires a concrete requirement or invariant")
        if (
            not explicit_value(manual_evidence, allow_none=False)
            or "*" in manual_evidence
        ):
            issues.append(f"{evidence_id} requires concrete AWS/manual evidence")
        if clean_cell(row.get("Artifact/environment", "")) != expected_target:
            issues.append(
                f"{evidence_id} does not bind the exact artifact/account/Region/environment"
            )
    return issues


def _deployment_operation_result_issues(
    value: str, evidence_id: str, *, started: bool
) -> list[str]:
    """Validate the machine-readable operation identifier and direct-result grammar."""

    cleaned = clean_cell(value)
    if started:
        return (
            []
            if cleaned == AWS_DEPLOYMENT_PRECALL_RESULT
            else [f"{evidence_id} STARTED must use the exact pre-call result sentinel"]
        )
    match = re.fullmatch(
        r"IDENTIFIERS: (?P<identifiers>.+); RESULT: (?P<result>.+)", cleaned
    )
    if match is None:
        return [
            f"{evidence_id} post-call result must use IDENTIFIERS: <list or NONE reason>; RESULT: <direct result>"
        ]
    identifiers = clean_cell(match.group("identifiers"))
    result = clean_cell(match.group("result"))
    none_match = re.fullmatch(r"NONE \u2014 (?P<reason>.+)", identifiers)
    if none_match is not None:
        reason = clean_cell(none_match.group("reason"))
        if not explicit_value(reason, allow_none=False) or "*" in reason:
            return [f"{evidence_id} NONE identifiers require a concrete reason"]
    else:
        values = [item.strip() for item in identifiers.split(",")]
        if (
            not values
            or len(values) != len(set(values))
            or any(
                not explicit_value(item, allow_none=False)
                or "*" in item
                or re.search(r"[\r\n\x00-\x1f\x7f]", item) is not None
                for item in values
            )
        ):
            return [
                f"{evidence_id} operation identifiers must be a unique exact wildcard-free list"
            ]
    if not explicit_value(result, allow_none=False) or "*" in result:
        return [f"{evidence_id} requires a concrete direct result"]
    return []


def _deployment_values(value: str, label: str, *, allow_none: bool) -> list[str]:
    cleaned = clean_cell(value)
    if allow_none and cleaned == "NONE":
        return []
    values = _split_authority_values(cleaned)
    if (
        not values
        or len(values) != len(set(values))
        or any("*" in item for item in values)
    ):
        raise ValueError(f"{label} must be a unique wildcard-free exact list")
    return values


def _deployment_evidence_ids(value: str, *, allow_none: bool) -> list[str]:
    values = _deployment_values(value, "Acceptance evidence IDs", allow_none=allow_none)
    if any(re.fullmatch(r"EV-\d{4,}", item) is None for item in values):
        raise ValueError(
            "Acceptance evidence IDs must be a unique comma-separated EV list or NONE"
        )
    return values


def _deployment_expected_binding(
    verify_text: str,
    *,
    construction_authorization: str,
    envelope: Mapping[str, str],
    lane: str | None,
    artifact_binding: str,
    gate_b_authority_source: str = "",
    gate_b_authorized_at: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """Return the current mutation ceiling without treating it as an attempt."""

    issues: list[str] = []
    if construction_authorization == "NONE":
        return {}, ["deployment evidence requires a current construction authorization"]
    if lane not in {"fast-dev", "explicit-gate"}:
        return {}, ["deployment evidence is not permitted for the selected AWS lane"]
    try:
        environment, _environment_class = parse_aws_environment(
            envelope.get("AWS environment", "")
        )
    except ValueError:
        environment = ""
    account = _envelope_scalar(envelope, "AWS account", "ACCOUNT")
    region = _envelope_scalar(envelope, "AWS Region", "REGION")
    deployment_role = _envelope_scalar(envelope, "AWS role or profile", "ROLE")
    resources = _envelope_values(envelope, "AWS resource allowlist", "RESOURCES")
    allowed_operations = _envelope_values(
        envelope, "AWS allowed operations", "OPERATIONS"
    )
    operations = (
        [
            operation
            for operation in allowed_operations
            if AWS_READ_ONLY_OPERATION.fullmatch(operation) is None
        ]
        if lane == "fast-dev"
        else allowed_operations
    )
    for label, value in (
        ("AWS account", account),
        ("AWS Region", region),
        ("AWS environment", environment),
        ("AWS role or profile", deployment_role),
    ):
        if not value:
            issues.append(f"deployment evidence requires exact {label}")
    if not resources or not operations:
        issues.append(
            "deployment evidence requires exact Gate B resources and operations"
        )
    if not _receipt_artifact_matches_gate_b(
        artifact_binding, envelope, artifact_binding
    ):
        issues.append("deployment evidence artifact is outside current Gate B")
    authorization_validity = clean_cell(envelope.get("AWS authorization validity", ""))
    validity_match = re.fullmatch(
        r"Expires at (?P<timestamp>[^\s;]+); earlier completion: [^\r\n]+",
        authorization_validity,
    )
    expected: dict[str, Any] = {
        "authorization_id": construction_authorization,
        "receipt_digest": "NONE",
        "authorized_at": clean_cell(gate_b_authorized_at),
        "valid_until": (
            validity_match.group("timestamp") if validity_match is not None else "NONE"
        ),
        "deployment_role": deployment_role or "NONE",
        "deployment_authority_source": clean_cell(gate_b_authority_source),
        "artifact": artifact_binding,
        "plan": clean_cell(envelope.get("AWS stack or application", "")),
        "account": account or "NONE",
        "region": region or "NONE",
        "environment": environment or "NONE",
        "resources": resources,
        "operations": operations,
        "verify_text": verify_text,
    }
    if lane == "fast-dev":
        if validity_match is None:
            issues.append(
                "fast-dev deployment evidence requires exact authorization validity"
            )
        if not explicit_timestamp(expected["authorized_at"]):
            issues.append(
                "fast-dev deployment evidence requires the Gate B authorization timestamp"
            )
        if not explicit_value(expected["plan"], allow_none=False):
            issues.append(
                "fast-dev deployment evidence requires an exact stack or application"
            )
        if (
            not explicit_value(
                expected["deployment_authority_source"], allow_none=False
            )
            or "*" in expected["deployment_authority_source"]
        ):
            issues.append(
                "fast-dev deployment evidence requires the Gate B owner authorization source"
            )
        return expected, issues

    try:
        receipt = marked_receipt(verify_text, "aws-deployment")
        provenance = _action_authorization_rows(verify_text).get("Deployment")
    except ValueError:
        receipt = ""
        provenance = None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS DEPLOYMENT",
        AWS_DEPLOYMENT_RECEIPT_FIELDS,
        allow_none_fields=frozenset({"Rollback boundary"}),
    )
    digest = (
        "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        if receipt
        else "NONE"
    )
    if fields is None or provenance is None or unresolved(receipt):
        issues.append(
            "explicit-gate deployment evidence requires one exact owner-authored receipt"
        )
        return expected, issues
    receipt_resources = _split_authority_values(
        fields["Stack, application, and resources"]
    )
    receipt_operations = _split_authority_values(fields["Allowed operations"])
    receipt_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    receipt_resources_and_operations = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed operations']}"
    )
    expected.update(
        {
            "authorization_id": fields["AWS authorization"],
            "receipt_digest": digest,
            "authorized_at": clean_cell(provenance.get("Observed at", "")),
            "valid_until": fields["Valid until"],
            "deployment_role": fields["Profile or role"],
            "deployment_authority_source": clean_cell(
                provenance.get("Stable owner-message source", "")
            ),
            "artifact": fields["Artifact digest"],
            "plan": fields["IaC plan/change-set binding"],
            "account": fields["Account"],
            "region": fields["Region"],
            "environment": fields["Environment"],
            "resources": receipt_resources,
            "operations": receipt_operations,
        }
    )
    receipt_binding_invalid = (
        re.fullmatch(r"AWS-AUTH-\d{4,}", fields["AWS authorization"]) is None
        or fields["Construction authorization"] != construction_authorization
        or AWS_PLAN_BINDING.fullmatch(fields["IaC plan/change-set binding"]) is None
        or not _receipt_identity_matches_gate_b(fields, envelope)
        or not _receipt_scope_within_gate_b(
            receipt_resources, receipt_operations, envelope
        )
        or not _receipt_artifact_matches_gate_b(
            fields["Artifact digest"], envelope, artifact_binding
        )
        or fields["Rollback boundary"] != _gate_b_rollback_value(envelope)
    )
    provenance_invalid = (
        provenance.get("Authorization ID") != fields["AWS authorization"]
        or provenance.get("Construction AUTH") != construction_authorization
        or provenance.get("Role or profile") != fields["Profile or role"]
        or provenance.get("Artifact digest") != fields["Artifact digest"]
        or provenance.get("IaC plan/change-set binding")
        != fields["IaC plan/change-set binding"]
        or provenance.get("Account / Region / environment") != receipt_scope
        or provenance.get("Resources and operations")
        != receipt_resources_and_operations
        or provenance.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(provenance.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(
            provenance.get("Stable owner-message source", ""), allow_none=False
        )
        or not explicit_timestamp(provenance.get("Observed at", ""))
        or clean_cell(provenance.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or clean_cell(provenance.get("Result", ""))
        not in {"AUTHORIZED", "RUNNING", "READY"}
        or AWS_PREFLIGHT_ID.fullmatch(
            clean_cell(provenance.get("Preflight evidence", ""))
        )
        is None
    )
    if receipt_binding_invalid:
        issues.append(
            "deployment receipt does not match current Gate B identity, scope, "
            "artifact, plan, or rollback boundary"
        )
    if provenance_invalid:
        issues.append(
            "deployment receipt does not match its exact authorization provenance"
        )
    return expected, issues


def _deployment_row_binding_issues(
    row: Mapping[str, str],
    expected: Mapping[str, Any],
    read_authority: Mapping[str, Any] | None,
    *,
    historical: bool = False,
) -> list[str]:
    evidence_id = clean_cell(row.get("Evidence ID", "")) or "deployment row"
    phase = clean_cell(row.get("Phase", ""))
    status = clean_cell(row.get("Status", ""))
    issues: list[str] = []
    expected_scope = (
        f"ACCOUNT: {expected.get('account')}; REGION: {expected.get('region')}; "
        f"ENVIRONMENT: {expected.get('environment')}"
    )
    scalar_fields = {
        "Deployment authorization": expected.get("authorization_id"),
        "Deployment receipt digest": expected.get("receipt_digest"),
        "Deployment valid until": expected.get("valid_until"),
        "Deployment authority source": expected.get("deployment_authority_source"),
        "Deployment role or profile": expected.get("deployment_role"),
        "Artifact digest": expected.get("artifact"),
        "Plan/change-set binding": expected.get("plan"),
        "Account / Region / environment": expected_scope,
    }
    for field_name, value in scalar_fields.items():
        if clean_cell(row.get(field_name, "")) != clean_cell(value):
            issues.append(f"{evidence_id} {field_name} does not match its authority")
    try:
        resources = _deployment_values(
            row.get("Resources", ""), "Resources", allow_none=False
        )
        operations = _deployment_values(
            row.get("Mutation operations", ""),
            "Mutation operations",
            allow_none=False,
        )
    except ValueError as exc:
        issues.append(str(exc))
        resources, operations = [], []
    if set(resources) != set(expected.get("resources", [])):
        issues.append(f"{evidence_id} Resources do not match the attempted scope")
    if set(operations) != set(expected.get("operations", [])):
        issues.append(
            f"{evidence_id} Mutation operations do not match the attempted scope"
        )
    started = phase == "AWS-20" and status == "STARTED"
    operation_result = clean_cell(
        row.get("Operation identifiers and direct result", "")
    )
    issues.extend(
        _deployment_operation_result_issues(
            operation_result, evidence_id, started=started
        )
    )
    rollback_result = clean_cell(row.get("Rollback result", ""))
    if started and rollback_result != "NONE":
        issues.append(f"{evidence_id} STARTED must use Rollback result = NONE")
    for field_name, allow_none in (
        ("Rollback result", True),
        ("Durable source", False),
    ):
        if not explicit_value(row.get(field_name, ""), allow_none=allow_none):
            issues.append(f"{evidence_id} requires {field_name}")
    blocker_reason = clean_cell(row.get("Blocker or stale reason", ""))
    if status in {"BLOCKED", "STALE"}:
        if not explicit_value(blocker_reason, allow_none=False):
            issues.append(f"{evidence_id} requires an exact blocker or stale reason")
    elif blocker_reason != "NONE":
        issues.append(f"{evidence_id} must use Blocker or stale reason = NONE")
    identity = clean_cell(row.get("Identity and boundary match", ""))
    if phase == "AWS-20":
        for field_name in (
            "Read authorization",
            "Read role or profile",
            "Read receipt digest",
            "Read valid until",
            "Read authority source",
            "Read operations observed",
            "Acceptance evidence IDs",
        ):
            if clean_cell(row.get(field_name, "")) != "NONE":
                issues.append(f"{evidence_id} AWS-20 requires {field_name} = NONE")
        if identity not in {"PASS", "VERIFIED"}:
            issues.append(
                f"{evidence_id} AWS-20 requires verified identity and boundary"
            )
        return issues

    read_id = clean_cell(row.get("Read authorization", ""))
    read_role = clean_cell(row.get("Read role or profile", ""))
    read_digest = clean_cell(row.get("Read receipt digest", ""))
    read_valid_until = clean_cell(row.get("Read valid until", ""))
    read_source = clean_cell(row.get("Read authority source", ""))
    read_provenance = _parse_deployment_read_provenance(read_source)
    if AWS_READ_AUTHORIZATION_ID.fullmatch(read_id) is None:
        issues.append(f"{evidence_id} AWS-30 requires a separate read authorization")
    if not explicit_value(read_role, allow_none=False):
        issues.append(f"{evidence_id} AWS-30 requires a separate read role")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", read_digest) is None:
        issues.append(f"{evidence_id} AWS-30 requires an exact read receipt digest")
    read_expiry = _iso_datetime(read_valid_until)
    observed_at = _iso_datetime(row.get("Observed at", ""))
    if read_valid_until == "ONE_OPERATION" or read_expiry is None:
        issues.append(f"{evidence_id} AWS-30 requires reusable ISO read validity")
    elif observed_at is not None and observed_at > read_expiry:
        issues.append(f"{evidence_id} AWS-30 was observed after read authority expiry")
    if read_provenance is None:
        issues.append(
            f"{evidence_id} AWS-30 requires the exact durable read authority "
            "source, authorization time, resources, and operations envelope"
        )
    try:
        observed_reads = _deployment_values(
            row.get("Read operations observed", ""),
            "Read operations observed",
            allow_none=status == "STALE",
        )
        acceptance_ids = _deployment_evidence_ids(
            row.get("Acceptance evidence IDs", ""),
            allow_none=status != "COMPLETE",
        )
    except ValueError as exc:
        issues.append(str(exc))
        observed_reads, acceptance_ids = [], []
    if read_provenance is not None:
        read_authorized_at = _iso_datetime(read_provenance["authorized_at"])
        if (
            observed_at is not None
            and read_authorized_at is not None
            and observed_at < read_authorized_at
        ):
            issues.append(
                f"{evidence_id} AWS-30 observation precedes read authorization"
            )
        if resources != read_provenance["resources"]:
            issues.append(
                f"{evidence_id} Resources do not match the durable read authorization"
            )
        if not set(observed_reads).issubset(set(read_provenance["operations"])):
            issues.append(
                f"{evidence_id} observed reads exceed the durable read authorization"
            )
    if status in {"COMPLETE", "BLOCKED"} and identity not in {"PASS", "VERIFIED"}:
        issues.append(f"{evidence_id} AWS-30 requires verified identity and boundary")
    if status == "STALE" and not explicit_value(identity, allow_none=False):
        issues.append(
            f"{evidence_id} STALE requires a concrete identity and boundary result"
        )
    if (
        status in {"COMPLETE", "BLOCKED"}
        and not historical
        and read_authority is not None
    ):
        same_read_id = read_id == clean_cell(read_authority.get("authorization_id", ""))
        if not same_read_id:
            issues.append(
                f"{evidence_id} read authorization does not match current authority"
            )
        else:
            read_scope = (
                f"ACCOUNT: {read_authority.get('account')}; "
                f"REGION: {read_authority.get('region')}; "
                f"ENVIRONMENT: {read_authority.get('environment')}"
            )
            read_authorized_at = _iso_datetime(read_authority.get("authorized_at", ""))
            if read_authorized_at is None:
                issues.append(f"{evidence_id} read authorization timestamp is invalid")
            elif observed_at is not None and observed_at < read_authorized_at:
                issues.append(
                    f"{evidence_id} AWS-30 observation precedes read authorization"
                )
            if read_role != clean_cell(read_authority.get("role_or_profile", "")):
                issues.append(f"{evidence_id} read role does not match its receipt")
            if read_digest != clean_cell(read_authority.get("receipt_digest", "")):
                issues.append(f"{evidence_id} read receipt digest is tampered")
            if read_valid_until != clean_cell(read_authority.get("expiration", "")):
                issues.append(f"{evidence_id} read validity is tampered")
            expected_read_source = _format_deployment_read_provenance(
                clean_cell(read_authority.get("authority_source", "")),
                clean_cell(read_authority.get("authorized_at", "")),
                read_authority.get("resources", []),
                read_authority.get("operations", []),
            )
            if read_source != expected_read_source:
                issues.append(f"{evidence_id} read authority provenance is tampered")
            if expected_scope != read_scope:
                issues.append(f"{evidence_id} read account boundary is stale")
            if resources != list(read_authority.get("resources", [])):
                issues.append(
                    f"{evidence_id} attempted resources do not match read scope"
                )
            if not set(observed_reads).issubset(
                set(read_authority.get("operations", []))
            ):
                issues.append(
                    f"{evidence_id} observed reads exceed the read authorization"
                )
    if status == "COMPLETE":
        if not acceptance_ids:
            issues.append(f"{evidence_id} COMPLETE requires acceptance evidence IDs")
        else:
            issues.extend(
                _deployment_acceptance_evidence_issues(
                    str(expected.get("verify_text", "")), acceptance_ids, expected
                )
            )
    return issues


def _format_deployment_read_provenance(
    source: str,
    authorized_at: str,
    resources: Any,
    operations: Any,
) -> str:
    """Format the exact durable AWS-30 read-authorization envelope."""

    resource_values = list(resources) if isinstance(resources, (list, tuple)) else []
    operation_values = list(operations) if isinstance(operations, (list, tuple)) else []
    return (
        f"SOURCE: {clean_cell(source)}; AUTHORIZED_AT: {clean_cell(authorized_at)}; "
        f"RESOURCES: {', '.join(clean_cell(item) for item in resource_values)}; "
        f"OPERATIONS: {', '.join(clean_cell(item) for item in operation_values)}"
    )


def _parse_deployment_read_provenance(value: str) -> dict[str, Any] | None:
    """Parse one canonical AWS-30 envelope without reviving its authority."""

    cleaned = clean_cell(value)
    match = AWS_DEPLOYMENT_READ_PROVENANCE.fullmatch(cleaned)
    if match is None:
        return None
    source = clean_cell(match.group("source"))
    authorized_at = clean_cell(match.group("authorized_at"))
    try:
        resources = _deployment_values(
            match.group("resources"), "Read-authorized resources", allow_none=False
        )
        operations = _deployment_values(
            match.group("operations"), "Read-authorized operations", allow_none=False
        )
    except ValueError:
        return None
    if (
        not explicit_value(source, allow_none=False)
        or "*" in source
        or _iso_datetime(authorized_at) is None
        or any(AWS_READ_ONLY_OPERATION.fullmatch(item) is None for item in operations)
    ):
        return None
    canonical = _format_deployment_read_provenance(
        source, authorized_at, resources, operations
    )
    if cleaned != canonical:
        return None
    return {
        "source": source,
        "authorized_at": authorized_at,
        "resources": resources,
        "operations": operations,
    }


def _deployment_historical_authority_proof_issues(
    group: list[dict[str, str]],
    verify_text: str,
    *,
    gate_b_authority_source: str,
    gate_b_authorized_at: str,
) -> list[str]:
    """Prove a stale STARTED row followed its durable original authority."""

    first = group[0]
    issues: list[str] = []
    basis = clean_cell(first.get("REQ / DES / AUTH", ""))
    basis_match = re.fullmatch(
        r"REQ-\d{4,} / DES-\d{4,} / (?P<auth>AUTH-\d{4,})", basis
    )
    started_at = _iso_datetime(first.get("Observed at", ""))
    if basis_match is None or started_at is None:
        return ["historical deployment authorization timing proof is unavailable"]

    authorization_id = clean_cell(first.get("Deployment authorization", ""))
    receipt_digest = clean_cell(first.get("Deployment receipt digest", ""))
    authority_source = clean_cell(first.get("Deployment authority source", ""))
    if receipt_digest == "NONE":
        authorized_at = _iso_datetime(gate_b_authorized_at)
        if (
            authorization_id != basis_match.group("auth")
            or authorized_at is None
            or authority_source != clean_cell(gate_b_authority_source)
            or not explicit_value(authority_source, allow_none=False)
        ):
            issues.append(
                "historical fast-dev STARTED lacks its original Gate B authorization provenance"
            )
        elif started_at < authorized_at:
            issues.append(
                "historical deployment STARTED precedes its original authorization provenance"
            )
        return issues

    try:
        receipt = marked_receipt(verify_text, "aws-deployment")
        provenance = _action_authorization_rows(verify_text).get("Deployment")
    except ValueError:
        receipt = ""
        provenance = None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS DEPLOYMENT",
        AWS_DEPLOYMENT_RECEIPT_FIELDS,
        allow_none_fields=frozenset({"Rollback boundary"}),
    )
    if fields is None or provenance is None or unresolved(receipt):
        return [
            "historical explicit-gate STARTED lacks its durable original receipt and provenance"
        ]
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    receipt_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    receipt_resources_and_operations = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed operations']}"
    )
    authorized_at = _iso_datetime(provenance.get("Observed at", ""))
    binding_invalid = (
        fields["AWS authorization"] != authorization_id
        or fields["Construction authorization"] != basis_match.group("auth")
        or digest != receipt_digest
        or fields["Valid until"] != clean_cell(first.get("Deployment valid until", ""))
        or fields["Profile or role"]
        != clean_cell(first.get("Deployment role or profile", ""))
        or fields["Artifact digest"] != clean_cell(first.get("Artifact digest", ""))
        or fields["IaC plan/change-set binding"]
        != clean_cell(first.get("Plan/change-set binding", ""))
        or receipt_scope != clean_cell(first.get("Account / Region / environment", ""))
        or set(_split_authority_values(fields["Stack, application, and resources"]))
        != set(
            _deployment_values(
                first.get("Resources", ""), "Resources", allow_none=False
            )
        )
        or set(_split_authority_values(fields["Allowed operations"]))
        != set(
            _deployment_values(
                first.get("Mutation operations", ""),
                "Mutation operations",
                allow_none=False,
            )
        )
        or provenance.get("Authorization ID") != authorization_id
        or provenance.get("Construction AUTH") != basis_match.group("auth")
        or provenance.get("Role or profile") != fields["Profile or role"]
        or provenance.get("Artifact digest") != fields["Artifact digest"]
        or provenance.get("IaC plan/change-set binding")
        != fields["IaC plan/change-set binding"]
        or provenance.get("Account / Region / environment") != receipt_scope
        or provenance.get("Resources and operations")
        != receipt_resources_and_operations
        or clean_cell(provenance.get("Stable owner-message source", ""))
        != authority_source
        or provenance.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(provenance.get("Verbatim receipt SHA-256", "")) != digest
        or authorized_at is None
        or clean_cell(provenance.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or clean_cell(provenance.get("Result", ""))
        not in {"AUTHORIZED", "RUNNING", "READY"}
    )
    if binding_invalid:
        issues.append(
            "historical explicit-gate STARTED does not bind its durable original receipt and provenance"
        )
    elif started_at < authorized_at:
        issues.append(
            "historical deployment STARTED precedes its original authorization provenance"
        )
    return issues


def _deployment_historical_group_issues(
    group: list[dict[str, str]],
    verify_text: str,
    *,
    current_read_authority: Mapping[str, Any] | None = None,
    require_authorization_proof: bool = False,
    gate_b_authority_source: str = "",
    gate_b_authorized_at: str = "",
) -> list[str]:
    """Validate immutable historical rows without reviving their authority."""

    first = group[0]
    issues: list[str] = []
    scope = clean_cell(first.get("Account / Region / environment", ""))
    scope_match = re.fullmatch(
        r"ACCOUNT: (?P<account>[^;]+); REGION: (?P<region>[^;]+); "
        r"ENVIRONMENT: (?P<environment>[^;]+)",
        scope,
    )
    try:
        resources = _deployment_values(
            first.get("Resources", ""), "Resources", allow_none=False
        )
        operations = _deployment_values(
            first.get("Mutation operations", ""),
            "Mutation operations",
            allow_none=False,
        )
    except ValueError as exc:
        return [str(exc)]
    basis = clean_cell(first.get("REQ / DES / AUTH", ""))
    if re.fullmatch(r"REQ-\d{4,} / DES-\d{4,} / AUTH-\d{4,}", basis) is None:
        issues.append(
            "historical deployment attempt has a noncanonical REQ / DES / AUTH basis"
        )
    authorization_id = clean_cell(first.get("Deployment authorization", ""))
    digest = clean_cell(first.get("Deployment receipt digest", ""))
    deployment_valid_until = clean_cell(first.get("Deployment valid until", ""))
    deployment_source = clean_cell(first.get("Deployment authority source", ""))
    fast_dev = digest == "NONE"
    if fast_dev:
        if re.fullmatch(r"AUTH-\d{4,}", authorization_id) is None:
            issues.append("historical fast-dev attempt has noncanonical authority")
    elif (
        re.fullmatch(r"AWS-AUTH-\d{4,}", authorization_id) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
    ):
        issues.append("historical explicit-gate attempt has noncanonical authority")
    expires_at = _iso_datetime(deployment_valid_until)
    started_at = _iso_datetime(first.get("Observed at", ""))
    if fast_dev and expires_at is None:
        issues.append("historical fast-dev validity must be an ISO 8601 timestamp")
    elif (
        not fast_dev
        and deployment_valid_until != "ONE_OPERATION"
        and expires_at is None
    ):
        issues.append(
            "historical explicit-gate validity must be ISO 8601 or ONE_OPERATION"
        )
    elif started_at is not None and expires_at is not None and started_at > expires_at:
        issues.append("historical deployment STARTED occurred after authority expiry")
    if (
        not explicit_value(deployment_source, allow_none=False)
        or "*" in deployment_source
    ):
        issues.append("historical deployment authority source is unresolved")
    if scope_match is None:
        issues.append("historical deployment attempt has a noncanonical account scope")
        account = region = environment = "NONE"
    else:
        account = clean_cell(scope_match.group("account"))
        region = clean_cell(scope_match.group("region"))
        environment = clean_cell(scope_match.group("environment"))
        for label, value in (
            ("account", account),
            ("Region", region),
            ("environment", environment),
        ):
            if not explicit_value(value, allow_none=False) or "*" in value:
                issues.append(
                    f"historical deployment {label} must be concrete and wildcard-free"
                )
    deployment_role = clean_cell(first.get("Deployment role or profile", ""))
    artifact = clean_cell(first.get("Artifact digest", ""))
    plan = clean_cell(first.get("Plan/change-set binding", ""))
    if not explicit_value(deployment_role, allow_none=False) or "*" in deployment_role:
        issues.append(
            "historical deployment attempt requires a concrete deployment role"
        )
    if re.fullmatch(r"sha256:[0-9a-f]{64}", artifact) is None:
        issues.append("historical deployment attempt requires an exact artifact digest")
    if fast_dev:
        if not explicit_value(plan, allow_none=False) or "*" in plan:
            issues.append("historical fast-dev attempt requires an exact plan binding")
    elif AWS_PLAN_BINDING.fullmatch(plan) is None:
        issues.append(
            "historical explicit-gate attempt requires a canonical plan binding"
        )
    expected = {
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "valid_until": deployment_valid_until,
        "deployment_authority_source": deployment_source,
        "deployment_role": deployment_role,
        "artifact": artifact,
        "plan": plan,
        "account": account,
        "region": region,
        "environment": environment,
        "resources": resources,
        "operations": operations,
        "verify_text": verify_text,
    }
    if require_authorization_proof:
        issues.extend(
            _deployment_historical_authority_proof_issues(
                group,
                verify_text,
                gate_b_authority_source=gate_b_authority_source,
                gate_b_authorized_at=gate_b_authorized_at,
            )
        )
    for row in group:
        issues.extend(
            _deployment_row_binding_issues(
                row,
                expected,
                current_read_authority,
                historical=current_read_authority is None,
            )
        )
    return issues


def _deployment_group_projection(
    base: Mapping[str, Any],
    attempt_id: str,
    group: list[dict[str, str]],
) -> dict[str, Any]:
    action_rows = [row for row in group if row["Phase"] == "AWS-20"]
    terminal_rows = [
        row for row in action_rows if row["Status"] in AWS_DEPLOYMENT_TERMINAL_STATUSES
    ]
    action = terminal_rows[0] if terminal_rows else action_rows[0]
    reconciliation_rows = [row for row in group if row["Phase"] == "AWS-30"]
    reconciliation = reconciliation_rows[-1] if reconciliation_rows else None
    latest = reconciliation or action
    try:
        resources = _deployment_values(
            latest["Resources"], "Resources", allow_none=False
        )
        operations = _deployment_values(
            latest["Mutation operations"],
            "Mutation operations",
            allow_none=False,
        )
        observed_reads = (
            _deployment_values(
                latest["Read operations observed"],
                "Read operations observed",
                allow_none=latest["Status"] == "STALE",
            )
            if latest["Phase"] == "AWS-30"
            else []
        )
        acceptance_ids = (
            _deployment_evidence_ids(
                latest["Acceptance evidence IDs"],
                allow_none=latest["Status"] != "COMPLETE",
            )
            if latest["Phase"] == "AWS-30"
            else []
        )
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    reconciliation_status = (
        clean_cell(reconciliation["Status"]) if reconciliation else "NONE"
    )
    read_provenance = (
        _parse_deployment_read_provenance(latest["Read authority source"])
        if latest["Phase"] == "AWS-30"
        else None
    )
    status = (
        "ACTION_TERMINAL_REQUIRED"
        if clean_cell(action["Status"]) == "STARTED" and reconciliation is None
        else {
            "COMPLETE": "RECONCILED",
            "BLOCKED": "BLOCKED",
            "STALE": "RECONCILIATION_REQUIRED",
            "NONE": "RECONCILIATION_REQUIRED",
        }[reconciliation_status]
    )
    return {
        **base,
        "status": status,
        "attempt_id": attempt_id,
        "evidence_id": clean_cell(latest["Evidence ID"]),
        "phase": clean_cell(latest["Phase"]),
        "action_status": clean_cell(action["Status"]),
        "reconciliation_status": reconciliation_status,
        "deployment_authorization": clean_cell(latest["Deployment authorization"]),
        "deployment_receipt_digest": clean_cell(latest["Deployment receipt digest"]),
        "deployment_valid_until": clean_cell(latest["Deployment valid until"]),
        "deployment_authority_source": clean_cell(
            latest["Deployment authority source"]
        ),
        "read_authorization": clean_cell(latest["Read authorization"]),
        "deployment_role_or_profile": clean_cell(latest["Deployment role or profile"]),
        "read_role_or_profile": clean_cell(latest["Read role or profile"]),
        "read_receipt_digest": clean_cell(latest["Read receipt digest"]),
        "read_valid_until": clean_cell(latest["Read valid until"]),
        "read_authorized_at": (
            read_provenance["authorized_at"] if read_provenance else "NONE"
        ),
        "read_authorized_resources": (
            read_provenance["resources"] if read_provenance else []
        ),
        "read_authorized_operations": (
            read_provenance["operations"] if read_provenance else []
        ),
        "read_authority_source": clean_cell(latest["Read authority source"]),
        "artifact_digest": clean_cell(latest["Artifact digest"]),
        "plan_binding": clean_cell(latest["Plan/change-set binding"]),
        "resources": resources,
        "mutation_operations": operations,
        "read_operations_observed": observed_reads,
        "acceptance_evidence_ids": acceptance_ids,
        "operation_result": clean_cell(
            latest["Operation identifiers and direct result"]
        ),
        "rollback_result": clean_cell(latest["Rollback result"]),
        "identity_and_boundary_match": clean_cell(
            latest["Identity and boundary match"]
        ),
        "blocker_or_stale_reason": clean_cell(latest["Blocker or stale reason"]),
    }


def _deployment_authority_timing_issues(
    group: list[dict[str, str]], expected: Mapping[str, Any]
) -> list[str]:
    """Validate that mutation began within the exact recorded authority window."""

    issues: list[str] = []
    started_at = _iso_datetime(group[0].get("Observed at", ""))
    authorized_at = _iso_datetime(expected.get("authorized_at", ""))
    valid_until = clean_cell(expected.get("valid_until", ""))
    expires_at = None if valid_until == "ONE_OPERATION" else _iso_datetime(valid_until)
    if started_at is None:
        issues.append("deployment STARTED timestamp is invalid")
    if authorized_at is None:
        issues.append("deployment authorization timestamp is invalid")
    elif started_at is not None and started_at < authorized_at:
        issues.append("deployment STARTED precedes its authorization provenance")
    if valid_until != "ONE_OPERATION" and expires_at is None:
        issues.append("deployment authority has a noncanonical validity boundary")
    elif started_at is not None and expires_at is not None and started_at > expires_at:
        issues.append("deployment STARTED occurred after authority expiry")
    return issues


def derive_deployment_sequence_state(
    verify_text: str,
    read_authority: Mapping[str, Any] | None,
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    envelope: Mapping[str, str],
    lane: str | None,
    artifact_binding: str,
    release_evidence_cutoff: str = "NONE",
    release_state: str = "READY_TO_DEPLOY",
    gate_b_authority_source: str = "",
    gate_b_authorized_at: str = "",
    cost_posture: str = "",
    restricted_closure: bool = False,
) -> dict[str, Any]:
    """Derive AWS-20/AWS-30 sequencing without inferring an attempted action."""

    base: dict[str, Any] = {
        "status": "NOT_ACTIVE",
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "phase": "NONE",
        "action_status": "NONE",
        "reconciliation_status": "NONE",
        "deployment_authorization": "NONE",
        "deployment_receipt_digest": "NONE",
        "deployment_valid_until": "NONE",
        "deployment_authority_source": "NONE",
        "read_authorization": "NONE",
        "deployment_role_or_profile": "NONE",
        "read_role_or_profile": "NONE",
        "read_receipt_digest": "NONE",
        "read_valid_until": "NONE",
        "read_authorized_at": "NONE",
        "read_authorized_resources": [],
        "read_authorized_operations": [],
        "read_authority_source": "NONE",
        "artifact_digest": "NONE",
        "plan_binding": "NONE",
        "resources": [],
        "mutation_operations": [],
        "read_operations_observed": [],
        "acceptance_evidence_ids": [],
        "operation_result": "NONE",
        "rollback_result": "NONE",
        "identity_and_boundary_match": "NONE",
        "blocker_or_stale_reason": "NONE",
        "basis_stale": False,
        "acknowledged": False,
        "acknowledged_evidence_id": "NONE",
        "release_evidence_cutoff": release_evidence_cutoff,
        "current_mutation_authority_status": "UNAVAILABLE",
        "issues": [],
    }
    try:
        rows = parse_deployment_reconciliation_evidence(verify_text)
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    concrete: list[dict[str, str]] = []
    invalid_identifiers: list[str] = []
    for row in rows:
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id):
            concrete.append(row)
            continue
        status = clean_cell(row.get("Status", ""))
        placeholder = (
            unresolved(evidence_id)
            and status in {"", "NOT_STARTED"}
            and all(
                unresolved(row.get(header, ""))
                for header in AWS_DEPLOYMENT_EVIDENCE_HEADERS
                if header not in {"Evidence ID", "Status"}
            )
        )
        if not placeholder:
            invalid_identifiers.append(evidence_id or "EMPTY")
    if invalid_identifiers:
        return {
            **base,
            "status": "BLOCKED",
            "issues": [
                "AWS deployment evidence has noncanonical or partially populated IDs: "
                + ", ".join(sorted(invalid_identifiers))
            ],
        }
    if not concrete:
        return base
    evidence_ids = [clean_cell(row["Evidence ID"]) for row in concrete]
    if len(evidence_ids) != len(set(evidence_ids)):
        return {
            **base,
            "status": "BLOCKED",
            "issues": ["AWS deployment evidence contains duplicate Evidence IDs"],
        }
    structural_issues: list[str] = []
    timestamps: list[datetime] = []
    groups: dict[str, list[dict[str, str]]] = {}
    attempt_order: list[str] = []
    closed_attempts: set[str] = set()
    active_attempt = ""
    for row in concrete:
        evidence_id = clean_cell(row["Evidence ID"])
        attempt_id = clean_cell(row.get("Attempt ID", ""))
        phase = clean_cell(row.get("Phase", ""))
        status = clean_cell(row.get("Status", ""))
        observed_at = _iso_datetime(row.get("Observed at", ""))
        if AWS_DEPLOYMENT_ATTEMPT_ID.fullmatch(attempt_id) is None:
            structural_issues.append(f"{evidence_id} has a noncanonical Attempt ID")
        if phase == "AWS-20" and status not in AWS_DEPLOYMENT_ACTION_STATUSES:
            structural_issues.append(
                f"{evidence_id} has invalid AWS-20 status {status or 'EMPTY'}"
            )
        elif phase == "AWS-30" and status not in AWS_DEPLOYMENT_RECONCILIATION_STATUSES:
            structural_issues.append(
                f"{evidence_id} has invalid AWS-30 status {status or 'EMPTY'}"
            )
        elif phase not in {"AWS-20", "AWS-30"}:
            structural_issues.append(
                f"{evidence_id} phase must be exactly AWS-20 or AWS-30"
            )
        if observed_at is None:
            structural_issues.append(
                f"{evidence_id} Observed at must be ISO 8601 with timezone"
            )
        else:
            timestamps.append(observed_at)
        if attempt_id != active_attempt:
            if attempt_id in closed_attempts:
                structural_issues.append(
                    f"{evidence_id} reopens a noncontiguous deployment attempt"
                )
            if active_attempt:
                closed_attempts.add(active_attempt)
            active_attempt = attempt_id
            attempt_order.append(attempt_id)
        groups.setdefault(attempt_id, []).append(row)
    if len(timestamps) != len(set(timestamps)):
        structural_issues.append("AWS deployment evidence timestamps must be unique")
    if len(timestamps) == len(concrete) and timestamps != sorted(timestamps):
        structural_issues.append(
            "AWS deployment evidence must be appended in observed-time order"
        )
    replayed_authorization_ids: set[str] = set()
    replayed_receipt_digests: set[str] = set()
    for index, attempt_id in enumerate(attempt_order):
        group = groups.get(attempt_id, [])
        started = [
            row
            for row in group
            if row.get("Phase") == "AWS-20" and row.get("Status") == "STARTED"
        ]
        terminal = [
            row
            for row in group
            if row.get("Phase") == "AWS-20"
            and row.get("Status") in AWS_DEPLOYMENT_TERMINAL_STATUSES
        ]
        reconciliations = [row for row in group if row.get("Phase") == "AWS-30"]
        if len(started) != 1 or not group or group[0] not in started:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} requires exactly one first AWS-20 STARTED row"
            )
        if len(terminal) > 1:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} has more than one AWS-20 terminal row"
            )
        if reconciliations and len(terminal) != 1:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} AWS-30 requires one prior AWS-20 terminal row"
            )
        elif reconciliations:
            terminal_index = group.index(terminal[0])
            if any(group.index(row) < terminal_index for row in reconciliations):
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} AWS-30 must follow the AWS-20 terminal row"
                )
        stale_reconciliations = [
            row for row in reconciliations if row.get("Status") == "STALE"
        ]
        terminal_reconciliations = [
            row
            for row in reconciliations
            if row.get("Status") in {"COMPLETE", "BLOCKED"}
        ]
        if (
            len(reconciliations) > 2
            or len(stale_reconciliations) > 1
            or len(terminal_reconciliations) > 1
        ):
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} exceeds the bounded AWS-30 retry sequence"
            )
        if len(reconciliations) == 2:
            if reconciliations[0].get("Status") != "STALE" or reconciliations[1].get(
                "Status"
            ) not in {"COMPLETE", "BLOCKED"}:
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} AWS-30 recovery must be STALE then terminal"
                )
            if clean_cell(
                reconciliations[0].get("Read authorization", "")
            ) == clean_cell(reconciliations[1].get("Read authorization", "")):
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} AWS-30 recovery requires a fresh read authorization"
                )
        if reconciliations and group[-1] not in reconciliations:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} AWS-30 reconciliation must be last"
            )
        immutable_fields = (
            "REQ / DES / AUTH",
            "Deployment authorization",
            "Deployment receipt digest",
            "Deployment valid until",
            "Deployment authority source",
            "Deployment role or profile",
            "Artifact digest",
            "Plan/change-set binding",
            "Resources",
            "Mutation operations",
            "Account / Region / environment",
        )
        if group:
            first = group[0]
            for row in group[1:]:
                for field_name in immutable_fields:
                    if clean_cell(row.get(field_name, "")) != clean_cell(
                        first.get(field_name, "")
                    ):
                        structural_issues.append(
                            f"{attempt_id or 'EMPTY'} changes immutable {field_name}"
                        )
        authority_row = started[0] if started else group[0]
        authorization_id = clean_cell(authority_row.get("Deployment authorization", ""))
        receipt_digest = clean_cell(authority_row.get("Deployment receipt digest", ""))
        if authorization_id in replayed_authorization_ids:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} replays a deployment authorization ID"
            )
        replayed_authorization_ids.add(authorization_id)
        if receipt_digest != "NONE":
            if receipt_digest in replayed_receipt_digests:
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} replays a deployment receipt digest"
                )
            replayed_receipt_digests.add(receipt_digest)
        if index < len(attempt_order) - 1:
            if not terminal_reconciliations:
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} was not reconciled before the next attempt"
                )
    if structural_issues:
        return {**base, "status": "BLOCKED", "issues": structural_issues}

    deployment_rows_by_id = {clean_cell(row["Evidence ID"]): row for row in concrete}
    if re.fullmatch(r"EV-\d{4,}", release_evidence_cutoff):
        cutoff_row = deployment_rows_by_id.get(release_evidence_cutoff)
        try:
            verification_rows = parse_verification_matrix(verify_text)
        except ValueError as exc:
            return {**base, "status": "BLOCKED", "issues": [str(exc)]}
        verification_matches = [
            row
            for row in verification_rows
            if clean_cell(row.get("Evidence ID", "")) == release_evidence_cutoff
        ]
        if (1 if cutoff_row is not None else 0) + len(verification_matches) != 1:
            return {
                **base,
                "status": "BLOCKED",
                "issues": [
                    "Active evidence cutoff must resolve exactly once across the "
                    "deployment journal and Verification matrix"
                ],
            }
        if cutoff_row is not None and not (
            cutoff_row.get("Phase") == "AWS-30"
            and cutoff_row.get("Status") in {"COMPLETE", "BLOCKED"}
        ):
            return {
                **base,
                "status": "BLOCKED",
                "issues": ["Active evidence cutoff names a nonterminal deployment row"],
            }

    if len(attempt_order) > 1:
        previous_group = groups[attempt_order[-2]]
        previous_terminal = next(
            (
                row
                for row in reversed(previous_group)
                if row.get("Phase") == "AWS-30"
                and row.get("Status") in {"COMPLETE", "BLOCKED"}
            ),
            None,
        )
        latest_group = groups[attempt_order[-1]]
        latest_terminal = next(
            (
                row
                for row in reversed(latest_group)
                if row.get("Phase") == "AWS-30"
                and row.get("Status") in {"COMPLETE", "BLOCKED"}
            ),
            None,
        )
        allowed_cutoffs = (
            {clean_cell(previous_terminal.get("Evidence ID", ""))}
            if previous_terminal is not None
            else set()
        )
        if latest_terminal is not None:
            allowed_cutoffs.add(clean_cell(latest_terminal.get("Evidence ID", "")))
        if release_evidence_cutoff not in allowed_cutoffs:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_order[-1],
                "issues": [
                    "A later deployment attempt requires the prior terminal "
                    "AWS-30 evidence cutoff acknowledged by RELEASE-10"
                ],
            }

    for historical_attempt_id in attempt_order[:-1]:
        historical_issues = _deployment_historical_group_issues(
            groups[historical_attempt_id], verify_text
        )
        if historical_issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": historical_attempt_id,
                "issues": historical_issues,
            }

    expected_basis = (
        f"{requirements_revision} / {design_revision} / {construction_authorization}"
    )
    attempt_id = attempt_order[-1]
    group = groups[attempt_id]
    projection = _deployment_group_projection(base, attempt_id, group)
    terminal_reconciliation = next(
        (
            row
            for row in reversed(group)
            if row.get("Phase") == "AWS-30"
            and row.get("Status") in {"COMPLETE", "BLOCKED"}
        ),
        None,
    )
    if terminal_reconciliation is not None:
        terminal_id = clean_cell(terminal_reconciliation["Evidence ID"])
        if (
            release_state != "READY_TO_DEPLOY"
            and release_evidence_cutoff != terminal_id
        ):
            return {
                **projection,
                "status": "BLOCKED",
                "issues": [
                    "Post-reconciliation release state requires the exact terminal AWS-30 evidence cutoff"
                ],
            }
        acknowledged = release_evidence_cutoff == terminal_id
        terminal_basis_stale = False
        if acknowledged:
            allowed_release_states = (
                {"NOT_READY"}
                if clean_cell(terminal_reconciliation.get("Status", "")) == "BLOCKED"
                or clean_cell(group[0].get("REQ / DES / AUTH", "")) != expected_basis
                else {"NOT_READY", "RELEASE_VERIFIED"}
            )
            if release_state not in allowed_release_states:
                return {
                    **projection,
                    "status": "BLOCKED",
                    "basis_stale": (
                        clean_cell(group[0].get("REQ / DES / AUTH", ""))
                        != expected_basis
                    ),
                    "issues": [
                        "Terminal AWS-30 acknowledgement must update release state "
                        "and evidence cutoff together within the reconciliation result"
                    ],
                }
            terminal_issues = _deployment_historical_group_issues(group, verify_text)
        else:
            terminal_basis_stale = (
                clean_cell(group[0].get("REQ / DES / AUTH", "")) != expected_basis
            )
            restricted_read = restricted_closure or terminal_basis_stale
            terminal_read_authority = None if restricted_read else read_authority
            if terminal_read_authority is None:
                terminal_read_authority = _deployment_reconciliation_read_authority(
                    verify_text,
                    cost_posture,
                    group,
                    allow_expired=restricted_read,
                    require_post_action_freshness=restricted_read,
                )
            current_expected, current_binding_issues = _deployment_expected_binding(
                verify_text,
                construction_authorization=construction_authorization,
                envelope=envelope,
                lane=lane,
                artifact_binding=artifact_binding,
                gate_b_authority_source=gate_b_authority_source,
                gate_b_authorized_at=gate_b_authorized_at,
            )
            group_key = (
                clean_cell(group[0].get("Deployment authorization", "")),
                clean_cell(group[0].get("Deployment receipt digest", "")),
            )
            current_key = (
                clean_cell(current_expected.get("authorization_id", "")),
                clean_cell(current_expected.get("receipt_digest", "")),
            )
            if terminal_basis_stale:
                terminal_issues = _deployment_historical_group_issues(
                    group,
                    verify_text,
                    current_read_authority=terminal_read_authority,
                    require_authorization_proof=True,
                    gate_b_authority_source=gate_b_authority_source,
                    gate_b_authorized_at=gate_b_authorized_at,
                )
            else:
                terminal_issues = list(current_binding_issues)
                terminal_issues.extend(
                    _deployment_authority_timing_issues(group, current_expected)
                )
                for row in group:
                    terminal_issues.extend(
                        _deployment_row_binding_issues(
                            row,
                            current_expected,
                            terminal_read_authority,
                        )
                    )
            if terminal_read_authority is None:
                terminal_issues.append(
                    "Unacknowledged terminal AWS-30 evidence requires its exact marked read receipt"
                )
        if terminal_issues:
            return {
                **projection,
                "status": "BLOCKED",
                "basis_stale": terminal_basis_stale,
                "issues": terminal_issues,
            }
        current_expected, current_issues = _deployment_expected_binding(
            verify_text,
            construction_authorization=construction_authorization,
            envelope=envelope,
            lane=lane,
            artifact_binding=artifact_binding,
            gate_b_authority_source=gate_b_authority_source,
            gate_b_authorized_at=gate_b_authorized_at,
        )
        consumed_key = (
            clean_cell(group[0].get("Deployment authorization", "")),
            clean_cell(group[0].get("Deployment receipt digest", "")),
        )
        current_key = (
            clean_cell(current_expected.get("authorization_id", "")),
            clean_cell(current_expected.get("receipt_digest", "")),
        )
        if current_issues or not all(current_key):
            authority_status = "UNAVAILABLE"
        elif current_key == consumed_key:
            authority_status = "CONSUMED"
        else:
            authority_status = "FRESH"
        return {
            **projection,
            "status": "CONSUMED" if acknowledged else projection["status"],
            "acknowledged": acknowledged,
            "acknowledged_evidence_id": terminal_id if acknowledged else "NONE",
            "release_evidence_cutoff": release_evidence_cutoff,
            "current_mutation_authority_status": authority_status,
            "basis_stale": terminal_basis_stale,
        }

    group_basis = clean_cell(group[0].get("REQ / DES / AUTH", ""))
    basis_stale = group_basis != expected_basis
    reconciliation_read_authority = None
    if projection.get("status") == "RECONCILIATION_REQUIRED":
        restricted_read = restricted_closure or basis_stale
        reconciliation_read_authority = None if restricted_read else read_authority
        if reconciliation_read_authority is None:
            reconciliation_read_authority = _deployment_reconciliation_read_authority(
                verify_text,
                cost_posture,
                group,
                allow_expired=restricted_read,
                require_post_action_freshness=restricted_read,
            )
        elif not restricted_read:
            reconciliation_read_authority = {
                **dict(reconciliation_read_authority),
                "reconciliation_only": False,
                "attempt_id": attempt_id,
            }
    if basis_stale:
        historical_issues = _deployment_historical_group_issues(
            group,
            verify_text,
            current_read_authority=(
                reconciliation_read_authority
                if any(row.get("Phase") == "AWS-30" for row in group)
                else None
            ),
            require_authorization_proof=True,
            gate_b_authority_source=gate_b_authority_source,
            gate_b_authorized_at=gate_b_authorized_at,
        )
        if historical_issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "basis_stale": True,
                "issues": historical_issues,
            }
        if projection.get("status") == "ACTION_TERMINAL_REQUIRED":
            return {**projection, "basis_stale": True}
        return {
            **projection,
            "status": "RECONCILIATION_REQUIRED",
            "basis_stale": True,
            "reconciliation_read_authority": (
                dict(reconciliation_read_authority)
                if reconciliation_read_authority is not None
                else {}
            ),
            "blocker_or_stale_reason": (
                projection.get("blocker_or_stale_reason")
                if projection.get("reconciliation_status") == "STALE"
                else "Current REQ / DES / AUTH differs from the attempted action"
            ),
        }

    expected, binding_issues = _deployment_expected_binding(
        verify_text,
        construction_authorization=construction_authorization,
        envelope=envelope,
        lane=lane,
        artifact_binding=artifact_binding,
        gate_b_authority_source=gate_b_authority_source,
        gate_b_authorized_at=gate_b_authorized_at,
    )
    group_key = (
        clean_cell(group[0].get("Deployment authorization", "")),
        clean_cell(group[0].get("Deployment receipt digest", "")),
    )
    expected_key = (
        clean_cell(expected.get("authorization_id", "")),
        clean_cell(expected.get("receipt_digest", "")),
    )
    if group_key != expected_key:
        historical_issues = _deployment_historical_group_issues(
            group,
            verify_text,
            require_authorization_proof=True,
            gate_b_authority_source=gate_b_authority_source,
            gate_b_authorized_at=gate_b_authorized_at,
        )
        if historical_issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "issues": historical_issues,
            }
        return {
            **projection,
            "reconciliation_read_authority": (
                dict(reconciliation_read_authority)
                if reconciliation_read_authority is not None
                else {}
            ),
        }
    binding_issues.extend(_deployment_authority_timing_issues(group, expected))
    for row in group:
        if clean_cell(row.get("REQ / DES / AUTH", "")) != expected_basis:
            binding_issues.append(
                f"{row['Evidence ID']} does not match current REQ / DES / AUTH"
            )
        binding_issues.extend(
            _deployment_row_binding_issues(row, expected, reconciliation_read_authority)
        )
    if binding_issues:
        return {
            **base,
            "status": "BLOCKED",
            "attempt_id": attempt_id,
            "issues": binding_issues,
        }
    return {
        **projection,
        "reconciliation_read_authority": (
            dict(reconciliation_read_authority)
            if reconciliation_read_authority is not None
            else {}
        ),
    }


def _teardown_values(value: str, label: str, *, allow_none: bool) -> list[str]:
    cleaned = clean_cell(value)
    if allow_none and cleaned == "NONE":
        return []
    values = _split_authority_values(cleaned)
    if (
        not values
        or len(values) != len(set(values))
        or any("*" in item for item in values)
    ):
        raise ValueError(f"{label} must be a unique wildcard-free exact list")
    return values


def _teardown_receipt_row_issues(
    row: Mapping[str, str],
    verify_text: str,
    *,
    construction_authorization: str,
    envelope: Mapping[str, str],
    require_row_role_match: bool = True,
    historical: bool = False,
) -> tuple[dict[str, str] | None, str, list[str]]:
    """Validate one evidence row against the exact current teardown receipt."""

    try:
        receipt = marked_receipt(verify_text, "aws-teardown")
    except ValueError:
        receipt = ""
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS TEARDOWN",
        AWS_TEARDOWN_RECEIPT_FIELDS,
        allow_none_fields=frozenset(
            {"Resources and data to retain", "Shared dependencies"}
        ),
    )
    provenance = _action_authorization_rows(verify_text).get("Teardown")
    digest = (
        "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        if receipt
        else "NONE"
    )
    issues: list[str] = []
    if fields is None or provenance is None or unresolved(receipt):
        return (
            None,
            digest,
            ["evidence requires one exact owner-authored teardown receipt"],
        )
    action_authorization = clean_cell(row.get("Teardown authorization", ""))
    action_digest = clean_cell(row.get("Teardown receipt digest", ""))
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    if (
        action_authorization != fields["Teardown authorization"]
        or action_digest != digest
        or fields["Construction authorization"] != construction_authorization
        or (
            require_row_role_match
            and fields["Profile or role"] != clean_cell(row.get("Role or profile", ""))
        )
        or fields["Stack, application, and resources to remove"]
        != clean_cell(row.get("Resources proposed to remove", ""))
        or fields["Resources and data to retain"]
        != clean_cell(row.get("Resources retained", ""))
        or fields["Allowed deletion operations"]
        != clean_cell(row.get("Allowed deletion operations", ""))
        or fields["Shared dependencies"]
        != clean_cell(row.get("Shared dependencies", ""))
        or fields["Cost effect"] != clean_cell(row.get("Cost effect", ""))
        or fields["Post-teardown verification"]
        != clean_cell(row.get("Post-teardown verification", ""))
        or clean_cell(row.get("Account / Region / environment", "")) != expected_scope
        or (not historical and not _receipt_identity_matches_gate_b(fields, envelope))
        or provenance.get("Authorization ID") != action_authorization
        or provenance.get("Construction AUTH") != construction_authorization
        or provenance.get("Role or profile") != fields["Profile or role"]
        or provenance.get("Account / Region / environment") != expected_scope
        or provenance.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(provenance.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(provenance.get("Stable owner-message source", ""))
        or not explicit_timestamp(provenance.get("Observed at", ""))
        or clean_cell(provenance.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or clean_cell(provenance.get("Result", ""))
        not in {"AUTHORIZED", "RUNNING", "READY"}
    ):
        issues.append("evidence does not bind the exact teardown receipt")
    return fields, digest, issues


def _teardown_action_attempt_row_issues(
    row: Mapping[str, str],
    envelope: Mapping[str, str],
    *,
    historical: bool = False,
) -> list[str]:
    """Validate one direct AWS-50 STARTED or terminal journal row."""

    issues: list[str] = []
    status = clean_cell(row.get("Status", ""))
    if status not in AWS_TEARDOWN_ACTION_STATUSES:
        return ["matching AWS-50 attempt has an invalid action status"]
    try:
        resources = _teardown_values(
            row.get("Resources proposed to remove", ""),
            "Resources proposed to remove",
            allow_none=False,
        )
        operations = _teardown_values(
            row.get("Allowed deletion operations", ""),
            "Allowed deletion operations",
            allow_none=False,
        )
        retained = _teardown_values(
            row.get("Resources retained", ""), "Resources retained", allow_none=True
        )
        shared = _teardown_values(
            row.get("Shared dependencies", ""), "Shared dependencies", allow_none=True
        )
        removed = _teardown_values(
            row.get("Resources removed", ""), "Resources removed", allow_none=True
        )
        residuals = _teardown_values(
            row.get("Residual resources", ""), "Residual resources", allow_none=True
        )
    except ValueError as exc:
        return [str(exc)]
    if not historical and not _receipt_scope_within_gate_b(
        resources, operations, envelope
    ):
        issues.append("matching AWS-50 attempt exceeds Gate B")
    if (
        set(resources).intersection(retained)
        or set(resources).intersection(shared)
        or set(retained).intersection(shared)
    ):
        issues.append("matching AWS-50 removal, retention, and shared sets overlap")
    for field_name, allow_none in (
        ("Expected manifest or stack", False),
        ("Cost effect", False),
        ("Post-teardown verification", False),
        ("Stack events and terminal status", False),
        ("Resources removed", True),
        ("Snapshots and backups", True),
        ("Residual resources", True),
        ("Inventory or discovery limits", False),
    ):
        if not explicit_value(row.get(field_name, ""), allow_none=allow_none):
            issues.append(f"matching AWS-50 attempt requires {field_name}")
    if clean_cell(row.get("Identity and boundary match", "")) not in {
        "PASS",
        "VERIFIED",
    }:
        issues.append("matching AWS-50 attempt requires verified identity and boundary")
    direct_fields = (
        "Stack events and terminal status",
        "Resources removed",
        "Snapshots and backups",
        "Residual resources",
        "Inventory or discovery limits",
    )
    if status == "STARTED":
        if (
            clean_cell(row.get("Stack events and terminal status", ""))
            != AWS_TEARDOWN_PRECALL_RESULT
        ):
            issues.append("AWS-50 STARTED must use the exact pre-call sentinel")
        if (
            clean_cell(row.get("Inventory or discovery limits", ""))
            != AWS_TEARDOWN_PRECALL_RESULT
        ):
            issues.append(
                "AWS-50 STARTED inventory must use the exact pre-call sentinel"
            )
        for field_name in (
            "Resources removed",
            "Snapshots and backups",
            "Residual resources",
        ):
            if clean_cell(row.get(field_name, "")) != "NONE":
                issues.append(f"AWS-50 STARTED must use {field_name} = NONE")
        return issues
    if any(
        clean_cell(row.get(field_name, "")) == AWS_TEARDOWN_PRECALL_RESULT
        for field_name in direct_fields
    ):
        issues.append("AWS-50 terminal evidence cannot reuse the pre-call sentinel")
    if status == "SUCCEEDED":
        if residuals:
            issues.append("matching SUCCEEDED AWS-50 attempt cannot retain residuals")
        if set(removed) != set(resources):
            issues.append(
                "matching SUCCEEDED AWS-50 attempt must reconcile every removal"
            )
    return issues


def _teardown_basis_authorization(row: Mapping[str, str]) -> str | None:
    parts = [
        clean_cell(item)
        for item in clean_cell(row.get("REQ / DES / AUTH", "")).split(" / ")
    ]
    if (
        len(parts) != 3
        or re.fullmatch(r"REQ-\d{4,}", parts[0]) is None
        or re.fullmatch(r"DES-\d{4,}", parts[1]) is None
        or re.fullmatch(r"AUTH-\d{4,}", parts[2]) is None
    ):
        return None
    return parts[2]


def _teardown_attempt_timing_issues(
    started: Mapping[str, str], fields: Mapping[str, str], provenance: Mapping[str, str]
) -> list[str]:
    """Prove the one-operation receipt was current when STARTED was appended."""

    issues: list[str] = []
    started_at = _iso_datetime(started.get("Observed at", ""))
    authorized_at = _iso_datetime(provenance.get("Observed at", ""))
    valid_until = clean_cell(fields.get("Valid until", ""))
    expires_at = None if valid_until == "ONE_OPERATION" else _iso_datetime(valid_until)
    if started_at is None:
        issues.append("teardown STARTED timestamp is invalid")
    if authorized_at is None:
        issues.append("teardown authorization timestamp is invalid")
    elif started_at is not None and started_at < authorized_at:
        issues.append("teardown STARTED precedes its authorization provenance")
    if valid_until != "ONE_OPERATION" and expires_at is None:
        issues.append("teardown authority has a noncanonical validity boundary")
    elif started_at is not None and expires_at is not None and started_at > expires_at:
        issues.append("teardown STARTED occurred after authority expiry")
    return issues


def _teardown_read_row_issues(
    row: Mapping[str, str],
    authority: Mapping[str, Any] | None,
    *,
    require_authority: bool,
    require_exact_scope: bool = False,
) -> list[str]:
    """Validate durable AWS-40 read provenance without reviving old authority."""

    evidence_id = clean_cell(row.get("Evidence ID", "")) or "AWS-40 row"
    read_id = clean_cell(row.get("Read authorization", ""))
    read_role = clean_cell(row.get("Read role or profile", ""))
    read_digest = clean_cell(row.get("Read receipt digest", ""))
    read_valid_until = clean_cell(row.get("Read valid until", ""))
    read_source_proof = clean_cell(row.get("Read authority source", ""))
    source_match = AWS_TEARDOWN_READ_PROVENANCE.fullmatch(read_source_proof)
    read_source = clean_cell(source_match.group("source")) if source_match else ""
    read_authorized_at_value = (
        clean_cell(source_match.group("authorized_at")) if source_match else ""
    )
    observed_at = _iso_datetime(row.get("Observed at", ""))
    read_authorized_at = _iso_datetime(read_authorized_at_value)
    expires_at = _iso_datetime(read_valid_until)
    issues: list[str] = []
    if AWS_READ_AUTHORIZATION_ID.fullmatch(read_id) is None:
        issues.append(f"{evidence_id} AWS-40 requires a canonical read authorization")
    if not explicit_value(read_role, allow_none=False) or "*" in read_role:
        issues.append(f"{evidence_id} AWS-40 requires a concrete read role")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", read_digest) is None:
        issues.append(f"{evidence_id} AWS-40 requires an exact read receipt digest")
    if read_valid_until == "ONE_OPERATION" or expires_at is None:
        issues.append(f"{evidence_id} AWS-40 requires reusable ISO read validity")
    elif observed_at is not None and observed_at > expires_at:
        issues.append(f"{evidence_id} AWS-40 was observed after read authority expiry")
    if (
        source_match is None
        or not explicit_value(read_source, allow_none=False)
        or "*" in read_source
        or read_authorized_at is None
    ):
        issues.append(
            f"{evidence_id} AWS-40 requires a durable read authority source "
            "and ISO authorization timestamp"
        )
    elif observed_at is not None and observed_at < read_authorized_at:
        issues.append(f"{evidence_id} AWS-40 observation precedes read authorization")
    if authority is None:
        if require_authority:
            issues.append(
                f"{evidence_id} AWS-40 requires its exact current read receipt"
            )
        return issues

    expected_scope = (
        f"ACCOUNT: {authority.get('account')}; REGION: {authority.get('region')}; "
        f"ENVIRONMENT: {authority.get('environment')}"
    )
    if read_id != clean_cell(authority.get("authorization_id", "")):
        issues.append(
            f"{evidence_id} read authorization does not match current authority"
        )
    if read_role != clean_cell(authority.get("role_or_profile", "")):
        issues.append(f"{evidence_id} read role does not match its receipt")
    if read_digest != clean_cell(authority.get("receipt_digest", "")):
        issues.append(f"{evidence_id} read receipt digest is tampered")
    if read_valid_until != clean_cell(authority.get("expiration", "")):
        issues.append(f"{evidence_id} read validity is tampered")
    if read_source != clean_cell(authority.get("authority_source", "")):
        issues.append(f"{evidence_id} read authority source is tampered")
    if read_authorized_at_value != clean_cell(authority.get("authorized_at", "")):
        issues.append(f"{evidence_id} read authorization timestamp is tampered")
    if clean_cell(row.get("Account / Region / environment", "")) != expected_scope:
        issues.append(f"{evidence_id} read account boundary is stale")
    authority_authorized_at = _iso_datetime(authority.get("authorized_at", ""))
    if authority_authorized_at is None:
        issues.append(f"{evidence_id} read authorization timestamp is invalid")
    elif observed_at is not None and observed_at < authority_authorized_at:
        issues.append(f"{evidence_id} AWS-40 observation precedes read authorization")
    try:
        observed_resources: set[str] = set()
        for field_name in (
            "Resources proposed to remove",
            "Resources retained",
            "Shared dependencies",
            "Residual resources",
        ):
            observed_resources.update(
                _teardown_values(row.get(field_name, ""), field_name, allow_none=True)
            )
        observed_operations = _teardown_values(
            row.get("Post-teardown verification", ""),
            "Post-teardown verification",
            allow_none=clean_cell(row.get("Status", ""))
            in {"RUNNING", "BLOCKED", "STALE"},
        )
    except ValueError as exc:
        issues.append(str(exc))
        observed_resources, observed_operations = set(), []
    authorized_resources = set(authority.get("resources", []))
    authorized_operations = set(authority.get("operations", []))
    if require_exact_scope and observed_resources != authorized_resources:
        issues.append(f"{evidence_id} recorded resources do not match exact read scope")
    elif observed_resources and not observed_resources.issubset(authorized_resources):
        issues.append(f"{evidence_id} observed resources exceed read scope")
    if require_exact_scope and set(observed_operations) != authorized_operations:
        issues.append(
            f"{evidence_id} recorded operations do not match exact read scope"
        )
    elif observed_operations and not set(observed_operations).issubset(
        authorized_operations
    ):
        issues.append(f"{evidence_id} observed operations exceed read scope")
    return issues


def _teardown_reconciliation_read_authority(
    verify_text: str,
    cost_posture: str,
    group: list[dict[str, str]],
    attempt_id: str,
    *,
    restricted_closure: bool,
) -> dict[str, Any] | None:
    """Project current read authority for one immutable teardown attempt."""

    if not group:
        return None
    try:
        receipt = marked_receipt(verify_text, "aws-read-preflight")
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS READ-ONLY PREFLIGHT",
        AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
    )
    if fields is None:
        return None
    synthetic_group = [
        {
            **row,
            "Artifact digest": fields["Artifact digest"],
            "Resources": row.get("Resources proposed to remove", ""),
        }
        for row in group
    ]
    authority = _deployment_reconciliation_read_authority(
        verify_text,
        cost_posture,
        synthetic_group,
        allow_expired=False,
        require_post_action_freshness=restricted_closure,
    )
    if authority is None:
        return None
    return {
        **authority,
        "attempt_id": attempt_id,
        "reconciliation_only": restricted_closure,
    }


def derive_teardown_sequence_state(
    verify_text: str,
    read_authority: Mapping[str, Any] | None,
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    envelope: Mapping[str, str],
    restricted_closure: bool = False,
    cost_posture: str = "",
    active_artifact: str = "",
) -> dict[str, Any]:
    """Derive append-only AWS-40/AWS-50 sequencing without replay authority."""

    base: dict[str, Any] = {
        "status": "NOT_ACTIVE",
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "observed_at": "NONE",
        "ready_evidence_id": "NONE",
        "read_authorization": "NONE",
        "read_role_or_profile": "NONE",
        "read_receipt_digest": "NONE",
        "read_valid_until": "NONE",
        "read_authority_source": "NONE",
        "expected_manifest_or_stack": "NONE",
        "account": "NONE",
        "region": "NONE",
        "environment": "NONE",
        "phase": "NONE",
        "action_status": "NONE",
        "review_status": "NONE",
        "issues": [],
        "resources_to_remove": [],
        "allowed_operations": [],
        "resources_to_retain": [],
        "shared_dependencies": [],
        "resources_removed": [],
        "residual_resources": [],
        "cost_effect": "NONE",
        "post_action_verification": "NONE",
        "terminal_status": "NONE",
        "snapshots_and_backups": "NONE",
        "inventory_limits": "NONE",
        "identity_and_boundary_match": "NONE",
        "teardown_authorization": "NONE",
        "teardown_receipt_digest": "NONE",
        "blocker_or_stale_reason": "NONE",
        "basis_stale": False,
        "post_action_bound": False,
        "current_mutation_authority_status": "UNAVAILABLE",
        "reconciliation_read_authority": {},
    }
    try:
        rows = parse_teardown_reconciliation_evidence(verify_text)
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    concrete: list[dict[str, str]] = []
    invalid_identifiers: list[str] = []
    for row in rows:
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id):
            concrete.append({key: clean_cell(value) for key, value in row.items()})
            continue
        status = clean_cell(row.get("Status", ""))
        placeholder = (
            unresolved(evidence_id)
            and status in {"", "NOT_STARTED"}
            and all(
                unresolved(row.get(header, ""))
                for header in AWS_TEARDOWN_EVIDENCE_HEADERS
                if header not in {"Evidence ID", "Status"}
            )
        )
        if not placeholder:
            invalid_identifiers.append(evidence_id or "EMPTY")
    if invalid_identifiers:
        return {
            **base,
            "status": "BLOCKED",
            "issues": [
                "Teardown reconciliation evidence has noncanonical or partially "
                "populated IDs: " + ", ".join(sorted(invalid_identifiers))
            ],
        }
    if not concrete:
        return base
    identifiers = [row["Evidence ID"] for row in concrete]
    structural_issues: list[str] = []
    if len(identifiers) != len(set(identifiers)):
        structural_issues.append(
            "Teardown reconciliation evidence contains duplicate IDs"
        )
    timestamps: list[datetime] = []
    attempts: dict[str, list[dict[str, str]]] = {}
    attempt_order: list[str] = []
    closed_attempts: set[str] = set()
    active_attempt = ""
    for row in concrete:
        evidence_id = row["Evidence ID"]
        attempt_id = row.get("Attempt ID", "")
        phase = row.get("Phase", "")
        status = row.get("Status", "")
        observed_at = _iso_datetime(row.get("Observed at", ""))
        if phase == "AWS-40":
            if status not in AWS_TEARDOWN_REVIEW_STATUSES:
                structural_issues.append(
                    f"{evidence_id} has invalid AWS-40 status {status or 'EMPTY'}"
                )
            if (
                attempt_id != "NONE"
                and AWS_TEARDOWN_ATTEMPT_ID.fullmatch(attempt_id) is None
            ):
                structural_issues.append(f"{evidence_id} has a noncanonical Attempt ID")
            structural_issues.extend(
                _teardown_read_row_issues(row, None, require_authority=False)
            )
        elif phase == "AWS-50":
            if status not in AWS_TEARDOWN_ACTION_STATUSES:
                structural_issues.append(
                    f"{evidence_id} has invalid AWS-50 status {status or 'EMPTY'}"
                )
            if AWS_TEARDOWN_ATTEMPT_ID.fullmatch(attempt_id) is None:
                structural_issues.append(f"{evidence_id} has a noncanonical Attempt ID")
        else:
            structural_issues.append(
                f"{evidence_id} phase must be exactly AWS-40 or AWS-50"
            )
        if observed_at is None:
            structural_issues.append(
                f"{evidence_id} Observed at must be ISO 8601 with timezone"
            )
        else:
            timestamps.append(observed_at)
        if not explicit_value(row.get("Durable source", ""), allow_none=False):
            structural_issues.append(f"{evidence_id} requires a durable source")
        blocker_reason = row.get("Blocker or stale reason", "")
        if phase == "AWS-40" and status in {"BLOCKED", "STALE"}:
            if not explicit_value(blocker_reason, allow_none=False):
                structural_issues.append(
                    f"{evidence_id} requires an exact blocker or stale reason"
                )
        elif blocker_reason != "NONE":
            structural_issues.append(
                f"{evidence_id} must use Blocker or stale reason = NONE"
            )
        if attempt_id != "NONE":
            if attempt_id != active_attempt:
                if attempt_id in closed_attempts:
                    structural_issues.append(
                        f"{evidence_id} reopens a noncontiguous teardown attempt"
                    )
                if active_attempt:
                    closed_attempts.add(active_attempt)
                active_attempt = attempt_id
                attempt_order.append(attempt_id)
            attempts.setdefault(attempt_id, []).append(row)
        elif phase == "AWS-50":
            structural_issues.append(
                f"{evidence_id} AWS-50 requires a canonical Attempt ID"
            )
        elif active_attempt:
            active_rows = attempts.get(active_attempt, [])
            active_has_terminal_review = any(
                item.get("Phase") == "AWS-40"
                and item.get("Status")
                in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
                for item in active_rows
            )
            if phase == "AWS-40" and not active_has_terminal_review:
                structural_issues.append(
                    f"{evidence_id} AWS-40 cannot erase active teardown attempt "
                    f"binding {active_attempt}"
                )
            closed_attempts.add(active_attempt)
            active_attempt = ""
    if len(timestamps) != len(set(timestamps)):
        structural_issues.append(
            "Teardown reconciliation evidence timestamps must be unique"
        )
    if len(timestamps) == len(concrete) and timestamps != sorted(timestamps):
        structural_issues.append(
            "Teardown reconciliation evidence must be appended in observed-time order"
        )
    replayed_authorizations: set[str] = set()
    replayed_digests: set[str] = set()
    for index, attempt_id in enumerate(attempt_order):
        group = attempts[attempt_id]
        starts = [
            row
            for row in group
            if row.get("Phase") == "AWS-50" and row.get("Status") == "STARTED"
        ]
        terminals = [
            row
            for row in group
            if row.get("Phase") == "AWS-50"
            and row.get("Status") in AWS_TEARDOWN_TERMINAL_STATUSES
        ]
        reviews = [row for row in group if row.get("Phase") == "AWS-40"]
        if len(starts) != 1 or group[0] not in starts:
            structural_issues.append(
                f"{attempt_id} requires exactly one first AWS-50 STARTED row"
            )
        if len(terminals) > 1:
            structural_issues.append(
                f"{attempt_id} has more than one AWS-50 terminal row"
            )
        if terminals and group.index(terminals[0]) != 1:
            structural_issues.append(
                f"{attempt_id} AWS-50 terminal row must immediately follow STARTED"
            )
        if reviews and len(terminals) != 1:
            structural_issues.append(
                f"{attempt_id} AWS-40 requires one prior AWS-50 terminal row"
            )
        if (
            reviews
            and terminals
            and any(group.index(row) < group.index(terminals[0]) for row in reviews)
        ):
            structural_issues.append(
                f"{attempt_id} AWS-40 must follow the AWS-50 terminal row"
            )
        if len(reviews) > 2:
            structural_issues.append(
                f"{attempt_id} exceeds the bounded AWS-40 retry sequence"
            )
        if (
            len(reviews) == 2
            and reviews[0].get("Status") == "STALE"
            and reviews[0].get("Read authorization")
            == reviews[1].get("Read authorization")
        ):
            structural_issues.append(
                f"{attempt_id} AWS-40 recovery requires fresh read authority"
            )
        if len(reviews) == 2 and (
            reviews[0].get("Status") not in {"RUNNING", "STALE"}
            or reviews[1].get("Status")
            not in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
        ):
            structural_issues.append(
                f"{attempt_id} AWS-40 recovery must be RUNNING or STALE then terminal"
            )
        immutable_fields = (
            "REQ / DES / AUTH",
            "Read authorization",
            "Read role or profile",
            "Read receipt digest",
            "Read valid until",
            "Read authority source",
            "Teardown authorization",
            "Teardown receipt digest",
            "Role or profile",
            "Expected manifest or stack",
            "Resources proposed to remove",
            "Allowed deletion operations",
            "Resources retained",
            "Shared dependencies",
            "Cost effect",
            "Post-teardown verification",
            "Account / Region / environment",
        )
        action_rows = [row for row in group if row.get("Phase") == "AWS-50"]
        if action_rows:
            first = action_rows[0]
            for row in action_rows[1:]:
                for field_name in immutable_fields:
                    if row.get(field_name) != first.get(field_name):
                        structural_issues.append(
                            f"{attempt_id} changes immutable {field_name}"
                        )
        authority_row = starts[0] if starts else group[0]
        authorization_id = authority_row.get("Teardown authorization", "")
        receipt_digest = authority_row.get("Teardown receipt digest", "")
        if authorization_id in replayed_authorizations:
            structural_issues.append(
                f"{attempt_id} replays a teardown authorization ID"
            )
        replayed_authorizations.add(authorization_id)
        if receipt_digest in replayed_digests:
            structural_issues.append(f"{attempt_id} replays a teardown receipt digest")
        replayed_digests.add(receipt_digest)
        if index < len(attempt_order) - 1:
            terminal_reviews = [
                row
                for row in reviews
                if row.get("Status")
                in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
            ]
            if len(terminals) != 1 or len(terminal_reviews) != 1:
                structural_issues.append(
                    f"{attempt_id} was not reconciled before the next teardown attempt"
                )
    if structural_issues:
        return {**base, "status": "BLOCKED", "issues": structural_issues}

    expected_basis = (
        f"{requirements_revision} / {design_revision} / {construction_authorization}"
    )
    current_read = bool(
        read_authority is not None and read_authority.get("validity") == "CURRENT"
    )
    selected_attempt_id = clean_cell(concrete[-1].get("Attempt ID", ""))
    if selected_attempt_id != "NONE":
        if selected_attempt_id not in attempts:
            return {
                **base,
                "status": "BLOCKED",
                "issues": ["Latest teardown epoch is malformed"],
            }
        attempt_id = selected_attempt_id
        group = attempts[attempt_id]
        started = group[0]
        terminal = next(
            (
                row
                for row in group
                if row.get("Phase") == "AWS-50"
                and row.get("Status") in AWS_TEARDOWN_TERMINAL_STATUSES
            ),
            None,
        )
        reviews = [row for row in group if row.get("Phase") == "AWS-40"]
        latest = reviews[-1] if reviews else terminal or started
        group_basis = started.get("REQ / DES / AUTH", "")
        basis_authorization = _teardown_basis_authorization(started)
        basis_stale = group_basis != expected_basis
        historical = (
            restricted_closure or basis_stale or construction_authorization == "NONE"
        )
        issues: list[str] = []
        if basis_authorization is None:
            issues.append(f"{attempt_id} has a noncanonical REQ / DES / AUTH basis")
        started_index = concrete.index(started)
        ready = concrete[started_index - 1] if started_index > 0 else None
        if not (
            ready is not None
            and ready.get("Phase") == "AWS-40"
            and ready.get("Attempt ID") == "NONE"
            and ready.get("Status") == "READY_FOR_TEARDOWN"
        ):
            issues.append(
                f"{attempt_id} must immediately follow the latest READY_FOR_TEARDOWN evidence"
            )
            ready = None
        else:
            for field_name in (
                "REQ / DES / AUTH",
                "Read authorization",
                "Read role or profile",
                "Read receipt digest",
                "Read valid until",
                "Read authority source",
                "Role or profile",
                "Expected manifest or stack",
                "Resources proposed to remove",
                "Allowed deletion operations",
                "Resources retained",
                "Shared dependencies",
                "Cost effect",
                "Post-teardown verification",
                "Account / Region / environment",
            ):
                if ready.get(field_name) != started.get(field_name):
                    issues.append(
                        f"{attempt_id} does not match READY_FOR_TEARDOWN {field_name}"
                    )
            issues.extend(
                _teardown_read_row_issues(ready, None, require_authority=False)
            )
        if basis_authorization is not None:
            fields, digest, receipt_issues = _teardown_receipt_row_issues(
                started,
                verify_text,
                construction_authorization=basis_authorization,
                envelope=envelope,
                historical=historical,
            )
            issues.extend(receipt_issues)
            provenance = _action_authorization_rows(verify_text).get("Teardown")
            if fields is not None and provenance is not None:
                issues.extend(
                    _teardown_attempt_timing_issues(started, fields, provenance)
                )
            if digest != started.get("Teardown receipt digest"):
                issues.append(f"{attempt_id} has a stale teardown receipt digest")
        issues.extend(
            _teardown_action_attempt_row_issues(
                started, envelope, historical=historical
            )
        )
        if terminal is not None:
            issues.extend(
                _teardown_action_attempt_row_issues(
                    terminal, envelope, historical=historical
                )
            )
        if issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "evidence_id": latest.get("Evidence ID", "NONE"),
                "phase": latest.get("Phase", "NONE"),
                "action_status": terminal.get("Status", "STARTED")
                if terminal
                else "STARTED",
                "basis_stale": basis_stale,
                "issues": issues,
            }
        try:
            resources = _teardown_values(
                started["Resources proposed to remove"],
                "Resources proposed to remove",
                allow_none=False,
            )
            operations = _teardown_values(
                started["Allowed deletion operations"],
                "Allowed deletion operations",
                allow_none=False,
            )
            retained = _teardown_values(
                started["Resources retained"], "Resources retained", allow_none=True
            )
            shared = _teardown_values(
                started["Shared dependencies"], "Shared dependencies", allow_none=True
            )
            removed = _teardown_values(
                latest["Resources removed"], "Resources removed", allow_none=True
            )
            residuals = _teardown_values(
                latest["Residual resources"], "Residual resources", allow_none=True
            )
        except ValueError as exc:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "issues": [str(exc)],
            }
        reconciliation_read_authority: dict[str, Any] = {}
        if terminal is not None:
            restricted_read = (
                restricted_closure
                or basis_stale
                or construction_authorization == "NONE"
            )
            candidate = None if restricted_read else read_authority
            if candidate is not None and candidate.get("validity") == "CURRENT":
                reconciliation_read_authority = {
                    **dict(candidate),
                    "attempt_id": attempt_id,
                    "reconciliation_only": False,
                }
            else:
                recovered = _teardown_reconciliation_read_authority(
                    verify_text,
                    cost_posture,
                    group,
                    attempt_id,
                    restricted_closure=restricted_read,
                )
                if recovered is not None:
                    reconciliation_read_authority = recovered
        projection = {
            **base,
            "attempt_id": attempt_id,
            "evidence_id": latest.get("Evidence ID", "NONE"),
            "observed_at": latest.get("Observed at", "NONE"),
            "ready_evidence_id": ready.get("Evidence ID", "NONE"),
            "read_authorization": started["Read authorization"],
            "read_role_or_profile": started["Read role or profile"],
            "read_receipt_digest": started["Read receipt digest"],
            "read_valid_until": started["Read valid until"],
            "read_authority_source": started["Read authority source"],
            "expected_manifest_or_stack": started["Expected manifest or stack"],
            "account": fields["Account"],
            "region": fields["Region"],
            "environment": fields["Environment"],
            "phase": latest.get("Phase", "NONE"),
            "action_status": terminal.get("Status", "STARTED")
            if terminal
            else "STARTED",
            "basis_stale": basis_stale,
            "teardown_authorization": started["Teardown authorization"],
            "teardown_receipt_digest": started["Teardown receipt digest"],
            "role_or_profile": started["Role or profile"],
            "resources_to_remove": resources,
            "allowed_operations": operations,
            "resources_to_retain": retained,
            "shared_dependencies": shared,
            "resources_removed": removed,
            "residual_resources": residuals,
            "cost_effect": started["Cost effect"],
            "post_action_verification": started["Post-teardown verification"],
            "terminal_status": latest["Stack events and terminal status"],
            "snapshots_and_backups": latest["Snapshots and backups"],
            "inventory_limits": latest["Inventory or discovery limits"],
            "identity_and_boundary_match": latest["Identity and boundary match"],
            "blocker_or_stale_reason": latest["Blocker or stale reason"],
            "current_mutation_authority_status": "CONSUMED",
            "reconciliation_read_authority": reconciliation_read_authority,
        }
        if terminal is None:
            return {**projection, "status": "ACTION_TERMINAL_REQUIRED"}
        if not reviews:
            return {**projection, "status": "POST_ACTION_REVIEW"}
        review = reviews[-1]
        review_issues: list[str] = []
        terminal_time = _iso_datetime(terminal.get("Observed at", ""))
        review_time = _iso_datetime(review.get("Observed at", ""))
        if terminal_time is None or review_time is None or review_time <= terminal_time:
            review_issues.append(
                "post-action AWS-40 evidence must follow the terminal AWS-50 row"
            )
        if review.get("Teardown authorization") != started.get(
            "Teardown authorization"
        ):
            review_issues.append("post-action AWS-40 changes teardown authorization")
        if review.get("Teardown receipt digest") != started.get(
            "Teardown receipt digest"
        ):
            review_issues.append("post-action AWS-40 changes teardown receipt digest")
        for field_name in (
            "REQ / DES / AUTH",
            "Role or profile",
            "Expected manifest or stack",
            "Resources proposed to remove",
            "Allowed deletion operations",
            "Resources retained",
            "Shared dependencies",
            "Cost effect",
            "Post-teardown verification",
            "Account / Region / environment",
        ):
            if review.get(field_name) != started.get(field_name):
                review_issues.append(
                    f"post-action AWS-40 changes immutable {field_name}"
                )
        review_status = review.get("Status", "")
        review_authority = (
            reconciliation_read_authority
            if clean_cell(reconciliation_read_authority.get("authorization_id", ""))
            == clean_cell(review.get("Read authorization", ""))
            else None
        )
        review_issues.extend(
            _teardown_read_row_issues(
                review,
                review_authority,
                require_authority=review_status in {"RUNNING", "STALE"},
                require_exact_scope=(
                    review_status in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
                    and review_authority is not None
                ),
            )
        )
        if review_status in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN"} and review.get(
            "Identity and boundary match"
        ) not in {"PASS", "VERIFIED"}:
            review_issues.append(
                "post-action AWS-40 requires verified identity and boundary"
            )
        if review_status == "VERIFIED_CLEAN":
            if residuals:
                review_issues.append(
                    "VERIFIED_CLEAN requires Residual resources = NONE"
                )
            if set(removed) != set(resources):
                review_issues.append(
                    "VERIFIED_CLEAN must reconcile every proposed removal"
                )
        if review_status == "RESIDUALS_REMAIN" and not residuals:
            review_issues.append(
                "RESIDUALS_REMAIN requires an exact residual-resource list"
            )
        if review_issues:
            return {**projection, "status": "BLOCKED", "issues": review_issues}
        common_review = {
            **projection,
            "review_status": review_status,
            "evidence_id": review["Evidence ID"],
            "observed_at": review["Observed at"],
            "phase": "AWS-40",
            "read_authorization": review["Read authorization"],
            "read_role_or_profile": review["Read role or profile"],
            "read_receipt_digest": review["Read receipt digest"],
            "read_valid_until": review["Read valid until"],
            "read_authority_source": review["Read authority source"],
            "identity_and_boundary_match": review["Identity and boundary match"],
            "blocker_or_stale_reason": review["Blocker or stale reason"],
        }
        if review_status in {"RUNNING", "STALE"}:
            return {**common_review, "status": "POST_ACTION_REVIEW"}
        return {
            **common_review,
            "status": review_status,
            "post_action_bound": review_status
            in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"},
        }

    standalone_rows = [row for row in concrete if row.get("Attempt ID") == "NONE"]
    if not standalone_rows:
        return base
    latest = standalone_rows[-1]
    evidence_id = latest["Evidence ID"]
    status = latest["Status"]
    basis_stale = latest.get("REQ / DES / AUTH") != expected_basis
    authority_for_row = read_authority if current_read and not basis_stale else None
    require_current_read = bool(not basis_stale and status not in {"BLOCKED", "STALE"})
    issues = _teardown_read_row_issues(
        latest,
        authority_for_row,
        require_authority=require_current_read,
    )
    if (
        latest.get("Teardown authorization") != "NONE"
        or latest.get("Teardown receipt digest") != "NONE"
    ):
        issues.append("pre-action AWS-40 evidence cannot claim teardown authority")
    if status in {
        "READY_FOR_TEARDOWN",
        "VERIFIED_CLEAN",
        "RESIDUALS_REMAIN",
    } and latest.get("Identity and boundary match") not in {"PASS", "VERIFIED"}:
        issues.append(f"{evidence_id} requires a verified identity and boundary match")
    if issues:
        return {
            **base,
            "status": "BLOCKED",
            "evidence_id": evidence_id,
            "phase": "AWS-40",
            "basis_stale": basis_stale,
            "issues": issues,
        }
    projection = {
        **base,
        "status": status,
        "evidence_id": evidence_id,
        "observed_at": latest["Observed at"],
        "phase": "AWS-40",
        "read_authorization": latest["Read authorization"],
        "read_role_or_profile": latest["Read role or profile"],
        "read_receipt_digest": latest["Read receipt digest"],
        "read_valid_until": latest["Read valid until"],
        "read_authority_source": latest["Read authority source"],
        "expected_manifest_or_stack": latest["Expected manifest or stack"],
        "role_or_profile": latest["Role or profile"],
        "account": authority_for_row.get("account", "NONE")
        if authority_for_row
        else "NONE",
        "region": authority_for_row.get("region", "NONE")
        if authority_for_row
        else "NONE",
        "environment": authority_for_row.get("environment", "NONE")
        if authority_for_row
        else "NONE",
        "identity_and_boundary_match": latest["Identity and boundary match"],
        "blocker_or_stale_reason": latest["Blocker or stale reason"],
        "basis_stale": basis_stale,
    }
    if basis_stale or not current_read or construction_authorization == "NONE":
        return {**projection, "status": "BLOCKED" if status == "BLOCKED" else "STALE"}
    if status in {"RUNNING", "STALE"}:
        return projection
    if status == "BLOCKED":
        return projection
    allow_empty = status in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN"}
    try:
        resources = _teardown_values(
            latest["Resources proposed to remove"],
            "Resources proposed to remove",
            allow_none=allow_empty,
        )
        operations = _teardown_values(
            latest["Allowed deletion operations"],
            "Allowed deletion operations",
            allow_none=allow_empty,
        )
        retained = _teardown_values(
            latest["Resources retained"], "Resources retained", allow_none=True
        )
        shared = _teardown_values(
            latest["Shared dependencies"], "Shared dependencies", allow_none=True
        )
        removed = _teardown_values(
            latest["Resources removed"], "Resources removed", allow_none=True
        )
        residuals = _teardown_values(
            latest["Residual resources"], "Residual resources", allow_none=True
        )
    except ValueError as exc:
        return {**projection, "status": "BLOCKED", "issues": [str(exc)]}
    if bool(resources) != bool(operations):
        issues.append(
            "Removal resources and deletion operations must both be present or NONE"
        )
    elif resources and not _receipt_scope_within_gate_b(
        resources, operations, envelope
    ):
        issues.append("AWS-40 removal scope exceeds Gate B")
    if (
        set(resources).intersection(retained)
        or set(resources).intersection(shared)
        or set(retained).intersection(shared)
    ):
        issues.append("AWS-40 removal, retention, and shared sets overlap")
    for field_name, allow_none in (
        ("Expected manifest or stack", False),
        ("Cost effect", False),
        ("Post-teardown verification", False),
    ):
        if not explicit_value(latest.get(field_name, ""), allow_none=allow_none):
            issues.append(f"AWS-40 requires {field_name}")
    if status == "VERIFIED_CLEAN":
        if residuals:
            issues.append("VERIFIED_CLEAN requires Residual resources = NONE")
        if set(removed) != set(resources):
            issues.append("VERIFIED_CLEAN must reconcile every proposed removal")
    if status == "RESIDUALS_REMAIN" and not residuals:
        issues.append("RESIDUALS_REMAIN requires an exact residual-resource list")
    if issues:
        return {**projection, "status": "BLOCKED", "issues": issues}
    return {
        **projection,
        "resources_to_remove": resources,
        "allowed_operations": operations,
        "resources_to_retain": retained,
        "shared_dependencies": shared,
        "resources_removed": removed,
        "residual_resources": residuals,
        "cost_effect": latest["Cost effect"],
        "post_action_verification": latest["Post-teardown verification"],
        "terminal_status": latest["Stack events and terminal status"],
        "snapshots_and_backups": latest["Snapshots and backups"],
        "inventory_limits": latest["Inventory or discovery limits"],
    }


def derive_read_preflight_state(
    verify_text: str,
    authority: Mapping[str, Any] | None,
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    artifact_binding: str,
) -> dict[str, Any]:
    """Validate observed account evidence separately from AWS guidance evidence."""

    base: dict[str, Any] = {
        "status": "NOT_STARTED",
        "preflight_id": "NONE",
        "read_authorization": (
            authority.get("authorization_id", "NONE") if authority else "NONE"
        ),
        "account": authority.get("account", "NONE") if authority else "NONE",
        "region": authority.get("region", "NONE") if authority else "NONE",
        "environment": (authority.get("environment", "NONE") if authority else "NONE"),
        "account_access": "NOT_OBSERVED",
        "evidence_ids": [],
        "issues": [],
    }
    if authority is None or authority.get("validity") != "CURRENT":
        return base
    try:
        rows = parse_read_preflight_evidence(verify_text)
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    concrete = [
        row
        for row in rows
        if AWS_PREFLIGHT_ID.fullmatch(clean_cell(row.get("Preflight ID", "")))
    ]
    identifiers = [clean_cell(row["Preflight ID"]) for row in concrete]
    if len(identifiers) != len(set(identifiers)):
        return {
            **base,
            "status": "BLOCKED",
            "issues": ["Read-only preflight evidence contains duplicate Preflight IDs"],
        }
    candidates = [
        row
        for row in concrete
        if clean_cell(row.get("Read authorization", ""))
        == authority.get("authorization_id")
    ]
    if not candidates:
        return {**base, "status": "RUNNING"}
    if len(candidates) != 1:
        return {
            **base,
            "status": "BLOCKED",
            "issues": [
                "Expected exactly one preflight row for the current read authorization"
            ],
        }
    row = candidates[0]
    preflight_id = clean_cell(row["Preflight ID"])
    result = clean_cell(row.get("Result", ""))
    expected_basis = (
        f"{requirements_revision} / {design_revision} / {construction_authorization}"
    )
    expected_scalars = {
        "REQ / DES / AUTH": expected_basis,
        "Artifact digest": artifact_binding,
        "Role or profile": authority.get("role_or_profile"),
        "Account": authority.get("account"),
        "Region": authority.get("region"),
        "Environment": authority.get("environment"),
    }
    issues = [
        f"{field_name} does not match current read scope"
        for field_name, expected in expected_scalars.items()
        if clean_cell(row.get(field_name, "")) != expected
    ]
    authority_binding = authority.get("artifact_plan_binding")
    authorized_artifact = (
        authority_binding.get("artifact")
        if isinstance(authority_binding, Mapping)
        else None
    )
    if authorized_artifact != artifact_binding:
        issues.append(
            "Read receipt artifact binding does not match the current artifact"
        )
    resources = _split_authority_values(row.get("Resources", ""))
    operations = _split_authority_values(row.get("Operations observed", ""))
    if len(operations) != len(set(operations)):
        issues.append("Operations observed must not contain duplicates")
    if resources != list(authority.get("resources", [])):
        issues.append("Resources do not exactly match current read scope")
    if not operations or not set(operations).issubset(
        set(authority.get("operations", []))
    ):
        issues.append("Operations observed are empty or exceed current read scope")
    try:
        evidence_ids = _canonical_id_list(
            row.get("AWS evidence IDs", ""),
            re.compile(r"EV-\d{4,}"),
            "AWS evidence IDs",
        )
    except ValueError as exc:
        evidence_ids = []
        issues.append(str(exc))
    if clean_cell(row.get("Account access", "")) != "READ_ONLY_OBSERVED":
        issues.append("Account access must be READ_ONLY_OBSERVED")
    for label in ("Caller identity evidence", "Boundary and drift evidence"):
        value = clean_cell(row.get(label, ""))
        if re.fullmatch(r"EV-\d{4,}", value) is None:
            issues.append(f"{label} must reference one EV ID")
        elif value not in evidence_ids:
            issues.append(f"{label} must be included in AWS evidence IDs")
    started = _iso_datetime(row.get("Started at", ""))
    completed = _iso_datetime(row.get("Completed at", ""))
    if started is None:
        issues.append("Started at must be ISO 8601 with timezone")
    if result == "READY":
        if completed is None or (started is not None and completed < started):
            issues.append("Completed at must be current and not precede Started at")
        if clean_cell(row.get("Identity and boundary match", "")) not in {
            "PASS",
            "VERIFIED",
        }:
            issues.append("Identity and boundary match must be PASS or VERIFIED")
    if issues:
        return {
            **base,
            "status": "STALE" if result in {"READY", "RUNNING"} else "BLOCKED",
            "preflight_id": preflight_id,
            "evidence_ids": evidence_ids,
            "issues": issues,
            "account_access": "NOT_VERIFIED",
        }
    if result not in {"RUNNING", "READY", "BLOCKED", "STALE"}:
        return {
            **base,
            "status": "BLOCKED",
            "preflight_id": preflight_id,
            "issues": ["Preflight Result is not canonical"],
            "account_access": "NOT_VERIFIED",
        }
    return {
        **base,
        "status": result,
        "preflight_id": preflight_id,
        "evidence_ids": evidence_ids,
        "account_access": "READ_ONLY_OBSERVED",
    }


def derive_aws_execution_projection(
    materiality: Mapping[str, Any],
    *,
    release_decision: str,
    guidance_ready: bool,
    read_authority: Mapping[str, Any] | None,
    preflight: Mapping[str, Any],
    lane: str | None = None,
) -> dict[str, Any]:
    active = release_decision == "READY_TO_DEPLOY"
    preflight_projection = dict(preflight)
    read_scope_current = bool(
        read_authority is not None and read_authority.get("validity") == "CURRENT"
    )
    if not active:
        progress = "NOT_ACTIVE"
    elif lane == "documentation-only" and guidance_ready:
        progress = "AWS_PREFLIGHT_READY"
        preflight_projection.update(
            {
                "status": "NOT_APPLICABLE",
                "account": "NONE",
                "region": "NONE",
                "environment": "NONE",
                "account_access": "NOT_USED",
                "issues": [],
            }
        )
    elif not guidance_ready:
        progress = "AWS_GUIDANCE_REQUIRED"
    elif not read_scope_current:
        progress = "AWS_READ_SCOPE_REQUIRED"
    elif preflight.get("status") != "READY":
        progress = "AWS_PREFLIGHT_RUNNING"
    elif lane == "explicit-gate":
        progress = "WAITING_AWS_MUTATION_AUTH"
    else:
        progress = "AWS_PREFLIGHT_READY"
    completed: list[str] = []
    if active:
        if guidance_ready:
            completed.append("AWS_GUIDANCE_REQUIRED")
        if read_scope_current:
            completed.append("AWS_READ_SCOPE_REQUIRED")
        if preflight.get("status") in {"RUNNING", "READY"}:
            completed.append("AWS_PREFLIGHT_RUNNING")
        if preflight.get("status") == "READY" or (
            lane == "documentation-only" and guidance_ready
        ):
            completed.append("AWS_PREFLIGHT_READY")
    return {
        "schema_version": 1,
        "active": active,
        "lane": lane or "NONE",
        "requirements_materiality": dict(materiality),
        "guidance": {
            "status": "CURRENT" if guidance_ready else "REQUIRED",
        },
        "read_scope": {
            "status": (
                "NOT_APPLICABLE"
                if lane == "documentation-only"
                else "CURRENT"
                if read_scope_current
                else "REQUIRED"
            ),
            "authorization_id": (
                read_authority.get("authorization_id", "NONE")
                if read_scope_current and read_authority is not None
                else "NONE"
            ),
        },
        "preflight": preflight_projection,
        "completed_states": completed,
        "progress_state": progress,
    }


def _receipt_external_authority(
    verify_text: str,
    action: str,
    construction_authorization: str,
    *,
    envelope: Mapping[str, str],
    cost_posture: str,
    active_artifact: str,
    preflight: Mapping[str, Any] | None = None,
    teardown_review: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if action not in {"Deployment", "Teardown"}:
        return None
    deployment = action == "Deployment"
    gate = "aws-deployment" if deployment else "aws-teardown"
    title = "AUTHORIZE AWS DEPLOYMENT" if deployment else "AUTHORIZE AWS TEARDOWN"
    expected_fields = (
        AWS_DEPLOYMENT_RECEIPT_FIELDS if deployment else AWS_TEARDOWN_RECEIPT_FIELDS
    )
    allow_none_fields = (
        frozenset({"Rollback boundary"})
        if deployment
        else frozenset({"Resources and data to retain", "Shared dependencies"})
    )
    try:
        receipt = marked_receipt(verify_text, gate)
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        title,
        expected_fields,
        allow_none_fields=allow_none_fields,
    )
    row = _action_authorization_rows(verify_text).get(action)
    if fields is None or row is None or unresolved(receipt):
        return None
    auth_key = "AWS authorization" if deployment else "Teardown authorization"
    authorization_id = fields.get(auth_key, "")
    expected_pattern = r"AWS-AUTH-\d{4,}" if deployment else r"TEARDOWN-AUTH-\d{4,}"
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    result = clean_cell(row.get("Result", ""))
    valid_until = _receipt_validity_within_gate_b(
        fields.get("Valid until", ""), result, envelope
    )
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    resources_field = (
        "Stack, application, and resources"
        if deployment
        else "Stack, application, and resources to remove"
    )
    operations_field = (
        "Allowed operations" if deployment else "Allowed deletion operations"
    )
    resources = _split_authority_values(fields[resources_field])
    operations = _split_authority_values(fields[operations_field])
    expected_resources = (
        f"RESOURCES: {fields[resources_field]}; OPERATIONS: {fields[operations_field]}"
    )
    observed_at = clean_cell(row.get("Observed at", ""))
    if (
        re.fullmatch(expected_pattern, authorization_id) is None
        or fields.get("Construction authorization") != construction_authorization
        or row.get("Authorization ID") != authorization_id
        or row.get("Construction AUTH") != construction_authorization
        or row.get("Role or profile") != fields.get("Profile or role")
        or row.get("Approver") != fields.get("Approver")
        or not explicit_human_approver(fields.get("Approver", ""))
        or clean_cell(row.get("Verbatim receipt SHA-256", "")) != digest
        or clean_cell(row.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or row.get("Account / Region / environment") != expected_scope
        or row.get("Resources and operations") != expected_resources
        or not explicit_value(
            row.get("Stable owner-message source", ""), allow_none=False
        )
        or not explicit_timestamp(observed_at)
        or valid_until is None
        or result not in {"AUTHORIZED", "READY"}
        or not _receipt_identity_matches_gate_b(fields, envelope)
        or not _receipt_scope_within_gate_b(resources, operations, envelope)
    ):
        return None
    if deployment:
        artifact = fields["Artifact digest"]
        plan = fields["IaC plan/change-set binding"]
        cost_ceiling = fields["Cost ceiling"]
        rollback = fields["Rollback boundary"]
        preflight_id = clean_cell(
            preflight.get("preflight_id", "") if preflight else ""
        )
        expected_cost_validity = (
            f"COST: {cost_ceiling}; VALID_UNTIL: {fields['Valid until']}"
        )
        if (
            preflight is None
            or preflight.get("status") != "READY"
            or preflight.get("account_access") != "READ_ONLY_OBSERVED"
            or AWS_PREFLIGHT_ID.fullmatch(preflight_id) is None
            or clean_cell(row.get("Preflight evidence", "")) != preflight_id
            or row.get("Artifact digest") != artifact
            or row.get("IaC plan/change-set binding") != plan
            or row.get("Cost ceiling and validity") != expected_cost_validity
            or row.get("Rollback boundary") != rollback
            or AWS_PLAN_BINDING.fullmatch(plan) is None
            or not _receipt_artifact_matches_gate_b(artifact, envelope, active_artifact)
            or not _mutation_cost_within_gate_b(cost_ceiling, envelope, cost_posture)
            or rollback != _gate_b_rollback_value(envelope)
        ):
            return None
        kind = "AWS_DEPLOYMENT"
        retained_resources: list[str] = []
        shared_dependencies: list[str] = []
        cost_effect = "NONE"
        post_action_verification = "NONE"
        teardown_ready_binding = None
    else:
        teardown_review = teardown_review or {}
        evidence_id = clean_cell(teardown_review.get("evidence_id", ""))
        retained_resources = _split_authority_values(
            fields["Resources and data to retain"]
        )
        shared_dependencies = _split_authority_values(fields["Shared dependencies"])
        cost_effect = fields["Cost effect"]
        post_action_verification = fields["Post-teardown verification"]
        expected_cost_validity = (
            f"COST: {cost_effect}; VALID_UNTIL: {fields['Valid until']}"
        )
        teardown_artifact = "NOT_APPLICABLE — teardown binds the observed inventory"
        teardown_plan = "NOT_APPLICABLE — teardown uses its removal/retention manifest"
        overlap = (
            set(resources).intersection(retained_resources)
            or set(resources).intersection(shared_dependencies)
            or set(retained_resources).intersection(shared_dependencies)
        )
        unsafe_lists = any(
            "*" in item
            for item in resources
            + operations
            + retained_resources
            + shared_dependencies
        )
        if (
            teardown_review.get("status") != "READY_FOR_TEARDOWN"
            or re.fullmatch(r"EV-\d{4,}", evidence_id) is None
            or clean_cell(row.get("Preflight evidence", "")) != evidence_id
            or row.get("Artifact digest") != teardown_artifact
            or row.get("IaC plan/change-set binding") != teardown_plan
            or row.get("Cost ceiling and validity") != expected_cost_validity
            or row.get("Rollback boundary") != post_action_verification
            or resources != list(teardown_review.get("resources_to_remove", []))
            or operations != list(teardown_review.get("allowed_operations", []))
            or retained_resources
            != list(teardown_review.get("resources_to_retain", []))
            or shared_dependencies
            != list(teardown_review.get("shared_dependencies", []))
            or cost_effect != teardown_review.get("cost_effect")
            or post_action_verification
            != teardown_review.get("post_action_verification")
            or fields["Profile or role"] != teardown_review.get("role_or_profile")
            or fields["Account"] != teardown_review.get("account")
            or fields["Region"] != teardown_review.get("region")
            or fields["Environment"] != teardown_review.get("environment")
            or clean_cell(teardown_review.get("identity_and_boundary_match", ""))
            not in {"PASS", "VERIFIED"}
            or overlap
            or unsafe_lists
            or len(retained_resources) != len(set(retained_resources))
            or len(shared_dependencies) != len(set(shared_dependencies))
        ):
            return None
        artifact = teardown_artifact
        plan = teardown_plan
        cost_ceiling = clean_cell(envelope.get("AWS cost ceiling", ""))
        rollback = clean_cell(envelope.get("AWS rollback boundary", ""))
        if (
            _parse_cost_ceiling(cost_ceiling) is None
            or _gate_b_rollback_value(envelope) is None
        ):
            return None
        kind = "AWS_TEARDOWN"
        teardown_ready_binding = {
            "evidence_id": evidence_id,
            "read_authorization": clean_cell(
                teardown_review.get("read_authorization", "")
            ),
            "read_role_or_profile": clean_cell(
                teardown_review.get("read_role_or_profile", "")
            ),
            "read_receipt_digest": clean_cell(
                teardown_review.get("read_receipt_digest", "")
            ),
            "read_valid_until": clean_cell(teardown_review.get("read_valid_until", "")),
            "read_authority_source": clean_cell(
                teardown_review.get("read_authority_source", "")
            ),
            "expected_manifest_or_stack": clean_cell(
                teardown_review.get("expected_manifest_or_stack", "")
            ),
            "resources_retained": retained_resources,
            "shared_dependencies": shared_dependencies,
            "cost_effect": cost_effect,
            "post_teardown_verification": post_action_verification,
        }
    return {
        "kind": kind,
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "account": fields["Account"],
        "region": fields["Region"],
        "environment": fields["Environment"],
        "role_or_profile": fields["Profile or role"],
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {"artifact": artifact, "plan": plan},
        "cost_ceiling": cost_ceiling,
        "rollback_boundary": rollback,
        "expiration": valid_until,
        "retained_resources": retained_resources,
        "shared_dependencies": shared_dependencies,
        "cost_effect": cost_effect,
        "post_action_verification": post_action_verification,
        "teardown_ready_binding": teardown_ready_binding,
    }


def derive_external_authority(
    ctx: Context,
    envelope: dict[str, str],
    lane: str | None,
    construction_authorization: str,
    *,
    cost_posture: str = "",
    aws_progress_state: str | None = None,
    active_artifact: str = "",
    preflight: Mapping[str, Any] | None = None,
    aws_action_phase: str | None = None,
    teardown_review: Mapping[str, Any] | None = None,
    deployment_sequence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project exact current AWS authority without creating new authority."""

    empty: dict[str, Any] = {
        "kind": "NONE",
        "validity": "NONE",
        "authorization_id": "NONE",
        "receipt_digest": "NONE",
        "account": "NONE",
        "region": "NONE",
        "environment": "NONE",
        "role_or_profile": "NONE",
        "resources": [],
        "operations": [],
        "artifact_plan_binding": {"artifact": "NONE", "plan": "NONE"},
        "cost_ceiling": "NONE",
        "rollback_boundary": "NONE",
        "expiration": "NONE",
    }
    verify_text = ctx.texts.get(VERIFY_FILE, "")
    if aws_action_phase == "AWS-30" and deployment_sequence is not None:
        if ctx.has_errors or deployment_sequence.get("issues"):
            return empty
        reconciliation_authority = deployment_sequence.get(
            "reconciliation_read_authority"
        )
        if (
            isinstance(reconciliation_authority, Mapping)
            and reconciliation_authority.get("kind") == "AWS_READ_ONLY"
            and reconciliation_authority.get("validity") == "CURRENT"
            and reconciliation_authority.get("reconciliation_only") in {True, False}
            and reconciliation_authority.get("attempt_id")
            == deployment_sequence.get("attempt_id")
        ):
            return dict(reconciliation_authority)
        if (
            clean_cell(deployment_sequence.get("status", ""))
            == "RECONCILIATION_REQUIRED"
        ):
            required = dict(empty)
            required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
            required["validity"] = "REQUIRED"
            return required
        return empty
    if (
        aws_action_phase == "AWS-40"
        and teardown_review is not None
        and clean_cell(teardown_review.get("status", "")) == "POST_ACTION_REVIEW"
    ):
        if ctx.has_errors or teardown_review.get("issues"):
            return empty
        reconciliation_authority = teardown_review.get("reconciliation_read_authority")
        if (
            isinstance(reconciliation_authority, Mapping)
            and reconciliation_authority.get("kind") == "AWS_READ_ONLY"
            and reconciliation_authority.get("validity") == "CURRENT"
            and reconciliation_authority.get("reconciliation_only") in {True, False}
            and reconciliation_authority.get("attempt_id")
            == teardown_review.get("attempt_id")
        ):
            return dict(reconciliation_authority)
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if ctx.has_errors or construction_authorization == "NONE":
        return empty
    if aws_action_phase not in {"AWS-10", "AWS-20", "AWS-30", "AWS-40", "AWS-50"}:
        return empty
    if aws_action_phase == "AWS-10" and aws_progress_state == "AWS_READ_SCOPE_REQUIRED":
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if aws_action_phase == "AWS-10" and aws_progress_state == "AWS_PREFLIGHT_RUNNING":
        read_authority = _read_preflight_receipt_authority(
            verify_text,
            construction_authorization,
            cost_posture,
            envelope,
            active_artifact,
        )
        if read_authority is not None:
            return read_authority
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if (
        aws_action_phase == "AWS-10"
        and aws_progress_state == "AWS_PREFLIGHT_READY"
        and lane == "read-only"
    ):
        read_authority = _read_preflight_receipt_authority(
            verify_text,
            construction_authorization,
            cost_posture,
            envelope,
            active_artifact,
        )
        return read_authority if read_authority is not None else empty
    if aws_action_phase in {"AWS-30", "AWS-40"}:
        read_authority = _read_preflight_receipt_authority(
            verify_text,
            construction_authorization,
            cost_posture,
            envelope,
            active_artifact,
            allow_one_operation=False,
        )
        if read_authority is not None:
            return read_authority
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    boundary = envelope.get("AWS boundary", "NONE")
    if boundary not in {"READ_ONLY", "MUTATE_LISTED_RESOURCES"}:
        return empty
    if boundary == "READ_ONLY":
        # Gate B bounds the project but never substitutes for the exact
        # owner-authored preflight receipt required for authenticated reads.
        return empty
    if aws_action_phase == "AWS-50":
        if clean_cell((teardown_review or {}).get("status", "")) in {
            "ACTION_TERMINAL_REQUIRED",
            "POST_ACTION_REVIEW",
            "VERIFIED_CLEAN",
            "RESIDUALS_REMAIN",
            "BLOCKED",
        }:
            return empty
        authority = _receipt_external_authority(
            verify_text,
            "Teardown",
            construction_authorization,
            envelope=envelope,
            cost_posture=cost_posture,
            active_artifact=active_artifact,
            teardown_review=teardown_review,
        )
        if authority is not None:
            return authority
        required = dict(empty)
        required["kind"] = "AWS_ACTION_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if aws_action_phase != "AWS-20":
        return empty
    preflight_ready = bool(
        preflight is not None
        and preflight.get("status") == "READY"
        and preflight.get("account_access") == "READ_ONLY_OBSERVED"
        and AWS_PREFLIGHT_ID.fullmatch(clean_cell(preflight.get("preflight_id", "")))
        is not None
    )
    if lane == "explicit-gate" and boundary == "MUTATE_LISTED_RESOURCES":
        if aws_progress_state != "WAITING_AWS_MUTATION_AUTH" or not preflight_ready:
            return empty
        candidates = [
            item
            for item in (
                _receipt_external_authority(
                    verify_text,
                    "Deployment",
                    construction_authorization,
                    envelope=envelope,
                    cost_posture=cost_posture,
                    active_artifact=active_artifact,
                    preflight=preflight,
                ),
            )
            if item is not None
        ]
        if len(candidates) == 1:
            candidate = candidates[0]
            consumed = deployment_sequence or {}
            same_consumed_authority = (
                clean_cell(consumed.get("status", "")) == "CONSUMED"
                and clean_cell(consumed.get("deployment_authorization", ""))
                == clean_cell(candidate.get("authorization_id", ""))
                and clean_cell(consumed.get("deployment_receipt_digest", ""))
                == clean_cell(candidate.get("receipt_digest", ""))
            )
            if not same_consumed_authority:
                return candidate
            candidates = []
        required = dict(empty)
        required["kind"] = "AWS_ACTION_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED" if not candidates else "CONFLICTING"
        return required
    if boundary != "MUTATE_LISTED_RESOURCES" or lane != "fast-dev":
        return empty
    if aws_progress_state != "AWS_PREFLIGHT_READY" or not preflight_ready:
        return empty
    try:
        expiration = parse_future_expiry(envelope.get("AWS authorization validity", ""))
    except ValueError:
        return empty
    environment = envelope.get("AWS environment", "")
    environment_name = environment
    try:
        environment_name, _environment_class = parse_aws_environment(environment)
    except ValueError:
        return empty
    account = _envelope_scalar(envelope, "AWS account", "ACCOUNT")
    region = _envelope_scalar(envelope, "AWS Region", "REGION")
    role = _envelope_scalar(envelope, "AWS role or profile", "ROLE")
    resources = _envelope_values(envelope, "AWS resource allowlist", "RESOURCES")
    allowed_operations = _envelope_values(
        envelope, "AWS allowed operations", "OPERATIONS"
    )
    operations = [
        operation
        for operation in allowed_operations
        if AWS_READ_ONLY_OPERATION.fullmatch(operation) is None
    ]
    if (
        account is None
        or not operations
        or region is None
        or role is None
        or clean_cell(preflight.get("account", "")) != account
        or clean_cell(preflight.get("region", "")) != region
        or clean_cell(preflight.get("environment", "")) != environment_name
        or not _receipt_artifact_matches_gate_b(
            active_artifact, envelope, active_artifact
        )
        or not _receipt_scope_within_gate_b(resources, operations, envelope)
    ):
        return empty
    kind = "FAST_DEV_GATE_B"
    cost_ceiling = envelope.get("AWS cost ceiling", "NONE")
    if not _mutation_cost_within_gate_b(cost_ceiling, envelope, cost_posture):
        return empty
    currency, amount = parse_positive_cost(
        cost_ceiling,
        AWS_COST_CEILING,
        "AWS cost ceiling",
    )
    cost_ceiling = f"{currency}: {amount:.2f}"
    return {
        "kind": kind,
        "validity": "CURRENT",
        "authorization_id": construction_authorization,
        "receipt_digest": "NONE",
        "account": account,
        "region": region,
        "environment": environment_name,
        "role_or_profile": role,
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {
            "artifact": active_artifact,
            "plan": envelope.get("AWS stack or application", "NONE"),
        },
        "cost_ceiling": cost_ceiling,
        "rollback_boundary": envelope.get("AWS rollback boundary", "NONE"),
        "expiration": expiration.isoformat(),
    }


AWS_EXECUTION_CONTRACT_HEADERS = (
    "Execution ID",
    "Authority kind",
    "Authorization ID",
    "Receipt digest",
    "Script SHA-256",
    "Immutable artifact SHA-256",
    "Expected operations",
    "Resources",
    "Account",
    "Region",
    "Environment",
    "Role or profile",
    "Artifact digest",
    "Plan binding",
    "Cost ceiling",
    "Rollback boundary",
    "Valid until",
    "Evidence destination",
    "Status",
)


def _machine_value(value: Any, *labels: str) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = clean_cell(value)
    if cleaned == "NONE" or unresolved(cleaned) or cleaned.startswith("NOT_APPLICABLE"):
        return None
    for label in labels:
        prefix = label + ":"
        if cleaned.startswith(prefix):
            candidate = clean_cell(cleaned[len(prefix) :])
            return candidate if explicit_value(candidate) else None
    return cleaned if explicit_value(cleaned) else None


def _machine_list(values: Any, label: str) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        normalized = _machine_value(value, label)
        if normalized is not None and normalized not in result:
            result.append(normalized)
    return result


def _machine_cost(value: Any) -> dict[str, str] | None:
    normalized = _machine_value(value)
    if normalized is None:
        return None
    match = re.fullmatch(
        r"(?P<currency>[A-Z]{3}):\s*(?P<amount>\d+(?:\.\d{1,2})?)", normalized
    )
    if match is None:
        return None
    try:
        amount = Decimal(match.group("amount"))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return {"currency": match.group("currency"), "amount": f"{amount:.2f}"}


def _execution_contract_rows(verify_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    expected = list(AWS_EXECUTION_CONTRACT_HEADERS)
    for table in markdown_tables(verify_text):
        if not table or table[0] != expected:
            continue
        for cells in table[2:]:
            if len(cells) == len(expected):
                rows.append(dict(zip(expected, cells)))
    return rows


def _iso_datetime(value: str) -> datetime | None:
    cleaned = clean_cell(value)
    normalized = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _reviewed_script_contract(
    ctx: Context, request_match: dict[str, Any]
) -> dict[str, Any] | None:
    rows = [
        row
        for row in _execution_contract_rows(ctx.texts.get(VERIFY_FILE, ""))
        if re.fullmatch(r"AWS-EXEC-\d{4,}", clean_cell(row["Execution ID"]))
    ]
    if not rows:
        return None
    ids = [clean_cell(row["Execution ID"]) for row in rows]
    if len(ids) != len(set(ids)):
        ctx.warning(
            "AWS_EXECUTION_CONTRACT_INVALID",
            "Reviewed AWS execution contracts contain a duplicate AWS-EXEC ID",
            VERIFY_FILE,
        )
        return None
    authorization_id = request_match.get("authorization_id") or "NONE"
    candidates = [
        row for row in rows if clean_cell(row["Authorization ID"]) == authorization_id
    ]
    if len(candidates) != 1:
        ctx.warning(
            "AWS_EXECUTION_CONTRACT_INVALID",
            f"Expected one current AWS-EXEC contract for {authorization_id}; found {len(candidates)}",
            VERIFY_FILE,
        )
        return None
    row = candidates[0]
    execution_id = clean_cell(row["Execution ID"])
    issues: list[str] = []

    expected_scalars = {
        "Authority kind": request_match.get("authority_kind") or "NONE",
        "Receipt digest": request_match.get("receipt_digest") or "NONE",
        "Account": request_match.get("account") or "NONE",
        "Region": request_match.get("region") or "NONE",
        "Environment": request_match.get("environment") or "NONE",
        "Role or profile": request_match.get("role_or_profile") or "NONE",
        "Artifact digest": request_match.get("artifact_digest") or "NONE",
        "Plan binding": request_match.get("plan_binding") or "NONE",
        "Rollback boundary": request_match.get("rollback_boundary") or "NONE",
    }
    cost = request_match.get("cost_ceiling")
    expected_scalars["Cost ceiling"] = (
        f"{cost['currency']}: {cost['amount']}" if isinstance(cost, dict) else "NONE"
    )
    for field_name, expected_value in expected_scalars.items():
        if clean_cell(row[field_name]) != expected_value:
            issues.append(f"{field_name} does not match current authority")

    operations = _split_authority_values(row["Expected operations"])
    resources = _split_authority_values(row["Resources"])
    if not operations or not set(operations).issubset(set(request_match["operations"])):
        issues.append("Expected operations exceed current authority")
    if not resources or not set(resources).issubset(set(request_match["resources"])):
        issues.append("Resources exceed current authority")

    script_digest = clean_cell(row["Script SHA-256"])
    artifact_digest = clean_cell(row["Immutable artifact SHA-256"])
    digest_pattern = re.compile(r"sha256:[0-9a-f]{64}")
    bindings = [
        ("SCRIPT_SHA256", script_digest),
        ("IMMUTABLE_ARTIFACT_SHA256", artifact_digest),
    ]
    valid_bindings = [item for item in bindings if digest_pattern.fullmatch(item[1])]
    other_values = [value for _kind, value in bindings if value != "NONE"]
    if len(valid_bindings) != 1 or len(other_values) != 1:
        issues.append(
            "exactly one reviewed script or immutable artifact digest is required"
        )

    valid_until = _iso_datetime(row["Valid until"])
    authority_expiry = _iso_datetime(request_match.get("expires_at") or "")
    if (
        valid_until is None
        or authority_expiry is None
        or valid_until <= datetime.now(timezone.utc)
        or valid_until > authority_expiry
    ):
        issues.append("Valid until is expired or exceeds current authority")
    evidence_destination = clean_cell(row["Evidence destination"])
    if re.fullmatch(r"EV-[0-9]{4,}", evidence_destination) is None:
        issues.append("Evidence destination must be one stable EV ID")
    if clean_cell(row["Status"]) != "CURRENT":
        issues.append("Status must be CURRENT")

    if issues:
        ctx.warning(
            "AWS_EXECUTION_CONTRACT_INVALID",
            f"{execution_id}: " + "; ".join(issues),
            VERIFY_FILE,
        )
        return None
    binding_kind, binding_digest = valid_bindings[0]
    return {
        "execution_id": execution_id,
        "content_binding": {"kind": binding_kind, "sha256": binding_digest},
        "expected_operations": operations,
        "resources": resources,
        "valid_until": clean_cell(row["Valid until"]),
        "evidence_destination": evidence_destination,
    }


def derive_request_match(ctx: Context, authority: dict[str, Any]) -> dict[str, Any]:
    raw_validity = clean_cell(str(authority.get("validity", "NONE")))
    validity = (
        raw_validity
        if raw_validity in {"CURRENT", "NONE", "STALE", "BLOCKED"}
        else "BLOCKED"
    )
    binding = authority.get("artifact_plan_binding")
    binding = binding if isinstance(binding, dict) else {}
    raw_teardown_binding = authority.get("teardown_ready_binding")
    request_match: dict[str, Any] = {
        "schema_version": 1,
        "validity": validity,
        "authority_kind": _machine_value(authority.get("kind")),
        "authorization_id": _machine_value(authority.get("authorization_id")),
        "receipt_digest": _machine_value(authority.get("receipt_digest")),
        "account": _machine_value(authority.get("account"), "ACCOUNT"),
        "region": _machine_value(authority.get("region"), "REGION"),
        "environment": _machine_value(authority.get("environment"), "ENVIRONMENT"),
        "role_or_profile": _machine_value(authority.get("role_or_profile"), "ROLE"),
        "resources": _machine_list(authority.get("resources"), "RESOURCES"),
        "operations": _machine_list(authority.get("operations"), "OPERATIONS"),
        "artifact_digest": _machine_value(binding.get("artifact"), "EXACT_DIGEST"),
        "plan_binding": _machine_value(binding.get("plan"), "STACK"),
        "cost_ceiling": _machine_cost(authority.get("cost_ceiling")),
        "rollback_boundary": _machine_value(
            authority.get("rollback_boundary"), "ROLLBACK"
        ),
        "expires_at": _machine_value(authority.get("expiration")),
        "allowed_execution_lanes": [],
        "reviewed_script": None,
        "teardown_ready_binding": None,
    }
    if request_match["authority_kind"] == "AWS_TEARDOWN" and isinstance(
        raw_teardown_binding, Mapping
    ):
        request_match["teardown_ready_binding"] = {
            "evidence_id": _machine_value(raw_teardown_binding.get("evidence_id")),
            "read_authorization": _machine_value(
                raw_teardown_binding.get("read_authorization")
            ),
            "read_role_or_profile": _machine_value(
                raw_teardown_binding.get("read_role_or_profile"), "ROLE"
            ),
            "read_receipt_digest": _machine_value(
                raw_teardown_binding.get("read_receipt_digest")
            ),
            "read_valid_until": _machine_value(
                raw_teardown_binding.get("read_valid_until")
            ),
            "read_authority_source": _machine_value(
                raw_teardown_binding.get("read_authority_source")
            ),
            "expected_manifest_or_stack": _machine_value(
                raw_teardown_binding.get("expected_manifest_or_stack")
            ),
            "resources_retained": _machine_list(
                raw_teardown_binding.get("resources_retained"), "RESOURCES"
            ),
            "shared_dependencies": _machine_list(
                raw_teardown_binding.get("shared_dependencies"), "RESOURCES"
            ),
            "cost_effect": _machine_value(raw_teardown_binding.get("cost_effect")),
            "post_teardown_verification": _machine_value(
                raw_teardown_binding.get("post_teardown_verification")
            ),
        }
    if validity != "CURRENT":
        return request_match
    request_match["allowed_execution_lanes"] = ["STRUCTURED_API"]
    reviewed_script = _reviewed_script_contract(ctx, request_match)
    if reviewed_script is not None:
        request_match["allowed_execution_lanes"].append("REVIEWED_SCRIPT")
        request_match["reviewed_script"] = reviewed_script
    return request_match


def _aws_action_transition_projection(
    request_match: Mapping[str, Any] | None,
    sequence: Mapping[str, Any],
    *,
    authority_kind: str,
    authorization_field: str,
    receipt_digest_field: str,
) -> dict[str, Any]:
    """Bind one consumed journal attempt to its exact pre-call request ceiling.

    This projection is not mutation authority. It exists only so the optional
    hook can prove that the same-session call following STARTED is identical to
    the request that was current immediately before the journal append.
    """

    empty: dict[str, Any] = {
        "schema_version": 1,
        "status": "NONE",
        "attempt_id": "NONE",
        "authority_kind": "NONE",
        "request_match_sha256": "NONE",
        "request_match": {},
    }
    if (
        clean_cell(sequence.get("status", "")) != "ACTION_TERMINAL_REQUIRED"
        or sequence.get("issues")
        or not isinstance(request_match, Mapping)
        or request_match.get("schema_version") != 1
        or request_match.get("validity") != "CURRENT"
        or request_match.get("authority_kind") != authority_kind
        or clean_cell(request_match.get("authorization_id", ""))
        != clean_cell(sequence.get(authorization_field, ""))
        or clean_cell(request_match.get("receipt_digest", ""))
        != clean_cell(sequence.get(receipt_digest_field, ""))
    ):
        return empty
    attempt_id = clean_cell(sequence.get("attempt_id", ""))
    pattern = (
        AWS_TEARDOWN_ATTEMPT_ID
        if authority_kind == "AWS_TEARDOWN"
        else AWS_DEPLOYMENT_ATTEMPT_ID
    )
    if pattern.fullmatch(attempt_id) is None:
        return empty
    normalized = dict(request_match)
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                normalized,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
    )
    return {
        **empty,
        "status": "BOUND",
        "attempt_id": attempt_id,
        "authority_kind": authority_kind,
        "request_match_sha256": digest,
        "request_match": normalized,
    }


PROMPT_DOCS_ONLY_AWS_MODES = frozenset({"REQ-10", "DESIGN-10", "BUG-10"})
PROMPT_READ_ONLY_AWS_MODES = frozenset({"AWS-10", "AWS-30", "AWS-40"})
PROMPT_MUTATION_AWS_MODES = frozenset({"AWS-20", "AWS-50"})


def derive_current_prompt_aws_mode(next_prompt: str) -> str:
    """Return the maximum phase mode; authority is projected separately."""

    if next_prompt in PROMPT_DOCS_ONLY_AWS_MODES:
        return "DOCS_ONLY"
    if next_prompt in PROMPT_READ_ONLY_AWS_MODES:
        return "READ_ONLY"
    if next_prompt in PROMPT_MUTATION_AWS_MODES:
        return "MUTATION"
    return "NONE"


def derive_aws_mode_boundary(
    lane: str | None,
    envelope: Mapping[str, str],
    next_prompt: str,
    external_authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Separate planned ceilings, prompt capability, and current authority."""

    project_lane = lane if lane in AWS_LANES else "NONE"
    proposed_gate_b = clean_cell(envelope.get("AWS boundary", "NONE")).upper()
    gate_b_maximum = proposed_gate_b if proposed_gate_b in AWS_BOUNDARIES else "NONE"
    local_task_modes = ["NONE"] if gate_b_maximum == "NONE" else ["NONE", "DOCS_ONLY"]
    current_prompt_mode = derive_current_prompt_aws_mode(next_prompt)
    external_kind = clean_cell(external_authority.get("kind", "NONE")) or "NONE"
    external_validity = clean_cell(external_authority.get("validity", "NONE")) or "NONE"
    read_authorized = (
        current_prompt_mode == "READ_ONLY"
        and external_kind == "AWS_READ_ONLY"
        and external_validity == "CURRENT"
    )
    mutation_authorized = (
        current_prompt_mode == "MUTATION"
        and external_kind in {"AWS_DEPLOYMENT", "AWS_TEARDOWN", "FAST_DEV_GATE_B"}
        and external_validity == "CURRENT"
    )
    return {
        "project_lane": project_lane,
        "local_task_modes": local_task_modes,
        "current_prompt_mode": current_prompt_mode,
        "gate_b_maximum": gate_b_maximum,
        "external_authority_kind": external_kind,
        "external_authority_validity": external_validity,
        "account_access_authorized": read_authorized or mutation_authorized,
        "mutation_authorized": mutation_authorized,
    }


def _summary_table(ctx: Context, path: str, heading: str) -> dict[str, str]:
    text = ctx.texts.get(path, "")
    if not text:
        return {}
    try:
        return table_after_heading(text, heading)
    except ValueError:
        return {}


def _summary_value(value: object, fallback: str) -> str:
    cleaned = clean_cell(value)
    return cleaned if explicit_value(cleaned, allow_none=False) else fallback


def _summary_bullet(text: str, label: str) -> str:
    match = re.search(rf"(?m)^- {re.escape(label)}:[ \t]*(?P<value>.+?)[ \t]*$", text)
    return clean_cell(match.group("value")) if match else ""


# fmt: off
def derive_document_summary_specifications(ctx: Context, *, classification: str, lifecycle_state: str, next_prompt: str, project: Mapping[str, Any], prd_fields: Mapping[str, str], gate_a: str, gate_b: str, tasks: TaskSummary, release_decision: str, release_evidence_cutoff: str, aws_authorization: str, external_authority: Mapping[str, Any], interaction: Mapping[str, Any], active_artifact: str, deployment_sequence: Mapping[str, Any]) -> list[dict[str, Any]]:
# fmt: on
    """Normalize existing canonical values for the presentation-only summaries."""

    template_like = classification in {"TEMPLATE_SOURCE", "UNCONFIGURED_TEMPLATE"}
    prd_card = _summary_table(ctx, PRD_FILE, "### Gate A — readiness card")
    task_snapshot = _summary_table(ctx, TASKS_FILE, "## Active execution snapshot")
    verify_scope = _summary_table(ctx, VERIFY_FILE, "## Active evidence scope")
    runbook_boundary = _summary_table(ctx, RUNBOOK_FILE, "## Active operational boundary")
    verify_text = ctx.texts.get(VERIFY_FILE, "")
    bugfix_text = ctx.texts.get(BUGFIX_FILE, "")

    requirements_id = prd_fields.get("requirements_revision")
    design_id = prd_fields.get("design_revision")
    authorization_id = prd_fields.get("construction_authorization")
    checkpoint = _summary_value(task_snapshot.get("Last checkpoint"), "None")
    cutoff = _summary_value(release_evidence_cutoff, "Not yet recorded")
    updated = next(
        (
            value
            for value in (
                cutoff if cutoff != "Not yet recorded" else "",
                checkpoint if checkpoint != "None" else "",
                design_id,
                requirements_id,
            )
            if value
        ),
        "Current canonical records",
    )

    observed_ids: set[str] = set()
    failed_ids: set[str] = set()
    for line in verify_text.splitlines():
        evidence_ids = re.findall(r"\b(?:AWS-)?EV-\d{4,}\b", line)
        if not evidence_ids:
            continue
        upper = line.upper()
        if any(status in upper for status in ("VERIFIED", "PASSED", "OBSERVED")):
            observed_ids.update(evidence_ids)
        if any(status in upper for status in ("FAILED", "STALE", "BLOCKED")):
            failed_ids.update(evidence_ids)

    local_observed = release_decision in {"READY_TO_DEPLOY", "RELEASE_VERIFIED"}
    deployment_status = clean_cell(deployment_sequence.get("status", "NOT_ACTIVE"))
    deployment_observed = deployment_status == "RECONCILED"
    requirements_approved = gate_a == "APPROVED_FOR_DESIGN"
    design_approved = gate_b == "APPROVED_FOR_CONSTRUCTION"
    guidance_ready = not any(
        item.code.startswith("AWS_CORE_") and item.severity == "ERROR"
        for item in ctx.diagnostics
    )
    # fmt: off
    claim_rows = (
        ("Requirements are approved", requirements_approved, ("Owner confirmed", requirements_id, "Does not approve construction"), ("Not yet observed", "None", "Gate A is not approved")),
        ("Technical design is approved", design_approved, ("Owner confirmed", design_id, "Does not authorize AWS account work"), ("Not yet observed", "None", "Gate B is not approved")),
        ("Current AWS guidance informed the plan", guidance_ready and not template_like, ("Source verified", "Current AWS Core evidence", "Source guidance is not deployment evidence"), ("Not yet observed", "None", "Source guidance is not deployment evidence")),
        ("Local release checks passed", local_observed, ("Locally observed", release_decision, "Local evidence does not prove AWS behavior"), ("Not yet observed", "None", "Local evidence does not prove AWS behavior")),
        ("Application is deployed", deployment_observed, ("Deployed observed", "Deployment reconciliation", "Bound to the observed environment"), ("Not authorized", "None", "No deployment evidence or authority")),
    )
    # fmt: on
    claims = []
    for claim, ready, current, pending in claim_rows:
        maturity, evidence, limitation = current if ready else pending
        claims.append(
            {
                "claim": claim,
                "maturity": maturity,
                "evidence": evidence,
                "limitation": limitation,
            }
        )

    task_progress = (
        f"{len(tasks.done)} of {tasks.total} tasks complete"
        if tasks.total
        else "No tasks generated"
    )
    bug_title = _summary_bullet(bugfix_text, "Title")
    bug_active = active_artifact == BUGFIX_FILE or explicit_value(bug_title)
    bugfix = {
        "status": "Active bounded defect" if bug_active else "No active bounded defect",
        "defect": _summary_value(bug_title, "None") if bug_active else "None",
        "impact": "Recorded in the defect contract" if bug_active else "None",
        "reproduction": "Pending evidence" if bug_active else "Not active",
        "root_cause": "Pending evidence" if bug_active else "Not active",
        "repair": "Not started" if bug_active else "Not active",
        "regression": "Pending evidence" if bug_active else "Not active",
        "architecture": "Not yet assessed" if bug_active else "None",
        "environment": (
            _summary_value(_summary_bullet(bugfix_text, "Environment"), "Not recorded")
            if bug_active
            else "Not active"
        ),
        "requirements": (
            _summary_value(_summary_bullet(bugfix_text, "Related PRD requirements"), "None")
            if bug_active
            else "None"
        ),
        "updated": updated,
    }
    account_access = (
        external_authority.get("validity") == "CURRENT"
        and external_authority.get("kind")
        in {"AWS_READ_ONLY", "AWS_DEPLOYMENT", "AWS_TEARDOWN", "FAST_DEV_GATE_B"}
    )
    environment = _summary_value(
        runbook_boundary.get("Region and environment"),
        (
            f"Development in {project.get('region')}"
            if project.get("region")
            else "Development"
        ),
    )
    # fmt: off
    return build_summary_specifications({
        "template_like": template_like, "lifecycle_state": lifecycle_state, "next_prompt": next_prompt,
        "owner_stage": interaction.get("owner_stage"), "action_kind": interaction.get("action_kind"),
        "automatic_continuation_allowed": interaction.get("automatic_continuation_allowed"),
        "gate_a": gate_a, "gate_b": gate_b, "requirements_revision": requirements_id,
        "design_revision": design_id, "construction_authorization": authorization_id,
        "aws_authorization": aws_authorization, "aws_account_access_authorized": account_access,
        "updated": updated, "product_outcome": _summary_value(prd_card.get("Outcome"), "Not yet confirmed"),
        "release_boundary": _summary_value(prd_card.get("Scope"), "Not yet confirmed"),
        "region_and_cost": "Not yet recorded" if template_like else f"{project.get('region') or 'Region not recorded'}; {project.get('cost_posture') or 'Cost posture not recorded'}",
        "record_identities": "Not yet initialized" if template_like else " / ".join(item for item in (requirements_id, design_id, authorization_id) if item),
        "tasks": {
            "progress": task_progress, "plan_revision": tasks.plan_revision,
            "wave": _summary_value(task_snapshot.get("Current wave"), "None"),
            "active": ", ".join(tasks.active) if tasks.active else "None",
            "readiness": tasks.plan_state.replace("_", " ").title(),
            "blocker": ", ".join(tasks.blocked) if tasks.blocked else "None",
            "checkpoint": checkpoint, "known_green": _summary_value(task_snapshot.get("Last known-green commit"), "None"),
            "updated": checkpoint if checkpoint != "None" else updated,
        },
        "verify": {
            "release_result": release_decision.replace("_", " ").title(),
            "observed_count": str(len(observed_ids)), "failed_count": str(len(failed_ids)),
            "unobserved": "Recovery and teardown" if deployment_observed else "AWS deployment, recovery, and teardown" if local_observed else "Local build, AWS deployment, recovery, and teardown",
            "cutoff": _summary_value(verify_scope.get("Evidence cutoff"), cutoff),
            "updated": cutoff if cutoff != "Not yet recorded" else updated, "claims": claims,
        },
        "operations": {
            "environment": environment,
            "deployment_state": "Deployment observed" if deployment_observed else "Not deployed" if deployment_status in {"", "NOT_ACTIVE", "NONE"} else deployment_status.replace("_", " ").title(),
            "authority": str(external_authority.get("kind", "None")).replace("_", " ").title() if account_access else "None",
            "safe_action": "Only the exact authorized AWS operation" if account_access else "Local validation only",
            "deployment_approval": "Authorized only for the current deployment" if account_access and external_authority.get("kind") in {"AWS_DEPLOYMENT", "FAST_DEV_GATE_B"} else "Not authorized",
            "teardown_approval": "Authorized only for the current teardown" if account_access and external_authority.get("kind") == "AWS_TEARDOWN" else "Not authorized",
            "recovery_state": "Not yet observed",
            "emergency_state": "Follow the current runbook and authority" if deployment_observed else "No deployed environment exists",
            "updated": updated,
        },
        "bugfix": bugfix,
    })
    # fmt: on



def build_report(
    ctx: Context,
    lifecycle_state: str,
    next_prompt: str,
    prd_fields: dict[str, str],
    tasks: TaskSummary,
    *,
    manifest: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    release_decision: str = "NOT_READY",
    envelope: dict[str, str] | None = None,
    aws_execution_planning_ready: bool = False,
    design_aws_core_ready: bool = False,
    design_contract: DesignContract | None = None,
    adr_rationale: Mapping[str, Any] | None = None,
    intake_contract: IntakeFoundationContract | None = None,
    coverage_contract: CoverageContract | None = None,
    requirements_contract: RequirementsContract | None = None,
    aws_core_usage: Mapping[str, Any] | None = None,
    aws_execution: Mapping[str, Any] | None = None,
    owner_stage_hint: str | None = None,
    active_artifact: str = "",
    deployment_sequence: Mapping[str, Any] | None = None,
    teardown_sequence: Mapping[str, Any] | None = None,
    release_evidence_cutoff: str = "NONE",
    req_aws_core_materiality: str = "OPTIONAL",
    req_aws_core_ready: bool = True,
    aws_lifecycle_intent_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = manifest or {}
    state = state or {}
    setup = state.get("setup") if isinstance(state.get("setup"), dict) else {}
    project = state.get("project") if isinstance(state.get("project"), dict) else {}
    lifecycle = (
        state.get("lifecycle") if isinstance(state.get("lifecycle"), dict) else {}
    )
    envelope = envelope or {}
    aws_execution_projection = dict(aws_execution or {})
    deployment_sequence_projection = dict(deployment_sequence or {})
    teardown_sequence_projection = dict(teardown_sequence or {})
    adr_rationale_projection = dict(adr_rationale or empty_adr_rationale())
    aws_sequence_conflict = aws_deployment_teardown_sequence_conflict(
        deployment_sequence_projection, teardown_sequence_projection
    )
    if aws_sequence_conflict:
        if not any(
            item.code == "AWS_DEPLOYMENT_TEARDOWN_CONFLICT" for item in ctx.diagnostics
        ):
            ctx.error(
                "AWS_DEPLOYMENT_TEARDOWN_CONFLICT",
                "Open deployment and teardown journal epochs cannot coexist; close one sequence before continuing",
                VERIFY_FILE,
            )
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
    lifecycle_intent_projection = dict(
        aws_lifecycle_intent_record
        or {
            "value": "NONE",
            "source": "NONE",
            "recorded_at": "NONE",
            "provenance_status": "CURRENT",
            "authorizes_aws_access": False,
            "authorizes_mutation": False,
        }
    )
    residual_disposition_projection = derive_aws_residual_disposition(
        lifecycle_intent_projection, teardown_sequence_projection
    )
    aws_progress_state = (
        str(aws_execution_projection.get("progress_state"))
        if aws_execution_projection.get("active") is True
        else None
    )
    if design_contract is None:
        design_contract = DesignContract(
            design_revision=(
                prd_fields.get("design_revision") or lifecycle.get("design_revision")
            )
        )
    if coverage_contract is None:
        coverage_contract = CoverageContract()
    if intake_contract is None:
        intake_contract = IntakeFoundationContract()
    if requirements_contract is None:
        requirements_contract = RequirementsContract()
    if ctx.template_source:
        classification = "TEMPLATE_SOURCE"
    elif setup.get("status") in {
        "UNCONFIGURED_TEMPLATE",
        "{{SETUP_STATUS}}",
    }:
        classification = "UNCONFIGURED_TEMPLATE"
    elif project.get("mode") == "brownfield":
        classification = "ACTIVE_BROWNFIELD"
    else:
        classification = "ACTIVE_GREENFIELD"
    if ctx.has_errors:
        status = "BLOCKED"
    elif lifecycle_state == "INTAKE_REQUIRED":
        status = "READY"
    else:
        status = "RESUME"
    lane = project.get("aws_lane")
    aws_access = {
        None: "NOT_USED",
        "documentation-only": "DOCUMENTATION_ONLY",
        "read-only": "READ_ONLY",
        "fast-dev": "AUTHORIZED_BOUNDARY_REQUIRED",
        "explicit-gate": "EXACT_AUTHORIZATION_REQUIRED",
    }.get(lane, "NOT_USED")
    gate_a = prd_fields.get("gate_a") or lifecycle.get("gate_a") or "BLOCKED"
    gate_b = prd_fields.get("gate_b") or lifecycle.get("gate_b") or "BLOCKED"
    resolved_owner_stage = (
        owner_stage_hint
        if owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}
        else _owner_stage_from_gates(gate_a, gate_b)
    )
    authorization_id = prd_fields.get("construction_authorization") or lifecycle.get(
        "construction_authorization"
    )
    gate_b_authorization = (
        authorization_id
        if not ctx.has_errors and gate_b == "APPROVED_FOR_CONSTRUCTION"
        else "NONE"
    )
    deployment_status = clean_cell(deployment_sequence_projection.get("status", ""))
    auditable_status = (
        deployment_status
        in {
            "ACTION_TERMINAL_REQUIRED",
            "RECONCILIATION_REQUIRED",
            "RECONCILED",
            "BLOCKED",
        }
        or (deployment_status == "CONSUMED" and release_decision != "READY_TO_DEPLOY")
        or (
            deployment_status == "NOT_ACTIVE" and release_decision == "RELEASE_VERIFIED"
        )
    )
    deployment_authority_restricted = bool(
        not ctx.has_errors
        and not deployment_sequence_projection.get("issues")
        and auditable_status
    )
    teardown_status = clean_cell(teardown_sequence_projection.get("status", ""))
    teardown_attempt_id = clean_cell(teardown_sequence_projection.get("attempt_id", ""))
    teardown_action_status = clean_cell(
        teardown_sequence_projection.get("action_status", "")
    )
    teardown_attempt_unreconciled = bool(
        AWS_TEARDOWN_ATTEMPT_ID.fullmatch(teardown_attempt_id)
        and teardown_action_status in {"STARTED", *AWS_TEARDOWN_TERMINAL_STATUSES}
        and teardown_status
        in {"ACTION_TERMINAL_REQUIRED", "POST_ACTION_REVIEW", "BLOCKED"}
    )
    teardown_authority_restricted = bool(teardown_attempt_unreconciled)
    restricted_construction_authorization = (
        "NONE"
        if deployment_authority_restricted or teardown_authority_restricted
        else gate_b_authorization
    )
    aws_authorization = "NONE"
    deployment_journal_closure_authority = derive_deployment_journal_closure_authority(
        deployment_sequence_projection,
        next_prompt,
        restricted_closure=deployment_authority_restricted,
    )
    teardown_journal_closure_authority = derive_teardown_journal_closure_authority(
        teardown_sequence_projection,
        next_prompt,
        restricted_closure=teardown_authority_restricted,
    )
    external_authority = derive_external_authority(
        ctx,
        envelope,
        lane,
        restricted_construction_authorization,
        cost_posture=str(project.get("cost_posture", "")),
        aws_progress_state=aws_progress_state,
        active_artifact=active_artifact,
        aws_action_phase=next_prompt,
        teardown_review=teardown_sequence_projection,
        deployment_sequence=deployment_sequence_projection,
        preflight=(
            aws_execution_projection.get("preflight")
            if isinstance(aws_execution_projection.get("preflight"), Mapping)
            else None
        ),
    )
    aws_lifecycle_intent_write_authority = derive_aws_lifecycle_intent_write_authority(
        ctx,
        tasks,
        release_decision,
        deployment_sequence_projection,
        teardown_sequence_projection,
        external_authority,
        lifecycle_intent=lifecycle_intent_projection,
    )
    construction_authorization = (
        "NONE"
        if aws_lifecycle_intent_write_authority.get("valid") is True
        else restricted_construction_authorization
    )
    write_authority = derive_write_authority(
        ctx, envelope, tasks, construction_authorization
    )
    if external_authority.get("validity") == "CURRENT" and external_authority.get(
        "kind"
    ) in {"AWS_READ_ONLY", "AWS_DEPLOYMENT", "AWS_TEARDOWN", "FAST_DEV_GATE_B"}:
        projected_authorization = external_authority.get("authorization_id")
        if isinstance(projected_authorization, str):
            aws_authorization = projected_authorization
    external_authority["request_match"] = derive_request_match(ctx, external_authority)
    transition_authority: dict[str, Any] = {
        "kind": "NONE",
        "validity": "NONE",
        "request_match": {},
    }
    transition_sequence: Mapping[str, Any] = {}
    transition_kind = "NONE"
    transition_authorization_field = ""
    transition_receipt_field = ""
    if not aws_sequence_conflict and deployment_status == "ACTION_TERMINAL_REQUIRED":
        transition_authority = derive_external_authority(
            ctx,
            envelope,
            lane,
            gate_b_authorization,
            cost_posture=str(project.get("cost_posture", "")),
            aws_progress_state=aws_progress_state,
            active_artifact=active_artifact,
            aws_action_phase="AWS-20",
            teardown_review=teardown_sequence_projection,
            deployment_sequence={},
            preflight=(
                aws_execution_projection.get("preflight")
                if isinstance(aws_execution_projection.get("preflight"), Mapping)
                else None
            ),
        )
        transition_sequence = deployment_sequence_projection
        transition_kind = clean_cell(transition_authority.get("kind", ""))
        transition_authorization_field = "deployment_authorization"
        transition_receipt_field = "deployment_receipt_digest"
    elif not aws_sequence_conflict and teardown_status == "ACTION_TERMINAL_REQUIRED":
        transition_review = {
            **teardown_sequence_projection,
            "status": "READY_FOR_TEARDOWN",
            "evidence_id": teardown_sequence_projection.get(
                "ready_evidence_id", "NONE"
            ),
        }
        transition_authority = derive_external_authority(
            ctx,
            envelope,
            lane,
            gate_b_authorization,
            cost_posture=str(project.get("cost_posture", "")),
            aws_progress_state=aws_progress_state,
            active_artifact=active_artifact,
            aws_action_phase="AWS-50",
            teardown_review=transition_review,
            deployment_sequence=deployment_sequence_projection,
            preflight=(
                aws_execution_projection.get("preflight")
                if isinstance(aws_execution_projection.get("preflight"), Mapping)
                else None
            ),
        )
        transition_sequence = teardown_sequence_projection
        transition_kind = "AWS_TEARDOWN"
        transition_authorization_field = "teardown_authorization"
        transition_receipt_field = "teardown_receipt_digest"
    transition_request_match = (
        derive_request_match(ctx, transition_authority)
        if transition_kind != "NONE"
        else None
    )
    aws_action_transition = _aws_action_transition_projection(
        transition_request_match,
        transition_sequence,
        authority_kind=transition_kind,
        authorization_field=transition_authorization_field,
        receipt_digest_field=transition_receipt_field,
    )
    (
        owner_decision_brief, owner_decision_inventory, owner_brief_issues
    ) = derive_owner_decision_brief(
        ctx.texts.get(PRD_FILE, ""),
        prd_fields,
        intake_contract,
        requirements_contract,
        design_contract,
        envelope,
        has_errors=ctx.has_errors,
        enabled=classification not in {"TEMPLATE_SOURCE", "UNCONFIGURED_TEMPLATE"},
    )
    for code, message in owner_brief_issues:
        if code == "OWNER_BRIEF_SOURCE_STALE":
            ctx.warning(code, message, PRD_FILE)
        else:
            ctx.error(code, message, PRD_FILE)
    owner_answer_confirmation = derive_owner_answer_confirmation(
        ctx.texts.get(PRD_FILE, ""), intake_contract
    )
    diagnostic_codes = [item.code for item in ctx.diagnostics]
    aws_mutation_authority_ready = external_authority.get(
        "validity"
    ) == "CURRENT" and external_authority.get("kind") in {
        "AWS_DEPLOYMENT",
        "AWS_TEARDOWN",
        "FAST_DEV_GATE_B",
    }
    remediation = derive_remediation(
        ctx,
        classification=classification,
        gate_a=gate_a,
        gate_b=gate_b,
        envelope=envelope,
        tasks=tasks,
        requirements_revision=prd_fields.get("requirements_revision"),
        design_revision=prd_fields.get("design_revision"),
        owner_stage_hint=resolved_owner_stage,
    )
    interaction = derive_interaction(
        lifecycle_state,
        next_prompt,
        has_errors=ctx.has_errors,
        diagnostic_codes=diagnostic_codes,
        design_aws_core_ready=design_aws_core_ready,
        aws_execution_planning_ready=aws_execution_planning_ready,
        remediation=remediation,
        owner_stage_hint=resolved_owner_stage,
        aws_progress_state=aws_progress_state,
        aws_mutation_authority_ready=aws_mutation_authority_ready,
        aws_lane=lane,
        aws_read_authority_required=(
            external_authority.get("kind") == "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        ),
        req_aws_core_materiality=req_aws_core_materiality,
        req_aws_core_ready=req_aws_core_ready,
    )
    if (
        classification == "UNCONFIGURED_TEMPLATE"
        and remediation["next_action"]["action_kind"]
        == "COMPLETE_PREREQUISITE_CHECKLIST"
    ):
        interaction = derive_unconfigured_template_interaction(diagnostic_codes)
    context_plan = derive_context_plan(
        interaction,
        tasks,
        coverage_contract,
        next_prompt=next_prompt,
        restricted_deployment_closure=deployment_authority_restricted,
        restricted_teardown_closure=teardown_authority_restricted,
        source_texts=ctx.texts,
        adr_rationale=adr_rationale_projection,
    )
    context_issues = context_plan.pop("_resolution_issues", [])
    if context_issues:
        for issue in context_issues:
            issue_path = str(issue.get("path", ""))
            ctx.error(
                "CONTEXT_SOURCE_INVALID",
                str(issue.get("reason", "context source could not be resolved")),
                issue_path if issue_path != "NONE" else None,
            )
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
        status = "BLOCKED"
        construction_authorization = "NONE"
        aws_authorization = "NONE"
        write_authority = derive_write_authority(ctx, envelope, tasks, "NONE")
        deployment_journal_closure_authority = (
            derive_deployment_journal_closure_authority(
                deployment_sequence_projection,
                next_prompt,
                restricted_closure=False,
            )
        )
        teardown_journal_closure_authority = derive_teardown_journal_closure_authority(
            teardown_sequence_projection,
            next_prompt,
            restricted_closure=False,
        )
        external_authority = derive_external_authority(
            ctx,
            envelope,
            lane,
            "NONE",
            cost_posture=str(project.get("cost_posture", "")),
            aws_progress_state=aws_progress_state,
            active_artifact=active_artifact,
            aws_action_phase=next_prompt,
            teardown_review=teardown_sequence_projection,
            deployment_sequence=deployment_sequence_projection,
            preflight=(
                aws_execution_projection.get("preflight")
                if isinstance(aws_execution_projection.get("preflight"), Mapping)
                else None
            ),
        )
        external_authority["request_match"] = derive_request_match(
            ctx, external_authority
        )
        aws_lifecycle_intent_write_authority = (
            derive_aws_lifecycle_intent_write_authority(
                ctx,
                tasks,
                release_decision,
                deployment_sequence_projection,
                teardown_sequence_projection,
                external_authority,
                lifecycle_intent=lifecycle_intent_projection,
            )
        )
        (
            owner_decision_brief, owner_decision_inventory, _owner_brief_issues
        ) = derive_owner_decision_brief(
            ctx.texts.get(PRD_FILE, ""),
            prd_fields,
            intake_contract,
            requirements_contract,
            design_contract,
            envelope,
            has_errors=ctx.has_errors,
            enabled=classification not in {"TEMPLATE_SOURCE", "UNCONFIGURED_TEMPLATE"},
        )
        diagnostic_codes = [item.code for item in ctx.diagnostics]
        remediation = derive_remediation(
            ctx,
            classification=classification,
            gate_a=gate_a,
            gate_b=gate_b,
            envelope=envelope,
            tasks=tasks,
            requirements_revision=prd_fields.get("requirements_revision"),
            design_revision=prd_fields.get("design_revision"),
            owner_stage_hint=resolved_owner_stage,
        )
        interaction = derive_interaction(
            lifecycle_state,
            next_prompt,
            has_errors=True,
            diagnostic_codes=diagnostic_codes,
            design_aws_core_ready=design_aws_core_ready,
            aws_execution_planning_ready=aws_execution_planning_ready,
            remediation=remediation,
            owner_stage_hint=resolved_owner_stage,
            aws_progress_state=aws_progress_state,
            aws_mutation_authority_ready=False,
            aws_lane=lane,
            aws_read_authority_required=False,
            req_aws_core_materiality=req_aws_core_materiality,
            req_aws_core_ready=req_aws_core_ready,
        )
        if (
            classification == "UNCONFIGURED_TEMPLATE"
            and remediation["next_action"]["action_kind"]
            == "COMPLETE_PREREQUISITE_CHECKLIST"
        ):
            interaction = derive_unconfigured_template_interaction(diagnostic_codes)
        context_plan = derive_context_plan(
            interaction,
            tasks,
            coverage_contract,
            next_prompt=next_prompt,
            restricted_deployment_closure=False,
            restricted_teardown_closure=False,
            source_texts=ctx.texts,
            adr_rationale=adr_rationale_projection,
        )
        context_plan.pop("_resolution_issues", None)
    summary_sources: dict[str, str] = {}
    for summary_path in DOCUMENT_SUMMARY_FILES:
        summary_text = ctx.presentation_texts.get(summary_path)
        if summary_text is None:
            safe_read_text(ctx, summary_path)
            summary_text = ctx.presentation_texts.get(summary_path)
        if summary_text is not None:
            summary_sources[summary_path] = summary_text
    # fmt: off
    summary_specifications = derive_document_summary_specifications(ctx, classification=classification, lifecycle_state=lifecycle_state, next_prompt=next_prompt, project=project, prd_fields=prd_fields, gate_a=gate_a, gate_b=gate_b, tasks=tasks, release_decision=release_decision, release_evidence_cutoff=release_evidence_cutoff, aws_authorization=aws_authorization, external_authority=external_authority, interaction=interaction, active_artifact=active_artifact, deployment_sequence=deployment_sequence_projection)
    # fmt: on
    document_summaries, summary_issues = project_document_summaries(
        summary_sources, summary_specifications
    )
    brief_was_ready = owner_decision_brief.get("status") == "READY"
    for issue in summary_issues:
        reporter = (
            ctx.warning
            if issue["code"] == "DOCUMENT_SUMMARY_STALE" and not brief_was_ready
            else ctx.error
        )
        reporter(
            str(issue["code"]),
            str(issue["message"]),
            str(issue["path"]),
        )
    if summary_issues and brief_was_ready:
        blocked_brief = dict(owner_decision_brief)
        blocked_brief["status"] = "BLOCKED"
        blocked_brief["formal_receipt_required"] = False
        owner_decision_brief, _ = finalize_owner_decision_brief(blocked_brief)
    if any(
        issue["code"] != "DOCUMENT_SUMMARY_STALE" or brief_was_ready
        for issue in summary_issues
    ):
        status = "BLOCKED"
        diagnostic_codes = [item.code for item in ctx.diagnostics]
        remediation = derive_remediation(
            ctx,
            classification=classification,
            gate_a=gate_a,
            gate_b=gate_b,
            envelope=envelope,
            tasks=tasks,
            requirements_revision=prd_fields.get("requirements_revision"),
            design_revision=prd_fields.get("design_revision"),
            owner_stage_hint=resolved_owner_stage,
        )
        interaction = derive_interaction(
            lifecycle_state,
            next_prompt,
            has_errors=True,
            diagnostic_codes=diagnostic_codes,
            design_aws_core_ready=design_aws_core_ready,
            aws_execution_planning_ready=aws_execution_planning_ready,
            remediation=remediation,
            owner_stage_hint=resolved_owner_stage,
            aws_progress_state=aws_progress_state,
            aws_mutation_authority_ready=aws_mutation_authority_ready,
            aws_lane=lane,
            aws_read_authority_required=(
                external_authority.get("kind")
                == "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
            ),
            req_aws_core_materiality=req_aws_core_materiality,
            req_aws_core_ready=req_aws_core_ready,
        )
        if (
            classification == "UNCONFIGURED_TEMPLATE"
            and remediation["next_action"]["action_kind"]
            == "COMPLETE_PREREQUISITE_CHECKLIST"
        ):
            interaction = derive_unconfigured_template_interaction(diagnostic_codes)
        context_plan = derive_context_plan(
            interaction,
            tasks,
            coverage_contract,
            next_prompt=next_prompt,
            restricted_deployment_closure=deployment_authority_restricted,
            restricted_teardown_closure=teardown_authority_restricted,
            source_texts=ctx.texts,
            adr_rationale=adr_rationale_projection,
        )
        context_plan.pop("_resolution_issues", None)

    aws_mode_boundary = derive_aws_mode_boundary(
        lane,
        envelope,
        next_prompt,
        external_authority,
    )
    return {
        "schema_version": 2,
        "bootstrap_version": manifest.get(
            "bootstrap_version", state.get("bootstrap_version")
        ),
        "status": status,
        "classification": classification,
        "ok": not ctx.has_errors,
        "lifecycle_state": lifecycle_state,
        "resume_safe": not ctx.has_errors,
        "next_prompt": next_prompt,
        "interaction": interaction,
        "remediation": remediation,
        "context_plan": context_plan,
        "project": {
            "name": project.get("name"),
            "region": project.get("region"),
            "cost_posture": project.get("cost_posture"),
            "mode": project.get("mode"),
            "delivery_profile": project.get("delivery_profile"),
        },
        "git_baseline": inspect_git_baseline(ctx.root),
        "aws_access": aws_access,
        "aws_mode_boundary": aws_mode_boundary,
        "gates": {
            "gate_a": gate_a,
            "gate_b": gate_b,
        },
        "evidence_state": release_decision,
        "release_evidence_cutoff": release_evidence_cutoff,
        "aws_core_evidence": {
            "aws_execution_planning": (
                "READY" if aws_execution_planning_ready else "BLOCKED"
            ),
            "observed_usage": dict(aws_core_usage or {}),
        },
        "authorizations": {
            "construction": construction_authorization,
            "aws": aws_authorization,
        },
        "write_authority": write_authority,
        "deployment_journal_closure_authority": (deployment_journal_closure_authority),
        "teardown_journal_closure_authority": (teardown_journal_closure_authority),
        "aws_lifecycle_intent": lifecycle_intent_projection,
        "aws_residual_disposition": residual_disposition_projection,
        "aws_lifecycle_intent_write_authority": aws_lifecycle_intent_write_authority,
        "external_authority": external_authority,
        "hook_constraints": {
            "GitHub boundary": envelope.get("GitHub boundary", "NONE"),
            "GitHub repository, branch, and merge constraints": envelope.get(
                "GitHub repository, branch, and merge constraints", "NONE"
            ),
        },
        "aws_action_transition": aws_action_transition,
        "aws_execution": aws_execution_projection,
        "aws_deployment": deployment_sequence_projection,
        "aws_teardown": teardown_sequence_projection,
        "basis": {
            "requirements_revision": prd_fields.get("requirements_revision"),
            "design_revision": prd_fields.get("design_revision"),
            "construction_authorization": prd_fields.get("construction_authorization"),
            "prd_snapshot_sha256": (
                "sha256:"
                + hashlib.sha256(
                    canonical_bytes_without_generated_summary(
                        ctx.presentation_texts[PRD_FILE]
                    )
                ).hexdigest()
                if PRD_FILE in ctx.presentation_texts
                else "NONE"
            ),
        },
        "document_summaries": document_summaries,
        "owner_decision_brief": owner_decision_brief,
        "owner_decision_inventory": owner_decision_inventory,
        "owner_answer_confirmation": owner_answer_confirmation,
        "intake_foundation": intake_contract.to_dict(),
        "requirements_contract": requirements_contract.to_dict(),
        "coverage_plan": coverage_contract.to_dict(),
        "design_contract": design_contract.to_dict(),
        "adr_rationale": adr_rationale_projection,
        "tasks": {
            "total": tasks.total,
            "completed": len(tasks.done),
            "skipped": len(tasks.skipped),
            "blocked": len(tasks.blocked),
            "ready": len(tasks.ready),
            "in_progress": len(tasks.active),
            "ready_ids": tasks.ready,
            "active_ids": tasks.active,
            "blocked_ids": tasks.blocked,
            "requirement_coverage_complete": tasks.requirement_coverage_complete,
            "requirement_coverage": [
                tasks.requirement_coverage[requirement_id]
                for requirement_id in sorted(tasks.requirement_coverage)
            ],
            "missing_requirement_ids": tasks.missing_requirement_ids,
        },
        "diagnostics": [
            item.to_dict(f"DGN-{index:04d}")
            for index, item in enumerate(ctx.diagnostics, start=1)
        ],
    }


def print_human(report: dict[str, Any]) -> None:
    status = "PASS" if report["ok"] else "BLOCKED"
    basis = report["basis"]
    print(f"AWS Codex Fastlane Engine: {status}")
    print(f"Classification: {report['classification']}")
    print(f"Lifecycle: {report['lifecycle_state']}")
    print(
        "Basis: "
        f"{basis.get('requirements_revision') or 'NONE'} / "
        f"{basis.get('design_revision') or 'NONE'} / "
        f"{basis.get('construction_authorization') or 'NONE'}"
    )
    print(f"Resume safe: {'yes' if report['resume_safe'] else 'no'}")
    print(f"Next prompt: {report['next_prompt']}")
    print(f"Git baseline: {report['git_baseline']}")
    print(f"AWS access: {report['aws_access']}")
    print(f"Gate A: {report['gates']['gate_a']}")
    print(f"Gate B: {report['gates']['gate_b']}")
    print(f"Evidence: {report['evidence_state']}")
    print(
        "AWS execution planning: "
        f"{report['aws_core_evidence']['aws_execution_planning']}"
    )
    print(f"AWS authorization: {report['authorizations']['aws']}")
    for item in report["diagnostics"]:
        location = f" ({item['path']})" if item.get("path") else ""
        print(f"{item['severity']} {item['code']}{location}: {item['message']}")


def _parse_current_intake_response(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    report = inspect_project(args.root, template_source=args.template_source)
    if not report["ok"]:
        return {
            "schema_version": 1,
            "status": "FAIL",
            "errors": [
                {
                    "code": "INTAKE_PROJECT_INVALID",
                    "message": "Project must pass the Fastlane Engine before an intake response can be parsed",
                }
            ],
        }, 1
    pending_card = report["intake_foundation"].get("pending_card")
    if not isinstance(pending_card, dict):
        return {
            "schema_version": 1,
            "status": "FAIL",
            "errors": [
                {
                    "code": "INTAKE_CARD_INVALID",
                    "message": "Project has no valid pending intake card",
                }
            ],
        }, 1
    try:
        basis = report.get("basis")
        if not isinstance(basis, Mapping):
            raise ValueError("Current project basis is missing")
        text, _ = bounded_prd_snapshot(
            args.root, clean_cell(basis.get("prd_snapshot_sha256", ""))
        )
        response_table = contract_table_after_heading(
            text, INTAKE_RESPONSE_REGISTER_HEADING, INTAKE_RESPONSE_REGISTER_HEADERS
        )
        if response_table is None:
            raise ValueError("Normalized owner response register is missing")
        register_issues: list[tuple[str, str]] = []
        responses = _parse_intake_response_register(
            response_table, dict(INTAKE_FOUNDATION_FIELDS), register_issues
        )
        if register_issues:
            raise ValueError("Normalized owner response register is invalid")
    except (OSError, UnicodeError, ValueError):
        return {
            "schema_version": 1,
            "status": "FAIL",
            "errors": [
                {
                    "code": "INTAKE_PROJECT_INVALID",
                    "message": "Current intake contract cannot be parsed safely",
                }
            ],
        }, 1
    numbers = [
        int(response.owner_response_id.rsplit("-", 1)[1]) for response in responses
    ]
    result = parse_intake_owner_response(
        sys.stdin.read(MAX_RESPONSE_CHARACTERS + 1),
        pending_card,
        expected_card_id=args.presented_card_id,
        expected_revision=args.presented_card_revision,
        expected_sha256=args.presented_card_sha256,
        owner_response_id=f"OWNER-MSG-{max(numbers, default=0) + 1:04d}",
    )
    return result.to_dict(), 0 if result.status == "PASS" else 2


def _validate_current_gate_receipt(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    """Validate a pending Gate A/B candidate without changing project files."""

    report = inspect_project(args.root, template_source=args.template_source)
    if not report["ok"]:
        return {
            "schema_version": 1,
            "status": "FAIL",
            "candidate_accepted": False,
            "project_state_changed": False,
            "errors": [
                {
                    "code": "GATE_RECEIPT_PROJECT_INVALID",
                    "message": (
                        "Project must pass the Fastlane Engine before a gate "
                        "receipt can be validated"
                    ),
                }
            ],
        }, 1
    try:
        contract = current_gate_receipt_contract(args.root, report)
    except ValueError:
        return {
            "schema_version": 1,
            "status": "FAIL",
            "candidate_accepted": False,
            "project_state_changed": False,
            "lifecycle_state": report.get("lifecycle_state", "BLOCKED"),
            "next_prompt": report.get("next_prompt", "STOP"),
            "errors": [
                {
                    "code": "GATE_RECEIPT_NOT_PENDING",
                    "message": "The project is not waiting for an owner gate receipt",
                }
            ],
        }, 1
    candidate = sys.stdin.read(MAX_GATE_RECEIPT_CHARACTERS + 1)
    result = validate_gate_receipt_candidate(candidate, contract)
    return result, 0 if result["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    configure_utf8_standard_streams()
    parser = argparse.ArgumentParser(description="Read-only AWS Codex Fastlane Engine")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root (defaults to the bootstrap project containing this script)",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    parser.add_argument(
        "--template-source",
        action="store_true",
        help="Allow unresolved render tokens in the reusable template source",
    )
    parser.add_argument(
        "--prior-remediation-fingerprint",
        help="Prior sha256 remediation fingerprint for one bounded retry",
    )
    parser.add_argument("--parse-intake-response", action="store_true")
    parser.add_argument("--parse-gate-correction", action="store_true")
    parser.add_argument("--validate-gate-receipt", action="store_true")
    parser.add_argument("--input-stdin", action="store_true")
    parser.add_argument("--presented-card-id")
    parser.add_argument("--presented-card-revision", type=int)
    parser.add_argument("--presented-card-sha256")
    args = parser.parse_args(argv)
    if (
        args.prior_remediation_fingerprint is not None
        and re.fullmatch(r"sha256:[0-9a-f]{64}", args.prior_remediation_fingerprint)
        is None
    ):
        parser.error(
            "--prior-remediation-fingerprint must be sha256:<64 lowercase hex>"
        )
    owner_input_modes = sum(
        (
            args.parse_intake_response,
            args.parse_gate_correction,
            args.validate_gate_receipt,
        )
    )
    if owner_input_modes > 1:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "FAIL",
                    "errors": [
                        {
                            "code": "OWNER_INPUT_USAGE",
                            "message": "Select exactly one owner-input parser mode",
                        }
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    if args.parse_gate_correction:
        if not args.input_stdin or not args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "FAIL",
                        "errors": [
                            {
                                "code": "GATE_CORRECTION_USAGE",
                                "message": "Gate correction parsing requires stdin and JSON",
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        candidate = sys.stdin.read(MAX_RESPONSE_CHARACTERS + 1)
        result = parse_gate_correction(candidate).to_dict()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 2
    if args.parse_intake_response:
        if (
            not args.input_stdin
            or not args.json
            or args.presented_card_id is None
            or args.presented_card_revision is None
            or args.presented_card_sha256 is None
        ):
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "FAIL",
                        "errors": [
                            {
                                "code": "INTAKE_PARSE_USAGE",
                                "message": "Parsing requires stdin, JSON, and the presented card ID, revision, and digest",
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        result, exit_code = _parse_current_intake_response(args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return exit_code
    if args.validate_gate_receipt:
        if not args.input_stdin or not args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "FAIL",
                        "errors": [
                            {
                                "code": "GATE_RECEIPT_USAGE",
                                "message": (
                                    "Gate receipt validation requires stdin and JSON"
                                ),
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        result, exit_code = _validate_current_gate_receipt(args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return exit_code
    report = inspect_project(
        args.root,
        template_source=args.template_source,
        prior_remediation_fingerprint=args.prior_remediation_fingerprint,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
