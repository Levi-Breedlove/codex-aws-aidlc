"""Historical import surface for the stable ``bootstrap_doctor`` facade.

Canonical inputs are the modular Engine modules named below. The installer
adds only symbols exposed by Fastlane 1.2.16 that the thin doctor no longer
owns directly. It performs no I/O, derives no policy, and grants no authority.
"""

from __future__ import annotations

import hashlib
import re
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any


_MODULE_SUFFIXES = (
    "api",
    "core.contracts",
    "core.diagnostics",
    "core.ids",
    "core.snapshot",
    "package.manifest",
    "package.state",
    "define",
    "define.coverage",
    "define.intake",
    "define.models",
    "define.project",
    "define.requirements",
    "design",
    "design.architecture",
    "design.envelope",
    "design.harness",
    "design.models",
    "design.project",
    "design.source",
    "design.support",
    "deliver",
    "deliver.evidence",
    "deliver.models",
    "deliver.repository",
    "deliver.tasks",
    "aws",
    "authority.aws",
    "authority.github",
    "authority.models",
    "authority.receipts",
    "authority.write",
    "composition",
    "orchestration",
    "owner_decisions",
    "project_delivery",
    "project_inspection",
    "project_validation",
    "remediation",
    "report",
    "routing",
)

# COMPATIBILITY: this is the exact set of historical doctor-level names that
# moved out of the facade during the 1.2.17 extraction.
_LEGACY_NAMES = frozenset(
    """
    APPLICATION_SOURCE_DIAGNOSTIC_CODES APPLICATION_SOURCE_DISPOSITION_FIELD
    AWS_CORE_GENERATED_DIAGNOSTICS AWS_DEPLOYMENT_TERMINAL_STATUSES
    AWS_DEPLOYMENT_ATTEMPT_ID AWS_DEPLOYMENT_EVIDENCE_HEADING
    AWS_DEPLOYMENT_RECEIPT_FIELDS AWS_DERIVED_ARTIFACT AWS_EXACT_ARTIFACT
    AWS_EXECUTION_CONTRACT_HEADERS AWS_PLAN_BINDING AWS_PREFLIGHT_ID
    AWS_READ_AUTHORIZATION_ID AWS_READ_ONLY_OPERATION
    AWS_READ_PREFLIGHT_RECEIPT_FIELDS AWS_TEARDOWN_EVIDENCE_HEADING
    AWS_TEARDOWN_RECEIPT_FIELDS
    ArchitectureContract AssumptionLifecycleRecord CONTEXT_MAXIMUM_INITIAL_BYTES
    ChangeImpactRow CoverageOmission DEFINE_AGENT_DIAGNOSTICS
    DELIVERY_VALIDATION_POLICY DELIVER_AGENT_DIAGNOSTICS DESIGN_AGENT_DIAGNOSTICS
    Decimal DiagnosticCollector InspectedTask IntakeCard IntakeQuestion
    InvalidOperation Iterable LEGACY_TASK_AWS_MODE ManifestPolicy
    NormalizedOwnerResponse OWNER_AUTHORIZATION_DIAGNOSTICS
    OWNER_CONFIRMATION_FIELDS OWNER_DECISION_DIAGNOSTICS
    OWNER_INTAKE_DECISION_METADATA OWNER_SETUP_DIAGNOSTICS
    OWNER_TECHNICAL_DOMAIN_METADATA ObservationError PROJECT_NAME_TOKEN
    PROMPT_DOCS_ONLY_AWS_MODES PROMPT_MUTATION_AWS_MODES
    PROMPT_READ_ONLY_AWS_MODES ProjectDesignContract ProjectSnapshot
    PropertyTestEvidenceRow PurePosixPath RequirementsChangeLineage Sequence
    SnapshotObserver StatePolicy TASK_REPLAN_DIAGNOSTICS TECHNICAL_DOMAIN_ORDER
    TECHNOLOGY_CONCERN_DOMAINS TECHNOLOGY_DECISION_ID TaskCompletionEvidenceRow
    TaskRequirementCoverageResult TechnologyDecision UNCONFIGURED_SETUP_DIAGNOSTICS
    _action_authorization_rows _authorization_expiry_ceiling
    _authorization_valid_until _context_request _cost_at_most
    _current_prd_basis_ids_core _deployment_reconciliation_read_authority
    _deployment_values _deployment_values_core _derive_architecture_contract
    _derive_architecture_contract_core _derive_gate_a_decision_inventory
    _derive_gate_b_decision_inventory _derive_project_design_contract_core
    _derive_aws_execution_projection_core _derive_deployment_sequence_state_core
    _derive_read_preflight_state_core _derive_task_requirement_coverage_core
    _derive_teardown_sequence_state_core _envelope_scalar _envelope_values
    _exact_receipt_fields _execution_contract_rows _gate_b_rollback_value
    _iso_datetime _machine_cost _machine_list _machine_value
    _missing_property_coverage_core _mutation_cost_within_gate_b
    _owner_decision_section _owner_readable_journeys _owner_stable_ids
    _owner_technical_domain _parse_cost_ceiling _parse_property_test_evidence_core
    _parse_aws_lifecycle_intent_record_core _parse_release_decision_record_core
    _read_bound_honors_cost_posture
    _receipt_artifact_matches_gate_b _receipt_fields
    _receipt_identity_matches_gate_b _receipt_scope_within_gate_b
    _receipt_validity_within_gate_b _resolve_context_metadata
    _reviewed_script_contract _schema_13_requirement_rows
    _source_disposition_owner_parts _split_authority_values _state_trigger_map
    _summary_bullet _summary_table _summary_value
    _task_requirement_rules_core _teardown_reconciliation_read_authority
    _technology_version_policy_allows_core _unique_owner_text
    _validate_done_property_evidence_core _validate_property_projection_core
    _validate_task_records_core answer_confirmation brownfield_contract_issues
    canonical_id_list command_matches_prefix concrete_requirement_subject
    current_prd_basis_ids dataclass datetime derive_change_impact_contract
    empty_owner_decision_brief empty_owner_decision_inventory exact_selection
    explicit_timestamp external_target_contains field
    finalize_owner_decision_inventory gate_a_method_contract_issues
    gate_a_readiness_card_issues git_read has_symlink_component
    inspect_task_sections intake_detail_safety_code intake_reply_token
    iso_datetime lifecycle_intent_record_boundary_is_settled marked_receipt
    measurable_acceptance_is_bound normalize_aws_region normalize_project_name
    observable_requirement_response os owner_claim owner_source_locator
    parse_authorized_ids parse_aws_environment parse_command_prefixes
    parse_envelope_paths parse_envelope_targets parse_exact_id_list
    parse_future_expiry parse_future_expiry_at parse_github_constraints
    parse_property_test_evidence parse_task_boundary parse_verification_matrix
    release_lifecycle_intent_boundary_is_settled
    split_table_row strip_generated_summary technology_reasoning_parts timezone
    unresolved unselected_selection validate_application_source_root
    validate_authorized_baseline_repository validate_aws_artifact
    validate_aws_lifecycle_intent validate_brownfield_contract
    validate_checkpoint_record validate_construction_envelope
    validate_construction_repository validate_done_property_evidence
    validate_gate_a_readiness_card validate_package_manifest
    validate_package_placeholders validate_package_prompt_pack
    validate_package_state_schema validate_readiness_card
    validate_release_decision validate_task_property_execution_projection
    validate_tasks_against_envelope validation_commands
    """.split()
)

