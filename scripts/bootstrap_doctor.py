#!/usr/bin/env python3
# ruff: noqa: F401 - stable compatibility facade intentionally re-exports names.
"""Stable read-only CLI for the modular Fastlane Engine.

``bootstrap.yaml`` uses portable, unambiguous JSON-compatible YAML.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

# COMPATIBILITY: importlib file loaders do not add ``scripts`` to sys.path,
# while direct CLI execution does. Preserve both supported loading modes.
if not __package__:
    _scripts_directory = str(Path(__file__).resolve().parent)
    if _scripts_directory not in sys.path:
        sys.path.insert(0, _scripts_directory)

if __package__:
    from .fastlane_engine.core.contracts import (
        ContractTable,
        _parse_contract_table_lines,
        contract_table_after_heading,
        table_after_heading,
    )
    from .fastlane_engine.core.ids import (
        clean_cell,
        explicit_value,
        validate_relative_path,
    )
    from .fastlane_engine.define.intake import (
        _parse_intake_response_register,
    )
    from .fastlane_engine.define.models import (
        CoverageContract,
        IntakeFoundationContract,
        RequirementsContract,
    )
    from .fastlane_engine.define.requirements import (
        authoritative_requirement_ids,
    )
    from .fastlane_engine.design import (
        APPLICATION_SOURCE_NOT_APPLICABLE as APPLICATION_SOURCE_NOT_APPLICABLE,
        ARCHITECTURE_CANDIDATE_HEADING as ARCHITECTURE_CANDIDATE_HEADING,
        ARCHITECTURE_DRIVER_HEADING as ARCHITECTURE_DRIVER_HEADING,
        ARCHITECTURE_SELECTION_HEADING as ARCHITECTURE_SELECTION_HEADING,
        ARCHITECTURE_TRACEABILITY_HEADERS as ARCHITECTURE_TRACEABILITY_HEADERS,
        ARCHITECTURE_TRACEABILITY_HEADING as ARCHITECTURE_TRACEABILITY_HEADING,
        AWS_SERVICE_DECISION_HEADERS as AWS_SERVICE_DECISION_HEADERS,
        AWS_SERVICE_DECISION_HEADING as AWS_SERVICE_DECISION_HEADING,
        AWS_DISCOVERY_ID as AWS_DISCOVERY_ID,
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
        TECHNOLOGY_DECISION_HEADERS as TECHNOLOGY_DECISION_HEADERS,
        TECHNOLOGY_DECISION_HEADING as TECHNOLOGY_DECISION_HEADING,
        DesignContract,
        HarnessRow as HarnessRow,
        derive_diagram_contract as derive_diagram_contract,
        derive_harness_contract as derive_harness_contract,
        parse_application_source_disposition as parse_application_source_disposition,
        parse_property_run_target,
        parsed_numeric_version,
        required_diagram_kinds,
        technology_contract_value_is_unresolved,
        machine_comparable_property_version_policy as machine_comparable_property_version_policy,
        valid_property_execution_command,
        valid_technology_selection as valid_technology_selection,
        valid_technology_version_policy as valid_technology_version_policy,
        validate_application_source_disposition as validate_application_source_disposition,
    )
else:  # Executed directly from scripts/.
    from fastlane_engine.core.contracts import (
        ContractTable as ContractTable,
        _parse_contract_table_lines as _parse_contract_table_lines,
        contract_table_after_heading,
        table_after_heading,
    )
    from fastlane_engine.core.ids import (
        clean_cell,
        explicit_value,
        validate_relative_path,
    )
    from fastlane_engine.define.intake import (
        _parse_intake_response_register,
    )
    from fastlane_engine.define.models import (
        CoverageContract,
        IntakeFoundationContract,
        RequirementsContract,
    )
    from fastlane_engine.define.requirements import (
        authoritative_requirement_ids,
    )
    from fastlane_engine.design import (
        APPLICATION_SOURCE_NOT_APPLICABLE as APPLICATION_SOURCE_NOT_APPLICABLE,
        ARCHITECTURE_CANDIDATE_HEADING as ARCHITECTURE_CANDIDATE_HEADING,
        ARCHITECTURE_DRIVER_HEADING as ARCHITECTURE_DRIVER_HEADING,
        ARCHITECTURE_SELECTION_HEADING as ARCHITECTURE_SELECTION_HEADING,
        ARCHITECTURE_TRACEABILITY_HEADERS as ARCHITECTURE_TRACEABILITY_HEADERS,
        ARCHITECTURE_TRACEABILITY_HEADING as ARCHITECTURE_TRACEABILITY_HEADING,
        AWS_SERVICE_DECISION_HEADERS as AWS_SERVICE_DECISION_HEADERS,
        AWS_SERVICE_DECISION_HEADING as AWS_SERVICE_DECISION_HEADING,
        AWS_DISCOVERY_ID,
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
        LAYER_BOUNDARY_HEADERS as LAYER_BOUNDARY_HEADERS,
        LAYER_BOUNDARY_HEADING as LAYER_BOUNDARY_HEADING,
        MATERIAL_AWS_EVIDENCE_HEADING as MATERIAL_AWS_EVIDENCE_HEADING,
        PROPERTY_EXECUTION_HEADERS as PROPERTY_EXECUTION_HEADERS,
        PROPERTY_EXECUTION_HEADING as PROPERTY_EXECUTION_HEADING,
        PROPERTY_ID as PROPERTY_ID,
        PROPERTY_TEST_EVIDENCE_DESTINATION as PROPERTY_TEST_EVIDENCE_DESTINATION,
        RICH_TO_STATE_TRIGGER as RICH_TO_STATE_TRIGGER,
        SPIKE_HEADING as SPIKE_HEADING,
        STATE_APPLICABILITY_HEADERS as STATE_APPLICABILITY_HEADERS,
        STATE_APPLICABILITY_HEADING as STATE_APPLICABILITY_HEADING,
        STATE_REGISTER_HEADERS as STATE_REGISTER_HEADERS,
        STATE_REGISTER_HEADING as STATE_REGISTER_HEADING,
        TECHNOLOGY_DECISION_HEADERS as TECHNOLOGY_DECISION_HEADERS,
        TECHNOLOGY_DECISION_HEADING as TECHNOLOGY_DECISION_HEADING,
        DesignContract,
        HarnessRow as HarnessRow,
        derive_diagram_contract as derive_diagram_contract,
        derive_harness_contract as derive_harness_contract,
        parse_application_source_disposition as parse_application_source_disposition,
        parse_property_run_target as parse_property_run_target,
        parsed_numeric_version as parsed_numeric_version,
        required_diagram_kinds,
        technology_contract_value_is_unresolved as technology_contract_value_is_unresolved,
        machine_comparable_property_version_policy as machine_comparable_property_version_policy,
        valid_property_execution_command as valid_property_execution_command,
        valid_technology_selection as valid_technology_selection,
        valid_technology_version_policy as valid_technology_version_policy,
        validate_application_source_disposition as validate_application_source_disposition,
    )


if __package__:
    from .fastlane_engine import project_inspection as _project_inspection
    from .fastlane_engine.core import snapshot as _snapshot
    from .fastlane_engine.project_validation import (
        validate_manifest,
        validate_placeholders,
        validate_prd,
        validate_prompt_pack,
        validate_state_schema,
    )
    from .fastlane_engine.project_delivery import (
        validate_aws_lifecycle_intent_record,
        validate_release_decision_record,
        validate_tasks,
    )
else:
    from fastlane_engine import project_inspection as _project_inspection
    from fastlane_engine.core import snapshot as _snapshot
    from fastlane_engine.project_validation import (
        validate_manifest,
        validate_placeholders,
        validate_prd,
        validate_prompt_pack,
        validate_state_schema,
    )
    from fastlane_engine.project_delivery import (
        validate_aws_lifecycle_intent_record,
        validate_release_decision_record,
        validate_tasks,
    )


# COMPATIBILITY: keep historical doctor-level names while ownership moves into
# the modular Engine. New callers use ``fastlane_engine.api``.
_project_inspection.install_compatibility_exports(globals())
_canonical_id_list = _project_inspection._canonical_id_list
_DEFINE_COMPATIBILITY_EXPORTS = _project_inspection._DEFINE_COMPATIBILITY_EXPORTS
STATE_FILE = _project_inspection.STATE_FILE
MANIFEST_FILE = _project_inspection.MANIFEST_FILE
PROJECT_DOCUMENT_DIRECTORY = _project_inspection.PROJECT_DOCUMENT_DIRECTORY
BUGFIX_FILE = _project_inspection.BUGFIX_FILE
PROJECT_README_FILE = _project_inspection.PROJECT_README_FILE
PRD_FILE = _project_inspection.PRD_FILE
RUNBOOK_FILE = _project_inspection.RUNBOOK_FILE
TASKS_FILE = _project_inspection.TASKS_FILE
VERIFY_FILE = _project_inspection.VERIFY_FILE
PROMPT_FILE = _project_inspection.PROMPT_FILE
ENGINE_RUNTIME_CONTROL_FILES = _project_inspection.ENGINE_RUNTIME_CONTROL_FILES
DOCUMENT_SUMMARY_FILES = _project_inspection.DOCUMENT_SUMMARY_FILES
REQ_ID = _project_inspection.REQ_ID
DES_ID = _project_inspection.DES_ID
AUTH_ID = _project_inspection.AUTH_ID
PLAN_ID = _project_inspection.PLAN_ID
TASK_ID = _project_inspection.TASK_ID
RUN_ID = _project_inspection.RUN_ID
CHECKPOINT_ID = _project_inspection.CHECKPOINT_ID
COST_AMOUNT = _project_inspection.COST_AMOUNT
AWS_COST_CEILING = _project_inspection.AWS_COST_CEILING
COST_POSTURE_WITH_CAP = _project_inspection.COST_POSTURE_WITH_CAP
DEFAULT_COST_POSTURE = _project_inspection.DEFAULT_COST_POSTURE
MAX_GATE_RECEIPT_CHARACTERS = _project_inspection.MAX_GATE_RECEIPT_CHARACTERS
ISO_4217_CURRENCY_CODES = _project_inspection.ISO_4217_CURRENCY_CODES
PROJECT_MODES = _project_inspection.PROJECT_MODES
DELIVERY_PROFILES = _project_inspection.DELIVERY_PROFILES
RISK_LEVELS = _project_inspection.RISK_LEVELS
AWS_LANES = _project_inspection.AWS_LANES
WORK_KINDS = _project_inspection.WORK_KINDS
ARCHITECTURE_DISPOSITIONS = _project_inspection.ARCHITECTURE_DISPOSITIONS
COVERAGE_DOMAINS = _project_inspection.COVERAGE_DOMAINS
ALWAYS_REQUIRED_COVERAGE = _project_inspection.ALWAYS_REQUIRED_COVERAGE
COVERAGE_PLAN_HEADING = _project_inspection.COVERAGE_PLAN_HEADING
COVERAGE_PLAN_HEADERS = _project_inspection.COVERAGE_PLAN_HEADERS
CHANGE_IMPACT_HEADING = _project_inspection.CHANGE_IMPACT_HEADING
CHANGE_IMPACT_HEADERS = _project_inspection.CHANGE_IMPACT_HEADERS
CHANGE_ID = _project_inspection.CHANGE_ID
INTAKE_FOUNDATION_HEADING = _project_inspection.INTAKE_FOUNDATION_HEADING
INTAKE_FOUNDATION_HEADERS = _project_inspection.INTAKE_FOUNDATION_HEADERS
LEGACY_INTAKE_FOUNDATION_HEADERS = _project_inspection.LEGACY_INTAKE_FOUNDATION_HEADERS
INTAKE_FOUNDATION_FIELDS = _project_inspection.INTAKE_FOUNDATION_FIELDS
INTAKE_CORE_FIELDS = _project_inspection.INTAKE_CORE_FIELDS
OWNER_WORK_CONTEXTS = _project_inspection.OWNER_WORK_CONTEXTS
OWNER_WORK_CONTEXT_SELECTIONS = _project_inspection.OWNER_WORK_CONTEXT_SELECTIONS
INTAKE_BASES = _project_inspection.INTAKE_BASES
INTAKE_CARD_HEADING = _project_inspection.INTAKE_CARD_HEADING
INTAKE_CARD_HEADERS = _project_inspection.INTAKE_CARD_HEADERS
INTAKE_ID = _project_inspection.INTAKE_ID
INTAKE_CARD_ID = _project_inspection.INTAKE_CARD_ID
INTAKE_QUESTION_ID = _project_inspection.INTAKE_QUESTION_ID
OWNER_RESPONSE_ID = _project_inspection.OWNER_RESPONSE_ID
INTAKE_OWNER_RESPONSE = _project_inspection.INTAKE_OWNER_RESPONSE
INTAKE_RESPONSE_REGISTER_HEADING = _project_inspection.INTAKE_RESPONSE_REGISTER_HEADING
INTAKE_RESPONSE_REGISTER_HEADERS = _project_inspection.INTAKE_RESPONSE_REGISTER_HEADERS
STABLE_CONTRACT_ID = _project_inspection.STABLE_CONTRACT_ID
NORMATIVE_REQUIREMENT_HEADERS = _project_inspection.NORMATIVE_REQUIREMENT_HEADERS
LEGACY_NORMATIVE_REQUIREMENT_HEADERS = (
    _project_inspection.LEGACY_NORMATIVE_REQUIREMENT_HEADERS
)
LEGACY_REQUIREMENT_HEADERS = _project_inspection.LEGACY_REQUIREMENT_HEADERS
PROJECT_CONTRACT_SCHEMA = _project_inspection.PROJECT_CONTRACT_SCHEMA
REQUIREMENTS_CHANGE_LINEAGE_HEADING = (
    _project_inspection.REQUIREMENTS_CHANGE_LINEAGE_HEADING
)
REQUIREMENTS_CHANGE_LINEAGE_HEADERS = (
    _project_inspection.REQUIREMENTS_CHANGE_LINEAGE_HEADERS
)
ASSUMPTION_LIFECYCLE_HEADING = _project_inspection.ASSUMPTION_LIFECYCLE_HEADING
ASSUMPTION_LIFECYCLE_HEADERS = _project_inspection.ASSUMPTION_LIFECYCLE_HEADERS
ASSUMPTION_STATUSES = _project_inspection.ASSUMPTION_STATUSES
REQUIREMENTS_REVISION_ID = _project_inspection.REQUIREMENTS_REVISION_ID
ASSUMPTION_ID = _project_inspection.ASSUMPTION_ID
ACTOR_HEADING = _project_inspection.ACTOR_HEADING
ACTOR_HEADERS = _project_inspection.ACTOR_HEADERS
ACTOR_KINDS = _project_inspection.ACTOR_KINDS
ACTOR_ID = _project_inspection.ACTOR_ID
ACCEPTANCE_ID = _project_inspection.ACCEPTANCE_ID
ACCEPTANCE_TEST_BINDING_ID = _project_inspection.ACCEPTANCE_TEST_BINDING_ID
RICH_USE_CASE_TRIGGERS = _project_inspection.RICH_USE_CASE_TRIGGERS
RICH_USE_CASE_APPLICABILITY_HEADING = (
    _project_inspection.RICH_USE_CASE_APPLICABILITY_HEADING
)
RICH_USE_CASE_APPLICABILITY_HEADERS = (
    _project_inspection.RICH_USE_CASE_APPLICABILITY_HEADERS
)
RICH_USE_CASE_HEADING = _project_inspection.RICH_USE_CASE_HEADING
RICH_USE_CASE_HEADERS = _project_inspection.RICH_USE_CASE_HEADERS
USE_CASE_ID = _project_inspection.USE_CASE_ID
BUSINESS_RULE_HEADING = _project_inspection.BUSINESS_RULE_HEADING
BUSINESS_RULE_HEADERS = _project_inspection.BUSINESS_RULE_HEADERS
BUSINESS_RULE_ID = _project_inspection.BUSINESS_RULE_ID
REQUIREMENT_COVERAGE_HEADING = _project_inspection.REQUIREMENT_COVERAGE_HEADING
REQUIREMENT_COVERAGE_HEADERS = _project_inspection.REQUIREMENT_COVERAGE_HEADERS
INTAKE_FOUNDATION_IDS = _project_inspection.INTAKE_FOUNDATION_IDS
STATE_MODEL_TRIGGERS = _project_inspection.STATE_MODEL_TRIGGERS
EARS_FORMS = _project_inspection.EARS_FORMS
EARS_PATTERNS = _project_inspection.EARS_PATTERNS
CONCRETE_SUBJECT = _project_inspection.CONCRETE_SUBJECT
NON_CONCRETE_SUBJECTS = _project_inspection.NON_CONCRETE_SUBJECTS
ACCEPTANCE_FORMS = _project_inspection.ACCEPTANCE_FORMS
GHERKIN_ACCEPTANCE = _project_inspection.GHERKIN_ACCEPTANCE
MEASURABLE_EXPECTED_RESULT = _project_inspection.MEASURABLE_EXPECTED_RESULT
MEASURABLE_BINDING = _project_inspection.MEASURABLE_BINDING
QAS_HEADERS = _project_inspection.QAS_HEADERS
QAS_ID = _project_inspection.QAS_ID
PROPERTY_TEST_EVIDENCE_HEADING = _project_inspection.PROPERTY_TEST_EVIDENCE_HEADING
PROPERTY_TEST_EVIDENCE_HEADERS = _project_inspection.PROPERTY_TEST_EVIDENCE_HEADERS
PROPERTY_TEST_RESULTS = _project_inspection.PROPERTY_TEST_RESULTS
PROPERTY_TEST_FAILURE_CLASSES = _project_inspection.PROPERTY_TEST_FAILURE_CLASSES
GATE_A_STATES = _project_inspection.GATE_A_STATES
GATE_B_STATES = _project_inspection.GATE_B_STATES
RUN_MODES = _project_inspection.RUN_MODES
RUN_STATES = _project_inspection.RUN_STATES
BROWNFIELD_STATES = _project_inspection.BROWNFIELD_STATES
CANONICAL_PLACEHOLDERS = _project_inspection.CANONICAL_PLACEHOLDERS
MANDATORY_REQUIRED_FILES = _project_inspection.MANDATORY_REQUIRED_FILES
Context = _project_inspection.Context
TASK_METADATA_KEYS = _project_inspection.TASK_METADATA_KEYS
TASK_HEADER_PATTERN = _project_inspection.TASK_HEADER_PATTERN
TASK_META_PATTERN = _project_inspection.TASK_META_PATTERN
TASK_STATUSES = _project_inspection.TASK_STATUSES
TASK_AWS_MODES = _project_inspection.TASK_AWS_MODES
TASK_DESIGN_TRACE_PATTERN = _project_inspection.TASK_DESIGN_TRACE_PATTERN
EVIDENCE_PATTERN = _project_inspection.EVIDENCE_PATTERN
LOCAL_EVIDENCE_ID = _project_inspection.LOCAL_EVIDENCE_ID
LOCAL_EVIDENCE_LIKE = _project_inspection.LOCAL_EVIDENCE_LIKE
TASK_COMPLETION_EVIDENCE_STATUSES = (
    _project_inspection.TASK_COMPLETION_EVIDENCE_STATUSES
)
EVIDENCE_PLACEHOLDER_PATTERN = _project_inspection.EVIDENCE_PLACEHOLDER_PATTERN
UNRESOLVED_TOKEN = _project_inspection.UNRESOLVED_TOKEN
SNAPSHOT_FIELDS = _project_inspection.SNAPSHOT_FIELDS
SNAPSHOT_RUN_STATES = _project_inspection.SNAPSHOT_RUN_STATES
GITHUB_BOUNDARIES = _project_inspection.GITHUB_BOUNDARIES
AWS_BOUNDARIES = _project_inspection.AWS_BOUNDARIES
AWS_DETAIL_FIELDS = _project_inspection.AWS_DETAIL_FIELDS
CONTROL_HASH_FILES = _project_inspection.CONTROL_HASH_FILES
COORDINATOR_LEDGER_PATHS = _project_inspection.COORDINATOR_LEDGER_PATHS
ID_LIKE = _project_inspection.ID_LIKE
GITHUB_ISSUE_URL = _project_inspection.GITHUB_ISSUE_URL
SHELL_CONTROL = _project_inspection.SHELL_CONTROL
NON_HUMAN_APPROVER = _project_inspection.NON_HUMAN_APPROVER
ENVELOPE_EXPLICIT_FIELDS = _project_inspection.ENVELOPE_EXPLICIT_FIELDS
BROWNFIELD_BASELINE_FIELDS = _project_inspection.BROWNFIELD_BASELINE_FIELDS
GATE_A_READINESS_FIELDS = _project_inspection.GATE_A_READINESS_FIELDS
GATE_B_READINESS_FIELDS = _project_inspection.GATE_B_READINESS_FIELDS
AWS_CORE_MATERIALITY_VALUES = _project_inspection.AWS_CORE_MATERIALITY_VALUES
VERIFICATION_MATRIX_HEADING = _project_inspection.VERIFICATION_MATRIX_HEADING
VERIFICATION_MATRIX_HEADERS = _project_inspection.VERIFICATION_MATRIX_HEADERS
require_aws_core_phase_evidence = _project_inspection.require_aws_core_phase_evidence
parse_task_write_set = _project_inspection.parse_task_write_set
parse_task_external_state = _project_inspection.parse_task_external_state
parse_positive_cost = _project_inspection.parse_positive_cost
parse_cost_posture = _project_inspection.parse_cost_posture
validate_aws_cost_ceiling = _project_inspection.validate_aws_cost_ceiling
explicit_human_approver = _project_inspection.explicit_human_approver
_heading_title_span = _project_inspection._heading_title_span
MAX_REQUIRED_FILES = _project_inspection.MAX_REQUIRED_FILES
MAX_REQUIRED_FILE_BYTES = _project_inspection.MAX_REQUIRED_FILE_BYTES
MAX_PROJECT_SOURCE_BYTES = _project_inspection.MAX_PROJECT_SOURCE_BYTES
BINARY_REQUIRED_SUFFIXES = _project_inspection.BINARY_REQUIRED_SUFFIXES
MANIFEST_POLICY = _project_inspection.MANIFEST_POLICY
STATE_POLICY = _project_inspection.STATE_POLICY
safe_read_required_binary = _project_inspection.safe_read_required_binary
safe_read_text = _project_inspection.safe_read_text
bounded_prd_snapshot = _project_inspection.bounded_prd_snapshot
load_json_document = _project_inspection.load_json_document


if __package__:
    from .fastlane_engine.deliver import (
        CheckpointReceiptRow,
        TaskRequirementCoverage,
        TaskSummary,
        declared_task_waivers,
        evidence_timestamp,
        inspect_task_blocks,
        parse_observed_property_run,
        parse_task_completion_evidence,
        replay_evidence_matches_contract,
        require_durable_evidence_source,
        require_explicit_evidence_value as require_explicit_evidence_value,
        task_property_execution_table,
        task_waiver_rows,
        validate_done_evidence,
    )
else:
    from fastlane_engine.deliver import (
        CheckpointReceiptRow as CheckpointReceiptRow,
        TaskRequirementCoverage as TaskRequirementCoverage,
        TaskSummary,
        declared_task_waivers as declared_task_waivers,
        evidence_timestamp as evidence_timestamp,
        inspect_task_blocks,
        parse_observed_property_run as parse_observed_property_run,
        parse_task_completion_evidence as parse_task_completion_evidence,
        replay_evidence_matches_contract as replay_evidence_matches_contract,
        require_durable_evidence_source as require_durable_evidence_source,
        require_explicit_evidence_value,
        task_property_execution_table as task_property_execution_table,
        task_waiver_rows as task_waiver_rows,
        validate_done_evidence as validate_done_evidence,
    )


if __package__:
    from .fastlane_engine.aws import (  # noqa: F401 - compatibility re-exports
        AWS_CORE_EVIDENCE_HEADERS,
        AWS_CORE_EVIDENCE_HEADERS_V1,
        AWS_CORE_EVIDENCE_PHASES,
        AWS_CORE_EVIDENCE_STATUSES,
        AWS_CORE_REQUIRED_CAPABILITIES,
        AWS_DEPLOYMENT_ACTION_STATUSES,
        AWS_DEPLOYMENT_ATTEMPT_ID,
        AWS_DEPLOYMENT_EVIDENCE_HEADERS,
        AWS_DEPLOYMENT_EVIDENCE_HEADING,
        AWS_DEPLOYMENT_PRECALL_RESULT,
        AWS_DEPLOYMENT_READ_PROVENANCE,
        AWS_DEPLOYMENT_RECEIPT_FIELDS,
        AWS_DEPLOYMENT_RECONCILIATION_STATUSES,
        AWS_LIFECYCLE_INTENT_SOURCE,
        AWS_LIFECYCLE_INTENT_VALUES,
        AWS_PLAN_BINDING,
        AWS_PREFLIGHT_ID,
        AWS_READ_AUTHORIZATION_ID,
        AWS_READ_ONLY_OPERATION,
        AWS_READ_PREFLIGHT_HEADERS,
        AWS_READ_PREFLIGHT_HEADING,
        AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
        AWS_TEARDOWN_ACTION_STATUSES,
        AWS_TEARDOWN_ATTEMPT_ID,
        AWS_TEARDOWN_EVIDENCE_HEADERS,
        AWS_TEARDOWN_EVIDENCE_HEADING,
        AWS_TEARDOWN_PRECALL_RESULT,
        AWS_TEARDOWN_READ_PROVENANCE,
        AWS_TEARDOWN_RECEIPT_FIELDS,
        AWS_TEARDOWN_REVIEW_STATUSES,
        AWS_TEARDOWN_TERMINAL_STATUSES,
        AwsAuthorityPolicy,
        AwsCoreEvidenceRow,
        aws_core_evidence_diagnostic_code,
        aws_core_phase_evidence_issues,
        aws_deployment_teardown_sequence_conflict,
        aws_lifecycle_intent_route_is_eligible,
        derive_aws_core_observed_usage,
        derive_aws_delivery_route,
        derive_aws_execution_projection as _derive_aws_execution_projection_core,
        derive_aws_residual_disposition,
        derive_deployment_sequence_state as _derive_deployment_sequence_state_core,
        derive_read_preflight_state as _derive_read_preflight_state_core,
        derive_teardown_route,
        derive_teardown_sequence_state as _derive_teardown_sequence_state_core,
        parse_aws_core_evidence,
        parse_aws_lifecycle_intent_record as _parse_aws_lifecycle_intent_record_core,
        parse_deployment_reconciliation_evidence,
        parse_read_preflight_evidence,
        parse_teardown_reconciliation_evidence,
        release_lifecycle_intent_boundary_is_settled,
        validate_advisory_design_binding,
    )
    from .fastlane_engine.aws.deployment import (  # noqa: F401 - compatibility re-export
        _deployment_values as _deployment_values_core,
        _format_deployment_read_provenance,
    )
else:
    from fastlane_engine.aws import (
        AWS_CORE_EVIDENCE_HEADERS,
        AWS_CORE_EVIDENCE_HEADERS_V1,
        AWS_CORE_EVIDENCE_PHASES,
        AWS_CORE_EVIDENCE_STATUSES,
        AWS_CORE_REQUIRED_CAPABILITIES,
        AWS_DEPLOYMENT_ACTION_STATUSES,
        AWS_DEPLOYMENT_EVIDENCE_HEADERS,
        AWS_DEPLOYMENT_PRECALL_RESULT,
        AWS_DEPLOYMENT_READ_PROVENANCE,
        AWS_DEPLOYMENT_RECONCILIATION_STATUSES,
        AWS_LIFECYCLE_INTENT_SOURCE,
        AWS_LIFECYCLE_INTENT_VALUES,
        AWS_READ_PREFLIGHT_HEADERS,
        AWS_READ_PREFLIGHT_HEADING,
        AWS_TEARDOWN_ACTION_STATUSES,
        AWS_TEARDOWN_ATTEMPT_ID,
        AWS_TEARDOWN_EVIDENCE_HEADERS,
        AWS_TEARDOWN_PRECALL_RESULT,
        AWS_TEARDOWN_READ_PROVENANCE,
        AWS_TEARDOWN_REVIEW_STATUSES,
        AWS_TEARDOWN_TERMINAL_STATUSES,
        AwsAuthorityPolicy,
        AwsCoreEvidenceRow,
        aws_core_evidence_diagnostic_code,
        aws_core_phase_evidence_issues,
        aws_deployment_teardown_sequence_conflict,
        aws_lifecycle_intent_route_is_eligible,
        derive_aws_core_observed_usage,
        derive_aws_delivery_route,
        derive_aws_residual_disposition,
        derive_teardown_route,
        parse_aws_core_evidence,
        parse_deployment_reconciliation_evidence,
        parse_read_preflight_evidence,
        parse_teardown_reconciliation_evidence,
        validate_advisory_design_binding,
    )
    from fastlane_engine.aws.deployment import (
        _deployment_values as _deployment_values_core,
        _format_deployment_read_provenance,
    )


# COMPATIBILITY: keep historical doctor-level imports available while callers
# move to the public Engine API in later extraction PRs.
_AWS_COMPATIBILITY_REEXPORTS = (
    AWS_DISCOVERY_ID,
    require_explicit_evidence_value,
    AWS_CORE_EVIDENCE_HEADERS,
    AWS_CORE_EVIDENCE_HEADERS_V1,
    AWS_CORE_EVIDENCE_PHASES,
    AWS_CORE_EVIDENCE_STATUSES,
    AWS_CORE_REQUIRED_CAPABILITIES,
    AWS_DEPLOYMENT_ACTION_STATUSES,
    AWS_DEPLOYMENT_EVIDENCE_HEADERS,
    AWS_DEPLOYMENT_PRECALL_RESULT,
    AWS_DEPLOYMENT_READ_PROVENANCE,
    AWS_DEPLOYMENT_RECONCILIATION_STATUSES,
    AWS_LIFECYCLE_INTENT_SOURCE,
    AWS_LIFECYCLE_INTENT_VALUES,
    AWS_READ_PREFLIGHT_HEADERS,
    AWS_READ_PREFLIGHT_HEADING,
    AWS_TEARDOWN_ACTION_STATUSES,
    AWS_TEARDOWN_EVIDENCE_HEADERS,
    AWS_TEARDOWN_PRECALL_RESULT,
    AWS_TEARDOWN_READ_PROVENANCE,
    AWS_TEARDOWN_REVIEW_STATUSES,
    parse_deployment_reconciliation_evidence,
    parse_read_preflight_evidence,
    parse_teardown_reconciliation_evidence,
    validate_advisory_design_binding,
    _format_deployment_read_provenance,
)

if __package__:
    from .fastlane_engine.routing import (
        derive_route,
        preserve_expired_authority_for_deployment_closure as _preserve_deployment_closure,
        preserve_expired_authority_for_teardown_closure as _preserve_teardown_closure,
        preserve_specialized_teardown_block as _preserve_teardown_block,
    )
    from .fastlane_engine.owner_decisions import (
        _owner_locator_for_heading,
        derive_owner_answer_confirmation,
        derive_owner_decision_brief,
    )
    from .fastlane_engine.api import current_gate_receipt_contract
    from .fastlane_engine.authority.receipts import validate_gate_receipt_candidate
    from .fastlane_engine.authority.aws import (
        build_aws_authority_policy,
    )
    from .fastlane_engine.api import (
        _read_preflight_receipt_authority,
        _receipt_external_authority,
        derive_aws_lifecycle_intent_write_authority,
        derive_aws_execution_projection,
        derive_deployment_sequence_state,
        derive_external_authority as _derive_external_authority_core,
        derive_read_preflight_state,
        derive_teardown_sequence_state,
        derive_write_authority,
        lifecycle_intent_record_boundary_is_settled,
        prepare_source_brief_request,
        explain_project_validation,
    )
    from .fastlane_engine.authority.github import (
        _aws_action_transition_projection,
        derive_aws_mode_boundary,
        derive_current_prompt_aws_mode,
        derive_request_match,
    )
    from .fastlane_engine.authority.write import (
        derive_deployment_journal_closure_authority,
        derive_teardown_journal_closure_authority,
    )
    from .fastlane_engine.remediation import (
        _agent_correction_is_safe,
        _owner_authorization_action,
        _owner_stage_for_aws_core_phases,
        _owner_stage_from_gates,
        derive_interaction,
        derive_remediation,
        derive_unconfigured_template_interaction,
    )
    from .fastlane_engine.orchestration import (
        _preserve_expired_authority_for_deployment_closure,
        _preserve_expired_authority_for_teardown_closure,
        _preserve_specialized_teardown_block,
        inspect_project,
    )
    from .fastlane_engine.composition import (
        _context_selector_span,
        build_report,
        derive_context_plan,
        derive_document_summary_specifications,
    )
    from .fastlane_engine.core.diagnostics import Diagnostic
    from .fastlane_engine.core.contracts import (
        external_targets_overlap,
        markdown_tables,
        path_boundaries_overlap,
        path_boundary_contains,
    )
    from .fastlane_engine.define import (
        derive_coverage_contract,
        derive_intake_foundation_contract,
        derive_req_aws_materiality,
        derive_requirements_contract,
    )
    from .fastlane_engine.define.requirements import (
        JOURNEY_HEADERS,
        JOURNEY_HEADING,
        quality_attribute_scenario_issues,
        requirement_method_issues,
    )
    from .fastlane_engine.design import (
        APPLICATION_SOURCE_BROWNFIELD,
        APPLICATION_SOURCE_GREENFIELD,
        ApplicationSourceDisposition,
        HarnessContract,
        PropertyExecution,
        canonical_envelope_sha256,
        derive_design_contract as _derive_design_contract_core,
        validate_application_source_write_set,
    )
    from .fastlane_engine.deliver import (
        parse_checkpoint_git_receipt,
        parse_checkpoint_rows,
    )
    from .fastlane_engine.project_delivery import (
        derive_task_requirement_coverage,
        missing_current_property_task_coverage,
        parse_property_test_evidence,
        record_task_graph_validation_errors,
        task_requirement_evidence_dispositions,
        task_requirement_rules,
        technology_version_policy_allows,
        validate_done_property_evidence,
        validate_resume_repository,
        validate_task_property_execution_projection,
        validate_task_records,
    )
    from .fastlane_engine.project_validation import (
        _derive_architecture_contract,
        current_prd_basis_ids,
        derive_design_contract as _derive_design_contract_facade,
        derive_project_design_contract,
        validate_gate_a_method_contract,
    )
    from .fastlane_engine.owner_decisions import TECHNICAL_DOMAIN_ORDER
    from .fastlane_engine.doctor_compat import (
        install_legacy_doctor_exports,
        patchable_design_contract_facade,
        patchable_git_observers,
    )
else:
    from fastlane_engine.routing import (
        derive_route,
        preserve_expired_authority_for_deployment_closure as _preserve_deployment_closure,
        preserve_expired_authority_for_teardown_closure as _preserve_teardown_closure,
        preserve_specialized_teardown_block as _preserve_teardown_block,
    )
    from fastlane_engine.owner_decisions import (
        _owner_locator_for_heading,
        derive_owner_answer_confirmation,
        derive_owner_decision_brief,
    )
    from fastlane_engine.api import current_gate_receipt_contract
    from fastlane_engine.authority.receipts import validate_gate_receipt_candidate
    from fastlane_engine.authority.aws import (
        build_aws_authority_policy,
    )
    from fastlane_engine.api import (
        _read_preflight_receipt_authority,
        _receipt_external_authority,
        derive_aws_lifecycle_intent_write_authority,
        derive_aws_execution_projection,
        derive_deployment_sequence_state,
        derive_external_authority as _derive_external_authority_core,
        derive_read_preflight_state,
        derive_teardown_sequence_state,
        derive_write_authority,
        lifecycle_intent_record_boundary_is_settled,
        prepare_source_brief_request,
        explain_project_validation,
    )
    from fastlane_engine.authority.github import (
        _aws_action_transition_projection,
        derive_aws_mode_boundary,
        derive_current_prompt_aws_mode,
        derive_request_match,
    )
    from fastlane_engine.authority.write import (
        derive_deployment_journal_closure_authority,
        derive_teardown_journal_closure_authority,
    )
    from fastlane_engine.remediation import (
        _agent_correction_is_safe,
        _owner_authorization_action,
        _owner_stage_for_aws_core_phases,
        _owner_stage_from_gates,
        derive_interaction,
        derive_remediation,
        derive_unconfigured_template_interaction,
    )
    from fastlane_engine.orchestration import (
        _preserve_expired_authority_for_deployment_closure,
        _preserve_expired_authority_for_teardown_closure,
        _preserve_specialized_teardown_block,
        inspect_project,
    )
    from fastlane_engine.composition import (
        _context_selector_span,
        build_report,
        derive_context_plan,
        derive_document_summary_specifications,
    )
    from fastlane_engine.core.diagnostics import Diagnostic
    from fastlane_engine.core.contracts import (
        external_targets_overlap,
        markdown_tables,
        path_boundaries_overlap,
        path_boundary_contains,
    )
    from fastlane_engine.define import (
        derive_coverage_contract,
        derive_intake_foundation_contract,
        derive_req_aws_materiality,
        derive_requirements_contract,
    )
    from fastlane_engine.define.requirements import (
        JOURNEY_HEADERS,
        JOURNEY_HEADING,
        quality_attribute_scenario_issues,
        requirement_method_issues,
    )
    from fastlane_engine.design import (
        APPLICATION_SOURCE_BROWNFIELD,
        APPLICATION_SOURCE_GREENFIELD,
        ApplicationSourceDisposition,
        HarnessContract,
        PropertyExecution,
        canonical_envelope_sha256,
        derive_design_contract as _derive_design_contract_core,
        validate_application_source_write_set,
    )
    from fastlane_engine.deliver import (
        parse_checkpoint_git_receipt,
        parse_checkpoint_rows,
    )
    from fastlane_engine.project_delivery import (
        derive_task_requirement_coverage,
        missing_current_property_task_coverage,
        parse_property_test_evidence,
        record_task_graph_validation_errors,
        task_requirement_evidence_dispositions,
        task_requirement_rules,
        technology_version_policy_allows,
        validate_done_property_evidence,
        validate_resume_repository,
        validate_task_property_execution_projection,
        validate_task_records,
    )
    from fastlane_engine.project_validation import (
        _derive_architecture_contract,
        current_prd_basis_ids,
        derive_design_contract as _derive_design_contract_facade,
        derive_project_design_contract,
        validate_gate_a_method_contract,
    )
    from fastlane_engine.owner_decisions import TECHNICAL_DOMAIN_ORDER
    from fastlane_engine.doctor_compat import (
        install_legacy_doctor_exports,
        patchable_design_contract_facade,
        patchable_git_observers,
    )


_OWNER_COMPATIBILITY_REEXPORTS = (_owner_locator_for_heading,)
_REMEDIATION_COMPATIBILITY_REEXPORTS = (
    _agent_correction_is_safe,
    _owner_authorization_action,
    _owner_stage_for_aws_core_phases,
    _owner_stage_from_gates,
)
_AUTHORITY_COMPATIBILITY_REEXPORTS = (derive_current_prompt_aws_mode,)


def _aws_authority_policy() -> AwsAuthorityPolicy:
    """COMPATIBILITY: expose the modular exact-authority policy."""

    return build_aws_authority_policy()


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
        parse_checkpoint_cells,
        parse_checkpoint_git_receipt_value,
        parse_task_completion_evidence_cells,
        split_markdown_table_row,
        without_fenced_code,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_contracts import (
        ContractParseError as ContractParseError,
        parse_checkpoint_cells as parse_checkpoint_cells,
        parse_checkpoint_git_receipt_value as parse_checkpoint_git_receipt_value,
        parse_task_completion_evidence_cells as parse_task_completion_evidence_cells,
        split_markdown_table_row,
        without_fenced_code,
    )

try:
    from fastlane_owner_briefs import finalize_owner_decision_brief
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_owner_briefs import finalize_owner_decision_brief
try:
    from fastlane_document_summaries import (
        build_summary_specifications,
        canonical_bytes_without_generated_summary,
        project_document_summaries,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_document_summaries import (
        build_summary_specifications,
        canonical_bytes_without_generated_summary,
        project_document_summaries,
    )


try:
    from fastlane_process import resolve_trusted_git
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_process import resolve_trusted_git

try:
    from fastlane_stdio import configure_utf8_standard_streams
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_stdio import configure_utf8_standard_streams

try:
    from intake_response import (
        MAX_RESPONSE_CHARACTERS,
        parse_intake_owner_response,
        parse_gate_correction,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.intake_response import (
        MAX_RESPONSE_CHARACTERS,
        parse_intake_owner_response,
        parse_gate_correction,
    )


install_legacy_doctor_exports(globals())
git_read, inspect_git_baseline = patchable_git_observers(globals())
derive_design_contract = patchable_design_contract_facade(
    globals(), _derive_design_contract_facade
)


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


def _owner_input_usage(code: str, message: str) -> int:
    print(
        json.dumps(
            {
                "schema_version": 1,
                "status": "FAIL",
                "errors": [{"code": code, "message": message}],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1


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
    parser.add_argument("--source-brief", help="Preview one owner product brief")
    parser.add_argument(
        "--explain-validation",
        action="store_true",
        help="Project source-bound validation obligations without executing them",
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
        return _owner_input_usage(
            "OWNER_INPUT_USAGE", "Select exactly one owner-input parser mode"
        )
    if args.explain_validation:
        if (
            not args.json
            or owner_input_modes
            or args.source_brief is not None
            or args.input_stdin
        ):
            parser.error(
                "--explain-validation requires --json and cannot combine with source or owner-input modes"
            )
        payload = explain_project_validation(
            args.root, template_source=args.template_source
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["report"]["ok"] else 1
    if args.source_brief is not None:
        payload, exit_code = prepare_source_brief_request(
            args.root, args.source_brief, args.json, owner_input_modes
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return exit_code
    if args.parse_gate_correction:
        if not args.input_stdin or not args.json:
            return _owner_input_usage(
                "GATE_CORRECTION_USAGE",
                "Gate correction parsing requires stdin and JSON",
            )
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
            return _owner_input_usage(
                "INTAKE_PARSE_USAGE",
                "Parsing requires stdin, JSON, and the presented card ID, revision, and digest",
            )
        result, exit_code = _parse_current_intake_response(args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return exit_code
    if args.validate_gate_receipt:
        if not args.input_stdin or not args.json:
            return _owner_input_usage(
                "GATE_RECEIPT_USAGE", "Gate receipt validation requires stdin and JSON"
            )
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
