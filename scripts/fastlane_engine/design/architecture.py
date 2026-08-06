"""Whole-system architecture comparison and AWS evidence contracts.

Canonical inputs are caller-observed project records. Outputs are immutable
Design projections or ordered validation issues. This module performs no I/O,
routing, mutation, approval, authorization, or owner-facing rendering.
"""

from __future__ import annotations


import hashlib
import re
from datetime import datetime

from ..core.contracts import (
    ContractTable,
    contract_table_after_heading,
    table_after_heading,
)
from ..core.ids import (
    STABLE_CONTRACT_ID,
    canonical_id_list,
    explicit_value,
    none_with_reason,
)
from .models import (
    ARCHITECTURE_DESIGN_ID,
    ARCHITECTURE_ID,
    ARCHITECTURE_TEST_ID,
    ArchitectureCandidate,
    ArchitectureContract,
    ArchitectureDriver,
    ArchitectureSelection,
    ArchitectureTrace,
    MaterialAwsEvidence,
)


ARCHITECTURE_DRIVER_HEADING = "### Architecture drivers"


ARCHITECTURE_DRIVER_HEADERS = (
    "Driver ID",
    "Requirement basis",
    "Class",
    "Decision implication",
    "Validation",
)


ARCHITECTURE_CANDIDATE_HEADING = "### Whole-system candidates"


ARCHITECTURE_CANDIDATE_HEADERS = (
    "Candidate ID",
    "Architecture summary",
    "Requirement coverage",
    "AWS evidence",
    "Eligibility",
    "Failed constraints",
    "Tradeoffs",
)


ARCHITECTURE_SELECTION_HEADERS_V2 = (
    "Architecture ID",
    "Selected candidate",
    "Requirement and driver basis",
    "Rationale",
    "Rejected alternatives",
    "Risks",
    "Mitigations",
    "Cost effect",
    "Breakpoints",
    "Revisit triggers",
    "Validation",
)


ARCHITECTURE_SELECTION_HEADING = "### Selected architecture"


ARCHITECTURE_SELECTION_HEADERS = (
    "Architecture ID",
    "Selected candidate",
    "Requirement and driver basis",
    "Rationale",
    "Rejected alternatives",
    "Risks",
    "Mitigations",
    "Security impact",
    "Reliability impact",
    "Operational burden",
    "Cost effect",
    "Breakpoints",
    "Migration path",
    "Revisit triggers",
    "Validation",
)


ARCHITECTURE_TRACEABILITY_HEADING = "### Architecture traceability"


ARCHITECTURE_TRACEABILITY_HEADERS_V4 = (
    "Requirement ID",
    "ARCH / COMP / API / EVENT / CLI / FILE / DATA / CTRL / BOUNDARY / STATE IDs",
    "Property/test IDs",
    "Evidence IDs",
)


ARCHITECTURE_TRACEABILITY_HEADERS = (
    "Requirement ID",
    "ARCH / API / EVENT / CLI / FILE / BOUNDARY / STATE IDs",
    "Property/test IDs",
    "Evidence IDs",
)


MATERIAL_AWS_EVIDENCE_HEADING = "### Material AWS evidence"


MATERIAL_AWS_EVIDENCE_HEADERS_V1 = (
    "Evidence ID",
    "Design IDs",
    "Material claim",
    "AWS Core capability",
    "Official reference",
    "Observed date",
)


MATERIAL_AWS_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Discovery ID",
    "Design IDs",
    "Material claim",
    "AWS Core capability",
    "Official reference",
    "Observed date",
)


ARCHITECTURE_DRIVER_ID = re.compile(r"DRV-\d{4,}")


ARCHITECTURE_CANDIDATE_ID = re.compile(r"CAND-\d{4,}")


AWS_MATERIAL_EVIDENCE_ID = re.compile(r"AWS-EV-\d{4,}")


AWS_DISCOVERY_ID = re.compile(r"AWS-DISC-\d{4,}")


ARCHITECTURE_DRIVER_CLASSES = {"HARD_CONSTRAINT", "PREFERENCE", "REVISIT_TRIGGER"}


ARCHITECTURE_ELIGIBILITY = {"ELIGIBLE", "INELIGIBLE"}


AWS_DOCUMENTATION_CAPABILITIES = {"retrieve_skill", "search_documentation"}


