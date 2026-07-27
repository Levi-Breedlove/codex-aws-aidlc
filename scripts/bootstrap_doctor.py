#!/usr/bin/env python3
"""Read-only structural and lifecycle checks for AWS Codex Fastlane projects.

``bootstrap.yaml`` intentionally uses JSON syntax. JSON is a YAML 1.2 subset,
so the state ledger remains portable while this doctor can use only Python's
standard library and reject ambiguous YAML constructs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

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


STATE_FILE = "bootstrap.yaml"
MANIFEST_FILE = "bootstrap.manifest.json"
PROJECT_DOCUMENT_DIRECTORY = "docs/project"
BUGFIX_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/BUGFIX.md"
PRD_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/PRD.md"
RUNBOOK_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/RUNBOOK.md"
TASKS_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/TASKS.md"
VERIFY_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/VERIFY.md"
PROMPT_FILE = "prompts/CODEX-PROMPTS.md"
REQ_ID = re.compile(r"REQ-\d{4,}")
DES_ID = re.compile(r"DES-\d{4,}")
AUTH_ID = re.compile(r"AUTH-\d{4,}")
PLAN_ID = re.compile(r"PLAN-\d{4,}")
TASK_ID = re.compile(r"TASK-\d+")
RUN_ID = re.compile(r"RUN-\d{4,}")
CHECKPOINT_ID = re.compile(r"CP-\d{4,}")
COST_AMOUNT = r"[1-9]\d*(?:\.\d{1,2})?"
AWS_COST_CEILING = re.compile(
    rf"(?P<currency>[A-Z]{{3}}): (?P<amount>{COST_AMOUNT})"
)
COST_POSTURE_WITH_CAP = re.compile(
    rf"MINIMIZE_TOTAL_COST; HARD_CAP: (?P<currency>[A-Z]{{3}}) (?P<amount>{COST_AMOUNT})"
)
DEFAULT_COST_POSTURE = "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED"
# Current ISO 4217 List One currency and fund codes, excluding the testing
# code XTS and no-currency code XXX. Keep this equal to bootstrap.py so setup
# and machine-derived authorization enforce the same dependency-free grammar.
ISO_4217_CURRENCY_CODES = frozenset(
    """AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR XOF XPD XPF XPT XSU XUA YER ZAR ZMW ZWG""".split()
)

PROJECT_MODES = {"greenfield", "brownfield"}
DELIVERY_PROFILES = {"quick-mvp", "standard", "high-risk"}
RISK_LEVELS = {"low", "moderate", "high", "critical"}
AWS_LANES = {"documentation-only", "read-only", "fast-dev", "explicit-gate"}
WORK_KINDS = {
    "NEW_BUILD",
    "FEATURE",
    "BUGFIX",
    "REFACTOR",
    "MIGRATION",
    "INFRASTRUCTURE",
    "SECURITY_FIX",
}
ARCHITECTURE_DISPOSITIONS = {"SELECT", "AMEND", "PRESERVE"}
COVERAGE_DOMAINS = (
    "REQUIREMENTS",
    "ARCHITECTURE_COMPARISON",
    "AWS_EVIDENCE",
    "DATA",
    "SECURITY_PRIVACY",
    "RELIABILITY_RECOVERY",
    "COST",
    "HARNESS",
    "TASKS",
    "OPERATIONS",
)
ALWAYS_REQUIRED_COVERAGE = {
    "REQUIREMENTS",
    "SECURITY_PRIVACY",
    "COST",
    "HARNESS",
    "TASKS",
    "OPERATIONS",
}
COVERAGE_PLAN_HEADING = "### Adaptive coverage plan"
COVERAGE_PLAN_HEADERS = (
    "Work kind",
    "Delivery profile",
    "Architecture disposition",
    "Required sections",
    "Omitted sections and reasons",
    "Basis IDs",
)
CHANGE_IMPACT_HEADING = "### Change impact record"
CHANGE_IMPACT_HEADERS = (
    "Change ID",
    "Changed basis IDs",
    "Affected IDs",
    "Preserved IDs",
    "Required revalidation",
)
CHANGE_ID = re.compile(r"CHANGE-\d{4,}")
TECHNOLOGY_DECISION_HEADING = "### Technology and toolchain decision register"
TECHNOLOGY_DECISION_HEADERS = (
    "Decision ID",
    "Concern",
    "Selection",
    "Version policy",
    "Source",
    "Basis IDs",
    "Alternatives and rationale",
    "Compatibility/migration",
    "Validation",
)
REQUIRED_TECHNOLOGY_CONCERNS = (
    "APPLICATION_RUNTIME",
    "APPLICATION_FRAMEWORK",
    "FRONTEND_FRAMEWORK",
    "INFRASTRUCTURE_AS_CODE",
    "PACKAGE_BUILD_TOOLING",
    "TEST_TOOLING",
    "PROPERTY_TESTING",
    "SECURITY_VALIDATION",
    "DEPLOYMENT_TOOLING",
)
TECHNOLOGY_DECISION_ID = re.compile(r"TECH-\d{4}")
TECHNOLOGY_CONCERN = re.compile(r"[A-Z][A-Z0-9_]*")
STABLE_CONTRACT_ID = re.compile(
    r"[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}"
)
TECHNOLOGY_SOURCES = {
    "OWNER_CONSTRAINT",
    "REPOSITORY_FACT",
    "AGENT_RECOMMENDATION",
}
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
ARCHITECTURE_TRACEABILITY_HEADERS = (
    "Requirement ID",
    "ARCH / COMP / API / DATA / CTRL IDs",
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
ARCHITECTURE_ID = re.compile(r"ARCH-\d{4,}")
ARCHITECTURE_DESIGN_ID = re.compile(r"(?:ARCH|COMP|API|DATA|CTRL)-\d{3,}")
ARCHITECTURE_TEST_ID = re.compile(r"(?:PROP|EX|TEST)-\d{3,}")
AWS_MATERIAL_EVIDENCE_ID = re.compile(r"AWS-EV-\d{4,}")
AWS_DISCOVERY_ID = re.compile(r"AWS-DISC-\d{4,}")
ARCHITECTURE_DRIVER_CLASSES = {"HARD_CONSTRAINT", "PREFERENCE", "REVISIT_TRIGGER"}
ARCHITECTURE_ELIGIBILITY = {"ELIGIBLE", "INELIGIBLE"}
AWS_DOCUMENTATION_CAPABILITIES = {"retrieve_skill", "search_documentation"}
NORMATIVE_REQUIREMENT_HEADERS = (
    "ID",
    "Requirement",
    "EARS form",
    "Acceptance criteria",
    "Acceptance form",
)
LEGACY_REQUIREMENT_HEADERS = ("ID", "Requirement", "Acceptance criteria")
EARS_FORMS = {
    "UBIQUITOUS",
    "EVENT_DRIVEN",
    "STATE_DRIVEN",
    "UNWANTED_BEHAVIOR",
    "OPTIONAL_FEATURE",
    "COMPLEX",
}
# The Fastlane EARS Contract is a project-local normative schema. It does not
# redefine EARS outside this template.
EARS_PATTERNS = {
    "UBIQUITOUS": re.compile(
        r"The (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "EVENT_DRIVEN": re.compile(
        r"WHEN (?P<trigger>.+), the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "STATE_DRIVEN": re.compile(
        r"WHILE (?P<state>.+), the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "UNWANTED_BEHAVIOR": re.compile(
        r"IF (?P<condition>.+), THEN the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "OPTIONAL_FEATURE": re.compile(
        r"WHERE (?P<feature>.+), the (?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
    "COMPLEX": re.compile(
        r"WHILE (?P<state>.+), WHEN (?P<trigger>.+), the "
        r"(?P<subject>.+?) SHALL (?P<response>.+)\."
    ),
}
CONCRETE_SUBJECT = re.compile(r"[A-Za-z][A-Za-z0-9 _./'()-]*")
NON_CONCRETE_SUBJECTS = {
    "it",
    "something",
    "thing",
    "system subject",
    "placeholder",
    "unknown",
}
ACCEPTANCE_FORMS = {"GHERKIN", "MEASURABLE"}
GHERKIN_ACCEPTANCE = re.compile(
    r"GIVEN (?P<precondition>.+), WHEN (?P<trigger>.+), THEN (?P<result>.+)\."
)
MEASURABLE_EXPECTED_RESULT = re.compile(
    r"\b(?:allow|allows|cite|cites|contain|contains|confirm|confirms|cover|covers|"
    r"demonstrate|demonstrates|deny|denied|equal|equals|exceed|exceeds|fail|fails|find|finds|"
    r"identify|identifies|link|links|map|maps|match|matches|meet|meets|name|names|"
    r"pass|passes|preserve|preserves|prove|proves|record|records|reject|rejects|"
    r"restore|restores|show|shows|stay|stays|succeed|succeeds)\b|"
    r"(?:<=|>=|==|<|>)",
    re.IGNORECASE,
)
MEASURABLE_BINDING = re.compile(
    r"\b(?:at least|at most|bounded|calculation|configured|configuration|"
    r"every|each|exact|exactly|maximum|minimum|normal and peak|policy|"
    r"percentile|RPO|RTO|threshold|time-bounded|zero|one|all five|bound|"
    r"generated-case bound|pass condition|traceability check|runbook check|"
    r"owner decision|observed measurement|recorded [A-Za-z0-9 -]+ boundary|"
    r"approved (?:[A-Za-z0-9-]+ )?(?:boundary|case|control|environment|limit|"
    r"outcome|requirement|result|target|trigger|workload))\b|"
    r"\b(?:TEST|PROP|EV)-\d{3,}\b|"
    r"`[^`\r\n]+`|"
    r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/\S+|"
    r"\b(?:python|pytest|npm|pnpm|yarn|cargo|go test|dotnet test)\b|"
    r"\d+(?:\.\d+)?\s*(?:%|ms|s|seconds?|minutes?|hours?|requests?/s)?",
    re.IGNORECASE,
)
UNDEFINED_QUALITY_TERM = re.compile(
    r"\b(?:fast|secure|scalable|user[- ]friendly|appropriate)\b",
    re.IGNORECASE,
)
QAS_HEADERS = (
    "QAS ID", "Requirement IDs", "Source", "Stimulus", "Environment",
    "Artifact", "Response", "Response measure",
)
QAS_ID = re.compile(r"QAS-\d{3,}")
HARNESS_HEADING = "### Gate B Harness Profile"
HARNESS_HEADERS = (
    "Harness ID",
    "Layer",
    "Selected check or tool",
    "Trigger",
    "Basis IDs",
    "Exact command or API",
    "Evidence destination",
    "Required or conditional status",
)
HARNESS_ID = re.compile(r"HARNESS-\d{3,}")
HARNESS_LAYERS = {
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
}
HARNESS_EVIDENCE_DESTINATION = (
    "docs/project/VERIFY.md#harness-execution-evidence"
)
MANAGED_SERVERLESS_MARKER = "MANAGED_SERVERLESS_BASELINE:"
PROPERTY_EXECUTION_HEADING = "### Property execution contract"
PROPERTY_EXECUTION_HEADERS = (
    "Property ID",
    "Framework TECH ID",
    "Exact command",
    "Run target/time bound",
    "Seed or reproduction format",
    "Evidence destination",
)
PROPERTY_APPLICABILITY_HEADERS = (
    "Requirement ID",
    "Applicability",
    "Reason or property IDs",
)
PROPERTY_DEFINITION_HEADERS = (
    "Property ID",
    "Requirement IDs",
    "Invariant",
    "Generated inputs or state",
    "Preconditions",
    "Oracle",
    "Boundary or shrink focus",
    "Layer",
)
PROPERTY_SPECIFICATION_HEADING = "## 24. Property-based testing specification"
PROPERTY_ID = re.compile(r"PROP-\d{3,}")
PROPERTY_TEST_EVIDENCE_HEADING = "## Property-based test evidence"
PROPERTY_TEST_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Task ID",
    "REQ / DES / AUTH",
    "Property ID",
    "Framework TECH ID",
    "Framework selection",
    "Observed exact version",
    "Exact command",
    "Observed run",
    "Replay seed or exact command",
    "Minimized counterexample",
    "Failure class / resolution",
    "Result",
    "Observed at",
    "Commit / worktree / artifact",
    "Durable source",
)
PROPERTY_TEST_EVIDENCE_DESTINATION = (
    "docs/project/VERIFY.md#property-based-test-evidence"
)
PROPERTY_TEST_RESULTS = {"NOT_STARTED", "PASS", "FAIL"}
PROPERTY_TEST_FAILURE_CLASSES = {
    "IMPLEMENTATION_DEFECT",
    "SPECIFICATION_AMBIGUITY_OR_DEFECT",
    "GENERATOR_OR_ORACLE_DEFECT",
    "ENVIRONMENT_DEFECT",
}
PROPERTY_COMMAND_EXECUTABLE = re.compile(
    r"(?:[a-z0-9][a-z0-9_.+-]*|\.{0,2}/[A-Za-z0-9_./+-]+|/[A-Za-z0-9_./+-]+)"
)
PROPERTY_COMMAND_PROSE_VERBS = {
    "check",
    "execute",
    "record",
    "run",
    "test",
    "use",
    "validate",
    "verify",
}
GATE_A_STATES = {
    "BLOCKED",
    "PENDING_OWNER_APPROVAL",
    "APPROVED_FOR_DESIGN",
    "STALE",
}
GATE_B_STATES = {
    "BLOCKED",
    "PENDING_OWNER_APPROVAL",
    "APPROVED_FOR_CONSTRUCTION",
    "STALE",
}
RUN_MODES = {"NONE", "SINGLE_TASK", "AUTONOMOUS"}
RUN_STATES = {"IDLE", "RUNNING", "CHECKPOINTED", "BLOCKED", "COMPLETE"}
BROWNFIELD_STATES = {"UNASSESSED", "NOT_APPLICABLE", "RECORDED", "STALE"}
CANONICAL_PLACEHOLDERS = {
    "My AWS Project",
    "{{AWS_REGION}}",
    "{{COST_POSTURE}}",
    "{{SETUP_METHOD}}",
    "{{SETUP_STATUS}}",
}
MANDATORY_REQUIRED_FILES = {
    ".github/ISSUE_TEMPLATE/aws-vertical-slice.yml",
    ".github/ISSUE_TEMPLATE/bugfix.yml",
    ".github/ISSUE_TEMPLATE/waf-risk.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".gitignore",
    ".agents/skills/build-fastlane/SKILL.md",
    ".agents/skills/explain-fastlane/SKILL.md",
    ".agents/skills/fastlane/SKILL.md",
    ".agents/skills/launch-fastlane/SKILL.md",
    ".agents/skills/maintain-fastlane/SKILL.md",
    ".agents/skills/operate-fastlane-aws/SKILL.md",
    ".agents/skills/plan-fastlane/SKILL.md",
    "AGENTS.md",
    BUGFIX_FILE,
    "LICENSE",
    PRD_FILE,
    "README.md",
    RUNBOOK_FILE,
    "SECURITY.md",
    TASKS_FILE,
    VERIFY_FILE,
    "app/AGENTS.md",
    "bootstrap.manifest.json",
    "bootstrap.py",
    "bootstrap.yaml",
    "docs/adr/0000-template.md",
    "docs/DEPENDENCY-POLICY.md",
    "docs/SETUP.md",
    "docs/TROUBLESHOOTING.md",
    "docs/WORKFLOW.md",
    "infrastructure/AGENTS.md",
    "prompts/CODEX-PROMPTS.md",
    "scripts/bootstrap_doctor.py",
    "scripts/bootstrap_dependencies.py",
    "scripts/setup_assistant.py",
    "scripts/task_waves.py",
    "tests/AGENTS.md",
}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    path: str | None = None
    severity: str = "ERROR"

    def to_dict(self, diagnostic_id: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if diagnostic_id is not None:
            result["diagnostic_id"] = diagnostic_id
        if self.path is not None:
            result["path"] = self.path
        return result


@dataclass
class Context:
    root: Path
    template_source: bool = False
    diagnostics: list[Diagnostic] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)

    def error(self, code: str, message: str, path: str | None = None) -> None:
        self.diagnostics.append(Diagnostic(code, message, path))

    def warning(self, code: str, message: str, path: str | None = None) -> None:
        self.diagnostics.append(Diagnostic(code, message, path, "WARNING"))

    @property
    def has_errors(self) -> bool:
        return any(item.severity == "ERROR" for item in self.diagnostics)


@dataclass
class TaskSummary:
    plan_revision: str | None = None
    plan_state: str = "UNINITIALIZED"
    statuses: dict[str, str] = field(default_factory=dict)
    ready: list[str] = field(default_factory=list)
    active: list[str] = field(default_factory=list)
    write_sets: dict[str, list[str]] = field(default_factory=dict)
    attempts_used: dict[str, int] = field(default_factory=dict)
    attempt_budgets: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.statuses)

    @property
    def done(self) -> list[str]:
        return sorted(
            task_id for task_id, status in self.statuses.items() if status == "DONE"
        )

    @property
    def skipped(self) -> list[str]:
        return sorted(
            task_id for task_id, status in self.statuses.items() if status == "SKIPPED"
        )

    @property
    def blocked(self) -> list[str]:
        return sorted(
            task_id for task_id, status in self.statuses.items() if status == "BLOCKED"
        )

    @property
    def terminal(self) -> bool:
        return bool(self.statuses) and all(
            status in {"DONE", "SKIPPED"} for status in self.statuses.values()
        )


@dataclass(frozen=True)
class ContractTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    canonical_bytes: bytes


@dataclass(frozen=True)
class CoverageOmission:
    section: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"section": self.section, "reason": self.reason}


@dataclass(frozen=True)
class CoverageContract:
    schema_version: int = 1
    status: str = "UNINITIALIZED"
    work_kind: str | None = None
    delivery_profile: str | None = None
    architecture_disposition: str | None = None
    required_sections: tuple[str, ...] = ()
    omissions: tuple[CoverageOmission, ...] = ()
    basis_ids: tuple[str, ...] = ()
    canonical_sha256: str | None = None
    compatibility_full_coverage: bool = False
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "work_kind": self.work_kind,
            "delivery_profile": self.delivery_profile,
            "architecture_disposition": self.architecture_disposition,
            "required_sections": list(self.required_sections),
            "omissions": [item.to_dict() for item in self.omissions],
            "basis_ids": list(self.basis_ids),
            "canonical_sha256": self.canonical_sha256,
            "compatibility_full_coverage": self.compatibility_full_coverage,
        }


@dataclass(frozen=True)
class ChangeImpactRow:
    change_id: str
    changed_basis_ids: str
    affected_ids: str
    preserved_ids: str
    required_revalidation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "change_id": self.change_id,
            "changed_basis_ids": self.changed_basis_ids,
            "affected_ids": self.affected_ids,
            "preserved_ids": self.preserved_ids,
            "required_revalidation": self.required_revalidation,
        }


@dataclass(frozen=True)
class ChangeImpactContract:
    schema_version: int = 1
    status: str = "UNINITIALIZED"
    rows: tuple[ChangeImpactRow, ...] = ()
    stale_targets: tuple[str, ...] = ()
    canonical_sha256: str | None = None
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "rows": [row.to_dict() for row in self.rows],
            "stale_targets": list(self.stale_targets),
            "canonical_sha256": self.canonical_sha256,
        }


@dataclass(frozen=True)
class TechnologyDecision:
    decision_id: str
    concern: str
    selection: str
    version_policy: str
    source: str
    basis_ids: str
    alternatives_and_rationale: str
    compatibility_migration: str
    validation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "decision_id": self.decision_id,
            "concern": self.concern,
            "selection": self.selection,
            "version_policy": self.version_policy,
            "source": self.source,
            "basis_ids": self.basis_ids,
            "alternatives_and_rationale": self.alternatives_and_rationale,
            "compatibility_migration": self.compatibility_migration,
            "validation": self.validation,
        }


@dataclass(frozen=True)
class PropertyExecution:
    property_id: str
    framework_tech_id: str
    exact_command: str
    run_target_time_bound: str
    seed_or_reproduction_format: str
    evidence_destination: str

    def to_dict(self) -> dict[str, str]:
        return {
            "property_id": self.property_id,
            "framework_tech_id": self.framework_tech_id,
            "exact_command": self.exact_command,
            "run_target_time_bound": self.run_target_time_bound,
            "seed_or_reproduction_format": self.seed_or_reproduction_format,
            "evidence_destination": self.evidence_destination,
        }


@dataclass(frozen=True)
class ArchitectureDriver:
    driver_id: str
    requirement_basis: str
    driver_class: str
    decision_implication: str
    validation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "driver_id": self.driver_id,
            "requirement_basis": self.requirement_basis,
            "class": self.driver_class,
            "decision_implication": self.decision_implication,
            "validation": self.validation,
        }


@dataclass(frozen=True)
class ArchitectureCandidate:
    candidate_id: str
    architecture_summary: str
    requirement_coverage: str
    aws_evidence: str
    eligibility: str
    failed_constraints: str
    tradeoffs: str

    def to_dict(self) -> dict[str, str]:
        return {
            "candidate_id": self.candidate_id,
            "architecture_summary": self.architecture_summary,
            "requirement_coverage": self.requirement_coverage,
            "aws_evidence": self.aws_evidence,
            "eligibility": self.eligibility,
            "failed_constraints": self.failed_constraints,
            "tradeoffs": self.tradeoffs,
        }


@dataclass(frozen=True)
class ArchitectureSelection:
    architecture_id: str
    selected_candidate: str
    requirement_and_driver_basis: str
    rationale: str
    rejected_alternatives: str
    risks: str
    mitigations: str
    security_impact: str
    reliability_impact: str
    operational_burden: str
    cost_effect: str
    breakpoints: str
    migration_path: str
    revisit_triggers: str
    validation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "architecture_id": self.architecture_id,
            "selected_candidate": self.selected_candidate,
            "requirement_and_driver_basis": self.requirement_and_driver_basis,
            "rationale": self.rationale,
            "rejected_alternatives": self.rejected_alternatives,
            "risks": self.risks,
            "mitigations": self.mitigations,
            "security_impact": self.security_impact,
            "reliability_impact": self.reliability_impact,
            "operational_burden": self.operational_burden,
            "cost_effect": self.cost_effect,
            "breakpoints": self.breakpoints,
            "migration_path": self.migration_path,
            "revisit_triggers": self.revisit_triggers,
            "validation": self.validation,
        }


@dataclass(frozen=True)
class ArchitectureTrace:
    requirement_id: str
    design_ids: str
    property_test_ids: str
    evidence_ids: str

    def to_dict(self) -> dict[str, str]:
        return {
            "requirement_id": self.requirement_id,
            "design_ids": self.design_ids,
            "property_test_ids": self.property_test_ids,
            "evidence_ids": self.evidence_ids,
        }


@dataclass(frozen=True)
class MaterialAwsEvidence:
    evidence_id: str
    discovery_id: str
    design_ids: str
    material_claim: str
    capability: str
    official_reference: str
    observed_date: str

    def to_dict(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "discovery_id": self.discovery_id,
            "design_ids": self.design_ids,
            "material_claim": self.material_claim,
            "capability": self.capability,
            "official_reference": self.official_reference,
            "observed_date": self.observed_date,
        }


@dataclass(frozen=True)
class HarnessRow:
    harness_id: str
    layer: str
    selected_check: str
    trigger: str
    basis_ids: str
    exact_command: str
    evidence_destination: str
    requirement_status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "harness_id": self.harness_id,
            "layer": self.layer,
            "selected_check": self.selected_check,
            "trigger": self.trigger,
            "basis_ids": self.basis_ids,
            "exact_command": self.exact_command,
            "evidence_destination": self.evidence_destination,
            "requirement_status": self.requirement_status,
        }


@dataclass(frozen=True)
class HarnessContract:
    schema_version: int = 1
    status: str = "UNINITIALIZED"
    rows: tuple[HarnessRow, ...] = ()
    required_ids: tuple[str, ...] = ()
    canonical_sha256: str | None = None
    grandfathered_v1: bool = False
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "rows": [row.to_dict() for row in self.rows],
            "required_ids": list(self.required_ids),
            "canonical_sha256": self.canonical_sha256,
            "grandfathered_v1": self.grandfathered_v1,
        }


@dataclass(frozen=True)
class ArchitectureContract:
    schema_version: int = 1
    status: str = "UNINITIALIZED"
    drivers: tuple[ArchitectureDriver, ...] = ()
    candidates: tuple[ArchitectureCandidate, ...] = ()
    selection: ArchitectureSelection | None = None
    traceability: tuple[ArchitectureTrace, ...] = ()
    aws_evidence: tuple[MaterialAwsEvidence, ...] = ()
    canonical_sha256: str | None = None
    grandfathered_v1: bool = False
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "drivers": [item.to_dict() for item in self.drivers],
            "candidates": [item.to_dict() for item in self.candidates],
            "selection": self.selection.to_dict() if self.selection else None,
            "traceability": [item.to_dict() for item in self.traceability],
            "aws_evidence": [item.to_dict() for item in self.aws_evidence],
            "canonical_sha256": self.canonical_sha256,
            "grandfathered_v1": self.grandfathered_v1,
        }


@dataclass(frozen=True)
class DesignContract:
    schema_version: int = 1
    status: str = "UNINITIALIZED"
    design_revision: str | None = None
    technology_decisions: tuple[TechnologyDecision, ...] = ()
    property_execution: tuple[PropertyExecution, ...] = ()
    architecture: ArchitectureContract = field(default_factory=ArchitectureContract)
    harness: HarnessContract = field(default_factory=HarnessContract)
    change_impact: ChangeImpactContract = field(default_factory=ChangeImpactContract)
    canonical_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "design_revision": self.design_revision,
            "technology_decisions": [item.to_dict() for item in self.technology_decisions],
            "property_execution": [item.to_dict() for item in self.property_execution],
            "architecture": self.architecture.to_dict(),
            "harness": self.harness.to_dict(),
            "change_impact": self.change_impact.to_dict(),
            "canonical_sha256": self.canonical_sha256,
        }


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
TASK_AWS_MODES = {"NONE", "DOCS_ONLY", "READ_ONLY", "MUTATION"}
TASK_DESIGN_TRACE_PATTERN = re.compile(
    r"^(?P<design>DES-\d{4}); TECH: "
    r"(?:(?P<none>NONE — no technology/toolchain impact)|"
    r"(?P<technologies>TECH-\d{4}(?:, TECH-\d{4})*))$"
)
EVIDENCE_PATTERN = re.compile(
    r"(?:\b(?:EV|EVIDENCE)-[A-Z0-9][A-Z0-9._-]*\b|"
    r"\bVERIFY\.md#[A-Za-z0-9._-]+\b|https?://\S+)",
    re.IGNORECASE,
)
LOCAL_EVIDENCE_ID = re.compile(r"\bEV-\d{4,}\b")
LOCAL_EVIDENCE_LIKE = re.compile(r"\b(?:EV|EVIDENCE)-[A-Za-z0-9._-]+\b", re.IGNORECASE)
TASK_COMPLETION_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Task",
    "Command or observation",
    "Result",
    "Actor",
    "Observed at",
    "Commit / worktree / artifact",
    "Durable source",
    "Status",
)
TASK_COMPLETION_EVIDENCE_STATUSES = {"LOCAL_PASS", "VERIFIED"}
EVIDENCE_PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:TODO|TBD|TBC|UNKNOWN|UNASSIGNED|PENDING|PLACEHOLDER|"
    r"NOT[ _-]*STARTED|NONE|N/?A)\b|<[^>]+>",
    re.IGNORECASE,
)
UNRESOLVED_TOKEN = re.compile(
    r"(?<![A-Z0-9])(?:TODO|TBD|TBC|UNKNOWN|UNASSIGNED)(?![A-Z0-9])",
    re.IGNORECASE,
)
CHECKPOINT_HEADERS = (
    "Checkpoint",
    "Run",
    "Time",
    "REQ / DES / AUTH",
    "Commit and protected dirty paths",
    "Task outcomes and attempts",
    "Evidence and external actions",
    "Blockers and next safe action",
)
SNAPSHOT_FIELDS = {
    "Task-plan revision",
    "Task-plan state",
    "Requirements revision",
    "Design revision",
    "Construction authorization",
    "Gate B state",
    "Run state",
    "Active run ID",
    "Baseline commit",
    "Protected dirty paths",
    "Coordinator",
    "Maximum workers",
    "Current wave",
    "Last checkpoint",
    "Last known-green commit",
    "Next safe action",
}
SNAPSHOT_RUN_STATES = {"NOT_STARTED", "RUNNING", "PAUSED", "BLOCKED", "COMPLETE"}
GITHUB_BOUNDARIES = {"NONE", "READ_ONLY", "ISSUES", "BRANCH_AND_PR", "MERGE_WHEN_GREEN"}
AWS_BOUNDARIES = {"NONE", "DOCS_ONLY", "READ_ONLY", "MUTATE_LISTED_RESOURCES"}
AWS_DETAIL_FIELDS = {
    "AWS account",
    "AWS role or profile",
    "AWS Region",
    "AWS environment",
    "AWS stack or application",
    "AWS resource allowlist",
    "AWS allowed operations",
    "AWS cost ceiling",
    "AWS prohibited operations",
    "AWS artifact authorization and provenance",
    "AWS rollback boundary",
    "AWS authorization validity",
}
CONTROL_HASH_FILES = {
    "bootstrap.py",
    "scripts/bootstrap_dependencies.py",
    "scripts/bootstrap_doctor.py",
    "scripts/setup_assistant.py",
    "scripts/task_waves.py",
}
COORDINATOR_LEDGER_PATHS = {TASKS_FILE, VERIFY_FILE, STATE_FILE}
AUTHORIZED_ID = re.compile(r"[A-Z][A-Z0-9_]*-\d+")
ID_LIKE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*-\d+\b")
GITHUB_CONSTRAINT = re.compile(
    r"REPO: (?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+); "
    r"BRANCH: (?P<branch>[A-Za-z0-9._/-]+); MERGE: (?P<merge>ALLOWED|PROHIBITED)"
)
GITHUB_ISSUE_URL = re.compile(
    r"https://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/[1-9]\d*"
)
AWS_ENVIRONMENT = re.compile(
    r"ENVIRONMENT: (?P<name>[^;\r\n]+); CLASS: (?P<class>NON_PRODUCTION|PRODUCTION)"
)
AWS_EXACT_ARTIFACT = re.compile(r"EXACT_DIGEST: sha256:[0-9a-f]{64}")
AWS_DERIVED_ARTIFACT = re.compile(
    r"DERIVED_FROM_AUTHORIZED_SOURCE: (?P<rule>[^\r\n]+)"
)
TASK_BOUNDARY_DERIVED = "DERIVED_FROM_AUTHORIZED_IDS_AND_WRITE_SET"
SHELL_CONTROL = re.compile(r"[;&|><`$()\\\r\n]")
NON_HUMAN_APPROVER = re.compile(
    r"(?:^|[^a-z0-9])(?:ai|agent|assistant|automated|automation|bot|chatbot|"
    r"chatgpt|codex|gpt(?:-[0-9]+)?|llm|model|openai|robot|system|workflow|"
    r"service[ _-]*account|pending|placeholder|not[ _-]*started)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
ENVELOPE_EXPLICIT_FIELDS = {
    "Project mode",
    "Delivery profile and effective risk",
    "Project AWS lane",
    "Authorized outcome",
    "Authorized requirement and design IDs",
    "Design contract SHA-256",
    "Authorized baseline commit",
    "Protected dirty paths",
    "In-scope components and environments",
    "Allowed repository write set",
    "Excluded or owner-only write set",
    "Allowed external-state targets",
    "Task boundary",
    "Parallelism rule",
    "Checkpoint cadence",
    "Required checkpoint contents",
    "Local command boundary",
    "GitHub repository, branch, and merge constraints",
    *AWS_DETAIL_FIELDS,
    "Rollback, recovery, and teardown boundary",
    "Mandatory stop conditions",
    "Authorization expiry or completion condition",
}
BROWNFIELD_BASELINE_FIELDS = {
    "Repository and baseline commit",
    "Deployed environments and observed versions",
    "Existing architecture and ownership",
    "Current interfaces, schemas, and consumers",
    "Current data stores and migration constraints",
    "Existing security and compliance controls",
    "Baseline verification commands",
    "Baseline evidence location",
    "Known defects and accepted debt",
    "Repository-to-environment drift",
    "Dirty or user-owned working-tree changes",
    "Protected files and components",
    "Unresolved bootstrap overlay collisions",
}
GATE_A_READINESS_FIELDS = {
    "Outcome",
    "Owner and users",
    "Scope and non-goals",
    "Measurable requirement/acceptance IDs",
    "Data boundary",
    "Identity/security boundary",
    "Environment/Region",
    "Failure/recovery",
    "Cost posture",
    "Intake provenance",
}
GATE_B_READINESS_FIELDS = {
    "Design basis IDs",
    "Architecture/components",
    "Technology/toolchains/version policy",
    "Interfaces/data flow",
    "Identity/secrets",
    "Failure/retry/concurrency",
    "Deployment/operations",
    "Validation/evidence",
    "Rollback/recovery/teardown",
    "Brownfield compatibility/migration",
    "Outstanding gaps",
}
AWS_CORE_EVIDENCE_HEADERS = (
    "Phase",
    "Discovery ID",
    "Basis IDs",
    "Plugin source",
    "Invoked plugin identity",
    "Observed plugin version",
    "Capability",
    "Observation actor",
    "Requested skill",
    "Returned skill identifier",
    "Documentation query",
    "Discovered skill identifiers",
    "Source references",
    "Advisory Design binding",
    "Credentials inspected",
    "AWS account accessed",
    "Observed at",
    "Evidence binding",
    "Observed status",
)
AWS_CORE_EVIDENCE_HEADERS_V1 = tuple(
    header for header in AWS_CORE_EVIDENCE_HEADERS
    if header not in {"Discovery ID", "Basis IDs", "Discovered skill identifiers"}
)
AWS_CORE_EVIDENCE_PHASES = ("DESIGN-10", "AWS-10")
AWS_CORE_REQUIRED_CAPABILITIES = ("search_documentation", "retrieve_skill")
AWS_CORE_OFFICIAL_SOURCE = "aws/agent-toolkit-for-aws"
AWS_CORE_OFFICIAL_IDENTITY = "aws-core@agent-toolkit-for-aws"
AWS_CORE_OBSERVATION_ACTOR = "CODEX_LIVE_TOOL_CALL"
AWS_CORE_PLUGIN_VERSION_PATTERN = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
)
AWS_CORE_CANONICAL_SKILL_IDENTIFIER_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:/@-]*"
)
AWS_CORE_OFFICIAL_DOCUMENTATION_REFERENCE_PATTERN = re.compile(
    r"https://(?:docs\.aws\.amazon\.com|aws\.amazon\.com)/\S+",
    re.IGNORECASE,
)
AWS_CORE_EVIDENCE_STATUSES = {
    "NOT_STARTED",
    "PASS",
    "VERIFIED",
    "FAILED",
    "BLOCKED",
    "STALE",
}


@dataclass
class InspectedTask:
    task_id: str
    title: str
    block: str
    metadata: dict[str, str]
    duplicates: set[str]

    @property
    def status(self) -> str:
        return clean_cell(self.metadata.get("Status", "")).upper()

    @property
    def dependencies(self) -> list[str]:
        raw = clean_cell(self.metadata.get("Depends on", "NONE"))
        return [] if raw in {"", "NONE", "-"} else [item.strip() for item in raw.split(",")]

    @property
    def attempts_used(self) -> int:
        return int(clean_cell(self.metadata["Attempts used"]))

    @property
    def attempt_budget(self) -> int:
        return int(clean_cell(self.metadata["Attempt budget"]))


@dataclass(frozen=True)
class TaskCompletionEvidenceRow:
    evidence_id: str
    task_id: str
    command_or_observation: str
    result: str
    actor: str
    observed_at: str
    commit_worktree_artifact: str
    durable_source: str
    status: str


@dataclass(frozen=True)
class PropertyTestEvidenceRow:
    evidence_id: str
    task_id: str
    requirements_design_authorization: str
    property_id: str
    framework_tech_id: str
    framework_selection: str
    observed_exact_version: str
    exact_command: str
    observed_run: str
    replay_seed_or_exact_command: str
    minimized_counterexample: str
    failure_class_resolution: str
    result: str
    observed_at: str
    commit_worktree_artifact: str
    durable_source: str


@dataclass(frozen=True)
class AwsCoreEvidenceRow:
    phase: str
    discovery_id: str
    basis_ids: str
    plugin_source: str
    invoked_plugin_identity: str
    observed_plugin_version: str
    capability: str
    observation_actor: str
    requested_skill: str
    returned_skill_identifier: str
    documentation_query: str
    discovered_skill_identifiers: str
    source_references: str
    advisory_design_binding: str
    credentials_inspected: str
    aws_account_accessed: str
    observed_at: str
    evidence_binding: str
    observed_status: str


@dataclass(frozen=True)
class CheckpointReceiptRow:
    checkpoint_id: str
    run_id: str
    recorded_at: str
    basis: str
    commit_and_dirty: str
    task_outcomes: str
    evidence_and_external: str
    blockers_and_next: str


def without_fenced_code(text: str) -> str:
    """Hide fenced examples while preserving offsets for structural parsing."""

    result: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = "```" if stripped.startswith("```") else "~~~" if stripped.startswith("~~~") else None
        if marker is not None:
            fence = None if fence == marker else marker if fence is None else fence
            result.append(" " * (len(line.rstrip("\r\n"))) + line[len(line.rstrip("\r\n")) :])
        elif fence is None:
            result.append(line)
        else:
            result.append(" " * (len(line.rstrip("\r\n"))) + line[len(line.rstrip("\r\n")) :])
    return "".join(result)


def inspect_task_blocks(text: str) -> list[InspectedTask]:
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
        tasks.append(InspectedTask(match.group(1), match.group(2).strip(), block, metadata, duplicates))
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


def split_markdown_table_row(line: str) -> list[str] | None:
    """Split a pipe table row while honoring Markdown escaped pipes."""

    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in stripped[1:-1]:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def parse_task_completion_evidence(text: str) -> list[TaskCompletionEvidenceRow]:
    structural = without_fenced_code(text)
    headings = list(
        re.finditer(r"^## Task completion evidence[ \t]*$", structural, re.MULTILINE)
    )
    if len(headings) != 1:
        raise ValueError("VERIFY.md requires exactly one Task completion evidence section")
    following = re.search(r"^##\s+", structural[headings[0].end() :], re.MULTILINE)
    end = headings[0].end() + following.start() if following else len(structural)
    lines = structural[headings[0].end() : end].splitlines()
    header_indexes = [
        index
        for index, line in enumerate(lines)
        if split_markdown_table_row(line) == list(TASK_COMPLETION_EVIDENCE_HEADERS)
    ]
    if len(header_indexes) != 1:
        raise ValueError("VERIFY.md requires one exact Task completion evidence table")
    header = header_indexes[0]
    separator = split_markdown_table_row(lines[header + 1]) if header + 1 < len(lines) else None
    if (
        separator is None
        or len(separator) != len(TASK_COMPLETION_EVIDENCE_HEADERS)
        or any(re.fullmatch(r":?-{3,}:?", cell) is None for cell in separator)
    ):
        raise ValueError("VERIFY.md Task completion evidence separator is invalid")
    rows: list[TaskCompletionEvidenceRow] = []
    for line in lines[header + 2 :]:
        if not line.strip():
            if rows:
                break
            continue
        cells = split_markdown_table_row(line)
        if cells is None:
            if rows:
                break
            raise ValueError("VERIFY.md Task completion evidence row is missing")
        if len(cells) != len(TASK_COMPLETION_EVIDENCE_HEADERS):
            raise ValueError("VERIFY.md Task completion evidence row must have nine cells")
        row = TaskCompletionEvidenceRow(*(clean_cell(cell) for cell in cells))
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError("VERIFY.md Task completion Evidence ID must be EV-nnnn")
        rows.append(row)
    identifiers = [row.evidence_id for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("VERIFY.md Task completion Evidence IDs must be unique")
    return rows


def parse_aws_core_evidence(
    text: str,
    *,
    allow_legacy: bool = False,
) -> dict[tuple[str, str, str], AwsCoreEvidenceRow]:
    """Parse linked runtime skill-discovery evidence chains."""

    structural = without_fenced_code(text)
    headings = list(re.finditer(r"^## AWS Core evidence[ \t]*$", structural, re.MULTILINE))
    if len(headings) != 1:
        raise ValueError("VERIFY.md requires exactly one AWS Core evidence section")
    following = re.search(r"^##\s+", structural[headings[0].end() :], re.MULTILINE)
    end = headings[0].end() + following.start() if following else len(structural)
    lines = structural[headings[0].end() : end].splitlines()

    headers = AWS_CORE_EVIDENCE_HEADERS
    header_indexes = [
        index
        for index, line in enumerate(lines)
        if split_markdown_table_row(line) == list(headers)
    ]
    legacy = False
    if len(header_indexes) != 1 and allow_legacy:
        headers = AWS_CORE_EVIDENCE_HEADERS_V1
        header_indexes = [
            index
            for index, line in enumerate(lines)
            if split_markdown_table_row(line) == list(headers)
        ]
        legacy = len(header_indexes) == 1
    if len(header_indexes) != 1:
        raise ValueError("VERIFY.md requires one exact AWS Core evidence table")
    header = header_indexes[0]
    separator = split_markdown_table_row(lines[header + 1]) if header + 1 < len(lines) else None
    if (
        separator is None
        or len(separator) != len(headers)
        or any(re.fullmatch(r":?-{3,}:?", cell) is None for cell in separator)
    ):
        raise ValueError("VERIFY.md AWS Core evidence separator is invalid")

    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow] = {}
    discovery_phases: dict[str, str] = {}
    for line in lines[header + 2 :]:
        if not line.strip():
            if rows:
                break
            continue
        cells = split_markdown_table_row(line)
        if cells is None:
            if rows:
                break
            raise ValueError("VERIFY.md AWS Core evidence row is missing")
        if len(cells) != len(headers):
            raise ValueError(
                f"VERIFY.md AWS Core evidence row must have {len(headers)} cells"
            )
        cleaned = tuple(clean_cell(cell) for cell in cells)
        if legacy:
            row = AwsCoreEvidenceRow(
                cleaned[0],
                "",
                "",
                *cleaned[1:9],
                "",
                *cleaned[9:],
            )
        else:
            row = AwsCoreEvidenceRow(*cleaned)
        if row.phase not in AWS_CORE_EVIDENCE_PHASES:
            raise ValueError(f"VERIFY.md AWS Core evidence has unknown phase {row.phase!r}")
        capability = row.capability.replace("`", "").strip()
        if capability not in AWS_CORE_REQUIRED_CAPABILITIES:
            raise ValueError(
                f"{row.phase} AWS Core evidence has unknown capability {capability!r}"
            )
        if not legacy and AWS_DISCOVERY_ID.fullmatch(row.discovery_id) is None:
            raise ValueError(
                f"{row.phase} AWS Core evidence has invalid Discovery ID {row.discovery_id!r}"
            )
        owner = discovery_phases.setdefault(row.discovery_id, row.phase)
        if row.discovery_id and owner != row.phase:
            raise ValueError(
                f"{row.discovery_id} AWS Core discovery ID is reused across phases"
            )
        key = (row.phase, row.discovery_id, capability)
        if key in rows:
            raise ValueError(
                f"VERIFY.md AWS Core evidence duplicates {row.phase} "
                f"{row.discovery_id or 'legacy'} {capability}"
            )
        if row.observed_status not in AWS_CORE_EVIDENCE_STATUSES:
            raise ValueError(
                f"{row.phase} {capability} AWS Core evidence has invalid status"
            )
        rows[key] = row

    missing: list[str] = []
    for phase in AWS_CORE_EVIDENCE_PHASES:
        discovery_ids = sorted(
            {discovery_id for row_phase, discovery_id, _ in rows if row_phase == phase}
        )
        if not discovery_ids:
            missing.append(f"{phase} discovery chain")
            continue
        for discovery_id in discovery_ids:
            for capability in AWS_CORE_REQUIRED_CAPABILITIES:
                if (phase, discovery_id, capability) not in rows:
                    missing.append(
                        f"{phase} {discovery_id or 'legacy'} {capability}"
                    )
    if missing:
        raise ValueError(
            "VERIFY.md AWS Core evidence is missing linked rows: " + ", ".join(missing)
        )
    return rows

def validate_advisory_design_binding(
    value: str,
    phase: str,
    *,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
) -> None:
    cleaned = clean_cell(value)
    not_applicable_prefix = "NOT_APPLICABLE — "
    if cleaned.startswith(not_applicable_prefix):
        if phase != "AWS-10" or not explicit_value(
            cleaned[len(not_applicable_prefix) :], allow_none=False
        ):
            raise ValueError(
                f"{phase} Advisory Design binding has invalid NOT_APPLICABLE form"
            )
        return
    match = re.fullmatch(r"(?P<design>DES-\d{4,}); TECH: (?P<technology>.+)", cleaned)
    if match is None:
        raise ValueError(
            f"{phase} Advisory Design binding must use DES-nnnn; TECH: <TECH IDs> "
            "or DES-nnnn; TECH: NONE — <reason>"
        )
    design_revision = match.group("design")
    if (
        expected_design_revision is not None
        and design_revision != expected_design_revision
    ):
        raise ValueError(
            f"{phase} Advisory Design binding must reference {expected_design_revision}"
        )
    technology = match.group("technology")
    none_prefix = "NONE — "
    if technology.startswith(none_prefix):
        if not explicit_value(technology[len(none_prefix) :], allow_none=False):
            raise ValueError(
                f"{phase} Advisory Design binding requires a concrete NONE reason"
            )
        return
    identifiers = [item.strip() for item in technology.split(",")]
    if not identifiers or any(
        TECHNOLOGY_DECISION_ID.fullmatch(item) is None for item in identifiers
    ):
        raise ValueError(
            f"{phase} Advisory Design binding TECH values must be comma-separated TECH-nnnn IDs"
        )
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{phase} Advisory Design binding contains duplicate TECH IDs")
    if approved_tech_ids is not None:
        unknown = sorted(set(identifiers) - approved_tech_ids)
        if unknown:
            raise ValueError(
                f"{phase} Advisory Design binding references unapproved TECH IDs: "
                + ", ".join(unknown)
            )


def _unlinked_aws_core_phase_evidence_issues(
    rows: dict[tuple[str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    expected_binding: str | None = None,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
) -> list[str]:
    """Return deterministic reasons that current official evidence is not ready."""

    issues: list[str] = []
    observed_versions: set[str] = set()
    for capability in AWS_CORE_REQUIRED_CAPABILITIES:
        row = rows.get((phase, capability))
        label = f"{phase} {capability}"
        if row is None or row.observed_status not in {"PASS", "VERIFIED"}:
            issues.append(f"{label} requires fresh PASS evidence")
            continue
        if row.plugin_source != AWS_CORE_OFFICIAL_SOURCE:
            issues.append(
                f"{label} plugin source must be {AWS_CORE_OFFICIAL_SOURCE}"
            )
        if row.invoked_plugin_identity != AWS_CORE_OFFICIAL_IDENTITY:
            issues.append(
                f"{label} invoked plugin identity must be {AWS_CORE_OFFICIAL_IDENTITY}"
            )
        version = clean_cell(row.observed_plugin_version)
        if AWS_CORE_PLUGIN_VERSION_PATTERN.fullmatch(version) is None:
            issues.append(
                f"{label} Observed plugin version must be an observed semantic version"
            )
        else:
            observed_versions.add(version)
        if row.observation_actor != AWS_CORE_OBSERVATION_ACTOR:
            issues.append(
                f"{label} Observation actor must be {AWS_CORE_OBSERVATION_ACTOR}"
            )
        if row.credentials_inspected != "NO":
            issues.append(f"{label} Credentials inspected must be NO")
        if row.aws_account_accessed != "NO":
            issues.append(f"{label} AWS account accessed must be NO")
        try:
            validate_advisory_design_binding(
                row.advisory_design_binding,
                phase,
                expected_design_revision=expected_design_revision,
                approved_tech_ids=approved_tech_ids,
            )
        except ValueError as exc:
            issues.append(str(exc))
        if capability == "retrieve_skill":
            try:
                requested_skill = require_explicit_evidence_value(
                    row.requested_skill, f"{label} Requested skill"
                )
            except ValueError as exc:
                issues.append(str(exc))
            try:
                returned_identifier = require_explicit_evidence_value(
                    row.returned_skill_identifier,
                    f"{label} Returned skill identifier",
                )
            except ValueError as exc:
                issues.append(str(exc))
            else:
                if (
                    AWS_CORE_CANONICAL_SKILL_IDENTIFIER_PATTERN.fullmatch(
                        returned_identifier
                    )
                    is None
                ):
                    issues.append(
                        f"{label} Returned skill identifier must be canonical"
                    )
        else:
            try:
                documentation_query = require_explicit_evidence_value(
                    row.documentation_query, f"{label} Documentation query"
                )
            except ValueError as exc:
                issues.append(str(exc))
            try:
                source_references = require_explicit_evidence_value(
                    row.source_references, f"{label} Source references"
                )
            except ValueError as exc:
                issues.append(str(exc))
            else:
                if (
                    AWS_CORE_OFFICIAL_DOCUMENTATION_REFERENCE_PATTERN.search(
                        source_references
                    )
                    is None
                ):
                    issues.append(
                        f"{label} Source references must include returned "
                        "official AWS documentation"
                    )
        if not explicit_timestamp(row.observed_at):
            issues.append(f"{label} Observed at must be ISO 8601 with timezone")
        try:
            binding = require_explicit_evidence_value(
                row.evidence_binding, f"{label} Evidence binding"
            )
        except ValueError as exc:
            issues.append(str(exc))
        else:
            if expected_binding is not None and binding != clean_cell(expected_binding):
                issues.append(
                    f"{label} Evidence binding does not match current "
                    f"{clean_cell(expected_binding)}"
                )
    if len(observed_versions) > 1:
        issues.append(
            f"{phase} capability rows must record one observed plugin version"
        )
    return issues


def aws_core_phase_evidence_issues(
    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    expected_binding: str | None = None,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
    allow_legacy_discovery: bool = False,
) -> list[str]:
    """Validate ordered, source-attributed runtime skill-discovery chains."""

    discovery_ids = sorted(
        {discovery_id for row_phase, discovery_id, _ in rows if row_phase == phase}
    )
    if not discovery_ids:
        return [f"{phase} requires at least one AWS-DISC discovery chain"]
    if "" in discovery_ids:
        if not allow_legacy_discovery or len(discovery_ids) != 1:
            return [f"{phase} legacy AWS Core evidence requires discovery migration"]
        legacy = {
            (phase, capability): rows[(phase, "", capability)]
            for capability in AWS_CORE_REQUIRED_CAPABILITIES
            if (phase, "", capability) in rows
        }
        return _unlinked_aws_core_phase_evidence_issues(
            legacy,
            phase,
            expected_binding=expected_binding,
            expected_design_revision=expected_design_revision,
            approved_tech_ids=approved_tech_ids,
        )

    issues: list[str] = []
    for discovery_id in discovery_ids:
        chain = {
            (phase, capability): rows[(phase, discovery_id, capability)]
            for capability in AWS_CORE_REQUIRED_CAPABILITIES
            if (phase, discovery_id, capability) in rows
        }
        issues.extend(
            _unlinked_aws_core_phase_evidence_issues(
                chain,
                phase,
                expected_binding=expected_binding,
                expected_design_revision=expected_design_revision,
                approved_tech_ids=approved_tech_ids,
            )
        )
        search = chain.get((phase, "search_documentation"))
        retrieve = chain.get((phase, "retrieve_skill"))
        if search is None or retrieve is None:
            issues.append(f"{phase} {discovery_id} requires linked search and retrieve rows")
            continue

        try:
            basis_ids = _canonical_id_list(
                search.basis_ids,
                STABLE_CONTRACT_ID,
                f"{phase} {discovery_id} Basis IDs",
            )
        except ValueError as exc:
            issues.append(str(exc))
            basis_ids = []
        if expected_design_revision and expected_design_revision not in basis_ids:
            issues.append(
                f"{phase} {discovery_id} Basis IDs must include {expected_design_revision}"
            )

        try:
            discovered = _canonical_id_list(
                search.discovered_skill_identifiers,
                AWS_CORE_CANONICAL_SKILL_IDENTIFIER_PATTERN,
                f"{phase} {discovery_id} Discovered skill identifiers",
            )
        except ValueError as exc:
            issues.append(str(exc))
            discovered = []

        shared = (
            "basis_ids",
            "plugin_source",
            "invoked_plugin_identity",
            "observed_plugin_version",
            "observation_actor",
            "discovered_skill_identifiers",
            "advisory_design_binding",
            "credentials_inspected",
            "aws_account_accessed",
            "evidence_binding",
        )
        for field_name in shared:
            if getattr(search, field_name) != getattr(retrieve, field_name):
                issues.append(
                    f"{phase} {discovery_id} rows must share {field_name}"
                )
        if retrieve.requested_skill != retrieve.returned_skill_identifier:
            issues.append(
                f"{phase} {discovery_id} retrieved identifier must equal the selected identifier"
            )
        if retrieve.returned_skill_identifier not in discovered:
            issues.append(
                f"{phase} {discovery_id} retrieved identifier was not returned by search"
            )

        if explicit_timestamp(search.observed_at) and explicit_timestamp(retrieve.observed_at):
            searched_at = datetime.fromisoformat(search.observed_at.replace("Z", "+00:00"))
            retrieved_at = datetime.fromisoformat(retrieve.observed_at.replace("Z", "+00:00"))
            if retrieved_at < searched_at:
                issues.append(
                    f"{phase} {discovery_id} retrieve timestamp precedes search"
                )
    return issues


def require_aws_core_phase_evidence(
    ctx: Context,
    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    expected_binding: str | None = None,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
    allow_legacy_discovery: bool = False,
) -> None:
    """Block a phase boundary unless both official AWS Core calls are evidenced."""

    for issue in aws_core_phase_evidence_issues(
        rows,
        phase,
        expected_binding=expected_binding,
        expected_design_revision=expected_design_revision,
        approved_tech_ids=approved_tech_ids,
        allow_legacy_discovery=allow_legacy_discovery,
    ):
        ctx.error("AWS_CORE_EVIDENCE_REQUIRED", issue, VERIFY_FILE)


def require_explicit_evidence_value(value: str, label: str) -> str:
    cleaned = clean_cell(value)
    if (
        not cleaned
        or any(character in cleaned for character in "\r\n")
        or EVIDENCE_PLACEHOLDER_PATTERN.search(cleaned) is not None
    ):
        raise ValueError(f"{label} is unresolved or placeholder evidence")
    return cleaned


def require_durable_evidence_source(value: str, label: str) -> str:
    """Require one safe local, git, artifact, HTTPS, or S3 evidence reference."""

    source = require_explicit_evidence_value(value, label)
    candidate = re.sub(r"^artifact\s*:\s*", "", source, flags=re.IGNORECASE)
    candidate_path = candidate.split("#", 1)[0]
    path_source = bool(
        re.fullmatch(
            r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+(?:#[A-Za-z0-9._-]+)?",
            candidate,
        )
        and ".." not in PurePosixPath(candidate_path).parts
    )
    if (
        re.fullmatch(r"VERIFY\.md#[A-Za-z0-9._-]+", source) is None
        and re.fullmatch(r"git:[0-9a-fA-F]{7,64}", source, re.IGNORECASE)
        is None
        and re.fullmatch(r"(?:https?|s3)://\S+", source, re.IGNORECASE) is None
        and not path_source
    ):
        raise ValueError(f"{label} is not a local durable reference")
    return source


def validate_done_evidence(verify_text: str | None, task: InspectedTask) -> None:
    evidence = clean_cell(task.metadata.get("Evidence", ""))
    references = [match.group(0) for match in EVIDENCE_PATTERN.finditer(evidence)]
    local = [reference for reference in references if re.fullmatch(r"EV-\d{4,}", reference)]
    invalid_local = [
        reference
        for reference in references
        if LOCAL_EVIDENCE_LIKE.fullmatch(reference) is not None
        and re.fullmatch(r"EV-\d{4,}", reference) is None
    ]
    if invalid_local:
        raise ValueError(
            f"{task.task_id}: invalid local Evidence ID: {', '.join(invalid_local)}"
        )
    if not local:
        raise ValueError(f"{task.task_id}: DONE requires at least one local Evidence reference")
    if len(local) != len(set(local)):
        raise ValueError(f"{task.task_id}: local Evidence references must be unique")
    if verify_text is None:
        raise ValueError(f"{task.task_id}: local Evidence requires VERIFY.md")
    rows = parse_task_completion_evidence(verify_text)
    for reference in local:
        matching = [row for row in rows if row.evidence_id == reference]
        if len(matching) != 1:
            raise ValueError(
                f"{task.task_id}: Evidence is not recorded in VERIFY.md: {reference}"
            )
        row = matching[0]
        if row.task_id != task.task_id:
            raise ValueError(
                f"{task.task_id}: Evidence row names the wrong task {row.task_id!r}"
            )
        label = f"{task.task_id} Evidence {row.evidence_id}"
        require_explicit_evidence_value(row.command_or_observation, f"{label} command")
        require_explicit_evidence_value(row.result, f"{label} result")
        require_explicit_evidence_value(row.actor, f"{label} actor")
        if not explicit_timestamp(row.observed_at):
            raise ValueError(f"{label} observed time must be ISO 8601 with timezone")
        material = require_explicit_evidence_value(
            row.commit_worktree_artifact, f"{label} commit/worktree/artifact"
        )
        if (
            re.search(r"\b[0-9a-fA-F]{7,64}\b", material) is None
            and re.search(
                r"\b(?:worktree|artifact)\s*[:=]\s*\S+", material, re.IGNORECASE
            )
            is None
        ):
            raise ValueError(f"{label} requires an explicit commit, worktree, or artifact")
        require_durable_evidence_source(
            row.durable_source, f"{label} durable source"
        )
        if row.status not in TASK_COMPLETION_EVIDENCE_STATUSES:
            raise ValueError(f"{label} status must be LOCAL_PASS or VERIFIED")


def parse_task_write_set(value: str, task_id: str) -> list[str]:
    value = clean_cell(value)
    if value in {"", "TODO", "TBD", "UNKNOWN"}:
        raise ValueError(f"{task_id}: unresolved Write set")
    if value == "NONE":
        return []
    result: list[str] = []
    for item in (part.strip() for part in value.split(",")):
        broad = item.endswith("/**")
        base = item[:-3] if broad else item
        pure = PurePosixPath(base)
        if (
            not base
            or pure.is_absolute()
            or "\\" in item
            or any(part.casefold() in {"", ".", "..", ".git"} for part in pure.parts)
            or any(character in base for character in "*?[]{}")
            or pure.as_posix() != base
        ):
            raise ValueError(f"{task_id}: unsafe Write set entry {item!r}")
        result.append(item)
    if len(result) != len({item.casefold() for item in result}):
        raise ValueError(f"{task_id}: duplicate Write set entry")
    return result


def parse_task_external_state(value: str, task_id: str) -> list[str]:
    value = clean_cell(value)
    if value in {"", "TODO", "TBD", "UNKNOWN"}:
        raise ValueError(f"{task_id}: unresolved External state")
    if value == "NONE":
        return []
    values = [item.strip() for item in value.split(",")]
    if any(not item or any(character in item for character in "*?[]{}") for item in values):
        raise ValueError(f"{task_id}: ambiguous External state")
    if len(values) != len({item.casefold() for item in values}):
        raise ValueError(f"{task_id}: duplicate External state entry")
    return values


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
        if len(pair) != 2 or re.fullmatch(r"TASK-\d+", pair[0]) is None or re.fullmatch(
            r"WAIVER-\d+", pair[1]
        ) is None:
            raise ValueError(f"{task.task_id}: invalid dependency waiver {entry!r}")
        result[pair[0]] = pair[1]
    return result


def validate_task_records(
    text: str,
    snapshot: dict[str, str],
    verify_text: str | None = None,
    approved_tech_ids: set[str] | None = None,
    property_execution_by_id: dict[str, PropertyExecution] | None = None,
    technology_decisions_by_id: dict[str, TechnologyDecision] | None = None,
) -> tuple[list[InspectedTask], dict[str, InspectedTask], list[str]]:
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
        for property_id in PROPERTY_ID.findall(
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
            property_evidence_rows = parse_property_test_evidence(verify_text)
        except ValueError as exc:
            errors.append(str(exc))
    observed_property_evidence = any(
        row.result in {"PASS", "FAIL"} for row in property_evidence_rows
    )
    if done_property_ids or observed_property_evidence:
        if verify_text is None:
            errors.append("DONE property tasks require VERIFY.md property-test evidence")
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
        } or (
            task.status == "BACKLOG"
            and snapshot.get("Task-plan state") == "CURRENT"
        )
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
        for field, expected, pattern in (
            ("Requirements", current_req, REQ_ID),
            ("Authorization", current_auth, AUTH_ID),
        ):
            match = pattern.search(clean_cell(task.metadata.get(field, "")))
            if match is None or match.group(0) != expected:
                errors.append(f"{task.task_id}: {field} does not match current execution basis")
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
        if task.status in {"READY", "IN_PROGRESS"} and snapshot.get("Gate B state") != "APPROVED_FOR_CONSTRUCTION":
            errors.append(f"{task.task_id}: Gate B is not approved for construction")
        if task.status in {"READY", "IN_PROGRESS"} and snapshot.get("Task-plan state") != "CURRENT":
            errors.append(f"{task.task_id}: task plan is not CURRENT")
        try:
            parse_task_write_set(task.metadata.get("Write set", ""), task.task_id)
            parse_task_external_state(task.metadata.get("External state", ""), task.task_id)
        except ValueError as exc:
            errors.append(str(exc))
        run_id = clean_cell(task.metadata.get("Run ID", "NONE"))
        if task.status == "IN_PROGRESS":
            if (
                run_id != snapshot.get("Active run ID")
                or snapshot.get("Run state") != "RUNNING"
                or clean_cell(task.metadata.get("Owner", "")) in {"", "NONE", "UNASSIGNED"}
                or used < 1
                or CHECKPOINT_ID.fullmatch(clean_cell(task.metadata.get("Last checkpoint", ""))) is None
            ):
                errors.append(f"{task.task_id}: invalid IN_PROGRESS claim")
        elif run_id != "NONE":
            errors.append(f"{task.task_id}: non-IN_PROGRESS task must use Run ID NONE")
        if task.status == "READY" and used >= budget:
            errors.append(f"{task.task_id}: attempt budget exhausted")
        if task.status == "DONE":
            evidence = clean_cell(task.metadata.get("Evidence", ""))
            if evidence in {"", "NONE", "TODO"} or EVIDENCE_PATTERN.search(evidence) is None:
                errors.append(f"{task.task_id}: DONE requires Evidence")
            try:
                validate_done_evidence(verify_text, task)
            except ValueError as exc:
                errors.append(str(exc))
        if task.status == "BLOCKED" and clean_cell(task.metadata.get("Blocker", "")) in {"", "NONE", "TODO"}:
            errors.append(f"{task.task_id}: BLOCKED requires a blocker")
        if task.status == "SKIPPED" and clean_cell(task.metadata.get("Skip record", "")) in {"", "NONE", "TODO"}:
            errors.append(f"{task.task_id}: SKIPPED requires a skip record")
        updated = clean_cell(task.metadata.get("Last updated", ""))
        if updated not in {"", "TODO"} and not explicit_timestamp(updated):
            errors.append(f"{task.task_id}: Last updated must be ISO 8601 with timezone")
        try:
            declared = declared_task_waivers(task)
            for dependency_id, waiver_id in declared.items():
                waiver = waivers.get(waiver_id)
                if waiver is None:
                    errors.append(f"{task.task_id}: unknown dependency waiver {waiver_id}")
                elif waiver[0] != dependency_id or waiver[1] != task.task_id:
                    errors.append(f"{task.task_id}: waiver {waiver_id} does not match its task pair")
        except ValueError as exc:
            errors.append(str(exc))
        if execution_contract_required:
            sections, duplicate_sections = inspect_task_sections(task.block)
            for name in sorted(duplicate_sections):
                errors.append(f"{task.task_id}: duplicate required section #### {name}")
            for name in ("Outcome", "Acceptance criteria", "Validation", "Execution log"):
                if name not in sections:
                    errors.append(f"{task.task_id}: missing required section #### {name}")
            outcome = sections.get("Outcome", "")
            if not outcome.strip() or "TODO" in outcome.upper():
                errors.append(f"{task.task_id}: unresolved Outcome")
            acceptance = sections.get("Acceptance criteria", "")
            if "- [" not in acceptance or "TODO" in acceptance.upper():
                errors.append(f"{task.task_id}: objective acceptance criteria are required")
            validation = sections.get("Validation", "")
            if "```" not in validation or "TODO" in validation.upper():
                errors.append(f"{task.task_id}: executable validation commands are required")
            try:
                validate_task_property_execution_projection(
                    validation,
                    task.task_id,
                    task.metadata.get("Requirements", ""),
                    technology_refs,
                    property_execution_by_id,
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
                errors.append(f"{task.task_id}: DONE requires an observed Execution log")
            if task.status == "DONE" and "- [ ]" in acceptance:
                errors.append(f"{task.task_id}: DONE has incomplete acceptance criteria")

    observed_property_pairs = {
        (row.task_id, row.property_id)
        for row in property_evidence_rows
        if row.result in {"PASS", "FAIL"}
    }
    done_property_pairs = {
        (task.task_id, property_id)
        for task in tasks
        if task.status == "DONE"
        for property_id in PROPERTY_ID.findall(
            clean_cell(task.metadata.get("Requirements", ""))
        )
    }
    for task_id, property_id in sorted(
        observed_property_pairs | done_property_pairs
    ):
        task = by_id.get(task_id)
        if task is None:
            errors.append(
                f"{task_id} {property_id}: observed property-test evidence "
                "references an unknown current task"
            )
            continue
        task_property_ids = set(
            PROPERTY_ID.findall(clean_cell(task.metadata.get("Requirements", "")))
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
        technology = (technology_decisions_by_id or {}).get(
            expected.framework_tech_id
        )
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
            raise ValueError("Dependency cycle detected: " + " -> ".join([*stack[start:], task_id]))
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
            re.fullmatch(rf"{re.escape(current_auth)}(?:\s+clause\s+[A-Za-z0-9._:-]+)?", authority)
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
                if waiver is None or waiver[0] != dependency_id or waiver[1] != task.task_id:
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
    property_execution_by_id: dict[str, PropertyExecution],
) -> list[str]:
    """Return approved properties omitted from a current task plan."""

    if plan_state != "CURRENT":
        return []
    covered_property_ids = {
        property_id
        for task in tasks
        if task.status in {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE"}
        for property_id in PROPERTY_ID.findall(
            clean_cell(task.metadata.get("Requirements", ""))
        )
    }
    return sorted(set(property_execution_by_id) - covered_property_ids)


def clean_cell(value: Any) -> str:
    text = str(value).strip()
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        text = text[1:-1].strip()
    return text


def unresolved(value: str) -> bool:
    cleaned = clean_cell(value)
    return (
        not cleaned
        or UNRESOLVED_TOKEN.search(cleaned) is not None
        or "<" in cleaned
        or ">" in cleaned
    )


def explicit_value(value: str, *, allow_none: bool = False) -> bool:
    cleaned = clean_cell(value)
    if unresolved(cleaned):
        return False
    return allow_none or cleaned not in {"NONE", "NOT_RECORDED", "UNASSIGNED"}


def parse_positive_cost(
    value: str,
    pattern: re.Pattern[str],
    field_name: str,
) -> tuple[str, Decimal]:
    """Parse one finite positive ISO-currency amount in canonical form."""

    cleaned = clean_cell(value)
    match = pattern.fullmatch(cleaned)
    if match is None:
        raise ValueError(
            f"{field_name} must use a finite positive currency amount such as "
            "USD: 20.00"
        )
    try:
        amount = Decimal(match.group("amount"))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} amount is invalid") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"{field_name} amount must be finite and positive")
    currency = match.group("currency")
    if currency not in ISO_4217_CURRENCY_CODES:
        raise ValueError(
            f"{field_name} currency must be a current ISO 4217 List One code"
        )
    return currency, amount


def parse_cost_posture(value: str) -> tuple[str, Decimal] | None:
    """Return an optional owner hard cap from the canonical Gate A posture."""

    cleaned = clean_cell(value)
    if cleaned == DEFAULT_COST_POSTURE:
        return None
    match = COST_POSTURE_WITH_CAP.fullmatch(cleaned)
    if match is None:
        raise ValueError(
            "Cost posture must be MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED or "
            "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00"
        )
    return parse_positive_cost(
        f"{match.group('currency')}: {match.group('amount')}",
        AWS_COST_CEILING,
        "Cost posture hard cap",
    )


def validate_aws_cost_ceiling(value: str, cost_posture: str) -> None:
    """Require a finite mutation ceiling and honor any Gate A owner cap."""

    currency, amount = parse_positive_cost(
        value,
        AWS_COST_CEILING,
        "AWS cost ceiling",
    )
    owner_cap = parse_cost_posture(cost_posture)
    if owner_cap is None:
        return
    cap_currency, cap_amount = owner_cap
    if currency != cap_currency:
        raise ValueError(
            "AWS cost ceiling currency must match the Gate A owner hard cap"
        )
    if amount > cap_amount:
        raise ValueError("AWS cost ceiling exceeds the Gate A owner hard cap")


def explicit_timestamp(value: str) -> bool:
    cleaned = clean_cell(value)
    if unresolved(cleaned):
        return False
    candidate = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def explicit_human_approver(value: str) -> bool:
    """Require an explicit owner identity that is not an agent or automation."""

    cleaned = clean_cell(value)
    return explicit_value(cleaned) and NON_HUMAN_APPROVER.search(cleaned) is None


def parse_exact_id_list(value: str, pattern: re.Pattern[str], field_name: str) -> list[str]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return []
    if unresolved(cleaned):
        raise ValueError(f"{field_name} is unresolved")
    items = [item.strip() for item in cleaned.split(",")]
    if any(pattern.fullmatch(item) is None for item in items):
        raise ValueError(f"{field_name} must contain comma-separated {pattern.pattern} IDs or NONE")
    if len(items) != len(set(items)):
        raise ValueError(f"{field_name} contains duplicate IDs")
    return items


def markdown_tables(text: str) -> list[list[list[str]]]:
    """Return simple Markdown tables without evaluating any project content."""

    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    structural = without_fenced_code(text)
    for raw_line, structural_line in zip(text.splitlines(), structural.splitlines()):
        if structural_line.strip().startswith("|"):
            current.append([clean_cell(cell) for cell in split_table_row(raw_line)])
        elif current:
            if len(current) >= 3:
                tables.append(current)
            current = []
    if len(current) >= 3:
        tables.append(current)
    return tables


def task_property_execution_table(
    validation_section: str, task_id: str
) -> ContractTable | None:
    """Return the one exact property-execution projection outside code fences."""

    structural = without_fenced_code(validation_section)
    source_lines = validation_section.splitlines()
    structural_lines = structural.splitlines()
    matches: list[ContractTable] = []
    index = 0
    while index < len(source_lines):
        if not structural_lines[index].strip().startswith("|"):
            index += 1
            continue
        raw_lines: list[str] = []
        while index < len(source_lines) and structural_lines[index].strip().startswith("|"):
            raw_lines.append(source_lines[index])
            index += 1
        header = split_markdown_table_row(raw_lines[0])
        if header is None or not header or clean_cell(header[0]) != "Property ID":
            continue
        try:
            matches.append(
                _parse_contract_table_lines(raw_lines, PROPERTY_EXECUTION_HEADERS)
            )
        except ValueError as exc:
            raise ValueError(
                f"{task_id}: property execution projection {exc}"
            ) from exc
    if len(matches) > 1:
        raise ValueError(
            f"{task_id}: Validation must contain exactly one property execution projection"
        )
    return matches[0] if matches else None


def validate_task_property_execution_projection(
    validation_section: str,
    task_id: str,
    requirements: str,
    technology_refs: list[str],
    property_execution_by_id: dict[str, PropertyExecution] | None,
) -> None:
    """Require an exact PRD projection and one exact command per referenced property."""

    property_ids = PROPERTY_ID.findall(clean_cell(requirements))
    if len(property_ids) != len(set(property_ids)):
        raise ValueError(f"{task_id}: Requirements contains duplicate PROP IDs")
    table = task_property_execution_table(validation_section, task_id)
    if not property_ids:
        if table is not None:
            raise ValueError(
                f"{task_id}: Validation has a property execution projection without a PROP requirement"
            )
        return
    if property_execution_by_id is None:
        raise ValueError(
            f"{task_id}: property execution contract is unavailable for PROP validation"
        )
    unknown = [item for item in property_ids if item not in property_execution_by_id]
    if unknown:
        raise ValueError(
            f"{task_id}: Requirements references unknown PROP IDs: " + ", ".join(unknown)
        )
    if table is None:
        raise ValueError(
            f"{task_id}: Validation requires the exact property execution projection"
        )
    projected_ids = [row[0] for row in table.rows]
    if projected_ids != property_ids or len(projected_ids) != len(set(projected_ids)):
        raise ValueError(
            f"{task_id}: property execution projection IDs must exactly match Requirements"
        )
    for row in table.rows:
        expected = property_execution_by_id[row[0]]
        if not valid_property_execution_command(expected.exact_command):
            raise ValueError(
                f"{task_id}: {row[0]} Exact command is not an executable local command"
            )
        if not valid_property_execution_command(row[2]):
            raise ValueError(
                f"{task_id}: projected {row[0]} Exact command is not an executable "
                "local command"
            )
        expected_row = (
            expected.property_id,
            expected.framework_tech_id,
            expected.exact_command,
            expected.run_target_time_bound,
            expected.seed_or_reproduction_format,
            expected.evidence_destination,
        )
        if row != expected_row:
            raise ValueError(
                f"{task_id}: property execution projection for {row[0]} does not match the PRD contract"
            )
        if expected.framework_tech_id not in technology_refs:
            raise ValueError(
                f"{task_id}: Design must reference {expected.framework_tech_id} for {row[0]}"
            )
    commands = validation_commands(validation_section, task_id)
    for command in dict.fromkeys(
        property_execution_by_id[item].exact_command for item in property_ids
    ):
        if commands.count(command) != 1:
            raise ValueError(
                f"{task_id}: property command {command!r} must appear exactly once in Validation"
            )


def _canonical_contract_table(raw_lines: list[str]) -> bytes:
    return ("\n".join(line.rstrip() for line in raw_lines) + "\n").encode("utf-8")


def _parse_contract_table_lines(
    raw_lines: list[str], expected_headers: tuple[str, ...]
) -> ContractTable:
    if len(raw_lines) < 2:
        raise ValueError("Markdown contract table requires a header and separator")
    parsed: list[tuple[str, ...]] = []
    for raw_line in raw_lines:
        cells = split_markdown_table_row(raw_line)
        if cells is None:
            raise ValueError("Malformed Markdown contract table row")
        parsed.append(tuple(clean_cell(cell) for cell in cells))
    if parsed[0] != expected_headers:
        raise ValueError(
            "Contract table headers must be exactly: " + " | ".join(expected_headers)
        )
    if len(parsed[1]) != len(expected_headers) or any(
        re.fullmatch(r":?-{3,}:?", cell) is None for cell in parsed[1]
    ):
        raise ValueError("Contract table separator is malformed")
    for row in parsed[2:]:
        if len(row) != len(expected_headers):
            raise ValueError(
                f"Contract table row has {len(row)} cells; expected {len(expected_headers)}"
            )
    return ContractTable(
        headers=expected_headers,
        rows=tuple(parsed[2:]),
        canonical_bytes=_canonical_contract_table(raw_lines),
    )


def _heading_section_offsets(
    text: str, heading: str
) -> tuple[int, int, int] | None:
    """Return heading start, body start, and section end using canonical rules."""

    structural = without_fenced_code(text)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*\r?$", structural, re.MULTILINE)
    )
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one heading {heading!r}; found {len(matches)}")
    level = len(heading) - len(heading.lstrip("#"))
    following = re.search(
        rf"^#{{1,{level}}}[ \t]+", structural[matches[0].end() :], re.MULTILINE
    )
    end = matches[0].end() + following.start() if following else len(text)
    return matches[0].start(), matches[0].end(), end


def _heading_section_lines(
    text: str, heading: str
) -> tuple[list[str], list[str]] | None:
    offsets = _heading_section_offsets(text, heading)
    if offsets is None:
        return None
    _, body_start, end = offsets
    structural = without_fenced_code(text)
    return text[body_start:end].splitlines(), structural[body_start:end].splitlines()


def _heading_title_span(text: str, title: str) -> SourceSpan:
    """Resolve one visible Markdown heading title without inspecting fences."""

    structural = without_fenced_code(text)
    matches = list(
        re.finditer(
            rf"^(?P<marks>#{{1,6}})[ \t]+(?:\d+(?:\.\d+)*\.?[ \t]+)?{re.escape(title)}[ \t]*\r?$",
            structural,
            re.MULTILINE,
        )
    )
    if len(matches) != 1:
        raise ValueError(f"expected exactly one heading title {title!r}; found {len(matches)}")
    level = len(matches[0].group("marks"))
    following = re.search(
        rf"^#{{1,{level}}}[ \t]+", structural[matches[0].end() :], re.MULTILINE
    )
    end = matches[0].end() + following.start() if following else len(text)
    return SourceSpan(matches[0].start(), end)


def contract_table_after_heading(
    text: str, heading: str, expected_headers: tuple[str, ...]
) -> ContractTable | None:
    section = _heading_section_lines(text, heading)
    if section is None:
        return None
    lines, structural_lines = section
    start = next(
        (
            index
            for index, structural_line in enumerate(structural_lines)
            if structural_line.strip().startswith("|")
        ),
        None,
    )
    if start is None:
        raise ValueError(f"No Markdown table after {heading!r}")
    raw_lines: list[str] = []
    for line, structural_line in zip(lines[start:], structural_lines[start:]):
        if not structural_line.strip().startswith("|"):
            break
        raw_lines.append(line)
    return _parse_contract_table_lines(raw_lines, expected_headers)


def contract_table_in_section(
    text: str, heading: str, expected_headers: tuple[str, ...]
) -> ContractTable | None:
    section = _heading_section_lines(text, heading)
    if section is None:
        return None
    lines, structural_lines = section
    matches: list[ContractTable] = []
    index = 0
    while index < len(lines):
        if not structural_lines[index].strip().startswith("|"):
            index += 1
            continue
        raw_lines: list[str] = []
        while index < len(lines) and structural_lines[index].strip().startswith("|"):
            raw_lines.append(lines[index])
            index += 1
        header = split_markdown_table_row(raw_lines[0])
        if header is None or tuple(clean_cell(cell) for cell in header) != expected_headers:
            continue
        matches.append(_parse_contract_table_lines(raw_lines, expected_headers))
    if len(matches) > 1:
        raise ValueError(
            f"Expected one table with headers {' | '.join(expected_headers)} after {heading!r}"
        )
    return matches[0] if matches else None


def parse_property_test_evidence(text: str) -> list[PropertyTestEvidenceRow]:
    """Parse the exact durable property-test evidence table from VERIFY.md."""

    table = contract_table_after_heading(
        text,
        PROPERTY_TEST_EVIDENCE_HEADING,
        PROPERTY_TEST_EVIDENCE_HEADERS,
    )
    if table is None:
        raise ValueError(
            "VERIFY.md requires exactly one Property-based test evidence section"
        )
    rows: list[PropertyTestEvidenceRow] = []
    seen_evidence_ids: set[str] = set()
    for cells in table.rows:
        row = PropertyTestEvidenceRow(*cells)
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError(
                "VERIFY.md Property-based test evidence Evidence ID must be EV-nnnn"
            )
        if row.evidence_id in seen_evidence_ids:
            raise ValueError(
                "VERIFY.md Property-based test evidence Evidence IDs must be unique"
            )
        seen_evidence_ids.add(row.evidence_id)
        if PROPERTY_ID.fullmatch(row.property_id) is None:
            raise ValueError(
                "VERIFY.md Property-based test evidence Property ID must be PROP-nnn"
            )
        if row.result not in PROPERTY_TEST_RESULTS:
            raise ValueError(
                f"{row.property_id}: property-test Result must be NOT_STARTED, PASS, or FAIL"
            )
        rows.append(row)
    return rows


def parse_property_run_target(value: str) -> tuple[int | None, Decimal | None]:
    """Parse the canonical minimum-case and/or maximum-duration execution target."""

    cleaned = clean_cell(value)
    match = re.fullmatch(
        r"(?:MIN_CASES: (?P<cases>[1-9]\d*)"
        r"(?:; MAX_SECONDS: (?P<case_seconds>[1-9]\d*))?"
        r"|MAX_SECONDS: (?P<seconds>[1-9]\d*))",
        cleaned,
    )
    if match is None:
        raise ValueError(
            "run target/time bound must be MIN_CASES: <positive integer>, "
            "MAX_SECONDS: <positive number>, or both in that order"
        )
    minimum_cases = int(match.group("cases")) if match.group("cases") else None
    seconds_text = match.group("case_seconds") or match.group("seconds")
    maximum_seconds = Decimal(seconds_text) if seconds_text is not None else None
    if maximum_seconds is not None and (
        not maximum_seconds.is_finite() or maximum_seconds <= 0
    ):
        raise ValueError("MAX_SECONDS must be finite and greater than zero")
    return minimum_cases, maximum_seconds


def parse_observed_property_run(value: str) -> tuple[int, Decimal]:
    """Parse one exact observed case count and elapsed duration."""

    match = re.fullmatch(
        r"CASES: (?P<cases>[1-9]\d*); "
        r"ELAPSED_SECONDS: (?P<seconds>\d+(?:\.\d+)?)",
        clean_cell(value),
    )
    if match is None:
        raise ValueError(
            "Observed run must be CASES: <positive integer>; "
            "ELAPSED_SECONDS: <nonnegative number>"
        )
    elapsed = Decimal(match.group("seconds"))
    if not elapsed.is_finite() or elapsed < 0:
        raise ValueError("ELAPSED_SECONDS must be finite and nonnegative")
    return int(match.group("cases")), elapsed


def parsed_numeric_version(value: str) -> tuple[int, ...] | None:
    """Return the numeric release tuple for one exact package version."""

    cleaned = clean_cell(value)
    match = re.fullmatch(r"v?(?P<numeric>\d+(?:\.\d+)*)", cleaned)
    if match is None:
        return None
    return tuple(int(part) for part in match.group("numeric").split("."))


def technology_version_policy_allows(policy: str, observed: str) -> bool:
    """Check an observed exact version against the machine-comparable policy forms."""

    if technology_contract_value_is_unresolved(
        policy
    ) or technology_contract_value_is_unresolved(observed):
        return False
    if policy.startswith("EXACT: "):
        return observed == policy.removeprefix("EXACT: ")
    observed_parts = parsed_numeric_version(observed)
    if observed_parts is None:
        return False
    if policy.startswith("COMPATIBLE_MAJOR: "):
        return observed_parts[0] == int(policy.removeprefix("COMPATIBLE_MAJOR: "))
    if policy.startswith("MINIMUM: "):
        minimum = parsed_numeric_version(policy.removeprefix("MINIMUM: "))
        if minimum is None:
            return False
        width = max(len(observed_parts), len(minimum))
        return observed_parts + (0,) * (width - len(observed_parts)) >= minimum + (
            0,
        ) * (width - len(minimum))
    # These policies require external evidence mapping the observed version to
    # the dated LTS release or organization constraint. A numeric-looking
    # version alone cannot prove either policy, so local validation fails closed.
    return False


def replay_evidence_matches_contract(
    approved_format: str,
    observed_replay: str,
    exact_command: str,
) -> bool:
    """Bind replay evidence to the current PRD reproduction-format contract."""

    approved = clean_cell(approved_format)
    observed = clean_cell(observed_replay)
    if unresolved(approved) or unresolved(observed):
        return False
    lowered_approved = approved.casefold()
    lowered_observed = observed.casefold()
    if EVIDENCE_PLACEHOLDER_PATTERN.search(observed) is not None or re.search(
        r"\b(?:unavailable|missing|not[ _-]*recorded|not[ _-]*captured)\b",
        lowered_observed,
    ):
        return False
    if "seed" in lowered_approved:
        match = re.fullmatch(
            r"(?:seed\s*[:=]\s*|.*(?:^|\s)--seed(?:=|\s+))(?P<seed>\S+)",
            observed,
            re.IGNORECASE,
        )
        if match is None:
            return False
        seed = match.group("seed").strip("'\"")
        if not seed or EVIDENCE_PLACEHOLDER_PATTERN.fullmatch(seed) is not None:
            return False
        if "integer" in lowered_approved and re.fullmatch(r"\d+", seed) is None:
            return False
        return True
    if "command" in lowered_approved:
        return observed == exact_command
    return observed == approved


def valid_replay_format_contract(value: str) -> bool:
    """Require a property plan to declare a machine-checkable replay mode."""

    cleaned = clean_cell(value)
    if unresolved(cleaned):
        return False
    lowered = cleaned.casefold()
    return "seed" in lowered or "command" in lowered


def valid_property_execution_command(value: str) -> bool:
    """Recognize one explicit local command rather than prose or a sentinel."""

    cleaned = clean_cell(value)
    if (
        unresolved(cleaned)
        or EVIDENCE_PLACEHOLDER_PATTERN.search(cleaned) is not None
        or SHELL_CONTROL.search(cleaned) is not None
        or cleaned.startswith(("-", "#"))
    ):
        return False
    executable = cleaned.split(maxsplit=1)[0].strip("'\"")
    return bool(
        PROPERTY_COMMAND_EXECUTABLE.fullmatch(executable)
        and executable.casefold() not in PROPERTY_COMMAND_PROSE_VERBS
    )


def evidence_timestamp(value: str, label: str) -> datetime:
    if not explicit_timestamp(value):
        raise ValueError(f"{label} must be ISO 8601 with timezone")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_done_property_evidence(
    rows: list[PropertyTestEvidenceRow],
    task: InspectedTask,
    snapshot: dict[str, str],
    expected: PropertyExecution,
    technology: TechnologyDecision,
    completion_rows: list[TaskCompletionEvidenceRow],
    *,
    require_done_pass: bool = True,
) -> None:
    """Validate observed property history and, for DONE, require a final pass."""

    task_id = task.task_id
    if expected.evidence_destination != PROPERTY_TEST_EVIDENCE_DESTINATION:
        raise ValueError(
            f"{task_id}: {expected.property_id} PRD evidence destination does not "
            "identify the exact VERIFY.md property evidence section"
        )
    observed = [
        row
        for row in rows
        if row.task_id == task_id
        and row.property_id == expected.property_id
        and row.result in {"PASS", "FAIL"}
    ]
    if not observed and require_done_pass:
        raise ValueError(
            f"{task_id}: DONE {expected.property_id} requires observed property-test evidence"
        )
    if not observed:
        return
    expected_basis = (
        f"{snapshot.get('Requirements revision', '')} / "
        f"{snapshot.get('Design revision', '')} / "
        f"{snapshot.get('Construction authorization', '')}"
    )
    completion_by_id = {row.evidence_id: row for row in completion_rows}
    task_evidence_ids = set(
        LOCAL_EVIDENCE_ID.findall(clean_cell(task.metadata.get("Evidence", "")))
    )
    passing = False
    timestamps: list[tuple[datetime, PropertyTestEvidenceRow]] = []
    for index, row in enumerate(observed, start=1):
        label = f"{task_id} {expected.property_id} evidence row {index}"
        if re.fullmatch(r"EV-\d{4,}", row.evidence_id) is None:
            raise ValueError(f"{label} Evidence ID must be EV-nnnn")
        if row.requirements_design_authorization != expected_basis:
            raise ValueError(f"{label} REQ / DES / AUTH is not current")
        if row.framework_tech_id != expected.framework_tech_id:
            raise ValueError(
                f"{label} Framework TECH ID does not match the current PRD property contract"
            )
        if row.framework_selection != technology.selection:
            raise ValueError(
                f"{label} Framework selection does not match {technology.decision_id}"
            )
        observed_version = require_explicit_evidence_value(
            row.observed_exact_version,
            f"{label} observed exact version",
        )
        if not technology_version_policy_allows(
            technology.version_policy, observed_version
        ):
            raise ValueError(
                f"{label} observed exact version does not satisfy "
                f"{technology.version_policy}"
            )
        if row.exact_command != expected.exact_command:
            raise ValueError(
                f"{label} Exact command does not match the current PRD property contract"
            )
        try:
            observed_cases, observed_seconds = parse_observed_property_run(
                row.observed_run
            )
            minimum_cases, maximum_seconds = parse_property_run_target(
                expected.run_target_time_bound
            )
        except ValueError as exc:
            raise ValueError(f"{label} {exc}") from exc
        replay = require_explicit_evidence_value(
            row.replay_seed_or_exact_command,
            f"{label} replay seed or exact command",
        )
        if not replay_evidence_matches_contract(
            expected.seed_or_reproduction_format,
            replay,
            expected.exact_command,
        ):
            raise ValueError(
                f"{label} replay evidence does not match the approved PRD "
                "Seed or reproduction format"
            )
        observed_at = evidence_timestamp(row.observed_at, f"{label} Observed at")
        timestamps.append((observed_at, row))
        material = require_explicit_evidence_value(
            row.commit_worktree_artifact,
            f"{label} commit/worktree/artifact",
        )
        require_durable_evidence_source(row.durable_source, f"{label} durable source")
        completion = completion_by_id.get(row.evidence_id)
        if completion is None:
            raise ValueError(
                f"{label} Evidence ID is missing from Task completion evidence"
            )
        if (
            completion.task_id != task_id
            or completion.command_or_observation != row.exact_command
            or completion.observed_at != row.observed_at
            or completion.commit_worktree_artifact != material
            or completion.durable_source != row.durable_source
        ):
            raise ValueError(
                f"{label} does not match its Task completion evidence binding"
            )
        require_explicit_evidence_value(
            completion.result,
            f"{label} Task completion result",
        )
        require_explicit_evidence_value(
            completion.actor,
            f"{label} Task completion actor",
        )
        if row.result == "PASS":
            passing = True
            if require_done_pass and row.evidence_id not in task_evidence_ids:
                raise ValueError(
                    f"{label} PASS Evidence ID is not cited by the DONE task"
                )
            if completion.status not in TASK_COMPLETION_EVIDENCE_STATUSES:
                raise ValueError(
                    f"{label} PASS completion status must be LOCAL_PASS or VERIFIED"
                )
            if minimum_cases is not None and observed_cases < minimum_cases:
                raise ValueError(
                    f"{label} observed cases do not meet MIN_CASES: {minimum_cases}"
                )
            if maximum_seconds is not None and observed_seconds > maximum_seconds:
                raise ValueError(
                    f"{label} elapsed time exceeds MAX_SECONDS: {maximum_seconds}"
                )
            if row.minimized_counterexample != "NONE":
                raise ValueError(
                    f"{label} PASS must record Minimized counterexample as NONE"
                )
            if row.failure_class_resolution != "NONE":
                raise ValueError(
                    f"{label} PASS must record Failure class / resolution as NONE"
                )
            continue
        if completion.status != "FAILED":
            raise ValueError(f"{label} FAIL completion status must be FAILED")
        counterexample = require_explicit_evidence_value(
            row.minimized_counterexample,
            f"{label} minimized counterexample",
        )
        if counterexample == "NONE":
            raise ValueError(f"{label} FAIL requires a minimized counterexample")
        failure_match = re.fullmatch(
            "(?P<class>" + "|".join(sorted(PROPERTY_TEST_FAILURE_CLASSES))
            + r") — (?P<resolution>.+)",
            row.failure_class_resolution,
        )
        if failure_match is None:
            raise ValueError(
                f"{label} FAIL requires one supported failure class and a concrete "
                "resolution separated by an em dash"
            )
        try:
            require_explicit_evidence_value(
                failure_match.group("resolution"),
                f"{label} failure resolution",
            )
        except ValueError as exc:
            raise ValueError(
                f"{label} FAIL requires one supported failure class and a concrete "
                "resolution separated by an em dash"
            ) from exc
    if len({stamp for stamp, _row in timestamps}) != len(timestamps):
        raise ValueError(
            f"{task_id}: {expected.property_id} observed timestamps must be unique"
        )
    if require_done_pass and not passing:
        raise ValueError(
            f"{task_id}: DONE {expected.property_id} requires preserved failure rows "
            "and a later PASS row"
        )
    latest = max(timestamps, key=lambda item: item[0])[1]
    if require_done_pass and latest.result != "PASS":
        raise ValueError(
            f"{task_id}: DONE {expected.property_id} requires the latest observed "
            "property-test result to be PASS"
        )


def valid_technology_version_policy(value: str) -> bool:
    cleaned = clean_cell(value)
    if technology_contract_value_is_unresolved(cleaned):
        return False
    if cleaned.startswith("COMPATIBLE_MAJOR: "):
        return re.fullmatch(r"COMPATIBLE_MAJOR: [1-9]\d*", cleaned) is not None
    if cleaned.startswith("CURRENT_LTS_AS_OF: "):
        match = re.fullmatch(r"CURRENT_LTS_AS_OF: (\d{4}-\d{2}-\d{2})", cleaned)
        if match is None:
            return False
        try:
            datetime.strptime(match.group(1), "%Y-%m-%d")
        except ValueError:
            return False
        return True
    if cleaned.startswith("EXACT: "):
        return explicit_value(cleaned.removeprefix("EXACT: "), allow_none=False)
    if cleaned.startswith("MINIMUM: "):
        minimum = cleaned.removeprefix("MINIMUM: ")
        return (
            explicit_value(minimum, allow_none=False)
            and parsed_numeric_version(minimum) is not None
        )
    if cleaned.startswith("ORG_MANAGED: "):
        return explicit_value(
            cleaned.removeprefix("ORG_MANAGED: "), allow_none=False
        )
    prefix = "NOT_APPLICABLE — "
    return cleaned.startswith(prefix) and explicit_value(
        cleaned[len(prefix) :], allow_none=False
    )


def machine_comparable_property_version_policy(value: str) -> bool:
    """Require an active property framework policy with deterministic comparison."""

    cleaned = clean_cell(value)
    if not valid_technology_version_policy(cleaned):
        return False
    if cleaned.startswith("EXACT: "):
        return explicit_value(cleaned.removeprefix("EXACT: "), allow_none=False)
    if cleaned.startswith("COMPATIBLE_MAJOR: "):
        return re.fullmatch(r"COMPATIBLE_MAJOR: [1-9]\d*", cleaned) is not None
    if cleaned.startswith("MINIMUM: "):
        return parsed_numeric_version(cleaned.removeprefix("MINIMUM: ")) is not None
    return False


def technology_value_is_not_applicable(value: str) -> bool:
    return clean_cell(value).startswith("NOT_APPLICABLE — ")


def technology_contract_value_is_unresolved(value: str) -> bool:
    """Reject the complete contract sentinel vocabulary in technology cells."""

    cleaned = clean_cell(value)
    return unresolved(cleaned) or EVIDENCE_PLACEHOLDER_PATTERN.search(cleaned) is not None


def valid_technology_selection(value: str) -> bool:
    """Accept one concrete selection or the one canonical non-applicable form."""

    cleaned = clean_cell(value)
    if technology_contract_value_is_unresolved(cleaned):
        return False
    if technology_value_is_not_applicable(cleaned):
        reason = cleaned.removeprefix("NOT_APPLICABLE — ")
        return (
            explicit_value(reason, allow_none=False)
            and EVIDENCE_PLACEHOLDER_PATTERN.search(reason) is None
        )
    normalized = re.sub(r"[\s_-]+", "_", cleaned.upper())
    if cleaned.startswith("NOT_APPLICABLE") or normalized in {
        "N/A",
        "NA",
        "NONE",
        "NOT_APPLICABLE",
        "DOES_NOT_APPLY",
    }:
        return False
    return explicit_value(cleaned, allow_none=False)


def valid_technology_basis_ids(value: str) -> bool:
    """Require a canonical, duplicate-free comma-space stable-ID list."""

    cleaned = clean_cell(value)
    if unresolved(cleaned):
        return False
    identifiers = cleaned.split(", ")
    return bool(identifiers) and all(
        STABLE_CONTRACT_ID.fullmatch(identifier) is not None
        for identifier in identifiers
    ) and len(identifiers) == len(set(identifiers))


def authoritative_requirement_ids(text: str) -> set[str]:
    """Return every stable ID in an authoritative requirement table."""

    identifiers: set[str] = set()
    for table in markdown_tables(text):
        if not table or tuple(table[0]) not in {
            NORMATIVE_REQUIREMENT_HEADERS,
            LEGACY_REQUIREMENT_HEADERS,
        }:
            continue
        expected_cells = len(table[0])
        for row in table[2:]:
            if (
                len(row) == expected_cells
                and STABLE_CONTRACT_ID.fullmatch(row[0]) is not None
            ):
                identifiers.add(row[0])
    return identifiers


def concrete_requirement_subject(value: str) -> bool:
    """Return whether a Fastlane EARS subject names a concrete project actor."""

    subject = clean_cell(value)
    return bool(
        CONCRETE_SUBJECT.fullmatch(subject)
        and subject.casefold() not in NON_CONCRETE_SUBJECTS
        and not unresolved(subject)
        and not any(character in subject for character in "<>{}")
    )


def observable_requirement_response(value: str) -> bool:
    response = clean_cell(value)
    return bool(
        not unresolved(response)
        and re.search(r"[A-Za-z]", response)
        and not any(character in response for character in "<>{}")
        and response.casefold()
        not in {"be appropriate", "be fast", "be scalable", "be secure", "work"}
    )


def measurable_acceptance_is_bound(value: str) -> bool:
    """Reject keyword-only claims while accepting an observable bound or check."""

    words = re.findall(r"[A-Za-z0-9]+", value)
    return bool(
        len(words) >= 6
        and MEASURABLE_EXPECTED_RESULT.search(value)
        and MEASURABLE_BINDING.search(value)
        and UNDEFINED_QUALITY_TERM.search(value) is None
    )


def requirement_method_issues(
    requirement_id: str,
    requirement: str,
    ears_form: str,
    acceptance_criteria: str,
    acceptance_form: str,
) -> list[str]:
    """Return deterministic Fastlane EARS and acceptance issues for one row."""

    issues: list[str] = []
    values = {
        "requirement": requirement,
        "EARS form": ears_form,
        "acceptance criteria": acceptance_criteria,
        "acceptance form": acceptance_form,
    }
    for field_name, value in values.items():
        if unresolved(value):
            issues.append(f"{requirement_id}: {field_name} is unresolved")
    if issues:
        return issues

    if ears_form not in EARS_FORMS:
        issues.append(
            f"{requirement_id}: EARS form must be one of "
            + ", ".join(sorted(EARS_FORMS))
        )
        return issues
    shall_count = len(re.findall(r"\bSHALL\b", requirement))
    if shall_count == 0:
        issues.append(f"{requirement_id}: requirement is missing SHALL")
    elif shall_count != 1:
        issues.append(
            f"{requirement_id}: requirement must contain exactly one uppercase SHALL"
        )
    grammar = EARS_PATTERNS[ears_form].fullmatch(requirement)
    if grammar is None:
        issues.append(
            f"{requirement_id}: requirement does not match {ears_form} clause order"
        )
    elif not concrete_requirement_subject(grammar.group("subject")):
        issues.append(
            f"{requirement_id}: requirement subject must be concrete and non-placeholder"
        )
    elif not observable_requirement_response(grammar.group("response")):
        issues.append(
            f"{requirement_id}: requirement response must be concrete and observable"
        )
    vague_requirement = UNDEFINED_QUALITY_TERM.search(requirement)
    if vague_requirement is not None:
        issues.append(
            f"{requirement_id}: requirement contains undefined qualitative term "
            f"{vague_requirement.group(0)!r}"
        )

    if acceptance_form not in ACCEPTANCE_FORMS:
        issues.append(
            f"{requirement_id}: Acceptance form must be GHERKIN or MEASURABLE"
        )
        return issues
    if acceptance_form == "GHERKIN":
        if (
            GHERKIN_ACCEPTANCE.fullmatch(acceptance_criteria) is None
            or len(re.findall(r"\bGIVEN\b", acceptance_criteria)) != 1
            or len(re.findall(r"\bWHEN\b", acceptance_criteria)) != 1
            or len(re.findall(r"\bTHEN\b", acceptance_criteria)) != 1
        ):
            issues.append(
                f"{requirement_id}: GHERKIN acceptance must use GIVEN, one WHEN, "
                "and THEN in canonical order"
            )
    elif not measurable_acceptance_is_bound(acceptance_criteria):
        issues.append(
            f"{requirement_id}: MEASURABLE acceptance requires an observable expected "
            "result plus a bound, policy/configuration check, exact command/API, or "
            "stable TEST/PROP/EV binding"
        )
    return issues


def quality_attribute_scenario_issues(
    text: str,
    requirement_ids: set[str],
) -> list[str]:
    """Validate the compact QAS register or its concrete non-applicable reason."""

    structural = without_fenced_code(text)
    heading = re.search(
        r"^### Quality attribute scenarios\s*$", structural, re.MULTILINE
    )
    if heading is None:
        return ["QAS-SECTION: Quality attribute scenarios section is missing"]
    following = re.search(
        r"^#{1,3}\s+", structural[heading.end():], re.MULTILINE
    )
    end = heading.end() + following.start() if following else len(structural)
    section = structural[heading.end():end]
    tables = [
        table
        for table in markdown_tables(section)
        if table and tuple(table[0]) == QAS_HEADERS
    ]
    if not tables:
        non_applicable = re.search(
            r"^NOT_APPLICABLE — (?P<reason>.+)$", section, re.MULTILINE
        )
        if non_applicable is None or unresolved(non_applicable.group("reason")):
            return [
                "QAS-SECTION: require one complete QAS table or "
                "NOT_APPLICABLE — <concrete reason>"
            ]
        return []
    if len(tables) != 1:
        return ["QAS-SECTION: exactly one Quality attribute scenarios table is required"]

    issues: list[str] = []
    seen: set[str] = set()
    for row in tables[0][2:]:
        row_id = clean_cell(row[0]) if row else "QAS-UNKNOWN"
        if len(row) != len(QAS_HEADERS):
            issues.append(
                f"{row_id}: QAS row must have exactly {len(QAS_HEADERS)} fields"
            )
            continue
        if QAS_ID.fullmatch(row_id) is None:
            issues.append(f"{row_id}: QAS ID must use QAS-nnn")
            continue
        if row_id in seen:
            issues.append(f"{row_id}: QAS ID is duplicated")
        seen.add(row_id)
        for field_name, value in zip(QAS_HEADERS[1:], row[1:]):
            if unresolved(value):
                issues.append(f"{row_id}: {field_name} is unresolved")
        try:
            basis = parse_exact_id_list(row[1], STABLE_CONTRACT_ID, "Requirement IDs")
        except ValueError as exc:
            issues.append(f"{row_id}: {exc}")
        else:
            unknown = sorted(set(basis) - requirement_ids)
            if unknown:
                issues.append(
                    f"{row_id}: Requirement IDs reference unknown requirements: "
                    + ", ".join(unknown)
                )
        if not unresolved(row[7]) and not measurable_acceptance_is_bound(row[7]):
            issues.append(
                f"{row_id}: Response measure requires an explicit observable bound"
            )
    return issues


def validate_gate_a_method_contract(
    ctx: Context,
    text: str,
    *,
    grandfather_approved_v1: bool = False,
) -> None:
    """Fail closed on the Fastlane EARS Contract at Gate A boundaries."""

    found = False
    legacy_rows: list[str] = []
    modern_tables = 0
    for table in markdown_tables(text):
        if not table:
            continue
        headers = tuple(table[0])
        if headers == LEGACY_REQUIREMENT_HEADERS:
            found = True
            legacy_rows.extend(
                clean_cell(row[0]) if row else "REQ-UNKNOWN"
                for row in table[2:]
            )
            continue
        if headers != NORMATIVE_REQUIREMENT_HEADERS:
            continue
        found = True
        modern_tables += 1
        for row in table[2:]:
            row_id = clean_cell(row[0]) if row else "REQ-UNKNOWN"
            if len(row) != len(NORMATIVE_REQUIREMENT_HEADERS):
                ctx.error(
                    "REQUIREMENT_METHOD_CONTRACT",
                    f"{row_id}: normative requirement row must have exactly five fields",
                    PRD_FILE,
                )
                continue
            for issue in requirement_method_issues(*row):
                ctx.error("REQUIREMENT_METHOD_CONTRACT", issue, PRD_FILE)
    if not found:
        ctx.error(
            "REQUIREMENT_METHOD_CONTRACT",
            "REQ-SECTION: no authoritative normative requirement table was found",
            PRD_FILE,
        )
        return

    legacy_is_grandfathered = bool(
        grandfather_approved_v1 and legacy_rows and modern_tables == 0
    )
    if legacy_rows and not legacy_is_grandfathered:
        for row_id in legacy_rows:
            ctx.error(
                "REQUIREMENT_METHOD_MIGRATION_REQUIRED",
                f"{row_id}: migrate the complete normative table to the Fastlane "
                "EARS Contract before Gate A can become ready",
                PRD_FILE,
            )
    if legacy_is_grandfathered:
        return

    requirement_ids = authoritative_requirement_ids(text)
    for issue in quality_attribute_scenario_issues(text, requirement_ids):
        ctx.error("QAS_CONTRACT", issue, PRD_FILE)


def current_prd_basis_ids(
    text: str,
    design_revision: str | None,
) -> set[str]:
    """Return stable IDs actually declared outside the technology register."""

    identifiers = authoritative_requirement_ids(text)
    if design_revision is not None:
        identifiers.add(design_revision)
    try:
        document = table_after_heading(text, "## Document status")
    except ValueError:
        document = {}
    for field in (
        "Current requirements revision",
        "Current design revision",
        "Current construction authorization ID",
    ):
        value = clean_cell(document.get(field, ""))
        if STABLE_CONTRACT_ID.fullmatch(value) is not None:
            identifiers.add(value)
    technology_headers = list(TECHNOLOGY_DECISION_HEADERS)
    for table in markdown_tables(text):
        if not table or table[0] == technology_headers:
            continue
        for row in table[2:]:
            if row and STABLE_CONTRACT_ID.fullmatch(row[0]) is not None:
                identifiers.add(row[0])
    return identifiers


def _exact_property_ids(value: str) -> list[str]:
    cleaned = clean_cell(value)
    if unresolved(cleaned):
        raise ValueError("property IDs are unresolved")
    identifiers = [item.strip() for item in cleaned.split(",")]
    if not identifiers or any(PROPERTY_ID.fullmatch(item) is None for item in identifiers):
        raise ValueError("property IDs must be comma-separated PROP-nnn IDs")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("property ID list contains duplicates")
    return identifiers


def _canonical_id_list(
    value: str,
    pattern: re.Pattern[str],
    field_name: str,
) -> list[str]:
    """Parse a stable ID list and require its exact comma-space representation."""

    identifiers = parse_exact_id_list(value, pattern, field_name)
    if clean_cell(value) != ", ".join(identifiers):
        raise ValueError(f"{field_name} must use comma-space-separated IDs")
    return identifiers


def _none_with_reason(value: str) -> bool:
    cleaned = clean_cell(value)
    return bool(re.fullmatch(r"NONE\s+(?:-|—)\s+\S.*", cleaned)) and not unresolved(cleaned)


def _coverage_domain_list(value: str, field_name: str) -> list[str]:
    cleaned = clean_cell(value)
    if unresolved(cleaned):
        raise ValueError(f"{field_name} is unresolved")
    values = [item.strip() for item in cleaned.split(",")]
    if not values or any(item not in COVERAGE_DOMAINS for item in values):
        raise ValueError(
            f"{field_name} must use comma-separated canonical coverage domains"
        )
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} contains duplicate domains")
    if cleaned != ", ".join(values):
        raise ValueError(f"{field_name} must use comma-space-separated domains")
    return values


def _coverage_omissions(value: str) -> list[CoverageOmission]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return []
    if unresolved(cleaned):
        raise ValueError("Omitted sections and reasons is unresolved")
    omissions: list[CoverageOmission] = []
    seen: set[str] = set()
    for item in cleaned.split("; "):
        section, separator, reason = item.partition(": ")
        if not separator or section not in COVERAGE_DOMAINS:
            raise ValueError(
                "Omissions must use SECTION: concrete reason entries separated by semicolon-space"
            )
        if section in seen:
            raise ValueError(f"Omitted section {section} is duplicated")
        if not explicit_value(reason, allow_none=False):
            raise ValueError(f"Omitted section {section} requires a concrete reason")
        seen.add(section)
        omissions.append(CoverageOmission(section, reason))
    return omissions


def derive_coverage_contract(
    text: str,
    requirements_revision: str | None,
    delivery_profile: str | None,
    effective_risk: str | None,
    aws_lane: str | None,
    *,
    required: bool,
    grandfather_current_gate_a: bool,
) -> tuple[CoverageContract, list[str]]:
    issues: list[str] = []
    try:
        table = contract_table_after_heading(
            text, COVERAGE_PLAN_HEADING, COVERAGE_PLAN_HEADERS
        )
    except ValueError as exc:
        table = None
        issues.append(f"{COVERAGE_PLAN_HEADING}: {exc}")
    if table is None:
        if grandfather_current_gate_a and not issues:
            return (
                CoverageContract(
                    status="READY",
                    required_sections=COVERAGE_DOMAINS,
                    compatibility_full_coverage=True,
                ),
                [],
            )
        if required and not issues:
            issues.append(f"Missing {COVERAGE_PLAN_HEADING}")
        return CoverageContract(status="BLOCKED" if required else "UNINITIALIZED"), issues
    if len(table.rows) != 1:
        issues.append("Adaptive coverage plan must contain exactly one row")
        return CoverageContract(status="BLOCKED", canonical_bytes=table.canonical_bytes), issues

    row = table.rows[0]
    if not required and any(unresolved(cell) for cell in row):
        return (
            CoverageContract(
                status="UNINITIALIZED", canonical_bytes=table.canonical_bytes
            ),
            [],
        )
    work_kind, profile, disposition, required_value, omitted_value, basis_value = row
    if work_kind not in WORK_KINDS:
        issues.append(f"Adaptive coverage has invalid work kind {work_kind!r}")
    if profile not in DELIVERY_PROFILES:
        issues.append(f"Adaptive coverage has invalid delivery profile {profile!r}")
    elif profile != delivery_profile:
        issues.append("Adaptive coverage delivery profile must match Document status")
    if disposition not in ARCHITECTURE_DISPOSITIONS:
        issues.append(
            f"Adaptive coverage has invalid architecture disposition {disposition!r}"
        )
    if work_kind == "NEW_BUILD" and disposition != "SELECT":
        issues.append("NEW_BUILD requires architecture disposition SELECT")

    required_sections: list[str] = []
    omissions: list[CoverageOmission] = []
    basis_ids: list[str] = []
    try:
        required_sections = _coverage_domain_list(required_value, "Required sections")
    except ValueError as exc:
        issues.append(str(exc))
    try:
        omissions = _coverage_omissions(omitted_value)
    except ValueError as exc:
        issues.append(str(exc))
    for omission in omissions:
        if STABLE_CONTRACT_ID.search(omission.reason) is None and "REPOSITORY_BASELINE" not in omission.reason:
            issues.append(
                f"Omitted section {omission.section} requires a requirement ID or REPOSITORY_BASELINE basis"
            )
    omitted_sections = {item.section for item in omissions}
    if set(required_sections) & omitted_sections:
        issues.append("Coverage domains cannot be both required and omitted")
    if set(required_sections) | omitted_sections != set(COVERAGE_DOMAINS):
        issues.append(
            "Required and omitted coverage domains must partition every canonical domain"
        )

    minimum = set(ALWAYS_REQUIRED_COVERAGE)
    if disposition in {"SELECT", "AMEND"}:
        minimum.update({"ARCHITECTURE_COMPARISON", "AWS_EVIDENCE"})
    if effective_risk in {"high", "critical"}:
        minimum.update(COVERAGE_DOMAINS)
    if aws_lane in {"read-only", "fast-dev", "explicit-gate"}:
        minimum.add("AWS_EVIDENCE")
    missing_minimum = sorted(minimum - set(required_sections))
    requirement_ids = authoritative_requirement_ids(text)
    if any(identifier.startswith("DATA-") for identifier in requirement_ids):
        minimum.add("DATA")
    if any(identifier.startswith("REL-") for identifier in requirement_ids):
        minimum.add("RELIABILITY_RECOVERY")
    if missing_minimum:
        issues.append(
            "Adaptive coverage omits mandatory domains: " + ", ".join(missing_minimum)
        )

    try:
        basis_ids = _canonical_id_list(
            basis_value, STABLE_CONTRACT_ID, "Adaptive coverage Basis IDs"
        )
        expected = [
            identifier
            for identifier in [requirements_revision, *sorted(authoritative_requirement_ids(text))]
            if identifier
        ]
        if basis_ids != expected:
            issues.append(
                "Adaptive coverage Basis IDs must exactly bind the current requirements: "
                + ", ".join(expected)
            )
    except ValueError as exc:
        issues.append(str(exc))

    digest = "sha256:" + hashlib.sha256(table.canonical_bytes).hexdigest()
    return (
        CoverageContract(
            status="READY" if not issues else "BLOCKED",
            work_kind=work_kind,
            delivery_profile=profile,
            architecture_disposition=disposition,
            required_sections=tuple(required_sections),
            omissions=tuple(omissions),
            basis_ids=tuple(basis_ids),
            canonical_sha256=digest,
            canonical_bytes=table.canonical_bytes,
        ),
        issues,
    )


def derive_change_impact_contract(
    text: str,
    coverage: CoverageContract,
    allowed_ids: set[str],
    *,
    required: bool,
) -> tuple[ChangeImpactContract, list[str]]:
    issues: list[str] = []
    try:
        table = contract_table_after_heading(
            text, CHANGE_IMPACT_HEADING, CHANGE_IMPACT_HEADERS
        )
    except ValueError as exc:
        table = None
        issues.append(f"{CHANGE_IMPACT_HEADING}: {exc}")
    if table is None:
        if required and not issues:
            issues.append(f"Missing {CHANGE_IMPACT_HEADING}")
        return ChangeImpactContract(status="BLOCKED" if required else "UNINITIALIZED"), issues

    if not required and any(unresolved(cell) for row in table.rows for cell in row):
        return (
            ChangeImpactContract(
                status="UNINITIALIZED", canonical_bytes=table.canonical_bytes
            ),
            [],
        )
    rows: list[ChangeImpactRow] = []
    seen: set[str] = set()
    stale_targets: set[str] = set()
    disposition = coverage.architecture_disposition
    needs_rows = required and disposition in {"AMEND", "PRESERVE"}
    if needs_rows and not table.rows:
        issues.append(f"{disposition} requires at least one change-impact row")

    for raw_row in table.rows:
        row = ChangeImpactRow(*raw_row)
        rows.append(row)
        if CHANGE_ID.fullmatch(row.change_id) is None:
            issues.append(f"Invalid change-impact ID {row.change_id!r}")
        elif row.change_id in seen:
            issues.append(f"Duplicate change-impact ID {row.change_id}")
        seen.add(row.change_id)
        parsed: dict[str, list[str]] = {}
        for label, value in (
            ("Changed basis IDs", row.changed_basis_ids),
            ("Affected IDs", row.affected_ids),
        ):
            try:
                parsed[label] = _canonical_id_list(value, STABLE_CONTRACT_ID, label)
                unknown = sorted(set(parsed[label]) - allowed_ids)
                if unknown:
                    issues.append(
                        f"{row.change_id}: {label} contains unknown IDs: "
                        + ", ".join(unknown)
                    )
            except ValueError as exc:
                issues.append(f"{row.change_id}: {exc}")
                parsed[label] = []
        if row.preserved_ids == "NONE":
            parsed["Preserved IDs"] = []
        else:
            try:
                parsed["Preserved IDs"] = _canonical_id_list(
                    row.preserved_ids, STABLE_CONTRACT_ID, "Preserved IDs"
                )
                unknown = sorted(set(parsed["Preserved IDs"]) - allowed_ids)
                if unknown:
                    issues.append(
                        f"{row.change_id}: Preserved IDs contains unknown IDs: "
                        + ", ".join(unknown)
                    )
            except ValueError as exc:
                issues.append(f"{row.change_id}: {exc}")
                parsed["Preserved IDs"] = []
        overlap = sorted(set(parsed["Affected IDs"]) & set(parsed["Preserved IDs"]))
        if overlap:
            issues.append(
                f"{row.change_id}: IDs cannot be both affected and preserved: "
                + ", ".join(overlap)
            )
        if row.required_revalidation == "FULL_REVALIDATION":
            stale_targets.update({"GATE_A", "GATE_B", "TASKS", "AWS_AUTHORITY"})
        else:
            try:
                revalidation_ids = _canonical_id_list(
                    row.required_revalidation,
                    STABLE_CONTRACT_ID,
                    "Required revalidation",
                )
                unknown = sorted(set(revalidation_ids) - allowed_ids)
                if unknown:
                    issues.append(
                        f"{row.change_id}: Required revalidation contains unknown IDs: "
                        + ", ".join(unknown)
                    )
            except ValueError as exc:
                issues.append(f"{row.change_id}: {exc}")
        changed = set(parsed["Changed basis IDs"])
        affected = set(parsed["Affected IDs"])
        if any(identifier in authoritative_requirement_ids(text) for identifier in changed):
            stale_targets.update({"GATE_A", "GATE_B", "TASKS", "AWS_AUTHORITY"})
        elif changed or affected:
            stale_targets.update({"GATE_B", "TASKS", "AWS_AUTHORITY"})
        if disposition == "PRESERVE":
            controlled = sorted(
                identifier
                for identifier in changed | affected
                if re.match(r"^(?:DRV|CAND|ARCH|TECH|HARNESS|AWS-EV)-", identifier)
            )
            if controlled:
                issues.append(
                    f"{row.change_id}: PRESERVE cannot change architecture-controlled IDs: "
                    + ", ".join(controlled)
                )
        if disposition == "AMEND" and not any(
            re.match(r"^(?:DRV|CAND|ARCH|TECH|HARNESS|AWS-EV)-", identifier)
            for identifier in affected
        ):
            issues.append(
                f"{row.change_id}: AMEND must identify at least one affected design ID"
            )

    digest = "sha256:" + hashlib.sha256(table.canonical_bytes).hexdigest()
    return (
        ChangeImpactContract(
            status="READY" if not issues else "BLOCKED",
            rows=tuple(rows),
            stale_targets=tuple(sorted(stale_targets)),
            canonical_sha256=digest,
            canonical_bytes=table.canonical_bytes,
        ),
        issues,
    )


def _derive_architecture_contract(
    text: str,
    design_revision: str | None,
    technology_ids: set[str],
    *,
    required: bool,
    grandfather_approved_v1: bool = False,
) -> tuple[ArchitectureContract, list[str]]:
    issues: list[str] = []
    specifications = (
        ("drivers", ARCHITECTURE_DRIVER_HEADING, ARCHITECTURE_DRIVER_HEADERS),
        ("candidates", ARCHITECTURE_CANDIDATE_HEADING, ARCHITECTURE_CANDIDATE_HEADERS),
        ("selection", ARCHITECTURE_SELECTION_HEADING, ARCHITECTURE_SELECTION_HEADERS),
        ("traceability", ARCHITECTURE_TRACEABILITY_HEADING, ARCHITECTURE_TRACEABILITY_HEADERS),
        ("evidence", MATERIAL_AWS_EVIDENCE_HEADING, MATERIAL_AWS_EVIDENCE_HEADERS),
    )
    tables: dict[str, ContractTable | None] = {}
    parse_issues: list[str] = []
    selection_schema_version = 3
    evidence_schema_version = 2
    for key, heading, headers in specifications:
        try:
            tables[key] = contract_table_after_heading(text, heading, headers)
        except ValueError as current_exc:
            if key == "selection" and grandfather_approved_v1:
                try:
                    tables[key] = contract_table_after_heading(
                        text, heading, ARCHITECTURE_SELECTION_HEADERS_V2
                    )
                    selection_schema_version = 2
                    continue
                except ValueError as legacy_exc:
                    current_exc = legacy_exc
            if key == "evidence" and grandfather_approved_v1:
                try:
                    tables[key] = contract_table_after_heading(
                        text, heading, MATERIAL_AWS_EVIDENCE_HEADERS_V1
                    )
                    evidence_schema_version = 1
                    continue
                except ValueError as legacy_exc:
                    current_exc = legacy_exc
            tables[key] = None
            parse_issues.append(f"{heading}: {current_exc}")
    issues.extend(parse_issues)

    all_missing = all(tables[key] is None for key, _, _ in specifications)
    gate_b_state = ""
    try:
        gate_b_state = table_after_heading(text, "## Document status").get(
            "Gate B derived status", ""
        )
    except ValueError:
        pass
    grandfathered = all_missing and (
        grandfather_approved_v1
        or gate_b_state == "APPROVED_FOR_CONSTRUCTION"
    )
    if all_missing:
        if required and not grandfathered:
            issues.extend(f"Missing {heading}" for _, heading, _ in specifications)
        return (
            ArchitectureContract(
                schema_version=1,
                status="READY" if grandfathered and not issues else "UNINITIALIZED" if not required else "BLOCKED",
                grandfathered_v1=grandfathered,
            ),
            issues,
        )
    for key, heading, _ in specifications:
        if tables[key] is None:
            issues.append(f"Missing {heading}")

    drivers: list[ArchitectureDriver] = []
    candidates: list[ArchitectureCandidate] = []
    selection: ArchitectureSelection | None = None
    traces: list[ArchitectureTrace] = []
    evidence: list[MaterialAwsEvidence] = []
    requirements = authoritative_requirement_ids(text)
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
                issues.append(f"{driver.driver_id}: invalid driver class {driver.driver_class!r}")
            elif driver.driver_class == "HARD_CONSTRAINT":
                hard_constraint_ids.add(driver.driver_id)
            try:
                basis = _canonical_id_list(
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
                issues.append(f"Invalid architecture candidate ID {candidate.candidate_id!r}")
            elif candidate.candidate_id in seen_candidate_ids:
                issues.append(f"Duplicate architecture candidate ID {candidate.candidate_id}")
            seen_candidate_ids.add(candidate.candidate_id)
            if not explicit_value(candidate.architecture_summary, allow_none=False):
                issues.append(f"{candidate.candidate_id}: architecture summary must be concrete")
            try:
                coverage = _canonical_id_list(
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
                issues.append(f"{candidate.candidate_id}: invalid eligibility {candidate.eligibility!r}")
            if candidate.eligibility == "ELIGIBLE":
                if candidate.failed_constraints != "NONE":
                    issues.append(f"{candidate.candidate_id}: an eligible candidate must have Failed constraints NONE")
            elif candidate.eligibility == "INELIGIBLE":
                try:
                    failed = _canonical_id_list(
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
                issues.append(f"Invalid selected architecture ID {selection.architecture_id!r}")
            if selection.selected_candidate not in seen_candidate_ids:
                issues.append("Selected architecture must reference a current candidate")
            selected = next(
                (item for item in candidates if item.candidate_id == selection.selected_candidate),
                None,
            )
            if selected is not None and selected.eligibility != "ELIGIBLE":
                issues.append("A hard-constraint-failing candidate cannot be selected")
            expected_basis = [*expected_requirement_order, *(item.driver_id for item in drivers)]
            try:
                basis = _canonical_id_list(
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
                    rejected = _canonical_id_list(
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
                    issues.append(f"{selection.architecture_id}: {label} must be concrete")

    trace_table = tables["traceability"]
    seen_trace_requirements: set[str] = set()
    if trace_table is not None:
        for row in trace_table.rows:
            trace = ArchitectureTrace(*row)
            traces.append(trace)
            if trace.requirement_id in seen_trace_requirements:
                issues.append(f"Duplicate architecture traceability requirement {trace.requirement_id}")
            seen_trace_requirements.add(trace.requirement_id)
            if trace.requirement_id not in requirements:
                issues.append(f"Architecture traceability references non-requirement ID {trace.requirement_id}")
            try:
                design_ids = _canonical_id_list(
                    trace.design_ids,
                    ARCHITECTURE_DESIGN_ID,
                    f"{trace.requirement_id} architecture traceability design IDs",
                )
                if selection is not None and selection.architecture_id not in design_ids:
                    issues.append(f"{trace.requirement_id}: traceability must include {selection.architecture_id}")
                if not any(identifier != (selection.architecture_id if selection else "") for identifier in design_ids):
                    issues.append(f"{trace.requirement_id}: traceability must include a component, API, data, or control ID")
            except ValueError as exc:
                issues.append(str(exc))
            if not _none_with_reason(trace.property_test_ids):
                try:
                    _canonical_id_list(
                        trace.property_test_ids,
                        ARCHITECTURE_TEST_ID,
                        f"{trace.requirement_id} property/test IDs",
                    )
                except ValueError as exc:
                    issues.append(str(exc))
        missing_traces = sorted(requirements - seen_trace_requirements)
        extra_traces = sorted(seen_trace_requirements - requirements)
        if missing_traces:
            issues.append("Architecture traceability is missing requirement IDs: " + ", ".join(missing_traces))
        if extra_traces:
            issues.append("Architecture traceability has unknown requirement IDs: " + ", ".join(extra_traces))

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
            if evidence_schema_version == 2 and AWS_DISCOVERY_ID.fullmatch(item.discovery_id) is None:
                issues.append(
                    f"{item.evidence_id}: invalid Discovery ID {item.discovery_id!r}"
                )
            if AWS_MATERIAL_EVIDENCE_ID.fullmatch(item.evidence_id) is None:
                issues.append(f"Invalid material AWS evidence ID {item.evidence_id!r}")
            elif item.evidence_id in seen_evidence_ids:
                issues.append(f"Duplicate material AWS evidence ID {item.evidence_id}")
            seen_evidence_ids.add(item.evidence_id)
            try:
                bound_ids = _canonical_id_list(
                    item.design_ids,
                    STABLE_CONTRACT_ID,
                    f"{item.evidence_id} design IDs",
                )
                evidence_design_ids[item.evidence_id] = set(bound_ids)
                unknown = sorted(set(bound_ids) - declared_design_ids)
                if unknown:
                    issues.append(f"{item.evidence_id}: unknown design IDs: " + ", ".join(unknown))
            except ValueError as exc:
                issues.append(str(exc))
            if not explicit_value(item.material_claim, allow_none=False):
                issues.append(f"{item.evidence_id}: material claim must be concrete")
            if item.capability not in AWS_DOCUMENTATION_CAPABILITIES:
                issues.append(f"{item.evidence_id}: invalid AWS Core capability {item.capability!r}")
            else:
                seen_capabilities.add(item.capability)
            if re.fullmatch(r"https://(?:docs\.)?aws\.amazon\.com/\S+", item.official_reference) is None:
                issues.append(f"{item.evidence_id}: Official reference must be an AWS HTTPS URL")
            try:
                datetime.strptime(item.observed_date, "%Y-%m-%d")
            except ValueError:
                issues.append(f"{item.evidence_id}: Observed date must use YYYY-MM-DD")
        missing_capabilities = sorted(AWS_DOCUMENTATION_CAPABILITIES - seen_capabilities)
        if missing_capabilities:
            issues.append(
                "Material AWS evidence is missing AWS Core capabilities: "
                + ", ".join(missing_capabilities)
            )

    for candidate in candidates:
        try:
            evidence_ids = _canonical_id_list(
                candidate.aws_evidence,
                AWS_MATERIAL_EVIDENCE_ID,
                f"{candidate.candidate_id} AWS evidence",
            )
            unknown = sorted(set(evidence_ids) - seen_evidence_ids)
            if unknown:
                issues.append(f"{candidate.candidate_id}: unknown AWS evidence IDs: " + ", ".join(unknown))
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
        if _none_with_reason(trace.evidence_ids):
            continue
        try:
            evidence_ids = _canonical_id_list(
                trace.evidence_ids,
                AWS_MATERIAL_EVIDENCE_ID,
                f"{trace.requirement_id} evidence IDs",
            )
            unknown = sorted(set(evidence_ids) - seen_evidence_ids)
            if unknown:
                issues.append(f"{trace.requirement_id}: unknown AWS evidence IDs: " + ", ".join(unknown))
        except ValueError as exc:
            issues.append(str(exc))

    try:
        project_mode = table_after_heading(text, "## Document status").get("Project mode", "")
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


def harness_status_parts(value: str) -> tuple[str, str | None]:
    cleaned = clean_cell(value)
    if cleaned == "REQUIRED":
        return "REQUIRED", None
    for prefix in ("CONDITIONAL", "NOT_APPLICABLE"):
        if not cleaned.startswith(prefix):
            continue
        suffix = cleaned[len(prefix):].strip()
        if suffix.startswith("—"):
            suffix = suffix[1:].strip()
        elif suffix.startswith("-"):
            suffix = suffix[1:].strip()
        if suffix and not unresolved(suffix):
            return prefix, suffix
    return "INVALID", None


def derive_harness_contract(
    text: str,
    allowed_basis_ids: set[str],
    *,
    required: bool,
    grandfather_approved_v1: bool,
) -> tuple[HarnessContract, list[str]]:
    """Parse and validate the Gate B Harness Profile as design-controlled data."""

    issues: list[str] = []
    try:
        table = contract_table_after_heading(text, HARNESS_HEADING, HARNESS_HEADERS)
    except ValueError as exc:
        table = None
        issues.append(f"Harness Profile: {exc}")
    if table is None:
        if grandfather_approved_v1:
            return (
                HarnessContract(
                    status="GRANDFATHERED_V1",
                    grandfathered_v1=True,
                ),
                [],
            )
        return HarnessContract(), [f"Missing {HARNESS_HEADING}"]

    rows: list[HarnessRow] = []
    required_ids: list[str] = []
    seen: set[str] = set()
    for raw in table.rows:
        row = HarnessRow(*raw)
        rows.append(row)
        if HARNESS_ID.fullmatch(row.harness_id) is None:
            issues.append(f"{row.harness_id}: invalid Harness ID")
        elif row.harness_id in seen:
            issues.append(f"{row.harness_id}: duplicate Harness ID")
        seen.add(row.harness_id)
        if row.layer not in HARNESS_LAYERS:
            issues.append(f"{row.harness_id}: invalid Harness layer {row.layer!r}")
        if unresolved(row.trigger):
            issues.append(f"{row.harness_id}: Trigger is unresolved")
        try:
            basis = _canonical_id_list(
                row.basis_ids,
                STABLE_CONTRACT_ID,
                f"{row.harness_id} Basis IDs",
            )
        except ValueError as exc:
            issues.append(str(exc))
            basis = []
        unknown = sorted(set(basis) - allowed_basis_ids)
        if unknown:
            issues.append(
                f"{row.harness_id}: Basis IDs are not current design IDs: "
                + ", ".join(unknown)
            )

        status, reason = harness_status_parts(row.requirement_status)
        if status == "INVALID":
            issues.append(
                f"{row.harness_id}: status must be REQUIRED, CONDITIONAL — "
                "<trigger>, or NOT_APPLICABLE — <reason>"
            )
            continue
        if status == "NOT_APPLICABLE":
            if any(
                clean_cell(value) != "NOT_APPLICABLE"
                for value in (
                    row.selected_check,
                    row.exact_command,
                    row.evidence_destination,
                )
            ):
                issues.append(
                    f"{row.harness_id}: NOT_APPLICABLE rows must use "
                    "NOT_APPLICABLE for check, command/API, and evidence destination"
                )
            if reason is None:
                issues.append(
                    f"{row.harness_id}: NOT_APPLICABLE requires a concrete reason"
                )
            continue

        if unresolved(row.selected_check):
            issues.append(f"{row.harness_id}: Selected check or tool is unresolved")
        if not valid_property_execution_command(row.exact_command):
            issues.append(
                f"{row.harness_id}: Exact command or API must be one concrete command"
            )
        if row.evidence_destination != HARNESS_EVIDENCE_DESTINATION:
            issues.append(
                f"{row.harness_id}: Evidence destination must be exactly "
                f"{HARNESS_EVIDENCE_DESTINATION}"
            )
        if status == "CONDITIONAL":
            if reason is None:
                issues.append(f"{row.harness_id}: CONDITIONAL requires a concrete trigger")
            if required:
                issues.append(
                    f"{row.harness_id}: CONDITIONAL must resolve to REQUIRED or "
                    "NOT_APPLICABLE before Gate B"
                )
        else:
            required_ids.append(row.harness_id)

    canonical = table.canonical_bytes
    digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return (
        HarnessContract(
            schema_version=2,
            status="READY" if not issues else "BLOCKED",
            rows=tuple(rows),
            required_ids=tuple(required_ids),
            canonical_sha256=digest,
            canonical_bytes=canonical,
        ),
        issues,
    )


def derive_design_contract(
    text: str,
    design_revision: str | None,
    *,
    required: bool = False,
    grandfather_approved_v1: bool = False,
    coverage_contract: CoverageContract | None = None,
) -> tuple[DesignContract, list[str]]:
    issues: list[str] = []
    if coverage_contract is None:
        try:
            document = table_after_heading(text, "## Document status")
        except ValueError:
            document = {}
        coverage_contract, coverage_issues = derive_coverage_contract(
            text,
            clean_cell(document.get("Current requirements revision", "")) or None,
            clean_cell(document.get("Delivery profile", "")) or None,
            clean_cell(document.get("Effective risk", "")) or None,
            clean_cell(document.get("AWS lane", "")) or None,
            required=required,
            grandfather_current_gate_a=grandfather_approved_v1,
        )
        if required:
            issues.extend(coverage_issues)
    try:
        technology_table = contract_table_after_heading(
            text, TECHNOLOGY_DECISION_HEADING, TECHNOLOGY_DECISION_HEADERS
        )
    except ValueError as exc:
        technology_table = None
        issues.append(f"Technology decision register: {exc}")
    try:
        execution_table = contract_table_after_heading(
            text, PROPERTY_EXECUTION_HEADING, PROPERTY_EXECUTION_HEADERS
        )
    except ValueError as exc:
        execution_table = None
        issues.append(f"Property execution contract: {exc}")

    both_missing = technology_table is None and execution_table is None and not issues
    if technology_table is None:
        issues.append(f"Missing {TECHNOLOGY_DECISION_HEADING}")
    if execution_table is None:
        issues.append(f"Missing {PROPERTY_EXECUTION_HEADING}")

    technologies: list[TechnologyDecision] = []
    seen_technology_ids: set[str] = set()
    concern_counts: dict[str, int] = {}
    allowed_basis_ids = current_prd_basis_ids(text, design_revision)
    if technology_table is not None:
        if not technology_table.rows:
            issues.append("Technology decision register has no stored rows")
        for row in technology_table.rows:
            decision = TechnologyDecision(*row)
            technologies.append(decision)
            if TECHNOLOGY_DECISION_ID.fullmatch(decision.decision_id) is None:
                issues.append(f"Invalid technology decision ID {decision.decision_id!r}")
            elif decision.decision_id in seen_technology_ids:
                issues.append(f"Duplicate technology decision ID {decision.decision_id}")
            seen_technology_ids.add(decision.decision_id)
            if TECHNOLOGY_CONCERN.fullmatch(decision.concern) is None:
                issues.append(
                    f"{decision.decision_id}: invalid technology concern {decision.concern!r}"
                )
            concern_counts[decision.concern] = concern_counts.get(decision.concern, 0) + 1
            if any(technology_contract_value_is_unresolved(cell) for cell in row):
                issues.append(f"{decision.decision_id}: unresolved technology decision cell")
            if not unresolved(decision.selection) and not valid_technology_selection(
                decision.selection
            ):
                issues.append(
                    f"{decision.decision_id}: invalid selection {decision.selection!r}; "
                    "use NOT_APPLICABLE — <reason> when the concern does not apply"
                )
            if not unresolved(decision.version_policy) and not valid_technology_version_policy(
                decision.version_policy
            ):
                issues.append(
                    f"{decision.decision_id}: invalid version policy {decision.version_policy!r}"
                )
            if (
                not unresolved(decision.selection)
                and not unresolved(decision.version_policy)
                and technology_value_is_not_applicable(decision.selection)
                != technology_value_is_not_applicable(decision.version_policy)
            ):
                issues.append(
                    f"{decision.decision_id}: Selection and Version policy must both "
                    "use NOT_APPLICABLE — <reason>, or both be applicable"
                )
            if not unresolved(decision.source) and decision.source not in TECHNOLOGY_SOURCES:
                issues.append(f"{decision.decision_id}: invalid source {decision.source!r}")
            if not unresolved(decision.basis_ids):
                if not valid_technology_basis_ids(decision.basis_ids):
                    issues.append(
                        f"{decision.decision_id}: Basis IDs must be exact comma-separated "
                        "stable IDs without prose or duplicates"
                    )
                else:
                    basis_ids = decision.basis_ids.split(", ")
                    unknown_basis_ids = [
                        identifier
                        for identifier in basis_ids
                        if identifier not in allowed_basis_ids
                    ]
                    if unknown_basis_ids:
                        issues.append(
                            f"{decision.decision_id}: Basis IDs are not current PRD IDs: "
                            + ", ".join(unknown_basis_ids)
                        )
                    if design_revision is not None and design_revision not in basis_ids:
                        issues.append(
                            f"{decision.decision_id}: Basis IDs must include current "
                            f"design revision {design_revision}"
                        )
        for concern in REQUIRED_TECHNOLOGY_CONCERNS:
            count = concern_counts.get(concern, 0)
            if count != 1:
                issues.append(
                    f"Technology concern {concern} must appear exactly once; found {count}"
                )

    executions: list[PropertyExecution] = []
    seen_execution_ids: set[str] = set()
    if execution_table is not None:
        for row in execution_table.rows:
            execution = PropertyExecution(*row)
            executions.append(execution)
            if PROPERTY_ID.fullmatch(execution.property_id) is None:
                issues.append(f"Invalid property execution ID {execution.property_id!r}")
            elif execution.property_id in seen_execution_ids:
                issues.append(f"Duplicate property execution ID {execution.property_id}")
            seen_execution_ids.add(execution.property_id)
            if TECHNOLOGY_DECISION_ID.fullmatch(execution.framework_tech_id) is None:
                issues.append(
                    f"{execution.property_id}: invalid Framework TECH ID {execution.framework_tech_id!r}"
                )
            if any(unresolved(cell) for cell in row):
                issues.append(f"{execution.property_id}: unresolved property execution cell")
            if not valid_property_execution_command(execution.exact_command):
                issues.append(
                    f"{execution.property_id}: Exact command must be one explicit "
                    "local command, not prose or placeholder content"
                )
            if not unresolved(execution.run_target_time_bound):
                try:
                    parse_property_run_target(execution.run_target_time_bound)
                except ValueError as exc:
                    issues.append(f"{execution.property_id}: {exc}")
            if not unresolved(
                execution.seed_or_reproduction_format
            ) and not valid_replay_format_contract(
                execution.seed_or_reproduction_format
            ):
                issues.append(
                    f"{execution.property_id}: Seed or reproduction format must "
                    "declare a seed or exact-command replay mode"
                )
            if execution.evidence_destination != PROPERTY_TEST_EVIDENCE_DESTINATION:
                issues.append(
                    f"{execution.property_id}: Evidence destination must be exactly "
                    f"{PROPERTY_TEST_EVIDENCE_DESTINATION}"
                )

    technology_by_id = {
        decision.decision_id: decision for decision in technologies
    }
    for execution in executions:
        property_technology = technology_by_id.get(execution.framework_tech_id)
        if (
            property_technology is None
            or property_technology.concern != "PROPERTY_TESTING"
        ):
            issues.append(
                f"{execution.property_id}: Framework TECH ID must reference the PROPERTY_TESTING decision"
            )
            continue
        if technology_value_is_not_applicable(
            property_technology.selection
        ) or technology_value_is_not_applicable(property_technology.version_policy):
            issues.append(
                f"{property_technology.decision_id}: active property execution cannot "
                "use a NOT_APPLICABLE PROPERTY_TESTING selection or version policy"
            )
        elif not machine_comparable_property_version_policy(
            property_technology.version_policy
        ):
            issues.append(
                f"{property_technology.decision_id}: active property execution "
                "requires an EXACT, COMPATIBLE_MAJOR, or numeric MINIMUM version policy"
            )

    try:
        applicability_table = contract_table_in_section(
            text, PROPERTY_SPECIFICATION_HEADING, PROPERTY_APPLICABILITY_HEADERS
        )
        definition_table = contract_table_in_section(
            text, PROPERTY_SPECIFICATION_HEADING, PROPERTY_DEFINITION_HEADERS
        )
    except ValueError as exc:
        applicability_table = definition_table = None
        issues.append(f"Property-based testing specification: {exc}")
    if applicability_table is None:
        issues.append("Missing exact property applicability table")
    if definition_table is None:
        issues.append("Missing exact property definition table")

    applicable_property_ids: set[str] = set()
    applicable_requirements_by_property: dict[str, set[str]] = {}
    classified_requirement_ids: set[str] = set()
    if applicability_table is not None:
        seen_requirements: set[str] = set()
        for requirement_id, applicability, reason_or_ids in applicability_table.rows:
            if unresolved(requirement_id) or unresolved(applicability) or unresolved(reason_or_ids):
                issues.append("Property applicability row contains unresolved cells")
                continue
            if requirement_id in seen_requirements:
                issues.append(f"Duplicate property applicability requirement {requirement_id}")
            seen_requirements.add(requirement_id)
            if STABLE_CONTRACT_ID.fullmatch(requirement_id) is None:
                issues.append(
                    f"Invalid property applicability requirement ID {requirement_id!r}"
                )
                continue
            classified_requirement_ids.add(requirement_id)
            if applicability == "APPLICABLE":
                try:
                    property_ids = _exact_property_ids(reason_or_ids)
                    applicable_property_ids.update(property_ids)
                    for property_id in property_ids:
                        applicable_requirements_by_property.setdefault(
                            property_id, set()
                        ).add(requirement_id)
                except ValueError as exc:
                    issues.append(f"{requirement_id}: {exc}")
            elif applicability == "NOT_APPLICABLE":
                if (
                    not explicit_value(reason_or_ids, allow_none=False)
                    or EVIDENCE_PLACEHOLDER_PATTERN.search(reason_or_ids) is not None
                ):
                    issues.append(
                        f"{requirement_id}: NOT_APPLICABLE requires a concrete reason"
                    )
            else:
                issues.append(
                    f"{requirement_id}: applicability must be APPLICABLE or NOT_APPLICABLE"
                )
        required_classifications = authoritative_requirement_ids(text)
        missing_classifications = sorted(
            required_classifications - classified_requirement_ids
        )
        unknown_classifications = sorted(
            classified_requirement_ids - required_classifications
        )
        if missing_classifications:
            issues.append(
                "Property applicability is missing current requirement IDs: "
                + ", ".join(missing_classifications)
            )
        if unknown_classifications:
            issues.append(
                "Property applicability references non-requirement IDs: "
                + ", ".join(unknown_classifications)
            )

    definitions: dict[str, tuple[str, ...]] = {}
    if definition_table is not None:
        for row in definition_table.rows:
            property_id = row[0]
            if PROPERTY_ID.fullmatch(property_id) is None:
                issues.append(f"Invalid property definition ID {property_id!r}")
                continue
            if property_id in definitions:
                issues.append(f"Duplicate property definition ID {property_id}")
            definitions[property_id] = row
            for header, value in zip(PROPERTY_DEFINITION_HEADERS[2:], row[2:]):
                if (
                    not explicit_value(value, allow_none=False)
                    or EVIDENCE_PLACEHOLDER_PATTERN.search(value) is not None
                ):
                    issues.append(
                        f"{property_id}: {header} must be concrete semantic content, "
                        "not a placeholder or sentinel"
                    )
    extra_definition_ids = sorted(set(definitions) - applicable_property_ids)
    if extra_definition_ids:
        issues.append(
            "Property definitions are not referenced as APPLICABLE: "
            + ", ".join(extra_definition_ids)
        )
    for property_id in sorted(applicable_property_ids):
        definition = definitions.get(property_id)
        if definition is None:
            issues.append(f"{property_id}: applicable property has no definition")
        elif any(unresolved(cell) for cell in definition):
            issues.append(f"{property_id}: applicable property definition is unresolved")
        else:
            expected_requirement_ids = sorted(
                applicable_requirements_by_property.get(property_id, set())
            )
            expected_requirement_value = ", ".join(expected_requirement_ids)
            if definition[1] != expected_requirement_value:
                issues.append(
                    f"{property_id}: Requirement IDs must exactly match the "
                    "applicability table's current inverse mapping: "
                    f"{expected_requirement_value}"
                )

    execution_ids = {execution.property_id for execution in executions}
    for property_id in sorted(applicable_property_ids - execution_ids):
        issues.append(f"{property_id}: applicable property has no execution row")
    for property_id in sorted(execution_ids - applicable_property_ids):
        issues.append(f"{property_id}: execution row is not referenced as APPLICABLE")

    architecture, architecture_issues = _derive_architecture_contract(
        text,
        design_revision,
        set(technology_by_id),
        required=required,
        grandfather_approved_v1=grandfather_approved_v1,
    )
    issues.extend(architecture_issues)
    harness, harness_issues = derive_harness_contract(
        text,
        allowed_basis_ids | set(technology_by_id),
        required=required,
        grandfather_approved_v1=(
            grandfather_approved_v1 or architecture.grandfathered_v1
        ),
    )
    issues.extend(harness_issues)
    change_impact, change_impact_issues = derive_change_impact_contract(
        text,
        coverage_contract,
        allowed_basis_ids | set(technology_by_id),
        required=required and not grandfather_approved_v1,
    )
    if required:
        issues.extend(change_impact_issues)


    canonical_sha256: str | None = None
    if (
        technology_table is not None
        and applicability_table is not None
        and definition_table is not None
        and execution_table is not None
        and (
            harness.canonical_bytes is not None
            or harness.grandfathered_v1
        )
        and (
            change_impact.canonical_bytes is not None
            or grandfather_approved_v1
        )
    ):
        architecture_bytes = architecture.canonical_bytes or b""
        harness_bytes = harness.canonical_bytes or b""
        change_impact_bytes = change_impact.canonical_bytes or b""
        canonical_sha256 = "sha256:" + hashlib.sha256(
            architecture_bytes
            + harness_bytes
            + change_impact_bytes
            + technology_table.canonical_bytes
            + applicability_table.canonical_bytes
            + definition_table.canonical_bytes
            + execution_table.canonical_bytes
        ).hexdigest()
    status = (
        "UNINITIALIZED"
        if both_missing and not required
        else "READY"
        if not issues
        else "BLOCKED"
    )
    return (
        DesignContract(
            schema_version=(
                architecture.schema_version
                if harness.grandfathered_v1
                else max(4, architecture.schema_version)
            ),
            status=status,
            design_revision=design_revision,
            technology_decisions=tuple(technologies),
            property_execution=tuple(executions),
            architecture=architecture,
            harness=harness,
            canonical_sha256=canonical_sha256,
            change_impact=change_impact,
        ),
        issues,
    )


def canonical_envelope_sha256(prd_text: str) -> str:
    heading = "## 28. Construction envelope"
    structural = without_fenced_code(prd_text)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*$", structural, re.MULTILINE)
    )
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one heading {heading!r}")
    lines = prd_text[matches[0].end() :].splitlines()
    structural_lines = structural[matches[0].end() :].splitlines()
    start = next(
        (index for index, line in enumerate(structural_lines) if line.startswith("|")),
        None,
    )
    if start is None:
        raise ValueError("Construction envelope Markdown table is missing")
    table_lines: list[str] = []
    for line, structural_line in zip(lines[start:], structural_lines[start:]):
        if not structural_line.startswith("|"):
            break
        table_lines.append(line.rstrip())
    if len(table_lines) < 3:
        raise ValueError("Construction envelope Markdown table is malformed")
    payload = ("\n".join(table_lines) + "\n").encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def parse_authorized_ids(value: str) -> list[str]:
    cleaned = clean_cell(value)
    match = re.fullmatch(
        r"REQ: (?P<req>REQ-\d{4,}); DES: (?P<des>DES-\d{4,}); SCOPE_IDS: (?P<scope>.+)",
        cleaned,
    )
    if match is None:
        raise ValueError(
            "Authorized requirement and design IDs must use "
            "REQ: REQ-0001; DES: DES-0001; SCOPE_IDS: FR-001, SEC-001"
        )
    scope = parse_exact_id_list(
        match.group("scope"), AUTHORIZED_ID, "Authorized SCOPE_IDS"
    )
    if not scope:
        raise ValueError("Authorized SCOPE_IDS cannot be NONE")
    ids = [match.group("req"), match.group("des"), *scope]
    if len(ids) != len(set(ids)):
        raise ValueError("Authorized requirement and design IDs contain duplicates")
    return ids


def parse_envelope_paths(value: str, label: str, *, allow_none: bool) -> list[str]:
    cleaned = clean_cell(value)
    if allow_none and cleaned == "NONE":
        return []
    prefix = "PATHS: "
    if not cleaned.startswith(prefix):
        raise ValueError(f"{label} must use PATHS: path; path" + (" or NONE" if allow_none else ""))
    items = [item.strip() for item in cleaned[len(prefix) :].split(";")]
    return parse_task_write_set(",".join(items), label)


def parse_envelope_targets(value: str) -> list[str]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return []
    prefix = "TARGETS: "
    if not cleaned.startswith(prefix):
        raise ValueError("Allowed external-state targets must use TARGETS: target; target or NONE")
    items = [item.strip() for item in cleaned[len(prefix) :].split(";")]
    return parse_task_external_state(",".join(items), "Gate B envelope")


def parse_task_boundary(value: str) -> tuple[str, set[str]]:
    cleaned = clean_cell(value)
    if cleaned == TASK_BOUNDARY_DERIVED:
        return "DERIVED", set()
    prefix = "TASK_IDS: "
    if not cleaned.startswith(prefix):
        raise ValueError(
            "Task boundary must be exactly DERIVED_FROM_AUTHORIZED_IDS_AND_WRITE_SET "
            "or TASK_IDS: TASK-001, TASK-002"
        )
    values = [item.strip() for item in cleaned[len(prefix) :].split(",")]
    if not values or any(TASK_ID.fullmatch(item) is None for item in values):
        raise ValueError("TASK_IDS must contain only comma-separated TASK IDs")
    if len(values) != len(set(values)):
        raise ValueError("TASK_IDS contains duplicates")
    return "EXPLICIT", set(values)


def parse_command_prefixes(value: str) -> list[str]:
    cleaned = clean_cell(value)
    prefix = "ALLOW_PREFIXES: "
    if not cleaned.startswith(prefix):
        raise ValueError("Local command boundary must use ALLOW_PREFIXES: prefix; prefix")
    values = [item.strip() for item in cleaned[len(prefix) :].split(";")]
    if not values or any(not item for item in values):
        raise ValueError("Local command boundary contains an empty prefix")
    if any(SHELL_CONTROL.search(item) or item.startswith(("-", "#")) for item in values):
        raise ValueError("Local command prefixes cannot contain shell-control syntax")
    if len(values) != len(set(values)):
        raise ValueError("Local command boundary contains duplicate prefixes")
    return values


def validation_commands(section: str, task_id: str) -> list[str]:
    fences = re.findall(r"^```[^\r\n]*\r?\n(.*?)^```\s*$", section, re.MULTILINE | re.DOTALL)
    commands: list[str] = []
    for body in fences:
        for raw_line in body.splitlines():
            command = raw_line.strip()
            if not command or command.startswith("#"):
                continue
            if command.startswith("$ "):
                command = command[2:].strip()
            if SHELL_CONTROL.search(command):
                raise ValueError(f"{task_id}: Validation command contains shell-control syntax")
            commands.append(command)
    if not commands:
        raise ValueError(f"{task_id}: Validation requires at least one fenced command")
    return commands


def command_matches_prefix(command: str, prefix: str) -> bool:
    return command == prefix or command.startswith(prefix + " ")


def parse_github_constraints(value: str, boundary: str) -> str | None:
    cleaned = clean_cell(value)
    if boundary in {"NONE", "READ_ONLY"}:
        if cleaned != "NONE":
            raise ValueError(f"GitHub boundary {boundary} requires constraints NONE")
        return None
    match = GITHUB_CONSTRAINT.fullmatch(cleaned)
    if match is None:
        raise ValueError(
            "GitHub write constraints must be exactly "
            "REPO: owner/name; BRANCH: branch; MERGE: ALLOWED|PROHIBITED"
        )
    branch = match.group("branch")
    if (
        branch.startswith(("/", "-"))
        or branch.endswith("/")
        or "//" in branch
        or ".." in branch
        or "@{" in branch
    ):
        raise ValueError("GitHub branch constraint is unsafe")
    merge = match.group("merge")
    expected_merge = "ALLOWED" if boundary == "MERGE_WHEN_GREEN" else "PROHIBITED"
    if merge != expected_merge:
        raise ValueError(f"GitHub boundary {boundary} requires MERGE: {expected_merge}")
    return match.group("repo")


def parse_future_expiry(value: str) -> datetime:
    cleaned = clean_cell(value)
    match = re.fullmatch(
        r"Expires at (?P<timestamp>[^\s;]+); earlier completion: (?P<condition>[^\r\n]+)",
        cleaned,
    )
    if match is None:
        raise ValueError(
            "Authorization expiry must use Expires at <ISO8601>; earlier completion: <exact condition>"
        )
    if not explicit_value(match.group("condition"), allow_none=False):
        raise ValueError("Authorization earlier-completion condition must be explicit")
    candidate = match.group("timestamp")
    normalized = candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate
    try:
        expires_at = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Authorization expiry timestamp is not ISO 8601") from exc
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValueError("Authorization expiry timestamp must include a timezone")
    if expires_at <= datetime.now(timezone.utc):
        raise ValueError("Construction authorization is expired")
    return expires_at


def parse_aws_environment(value: str) -> tuple[str, str]:
    cleaned = clean_cell(value)
    match = AWS_ENVIRONMENT.fullmatch(cleaned)
    if match is None or not explicit_value(match.group("name")):
        raise ValueError(
            "AWS environment must use "
            "ENVIRONMENT: <exact>; CLASS: NON_PRODUCTION|PRODUCTION"
        )
    return match.group("name"), match.group("class")


def validate_aws_artifact(value: str, baseline: str) -> None:
    cleaned = clean_cell(value)
    if AWS_EXACT_ARTIFACT.fullmatch(cleaned) is not None:
        return
    match = AWS_DERIVED_ARTIFACT.fullmatch(cleaned)
    if match is None:
        raise ValueError(
            "AWS artifact authorization must use EXACT_DIGEST: sha256:<64 lowercase> "
            "or DERIVED_FROM_AUTHORIZED_SOURCE: <deterministic rule>"
        )
    rule = match.group("rule")
    if (
        not explicit_value(rule)
        or baseline not in rule
        or "sha256" not in rule.casefold()
    ):
        raise ValueError(
            "Derived AWS artifact authorization must bind the authorized baseline "
            "commit and an exact SHA-256 derivation rule"
        )


def validate_relative_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    pure = PurePosixPath(value)
    if pure.is_absolute() or "\\" in value or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    return value


def has_symlink_component(root: Path, relative: str) -> bool:
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def safe_read_text(ctx: Context, relative: str, *, required: bool = True) -> str | None:
    if validate_relative_path(relative) is None:
        ctx.error("MANIFEST_UNSAFE_PATH", f"Unsafe project-relative path: {relative!r}")
        return None
    if has_symlink_component(ctx.root, relative):
        ctx.error("REQUIRED_FILE_SYMLINK", "Required path contains a symbolic link", relative)
        return None
    path = ctx.root / relative
    if not path.exists():
        if required:
            ctx.error("REQUIRED_FILE_MISSING", "Required file is missing", relative)
        return None
    if not path.is_file():
        ctx.error("REQUIRED_FILE_NOT_REGULAR", "Required path is not a regular file", relative)
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        ctx.error("REQUIRED_FILE_UNREADABLE", f"Unable to read UTF-8 text: {exc}", relative)
        return None
    ctx.texts[relative] = text
    return text


def load_json_document(ctx: Context, relative: str, code: str) -> dict[str, Any] | None:
    text = safe_read_text(ctx, relative)
    if text is None:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        ctx.error(code, f"Expected JSON-compatible YAML: {exc}", relative)
        return None
    if not isinstance(value, dict):
        ctx.error(code, "Top-level value must be an object", relative)
        return None
    return value


def split_table_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def table_after_heading(text: str, heading: str) -> dict[str, str]:
    structural = without_fenced_code(text)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*$", structural, re.MULTILINE)
    )
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one heading {heading!r}; found {len(matches)}")
    lines = text[matches[0].end() :].splitlines()
    structural_lines = structural[matches[0].end() :].splitlines()
    start = next(
        (
            index
            for index, line in enumerate(structural_lines)
            if line.strip().startswith("|")
        ),
        None,
    )
    if start is None:
        raise ValueError(f"No Markdown table after {heading!r}")
    table_lines: list[str] = []
    for line, structural_line in zip(lines[start:], structural_lines[start:]):
        if not structural_line.strip().startswith("|"):
            break
        table_lines.append(line)
    if len(table_lines) < 3:
        raise ValueError(f"Malformed Markdown table after {heading!r}")
    result: dict[str, str] = {}
    for line in table_lines[2:]:
        cells = split_table_row(line)
        if len(cells) < 2:
            continue
        key = clean_cell(cells[0])
        if key in result:
            raise ValueError(f"Duplicate field {key!r} after {heading!r}")
        result[key] = clean_cell(cells[1])
    return result


def marked_receipt(text: str, gate: str) -> str:
    start = f"<!-- bootstrap:{gate}-receipt:start -->"
    end = f"<!-- bootstrap:{gate}-receipt:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"Expected exactly one marked {gate} receipt block")
    body = text.split(start, 1)[1].split(end, 1)[0].strip()
    match = re.fullmatch(r"```text\s*\n(?P<receipt>.*?)\n```", body, re.DOTALL)
    if match is None:
        raise ValueError(f"Marked {gate} receipt must contain one text fence")
    return match.group("receipt").replace("\r\n", "\n").strip()


def exact_selection(
    ctx: Context,
    value: str,
    allowed: set[str],
    code: str,
    field_name: str,
    *,
    allow_unselected: bool,
) -> str | None:
    cleaned = clean_cell(value)
    if cleaned in allowed:
        return cleaned
    if allow_unselected and any(item in cleaned for item in allowed):
        return None
    ctx.error(code, f"{field_name} must be exactly one of {sorted(allowed)}", PRD_FILE)
    return None


def validate_manifest(ctx: Context, manifest: dict[str, Any]) -> None:
    expected_fields = {
        "schema_version",
        "bootstrap_version",
        "python_requires",
        "required_files",
        "canonical_prompt_ids",
        "template_placeholders",
        "control_sha256",
        "source_sha256",
    }
    if set(manifest) != expected_fields:
        ctx.error(
            "MANIFEST_SCHEMA",
            f"Manifest fields must be exactly {sorted(expected_fields)}",
            MANIFEST_FILE,
        )
    if manifest.get("schema_version") != 1:
        ctx.error("MANIFEST_SCHEMA", "Unsupported manifest schema_version", MANIFEST_FILE)
    version = manifest.get("bootstrap_version")
    if not isinstance(version, str) or re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        ctx.error("MANIFEST_VERSION", "bootstrap_version must be semantic version text", MANIFEST_FILE)

    files = manifest.get("required_files")
    if not isinstance(files, list):
        ctx.error("MANIFEST_REQUIRED_FILES", "required_files must be an array", MANIFEST_FILE)
        return
    seen: set[str] = set()
    folded: set[str] = set()
    for item in files:
        relative = validate_relative_path(item)
        if relative is None:
            ctx.error("MANIFEST_UNSAFE_PATH", f"Unsafe required_files entry: {item!r}", MANIFEST_FILE)
            continue
        if relative in seen or relative.casefold() in folded:
            ctx.error("MANIFEST_DUPLICATE_PATH", f"Duplicate required path: {relative}", MANIFEST_FILE)
            continue
        seen.add(relative)
        folded.add(relative.casefold())
        safe_read_text(ctx, relative)
    missing_mandatory = sorted(MANDATORY_REQUIRED_FILES - seen)
    if missing_mandatory:
        ctx.error(
            "MANIFEST_REQUIRED_BASELINE",
            "Manifest omits mandatory control files: " + ", ".join(missing_mandatory),
            MANIFEST_FILE,
        )
    if set(manifest.get("template_placeholders", [])) != CANONICAL_PLACEHOLDERS:
        ctx.error(
            "MANIFEST_PLACEHOLDERS",
            "template_placeholders must contain the canonical render tokens",
            MANIFEST_FILE,
        )
    source_hashes = manifest.get("source_sha256")
    expected_source_paths = seen - {MANIFEST_FILE}
    if not isinstance(source_hashes, dict) or set(source_hashes) != expected_source_paths:
        ctx.error(
            "MANIFEST_SOURCE_HASHES",
            "source_sha256 must map every required file except the manifest itself",
            MANIFEST_FILE,
        )
    else:
        for relative in sorted(expected_source_paths):
            expected = source_hashes.get(relative)
            if (
                not isinstance(expected, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected) is None
            ):
                ctx.error(
                    "MANIFEST_SOURCE_HASHES",
                    f"Invalid source SHA-256 for {relative}",
                    MANIFEST_FILE,
                )
                continue
            if ctx.template_source and not has_symlink_component(ctx.root, relative):
                try:
                    actual = hashlib.sha256((ctx.root / relative).read_bytes()).hexdigest()
                except OSError as exc:
                    ctx.error(
                        "MANIFEST_SOURCE_HASHES",
                        f"Unable to hash template source: {exc}",
                        relative,
                    )
                    continue
                if actual != expected:
                    ctx.error(
                        "MANIFEST_SOURCE_HASHES",
                        f"Template source hash mismatch for {relative}",
                        relative,
                    )
    controls = manifest.get("control_sha256")
    if not isinstance(controls, dict) or set(controls) != CONTROL_HASH_FILES:
        ctx.error(
            "MANIFEST_CONTROL_HASHES",
            "control_sha256 must map exactly the trusted runtime control files",
            MANIFEST_FILE,
        )
        return
    for relative in sorted(CONTROL_HASH_FILES):
        expected = controls.get(relative)
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            ctx.error(
                "MANIFEST_CONTROL_HASHES",
                f"Invalid SHA-256 for trusted control {relative}",
                MANIFEST_FILE,
            )
            continue
        if has_symlink_component(ctx.root, relative):
            continue
        try:
            actual = hashlib.sha256((ctx.root / relative).read_bytes()).hexdigest()
        except OSError as exc:
            ctx.error(
                "CONTROL_HASH_UNREADABLE",
                f"Unable to hash trusted control: {exc}",
                relative,
            )
            continue
        if actual != expected:
            ctx.error(
                "CONTROL_HASH_MISMATCH",
                f"Trusted runtime control hash mismatch: expected {expected}, observed {actual}",
                relative,
            )


def validate_prompt_pack(ctx: Context, manifest: dict[str, Any], state: dict[str, Any]) -> None:
    text = ctx.texts.get(PROMPT_FILE) or safe_read_text(ctx, PROMPT_FILE)
    if text is None:
        return
    version_match = re.search(r"^\*\*Pack version:\*\*\s*(\d+\.\d+\.\d+)\s*$", text, re.MULTILINE)
    if version_match is None:
        ctx.error("PROMPT_VERSION_MISSING", "Prompt pack version is missing", PROMPT_FILE)
    else:
        versions = {
            str(manifest.get("bootstrap_version")),
            str(state.get("bootstrap_version")),
            version_match.group(1),
        }
        if len(versions) != 1:
            ctx.error("BOOTSTRAP_VERSION_DRIFT", f"Version values disagree: {sorted(versions)}")

    expected = manifest.get("canonical_prompt_ids")
    actual = re.findall(r"^##\s+([A-Z]+-\d{2})\s+", text, re.MULTILINE)
    if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
        ctx.error("PROMPT_IDS_MANIFEST", "canonical_prompt_ids must be an array of strings", MANIFEST_FILE)
    elif actual != expected:
        ctx.error("PROMPT_IDS_DRIFT", f"Prompt headings do not match manifest order: {actual}", PROMPT_FILE)
    elif len(actual) != len(set(actual)):
        ctx.error("PROMPT_IDS_DUPLICATE", "Canonical prompt IDs must be unique", PROMPT_FILE)


def validate_placeholders(ctx: Context) -> None:
    if ctx.template_source:
        return
    excluded = {MANIFEST_FILE, "bootstrap.py", "scripts/bootstrap_doctor.py"}
    for relative, text in sorted(ctx.texts.items()):
        if relative in excluded or relative.startswith("tests/"):
            continue
        for token in sorted(CANONICAL_PLACEHOLDERS):
            if token in text:
                ctx.error(
                    "PLACEHOLDER_UNRESOLVED",
                    f"Unresolved bootstrap placeholder {token!r}",
                    relative,
                )


def validate_state_schema(ctx: Context, state: dict[str, Any]) -> bool:
    expected_top = {
        "schema_version",
        "bootstrap_version",
        "setup",
        "project",
        "lifecycle",
        "execution",
    }
    if set(state) != expected_top:
        ctx.error("STATE_SCHEMA", f"State keys must be exactly {sorted(expected_top)}", STATE_FILE)
    if state.get("schema_version") != 1:
        ctx.error("STATE_SCHEMA", "Unsupported state schema_version", STATE_FILE)

    setup = state.get("setup")
    project = state.get("project")
    lifecycle = state.get("lifecycle")
    execution = state.get("execution")
    if (
        not isinstance(setup, dict)
        or not isinstance(project, dict)
        or not isinstance(lifecycle, dict)
        or not isinstance(execution, dict)
    ):
        ctx.error(
            "STATE_SCHEMA",
            "setup, project, lifecycle, and execution must be objects",
            STATE_FILE,
        )
        return False

    setup_expected = {"status", "method"}
    project_expected = {
        "name",
        "region",
        "cost_posture",
        "mode",
        "delivery_profile",
        "effective_risk",
        "aws_lane",
        "brownfield_baseline",
    }
    lifecycle_expected = {
        "requirements_revision",
        "design_revision",
        "construction_authorization",
        "gate_a",
        "gate_b",
    }
    execution_expected = {
        "plan_revision",
        "plan_state",
        "run_id",
        "coordinator",
        "mode",
        "state",
        "basis",
        "active_tasks",
        "attempts",
        "last_checkpoint",
    }
    for name, value, expected in (
        ("setup", setup, setup_expected),
        ("project", project, project_expected),
        ("lifecycle", lifecycle, lifecycle_expected),
        ("execution", execution, execution_expected),
    ):
        if set(value) != expected:
            ctx.error("STATE_SCHEMA", f"{name} keys must be exactly {sorted(expected)}", STATE_FILE)

    setup_status = setup.get("status")
    setup_method = setup.get("method")
    allowed_setup_statuses = {"UNCONFIGURED_TEMPLATE", "CONFIGURED"}
    if ctx.template_source:
        allowed_setup_statuses.add("{{SETUP_STATUS}}")
    if setup_status not in allowed_setup_statuses:
        ctx.error("STATE_SETUP", "Invalid setup.status", STATE_FILE)
    allowed_methods = {"IN_PLACE", "EXTERNAL_COPY"}
    if ctx.template_source:
        allowed_methods.add("{{SETUP_METHOD}}")
    if setup_method not in allowed_methods:
        ctx.error("STATE_SETUP", "Invalid setup.method", STATE_FILE)
    for key in ("name", "region", "cost_posture"):
        value = project.get(key)
        if not isinstance(value, str) or not value.strip():
            ctx.error("PROJECT_IDENTITY", f"project.{key} must be non-empty text", STATE_FILE)
    cost_posture = project.get("cost_posture")
    if isinstance(cost_posture, str) and not (
        ctx.template_source and cost_posture == "{{COST_POSTURE}}"
    ):
        try:
            parse_cost_posture(cost_posture)
        except ValueError as exc:
            ctx.error("PROJECT_COST_POSTURE", str(exc), STATE_FILE)

    for key, allowed in (
        ("mode", PROJECT_MODES),
        ("delivery_profile", DELIVERY_PROFILES),
        ("effective_risk", RISK_LEVELS),
        ("aws_lane", AWS_LANES),
    ):
        value = project.get(key)
        if value is not None and (not isinstance(value, str) or value not in allowed):
            ctx.error("PROJECT_VOCABULARY", f"Invalid project.{key}: {value!r}", STATE_FILE)
    baseline_state = project.get("brownfield_baseline")
    if not isinstance(baseline_state, str) or baseline_state not in BROWNFIELD_STATES:
        ctx.error("PROJECT_VOCABULARY", "Invalid brownfield_baseline state", STATE_FILE)

    if REQ_ID.fullmatch(str(lifecycle.get("requirements_revision"))) is None:
        ctx.error("STATE_REVISION_ID", "Invalid requirements revision", STATE_FILE)
    if DES_ID.fullmatch(str(lifecycle.get("design_revision"))) is None:
        ctx.error("STATE_REVISION_ID", "Invalid design revision", STATE_FILE)
    if AUTH_ID.fullmatch(str(lifecycle.get("construction_authorization"))) is None:
        ctx.error("STATE_REVISION_ID", "Invalid construction authorization", STATE_FILE)
    gate_a = lifecycle.get("gate_a")
    gate_b = lifecycle.get("gate_b")
    if (
        not isinstance(gate_a, str)
        or gate_a not in GATE_A_STATES
        or not isinstance(gate_b, str)
        or gate_b not in GATE_B_STATES
    ):
        ctx.error("STATE_GATE", "Invalid derived gate state", STATE_FILE)

    run_mode = execution.get("mode")
    run_state_value = execution.get("state")
    if (
        not isinstance(run_mode, str)
        or run_mode not in RUN_MODES
        or not isinstance(run_state_value, str)
        or run_state_value not in RUN_STATES
    ):
        ctx.error("STATE_RUN", "Invalid execution mode or state", STATE_FILE)
    plan = execution.get("plan_revision")
    if plan is not None and PLAN_ID.fullmatch(str(plan)) is None:
        ctx.error("STATE_RUN", "plan_revision must be null or PLAN-nnnn", STATE_FILE)
    plan_state = execution.get("plan_state")
    if not isinstance(plan_state, str) or plan_state not in {"UNINITIALIZED", "CURRENT", "STALE"}:
        ctx.error("STATE_RUN", "plan_state must be UNINITIALIZED, CURRENT, or STALE", STATE_FILE)
    if (plan is None) != (plan_state == "UNINITIALIZED"):
        ctx.error("STATE_RUN", "plan_revision and plan_state are inconsistent", STATE_FILE)
    active = execution.get("active_tasks")
    if not isinstance(active, list) or not all(isinstance(item, str) and TASK_ID.fullmatch(item) for item in active):
        ctx.error("STATE_RUN", "active_tasks must contain only TASK IDs", STATE_FILE)
    elif len(active) != len(set(active)):
        ctx.error("STATE_RUN", "active_tasks contains duplicates", STATE_FILE)
    attempts = execution.get("attempts")
    if not isinstance(attempts, dict) or any(
        TASK_ID.fullmatch(str(key)) is None or not isinstance(value, int) or isinstance(value, bool) or value < 0
        for key, value in (attempts.items() if isinstance(attempts, dict) else [])
    ):
        ctx.error("STATE_RUN", "attempts must map TASK IDs to non-negative integers", STATE_FILE)
    run_id = execution.get("run_id")
    coordinator = execution.get("coordinator")
    run_state = run_state_value if isinstance(run_state_value, str) else ""
    basis = execution.get("basis")
    if run_id is not None and RUN_ID.fullmatch(str(run_id)) is None:
        ctx.error("STATE_RUN", "run_id must be null or RUN-nnnn", STATE_FILE)
    if run_state == "IDLE":
        if (
            run_id is not None
            or coordinator is not None
            or execution.get("mode") != "NONE"
            or execution.get("active_tasks")
        ):
            ctx.error("STATE_RUN", "IDLE execution cannot have a coordinator, run ID, run mode, or active tasks", STATE_FILE)
    else:
        if run_id is None or coordinator is None or execution.get("mode") == "NONE":
            ctx.error("STATE_RUN", "A non-IDLE execution requires a coordinator, run ID, and run mode", STATE_FILE)
        expected_basis_keys = {
            "requirements_revision",
            "design_revision",
            "construction_authorization",
        }
        if not isinstance(basis, dict) or set(basis) != expected_basis_keys:
            ctx.error("STATE_RUN", "A non-IDLE execution requires a complete revision basis", STATE_FILE)
    checkpoint = execution.get("last_checkpoint")
    if checkpoint is not None:
        checkpoint_keys = {"id", "at", "evidence_ref"}
        if not isinstance(checkpoint, dict) or set(checkpoint) != checkpoint_keys:
            ctx.error("STATE_RUN", "last_checkpoint has an invalid shape", STATE_FILE)
        elif (
            CHECKPOINT_ID.fullmatch(str(checkpoint.get("id"))) is None
            or unresolved(str(checkpoint.get("at", "")))
            or unresolved(str(checkpoint.get("evidence_ref", "")))
        ):
            ctx.error("STATE_RUN", "last_checkpoint fields must be explicit", STATE_FILE)
    if run_state in {"CHECKPOINTED", "BLOCKED", "COMPLETE"} and checkpoint is None:
        ctx.error("STATE_RUN", f"{run_state} execution requires a checkpoint", STATE_FILE)
    if run_state == "COMPLETE" and execution.get("active_tasks"):
        ctx.error("STATE_RUN", "COMPLETE execution cannot have active tasks", STATE_FILE)
    if execution.get("state") == "RUNNING":
        ctx.error(
            "RUN_UNCLEAN_INTERRUPTION",
            "Persisted RUNNING state is not safe to resume; reconcile partial work and checkpoint first",
            STATE_FILE,
        )
    return True


def validate_brownfield_contract(ctx: Context, text: str) -> None:
    heading = "### 1.2 Brownfield baseline and preservation contract"
    matches = list(re.finditer(rf"^{re.escape(heading)}\s*$", text, re.MULTILINE))
    if len(matches) != 1:
        ctx.error("BROWNFIELD_PRD_BASELINE", f"Expected exactly one {heading!r}", PRD_FILE)
        return
    next_heading = re.search(r"^##\s+2\.", text[matches[0].end() :], re.MULTILINE)
    end = matches[0].end() + next_heading.start() if next_heading else len(text)
    tables = markdown_tables(text[matches[0].end() : end])
    if len(tables) < 2:
        ctx.error(
            "BROWNFIELD_PRD_BASELINE",
            "Brownfield approval requires both baseline and preservation tables",
            PRD_FILE,
        )
        return

    baseline: dict[str, str] = {}
    for row in tables[0][2:]:
        if len(row) >= 2:
            if row[0] in baseline:
                ctx.error("BROWNFIELD_PRD_BASELINE", f"Duplicate brownfield field {row[0]!r}", PRD_FILE)
            baseline[row[0]] = row[1]
    missing = sorted(BROWNFIELD_BASELINE_FIELDS - set(baseline))
    if missing:
        ctx.error(
            "BROWNFIELD_PRD_BASELINE",
            "Brownfield baseline is missing fields: " + ", ".join(missing),
            PRD_FILE,
        )
    unresolved_fields = sorted(
        field for field in BROWNFIELD_BASELINE_FIELDS if not explicit_value(baseline.get(field, ""), allow_none=True)
    )
    if unresolved_fields:
        ctx.error(
            "BROWNFIELD_PRD_BASELINE",
            "Brownfield baseline has unresolved fields: " + ", ".join(unresolved_fields),
            PRD_FILE,
        )

    preservation_rows = [
        row for row in tables[1][2:] if row and re.fullmatch(r"PRES-\d+", row[0]) is not None
    ]
    if not preservation_rows:
        ctx.error(
            "BROWNFIELD_PRD_PRESERVATION",
            "Brownfield approval requires at least one explicit PRES record",
            PRD_FILE,
        )
    for row in preservation_rows:
        if len(row) < 5 or any(not explicit_value(value, allow_none=False) for value in row[1:5]):
            ctx.error(
                "BROWNFIELD_PRD_PRESERVATION",
                f"{row[0]} must explicitly define the preserved behavior and change boundary",
                PRD_FILE,
            )


def validate_construction_envelope(
    ctx: Context,
    envelope: dict[str, str],
    fields: dict[str, str],
    selections: dict[str, str | None],
    cost_posture: str,
    design_contract: DesignContract,
) -> None:
    missing = sorted(ENVELOPE_EXPLICIT_FIELDS - set(envelope))
    if missing:
        ctx.error("GATE_B_ENVELOPE", "Construction envelope is missing fields: " + ", ".join(missing), PRD_FILE)
    unresolved_fields = sorted(
        field
        for field in ENVELOPE_EXPLICIT_FIELDS
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
            "Construction envelope has unresolved fields: " + ", ".join(unresolved_fields),
            PRD_FILE,
        )

    if envelope.get("Construction authorization ID") != fields.get("construction_authorization"):
        ctx.error("GATE_B_ENVELOPE", "Envelope AUTH does not match current AUTH", PRD_FILE)
    authorized_baseline = envelope.get("Authorized baseline commit", "")
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", authorized_baseline) is None:
        ctx.error("GATE_B_ENVELOPE", "Authorized baseline commit must be a full lowercase Git commit hash", PRD_FILE)
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
            ctx.error("GATE_B_PROJECT_DRIFT", f"Envelope {key} does not exactly match Document status", PRD_FILE)
    try:
        authorized_ids = parse_authorized_ids(
            envelope.get("Authorized requirement and design IDs", "")
        )
        if fields.get("requirements_revision") != authorized_ids[0]:
            ctx.error("GATE_B_ENVELOPE", "Authorized ID basis must include the current REQ revision", PRD_FILE)
        if fields.get("design_revision") != authorized_ids[1]:
            ctx.error("GATE_B_ENVELOPE", "Authorized ID basis must include the current DES revision", PRD_FILE)
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
        or envelope.get("Design contract SHA-256")
        != design_contract.canonical_sha256
    ):
        ctx.error(
            "GATE_B_DESIGN_CONTRACT_HASH",
            "Construction envelope Design contract SHA-256 must equal the current derived design contract hash",
            PRD_FILE,
        )

    if envelope.get("Autonomous construction") not in {"ALLOWED", "PROHIBITED"}:
        ctx.error("GATE_B_ENVELOPE", "Autonomous construction must be ALLOWED or PROHIBITED", PRD_FILE)
    numeric: dict[str, int] = {}
    for key in ("Maximum generated tasks", "Maximum parallel workers", "Attempt budget"):
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
        parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
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
        parse_future_expiry(envelope.get("Authorization expiry or completion condition", ""))
    except ValueError as exc:
        ctx.error("GATE_B_ENVELOPE", str(exc), PRD_FILE)
    if numeric.get("Maximum parallel workers", 1) > 1 and "isolated worktree" not in envelope.get(
        "Parallelism rule", ""
    ).lower():
        ctx.error(
            "GATE_B_ENVELOPE",
            "More than one worker requires disjoint work in isolated worktrees",
            PRD_FILE,
        )

    lane_boundaries = {
        "documentation-only": {"NONE", "DOCS_ONLY"},
        "read-only": {"NONE", "DOCS_ONLY", "READ_ONLY"},
        "fast-dev": {"NONE", "DOCS_ONLY", "READ_ONLY", "MUTATE_LISTED_RESOURCES"},
        "explicit-gate": {"NONE", "DOCS_ONLY", "READ_ONLY", "MUTATE_LISTED_RESOURCES"},
    }
    lane = selections.get("aws_lane")
    if lane in lane_boundaries and envelope.get("AWS boundary") not in lane_boundaries[lane]:
        ctx.error("AWS_LANE_BOUNDARY", "AWS boundary does not match the selected project lane", PRD_FILE)
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
                ctx.error("GATE_B_ENVELOPE", f"{key} is required for READ_ONLY AWS authority", PRD_FILE)
            elif key not in required_read and not (
                explicit_value(value) or value.startswith("NOT_APPLICABLE — ")
            ):
                ctx.error("GATE_B_ENVELOPE", f"{key} must be explicit for READ_ONLY AWS authority", PRD_FILE)
        try:
            parse_aws_environment(envelope.get("AWS environment", ""))
            parse_future_expiry(envelope.get("AWS authorization validity", ""))
        except ValueError as exc:
            ctx.error("GATE_B_ENVELOPE", str(exc), PRD_FILE)
    elif aws_boundary == "MUTATE_LISTED_RESOURCES":
        for key in sorted(AWS_DETAIL_FIELDS):
            value = envelope.get(key, "")
            if not explicit_value(value) or value.startswith("NOT_APPLICABLE — "):
                ctx.error("GATE_B_ENVELOPE", f"{key} is required for AWS mutation authority", PRD_FILE)
        try:
            _environment, environment_class = parse_aws_environment(
                envelope.get("AWS environment", "")
            )
            if lane == "fast-dev" and environment_class != "NON_PRODUCTION":
                raise ValueError("fast-dev AWS mutation authority must be NON_PRODUCTION")
            validate_aws_artifact(
                envelope.get("AWS artifact authorization and provenance", ""),
                envelope.get("Authorized baseline commit", ""),
            )
            validate_aws_cost_ceiling(
                envelope.get("AWS cost ceiling", ""),
                cost_posture,
            )
            parse_future_expiry(envelope.get("AWS authorization validity", ""))
        except ValueError as exc:
            ctx.error("GATE_B_ENVELOPE", str(exc), PRD_FILE)


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
    for field in sorted(expected_fields):
        value = clean_cell(card.get(field, ""))
        if field == "Outstanding gaps" and value == "NONE":
            continue
        if value.startswith("NOT_APPLICABLE — ") and explicit_value(
            value.removeprefix("NOT_APPLICABLE — ")
        ):
            continue
        if not explicit_value(value, allow_none=False):
            ctx.error(
                f"{gate}_READINESS_CARD",
                f"{field} is not an explicit current decision basis",
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
]:
    text = ctx.texts.get(PRD_FILE) or safe_read_text(ctx, PRD_FILE)
    if text is None:
        return {}, {}, {}, False, DesignContract(), CoverageContract()
    try:
        document = table_after_heading(text, "## Document status")
        workload = table_after_heading(text, "## 1. Workload profile")
        gate_a_agent = table_after_heading(text, "### Gate A — agent analysis record")
        gate_a_card = table_after_heading(text, "### Gate A — readiness card")
        gate_a_owner = table_after_heading(text, "### Gate A — owner acceptance record")
        gate_b_agent = table_after_heading(text, "## 27. Gate B agent review record")
        gate_b_card = table_after_heading(text, "### Gate B — readiness card")
        envelope = table_after_heading(text, "## 28. Construction envelope")
        gate_b_owner = table_after_heading(text, "## 29. Gate B owner authorization record")
        envelope_digest = canonical_envelope_sha256(text)
        # Check marker structure even before either gate is approved.
        marked_receipt(text, "gate-a")
        marked_receipt(text, "gate-b")
    except ValueError as exc:
        ctx.error("PRD_STRUCTURE", str(exc), PRD_FILE)
        return {}, {}, {}, False, DesignContract(), CoverageContract()

    project = state.get("project", {})
    lifecycle = state.get("lifecycle", {})
    allow_unselected = project.get("mode") is None
    selections = {
        "mode": exact_selection(
            ctx, document.get("Project mode", ""), PROJECT_MODES,
            "PROJECT_VOCABULARY", "Project mode", allow_unselected=allow_unselected,
        ),
        "delivery_profile": exact_selection(
            ctx, document.get("Delivery profile", ""), DELIVERY_PROFILES,
            "PROJECT_VOCABULARY", "Delivery profile", allow_unselected=allow_unselected,
        ),
        "effective_risk": exact_selection(
            ctx, document.get("Effective risk", ""), RISK_LEVELS,
            "PROJECT_VOCABULARY", "Effective risk", allow_unselected=allow_unselected,
        ),
        "aws_lane": exact_selection(
            ctx, document.get("AWS lane", ""), AWS_LANES,
            "PROJECT_VOCABULARY", "AWS lane", allow_unselected=allow_unselected,
        ),
    }
    for key, selected in selections.items():
        if project.get(key) != selected:
            ctx.error(
                "STATE_PRD_DRIFT",
                f"project.{key}={project.get(key)!r} does not match PRD value {selected!r}",
                STATE_FILE,
            )
    if selections["effective_risk"] in {"high", "critical"} and selections["delivery_profile"] != "high-risk":
        ctx.error("PROJECT_RISK_PROFILE", "High or critical risk requires the high-risk profile", PRD_FILE)

    fields = {
        "requirements_revision": document.get("Current requirements revision", ""),
        "design_revision": document.get("Current design revision", ""),
        "construction_authorization": document.get("Current construction authorization ID", ""),
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
            ctx.error("PRD_REVISION_ID", f"Invalid PRD {key}: {fields[key]!r}", PRD_FILE)
    if fields["gate_a"] not in GATE_A_STATES or fields["gate_b"] not in GATE_B_STATES:
        ctx.error("PRD_GATE", "Invalid PRD derived gate state", PRD_FILE)
    for key, value in fields.items():
        if lifecycle.get(key) != value:
            ctx.error(
                "STATE_PRD_DRIFT",
                f"lifecycle.{key}={lifecycle.get(key)!r} does not match PRD {value!r}",
                STATE_FILE,
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
    gate_b_agent_ready = gate_b_agent.get("Agent recommendation") == "READY_FOR_CONSTRUCTION_APPROVAL"
    coverage_required = gate_a_agent_ready or gate_a_ready_or_current
    grandfather_approved_v1_requirements = bool(
        fields["gate_a"] == "APPROVED_FOR_DESIGN"
        and gate_a_agent.get("Requirements revision reviewed")
        == fields["requirements_revision"]
        and gate_a_owner.get("Authorized requirements revision")
        == fields["requirements_revision"]
    )
    coverage_contract, coverage_issues = derive_coverage_contract(
        text,
        fields.get("requirements_revision"),
        selections.get("delivery_profile"),
        selections.get("effective_risk"),
        selections.get("aws_lane"),
        required=coverage_required,
        grandfather_current_gate_a=grandfather_approved_v1_requirements,
    )
    if coverage_required:
        for issue in coverage_issues:
            ctx.error("ADAPTIVE_COVERAGE_INVALID", issue, PRD_FILE)
    design_contract_required = gate_b_agent_ready or gate_b_ready_or_current
    grandfather_approved_v1_design = bool(
        fields["gate_b"] == "APPROVED_FOR_CONSTRUCTION"
        and gate_b_agent.get("Design revision reviewed")
        == fields["design_revision"]
        and gate_b_agent.get("Construction authorization ID reviewed")
        == fields["construction_authorization"]
        and gate_b_owner.get("Authorized design revision")
        == fields["design_revision"]
        and gate_b_owner.get("Authorized construction authorization ID")
        == fields["construction_authorization"]
    )
    design_contract, design_contract_issues = derive_design_contract(
        text,
        fields.get("design_revision"),
        required=design_contract_required,
        grandfather_approved_v1=grandfather_approved_v1_design,
        coverage_contract=coverage_contract,
    )
    if design_contract_required:
        for issue in design_contract_issues:
            ctx.error("DESIGN_CONTRACT_INVALID", issue, PRD_FILE)
    card_cost_posture = clean_cell(gate_a_card.get("Cost posture", ""))
    if gate_a_agent_ready or gate_a_ready_or_current:
        validate_gate_a_method_contract(
            ctx,
            text,
            grandfather_approved_v1=grandfather_approved_v1_requirements,
        )
        validate_readiness_card(ctx, gate_a_card, GATE_A_READINESS_FIELDS, "GATE_A")
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
            decision.decision_id
            for decision in design_contract.technology_decisions
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
            ctx.error("GATE_B_READINESS_CARD", "Gate B readiness requires Outstanding gaps NONE", PRD_FILE)
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
        missing_selections = sorted(key for key, value in selections.items() if value is None)
        if missing_selections:
            ctx.error(
                "PROJECT_SELECTION_REQUIRED",
                "Gate readiness requires explicit project selections: " + ", ".join(missing_selections),
                PRD_FILE,
            )
    if selections["mode"] == "greenfield" and project.get("brownfield_baseline") != "NOT_APPLICABLE":
        ctx.error("BROWNFIELD_STATE", "Greenfield mode requires NOT_APPLICABLE brownfield state", STATE_FILE)
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
        rows = re.findall(r"^\|\s*FR-\d+\s*\|(.+)$", functional_match.group(0), re.MULTILINE)
        requirements_present = requirements_present and any("TODO" not in row.upper() for row in rows)

    if gate_a_ready_or_current:
        if gate_a_agent.get("Requirements revision analyzed") != fields["requirements_revision"]:
            ctx.error("GATE_A_REVISION_MISMATCH", "Gate A analysis does not match current REQ", PRD_FILE)
        if gate_a_agent.get("Agent recommendation") not in {
            "READY_WITH_PROPOSED_ASSUMPTIONS",
            "READY_FOR_OWNER_APPROVAL",
        }:
            ctx.error("GATE_A_RECOMMENDATION", "Gate A was not agent-ready", PRD_FILE)
        for key in ("Open blocking finding IDs", "Open blocking decision IDs"):
            if gate_a_agent.get(key) != "NONE":
                ctx.error("GATE_A_BLOCKER", f"{key} must be NONE before owner approval", PRD_FILE)

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
        if gate_a_owner.get("Owner decision") != "APPROVED" or gate_a_owner.get(
            "Authorized requirements revision"
        ) != fields["requirements_revision"]:
            ctx.error("GATE_A_OWNER_RECORD", "Gate A owner record is not current and approved", PRD_FILE)
        if gate_a_owner.get("Authorized cost posture") != card_cost_posture:
            ctx.error(
                "GATE_A_COST_AUTHORIZATION",
                "Gate A owner record does not authorize the exact readiness-card cost posture",
                PRD_FILE,
            )
        if gate_a_owner.get("Derived Gate A state") != fields["gate_a"]:
            ctx.error("GATE_A_OWNER_RECORD", "Detailed Gate A state does not match Document status", PRD_FILE)
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
            ctx.error("GATE_A_OWNER_RECORD", "Gate A authorization source is unresolved", PRD_FILE)
        if gate_a_owner.get("Verbatim owner receipt") != "RECORDED_BELOW":
            ctx.error("GATE_A_OWNER_RECORD", "Approved Gate A must reference the marked receipt block", PRD_FILE)
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
                ctx.error("GATE_A_RECEIPT_MISMATCH", "Marked Gate A receipt does not match structured fields", PRD_FILE)
        except ValueError as exc:
            ctx.error("GATE_A_RECEIPT_MISMATCH", str(exc), PRD_FILE)

    if gate_b_ready_or_current:
        reviewed = {
            "Requirements revision reviewed": fields["requirements_revision"],
            "Design revision reviewed": fields["design_revision"],
            "Construction authorization ID reviewed": fields["construction_authorization"],
        }
        for key, value in reviewed.items():
            if gate_b_agent.get(key) != value:
                ctx.error("GATE_B_REVISION_MISMATCH", f"{key} does not match current state", PRD_FILE)
        if gate_b_agent.get("Construction envelope SHA-256 reviewed") != envelope_digest:
            ctx.error(
                "GATE_B_ENVELOPE_HASH",
                "Gate B agent review does not bind the complete current construction envelope",
                PRD_FILE,
            )
        if gate_b_agent.get("Agent recommendation") != "READY_FOR_CONSTRUCTION_APPROVAL":
            ctx.error("GATE_B_RECOMMENDATION", "Gate B was not agent-ready", PRD_FILE)
        for key in (
            "PRD completeness gaps",
            "Requirement-to-design-and-test traceability gaps",
            "Unresolved risk or preservation gaps",
        ):
            if gate_b_agent.get(key) != "NONE":
                ctx.error("GATE_B_GAP", f"{key} must be NONE before owner approval", PRD_FILE)
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
            ctx.error("GATE_B_WITHOUT_GATE_A", "Gate B cannot be current while Gate A is not current", PRD_FILE)
        if gate_b_owner.get("Authorized construction envelope SHA-256") != envelope_digest:
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
            "Authorized construction authorization ID": fields["construction_authorization"],
        }
        if gate_b_owner.get("Owner decision") != "APPROVED":
            ctx.error("GATE_B_OWNER_RECORD", "Gate B owner decision is not APPROVED", PRD_FILE)
        for key, value in owner_values.items():
            if gate_b_owner.get(key) != value:
                ctx.error("GATE_B_OWNER_RECORD", f"{key} does not match current state", PRD_FILE)
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
            ctx.error("GATE_B_OWNER_RECORD", "Gate B authorization source is unresolved", PRD_FILE)
        if gate_b_owner.get("Derived Gate B state") != fields["gate_b"]:
            ctx.error("GATE_B_OWNER_RECORD", "Detailed Gate B state does not match Document status", PRD_FILE)
        if gate_b_owner.get("Verbatim owner receipt") != "RECORDED_BELOW":
            ctx.error("GATE_B_OWNER_RECORD", "Approved Gate B must reference the marked receipt block", PRD_FILE)
        try:
            actual = marked_receipt(text, "gate-b")
            if actual != expected:
                ctx.error("GATE_B_RECEIPT_MISMATCH", "Marked Gate B receipt does not match structured fields", PRD_FILE)
        except ValueError as exc:
            ctx.error("GATE_B_RECEIPT_MISMATCH", str(exc), PRD_FILE)

    return (
        fields,
        envelope,
        selections,
        requirements_present or gate_b_agent_ready,
        design_contract,
        coverage_contract,
    )


def path_boundary_contains(allowed: str, requested: str) -> bool:
    allowed = allowed.casefold()
    requested = requested.casefold()
    allowed_base = allowed[:-3] if allowed.endswith("/**") else allowed
    requested_base = requested[:-3] if requested.endswith("/**") else requested
    if allowed.endswith("/**"):
        return requested_base == allowed_base or requested_base.startswith(allowed_base + "/")
    return allowed == requested and not requested.endswith("/**")


def path_boundaries_overlap(first: str, second: str) -> bool:
    first = first.casefold()
    second = second.casefold()
    first_base = first[:-3] if first.endswith("/**") else first
    second_base = second[:-3] if second.endswith("/**") else second
    return (
        first_base == second_base
        or first_base.startswith(second_base + "/")
        or second_base.startswith(first_base + "/")
    )


def external_targets_overlap(first: str, second: str) -> bool:
    first = first.casefold()
    second = second.casefold()
    if first == second:
        return True
    return any(
        first.startswith(second + separator) or second.startswith(first + separator)
        for separator in ("/", ":", "#")
    )


def external_target_contains(allowed: str, requested: str) -> bool:
    allowed = allowed.casefold()
    requested = requested.casefold()
    if allowed == requested:
        return True
    return any(requested.startswith(allowed + separator) for separator in ("/", ":", "#"))


def validate_tasks_against_envelope(
    ctx: Context,
    tasks: list[InspectedTask],
    snapshot: dict[str, str],
    state: dict[str, Any],
    envelope: dict[str, str],
) -> None:
    try:
        maximum_tasks = int(envelope.get("Maximum generated tasks", ""))
        maximum_workers = int(envelope.get("Maximum parallel workers", ""))
        maximum_attempts = int(envelope.get("Attempt budget", ""))
        snapshot_workers = int(snapshot.get("Maximum workers", ""))
        allowed_writes = parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
        )
        excluded_writes = parse_envelope_paths(
            envelope.get("Excluded or owner-only write set", ""),
            "Excluded or owner-only write set",
            allow_none=True,
        )
        allowed_external = parse_envelope_targets(
            envelope.get("Allowed external-state targets", "")
        )
        authorized_protected = parse_envelope_paths(
            envelope.get("Protected dirty paths", ""),
            "Protected dirty paths",
            allow_none=True,
        )
        authorized_ids = set(
            parse_authorized_ids(
                envelope.get("Authorized requirement and design IDs", "")
            )
        )
        authorized_ids.update(ID_LIKE.findall(envelope.get("Authorized outcome", "")))
        boundary_mode, explicit_task_ids = parse_task_boundary(envelope.get("Task boundary", ""))
        command_prefixes = parse_command_prefixes(envelope.get("Local command boundary", ""))
        github_repo = parse_github_constraints(
            envelope.get("GitHub repository, branch, and merge constraints", ""),
            envelope.get("GitHub boundary", ""),
        )
        parse_future_expiry(envelope.get("Authorization expiry or completion condition", ""))
    except (ValueError, TypeError) as exc:
        ctx.error("GATE_B_ENVELOPE", f"Cannot validate task boundaries: {exc}", PRD_FILE)
        return
    if len(tasks) > maximum_tasks:
        ctx.error("TASK_LIMIT_EXCEEDED", f"{len(tasks)} tasks exceed AUTH maximum {maximum_tasks}", TASKS_FILE)
    if snapshot_workers > maximum_workers:
        ctx.error("WORKER_LIMIT_EXCEEDED", "TASKS Maximum workers exceeds AUTH", TASKS_FILE)
    if maximum_workers > 1 and "isolated worktree" not in envelope.get("Parallelism rule", "").lower():
        ctx.error("GATE_B_ENVELOPE", "Parallel AUTH above one worker must require isolated worktrees", PRD_FILE)
    if snapshot.get("Baseline commit") != envelope.get("Authorized baseline commit"):
        ctx.error("TASK_BASELINE_DRIFT", "TASKS baseline commit does not match AUTH", TASKS_FILE)
    snapshot_protected = snapshot.get("Protected dirty paths", "NONE")
    try:
        task_protected = (
            []
            if snapshot_protected == "NONE"
            else parse_task_write_set(snapshot_protected, "Protected dirty paths")
        )
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
        task_protected = []
    if [item.casefold() for item in task_protected] != [item.casefold() for item in authorized_protected]:
        ctx.error("TASK_BASELINE_DRIFT", "TASKS protected dirty paths do not match AUTH", TASKS_FILE)

    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    if execution.get("mode") == "AUTONOMOUS" and envelope.get("Autonomous construction") != "ALLOWED":
        ctx.error("AUTONOMY_OUTSIDE_AUTH", "AUTONOMOUS run is not allowed by Gate B", STATE_FILE)
    if not tasks:
        return

    github_boundary = envelope.get("GitHub boundary", "NONE")
    aws_boundary = envelope.get("AWS boundary", "NONE")
    protected = snapshot.get("Protected dirty paths", "NONE")
    try:
        protected_paths = [] if protected == "NONE" else parse_task_write_set(protected, "Protected dirty paths")
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
        protected_paths = []

    for task in tasks:
        try:
            writes = parse_task_write_set(task.metadata["Write set"], task.task_id)
            external_targets = parse_task_external_state(
                task.metadata["External state"], task.task_id
            )
        except (KeyError, ValueError):
            continue
        for requested in writes:
            if not any(path_boundary_contains(allowed, requested) for allowed in allowed_writes):
                ctx.error("TASK_OUTSIDE_WRITE_BOUNDARY", f"{task.task_id} write {requested!r} is outside AUTH", TASKS_FILE)
            if any(path_boundaries_overlap(requested, excluded) for excluded in excluded_writes):
                ctx.error("TASK_EXCLUDED_WRITE", f"{task.task_id} overlaps excluded path {requested!r}", TASKS_FILE)
            if task.status in {"READY", "IN_PROGRESS"} and any(
                path_boundaries_overlap(requested, dirty) for dirty in protected_paths
            ):
                ctx.error("TASK_PROTECTED_DIRTY_OVERLAP", f"{task.task_id} overlaps protected dirty path {requested!r}", TASKS_FILE)
        for target in external_targets:
            if not any(external_target_contains(allowed, target) for allowed in allowed_external):
                ctx.error(
                    "TASK_EXTERNAL_STATE_BOUNDARY",
                    f"{task.task_id} external target {target!r} is outside AUTH",
                    TASKS_FILE,
                )
        if boundary_mode == "EXPLICIT" and task.task_id not in explicit_task_ids:
            ctx.error("TASK_OUTSIDE_TASK_BOUNDARY", f"{task.task_id} is not listed by AUTH", TASKS_FILE)

        sections, _duplicates = inspect_task_sections(task.block)
        referenced_ids = set(ID_LIKE.findall(task.metadata.get("Requirements", "")))
        referenced_ids.update(
            item
            for item in ID_LIKE.findall(task.metadata.get("Design", ""))
            if TECHNOLOGY_DECISION_ID.fullmatch(item) is None
        )
        referenced_ids.update(ID_LIKE.findall(sections.get("Outcome", "")))
        outside_ids = sorted(referenced_ids - authorized_ids)
        if outside_ids:
            ctx.error(
                "TASK_ID_OUTSIDE_AUTH",
                f"{task.task_id} references unauthorized IDs: {', '.join(outside_ids)}",
                TASKS_FILE,
            )
        if task.status in {"READY", "IN_PROGRESS", "DONE"}:
            try:
                commands = validation_commands(sections.get("Validation", ""), task.task_id)
                for command in commands:
                    if not any(command_matches_prefix(command, prefix) for prefix in command_prefixes):
                        ctx.error(
                            "TASK_COMMAND_BOUNDARY",
                            f"{task.task_id} command {command!r} is outside AUTH",
                            TASKS_FILE,
                        )
            except ValueError as exc:
                ctx.error("TASK_COMMAND_BOUNDARY", str(exc), TASKS_FILE)
        try:
            if task.attempt_budget > maximum_attempts:
                ctx.error("TASK_ATTEMPT_BOUNDARY", f"{task.task_id} attempt budget exceeds AUTH", TASKS_FILE)
        except (KeyError, ValueError):
            pass
        aws_mode = clean_cell(task.metadata.get("AWS mode", "NONE")).upper()
        allowed_aws_modes = {
            "NONE": {"NONE"},
            "DOCS_ONLY": {"NONE", "DOCS_ONLY"},
            "READ_ONLY": {"NONE", "DOCS_ONLY", "READ_ONLY"},
            "MUTATE_LISTED_RESOURCES": {"NONE", "DOCS_ONLY", "READ_ONLY", "MUTATION"},
        }
        if aws_mode not in allowed_aws_modes.get(aws_boundary, set()):
            ctx.error("TASK_AWS_BOUNDARY", f"{task.task_id} AWS mode exceeds AUTH", TASKS_FILE)
        issue = clean_cell(task.metadata.get("GitHub issue", "PENDING_SYNC"))
        if github_boundary in {"NONE", "READ_ONLY"} and issue != "PENDING_SYNC":
            ctx.error("TASK_GITHUB_BOUNDARY", f"{task.task_id} has a GitHub write result outside AUTH", TASKS_FILE)
        elif github_boundary not in {"NONE", "READ_ONLY"} and issue != "PENDING_SYNC":
            match = GITHUB_ISSUE_URL.fullmatch(issue)
            if match is None or github_repo is None or match.group("repo").casefold() != github_repo.casefold():
                ctx.error(
                    "TASK_GITHUB_BOUNDARY",
                    f"{task.task_id} issue URL does not match the authorized GitHub repository",
                    TASKS_FILE,
                )

    active = [task for task in tasks if task.status == "IN_PROGRESS"]
    if len(active) > min(maximum_workers, snapshot_workers):
        ctx.error("WORKER_LIMIT_EXCEEDED", "IN_PROGRESS tasks exceed the active worker limit", TASKS_FILE)
    for index, first in enumerate(active):
        first_writes = parse_task_write_set(first.metadata["Write set"], first.task_id)
        first_external = parse_task_external_state(first.metadata["External state"], first.task_id)
        for second in active[index + 1 :]:
            second_writes = parse_task_write_set(second.metadata["Write set"], second.task_id)
            second_external = parse_task_external_state(second.metadata["External state"], second.task_id)
            conflict = any(path_boundaries_overlap(a, b) for a in first_writes for b in second_writes)
            conflict |= any(external_targets_overlap(a, b) for a in first_external for b in second_external)
            conflict |= clean_cell(first.metadata["AWS mode"]).upper() == "MUTATION"
            conflict |= clean_cell(second.metadata["AWS mode"]).upper() == "MUTATION"
            if conflict:
                ctx.error("ACTIVE_TASK_CONFLICT", f"{first.task_id} conflicts with {second.task_id}", TASKS_FILE)

def git_read(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(root),
            *arguments,
        ],
        check=False,
        capture_output=True,
        env=environment,
        timeout=10,
    )


def parse_checkpoint_rows(tasks_text: str) -> list[CheckpointReceiptRow]:
    structural = without_fenced_code(tasks_text)
    headings = list(
        re.finditer(r"^## Checkpoints and resume[ \t]*$", structural, re.MULTILINE)
    )
    if len(headings) != 1:
        raise ValueError("TASKS requires exactly one Checkpoints and resume section")
    following = re.search(r"^##\s+", structural[headings[0].end() :], re.MULTILINE)
    end = headings[0].end() + following.start() if following else len(structural)
    raw_lines = tasks_text[headings[0].end() : end].splitlines()
    structural_lines = structural[headings[0].end() : end].splitlines()
    header_indexes = [
        index
        for index, (raw_line, structural_line) in enumerate(
            zip(raw_lines, structural_lines)
        )
        if structural_line.strip().startswith("|")
        and split_markdown_table_row(raw_line) == list(CHECKPOINT_HEADERS)
    ]
    if len(header_indexes) != 1:
        raise ValueError("TASKS requires one exact checkpoint table header")
    header = header_indexes[0]
    table_lines: list[str] = []
    for raw_line, structural_line in zip(raw_lines[header:], structural_lines[header:]):
        if not structural_line.strip().startswith("|"):
            break
        table_lines.append(raw_line)
    header = 0
    separator = (
        split_markdown_table_row(table_lines[header + 1])
        if header + 1 < len(table_lines)
        else None
    )
    if (
        separator is None
        or len(separator) != len(CHECKPOINT_HEADERS)
        or any(re.fullmatch(r":?-{3,}:?", cell) is None for cell in separator)
    ):
        raise ValueError("TASKS checkpoint table separator is invalid")
    rows: list[CheckpointReceiptRow] = []
    for line in table_lines[header + 2 :]:
        cells = split_markdown_table_row(line)
        if cells is None or len(cells) != len(CHECKPOINT_HEADERS):
            raise ValueError("TASKS checkpoint rows must have exactly eight cells")
        cleaned = [clean_cell(cell) for cell in cells]
        if cleaned[0] == "NONE":
            continue
        if CHECKPOINT_ID.fullmatch(cleaned[0]) is None:
            raise ValueError(f"Invalid checkpoint table ID: {cleaned[0]!r}")
        rows.append(CheckpointReceiptRow(*cleaned))
    identifiers = [row.checkpoint_id for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Checkpoint table IDs must be unique")
    ordinals = [int(identifier.split("-", 1)[1]) for identifier in identifiers]
    if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
        raise ValueError("Checkpoint table IDs must be strictly monotonic")
    return rows


def parse_checkpoint_git_receipt(
    tasks_text: str,
    checkpoint_id: str,
) -> tuple[str, list[str]]:
    rows = parse_checkpoint_rows(tasks_text)
    matches = [row for row in rows if row.checkpoint_id == checkpoint_id]
    if not rows or len(matches) != 1 or rows[-1].checkpoint_id != checkpoint_id:
        raise ValueError(f"{checkpoint_id}: must be the unique newest checkpoint row")
    receipt = matches[0].commit_and_dirty
    match = re.fullmatch(
        r"Commit\s*:\s*`?([0-9a-fA-F]{7,64})`?\s*;\s*Dirty\s*:\s*(.+?)\s*",
        receipt,
        re.IGNORECASE,
    )
    if match is None:
        raise ValueError(
            f"{checkpoint_id}: commit receipt must use Commit: <sha>; Dirty: <paths|NONE>"
        )
    dirty_value = match.group(2).replace("`", "").strip()
    dirty = (
        []
        if dirty_value == "NONE"
        else parse_task_write_set(dirty_value, f"{checkpoint_id} checkpoint Dirty paths")
    )
    return match.group(1), dirty


def validate_checkpoint_record(
    ctx: Context,
    tasks_text: str,
    snapshot: dict[str, str],
    tasks: list[InspectedTask],
    verify_text: str | None,
) -> None:
    checkpoint_id = snapshot.get("Last checkpoint", "")
    try:
        rows = parse_checkpoint_rows(tasks_text)
        matching = [row for row in rows if row.checkpoint_id == checkpoint_id]
        if not rows or len(matching) != 1 or rows[-1].checkpoint_id != checkpoint_id:
            raise ValueError(f"{checkpoint_id}: must be the unique newest checkpoint row")
        row = matching[0]
        if row.run_id != snapshot.get("Active run ID"):
            raise ValueError(f"{checkpoint_id}: checkpoint run does not match the snapshot")
        if not explicit_timestamp(row.recorded_at):
            raise ValueError(f"{checkpoint_id}: checkpoint time must be ISO 8601 with timezone")
        for prefix, expected in (
            ("REQ", snapshot.get("Requirements revision", "")),
            ("DES", snapshot.get("Design revision", "")),
            ("AUTH", snapshot.get("Construction authorization", "")),
        ):
            if re.findall(rf"\b{prefix}-\d{{4,}}\b", row.basis) != [expected]:
                raise ValueError(f"{checkpoint_id}: checkpoint REQ/DES/AUTH basis is not current")
        parse_checkpoint_git_receipt(tasks_text, checkpoint_id)
        if not explicit_value(row.task_outcomes):
            raise ValueError(f"{checkpoint_id}: task outcomes and attempts are unresolved")
        for task in tasks:
            token = re.compile(
                rf"(?<![A-Za-z0-9-]){re.escape(task.task_id)}(?![A-Za-z0-9-])"
            )
            segments = [
                segment.strip()
                for segment in re.split(r"[;\n]", row.task_outcomes)
                if token.search(segment) is not None
            ]
            if len(segments) != 1 or re.search(
                rf"\b{re.escape(task.status)}\b", segments[0]
            ) is None:
                raise ValueError(f"{checkpoint_id}: outcome for {task.task_id} is not current")
            attempt = re.compile(
                rf"\battempts?(?:\s+used)?\s*[=:]\s*{task.attempts_used}"
                rf"(?:\s*/\s*{task.attempt_budget})?(?!\s*/\s*\d)\b",
                re.IGNORECASE,
            )
            if attempt.search(segments[0]) is None:
                raise ValueError(f"{checkpoint_id}: attempts for {task.task_id} are not current")
        if (
            not explicit_value(row.evidence_and_external)
            or re.search(r"\bevidence\b", row.evidence_and_external, re.IGNORECASE) is None
            or re.search(r"\bexternal\b", row.evidence_and_external, re.IGNORECASE) is None
        ):
            raise ValueError(f"{checkpoint_id}: evidence and external actions are unresolved")
        evidence_cell = row.evidence_and_external
        for task in tasks:
            references = [
                match.group(0)
                for match in EVIDENCE_PATTERN.finditer(
                    clean_cell(task.metadata.get("Evidence", ""))
                )
            ]
            if any(
                re.search(
                    rf"(?<![A-Za-z0-9._-]){re.escape(reference)}(?![A-Za-z0-9._-])",
                    evidence_cell,
                    re.IGNORECASE,
                )
                is None
                for reference in references
            ):
                raise ValueError(f"{checkpoint_id}: evidence for {task.task_id} is incomplete")
        if (
            not explicit_value(row.blockers_and_next)
            or re.search(r"\bblockers?\b", row.blockers_and_next, re.IGNORECASE) is None
            or re.search(r"\bnext\b", row.blockers_and_next, re.IGNORECASE) is None
        ):
            raise ValueError(f"{checkpoint_id}: blockers and next action are unresolved")
        structural_verify = without_fenced_code(verify_text) if verify_text is not None else ""
        if re.search(
            rf"(?<![A-Za-z0-9-]){re.escape(checkpoint_id)}(?![A-Za-z0-9-])",
            structural_verify,
        ) is None:
            raise ValueError(f"{checkpoint_id}: checkpoint is not referenced in VERIFY.md")
    except (KeyError, ValueError) as exc:
        ctx.error("CONSTRUCTION_CHECKPOINT_UNVERIFIED", str(exc), TASKS_FILE)


def validate_authorized_baseline_repository(ctx: Context, baseline: str) -> None:
    """Prove Gate B's full authorized baseline resolves in a regular worktree."""

    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", baseline) is None:
        return
    try:
        inside = git_read(ctx.root, "rev-parse", "--is-inside-work-tree")
        bare = git_read(ctx.root, "rev-parse", "--is-bare-repository")
        resolved = git_read(ctx.root, "rev-parse", "--verify", f"{baseline}^{{commit}}")
    except (OSError, subprocess.SubprocessError) as exc:
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
    if resolved.returncode != 0 or resolved.stdout.decode("ascii", errors="replace").strip() != baseline:
        ctx.error(
            "GATE_B_GIT_UNVERIFIED",
            "Authorized baseline commit does not resolve exactly in this repository",
            PRD_FILE,
        )


