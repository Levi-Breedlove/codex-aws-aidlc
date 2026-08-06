"""Pure Delivery task graph and requirement-coverage validation.

Canonical inputs are caller-supplied TASKS, VERIFY, and normalized Define or
Design projections. Results are immutable records or deterministic failures.
This module performs no I/O, mutation, routing, approval, or authorization.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..core.contracts import (
    parse_task_external_state,
    parse_task_write_set,
    split_table_row,
    table_after_heading,
    without_fenced_code,
)
from ..core.ids import (
    STABLE_CONTRACT_ID,
    canonical_id_list,
    clean_cell,
    explicit_timestamp,
    explicit_value,
    unresolved,
)
from .evidence import (
    EVIDENCE_PATTERN,
    PROPERTY_TEST_EVIDENCE_HEADING,
    parse_property_test_evidence,
    parse_task_completion_evidence,
    parse_verification_matrix,
    validate_done_evidence,
    validate_done_property_evidence,
    validate_task_property_execution_projection,
)
from .models import (
    DeliveryValidationPolicy,
    InspectedTask,
    PropertyTestEvidenceRow,
    TaskCompletionEvidenceRow,
    TaskRequirementCoverage,
    TaskRequirementCoverageResult,
)

REQ_ID = re.compile(r"REQ-\d{4,}")
DES_ID = re.compile(r"DES-\d{4,}")
AUTH_ID = re.compile(r"AUTH-\d{4,}")
CHECKPOINT_ID = re.compile(r"CP-\d{4,}")
ACCEPTANCE_ID = re.compile(r"AC-[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
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


def inspect_task_blocks(text: str) -> list[InspectedTask]:
    """CANONICALIZATION: parse ordered task blocks and exact metadata."""

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
    property_execution_by_id: Mapping[str, Any] | None = None,
    technology_decisions_by_id: Mapping[str, Any] | None = None,
    policy: DeliveryValidationPolicy | None = None,
) -> tuple[list[InspectedTask], dict[str, InspectedTask], list[str]]:
    """SAFETY: validate the complete task graph before exposing READY work."""

    if policy is None:
        raise ValueError("Delivery validation policy is required")
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
        for property_id in policy.property_id.findall(
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
            property_evidence_rows = parse_property_test_evidence(verify_text, policy)
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
                    policy,
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
        for property_id in policy.property_id.findall(
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
            policy.property_id.findall(
                clean_cell(task.metadata.get("Requirements", ""))
            )
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
                policy,
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
    property_execution_by_id: Mapping[str, Any],
    policy: DeliveryValidationPolicy,
) -> list[str]:
    """Return approved properties omitted from a current task plan."""

    if plan_state != "CURRENT":
        return []
    covered_property_ids = {
        property_id
        for task in tasks
        if task.status in {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE"}
        for property_id in policy.property_id.findall(
            clean_cell(task.metadata.get("Requirements", ""))
        )
    }
    return sorted(set(property_execution_by_id) - covered_property_ids)


def task_requirement_rules(
    prd_text: str,
    requirements_contract: Any,
    schema_13_requirement_rows: Callable[
        [str], tuple[list[tuple[str, ...]], dict[str, str], set[str]]
    ],
) -> dict[str, tuple[str, str]]:
    """SAFETY: bind each current requirement to its exact acceptance rule."""

    if requirements_contract.grandfathered_approved_gate_a:
        return {}
    rows, acceptance_by_requirement, _legacy_ids = schema_13_requirement_rows(prd_text)
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
    """SAFETY: resolve no-task dispositions only from current exact evidence."""

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
            basis_ids = canonical_id_list(
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
    """SAFETY: derive exactly one coverage disposition per approved requirement."""

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


__all__ = (
    "TASK_AWS_MODES",
    "TASK_METADATA_KEYS",
    "TASK_STATUSES",
    "declared_task_waivers",
    "derive_task_requirement_coverage",
    "inspect_task_blocks",
    "inspect_task_sections",
    "missing_current_property_task_coverage",
    "task_requirement_evidence_dispositions",
    "task_requirement_rules",
    "task_waiver_rows",
    "validate_task_records",
)
