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
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path, PurePosixPath

from scripts import fastlane_document_summaries as document_summaries
from scripts.fastlane_adr import ADR_AUTHORITY
from scripts.fastlane_engine.design.models import (
    APPLICATION_SOURCE_INFRASTRUCTURE_ONLY,
)
from scripts.fastlane_engine.design import diagrams as design_diagrams
from scripts.fastlane_engine.design.support import AWS_SERVICE_TECH_CONCERNS

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = REPOSITORY_ROOT
SCRIPTS = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
TEMPLATE_SOURCE_MODE = "{{SETUP_STATUS}}" in (
    REPOSITORY_ROOT / "bootstrap.yaml"
).read_text(encoding="utf-8")
source_template_only = unittest.skipUnless(
    TEMPLATE_SOURCE_MODE,
    "maintainer source-integrity test is not applicable after project configuration",
)

EXPECTED_AWS_DESIGN_CONCERNS = (
    "Compute",
    "API and edge",
    "Identity",
    "Data",
    "Messaging",
    "Observability",
    "Deployment",
    "Secrets and encryption",
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
setup_runtime = sys.modules["scripts.setup_assistant"]


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


def fixture_rows(rows: str) -> list[str]:
    return rows.replace(" ;; ", "\n").strip().splitlines()


def set_fixture_values(text: str, heading: str, next_heading: str, rows: str) -> str:
    for row in fixture_rows(rows):
        field, value = row.split(" || ", 1)
        text = set_table_value(text, heading, next_heading, field, value)
    return text


def replace_fixture_table(text: str, heading: str, headers: str, rows: str = "") -> str:
    values = [tuple(row.split(" || ")) for row in fixture_rows(rows)]
    return replace_contract_table(text, heading, tuple(headers.split(" || ")), values)


def replace_fixture_bullets(text: str, rows: str) -> str:
    for row in fixture_rows(rows):
        field, value = row.split(" || ", 1)
        text = text.replace(f"- {field}: TODO", f"- {field}: {value}", 1)
    return text


def replace_fixture_sections(text: str, rows: str) -> str:
    for row in fixture_rows(rows):
        heading, next_heading, body = row.split(" || ", 2)
        text = set_diagram_block(text, heading, next_heading, body.replace("\\n", "\n"))
    return text


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
        r"(?m)^\| Project contract schema \| `1\.4` \|\r?\n",
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
        doctor.REQUIREMENTS_CHANGE_LINEAGE_HEADING,
        doctor.ASSUMPTION_LIFECYCLE_HEADING,
    ):
        heading_start = text.index(heading)
        table_start = text.index("|", heading_start)
        table_end = text.index("\n\n", table_start)
        text = text[:table_start] + text[table_end + 2 :]
    return text