_LEGACY_ALIASES = {
    "_derive_aws_execution_projection_core": "derive_aws_execution_projection",
    "_derive_deployment_sequence_state_core": "derive_deployment_sequence_state",
    "_derive_read_preflight_state_core": "derive_read_preflight_state",
    "_derive_teardown_sequence_state_core": "derive_teardown_sequence_state",
}


def _source_modules() -> tuple[ModuleType, ...]:
    package = __package__ or "fastlane_engine"
    return tuple(import_module(f"{package}.{suffix}") for suffix in _MODULE_SUFFIXES)


def install_legacy_doctor_exports(namespace: dict[str, object]) -> None:
    """COMPATIBILITY: restore the historical surface without overriding facades."""

    modules = _source_modules()
    unresolved: list[str] = []
    for name in sorted(_LEGACY_NAMES):
        if name in namespace:
            continue
        for module in modules:
            if hasattr(module, name):
                namespace[name] = getattr(module, name)
                break
        else:
            target = _LEGACY_ALIASES.get(name)
            if target is not None:
                for module in modules:
                    if hasattr(module, target):
                        namespace[name] = getattr(module, target)
                        break
                else:
                    unresolved.append(name)
            else:
                unresolved.append(name)
    if unresolved:
        raise RuntimeError(
            "Fastlane doctor compatibility exports are unavailable: "
            + ", ".join(unresolved)
        )

    observation = import_module(f"{__package__}.project_inspection")
    delegated_safe_read_text = observation.safe_read_text

    def safe_read_text(ctx: Any, relative: str, *, required: bool = True) -> str | None:
        """COMPATIBILITY: honor historical facade-level observation limits."""

        ctx._observer.max_files = int(namespace["MAX_REQUIRED_FILES"])
        ctx._observer.max_file_bytes = int(namespace["MAX_REQUIRED_FILE_BYTES"])
        ctx._observer.max_source_bytes = int(namespace["MAX_PROJECT_SOURCE_BYTES"])
        return delegated_safe_read_text(ctx, relative, required=required)

    def bounded_prd_snapshot(
        root: Path, expected_sha256: str | None = None
    ) -> tuple[str, str]:
        """COMPATIBILITY: preserve bounded snapshot monkeypatch seams."""

        context = observation.Context(root=root.resolve())
        text = safe_read_text(context, observation.PRD_FILE)
        if text is None or context.has_errors:
            raise ValueError("Unable to read a bounded PRD snapshot")
        raw_text = context.presentation_texts.get(observation.PRD_FILE, text)
        digest = (
            "sha256:"
            + hashlib.sha256(
                observation.canonical_bytes_without_generated_summary(raw_text)
            ).hexdigest()
        )
        if expected_sha256 is not None and (
            re.fullmatch(r"sha256:[0-9a-f]{64}", expected_sha256) is None
            or digest != expected_sha256
        ):
            raise ValueError("PRD snapshot changed after project inspection")
        return text, digest

    namespace["safe_read_text"] = safe_read_text
    namespace["bounded_prd_snapshot"] = bounded_prd_snapshot

    def derive_external_authority(
        ctx: Any,
        envelope: dict[str, str],
        lane: str | None,
        construction_authorization: str,
        *,
        cost_posture: str = "",
        aws_progress_state: str | None = None,
        active_artifact: str = "",
        preflight: Any = None,
        aws_action_phase: str | None = None,
        teardown_review: Any = None,
        deployment_sequence: Any = None,
    ) -> dict[str, Any]:
        """COMPATIBILITY: preserve doctor monkeypatch seams over authority."""

        return namespace["_derive_external_authority_core"](
            ctx,
            envelope,
            lane,
            construction_authorization,
            cost_posture=cost_posture,
            aws_progress_state=aws_progress_state,
            active_artifact=active_artifact,
            preflight=preflight,
            aws_action_phase=aws_action_phase,
            teardown_review=teardown_review,
            deployment_sequence=deployment_sequence,
            read_authority_deriver=namespace["_read_preflight_receipt_authority"],
            action_authority_deriver=namespace["_receipt_external_authority"],
        )

    namespace["derive_external_authority"] = derive_external_authority


