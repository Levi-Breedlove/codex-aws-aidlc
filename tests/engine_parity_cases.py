"""Frozen Fastlane Engine parity fixtures and ephemeral measurement helpers."""

from __future__ import annotations

import argparse
import ast
import copy
import contextlib
import hashlib
import io
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable, Mapping
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import bootstrap_doctor as doctor
from tests import test_bootstrap_doctor as doctor_fixtures


ORACLE_PATH = REPOSITORY_ROOT / "tests/fixtures/engine_parity_v1.json"
QUALIFICATION_ORACLE_PATH = (
    REPOSITORY_ROOT / "tests/fixtures/engine_qualification_v1.json"
)
BASELINE_COMMIT = "312b53ce00f9db5263f3a72e778f833e70c7db8e"
BASELINE_PACKAGE_VERSION = "1" + ".2.10"
SUMMARY_TRUTH_BASE_COMMIT = "8dbb11fd0e54af392ac073ce597cdb26fc336fcc"
ADAPTIVE_KICKOFF_BASE_COMMIT = "204b1b7477413425114deaa54a9ece8f9fc14e53"
AWS_DESIGN_COVERAGE_BASE_COMMIT = "e31d60bec32dd52b3ec29f36abfad2096e9ef867"
HUMAN_DIAGRAM_SUPPORT_DIGEST_BASE_COMMIT = "66bcf1de7e5e06feb3dcf84fae2081d515c881a4"
OWNER_SOURCE_NAVIGATION_BASE_COMMIT = "47e1e548e0ae429d47ff838b3ebd60e98a1a5e1e"
SEPARATE_AWS_AUTHORITY_BASE_COMMIT = "94594e7fabfa0a4dc7a1020cf51792a9ca10f07e"
MERMAID_PRESENTATION_BASE_COMMIT = "2af6a7911e8b72bafb87102bbc8ae70e6b82c9bb"
GOLDEN_PRD_TRUTH_BASE_COMMIT = "f24bf4674a792a305acfae5cd9e9ad0077a9bf79"
EXPLICIT_REGION_SELECTION_BASE_COMMIT = "c14f4a9eb7c57332d4332033c034ef1e9b33355a"
QUALIFICATION_BASE_COMMIT = "f26a085170de2f99ad11450b5bf3c2ebaaf30501"
QUALIFICATION_BASE_PACKAGE_VERSION = "1" + ".2.24"
DEFINITION_OF_COMPLETE_BASE_COMMIT = "8909518c474aefbc34d501ba3ff7452713b32656"
PACKAGE_VERSION_SENTINEL = "<PACKAGE_VERSION>"
GIT_SHA_SENTINEL = "<GIT_SHA>"
GIT_SHA = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")
FROZEN_ORACLE_SHA256 = (
    "fe045b9afd14e171fc595dea5c82f3b4fac0a0e4d3956dc99e02d8eb09e87746"
)