def validate_construction_repository(
    ctx: Context,
    snapshot: dict[str, str],
    *,
    tasks_text: str | None,
    reconcile_worktree: bool,
) -> None:
    """Prove construction Git history and, at checkpoints, current dirty state."""

    baseline = snapshot.get("Baseline commit", "")
    known_green = snapshot.get("Last known-green commit", "")
    for label, value in (("Baseline commit", baseline), ("Last known-green commit", known_green)):
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
            ctx.error(
                "CONSTRUCTION_GIT_UNVERIFIED",
                f"{label} must be a full lowercase Git commit ID",
                TASKS_FILE,
            )
            return

    checkpoint_commit: str | None = None
    checkpoint_dirty: list[str] | None = None
    if reconcile_worktree and tasks_text is not None:
        checkpoint_id = snapshot.get("Last checkpoint", "")
        if CHECKPOINT_ID.fullmatch(checkpoint_id) is None:
            ctx.error(
                "CONSTRUCTION_CHECKPOINT_UNVERIFIED",
                "Checkpointed construction requires a current checkpoint receipt",
                TASKS_FILE,
            )
            return
        try:
            checkpoint_commit, checkpoint_dirty = parse_checkpoint_git_receipt(
                tasks_text, checkpoint_id
            )
        except ValueError as exc:
            ctx.error("CONSTRUCTION_CHECKPOINT_UNVERIFIED", str(exc), TASKS_FILE)
            return

    try:
        inside = git_read(ctx.root, "rev-parse", "--is-inside-work-tree")
        bare = git_read(ctx.root, "rev-parse", "--is-bare-repository")
        head_result = git_read(ctx.root, "rev-parse", "--verify", "HEAD^{commit}")
        baseline_result = git_read(ctx.root, "rev-parse", "--verify", f"{baseline}^{{commit}}")
        green_result = git_read(ctx.root, "rev-parse", "--verify", f"{known_green}^{{commit}}")
        checkpoint_result = (
            git_read(ctx.root, "rev-parse", "--verify", f"{checkpoint_commit}^{{commit}}")
            if checkpoint_commit is not None
            else None
        )
    except (OSError, subprocess.SubprocessError) as exc:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            f"Unable to inspect construction Git state read-only: {exc}",
            TASKS_FILE,
        )
        return
    if (
        inside.returncode != 0
        or inside.stdout.strip() != b"true"
        or bare.returncode != 0
        or bare.stdout.strip() != b"false"
    ):
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Construction requires a regular local Git worktree",
            TASKS_FILE,
        )
        return
    commit_results = [head_result, baseline_result, green_result]
    if checkpoint_result is not None:
        commit_results.append(checkpoint_result)
    if any(result.returncode != 0 for result in commit_results):
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Authorized baseline, last-known-green, or checkpoint commit cannot be resolved",
            TASKS_FILE,
        )
        return
    resolved_baseline = baseline_result.stdout.decode("ascii", errors="replace").strip()
    resolved_green = green_result.stdout.decode("ascii", errors="replace").strip()
    if resolved_baseline != baseline or resolved_green != known_green:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Construction commit identities must be exact full hashes",
            TASKS_FILE,
        )
        return
    if checkpoint_result is not None and (
        checkpoint_result.stdout.decode("ascii", errors="replace").strip() != resolved_green
    ):
        ctx.error(
            "CONSTRUCTION_CHECKPOINT_UNVERIFIED",
            "Checkpoint receipt commit does not match Last known-green commit",
            TASKS_FILE,
        )
        return

    try:
        baseline_ancestor = git_read(
            ctx.root, "merge-base", "--is-ancestor", baseline, known_green
        )
        green_ancestor = git_read(
            ctx.root, "merge-base", "--is-ancestor", known_green, "HEAD"
        )
        committed = git_read(
            ctx.root,
            "diff",
            "--name-only",
            "-z",
            "--relative",
            f"{known_green}..HEAD",
            "--",
            ".",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            f"Unable to compare construction Git history: {exc}",
            TASKS_FILE,
        )
        return
    if baseline_ancestor.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Authorized baseline is not an ancestor of Last known-green commit",
            TASKS_FILE,
        )
    if green_ancestor.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Last known-green commit is not an ancestor of current HEAD",
            TASKS_FILE,
        )
    if committed.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Unable to enumerate commits after Last known-green",
            TASKS_FILE,
        )
        return
    committed_paths = {
        item.decode("utf-8", errors="surrogateescape")
        for item in committed.stdout.split(b"\0")
        if item
    }
    unauthorized_committed = sorted(committed_paths - COORDINATOR_LEDGER_PATHS)
    if unauthorized_committed:
        ctx.error(
            "CONSTRUCTION_GIT_DRIFT",
            "Commits after Last known-green contain non-ledger paths: "
            + ", ".join(unauthorized_committed),
            TASKS_FILE,
        )

    if not reconcile_worktree:
        return
    try:
        tracked = git_read(ctx.root, "diff", "--name-only", "-z", "--relative", "HEAD", "--", ".")
        untracked = git_read(ctx.root, "ls-files", "--others", "--exclude-standard", "-z", "--", ".")
    except (OSError, subprocess.SubprocessError) as exc:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            f"Unable to enumerate the checkpoint worktree: {exc}",
            TASKS_FILE,
        )
        return
    if tracked.returncode != 0 or untracked.returncode != 0:
        ctx.error(
            "CONSTRUCTION_GIT_UNVERIFIED",
            "Unable to enumerate the checkpoint worktree",
            TASKS_FILE,
        )
        return
    observed = {
        item.decode("utf-8", errors="surrogateescape")
        for payload in (tracked.stdout, untracked.stdout)
        for item in payload.split(b"\0")
        if item
    }
    observed_nonledger = observed - COORDINATOR_LEDGER_PATHS
    protected_value = snapshot.get("Protected dirty paths", "NONE")
    try:
        protected = (
            []
            if protected_value == "NONE"
            else parse_task_write_set(protected_value, "Protected dirty paths")
        )
    except ValueError as exc:
        ctx.error("CONSTRUCTION_GIT_UNVERIFIED", str(exc), TASKS_FILE)
        return
    if checkpoint_dirty is not None and {
        item.casefold() for item in checkpoint_dirty
    } != {item.casefold() for item in protected}:
        ctx.error(
            "CONSTRUCTION_CHECKPOINT_UNVERIFIED",
            "Checkpoint Dirty paths do not match Protected dirty paths",
            TASKS_FILE,
        )
    uncovered = sorted(
        path
        for path in observed_nonledger
        if not any(path_boundary_contains(boundary, path) for boundary in protected)
    )
    unused = sorted(
        boundary
        for boundary in protected
        if not any(path_boundary_contains(boundary, path) for path in observed_nonledger)
    )
    if uncovered or unused:
        details: list[str] = []
        if uncovered:
            details.append("unrecorded dirty paths=" + ", ".join(uncovered))
        if unused:
            details.append("recorded paths not dirty=" + ", ".join(unused))
        ctx.error(
            "CONSTRUCTION_WORKTREE_DRIFT",
            "Checkpoint protected paths do not exactly match the worktree: "
            + "; ".join(details),
            TASKS_FILE,
        )


