"""Deterministic non-authoritative owner decision projections.

Canonical inputs are already-parsed requirements and Design results plus the
canonical PRD text. Outputs are derived Owner Brief and Answer Confirmation
records. This module performs no I/O, routing, mutation, approval, authorization,
or rendering and preserves the Fastlane 1.2.16 projection schemas.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .core.contracts import contract_table_after_heading, table_after_heading
from .core.ids import clean_cell, explicit_value
from .core.markdown_index import heading_title_span
from .define.intake import (
    INTAKE_FOUNDATION_FIELDS,
    INTAKE_FOUNDATION_HEADERS,
    INTAKE_FOUNDATION_HEADING,
    OWNER_WORK_CONTEXT_SELECTIONS,
)
from .define.models import (
    IntakeFoundationContract,
    IntakeQuestion,
    NormalizedOwnerResponse,
    RequirementsContract,
)
from .design import (
    APPLICATION_SOURCE_BROWNFIELD,
    APPLICATION_SOURCE_GREENFIELD,
    JOURNEY_HEADERS,
    JOURNEY_HEADING,
    ApplicationSourceDisposition,
    DesignContract,
    TechnologyDecision,  # noqa: F401 - stable compatibility re-export
)
from .owner_decision_sections import (
    design8_owner_decision_additions,
    finalize_gate_b_inventory,
    gate_a_owner_sections,
    gate_b_technical_groups,
    group_owner_technologies,
    owner_decision_record,
    technology_owner_reasoning,
)

try:
    from ..fastlane_owner_briefs import (
        GATE_B_NAVIGATION_LOCATOR_KEYS,
        TECHNICAL_DOMAIN_ORDER,
        answer_confirmation,
        claim as owner_claim,
        empty_owner_decision_brief,
        empty_owner_decision_inventory,
        finalize_owner_decision_brief,
        finalize_owner_decision_inventory,
        source_locator as owner_source_locator,
    )
except ImportError:  # Executed with scripts/ on sys.path.
    from fastlane_owner_briefs import (
        GATE_B_NAVIGATION_LOCATOR_KEYS,
        TECHNICAL_DOMAIN_ORDER,
        answer_confirmation,
        claim as owner_claim,
        empty_owner_decision_brief,
        empty_owner_decision_inventory,
        finalize_owner_decision_brief,
        finalize_owner_decision_inventory,
        source_locator as owner_source_locator,
    )


PRD_FILE = "docs/project/PRD.md"
REQ_ID = re.compile(r"REQ-\d{4,}")
DES_ID = re.compile(r"DES-\d{4,}")
AUTH_ID = re.compile(r"AUTH-\d{4,}")


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


GATE_B_LOCATOR_SPECS = (
    ("technical-plan", "Technical plan", "14. Architecture overview"),
    ("technology-register", "Technology decisions", "Technology decisions"),
    ("selected-architecture", "Selected architecture", "Selected architecture"),
    ("components", "Component design", "15. Component design"),
    ("interfaces", "Interfaces and contracts", "16. Interfaces and contracts"),
    ("data-lifecycle", "Data model and lifecycle", "17. Data model and lifecycle"),
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
    (
        GATE_B_NAVIGATION_LOCATOR_KEYS[0],
        "Complete proposed architecture",
        "Proposed system at a glance",
    ),
    (
        GATE_B_NAVIGATION_LOCATOR_KEYS[1],
        "AWS implementation diagram",
        "AWS implementation at a glance",
    ),
    (GATE_B_NAVIGATION_LOCATOR_KEYS[2], "Project diagram guide", "Diagram guide"),
)


def _owner_locator_for_heading(
    text: str,
    *,
    key: str,
    label: str,
    heading: str,
    required: bool = True,
) -> dict[str, Any]:
    """Resolve a brief locator through the Engine's canonical heading parser."""

    span = heading_title_span(text, heading)
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


def _whole_system_architecture_selection(
    design_contract: DesignContract, selection: Any
) -> str:
    candidate = next(
        (
            item
            for item in design_contract.architecture.candidates
            if item.candidate_id == selection.selected_candidate
        ),
        None,
    )
    return (
        "Whole-system architecture: "
        + selection.selected_candidate
        + (f" — {candidate.architecture_summary}" if candidate is not None else "")
    )


def _required_harness_owner_selections(design_contract: DesignContract) -> list[str]:
    return [
        f"{row.harness_id}: {row.selected_check}; "
        f"COMMAND: {row.exact_command}; EVIDENCE: {row.evidence_destination}"
        for row in design_contract.harness.rows
        if row.harness_id in design_contract.harness.required_ids
    ]


def _gate_b_recommendation(design_contract: DesignContract, selection: Any) -> str:
    candidate = next(
        (
            item
            for item in design_contract.architecture.candidates
            if item.candidate_id == selection.selected_candidate
        ),
        None,
    )
    return selection.selected_candidate + (
        f" — {candidate.architecture_summary}" if candidate is not None else ""
    )