FROZEN_APPROVED_BEHAVIOR_CHANGES = [
    {
        "id": "DOCUMENT_SUMMARY_TRUTH_1_2_19",
        "base_commit": SUMMARY_TRUTH_BASE_COMMIT,
        "scope": [
            "document summary owner action and next action",
            "document summary canonical field selection",
            "document summary evidence maturity",
        ],
        "prohibited": [
            "lifecycle or routing change",
            "gate or authority change",
            "canonical digest change",
            "receipt change",
        ],
    },
    {
        "id": "ADAPTIVE_KICKOFF_1_2_28",
        "base_commit": ADAPTIVE_KICKOFF_BASE_COMMIT,
        "scope": [
            "derived next-question consultation guidance",
            "Codex-owned project configuration guidance",
            "automatic requirements continuation after complete owner intake",
            "context locator bytes for updated coordinator procedure",
        ],
        "prohibited": [
            "gate or authority change",
            "canonical requirement or design digest change",
            "receipt change",
            "owner approval inferred from project configuration",
        ],
    },
    {
        "id": "AWS_DESIGN_COVERAGE_1_2_33",
        "base_commit": AWS_DESIGN_COVERAGE_BASE_COMMIT,
        "scope": [
            "canonical PRD AWS implementation concern vocabulary",
            "owner-readable Gate A to Design to Gate B timing",
            "PRD snapshot and source-locator metadata for the updated section",
        ],
        "prohibited": [
            "lifecycle, routing, or remediation change",
            "requirement, design, diagram, gate, or authority semantic change",
            "receipt change",
            "AWS access or execution claim",
        ],
    },
    {
        "id": "HUMAN_DIAGRAM_SUPPORT_DIGESTS_1_2_35",
        "base_commit": HUMAN_DIAGRAM_SUPPORT_DIGEST_BASE_COMMIT,
        "scope": [
            "owner-readable planned architecture and AWS implementation diagrams",
            "normalized selected-technology and AWS-evidence bindings required to keep the Golden technical plan and its diagrams mutually consistent",
            "diagram direction, edge-kind, purpose, normalized-containment, semantic-digest, and presentation-source fingerprint binding",
            "Design digest binding for error-handling, AWS implementation, and IaC validation support tables",
            "PRD snapshot and context-locator bytes changed only by those human Design records",
        ],
        "prohibited": [
            "requirement, lifecycle, routing, remediation, task, gate, authority, or receipt change",
            "construction or AWS authorization change",
            "AWS access, execution, deployment, recovery, or teardown evidence claim",
        ],
    },
    {
        "id": "OWNER_SOURCE_NAVIGATION_1_2_36",
        "base_commit": OWNER_SOURCE_NAVIGATION_BASE_COMMIT,
        "scope": [
            "owner-facing Technical decision index and diagram-guide links to existing canonical PRD sections",
            "PRD snapshot and source-locator bytes changed only by those navigation labels",
            "Fastlane patch-version mirrors and consequential manifest hashes",
        ],
        "prohibited": [
            "requirement, design, diagram, lifecycle, routing, remediation, task, gate, authority, or receipt change",
            "construction or AWS authorization change",
            "AWS access, execution, deployment, recovery, or teardown evidence claim",
        ],
    },
    {
        "id": "SEPARATE_AWS_MUTATION_AUTHORITY_1_2_37",
        "base_commit": SEPARATE_AWS_AUTHORITY_BASE_COMMIT,
        "scope": [
            "fast-dev AWS-20 routing waits for a separate exact deployment receipt",
            "receipt-backed AWS_DEPLOYMENT authority for both mutation lanes",
            "legacy fast-dev deployment-journal reconciliation without renewed mutation authority",
            "consequential owner interaction, hook, prompt, and package-version projections",
        ],
        "prohibited": [
            "Gate A or Gate B schema, receipt, approval, or migration change",
            "requirement, design, diagram, task, or local construction authority change",
            "AWS access, execution, deployment, recovery, or teardown evidence claim",
            "release, GitHub, or teardown authority broadening",
        ],
    },
    {
        "id": "MERMAID_PRESENTATION_1_2_39",
        "base_commit": MERMAID_PRESENTATION_BASE_COMMIT,
        "scope": [
            "compact state-diagram presentation and exact rendered-review fixture coverage",
            "bounded node and relationship line-break presentation validation",
            "relationship line breaks excluded from modern diagram semantic digests",
            "dark and default render guidance with the existing restrained semantic palette",
            "context-locator bytes changed only by the updated Design procedure",
        ],
        "prohibited": [
            "requirement, design, containment, relationship, lifecycle, routing, task, gate, authority, or receipt semantic change",
            "construction or AWS authorization change",
            "AWS access, execution, deployment, recovery, or teardown evidence claim",
        ],
    },
    {
        "id": "GOLDEN_PRD_TRUTH_1_2_42",
        "base_commit": GOLDEN_PRD_TRUTH_BASE_COMMIT,
        "scope": [
            "fail-closed owner-visible Product Agreement and Design completeness",
            "exact Findings and Open decisions reconciliation with Gate A summaries",
            "selected-Region and bounded-label diagram presentation validation",
            "native-text default and dark Golden render evidence",
        ],
        "prohibited": [
            "canonical requirement, design, diagram semantic, envelope, gate, authority, or receipt change",
            "lifecycle or route change for already-complete current project records",
            "AWS access, execution, deployment, recovery, or teardown evidence claim",
        ],
    },
    {
        "id": "EXPLICIT_REGION_SELECTION_1_2_43",
        "base_commit": EXPLICIT_REGION_SELECTION_BASE_COMMIT,
        "scope": [
            "fresh initialization requires one explicit canonical owner Region",
            "recommendation requests remain unselected until a new owner confirmation",
            "context-locator bytes changed only by the updated Define procedure",
            "Fastlane patch-version mirrors and Golden fixture version identity",
        ],
        "prohibited": [
            "migration or rewrite of an initialized project's recorded Region",
            "requirement, design, diagram, lifecycle, route, gate, authority, or receipt change",
            "AWS access, execution, deployment, recovery, or teardown evidence claim",
        ],
    },
    {
        "id": "OWNER_DECISION_EVIDENCE_AND_REMEDIATION_1_2_46",
        "base_commit": "11f34120660b910d12c529cb0ed0b01c2b530ed9",
        "scope": [
            "current prompt-slice bytes for the clarified owner-facing procedures",
            "concrete Gate A and Gate B owner decision projections and exact current source locators",
            "risk-derived Harness selection with exact command and evidence destination",
            "additive agent-correction cause, bounded write set, task validation evidence, and Engine rerun detail",
        ],
        "prohibited": [
            "lifecycle or route change",
            "gate, authority, or receipt change",
            "requirement, design, diagram, or construction-envelope semantic change",
            "AWS access, execution, deployment, recovery, or teardown evidence claim",
        ],
    },
]
DEFINITION_OF_COMPLETE_CHANGE = {
    "id": "DEFINITION_OF_COMPLETE_CONTRACTS_1_3_0",
    "base_commit": DEFINITION_OF_COMPLETE_BASE_COMMIT,
    "scope": [
        "Requirements 1.5 completion target, outcome, dataset, external-obligation, and cross-cutting-risk projections with approved Requirements 1.4 compatibility",
        "Design 8 data, environment, Well-Architected consideration, dependency-policy, and semantic relationship projections with approved Design 7 compatibility",
        "typed release claims, target-specific qualified completion wording, owner decision additions, and Engine-derived current AWS authority",
        "card-scoped Accept this recommendation. handling with the hidden exact legacy Accept all recommendations. compatibility alias",
        "architecture-board direction, relationship category, edge kind, containment, and semantic-path parity",
        "consequential PRD snapshot, current context selection, owner locator, and canonical digest changes",
    ],
    "prohibited": [
        "lifecycle or route change for an equivalent legacy project",
        "legacy Gate A, Gate B, AWS receipt, approval, or authority change",
        "AWS access, execution, deployment, recovery, or teardown evidence claim",
        "frozen pre-refactor oracle mutation",
    ],
}
LOCAL_ALPHA_SPECIFICATION_CHANGE = {
    "id": "REQUIREMENTS_1_6_DESIGN_9_LOCAL_ALPHA_1_4_0",
    "base_commit": "831a3ae5bfcc0597f7ca763d8de0f211ee053fe2",
    "scope": [
        "Requirements 1.6 exact recovery, scenario-classification, input-applicability and input-boundary bindings",
        "Design 9 exact acceptance criteria and one-obligation validation checks with command, stage, time bound and evidence destination",
        "Current task acceptance and local-build check projections",
        "Consequential current source ranges, source bytes, canonical digests and owner recovery wording",
        "Explicit required-task-record overflow under the unchanged context budget",
    ],
    "prohibited": [
        "Frozen pre-refactor oracle or historical canonical digest changes",
        "Changes to independently specified lifecycle, route, gate, authority, task-state or diagnostic meanings",
        "Truncating required records or increasing context limits to conceal growth",
        "Application, AWS, recovery or arbitrary narrative correctness claims inferred from structured fixture validation",
    ],
}
QUALIFICATION_APPROVED_BEHAVIOR_CHANGES = [
    *FROZEN_APPROVED_BEHAVIOR_CHANGES,
    DEFINITION_OF_COMPLETE_CHANGE,
    LOCAL_ALPHA_SPECIFICATION_CHANGE,
]
SUMMARY_TRUTH_COMPATIBILITY_DIGESTS = {
    "template_source": (
        "93342ac776238cc2fb71393e51fb25e195bc70ef1c1561f2ec71988441a5dd7a"
    ),
    "unconfigured_template": (
        "547740ec1c6690da6ded36c63dd19e9f0ba5c0de3367dae6b4f96a8d6dde01eb"
    ),
    "rendered_intake": (
        "e6afd8ab6be91dd838f3cfa33e36a779753b38849c05f00a8b32c1d350309e91"
    ),
    "gate_a_pending": (
        "e6fde4991c3de475f3a4821aeab79f5ef4a7c87377ef0f08fe3979890717819b"
    ),
    "gate_a_approved": (
        "6b276a571c34daad92f95856eb61dca880123c077f360ba9f125b3eca796b939"
    ),
    "gate_b_pending": (
        "f43aa524fa97ebb0a38f0c8c8dfea419c87398ce08c6b3b4a40b3074457dffd9"
    ),
    "gate_b_approved": (
        "09899b548a21b9895404a6efd3a40158ffd5073fb10990f8802487ebeb31f7eb"
    ),
}
CURRENT_COMPATIBILITY_DIGESTS = {
    "template_source": (
        "4454ad024028fd38233fa7f210618137361bb8711a121277b55fc0c784731329"
    ),
    "unconfigured_template": (
        "7f2724699186f3d97fed77d02a701cd01983b13bf34d434f3832c9f3d7376b47"
    ),
    "rendered_intake": (
        "837e63b41a9023031d15ef3aa2cfb2fe71ec28bc5d47cc74a53f64bbd1ab54b9"
    ),
    "gate_a_pending": (
        "62fec6727ce1ccba560db03c08a2697a29dadf130e99433b2c190ae769accd17"
    ),
    "gate_a_approved": (
        "eceda55343f93c30149889cc73e5c0a37da9e8ed7197108b16ebc65f1c35e2b2"
    ),
    "gate_b_pending": (
        "895e9dfa49f9583bcaacb4cbc59beffe19a2f885a506ac4cf9673fc9cc3f8eb1"
    ),
    "gate_b_approved": (
        "5a1a44fcf0100651b2fb6c1977704f4f0ff900919eac91d40a30b1836b004076"
    ),
}
CURRENT_APPROVED_BEHAVIOR_ADDITION_DIGESTS = {
    "template_source": "9870c8c3d83d1d5d79be733fa2baa39c5d3a7718b66504aeb46e556b30fe1edb",
    "unconfigured_template": "680b873da939d4ba6af8cc219e3750b0746549dbb41b5bdd62ae52144a6eed5b",
    "rendered_intake": "3b4ca31afaf86349ea5708de1aadd5ddad53be8f8d4cfd7b9c396ef6302aeb1f",
    "gate_a_pending": "73ec17d4d6b4e8688cf9f43f71893e846819347686e0076a4bbb319891595bd4",
    "gate_a_approved": "dd0b3dd451f59233b26062b9f67c3fea736e0c9951a680c436ddfc5094000870",
    "gate_b_pending": "a4da066331f4870fba719b381eacb68e6ab36d89dc2414542f4df41440cd2a44",
    "gate_b_approved": "2ff1183d18cf510e7d3b713acef07650fa4931c7b4f71fb7e444985244aa5b8a",
}