def validate_resume_repository(
    ctx: Context,
    snapshot: dict[str, str],
    tasks_text: str | None = None,
) -> None:
    """Compatibility entry point for conservative checkpoint reconciliation."""

    validate_construction_repository(
        ctx,
        snapshot,
        tasks_text=tasks_text,
        reconcile_worktree=True,
    )


def validate_tasks(
    ctx: Context,
    state: dict[str, Any],
    prd_fields: dict[str, str],
    envelope: dict[str, str],
    design_contract: DesignContract,
) -> TaskSummary:
    summary = TaskSummary()
    text = ctx.texts.get(TASKS_FILE) or safe_read_text(ctx, TASKS_FILE)
    if text is None:
        return summary
    try:
        snapshot = table_after_heading(text, "## Active execution snapshot")
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
        return summary

    if set(snapshot) != SNAPSHOT_FIELDS:
        missing = sorted(SNAPSHOT_FIELDS - set(snapshot))
        extra = sorted(set(snapshot) - SNAPSHOT_FIELDS)
        details: list[str] = []
        if missing:
            details.append("missing=" + ", ".join(missing))
        if extra:
            details.append("unexpected=" + ", ".join(extra))
        ctx.error("TASK_SNAPSHOT", "Active execution snapshot fields must be exact: " + "; ".join(details), TASKS_FILE)

    run_state = snapshot.get("Run state", "")
    if run_state not in SNAPSHOT_RUN_STATES:
        ctx.error("TASK_SNAPSHOT", f"Invalid Run state {run_state!r}", TASKS_FILE)
    try:
        snapshot_workers = int(snapshot.get("Maximum workers", ""))
        if snapshot_workers < 1:
            raise ValueError
    except ValueError:
        ctx.error("TASK_SNAPSHOT", "Maximum workers must be a positive integer", TASKS_FILE)
    active_run_id = snapshot.get("Active run ID", "")
    coordinator = snapshot.get("Coordinator", "")
    if run_state == "NOT_STARTED":
        if active_run_id != "NONE" or coordinator != "UNASSIGNED":
            ctx.error("TASK_SNAPSHOT", "NOT_STARTED requires no run ID and an unassigned coordinator", TASKS_FILE)
    else:
        if RUN_ID.fullmatch(active_run_id) is None or coordinator in {"", "NONE", "UNASSIGNED", "TODO"}:
            ctx.error("TASK_SNAPSHOT", "An active or checkpointed run requires a RUN ID and coordinator", TASKS_FILE)
    current_wave = snapshot.get("Current wave", "")
    if current_wave != "NONE" and re.fullmatch(r"[1-9]\d*", current_wave) is None:
        ctx.error("TASK_SNAPSHOT", "Current wave must be NONE or a positive integer", TASKS_FILE)
    checkpoint = snapshot.get("Last checkpoint", "")
    if run_state in {"PAUSED", "BLOCKED", "COMPLETE"}:
        if CHECKPOINT_ID.fullmatch(checkpoint) is None:
            ctx.error("TASK_SNAPSHOT", f"{run_state} requires a checkpoint ID", TASKS_FILE)
    elif checkpoint != "NONE":
        ctx.error("TASK_SNAPSHOT", f"{run_state or 'unknown run state'} must not claim a checkpoint", TASKS_FILE)
    try:
        if snapshot.get("Protected dirty paths") != "NONE":
            parse_task_write_set(snapshot.get("Protected dirty paths", ""), "Protected dirty paths")
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
    if not explicit_value(snapshot.get("Next safe action", ""), allow_none=False):
        ctx.error("TASK_SNAPSHOT", "Next safe action must be explicit", TASKS_FILE)
    if snapshot.get("Gate B state") == "APPROVED_FOR_CONSTRUCTION":
        for key in ("Baseline commit", "Last known-green commit"):
            if re.fullmatch(
                r"(?:[0-9a-f]{40}|[0-9a-f]{64})", snapshot.get(key, "")
            ) is None:
                ctx.error(
                    "TASK_SNAPSHOT",
                    f"Current Gate B requires a full lowercase {key}",
                    TASKS_FILE,
                )

    raw_plan = snapshot.get("Task-plan revision", "")
    summary.plan_state = snapshot.get("Task-plan state", "")
    summary.plan_revision = None if raw_plan == "UNINITIALIZED" else raw_plan
    if summary.plan_revision is not None and PLAN_ID.fullmatch(summary.plan_revision) is None:
        ctx.error("TASK_PLAN_STATE", "Task-plan revision must be UNINITIALIZED or PLAN-nnnn", TASKS_FILE)
    if summary.plan_state not in {"UNINITIALIZED", "CURRENT", "STALE"}:
        ctx.error("TASK_PLAN_STATE", "Task-plan state must be UNINITIALIZED, CURRENT, or STALE", TASKS_FILE)
    if summary.plan_revision is None and summary.plan_state != "UNINITIALIZED":
        ctx.error("TASK_PLAN_STATE", "UNINITIALIZED revision requires UNINITIALIZED plan state", TASKS_FILE)
    if summary.plan_revision is not None and summary.plan_state == "UNINITIALIZED":
        ctx.error("TASK_PLAN_STATE", "Initialized revision cannot have UNINITIALIZED plan state", TASKS_FILE)
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    lifecycle = state.get("lifecycle") if isinstance(state.get("lifecycle"), dict) else {}
    if summary.plan_revision != execution.get("plan_revision"):
        ctx.error("STATE_TASK_DRIFT", "Task-plan revision does not match bootstrap state", TASKS_FILE)
    if summary.plan_state != execution.get("plan_state"):
        ctx.error("STATE_TASK_DRIFT", "Task-plan state does not match bootstrap state", TASKS_FILE)
    snapshot_pairs = {
        "Requirements revision": "requirements_revision",
        "Design revision": "design_revision",
        "Construction authorization": "construction_authorization",
        "Gate B state": "gate_b",
    }
    for snapshot_key, lifecycle_key in snapshot_pairs.items():
        if snapshot.get(snapshot_key) != lifecycle.get(lifecycle_key):
            ctx.error("STATE_TASK_DRIFT", f"{snapshot_key} does not match lifecycle state", TASKS_FILE)

    run_map = {
        "IDLE": "NOT_STARTED",
        "RUNNING": "RUNNING",
        "CHECKPOINTED": "PAUSED",
        "BLOCKED": "BLOCKED",
        "COMPLETE": "COMPLETE",
    }
    execution_state = execution.get("state") if isinstance(execution.get("state"), str) else ""
    expected_run = run_map.get(execution_state)
    if expected_run is not None and snapshot.get("Run state") != expected_run:
        ctx.error("STATE_TASK_DRIFT", "Run state does not match bootstrap state", TASKS_FILE)
    expected_run_id = execution.get("run_id") or "NONE"
    if snapshot.get("Active run ID") != expected_run_id:
        ctx.error("STATE_TASK_DRIFT", "Active run ID does not match bootstrap state", TASKS_FILE)
    expected_coordinator = execution.get("coordinator") or "UNASSIGNED"
    if snapshot.get("Coordinator") != expected_coordinator:
        ctx.error("STATE_TASK_DRIFT", "Coordinator does not match bootstrap state", TASKS_FILE)

    verify_text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    try:
        approved_tech_ids = {
            decision.decision_id
            for decision in design_contract.technology_decisions
        }
        property_execution_by_id = {
            execution.property_id: execution
            for execution in design_contract.property_execution
        }
        technology_decisions_by_id = {
            decision.decision_id: decision
            for decision in design_contract.technology_decisions
        }
        tasks, _by_id, ready = validate_task_records(
            text,
            snapshot,
            verify_text,
            approved_tech_ids,
            property_execution_by_id,
            technology_decisions_by_id,
        )
    except ValueError as exc:
        ctx.error("TASK_GRAPH_INVALID", str(exc), TASKS_FILE)
        return summary

    missing_property_ids = missing_current_property_task_coverage(
        tasks,
        summary.plan_state,
        property_execution_by_id,
    )
    if missing_property_ids:
        ctx.error(
            "TASK_PROPERTY_COVERAGE",
            "CURRENT task plan does not cover approved property execution IDs: "
            + ", ".join(missing_property_ids),
            TASKS_FILE,
        )

    if summary.plan_revision is None and tasks:
        ctx.error("TASK_PLAN_STATE", "UNINITIALIZED task plan contains task blocks", TASKS_FILE)
    if summary.plan_revision is not None and not tasks:
        ctx.error("TASK_PLAN_STATE", "Initialized task plan contains no task blocks", TASKS_FILE)
    if summary.plan_state == "CURRENT" and prd_fields.get("gate_b") != "APPROVED_FOR_CONSTRUCTION":
        ctx.error("TASK_PLAN_STATE", "CURRENT task plan requires current Gate B", TASKS_FILE)
    if summary.plan_state == "STALE" and any(task.status in {"READY", "IN_PROGRESS"} for task in tasks):
        ctx.error("TASK_PLAN_STATE", "STALE task plan cannot contain runnable or active tasks", TASKS_FILE)

    summary.statuses = {task.task_id: task.status for task in tasks}
    summary.active = sorted(task.task_id for task in tasks if task.status == "IN_PROGRESS")
    summary.ready = sorted(ready)
    summary.attempts_used = {task.task_id: task.attempts_used for task in tasks}
    summary.attempt_budgets = {task.task_id: task.attempt_budget for task in tasks}
    for task in tasks:
        try:
            summary.write_sets[task.task_id] = parse_task_write_set(
                task.metadata.get("Write set", ""), task.task_id
            )
        except ValueError:
            summary.write_sets[task.task_id] = []

    state_active_value = execution.get("active_tasks")
    state_active = (
        sorted(state_active_value)
        if isinstance(state_active_value, list) and all(isinstance(item, str) for item in state_active_value)
        else []
    )
    if summary.active != state_active:
        ctx.error("STATE_TASK_DRIFT", "active_tasks does not match IN_PROGRESS task records", STATE_FILE)
    task_attempts = {task.task_id: task.attempts_used for task in tasks}
    if execution.get("attempts") != task_attempts:
        ctx.error("STATE_TASK_DRIFT", "attempt counters do not match task records", STATE_FILE)
    state_checkpoint = execution.get("last_checkpoint")
    expected_checkpoint = (
        state_checkpoint.get("id")
        if isinstance(state_checkpoint, dict)
        else "NONE"
    )
    if snapshot.get("Last checkpoint") != expected_checkpoint:
        ctx.error("STATE_TASK_DRIFT", "Last checkpoint does not match bootstrap state", TASKS_FILE)

    basis = execution.get("basis")
    if basis is not None:
        expected_basis = {
            "requirements_revision": prd_fields.get("requirements_revision"),
            "design_revision": prd_fields.get("design_revision"),
            "construction_authorization": prd_fields.get("construction_authorization"),
        }
        if basis != expected_basis:
            ctx.error("RUN_BASIS_STALE", "Execution basis does not match current PRD revisions", STATE_FILE)
    if prd_fields.get("gate_b") == "APPROVED_FOR_CONSTRUCTION" or tasks:
        validate_tasks_against_envelope(ctx, tasks, snapshot, state, envelope)
    construction_states = {"RUNNING", "CHECKPOINTED", "BLOCKED", "COMPLETE"}
    if execution_state in {"CHECKPOINTED", "BLOCKED", "COMPLETE"}:
        validate_checkpoint_record(ctx, text, snapshot, tasks, verify_text)
    if (
        prd_fields.get("gate_b") == "APPROVED_FOR_CONSTRUCTION"
        or execution_state in construction_states
    ):
        validate_construction_repository(
            ctx,
            snapshot,
            tasks_text=text,
            reconcile_worktree=execution_state in {"CHECKPOINTED", "BLOCKED", "COMPLETE"},
        )
    return summary