def _gate_b_construction_boundary(envelope: Mapping[str, str]) -> str:
    return "; ".join(
        (
            "Outcome: " + envelope.get("Authorized outcome", "Not yet recorded."),
            "Writes: " + envelope.get("Allowed repository write set", "NONE"),
            "Excludes: " + envelope.get("Excluded or owner-only write set", "NONE"),
            "Commands: " + envelope.get("Local command boundary", "NONE"),
            "Tasks: " + envelope.get("Maximum generated tasks", "NONE"),
            "Attempts: " + envelope.get("Attempt budget", "NONE"),
            "Checkpoints: " + envelope.get("Checkpoint cadence", "NONE"),
            "External state: " + envelope.get("Allowed external-state targets", "NONE"),
            "GitHub: " + envelope.get("GitHub boundary", "NONE"),
            "AWS: " + envelope.get("AWS boundary", "NONE"),
        )
    )


def _owner_intake_selections(inventory: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(item.get("decision_id")): str(item.get("selection", ""))
        for item in inventory.get("decisions", [])
        if isinstance(item, Mapping)
    }


def _gate_a_outcome_text(
    selections: Mapping[str, str], readiness: Mapping[str, str]
) -> str:
    return selections.get("INTAKE-0004", readiness.get("Outcome", "Not yet recorded."))


def _gate_a_boundary(selections: Mapping[str, str]) -> str:
    return selections.get("INTAKE-0005") or "Not yet recorded."


def _gate_a_success_text(
    selections: Mapping[str, str], readiness: Mapping[str, str]
) -> str:
    measure = selections.get("INTAKE-0006", "Not yet recorded.").rstrip(".; ")
    acceptance = readiness.get(
        "Measurable requirement/acceptance IDs", "Not yet recorded."
    )
    return measure + "; acceptance records: " + acceptance


def _gate_a_metric_text(requirements: RequirementsContract) -> str:
    return (
        "; ".join(
            f"{item.metric_id}: {item.metric}; target {item.target}; "
            f"window {item.measurement_window}; evidence {item.evidence_source}; "
            f"owner {item.accountable_role}; guardrail {item.guardrail}; "
            f"miss action {item.missed_target_action}"
            for item in requirements.outcome_metrics
        )
        or "Not yet recorded."
    )


def _gate_a_dataset_text(requirements: RequirementsContract) -> str:
    return (
        "; ".join(
            f"{item.dataset_id}: {item.dataset_category}; {item.classification}; "
            f"source {item.source_of_truth}; access {item.access_boundary}; "
            f"retention {item.retention}; deletion {item.deletion}; "
            f"recovery {item.recovery}; residency {item.residency}; "
            f"migration {item.migration}; audit {item.audit_obligation}; "
            f"owner {item.accountable_role}"
            for item in requirements.datasets
        )
        or "Not yet recorded."
    )


def _gate_a_obligation_text(requirements: RequirementsContract) -> str:
    return (
        "; ".join(
            f"{item.obligation_id}: {item.applicability}; {item.obligation}; "
            f"basis {item.source_basis}; owner {item.accountable_role}; "
            f"review {item.review_trigger}"
            for item in requirements.external_obligations
        )
        or "Not yet recorded."
    )


def _gate_a_risk_text(requirements: RequirementsContract) -> str:
    return (
        "; ".join(
            f"{item.risk_id}: {item.risk}; {item.likelihood}/{item.impact}; "
            f"owner {item.accountable_role}; mitigation {item.mitigation}; "
            f"revisit {item.revisit_trigger}; status {item.status}"
            for item in requirements.cross_cutting_risks
        )
        or "Not yet recorded."
    )


