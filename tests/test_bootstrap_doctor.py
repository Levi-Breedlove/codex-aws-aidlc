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


def approve_gate_a(text: str) -> str:
    replacements = {
        "| FR-001 | TODO | UBIQUITOUS | TODO | MEASURABLE |": (
            "| FR-001 | The application SHALL display the current approved project outcome. "
            "| UBIQUITOUS | A rendered-output test confirms the approved outcome is displayed. "
            "| MEASURABLE |"
        ),
        "| FR-002 | TODO | UNWANTED_BEHAVIOR | TODO | GHERKIN |": (
            "| FR-002 | IF input violates approved constraints, THEN the application SHALL "
            "reject it without changing approved state. | UNWANTED_BEHAVIOR | GIVEN input "
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
            "TECH-0006, TECH-0007, TECH-0008, TECH-0009, PROP-001`"
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
    actor: str = "CODEX_LIVE_TOOL_CALL",
    plugin_version: str = "1.2.0",
    advisory_design_binding: str = "DES-0001; TECH: NONE — no technology/toolchain impact",
) -> str:
    if binding is None:
        binding = {
            "DESIGN-10": "DES-0001",
            "AWS-10": "sha256:" + "a" * 64,
        }[phase]
    for capability in doctor.AWS_CORE_REQUIRED_CAPABILITIES:
        text = record_aws_core_capability_evidence(
            text,
            phase,
            capability,
            status,
            binding=binding,
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
    if capability == "retrieve_skill":
        requested_skill = requested_skill or "aws-architecture"
        returned_skill_identifier = returned_skill_identifier or requested_skill
        documentation_query = "—"
        source_references = "—"
    else:
        requested_skill = "—"
        returned_skill_identifier = "—"
        documentation_query = documentation_query or "Current AWS service and IAM guidance"
        source_references = source_references or (
            "https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html"
        )
    replacement = (
        f"| `{phase}` | `{plugin_source}` | `{invoked_identity}` | "
        f"`{plugin_version}` | `{capability}` | `{actor}` | "
        f"`{requested_skill}` | `{returned_skill_identifier}` | "
        f"`{documentation_query}` | `{source_references}` | "
        f"`{advisory_design_binding}` | `{credentials_inspected}` | "
        f"`{aws_account_accessed}` | `2026-07-20T12:00:00Z` | "
        f"`{binding}` | `{status}` |"
    )
    updated, count = re.subn(
        rf"^\| `{re.escape(phase)}` \|.*\| `{re.escape(capability)}` \|.*$",
        replacement,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise AssertionError(
            f"Missing AWS Core evidence row for {phase} {capability}"
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


def complete_design_contract(text: str) -> str:
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
            "| Architecture ID | Selected candidate | Requirement and driver basis | Rationale | Rejected alternatives | Risks | Mitigations | Cost effect | Breakpoints | Revisit triggers | Validation |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
            f"| ARCH-0001 | CAND-0001 | {requirement_list}, DRV-0001 | Meets every hard constraint with the smallest managed surface | CAND-0002 | Managed-service limits | Validate quotas and alarms before deployment | Pay per request with no intentional idle compute | Reassess at sustained utilization where containers are cheaper | Reassess on quota, residency, or latency changes | Requirement trace and integration tests |",
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
            "| Requirement ID | ARCH / COMP / API / DATA / CTRL IDs | Property/test IDs | Evidence IDs |",
            "|---|---|---|---|",
            *trace_rows,
        ]
    )
    text = put_contract_table(text, doctor.ARCHITECTURE_TRACEABILITY_HEADING, trace_table, doctor.MATERIAL_AWS_EVIDENCE_HEADING)
    evidence_table = "\n".join(
        [
            "| Evidence ID | Design IDs | Material claim | AWS Core capability | Official reference | Observed date |",
            "|---|---|---|---|---|---|",
            "| AWS-EV-0001 | DRV-0001, CAND-0001, CAND-0002, ARCH-0001, TECH-0001 | AWS managed serverless services support bounded pay-per-use execution patterns | retrieve_skill | https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html | 2026-07-17 |",
            "| AWS-EV-0002 | DRV-0001, CAND-0001, CAND-0002, ARCH-0001, TECH-0004 | AWS documentation defines current serverless security and operational guidance | search_documentation | https://docs.aws.amazon.com/lambda/latest/dg/security.html | 2026-07-17 |",
        ]
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
    harness_table = "\n".join(
        [
            "| Harness ID | Layer | Selected check or tool | Trigger | Basis IDs | Exact command or API | Evidence destination | Required or conditional status |",
            "|---|---|---|---|---|---|---|---|",
            *harness_rows,
        ]
    )
    return put_contract_table(
        text,
        doctor.HARNESS_HEADING,
        harness_table,
        "## 27. Gate B agent review record",
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
        self.assertEqual(report["bootstrap_version"], "1.2.0")
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
        self.assertEqual(report["design_contract"]["schema_version"], 3)
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
        self.assertEqual(ready.schema_version, 3)
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

        legacy = complete.replace(
            "| Gate B derived status | `BLOCKED` |",
            "| Gate B derived status | `APPROVED_FOR_CONSTRUCTION` |",
            1,
        )
        for heading in (
            doctor.ARCHITECTURE_DRIVER_HEADING,
            doctor.ARCHITECTURE_CANDIDATE_HEADING,
            doctor.ARCHITECTURE_SELECTION_HEADING,
            doctor.ARCHITECTURE_TRACEABILITY_HEADING,
            doctor.MATERIAL_AWS_EVIDENCE_HEADING,
            doctor.HARNESS_HEADING,
        ):
            legacy = legacy.replace(heading, heading + " (legacy v1)", 1)
        grandfathered, grandfathered_issues = doctor.derive_design_contract(
            legacy,
            "DES-0001",
            required=True,
        )
        self.assertEqual(grandfathered_issues, [])
        self.assertEqual(grandfathered.status, "READY")
        self.assertEqual(grandfathered.schema_version, 1)
        self.assertTrue(grandfathered.architecture.grandfathered_v1)

        design_changed = legacy.replace(
            doctor.ARCHITECTURE_DRIVER_HEADING + " (legacy v1)",
            doctor.ARCHITECTURE_DRIVER_HEADING,
            1,
        )
        invalidated, invalidated_issues = doctor.derive_design_contract(
            design_changed,
            "DES-0001",
            required=True,
        )
        self.assertEqual(invalidated.status, "BLOCKED")
        self.assertTrue(
            any("Missing ### Whole-system candidates" in issue for issue in invalidated_issues),
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
            self.assertEqual(contract["schema_version"], 3)
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
                    + " | EV-AWS-0010 | PASS | READY |"
                    + suffix
                )
                break
        else:
            self.fail("Deployment authorization provenance row not found")
        authority = doctor._receipt_external_authority(
            "".join(lines), "Deployment", "AUTH-0001"
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
                ", TECH-0009, PROP-001`",
                ", TECH-0009`",
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

    def test_gate_b_requires_fresh_design_aws_core_evidence(self) -> None:
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

        self.assertIn("AWS_CORE_EVIDENCE_REQUIRED", codes(report))
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

    def test_aws_core_evidence_is_limited_to_design_and_aws_preflight(self) -> None:
        verify_text = (REPOSITORY_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        rows = doctor.parse_aws_core_evidence(verify_text)
        self.assertEqual(
            {phase for phase, _capability in rows},
            {"DESIGN-10", "AWS-10"},
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
        self.assertEqual(
            valid_mutation_report["external_authority"]["kind"],
            "FAST_DEV_GATE_B",
        )
        self.assertEqual(
            valid_mutation_report["external_authority"]["validity"],
            "CURRENT",
        )
        self.assertEqual(
            valid_mutation_report["external_authority"]["account"],
            "ACCOUNT: 123456789012",
        )
        self.assertEqual(
            valid_mutation_report["external_authority"]["region"],
            "REGION: us-west-2",
        )
        self.assertEqual(
            valid_mutation_report["external_authority"]["cost_ceiling"],
            "USD: 20.00",
        )
        request_match = valid_mutation_report["external_authority"]["request_match"]
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
        self.assertEqual(
            explicit_gate_report["external_authority"]["kind"],
            "AWS_ACTION_RECEIPT_REQUIRED",
        )
        self.assertEqual(
            explicit_gate_report["external_authority"]["request_match"]["validity"],
            "BLOCKED",
        )

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


if __name__ == "__main__":
    unittest.main()