# Each required refactor scenario remains tied to a named existing regression.
# Full report snapshots below add exact cross-domain parity at representative gates.
SCENARIO_COVERAGE: dict[str, tuple[str, ...]] = {
    "fresh_template": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_ordinary_doctor_routes_untouched_template_to_prerequisites",
    ),
    "prerequisite_failure_and_initialization": (
        "tests.test_product_journeys.ProductJourneyTests."
        "test_extracted_template_setup_initializes_once_and_resumes",
    ),
    "intake_pending_and_partial": (
        "tests.test_product_journeys.ProductJourneyTests."
        "test_partial_high_risk_intake_remains_a_plain_owner_consultation",
    ),
    "intake_stale_or_unproven": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_unproven_selection_is_agent_correctable_without_owner_confirmation",
    ),
    "intake_ambiguous": (
        "tests.test_intake_response.IntakeResponseRejectionTests."
        "test_unknown_duplicate_and_conflicting_reply_keys_are_rejected",
    ),
    "intake_secret_like": (
        "tests.test_intake_response.IntakeResponseRejectionTests."
        "test_record_unsafe_details_are_rejected_without_echo",
    ),
    "gate_a_blocked": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_gate_a_rejects_unresolved_normative_requirement",
    ),
    "gate_a_ready_and_receipt": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_gate_receipt_cli_validates_same_gate_and_never_writes",
    ),
    "gate_a_approved": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_exact_approved_receipts_route_uninitialized_plan_to_tasks",
    ),
    "gate_a_stale": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_stale_gates_route_to_repair_prompts",
    ),
    "gate_b_blocked": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_undeclared_architecture_traceability_blocks_gate_b",
    ),
    "gate_b_ready_and_receipt": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_gate_receipt_cli_validates_same_gate_and_never_writes",
    ),
    "gate_b_approved": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_exact_approved_receipts_route_uninitialized_plan_to_tasks",
    ),
    "gate_b_stale": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_gate_b_design_hash_staleness_blocks_query_start_claim_and_status",
    ),
    "adr_absent": (
        "tests.test_adr_rationale.AdrRationaleTests."
        "test_no_reference_keeps_projects_unchanged",
    ),
    "adr_current": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_current_adr_is_additive_and_digest_neutral",
    ),
    "adr_stale": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_stale_adr_is_safe_codex_correction_without_owner_turn",
    ),
    "adr_malformed_or_unsafe": (
        "tests.test_adr_rationale.AdrRationaleTests."
        "test_missing_and_unsafe_links_fail_closed",
    ),
    "adr_duplicate_or_conflicting": (
        "tests.test_adr_rationale.AdrRationaleTests.test_duplicate_id_fails_closed",
    ),
    "task_plan_and_claim": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_ready_selects_only_explicit_ready_tasks",
    ),
    "task_coverage_failure": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_task_requirement_coverage_rejects_invalid_acceptance_traces",
    ),
    "task_completion": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_single_task_mode_survives_pause_resume_and_complete",
    ),
    "task_failed_local_evidence": (
        "tests.test_product_journeys.ProductJourneyTests."
        "test_failed_task_evidence_cannot_produce_false_done",
    ),
    "release_ready_and_blocked": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_plan_state_and_release_state_have_explicit_routes",
    ),
    "aws_guidance_and_read_authority": (
        "tests.test_product_journeys.ProductJourneyTests."
        "test_aws_guidance_read_scope_preflight_and_mutation_wait_are_serial",
    ),
    "aws_preflight": (
        "tests.test_doctor_interaction.DoctorInteractionTests."
        "test_aws_preflight_collects_evidence_before_requesting_authority",
    ),
    "deployment_started_and_terminal": (
        "tests.test_bootstrap_doctor.AwsDeploymentReconciliationRegressionTests."
        "test_started_and_every_terminal_action_require_aws30",
    ),
    "deployment_partial_or_stale": (
        "tests.test_bootstrap_doctor.AwsDeploymentReconciliationRegressionTests."
        "test_aws30_complete_blocked_and_stale_have_distinct_states",
    ),
    "deployment_reconciliation": (
        "tests.test_bootstrap_doctor.AwsDeploymentReconciliationRegressionTests."
        "test_deployment_sequence_routes_through_release_cutoff_and_residual_review",
    ),
    "residual_review": (
        "tests.test_product_journeys.ProductJourneyTests."
        "test_residual_disposition_is_fresh_set_level_and_non_authorizing",
    ),
    "teardown_readiness_and_terminal": (
        "tests.test_bootstrap_doctor.AwsExecutionContractRegressionTests."
        "test_teardown_sequence_routes_by_current_phase_evidence",
    ),
    "greenfield": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_greenfield_gate_b_binds_application_source_to_singular_app",
    ),
    "brownfield": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_brownfield_baseline_is_deferred_until_gate_a_readiness",
    ),
    "high_risk": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_high_risk_requires_high_risk_profile",
    ),
    "select_amend_preserve": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_adaptive_coverage_select_amend_preserve_and_fail_closed",
    ),
    "grandfathered_schemas": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_approved_schema_five_design_is_grandfathered_without_diagrams",
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_genuine_1234_design_keeps_exact_schema_seven_and_six_digests",
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_genuine_schema_six_approved_design_keeps_its_historical_digest",
    ),
    "malformed_or_duplicate_rows": (
        "tests.test_fastlane_contracts.SharedEvidenceAndCheckpointTests."
        "test_malformed_or_discontiguous_checkpoints_fail",
    ),
    "tampered_digests": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_gate_b_hash_binds_every_envelope_row",
    ),
    "unsafe_paths": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_unsafe_write_boundaries_are_rejected",
    ),
    "unsafe_authority": (
        "tests.test_fastlane_hooks.FastlaneHookTests."
        "test_unauthorized_aws_and_github_mutations_are_denied",
    ),
    "interrupted_action": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_interrupted_state_first_write_blocks_next_mutation",
    ),
    "resume": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_resume_fails_closed_when_git_is_unavailable_or_dirty_set_drifts",
    ),
}

