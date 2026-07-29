from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path, PurePosixPath


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = REPOSITORY_ROOT
TEMPLATE_SOURCE_MODE = "{{SETUP_STATUS}}" in (
    REPOSITORY_ROOT / "bootstrap.yaml"
).read_text(encoding="utf-8")
source_template_only = unittest.skipUnless(
    TEMPLATE_SOURCE_MODE,
    "maintainer source-integrity test is not applicable after project configuration",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


doctor = load_module(
    "bootstrap_doctor_under_test",
    PROJECT_ROOT / "scripts" / "bootstrap_doctor.py",
)
bootstrap_runtime = load_module(
    "bootstrap_runtime_for_doctor_tests",
    PROJECT_ROOT / "bootstrap.py",
)


def codes(report: dict[str, object]) -> set[str]:
    return {item["code"] for item in report["diagnostics"]}  # type: ignore[index]


def set_table_value(
    text: str,
    heading: str,
    next_heading: str,
    field: str,
    value: str,
) -> str:
    start = text.index(heading)
    end = text.index(next_heading, start + len(heading))
    section = text[start:end]
    lines = section.splitlines(keepends=True)
    prefix = f"| {field} |"
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {field!r} row in {heading!r}")
    suffix = "\n" if lines[matches[0]].endswith("\n") else ""
    lines[matches[0]] = f"| {field} | {value} |{suffix}"
    return text[:start] + "".join(lines) + text[end:]


def set_receipt(text: str, gate: str, receipt: str) -> str:
    start_marker = f"<!-- bootstrap:{gate}-receipt:start -->"
    end_marker = f"<!-- bootstrap:{gate}-receipt:end -->"
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    body = f"\n```text\n{receipt}\n```\n"
    return text[:start] + body + text[end:]


def intake_provenance(
    owner_response_id: str,
    card_id: str,
    revision: int,
    card_digest: str,
    question_id: str,
    selection: str,
) -> str:
    return (
        f"OWNER_RESPONSE: {owner_response_id}; CARD: {card_id}; "
        f"REVISION: {revision}; SHA256: {card_digest}; "
        f"QUESTION: {question_id}; ANSWER: {selection}"
    )


def replace_contract_table(
    text: str,
    heading: str,
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
) -> str:
    heading_start = text.index(heading)
    table_start = text.index("|", heading_start)
    table_end = text.index("\n\n", table_start)
    rendered = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _header in headers) + "|",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]
    return text[:table_start] + "\n".join(rendered) + text[table_end:]


def replace_contract_table_with_sentinel(
    text: str,
    heading: str,
    reason: str,
) -> str:
    heading_start = text.index(heading)
    table_start = text.index("|", heading_start)
    table_end = text.index("\n\n", table_start)
    sentinel = f"NOT_APPLICABLE - {reason}"
    return text[:table_start] + sentinel + text[table_end:]


def exact_legacy_requirements_projection(text: str) -> str:
    text = re.sub(
        r"(?m)^\| Project contract schema \| `1\.3` \|\r?\n",
        "",
        text,
        count=1,
    )
    modern_pattern = re.compile(
        r"(?m)^\| ID \| Requirement \| EARS form \| Acceptance ID \| "
        r"Acceptance criteria \| Acceptance form \|\r?\n"
        r"^\|[-:| ]+\|\r?\n(?:^\|.*\|\r?\n?)+"
    )

    def legacy_table(match: re.Match[str]) -> str:
        table = doctor.markdown_tables(match.group(0))[0]
        rows = [
            "| ID | Requirement | Acceptance criteria |",
            "|---|---|---|",
            *(f"| {row[0]} | {row[1]} | {row[4]} |" for row in table[2:]),
        ]
        return "\n".join(rows) + "\n"

    text = modern_pattern.sub(legacy_table, text)
    for heading in (
        doctor.ACTOR_HEADING,
        doctor.JOURNEY_HEADING,
        doctor.RICH_USE_CASE_APPLICABILITY_HEADING,
        doctor.RICH_USE_CASE_HEADING,
        doctor.BUSINESS_RULE_HEADING,
        doctor.REQUIREMENT_COVERAGE_HEADING,
    ):
        heading_start = text.index(heading)
        table_start = text.index("|", heading_start)
        table_end = text.index("\n\n", table_start)
        text = text[:table_start] + text[table_end + 2:]
    return text


def exact_legacy_schema_four_projection(text: str) -> str:
    text = re.sub(
        r"(?m)^\| Project design contract schema \| `5` \|\r?\n",
        "",
        text,
        count=1,
    )
    legacy_interface_table = "\n".join([
        "| Contract ID | Producer | Consumer | Schema or protocol | Authentication | Versioning | Idempotency |",
        "|---|---|---|---|---|---|---|",
        "| API-001 | Local client | Trusted application service | Versioned JSON request and response | Approved identity token | Compatible additions only | One idempotent read per request |",
    ])
    text = put_contract_table(
        text,
        doctor.INTERFACE_HEADING,
        legacy_interface_table,
        "## 17. Data model and lifecycle",
    )

    def remove_region(value: str, start: str, end: str) -> str:
        start_index = value.index(start)
        end_index = value.index(end, start_index)
        return value[:start_index] + value[end_index:]

    text = remove_region(text, doctor.LAYER_BOUNDARY_HEADING, doctor.INTERFACE_HEADING)
    text = remove_region(text, doctor.STATE_APPLICABILITY_HEADING, "```mermaid")
    text = remove_region(
        text,
        doctor.FIRST_WAVE_HEADING,
        "`docs/project/TASKS.md` will translate this design",
    )
    return text.replace(
        "DES-0001, FR-001, JOURNEY-001, WAVE-001",
        "DES-0001, FR-001",
        1,
    )



def confirm_intake_foundation(
    text: str,
    values: dict[str, str],
    owner_responses: dict[str, str],
) -> str:
    output: list[str] = []
    for line in text.splitlines(keepends=True):
        cells = doctor.split_markdown_table_row(line)
        line_ending = "\n" if line.endswith("\n") else ""
        if cells and len(cells) == 6 and cells[0] in values:
            cells[2] = values[cells[0]]
            cells[3] = "OWNER_FACT"
            cells[4] = "CONFIRMED"
            cells[5] = owner_responses[cells[0]]
            line = "| " + " | ".join(cells) + " |" + line_ending
        output.append(line)
    return "".join(output)


def complete_intake_foundation(
    text: str,
    *,
    work_context_choice: str = "A",
) -> str:
    initial, initial_issues = doctor.derive_intake_foundation_contract(
        text, "greenfield", grandfather_current_gate_a=False
    )
    if initial_issues or initial.pending_card is None:
        raise AssertionError(f"Initial intake card is invalid: {initial_issues}")
    first_digest = initial.pending_card.canonical_sha256
    context_values = {
        "A": ("NEW_APPLICATION", "NONE"),
        "B": ("EXISTING_APPLICATION_CHANGE", "Existing application"),
        "C": ("REPAIR_OR_MIGRATION", "Existing system migration"),
    }
    if work_context_choice not in context_values:
        raise AssertionError("work_context_choice must be A, B, or C")
    work_context, work_context_detail = context_values[work_context_choice]
    register_rows: list[tuple[str, ...]] = []
    provenance_by_intake: dict[str, str] = {}

    def resolve(
        owner_response_id: str,
        card_id: str,
        card_digest: str,
        reply_key: str,
        question_id: str,
        selection: str,
        detail: str,
        basis_ids: tuple[str, ...],
    ) -> None:
        nonlocal text
        provenance = intake_provenance(
            owner_response_id,
            card_id,
            1,
            card_digest,
            question_id,
            selection,
        )
        text = set_intake_card_resolution(
            text,
            question_id,
            selection,
            detail=detail,
            owner_response=provenance,
        )
        register_rows.append(
            (
                owner_response_id,
                card_id,
                "1",
                card_digest,
                reply_key,
                question_id,
                selection,
                detail,
                ", ".join(basis_ids),
            )
        )
        for basis_id in basis_ids:
            provenance_by_intake[basis_id] = provenance

    resolve(
        "OWNER-MSG-0001",
        "INTAKE-CARD-0001",
        first_digest,
        "1",
        "INTAKE-Q-0001",
        work_context_choice,
        work_context_detail,
        ("INTAKE-0001",),
    )
    resolve(
        "OWNER-MSG-0001",
        "INTAKE-CARD-0001",
        first_digest,
        "2",
        "INTAKE-Q-0002",
        "RESPONSE",
        "Development users need to see the approved project outcome.",
        ("INTAKE-0002", "INTAKE-0003"),
    )
    resolve(
        "OWNER-MSG-0001",
        "INTAKE-CARD-0001",
        first_digest,
        "3",
        "INTAKE-Q-0003",
        "RESPONSE",
        "The first release displays the approved outcome locally.",
        ("INTAKE-0004", "INTAKE-0005"),
    )

    text = replace_contract_table(
        text,
        doctor.INTAKE_CARD_HEADING,
        doctor.INTAKE_CARD_HEADERS,
        [
            (
                "INTAKE-CARD-0002",
                "1",
                "1",
                "INTAKE-Q-0004",
                "FACT",
                "INTAKE-0006",
                "How will you know the first release succeeds?",
                "NOT_APPLICABLE",
                "NOT_APPLICABLE",
                "NOT_APPLICABLE",
                "NONE",
                "RESPONSE",
                "Name one observable success measure.",
                "PENDING",
                "NONE",
                "NONE",
            ),
            (
                "INTAKE-CARD-0002",
                "1",
                "2",
                "INTAKE-Q-0005",
                "FACT",
                "INTAKE-0007",
                "What data and operating boundaries materially affect the first release?",
                "NOT_APPLICABLE",
                "NOT_APPLICABLE",
                "NOT_APPLICABLE",
                "NONE",
                "RESPONSE",
                "Describe sensitive data, Region, release audience, or other boundaries.",
                "PENDING",
                "NONE",
                "NONE",
            ),
        ],
    )
    second_table = doctor.contract_table_after_heading(
        text, doctor.INTAKE_CARD_HEADING, doctor.INTAKE_CARD_HEADERS
    )
    if second_table is None:
        raise AssertionError("Second intake card is missing")
    second_digest = "sha256:" + hashlib.sha256(second_table.canonical_bytes).hexdigest()
    resolve(
        "OWNER-MSG-0002",
        "INTAKE-CARD-0002",
        second_digest,
        "1",
        "INTAKE-Q-0004",
        "RESPONSE",
        "A rendered-output test confirms the approved outcome",
        ("INTAKE-0006",),
    )
    resolve(
        "OWNER-MSG-0002",
        "INTAKE-CARD-0002",
        second_digest,
        "2",
        "INTAKE-Q-0005",
        "RESPONSE",
        "Synthetic internal development data; us-west-2 only",
        ("INTAKE-0007",),
    )
    values = {
        "INTAKE-0001": work_context,
        "INTAKE-0002": "Development users",
        "INTAKE-0003": "Users need to see the approved project outcome",
        "INTAKE-0004": "Display the current approved project outcome",
        "INTAKE-0005": "Local development slice only",
        "INTAKE-0006": "A rendered-output test confirms the approved outcome",
        "INTAKE-0007": "Synthetic internal development data; us-west-2 only",
    }
    text = confirm_intake_foundation(text, values, provenance_by_intake)
    return replace_contract_table(
        text,
        doctor.INTAKE_RESPONSE_REGISTER_HEADING,
        doctor.INTAKE_RESPONSE_REGISTER_HEADERS,
        register_rows,
    )


def set_intake_card_resolution(
    text: str,
    question_id: str,
    selection: str,
    *,
    detail: str = "NONE",
    owner_response: str = "NONE",
) -> str:
    output: list[str] = []
    matched = 0
    for line in text.splitlines(keepends=True):
        cells = doctor.split_markdown_table_row(line)
        line_ending = "\n" if line.endswith("\n") else ""
        if cells and len(cells) == 16 and cells[3] == question_id:
            cells[13] = selection
            cells[14] = detail
            cells[15] = owner_response
            line = "| " + " | ".join(cells) + " |" + line_ending
            matched += 1
        output.append(line)
    if matched != 1:
        raise AssertionError(f"Expected one intake-card row for {question_id}")
    return "".join(output)


def complete_requirements_contract(text: str) -> str:
    text = set_table_value(
        text,
        "## Document status",
        "## 1. Workload profile",
        "Project contract schema",
        "`1.3`",
    )
    requirement_ids = sorted(doctor.authoritative_requirement_ids(text))
    requirement_list = ", ".join(requirement_ids)
    text = replace_contract_table(
        text,
        doctor.ACTOR_HEADING,
        doctor.ACTOR_HEADERS,
        [
            (
                "ACT-001",
                "Development user",
                "PRIMARY_USER",
                "See the approved project outcome",
                "May access only the local synthetic development outcome",
                "INTAKE-0002, INTAKE-0003, INTAKE-0004, INTAKE-0005, INTAKE-0007",
            )
        ],
    )
    text = replace_contract_table(
        text,
        doctor.JOURNEY_HEADING,
        doctor.JOURNEY_HEADERS,
        [
            (
                "JOURNEY-001",
                "ACT-001",
                "See the approved project outcome",
                "The development user requests the local result",
                "The current approved outcome is displayed",
                "Invalid input is rejected without changing approved state",
                requirement_list,
                "NONE",
            )
        ],
    )
    text = replace_contract_table(
        text,
        doctor.RICH_USE_CASE_APPLICABILITY_HEADING,
        doctor.RICH_USE_CASE_APPLICABILITY_HEADERS,
        [(
            "NOT_APPLICABLE",
            "NOT_APPLICABLE - low-risk single-actor synchronous fixture",
            "NONE",
        )],
    )
    text = replace_contract_table(
        text, doctor.RICH_USE_CASE_HEADING, doctor.RICH_USE_CASE_HEADERS, []
    )
    text = replace_contract_table(
        text, doctor.BUSINESS_RULE_HEADING, doctor.BUSINESS_RULE_HEADERS, []
    )
    return replace_contract_table(
        text,
        doctor.REQUIREMENT_COVERAGE_HEADING,
        doctor.REQUIREMENT_COVERAGE_HEADERS,
        [
            (
                requirement_id,
                "INTAKE-0002, INTAKE-0003, INTAKE-0004, INTAKE-0005, INTAKE-0006, INTAKE-0007",
                "ACT-001",
                "JOURNEY-001",
                f"AC-{requirement_id}",
                "INTAKE-0006",
            )
            for requirement_id in requirement_ids
        ],
    )


def approve_gate_a(text: str) -> str:
    text = complete_intake_foundation(text)
    replacements = {
        "| FR-001 | TODO | UBIQUITOUS | AC-FR-001 | TODO | MEASURABLE |": (
            "| FR-001 | The application SHALL display the current approved project outcome. "
            "| UBIQUITOUS | AC-FR-001 | A rendered-output test confirms the approved outcome is displayed. "
            "| MEASURABLE |"
        ),
        "| FR-002 | TODO | UNWANTED_BEHAVIOR | AC-FR-002 | TODO | GHERKIN |": (
            "| FR-002 | IF input violates approved constraints, THEN the application SHALL "
            "reject it without changing approved state. | UNWANTED_BEHAVIOR | AC-FR-002 | GIVEN input "
            "outside approved constraints, WHEN the application receives it, THEN the input "
            "is rejected and approved state is unchanged. | GHERKIN |"
        ),
        "| QAS-001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO |": (
            "| QAS-001 | REL-004 | Operator | Primary data store becomes unavailable | "
            "Development recovery rehearsal | Durable data store | Restore the latest "
            "approved backup | A timed restore rehearsal meets RTO 60 minutes and RPO "
            "15 minutes. |"
        ),
    }
    for before, after in replacements.items():
        if text.count(before) != 1:
            raise AssertionError(f"Expected one method-contract fixture row: {before}")
        text = text.replace(before, after, 1)
    text = complete_requirements_contract(text)

    for field, value in {
        "Project mode": "`greenfield`",
        "Delivery profile": "`quick-mvp`",
        "Effective risk": "`low`",
        "AWS lane": "`documentation-only`",
    }.items():
        text = set_table_value(
            text,
            "## Document status",
            "## 1. Workload profile",
            field,
            value,
        )
    text = set_table_value(
        text,
        "## Document status",
        "## 1. Workload profile",
        "Gate A derived status",
        "`APPROVED_FOR_DESIGN`",
    )
    text = set_table_value(
        text,
        "### Gate A — agent analysis record",
        "### Gate A — owner acceptance record",
        "Requirements revision analyzed",
        "`REQ-0001`",
    )
    for field in (
        "Open blocking finding IDs",
        "Proposed assumption IDs required to proceed",
        "Open blocking decision IDs",
    ):
        text = set_table_value(
            text,
            "### Gate A — agent analysis record",
            "### Gate A — owner acceptance record",
            field,
            "`NONE`",
        )
    text = set_table_value(
        text,
        "### Gate A — agent analysis record",
        "### Gate A — owner acceptance record",
        "Agent recommendation",
        "`READY_FOR_OWNER_APPROVAL`",
    )
    gate_a_card = {
        "Outcome": "`OUT-001 — Deliver FR-001`",
        "Owner and users": "`alice; development users`",
        "Scope and non-goals": "`FR-001 in scope; production is out of scope`",
        "Measurable requirement/acceptance IDs": "`FR-001, EX-001`",
        "Data boundary": "`Synthetic internal test data only`",
        "Identity/security boundary": "`Local development identity; no public access`",
        "Environment/Region": "`Development; us-west-2`",
        "Failure/recovery": "`Fail closed; local rollback to baseline`",
        "Cost posture": "`MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED`",
        "Intake provenance": "`owner message MSG-000`",
    }
    for field, value in gate_a_card.items():
        text = set_table_value(
            text,
            "### Gate A — readiness card",
            "### Gate A — owner acceptance record",
            field,
            value,
        )
    owner_values = {
        "Approver": "alice",
        "Owner decision": "`APPROVED`",
        "Authorized requirements revision": "`REQ-0001`",
        "Authorized cost posture": "`MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED`",
        "Explicitly accepted assumption IDs": "`NONE`",
        "Authorization provided at": "`2026-07-17T10:00:00-07:00`",
        "Authorization source": "`owner message MSG-001`",
        "Verbatim owner receipt": "`RECORDED_BELOW`",
        "Derived Gate A state": "`APPROVED_FOR_DESIGN`",
    }
    for field, value in owner_values.items():
        text = set_table_value(
            text,
            "### Gate A — owner acceptance record",
            "### Gate A validation and invalidation rules",
            field,
            value,
        )
    text = complete_coverage_plan(text)
    return set_receipt(
        text,
        "gate-a",
        "\n".join(
            [
                "APPROVE REQUIREMENTS GATE A",
                "Requirements revision: REQ-0001",
                "Cost posture: MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                "Accepted assumptions: NONE",
                "Approver: alice",
            ]
        ),
    )


def approve_gate_b(text: str, *, baseline: str = "a" * 40) -> str:
    text = complete_design_contract(text)
    design_contract, design_issues = doctor.derive_design_contract(
        text, "DES-0001", required=True
    )
    if design_issues or design_contract.canonical_sha256 is None:
        raise AssertionError(
            "Test Gate B requires a complete design contract: "
            + "; ".join(design_issues)
        )
    text = set_table_value(
        text,
        "## Document status",
        "## 1. Workload profile",
        "Gate B derived status",
        "`APPROVED_FOR_CONSTRUCTION`",
    )
    agent_values = {
        "Requirements revision reviewed": "`REQ-0001`",
        "Design revision reviewed": "`DES-0001`",
        "Construction authorization ID reviewed": "`AUTH-0001`",
        "PRD completeness gaps": "`NONE`",
        "Requirement-to-design-and-test traceability gaps": "`NONE`",
        "Unresolved risk or preservation gaps": "`NONE`",
        "Agent recommendation": "`READY_FOR_CONSTRUCTION_APPROVAL`",
    }
    for field, value in agent_values.items():
        text = set_table_value(
            text,
            "## 27. Gate B agent review record",
            "## 28. Construction envelope",
            field,
            value,
        )
    gate_b_card = {
        "Design basis IDs": "`DES-0001, FR-001`",
        "Architecture/components": "`ARCH-0001`",
        "Technology/toolchains/version policy": (
            "`TECH-0001, TECH-0002, TECH-0003, TECH-0004, TECH-0005, "
            "TECH-0006, TECH-0007, TECH-0008, TECH-0009`"
        ),
        "Interfaces/data flow": "`Local request and response flow`",
        "Identity/secrets": "`No secrets; local development identity`",
        "Failure/retry/concurrency": "`Fail closed; bounded retries; serialized state`",
        "Deployment/operations": "`Documentation-only AWS lane; local commands`",
        "Validation/evidence": "`EX-001 and focused unittest evidence`",
        "Rollback/recovery/teardown": "`Restore the authorized baseline commit`",
        "Brownfield compatibility/migration": "`NOT_APPLICABLE — greenfield project`",
        "Outstanding gaps": "`NONE`",
    }
    for field, value in gate_b_card.items():
        text = set_table_value(
            text,
            "### Gate B — readiness card",
            "## 28. Construction envelope",
            field,
            value,
        )
    envelope_values = {
        "Project mode": "`greenfield`",
        "Delivery profile and effective risk": "`quick-mvp / low`",
        "Project AWS lane": "`documentation-only`",
        "Authorized outcome": "`OUT-001 — Deliver the FR-001 outcome`",
        "Authorized requirement and design IDs": (
            "`REQ: REQ-0001; DES: DES-0001; SCOPE_IDS: FR-001, "
            "ARCH-0001, TECH-0001, TECH-0002, TECH-0003, TECH-0004, TECH-0005, "
            "TECH-0006, TECH-0007, TECH-0008, TECH-0009, PROP-001, HARNESS-004, "
            "API-001, BOUNDARY-001, WAVE-001`"
        ),
        "Design contract SHA-256": f"`{design_contract.canonical_sha256}`",
        "Authorized baseline commit": f"`{baseline}`",
        "Protected dirty paths": "`NONE`",
        "In-scope components and environments": "`app and tests in development`",
        "Allowed repository write set": "`PATHS: app/**; tests/**`",
        "Excluded or owner-only write set": "`PATHS: docs/project/PRD.md; bootstrap.yaml`",
        "Allowed external-state targets": "`NONE`",
        "Task boundary": "`DERIVED_FROM_AUTHORIZED_IDS_AND_WRITE_SET`",
        "Autonomous construction": "`ALLOWED`",
        "Maximum generated tasks": "`8`",
        "Maximum parallel workers": "`2`",
        "Parallelism rule": "`Disjoint changes in isolated worktrees; otherwise serialize`",
        "Attempt budget": "`3`",
        "Checkpoint cadence": "`COMMIT_AFTER_EACH_VALIDATED_WAVE_BEFORE_PAUSE`",
        "Local command boundary": "`ALLOW_PREFIXES: python -m unittest`",
        "GitHub boundary": "`NONE`",
        "GitHub repository, branch, and merge constraints": "`NONE`",
        "AWS boundary": "`DOCS_ONLY`",
        "Rollback, recovery, and teardown boundary": "`Local rollback only; teardown prohibited`",
        "Mandatory stop conditions": "`Any boundary, gate, attempt, or evidence mismatch`",
        "Authorization expiry or completion condition": "`Expires at 2099-12-31T23:59:59Z; earlier completion: release review`",
    }
    aws_not_applicable = "`NOT_APPLICABLE — AWS boundary DOCS_ONLY authorizes no authenticated action`"
    for field in doctor.AWS_DETAIL_FIELDS:
        envelope_values[field] = aws_not_applicable
    for field, value in envelope_values.items():
        text = set_table_value(
            text,
            "## 28. Construction envelope",
            "## 29. Gate B owner authorization record",
            field,
            value,
        )
    envelope_digest = doctor.canonical_envelope_sha256(text)
    text = set_table_value(
        text,
        "## 27. Gate B agent review record",
        "## 28. Construction envelope",
        "Construction envelope SHA-256 reviewed",
        f"`{envelope_digest}`",
    )
    owner_values = {
        "Approver": "alice",
        "Owner decision": "`APPROVED`",
        "Authorized requirements revision": "`REQ-0001`",
        "Authorized design revision": "`DES-0001`",
        "Authorized construction authorization ID": "`AUTH-0001`",
        "Authorized construction envelope SHA-256": f"`{envelope_digest}`",
        "Authorization provided at": "`2026-07-17T10:30:00-07:00`",
        "Authorization source": "`owner message MSG-002`",
        "Verbatim owner receipt": "`RECORDED_BELOW`",
        "Derived Gate B state": "`APPROVED_FOR_CONSTRUCTION`",
    }
    for field, value in owner_values.items():
        text = set_table_value(
            text,
            "## 29. Gate B owner authorization record",
            "## 30. Gate B validation and invalidation rules",
            field,
            value,
        )
    return set_receipt(
        text,
        "gate-b",
        "\n".join(
            [
                "APPROVE PRD AND CONSTRUCTION GATE B",
                "Requirements revision: REQ-0001",
                "Design revision: DES-0001",
                "Construction authorization: AUTH-0001",
                f"Construction envelope SHA-256: {envelope_digest}",
                "Use the proposed construction envelope above.",
                "Approver: alice",
            ]
        ),
    )


def rebind_gate_b_envelope(text: str) -> str:
    design_revision = doctor.table_after_heading(
        text, "## Document status"
    )["Current design revision"]
    design_contract, design_issues = doctor.derive_design_contract(
        text, design_revision, required=True
    )
    if design_issues or design_contract.canonical_sha256 is None:
        raise AssertionError(
            "Cannot rebind an invalid design contract: " + "; ".join(design_issues)
        )
    text = set_table_value(
        text,
        "## 28. Construction envelope",
        "## 29. Gate B owner authorization record",
        "Design contract SHA-256",
        f"`{design_contract.canonical_sha256}`",
    )
    digest = doctor.canonical_envelope_sha256(text)
    text = set_table_value(
        text,
        "## 27. Gate B agent review record",
        "## 28. Construction envelope",
        "Construction envelope SHA-256 reviewed",
        f"`{digest}`",
    )
    text = set_table_value(
        text,
        "## 29. Gate B owner authorization record",
        "## 30. Gate B validation and invalidation rules",
        "Authorized construction envelope SHA-256",
        f"`{digest}`",
    )
    return set_receipt(
        text,
        "gate-b",
        "\n".join(
            [
                "APPROVE PRD AND CONSTRUCTION GATE B",
                "Requirements revision: REQ-0001",
                "Design revision: DES-0001",
                "Construction authorization: AUTH-0001",
                f"Construction envelope SHA-256: {digest}",
                "Use the proposed construction envelope above.",
                "Approver: alice",
            ]
        ),
    )


def current_greenfield_state(state: dict[str, object], *, gate_b: bool = False) -> None:
    setup = state["setup"]
    project = state["project"]
    lifecycle = state["lifecycle"]
    assert isinstance(setup, dict)
    assert isinstance(project, dict)
    assert isinstance(lifecycle, dict)
    setup.update({"status": "CONFIGURED", "method": "EXTERNAL_COPY"})
    project.update(
        {
            "name": "Doctor Test Project",
            "region": "us-west-2",
            "cost_posture": "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
            "mode": "greenfield",
            "delivery_profile": "quick-mvp",
            "effective_risk": "low",
            "aws_lane": "documentation-only",
            "brownfield_baseline": "NOT_APPLICABLE",
        }
    )
    lifecycle["gate_a"] = "APPROVED_FOR_DESIGN"
    if gate_b:
        lifecycle["gate_b"] = "APPROVED_FOR_CONSTRUCTION"


def record_aws_core_evidence(
    text: str,
    phase: str,
    status: str = "PASS",
    *,
    binding: str | None = None,
    discovery_id: str | None = None,
    basis_ids: str = "DES-0001",
    discovered_skill_identifiers: str = "aws-architecture, aws-iam",
    actor: str = "CODEX_LIVE_TOOL_CALL",
    plugin_version: str = "1.2.0",
    advisory_design_binding: str = "DES-0001; TECH: NONE — no technology/toolchain impact",
) -> str:
    if binding is None:
        binding = {
            "DESIGN-10": "DES-0001",
            "AWS-10": "sha256:" + "a" * 64,
        }[phase]
    if discovery_id is None:
        discovery_id = {
            "DESIGN-10": "AWS-DISC-0002",
            "AWS-10": "AWS-DISC-0003",
        }[phase]
    for capability in doctor.AWS_CORE_REQUIRED_CAPABILITIES:
        text = record_aws_core_capability_evidence(
            text,
            phase,
            capability,
            status,
            binding=binding,
            discovery_id=discovery_id,
            basis_ids=basis_ids,
            discovered_skill_identifiers=discovered_skill_identifiers,
            actor=actor,
            plugin_version=plugin_version,
            advisory_design_binding=advisory_design_binding,
        )
    return text