def validate_release_decision(ctx: Context) -> str:
    relative = VERIFY_FILE
    text = ctx.texts.get(relative) or safe_read_text(ctx, relative)
    if text is None:
        return "NOT_READY"
    heading = "## Current release decision"
    matches = list(re.finditer(rf"^{re.escape(heading)}[ \t]*$", text, re.MULTILINE))
    if len(matches) != 1:
        ctx.error("RELEASE_DECISION", f"Expected exactly one {heading!r}", relative)
        return "NOT_READY"
    section = text[matches[0].end() :]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    decisions = re.findall(r"^- Release state:\s*`([^`]+)`\s*$", section, re.MULTILINE)
    if len(decisions) != 1 or decisions[0] not in {
        "NOT_READY",
        "READY_TO_DEPLOY",
        "RELEASE_VERIFIED",
    }:
        ctx.error(
            "RELEASE_DECISION",
            "Release decision must be exactly NOT_READY, READY_TO_DEPLOY, or RELEASE_VERIFIED",
            relative,
        )
        return "NOT_READY"
    return decisions[0]


def derive_route(
    gate_a: str,
    gate_b: str,
    requirements_present: bool,
    gate_b_agent_ready: bool,
    tasks: TaskSummary,
    autonomous_allowed: bool,
    execution_mode: str,
    release_decision: str = "NOT_READY",
) -> tuple[str, str]:
    if gate_a == "STALE":
        return (
            ("REQUIREMENTS_STALE", "REQ-10")
            if requirements_present
            else ("INTAKE_REQUIRED", "INTAKE-10")
        )
    if gate_a == "BLOCKED":
        return ("REQUIREMENTS_ANALYSIS", "REQ-10") if requirements_present else ("INTAKE_REQUIRED", "INTAKE-10")
    if gate_a == "PENDING_OWNER_APPROVAL":
        return "WAITING_GATE_A", "INTAKE-20"
    if gate_a != "APPROVED_FOR_DESIGN":
        return "BLOCKED", "STOP"
    if gate_b == "STALE":
        return "DESIGN_STALE", "DESIGN-10"
    if gate_b == "BLOCKED":
        return ("WAITING_GATE_B", "DESIGN-20") if gate_b_agent_ready else ("DESIGN_REQUIRED", "DESIGN-10")
    if gate_b == "PENDING_OWNER_APPROVAL":
        return "WAITING_GATE_B", "DESIGN-20"
    if gate_b != "APPROVED_FOR_CONSTRUCTION":
        return "BLOCKED", "STOP"
    if tasks.plan_state in {"UNINITIALIZED", "STALE"}:
        return "TASK_PLAN_REQUIRED", "TASK-10"
    if tasks.active:
        if execution_mode == "AUTONOMOUS" and autonomous_allowed:
            return "CONSTRUCTION_AUTONOMOUS", "BUILD-20"
        if len(tasks.active) == 1:
            return "CONSTRUCTION_SINGLE", "BUILD-10"
        return "BLOCKED", "STOP"
    if len(tasks.ready) == 1:
        return "CONSTRUCTION_SINGLE", "BUILD-10"
    if len(tasks.ready) > 1:
        if autonomous_allowed:
            return "CONSTRUCTION_AUTONOMOUS", "BUILD-20"
        return "BLOCKED", "STOP"
    if tasks.terminal:
        if release_decision == "READY_TO_DEPLOY":
            return "AWS_PREFLIGHT_REQUIRED", "AWS-10"
        if release_decision == "RELEASE_VERIFIED":
            return "RELEASE_VERIFIED", "STOP"
        return "RELEASE_REVIEW", "RELEASE-10"
    return "BLOCKED", "STOP"