# COMPATIBILITY: the frozen pre-refactor oracle records the original selectors.
# The regression methods moved without semantic changes during 1.2.25
# qualification, so discovery resolves only these exact class prefixes.
SCENARIO_SELECTOR_RELOCATIONS = {
    ("tests.test_bootstrap_doctor.AwsDeploymentReconciliationRegressionTests."): (
        "tests.test_engine_aws_deployment.AwsDeploymentReconciliationRegressionTests."
    ),
    ("tests.test_bootstrap_doctor.AwsExecutionContractRegressionTests."): (
        "tests.test_engine_aws_execution.AwsExecutionContractRegressionTests."
    ),
}


def current_scenario_selector(selector: str) -> str:
    """Return the current location for one frozen regression selector."""

    for previous, current in SCENARIO_SELECTOR_RELOCATIONS.items():
        if selector.startswith(previous):
            return current + selector[len(previous) :]
    return selector


REPORT_CASES = (
    "template_source",
    "unconfigured_template",
    "rendered_intake",
    "gate_a_pending",
    "gate_a_approved",
    "gate_b_pending",
    "gate_b_approved",
)

QUALIFICATION_REPORT_CASES = (
    "stale_gate_a_summary",
    "task_ready",
)

QUALIFICATION_AWS_SCENARIO_COVERAGE: dict[str, tuple[str, ...]] = {
    "fast_dev_separate_deployment_receipt": (
        "tests.test_engine_aws_execution."
        "AwsExecutionContractRegressionTests."
        "test_fast_dev_mutation_requires_observed_preflight_and_exact_receipt",
    ),
    "deployment_action_terminals": (
        "tests.test_engine_aws_deployment."
        "AwsDeploymentReconciliationRegressionTests."
        "test_started_and_every_terminal_action_require_aws30",
    ),
    "deployment_reconciliation_terminals": (
        "tests.test_engine_aws_deployment."
        "AwsDeploymentReconciliationRegressionTests."
        "test_aws30_complete_blocked_and_stale_have_distinct_states",
    ),
    "teardown_action_and_review_terminals": (
        "tests.test_engine_aws_execution."
        "AwsExecutionContractRegressionTests."
        "test_teardown_sequence_routes_by_current_phase_evidence",
    ),
}

QUALIFICATION_DESIGN_SCENARIO_COVERAGE: dict[str, tuple[str, ...]] = {
    "diagram_directed_edges_and_edge_kinds": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_golden_diagram_edges_are_independently_authored_and_exact",
    ),
    "diagram_kind_purpose": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_focused_diagrams_must_match_their_owner_purpose",
    ),
    "design_support_digest_binding": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_design_support_records_are_complete_and_technology_bound",
    ),
    "architecture_traceability_digest_binding": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_architecture_contract_is_traceable_fail_closed_and_digest_bound",
    ),
}

QUALIFICATION_DEFINITION_OF_COMPLETE_SCENARIO_COVERAGE: dict[str, tuple[str, ...]] = {
    "requirements_15": (
        "tests.test_requirements_v15.Requirements15Tests."
        "test_complete_contract_projects_typed_side_registries",
        "tests.test_requirements_v15.Requirements15Tests."
        "test_approved_schema_14_keeps_exact_digest_without_legacy_bridge",
        "tests.test_requirements_v15.Requirements15Tests."
        "test_gate_a_brief_exposes_target_and_typed_owner_records",
    ),
    "design_8": (
        "tests.test_design_v8.Design8ContractTests."
        "test_complete_projection_is_typed_and_every_table_is_digest_bound",
        "tests.test_design_v8.Design8ContractTests."
        "test_dependency_policy_is_default_deny_and_prefix_is_never_sufficient",
        "tests.test_design_v8.Design8ContractTests."
        "test_exact_approved_design7_digest_is_compatible_but_partial_is_not",
        "tests.test_design_v8.Design8ContractTests."
        "test_gate_b_owner_inventory_projects_design8_without_a_new_domain",
    ),
    "release_claims": (
        "tests.test_engine_composition.EngineCompositionTests."
        "test_release_claim_derives_each_cumulative_target_without_authority",
        "tests.test_engine_composition.EngineCompositionTests."
        "test_release_claim_validator_rejects_overclaim_and_noncanonical_evidence",
    ),
    "aws_authority_projection": (
        "tests.test_document_summaries.DocumentSummaryProjectionTests."
        "test_current_aws_authority_projection_is_not_gate_b_digest_input",
    ),
    "recommendation_compatibility": (
        "tests.test_intake_response.IntakeResponseAcceptanceTests."
        "test_accept_phrase_applies_only_to_the_current_recommendation",
        "tests.test_intake_response.IntakeResponseRejectionTests."
        "test_legacy_accept_phrase_remains_an_exact_compatibility_alias",
    ),
    "architecture_board_semantics": (
        "tests.test_engine_design.EngineDesignTests."
        "test_architecture_board_cross_check_requires_semantic_path_parity",
    ),
    "completion_policy": (
        "tests.test_template_compatibility.TemplateCompatibilityTests."
        "test_fastlane_13_completion_policy_names_each_evidence_level",
        "tests.test_prompt_contracts.PromptPackContractTests."
        "test_project_completion_is_target_specific_and_monotonic",
    ),
    "context_selection_and_owner_locators": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_context_plan_is_route_bounded_ephemeral_and_complete",
        "tests.test_owner_briefs.OwnerBriefProjectionTests."
        "test_source_locator_is_repository_relative_and_digest_bound",
    ),
}