def exact_legacy_schema_four_projection(text: str) -> str:
    text = re.sub(
        r"(?m)^\| Project design contract schema \| `7` \|\r?\n",
        "",
        text,
        count=1,
    )
    legacy_interface_table = "\n".join(
        [
            "| Contract ID | Producer | Consumer | Schema or protocol | Authentication | Versioning | Idempotency |",
            "|---|---|---|---|---|---|---|",
            "| API-001 | Local client | Trusted application service | Versioned JSON request and response | Approved identity token | Compatible additions only | One idempotent read per request |",
        ]
    )
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

    text = remove_region(
        text, doctor.DIAGRAM_CONTRACT_HEADING, "## 14. Architecture overview"
    )
    text = remove_region(text, doctor.LAYER_BOUNDARY_HEADING, doctor.INTERFACE_HEADING)
    text = remove_region(
        text, doctor.STATE_APPLICABILITY_HEADING, "### Data lifecycle view"
    )
    text = remove_region(
        text,
        doctor.FIRST_WAVE_HEADING,
        "## Validation strategy",
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
    if initial_issues:
        raise AssertionError(f"Initial intake card is invalid: {initial_issues}")
    if initial.pending_card is None:
        if initial.status == "READY_FOR_REQUIREMENTS":
            return text
        raise AssertionError("Initial intake card is unavailable before readiness")
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

    def resolve_current(
        *,
        owner_response_id: str,
        card_id: str,
        card_digest: str,
        question_id: str,
        selection: str,
        detail: str,
        basis_id: str,
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
                "1",
                question_id,
                selection,
                detail,
                basis_id,
            )
        )
        provenance_by_intake[basis_id] = provenance

    resolve_current(
        owner_response_id="OWNER-MSG-0001",
        card_id="INTAKE-CARD-0001",
        card_digest=initial.pending_card.canonical_sha256,
        question_id="INTAKE-Q-0001",
        selection=work_context_choice,
        detail=work_context_detail,
        basis_id="INTAKE-0001",
    )

    facts = (
        (
            "INTAKE-0002",
            "Who will use the app?",
            "Name the primary people or teams.",
            "Development teams",
        ),
        (
            "INTAKE-0003",
            "What are they trying to do, and what makes that difficult today?",
            "Describe their current task and the obstacle.",
            "They need a clear view of approved project outcomes.",
        ),
        (
            "INTAKE-0004",
            "What should the app let them accomplish first?",
            "Describe one useful, observable result.",
            "See the current approved project outcome.",
        ),
        (
            "INTAKE-0005",
            "What must the first release include, and what can wait?",
            "Name the smallest useful app boundary and anything deferred.",
            "Include one local outcome view; defer external integrations.",
        ),
        (
            "INTAKE-0006",
            "What visible result would convince you the first trial succeeded?",
            "Name a result a person can see or measure.",
            "An invited tester can view the approved outcome without help.",
        ),
        (
            "INTAKE-0007",
            "What information will people enter, upload, view, or generate?",
            "List the app's important data in ordinary language.",
            "Synthetic project names, status, and outcome summaries.",
        ),
        (
            "INTAKE-0008",
            (
                "Could that information reveal identity, health, money, location, "
                "credentials, or another sensitive detail?"
            ),
            "Say no, or name the sensitive information and who may see it.",
            "No sensitive data in the first trial.",
        ),
        (
            "INTAKE-0009",
            "Who should be allowed to use the first release?",
            "Describe the initial audience and any sign-in boundary.",
            "Invited development testers only.",
        ),
        (
            "INTAKE-0010",
            ("Where will the first users be, and are there places the data must stay?"),
            "Name the user geography and any data-location rule.",
            "United States users; data remains in us-west-2.",
        ),
    )
    for index, (basis_id, prompt, detail_prompt, value) in enumerate(facts, start=2):
        card_id = f"INTAKE-CARD-{index:04d}"
        question_id = f"INTAKE-Q-{index:04d}"
        text = replace_contract_table(
            text,
            doctor.INTAKE_CARD_HEADING,
            doctor.INTAKE_CARD_HEADERS,
            [
                (
                    card_id,
                    "1",
                    "1",
                    question_id,
                    "FACT",
                    basis_id,
                    prompt,
                    "NOT_APPLICABLE",
                    "NOT_APPLICABLE",
                    "NOT_APPLICABLE",
                    "NONE",
                    "RESPONSE",
                    detail_prompt,
                    "PENDING",
                    "NONE",
                    "NONE",
                )
            ],
        )
        table = doctor.contract_table_after_heading(
            text, doctor.INTAKE_CARD_HEADING, doctor.INTAKE_CARD_HEADERS
        )
        if table is None:
            raise AssertionError(f"{card_id} is missing")
        digest = "sha256:" + hashlib.sha256(table.canonical_bytes).hexdigest()
        resolve_current(
            owner_response_id=f"OWNER-MSG-{index:04d}",
            card_id=card_id,
            card_digest=digest,
            question_id=question_id,
            selection="RESPONSE",
            detail=value,
            basis_id=basis_id,
        )

    values = {
        "INTAKE-0001": work_context,
        **{basis_id: value for basis_id, _prompt, _detail_prompt, value in facts},
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
        "`1.4`",
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
        [
            (
                "NOT_APPLICABLE",
                "NOT_APPLICABLE - low-risk single-actor synchronous fixture",
                "NONE",
            )
        ],
    )
    text = replace_contract_table(
        text, doctor.RICH_USE_CASE_HEADING, doctor.RICH_USE_CASE_HEADERS, []
    )
    text = replace_contract_table(
        text, doctor.BUSINESS_RULE_HEADING, doctor.BUSINESS_RULE_HEADERS, []
    )
    text = replace_contract_table(
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
    text = replace_contract_table(
        text,
        doctor.REQUIREMENTS_CHANGE_LINEAGE_HEADING,
        doctor.REQUIREMENTS_CHANGE_LINEAGE_HEADERS,
        [
            (
                "REQ-0001",
                "NONE",
                "INITIAL_DEFINITION",
                requirement_list,
                "NONE",
                "NONE",
                "NONE",
                "NONE - first definition",
                "FULL_REVALIDATION",
            )
        ],
    )
    return replace_contract_table(
        text,
        doctor.ASSUMPTION_LIFECYCLE_HEADING,
        doctor.ASSUMPTION_LIFECYCLE_HEADERS,
        [],
    )


def approve_gate_a(
    text: str,
    *,
    work_context_choice: str = "A",
    project_mode: str = "greenfield",
) -> str:
    text = complete_intake_foundation(text, work_context_choice=work_context_choice)
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
    text = complete_owner_visible_gate_a(text, project_mode=project_mode)

    for field, value in {
        "Project mode": f"`{project_mode}`",
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
        "Explicitly rejected assumption IDs and resolution": "`NONE`",
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


def complete_owner_visible_gate_a(text: str, *, project_mode: str) -> str:
    text = set_fixture_values(
        text,
        "## Document status",
        "## 1. Workload profile",
        "Bootstrap release || `Fastlane 1.2.43; baseline c14f4a9` ;; Specification status || `Current` ;; Target release || `development validation` ;; Last reviewed || `2026-07-17T09:55:00-07:00` ;; Primary owner || `alice`",
    )
    text = set_fixture_values(
        text,
        "## 1. Workload profile",
        "### Owner decisions and sources",
        "Business outcome || `Display the current approved project outcome` ;; Primary owner || `alice` ;; Users || `development users` ;; Environment || `Development` ;; AWS accounts || `NONE — no account access is authorized` ;; Primary Region || `us-west-2` ;; Data classification || `internal synthetic` ;; Availability target || `best effort during development` ;; Recovery target || `RTO: 60 minutes; RPO: 15 minutes` ;; Expected traffic || `up to 100 requests per minute` ;; Applicable AWS lenses || `Serverless; security; reliability; cost optimization`",
    )
    text = set_fixture_values(
        text,
        "### 1.1 Intake provenance",
        "#### Intake foundation",
        "Intake session ID || `INTAKE-SESSION-0001` ;; Intake source links || `NONE — direct owner intake` ;; Participants and decision owner || `alice; decision owner alice` ;; Captured by || `Fastlane coordinator` ;; Captured at || `2026-07-17T09:30:00-07:00` ;; Last reconciled with sources || `2026-07-17T09:45:00-07:00` ;; Owner-stated outcome, in their words || `Show the current approved project outcome` ;; Unresolved input IDs || `NONE` ;; Material source conflicts || `NONE`",
    )
    intake_source = "| FR-001 | `OWNER_FACT` / `REPOSITORY_FACT` / `AGENT_RECOMMENDATION` / `PROPOSED_ASSUMPTION` / `OPEN_QUESTION` | TODO | TODO | TODO |"
    if text.count(intake_source) != 1:
        raise AssertionError("Expected one unresolved intake provenance row")
    text = text.replace(
        intake_source,
        "| FR-001 | OWNER_FACT | owner message MSG-000 | HIGH | CONFIRMED |",
        1,
    )
    text = replace_fixture_sections(
        text,
        r"## 2. Product statement || ## 3. Problem and opportunity || Fastlane Golden Project helps development users see the current approved project outcome through a bounded development interface. ;; ## 3. Problem and opportunity || ## 4. Users and outcomes || Development users need one reliable view of the approved outcome; ambiguous or invalid input must not change approved state. ;; ### Goals || ### Non-goals || 1. Display the approved outcome.\n2. Reject invalid input without changing state.\n3. Preserve traceable validation evidence. ;; ### Non-goals || ## 6. Feature specifications || - Production deployment or AWS account access.\n- Unapproved product behavior or data migration. ;; ### Alternate flows || ### Failure and recovery flows || - A user may correct rejected input and resubmit without changing approved state. ;; ### Failure and recovery flows || ## 8. Data requirements || - A failed request returns a safe explanation and preserves the last approved state.",
    )
    text = replace_fixture_table(
        text,
        "### User stories",
        "ID || User story || Priority || Related requirements",
        "US-001 || As a development user, I want the approved outcome, so that I can verify the current result. || High || FR-001",
    )
    text = replace_fixture_table(
        text,
        "### Findings",
        "ID || Type || Requirements involved || Finding || Resolution or decision || Blocking? || Status",
    )
    text = replace_fixture_table(
        text,
        "### Open decisions",
        "ID || Decision needed || Options || Decision owner || Blocking? || Resolution",
    )
    text = set_fixture_values(
        text,
        "### Gate A — agent analysis record",
        "### Gate A — owner acceptance record",
        "Reviewed commit (optional) || `NOT_RECORDED` ;; Analysis performed by || `Fastlane deterministic validation` ;; Analysis completed at || `2026-07-17T09:50:00-07:00` ;; AWS Core materiality || `NOT_MATERIAL` ;; AWS materiality basis IDs || `NONE — documentation-only local release` ;; AWS Core discovery IDs || `NONE — no material AWS requirement` ;; Unresolved material AWS fact IDs || `NONE` ;; Recommendation rationale || `The complete Product Agreement has no open blockers`",
    )
    if project_mode == "greenfield":
        for field in doctor.BROWNFIELD_BASELINE_FIELDS:
            text = set_table_value(
                text,
                "### 1.2 Brownfield baseline and preservation contract",
                "## 2. Product statement",
                field,
                "`NOT_APPLICABLE — greenfield project`",
            )
        text = text.replace(
            "| PRES-001 | TODO | TODO | TODO | TODO |",
            "| PRES-001 | NOT_APPLICABLE — greenfield project | NOT_APPLICABLE — greenfield project | NOT_APPLICABLE — greenfield project | NOT_APPLICABLE — greenfield project |",
            1,
        )
    return text


def approve_gate_b(
    text: str,
    *,
    baseline: str = "a" * 40,
    design_builder: Callable[[str], str] | None = None,
    envelope_overrides: Mapping[str, str] | None = None,
) -> str:
    text = (design_builder or complete_design_contract)(text)
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
            "TECH-0006, TECH-0007, TECH-0008, TECH-0009, TECH-0010, "
            "TECH-0011, TECH-0012, TECH-0013, TECH-0014, TECH-0015`"
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
            "`REQ: REQ-0001; DES: DES-0001; SCOPE_IDS: "
            + ", ".join(
                (
                    *MODERN_APPROVED_REQUIREMENT_IDS,
                    "ARCH-0001",
                    *(f"TECH-{number:04d}" for number in range(1, 16)),
                    "PROP-001",
                    "HARNESS-004",
                    "JOURNEY-001",
                    "API-001",
                    "BOUNDARY-001",
                    "WAVE-001",
                )
            )
            + "`"
        ),
        "Design contract SHA-256": f"`{design_contract.canonical_sha256}`",
        "Authorized baseline commit": f"`{baseline}`",
        "Protected dirty paths": "`NONE`",
        "In-scope components and environments": "`app and tests in development`",
        "Allowed repository write set": "`PATHS: app/**; tests/**`",
        "Application source disposition": "`GREENFIELD_APP_ROOT: app/**`",
        "Excluded or owner-only write set": "`PATHS: docs/project/PRD.md; bootstrap.yaml`",
        "Allowed external-state targets": "`NONE`",
        "Task boundary": "`DERIVED_FROM_AUTHORIZED_IDS_AND_WRITE_SET`",
        "Autonomous construction": "`ALLOWED`",
        "Maximum generated tasks": "`8`",
        "Maximum parallel workers": "`1`",
        "Parallelism rule": "`One coordinator; serialize all mutable execution`",
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
    aws_not_applicable = (
        "`NOT_APPLICABLE — AWS boundary DOCS_ONLY authorizes no authenticated action`"
    )
    for field in doctor.AWS_DETAIL_FIELDS:
        envelope_values[field] = aws_not_applicable
    envelope_values.update(envelope_overrides or {})
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


def rebind_gate_b_envelope(text: str, *, grandfather_approved_v1: bool = False) -> str:
    design_revision = doctor.table_after_heading(text, "## Document status")[
        "Current design revision"
    ]
    design_contract, design_issues = doctor.derive_design_contract(
        text,
        design_revision,
        required=True,
        grandfather_approved_v1=grandfather_approved_v1,
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


def bind_technology_adr(text: str) -> str:
    table = doctor.contract_table_after_heading(
        text,
        doctor.TECHNOLOGY_DECISION_HEADING,
        doctor.TECHNOLOGY_DECISION_HEADERS,
    )
    if table is None:
        raise AssertionError("Technology decision register is missing")
    rows = [list(row) for row in table.rows]
    matches = [row for row in rows if row[0] == "TECH-0001"]
    if len(matches) != 1:
        raise AssertionError("TECH-0001 must appear exactly once")
    matches[0][-1] += "; rationale: [ADR-0001](../adr/0001-runtime.md)"
    rebound = replace_contract_table(
        text,
        doctor.TECHNOLOGY_DECISION_HEADING,
        doctor.TECHNOLOGY_DECISION_HEADERS,
        [tuple(row) for row in rows],
    )
    return rebind_gate_b_envelope(rebound)


def accepted_runtime_adr(
    *, design_revision: str = "DES-0001", context: str | None = None
) -> str:
    rationale = context or (
        "The approved application needs the selected runtime and its bounded "
        "packaging and support model."
    )
    return f"""# ADR-0001: Application runtime

## Decision record

| Field | Current value |
|---|---|
| Status | Accepted |
| Design revision | {design_revision} |
| Primary decision | TECH-0001 |
| Decision value | Python 3.12 on AWS Lambda |
| Related basis IDs | DES-0001, FR-001 |
| Canonical PRD section | Technology and toolchain decision register |
| Evidence maturity | SOURCE_VERIFIED |
| Evidence IDs | AWS-EV-0001 |
| Supersedes | NONE |
| Superseded by | NONE |
| Authority | {ADR_AUTHORITY} |

## Context

{rationale}

## Decision

Use Python for the approved local application runtime.

## Alternatives considered

A second runtime was rejected because it adds packaging and operations cost.

## Consequences

The project accepts Python support and dependency lifecycle constraints.

## Evidence and validation

Current AWS source evidence and the selected task checks support the decision.

## Revisit when

Reconsider when support, performance, or compatibility requirements change.
"""


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


MATERIAL_AWS_TECH_IDS = (
    "TECH-0001",
    "TECH-0002",
    "TECH-0004",
    "TECH-0008",
    "TECH-0009",
    "TECH-0010",
    "TECH-0011",
    "TECH-0013",
    "TECH-0014",
    "TECH-0015",
)


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


MODERN_APPROVED_REQUIREMENT_IDS = (
    *(f"COST-{number:03d}" for number in range(1, 6)),
    *(f"DATA-{number:03d}" for number in range(1, 6)),
    *(f"FR-{number:03d}" for number in range(1, 3)),
    *(f"OPS-{number:03d}" for number in range(1, 6)),
    *(f"PERF-{number:03d}" for number in range(1, 5)),
    *(f"REL-{number:03d}" for number in range(1, 6)),
    *(f"SEC-{number:03d}" for number in range(1, 8)),
    *(f"SUS-{number:03d}" for number in range(1, 5)),
)
MODERN_TASK_REQUIREMENT_TRACE = "; ".join(
    (
        "REQ-0001",
        *(
            identifier
            for requirement_id in MODERN_APPROVED_REQUIREMENT_IDS
            for identifier in (requirement_id, f"AC-{requirement_id}")
        ),
    )
)


def ready_task(
    write_set: str = "app/main.py",
    *,
    requirements: str = MODERN_TASK_REQUIREMENT_TRACE,
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
        "Project mode",
        "`greenfield`",
    )
    text = set_table_value(
        text,
        "## Document status",
        "## 1. Workload profile",
        "Project design contract schema",
        "`7`",
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
    text = replace_contract_table_with_sentinel(
        text,
        doctor.SPIKE_HEADING,
        "no prerequisite discovery is needed before the walking skeleton",
    )
    return set_table_value(
        text,
        "## 28. Construction envelope",
        "## 29. Gate B owner authorization record",
        "Application source disposition",
        "`GREENFIELD_APP_ROOT: app/**`",
    )


def set_diagram_block(text: str, heading: str, next_heading: str, block: str) -> str:
    start = text.index(heading) + len(heading)
    end = text.index(next_heading, start)
    return text[:start] + "\n\n" + block.strip() + "\n\n" + text[end:]


def complete_diagram_contract(text: str) -> str:
    aws_tech_ids = (
        "TECH-0001",
        "TECH-0002",
        "TECH-0004",
        "TECH-0008",
        "TECH-0009",
        "TECH-0010",
        "TECH-0011",
        "TECH-0012",
        "TECH-0013",
        "TECH-0014",
        "TECH-0015",
    )
    active_aws_tech_ids = tuple(
        identifier for identifier in aws_tech_ids if identifier != "TECH-0012"
    )
    rows = [
        (
            "DIAGRAM-0001",
            "SYSTEM_CONTEXT",
            "REQUIRED",
            "CURRENT",
            "proposed-system-at-a-glance",
            "ARCH-0001, FR-001",
            ", ".join(
                (
                    "ARCH-0001",
                    "ACT-001",
                    "API-001",
                    "BOUNDARY-001",
                    *active_aws_tech_ids,
                )
            ),
        ),
        (
            "DIAGRAM-0002",
            "PRIMARY_OUTCOME",
            "REQUIRED",
            "CURRENT",
            "sequence-primary-outcome",
            "ARCH-0001, JOURNEY-001",
            "ACT-001, API-001",
        ),
        (
            "DIAGRAM-0003",
            "DATA_LIFECYCLE",
            "CONDITIONAL",
            "CURRENT",
            "data-lifecycle-view",
            "ARCH-0001, DATA-001",
            "API-001, TECH-0011",
        ),
        (
            "DIAGRAM-0004",
            "FAILURE_RECOVERY",
            "CONDITIONAL",
            "CURRENT",
            "sequence-failure-and-recovery",
            "ARCH-0001, REL-005",
            "API-001, TECH-0015",
        ),
        (
            "DIAGRAM-0005",
            "MIGRATION",
            "CONDITIONAL",
            "NOT_YET_CREATED",
            "migration-view",
            "NONE",
            "NONE",
        ),
        (
            "DIAGRAM-0006",
            "JOURNEY",
            "CONDITIONAL",
            "NOT_YET_CREATED",
            "journey-view",
            "NONE",
            "NONE",
        ),
        (
            "DIAGRAM-0007",
            "STATE",
            "CONDITIONAL",
            "NOT_YET_CREATED",
            "state-view",
            "NONE",
            "NONE",
        ),
        (
            "DIAGRAM-0008",
            "AWS_IMPLEMENTATION",
            "REQUIRED",
            "CURRENT",
            "aws-implementation-at-a-glance",
            "ARCH-0001, DES-0001",
            ", ".join(("ARCH-0001", *active_aws_tech_ids)),
        ),
    ]
    text = replace_contract_table(
        text, doctor.DIAGRAM_CONTRACT_HEADING, doctor.DIAGRAM_CONTRACT_HEADERS, rows
    )
    text = set_diagram_block(
        text,
        "### Proposed system at a glance",
        "## 15. Component design",
        """```mermaid
flowchart TB
    accTitle: Complete proposed review application architecture
    accDescr: The project owner enters through a managed API and identity boundary, the review application runs on managed compute, and data, operations, encryption, deployment, and rollback services support the result.
    subgraph PEOPLE[\"People\"]
        ACT-001[\"Development user\"]:::actor
    end
    subgraph AWS_CLOUD[\"AWS Cloud · proposed architecture\"]
        subgraph REGION[\"AWS Region · us-west-2\"]
            subgraph ENTRY[\"Managed entry and identity\"]
                TECH-0013[\"Amazon API Gateway<br/>regional HTTPS endpoint\"]:::entry
                TECH-0010[\"Amazon Cognito with<br/>server-side authorization\"]:::entry
            end
            subgraph APPLICATION[\"Application · trust boundary\"]
                BOUNDARY-001[\"Local client adapter to<br/>Application domain\"]:::entry
                API-001[\"Local client to<br/>Trusted application service\"]:::compute
                TECH-0002[\"FastAPI through a<br/>Lambda adapter\"]:::compute
                TECH-0001[\"Python 3.12 on<br/>AWS Lambda\"]:::compute
                ARCH-0001[\"Managed Serverless Baseline\"]:::compute
            end
            subgraph DATA[\"Owner data and safeguards\"]
                TECH-0011[(\"Amazon DynamoDB with<br/>per-owner records\")]:::data
                TECH-0008[\"Bandit static checks;<br/>AWS KMS-managed encryption;<br/>no application secrets stored\"]:::event
            end
            subgraph OPERATIONS[\"Operations, delivery, and recovery\"]
                TECH-0014[\"Amazon CloudWatch<br/>logs, metrics, and alarms\"]:::ops
                TECH-0004[\"AWS SAM<br/>infrastructure templates\"]:::ops
                TECH-0009[\"AWS SAM CLI deployment<br/>and change sets\"]:::ops
                TECH-0015[\"AWS SAM rollback to the<br/>last validated stack\"]:::ops
            end
        end
    end
    %% Primary request path
    ACT-001 -->|sends a review request through| TECH-0013
    TECH-0010 -. \"provides token issuer trust to\" .-> TECH-0013
    TECH-0013 -->|routes authenticated requests into| BOUNDARY-001
    BOUNDARY-001 -->|allows requests to| API-001
    API-001 -->|invokes| TECH-0002
    TECH-0002 -->|runs on| TECH-0001
    TECH-0001 -->|implements| ARCH-0001
    ARCH-0001 -->|stores owner records in| TECH-0011
    %% Security, telemetry, delivery, and recovery
    TECH-0008 -. \"protects code, data, and secrets posture for\" .-> ARCH-0001
    ARCH-0001 -. \"emits operational signals to\" .-> TECH-0014
    TECH-0004 -. "defines changes for" .-> TECH-0009
    TECH-0009 -. "deploys" .-> TECH-0001
    TECH-0015 -. "restores" .-> TECH-0001
    classDef actor fill:#FFFFFF,stroke:#232F3E,color:#232F3E,stroke-width:2px;
    classDef entry fill:#EAF3FF,stroke:#147EBA,color:#232F3E;
    classDef compute fill:#FFF1E8,stroke:#D86613,color:#232F3E;
    classDef data fill:#EDF7ED,stroke:#248814,color:#232F3E;
    classDef event fill:#F3ECFF,stroke:#8C4FFF,color:#232F3E;
    classDef ops fill:#FFF7DF,stroke:#D38B00,color:#232F3E;
```""",
    )
    text = set_diagram_block(
        text,
        "### AWS implementation at a glance",
        "<details>\n<summary>Exact AWS service decision records</summary>",
        """```mermaid
flowchart TB
    accTitle: Proposed AWS implementation
    accDescr: Requests move through the selected edge, identity, compute, and data services while managed observability, encryption, deployment, and rollback controls support the application.
    subgraph AWS_CLOUD[\"AWS Cloud · proposed implementation\"]
        subgraph REGION[\"AWS Region · us-west-2\"]
            subgraph ENTRY[\"Managed entry and identity\"]
                TECH-0013[\"Amazon API Gateway<br/>regional HTTPS endpoint\"]:::entry
                TECH-0010[\"Amazon Cognito with<br/>server-side authorization\"]:::entry
            end
            subgraph APPLICATION[\"Application · compute\"]
                TECH-0002[\"FastAPI through a<br/>Lambda adapter\"]:::compute
                TECH-0001[\"Python 3.12 on<br/>AWS Lambda\"]:::compute
                ARCH-0001[\"Managed Serverless Baseline\"]:::compute
            end
            subgraph DATA[\"Data and request coordination\"]
                TECH-0011[(\"Amazon DynamoDB with<br/>per-owner records\")]:::data
            end
            subgraph OPERATE[\"Operations and safeguards\"]
                TECH-0008[\"Bandit static checks;<br/>AWS KMS-managed encryption;<br/>no application secrets stored\"]:::event
                TECH-0014[\"Amazon CloudWatch<br/>logs, metrics, and alarms\"]:::ops
                TECH-0004[\"AWS SAM<br/>infrastructure templates\"]:::ops
                TECH-0009[\"AWS SAM CLI deployment<br/>and change sets\"]:::ops
                TECH-0015[\"AWS SAM rollback to the<br/>last validated stack\"]:::ops
            end
        end
    end
    %% Primary request and data path
    TECH-0010 -. \"provides token issuer trust to\" .-> TECH-0013
    TECH-0013 -->|routes authenticated requests to| TECH-0002
    TECH-0002 -->|runs on| TECH-0001
    TECH-0001 -->|implements| ARCH-0001
    ARCH-0001 -->|reads and writes| TECH-0011
    %% Coordination, security, telemetry, delivery, and recovery
    TECH-0008 -. \"protects\" .-> ARCH-0001
    ARCH-0001 -. \"emits signals to\" .-> TECH-0014
    TECH-0004 -. "defines changes for" .-> TECH-0009
    TECH-0009 -. "deploys" .-> TECH-0001
    TECH-0015 -. "restores" .-> TECH-0001
    classDef entry fill:#EAF3FF,stroke:#147EBA,color:#232F3E;
    classDef compute fill:#FFF1E8,stroke:#D86613,color:#232F3E;
    classDef data fill:#EDF7ED,stroke:#248814,color:#232F3E;
    classDef event fill:#F3ECFF,stroke:#8C4FFF,color:#232F3E;
    classDef ops fill:#FFF7DF,stroke:#D38B00,color:#232F3E;
```""",
    )
    text = set_diagram_block(
        text,
        "### Data lifecycle view",
        "## 18. Detailed sequence diagrams",
        """```mermaid
flowchart LR
    accTitle: Owner record data lifecycle
    accDescr: The review API validates each request before storing an owner-scoped record.
    API-001[\"Local client to<br/>Trusted application service\"]
    TECH-0011[(\"Amazon DynamoDB with<br/>per-owner records\")]
    API-001 -->|validates and stores in| TECH-0011
```""",
    )
    text = set_diagram_block(
        text,
        "### Sequence — primary outcome",
        "### Sequence — failure and recovery",
        """```mermaid
flowchart LR
    accTitle: First useful owner outcome
    accDescr: The project owner submits one review request and receives the validated result through the review API.
    ACT-001[\"Development user\"]
    API-001[\"Local client to<br/>Trusted application service\"]
    ACT-001 -->|submits a review request to| API-001
    API-001 -->|returns the validated review to| ACT-001
```""",
    )
    return set_diagram_block(
        text,
        "### Sequence — failure and recovery",
        "## 19. Error handling strategy",
        """```mermaid
flowchart LR
    accTitle: Review failure and recovery path
    accDescr: A failed review request preserves the approved state and uses the planned rollback and recovery path.
    API-001[\"Local client to<br/>Trusted application service\"]
    TECH-0015[\"AWS SAM rollback to the<br/>last validated stack\"]
    API-001 -->|fails safely and invokes| TECH-0015
```""",
    )


def complete_state_diagrams(text: str, *, actorless_primary: bool = False) -> str:
    table = doctor.contract_table_after_heading(
        text,
        doctor.DIAGRAM_CONTRACT_HEADING,
        doctor.DIAGRAM_CONTRACT_HEADERS,
    )
    if table is None:
        raise AssertionError("Project diagram contract is missing")
    rows = [list(row) for row in table.rows]
    for row in rows:
        if row[1] == "SYSTEM_CONTEXT":
            referenced_ids = [item.strip() for item in row[6].split(",")]
            if actorless_primary:
                referenced_ids = [item for item in referenced_ids if item != "ACT-001"]
            if "STATE-001" not in referenced_ids:
                referenced_ids.append("STATE-001")
            row[6] = ", ".join(referenced_ids)
        elif row[1] == "PRIMARY_OUTCOME" and actorless_primary:
            row[5] = "ARCH-0001, FR-001"
            row[6] = "API-001, STATE-001"
        elif row[1] == "STATE":
            row[3] = "CURRENT"
            row[5] = "ARCH-0001, FR-001"
            row[6] = "ARCH-0001, STATE-001"
    text = replace_contract_table(
        text,
        doctor.DIAGRAM_CONTRACT_HEADING,
        doctor.DIAGRAM_CONTRACT_HEADERS,
        [tuple(row) for row in rows],
    )
    interface_node = (
        '                API-001["Local client to<br/>Trusted application service"]'
        ":::compute"
    )
    if interface_node not in text:
        raise AssertionError("Complete system diagram interface node is missing")
    text = text.replace(
        interface_node,
        interface_node + '\n                STATE-001["PENDING,<br/>READY"]:::event',
        1,
    )
    boundary_edge = "    BOUNDARY-001 -->|allows requests to| API-001"
    if boundary_edge not in text:
        raise AssertionError("Complete system diagram boundary edge is missing")
    text = text.replace(
        boundary_edge,
        boundary_edge + "\n    API-001 -->|advances the review state to| STATE-001",
        1,
    )
    text = set_diagram_block(
        text,
        "### State view",
        "### Data lifecycle view",
        """```mermaid
flowchart TB
    accTitle: Review lifecycle state
    accDescr: The selected application points to one canonical review-state model and names its exact recorded transition.
    ARCH-0001["Managed Serverless Baseline"]:::compute
    STATE-001["PENDING,<br/>READY"]:::event
    ARCH-0001 -->|permits PENDING<br/>to READY| STATE-001
    classDef compute fill:#FFF1E8,stroke:#D86613,color:#232F3E;
    classDef event fill:#F3ECFF,stroke:#8C4FFF,color:#232F3E;
```""",
    )
    if not actorless_primary:
        return text
    people = """    subgraph PEOPLE["People"]
        ACT-001["Development user"]:::actor
    end
"""
    if people not in text:
        raise AssertionError("Complete system diagram actor group is missing")
    text = text.replace(people, "", 1)
    actor_edge = "    ACT-001 -->|sends a review request through| TECH-0013\n"
    if actor_edge not in text:
        raise AssertionError("Complete system diagram actor edge is missing")
    text = text.replace(actor_edge, "", 1)
    actor_style = (
        "    classDef actor fill:#FFFFFF,stroke:#232F3E,color:#232F3E,"
        "stroke-width:2px;\n"
    )
    if actor_style not in text:
        raise AssertionError("Complete system diagram actor style is missing")
    text = text.replace(actor_style, "", 1)
    primary_heading = next(
        line
        for line in text.splitlines()
        if line.startswith("### Sequence") and "primary outcome" in line
    )
    failure_heading = next(
        line
        for line in text.splitlines()
        if line.startswith("### Sequence") and "failure and recovery" in line
    )
    return set_diagram_block(
        text,
        primary_heading,
        failure_heading,
        """```mermaid
flowchart LR
    accTitle: First useful legacy-project outcome
    accDescr: The existing project interface advances the approved review lifecycle without inventing an actor that the legacy requirements never recorded.
    API-001["Local client to<br/>Trusted application service"]
    STATE-001["PENDING, READY"]
    API-001 -->|advances the review state to| STATE-001
```""",
    )


def complete_owner_visible_design(text: str) -> str:
    text = set_fixture_values(
        text,
        "### Technical design revision record",
        "### Technology and toolchain decision register",
        "Requirements revision designed || `REQ-0001` ;; Reviewed commit (optional) || `NOT_RECORDED` ;; Design prepared by || `Fastlane coordinator` ;; Design completed at || `2026-07-17T10:15:00-07:00` ;; Remaining design gaps || `NONE`",
    )
    text = replace_fixture_table(
        text,
        "## 15. Component design",
        "Component || Responsibility || Inputs || Outputs || Dependencies || Failure behavior || Owner",
        "Trusted application service || Validate requests and return the approved outcome || Approved request DTO || Approved outcome DTO || Local client adapter and owner record store || Fail closed without changing approved state || alice",
    )
    brownfield = (
        doctor.table_after_heading(text, "## Document status")["Project mode"]
        == "brownfield"
    )
    values = {
        True: "Legacy service and tests || Legacy service boundary || Preserve existing records with a reversible adapter || Bounded local compatibility checks || `PRES-001`",
        False: "None — greenfield application || None — greenfield application || NOT_APPLICABLE — greenfield application || NOT_APPLICABLE — local development release || `NOT_APPLICABLE — greenfield project`",
    }[brownfield]
    reuse, modify, migration, rollout, compatibility = values.split(" || ")
    text = replace_fixture_bullets(
        text,
        f"Existing components to reuse || {reuse} ;; Components to modify || {modify} ;; Components to add || Trusted service, local adapter, and validation tests ;; Compatibility constraints || Preserve the approved request and outcome schema ;; Migration approach || {migration} ;; Feature flags or staged rollout || {rollout} ;; Rollback boundary || Restore the authorized baseline commit ;; Explicitly deferred work || AWS deployment and production operations",
    )
    text = replace_fixture_table(
        text,
        "## 22. Test layers",
        "Layer || Purpose || Required coverage",
        "Static || Formatting, linting, typing, schemas, IaC || Required ;; Unit || Isolated rules and functions || Required ;; Integration || Data stores, identity, APIs, and contracts || Required ;; End-to-end || Complete user outcomes || Required for FR-001 ;; Security || Authentication, authorization, abuse, and secrets || Required ;; Reliability || Timeout, recovery, and safe-state preservation || Required ;; Performance || Latency and bounded throughput || Conditional on load target ;; AWS environment || Deployed configuration and service behavior || NOT_APPLICABLE — no AWS authorization ;; Operations || Deployment, alarms, rollback, restore, teardown || NOT_APPLICABLE — local release",
    )
    text = replace_fixture_bullets(
        text,
        "Synthetic fixture strategy || Deterministic owner and outcome fixtures ;; Generated data constraints || No secrets or real customer data ;; Sensitive-data prohibition || Synthetic internal values only ;; Local emulation or mocks || Local adapters with explicit boundaries ;; AWS test environment || NOT_APPLICABLE — no AWS authorization ;; Cleanup strategy || Remove temporary local fixtures after validation ;; Cost limit for billable deployed tests || NOT_APPLICABLE — local validation",
    )
    text = set_fixture_values(
        text,
        "## 27. Gate B agent review record",
        "## 28. Construction envelope",
        "Requirements revision reviewed || `REQ-0001` ;; Design revision reviewed || `DES-0001` ;; Construction authorization ID reviewed || `AUTH-0001` ;; Construction envelope SHA-256 reviewed || `NOT_RECORDED — calculated before owner review` ;; Reviewed commit (optional) || `NOT_RECORDED` ;; PRD completeness gaps || `NONE` ;; Requirement-to-design-and-test traceability gaps || `NONE` ;; Unresolved risk or preservation gaps || `NONE` ;; Review completed by and at || `Fastlane read-only review; 2026-07-17T10:20:00-07:00` ;; Agent recommendation || `READY_FOR_CONSTRUCTION_APPROVAL` ;; Recommendation rationale || `The complete design and bounded local envelope are review-ready`",
    )
    text = set_fixture_values(
        text,
        "### Gate B — readiness card",
        "## 28. Construction envelope",
        f"Design basis IDs || `DES-0001, FR-001` ;; Architecture/components || `ARCH-0001` ;; Technology/toolchains/version policy || `TECH-0001, TECH-0002, TECH-0003, TECH-0004, TECH-0005, TECH-0006, TECH-0007, TECH-0008, TECH-0009, TECH-0010, TECH-0011, TECH-0012, TECH-0013, TECH-0014, TECH-0015` ;; Interfaces/data flow || `Local request and response flow` ;; Identity/secrets || `No secrets; local development identity` ;; Failure/retry/concurrency || `Fail closed; bounded retries; serialized state` ;; Deployment/operations || `Documentation-only AWS lane; local commands` ;; Validation/evidence || `EX-001 and focused unittest evidence` ;; Rollback/recovery/teardown || `Restore the authorized baseline commit` ;; Brownfield compatibility/migration || {compatibility} ;; Outstanding gaps || `NONE`",
    )
    return text


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
    text = put_contract_table(
        text,
        doctor.ARCHITECTURE_DRIVER_HEADING,
        driver_table,
        doctor.ARCHITECTURE_CANDIDATE_HEADING,
    )
    candidate_table = "\n".join(
        [
            "| Candidate ID | Architecture summary | Requirement coverage | AWS evidence | Eligibility | Failed constraints | Tradeoffs |",
            "|---|---|---|---|---|---|---|",
            f"| CAND-0001 | MANAGED_SERVERLESS_BASELINE: bounded managed entry, compute, and data services | {requirement_list} | AWS-EV-0001, AWS-EV-0002 | ELIGIBLE | NONE | Lowest idle cost and operations; service limits remain revisit triggers |",
            f"| CAND-0002 | Container service with continuously provisioned compute | {requirement_list} | AWS-EV-0001, AWS-EV-0002 | INELIGIBLE | DRV-0001 | More runtime control but unnecessary fixed operations for this bounded workload |",
        ]
    )
    text = put_contract_table(
        text,
        doctor.ARCHITECTURE_CANDIDATE_HEADING,
        candidate_table,
        doctor.ARCHITECTURE_SELECTION_HEADING,
    )
    selection_table = "\n".join(
        [
            "| Architecture ID | Selected candidate | Requirement and driver basis | Rationale | Rejected alternatives | Risks | Mitigations | Security impact | Reliability impact | Operational burden | Cost effect | Breakpoints | Migration path | Revisit triggers | Validation |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
            f"| ARCH-0001 | CAND-0001 | {requirement_list}, DRV-0001 | Meets every hard constraint with the smallest managed surface | CAND-0002 | Managed-service limits | Validate quotas and alarms before deployment | Retains server-side authorization and least-privilege controls | Managed services bound failure domains with tested recovery | No continuously provisioned compute to operate | Pay per request with no intentional idle compute | Reassess at sustained utilization where containers are cheaper | Use versioned APIs and reversible IaC for any later migration | Reassess on quota, residency, or latency changes | Requirement trace and integration tests |",
        ]
    )
    text = put_contract_table(
        text,
        doctor.ARCHITECTURE_SELECTION_HEADING,
        selection_table,
        doctor.ARCHITECTURE_TRACEABILITY_HEADING,
    )
    trace_rows = [
        (
            f"| {requirement_id} | ARCH-0001, API-001 | "
            f"{'PROP-001' if requirement_id == 'FR-001' else 'EX-001'} | "
            "AWS-EV-0001, AWS-EV-0002 |"
        )
        for requirement_id in requirement_ids
    ]
    trace_table = "\n".join(
        [
            "| " + " | ".join(doctor.ARCHITECTURE_TRACEABILITY_HEADERS) + " |",
            "|---|---|---|---|",
            *trace_rows,
        ]
    )
    text = put_contract_table(
        text,
        doctor.ARCHITECTURE_TRACEABILITY_HEADING,
        trace_table,
        doctor.MATERIAL_AWS_EVIDENCE_HEADING,
    )
    evidence_table = "\n".join(
        [
            "| Evidence ID | Discovery ID | Design IDs | Material claim | AWS Core capability | Official reference | Observed date |",
            "|---|---|---|---|---|---|---|",
            "| AWS-EV-0001 | AWS-DISC-0002 | DRV-0001, CAND-0001, CAND-0002, ARCH-0001, TECH-0001, TECH-0002 | AWS Lambda supports the selected bounded Python and FastAPI execution model | retrieve_skill | https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html | 2026-07-17 |",
            "| AWS-EV-0002 | AWS-DISC-0002 | DRV-0001, CAND-0001, CAND-0002, ARCH-0001, TECH-0013 | Amazon API Gateway provides the selected managed regional HTTPS entry point | search_documentation | https://docs.aws.amazon.com/apigateway/latest/developerguide/welcome.html | 2026-07-17 |",
            "| AWS-EV-0003 | AWS-DISC-0002 | TECH-0010 | Amazon Cognito supports the selected authenticated user boundary | retrieve_skill | https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools.html | 2026-07-17 |",
            "| AWS-EV-0004 | AWS-DISC-0002 | TECH-0011 | Amazon DynamoDB supports owner-scoped records with managed persistence | search_documentation | https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html | 2026-07-17 |",
            "| AWS-EV-0005 | AWS-DISC-0002 | TECH-0014 | Amazon CloudWatch provides the selected logs, metrics, and alarms | search_documentation | https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html | 2026-07-17 |",
            "| AWS-EV-0006 | AWS-DISC-0002 | TECH-0004, TECH-0009, TECH-0015 | AWS SAM supports reviewable infrastructure, change sets, deployment, and bounded rollback | retrieve_skill | https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html | 2026-07-17 |",
            "| AWS-EV-0007 | AWS-DISC-0002 | TECH-0008 | AWS KMS supports managed encryption controls for the selected application data path | search_documentation | https://docs.aws.amazon.com/kms/latest/developerguide/overview.html | 2026-07-17 |",
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
    text = put_contract_table(
        text,
        doctor.MATERIAL_AWS_EVIDENCE_HEADING,
        evidence_table,
        "## 14. Architecture overview",
    )
    text = replace_contract_table(
        text,
        "## 23. Example-based scenarios",
        ("Test ID", "Scenario", "Expected result", "Layer"),
        [
            (
                "EX-001",
                "Known happy path",
                "Approved outcome is returned",
                "Integration",
            ),
            (
                "EX-002",
                "Known boundary or failure",
                "Safe rejection preserves approved state",
                "Unit",
            ),
        ],
    )
    technology_rows = (
        (
            "TECH-0001",
            "APPLICATION_RUNTIME",
            "Python 3.12 on AWS Lambda",
            "CURRENT_LTS_AS_OF: 2026-07-01",
        ),
        (
            "TECH-0002",
            "APPLICATION_FRAMEWORK",
            "FastAPI through a Lambda adapter",
            "COMPATIBLE_MAJOR: 1",
        ),
        (
            "TECH-0003",
            "FRONTEND_FRAMEWORK",
            "NOT_APPLICABLE — server-rendered interface",
            "NOT_APPLICABLE — server-rendered interface",
        ),
        (
            "TECH-0004",
            "INFRASTRUCTURE_AS_CODE",
            "AWS SAM infrastructure templates",
            "COMPATIBLE_MAJOR: 1",
        ),
        ("TECH-0005", "PACKAGE_BUILD_TOOLING", "pip", "MINIMUM: 24.0"),
        (
            "TECH-0006",
            "TEST_TOOLING",
            "unittest",
            "ORG_MANAGED: Python standard library",
        ),
        ("TECH-0007", "PROPERTY_TESTING", "Hypothesis", "MINIMUM: 6.0"),
        (
            "TECH-0008",
            "SECURITY_VALIDATION",
            "Bandit static checks; AWS KMS-managed encryption; no application secrets stored",
            "EXACT: 1.7.9",
        ),
        (
            "TECH-0009",
            "DEPLOYMENT_TOOLING",
            "AWS SAM CLI deployment and change sets",
            "MINIMUM: 1.120",
        ),
        (
            "TECH-0010",
            "IDENTITY_AUTHORIZATION",
            "Amazon Cognito with server-side authorization",
            "ORG_MANAGED: approved design contract",
        ),
        (
            "TECH-0011",
            "DATA_STORAGE",
            "Amazon DynamoDB with per-owner records",
            "ORG_MANAGED: approved design contract",
        ),
        (
            "TECH-0012",
            "MESSAGING_RETRIES",
            "NOT_APPLICABLE — synchronous local request flow",
            "NOT_APPLICABLE — synchronous local request flow",
        ),
        (
            "TECH-0013",
            "EDGE_NETWORKING",
            "Amazon API Gateway regional HTTPS endpoint",
            "ORG_MANAGED: approved design contract",
        ),
        (
            "TECH-0014",
            "OBSERVABILITY_INCIDENT_RESPONSE",
            "Amazon CloudWatch logs, metrics, and alarms",
            "ORG_MANAGED: approved design contract",
        ),
        (
            "TECH-0015",
            "RELIABILITY_RECOVERY",
            "AWS SAM rollback to the last validated stack",
            "ORG_MANAGED: approved design contract",
        ),
    )
    reasoning = {
        "APPLICATION_RUNTIME": (
            "The managed runtime fits the bounded workload and current Python support",
            "A second runtime would add packaging and operations cost",
        ),
        "APPLICATION_FRAMEWORK": (
            "It provides the smallest typed HTTP surface on the selected managed runtime",
            "A larger framework adds features the first release does not need",
        ),
        "FRONTEND_FRAMEWORK": (
            "The approved slice uses a server-rendered interface",
            "A separate browser framework adds a second build surface",
        ),
        "INFRASTRUCTURE_AS_CODE": (
            "It keeps the planned AWS shape reviewable and reversible",
            "Hand-written account changes are not deterministic",
        ),
        "PACKAGE_BUILD_TOOLING": (
            "It matches the selected Python runtime",
            "A second package manager adds lock and setup ambiguity",
        ),
        "TEST_TOOLING": (
            "It is available with the runtime and fits the bounded slice",
            "A second unit-test runner adds no current benefit",
        ),
        "PROPERTY_TESTING": (
            "Generated boundary cases protect the approved invariant",
            "Example-only checks miss important input combinations",
        ),
        "SECURITY_VALIDATION": (
            "Static checks and managed encryption protect code and stored records",
            "Manual review alone is not reproducible",
        ),
        "DEPLOYMENT_TOOLING": (
            "It matches the selected reversible infrastructure definition",
            "An unrelated deployment tool would duplicate configuration",
        ),
        "IDENTITY_AUTHORIZATION": (
            "It preserves server-side access decisions with a managed user boundary",
            "Client-only authorization would not enforce the boundary",
        ),
        "DATA_STORAGE": (
            "It preserves owner-scoped records without database operations",
            "A relational database adds operations not required by the access pattern",
        ),
        "MESSAGING_RETRIES": (
            "The approved outcome completes synchronously",
            "A queue adds delayed-state complexity without a requirement",
        ),
        "EDGE_NETWORKING": (
            "A regional managed HTTPS entry point bounds the public interface",
            "A separate CDN adds a layer the current access pattern does not need",
        ),
        "OBSERVABILITY_INCIDENT_RESPONSE": (
            "Managed logs, metrics, and alarms expose failures without sensitive content",
            "Unstructured console output is harder to verify",
        ),
        "RELIABILITY_RECOVERY": (
            "The selected deployment path can restore the last validated stack",
            "A multi-Region recovery design exceeds the current recovery requirement",
        ),
    }
    technology_table = "\n".join(
        [
            "| Decision ID | Concern | Selection | Version policy | Source | Basis IDs | Alternatives and rationale | Compatibility/migration | Validation |",
            "|---|---|---|---|---|---|---|---|---|",
            *(
                f"| {decision_id} | {concern} | {selection} | {policy} | "
                "AGENT_RECOMMENDATION | DES-0001, FR-001 | "
                f"RATIONALE: {reasoning[concern][0]}; "
                f"REJECTED: {reasoning[concern][1]} | "
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
                for requirement_id in sorted(doctor.authoritative_requirement_ids(text))
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
    text = replace_contract_table(
        text,
        doctor.ERROR_HANDLING_HEADING,
        doctor.ERROR_HANDLING_HEADERS,
        [
            (
                "Validation",
                "Request exceeds the approved input shape",
                "No",
                "Reject the request with a safe explanation",
                "Validation error counter without request content",
                "The user corrects the request",
            ),
            (
                "Transient dependency",
                "A dependency times out temporarily",
                "Bounded to 3 attempts",
                "Ask the user to try again later",
                "Retry count and dependency timeout trace",
                "Stop at the retry bound and preserve state",
            ),
            (
                "Permanent dependency",
                "A dependency rejects the approved operation",
                "No",
                "Explain that the operation could not complete",
                "Permanent dependency failure counter",
                "Correct the dependency configuration before retry",
            ),
            (
                "Concurrency conflict",
                "A request uses a stale record version",
                "No or retry with fresh state",
                "Return a conflict response",
                "Conflict counter with the record category",
                "Re-read the current record before retry",
            ),
            (
                "Internal defect",
                "Unexpected application failure",
                "No uncontrolled retry",
                "Return a generic safe error",
                "Alert and trace without sensitive content",
                "Roll back or correct the defect",
            ),
        ],
    )
    text = replace_contract_table(
        text,
        doctor.AWS_SERVICE_DECISION_HEADING,
        doctor.AWS_SERVICE_DECISION_HEADERS,
        [
            (
                "Compute",
                "TECH-0001, TECH-0002",
                "Python 3.12 on AWS Lambda; FastAPI through a Lambda adapter",
                "Pay-per-use compute fits the bounded workload",
                "Managed runtime limits become revisit triggers",
            ),
            (
                "API and edge",
                "TECH-0002, TECH-0013",
                "FastAPI through a Lambda adapter; Amazon API Gateway regional HTTPS endpoint",
                "One managed entry point keeps the interface bounded",
                "A public endpoint requires separate deployment authorization",
            ),
            (
                "Identity",
                "TECH-0010",
                "Amazon Cognito with server-side authorization",
                "The local release preserves the approved identity boundary",
                "An AWS identity provider is deferred until deployment design needs it",
            ),
            (
                "Data",
                "TECH-0011",
                "Amazon DynamoDB with per-owner records",
                "The adapter preserves ownership and supports later migration",
                "A managed AWS store is not locally observed",
            ),
            (
                "Messaging",
                "TECH-0012",
                "NOT_APPLICABLE — synchronous local request flow",
                "No background delivery is required by the approved journey",
                "A queue is reconsidered if asynchronous work becomes material",
            ),
            (
                "Observability",
                "TECH-0014",
                "Amazon CloudWatch logs, metrics, and alarms",
                "The local evidence can verify useful signals without secrets",
                "AWS-native signals remain unobserved before deployment",
            ),
            (
                "Deployment",
                "TECH-0004, TECH-0009, TECH-0015",
                "AWS SAM infrastructure templates; AWS SAM CLI deployment and change sets; AWS SAM rollback to the last validated stack",
                "The selected tools keep planned infrastructure reproducible",
                "Account-side planning still requires separate authority",
            ),
            (
                "Secrets and encryption",
                "TECH-0008",
                "Bandit static checks; AWS KMS-managed encryption; no application secrets stored",
                "The design avoids introducing a secret before it is required",
                "Deployed encryption controls remain unobserved",
            ),
        ],
    )
    text = replace_contract_table(
        text,
        doctor.IAC_VALIDATION_HEADING,
        doctor.IAC_VALIDATION_HEADERS,
        [
            (
                "CloudFormation / SAM / CDK",
                "APPLICABLE",
                "TECH-0004, TECH-0008, TECH-0009",
                "sam validate, selected lint, and policy checks",
                "Review a separately authorized change set bound to the template digest",
                doctor.IAC_VALIDATION_EVIDENCE_DESTINATION,
            ),
            (
                "Terraform",
                "NOT_APPLICABLE - AWS SAM is the selected infrastructure tool",
                "NOT_APPLICABLE - no Terraform technology decision is active",
                "NOT_APPLICABLE - no Terraform configuration is approved",
                "NOT_APPLICABLE - no Terraform plan is approved",
                doctor.IAC_VALIDATION_EVIDENCE_DESTINATION,
            ),
            (
                "Container delivery",
                "NOT_APPLICABLE - no container delivery path is approved",
                "NOT_APPLICABLE - no container technology decision is active",
                "NOT_APPLICABLE - no container artifact is approved",
                "NOT_APPLICABLE - no image deployment is approved",
                doctor.IAC_VALIDATION_EVIDENCE_DESTINATION,
            ),
            (
                "Other approved delivery path",
                "NOT_APPLICABLE - no additional delivery path is approved",
                "NOT_APPLICABLE - no additional delivery technology is active",
                "NOT_APPLICABLE - no additional local validation is needed",
                "NOT_APPLICABLE - no additional AWS planning is approved",
                doctor.IAC_VALIDATION_EVIDENCE_DESTINATION,
            ),
        ],
    )
    return complete_owner_visible_design(
        complete_diagram_contract(complete_project_design_contract(text))
    )


def complete_brownfield_foundation(
    text: str,
    *,
    baseline: str = "a" * 40,
) -> str:
    text = complete_intake_foundation(text, work_context_choice="B")
    values = {
        "Repository and baseline commit": f"`{baseline}`",
        "Deployed environments and observed versions": (
            "`development; version 1 observed`"
        ),
        "Existing architecture and ownership": "`single service; owner alice`",
        "Current interfaces, schemas, and consumers": (
            "`HTTP API v1; schema v1; internal users`"
        ),
        "Current data stores and migration constraints": (
            "`local JSON; preserve records; no migration`"
        ),
        "Existing security and compliance controls": (
            "`owner access; least privilege; no regulated data`"
        ),
        "Baseline verification commands": "`python -m unittest`",
        "Baseline evidence location": "`docs/project/VERIFY.md`",
        "Known defects and accepted debt": "`NONE_OBSERVED`",
        "Repository-to-environment drift": "`NONE_OBSERVED`",
        "Dirty or user-owned working-tree changes": "`NONE`",
        "Protected files and components": "`legacy/**`",
        "Unresolved bootstrap overlay collisions": "`NONE`",
    }
    if set(values) != set(doctor.BROWNFIELD_BASELINE_FIELDS):
        raise AssertionError(
            "Brownfield fixture fields do not match the Engine contract"
        )
    for field, value in values.items():
        text = set_table_value(
            text,
            "### 1.2 Brownfield baseline and preservation contract",
            "## Product requirements",
            field,
            value,
        )
    unresolved = "| PRES-001 | TODO | TODO | TODO | TODO |"
    current = (
        "| PRES-001 | Preserve legacy/** behavior | Baseline verification commands | "
        "Narrow changes only | Parallel application roots or replacement without owner approval |"
    )
    if unresolved in text:
        text = text.replace(unresolved, current, 1)
    elif current not in text:
        raise AssertionError("Brownfield fixture PRES-001 row is missing")
    return set_table_value(
        text,
        "## Document status",
        "## 1. Workload profile",
        "Project mode",
        "`brownfield`",
    )


def complete_existing_design_contract(
    text: str,
    *,
    work_kind: str,
    baseline: str = "a" * 40,
) -> str:
    if work_kind not in {"FEATURE", "INFRASTRUCTURE"}:
        raise AssertionError(
            "Existing-project fixture work kind must be FEATURE or INFRASTRUCTURE"
        )

    text = complete_brownfield_foundation(text, baseline=baseline)
    text = complete_design_contract(text)
    text = complete_coverage_plan(text, work_kind=work_kind, disposition="AMEND")
    text = replace_contract_table_with_sentinel(
        text,
        doctor.FIRST_WAVE_HEADING,
        f"{work_kind} work does not define a greenfield walking skeleton",
    )
    wave_basis = "DES-0001, FR-001, JOURNEY-001, WAVE-001"
    if wave_basis not in text:
        raise AssertionError(
            "Existing-project fixture walking-skeleton basis is missing"
        )
    text = text.replace(wave_basis, "DES-0001, FR-001", 1)
    impact_table = "\n".join(
        [
            "| Change ID | Changed basis IDs | Affected IDs | Preserved IDs | Required revalidation |",
            "|---|---|---|---|---|",
            "| CHANGE-0001 | FR-001 | ARCH-0001 | TECH-0001 | ARCH-0001 |",
        ]
    )
    text = put_contract_table(
        text,
        doctor.CHANGE_IMPACT_HEADING,
        impact_table,
        "## 14. Architecture overview",
    )
    text = set_table_value(
        text,
        "## Document status",
        "## 1. Workload profile",
        "Project mode",
        "`brownfield`",
    )
    source_disposition = (
        APPLICATION_SOURCE_INFRASTRUCTURE_ONLY
        if work_kind == "INFRASTRUCTURE"
        else "BROWNFIELD_PRESERVE: legacy/**"
    )
    text = set_table_value(
        text,
        "## 28. Construction envelope",
        "## 29. Gate B owner authorization record",
        "Application source disposition",
        f"`{source_disposition}`",
    )

    table = doctor.contract_table_after_heading(
        text,
        doctor.DIAGRAM_CONTRACT_HEADING,
        doctor.DIAGRAM_CONTRACT_HEADERS,
    )
    if table is None:
        raise AssertionError("Existing-project diagram contract is missing")
    rows = [list(row) for row in table.rows]
    for row in rows:
        if row[1] == "MIGRATION":
            row[3] = "CURRENT"
            row[5] = "PRES-001, ARCH-0001"
            row[6] = "BOUNDARY-001, ARCH-0001, TECH-0011, TECH-0015"
    text = replace_contract_table(
        text,
        doctor.DIAGRAM_CONTRACT_HEADING,
        doctor.DIAGRAM_CONTRACT_HEADERS,
        [tuple(row) for row in rows],
    )
    text = set_diagram_block(
        text,
        "### Migration view",
        "## 14. Architecture overview",
        """```mermaid
flowchart LR
    accTitle: Existing application compatibility and rollback
    accDescr: Existing requests cross the project boundary into the selected architecture, which keeps compatible owner records and a failure recovery path.
    BOUNDARY-001["Local client adapter to<br/>Application domain"]:::entry
    ARCH-0001["Managed Serverless Baseline"]:::compute
    TECH-0011[("Amazon DynamoDB with<br/>per-owner records")]:::data
    TECH-0015["AWS SAM rollback to the<br/>last validated stack"]:::ops
    BOUNDARY-001 -->|routes existing requests to| ARCH-0001
    ARCH-0001 -->|keeps compatible records in| TECH-0011
    TECH-0015 -. "restores" .-> ARCH-0001
    classDef entry fill:#EAF3FF,stroke:#147EBA,color:#232F3E;
    classDef compute fill:#FFF1E8,stroke:#D86613,color:#232F3E;
    classDef data fill:#EDF7ED,stroke:#248814,color:#232F3E;
    classDef ops fill:#FFF7DF,stroke:#D38B00,color:#232F3E;
```""",
    )
    if work_kind == "INFRASTRUCTURE":
        replacements = {
            "accTitle: Proposed AWS implementation": (
                "accTitle: Infrastructure-only AWS implementation"
            ),
            "accDescr: Requests move through the selected edge, identity, compute, and data services while managed observability, encryption, deployment, and rollback controls support the application.": (
                "accDescr: Existing application traffic keeps its selected edge, "
                "identity, compute, and data services while infrastructure work is "
                "limited to managed operations, deployment, and rollback controls."
            ),
        }
        for before, after in replacements.items():
            if text.count(before) != 1:
                raise AssertionError(
                    f"Expected one infrastructure diagram marker: {before}"
                )
            text = text.replace(before, after, 1)

    design_revision = doctor.table_after_heading(text, "## Document status")[
        "Current design revision"
    ]
    contract, issues = doctor.derive_design_contract(
        text,
        design_revision,
        required=True,
    )
    if issues or contract.status != "READY":
        raise AssertionError(
            "Existing-project design fixture is invalid: " + "; ".join(issues)
        )
    return text


def complete_legacy_design_bridge(text: str) -> str:
    text = exact_legacy_requirements_projection(
        complete_design_contract(approve_gate_a(text))
    )
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
        [
            (
                "STATE-001",
                "RESOURCE-001",
                "PENDING, READY",
                "PENDING",
                "PENDING to READY",
                "READY",
                "Reject invalid transitions",
                "FR-001",
                "AC-FR-001",
            )
        ],
    )
    text = replace_contract_table(
        text,
        doctor.FIRST_WAVE_HEADING,
        doctor.FIRST_WAVE_HEADERS,
        [
            (
                "WAVE-001",
                "NEW_BUILD",
                "NONE",
                "FR-001",
                "AC-FR-001",
                "HARNESS-004",
                "NONE",
            )
        ],
    )
    return complete_state_diagrams(text, actorless_primary=True)


def schema_six_design_projection(text: str) -> str:
    """Project a modern test design into the exact pre-AWS schema-six shape."""

    text = text.replace(
        "| Project design contract schema | `7` |",
        "| Project design contract schema | `6` |",
        1,
    )
    text = re.sub(
        r"(?m)^\| Application source disposition \|.*\r?\n",
        "",
        text,
        count=1,
    )
    table = doctor.contract_table_after_heading(
        text, doctor.DIAGRAM_CONTRACT_HEADING, doctor.DIAGRAM_CONTRACT_HEADERS
    )
    assert table is not None
    legacy_endpoints = {
        "SYSTEM_CONTEXT": "ACT-001, TECH-0013, BOUNDARY-001, API-001, TECH-0002, TECH-0001, ARCH-0001, TECH-0011",
        "PRIMARY_OUTCOME": "ACT-001, API-001",
        "DATA_LIFECYCLE": "API-001, TECH-0011",
        "FAILURE_RECOVERY": "API-001, TECH-0015",
    }
    return replace_contract_table(
        text,
        doctor.DIAGRAM_CONTRACT_HEADING,
        doctor.DIAGRAM_CONTRACT_HEADERS,
        [
            (*row[:6], legacy_endpoints.get(row[1], row[6]))
            for row in table.rows
            if row[1] != "AWS_IMPLEMENTATION"
        ],
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


def no_task_requirement_evidence_row(
    requirement_id: str,
    *,
    evidence_id: str,
    status: str,
    acceptance_id: str | None = None,
) -> tuple[str, ...]:
    acceptance_id = acceptance_id or f"AC-{requirement_id}"
    return (
        evidence_id,
        f"{requirement_id}, {acceptance_id}",
        "NONE",
        f"Current evidence satisfies {requirement_id} and {acceptance_id}",
        "Focused current evidence was reviewed and passed",
        "NOT_APPLICABLE - local or applicability evidence",
        "Current REQ-0001 / DES-0001 / AUTH-0001 evidence set",
        status,
    )


def requirement_evidence_verify(
    *rows: tuple[str, ...],
    requirements_revision: str = "REQ-0001",
    design_revision: str = "DES-0001",
    construction_authorization: str = "AUTH-0001",
    source: str | None = None,
) -> str:
    text = source or (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(
        encoding="utf-8"
    )
    for field, value in (
        ("Requirements revision", requirements_revision),
        ("Design revision", design_revision),
        ("Construction authorization", construction_authorization),
    ):
        text = set_table_value(
            text,
            "## Active evidence scope",
            "## Evidence status vocabulary",
            field,
            f"`{value}`",
        )
    return replace_contract_table(
        text,
        doctor.VERIFICATION_MATRIX_HEADING,
        doctor.VERIFICATION_MATRIX_HEADERS,
        list(rows),
    )


def modern_task_requirement_rules() -> dict[str, tuple[str, str]]:
    text = complete_design_contract(
        (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
    )
    intake, intake_issues = doctor.derive_intake_foundation_contract(
        text,
        "greenfield",
        grandfather_current_gate_a=False,
    )
    if intake_issues:
        raise AssertionError(intake_issues)
    requirements, requirement_issues = doctor.derive_requirements_contract(
        text,
        "low",
        intake,
        required=True,
        grandfather_current_gate_a=False,
    )
    if requirement_issues:
        raise AssertionError(requirement_issues)
    return doctor.task_requirement_rules(text, requirements)


def refresh_control_hashes(project: Path) -> None:
    manifest_path = project / "bootstrap.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["control_sha256"] = {
        relative: hashlib.sha256((project / relative).read_bytes()).hexdigest()
        for relative in doctor.CONTROL_HASH_FILES
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def refresh_document_summaries(project: Path) -> None:
    """Apply the Engine-derived presentation blocks at a lifecycle checkpoint."""

    refresh_control_hashes(project)
    report = doctor.inspect_project(project)
    for summary in report["document_summaries"]["documents"]:
        path = project / str(summary["path"])
        source_text = path.read_text(encoding="utf-8")
        begin = source_text.index(document_summaries.SUMMARY_BEGIN)
        begin += len(document_summaries.SUMMARY_BEGIN)
        end = source_text.index(document_summaries.SUMMARY_END, begin)
        rendered = document_summaries.render_summary_markdown(summary)
        path.write_text(
            source_text[:begin] + "\n" + rendered + source_text[end:],
            encoding="utf-8",
        )
    refresh_control_hashes(project)


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
        "AWS environment": (f"ENVIRONMENT: {environment}; CLASS: NON_PRODUCTION"),
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
            "Expires at 2099-12-31T23:59:59Z; earlier completion: release review"
        ),
        "Authorized baseline commit": "a" * 40,
    }


def ready_preflight(*, account: str, region: str, environment: str) -> dict[str, str]:
    return {
        "status": "READY",
        "preflight_id": "AWS-PREFLIGHT-0001",
        "account_access": "READ_ONLY_OBSERVED",
        "account": account,
        "region": region,
        "environment": environment,
    }


class BootstrapDoctorTests(unittest.TestCase):
    def test_required_project_text_has_per_file_and_aggregate_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "first.txt").write_text("1234", encoding="utf-8")
            (root / "second.txt").write_text("56", encoding="utf-8")

            original_file_limit = doctor.MAX_REQUIRED_FILE_BYTES
            original_project_limit = doctor.MAX_PROJECT_SOURCE_BYTES
            try:
                doctor.MAX_REQUIRED_FILE_BYTES = 3
                doctor.MAX_PROJECT_SOURCE_BYTES = 20
                per_file = doctor.Context(root)
                self.assertIsNone(doctor.safe_read_text(per_file, "first.txt"))
                self.assertEqual(
                    [item.code for item in per_file.diagnostics],
                    ["REQUIRED_FILE_TOO_LARGE"],
                )

                doctor.MAX_REQUIRED_FILE_BYTES = 10
                doctor.MAX_PROJECT_SOURCE_BYTES = 5
                aggregate = doctor.Context(root)
                self.assertEqual(
                    doctor.safe_read_text(aggregate, "first.txt"),
                    "1234",
                )
                self.assertIsNone(doctor.safe_read_text(aggregate, "second.txt"))
                self.assertEqual(
                    [item.code for item in aggregate.diagnostics],
                    ["PROJECT_SOURCE_LIMIT"],
                )
            finally:
                doctor.MAX_REQUIRED_FILE_BYTES = original_file_limit
                doctor.MAX_PROJECT_SOURCE_BYTES = original_project_limit

    def test_required_project_text_is_cached_and_counted_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "record.txt").write_text("record", encoding="utf-8")
            context = doctor.Context(root)

            self.assertEqual(doctor.safe_read_text(context, "record.txt"), "record")
            first_count = context.source_bytes_read
            self.assertEqual(doctor.safe_read_text(context, "record.txt"), "record")
            self.assertEqual(context.source_bytes_read, first_count)

    def test_prd_snapshot_is_bounded_normalized_and_content_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prd = root / doctor.PRD_FILE
            prd.parent.mkdir(parents=True)
            prd.write_bytes(b"first\r\nsecond\r")

            text, digest = doctor.bounded_prd_snapshot(root)
            self.assertEqual(text, "first\nsecond\n")
            self.assertEqual(
                digest,
                "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
            self.assertEqual(doctor.bounded_prd_snapshot(root, digest)[0], text)

            prd.write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                doctor.bounded_prd_snapshot(root, digest)

            original_limit = doctor.MAX_REQUIRED_FILE_BYTES
            try:
                doctor.MAX_REQUIRED_FILE_BYTES = 3
                with self.assertRaisesRegex(ValueError, "bounded PRD snapshot"):
                    doctor.bounded_prd_snapshot(root)
            finally:
                doctor.MAX_REQUIRED_FILE_BYTES = original_limit

    def test_manifest_rejects_excessive_required_file_inventory(self) -> None:
        context = doctor.Context(PROJECT_ROOT)
        manifest = {
            "schema_version": 1,
            "bootstrap_version": "1.1.0",
            "python_requires": ">=3.11",
            "required_files": [
                f"docs/record-{index}.md"
                for index in range(doctor.MAX_REQUIRED_FILES + 1)
            ],
            "canonical_prompt_ids": [],
            "template_placeholders": [],
            "control_sha256": {},
            "source_sha256": {},
        }

        doctor.validate_manifest(context, manifest)

        self.assertIn(
            "MANIFEST_REQUIRED_FILES_LIMIT",
            [item.code for item in context.diagnostics],
        )
        self.assertEqual(context.texts, {})

    def test_manifest_control_hashes_cannot_reference_omitted_required_file(
        self,
    ) -> None:
        manifest = json.loads(
            (PROJECT_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        omitted = "scripts/fastlane_process.py"
        manifest["required_files"].remove(omitted)
        manifest["source_sha256"].pop(omitted)
        context = doctor.Context(PROJECT_ROOT)

        doctor.validate_manifest(context, manifest)

        self.assertIn(
            "MANIFEST_CONTROL_REQUIRED_FILES",
            [item.code for item in context.diagnostics],
        )

    def test_legacy_authenticated_task_modes_fail_closed_and_require_replan(
        self,
    ) -> None:
        self.assertEqual(doctor.TASK_AWS_MODES, {"NONE", "DOCS_ONLY"})
        context = doctor.Context(PROJECT_ROOT)
        doctor.record_task_graph_validation_errors(
            context,
            "\n".join(
                (
                    "TASK-001: invalid AWS mode 'READ_ONLY'",
                    "TASK-002: invalid AWS mode 'MUTATION'",
                )
            ),
        )
        self.assertEqual(
            [item.code for item in context.diagnostics],
            ["TASK_AWS_MODE_REPLAN_REQUIRED"],
        )
        self.assertIn("preserve every DONE completion", context.diagnostics[0].message)
        self.assertIn("append-only VERIFY evidence", context.diagnostics[0].message)

        remediation = doctor.derive_remediation(
            context,
            classification="ACTIVE_GREENFIELD",
            gate_a="APPROVED_FOR_DESIGN",
            gate_b="APPROVED_FOR_CONSTRUCTION",
            envelope={
                "Allowed repository write set": "PATHS: docs/project/TASKS.md",
                "Excluded or owner-only write set": "NONE",
                "Protected dirty paths": "NONE",
            },
            tasks=doctor.TaskSummary(),
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            owner_stage_hint="DELIVER",
        )
        self.assertEqual(remediation["items"][0]["category"], "AGENT_REPLAN")
        self.assertEqual(remediation["next_action"]["action_kind"], "REPLAN_TASKS")
        self.assertTrue(remediation["next_action"]["preserve_done_evidence"])
        self.assertTrue(remediation["next_action"]["automatic_continuation_allowed"])

        mixed = doctor.Context(PROJECT_ROOT)
        doctor.record_task_graph_validation_errors(
            mixed,
            "TASK-001: invalid AWS mode 'READ_ONLY'\n"
            "TASK-003: invalid attempt counters",
        )
        self.assertEqual(
            [item.code for item in mixed.diagnostics],
            ["TASK_AWS_MODE_REPLAN_REQUIRED", "TASK_GRAPH_INVALID"],
        )

    def test_aws_lifecycle_intent_record_is_exact_non_authorizing_and_migratable(
        self,
    ) -> None:
        def validate(lines: list[str]) -> tuple[object, dict[str, object]]:
            context = doctor.Context(PROJECT_ROOT)
            context.texts[doctor.VERIFY_FILE] = "\n".join(
                (
                    "## Current release decision",
                    "",
                    "- Release state: `RELEASE_VERIFIED`",
                    *lines,
                    "- Active evidence cutoff: NONE",
                    "",
                    "## Evidence status vocabulary",
                )
            )
            return context, doctor.validate_aws_lifecycle_intent_record(context)

        for lines in ([], ["- AWS lifecycle intent: `NONE`"]):
            with self.subTest(lines=lines):
                context, record = validate(lines)
                self.assertFalse(context.has_errors)
                self.assertEqual(record["provenance_status"], "LEGACY_NONE")
                self.assertEqual(record["value"], "NONE")
                self.assertFalse(record["authorizes_aws_access"])
                self.assertFalse(record["authorizes_mutation"])

        current_cases = (
            (
                [
                    "- AWS lifecycle intent: `NONE`",
                    "- AWS lifecycle intent source: `NONE`",
                    "- AWS lifecycle intent recorded at: `NONE`",
                ],
                "NONE",
            ),
            (
                [
                    "- AWS lifecycle intent: `RESIDUAL_REVIEW`",
                    "- AWS lifecycle intent source: `owner-message MSG-AWS-LIFECYCLE-0001`",
                    "- AWS lifecycle intent recorded at: `2026-07-29T12:00:00+00:00`",
                ],
                "RESIDUAL_REVIEW",
            ),
        )
        for lines, expected in current_cases:
            with self.subTest(expected=expected):
                context, record = validate(lines)
                self.assertFalse(context.has_errors)
                self.assertEqual(record["provenance_status"], "CURRENT")
                self.assertEqual(record["value"], expected)
                self.assertFalse(record["authorizes_aws_access"])
                self.assertFalse(record["authorizes_mutation"])

        malformed_cases = (
            [
                "- AWS lifecycle intent: `TEARDOWN`",
                "- AWS lifecycle intent recorded at: `2026-07-29T12:00:00Z`",
            ],
            [
                "- AWS lifecycle intent: `TEARDOWN`",
                "- AWS lifecycle intent source: `conversation inference`",
                "- AWS lifecycle intent recorded at: `2026-07-29T12:00:00Z`",
            ],
            [
                "- AWS lifecycle intent: `TEARDOWN`",
                "- AWS lifecycle intent source: `owner-message MSG-AWS-LIFECYCLE-0002`",
                "- AWS lifecycle intent recorded at: `2026-07-29T12:00:00`",
            ],
            [
                "- AWS lifecycle intent source: `owner-message MSG-AWS-LIFECYCLE-0003`",
                "- AWS lifecycle intent: `TEARDOWN`",
                "- AWS lifecycle intent recorded at: `2026-07-29T12:00:00Z`",
            ],
            [
                "- AWS lifecycle intent: `TEARDOWN`",
                "- AWS lifecycle intent source: `owner-message MSG-AWS-LIFECYCLE-0004`",
                "- AWS lifecycle intent recorded at: `2026-07-29T12:00:00Z`",
                "- AWS lifecycle intent: `TEARDOWN`",
            ],
        )
        for lines in malformed_cases:
            with self.subTest(lines=lines):
                context, record = validate(lines)
                self.assertIn(
                    "AWS_LIFECYCLE_INTENT_PROVENANCE",
                    codes(
                        {
                            "diagnostics": [
                                item.to_dict() for item in context.diagnostics
                            ]
                        }
                    ),
                )
                self.assertEqual(record["provenance_status"], "LEGACY_NONE")
                self.assertEqual(record["value"], "NONE")

    def test_lifecycle_intent_write_authority_requires_a_settled_release_boundary(
        self,
    ) -> None:
        terminal = doctor.TaskSummary(
            plan_revision="PLAN-0001",
            plan_state="CURRENT",
            statuses={"TASK-001": "DONE"},
        )
        no_external = {"kind": "NONE", "validity": "NONE"}
        not_active = {"status": "NOT_ACTIVE", "issues": []}
        consumed = {"status": "CONSUMED", "issues": []}
        teardown = {"status": "NOT_ACTIVE", "issues": []}

        denied = doctor.derive_aws_lifecycle_intent_write_authority(
            doctor.Context(PROJECT_ROOT),
            terminal,
            "NOT_READY",
            not_active,
            teardown,
            no_external,
        )
        self.assertFalse(denied["valid"])

        for release_state, deployment in (
            ("NOT_READY", consumed),
            ("RELEASE_VERIFIED", not_active),
            ("RELEASE_VERIFIED", consumed),
        ):
            with self.subTest(
                release_state=release_state, deployment=deployment["status"]
            ):
                authority = doctor.derive_aws_lifecycle_intent_write_authority(
                    doctor.Context(PROJECT_ROOT),
                    terminal,
                    release_state,
                    deployment,
                    teardown,
                    no_external,
                )
                self.assertEqual(authority["kind"], "AWS_LIFECYCLE_INTENT_RECORD")
                self.assertTrue(authority["valid"])
                self.assertEqual(authority["allowed_write_paths"], [doctor.VERIFY_FILE])
                self.assertEqual(
                    authority["allowed_sections"], ["## Current release decision"]
                )
                self.assertEqual(
                    authority["allowed_operations"], ["UPDATE_AWS_LIFECYCLE_INTENT"]
                )
                self.assertEqual(
                    authority["allowed_values"], ["NONE", "RESIDUAL_REVIEW", "TEARDOWN"]
                )
                self.assertEqual(authority["construction_authorization"], "NONE")
                self.assertEqual(authority["aws_mutation_authority"], "NONE")

        current_external = doctor.derive_aws_lifecycle_intent_write_authority(
            doctor.Context(PROJECT_ROOT),
            terminal,
            "RELEASE_VERIFIED",
            not_active,
            teardown,
            {"kind": "AWS_READ_ONLY", "validity": "CURRENT"},
        )
        self.assertFalse(current_external["valid"])
        pending_action = doctor.derive_aws_lifecycle_intent_write_authority(
            doctor.Context(PROJECT_ROOT),
            terminal,
            "RELEASE_VERIFIED",
            not_active,
            {"status": "POST_ACTION_REVIEW", "issues": []},
            no_external,
        )
        self.assertFalse(pending_action["valid"])
        active_intent_route = doctor.derive_aws_lifecycle_intent_write_authority(
            doctor.Context(PROJECT_ROOT),
            terminal,
            "RELEASE_VERIFIED",
            not_active,
            teardown,
            no_external,
            lifecycle_intent={"value": "RESIDUAL_REVIEW"},
        )
        self.assertFalse(active_intent_route["valid"])
        for terminal_status, expected_values in (
            ("VERIFIED_CLEAN", ["NONE", "RESIDUAL_REVIEW", "TEARDOWN"]),
            ("READY_FOR_TEARDOWN", ["RETAIN", "RESIDUAL_REVIEW", "TEARDOWN"]),
            ("RESIDUALS_REMAIN", ["RETAIN", "RESIDUAL_REVIEW", "TEARDOWN"]),
        ):
            with self.subTest(
                terminal_intent_status=terminal_status,
                expected_values=expected_values,
            ):
                terminal_intent_update = (
                    doctor.derive_aws_lifecycle_intent_write_authority(
                        doctor.Context(PROJECT_ROOT),
                        terminal,
                        "RELEASE_VERIFIED",
                        not_active,
                        {"status": terminal_status, "issues": []},
                        no_external,
                        lifecycle_intent={"value": "RESIDUAL_REVIEW"},
                    )
                )
                self.assertTrue(terminal_intent_update["valid"])
                self.assertEqual(
                    terminal_intent_update["allowed_values"], expected_values
                )

        self.assertFalse(
            doctor.aws_lifecycle_intent_route_is_eligible(
                "TEARDOWN",
                "RELEASE_REVIEW",
                "NOT_READY",
                terminal,
                not_active,
                teardown,
            )
        )
        self.assertTrue(
            doctor.aws_lifecycle_intent_route_is_eligible(
                "TEARDOWN", "RELEASE_REVIEW", "NOT_READY", terminal, consumed, teardown
            )
        )

    def copy_project(
        self,
        destination: Path,
        *,
        source_overrides: Mapping[str, bytes] | None = None,
    ) -> Path:
        project = destination / "project"
        project.mkdir()
        manifest = json.loads(
            (PROJECT_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
        )
        overrides = dict(source_overrides or {})
        unexpected = sorted(set(overrides) - set(manifest["required_files"]))
        if unexpected:
            raise AssertionError(
                "Fixture overrides are not manifest-required: " + ", ".join(unexpected)
            )
        for relative in manifest["required_files"]:
            target = project.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative in overrides:
                target.write_bytes(overrides[relative])
            else:
                source = PROJECT_ROOT.joinpath(*PurePosixPath(relative).parts)
                shutil.copy2(source, target)
        values = dict(bootstrap_runtime.PLACEHOLDERS)
        values.update(
            {
                "{{PROJECT_NAME}}": "Doctor Test Project",
                "{{AWS_REGION}}": "us-west-2",
                "{{COST_POSTURE}}": "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
            }
        )
        for relative in manifest["required_files"]:
            if not bootstrap_runtime.should_render_path(relative):
                continue
            path = project.joinpath(*PurePosixPath(relative).parts)
            rendered = bootstrap_runtime.rendered_bytes(
                path, values, relative=relative, render=True
            )
            if rendered != path.read_bytes():
                path.write_bytes(rendered)
        return project

    def approve_project(
        self,
        project: Path,
        *,
        gate_b: bool = True,
        baseline_paths: tuple[str, ...] | None = None,
    ) -> None:
        baseline = "a" * 40
        if gate_b:
            if baseline_paths is not None:
                normalized = tuple(
                    PurePosixPath(path).as_posix() for path in baseline_paths
                )
                if (
                    not normalized
                    or len(normalized) != len(set(normalized))
                    or normalized != baseline_paths
                    or any(
                        PurePosixPath(path).is_absolute()
                        or "." in PurePosixPath(path).parts
                        or ".." in PurePosixPath(path).parts
                        or not project.joinpath(*PurePosixPath(path).parts).is_file()
                        for path in normalized
                    )
                ):
                    raise AssertionError("Fixture baseline paths are invalid")
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            subprocess.run(
                ["git", "-C", str(project), "config", "maintenance.auto", "false"],
                check=True,
            )
            if baseline_paths is not None:
                empty_hooks = project / ".git/fastlane-empty-hooks"
                empty_hooks.mkdir()
                (project / ".git/info/attributes").write_text(
                    "* -text -filter -ident -working-tree-encoding\n",
                    encoding="utf-8",
                )
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(project),
                        "config",
                        "core.hooksPath",
                        str(empty_hooks),
                    ],
                    check=True,
                )
                subprocess.run(
                    ["git", "-C", str(project), "config", "commit.gpgsign", "false"],
                    check=True,
                )
            subprocess.run(
                ["git", "-C", str(project), "config", "user.name", "Doctor Test"],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(project),
                    "config",
                    "user.email",
                    "doctor@example.test",
                ],
                check=True,
            )
            if baseline_paths is None:
                subprocess.run(["git", "-C", str(project), "add", "."], check=True)
            else:
                excluded = project / ".git/info/exclude"
                excluded.write_text("*\n", encoding="utf-8")
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(project),
                        "add",
                        "-f",
                        "--",
                        *baseline_paths,
                    ],
                    check=True,
                )
            subprocess.run(
                ["git", "-C", str(project), "commit", "-qm", "baseline"], check=True
            )
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
                verify_path.read_text(encoding="utf-8"),
                "DESIGN-10",
                advisory_design_binding=(
                    "DES-0001; TECH: " + ", ".join(MATERIAL_AWS_TECH_IDS)
                ),
            )
            verify_path.write_text(verify_text, encoding="utf-8")

    def approve_existing_project(
        self,
        project: Path,
        *,
        work_kind: str,
        baseline_paths: tuple[str, ...] | None = None,
    ) -> str:
        if work_kind not in {"FEATURE", "INFRASTRUCTURE"}:
            raise AssertionError(
                "Existing-project fixture work kind must be FEATURE or INFRASTRUCTURE"
            )

        prd_path = project / "docs/project/PRD.md"
        tasks_path = project / "docs/project/TASKS.md"
        source_prd = prd_path.read_text(encoding="utf-8")
        source_tasks = tasks_path.read_text(encoding="utf-8")

        self.approve_project(
            project,
            gate_b=True,
            baseline_paths=baseline_paths,
        )
        baseline = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        text = complete_brownfield_foundation(source_prd, baseline=baseline)
        text = approve_gate_a(text, project_mode="brownfield")
        text = approve_gate_b(
            text,
            baseline=baseline,
            design_builder=lambda candidate: complete_existing_design_contract(
                candidate,
                work_kind=work_kind,
                baseline=baseline,
            ),
        )
        text = set_table_value(
            text,
            "### Gate B — readiness card",
            "## 28. Construction envelope",
            "Brownfield compatibility/migration",
            "`PRES-001; CURRENT migration and rollback view`",
        )
        if work_kind == "INFRASTRUCTURE":
            in_scope = "`infrastructure and tests in development`"
            write_set = "`PATHS: infrastructure/**; tests/**`"
            source_disposition = f"`{APPLICATION_SOURCE_INFRASTRUCTURE_ONLY}`"
        else:
            in_scope = "`legacy service and tests in development`"
            write_set = "`PATHS: legacy/**; tests/**`"
            source_disposition = "`BROWNFIELD_PRESERVE: legacy/**`"

        scope_ids = (
            *MODERN_APPROVED_REQUIREMENT_IDS,
            "ARCH-0001",
            *(f"TECH-{number:04d}" for number in range(1, 16)),
            "PROP-001",
            "HARNESS-004",
            "JOURNEY-001",
            "API-001",
            "BOUNDARY-001",
            "PRES-001",
        )
        envelope_values = {
            "Project mode": "`brownfield`",
            "Authorized requirement and design IDs": (
                "`REQ: REQ-0001; DES: DES-0001; SCOPE_IDS: "
                + ", ".join(scope_ids)
                + "`"
            ),
            "In-scope components and environments": in_scope,
            "Allowed repository write set": write_set,
            "Application source disposition": source_disposition,
        }
        for field, value in envelope_values.items():
            text = set_table_value(
                text,
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                field,
                value,
            )
        text = rebind_gate_b_envelope(text)
        prd_path.write_text(text, encoding="utf-8")

        tasks_path.write_text(
            current_task_snapshot(source_tasks, baseline=baseline),
            encoding="utf-8",
        )
        state_path = project / "bootstrap.yaml"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["project"].update(
            {
                "mode": "brownfield",
                "delivery_profile": "quick-mvp",
                "effective_risk": "low",
                "aws_lane": "documentation-only",
                "brownfield_baseline": "RECORDED",
            }
        )
        state["lifecycle"].update(
            {
                "gate_a": "APPROVED_FOR_DESIGN",
                "gate_b": "APPROVED_FOR_CONSTRUCTION",
            }
        )
        state_path.write_text(json.dumps(state), encoding="utf-8")
        refresh_document_summaries(project)
        return baseline

    def set_non_material_req_evidence(self, project: Path) -> None:
        prd_path = project / "docs/project/PRD.md"
        text = prd_path.read_text(encoding="utf-8")
        for field, value in {
            "AWS Core materiality": "`NOT_MATERIAL`",
            "AWS materiality basis IDs": (
                "`NONE — no AWS-specific fact affects Gate A`"
            ),
            "AWS Core discovery IDs": (
                "`NONE — AWS evidence is not material to Gate A`"
            ),
            "Unresolved material AWS fact IDs": "`NONE`",
        }.items():
            text = set_table_value(
                text,
                "### Gate A — agent analysis record",
                "### Gate A — owner acceptance record",
                field,
                value,
            )
        prd_path.write_text(text, encoding="utf-8")

    def pending_gate_a(self, project: Path) -> str:
        self.approve_project(project, gate_b=False)
        self.set_non_material_req_evidence(project)
        prd_path = project / "docs/project/PRD.md"
        text = prd_path.read_text(encoding="utf-8")
        text = set_table_value(
            text,
            "## Document status",
            "## 1. Workload profile",
            "Gate A derived status",
            "`PENDING_OWNER_APPROVAL`",
        )
        for field, value in {
            "Approver": "TODO",
            "Owner decision": "`PENDING`",
            "Authorized requirements revision": "TODO",
            "Authorized cost posture": "TODO",
            "Explicitly accepted assumption IDs": "TODO / `NONE`",
            "Authorization provided at": "TODO (ISO 8601 with timezone)",
            "Authorization source": "TODO (message, issue, meeting record, or commit link)",
            "Verbatim owner receipt": "`TODO`",
            "Derived Gate A state": "`PENDING_OWNER_APPROVAL`",
        }.items():
            text = set_table_value(
                text,
                "### Gate A — owner acceptance record",
                "### Gate A validation and invalidation rules",
                field,
                value,
            )
        proposal = "\n".join(
            [
                "APPROVE REQUIREMENTS GATE A",
                "Requirements revision: REQ-0001",
                "Cost posture: MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
                "Accepted assumptions: NONE",
                "Approver: <name/handle>",
            ]
        )
        prd_path.write_text(set_receipt(text, "gate-a", proposal), encoding="utf-8")
        state_path = project / "bootstrap.yaml"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["lifecycle"]["gate_a"] = "PENDING_OWNER_APPROVAL"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        refresh_document_summaries(project)
        report = doctor.inspect_project(project)
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["document_summaries"]["status"], "CURRENT")
        self.assertEqual(report["lifecycle_state"], "WAITING_GATE_A")
        self.assertEqual(report["next_prompt"], "INTAKE-20")
        return proposal.replace("<name/handle>", "alice")

    def pending_gate_b(
        self,
        project: Path,
        *,
        baseline_paths: tuple[str, ...] | None = None,
    ) -> str:
        self.approve_project(project, baseline_paths=baseline_paths)
        self.set_non_material_req_evidence(project)
        prd_path = project / "docs/project/PRD.md"
        text = prd_path.read_text(encoding="utf-8")
        text = set_table_value(
            text,
            "## Document status",
            "## 1. Workload profile",
            "Gate B derived status",
            "`PENDING_OWNER_APPROVAL`",
        )
        for field, value in {
            "Approver": "TODO",
            "Owner decision": "`PENDING`",
            "Authorized requirements revision": "TODO",
            "Authorized design revision": "TODO",
            "Authorized construction authorization ID": "TODO",
            "Authorized construction envelope SHA-256": "TODO",
            "Authorization provided at": "TODO (ISO 8601 with timezone)",
            "Authorization source": "TODO (message, issue, meeting record, or commit link)",
            "Verbatim owner receipt": "`TODO`",
            "Derived Gate B state": "`PENDING_OWNER_APPROVAL`",
        }.items():
            text = set_table_value(
                text,
                "## 29. Gate B owner authorization record",
                "## 30. Gate B validation and invalidation rules",
                field,
                value,
            )
        digest = doctor.canonical_envelope_sha256(text)
        proposal = "\n".join(
            [
                "APPROVE PRD AND CONSTRUCTION GATE B",
                "Requirements revision: REQ-0001",
                "Design revision: DES-0001",
                "Construction authorization: AUTH-0001",
                f"Construction envelope SHA-256: {digest}",
                "Use the proposed construction envelope above.",
                "Approver: <name/handle>",
            ]
        )
        prd_path.write_text(set_receipt(text, "gate-b", proposal), encoding="utf-8")
        state_path = project / "bootstrap.yaml"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["lifecycle"]["gate_b"] = "PENDING_OWNER_APPROVAL"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        tasks_path = project / "docs/project/TASKS.md"
        tasks = set_table_value(
            tasks_path.read_text(encoding="utf-8"),
            "## Active execution snapshot",
            "## Dependencies, waivers, and waves",
            "Gate B state",
            "`PENDING_OWNER_APPROVAL`",
        )
        tasks = set_table_value(
            tasks,
            "## Active execution snapshot",
            "## Dependencies, waivers, and waves",
            "Next safe action",
            "Complete Gate B; when current, run `TASK-10`.",
        )
        tasks_path.write_text(tasks, encoding="utf-8")
        refresh_document_summaries(project)
        report = doctor.inspect_project(project)
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["document_summaries"]["status"], "CURRENT")
        self.assertEqual(report["lifecycle_state"], "WAITING_GATE_B")
        self.assertEqual(report["next_prompt"], "DESIGN-20")
        return proposal.replace("<name/handle>", "alice")

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

        subprocess.run(
            ["git", "-C", str(project), "add", "docs/project/PRD.md"], check=True
        )
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
                requirements=f"{MODERN_TASK_REQUIREMENT_TRACE}; PROP-001",
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
                "## Dependencies, waivers, and waves",
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
        placeholder = (
            "| `NONE` | `NONE` | TODO | `REQ-0001` / `DES-0001` / `AUTH-0001` | "
            "TODO | No work started | `NONE` | Complete Gate B; when current, run "
            "`TASK-10` |"
        )
        self.assertIn(placeholder, text)
        text = text.replace(placeholder, placeholder + "\n" + checkpoint.rstrip(), 1)
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
        self.assertEqual(report["gates"], {"gate_a": "BLOCKED", "gate_b": "BLOCKED"})
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
        self.assertEqual(report["bootstrap_version"], "1.2.43")
        self.assertEqual(report["classification"], "TEMPLATE_SOURCE")
        summaries = report["document_summaries"]
        self.assertEqual(summaries["schema_version"], 1)
        self.assertEqual(summaries["status"], "CURRENT")
        self.assertEqual(
            {item["path"] for item in summaries["documents"]},
            {
                f"docs/project/{name}.md"
                for name in ("README", "PRD", "TASKS", "VERIFY", "RUNBOOK", "BUGFIX")
            },
        )
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
        self.assertEqual(report["design_contract"]["schema_version"], 7)
        self.assertIn(
            report["design_contract"]["status"],
            {"UNINITIALIZED", "BLOCKED"},
        )
        self.assertEqual(report["adr_rationale"]["status"], "NONE")
        self.assertFalse(report["adr_rationale"]["authoritative"])

    def test_current_adr_is_additive_and_digest_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(Path(temporary))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            prd_path.write_text(
                bind_technology_adr(prd_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            adr_path = project / "docs/adr/0001-runtime.md"
            adr_path.write_text(accepted_runtime_adr(), encoding="utf-8")
            refresh_document_summaries(project)

            first = doctor.inspect_project(project)
            self.assertTrue(first["ok"], first["diagnostics"])
            self.assertEqual(first["adr_rationale"]["status"], "CURRENT")
            self.assertEqual(first["gates"]["gate_b"], "APPROVED_FOR_CONSTRUCTION")
            design_digest = first["design_contract"]["canonical_sha256"]
            gate_b = dict(first["gates"])

            adr_path.write_text(
                accepted_runtime_adr(
                    context=(
                        "The same canonical selection now has clearer rationale for "
                        "a human reviewer."
                    )
                ),
                encoding="utf-8",
            )
            second = doctor.inspect_project(project)
            self.assertTrue(second["ok"], second["diagnostics"])
            self.assertEqual(second["adr_rationale"]["status"], "CURRENT")
            self.assertNotEqual(
                first["adr_rationale"]["projection_sha256"],
                second["adr_rationale"]["projection_sha256"],
            )
            self.assertEqual(
                second["design_contract"]["canonical_sha256"], design_digest
            )
            self.assertEqual(second["gates"], gate_b)

    def test_stale_adr_is_safe_codex_correction_without_owner_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(Path(temporary))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            prd_path.write_text(
                bind_technology_adr(prd_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            (project / "docs/adr/0001-runtime.md").write_text(
                accepted_runtime_adr(design_revision="DES-0000"), encoding="utf-8"
            )
            refresh_document_summaries(project)

            report = doctor.inspect_project(project)
            self.assertFalse(report["ok"])
            self.assertIn("ADR_RATIONALE_STALE", codes(report))
            self.assertEqual(report["gates"]["gate_b"], "APPROVED_FOR_CONSTRUCTION")
            self.assertEqual(
                report["remediation"]["next_action"]["action_kind"],
                "CORRECT_AND_REVALIDATE",
            )
            self.assertFalse(report["interaction"]["turn_boundary_required"])

    def test_prd_adr_link_is_not_auto_corrected_after_gate_b(self) -> None:
        diagnostic = doctor.Diagnostic(
            "ADR_RATIONALE_UNSAFE",
            "unsafe canonical link",
            doctor.PRD_FILE,
        )
        self.assertFalse(
            doctor._agent_correction_is_safe(
                diagnostic,
                "DELIVER",
                "APPROVED_FOR_CONSTRUCTION",
                {},
                doctor.TaskSummary(),
            )
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
                "The system records the approved result.",
                "UBIQUITOUS",
                measurable,
            ),
            "clause order": (
                "The system SHALL record the approved result.",
                "EVENT_DRIVEN",
                measurable,
            ),
            "requirement subject": (
                "The thing SHALL record the approved result.",
                "UBIQUITOUS",
                measurable,
            ),
            "requirement is unresolved": (
                "TODO",
                "UBIQUITOUS",
                measurable,
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
        self.assertTrue(
            any("QAS-001: Response measure is unresolved" in issue for issue in issues)
        )

    def test_fastlane_ears_migration_is_complete_and_grandfathers_only_current_gate_a(
        self,
    ) -> None:
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

        partial = (
            legacy
            + """
| ID | Requirement | EARS form | Acceptance criteria | Acceptance form |
|---|---|---|---|---|
| FR-002 | The worker SHALL preserve the approved result. | UBIQUITOUS | A bounded test confirms every approved result is preserved. | MEASURABLE |
"""
        )
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
                any(
                    "FR-001: requirement is unresolved" in message
                    for message in messages
                ),
                messages,
            )

    def test_gate_a_rejects_unselected_region_and_unreconciled_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self.copy_project(Path(temp_dir))
            self.approve_project(project, gate_b=False)
            prd_path = project / "docs/project/PRD.md"
            approved = prd_path.read_text(encoding="utf-8")
            unresolved_region = set_table_value(
                approved,
                "## 1. Workload profile",
                "### Owner decisions and sources",
                "Primary Region",
                "`TODO — owner has not selected a Region`",
            )
            prd_path.write_text(unresolved_region, encoding="utf-8")
            self.assertIn(
                "GATE_A_READINESS_CARD", codes(doctor.inspect_project(project))
            )
            blocker = replace_fixture_table(
                approved,
                "### Findings",
                "ID || Type || Requirements involved || Finding || Resolution or decision || Blocking? || Status",
                "RA-001 || Ambiguity || FR-001 || Owner Region is unresolved || Request owner selection || Yes || Open",
            )
            prd_path.write_text(blocker, encoding="utf-8")
            self.assertIn("GATE_A_BLOCKER", codes(doctor.inspect_project(project)))

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
        self.assertEqual(len(ready.technology_decisions), 15)
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
        self.assertFalse(doctor.valid_property_execution_command("Run property tests"))

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
            complete.replace(
                "| TECH-0007 | PROPERTY_TESTING | Hypothesis |",
                "| TECH-0007 | PROPERTY_TESTING | Hypothesis 7 |",
                1,
            ),
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
                complete.replace(
                    technology_row, technology_row + "\n" + technology_row, 1
                ),
                "Duplicate technology decision ID",
            ),
            "unresolved cell": (
                complete.replace(
                    "| TECH-0007 | PROPERTY_TESTING | Hypothesis |",
                    "| TECH-0007 | PROPERTY_TESTING | TODO |",
                    1,
                ),
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
                    "Generated boundary cases protect the approved invariant",
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
                complete.replace(
                    property_row, property_row.replace("TECH-0007", "TECH-0006"), 1
                ),
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
                contract, contract_issues = doctor.derive_design_contract(
                    text, "DES-0001"
                )
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
        no_applicable_properties = no_applicable_properties.replace(
            "| FR-001 | ARCH-0001, API-001 | PROP-001 |",
            "| FR-001 | ARCH-0001, API-001 | EX-001 |",
            1,
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

    def test_design_support_records_are_complete_and_technology_bound(self) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        template_table = doctor.contract_table_after_heading(
            template,
            doctor.AWS_SERVICE_DECISION_HEADING,
            doctor.AWS_SERVICE_DECISION_HEADERS,
        )
        self.assertIsNotNone(template_table)
        self.assertEqual(
            tuple(AWS_SERVICE_TECH_CONCERNS),
            EXPECTED_AWS_DESIGN_CONCERNS,
        )
        self.assertEqual(
            tuple(row[0] for row in template_table.rows),
            EXPECTED_AWS_DESIGN_CONCERNS,
        )
        complete = complete_design_contract(template)
        ready, ready_issues = doctor.derive_design_contract(
            complete,
            "DES-0001",
            required=True,
        )
        self.assertEqual(ready_issues, [])
        self.assertEqual(ready.status, "READY")
        support_changes = {
            "error behavior": (
                "Reject the request with a safe explanation",
                "Reject the request and explain the approved input boundary",
            ),
            "AWS rationale": (
                "Pay-per-use compute fits the bounded workload",
                "Pay-per-use compute fits the approved request volume",
            ),
            "IaC validation": (
                "sam validate, selected lint, and policy checks",
                "sam validate, selected lint, policy checks, and template review",
            ),
        }
        for label, (before, after) in support_changes.items():
            with self.subTest(support_digest=label):
                candidate = complete.replace(before, after, 1)
                self.assertNotEqual(candidate, complete)
                changed, changed_issues = doctor.derive_design_contract(
                    candidate, "DES-0001", required=True
                )
                self.assertEqual(changed_issues, [])
                self.assertEqual(changed.status, "READY")
                self.assertNotEqual(changed.canonical_sha256, ready.canonical_sha256)
                self.assertEqual(
                    changed.architecture.canonical_sha256,
                    ready.architecture.canonical_sha256,
                )
                self.assertEqual(
                    changed.project_contract.canonical_sha256,
                    ready.project_contract.canonical_sha256,
                )
                self.assertEqual(
                    changed.diagram_contract.canonical_sha256,
                    ready.diagram_contract.canonical_sha256,
                )
        approved_projection, approved_projection_issues = doctor.derive_design_contract(
            complete,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(approved_projection_issues, [])
        self.assertEqual(approved_projection.canonical_sha256, ready.canonical_sha256)
        approved_invalid, approved_invalid_issues = doctor.derive_design_contract(
            complete.replace("Reject the request with a safe explanation", "TODO", 1),
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(approved_invalid.status, "BLOCKED")
        self.assertTrue(
            any(
                "error-handling field must be concrete" in issue
                for issue in approved_invalid_issues
            ),
            approved_invalid_issues,
        )

        cases = {
            "missing required error class": (
                re.sub(
                    r"(?m)^\| Validation \|.*\r?\n",
                    "",
                    complete,
                    count=1,
                ),
                "Error class Validation must appear exactly once; found 0",
            ),
            "unbounded retry": (
                complete.replace("Bounded to 3 attempts", "Retry forever", 1),
                "retry posture is unbounded",
            ),
            "missing AWS concern": (
                re.sub(r"(?m)^\| Messaging \|.*\r?\n", "", complete, count=1),
                "AWS concern Messaging must appear exactly once; found 0",
            ),
            "duplicate AWS concern": (
                re.sub(
                    r"(?m)^(\| Messaging \|.*\r?\n)",
                    lambda match: match.group(1) * 2,
                    complete,
                    count=1,
                ),
                "AWS concern Messaging must appear exactly once; found 2",
            ),
            "unexpected AWS concern": (
                complete.replace("| Messaging |", "| Networking |", 1),
                "Unexpected AWS decision concerns: Networking",
            ),
            "unresolved AWS mechanism": (
                complete.replace(
                    "Python 3.12 on AWS Lambda; FastAPI through a Lambda adapter",
                    "TODO",
                    1,
                ),
                "Compute: AWS service or mechanism is unresolved",
            ),
            "conflicting concrete AWS mechanism": (
                complete.replace(
                    "Python 3.12 on AWS Lambda; FastAPI through a Lambda adapter",
                    "Python 3.12 on Amazon ECS; FastAPI behind an Application Load Balancer",
                    1,
                ),
                "Compute: AWS service or mechanism must exactly reproduce the controlling TECH selections",
            ),
            "unknown AWS technology decision": (
                complete.replace(
                    "| Identity | TECH-0010 |",
                    "| Identity | TECH-9999 |",
                    1,
                ),
                "AWS decision IDs are not current technology IDs: TECH-9999",
            ),
            "unrelated AWS technology decision": (
                complete.replace(
                    "| Identity | TECH-0010 |",
                    "| Identity | TECH-0011 |",
                    1,
                ),
                "AWS decision IDs must exactly match the ordered controlling decisions",
            ),
            "deployment omits recovery decision": (
                complete.replace(
                    "| Deployment | TECH-0004, TECH-0009, TECH-0015 |",
                    "| Deployment | TECH-0004, TECH-0009 |",
                    1,
                ),
                "Deployment: AWS decision IDs must exactly match the ordered controlling decisions",
            ),
            "missing material AWS evidence": (
                complete.replace(
                    "CAND-0002, ARCH-0001, TECH-0013",
                    "CAND-0002, ARCH-0001",
                    1,
                ),
                "API and edge: applicable TECH decisions lack current material AWS evidence: TECH-0013",
            ),
            "bare not applicable": (
                complete.replace(
                    "| Messaging | TECH-0012 | NOT_APPLICABLE — synchronous local request flow |",
                    "| Messaging | TECH-0012 | NOT_APPLICABLE |",
                    1,
                ),
                "Messaging: NOT_APPLICABLE requires a concrete reason",
            ),
            "unrelated IaC technology binding": (
                complete.replace(
                    "| CloudFormation / SAM / CDK | APPLICABLE | TECH-0004, TECH-0008, TECH-0009 |",
                    "| CloudFormation / SAM / CDK | APPLICABLE | TECH-0006 |",
                    1,
                ),
                "TECH binding uses unrelated concerns: TEST_TOOLING",
            ),
            "wrong IaC evidence destination": (
                complete.replace(
                    doctor.IAC_VALIDATION_EVIDENCE_DESTINATION,
                    "docs/project/VERIFY.md",
                    1,
                ),
                "Evidence destination must be exactly "
                + doctor.IAC_VALIDATION_EVIDENCE_DESTINATION,
            ),
        }
        for label, (changed, expected) in cases.items():
            with self.subTest(label=label):
                self.assertNotEqual(changed, complete, label)
                blocked, issues = doctor.derive_design_contract(
                    changed,
                    "DES-0001",
                    required=True,
                )
                self.assertEqual(blocked.status, "BLOCKED")
                self.assertIn(expected, "\n".join(issues))

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

        new_app_selected, new_app_selected_issues = doctor.derive_coverage_contract(
            selected,
            "REQ-0001",
            "quick-mvp",
            "low",
            "documentation-only",
            required=True,
            grandfather_current_gate_a=False,
            owner_work_context="NEW_APPLICATION",
        )
        self.assertEqual(new_app_selected_issues, [])
        self.assertEqual(new_app_selected.status, "READY")

        new_app_mismatch, new_app_mismatch_issues = doctor.derive_coverage_contract(
            amended,
            "REQ-0001",
            "quick-mvp",
            "low",
            "documentation-only",
            required=True,
            grandfather_current_gate_a=False,
            owner_work_context="NEW_APPLICATION",
        )
        self.assertEqual(new_app_mismatch.status, "BLOCKED")
        self.assertIn(
            "NEW_APPLICATION owner work context requires work kind NEW_BUILD",
            new_app_mismatch_issues,
        )

        unsafe_table = preserve_table.replace("SECURITY_PRIVACY, ", "", 1).replace(
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

    def test_change_impact_is_design_bound_and_falls_back_to_full_revalidation(
        self,
    ) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        template = complete_intake_foundation(template, work_context_choice="B")
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
            any(
                "PRESERVE cannot change architecture-controlled IDs" in issue
                for issue in invalid_issues
            ),
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
                self.assertTrue(
                    any(reference in item for item in plan["source_slices"])
                )
                self.assertIn("CURRENT_BLOCKER", plan["active_ids"])
                self.assertEqual(
                    len(plan["source_slices"]), len(set(plan["source_slices"]))
                )

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
            any(
                "Action authorization provenance" in item
                for item in aws_plan["source_slices"]
            )
        )
        self.assertEqual(aws_plan["active_ids"], ["TASK-0001"])

        for phase, reason in (
            ("AWS-40", "AWS_RESIDUAL_REVIEW"),
            ("AWS-50", "WAITING_AWS_TEARDOWN_AUTH"),
        ):
            with self.subTest(teardown_phase=phase):
                teardown_plan = doctor.derive_context_plan(
                    {
                        "owner_stage": "DELIVER",
                        "route_reason_code": reason,
                        "blocking_ids": [],
                    },
                    tasks,
                    coverage,
                    next_prompt=phase,
                )
                self.assertEqual(len(teardown_plan["source_slices"]), 2)
                self.assertTrue(
                    any(
                        "references/deliver.md" in item
                        for item in teardown_plan["source_slices"]
                    )
                )
                self.assertTrue(
                    any(
                        "Teardown reconciliation evidence" in item
                        for item in teardown_plan["source_slices"]
                    )
                )
                self.assertTrue(
                    any(
                        "Action authorization provenance" in item
                        for item in teardown_plan["on_demand_slices"]
                    )
                )
                self.assertTrue(
                    any(
                        "Read-only AWS preflight evidence" in item
                        for item in teardown_plan["on_demand_slices"]
                    )
                )
                self.assertTrue(
                    any(
                        "AWS deployment action" in item
                        for item in teardown_plan["on_demand_slices"]
                    )
                )

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

    def test_approved_schema_two_architecture_is_grandfathered_until_design_change(
        self,
    ) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(template)
        requirement_list = ", ".join(
            sorted(doctor.authoritative_requirement_ids(complete))
        )
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

    def test_architecture_contract_is_traceable_fail_closed_and_digest_bound(
        self,
    ) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(template)
        ready, issues = doctor.derive_design_contract(
            complete,
            "DES-0001",
            required=True,
        )

        self.assertEqual(issues, [])
        self.assertEqual(ready.status, "READY")
        self.assertEqual(ready.schema_version, 7)
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
        one_candidate = re.sub(
            r"(?m)^\| CAND-0002 \|.*\r?\n",
            "",
            complete,
            count=1,
        )
        one_candidate_contract, one_candidate_issues = doctor.derive_design_contract(
            one_candidate,
            "DES-0001",
            required=True,
        )
        self.assertEqual(one_candidate_contract.status, "BLOCKED")
        self.assertIn(
            "SELECT requires at least two complete non-straw whole-system candidates",
            one_candidate_issues,
        )

        no_viable_alternative = complete.replace(
            "Meets every hard constraint with the smallest managed surface | CAND-0002 |",
            "Meets every hard constraint with the smallest managed surface | NO_VIABLE_ALTERNATIVE |",
            1,
        )
        no_viable_contract, no_viable_issues = doctor.derive_design_contract(
            no_viable_alternative,
            "DES-0001",
            required=True,
        )
        self.assertEqual(no_viable_issues, [])
        self.assertEqual(no_viable_contract.status, "READY")

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
                    r"(?m)^\| FR-001 \| ARCH-0001, API-001 \|.*\r?\n",
                    "",
                    complete,
                    count=1,
                ),
                "Architecture traceability is missing requirement IDs: FR-001",
            ),
            "missing AWS Core capability": (
                re.sub(
                    r"(?m)^\| AWS-EV-\d+ \|.*\| search_documentation \|.*\r?\n",
                    "",
                    complete,
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
                    "CAND-0002, ARCH-0001, TECH-0013",
                    "CAND-0002, TECH-0013",
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
            any(
                "Project design contract schema 7" in issue
                for issue in invalidated_issues
            ),
            invalidated_issues,
        )

    def test_architecture_traceability_rejects_undeclared_design_ids(self) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(template)
        baseline, baseline_issues = doctor.derive_design_contract(
            complete,
            "DES-0001",
            required=True,
        )
        self.assertEqual(baseline_issues, [])
        self.assertEqual(baseline.status, "READY")

        undeclared_ids = (
            "ARCH-9999",
            "COMP-001",
            "API-999",
            "EVENT-999",
            "CLI-999",
            "FILE-999",
            "DATA-001",
            "CTRL-999",
            "BOUNDARY-999",
            "STATE-999",
        )
        trace_pattern = re.compile(
            r"(?m)^(\| FR-001 \| )ARCH-0001, API-001( \| PROP-001 \|)"
        )
        for undeclared_id in undeclared_ids:
            with self.subTest(undeclared_id=undeclared_id):
                changed, count = trace_pattern.subn(
                    lambda match: (
                        f"{match.group(1)}ARCH-0001, {undeclared_id}{match.group(2)}"
                    ),
                    complete,
                    count=1,
                )
                self.assertEqual(count, 1)
                blocked, blocked_issues = doctor.derive_design_contract(
                    changed,
                    "DES-0001",
                    required=True,
                )
                self.assertEqual(blocked.status, "BLOCKED")
                self.assertIn(
                    "FR-001: architecture traceability references undeclared "
                    f"design IDs: {undeclared_id}",
                    blocked_issues,
                )

    def test_architecture_traceability_rejects_undeclared_property_and_test_ids(
        self,
    ) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(template)
        trace_pattern = re.compile(
            r"(?m)^(\| FR-001 \| ARCH-0001, API-001 \| )PROP-001( \|)"
        )
        for undeclared_id in ("PROP-999", "EX-999", "TEST-999"):
            with self.subTest(undeclared_id=undeclared_id):
                changed, count = trace_pattern.subn(
                    lambda match: f"{match.group(1)}{undeclared_id}{match.group(2)}",
                    complete,
                    count=1,
                )
                self.assertEqual(count, 1)
                blocked, blocked_issues = doctor.derive_design_contract(
                    changed,
                    "DES-0001",
                    required=True,
                )
                self.assertEqual(blocked.status, "BLOCKED")
                self.assertIn(
                    "FR-001: architecture traceability references undeclared "
                    f"property/test IDs: {undeclared_id}",
                    blocked_issues,
                )

    def test_architecture_traceability_accepts_declared_contract_ids(self) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(template)
        design_pattern = re.compile(
            r"(?m)^(\| FR-001 \| )ARCH-0001, API-001( \| PROP-001 \|)"
        )
        test_pattern = re.compile(
            r"(?m)^(\| FR-001 \| ARCH-0001, API-001 \| )PROP-001( \|)"
        )
        cases = {
            "declared API and property": complete,
            "declared boundary": design_pattern.sub(
                lambda match: (
                    f"{match.group(1)}ARCH-0001, BOUNDARY-001{match.group(2)}"
                ),
                complete,
                count=1,
            ),
            "declared example": test_pattern.sub(
                lambda match: f"{match.group(1)}EX-001{match.group(2)}",
                complete,
                count=1,
            ),
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                ready, issues = doctor.derive_design_contract(
                    text,
                    "DES-0001",
                    required=True,
                )
                self.assertEqual(issues, [])
                self.assertEqual(ready.status, "READY")

    def test_example_scenarios_are_bound_to_the_modern_design_digest(self) -> None:
        template = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(template)
        baseline, baseline_issues = doctor.derive_design_contract(
            complete,
            "DES-0001",
            required=True,
        )
        changed_text = complete.replace(
            "Approved outcome is returned",
            "Approved outcome is returned with its current version",
            1,
        )
        changed, changed_issues = doctor.derive_design_contract(
            changed_text,
            "DES-0001",
            required=True,
        )

        self.assertEqual(baseline_issues, [])
        self.assertEqual(changed_issues, [])
        self.assertEqual(baseline.status, "READY")
        self.assertEqual(changed.status, "READY")
        self.assertNotEqual(changed.canonical_sha256, baseline.canonical_sha256)

    def test_undeclared_architecture_traceability_blocks_gate_b(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            self.approve_project(project)
            ready_report = doctor.inspect_project(project)
            self.assertTrue(ready_report["ok"], ready_report["diagnostics"])
            self.assertTrue(ready_report["write_authority"]["valid"])

            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            changed, count = re.subn(
                r"(?m)^(\| FR-001 \| )ARCH-0001, API-001( \| PROP-001 \|)",
                lambda match: f"{match.group(1)}ARCH-0001, API-999{match.group(2)}",
                text,
                count=1,
            )
            self.assertEqual(count, 1)
            prd_path.write_text(changed, encoding="utf-8")
            blocked_report = doctor.inspect_project(project)

        self.assertFalse(blocked_report["ok"])
        self.assertEqual(blocked_report["status"], "BLOCKED")
        self.assertIn("DESIGN_CONTRACT_INVALID", codes(blocked_report))
        self.assertEqual(blocked_report["design_contract"]["status"], "BLOCKED")
        self.assertEqual(blocked_report["gates"]["gate_b"], "APPROVED_FOR_CONSTRUCTION")
        self.assertFalse(blocked_report["write_authority"]["valid"])
        self.assertEqual(blocked_report["external_authority"]["kind"], "NONE")
        self.assertEqual(blocked_report["next_prompt"], "STOP")
        self.assertTrue(
            any(
                diagnostic["code"] == "DESIGN_CONTRACT_INVALID"
                and "FR-001: architecture traceability references undeclared "
                "design IDs: API-999"
                in diagnostic["message"]
                for diagnostic in blocked_report["diagnostics"]
            ),
            blocked_report["diagnostics"],
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
            self.assertEqual(contract["schema_version"], 7)
            self.assertEqual(
                ready_report["requirements_contract"]["schema_version"], "1.4"
            )
            self.assertEqual(ready_report["requirements_contract"]["status"], "READY")
            self.assertEqual(contract["project_contract"]["status"], "READY")
            self.assertEqual(
                contract["project_contract"]["first_wave"]["wave_contract_id"],
                "WAVE-001",
            )
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
            self.assertEqual(len(contract["technology_decisions"]), 15)
            self.assertEqual(
                contract["technology_decisions"][6]["concern"], "PROPERTY_TESTING"
            )
            self.assertEqual(
                contract["property_execution"][0]["framework_tech_id"], "TECH-0007"
            )
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
        receipt_digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        verify_text = set_receipt(verify_text, "aws-deployment", receipt)
        lines = verify_text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if line.startswith("| Deployment | TODO |"):
                suffix = "\n" if line.endswith("\n") else ""
                lines[index] = (
                    "| Deployment | AWS-AUTH-0001 | AUTH-0001 | "
                    "fastlane-deployment-role | sha256:"
                    + "a"
                    * 64
                    + " | TYPE: CLOUDFORMATION_CHANGE_SET; IDENTIFIER: "
                    "canary-change-set; DIGEST: sha256:"
                    + "b"
                    * 64
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

        for lane in ("fast-dev", "explicit-gate"):
            with self.subTest(lane=lane):
                projected = doctor.derive_external_authority(
                    ctx,
                    envelope,
                    lane,
                    "AUTH-0001",
                    cost_posture="MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00",
                    aws_progress_state="WAITING_AWS_MUTATION_AUTH",
                    active_artifact="sha256:" + "a" * 64,
                    aws_action_phase="AWS-20",
                    preflight=preflight,
                )
                self.assertEqual(projected["kind"], "AWS_DEPLOYMENT")
                self.assertEqual(projected["authorization_id"], "AWS-AUTH-0001")
                self.assertEqual(projected["receipt_digest"], receipt_digest)

        nonhuman_receipt = receipt.replace("Approver: alice", "Approver: Codex")
        nonhuman_digest = (
            "sha256:" + hashlib.sha256(nonhuman_receipt.encode("utf-8")).hexdigest()
        )
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
            "unbound": row.replace(
                "| sha256:" + "d" * 64 + " | NONE |", "| NONE | NONE |"
            ),
        }
        for label, invalid_row in invalid_rows.items():
            with self.subTest(label=label):
                invalid_ctx = doctor.Context(Path("."))
                invalid_ctx.texts[doctor.VERIFY_FILE] = with_rows(invalid_row)
                invalid_match = doctor.derive_request_match(invalid_ctx, authority)
                self.assertEqual(
                    invalid_match["allowed_execution_lanes"], ["STRUCTURED_API"]
                )
                self.assertIsNone(invalid_match["reviewed_script"])
                self.assertTrue(
                    any(
                        item.code == "AWS_EXECUTION_CONTRACT_INVALID"
                        for item in invalid_ctx.diagnostics
                    )
                )

        duplicate_ctx = doctor.Context(Path("."))
        duplicate_ctx.texts[doctor.VERIFY_FILE] = with_rows(row, row)
        duplicate_match = doctor.derive_request_match(duplicate_ctx, authority)
        self.assertEqual(duplicate_match["allowed_execution_lanes"], ["STRUCTURED_API"])
        self.assertIsNone(duplicate_match["reviewed_script"])

    def test_gate_b_binds_live_design_contract_hash_and_required_scope_ids(
        self,
    ) -> None:
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

    def test_gate_b_readiness_card_exactly_enumerates_current_technology_ids(
        self,
    ) -> None:
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
        self.assertIn("OWNER_BRIEF_SOURCE_MISMATCH", codes(report))
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["owner_decision_brief"]["schema_version"], 1)
        self.assertEqual(report["owner_answer_confirmation"]["schema_version"], 1)
        self.assertEqual(report["document_summaries"]["schema_version"], 1)
        self.assertEqual(report["document_summaries"]["status"], "BLOCKED")
        self.assertIn("DOCUMENT_SUMMARY_SOURCE_INVALID", codes(report))
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
        item = next(
            item
            for item in report["remediation"]["items"]
            if item["diagnostic_code"] == "PROJECT_RISK_PROFILE"
        )
        self.assertEqual(item["responsible_party"], "CODEX")
        self.assertTrue(item["automatic_correction_allowed"])
        self.assertFalse(report["interaction"]["turn_boundary_required"])

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
            text = text.replace(
                "Approver: alice\n```\n<!-- bootstrap:gate-b",
                "Approver: mallory\n```\n<!-- bootstrap:gate-b",
            )
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
            "duplicate singleton metadata": ledger
            + task.replace(
                "- Status: `READY`", "- Status: `READY`\n- Status: `READY`", 1
            ),
            "stale execution basis": ledger
            + task.replace("REQ-0001; FR-001", "REQ-9999; FR-001", 1),
            "missing objective section": ledger
            + task.replace("#### Validation", "#### Checks", 1),
            "ambiguous external target": ledger
            + task.replace("- External state: `NONE`", "- External state: `aws:*`", 1),
            "fenced heading cannot satisfy section": ledger
            + task.replace("#### Outcome", "#### Summary", 1).replace(
                "python -m unittest",
                "#### Outcome\nFake fenced heading\npython -m unittest",
                1,
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

    def test_task_property_projection_is_exact_for_every_executable_status(
        self,
    ) -> None:
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
        verify = (
            """## Task completion evidence

| Evidence ID | Task | Command or observation | Result | Actor | Observed at | Commit / worktree / artifact | Durable source | Status |
|---|---|---|---|---|---|---|---|---|
| EV-0001 | TASK-001 | python -m unittest tests.test_properties | passed | alice | 2026-07-17T12:00:00-07:00 | commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa | docs/project/VERIFY.md#ev-0001 | LOCAL_PASS |
"""
            + "\n"
            + property_test_evidence_section()
        )
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
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(ValueError, expected),
            ):
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
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(ValueError, expected),
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
            with (
                self.subTest(replay=replay),
                self.assertRaisesRegex(
                    ValueError,
                    "replay evidence does not match the approved PRD",
                ),
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
        ready = ready_task(
            requirements="REQ-0001; FR-001; PROP-001",
            design="DES-0001; TECH: TECH-0001, TECH-0007",
            command="python -m unittest tests.test_properties",
            property_projection=property_execution_projection(),
        )
        valid_verify = (
            task_completion_evidence_section() + "\n" + property_test_evidence_section()
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
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(ValueError, expected),
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
        backlog = property_task.replace("- Status: `READY`", "- Status: `BACKLOG`", 1)
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
        ).replace(
            "- Blocker: `NONE`", "- Blocker: `BLOCK-001 — dependency unavailable`", 1
        )
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

    def test_task_requirement_coverage_rejects_invalid_acceptance_traces(
        self,
    ) -> None:
        rules = {
            "FR-001": ("AC-FR-001", "UBIQUITOUS"),
            "FR-002": ("AC-FR-002", "UNWANTED_BEHAVIOR"),
        }
        cases = {
            "missing canonical acceptance": (
                "REQ-0001; FR-001",
                ("TASK-001: FR-001 requires AC-FR-001",),
            ),
            "mismatched canonical acceptance": (
                "REQ-0001; FR-001; AC-FR-002",
                (
                    "TASK-001: FR-001 requires AC-FR-001",
                    "TASK-001: AC-FR-002 requires owning requirement FR-002",
                ),
            ),
            "unknown acceptance": (
                "REQ-0001; FR-001; AC-FR-999",
                ("TASK-001: unknown acceptance IDs: AC-FR-999",),
            ),
        }
        for name, (requirements, expected_issues) in cases.items():
            with self.subTest(case=name):
                result = doctor.derive_task_requirement_coverage(
                    doctor.inspect_task_blocks(ready_task(requirements=requirements)),
                    "CURRENT",
                    rules,
                    {},
                )
                for expected_issue in expected_issues:
                    self.assertIn(expected_issue, result.trace_issues)
                self.assertIn("FR-001", result.missing_requirement_ids)

    def test_skipped_tasks_do_not_satisfy_requirement_coverage(self) -> None:
        skipped = ready_task(requirements="REQ-0001; FR-001; AC-FR-001").replace(
            "- Status: `READY`", "- Status: `SKIPPED`", 1
        )
        skipped = skipped.replace(
            "- Skip record: `NONE`",
            "- Skip record: `OWNER-DECISION-001 - superseded; evidence EV-0001`",
            1,
        )
        result = doctor.derive_task_requirement_coverage(
            doctor.inspect_task_blocks(skipped),
            "CURRENT",
            {"FR-001": ("AC-FR-001", "UBIQUITOUS")},
            {},
        )

        self.assertEqual(result.trace_issues, ())
        self.assertEqual(result.records, ())
        self.assertEqual(result.missing_requirement_ids, ("FR-001",))

    def test_task_requirement_coverage_can_be_distributed_across_tasks(
        self,
    ) -> None:
        first = ready_task(requirements="REQ-0001; FR-001; AC-FR-001")
        second = ready_task(requirements="REQ-0001; FR-002; AC-FR-002").replace(
            "TASK-001", "TASK-002"
        )
        result = doctor.derive_task_requirement_coverage(
            doctor.inspect_task_blocks(first + second),
            "CURRENT",
            {
                "FR-001": ("AC-FR-001", "UBIQUITOUS"),
                "FR-002": ("AC-FR-002", "UNWANTED_BEHAVIOR"),
            },
            {},
        )

        self.assertEqual(result.trace_issues, ())
        self.assertEqual(result.evidence_issues, ())
        self.assertEqual(result.missing_requirement_ids, ())
        by_requirement = {record.requirement_id: record for record in result.records}
        self.assertEqual(by_requirement["FR-001"].disposition, "TASK_COVERED")
        self.assertEqual(by_requirement["FR-001"].task_ids, ("TASK-001",))
        self.assertEqual(by_requirement["FR-002"].disposition, "TASK_COVERED")
        self.assertEqual(by_requirement["FR-002"].task_ids, ("TASK-002",))

    def test_current_local_pass_and_verified_no_task_evidence_satisfies_coverage(
        self,
    ) -> None:
        rules = {
            "FR-001": ("AC-FR-001", "UBIQUITOUS"),
            "FR-002": ("AC-FR-002", "UNWANTED_BEHAVIOR"),
        }
        verify = requirement_evidence_verify(
            no_task_requirement_evidence_row(
                "FR-001",
                evidence_id="EV-9001",
                status="LOCAL_PASS",
            ),
            no_task_requirement_evidence_row(
                "FR-002",
                evidence_id="EV-9002",
                status="VERIFIED",
            ),
        )
        evidence, evidence_issues = doctor.task_requirement_evidence_dispositions(
            verify,
            {
                "Requirements revision": "REQ-0001",
                "Design revision": "DES-0001",
                "Construction authorization": "AUTH-0001",
            },
            rules,
        )
        result = doctor.derive_task_requirement_coverage(
            [],
            "CURRENT",
            rules,
            evidence,
        )

        self.assertEqual(evidence_issues, ())
        self.assertEqual(
            evidence,
            {
                "FR-001": ("ALREADY_SATISFIED", ("EV-9001",)),
                "FR-002": ("ALREADY_SATISFIED", ("EV-9002",)),
            },
        )
        self.assertEqual(result.missing_requirement_ids, ())
        self.assertTrue(
            all(record.disposition == "ALREADY_SATISFIED" for record in result.records)
        )

    def test_stale_no_task_evidence_scope_does_not_satisfy_coverage(self) -> None:
        rules = {"FR-001": ("AC-FR-001", "UBIQUITOUS")}
        verify = requirement_evidence_verify(
            no_task_requirement_evidence_row(
                "FR-001",
                evidence_id="EV-9001",
                status="LOCAL_PASS",
            ),
            requirements_revision="REQ-0000",
        )
        evidence, evidence_issues = doctor.task_requirement_evidence_dispositions(
            verify,
            {
                "Requirements revision": "REQ-0001",
                "Design revision": "DES-0001",
                "Construction authorization": "AUTH-0001",
            },
            rules,
        )
        result = doctor.derive_task_requirement_coverage(
            [],
            "CURRENT",
            rules,
            evidence,
        )

        self.assertEqual(evidence, {})
        self.assertEqual(evidence_issues, ())
        self.assertEqual(result.missing_requirement_ids, ("FR-001",))

    def test_not_applicable_evidence_is_limited_to_optional_features(self) -> None:
        optional_rules = {"DATA-004": ("AC-DATA-004", "OPTIONAL_FEATURE")}
        optional_verify = requirement_evidence_verify(
            no_task_requirement_evidence_row(
                "DATA-004",
                evidence_id="EV-9001",
                status="NOT_APPLICABLE",
            )
        )
        optional, optional_issues = doctor.task_requirement_evidence_dispositions(
            optional_verify,
            {
                "Requirements revision": "REQ-0001",
                "Design revision": "DES-0001",
                "Construction authorization": "AUTH-0001",
            },
            optional_rules,
        )
        self.assertEqual(optional_issues, ())
        self.assertEqual(
            optional,
            {"DATA-004": ("NOT_APPLICABLE", ("EV-9001",))},
        )

        required_rules = {"FR-001": ("AC-FR-001", "UBIQUITOUS")}
        required_verify = requirement_evidence_verify(
            no_task_requirement_evidence_row(
                "FR-001",
                evidence_id="EV-9002",
                status="NOT_APPLICABLE",
            )
        )
        required, required_issues = doctor.task_requirement_evidence_dispositions(
            required_verify,
            {
                "Requirements revision": "REQ-0001",
                "Design revision": "DES-0001",
                "Construction authorization": "AUTH-0001",
            },
            required_rules,
        )
        required_result = doctor.derive_task_requirement_coverage(
            [],
            "CURRENT",
            required_rules,
            required,
        )
        self.assertEqual(required, {})
        self.assertIn(
            "EV-9002: NOT_APPLICABLE is allowed only for OPTIONAL_FEATURE requirements",
            required_issues,
        )
        self.assertEqual(required_result.missing_requirement_ids, ("FR-001",))

    def test_task_coverage_conflicts_with_not_applicable_evidence(self) -> None:
        result = doctor.derive_task_requirement_coverage(
            doctor.inspect_task_blocks(
                ready_task(requirements="REQ-0001; DATA-004; AC-DATA-004")
            ),
            "CURRENT",
            {"DATA-004": ("AC-DATA-004", "OPTIONAL_FEATURE")},
            {"DATA-004": ("NOT_APPLICABLE", ("EV-9001",))},
        )

        self.assertEqual(result.missing_requirement_ids, ())
        self.assertEqual(
            result.evidence_issues,
            ("DATA-004: task coverage conflicts with NOT_APPLICABLE evidence",),
        )
        self.assertEqual(result.records[0].disposition, "TASK_COVERED")

    def test_doctor_reports_requirement_coverage_and_routes_gaps_to_replan(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            self.approve_project(project)
            full_task = ready_task(
                requirements="REQ-0001; FR-001; AC-FR-001; PROP-001",
                design="DES-0001; TECH: TECH-0001, TECH-0007",
                command="python -m unittest tests.test_properties",
                property_projection=property_execution_projection(),
            )
            self.initialize_task_plan(project, full_task)
            rules = modern_task_requirement_rules()
            verify_path = project / "docs/project/VERIFY.md"
            verify_path.write_text(
                requirement_evidence_verify(
                    *(
                        no_task_requirement_evidence_row(
                            requirement_id,
                            evidence_id=f"EV-{9100 + index:04d}",
                            status="LOCAL_PASS",
                        )
                        for index, requirement_id in enumerate(
                            (item for item in rules if item != "FR-001"),
                            start=1,
                        )
                    ),
                    source=verify_path.read_text(encoding="utf-8"),
                ),
                encoding="utf-8",
            )
            refresh_control_hashes(project)
            current_report = doctor.inspect_project(project)

            tasks_path = project / "docs/project/TASKS.md"
            text = tasks_path.read_text(encoding="utf-8").replace(
                "REQ-0001; FR-001; AC-FR-001; PROP-001",
                "REQ-0001; PROP-001",
                1,
            )
            tasks_path.write_text(text, encoding="utf-8")
            blocked_report = doctor.inspect_project(project)

        self.assertTrue(current_report["ok"], current_report["diagnostics"])
        self.assertNotIn("TASK_REQUIREMENT_COVERAGE", codes(current_report))
        self.assertEqual(current_report["tasks"]["total"], 1)
        self.assertEqual(current_report["tasks"]["ready"], 1)
        self.assertEqual(current_report["tasks"]["ready_ids"], ["TASK-001"])
        self.assertTrue(current_report["tasks"]["requirement_coverage_complete"])
        self.assertEqual(current_report["tasks"]["missing_requirement_ids"], [])
        self.assertEqual(
            len(current_report["tasks"]["requirement_coverage"]),
            len(MODERN_APPROVED_REQUIREMENT_IDS),
        )

        self.assertFalse(blocked_report["ok"])
        self.assertIn("TASK_REQUIREMENT_COVERAGE", codes(blocked_report))
        self.assertFalse(blocked_report["tasks"]["requirement_coverage_complete"])
        self.assertIn("FR-001", blocked_report["tasks"]["missing_requirement_ids"])
        self.assertNotIn("FR-002", blocked_report["tasks"]["missing_requirement_ids"])
        remediation = next(
            item
            for item in blocked_report["remediation"]["items"]
            if item["diagnostic_code"] == "TASK_REQUIREMENT_COVERAGE"
        )
        self.assertEqual(remediation["responsible_party"], "CODEX")
        self.assertEqual(remediation["category"], "AGENT_REPLAN")
        self.assertTrue(remediation["automatic_correction_allowed"])

        replan_context = doctor.Context(PROJECT_ROOT)
        replan_context.error(
            "TASK_REQUIREMENT_COVERAGE",
            "CURRENT task plan does not cover approved requirement IDs: FR-001",
            doctor.TASKS_FILE,
        )
        replan = doctor.derive_remediation(
            replan_context,
            classification="ACTIVE_GREENFIELD",
            gate_a="APPROVED_FOR_DESIGN",
            gate_b="APPROVED_FOR_CONSTRUCTION",
            envelope={
                "Allowed repository write set": "PATHS: docs/project/TASKS.md",
                "Excluded or owner-only write set": "NONE",
                "Protected dirty paths": "NONE",
            },
            tasks=doctor.TaskSummary(plan_state="CURRENT"),
            requirements_revision="REQ-0001",
            design_revision="DES-0001",
            owner_stage_hint="DELIVER",
        )
        self.assertEqual(
            replan["next_action"]["action_kind"],
            "REPLAN_TASKS",
        )
        self.assertTrue(replan["next_action"]["preserve_done_evidence"])
        self.assertTrue(replan["next_action"]["automatic_continuation_allowed"])

    def test_done_requires_observed_log_and_passing_structured_local_evidence(
        self,
    ) -> None:
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
        stock_verify = (PROJECT_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        with self.assertRaisesRegex(
            ValueError, "wrong task|placeholder evidence|LOCAL_PASS"
        ):
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
        with self.assertRaisesRegex(
            ValueError, "status must be LOCAL_PASS or VERIFIED"
        ):
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

    def test_greenfield_gate_b_binds_application_source_to_singular_app(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        greenfield = doctor.ApplicationSourceDisposition(
            doctor.APPLICATION_SOURCE_GREENFIELD,
            ("app/**",),
        )
        self.assertEqual(
            doctor.validate_application_source_disposition(
                greenfield,
                project_mode="greenfield",
                work_kind="NEW_BUILD",
                prd_text=source,
            ),
            [],
        )
        doctor.validate_application_source_write_set(
            greenfield,
            ["app/**", "tests/**"],
        )
        for invalid in (
            ["app/**", "src/**", "tests/**"],
            ["apps/**", "tests/**"],
            ["src/**", "tests/**"],
        ):
            with self.subTest(paths=invalid):
                with self.assertRaisesRegex(
                    ValueError,
                    "APPLICATION_SOURCE_PARALLEL_ROOT",
                ):
                    doctor.validate_application_source_write_set(greenfield, invalid)

        infrastructure = doctor.ApplicationSourceDisposition(
            doctor.APPLICATION_SOURCE_NOT_APPLICABLE
        )
        self.assertEqual(
            doctor.validate_application_source_disposition(
                infrastructure,
                project_mode="greenfield",
                work_kind="INFRASTRUCTURE",
                prd_text=source,
            ),
            [],
        )
        doctor.validate_application_source_write_set(
            infrastructure,
            ["infrastructure/**", "tests/**"],
        )

        brownfield_text = set_table_value(
            source,
            "### 1.2 Brownfield baseline and preservation contract",
            "## Product requirements",
            "Protected files and components",
            "`service/**`",
        ).replace(
            "| PRES-001 | TODO | TODO | TODO | TODO |",
            "| PRES-001 | Preserve service/** | Baseline tests | Narrow changes only | Parallel application roots |",
            1,
        )
        brownfield = doctor.ApplicationSourceDisposition(
            doctor.APPLICATION_SOURCE_BROWNFIELD,
            ("service/**",),
        )
        self.assertEqual(
            doctor.validate_application_source_disposition(
                brownfield,
                project_mode="brownfield",
                work_kind="FEATURE",
                prd_text=brownfield_text,
            ),
            [],
        )
        doctor.validate_application_source_write_set(
            brownfield,
            ["service/**", "tests/**"],
        )
        with self.assertRaisesRegex(
            ValueError,
            "APPLICATION_SOURCE_PARALLEL_ROOT",
        ):
            doctor.validate_application_source_write_set(
                brownfield,
                ["service/**", "app/**", "tests/**"],
            )
        conflict = doctor.validate_application_source_disposition(
            brownfield,
            project_mode="brownfield",
            work_kind="FEATURE",
            prd_text=set_table_value(
                source,
                "### 1.2 Brownfield baseline and preservation contract",
                "## Product requirements",
                "Protected files and components",
                "`service/**`",
            ),
        )
        self.assertTrue(
            any("matching PRES record" in issue for issue in conflict),
            conflict,
        )
        lookalike_text = set_table_value(
            source,
            "### 1.2 Brownfield baseline and preservation contract",
            "## Product requirements",
            "Protected files and components",
            "`myservice/**`",
        ).replace(
            "| PRES-001 | TODO | TODO | TODO | TODO |",
            "| PRES-001 | Preserve myservice/** | Baseline tests | Narrow changes only | Parallel application roots |",
            1,
        )
        lookalike_conflict = doctor.validate_application_source_disposition(
            brownfield,
            project_mode="brownfield",
            work_kind="FEATURE",
            prd_text=lookalike_text,
        )
        self.assertTrue(
            any(
                "Protected files and components" in issue
                and "matching PRES record" in issue
                for issue in lookalike_conflict
            ),
            lookalike_conflict,
        )

        complete = complete_design_contract(source)
        design, issues = doctor.derive_design_contract(
            complete,
            "DES-0001",
            required=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(
            design.to_dict()["application_source_disposition"],
            {"kind": "GREENFIELD_APP_ROOT", "paths": ["app/**"]},
        )
        missing = re.sub(
            r"(?m)^\| Application source disposition \|.*\r?\n",
            "",
            complete,
            count=1,
        )
        missing_contract, missing_issues = doctor.derive_design_contract(
            missing,
            "DES-0001",
            required=True,
        )
        self.assertEqual(missing_contract.status, "BLOCKED")
        self.assertTrue(
            any(
                "APPLICATION_SOURCE_DISPOSITION_MISSING" in issue
                for issue in missing_issues
            ),
            missing_issues,
        )

        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            text = set_table_value(
                prd_path.read_text(encoding="utf-8"),
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "Allowed repository write set",
                "`PATHS: apps/**; tests/**`",
            )
            prd_path.write_text(rebind_gate_b_envelope(text), encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("APPLICATION_SOURCE_PARALLEL_ROOT", codes(report))
        self.assertTrue(
            any(
                "apps/** or src/**" in item["message"] for item in report["diagnostics"]
            ),
            report["diagnostics"],
        )

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
        passed = record_aws_core_evidence(verify_text, "DESIGN-10", binding=binding)
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
            any(
                "Advisory Design binding must reference DES-0001" in issue
                for issue in wrong_design_issues
            )
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
            any(
                "Advisory Design binding must use" in issue
                for issue in malformed_trace_issues
            )
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
            any(
                "unapproved TECH IDs: TECH-9999" in issue
                for issue in unknown_tech_issues
            )
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
        self.assertEqual(observed["chains"][0]["skill_identifier"], "aws-architecture")
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
            any(
                "retrieve timestamp precedes search" in issue
                for issue in chronology_issues
            ),
            chronology_issues,
        )

        duplicate = passed.replace(
            design_rows[0], design_rows[0] + "\n" + design_rows[0], 1
        )
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

    def test_aws_core_evidence_is_limited_to_requirements_design_and_preflight(
        self,
    ) -> None:
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

        passed = record_aws_core_evidence(verify_text, "AWS-10", binding=binding)
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
                text,
                "## Document status",
                "## 1. Workload profile",
                "AWS lane",
                "`fast-dev`",
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

    def test_fast_dev_mutation_requires_nonproduction_artifact_and_finite_validity(
        self,
    ) -> None:
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
                text,
                "## Document status",
                "## 1. Workload profile",
                "AWS lane",
                "`fast-dev`",
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
            aws_progress_state="WAITING_AWS_MUTATION_AUTH",
            active_artifact="sha256:" + "2" * 64,
            aws_action_phase="AWS-20",
            preflight=ready_preflight(
                account="123456789012", region="us-west-2", environment="dev"
            ),
        )
        self.assertEqual(fast_dev_authority["kind"], "AWS_ACTION_RECEIPT_REQUIRED")
        self.assertEqual(fast_dev_authority["validity"], "REQUIRED")
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
        self.assertNotEqual(before_preflight["kind"], "AWS_DEPLOYMENT")
        self.assertNotEqual(before_preflight["validity"], "CURRENT")

    def test_cost_posture_and_mutation_ceiling_are_canonical_and_bounded(self) -> None:
        self.assertIsNone(
            doctor.parse_cost_posture("MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED")
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
            doctor.parse_cost_posture("MINIMIZE_TOTAL_COST; HARD_CAP: ZZZ 20.00")
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

    def test_external_state_and_paths_use_case_insensitive_authorized_containment(
        self,
    ) -> None:
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
                    requirements=f"{MODERN_TASK_REQUIREMENT_TRACE}; PROP-001",
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
            self.initialize_task_plan(
                project, ready_task(external_state="aws:stack/prod")
            )

            denied_report = doctor.inspect_project(project)

        self.assertIn("TASK_EXTERNAL_STATE_BOUNDARY", codes(denied_report))

    def test_validation_commands_are_prefix_bound_and_reject_shell_control(
        self,
    ) -> None:
        for command in (
            "python setup.py",
            "python -m unittest && curl https://example.test",
        ):
            with (
                self.subTest(command=command),
                tempfile.TemporaryDirectory() as directory,
            ):
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
            "parallel workers above one": (
                "Maximum parallel workers",
                "`2`",
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
                    "--prerequisite-report-stdin",
                ],
                cwd=project,
                input=json.dumps(setup_runtime.READY_PREREQUISITE_REPORT),
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
                text = set_table_value(
                    text, "## Document status", "## 1. Workload profile", field, value
                )
            prd_path.write_text(text, encoding="utf-8")

            blocked_report = doctor.inspect_project(project)

            text = approve_gate_a(
                prd_path.read_text(encoding="utf-8"), project_mode="brownfield"
            )
            text = set_table_value(
                text,
                "## Document status",
                "## 1. Workload profile",
                "Project mode",
                "`brownfield`",
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
            doctor.derive_route(
                "STALE", "STALE", True, False, doctor.TaskSummary(), False, "NONE"
            )[1],
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
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Doctor Test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "doctor@example.test"],
                check=True,
            )
            tracked = root / "tracked.txt"
            tracked.write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-qm", "baseline"], check=True
            )
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
        self.assertIn(
            "CONSTRUCTION_WORKTREE_DRIFT",
            {item.code for item in dirty_context.diagnostics},
        )

    def test_current_gate_b_and_checkpoint_states_require_real_git_history(
        self,
    ) -> None:
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
                    "## Dependencies, waivers, and waves",
                    "Baseline commit",
                    "`ffffffffffffffffffffffffffffffffffffffff`",
                ),
                encoding="utf-8",
            )

            fabricated_report = doctor.inspect_project(project)

        self.assertIn("GATE_B_GIT_UNVERIFIED", codes(fabricated_report))
        self.assertIn("CONSTRUCTION_GIT_UNVERIFIED", codes(fabricated_report))

    def test_real_paused_checkpoint_accepts_ledger_dirt_and_rejects_code_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            maintenance_auto = subprocess.run(
                ["git", "-C", str(project), "config", "--get", "maintenance.auto"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(maintenance_auto, "false")
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
                verify_text.replace("CP-0001", "CP-9999") + "\n```text\nCP-0001\n```\n",
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
        self.assertNotIn("TASK_REQUIREMENT_COVERAGE", codes(paused_report))
        self.assertNotEqual(
            paused_report["interaction"]["route_reason_code"],
            "TASK_REPLAN_REQUIRED",
        )
        self.assertIn(
            "CONSTRUCTION_CHECKPOINT_UNVERIFIED", codes(evidence_prefix_report)
        )
        self.assertIn("CONSTRUCTION_CHECKPOINT_UNVERIFIED", codes(wrong_attempt_report))
        self.assertIn(
            "CONSTRUCTION_CHECKPOINT_UNVERIFIED", codes(missing_receipt_report)
        )
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
        self.assertEqual(len(contract.pending_card.questions), 1)
        self.assertEqual(
            contract.pending_card.questions[0].prompt,
            "What are you starting with?",
        )
        self.assertIsNone(contract.pending_card.questions[0].recommended)
        self.assertFalse(contract.pending_card.accept_all_allowed)
        self.assertEqual(
            contract.next_question_guidance.status, "STARTING_POINT_REQUIRED"
        )
        self.assertEqual(contract.next_question_guidance.target_ids, ("INTAKE-0001",))
        self.assertFalse(contract.project_configuration.owner_action_required)
        self.assertEqual(
            contract.project_configuration.safest_current_aws_lane,
            "documentation-only",
        )

    def test_intake_selection_requires_current_owner_provenance_and_detail(
        self,
    ) -> None:
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
        self.assertEqual(len(contract.basis_ids), 10)
        self.assertEqual(contract.missing_fields, ())
        self.assertIsNone(contract.pending_card)
        self.assertEqual(contract.schema_version, 2)
        self.assertEqual(
            contract.current_understanding,
            (
                "Starting point: a new application.",
                "Users and problem: Development teams — They need a clear view of approved project outcomes.",
                "First useful outcome and release: See the current approved project outcome. — Include one local outcome view; defer external integrations.",
                "Success and first audience: An invited tester can view the approved outcome without help. — Invited development testers only.",
                "Data and operating boundaries: Synthetic project names, status, and outcome summaries. — No sensitive data in the first trial. — United States users; data remains in us-west-2.",
            ),
        )
        assert response_table is not None
        assert card_table is not None
        self.assertEqual(len(response_table.rows), 10)
        self.assertEqual(
            {row[0] for row in response_table.rows},
            {f"OWNER-MSG-{index:04d}" for index in range(1, 11)},
        )
        self.assertEqual({row[0] for row in card_table.rows}, {"INTAKE-CARD-0010"})
        foundation_table = doctor.contract_table_after_heading(
            completed,
            doctor.INTAKE_FOUNDATION_HEADING,
            doctor.INTAKE_FOUNDATION_HEADERS,
        )
        assert foundation_table is not None
        historical = {row[0]: row[5] for row in foundation_table.rows}
        self.assertIn("OWNER-MSG-0001", historical["INTAKE-0001"])
        self.assertIn("OWNER-MSG-0005", historical["INTAKE-0005"])
        self.assertIn("OWNER-MSG-0006", historical["INTAKE-0006"])
        self.assertIn("OWNER-MSG-0007", historical["INTAKE-0007"])

    def test_owner_work_context_choices_map_exactly_to_semantic_values(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        expected = {
            "A": ("NEW_APPLICATION", "greenfield"),
            "B": ("EXISTING_APPLICATION_CHANGE", "brownfield"),
            "C": ("REPAIR_OR_MIGRATION", "brownfield"),
        }
        for choice, (owner_work_context, project_mode) in expected.items():
            with self.subTest(choice=choice):
                contract, issues = doctor.derive_intake_foundation_contract(
                    complete_intake_foundation(source, work_context_choice=choice),
                    "greenfield",
                    grandfather_current_gate_a=False,
                )
                self.assertEqual(issues, [])
                self.assertEqual(contract.owner_work_context, owner_work_context)
                self.assertEqual(
                    contract.project_configuration.derived_project_mode,
                    project_mode,
                )
                self.assertFalse(contract.project_configuration.owner_action_required)
                self.assertEqual(
                    contract.project_configuration.codex_actions,
                    (
                        "SET_PROJECT_MODE",
                        "CLASSIFY_EFFECTIVE_RISK",
                        "SELECT_DELIVERY_PROFILE",
                        "SET_SAFEST_CURRENT_AWS_LANE",
                    ),
                )

    def test_internal_configuration_is_not_a_valid_owner_intake_decision(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        invalid = replace_contract_table(
            source,
            doctor.INTAKE_CARD_HEADING,
            doctor.INTAKE_CARD_HEADERS,
            [
                (
                    "INTAKE-CARD-0001",
                    "1",
                    "1",
                    "INTAKE-Q-0001",
                    "DECISION",
                    "INTAKE-0001",
                    "Which project configuration should I use?",
                    "Greenfield · High-risk · Documentation-only",
                    "Greenfield · High-risk · Read-only",
                    "Greenfield · High-risk · Explicit-gate",
                    "A",
                    "NONE",
                    "NONE",
                    "PENDING",
                    "NONE",
                    "NONE",
                )
            ],
        )

        contract, issues = doctor.derive_intake_foundation_contract(
            invalid, "greenfield", grandfather_current_gate_a=False
        )

        self.assertEqual(contract.status, "BLOCKED")
        self.assertIn(
            (
                "INTAKE_CARD_INVALID",
                "INTAKE-Q-0001 asks the owner to choose Fastlane internal configuration",
            ),
            issues,
        )

    def test_product_access_language_is_not_mistaken_for_configuration(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        product_question = replace_contract_table(
            source,
            doctor.INTAKE_CARD_HEADING,
            doctor.INTAKE_CARD_HEADERS,
            [
                (
                    "INTAKE-CARD-0001",
                    "1",
                    "1",
                    "INTAKE-Q-0001",
                    "DECISION",
                    "INTAKE-0001",
                    "Which access should a standard reviewer have?",
                    "Read-only access",
                    "Comment access",
                    "Administrative access",
                    "A",
                    "NONE",
                    "NONE",
                    "PENDING",
                    "NONE",
                    "NONE",
                )
            ],
        )

        contract, issues = doctor.derive_intake_foundation_contract(
            product_question, "greenfield", grandfather_current_gate_a=False
        )

        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "FOUNDATION_REQUIRED")

    def test_resolved_card_requires_the_next_one_question_card(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        initial, issues = doctor.derive_intake_foundation_contract(
            source, "greenfield", grandfather_current_gate_a=False
        )
        self.assertEqual(issues, [])
        assert initial.pending_card is not None
        digest = initial.pending_card.canonical_sha256
        provenance = intake_provenance(
            "OWNER-MSG-0001",
            "INTAKE-CARD-0001",
            1,
            digest,
            "INTAKE-Q-0001",
            "A",
        )
        resolved = set_intake_card_resolution(
            source, "INTAKE-Q-0001", "A", owner_response=provenance
        )
        resolved = confirm_intake_foundation(
            resolved,
            {"INTAKE-0001": "NEW_APPLICATION"},
            {"INTAKE-0001": provenance},
        )
        resolved = replace_contract_table(
            resolved,
            doctor.INTAKE_RESPONSE_REGISTER_HEADING,
            doctor.INTAKE_RESPONSE_REGISTER_HEADERS,
            [
                (
                    "OWNER-MSG-0001",
                    "INTAKE-CARD-0001",
                    "1",
                    digest,
                    "1",
                    "INTAKE-Q-0001",
                    "A",
                    "NONE",
                    "INTAKE-0001",
                )
            ],
        )
        contract, issues = doctor.derive_intake_foundation_contract(
            resolved, "greenfield", grandfather_current_gate_a=False
        )
        self.assertIn("INTAKE_CARD_REQUIRED", {code for code, _ in issues})
        self.assertIsNone(contract.pending_card)
        self.assertEqual(
            contract.current_understanding,
            ("Starting point: a new application.",),
        )

        next_card = replace_contract_table(
            resolved,
            doctor.INTAKE_CARD_HEADING,
            doctor.INTAKE_CARD_HEADERS,
            [
                (
                    "INTAKE-CARD-0002",
                    "1",
                    "1",
                    "INTAKE-Q-0002",
                    "FACT",
                    "INTAKE-0002",
                    "Who will use the app?",
                    "NOT_APPLICABLE",
                    "NOT_APPLICABLE",
                    "NOT_APPLICABLE",
                    "NONE",
                    "RESPONSE",
                    "Name the primary people or teams.",
                    "PENDING",
                    "NONE",
                    "NONE",
                )
            ],
        )
        contract, issues = doctor.derive_intake_foundation_contract(
            next_card, "greenfield", grandfather_current_gate_a=False
        )
        self.assertEqual(issues, [])
        assert contract.pending_card is not None
        self.assertEqual(len(contract.pending_card.questions), 1)
        self.assertEqual(
            contract.next_question_guidance.fields,
            ("PRIMARY_USERS", "OWNER_STATED_PROBLEM", "OBSERVABLE_OUTCOME"),
        )
        self.assertEqual(
            contract.next_question_guidance.objective,
            (
                "Understand who will use the new application, what is difficult "
                "today, and the first useful result they need."
            ),
        )
        self.assertEqual(contract.next_question_guidance.basis_ids, ("INTAKE-0001",))
        parsed = doctor.parse_intake_owner_response(
            "Development teams; especially release coordinators",
            contract.pending_card.to_dict(),
            expected_card_id="INTAKE-CARD-0002",
            expected_revision=1,
            expected_sha256=contract.pending_card.canonical_sha256,
            owner_response_id="OWNER-MSG-0002",
        )
        self.assertEqual(parsed.status, "PASS", parsed.to_dict())
        self.assertEqual([answer.reply_key for answer in parsed.answers], ["1"])
        self.assertEqual(
            parsed.answers[0].detail,
            "Development teams; especially release coordinators",
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
        empty_fact = list(table.rows) + [
            (
                "OWNER-MSG-0003",
                "INTAKE-CARD-0999",
                "1",
                "sha256:" + "f" * 64,
                "1",
                "INTAKE-Q-0999",
                "RESPONSE",
                "NONE",
                "INTAKE-0001",
            )
        ]
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

    def test_intake_parser_cli_is_current_card_bound_and_zero_write(
        self,
    ) -> None:
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

            def parse(
                reply: str, *, stale: bool = False
            ) -> tuple[int, dict[str, object]]:
                current = list(command)
                if stale:
                    digest_index = current.index("--presented-card-sha256") + 1
                    current[digest_index] = "sha256:" + "f" * 64
                completed = subprocess.run(
                    current,
                    cwd=project,
                    input=reply,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=environment,
                )
                self.assertEqual(completed.stderr, "", completed.stderr)
                return completed.returncode, json.loads(completed.stdout)

            valid_exit, valid = parse("1a")
            stale_exit, stale = parse("1A", stale=True)
            duplicate_exit, duplicate = parse("1A; 1B")
            wrong_key_exit, wrong_key = parse("2: Development teams")

            self.assertEqual(valid_exit, 0)
            self.assertEqual(valid["status"], "PASS")
            self.assertEqual(valid["owner_response_id"], "OWNER-MSG-0001")
            self.assertEqual(valid["answers"][0]["selection"], "A")
            self.assertEqual(valid["unresolved_reply_keys"], [])
            self.assertEqual(stale_exit, 2)
            self.assertIn(
                "INTAKE_CARD_STALE",
                {item["code"] for item in stale["errors"]},
            )
            self.assertEqual(duplicate_exit, 2)
            self.assertIn(
                "INTAKE_REPLY_KEY_DUPLICATE",
                {item["code"] for item in duplicate["errors"]},
            )
            self.assertEqual(wrong_key_exit, 2)
            self.assertIn(
                "INTAKE_REPLY_KEY_UNKNOWN",
                {item["code"] for item in wrong_key["errors"]},
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
            current = doctor.inspect_project(project)["intake_foundation"][
                "pending_card"
            ]
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
            self.assertIn(
                "INTAKE_CARD_STALE", {item["code"] for item in result["errors"]}
            )

    def test_gate_receipt_cli_validates_same_gate_and_never_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))

            def snapshot(target: Path = project) -> dict[str, str]:
                return {
                    path.relative_to(target).as_posix(): hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                    for path in target.rglob("*")
                    if path.is_file()
                }

            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

            def validate(
                candidate: str,
                target: Path = project,
            ) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "scripts/bootstrap_doctor.py",
                        "--root",
                        str(target),
                        "--validate-gate-receipt",
                        "--input-stdin",
                        "--json",
                    ],
                    cwd=target,
                    input=candidate,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=environment,
                )
                return completed, json.loads(completed.stdout)

            gate_a = self.pending_gate_a(project)
            gate_a_baseline = snapshot()
            current_report = doctor.inspect_project(project)
            contract = doctor.current_gate_receipt_contract(project, current_report)
            prd_path = project / doctor.PRD_FILE
            current_prd = prd_path.read_text(encoding="utf-8")
            prd_path.write_text(current_prd + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pending gate contract") as raised:
                doctor.current_gate_receipt_contract(project, current_report)
            self.assertIsNotNone(raised.exception.__cause__)
            self.assertIn("snapshot changed", str(raised.exception.__cause__))
            prd_path.write_text(current_prd, encoding="utf-8")
            crlf_result = doctor.validate_gate_receipt_candidate(
                gate_a.replace("\n", "\r\n"), contract
            )
            self.assertEqual(crlf_result["status"], "PASS")
            self.assertEqual(crlf_result["normalized_receipt"], gate_a)

            # Text-mode subprocess pipes perform platform newline translation;
            # logical LF here becomes the platform representation on the wire.
            completed, result = validate("  \n" + gate_a + "\n  ")
            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["candidate_accepted"])
            self.assertEqual(result["gate"], "GATE_A")
            self.assertEqual(result["lifecycle_state"], "WAITING_GATE_A")
            self.assertEqual(result["next_prompt"], "INTAKE-20")
            self.assertEqual(result["owner_action_kind"], "APPROVE_GATE_A")
            self.assertFalse(result["project_state_changed"])
            self.assertEqual(result["normalized_receipt"], gate_a)
            self.assertEqual(snapshot(), gate_a_baseline)

            gate_a_lines = gate_a.splitlines()
            invalid_gate_a = [
                "\n".join(gate_a_lines[:-1]),
                "```text\n" + gate_a + "\n```",
                "\n".join(
                    [
                        gate_a_lines[0],
                        gate_a_lines[2],
                        gate_a_lines[1],
                        *gate_a_lines[3:],
                    ]
                ),
                gate_a.replace("REQ-0001", "REQ-9999"),
                gate_a.replace("Approver: alice", "Approver: <name/handle>"),
                gate_a.replace("Approver: alice", "Approver: Codex"),
                gate_a + "\nSecret: synthetic-private-value",
            ]
            for candidate in invalid_gate_a:
                completed, result = validate(candidate)
                self.assertEqual(completed.returncode, 2, completed.stdout)
                self.assertEqual(result["status"], "FAIL")
                self.assertFalse(result["candidate_accepted"])
                self.assertEqual(result["lifecycle_state"], "WAITING_GATE_A")
                self.assertEqual(result["next_prompt"], "INTAKE-20")
                self.assertEqual(result["owner_action_kind"], "APPROVE_GATE_A")
                self.assertFalse(result["project_state_changed"])
                self.assertNotIn("normalized_receipt", result)
                self.assertNotIn(candidate, completed.stdout)
                self.assertNotIn("synthetic-private-value", completed.stdout)
                self.assertEqual(snapshot(), gate_a_baseline)

            gate_b_parent = Path(directory) / "gate-b"
            gate_b_parent.mkdir()
            gate_b_project = self.copy_project(gate_b_parent)
            gate_b = self.pending_gate_b(gate_b_project)
            gate_b_baseline = snapshot(gate_b_project)
            completed, result = validate(gate_b, gate_b_project)
            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["candidate_accepted"])
            self.assertEqual(result["gate"], "GATE_B")
            self.assertEqual(result["lifecycle_state"], "WAITING_GATE_B")
            self.assertEqual(result["next_prompt"], "DESIGN-20")
            self.assertEqual(result["owner_action_kind"], "APPROVE_GATE_B")
            self.assertFalse(result["project_state_changed"])
            self.assertEqual(result["normalized_receipt"], gate_b)
            self.assertEqual(snapshot(gate_b_project), gate_b_baseline)

            gate_b_lines = gate_b.splitlines()
            invalid_gate_b = [
                "\n".join(gate_b_lines[:-1]),
                gate_b.replace(
                    gate_b_lines[4],
                    "Construction envelope SHA-256: sha256:" + "0" * 64,
                ),
                gate_b + "\nUnexpected: line",
            ]
            for candidate in invalid_gate_b:
                completed, result = validate(candidate, gate_b_project)
                self.assertEqual(completed.returncode, 2, completed.stdout)
                self.assertEqual(result["status"], "FAIL")
                self.assertFalse(result["candidate_accepted"])
                self.assertEqual(result["lifecycle_state"], "WAITING_GATE_B")
                self.assertEqual(result["next_prompt"], "DESIGN-20")
                self.assertEqual(result["owner_action_kind"], "APPROVE_GATE_B")
                self.assertFalse(result["project_state_changed"])
                self.assertNotIn("normalized_receipt", result)
                self.assertNotIn(candidate, completed.stdout)
                self.assertEqual(snapshot(gate_b_project), gate_b_baseline)

    def test_gate_receipt_cli_requires_a_valid_pending_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project, gate_b=False)
            refresh_control_hashes(project)
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/bootstrap_doctor.py",
                    "--root",
                    str(project),
                    "--validate-gate-receipt",
                    "--input-stdin",
                    "--json",
                ],
                cwd=project,
                input="APPROVE REQUIREMENTS GATE A",
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            result = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 1, completed.stdout)
            self.assertEqual(result["status"], "FAIL")
            self.assertFalse(result["candidate_accepted"])
            self.assertFalse(result["project_state_changed"])
            self.assertIn(
                "GATE_RECEIPT_NOT_PENDING",
                {item["code"] for item in result["errors"]},
            )

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

    def test_missing_modern_intake_record_names_the_exact_migration_target(
        self,
    ) -> None:
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

    def test_owner_input_creates_a_turn_boundary_but_automatic_work_does_not(
        self,
    ) -> None:
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

    def test_unproven_selection_is_agent_correctable_without_owner_confirmation(
        self,
    ) -> None:
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

    def test_real_cli_forwards_remediation_fingerprint_and_escalates_repeat(
        self,
    ) -> None:
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
        values = dict(bootstrap_runtime.PLACEHOLDERS)
        values.update(
            {
                "{{PROJECT_NAME}}": "Doctor Test Project",
                "{{AWS_REGION}}": "us-west-2",
                "{{COST_POSTURE}}": "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
            }
        )
        source = bootstrap_runtime.rendered_bytes(
            PROJECT_ROOT / "docs/project/PRD.md",
            values,
            relative="docs/project/PRD.md",
            render=True,
        ).decode("utf-8")
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
            with (
                self.subTest(code=expected_code),
                tempfile.TemporaryDirectory() as directory,
            ):
                project = self.copy_project(Path(directory))
                (project / "docs/project/PRD.md").write_text(prd_text, encoding="utf-8")
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
            with (
                self.subTest(missing=missing_key),
                tempfile.TemporaryDirectory() as directory,
            ):
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

    def test_complete_intake_routes_to_codex_owned_configuration_and_requirements(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            prd_path = project / "docs/project/PRD.md"
            prd_path.write_text(
                complete_intake_foundation(prd_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )

            report = doctor.inspect_project(project)

        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["next_prompt"], "REQ-10")
        self.assertEqual(report["lifecycle_state"], "REQUIREMENTS_ANALYSIS")
        self.assertEqual(
            report["interaction"]["owner_action_kind"],
            "NONE_CONTINUE_AUTOMATICALLY",
        )
        configuration = report["intake_foundation"]["project_configuration"]
        self.assertEqual(configuration["status"], "CODEX_ACTION_REQUIRED")
        self.assertFalse(configuration["owner_action_required"])
        self.assertEqual(configuration["derived_project_mode"], "greenfield")
        self.assertEqual(configuration["safest_current_aws_lane"], "documentation-only")
        self.assertEqual(
            configuration["codex_actions"],
            [
                "SET_PROJECT_MODE",
                "CLASSIFY_EFFECTIVE_RISK",
                "SELECT_DELIVERY_PROFILE",
                "SET_SAFEST_CURRENT_AWS_LANE",
            ],
        )
        self.assertEqual(
            configuration["risk_profile_basis_ids"],
            [
                "INTAKE-0005",
                "INTAKE-0007",
                "INTAKE-0008",
                "INTAKE-0009",
                "INTAKE-0010",
            ],
        )

    def test_owner_work_context_conflict_is_a_codex_owned_correction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            prd_path = project / "docs/project/PRD.md"
            text = complete_intake_foundation(
                prd_path.read_text(encoding="utf-8"), work_context_choice="B"
            )
            for field, value in {
                "Project mode": "`greenfield`",
                "Delivery profile": "`standard`",
                "Effective risk": "`moderate`",
                "AWS lane": "`documentation-only`",
            }.items():
                text = set_table_value(
                    text,
                    "## Document status",
                    "## 1. Workload profile",
                    field,
                    value,
                )
            prd_path.write_text(text, encoding="utf-8")
            state_path = project / "bootstrap.yaml"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project"].update(
                {
                    "mode": "greenfield",
                    "delivery_profile": "standard",
                    "effective_risk": "moderate",
                    "aws_lane": "documentation-only",
                    "brownfield_baseline": "NOT_APPLICABLE",
                }
            )
            state_path.write_text(json.dumps(state), encoding="utf-8")

            report = doctor.inspect_project(project)

        self.assertIn("PROJECT_CONFIGURATION_CONFLICT", codes(report))
        item = next(
            item
            for item in report["remediation"]["items"]
            if item["diagnostic_code"] == "PROJECT_CONFIGURATION_CONFLICT"
        )
        self.assertEqual(item["responsible_party"], "CODEX")
        self.assertEqual(item["category"], "AGENT_CORRECTION")
        self.assertTrue(item["automatic_correction_allowed"])
        self.assertFalse(report["interaction"]["turn_boundary_required"])

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
        self.assertEqual(contract.schema_version, "1.4")
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
            "| Project contract schema | `1.4` |",
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
            ("Project contract schema 1.4",),
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

    def test_requirements_lineage_and_assumption_lifecycle_fail_closed(
        self,
    ) -> None:
        source = approve_gate_a(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        intake, intake_issues = doctor.derive_intake_foundation_contract(
            source,
            "greenfield",
            grandfather_current_gate_a=False,
        )
        self.assertEqual(intake_issues, [])

        invalid_lineage = source.replace(
            "| REQ-0001 | NONE | INITIAL_DEFINITION |",
            "| REQ-0001 | REQ-0001 | INITIAL_DEFINITION |",
            1,
        )
        blocked, issues = doctor.derive_requirements_contract(
            invalid_lineage,
            "low",
            intake,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertIn(
            "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
            {code for code, _message in issues},
        )

        invalid_assumption = replace_contract_table(
            source,
            doctor.ASSUMPTION_LIFECYCLE_HEADING,
            doctor.ASSUMPTION_LIFECYCLE_HEADERS,
            [
                (
                    "ASM-001",
                    "The development user can access the approved outcome",
                    "DRAFT",
                    "FR-001",
                    "PENDING_OWNER_DECISION",
                )
            ],
        )
        blocked, issues = doctor.derive_requirements_contract(
            invalid_assumption,
            "low",
            intake,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(blocked.status, "BLOCKED")
        self.assertIn(
            "ASSUMPTION_LIFECYCLE_INVALID",
            {code for code, _message in issues},
        )

    def test_approved_schema_13_is_grandfathered_until_requirements_change(
        self,
    ) -> None:
        source = approve_gate_a(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        intake, intake_issues = doctor.derive_intake_foundation_contract(
            source,
            "greenfield",
            grandfather_current_gate_a=False,
        )
        self.assertEqual(intake_issues, [])
        legacy = source.replace(
            "| Project contract schema | `1.4` |",
            "| Project contract schema | `1.3` |",
            1,
        )
        start = legacy.index(doctor.REQUIREMENTS_CHANGE_LINEAGE_HEADING)
        end = legacy.index("### Open decisions", start)
        legacy = legacy[:start] + legacy[end:]

        grandfathered, issues = doctor.derive_requirements_contract(
            legacy,
            "low",
            intake,
            required=True,
            grandfather_current_gate_a=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(grandfathered.status, "GRANDFATHERED")
        self.assertEqual(grandfathered.schema_version, "1.3")
        self.assertTrue(grandfathered.grandfathered_approved_gate_a)

        migration, migration_issues = doctor.derive_requirements_contract(
            legacy,
            "low",
            intake,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(migration.status, "MIGRATION_REQUIRED")
        self.assertIn(
            "PROJECT_CONTRACT_MIGRATION_REQUIRED",
            {code for code, _message in migration_issues},
        )

    def test_schema_13_requires_inverse_actor_and_journey_coverage(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        text = approve_gate_a(source)
        intake_contract, intake_issues = doctor.derive_intake_foundation_contract(
            text,
            "greenfield",
            grandfather_current_gate_a=False,
        )
        self.assertEqual(intake_issues, [])
        actors = doctor.contract_table_after_heading(
            text,
            doctor.ACTOR_HEADING,
            doctor.ACTOR_HEADERS,
        )
        journeys = doctor.contract_table_after_heading(
            text,
            doctor.JOURNEY_HEADING,
            doctor.JOURNEY_HEADERS,
        )
        self.assertIsNotNone(actors)
        self.assertIsNotNone(journeys)
        assert actors is not None
        assert journeys is not None

        actor_candidate = replace_contract_table(
            text,
            doctor.ACTOR_HEADING,
            doctor.ACTOR_HEADERS,
            [
                *actors.rows,
                (
                    "ACT-002",
                    "Development observer",
                    "SECONDARY_USER",
                    "Observe the approved local outcome",
                    "May read only synthetic development output",
                    "INTAKE-0002, INTAKE-0003, INTAKE-0004, INTAKE-0005, INTAKE-0007",
                ),
            ],
        )
        actor_contract, actor_issues = doctor.derive_requirements_contract(
            actor_candidate,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(actor_contract.status, "BLOCKED")
        self.assertTrue(
            any(
                code == "ACTOR_CONTRACT_INVALID" and "uncovered=ACT-002" in message
                for code, message in actor_issues
            ),
            actor_issues,
        )

        invalid_kind = replace_contract_table(
            text,
            doctor.ACTOR_HEADING,
            doctor.ACTOR_HEADERS,
            [actors.rows[0][:2] + ("CUSTOMER",) + actors.rows[0][3:]],
        )
        invalid_kind_contract, invalid_kind_issues = (
            doctor.derive_requirements_contract(
                invalid_kind,
                "low",
                intake_contract,
                required=True,
                grandfather_current_gate_a=False,
            )
        )
        self.assertEqual(invalid_kind_contract.status, "BLOCKED")
        self.assertTrue(
            any(
                code == "ACTOR_CONTRACT_INVALID"
                and "invalid actor kind 'CUSTOMER'" in message
                for code, message in invalid_kind_issues
            ),
            invalid_kind_issues,
        )

        requirement_list = ", ".join(sorted(doctor.authoritative_requirement_ids(text)))
        journey_candidate = replace_contract_table(
            text,
            doctor.JOURNEY_HEADING,
            doctor.JOURNEY_HEADERS,
            [
                *journeys.rows,
                (
                    "JOURNEY-002",
                    "ACT-001",
                    "Review the approved local outcome",
                    "The development user requests a review",
                    "The current approved outcome is reviewed",
                    "Invalid input is rejected without changing approved state",
                    requirement_list,
                    "NONE",
                ),
            ],
        )
        journey_contract, journey_issues = doctor.derive_requirements_contract(
            journey_candidate,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(journey_contract.status, "BLOCKED")
        self.assertTrue(
            any(
                code == "JOURNEY_CONTRACT_INVALID"
                and "uncovered=JOURNEY-002" in message
                for code, message in journey_issues
            ),
            journey_issues,
        )

    def test_schema_13_rich_use_cases_cover_each_risk_or_triggered_journey(
        self,
    ) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        base = approve_gate_a(source)
        intake_contract, intake_issues = doctor.derive_intake_foundation_contract(
            base,
            "greenfield",
            grandfather_current_gate_a=False,
        )
        self.assertEqual(intake_issues, [])
        coverage = doctor.contract_table_after_heading(
            base,
            doctor.REQUIREMENT_COVERAGE_HEADING,
            doctor.REQUIREMENT_COVERAGE_HEADERS,
        )
        self.assertIsNotNone(coverage)
        assert coverage is not None
        requirement_list = ", ".join(sorted(doctor.authoritative_requirement_ids(base)))

        def rich_fixture(second_trigger: str) -> str:
            candidate = replace_contract_table(
                base,
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
                        "CONFIDENTIAL_OR_REGULATED_MUTATION",
                    ),
                    (
                        "JOURNEY-002",
                        "ACT-001",
                        "Review the approved project outcome",
                        "The development user requests a review",
                        "The current approved outcome is reviewed",
                        "Invalid input is rejected without changing approved state",
                        requirement_list,
                        second_trigger,
                    ),
                ],
            )
            candidate = replace_contract_table(
                candidate,
                doctor.REQUIREMENT_COVERAGE_HEADING,
                doctor.REQUIREMENT_COVERAGE_HEADERS,
                [
                    row[:3] + ("JOURNEY-001, JOURNEY-002",) + row[4:]
                    for row in coverage.rows
                ],
            )
            candidate = replace_contract_table(
                candidate,
                doctor.RICH_USE_CASE_APPLICABILITY_HEADING,
                doctor.RICH_USE_CASE_APPLICABILITY_HEADERS,
                [
                    (
                        "REQUIRED",
                        "CONFIDENTIAL_OR_REGULATED_MUTATION",
                        "USECASE-001",
                    )
                ],
            )
            candidate = replace_contract_table(
                candidate,
                doctor.RICH_USE_CASE_HEADING,
                doctor.RICH_USE_CASE_HEADERS,
                [
                    (
                        "USECASE-001",
                        "JOURNEY-001",
                        "ACT-001",
                        "The development user needs private, correct output",
                        "The user has an approved local request",
                        "The approved outcome is displayed",
                        "Failure preserves approved state and exposes no confidential content",
                        "BR-001",
                        "FR-001",
                    )
                ],
            )
            return replace_contract_table(
                candidate,
                doctor.BUSINESS_RULE_HEADING,
                doctor.BUSINESS_RULE_HEADERS,
                [
                    (
                        "BR-001",
                        "Only the approved local outcome may be displayed",
                        "FR-001",
                        "JOURNEY-001, USECASE-001",
                        "AC-FR-001",
                    )
                ],
            )

        triggered_only = rich_fixture("NONE")
        low_contract, low_issues = doctor.derive_requirements_contract(
            triggered_only,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(low_issues, [])
        self.assertEqual(low_contract.status, "READY")
        self.assertEqual(low_contract.use_case_ids, ("USECASE-001",))

        high_contract, high_issues = doctor.derive_requirements_contract(
            triggered_only,
            "high",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(high_contract.status, "BLOCKED")
        self.assertTrue(
            any(
                code == "RICH_USE_CASE_REQUIRED" and "missing=JOURNEY-002" in message
                for code, message in high_issues
            ),
            high_issues,
        )

        both_triggered = rich_fixture("PARTIAL_FAILURE")
        triggered_contract, triggered_issues = doctor.derive_requirements_contract(
            both_triggered,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(triggered_contract.status, "BLOCKED")
        self.assertTrue(
            any(
                code == "RICH_USE_CASE_REQUIRED" and "missing=JOURNEY-002" in message
                for code, message in triggered_issues
            ),
            triggered_issues,
        )

    def test_schema_13_acceptance_test_bindings_are_exact_and_requirement_local(
        self,
    ) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        base = approve_gate_a(source)
        intake_contract, intake_issues = doctor.derive_intake_foundation_contract(
            base,
            "greenfield",
            grandfather_current_gate_a=False,
        )
        self.assertEqual(intake_issues, [])
        functionals = doctor.contract_table_after_heading(
            base,
            "### Functional requirements",
            doctor.NORMATIVE_REQUIREMENT_HEADERS,
        )
        coverage = doctor.contract_table_after_heading(
            base,
            doctor.REQUIREMENT_COVERAGE_HEADING,
            doctor.REQUIREMENT_COVERAGE_HEADERS,
        )
        self.assertIsNotNone(functionals)
        self.assertIsNotNone(coverage)
        assert functionals is not None
        assert coverage is not None

        functional_rows: list[tuple[str, ...]] = []
        for row in functionals.rows:
            cells = list(row)
            if cells[0] == "FR-001":
                cells[4] += " TEST-001 records this exact observation."
            elif cells[0] == "FR-002":
                cells[4] += " TEST-002 records this exact observation."
            functional_rows.append(tuple(cells))
        valid = replace_contract_table(
            base,
            "### Functional requirements",
            doctor.NORMATIVE_REQUIREMENT_HEADERS,
            functional_rows,
        )
        valid_coverage_rows = [
            row[:4]
            + (
                (
                    f"{row[4]}, TEST-001"
                    if row[0] == "FR-001"
                    else f"{row[4]}, TEST-002"
                    if row[0] == "FR-002"
                    else row[4]
                ),
            )
            + row[5:]
            for row in coverage.rows
        ]
        valid = replace_contract_table(
            valid,
            doctor.REQUIREMENT_COVERAGE_HEADING,
            doctor.REQUIREMENT_COVERAGE_HEADERS,
            valid_coverage_rows,
        )
        valid_contract, valid_issues = doctor.derive_requirements_contract(
            valid,
            "low",
            intake_contract,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(valid_issues, [])
        self.assertEqual(valid_contract.status, "READY")

        def with_fr1_coverage(value: str) -> str:
            return replace_contract_table(
                valid,
                doctor.REQUIREMENT_COVERAGE_HEADING,
                doctor.REQUIREMENT_COVERAGE_HEADERS,
                [
                    row[:4] + (value,) + row[5:] if row[0] == "FR-001" else row
                    for row in valid_coverage_rows
                ],
            )

        for label, acceptance_test_ids in {
            "missing explicit binding": "AC-FR-001",
            "invented test binding": "AC-FR-001, TEST-999",
            "cross-bound test binding": "AC-FR-001, TEST-002",
        }.items():
            with self.subTest(label=label):
                contract, issues = doctor.derive_requirements_contract(
                    with_fr1_coverage(acceptance_test_ids),
                    "low",
                    intake_contract,
                    required=True,
                    grandfather_current_gate_a=False,
                )
                self.assertEqual(contract.status, "BLOCKED")
                self.assertTrue(
                    any(
                        code == "REQUIREMENT_COVERAGE_INVALID"
                        and "FR-001: Acceptance/test IDs must exactly match" in message
                        and "expected=AC-FR-001,TEST-001" in message
                        for code, message in issues
                    ),
                    issues,
                )

        for label, acceptance_id in {
            "cross-bound acceptance": "AC-FR-002",
            "invented acceptance": "AC-FR-999",
        }.items():
            with self.subTest(label=label):
                wrong_rows = [
                    row[:3] + (acceptance_id,) + row[4:] if row[0] == "FR-001" else row
                    for row in functional_rows
                ]
                candidate = replace_contract_table(
                    valid,
                    "### Functional requirements",
                    doctor.NORMATIVE_REQUIREMENT_HEADERS,
                    wrong_rows,
                )
                contract, issues = doctor.derive_requirements_contract(
                    candidate,
                    "low",
                    intake_contract,
                    required=True,
                    grandfather_current_gate_a=False,
                )
                self.assertEqual(contract.status, "BLOCKED")
                self.assertTrue(
                    any(
                        code == "REQUIREMENT_COVERAGE_INVALID"
                        and "FR-001: Acceptance ID must be exactly AC-FR-001" in message
                        for code, message in issues
                    ),
                    issues,
                )

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

    def test_approved_schema_five_design_is_grandfathered_without_diagrams(
        self,
    ) -> None:
        source = complete_design_contract(
            approve_gate_a(
                (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
            )
        )
        legacy = source.replace(
            "| Project design contract schema | `7` |",
            "| Project design contract schema | `5` |",
            1,
        )
        start = legacy.index(doctor.DIAGRAM_CONTRACT_HEADING)
        end = legacy.index("## 14. Architecture overview", start)
        legacy = legacy[:start] + legacy[end:]

        grandfathered, issues = doctor.derive_design_contract(
            legacy,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(grandfathered.status, "READY")
        self.assertEqual(grandfathered.schema_version, 5)
        self.assertTrue(grandfathered.project_contract.grandfathered_v5)
        self.assertTrue(grandfathered.diagram_contract.grandfathered_schema5)

        migration, migration_issues = doctor.derive_design_contract(
            legacy,
            "DES-0001",
            required=True,
            grandfather_approved_v1=False,
        )
        self.assertEqual(migration.status, "BLOCKED")
        self.assertEqual(migration.project_contract.status, "MIGRATION_REQUIRED")
        self.assertTrue(migration_issues)
        design_path = ".agents/skills/fastlane/references/design.md"
        patterns_path = ".agents/skills/fastlane/references/diagram-patterns.md"
        migration_plan = doctor.derive_context_plan(
            {
                "owner_stage": "DESIGN",
                "route_reason_code": "DESIGN_REQUIRED",
                "blocking_ids": [],
            },
            doctor.TaskSummary(),
            doctor.CoverageContract(status="READY", work_kind="NEW_BUILD"),
            next_prompt="DESIGN-10",
            source_texts={
                doctor.PRD_FILE: legacy,
                doctor.VERIFY_FILE: (PROJECT_ROOT / doctor.VERIFY_FILE).read_text(
                    encoding="utf-8"
                ),
                design_path: (PROJECT_ROOT / design_path).read_text(encoding="utf-8"),
                patterns_path: (PROJECT_ROOT / patterns_path).read_text(
                    encoding="utf-8"
                ),
            },
            design_contract=migration,
            diagram_remediation_required=True,
        )
        self.assertEqual(migration_plan["budget_status"], "WITHIN_LIMIT")
        self.assertEqual(migration_plan.get("resolution_issues", []), [])
        self.assertIn(patterns_path, migration_plan["on_demand_slices"])
        self.assertNotIn(
            f"{doctor.PRD_FILE}#Project diagram contract",
            migration_plan["on_demand_slices"],
        )

    def test_approved_schema_six_design_is_grandfathered_without_source_disposition(
        self,
    ) -> None:
        source = complete_design_contract(
            approve_gate_a(
                (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
            )
        )
        legacy = schema_six_design_projection(source)
        grandfathered, issues = doctor.derive_design_contract(
            legacy,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(grandfathered.status, "READY")
        self.assertEqual(grandfathered.schema_version, 6)
        self.assertTrue(grandfathered.project_contract.grandfathered_v6)
        self.assertFalse(grandfathered.diagram_contract.grandfathered_schema5)
        self.assertIsNotNone(grandfathered.diagram_contract.canonical_sha256)
        self.assertIsNotNone(grandfathered.canonical_sha256)
        self.assertIsNone(grandfathered.project_contract.application_source_disposition)

        migration, migration_issues = doctor.derive_design_contract(
            legacy,
            "DES-0001",
            required=True,
            grandfather_approved_v1=False,
        )
        self.assertEqual(migration.status, "BLOCKED")
        self.assertEqual(migration.project_contract.status, "MIGRATION_REQUIRED")
        self.assertTrue(migration_issues)

    def test_genuine_1234_design_keeps_exact_schema_seven_and_six_digests(
        self,
    ) -> None:
        # Frozen from 66bcf1de via its historical complete_design_contract(approve_gate_a(PRD)).
        fixture = PROJECT_ROOT / "tests/fixtures/legacy_1234_pre_aws_prd.md"
        source_bytes = fixture.read_bytes()
        self.assertEqual(
            hashlib.sha256(source_bytes).hexdigest(),
            "d7a86f7a7ea0128b8b8a3ed95dab4b9e4567de242a211adec3d47d426ec53016",
        )
        source = source_bytes.decode("utf-8")
        schema_seven, issues = doctor.derive_design_contract(
            source,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(schema_seven.status, "READY")
        self.assertEqual(schema_seven.schema_version, 7)
        self.assertEqual(
            schema_seven.diagram_contract.canonical_sha256,
            "sha256:ce8b2dfed3fb6cb3967244bfe2f11265c440e1ae03c2bb92b0ede1966cc5d9d8",
        )
        self.assertEqual(
            schema_seven.canonical_sha256,
            "sha256:9e925fbaf47a328ab9ea327d6d7f1058d9945154d8ecabe27384a9115bf23cbc",
        )

        schema_six_source = source.replace(
            "| Project design contract schema | `7` |",
            "| Project design contract schema | `6` |",
            1,
        )
        schema_six_source = re.sub(
            r"(?m)^\| Application source disposition \|.*\r?\n",
            "",
            schema_six_source,
            count=1,
        )
        self.assertNotEqual(schema_six_source, source)
        schema_six, issues = doctor.derive_design_contract(
            schema_six_source,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(schema_six.status, "READY")
        self.assertEqual(schema_six.schema_version, 6)
        self.assertEqual(
            schema_six.diagram_contract.canonical_sha256,
            "sha256:ce8b2dfed3fb6cb3967244bfe2f11265c440e1ae03c2bb92b0ede1966cc5d9d8",
        )
        self.assertEqual(
            schema_six.canonical_sha256,
            "sha256:edae7e371e9cb8408d3954207c810b9027ad8577ecf028f3f09e540d32dffcf1",
        )

    def test_genuine_schema_six_approved_design_keeps_its_historical_digest(
        self,
    ) -> None:
        # Frozen from a7222753 via its historical approve_gate_b(approve_gate_a(PRD)).
        fixture = PROJECT_ROOT / "tests/fixtures/legacy_schema6_approved_prd.md"
        source_bytes = fixture.read_bytes()
        self.assertEqual(
            hashlib.sha256(source_bytes).hexdigest(),
            "a19d24c797c8bb1c2c12034ae061b4cf9100f6f0e7fdf61afb41e9e344d90138",
        )
        contract, issues = doctor.derive_design_contract(
            source_bytes.decode("utf-8"),
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )

        self.assertEqual(issues, [])
        self.assertEqual(contract.status, "READY")
        self.assertEqual(contract.schema_version, 6)
        self.assertEqual(
            contract.diagram_contract.canonical_sha256,
            "sha256:ce8b2dfed3fb6cb3967244bfe2f11265c440e1ae03c2bb92b0ede1966cc5d9d8",
        )
        self.assertEqual(
            contract.canonical_sha256,
            "sha256:7a912283b2f0dfd5270ef00cf5dfcff174bd657b45eed359fa16b8cbc1ac4680",
        )

        false_claim = source_bytes.decode("utf-8").replace(
            'ARCH-0001["Managed application"]',
            'ARCH-0001["Deployment live in AWS"]',
            1,
        )
        self.assertNotEqual(false_claim, source_bytes.decode("utf-8"))
        drifted, drift_issues = doctor.derive_design_contract(
            false_claim,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(drifted.status, "READY")
        self.assertEqual(drifted.canonical_sha256, contract.canonical_sha256)
        self.assertEqual(
            drifted.diagram_contract.canonical_sha256,
            contract.diagram_contract.canonical_sha256,
        )
        self.assertEqual(len(drift_issues), 1)
        self.assertIn("DIAGRAM_PRESENTATION_STALE", drift_issues[0])
        self.assertIn("must not claim", drift_issues[0])

        unquoted_claim = source_bytes.decode("utf-8").replace(
            'ARCH-0001["Managed application"]',
            "ARCH-0001[Deployment live in AWS]",
            1,
        )
        unquoted, unquoted_issues = doctor.derive_design_contract(
            unquoted_claim,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(unquoted.status, "READY")
        self.assertEqual(unquoted.canonical_sha256, contract.canonical_sha256)
        self.assertEqual(len(unquoted_issues), 1)
        self.assertIn("DIAGRAM_PRESENTATION_STALE", unquoted_issues[0])

        dotted_claim = source_bytes.decode("utf-8").replace(
            "    ARCH-0001 -->|serves| API-001",
            "    ARCH-0001 -. Deployment live in AWS .-> API-001\n"
            "    ARCH-0001 -->|serves| API-001",
            1,
        )
        dotted, dotted_issues = doctor.derive_design_contract(
            dotted_claim,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(dotted.status, "READY")
        self.assertEqual(dotted.canonical_sha256, contract.canonical_sha256)
        self.assertEqual(len(dotted_issues), 1)
        self.assertIn("DIAGRAM_PRESENTATION_STALE", dotted_issues[0])

        benign_unquoted = source_bytes.decode("utf-8").replace(
            'API-001["Approved interface"]',
            "API-001[Successful outcome]",
            1,
        )
        benign, benign_issues = doctor.derive_design_contract(
            benign_unquoted,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(benign.status, "READY")
        self.assertEqual(benign.canonical_sha256, contract.canonical_sha256)
        self.assertEqual(benign_issues, [])

        encoded_claim = source_bytes.decode("utf-8").replace(
            'ARCH-0001["Managed application"]',
            'ARCH-0001["Deployment l&#105;ve in AWS"]',
            1,
        )
        encoded, encoded_issues = doctor.derive_design_contract(
            encoded_claim,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(encoded.status, "READY")
        self.assertEqual(encoded.canonical_sha256, contract.canonical_sha256)
        self.assertEqual(len(encoded_issues), 1)
        self.assertIn("DIAGRAM_PRESENTATION_STALE", encoded_issues[0])

        for unsafe_statement in (
            'click ARCH-0001 "javascript:alert(1)"',
            'click ARCH-0001 "https://example.invalid/collect"',
            '%%{init: {"securityLevel": "loose"}}%%',
            "classDef unsafe fill:url(https://example.invalid/pixel);",
            'ARCH-0001["Managed application<img src=x>"]',
        ):
            with self.subTest(unsafe_statement=unsafe_statement):
                unsafe_source = source_bytes.decode("utf-8").replace(
                    "    ARCH-0001 -->|serves| API-001",
                    f"    {unsafe_statement}\n    ARCH-0001 -->|serves| API-001",
                    1,
                )
                unsafe, unsafe_issues = doctor.derive_design_contract(
                    unsafe_source,
                    "DES-0001",
                    required=True,
                    grandfather_approved_v1=True,
                )
                self.assertEqual(unsafe.status, "READY")
                self.assertEqual(unsafe.canonical_sha256, contract.canonical_sha256)
                self.assertEqual(len(unsafe_issues), 1)
                self.assertIn("DIAGRAM_PRESENTATION_STALE", unsafe_issues[0])
                self.assertIn("active directives", unsafe_issues[0])

    def test_approved_schema_six_gate_b_keeps_its_design_digest_current(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)
            self.approve_project(project)
            prd_path = project / "docs/project/PRD.md"
            legacy = schema_six_design_projection(prd_path.read_text(encoding="utf-8"))
            legacy = rebind_gate_b_envelope(legacy, grandfather_approved_v1=True)
            prd_path.write_text(legacy, encoding="utf-8")
            refresh_document_summaries(project)
            report = doctor.inspect_project(project)
            false_claim = legacy.replace(
                'ARCH-0001["Managed Serverless Baseline"]:::compute',
                'ARCH-0001["Deployment live in AWS"]:::compute',
                1,
            )
            self.assertNotEqual(false_claim, legacy)
            prd_path.write_text(false_claim, encoding="utf-8")
            refresh_document_summaries(project)
            drifted = doctor.inspect_project(project)

        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["gates"]["gate_b"], "APPROVED_FOR_CONSTRUCTION")
        self.assertEqual(report["design_contract"]["status"], "READY")
        self.assertIsNotNone(report["design_contract"]["canonical_sha256"])
        self.assertNotIn("GATE_B_DESIGN_CONTRACT_HASH", codes(report))
        self.assertFalse(drifted["ok"])
        self.assertEqual(drifted["gates"]["gate_b"], "APPROVED_FOR_CONSTRUCTION")
        self.assertEqual(drifted["design_contract"]["status"], "READY")
        self.assertEqual(
            drifted["design_contract"]["canonical_sha256"],
            report["design_contract"]["canonical_sha256"],
        )
        self.assertEqual(codes(drifted), {"DIAGRAM_PRESENTATION_STALE"})
        self.assertNotIn("GATE_B_DESIGN_CONTRACT_HASH", codes(drifted))
        self.assertEqual(
            drifted["authorizations"], {"construction": "NONE", "aws": "NONE"}
        )
        self.assertEqual(
            (drifted["lifecycle_state"], drifted["next_prompt"]),
            ("BLOCKED", "STOP"),
        )
        self.assertEqual(drifted["context_plan"]["budget_status"], "WITHIN_LIMIT")
        self.assertEqual(drifted["context_plan"].get("resolution_issues", []), [])
        self.assertIn(
            f"{doctor.PRD_FILE}#Proposed system at a glance",
            drifted["context_plan"]["on_demand_slices"],
        )
        self.assertNotIn(
            f"{doctor.PRD_FILE}#AWS implementation at a glance",
            drifted["context_plan"]["on_demand_slices"],
        )
        item = drifted["remediation"]["items"][0]
        self.assertEqual(item["responsible_party"], "CODEX")
        self.assertEqual(item["category"], "AGENT_CORRECTION")
        self.assertEqual(
            drifted["remediation"]["next_action"]["action_kind"],
            "CORRECT_AND_REVALIDATE",
        )

    def test_diagram_semantics_and_rendering_are_bound_separately(self) -> None:
        def system_context(contract):
            records = contract.diagram_contract.records
            return {row.diagram_id: row for row in records}["DIAGRAM-0001"]

        source = complete_design_contract(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        source = set_table_value(
            source,
            "## 1. Workload profile",
            "### Owner decisions and sources",
            "Primary Region",
            "`us-west-2`",
        )
        baseline, baseline_issues = doctor.derive_design_contract(
            source,
            "DES-0001",
            required=True,
        )
        self.assertEqual(baseline_issues, [])
        baseline_record = system_context(baseline)

        relabeled, relabeled_issues = doctor.derive_design_contract(
            source.replace(
                "Managed Serverless Baseline",
                "Managed Serverless<br/>Baseline",
                1,
            ),
            "DES-0001",
            required=True,
        )
        self.assertEqual(relabeled_issues, [])
        relabeled_record = system_context(relabeled)
        self.assertEqual(baseline.canonical_sha256, relabeled.canonical_sha256)
        self.assertEqual(
            baseline_record.semantic_sha256,
            relabeled_record.semantic_sha256,
        )
        self.assertNotEqual(
            baseline_record.rendered_sha256,
            relabeled_record.rendered_sha256,
        )

        wrapped_relation, wrapped_issues = doctor.derive_design_contract(
            source.replace(
                "ACT-001 -->|sends a review request through| TECH-0013",
                "ACT-001 -->|sends a review<br/>request through| TECH-0013",
                1,
            ),
            "DES-0001",
            required=True,
        )
        self.assertEqual(wrapped_issues, [])
        wrapped_record = system_context(wrapped_relation)
        self.assertEqual(baseline.canonical_sha256, wrapped_relation.canonical_sha256)
        self.assertEqual(
            baseline_record.semantic_sha256,
            wrapped_record.semantic_sha256,
        )
        self.assertNotEqual(
            baseline_record.rendered_sha256,
            wrapped_record.rendered_sha256,
        )

        overwrapped, overwrapped_issues = doctor.derive_design_contract(
            source.replace(
                "ACT-001 -->|sends a review request through| TECH-0013",
                "ACT-001 -->|sends a<br/>review request<br/>through| TECH-0013",
                1,
            ),
            "DES-0001",
            required=True,
        )
        self.assertEqual(overwrapped.status, "READY")
        self.assertTrue(overwrapped_issues)
        self.assertTrue(
            all(
                issue.startswith("DIAGRAM_PRESENTATION_STALE: ")
                for issue in overwrapped_issues
            ),
            overwrapped_issues,
        )
        overwrapped_record = system_context(overwrapped)
        self.assertEqual(baseline.canonical_sha256, overwrapped.canonical_sha256)
        self.assertEqual(
            baseline_record.semantic_sha256,
            overwrapped_record.semantic_sha256,
        )
        self.assertNotEqual(
            baseline_record.rendered_sha256,
            overwrapped_record.rendered_sha256,
        )

        region_drifted, region_issues = doctor.derive_design_contract(
            source.replace(
                "AWS Region · us-west-2",
                "AWS Region · us-east-1",
            ),
            "DES-0001",
            required=True,
        )
        self.assertEqual(region_drifted.status, "READY")
        self.assertTrue(
            region_issues
            and all(
                issue.startswith("DIAGRAM_PRESENTATION_STALE: ")
                for issue in region_issues
            ),
            region_issues,
        )
        self.assertEqual(baseline.canonical_sha256, region_drifted.canonical_sha256)
        region_record = system_context(region_drifted)
        self.assertEqual(baseline_record.semantic_sha256, region_record.semantic_sha256)
        self.assertNotEqual(
            baseline_record.rendered_sha256, region_record.rendered_sha256
        )
        for width, has_issue in ((48, False), (49, True)):
            node = f'TECH-0001["{"x" * width}"]'
            self.assertEqual(
                bool(design_diagrams._mermaid_node_line_issues("D", [node])), has_issue
            )

        stateful_source = replace_contract_table(
            source,
            doctor.STATE_APPLICABILITY_HEADING,
            doctor.STATE_APPLICABILITY_HEADERS,
            [("RESOURCE-001", "APPLICABLE", "LIFECYCLE_RESOURCE: FR-001", "STATE-001")],
        )
        stateful_source = replace_contract_table(
            stateful_source,
            doctor.STATE_REGISTER_HEADING,
            doctor.STATE_REGISTER_HEADERS,
            [
                (
                    "STATE-001",
                    "RESOURCE-001",
                    "PENDING, READY",
                    "PENDING",
                    "PENDING to READY",
                    "READY",
                    "Reject invalid transitions",
                    "FR-001",
                    "AC-FR-001",
                )
            ],
        )
        restyled_state_source = complete_state_diagrams(stateful_source)
        released_state_source = set_diagram_block(
            restyled_state_source,
            "### State view",
            "### Data lifecycle view",
            """```mermaid
flowchart LR
    accTitle: Review lifecycle state
    accDescr: The selected application points to one canonical review-state model and names its exact recorded transition.
    ARCH-0001["Managed Serverless Baseline"]
    STATE-001["PENDING, READY"]
    ARCH-0001 -->|permits PENDING to READY| STATE-001
```""",
        )
        released_state, released_state_issues = doctor.derive_design_contract(
            released_state_source,
            "DES-0001",
            required=True,
        )
        restyled_state, restyled_state_issues = doctor.derive_design_contract(
            restyled_state_source,
            "DES-0001",
            required=True,
        )
        self.assertEqual(released_state_issues, [])
        self.assertEqual(restyled_state_issues, [])
        self.assertEqual(released_state.status, "READY")
        self.assertEqual(
            released_state.canonical_sha256, restyled_state.canonical_sha256
        )
        released_state_record = next(
            record
            for record in released_state.diagram_contract.records
            if record.diagram_id == "DIAGRAM-0007"
        )
        restyled_state_record = next(
            record
            for record in restyled_state.diagram_contract.records
            if record.diagram_id == "DIAGRAM-0007"
        )
        self.assertEqual(
            released_state_record.semantic_sha256,
            restyled_state_record.semantic_sha256,
        )
        self.assertNotEqual(
            released_state_record.rendered_sha256,
            restyled_state_record.rendered_sha256,
        )
        table = doctor.contract_table_after_heading(
            restyled_state_source,
            doctor.DIAGRAM_CONTRACT_HEADING,
            doctor.DIAGRAM_CONTRACT_HEADERS,
        )
        self.assertIsNotNone(table)
        legacy_rows = [list(row) for row in table.rows]
        for row in legacy_rows:
            if row[1] == "STATE":
                row[6] = "STATE-001"
        self_loop_state_source = replace_contract_table(
            restyled_state_source,
            doctor.DIAGRAM_CONTRACT_HEADING,
            doctor.DIAGRAM_CONTRACT_HEADERS,
            [tuple(row) for row in legacy_rows],
        )
        self_loop_state_source = set_diagram_block(
            self_loop_state_source,
            "### State view",
            "### Data lifecycle view",
            """```mermaid
flowchart TB
    accTitle: Review lifecycle state
    accDescr: The legacy presentation incorrectly shows the whole review-state model as a transition back to itself.
    STATE-001["PENDING,<br/>READY"]:::event
    STATE-001 -->|loops back to itself| STATE-001
    classDef event fill:#F3ECFF,stroke:#8C4FFF,color:#232F3E;
```""",
        )
        self_loop_state, self_loop_issues = doctor.derive_design_contract(
            self_loop_state_source,
            "DES-0001",
            required=True,
        )
        self.assertEqual(self_loop_state.status, "READY")
        self.assertTrue(self_loop_state_issues := self_loop_issues)
        self.assertTrue(
            all(
                issue.startswith("DIAGRAM_PRESENTATION_STALE: ")
                for issue in self_loop_state_issues
            ),
            self_loop_state_issues,
        )
        self.assertTrue(
            any(
                "STATE must not contain self-loop STATE-001" in issue
                for issue in self_loop_issues
            ),
            self_loop_issues,
        )
        self_loop_record = next(
            record
            for record in self_loop_state.diagram_contract.records
            if record.diagram_id == "DIAGRAM-0007"
        )
        self.assertNotEqual(
            self_loop_record.semantic_sha256,
            restyled_state_record.semantic_sha256,
        )

        presentation_variants = (
            source.replace('subgraph PEOPLE["People"]', "subgraph PEOPLE", 1),
            source.replace(
                'ACT-001["Development user"]:::actor',
                "ACT-001[Development user]:::actor",
                1,
            ),
        )
        for candidate in presentation_variants:
            self.assertNotEqual(candidate, source)
            presented, presentation_issues = doctor.derive_design_contract(
                candidate,
                "DES-0001",
                required=True,
            )
            self.assertEqual(presented.status, "READY")
            self.assertTrue(presentation_issues)
            self.assertTrue(
                all(
                    issue.startswith("DIAGRAM_PRESENTATION_STALE: ")
                    for issue in presentation_issues
                ),
                presentation_issues,
            )
            presented_record = next(
                record
                for record in presented.diagram_contract.records
                if record.diagram_id == "DIAGRAM-0001"
            )
            self.assertEqual(baseline.canonical_sha256, presented.canonical_sha256)
            self.assertEqual(
                baseline_record.semantic_sha256,
                presented_record.semantic_sha256,
            )
            self.assertNotEqual(
                baseline_record.rendered_sha256,
                presented_record.rendered_sha256,
            )

        long_relationship = source.replace(
            "ACT-001 -->|sends a review request through| TECH-0013",
            "ACT-001 -->|sends one deliberately overlong owner request through the selected public entry service for processing| TECH-0013",
            1,
        )
        self.assertNotEqual(long_relationship, source)
        long_contract, long_issues = doctor.derive_design_contract(
            long_relationship,
            "DES-0001",
            required=True,
        )
        self.assertEqual(long_contract.status, "BLOCKED")
        self.assertTrue(
            any("relationship label exceeds 72" in issue for issue in long_issues),
            long_issues,
        )

        semantic, semantic_issues = doctor.derive_design_contract(
            source.replace("-->|implements|", "-->|routes through|", 1),
            "DES-0001",
            required=True,
        )
        self.assertEqual(semantic_issues, [])
        self.assertNotEqual(baseline.canonical_sha256, semantic.canonical_sha256)
        self.assertNotEqual(
            baseline.diagram_contract.canonical_sha256,
            semantic.diagram_contract.canonical_sha256,
        )

        moved_data = source.replace(
            '                TECH-0011[("Amazon DynamoDB with<br/>per-owner records")]:::data\n',
            "",
            1,
        ).replace(
            '                TECH-0010["Amazon Cognito with<br/>server-side authorization"]:::entry\n',
            '                TECH-0010["Amazon Cognito with<br/>server-side authorization"]:::entry\n'
            '                TECH-0011[("Amazon DynamoDB with<br/>per-owner records")]:::data\n',
            1,
        )
        self.assertNotEqual(moved_data, source)
        regrouped, regrouped_issues = doctor.derive_design_contract(
            moved_data,
            "DES-0001",
            required=True,
        )
        self.assertEqual(regrouped_issues, [])
        self.assertNotEqual(
            baseline.diagram_contract.canonical_sha256,
            regrouped.diagram_contract.canonical_sha256,
        )
        self.assertNotEqual(baseline.canonical_sha256, regrouped.canonical_sha256)

        edge_kind, edge_kind_issues = doctor.derive_design_contract(
            source.replace(
                "TECH-0013 -->|routes authenticated requests to| TECH-0002",
                'TECH-0013 -. "routes authenticated requests to" .-> TECH-0002',
                1,
            ),
            "DES-0001",
            required=True,
        )
        self.assertEqual(edge_kind_issues, [])
        baseline_aws = next(
            record
            for record in baseline.diagram_contract.records
            if record.kind == "AWS_IMPLEMENTATION"
        )
        changed_aws = next(
            record
            for record in edge_kind.diagram_contract.records
            if record.kind == "AWS_IMPLEMENTATION"
        )
        self.assertNotEqual(baseline_aws.semantic_sha256, changed_aws.semantic_sha256)
        self.assertNotEqual(baseline.canonical_sha256, edge_kind.canonical_sha256)

        diagram_table = doctor.contract_table_after_heading(
            source, doctor.DIAGRAM_CONTRACT_HEADING, doctor.DIAGRAM_CONTRACT_HEADERS
        )
        self.assertIsNotNone(diagram_table)
        reordered_source = replace_contract_table(
            source,
            doctor.DIAGRAM_CONTRACT_HEADING,
            doctor.DIAGRAM_CONTRACT_HEADERS,
            list(reversed(diagram_table.rows)),
        )
        reordered, reordered_issues = doctor.derive_design_contract(
            reordered_source, "DES-0001", required=True
        )
        self.assertEqual(reordered_issues, [])
        self.assertEqual(
            baseline.diagram_contract.canonical_sha256,
            reordered.diagram_contract.canonical_sha256,
        )
        self.assertEqual(baseline.canonical_sha256, reordered.canonical_sha256)

    def test_golden_diagram_edges_are_independently_authored_and_exact(self) -> None:
        source = complete_design_contract(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        expected = {
            "SYSTEM_CONTEXT": frozenset(
                {
                    ("ACT-001", "SOLID", "TECH-0013"),
                    ("TECH-0010", "DASHED", "TECH-0013"),
                    ("TECH-0013", "SOLID", "BOUNDARY-001"),
                    ("BOUNDARY-001", "SOLID", "API-001"),
                    ("API-001", "SOLID", "TECH-0002"),
                    ("TECH-0002", "SOLID", "TECH-0001"),
                    ("TECH-0001", "SOLID", "ARCH-0001"),
                    ("ARCH-0001", "SOLID", "TECH-0011"),
                    ("TECH-0008", "DASHED", "ARCH-0001"),
                    ("ARCH-0001", "DASHED", "TECH-0014"),
                    ("TECH-0004", "DASHED", "TECH-0009"),
                    ("TECH-0009", "DASHED", "TECH-0001"),
                    ("TECH-0015", "DASHED", "TECH-0001"),
                }
            ),
            "AWS_IMPLEMENTATION": frozenset(
                {
                    ("TECH-0010", "DASHED", "TECH-0013"),
                    ("TECH-0013", "SOLID", "TECH-0002"),
                    ("TECH-0002", "SOLID", "TECH-0001"),
                    ("TECH-0001", "SOLID", "ARCH-0001"),
                    ("ARCH-0001", "SOLID", "TECH-0011"),
                    ("TECH-0008", "DASHED", "ARCH-0001"),
                    ("ARCH-0001", "DASHED", "TECH-0014"),
                    ("TECH-0004", "DASHED", "TECH-0009"),
                    ("TECH-0009", "DASHED", "TECH-0001"),
                    ("TECH-0015", "DASHED", "TECH-0001"),
                }
            ),
            "PRIMARY_OUTCOME": frozenset(
                {
                    ("ACT-001", "SOLID", "API-001"),
                    ("API-001", "SOLID", "ACT-001"),
                }
            ),
            "DATA_LIFECYCLE": frozenset({("API-001", "SOLID", "TECH-0011")}),
            "FAILURE_RECOVERY": frozenset({("API-001", "SOLID", "TECH-0015")}),
        }
        primary_heading = next(
            line
            for line in source.splitlines()
            if line.startswith("### Sequence") and "primary outcome" in line
        )
        failure_heading = next(
            line
            for line in source.splitlines()
            if line.startswith("### Sequence") and "failure and recovery" in line
        )
        sections = {
            "SYSTEM_CONTEXT": ("### Proposed system at a glance", "## 15."),
            "AWS_IMPLEMENTATION": (
                "### AWS implementation at a glance",
                "<details>",
            ),
            "PRIMARY_OUTCOME": (primary_heading, failure_heading),
            "DATA_LIFECYCLE": ("### Data lifecycle view", "## 18."),
            "FAILURE_RECOVERY": (failure_heading, "## 19."),
        }
        solid = re.compile(
            r"^\s*([A-Z][A-Z0-9_]*-\d{3,})\s*-->\|[^|]+\|\s*"
            r"([A-Z][A-Z0-9_]*-\d{3,})\s*$"
        )
        dashed = re.compile(
            r'^\s*([A-Z][A-Z0-9_]*-\d{3,})\s*-\.\s*"[^"]+"\s*\.->\s*'
            r"([A-Z][A-Z0-9_]*-\d{3,})\s*$"
        )

        def independently_observed_edges(
            candidate: str, heading: str, next_marker: str
        ) -> frozenset[tuple[str, str, str]]:
            start = candidate.index(heading) + len(heading)
            end = candidate.index(next_marker, start)
            section = candidate[start:end]
            fence_start = section.index("```mermaid")
            fence_end = section.index("```", fence_start + len("```mermaid"))
            lines = section[fence_start:fence_end].splitlines()
            observed: set[tuple[str, str, str]] = set()
            edge_lines = 0
            for line in lines:
                match = solid.fullmatch(line)
                if match is not None:
                    edge_lines += 1
                    observed.add((match.group(1), "SOLID", match.group(2)))
                    continue
                match = dashed.fullmatch(line)
                if match is not None:
                    edge_lines += 1
                    observed.add((match.group(1), "DASHED", match.group(2)))
            self.assertEqual(edge_lines, len(observed))
            return frozenset(observed)

        for kind, (heading, next_marker) in sections.items():
            with self.subTest(kind=kind):
                self.assertEqual(
                    independently_observed_edges(source, heading, next_marker),
                    expected[kind],
                )

        reversed_cases = (
            (
                "AWS_IMPLEMENTATION",
                "TECH-0013 -->|routes authenticated requests to| TECH-0002",
                "TECH-0002 -->|routes authenticated requests to| TECH-0013",
            ),
            (
                "DATA_LIFECYCLE",
                "API-001 -->|validates and stores in| TECH-0011",
                "TECH-0011 -->|validates and stores in| API-001",
            ),
            (
                "FAILURE_RECOVERY",
                "API-001 -->|fails safely and invokes| TECH-0015",
                "TECH-0015 -->|fails safely and invokes| API-001",
            ),
            (
                "AWS_IMPLEMENTATION",
                'TECH-0010 -. "provides token issuer trust to" .-> TECH-0013',
                'TECH-0013 -. "provides token issuer trust to" .-> TECH-0010',
            ),
            (
                "AWS_IMPLEMENTATION",
                'ARCH-0001 -. "emits signals to" .-> TECH-0014',
                'TECH-0014 -. "emits signals to" .-> ARCH-0001',
            ),
            (
                "AWS_IMPLEMENTATION",
                'TECH-0009 -. "deploys" .-> TECH-0001',
                'TECH-0001 -. "deploys" .-> TECH-0009',
            ),
            (
                "AWS_IMPLEMENTATION",
                "ARCH-0001 -->|reads and writes| TECH-0011",
                "TECH-0011 -->|reads and writes| ARCH-0001",
            ),
            (
                "AWS_IMPLEMENTATION",
                'TECH-0015 -. "restores" .-> TECH-0001',
                'TECH-0001 -. "restores" .-> TECH-0015',
            ),
        )
        for kind, current, reversed_edge in reversed_cases:
            heading, next_marker = sections[kind]
            section_start = source.index(heading)
            candidate = source[:section_start] + source[section_start:].replace(
                current, reversed_edge, 1
            )
            self.assertNotEqual(
                independently_observed_edges(candidate, heading, next_marker),
                expected[kind],
            )

    def test_moving_unchanged_diagram_preserves_approved_gate_b(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            self.set_non_material_req_evidence(project)
            refresh_control_hashes(project)
            baseline = doctor.inspect_project(project)
            self.assertTrue(baseline["ok"], baseline["diagnostics"])
            self.assertEqual(baseline["gates"]["gate_b"], "APPROVED_FOR_CONSTRUCTION")
            baseline_records = {
                item["kind"]: item
                for item in baseline["design_contract"]["diagram_contract"]["records"]
            }

            prd_path = project / "docs/project/PRD.md"
            source = prd_path.read_text(encoding="utf-8")
            baseline_locator = doctor._owner_locator_for_heading(
                source,
                key="system-context",
                label="System context",
                heading="Proposed system at a glance",
            )
            start = source.index("### Proposed system at a glance")
            end = source.index("## 15. Component design", start)
            section = source[start:end]
            without_section = source[:start] + source[end:]
            architecture_section = "## 14. Architecture overview\n\n"
            insertion = without_section.index(architecture_section) + len(
                architecture_section
            )
            moved = (
                without_section[:insertion]
                + section.rstrip()
                + "\n\n"
                + without_section[insertion:]
            )
            moved_locator = doctor._owner_locator_for_heading(
                moved,
                key="system-context",
                label="System context",
                heading="Proposed system at a glance",
            )
            self.assertNotEqual(
                baseline_locator["start_line"], moved_locator["start_line"]
            )
            self.assertNotEqual(
                baseline_locator["section_sha256"], moved_locator["section_sha256"]
            )
            prd_path.write_text(moved, encoding="utf-8")
            refresh_control_hashes(project)
            relocated = doctor.inspect_project(project)

        self.assertTrue(relocated["ok"], relocated["diagnostics"])
        self.assertEqual(relocated["gates"], baseline["gates"])
        self.assertEqual(relocated["next_prompt"], baseline["next_prompt"])
        self.assertEqual(
            relocated["design_contract"]["canonical_sha256"],
            baseline["design_contract"]["canonical_sha256"],
        )
        self.assertEqual(
            relocated["design_contract"]["diagram_contract"],
            baseline["design_contract"]["diagram_contract"],
        )
        relocated_records = {
            item["kind"]: item
            for item in relocated["design_contract"]["diagram_contract"]["records"]
        }
        for kind in ("SYSTEM_CONTEXT", "PRIMARY_OUTCOME", "AWS_IMPLEMENTATION"):
            self.assertEqual(
                relocated_records[kind]["semantic_sha256"],
                baseline_records[kind]["semantic_sha256"],
            )
            self.assertEqual(
                relocated_records[kind]["rendered_sha256"],
                baseline_records[kind]["rendered_sha256"],
            )
        selected = "\n".join(
            moved.splitlines()[
                moved_locator["start_line"] - 1 : moved_locator["end_line"]
            ]
        )
        self.assertTrue(selected.startswith("### Proposed system at a glance"))
        self.assertNotIn("<details>", selected)
        self.assertEqual(moved_locator["heading"], "Proposed system at a glance")

    def test_label_only_diagram_polish_preserves_approved_gate_b(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            self.set_non_material_req_evidence(project)
            refresh_control_hashes(project)
            baseline = doctor.inspect_project(project)
            self.assertTrue(baseline["ok"], baseline["diagnostics"])
            baseline_record = next(
                item
                for item in baseline["design_contract"]["diagram_contract"]["records"]
                if item["kind"] == "SYSTEM_CONTEXT"
            )

            prd_path = project / "docs/project/PRD.md"
            source = prd_path.read_text(encoding="utf-8")
            relabeled_source = source.replace(
                'ARCH-0001["Managed Serverless Baseline"]:::compute',
                'ARCH-0001["Managed Serverless<br/>Baseline"]:::compute',
                1,
            )
            self.assertNotEqual(relabeled_source, source)
            prd_path.write_text(relabeled_source, encoding="utf-8")
            refresh_control_hashes(project)
            relabeled = doctor.inspect_project(project)
            locator = doctor._owner_locator_for_heading(
                relabeled_source,
                key="complete-architecture-diagram",
                label="Complete architecture",
                heading="Proposed system at a glance",
            )
            mislabeled_source = source.replace(
                'TECH-0013["Amazon API Gateway<br/>regional HTTPS endpoint"]:::entry',
                'TECH-0013["Unrelated edge service"]:::entry',
                1,
            )
            self.assertNotEqual(mislabeled_source, source)
            prd_path.write_text(mislabeled_source, encoding="utf-8")
            refresh_control_hashes(project)
            mislabeled = doctor.inspect_project(project)
            decorative_source = source.replace(
                'subgraph PEOPLE["People"]',
                'subgraph PEOPLE["People"]\n'
                '        EXTRA-999["Decorative legend node"]:::actor',
                1,
            )
            self.assertNotEqual(decorative_source, source)
            prd_path.write_text(decorative_source, encoding="utf-8")
            refresh_control_hashes(project)
            decorative = doctor.inspect_project(project)
            contained_actor_source = source.replace(
                '    subgraph PEOPLE["People"]\n'
                '        ACT-001["Development user"]:::actor\n'
                "    end\n"
                '    subgraph AWS_CLOUD["AWS Cloud · proposed architecture"]',
                '    subgraph AWS_CLOUD["AWS Cloud · proposed architecture"]\n'
                '        ACT-001["Development user"]:::actor',
                1,
            )
            self.assertNotEqual(contained_actor_source, source)
            prd_path.write_text(contained_actor_source, encoding="utf-8")
            refresh_control_hashes(project)
            contained_actor = doctor.inspect_project(project)

        self.assertTrue(relabeled["ok"], relabeled["diagnostics"])
        self.assertEqual(relabeled["gates"], baseline["gates"])
        self.assertEqual(
            relabeled["design_contract"]["canonical_sha256"],
            baseline["design_contract"]["canonical_sha256"],
        )
        relabeled_record = next(
            item
            for item in relabeled["design_contract"]["diagram_contract"]["records"]
            if item["kind"] == "SYSTEM_CONTEXT"
        )
        self.assertEqual(
            relabeled_record["semantic_sha256"],
            baseline_record["semantic_sha256"],
        )
        self.assertNotEqual(
            relabeled_record["rendered_sha256"],
            baseline_record["rendered_sha256"],
        )
        self.assertEqual(locator["heading"], "Proposed system at a glance")
        self.assertTrue(locator["section_sha256"].startswith("sha256:"))
        self.assertFalse(mislabeled["ok"])
        self.assertEqual(mislabeled["gates"], baseline["gates"])
        self.assertEqual(
            mislabeled["design_contract"]["canonical_sha256"],
            baseline["design_contract"]["canonical_sha256"],
        )
        mislabeled_codes = codes(mislabeled)
        self.assertIn("DIAGRAM_PRESENTATION_STALE", mislabeled_codes)
        self.assertNotIn("GATE_B_DESIGN_CONTRACT_HASH", mislabeled_codes)
        repair = next(
            item
            for item in mislabeled["remediation"]["items"]
            if item["diagnostic_code"] == "DIAGRAM_PRESENTATION_STALE"
        )
        self.assertEqual(repair["responsible_party"], "CODEX")
        self.assertTrue(repair["automatic_correction_allowed"])
        self.assertIn(
            ".agents/skills/fastlane/references/diagram-patterns.md",
            mislabeled["context_plan"]["on_demand_slices"],
        )
        self.assertIn(
            f"{doctor.PRD_FILE}#Project diagram contract",
            mislabeled["context_plan"]["on_demand_slices"],
        )
        self.assertIn(
            f"{doctor.PRD_FILE}#Proposed system at a glance",
            mislabeled["context_plan"]["on_demand_slices"],
        )
        resolved_diagram = next(
            item
            for item in mislabeled["context_plan"]["resolved_on_demand_slices"]
            if item["path"] == doctor.PRD_FILE
            and item["selector"] == "Proposed system at a glance"
        )
        selected_diagram = "\n".join(
            mislabeled_source.splitlines()[
                resolved_diagram["start_line"] - 1 : resolved_diagram["end_line"]
            ]
        )
        self.assertIn("Unrelated edge service", selected_diagram)
        self.assertFalse(decorative["ok"])
        self.assertEqual(decorative["gates"], baseline["gates"])
        self.assertEqual(
            decorative["design_contract"]["canonical_sha256"],
            baseline["design_contract"]["canonical_sha256"],
        )
        decorative_record = next(
            item
            for item in decorative["design_contract"]["diagram_contract"]["records"]
            if item["kind"] == "SYSTEM_CONTEXT"
        )
        self.assertEqual(
            decorative_record["semantic_sha256"],
            baseline_record["semantic_sha256"],
        )
        self.assertNotEqual(
            decorative_record["rendered_sha256"],
            baseline_record["rendered_sha256"],
        )
        self.assertIn("DIAGRAM_PRESENTATION_STALE", codes(decorative))
        self.assertNotIn("GATE_B_DESIGN_CONTRACT_HASH", codes(decorative))
        contained_codes = codes(contained_actor)
        self.assertFalse(contained_actor["ok"])
        self.assertIn("DESIGN_CONTRACT_INVALID", contained_codes)
        self.assertIn("GATE_B_DESIGN_CONTRACT_HASH", contained_codes)
        self.assertNotIn("DIAGRAM_PRESENTATION_STALE", contained_codes)

    def test_false_diagram_claim_cannot_reach_the_gate_b_owner_brief(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.pending_gate_b(project)
            baseline = doctor.inspect_project(project)
            prd_path = project / "docs/project/PRD.md"
            source = prd_path.read_text(encoding="utf-8")
            changed = source.replace(
                "The project owner submits one review request and receives the validated result through the review API.",
                "Proposed system is live in AWS.",
                1,
            )
            self.assertNotEqual(changed, source)
            prd_path.write_text(changed, encoding="utf-8")
            refresh_document_summaries(project)
            observed = doctor.inspect_project(project)
            reverse_changed = source.replace(
                "The project owner submits one review request and receives the validated result through the review API.",
                "Successful planned deployment.",
                1,
            )
            self.assertNotEqual(reverse_changed, source)
            prd_path.write_text(reverse_changed, encoding="utf-8")
            refresh_document_summaries(project)
            reverse_observed = doctor.inspect_project(project)
            encoded_changed = source.replace(
                "The project owner submits one review request and receives the validated result through the review API.",
                "Proposed deployment l&#105;ve in AWS.",
                1,
            )
            self.assertNotEqual(encoded_changed, source)
            prd_path.write_text(encoded_changed, encoding="utf-8")
            refresh_document_summaries(project)
            encoded_observed = doctor.inspect_project(project)
            future_plan = source.replace(
                "The project owner submits one review request and receives the validated result through the review API.",
                "Deployment will be validated before release.",
                1,
            )
            self.assertNotEqual(future_plan, source)
            prd_path.write_text(future_plan, encoding="utf-8")
            refresh_document_summaries(project)
            future_observed = doctor.inspect_project(project)

        self.assertFalse(observed["ok"])
        self.assertEqual(observed["gates"], baseline["gates"])
        self.assertEqual(observed["design_contract"]["status"], "READY")
        self.assertEqual(
            observed["design_contract"]["canonical_sha256"],
            baseline["design_contract"]["canonical_sha256"],
        )
        self.assertIn("DIAGRAM_PRESENTATION_STALE", codes(observed))
        self.assertEqual(observed["owner_decision_brief"]["status"], "BLOCKED")
        self.assertEqual(
            observed["authorizations"], {"construction": "NONE", "aws": "NONE"}
        )
        self.assertIn(
            f"{doctor.PRD_FILE}#Sequence — primary outcome",
            observed["context_plan"]["on_demand_slices"],
        )
        self.assertFalse(reverse_observed["ok"])
        self.assertIn("DIAGRAM_PRESENTATION_STALE", codes(reverse_observed))
        self.assertEqual(reverse_observed["owner_decision_brief"]["status"], "BLOCKED")
        self.assertFalse(encoded_observed["ok"])
        self.assertIn("DIAGRAM_PRESENTATION_STALE", codes(encoded_observed))
        self.assertEqual(encoded_observed["owner_decision_brief"]["status"], "BLOCKED")
        self.assertTrue(future_observed["ok"], future_observed["diagnostics"])
        self.assertEqual(future_observed["owner_decision_brief"]["status"], "READY")
        self.assertEqual(future_observed["gates"], baseline["gates"])

    def test_semantic_diagram_repair_loads_the_bounded_design_procedure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.pending_gate_b(project)
            prd_path = project / "docs/project/PRD.md"
            source = prd_path.read_text(encoding="utf-8")
            malformed = source.replace(
                "ACT-001 -->|sends a review request through| TECH-0013",
                "ACT-001 --> TECH-0013",
                1,
            )
            self.assertNotEqual(malformed, source)
            prd_path.write_text(malformed, encoding="utf-8")
            refresh_document_summaries(project)

            report = doctor.inspect_project(project)

        self.assertFalse(report["ok"])
        self.assertEqual(report["gates"]["gate_a"], "APPROVED_FOR_DESIGN")
        self.assertIn("DESIGN_CONTRACT_INVALID", codes(report))
        repair = next(
            item
            for item in report["remediation"]["items"]
            if item["diagnostic_code"] == "DESIGN_CONTRACT_INVALID"
        )
        self.assertEqual(repair["responsible_party"], "CODEX")
        self.assertTrue(repair["automatic_correction_allowed"])
        self.assertEqual(
            report["remediation"]["next_action"]["action_kind"],
            "CORRECT_AND_REVALIDATE",
        )
        self.assertIn(
            ".agents/skills/fastlane/references/diagram-patterns.md",
            report["context_plan"]["on_demand_slices"],
        )
        self.assertIn(
            f"{doctor.PRD_FILE}#Project diagram contract",
            report["context_plan"]["on_demand_slices"],
        )
        self.assertIn(
            f"{doctor.PRD_FILE}#Proposed system at a glance",
            report["context_plan"]["on_demand_slices"],
        )

    def test_stale_diagram_repair_loads_its_exact_owner_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.pending_gate_b(project)
            prd_path = project / "docs/project/PRD.md"
            source = prd_path.read_text(encoding="utf-8")
            stale = source.replace(
                "| DIAGRAM-0003 | DATA_LIFECYCLE | CONDITIONAL | CURRENT |",
                "| DIAGRAM-0003 | DATA_LIFECYCLE | CONDITIONAL | STALE |",
                1,
            )
            self.assertNotEqual(stale, source)
            prd_path.write_text(stale, encoding="utf-8")
            refresh_document_summaries(project)
            report = doctor.inspect_project(project)

        self.assertFalse(report["ok"])
        self.assertIn(
            f"{doctor.PRD_FILE}#Data lifecycle view",
            report["context_plan"]["on_demand_slices"],
        )
        resolved = next(
            item
            for item in report["context_plan"]["resolved_on_demand_slices"]
            if item["path"] == doctor.PRD_FILE
            and item["selector"] == "Data lifecycle view"
        )
        selected = "\n".join(
            stale.splitlines()[resolved["start_line"] - 1 : resolved["end_line"]]
        )
        self.assertTrue(selected.startswith("### Data lifecycle view"))
        self.assertIn("```mermaid", selected)

    def test_required_project_diagrams_fail_closed_when_stale_or_generic(
        self,
    ) -> None:
        source = complete_design_contract(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        actor_inside_cloud = source.replace(
            '    subgraph PEOPLE["People"]\n'
            '        ACT-001["Development user"]:::actor\n'
            "    end\n"
            '    subgraph AWS_CLOUD["AWS Cloud · proposed architecture"]',
            '    subgraph AWS_CLOUD["AWS Cloud · proposed architecture"]\n'
            '        ACT-001["Development user"]:::actor',
            1,
        )
        hidden_architecture = source.replace(
            "### Proposed system at a glance",
            "<details>\n<summary>Hidden architecture</summary>\n\n"
            "### Proposed system at a glance",
            1,
        ).replace("## 15. Component design", "</details>\n\n## 15. Component design", 1)
        cases = {
            "stale": (
                source.replace(
                    "| DIAGRAM-0001 | SYSTEM_CONTEXT | REQUIRED | CURRENT |",
                    "| DIAGRAM-0001 | SYSTEM_CONTEXT | REQUIRED | STALE |",
                    1,
                ),
                "required SYSTEM_CONTEXT diagram is not CURRENT",
                "BLOCKED",
            ),
            "generic": (
                source.replace(
                    'ARCH-0001["Managed Serverless Baseline"]:::compute',
                    'ARCH-0001["TODO"]:::compute',
                    1,
                ),
                "generic placeholder content",
                "BLOCKED",
            ),
            "raw ID label": (
                source.replace(
                    'ARCH-0001["Managed Serverless Baseline"]:::compute',
                    'ARCH-0001["ARCH-0001"]:::compute',
                    1,
                ),
                "label must not expose a canonical record ID",
                "READY",
            ),
            "wrong complete orientation": (
                source.replace("flowchart TB", "flowchart LR", 1),
                "SYSTEM_CONTEXT must use one top-to-bottom flowchart",
                "READY",
            ),
            "unlabeled grouping": (
                source.replace(
                    'subgraph PEOPLE["People"]',
                    "subgraph PEOPLE",
                    1,
                ),
                "every subgraph requires one quoted human label",
                "READY",
            ),
            "missing accessibility title": (
                source.replace(
                    "    accTitle: Complete proposed review application architecture\n",
                    "",
                    1,
                ),
                "Mermaid requires one meaningful accTitle",
                "READY",
            ),
            "AWS label differs from selected technology": (
                source.replace(
                    'TECH-0013["Amazon API Gateway<br/>regional HTTPS endpoint"]:::entry',
                    'TECH-0013["Unrelated edge service"]:::entry',
                    1,
                ),
                "label must match its selected technical value",
                "READY",
            ),
            "interactive Mermaid directive": (
                source.replace(
                    '        ACT-001["Development user"]:::actor',
                    '        ACT-001["Development user"]:::actor\n'
                    '        click ACT-001 "https://example.invalid"',
                    1,
                ),
                "unsupported Mermaid statement",
                "READY",
            ),
            "unsafe label markup": (
                source.replace(
                    'ACT-001["Development user"]:::actor',
                    'ACT-001["Development user<img src=https://example.invalid>"]:::actor',
                    1,
                ),
                "may use only plain text and supported line breaks",
                "READY",
            ),
            "active Windows file URI": (
                source.replace(
                    'ACT-001["Development user"]:::actor',
                    'ACT-001["Development user file:C:\\\\sensitive.txt"]:::actor',
                    1,
                ),
                "must not contain an external or active URI",
                "READY",
            ),
            "wrong semantic color role": (
                source.replace(
                    'ACT-001["Development user"]:::actor',
                    'ACT-001["Development user"]:::entry',
                    1,
                ),
                "color role that conflicts with canonical meaning",
                "READY",
            ),
            "external actor inside cloud boundary": (
                actor_inside_cloud,
                "external actors must remain outside the system boundary",
                "BLOCKED",
            ),
            "observed deployment claim": (
                source.replace(
                    "AWS Cloud · proposed architecture",
                    "AWS Cloud · proposed architecture · was deployed and verified",
                    1,
                ),
                "subgraph label must not claim approval, authorization, access, or observed execution evidence",
                "READY",
            ),
            "focused accessibility authority claim": (
                source.replace(
                    "The project owner submits one review request and receives the validated result through the review API.",
                    "The owner authorized AWS deployment and the result was deployed and verified.",
                    1,
                ),
                "accDescr must not claim approval, authorization, access, or observed execution evidence",
                "READY",
            ),
            "focused authorization claim": (
                source.replace(
                    "ACT-001 -->|submits a review request to| API-001",
                    "ACT-001 -->|owner authorized AWS deployment| API-001",
                    1,
                ),
                "relationship label must not claim approval, authorization, access, or observed execution evidence",
                "BLOCKED",
            ),
            "broad observed relationship claim": (
                source.replace(
                    "TECH-0013 -->|routes authenticated requests into| BOUNDARY-001",
                    "TECH-0013 -->|was deployed and verified through| BOUNDARY-001",
                    1,
                ),
                "relationship label must not claim approval, authorization, access, or observed execution evidence",
                "BLOCKED",
            ),
            "node access grant claim": (
                source.replace(
                    'ACT-001["Development user"]:::actor',
                    'ACT-001["Owner granted AWS access"]:::actor',
                    1,
                ),
                "ACT-001 label must not claim approval, authorization, access, or observed execution evidence",
                "READY",
            ),
            "focused accessibility access grant claim": (
                source.replace(
                    "The project owner submits one review request and receives the validated result through the review API.",
                    "The owner granted AWS access.",
                    1,
                ),
                "accDescr must not claim approval, authorization, access, or observed execution evidence",
                "READY",
            ),
            "focused relationship access grant claim": (
                source.replace(
                    "ACT-001 -->|submits a review request to| API-001",
                    "ACT-001 -->|owner granted AWS access| API-001",
                    1,
                ),
                "relationship label must not claim approval, authorization, access, or observed execution evidence",
                "BLOCKED",
            ),
            "subgraph access grant claim": (
                source.replace(
                    "AWS Cloud · proposed architecture",
                    "AWS Cloud · owner granted AWS access",
                    1,
                ),
                "subgraph label must not claim approval, authorization, access, or observed execution evidence",
                "READY",
            ),
            "hidden required architecture": (
                hidden_architecture,
                "must remain visible outside disclosures",
                "READY",
            ),
            "duplicate palette override": (
                source.replace(
                    "classDef actor fill:#FFFFFF,stroke:#232F3E,color:#232F3E,stroke-width:2px;",
                    "classDef actor fill:#FFFFFF,fill:#000000,stroke:#232F3E,color:#232F3E,stroke-width:2px;",
                    1,
                ),
                "actor classDef must use the approved readable semantic palette",
                "READY",
            ),
            "unused unsafe style": (
                source.replace(
                    "classDef actor fill:#FFFFFF,stroke:#232F3E,color:#232F3E,stroke-width:2px;",
                    "classDef actor fill:#FFFFFF,stroke:#232F3E,color:#232F3E,stroke-width:2px;\n"
                    "    classDef tracker fill:url(https://example.invalid),stroke:#000000,color:#000000;",
                    1,
                ),
                "classDef styles must be used by displayed nodes",
                "READY",
            ),
            "empty organizational group": (
                source.replace(
                    '        subgraph REGION["',
                    '        subgraph EMPTY["Unused group"]\n        end\n'
                    '        subgraph REGION["',
                    1,
                ),
                "broad architecture contains empty subgraphs",
                "READY",
            ),
            "disconnected deployment island": (
                source.replace(
                    'TECH-0009 -. "deploys" .-> TECH-0001',
                    'TECH-0009 -. "returns deployment metadata to" .-> TECH-0004',
                    1,
                ),
                "must present one connected owner view",
                "BLOCKED",
            ),
            "architecture self-loop": (
                source.replace(
                    "ARCH-0001 -->|stores owner records in| TECH-0011",
                    "ARCH-0001 -->|stores owner records in| TECH-0011\n"
                    "    ARCH-0001 -->|implements itself| ARCH-0001",
                    1,
                ),
                "must not contain self-loop ARCH-0001",
                "BLOCKED",
            ),
            "system view without requirement basis": (
                source.replace(
                    "proposed-system-at-a-glance | ARCH-0001, FR-001 |",
                    "proposed-system-at-a-glance | ARCH-0001 |",
                    1,
                ),
                "lacks its canonical purpose basis",
                "BLOCKED",
            ),
            "unsupported unlabeled relationship": (
                source.replace(
                    "ACT-001 -->|sends a review request through| TECH-0013",
                    "ACT-001 -->|sends a review request through| TECH-0013\n"
                    "    ACT-001 --> TECH-0013",
                    1,
                ),
                "every visible relationship must connect labeled canonical component nodes",
                "BLOCKED",
            ),
            "empty relationship meaning": (
                source.replace(
                    "API-001 -->|invokes| TECH-0002",
                    "API-001 -->|   | TECH-0002",
                    1,
                ),
                "relationship labels must not be empty",
                "BLOCKED",
            ),
            "AWS component omitted": (
                source.replace(
                    'TECH-0015 -. "restores" .-> TECH-0001',
                    "",
                    1,
                ),
                "Referenced IDs must exactly match Mermaid relationship endpoints",
                "BLOCKED",
            ),
        }
        for label, (candidate, expected, expected_status) in cases.items():
            with self.subTest(case=label):
                self.assertNotEqual(candidate, source, label)
                blocked, issues = doctor.derive_design_contract(
                    candidate,
                    "DES-0001",
                    required=True,
                )
                self.assertEqual(blocked.status, expected_status)
                self.assertTrue(any(expected in issue for issue in issues), issues)
                if expected_status == "READY":
                    self.assertTrue(
                        all(
                            issue.startswith("DIAGRAM_PRESENTATION_STALE: ")
                            for issue in issues
                        ),
                        issues,
                    )
                    self.assertIsNotNone(blocked.canonical_sha256)

    def test_focused_diagrams_must_match_their_owner_purpose(self) -> None:
        source = complete_design_contract(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        table = doctor.contract_table_after_heading(
            source, doctor.DIAGRAM_CONTRACT_HEADING, doctor.DIAGRAM_CONTRACT_HEADERS
        )
        self.assertIsNotNone(table)
        false_view = """```mermaid
flowchart LR
    accTitle: Incorrect technical view
    accDescr: This intentionally unrelated graph proves each view retains its project purpose.
    TECH-0004["AWS SAM<br/>infrastructure templates"]
    TECH-0014["Amazon CloudWatch<br/>logs, metrics, and alarms"]
    TECH-0004 -->|sends to| TECH-0014
```"""
        primary_heading = next(
            line
            for line in source.splitlines()
            if line.startswith("### Sequence") and "primary outcome" in line
        )
        failure_heading = next(
            line
            for line in source.splitlines()
            if line.startswith("### Sequence") and "failure and recovery" in line
        )
        cases = {
            "PRIMARY_OUTCOME": (
                "DIAGRAM-0002",
                primary_heading,
                failure_heading,
                "must show an approved actor",
            ),
            "DATA_LIFECYCLE": (
                "DIAGRAM-0003",
                "### Data lifecycle view",
                "## 18. Detailed sequence diagrams",
                "must show the selected data-storage mechanism",
            ),
            "FAILURE_RECOVERY": (
                "DIAGRAM-0004",
                failure_heading,
                "## 19. Error handling strategy",
                "must show the selected recovery mechanism",
            ),
        }
        for kind, (diagram_id, heading, next_heading, expected) in cases.items():
            with self.subTest(kind=kind):
                changed = replace_contract_table(
                    source,
                    doctor.DIAGRAM_CONTRACT_HEADING,
                    doctor.DIAGRAM_CONTRACT_HEADERS,
                    [
                        (*row[:6], "TECH-0004, TECH-0014")
                        if row[0] == diagram_id
                        else row
                        for row in table.rows
                    ],
                )
                changed = set_diagram_block(changed, heading, next_heading, false_view)
                blocked, issues = doctor.derive_design_contract(
                    changed, "DES-0001", required=True
                )
                self.assertEqual(blocked.status, "BLOCKED")
                self.assertTrue(any(expected in issue for issue in issues), issues)

    def test_focused_diagram_styles_are_optional_but_never_active_or_false(
        self,
    ) -> None:
        source = complete_design_contract(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        baseline, baseline_issues = doctor.derive_design_contract(
            source, "DES-0001", required=True
        )
        self.assertEqual(baseline_issues, [])
        data_start = source.index("### Data lifecycle view")
        data_section = (
            source[data_start:]
            .replace(
                'TECH-0011[("Amazon DynamoDB with<br/>per-owner records")]',
                'TECH-0011[("Amazon DynamoDB with<br/>per-owner records")]:::tracker',
                1,
            )
            .replace(
                "API-001 -->|validates and stores in| TECH-0011",
                "API-001 -->|validates and stores in| TECH-0011\n"
                "    classDef tracker fill:url(https://example.invalid/pixel),stroke:#000000,color:#000000;",
                1,
            )
        )
        styled = source[:data_start] + data_section
        self.assertNotEqual(styled, source)
        candidate, issues = doctor.derive_design_contract(
            styled, "DES-0001", required=True
        )
        self.assertEqual(candidate.status, "READY")
        self.assertEqual(candidate.canonical_sha256, baseline.canonical_sha256)
        self.assertTrue(issues)
        self.assertTrue(
            all(issue.startswith("DIAGRAM_PRESENTATION_STALE: ") for issue in issues),
            issues,
        )
        self.assertTrue(
            any("unsupported Mermaid classDef 'tracker'" in issue for issue in issues),
            issues,
        )

    def test_approved_pre_aws_design_seven_remains_current_until_revision(
        self,
    ) -> None:
        legacy = (PROJECT_ROOT / "tests/fixtures/legacy_1234_pre_aws_prd.md").read_text(
            encoding="utf-8"
        )

        grandfathered, issues = doctor.derive_design_contract(
            legacy,
            "DES-0001",
            required=True,
            grandfather_approved_v1=True,
        )
        self.assertEqual(issues, [])
        self.assertEqual(grandfathered.status, "READY")
        self.assertEqual(
            grandfathered.diagram_contract.canonical_sha256,
            "sha256:ce8b2dfed3fb6cb3967244bfe2f11265c440e1ae03c2bb92b0ede1966cc5d9d8",
        )
        self.assertEqual(
            grandfathered.canonical_sha256,
            "sha256:9e925fbaf47a328ab9ea327d6d7f1058d9945154d8ecabe27384a9115bf23cbc",
        )

        revised, revised_issues = doctor.derive_design_contract(
            legacy,
            "DES-0001",
            required=True,
            grandfather_approved_v1=False,
        )
        self.assertEqual(revised.status, "BLOCKED")
        self.assertTrue(
            any(
                "Missing required diagram kinds: AWS_IMPLEMENTATION" in issue
                for issue in revised_issues
            ),
            revised_issues,
        )

    def test_pre_aws_projection_envelope_remains_current_after_upgrade(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            self.set_non_material_req_evidence(project)
            prd_path = project / "docs/project/PRD.md"
            text = prd_path.read_text(encoding="utf-8")
            diagram_table = doctor.contract_table_after_heading(
                text,
                doctor.DIAGRAM_CONTRACT_HEADING,
                doctor.DIAGRAM_CONTRACT_HEADERS,
            )
            self.assertIsNotNone(diagram_table)
            assert diagram_table is not None
            text = replace_contract_table(
                text,
                doctor.DIAGRAM_CONTRACT_HEADING,
                doctor.DIAGRAM_CONTRACT_HEADERS,
                [
                    (
                        row[0],
                        row[1],
                        row[2],
                        "NOT_YET_CREATED",
                        row[4],
                        "NONE",
                        "NONE",
                    )
                    if row[1] == "AWS_IMPLEMENTATION"
                    else row
                    for row in diagram_table.rows
                ],
            )
            text = set_diagram_block(
                text,
                "### AWS implementation at a glance",
                "<details>\n<summary>Exact AWS service decision records</summary>",
                "No AWS implementation diagram was required by this approved legacy design.",
            )
            legacy_contract, legacy_issues = doctor.derive_design_contract(
                text,
                "DES-0001",
                required=True,
                grandfather_approved_v1=True,
            )
            self.assertEqual(legacy_issues, [])
            self.assertIsNotNone(legacy_contract.canonical_sha256)
            frozen_design_sha256 = legacy_contract.canonical_sha256
            assert frozen_design_sha256 is not None
            text = set_table_value(
                text,
                "## 28. Construction envelope",
                "## 29. Gate B owner authorization record",
                "Design contract SHA-256",
                f"`{frozen_design_sha256}`",
            )
            envelope_digest = doctor.canonical_envelope_sha256(text)
            text = set_table_value(
                text,
                "## 27. Gate B agent review record",
                "## 28. Construction envelope",
                "Construction envelope SHA-256 reviewed",
                f"`{envelope_digest}`",
            )
            text = set_table_value(
                text,
                "## 29. Gate B owner authorization record",
                "## 30. Gate B validation and invalidation rules",
                "Authorized construction envelope SHA-256",
                f"`{envelope_digest}`",
            )
            text = set_receipt(
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
            prd_path.write_text(text, encoding="utf-8")
            refresh_document_summaries(project)
            report = doctor.inspect_project(project)

        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["diagnostics"], [])
        self.assertEqual(
            report["design_contract"]["canonical_sha256"],
            frozen_design_sha256,
        )
        self.assertEqual(report["gates"]["gate_b"], "APPROVED_FOR_CONSTRUCTION")
        self.assertEqual(report["lifecycle_state"], "TASK_PLAN_REQUIRED")
        self.assertEqual(report["next_prompt"], "TASK-10")

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
        self.assertEqual(ready.schema_version, 7)
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
            any(
                "Authorization" in issue and "must be concrete" in issue
                for issue in blocked_issues
            ),
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
            [
                (
                    "STATE-001",
                    "RESOURCE-001",
                    "PENDING, READY",
                    "PENDING",
                    "PENDING -> READY",
                    "READY",
                    "Reject invalid transitions",
                    "FR-001",
                    "TEST-999",
                )
            ],
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
            "| Project design contract schema | `7` |\n", "", 1
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
            any(
                "Project design contract schema 7" in issue
                for issue in migration_issues
            ),
            migration_issues,
        )

    def test_truthful_standard_and_plain_colon_actor_labels_remain_current(
        self,
    ) -> None:
        source = complete_design_contract(
            (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        )
        self.assertEqual(source.count("Development user"), 3)
        for label in ("ISO-27001 reviewer", "Data: owner"):
            with self.subTest(label=label):
                changed = source.replace("Development user", label)
                self.assertEqual(changed.count(label), 3)
                contract, issues = doctor.derive_design_contract(
                    changed,
                    "DES-0001",
                    required=True,
                )
                self.assertEqual(contract.status, "READY")
                self.assertEqual(issues, [])

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
            rows=(
                doctor.HarnessRow(
                    "HARNESS-001",
                    "End-to-end",
                    "unittest",
                    "Approved design",
                    "DES-0001, FR-001",
                    "python -m unittest tests.test_legacy",
                    "docs/project/VERIFY.md#legacy",
                    "REQUIRED",
                ),
            ),
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
                    "JOURNEY-001",
                    "ACT-001",
                    "See the approved project outcome",
                    "The development user requests the local result",
                    "The current approved outcome is displayed",
                    "Invalid input is rejected without changing approved state",
                    ", ".join(journey_one_ids),
                    "NONE",
                ),
                (
                    "JOURNEY-002",
                    "ACT-001",
                    "Reject invalid input",
                    "The development user submits invalid input",
                    "The invalid input is rejected",
                    "Approved state remains unchanged",
                    "FR-002",
                    "NONE",
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
                (*row[:3], "JOURNEY-002", *row[4:]) if row[0] == "FR-002" else row
                for row in coverage_table.rows
            ],
        )
        mismatched_wave = replace_contract_table(
            split,
            doctor.FIRST_WAVE_HEADING,
            doctor.FIRST_WAVE_HEADERS,
            [
                (
                    "WAVE-001",
                    "NEW_BUILD",
                    "JOURNEY-001",
                    "FR-001, FR-002",
                    "AC-FR-001, AC-FR-002",
                    "HARNESS-004",
                    "NONE",
                )
            ],
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
            [
                (
                    "WAVE-001",
                    "NEW_BUILD",
                    "JOURNEY-001",
                    "FR-001",
                    "AC-FR-001",
                    "HARNESS-004",
                    "SPIKE-001",
                )
            ],
        )
        spike_table = "\n".join(
            [
                "| Spike ID | Blocking technical unknown | Time box | Disposable output boundary | Exit criterion | Required next action |",
                "|---|---|---|---|---|---|",
                "| SPIKE-001 | Verify the local adapter contract | MAX_ATTEMPTS: 2 | work/spike/** | python -m unittest tests.test_spike_exit | DISCARD_AND_BUILD_WALKING_SKELETON |",
            ]
        )
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
                    any(
                        "Exit criterion must be one explicit local command" in issue
                        for issue in unsafe_issues
                    ),
                    unsafe_issues,
                )

    def test_design_seven_fails_when_any_owner_technical_domain_is_missing(
        self,
    ) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        complete = complete_design_contract(source)
        representative_concerns = {
            "application/runtime": "APPLICATION_RUNTIME",
            "identity": "IDENTITY_AUTHORIZATION",
            "data": "DATA_STORAGE",
            "messaging": "MESSAGING_RETRIES",
            "edge/networking": "EDGE_NETWORKING",
            "observability": "OBSERVABILITY_INCIDENT_RESPONSE",
            "deployment/recovery": "RELIABILITY_RECOVERY",
            "validation/construction": "TEST_TOOLING",
        }
        self.assertEqual(
            set(representative_concerns),
            set(doctor.TECHNICAL_DOMAIN_ORDER),
        )
        for domain, concern in representative_concerns.items():
            with self.subTest(domain=domain, concern=concern):
                without_concern = "\n".join(
                    line
                    for line in complete.splitlines()
                    if f"| {concern} |" not in line
                )
                design, issues = doctor.derive_design_contract(
                    without_concern,
                    "DES-0001",
                    required=True,
                )
                self.assertEqual(design.status, "BLOCKED")
                self.assertTrue(
                    any(
                        f"Technology concern {concern} must appear exactly once"
                        in issue
                        for issue in issues
                    ),
                    issues,
                )

    def test_real_approved_schema_12_gate_a_reaches_schema_six(self) -> None:
        source = (PROJECT_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        approved_modern = complete_design_contract(approve_gate_a(source))
        legacy_basis = exact_legacy_requirements_projection(approved_modern)
        migrated = complete_legacy_design_bridge(source)
        self.assertEqual(
            legacy_basis.split("# Technical Plan", 1)[0],
            migrated.split("# Technical Plan", 1)[0],
        )
        requirements, requirement_issues = doctor.derive_requirements_contract(
            migrated,
            "low",
            None,
            required=True,
            grandfather_current_gate_a=True,
        )
        self.assertEqual(requirement_issues, [])
        self.assertEqual(requirements.status, "GRANDFATHERED")
        self.assertEqual(
            requirements.acceptance_ids,
            tuple(f"AC-{item}" for item in requirements.requirement_ids),
        )
        design, design_issues = doctor.derive_design_contract(
            migrated,
            "DES-0001",
            required=True,
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
                    [
                        (
                            "RESOURCE-001",
                            "NOT_APPLICABLE",
                            "NOT_APPLICABLE - no state",
                            "NONE",
                        )
                    ],
                ),
                "grandfathered Gate A design requires an applicable state model",
            ),
        }
        for label, (candidate, expected) in cases.items():
            with self.subTest(case=label):
                design, issues = doctor.derive_design_contract(
                    candidate,
                    "DES-0001",
                    required=True,
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
            modern,
            "DES-0001",
            required=True,
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
            complete,
            "low",
            None,
            required=True,
            grandfather_current_gate_a=False,
        )
        self.assertEqual(requirement_issues, [])

        def stateful(trigger_basis: str) -> str:
            text = replace_contract_table(
                complete,
                doctor.STATE_APPLICABILITY_HEADING,
                doctor.STATE_APPLICABILITY_HEADERS,
                [("RESOURCE-001", "APPLICABLE", trigger_basis, "STATE-001")],
            )
            text = replace_contract_table(
                text,
                doctor.STATE_REGISTER_HEADING,
                doctor.STATE_REGISTER_HEADERS,
                [
                    (
                        "STATE-001",
                        "RESOURCE-001",
                        "PENDING, READY",
                        "PENDING",
                        "PENDING to READY",
                        "READY",
                        "Reject invalid transitions",
                        "FR-001",
                        "AC-FR-001",
                    )
                ],
            )
            return complete_state_diagrams(text)

        for category in doctor.STATE_MODEL_TRIGGERS:
            with self.subTest(category=category):
                ready, issues = doctor.derive_design_contract(
                    stateful(f"{category}: FR-001"),
                    "DES-0001",
                    required=True,
                    requirements_contract=requirements,
                )
                self.assertEqual(issues, [])
                self.assertEqual(ready.status, "READY")
        for rich_trigger, state_trigger in doctor.RICH_TO_STATE_TRIGGER.items():
            triggered = replace(requirements, rich_use_case_triggers=(rich_trigger,))
            blocked, issues = doctor.derive_design_contract(
                stateful("LIFECYCLE_RESOURCE: FR-001"),
                "DES-0001",
                required=True,
                requirements_contract=triggered,
            )
            self.assertEqual(blocked.status, "BLOCKED")
            self.assertTrue(any(state_trigger in issue for issue in issues), issues)
            ready, issues = doctor.derive_design_contract(
                stateful(f"{state_trigger}: FR-001"),
                "DES-0001",
                required=True,
                requirements_contract=triggered,
            )
            self.assertEqual(issues, [])
            self.assertEqual(ready.status, "READY")

        for invalid in (
            "UNKNOWN: FR-001",
            "APPROVAL_FLOW: FR-001; LIFECYCLE_RESOURCE: FR-001",
        ):
            blocked, issues = doctor.derive_design_contract(
                stateful(invalid),
                "DES-0001",
                required=True,
                requirements_contract=requirements,
            )
            self.assertEqual(blocked.status, "BLOCKED")
            self.assertTrue(any("State trigger" in issue for issue in issues), issues)

    @source_template_only
    def test_additive_owner_projections_preserve_engine_schema_and_template_route(
        self,
    ) -> None:
        report = doctor.inspect_project(PROJECT_ROOT)

        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["classification"], "UNCONFIGURED_TEMPLATE")
        self.assertEqual(report["owner_decision_brief"]["schema_version"], 1)
        self.assertEqual(report["owner_decision_brief"]["status"], "NONE")
        self.assertEqual(report["owner_decision_inventory"]["schema_version"], 1)
        self.assertEqual(report["owner_decision_inventory"]["kind"], "NONE")
        self.assertEqual(report["owner_decision_inventory"]["status"], "NONE")
        self.assertEqual(report["owner_decision_inventory"]["decisions"], [])
        self.assertEqual(report["owner_answer_confirmation"]["schema_version"], 1)
        self.assertEqual(report["owner_answer_confirmation"]["status"], "NONE")
        self.assertEqual(
            report["interaction"]["owner_action_kind"],
            "COMPLETE_PREREQUISITE_CHECKLIST",
        )

    def test_stale_document_summaries_do_not_change_lifecycle_or_authority(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            refresh_control_hashes(project)

            report = doctor.inspect_project(project)

        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["classification"], "ACTIVE_GREENFIELD")
        self.assertEqual(report["next_prompt"], "INTAKE-10")
        self.assertEqual(
            report["authorizations"],
            {"construction": "NONE", "aws": "NONE"},
        )
        self.assertEqual(report["document_summaries"]["schema_version"], 1)
        self.assertEqual(report["document_summaries"]["status"], "STALE")
        self.assertIn("DOCUMENT_SUMMARY_STALE", codes(report))
        self.assertEqual(
            report["document_summaries"]["repair"],
            {
                "responsible_party": "CODEX",
                "action_kind": "CORRECT_AND_REVALIDATE",
                "automatic_continuation_allowed": True,
            },
        )
        self.assertNotIn(
            "DOCUMENT_SUMMARY_STALE",
            {item["diagnostic_code"] for item in report["remediation"]["items"]},
        )

    def test_stale_summary_blocks_only_a_pending_owner_brief(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.pending_gate_a(project)
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
            self.assertNotEqual(source_text, changed)
            prd_path.write_text(changed, encoding="utf-8")
            refresh_control_hashes(project)
            observed = doctor.inspect_project(project)

        self.assertTrue(baseline["ok"], baseline["diagnostics"])
        self.assertFalse(observed["ok"])
        self.assertEqual(observed["lifecycle_state"], "WAITING_GATE_A")
        self.assertEqual(observed["gates"], baseline["gates"])
        self.assertEqual(
            observed["requirements_contract"], baseline["requirements_contract"]
        )
        self.assertEqual(
            observed["basis"]["prd_snapshot_sha256"],
            baseline["basis"]["prd_snapshot_sha256"],
        )
        self.assertEqual(observed["owner_decision_brief"]["status"], "BLOCKED")
        self.assertFalse(observed["owner_decision_brief"]["formal_receipt_required"])
        self.assertEqual(
            observed["remediation"]["next_action"]["action_kind"],
            "CORRECT_AND_REVALIDATE",
        )

    def test_summary_hand_edit_changes_only_the_presentation_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_project(Path(directory))
            self.approve_project(project)
            self.set_non_material_req_evidence(project)
            refresh_control_hashes(project)
            baseline = doctor.inspect_project(project)
            prd_path = project / "docs/project/PRD.md"
            source = prd_path.read_text(encoding="utf-8")
            changed = source.replace(
                "\n".join(
                    [
                        "| Product outcome | Not yet confirmed |",
                        "| First-release boundary | Not yet confirmed |",
                        "| Requirements | Not yet initialized |",
                        "| Technical design | Not yet initialized |",
                        "| Gate A | Not yet initialized |",
                    ]
                ),
                "\n".join(
                    [
                        "## Document status",
                        "| Field | Value |",
                        "|---|---|",
                        "| Requirements revision | REQ-9999 |",
                        "| Gate A derived status | APPROVED_FOR_DESIGN |",
                    ]
                ),
                1,
            )
            self.assertNotEqual(source, changed)
            prd_path.write_text(changed, encoding="utf-8")
            refresh_control_hashes(project)
            observed = doctor.inspect_project(project)

        self.assertTrue(baseline["ok"], baseline["diagnostics"])
        self.assertTrue(observed["ok"], observed["diagnostics"])
        for key in (
            "classification",
            "lifecycle_state",
            "next_prompt",
            "interaction",
            "gates",
            "evidence_state",
            "authorizations",
            "write_authority",
            "external_authority",
            "intake_foundation",
            "requirements_contract",
            "coverage_plan",
            "design_contract",
            "tasks",
        ):
            self.assertEqual(observed[key], baseline[key], key)
        self.assertEqual(observed["basis"], baseline["basis"])
        self.assertEqual(observed["document_summaries"]["status"], "STALE")
        self.assertEqual(
            observed["document_summaries"]["repair"]["action_kind"],
            "CORRECT_AND_REVALIDATE",
        )


if __name__ == "__main__":
    unittest.main()