def record_aws_core_capability_evidence(
    text: str,
    phase: str,
    capability: str,
    status: str = "PASS",
    *,
    binding: str,
    discovery_id: str | None = None,
    basis_ids: str = "DES-0001",
    discovered_skill_identifiers: str = "aws-architecture, aws-iam",
    actor: str = "CODEX_LIVE_TOOL_CALL",
    plugin_source: str = "aws/agent-toolkit-for-aws",
    invoked_identity: str = "aws-core@agent-toolkit-for-aws",
    plugin_version: str = "1.2.0",
    requested_skill: str | None = None,
    returned_skill_identifier: str | None = None,
    documentation_query: str | None = None,
    source_references: str | None = None,
    advisory_design_binding: str = "DES-0001; TECH: NONE — no technology/toolchain impact",
    credentials_inspected: str = "NO",
    aws_account_accessed: str = "NO",
) -> str:
    if discovery_id is None:
        discovery_id = {
            "DESIGN-10": "AWS-DISC-0002",
            "AWS-10": "AWS-DISC-0003",
        }[phase]
    if capability == "retrieve_skill":
        requested_skill = requested_skill or "aws-architecture"
        returned_skill_identifier = returned_skill_identifier or requested_skill
        documentation_query = "—"
        source_references = "—"
        observed_at = "2026-07-20T12:00:01Z"
    else:
        requested_skill = "—"
        returned_skill_identifier = "—"
        documentation_query = documentation_query or "AWS skills for current guidance"
        source_references = source_references or (
            "https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html"
        )
        observed_at = "2026-07-20T12:00:00Z"
    replacement = (
        f"| `{phase}` | `{discovery_id}` | `{basis_ids}` | `{plugin_source}` | "
        f"`{invoked_identity}` | `{plugin_version}` | `{capability}` | `{actor}` | "
        f"`{requested_skill}` | `{returned_skill_identifier}` | "
        f"`{documentation_query}` | `{discovered_skill_identifiers}` | "
        f"`{source_references}` | `{advisory_design_binding}` | "
        f"`{credentials_inspected}` | `{aws_account_accessed}` | `{observed_at}` | "
        f"`{binding}` | `{status}` |"
    )
    updated, count = re.subn(
        rf"^\| `{re.escape(phase)}` \| `{re.escape(discovery_id)}` \|.*"
        rf"\| `{re.escape(capability)}` \|.*$",
        replacement,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise AssertionError(
            f"Missing AWS Core evidence row for {phase} {discovery_id} {capability}"
        )
    return updated


def current_task_snapshot(
    text: str,
    *,
    gate_b: str = "APPROVED_FOR_CONSTRUCTION",
    baseline: str = "a" * 40,
) -> str:
    replacements = {
        "| Gate B state | `BLOCKED` |": f"| Gate B state | `{gate_b}` |",
        "| Baseline commit | `TODO` |": f"| Baseline commit | `{baseline}` |",
        "| Last known-green commit | `TODO` |": f"| Last known-green commit | `{baseline}` |",
        "| Next safe action | Complete Gate B; when current, run `TASK-10` |": "| Next safe action | Run `TASK-10` |",
    }
    for old, new in replacements.items():
        if old not in text:
            raise AssertionError(f"Missing task snapshot row: {old}")
        text = text.replace(old, new, 1)
    return text


def ready_task(
    write_set: str = "app/main.py",
    *,
    requirements: str = "REQ-0001; FR-001",
    design: str = "DES-0001; TECH: TECH-0001",
    outcome: str = "The authorized slice is implemented without expanding scope.",
    external_state: str = "NONE",
    command: str = "python -m unittest",
    github_issue: str = "PENDING_SYNC",
    property_projection: str = "",
) -> str:
    return f"""

### TASK-001 — Implement the authorized slice

- Status: `READY`
- Requirements: `{requirements}`
- Design: `{design}`
- Authorization: `AUTH-0001`
- Depends on: `NONE`
- Dependency waivers: `NONE`
- Owner: `UNASSIGNED`
- Run ID: `NONE`
- Risk: `low`
- Write set: `{write_set}`
- External state: `{external_state}`
- AWS mode: `NONE`
- Attempt budget: `3`
- Attempts used: `0`
- Evidence: `NONE`
- Blocker: `NONE`
- Skip record: `NONE`
- GitHub issue: `{github_issue}`
- Last checkpoint: `NONE`
- Last updated: `2026-07-17T11:00:00-07:00`

#### Outcome

{outcome}

#### Acceptance criteria

- [ ] The authorized behavior passes its focused test.

#### Validation

{property_projection}

```bash
{command}
```

#### Execution log

Not started.
"""


def put_contract_table(
    text: str,
    heading: str,
    table: str,
    insertion_marker: str,
) -> str:
    if heading not in text:
        replacement = f"{heading}\n\n{table.rstrip()}\n\n{insertion_marker}"
        if text.count(insertion_marker) != 1:
            raise AssertionError(f"Expected one insertion marker {insertion_marker!r}")
        return text.replace(insertion_marker, replacement, 1)
    start = text.index(heading) + len(heading)
    match = re.search(r"(?m)(?:^\|.*\|(?:\r?\n|$))+", text[start:])
    if match is None:
        raise AssertionError(f"Missing table after {heading!r}")
    table_start = start + match.start()
    table_end = start + match.end()
    return text[:table_start] + table.rstrip() + "\n" + text[table_end:]


def complete_coverage_plan(
    text: str,
    *,
    work_kind: str = "NEW_BUILD",
    disposition: str = "SELECT",
) -> str:
    document = doctor.table_after_heading(text, "## Document status")
    requirements_revision = document["Current requirements revision"]
    delivery_profile = document["Delivery profile"]
    if delivery_profile not in doctor.DELIVERY_PROFILES:
        text = set_table_value(
            text,
            "## Document status",
            "## 1. Workload profile",
            "Delivery profile",
            "`quick-mvp`",
        )
        document = doctor.table_after_heading(text, "## Document status")
        delivery_profile = "quick-mvp"
    basis_ids = ", ".join(
        [requirements_revision, *sorted(doctor.authoritative_requirement_ids(text))]
    )
    coverage_table = "\n".join(
        [
            "| Work kind | Delivery profile | Architecture disposition | Required sections | Omitted sections and reasons | Basis IDs |",
            "|---|---|---|---|---|---|",
            f"| {work_kind} | {delivery_profile} | {disposition} | "
            + ", ".join(doctor.COVERAGE_DOMAINS)
            + f" | NONE | {basis_ids} |",
        ]
    )
    return put_contract_table(
        text,
        doctor.COVERAGE_PLAN_HEADING,
        coverage_table,
        "## 1. Workload profile",
    )


def complete_project_design_contract(text: str) -> str:
    text = set_table_value(
        text,
        "## Document status",
        "## 1. Workload profile",
        "Project design contract schema",
        "`5`",
    )
    text = replace_contract_table(
        text,
        doctor.INTERFACE_HEADING,
        doctor.INTERFACE_HEADERS,
        [
            (
                "API-001",
                "API",
                "FR-001",
                "Local client",
                "Trusted application service",
                "Versioned request/response schema",
                "NOT_APPLICABLE - local development fixture",
                "Server verifies the caller may request the local outcome",
                "Reject values outside the approved schema",
                "Return the approved outcome with success status",
                "Return a safe error and preserve approved state",
                "Compatible schema additions only",
                "One idempotent read per request",
                "2 seconds",
                "100 requests per minute",
                "p95 response within 2 seconds",
            )
        ],
    )
    text = replace_contract_table(
        text,
        doctor.LAYER_BOUNDARY_HEADING,
        doctor.LAYER_BOUNDARY_HEADERS,
        [
            (
                "BOUNDARY-001",
                "Local client adapter",
                "Application domain",
                "Approved request and outcome DTOs",
                "Explicit adapter-to-domain mapping",
                "INWARD - adapter depends on the domain contract",
                "SERVER_SIDE - trusted service enforces authorization",
                "NOT_APPLICABLE - no external provider object crosses the boundary",
                "FR-001, FR-002",
                "AC-FR-001, AC-FR-002",
            )
        ],
    )
    text = replace_contract_table(
        text,
        doctor.STATE_APPLICABILITY_HEADING,
        doctor.STATE_APPLICABILITY_HEADERS,
        [
            (
                "RESOURCE-001",
                "NOT_APPLICABLE",
                "NOT_APPLICABLE - synchronous read has no meaningful lifecycle transition",
                "NONE",
            )
        ],
    )
    text = replace_contract_table(
        text, doctor.STATE_REGISTER_HEADING, doctor.STATE_REGISTER_HEADERS, []
    )
    text = replace_contract_table(
        text,
        doctor.FIRST_WAVE_HEADING,
        doctor.FIRST_WAVE_HEADERS,
        [
            (
                "WAVE-001",
                "NEW_BUILD",
                "JOURNEY-001",
                "FR-001",
                "AC-FR-001",
                "HARNESS-004",
                "NONE",
            )
        ],
    )
    return replace_contract_table_with_sentinel(
        text,
        doctor.SPIKE_HEADING,
        "no prerequisite discovery is needed before the walking skeleton",
    )


def complete_design_contract(text: str) -> str:
    foundation = doctor.contract_table_after_heading(
        text,
        doctor.INTAKE_FOUNDATION_HEADING,
        doctor.INTAKE_FOUNDATION_HEADERS,
    )
    if foundation is None or any(row[4] != "CONFIRMED" for row in foundation.rows):
        text = complete_intake_foundation(text)
    text = complete_requirements_contract(text)
    text = complete_coverage_plan(text)
    requirement_ids = sorted(doctor.authoritative_requirement_ids(text))
    requirement_list = ", ".join(requirement_ids)
    driver_table = "\n".join(
        [
            "| Driver ID | Requirement basis | Class | Decision implication | Validation |",
            "|---|---|---|---|---|",
            f"| DRV-0001 | {requirement_list} | HARD_CONSTRAINT | Preserve complete approved requirement coverage with the lowest operational burden | Compare every candidate against all requirement IDs |",
        ]
    )
    text = put_contract_table(text, doctor.ARCHITECTURE_DRIVER_HEADING, driver_table, doctor.ARCHITECTURE_CANDIDATE_HEADING)
    candidate_table = "\n".join(
        [
            "| Candidate ID | Architecture summary | Requirement coverage | AWS evidence | Eligibility | Failed constraints | Tradeoffs |",
            "|---|---|---|---|---|---|---|",
            f"| CAND-0001 | MANAGED_SERVERLESS_BASELINE: bounded managed entry, compute, and data services | {requirement_list} | AWS-EV-0001, AWS-EV-0002 | ELIGIBLE | NONE | Lowest idle cost and operations; service limits remain revisit triggers |",
            f"| CAND-0002 | Container service with continuously provisioned compute | {requirement_list} | AWS-EV-0001, AWS-EV-0002 | INELIGIBLE | DRV-0001 | More runtime control but unnecessary fixed operations for this bounded workload |",
        ]
    )
    text = put_contract_table(text, doctor.ARCHITECTURE_CANDIDATE_HEADING, candidate_table, doctor.ARCHITECTURE_SELECTION_HEADING)
    selection_table = "\n".join(
        [
            "| Architecture ID | Selected candidate | Requirement and driver basis | Rationale | Rejected alternatives | Risks | Mitigations | Security impact | Reliability impact | Operational burden | Cost effect | Breakpoints | Migration path | Revisit triggers | Validation |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
            f"| ARCH-0001 | CAND-0001 | {requirement_list}, DRV-0001 | Meets every hard constraint with the smallest managed surface | CAND-0002 | Managed-service limits | Validate quotas and alarms before deployment | Retains server-side authorization and least-privilege controls | Managed services bound failure domains with tested recovery | No continuously provisioned compute to operate | Pay per request with no intentional idle compute | Reassess at sustained utilization where containers are cheaper | Use versioned APIs and reversible IaC for any later migration | Reassess on quota, residency, or latency changes | Requirement trace and integration tests |",
        ]
    )
    text = put_contract_table(text, doctor.ARCHITECTURE_SELECTION_HEADING, selection_table, doctor.ARCHITECTURE_TRACEABILITY_HEADING)
    trace_rows = [
        (
            f"| {requirement_id} | ARCH-0001, COMP-0001 | "
            f"{'PROP-001' if requirement_id == 'FR-001' else 'EX-001'} | "
            "AWS-EV-0001, AWS-EV-0002 |"
        )
        for requirement_id in requirement_ids
    ]
    trace_table = "\n".join(
        [
            "| Requirement ID | ARCH / COMP / API / EVENT / CLI / FILE / DATA / CTRL / BOUNDARY / STATE IDs | Property/test IDs | Evidence IDs |",
            "|---|---|---|---|",
            *trace_rows,
        ]
    )
    text = put_contract_table(text, doctor.ARCHITECTURE_TRACEABILITY_HEADING, trace_table, doctor.MATERIAL_AWS_EVIDENCE_HEADING)
    evidence_table = "\n".join(
        [
            "| Evidence ID | Discovery ID | Design IDs | Material claim | AWS Core capability | Official reference | Observed date |",
            "|---|---|---|---|---|---|---|",
            "| AWS-EV-0001 | AWS-DISC-0002 | DRV-0001, CAND-0001, CAND-0002, ARCH-0001, TECH-0001 | AWS managed serverless services support bounded pay-per-use execution patterns | retrieve_skill | https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html | 2026-07-17 |",
            "| AWS-EV-0002 | AWS-DISC-0002 | DRV-0001, CAND-0001, CAND-0002, ARCH-0001, TECH-0004 | AWS documentation defines current serverless security and operational guidance | search_documentation | https://docs.aws.amazon.com/lambda/latest/dg/security.html | 2026-07-17 |",
        ]
    )
    change_impact_table = "\n".join(
        [
            "| Change ID | Changed basis IDs | Affected IDs | Preserved IDs | Required revalidation |",
            "|---|---|---|---|---|",
        ]
    )
    text = put_contract_table(
        text,
        doctor.CHANGE_IMPACT_HEADING,
        change_impact_table,
        "## 14. Architecture overview",
    )
    text = put_contract_table(text, doctor.MATERIAL_AWS_EVIDENCE_HEADING, evidence_table, "## 14. Architecture overview")
    technology_rows = (
        ("TECH-0001", "APPLICATION_RUNTIME", "Python", "CURRENT_LTS_AS_OF: 2026-07-01"),
        ("TECH-0002", "APPLICATION_FRAMEWORK", "FastAPI", "COMPATIBLE_MAJOR: 1"),
        (
            "TECH-0003",
            "FRONTEND_FRAMEWORK",
            "NOT_APPLICABLE — server-rendered interface",
            "NOT_APPLICABLE — server-rendered interface",
        ),
        ("TECH-0004", "INFRASTRUCTURE_AS_CODE", "AWS SAM", "COMPATIBLE_MAJOR: 1"),
        ("TECH-0005", "PACKAGE_BUILD_TOOLING", "pip", "MINIMUM: 24.0"),
        ("TECH-0006", "TEST_TOOLING", "unittest", "ORG_MANAGED: Python standard library"),
        ("TECH-0007", "PROPERTY_TESTING", "Hypothesis", "MINIMUM: 6.0"),
        ("TECH-0008", "SECURITY_VALIDATION", "Bandit", "EXACT: 1.7.9"),
        ("TECH-0009", "DEPLOYMENT_TOOLING", "AWS SAM CLI", "MINIMUM: 1.120"),
    )
    technology_table = "\n".join(
        [
            "| Decision ID | Concern | Selection | Version policy | Source | Basis IDs | Alternatives and rationale | Compatibility/migration | Validation |",
            "|---|---|---|---|---|---|---|---|---|",
            *(
                f"| {decision_id} | {concern} | {selection} | {policy} | "
                "AGENT_RECOMMENDATION | DES-0001, FR-001 | Selected for the approved slice | "
                "No migration required | Validate with the task command |"
                for decision_id, concern, selection, policy in technology_rows
            ),
        ]
    )
    text = put_contract_table(
        text,
        doctor.TECHNOLOGY_DECISION_HEADING,
        technology_table,
        "## 14. Architecture overview",
    )
    applicability = "\n".join(
        [
            "| Requirement ID | Applicability | Reason or property IDs |",
            "|---|---|---|",
            *(
                (
                    "| FR-001 | APPLICABLE | PROP-001 |"
                    if requirement_id == "FR-001"
                    else (
                        f"| {requirement_id} | NOT_APPLICABLE | "
                        "No stable generated-input oracle is approved for this requirement |"
                    )
                )
                for requirement_id in sorted(
                    doctor.authoritative_requirement_ids(text)
                )
            ),
        ]
    )
    applicability_pattern = re.compile(
        r"(?m)^\| Requirement ID \| Applicability \| Reason or property IDs \|\r?\n"
        r"^\|[-:| ]+\|\r?\n(?:^\|.*\|\r?\n?)+"
    )
    text, count = applicability_pattern.subn(applicability + "\n", text, count=1)
    if count != 1:
        raise AssertionError("Missing property applicability table")
    text = text.replace("| PROP-001 | SEC-002 |", "| PROP-001 | FR-001 |", 1)
    text = re.sub(r"(?m)^\| PROP-00[2-5] \|.*\|\r?\n?", "", text)
    execution_table = property_execution_projection()
    text = put_contract_table(
        text,
        doctor.PROPERTY_EXECUTION_HEADING,
        execution_table,
        "Add workload-specific properties for:",
    )
    harness_rows = [
        (
            f"| HARNESS-{index:03d} | {layer} | NOT_APPLICABLE | "
            "The focused fixture does not exercise this harness layer | "
            "DES-0001, FR-001 | NOT_APPLICABLE | NOT_APPLICABLE | "
            "NOT_APPLICABLE - the focused fixture validates other contracts |"
        )
        for index, layer in enumerate(
            (
                "Static",
                "Unit",
                "Integration",
                "End-to-end",
                "Property",
                "Security and privacy",
                "Reliability and recovery",
                "Performance and scalability",
                "IaC and policy",
                "AWS environment and operations",
            ),
            start=1,
        )
    ]
    harness_rows[3] = (
        "| HARNESS-004 | End-to-end | unittest journey validation | "
        "NEW_BUILD first outcome | DES-0001, FR-001, JOURNEY-001, WAVE-001 | "
        "python -m unittest tests.test_product_journeys | "
        "docs/project/VERIFY.md#harness-execution-evidence | REQUIRED |"
    )
    harness_table = "\n".join(
        [
            "| Harness ID | Layer | Selected check or tool | Trigger | Basis IDs | Exact command or API | Evidence destination | Required or conditional status |",
            "|---|---|---|---|---|---|---|---|",
            *harness_rows,
        ]
    )
    text = put_contract_table(
        text,
        doctor.HARNESS_HEADING,
        harness_table,
        "## 27. Gate B agent review record",
    )
    return complete_project_design_contract(text)


def complete_legacy_design_bridge(text: str) -> str:
    text = exact_legacy_requirements_projection(complete_design_contract(approve_gate_a(text)))
    text = text.replace(
        "DES-0001, FR-001, JOURNEY-001, WAVE-001",
        "DES-0001, FR-001, WAVE-001",
        1,
    )
    text = replace_contract_table(
        text,
        doctor.STATE_APPLICABILITY_HEADING,
        doctor.STATE_APPLICABILITY_HEADERS,
        [("RESOURCE-001", "APPLICABLE", "LIFECYCLE_RESOURCE: FR-001", "STATE-001")],
    )
    text = replace_contract_table(
        text,
        doctor.STATE_REGISTER_HEADING,
        doctor.STATE_REGISTER_HEADERS,
        [(
            "STATE-001", "RESOURCE-001", "PENDING, READY", "PENDING",
            "PENDING to READY", "READY", "Reject invalid transitions",
            "FR-001", "AC-FR-001",
        )],
    )
    return replace_contract_table(
        text,
        doctor.FIRST_WAVE_HEADING,
        doctor.FIRST_WAVE_HEADERS,
        [(
            "WAVE-001", "NEW_BUILD", "NONE", "FR-001", "AC-FR-001",
            "HARNESS-004", "NONE",
        )],
    )


def property_execution_projection() -> str:
    return "\n".join(
        [
            "| Property ID | Framework TECH ID | Exact command | Run target/time bound | Seed or reproduction format | Evidence destination |",
            "|---|---|---|---|---|---|",
            "| PROP-001 | TECH-0007 | python -m unittest tests.test_properties | MIN_CASES: 100; MAX_SECONDS: 30 | integer seed; reproduce with the recorded --seed value | docs/project/VERIFY.md#property-based-test-evidence |",
        ]
    )


def property_test_evidence_row(
    *,
    evidence_id: str = "EV-0001",
    task_id: str = "TASK-001",
    property_id: str = "PROP-001",
    basis: str = "REQ-0001 / DES-0001 / AUTH-0001",
    result: str = "PASS",
    exact_command: str = "python -m unittest tests.test_properties",
    framework_tech_id: str = "TECH-0007",
    framework_selection: str = "Hypothesis",
    observed_version: str = "6.112.1",
    observed_run: str = "CASES: 100; ELAPSED_SECONDS: 1.25",
    replay: str = "seed: 12345",
    counterexample: str = "NONE",
    failure: str = "NONE",
    observed_at: str = "2026-07-17T12:00:00-07:00",
    material: str = "commit: " + "a" * 40,
    source: str = "docs/project/VERIFY.md#ev-0001",
) -> str:
    return (
        f"| {evidence_id} | {task_id} | {basis} | {property_id} | "
        f"{framework_tech_id} | {framework_selection} | {observed_version} | "
        f"{exact_command} | {observed_run} | {replay} | {counterexample} | "
        f"{failure} | {result} | {observed_at} | {material} | {source} |"
    )


def property_test_evidence_section(**row_options: str) -> str:
    return "\n".join(
        [
            "## Property-based test evidence",
            "",
            "| Evidence ID | Task ID | REQ / DES / AUTH | Property ID | Framework TECH ID | Framework selection | Observed exact version | Exact command | Observed run | Replay seed or exact command | Minimized counterexample | Failure class / resolution | Result | Observed at | Commit / worktree / artifact | Durable source |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
            property_test_evidence_row(**row_options),
        ]
    )


def task_completion_evidence_section(
    *rows: tuple[str, str, str, str, str, str],
) -> str:
    """Build exact task-completion rows that bind property-test evidence."""

    if not rows:
        rows = (
            (
                "EV-0001",
                "python -m unittest tests.test_properties",
                "2026-07-17T12:00:00-07:00",
                "commit: " + "a" * 40,
                "docs/project/VERIFY.md#ev-0001",
                "LOCAL_PASS",
            ),
        )
    rendered_rows = [
        (
            f"| {evidence_id} | TASK-001 | {command} | observed property run | "
            f"alice | {observed_at} | {material} | {source} | {status} |"
        )
        for evidence_id, command, observed_at, material, source, status in rows
    ]
    return "\n".join(
        [
            "## Task completion evidence",
            "",
            "| Evidence ID | Task | Command or observation | Result | Actor | Observed at | Commit / worktree / artifact | Durable source | Status |",
            "|---|---|---|---|---|---|---|---|---|",
            *rendered_rows,
        ]
    )


def refresh_control_hashes(project: Path) -> None:
    manifest_path = project / "bootstrap.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["control_sha256"] = {
        relative: hashlib.sha256((project / relative).read_bytes()).hexdigest()
        for relative in doctor.CONTROL_HASH_FILES
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def aws_authority_envelope(
    *,
    role: str,
    account: str,
    region: str,
    environment: str,
    resources: list[str],
    operations: list[str],
    artifact: str,
    rollback: str,
    boundary: str = "MUTATE_LISTED_RESOURCES",
) -> dict[str, str]:
    return {
        "AWS boundary": boundary,
        "AWS role or profile": f"ROLE: {role}",
        "AWS account": f"ACCOUNT: {account}",
        "AWS Region": f"REGION: {region}",
        "AWS environment": (
            f"ENVIRONMENT: {environment}; CLASS: NON_PRODUCTION"
        ),
        "AWS stack or application": "STACK: fastlane-stack",
        "AWS resource allowlist": "RESOURCES: " + ", ".join(resources),
        "AWS allowed operations": "OPERATIONS: " + ", ".join(operations),
        "AWS cost ceiling": "USD: 20.00",
        "AWS artifact authorization and provenance": f"EXACT_DIGEST: {artifact}",
        "AWS rollback boundary": f"ROLLBACK: {rollback}",
        "AWS authorization validity": (
            "Expires at 2099-12-31T23:59:59Z; "
            "earlier completion: authorized AWS action ends"
        ),
        "Authorization expiry or completion condition": (
            "Expires at 2099-12-31T23:59:59Z; "
            "earlier completion: release review"
        ),
        "Authorized baseline commit": "a" * 40,
    }


def ready_preflight(
    *, account: str, region: str, environment: str
) -> dict[str, str]:
    return {
        "status": "READY",
        "preflight_id": "AWS-PREFLIGHT-0001",
        "account_access": "READ_ONLY_OBSERVED",
        "account": account,
        "region": region,
        "environment": environment,
    }


class BootstrapDoctorTests(unittest.TestCase):
    def copy_project(self, destination: Path) -> Path:
        project = destination / "project"
        project.mkdir()
        manifest = json.loads(
            (PROJECT_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        for relative in manifest["required_files"]:
            source = PROJECT_ROOT.joinpath(*PurePosixPath(relative).parts)
            target = project.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        values = dict(bootstrap_runtime.PLACEHOLDERS)
        values.update(
            {
                "My AWS Project": "Doctor Test Project",
                "{{AWS_REGION}}": "us-west-2",
                "{{COST_POSTURE}}": "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
            }
        )
        for relative in manifest["required_files"]:
            if not bootstrap_runtime.should_render_path(relative):
                continue
            path = project.joinpath(*PurePosixPath(relative).parts)
            rendered = bootstrap_runtime.rendered_bytes(path, values, render=True)
            if rendered != path.read_bytes():
                path.write_bytes(rendered)
        return project

    def approve_project(self, project: Path, *, gate_b: bool = True) -> None:
        baseline = "a" * 40
        if gate_b:
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            subprocess.run(["git", "-C", str(project), "config", "user.name", "Doctor Test"], check=True)
            subprocess.run(
                ["git", "-C", str(project), "config", "user.email", "doctor@example.test"],
                check=True,
            )
            subprocess.run(["git", "-C", str(project), "add", "."], check=True)
            subprocess.run(["git", "-C", str(project), "commit", "-qm", "baseline"], check=True)
            baseline = subprocess.run(
                ["git", "-C", str(project), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        prd_path = project / "docs/project/PRD.md"
        text = approve_gate_a(prd_path.read_text(encoding="utf-8"))
        if gate_b:
            text = approve_gate_b(text, baseline=baseline)
        prd_path.write_text(text, encoding="utf-8")
        state_path = project / "bootstrap.yaml"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        current_greenfield_state(state, gate_b=gate_b)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        if gate_b:
            tasks_path = project / "docs/project/TASKS.md"
            tasks_path.write_text(
                current_task_snapshot(
                    tasks_path.read_text(encoding="utf-8"), baseline=baseline
                ),
                encoding="utf-8",
            )
            verify_path = project / "docs/project/VERIFY.md"
            verify_text = record_aws_core_evidence(
                verify_path.read_text(encoding="utf-8"), "DESIGN-10"
            )
            verify_path.write_text(verify_text, encoding="utf-8")

    def initialize_task_plan(self, project: Path, task_text: str) -> None:
        state_path = project / "bootstrap.yaml"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["execution"]["plan_revision"] = "PLAN-0001"
        state["execution"]["plan_state"] = "CURRENT"
        state["execution"]["attempts"] = {"TASK-001": 0}
        state_path.write_text(json.dumps(state), encoding="utf-8")
        tasks_path = project / "docs/project/TASKS.md"
        text = tasks_path.read_text(encoding="utf-8").replace(
            "| Task-plan revision | `UNINITIALIZED` |",
            "| Task-plan revision | `PLAN-0001` |",
            1,
        )
        text = text.replace(
            "| Task-plan state | `UNINITIALIZED` |",
            "| Task-plan state | `CURRENT` |",
            1,
        )
        tasks_path.write_text(text + task_text, encoding="utf-8")

    def pause_project_at_real_checkpoint(self, project: Path) -> str:
        """Create a coherent paused checkpoint with coordinator ledgers dirty."""

        subprocess.run(["git", "-C", str(project), "add", "docs/project/PRD.md"], check=True)
        subprocess.run(
            ["git", "-C", str(project), "commit", "-qm", "approve gate b prd"],
            check=True,
        )
        known_green = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.initialize_task_plan(
            project,
            ready_task(
                requirements="REQ-0001; FR-001; PROP-001",
                design="DES-0001; TECH: TECH-0001, TECH-0007",
                command="python -m unittest tests.test_properties",
                property_projection=property_execution_projection(),
            ),
        )

        state_path = project / "bootstrap.yaml"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["execution"].update(
            {
                "mode": "SINGLE_TASK",
                "state": "CHECKPOINTED",
                "run_id": "RUN-0001",
                "coordinator": "doctor-test-coordinator",
                "basis": {
                    "requirements_revision": "REQ-0001",
                    "design_revision": "DES-0001",
                    "construction_authorization": "AUTH-0001",
                },
                "active_tasks": [],
                "last_checkpoint": {
                    "id": "CP-0001",
                    "at": "2026-07-17T12:00:00-07:00",
                    "evidence_ref": "docs/project/VERIFY.md#cp-0001",
                },
            }
        )
        state_path.write_text(json.dumps(state), encoding="utf-8")

        tasks_path = project / "docs/project/TASKS.md"
        text = tasks_path.read_text(encoding="utf-8")
        for field, value in {
            "Run state": "`PAUSED`",
            "Active run ID": "`RUN-0001`",
            "Coordinator": "`doctor-test-coordinator`",
            "Last checkpoint": "`CP-0001`",
            "Last known-green commit": f"`{known_green}`",
            "Next safe action": "Resume the current checkpointed run.",
        }.items():
            text = set_table_value(
                text,
                "## Active execution snapshot",
                "## Coordinator contract",
                field,
                value,
            )
        checkpoint = (
            f"| `CP-0001` | `RUN-0001` | 2026-07-17T12:00:00-07:00 | "
            f"`REQ-0001` / `DES-0001` / `AUTH-0001` | "
            f"Commit: `{known_green}`; Dirty: NONE | "
            "TASK-001 READY attempts=0/3 | Evidence: NONE; External: NONE | "
            "Blockers: NONE; Next: resume TASK-001 |\n"
        )
        text = text.replace("\n\nTo resume,", "\n" + checkpoint + "\nTo resume,", 1)
        tasks_path.write_text(text, encoding="utf-8")

        verify_path = project / "docs/project/VERIFY.md"
        verify_path.write_text(
            verify_path.read_text(encoding="utf-8")
            + "\n\n### CP-0001\n\nCheckpoint receipt recorded.\n",
            encoding="utf-8",
        )
        return known_green

    @source_template_only
    def test_ordinary_doctor_routes_untouched_template_to_prerequisites(self) -> None:
        report = doctor.inspect_project(PROJECT_ROOT)

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["classification"], "UNCONFIGURED_TEMPLATE")
        self.assertEqual(
            report["gates"], {"gate_a": "BLOCKED", "gate_b": "BLOCKED"}
        )
        self.assertEqual(report["authorizations"]["construction"], "NONE")
        self.assertEqual(report["authorizations"]["aws"], "NONE")
        self.assertEqual(
            report["interaction"],
            {
                "owner_stage": "DEFINE",
                "response_mode": "BLOCKER",
                "state": "BLOCKED",
                "route_reason_code": "UNCONFIGURED_TEMPLATE",
                "owner_action_required": True,
                "owner_action_kind": "COMPLETE_PREREQUISITE_CHECKLIST",
                "blocking_ids": sorted(
                    {item["code"] for item in report["diagnostics"]}
                ),
                "automatic_continuation_allowed": False,
                "turn_boundary_required": True,
                "formal_receipt_required": False,
                "aws_core": {
                    "materiality": "NOT_MATERIAL",
                    "evidence_status": "NOT_REQUIRED",
                },
            },
        )

    @source_template_only
    def test_template_source_is_coherent_and_routes_to_intake(self) -> None:
        report = doctor.inspect_project(PROJECT_ROOT, template_source=True)

        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["bootstrap_version"], "1.0.1")
        self.assertEqual(report["classification"], "TEMPLATE_SOURCE")
        self.assertEqual(report["next_prompt"], "INTAKE-10")
        self.assertEqual(
            report["gates"],
            {"gate_a": "BLOCKED", "gate_b": "BLOCKED"},
        )
        self.assertEqual(report["evidence_state"], "NOT_READY")
        self.assertEqual(
            report["authorizations"],
            {"construction": "NONE", "aws": "NONE"},
        )
        self.assertEqual(report["design_contract"]["schema_version"], 5)
        self.assertIn(
            report["design_contract"]["status"],
            {"UNINITIALIZED", "BLOCKED"},
        )

    def test_each_ears_form_accepts_a_canonical_requirement(self) -> None:
        examples = {
            "UBIQUITOUS": "The system SHALL record the approved result.",
            "EVENT_DRIVEN": (
                "WHEN an approved request arrives, the application SHALL return the result."
            ),
            "STATE_DRIVEN": (
                "WHILE recovery is active, the service SHALL reject conflicting writes."
            ),
            "UNWANTED_BEHAVIOR": (
                "IF input exceeds the approved limit, THEN the service SHALL reject the input."
            ),
            "OPTIONAL_FEATURE": (
                "WHERE durable recovery applies, the project SHALL retain an approved backup."
            ),
            "COMPLEX": (
                "WHILE recovery is active, WHEN a status request arrives, the system SHALL "
                "return the current recovery state."
            ),
        }
        for ears_form, requirement in examples.items():
            with self.subTest(ears_form=ears_form):
                self.assertEqual(
                    doctor.requirement_method_issues(
                        "FR-900",
                        requirement,
                        ears_form,
                        "A bounded test confirms the observable result for every approved case.",
                        "MEASURABLE",
                    ),
                    [],
                )

    def test_requirement_method_contract_rejects_malformed_examples(self) -> None:
        measurable = "A bounded test confirms the observable result."
        cases = {
            "missing SHALL": (
                "The system records the approved result.", "UBIQUITOUS", measurable,
            ),
            "clause order": (
                "The system SHALL record the approved result.", "EVENT_DRIVEN", measurable,
            ),
            "requirement subject": (
                "The thing SHALL record the approved result.", "UBIQUITOUS", measurable,
            ),
            "requirement is unresolved": (
                "TODO", "UBIQUITOUS", measurable,
            ),
        }
        for expected, (requirement, ears_form, acceptance) in cases.items():
            with self.subTest(expected=expected):
                issues = doctor.requirement_method_issues(
                    "FR-901", requirement, ears_form, acceptance, "MEASURABLE"
                )
                self.assertTrue(any(expected in issue for issue in issues), issues)

    def test_fastlane_ears_accepts_concrete_subjects_and_commas(self) -> None:
        cases = (
            (
                "The worker SHALL record the approved result.",
                "UBIQUITOUS",
            ),
            (
                "WHEN input contains commas, quotes, and spaces, the parser SHALL preserve the value.",
                "EVENT_DRIVEN",
            ),
            (
                "WHILE recovery handles old, partial state, WHEN a request contains commas, the coordinator SHALL preserve the current result.",
                "COMPLEX",
            ),
        )
        for requirement, ears_form in cases:
            with self.subTest(requirement=requirement):
                self.assertEqual(
                    doctor.requirement_method_issues(
                        "FR-903",
                        requirement,
                        ears_form,
                        "A bounded test confirms the observable result for every approved case.",
                        "MEASURABLE",
                    ),
                    [],
                )

    def test_measurable_acceptance_rejects_keyword_only_claims(self) -> None:
        issues = doctor.requirement_method_issues(
            "FR-904",
            "The service SHALL reject invalid input.",
            "UBIQUITOUS",
            "Secure, bounded, policy compliant.",
            "MEASURABLE",
        )
        self.assertTrue(
            any("observable expected result" in issue for issue in issues),
            issues,
        )

    def test_gherkin_and_measurable_acceptance_forms_are_distinct(self) -> None:
        requirement = "The system SHALL record the approved result."
        gherkin = (
            "GIVEN an approved request, WHEN the system receives it, "
            "THEN the result is recorded."
        )
        measurable = "A bounded test confirms the result for every approved request."
        self.assertEqual(
            doctor.requirement_method_issues(
                "FR-902", requirement, "UBIQUITOUS", gherkin, "GHERKIN"
            ),
            [],
        )
        self.assertTrue(
            doctor.requirement_method_issues(
                "FR-902", requirement, "UBIQUITOUS", gherkin, "MEASURABLE"
            )
        )
        self.assertTrue(
            doctor.requirement_method_issues(
                "FR-902", requirement, "UBIQUITOUS", measurable, "GHERKIN"
            )
        )

    def test_quality_attribute_scenario_requires_complete_bounded_fields(self) -> None:
        text = approve_gate_a(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        requirement_ids = doctor.authoritative_requirement_ids(text)
        self.assertEqual(
            doctor.quality_attribute_scenario_issues(text, requirement_ids), []
        )
        broken = text.replace(
            "A timed restore rehearsal meets RTO 60 minutes and RPO 15 minutes.",
            "TODO",
            1,
        )
        issues = doctor.quality_attribute_scenario_issues(broken, requirement_ids)
        self.assertTrue(any("QAS-001: Response measure is unresolved" in issue for issue in issues))

    def test_fastlane_ears_migration_is_complete_and_grandfathers_only_current_gate_a(self) -> None:
        legacy = """| ID | Requirement | Acceptance criteria |
|---|---|---|
| FR-001 | Existing approved behavior | Existing approved observation |
"""
        grandfathered = doctor.Context(Path("."))
        doctor.validate_gate_a_method_contract(
            grandfathered,
            legacy,
            grandfather_approved_v1=True,
        )
        self.assertEqual(grandfathered.diagnostics, [])

        unapproved = doctor.Context(Path("."))
        doctor.validate_gate_a_method_contract(
            unapproved,
            legacy,
            grandfather_approved_v1=False,
        )
        self.assertTrue(
            any(
                item.code == "REQUIREMENT_METHOD_MIGRATION_REQUIRED"
                and "FR-001" in item.message
                for item in unapproved.diagnostics
            ),
            unapproved.diagnostics,
        )

        partial = legacy + """
| ID | Requirement | EARS form | Acceptance criteria | Acceptance form |
|---|---|---|---|---|
| FR-002 | The worker SHALL preserve the approved result. | UBIQUITOUS | A bounded test confirms every approved result is preserved. | MEASURABLE |
"""
        mixed = doctor.Context(Path("."))
        doctor.validate_gate_a_method_contract(
            mixed,
            partial,
            grandfather_approved_v1=True,
        )
        self.assertTrue(
            any(
                item.code == "REQUIREMENT_METHOD_MIGRATION_REQUIRED"
                and "FR-001" in item.message
                for item in mixed.diagnostics
            ),
            mixed.diagnostics,
        )

    def test_gate_a_rejects_unresolved_normative_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self.copy_project(Path(temp_dir))
            self.approve_project(project, gate_b=False)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8").replace(
                "The application SHALL display the current approved project outcome.",
                "TODO",
                1,
            )
            prd_path.write_text(text, encoding="utf-8")
            report = doctor.inspect_project(project)
            self.assertIn("REQUIREMENT_METHOD_CONTRACT", codes(report))
            messages = [item["message"] for item in report["diagnostics"]]
            self.assertTrue(
                any("FR-001: requirement is unresolved" in message for message in messages),
                messages,
            )

    def test_design_contract_parser_is_deterministic_and_fail_closed(self) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        initial, _initial_issues = doctor.derive_design_contract(template, "DES-0001")
        self.assertIn(initial.status, {"UNINITIALIZED", "BLOCKED"})
        absent, _absent_issues = doctor.derive_design_contract("", "DES-0001")
        required_absent, _required_absent_issues = doctor.derive_design_contract(
            "", "DES-0001", required=True
        )
        self.assertEqual(absent.status, "UNINITIALIZED")
        self.assertEqual(required_absent.status, "BLOCKED")

        complete = complete_design_contract(template)
        ready, issues = doctor.derive_design_contract(complete, "DES-0001")
        self.assertEqual(issues, [])
        self.assertEqual(ready.status, "READY")
        self.assertEqual(len(ready.technology_decisions), 9)
        self.assertEqual(len(ready.property_execution), 1)
        self.assertRegex(ready.canonical_sha256 or "", r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(
            doctor.technology_version_policy_allows(
                "EXACT: nodejs20.x",
                "nodejs20.x",
            )
        )
        self.assertFalse(
            doctor.technology_version_policy_allows(
                "EXACT: nodejs20.x",
                "nodejs22.x",
            )
        )
        self.assertTrue(
            doctor.technology_version_policy_allows("MINIMUM: 6.0", "6.112.1")
        )
        self.assertFalse(
            doctor.technology_version_policy_allows("MINIMUM: 6.0", "6.0rc1")
        )
        self.assertFalse(
            doctor.technology_version_policy_allows(
                "CURRENT_LTS_AS_OF: 2026-07-01",
                "0.0.1",
            )
        )
        self.assertFalse(
            doctor.technology_version_policy_allows(
                "ORG_MANAGED: company baseline",
                "0.0.1",
            )
        )
        self.assertFalse(doctor.valid_technology_version_policy("MINIMUM: latest"))
        for sentinel in (
            "TODO",
            "TBD",
            "TBC",
            "UNKNOWN",
            "UNASSIGNED",
            "PENDING",
            "PLACEHOLDER",
            "NOT_STARTED",
            "NONE",
            "N/A",
        ):
            with self.subTest(technology_sentinel=sentinel):
                self.assertFalse(doctor.valid_technology_selection(sentinel))
                self.assertFalse(
                    doctor.valid_technology_version_policy(f"EXACT: {sentinel}")
                )
                self.assertFalse(
                    doctor.valid_technology_version_policy(f"ORG_MANAGED: {sentinel}")
                )
                self.assertFalse(
                    doctor.machine_comparable_property_version_policy(
                        f"EXACT: {sentinel}"
                    )
                )
                self.assertFalse(
                    doctor.technology_version_policy_allows(
                        f"EXACT: {sentinel}", sentinel
                    )
                )
        self.assertFalse(
            doctor.valid_technology_version_policy("NOT_APPLICABLE \u2014 N/A")
        )
        self.assertTrue(
            doctor.replay_evidence_matches_contract(
                "record the exact command",
                "python -m unittest tests.test_properties",
                "python -m unittest tests.test_properties",
            )
        )
        self.assertFalse(
            doctor.replay_evidence_matches_contract(
                "record the exact command",
                "python -m unittest wrong",
                "python -m unittest tests.test_properties",
            )
        )
        self.assertTrue(
            doctor.valid_property_execution_command(
                "python -m unittest tests.test_properties"
            )
        )
        self.assertFalse(doctor.valid_property_execution_command("PENDING"))
        self.assertFalse(
            doctor.valid_property_execution_command("Run property tests")
        )

        technology_header = (
            "| Decision ID | Concern | Selection | Version policy | Source | Basis IDs | "
            "Alternatives and rationale | Compatibility/migration | Validation |"
        )
        with_trailing_space = complete.replace(
            technology_header, technology_header + "   ", 1
        )
        normalized, normalized_issues = doctor.derive_design_contract(
            with_trailing_space, "DES-0001"
        )
        self.assertEqual(normalized_issues, [])
        self.assertEqual(normalized.canonical_sha256, ready.canonical_sha256)
        changed, changed_issues = doctor.derive_design_contract(
            complete.replace("| TECH-0007 | PROPERTY_TESTING | Hypothesis |", "| TECH-0007 | PROPERTY_TESTING | Hypothesis 7 |", 1),
            "DES-0001",
        )
        self.assertEqual(changed_issues, [])
        self.assertNotEqual(changed.canonical_sha256, ready.canonical_sha256)

        property_row = (
            "| PROP-001 | TECH-0007 | python -m unittest tests.test_properties | "
            "MIN_CASES: 100; MAX_SECONDS: 30 | integer seed; reproduce with the recorded "
            "--seed value | docs/project/VERIFY.md#property-based-test-evidence |"
        )
        technology_row = next(
            line for line in complete.splitlines() if line.startswith("| TECH-0007 |")
        )
        cases = {
            "malformed header": (
                complete.replace("| Decision ID | Concern |", "| ID | Concern |", 1),
                "headers must be exactly",
            ),
            "duplicate stable ID": (
                complete.replace(technology_row, technology_row + "\n" + technology_row, 1),
                "Duplicate technology decision ID",
            ),
            "unresolved cell": (
                complete.replace("| TECH-0007 | PROPERTY_TESTING | Hypothesis |", "| TECH-0007 | PROPERTY_TESTING | TODO |", 1),
                "unresolved technology decision cell",
            ),
            "pending selection sentinel": (
                complete.replace(
                    "| TECH-0007 | PROPERTY_TESTING | Hypothesis |",
                    "| TECH-0007 | PROPERTY_TESTING | PENDING |",
                    1,
                ),
                "unresolved technology decision cell",
            ),
            "placeholder version-policy payload": (
                complete.replace("MINIMUM: 6.0", "EXACT: PLACEHOLDER", 1),
                "unresolved technology decision cell",
            ),
            "pending basis sentinel": (
                complete.replace("DES-0001, FR-001", "PENDING", 1),
                "unresolved technology decision cell",
            ),
            "placeholder rationale sentinel": (
                complete.replace(
                    "Selected for the approved slice",
                    "PLACEHOLDER",
                    1,
                ),
                "unresolved technology decision cell",
            ),
            "not-applicable compatibility sentinel": (
                complete.replace("No migration required", "N/A", 1),
                "unresolved technology decision cell",
            ),
            "none validation sentinel": (
                complete.replace(
                    "Validate with the task command",
                    "NONE",
                    1,
                ),
                "unresolved technology decision cell",
            ),
            "non-canonical not applicable selection": (
                complete.replace(
                    "| TECH-0003 | FRONTEND_FRAMEWORK | NOT_APPLICABLE — server-rendered interface |",
                    "| TECH-0003 | FRONTEND_FRAMEWORK | N/A |",
                    1,
                ),
                "invalid selection",
            ),
            "placeholder not applicable reason": (
                complete.replace(
                    "| TECH-0003 | FRONTEND_FRAMEWORK | NOT_APPLICABLE — server-rendered interface |",
                    "| TECH-0003 | FRONTEND_FRAMEWORK | NOT_APPLICABLE — N/A |",
                    1,
                ),
                "invalid selection",
            ),
            "active property framework marked not applicable": (
                complete.replace(
                    "| TECH-0007 | PROPERTY_TESTING | Hypothesis |",
                    "| TECH-0007 | PROPERTY_TESTING | NOT_APPLICABLE — no property tests |",
                    1,
                ),
                "active property execution cannot use a NOT_APPLICABLE",
            ),
            "invalid version policy": (
                complete.replace("MINIMUM: 6.0", "LATEST", 1),
                "invalid version policy",
            ),
            "minimum policy cannot be compared": (
                complete.replace("MINIMUM: 6.0", "MINIMUM: latest", 1),
                "invalid version policy",
            ),
            "current lts cannot govern active property evidence": (
                complete.replace(
                    "| TECH-0007 | PROPERTY_TESTING | Hypothesis | MINIMUM: 6.0 |",
                    "| TECH-0007 | PROPERTY_TESTING | Hypothesis | CURRENT_LTS_AS_OF: 2026-07-01 |",
                    1,
                ),
                "active property execution requires an EXACT, COMPATIBLE_MAJOR, or numeric MINIMUM version policy",
            ),
            "organization managed cannot govern active property evidence": (
                complete.replace(
                    "| TECH-0007 | PROPERTY_TESTING | Hypothesis | MINIMUM: 6.0 |",
                    "| TECH-0007 | PROPERTY_TESTING | Hypothesis | ORG_MANAGED: organization baseline |",
                    1,
                ),
                "active property execution requires an EXACT, COMPATIBLE_MAJOR, or numeric MINIMUM version policy",
            ),
            "invalid source": (
                complete.replace(
                    "CURRENT_LTS_AS_OF: 2026-07-01 | AGENT_RECOMMENDATION |",
                    "CURRENT_LTS_AS_OF: 2026-07-01 | INTERNET_SEARCH |",
                    1,
                ),
                "invalid source",
            ),
            "prose basis IDs": (
                complete.replace("DES-0001, FR-001", "DES-0001 and FR-001", 1),
                "Basis IDs must be exact comma-separated stable IDs",
            ),
            "duplicate basis IDs": (
                complete.replace(
                    "DES-0001, FR-001",
                    "DES-0001, FR-001, FR-001",
                    1,
                ),
                "Basis IDs must be exact comma-separated stable IDs",
            ),
            "wrong framework cross-reference": (
                complete.replace(property_row, property_row.replace("TECH-0007", "TECH-0006"), 1),
                "PROPERTY_TESTING decision",
            ),
            "replay format has no machine-checkable mode": (
                complete.replace(
                    property_row,
                    property_row.replace(
                        "integer seed; reproduce with the recorded --seed value",
                        "capture replay information",
                    ),
                    1,
                ),
                "declare a seed or exact-command replay mode",
            ),
            "not-applicable applicability without reason": (
                complete.replace(
                    "| FR-001 | APPLICABLE | PROP-001 |",
                    "| FR-001 | NOT_APPLICABLE | NONE |",
                    1,
                ),
                "NOT_APPLICABLE requires a concrete reason",
            ),
            "property definition references stale requirement": (
                complete.replace(
                    "| PROP-001 | FR-001 |",
                    "| PROP-001 | FR-999 |",
                    1,
                ),
                "Requirement IDs must exactly match the applicability table's current inverse mapping",
            ),
            "property definition duplicates requirement": (
                complete.replace(
                    "| PROP-001 | FR-001 |",
                    "| PROP-001 | FR-001, FR-001 |",
                    1,
                ),
                "Requirement IDs must exactly match the applicability table's current inverse mapping",
            ),
            "placeholder property invariant": (
                complete.replace(
                    "An actor never observes another actor's protected resource.",
                    "PENDING",
                    1,
                ),
                "Invariant must be concrete semantic content",
            ),
            "sentinel property oracle": (
                complete.replace(
                    "Access allowed only when policy relation holds",
                    "NONE",
                    1,
                ),
                "Oracle must be concrete semantic content",
            ),
            "placeholder property layer": (
                complete.replace(
                    "Cross-tenant IDs, missing ownership, role changes | Integration |",
                    "Cross-tenant IDs, missing ownership, role changes | PLACEHOLDER |",
                    1,
                ),
                "Layer must be concrete semantic content",
            ),
            "placeholder exact command": (
                complete.replace(
                    "python -m unittest tests.test_properties",
                    "PENDING",
                    1,
                ),
                "Exact command must be one explicit local command",
            ),
            "prose exact command": (
                complete.replace(
                    "python -m unittest tests.test_properties",
                    "Run property tests",
                    1,
                ),
                "Exact command must be one explicit local command",
            ),
        }
        for label, (text, expected) in cases.items():
            with self.subTest(label=label):
                contract, contract_issues = doctor.derive_design_contract(text, "DES-0001")
                self.assertEqual(contract.status, "BLOCKED")
                self.assertIn(expected, "\n".join(contract_issues))

        no_applicable_properties = complete.replace(
            "| FR-001 | APPLICABLE | PROP-001 |",
            "| FR-001 | NOT_APPLICABLE | The requirement has no broad input space |",
            1,
        )
        no_applicable_properties = re.sub(
            r"(?m)^\| PROP-001 \|.*\|\r?\n?",
            "",
            no_applicable_properties,
        )
        no_applicable_properties = put_contract_table(
            no_applicable_properties,
            doctor.PROPERTY_EXECUTION_HEADING,
            "\n".join(
                [
                    "| Property ID | Framework TECH ID | Exact command | Run target/time bound | Seed or reproduction format | Evidence destination |",
                    "|---|---|---|---|---|---|",
                ]
            ),
            "Add workload-specific properties for:",
        )
        no_property_contract, no_property_issues = doctor.derive_design_contract(
            no_applicable_properties,
            "DES-0001",
        )
        self.assertEqual(no_property_issues, [])
        self.assertEqual(no_property_contract.status, "READY")

        shared_property = complete.replace(
            "| FR-002 | NOT_APPLICABLE | No stable generated-input oracle is approved for this requirement |",
            "| FR-002 | APPLICABLE | PROP-001 |",
            1,
        ).replace(
            "| PROP-001 | FR-001 |",
            "| PROP-001 | FR-001, FR-002 |",
            1,
        )
        shared_contract, shared_issues = doctor.derive_design_contract(
            shared_property,
            "DES-0001",
        )
        self.assertEqual(shared_issues, [])
        self.assertEqual(shared_contract.status, "READY")
        reversed_requirement_ids = shared_property.replace(
            "| PROP-001 | FR-001, FR-002 |",
            "| PROP-001 | FR-002, FR-001 |",
            1,
        )
        reversed_contract, reversed_issues = doctor.derive_design_contract(
            reversed_requirement_ids,
            "DES-0001",
        )
        self.assertEqual(reversed_contract.status, "BLOCKED")
        self.assertTrue(
            any(
                "Requirement IDs must exactly match" in issue
                for issue in reversed_issues
            )
        )
        self.assertEqual(no_property_contract.property_execution, ())

    def test_adaptive_coverage_select_amend_preserve_and_fail_closed(self) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        selected = complete_coverage_plan(template)
        contract, issues = doctor.derive_coverage_contract(
            selected,
            "REQ-0001",
            "quick-mvp",
            "low",
            "documentation-only",
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(issues, [])
        self.assertEqual(contract.architecture_disposition, "SELECT")
        self.assertEqual(contract.required_sections, doctor.COVERAGE_DOMAINS)

        requirement_ids = sorted(doctor.authoritative_requirement_ids(selected))
        basis_ids = ", ".join(["REQ-0001", *requirement_ids])
        preserved_sections = [
            item
            for item in doctor.COVERAGE_DOMAINS
            if item not in {"ARCHITECTURE_COMPARISON", "AWS_EVIDENCE"}
        ]
        preserve_table = "\n".join(
            [
                "| Work kind | Delivery profile | Architecture disposition | Required sections | Omitted sections and reasons | Basis IDs |",
                "|---|---|---|---|---|---|",
                "| BUGFIX | quick-mvp | PRESERVE | "
                + ", ".join(preserved_sections)
                + " | ARCHITECTURE_COMPARISON: ARCH-0001 remains unchanged; "
                "AWS_EVIDENCE: documentation-only repository fix uses REPOSITORY_BASELINE | "
                + basis_ids
                + " |",
            ]
        )
        preserved = put_contract_table(
            selected,
            doctor.COVERAGE_PLAN_HEADING,
            preserve_table,
            "## 1. Workload profile",
        )
        preserve_contract, preserve_issues = doctor.derive_coverage_contract(
            preserved,
            "REQ-0001",
            "quick-mvp",
            "low",
            "documentation-only",
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(preserve_issues, [])
        self.assertEqual(preserve_contract.architecture_disposition, "PRESERVE")

        amended = complete_coverage_plan(
            template, work_kind="FEATURE", disposition="AMEND"
        )
        amend_contract, amend_issues = doctor.derive_coverage_contract(
            amended,
            "REQ-0001",
            "quick-mvp",
            "low",
            "documentation-only",
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(amend_issues, [])
        self.assertEqual(amend_contract.architecture_disposition, "AMEND")

        unsafe_table = preserve_table.replace(
            "SECURITY_PRIVACY, ", "", 1
        ).replace(
            "ARCHITECTURE_COMPARISON:",
            "SECURITY_PRIVACY: SEC-001 is still material; ARCHITECTURE_COMPARISON:",
            1,
        )
        unsafe = put_contract_table(
            selected,
            doctor.COVERAGE_PLAN_HEADING,
            unsafe_table,
            "## 1. Workload profile",
        )
        blocked, blocked_issues = doctor.derive_coverage_contract(
            unsafe,
            "REQ-0001",
            "quick-mvp",
            "low",
            "documentation-only",
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertTrue(
            any("SECURITY_PRIVACY" in issue for issue in blocked_issues),
            blocked_issues,
        )

    def test_change_impact_is_design_bound_and_falls_back_to_full_revalidation(self) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        amended = complete_design_contract(template)
        amended = complete_coverage_plan(
            amended, work_kind="FEATURE", disposition="AMEND"
        )
        amended = replace_contract_table_with_sentinel(
            amended,
            doctor.FIRST_WAVE_HEADING,
            "FEATURE work does not define a greenfield walking skeleton",
        )
        amended = amended.replace(
            "DES-0001, FR-001, JOURNEY-001, WAVE-001",
            "DES-0001, FR-001",
            1,
        )
        impact_table = "\n".join(
            [
                "| Change ID | Changed basis IDs | Affected IDs | Preserved IDs | Required revalidation |",
                "|---|---|---|---|---|",
                "| CHANGE-0001 | FR-001 | ARCH-0001 | TECH-0001 | ARCH-0001 |",
            ]
        )
        amended = put_contract_table(
            amended,
            doctor.CHANGE_IMPACT_HEADING,
            impact_table,
            "## 14. Architecture overview",
        )
        contract, issues = doctor.derive_design_contract(
            amended, "DES-0001", required=True
        )
        self.assertEqual(issues, [])
        self.assertEqual(contract.change_impact.status, "READY")
        self.assertIn("GATE_A", contract.change_impact.stale_targets)
        original_digest = contract.canonical_sha256

        full_table = impact_table.replace(
            "| ARCH-0001 | TECH-0001 | ARCH-0001 |",
            "| ARCH-0001 | TECH-0001 | FULL_REVALIDATION |",
            1,
        )
        uncertain = put_contract_table(
            amended,
            doctor.CHANGE_IMPACT_HEADING,
            full_table,
            "## 14. Architecture overview",
        )
        full_contract, full_issues = doctor.derive_design_contract(
            uncertain, "DES-0001", required=True
        )
        self.assertEqual(full_issues, [])
        self.assertEqual(
            set(full_contract.change_impact.stale_targets),
            {"AWS_AUTHORITY", "GATE_A", "GATE_B", "TASKS"},
        )
        self.assertNotEqual(original_digest, full_contract.canonical_sha256)

        preserved = complete_coverage_plan(
            amended, work_kind="BUGFIX", disposition="PRESERVE"
        )
        invalid_preserve, invalid_issues = doctor.derive_design_contract(
            preserved, "DES-0001", required=True
        )
        self.assertEqual(invalid_preserve.status, "BLOCKED")
        self.assertTrue(
            any("PRESERVE cannot change architecture-controlled IDs" in issue for issue in invalid_issues),
            invalid_issues,
        )

    def test_context_plan_is_route_bounded_ephemeral_and_complete(self) -> None:
        tasks = doctor.TaskSummary(
            statuses={"TASK-0001": "IN_PROGRESS", "TASK-0002": "READY"},
            active=["TASK-0001"],
            ready=["TASK-0002"],
        )
        coverage = doctor.CoverageContract(
            status="READY",
            basis_ids=("REQ-0001", "FR-001"),
        )
        expected_reference = {
            "DEFINE": "references/define.md",
            "DESIGN": "references/design.md",
            "DELIVER": "references/deliver.md",
        }
        for stage, reference in expected_reference.items():
            with self.subTest(stage=stage):
                plan = doctor.derive_context_plan(
                    {
                        "owner_stage": stage,
                        "route_reason_code": "DESIGN_REQUIRED",
                        "blocking_ids": ["CURRENT_BLOCKER"],
                    },
                    tasks,
                    coverage,
                )
                self.assertEqual(plan["maximum_initial_bytes"], 12_000)
                self.assertTrue(any(reference in item for item in plan["source_slices"]))
                self.assertIn("CURRENT_BLOCKER", plan["active_ids"])
                self.assertEqual(len(plan["source_slices"]), len(set(plan["source_slices"])))

        aws_plan = doctor.derive_context_plan(
            {
                "owner_stage": "DELIVER",
                "route_reason_code": "AWS_PREFLIGHT_REQUIRED",
                "blocking_ids": [],
            },
            tasks,
            coverage,
        )
        self.assertTrue(
            any("Action authorization provenance" in item for item in aws_plan["source_slices"])
        )
        self.assertEqual(aws_plan["active_ids"], ["TASK-0001"])

        report = doctor.inspect_project(PROJECT_ROOT, template_source=True)
        resolved = report["context_plan"]
        self.assertEqual(resolved["maximum_initial_bytes"], 12_000)
        self.assertEqual(resolved["maximum_initial_source_bytes"], 12_000)
        self.assertEqual(resolved["budget_status"], "WITHIN_LIMIT")
        self.assertEqual(
            resolved["actual_initial_source_bytes"],
            sum(item["source_bytes"] for item in resolved["resolved_initial_slices"]),
        )
        self.assertLessEqual(resolved["actual_initial_source_bytes"], 12_000)
        self.assertEqual(resolved["overflow_records"], [])
        self.assertTrue(resolved["resolved_initial_slices"])
        for item in resolved["resolved_initial_slices"]:
            self.assertRegex(item["canonical_sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertGreaterEqual(item["start_line"], 1)
            self.assertGreaterEqual(item["end_line"], item["start_line"])

    def test_approved_schema_two_architecture_is_grandfathered_until_design_change(self) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(template)
        requirement_list = ", ".join(sorted(doctor.authoritative_requirement_ids(complete)))
        legacy_selection = "\n".join(
            [
                "| Architecture ID | Selected candidate | Requirement and driver basis | Rationale | Rejected alternatives | Risks | Mitigations | Cost effect | Breakpoints | Revisit triggers | Validation |",
                "|---|---|---|---|---|---|---|---|---|---|---|",
                f"| ARCH-0001 | CAND-0001 | {requirement_list}, DRV-0001 | Meets every hard constraint | CAND-0002 | Managed-service limits | Validate quotas and alarms | Pay per request | Reassess at sustained utilization | Reassess on quota changes | Requirement trace and integration tests |",
            ]
        )
        legacy = put_contract_table(
            complete,
            doctor.ARCHITECTURE_SELECTION_HEADING,
            legacy_selection,
            doctor.ARCHITECTURE_TRACEABILITY_HEADING,
        ).replace(
            "| Gate B derived status | `BLOCKED` |",
            "| Gate B derived status | `APPROVED_FOR_CONSTRUCTION` |",
            1,
        )

        grandfathered, issues = doctor.derive_design_contract(
            legacy,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(grandfathered.status, "READY")
        self.assertEqual(grandfathered.architecture.schema_version, 2)
        self.assertFalse(grandfathered.architecture.grandfathered_v1)

        invalidated, invalidated_issues = doctor.derive_design_contract(
            legacy.replace("Managed-service limits", "Changed risk", 1),
            "DES-0002",
            required=True,
            grandfather_approved_v1=False,
        )
        self.assertEqual(invalidated.status, "BLOCKED")
        self.assertTrue(
            any("Selected architecture" in issue for issue in invalidated_issues),
            invalidated_issues,
        )


    def test_architecture_contract_is_traceable_fail_closed_and_digest_bound(self) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(template)
        ready, issues = doctor.derive_design_contract(
            complete,
            "DES-0001",
            required=True,
        )

        self.assertEqual(issues, [])
        self.assertEqual(ready.status, "READY")
        self.assertEqual(ready.schema_version, 5)
        self.assertEqual(ready.architecture.schema_version, 4)
        self.assertEqual(ready.change_impact.status, "READY")
        self.assertEqual(ready.architecture.status, "READY")
        self.assertFalse(ready.architecture.grandfathered_v1)
        self.assertEqual(
            ready.architecture.selection.architecture_id,
            "ARCH-0001",
        )
        self.assertEqual(
            {item.capability for item in ready.architecture.aws_evidence},
            {"retrieve_skill", "search_documentation"},
        )
        self.assertRegex(
            ready.architecture.canonical_sha256 or "",
            r"^sha256:[0-9a-f]{64}$",
        )

        cases: dict[str, tuple[str, str]] = {
            "hard-constraint failure selected": (
                complete.replace(
                    "| ARCH-0001 | CAND-0001 |",
                    "| ARCH-0001 | CAND-0002 |",
                    1,
                ),
                "hard-constraint-failing candidate cannot be selected",
            ),
            "missing requirement trace": (
                re.sub(
                    r"(?m)^\| FR-001 \| ARCH-0001, COMP-0001 \|.*\r?\n",
                    "",
                    complete,
                    count=1,
                ),
                "Architecture traceability is missing requirement IDs: FR-001",
            ),
            "missing AWS Core capability": (
                re.sub(
                    r"(?m)^\| AWS-EV-0002 \|.*\r?\n",
                    "",
                    complete,
                    count=1,
                ),
                "Material AWS evidence is missing AWS Core capabilities: search_documentation",
            ),
            "candidate evidence is not bidirectionally bound": (
                complete.replace(
                    "DRV-0001, CAND-0001, CAND-0002, ARCH-0001, TECH-0001",
                    "DRV-0001, CAND-0002, ARCH-0001, TECH-0001",
                    1,
                ).replace(
                    "DRV-0001, CAND-0001, CAND-0002, ARCH-0001, TECH-0004",
                    "DRV-0001, CAND-0002, ARCH-0001, TECH-0004",
                    1,
                ),
                "CAND-0001: AWS evidence rows are not bound to this candidate",
            ),
            "selected architecture has no bound evidence": (
                complete.replace(
                    "CAND-0002, ARCH-0001, TECH-0001",
                    "CAND-0002, TECH-0001",
                    1,
                ).replace(
                    "CAND-0002, ARCH-0001, TECH-0004",
                    "CAND-0002, TECH-0004",
                    1,
                ),
                "Selected architecture has no bound material AWS evidence",
            ),
        }
        for name, (changed_text, expected_issue) in cases.items():
            with self.subTest(case=name):
                blocked, blocked_issues = doctor.derive_design_contract(
                    changed_text,
                    "DES-0001",
                    required=True,
                )
                self.assertEqual(blocked.status, "BLOCKED")
                self.assertTrue(
                    any(expected_issue in issue for issue in blocked_issues),
                    blocked_issues,
                )

        architecture_change = complete.replace(
            "Managed-service limits",
            "Service quota uncertainty",
            1,
        )
        changed, changed_issues = doctor.derive_design_contract(
            architecture_change,
            "DES-0001",
            required=True,
        )
        self.assertEqual(changed_issues, [])
        self.assertNotEqual(changed.canonical_sha256, ready.canonical_sha256)
        self.assertNotEqual(
            changed.architecture.canonical_sha256,
            ready.architecture.canonical_sha256,
        )

        legacy = exact_legacy_schema_four_projection(complete)
        grandfathered, grandfathered_issues = doctor.derive_design_contract(
            legacy,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(grandfathered_issues, [])
        self.assertEqual(grandfathered.status, "READY")
        self.assertEqual(grandfathered.schema_version, 4)
        self.assertFalse(grandfathered.architecture.grandfathered_v1)
        self.assertTrue(grandfathered.project_contract.grandfathered_v4)

        design_changed = legacy + "\n### State register\n"
        invalidated, invalidated_issues = doctor.derive_design_contract(
            design_changed,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(invalidated.status, "BLOCKED")
        self.assertTrue(
            any("Project design contract schema 5" in issue for issue in invalidated_issues),
            invalidated_issues,
        )

    def test_all_part_one_requirement_families_have_stable_ids(self) -> None:
        prd = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        identifiers = doctor.authoritative_requirement_ids(prd)
        expected = {
            *(f"DATA-{number:03d}" for number in range(1, 6)),
            *(f"PERF-{number:03d}" for number in range(1, 5)),
            *(f"COST-{number:03d}" for number in range(1, 6)),
            *(f"SUS-{number:03d}" for number in range(1, 5)),
            *(f"OPS-{number:03d}" for number in range(1, 6)),
        }
        self.assertTrue(expected.issubset(identifiers))
        for retired_bullet in (
            "- Latency target: TODO",
            "- Hard monthly ceiling: TODO",
            "- Infrastructure as code: TODO",
        ):
            self.assertNotIn(retired_bullet, prd)

    def test_design_contract_json_and_gate_b_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            self.approve_project(project)

            ready_report = doctor.inspect_project(project)
            contract = ready_report["design_contract"]
            self.assertTrue(ready_report["ok"], ready_report["diagnostics"])
            self.assertEqual(ready_report["status"], "RESUME")
            self.assertEqual(ready_report["next_prompt"], "TASK-10")
            self.assertEqual(contract["schema_version"], 5)
            self.assertEqual(
                ready_report["requirements_contract"]["schema_version"], "1.3"
            )
            self.assertEqual(ready_report["requirements_contract"]["status"], "READY")
            self.assertEqual(contract["project_contract"]["status"], "READY")
            self.assertEqual(contract["project_contract"]["first_wave"]["wave_contract_id"], "WAVE-001")
            self.assertEqual(ready_report["coverage_plan"]["status"], "READY")
            self.assertEqual(contract["change_impact"]["status"], "READY")
            self.assertEqual(contract["status"], "READY")
            self.assertEqual(contract["design_revision"], "DES-0001")
            self.assertTrue(ready_report["write_authority"]["valid"])
            self.assertEqual(
                ready_report["write_authority"]["approved_write_roots"],
                ["app/**", "tests/**"],
            )
            self.assertEqual(
                ready_report["write_authority"]["exclusions"],
                ["docs/project/PRD.md", "bootstrap.yaml"],
            )
            self.assertEqual(ready_report["external_authority"]["kind"], "NONE")
            self.assertEqual(len(contract["technology_decisions"]), 9)
            self.assertEqual(contract["technology_decisions"][6]["concern"], "PROPERTY_TESTING")
            self.assertEqual(contract["property_execution"][0]["framework_tech_id"], "TECH-0007")
            self.assertRegex(contract["canonical_sha256"], r"^sha256:[0-9a-f]{64}$")

            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8").replace(
                "| PROP-001 | TECH-0007 | python -m unittest tests.test_properties |",
                "| PROP-001 | TECH-0006 | python -m unittest tests.test_properties |",
                1,
            )
            prd_path.write_text(text, encoding="utf-8")
            blocked_report = doctor.inspect_project(project)

        self.assertFalse(blocked_report["ok"])
        self.assertEqual(blocked_report["status"], "BLOCKED")
        self.assertIn("DESIGN_CONTRACT_INVALID", codes(blocked_report))
        self.assertEqual(blocked_report["design_contract"]["status"], "BLOCKED")
        self.assertEqual(blocked_report["gates"]["gate_b"], "APPROVED_FOR_CONSTRUCTION")
        self.assertEqual(blocked_report["next_prompt"], "STOP")

    def test_exact_deployment_receipt_projects_current_external_authority(self) -> None:
        verify_text = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        receipt = "\n".join(
            [
                "AUTHORIZE AWS DEPLOYMENT",
                "AWS authorization: AWS-AUTH-0001",
                "Construction authorization: AUTH-0001",
                "Profile or role: fastlane-deployment-role",
                "Account: 111122223333",
                "Region: us-west-2",
                "Environment: development",
                "Artifact digest: sha256:" + "a" * 64,
                "IaC plan/change-set binding: TYPE: CLOUDFORMATION_CHANGE_SET; "
                "IDENTIFIER: canary-change-set; DIGEST: sha256:" + "b" * 64,
                "Stack, application, and resources: fastlane-stack",
                "Allowed operations: cloudformation:CreateChangeSet, "
                "cloudformation:ExecuteChangeSet",
                "Cost ceiling: USD: 20.00",
                "Rollback boundary: rollback fastlane-stack",
                "Valid until: 2099-01-01T00:00:00Z",
                "Approver: alice",
            ]
        )
        receipt_digest = "sha256:" + hashlib.sha256(
            receipt.encode("utf-8")
        ).hexdigest()
        verify_text = set_receipt(verify_text, "aws-deployment", receipt)
        lines = verify_text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if line.startswith("| Deployment | TODO |"):
                suffix = "\n" if line.endswith("\n") else ""
                lines[index] = (
                    "| Deployment | AWS-AUTH-0001 | AUTH-0001 | "
                    "fastlane-deployment-role | sha256:" + "a" * 64
                    + " | TYPE: CLOUDFORMATION_CHANGE_SET; IDENTIFIER: "
                    "canary-change-set; DIGEST: sha256:" + "b" * 64
                    + " | ACCOUNT: 111122223333; REGION: us-west-2; "
                    "ENVIRONMENT: development | RESOURCES: fastlane-stack; "
                    "OPERATIONS: cloudformation:CreateChangeSet, "
                    "cloudformation:ExecuteChangeSet | COST: USD: 20.00; "
                    "VALID_UNTIL: 2099-01-01T00:00:00Z | "
                    "rollback fastlane-stack | owner-message MSG-AWS-0001 | "
                    "alice | 2027-01-01T00:00:00Z | "
                    + receipt_digest
                    + " | AWS-PREFLIGHT-0001 | PASS | READY |"
                    + suffix
                )
                break
        else:
            self.fail("Deployment authorization provenance row not found")
        envelope = aws_authority_envelope(
            role="fastlane-deployment-role",
            account="111122223333",
            region="us-west-2",
            environment="development",
            resources=["fastlane-stack"],
            operations=[
                "cloudformation:CreateChangeSet",
                "cloudformation:ExecuteChangeSet",
            ],
            artifact="sha256:" + "a" * 64,
            rollback="rollback fastlane-stack",
        )
        preflight = ready_preflight(
            account="111122223333",
            region="us-west-2",
            environment="development",
        )
        authority = doctor._receipt_external_authority(
            "".join(lines),
            "Deployment",
            "AUTH-0001",
            envelope=envelope,
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            active_artifact="sha256:" + "a" * 64,
            preflight=preflight,
        )

        self.assertIsNotNone(authority)
        self.assertEqual(authority["kind"], "AWS_DEPLOYMENT")
        self.assertEqual(authority["validity"], "CURRENT")
        self.assertEqual(authority["authorization_id"], "AWS-AUTH-0001")
        self.assertEqual(authority["receipt_digest"], receipt_digest)
        self.assertEqual(authority["account"], "111122223333")
        self.assertEqual(authority["region"], "us-west-2")
        self.assertEqual(authority["environment"], "development")
        self.assertEqual(authority["role_or_profile"], "fastlane-deployment-role")
        self.assertEqual(authority["resources"], ["fastlane-stack"])
        self.assertEqual(
            authority["operations"],
            [
                "cloudformation:CreateChangeSet",
                "cloudformation:ExecuteChangeSet",
            ],
        )
        self.assertEqual(authority["cost_ceiling"], "USD: 20.00")
        self.assertEqual(authority["rollback_boundary"], "rollback fastlane-stack")
        self.assertEqual(authority["expiration"], "2099-01-01T00:00:00Z")

        ctx = doctor.Context(Path("."))
        ctx.texts[doctor.VERIFY_FILE] = "".join(lines)
        request_match = doctor.derive_request_match(ctx, authority)
        self.assertEqual(request_match["schema_version"], 1)
        self.assertEqual(request_match["authority_kind"], "AWS_DEPLOYMENT")
        self.assertEqual(request_match["account"], "111122223333")
        self.assertEqual(request_match["region"], "us-west-2")
        self.assertEqual(request_match["resources"], ["fastlane-stack"])
        self.assertEqual(
            request_match["operations"],
            [
                "cloudformation:CreateChangeSet",
                "cloudformation:ExecuteChangeSet",
            ],
        )
        self.assertEqual(
            request_match["cost_ceiling"],
            {"currency": "USD", "amount": "20.00"},
        )
        self.assertEqual(request_match["allowed_execution_lanes"], ["STRUCTURED_API"])
        self.assertIsNone(request_match["reviewed_script"])

        nonhuman_receipt = receipt.replace("Approver: alice", "Approver: Codex")
        nonhuman_digest = "sha256:" + hashlib.sha256(
            nonhuman_receipt.encode("utf-8")
        ).hexdigest()
        nonhuman = set_receipt("".join(lines), "aws-deployment", nonhuman_receipt)
        nonhuman = nonhuman.replace(
            " | alice | 2027-01-01T00:00:00Z | ",
            " | Codex | 2027-01-01T00:00:00Z | ",
            1,
        ).replace(receipt_digest, nonhuman_digest, 1)
        self.assertIsNone(
            doctor._receipt_external_authority(
                nonhuman,
                "Deployment",
                "AUTH-0001",
                envelope=envelope,
                cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
                active_artifact="sha256:" + "a" * 64,
                preflight=preflight,
            )
        )

    def test_reviewed_script_contract_is_exact_current_and_fail_closed(self) -> None:
        verify_template = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        authority = {
            "kind": "AWS_DEPLOYMENT",
            "validity": "CURRENT",
            "authorization_id": "AWS-AUTH-0001",
            "receipt_digest": "sha256:" + "c" * 64,
            "account": "111122223333",
            "region": "us-west-2",
            "environment": "development",
            "role_or_profile": "fastlane-deployment-role",
            "resources": ["fastlane-stack"],
            "operations": [
                "cloudformation:CreateChangeSet",
                "cloudformation:ExecuteChangeSet",
            ],
            "artifact_plan_binding": {
                "artifact": "sha256:" + "a" * 64,
                "plan": "TYPE: CLOUDFORMATION_CHANGE_SET; IDENTIFIER: canary; "
                "DIGEST: sha256:" + "b" * 64,
            },
            "cost_ceiling": "USD: 20.00",
            "rollback_boundary": "rollback fastlane-stack",
            "expiration": "2099-01-01T00:00:00Z",
        }
        row = (
            "| AWS-EXEC-0001 | AWS_DEPLOYMENT | AWS-AUTH-0001 | sha256:"
            + "c" * 64
            + " | sha256:"
            + "d" * 64
            + " | NONE | cloudformation:CreateChangeSet | fastlane-stack | "
            "111122223333 | us-west-2 | development | fastlane-deployment-role | "
            "sha256:"
            + "a" * 64
            + " | TYPE: CLOUDFORMATION_CHANGE_SET; IDENTIFIER: canary; DIGEST: sha256:"
            + "b" * 64
            + " | USD: 20.00 | rollback fastlane-stack | 2099-01-01T00:00:00Z | "
            "EV-0601 | CURRENT |"
        )

        def with_rows(*rows: str) -> str:
            lines = verify_template.splitlines()
            heading = lines.index("## Reviewed AWS execution contracts")
            data_index = next(
                index
                for index in range(heading + 1, len(lines))
                if lines[index].startswith("| TODO | TODO |")
            )
            lines[data_index : data_index + 1] = list(rows)
            return "\n".join(lines) + "\n"

        ctx = doctor.Context(Path("."))
        ctx.texts[doctor.VERIFY_FILE] = with_rows(row)
        request_match = doctor.derive_request_match(ctx, authority)
        self.assertEqual(
            request_match["allowed_execution_lanes"],
            ["STRUCTURED_API", "REVIEWED_SCRIPT"],
        )
        reviewed = request_match["reviewed_script"]
        self.assertEqual(reviewed["execution_id"], "AWS-EXEC-0001")
        self.assertEqual(reviewed["content_binding"]["kind"], "SCRIPT_SHA256")
        self.assertEqual(reviewed["evidence_destination"], "EV-0601")
        self.assertEqual(ctx.diagnostics, [])

        invalid_rows = {
            "mismatched authority": row.replace(
                "AWS-AUTH-0001 | sha256:", "AWS-AUTH-9999 | sha256:", 1
            ),
            "expired": row.replace(
                "2099-01-01T00:00:00Z | EV-0601",
                "2000-01-01T00:00:00Z | EV-0601",
            ),
            "unbound": row.replace("| sha256:" + "d" * 64 + " | NONE |", "| NONE | NONE |"),
        }
        for label, invalid_row in invalid_rows.items():
            with self.subTest(label=label):
                invalid_ctx = doctor.Context(Path("."))
                invalid_ctx.texts[doctor.VERIFY_FILE] = with_rows(invalid_row)
                invalid_match = doctor.derive_request_match(invalid_ctx, authority)
                self.assertEqual(invalid_match["allowed_execution_lanes"], ["STRUCTURED_API"])
                self.assertIsNone(invalid_match["reviewed_script"])
                self.assertTrue(
                    any(item.code == "AWS_EXECUTION_CONTRACT_INVALID" for item in invalid_ctx.diagnostics)
                )

        duplicate_ctx = doctor.Context(Path("."))
        duplicate_ctx.texts[doctor.VERIFY_FILE] = with_rows(row, row)
        duplicate_match = doctor.derive_request_match(duplicate_ctx, authority)
        self.assertEqual(duplicate_match["allowed_execution_lanes"], ["STRUCTURED_API"])
        self.assertIsNone(duplicate_match["reviewed_script"])

    def test_gate_b_binds_live_design_contract_hash_and_required_scope_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8").replace(
                "| TECH-0007 | PROPERTY_TESTING | Hypothesis |",
                "| TECH-0007 | PROPERTY_TESTING | Hypothesis 7 |",
                1,
            )
            prd_path.write_text(text, encoding="utf-8")
            stale_hash_report = doctor.inspect_project(project)

        self.assertFalse(stale_hash_report["ok"])
        self.assertIn("GATE_B_DESIGN_CONTRACT_HASH", codes(stale_hash_report))
        self.assertEqual(stale_hash_report["next_prompt"], "STOP")

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8").replace(
                "Managed-service limits",
                "Service quota uncertainty",
                1,
            )
            prd_path.write_text(text, encoding="utf-8")
            stale_architecture_report = doctor.inspect_project(project)

        self.assertFalse(stale_architecture_report["ok"])
        self.assertIn(
            "GATE_B_DESIGN_CONTRACT_HASH",
            codes(stale_architecture_report),
        )
        self.assertEqual(stale_architecture_report["next_prompt"], "STOP")

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8").replace(
                ", PROP-001, HARNESS-004",
                ", HARNESS-004",
                1,
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            missing_scope_report = doctor.inspect_project(project)

        self.assertFalse(missing_scope_report["ok"])
        self.assertIn("GATE_B_ENVELOPE", codes(missing_scope_report))
        self.assertTrue(
            any(
                "missing current design contract IDs: PROP-001" in diagnostic["message"]
                for diagnostic in missing_scope_report["diagnostics"]
            )
        )

    def test_gate_b_readiness_card_exactly_enumerates_current_technology_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "### Gate B — readiness card",
                "## 28. Construction envelope",
                "Technology/toolchains/version policy",
                "`TECH-0001, TECH-0002, TECH-0003`",
            )
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("GATE_B_READINESS_CARD", codes(report))
        self.assertTrue(
            any(
                "must exactly enumerate the current technology decision IDs"
                in diagnostic["message"]
                for diagnostic in report["diagnostics"]
            )
        )

    def test_doctor_does_not_mutate_project(self) -> None:
        before = {
            path.relative_to(PROJECT_ROOT): (
                path.read_bytes(),
                path.stat().st_mode,
                path.stat().st_mtime_ns,
            )
            for path in PROJECT_ROOT.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }

        doctor.inspect_project(PROJECT_ROOT, template_source=True)

        after = {
            path.relative_to(PROJECT_ROOT): (
                path.read_bytes(),
                path.stat().st_mode,
                path.stat().st_mtime_ns,
            )
            for path in PROJECT_ROOT.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertEqual(after, before)

    @source_template_only
    def test_active_project_rejects_unresolved_placeholders(self) -> None:
        report = doctor.inspect_project(PROJECT_ROOT)

        self.assertFalse(report["ok"])
        self.assertIn("PLACEHOLDER_UNRESOLVED", codes(report))
        self.assertEqual(report["next_prompt"], "STOP")

    def test_missing_manifest_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            (project / "docs/project/PRD.md").unlink()

            report = doctor.inspect_project(project)

        self.assertIn("REQUIRED_FILE_MISSING", codes(report))
        self.assertFalse(report["resume_safe"])

    def test_required_file_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.copy_project(root)
            outside = root / "outside.md"
            outside.write_text("not a PRD", encoding="utf-8")
            (project / "docs/project/PRD.md").unlink()
            try:
                os.symlink(outside, project / "docs/project/PRD.md")
            except OSError as exc:
                self.skipTest(f"Symbolic links unavailable: {exc}")

            report = doctor.inspect_project(project)

        self.assertIn("REQUIRED_FILE_SYMLINK", codes(report))

    def test_state_prd_revision_drift_stops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            path = project / "bootstrap.yaml"
            state = json.loads(path.read_text(encoding="utf-8"))
            state["lifecycle"]["requirements_revision"] = "REQ-0002"
            path.write_text(json.dumps(state), encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("STATE_PRD_DRIFT", codes(report))
        self.assertEqual(report["next_prompt"], "STOP")

    def test_high_risk_requires_high_risk_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"].update(
                {
                    "mode": "greenfield",
                    "delivery_profile": "quick-mvp",
                    "effective_risk": "high",
                    "aws_lane": "explicit-gate",
                    "brownfield_baseline": "NOT_APPLICABLE",
                }
            )
            state_path.write_text(json.dumps(state), encoding="utf-8")
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            for field, value in {
                "Project mode": "`greenfield`",
                "Delivery profile": "`quick-mvp`",
                "Effective risk": "`high`",
                "AWS lane": "`explicit-gate`",
            }.items():
                text = set_table_value(
                    text, "## Document status", "## 1. Workload profile", field, value
                )
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("PROJECT_RISK_PROFILE", codes(report))

    def test_persisted_running_state_is_not_safe_to_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            path = project / "bootstrap.yaml"
            state = json.loads(path.read_text(encoding="utf-8"))
            state["execution"]["state"] = "RUNNING"
            path.write_text(json.dumps(state), encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("RUN_UNCLEAN_INTERRUPTION", codes(report))
        self.assertEqual(report["next_prompt"], "STOP")

    def test_exact_approved_receipts_route_uninitialized_plan_to_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)

            report = doctor.inspect_project(project)

        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["next_prompt"], "TASK-10")

    def test_altered_approved_gate_b_receipt_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            text = text.replace("Approver: alice\n```\n<!-- bootstrap:gate-b", "Approver: mallory\n```\n<!-- bootstrap:gate-b")
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("GATE_B_RECEIPT_MISMATCH", codes(report))

    def test_task_dependency_cycle_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["execution"]["plan_revision"] = "PLAN-0001"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            tasks_path = project / "docs/project/TASKS.md"
            text = tasks_path.read_text(encoding="utf-8").replace(
                "| Task-plan revision | `UNINITIALIZED` |",
                "| Task-plan revision | `PLAN-0001` |",
            )
            text += """

### TASK-001 — First

- Status: `READY`
- Depends on: `TASK-002`

### TASK-002 — Second

- Status: `READY`
- Depends on: `TASK-001`
"""
            tasks_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("TASK_GRAPH_INVALID", codes(report))

    def test_doctor_never_executes_project_task_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            sentinel = Path(directory) / "executed"
            (project / "scripts" / "task_waves.py").write_text(
                f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\nraise RuntimeError('executed')\n",
                encoding="utf-8",
            )

            report = doctor.inspect_project(project)
            executed = sentinel.exists()

        self.assertFalse(report["ok"])
        self.assertIn("CONTROL_HASH_MISMATCH", codes(report))
        self.assertFalse(executed)

    def test_fenced_fake_task_is_not_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            tasks_path = project / "docs/project/TASKS.md"
            tasks_path.write_text(
                tasks_path.read_text(encoding="utf-8")
                + """
```markdown
### TASK-999 — This is documentation, not a task
- Status: `IN_PROGRESS`
- Depends on: `TASK-999`
```
""",
                encoding="utf-8",
            )

            report = doctor.inspect_project(project)

        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["tasks"]["total"], 0)

    def test_fenced_prd_tables_cannot_shadow_authoritative_structure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            fake = """```markdown
## 28. Construction envelope

| Field | Authorized boundary |
|---|---|
| Authorized baseline commit | `ffffffffffffffffffffffffffffffffffffffff` |
```

"""
            prd_path.write_text(
                fake + prd_path.read_text(encoding="utf-8"), encoding="utf-8"
            )

            report = doctor.inspect_project(project)

        self.assertNotIn("PRD_STRUCTURE", codes(report))
        self.assertNotIn("GATE_B_ENVELOPE_HASH", codes(report))

    def test_write_boundaries_reject_git_directory_case_insensitively(self) -> None:
        for value in (".git/config", ".GIT/config", "app/.Git/index"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                doctor.parse_task_write_set(value, "TASK-001")

    def test_embedded_task_parser_enforces_key_task_invariants(self) -> None:
        snapshot = {
            "Requirements revision": "REQ-0001",
            "Design revision": "DES-0001",
            "Construction authorization": "AUTH-0001",
            "Gate B state": "APPROVED_FOR_CONSTRUCTION",
            "Run state": "NOT_STARTED",
            "Active run ID": "NONE",
        }
        ledger = (PROJECT_ROOT / "docs/project/TASKS.md").read_text(encoding="utf-8")
        task = ready_task()
        cases = {
            "duplicate singleton metadata": ledger + task.replace(
                "- Status: `READY`", "- Status: `READY`\n- Status: `READY`", 1
            ),
            "stale execution basis": ledger + task.replace("REQ-0001; FR-001", "REQ-9999; FR-001", 1),
            "missing objective section": ledger + task.replace("#### Validation", "#### Checks", 1),
            "ambiguous external target": ledger + task.replace(
                "- External state: `NONE`", "- External state: `aws:*`", 1
            ),
            "fenced heading cannot satisfy section": ledger
            + task.replace("#### Outcome", "#### Summary", 1).replace(
                "python -m unittest", "#### Outcome\nFake fenced heading\npython -m unittest", 1
            ),
        }
        for label, text in cases.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                doctor.validate_task_records(text, snapshot)

    def test_embedded_task_parser_enforces_approved_technology_trace(self) -> None:
        snapshot = {
            "Requirements revision": "REQ-0001",
            "Design revision": "DES-0001",
            "Construction authorization": "AUTH-0001",
            "Gate B state": "APPROVED_FOR_CONSTRUCTION",
            "Task-plan state": "CURRENT",
            "Run state": "NOT_STARTED",
            "Active run ID": "NONE",
        }
        ledger = (PROJECT_ROOT / "docs/project/TASKS.md").read_text(encoding="utf-8")
        approved = ledger + ready_task(design="DES-0001; TECH: TECH-0001")
        tasks, _by_id, ready = doctor.validate_task_records(
            approved,
            snapshot,
            approved_tech_ids={"TECH-0001"},
        )
        self.assertEqual([task.task_id for task in tasks], ["TASK-001"])
        self.assertEqual(ready, ["TASK-001"])

        unapproved = ledger + ready_task(design="DES-0001; TECH: TECH-9999")
        with self.assertRaisesRegex(ValueError, "unapproved TECH IDs: TECH-9999"):
            doctor.validate_task_records(
                unapproved,
                snapshot,
                approved_tech_ids={"TECH-0001"},
            )

        malformed = ledger + ready_task(design="DES-0001; TECH: TECH-0001,TECH-0002")
        with self.assertRaisesRegex(ValueError, "Design must exactly match"):
            doctor.validate_task_records(
                malformed,
                snapshot,
                approved_tech_ids={"TECH-0001", "TECH-0002"},
            )

    def test_task_property_projection_is_exact_for_every_executable_status(self) -> None:
        snapshot = {
            "Requirements revision": "REQ-0001",
            "Design revision": "DES-0001",
            "Construction authorization": "AUTH-0001",
            "Gate B state": "APPROVED_FOR_CONSTRUCTION",
            "Task-plan state": "CURRENT",
            "Run state": "NOT_STARTED",
            "Active run ID": "NONE",
        }
        ledger = (PROJECT_ROOT / "docs/project/TASKS.md").read_text(encoding="utf-8")
        prd = complete_design_contract(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        contract, issues = doctor.derive_design_contract(prd, "DES-0001", required=True)
        self.assertEqual(issues, [])
        executions = {item.property_id: item for item in contract.property_execution}
        technologies = {
            item.decision_id: item for item in contract.technology_decisions
        }
        task = ready_task(
            requirements="REQ-0001; FR-001; PROP-001",
            design="DES-0001; TECH: TECH-0001, TECH-0007",
            command="python -m unittest tests.test_properties",
            property_projection=property_execution_projection(),
        )
        doctor.validate_task_records(
            ledger + task,
            snapshot,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            property_execution_by_id=executions,
            technology_decisions_by_id=technologies,
        )

        running = (
            task.replace("- Status: `READY`", "- Status: `IN_PROGRESS`", 1)
            .replace("- Owner: `UNASSIGNED`", "- Owner: `alice`", 1)
            .replace("- Run ID: `NONE`", "- Run ID: `RUN-0001`", 1)
            .replace("- Attempts used: `0`", "- Attempts used: `1`", 1)
            .replace("- Last checkpoint: `NONE`", "- Last checkpoint: `CP-0001`", 1)
        )
        running_snapshot = dict(snapshot)
        running_snapshot.update({"Run state": "RUNNING", "Active run ID": "RUN-0001"})
        doctor.validate_task_records(
            ledger + running,
            running_snapshot,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            property_execution_by_id=executions,
        )

        done = (
            task.replace("- Status: `READY`", "- Status: `DONE`", 1)
            .replace("- Evidence: `NONE`", "- Evidence: `EV-0001`", 1)
            .replace("- [ ]", "- [x]", 1)
            .replace(
                "Not started.",
                "2026-07-17T12:00:00-07:00 coordinator observed validation pass.",
                1,
            )
        )
        verify = """## Task completion evidence

| Evidence ID | Task | Command or observation | Result | Actor | Observed at | Commit / worktree / artifact | Durable source | Status |
|---|---|---|---|---|---|---|---|---|
| EV-0001 | TASK-001 | python -m unittest tests.test_properties | passed | alice | 2026-07-17T12:00:00-07:00 | commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa | docs/project/VERIFY.md#ev-0001 | LOCAL_PASS |
""" + "\n" + property_test_evidence_section()
        doctor.validate_task_records(
            ledger + done,
            snapshot,
            verify,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            property_execution_by_id=executions,
            technology_decisions_by_id=technologies,
        )

        invalid_cases = {
            "requires the exact property execution projection": ready_task(
                requirements="REQ-0001; FR-001; PROP-001",
                design="DES-0001; TECH: TECH-0001, TECH-0007",
                command="python -m unittest tests.test_properties",
            ),
            "does not match the PRD contract": task.replace(
                "MIN_CASES: 100; MAX_SECONDS: 30",
                "MIN_CASES: 100; MAX_SECONDS: 31",
                1,
            ),
            "must appear exactly once": task.replace(
                "python -m unittest tests.test_properties\n```",
                "python -m unittest tests.test_properties\npython -m unittest tests.test_properties\n```",
                1,
            ),
        }
        for expected, invalid in invalid_cases.items():
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                doctor.validate_task_records(
                    ledger + invalid,
                    snapshot,
                    approved_tech_ids={"TECH-0001", "TECH-0007"},
                    property_execution_by_id=executions,
                )

        prose_expected = doctor.PropertyExecution(
            "PROP-001",
            "TECH-0007",
            "Run property tests",
            "MIN_CASES: 100; MAX_SECONDS: 30",
            "integer seed; reproduce with the recorded --seed value",
            "docs/project/VERIFY.md#property-based-test-evidence",
        )
        prose_projection = property_execution_projection().replace(
            "python -m unittest tests.test_properties",
            "Run property tests",
        )
        with self.assertRaisesRegex(ValueError, "not an executable local command"):
            doctor.validate_task_records(
                ledger
                + ready_task(
                    requirements="REQ-0001; FR-001; PROP-001",
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    command="Run property tests",
                    property_projection=prose_projection,
                ),
                snapshot,
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                property_execution_by_id={"PROP-001": prose_expected},
            )

    def test_done_property_task_requires_exact_observed_property_evidence(self) -> None:
        snapshot = {
            "Requirements revision": "REQ-0001",
            "Design revision": "DES-0001",
            "Construction authorization": "AUTH-0001",
            "Gate B state": "APPROVED_FOR_CONSTRUCTION",
            "Task-plan state": "CURRENT",
            "Run state": "NOT_STARTED",
            "Active run ID": "NONE",
        }
        ledger = (PROJECT_ROOT / "docs/project/TASKS.md").read_text(encoding="utf-8")
        prd = complete_design_contract(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        contract, issues = doctor.derive_design_contract(prd, "DES-0001", required=True)
        self.assertEqual(issues, [])
        executions = {item.property_id: item for item in contract.property_execution}
        technologies = {
            item.decision_id: item for item in contract.technology_decisions
        }
        done = (
            ready_task(
                requirements="REQ-0001; FR-001; PROP-001",
                design="DES-0001; TECH: TECH-0001, TECH-0007",
                command="python -m unittest tests.test_properties",
                property_projection=property_execution_projection(),
            )
            .replace("- Status: `READY`", "- Status: `DONE`", 1)
            .replace("- Evidence: `NONE`", "- Evidence: `EV-0001`", 1)
            .replace("- [ ]", "- [x]", 1)
            .replace(
                "Not started.",
                "2026-07-17T12:00:00-07:00 coordinator observed validation pass.",
                1,
            )
        )
        task_evidence = task_completion_evidence_section()
        valid_verify = task_evidence + "\n" + property_test_evidence_section()
        doctor.validate_task_records(
            ledger + done,
            snapshot,
            valid_verify,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            property_execution_by_id=executions,
            technology_decisions_by_id=technologies,
        )

        invalid_cases = {
            "Property-based test evidence section": task_evidence,
            "Exact command does not match": task_evidence
            + "\n"
            + property_test_evidence_section(exact_command="python -m unittest wrong"),
            "observed exact version does not satisfy": task_evidence
            + "\n"
            + property_test_evidence_section(observed_version="latest"),
            "observed exact version does not satisfy MINIMUM": task_evidence
            + "\n"
            + property_test_evidence_section(observed_version="6.0rc1"),
            "Observed run must be": task_evidence
            + "\n"
            + property_test_evidence_section(observed_run="TODO"),
            "replay evidence does not match the approved PRD": task_evidence
            + "\n"
            + property_test_evidence_section(replay="random replay token"),
            "PASS must record Minimized counterexample as NONE": task_evidence
            + "\n"
            + property_test_evidence_section(counterexample="user_id=''"),
            "durable source is not a local durable reference": task_evidence
            + "\n"
            + property_test_evidence_section(source="observed by the coordinator"),
        }
        for expected, verify_text in invalid_cases.items():
            with self.subTest(expected=expected), self.assertRaisesRegex(
                ValueError, expected
            ):
                doctor.validate_task_records(
                    ledger + done,
                    snapshot,
                    verify_text,
                    approved_tech_ids={"TECH-0001", "TECH-0007"},
                    property_execution_by_id=executions,
                    technology_decisions_by_id=technologies,
                )

        for replay in ("seed unavailable", "seed: unavailable", "seed: abc"):
            with self.subTest(replay=replay), self.assertRaisesRegex(
                ValueError,
                "replay evidence does not match the approved PRD",
            ):
                doctor.validate_task_records(
                    ledger + done,
                    snapshot,
                    task_evidence
                    + "\n"
                    + property_test_evidence_section(replay=replay),
                    approved_tech_ids={"TECH-0001", "TECH-0007"},
                    property_execution_by_id=executions,
                    technology_decisions_by_id=technologies,
                )

        failure_material = "commit: " + "b" * 40
        failure_source = "tests/artifacts/property-PROP-001-failure.json"
        failure_then_pass = (
            task_completion_evidence_section(
                (
                    "EV-0002",
                    "python -m unittest tests.test_properties",
                    "2026-07-17T11:00:00-07:00",
                    failure_material,
                    failure_source,
                    "FAILED",
                ),
                (
                    "EV-0001",
                    "python -m unittest tests.test_properties",
                    "2026-07-17T12:00:00-07:00",
                    "commit: " + "a" * 40,
                    "docs/project/VERIFY.md#ev-0001",
                    "LOCAL_PASS",
                ),
            )
            + "\n"
            + property_test_evidence_section(
                evidence_id="EV-0002",
                result="FAIL",
                observed_at="2026-07-17T11:00:00-07:00",
                material=failure_material,
                counterexample="user_id=''",
                failure=(
                    "IMPLEMENTATION_DEFECT — corrected input normalization; "
                    "evidence EV-0002"
                ),
                source=failure_source,
            )
            + "\n"
            + property_test_evidence_row(evidence_id="EV-0001")
        )
        doctor.validate_task_records(
            ledger + done,
            snapshot,
            failure_then_pass,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            property_execution_by_id=executions,
            technology_decisions_by_id=technologies,
        )

        failure_only_source = "tests/artifacts/property-PROP-001-open-failure.json"
        failure_only_material = "commit: " + "d" * 40
        failure_only = (
            task_completion_evidence_section(
                (
                    "EV-0001",
                    "python -m unittest tests.test_properties",
                    "2026-07-17T12:00:00-07:00",
                    "commit: " + "a" * 40,
                    "docs/project/VERIFY.md#ev-0001",
                    "LOCAL_PASS",
                ),
                (
                    "EV-0002",
                    "python -m unittest tests.test_properties",
                    "2026-07-17T13:00:00-07:00",
                    failure_only_material,
                    failure_only_source,
                    "FAILED",
                ),
            )
            + "\n"
            + property_test_evidence_section(
                evidence_id="EV-0002",
                result="FAIL",
                observed_at="2026-07-17T13:00:00-07:00",
                material=failure_only_material,
                counterexample="user_id=''",
                failure="IMPLEMENTATION_DEFECT — correction remains open",
                source=failure_only_source,
            )
        )
        with self.assertRaisesRegex(ValueError, "requires preserved failure rows"):
            doctor.validate_task_records(
                ledger + done,
                snapshot,
                failure_only,
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                property_execution_by_id=executions,
                technology_decisions_by_id=technologies,
            )

        later_failure_material = "commit: " + "c" * 40
        later_failure_source = "tests/artifacts/property-PROP-001-latest-failure.json"
        pass_then_failure = (
            task_completion_evidence_section(
                (
                    "EV-0001",
                    "python -m unittest tests.test_properties",
                    "2026-07-17T12:00:00-07:00",
                    "commit: " + "a" * 40,
                    "docs/project/VERIFY.md#ev-0001",
                    "LOCAL_PASS",
                ),
                (
                    "EV-0002",
                    "python -m unittest tests.test_properties",
                    "2026-07-17T13:00:00-07:00",
                    later_failure_material,
                    later_failure_source,
                    "FAILED",
                ),
            )
            + "\n"
            + property_test_evidence_section()
            + "\n"
            + property_test_evidence_row(
                evidence_id="EV-0002",
                result="FAIL",
                observed_at="2026-07-17T13:00:00-07:00",
                material=later_failure_material,
                replay="seed: 99999",
                counterexample="user_id=''",
                failure="IMPLEMENTATION_DEFECT — a new regression remains open",
                source=later_failure_source,
            )
        )
        with self.assertRaisesRegex(ValueError, "latest observed property-test result"):
            doctor.validate_task_records(
                ledger + done,
                snapshot,
                pass_then_failure,
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                property_execution_by_id=executions,
                technology_decisions_by_id=technologies,
            )

        duplicate_property_evidence = (
            valid_verify + "\n" + property_test_evidence_row(evidence_id="EV-0001")
        )
        with self.assertRaisesRegex(
            ValueError,
            "Property-based test evidence Evidence IDs must be unique",
        ):
            doctor.validate_task_records(
                ledger + done,
                snapshot,
                duplicate_property_evidence,
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                property_execution_by_id=executions,
                technology_decisions_by_id=technologies,
            )

    def test_observed_property_evidence_is_validated_before_done(self) -> None:
        snapshot = {
            "Requirements revision": "REQ-0001",
            "Design revision": "DES-0001",
            "Construction authorization": "AUTH-0001",
            "Gate B state": "APPROVED_FOR_CONSTRUCTION",
            "Task-plan state": "CURRENT",
            "Run state": "NOT_STARTED",
            "Active run ID": "NONE",
        }
        ledger = (PROJECT_ROOT / "docs/project/TASKS.md").read_text(
            encoding="utf-8"
        )
        prd = complete_design_contract(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        contract, issues = doctor.derive_design_contract(
            prd, "DES-0001", required=True
        )
        self.assertEqual(issues, [])
        executions = {
            item.property_id: item for item in contract.property_execution
        }
        technologies = {
            item.decision_id: item for item in contract.technology_decisions
        }
        ready = ready_task(
            requirements="REQ-0001; FR-001; PROP-001",
            design="DES-0001; TECH: TECH-0001, TECH-0007",
            command="python -m unittest tests.test_properties",
            property_projection=property_execution_projection(),
        )
        valid_verify = (
            task_completion_evidence_section()
            + "\n"
            + property_test_evidence_section()
        )
        doctor.validate_task_records(
            ledger + ready,
            snapshot,
            valid_verify,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            property_execution_by_id=executions,
            technology_decisions_by_id=technologies,
        )

        invalid_verify_cases = {
            "Evidence ID is missing from Task completion evidence": (
                task_completion_evidence_section(
                    (
                        "EV-0002",
                        "python -m unittest tests.test_properties",
                        "2026-07-17T12:00:00-07:00",
                        "commit: " + "a" * 40,
                        "docs/project/VERIFY.md#ev-0002",
                        "LOCAL_PASS",
                    )
                )
                + "\n"
                + property_test_evidence_section()
            ),
            "Task completion actor is unresolved or placeholder evidence": (
                valid_verify.replace("| alice |", "| PENDING |", 1)
            ),
            "Task completion result is unresolved or placeholder evidence": (
                valid_verify.replace(
                    "| observed property run | alice |",
                    "| PENDING | alice |",
                    1,
                )
            ),
            "observed property-test evidence references an unknown current task": (
                task_completion_evidence_section()
                + "\n"
                + property_test_evidence_section(task_id="TASK-999")
            ),
        }
        for expected, verify_text in invalid_verify_cases.items():
            with self.subTest(expected=expected), self.assertRaisesRegex(
                ValueError, expected
            ):
                doctor.validate_task_records(
                    ledger + ready,
                    snapshot,
                    verify_text,
                    approved_tech_ids={"TECH-0001", "TECH-0007"},
                    property_execution_by_id=executions,
                    technology_decisions_by_id=technologies,
                )

        failure_material = "commit: " + "b" * 40
        failure_source = "tests/artifacts/property-PROP-001-failure.json"
        valid_history = (
            task_completion_evidence_section(
                (
                    "EV-0002",
                    "python -m unittest tests.test_properties",
                    "2026-07-17T11:00:00-07:00",
                    failure_material,
                    failure_source,
                    "FAILED",
                ),
                (
                    "EV-0001",
                    "python -m unittest tests.test_properties",
                    "2026-07-17T12:00:00-07:00",
                    "commit: " + "a" * 40,
                    "docs/project/VERIFY.md#ev-0001",
                    "LOCAL_PASS",
                ),
            )
            + "\n"
            + property_test_evidence_section(
                evidence_id="EV-0002",
                result="FAIL",
                observed_at="2026-07-17T11:00:00-07:00",
                material=failure_material,
                counterexample="user_id=''",
                failure=(
                    "IMPLEMENTATION_DEFECT — corrected input normalization; "
                    "evidence EV-0002"
                ),
                source=failure_source,
            )
            + "\n"
            + property_test_evidence_row(evidence_id="EV-0001")
        )
        doctor.validate_task_records(
            ledger + ready,
            snapshot,
            valid_history,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            property_execution_by_id=executions,
            technology_decisions_by_id=technologies,
        )
        pending_resolution = valid_history.replace(
            "corrected input normalization; evidence EV-0002",
            "PENDING",
            1,
        )
        with self.assertRaisesRegex(ValueError, "concrete resolution"):
            doctor.validate_task_records(
                ledger + ready,
                snapshot,
                pending_resolution,
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                property_execution_by_id=executions,
                technology_decisions_by_id=technologies,
            )

        untouched_verify = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        doctor.validate_task_records(
            ledger + ready_task(),
            snapshot,
            untouched_verify,
        )

    def test_current_task_plan_covers_every_approved_property_execution(self) -> None:
        snapshot = {
            "Requirements revision": "REQ-0001",
            "Design revision": "DES-0001",
            "Construction authorization": "AUTH-0001",
            "Gate B state": "APPROVED_FOR_CONSTRUCTION",
            "Task-plan state": "CURRENT",
            "Run state": "NOT_STARTED",
            "Active run ID": "NONE",
        }
        ledger = (PROJECT_ROOT / "docs/project/TASKS.md").read_text(encoding="utf-8")
        expected = doctor.PropertyExecution(
            "PROP-001",
            "TECH-0007",
            "python -m unittest tests.test_properties",
            "MIN_CASES: 100; MAX_SECONDS: 30",
            "integer seed; reproduce with the recorded --seed value",
            "docs/project/VERIFY.md#property-based-test-evidence",
        )
        tasks, _by_id, _ready = doctor.validate_task_records(
            ledger + ready_task(),
            snapshot,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            property_execution_by_id={"PROP-001": expected},
        )
        self.assertEqual(
            doctor.missing_current_property_task_coverage(
                tasks,
                "CURRENT",
                {"PROP-001": expected},
            ),
            ["PROP-001"],
        )
        property_task = ready_task(
            requirements="REQ-0001; FR-001; PROP-001",
            design="DES-0001; TECH: TECH-0001, TECH-0007",
            command="python -m unittest tests.test_properties",
            property_projection=property_execution_projection(),
        )
        skipped = property_task.replace(
            "- Status: `READY`", "- Status: `SKIPPED`", 1
        ).replace(
            "- Skip record: `NONE`",
            "- Skip record: `OWNER-DECISION-001 — superseded; evidence EV-0001`",
            1,
        )
        self.assertEqual(
            doctor.missing_current_property_task_coverage(
                doctor.inspect_task_blocks(ledger + skipped),
                "CURRENT",
                {"PROP-001": expected},
            ),
            ["PROP-001"],
        )
        backlog = property_task.replace(
            "- Status: `READY`", "- Status: `BACKLOG`", 1
        )
        doctor.validate_task_records(
            ledger + backlog,
            snapshot,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            property_execution_by_id={"PROP-001": expected},
        )
        self.assertEqual(
            doctor.missing_current_property_task_coverage(
                doctor.inspect_task_blocks(ledger + backlog),
                "CURRENT",
                {"PROP-001": expected},
            ),
            [],
        )
        malformed_backlog = backlog.replace(property_execution_projection(), "", 1)
        with self.assertRaisesRegex(
            ValueError,
            "requires the exact property execution projection",
        ):
            doctor.validate_task_records(
                ledger + malformed_backlog,
                snapshot,
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                property_execution_by_id={"PROP-001": expected},
            )
        self.assertEqual(
            doctor.missing_current_property_task_coverage(
                doctor.inspect_task_blocks(ledger + property_task),
                "CURRENT",
                {"PROP-001": expected},
            ),
            [],
        )
        blocked_property_task = property_task.replace(
            "- Status: `READY`", "- Status: `BLOCKED`", 1
        ).replace("- Blocker: `NONE`", "- Blocker: `BLOCK-001 — dependency unavailable`", 1)
        doctor.validate_task_records(
            ledger + blocked_property_task,
            snapshot,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            property_execution_by_id={"PROP-001": expected},
        )
        malformed_blocked = blocked_property_task.replace(
            property_execution_projection(),
            "",
            1,
        )
        with self.assertRaisesRegex(
            ValueError,
            "requires the exact property execution projection",
        ):
            doctor.validate_task_records(
                ledger + malformed_blocked,
                snapshot,
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                property_execution_by_id={"PROP-001": expected},
            )

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            self.initialize_task_plan(project, ready_task())
            refresh_control_hashes(project)

            report = doctor.inspect_project(project)

        self.assertIn("TASK_PROPERTY_COVERAGE", codes(report))
        self.assertTrue(
            any(
                "CURRENT task plan does not cover approved property execution IDs: PROP-001"
                in diagnostic["message"]
                for diagnostic in report["diagnostics"]
            )
        )

    def test_done_requires_observed_log_and_passing_structured_local_evidence(self) -> None:
        snapshot = {
            "Requirements revision": "REQ-0001",
            "Design revision": "DES-0001",
            "Construction authorization": "AUTH-0001",
            "Gate B state": "APPROVED_FOR_CONSTRUCTION",
            "Task-plan state": "CURRENT",
            "Run state": "NOT_STARTED",
            "Active run ID": "NONE",
        }
        ledger = (PROJECT_ROOT / "docs/project/TASKS.md").read_text(encoding="utf-8")
        done = (
            ready_task()
            .replace("- Status: `READY`", "- Status: `DONE`", 1)
            .replace("- Evidence: `NONE`", "- Evidence: `EV-0001`", 1)
            .replace("- [ ]", "- [x]", 1)
        )
        valid_verify = """## Task completion evidence

| Evidence ID | Task | Command or observation | Result | Actor | Observed at | Commit / worktree / artifact | Durable source | Status |
|---|---|---|---|---|---|---|---|---|
| EV-0001 | TASK-001 | python -m unittest | passed | alice | 2026-07-17T12:00:00-07:00 | commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa | docs/project/VERIFY.md#ev-0001 | LOCAL_PASS |
"""
        with self.assertRaisesRegex(ValueError, "observed Execution log"):
            doctor.validate_task_records(ledger + done, snapshot, valid_verify)

        observed = done.replace(
            "Not started.",
            "2026-07-17T12:00:00-07:00 coordinator observed validation pass.",
            1,
        )
        stock_verify = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "wrong task|placeholder evidence|LOCAL_PASS"):
            doctor.validate_task_records(ledger + observed, snapshot, stock_verify)

        invalid_id = observed.replace("EV-0001", "EVIDENCE-0001", 1)
        with self.assertRaisesRegex(ValueError, "invalid local Evidence ID"):
            doctor.validate_task_records(ledger + invalid_id, snapshot, valid_verify)

        multi_done = observed.replace("EV-0001", "EV-0001, EV-0002", 1)
        multi_verify = valid_verify + (
            "| EV-0002 | TASK-001 | python -m unittest integration | passed | alice | "
            "2026-07-17T12:01:00-07:00 | "
            "commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa | "
            "docs/project/VERIFY.md#ev-0002 | VERIFIED |\n"
        )
        doctor.validate_task_records(ledger + multi_done, snapshot, multi_verify)

        mixed_url = observed.replace(
            "EV-0001", "EV-0001, https://evidence.example.test/runs/EV-0001", 1
        )
        doctor.validate_task_records(ledger + mixed_url, snapshot, valid_verify)

        traversal_source = valid_verify.replace(
            "docs/project/VERIFY.md#ev-0001", "artifact: a/../b", 1
        )
        with self.assertRaisesRegex(ValueError, "durable source"):
            doctor.validate_task_records(ledger + observed, snapshot, traversal_source)

        failed_observation = valid_verify.replace("LOCAL_PASS", "FAILED", 1)
        with self.assertRaisesRegex(ValueError, "status must be LOCAL_PASS or VERIFIED"):
            doctor.validate_task_records(
                ledger + observed,
                snapshot,
                failed_observation,
            )

    def test_malformed_nested_state_never_crashes(self) -> None:
        for key in ("project", "lifecycle", "execution"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                project = self.copy_project(Path(directory))
                state_path = project / "bootstrap.yaml"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state[key] = "malformed"
                state_path.write_text(json.dumps(state), encoding="utf-8")

                report = doctor.inspect_project(project)

                self.assertFalse(report["ok"])
                self.assertIn("STATE_SCHEMA", codes(report))
                self.assertEqual(report["next_prompt"], "STOP")

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"]["mode"] = []
            state["lifecycle"]["gate_a"] = {}
            state["execution"]["state"] = []
            state["execution"]["active_tasks"] = [{}]
            state_path.write_text(json.dumps(state), encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertFalse(report["ok"])
        self.assertIn("PROJECT_VOCABULARY", codes(report))
        self.assertIn("STATE_GATE", codes(report))
        self.assertIn("STATE_RUN", codes(report))

    def test_gate_a_requires_exact_assumption_acceptance_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project, gate_b=False)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            text = set_table_value(
                text,
                "### Gate A — agent analysis record",
                "### Gate A — owner acceptance record",
                "Proposed assumption IDs required to proceed",
                "`ASM-001`",
            )
            text = set_table_value(
                text,
                "### Gate A — owner acceptance record",
                "### Gate A validation and invalidation rules",
                "Explicitly accepted assumption IDs",
                "`ASM-001, ASM-999`",
            )
            text = set_table_value(
                text,
                "### Gate A — owner acceptance record",
                "### Gate A validation and invalidation rules",
                "Authorization source",
                "`TODO`",
            )
            text = set_receipt(
                text,
                "gate-a",
                "\n".join(
                    [
                        "APPROVE REQUIREMENTS GATE A",
                        "Requirements revision: REQ-0001",
                        "Cost posture: MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                        "Accepted assumptions: ASM-001, ASM-999",
                        "Approver: alice",
                    ]
                ),
            )
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("GATE_A_ASSUMPTIONS", codes(report))
        self.assertIn("GATE_A_OWNER_RECORD", codes(report))

    def test_gate_approvers_must_be_explicit_humans(self) -> None:
        for identity in (
            "GPT-5",
            "GPT.5",
            "AWS Core",
            "Lambda",
            "deployment service",
            "Codex",
            "AI",
            "AUTOMATION",
            "release agent",
            "system",
            "service-account",
            "PENDING",
            "PLACEHOLDER",
            "NOT_STARTED",
        ):
            with self.subTest(identity=identity):
                self.assertFalse(doctor.explicit_human_approver(identity))
        self.assertTrue(doctor.explicit_human_approver("Alice Rivera"))

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            prd_path = project / "docs/project/PRD.md"
            text = approve_gate_a(prd_path.read_text(encoding="utf-8"))
            text = set_table_value(
                text,
                "### Gate A — owner acceptance record",
                "## 14. Architecture overview",
                "Approver",
                "`PENDING`",
            )
            text = text.replace(
                "Approver: alice\n```\n<!-- bootstrap:gate-a",
                "Approver: PENDING\n```\n<!-- bootstrap:gate-a",
            )
            prd_path.write_text(text, encoding="utf-8")
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            current_greenfield_state(state)
            state_path.write_text(json.dumps(state), encoding="utf-8")

            gate_a_report = doctor.inspect_project(project)

        self.assertIn("GATE_A_HUMAN_APPROVER", codes(gate_a_report))

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 29. Gate B owner authorization record",
                "## 30. Gate B validation and invalidation rules",
                "Approver",
                "`PLACEHOLDER`",
            )
            text = text.replace(
                "Approver: alice\n```\n<!-- bootstrap:gate-b",
                "Approver: PLACEHOLDER\n```\n<!-- bootstrap:gate-b",
            )
            prd_path.write_text(text, encoding="utf-8")

            gate_b_report = doctor.inspect_project(project)

        self.assertIn("GATE_B_HUMAN_APPROVER", codes(gate_b_report))

    def test_gate_a_assumption_order_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project, gate_b=False)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            text = set_table_value(
                text,
                "### Gate A — agent analysis record",
                "### Gate A — owner acceptance record",
                "Proposed assumption IDs required to proceed",
                "`ASM-001, ASM-002`",
            )
            text = set_table_value(
                text,
                "### Gate A — owner acceptance record",
                "### Gate A validation and invalidation rules",
                "Explicitly accepted assumption IDs",
                "`ASM-002, ASM-001`",
            )
            text = set_receipt(
                text,
                "gate-a",
                "\n".join(
                    [
                        "APPROVE REQUIREMENTS GATE A",
                        "Requirements revision: REQ-0001",
                        "Cost posture: MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                        "Accepted assumptions: ASM-002, ASM-001",
                        "Approver: alice",
                    ]
                ),
            )
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("GATE_A_ASSUMPTIONS", codes(report))

    def test_gate_b_rejects_any_unresolved_critical_envelope_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "Mandatory stop conditions",
                "`TODO`",
            )
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("GATE_B_ENVELOPE", codes(report))

    def test_gate_b_rejects_generated_invalid_design_aws_core_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            verify_path = project / "docs/project/VERIFY.md"
            verify_path.write_text(
                record_aws_core_evidence(
                    verify_path.read_text(encoding="utf-8"),
                    "DESIGN-10",
                    "NOT_STARTED",
                ),
                encoding="utf-8",
            )

            report = doctor.inspect_project(project)

        self.assertIn("AWS_CORE_EVIDENCE_GENERATED_INVALID", codes(report))
        self.assertEqual(
            report["remediation"]["next_action"]["responsible_party"],
            "CODEX",
        )
        self.assertEqual(report["next_prompt"], "STOP")

    def test_boot_00_routes_to_intake_without_aws_core_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            manifest_path = project / "bootstrap.manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["control_sha256"] = {
                relative: hashlib.sha256((project / relative).read_bytes()).hexdigest()
                for relative in doctor.CONTROL_HASH_FILES
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertNotIn("AWS_CORE_BOOT00_EVIDENCE_REQUIRED", codes(report))
        self.assertEqual(report["next_prompt"], "INTAKE-10")

    def test_aws_core_capabilities_require_independent_attribution(self) -> None:
        verify_text = (REPOSITORY_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        binding = "DES-0001"
        passed = record_aws_core_evidence(
            verify_text, "DESIGN-10", binding=binding
        )
        passed_rows = doctor.parse_aws_core_evidence(passed)
        self.assertEqual(
            doctor.aws_core_phase_evidence_issues(
                passed_rows,
                "DESIGN-10",
                expected_binding=binding,
                expected_design_revision="DES-0001",
                approved_tech_ids={"TECH-0001"},
            ),
            [],
        )

        wrong_design = record_aws_core_capability_evidence(
            passed,
            "DESIGN-10",
            "retrieve_skill",
            binding=binding,
            advisory_design_binding="DES-9999; TECH: TECH-0001",
        )
        wrong_design_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(wrong_design),
            "DESIGN-10",
            expected_binding=binding,
            expected_design_revision="DES-0001",
            approved_tech_ids={"TECH-0001"},
        )
        self.assertTrue(
            any("Advisory Design binding must reference DES-0001" in issue for issue in wrong_design_issues)
        )

        malformed_trace = record_aws_core_capability_evidence(
            passed,
            "DESIGN-10",
            "retrieve_skill",
            binding=binding,
            advisory_design_binding="DES-0001 architecture review",
        )
        malformed_trace_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(malformed_trace),
            "DESIGN-10",
            expected_binding=binding,
        )
        self.assertTrue(
            any("Advisory Design binding must use" in issue for issue in malformed_trace_issues)
        )

        aws_binding = "sha256:" + "a" * 64
        aws_not_applicable = record_aws_core_evidence(
            verify_text,
            "AWS-10",
            binding=aws_binding,
            advisory_design_binding="NOT_APPLICABLE — operational preflight did not change the design",
        )
        self.assertEqual(
            doctor.aws_core_phase_evidence_issues(
                doctor.parse_aws_core_evidence(aws_not_applicable),
                "AWS-10",
                expected_binding=aws_binding,
                expected_design_revision="DES-0001",
                approved_tech_ids={"TECH-0001"},
            ),
            [],
        )

        aws_wrong_design = record_aws_core_capability_evidence(
            record_aws_core_evidence(verify_text, "AWS-10", binding=aws_binding),
            "AWS-10",
            "retrieve_skill",
            binding=aws_binding,
            advisory_design_binding="DES-9999; TECH: TECH-0001",
        )
        aws_wrong_design_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(aws_wrong_design),
            "AWS-10",
            expected_binding=aws_binding,
            expected_design_revision="DES-0001",
            approved_tech_ids={"TECH-0001"},
        )
        self.assertTrue(
            any("must reference DES-0001" in issue for issue in aws_wrong_design_issues)
        )

        unknown_tech = record_aws_core_capability_evidence(
            passed,
            "DESIGN-10",
            "retrieve_skill",
            binding=binding,
            advisory_design_binding="DES-0001; TECH: TECH-9999",
        )
        unknown_tech_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(unknown_tech),
            "DESIGN-10",
            expected_binding=binding,
            expected_design_revision="DES-0001",
            approved_tech_ids={"TECH-0001"},
        )
        self.assertTrue(
            any("unapproved TECH IDs: TECH-9999" in issue for issue in unknown_tech_issues)
        )

        unattributed = record_aws_core_capability_evidence(
            passed,
            "DESIGN-10",
            "retrieve_skill",
            binding=binding,
            actor="Codex",
        )
        unattributed_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(unattributed),
            "DESIGN-10",
            expected_binding=binding,
        )
        self.assertTrue(
            any("Observation actor" in issue for issue in unattributed_issues)
        )

        generic = record_aws_core_capability_evidence(
            passed,
            "DESIGN-10",
            "search_documentation",
            binding=binding,
            plugin_source="generic-aws-docs",
        )
        generic_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(generic),
            "DESIGN-10",
            expected_binding=binding,
        )
        self.assertTrue(any("plugin source" in issue for issue in generic_issues))

        one_failed = record_aws_core_capability_evidence(
            passed,
            "DESIGN-10",
            "search_documentation",
            "FAILED",
            binding=binding,
        )
        failed_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(one_failed),
            "DESIGN-10",
            expected_binding=binding,
        )
        self.assertTrue(
            any(
                "DESIGN-10 search_documentation requires fresh PASS" in issue
                for issue in failed_issues
            )
        )

    def test_aws_core_runtime_discovery_chains_are_linked_and_ordered(self) -> None:
        verify_text = (REPOSITORY_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        passed = record_aws_core_evidence(verify_text, "DESIGN-10")
        design_rows = re.findall(
            r"(?m)^\| `DESIGN-10` \| `AWS-DISC-0002` \|.*$", passed
        )
        self.assertEqual(len(design_rows), 2)
        second_rows = "\n".join(
            row.replace("AWS-DISC-0002", "AWS-DISC-0004").replace(
                "aws-architecture", "aws-databases"
            )
            for row in design_rows
        )
        first_aws_10 = re.search(r"(?m)^\| `AWS-10` \|", passed)
        self.assertIsNotNone(first_aws_10)
        multiple = (
            passed[: first_aws_10.start()]
            + second_rows
            + "\n"
            + passed[first_aws_10.start() :]
        )
        multiple_rows = doctor.parse_aws_core_evidence(multiple)
        self.assertEqual(
            {
                discovery_id
                for phase, discovery_id, _capability in multiple_rows
                if phase == "DESIGN-10"
            },
            {"AWS-DISC-0002", "AWS-DISC-0004"},
        )
        self.assertEqual(
            doctor.aws_core_phase_evidence_issues(
                multiple_rows,
                "DESIGN-10",
                expected_binding="DES-0001",
                expected_design_revision="DES-0001",
            ),
            [],
        )

        observed = doctor.derive_aws_core_observed_usage(
            multiple_rows,
            "DESIGN-10",
            issues=[],
        )
        self.assertEqual(observed["status"], "OBSERVED")
        self.assertEqual(observed["phase"], "DESIGN-10")
        self.assertEqual(
            [chain["discovery_id"] for chain in observed["chains"]],
            ["AWS-DISC-0002", "AWS-DISC-0004"],
        )
        self.assertEqual(
            observed["chains"][0]["skill_identifier"], "aws-architecture"
        )
        self.assertEqual(
            observed["chains"][0]["official_references"],
            ["https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html"],
        )
        self.assertIs(observed["chains"][0]["credentials_inspected"], False)
        self.assertIs(observed["chains"][0]["aws_account_accessed"], False)
        self.assertEqual(
            doctor.derive_aws_core_observed_usage(
                multiple_rows,
                "DESIGN-10",
                issues=["current chain is unavailable"],
            ),
            {"status": "UNOBSERVED", "phase": "DESIGN-10", "chains": []},
        )

        mismatched = record_aws_core_capability_evidence(
            passed,
            "DESIGN-10",
            "retrieve_skill",
            binding="DES-0001",
            returned_skill_identifier="aws-databases",
        )
        mismatch_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(mismatched),
            "DESIGN-10",
            expected_binding="DES-0001",
            expected_design_revision="DES-0001",
        )
        self.assertTrue(
            any("was not returned by search" in issue for issue in mismatch_issues),
            mismatch_issues,
        )

        retrieve_first = passed.replace(
            "`2026-07-20T12:00:01Z`",
            "`2026-07-20T11:59:59Z`",
            1,
        )
        chronology_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(retrieve_first),
            "DESIGN-10",
            expected_binding="DES-0001",
            expected_design_revision="DES-0001",
        )
        self.assertTrue(
            any("retrieve timestamp precedes search" in issue for issue in chronology_issues),
            chronology_issues,
        )

        duplicate = passed.replace(design_rows[0], design_rows[0] + "\n" + design_rows[0], 1)
        with self.assertRaisesRegex(ValueError, "duplicates DESIGN-10"):
            doctor.parse_aws_core_evidence(duplicate)

        reused = passed.replace("`AWS-DISC-0003`", "`AWS-DISC-0002`")
        with self.assertRaisesRegex(ValueError, "reused across phases"):
            doctor.parse_aws_core_evidence(reused)

        wrong_phase = passed.replace("`DESIGN-10`", "`BOOT-00`", 1)
        with self.assertRaisesRegex(ValueError, "unknown phase"):
            doctor.parse_aws_core_evidence(wrong_phase)

    def test_material_aws_claim_requires_current_discovery_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8").replace(
                "| AWS-EV-0001 | AWS-DISC-0002 |",
                "| AWS-EV-0001 | AWS-DISC-9999 |",
                1,
            )
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("AWS_CORE_EVIDENCE_REQUIRED", codes(report))
        self.assertTrue(
            any(
                "AWS-EV-0001 must cite a current DESIGN-10 AWS-DISC chain"
                in item["message"]
                for item in report["diagnostics"]
            ),
            report["diagnostics"],
        )

    def test_aws_core_evidence_is_limited_to_requirements_design_and_preflight(self) -> None:
        verify_text = (REPOSITORY_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        rows = doctor.parse_aws_core_evidence(verify_text)
        self.assertEqual(
            {phase for phase, _discovery, _capability in rows},
            {"REQ-10", "DESIGN-10", "AWS-10"},
        )
        self.assertNotIn("BOOT-00", doctor.AWS_CORE_EVIDENCE_PHASES)

    def test_missing_aws_10_evidence_blocks_aws_execution_planning(self) -> None:
        verify_text = (REPOSITORY_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        rows = doctor.parse_aws_core_evidence(verify_text)
        binding = "sha256:" + "a" * 64
        self.assertTrue(
            doctor.aws_core_phase_evidence_issues(
                rows, "AWS-10", expected_binding=binding
            )
        )

        passed = record_aws_core_evidence(
            verify_text, "AWS-10", binding=binding
        )
        passed_rows = doctor.parse_aws_core_evidence(passed)
        self.assertEqual(
            doctor.aws_core_phase_evidence_issues(
                passed_rows, "AWS-10", expected_binding=binding
            ),
            [],
        )
        self.assertTrue(
            doctor.aws_core_phase_evidence_issues(
                passed_rows,
                "AWS-10",
                expected_binding="sha256:" + "b" * 64,
            )
        )

    def test_split_aws_rows_are_conditionally_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "AWS account",
                "`NONE`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")

            docs_only_report = doctor.inspect_project(project)

        self.assertIn("GATE_B_ENVELOPE", codes(docs_only_report))

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            text = set_table_value(
                text, "## Document status", "## 1. Workload profile", "AWS lane", "`fast-dev`"
            )
            for field, value in {
                "Project AWS lane": "`fast-dev`",
                "AWS boundary": "`MUTATE_LISTED_RESOURCES`",
            }.items():
                text = set_table_value(
                    text,
                    "## 28. Construction envelope",
                    "## 29. Gate B owner authorization record",
                    field,
                    value,
                )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"]["aws_lane"] = "fast-dev"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            mutation_report = doctor.inspect_project(project)

        self.assertIn("GATE_B_ENVELOPE", codes(mutation_report))

    def test_fast_dev_mutation_requires_nonproduction_artifact_and_finite_validity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"]["aws_lane"] = "fast-dev"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            text = set_table_value(
                text, "## Document status", "## 1. Workload profile", "AWS lane", "`fast-dev`"
            )
            values = {
                "Project AWS lane": "`fast-dev`",
                "AWS boundary": "`MUTATE_LISTED_RESOURCES`",
                "AWS account": "`ACCOUNT: 123456789012`",
                "AWS role or profile": "`ROLE: fast-dev-deployer`",
                "AWS Region": "`REGION: us-west-2`",
                "AWS environment": "`ENVIRONMENT: production; CLASS: PRODUCTION`",
                "AWS stack or application": "`STACK: fastlane-test`",
                "AWS resource allowlist": "`RESOURCES: arn:aws:cloudformation:us-west-2:123456789012:stack/fastlane-test`",
                "AWS allowed operations": "`OPERATIONS: cloudformation:CreateChangeSet, cloudformation:ExecuteChangeSet`",
                "AWS cost ceiling": "`USD: 20`",
                "AWS prohibited operations": "`PROHIBITED: IAM broadening, wildcard resources, destructive replacement`",
                "AWS artifact authorization and provenance": "`EXACT_DIGEST: sha256:"
                + "1" * 64
                + "`",
                "AWS rollback boundary": "`ROLLBACK: delete only the authorized fastlane-test stack`",
                "AWS authorization validity": "`Expires at 2099-01-01T00:00:00Z; earlier completion: authorized stack reaches terminal state`",
            }
            for field, value in values.items():
                text = set_table_value(
                    text,
                    "## 28. Construction envelope",
                    "## 29. Gate B owner authorization record",
                    field,
                    value,
                )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")

            production_report = doctor.inspect_project(project)

            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "AWS environment",
                "`ENVIRONMENT: dev; CLASS: NON_PRODUCTION`",
            )
            text = set_table_value(
                text,
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "AWS artifact authorization and provenance",
                "`latest build`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            artifact_report = doctor.inspect_project(project)

            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "AWS artifact authorization and provenance",
                "`EXACT_DIGEST: sha256:" + "2" * 64 + "`",
            )
            text = set_table_value(
                text,
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "AWS authorization validity",
                "`forever`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            validity_report = doctor.inspect_project(project)

            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "AWS authorization validity",
                "`Expires at 2099-01-01T00:00:00Z; earlier completion: authorized stack reaches terminal state`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            valid_mutation_report = doctor.inspect_project(project)

            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "AWS cost ceiling",
                "`unlimited`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            invalid_cost_report = doctor.inspect_project(project)

            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "AWS cost ceiling",
                "`USD: 20.00`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")

            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"]["aws_lane"] = "explicit-gate"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            text = prd_path.read_text(encoding="utf-8")
            text = set_table_value(
                text,
                "## Document status",
                "## 1. Workload profile",
                "AWS lane",
                "`explicit-gate`",
            )
            text = set_table_value(
                text,
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "Project AWS lane",
                "`explicit-gate`",
            )
            text = set_table_value(
                text,
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "AWS environment",
                "`ENVIRONMENT: production; CLASS: PRODUCTION`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            explicit_gate_report = doctor.inspect_project(project)

        production_messages = "\n".join(
            item["message"] for item in production_report["diagnostics"]
        )
        artifact_messages = "\n".join(
            item["message"] for item in artifact_report["diagnostics"]
        )
        validity_messages = "\n".join(
            item["message"] for item in validity_report["diagnostics"]
        )
        invalid_cost_messages = "\n".join(
            item["message"] for item in invalid_cost_report["diagnostics"]
        )
        self.assertIn("must be NON_PRODUCTION", production_messages)
        self.assertIn("EXACT_DIGEST", artifact_messages)
        self.assertIn("Expires at <ISO8601>", validity_messages)
        self.assertIn("finite positive currency amount", invalid_cost_messages)
        self.assertEqual(invalid_cost_report["authorizations"]["aws"], "NONE")
        self.assertNotIn("GATE_B_ENVELOPE", codes(valid_mutation_report))
        self.assertNotIn("AWS_LANE_BOUNDARY", codes(valid_mutation_report))
        self.assertNotIn("GATE_B_ENVELOPE", codes(explicit_gate_report))
        self.assertNotIn("AWS_LANE_BOUNDARY", codes(explicit_gate_report))
        for inactive_report in (valid_mutation_report, explicit_gate_report):
            self.assertEqual(inactive_report["external_authority"]["kind"], "NONE")
            self.assertEqual(inactive_report["external_authority"]["validity"], "NONE")
            self.assertEqual(inactive_report["authorizations"]["aws"], "NONE")
            self.assertEqual(
                inactive_report["external_authority"]["request_match"]["validity"],
                "NONE",
            )

        fast_dev_context = doctor.Context(PROJECT_ROOT)
        fast_dev_envelope = {
            "AWS boundary": "MUTATE_LISTED_RESOURCES",
            "AWS account": "ACCOUNT: 123456789012",
            "AWS role or profile": "ROLE: fast-dev-deployer",
            "AWS Region": "REGION: us-west-2",
            "AWS environment": "ENVIRONMENT: dev; CLASS: NON_PRODUCTION",
            "AWS stack or application": "STACK: fastlane-test",
            "AWS resource allowlist": (
                "RESOURCES: arn:aws:cloudformation:us-west-2:123456789012:"
                "stack/fastlane-test"
            ),
            "AWS allowed operations": (
                "OPERATIONS: cloudformation:CreateChangeSet, "
                "cloudformation:ExecuteChangeSet"
            ),
            "AWS cost ceiling": "USD: 20.00",
            "AWS artifact authorization and provenance": (
                "EXACT_DIGEST: sha256:" + "2" * 64
            ),
            "AWS rollback boundary": "ROLLBACK: delete only the authorized fastlane-test stack",
            "AWS authorization validity": (
                "Expires at 2099-01-01T00:00:00Z; earlier completion: "
                "authorized stack reaches terminal state"
            ),
        }
        fast_dev_authority = doctor.derive_external_authority(
            fast_dev_context,
            fast_dev_envelope,
            "fast-dev",
            "AUTH-0001",
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            aws_progress_state="AWS_PREFLIGHT_READY",
            active_artifact="sha256:" + "2" * 64,
            aws_action_phase="AWS-20",
            preflight=ready_preflight(
                account="123456789012", region="us-west-2", environment="dev"
            ),
        )
        self.assertEqual(fast_dev_authority["kind"], "FAST_DEV_GATE_B")
        self.assertEqual(fast_dev_authority["validity"], "CURRENT")
        self.assertEqual(fast_dev_authority["account"], "123456789012")
        self.assertEqual(fast_dev_authority["region"], "us-west-2")
        self.assertEqual(fast_dev_authority["cost_ceiling"], "USD: 20.00")
        request_match = doctor.derive_request_match(
            fast_dev_context, fast_dev_authority
        )
        self.assertEqual(request_match["schema_version"], 1)
        self.assertEqual(request_match["authority_kind"], "FAST_DEV_GATE_B")
        self.assertEqual(request_match["account"], "123456789012")
        self.assertEqual(request_match["region"], "us-west-2")
        self.assertEqual(
            request_match["cost_ceiling"],
            {"currency": "USD", "amount": "20.00"},
        )
        self.assertNotIn("ACCOUNT:", request_match["account"])
        self.assertNotIn("REGION:", request_match["region"])
        self.assertEqual(request_match["allowed_execution_lanes"], ["STRUCTURED_API"])
        self.assertIsNone(request_match["reviewed_script"])
        before_preflight = doctor.derive_external_authority(
            doctor.Context(PROJECT_ROOT),
            fast_dev_envelope,
            "fast-dev",
            "AUTH-0001",
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            aws_progress_state="AWS_PREFLIGHT_RUNNING",
            active_artifact="sha256:" + "2" * 64,
            aws_action_phase="AWS-20",
        )
        self.assertNotEqual(before_preflight["kind"], "FAST_DEV_GATE_B")
        self.assertNotEqual(before_preflight["validity"], "CURRENT")

    def test_cost_posture_and_mutation_ceiling_are_canonical_and_bounded(self) -> None:
        self.assertIsNone(
            doctor.parse_cost_posture(
                "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED"
            )
        )
        currency, amount = doctor.parse_cost_posture(
            "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00"
        )
        self.assertEqual(currency, "USD")
        self.assertEqual(str(amount), "20.00")
        doctor.validate_aws_cost_ceiling(
            "USD: 20.00",
            "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
        )
        for invalid in (
            "unlimited",
            "HARD_CAP_NOT_STATED",
            "-1",
            "NaN",
            "Infinity",
            "20.00",
            "usd: 20.00",
            "USD: 0",
            "USD: 20.000",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "finite positive"):
                    doctor.validate_aws_cost_ceiling(
                        invalid,
                        "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                    )
        for invalid_currency in ("ZZZ: 20.00", "XTS: 20.00", "XXX: 20.00"):
            with self.subTest(invalid_currency=invalid_currency):
                with self.assertRaisesRegex(ValueError, "current ISO 4217"):
                    doctor.validate_aws_cost_ceiling(
                        invalid_currency,
                        "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                    )
        with self.assertRaisesRegex(ValueError, "current ISO 4217"):
            doctor.parse_cost_posture(
                "MINIMIZE_TOTAL_COST; HARD_CAP: ZZZ 20.00"
            )
        self.assertEqual(
            bootstrap_runtime.ISO_4217_CURRENCY_CODES,
            doctor.ISO_4217_CURRENCY_CODES,
        )
        with self.assertRaisesRegex(ValueError, "currency must match"):
            doctor.validate_aws_cost_ceiling(
                "EUR: 10.00",
                "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            )
        with self.assertRaisesRegex(ValueError, "exceeds"):
            doctor.validate_aws_cost_ceiling(
                "USD: 20.01",
                "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            )

    def test_gate_a_receipt_binds_exact_owner_cost_posture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project, gate_b=False)

            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "### Gate A — readiness card",
                "### Gate A — owner acceptance record",
                "Cost posture",
                "`MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00`",
            )
            prd_path.write_text(text, encoding="utf-8")

            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"]["cost_posture"] = (
                "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00"
            )
            state_path.write_text(json.dumps(state), encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertFalse(report["ok"])
        self.assertIn("GATE_A_COST_AUTHORIZATION", codes(report))
        self.assertIn("GATE_A_RECEIPT_MISMATCH", codes(report))
        self.assertEqual(report["authorizations"]["aws"], "NONE")
        self.assertEqual(report["next_prompt"], "STOP")

    def test_gate_b_hash_binds_every_envelope_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "Maximum generated tasks",
                "`7`",
            )
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("GATE_B_ENVELOPE_HASH", codes(report))
        self.assertIn("GATE_B_RECEIPT_MISMATCH", codes(report))

    def test_gate_b_project_rows_must_exactly_match_document_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "Project mode",
                "`brownfield`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("GATE_B_PROJECT_DRIFT", codes(report))

    def test_gate_readiness_cards_are_required_for_ready_recommendations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project, gate_b=False)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "### Gate A — readiness card",
                "### Gate A — owner acceptance record",
                "Owner and users",
                "`UNASSIGNED`",
            )
            prd_path.write_text(text, encoding="utf-8")

            gate_a_report = doctor.inspect_project(project)

        self.assertIn("GATE_A_READINESS_CARD", codes(gate_a_report))

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "### Gate B — readiness card",
                "## 28. Construction envelope",
                "Validation/evidence",
                "`TODO`",
            )
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("GATE_B_READINESS_CARD", codes(report))

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "### Gate B — readiness card",
                "## 28. Construction envelope",
                "Validation/evidence",
                "`TBD`",
            )
            prd_path.write_text(text, encoding="utf-8")

            tbd_report = doctor.inspect_project(project)

        self.assertIn("GATE_B_READINESS_CARD", codes(tbd_report))

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "Mandatory stop conditions",
                "`UNKNOWN`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")

            unknown_report = doctor.inspect_project(project)

        self.assertIn("GATE_B_ENVELOPE", codes(unknown_report))

    def test_task_ids_must_be_subsets_of_authorized_ids(self) -> None:
        cases = {
            "requirements": {"requirements": "REQ-0001; FR-999"},
            "outcome": {"outcome": "Deliver OUT-999 without scope expansion."},
        }
        for label, task_options in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                project = self.copy_project(Path(directory))
                self.approve_project(project)
                self.initialize_task_plan(project, ready_task(**task_options))

                report = doctor.inspect_project(project)

                self.assertIn("TASK_ID_OUTSIDE_AUTH", codes(report))

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            self.initialize_task_plan(
                project,
                ready_task(design="DES-0001; ADR-999"),
            )

            malformed_design_report = doctor.inspect_project(project)

        self.assertIn("TASK_GRAPH_INVALID", codes(malformed_design_report))

    def test_external_state_and_paths_use_case_insensitive_authorized_containment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "Allowed external-state targets",
                "`TARGETS: AWS:stack/dev`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            self.initialize_task_plan(
                project,
                ready_task(
                    "APP/main.py",
                    requirements="REQ-0001; FR-001; PROP-001",
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    external_state="aws:STACK/dev/resource",
                    command="python -m unittest tests.test_properties",
                    property_projection=property_execution_projection(),
                ),
            )
            refresh_control_hashes(project)

            allowed_report = doctor.inspect_project(project)

        self.assertTrue(allowed_report["ok"], allowed_report["diagnostics"])

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "Allowed external-state targets",
                "`TARGETS: aws:stack/dev`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            self.initialize_task_plan(project, ready_task(external_state="aws:stack/prod"))

            denied_report = doctor.inspect_project(project)

        self.assertIn("TASK_EXTERNAL_STATE_BOUNDARY", codes(denied_report))

    def test_validation_commands_are_prefix_bound_and_reject_shell_control(self) -> None:
        for command in ("python setup.py", "python -m unittest && curl https://example.test"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                project = self.copy_project(Path(directory))
                self.approve_project(project)
                self.initialize_task_plan(project, ready_task(command=command))

                report = doctor.inspect_project(project)

                self.assertIn("TASK_COMMAND_BOUNDARY", codes(report))

    def test_github_issue_url_must_match_exact_authorized_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            for field, value in {
                "GitHub boundary": "`ISSUES`",
                "GitHub repository, branch, and merge constraints": (
                    "`REPO: Levi-Breedlove/aws-bootstrap; BRANCH: main; MERGE: PROHIBITED`"
                ),
            }.items():
                text = set_table_value(
                    text,
                    "## 28. Construction envelope",
                    "## 29. Gate B owner authorization record",
                    field,
                    value,
                )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            self.initialize_task_plan(
                project,
                ready_task(github_issue="https://github.com/example/other/issues/12"),
            )

            report = doctor.inspect_project(project)

        self.assertIn("TASK_GITHUB_BOUNDARY", codes(report))

    def test_task_boundary_is_exact_and_authorization_must_be_unexpired(self) -> None:
        cases = {
            "substring boundary": (
                "Task boundary",
                "`NOT_DERIVED_FROM_AUTHORIZED_IDS_AND_WRITE_SET`",
            ),
            "expired": (
                "Authorization expiry or completion condition",
                "`Expires at 2020-01-01T00:00:00Z`",
            ),
        }
        for label, (field, value) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                project = self.copy_project(Path(directory))
                self.approve_project(project)
                prd_path = project / "docs/project/PRD.md"
                text = set_table_value(
                    prd_path.read_text(encoding="utf-8"),
                    "## 28. Construction envelope",
                    "## 29. Gate B owner authorization record",
                    field,
                    value,
                )
                prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")

                report = doctor.inspect_project(project)

                self.assertIn("GATE_B_ENVELOPE", codes(report))

    def test_brownfield_baseline_is_deferred_until_gate_a_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            setup = subprocess.run(
                [
                    sys.executable,
                    str(project / "bootstrap.py"),
                    "--target",
                    str(project),
                    "--project-name",
                    "Brownfield Doctor Test",
                    "--region",
                    "us-west-2",
                    "--cost-posture",
                    "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                    "--in-place-template-instance",
                ],
                cwd=project,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"].update(
                {
                    "mode": "brownfield",
                    "delivery_profile": "quick-mvp",
                    "effective_risk": "low",
                    "aws_lane": "documentation-only",
                    "brownfield_baseline": "UNASSESSED",
                }
            )
            state_path.write_text(json.dumps(state), encoding="utf-8")
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            for field, value in {
                "Project mode": "`brownfield`",
                "Delivery profile": "`quick-mvp`",
                "Effective risk": "`low`",
                "AWS lane": "`documentation-only`",
            }.items():
                text = set_table_value(text, "## Document status", "## 1. Workload profile", field, value)
            prd_path.write_text(text, encoding="utf-8")

            blocked_report = doctor.inspect_project(project)

            text = approve_gate_a(prd_path.read_text(encoding="utf-8"))
            text = set_table_value(
                text, "## Document status", "## 1. Workload profile", "Project mode", "`brownfield`"
            )
            prd_path.write_text(text, encoding="utf-8")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["lifecycle"]["gate_a"] = "APPROVED_FOR_DESIGN"
            state["project"]["brownfield_baseline"] = "RECORDED"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            approval_report = doctor.inspect_project(project)

        self.assertTrue(blocked_report["ok"], blocked_report["diagnostics"])
        self.assertIn("BROWNFIELD_PRD_BASELINE", codes(approval_report))
        self.assertIn("BROWNFIELD_PRD_PRESERVATION", codes(approval_report))

    def test_stale_gates_route_to_repair_prompts(self) -> None:
        self.assertEqual(
            doctor.derive_route("STALE", "STALE", True, False, doctor.TaskSummary(), False, "NONE")[1],
            "REQ-10",
        )
        self.assertEqual(
            doctor.derive_route(
                "APPROVED_FOR_DESIGN",
                "STALE",
                True,
                False,
                doctor.TaskSummary(),
                False,
                "NONE",
            )[1],
            "DESIGN-10",
        )

    def test_uninitialized_snapshot_is_still_structurally_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            tasks_path = project / "docs/project/TASKS.md"
            text = tasks_path.read_text(encoding="utf-8").replace(
                "| Maximum workers | `1` |\n", "", 1
            )
            tasks_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("TASK_SNAPSHOT", codes(report))

    def test_task_write_set_is_bound_to_gate_b_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            self.initialize_task_plan(project, ready_task("infrastructure/**"))

            report = doctor.inspect_project(project)

        self.assertIn("TASK_OUTSIDE_WRITE_BOUNDARY", codes(report))

    def test_paused_resume_requires_git_and_worktree_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Doctor Test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "doctor@example.test"], check=True)
            tracked = root / "tracked.txt"
            tracked.write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "baseline"], check=True)
            head = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            snapshot = {
                "Baseline commit": head,
                "Last known-green commit": head,
                "Protected dirty paths": "NONE",
            }
            clean_context = doctor.Context(root=root)
            doctor.validate_resume_repository(clean_context, snapshot)
            tracked.write_text("unexpected\n", encoding="utf-8")
            dirty_context = doctor.Context(root=root)
            doctor.validate_resume_repository(dirty_context, snapshot)

        self.assertFalse(clean_context.diagnostics)
        self.assertIn("CONSTRUCTION_WORKTREE_DRIFT", {item.code for item in dirty_context.diagnostics})

    def test_current_gate_b_and_checkpoint_states_require_real_git_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            prd_path = project / "docs/project/PRD.md"
            prd_path.write_text(
                approve_gate_b(approve_gate_a(prd_path.read_text(encoding="utf-8"))),
                encoding="utf-8",
            )
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            current_greenfield_state(state, gate_b=True)
            state_path.write_text(json.dumps(state), encoding="utf-8")
            tasks_path = project / "docs/project/TASKS.md"
            tasks_path.write_text(
                current_task_snapshot(tasks_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )

            no_git_report = doctor.inspect_project(project)

        self.assertIn("GATE_B_GIT_UNVERIFIED", codes(no_git_report))
        self.assertIn("CONSTRUCTION_GIT_UNVERIFIED", codes(no_git_report))

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "Authorized baseline commit",
                "`ffffffffffffffffffffffffffffffffffffffff`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")
            tasks_path = project / "docs/project/TASKS.md"
            tasks_path.write_text(
                set_table_value(
                    tasks_path.read_text(encoding="utf-8"),
                    "## Active execution snapshot",
                    "## Coordinator contract",
                    "Baseline commit",
                    "`ffffffffffffffffffffffffffffffffffffffff`",
                ),
                encoding="utf-8",
            )

            fabricated_report = doctor.inspect_project(project)

        self.assertIn("GATE_B_GIT_UNVERIFIED", codes(fabricated_report))
        self.assertIn("CONSTRUCTION_GIT_UNVERIFIED", codes(fabricated_report))

    def test_real_paused_checkpoint_accepts_ledger_dirt_and_rejects_code_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            self.pause_project_at_real_checkpoint(project)

            paused_report = doctor.inspect_project(project)

            tasks_path = project / "docs/project/TASKS.md"
            tasks_text = tasks_path.read_text(encoding="utf-8")
            prefixed_evidence = tasks_text.replace(
                "- Evidence: `NONE`", "- Evidence: `EV-0001`", 1
            ).replace("Evidence: NONE; External:", "Evidence: EV-00010; External:", 1)
            tasks_path.write_text(prefixed_evidence, encoding="utf-8")
            evidence_prefix_report = doctor.inspect_project(project)
            tasks_path.write_text(tasks_text, encoding="utf-8")

            tasks_path.write_text(
                tasks_text.replace("attempts=0/3", "attempts=0/99", 1),
                encoding="utf-8",
            )
            wrong_attempt_report = doctor.inspect_project(project)
            tasks_path.write_text(tasks_text, encoding="utf-8")

            verify_path = project / "docs/project/VERIFY.md"
            verify_text = verify_path.read_text(encoding="utf-8")
            verify_path.write_text(
                verify_text.replace("CP-0001", "CP-9999")
                + "\n```text\nCP-0001\n```\n",
                encoding="utf-8",
            )
            missing_receipt_report = doctor.inspect_project(project)
            verify_path.write_text(verify_text, encoding="utf-8")

            drift_path = project / "app" / "drift.py"
            drift_path.write_text("DRIFT = True\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(project), "add", "app/drift.py"], check=True
            )
            subprocess.run(
                ["git", "-C", str(project), "commit", "-qm", "unauthorized drift"],
                check=True,
            )
            drift_report = doctor.inspect_project(project)

        self.assertNotIn("CONSTRUCTION_GIT_UNVERIFIED", codes(paused_report))
        self.assertNotIn("CONSTRUCTION_CHECKPOINT_UNVERIFIED", codes(paused_report))
        self.assertNotIn("CONSTRUCTION_WORKTREE_DRIFT", codes(paused_report))
        self.assertIn("CONSTRUCTION_CHECKPOINT_UNVERIFIED", codes(evidence_prefix_report))
        self.assertIn("CONSTRUCTION_CHECKPOINT_UNVERIFIED", codes(wrong_attempt_report))
        self.assertIn("CONSTRUCTION_CHECKPOINT_UNVERIFIED", codes(missing_receipt_report))
        self.assertIn("CONSTRUCTION_GIT_DRIFT", codes(drift_report))

    def test_route_function_handles_construction_modes(self) -> None:
        uninitialized = doctor.TaskSummary(plan_revision=None)
        self.assertEqual(
            doctor.derive_route(
                "APPROVED_FOR_DESIGN",
                "APPROVED_FOR_CONSTRUCTION",
                True,
                True,
                uninitialized,
                True,
                "NONE",
            )[1],
            "TASK-10",
        )
        multiple = doctor.TaskSummary(
            plan_revision="PLAN-0001",
            plan_state="CURRENT",
            statuses={"TASK-001": "READY", "TASK-002": "READY"},
            ready=["TASK-001", "TASK-002"],
        )
        self.assertEqual(
            doctor.derive_route(
                "APPROVED_FOR_DESIGN",
                "APPROVED_FOR_CONSTRUCTION",
                True,
                True,
                multiple,
                True,
                "NONE",
            )[1],
            "BUILD-20",
        )

    def test_plan_state_and_release_state_have_explicit_routes(self) -> None:
        stale = doctor.TaskSummary(plan_revision="PLAN-0001", plan_state="STALE")
        self.assertEqual(
            doctor.derive_route(
                "APPROVED_FOR_DESIGN",
                "APPROVED_FOR_CONSTRUCTION",
                True,
                True,
                stale,
                True,
                "NONE",
            )[1],
            "TASK-10",
        )
        terminal = doctor.TaskSummary(
            plan_revision="PLAN-0001",
            plan_state="CURRENT",
            statuses={"TASK-001": "DONE"},
        )
        expected = {
            "NOT_READY": "RELEASE-10",
            "READY_TO_DEPLOY": "AWS-10",
            "RELEASE_VERIFIED": "STOP",
        }
        for release_state, prompt in expected.items():
            with self.subTest(release_state=release_state):
                self.assertEqual(
                    doctor.derive_route(
                        "APPROVED_FOR_DESIGN",
                        "APPROVED_FOR_CONSTRUCTION",
                        True,
                        True,
                        terminal,
                        True,
                        "NONE",
                        release_state,
                    )[1],
                    prompt,
                )


    def test_greenfield_repository_does_not_infer_a_new_application(self) -> None:
        text = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")

        contract, issues = doctor.derive_intake_foundation_contract(
            text, "greenfield", grandfather_current_gate_a=False
        )

        self.assertEqual(issues, [])
        self.assertEqual(contract.repository_mode, "GREENFIELD")
        self.assertIsNone(contract.owner_work_context)
        self.assertEqual(contract.status, "FOUNDATION_REQUIRED")
        self.assertIn("OWNER_WORK_CONTEXT", contract.missing_fields)
        self.assertIsNotNone(contract.pending_card)
        assert contract.pending_card is not None
        self.assertEqual(len(contract.pending_card.questions), 3)
        self.assertEqual(
            contract.pending_card.questions[0].prompt,
            "What are you starting with?",
        )
        self.assertIsNone(contract.pending_card.questions[0].recommended)
        self.assertFalse(contract.pending_card.accept_all_allowed)

    def test_intake_selection_requires_current_owner_provenance_and_detail(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        current_response = (
            "OWNER_RESPONSE: OWNER-MSG-0002; CARD: INTAKE-CARD-0001; REVISION: 1"
        )
        cases = {
            "assistant-authored selection": set_intake_card_resolution(
                source, "INTAKE-Q-0001", "A"
            ),
            "stale card response": set_intake_card_resolution(
                source,
                "INTAKE-Q-0001",
                "A",
                owner_response=(
                    "OWNER_RESPONSE: OWNER-MSG-0002; CARD: INTAKE-CARD-0999; "
                    "REVISION: 1"
                ),
            ),
            "missing required detail": set_intake_card_resolution(
                source,
                "INTAKE-Q-0001",
                "B",
                owner_response=current_response,
            ),
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                _contract, issues = doctor.derive_intake_foundation_contract(
                    text, "greenfield", grandfather_current_gate_a=False
                )
                self.assertIn(
                    "INTAKE_SELECTION_PROVENANCE_INVALID",
                    {code for code, _message in issues},
                )

    def test_complete_owner_grounded_intake_is_ready_for_requirements(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        completed = complete_intake_foundation(source)

        contract, issues = doctor.derive_intake_foundation_contract(
            completed,
            "greenfield",
            grandfather_current_gate_a=False,
        )
        response_table = doctor.contract_table_after_heading(
            completed,
            doctor.INTAKE_RESPONSE_REGISTER_HEADING,
            doctor.INTAKE_RESPONSE_REGISTER_HEADERS,
        )
        card_table = doctor.contract_table_after_heading(
            completed,
            doctor.INTAKE_CARD_HEADING,
            doctor.INTAKE_CARD_HEADERS,
        )

        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "READY_FOR_REQUIREMENTS")
        self.assertEqual(contract.owner_work_context, "NEW_APPLICATION")
        self.assertEqual(len(contract.basis_ids), 7)
        self.assertEqual(contract.missing_fields, ())
        self.assertIsNone(contract.pending_card)
        assert response_table is not None
        assert card_table is not None
        self.assertEqual(len(response_table.rows), 5)
        self.assertEqual(
            {row[0] for row in response_table.rows},
            {"OWNER-MSG-0001", "OWNER-MSG-0002"},
        )
        self.assertEqual({row[0] for row in card_table.rows}, {"INTAKE-CARD-0002"})
        foundation_table = doctor.contract_table_after_heading(
            completed,
            doctor.INTAKE_FOUNDATION_HEADING,
            doctor.INTAKE_FOUNDATION_HEADERS,
        )
        assert foundation_table is not None
        historical = {row[0]: row[5] for row in foundation_table.rows}
        self.assertIn("OWNER-MSG-0001", historical["INTAKE-0001"])
        self.assertIn("OWNER-MSG-0001", historical["INTAKE-0005"])
        self.assertIn("OWNER-MSG-0002", historical["INTAKE-0006"])
        self.assertIn("OWNER-MSG-0002", historical["INTAKE-0007"])

    def test_owner_work_context_choices_map_exactly_to_semantic_values(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        expected = {
            "A": "NEW_APPLICATION",
            "B": "EXISTING_APPLICATION_CHANGE",
            "C": "REPAIR_OR_MIGRATION",
        }
        for choice, owner_work_context in expected.items():
            with self.subTest(choice=choice):
                contract, issues = doctor.derive_intake_foundation_contract(
                    complete_intake_foundation(source, work_context_choice=choice),
                    "greenfield",
                    grandfather_current_gate_a=False,
                )
                self.assertEqual(issues, [])
                self.assertEqual(contract.owner_work_context, owner_work_context)

    def test_partial_intake_rerenders_and_parses_original_remaining_keys(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        initial, issues = doctor.derive_intake_foundation_contract(
            source, "greenfield", grandfather_current_gate_a=False
        )
        self.assertEqual(issues, [])
        assert initial.pending_card is not None
        digest = initial.pending_card.canonical_sha256
        provenance = intake_provenance(
            "OWNER-MSG-0001", "INTAKE-CARD-0001", 1, digest, "INTAKE-Q-0001", "A"
        )
        partial = set_intake_card_resolution(
            source, "INTAKE-Q-0001", "A", owner_response=provenance
        )
        partial = confirm_intake_foundation(
            partial,
            {"INTAKE-0001": "NEW_APPLICATION"},
            {"INTAKE-0001": provenance},
        )
        partial = replace_contract_table(
            partial,
            doctor.INTAKE_RESPONSE_REGISTER_HEADING,
            doctor.INTAKE_RESPONSE_REGISTER_HEADERS,
            [(
                "OWNER-MSG-0001", "INTAKE-CARD-0001", "1", digest, "1",
                "INTAKE-Q-0001", "A", "NONE", "INTAKE-0001",
            )],
        )
        contract, issues = doctor.derive_intake_foundation_contract(
            partial, "greenfield", grandfather_current_gate_a=False
        )
        self.assertEqual(issues, [])
        assert contract.pending_card is not None
        self.assertEqual(
            [question.reply_key for question in contract.pending_card.questions],
            ["2", "3"],
        )
        remaining_digest = contract.pending_card.canonical_sha256
        parsed = doctor.parse_intake_owner_response(
            f"{contract.pending_card.reply_token}; 2: Users; 3: First useful result",
            contract.pending_card.to_dict(),
            expected_card_id="INTAKE-CARD-0001",
            expected_revision=1,
            expected_sha256=remaining_digest,
            owner_response_id="OWNER-MSG-0002",
        )
        self.assertEqual(parsed.status, "PASS", parsed.to_dict())
        self.assertEqual(
            [answer.reply_key for answer in parsed.answers], ["2", "3"]
        )

    def test_response_register_rejects_repeated_questions_and_empty_facts(self) -> None:
        source = complete_intake_foundation(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        table = doctor.contract_table_after_heading(
            source,
            doctor.INTAKE_RESPONSE_REGISTER_HEADING,
            doctor.INTAKE_RESPONSE_REGISTER_HEADERS,
        )
        assert table is not None
        repeated_row = list(table.rows[0])
        repeated_row[0] = "OWNER-MSG-0003"
        repeated_row[3] = "sha256:" + "e" * 64
        repeated = list(table.rows) + [tuple(repeated_row)]
        repeated_text = replace_contract_table(
            source,
            doctor.INTAKE_RESPONSE_REGISTER_HEADING,
            doctor.INTAKE_RESPONSE_REGISTER_HEADERS,
            repeated,
        )
        _contract, issues = doctor.derive_intake_foundation_contract(
            repeated_text, "greenfield", grandfather_current_gate_a=False
        )
        self.assertIn(
            "INTAKE_RESPONSE_REGISTER_INVALID",
            {code for code, _message in issues},
        )
        empty_fact = list(table.rows) + [(
            "OWNER-MSG-0003", "INTAKE-CARD-0999", "1", "sha256:" + "f" * 64,
            "1", "INTAKE-Q-0999", "RESPONSE", "NONE", "INTAKE-0001",
        )]
        empty_text = replace_contract_table(
            source,
            doctor.INTAKE_RESPONSE_REGISTER_HEADING,
            doctor.INTAKE_RESPONSE_REGISTER_HEADERS,
            empty_fact,
        )
        _contract, issues = doctor.derive_intake_foundation_contract(
            empty_text, "greenfield", grandfather_current_gate_a=False
        )
        self.assertTrue(
            any(
                code == "INTAKE_RESPONSE_REGISTER_INVALID"
                and "concrete factual detail" in message
                for code, message in issues
            )
        )
        placeholder_row = list(table.rows[1])
        placeholder_row[7] = "NONE - unavailable"
        placeholder_text = replace_contract_table(
            source,
            doctor.INTAKE_RESPONSE_REGISTER_HEADING,
            doctor.INTAKE_RESPONSE_REGISTER_HEADERS,
            [table.rows[0], tuple(placeholder_row), *table.rows[2:]],
        )
        _contract, issues = doctor.derive_intake_foundation_contract(
            placeholder_text, "greenfield", grandfather_current_gate_a=False
        )
        self.assertIn(
            "INTAKE_RESPONSE_REGISTER_INVALID", {code for code, _message in issues}
        )

    def test_intake_parser_cli_is_normalizing_partial_stale_and_zero_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            report = doctor.inspect_project(project)
            self.assertTrue(report["ok"], report["diagnostics"])
            card = report["intake_foundation"]["pending_card"]
            assert isinstance(card, dict)

            def snapshot() -> dict[str, str]:
                return {
                    path.relative_to(project).as_posix(): hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                    for path in project.rglob("*")
                    if path.is_file()
                }

            baseline = snapshot()
            command = [
                sys.executable,
                "scripts/bootstrap_doctor.py",
                "--root",
                str(project),
                "--parse-intake-response",
                "--input-stdin",
                "--presented-card-id",
                str(card["card_id"]),
                "--presented-card-revision",
                str(card["revision"]),
                "--presented-card-sha256",
                str(card["canonical_sha256"]),
                "--json",
            ]
            environment = dict(os.environ)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"

            def parse(reply: str, *, stale: bool = False) -> tuple[int, dict[str, object]]:
                current = list(command)
                if stale:
                    digest_index = current.index("--presented-card-sha256") + 1
                    current[digest_index] = "sha256:" + "f" * 64
                completed = subprocess.run(
                    current,
                    cwd=project,
                    input=f"{card['reply_token']}; {reply}",
                    capture_output=True,
                    text=True,
                    check=False,
                    env=environment,
                )
                self.assertEqual(completed.stderr, "", completed.stderr)
                return completed.returncode, json.loads(completed.stdout)

            valid_exit, valid = parse(
                "1a; 2: Development users need a clear outcome; "
                "3: The first release displays that outcome"
            )
            partial_exit, partial = parse(
                "2: Development users need a clear outcome"
            )
            stale_exit, stale = parse("1A", stale=True)
            rejected_exit, rejected = parse("1A; 1B")
            secret_exit, secret = parse(
                "2: aws_secret_access_key=synthetic-value"
            )

            self.assertEqual(valid_exit, 0)
            self.assertEqual(valid["status"], "PASS")
            self.assertEqual(valid["owner_response_id"], "OWNER-MSG-0001")
            self.assertEqual(valid["answers"][0]["selection"], "A")
            self.assertEqual(valid["unresolved_reply_keys"], [])
            self.assertEqual(partial_exit, 0)
            self.assertEqual(partial["status"], "PASS")
            self.assertEqual(partial["unresolved_reply_keys"], ["1", "3"])
            self.assertEqual(
                partial["owner_status"]["required_from_you"],
                "Nothing until Codex records them and presents only the remaining questions.",
            )
            self.assertEqual(stale_exit, 2)
            self.assertIn(
                "INTAKE_CARD_STALE",
                {item["code"] for item in stale["errors"]},
            )
            self.assertEqual(rejected_exit, 2)
            self.assertIn(
                "INTAKE_REPLY_KEY_DUPLICATE",
                {item["code"] for item in rejected["errors"]},
            )
            self.assertEqual(secret_exit, 2)
            self.assertIn(
                "INTAKE_SECRET_MATERIAL",
                {item["code"] for item in secret["errors"]},
            )
            self.assertNotIn(
                "synthetic-value", json.dumps(secret, sort_keys=True)
            )
            self.assertEqual(snapshot(), baseline)

    def test_cli_rejects_a_delayed_reply_bound_to_the_previous_card(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            old = doctor.inspect_project(project)["intake_foundation"]["pending_card"]
            assert isinstance(old, dict)
            delayed = f"{old['reply_token']}; 1A"
            prd = project / "docs/project/PRD.md"
            prd.write_text(
                prd.read_text(encoding="utf-8").replace(
                    "What are you starting with?",
                    "Which starting point matches this work?",
                    1,
                ),
                encoding="utf-8",
            )
            refresh_control_hashes(project)
            current = doctor.inspect_project(project)["intake_foundation"]["pending_card"]
            assert isinstance(current, dict)
            self.assertNotEqual(old["reply_token"], current["reply_token"])
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/bootstrap_doctor.py",
                    "--root",
                    str(project),
                    "--parse-intake-response",
                    "--input-stdin",
                    "--presented-card-id",
                    str(current["card_id"]),
                    "--presented-card-revision",
                    str(current["revision"]),
                    "--presented-card-sha256",
                    str(current["canonical_sha256"]),
                    "--json",
                ],
                cwd=project,
                input=delayed,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            result = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("INTAKE_CARD_STALE", {item["code"] for item in result["errors"]})

    def test_intake_contract_migrates_only_unapproved_legacy_projects(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        foundation_start = source.index(doctor.INTAKE_FOUNDATION_HEADING)
        register_start = source.index(doctor.INTAKE_RESPONSE_REGISTER_HEADING)
        card_start = source.index(doctor.INTAKE_CARD_HEADING)
        legacy_foundation_lines: list[str] = []
        for line in source[foundation_start:register_start].splitlines(keepends=True):
            cells = doctor.split_markdown_table_row(line)
            if cells and len(cells) == 6:
                ending = "\n" if line.endswith("\n") else ""
                line = "| " + " | ".join(cells[:-1]) + " |" + ending
            legacy_foundation_lines.append(line)
        legacy = (
            source[:foundation_start]
            + "".join(legacy_foundation_lines)
            + source[card_start:]
        )

        unapproved, unapproved_issues = doctor.derive_intake_foundation_contract(
            legacy, "greenfield", grandfather_current_gate_a=False
        )
        approved, approved_issues = doctor.derive_intake_foundation_contract(
            legacy, "greenfield", grandfather_current_gate_a=True
        )

        self.assertEqual(unapproved.status, "FOUNDATION_REQUIRED")
        self.assertIn(
            "INTAKE_CONTRACT_MIGRATION_REQUIRED",
            {code for code, _message in unapproved_issues},
        )
        self.assertTrue(
            any(
                "owner-response provenance" in message
                and "normalized response register" in message
                and "unconfirmed context" in message
                and "without synthesizing" in message
                for code, message in unapproved_issues
                if code == "INTAKE_CONTRACT_MIGRATION_REQUIRED"
            )
        )
        self.assertEqual(approved_issues, [])
        self.assertEqual(approved.status, "READY_FOR_REQUIREMENTS")
        self.assertTrue(approved.grandfathered_approved_gate_a)

    def test_missing_modern_intake_record_names_the_exact_migration_target(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        register_start = source.index(doctor.INTAKE_RESPONSE_REGISTER_HEADING)
        card_start = source.index(doctor.INTAKE_CARD_HEADING)
        missing_register = source[:register_start] + source[card_start:]

        contract, issues = doctor.derive_intake_foundation_contract(
            missing_register,
            "greenfield",
            grandfather_current_gate_a=False,
        )

        self.assertEqual(contract.status, "FOUNDATION_REQUIRED")
        self.assertIn(
            (
                "INTAKE_CONTRACT_MIGRATION_REQUIRED",
                "Unapproved project is missing: normalized response register",
            ),
            issues,
        )


    def test_owner_input_creates_a_turn_boundary_but_automatic_work_does_not(self) -> None:
        owner_input = doctor.derive_interaction(
            "INTAKE_REQUIRED",
            "INTAKE-10",
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=False,
            aws_execution_planning_ready=False,
        )
        automatic = doctor.derive_interaction(
            "DESIGN_REQUIRED",
            "DESIGN-10",
            has_errors=False,
            diagnostic_codes=[],
            design_aws_core_ready=False,
            aws_execution_planning_ready=False,
        )

        self.assertTrue(owner_input["turn_boundary_required"])
        self.assertFalse(owner_input["automatic_continuation_allowed"])
        self.assertFalse(automatic["turn_boundary_required"])
        self.assertTrue(automatic["automatic_continuation_allowed"])

    def test_unproven_selection_is_agent_correctable_without_owner_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            prd_path = project / "docs/project/PRD.md"
            text = set_intake_card_resolution(
                prd_path.read_text(encoding="utf-8"),
                "INTAKE-Q-0001",
                "A",
            )
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("INTAKE_SELECTION_PROVENANCE_INVALID", codes(report))
        item = next(
            item
            for item in report["remediation"]["items"]
            if item["diagnostic_code"] == "INTAKE_SELECTION_PROVENANCE_INVALID"
        )
        self.assertEqual(item["responsible_party"], "CODEX")
        self.assertEqual(item["category"], "AGENT_CORRECTION")
        self.assertTrue(item["automatic_correction_allowed"])
        self.assertEqual(
            report["remediation"]["next_action"]["action_kind"],
            "CORRECT_AND_REVALIDATE",
        )
        self.assertFalse(report["interaction"]["turn_boundary_required"])

    def test_real_cli_forwards_remediation_fingerprint_and_escalates_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            prd_path = project / "docs/project/PRD.md"
            text = set_intake_card_resolution(
                prd_path.read_text(encoding="utf-8"),
                "INTAKE-Q-0001",
                "A",
            )
            prd_path.write_text(text, encoding="utf-8")
            refresh_control_hashes(project)
            command = [
                sys.executable,
                "scripts/bootstrap_doctor.py",
                "--root",
                str(project),
                "--json",
            ]
            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            first_process = subprocess.run(
                command,
                cwd=project,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )
            self.assertEqual(first_process.returncode, 1)
            first = json.loads(first_process.stdout)
            fingerprint = first["remediation"]["fingerprint"]
            self.assertEqual(
                first["remediation"]["next_action"]["responsible_party"], "CODEX"
            )

            repeated_process = subprocess.run(
                command + ["--prior-remediation-fingerprint", fingerprint],
                cwd=project,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )
            self.assertEqual(repeated_process.returncode, 1)
            repeated = json.loads(repeated_process.stdout)
            self.assertEqual(repeated["remediation"]["retry_state"], "REPEATED")
            self.assertEqual(
                repeated["remediation"]["next_action"]["responsible_party"],
                "HUMAN_REVIEWER",
            )
            self.assertEqual(repeated["remediation"]["fingerprint"], fingerprint)
            invalid_fingerprint = subprocess.run(
                command + ["--prior-remediation-fingerprint", "sha256:ABC"],
                cwd=project,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )
            self.assertEqual(invalid_fingerprint.returncode, 2)
            self.assertIn(
                "--prior-remediation-fingerprint must be sha256:",
                invalid_fingerprint.stderr,
            )



    def test_generated_intake_provenance_defects_are_agent_correctable(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_intake_foundation(source)
        foundation_table = doctor.contract_table_after_heading(
            complete,
            doctor.INTAKE_FOUNDATION_HEADING,
            doctor.INTAKE_FOUNDATION_HEADERS,
        )
        response_table = doctor.contract_table_after_heading(
            complete,
            doctor.INTAKE_RESPONSE_REGISTER_HEADING,
            doctor.INTAKE_RESPONSE_REGISTER_HEADERS,
        )
        assert foundation_table is not None
        assert response_table is not None
        foundation_rows = [list(row) for row in foundation_table.rows]
        foundation_rows[0][5] = "NONE"
        invalid_foundation = replace_contract_table(
            complete,
            doctor.INTAKE_FOUNDATION_HEADING,
            doctor.INTAKE_FOUNDATION_HEADERS,
            [tuple(row) for row in foundation_rows],
        )
        response_rows = [list(row) for row in response_table.rows]
        response_rows[0][0] = "OWNER-MSG-invalid"
        invalid_register = replace_contract_table(
            complete,
            doctor.INTAKE_RESPONSE_REGISTER_HEADING,
            doctor.INTAKE_RESPONSE_REGISTER_HEADERS,
            [tuple(row) for row in response_rows],
        )
        cases = {
            "INTAKE_FOUNDATION_PROVENANCE_INVALID": invalid_foundation,
            "INTAKE_RESPONSE_REGISTER_INVALID": invalid_register,
        }

        for expected_code, prd_text in cases.items():
            with self.subTest(code=expected_code), tempfile.TemporaryDirectory() as directory:
                project = self.copy_project(Path(directory))
                (project / "docs/project/PRD.md").write_text(
                    prd_text, encoding="utf-8"
                )
                report = doctor.inspect_project(project)

            self.assertIn(expected_code, codes(report))
            item = next(
                item
                for item in report["remediation"]["items"]
                if item["diagnostic_code"] == expected_code
            )
            self.assertEqual(item["responsible_party"], "CODEX")
            self.assertEqual(item["category"], "AGENT_CORRECTION")
            self.assertTrue(item["automatic_correction_allowed"])
            self.assertFalse(report["interaction"]["turn_boundary_required"])

    def test_incomplete_intake_routes_as_open_decisions_not_corruption(self) -> None:
        choices = {
            "mode": ("Project mode", "`greenfield`", "greenfield"),
            "delivery_profile": ("Delivery profile", "`high-risk`", "high-risk"),
            "effective_risk": ("Effective risk", "`high`", "high"),
            "aws_lane": ("AWS lane", "`explicit-gate`", "explicit-gate"),
        }
        for missing_key in choices:
            with self.subTest(missing=missing_key), tempfile.TemporaryDirectory() as directory:
                project = self.copy_project(Path(directory))
                prd_path = project / "docs/project/PRD.md"
                text = prd_path.read_text(encoding="utf-8")
                state_path = project / "bootstrap.yaml"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state["project"]["brownfield_baseline"] = "NOT_APPLICABLE"
                for key, (label, rendered, state_value) in choices.items():
                    if key == missing_key:
                        continue
                    text = set_table_value(
                        text,
                        "## Document status",
                        "## 1. Workload profile",
                        label,
                        rendered,
                    )
                    state["project"][key] = state_value
                prd_path.write_text(text, encoding="utf-8")
                state_path.write_text(json.dumps(state), encoding="utf-8")

                report = doctor.inspect_project(project)

                self.assertTrue(report["ok"], report["diagnostics"])
                self.assertNotIn("PROJECT_VOCABULARY", codes(report))
                self.assertNotIn("PROJECT_SELECTION_REQUIRED", codes(report))
                self.assertNotIn("STATE_PRD_DRIFT", codes(report))
                self.assertEqual(report["next_prompt"], "INTAKE-10")
                self.assertEqual(report["status"], "READY")
                self.assertEqual(report["interaction"]["response_mode"], "OWNER_UPDATE")
                self.assertEqual(report["interaction"]["state"], "NEEDS_INPUT")
                self.assertEqual(
                    report["interaction"]["owner_action_kind"],
                    "ANSWER_OPEN_DECISIONS",
                )
                self.assertEqual(
                    report["interaction"]["route_reason_code"], "INTAKE_REQUIRED"
                )

    def test_malformed_multi_choice_intake_value_remains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## Document status",
                "## 1. Workload profile",
                "Project mode",
                "`greenfield` / `brownfield` / `sideways`",
            )
            prd_path.write_text(text, encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertFalse(report["ok"])
        self.assertIn("PROJECT_VOCABULARY", codes(report))
        self.assertNotIn("PROJECT_SELECTION_REQUIRED", codes(report))
        self.assertEqual(
            report["remediation"]["next_action"]["action_kind"],
            "REVIEW_SAFETY_BLOCKER",
        )

    def test_unsupported_intake_value_remains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            values = {
                "Project mode": "`sideways`",
                "Delivery profile": "`high-risk`",
                "Effective risk": "`high`",
                "AWS lane": "`explicit-gate`",
            }
            for label, value in values.items():
                text = set_table_value(
                    text,
                    "## Document status",
                    "## 1. Workload profile",
                    label,
                    value,
                )
            prd_path.write_text(text, encoding="utf-8")
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"].update(
                {
                    "delivery_profile": "high-risk",
                    "effective_risk": "high",
                    "aws_lane": "explicit-gate",
                    "brownfield_baseline": "NOT_APPLICABLE",
                }
            )
            state_path.write_text(json.dumps(state), encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertFalse(report["ok"])
        self.assertIn("PROJECT_VOCABULARY", codes(report))
        self.assertNotIn("PROJECT_SELECTION_REQUIRED", codes(report))
        self.assertEqual(
            report["remediation"]["next_action"]["action_kind"],
            "REVIEW_SAFETY_BLOCKER",
        )
    def test_schema_13_requirements_projection_is_grounded_and_migratable(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        text = approve_gate_a(source)
        intake_contract, intake_issues = doctor.derive_intake_foundation_contract(
            text,
            "greenfield",
            grandfather_current_gate_a=False,
        )
        self.assertEqual(intake_issues, [])
        self.assertEqual(intake_contract.status, "READY_FOR_REQUIREMENTS")

        contract, issues = doctor.derive_requirements_contract(
            text,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "READY")
        self.assertEqual(contract.schema_version, "1.3")
        self.assertEqual(contract.actor_ids, ("ACT-001",))
        self.assertEqual(contract.journey_ids, ("JOURNEY-001",))
        self.assertEqual(
            set(contract.acceptance_ids),
            {f"AC-{identifier}" for identifier in contract.requirement_ids},
        )
        self.assertRegex(contract.canonical_sha256 or "", r"^sha256:[0-9a-f]{64}$")

        ungrounded = text.replace(
            "INTAKE-0002, INTAKE-0003, INTAKE-0004, INTAKE-0005, INTAKE-0007",
            "INTAKE-9999",
            1,
        )
        blocked, blocked_issues = doctor.derive_requirements_contract(
            ungrounded,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertIn(
            "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
            {code for code, _message in blocked_issues},
        )

        legacy = text.replace(
            "| Project contract schema | `1.3` |",
            "| Project contract schema | `1.2` |",
            1,
        )
        migration, migration_issues = doctor.derive_requirements_contract(
            legacy,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(migration.status, "MIGRATION_REQUIRED")
        self.assertEqual(
            migration.missing_records,
            ("Project contract schema 1.3",),
        )
        self.assertEqual(
            {code for code, _message in migration_issues},
            {"PROJECT_CONTRACT_MIGRATION_REQUIRED"},
        )
        mislabeled, mislabeled_issues = doctor.derive_requirements_contract(
            legacy,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=True,
        )
        self.assertEqual(mislabeled.status, "MIGRATION_REQUIRED")
        self.assertEqual(
            {code for code, _message in mislabeled_issues},
            {"PROJECT_CONTRACT_MIGRATION_REQUIRED"},
        )

        exact_legacy = """## Document status

| Field | Value |
|---|---|
| Current requirements revision | `REQ-0001` |
| Gate A derived status | `APPROVED_FOR_DESIGN` |

## Approved legacy requirements

| ID | Requirement | Acceptance criteria |
|---|---|---|
| FR-001 | The application SHALL preserve the approved outcome. | An observed test confirms the approved outcome. |
"""
        grandfathered, grandfathered_issues = doctor.derive_requirements_contract(
            exact_legacy,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=True,
        )
        self.assertEqual(grandfathered_issues, [])
        self.assertEqual(grandfathered.status, "GRANDFATHERED")
        self.assertEqual(grandfathered.requirement_ids, ("FR-001",))
        self.assertTrue(grandfathered.grandfathered_approved_gate_a)

    def test_rich_use_case_trigger_cannot_be_silently_ignored(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        text = approve_gate_a(source)
        intake_contract, _issues = doctor.derive_intake_foundation_contract(
            text,
            "greenfield",
            grandfather_current_gate_a=False,
        )

        high_risk, high_risk_issues = doctor.derive_requirements_contract(
            text,
            "high",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(high_risk.status, "BLOCKED")
        self.assertIn(
            "RICH_USE_CASE_REQUIRED",
            {code for code, _message in high_risk_issues},
        )

        explicit_required = text.replace(
            "| NOT_APPLICABLE | NOT_APPLICABLE - low-risk single-actor synchronous fixture | NONE |",
            "| REQUIRED | CONFIDENTIAL_MUTATION | USECASE-001 |",
            1,
        )
        required_contract, required_issues = doctor.derive_requirements_contract(
            explicit_required,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(required_contract.status, "BLOCKED")
        self.assertIn(
            "RICH_USE_CASE_INVALID",
            {code for code, _message in required_issues},
        )

    def test_inspect_project_bridges_exact_legacy_gate_a_analysis_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            self.approve_project(project, gate_b=False)
            prd_path = project / "docs/project/PRD.md"
            prd_path.write_text(
                exact_legacy_requirements_projection(
                    prd_path.read_text(encoding="utf-8")
                ),
                encoding="utf-8",
            )

            report = doctor.inspect_project(project)

        self.assertEqual(report["requirements_contract"]["status"], "GRANDFATHERED")
        self.assertTrue(
            report["requirements_contract"]["grandfathered_approved_gate_a"]
        )
        self.assertNotIn("PROJECT_CONTRACT_MIGRATION_REQUIRED", codes(report))
        self.assertEqual(report["next_prompt"], "DESIGN-10")

    def test_schema_five_project_design_is_digest_bound_and_fail_closed(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(source)
        ready, issues = doctor.derive_design_contract(
            complete,
            "DES-0001",
            required=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(ready.status, "READY")
        self.assertEqual(ready.schema_version, 5)
        self.assertEqual(ready.project_contract.status, "READY")
        self.assertEqual(ready.project_contract.interface_ids, ("API-001",))
        self.assertEqual(ready.project_contract.boundary_ids, ("BOUNDARY-001",))
        self.assertEqual(
            ready.project_contract.first_wave.wave_contract_id,
            "WAVE-001",
        )
        self.assertIsNone(ready.project_contract.spike)

        changed_text = complete.replace(
            "100 requests per minute",
            "200 requests per minute",
            1,
        )
        changed, changed_issues = doctor.derive_design_contract(
            changed_text,
            "DES-0001",
            required=True,
        )
        self.assertEqual(changed_issues, [])
        self.assertNotEqual(
            ready.project_contract.canonical_sha256,
            changed.project_contract.canonical_sha256,
        )
        self.assertNotEqual(ready.canonical_sha256, changed.canonical_sha256)

        unsafe = complete.replace(
            "Server verifies the caller may request the local outcome",
            "TODO",
            1,
        )
        blocked, blocked_issues = doctor.derive_design_contract(
            unsafe,
            "DES-0001",
            required=True,
        )
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertTrue(
            any("Authorization" in issue and "must be concrete" in issue for issue in blocked_issues),
            blocked_issues,
        )

    def test_schema_five_project_contract_rejects_false_ready_details(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(source)
        stateful = replace_contract_table(
            complete,
            doctor.STATE_APPLICABILITY_HEADING,
            doctor.STATE_APPLICABILITY_HEADERS,
            [("RESOURCE-001", "APPLICABLE", "LIFECYCLE_RESOURCE: FR-001", "STATE-001")],
        )
        stateful = replace_contract_table(
            stateful,
            doctor.STATE_REGISTER_HEADING,
            doctor.STATE_REGISTER_HEADERS,
            [(
                "STATE-001", "RESOURCE-001", "PENDING, READY", "PENDING",
                "PENDING -> READY", "READY", "Reject invalid transitions",
                "FR-001", "TEST-999",
            )],
        )
        cases = {
            "client-only authorization": (
                complete.replace(
                    "Server verifies the caller may request the local outcome",
                    "Client sends its caller identifier",
                    1,
                ),
                "Authorization must be server-side",
            ),
            "vague timeout": (
                complete.replace("2 seconds", "fast", 1),
                "Timeout bound must contain a numeric measurable bound",
            ),
            "invented boundary validation": (
                complete.replace("AC-FR-001, AC-FR-002", "TEST-999", 1),
                "unknown Validation IDs: TEST-999",
            ),
            "invented state validation": (
                stateful,
                "STATE-001: unknown Validation IDs: TEST-999",
            ),
            "unbound end-to-end Harness": (
                complete.replace(
                    "DES-0001, FR-001, JOURNEY-001, WAVE-001",
                    "DES-0001, FR-001",
                    1,
                ),
                "Basis IDs must include both JOURNEY-001 and WAVE-001",
            ),
        }
        for label, (changed, expected) in cases.items():
            with self.subTest(case=label):
                blocked, issues = doctor.derive_design_contract(
                    changed, "DES-0001", required=True
                )
                self.assertEqual(blocked.status, "BLOCKED")
                self.assertTrue(any(expected in issue for issue in issues), issues)

        mislabeled_current = complete.replace(
            "| Project design contract schema | `5` |\n", "", 1
        )
        migration, migration_issues = doctor.derive_design_contract(
            mislabeled_current,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(migration.project_contract.status, "MIGRATION_REQUIRED")
        self.assertFalse(migration.project_contract.grandfathered_v4)
        self.assertTrue(
            any("Project design contract schema 5" in issue for issue in migration_issues),
            migration_issues,
        )

    def test_exact_schema_four_shape_is_the_only_project_design_bridge(self) -> None:
        legacy_text = """## Document status

| Field | Value |
|---|---|
| Current design revision | `DES-0001` |
| Gate B derived status | `APPROVED_FOR_CONSTRUCTION` |

## 16. Interfaces and contracts

| Contract ID | Producer | Consumer | Schema or protocol | Authentication | Versioning | Idempotency |
|---|---|---|---|---|---|---|
| API-001 | Browser | Application | JSON over HTTPS | Approved identity token | Versioned path | Idempotency key |
"""
        requirements = doctor.RequirementsContract(
            schema_version="1.2",
            status="GRANDFATHERED",
            requirement_ids=("FR-001",),
            grandfathered_approved_gate_a=True,
        )
        coverage = doctor.CoverageContract(status="READY", work_kind="NEW_BUILD")
        harness = doctor.HarnessContract(
            status="READY",
            rows=(doctor.HarnessRow(
                "HARNESS-001", "End-to-end", "unittest", "Approved design",
                "DES-0001, FR-001", "python -m unittest tests.test_legacy",
                "docs/project/VERIFY.md#legacy", "REQUIRED",
            ),),
            required_ids=("HARNESS-001",),
        )
        legacy_ids = {"ARCH-0001", "TECH-0001", "PROP-001", "HARNESS-001"}

        grandfathered, issues = doctor.derive_project_design_contract(
            legacy_text,
            requirements,
            coverage,
            {"DES-0001", "FR-001"},
            harness,
            legacy_ids,
            required=True,
            grandfather_approved_v4=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(grandfathered.status, "GRANDFATHERED")
        self.assertTrue(grandfathered.grandfathered_v4)

        damaged_current, damaged_issues = doctor.derive_project_design_contract(
            legacy_text + "\n### State register\n",
            requirements,
            coverage,
            {"DES-0001", "FR-001"},
            harness,
            legacy_ids,
            required=True,
            grandfather_approved_v4=True,
        )
        self.assertEqual(damaged_current.status, "MIGRATION_REQUIRED")
        self.assertFalse(damaged_current.grandfathered_v4)
        self.assertTrue(damaged_issues)

    def test_new_build_wave_and_spike_are_executable_and_journey_bound(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(source)
        requirement_ids = sorted(doctor.authoritative_requirement_ids(complete))
        journey_one_ids = [item for item in requirement_ids if item != "FR-002"]
        split = replace_contract_table(
            complete,
            doctor.JOURNEY_HEADING,
            doctor.JOURNEY_HEADERS,
            [
                (
                    "JOURNEY-001", "ACT-001", "See the approved project outcome",
                    "The development user requests the local result",
                    "The current approved outcome is displayed",
                    "Invalid input is rejected without changing approved state",
                    ", ".join(journey_one_ids), "NONE",
                ),
                (
                    "JOURNEY-002", "ACT-001", "Reject invalid input",
                    "The development user submits invalid input",
                    "The invalid input is rejected",
                    "Approved state remains unchanged", "FR-002", "NONE",
                ),
            ],
        )
        coverage_table = doctor.contract_table_after_heading(
            split,
            doctor.REQUIREMENT_COVERAGE_HEADING,
            doctor.REQUIREMENT_COVERAGE_HEADERS,
        )
        assert coverage_table is not None
        split = replace_contract_table(
            split,
            doctor.REQUIREMENT_COVERAGE_HEADING,
            doctor.REQUIREMENT_COVERAGE_HEADERS,
            [
                (*row[:3], "JOURNEY-002", *row[4:])
                if row[0] == "FR-002" else row
                for row in coverage_table.rows
            ],
        )
        mismatched_wave = replace_contract_table(
            split,
            doctor.FIRST_WAVE_HEADING,
            doctor.FIRST_WAVE_HEADERS,
            [(
                "WAVE-001", "NEW_BUILD", "JOURNEY-001", "FR-001, FR-002",
                "AC-FR-001, AC-FR-002", "HARNESS-004", "NONE",
            )],
        )
        blocked, mismatch_issues = doctor.derive_design_contract(
            mismatched_wave, "DES-0001", required=True
        )
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertTrue(
            any(
                "first-wave requirement IDs are not owned by JOURNEY-001: FR-002"
                in issue
                for issue in mismatch_issues
            ),
            mismatch_issues,
        )

        spiked = replace_contract_table(
            complete,
            doctor.FIRST_WAVE_HEADING,
            doctor.FIRST_WAVE_HEADERS,
            [(
                "WAVE-001", "NEW_BUILD", "JOURNEY-001", "FR-001",
                "AC-FR-001", "HARNESS-004", "SPIKE-001",
            )],
        )
        spike_table = "\n".join([
            "| Spike ID | Blocking technical unknown | Time box | Disposable output boundary | Exit criterion | Required next action |",
            "|---|---|---|---|---|---|",
            "| SPIKE-001 | Verify the local adapter contract | MAX_ATTEMPTS: 2 | work/spike/** | python -m unittest tests.test_spike_exit | DISCARD_AND_BUILD_WALKING_SKELETON |",
        ])
        spiked = spiked.replace(
            "NOT_APPLICABLE - no prerequisite discovery is needed before the walking skeleton",
            spike_table,
            1,
        )
        ready, ready_issues = doctor.derive_design_contract(
            spiked, "DES-0001", required=True
        )
        self.assertEqual(ready_issues, [])
        self.assertEqual(ready.status, "READY")
        self.assertEqual(ready.project_contract.spike.spike_id, "SPIKE-001")

        for bad_exit in (
            "Confirm the adapter works",
            "python -m unittest tests.test_spike_exit; echo unsafe",
        ):
            with self.subTest(exit_criterion=bad_exit):
                unsafe, unsafe_issues = doctor.derive_design_contract(
                    spiked.replace(
                        "python -m unittest tests.test_spike_exit", bad_exit, 1
                    ),
                    "DES-0001",
                    required=True,
                )
                self.assertEqual(unsafe.status, "BLOCKED")
                self.assertTrue(
                    any("Exit criterion must be one explicit local command" in issue
                        for issue in unsafe_issues),
                    unsafe_issues,
                )

    def test_real_approved_schema_12_gate_a_reaches_schema_five(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        approved_modern = complete_design_contract(approve_gate_a(source))
        legacy_basis = exact_legacy_requirements_projection(approved_modern)
        migrated = complete_legacy_design_bridge(source)
        self.assertEqual(
            legacy_basis.split("# Part III", 1)[0],
            migrated.split("# Part III", 1)[0],
        )
        requirements, requirement_issues = doctor.derive_requirements_contract(
            migrated, "low", None, required=True,
            grandfather_current_gate_a=True,
        )
        self.assertEqual(requirement_issues, [])
        self.assertEqual(requirements.status, "GRANDFATHERED")
        self.assertEqual(
            requirements.acceptance_ids,
            tuple(f"AC-{item}" for item in requirements.requirement_ids),
        )
        design, design_issues = doctor.derive_design_contract(
            migrated, "DES-0001", required=True,
            grandfather_approved_v1=True,
            requirements_contract=requirements,
        )
        self.assertEqual(design_issues, [])
        self.assertEqual(design.status, "READY")
        self.assertIsNone(design.project_contract.first_wave.journey_id)
        self.assertIn(
            requirements.canonical_sha256.encode("utf-8"),
            design.project_contract.canonical_bytes,
        )

    def test_legacy_schema_five_bridge_is_fail_closed(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        migrated = complete_legacy_design_bridge(source)
        cases = {
            "invented journey": (
                migrated.replace(
                    "| WAVE-001 | NEW_BUILD | NONE |",
                    "| WAVE-001 | NEW_BUILD | JOURNEY-001 |",
                    1,
                ),
                "walking-skeleton journey must be NONE",
            ),
            "unbound Harness": (
                migrated.replace(
                    "DES-0001, FR-001, WAVE-001",
                    "DES-0001, WAVE-001",
                    1,
                ),
                "Basis IDs must include the wave and every selected requirement",
            ),
            "missing conservative state": (
                replace_contract_table(
                    migrated,
                    doctor.STATE_APPLICABILITY_HEADING,
                    doctor.STATE_APPLICABILITY_HEADERS,
                    [("RESOURCE-001", "NOT_APPLICABLE", "NOT_APPLICABLE - no state", "NONE")],
                ),
                "grandfathered Gate A design requires an applicable state model",
            ),
        }
        for label, (candidate, expected) in cases.items():
            with self.subTest(case=label):
                design, issues = doctor.derive_design_contract(
                    candidate, "DES-0001", required=True,
                    grandfather_approved_v1=True,
                )
                self.assertEqual(design.status, "BLOCKED")
                self.assertTrue(any(expected in issue for issue in issues), issues)

        modern = complete_design_contract(source).replace(
            "| WAVE-001 | NEW_BUILD | JOURNEY-001 |",
            "| WAVE-001 | NEW_BUILD | NONE |",
            1,
        )
        modern_design, modern_issues = doctor.derive_design_contract(
            modern, "DES-0001", required=True,
        )
        self.assertEqual(modern_design.status, "BLOCKED")
        self.assertTrue(
            any("not a current JOURNEY ID" in issue for issue in modern_issues),
            modern_issues,
        )

    def test_state_trigger_categories_are_typed_and_journey_bound(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(source)
        requirements, requirement_issues = doctor.derive_requirements_contract(
            complete, "low", None, required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(requirement_issues, [])

        def stateful(trigger_basis: str) -> str:
            text = replace_contract_table(
                complete, doctor.STATE_APPLICABILITY_HEADING,
                doctor.STATE_APPLICABILITY_HEADERS,
                [("RESOURCE-001", "APPLICABLE", trigger_basis, "STATE-001")],
            )
            return replace_contract_table(
                text, doctor.STATE_REGISTER_HEADING, doctor.STATE_REGISTER_HEADERS,
                [(
                    "STATE-001", "RESOURCE-001", "PENDING, READY", "PENDING",
                    "PENDING to READY", "READY", "Reject invalid transitions",
                    "FR-001", "AC-FR-001",
                )],
            )

        for category in doctor.STATE_MODEL_TRIGGERS:
            with self.subTest(category=category):
                ready, issues = doctor.derive_design_contract(
                    stateful(f"{category}: FR-001"), "DES-0001", required=True,
                    requirements_contract=requirements,
                )
                self.assertEqual(issues, [])
                self.assertEqual(ready.status, "READY")
        for rich_trigger, state_trigger in doctor.RICH_TO_STATE_TRIGGER.items():
            triggered = replace(requirements, rich_use_case_triggers=(rich_trigger,))
            blocked, issues = doctor.derive_design_contract(
                stateful("LIFECYCLE_RESOURCE: FR-001"), "DES-0001", required=True,
                requirements_contract=triggered,
            )
            self.assertEqual(blocked.status, "BLOCKED")
            self.assertTrue(any(state_trigger in issue for issue in issues), issues)
            ready, issues = doctor.derive_design_contract(
                stateful(f"{state_trigger}: FR-001"), "DES-0001", required=True,
                requirements_contract=triggered,
            )
            self.assertEqual(issues, [])
            self.assertEqual(ready.status, "READY")

        for invalid in (
            "UNKNOWN: FR-001",
            "APPROVAL_FLOW: FR-001; LIFECYCLE_RESOURCE: FR-001",
        ):
            blocked, issues = doctor.derive_design_contract(
                stateful(invalid), "DES-0001", required=True,
                requirements_contract=requirements,
            )
            self.assertEqual(blocked.status, "BLOCKED")
            self.assertTrue(any("State trigger" in issue for issue in issues), issues)

class AwsExecutionContractRegressionTests(unittest.TestCase):
    def test_req_materiality_modes_and_unresolved_required_fact(self) -> None:
        cases = (
            (
                {
                    "AWS Core materiality": "REQUIRED",
                    "AWS materiality basis IDs": "REQ-0001, SEC-0001",
                    "AWS Core discovery IDs": "AWS-DISC-0001",
                    "Unresolved material AWS fact IDs": "NONE",
                },
                "REQUIRED",
            ),
            (
                {
                    "AWS Core materiality": "OPTIONAL",
                    "AWS materiality basis IDs": "NONE — current AWS facts do not block Gate A",
                    "AWS Core discovery IDs": "NONE — live evidence is optional for this decision",
                    "Unresolved material AWS fact IDs": "NONE",
                },
                "OPTIONAL",
            ),
            (
                {
                    "AWS Core materiality": "NOT_MATERIAL",
                    "AWS materiality basis IDs": "NONE — no AWS-specific fact affects Gate A",
                    "AWS Core discovery IDs": "NONE — AWS evidence is not material to Gate A",
                    "Unresolved material AWS fact IDs": "NONE",
                },
                "NOT_MATERIAL",
            ),
        )
        for fields, expected in cases:
            with self.subTest(materiality=expected):
                result, issues = doctor.derive_req_aws_materiality(
                    fields,
                    "REQ-0001",
                    required=True,
                    grandfather_current_gate_a=False,
                )
                self.assertEqual(issues, [])
                self.assertEqual(result["materiality"], expected)
                self.assertEqual(result["status"], "CURRENT")

        blocked, issues = doctor.derive_req_aws_materiality(
            {
                "AWS Core materiality": "REQUIRED",
                "AWS materiality basis IDs": "REQ-0001, SEC-0001",
                "AWS Core discovery IDs": "AWS-DISC-0001",
                "Unresolved material AWS fact IDs": "SEC-0002",
            },
            "REQ-0001",

            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertTrue(any("unresolved" in issue.lower() for issue in issues), issues)
    def test_req_evidence_matches_exact_basis_without_selecting_architecture(self) -> None:
        verify_text = (REPOSITORY_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        passed = record_aws_core_evidence(
            verify_text,
            "REQ-10",
            binding="REQ-0001",
            discovery_id="AWS-DISC-0001",
            basis_ids="REQ-0001, SEC-0001",
            advisory_design_binding=(
                "NOT_APPLICABLE — requirements feasibility only; no architecture selected"
            ),
        )
        rows = doctor.parse_aws_core_evidence(passed)
        self.assertEqual(
            doctor.aws_core_phase_evidence_issues(
                rows,
                "REQ-10",
                expected_binding="REQ-0001",
                expected_basis_ids={"REQ-0001", "SEC-0001"},
            ),
            [],
        )
        wrong_basis = doctor.aws_core_phase_evidence_issues(
            rows,
            "REQ-10",
            expected_binding="REQ-0001",
            expected_basis_ids={"REQ-0001", "SEC-0002"},
        )
        self.assertTrue(any("exactly match" in issue for issue in wrong_basis))

        premature = record_aws_core_evidence(
            verify_text,
            "REQ-10",
            binding="REQ-0001",
            discovery_id="AWS-DISC-0001",
            basis_ids="REQ-0001, SEC-0001",
            advisory_design_binding="DES-0001; TECH: TECH-0001",
        )
        premature_issues = doctor.aws_core_phase_evidence_issues(
            doctor.parse_aws_core_evidence(premature),
            "REQ-10",
            expected_binding="REQ-0001",
            expected_basis_ids={"REQ-0001", "SEC-0001"},
        )
        self.assertTrue(any("without selecting" in issue for issue in premature_issues))


    def test_all_four_lanes_have_deterministic_progression(self) -> None:
        materiality = {"materiality": "OPTIONAL", "status": "CURRENT"}
        authority = {
            "validity": "CURRENT",
            "authorization_id": "AWS-READ-AUTH-0001",
        }
        ready = {"status": "READY", "account_access": "READ_ONLY_OBSERVED"}
        not_started = {"status": "NOT_STARTED", "account_access": "NOT_OBSERVED"}

        documentation = doctor.derive_aws_execution_projection(
            materiality,
            release_decision="READY_TO_DEPLOY",
            guidance_ready=True,
            read_authority=None,
            preflight=not_started,
            lane="documentation-only",
        )
        self.assertEqual(documentation["progress_state"], "AWS_PREFLIGHT_READY")
        self.assertEqual(documentation["preflight"]["account_access"], "NOT_USED")

        for lane, expected in (
            ("read-only", "AWS_PREFLIGHT_READY"),
            ("fast-dev", "AWS_PREFLIGHT_READY"),
            ("explicit-gate", "WAITING_AWS_MUTATION_AUTH"),
        ):
            with self.subTest(lane=lane):
                projected = doctor.derive_aws_execution_projection(
                    materiality,
                    release_decision="READY_TO_DEPLOY",
                    guidance_ready=True,
                    read_authority=authority,
                    preflight=ready,
                    lane=lane,
                )
                self.assertEqual(projected["progress_state"], expected)

        guidance = doctor.derive_aws_execution_projection(
            materiality,
            release_decision="READY_TO_DEPLOY",
            guidance_ready=False,
            read_authority=None,
            preflight=not_started,
            lane="read-only",
        )
        self.assertEqual(guidance["progress_state"], "AWS_GUIDANCE_REQUIRED")

    def test_remediation_fingerprint_binds_revisions_and_escalates_repeat(self) -> None:
        first_context = doctor.Context(PROJECT_ROOT)
        first_context.error(
            "AWS_CORE_DISCOVERY_REQUIRED",
            "Fresh discovery evidence is required",
            doctor.VERIFY_FILE,
        )
        first = doctor.derive_remediation(
            first_context,
            classification="ACTIVE_GREENFIELD",
            gate_a="BLOCKED",
            gate_b="BLOCKED",
            envelope={},
            tasks=doctor.TaskSummary(),
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
        )
        self.assertEqual(first["next_action"]["responsible_party"], "CODEX")
        self.assertEqual(first["retry_state"], "FIRST_OR_NONE")

        repeated_context = doctor.Context(
            PROJECT_ROOT,
            prior_remediation_fingerprint=first["fingerprint"],
        )
        repeated_context.error(
            "AWS_CORE_DISCOVERY_REQUIRED",
            "Fresh discovery evidence is required",
            doctor.VERIFY_FILE,
        )
        repeated = doctor.derive_remediation(
            repeated_context,
            classification="ACTIVE_GREENFIELD",
            gate_a="BLOCKED",
            gate_b="BLOCKED",
            envelope={},
            tasks=doctor.TaskSummary(),
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
        )
        self.assertEqual(repeated["retry_state"], "REPEATED")
        self.assertEqual(repeated["next_action"]["responsible_party"], "HUMAN_REVIEWER")

        changed_revision_context = doctor.Context(
            PROJECT_ROOT,
            prior_remediation_fingerprint=first["fingerprint"],
        )
        changed_revision_context.error(
            "AWS_CORE_DISCOVERY_REQUIRED",
            "Fresh discovery evidence is required",
            doctor.VERIFY_FILE,
        )
        changed_revision = doctor.derive_remediation(
            changed_revision_context,
            classification="ACTIVE_GREENFIELD",
            gate_a="BLOCKED",
            gate_b="BLOCKED",
            envelope={},
            tasks=doctor.TaskSummary(),
            requirements_revision="REQ-0001",
            design_revision="DES-0002",
        )
        self.assertNotEqual(changed_revision["fingerprint"], first["fingerprint"])
        self.assertEqual(changed_revision["next_action"]["responsible_party"], "CODEX")

    def test_aws_evidence_remediation_ownership_is_precise(self) -> None:
        cases = (
            ("AWS_CORE_CAPABILITY_UNAVAILABLE", "OWNER"),
            ("AWS_CORE_EVIDENCE_REQUIRED", "CODEX"),
            ("AWS_CORE_EVIDENCE_STRUCTURE", "HUMAN_REVIEWER"),
        )
        for code, expected in cases:
            with self.subTest(code=code):
                context = doctor.Context(PROJECT_ROOT)
                context.error(code, "evidence problem", doctor.VERIFY_FILE)
                result = doctor.derive_remediation(
                    context,
                    classification="ACTIVE_GREENFIELD",
                    gate_a="APPROVED_FOR_DESIGN",
                    gate_b="BLOCKED",
                    envelope={},
                    tasks=doctor.TaskSummary(),
                    requirements_revision="REQ-0001",
                    design_revision="DES-0001",
                )
                self.assertEqual(result["next_action"]["responsible_party"], expected)

    def test_post_gate_b_aws_evidence_repairs_preserve_approved_prd(self) -> None:
        cases = (
            (
                "AWS_CORE_EVIDENCE_GENERATED_INVALID",
                doctor.VERIFY_FILE,
                "CODEX",
            ),
            (
                "AWS_CORE_EVIDENCE_GENERATED_INVALID",
                doctor.PRD_FILE,
                "HUMAN_REVIEWER",
            ),
            (
                "AWS_CORE_EVIDENCE_STRUCTURE",
                doctor.VERIFY_FILE,
                "HUMAN_REVIEWER",
            ),
        )
        for code, path, expected in cases:
            with self.subTest(code=code, path=path):
                context = doctor.Context(PROJECT_ROOT)
                context.error(code, "evidence problem", path)
                result = doctor.derive_remediation(
                    context,
                    classification="ACTIVE_GREENFIELD",
                    gate_a="APPROVED_FOR_DESIGN",
                    gate_b="APPROVED_FOR_CONSTRUCTION",
                    envelope={},
                    tasks=doctor.TaskSummary(),
                    requirements_revision="REQ-0001",
                    design_revision="DES-0001",
                    owner_stage_hint="DESIGN",
                )
                self.assertEqual(
                    result["next_action"]["responsible_party"], expected
                )
                if expected == "CODEX":
                    repeated_context = doctor.Context(
                        PROJECT_ROOT,
                        prior_remediation_fingerprint=result["fingerprint"],
                    )
                    repeated_context.error(code, "evidence problem", path)
                    repeated = doctor.derive_remediation(
                        repeated_context,
                        classification="ACTIVE_GREENFIELD",
                        gate_a="APPROVED_FOR_DESIGN",
                        gate_b="APPROVED_FOR_CONSTRUCTION",
                        envelope={},
                        tasks=doctor.TaskSummary(),
                        requirements_revision="REQ-0001",
                        design_revision="DES-0001",
                        owner_stage_hint="DESIGN",
                    )
                    self.assertEqual(
                        repeated["next_action"]["responsible_party"],
                        "HUMAN_REVIEWER",
                    )

    def test_teardown_receipt_cannot_satisfy_deployment_wait(self) -> None:
        context = doctor.Context(PROJECT_ROOT)
        context.texts[doctor.VERIFY_FILE] = "verification"
        calls: list[str] = []
        original = doctor._receipt_external_authority

        def fake_receipt(
            _text: str, action: str, _construction_authorization: str, **_kwargs: object
        ) -> dict[str, object] | None:
            calls.append(action)
            if action == "Teardown":
                return {"kind": "AWS_TEARDOWN", "validity": "CURRENT"}
            return None

        doctor._receipt_external_authority = fake_receipt
        try:
            result = doctor.derive_external_authority(
                context,
                {"AWS boundary": "MUTATE_LISTED_RESOURCES"},
                "explicit-gate",
                "AUTH-0001",
                aws_progress_state="WAITING_AWS_MUTATION_AUTH",
                aws_action_phase="AWS-20",
                preflight={
                    "status": "READY",
                    "preflight_id": "AWS-PREFLIGHT-0001",
                    "account_access": "READ_ONLY_OBSERVED",
                },
            )
        finally:
            doctor._receipt_external_authority = original
        self.assertEqual(calls, ["Deployment"])
        self.assertEqual(result["kind"], "AWS_ACTION_RECEIPT_REQUIRED")
        self.assertEqual(result["validity"], "REQUIRED")

    def test_read_preflight_artifact_mismatch_is_stale(self) -> None:
        artifact_a = "sha256:" + ("a" * 64)
        artifact_b = "sha256:" + ("b" * 64)
        authority = {
            "validity": "CURRENT",
            "authorization_id": "AWS-READ-AUTH-0001",
            "account": "123456789012",
            "region": "us-west-2",
            "environment": "development",
            "role_or_profile": "audit-role",
            "resources": ["bucket-a"],
            "operations": ["s3:GetObject"],
            "artifact_plan_binding": {"artifact": artifact_a, "plan": "NONE"},
        }
        values = (
            "AWS-PREFLIGHT-0001", "AWS-READ-AUTH-0001",
            "REQ-0001 / DES-0001 / AUTH-0001", artifact_b,
            "audit-role", "123456789012", "us-west-2", "development",
            "bucket-a", "s3:GetObject", "EV-0001", "READ_ONLY_OBSERVED",
            "EV-0002", "EV-0003", "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:01:00+00:00", "PASS", "READY",
        )
        table = "\n".join(
            (
                doctor.AWS_READ_PREFLIGHT_HEADING,
                "| " + " | ".join(doctor.AWS_READ_PREFLIGHT_HEADERS) + " |",
                "|" + "|".join("---" for _ in doctor.AWS_READ_PREFLIGHT_HEADERS) + "|",
                "| " + " | ".join(values) + " |",
            )
        )
        result = doctor.derive_read_preflight_state(
            table,
            authority,
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            construction_authorization="AUTH-0001",
            artifact_binding=artifact_b,
        )
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["account_access"], "NOT_VERIFIED")
        self.assertTrue(any("receipt artifact" in issue.lower() for issue in result["issues"]))

    def test_read_authority_requires_bounded_cost_provenance(self) -> None:
        receipt_lines = [
            "AUTHORIZE AWS READ-ONLY PREFLIGHT",
            "Read authorization: AWS-READ-AUTH-0001",
            "Construction authorization: AUTH-0001",
            "Profile or role: audit-role",
            "Account: 123456789012",
            "Region: us-west-2",
            "Environment: development",
            "Stack, application, and resources: bucket-a",
            "Allowed read-only operations: s3:GetObject",
            "Artifact digest: sha256:" + ("a" * 64),
            "Prohibited operations: ALL_MUTATIONS",
            "Valid until: ONE_OPERATION",
            "Approver: owner-handle",
        ]
        receipt = "\n".join(receipt_lines)
        digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        headers = (
            "Action", "Authorization ID", "Construction AUTH", "Role or profile",
            "Artifact digest", "IaC plan/change-set binding",
            "Account / Region / environment", "Resources and operations",
            "Cost ceiling and validity", "Rollback boundary",
            "Stable owner-message source", "Approver", "Observed at",
            "Verbatim receipt SHA-256", "Preflight evidence",
            "Identity and boundary match", "Result",
        )

        def document(cost: str) -> str:
            row = (
                "Read-only preflight", "AWS-READ-AUTH-0001", "AUTH-0001",
                "audit-role", "sha256:" + ("a" * 64),
                "NOT_APPLICABLE — read-only preflight creates no plan",
                "ACCOUNT: 123456789012; REGION: us-west-2; ENVIRONMENT: development",
                "RESOURCES: bucket-a; OPERATIONS: s3:GetObject", cost,
                "NOT_APPLICABLE — no mutation", "owner-message-1", "owner-handle",
                "2026-01-01T00:00:00+00:00", digest, "NONE", "PASS", "AUTHORIZED",
            )
            return "\n".join((
                "<!-- bootstrap:aws-read-preflight-receipt:start -->",
                "```text", receipt, "```",
                "<!-- bootstrap:aws-read-preflight-receipt:end -->",
                "## Action authorization provenance",
                "| " + " | ".join(headers) + " |",
                "|" + "|".join("---" for _ in headers) + "|",
                "| " + " | ".join(row) + " |",
                "| Deployment | " + " | ".join("TODO" for _ in headers[1:]) + " |",
            ))

        cost_posture = "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00"
        active_artifact = "sha256:" + ("a" * 64)
        envelope = aws_authority_envelope(
            role="audit-role",
            account="123456789012",
            region="us-west-2",
            environment="development",
            resources=["bucket-a"],
            operations=["s3:GetObject"],
            artifact=active_artifact,
            rollback="NONE",
            boundary="READ_ONLY",
        )

        valid = document(
            "COST: expected low-volume request charges under USD 0.01; "
            f"BOUNDED_BY: {cost_posture}; "
            "VALID_UNTIL: ONE_OPERATION"
        )
        authority = doctor._read_preflight_receipt_authority(
            valid, "AUTH-0001", cost_posture, envelope, active_artifact
        )
        self.assertIsNotNone(authority)
        self.assertIn("BOUNDED_BY", authority["cost_ceiling"])
        invalid = document(
            "COST: NOT_APPLICABLE — read-only; BOUNDED_BY: USD 20.00; "
            "VALID_UNTIL: ONE_OPERATION"
        )
        self.assertIsNone(
            doctor._read_preflight_receipt_authority(
                invalid, "AUTH-0001", cost_posture, envelope, active_artifact
            )
        )
        nonhuman_receipt = receipt.replace(
            "Approver: owner-handle", "Approver: Codex"
        )
        nonhuman_digest = "sha256:" + hashlib.sha256(
            nonhuman_receipt.encode("utf-8")
        ).hexdigest()
        nonhuman = set_receipt(valid, "aws-read-preflight", nonhuman_receipt)
        nonhuman = nonhuman.replace(
            " | owner-handle | ", " | Codex | ", 1
        ).replace(digest, nonhuman_digest, 1)
        self.assertIsNone(
            doctor._read_preflight_receipt_authority(
                nonhuman, "AUTH-0001", cost_posture, envelope, active_artifact
            )
        )

        for operation in (
            "ec2:RunInstances",
            "iam:AttachRolePolicy",
            "dynamodb:BatchWriteItem",
            "s3:RestoreObject",
        ):
            with self.subTest(operation=operation):
                mutation_receipt = receipt.replace("s3:GetObject", operation)
                mutation_digest = "sha256:" + hashlib.sha256(
                    mutation_receipt.encode("utf-8")
                ).hexdigest()
                mutation = set_receipt(
                    valid, "aws-read-preflight", mutation_receipt
                )
                mutation = mutation.replace(
                    "RESOURCES: bucket-a; OPERATIONS: s3:GetObject",
                    f"RESOURCES: bucket-a; OPERATIONS: {operation}",
                    1,
                ).replace(digest, mutation_digest, 1)
                self.assertIsNone(
                    doctor._read_preflight_receipt_authority(
                        mutation,
                        "AUTH-0001",
                        cost_posture,
                        envelope,
                        active_artifact,
                    )
                )

    def test_teardown_authority_requires_an_explicit_human_approver(self) -> None:
        verify_text = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        headers = (
            "Action", "Authorization ID", "Construction AUTH", "Role or profile",
            "Artifact digest", "IaC plan/change-set binding",
            "Account / Region / environment", "Resources and operations",
            "Cost ceiling and validity", "Rollback boundary",
            "Stable owner-message source", "Approver", "Observed at",
            "Verbatim receipt SHA-256", "Preflight evidence",
            "Identity and boundary match", "Result",
        )

        def document(approver: str) -> str:
            receipt = "\n".join((
                "AUTHORIZE AWS TEARDOWN",
                "Teardown authorization: TEARDOWN-AUTH-0001",
                "Construction authorization: AUTH-0001",
                "Profile or role: cleanup-role",
                "Account: 111122223333",
                "Region: us-west-2",
                "Environment: development",
                "Stack, application, and resources to remove: fastlane-stack",
                "Resources and data to retain: NONE",
                "Allowed deletion operations: cloudformation:DeleteStack",
                "Shared dependencies: NONE",
                "Cost effect: removes stack billing",
                "Post-teardown verification: cloudformation:DescribeStacks",
                "Valid until: 2099-01-01T00:00:00Z",
                f"Approver: {approver}",
            ))
            digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
            row = (
                "Teardown", "TEARDOWN-AUTH-0001", "AUTH-0001", "cleanup-role",
                "NOT_APPLICABLE — teardown binds the observed inventory",
                "NOT_APPLICABLE — teardown uses its removal/retention manifest",
                "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
                "RESOURCES: fastlane-stack; OPERATIONS: cloudformation:DeleteStack",
                "COST: removes stack billing; VALID_UNTIL: 2099-01-01T00:00:00Z",
                "cloudformation:DescribeStacks", "owner-message-2", approver,
                "2027-01-01T00:00:00Z", digest, "EV-0040", "PASS", "READY",
            )
            rendered = set_receipt(verify_text, "aws-teardown", receipt)
            lines = rendered.splitlines()
            for index, line in enumerate(lines):
                if line.startswith("| Teardown | TODO |"):
                    lines[index] = "| " + " | ".join(row) + " |"
                    break
            else:
                self.fail("Teardown authorization provenance row not found")
            return "\n".join(lines) + "\n"

        envelope = aws_authority_envelope(
            role="cleanup-role",
            account="111122223333",
            region="us-west-2",
            environment="development",
            resources=["fastlane-stack"],
            operations=["cloudformation:DeleteStack"],
            artifact="sha256:" + "a" * 64,
            rollback="restore stack from approved IaC",
        )
        teardown_review = {
            "status": "READY_FOR_TEARDOWN",
            "evidence_id": "EV-0040",
            "resources_to_remove": ["fastlane-stack"],
            "allowed_operations": ["cloudformation:DeleteStack"],
            "resources_to_retain": [],
            "shared_dependencies": [],
            "cost_effect": "removes stack billing",
            "post_action_verification": "cloudformation:DescribeStacks",
            "role_or_profile": "cleanup-role",
            "account": "111122223333",
            "region": "us-west-2",
            "environment": "development",
            "identity_and_boundary_match": "PASS",
        }
        authority = doctor._receipt_external_authority(
            document("Alice Rivera"),
            "Teardown",
            "AUTH-0001",
            envelope=envelope,
            cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            active_artifact="sha256:" + "a" * 64,
            teardown_review=teardown_review,
        )
        self.assertIsNotNone(authority)
        self.assertEqual(authority["kind"], "AWS_TEARDOWN")
        self.assertEqual(authority["cost_ceiling"], "USD: 20.00")
        self.assertNotEqual(authority["cost_ceiling"], "removes stack billing")
        self.assertEqual(
            authority["rollback_boundary"],
            "ROLLBACK: restore stack from approved IaC",
        )
        self.assertNotEqual(
            authority["rollback_boundary"], "cloudformation:DescribeStacks"
        )
        self.assertIsNone(
            doctor._receipt_external_authority(
                document("Codex"),
                "Teardown",
                "AUTH-0001",
                envelope=envelope,
                cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
                active_artifact="sha256:" + "a" * 64,
                teardown_review=teardown_review,
            )
        )


    def test_teardown_sequence_routes_by_current_phase_evidence(self) -> None:
        envelope = aws_authority_envelope(
            role="cleanup-role", account="111122223333", region="us-west-2",
            environment="development", resources=["fastlane-stack"],
            operations=["cloudformation:DeleteStack"],
            artifact="sha256:" + "a" * 64,
            rollback="restore stack from approved IaC",
        )
        read_authority = {
            "validity": "CURRENT",
            "authorization_id": "AWS-READ-AUTH-0001",
            "role_or_profile": "cleanup-role",
            "account": "111122223333",
            "region": "us-west-2",
            "environment": "development",
        }

        receipt = "\n".join((
            "AUTHORIZE AWS TEARDOWN",
            "Teardown authorization: TEARDOWN-AUTH-0001",
            "Construction authorization: AUTH-0001",
            "Profile or role: cleanup-role",
            "Account: 111122223333",
            "Region: us-west-2",
            "Environment: development",
            "Stack, application, and resources to remove: fastlane-stack",
            "Resources and data to retain: NONE",
            "Allowed deletion operations: cloudformation:DeleteStack",
            "Shared dependencies: NONE",
            "Cost effect: removes stack billing",
            "Post-teardown verification: cloudformation:DescribeStacks",
            "Valid until: 2099-01-01T00:00:00Z",
            "Approver: Alice Rivera",
        ))
        receipt_digest = "sha256:" + hashlib.sha256(
            receipt.encode("utf-8")
        ).hexdigest()
        provenance_headers = (
            "Action", "Authorization ID", "Construction AUTH", "Role or profile",
            "Artifact digest", "IaC plan/change-set binding",
            "Account / Region / environment", "Resources and operations",
            "Cost ceiling and validity", "Rollback boundary",
            "Stable owner-message source", "Approver", "Observed at",
            "Verbatim receipt SHA-256", "Preflight evidence",
            "Identity and boundary match", "Result",
        )
        provenance_row = (
            "Teardown", "TEARDOWN-AUTH-0001", "AUTH-0001", "cleanup-role",
            "NOT_APPLICABLE \u2014 teardown binds the observed inventory",
            "NOT_APPLICABLE \u2014 teardown uses its removal/retention manifest",
            "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
            "RESOURCES: fastlane-stack; OPERATIONS: cloudformation:DeleteStack",
            "COST: removes stack billing; VALID_UNTIL: 2099-01-01T00:00:00Z",
            "cloudformation:DescribeStacks", "owner-message-2", "Alice Rivera",
            "2027-01-01T00:00:00Z", receipt_digest, "EV-0040", "PASS", "READY",
        )

        def evidence_row(
            phase: str, status: str, *, evidence_id: str = "EV-0040",
            observed_at: str = "2027-01-01T00:00:00Z",
            read_authorization: str = "AWS-READ-AUTH-0001",
            teardown_authorization: str | None = None,
            teardown_receipt_digest: str | None = None,
            terminal_status: str | None = None,
            resources_removed: str | None = None,
            residual_resources: str | None = None,
            blocker_or_stale_reason: str | None = None,
        ) -> str:
            action_phase = phase == "AWS-50"
            if teardown_authorization is None:
                teardown_authorization = (
                    "TEARDOWN-AUTH-0001" if action_phase else "NONE"
                )
            if teardown_receipt_digest is None:
                teardown_receipt_digest = receipt_digest if action_phase else "NONE"
            if terminal_status is None:
                terminal_status = {
                    "SUCCEEDED": "DELETE_COMPLETE",
                    "FAILED": "DELETE_FAILED",
                    "PARTIAL": "PARTIAL_DELETE",
                    "UNKNOWN": "TERMINAL_STATUS_UNDETERMINED",
                    "VERIFIED_CLEAN": "STACK_ABSENT",
                    "RESIDUALS_REMAIN": "STACK_OR_RESOURCES_REMAIN",
                }.get(status, "NONE")
            if resources_removed is None:
                resources_removed = (
                    "fastlane-stack"
                    if status in {"SUCCEEDED", "VERIFIED_CLEAN"}
                    else "NONE"
                )
            if residual_resources is None:
                residual_resources = (
                    "fastlane-stack"
                    if status in {
                        "FAILED", "PARTIAL", "UNKNOWN", "RESIDUALS_REMAIN"
                    }
                    else "NONE"
                )
            if blocker_or_stale_reason is None:
                blocker_or_stale_reason = (
                    "caller identity could not be verified"
                    if status == "BLOCKED"
                    else "read evidence no longer matches the current basis"
                    if status == "STALE"
                    else "NONE"
                )
            values = {
                "Evidence ID": evidence_id,
                "Phase": phase,
                "REQ / DES / AUTH": "REQ-0001 / DES-0001 / AUTH-0001",
                "Read authorization": read_authorization,
                "Teardown authorization": teardown_authorization,
                "Teardown receipt digest": teardown_receipt_digest,
                "Role or profile": "cleanup-role",
                "Expected manifest or stack": "fastlane-stack",
                "Resources proposed to remove": "fastlane-stack",
                "Allowed deletion operations": "cloudformation:DeleteStack",
                "Resources retained": "NONE",
                "Shared dependencies": "NONE",
                "Cost effect": "removes stack billing",
                "Post-teardown verification": "cloudformation:DescribeStacks",
                "Stack events and terminal status": terminal_status,
                "Resources removed": resources_removed,
                "Snapshots and backups": "NONE",
                "Residual resources": residual_resources,
                "Inventory or discovery limits": "CloudFormation stack scope",
                "Account / Region / environment": (
                    "ACCOUNT: 111122223333; REGION: us-west-2; "
                    "ENVIRONMENT: development"
                ),
                "Observed at": observed_at,
                "Durable source": f"docs/project/VERIFY.md#{evidence_id.lower()}",
                "Identity and boundary match": "PASS",
                "Blocker or stale reason": blocker_or_stale_reason,
                "Status": status,
            }
            return "| " + " | ".join(
                values[field] for field in doctor.AWS_TEARDOWN_EVIDENCE_HEADERS
            ) + " |"

        def document(*rows: str, duplicate_provenance: bool = False) -> str:
            headers = doctor.AWS_TEARDOWN_EVIDENCE_HEADERS
            rendered_provenance = "| " + " | ".join(provenance_row) + " |"
            placeholder_provenance = (
                "| Read-only preflight | "
                + " | ".join("TODO" for _ in provenance_headers[1:])
                + " |"
            )
            provenance_rows = [placeholder_provenance, rendered_provenance]
            if duplicate_provenance:
                provenance_rows.append(rendered_provenance)
            return "\n".join((
                "<!-- bootstrap:aws-teardown-receipt:start -->",
                "```text",
                receipt,
                "```",
                "<!-- bootstrap:aws-teardown-receipt:end -->",
                "",
                "## Action authorization provenance",
                "| " + " | ".join(provenance_headers) + " |",
                "|" + "|".join("---" for _ in provenance_headers) + "|",
                *provenance_rows,
                "",
                doctor.AWS_TEARDOWN_EVIDENCE_HEADING,
                "",
                "| " + " | ".join(headers) + " |",
                "|" + "|".join("---" for _ in headers) + "|",
                *rows,
            ))

        def derive(text: str) -> dict[str, object]:
            return doctor.derive_teardown_sequence_state(
                text, read_authority,
                requirements_revision="REQ-0001",
                design_revision="DES-0001",
                construction_authorization="AUTH-0001",
                envelope=envelope,
            )

        self.assertEqual(derive(document())["status"], "NOT_ACTIVE")
        running = derive(document(evidence_row("AWS-40", "RUNNING")))
        self.assertEqual(running["status"], "RUNNING")
        ready_row = evidence_row("AWS-40", "READY_FOR_TEARDOWN")
        ready = derive(document(ready_row))
        self.assertEqual(ready["status"], "READY_FOR_TEARDOWN")
        self.assertEqual(ready["resources_to_remove"], ["fastlane-stack"])
        blocked = derive(document(evidence_row("AWS-40", "BLOCKED")))
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertEqual(
            blocked["blocker_or_stale_reason"],
            "caller identity could not be verified",
        )
        self.assertIn("caller identity could not be verified", blocked["issues"][0])


        action_results: dict[str, dict[str, object]] = {}
        action_cases = (
            ("SUCCEEDED", "EV-0050", "2027-01-02T00:00:00Z"),
            ("FAILED", "EV-0051", "2027-01-02T00:00:01Z"),
            ("PARTIAL", "EV-0052", "2027-01-02T00:00:02Z"),
            ("UNKNOWN", "EV-0053", "2027-01-02T00:00:03Z"),
        )
        for action_status, evidence_id, observed_at in action_cases:
            with self.subTest(action_status=action_status):
                post_action = derive(document(
                    ready_row,
                    evidence_row(
                        "AWS-50", action_status, evidence_id=evidence_id,
                        observed_at=observed_at,
                    ),
                ))
                action_results[action_status] = post_action
                self.assertEqual(
                    post_action["status"], "POST_ACTION_REVIEW", post_action["issues"]
                )
                self.assertEqual(post_action["action_status"], action_status)
                self.assertEqual(
                    post_action["teardown_authorization"],
                    "TEARDOWN-AUTH-0001",
                )
                self.assertEqual(
                    post_action["teardown_receipt_digest"], receipt_digest
                )

        verified = derive(document(
            ready_row,
            evidence_row(
                "AWS-50", "SUCCEEDED", evidence_id="EV-0060",
                observed_at="2027-01-03T00:00:00Z",
            ),
            evidence_row(
                "AWS-40", "VERIFIED_CLEAN", evidence_id="EV-0061",
                observed_at="2027-01-03T00:00:01Z",
                teardown_authorization="TEARDOWN-AUTH-0001",
                teardown_receipt_digest=receipt_digest,
            ),
        ))
        self.assertEqual(verified["status"], "VERIFIED_CLEAN", verified["issues"])
        residuals = derive(document(
            ready_row,
            evidence_row(
                "AWS-50", "PARTIAL", evidence_id="EV-0062",
                observed_at="2027-01-03T00:00:02Z",
            ),
            evidence_row(
                "AWS-40", "RESIDUALS_REMAIN", evidence_id="EV-0063",
                observed_at="2027-01-03T00:00:03Z",
                teardown_authorization="TEARDOWN-AUTH-0001",
                teardown_receipt_digest=receipt_digest,
            ),
        ))
        self.assertEqual(residuals["status"], "RESIDUALS_REMAIN", residuals["issues"])

        invalid_cases = (
            (
                evidence_row(
                    "AWS-50", "SUCCEEDED", evidence_id="EV-0070",
                    observed_at="2027-01-04T00:00:00Z",
                    teardown_authorization="TEARDOWN-AUTH-9999",
                ),
                "exact teardown receipt",
            ),
            (
                evidence_row(
                    "AWS-50", "SUCCEEDED", evidence_id="EV-0071",
                    observed_at="2027-01-04T00:00:01Z",
                    teardown_receipt_digest="sha256:" + "f" * 64,
                ),
                "exact teardown receipt",
            ),
            (
                evidence_row(
                    "AWS-50", "SUCCEEDED", evidence_id="EV-0072",
                    observed_at="2027-01-04T00:00:02Z",
                    terminal_status="NONE",
                ),
                "Stack events and terminal status",
            ),
            (
                evidence_row(
                    "AWS-50", "SUCCEEDED", evidence_id="EV-0073",
                    observed_at="2027-01-04T00:00:03Z",
                    residual_resources="fastlane-stack",
                ),
                "cannot retain unexpected residuals",
            ),
            (
                evidence_row(
                    "AWS-50", "SUCCEEDED", evidence_id="EV-0074",
                    observed_at="2027-01-04T00:00:04Z",
                    resources_removed="NONE",
                ),
                "must reconcile every removal",
            ),
        )
        for invalid_row, expected_issue in invalid_cases:
            with self.subTest(expected_issue=expected_issue):
                invalid = derive(document(ready_row, invalid_row))
                self.assertEqual(invalid["status"], "BLOCKED")
                self.assertTrue(
                    any(expected_issue in issue for issue in invalid["issues"]),
                    invalid["issues"],
                )

        malformed_id = derive(document(
            ready_row,
            evidence_row(
                "AWS-50", "SUCCEEDED", evidence_id="EV-BAD",
                observed_at="2027-01-04T00:00:05Z",
            ),
        ))
        self.assertEqual(malformed_id["status"], "BLOCKED")
        self.assertTrue(any(
            "noncanonical" in issue for issue in malformed_id["issues"]
        ))
        partial_placeholder = derive(document(
            ready_row,
            evidence_row(
                "AWS-50", "SUCCEEDED", evidence_id="TODO",
                observed_at="2027-01-04T00:00:06Z",
            ),
        ))
        self.assertEqual(partial_placeholder["status"], "BLOCKED")
        wrong_read_authority = derive(document(
            ready_row,
            evidence_row(
                "AWS-50", "SUCCEEDED", evidence_id="EV-0075",
                observed_at="2027-01-04T00:00:07Z",
                read_authorization="AWS-READ-AUTH-9999",
            ),
        ))
        self.assertEqual(wrong_read_authority["status"], "BLOCKED")
        self.assertTrue(any(
            "matching READY_FOR_TEARDOWN" in issue
            for issue in wrong_read_authority["issues"]
        ))
        missing_blocker = derive(document(evidence_row(
            "AWS-40", "BLOCKED", evidence_id="EV-0076",
            observed_at="2027-01-04T00:00:08Z",
            blocker_or_stale_reason="NONE",
        )))
        self.assertEqual(missing_blocker["status"], "BLOCKED")
        self.assertTrue(any(
            "exact blocker" in issue for issue in missing_blocker["issues"]
        ))
        replayed_action = derive(document(
            ready_row,
            evidence_row(
                "AWS-50", "PARTIAL", evidence_id="EV-0077",
                observed_at="2027-01-04T00:00:09Z",
            ),
            evidence_row(
                "AWS-50", "SUCCEEDED", evidence_id="EV-0078",
                observed_at="2027-01-04T00:00:10Z",
            ),
        ))
        self.assertEqual(replayed_action["status"], "BLOCKED")
        self.assertTrue(any(
            "replays a teardown authorization" in issue
            for issue in replayed_action["issues"]
        ))
        different_authority_retry = derive(document(
            ready_row,
            evidence_row(
                "AWS-50", "FAILED", evidence_id="EV-0079",
                observed_at="2027-01-04T00:00:10Z",
                teardown_authorization="TEARDOWN-AUTH-9999",
                teardown_receipt_digest="sha256:" + "f" * 64,
            ),
            evidence_row(
                "AWS-50", "SUCCEEDED", evidence_id="EV-0088",
                observed_at="2027-01-04T00:00:11Z",
            ),
        ))
        self.assertEqual(different_authority_retry["status"], "BLOCKED")
        self.assertTrue(any(
            "does not follow matching READY_FOR_TEARDOWN" in issue
            for issue in different_authority_retry["issues"]
        ))

        premature_binding = derive(document(evidence_row(
            "AWS-40", "READY_FOR_TEARDOWN", evidence_id="EV-0080",
            teardown_authorization="TEARDOWN-AUTH-0001",
            teardown_receipt_digest=receipt_digest,
        )))
        self.assertEqual(premature_binding["status"], "BLOCKED")
        orphan_terminal = derive(document(evidence_row(
            "AWS-40", "VERIFIED_CLEAN", evidence_id="EV-0081",
            teardown_authorization="TEARDOWN-AUTH-0001",
            teardown_receipt_digest=receipt_digest,
        )))
        self.assertEqual(orphan_terminal["status"], "BLOCKED")

        residual_only_clean = derive(document(evidence_row(
            "AWS-40", "VERIFIED_CLEAN", evidence_id="EV-0085",
            observed_at="2027-01-05T00:00:01Z",
        )))
        self.assertEqual(residual_only_clean["status"], "VERIFIED_CLEAN")
        self.assertFalse(residual_only_clean["post_action_bound"])
        self.assertEqual(
            doctor.derive_teardown_route("TEARDOWN", residual_only_clean),
            ("AWS_RESIDUAL_REVIEW_COMPLETE", "STOP"),
        )

        erased_binding = derive(document(
            ready_row,
            evidence_row(
                "AWS-50", "SUCCEEDED", evidence_id="EV-0086",
                observed_at="2027-01-05T00:00:02Z",
            ),
            evidence_row(
                "AWS-40", "VERIFIED_CLEAN", evidence_id="EV-0087",
                observed_at="2027-01-05T00:00:03Z",
            ),
        ))
        self.assertEqual(erased_binding["status"], "BLOCKED")
        self.assertTrue(any(
            "cannot erase" in issue for issue in erased_binding["issues"]
        ))

        partial_pairs = (
            ("TEARDOWN-AUTH-0001", "NONE"),
            ("NONE", receipt_digest),
            ("NOT-CANONICAL", receipt_digest),
            ("TEARDOWN-AUTH-0001", "sha256:not-a-digest"),
        )
        for index, (authorization_id, digest_value) in enumerate(partial_pairs):
            with self.subTest(
                authorization_id=authorization_id, digest_value=digest_value
            ):
                malformed = derive(document(evidence_row(
                    "AWS-40", "VERIFIED_CLEAN",
                    evidence_id=f"EV-{8090 + index}",
                    observed_at=f"2027-01-05T00:01:0{index}Z",
                    teardown_authorization=authorization_id,
                    teardown_receipt_digest=digest_value,
                )))
                self.assertEqual(malformed["status"], "BLOCKED")

        replayed_attempt = derive(document(
            ready_row,
            evidence_row(
                "AWS-50", "SUCCEEDED", evidence_id="EV-0094",
                observed_at="2027-01-05T00:02:00Z",
            ),
            evidence_row(
                "AWS-50", "SUCCEEDED", evidence_id="EV-0095",
                observed_at="2027-01-05T00:02:01Z",
            ),
            evidence_row(
                "AWS-40", "VERIFIED_CLEAN", evidence_id="EV-0096",
                observed_at="2027-01-05T00:02:02Z",
                teardown_authorization="TEARDOWN-AUTH-0001",
                teardown_receipt_digest=receipt_digest,
            ),
        ))
        self.assertEqual(replayed_attempt["status"], "BLOCKED")
        self.assertTrue(any(
            "exactly one earlier matching" in issue
            for issue in replayed_attempt["issues"]
        ))

        duplicate_id = derive(document(
            evidence_row("AWS-40", "RUNNING"),
            evidence_row(
                "AWS-40", "READY_FOR_TEARDOWN",
                observed_at="2027-01-02T00:00:00Z",
            ),
        ))
        self.assertEqual(duplicate_id["status"], "BLOCKED")
        self.assertTrue(any(
            "duplicate IDs" in issue for issue in duplicate_id["issues"]
        ))
        duplicate_timestamp = derive(document(
            evidence_row("AWS-40", "RUNNING", evidence_id="EV-0082"),
            evidence_row(
                "AWS-40", "READY_FOR_TEARDOWN", evidence_id="EV-0083",
            ),
        ))
        self.assertEqual(duplicate_timestamp["status"], "BLOCKED")
        self.assertTrue(any(
            "timestamps must be unique" in issue
            for issue in duplicate_timestamp["issues"]
        ))
        duplicate_provenance = derive(document(
            ready_row,
            evidence_row(
                "AWS-50", "SUCCEEDED", evidence_id="EV-0084",
                observed_at="2027-01-05T00:00:00Z",
            ),
            duplicate_provenance=True,
        ))
        self.assertEqual(duplicate_provenance["status"], "BLOCKED")
        self.assertTrue(any(
            "one exact owner-authored teardown receipt" in issue
            for issue in duplicate_provenance["issues"]
        ))

        route_cases = (
            (
                "RESIDUAL_REVIEW", ready,
                ("AWS_RESIDUALS_REMAIN", "STOP"),
            ),
            (
                "RESIDUAL_REVIEW", verified,
                ("AWS_RESIDUAL_REVIEW_COMPLETE", "STOP"),
            ),
            (
                "RESIDUAL_REVIEW", residuals,
                ("AWS_RESIDUALS_REMAIN", "STOP"),
            ),
            (
                "RESIDUAL_REVIEW", blocked,
                ("AWS_RESIDUAL_REVIEW_BLOCKED", "STOP"),
            ),
            (
                "TEARDOWN", ready,
                ("WAITING_AWS_TEARDOWN_AUTH", "AWS-50"),
            ),
            (
                "TEARDOWN", verified,
                ("AWS_TEARDOWN_COMPLETE", "STOP"),
            ),
            (
                "TEARDOWN", residuals,
                ("AWS_RESIDUALS_REMAIN", "STOP"),
            ),
            (
                "TEARDOWN", blocked,
                ("AWS_RESIDUAL_REVIEW_BLOCKED", "STOP"),
            ),
            (
                "TEARDOWN", action_results["SUCCEEDED"],
                ("AWS_RESIDUAL_REVIEW", "AWS-40"),
            ),
            (
                "TEARDOWN", running,
                ("AWS_RESIDUAL_REVIEW", "AWS-40"),
            ),
        )
        for intent, sequence, expected_route in route_cases:
            with self.subTest(intent=intent, status=sequence["status"]):
                self.assertEqual(
                    doctor.derive_teardown_route(intent, sequence),
                    expected_route,
                )
        self.assertIsNone(doctor.derive_teardown_route("NONE", ready))
        specialized = doctor.derive_interaction(
            "AWS_RESIDUAL_REVIEW_BLOCKED",
            "STOP",
            has_errors=True,
            diagnostic_codes=["AWS_TEARDOWN_EVIDENCE_INVALID"],
            design_aws_core_ready=True,
            aws_execution_planning_ready=True,
            remediation={
                "next_action": {
                    "action_kind": "FIX_VALIDATION_FAILURE",
                }
            },
        )
        self.assertEqual(
            specialized["owner_action_kind"],
            "REVIEW_SAFETY_BLOCKER",
        )
        self.assertEqual(
            specialized["route_reason_code"], "AWS_RESIDUAL_REVIEW_BLOCKED"
        )
        teardown_context = doctor.Context(PROJECT_ROOT)
        teardown_context.error(
            "AWS_TEARDOWN_EVIDENCE_INVALID", "residual review blocked", doctor.VERIFY_FILE
        )
        self.assertTrue(doctor._preserve_specialized_teardown_block(
            teardown_context, "AWS_RESIDUAL_REVIEW_BLOCKED"
        ))
        teardown_context.error("UNRELATED_VALIDATION", "separate error")
        self.assertFalse(doctor._preserve_specialized_teardown_block(
            teardown_context, "AWS_RESIDUAL_REVIEW_BLOCKED"
        ))

    def test_action_receipts_are_phase_isolated(self) -> None:
        context = doctor.Context(PROJECT_ROOT)
        context.texts[doctor.VERIFY_FILE] = "verification"
        calls: list[str] = []
        original = doctor._receipt_external_authority

        def fake_receipt(
            _text: str, action: str, _authorization: str, **_kwargs: object
        ) -> dict[str, object]:
            calls.append(action)
            return {"kind": f"AWS_{action.upper()}", "validity": "CURRENT"}

        doctor._receipt_external_authority = fake_receipt
        try:
            teardown = doctor.derive_external_authority(
                context, {"AWS boundary": "MUTATE_LISTED_RESOURCES"},
                "explicit-gate", "AUTH-0001", aws_action_phase="AWS-50",
                teardown_review={"status": "READY_FOR_TEARDOWN"},
            )
            self.assertEqual(calls, ["Teardown"])
            calls.clear()
            deployment = doctor.derive_external_authority(
                context, {"AWS boundary": "MUTATE_LISTED_RESOURCES"},
                "explicit-gate", "AUTH-0001", aws_action_phase="AWS-20",
                aws_progress_state="WAITING_AWS_MUTATION_AUTH",
                preflight={
                    "status": "READY",
                    "preflight_id": "AWS-PREFLIGHT-0001",
                    "account_access": "READ_ONLY_OBSERVED",
                },
            )
            self.assertEqual(calls, ["Deployment"])
        finally:
            doctor._receipt_external_authority = original
        self.assertEqual(teardown["kind"], "AWS_TEARDOWN")
        self.assertEqual(deployment["kind"], "AWS_DEPLOYMENT")

    def test_fast_dev_mutation_requires_observed_preflight_and_aws20(self) -> None:
        artifact = "sha256:" + "a" * 64
        envelope = aws_authority_envelope(
            role="deploy-role", account="111122223333", region="us-west-2",
            environment="development", resources=["fastlane-stack"],
            operations=["cloudformation:ExecuteChangeSet"], artifact=artifact,
            rollback="rollback fastlane-stack",
        )
        context = doctor.Context(PROJECT_ROOT)
        context.texts[doctor.VERIFY_FILE] = "verification"
        common = {
            "cost_posture": "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
            "aws_progress_state": "AWS_PREFLIGHT_READY",
            "active_artifact": artifact,
        }
        self.assertEqual(doctor.derive_external_authority(
            context, envelope, "fast-dev", "AUTH-0001", **common
        )["kind"], "NONE")
        self.assertEqual(doctor.derive_external_authority(
            context, envelope, "fast-dev", "AUTH-0001",
            aws_action_phase="AWS-20", **common
        )["kind"], "NONE")
        authority = doctor.derive_external_authority(
            context, envelope, "fast-dev", "AUTH-0001",
            aws_action_phase="AWS-20",
            preflight=ready_preflight(
                account="111122223333", region="us-west-2",
                environment="development",
            ),
            **common,
        )
        self.assertEqual(authority["kind"], "FAST_DEV_GATE_B")

if __name__ == "__main__":
    unittest.main()