def inspect_project(root: Path, *, template_source: bool = False) -> dict[str, Any]:
    root = root.resolve()
    ctx = Context(root=root, template_source=template_source)
    if not root.is_dir():
        ctx.error("PROJECT_ROOT", "Project root is not a directory", str(root))
        return build_report(ctx, "BLOCKED", "STOP", {}, TaskSummary())

    manifest = load_json_document(ctx, MANIFEST_FILE, "MANIFEST_PARSE")
    state = load_json_document(ctx, STATE_FILE, "STATE_PARSE")
    if manifest is None or state is None:
        return build_report(
            ctx,
            "BLOCKED",
            "STOP",
            {},
            TaskSummary(),
            manifest=manifest,
            state=state,
        )

    validate_manifest(ctx, manifest)
    state_sections_valid = validate_state_schema(ctx, state)
    validate_prompt_pack(ctx, manifest, state)
    if not state_sections_valid:
        validate_placeholders(ctx)
        return build_report(
            ctx,
            "BLOCKED",
            "STOP",
            {},
            TaskSummary(),
            manifest=manifest,
            state=state,
        )
    (
        prd_fields,
        envelope,
        _selections,
        requirements_present,
        design_contract,
        coverage_contract,
    ) = validate_prd(ctx, state)
    allow_legacy_design_discovery = bool(
        prd_fields.get("gate_b") == "APPROVED_FOR_CONSTRUCTION"
        and design_contract.architecture.schema_version < 4
    )
    aws_core_rows: dict[tuple[str, str, str], AwsCoreEvidenceRow] = {}
    verify_text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    if verify_text is not None:
        try:
            aws_core_rows = parse_aws_core_evidence(
                verify_text,
                allow_legacy=allow_legacy_design_discovery,
            )
        except ValueError as exc:
            ctx.error("AWS_CORE_EVIDENCE_STRUCTURE", str(exc), VERIFY_FILE)
    tasks = validate_tasks(ctx, state, prd_fields, envelope, design_contract)
    release_decision = validate_release_decision(ctx)
    validate_placeholders(ctx)

    gate_a = prd_fields.get("gate_a", "BLOCKED")
    gate_b = prd_fields.get("gate_b", "BLOCKED")
    prd_text = ctx.texts.get(PRD_FILE, "")
    try:
        gate_b_agent = table_after_heading(prd_text, "## 27. Gate B agent review record")
        gate_b_agent_ready = gate_b_agent.get("Agent recommendation") == "READY_FOR_CONSTRUCTION_APPROVAL"
    except ValueError:
        gate_b_agent_ready = False
    approved_tech_ids = {
        decision.decision_id for decision in design_contract.technology_decisions
    }
    design_aws_core_issues = aws_core_phase_evidence_issues(
        aws_core_rows,
        "DESIGN-10",
        expected_binding=prd_fields.get("design_revision"),
        expected_design_revision=prd_fields.get("design_revision"),
        approved_tech_ids=approved_tech_ids,
        allow_legacy_discovery=allow_legacy_design_discovery,
    )
    material_discovery_issues: list[str] = []
    if not allow_legacy_design_discovery:
        design_discovery_ids = {
            discovery_id
            for row_phase, discovery_id, _capability in aws_core_rows
            if row_phase == "DESIGN-10"
        }
        for evidence in design_contract.architecture.aws_evidence:
            if evidence.discovery_id not in design_discovery_ids:
                issue = (
                    f"{evidence.evidence_id} must cite a current DESIGN-10 "
                    f"AWS-DISC chain"
                )
                material_discovery_issues.append(issue)
                design_aws_core_issues.append(issue)
    design_aws_core_ready = not design_aws_core_issues
    if gate_b_agent_ready or gate_b in {
        "PENDING_OWNER_APPROVAL",
        "APPROVED_FOR_CONSTRUCTION",
    }:
        require_aws_core_phase_evidence(
            ctx,
            aws_core_rows,
            "DESIGN-10",
            expected_binding=prd_fields.get("design_revision"),
            expected_design_revision=prd_fields.get("design_revision"),
            approved_tech_ids=approved_tech_ids,
            allow_legacy_discovery=allow_legacy_design_discovery,
        )
        for issue in material_discovery_issues:
            ctx.error("AWS_CORE_EVIDENCE_REQUIRED", issue, PRD_FILE)
    lifecycle_state, next_prompt = derive_route(
        gate_a,
        gate_b,
        requirements_present,
        gate_b_agent_ready,
        tasks,
        envelope.get("Autonomous construction") == "ALLOWED",
        state.get("execution", {}).get("mode", "NONE"),
        release_decision,
    )
    aws_execution_planning_ready = False
    aws_10_issues = ["AWS-10 active artifact binding is unresolved"]
    if verify_text is not None:
        try:
            active_scope = table_after_heading(verify_text, "## Active evidence scope")
            artifact_binding = clean_cell(
                active_scope.get("Commit, tag, or image digest", "")
            )
        except ValueError:
            artifact_binding = ""
        if explicit_value(artifact_binding, allow_none=False):
            aws_10_issues = aws_core_phase_evidence_issues(
                aws_core_rows,
                "AWS-10",
                expected_binding=artifact_binding,
                expected_design_revision=prd_fields.get("design_revision"),
                approved_tech_ids={
                    decision.decision_id
                    for decision in design_contract.technology_decisions
                },
            )
            aws_execution_planning_ready = not aws_10_issues
    if next_prompt == "AWS-10":
        if not aws_execution_planning_ready:
            ctx.warning(
                "AWS_CORE_AWS10_EVIDENCE_REQUIRED",
                "AWS-10 must record a fresh linked search_documentation then "
                "retrieve_skill discovery chain bound to the current artifact before "
                "AWS execution planning: " + "; ".join(aws_10_issues),
                VERIFY_FILE,
            )
    if ctx.has_errors:
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
    return build_report(
        ctx,
        lifecycle_state,
        next_prompt,
        prd_fields,
        tasks,
        manifest=manifest,
        state=state,
        release_decision=release_decision,
        envelope=envelope,
        aws_execution_planning_ready=aws_execution_planning_ready,
        design_aws_core_ready=design_aws_core_ready,
        design_contract=design_contract,
        coverage_contract=coverage_contract,
    )