def _normalize_string(value: str) -> str:
    return GIT_SHA.sub(GIT_SHA_SENTINEL, value)


def normalize_report(value: Any, *, key: str | None = None) -> Any:
    """Normalize only approved package and synthetic Git identities."""

    if key == "bootstrap_version":
        return PACKAGE_VERSION_SENTINEL
    if isinstance(value, Mapping):
        return {
            str(item_key): normalize_report(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_report(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_report(item) for item in value]
    if isinstance(value, str):
        return _normalize_string(value)
    return value


def _capture_case(report: dict[str, Any]) -> dict[str, Any]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        doctor.print_human(report)
    return {
        "exit_code": 0 if report["ok"] else 1,
        "human_output": _normalize_string(stream.getvalue()),
        "report": normalize_report(report),
    }


def _project_case(
    temporary: Path,
    name: str,
    configure: Callable[[doctor_fixtures.BootstrapDoctorTests, Path], None],
) -> dict[str, Any]:
    parent = temporary / name
    parent.mkdir()
    fixture = doctor_fixtures.BootstrapDoctorTests()
    project = fixture.copy_project(parent)
    if name.startswith("gate-b"):
        # CANONICALIZATION: bind Gate B to one synthetic commit whose tree is
        # independent of later packaged-source movement. The ignored package is
        # still read and validated by the Engine; it simply cannot perturb the
        # deliberately synthetic Git identity allowed by the parity contract.
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        (project / ".fastlane-parity-baseline").write_text(
            "Fastlane synthetic parity baseline.\n",
            encoding="utf-8",
            newline="\n",
        )
        (project / ".git/info/exclude").write_text(
            "*\n!.fastlane-parity-baseline\n",
            encoding="utf-8",
            newline="\n",
        )
    with mock.patch.dict(
        os.environ,
        {
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
        },
    ):
        configure(fixture, project)
    return _capture_case(doctor.inspect_project(project))


def build_parity_reports() -> dict[str, dict[str, Any]]:
    """Build representative complete Engine outputs from synthetic records."""

    reports = {
        "template_source": _capture_case(
            doctor.inspect_project(REPOSITORY_ROOT, template_source=True)
        ),
        "unconfigured_template": _capture_case(doctor.inspect_project(REPOSITORY_ROOT)),
    }
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        reports["rendered_intake"] = _project_case(
            temporary,
            "rendered-intake",
            lambda _fixture, _project: None,
        )
        reports["gate_a_pending"] = _project_case(
            temporary,
            "gate-a-pending",
            lambda fixture, project: fixture.pending_gate_a(project),
        )

        def approve_gate_a(
            fixture: doctor_fixtures.BootstrapDoctorTests, project: Path
        ) -> None:
            fixture.approve_project(project, gate_b=False)
            fixture.set_non_material_req_evidence(project)
            doctor_fixtures.refresh_document_summaries(project)

        reports["gate_a_approved"] = _project_case(
            temporary, "gate-a-approved", approve_gate_a
        )
        reports["gate_b_pending"] = _project_case(
            temporary,
            "gate-b-pending",
            lambda fixture, project: fixture.pending_gate_b(project),
        )

        def approve_gate_b(
            fixture: doctor_fixtures.BootstrapDoctorTests, project: Path
        ) -> None:
            fixture.approve_project(project)
            fixture.set_non_material_req_evidence(project)
            doctor_fixtures.refresh_document_summaries(project)

        reports["gate_b_approved"] = _project_case(
            temporary, "gate-b-approved", approve_gate_b
        )
    return {name: reports[name] for name in REPORT_CASES}


def build_qualification_reports() -> dict[str, dict[str, Any]]:
    """Build reports not present in the frozen pre-refactor oracle."""

    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)

        def stale_gate_a_summary(
            fixture: doctor_fixtures.BootstrapDoctorTests, project: Path
        ) -> None:
            fixture.pending_gate_a(project)
            baseline = doctor.inspect_project(project)
            prd_path = project / "docs/project/PRD.md"
            source_text = prd_path.read_text(encoding="utf-8")
            prd_summary = next(
                item
                for item in baseline["document_summaries"]["documents"]
                if item["path"] == doctor.PRD_FILE
            )
            product_outcome = next(
                item["value"]
                for item in prd_summary["fields"]
                if item["label"] == "Product outcome"
            )
            changed = source_text.replace(
                f"| Product outcome | {product_outcome} |",
                "| Product outcome | Stale generated value |",
                1,
            )
            if changed == source_text:
                raise AssertionError("qualification summary fixture did not change")
            prd_path.write_text(changed, encoding="utf-8", newline="\n")
            doctor_fixtures.refresh_control_hashes(project)

        def task_ready(
            fixture: doctor_fixtures.BootstrapDoctorTests, project: Path
        ) -> None:
            fixture.approve_project(project)
            fixture.set_non_material_req_evidence(project)
            fixture.initialize_task_plan(
                project,
                doctor_fixtures.ready_task(
                    requirements=(
                        doctor_fixtures.MODERN_TASK_REQUIREMENT_TRACE + "; PROP-001"
                    ),
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    command="python -m unittest tests.test_properties",
                    property_projection=(
                        doctor_fixtures.property_execution_projection()
                    ),
                ),
            )
            doctor_fixtures.refresh_document_summaries(project)

        reports = {
            "stale_gate_a_summary": _project_case(
                temporary, "stale-gate-a-summary", stale_gate_a_summary
            ),
            "task_ready": _project_case(temporary, "gate-b-task-ready", task_ready),
        }
    return {name: reports[name] for name in QUALIFICATION_REPORT_CASES}


def build_deployment_qualification_cases() -> dict[str, dict[str, Any]]:
    """Project every deployment terminal through the public Engine contract."""

    from tests.test_engine_aws_deployment import (
        AwsDeploymentReconciliationRegressionTests,
    )

    fixture = AwsDeploymentReconciliationRegressionTests()
    read_authority = fixture.deployment_read_authority()
    cases: dict[str, dict[str, Any]] = {}

    def capture(name: str, rows: list[tuple[str, ...]], *, read: bool = False) -> None:
        projection = fixture.derive_deployment(
            rows,
            read_authority=read_authority if read else None,
        )
        route = doctor.derive_aws_delivery_route(
            "READY_TO_DEPLOY",
            {"progress_state": "AWS_PREFLIGHT_READY"},
            projection,
            "fast-dev",
        )
        cases[name] = {
            "status": projection["status"],
            "action_status": projection["action_status"],
            "reconciliation_status": projection["reconciliation_status"],
            "phase": projection["phase"],
            "route": list(route) if route else None,
            "issues": list(projection["issues"]),
        }

    for index, action_status in enumerate(
        ("STARTED", "SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN"), start=1
    ):
        rows = [
            fixture.deployment_row(
                evidence_id=f"EV-31{index:02d}",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
            )
        ]
        if action_status != "STARTED":
            rows.append(
                fixture.deployment_row(
                    evidence_id=f"EV-32{index:02d}",
                    phase="AWS-20",
                    status=action_status,
                    observed_at="2027-01-01T00:01:00Z",
                )
            )
        capture(f"action_{action_status.casefold()}", rows)

    for index, action_status in enumerate(
        ("SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN"), start=1
    ):
        rows = [
            fixture.deployment_row(
                evidence_id=f"EV-33{index:02d}",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-02T00:00:00Z",
            ),
            fixture.deployment_row(
                evidence_id=f"EV-34{index:02d}",
                phase="AWS-20",
                status=action_status,
                observed_at="2027-01-02T00:01:00Z",
            ),
            fixture.deployment_row(
                evidence_id=f"EV-35{index:02d}",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-02T00:02:00Z",
                read_authority=read_authority,
            ),
        ]
        capture(f"reconciled_{action_status.casefold()}", rows, read=True)

    for index, reconciliation_status in enumerate(("BLOCKED", "STALE"), start=1):
        rows = [
            fixture.deployment_row(
                evidence_id=f"EV-36{index:02d}",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-03T00:00:00Z",
            ),
            fixture.deployment_row(
                evidence_id=f"EV-37{index:02d}",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-03T00:01:00Z",
            ),
            fixture.deployment_row(
                evidence_id=f"EV-38{index:02d}",
                phase="AWS-30",
                status=reconciliation_status,
                observed_at="2027-01-03T00:02:00Z",
                read_authority=read_authority,
            ),
        ]
        capture(f"reconciliation_{reconciliation_status.casefold()}", rows, read=True)

    return cases


def _branch_complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(
            child,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.IfExp,
                ast.ExceptHandler,
                ast.Assert,
                ast.comprehension,
            ),
        ):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(0, len(child.values) - 1)
        elif isinstance(child, ast.Match):
            score += len(child.cases)
    return score