def _derive_gate_b_decision_inventory(
    design_contract: DesignContract,
    requirements_revision: str,
    design_revision: str,
    authorization_id: str,
    *,
    status: str,
) -> tuple[dict[str, Any], list[str]]:
    """SAFETY: require one complete Gate B owner decision inventory."""
    issues: list[str] = []
    grouped = group_owner_technologies(
        design_contract.technology_decisions,
        TECHNICAL_DOMAIN_ORDER,
        _owner_technical_domain,
    )
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
        rationales, alternatives, reasoning_issues = technology_owner_reasoning(
            technologies, required=status == "READY"
        )
        issues.extend(reasoning_issues)
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
                0, _whole_system_architecture_selection(design_contract, selection)
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
            selections.extend(_required_harness_owner_selections(design_contract))
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
        extension = design_contract.project_contract.design_v8
        additions = design8_owner_decision_additions(
            domain,
            extension,
            enabled=design_contract.project_contract.schema_version >= 8,
        )
        selections.extend(additions.selections)
        rationales.extend(additions.rationales)
        alternatives.extend(additions.alternatives)
        tradeoffs.extend(additions.tradeoffs)
        safeguards.extend(additions.safeguards)
        reconsider.extend(additions.reconsider)
        basis_ids = sorted(set(basis_ids) | set(additions.basis_ids))
        evidence_ids = [item.evidence_id for item in evidence]
        evidence_ids = list(dict.fromkeys([*evidence_ids, *additions.evidence_ids]))
        decisions.append(
            owner_decision_record(
                decision_id=decision_id,
                domain=domain,
                title=title,
                owner_effect=owner_effect,
                selections=selections,
                rationales=rationales,
                alternatives=alternatives,
                tradeoffs=tradeoffs,
                safeguards=safeguards,
                reconsider=reconsider,
                basis_ids=basis_ids,
                evidence_ids=evidence_ids,
                source_evidence_complete=additions.source_evidence_complete,
                source_keys=source_keys,
                schema_version=design_contract.project_contract.schema_version,
                unique_text=_unique_owner_text,
            )
        )
    finalized, combined_issues = finalize_gate_b_inventory(
        status,
        TECHNICAL_DOMAIN_ORDER,
        decisions,
        issues,
        finalize_owner_decision_inventory,
    )
    return finalized, combined_issues


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
    """SAFETY: derive one fail-closed gate view and complete inventory."""

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
        intake_selections = _owner_intake_selections(inventory)
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
        sections = gate_a_owner_sections(
            section=_owner_decision_section,
            requirements_revision=requirements_revision,
            intake=intake_contract,
            requirements=requirements_contract,
            gate_a_card=gate_a_card,
            gate_a_analysis=gate_a_analysis,
            readable_journeys=readable_journeys,
            outcome_text=_gate_a_outcome_text(intake_selections, gate_a_card),
            boundary_text=_gate_a_boundary(intake_selections),
            success_text=_gate_a_success_text(intake_selections, gate_a_card),
            metric_text=_gate_a_metric_text(requirements_contract),
            dataset_text=_gate_a_dataset_text(requirements_contract),
            obligation_text=_gate_a_obligation_text(requirements_contract),
            risk_text=_gate_a_risk_text(requirements_contract),
        )
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
        recommendation = (
            _gate_b_recommendation(design_contract, selection)
            if selection is not None
            else "Not yet selected."
        )
        construction_boundary = _gate_b_construction_boundary(envelope)
        sections = [
            _owner_decision_section(
                "GATE-B-EXECUTIVE",
                "Executive decision",
                [
                    "Recommendation: " + recommendation,
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
                    "Construction boundary: " + construction_boundary,
                ],
                [
                    requirements_revision,
                    design_revision,
                    authorization_id,
                    *([selection.architecture_id] if selection is not None else []),
                ],
            )
        ]
        technical_groups = gate_b_technical_groups(inventory)
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
        locator_specs = GATE_B_LOCATOR_SPECS
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


def _confirmed_foundation_answer(
    prd_text: str, response: NormalizedOwnerResponse
) -> list[str] | None:
    """Bind a historical card answer to its still-confirmed canonical values."""
    try:
        table = contract_table_after_heading(
            prd_text, INTAKE_FOUNDATION_HEADING, INTAKE_FOUNDATION_HEADERS
        )
    except ValueError:
        return None
    recorded: list[str] = []
    for basis_id in response.basis_ids:
        rows = [row for row in table.rows if row[0] == basis_id]
        if len(rows) != 1:
            return None
        _identifier, field, value, basis, status, provenance = rows[0]
        metadata = OWNER_INTAKE_DECISION_METADATA.get(field)
        if (
            metadata is None
            or dict(INTAKE_FOUNDATION_FIELDS).get(basis_id) != field
            or basis != "OWNER_FACT"
            or status != "CONFIRMED"
            or provenance != response.provenance
            or not explicit_value(value, allow_none=False)
        ):
            return None
        if field == "OWNER_WORK_CONTEXT":
            if value != OWNER_WORK_CONTEXT_SELECTIONS.get(response.selection):
                return None
            value = {
                "NEW_APPLICATION": "a new application.",
                "EXISTING_APPLICATION_CHANGE": "a change to an existing application.",
                "REPAIR_OR_MIGRATION": "a repair, replacement, or migration.",
            }.get(value, value)
            if response.selection_detail:
                value += f" ({response.selection_detail})"
        recorded.append(f"{metadata[1]}: {value}")
    return recorded or None


def _recorded_intake_answer(
    prd_text: str, response: NormalizedOwnerResponse, question: IntakeQuestion | None
) -> list[str] | None:
    if question is None:
        return _confirmed_foundation_answer(prd_text, response)
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
    return [f"{question.prompt}: {value}"] if value else None


def derive_owner_answer_confirmation(
    prd_text: str,
    intake_contract: IntakeFoundationContract,
) -> dict[str, Any]:
    """SAFETY: project only the latest canonical normalized intake response."""

    if not intake_contract.normalized_responses:
        return answer_confirmation()
    if intake_contract.status == "BLOCKED":
        return answer_confirmation(status="BLOCKED")
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
        values = _recorded_intake_answer(prd_text, response, question)
        if values is None:
            return answer_confirmation(status="BLOCKED")
        recorded.extend(values)
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


__all__ = (
    "derive_owner_answer_confirmation",
    "derive_owner_decision_brief",
)
