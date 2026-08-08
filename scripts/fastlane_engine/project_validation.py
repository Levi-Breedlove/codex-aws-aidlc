"""Cross-domain project contract validation for Fastlane orchestration.

Canonical inputs are bounded project text, immutable snapshots, and normalized
Define/Design/Delivery records. Returns diagnostics through the caller context.
Git access is read-only and trusted; this module never writes, routes, approves,
or grants GitHub or AWS authority. Fastlane 1.2.16 behavior is preserved.
"""

from __future__ import annotations

import html
import re
from typing import Any, Mapping

from .authority.receipts import exact_selection, marked_receipt, unselected_selection
from .core.contracts import table_after_heading
from .core.ids import (
    clean_cell,
    explicit_timestamp,
    explicit_value,
    parse_exact_id_list,
    unresolved,
)
from .core.snapshot import GitObservationError, has_symlink_component
from .define.coverage import derive_change_impact_contract, derive_coverage_contract
from .define.intake import derive_intake_foundation_contract
from .define.models import (
    CoverageContract,
    IntakeFoundationContract,
    RequirementsContract,
)
from .define.project import (
    brownfield_contract_issues,
    derive_req_aws_materiality,
    gate_a_readiness_card_issues,
)
from .define.requirements import (
    _state_trigger_map,
    authoritative_requirement_ids,
    derive_requirements_contract,
    gate_a_method_contract_issues,
)
from .design import (
    APPLICATION_SOURCE_DIAGNOSTIC_CODES,
    APPLICATION_SOURCE_DISPOSITION_FIELD,
    ArchitectureContract,
    DesignContract,
    HarnessContract,
    ProjectDesignContract,
    _derive_architecture_contract as _derive_architecture_contract_core,
    canonical_envelope_sha256,
    current_prd_basis_ids as _current_prd_basis_ids_core,
    derive_design_contract as _derive_design_contract_core,
    derive_project_design_contract as _derive_project_design_contract_core,
    parse_authorized_ids,
    parse_aws_environment,
    parse_command_prefixes,
    parse_envelope_paths,
    parse_envelope_targets,
    parse_github_constraints,
    parse_task_boundary,
    validate_application_source_root,
    validate_application_source_write_set,
    validate_aws_artifact,
)
from .package.manifest import (
    validate_manifest as validate_package_manifest,
    validate_placeholders as validate_package_placeholders,
    validate_prompt_pack as validate_package_prompt_pack,
)
from .package.state import validate_state_schema as validate_package_state_schema
from .project_inspection import (
    AUTH_ID,
    AWS_BOUNDARIES,
    AWS_DETAIL_FIELDS,
    AWS_LANES,
    DELIVERY_PROFILES,
    DES_ID,
    ENVELOPE_EXPLICIT_FIELDS,
    GATE_A_STATES,
    GATE_B_READINESS_FIELDS,
    GATE_B_STATES,
    GITHUB_BOUNDARIES,
    MANIFEST_POLICY,
    PRD_FILE,
    PROJECT_MODES,
    REQ_ID,
    RISK_LEVELS,
    STATE_FILE,
    STATE_POLICY,
    Context,
    explicit_human_approver,
    parse_cost_posture,
    parse_future_expiry,
    safe_read_required_binary,
    safe_read_text,
    validate_aws_cost_ceiling,
)

try:
    from fastlane_project_identity import normalize_aws_region, normalize_project_name
except ModuleNotFoundError:
    from scripts.fastlane_project_identity import (
        normalize_aws_region,
        normalize_project_name,
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
    _evaluator: Any = None,
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
    evaluator = _evaluator or _derive_design_contract_core
    return evaluator(
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
    """SAFETY: validate the exact Gate B construction authority boundary."""

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
            envelope.get("Authorization expiry or completion condition", ""),
            observed_at=ctx.observed_at,
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
            parse_future_expiry(
                envelope.get("AWS authorization validity", ""),
                observed_at=ctx.observed_at,
            )
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
            parse_future_expiry(
                envelope.get("AWS authorization validity", ""),
                observed_at=ctx.observed_at,
            )
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


def _intake_repository_mode(
    selections: Mapping[str, str | None],
    state: Mapping[str, Any],
    *,
    template_source: bool,
) -> str | None:
    """Preserve repository classification without presenting it as owner intent."""

    mode = selections.get("mode")
    setup_state = state.get("setup") if isinstance(state.get("setup"), dict) else {}
    if (
        mode is None
        and not template_source
        and setup_state.get("status")
        not in {"UNCONFIGURED_TEMPLATE", "{{SETUP_STATUS}}"}
    ):
        return "greenfield"
    return mode


def _record_project_configuration_issues(
    ctx: Context, intake_contract: IntakeFoundationContract
) -> None:
    """Fail closed when confirmed owner context conflicts with recorded mode."""

    actions = set(intake_contract.project_configuration.codex_actions)
    if intake_contract.status == "READY_FOR_REQUIREMENTS" and (
        "RECONCILE_PROJECT_MODE" in actions
    ):
        ctx.error(
            "PROJECT_CONFIGURATION_CONFLICT",
            "Confirmed owner work context conflicts with the recorded project mode",
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
    """SAFETY: compose canonical PRD validation in diagnostic order."""

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
    intake_repository_mode = _intake_repository_mode(
        selections, state, template_source=ctx.template_source
    )
    intake_contract, intake_issues = derive_intake_foundation_contract(
        text,
        intake_repository_mode,
        grandfather_current_gate_a=grandfather_approved_v1_requirements,
        project_selections=selections,
    )
    for code, issue in intake_issues:
        ctx.error(code, issue, PRD_FILE)
    if gate_a_ready_or_current and intake_contract.status != "READY_FOR_REQUIREMENTS":
        ctx.error(
            "INTAKE_FOUNDATION_REQUIRED",
            "Gate A requires a complete owner-grounded intake foundation and no pending card",
            PRD_FILE,
        )
    _record_project_configuration_issues(ctx, intake_contract)
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


def validate_authorized_baseline_repository(ctx: Context, baseline: str) -> None:
    """Prove Gate B's full authorized baseline resolves in a regular worktree."""

    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", baseline) is None:
        return
    try:
        inside = ctx.git_result("rev-parse", "--is-inside-work-tree")
        bare = ctx.git_result("rev-parse", "--is-bare-repository")
        resolved = ctx.git_result("rev-parse", "--verify", f"{baseline}^{{commit}}")
    except GitObservationError as exc:
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