def doctor_characterization() -> dict[str, Any]:
    """Return deterministic structural metrics for the locked monolith."""

    path = REPOSITORY_ROOT / "scripts/bootstrap_doctor.py"
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    tree = ast.parse(text)
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = node.end_lineno or node.lineno
            functions.append(
                {
                    "branch_complexity": _branch_complexity(node),
                    "end_line": end_line,
                    "line_count": end_line - node.lineno + 1,
                    "name": node.name,
                    "start_line": node.lineno,
                }
            )
        elif isinstance(node, ast.ClassDef):
            classes.append(
                {
                    "end_line": node.end_lineno or node.lineno,
                    "name": node.name,
                    "start_line": node.lineno,
                }
            )
    structural = {"classes": classes, "functions": functions}
    canonical = json.dumps(
        structural, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return {
        "byte_count": len(raw),
        "class_count": len(classes),
        "classes": classes,
        "function_count": len(functions),
        "functions": functions,
        "line_count": len(text.splitlines()),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "structure_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def receipt_contracts() -> dict[str, dict[str, str]]:
    """Capture the five exact owner receipt templates byte-for-byte."""

    text = (REPOSITORY_ROOT / "prompts/CODEX-PROMPTS.md").read_text(encoding="utf-8")
    sections = []
    for heading in (
        "## Exactly accepted Gate receipts",
        "## AWS action receipt templates",
    ):
        start = text.index(heading)
        next_heading = text.find("\n## ", start + len(heading))
        sections.append(text[start:] if next_heading < 0 else text[start:next_heading])
    blocks = []
    for section in sections:
        blocks.extend(
            match.group("body")
            for match in re.finditer(
                r"(?P<fence>`{3}|~{3})text\n(?P<body>.*?)\n(?P=fence)",
                section,
                re.DOTALL,
            )
        )
    result: dict[str, dict[str, str]] = {}
    for block in blocks:
        normalized = block.replace("\r\n", "\n").replace("\r", "\n") + "\n"
        label = normalized.splitlines()[0]
        result[label] = {
            "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "text": normalized,
        }
    return result


def canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def approved_behavior_additions_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Project every exact report subtree hidden by the 1.3 compatibility residue."""

    report = case.get("report")
    if not isinstance(report, Mapping):
        return {}
    projection: dict[str, Any] = {}
    for field in (
        "document_summaries",
        "context_plan",
        "owner_answer_confirmation",
        "owner_decision_brief",
        "owner_decision_inventory",
        "requirements_contract",
        "design_contract",
    ):
        if field in report:
            projection[field] = copy.deepcopy(report[field])
    intake = report.get("intake_foundation")
    if isinstance(intake, Mapping):
        projection["intake_foundation"] = {
            field: copy.deepcopy(intake[field])
            for field in ("next_question_guidance", "project_configuration")
            if field in intake
        }
    basis = report.get("basis")
    if isinstance(basis, Mapping) and "prd_snapshot_sha256" in basis:
        projection["basis"] = {
            "prd_snapshot_sha256": copy.deepcopy(basis["prd_snapshot_sha256"])
        }
    return projection


def approved_behavior_compatibility_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Return the frozen residue after separately pinned 1.3 additions."""

    normalized = copy.deepcopy(dict(case))
    report = normalized.get("report")
    if not isinstance(report, dict):
        return normalized
    report.pop("document_summaries", None)
    intake = report.get("intake_foundation")
    if isinstance(intake, dict):
        intake.pop("next_question_guidance", None)
        intake.pop("project_configuration", None)
    context_plan = report.get("context_plan")
    if isinstance(context_plan, dict):
        for field in ("actual_initial_bytes", "actual_initial_source_bytes"):
            context_plan.pop(field, None)
        resolved_slices: list[dict[str, Any]] = []
        for field in ("resolved_initial_slices", "resolved_on_demand_slices"):
            entries = context_plan.pop(field, None)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for locator_field in (
                    "canonical_sha256",
                    "end_line",
                    "source_bytes",
                    "start_line",
                ):
                    entry.pop(locator_field, None)
                resolved_slices.append(entry)
        if resolved_slices:
            context_plan["resolved_slices"] = sorted(
                resolved_slices,
                key=lambda entry: json.dumps(
                    entry, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                ),
            )
    for owner_field in ("owner_answer_confirmation", "owner_decision_brief"):
        owner_projection = report.get(owner_field)
        if not isinstance(owner_projection, dict):
            continue
        owner_projection.pop("canonical_sha256", None)
        locators = owner_projection.get("source_locators")
        if not isinstance(locators, list):
            continue
        for locator in locators:
            if not isinstance(locator, dict):
                continue
            for field in ("end_line", "section_sha256", "start_line"):
                locator.pop(field, None)
    owner_brief = report.get("owner_decision_brief")
    if isinstance(owner_brief, dict):
        owner_brief.pop("executive_sections", None)
        owner_brief.pop("technical_decision_groups", None)
        owner_basis = owner_brief.get("basis")
        if (
            isinstance(owner_basis, dict)
            and owner_basis.get("design_contract_sha256") is not None
        ):
            owner_basis.pop("design_contract_sha256", None)
    owner_inventory = report.get("owner_decision_inventory")
    if isinstance(owner_inventory, dict):
        owner_inventory.pop("canonical_sha256", None)
        owner_inventory.pop("decisions", None)
    basis = report.get("basis")
    if isinstance(basis, dict):
        basis.pop("prd_snapshot_sha256", None)
    requirements = report.get("requirements_contract")
    if isinstance(requirements, dict):
        requirements_schema = requirements.get("schema_version")
        if requirements_schema in ("1.4", "1.5", "1.6"):
            requirements.pop("canonical_sha256", None)
        if requirements_schema in ("1.5", "1.6"):
            requirements["schema_version"] = "1.4"
            for field in (
                "approved_schema_14_compatibility",
                "completion_target",
                "cross_cutting_risks",
                "datasets",
                "external_obligations",
                "outcome_metrics",
                "requirements_v16",
            ):
                requirements.pop(field, None)
    design = report.get("design_contract")
    if not isinstance(design, dict):
        return normalized
    design_schema = design.get("schema_version")
    if design_schema in (7, 8, 9):
        design.pop("canonical_sha256", None)
    if design_schema in (8, 9):
        design["schema_version"] = 7
    project_contract = design.get("project_contract")
    if isinstance(project_contract, dict):
        project_schema = project_contract.get("schema_version")
        if project_schema in (7, 8, 9):
            project_contract.pop("canonical_sha256", None)
        if project_schema in (8, 9):
            project_contract["schema_version"] = 7
            project_contract.pop("design_v8", None)
        if project_schema == 9:
            project_contract.pop("validation_checks", None)
            project_contract.pop("acceptance_criteria", None)
    diagram_contract = design.get("diagram_contract")
    if isinstance(diagram_contract, dict):
        if design_schema in (7, 8, 9):
            diagram_contract.pop("canonical_sha256", None)
        records = diagram_contract.get("records")
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, dict):
                    continue
                if design_schema in (7, 8, 9):
                    for field in ("rendered_sha256", "semantic_sha256"):
                        record.pop(field, None)
                if design_schema in (8, 9):
                    for field in ("containment", "semantic_relationships"):
                        record.pop(field, None)
    return normalized


def summary_truth_compatibility_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """COMPATIBILITY: retain the public test helper name from Fastlane 1.2.19."""

    return approved_behavior_compatibility_case(case)


def frozen_doctor_characterization() -> dict[str, Any]:
    """Preserve the exact pre-refactor structural baseline when refreshing reports."""

    if ORACLE_PATH.is_file():
        existing = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
        baseline = existing.get("baseline")
        characterization = existing.get("doctor_characterization")
        if (
            isinstance(baseline, Mapping)
            and baseline.get("commit") == BASELINE_COMMIT
            and isinstance(characterization, dict)
        ):
            return characterization
    return doctor_characterization()


def build_oracle() -> dict[str, Any]:
    reports = build_parity_reports()
    return {
        "schema_version": 1,
        "baseline": {
            "commit": BASELINE_COMMIT,
            "package_version": BASELINE_PACKAGE_VERSION,
            "report_schema_version": 2,
        },
        "approved_behavior_changes": FROZEN_APPROVED_BEHAVIOR_CHANGES,
        "summary_truth_compatibility": {
            "base_commit": SUMMARY_TRUTH_BASE_COMMIT,
            "allowed_projection": [
                "document_summaries",
                "intake_foundation.next_question_guidance",
                "intake_foundation.project_configuration",
            ],
            "allowed_locator_metadata": [
                "canonical_sha256",
                "source_bytes",
                "start_line",
                "end_line",
                "actual_initial_source_bytes",
                "actual_initial_bytes",
            ],
            "report_case_digests": SUMMARY_TRUTH_COMPATIBILITY_DIGESTS,
        },
        "normalization": {
            "allowed": [
                "package version",
                "repository or synthetic Git commit identity",
            ],
            "forbidden": [
                "diagnostic IDs or order",
                "paths or messages",
                "lifecycle or next prompt",
                "owner action or continuation",
                "authority or remediation",
                "canonical projections or receipts",
            ],
        },
        "doctor_characterization": frozen_doctor_characterization(),
        "receipt_contracts": receipt_contracts(),
        "report_case_digests": {
            name: canonical_digest(case) for name, case in reports.items()
        },
        "report_cases": reports,
        "scenario_coverage": {
            name: list(selectors) for name, selectors in SCENARIO_COVERAGE.items()
        },
    }


def build_qualification_oracle() -> dict[str, Any]:
    """Freeze current modular boundaries without replacing the original oracle."""

    reports = build_qualification_reports()
    deployment_cases = build_deployment_qualification_cases()
    return {
        "schema_version": 1,
        "baseline": {
            "commit": QUALIFICATION_BASE_COMMIT,
            "package_version": QUALIFICATION_BASE_PACKAGE_VERSION,
            "report_schema_version": 2,
        },
        "approved_behavior_changes": QUALIFICATION_APPROVED_BEHAVIOR_CHANGES,
        "normalization": {
            "allowed": [
                "package version",
                "repository or synthetic Git commit identity",
            ],
            "forbidden": [
                "diagnostic IDs or order",
                "lifecycle or next prompt",
                "owner action or continuation",
                "authority or remediation",
                "deployment action or reconciliation result",
                "canonical projections or receipts",
            ],
        },
        "report_case_digests": {
            name: canonical_digest(case) for name, case in reports.items()
        },
        "report_cases": reports,
        "deployment_case_digests": {
            name: canonical_digest(case) for name, case in deployment_cases.items()
        },
        "deployment_cases": deployment_cases,
        "design_scenario_coverage": {
            name: list(selectors)
            for name, selectors in QUALIFICATION_DESIGN_SCENARIO_COVERAGE.items()
        },
        "definition_of_complete_scenario_coverage": {
            name: list(selectors)
            for name, selectors in (
                QUALIFICATION_DEFINITION_OF_COMPLETE_SCENARIO_COVERAGE.items()
            )
        },
        "aws_scenario_coverage": {
            name: list(selectors)
            for name, selectors in QUALIFICATION_AWS_SCENARIO_COVERAGE.items()
        },
    }


def _benchmark_platform() -> dict[str, str]:
    distribution = ""
    distribution_version = ""
    if platform.system() == "Linux":
        try:
            release = platform.freedesktop_os_release()
        except OSError:
            release = {}
        distribution = release.get("ID", "")
        distribution_version = release.get("VERSION_ID", "")
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "distribution": distribution,
        "distribution_version": distribution_version,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
    }