def inspect_git_baseline(root: Path) -> str:
    """Return the current commit or PENDING without changing Git state."""

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "PENDING"
    if result.returncode != 0:
        return "PENDING"
    commit = result.stdout.strip()
    return commit if re.fullmatch(r"[0-9a-fA-F]{40,64}", commit) else "PENDING"


DEFINE_AGENT_DIAGNOSTICS = frozenset(
    {
        "ADAPTIVE_COVERAGE_INVALID",
        "GATE_A_LIFECYCLE_TRANSITION",
        "GATE_A_READINESS_CARD",
        "GATE_A_RECOMMENDATION",
    }
)
DESIGN_AGENT_DIAGNOSTICS = frozenset(
    {
        "AWS_LANE_BOUNDARY",
        "DESIGN_CONTRACT_INVALID",
        "GATE_B_DESIGN_CONTRACT_HASH",
        "GATE_B_ENVELOPE",
        "GATE_B_ENVELOPE_HASH",
        "GATE_B_GAP",
        "GATE_B_LIFECYCLE_TRANSITION",
        "GATE_B_PROJECT_DRIFT",
        "GATE_B_READINESS_CARD",
        "GATE_B_RECOMMENDATION",
        "GATE_B_REVISION_MISMATCH",
    }
)
DELIVER_AGENT_DIAGNOSTICS = frozenset(
    {
        "ACTIVE_TASK_CONFLICT",
        "AUTONOMY_OUTSIDE_AUTH",
        "STATE_TASK_DRIFT",
        "TASK_ATTEMPT_BOUNDARY",
        "TASK_AWS_BOUNDARY",
        "TASK_BASELINE_DRIFT",
        "TASK_COMMAND_BOUNDARY",
        "TASK_EXCLUDED_WRITE",
        "TASK_EXTERNAL_STATE_BOUNDARY",
        "TASK_GITHUB_BOUNDARY",
        "TASK_GRAPH_INVALID",
        "TASK_ID_OUTSIDE_AUTH",
        "TASK_LIMIT_EXCEEDED",
        "TASK_OUTSIDE_TASK_BOUNDARY",
        "TASK_OUTSIDE_WRITE_BOUNDARY",
        "TASK_PLAN_STATE",
        "TASK_PROPERTY_COVERAGE",
        "TASK_SNAPSHOT",
        "WORKER_LIMIT_EXCEEDED",
    }
)
OWNER_DECISION_DIAGNOSTICS = frozenset(
    {
        "BROWNFIELD_PRD_BASELINE",
        "BROWNFIELD_PRD_PRESERVATION",
        "BROWNFIELD_STATE",
        "GATE_A_ASSUMPTIONS",
        "GATE_A_BLOCKER",
        "GATE_A_COST_POSTURE",
        "PLACEHOLDER_UNRESOLVED",
        "PROJECT_COST_POSTURE",
        "PROJECT_IDENTITY",
        "PROJECT_RISK_PROFILE",
        "PROJECT_SELECTION_REQUIRED",
        "REQUIREMENT_METHOD_MIGRATION_REQUIRED",
    }
)
OWNER_SETUP_DIAGNOSTICS = frozenset(
    {
        "AWS_CORE_EVIDENCE_REQUIRED",
        "AWS_CORE_EVIDENCE_STRUCTURE",
    }
)
OWNER_AUTHORIZATION_DIAGNOSTICS = frozenset(
    {
        "GATE_A_COST_AUTHORIZATION",
        "GATE_A_HUMAN_APPROVER",
        "GATE_A_OWNER_RECORD",
        "GATE_A_RECEIPT_MISMATCH",
        "GATE_B_HUMAN_APPROVER",
        "GATE_B_OWNER_RECORD",
        "GATE_B_RECEIPT_MISMATCH",
        "GATE_B_WITHOUT_GATE_A",
    }
)
UNCONFIGURED_SETUP_DIAGNOSTICS = frozenset(
    {
        "PLACEHOLDER_UNRESOLVED",
        "PROJECT_COST_POSTURE",
        "STATE_SETUP",
    }
)