MANAGED_SERVERLESS_MARKER = "MANAGED_SERVERLESS_BASELINE:"


def _architecture_tables(
    text: str,
    *,
    required: bool,
    grandfather_approved_v1: bool,
) -> tuple[
    dict[str, ContractTable | None],
    list[str],
    int,
    int,
    ArchitectureContract | None,
]:
    """COMPATIBILITY: Parse current and grandfathered tables in canonical order."""

    specifications = (
        ("drivers", ARCHITECTURE_DRIVER_HEADING, ARCHITECTURE_DRIVER_HEADERS),
        ("candidates", ARCHITECTURE_CANDIDATE_HEADING, ARCHITECTURE_CANDIDATE_HEADERS),
        ("selection", ARCHITECTURE_SELECTION_HEADING, ARCHITECTURE_SELECTION_HEADERS),
        (
            "traceability",
            ARCHITECTURE_TRACEABILITY_HEADING,
            ARCHITECTURE_TRACEABILITY_HEADERS,
        ),
        ("evidence", MATERIAL_AWS_EVIDENCE_HEADING, MATERIAL_AWS_EVIDENCE_HEADERS),
    )
    tables: dict[str, ContractTable | None] = {}
    issues: list[str] = []
    selection_schema_version = 3
    evidence_schema_version = 2
    for key, heading, headers in specifications:
        try:
            tables[key] = contract_table_after_heading(text, heading, headers)
        except ValueError as exc:
            current_message = str(exc)
            if key == "selection" and grandfather_approved_v1:
                try:
                    tables[key] = contract_table_after_heading(
                        text, heading, ARCHITECTURE_SELECTION_HEADERS_V2
                    )
                    selection_schema_version = 2
                    continue
                except ValueError as legacy_exc:
                    current_message = str(legacy_exc)
            if key == "evidence" and grandfather_approved_v1:
                try:
                    tables[key] = contract_table_after_heading(
                        text, heading, MATERIAL_AWS_EVIDENCE_HEADERS_V1
                    )
                    evidence_schema_version = 1
                    continue
                except ValueError as legacy_exc:
                    current_message = str(legacy_exc)
            tables[key] = None
            if key == "traceability" and grandfather_approved_v1:
                try:
                    tables[key] = contract_table_after_heading(
                        text, heading, ARCHITECTURE_TRACEABILITY_HEADERS_V4
                    )
                    continue
                except ValueError as legacy_exc:
                    current_message = str(legacy_exc)
            issues.append(f"{heading}: {current_message}")

    all_missing = all(tables[key] is None for key, _, _ in specifications)
    gate_b_state = ""
    try:
        gate_b_state = table_after_heading(text, "## Document status").get(
            "Gate B derived status", ""
        )
    except ValueError:
        pass
    grandfathered = all_missing and (
        grandfather_approved_v1 or gate_b_state == "APPROVED_FOR_CONSTRUCTION"
    )
    if all_missing:
        if required and not grandfathered:
            issues.extend(f"Missing {heading}" for _, heading, _ in specifications)
        contract = ArchitectureContract(
            schema_version=1,
            status=(
                "READY"
                if grandfathered and not issues
                else "UNINITIALIZED"
                if not required
                else "BLOCKED"
            ),
            grandfathered_v1=grandfathered,
        )
        return (
            tables,
            issues,
            selection_schema_version,
            evidence_schema_version,
            contract,
        )
    for key, heading, _ in specifications:
        if tables[key] is None:
            issues.append(f"Missing {heading}")
    return tables, issues, selection_schema_version, evidence_schema_version, None