def _eight_task_plan() -> str:
    blocks: list[str] = []
    requirement_ids = doctor_fixtures.MODERN_APPROVED_REQUIREMENT_IDS
    for index in range(8):
        assigned = requirement_ids[index::8]
        trace = [
            "REQ-0001",
            *(
                identifier
                for requirement_id in assigned
                for identifier in (requirement_id, f"AC-{requirement_id}")
            ),
        ]
        property_task = index == 0
        if property_task:
            trace.append("PROP-001")
        block = doctor_fixtures.ready_task(
            write_set=f"app/benchmark/task_{index + 1:03d}.py",
            requirements="; ".join(trace),
            design=(
                "DES-0001; TECH: TECH-0001, TECH-0007"
                if property_task
                else "DES-0001; TECH: TECH-0001"
            ),
            command=(
                "python -m unittest tests.test_properties"
                if property_task
                else "python -m unittest"
            ),
            property_projection=(
                doctor_fixtures.property_execution_projection() if property_task else ""
            ),
        )
        blocks.append(block.replace("TASK-001", f"TASK-{index + 1:03d}"))
    return "".join(blocks)


def _benchmark_projects(
    temporary: Path,
) -> dict[str, tuple[Callable[[], Any], str, int, int]]:
    fixture = doctor_fixtures.BootstrapDoctorTests()

    def copy(name: str) -> Path:
        parent = temporary / name
        parent.mkdir()
        return fixture.copy_project(parent)

    gate_a = copy("gate-a")
    fixture.pending_gate_a(gate_a)
    gate_b = copy("gate-b")
    fixture.pending_gate_b(gate_b)
    task_heavy = copy("eight-task-plan")
    fixture.approve_project(task_heavy)
    fixture.set_non_material_req_evidence(task_heavy)
    fixture.initialize_task_plan(task_heavy, _eight_task_plan())
    state_path = task_heavy / "bootstrap.yaml"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["execution"]["attempts"] = {f"TASK-{index:03d}": 0 for index in range(1, 9)}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    doctor_fixtures.refresh_document_summaries(task_heavy)
    return {
        "template": (
            lambda: doctor.inspect_project(REPOSITORY_ROOT, template_source=True),
            "INTAKE_REQUIRED",
            0,
            0,
        ),
        "gate_a": (
            lambda: doctor.inspect_project(gate_a),
            "WAITING_GATE_A",
            0,
            0,
        ),
        "gate_b": (
            lambda: doctor.inspect_project(gate_b),
            "WAITING_GATE_B",
            0,
            0,
        ),
        "eight_task_plan": (
            lambda: doctor.inspect_project(task_heavy),
            "CONSTRUCTION_AUTONOMOUS",
            8,
            8,
        ),
    }