def _owner_stage_from_gates(gate_a: str, gate_b: str) -> str:
    if gate_a != "APPROVED_FOR_DESIGN":
        return "DEFINE"
    if gate_b != "APPROVED_FOR_CONSTRUCTION":
        return "DESIGN"
    return "DELIVER"


def _agent_correction_is_safe(
    diagnostic: Diagnostic,
    owner_stage: str,
    gate_b: str,
    envelope: Mapping[str, str],
    tasks: TaskSummary,
) -> bool:
    """Return whether one generated defect is repairable inside current boundaries."""

    relative = validate_relative_path(diagnostic.path)
    if relative is None:
        return False
    if owner_stage == "DEFINE":
        return (
            diagnostic.code in DEFINE_AGENT_DIAGNOSTICS
            and relative == PRD_FILE
        )
    if owner_stage == "DESIGN":
        return (
            diagnostic.code in DESIGN_AGENT_DIAGNOSTICS
            and relative == PRD_FILE
            and gate_b != "APPROVED_FOR_CONSTRUCTION"
        )
    if diagnostic.code not in DELIVER_AGENT_DIAGNOSTICS:
        return False
    if gate_b != "APPROVED_FOR_CONSTRUCTION":
        return False
    try:
        allowed = parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
        )
        excluded = parse_envelope_paths(
            envelope.get("Excluded or owner-only write set", ""),
            "Excluded or owner-only write set",
            allow_none=True,
        )
        protected = parse_envelope_paths(
            envelope.get("Protected dirty paths", ""),
            "Protected dirty paths",
            allow_none=True,
        )
    except ValueError:
        return False
    if any(path_boundaries_overlap(relative, item) for item in excluded + protected):
        return False
    if relative in COORDINATOR_LEDGER_PATHS:
        return True
    if len(tasks.active) != 1:
        return False
    active_task = tasks.active[0]
    if tasks.attempts_used.get(active_task, 0) >= tasks.attempt_budgets.get(
        active_task, 0
    ):
        return False
    return any(path_boundary_contains(item, relative) for item in allowed) and any(
        path_boundary_contains(item, relative)
        for item in tasks.write_sets.get(active_task, [])
    )


def _owner_authorization_action(items: list[dict[str, Any]]) -> str:
    codes = {str(item.get("diagnostic_code", "")) for item in items}
    if any(code.startswith("GATE_A_") for code in codes):
        return "APPROVE_GATE_A"
    if any(code.startswith("GATE_B_") for code in codes):
        return "APPROVE_GATE_B"
    return "AUTHORIZE_AWS_OPERATION"


def derive_remediation(
    ctx: Context,
    *,
    classification: str,
    gate_a: str,
    gate_b: str,
    envelope: Mapping[str, str],
    tasks: TaskSummary,
) -> dict[str, Any]:
    """Classify each error, then derive one deterministic next action."""

    owner_stage = _owner_stage_from_gates(gate_a, gate_b)
    items: list[dict[str, Any]] = []
    for index, diagnostic in enumerate(ctx.diagnostics, start=1):
        if diagnostic.severity != "ERROR":
            continue
        responsible_party = "HUMAN_REVIEWER"
        category = "MANUAL_SAFETY_REVIEW"
        automatic = False
        if (
            classification == "UNCONFIGURED_TEMPLATE"
            and diagnostic.code in UNCONFIGURED_SETUP_DIAGNOSTICS
        ):
            responsible_party = "OWNER"
            category = "OWNER_SETUP"
        elif diagnostic.code in OWNER_SETUP_DIAGNOSTICS:
            responsible_party = "OWNER"
            category = "OWNER_SETUP"
        elif diagnostic.code in OWNER_DECISION_DIAGNOSTICS:
            responsible_party = "OWNER"
            category = "OWNER_DECISION"
        elif diagnostic.code in OWNER_AUTHORIZATION_DIAGNOSTICS:
            responsible_party = "OWNER"
            category = "OWNER_AUTHORIZATION"
        elif _agent_correction_is_safe(
            diagnostic, owner_stage, gate_b, envelope, tasks
        ):
            responsible_party = "CODEX"
            category = "AGENT_CORRECTION"
            automatic = True
        items.append(
            {
                "diagnostic_id": f"DGN-{index:04d}",
                "diagnostic_code": diagnostic.code,
                "path": diagnostic.path,
                "responsible_party": responsible_party,
                "category": category,
                "automatic_correction_allowed": automatic,
            }
        )

    manual = [item for item in items if item["category"] == "MANUAL_SAFETY_REVIEW"]
    codex = [item for item in items if item["category"] == "AGENT_CORRECTION"]
    owner_decisions = [item for item in items if item["category"] == "OWNER_DECISION"]
    owner_setup = [item for item in items if item["category"] == "OWNER_SETUP"]
    owner_authorization = [
        item for item in items if item["category"] == "OWNER_AUTHORIZATION"
    ]
    if manual:
        next_action = {
            "responsible_party": "HUMAN_REVIEWER",
            "action_kind": "REVIEW_SAFETY_BLOCKER",
            "automatic_continuation_allowed": False,
        }
    elif codex:
        next_action = {
            "responsible_party": "CODEX",
            "action_kind": "CORRECT_AND_REVALIDATE",
            "automatic_continuation_allowed": True,
        }
    elif owner_decisions:
        next_action = {
            "responsible_party": "OWNER",
            "action_kind": "ANSWER_OPEN_DECISIONS",
            "automatic_continuation_allowed": False,
        }
    elif owner_setup:
        next_action = {
            "responsible_party": "OWNER",
            "action_kind": (
                "COMPLETE_PREREQUISITE_CHECKLIST"
                if classification == "UNCONFIGURED_TEMPLATE"
                else "ENABLE_AWS_CORE"
            ),
            "automatic_continuation_allowed": False,
        }
    elif owner_authorization:
        next_action = {
            "responsible_party": "OWNER",
            "action_kind": _owner_authorization_action(owner_authorization),
            "automatic_continuation_allowed": False,
        }
    else:
        next_action = {
            "responsible_party": "CODEX",
            "action_kind": "CONTINUE_CURRENT_ROUTE",
            "automatic_continuation_allowed": True,
        }
    return {"items": items, "next_action": next_action}


def derive_interaction(
    lifecycle_state: str,
    next_prompt: str,
    *,
    has_errors: bool,
    diagnostic_codes: list[str],
    design_aws_core_ready: bool,
    aws_execution_planning_ready: bool,
    remediation: Mapping[str, Any] | None = None,
    owner_stage_hint: str | None = None,
) -> dict[str, Any]:
    """Derive stable owner interaction metadata without conversational prose."""

    aws_evidence_failure = any(code.startswith("AWS_CORE_") for code in diagnostic_codes)
    design_evidence_failure = any(
        code in {"AWS_CORE_EVIDENCE_REQUIRED", "AWS_CORE_EVIDENCE_STRUCTURE"}
        for code in diagnostic_codes
    )

    if lifecycle_state in {
        "INTAKE_REQUIRED",
        "REQUIREMENTS_ANALYSIS",
        "REQUIREMENTS_STALE",
        "WAITING_GATE_A",
    }:
        owner_stage = "DEFINE"
    elif lifecycle_state in {"DESIGN_REQUIRED", "DESIGN_STALE", "WAITING_GATE_B"}:
        owner_stage = "DESIGN"
    elif design_evidence_failure:
        owner_stage = "DESIGN"
    else:
        owner_stage = "DELIVER"
    if not design_evidence_failure and owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}:
        owner_stage = owner_stage_hint

    if has_errors or lifecycle_state == "BLOCKED":
        next_action = remediation.get("next_action") if remediation else None
        remediation_action = (
            str(next_action.get("action_kind", ""))
            if isinstance(next_action, Mapping)
            else ""
        )
        if remediation_action == "CORRECT_AND_REVALIDATE":
            response_mode = "OWNER_UPDATE"
            state = "WORKING"
            action_kind = "NONE_CONTINUE_AUTOMATICALLY"
            automatic = True
        elif remediation_action in {
            "ANSWER_OPEN_DECISIONS",
            "APPROVE_GATE_A",
            "APPROVE_GATE_B",
            "AUTHORIZE_AWS_OPERATION",
            "COMPLETE_PREREQUISITE_CHECKLIST",
            "ENABLE_AWS_CORE",
            "REVIEW_SAFETY_BLOCKER",
        }:
            response_mode = "BLOCKER"
            state = "BLOCKED"
            action_kind = remediation_action
            automatic = False
        else:
            response_mode = "BLOCKER"
            state = "BLOCKED"
            action_kind = "ENABLE_AWS_CORE" if aws_evidence_failure else "FIX_VALIDATION_FAILURE"
            automatic = False
        formal_receipt = False
    elif lifecycle_state == "WAITING_GATE_A":
        response_mode = "GATE_A"
        state = "AWAITING_APPROVAL"
        action_kind = "APPROVE_GATE_A"
        automatic = False
        formal_receipt = True
    elif lifecycle_state == "WAITING_GATE_B":
        response_mode = "GATE_B"
        state = "AWAITING_APPROVAL"
        action_kind = "APPROVE_GATE_B"
        automatic = False
        formal_receipt = True
    elif next_prompt.startswith("AWS-") and aws_execution_planning_ready:
        response_mode = "AWS_RECEIPT"
        state = "AWAITING_APPROVAL"
        action_kind = "AUTHORIZE_AWS_OPERATION"
        automatic = False
        formal_receipt = True
    elif next_prompt.startswith("AWS-"):
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif lifecycle_state in {"INTAKE_REQUIRED", "REQUIREMENTS_STALE"}:
        response_mode = "OWNER_UPDATE"
        state = "NEEDS_INPUT"
        action_kind = "ANSWER_OPEN_DECISIONS"
        automatic = False
        formal_receipt = False
    elif lifecycle_state == "RELEASE_VERIFIED":
        response_mode = "OWNER_UPDATE"
        state = "COMPLETE"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = False
        formal_receipt = False
    else:
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False

    material = owner_stage == "DESIGN" or next_prompt.startswith("AWS-")
    if not material:
        evidence_status = "NOT_REQUIRED"
    elif next_prompt.startswith("AWS-"):
        evidence_status = "CURRENT" if aws_execution_planning_ready else (
            "BLOCKED" if has_errors else "REQUIRED"
        )
    else:
        evidence_status = "CURRENT" if design_aws_core_ready else (
            "BLOCKED" if has_errors else "REQUIRED"
        )

    blocking_ids: list[str] = []
    if state == "BLOCKED" and remediation:
        remediation_items = remediation.get("items")
        if isinstance(remediation_items, list):
            blocking_ids = [
                str(item["diagnostic_id"])
                for item in remediation_items
                if isinstance(item, Mapping) and "diagnostic_id" in item
            ]
    if state == "BLOCKED" and not blocking_ids:
        blocking_ids = sorted(set(diagnostic_codes))

    return {
        "owner_stage": owner_stage,
        "response_mode": response_mode,
        "state": state,
        "route_reason_code": lifecycle_state,
        "owner_action_required": action_kind != "NONE_CONTINUE_AUTOMATICALLY",
        "owner_action_kind": action_kind,
        "blocking_ids": blocking_ids,
        "automatic_continuation_allowed": automatic,
        "formal_receipt_required": formal_receipt,
        "aws_core": {
            "materiality": "MATERIAL" if material else "NOT_MATERIAL",
            "evidence_status": evidence_status,
        },
    }