def _derive_architecture_contract(
    text: str,
    design_revision: str | None,
    technology_ids: set[str],
    requirement_ids: set[str],
    *,
    required: bool,
    architecture_disposition: str | None = None,
    grandfather_approved_v1: bool = False,
) -> tuple[ArchitectureContract, list[str]]:
    """SAFETY: Validate the whole-system choice and every bound design record."""

    specifications = (
        ("drivers", ARCHITECTURE_DRIVER_HEADING, ARCHITECTURE_DRIVER_HEADERS),
        ("candidates", ARCHITECTURE_CANDIDATE_HEADING, ARCHITECTURE_CANDIDATE_HEADERS),
        ("selection", ARCHITECTURE_SELECTION_HEADING, ARCHITECTURE_SELECTION_HEADERS),
        (
            "traceability",
            ARCHITECTURE_TRACEABILITY_HEADING,
            ARCHITECTURE_TRACEABILITY_HEADERS,
        ),
        ("evidence", MATERIAL_AWS_EVIDENCE_HEADING, MATERIAL_AWS_EVIDENCE_HEADERS),
    )
    (
        tables,
        issues,
        selection_schema_version,
        evidence_schema_version,
        early_contract,
    ) = _architecture_tables(
        text,
        required=required,
        grandfather_approved_v1=grandfather_approved_v1,
    )
    if early_contract is not None:
        return early_contract, issues

    drivers: list[ArchitectureDriver] = []
    candidates: list[ArchitectureCandidate] = []
    selection: ArchitectureSelection | None = None
    traces: list[ArchitectureTrace] = []
    evidence: list[MaterialAwsEvidence] = []
    requirements = requirement_ids
    expected_requirement_order = sorted(requirements)

    driver_table = tables["drivers"]
    seen_driver_ids: set[str] = set()
    hard_constraint_ids: set[str] = set()
    if driver_table is not None:
        if not driver_table.rows:
            issues.append("Architecture drivers has no stored rows")
        for row in driver_table.rows:
            driver = ArchitectureDriver(*row)
            drivers.append(driver)
            if ARCHITECTURE_DRIVER_ID.fullmatch(driver.driver_id) is None:
                issues.append(f"Invalid architecture driver ID {driver.driver_id!r}")
            elif driver.driver_id in seen_driver_ids:
                issues.append(f"Duplicate architecture driver ID {driver.driver_id}")
            seen_driver_ids.add(driver.driver_id)
            if driver.driver_class not in ARCHITECTURE_DRIVER_CLASSES:
                issues.append(
                    f"{driver.driver_id}: invalid driver class {driver.driver_class!r}"
                )
            elif driver.driver_class == "HARD_CONSTRAINT":
                hard_constraint_ids.add(driver.driver_id)
            try:
                basis = canonical_id_list(
                    driver.requirement_basis,
                    STABLE_CONTRACT_ID,
                    f"{driver.driver_id} requirement basis",
                )
                unknown = sorted(set(basis) - requirements)
                if unknown:
                    issues.append(
                        f"{driver.driver_id}: requirement basis is not Gate A requirement IDs: "
                        + ", ".join(unknown)
                    )
            except ValueError as exc:
                issues.append(str(exc))
            for label, value in (
                ("Decision implication", driver.decision_implication),
                ("Validation", driver.validation),
            ):
                if not explicit_value(value, allow_none=False):
                    issues.append(f"{driver.driver_id}: {label} must be concrete")

    candidate_table = tables["candidates"]
    seen_candidate_ids: set[str] = set()
    if candidate_table is not None:
        if not candidate_table.rows:
            issues.append("Whole-system candidates has no stored rows")
        for row in candidate_table.rows:
            candidate = ArchitectureCandidate(*row)
            candidates.append(candidate)
            if ARCHITECTURE_CANDIDATE_ID.fullmatch(candidate.candidate_id) is None:
                issues.append(
                    f"Invalid architecture candidate ID {candidate.candidate_id!r}"
                )
            elif candidate.candidate_id in seen_candidate_ids:
                issues.append(
                    f"Duplicate architecture candidate ID {candidate.candidate_id}"
                )
            seen_candidate_ids.add(candidate.candidate_id)
            if not explicit_value(candidate.architecture_summary, allow_none=False):
                issues.append(
                    f"{candidate.candidate_id}: architecture summary must be concrete"
                )
            try:
                coverage = canonical_id_list(
                    candidate.requirement_coverage,
                    STABLE_CONTRACT_ID,
                    f"{candidate.candidate_id} requirement coverage",
                )
                if coverage != expected_requirement_order:
                    issues.append(
                        f"{candidate.candidate_id}: requirement coverage must exactly enumerate current requirement IDs: "
                        + ", ".join(expected_requirement_order)
                    )
            except ValueError as exc:
                issues.append(str(exc))
            if candidate.eligibility not in ARCHITECTURE_ELIGIBILITY:
                issues.append(
                    f"{candidate.candidate_id}: invalid eligibility {candidate.eligibility!r}"
                )
            if candidate.eligibility == "ELIGIBLE":
                if candidate.failed_constraints != "NONE":
                    issues.append(
                        f"{candidate.candidate_id}: an eligible candidate must have Failed constraints NONE"
                    )
            elif candidate.eligibility == "INELIGIBLE":
                try:
                    failed = canonical_id_list(
                        candidate.failed_constraints,
                        ARCHITECTURE_DRIVER_ID,
                        f"{candidate.candidate_id} failed constraints",
                    )
                    non_hard = sorted(set(failed) - hard_constraint_ids)
                    if non_hard:
                        issues.append(
                            f"{candidate.candidate_id}: failed constraints must reference HARD_CONSTRAINT drivers: "
                            + ", ".join(non_hard)
                        )
                except ValueError as exc:
                    issues.append(str(exc))
            if not explicit_value(candidate.tradeoffs, allow_none=False):
                issues.append(f"{candidate.candidate_id}: tradeoffs must be concrete")
    if (
        required
        and architecture_disposition == "SELECT"
        and not grandfather_approved_v1
        and len(seen_candidate_ids) < 2
    ):
        issues.append(
            "SELECT requires at least two complete non-straw whole-system candidates"
        )

    selection_table = tables["selection"]
    if selection_table is not None:
        if len(selection_table.rows) != 1:
            issues.append("Selected architecture must contain exactly one row")
        elif selection_table.rows:
            if selection_schema_version == 3:
                selection = ArchitectureSelection(*selection_table.rows[0])
            else:
                legacy = selection_table.rows[0]
                selection = ArchitectureSelection(
                    architecture_id=legacy[0],
                    selected_candidate=legacy[1],
                    requirement_and_driver_basis=legacy[2],
                    rationale=legacy[3],
                    rejected_alternatives=legacy[4],
                    risks=legacy[5],
                    mitigations=legacy[6],
                    security_impact="",
                    reliability_impact="",
                    operational_burden="",
                    cost_effect=legacy[7],
                    breakpoints=legacy[8],
                    migration_path="",
                    revisit_triggers=legacy[9],
                    validation=legacy[10],
                )
            if ARCHITECTURE_ID.fullmatch(selection.architecture_id) is None:
                issues.append(
                    f"Invalid selected architecture ID {selection.architecture_id!r}"
                )
            if selection.selected_candidate not in seen_candidate_ids:
                issues.append(
                    "Selected architecture must reference a current candidate"
                )
            selected = next(
                (
                    item
                    for item in candidates
                    if item.candidate_id == selection.selected_candidate
                ),
                None,
            )
            if selected is not None and selected.eligibility != "ELIGIBLE":
                issues.append("A hard-constraint-failing candidate cannot be selected")
            expected_basis = [
                *expected_requirement_order,
                *(item.driver_id for item in drivers),
            ]
            try:
                basis = canonical_id_list(
                    selection.requirement_and_driver_basis,
                    STABLE_CONTRACT_ID,
                    f"{selection.architecture_id} requirement and driver basis",
                )
                if basis != expected_basis:
                    issues.append(
                        f"{selection.architecture_id}: basis must exactly enumerate current requirements and drivers: "
                        + ", ".join(expected_basis)
                    )
            except ValueError as exc:
                issues.append(str(exc))
            nonselected = [
                item.candidate_id
                for item in candidates
                if item.candidate_id != selection.selected_candidate
            ]
            eligible = [item for item in candidates if item.eligibility == "ELIGIBLE"]
            if selection.rejected_alternatives == "NO_VIABLE_ALTERNATIVE":
                if len(eligible) != 1 or any(
                    item.eligibility != "INELIGIBLE"
                    for item in candidates
                    if item.candidate_id != selection.selected_candidate
                ):
                    issues.append(
                        "NO_VIABLE_ALTERNATIVE is valid only when exactly one candidate is eligible"
                    )
            else:
                try:
                    rejected = canonical_id_list(
                        selection.rejected_alternatives,
                        ARCHITECTURE_CANDIDATE_ID,
                        f"{selection.architecture_id} rejected alternatives",
                    )
                    if rejected != nonselected:
                        issues.append(
                            f"{selection.architecture_id}: rejected alternatives must enumerate every nonselected candidate in table order"
                        )
                except ValueError as exc:
                    issues.append(str(exc))
            dossier_fields = (
                ("Rationale", selection.rationale),
                ("Risks", selection.risks),
                ("Mitigations", selection.mitigations),
            )
            if selection_schema_version == 3:
                dossier_fields += (
                    ("Security impact", selection.security_impact),
                    ("Reliability impact", selection.reliability_impact),
                    ("Operational burden", selection.operational_burden),
                )
            dossier_fields += (
                ("Cost effect", selection.cost_effect),
                ("Breakpoints", selection.breakpoints),
            )
            if selection_schema_version == 3:
                dossier_fields += (("Migration path", selection.migration_path),)
            dossier_fields += (
                ("Revisit triggers", selection.revisit_triggers),
                ("Validation", selection.validation),
            )
            for label, value in dossier_fields:
                if not explicit_value(value, allow_none=False):
                    issues.append(
                        f"{selection.architecture_id}: {label} must be concrete"
                    )

    trace_table = tables["traceability"]
    seen_trace_requirements: set[str] = set()
    if trace_table is not None:
        for row in trace_table.rows:
            trace = ArchitectureTrace(*row)
            traces.append(trace)
            if trace.requirement_id in seen_trace_requirements:
                issues.append(
                    f"Duplicate architecture traceability requirement {trace.requirement_id}"
                )
            seen_trace_requirements.add(trace.requirement_id)
            if trace.requirement_id not in requirements:
                issues.append(
                    f"Architecture traceability references non-requirement ID {trace.requirement_id}"
                )
            try:
                design_ids = canonical_id_list(
                    trace.design_ids,
                    ARCHITECTURE_DESIGN_ID,
                    f"{trace.requirement_id} architecture traceability design IDs",
                )
                if (
                    selection is not None
                    and selection.architecture_id not in design_ids
                ):
                    issues.append(
                        f"{trace.requirement_id}: traceability must include {selection.architecture_id}"
                    )
                if not any(
                    identifier != (selection.architecture_id if selection else "")
                    for identifier in design_ids
                ):
                    issues.append(
                        f"{trace.requirement_id}: traceability must include at least one additional design ID"
                    )
            except ValueError as exc:
                issues.append(str(exc))
            if not none_with_reason(trace.property_test_ids):
                try:
                    canonical_id_list(
                        trace.property_test_ids,
                        ARCHITECTURE_TEST_ID,
                        f"{trace.requirement_id} property/test IDs",
                    )
                except ValueError as exc:
                    issues.append(str(exc))
        missing_traces = sorted(requirements - seen_trace_requirements)
        extra_traces = sorted(seen_trace_requirements - requirements)
        if missing_traces:
            issues.append(
                "Architecture traceability is missing requirement IDs: "
                + ", ".join(missing_traces)
            )
        if extra_traces:
            issues.append(
                "Architecture traceability has unknown requirement IDs: "
                + ", ".join(extra_traces)
            )

    evidence_table = tables["evidence"]
    seen_evidence_ids: set[str] = set()
    seen_capabilities: set[str] = set()
    evidence_design_ids: dict[str, set[str]] = {}
    declared_design_ids = {
        *(item.driver_id for item in drivers),
        *(item.candidate_id for item in candidates),
        *(technology_ids),
    }
    if selection is not None:
        declared_design_ids.add(selection.architecture_id)
    if evidence_table is not None:
        if not evidence_table.rows:
            issues.append("Material AWS evidence has no stored rows")
        for row in evidence_table.rows:
            item = (
                MaterialAwsEvidence(*row)
                if evidence_schema_version == 2
                else MaterialAwsEvidence(row[0], "", *row[1:])
            )
            evidence.append(item)
            if (
                evidence_schema_version == 2
                and AWS_DISCOVERY_ID.fullmatch(item.discovery_id) is None
            ):
                issues.append(
                    f"{item.evidence_id}: invalid Discovery ID {item.discovery_id!r}"
                )
            if AWS_MATERIAL_EVIDENCE_ID.fullmatch(item.evidence_id) is None:
                issues.append(f"Invalid material AWS evidence ID {item.evidence_id!r}")
            elif item.evidence_id in seen_evidence_ids:
                issues.append(f"Duplicate material AWS evidence ID {item.evidence_id}")
            seen_evidence_ids.add(item.evidence_id)
            try:
                bound_ids = canonical_id_list(
                    item.design_ids,
                    STABLE_CONTRACT_ID,
                    f"{item.evidence_id} design IDs",
                )
                evidence_design_ids[item.evidence_id] = set(bound_ids)
                unknown = sorted(set(bound_ids) - declared_design_ids)
                if unknown:
                    issues.append(
                        f"{item.evidence_id}: unknown design IDs: " + ", ".join(unknown)
                    )
            except ValueError as exc:
                issues.append(str(exc))
            if not explicit_value(item.material_claim, allow_none=False):
                issues.append(f"{item.evidence_id}: material claim must be concrete")
            if item.capability not in AWS_DOCUMENTATION_CAPABILITIES:
                issues.append(
                    f"{item.evidence_id}: invalid AWS Core capability {item.capability!r}"
                )
            else:
                seen_capabilities.add(item.capability)
            if (
                re.fullmatch(
                    r"https://(?:docs\.)?aws\.amazon\.com/\S+", item.official_reference
                )
                is None
            ):
                issues.append(
                    f"{item.evidence_id}: Official reference must be an AWS HTTPS URL"
                )
            try:
                datetime.strptime(item.observed_date, "%Y-%m-%d")
            except ValueError:
                issues.append(f"{item.evidence_id}: Observed date must use YYYY-MM-DD")
        missing_capabilities = sorted(
            AWS_DOCUMENTATION_CAPABILITIES - seen_capabilities
        )
        if missing_capabilities:
            issues.append(
                "Material AWS evidence is missing AWS Core capabilities: "
                + ", ".join(missing_capabilities)
            )

    for candidate in candidates:
        try:
            evidence_ids = canonical_id_list(
                candidate.aws_evidence,
                AWS_MATERIAL_EVIDENCE_ID,
                f"{candidate.candidate_id} AWS evidence",
            )
            unknown = sorted(set(evidence_ids) - seen_evidence_ids)
            if unknown:
                issues.append(
                    f"{candidate.candidate_id}: unknown AWS evidence IDs: "
                    + ", ".join(unknown)
                )
            unbound = sorted(
                evidence_id
                for evidence_id in evidence_ids
                if candidate.candidate_id
                not in evidence_design_ids.get(evidence_id, set())
            )
            if unbound:
                issues.append(
                    f"{candidate.candidate_id}: AWS evidence rows are not bound to this candidate: "
                    + ", ".join(unbound)
                )
        except ValueError as exc:
            issues.append(str(exc))
    if selection is not None and not any(
        selection.architecture_id in bound_ids
        for bound_ids in evidence_design_ids.values()
    ):
        issues.append("Selected architecture has no bound material AWS evidence")
    for trace in traces:
        if none_with_reason(trace.evidence_ids):
            continue
        try:
            evidence_ids = canonical_id_list(
                trace.evidence_ids,
                AWS_MATERIAL_EVIDENCE_ID,
                f"{trace.requirement_id} evidence IDs",
            )
            unknown = sorted(set(evidence_ids) - seen_evidence_ids)
            if unknown:
                issues.append(
                    f"{trace.requirement_id}: unknown AWS evidence IDs: "
                    + ", ".join(unknown)
                )
        except ValueError as exc:
            issues.append(str(exc))

    try:
        project_mode = table_after_heading(text, "## Document status").get(
            "Project mode", ""
        )
    except ValueError:
        project_mode = ""
    if project_mode == "greenfield" and not any(
        item.architecture_summary.startswith(MANAGED_SERVERLESS_MARKER)
        for item in candidates
    ):
        issues.append(
            "Greenfield architecture candidates must evaluate the managed-serverless baseline"
        )

    canonical_bytes: bytes | None = None
    canonical_sha256: str | None = None
    if all(tables[key] is not None for key, _, _ in specifications):
        canonical_bytes = b"".join(
            tables[key].canonical_bytes  # type: ignore[union-attr]
            for key, _, _ in specifications
        )
        canonical_sha256 = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
    return (
        ArchitectureContract(
            schema_version=(
                selection_schema_version
                if grandfather_approved_v1 and selection_schema_version < 3
                else (4 if evidence_schema_version == 2 else selection_schema_version)
            ),
            status="READY" if not issues else "BLOCKED",
            drivers=tuple(drivers),
            candidates=tuple(candidates),
            selection=selection,
            traceability=tuple(traces),
            aws_evidence=tuple(evidence),
            canonical_sha256=canonical_sha256,
            canonical_bytes=canonical_bytes,
        ),
        issues,
    )