def _assert_benchmark_report(
    scenario: str,
    report: Mapping[str, Any],
    lifecycle: str,
    task_total: int,
    task_ready: int,
) -> None:
    tasks = report.get("tasks")
    coherent = bool(
        report.get("ok") is True
        and report.get("lifecycle_state") == lifecycle
        and isinstance(tasks, Mapping)
        and tasks.get("total") == task_total
        and tasks.get("ready") == task_ready
    )
    if not coherent:
        raise RuntimeError(f"{scenario} benchmark scenario is not coherent")


def benchmark_engine_scenarios(
    warmups: int = 2,
    iterations: int = 10,
) -> dict[str, Any]:
    """Measure four prebuilt lifecycle scenarios without persisting machine data."""

    if warmups < 1:
        raise ValueError("warmups must be positive")
    if iterations < 1:
        raise ValueError("iterations must be positive")
    results: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as directory:
        scenarios = _benchmark_projects(Path(directory))
        for name, (inspect, lifecycle, task_total, task_ready) in scenarios.items():
            for _index in range(warmups):
                _assert_benchmark_report(
                    name, inspect(), lifecycle, task_total, task_ready
                )
            wall_ms: list[float] = []
            cpu_ms: list[float] = []
            for _index in range(iterations):
                wall_start = time.perf_counter()
                cpu_start = time.process_time()
                report = inspect()
                cpu_ms.append((time.process_time() - cpu_start) * 1000)
                wall_ms.append((time.perf_counter() - wall_start) * 1000)
                _assert_benchmark_report(
                    name, report, lifecycle, task_total, task_ready
                )
            tracemalloc.start()
            try:
                memory_report = inspect()
                _current, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            _assert_benchmark_report(
                name, memory_report, lifecycle, task_total, task_ready
            )
            results[name] = {
                "lifecycle_state": lifecycle,
                "task_total": task_total,
                "task_ready": task_ready,
                "peak_memory_mib": peak / (1024 * 1024),
                "warm_median_cpu_ms": statistics.median(cpu_ms),
                "warm_median_wall_ms": statistics.median(wall_ms),
            }
    return {
        "warmups": warmups,
        "iterations": iterations,
        "platform": _benchmark_platform(),
        "scenarios": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write-qualification-oracle", action="store_true")
    action.add_argument("--benchmark", action="store_true")
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args(argv)
    if args.benchmark:
        print(
            json.dumps(
                benchmark_engine_scenarios(
                    warmups=args.warmups,
                    iterations=args.iterations,
                ),
                indent=2,
            )
        )
        return 0
    output_path = QUALIFICATION_ORACLE_PATH
    payload = build_qualification_oracle()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {output_path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