def derive_unconfigured_template_interaction(
    diagnostic_codes: list[str],
) -> dict[str, Any]:
    """Return honest setup-first metadata for an untouched adopter template."""

    return {
        "owner_stage": "DEFINE",
        "response_mode": "BLOCKER",
        "state": "BLOCKED",
        "route_reason_code": "UNCONFIGURED_TEMPLATE",
        "owner_action_required": True,
        "owner_action_kind": "COMPLETE_PREREQUISITE_CHECKLIST",
        "blocking_ids": sorted(set(diagnostic_codes)),
        "automatic_continuation_allowed": False,
        "formal_receipt_required": False,
        "aws_core": {
            "materiality": "NOT_MATERIAL",
            "evidence_status": "NOT_REQUIRED",
        },
    }


CONTEXT_MAXIMUM_INITIAL_BYTES = 12_000


def _context_selector_span(request: SliceRequest, text: str) -> SourceSpan:
    """Resolve one selector through the doctor's canonical Markdown helpers."""

    if request.selector_kind == "WHOLE_FILE":
        if not text:
            raise ValueError("whole-file source is empty")
        return SourceSpan(0, len(text))
    if request.selector_kind == "HEADING":
        return _heading_title_span(text, request.selector)
    if request.selector_kind == "TASK_ID":
        matches = [
            task for task in inspect_task_blocks(text) if task.task_id == request.selector
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one task {request.selector!r}; found {len(matches)}"
            )
        start = text.find(matches[0].block)
        if start < 0:
            raise ValueError(f"task {request.selector!r} has no canonical source range")
        return SourceSpan(start, start + len(matches[0].block))
    if request.selector_kind == "RECORD_ID":
        structural_lines = without_fenced_code(text).splitlines(keepends=True)
        source_lines = text.splitlines(keepends=True)
        token = re.compile(rf"(?<![A-Z0-9-]){re.escape(request.selector)}(?![A-Z0-9-])")
        matches: list[SourceSpan] = []
        offset = 0
        for source_line, structural_line in zip(source_lines, structural_lines):
            cells = (
                split_markdown_table_row(source_line.rstrip("\r\n"))
                if structural_line.strip().startswith("|")
                else None
            )
            if cells is not None and any(token.search(clean_cell(cell)) for cell in cells):
                matches.append(SourceSpan(offset, offset + len(source_line)))
            offset += len(source_line)
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one table record {request.selector!r}; found {len(matches)}"
            )
        return matches[0]
    raise ValueError(f"unsupported selector kind {request.selector_kind!r}")


def _context_request(
    value: str,
    active_ids: list[str],
    *,
    initial: bool,
) -> SliceRequest:
    path, marker, selector = value.partition("#")
    if not marker:
        selector_kind = "WHOLE_FILE"
        selector = path
        priority = 0
        reason = "Current phase procedure"
    elif TASK_ID.fullmatch(selector):
        selector_kind = "TASK_ID"
        priority = 2
        reason = "Active task and dependencies"
    else:
        selector_kind = "HEADING"
        if path == TASKS_FILE:
            priority = 2
            reason = "Active task and dependencies"
        elif path == PRD_FILE:
            priority = 3
            reason = "Controlling PRD record"
        else:
            priority = 4
            reason = "Consequential evidence or authority"
    required_selectors = {
        "Document status",
        "Active execution snapshot",
        "AWS Core evidence",
        "Action authorization provenance",
        "Conditional AWS action receipts",
    }
    required = initial and (
        selector_kind in {"WHOLE_FILE", "TASK_ID"} or selector in required_selectors
    )
    return SliceRequest(
        path=path,
        selector_kind=selector_kind,
        selector=selector,
        priority=priority if initial else 5,
        reason=reason if initial else "On-demand canonical source",
        required=required,
        active_ids=tuple(active_ids),
    )


def _resolve_context_metadata(
    source_slices: list[str],
    on_demand_slices: list[str],
    active_ids: list[str],
    source_texts: Mapping[str, str],
) -> tuple[dict[str, object], list[dict[str, str]]]:
    initial_requests = [
        _context_request(value, active_ids, initial=True) for value in source_slices
    ]
    on_demand_requests = [
        _context_request(value, active_ids, initial=False)
        for value in on_demand_slices
    ]
    return resolve_context_packet(
        initial_requests,
        on_demand_requests,
        source_texts,
        _context_selector_span,
        maximum_initial_source_bytes=CONTEXT_MAXIMUM_INITIAL_BYTES,
    )


def derive_context_plan(
    interaction: Mapping[str, Any],
    tasks: TaskSummary,
    coverage: CoverageContract,
    *,
    source_texts: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Select an ephemeral, route-bounded canonical context packet."""

    stage = interaction.get("owner_stage")
    reason = interaction.get("route_reason_code")
    if stage == "DEFINE":
        source_slices = [
            ".agents/skills/fastlane/references/define.md",
            f"{PRD_FILE}#Document status",
            f"{PRD_FILE}#Part I — Requirements",
        ]
        on_demand_slices = [
            f"{PRD_FILE}#Part II — Requirements Analysis and Gate A",
            BUGFIX_FILE,
        ]
    elif stage == "DESIGN":
        source_slices = [
            ".agents/skills/fastlane/references/design.md",
            f"{PRD_FILE}#Adaptive coverage plan",
            f"{PRD_FILE}#Architecture drivers",
            f"{PRD_FILE}#Whole-system candidates",
            f"{PRD_FILE}#Selected architecture",
            f"{VERIFY_FILE}#AWS Core evidence",
        ]
        on_demand_slices = [
            f"{PRD_FILE}#Architecture traceability",
            f"{PRD_FILE}#Change impact record",
            f"{PRD_FILE}#Gate B Harness Profile",
            f"{PRD_FILE}#Construction envelope",
        ]
    elif stage == "DELIVER":
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md",
            f"{TASKS_FILE}#Active execution snapshot",
        ]
        on_demand_slices = [
            f"{PRD_FILE}#Construction envelope",
            f"{VERIFY_FILE}#Task completion evidence",
            f"{VERIFY_FILE}#Construction and release readiness checks",
            f"{RUNBOOK_FILE}#Active operational boundary",
        ]
    else:
        raise ValueError("context plan requires a known owner stage")

    active_ids: list[str] = []
    if stage == "DELIVER":
        active_ids.extend(tasks.active)
        if not active_ids and tasks.ready:
            active_ids.append(tasks.ready[0])
    else:
        active_ids.extend(coverage.basis_ids)
    blockers = interaction.get("blocking_ids")
    if isinstance(blockers, list):
        active_ids.extend(item for item in blockers if isinstance(item, str))
    active_ids = sorted(set(active_ids))

    if stage == "DELIVER" and active_ids:
        source_slices.append(f"{TASKS_FILE}#" + active_ids[0])
    if isinstance(reason, str) and reason.startswith("AWS_"):
        source_slices.extend(
            [
                f"{VERIFY_FILE}#Action authorization provenance",
                f"{RUNBOOK_FILE}#Conditional AWS action receipts",
            ]
        )

    plan: dict[str, Any] = {
        "source_slices": source_slices,
        "active_ids": active_ids,
        "on_demand_slices": on_demand_slices,
        "maximum_initial_bytes": CONTEXT_MAXIMUM_INITIAL_BYTES,
    }
    if source_texts is not None:
        metadata, issues = _resolve_context_metadata(
            source_slices,
            on_demand_slices,
            active_ids,
            source_texts,
        )
        plan.update(metadata)
        plan["_resolution_issues"] = issues
    return plan


def _split_authority_values(value: str) -> list[str]:
    """Return conservative exact values from a comma- or semicolon-list."""

    cleaned = clean_cell(value)
    if not explicit_value(cleaned, allow_none=False):
        return []
    return [item.strip() for item in re.split(r"[,;]", cleaned) if item.strip()]


def derive_write_authority(
    ctx: Context,
    envelope: dict[str, str],
    tasks: TaskSummary,
    construction_authorization: str,
) -> dict[str, Any]:
    """Project the current Gate B and active-task write boundaries for hooks."""

    result: dict[str, Any] = {
        "valid": False,
        "authorization_id": "NONE",
        "approved_write_roots": [],
        "exclusions": [],
        "protected_paths": [],
        "active_task": "NONE",
        "active_task_write_set": [],
    }
    if ctx.has_errors or construction_authorization == "NONE":
        return result
    try:
        roots = parse_envelope_paths(
            envelope.get("Allowed repository write set", ""),
            "Allowed repository write set",
            allow_none=False,
        )
        exclusions = parse_envelope_paths(
            envelope.get("Excluded or owner-only write set", ""),
            "Excluded or owner-only write set",
            allow_none=True,
        )
        protected = parse_envelope_paths(
            envelope.get("Protected dirty paths", ""),
            "Protected dirty paths",
            allow_none=True,
        )
    except ValueError:
        return result
    active_task = tasks.active[0] if len(tasks.active) == 1 else "NONE"
    active_write_set = tasks.write_sets.get(active_task, []) if active_task != "NONE" else []
    return {
        "valid": True,
        "authorization_id": construction_authorization,
        "approved_write_roots": roots,
        "exclusions": exclusions,
        "protected_paths": protected,
        "active_task": active_task,
        "active_task_write_set": active_write_set,
    }


def _action_authorization_rows(text: str) -> dict[str, dict[str, str]]:
    heading = "## Action authorization provenance"
    structural = without_fenced_code(text)
    matches = list(re.finditer(rf"^{re.escape(heading)}[ \t]*$", structural, re.MULTILINE))
    if len(matches) != 1:
        return {}
    original_lines = text[matches[0].end() :].splitlines()
    structural_lines = structural[matches[0].end() :].splitlines()
    start = next(
        (index for index, line in enumerate(structural_lines) if line.strip().startswith("|")),
        None,
    )
    if start is None:
        return {}
    table: list[str] = []
    for original, visible in zip(original_lines[start:], structural_lines[start:]):
        if not visible.strip().startswith("|"):
            break
        table.append(original)
    if len(table) < 4:
        return {}
    headers = [clean_cell(cell) for cell in split_table_row(table[0])]
    result: dict[str, dict[str, str]] = {}
    for line in table[2:]:
        cells = [clean_cell(cell) for cell in split_table_row(line)]
        if len(cells) != len(headers):
            continue
        row = dict(zip(headers, cells))
        action = row.get("Action", "")
        if action in {"Deployment", "Teardown"} and action not in result:
            result[action] = row
    return result


def _receipt_fields(receipt: str, expected_title: str) -> dict[str, str] | None:
    lines = receipt.splitlines()
    if not lines or lines[0].strip() != expected_title:
        return None
    result: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            return None
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in result or not explicit_value(value, allow_none=True):
            return None
        result[key] = value
    return result


def _authorization_valid_until(value: str, result: str) -> str | None:
    cleaned = clean_cell(value)
    normalized = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        expires = datetime.fromisoformat(normalized)
    except ValueError:
        return cleaned if explicit_value(cleaned) and result == "NOT_STARTED" else None
    if expires.tzinfo is None or expires.utcoffset() is None:
        return None
    return cleaned if expires > datetime.now(timezone.utc) else None


def _receipt_external_authority(
    verify_text: str,
    action: str,
    construction_authorization: str,
) -> dict[str, Any] | None:
    gate = "aws-deployment" if action == "Deployment" else "aws-teardown"
    title = "AUTHORIZE AWS DEPLOYMENT" if action == "Deployment" else "AUTHORIZE AWS TEARDOWN"
    try:
        receipt = marked_receipt(verify_text, gate)
    except ValueError:
        return None
    fields = _receipt_fields(receipt, title)
    row = _action_authorization_rows(verify_text).get(action)
    if fields is None or row is None or unresolved(receipt):
        return None
    auth_key = "AWS authorization" if action == "Deployment" else "Teardown authorization"
    authorization_id = fields.get(auth_key, "")
    expected_pattern = r"AWS-AUTH-\d{4,}" if action == "Deployment" else r"TEARDOWN-AUTH-\d{4,}"
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    result = clean_cell(row.get("Result", ""))
    valid_until = _authorization_valid_until(fields.get("Valid until", ""), result)
    if (
        re.fullmatch(expected_pattern, authorization_id) is None
        or fields.get("Construction authorization") != construction_authorization
        or row.get("Authorization ID") != authorization_id
        or row.get("Construction AUTH") != construction_authorization
        or row.get("Role or profile") != fields.get("Profile or role")
        or row.get("Approver") != fields.get("Approver")
        or clean_cell(row.get("Verbatim receipt SHA-256", "")) != digest
        or clean_cell(row.get("Identity and boundary match", "")) not in {"PASS", "VERIFIED"}
        or not explicit_value(row.get("Preflight evidence", ""), allow_none=False)
        or not explicit_value(row.get("Stable owner-message source", ""), allow_none=False)
        or valid_until is None
        or result not in {"NOT_STARTED", "AUTHORIZED", "READY"}
    ):
        return None
    account = fields.get("Account", "")
    region = fields.get("Region", "")
    environment = fields.get("Environment", "")
    if not all(explicit_value(value) for value in (account, region, environment)):
        return None
    if action == "Deployment":
        resources = fields.get("Stack, application, and resources", "")
        operations = fields.get("Allowed operations", "")
        artifact = fields.get("Artifact digest", "")
        plan = fields.get("IaC plan/change-set binding", "")
        ceiling = fields.get("Cost ceiling", "")
        rollback = fields.get("Rollback boundary", "")
        kind = "AWS_DEPLOYMENT"
    else:
        resources = fields.get("Stack, application, and resources to remove", "")
        operations = fields.get("Allowed deletion operations", "")
        artifact = "NOT_APPLICABLE — teardown binds observed inventory"
        plan = "NOT_APPLICABLE — teardown uses its removal and retention manifest"
        ceiling = fields.get("Cost effect", "")
        rollback = fields.get("Post-teardown verification", "")
        kind = "AWS_TEARDOWN"
    if not all(explicit_value(value, allow_none=True) for value in (resources, operations, ceiling, rollback)):
        return None
    return {
        "kind": kind,
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "account": account,
        "region": region,
        "environment": environment,
        "role_or_profile": fields.get("Profile or role", ""),
        "resources": _split_authority_values(resources) or [resources],
        "operations": _split_authority_values(operations) or [operations],
        "artifact_plan_binding": {"artifact": artifact, "plan": plan},
        "cost_ceiling": ceiling,
        "rollback_boundary": rollback,
        "expiration": valid_until,
    }


def derive_external_authority(
    ctx: Context,
    envelope: dict[str, str],
    lane: str | None,
    construction_authorization: str,
) -> dict[str, Any]:
    """Project exact current AWS authority without creating new authority."""

    empty: dict[str, Any] = {
        "kind": "NONE",
        "validity": "NONE",
        "authorization_id": "NONE",
        "receipt_digest": "NONE",
        "account": "NONE",
        "region": "NONE",
        "environment": "NONE",
        "role_or_profile": "NONE",
        "resources": [],
        "operations": [],
        "artifact_plan_binding": {"artifact": "NONE", "plan": "NONE"},
        "cost_ceiling": "NONE",
        "rollback_boundary": "NONE",
        "expiration": "NONE",
    }
    if ctx.has_errors or construction_authorization == "NONE":
        return empty
    boundary = envelope.get("AWS boundary", "NONE")
    if boundary not in {"READ_ONLY", "MUTATE_LISTED_RESOURCES"}:
        return empty
    verify_text = ctx.texts.get(VERIFY_FILE, "")
    if lane == "explicit-gate" and boundary == "MUTATE_LISTED_RESOURCES":
        candidates = [
            item
            for item in (
                _receipt_external_authority(verify_text, "Deployment", construction_authorization),
                _receipt_external_authority(verify_text, "Teardown", construction_authorization),
            )
            if item is not None
        ]
        if len(candidates) == 1:
            return candidates[0]
        required = dict(empty)
        required["kind"] = "AWS_ACTION_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED" if not candidates else "CONFLICTING"
        return required
    try:
        expiration = parse_future_expiry(envelope.get("AWS authorization validity", ""))
    except ValueError:
        return empty
    environment = envelope.get("AWS environment", "")
    environment_name = environment
    try:
        environment_name, _environment_class = parse_aws_environment(environment)
    except ValueError:
        pass
    kind = "AWS_READ_ONLY" if boundary == "READ_ONLY" else "FAST_DEV_GATE_B"
    cost_ceiling = envelope.get("AWS cost ceiling", "NONE")
    if kind == "FAST_DEV_GATE_B":
        try:
            currency, amount = parse_positive_cost(
                cost_ceiling,
                AWS_COST_CEILING,
                "AWS cost ceiling",
            )
            cost_ceiling = f"{currency}: {amount:.2f}"
        except ValueError:
            pass
    return {
        "kind": kind,
        "validity": "CURRENT",
        "authorization_id": construction_authorization,
        "receipt_digest": "NONE",
        "account": envelope.get("AWS account", "NONE"),
        "region": envelope.get("AWS Region", "NONE"),
        "environment": environment_name,
        "role_or_profile": envelope.get("AWS role or profile", "NONE"),
        "resources": _split_authority_values(envelope.get("AWS resource allowlist", "")),
        "operations": _split_authority_values(envelope.get("AWS allowed operations", "")),
        "artifact_plan_binding": {
            "artifact": envelope.get("AWS artifact authorization and provenance", "NONE"),
            "plan": envelope.get("AWS stack or application", "NONE"),
        },
        "cost_ceiling": cost_ceiling,
        "rollback_boundary": envelope.get("AWS rollback boundary", "NONE"),
        "expiration": expiration.isoformat(),
    }


AWS_EXECUTION_CONTRACT_HEADERS = (
    "Execution ID",
    "Authority kind",
    "Authorization ID",
    "Receipt digest",
    "Script SHA-256",
    "Immutable artifact SHA-256",
    "Expected operations",
    "Resources",
    "Account",
    "Region",
    "Environment",
    "Role or profile",
    "Artifact digest",
    "Plan binding",
    "Cost ceiling",
    "Rollback boundary",
    "Valid until",
    "Evidence destination",
    "Status",
)


def _machine_value(value: Any, *labels: str) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = clean_cell(value)
    if cleaned == "NONE" or unresolved(cleaned) or cleaned.startswith("NOT_APPLICABLE"):
        return None
    for label in labels:
        prefix = label + ":"
        if cleaned.startswith(prefix):
            candidate = clean_cell(cleaned[len(prefix) :])
            return candidate if explicit_value(candidate) else None
    return cleaned if explicit_value(cleaned) else None


def _machine_list(values: Any, label: str) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        normalized = _machine_value(value, label)
        if normalized is not None and normalized not in result:
            result.append(normalized)
    return result


def _machine_cost(value: Any) -> dict[str, str] | None:
    normalized = _machine_value(value)
    if normalized is None:
        return None
    match = re.fullmatch(r"(?P<currency>[A-Z]{3}):\s*(?P<amount>\d+(?:\.\d{1,2})?)", normalized)
    if match is None:
        return None
    try:
        amount = Decimal(match.group("amount"))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return {"currency": match.group("currency"), "amount": f"{amount:.2f}"}


def _execution_contract_rows(verify_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    expected = list(AWS_EXECUTION_CONTRACT_HEADERS)
    for table in markdown_tables(verify_text):
        if not table or table[0] != expected:
            continue
        for cells in table[2:]:
            if len(cells) == len(expected):
                rows.append(dict(zip(expected, cells)))
    return rows


def _iso_datetime(value: str) -> datetime | None:
    cleaned = clean_cell(value)
    normalized = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _reviewed_script_contract(
    ctx: Context, request_match: dict[str, Any]
) -> dict[str, Any] | None:
    rows = [
        row
        for row in _execution_contract_rows(ctx.texts.get(VERIFY_FILE, ""))
        if re.fullmatch(r"AWS-EXEC-\d{4,}", clean_cell(row["Execution ID"]))
    ]
    if not rows:
        return None
    ids = [clean_cell(row["Execution ID"]) for row in rows]
    if len(ids) != len(set(ids)):
        ctx.warning(
            "AWS_EXECUTION_CONTRACT_INVALID",
            "Reviewed AWS execution contracts contain a duplicate AWS-EXEC ID",
            VERIFY_FILE,
        )
        return None
    authorization_id = request_match.get("authorization_id") or "NONE"
    candidates = [
        row for row in rows if clean_cell(row["Authorization ID"]) == authorization_id
    ]
    if len(candidates) != 1:
        ctx.warning(
            "AWS_EXECUTION_CONTRACT_INVALID",
            f"Expected one current AWS-EXEC contract for {authorization_id}; found {len(candidates)}",
            VERIFY_FILE,
        )
        return None
    row = candidates[0]
    execution_id = clean_cell(row["Execution ID"])
    issues: list[str] = []

    expected_scalars = {
        "Authority kind": request_match.get("authority_kind") or "NONE",
        "Receipt digest": request_match.get("receipt_digest") or "NONE",
        "Account": request_match.get("account") or "NONE",
        "Region": request_match.get("region") or "NONE",
        "Environment": request_match.get("environment") or "NONE",
        "Role or profile": request_match.get("role_or_profile") or "NONE",
        "Artifact digest": request_match.get("artifact_digest") or "NONE",
        "Plan binding": request_match.get("plan_binding") or "NONE",
        "Rollback boundary": request_match.get("rollback_boundary") or "NONE",
    }
    cost = request_match.get("cost_ceiling")
    expected_scalars["Cost ceiling"] = (
        f"{cost['currency']}: {cost['amount']}" if isinstance(cost, dict) else "NONE"
    )
    for field_name, expected_value in expected_scalars.items():
        if clean_cell(row[field_name]) != expected_value:
            issues.append(f"{field_name} does not match current authority")

    operations = _split_authority_values(row["Expected operations"])
    resources = _split_authority_values(row["Resources"])
    if not operations or not set(operations).issubset(set(request_match["operations"])):
        issues.append("Expected operations exceed current authority")
    if not resources or not set(resources).issubset(set(request_match["resources"])):
        issues.append("Resources exceed current authority")

    script_digest = clean_cell(row["Script SHA-256"])
    artifact_digest = clean_cell(row["Immutable artifact SHA-256"])
    digest_pattern = re.compile(r"sha256:[0-9a-f]{64}")
    bindings = [
        ("SCRIPT_SHA256", script_digest),
        ("IMMUTABLE_ARTIFACT_SHA256", artifact_digest),
    ]
    valid_bindings = [item for item in bindings if digest_pattern.fullmatch(item[1])]
    other_values = [value for _kind, value in bindings if value != "NONE"]
    if len(valid_bindings) != 1 or len(other_values) != 1:
        issues.append("exactly one reviewed script or immutable artifact digest is required")

    valid_until = _iso_datetime(row["Valid until"])
    authority_expiry = _iso_datetime(request_match.get("expires_at") or "")
    if (
        valid_until is None
        or authority_expiry is None
        or valid_until <= datetime.now(timezone.utc)
        or valid_until > authority_expiry
    ):
        issues.append("Valid until is expired or exceeds current authority")
    evidence_destination = clean_cell(row["Evidence destination"])
    if re.fullmatch(r"EV-[0-9]{4,}", evidence_destination) is None:
        issues.append("Evidence destination must be one stable EV ID")
    if clean_cell(row["Status"]) != "CURRENT":
        issues.append("Status must be CURRENT")

    if issues:
        ctx.warning(
            "AWS_EXECUTION_CONTRACT_INVALID",
            f"{execution_id}: " + "; ".join(issues),
            VERIFY_FILE,
        )
        return None
    binding_kind, binding_digest = valid_bindings[0]
    return {
        "execution_id": execution_id,
        "content_binding": {"kind": binding_kind, "sha256": binding_digest},
        "expected_operations": operations,
        "resources": resources,
        "valid_until": clean_cell(row["Valid until"]),
        "evidence_destination": evidence_destination,
    }


def derive_request_match(ctx: Context, authority: dict[str, Any]) -> dict[str, Any]:
    raw_validity = clean_cell(str(authority.get("validity", "NONE")))
    validity = raw_validity if raw_validity in {"CURRENT", "NONE", "STALE", "BLOCKED"} else "BLOCKED"
    binding = authority.get("artifact_plan_binding")
    binding = binding if isinstance(binding, dict) else {}
    request_match: dict[str, Any] = {
        "schema_version": 1,
        "validity": validity,
        "authority_kind": _machine_value(authority.get("kind")),
        "authorization_id": _machine_value(authority.get("authorization_id")),
        "receipt_digest": _machine_value(authority.get("receipt_digest")),
        "account": _machine_value(authority.get("account"), "ACCOUNT"),
        "region": _machine_value(authority.get("region"), "REGION"),
        "environment": _machine_value(authority.get("environment"), "ENVIRONMENT"),
        "role_or_profile": _machine_value(authority.get("role_or_profile"), "ROLE"),
        "resources": _machine_list(authority.get("resources"), "RESOURCES"),
        "operations": _machine_list(authority.get("operations"), "OPERATIONS"),
        "artifact_digest": _machine_value(binding.get("artifact"), "EXACT_DIGEST"),
        "plan_binding": _machine_value(binding.get("plan"), "STACK"),
        "cost_ceiling": _machine_cost(authority.get("cost_ceiling")),
        "rollback_boundary": _machine_value(authority.get("rollback_boundary"), "ROLLBACK"),
        "expires_at": _machine_value(authority.get("expiration")),
        "allowed_execution_lanes": [],
        "reviewed_script": None,
    }
    if validity != "CURRENT":
        return request_match
    request_match["allowed_execution_lanes"] = ["STRUCTURED_API"]
    reviewed_script = _reviewed_script_contract(ctx, request_match)
    if reviewed_script is not None:
        request_match["allowed_execution_lanes"].append("REVIEWED_SCRIPT")
        request_match["reviewed_script"] = reviewed_script
    return request_match

def build_report(
    ctx: Context,
    lifecycle_state: str,
    next_prompt: str,
    prd_fields: dict[str, str],
    tasks: TaskSummary,
    *,
    manifest: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    release_decision: str = "NOT_READY",
    envelope: dict[str, str] | None = None,
    aws_execution_planning_ready: bool = False,
    design_aws_core_ready: bool = False,
    design_contract: DesignContract | None = None,
    coverage_contract: CoverageContract | None = None,
) -> dict[str, Any]:
    manifest = manifest or {}
    state = state or {}
    setup = state.get("setup") if isinstance(state.get("setup"), dict) else {}
    project = state.get("project") if isinstance(state.get("project"), dict) else {}
    lifecycle = (
        state.get("lifecycle") if isinstance(state.get("lifecycle"), dict) else {}
    )
    envelope = envelope or {}
    if design_contract is None:
        design_contract = DesignContract(
            design_revision=(
                prd_fields.get("design_revision")
                or lifecycle.get("design_revision")
            )
        )
    if coverage_contract is None:
        coverage_contract = CoverageContract()
    if ctx.template_source:
        classification = "TEMPLATE_SOURCE"
    elif setup.get("status") in {
        "UNCONFIGURED_TEMPLATE",
        "{{SETUP_STATUS}}",
    }:
        classification = "UNCONFIGURED_TEMPLATE"
    elif project.get("mode") == "brownfield":
        classification = "ACTIVE_BROWNFIELD"
    else:
        classification = "ACTIVE_GREENFIELD"
    if ctx.has_errors:
        status = "BLOCKED"
    elif lifecycle_state == "INTAKE_REQUIRED":
        status = "READY"
    else:
        status = "RESUME"
    lane = project.get("aws_lane")
    aws_access = {
        None: "NOT_USED",
        "documentation-only": "DOCUMENTATION_ONLY",
        "read-only": "READ_ONLY",
        "fast-dev": "AUTHORIZED_BOUNDARY_REQUIRED",
        "explicit-gate": "EXACT_AUTHORIZATION_REQUIRED",
    }.get(lane, "NOT_USED")
    gate_a = prd_fields.get("gate_a") or lifecycle.get("gate_a") or "BLOCKED"
    gate_b = prd_fields.get("gate_b") or lifecycle.get("gate_b") or "BLOCKED"
    authorization_id = (
        prd_fields.get("construction_authorization")
        or lifecycle.get("construction_authorization")
    )
    construction_authorization = (
        authorization_id
        if not ctx.has_errors and gate_b == "APPROVED_FOR_CONSTRUCTION"
        else "NONE"
    )
    aws_boundary = envelope.get("AWS boundary", "NONE")
    aws_authorization = (
        authorization_id
        if not ctx.has_errors
        and gate_b == "APPROVED_FOR_CONSTRUCTION"
        and aws_boundary in {"READ_ONLY", "MUTATE_LISTED_RESOURCES"}
        else "NONE"
    )
    write_authority = derive_write_authority(
        ctx, envelope, tasks, construction_authorization
    )
    external_authority = derive_external_authority(
        ctx, envelope, lane, construction_authorization
    )
    external_authority["request_match"] = derive_request_match(
        ctx, external_authority
    )
    diagnostic_codes = [item.code for item in ctx.diagnostics]
    remediation = derive_remediation(
        ctx,
        classification=classification,
        gate_a=gate_a,
        gate_b=gate_b,
        envelope=envelope,
        tasks=tasks,
    )
    interaction = derive_interaction(
        lifecycle_state,
        next_prompt,
        has_errors=ctx.has_errors,
        diagnostic_codes=diagnostic_codes,
        design_aws_core_ready=design_aws_core_ready,
        aws_execution_planning_ready=aws_execution_planning_ready,
        remediation=remediation,
        owner_stage_hint=_owner_stage_from_gates(gate_a, gate_b),
    )
    if (
        classification == "UNCONFIGURED_TEMPLATE"
        and remediation["next_action"]["action_kind"]
        == "COMPLETE_PREREQUISITE_CHECKLIST"
    ):
        interaction = derive_unconfigured_template_interaction(diagnostic_codes)
    context_plan = derive_context_plan(
        interaction,
        tasks,
        coverage_contract,
        source_texts=ctx.texts,
    )
    context_issues = context_plan.pop("_resolution_issues", [])
    if context_issues:
        for issue in context_issues:
            issue_path = str(issue.get("path", ""))
            ctx.error(
                "CONTEXT_SOURCE_INVALID",
                str(issue.get("reason", "context source could not be resolved")),
                issue_path if issue_path != "NONE" else None,
            )
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
        status = "BLOCKED"
        construction_authorization = "NONE"
        aws_authorization = "NONE"
        write_authority = derive_write_authority(ctx, envelope, tasks, "NONE")
        external_authority = derive_external_authority(ctx, envelope, lane, "NONE")
        external_authority["request_match"] = derive_request_match(
            ctx, external_authority
        )
        diagnostic_codes = [item.code for item in ctx.diagnostics]
        remediation = derive_remediation(
            ctx,
            classification=classification,
            gate_a=gate_a,
            gate_b=gate_b,
            envelope=envelope,
            tasks=tasks,
        )
        interaction = derive_interaction(
            lifecycle_state,
            next_prompt,
            has_errors=True,
            diagnostic_codes=diagnostic_codes,
            design_aws_core_ready=design_aws_core_ready,
            aws_execution_planning_ready=aws_execution_planning_ready,
            remediation=remediation,
            owner_stage_hint=_owner_stage_from_gates(gate_a, gate_b),
        )
        if (
            classification == "UNCONFIGURED_TEMPLATE"
            and remediation["next_action"]["action_kind"]
            == "COMPLETE_PREREQUISITE_CHECKLIST"
        ):
            interaction = derive_unconfigured_template_interaction(diagnostic_codes)
        context_plan = derive_context_plan(
            interaction,
            tasks,
            coverage_contract,
            source_texts=ctx.texts,
        )
        context_plan.pop("_resolution_issues", None)
    return {
        "schema_version": 2,
        "bootstrap_version": manifest.get(
            "bootstrap_version", state.get("bootstrap_version")
        ),
        "status": status,
        "classification": classification,
        "ok": not ctx.has_errors,
        "lifecycle_state": lifecycle_state,
        "resume_safe": not ctx.has_errors,
        "next_prompt": next_prompt,
        "interaction": interaction,
        "remediation": remediation,
        "context_plan": context_plan,
        "project": {
            "name": project.get("name"),
            "region": project.get("region"),
            "cost_posture": project.get("cost_posture"),
            "mode": project.get("mode"),
            "delivery_profile": project.get("delivery_profile"),
        },
        "git_baseline": inspect_git_baseline(ctx.root),
        "aws_access": aws_access,
        "gates": {
            "gate_a": gate_a,
            "gate_b": gate_b,
        },
        "evidence_state": release_decision,
        "aws_core_evidence": {
            "aws_execution_planning": (
                "READY" if aws_execution_planning_ready else "BLOCKED"
            )
        },
        "authorizations": {
            "construction": construction_authorization,
            "aws": aws_authorization,
        },
        "write_authority": write_authority,
        "external_authority": external_authority,
        "basis": {
            "requirements_revision": prd_fields.get("requirements_revision"),
            "design_revision": prd_fields.get("design_revision"),
            "construction_authorization": prd_fields.get("construction_authorization"),
        },
        "coverage_plan": coverage_contract.to_dict(),
        "design_contract": design_contract.to_dict(),
        "tasks": {
            "total": tasks.total,
            "completed": len(tasks.done),
            "skipped": len(tasks.skipped),
            "blocked": len(tasks.blocked),
            "ready": len(tasks.ready),
            "in_progress": len(tasks.active),
            "ready_ids": tasks.ready,
            "active_ids": tasks.active,
            "blocked_ids": tasks.blocked,
        },
        "diagnostics": [
            item.to_dict(f"DGN-{index:04d}")
            for index, item in enumerate(ctx.diagnostics, start=1)
        ],
    }


def print_human(report: dict[str, Any]) -> None:
    status = "PASS" if report["ok"] else "BLOCKED"
    basis = report["basis"]
    print(f"AWS Codex Fastlane Doctor: {status}")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only AWS Codex Fastlane project doctor")
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
    args = parser.parse_args(argv)
    report = inspect_project(args.root, template_source=args.template_source)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