def patchable_git_observers(namespace: dict[str, Any]) -> tuple[Any, Any]:
    """COMPATIBILITY: retain doctor-level trusted-Git mocking seams."""

    def git_read(root: Path, *arguments: str) -> Any:
        trusted_git = namespace["resolve_trusted_git"](root)
        options = {
            "resolve_git": lambda _root: trusted_git,
            "run": namespace["subprocess"].run,
        }
        return namespace["_snapshot"].git_read(root, *arguments, **options)

    def inspect_git_baseline(root: Path) -> str:
        try:
            trusted_git = namespace["resolve_trusted_git"](root)
        except OSError:
            return "PENDING"
        return namespace["_snapshot"].inspect_git_baseline(
            root,
            resolve_git=lambda _root: trusted_git,
            run=namespace["subprocess"].run,
        )

    return git_read, inspect_git_baseline


def patchable_design_contract_facade(namespace: dict[str, Any], facade: Any) -> Any:
    """COMPATIBILITY: retain the doctor-level pure-Design evaluator seam."""

    def derive_design_contract(
        text: str,
        design_revision: str | None,
        *,
        required: bool = False,
        grandfather_approved_v1: bool = False,
        coverage_contract: Any = None,
        requirements_contract: Any = None,
    ) -> Any:
        return facade(
            text,
            design_revision,
            required=required,
            grandfather_approved_v1=grandfather_approved_v1,
            coverage_contract=coverage_contract,
            requirements_contract=requirements_contract,
            _evaluator=namespace["_derive_design_contract_core"],
        )

    return derive_design_contract


__all__ = (
    "install_legacy_doctor_exports",
    "patchable_design_contract_facade",
    "patchable_git_observers",
)
