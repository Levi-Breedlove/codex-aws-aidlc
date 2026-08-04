#!/usr/bin/env python3
"""Read-only structural and lifecycle checks for AWS Codex Fastlane projects.

``bootstrap.yaml`` intentionally uses JSON syntax. JSON is a YAML 1.2 subset,
so the state ledger remains portable while this doctor can use only Python's
standard library and reject ambiguous YAML constructs.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

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

try:
    from fastlane_owner_briefs import (
        TECHNICAL_DOMAIN_ORDER,
        answer_confirmation,
        claim as owner_claim,
        empty_owner_decision_inventory,
        empty_owner_decision_brief,
        finalize_owner_decision_inventory,
        finalize_owner_decision_brief,
        source_locator as owner_source_locator,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_owner_briefs import (
        TECHNICAL_DOMAIN_ORDER,
        answer_confirmation,
        claim as owner_claim,
        empty_owner_decision_inventory,
        empty_owner_decision_brief,
        finalize_owner_decision_inventory,
        finalize_owner_decision_brief,
        source_locator as owner_source_locator,
    )
try:
    from fastlane_document_summaries import (
        build_summary_specifications,
        canonical_bytes_without_generated_summary,
        project_document_summaries,
        strip_generated_summary,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_document_summaries import (
        build_summary_specifications,
        canonical_bytes_without_generated_summary,
        project_document_summaries,
        strip_generated_summary,
    )


try:
    from fastlane_process import resolve_trusted_git
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_process import resolve_trusted_git

try:
    from fastlane_project_identity import (
        PROJECT_NAME_TOKEN,
        normalize_aws_region,
        normalize_project_name,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_project_identity import (
        PROJECT_NAME_TOKEN,
        normalize_aws_region,
        normalize_project_name,
    )

try:
    from fastlane_stdio import configure_utf8_standard_streams
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_stdio import configure_utf8_standard_streams

try:
    from intake_response import (
        MAX_RESPONSE_CHARACTERS,
        intake_detail_safety_code,
        intake_reply_token,
        parse_intake_owner_response,
        parse_gate_correction,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.intake_response import (
        MAX_RESPONSE_CHARACTERS,
        intake_detail_safety_code,
        intake_reply_token,
        parse_intake_owner_response,
        parse_gate_correction,
    )


STATE_FILE = "bootstrap.yaml"
MANIFEST_FILE = "bootstrap.manifest.json"
PROJECT_DOCUMENT_DIRECTORY = "docs/project"
BUGFIX_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/BUGFIX.md"
PROJECT_README_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/README.md"
PRD_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/PRD.md"
RUNBOOK_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/RUNBOOK.md"
TASKS_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/TASKS.md"
VERIFY_FILE = f"{PROJECT_DOCUMENT_DIRECTORY}/VERIFY.md"
PROMPT_FILE = "prompts/CODEX-PROMPTS.md"
DOCUMENT_SUMMARY_FILES = (
    PROJECT_README_FILE,
    PRD_FILE,
    TASKS_FILE,
    VERIFY_FILE,
    RUNBOOK_FILE,
    BUGFIX_FILE,
)
REQ_ID = re.compile(r"REQ-\d{4,}")
DES_ID = re.compile(r"DES-\d{4,}")
AUTH_ID = re.compile(r"AUTH-\d{4,}")
PLAN_ID = re.compile(r"PLAN-\d{4,}")
TASK_ID = re.compile(r"TASK-\d+")
RUN_ID = re.compile(r"RUN-\d{4,}")
CHECKPOINT_ID = re.compile(r"CP-\d{4,}")
COST_AMOUNT = r"[1-9]\d*(?:\.\d{1,2})?"
AWS_COST_CEILING = re.compile(rf"(?P<currency>[A-Z]{{3}}): (?P<amount>{COST_AMOUNT})")
COST_POSTURE_WITH_CAP = re.compile(
    rf"MINIMIZE_TOTAL_COST; HARD_CAP: (?P<currency>[A-Z]{{3}}) (?P<amount>{COST_AMOUNT})"
)
DEFAULT_COST_POSTURE = "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED"
MAX_GATE_RECEIPT_CHARACTERS = 4096
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
INTAKE_FOUNDATION_HEADING = "#### Intake foundation"
INTAKE_FOUNDATION_HEADERS = (
    "Intake ID",
    "Field",
    "Value",
    "Basis",
    "Status",
    "Owner response",
)
LEGACY_INTAKE_FOUNDATION_HEADERS = INTAKE_FOUNDATION_HEADERS[:-1]
INTAKE_FOUNDATION_FIELDS = (
    ("INTAKE-0001", "OWNER_WORK_CONTEXT"),
    ("INTAKE-0002", "PRIMARY_USERS"),
    ("INTAKE-0003", "OWNER_STATED_PROBLEM"),
    ("INTAKE-0004", "OBSERVABLE_OUTCOME"),
    ("INTAKE-0005", "FIRST_RELEASE_BOUNDARY"),
    ("INTAKE-0006", "SUCCESS_MEASURE"),
    ("INTAKE-0007", "DATA_TYPES"),
    ("INTAKE-0008", "DATA_SENSITIVITY"),
    ("INTAKE-0009", "RELEASE_AUDIENCE"),
    ("INTAKE-0010", "OPERATING_GEOGRAPHY"),
)
INTAKE_CORE_FIELDS = frozenset(
    {
        "OWNER_WORK_CONTEXT",
        "PRIMARY_USERS",
        "OWNER_STATED_PROBLEM",
        "OBSERVABLE_OUTCOME",
    }
)
OWNER_WORK_CONTEXTS = {
    "NEW_APPLICATION",
    "EXISTING_APPLICATION_CHANGE",
    "REPAIR_OR_MIGRATION",
}
OWNER_WORK_CONTEXT_SELECTIONS = {
    "A": "NEW_APPLICATION",
    "B": "EXISTING_APPLICATION_CHANGE",
    "C": "REPAIR_OR_MIGRATION",
}
INTAKE_BASES = {
    "OWNER_FACT",
    "REPOSITORY_FACT",
    "AGENT_RECOMMENDATION",
    "PROPOSED_ASSUMPTION",
    "OPEN_QUESTION",
}
INTAKE_CARD_HEADING = "#### Current intake decision card"
INTAKE_CARD_HEADERS = (
    "Card ID",
    "Revision",
    "Reply key",
    "Question ID",
    "Kind",
    "Basis IDs",
    "Prompt",
    "Option A",
    "Option B",
    "Option C",
    "Recommended",
    "Required detail for",
    "Detail prompt",
    "Selection",
    "Selection detail",
    "Owner response",
)
INTAKE_ID = re.compile(r"INTAKE-\d{4,}")
INTAKE_CARD_ID = re.compile(r"INTAKE-CARD-\d{4,}")
INTAKE_QUESTION_ID = re.compile(r"INTAKE-Q-\d{4,}")
OWNER_RESPONSE_ID = re.compile(r"OWNER-MSG-\d{4,}")
INTAKE_OWNER_RESPONSE = re.compile(
    r"OWNER_RESPONSE: (?P<message>OWNER-MSG-\d{4,}); "
    r"CARD: (?P<card>INTAKE-CARD-\d{4,}); REVISION: (?P<revision>[1-9]\d*); "
    r"SHA256: (?P<digest>sha256:[0-9a-f]{64}); "
    r"QUESTION: (?P<question>INTAKE-Q-\d{4,}); ANSWER: (?P<answer>A|B|C|RESPONSE)"
)
INTAKE_RESPONSE_REGISTER_HEADING = "#### Normalized owner response register"
INTAKE_RESPONSE_REGISTER_HEADERS = (
    "Owner response ID",
    "Card ID",
    "Revision",
    "Presented card digest",
    "Reply key",
    "Question ID",
    "Selection",
    "Selection detail",
    "Basis IDs",
)
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
LEGACY_REQUIRED_TECHNOLOGY_CONCERNS = (
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
REQUIRED_TECHNOLOGY_CONCERNS = (
    *LEGACY_REQUIRED_TECHNOLOGY_CONCERNS,
    "IDENTITY_AUTHORIZATION",
    "DATA_STORAGE",
    "MESSAGING_RETRIES",
    "EDGE_NETWORKING",
    "OBSERVABILITY_INCIDENT_RESPONSE",
    "RELIABILITY_RECOVERY",
)
TECHNOLOGY_DECISION_ID = re.compile(r"TECH-\d{4}")
TECHNOLOGY_CONCERN = re.compile(r"[A-Z][A-Z0-9_]*")
STABLE_CONTRACT_ID = re.compile(r"[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
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
ARCHITECTURE_ID = re.compile(r"ARCH-\d{4,}")
ARCHITECTURE_DESIGN_ID = re.compile(
    r"(?:ARCH|COMP|API|EVENT|CLI|FILE|DATA|CTRL|BOUNDARY|STATE)-\d{3,}"
)
ARCHITECTURE_TEST_ID = re.compile(r"(?:PROP|EX|TEST)-\d{3,}")
AWS_MATERIAL_EVIDENCE_ID = re.compile(r"AWS-EV-\d{4,}")
AWS_DISCOVERY_ID = re.compile(r"AWS-DISC-\d{4,}")
AWS_READ_AUTHORIZATION_ID = re.compile(r"AWS-READ-AUTH-\d{4,}")
AWS_PREFLIGHT_ID = re.compile(r"AWS-PREFLIGHT-\d{4,}")
ARCHITECTURE_DRIVER_CLASSES = {"HARD_CONSTRAINT", "PREFERENCE", "REVISIT_TRIGGER"}
ARCHITECTURE_ELIGIBILITY = {"ELIGIBLE", "INELIGIBLE"}
AWS_DOCUMENTATION_CAPABILITIES = {"retrieve_skill", "search_documentation"}
NORMATIVE_REQUIREMENT_HEADERS = (
    "ID",
    "Requirement",
    "EARS form",
    "Acceptance ID",
    "Acceptance criteria",
    "Acceptance form",
)
LEGACY_NORMATIVE_REQUIREMENT_HEADERS = (
    "ID",
    "Requirement",
    "EARS form",
    "Acceptance criteria",
    "Acceptance form",
)
LEGACY_REQUIREMENT_HEADERS = ("ID", "Requirement", "Acceptance criteria")
PROJECT_CONTRACT_SCHEMA = "1.4"
PROJECT_DESIGN_CONTRACT_SCHEMA = "7"
APPLICATION_SOURCE_DISPOSITION_FIELD = "Application source disposition"
APPLICATION_SOURCE_GREENFIELD = "GREENFIELD_APP_ROOT"
APPLICATION_SOURCE_BROWNFIELD = "BROWNFIELD_PRESERVE"
APPLICATION_SOURCE_NOT_APPLICABLE = "NOT_APPLICABLE"
APPLICATION_SOURCE_INFRASTRUCTURE_ONLY = "NOT_APPLICABLE — INFRASTRUCTURE_ONLY"
APPLICATION_SOURCE_DIAGNOSTIC_CODES = frozenset(
    {
        "APPLICATION_SOURCE_DISPOSITION_MISSING",
        "APPLICATION_SOURCE_DISPOSITION_INVALID",
        "APPLICATION_SOURCE_DISPOSITION_CONFLICT",
        "APPLICATION_SOURCE_PARALLEL_ROOT",
    }
)
REQUIREMENTS_CHANGE_LINEAGE_HEADING = "### Requirements change lineage"
REQUIREMENTS_CHANGE_LINEAGE_HEADERS = (
    "Current revision",
    "Prior revision",
    "Trigger",
    "Added IDs",
    "Changed IDs",
    "Removed IDs",
    "Preserved IDs",
    "Stale reason",
    "Required revalidation",
)
ASSUMPTION_LIFECYCLE_HEADING = "### Assumption lifecycle"
ASSUMPTION_LIFECYCLE_HEADERS = (
    "Assumption ID",
    "Assumption",
    "Status",
    "Basis IDs",
    "Validation or successor",
)
ASSUMPTION_STATUSES = {
    "PROPOSED",
    "ACCEPTED",
    "VALIDATED",
    "INVALIDATED",
    "SUPERSEDED",
}
REQUIREMENTS_REVISION_ID = re.compile(r"REQ-\d{4,}")
ASSUMPTION_ID = re.compile(r"ASM-\d{3,}")
DIAGRAM_CONTRACT_HEADING = "### Project diagram contract"
DIAGRAM_CONTRACT_HEADERS = (
    "Diagram ID",
    "Kind",
    "Applicability",
    "Status",
    "Anchor",
    "Basis IDs",
    "Referenced IDs",
)
DIAGRAM_ID = re.compile(r"DIAGRAM-\d{4,}")
DIAGRAM_KINDS = {
    "SYSTEM_CONTEXT",
    "PRIMARY_OUTCOME",
    "DATA_LIFECYCLE",
    "FAILURE_RECOVERY",
    "MIGRATION",
    "JOURNEY",
    "STATE",
}
DIAGRAM_APPLICABILITY = {"REQUIRED", "CONDITIONAL", "NOT_APPLICABLE"}
DIAGRAM_STATUSES = {"NOT_YET_CREATED", "CURRENT", "STALE", "NOT_APPLICABLE"}
DIAGRAM_REQUIRED_KINDS = {"SYSTEM_CONTEXT", "PRIMARY_OUTCOME"}
DIAGRAM_RELATIONSHIP = re.compile(
    r"^\s*(?P<from>[A-Z][A-Z0-9_]*-\d{3,})\s*"
    r"-->\|(?P<relation>[^|\r\n]+)\|\s*"
    r"(?P<to>[A-Z][A-Z0-9_]*-\d{3,})\s*$"
)
ACTOR_HEADING = "## 4. Users and outcomes"
ACTOR_HEADERS = (
    "Actor ID",
    "Actor or external system",
    "Kind",
    "Desired outcome or responsibility",
    "Permission/data boundary",
    "Intake basis IDs",
)
ACTOR_KINDS = {"PRIMARY_USER", "SECONDARY_USER", "OPERATOR", "EXTERNAL_SYSTEM"}
ACTOR_ID = re.compile(r"ACT-\d{3,}")
ACCEPTANCE_ID = re.compile(r"AC-[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
ACCEPTANCE_TEST_BINDING_ID = re.compile(r"\b(?:TEST|PROP|EV)-\d{3,}\b")
JOURNEY_HEADING = "### Journey register"
JOURNEY_HEADERS = (
    "Journey ID",
    "Actor IDs",
    "Goal",
    "Trigger",
    "Main success outcome",
    "Alternate/failure behavior",
    "Requirement IDs",
    "Rich-use-case triggers",
)
JOURNEY_ID = re.compile(r"JOURNEY-\d{3,}")
RICH_USE_CASE_TRIGGERS = {
    "DISTINCT_PERMISSIONED_ACTORS",
    "CONFIDENTIAL_OR_REGULATED_MUTATION",
    "MONEY_OR_ENTITLEMENT",
    "IRREVERSIBLE_ACTION",
    "MIGRATION_OR_CUTOVER",
    "ASYNCHRONOUS_WORK",
    "PARTIAL_FAILURE",
}
RICH_USE_CASE_APPLICABILITY_HEADING = "### Rich-use-case applicability"
RICH_USE_CASE_APPLICABILITY_HEADERS = ("Applicability", "Trigger basis", "Use-case IDs")
RICH_USE_CASE_HEADING = "### Rich use cases"
RICH_USE_CASE_HEADERS = (
    "Use case ID",
    "Journey ID",
    "Primary actor ID",
    "Stakeholder interests",
    "Preconditions",
    "Success guarantee",
    "Minimum failure guarantee",
    "Business rule IDs",
    "Requirement IDs",
)
USE_CASE_ID = re.compile(r"USECASE-\d{3,}")
BUSINESS_RULE_HEADING = "### Business rules"
BUSINESS_RULE_HEADERS = (
    "Rule ID",
    "Rule",
    "Basis IDs",
    "Journey/use-case IDs",
    "Validation ID",
)
BUSINESS_RULE_ID = re.compile(r"BR-\d{3,}")
REQUIREMENT_COVERAGE_HEADING = "### Requirement coverage"
REQUIREMENT_COVERAGE_HEADERS = (
    "Requirement ID",
    "Intake basis IDs",
    "Actor IDs",
    "Journey IDs",
    "Acceptance/test IDs",
    "Approved success measure ID",
)
INTAKE_FOUNDATION_IDS = {f"INTAKE-{index:04d}" for index in range(1, 11)}
INTERFACE_HEADING = "## 16. Interfaces and contracts"
INTERFACE_HEADERS = (
    "Contract ID",
    "Kind",
    "Requirement basis",
    "Producer",
    "Consumer",
    "Schema or protocol",
    "Authentication",
    "Authorization",
    "Input validation",
    "Success output/status",
    "Error and recovery behavior",
    "Compatibility/versioning",
    "Idempotency/concurrency",
    "Timeout bound",
    "Rate bound",
    "Performance bound",
)
LEGACY_INTERFACE_HEADERS_V4 = (
    "Contract ID",
    "Producer",
    "Consumer",
    "Schema or protocol",
    "Authentication",
    "Versioning",
    "Idempotency",
)
INTERFACE_ID = re.compile(r"(?:API|EVENT|CLI|FILE)-\d{3,}")
INTERFACE_KINDS = {"API", "EVENT", "CLI", "FILE"}
LAYER_BOUNDARY_HEADING = "### Layer boundaries"
LAYER_BOUNDARY_HEADERS = (
    "Boundary ID",
    "Outer adapter/layer",
    "Inner domain layer",
    "Boundary DTO/schema",
    "Explicit mapping",
    "Dependency direction",
    "Authorization enforcement",
    "External anti-corruption adapter",
    "Requirement IDs",
    "Validation IDs",
)
BOUNDARY_ID = re.compile(r"BOUNDARY-\d{3,}")
STATE_APPLICABILITY_HEADING = "### State-model applicability"
STATE_APPLICABILITY_HEADERS = (
    "Subject ID",
    "Applicability",
    "Trigger basis IDs",
    "State model IDs",
)
STATE_REGISTER_HEADING = "### State register"
STATE_REGISTER_HEADERS = (
    "State model ID",
    "Subject ID",
    "States",
    "Initial state",
    "Allowed transitions",
    "Terminal states",
    "Invalid-transition behavior",
    "Requirement IDs",
    "Validation IDs",
)
STATE_ID = re.compile(r"STATE-\d{3,}")
STATE_MODEL_TRIGGERS = (
    "LIFECYCLE_RESOURCE",
    "ASYNCHRONOUS_WORK",
    "RETRY_OR_RESUME",
    "APPROVAL_FLOW",
    "MIGRATION_OR_CUTOVER",
    "OTHER_MEANINGFUL_TRANSITION",
)
RICH_TO_STATE_TRIGGER = {
    "ASYNCHRONOUS_WORK": "ASYNCHRONOUS_WORK",
    "MIGRATION_OR_CUTOVER": "MIGRATION_OR_CUTOVER",
    "PARTIAL_FAILURE": "RETRY_OR_RESUME",
}
FIRST_WAVE_HEADING = "### First construction wave"
FIRST_WAVE_HEADERS = (
    "Wave contract ID",
    "Work kind",
    "Walking-skeleton journey ID",
    "Requirement IDs",
    "Acceptance/test IDs",
    "End-to-end Harness ID",
    "Blocking spike ID",
)
WAVE_ID = re.compile(r"WAVE-\d{3,}")
SPIKE_HEADING = "### Blocking spike"
SPIKE_HEADERS = (
    "Spike ID",
    "Blocking technical unknown",
    "Time box",
    "Disposable output boundary",
    "Exit criterion",
    "Required next action",
)
SPIKE_ID = re.compile(r"SPIKE-\d{3,}")
MEASURABLE_INTERFACE_BOUND = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*(?:ns|nanoseconds?|us|microseconds?|ms|"
    r"milliseconds?|s|secs?|seconds?|minutes?|hours?|days?|weeks?|bytes?|"
    r"kib|mib|gib|kb|mb|gb|tb|requests?|operations?|events?|items?|records?|"
    r"users?|transactions?|messages?|files?|rps|qps|tps|percent)\b|"
    r"\b\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*/\s*(?:s|sec(?:ond)?s?|"
    r"m|min(?:ute)?s?|h|hours?)\b|\b\d+(?:\.\d+)?\s+per\s+"
    r"(?:second|minute|hour|day)\b)",
    re.IGNORECASE,
)
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
    "UBIQUITOUS": re.compile(r"The (?P<subject>.+?) SHALL (?P<response>.+)\."),
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
    "QAS ID",
    "Requirement IDs",
    "Source",
    "Stimulus",
    "Environment",
    "Artifact",
    "Response",
    "Response measure",
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
EXAMPLE_SCENARIO_HEADING = "## 23. Example-based scenarios"
EXAMPLE_SCENARIO_HEADERS = (
    "Test ID",
    "Scenario",
    "Expected result",
    "Layer",
)
EXAMPLE_SCENARIO_ID = re.compile(r"EX-\d{3,}")
HARNESS_EVIDENCE_DESTINATION = "docs/project/VERIFY.md#harness-execution-evidence"
MANAGED_SERVERLESS_MARKER = "MANAGED_SERVERLESS_BASELINE:"
ERROR_HANDLING_HEADING = "## 19. Error handling strategy"
ERROR_HANDLING_HEADERS = (
    "Error class",
    "Example",
    "Retry?",
    "User-visible behavior",
    "Logging or metric",
    "Recovery",
)
REQUIRED_ERROR_CLASSES = (
    "Validation",
    "Transient dependency",
    "Permanent dependency",
    "Concurrency conflict",
    "Internal defect",
)
AWS_SERVICE_DECISION_HEADING = "## 20. AWS implementation approach"
AWS_SERVICE_DECISION_HEADERS = (
    "Concern",
    "Decision IDs",
    "AWS service or mechanism",
    "Rationale",
    "Tradeoff",
)
AWS_SERVICE_TECH_CONCERNS = {
    "Compute": {"APPLICATION_RUNTIME", "APPLICATION_FRAMEWORK"},
    "API and edge": {"APPLICATION_FRAMEWORK", "EDGE_NETWORKING"},
    "Identity": {"IDENTITY_AUTHORIZATION"},
    "Data": {"DATA_STORAGE"},
    "Messaging": {"MESSAGING_RETRIES"},
    "Observability": {"OBSERVABILITY_INCIDENT_RESPONSE"},
    "Deployment": {"INFRASTRUCTURE_AS_CODE", "DEPLOYMENT_TOOLING"},
    "Secrets and encryption": {"SECURITY_VALIDATION", "IDENTITY_AUTHORIZATION"},
}
IAC_VALIDATION_HEADING = "### IaC and delivery validation contract"
IAC_VALIDATION_HEADERS = (
    "Validation path",
    "Applicability",
    "TECH binding",
    "Required local/static validation",
    "AWS planning validation",
    "Evidence destination",
)
IAC_VALIDATION_PATHS = (
    "CloudFormation / SAM / CDK",
    "Terraform",
    "Container delivery",
    "Other approved delivery path",
)
IAC_VALIDATION_TECH_CONCERNS = {
    "INFRASTRUCTURE_AS_CODE",
    "SECURITY_VALIDATION",
    "DEPLOYMENT_TOOLING",
}
IAC_VALIDATION_EVIDENCE_DESTINATION = "docs/project/VERIFY.md#iac-validation-evidence"
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
    "{{PROJECT_NAME}}",
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
    "app/README.md",
    "bootstrap.manifest.json",
    "bootstrap.py",
    "bootstrap.yaml",
    "docs/adr/0000-template.md",
    "docs/DEPENDENCY-POLICY.md",
    "docs/SETUP.md",
    "docs/TROUBLESHOOTING.md",
    "docs/WORKFLOW.md",
    "scripts/fastlane_document_summaries.py",
    "infrastructure/AGENTS.md",
    "prompts/CODEX-PROMPTS.md",
    "scripts/bootstrap_doctor.py",
    "scripts/fastlane_owner_briefs.py",
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
    presentation_texts: dict[str, str] = field(default_factory=dict)
    source_file_bytes: dict[str, bytes] = field(default_factory=dict)
    source_bytes_read: int = 0
    prior_remediation_fingerprint: str | None = None

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
    requirement_coverage_complete: bool = False
    requirement_coverage: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing_requirement_ids: list[str] = field(default_factory=list)

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
class TaskRequirementCoverage:
    requirement_id: str
    acceptance_id: str
    disposition: str
    task_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "acceptance_id": self.acceptance_id,
            "disposition": self.disposition,
            "task_ids": list(self.task_ids),
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class TaskRequirementCoverageResult:
    records: tuple[TaskRequirementCoverage, ...] = ()
    trace_issues: tuple[str, ...] = ()
    evidence_issues: tuple[str, ...] = ()
    missing_requirement_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContractTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    canonical_bytes: bytes


@dataclass(frozen=True)
class RequirementsChangeLineage:
    current_revision: str
    prior_revision: str
    trigger: str
    added_ids: tuple[str, ...]
    changed_ids: tuple[str, ...]
    removed_ids: tuple[str, ...]
    preserved_ids: tuple[str, ...]
    stale_reason: str
    required_revalidation: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_revision": self.current_revision,
            "prior_revision": self.prior_revision,
            "trigger": self.trigger,
            "added_ids": list(self.added_ids),
            "changed_ids": list(self.changed_ids),
            "removed_ids": list(self.removed_ids),
            "preserved_ids": list(self.preserved_ids),
            "stale_reason": self.stale_reason,
            "required_revalidation": list(self.required_revalidation),
        }


@dataclass(frozen=True)
class AssumptionLifecycleRecord:
    assumption_id: str
    assumption: str
    status: str
    basis_ids: tuple[str, ...]
    validation_or_successor: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption_id": self.assumption_id,
            "assumption": self.assumption,
            "status": self.status,
            "basis_ids": list(self.basis_ids),
            "validation_or_successor": self.validation_or_successor,
        }


@dataclass(frozen=True)
class RequirementsContract:
    schema_version: str = "1.4"
    status: str = "UNINITIALIZED"
    actor_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    journey_ids: tuple[str, ...] = ()
    acceptance_ids: tuple[str, ...] = ()
    use_case_ids: tuple[str, ...] = ()
    business_rule_ids: tuple[str, ...] = ()
    rich_use_case_triggers: tuple[str, ...] = ()
    change_lineage: RequirementsChangeLineage | None = None
    assumptions: tuple[AssumptionLifecycleRecord, ...] = ()
    missing_records: tuple[str, ...] = ()
    canonical_sha256: str | None = None
    grandfathered_approved_gate_a: bool = False
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "actor_ids": list(self.actor_ids),
            "requirement_ids": list(self.requirement_ids),
            "journey_ids": list(self.journey_ids),
            "acceptance_ids": list(self.acceptance_ids),
            "use_case_ids": list(self.use_case_ids),
            "business_rule_ids": list(self.business_rule_ids),
            "rich_use_case_triggers": list(self.rich_use_case_triggers),
            "change_lineage": self.change_lineage.to_dict()
            if self.change_lineage
            else None,
            "assumptions": [item.to_dict() for item in self.assumptions],
            "missing_records": list(self.missing_records),
            "canonical_sha256": self.canonical_sha256,
            "grandfathered_approved_gate_a": self.grandfathered_approved_gate_a,
        }


@dataclass(frozen=True)
class IntakeQuestion:
    reply_key: str
    question_id: str
    kind: str
    basis_ids: tuple[str, ...]
    prompt: str
    option_a: str
    option_b: str
    option_c: str
    recommended: str | None
    required_detail_for: tuple[str, ...]
    detail_prompt: str | None
    selection: str
    selection_detail: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply_key": self.reply_key,
            "question_id": self.question_id,
            "kind": self.kind,
            "basis_ids": list(self.basis_ids),
            "prompt": self.prompt,
            "options": (
                {
                    "A": self.option_a,
                    "B": self.option_b,
                    "C": self.option_c,
                }
                if self.kind == "DECISION"
                else {}
            ),
            "recommended": self.recommended,
            "required_detail_for": list(self.required_detail_for),
            "detail_prompt": self.detail_prompt,
            "selection": self.selection,
            "selection_detail": self.selection_detail,
        }


@dataclass(frozen=True)
class IntakeCard:
    card_id: str
    revision: int
    questions: tuple[IntakeQuestion, ...]
    accept_all_allowed: bool
    owner_reply: str
    exact_reply: str
    canonical_sha256: str
    reply_token: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "revision": self.revision,
            "questions": [question.to_dict() for question in self.questions],
            "accept_all_allowed": self.accept_all_allowed,
            "owner_reply": self.owner_reply,
            "exact_reply": self.exact_reply,
            "canonical_sha256": self.canonical_sha256,
            "reply_token": self.reply_token,
        }


@dataclass(frozen=True)
class NormalizedOwnerResponse:
    owner_response_id: str
    card_id: str
    revision: int
    presented_card_digest: str
    reply_key: str
    question_id: str
    selection: str
    selection_detail: str | None
    basis_ids: tuple[str, ...]

    @property
    def provenance(self) -> str:
        return (
            f"OWNER_RESPONSE: {self.owner_response_id}; CARD: {self.card_id}; "
            f"REVISION: {self.revision}; SHA256: {self.presented_card_digest}; "
            f"QUESTION: {self.question_id}; ANSWER: {self.selection}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner_response_id": self.owner_response_id,
            "card_id": self.card_id,
            "revision": self.revision,
            "presented_card_digest": self.presented_card_digest,
            "reply_key": self.reply_key,
            "question_id": self.question_id,
            "selection": self.selection,
            "selection_detail": self.selection_detail,
            "basis_ids": list(self.basis_ids),
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class IntakeFoundationContract:
    schema_version: int = 2
    status: str = "UNINITIALIZED"
    repository_mode: str | None = None
    owner_work_context: str | None = None
    current_understanding: tuple[str, ...] = ()
    basis_ids: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    pending_card: IntakeCard | None = None
    grandfathered_approved_gate_a: bool = False
    normalized_responses: tuple[NormalizedOwnerResponse, ...] = field(
        default=(), repr=False, compare=False
    )
    all_questions: tuple[IntakeQuestion, ...] = field(
        default=(), repr=False, compare=False
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "repository_mode": self.repository_mode,
            "owner_work_context": self.owner_work_context,
            "current_understanding": list(self.current_understanding),
            "basis_ids": list(self.basis_ids),
            "missing_fields": list(self.missing_fields),
            "pending_card": (
                self.pending_card.to_dict() if self.pending_card else None
            ),
            "grandfathered_approved_gate_a": self.grandfathered_approved_gate_a,
        }


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
class FirstWaveContract:
    wave_contract_id: str
    work_kind: str
    journey_id: str | None
    requirement_ids: tuple[str, ...]
    acceptance_test_ids: tuple[str, ...]
    harness_id: str
    blocking_spike_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "wave_contract_id": self.wave_contract_id,
            "work_kind": self.work_kind,
            "journey_id": self.journey_id,
            "requirement_ids": list(self.requirement_ids),
            "acceptance_test_ids": list(self.acceptance_test_ids),
            "harness_id": self.harness_id,
            "blocking_spike_id": self.blocking_spike_id,
        }


@dataclass(frozen=True)
class SpikeContract:
    spike_id: str
    technical_unknown: str
    time_box: str
    disposable_boundary: str
    exit_criterion: str
    required_next_action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "spike_id": self.spike_id,
            "technical_unknown": self.technical_unknown,
            "time_box": self.time_box,
            "disposable_boundary": self.disposable_boundary,
            "exit_criterion": self.exit_criterion,
            "required_next_action": self.required_next_action,
        }


@dataclass(frozen=True)
class DiagramRecord:
    diagram_id: str
    kind: str
    applicability: str
    status: str
    anchor: str
    basis_ids: tuple[str, ...]
    referenced_ids: tuple[str, ...]
    relationships: tuple[tuple[str, str, str], ...]
    semantic_sha256: str | None
    rendered_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagram_id": self.diagram_id,
            "kind": self.kind,
            "applicability": self.applicability,
            "status": self.status,
            "anchor": self.anchor,
            "basis_ids": list(self.basis_ids),
            "referenced_ids": list(self.referenced_ids),
            "relationships": [
                {"from_id": source, "relation": relation, "to_id": target}
                for source, relation, target in self.relationships
            ],
            "semantic_sha256": self.semantic_sha256,
            "rendered_sha256": self.rendered_sha256,
        }


@dataclass(frozen=True)
class DiagramContract:
    schema_version: int = 1
    status: str = "TEMPLATE"
    architecture_basis_id: str | None = None
    records: tuple[DiagramRecord, ...] = ()
    canonical_sha256: str | None = None
    grandfathered_schema5: bool = False
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "architecture_basis_id": self.architecture_basis_id,
            "records": [item.to_dict() for item in self.records],
            "canonical_sha256": self.canonical_sha256,
            "grandfathered_schema5": self.grandfathered_schema5,
        }


@dataclass(frozen=True)
class ApplicationSourceDisposition:
    kind: str
    paths: tuple[str, ...] = ()

    @property
    def canonical_value(self) -> str:
        if self.kind == APPLICATION_SOURCE_NOT_APPLICABLE:
            return APPLICATION_SOURCE_INFRASTRUCTURE_ONLY
        return f"{self.kind}: {'; '.join(self.paths)}"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "paths": list(self.paths)}


@dataclass(frozen=True)
class ProjectDesignContract:
    schema_version: int = 7
    status: str = "UNINITIALIZED"
    application_source_disposition: ApplicationSourceDisposition | None = None
    interface_ids: tuple[str, ...] = ()
    boundary_ids: tuple[str, ...] = ()
    state_ids: tuple[str, ...] = ()
    first_wave: FirstWaveContract | None = None
    spike: SpikeContract | None = None
    missing_records: tuple[str, ...] = ()
    canonical_sha256: str | None = None
    grandfathered_v4: bool = False
    grandfathered_v5: bool = False
    grandfathered_v6: bool = False
    canonical_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "application_source_disposition": (
                self.application_source_disposition.to_dict()
                if self.application_source_disposition is not None
                else None
            ),
            "interface_ids": list(self.interface_ids),
            "boundary_ids": list(self.boundary_ids),
            "state_ids": list(self.state_ids),
            "first_wave": self.first_wave.to_dict() if self.first_wave else None,
            "spike": self.spike.to_dict() if self.spike else None,
            "missing_records": list(self.missing_records),
            "canonical_sha256": self.canonical_sha256,
            "grandfathered_v4": self.grandfathered_v4,
            "grandfathered_v5": self.grandfathered_v5,
            "grandfathered_v6": self.grandfathered_v6,
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
    diagram_contract: DiagramContract = field(default_factory=DiagramContract)
    canonical_sha256: str | None = None
    project_contract: ProjectDesignContract = field(
        default_factory=ProjectDesignContract
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "design_revision": self.design_revision,
            "technology_decisions": [
                item.to_dict() for item in self.technology_decisions
            ],
            "property_execution": [item.to_dict() for item in self.property_execution],
            "architecture": self.architecture.to_dict(),
            "harness": self.harness.to_dict(),
            "change_impact": self.change_impact.to_dict(),
            "diagram_contract": self.diagram_contract.to_dict(),
            "canonical_sha256": self.canonical_sha256,
            "project_contract": self.project_contract.to_dict(),
            "application_source_disposition": (
                self.project_contract.application_source_disposition.to_dict()
                if self.project_contract.application_source_disposition is not None
                else None
            ),
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
TASK_AWS_MODES = {"NONE", "DOCS_ONLY"}
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
    "scripts/fastlane_process.py",
    "scripts/fastlane_project_identity.py",
    "scripts/fastlane_stdio.py",
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
AWS_DERIVED_ARTIFACT = re.compile(r"DERIVED_FROM_AUTHORIZED_SOURCE: (?P<rule>[^\r\n]+)")
TASK_BOUNDARY_DERIVED = "DERIVED_FROM_AUTHORIZED_IDS_AND_WRITE_SET"
SHELL_CONTROL = re.compile(r"[;&|><`$()\\\r\n]")
NON_HUMAN_APPROVER = re.compile(
    r"(?:^|[^a-z0-9])(?:ai|agent|assistant|automated|automation|bot|chatbot|"
    r"chatgpt|codex|gpt(?:-[0-9]+(?:\.[0-9]+)?)?|lambda|llm|model|openai|robot|"
    r"service|system|workflow|aws[ _-]*(?:core|lambda)|pending|placeholder|"
    r"not[ _-]*started)(?:$|[^a-z0-9])",
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
    header
    for header in AWS_CORE_EVIDENCE_HEADERS
    if header not in {"Discovery ID", "Basis IDs", "Discovered skill identifiers"}
)
AWS_CORE_EVIDENCE_PHASES = ("REQ-10", "DESIGN-10", "AWS-10")
AWS_CORE_REQUIRED_CAPABILITIES = ("search_documentation", "retrieve_skill")
AWS_CORE_MATERIALITY_VALUES = {"REQUIRED", "OPTIONAL", "NOT_MATERIAL"}
AWS_READ_PREFLIGHT_RECEIPT_FIELDS = (
    "Read authorization",
    "Construction authorization",
    "Profile or role",
    "Account",
    "Region",
    "Environment",
    "Stack, application, and resources",
    "Allowed read-only operations",
    "Artifact digest",
    "Prohibited operations",
    "Valid until",
    "Approver",
)
AWS_DEPLOYMENT_RECEIPT_FIELDS = (
    "AWS authorization",
    "Construction authorization",
    "Profile or role",
    "Account",
    "Region",
    "Environment",
    "Artifact digest",
    "IaC plan/change-set binding",
    "Stack, application, and resources",
    "Allowed operations",
    "Cost ceiling",
    "Rollback boundary",
    "Valid until",
    "Approver",
)
AWS_TEARDOWN_RECEIPT_FIELDS = (
    "Teardown authorization",
    "Construction authorization",
    "Profile or role",
    "Account",
    "Region",
    "Environment",
    "Stack, application, and resources to remove",
    "Resources and data to retain",
    "Allowed deletion operations",
    "Shared dependencies",
    "Cost effect",
    "Post-teardown verification",
    "Valid until",
    "Approver",
)
AWS_PLAN_BINDING = re.compile(
    r"TYPE: (?P<type>CLOUDFORMATION_CHANGE_SET|TERRAFORM_PLAN|CONTAINER_IMAGE|OTHER); "
    r"IDENTIFIER: (?P<identifier>[^;\r\n]+); DIGEST: (?P<digest>sha256:[0-9a-f]{64})"
)
AWS_READ_PREFLIGHT_HEADING = "## Read-only AWS preflight evidence"
AWS_READ_PREFLIGHT_HEADERS = (
    "Preflight ID",
    "Read authorization",
    "REQ / DES / AUTH",
    "Artifact digest",
    "Role or profile",
    "Account",
    "Region",
    "Environment",
    "Resources",
    "Operations observed",
    "AWS evidence IDs",
    "Account access",
    "Caller identity evidence",
    "Boundary and drift evidence",
    "Started at",
    "Completed at",
    "Identity and boundary match",
    "Result",
)
AWS_TEARDOWN_EVIDENCE_HEADING = "## Teardown reconciliation evidence"
AWS_TEARDOWN_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Attempt ID",
    "Phase",
    "REQ / DES / AUTH",
    "Read authorization",
    "Read role or profile",
    "Read receipt digest",
    "Read valid until",
    "Read authority source",
    "Teardown authorization",
    "Teardown receipt digest",
    "Role or profile",
    "Expected manifest or stack",
    "Resources proposed to remove",
    "Allowed deletion operations",
    "Resources retained",
    "Shared dependencies",
    "Cost effect",
    "Post-teardown verification",
    "Stack events and terminal status",
    "Resources removed",
    "Snapshots and backups",
    "Residual resources",
    "Inventory or discovery limits",
    "Account / Region / environment",
    "Observed at",
    "Durable source",
    "Identity and boundary match",
    "Blocker or stale reason",
    "Status",
)
AWS_TEARDOWN_REVIEW_STATUSES = {
    "RUNNING",
    "READY_FOR_TEARDOWN",
    "VERIFIED_CLEAN",
    "RESIDUALS_REMAIN",
    "BLOCKED",
    "STALE",
}
AWS_TEARDOWN_ACTION_STATUSES = {
    "STARTED",
    "SUCCEEDED",
    "FAILED",
    "PARTIAL",
    "UNKNOWN",
}
AWS_TEARDOWN_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN"}
AWS_TEARDOWN_ATTEMPT_ID = re.compile(r"AWS-TEARDOWN-\d{4,}")
AWS_TEARDOWN_READ_PROVENANCE = re.compile(
    r"SOURCE: (?P<source>[^;\r\n]+); "
    r"AUTHORIZED_AT: (?P<authorized_at>[^;\r\n]+)"
)
AWS_DEPLOYMENT_READ_PROVENANCE = re.compile(
    r"SOURCE: (?P<source>[^;|\r\n]+); "
    r"AUTHORIZED_AT: (?P<authorized_at>[^;|\r\n]+); "
    r"RESOURCES: (?P<resources>[^;|\r\n]+); "
    r"OPERATIONS: (?P<operations>[^;|\r\n]+)"
)
AWS_TEARDOWN_PRECALL_RESULT = "NOT_OBSERVED — pre-call journal only"
AWS_DEPLOYMENT_EVIDENCE_HEADING = "## AWS deployment action and reconciliation evidence"
AWS_DEPLOYMENT_EVIDENCE_HEADERS = (
    "Evidence ID",
    "Attempt ID",
    "Phase",
    "REQ / DES / AUTH",
    "Deployment authorization",
    "Deployment receipt digest",
    "Deployment valid until",
    "Deployment authority source",
    "Read authorization",
    "Deployment role or profile",
    "Read role or profile",
    "Read receipt digest",
    "Read valid until",
    "Read authority source",
    "Artifact digest",
    "Plan/change-set binding",
    "Resources",
    "Mutation operations",
    "Read operations observed",
    "Account / Region / environment",
    "Operation identifiers and direct result",
    "Rollback result",
    "Acceptance evidence IDs",
    "Observed at",
    "Durable source",
    "Identity and boundary match",
    "Blocker or stale reason",
    "Status",
)
AWS_DEPLOYMENT_ATTEMPT_ID = re.compile(r"AWS-DEPLOY-\d{4,}")
AWS_DEPLOYMENT_ACTION_STATUSES = {
    "STARTED",
    "SUCCEEDED",
    "FAILED",
    "PARTIAL",
    "UNKNOWN",
}
AWS_DEPLOYMENT_TERMINAL_STATUSES = AWS_DEPLOYMENT_ACTION_STATUSES - {"STARTED"}
AWS_DEPLOYMENT_RECONCILIATION_STATUSES = {"COMPLETE", "BLOCKED", "STALE"}
AWS_DEPLOYMENT_PRECALL_RESULT = "NOT_OBSERVED \u2014 pre-call journal only"
VERIFICATION_MATRIX_HEADING = "## Verification matrix"
VERIFICATION_MATRIX_HEADERS = (
    "Evidence ID",
    "PRD / property IDs",
    "Task IDs",
    "Requirement or invariant",
    "Automated evidence",
    "AWS/manual evidence",
    "Artifact/environment",
    "Status",
)
AWS_READ_ONLY_OPERATION = re.compile(
    r"(?i)^(?:[a-z0-9-]+[.:])?(?:BatchGet|Check|Describe|Detect|Estimate|Get|"
    r"Head|List|Lookup|Preview|Search|Simulate|Validate)[A-Za-z0-9]*$"
)
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
AWS_CORE_OFFICIAL_DOCUMENTATION_URL_PATTERN = re.compile(
    r"https://(?:docs\.aws\.amazon\.com|aws\.amazon\.com)/[^\s<>)\]|,;]+",
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
        return (
            []
            if raw in {"", "NONE", "-"}
            else [item.strip() for item in raw.split(",")]
        )

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
        marker = (
            "```"
            if stripped.startswith("```")
            else "~~~"
            if stripped.startswith("~~~")
            else None
        )
        if marker is not None:
            fence = None if fence == marker else marker if fence is None else fence
            result.append(
                " " * (len(line.rstrip("\r\n"))) + line[len(line.rstrip("\r\n")) :]
            )
        elif fence is None:
            result.append(line)
        else:
            result.append(
                " " * (len(line.rstrip("\r\n"))) + line[len(line.rstrip("\r\n")) :]
            )
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
        raise ValueError(
            "VERIFY.md requires exactly one Task completion evidence section"
        )
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
    separator = (
        split_markdown_table_row(lines[header + 1]) if header + 1 < len(lines) else None
    )
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
            raise ValueError(
                "VERIFY.md Task completion evidence row must have nine cells"
            )
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
    headings = list(
        re.finditer(r"^## AWS Core evidence[ \t]*$", structural, re.MULTILINE)
    )
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
    separator = (
        split_markdown_table_row(lines[header + 1]) if header + 1 < len(lines) else None
    )
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
            raise ValueError(
                f"VERIFY.md AWS Core evidence has unknown phase {row.phase!r}"
            )
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
    present_phases = sorted(
        {row_phase for row_phase, _discovery_id, _capability in rows}
    )
    for phase in present_phases:
        discovery_ids = sorted(
            {discovery_id for row_phase, discovery_id, _ in rows if row_phase == phase}
        )
        if not discovery_ids:
            missing.append(f"{phase} discovery chain")
            continue
        for discovery_id in discovery_ids:
            for capability in AWS_CORE_REQUIRED_CAPABILITIES:
                if (phase, discovery_id, capability) not in rows:
                    missing.append(f"{phase} {discovery_id or 'legacy'} {capability}")
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
    if phase == "REQ-10":
        expected = (
            "NOT_APPLICABLE \u2014 requirements feasibility only; "
            "no architecture selected"
        )
        if cleaned != expected:
            raise ValueError(
                "REQ-10 Advisory Design binding must prove requirements feasibility "
                "without selecting an architecture"
            )
        return
    not_applicable_prefix = "NOT_APPLICABLE — "
    if cleaned.startswith(not_applicable_prefix):
        if phase not in {"REQ-10", "AWS-10"} or not explicit_value(
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
            issues.append(f"{label} plugin source must be {AWS_CORE_OFFICIAL_SOURCE}")
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
                require_explicit_evidence_value(
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
                require_explicit_evidence_value(
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
    expected_basis_ids: set[str] | None = None,
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
            issues.append(
                f"{phase} {discovery_id} requires linked search and retrieve rows"
            )
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
        if expected_basis_ids is not None and set(basis_ids) != expected_basis_ids:
            issues.append(
                f"{phase} {discovery_id} Basis IDs must exactly match the current "
                "AWS materiality basis IDs"
            )
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
                issues.append(f"{phase} {discovery_id} rows must share {field_name}")
        if retrieve.requested_skill != retrieve.returned_skill_identifier:
            issues.append(
                f"{phase} {discovery_id} retrieved identifier must equal the selected identifier"
            )
        if retrieve.returned_skill_identifier not in discovered:
            issues.append(
                f"{phase} {discovery_id} retrieved identifier was not returned by search"
            )

        if explicit_timestamp(search.observed_at) and explicit_timestamp(
            retrieve.observed_at
        ):
            searched_at = datetime.fromisoformat(
                search.observed_at.replace("Z", "+00:00")
            )
            retrieved_at = datetime.fromisoformat(
                retrieve.observed_at.replace("Z", "+00:00")
            )
            if retrieved_at < searched_at:
                issues.append(
                    f"{phase} {discovery_id} retrieve timestamp precedes search"
                )
    return issues


def derive_aws_core_observed_usage(
    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    issues: Sequence[str],
) -> dict[str, Any]:
    """Project only validated observable AWS Core use into owner-safe fields."""

    unobserved: dict[str, Any] = {
        "status": "UNOBSERVED",
        "phase": phase,
        "chains": [],
    }
    if issues:
        return unobserved
    chains: list[dict[str, Any]] = []
    discovery_ids = sorted(
        {
            discovery_id
            for row_phase, discovery_id, _capability in rows
            if row_phase == phase and discovery_id
        }
    )
    for discovery_id in discovery_ids:
        search = rows.get((phase, discovery_id, "search_documentation"))
        retrieve = rows.get((phase, discovery_id, "retrieve_skill"))
        if search is None or retrieve is None:
            continue
        references = sorted(
            set(
                AWS_CORE_OFFICIAL_DOCUMENTATION_URL_PATTERN.findall(
                    search.source_references
                )
            )
        )
        if not references:
            continue
        chains.append(
            {
                "discovery_id": discovery_id,
                "skill_identifier": retrieve.returned_skill_identifier,
                "official_references": references,
                "credentials_inspected": False,
                "aws_account_accessed": False,
            }
        )
    if not chains:
        return unobserved
    return {"status": "OBSERVED", "phase": phase, "chains": chains}


def aws_core_evidence_diagnostic_code(issue: str) -> str:
    """Classify generated AWS evidence gaps without assigning them to the owner."""

    if (
        "requires at least one AWS-DISC discovery chain" in issue
        or "requires linked search and retrieve rows" in issue
    ):
        return "AWS_CORE_DISCOVERY_REQUIRED"
    if any(
        marker in issue
        for marker in (
            "does not match current",
            "must exactly match the current",
            "must include DES-",
        )
    ):
        return "AWS_CORE_EVIDENCE_STALE"
    return "AWS_CORE_EVIDENCE_GENERATED_INVALID"


def require_aws_core_phase_evidence(
    ctx: Context,
    rows: dict[tuple[str, str, str], AwsCoreEvidenceRow],
    phase: str,
    *,
    expected_binding: str | None = None,
    expected_design_revision: str | None = None,
    approved_tech_ids: set[str] | None = None,
    expected_basis_ids: set[str] | None = None,
    allow_legacy_discovery: bool = False,
) -> None:
    """Block a phase boundary unless both official AWS Core calls are evidenced."""

    for issue in aws_core_phase_evidence_issues(
        rows,
        phase,
        expected_binding=expected_binding,
        expected_design_revision=expected_design_revision,
        approved_tech_ids=approved_tech_ids,
        expected_basis_ids=expected_basis_ids,
        allow_legacy_discovery=allow_legacy_discovery,
    ):
        ctx.error(aws_core_evidence_diagnostic_code(issue), issue, VERIFY_FILE)


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
        and re.fullmatch(r"git:[0-9a-fA-F]{7,64}", source, re.IGNORECASE) is None
        and re.fullmatch(r"(?:https?|s3)://\S+", source, re.IGNORECASE) is None
        and not path_source
    ):
        raise ValueError(f"{label} is not a local durable reference")
    return source


def validate_done_evidence(verify_text: str | None, task: InspectedTask) -> None:
    evidence = clean_cell(task.metadata.get("Evidence", ""))
    references = [match.group(0) for match in EVIDENCE_PATTERN.finditer(evidence)]
    local = [
        reference for reference in references if re.fullmatch(r"EV-\d{4,}", reference)
    ]
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
        raise ValueError(
            f"{task.task_id}: DONE requires at least one local Evidence reference"
        )
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
            raise ValueError(
                f"{label} requires an explicit commit, worktree, or artifact"
            )
        require_durable_evidence_source(row.durable_source, f"{label} durable source")
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
    if any(
        not item or any(character in item for character in "*?[]{}") for item in values
    ):
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
        for property_id in PROPERTY_ID.findall(
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


def task_requirement_rules(
    prd_text: str,
    requirements_contract: RequirementsContract,
) -> dict[str, tuple[str, str]]:
    """Return current requirement ID to acceptance ID and EARS form."""

    if requirements_contract.grandfathered_approved_gate_a:
        return {}
    rows, acceptance_by_requirement, _legacy_ids = _schema_13_requirement_rows(prd_text)
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
    """Resolve current no-task requirement dispositions from VERIFY.md."""

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
            basis_ids = _canonical_id_list(
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
    """Derive one complete disposition for every approved requirement."""

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


def parse_exact_id_list(
    value: str, pattern: re.Pattern[str], field_name: str
) -> list[str]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return []
    if unresolved(cleaned):
        raise ValueError(f"{field_name} is unresolved")
    items = [item.strip() for item in cleaned.split(",")]
    if any(pattern.fullmatch(item) is None for item in items):
        raise ValueError(
            f"{field_name} must contain comma-separated {pattern.pattern} IDs or NONE"
        )
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
        while index < len(source_lines) and structural_lines[index].strip().startswith(
            "|"
        ):
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
            raise ValueError(f"{task_id}: property execution projection {exc}") from exc
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
            f"{task_id}: Requirements references unknown PROP IDs: "
            + ", ".join(unknown)
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


def _heading_section_offsets(text: str, heading: str) -> tuple[int, int, int] | None:
    """Return heading start, body start, and section end using canonical rules."""

    structural = without_fenced_code(text)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*\r?$", structural, re.MULTILINE)
    )
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one heading {heading!r}; found {len(matches)}"
        )
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
        raise ValueError(
            f"expected exactly one heading title {title!r}; found {len(matches)}"
        )
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
        if (
            header is None
            or tuple(clean_cell(cell) for cell in header) != expected_headers
        ):
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
            "(?P<class>"
            + "|".join(sorted(PROPERTY_TEST_FAILURE_CLASSES))
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
        return explicit_value(cleaned.removeprefix("ORG_MANAGED: "), allow_none=False)
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
    return (
        unresolved(cleaned) or EVIDENCE_PLACEHOLDER_PATTERN.search(cleaned) is not None
    )


def technology_reasoning_parts(value: str) -> tuple[str, str]:
    """Split the canonical reasoning cell without duplicating its prose."""

    cleaned = clean_cell(value)
    prefix = "RATIONALE: "
    separator = "; REJECTED: "
    if not cleaned.startswith(prefix) or separator not in cleaned:
        raise ValueError(
            "Alternatives and rationale must use "
            "RATIONALE: <selection reason>; REJECTED: <alternatives and reasons>"
        )
    rationale, rejected = cleaned[len(prefix) :].split(separator, 1)
    if not explicit_value(rationale, allow_none=False) or not explicit_value(
        rejected, allow_none=False
    ):
        raise ValueError(
            "Technology rationale and rejected alternatives must be concrete"
        )
    return rationale, rejected


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
    return (
        bool(identifiers)
        and all(
            STABLE_CONTRACT_ID.fullmatch(identifier) is not None
            for identifier in identifiers
        )
        and len(identifiers) == len(set(identifiers))
    )


def authoritative_requirement_ids(text: str) -> set[str]:
    """Return every stable ID in an authoritative requirement table."""

    identifiers: set[str] = set()
    for table in markdown_tables(text):
        if not table or tuple(table[0]) not in {
            NORMATIVE_REQUIREMENT_HEADERS,
            LEGACY_REQUIREMENT_HEADERS,
            LEGACY_NORMATIVE_REQUIREMENT_HEADERS,
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
    following = re.search(r"^#{1,3}\s+", structural[heading.end() :], re.MULTILINE)
    end = heading.end() + following.start() if following else len(structural)
    section = structural[heading.end() : end]
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
        return [
            "QAS-SECTION: exactly one Quality attribute scenarios table is required"
        ]

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
    legacy_header_shapes: set[tuple[str, ...]] = set()
    modern_tables = 0
    for table in markdown_tables(text):
        if not table:
            continue
        headers = tuple(table[0])
        if headers in {
            LEGACY_NORMATIVE_REQUIREMENT_HEADERS,
            LEGACY_REQUIREMENT_HEADERS,
        }:
            found = True
            legacy_header_shapes.add(headers)
            legacy_rows.extend(
                clean_cell(row[0]) if row else "REQ-UNKNOWN" for row in table[2:]
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
                    f"{row_id}: normative requirement row must have exactly six fields",
                    PRD_FILE,
                )
                continue
            acceptance_id = clean_cell(row[3])
            expected_acceptance_id = f"AC-{row_id}"
            if (
                ACCEPTANCE_ID.fullmatch(acceptance_id) is None
                or acceptance_id != expected_acceptance_id
            ):
                ctx.error(
                    "REQUIREMENT_METHOD_CONTRACT",
                    f"{row_id}: Acceptance ID must be exactly {expected_acceptance_id}",
                    PRD_FILE,
                )
            for issue in requirement_method_issues(
                row[0], row[1], row[2], row[4], row[5]
            ):
                ctx.error("REQUIREMENT_METHOD_CONTRACT", issue, PRD_FILE)
    if not found:
        ctx.error(
            "REQUIREMENT_METHOD_CONTRACT",
            "REQ-SECTION: no authoritative normative requirement table was found",
            PRD_FILE,
        )
        return

    legacy_is_grandfathered = bool(
        grandfather_approved_v1
        and legacy_rows
        and modern_tables == 0
        and len(legacy_header_shapes) == 1
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


def _schema_13_requirement_rows(
    text: str,
) -> tuple[list[tuple[str, ...]], dict[str, str], list[str]]:
    rows: list[tuple[str, ...]] = []
    acceptance_by_requirement: dict[str, str] = {}
    legacy_ids: list[str] = []
    for table in markdown_tables(text):
        if not table:
            continue
        headers = tuple(table[0])
        if headers in {
            LEGACY_NORMATIVE_REQUIREMENT_HEADERS,
            LEGACY_REQUIREMENT_HEADERS,
        }:
            legacy_ids.extend(
                clean_cell(row[0]) if row else "REQ-UNKNOWN" for row in table[2:]
            )
            continue
        if headers != NORMATIVE_REQUIREMENT_HEADERS:
            continue
        for row in table[2:]:
            if len(row) != len(NORMATIVE_REQUIREMENT_HEADERS):
                continue
            normalized = tuple(clean_cell(cell) for cell in row)
            rows.append(normalized)
            acceptance_by_requirement[normalized[0]] = normalized[3]
    return rows, acceptance_by_requirement, legacy_ids


def _contract_table_or_issue(
    text: str,
    heading: str,
    headers: tuple[str, ...],
    issues: list[Any],
    missing_records: list[str],
    code: str | None = None,
) -> ContractTable | None:
    try:
        table = contract_table_after_heading(text, heading, headers)
    except ValueError as exc:
        table, message = None, f"{heading}: {exc}"
    else:
        message = f"Missing {heading}" if table is None else None
    if table is None:
        issues.append((code, message) if code else message)
        missing_records.append(heading)
    return table


def _contract_ids(
    value: str,
    pattern: re.Pattern[str],
    field_name: str,
) -> list[str]:
    return _canonical_id_list(clean_cell(value), pattern, field_name)


def _rich_trigger_list(value: str, journey_id: str) -> list[str]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return []
    if unresolved(cleaned):
        raise ValueError(f"{journey_id}: Rich-use-case triggers is unresolved")
    triggers = cleaned.split(", ")
    if cleaned != ", ".join(triggers):
        raise ValueError(
            f"{journey_id}: Rich-use-case triggers must use comma-space separation"
        )
    unknown = sorted(set(triggers) - RICH_USE_CASE_TRIGGERS)
    if unknown:
        raise ValueError(
            f"{journey_id}: unknown Rich-use-case triggers: " + ", ".join(unknown)
        )
    if len(triggers) != len(set(triggers)):
        raise ValueError(f"{journey_id}: Rich-use-case triggers contains duplicates")
    return triggers


def _state_trigger_map(value: str, subject_id: str) -> dict[str, tuple[str, ...]]:
    cleaned = clean_cell(value)
    segments = cleaned.split("; ")
    if unresolved(cleaned) or cleaned != "; ".join(segments):
        raise ValueError(
            f"{subject_id}: State trigger basis must use canonical '; ' segments"
        )
    result: dict[str, tuple[str, ...]] = {}
    for segment in segments:
        parts = segment.split(": ", 1)
        if len(parts) != 2 or parts[0] not in STATE_MODEL_TRIGGERS:
            raise ValueError(f"{subject_id}: invalid State trigger category")
        category, basis_value = parts
        if category in result:
            raise ValueError(
                f"{subject_id}: duplicate State trigger category {category}"
            )
        result[category] = tuple(
            _contract_ids(
                basis_value, STABLE_CONTRACT_ID, f"{subject_id} {category} basis IDs"
            )
        )
    if list(result) != [item for item in STATE_MODEL_TRIGGERS if item in result]:
        raise ValueError(
            f"{subject_id}: State trigger categories are not in canonical order"
        )
    return result


def derive_requirements_contract(
    text: str,
    effective_risk: str | None,
    intake_contract: IntakeFoundationContract | None = None,
    *,
    required: bool,
    grandfather_current_gate_a: bool,
) -> tuple[RequirementsContract, list[tuple[str, str]]]:
    """Derive the owner-grounded schema 1.4 requirements projection."""

    issues: list[tuple[str, str]] = []

    def add(code: str, message: str) -> None:
        issues.append((code, message))

    missing_records: list[str] = []
    try:
        document = table_after_heading(text, "## Document status")
    except ValueError as exc:
        document = {}
        if required:
            add("PROJECT_CONTRACT_MIGRATION_REQUIRED", str(exc))
    project_schema = clean_cell(document.get("Project contract schema", ""))
    requirement_rows, acceptance_by_requirement, legacy_ids = (
        _schema_13_requirement_rows(text)
    )
    requirement_row_by_id = {row[0]: row for row in requirement_rows}

    observed_headers = {tuple(table[0]) for table in markdown_tables(text) if table}
    current_header_map = {
        NORMATIVE_REQUIREMENT_HEADERS: "Six-column normative requirements",
        ACTOR_HEADERS: ACTOR_HEADING,
        JOURNEY_HEADERS: JOURNEY_HEADING,
        RICH_USE_CASE_APPLICABILITY_HEADERS: RICH_USE_CASE_APPLICABILITY_HEADING,
        RICH_USE_CASE_HEADERS: RICH_USE_CASE_HEADING,
        BUSINESS_RULE_HEADERS: BUSINESS_RULE_HEADING,
        REQUIREMENT_COVERAGE_HEADERS: REQUIREMENT_COVERAGE_HEADING,
        REQUIREMENTS_CHANGE_LINEAGE_HEADERS: REQUIREMENTS_CHANGE_LINEAGE_HEADING,
        ASSUMPTION_LIFECYCLE_HEADERS: ASSUMPTION_LIFECYCLE_HEADING,
    }
    current_present_headers = observed_headers & set(current_header_map)
    header_sections = (
        (ACTOR_HEADING, ACTOR_HEADERS),
        (JOURNEY_HEADING, JOURNEY_HEADERS),
        (RICH_USE_CASE_APPLICABILITY_HEADING, RICH_USE_CASE_APPLICABILITY_HEADERS),
        (RICH_USE_CASE_HEADING, RICH_USE_CASE_HEADERS),
        (BUSINESS_RULE_HEADING, BUSINESS_RULE_HEADERS),
        (REQUIREMENT_COVERAGE_HEADING, REQUIREMENT_COVERAGE_HEADERS),
        (REQUIREMENTS_CHANGE_LINEAGE_HEADING, REQUIREMENTS_CHANGE_LINEAGE_HEADERS),
        (ASSUMPTION_LIFECYCLE_HEADING, ASSUMPTION_LIFECYCLE_HEADERS),
    )
    for heading, headers in header_sections:
        try:
            if contract_table_after_heading(text, heading, headers) is not None:
                current_present_headers.add(headers)
        except ValueError:
            pass
    grandfather_schema_13 = bool(project_schema == "1.3" and grandfather_current_gate_a)
    if project_schema != PROJECT_CONTRACT_SCHEMA and not grandfather_schema_13:
        legacy_headers = observed_headers & {
            LEGACY_NORMATIVE_REQUIREMENT_HEADERS,
            LEGACY_REQUIREMENT_HEADERS,
        }
        real_legacy_ids = [
            identifier
            for identifier in legacy_ids
            if STABLE_CONTRACT_ID.fullmatch(identifier)
        ]
        exact_legacy_shape = bool(
            not project_schema
            and real_legacy_ids
            and len(real_legacy_ids) == len(legacy_ids)
            and len(real_legacy_ids) == len(set(real_legacy_ids))
            and len(legacy_headers) == 1
            and not current_present_headers
        )
        if grandfather_current_gate_a and exact_legacy_shape:
            approved_ids = tuple(sorted(real_legacy_ids))
            legacy_rows = [
                tuple(clean_cell(cell) for cell in row)
                for table in markdown_tables(text)
                if table
                and tuple(table[0])
                in {LEGACY_NORMATIVE_REQUIREMENT_HEADERS, LEGACY_REQUIREMENT_HEADERS}
                for row in table[2:]
            ]
            canonical_bytes = (
                b"PROJECT_CONTRACT_SCHEMA: 1.2\n"
                + json.dumps(
                    (
                        clean_cell(document.get("Current requirements revision", "")),
                        legacy_rows,
                    ),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            contract = RequirementsContract(
                schema_version="1.2",
                status="GRANDFATHERED",
                requirement_ids=approved_ids,
                acceptance_ids=tuple(f"AC-{item}" for item in approved_ids),
                canonical_sha256="sha256:"
                + hashlib.sha256(canonical_bytes).hexdigest(),
                canonical_bytes=canonical_bytes,
                grandfathered_approved_gate_a=True,
            )
            return contract, []
        if not required:
            return RequirementsContract(status="UNINITIALIZED"), []
        migration_targets = ["Project contract schema 1.4"]
        migration_targets.extend(
            label
            for headers, label in current_header_map.items()
            if headers not in current_present_headers
        )
        message = (
            "Project contract schema 1.4 is required before Gate A readiness; "
            "migrate only the listed generated records without inventing owner facts: "
            + ", ".join(migration_targets)
        )
        return (
            RequirementsContract(
                status="MIGRATION_REQUIRED", missing_records=tuple(migration_targets)
            ),
            [("PROJECT_CONTRACT_MIGRATION_REQUIRED", message)],
        )

    if intake_contract is None:
        repository_mode = clean_cell(document.get("Project mode", "")).lower()
        intake_contract, _intake_issues = derive_intake_foundation_contract(
            text,
            repository_mode if repository_mode in PROJECT_MODES else None,
            grandfather_current_gate_a=grandfather_current_gate_a,
        )
    confirmed_intake_ids = set(intake_contract.basis_ids)
    if required and intake_contract.status != "READY_FOR_REQUIREMENTS":
        add(
            "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
            "Schema 1.4 actor and success-measure bases require a complete confirmed intake foundation",
        )

    table_specs = (
        (ACTOR_HEADING, ACTOR_HEADERS, "ACTOR_CONTRACT_INVALID"),
        (JOURNEY_HEADING, JOURNEY_HEADERS, "JOURNEY_CONTRACT_INVALID"),
        (
            RICH_USE_CASE_APPLICABILITY_HEADING,
            RICH_USE_CASE_APPLICABILITY_HEADERS,
            "RICH_USE_CASE_INVALID",
        ),
        (RICH_USE_CASE_HEADING, RICH_USE_CASE_HEADERS, "RICH_USE_CASE_INVALID"),
        (BUSINESS_RULE_HEADING, BUSINESS_RULE_HEADERS, "BUSINESS_RULE_INVALID"),
        (
            REQUIREMENT_COVERAGE_HEADING,
            REQUIREMENT_COVERAGE_HEADERS,
            "REQUIREMENT_COVERAGE_INVALID",
        ),
    )
    tables = tuple(
        _contract_table_or_issue(text, heading, headers, issues, missing_records, code)
        for heading, headers, code in table_specs
    )
    actors, journeys, applicability, use_cases, business_rules, coverage = tables
    lineage_table: ContractTable | None = None
    assumption_table: ContractTable | None = None
    if not grandfather_schema_13:
        lineage_table = _contract_table_or_issue(
            text,
            REQUIREMENTS_CHANGE_LINEAGE_HEADING,
            REQUIREMENTS_CHANGE_LINEAGE_HEADERS,
            issues,
            missing_records,
            "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
        )
        assumption_table = _contract_table_or_issue(
            text,
            ASSUMPTION_LIFECYCLE_HEADING,
            ASSUMPTION_LIFECYCLE_HEADERS,
            issues,
            missing_records,
            "ASSUMPTION_LIFECYCLE_INVALID",
        )
    contract_tables = (*tables, lineage_table, assumption_table)
    if grandfather_schema_13:
        contract_tables = tables
    if legacy_ids:
        add(
            "PROJECT_CONTRACT_MIGRATION_REQUIRED",
            "Migrate legacy normative rows to schema 1.4: " + ", ".join(legacy_ids),
        )
        missing_records.extend(legacy_ids)
    requirement_ids = [row[0] for row in requirement_rows]
    duplicate_requirements = sorted(
        identifier
        for identifier in set(requirement_ids)
        if requirement_ids.count(identifier) > 1
    )
    if duplicate_requirements:
        add(
            "REQUIREMENT_COVERAGE_INVALID",
            "Duplicate authoritative requirement IDs: "
            + ", ".join(duplicate_requirements),
        )
    if not requirement_rows:
        add(
            "REQUIREMENT_COVERAGE_INVALID",
            "Schema 1.4 requires at least one normative requirement",
        )
    acceptance_ids: list[str] = []
    for row in requirement_rows:
        requirement_id = row[0]
        acceptance_id = row[3]
        if STABLE_CONTRACT_ID.fullmatch(requirement_id) is None:
            add(
                "REQUIREMENT_COVERAGE_INVALID",
                f"Invalid requirement ID {requirement_id!r}",
            )
        expected_acceptance = f"AC-{requirement_id}"
        if (
            ACCEPTANCE_ID.fullmatch(acceptance_id) is None
            or acceptance_id != expected_acceptance
        ):
            add(
                "REQUIREMENT_COVERAGE_INVALID",
                f"{requirement_id}: Acceptance ID must be exactly {expected_acceptance}",
            )
        acceptance_ids.append(acceptance_id)
    duplicate_acceptance = sorted(
        identifier
        for identifier in set(acceptance_ids)
        if acceptance_ids.count(identifier) > 1
    )
    if duplicate_acceptance:
        add(
            "REQUIREMENT_COVERAGE_INVALID",
            "Duplicate acceptance IDs: " + ", ".join(duplicate_acceptance),
        )
    requirement_set = set(requirement_ids)
    change_lineage: RequirementsChangeLineage | None = None
    assumptions: list[AssumptionLifecycleRecord] = []
    if lineage_table is not None:
        if len(lineage_table.rows) != 1:
            add(
                "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                "Requirements change lineage requires exactly one current-revision row",
            )
        else:
            raw = lineage_table.rows[0]
            (
                current,
                prior,
                trigger,
                added,
                changed,
                removed,
                preserved,
                stale,
                revalidate,
            ) = raw
            parsed_lists: dict[str, list[str]] = {}
            for label, value in (
                ("Added IDs", added),
                ("Changed IDs", changed),
                ("Removed IDs", removed),
                ("Preserved IDs", preserved),
            ):
                try:
                    parsed_lists[label] = parse_exact_id_list(
                        value, STABLE_CONTRACT_ID, label
                    )
                except ValueError as exc:
                    add("REQUIREMENTS_CHANGE_LINEAGE_INVALID", str(exc))
                    parsed_lists[label] = []
            if revalidate == "FULL_REVALIDATION":
                revalidation_ids: list[str] = []
            else:
                try:
                    revalidation_ids = parse_exact_id_list(
                        revalidate, STABLE_CONTRACT_ID, "Required revalidation"
                    )
                except ValueError as exc:
                    add("REQUIREMENTS_CHANGE_LINEAGE_INVALID", str(exc))
                    revalidation_ids = []
            expected_revision = clean_cell(
                document.get("Current requirements revision", "")
            )
            if (
                current != expected_revision
                or REQUIREMENTS_REVISION_ID.fullmatch(current) is None
            ):
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Current lineage revision must match Document status",
                )
            if prior != "NONE" and REQUIREMENTS_REVISION_ID.fullmatch(prior) is None:
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Prior revision must be REQ-nnnn or NONE",
                )
            if prior == current:
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Prior and current requirements revisions must differ",
                )
            if not explicit_value(trigger, allow_none=False) or not explicit_value(
                stale, allow_none=True
            ):
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Lineage trigger and stale reason must be explicit",
                )
            classified = [
                identifier
                for label in (
                    "Added IDs",
                    "Changed IDs",
                    "Removed IDs",
                    "Preserved IDs",
                )
                for identifier in parsed_lists[label]
            ]
            duplicates = sorted(
                identifier
                for identifier in set(classified)
                if classified.count(identifier) > 1
            )
            if duplicates:
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Lineage IDs appear in multiple dispositions: "
                    + ", ".join(duplicates),
                )
            current_declared = (
                set(parsed_lists["Added IDs"])
                | set(parsed_lists["Changed IDs"])
                | set(parsed_lists["Preserved IDs"])
            )
            if current_declared != requirement_set:
                add(
                    "REQUIREMENTS_CHANGE_LINEAGE_INVALID",
                    "Added, changed, and preserved IDs must enumerate the current requirement set",
                )
            change_lineage = RequirementsChangeLineage(
                current_revision=current,
                prior_revision=prior,
                trigger=trigger,
                added_ids=tuple(parsed_lists["Added IDs"]),
                changed_ids=tuple(parsed_lists["Changed IDs"]),
                removed_ids=tuple(parsed_lists["Removed IDs"]),
                preserved_ids=tuple(parsed_lists["Preserved IDs"]),
                stale_reason=stale,
                required_revalidation=tuple(revalidation_ids),
            )
    if assumption_table is not None:
        seen_assumptions: set[str] = set()
        for (
            assumption_id,
            statement,
            status,
            basis_value,
            validation,
        ) in assumption_table.rows:
            if (
                ASSUMPTION_ID.fullmatch(assumption_id) is None
                or assumption_id in seen_assumptions
            ):
                add(
                    "ASSUMPTION_LIFECYCLE_INVALID",
                    f"Invalid or duplicate assumption ID {assumption_id!r}",
                )
            seen_assumptions.add(assumption_id)
            if status not in ASSUMPTION_STATUSES:
                add(
                    "ASSUMPTION_LIFECYCLE_INVALID",
                    f"{assumption_id}: invalid assumption status {status!r}",
                )
            if not explicit_value(statement, allow_none=False) or not explicit_value(
                validation, allow_none=False
            ):
                add(
                    "ASSUMPTION_LIFECYCLE_INVALID",
                    f"{assumption_id}: statement and validation/successor must be explicit",
                )
            try:
                basis_ids = parse_exact_id_list(
                    basis_value, STABLE_CONTRACT_ID, f"{assumption_id} Basis IDs"
                )
            except ValueError as exc:
                add("ASSUMPTION_LIFECYCLE_INVALID", str(exc))
                basis_ids = []
            assumptions.append(
                AssumptionLifecycleRecord(
                    assumption_id=assumption_id,
                    assumption=statement,
                    status=status,
                    basis_ids=tuple(basis_ids),
                    validation_or_successor=validation,
                )
            )

    if not required and (
        any(table is None for table in contract_tables)
        or any(
            unresolved(cell)
            for table in contract_tables
            if table
            for row in table.rows
            for cell in row
        )
        or any(unresolved(cell) for row in requirement_rows for cell in row)
    ):
        return RequirementsContract(status="UNINITIALIZED"), []

    actor_ids: list[str] = []
    actor_kinds: dict[str, str] = {}
    if actors is not None:
        if not actors.rows:
            add("ACTOR_CONTRACT_INVALID", "Actor contract has no rows")
        for actor_id, name, kind, outcome, boundary, basis_value in actors.rows:
            if ACTOR_ID.fullmatch(actor_id) is None:
                add("ACTOR_CONTRACT_INVALID", f"Invalid actor ID {actor_id!r}")
                continue
            if actor_id in actor_ids:
                add("ACTOR_CONTRACT_INVALID", f"Duplicate actor ID {actor_id}")
            actor_ids.append(actor_id)
            actor_kinds[actor_id] = kind
            if kind not in ACTOR_KINDS:
                add(
                    "ACTOR_CONTRACT_INVALID", f"{actor_id}: invalid actor kind {kind!r}"
                )
            for label, value in (
                ("Actor or external system", name),
                ("Desired outcome or responsibility", outcome),
                ("Permission/data boundary", boundary),
            ):
                if not explicit_value(value, allow_none=False):
                    add(
                        "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
                        f"{actor_id}: {label} requires an owner-grounded value",
                    )
            try:
                basis_ids = _contract_ids(
                    basis_value,
                    re.compile(r"INTAKE-\d{4}"),
                    f"{actor_id} Intake basis IDs",
                )
                unknown = sorted(set(basis_ids) - confirmed_intake_ids)
                if unknown:
                    add(
                        "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
                        f"{actor_id}: intake basis IDs are not currently confirmed: "
                        + ", ".join(unknown),
                    )
            except ValueError as exc:
                add("ACTOR_CONTRACT_INVALID", str(exc))

    journey_ids: list[str] = []
    journey_requirements: dict[str, set[str]] = {}
    journey_actors: dict[str, set[str]] = {}
    declared_rich_triggers: set[str] = set()
    triggered_journey_ids: set[str] = set()
    if journeys is not None:
        if not journeys.rows:
            add("JOURNEY_CONTRACT_INVALID", "Journey register has no rows")
        for row in journeys.rows:
            (
                journey_id,
                actor_value,
                goal,
                trigger,
                success,
                failure,
                requirement_value,
                trigger_value,
            ) = row
            if JOURNEY_ID.fullmatch(journey_id) is None:
                add("JOURNEY_CONTRACT_INVALID", f"Invalid journey ID {journey_id!r}")
                continue
            if journey_id in journey_ids:
                add("JOURNEY_CONTRACT_INVALID", f"Duplicate journey ID {journey_id}")
            journey_ids.append(journey_id)
            for label, value in (
                ("Goal", goal),
                ("Trigger", trigger),
                ("Main success outcome", success),
                ("Alternate/failure behavior", failure),
            ):
                if not explicit_value(value, allow_none=False):
                    add(
                        "JOURNEY_CONTRACT_INVALID",
                        f"{journey_id}: {label} requires a concrete generated value grounded in approved requirements",
                    )
            try:
                refs = _contract_ids(actor_value, ACTOR_ID, f"{journey_id} Actor IDs")
                journey_actors[journey_id] = set(refs)
                unknown = sorted(set(refs) - set(actor_ids))
                if unknown:
                    add(
                        "JOURNEY_CONTRACT_INVALID",
                        f"{journey_id}: unknown actor IDs: " + ", ".join(unknown),
                    )
            except ValueError as exc:
                add("JOURNEY_CONTRACT_INVALID", str(exc))
            try:
                refs = _contract_ids(
                    requirement_value,
                    STABLE_CONTRACT_ID,
                    f"{journey_id} Requirement IDs",
                )
                journey_requirements[journey_id] = set(refs)
                unknown = sorted(set(refs) - requirement_set)
                if unknown:
                    add(
                        "JOURNEY_CONTRACT_INVALID",
                        f"{journey_id}: unknown requirement IDs: " + ", ".join(unknown),
                    )
            except ValueError as exc:
                add("JOURNEY_CONTRACT_INVALID", str(exc))
            try:
                journey_triggers = _rich_trigger_list(trigger_value, journey_id)
                declared_rich_triggers.update(journey_triggers)
                if journey_triggers:
                    triggered_journey_ids.add(journey_id)
            except ValueError as exc:
                add("JOURNEY_CONTRACT_INVALID", str(exc))

    high_or_critical = effective_risk in {"high", "critical"}
    required_rich_journey_ids = (
        set(journey_ids) if high_or_critical else set(triggered_journey_ids)
    )
    policy_requires_rich = bool(required_rich_journey_ids)
    rich_required = policy_requires_rich
    required_use_case_ids: list[str] = []
    if applicability is not None:
        if len(applicability.rows) != 1:
            add(
                "RICH_USE_CASE_INVALID",
                "Rich-use-case applicability requires exactly one row",
            )
        else:
            status, trigger_basis, use_case_value = applicability.rows[0]
            if status == "REQUIRED":
                rich_required = True
                if not explicit_value(trigger_basis, allow_none=False):
                    add(
                        "RICH_USE_CASE_INVALID",
                        "Rich-use-case trigger basis is unresolved",
                    )
                try:
                    required_use_case_ids = _contract_ids(
                        use_case_value, USE_CASE_ID, "Rich use-case IDs"
                    )
                except ValueError as exc:
                    add("RICH_USE_CASE_INVALID", str(exc))
            elif status == "NOT_APPLICABLE":
                if policy_requires_rich:
                    add(
                        "RICH_USE_CASE_REQUIRED",
                        "High/critical risk or a declared material journey trigger requires rich use cases",
                    )
                if not trigger_basis.startswith("NOT_APPLICABLE") or unresolved(
                    trigger_basis
                ):
                    add(
                        "RICH_USE_CASE_INVALID",
                        "NOT_APPLICABLE requires a concrete trigger-basis reason",
                    )
                if use_case_value != "NONE":
                    add(
                        "RICH_USE_CASE_INVALID",
                        "Non-applicable rich use cases require Use-case IDs NONE",
                    )
            else:
                add(
                    "RICH_USE_CASE_INVALID",
                    "Applicability must be REQUIRED or NOT_APPLICABLE",
                )

    if not rich_required:
        if use_cases is not None and use_cases.rows:
            add(
                "RICH_USE_CASE_INVALID",
                "NOT_APPLICABLE rich use cases require an empty rich-use-case table",
            )
        if business_rules is not None and business_rules.rows:
            add(
                "BUSINESS_RULE_INVALID",
                "NOT_APPLICABLE rich use cases require an empty business-rule table",
            )

    use_case_ids: list[str] = []
    use_case_journey_ids: set[str] = set()
    referenced_business_rules: set[str] = set()
    if use_cases is not None and rich_required:
        for row in use_cases.rows:
            (
                use_case_id,
                journey_id,
                primary_actor,
                interests,
                preconditions,
                success,
                minimum_failure,
                rules_value,
                requirements_value,
            ) = row
            if USE_CASE_ID.fullmatch(use_case_id) is None:
                add("RICH_USE_CASE_INVALID", f"Invalid use-case ID {use_case_id!r}")
                continue
            if use_case_id in use_case_ids:
                add("RICH_USE_CASE_INVALID", f"Duplicate use-case ID {use_case_id}")
            use_case_ids.append(use_case_id)
            if journey_id not in journey_ids:
                add(
                    "RICH_USE_CASE_INVALID",
                    f"{use_case_id}: unknown journey {journey_id}",
                )
            else:
                use_case_journey_ids.add(journey_id)
            if primary_actor not in journey_actors.get(journey_id, set()):
                add(
                    "RICH_USE_CASE_INVALID",
                    f"{use_case_id}: primary actor is not part of {journey_id}",
                )
            for label, value in (
                ("Stakeholder interests", interests),
                ("Preconditions", preconditions),
                ("Success guarantee", success),
                ("Minimum failure guarantee", minimum_failure),
            ):
                if not explicit_value(value, allow_none=False):
                    add(
                        "RICH_USE_CASE_INVALID",
                        f"{use_case_id}: {label} must be concrete",
                    )
            try:
                referenced_business_rules.update(
                    _contract_ids(
                        rules_value,
                        BUSINESS_RULE_ID,
                        f"{use_case_id} Business rule IDs",
                    )
                )
            except ValueError as exc:
                add("RICH_USE_CASE_INVALID", str(exc))
            try:
                refs = set(
                    _contract_ids(
                        requirements_value,
                        STABLE_CONTRACT_ID,
                        f"{use_case_id} Requirement IDs",
                    )
                )
                unknown = sorted(refs - requirement_set)
                if unknown:
                    add(
                        "RICH_USE_CASE_INVALID",
                        f"{use_case_id}: unknown requirement IDs: "
                        + ", ".join(unknown),
                    )
                journey_basis = journey_requirements.get(journey_id, set())
                outside_journey = sorted(refs - journey_basis)
                if outside_journey:
                    add(
                        "RICH_USE_CASE_INVALID",
                        f"{use_case_id}: requirement IDs are not part of {journey_id}: "
                        + ", ".join(outside_journey),
                    )
            except ValueError as exc:
                add("RICH_USE_CASE_INVALID", str(exc))
        if use_case_ids != required_use_case_ids:
            add(
                "RICH_USE_CASE_INVALID",
                "Rich use-case rows must exactly match the applicability record",
            )

    missing_rich_journey_ids = sorted(required_rich_journey_ids - use_case_journey_ids)
    if missing_rich_journey_ids:
        scope = (
            "every journey at high/critical risk"
            if high_or_critical
            else "every journey declaring a material rich-use-case trigger"
        )
        add(
            "RICH_USE_CASE_REQUIRED",
            f"Rich use cases must cover {scope}; missing="
            + ",".join(missing_rich_journey_ids),
        )

    business_rule_ids: list[str] = []
    if business_rules is not None and rich_required:
        for (
            rule_id,
            rule,
            basis_value,
            journey_use_case_value,
            validation_id,
        ) in business_rules.rows:
            if BUSINESS_RULE_ID.fullmatch(rule_id) is None:
                add("BUSINESS_RULE_INVALID", f"Invalid business-rule ID {rule_id!r}")
                continue
            if rule_id in business_rule_ids:
                add("BUSINESS_RULE_INVALID", f"Duplicate business-rule ID {rule_id}")
            business_rule_ids.append(rule_id)
            if not explicit_value(rule, allow_none=False):
                add("BUSINESS_RULE_INVALID", f"{rule_id}: Rule must be concrete")
            try:
                basis_refs = set(
                    _contract_ids(
                        basis_value, STABLE_CONTRACT_ID, f"{rule_id} Basis IDs"
                    )
                )
                refs = set(
                    _contract_ids(
                        journey_use_case_value,
                        STABLE_CONTRACT_ID,
                        f"{rule_id} Journey/use-case IDs",
                    )
                )
                unknown = sorted(refs - set(journey_ids) - set(use_case_ids))
                if unknown:
                    add(
                        "BUSINESS_RULE_INVALID",
                        f"{rule_id}: unknown journey/use-case IDs: "
                        + ", ".join(unknown),
                    )
                allowed_basis = (
                    requirement_set
                    | confirmed_intake_ids
                    | set(journey_ids)
                    | set(use_case_ids)
                )
                unknown_basis = sorted(basis_refs - allowed_basis)
                if unknown_basis:
                    add(
                        "BUSINESS_RULE_INVALID",
                        f"{rule_id}: unknown basis IDs: " + ", ".join(unknown_basis),
                    )
            except ValueError as exc:
                add("BUSINESS_RULE_INVALID", str(exc))
            if validation_id not in set(acceptance_ids):
                add(
                    "BUSINESS_RULE_INVALID",
                    f"{rule_id}: Validation ID must reference a current acceptance ID",
                )
        missing_rules = sorted(referenced_business_rules - set(business_rule_ids))
        extra_rules = sorted(set(business_rule_ids) - referenced_business_rules)
        if missing_rules or extra_rules:
            add(
                "BUSINESS_RULE_INVALID",
                "Business-rule rows must exactly match rich-use-case references; missing="
                + ",".join(missing_rules)
                + "; extra="
                + ",".join(extra_rules),
            )

    covered_requirements: list[str] = []
    covered_actor_ids: set[str] = set()
    covered_journey_ids: set[str] = set()
    if coverage is not None:
        for (
            requirement_id,
            intake_value,
            actor_value,
            journey_value,
            acceptance_value,
            success_measure,
        ) in coverage.rows:
            if requirement_id in covered_requirements:
                add(
                    "REQUIREMENT_COVERAGE_INVALID",
                    f"Duplicate coverage row for {requirement_id}",
                )
            covered_requirements.append(requirement_id)
            if requirement_id not in requirement_set:
                add(
                    "REQUIREMENT_COVERAGE_INVALID",
                    f"Coverage references unknown requirement {requirement_id}",
                )
            intake_refs: set[str] = set()
            actor_refs: set[str] = set()
            journey_refs: set[str] = set()
            acceptance_refs: list[str] = []
            try:
                intake_refs = set(
                    _contract_ids(
                        intake_value,
                        re.compile(r"INTAKE-\d{4}"),
                        f"{requirement_id} Intake basis IDs",
                    )
                )
                actor_refs = set(
                    _contract_ids(actor_value, ACTOR_ID, f"{requirement_id} Actor IDs")
                )
                journey_refs = set(
                    _contract_ids(
                        journey_value, JOURNEY_ID, f"{requirement_id} Journey IDs"
                    )
                )
                acceptance_refs = _contract_ids(
                    acceptance_value,
                    STABLE_CONTRACT_ID,
                    f"{requirement_id} Acceptance/test IDs",
                )
                if not intake_refs <= confirmed_intake_ids:
                    add(
                        "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
                        f"{requirement_id}: coverage cites intake basis IDs that are not currently confirmed",
                    )
                if not actor_refs <= set(actor_ids):
                    add(
                        "REQUIREMENT_COVERAGE_INVALID",
                        f"{requirement_id}: unknown actor IDs",
                    )
                if not journey_refs <= set(journey_ids):
                    add(
                        "REQUIREMENT_COVERAGE_INVALID",
                        f"{requirement_id}: unknown journey IDs",
                    )
                expected_acceptance = acceptance_by_requirement.get(requirement_id)
                requirement_row = requirement_row_by_id.get(requirement_id)
                if expected_acceptance is not None and requirement_row is not None:
                    criterion_bindings = list(
                        dict.fromkeys(
                            ACCEPTANCE_TEST_BINDING_ID.findall(requirement_row[4])
                        )
                    )
                    expected_refs = [expected_acceptance, *criterion_bindings]
                else:
                    expected_refs = []
                if acceptance_refs != expected_refs:
                    add(
                        "REQUIREMENT_COVERAGE_INVALID",
                        f"{requirement_id}: Acceptance/test IDs must exactly match "
                        "the canonical acceptance ID followed by test IDs explicitly "
                        "bound in that requirement's acceptance criterion; expected="
                        + ",".join(expected_refs),
                    )
                if requirement_id in requirement_set:
                    covered_actor_ids.update(actor_refs)
                    covered_journey_ids.update(journey_refs)
                if any(
                    requirement_id not in journey_requirements.get(item, set())
                    for item in journey_refs
                ):
                    add(
                        "REQUIREMENT_COVERAGE_INVALID",
                        f"{requirement_id}: cited journey does not include the requirement",
                    )
                journey_actor_union = set().union(
                    *(journey_actors.get(item, set()) for item in journey_refs)
                )
                if not actor_refs <= journey_actor_union:
                    add(
                        "REQUIREMENT_COVERAGE_INVALID",
                        f"{requirement_id}: every coverage actor must participate in a cited journey",
                    )
            except ValueError as exc:
                add("REQUIREMENT_COVERAGE_INVALID", str(exc))
            if (
                success_measure != "INTAKE-0006"
                or "INTAKE-0006" not in confirmed_intake_ids
            ):
                add(
                    "REQUIREMENT_COVERAGE_INVALID",
                    f"{requirement_id}: Approved success measure ID must be INTAKE-0006",
                )
        if covered_requirements != sorted(requirement_set):
            missing = sorted(requirement_set - set(covered_requirements))
            extra = sorted(set(covered_requirements) - requirement_set)
            add(
                "REQUIREMENT_COVERAGE_INVALID",
                "Coverage must enumerate every requirement exactly once in sorted order; missing="
                + ",".join(missing)
                + "; extra="
                + ",".join(extra),
            )
        uncovered_actor_ids = sorted(set(actor_ids) - covered_actor_ids)
        if uncovered_actor_ids:
            add(
                "ACTOR_CONTRACT_INVALID",
                "Every declared actor must participate in first-release requirement "
                "coverage; uncovered=" + ",".join(uncovered_actor_ids),
            )
        uncovered_journey_ids = sorted(set(journey_ids) - covered_journey_ids)
        if uncovered_journey_ids:
            add(
                "JOURNEY_CONTRACT_INVALID",
                "Every declared journey must participate in first-release requirement "
                "coverage; uncovered=" + ",".join(uncovered_journey_ids),
            )

    canonical_bytes: bytes | None = None
    canonical_sha256: str | None = None
    if all(table is not None for table in contract_tables):
        requirement_payload = (
            json.dumps(
                requirement_rows, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            + b"\n"
        )
        canonical_bytes = (
            ("1.3" if grandfather_schema_13 else PROJECT_CONTRACT_SCHEMA).encode(
                "utf-8"
            )
            + b"\n"
            + requirement_payload
            + b"".join(
                table.canonical_bytes for table in contract_tables if table is not None
            )
        )
        canonical_sha256 = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
    return (
        RequirementsContract(
            schema_version="1.3" if grandfather_schema_13 else PROJECT_CONTRACT_SCHEMA,
            status=(
                "GRANDFATHERED"
                if grandfather_schema_13 and not issues
                else "READY"
                if not issues
                else "BLOCKED"
            ),
            actor_ids=tuple(actor_ids),
            journey_ids=tuple(journey_ids),
            acceptance_ids=tuple(
                acceptance_by_requirement.get(item, "")
                for item in sorted(requirement_set)
            ),
            use_case_ids=tuple(use_case_ids),
            business_rule_ids=tuple(business_rule_ids),
            requirement_ids=tuple(sorted(requirement_set)),
            rich_use_case_triggers=tuple(sorted(declared_rich_triggers)),
            change_lineage=change_lineage,
            assumptions=tuple(assumptions),
            missing_records=tuple(dict.fromkeys(missing_records)),
            canonical_sha256=canonical_sha256,
            grandfathered_approved_gate_a=grandfather_schema_13,
            canonical_bytes=canonical_bytes,
        ),
        issues,
    )


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
    for field_name in (
        "Current requirements revision",
        "Current design revision",
        "Current construction authorization ID",
    ):
        value = clean_cell(document.get(field_name, ""))
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
    if not identifiers or any(
        PROPERTY_ID.fullmatch(item) is None for item in identifiers
    ):
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


def derive_example_scenario_contract(
    text: str,
) -> tuple[ContractTable | None, set[str], list[str]]:
    """Parse the authoritative example-scenario declarations."""

    issues: list[str] = []
    try:
        table = contract_table_after_heading(
            text, EXAMPLE_SCENARIO_HEADING, EXAMPLE_SCENARIO_HEADERS
        )
    except ValueError as exc:
        return None, set(), [f"{EXAMPLE_SCENARIO_HEADING}: {exc}"]
    if table is None:
        return None, set(), [f"Missing {EXAMPLE_SCENARIO_HEADING}"]
    if not table.rows:
        issues.append("Example-based scenarios has no stored rows")
    identifiers: set[str] = set()
    for test_id, scenario, expected_result, layer in table.rows:
        if EXAMPLE_SCENARIO_ID.fullmatch(test_id) is None:
            issues.append(f"Invalid example scenario ID {test_id!r}")
        elif test_id in identifiers:
            issues.append(f"Duplicate example scenario ID {test_id}")
        identifiers.add(test_id)
        if not explicit_value(scenario, allow_none=False):
            issues.append(f"{test_id}: Scenario must be concrete")
        if not explicit_value(expected_result, allow_none=False):
            issues.append(f"{test_id}: Expected result must be concrete")
        if layer not in HARNESS_LAYERS:
            issues.append(f"{test_id}: invalid Harness layer {layer!r}")
    return table, identifiers, issues


def _support_value_is_concrete(value: str) -> bool:
    cleaned = clean_cell(value)
    return (
        explicit_value(cleaned, allow_none=False)
        and EVIDENCE_PLACEHOLDER_PATTERN.search(cleaned) is None
    )


def _not_applicable_reason(value: str) -> str | None:
    match = re.fullmatch(r"NOT_APPLICABLE (?:\u2014|-) (.+)", clean_cell(value))
    if match is None or not _support_value_is_concrete(match.group(1)):
        return None
    return match.group(1)


def design_support_record_issues(
    text: str,
    technology_by_id: Mapping[str, TechnologyDecision],
) -> list[str]:
    """Validate design support records that block modern Gate B readiness."""

    issues: list[str] = []
    try:
        error_table = contract_table_after_heading(
            text, ERROR_HANDLING_HEADING, ERROR_HANDLING_HEADERS
        )
    except ValueError as exc:
        error_table = None
        issues.append(f"Error handling contract: {exc}")
    if error_table is None:
        issues.append(f"Missing {ERROR_HANDLING_HEADING}")
    else:
        counts: dict[str, int] = {}
        for row in error_table.rows:
            error_class, _example, retry, *_remainder = row
            counts[error_class] = counts.get(error_class, 0) + 1
            if any(not _support_value_is_concrete(cell) for cell in row):
                issues.append(
                    f"{error_class or 'Error handling row'}: every error-handling "
                    "field must be concrete"
                )
            retry_value = clean_cell(retry)
            if not re.search(
                r"\b(?:no|bounded|fresh state|max(?:imum)?)\b", retry_value, re.I
            ):
                issues.append(
                    f"{error_class or 'Error handling row'}: retry posture must "
                    "explicitly deny or bound retry"
                )
            if re.search(r"\b(?:unbounded|unlimited|forever)\b", retry_value, re.I):
                issues.append(
                    f"{error_class or 'Error handling row'}: retry posture is unbounded"
                )
        for error_class in REQUIRED_ERROR_CLASSES:
            count = counts.get(error_class, 0)
            if count != 1:
                issues.append(
                    f"Error class {error_class} must appear exactly once; found {count}"
                )
        unexpected = sorted(set(counts) - set(REQUIRED_ERROR_CLASSES))
        if unexpected:
            issues.append("Unexpected error classes: " + ", ".join(unexpected))

    try:
        aws_table = contract_table_after_heading(
            text, AWS_SERVICE_DECISION_HEADING, AWS_SERVICE_DECISION_HEADERS
        )
    except ValueError as exc:
        aws_table = None
        issues.append(f"AWS service decision contract: {exc}")
    if aws_table is None:
        issues.append(f"Missing {AWS_SERVICE_DECISION_HEADING}")
    else:
        counts: dict[str, int] = {}
        for concern, decision_ids, mechanism, rationale, tradeoff in aws_table.rows:
            counts[concern] = counts.get(concern, 0) + 1
            for label, value in (
                ("AWS service or mechanism", mechanism),
                ("Rationale", rationale),
                ("Tradeoff", tradeoff),
            ):
                if not _support_value_is_concrete(value):
                    issues.append(
                        f"{concern or 'AWS decision row'}: {label} is unresolved"
                    )
            try:
                identifiers = _canonical_id_list(
                    decision_ids,
                    TECHNOLOGY_DECISION_ID,
                    f"{concern} AWS decision IDs",
                )
            except ValueError as exc:
                issues.append(str(exc))
                identifiers = []
            decisions = [technology_by_id.get(identifier) for identifier in identifiers]
            unknown = [
                identifier
                for identifier, decision in zip(identifiers, decisions)
                if decision is None
            ]
            if unknown:
                issues.append(
                    f"{concern}: AWS decision IDs are not current technology IDs: "
                    + ", ".join(unknown)
                )
            allowed_concerns = AWS_SERVICE_TECH_CONCERNS.get(concern, set())
            if decisions and not any(
                decision is not None and decision.concern in allowed_concerns
                for decision in decisions
            ):
                issues.append(
                    f"{concern}: AWS decision IDs do not bind the relevant "
                    "technology concern"
                )
        for concern in AWS_SERVICE_TECH_CONCERNS:
            count = counts.get(concern, 0)
            if count != 1:
                issues.append(
                    f"AWS concern {concern} must appear exactly once; found {count}"
                )
        unexpected = sorted(set(counts) - set(AWS_SERVICE_TECH_CONCERNS))
        if unexpected:
            issues.append("Unexpected AWS decision concerns: " + ", ".join(unexpected))

    try:
        iac_table = contract_table_after_heading(
            text, IAC_VALIDATION_HEADING, IAC_VALIDATION_HEADERS
        )
    except ValueError as exc:
        iac_table = None
        issues.append(f"IaC and delivery validation contract: {exc}")
    if iac_table is None:
        issues.append(f"Missing {IAC_VALIDATION_HEADING}")
    else:
        counts: dict[str, int] = {}
        for row in iac_table.rows:
            (
                path,
                applicability,
                tech_binding,
                local_check,
                planning_check,
                destination,
            ) = row
            counts[path] = counts.get(path, 0) + 1
            for label, value in (
                ("TECH binding", tech_binding),
                ("Required local/static validation", local_check),
                ("AWS planning validation", planning_check),
            ):
                if not _support_value_is_concrete(value):
                    issues.append(
                        f"{path or 'IaC validation row'}: {label} is unresolved"
                    )
            if destination != IAC_VALIDATION_EVIDENCE_DESTINATION:
                issues.append(
                    f"{path}: Evidence destination must be exactly "
                    f"{IAC_VALIDATION_EVIDENCE_DESTINATION}"
                )
            if applicability == "APPLICABLE":
                try:
                    identifiers = _canonical_id_list(
                        tech_binding,
                        TECHNOLOGY_DECISION_ID,
                        f"{path} TECH binding",
                    )
                except ValueError as exc:
                    issues.append(str(exc))
                    identifiers = []
                decisions = [
                    technology_by_id.get(identifier) for identifier in identifiers
                ]
                unknown = [
                    identifier
                    for identifier, decision in zip(identifiers, decisions)
                    if decision is None
                ]
                if unknown:
                    issues.append(
                        f"{path}: TECH binding references unknown IDs: "
                        + ", ".join(unknown)
                    )
                invalid_concerns = sorted(
                    {
                        decision.concern
                        for decision in decisions
                        if decision is not None
                        and decision.concern not in IAC_VALIDATION_TECH_CONCERNS
                    }
                )
                if invalid_concerns:
                    issues.append(
                        f"{path}: TECH binding uses unrelated concerns: "
                        + ", ".join(invalid_concerns)
                    )
                if decisions and not any(
                    decision is not None
                    and decision.concern
                    in {"INFRASTRUCTURE_AS_CODE", "DEPLOYMENT_TOOLING"}
                    for decision in decisions
                ):
                    issues.append(
                        f"{path}: TECH binding needs an infrastructure or deployment decision"
                    )
                for decision in decisions:
                    if decision is not None and technology_value_is_not_applicable(
                        decision.selection
                    ):
                        issues.append(
                            f"{path}: applicable validation cannot bind non-applicable "
                            f"technology decision {decision.decision_id}"
                        )
            elif _not_applicable_reason(applicability) is None:
                issues.append(
                    f"{path}: Applicability must be APPLICABLE or "
                    "NOT_APPLICABLE - <concrete reason>"
                )
        for path in IAC_VALIDATION_PATHS:
            count = counts.get(path, 0)
            if count != 1:
                issues.append(
                    f"IaC validation path {path} must appear exactly once; found {count}"
                )
        unexpected = sorted(set(counts) - set(IAC_VALIDATION_PATHS))
        if unexpected:
            issues.append("Unexpected IaC validation paths: " + ", ".join(unexpected))
    return issues


def architecture_trace_declaration_issues(
    architecture: ArchitectureContract,
    project_contract: ProjectDesignContract,
    declared_property_test_ids: set[str],
) -> list[str]:
    """Require every architecture trace ID to resolve to a current declaration."""

    declared_design_ids = set(project_contract.interface_ids)
    declared_design_ids.update(project_contract.boundary_ids)
    declared_design_ids.update(project_contract.state_ids)
    if architecture.selection is not None:
        declared_design_ids.add(architecture.selection.architecture_id)

    issues: list[str] = []
    for trace in architecture.traceability:
        try:
            design_ids = _canonical_id_list(
                trace.design_ids,
                ARCHITECTURE_DESIGN_ID,
                f"{trace.requirement_id} architecture traceability design IDs",
            )
        except ValueError:
            pass
        else:
            undeclared_design_ids = sorted(set(design_ids) - declared_design_ids)
            if undeclared_design_ids:
                issues.append(
                    f"{trace.requirement_id}: architecture traceability references "
                    "undeclared design IDs: " + ", ".join(undeclared_design_ids)
                )

        if _none_with_reason(trace.property_test_ids):
            continue
        try:
            property_test_ids = _canonical_id_list(
                trace.property_test_ids,
                ARCHITECTURE_TEST_ID,
                f"{trace.requirement_id} property/test IDs",
            )
        except ValueError:
            continue
        undeclared_property_test_ids = sorted(
            set(property_test_ids) - declared_property_test_ids
        )
        if undeclared_property_test_ids:
            issues.append(
                f"{trace.requirement_id}: architecture traceability references "
                "undeclared property/test IDs: "
                + ", ".join(undeclared_property_test_ids)
            )
    return issues


def _intake_required_detail(value: str, kind: str) -> tuple[str, ...]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return ()
    if kind == "FACT":
        if cleaned != "RESPONSE":
            raise ValueError("FACT questions require detail for RESPONSE")
        return ("RESPONSE",)
    if cleaned == "RESPONSE":
        raise ValueError("DECISION questions require detail for A, B, or C")
    keys = [item.strip() for item in cleaned.split(",")]
    if (
        not keys
        or any(key not in {"A", "B", "C"} for key in keys)
        or len(keys) != len(set(keys))
        or cleaned != ", ".join(keys)
    ):
        raise ValueError(
            "Required detail for must be NONE or comma-space-separated A/B/C keys"
        )
    return tuple(keys)


def _intake_owner_reply_example(questions: list[IntakeQuestion]) -> str:
    replies: list[str] = []
    for question in questions:
        if question.kind == "FACT":
            replies.append(f"{question.reply_key}: <your answer>")
            continue
        if question.recommended is None:
            replies.append(f"{question.reply_key}: <choose A, B, or C>")
            continue
        choice = question.recommended
        reply = f"{question.reply_key}{choice}"
        if choice in question.required_detail_for:
            reply += ": <required detail>"
        replies.append(reply)
    return "; ".join(replies)


def _intake_reply_example(questions: list[IntakeQuestion], reply_token: str) -> str:
    """Return the internal legacy token-bound reply for 1.0.x consumers."""

    return reply_token + "; " + _intake_owner_reply_example(questions)


def _parse_intake_response_register(
    table: ContractTable,
    expected_foundation_rows: Mapping[str, str],
    issues: list[tuple[str, str]],
) -> tuple[NormalizedOwnerResponse, ...]:
    responses: list[NormalizedOwnerResponse] = []
    seen_question_rows: set[tuple[str, str]] = set()
    seen_reply_rows: set[tuple[str, str]] = set()
    seen_presented_questions: set[tuple[str, int, str]] = set()
    message_identities: dict[str, tuple[str, int, str]] = {}
    response_numbers: set[int] = set()
    for raw in table.rows:
        (
            owner_response_id,
            card_id,
            revision_text,
            presented_card_digest,
            reply_key,
            question_id,
            selection,
            selection_detail,
            basis_value,
        ) = raw
        valid = True
        if OWNER_RESPONSE_ID.fullmatch(owner_response_id) is None:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"Invalid owner response ID {owner_response_id!r}",
                )
            )
            valid = False
        else:
            response_numbers.add(int(owner_response_id.rsplit("-", 1)[1]))
        if INTAKE_CARD_ID.fullmatch(card_id) is None:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid card ID",
                )
            )
            valid = False
        try:
            revision = int(revision_text)
            if revision < 1 or str(revision) != revision_text:
                raise ValueError
        except ValueError:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid revision",
                )
            )
            revision = 0
            valid = False
        if re.fullmatch(r"sha256:[0-9a-f]{64}", presented_card_digest) is None:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid presented-card digest",
                )
            )
            valid = False
        if reply_key not in {"1", "2", "3"}:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid reply key",
                )
            )
            valid = False
        if INTAKE_QUESTION_ID.fullmatch(question_id) is None:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid question ID",
                )
            )
            valid = False
        if selection not in {"A", "B", "C", "RESPONSE"}:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid selection",
                )
            )
            valid = False
        if selection_detail != "NONE" and not explicit_value(
            selection_detail, allow_none=False
        ):
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has unresolved selection detail",
                )
            )
            valid = False
        detail_safety = (
            None
            if selection_detail == "NONE"
            else intake_detail_safety_code(selection_detail)
        )
        if detail_safety is not None:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has unsafe or placeholder selection detail",
                )
            )
            valid = False
        if selection == "RESPONSE" and (
            selection_detail == "NONE" or detail_safety is not None
        ):
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} requires concrete factual detail",
                )
            )
            valid = False
        try:
            basis_ids = tuple(
                _canonical_id_list(
                    basis_value, INTAKE_ID, f"{owner_response_id} Basis IDs"
                )
            )
            if not set(basis_ids).issubset(expected_foundation_rows):
                raise ValueError("Basis IDs must cite canonical intake foundation rows")
        except ValueError as exc:
            issues.append(
                ("INTAKE_RESPONSE_REGISTER_INVALID", f"{owner_response_id}: {exc}")
            )
            basis_ids = ()
            valid = False
        question_key = (owner_response_id, question_id)
        reply_key_pair = (owner_response_id, reply_key)
        if question_key in seen_question_rows or reply_key_pair in seen_reply_rows:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has a duplicate normalized answer",
                )
            )
            valid = False
        seen_question_rows.add(question_key)
        seen_reply_rows.add(reply_key_pair)
        presented_question = (card_id, revision, question_id)
        if presented_question in seen_presented_questions:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} repeats an answer to one presented question",
                )
            )
            valid = False
        seen_presented_questions.add(presented_question)
        identity = (card_id, revision, presented_card_digest)
        if (
            owner_response_id in message_identities
            and message_identities[owner_response_id] != identity
        ):
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} mixes card identities",
                )
            )
            valid = False
        message_identities[owner_response_id] = identity
        if valid:
            responses.append(
                NormalizedOwnerResponse(
                    owner_response_id=owner_response_id,
                    card_id=card_id,
                    revision=revision,
                    presented_card_digest=presented_card_digest,
                    reply_key=reply_key,
                    question_id=question_id,
                    selection=selection,
                    selection_detail=None
                    if selection_detail == "NONE"
                    else selection_detail,
                    basis_ids=basis_ids,
                )
            )
    if response_numbers and sorted(response_numbers) != list(
        range(1, max(response_numbers) + 1)
    ):
        issues.append(
            (
                "INTAKE_RESPONSE_REGISTER_INVALID",
                "Owner response IDs must be monotonic without gaps",
            )
        )
    return tuple(responses)


def derive_intake_foundation_contract(
    text: str,
    repository_mode: str | None,
    *,
    grandfather_current_gate_a: bool,
) -> tuple[IntakeFoundationContract, list[tuple[str, str]]]:
    """Derive owner-grounded intake state without treating recommendations as facts."""

    issues: list[tuple[str, str]] = []
    normalized_repository_mode = (
        repository_mode.strip().lower() if isinstance(repository_mode, str) else None
    )
    repository_mode_value = (
        normalized_repository_mode.upper()
        if normalized_repository_mode in PROJECT_MODES
        else None
    )
    try:
        foundation_table = contract_table_after_heading(
            text, INTAKE_FOUNDATION_HEADING, INTAKE_FOUNDATION_HEADERS
        )
        response_table = contract_table_after_heading(
            text, INTAKE_RESPONSE_REGISTER_HEADING, INTAKE_RESPONSE_REGISTER_HEADERS
        )
        card_table = contract_table_after_heading(
            text, INTAKE_CARD_HEADING, INTAKE_CARD_HEADERS
        )
    except ValueError as exc:
        try:
            legacy_foundation = contract_table_after_heading(
                text, INTAKE_FOUNDATION_HEADING, LEGACY_INTAKE_FOUNDATION_HEADERS
            )
            legacy_card = contract_table_after_heading(
                text, INTAKE_CARD_HEADING, INTAKE_CARD_HEADERS
            )
            legacy_response = contract_table_after_heading(
                text,
                INTAKE_RESPONSE_REGISTER_HEADING,
                INTAKE_RESPONSE_REGISTER_HEADERS,
            )
        except ValueError:
            legacy_foundation = legacy_card = legacy_response = None
        if (
            legacy_foundation is not None
            and legacy_card is not None
            and legacy_response is None
        ):
            if grandfather_current_gate_a:
                return (
                    IntakeFoundationContract(
                        status="READY_FOR_REQUIREMENTS",
                        repository_mode=repository_mode_value,
                        grandfathered_approved_gate_a=True,
                    ),
                    [],
                )
            return (
                IntakeFoundationContract(
                    status="FOUNDATION_REQUIRED",
                    repository_mode=repository_mode_value,
                    missing_fields=tuple(
                        field for _identifier, field in INTAKE_FOUNDATION_FIELDS
                    ),
                ),
                [
                    (
                        "INTAKE_CONTRACT_MIGRATION_REQUIRED",
                        "Unapproved legacy intake requires owner-response provenance and the normalized response register; retain legacy values only as unconfirmed context, reopen affected facts, and present the smallest current owner card without synthesizing historical OWNER-MSG records",
                    )
                ],
            )
        return (
            IntakeFoundationContract(
                status="BLOCKED",
                repository_mode=repository_mode_value,
            ),
            [("INTAKE_FOUNDATION_INVALID", str(exc))],
        )

    if foundation_table is None and response_table is None and card_table is None:
        if grandfather_current_gate_a:
            return (
                IntakeFoundationContract(
                    status="READY_FOR_REQUIREMENTS",
                    repository_mode=repository_mode_value,
                    grandfathered_approved_gate_a=True,
                ),
                [],
            )
        return (
            IntakeFoundationContract(
                status="FOUNDATION_REQUIRED",
                repository_mode=repository_mode_value,
                missing_fields=tuple(
                    field for _identifier, field in INTAKE_FOUNDATION_FIELDS
                ),
            ),
            [
                (
                    "INTAKE_CONTRACT_MIGRATION_REQUIRED",
                    "Unapproved initialized projects require the intake foundation, normalized response register, and current decision card",
                )
            ],
        )
    if foundation_table is None or response_table is None or card_table is None:
        missing_records = ", ".join(
            name
            for name, table in (
                ("intake foundation", foundation_table),
                ("normalized response register", response_table),
                ("current decision card", card_table),
            )
            if table is None
        )
        return (
            IntakeFoundationContract(
                status="FOUNDATION_REQUIRED",
                repository_mode=repository_mode_value,
                missing_fields=tuple(
                    field for _identifier, field in INTAKE_FOUNDATION_FIELDS
                ),
            ),
            [
                (
                    "INTAKE_CONTRACT_MIGRATION_REQUIRED",
                    "Unapproved project is missing: " + missing_records,
                )
            ],
        )

    expected_rows = dict(INTAKE_FOUNDATION_FIELDS)
    normalized_responses = _parse_intake_response_register(
        response_table, expected_rows, issues
    )
    responses_by_provenance = {
        response.provenance: response for response in normalized_responses
    }
    observed_rows: dict[str, tuple[str, str, str, str]] = {}
    for (
        intake_id,
        field_name,
        value,
        basis,
        status,
        owner_response,
    ) in foundation_table.rows:
        if intake_id in observed_rows:
            issues.append(
                ("INTAKE_FOUNDATION_INVALID", f"Duplicate intake ID {intake_id}")
            )
            continue
        if INTAKE_ID.fullmatch(intake_id) is None:
            issues.append(
                ("INTAKE_FOUNDATION_INVALID", f"Invalid intake ID {intake_id!r}")
            )
        if expected_rows.get(intake_id) != field_name:
            issues.append(
                (
                    "INTAKE_FOUNDATION_INVALID",
                    f"{intake_id} must define {expected_rows.get(intake_id)!r}",
                )
            )
        if basis not in INTAKE_BASES:
            issues.append(
                (
                    "INTAKE_FOUNDATION_INVALID",
                    f"{intake_id} has invalid basis {basis!r}",
                )
            )
        if status not in {"OPEN", "CONFIRMED"}:
            issues.append(
                (
                    "INTAKE_FOUNDATION_INVALID",
                    f"{intake_id} has invalid status {status!r}",
                )
            )
        if status == "CONFIRMED":
            if not explicit_value(value, allow_none=False):
                issues.append(
                    (
                        "INTAKE_FOUNDATION_INVALID",
                        f"{intake_id} has no concrete owner value",
                    )
                )
            normalized_response = responses_by_provenance.get(owner_response)
            if (
                normalized_response is None
                or intake_id not in normalized_response.basis_ids
            ):
                issues.append(
                    (
                        "INTAKE_FOUNDATION_PROVENANCE_INVALID",
                        f"{intake_id} is not bound to one normalized owner response that cites it",
                    )
                )
            if field_name == "OWNER_WORK_CONTEXT" and normalized_response is not None:
                expected_context = OWNER_WORK_CONTEXT_SELECTIONS.get(
                    normalized_response.selection
                )
                if expected_context is None or value != expected_context:
                    issues.append(
                        (
                            "INTAKE_FOUNDATION_PROVENANCE_INVALID",
                            "OWNER_WORK_CONTEXT must map A/B/C to NEW_APPLICATION/EXISTING_APPLICATION_CHANGE/REPAIR_OR_MIGRATION",
                        )
                    )
            if basis != "OWNER_FACT":
                issues.append(
                    (
                        "INTAKE_FOUNDATION_INVALID",
                        f"{intake_id} can be confirmed only with OWNER_FACT provenance",
                    )
                )
            if field_name == "OWNER_WORK_CONTEXT" and value not in OWNER_WORK_CONTEXTS:
                issues.append(
                    (
                        "INTAKE_FOUNDATION_INVALID",
                        "OWNER_WORK_CONTEXT must be NEW_APPLICATION, "
                        "EXISTING_APPLICATION_CHANGE, or REPAIR_OR_MIGRATION",
                    )
                )
        else:
            if basis == "OWNER_FACT":
                issues.append(
                    (
                        "INTAKE_FOUNDATION_INVALID",
                        f"{intake_id} cannot remain OPEN with OWNER_FACT provenance",
                    )
                )
            if owner_response != "NONE":
                issues.append(
                    (
                        "INTAKE_FOUNDATION_PROVENANCE_INVALID",
                        f"{intake_id} is OPEN but cites an owner response",
                    )
                )
        observed_rows[intake_id] = (field_name, value, status, owner_response)

    if (
        tuple((identifier, row[0]) for identifier, row in observed_rows.items())
        != INTAKE_FOUNDATION_FIELDS
    ):
        issues.append(
            (
                "INTAKE_FOUNDATION_INVALID",
                "Intake foundation rows and order must match the ten canonical INTAKE IDs",
            )
        )

    missing_fields = tuple(
        field_name
        for intake_id, field_name in INTAKE_FOUNDATION_FIELDS
        if observed_rows.get(intake_id, ("", "", "OPEN"))[2] != "CONFIRMED"
    )
    basis_ids = tuple(
        intake_id
        for intake_id, _field_name in INTAKE_FOUNDATION_FIELDS
        if observed_rows.get(intake_id, ("", "", "OPEN"))[2] == "CONFIRMED"
    )
    owner_work_context = None
    owner_row = observed_rows.get("INTAKE-0001")
    if owner_row is not None and owner_row[2] == "CONFIRMED":
        owner_work_context = owner_row[1]

    confirmed_values = {
        field_name: value
        for field_name, value, status, _owner_response in observed_rows.values()
        if status == "CONFIRMED"
    }
    current_understanding: list[str] = []
    context_summary = {
        "NEW_APPLICATION": "Starting point: a new application.",
        "EXISTING_APPLICATION_CHANGE": (
            "Starting point: a change to an existing application."
        ),
        "REPAIR_OR_MIGRATION": ("Starting point: a repair, replacement, or migration."),
    }.get(owner_work_context)
    if context_summary is not None:
        current_understanding.append(context_summary)
    users = confirmed_values.get("PRIMARY_USERS")
    problem = confirmed_values.get("OWNER_STATED_PROBLEM")
    if users and problem:
        current_understanding.append(f"Users and problem: {users} — {problem}")
    elif users:
        current_understanding.append(f"Users: {users}")
    elif problem:
        current_understanding.append(f"Problem: {problem}")
    outcome = confirmed_values.get("OBSERVABLE_OUTCOME")
    boundary = confirmed_values.get("FIRST_RELEASE_BOUNDARY")
    if outcome and boundary:
        current_understanding.append(
            f"First useful outcome and release: {outcome} — {boundary}"
        )
    elif outcome:
        current_understanding.append(f"First useful outcome: {outcome}")
    elif boundary:
        current_understanding.append(f"First release: {boundary}")
    success = confirmed_values.get("SUCCESS_MEASURE")
    audience = confirmed_values.get("RELEASE_AUDIENCE")
    if success and audience:
        current_understanding.append(
            f"Success and first audience: {success} — {audience}"
        )
    elif success:
        current_understanding.append(f"Success measure: {success}")
    elif audience:
        current_understanding.append(f"First audience: {audience}")
    data_types = confirmed_values.get("DATA_TYPES")
    sensitivity = confirmed_values.get("DATA_SENSITIVITY")
    geography = confirmed_values.get("OPERATING_GEOGRAPHY")
    boundaries = [
        value for value in (data_types, sensitivity, geography) if value is not None
    ]
    if boundaries:
        current_understanding.append(
            "Data and operating boundaries: " + " — ".join(boundaries)
        )
    all_questions: list[IntakeQuestion] = []
    pending_questions: list[IntakeQuestion] = []
    card_ids: set[str] = set()
    revisions: set[int] = set()
    reply_keys: set[str] = set()
    question_ids: set[str] = set()
    for raw in card_table.rows:
        (
            card_id,
            revision_text,
            reply_key,
            question_id,
            kind,
            basis_value,
            prompt,
            option_a,
            option_b,
            option_c,
            recommended,
            required_detail_value,
            detail_prompt,
            selection,
            selection_detail,
            owner_response,
        ) = raw
        card_ids.add(card_id)
        try:
            revision = int(revision_text)
            if revision < 1 or str(revision) != revision_text:
                raise ValueError
        except ValueError:
            issues.append(
                ("INTAKE_CARD_INVALID", f"{question_id} has invalid card revision")
            )
            revision = 0
        revisions.add(revision)
        if INTAKE_CARD_ID.fullmatch(card_id) is None:
            issues.append(("INTAKE_CARD_INVALID", f"Invalid card ID {card_id!r}"))
        if reply_key not in {"1", "2", "3"} or reply_key in reply_keys:
            issues.append(
                (
                    "INTAKE_CARD_INVALID",
                    f"{question_id} has invalid or duplicate reply key",
                )
            )
        reply_keys.add(reply_key)
        if (
            INTAKE_QUESTION_ID.fullmatch(question_id) is None
            or question_id in question_ids
        ):
            issues.append(
                (
                    "INTAKE_CARD_INVALID",
                    f"Invalid or duplicate question ID {question_id!r}",
                )
            )
        question_ids.add(question_id)
        if kind not in {"FACT", "DECISION"}:
            issues.append(
                ("INTAKE_CARD_INVALID", f"{question_id} kind must be FACT or DECISION")
            )
        try:
            question_basis = tuple(
                _canonical_id_list(basis_value, INTAKE_ID, f"{question_id} Basis IDs")
            )
            if not set(question_basis).issubset(expected_rows):
                raise ValueError("Basis IDs must cite canonical intake foundation rows")
        except ValueError as exc:
            issues.append(("INTAKE_CARD_INVALID", f"{question_id}: {exc}"))
            question_basis = ()
        if not explicit_value(prompt, allow_none=False):
            issues.append(
                ("INTAKE_CARD_INVALID", f"{question_id} prompt is unresolved")
            )

        if kind == "DECISION":
            options = (option_a, option_b, option_c)
            if any(not explicit_value(option, allow_none=False) for option in options):
                issues.append(
                    (
                        "INTAKE_CARD_INVALID",
                        f"{question_id} requires concrete A/B/C choices",
                    )
                )
            if len(set(options)) != 3:
                issues.append(
                    ("INTAKE_CARD_INVALID", f"{question_id} choices must be distinct")
                )
            if recommended not in {"A", "NONE"}:
                issues.append(
                    (
                        "INTAKE_CARD_INVALID",
                        f"{question_id} recommendation must be A or NONE",
                    )
                )
        else:
            if any(
                option != "NOT_APPLICABLE" for option in (option_a, option_b, option_c)
            ):
                issues.append(
                    (
                        "INTAKE_CARD_INVALID",
                        f"{question_id} FACT choices must be NOT_APPLICABLE",
                    )
                )
            if recommended != "NONE":
                issues.append(
                    (
                        "INTAKE_CARD_INVALID",
                        f"{question_id} FACT recommendation must be NONE",
                    )
                )
        try:
            required_detail = _intake_required_detail(required_detail_value, kind)
        except ValueError as exc:
            issues.append(("INTAKE_CARD_INVALID", f"{question_id}: {exc}"))
            required_detail = ()
        if required_detail:
            if not explicit_value(detail_prompt, allow_none=False):
                issues.append(
                    (
                        "INTAKE_CARD_INVALID",
                        f"{question_id} requires a concrete detail prompt",
                    )
                )
            detail_prompt_value: str | None = detail_prompt
        else:
            if detail_prompt != "NONE":
                issues.append(
                    ("INTAKE_CARD_INVALID", f"{question_id} detail prompt must be NONE")
                )
            detail_prompt_value = None

        allowed_selections = (
            {"PENDING", "RESPONSE"} if kind == "FACT" else {"PENDING", "A", "B", "C"}
        )
        if selection not in allowed_selections:
            issues.append(
                (
                    "INTAKE_CARD_INVALID",
                    f"{question_id} has invalid selection {selection!r}",
                )
            )
        resolved = selection != "PENDING"
        provenance = INTAKE_OWNER_RESPONSE.fullmatch(owner_response)
        if not resolved:
            if selection_detail != "NONE" or owner_response != "NONE":
                issues.append(
                    (
                        "INTAKE_SELECTION_PROVENANCE_INVALID",
                        f"{question_id} has an unproven selection; remove it and present the current card again",
                    )
                )
            if any(
                response.card_id == card_id
                and response.revision == revision
                and response.question_id == question_id
                for response in normalized_responses
            ):
                issues.append(
                    (
                        "INTAKE_SELECTION_PROVENANCE_INVALID",
                        f"{question_id} has an unproven selection; remove it and present the current card again",
                    )
                )
        else:
            normalized_response = responses_by_provenance.get(owner_response)
            if (
                provenance is None
                or provenance.group("card") != card_id
                or int(provenance.group("revision")) != revision
                or provenance.group("question") != question_id
                or provenance.group("answer") != selection
                or normalized_response is None
            ):
                issues.append(
                    (
                        "INTAKE_SELECTION_PROVENANCE_INVALID",
                        f"{question_id} selection is not bound to a current OWNER_RESPONSE",
                    )
                )
            elif (
                normalized_response.reply_key != reply_key
                or normalized_response.selection_detail
                != (None if selection_detail == "NONE" else selection_detail)
                or normalized_response.basis_ids != question_basis
            ):
                issues.append(
                    (
                        "INTAKE_SELECTION_PROVENANCE_INVALID",
                        f"{question_id} does not match its normalized owner response",
                    )
                )
            for basis_id in question_basis:
                foundation_row = observed_rows.get(basis_id)
                if (
                    foundation_row is None
                    or foundation_row[2] != "CONFIRMED"
                    or foundation_row[3] != owner_response
                ):
                    issues.append(
                        (
                            "INTAKE_FOUNDATION_PROVENANCE_INVALID",
                            f"{question_id} and {basis_id} must cite the same parsed owner response",
                        )
                    )
            detail_required = selection == "RESPONSE" or selection in required_detail
            if detail_required and not explicit_value(
                selection_detail, allow_none=False
            ):
                issues.append(
                    (
                        "INTAKE_SELECTION_PROVENANCE_INVALID",
                        f"{question_id} remains unresolved until its required detail is supplied",
                    )
                )
            if not detail_required and selection_detail != "NONE":
                issues.append(
                    (
                        "INTAKE_SELECTION_PROVENANCE_INVALID",
                        f"{question_id} has unexpected selection detail",
                    )
                )

        question = IntakeQuestion(
            reply_key=reply_key,
            question_id=question_id,
            kind=kind,
            basis_ids=question_basis,
            prompt=prompt,
            option_a=option_a,
            option_b=option_b,
            option_c=option_c,
            recommended=None if recommended == "NONE" else recommended,
            required_detail_for=required_detail,
            detail_prompt=detail_prompt_value,
            selection=selection,
            selection_detail=None if selection_detail == "NONE" else selection_detail,
        )
        all_questions.append(question)
        if not resolved:
            pending_questions.append(question)

    if len(all_questions) > 1:
        issues.append(
            (
                "INTAKE_CARD_MIGRATION_REQUIRED",
                "Reissue the first unresolved intake question alone with a new card revision and digest",
            )
        )
    elif len(all_questions) != 1:
        issues.append(
            (
                "INTAKE_CARD_INVALID",
                "Current intake card must contain exactly one question",
            )
        )
    if len(card_ids) != 1 or len(revisions) != 1:
        issues.append(
            ("INTAKE_CARD_INVALID", "Current intake card must use one ID and revision")
        )
    if sorted(reply_keys) != [str(index) for index in range(1, len(reply_keys) + 1)]:
        issues.append(
            (
                "INTAKE_CARD_INVALID",
                "Reply keys must be consecutive uppercase-choice numbers",
            )
        )

    pending_card = None
    if (
        len(all_questions) == 1
        and pending_questions
        and len(card_ids) == 1
        and len(revisions) == 1
    ):
        card_id = next(iter(card_ids))
        revision = next(iter(revisions))
        accept_all = all(
            question.kind == "DECISION"
            and question.recommended == "A"
            and "A" not in question.required_detail_for
            for question in pending_questions
        )
        canonical_sha256 = (
            "sha256:" + hashlib.sha256(card_table.canonical_bytes).hexdigest()
        )
        reply_token = intake_reply_token(card_id, revision, canonical_sha256)
        pending_card = IntakeCard(
            card_id=card_id,
            revision=revision,
            questions=tuple(pending_questions),
            accept_all_allowed=accept_all,
            owner_reply=_intake_owner_reply_example(pending_questions),
            exact_reply=_intake_reply_example(pending_questions, reply_token),
            canonical_sha256=canonical_sha256,
            reply_token=reply_token,
        )
    if missing_fields and not pending_questions:
        issues.append(
            (
                "INTAKE_CARD_REQUIRED",
                "Create the next one-question intake card for the remaining foundation fields",
            )
        )

    invalid_codes = {
        "INTAKE_FOUNDATION_INVALID",
        "INTAKE_FOUNDATION_PROVENANCE_INVALID",
        "INTAKE_RESPONSE_REGISTER_INVALID",
        "INTAKE_CARD_INVALID",
        "INTAKE_SELECTION_PROVENANCE_INVALID",
    }
    if any(code in invalid_codes for code, _ in issues):
        status = "BLOCKED"
    elif pending_questions or missing_fields:
        status = (
            "FOUNDATION_REQUIRED"
            if INTAKE_CORE_FIELDS.intersection(missing_fields)
            else "FOUNDATION_READY"
        )
    else:
        status = "READY_FOR_REQUIREMENTS"
    return (
        IntakeFoundationContract(
            status=status,
            current_understanding=tuple(current_understanding),
            repository_mode=repository_mode_value,
            owner_work_context=owner_work_context,
            basis_ids=basis_ids,
            missing_fields=missing_fields,
            pending_card=pending_card,
            normalized_responses=tuple(normalized_responses),
            all_questions=tuple(all_questions),
        ),
        issues,
    )


def _none_with_reason(value: str) -> bool:
    cleaned = clean_cell(value)
    return bool(re.fullmatch(r"NONE\s+(?:-|—)\s+\S.*", cleaned)) and not unresolved(
        cleaned
    )


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
    owner_work_context: str | None = None,
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
        return CoverageContract(
            status="BLOCKED" if required else "UNINITIALIZED"
        ), issues
    if len(table.rows) != 1:
        issues.append("Adaptive coverage plan must contain exactly one row")
        return CoverageContract(
            status="BLOCKED", canonical_bytes=table.canonical_bytes
        ), issues

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
    if owner_work_context == "NEW_APPLICATION" and work_kind != "NEW_BUILD":
        issues.append("NEW_APPLICATION owner work context requires work kind NEW_BUILD")
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
        if (
            STABLE_CONTRACT_ID.search(omission.reason) is None
            and "REPOSITORY_BASELINE" not in omission.reason
        ):
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
            for identifier in [
                requirements_revision,
                *sorted(authoritative_requirement_ids(text)),
            ]
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
        return ChangeImpactContract(
            status="BLOCKED" if required else "UNINITIALIZED"
        ), issues

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
        if any(
            identifier in authoritative_requirement_ids(text) for identifier in changed
        ):
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
    architecture_disposition: str | None = None,
    grandfather_approved_v1: bool = False,
) -> tuple[ArchitectureContract, list[str]]:
    issues: list[str] = []
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
    parse_issues: list[str] = []
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
            parse_issues.append(f"{heading}: {current_message}")
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
        grandfather_approved_v1 or gate_b_state == "APPROVED_FOR_CONSTRUCTION"
    )
    if all_missing:
        if required and not grandfathered:
            issues.extend(f"Missing {heading}" for _, heading, _ in specifications)
        return (
            ArchitectureContract(
                schema_version=1,
                status="READY"
                if grandfathered and not issues
                else "UNINITIALIZED"
                if not required
                else "BLOCKED",
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
                issues.append(
                    f"{driver.driver_id}: invalid driver class {driver.driver_class!r}"
                )
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
                design_ids = _canonical_id_list(
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
                bound_ids = _canonical_id_list(
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
            evidence_ids = _canonical_id_list(
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


def harness_status_parts(value: str) -> tuple[str, str | None]:
    cleaned = clean_cell(value)
    if cleaned == "REQUIRED":
        return "REQUIRED", None
    for prefix in ("CONDITIONAL", "NOT_APPLICABLE"):
        if not cleaned.startswith(prefix):
            continue
        suffix = cleaned[len(prefix) :].strip()
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
                issues.append(
                    f"{row.harness_id}: CONDITIONAL requires a concrete trigger"
                )
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


def _explicit_not_applicable_section(text: str, heading: str) -> bytes | None:
    section = _heading_section_lines(text, heading)
    if section is None:
        return None
    lines, structural_lines = section
    visible_lines = [
        line.strip()
        for line, structural in zip(lines, structural_lines)
        if structural.strip() and not structural.strip().startswith("|")
    ]
    for line in visible_lines:
        match = re.fullmatch(
            r"NOT_APPLICABLE\s+(?:\u2014|-)\s+(?P<reason>[^\r\n]+)",
            line,
        )
        if match is None:
            continue
        if explicit_value(match.group("reason"), allow_none=False):
            return (
                f"{heading}\nNOT_APPLICABLE - {match.group('reason').strip()}\n"
            ).encode("utf-8")
    return None


def _explicit_not_applicable_value(value: str) -> bool:
    match = re.fullmatch(
        r"NOT_APPLICABLE\s+(?:\u2014|-)\s+(?P<reason>.+)", clean_cell(value)
    )
    return bool(match and explicit_value(match.group("reason"), allow_none=False))


def _server_side_authorization_or_not_applicable(value: str) -> bool:
    cleaned = clean_cell(value)
    if _explicit_not_applicable_value(cleaned):
        return True
    normalized = re.sub(r"[\s-]+", "_", cleaned.upper())
    return "SERVER_SIDE" in normalized or bool(
        re.search(
            r"\bserver(?:-side)?\b.*\b(?:authoriz\w*|enforc\w*|verif\w*|den\w*|reject\w*)\b",
            cleaned,
            re.IGNORECASE,
        )
    )


def _measurable_interface_bound_or_not_applicable(value: str) -> bool:
    cleaned = clean_cell(value)
    return _explicit_not_applicable_value(cleaned) or bool(
        explicit_value(cleaned, allow_none=False)
        and UNDEFINED_QUALITY_TERM.search(cleaned) is None
        and MEASURABLE_INTERFACE_BOUND.search(cleaned)
    )


def _design_reference_issues(
    identifier: str,
    requirement_value: str,
    validation_value: str,
    requirement_ids: set[str],
    validation_ids: set[str],
) -> list[str]:
    issues: list[str] = []
    try:
        refs = set(
            _contract_ids(
                requirement_value, STABLE_CONTRACT_ID, f"{identifier} Requirement IDs"
            )
        )
        unknown = sorted(refs - requirement_ids)
        if unknown:
            issues.append(
                f"{identifier}: unknown requirement IDs: " + ", ".join(unknown)
            )
        refs = set(
            _contract_ids(
                validation_value, STABLE_CONTRACT_ID, f"{identifier} Validation IDs"
            )
        )
        unknown = sorted(refs - validation_ids)
        if unknown:
            issues.append(
                f"{identifier}: unknown Validation IDs: " + ", ".join(unknown)
            )
    except ValueError as exc:
        issues.append(str(exc))
    return issues


def parse_application_source_disposition(
    value: str,
) -> ApplicationSourceDisposition:
    """Parse the exact schema-7 application-source decision grammar."""

    normalized = clean_cell(value)
    if normalized == APPLICATION_SOURCE_INFRASTRUCTURE_ONLY:
        return ApplicationSourceDisposition(APPLICATION_SOURCE_NOT_APPLICABLE)
    for kind in (APPLICATION_SOURCE_GREENFIELD, APPLICATION_SOURCE_BROWNFIELD):
        prefix = f"{kind}: "
        if not normalized.startswith(prefix):
            continue
        raw_paths = [item.strip() for item in normalized[len(prefix) :].split(";")]
        try:
            paths = tuple(
                parse_task_write_set(
                    ",".join(raw_paths), APPLICATION_SOURCE_DISPOSITION_FIELD
                )
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if not paths:
            raise ValueError("Application source disposition has no source paths")
        if kind == APPLICATION_SOURCE_GREENFIELD and paths != ("app/**",):
            raise ValueError(
                "GREENFIELD_APP_ROOT must be exactly GREENFIELD_APP_ROOT: app/**"
            )
        return ApplicationSourceDisposition(kind, paths)
    raise ValueError(
        "Application source disposition must use GREENFIELD_APP_ROOT: app/**, "
        "BROWNFIELD_PRESERVE: path/**; another/path/**, or "
        "NOT_APPLICABLE — INFRASTRUCTURE_ONLY"
    )


def _brownfield_source_contract_section(text: str) -> str:
    heading = "### 1.2 Brownfield baseline and preservation contract"
    structural = without_fenced_code(text)
    matches = list(re.finditer(rf"^{re.escape(heading)}\s*$", structural, re.MULTILINE))
    if len(matches) != 1:
        return ""
    following = structural[matches[0].end() :]
    next_heading = re.search(r"^##\s+2\.", following, re.MULTILINE)
    end = matches[0].end() + (next_heading.start() if next_heading else len(following))
    return text[matches[0].end() : end]


def _contains_exact_source_path(value: str, path: str) -> bool:
    """Match one recorded source path without accepting a longer lookalike."""

    return (
        re.search(
            rf"(?<![A-Za-z0-9._/*-]){re.escape(path)}(?![A-Za-z0-9._/*-])",
            value,
            re.IGNORECASE,
        )
        is not None
    )


def validate_application_source_disposition(
    disposition: ApplicationSourceDisposition,
    *,
    project_mode: str | None,
    work_kind: str | None,
    prd_text: str,
) -> list[str]:
    """Return stable schema-7 source-disposition diagnostics."""

    issues: list[str] = []
    if disposition.kind == APPLICATION_SOURCE_NOT_APPLICABLE:
        if work_kind != "INFRASTRUCTURE":
            issues.append(
                "APPLICATION_SOURCE_DISPOSITION_INVALID: "
                "NOT_APPLICABLE — INFRASTRUCTURE_ONLY requires Work kind INFRASTRUCTURE"
            )
        return issues
    if disposition.kind == APPLICATION_SOURCE_GREENFIELD:
        if project_mode != "greenfield":
            issues.append(
                "APPLICATION_SOURCE_DISPOSITION_INVALID: GREENFIELD_APP_ROOT "
                "requires greenfield project mode"
            )
        if work_kind == "INFRASTRUCTURE":
            issues.append(
                "APPLICATION_SOURCE_DISPOSITION_INVALID: infrastructure-only work "
                "must use NOT_APPLICABLE — INFRASTRUCTURE_ONLY"
            )
        return issues
    if disposition.kind != APPLICATION_SOURCE_BROWNFIELD:
        issues.append(
            "APPLICATION_SOURCE_DISPOSITION_INVALID: unknown application source disposition kind"
        )
        return issues
    if project_mode != "brownfield":
        issues.append(
            "APPLICATION_SOURCE_DISPOSITION_INVALID: BROWNFIELD_PRESERVE requires brownfield project mode"
        )
        return issues
    preserved_section = _brownfield_source_contract_section(prd_text)
    tables = markdown_tables(preserved_section)
    protected_paths = ""
    preservation_rows: list[list[str]] = []
    for table in tables:
        headers = table[0]
        if headers == ["Field", "Brownfield baseline"]:
            protected_paths = next(
                (
                    row[1]
                    for row in table[2:]
                    if len(row) == 2 and row[0] == "Protected files and components"
                ),
                "",
            )
        elif headers == [
            "Preservation ID",
            "Behavior, asset, or constraint to preserve",
            "How it is verified before change",
            "Allowed change",
            "Explicitly prohibited or approval-required change",
        ]:
            preservation_rows = table[2:]

    missing_baseline = [
        path
        for path in disposition.paths
        if not _contains_exact_source_path(protected_paths, path)
    ]
    missing_preservation = [
        path
        for path in disposition.paths
        if not any(
            _contains_exact_source_path(" | ".join(row[1:]), path)
            for row in preservation_rows
        )
    ]
    if missing_baseline or missing_preservation:
        details: list[str] = []
        if missing_baseline:
            details.append(
                "Protected files and components: " + ", ".join(missing_baseline)
            )
        if missing_preservation:
            details.append("matching PRES record: " + ", ".join(missing_preservation))
        issues.append(
            "APPLICATION_SOURCE_DISPOSITION_CONFLICT: brownfield source roots must "
            "appear unchanged in both Gate A brownfield records; missing from "
            + "; ".join(details)
        )
    return issues


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
    """Validate the current interface, source, boundary, state, and delivery contract."""

    issues: list[str] = []
    add = issues.append
    missing_records: list[str] = []
    try:
        document = table_after_heading(text, "## Document status")
    except ValueError as exc:
        document = {}
        if required:
            issues.append(str(exc))
    design_schema = clean_cell(document.get("Project design contract schema", ""))
    grandfather_schema_6 = bool(design_schema == "6" and grandfather_approved_v4)
    grandfather_schema_5 = bool(
        design_schema == "5"
        and grandfather_approved_v4
        and DIAGRAM_CONTRACT_HEADING not in without_fenced_code(text)
    )
    if (
        design_schema != PROJECT_DESIGN_CONTRACT_SCHEMA
        and not grandfather_schema_6
        and not grandfather_schema_5
    ):
        observed_tables = [table for table in markdown_tables(text) if table]
        observed_headers = {tuple(table[0]) for table in observed_tables}
        current_headers = {
            INTERFACE_HEADERS,
            LAYER_BOUNDARY_HEADERS,
            STATE_APPLICABILITY_HEADERS,
            STATE_REGISTER_HEADERS,
            FIRST_WAVE_HEADERS,
            SPIKE_HEADERS,
            DIAGRAM_CONTRACT_HEADERS,
        }
        legacy_interface_tables = [
            table
            for table in observed_tables
            if tuple(table[0]) == LEGACY_INTERFACE_HEADERS_V4
        ]
        legacy_interface_ids = [
            clean_cell(row[0])
            for table in legacy_interface_tables
            for row in table[2:]
            if len(row) == len(LEGACY_INTERFACE_HEADERS_V4)
        ]
        structural_text = without_fenced_code(text)
        schema_five_only_headings = (
            LAYER_BOUNDARY_HEADING,
            STATE_APPLICABILITY_HEADING,
            STATE_REGISTER_HEADING,
            FIRST_WAVE_HEADING,
            SPIKE_HEADING,
        )
        exact_legacy_shape = bool(
            not design_schema
            and len(legacy_interface_tables) == 1
            and legacy_interface_ids
            and all(INTERFACE_ID.fullmatch(item) for item in legacy_interface_ids)
            and not (observed_headers & current_headers)
            and not any(
                re.search(
                    rf"^{re.escape(heading)}[ \t]*$", structural_text, re.MULTILINE
                )
                for heading in schema_five_only_headings
            )
            and any(ARCHITECTURE_ID.fullmatch(item) for item in legacy_design_ids)
            and any(
                TECHNOLOGY_DECISION_ID.fullmatch(item) for item in legacy_design_ids
            )
            and any(PROPERTY_ID.fullmatch(item) for item in legacy_design_ids)
            and any(HARNESS_ID.fullmatch(item) for item in legacy_design_ids)
        )
        if grandfather_approved_v4 and exact_legacy_shape:
            return (
                ProjectDesignContract(
                    schema_version=4, status="GRANDFATHERED", grandfathered_v4=True
                ),
                [],
            )
        if not required:
            return ProjectDesignContract(status="UNINITIALIZED"), []
        return (
            ProjectDesignContract(
                status="MIGRATION_REQUIRED",
                missing_records=(
                    "Project design contract schema 7",
                    APPLICATION_SOURCE_DISPOSITION_FIELD,
                    INTERFACE_HEADING,
                    LAYER_BOUNDARY_HEADING,
                    STATE_APPLICABILITY_HEADING,
                    STATE_REGISTER_HEADING,
                    FIRST_WAVE_HEADING,
                    SPIKE_HEADING,
                    DIAGRAM_CONTRACT_HEADING,
                ),
            ),
            [
                "Project design contract schema 7 requires an application source "
                "disposition plus current interface, layer-boundary, state-applicability, "
                "first-wave, spike, and diagram records"
            ],
        )

    source_disposition: ApplicationSourceDisposition | None = None
    if not (grandfather_schema_5 or grandfather_schema_6):
        try:
            envelope = table_after_heading(text, "## 28. Construction envelope")
        except ValueError as exc:
            envelope = {}
            if required:
                add(
                    "APPLICATION_SOURCE_DISPOSITION_MISSING: unable to read the "
                    f"construction envelope: {exc}"
                )
        raw_disposition = clean_cell(
            envelope.get(APPLICATION_SOURCE_DISPOSITION_FIELD, "")
        )
        if not raw_disposition or unresolved(raw_disposition):
            if required:
                add(
                    "APPLICATION_SOURCE_DISPOSITION_MISSING: schema 7 requires "
                    "Application source disposition before Gate B"
                )
                missing_records.append(APPLICATION_SOURCE_DISPOSITION_FIELD)
        else:
            try:
                source_disposition = parse_application_source_disposition(
                    raw_disposition
                )
            except ValueError as exc:
                add(f"APPLICATION_SOURCE_DISPOSITION_INVALID: {exc}")
            if source_disposition is not None:
                issues.extend(
                    validate_application_source_disposition(
                        source_disposition,
                        project_mode=clean_cell(
                            document.get("Project mode", "")
                        ).lower()
                        or None,
                        work_kind=coverage_contract.work_kind,
                        prd_text=text,
                    )
                )

    interfaces, boundaries, state_applicability, states = (
        _contract_table_or_issue(text, heading, headers, issues, missing_records)
        for heading, headers in (
            (INTERFACE_HEADING, INTERFACE_HEADERS),
            (LAYER_BOUNDARY_HEADING, LAYER_BOUNDARY_HEADERS),
            (STATE_APPLICABILITY_HEADING, STATE_APPLICABILITY_HEADERS),
            (STATE_REGISTER_HEADING, STATE_REGISTER_HEADERS),
        )
    )

    requirement_ids = set(
        requirements_contract.requirement_ids
    ) or authoritative_requirement_ids(text)
    current_validation_ids = (
        set(allowed_basis_ids)
        | set(requirements_contract.acceptance_ids)
        | set(harness.required_ids)
    )
    journey_requirement_ids: dict[str, set[str]] = {}
    try:
        journey_table = contract_table_after_heading(
            text, JOURNEY_HEADING, JOURNEY_HEADERS
        )
    except ValueError:
        journey_table = None
    if journey_table is not None:
        for journey_row in journey_table.rows:
            journey_id = journey_row[0]
            if JOURNEY_ID.fullmatch(journey_id) is None:
                continue
            try:
                journey_requirement_ids[journey_id] = set(
                    _contract_ids(
                        journey_row[6],
                        STABLE_CONTRACT_ID,
                        f"{journey_id} Requirement IDs",
                    )
                )
            except ValueError:
                continue
    interface_ids: list[str] = []
    if interfaces is not None:
        if not interfaces.rows and coverage_contract.work_kind == "NEW_BUILD":
            add("NEW_BUILD requires at least one material interface contract")
        for row in interfaces.rows:
            contract_id, kind, requirement_value, *details = row
            if INTERFACE_ID.fullmatch(contract_id) is None:
                add(f"Invalid material interface ID {contract_id!r}")
                continue
            if contract_id in interface_ids:
                add(f"Duplicate material interface ID {contract_id}")
            interface_ids.append(contract_id)
            if kind not in INTERFACE_KINDS or not contract_id.startswith(kind + "-"):
                add(f"{contract_id}: Kind must match its API/EVENT/CLI/FILE prefix")
            try:
                refs = set(
                    _contract_ids(
                        requirement_value,
                        STABLE_CONTRACT_ID,
                        f"{contract_id} Requirement basis",
                    )
                )
                unknown = sorted(refs - requirement_ids)
                if unknown:
                    add(
                        f"{contract_id}: unknown requirement basis IDs: "
                        + ", ".join(unknown)
                    )
            except ValueError as exc:
                add(str(exc))
            for header, value in zip(INTERFACE_HEADERS[3:], details):
                if not explicit_value(value, allow_none=False):
                    add(f"{contract_id}: {header} must be concrete")
            detail_values = dict(zip(INTERFACE_HEADERS[3:], details))
            if not _server_side_authorization_or_not_applicable(
                detail_values["Authorization"]
            ):
                add(
                    f"{contract_id}: Authorization must be server-side or use "
                    "NOT_APPLICABLE - <reason>"
                )
            for header in ("Timeout bound", "Rate bound", "Performance bound"):
                if not _measurable_interface_bound_or_not_applicable(
                    detail_values[header]
                ):
                    add(
                        f"{contract_id}: {header} must contain a numeric measurable "
                        "bound or use NOT_APPLICABLE - <reason>"
                    )

    boundary_ids: list[str] = []
    if boundaries is not None:
        if not boundaries.rows and coverage_contract.work_kind == "NEW_BUILD":
            add("NEW_BUILD requires at least one explicit layer boundary")
        for row in boundaries.rows:
            (
                boundary_id,
                outer,
                inner,
                dto,
                mapping,
                direction,
                authorization,
                adapter,
                requirement_value,
                validation_value,
            ) = row
            if BOUNDARY_ID.fullmatch(boundary_id) is None:
                add(f"Invalid boundary ID {boundary_id!r}")
                continue
            if boundary_id in boundary_ids:
                add(f"Duplicate boundary ID {boundary_id}")
            boundary_ids.append(boundary_id)
            for header, value in zip(
                LAYER_BOUNDARY_HEADERS[1:8],
                (outer, inner, dto, mapping, direction, authorization, adapter),
            ):
                if not explicit_value(value, allow_none=False):
                    add(f"{boundary_id}: {header} must be concrete")
            if "INWARD" not in direction.upper():
                add(f"{boundary_id}: Dependency direction must explicitly point inward")
            normalized_authorization = authorization.upper().replace("-", "_")
            if "SERVER_SIDE" not in normalized_authorization:
                add(f"{boundary_id}: Authorization enforcement must be server-side")
            issues.extend(
                _design_reference_issues(
                    boundary_id,
                    requirement_value,
                    validation_value,
                    requirement_ids,
                    current_validation_ids,
                )
            )

    applicable_state_ids: set[str] = set()
    state_subjects: dict[str, str] = {}
    declared_state_triggers: set[str] = set()
    required_state_triggers = {
        RICH_TO_STATE_TRIGGER[item]
        for item in requirements_contract.rich_use_case_triggers
        if item in RICH_TO_STATE_TRIGGER
    }
    if state_applicability is not None:
        if not state_applicability.rows:
            add("State-model applicability requires at least one row")
        for (
            subject_id,
            applicability,
            trigger_basis,
            state_value,
        ) in state_applicability.rows:
            if STABLE_CONTRACT_ID.fullmatch(subject_id) is None:
                add(f"Invalid state subject ID {subject_id!r}")
            if applicability == "APPLICABLE":
                try:
                    refs = _contract_ids(
                        state_value, STATE_ID, f"{subject_id} State model IDs"
                    )
                    for state_id in refs:
                        applicable_state_ids.add(state_id)
                        state_subjects[state_id] = subject_id
                    trigger_map = _state_trigger_map(trigger_basis, subject_id)
                    declared_state_triggers.update(trigger_map)
                    trigger_refs = {
                        item for values in trigger_map.values() for item in values
                    }
                    unknown_trigger = sorted(
                        trigger_refs - current_validation_ids - requirement_ids
                    )
                    if unknown_trigger:
                        add(
                            f"{subject_id}: unknown State trigger basis IDs: "
                            + ", ".join(unknown_trigger)
                        )
                except ValueError as exc:
                    add(str(exc))
            elif applicability == "NOT_APPLICABLE":
                if (
                    not trigger_basis.startswith("NOT_APPLICABLE")
                    or not explicit_value(trigger_basis, allow_none=False)
                    or state_value != "NONE"
                ):
                    add(
                        f"{subject_id}: NOT_APPLICABLE requires a concrete reason and State model IDs NONE"
                    )
            else:
                add(
                    f"{subject_id}: State applicability must be APPLICABLE or NOT_APPLICABLE"
                )
    missing_state_triggers = sorted(required_state_triggers - declared_state_triggers)
    if missing_state_triggers:
        add(
            "Journey triggers require applicable state categories: "
            + ", ".join(missing_state_triggers)
        )
    if requirements_contract.grandfathered_approved_gate_a and not applicable_state_ids:
        add("A grandfathered Gate A design requires an applicable state model")

    state_ids: list[str] = []
    if states is not None:
        for row in states.rows:
            (
                state_id,
                subject_id,
                state_value,
                initial_state,
                transitions,
                terminal_value,
                invalid_behavior,
                requirement_value,
                validation_value,
            ) = row
            if STATE_ID.fullmatch(state_id) is None:
                add(f"Invalid state model ID {state_id!r}")
                continue
            if state_id in state_ids:
                add(f"Duplicate state model ID {state_id}")
            state_ids.append(state_id)
            if state_id not in applicable_state_ids:
                add(f"{state_id}: state row is not declared APPLICABLE")
            if state_subjects.get(state_id) != subject_id:
                add(f"{state_id}: Subject ID does not match state applicability")
            declared_states = [
                item.strip() for item in state_value.split(",") if item.strip()
            ]
            if (
                not declared_states
                or state_value != ", ".join(declared_states)
                or initial_state not in declared_states
            ):
                add(
                    f"{state_id}: States must be canonical and contain the initial state"
                )
            if terminal_value != "NONE":
                terminal_states = [
                    item.strip() for item in terminal_value.split(",") if item.strip()
                ]
                if not set(terminal_states) <= set(declared_states):
                    add(f"{state_id}: Terminal states must be declared states or NONE")
            for label, value in (
                ("Allowed transitions", transitions),
                ("Invalid-transition behavior", invalid_behavior),
            ):
                if not explicit_value(value, allow_none=False):
                    add(f"{state_id}: {label} must be concrete")
            issues.extend(
                _design_reference_issues(
                    state_id,
                    requirement_value,
                    validation_value,
                    requirement_ids,
                    current_validation_ids,
                )
            )
        missing_states = sorted(applicable_state_ids - set(state_ids))
        if missing_states:
            add(
                "Applicable state models have no state row: "
                + ", ".join(missing_states)
            )

    first_wave_table: ContractTable | None = None
    first_wave_sentinel = _explicit_not_applicable_section(text, FIRST_WAVE_HEADING)
    try:
        first_wave_table = contract_table_after_heading(
            text, FIRST_WAVE_HEADING, FIRST_WAVE_HEADERS
        )
    except ValueError as exc:
        if first_wave_sentinel is None:
            add(f"{FIRST_WAVE_HEADING}: {exc}")
            missing_records.append(FIRST_WAVE_HEADING)
    first_wave: FirstWaveContract | None = None
    work_kind = coverage_contract.work_kind
    if work_kind == "NEW_BUILD":
        if first_wave_table is None or len(first_wave_table.rows) != 1:
            add("NEW_BUILD requires exactly one first construction wave row")
        else:
            (
                wave_id,
                row_work_kind,
                journey_id,
                requirement_value,
                acceptance_value,
                harness_id,
                spike_value,
            ) = first_wave_table.rows[0]
            if WAVE_ID.fullmatch(wave_id) is None:
                add(f"Invalid first-wave ID {wave_id!r}")
            if row_work_kind != "NEW_BUILD":
                add("First-wave Work kind must exactly match NEW_BUILD")
            legacy_bridge = requirements_contract.grandfathered_approved_gate_a
            journey_reference: str | None = None if legacy_bridge else journey_id
            if legacy_bridge and journey_id != "NONE":
                add(
                    f"{wave_id}: grandfathered Gate A walking-skeleton journey must be NONE"
                )
            elif not legacy_bridge and journey_id not in set(
                requirements_contract.journey_ids
            ):
                add(f"{wave_id}: walking-skeleton journey is not a current JOURNEY ID")
            try:
                wave_requirements = tuple(
                    _contract_ids(
                        requirement_value,
                        STABLE_CONTRACT_ID,
                        f"{wave_id} Requirement IDs",
                    )
                )
                unknown = sorted(set(wave_requirements) - requirement_ids)
                if unknown:
                    add(f"{wave_id}: unknown requirement IDs: " + ", ".join(unknown))
                selected_journey_requirements = journey_requirement_ids.get(
                    journey_reference or ""
                )
                if selected_journey_requirements is not None:
                    outside_journey = sorted(
                        set(wave_requirements) - selected_journey_requirements
                    )
                    if outside_journey:
                        add(
                            f"{wave_id}: first-wave requirement IDs are not owned by {journey_reference}: "
                            + ", ".join(outside_journey)
                        )
                acceptance_ids = tuple(
                    _contract_ids(
                        acceptance_value,
                        STABLE_CONTRACT_ID,
                        f"{wave_id} Acceptance/test IDs",
                    )
                )
                expected_acceptance = {f"AC-{item}" for item in wave_requirements}
                missing_acceptance = sorted(expected_acceptance - set(acceptance_ids))
                if missing_acceptance:
                    add(
                        f"{wave_id}: missing acceptance IDs: "
                        + ", ".join(missing_acceptance)
                    )
                unknown_acceptance = sorted(
                    set(acceptance_ids) - current_validation_ids
                )
                if unknown_acceptance:
                    add(
                        f"{wave_id}: unknown acceptance/test IDs: "
                        + ", ".join(unknown_acceptance)
                    )
            except ValueError as exc:
                wave_requirements = ()
                acceptance_ids = ()
                add(str(exc))
            harness_row = next(
                (row for row in harness.rows if row.harness_id == harness_id), None
            )
            if (
                harness_row is None
                or harness_row.layer != "End-to-end"
                or harness_id not in set(harness.required_ids)
            ):
                add(
                    f"{wave_id}: End-to-end Harness ID must reference a current required end-to-end check"
                )
            else:
                harness_basis = set(
                    _canonical_id_list(
                        harness_row.basis_ids,
                        STABLE_CONTRACT_ID,
                        f"{harness_id} Basis IDs",
                    )
                )
                required_harness_basis = (
                    {wave_id, *wave_requirements}
                    if legacy_bridge
                    else {wave_id, journey_id}
                )
                if not required_harness_basis <= harness_basis:
                    message = (
                        "include the wave and every selected requirement"
                        if legacy_bridge
                        else f"include both {journey_id} and {wave_id}"
                    )
                    add(f"{wave_id}: {harness_id} Basis IDs must {message}")
            spike_id: str | None
            if spike_value == "NONE":
                spike_id = None
            elif SPIKE_ID.fullmatch(spike_value) is None:
                spike_id = None
                add(f"{wave_id}: invalid Blocking spike ID {spike_value!r}")
            else:
                spike_id = spike_value
            first_wave = FirstWaveContract(
                wave_contract_id=wave_id,
                work_kind=row_work_kind,
                journey_id=journey_reference,
                requirement_ids=wave_requirements,
                acceptance_test_ids=acceptance_ids,
                harness_id=harness_id,
                blocking_spike_id=spike_id,
            )
    elif first_wave_sentinel is None:
        add("Non-NEW_BUILD work requires an explicit NOT_APPLICABLE first-wave reason")

    spike_table: ContractTable | None = None
    spike_sentinel = _explicit_not_applicable_section(text, SPIKE_HEADING)
    try:
        spike_table = contract_table_after_heading(text, SPIKE_HEADING, SPIKE_HEADERS)
    except ValueError as exc:
        if spike_sentinel is None:
            issues.append(f"{SPIKE_HEADING}: {exc}")
            missing_records.append(SPIKE_HEADING)
    spike: SpikeContract | None = None
    expected_spike_id = first_wave.blocking_spike_id if first_wave is not None else None
    if expected_spike_id is None:
        if spike_sentinel is None:
            add(
                "A first wave without a blocking spike requires an explicit NOT_APPLICABLE spike reason"
            )
    elif spike_table is None or len(spike_table.rows) != 1:
        add("A referenced blocking spike requires exactly one spike row")
    else:
        spike_id, unknown, time_box, disposable, exit_criterion, next_action = (
            spike_table.rows[0]
        )
        if spike_id != expected_spike_id:
            add("Blocking spike row must exactly match the first-wave spike ID")
        if not explicit_value(unknown, allow_none=False):
            add(f"{spike_id}: Blocking technical unknown must be concrete")
        if re.fullmatch(r"MAX_ATTEMPTS: [1-9]\d*", time_box) is None:
            add(f"{spike_id}: Time box must use MAX_ATTEMPTS: <positive integer>")
        for label, value in (
            ("Disposable output boundary", disposable),
            ("Exit criterion", exit_criterion),
        ):
            if not explicit_value(value, allow_none=False):
                add(f"{spike_id}: {label} must be concrete")
        if not valid_property_execution_command(exit_criterion):
            add(
                f"{spike_id}: Exit criterion must be one explicit local command, "
                "not prose, shell control, or placeholder content"
            )
        if next_action != "DISCARD_AND_BUILD_WALKING_SKELETON":
            add(
                f"{spike_id}: Required next action must be DISCARD_AND_BUILD_WALKING_SKELETON"
            )
        spike = SpikeContract(
            spike_id=spike_id,
            technical_unknown=unknown,
            time_box=time_box,
            disposable_boundary=disposable,
            exit_criterion=exit_criterion,
            required_next_action=next_action,
        )

    canonical_parts: list[bytes] = [
        f"PROJECT_DESIGN_CONTRACT_SCHEMA: "
        f"{'5' if grandfather_schema_5 else '6' if grandfather_schema_6 else PROJECT_DESIGN_CONTRACT_SCHEMA}\n".encode(
            "utf-8"
        )
    ]
    if source_disposition is not None:
        canonical_parts.append(
            (
                "APPLICATION_SOURCE_DISPOSITION: "
                + source_disposition.canonical_value
                + "\n"
            ).encode("utf-8")
        )
    if (
        requirements_contract.grandfathered_approved_gate_a
        and requirements_contract.canonical_sha256 is None
    ):
        add(
            "Grandfathered Gate A design requires a canonical legacy requirements projection"
        )
    elif requirements_contract.grandfathered_approved_gate_a:
        canonical_parts.append(
            f"LEGACY_GATE_A_BRIDGE: {requirements_contract.canonical_sha256}\n".encode(
                "utf-8"
            )
        )
    for table in (interfaces, boundaries, state_applicability, states):
        if table is not None:
            canonical_parts.append(table.canonical_bytes)
    if first_wave_table is not None:
        canonical_parts.append(first_wave_table.canonical_bytes)
    elif first_wave_sentinel is not None:
        canonical_parts.append(first_wave_sentinel)
    if spike_table is not None and expected_spike_id is not None:
        canonical_parts.append(spike_table.canonical_bytes)
    elif spike_sentinel is not None:
        canonical_parts.append(spike_sentinel)
    canonical_bytes = b"".join(canonical_parts)
    canonical_sha256 = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
    if not required and any(
        unresolved(cell)
        for table in (interfaces, boundaries, state_applicability, states)
        if table is not None
        for row in table.rows
        for cell in row
    ):
        return ProjectDesignContract(status="UNINITIALIZED"), []
    return (
        ProjectDesignContract(
            schema_version=(
                5 if grandfather_schema_5 else 6 if grandfather_schema_6 else 7
            ),
            status=(
                "GRANDFATHERED"
                if (grandfather_schema_5 or grandfather_schema_6) and not issues
                else "READY"
                if not issues
                else "BLOCKED"
            ),
            application_source_disposition=source_disposition,
            interface_ids=tuple(interface_ids),
            boundary_ids=tuple(boundary_ids),
            state_ids=tuple(state_ids),
            first_wave=first_wave,
            spike=spike,
            missing_records=tuple(dict.fromkeys(missing_records)),
            canonical_sha256=canonical_sha256,
            grandfathered_v5=grandfather_schema_5,
            grandfathered_v6=grandfather_schema_6,
            canonical_bytes=canonical_bytes,
        ),
        issues,
    )


def required_diagram_kinds(
    text: str,
    requirement_ids: Iterable[str],
    work_kind: str | None,
) -> set[str]:
    """Return diagram kinds required by the current canonical project records."""

    required = set(DIAGRAM_REQUIRED_KINDS)
    identifiers = set(requirement_ids)
    if any(identifier.startswith("DATA-") for identifier in identifiers):
        required.add("DATA_LIFECYCLE")
    if any(identifier.startswith("REL-") for identifier in identifiers):
        required.add("FAILURE_RECOVERY")
    try:
        document = table_after_heading(text, "## Document status")
    except ValueError:
        document = {}
    if (
        work_kind == "MIGRATION"
        or clean_cell(document.get("Project mode", "")).lower() == "brownfield"
    ):
        required.add("MIGRATION")
    return required


def _diagram_heading_for_anchor(text: str, anchor: str) -> str:
    """Resolve one stable Markdown anchor through the shared fenced-code rules."""

    structural = without_fenced_code(text)
    matches: list[str] = []
    for match in re.finditer(
        r"^(#{1,6})[ \t]+(.+?)[ \t]*\r?$", structural, re.MULTILINE
    ):
        title = re.sub(r"^\d+(?:\.\d+)*\.?[ \t]+", "", match.group(2)).strip()
        candidate = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        if candidate == anchor:
            matches.append(match.group(0).rstrip("\r"))
    if len(matches) != 1:
        raise ValueError(
            f"diagram anchor {anchor!r} must resolve to exactly one heading; found {len(matches)}"
        )
    return matches[0]


def _canonical_mermaid_block(text: str, anchor: str) -> tuple[bytes, str]:
    heading = _diagram_heading_for_anchor(text, anchor)
    offsets = _heading_section_offsets(text, heading)
    if offsets is None:
        raise ValueError(f"diagram anchor {anchor!r} has no source section")
    _, body_start, end = offsets
    section = text[body_start:end]
    matches = list(
        re.finditer(r"(?ms)^```mermaid[ \t]*\r?\n.*?^```[ \t]*\r?$", section)
    )
    if len(matches) != 1:
        raise ValueError(
            f"diagram anchor {anchor!r} requires exactly one Mermaid block; found {len(matches)}"
        )
    block = matches[0].group(0).replace("\r\n", "\n").replace("\r", "\n")
    canonical = block.rstrip("\n") + "\n"
    return canonical.encode("utf-8"), canonical


def derive_diagram_contract(
    text: str,
    architecture: ArchitectureContract,
    requirements: RequirementsContract,
    coverage: CoverageContract,
    *,
    required: bool,
    grandfathered_schema5: bool,
) -> tuple[DiagramContract, list[str]]:
    """Validate project-specific Mermaid views without making them authority."""

    if grandfathered_schema5:
        return (
            DiagramContract(status="CURRENT", grandfathered_schema5=True),
            [],
        )
    issues: list[str] = []
    try:
        table = contract_table_after_heading(
            text, DIAGRAM_CONTRACT_HEADING, DIAGRAM_CONTRACT_HEADERS
        )
    except ValueError as exc:
        table = None
        issues.append(str(exc))
    if table is None:
        if not required:
            return DiagramContract(status="TEMPLATE"), []
        return DiagramContract(status="INVALID"), [
            f"Missing {DIAGRAM_CONTRACT_HEADING}"
        ]
    if not required and (
        any(unresolved(cell) for row in table.rows for cell in row)
        or all(row[3] in {"NOT_YET_CREATED", "NOT_APPLICABLE"} for row in table.rows)
    ):
        return DiagramContract(status="TEMPLATE"), []

    architecture_id = (
        architecture.selection.architecture_id
        if architecture.selection is not None
        else None
    )
    expected_required = required_diagram_kinds(
        text,
        requirements.requirement_ids,
        coverage.work_kind,
    )

    records: list[DiagramRecord] = []
    seen_ids: set[str] = set()
    seen_kinds: set[str] = set()
    semantic_rows: list[tuple[str, str]] = []
    stale = False
    incomplete = False
    for raw in table.rows:
        (
            diagram_id,
            kind,
            applicability,
            status,
            anchor,
            basis_value,
            referenced_value,
        ) = raw
        if DIAGRAM_ID.fullmatch(diagram_id) is None or diagram_id in seen_ids:
            issues.append(f"Invalid or duplicate diagram ID {diagram_id!r}")
        seen_ids.add(diagram_id)
        if kind not in DIAGRAM_KINDS or kind in seen_kinds:
            issues.append(f"Invalid or duplicate diagram kind {kind!r}")
        seen_kinds.add(kind)
        if applicability not in DIAGRAM_APPLICABILITY:
            issues.append(f"{diagram_id}: invalid applicability {applicability!r}")
        if status not in DIAGRAM_STATUSES:
            issues.append(f"{diagram_id}: invalid status {status!r}")
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", anchor) is None:
            issues.append(f"{diagram_id}: invalid stable anchor {anchor!r}")
        try:
            basis_ids = parse_exact_id_list(
                basis_value, STABLE_CONTRACT_ID, f"{diagram_id} Basis IDs"
            )
        except ValueError as exc:
            issues.append(str(exc))
            basis_ids = []
        try:
            referenced_ids = parse_exact_id_list(
                referenced_value, STABLE_CONTRACT_ID, f"{diagram_id} Referenced IDs"
            )
        except ValueError as exc:
            issues.append(str(exc))
            referenced_ids = []
        must_be_current = kind in expected_required or status == "CURRENT"
        if kind in expected_required and applicability == "NOT_APPLICABLE":
            issues.append(
                f"{diagram_id}: {kind} is required by current canonical records"
            )
        if kind in expected_required and status != "CURRENT":
            incomplete = True
            issues.append(f"{diagram_id}: required {kind} diagram is not CURRENT")
        if status == "STALE":
            stale = True
            issues.append(f"{diagram_id}: rendered project diagram is STALE")

        relationships: tuple[tuple[str, str, str], ...] = ()
        semantic_sha256: str | None = None
        rendered_sha256: str | None = None
        if must_be_current and status == "CURRENT":
            if architecture_id is None or architecture_id not in basis_ids:
                issues.append(
                    f"{diagram_id}: CURRENT diagram must cite the selected ARCH-* basis"
                )
            if not referenced_ids:
                issues.append(f"{diagram_id}: CURRENT diagram requires referenced IDs")
            try:
                rendered_bytes, rendered_text = _canonical_mermaid_block(text, anchor)
                rendered_sha256 = "sha256:" + hashlib.sha256(rendered_bytes).hexdigest()
                body = rendered_text.split("\n", 1)[1].rsplit("\n```", 1)[0]
                if re.search(r"\b(?:TODO|PLACEHOLDER|GENERIC)\b", body, re.IGNORECASE):
                    issues.append(
                        f"{diagram_id}: Mermaid block contains generic placeholder content"
                    )
                parsed_relationships = sorted(
                    {
                        (
                            match.group("from"),
                            clean_cell(match.group("relation")),
                            match.group("to"),
                        )
                        for line in body.splitlines()
                        if (match := DIAGRAM_RELATIONSHIP.fullmatch(line)) is not None
                    }
                )
                relationships = tuple(parsed_relationships)
                if not relationships:
                    issues.append(
                        f"{diagram_id}: Mermaid block has no canonical relationships"
                    )
                endpoint_ids = {
                    identifier
                    for source, _relation, target in relationships
                    for identifier in (source, target)
                }
                if endpoint_ids != set(referenced_ids):
                    issues.append(
                        f"{diagram_id}: Referenced IDs must exactly match Mermaid relationship endpoints"
                    )
                for identifier in referenced_ids:
                    if (
                        re.search(
                            rf"(?<![A-Z0-9-]){re.escape(identifier)}(?![A-Z0-9-])",
                            body,
                        )
                        is None
                    ):
                        issues.append(
                            f"{diagram_id}: referenced ID {identifier} is absent from Mermaid"
                        )
                semantic_payload = {
                    "kind": kind,
                    "basis_ids": sorted(basis_ids),
                    "referenced_ids": sorted(referenced_ids),
                    "relationships": [
                        {"from_id": source, "relation": relation, "to_id": target}
                        for source, relation, target in relationships
                    ],
                }
                semantic_bytes = (
                    json.dumps(
                        semantic_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    + b"\n"
                )
                semantic_sha256 = "sha256:" + hashlib.sha256(semantic_bytes).hexdigest()
                semantic_rows.append((diagram_id, semantic_sha256))
            except ValueError as exc:
                issues.append(f"{diagram_id}: {exc}")
        records.append(
            DiagramRecord(
                diagram_id=diagram_id,
                kind=kind,
                applicability=applicability,
                status=status,
                anchor=anchor,
                basis_ids=tuple(basis_ids),
                referenced_ids=tuple(referenced_ids),
                relationships=relationships,
                semantic_sha256=semantic_sha256,
                rendered_sha256=rendered_sha256,
            )
        )

    missing_kinds = sorted(expected_required - seen_kinds)
    if missing_kinds:
        incomplete = True
        issues.append("Missing required diagram kinds: " + ", ".join(missing_kinds))
    canonical_bytes: bytes | None = None
    canonical_sha256: str | None = None
    if not issues or all(
        issue.endswith("rendered project diagram is STALE") for issue in issues
    ):
        canonical_bytes = (
            json.dumps(
                semantic_rows,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        canonical_sha256 = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
    status_value = (
        "STALE"
        if stale
        else "INVALID"
        if issues and not incomplete
        else "INCOMPLETE"
        if issues
        else "CURRENT"
    )
    return (
        DiagramContract(
            status=status_value,
            architecture_basis_id=architecture_id,
            records=tuple(records),
            canonical_sha256=canonical_sha256,
            canonical_bytes=canonical_bytes,
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
    requirements_contract: RequirementsContract | None = None,
) -> tuple[DesignContract, list[str]]:
    issues: list[str] = []
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
            issues.extend(coverage_issues)
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
            issues.extend(issue for _code, issue in requirement_issues)
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
    example_table, example_ids, example_issues = derive_example_scenario_contract(text)

    both_missing = technology_table is None and execution_table is None and not issues
    if technology_table is None:
        issues.append(f"Missing {TECHNOLOGY_DECISION_HEADING}")
    if execution_table is None:
        issues.append(f"Missing {PROPERTY_EXECUTION_HEADING}")

    technologies: list[TechnologyDecision] = []
    seen_technology_ids: set[str] = set()
    concern_counts: dict[str, int] = {}
    allowed_basis_ids = current_prd_basis_ids(text, design_revision) | set(
        requirements_contract.actor_ids
        + requirements_contract.journey_ids
        + requirements_contract.acceptance_ids
    )
    if technology_table is not None:
        if not technology_table.rows:
            issues.append("Technology decision register has no stored rows")
        for row in technology_table.rows:
            decision = TechnologyDecision(*row)
            technologies.append(decision)
            if TECHNOLOGY_DECISION_ID.fullmatch(decision.decision_id) is None:
                issues.append(
                    f"Invalid technology decision ID {decision.decision_id!r}"
                )
            elif decision.decision_id in seen_technology_ids:
                issues.append(
                    f"Duplicate technology decision ID {decision.decision_id}"
                )
            seen_technology_ids.add(decision.decision_id)
            if TECHNOLOGY_CONCERN.fullmatch(decision.concern) is None:
                issues.append(
                    f"{decision.decision_id}: invalid technology concern {decision.concern!r}"
                )
            concern_counts[decision.concern] = (
                concern_counts.get(decision.concern, 0) + 1
            )
            if any(technology_contract_value_is_unresolved(cell) for cell in row):
                issues.append(
                    f"{decision.decision_id}: unresolved technology decision cell"
                )
            elif not grandfather_approved_v1:
                try:
                    technology_reasoning_parts(decision.alternatives_and_rationale)
                except ValueError as exc:
                    issues.append(f"{decision.decision_id}: {exc}")
            if not unresolved(decision.selection) and not valid_technology_selection(
                decision.selection
            ):
                issues.append(
                    f"{decision.decision_id}: invalid selection {decision.selection!r}; "
                    "use NOT_APPLICABLE — <reason> when the concern does not apply"
                )
            if not unresolved(
                decision.version_policy
            ) and not valid_technology_version_policy(decision.version_policy):
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
            if (
                not unresolved(decision.source)
                and decision.source not in TECHNOLOGY_SOURCES
            ):
                issues.append(
                    f"{decision.decision_id}: invalid source {decision.source!r}"
                )
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
        required_concerns = (
            LEGACY_REQUIRED_TECHNOLOGY_CONCERNS
            if grandfather_approved_v1
            else REQUIRED_TECHNOLOGY_CONCERNS
        )
        for concern in required_concerns:
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
                issues.append(
                    f"Invalid property execution ID {execution.property_id!r}"
                )
            elif execution.property_id in seen_execution_ids:
                issues.append(
                    f"Duplicate property execution ID {execution.property_id}"
                )
            seen_execution_ids.add(execution.property_id)
            if TECHNOLOGY_DECISION_ID.fullmatch(execution.framework_tech_id) is None:
                issues.append(
                    f"{execution.property_id}: invalid Framework TECH ID {execution.framework_tech_id!r}"
                )
            if any(unresolved(cell) for cell in row):
                issues.append(
                    f"{execution.property_id}: unresolved property execution cell"
                )
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

    technology_by_id = {decision.decision_id: decision for decision in technologies}
    if required and not grandfather_approved_v1:
        issues.extend(design_support_record_issues(text, technology_by_id))
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
            if (
                unresolved(requirement_id)
                or unresolved(applicability)
                or unresolved(reason_or_ids)
            ):
                issues.append("Property applicability row contains unresolved cells")
                continue
            if requirement_id in seen_requirements:
                issues.append(
                    f"Duplicate property applicability requirement {requirement_id}"
                )
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
            issues.append(
                f"{property_id}: applicable property definition is unresolved"
            )
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

    declared_property_ids = applicable_property_ids & set(definitions) & execution_ids
    declared_property_test_ids = declared_property_ids | example_ids

    architecture, architecture_issues = _derive_architecture_contract(
        text,
        design_revision,
        set(technology_by_id),
        required=required,
        grandfather_approved_v1=grandfather_approved_v1,
        architecture_disposition=coverage_contract.architecture_disposition,
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
    project_contract, project_contract_issues = derive_project_design_contract(
        text,
        requirements_contract,
        coverage_contract,
        allowed_basis_ids | set(technology_by_id),
        harness,
        (
            set(technology_by_id)
            | {execution.property_id for execution in executions}
            | {row.harness_id for row in harness.rows}
            | (
                {architecture.selection.architecture_id}
                if architecture.selection is not None
                else set()
            )
        ),
        required=required,
        grandfather_approved_v4=grandfather_approved_v1,
    )
    if required:
        issues.extend(project_contract_issues)
    diagram_contract, diagram_issues = derive_diagram_contract(
        text,
        architecture,
        requirements_contract,
        coverage_contract,
        required=required,
        grandfathered_schema5=(
            project_contract.grandfathered_v4 or project_contract.grandfathered_v5
        ),
    )
    if required:
        issues.extend(diagram_issues)

    if not project_contract.grandfathered_v4:
        issues.extend(example_issues)
        trace_issues = architecture_trace_declaration_issues(
            architecture,
            project_contract,
            declared_property_test_ids,
        )
        issues.extend(trace_issues)
        if trace_issues:
            architecture = replace(architecture, status="BLOCKED")

    canonical_sha256: str | None = None
    if (
        technology_table is not None
        and applicability_table is not None
        and definition_table is not None
        and execution_table is not None
        and (harness.canonical_bytes is not None or harness.grandfathered_v1)
        and (change_impact.canonical_bytes is not None or grandfather_approved_v1)
        and (
            project_contract.canonical_bytes is not None
            or project_contract.grandfathered_v4
        )
        and (example_table is not None or project_contract.grandfathered_v4)
        and (
            diagram_contract.canonical_bytes is not None
            or project_contract.grandfathered_v4
            or project_contract.grandfathered_v5
        )
    ):
        architecture_bytes = architecture.canonical_bytes or b""
        harness_bytes = harness.canonical_bytes or b""
        change_impact_bytes = change_impact.canonical_bytes or b""
        project_contract_bytes = project_contract.canonical_bytes or b""
        diagram_contract_bytes = diagram_contract.canonical_bytes or b""
        canonical_sha256 = (
            "sha256:"
            + hashlib.sha256(
                architecture_bytes
                + harness_bytes
                + change_impact_bytes
                + project_contract_bytes
                + diagram_contract_bytes
                + technology_table.canonical_bytes
                + (example_table.canonical_bytes if example_table is not None else b"")
                + applicability_table.canonical_bytes
                + definition_table.canonical_bytes
                + execution_table.canonical_bytes
            ).hexdigest()
        )
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
                max(4, architecture.schema_version)
                if project_contract.grandfathered_v4
                else 5
                if project_contract.grandfathered_v5
                else 6
                if project_contract.grandfathered_v6
                else 7
            ),
            status=status,
            design_revision=design_revision,
            technology_decisions=tuple(technologies),
            property_execution=tuple(executions),
            architecture=architecture,
            harness=harness,
            canonical_sha256=canonical_sha256,
            change_impact=change_impact,
            diagram_contract=diagram_contract,
            project_contract=project_contract,
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
        raise ValueError(
            f"{label} must use PATHS: path; path" + (" or NONE" if allow_none else "")
        )
    items = [item.strip() for item in cleaned[len(prefix) :].split(";")]
    return parse_task_write_set(",".join(items), label)


def validate_application_source_root(
    paths: list[str], project_mode: str | None
) -> None:
    """Compatibility validator for the legacy inferred greenfield source root."""

    if project_mode != "greenfield":
        return
    top_level = {path.split("/", 1)[0].casefold() for path in paths}
    if top_level & {"apps", "src"}:
        raise ValueError(
            "Greenfield application source must use singular app/**; "
            "apps/** and src/** are not allowed"
        )
    if "app" not in top_level:
        raise ValueError(
            "Greenfield Allowed repository write set must include application source under app/**"
        )


def validate_application_source_write_set(
    disposition: ApplicationSourceDisposition,
    paths: list[str],
) -> None:
    """Bind the Gate B source decision to the construction write set."""

    top_level = {path.split("/", 1)[0].casefold() for path in paths}
    if disposition.kind == APPLICATION_SOURCE_NOT_APPLICABLE:
        if top_level & {"app", "apps", "src"}:
            raise ValueError(
                "APPLICATION_SOURCE_PARALLEL_ROOT: infrastructure-only work "
                "cannot authorize app/**, apps/**, or src/**"
            )
        return
    if disposition.kind == APPLICATION_SOURCE_GREENFIELD:
        if top_level & {"apps", "src"}:
            raise ValueError(
                "APPLICATION_SOURCE_PARALLEL_ROOT: greenfield work cannot "
                "authorize apps/** or src/** alongside app/**"
            )
        if not any(
            path_boundary_contains("app/**", path)
            or path_boundary_contains(path, "app/**")
            for path in paths
        ):
            raise ValueError(
                "APPLICATION_SOURCE_DISPOSITION_INVALID: greenfield Allowed "
                "repository write set must include application source under app/**"
            )
        return
    missing = [
        source
        for source in disposition.paths
        if not any(path_boundaries_overlap(source, path) for path in paths)
    ]
    if missing:
        raise ValueError(
            "APPLICATION_SOURCE_DISPOSITION_INVALID: Allowed repository write "
            "set does not cover approved brownfield source roots: " + ", ".join(missing)
        )
    for path in paths:
        if path.split("/", 1)[0].casefold() not in {"app", "apps", "src"}:
            continue
        if not any(
            path_boundaries_overlap(source, path) for source in disposition.paths
        ):
            raise ValueError(
                "APPLICATION_SOURCE_PARALLEL_ROOT: brownfield write set adds "
                "an unapproved parallel application root: " + path
            )


def parse_envelope_targets(value: str) -> list[str]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return []
    prefix = "TARGETS: "
    if not cleaned.startswith(prefix):
        raise ValueError(
            "Allowed external-state targets must use TARGETS: target; target or NONE"
        )
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
        raise ValueError(
            "Local command boundary must use ALLOW_PREFIXES: prefix; prefix"
        )
    values = [item.strip() for item in cleaned[len(prefix) :].split(";")]
    if not values or any(not item for item in values):
        raise ValueError("Local command boundary contains an empty prefix")
    if any(
        SHELL_CONTROL.search(item) or item.startswith(("-", "#")) for item in values
    ):
        raise ValueError("Local command prefixes cannot contain shell-control syntax")
    if len(values) != len(set(values)):
        raise ValueError("Local command boundary contains duplicate prefixes")
    return values


def validation_commands(section: str, task_id: str) -> list[str]:
    fences = re.findall(
        r"^```[^\r\n]*\r?\n(.*?)^```\s*$", section, re.MULTILINE | re.DOTALL
    )
    commands: list[str] = []
    for body in fences:
        for raw_line in body.splitlines():
            command = raw_line.strip()
            if not command or command.startswith("#"):
                continue
            if command.startswith("$ "):
                command = command[2:].strip()
            if SHELL_CONTROL.search(command):
                raise ValueError(
                    f"{task_id}: Validation command contains shell-control syntax"
                )
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
    if (
        pure.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        return None
    return value


def has_symlink_component(root: Path, relative: str) -> bool:
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


MAX_REQUIRED_FILES = 512
MAX_REQUIRED_FILE_BYTES = 16 * 1024 * 1024
MAX_PROJECT_SOURCE_BYTES = 64 * 1024 * 1024
BINARY_REQUIRED_SUFFIXES = frozenset({".png"})


def safe_read_required_binary(
    ctx: Context, relative: str, *, required: bool = True
) -> bytes | None:
    """Read one explicitly supported binary package file within integrity bounds."""

    cached = ctx.source_file_bytes.get(relative)
    if cached is not None:
        return cached
    if validate_relative_path(relative) is None:
        ctx.error("MANIFEST_UNSAFE_PATH", f"Unsafe project-relative path: {relative!r}")
        return None
    if has_symlink_component(ctx.root, relative):
        ctx.error(
            "REQUIRED_FILE_SYMLINK", "Required path contains a symbolic link", relative
        )
        return None
    path = ctx.root / relative
    if not path.exists():
        if required:
            ctx.error("REQUIRED_FILE_MISSING", "Required file is missing", relative)
        return None
    if not path.is_file():
        ctx.error(
            "REQUIRED_FILE_NOT_REGULAR", "Required path is not a regular file", relative
        )
        return None
    remaining = MAX_PROJECT_SOURCE_BYTES - ctx.source_bytes_read
    if remaining <= 0:
        ctx.error(
            "PROJECT_SOURCE_LIMIT",
            f"Required project files exceed the {MAX_PROJECT_SOURCE_BYTES}-byte aggregate limit",
            relative,
        )
        return None
    read_limit = min(MAX_REQUIRED_FILE_BYTES, remaining)
    try:
        with path.open("rb") as stream:
            raw = stream.read(read_limit + 1)
    except OSError as exc:
        ctx.error("REQUIRED_FILE_UNREADABLE", f"Unable to read file: {exc}", relative)
        return None
    if len(raw) > read_limit:
        code = (
            "REQUIRED_FILE_TOO_LARGE"
            if read_limit == MAX_REQUIRED_FILE_BYTES
            else "PROJECT_SOURCE_LIMIT"
        )
        limit = (
            MAX_REQUIRED_FILE_BYTES
            if code == "REQUIRED_FILE_TOO_LARGE"
            else MAX_PROJECT_SOURCE_BYTES
        )
        scope = "per-file" if code == "REQUIRED_FILE_TOO_LARGE" else "aggregate"
        ctx.error(
            code,
            f"Required project file exceeds the {limit}-byte {scope} limit",
            relative,
        )
        return None
    ctx.source_bytes_read += len(raw)
    ctx.source_file_bytes[relative] = raw
    return raw


def safe_read_text(ctx: Context, relative: str, *, required: bool = True) -> str | None:
    cached = ctx.texts.get(relative)
    if cached is not None:
        return cached
    if validate_relative_path(relative) is None:
        ctx.error("MANIFEST_UNSAFE_PATH", f"Unsafe project-relative path: {relative!r}")
        return None
    if has_symlink_component(ctx.root, relative):
        ctx.error(
            "REQUIRED_FILE_SYMLINK", "Required path contains a symbolic link", relative
        )
        return None
    path = ctx.root / relative
    if not path.exists():
        if required:
            ctx.error("REQUIRED_FILE_MISSING", "Required file is missing", relative)
        return None
    if not path.is_file():
        ctx.error(
            "REQUIRED_FILE_NOT_REGULAR", "Required path is not a regular file", relative
        )
        return None
    remaining = MAX_PROJECT_SOURCE_BYTES - ctx.source_bytes_read
    if remaining <= 0:
        ctx.error(
            "PROJECT_SOURCE_LIMIT",
            f"Required project text exceeds the {MAX_PROJECT_SOURCE_BYTES}-byte aggregate limit",
            relative,
        )
        return None
    read_limit = min(MAX_REQUIRED_FILE_BYTES, remaining)
    try:
        with path.open("rb") as stream:
            raw = stream.read(read_limit + 1)
    except OSError as exc:
        ctx.error(
            "REQUIRED_FILE_UNREADABLE", f"Unable to read UTF-8 text: {exc}", relative
        )
        return None
    if len(raw) > read_limit:
        code = (
            "REQUIRED_FILE_TOO_LARGE"
            if read_limit == MAX_REQUIRED_FILE_BYTES
            else "PROJECT_SOURCE_LIMIT"
        )
        limit = (
            MAX_REQUIRED_FILE_BYTES
            if code == "REQUIRED_FILE_TOO_LARGE"
            else MAX_PROJECT_SOURCE_BYTES
        )
        scope = "per-file" if code == "REQUIRED_FILE_TOO_LARGE" else "aggregate"
        ctx.error(
            code,
            f"Required project text exceeds the {limit}-byte {scope} limit",
            relative,
        )
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        ctx.error(
            "REQUIRED_FILE_UNREADABLE", f"Unable to read UTF-8 text: {exc}", relative
        )
        return None
    ctx.source_file_bytes[relative] = raw
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    ctx.source_bytes_read += len(raw)
    ctx.presentation_texts[relative] = text
    canonical_text = (
        strip_generated_summary(text) if relative in DOCUMENT_SUMMARY_FILES else text
    )
    ctx.texts[relative] = canonical_text
    return canonical_text


def bounded_prd_snapshot(
    root: Path, expected_sha256: str | None = None
) -> tuple[str, str]:
    """Read one normalized, size-bounded PRD snapshot and bind it by digest."""

    snapshot_context = Context(root=root.resolve())
    text = safe_read_text(snapshot_context, PRD_FILE)
    if text is None or snapshot_context.has_errors:
        raise ValueError("Unable to read a bounded PRD snapshot")
    raw_text = snapshot_context.presentation_texts.get(PRD_FILE, text)
    digest = (
        "sha256:"
        + hashlib.sha256(
            canonical_bytes_without_generated_summary(raw_text)
        ).hexdigest()
    )
    if expected_sha256 is not None and (
        re.fullmatch(r"sha256:[0-9a-f]{64}", expected_sha256) is None
        or digest != expected_sha256
    ):
        raise ValueError("PRD snapshot changed after project inspection")
    return text, digest


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
        raise ValueError(
            f"Expected exactly one heading {heading!r}; found {len(matches)}"
        )
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


def _owner_locator_for_heading(
    text: str,
    *,
    key: str,
    label: str,
    heading: str,
    required: bool = True,
) -> dict[str, Any]:
    """Resolve a brief locator through the Engine's canonical heading parser."""

    span = _heading_title_span(text, heading)
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


def _derive_gate_b_decision_inventory(
    design_contract: DesignContract,
    requirements_revision: str,
    design_revision: str,
    authorization_id: str,
    *,
    status: str,
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    grouped: dict[str, list[TechnologyDecision]] = {
        domain: [] for domain in TECHNICAL_DOMAIN_ORDER
    }
    for technology in design_contract.technology_decisions:
        grouped[_owner_technical_domain(technology.concern)].append(technology)

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
        rationales: list[str] = []
        alternatives: list[str] = []
        for technology in technologies:
            try:
                rationale, rejected = technology_reasoning_parts(
                    technology.alternatives_and_rationale
                )
            except ValueError as exc:
                if status == "READY":
                    issues.append(f"{technology.decision_id}: {exc}")
                continue
            rationales.append(rationale)
            alternatives.append(rejected)
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
                0, f"Whole-system architecture: {selection.selected_candidate}"
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
            selections.append(
                f"Harness Profile: {len(design_contract.harness.rows)} recorded checks"
            )
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
        evidence_ids = [item.evidence_id for item in evidence]
        maturity = "SOURCE_VERIFIED" if evidence_ids else "PLANNED_AFTER_APPROVAL"
        evidence_status = (
            "SOURCE_VERIFIED — " + ", ".join(evidence_ids)
            if evidence_ids
            else "PLANNED_AFTER_APPROVAL — this canonical design decision has not been observed in a deployed environment."
        )
        decisions.append(
            {
                "decision_id": decision_id,
                "domain": domain,
                "title": title,
                "selection": "; ".join(_unique_owner_text(selections)),
                "source": "Canonical Design-7 architecture and technology records",
                "maturity": maturity,
                "owner_effect": owner_effect,
                "why": " ".join(_unique_owner_text(rationales)),
                "alternatives": " ".join(_unique_owner_text(alternatives)),
                "tradeoff": " ".join(_unique_owner_text(tradeoffs)),
                "risk_and_mitigation": " ".join(_unique_owner_text(safeguards)),
                "evidence_status": evidence_status,
                "reconsider_when": " ".join(_unique_owner_text(reconsider)),
                "basis_ids": basis_ids,
                "evidence_ids": evidence_ids,
                "source_locator_keys": source_keys,
            }
        )
    projection = {
        "schema_version": 1,
        "kind": "GATE_B",
        "status": status,
        "required_domains": list(TECHNICAL_DOMAIN_ORDER),
        "decisions": decisions,
    }
    finalized, validation_issues = finalize_owner_decision_inventory(projection)
    return finalized, [*issues, *validation_issues]


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
    """Derive one fail-closed gate view and its complete decision inventory."""

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
        sections = [
            _owner_decision_section(
                "GATE-A-OUTCOME",
                "Outcome, users, and first useful journey",
                [
                    "Outcome: " + gate_a_card.get("Outcome", "Not yet recorded."),
                    "Owner and users: "
                    + gate_a_card.get("Owner and users", "Not yet recorded."),
                    "First-release journey: "
                    + ("; ".join(readable_journeys) or "Not yet recorded."),
                ],
                [requirements_revision, *intake_contract.basis_ids],
            ),
            _owner_decision_section(
                "GATE-A-BOUNDARY",
                "First-release boundary",
                [
                    "Scope and non-goals: "
                    + gate_a_card.get("Scope and non-goals", "Not yet recorded."),
                    "Data and access: "
                    + gate_a_card.get("Data boundary", "Not yet recorded.")
                    + " "
                    + gate_a_card.get(
                        "Identity/security boundary", "Not yet recorded."
                    ),
                ],
                [requirements_revision, *requirements_contract.requirement_ids],
            ),
            _owner_decision_section(
                "GATE-A-SUCCESS",
                "Success, resilience, Region, and cost",
                [
                    "Success measures: "
                    + gate_a_card.get(
                        "Measurable requirement/acceptance IDs", "Not yet recorded."
                    ),
                    "Recovery, Region, and cost: "
                    + gate_a_card.get("Failure/recovery", "Not yet recorded.")
                    + "; "
                    + gate_a_card.get("Environment/Region", "Not yet recorded.")
                    + "; "
                    + gate_a_card.get("Cost posture", "Not yet recorded."),
                ],
                [requirements_revision, *requirements_contract.acceptance_ids],
            ),
            _owner_decision_section(
                "GATE-A-RISK",
                "Assumptions, risks, and change impact",
                [
                    "Assumptions: " + gate_a_card.get("Assumptions", "None recorded."),
                    "Open decisions or findings: "
                    + gate_a_analysis.get(
                        "Open blocking decision IDs", "None recorded."
                    )
                    + "; "
                    + gate_a_analysis.get(
                        "Open blocking finding IDs", "None recorded."
                    ),
                    "Brownfield preservation: "
                    + gate_a_card.get(
                        "Brownfield baseline and preservation", "Not applicable."
                    ),
                ],
                [requirements_revision, *requirements_contract.requirement_ids],
            ),
        ]
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
        sections = [
            _owner_decision_section(
                "GATE-B-EXECUTIVE",
                "Executive decision",
                [
                    "Recommendation: "
                    + (
                        selection.selected_candidate
                        if selection is not None
                        else "Not yet selected."
                    ),
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
                    "Construction boundary: "
                    + envelope.get("Authorized outcome", "Not yet recorded."),
                ],
                [
                    requirements_revision,
                    design_revision,
                    authorization_id,
                    *([selection.architecture_id] if selection is not None else []),
                ],
            )
        ]
        technical_groups = [
            {
                "domain": decision["domain"],
                "decisions": [
                    {
                        "decision_id": decision["decision_id"],
                        "decision": decision["title"],
                        "owner_effect": decision["owner_effect"],
                        "selection": decision["selection"],
                        "requirement_basis": ", ".join(decision["basis_ids"]),
                        "why": decision["why"],
                        "alternatives": decision["alternatives"],
                        "tradeoff": decision["tradeoff"],
                        "risk_and_mitigation": decision["risk_and_mitigation"],
                        "evidence_status": decision["evidence_status"],
                        "reconsider_when": decision["reconsider_when"],
                        "basis_ids": decision["basis_ids"],
                        "evidence_ids": decision["evidence_ids"],
                        "source_locator_keys": decision["source_locator_keys"],
                    }
                ],
            }
            for decision in inventory.get("decisions", [])
        ]
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
        locator_specs = (
            ("technical-plan", "Technical plan", "14. Architecture overview"),
            ("technology-register", "Technology decisions", "Technology decisions"),
            ("selected-architecture", "Selected architecture", "Selected architecture"),
            ("components", "Component design", "15. Component design"),
            ("interfaces", "Interfaces and contracts", "16. Interfaces and contracts"),
            (
                "data-lifecycle",
                "Data model and lifecycle",
                "17. Data model and lifecycle",
            ),
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
        )
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


def derive_owner_answer_confirmation(
    prd_text: str,
    intake_contract: IntakeFoundationContract,
) -> dict[str, Any]:
    """Project only the latest canonical normalized intake response."""

    if not intake_contract.normalized_responses:
        return answer_confirmation()
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
        if question is None:
            return answer_confirmation(status="BLOCKED")
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
        if not value:
            return answer_confirmation(status="BLOCKED")
        recorded.append(f"{question.prompt}: {value}")
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


def current_gate_receipt_contract(
    root: Path, report: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the exact receipt proposal for the currently pending owner gate."""

    lifecycle_state = str(report.get("lifecycle_state", ""))
    next_prompt = str(report.get("next_prompt", ""))
    if lifecycle_state == "WAITING_GATE_A" and next_prompt == "INTAKE-20":
        gate = "GATE_A"
        owner_action_kind = "APPROVE_GATE_A"
    elif lifecycle_state == "WAITING_GATE_B" and next_prompt == "DESIGN-20":
        gate = "GATE_B"
        owner_action_kind = "APPROVE_GATE_B"
    else:
        raise ValueError("The project is not waiting for a Gate A or Gate B receipt")

    try:
        basis = report.get("basis")
        if not isinstance(basis, Mapping):
            raise ValueError("Current gate basis is missing")
        text, _ = bounded_prd_snapshot(
            root, clean_cell(basis.get("prd_snapshot_sha256", ""))
        )
        requirements_revision = clean_cell(basis.get("requirements_revision", ""))
        if REQ_ID.fullmatch(requirements_revision) is None:
            raise ValueError("Current requirements revision is invalid")
        if gate == "GATE_A":
            gate_a_agent = table_after_heading(
                text, "### Gate A — agent analysis record"
            )
            gate_a_card = table_after_heading(text, "### Gate A — readiness card")
            assumption_ids = parse_exact_id_list(
                gate_a_agent.get("Proposed assumption IDs required to proceed", ""),
                re.compile(r"ASM-\d+"),
                "Gate A proposed assumptions",
            )
            assumptions = ", ".join(assumption_ids) if assumption_ids else "NONE"
            cost_posture = clean_cell(gate_a_card.get("Cost posture", ""))
            parse_cost_posture(cost_posture)
            fixed_lines = [
                "APPROVE REQUIREMENTS GATE A",
                f"Requirements revision: {requirements_revision}",
                f"Cost posture: {cost_posture}",
                f"Accepted assumptions: {assumptions}",
            ]
            fields = {
                "requirements_revision": requirements_revision,
                "cost_posture": cost_posture,
                "accepted_assumptions": assumptions,
            }
        else:
            design_revision = clean_cell(basis.get("design_revision", ""))
            authorization_id = clean_cell(basis.get("construction_authorization", ""))
            if DES_ID.fullmatch(design_revision) is None:
                raise ValueError("Current design revision is invalid")
            if AUTH_ID.fullmatch(authorization_id) is None:
                raise ValueError("Current construction authorization is invalid")
            envelope_digest = canonical_envelope_sha256(text)
            fixed_lines = [
                "APPROVE PRD AND CONSTRUCTION GATE B",
                f"Requirements revision: {requirements_revision}",
                f"Design revision: {design_revision}",
                f"Construction authorization: {authorization_id}",
                f"Construction envelope SHA-256: {envelope_digest}",
                "Use the proposed construction envelope above.",
            ]
            fields = {
                "requirements_revision": requirements_revision,
                "design_revision": design_revision,
                "construction_authorization": authorization_id,
                "construction_envelope_sha256": envelope_digest,
            }
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("The current pending gate contract is invalid") from exc

    return {
        "gate": gate,
        "lifecycle_state": lifecycle_state,
        "next_prompt": next_prompt,
        "owner_action_kind": owner_action_kind,
        "fixed_lines": fixed_lines,
        "fields": fields,
        "expected_receipt": "\n".join([*fixed_lines, "Approver: <name/handle>"]),
    }


def validate_gate_receipt_candidate(
    candidate: str, contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one owner receipt without writing or echoing rejected content."""

    common = {
        "schema_version": 1,
        "gate": contract["gate"],
        "lifecycle_state": contract["lifecycle_state"],
        "next_prompt": contract["next_prompt"],
        "owner_action_kind": contract["owner_action_kind"],
        "formal_receipt_required": True,
        "project_state_changed": False,
        "expected_receipt": contract["expected_receipt"],
    }

    def rejected(code: str, message: str) -> dict[str, Any]:
        return {
            **common,
            "status": "FAIL",
            "candidate_accepted": False,
            "errors": [{"code": code, "message": message}],
        }

    if len(candidate) > MAX_GATE_RECEIPT_CHARACTERS:
        return rejected(
            "GATE_RECEIPT_TOO_LONG",
            "The owner receipt exceeds the bounded receipt length",
        )
    normalized = re.sub(r"\r+\n", "\n", candidate).replace("\r", "\n").strip()
    if not normalized or any(
        ord(character) < 32 and character != "\n" for character in normalized
    ):
        return rejected(
            "GATE_RECEIPT_FORMAT_INVALID",
            "The owner receipt contains invalid or missing text",
        )
    lines = normalized.split("\n")
    fixed_lines = contract.get("fixed_lines")
    if not isinstance(fixed_lines, list) or not all(
        isinstance(line, str) for line in fixed_lines
    ):
        return rejected(
            "GATE_RECEIPT_CONTRACT_INVALID",
            "The current gate receipt contract is invalid",
        )
    if len(lines) != len(fixed_lines) + 1:
        return rejected(
            "GATE_RECEIPT_FORMAT_INVALID",
            "The owner receipt must contain the complete exact ordered block",
        )
    if lines[:-1] != fixed_lines:
        return rejected(
            "GATE_RECEIPT_BASIS_MISMATCH",
            "The owner receipt does not match the current exact gate proposal",
        )
    approver_prefix = "Approver: "
    if not lines[-1].startswith(approver_prefix):
        return rejected(
            "GATE_RECEIPT_FORMAT_INVALID",
            "The final owner receipt line must be the Approver field",
        )
    approver = lines[-1][len(approver_prefix) :]
    if not explicit_human_approver(approver):
        return rejected(
            "GATE_RECEIPT_APPROVER_INVALID",
            "The approver must be an explicit human owner identity",
        )
    return {
        **common,
        "status": "PASS",
        "candidate_accepted": True,
        "normalized_receipt": normalized,
        "fields": {**dict(contract.get("fields", {})), "approver": approver},
        "errors": [],
    }


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


def unselected_selection(value: str, allowed: set[str]) -> bool:
    """Return whether a selection cell still represents an unanswered choice."""

    cleaned = clean_cell(value)
    if unresolved(cleaned):
        return True
    parts = [part.strip() for part in str(value).strip().split("/")]
    if len(parts) <= 1:
        return False
    choices: list[str] = []
    for part in parts:
        match = re.fullmatch(r"`?([a-z][a-z0-9-]*)`?", part)
        if match is None:
            return False
        choices.append(match.group(1))
    return len(choices) == len(allowed) and set(choices) == allowed


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
        ctx.error(
            "MANIFEST_SCHEMA", "Unsupported manifest schema_version", MANIFEST_FILE
        )
    version = manifest.get("bootstrap_version")
    if not isinstance(version, str) or re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        ctx.error(
            "MANIFEST_VERSION",
            "bootstrap_version must be semantic version text",
            MANIFEST_FILE,
        )

    files = manifest.get("required_files")
    if not isinstance(files, list):
        ctx.error(
            "MANIFEST_REQUIRED_FILES", "required_files must be an array", MANIFEST_FILE
        )
        return
    if len(files) > MAX_REQUIRED_FILES:
        ctx.error(
            "MANIFEST_REQUIRED_FILES_LIMIT",
            f"required_files exceeds the {MAX_REQUIRED_FILES}-entry limit",
            MANIFEST_FILE,
        )
        return
    seen: set[str] = set()
    folded: set[str] = set()
    for item in files:
        relative = validate_relative_path(item)
        if relative is None:
            ctx.error(
                "MANIFEST_UNSAFE_PATH",
                f"Unsafe required_files entry: {item!r}",
                MANIFEST_FILE,
            )
            continue
        if relative in seen or relative.casefold() in folded:
            ctx.error(
                "MANIFEST_DUPLICATE_PATH",
                f"Duplicate required path: {relative}",
                MANIFEST_FILE,
            )
            continue
        seen.add(relative)
        folded.add(relative.casefold())
        if PurePosixPath(relative).suffix.lower() in BINARY_REQUIRED_SUFFIXES:
            safe_read_required_binary(ctx, relative)
        else:
            safe_read_text(ctx, relative)
    missing_mandatory = sorted(MANDATORY_REQUIRED_FILES - seen)
    if missing_mandatory:
        ctx.error(
            "MANIFEST_REQUIRED_BASELINE",
            "Manifest omits mandatory control files: " + ", ".join(missing_mandatory),
            MANIFEST_FILE,
        )
    missing_controls = sorted(CONTROL_HASH_FILES - seen)
    if missing_controls:
        ctx.error(
            "MANIFEST_CONTROL_REQUIRED_FILES",
            "Manifest control files must also be required files: "
            + ", ".join(missing_controls),
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
    if (
        not isinstance(source_hashes, dict)
        or set(source_hashes) != expected_source_paths
    ):
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
                source_bytes = ctx.source_file_bytes.get(relative)
                if source_bytes is None:
                    source_text = ctx.presentation_texts.get(relative) or ctx.texts.get(
                        relative
                    )
                    if source_text is None:
                        continue
                    source_bytes = source_text.encode("utf-8")
                actual = hashlib.sha256(source_bytes).hexdigest()
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
        if (
            not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
        ):
            ctx.error(
                "MANIFEST_CONTROL_HASHES",
                f"Invalid SHA-256 for trusted control {relative}",
                MANIFEST_FILE,
            )
            continue
        if has_symlink_component(ctx.root, relative):
            continue
        control_text = ctx.texts.get(relative)
        if control_text is None:
            continue
        actual = hashlib.sha256(control_text.encode("utf-8")).hexdigest()
        if actual != expected:
            ctx.error(
                "CONTROL_HASH_MISMATCH",
                f"Trusted runtime control hash mismatch: expected {expected}, observed {actual}",
                relative,
            )


def validate_prompt_pack(
    ctx: Context, manifest: dict[str, Any], state: dict[str, Any]
) -> None:
    text = ctx.texts.get(PROMPT_FILE) or safe_read_text(ctx, PROMPT_FILE)
    if text is None:
        return
    version_match = re.search(
        r"^\*\*Pack version:\*\*\s*(\d+\.\d+\.\d+)\s*$", text, re.MULTILINE
    )
    if version_match is None:
        ctx.error(
            "PROMPT_VERSION_MISSING", "Prompt pack version is missing", PROMPT_FILE
        )
    else:
        versions = {
            str(manifest.get("bootstrap_version")),
            str(state.get("bootstrap_version")),
            version_match.group(1),
        }
        if len(versions) != 1:
            ctx.error(
                "BOOTSTRAP_VERSION_DRIFT",
                f"Version values disagree: {sorted(versions)}",
            )

    expected = manifest.get("canonical_prompt_ids")
    actual = re.findall(r"^##\s+([A-Z]+-\d{2})\s+", text, re.MULTILINE)
    if not isinstance(expected, list) or not all(
        isinstance(item, str) for item in expected
    ):
        ctx.error(
            "PROMPT_IDS_MANIFEST",
            "canonical_prompt_ids must be an array of strings",
            MANIFEST_FILE,
        )
    elif actual != expected:
        ctx.error(
            "PROMPT_IDS_DRIFT",
            f"Prompt headings do not match manifest order: {actual}",
            PROMPT_FILE,
        )
    elif len(actual) != len(set(actual)):
        ctx.error(
            "PROMPT_IDS_DUPLICATE", "Canonical prompt IDs must be unique", PROMPT_FILE
        )


def validate_placeholders(ctx: Context) -> None:
    if ctx.template_source:
        return
    excluded = {
        MANIFEST_FILE,
        "bootstrap.py",
        "scripts/bootstrap_doctor.py",
        "scripts/fastlane_project_identity.py",
    }
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
        ctx.error(
            "STATE_SCHEMA",
            f"State keys must be exactly {sorted(expected_top)}",
            STATE_FILE,
        )
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
            ctx.error(
                "STATE_SCHEMA",
                f"{name} keys must be exactly {sorted(expected)}",
                STATE_FILE,
            )

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
            ctx.error(
                "PROJECT_IDENTITY", f"project.{key} must be non-empty text", STATE_FILE
            )
    name = project.get("name")
    if (
        isinstance(name, str)
        and name.strip()
        and not (ctx.template_source and name == PROJECT_NAME_TOKEN)
    ):
        try:
            canonical_name = normalize_project_name(name)
        except ValueError as exc:
            ctx.error("PROJECT_IDENTITY", str(exc), STATE_FILE)
        else:
            if canonical_name != name:
                ctx.error(
                    "PROJECT_IDENTITY",
                    "project.name must use its canonical normalized value",
                    STATE_FILE,
                )
    region = project.get("region")
    if (
        isinstance(region, str)
        and region.strip()
        and not (ctx.template_source and region == "{{AWS_REGION}}")
    ):
        try:
            canonical_region = normalize_aws_region(region)
        except ValueError as exc:
            ctx.error("PROJECT_IDENTITY", str(exc), STATE_FILE)
        else:
            if canonical_region != region:
                ctx.error(
                    "PROJECT_IDENTITY",
                    "project.region must use its canonical lowercase value",
                    STATE_FILE,
                )
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
            ctx.error(
                "PROJECT_VOCABULARY", f"Invalid project.{key}: {value!r}", STATE_FILE
            )
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
    if not isinstance(plan_state, str) or plan_state not in {
        "UNINITIALIZED",
        "CURRENT",
        "STALE",
    }:
        ctx.error(
            "STATE_RUN",
            "plan_state must be UNINITIALIZED, CURRENT, or STALE",
            STATE_FILE,
        )
    if (plan is None) != (plan_state == "UNINITIALIZED"):
        ctx.error(
            "STATE_RUN", "plan_revision and plan_state are inconsistent", STATE_FILE
        )
    active = execution.get("active_tasks")
    if not isinstance(active, list) or not all(
        isinstance(item, str) and TASK_ID.fullmatch(item) for item in active
    ):
        ctx.error("STATE_RUN", "active_tasks must contain only TASK IDs", STATE_FILE)
    elif len(active) != len(set(active)):
        ctx.error("STATE_RUN", "active_tasks contains duplicates", STATE_FILE)
    attempts = execution.get("attempts")
    if not isinstance(attempts, dict) or any(
        TASK_ID.fullmatch(str(key)) is None
        or not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for key, value in (attempts.items() if isinstance(attempts, dict) else [])
    ):
        ctx.error(
            "STATE_RUN",
            "attempts must map TASK IDs to non-negative integers",
            STATE_FILE,
        )
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
            ctx.error(
                "STATE_RUN",
                "IDLE execution cannot have a coordinator, run ID, run mode, or active tasks",
                STATE_FILE,
            )
    else:
        if run_id is None or coordinator is None or execution.get("mode") == "NONE":
            ctx.error(
                "STATE_RUN",
                "A non-IDLE execution requires a coordinator, run ID, and run mode",
                STATE_FILE,
            )
        expected_basis_keys = {
            "requirements_revision",
            "design_revision",
            "construction_authorization",
        }
        if not isinstance(basis, dict) or set(basis) != expected_basis_keys:
            ctx.error(
                "STATE_RUN",
                "A non-IDLE execution requires a complete revision basis",
                STATE_FILE,
            )
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
            ctx.error(
                "STATE_RUN", "last_checkpoint fields must be explicit", STATE_FILE
            )
    if run_state in {"CHECKPOINTED", "BLOCKED", "COMPLETE"} and checkpoint is None:
        ctx.error(
            "STATE_RUN", f"{run_state} execution requires a checkpoint", STATE_FILE
        )
    if run_state == "COMPLETE" and execution.get("active_tasks"):
        ctx.error(
            "STATE_RUN", "COMPLETE execution cannot have active tasks", STATE_FILE
        )
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
        ctx.error(
            "BROWNFIELD_PRD_BASELINE", f"Expected exactly one {heading!r}", PRD_FILE
        )
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
                ctx.error(
                    "BROWNFIELD_PRD_BASELINE",
                    f"Duplicate brownfield field {row[0]!r}",
                    PRD_FILE,
                )
            baseline[row[0]] = row[1]
    missing = sorted(BROWNFIELD_BASELINE_FIELDS - set(baseline))
    if missing:
        ctx.error(
            "BROWNFIELD_PRD_BASELINE",
            "Brownfield baseline is missing fields: " + ", ".join(missing),
            PRD_FILE,
        )
    unresolved_fields = sorted(
        field
        for field in BROWNFIELD_BASELINE_FIELDS
        if not explicit_value(baseline.get(field, ""), allow_none=True)
    )
    if unresolved_fields:
        ctx.error(
            "BROWNFIELD_PRD_BASELINE",
            "Brownfield baseline has unresolved fields: "
            + ", ".join(unresolved_fields),
            PRD_FILE,
        )

    preservation_rows = [
        row
        for row in tables[1][2:]
        if row and re.fullmatch(r"PRES-\d+", row[0]) is not None
    ]
    if not preservation_rows:
        ctx.error(
            "BROWNFIELD_PRD_PRESERVATION",
            "Brownfield approval requires at least one explicit PRES record",
            PRD_FILE,
        )
    for row in preservation_rows:
        if len(row) < 5 or any(
            not explicit_value(value, allow_none=False) for value in row[1:5]
        ):
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
            envelope.get("Authorization expiry or completion condition", "")
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
            parse_future_expiry(envelope.get("AWS authorization validity", ""))
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
            parse_future_expiry(envelope.get("AWS authorization validity", ""))
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


def derive_req_aws_materiality(
    gate_a_agent: Mapping[str, str],
    requirements_revision: str,
    *,
    required: bool,
    grandfather_current_gate_a: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Derive the REQ-10 AWS materiality contract without inventing AWS facts."""

    raw_materiality = clean_cell(gate_a_agent.get("AWS Core materiality", ""))
    raw_basis = clean_cell(gate_a_agent.get("AWS materiality basis IDs", ""))
    raw_discovery = clean_cell(gate_a_agent.get("AWS Core discovery IDs", ""))
    raw_unresolved = clean_cell(
        gate_a_agent.get("Unresolved material AWS fact IDs", "")
    )
    issues: list[str] = []

    if raw_materiality not in AWS_CORE_MATERIALITY_VALUES:
        if grandfather_current_gate_a:
            return (
                {
                    "materiality": "OPTIONAL",
                    "status": "GRANDFATHERED",
                    "source": "LEGACY_UNRECORDED",
                    "basis_ids": [requirements_revision]
                    if REQ_ID.fullmatch(requirements_revision)
                    else [],
                    "discovery_ids": [],
                    "unresolved_fact_ids": [],
                },
                [],
            )
        if not required:
            return (
                {
                    "materiality": "OPTIONAL",
                    "status": "UNASSESSED",
                    "source": "CURRENT_PRD",
                    "basis_ids": [],
                    "discovery_ids": [],
                    "unresolved_fact_ids": [],
                },
                [],
            )
        issues.append(
            "AWS Core materiality must be exactly REQUIRED, OPTIONAL, or NOT_MATERIAL"
        )

    def ids_or_none(
        value: str, pattern: re.Pattern[str], label: str
    ) -> tuple[list[str], bool]:
        if value == "NONE" or value.startswith("NONE — "):
            reason = value[6:].strip() if value.startswith("NONE — ") else ""
            if value.startswith("NONE — ") and not explicit_value(reason):
                raise ValueError(f"{label} NONE form requires a concrete reason")
            return [], True
        return _canonical_id_list(value, pattern, label), False

    basis_ids: list[str] = []
    discovery_ids: list[str] = []
    unresolved_ids: list[str] = []
    basis_none = discovery_none = unresolved_none = False
    try:
        basis_ids, basis_none = ids_or_none(
            raw_basis, STABLE_CONTRACT_ID, "AWS materiality basis IDs"
        )
    except ValueError as exc:
        issues.append(str(exc))
    try:
        discovery_ids, discovery_none = ids_or_none(
            raw_discovery, AWS_DISCOVERY_ID, "AWS Core discovery IDs"
        )
    except ValueError as exc:
        issues.append(str(exc))
    try:
        unresolved_ids, unresolved_none = ids_or_none(
            raw_unresolved, STABLE_CONTRACT_ID, "Unresolved material AWS fact IDs"
        )
    except ValueError as exc:
        issues.append(str(exc))

    basis_none_with_reason = raw_basis.startswith("NONE — ")
    discovery_none_with_reason = raw_discovery.startswith("NONE — ")
    if (
        not basis_none
        and requirements_revision
        and requirements_revision not in basis_ids
    ):
        issues.append(f"AWS materiality basis IDs must include {requirements_revision}")
    if raw_materiality == "REQUIRED":
        if basis_none or not basis_ids:
            issues.append("REQUIRED AWS materiality needs current basis IDs")
        if discovery_none or not discovery_ids:
            issues.append("REQUIRED AWS materiality needs current AWS-DISC evidence")
        if not unresolved_none or unresolved_ids:
            issues.append(
                "REQUIRED AWS materiality cannot retain unresolved AWS fact IDs at Gate A"
            )
    elif raw_materiality == "OPTIONAL":
        if basis_none and not basis_none_with_reason:
            issues.append(
                "OPTIONAL AWS materiality needs basis IDs or NONE with a reason"
            )
        if discovery_none and not discovery_none_with_reason:
            issues.append(
                "OPTIONAL AWS materiality needs AWS-DISC IDs or NONE with a reason"
            )
        if not unresolved_none or unresolved_ids:
            issues.append(
                "OPTIONAL AWS materiality cannot retain unresolved material AWS fact IDs"
            )
    elif raw_materiality == "NOT_MATERIAL":
        if not basis_none or basis_ids or not basis_none_with_reason:
            issues.append(
                "NOT_MATERIAL requires AWS materiality basis IDs NONE with a reason"
            )
        if not discovery_none or discovery_ids or not discovery_none_with_reason:
            issues.append(
                "NOT_MATERIAL requires AWS Core discovery IDs NONE with a reason"
            )
        if not unresolved_none or unresolved_ids:
            issues.append("NOT_MATERIAL cannot retain unresolved AWS fact IDs")

    return (
        {
            "materiality": raw_materiality
            if raw_materiality in AWS_CORE_MATERIALITY_VALUES
            else "OPTIONAL",
            "status": "CURRENT" if not issues else "BLOCKED",
            "source": "CURRENT_PRD",
            "basis_ids": basis_ids,
            "discovery_ids": discovery_ids,
            "unresolved_fact_ids": unresolved_ids,
        },
        issues,
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
    intake_repository_mode = selections.get("mode")
    setup_state = state.get("setup") if isinstance(state.get("setup"), dict) else {}
    if (
        intake_repository_mode is None
        and not ctx.template_source
        and setup_state.get("status")
        not in {"UNCONFIGURED_TEMPLATE", "{{SETUP_STATUS}}"}
    ):
        intake_repository_mode = "greenfield"
    intake_contract, intake_issues = derive_intake_foundation_contract(
        text,
        intake_repository_mode,
        grandfather_current_gate_a=grandfather_approved_v1_requirements,
    )
    for code, issue in intake_issues:
        ctx.error(code, issue, PRD_FILE)
    if gate_a_ready_or_current and intake_contract.status != "READY_FOR_REQUIREMENTS":
        ctx.error(
            "INTAKE_FOUNDATION_REQUIRED",
            "Gate A requires a complete owner-grounded intake foundation and no pending card",
            PRD_FILE,
        )
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


def path_boundary_contains(allowed: str, requested: str) -> bool:
    allowed = allowed.casefold()
    requested = requested.casefold()
    allowed_base = allowed[:-3] if allowed.endswith("/**") else allowed
    requested_base = requested[:-3] if requested.endswith("/**") else requested
    if allowed.endswith("/**"):
        return requested_base == allowed_base or requested_base.startswith(
            allowed_base + "/"
        )
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
    return any(
        requested.startswith(allowed + separator) for separator in ("/", ":", "#")
    )


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
        boundary_mode, explicit_task_ids = parse_task_boundary(
            envelope.get("Task boundary", "")
        )
        command_prefixes = parse_command_prefixes(
            envelope.get("Local command boundary", "")
        )
        github_repo = parse_github_constraints(
            envelope.get("GitHub repository, branch, and merge constraints", ""),
            envelope.get("GitHub boundary", ""),
        )
        parse_future_expiry(
            envelope.get("Authorization expiry or completion condition", "")
        )
    except (ValueError, TypeError) as exc:
        if str(exc) == "Construction authorization is expired":
            ctx.error(
                "GATE_B_AUTHORITY_EXPIRED",
                "Gate B authority expired; the owner must reapprove the current "
                "design boundary before any new local or AWS operation",
                PRD_FILE,
            )
        else:
            ctx.error(
                "GATE_B_ENVELOPE",
                f"Cannot validate task boundaries: {exc}",
                PRD_FILE,
            )
        return
    if len(tasks) > maximum_tasks:
        ctx.error(
            "TASK_LIMIT_EXCEEDED",
            f"{len(tasks)} tasks exceed AUTH maximum {maximum_tasks}",
            TASKS_FILE,
        )
    if snapshot_workers > maximum_workers:
        ctx.error(
            "WORKER_LIMIT_EXCEEDED", "TASKS Maximum workers exceeds AUTH", TASKS_FILE
        )
    if maximum_workers != 1:
        ctx.error(
            "GATE_B_ENVELOPE",
            "Current AUTH must permit exactly one parallel worker",
            PRD_FILE,
        )
    if snapshot.get("Baseline commit") != envelope.get("Authorized baseline commit"):
        ctx.error(
            "TASK_BASELINE_DRIFT",
            "TASKS baseline commit does not match AUTH",
            TASKS_FILE,
        )
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
    if [item.casefold() for item in task_protected] != [
        item.casefold() for item in authorized_protected
    ]:
        ctx.error(
            "TASK_BASELINE_DRIFT",
            "TASKS protected dirty paths do not match AUTH",
            TASKS_FILE,
        )

    execution = (
        state.get("execution") if isinstance(state.get("execution"), dict) else {}
    )
    if (
        execution.get("mode") == "AUTONOMOUS"
        and envelope.get("Autonomous construction") != "ALLOWED"
    ):
        ctx.error(
            "AUTONOMY_OUTSIDE_AUTH",
            "AUTONOMOUS run is not allowed by Gate B",
            STATE_FILE,
        )
    if not tasks:
        return

    github_boundary = envelope.get("GitHub boundary", "NONE")
    aws_boundary = envelope.get("AWS boundary", "NONE")
    protected = snapshot.get("Protected dirty paths", "NONE")
    try:
        protected_paths = (
            []
            if protected == "NONE"
            else parse_task_write_set(protected, "Protected dirty paths")
        )
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
            if not any(
                path_boundary_contains(allowed, requested) for allowed in allowed_writes
            ):
                ctx.error(
                    "TASK_OUTSIDE_WRITE_BOUNDARY",
                    f"{task.task_id} write {requested!r} is outside AUTH",
                    TASKS_FILE,
                )
            if any(
                path_boundaries_overlap(requested, excluded)
                for excluded in excluded_writes
            ):
                ctx.error(
                    "TASK_EXCLUDED_WRITE",
                    f"{task.task_id} overlaps excluded path {requested!r}",
                    TASKS_FILE,
                )
            if task.status in {"READY", "IN_PROGRESS"} and any(
                path_boundaries_overlap(requested, dirty) for dirty in protected_paths
            ):
                ctx.error(
                    "TASK_PROTECTED_DIRTY_OVERLAP",
                    f"{task.task_id} overlaps protected dirty path {requested!r}",
                    TASKS_FILE,
                )
        for target in external_targets:
            if not any(
                external_target_contains(allowed, target)
                for allowed in allowed_external
            ):
                ctx.error(
                    "TASK_EXTERNAL_STATE_BOUNDARY",
                    f"{task.task_id} external target {target!r} is outside AUTH",
                    TASKS_FILE,
                )
        if boundary_mode == "EXPLICIT" and task.task_id not in explicit_task_ids:
            ctx.error(
                "TASK_OUTSIDE_TASK_BOUNDARY",
                f"{task.task_id} is not listed by AUTH",
                TASKS_FILE,
            )

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
                commands = validation_commands(
                    sections.get("Validation", ""), task.task_id
                )
                for command in commands:
                    if not any(
                        command_matches_prefix(command, prefix)
                        for prefix in command_prefixes
                    ):
                        ctx.error(
                            "TASK_COMMAND_BOUNDARY",
                            f"{task.task_id} command {command!r} is outside AUTH",
                            TASKS_FILE,
                        )
            except ValueError as exc:
                ctx.error("TASK_COMMAND_BOUNDARY", str(exc), TASKS_FILE)
        try:
            if task.attempt_budget > maximum_attempts:
                ctx.error(
                    "TASK_ATTEMPT_BOUNDARY",
                    f"{task.task_id} attempt budget exceeds AUTH",
                    TASKS_FILE,
                )
        except (KeyError, ValueError):
            pass
        aws_mode = clean_cell(task.metadata.get("AWS mode", "NONE")).upper()
        allowed_aws_modes = {
            "NONE": {"NONE"},
            "DOCS_ONLY": {"NONE", "DOCS_ONLY"},
            "READ_ONLY": {"NONE", "DOCS_ONLY"},
            "MUTATE_LISTED_RESOURCES": {"NONE", "DOCS_ONLY"},
        }
        if aws_mode not in allowed_aws_modes.get(aws_boundary, set()):
            ctx.error(
                "TASK_AWS_BOUNDARY",
                f"{task.task_id} AWS mode exceeds the local-task ceiling",
                TASKS_FILE,
            )
        issue = clean_cell(task.metadata.get("GitHub issue", "PENDING_SYNC"))
        if github_boundary in {"NONE", "READ_ONLY"} and issue != "PENDING_SYNC":
            ctx.error(
                "TASK_GITHUB_BOUNDARY",
                f"{task.task_id} has a GitHub write result outside AUTH",
                TASKS_FILE,
            )
        elif github_boundary not in {"NONE", "READ_ONLY"} and issue != "PENDING_SYNC":
            match = GITHUB_ISSUE_URL.fullmatch(issue)
            if (
                match is None
                or github_repo is None
                or match.group("repo").casefold() != github_repo.casefold()
            ):
                ctx.error(
                    "TASK_GITHUB_BOUNDARY",
                    f"{task.task_id} issue URL does not match the authorized GitHub repository",
                    TASKS_FILE,
                )

    active = [task for task in tasks if task.status == "IN_PROGRESS"]
    if len(active) > min(maximum_workers, snapshot_workers):
        ctx.error(
            "WORKER_LIMIT_EXCEEDED",
            "IN_PROGRESS tasks exceed the active worker limit",
            TASKS_FILE,
        )
    for index, first in enumerate(active):
        first_writes = parse_task_write_set(first.metadata["Write set"], first.task_id)
        first_external = parse_task_external_state(
            first.metadata["External state"], first.task_id
        )
        for second in active[index + 1 :]:
            second_writes = parse_task_write_set(
                second.metadata["Write set"], second.task_id
            )
            second_external = parse_task_external_state(
                second.metadata["External state"], second.task_id
            )
            conflict = any(
                path_boundaries_overlap(a, b)
                for a in first_writes
                for b in second_writes
            )
            conflict |= any(
                external_targets_overlap(a, b)
                for a in first_external
                for b in second_external
            )
            conflict |= clean_cell(first.metadata["AWS mode"]).upper() == "MUTATION"
            conflict |= clean_cell(second.metadata["AWS mode"]).upper() == "MUTATION"
            if conflict:
                ctx.error(
                    "ACTIVE_TASK_CONFLICT",
                    f"{first.task_id} conflicts with {second.task_id}",
                    TASKS_FILE,
                )


def git_read(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return subprocess.run(
        [
            resolve_trusted_git(root),
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
        else parse_task_write_set(
            dirty_value, f"{checkpoint_id} checkpoint Dirty paths"
        )
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
            raise ValueError(
                f"{checkpoint_id}: must be the unique newest checkpoint row"
            )
        row = matching[0]
        if row.run_id != snapshot.get("Active run ID"):
            raise ValueError(
                f"{checkpoint_id}: checkpoint run does not match the snapshot"
            )
        if not explicit_timestamp(row.recorded_at):
            raise ValueError(
                f"{checkpoint_id}: checkpoint time must be ISO 8601 with timezone"
            )
        for prefix, expected in (
            ("REQ", snapshot.get("Requirements revision", "")),
            ("DES", snapshot.get("Design revision", "")),
            ("AUTH", snapshot.get("Construction authorization", "")),
        ):
            if re.findall(rf"\b{prefix}-\d{{4,}}\b", row.basis) != [expected]:
                raise ValueError(
                    f"{checkpoint_id}: checkpoint REQ/DES/AUTH basis is not current"
                )
        parse_checkpoint_git_receipt(tasks_text, checkpoint_id)
        if not explicit_value(row.task_outcomes):
            raise ValueError(
                f"{checkpoint_id}: task outcomes and attempts are unresolved"
            )
        for task in tasks:
            token = re.compile(
                rf"(?<![A-Za-z0-9-]){re.escape(task.task_id)}(?![A-Za-z0-9-])"
            )
            segments = [
                segment.strip()
                for segment in re.split(r"[;\n]", row.task_outcomes)
                if token.search(segment) is not None
            ]
            if (
                len(segments) != 1
                or re.search(rf"\b{re.escape(task.status)}\b", segments[0]) is None
            ):
                raise ValueError(
                    f"{checkpoint_id}: outcome for {task.task_id} is not current"
                )
            attempt = re.compile(
                rf"\battempts?(?:\s+used)?\s*[=:]\s*{task.attempts_used}"
                rf"(?:\s*/\s*{task.attempt_budget})?(?!\s*/\s*\d)\b",
                re.IGNORECASE,
            )
            if attempt.search(segments[0]) is None:
                raise ValueError(
                    f"{checkpoint_id}: attempts for {task.task_id} are not current"
                )
        if (
            not explicit_value(row.evidence_and_external)
            or re.search(r"\bevidence\b", row.evidence_and_external, re.IGNORECASE)
            is None
            or re.search(r"\bexternal\b", row.evidence_and_external, re.IGNORECASE)
            is None
        ):
            raise ValueError(
                f"{checkpoint_id}: evidence and external actions are unresolved"
            )
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
                raise ValueError(
                    f"{checkpoint_id}: evidence for {task.task_id} is incomplete"
                )
        if (
            not explicit_value(row.blockers_and_next)
            or re.search(r"\bblockers?\b", row.blockers_and_next, re.IGNORECASE) is None
            or re.search(r"\bnext\b", row.blockers_and_next, re.IGNORECASE) is None
        ):
            raise ValueError(
                f"{checkpoint_id}: blockers and next action are unresolved"
            )
        structural_verify = (
            without_fenced_code(verify_text) if verify_text is not None else ""
        )
        if (
            re.search(
                rf"(?<![A-Za-z0-9-]){re.escape(checkpoint_id)}(?![A-Za-z0-9-])",
                structural_verify,
            )
            is None
        ):
            raise ValueError(
                f"{checkpoint_id}: checkpoint is not referenced in VERIFY.md"
            )
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
    if (
        resolved.returncode != 0
        or resolved.stdout.decode("ascii", errors="replace").strip() != baseline
    ):
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
    for label, value in (
        ("Baseline commit", baseline),
        ("Last known-green commit", known_green),
    ):
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
        baseline_result = git_read(
            ctx.root, "rev-parse", "--verify", f"{baseline}^{{commit}}"
        )
        green_result = git_read(
            ctx.root, "rev-parse", "--verify", f"{known_green}^{{commit}}"
        )
        checkpoint_result = (
            git_read(
                ctx.root, "rev-parse", "--verify", f"{checkpoint_commit}^{{commit}}"
            )
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
        checkpoint_result.stdout.decode("ascii", errors="replace").strip()
        != resolved_green
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
        tracked = git_read(
            ctx.root, "diff", "--name-only", "-z", "--relative", "HEAD", "--", "."
        )
        untracked = git_read(
            ctx.root, "ls-files", "--others", "--exclude-standard", "-z", "--", "."
        )
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
        if not any(
            path_boundary_contains(boundary, path) for path in observed_nonledger
        )
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


LEGACY_TASK_AWS_MODE = re.compile(
    r"^(?P<task>TASK-\d+): invalid AWS mode '(?:READ_ONLY|MUTATION)'$"
)


def record_task_graph_validation_errors(ctx: Context, message: str) -> None:
    """Project legacy authenticated task modes as a fail-closed replan."""

    issues = [line.strip() for line in message.splitlines() if line.strip()]
    legacy = [line for line in issues if LEGACY_TASK_AWS_MODE.fullmatch(line)]
    remaining = [line for line in issues if line not in legacy]
    if legacy:
        task_ids = sorted(
            {
                match.group("task")
                for line in legacy
                if (match := LEGACY_TASK_AWS_MODE.fullmatch(line)) is not None
            }
        )
        ctx.error(
            "TASK_AWS_MODE_REPLAN_REQUIRED",
            "Legacy authenticated task AWS mode requires replanning local work "
            f"for {', '.join(task_ids)}; preserve every DONE completion and "
            "append-only VERIFY evidence row rather than rewriting observed evidence",
            TASKS_FILE,
        )
    if remaining:
        ctx.error("TASK_GRAPH_INVALID", "\n".join(remaining), TASKS_FILE)


def validate_tasks(
    ctx: Context,
    state: dict[str, Any],
    prd_fields: dict[str, str],
    envelope: dict[str, str],
    requirements_contract: RequirementsContract,
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
        ctx.error(
            "TASK_SNAPSHOT",
            "Active execution snapshot fields must be exact: " + "; ".join(details),
            TASKS_FILE,
        )

    run_state = snapshot.get("Run state", "")
    if run_state not in SNAPSHOT_RUN_STATES:
        ctx.error("TASK_SNAPSHOT", f"Invalid Run state {run_state!r}", TASKS_FILE)
    try:
        snapshot_workers = int(snapshot.get("Maximum workers", ""))
        if snapshot_workers < 1:
            raise ValueError
    except ValueError:
        ctx.error(
            "TASK_SNAPSHOT", "Maximum workers must be a positive integer", TASKS_FILE
        )
    active_run_id = snapshot.get("Active run ID", "")
    coordinator = snapshot.get("Coordinator", "")
    if run_state == "NOT_STARTED":
        if active_run_id != "NONE" or coordinator != "UNASSIGNED":
            ctx.error(
                "TASK_SNAPSHOT",
                "NOT_STARTED requires no run ID and an unassigned coordinator",
                TASKS_FILE,
            )
    else:
        if RUN_ID.fullmatch(active_run_id) is None or coordinator in {
            "",
            "NONE",
            "UNASSIGNED",
            "TODO",
        }:
            ctx.error(
                "TASK_SNAPSHOT",
                "An active or checkpointed run requires a RUN ID and coordinator",
                TASKS_FILE,
            )
    current_wave = snapshot.get("Current wave", "")
    if current_wave != "NONE" and re.fullmatch(r"[1-9]\d*", current_wave) is None:
        ctx.error(
            "TASK_SNAPSHOT",
            "Current wave must be NONE or a positive integer",
            TASKS_FILE,
        )
    checkpoint = snapshot.get("Last checkpoint", "")
    if run_state in {"PAUSED", "BLOCKED", "COMPLETE"}:
        if CHECKPOINT_ID.fullmatch(checkpoint) is None:
            ctx.error(
                "TASK_SNAPSHOT", f"{run_state} requires a checkpoint ID", TASKS_FILE
            )
    elif checkpoint != "NONE":
        ctx.error(
            "TASK_SNAPSHOT",
            f"{run_state or 'unknown run state'} must not claim a checkpoint",
            TASKS_FILE,
        )
    try:
        if snapshot.get("Protected dirty paths") != "NONE":
            parse_task_write_set(
                snapshot.get("Protected dirty paths", ""), "Protected dirty paths"
            )
    except ValueError as exc:
        ctx.error("TASK_SNAPSHOT", str(exc), TASKS_FILE)
    if not explicit_value(snapshot.get("Next safe action", ""), allow_none=False):
        ctx.error("TASK_SNAPSHOT", "Next safe action must be explicit", TASKS_FILE)
    if snapshot.get("Gate B state") == "APPROVED_FOR_CONSTRUCTION":
        for key in ("Baseline commit", "Last known-green commit"):
            if (
                re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", snapshot.get(key, ""))
                is None
            ):
                ctx.error(
                    "TASK_SNAPSHOT",
                    f"Current Gate B requires a full lowercase {key}",
                    TASKS_FILE,
                )

    raw_plan = snapshot.get("Task-plan revision", "")
    summary.plan_state = snapshot.get("Task-plan state", "")
    summary.plan_revision = None if raw_plan == "UNINITIALIZED" else raw_plan
    if (
        summary.plan_revision is not None
        and PLAN_ID.fullmatch(summary.plan_revision) is None
    ):
        ctx.error(
            "TASK_PLAN_STATE",
            "Task-plan revision must be UNINITIALIZED or PLAN-nnnn",
            TASKS_FILE,
        )
    if summary.plan_state not in {"UNINITIALIZED", "CURRENT", "STALE"}:
        ctx.error(
            "TASK_PLAN_STATE",
            "Task-plan state must be UNINITIALIZED, CURRENT, or STALE",
            TASKS_FILE,
        )
    if summary.plan_revision is None and summary.plan_state != "UNINITIALIZED":
        ctx.error(
            "TASK_PLAN_STATE",
            "UNINITIALIZED revision requires UNINITIALIZED plan state",
            TASKS_FILE,
        )
    if summary.plan_revision is not None and summary.plan_state == "UNINITIALIZED":
        ctx.error(
            "TASK_PLAN_STATE",
            "Initialized revision cannot have UNINITIALIZED plan state",
            TASKS_FILE,
        )
    execution = (
        state.get("execution") if isinstance(state.get("execution"), dict) else {}
    )
    lifecycle = (
        state.get("lifecycle") if isinstance(state.get("lifecycle"), dict) else {}
    )
    if summary.plan_revision != execution.get("plan_revision"):
        ctx.error(
            "STATE_TASK_DRIFT",
            "Task-plan revision does not match bootstrap state",
            TASKS_FILE,
        )
    if summary.plan_state != execution.get("plan_state"):
        ctx.error(
            "STATE_TASK_DRIFT",
            "Task-plan state does not match bootstrap state",
            TASKS_FILE,
        )
    snapshot_pairs = {
        "Requirements revision": "requirements_revision",
        "Design revision": "design_revision",
        "Construction authorization": "construction_authorization",
        "Gate B state": "gate_b",
    }
    for snapshot_key, lifecycle_key in snapshot_pairs.items():
        if snapshot.get(snapshot_key) != lifecycle.get(lifecycle_key):
            ctx.error(
                "STATE_TASK_DRIFT",
                f"{snapshot_key} does not match lifecycle state",
                TASKS_FILE,
            )

    run_map = {
        "IDLE": "NOT_STARTED",
        "RUNNING": "RUNNING",
        "CHECKPOINTED": "PAUSED",
        "BLOCKED": "BLOCKED",
        "COMPLETE": "COMPLETE",
    }
    execution_state = (
        execution.get("state") if isinstance(execution.get("state"), str) else ""
    )
    expected_run = run_map.get(execution_state)
    if expected_run is not None and snapshot.get("Run state") != expected_run:
        ctx.error(
            "STATE_TASK_DRIFT", "Run state does not match bootstrap state", TASKS_FILE
        )
    expected_run_id = execution.get("run_id") or "NONE"
    if snapshot.get("Active run ID") != expected_run_id:
        ctx.error(
            "STATE_TASK_DRIFT",
            "Active run ID does not match bootstrap state",
            TASKS_FILE,
        )
    expected_coordinator = execution.get("coordinator") or "UNASSIGNED"
    if snapshot.get("Coordinator") != expected_coordinator:
        ctx.error(
            "STATE_TASK_DRIFT", "Coordinator does not match bootstrap state", TASKS_FILE
        )

    verify_text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    try:
        approved_tech_ids = {
            decision.decision_id for decision in design_contract.technology_decisions
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
        record_task_graph_validation_errors(ctx, str(exc))
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
    try:
        requirement_rules = (
            task_requirement_rules(ctx.texts.get(PRD_FILE, ""), requirements_contract)
            if summary.plan_state == "CURRENT"
            else {}
        )
        requirement_evidence, requirement_evidence_issues = (
            task_requirement_evidence_dispositions(
                verify_text,
                {
                    "Requirements revision": snapshot.get("Requirements revision", ""),
                    "Design revision": snapshot.get("Design revision", ""),
                    "Construction authorization": snapshot.get(
                        "Construction authorization", ""
                    ),
                },
                requirement_rules,
            )
        )
        requirement_coverage = derive_task_requirement_coverage(
            tasks,
            summary.plan_state,
            requirement_rules,
            requirement_evidence,
        )
    except ValueError as exc:
        ctx.error("TASK_REQUIREMENT_TRACE_INVALID", str(exc), TASKS_FILE)
    else:
        summary.requirement_coverage = {
            record.requirement_id: record.to_dict()
            for record in requirement_coverage.records
        }
        summary.missing_requirement_ids = list(
            requirement_coverage.missing_requirement_ids
        )
        summary.requirement_coverage_complete = bool(
            summary.plan_state == "CURRENT"
            and not requirement_coverage.trace_issues
            and not requirement_evidence_issues
            and not requirement_coverage.evidence_issues
            and not requirement_coverage.missing_requirement_ids
        )
        if requirement_coverage.trace_issues:
            ctx.error(
                "TASK_REQUIREMENT_TRACE_INVALID",
                "\n".join(requirement_coverage.trace_issues),
                TASKS_FILE,
            )
        all_evidence_issues = [
            *requirement_evidence_issues,
            *requirement_coverage.evidence_issues,
        ]
        if all_evidence_issues:
            ctx.error(
                "TASK_REQUIREMENT_COVERAGE_EVIDENCE_INVALID",
                "\n".join(all_evidence_issues),
                VERIFY_FILE,
            )
        if requirement_coverage.missing_requirement_ids:
            ctx.error(
                "TASK_REQUIREMENT_COVERAGE",
                "CURRENT task plan does not cover approved requirement IDs: "
                + ", ".join(requirement_coverage.missing_requirement_ids),
                TASKS_FILE,
            )

    if summary.plan_revision is None and tasks:
        ctx.error(
            "TASK_PLAN_STATE",
            "UNINITIALIZED task plan contains task blocks",
            TASKS_FILE,
        )
    if summary.plan_revision is not None and not tasks:
        ctx.error(
            "TASK_PLAN_STATE",
            "Initialized task plan contains no task blocks",
            TASKS_FILE,
        )
    if (
        summary.plan_state == "CURRENT"
        and prd_fields.get("gate_b") != "APPROVED_FOR_CONSTRUCTION"
    ):
        ctx.error(
            "TASK_PLAN_STATE", "CURRENT task plan requires current Gate B", TASKS_FILE
        )
    if summary.plan_state == "STALE" and any(
        task.status in {"READY", "IN_PROGRESS"} for task in tasks
    ):
        ctx.error(
            "TASK_PLAN_STATE",
            "STALE task plan cannot contain runnable or active tasks",
            TASKS_FILE,
        )

    summary.statuses = {task.task_id: task.status for task in tasks}
    summary.active = sorted(
        task.task_id for task in tasks if task.status == "IN_PROGRESS"
    )
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
        if isinstance(state_active_value, list)
        and all(isinstance(item, str) for item in state_active_value)
        else []
    )
    if summary.active != state_active:
        ctx.error(
            "STATE_TASK_DRIFT",
            "active_tasks does not match IN_PROGRESS task records",
            STATE_FILE,
        )
    task_attempts = {task.task_id: task.attempts_used for task in tasks}
    if execution.get("attempts") != task_attempts:
        ctx.error(
            "STATE_TASK_DRIFT", "attempt counters do not match task records", STATE_FILE
        )
    state_checkpoint = execution.get("last_checkpoint")
    expected_checkpoint = (
        state_checkpoint.get("id") if isinstance(state_checkpoint, dict) else "NONE"
    )
    if snapshot.get("Last checkpoint") != expected_checkpoint:
        ctx.error(
            "STATE_TASK_DRIFT",
            "Last checkpoint does not match bootstrap state",
            TASKS_FILE,
        )

    basis = execution.get("basis")
    if basis is not None:
        expected_basis = {
            "requirements_revision": prd_fields.get("requirements_revision"),
            "design_revision": prd_fields.get("design_revision"),
            "construction_authorization": prd_fields.get("construction_authorization"),
        }
        if basis != expected_basis:
            ctx.error(
                "RUN_BASIS_STALE",
                "Execution basis does not match current PRD revisions",
                STATE_FILE,
            )
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
            reconcile_worktree=execution_state
            in {"CHECKPOINTED", "BLOCKED", "COMPLETE"},
        )
    return summary


def validate_release_decision_record(ctx: Context) -> dict[str, str]:
    """Validate the release state and its durable evidence acknowledgment."""

    relative = VERIFY_FILE
    text = ctx.texts.get(relative) or safe_read_text(ctx, relative)
    if text is None:
        return {"release_state": "NOT_READY", "active_evidence_cutoff": "NONE"}
    heading = "## Current release decision"
    matches = list(re.finditer(rf"^{re.escape(heading)}[ \t]*$", text, re.MULTILINE))
    if len(matches) != 1:
        ctx.error("RELEASE_DECISION", f"Expected exactly one {heading!r}", relative)
        return {"release_state": "NOT_READY", "active_evidence_cutoff": "NONE"}
    section = text[matches[0].end() :]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    decisions = re.findall(r"^- Release state:\s*`([^`]+)`\s*$", section, re.MULTILINE)
    release_state = decisions[0] if len(decisions) == 1 else "NOT_READY"
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
        release_state = "NOT_READY"
    cutoff_rows = re.findall(
        r"^- Active evidence cutoff:\s*(?P<value>[^\r\n]+?)\s*$",
        section,
        re.MULTILINE,
    )
    cutoff = clean_cell(cutoff_rows[0]) if len(cutoff_rows) == 1 else "NONE"
    if len(cutoff_rows) != 1 or (
        cutoff not in {"TODO", "NONE"} and re.fullmatch(r"EV-\d{4,}", cutoff) is None
    ):
        ctx.error(
            "RELEASE_EVIDENCE_CUTOFF",
            "Active evidence cutoff must appear exactly once and be TODO, NONE, "
            "or one canonical EV-* ID",
            relative,
        )
        cutoff = "NONE"
    return {
        "release_state": release_state,
        "active_evidence_cutoff": cutoff,
    }


def validate_release_decision(ctx: Context) -> str:
    """Compatibility wrapper returning only the validated release state."""

    return validate_release_decision_record(ctx)["release_state"]


AWS_LIFECYCLE_INTENT_VALUES = {"NONE", "RESIDUAL_REVIEW", "TEARDOWN", "RETAIN"}
AWS_LIFECYCLE_INTENT_SOURCE = re.compile(r"owner-message MSG-AWS-LIFECYCLE-\d{4,}")


def validate_aws_lifecycle_intent_record(ctx: Context) -> dict[str, Any]:
    """Validate the atomic, non-authorizing owner lifecycle-intent record."""

    legacy_none = {
        "value": "NONE",
        "source": "NONE",
        "recorded_at": "NONE",
        "provenance_status": "LEGACY_NONE",
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
    }
    text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    if text is None:
        return legacy_none
    heading = "## Current release decision"
    headings = list(re.finditer(rf"^{re.escape(heading)}[ \t]*$", text, re.MULTILINE))
    if len(headings) != 1:
        # validate_release_decision_record owns the structural diagnostic.
        return legacy_none
    section = text[headings[0].end() :]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    value_lines = list(
        re.finditer(
            r"^- AWS lifecycle intent:\s*`([^`]+)`\s*$",
            section,
            re.MULTILINE,
        )
    )
    source_lines = list(
        re.finditer(
            r"^- AWS lifecycle intent source:\s*`([^`]+)`\s*$",
            section,
            re.MULTILINE,
        )
    )
    recorded_lines = list(
        re.finditer(
            r"^- AWS lifecycle intent recorded at:\s*`([^`]+)`\s*$",
            section,
            re.MULTILINE,
        )
    )
    if not value_lines and not source_lines and not recorded_lines:
        return legacy_none
    if (
        len(value_lines) == 1
        and value_lines[0].group(1) == "NONE"
        and not source_lines
        and not recorded_lines
    ):
        return legacy_none
    exact_record = re.search(
        r"^- AWS lifecycle intent:\s*`([^`]+)`\s*\r?\n"
        r"- AWS lifecycle intent source:\s*`([^`]+)`\s*\r?\n"
        r"- AWS lifecycle intent recorded at:\s*`([^`]+)`\s*$",
        section,
        re.MULTILINE,
    )
    if (
        len(value_lines) != 1
        or len(source_lines) != 1
        or len(recorded_lines) != 1
        or exact_record is None
    ):
        ctx.error(
            "AWS_LIFECYCLE_INTENT_PROVENANCE",
            "AWS lifecycle intent must be one exact ordered value/source/recorded-at triple",
            VERIFY_FILE,
        )
        return legacy_none
    value, source, recorded_at = exact_record.groups()
    valid = value in AWS_LIFECYCLE_INTENT_VALUES
    if value == "NONE":
        valid = valid and source == "NONE" and recorded_at == "NONE"
    else:
        valid = bool(
            valid
            and AWS_LIFECYCLE_INTENT_SOURCE.fullmatch(source)
            and _iso_datetime(recorded_at) is not None
        )
    if not valid:
        ctx.error(
            "AWS_LIFECYCLE_INTENT_PROVENANCE",
            "Non-NONE AWS lifecycle intent requires an owner-message source and timezone-aware recorded-at value; NONE requires NONE provenance",
            VERIFY_FILE,
        )
        return legacy_none
    return {
        "value": value,
        "source": source,
        "recorded_at": recorded_at,
        "provenance_status": "CURRENT",
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
    }


def validate_aws_lifecycle_intent(ctx: Context) -> str:
    """Compatibility wrapper returning only the validated intent value."""

    return str(validate_aws_lifecycle_intent_record(ctx)["value"])


def derive_teardown_route(
    intent: str,
    teardown_sequence: Mapping[str, Any],
    residual_disposition: Mapping[str, Any] | None = None,
) -> tuple[str, str] | None:
    """Route residual review and teardown without treating intent as authority."""

    status = clean_cell(teardown_sequence.get("status", "NOT_ACTIVE"))
    if status == "ACTION_TERMINAL_REQUIRED":
        return "AWS_TEARDOWN_ACTION_TERMINAL", "AWS-50"
    if status == "POST_ACTION_REVIEW":
        return "AWS_RESIDUAL_REVIEW", "AWS-40"
    if status == "BLOCKED":
        return "AWS_RESIDUAL_REVIEW_BLOCKED", "STOP"
    disposition = residual_disposition or {}
    disposition_status = clean_cell(disposition.get("status", "NOT_APPLICABLE"))
    disposition_value = clean_cell(disposition.get("value", "NONE"))
    if status in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}:
        if disposition_status != "CURRENT":
            return "AWS_RESIDUALS_REMAIN", "STOP"
        if disposition_status == "CURRENT":
            if disposition_value == "RETAIN":
                return "AWS_RESIDUALS_RETAINED", "STOP"
            if disposition_value == "INVESTIGATE":
                return "AWS_RESIDUAL_REVIEW", "AWS-40"
            if disposition_value == "REMOVE":
                return (
                    ("WAITING_AWS_TEARDOWN_AUTH", "AWS-50")
                    if status == "READY_FOR_TEARDOWN"
                    else ("AWS_RESIDUAL_REVIEW", "AWS-40")
                )
    if intent == "NONE":
        return None
    if intent == "RESIDUAL_REVIEW":
        if status == "VERIFIED_CLEAN":
            return "AWS_RESIDUAL_REVIEW_COMPLETE", "STOP"
        return "AWS_RESIDUAL_REVIEW", "AWS-40"
    if intent == "TEARDOWN":
        if status == "VERIFIED_CLEAN":
            return (
                ("AWS_TEARDOWN_COMPLETE", "STOP")
                if teardown_sequence.get("post_action_bound") is True
                else ("AWS_RESIDUAL_REVIEW_COMPLETE", "STOP")
            )
        return "AWS_RESIDUAL_REVIEW", "AWS-40"
    return None


def derive_aws_residual_disposition(
    intent_record: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one non-authorizing residual choice to the latest AWS-40 evidence."""

    base: dict[str, Any] = {
        "status": "NOT_APPLICABLE",
        "value": "NONE",
        "basis_evidence_id": "NONE",
        "basis_status": "NONE",
        "basis_observed_at": "NONE",
        "recorded_at": clean_cell(intent_record.get("recorded_at", "NONE")),
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
        "issues": [],
    }
    basis_status = clean_cell(teardown_sequence.get("status", "NOT_ACTIVE"))
    intent = clean_cell(intent_record.get("value", "NONE"))
    if basis_status not in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}:
        if intent == "RETAIN":
            return {
                **base,
                "status": "INVALID",
                "issues": ["RETAIN requires current residual-resource evidence"],
            }
        return base
    basis_observed_at = clean_cell(teardown_sequence.get("observed_at", ""))
    basis_time = _iso_datetime(basis_observed_at)
    recorded_at = clean_cell(intent_record.get("recorded_at", ""))
    record_time = _iso_datetime(recorded_at)
    projection = {
        **base,
        "status": "PENDING",
        "basis_evidence_id": clean_cell(teardown_sequence.get("evidence_id", "NONE")),
        "basis_status": basis_status,
        "basis_observed_at": basis_observed_at or "NONE",
        "recorded_at": recorded_at or "NONE",
    }
    if basis_time is None:
        return {
            **projection,
            "status": "INVALID",
            "issues": ["Residual disposition basis lacks an exact observed timestamp"],
        }
    mapped = {
        "RETAIN": "RETAIN",
        "RESIDUAL_REVIEW": "INVESTIGATE",
        "TEARDOWN": "REMOVE",
    }.get(intent)
    if (
        mapped is None
        or intent_record.get("provenance_status") != "CURRENT"
        or record_time is None
    ):
        return projection
    if basis_status == "RESIDUALS_REMAIN" and record_time <= basis_time:
        return projection
    if (
        basis_status == "READY_FOR_TEARDOWN"
        and intent != "TEARDOWN"
        and record_time <= basis_time
    ):
        return projection
    return {**projection, "status": "CURRENT", "value": mapped}


def aws_deployment_teardown_sequence_conflict(
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> bool:
    """Reject simultaneous open deployment and teardown journal epochs."""

    deployment_status = clean_cell(deployment_sequence.get("status", ""))
    teardown_status = clean_cell(teardown_sequence.get("status", ""))
    deployment_open = deployment_status not in {"", "NONE", "NOT_ACTIVE", "CONSUMED"}
    teardown_open = teardown_status not in {
        "",
        "NONE",
        "NOT_ACTIVE",
        "VERIFIED_CLEAN",
        "RESIDUALS_REMAIN",
    }
    return deployment_open and teardown_open


def release_lifecycle_intent_boundary_is_settled(
    release_decision: str, deployment_sequence: Mapping[str, Any]
) -> bool:
    """Allow elective post-release intent only at an auditable boundary."""

    deployment_status = clean_cell(deployment_sequence.get("status", ""))
    return bool(
        not deployment_sequence.get("issues")
        and (
            (
                release_decision == "RELEASE_VERIFIED"
                and deployment_status in {"NOT_ACTIVE", "CONSUMED"}
            )
            or (release_decision == "NOT_READY" and deployment_status == "CONSUMED")
        )
    )


def aws_lifecycle_intent_route_is_eligible(
    intent: str,
    lifecycle_state: str,
    release_decision: str,
    tasks: TaskSummary,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> bool:
    """Return whether elective owner intent may enter AWS-40 now."""

    return bool(
        intent in {"RESIDUAL_REVIEW", "TEARDOWN"}
        and (
            lifecycle_state in {"RELEASE_REVIEW", "RELEASE_VERIFIED"}
            or clean_cell(deployment_sequence.get("status", "")) == "CONSUMED"
        )
        and (
            tasks.terminal
            or clean_cell(deployment_sequence.get("status", "")) == "CONSUMED"
        )
        and release_lifecycle_intent_boundary_is_settled(
            release_decision, deployment_sequence
        )
        and clean_cell(teardown_sequence.get("status", ""))
        not in {"ACTION_TERMINAL_REQUIRED", "POST_ACTION_REVIEW"}
        and not teardown_sequence.get("issues")
    )


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
        return (
            ("REQUIREMENTS_ANALYSIS", "REQ-10")
            if requirements_present
            else ("INTAKE_REQUIRED", "INTAKE-10")
        )
    if gate_a == "PENDING_OWNER_APPROVAL":
        return "WAITING_GATE_A", "INTAKE-20"
    if gate_a != "APPROVED_FOR_DESIGN":
        return "BLOCKED", "STOP"
    if gate_b == "STALE":
        return "DESIGN_STALE", "DESIGN-10"
    if gate_b == "BLOCKED":
        return (
            ("WAITING_GATE_B", "DESIGN-20")
            if gate_b_agent_ready
            else ("DESIGN_REQUIRED", "DESIGN-10")
        )
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


def derive_aws_delivery_route(
    release_decision: str,
    aws_execution: Mapping[str, Any],
    deployment_sequence: Mapping[str, Any],
    lane: str | None,
    release_evidence_cutoff: str = "NONE",
) -> tuple[str, str] | None:
    """Route a release without confusing authority with an attempted action."""

    deployment_status = clean_cell(deployment_sequence.get("status", ""))
    if deployment_sequence.get("issues"):
        return "BLOCKED", "STOP"
    if deployment_status == "ACTION_TERMINAL_REQUIRED":
        return "AWS_DEPLOYMENT_ACTION_TERMINAL", "AWS-20"
    if deployment_status == "RECONCILIATION_REQUIRED":
        return "AWS_DEPLOYMENT_RECONCILIATION", "AWS-30"
    if deployment_status in {"RECONCILED", "BLOCKED"}:
        terminal_evidence = clean_cell(deployment_sequence.get("evidence_id", ""))
        if release_evidence_cutoff != terminal_evidence:
            return "RELEASE_REVIEW", "RELEASE-10"
    if deployment_status == "CONSUMED":
        if release_decision == "NOT_READY":
            return "RELEASE_REVIEW_BLOCKED", "STOP"
        if release_decision != "READY_TO_DEPLOY":
            return None
        if (
            clean_cell(deployment_sequence.get("current_mutation_authority_status", ""))
            == "UNAVAILABLE"
        ):
            return None
    if release_decision != "READY_TO_DEPLOY":
        return None
    progress_state = clean_cell(aws_execution.get("progress_state", ""))
    if progress_state == "WAITING_AWS_MUTATION_AUTH":
        return "WAITING_AWS_MUTATION_AUTH", "AWS-20"
    if progress_state == "AWS_PREFLIGHT_READY" and lane == "fast-dev":
        return "AWS_PREFLIGHT_READY", "AWS-20"
    if progress_state == "AWS_PREFLIGHT_READY":
        return "AWS_PREFLIGHT_READY", "STOP"
    return progress_state or "AWS_PREFLIGHT_REQUIRED", "AWS-10"


def _preserve_expired_authority_for_deployment_closure(
    ctx: Context,
    deployment_sequence: Mapping[str, Any],
    release_decision: str,
) -> None:
    status = clean_cell(deployment_sequence.get("status", ""))
    terminal_reconciliation = bool(
        (
            status in {"RECONCILED", "BLOCKED"}
            or (status == "CONSUMED" and release_decision != "READY_TO_DEPLOY")
        )
        and not deployment_sequence.get("issues")
        and clean_cell(deployment_sequence.get("phase", "")) == "AWS-30"
        and clean_cell(deployment_sequence.get("reconciliation_status", ""))
        in {"COMPLETE", "BLOCKED"}
    )
    read_only_reconciliation = bool(
        status == "RECONCILIATION_REQUIRED"
        and not deployment_sequence.get("issues")
        and clean_cell(deployment_sequence.get("action_status", ""))
        in AWS_DEPLOYMENT_TERMINAL_STATUSES
    )
    completed_without_attempt = bool(
        status == "NOT_ACTIVE" and release_decision == "RELEASE_VERIFIED"
    )
    if (
        status != "ACTION_TERMINAL_REQUIRED"
        and not read_only_reconciliation
        and not terminal_reconciliation
        and not completed_without_attempt
    ):
        return
    ctx.diagnostics = [
        Diagnostic(item.code, item.message, item.path, "WARNING")
        if item.code == "GATE_B_AUTHORITY_EXPIRED"
        else item
        for item in ctx.diagnostics
    ]


def _preserve_expired_authority_for_teardown_closure(
    ctx: Context, teardown_sequence: Mapping[str, Any]
) -> None:
    """Keep only the local UNKNOWN closure after a valid teardown STARTED row."""

    if clean_cell(teardown_sequence.get("status", "")) not in {
        "ACTION_TERMINAL_REQUIRED",
        "POST_ACTION_REVIEW",
    } or teardown_sequence.get("issues"):
        return
    ctx.diagnostics = [
        Diagnostic(item.code, item.message, item.path, "WARNING")
        if item.code == "GATE_B_AUTHORITY_EXPIRED"
        else item
        for item in ctx.diagnostics
    ]


def _preserve_specialized_teardown_block(ctx: Context, lifecycle_state: str) -> bool:
    """Keep the teardown safety route only when every error belongs to it."""

    return lifecycle_state == "AWS_RESIDUAL_REVIEW_BLOCKED" and all(
        item.severity != "ERROR" or item.code == "AWS_TEARDOWN_EVIDENCE_INVALID"
        for item in ctx.diagnostics
    )


def inspect_project(
    root: Path,
    *,
    template_source: bool = False,
    prior_remediation_fingerprint: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    ctx = Context(
        root=root,
        template_source=template_source,
        prior_remediation_fingerprint=prior_remediation_fingerprint,
    )
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
        selections,
        requirements_present,
        design_contract,
        coverage_contract,
        intake_contract,
        requirements_contract,
    ) = validate_prd(ctx, state)
    allow_legacy_design_discovery = bool(
        prd_fields.get("gate_b") == "APPROVED_FOR_CONSTRUCTION"
        and design_contract.architecture.schema_version < 4
    )
    aws_core_rows: dict[tuple[str, str, str], AwsCoreEvidenceRow] = {}
    blocking_aws_core_phases: set[str] = set()
    verify_text = ctx.texts.get(VERIFY_FILE) or safe_read_text(ctx, VERIFY_FILE)
    if verify_text is not None:
        try:
            active_scope = table_after_heading(verify_text, "## Active evidence scope")
        except ValueError:
            active_scope = {}
        verify_name = html.unescape(clean_cell(active_scope.get("Workload", "")))
        if verify_name and state.get("project", {}).get("name") != verify_name:
            ctx.error(
                "STATE_VERIFY_DRIFT",
                "project.name does not match the VERIFY Workload value",
                VERIFY_FILE,
            )
        try:
            aws_core_rows = parse_aws_core_evidence(
                verify_text,
                allow_legacy=allow_legacy_design_discovery,
            )
        except ValueError as exc:
            ctx.error("AWS_CORE_EVIDENCE_GENERATED_INVALID", str(exc), VERIFY_FILE)
    tasks = validate_tasks(
        ctx,
        state,
        prd_fields,
        envelope,
        requirements_contract,
        design_contract,
    )
    release_record = validate_release_decision_record(ctx)
    release_decision = release_record["release_state"]
    release_evidence_cutoff = release_record["active_evidence_cutoff"]
    aws_lifecycle_intent_record = validate_aws_lifecycle_intent_record(ctx)
    aws_lifecycle_intent = str(aws_lifecycle_intent_record["value"])
    validate_placeholders(ctx)

    gate_a = prd_fields.get("gate_a", "BLOCKED")
    gate_b = prd_fields.get("gate_b", "BLOCKED")
    prd_text = ctx.texts.get(PRD_FILE, "")
    gate_a_agent_ready = False
    gate_b_agent_ready = False
    try:
        gate_a_agent = table_after_heading(
            prd_text, "### Gate A — agent analysis record"
        )
        gate_b_agent = table_after_heading(
            prd_text, "## 27. Gate B agent review record"
        )
        gate_a_agent_ready = gate_a_agent.get("Agent recommendation") in {
            "READY_WITH_PROPOSED_ASSUMPTIONS",
            "READY_FOR_OWNER_APPROVAL",
        }
        gate_b_agent_ready = (
            gate_b_agent.get("Agent recommendation")
            == "READY_FOR_CONSTRUCTION_APPROVAL"
        )
    except ValueError:
        pass
    approved_tech_ids = {
        decision.decision_id for decision in design_contract.technology_decisions
    }
    req_materiality_raw = prd_fields.get("req_aws_materiality")
    req_materiality: Mapping[str, Any] = (
        req_materiality_raw
        if isinstance(req_materiality_raw, Mapping)
        else {
            "materiality": "OPTIONAL",
            "status": "UNASSESSED",
            "basis_ids": [],
            "discovery_ids": [],
            "unresolved_fact_ids": [],
        }
    )
    req_materiality_value = str(req_materiality.get("materiality", "OPTIONAL"))
    declared_req_discovery_ids = {
        str(item) for item in req_materiality.get("discovery_ids", [])
    }
    observed_req_discovery_ids = {
        discovery_id
        for row_phase, discovery_id, _capability in aws_core_rows
        if row_phase == "REQ-10"
    }
    req_aws_core_issues: list[str] = []
    if req_materiality_value == "REQUIRED" or declared_req_discovery_ids:
        req_aws_core_issues = aws_core_phase_evidence_issues(
            aws_core_rows,
            "REQ-10",
            expected_binding=prd_fields.get("requirements_revision"),
            expected_basis_ids={
                str(item) for item in req_materiality.get("basis_ids", [])
            },
        )
        if declared_req_discovery_ids != observed_req_discovery_ids:
            req_aws_core_issues.append(
                "REQ-10 AWS Core discovery IDs must exactly match the current "
                "Gate A materiality record"
            )
    req_aws_core_ready = not req_aws_core_issues
    if (
        gate_a_agent_ready
        or gate_a in {"PENDING_OWNER_APPROVAL", "APPROVED_FOR_DESIGN"}
    ) and req_materiality_value == "REQUIRED":
        if req_aws_core_issues:
            blocking_aws_core_phases.add("REQ-10")
        for issue in req_aws_core_issues:
            ctx.error(aws_core_evidence_diagnostic_code(issue), issue, VERIFY_FILE)
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
    design_evidence_enforced = gate_b_agent_ready or gate_b in {
        "PENDING_OWNER_APPROVAL",
        "APPROVED_FOR_CONSTRUCTION",
    }
    if design_evidence_enforced:
        if design_aws_core_issues:
            blocking_aws_core_phases.add("DESIGN-10")
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
    if (
        gate_a == "BLOCKED"
        and not ctx.has_errors
        and any(value is None for value in selections.values())
    ):
        lifecycle_state, next_prompt = "INTAKE_REQUIRED", "INTAKE-10"
    artifact_binding = ""
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
    aws_guidance_ready = not aws_10_issues
    construction_authorization = (
        str(prd_fields.get("construction_authorization", "NONE"))
        if gate_b == "APPROVED_FOR_CONSTRUCTION"
        else "NONE"
    )
    read_authority = (
        _read_preflight_receipt_authority(
            verify_text or "",
            construction_authorization,
            str(state.get("project", {}).get("cost_posture", "")),
            envelope,
            artifact_binding,
        )
        if construction_authorization != "NONE"
        else None
    )
    preflight = derive_read_preflight_state(
        verify_text or "",
        read_authority,
        requirements_revision=str(prd_fields.get("requirements_revision", "")),
        design_revision=str(prd_fields.get("design_revision", "")),
        construction_authorization=construction_authorization,
        artifact_binding=artifact_binding,
    )
    deployment_sequence = derive_deployment_sequence_state(
        verify_text or "",
        read_authority,
        requirements_revision=str(prd_fields.get("requirements_revision", "")),
        design_revision=str(prd_fields.get("design_revision", "")),
        construction_authorization=construction_authorization,
        envelope=envelope,
        lane=selections.get("aws_lane"),
        artifact_binding=artifact_binding,
        release_evidence_cutoff=release_evidence_cutoff,
        release_state=release_decision,
        gate_b_authority_source=str(prd_fields.get("gate_b_authorization_source", "")),
        gate_b_authorized_at=str(prd_fields.get("gate_b_authorized_at", "")),
        cost_posture=str(state.get("project", {}).get("cost_posture", "")),
        restricted_closure=(
            gate_b != "APPROVED_FOR_CONSTRUCTION"
            or any(item.code == "GATE_B_AUTHORITY_EXPIRED" for item in ctx.diagnostics)
        ),
    )
    _preserve_expired_authority_for_deployment_closure(
        ctx, deployment_sequence, release_decision
    )
    teardown_sequence = derive_teardown_sequence_state(
        verify_text or "",
        read_authority,
        requirements_revision=str(prd_fields.get("requirements_revision", "")),
        design_revision=str(prd_fields.get("design_revision", "")),
        construction_authorization=construction_authorization,
        envelope=envelope,
        restricted_closure=(
            gate_b != "APPROVED_FOR_CONSTRUCTION"
            or any(item.code == "GATE_B_AUTHORITY_EXPIRED" for item in ctx.diagnostics)
        ),
        cost_posture=str(state.get("project", {}).get("cost_posture", "")),
        active_artifact=artifact_binding,
    )
    _preserve_expired_authority_for_teardown_closure(ctx, teardown_sequence)
    aws_sequence_conflict = aws_deployment_teardown_sequence_conflict(
        deployment_sequence, teardown_sequence
    )
    if aws_sequence_conflict:
        ctx.error(
            "AWS_DEPLOYMENT_TEARDOWN_CONFLICT",
            "Open deployment and teardown journal epochs cannot coexist; close one sequence before continuing",
            VERIFY_FILE,
        )
    aws_execution = derive_aws_execution_projection(
        req_materiality,
        release_decision=release_decision,
        guidance_ready=aws_guidance_ready,
        read_authority=read_authority,
        preflight=preflight,
        lane=selections.get("aws_lane"),
    )
    if deployment_sequence.get("status") not in {"NOT_ACTIVE", "CONSUMED"}:
        aws_execution = {
            **aws_execution,
            "active": False,
            "progress_state": "NOT_ACTIVE",
        }
    elif (
        deployment_sequence.get("status") == "CONSUMED"
        and release_decision == "READY_TO_DEPLOY"
        and deployment_sequence.get("current_mutation_authority_status") == "CONSUMED"
    ):
        aws_execution = {
            **aws_execution,
            "progress_state": "WAITING_AWS_MUTATION_AUTH",
        }
        if selections.get("aws_lane") == "fast-dev":
            ctx.error(
                "AWS_DEPLOYMENT_AUTHORITY_REPLAY",
                "A fast-dev retry requires a freshly approved Gate B construction authorization",
                PRD_FILE,
            )
    aws_execution_planning_ready = preflight.get("status") == "READY"
    aws_delivery_route = derive_aws_delivery_route(
        release_decision,
        aws_execution,
        deployment_sequence,
        selections.get("aws_lane"),
        release_evidence_cutoff,
    )
    residual_disposition = derive_aws_residual_disposition(
        aws_lifecycle_intent_record, teardown_sequence
    )
    if residual_disposition.get("status") == "INVALID":
        ctx.error(
            "AWS_RESIDUAL_DISPOSITION_INVALID",
            "; ".join(str(item) for item in residual_disposition.get("issues", [])),
            VERIFY_FILE,
        )
    teardown_recovery_route = derive_teardown_route(
        aws_lifecycle_intent, teardown_sequence, residual_disposition
    )
    teardown_status = clean_cell(teardown_sequence.get("status", ""))
    if aws_sequence_conflict:
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
    elif (
        not ctx.has_errors
        and teardown_status in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}
        and not teardown_sequence.get("issues")
        and teardown_recovery_route is not None
    ):
        lifecycle_state, next_prompt = teardown_recovery_route
    elif (
        teardown_status in {"ACTION_TERMINAL_REQUIRED", "POST_ACTION_REVIEW", "BLOCKED"}
        and not teardown_sequence.get("issues")
        and teardown_recovery_route is not None
    ):
        lifecycle_state, next_prompt = teardown_recovery_route
    elif (
        not ctx.has_errors
        and aws_lifecycle_intent_route_is_eligible(
            aws_lifecycle_intent,
            lifecycle_state,
            release_decision,
            tasks,
            deployment_sequence,
            teardown_sequence,
        )
        and teardown_recovery_route is not None
    ):
        lifecycle_state, next_prompt = teardown_recovery_route
    elif aws_delivery_route is not None and not ctx.has_errors:
        lifecycle_state, next_prompt = aws_delivery_route
    if next_prompt == "AWS-10" and not aws_guidance_ready:
        ctx.warning(
            "AWS_CORE_AWS10_EVIDENCE_REQUIRED",
            "AWS-10 must record a fresh linked search_documentation then "
            "retrieve_skill discovery chain bound to the current artifact before "
            "AWS execution planning: " + "; ".join(aws_10_issues),
            VERIFY_FILE,
        )
    if preflight.get("issues"):
        ctx.error(
            "AWS_PREFLIGHT_EVIDENCE_INVALID",
            "; ".join(str(item) for item in preflight["issues"]),
            VERIFY_FILE,
        )
    # A stale attempted basis never authorizes new mutation, but read-only
    # reconciliation still proceeds so the observed action can be closed.
    if deployment_sequence.get("issues"):
        ctx.error(
            "AWS_DEPLOYMENT_EVIDENCE_INVALID",
            "; ".join(str(item) for item in deployment_sequence["issues"]),
            VERIFY_FILE,
        )
    if teardown_sequence.get("issues"):
        ctx.error(
            "AWS_TEARDOWN_EVIDENCE_INVALID",
            "; ".join(str(item) for item in teardown_sequence["issues"]),
            VERIFY_FILE,
        )
    aws_core_usage = {
        "REQ-10": derive_aws_core_observed_usage(
            aws_core_rows,
            "REQ-10",
            issues=req_aws_core_issues,
        ),
        "DESIGN-10": derive_aws_core_observed_usage(
            aws_core_rows,
            "DESIGN-10",
            issues=design_aws_core_issues,
        ),
        "AWS-10": derive_aws_core_observed_usage(
            aws_core_rows,
            "AWS-10",
            issues=aws_10_issues,
        ),
    }
    specialized_teardown_block = _preserve_specialized_teardown_block(
        ctx, lifecycle_state
    )
    if ctx.has_errors and not specialized_teardown_block:
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
    owner_stage_hint = _owner_stage_for_aws_core_phases(
        blocking_aws_core_phases,
        _owner_stage_from_gates(gate_a, gate_b),
    )
    if any(
        item.code == "APPLICATION_SOURCE_DISPOSITION_CONFLICT"
        for item in ctx.diagnostics
    ):
        owner_stage_hint = "DEFINE"
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
        intake_contract=intake_contract,
        coverage_contract=coverage_contract,
        aws_execution=aws_execution,
        requirements_contract=requirements_contract,
        aws_core_usage=aws_core_usage,
        owner_stage_hint=owner_stage_hint,
        active_artifact=artifact_binding,
        deployment_sequence=deployment_sequence,
        teardown_sequence=teardown_sequence,
        req_aws_core_materiality=req_materiality_value,
        req_aws_core_ready=req_aws_core_ready,
        aws_lifecycle_intent_record=aws_lifecycle_intent_record,
        release_evidence_cutoff=release_evidence_cutoff,
    )


def inspect_git_baseline(root: Path) -> str:
    """Return the current commit or PENDING without changing Git state."""

    try:
        result = subprocess.run(
            [
                resolve_trusted_git(root),
                "-C",
                str(root),
                "rev-parse",
                "--verify",
                "HEAD",
            ],
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
        "PROJECT_CONTRACT_MIGRATION_REQUIRED",
        "ACTOR_CONTRACT_INVALID",
        "JOURNEY_CONTRACT_INVALID",
        "RICH_USE_CASE_REQUIRED",
        "RICH_USE_CASE_INVALID",
        "BUSINESS_RULE_INVALID",
        "REQUIREMENT_COVERAGE_INVALID",
        "INTAKE_CARD_REQUIRED",
        "INTAKE_CARD_MIGRATION_REQUIRED",
        "INTAKE_CONTRACT_MIGRATION_REQUIRED",
        "INTAKE_SELECTION_PROVENANCE_INVALID",
        "INTAKE_FOUNDATION_PROVENANCE_INVALID",
        "INTAKE_RESPONSE_REGISTER_INVALID",
        "OWNER_BRIEF_SOURCE_STALE",
        "OWNER_BRIEF_COVERAGE_INCOMPLETE",
        "OWNER_BRIEF_SOURCE_MISMATCH",
        "OWNER_BRIEF_OUTPUT_BUDGET_UNRESOLVED",
        "GATE_A_LIFECYCLE_TRANSITION",
        "GATE_A_READINESS_CARD",
        "GATE_A_RECOMMENDATION",
        "REQ_AWS_MATERIALITY_INVALID",
        "AWS_CORE_REQ10_EVIDENCE_REQUIRED",
        "AWS_CORE_DISCOVERY_REQUIRED",
        "AWS_CORE_EVIDENCE_STALE",
        "AWS_CORE_EVIDENCE_GENERATED_INVALID",
    }
)
DESIGN_AGENT_DIAGNOSTICS = frozenset(
    {
        "APPLICATION_SOURCE_DISPOSITION_INVALID",
        "APPLICATION_SOURCE_DISPOSITION_MISSING",
        "APPLICATION_SOURCE_PARALLEL_ROOT",
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
        "OWNER_BRIEF_SOURCE_STALE",
        "OWNER_BRIEF_COVERAGE_INCOMPLETE",
        "OWNER_BRIEF_SOURCE_MISMATCH",
        "OWNER_BRIEF_OUTPUT_BUDGET_UNRESOLVED",
        "AWS_CORE_EVIDENCE_REQUIRED",
        "AWS_CORE_DISCOVERY_REQUIRED",
        "AWS_CORE_EVIDENCE_STALE",
        "AWS_CORE_EVIDENCE_GENERATED_INVALID",
    }
)
DELIVER_AGENT_DIAGNOSTICS = frozenset(
    {
        "ACTIVE_TASK_CONFLICT",
        "AUTONOMY_OUTSIDE_AUTH",
        "STATE_TASK_DRIFT",
        "TASK_ATTEMPT_BOUNDARY",
        "TASK_AWS_BOUNDARY",
        "TASK_AWS_MODE_REPLAN_REQUIRED",
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
        "TASK_REQUIREMENT_TRACE_INVALID",
        "TASK_REQUIREMENT_COVERAGE",
        "TASK_REQUIREMENT_COVERAGE_EVIDENCE_INVALID",
        "TASK_SNAPSHOT",
        "WORKER_LIMIT_EXCEEDED",
    }
)
TASK_REPLAN_DIAGNOSTICS = frozenset(
    {
        "TASK_AWS_MODE_REPLAN_REQUIRED",
        "TASK_REQUIREMENT_TRACE_INVALID",
        "TASK_REQUIREMENT_COVERAGE",
        "TASK_REQUIREMENT_COVERAGE_EVIDENCE_INVALID",
    }
)
OWNER_DECISION_DIAGNOSTICS = frozenset(
    {
        "APPLICATION_SOURCE_DISPOSITION_CONFLICT",
        "BROWNFIELD_PRD_BASELINE",
        "PROJECT_CONTRACT_OWNER_FACT_REQUIRED",
        "BROWNFIELD_PRD_PRESERVATION",
        "BROWNFIELD_STATE",
        "GATE_A_ASSUMPTIONS",
        "GATE_A_BLOCKER",
        "GATE_A_COST_POSTURE",
        "INTAKE_FOUNDATION_REQUIRED",
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
        "AWS_CORE_CAPABILITY_UNAVAILABLE",
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
        "GATE_B_AUTHORITY_EXPIRED",
    }
)
UNCONFIGURED_SETUP_DIAGNOSTICS = frozenset(
    {
        "PLACEHOLDER_UNRESOLVED",
        "PROJECT_COST_POSTURE",
        "PROJECT_IDENTITY",
        "STATE_SETUP",
    }
)


AWS_CORE_GENERATED_DIAGNOSTICS = frozenset(
    {
        "AWS_CORE_REQ10_EVIDENCE_REQUIRED",
        "AWS_CORE_EVIDENCE_REQUIRED",
        "AWS_CORE_DISCOVERY_REQUIRED",
        "AWS_CORE_EVIDENCE_STALE",
        "AWS_CORE_EVIDENCE_GENERATED_INVALID",
    }
)


def _owner_stage_from_gates(gate_a: str, gate_b: str) -> str:
    if gate_a != "APPROVED_FOR_DESIGN":
        return "DEFINE"
    if gate_b != "APPROVED_FOR_CONSTRUCTION":
        return "DESIGN"
    return "DELIVER"


def _owner_stage_for_aws_core_phases(phases: set[str], fallback: str) -> str:
    """Return the earliest owner stage affected by enforced AWS evidence."""

    if "REQ-10" in phases:
        return "DEFINE"
    if "DESIGN-10" in phases:
        return "DESIGN"
    if "AWS-10" in phases:
        return "DELIVER"
    return fallback


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
    if diagnostic.code == "DOCUMENT_SUMMARY_STALE":
        return relative in DOCUMENT_SUMMARY_FILES

    if owner_stage == "DEFINE":
        if diagnostic.code not in DEFINE_AGENT_DIAGNOSTICS:
            return False
        if diagnostic.code in AWS_CORE_GENERATED_DIAGNOSTICS:
            return relative in {PRD_FILE, VERIFY_FILE}
        return relative == PRD_FILE
    if owner_stage == "DESIGN":
        if diagnostic.code not in DESIGN_AGENT_DIAGNOSTICS:
            return False
        if diagnostic.code in AWS_CORE_GENERATED_DIAGNOSTICS:
            return relative == VERIFY_FILE or (
                gate_b != "APPROVED_FOR_CONSTRUCTION" and relative == PRD_FILE
            )
        if gate_b == "APPROVED_FOR_CONSTRUCTION":
            return False
        return relative == PRD_FILE
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
    requirements_revision: str | None = None,
    design_revision: str | None = None,
    owner_stage_hint: str | None = None,
) -> dict[str, Any]:
    """Classify each error, then derive one deterministic next action."""

    owner_stage = (
        owner_stage_hint
        if owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}
        else _owner_stage_from_gates(gate_a, gate_b)
    )
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
        elif diagnostic.code in TASK_REPLAN_DIAGNOSTICS and _agent_correction_is_safe(
            diagnostic, owner_stage, gate_b, envelope, tasks
        ):
            responsible_party = "CODEX"
            category = "AGENT_REPLAN"
            automatic = True
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

    codex_payload: list[dict[str, str]] = []
    for item in items:
        if item["category"] not in {"AGENT_CORRECTION", "AGENT_REPLAN"}:
            continue
        diagnostic_index = int(str(item["diagnostic_id"]).rsplit("-", 1)[1]) - 1
        diagnostic = ctx.diagnostics[diagnostic_index]
        codex_payload.append(
            {
                "code": diagnostic.code,
                "path": diagnostic.path or "NONE",
                "cause": re.sub(r"\s+", " ", diagnostic.message).strip(),
                "requirements_revision": requirements_revision or "NONE",
                "design_revision": design_revision or "NONE",
            }
        )
    remediation_fingerprint = "NONE"
    if codex_payload:
        canonical = json.dumps(
            codex_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        remediation_fingerprint = "sha256:" + hashlib.sha256(canonical).hexdigest()
    repeated_fingerprint = (
        remediation_fingerprint != "NONE"
        and ctx.prior_remediation_fingerprint == remediation_fingerprint
    )
    if repeated_fingerprint:
        for item in items:
            if item["category"] in {"AGENT_CORRECTION", "AGENT_REPLAN"}:
                item["responsible_party"] = "HUMAN_REVIEWER"
                item["category"] = "MANUAL_SAFETY_REVIEW"
                item["automatic_correction_allowed"] = False

    manual = [item for item in items if item["category"] == "MANUAL_SAFETY_REVIEW"]
    codex = [item for item in items if item["category"] == "AGENT_CORRECTION"]
    replans = [item for item in items if item["category"] == "AGENT_REPLAN"]
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
    elif replans:
        next_action = {
            "responsible_party": "CODEX",
            "action_kind": "REPLAN_TASKS",
            "automatic_continuation_allowed": True,
            "preserve_done_evidence": True,
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
    return {
        "items": items,
        "next_action": next_action,
        "fingerprint": remediation_fingerprint,
        "retry_state": "REPEATED" if repeated_fingerprint else "FIRST_OR_NONE",
    }


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
    aws_progress_state: str | None = None,
    aws_mutation_authority_ready: bool = False,
    aws_lane: str | None = None,
    aws_read_authority_required: bool = False,
    req_aws_core_materiality: str = "OPTIONAL",
    req_aws_core_ready: bool = True,
) -> dict[str, Any]:
    """Derive stable owner interaction metadata without conversational prose."""

    aws_core_capability_unavailable = (
        "AWS_CORE_CAPABILITY_UNAVAILABLE" in diagnostic_codes
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
    else:
        owner_stage = "DELIVER"
    if owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}:
        owner_stage = owner_stage_hint

    route_reason_code = lifecycle_state
    if lifecycle_state in {
        "AWS_RESIDUAL_REVIEW_BLOCKED",
        "RELEASE_REVIEW_BLOCKED",
    }:
        response_mode = "BLOCKER"
        state = "BLOCKED"
        action_kind = "REVIEW_SAFETY_BLOCKER"
        automatic = False
        formal_receipt = False
    elif has_errors or lifecycle_state == "BLOCKED":
        next_action = remediation.get("next_action") if remediation else None
        remediation_action = (
            str(next_action.get("action_kind", ""))
            if isinstance(next_action, Mapping)
            else ""
        )
        if remediation_action in {"CORRECT_AND_REVALIDATE", "REPLAN_TASKS"}:
            response_mode = "OWNER_UPDATE"
            state = "WORKING"
            action_kind = "NONE_CONTINUE_AUTOMATICALLY"
            automatic = True
            if remediation_action == "REPLAN_TASKS":
                route_reason_code = "TASK_REPLAN_REQUIRED"
        elif remediation_action == "ANSWER_OPEN_DECISIONS":
            response_mode = "OWNER_UPDATE"
            state = "NEEDS_INPUT"
            action_kind = remediation_action
            automatic = False
            route_reason_code = "INTAKE_REQUIRED"
        elif remediation_action in {
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
            action_kind = (
                "ENABLE_AWS_CORE"
                if aws_core_capability_unavailable
                else "FIX_VALIDATION_FAILURE"
            )
            automatic = False
        formal_receipt = False
    elif lifecycle_state in {
        "AWS_DEPLOYMENT_ACTION_TERMINAL",
        "AWS_TEARDOWN_ACTION_TERMINAL",
    }:
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif lifecycle_state in {
        "AWS_DEPLOYMENT_RECONCILIATION",
        "AWS_RESIDUAL_REVIEW",
    }:
        response_mode = "AWS_RECEIPT" if aws_read_authority_required else "OWNER_UPDATE"
        state = "AWAITING_APPROVAL" if aws_read_authority_required else "WORKING"
        action_kind = (
            "AUTHORIZE_AWS_READ_PREFLIGHT"
            if aws_read_authority_required
            else "NONE_CONTINUE_AUTOMATICALLY"
        )
        automatic = not aws_read_authority_required
        formal_receipt = aws_read_authority_required
    elif lifecycle_state == "WAITING_AWS_TEARDOWN_AUTH":
        response_mode = (
            "OWNER_UPDATE" if aws_mutation_authority_ready else "AWS_RECEIPT"
        )
        state = "WORKING" if aws_mutation_authority_ready else "AWAITING_APPROVAL"
        action_kind = (
            "NONE_CONTINUE_AUTOMATICALLY"
            if aws_mutation_authority_ready
            else "AUTHORIZE_AWS_TEARDOWN"
        )
        automatic = aws_mutation_authority_ready
        formal_receipt = not aws_mutation_authority_ready
    elif lifecycle_state in {
        "AWS_RESIDUAL_REVIEW_COMPLETE",
        "AWS_RESIDUALS_RETAINED",
        "AWS_TEARDOWN_COMPLETE",
    }:
        response_mode = "OWNER_UPDATE"
        state = "COMPLETE"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = False
        formal_receipt = False
    elif lifecycle_state == "AWS_RESIDUALS_REMAIN":
        response_mode = "BLOCKER"
        state = "NEEDS_INPUT"
        action_kind = "CHOOSE_AWS_RESIDUAL_DISPOSITION"
        automatic = False
        formal_receipt = False
    elif aws_progress_state == "AWS_GUIDANCE_REQUIRED":
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif aws_progress_state == "AWS_READ_SCOPE_REQUIRED":
        response_mode = "AWS_RECEIPT"
        state = "AWAITING_APPROVAL"
        action_kind = "AUTHORIZE_AWS_READ_PREFLIGHT"
        automatic = False
        formal_receipt = True
    elif aws_progress_state == "AWS_PREFLIGHT_RUNNING":
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
    elif aws_progress_state == "AWS_PREFLIGHT_READY":
        response_mode = "OWNER_UPDATE"
        state = "WORKING" if aws_lane == "fast-dev" else "COMPLETE"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = aws_lane == "fast-dev"
        formal_receipt = False
    elif aws_progress_state == "WAITING_AWS_MUTATION_AUTH":
        response_mode = (
            "OWNER_UPDATE" if aws_mutation_authority_ready else "AWS_RECEIPT"
        )
        state = "WORKING" if aws_mutation_authority_ready else "AWAITING_APPROVAL"
        action_kind = (
            "NONE_CONTINUE_AUTOMATICALLY"
            if aws_mutation_authority_ready
            else "AUTHORIZE_AWS_OPERATION"
        )
        automatic = aws_mutation_authority_ready
        formal_receipt = not aws_mutation_authority_ready
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
    elif next_prompt == "AWS-50":
        response_mode = (
            "OWNER_UPDATE" if aws_mutation_authority_ready else "AWS_RECEIPT"
        )
        state = "WORKING" if aws_mutation_authority_ready else "AWAITING_APPROVAL"
        action_kind = (
            "NONE_CONTINUE_AUTOMATICALLY"
            if aws_mutation_authority_ready
            else "AUTHORIZE_AWS_TEARDOWN"
        )
        automatic = aws_mutation_authority_ready
        formal_receipt = not aws_mutation_authority_ready
    elif next_prompt in {"AWS-30", "AWS-40"} and aws_read_authority_required:
        response_mode = "AWS_RECEIPT"
        state = "AWAITING_APPROVAL"
        action_kind = "AUTHORIZE_AWS_READ_PREFLIGHT"
        automatic = False
        formal_receipt = True
    elif next_prompt in {"AWS-30", "AWS-40"}:
        response_mode = "OWNER_UPDATE"
        state = "WORKING"
        action_kind = "NONE_CONTINUE_AUTOMATICALLY"
        automatic = True
        formal_receipt = False
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

    req_core_material = bool(
        owner_stage == "DEFINE"
        and next_prompt in {"REQ-10", "INTAKE-20"}
        and req_aws_core_materiality == "REQUIRED"
    )
    material = (
        req_core_material
        or owner_stage == "DESIGN"
        or next_prompt.startswith("AWS-")
        or aws_progress_state is not None
    )
    if not material:
        evidence_status = "NOT_REQUIRED"
    elif req_core_material:
        evidence_status = (
            "CURRENT"
            if req_aws_core_ready
            else ("BLOCKED" if has_errors else "REQUIRED")
        )
    elif aws_progress_state is not None:
        evidence_status = (
            "REQUIRED" if aws_progress_state == "AWS_GUIDANCE_REQUIRED" else "CURRENT"
        )
    elif next_prompt.startswith("AWS-"):
        evidence_status = (
            "CURRENT"
            if aws_execution_planning_ready
            else ("BLOCKED" if has_errors else "REQUIRED")
        )
    else:
        evidence_status = (
            "CURRENT"
            if design_aws_core_ready
            else ("BLOCKED" if has_errors else "REQUIRED")
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
        "route_reason_code": route_reason_code,
        "owner_action_required": action_kind != "NONE_CONTINUE_AUTOMATICALLY",
        "owner_action_kind": action_kind,
        "blocking_ids": blocking_ids,
        "automatic_continuation_allowed": automatic,
        "turn_boundary_required": (
            action_kind != "NONE_CONTINUE_AUTOMATICALLY" and not automatic
        ),
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
        "turn_boundary_required": True,
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
            task
            for task in inspect_task_blocks(text)
            if task.task_id == request.selector
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
            if cells is not None and any(
                token.search(clean_cell(cell)) for cell in cells
            ):
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
        elif path.startswith(".agents/skills/fastlane/references/"):
            priority = 0
            reason = "Current phase procedure"
        else:
            priority = 4
            reason = "Consequential evidence or authority"
    required_selectors = {
        "Document status",
        "Active execution snapshot",
        "AWS Core evidence",
        "Read-only AWS preflight evidence",
        "Read-only AWS preflight",
        "Action authorization provenance",
        "AWS deployment action and reconciliation evidence",
        "Conditional AWS action receipts",
        "Teardown reconciliation evidence",
        "13. Teardown and decommissioning",
        "14. Residual-resource and billing verification",
    }
    # A phase procedure is complete guidance, not one atomic lifecycle record.
    # It may move on demand as a whole when current required state needs the
    # initial budget; the coordinator loads it later only when the current
    # decision requires it. Task blocks and controlling state records remain
    # atomic and required.
    required = initial and (
        selector_kind == "TASK_ID"
        or selector in required_selectors
        or (
            selector_kind == "HEADING"
            and path.startswith(".agents/skills/fastlane/references/")
        )
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
        _context_request(value, active_ids, initial=False) for value in on_demand_slices
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
    next_prompt: str = "",
    restricted_deployment_closure: bool = False,
    restricted_teardown_closure: bool = False,
    source_texts: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Select an ephemeral, route-bounded canonical context packet."""

    stage = interaction.get("owner_stage")
    reason = interaction.get("route_reason_code")
    deployment_closure_context = restricted_deployment_closure and next_prompt in {
        "AWS-20",
        "AWS-30",
        "RELEASE-10",
    }
    teardown_closure_context = restricted_teardown_closure and next_prompt in {
        "AWS-40",
        "AWS-50",
    }
    closure_context = deployment_closure_context or teardown_closure_context
    if teardown_closure_context:
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#Teardown and residuals",
            f"{VERIFY_FILE}#Teardown reconciliation evidence",
        ]
        on_demand_slices = [
            f"{TASKS_FILE}#Active execution snapshot",
            f"{PRD_FILE}#Construction envelope",
            f"{VERIFY_FILE}#Action authorization provenance",
            f"{VERIFY_FILE}#Read-only AWS preflight evidence",
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
            f"{RUNBOOK_FILE}#Conditional AWS action receipts",
            f"{RUNBOOK_FILE}#Read-only AWS preflight",
            f"{RUNBOOK_FILE}#13. Teardown and decommissioning",
            f"{RUNBOOK_FILE}#14. Residual-resource and billing verification",
        ]
    elif deployment_closure_context:
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#AWS handoff and reconciliation",
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
        ]
        on_demand_slices = [
            f"{TASKS_FILE}#Active execution snapshot",
            f"{PRD_FILE}#Construction envelope",
            f"{VERIFY_FILE}#Action authorization provenance",
            f"{VERIFY_FILE}#Read-only AWS preflight evidence",
            f"{RUNBOOK_FILE}#Conditional AWS action receipts",
            f"{RUNBOOK_FILE}#Read-only AWS preflight",
        ]
        if next_prompt in {"AWS-30", "RELEASE-10"}:
            on_demand_slices.extend(
                [
                    f"{VERIFY_FILE}#Verification matrix",
                    f"{VERIFY_FILE}#Current release decision",
                ]
            )
    elif stage == "DEFINE":
        source_slices = [
            ".agents/skills/fastlane/references/define.md#Setup and intake",
            f"{PRD_FILE}#Document status",
            f"{PRD_FILE}#Product Agreement",
        ]
        on_demand_slices = [
            ".agents/skills/fastlane/references/define.md#Requirements and Gate A",
            ".agents/skills/fastlane/references/define.md#Review and AWS evidence",
            f"{PRD_FILE}#Gate A Review",
            BUGFIX_FILE,
        ]
    elif stage == "DESIGN":
        source_slices = [
            ".agents/skills/fastlane/references/design.md#Architecture selection and records",
            f"{PRD_FILE}#Adaptive coverage plan",
            f"{PRD_FILE}#Architecture drivers",
            f"{PRD_FILE}#Whole-system candidates",
            f"{PRD_FILE}#Selected architecture",
            f"{VERIFY_FILE}#AWS Core evidence",
        ]
        on_demand_slices = [
            ".agents/skills/fastlane/references/design.md#Architecture and AWS evidence",
            ".agents/skills/fastlane/references/design.md#Validation, diagrams, and Gate B",
            ".agents/skills/fastlane/references/design.md#Challenger and approval",
            f"{PRD_FILE}#Architecture traceability",
            f"{PRD_FILE}#Change impact record",
            f"{PRD_FILE}#Project diagram contract",
            f"{PRD_FILE}#Gate B Harness Profile",
            f"{PRD_FILE}#Construction envelope",
        ]
    elif stage == "DELIVER":
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#Tasks and local construction",
            f"{TASKS_FILE}#Active execution snapshot",
        ]
        on_demand_slices = [
            ".agents/skills/fastlane/references/deliver.md#AWS handoff and reconciliation",
            ".agents/skills/fastlane/references/deliver.md#Teardown and residuals",
            f"{PRD_FILE}#Construction envelope",
            f"{VERIFY_FILE}#Task completion evidence",
            f"{VERIFY_FILE}#Construction and release readiness checks",
            f"{RUNBOOK_FILE}#Active operational boundary",
        ]
    else:
        raise ValueError("context plan requires a known owner stage")

    active_ids: list[str] = []
    task_context_ids: list[str] = []
    if stage == "DELIVER":
        task_context_ids.extend(tasks.active)
        if not task_context_ids and tasks.ready:
            task_context_ids.append(tasks.ready[0])
        active_ids.extend(task_context_ids)
    else:
        active_ids.extend(coverage.basis_ids)
    blockers = interaction.get("blocking_ids")
    if isinstance(blockers, list):
        active_ids.extend(item for item in blockers if isinstance(item, str))
    active_ids = sorted(set(active_ids))

    if stage == "DELIVER" and task_context_ids:
        source_slices.append(f"{TASKS_FILE}#" + task_context_ids[0])
    aws_phase = next_prompt if next_prompt.startswith("AWS-") else ""
    teardown_context_reasons = {
        "AWS_RESIDUAL_REVIEW",
        "AWS_RESIDUAL_REVIEW_COMPLETE",
        "AWS_RESIDUALS_RETAINED",
        "AWS_RESIDUALS_REMAIN",
        "AWS_RESIDUAL_REVIEW_BLOCKED",
        "AWS_TEARDOWN_COMPLETE",
        "AWS_TEARDOWN_ACTION_TERMINAL",
    }
    teardown_phase_context = (
        aws_phase in {"AWS-40", "AWS-50"} or reason in teardown_context_reasons
    )
    if teardown_phase_context and not closure_context:
        source_slices = [
            ".agents/skills/fastlane/references/deliver.md#Teardown and residuals",
            f"{VERIFY_FILE}#Teardown reconciliation evidence",
        ]
        on_demand_slices.extend(
            [
                f"{TASKS_FILE}#Active execution snapshot",
                f"{PRD_FILE}#Construction envelope",
                f"{VERIFY_FILE}#Action authorization provenance",
                f"{VERIFY_FILE}#Read-only AWS preflight evidence",
                f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
                f"{VERIFY_FILE}#AWS Core evidence",
                f"{RUNBOOK_FILE}#Conditional AWS action receipts",
                f"{RUNBOOK_FILE}#Read-only AWS preflight",
                f"{RUNBOOK_FILE}#13. Teardown and decommissioning",
                f"{RUNBOOK_FILE}#14. Residual-resource and billing verification",
            ]
        )
        if task_context_ids:
            on_demand_slices.append(f"{TASKS_FILE}#" + task_context_ids[0])
    common_aws_slices = [
        f"{VERIFY_FILE}#Action authorization provenance",
        f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
        f"{RUNBOOK_FILE}#Conditional AWS action receipts",
        f"{VERIFY_FILE}#AWS Core evidence",
        f"{VERIFY_FILE}#Read-only AWS preflight evidence",
        f"{RUNBOOK_FILE}#Read-only AWS preflight",
    ]
    if closure_context:
        pass
    elif teardown_phase_context:
        pass
    elif reason == "AWS_DEPLOYMENT_ACTION_TERMINAL":
        source_slices.append(
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence"
        )
        on_demand_slices.extend(common_aws_slices)
    elif reason == "AWS_DEPLOYMENT_RECONCILIATION":
        source_slices.append(
            f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence"
        )
        on_demand_slices.extend(common_aws_slices)
    elif aws_phase or (isinstance(reason, str) and reason.startswith("AWS_")):
        source_slices.extend(common_aws_slices)
    if aws_phase == "AWS-30" and not closure_context:
        source_slices.extend(
            [
                f"{VERIFY_FILE}#Verification matrix",
                f"{VERIFY_FILE}#Current release decision",
            ]
        )
    if next_prompt == "RELEASE-10" and not closure_context:
        source_slices.extend(
            [
                f"{VERIFY_FILE}#Verification matrix",
                f"{VERIFY_FILE}#AWS deployment action and reconciliation evidence",
                f"{VERIFY_FILE}#Current release decision",
            ]
        )
    if stage == "DESIGN" and source_texts is not None:
        prd_source = source_texts.get(PRD_FILE)
        if isinstance(prd_source, str):
            try:
                diagram_table = contract_table_after_heading(
                    prd_source, DIAGRAM_CONTRACT_HEADING, DIAGRAM_CONTRACT_HEADERS
                )
            except ValueError:
                diagram_table = None
            required_kinds = required_diagram_kinds(
                prd_source,
                authoritative_requirement_ids(prd_source),
                coverage.work_kind,
            )
            if diagram_table is not None and any(
                row[1] in required_kinds and row[3] != "CURRENT"
                for row in diagram_table.rows
            ):
                on_demand_slices.append(
                    ".agents/skills/fastlane/references/diagram-patterns.md"
                )
    source_slices = list(dict.fromkeys(source_slices))
    on_demand_slices = list(dict.fromkeys(on_demand_slices))

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
    active_write_set = (
        tasks.write_sets.get(active_task, []) if active_task != "NONE" else []
    )
    return {
        "valid": True,
        "authorization_id": construction_authorization,
        "approved_write_roots": roots,
        "exclusions": exclusions,
        "protected_paths": protected,
        "active_task": active_task,
        "active_task_write_set": active_write_set,
    }


def derive_deployment_journal_closure_authority(
    deployment_sequence: Mapping[str, Any],
    next_prompt: str,
    *,
    restricted_closure: bool,
) -> dict[str, Any]:
    """Expose only the exact local VERIFY closure operation for one attempt."""

    empty: dict[str, Any] = {
        "valid": False,
        "kind": "NONE",
        "authorization_id": "NONE",
        "mode": "BOUNDED_EVIDENCE_CLOSURE",
        "allowed_write_paths": [],
        "allowed_sections": [],
        "allowed_operations": [],
        "allowed_release_states": [],
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }
    if not restricted_closure or deployment_sequence.get("issues"):
        return empty
    status = clean_cell(deployment_sequence.get("status", ""))
    contract = {
        ("ACTION_TERMINAL_REQUIRED", "AWS-20"): (
            [AWS_DEPLOYMENT_EVIDENCE_HEADING],
            ["APPEND_ACTION_TERMINAL_ROW"],
            [],
        ),
        ("RECONCILIATION_REQUIRED", "AWS-30"): (
            [
                "bootstrap:aws-read-preflight-receipt",
                "## Action authorization provenance",
                AWS_DEPLOYMENT_EVIDENCE_HEADING,
            ],
            [
                "RECORD_RECONCILIATION_READ_AUTHORITY",
                "APPEND_RECONCILIATION_ROW",
            ],
            [],
        ),
        ("RECONCILED", "RELEASE-10"): (
            ["## Current release decision"],
            ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
            (
                ["NOT_READY"]
                if deployment_sequence.get("basis_stale") is True
                else ["NOT_READY", "RELEASE_VERIFIED"]
            ),
        ),
        ("BLOCKED", "RELEASE-10"): (
            ["## Current release decision"],
            ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
            ["NOT_READY"],
        ),
    }.get((status, next_prompt))
    if contract is None:
        return empty
    attempt_id = clean_cell(deployment_sequence.get("attempt_id", ""))
    evidence_id = clean_cell(deployment_sequence.get("evidence_id", ""))
    if AWS_DEPLOYMENT_ATTEMPT_ID.fullmatch(attempt_id) is None:
        return empty
    if next_prompt == "RELEASE-10" and re.fullmatch(r"EV-\d{4,}", evidence_id) is None:
        return empty
    sections, operations, allowed_release_states = contract
    return {
        **empty,
        "valid": True,
        "kind": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
        "authorization_id": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
        "allowed_write_paths": [VERIFY_FILE],
        "allowed_sections": sections,
        "allowed_operations": operations,
        "allowed_release_states": allowed_release_states,
        "attempt_id": attempt_id,
        "evidence_id": evidence_id if evidence_id else "NONE",
    }


def derive_teardown_journal_closure_authority(
    teardown_sequence: Mapping[str, Any],
    next_prompt: str,
    *,
    restricted_closure: bool,
) -> dict[str, Any]:
    """Expose one exact VERIFY-only UNKNOWN closure for a lone STARTED row."""

    empty: dict[str, Any] = {
        "valid": False,
        "kind": "NONE",
        "authorization_id": "NONE",
        "mode": "BOUNDED_EVIDENCE_CLOSURE",
        "allowed_write_paths": [],
        "allowed_sections": [],
        "allowed_operations": [],
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }
    if (
        not restricted_closure
        or teardown_sequence.get("issues")
        or clean_cell(teardown_sequence.get("status", "")) != "ACTION_TERMINAL_REQUIRED"
        or next_prompt != "AWS-50"
    ):
        return empty
    attempt_id = clean_cell(teardown_sequence.get("attempt_id", ""))
    evidence_id = clean_cell(teardown_sequence.get("evidence_id", ""))
    if (
        AWS_TEARDOWN_ATTEMPT_ID.fullmatch(attempt_id) is None
        or re.fullmatch(r"EV-\d{4,}", evidence_id) is None
    ):
        return empty
    return {
        **empty,
        "valid": True,
        "kind": "AWS_TEARDOWN_JOURNAL_CLOSURE",
        "authorization_id": "AWS_TEARDOWN_JOURNAL_CLOSURE",
        "allowed_write_paths": [VERIFY_FILE],
        "allowed_sections": [AWS_TEARDOWN_EVIDENCE_HEADING],
        "allowed_operations": ["APPEND_TEARDOWN_TERMINAL_ROW"],
        "attempt_id": attempt_id,
        "evidence_id": evidence_id,
    }


def lifecycle_intent_record_boundary_is_settled(
    tasks: TaskSummary,
    release_decision: str,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
) -> bool:
    """Return whether one local owner-intent record may be updated."""

    return bool(
        (
            tasks.terminal
            or clean_cell(deployment_sequence.get("status", "")) == "CONSUMED"
        )
        and release_lifecycle_intent_boundary_is_settled(
            release_decision, deployment_sequence
        )
        and clean_cell(teardown_sequence.get("status", ""))
        in {
            "NOT_ACTIVE",
            "STALE",
            "READY_FOR_TEARDOWN",
            "VERIFIED_CLEAN",
            "RESIDUALS_REMAIN",
        }
        and not teardown_sequence.get("issues")
    )


def derive_aws_lifecycle_intent_write_authority(
    ctx: Context,
    tasks: TaskSummary,
    release_decision: str,
    deployment_sequence: Mapping[str, Any],
    teardown_sequence: Mapping[str, Any],
    external_authority: Mapping[str, Any],
    *,
    lifecycle_intent: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose one exact local owner-intent update and no AWS authority."""

    empty: dict[str, Any] = {
        "valid": False,
        "kind": "NONE",
        "authorization_id": "NONE",
        "mode": "BOUNDED_RELEASE_INTENT_RECORD",
        "allowed_write_paths": [],
        "allowed_sections": [],
        "allowed_operations": [],
        "allowed_values": [],
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }
    intent_value = clean_cell((lifecycle_intent or {}).get("value", "NONE"))
    teardown_status = clean_cell(teardown_sequence.get("status", "NOT_ACTIVE"))
    allowed_values = (
        ["RETAIN", "RESIDUAL_REVIEW", "TEARDOWN"]
        if teardown_status in {"READY_FOR_TEARDOWN", "RESIDUALS_REMAIN"}
        else ["NONE", "RESIDUAL_REVIEW", "TEARDOWN"]
    )
    intent_route_active = bool(
        intent_value in {"RESIDUAL_REVIEW", "TEARDOWN"}
        and teardown_status in {"NOT_ACTIVE", "STALE"}
    )
    if (
        ctx.has_errors
        or intent_route_active
        or not lifecycle_intent_record_boundary_is_settled(
            tasks,
            release_decision,
            deployment_sequence,
            teardown_sequence,
        )
        or clean_cell(external_authority.get("validity", "NONE")) == "CURRENT"
    ):
        return empty
    return {
        **empty,
        "valid": True,
        "kind": "AWS_LIFECYCLE_INTENT_RECORD",
        "authorization_id": "AWS_LIFECYCLE_INTENT_RECORD",
        "allowed_write_paths": [VERIFY_FILE],
        "allowed_sections": ["## Current release decision"],
        "allowed_operations": ["UPDATE_AWS_LIFECYCLE_INTENT"],
        "allowed_values": allowed_values,
    }


def _action_authorization_rows(text: str) -> dict[str, dict[str, str]]:
    heading = "## Action authorization provenance"
    structural = without_fenced_code(text)
    matches = list(
        re.finditer(rf"^{re.escape(heading)}[ \t]*$", structural, re.MULTILINE)
    )
    if len(matches) != 1:
        return {}
    original_lines = text[matches[0].end() :].splitlines()
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
        if action in {"Read-only preflight", "Deployment", "Teardown"}:
            if action in result:
                # Conflicting or repeated provenance is never first-row-wins.
                return {}
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


def _authorization_valid_until(
    value: str, result: str, *, allow_expired: bool = False
) -> str | None:
    cleaned = clean_cell(value)
    normalized = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        expires = datetime.fromisoformat(normalized)
    except ValueError:
        if cleaned == "ONE_OPERATION" and result in {"AUTHORIZED", "RUNNING", "READY"}:
            return cleaned
        return cleaned if explicit_value(cleaned) and result == "NOT_STARTED" else None
    if expires.tzinfo is None or expires.utcoffset() is None:
        return None
    return cleaned if allow_expired or expires > datetime.now(timezone.utc) else None


def _parse_cost_ceiling(value: str) -> tuple[str, Decimal] | None:
    """Return one canonical finite AWS cost ceiling or None."""

    try:
        return parse_positive_cost(value, AWS_COST_CEILING, "AWS cost ceiling")
    except ValueError:
        return None


def _cost_at_most(candidate: tuple[str, Decimal], ceiling: tuple[str, Decimal]) -> bool:
    return candidate[0] == ceiling[0] and candidate[1] <= ceiling[1]


def _read_bound_honors_cost_posture(
    bound: str,
    cost_posture: str,
    gate_b_cost_ceiling: str,
) -> bool:
    """Bind read-only billing exposure to Gate A and any Gate B ceiling."""

    cleaned_bound = clean_cell(bound)
    approved_posture = clean_cell(cost_posture)
    try:
        owner_cap = parse_cost_posture(approved_posture)
    except ValueError:
        return False
    if cleaned_bound == approved_posture:
        candidate = owner_cap
    else:
        try:
            validate_aws_cost_ceiling(cleaned_bound, approved_posture)
        except ValueError:
            return False
        candidate = _parse_cost_ceiling(cleaned_bound)
    gate_value = clean_cell(gate_b_cost_ceiling)
    if gate_value.startswith("NOT_APPLICABLE"):
        return True
    gate_cap = _parse_cost_ceiling(gate_value)
    return (
        candidate is not None
        and gate_cap is not None
        and _cost_at_most(candidate, gate_cap)
    )


def _envelope_scalar(envelope: Mapping[str, str], field: str, label: str) -> str | None:
    value = clean_cell(envelope.get(field, ""))
    prefix = label + ":"
    if not value.startswith(prefix):
        return None
    candidate = clean_cell(value[len(prefix) :])
    return candidate if explicit_value(candidate, allow_none=False) else None


def _envelope_values(envelope: Mapping[str, str], field: str, label: str) -> list[str]:
    value = clean_cell(envelope.get(field, ""))
    prefix = label + ":"
    if not value.startswith(prefix):
        return []
    return _split_authority_values(value[len(prefix) :])


def _receipt_identity_matches_gate_b(
    fields: Mapping[str, str], envelope: Mapping[str, str]
) -> bool:
    try:
        environment, _environment_class = parse_aws_environment(
            envelope.get("AWS environment", "")
        )
    except ValueError:
        return False
    expected = {
        "Profile or role": _envelope_scalar(envelope, "AWS role or profile", "ROLE"),
        "Account": _envelope_scalar(envelope, "AWS account", "ACCOUNT"),
        "Region": _envelope_scalar(envelope, "AWS Region", "REGION"),
        "Environment": environment,
    }
    return all(
        expected_value is not None and fields.get(field) == expected_value
        for field, expected_value in expected.items()
    )


def _receipt_scope_within_gate_b(
    resources: list[str],
    operations: list[str],
    envelope: Mapping[str, str],
) -> bool:
    allowed_resources = set(
        _envelope_values(envelope, "AWS resource allowlist", "RESOURCES")
    )
    allowed_operations = set(
        _envelope_values(envelope, "AWS allowed operations", "OPERATIONS")
    )
    unsafe = any("*" in item for item in resources + operations)
    return bool(
        resources
        and operations
        and not unsafe
        and len(resources) == len(set(resources))
        and len(operations) == len(set(operations))
        and set(resources).issubset(allowed_resources)
        and set(operations).issubset(allowed_operations)
    )


def _receipt_artifact_matches_gate_b(
    artifact: str,
    envelope: Mapping[str, str],
    active_artifact: str,
) -> bool:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", artifact) is None:
        return False
    if artifact != clean_cell(active_artifact):
        return False
    approved = clean_cell(envelope.get("AWS artifact authorization and provenance", ""))
    if approved.startswith("NOT_APPLICABLE"):
        return envelope.get("AWS boundary") == "READ_ONLY"
    if AWS_EXACT_ARTIFACT.fullmatch(approved) is not None:
        return artifact == approved.removeprefix("EXACT_DIGEST: ")
    try:
        validate_aws_artifact(
            approved, clean_cell(envelope.get("Authorized baseline commit", ""))
        )
    except ValueError:
        return False
    return AWS_DERIVED_ARTIFACT.fullmatch(approved) is not None


def _authorization_expiry_ceiling(value: str, *, allow_expired: bool) -> datetime:
    if not allow_expired:
        return parse_future_expiry(value)
    cleaned = clean_cell(value)
    match = re.fullmatch(
        r"Expires at (?P<timestamp>[^\s;]+); earlier completion: (?P<condition>[^\r\n]+)",
        cleaned,
    )
    if match is None or not explicit_value(match.group("condition"), allow_none=False):
        raise ValueError("Authorization expiry is not canonical")
    expires_at = _iso_datetime(match.group("timestamp"))
    if expires_at is None:
        raise ValueError("Authorization expiry timestamp is not ISO 8601 with timezone")
    return expires_at


def _receipt_validity_within_gate_b(
    valid_until: str,
    result: str,
    envelope: Mapping[str, str],
    *,
    allow_expired: bool = False,
) -> str | None:
    current = _authorization_valid_until(
        valid_until, result, allow_expired=allow_expired
    )
    if current is None:
        return None
    try:
        ceilings = [
            _authorization_expiry_ceiling(
                envelope.get("Authorization expiry or completion condition", ""),
                allow_expired=allow_expired,
            )
        ]
    except ValueError:
        return None
    aws_validity = clean_cell(envelope.get("AWS authorization validity", ""))
    if not aws_validity.startswith("NOT_APPLICABLE"):
        try:
            ceilings.append(
                _authorization_expiry_ceiling(aws_validity, allow_expired=allow_expired)
            )
        except ValueError:
            return None
    if current == "ONE_OPERATION":
        return current
    expires = _iso_datetime(current)
    if expires is None:
        return None
    return current if all(expires <= ceiling for ceiling in ceilings) else None


def _gate_b_rollback_value(envelope: Mapping[str, str]) -> str | None:
    value = clean_cell(envelope.get("AWS rollback boundary", ""))
    prefix = "ROLLBACK:"
    if not value.startswith(prefix):
        return None
    candidate = clean_cell(value[len(prefix) :])
    if unresolved(candidate) or not candidate:
        return None
    return candidate


def _mutation_cost_within_gate_b(
    value: str,
    envelope: Mapping[str, str],
    cost_posture: str,
) -> bool:
    try:
        validate_aws_cost_ceiling(value, cost_posture)
    except ValueError:
        return False
    candidate = _parse_cost_ceiling(value)
    gate_cap = _parse_cost_ceiling(envelope.get("AWS cost ceiling", ""))
    return (
        candidate is not None
        and gate_cap is not None
        and _cost_at_most(candidate, gate_cap)
    )


def _exact_receipt_fields(
    receipt: str,
    expected_title: str,
    expected_fields: tuple[str, ...],
    *,
    allow_none_fields: frozenset[str] = frozenset(),
) -> dict[str, str] | None:
    lines = receipt.splitlines()
    if len(lines) != len(expected_fields) + 1 or lines[0].strip() != expected_title:
        return None
    result: dict[str, str] = {}
    for line, expected in zip(lines[1:], expected_fields):
        if ":" not in line:
            return None
        key, value = line.split(":", 1)
        if key.strip() != expected:
            return None
        value = value.strip()
        if not explicit_value(value, allow_none=expected in allow_none_fields):
            return None
        result[expected] = value
    return result


def _read_preflight_receipt_authority(
    verify_text: str,
    construction_authorization: str,
    cost_posture: str,
    envelope: Mapping[str, str],
    active_artifact: str,
    *,
    allow_one_operation: bool = True,
    allow_expired: bool = False,
) -> dict[str, Any] | None:
    """Project one exact owner-authored read-only preflight scope."""

    try:
        receipt = marked_receipt(verify_text, "aws-read-preflight")
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS READ-ONLY PREFLIGHT",
        AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
    )
    row = _action_authorization_rows(verify_text).get("Read-only preflight")
    if fields is None or row is None or unresolved(receipt):
        return None
    authorization_id = fields["Read authorization"]
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    result = clean_cell(row.get("Result", ""))
    valid_until = _receipt_validity_within_gate_b(
        fields["Valid until"],
        result,
        envelope,
        allow_expired=allow_expired,
    )
    if valid_until == "ONE_OPERATION" and not allow_one_operation:
        return None
    cost_validity = clean_cell(row.get("Cost ceiling and validity", ""))
    cost_match = re.fullmatch(
        r"COST: (?P<effect>.+?); BOUNDED_BY: (?P<bound>.+?); VALID_UNTIL: (?P<until>.+)",
        cost_validity,
    )
    valid_cost_provenance = bool(
        cost_match
        and explicit_value(cost_match.group("effect"), allow_none=False)
        and explicit_value(cost_match.group("bound"), allow_none=False)
        and not clean_cell(cost_match.group("effect")).startswith("NOT_APPLICABLE")
        and not clean_cell(cost_match.group("bound")).startswith("NOT_APPLICABLE")
        and _read_bound_honors_cost_posture(
            cost_match.group("bound"),
            cost_posture,
            envelope.get("AWS cost ceiling", ""),
        )
        and clean_cell(cost_match.group("until")) == fields["Valid until"]
    )
    read_cost = (
        f"EXPECTED: {clean_cell(cost_match.group('effect'))}; "
        f"BOUNDED_BY: {clean_cell(cost_match.group('bound'))}"
        if cost_match
        else "NONE"
    )
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    expected_resources = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed read-only operations']}"
    )
    observed_at = clean_cell(row.get("Observed at", ""))
    if (
        AWS_READ_AUTHORIZATION_ID.fullmatch(authorization_id) is None
        or fields["Construction authorization"] != construction_authorization
        or fields["Prohibited operations"] != "ALL_MUTATIONS"
        or row.get("Authorization ID") != authorization_id
        or row.get("Construction AUTH") != construction_authorization
        or row.get("Role or profile") != fields["Profile or role"]
        or row.get("Artifact digest") != fields["Artifact digest"]
        or row.get("Account / Region / environment") != expected_scope
        or row.get("Resources and operations") != expected_resources
        or row.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(row.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(row.get("Stable owner-message source", ""))
        or not explicit_timestamp(observed_at)
        or clean_cell(row.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or not valid_cost_provenance
        or valid_until is None
        or result not in {"AUTHORIZED", "RUNNING", "READY"}
    ):
        return None
    resources = _split_authority_values(fields["Stack, application, and resources"])
    operations = _split_authority_values(fields["Allowed read-only operations"])
    if (
        not resources
        or not operations
        or any(AWS_READ_ONLY_OPERATION.fullmatch(item) is None for item in operations)
        or not _receipt_identity_matches_gate_b(fields, envelope)
        or not _receipt_scope_within_gate_b(resources, operations, envelope)
        or not _receipt_artifact_matches_gate_b(
            fields["Artifact digest"], envelope, active_artifact
        )
    ):
        return None
    return {
        "kind": "AWS_READ_ONLY",
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "account": fields["Account"],
        "region": fields["Region"],
        "environment": fields["Environment"],
        "role_or_profile": fields["Profile or role"],
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {
            "artifact": fields["Artifact digest"],
            "plan": "NONE",
        },
        "cost_ceiling": read_cost,
        "rollback_boundary": "NONE",
        "expiration": valid_until,
        "authorized_at": observed_at,
        "authority_source": clean_cell(row.get("Stable owner-message source", "")),
    }


def _deployment_reconciliation_read_authority(
    verify_text: str,
    cost_posture: str,
    group: list[dict[str, str]],
    *,
    allow_expired: bool = False,
    require_post_action_freshness: bool = False,
) -> dict[str, Any] | None:
    """Project exact read-only scope for current or restricted reconciliation."""

    if not group:
        return None
    first = group[0]
    basis_match = re.fullmatch(
        r"REQ-\d{4,} / DES-\d{4,} / (?P<auth>AUTH-\d{4,})",
        clean_cell(first.get("REQ / DES / AUTH", "")),
    )
    scope_match = re.fullmatch(
        r"ACCOUNT: (?P<account>[^;]+); REGION: (?P<region>[^;]+); "
        r"ENVIRONMENT: (?P<environment>[^;]+)",
        clean_cell(first.get("Account / Region / environment", "")),
    )
    if basis_match is None or scope_match is None:
        return None
    account = clean_cell(scope_match.group("account"))
    region = clean_cell(scope_match.group("region"))
    environment = clean_cell(scope_match.group("environment"))
    artifact = clean_cell(first.get("Artifact digest", ""))
    if (
        any(
            not explicit_value(value, allow_none=False) or "*" in value
            for value in (account, region, environment)
        )
        or re.fullmatch(r"sha256:[0-9a-f]{64}", artifact) is None
    ):
        return None
    try:
        attempted_resources = _deployment_values(
            first.get("Resources", ""), "Resources", allow_none=False
        )
        receipt = marked_receipt(verify_text, "aws-read-preflight")
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS READ-ONLY PREFLIGHT",
        AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
    )
    row = _action_authorization_rows(verify_text).get("Read-only preflight")
    if fields is None or row is None or unresolved(receipt):
        return None
    authorization_id = fields["Read authorization"]
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    result = clean_cell(row.get("Result", ""))
    valid_until = _authorization_valid_until(
        fields["Valid until"], result, allow_expired=allow_expired
    )
    if valid_until in {None, "ONE_OPERATION"}:
        return None
    cost_validity = clean_cell(row.get("Cost ceiling and validity", ""))
    cost_match = re.fullmatch(
        r"COST: (?P<effect>.+?); BOUNDED_BY: (?P<bound>.+?); VALID_UNTIL: (?P<until>.+)",
        cost_validity,
    )
    valid_cost_provenance = bool(
        cost_match
        and explicit_value(cost_match.group("effect"), allow_none=False)
        and explicit_value(cost_match.group("bound"), allow_none=False)
        and not clean_cell(cost_match.group("effect")).startswith("NOT_APPLICABLE")
        and not clean_cell(cost_match.group("bound")).startswith("NOT_APPLICABLE")
        and _read_bound_honors_cost_posture(
            cost_match.group("bound"),
            cost_posture,
            "NOT_APPLICABLE — reconciliation receipt is the read-only ceiling",
        )
        and clean_cell(cost_match.group("until")) == fields["Valid until"]
    )
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    expected_resources = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed read-only operations']}"
    )
    observed_at = clean_cell(row.get("Observed at", ""))
    authorized_at = _iso_datetime(observed_at)
    if (
        AWS_READ_AUTHORIZATION_ID.fullmatch(authorization_id) is None
        or fields["Construction authorization"] != basis_match.group("auth")
        or fields["Prohibited operations"] != "ALL_MUTATIONS"
        or fields["Account"] != account
        or fields["Region"] != region
        or fields["Environment"] != environment
        or fields["Artifact digest"] != artifact
        or row.get("Authorization ID") != authorization_id
        or row.get("Construction AUTH") != basis_match.group("auth")
        or row.get("Role or profile") != fields["Profile or role"]
        or row.get("Artifact digest") != artifact
        or row.get("Account / Region / environment") != expected_scope
        or row.get("Resources and operations") != expected_resources
        or row.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(row.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(
            row.get("Stable owner-message source", ""), allow_none=False
        )
        or "*" in clean_cell(row.get("Stable owner-message source", ""))
        or authorized_at is None
        or clean_cell(row.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or not valid_cost_provenance
        or result not in {"AUTHORIZED", "RUNNING", "READY"}
    ):
        return None
    resources = _split_authority_values(fields["Stack, application, and resources"])
    operations = _split_authority_values(fields["Allowed read-only operations"])
    if (
        not resources
        or not operations
        or len(resources) != len(set(resources))
        or len(operations) != len(set(operations))
        or any("*" in item for item in resources + operations)
        or set(resources) != set(attempted_resources)
        or any(AWS_READ_ONLY_OPERATION.fullmatch(item) is None for item in operations)
    ):
        return None

    if require_post_action_freshness:
        terminal_reconciliation = (
            group[-1]
            if clean_cell(group[-1].get("Phase", "")) == "AWS-30"
            and clean_cell(group[-1].get("Status", "")) in {"COMPLETE", "BLOCKED"}
            else None
        )
        if terminal_reconciliation is None:
            prior_times = [_iso_datetime(item.get("Observed at", "")) for item in group]
            if any(item is None for item in prior_times) or authorized_at <= max(
                prior_times
            ):
                return None
        else:
            prior_times = [
                _iso_datetime(item.get("Observed at", "")) for item in group[:-1]
            ]
            terminal_at = _iso_datetime(terminal_reconciliation.get("Observed at", ""))
            if (
                not prior_times
                or any(item is None for item in prior_times)
                or terminal_at is None
                or authorized_at <= max(prior_times)
                or authorized_at > terminal_at
            ):
                return None

    read_cost = (
        f"EXPECTED: {clean_cell(cost_match.group('effect'))}; "
        f"BOUNDED_BY: {clean_cell(cost_match.group('bound'))}"
        if cost_match
        else "NONE"
    )
    return {
        "kind": "AWS_READ_ONLY",
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "account": account,
        "region": region,
        "environment": environment,
        "role_or_profile": fields["Profile or role"],
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {"artifact": artifact, "plan": "NONE"},
        "cost_ceiling": read_cost,
        "rollback_boundary": "NONE",
        "expiration": valid_until,
        "authorized_at": observed_at,
        "authority_source": clean_cell(row.get("Stable owner-message source", "")),
        "reconciliation_only": require_post_action_freshness,
        "attempt_id": clean_cell(first.get("Attempt ID", "")),
    }


def parse_read_preflight_evidence(text: str) -> list[dict[str, str]]:
    table = contract_table_after_heading(
        text, AWS_READ_PREFLIGHT_HEADING, AWS_READ_PREFLIGHT_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def parse_teardown_reconciliation_evidence(text: str) -> list[dict[str, str]]:
    table = contract_table_after_heading(
        text, AWS_TEARDOWN_EVIDENCE_HEADING, AWS_TEARDOWN_EVIDENCE_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def parse_deployment_reconciliation_evidence(
    text: str,
) -> list[dict[str, str]]:
    """Parse the append-only AWS-20/AWS-30 deployment operation journal."""

    table = contract_table_after_heading(
        text, AWS_DEPLOYMENT_EVIDENCE_HEADING, AWS_DEPLOYMENT_EVIDENCE_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def parse_verification_matrix(text: str) -> list[dict[str, str]]:
    """Parse the canonical release acceptance registry."""

    table = contract_table_after_heading(
        text, VERIFICATION_MATRIX_HEADING, VERIFICATION_MATRIX_HEADERS
    )
    if table is None:
        return []
    return [dict(zip(table.headers, row)) for row in table.rows]


def _deployment_acceptance_evidence_issues(
    verify_text: str,
    evidence_ids: list[str],
    expected: Mapping[str, Any],
) -> list[str]:
    """Resolve AWS-30 COMPLETE IDs to current VERIFIED target-bound evidence."""

    try:
        rows = parse_verification_matrix(verify_text)
    except ValueError as exc:
        return [str(exc)]
    by_id: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id):
            by_id.setdefault(evidence_id, []).append(row)
    expected_target = (
        f"ARTIFACT: {expected.get('artifact')}; ACCOUNT: {expected.get('account')}; "
        f"REGION: {expected.get('region')}; ENVIRONMENT: {expected.get('environment')}"
    )
    issues: list[str] = []
    for evidence_id in evidence_ids:
        matching = by_id.get(evidence_id, [])
        if len(matching) != 1:
            issues.append(
                f"{evidence_id} must resolve exactly once in the Verification matrix"
            )
            continue
        row = matching[0]
        if clean_cell(row.get("Status", "")) != "VERIFIED":
            issues.append(f"{evidence_id} Verification matrix status must be VERIFIED")
        requirement = clean_cell(row.get("Requirement or invariant", ""))
        manual_evidence = clean_cell(row.get("AWS/manual evidence", ""))
        if not explicit_value(requirement, allow_none=False) or "*" in requirement:
            issues.append(f"{evidence_id} requires a concrete requirement or invariant")
        if (
            not explicit_value(manual_evidence, allow_none=False)
            or "*" in manual_evidence
        ):
            issues.append(f"{evidence_id} requires concrete AWS/manual evidence")
        if clean_cell(row.get("Artifact/environment", "")) != expected_target:
            issues.append(
                f"{evidence_id} does not bind the exact artifact/account/Region/environment"
            )
    return issues


def _deployment_operation_result_issues(
    value: str, evidence_id: str, *, started: bool
) -> list[str]:
    """Validate the machine-readable operation identifier and direct-result grammar."""

    cleaned = clean_cell(value)
    if started:
        return (
            []
            if cleaned == AWS_DEPLOYMENT_PRECALL_RESULT
            else [f"{evidence_id} STARTED must use the exact pre-call result sentinel"]
        )
    match = re.fullmatch(
        r"IDENTIFIERS: (?P<identifiers>.+); RESULT: (?P<result>.+)", cleaned
    )
    if match is None:
        return [
            f"{evidence_id} post-call result must use IDENTIFIERS: <list or NONE reason>; RESULT: <direct result>"
        ]
    identifiers = clean_cell(match.group("identifiers"))
    result = clean_cell(match.group("result"))
    none_match = re.fullmatch(r"NONE \u2014 (?P<reason>.+)", identifiers)
    if none_match is not None:
        reason = clean_cell(none_match.group("reason"))
        if not explicit_value(reason, allow_none=False) or "*" in reason:
            return [f"{evidence_id} NONE identifiers require a concrete reason"]
    else:
        values = [item.strip() for item in identifiers.split(",")]
        if (
            not values
            or len(values) != len(set(values))
            or any(
                not explicit_value(item, allow_none=False)
                or "*" in item
                or re.search(r"[\r\n\x00-\x1f\x7f]", item) is not None
                for item in values
            )
        ):
            return [
                f"{evidence_id} operation identifiers must be a unique exact wildcard-free list"
            ]
    if not explicit_value(result, allow_none=False) or "*" in result:
        return [f"{evidence_id} requires a concrete direct result"]
    return []


def _deployment_values(value: str, label: str, *, allow_none: bool) -> list[str]:
    cleaned = clean_cell(value)
    if allow_none and cleaned == "NONE":
        return []
    values = _split_authority_values(cleaned)
    if (
        not values
        or len(values) != len(set(values))
        or any("*" in item for item in values)
    ):
        raise ValueError(f"{label} must be a unique wildcard-free exact list")
    return values


def _deployment_evidence_ids(value: str, *, allow_none: bool) -> list[str]:
    values = _deployment_values(value, "Acceptance evidence IDs", allow_none=allow_none)
    if any(re.fullmatch(r"EV-\d{4,}", item) is None for item in values):
        raise ValueError(
            "Acceptance evidence IDs must be a unique comma-separated EV list or NONE"
        )
    return values


def _deployment_expected_binding(
    verify_text: str,
    *,
    construction_authorization: str,
    envelope: Mapping[str, str],
    lane: str | None,
    artifact_binding: str,
    gate_b_authority_source: str = "",
    gate_b_authorized_at: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """Return the current mutation ceiling without treating it as an attempt."""

    issues: list[str] = []
    if construction_authorization == "NONE":
        return {}, ["deployment evidence requires a current construction authorization"]
    if lane not in {"fast-dev", "explicit-gate"}:
        return {}, ["deployment evidence is not permitted for the selected AWS lane"]
    try:
        environment, _environment_class = parse_aws_environment(
            envelope.get("AWS environment", "")
        )
    except ValueError:
        environment = ""
    account = _envelope_scalar(envelope, "AWS account", "ACCOUNT")
    region = _envelope_scalar(envelope, "AWS Region", "REGION")
    deployment_role = _envelope_scalar(envelope, "AWS role or profile", "ROLE")
    resources = _envelope_values(envelope, "AWS resource allowlist", "RESOURCES")
    allowed_operations = _envelope_values(
        envelope, "AWS allowed operations", "OPERATIONS"
    )
    operations = (
        [
            operation
            for operation in allowed_operations
            if AWS_READ_ONLY_OPERATION.fullmatch(operation) is None
        ]
        if lane == "fast-dev"
        else allowed_operations
    )
    for label, value in (
        ("AWS account", account),
        ("AWS Region", region),
        ("AWS environment", environment),
        ("AWS role or profile", deployment_role),
    ):
        if not value:
            issues.append(f"deployment evidence requires exact {label}")
    if not resources or not operations:
        issues.append(
            "deployment evidence requires exact Gate B resources and operations"
        )
    if not _receipt_artifact_matches_gate_b(
        artifact_binding, envelope, artifact_binding
    ):
        issues.append("deployment evidence artifact is outside current Gate B")
    authorization_validity = clean_cell(envelope.get("AWS authorization validity", ""))
    validity_match = re.fullmatch(
        r"Expires at (?P<timestamp>[^\s;]+); earlier completion: [^\r\n]+",
        authorization_validity,
    )
    expected: dict[str, Any] = {
        "authorization_id": construction_authorization,
        "receipt_digest": "NONE",
        "authorized_at": clean_cell(gate_b_authorized_at),
        "valid_until": (
            validity_match.group("timestamp") if validity_match is not None else "NONE"
        ),
        "deployment_role": deployment_role or "NONE",
        "deployment_authority_source": clean_cell(gate_b_authority_source),
        "artifact": artifact_binding,
        "plan": clean_cell(envelope.get("AWS stack or application", "")),
        "account": account or "NONE",
        "region": region or "NONE",
        "environment": environment or "NONE",
        "resources": resources,
        "operations": operations,
        "verify_text": verify_text,
    }
    if lane == "fast-dev":
        if validity_match is None:
            issues.append(
                "fast-dev deployment evidence requires exact authorization validity"
            )
        if not explicit_timestamp(expected["authorized_at"]):
            issues.append(
                "fast-dev deployment evidence requires the Gate B authorization timestamp"
            )
        if not explicit_value(expected["plan"], allow_none=False):
            issues.append(
                "fast-dev deployment evidence requires an exact stack or application"
            )
        if (
            not explicit_value(
                expected["deployment_authority_source"], allow_none=False
            )
            or "*" in expected["deployment_authority_source"]
        ):
            issues.append(
                "fast-dev deployment evidence requires the Gate B owner authorization source"
            )
        return expected, issues

    try:
        receipt = marked_receipt(verify_text, "aws-deployment")
        provenance = _action_authorization_rows(verify_text).get("Deployment")
    except ValueError:
        receipt = ""
        provenance = None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS DEPLOYMENT",
        AWS_DEPLOYMENT_RECEIPT_FIELDS,
        allow_none_fields=frozenset({"Rollback boundary"}),
    )
    digest = (
        "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        if receipt
        else "NONE"
    )
    if fields is None or provenance is None or unresolved(receipt):
        issues.append(
            "explicit-gate deployment evidence requires one exact owner-authored receipt"
        )
        return expected, issues
    receipt_resources = _split_authority_values(
        fields["Stack, application, and resources"]
    )
    receipt_operations = _split_authority_values(fields["Allowed operations"])
    receipt_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    receipt_resources_and_operations = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed operations']}"
    )
    expected.update(
        {
            "authorization_id": fields["AWS authorization"],
            "receipt_digest": digest,
            "authorized_at": clean_cell(provenance.get("Observed at", "")),
            "valid_until": fields["Valid until"],
            "deployment_role": fields["Profile or role"],
            "deployment_authority_source": clean_cell(
                provenance.get("Stable owner-message source", "")
            ),
            "artifact": fields["Artifact digest"],
            "plan": fields["IaC plan/change-set binding"],
            "account": fields["Account"],
            "region": fields["Region"],
            "environment": fields["Environment"],
            "resources": receipt_resources,
            "operations": receipt_operations,
        }
    )
    receipt_binding_invalid = (
        re.fullmatch(r"AWS-AUTH-\d{4,}", fields["AWS authorization"]) is None
        or fields["Construction authorization"] != construction_authorization
        or AWS_PLAN_BINDING.fullmatch(fields["IaC plan/change-set binding"]) is None
        or not _receipt_identity_matches_gate_b(fields, envelope)
        or not _receipt_scope_within_gate_b(
            receipt_resources, receipt_operations, envelope
        )
        or not _receipt_artifact_matches_gate_b(
            fields["Artifact digest"], envelope, artifact_binding
        )
        or fields["Rollback boundary"] != _gate_b_rollback_value(envelope)
    )
    provenance_invalid = (
        provenance.get("Authorization ID") != fields["AWS authorization"]
        or provenance.get("Construction AUTH") != construction_authorization
        or provenance.get("Role or profile") != fields["Profile or role"]
        or provenance.get("Artifact digest") != fields["Artifact digest"]
        or provenance.get("IaC plan/change-set binding")
        != fields["IaC plan/change-set binding"]
        or provenance.get("Account / Region / environment") != receipt_scope
        or provenance.get("Resources and operations")
        != receipt_resources_and_operations
        or provenance.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(provenance.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(
            provenance.get("Stable owner-message source", ""), allow_none=False
        )
        or not explicit_timestamp(provenance.get("Observed at", ""))
        or clean_cell(provenance.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or clean_cell(provenance.get("Result", ""))
        not in {"AUTHORIZED", "RUNNING", "READY"}
        or AWS_PREFLIGHT_ID.fullmatch(
            clean_cell(provenance.get("Preflight evidence", ""))
        )
        is None
    )
    if receipt_binding_invalid:
        issues.append(
            "deployment receipt does not match current Gate B identity, scope, "
            "artifact, plan, or rollback boundary"
        )
    if provenance_invalid:
        issues.append(
            "deployment receipt does not match its exact authorization provenance"
        )
    return expected, issues


def _deployment_row_binding_issues(
    row: Mapping[str, str],
    expected: Mapping[str, Any],
    read_authority: Mapping[str, Any] | None,
    *,
    historical: bool = False,
) -> list[str]:
    evidence_id = clean_cell(row.get("Evidence ID", "")) or "deployment row"
    phase = clean_cell(row.get("Phase", ""))
    status = clean_cell(row.get("Status", ""))
    issues: list[str] = []
    expected_scope = (
        f"ACCOUNT: {expected.get('account')}; REGION: {expected.get('region')}; "
        f"ENVIRONMENT: {expected.get('environment')}"
    )
    scalar_fields = {
        "Deployment authorization": expected.get("authorization_id"),
        "Deployment receipt digest": expected.get("receipt_digest"),
        "Deployment valid until": expected.get("valid_until"),
        "Deployment authority source": expected.get("deployment_authority_source"),
        "Deployment role or profile": expected.get("deployment_role"),
        "Artifact digest": expected.get("artifact"),
        "Plan/change-set binding": expected.get("plan"),
        "Account / Region / environment": expected_scope,
    }
    for field_name, value in scalar_fields.items():
        if clean_cell(row.get(field_name, "")) != clean_cell(value):
            issues.append(f"{evidence_id} {field_name} does not match its authority")
    try:
        resources = _deployment_values(
            row.get("Resources", ""), "Resources", allow_none=False
        )
        operations = _deployment_values(
            row.get("Mutation operations", ""),
            "Mutation operations",
            allow_none=False,
        )
    except ValueError as exc:
        issues.append(str(exc))
        resources, operations = [], []
    if set(resources) != set(expected.get("resources", [])):
        issues.append(f"{evidence_id} Resources do not match the attempted scope")
    if set(operations) != set(expected.get("operations", [])):
        issues.append(
            f"{evidence_id} Mutation operations do not match the attempted scope"
        )
    started = phase == "AWS-20" and status == "STARTED"
    operation_result = clean_cell(
        row.get("Operation identifiers and direct result", "")
    )
    issues.extend(
        _deployment_operation_result_issues(
            operation_result, evidence_id, started=started
        )
    )
    rollback_result = clean_cell(row.get("Rollback result", ""))
    if started and rollback_result != "NONE":
        issues.append(f"{evidence_id} STARTED must use Rollback result = NONE")
    for field_name, allow_none in (
        ("Rollback result", True),
        ("Durable source", False),
    ):
        if not explicit_value(row.get(field_name, ""), allow_none=allow_none):
            issues.append(f"{evidence_id} requires {field_name}")
    blocker_reason = clean_cell(row.get("Blocker or stale reason", ""))
    if status in {"BLOCKED", "STALE"}:
        if not explicit_value(blocker_reason, allow_none=False):
            issues.append(f"{evidence_id} requires an exact blocker or stale reason")
    elif blocker_reason != "NONE":
        issues.append(f"{evidence_id} must use Blocker or stale reason = NONE")
    identity = clean_cell(row.get("Identity and boundary match", ""))
    if phase == "AWS-20":
        for field_name in (
            "Read authorization",
            "Read role or profile",
            "Read receipt digest",
            "Read valid until",
            "Read authority source",
            "Read operations observed",
            "Acceptance evidence IDs",
        ):
            if clean_cell(row.get(field_name, "")) != "NONE":
                issues.append(f"{evidence_id} AWS-20 requires {field_name} = NONE")
        if identity not in {"PASS", "VERIFIED"}:
            issues.append(
                f"{evidence_id} AWS-20 requires verified identity and boundary"
            )
        return issues

    read_id = clean_cell(row.get("Read authorization", ""))
    read_role = clean_cell(row.get("Read role or profile", ""))
    read_digest = clean_cell(row.get("Read receipt digest", ""))
    read_valid_until = clean_cell(row.get("Read valid until", ""))
    read_source = clean_cell(row.get("Read authority source", ""))
    read_provenance = _parse_deployment_read_provenance(read_source)
    if AWS_READ_AUTHORIZATION_ID.fullmatch(read_id) is None:
        issues.append(f"{evidence_id} AWS-30 requires a separate read authorization")
    if not explicit_value(read_role, allow_none=False):
        issues.append(f"{evidence_id} AWS-30 requires a separate read role")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", read_digest) is None:
        issues.append(f"{evidence_id} AWS-30 requires an exact read receipt digest")
    read_expiry = _iso_datetime(read_valid_until)
    observed_at = _iso_datetime(row.get("Observed at", ""))
    if read_valid_until == "ONE_OPERATION" or read_expiry is None:
        issues.append(f"{evidence_id} AWS-30 requires reusable ISO read validity")
    elif observed_at is not None and observed_at > read_expiry:
        issues.append(f"{evidence_id} AWS-30 was observed after read authority expiry")
    if read_provenance is None:
        issues.append(
            f"{evidence_id} AWS-30 requires the exact durable read authority "
            "source, authorization time, resources, and operations envelope"
        )
    try:
        observed_reads = _deployment_values(
            row.get("Read operations observed", ""),
            "Read operations observed",
            allow_none=status == "STALE",
        )
        acceptance_ids = _deployment_evidence_ids(
            row.get("Acceptance evidence IDs", ""),
            allow_none=status != "COMPLETE",
        )
    except ValueError as exc:
        issues.append(str(exc))
        observed_reads, acceptance_ids = [], []
    if read_provenance is not None:
        read_authorized_at = _iso_datetime(read_provenance["authorized_at"])
        if (
            observed_at is not None
            and read_authorized_at is not None
            and observed_at < read_authorized_at
        ):
            issues.append(
                f"{evidence_id} AWS-30 observation precedes read authorization"
            )
        if resources != read_provenance["resources"]:
            issues.append(
                f"{evidence_id} Resources do not match the durable read authorization"
            )
        if not set(observed_reads).issubset(set(read_provenance["operations"])):
            issues.append(
                f"{evidence_id} observed reads exceed the durable read authorization"
            )
    if status in {"COMPLETE", "BLOCKED"} and identity not in {"PASS", "VERIFIED"}:
        issues.append(f"{evidence_id} AWS-30 requires verified identity and boundary")
    if status == "STALE" and not explicit_value(identity, allow_none=False):
        issues.append(
            f"{evidence_id} STALE requires a concrete identity and boundary result"
        )
    if (
        status in {"COMPLETE", "BLOCKED"}
        and not historical
        and read_authority is not None
    ):
        same_read_id = read_id == clean_cell(read_authority.get("authorization_id", ""))
        if not same_read_id:
            issues.append(
                f"{evidence_id} read authorization does not match current authority"
            )
        else:
            read_scope = (
                f"ACCOUNT: {read_authority.get('account')}; "
                f"REGION: {read_authority.get('region')}; "
                f"ENVIRONMENT: {read_authority.get('environment')}"
            )
            read_authorized_at = _iso_datetime(read_authority.get("authorized_at", ""))
            if read_authorized_at is None:
                issues.append(f"{evidence_id} read authorization timestamp is invalid")
            elif observed_at is not None and observed_at < read_authorized_at:
                issues.append(
                    f"{evidence_id} AWS-30 observation precedes read authorization"
                )
            if read_role != clean_cell(read_authority.get("role_or_profile", "")):
                issues.append(f"{evidence_id} read role does not match its receipt")
            if read_digest != clean_cell(read_authority.get("receipt_digest", "")):
                issues.append(f"{evidence_id} read receipt digest is tampered")
            if read_valid_until != clean_cell(read_authority.get("expiration", "")):
                issues.append(f"{evidence_id} read validity is tampered")
            expected_read_source = _format_deployment_read_provenance(
                clean_cell(read_authority.get("authority_source", "")),
                clean_cell(read_authority.get("authorized_at", "")),
                read_authority.get("resources", []),
                read_authority.get("operations", []),
            )
            if read_source != expected_read_source:
                issues.append(f"{evidence_id} read authority provenance is tampered")
            if expected_scope != read_scope:
                issues.append(f"{evidence_id} read account boundary is stale")
            if resources != list(read_authority.get("resources", [])):
                issues.append(
                    f"{evidence_id} attempted resources do not match read scope"
                )
            if not set(observed_reads).issubset(
                set(read_authority.get("operations", []))
            ):
                issues.append(
                    f"{evidence_id} observed reads exceed the read authorization"
                )
    if status == "COMPLETE":
        if not acceptance_ids:
            issues.append(f"{evidence_id} COMPLETE requires acceptance evidence IDs")
        else:
            issues.extend(
                _deployment_acceptance_evidence_issues(
                    str(expected.get("verify_text", "")), acceptance_ids, expected
                )
            )
    return issues


def _format_deployment_read_provenance(
    source: str,
    authorized_at: str,
    resources: Any,
    operations: Any,
) -> str:
    """Format the exact durable AWS-30 read-authorization envelope."""

    resource_values = list(resources) if isinstance(resources, (list, tuple)) else []
    operation_values = list(operations) if isinstance(operations, (list, tuple)) else []
    return (
        f"SOURCE: {clean_cell(source)}; AUTHORIZED_AT: {clean_cell(authorized_at)}; "
        f"RESOURCES: {', '.join(clean_cell(item) for item in resource_values)}; "
        f"OPERATIONS: {', '.join(clean_cell(item) for item in operation_values)}"
    )


def _parse_deployment_read_provenance(value: str) -> dict[str, Any] | None:
    """Parse one canonical AWS-30 envelope without reviving its authority."""

    cleaned = clean_cell(value)
    match = AWS_DEPLOYMENT_READ_PROVENANCE.fullmatch(cleaned)
    if match is None:
        return None
    source = clean_cell(match.group("source"))
    authorized_at = clean_cell(match.group("authorized_at"))
    try:
        resources = _deployment_values(
            match.group("resources"), "Read-authorized resources", allow_none=False
        )
        operations = _deployment_values(
            match.group("operations"), "Read-authorized operations", allow_none=False
        )
    except ValueError:
        return None
    if (
        not explicit_value(source, allow_none=False)
        or "*" in source
        or _iso_datetime(authorized_at) is None
        or any(AWS_READ_ONLY_OPERATION.fullmatch(item) is None for item in operations)
    ):
        return None
    canonical = _format_deployment_read_provenance(
        source, authorized_at, resources, operations
    )
    if cleaned != canonical:
        return None
    return {
        "source": source,
        "authorized_at": authorized_at,
        "resources": resources,
        "operations": operations,
    }


def _deployment_historical_authority_proof_issues(
    group: list[dict[str, str]],
    verify_text: str,
    *,
    gate_b_authority_source: str,
    gate_b_authorized_at: str,
) -> list[str]:
    """Prove a stale STARTED row followed its durable original authority."""

    first = group[0]
    issues: list[str] = []
    basis = clean_cell(first.get("REQ / DES / AUTH", ""))
    basis_match = re.fullmatch(
        r"REQ-\d{4,} / DES-\d{4,} / (?P<auth>AUTH-\d{4,})", basis
    )
    started_at = _iso_datetime(first.get("Observed at", ""))
    if basis_match is None or started_at is None:
        return ["historical deployment authorization timing proof is unavailable"]

    authorization_id = clean_cell(first.get("Deployment authorization", ""))
    receipt_digest = clean_cell(first.get("Deployment receipt digest", ""))
    authority_source = clean_cell(first.get("Deployment authority source", ""))
    if receipt_digest == "NONE":
        authorized_at = _iso_datetime(gate_b_authorized_at)
        if (
            authorization_id != basis_match.group("auth")
            or authorized_at is None
            or authority_source != clean_cell(gate_b_authority_source)
            or not explicit_value(authority_source, allow_none=False)
        ):
            issues.append(
                "historical fast-dev STARTED lacks its original Gate B authorization provenance"
            )
        elif started_at < authorized_at:
            issues.append(
                "historical deployment STARTED precedes its original authorization provenance"
            )
        return issues

    try:
        receipt = marked_receipt(verify_text, "aws-deployment")
        provenance = _action_authorization_rows(verify_text).get("Deployment")
    except ValueError:
        receipt = ""
        provenance = None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS DEPLOYMENT",
        AWS_DEPLOYMENT_RECEIPT_FIELDS,
        allow_none_fields=frozenset({"Rollback boundary"}),
    )
    if fields is None or provenance is None or unresolved(receipt):
        return [
            "historical explicit-gate STARTED lacks its durable original receipt and provenance"
        ]
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    receipt_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    receipt_resources_and_operations = (
        f"RESOURCES: {fields['Stack, application, and resources']}; "
        f"OPERATIONS: {fields['Allowed operations']}"
    )
    authorized_at = _iso_datetime(provenance.get("Observed at", ""))
    binding_invalid = (
        fields["AWS authorization"] != authorization_id
        or fields["Construction authorization"] != basis_match.group("auth")
        or digest != receipt_digest
        or fields["Valid until"] != clean_cell(first.get("Deployment valid until", ""))
        or fields["Profile or role"]
        != clean_cell(first.get("Deployment role or profile", ""))
        or fields["Artifact digest"] != clean_cell(first.get("Artifact digest", ""))
        or fields["IaC plan/change-set binding"]
        != clean_cell(first.get("Plan/change-set binding", ""))
        or receipt_scope != clean_cell(first.get("Account / Region / environment", ""))
        or set(_split_authority_values(fields["Stack, application, and resources"]))
        != set(
            _deployment_values(
                first.get("Resources", ""), "Resources", allow_none=False
            )
        )
        or set(_split_authority_values(fields["Allowed operations"]))
        != set(
            _deployment_values(
                first.get("Mutation operations", ""),
                "Mutation operations",
                allow_none=False,
            )
        )
        or provenance.get("Authorization ID") != authorization_id
        or provenance.get("Construction AUTH") != basis_match.group("auth")
        or provenance.get("Role or profile") != fields["Profile or role"]
        or provenance.get("Artifact digest") != fields["Artifact digest"]
        or provenance.get("IaC plan/change-set binding")
        != fields["IaC plan/change-set binding"]
        or provenance.get("Account / Region / environment") != receipt_scope
        or provenance.get("Resources and operations")
        != receipt_resources_and_operations
        or clean_cell(provenance.get("Stable owner-message source", ""))
        != authority_source
        or provenance.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(provenance.get("Verbatim receipt SHA-256", "")) != digest
        or authorized_at is None
        or clean_cell(provenance.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or clean_cell(provenance.get("Result", ""))
        not in {"AUTHORIZED", "RUNNING", "READY"}
    )
    if binding_invalid:
        issues.append(
            "historical explicit-gate STARTED does not bind its durable original receipt and provenance"
        )
    elif started_at < authorized_at:
        issues.append(
            "historical deployment STARTED precedes its original authorization provenance"
        )
    return issues


def _deployment_historical_group_issues(
    group: list[dict[str, str]],
    verify_text: str,
    *,
    current_read_authority: Mapping[str, Any] | None = None,
    require_authorization_proof: bool = False,
    gate_b_authority_source: str = "",
    gate_b_authorized_at: str = "",
) -> list[str]:
    """Validate immutable historical rows without reviving their authority."""

    first = group[0]
    issues: list[str] = []
    scope = clean_cell(first.get("Account / Region / environment", ""))
    scope_match = re.fullmatch(
        r"ACCOUNT: (?P<account>[^;]+); REGION: (?P<region>[^;]+); "
        r"ENVIRONMENT: (?P<environment>[^;]+)",
        scope,
    )
    try:
        resources = _deployment_values(
            first.get("Resources", ""), "Resources", allow_none=False
        )
        operations = _deployment_values(
            first.get("Mutation operations", ""),
            "Mutation operations",
            allow_none=False,
        )
    except ValueError as exc:
        return [str(exc)]
    basis = clean_cell(first.get("REQ / DES / AUTH", ""))
    if re.fullmatch(r"REQ-\d{4,} / DES-\d{4,} / AUTH-\d{4,}", basis) is None:
        issues.append(
            "historical deployment attempt has a noncanonical REQ / DES / AUTH basis"
        )
    authorization_id = clean_cell(first.get("Deployment authorization", ""))
    digest = clean_cell(first.get("Deployment receipt digest", ""))
    deployment_valid_until = clean_cell(first.get("Deployment valid until", ""))
    deployment_source = clean_cell(first.get("Deployment authority source", ""))
    fast_dev = digest == "NONE"
    if fast_dev:
        if re.fullmatch(r"AUTH-\d{4,}", authorization_id) is None:
            issues.append("historical fast-dev attempt has noncanonical authority")
    elif (
        re.fullmatch(r"AWS-AUTH-\d{4,}", authorization_id) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
    ):
        issues.append("historical explicit-gate attempt has noncanonical authority")
    expires_at = _iso_datetime(deployment_valid_until)
    started_at = _iso_datetime(first.get("Observed at", ""))
    if fast_dev and expires_at is None:
        issues.append("historical fast-dev validity must be an ISO 8601 timestamp")
    elif (
        not fast_dev
        and deployment_valid_until != "ONE_OPERATION"
        and expires_at is None
    ):
        issues.append(
            "historical explicit-gate validity must be ISO 8601 or ONE_OPERATION"
        )
    elif started_at is not None and expires_at is not None and started_at > expires_at:
        issues.append("historical deployment STARTED occurred after authority expiry")
    if (
        not explicit_value(deployment_source, allow_none=False)
        or "*" in deployment_source
    ):
        issues.append("historical deployment authority source is unresolved")
    if scope_match is None:
        issues.append("historical deployment attempt has a noncanonical account scope")
        account = region = environment = "NONE"
    else:
        account = clean_cell(scope_match.group("account"))
        region = clean_cell(scope_match.group("region"))
        environment = clean_cell(scope_match.group("environment"))
        for label, value in (
            ("account", account),
            ("Region", region),
            ("environment", environment),
        ):
            if not explicit_value(value, allow_none=False) or "*" in value:
                issues.append(
                    f"historical deployment {label} must be concrete and wildcard-free"
                )
    deployment_role = clean_cell(first.get("Deployment role or profile", ""))
    artifact = clean_cell(first.get("Artifact digest", ""))
    plan = clean_cell(first.get("Plan/change-set binding", ""))
    if not explicit_value(deployment_role, allow_none=False) or "*" in deployment_role:
        issues.append(
            "historical deployment attempt requires a concrete deployment role"
        )
    if re.fullmatch(r"sha256:[0-9a-f]{64}", artifact) is None:
        issues.append("historical deployment attempt requires an exact artifact digest")
    if fast_dev:
        if not explicit_value(plan, allow_none=False) or "*" in plan:
            issues.append("historical fast-dev attempt requires an exact plan binding")
    elif AWS_PLAN_BINDING.fullmatch(plan) is None:
        issues.append(
            "historical explicit-gate attempt requires a canonical plan binding"
        )
    expected = {
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "valid_until": deployment_valid_until,
        "deployment_authority_source": deployment_source,
        "deployment_role": deployment_role,
        "artifact": artifact,
        "plan": plan,
        "account": account,
        "region": region,
        "environment": environment,
        "resources": resources,
        "operations": operations,
        "verify_text": verify_text,
    }
    if require_authorization_proof:
        issues.extend(
            _deployment_historical_authority_proof_issues(
                group,
                verify_text,
                gate_b_authority_source=gate_b_authority_source,
                gate_b_authorized_at=gate_b_authorized_at,
            )
        )
    for row in group:
        issues.extend(
            _deployment_row_binding_issues(
                row,
                expected,
                current_read_authority,
                historical=current_read_authority is None,
            )
        )
    return issues


def _deployment_group_projection(
    base: Mapping[str, Any],
    attempt_id: str,
    group: list[dict[str, str]],
) -> dict[str, Any]:
    action_rows = [row for row in group if row["Phase"] == "AWS-20"]
    terminal_rows = [
        row for row in action_rows if row["Status"] in AWS_DEPLOYMENT_TERMINAL_STATUSES
    ]
    action = terminal_rows[0] if terminal_rows else action_rows[0]
    reconciliation_rows = [row for row in group if row["Phase"] == "AWS-30"]
    reconciliation = reconciliation_rows[-1] if reconciliation_rows else None
    latest = reconciliation or action
    try:
        resources = _deployment_values(
            latest["Resources"], "Resources", allow_none=False
        )
        operations = _deployment_values(
            latest["Mutation operations"],
            "Mutation operations",
            allow_none=False,
        )
        observed_reads = (
            _deployment_values(
                latest["Read operations observed"],
                "Read operations observed",
                allow_none=latest["Status"] == "STALE",
            )
            if latest["Phase"] == "AWS-30"
            else []
        )
        acceptance_ids = (
            _deployment_evidence_ids(
                latest["Acceptance evidence IDs"],
                allow_none=latest["Status"] != "COMPLETE",
            )
            if latest["Phase"] == "AWS-30"
            else []
        )
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    reconciliation_status = (
        clean_cell(reconciliation["Status"]) if reconciliation else "NONE"
    )
    read_provenance = (
        _parse_deployment_read_provenance(latest["Read authority source"])
        if latest["Phase"] == "AWS-30"
        else None
    )
    status = (
        "ACTION_TERMINAL_REQUIRED"
        if clean_cell(action["Status"]) == "STARTED" and reconciliation is None
        else {
            "COMPLETE": "RECONCILED",
            "BLOCKED": "BLOCKED",
            "STALE": "RECONCILIATION_REQUIRED",
            "NONE": "RECONCILIATION_REQUIRED",
        }[reconciliation_status]
    )
    return {
        **base,
        "status": status,
        "attempt_id": attempt_id,
        "evidence_id": clean_cell(latest["Evidence ID"]),
        "phase": clean_cell(latest["Phase"]),
        "action_status": clean_cell(action["Status"]),
        "reconciliation_status": reconciliation_status,
        "deployment_authorization": clean_cell(latest["Deployment authorization"]),
        "deployment_receipt_digest": clean_cell(latest["Deployment receipt digest"]),
        "deployment_valid_until": clean_cell(latest["Deployment valid until"]),
        "deployment_authority_source": clean_cell(
            latest["Deployment authority source"]
        ),
        "read_authorization": clean_cell(latest["Read authorization"]),
        "deployment_role_or_profile": clean_cell(latest["Deployment role or profile"]),
        "read_role_or_profile": clean_cell(latest["Read role or profile"]),
        "read_receipt_digest": clean_cell(latest["Read receipt digest"]),
        "read_valid_until": clean_cell(latest["Read valid until"]),
        "read_authorized_at": (
            read_provenance["authorized_at"] if read_provenance else "NONE"
        ),
        "read_authorized_resources": (
            read_provenance["resources"] if read_provenance else []
        ),
        "read_authorized_operations": (
            read_provenance["operations"] if read_provenance else []
        ),
        "read_authority_source": clean_cell(latest["Read authority source"]),
        "artifact_digest": clean_cell(latest["Artifact digest"]),
        "plan_binding": clean_cell(latest["Plan/change-set binding"]),
        "resources": resources,
        "mutation_operations": operations,
        "read_operations_observed": observed_reads,
        "acceptance_evidence_ids": acceptance_ids,
        "operation_result": clean_cell(
            latest["Operation identifiers and direct result"]
        ),
        "rollback_result": clean_cell(latest["Rollback result"]),
        "identity_and_boundary_match": clean_cell(
            latest["Identity and boundary match"]
        ),
        "blocker_or_stale_reason": clean_cell(latest["Blocker or stale reason"]),
    }


def _deployment_authority_timing_issues(
    group: list[dict[str, str]], expected: Mapping[str, Any]
) -> list[str]:
    """Validate that mutation began within the exact recorded authority window."""

    issues: list[str] = []
    started_at = _iso_datetime(group[0].get("Observed at", ""))
    authorized_at = _iso_datetime(expected.get("authorized_at", ""))
    valid_until = clean_cell(expected.get("valid_until", ""))
    expires_at = None if valid_until == "ONE_OPERATION" else _iso_datetime(valid_until)
    if started_at is None:
        issues.append("deployment STARTED timestamp is invalid")
    if authorized_at is None:
        issues.append("deployment authorization timestamp is invalid")
    elif started_at is not None and started_at < authorized_at:
        issues.append("deployment STARTED precedes its authorization provenance")
    if valid_until != "ONE_OPERATION" and expires_at is None:
        issues.append("deployment authority has a noncanonical validity boundary")
    elif started_at is not None and expires_at is not None and started_at > expires_at:
        issues.append("deployment STARTED occurred after authority expiry")
    return issues


def derive_deployment_sequence_state(
    verify_text: str,
    read_authority: Mapping[str, Any] | None,
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    envelope: Mapping[str, str],
    lane: str | None,
    artifact_binding: str,
    release_evidence_cutoff: str = "NONE",
    release_state: str = "READY_TO_DEPLOY",
    gate_b_authority_source: str = "",
    gate_b_authorized_at: str = "",
    cost_posture: str = "",
    restricted_closure: bool = False,
) -> dict[str, Any]:
    """Derive AWS-20/AWS-30 sequencing without inferring an attempted action."""

    base: dict[str, Any] = {
        "status": "NOT_ACTIVE",
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "phase": "NONE",
        "action_status": "NONE",
        "reconciliation_status": "NONE",
        "deployment_authorization": "NONE",
        "deployment_receipt_digest": "NONE",
        "deployment_valid_until": "NONE",
        "deployment_authority_source": "NONE",
        "read_authorization": "NONE",
        "deployment_role_or_profile": "NONE",
        "read_role_or_profile": "NONE",
        "read_receipt_digest": "NONE",
        "read_valid_until": "NONE",
        "read_authorized_at": "NONE",
        "read_authorized_resources": [],
        "read_authorized_operations": [],
        "read_authority_source": "NONE",
        "artifact_digest": "NONE",
        "plan_binding": "NONE",
        "resources": [],
        "mutation_operations": [],
        "read_operations_observed": [],
        "acceptance_evidence_ids": [],
        "operation_result": "NONE",
        "rollback_result": "NONE",
        "identity_and_boundary_match": "NONE",
        "blocker_or_stale_reason": "NONE",
        "basis_stale": False,
        "acknowledged": False,
        "acknowledged_evidence_id": "NONE",
        "release_evidence_cutoff": release_evidence_cutoff,
        "current_mutation_authority_status": "UNAVAILABLE",
        "issues": [],
    }
    try:
        rows = parse_deployment_reconciliation_evidence(verify_text)
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    concrete: list[dict[str, str]] = []
    invalid_identifiers: list[str] = []
    for row in rows:
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id):
            concrete.append(row)
            continue
        status = clean_cell(row.get("Status", ""))
        placeholder = (
            unresolved(evidence_id)
            and status in {"", "NOT_STARTED"}
            and all(
                unresolved(row.get(header, ""))
                for header in AWS_DEPLOYMENT_EVIDENCE_HEADERS
                if header not in {"Evidence ID", "Status"}
            )
        )
        if not placeholder:
            invalid_identifiers.append(evidence_id or "EMPTY")
    if invalid_identifiers:
        return {
            **base,
            "status": "BLOCKED",
            "issues": [
                "AWS deployment evidence has noncanonical or partially populated IDs: "
                + ", ".join(sorted(invalid_identifiers))
            ],
        }
    if not concrete:
        return base
    evidence_ids = [clean_cell(row["Evidence ID"]) for row in concrete]
    if len(evidence_ids) != len(set(evidence_ids)):
        return {
            **base,
            "status": "BLOCKED",
            "issues": ["AWS deployment evidence contains duplicate Evidence IDs"],
        }
    structural_issues: list[str] = []
    timestamps: list[datetime] = []
    groups: dict[str, list[dict[str, str]]] = {}
    attempt_order: list[str] = []
    closed_attempts: set[str] = set()
    active_attempt = ""
    for row in concrete:
        evidence_id = clean_cell(row["Evidence ID"])
        attempt_id = clean_cell(row.get("Attempt ID", ""))
        phase = clean_cell(row.get("Phase", ""))
        status = clean_cell(row.get("Status", ""))
        observed_at = _iso_datetime(row.get("Observed at", ""))
        if AWS_DEPLOYMENT_ATTEMPT_ID.fullmatch(attempt_id) is None:
            structural_issues.append(f"{evidence_id} has a noncanonical Attempt ID")
        if phase == "AWS-20" and status not in AWS_DEPLOYMENT_ACTION_STATUSES:
            structural_issues.append(
                f"{evidence_id} has invalid AWS-20 status {status or 'EMPTY'}"
            )
        elif phase == "AWS-30" and status not in AWS_DEPLOYMENT_RECONCILIATION_STATUSES:
            structural_issues.append(
                f"{evidence_id} has invalid AWS-30 status {status or 'EMPTY'}"
            )
        elif phase not in {"AWS-20", "AWS-30"}:
            structural_issues.append(
                f"{evidence_id} phase must be exactly AWS-20 or AWS-30"
            )
        if observed_at is None:
            structural_issues.append(
                f"{evidence_id} Observed at must be ISO 8601 with timezone"
            )
        else:
            timestamps.append(observed_at)
        if attempt_id != active_attempt:
            if attempt_id in closed_attempts:
                structural_issues.append(
                    f"{evidence_id} reopens a noncontiguous deployment attempt"
                )
            if active_attempt:
                closed_attempts.add(active_attempt)
            active_attempt = attempt_id
            attempt_order.append(attempt_id)
        groups.setdefault(attempt_id, []).append(row)
    if len(timestamps) != len(set(timestamps)):
        structural_issues.append("AWS deployment evidence timestamps must be unique")
    if len(timestamps) == len(concrete) and timestamps != sorted(timestamps):
        structural_issues.append(
            "AWS deployment evidence must be appended in observed-time order"
        )
    replayed_authorization_ids: set[str] = set()
    replayed_receipt_digests: set[str] = set()
    for index, attempt_id in enumerate(attempt_order):
        group = groups.get(attempt_id, [])
        started = [
            row
            for row in group
            if row.get("Phase") == "AWS-20" and row.get("Status") == "STARTED"
        ]
        terminal = [
            row
            for row in group
            if row.get("Phase") == "AWS-20"
            and row.get("Status") in AWS_DEPLOYMENT_TERMINAL_STATUSES
        ]
        reconciliations = [row for row in group if row.get("Phase") == "AWS-30"]
        if len(started) != 1 or not group or group[0] not in started:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} requires exactly one first AWS-20 STARTED row"
            )
        if len(terminal) > 1:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} has more than one AWS-20 terminal row"
            )
        if reconciliations and len(terminal) != 1:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} AWS-30 requires one prior AWS-20 terminal row"
            )
        elif reconciliations:
            terminal_index = group.index(terminal[0])
            if any(group.index(row) < terminal_index for row in reconciliations):
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} AWS-30 must follow the AWS-20 terminal row"
                )
        stale_reconciliations = [
            row for row in reconciliations if row.get("Status") == "STALE"
        ]
        terminal_reconciliations = [
            row
            for row in reconciliations
            if row.get("Status") in {"COMPLETE", "BLOCKED"}
        ]
        if (
            len(reconciliations) > 2
            or len(stale_reconciliations) > 1
            or len(terminal_reconciliations) > 1
        ):
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} exceeds the bounded AWS-30 retry sequence"
            )
        if len(reconciliations) == 2:
            if reconciliations[0].get("Status") != "STALE" or reconciliations[1].get(
                "Status"
            ) not in {"COMPLETE", "BLOCKED"}:
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} AWS-30 recovery must be STALE then terminal"
                )
            if clean_cell(
                reconciliations[0].get("Read authorization", "")
            ) == clean_cell(reconciliations[1].get("Read authorization", "")):
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} AWS-30 recovery requires a fresh read authorization"
                )
        if reconciliations and group[-1] not in reconciliations:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} AWS-30 reconciliation must be last"
            )
        immutable_fields = (
            "REQ / DES / AUTH",
            "Deployment authorization",
            "Deployment receipt digest",
            "Deployment valid until",
            "Deployment authority source",
            "Deployment role or profile",
            "Artifact digest",
            "Plan/change-set binding",
            "Resources",
            "Mutation operations",
            "Account / Region / environment",
        )
        if group:
            first = group[0]
            for row in group[1:]:
                for field_name in immutable_fields:
                    if clean_cell(row.get(field_name, "")) != clean_cell(
                        first.get(field_name, "")
                    ):
                        structural_issues.append(
                            f"{attempt_id or 'EMPTY'} changes immutable {field_name}"
                        )
        authority_row = started[0] if started else group[0]
        authorization_id = clean_cell(authority_row.get("Deployment authorization", ""))
        receipt_digest = clean_cell(authority_row.get("Deployment receipt digest", ""))
        if authorization_id in replayed_authorization_ids:
            structural_issues.append(
                f"{attempt_id or 'EMPTY'} replays a deployment authorization ID"
            )
        replayed_authorization_ids.add(authorization_id)
        if receipt_digest != "NONE":
            if receipt_digest in replayed_receipt_digests:
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} replays a deployment receipt digest"
                )
            replayed_receipt_digests.add(receipt_digest)
        if index < len(attempt_order) - 1:
            if not terminal_reconciliations:
                structural_issues.append(
                    f"{attempt_id or 'EMPTY'} was not reconciled before the next attempt"
                )
    if structural_issues:
        return {**base, "status": "BLOCKED", "issues": structural_issues}

    deployment_rows_by_id = {clean_cell(row["Evidence ID"]): row for row in concrete}
    if re.fullmatch(r"EV-\d{4,}", release_evidence_cutoff):
        cutoff_row = deployment_rows_by_id.get(release_evidence_cutoff)
        try:
            verification_rows = parse_verification_matrix(verify_text)
        except ValueError as exc:
            return {**base, "status": "BLOCKED", "issues": [str(exc)]}
        verification_matches = [
            row
            for row in verification_rows
            if clean_cell(row.get("Evidence ID", "")) == release_evidence_cutoff
        ]
        if (1 if cutoff_row is not None else 0) + len(verification_matches) != 1:
            return {
                **base,
                "status": "BLOCKED",
                "issues": [
                    "Active evidence cutoff must resolve exactly once across the "
                    "deployment journal and Verification matrix"
                ],
            }
        if cutoff_row is not None and not (
            cutoff_row.get("Phase") == "AWS-30"
            and cutoff_row.get("Status") in {"COMPLETE", "BLOCKED"}
        ):
            return {
                **base,
                "status": "BLOCKED",
                "issues": ["Active evidence cutoff names a nonterminal deployment row"],
            }

    if len(attempt_order) > 1:
        previous_group = groups[attempt_order[-2]]
        previous_terminal = next(
            (
                row
                for row in reversed(previous_group)
                if row.get("Phase") == "AWS-30"
                and row.get("Status") in {"COMPLETE", "BLOCKED"}
            ),
            None,
        )
        latest_group = groups[attempt_order[-1]]
        latest_terminal = next(
            (
                row
                for row in reversed(latest_group)
                if row.get("Phase") == "AWS-30"
                and row.get("Status") in {"COMPLETE", "BLOCKED"}
            ),
            None,
        )
        allowed_cutoffs = (
            {clean_cell(previous_terminal.get("Evidence ID", ""))}
            if previous_terminal is not None
            else set()
        )
        if latest_terminal is not None:
            allowed_cutoffs.add(clean_cell(latest_terminal.get("Evidence ID", "")))
        if release_evidence_cutoff not in allowed_cutoffs:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_order[-1],
                "issues": [
                    "A later deployment attempt requires the prior terminal "
                    "AWS-30 evidence cutoff acknowledged by RELEASE-10"
                ],
            }

    for historical_attempt_id in attempt_order[:-1]:
        historical_issues = _deployment_historical_group_issues(
            groups[historical_attempt_id], verify_text
        )
        if historical_issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": historical_attempt_id,
                "issues": historical_issues,
            }

    expected_basis = (
        f"{requirements_revision} / {design_revision} / {construction_authorization}"
    )
    attempt_id = attempt_order[-1]
    group = groups[attempt_id]
    projection = _deployment_group_projection(base, attempt_id, group)
    terminal_reconciliation = next(
        (
            row
            for row in reversed(group)
            if row.get("Phase") == "AWS-30"
            and row.get("Status") in {"COMPLETE", "BLOCKED"}
        ),
        None,
    )
    if terminal_reconciliation is not None:
        terminal_id = clean_cell(terminal_reconciliation["Evidence ID"])
        if (
            release_state != "READY_TO_DEPLOY"
            and release_evidence_cutoff != terminal_id
        ):
            return {
                **projection,
                "status": "BLOCKED",
                "issues": [
                    "Post-reconciliation release state requires the exact terminal AWS-30 evidence cutoff"
                ],
            }
        acknowledged = release_evidence_cutoff == terminal_id
        terminal_basis_stale = False
        if acknowledged:
            allowed_release_states = (
                {"NOT_READY"}
                if clean_cell(terminal_reconciliation.get("Status", "")) == "BLOCKED"
                or clean_cell(group[0].get("REQ / DES / AUTH", "")) != expected_basis
                else {"NOT_READY", "RELEASE_VERIFIED"}
            )
            if release_state not in allowed_release_states:
                return {
                    **projection,
                    "status": "BLOCKED",
                    "basis_stale": (
                        clean_cell(group[0].get("REQ / DES / AUTH", ""))
                        != expected_basis
                    ),
                    "issues": [
                        "Terminal AWS-30 acknowledgement must update release state "
                        "and evidence cutoff together within the reconciliation result"
                    ],
                }
            terminal_issues = _deployment_historical_group_issues(group, verify_text)
        else:
            terminal_basis_stale = (
                clean_cell(group[0].get("REQ / DES / AUTH", "")) != expected_basis
            )
            restricted_read = restricted_closure or terminal_basis_stale
            terminal_read_authority = None if restricted_read else read_authority
            if terminal_read_authority is None:
                terminal_read_authority = _deployment_reconciliation_read_authority(
                    verify_text,
                    cost_posture,
                    group,
                    allow_expired=restricted_read,
                    require_post_action_freshness=restricted_read,
                )
            current_expected, current_binding_issues = _deployment_expected_binding(
                verify_text,
                construction_authorization=construction_authorization,
                envelope=envelope,
                lane=lane,
                artifact_binding=artifact_binding,
                gate_b_authority_source=gate_b_authority_source,
                gate_b_authorized_at=gate_b_authorized_at,
            )
            group_key = (
                clean_cell(group[0].get("Deployment authorization", "")),
                clean_cell(group[0].get("Deployment receipt digest", "")),
            )
            current_key = (
                clean_cell(current_expected.get("authorization_id", "")),
                clean_cell(current_expected.get("receipt_digest", "")),
            )
            if terminal_basis_stale:
                terminal_issues = _deployment_historical_group_issues(
                    group,
                    verify_text,
                    current_read_authority=terminal_read_authority,
                    require_authorization_proof=True,
                    gate_b_authority_source=gate_b_authority_source,
                    gate_b_authorized_at=gate_b_authorized_at,
                )
            else:
                terminal_issues = list(current_binding_issues)
                terminal_issues.extend(
                    _deployment_authority_timing_issues(group, current_expected)
                )
                for row in group:
                    terminal_issues.extend(
                        _deployment_row_binding_issues(
                            row,
                            current_expected,
                            terminal_read_authority,
                        )
                    )
            if terminal_read_authority is None:
                terminal_issues.append(
                    "Unacknowledged terminal AWS-30 evidence requires its exact marked read receipt"
                )
        if terminal_issues:
            return {
                **projection,
                "status": "BLOCKED",
                "basis_stale": terminal_basis_stale,
                "issues": terminal_issues,
            }
        current_expected, current_issues = _deployment_expected_binding(
            verify_text,
            construction_authorization=construction_authorization,
            envelope=envelope,
            lane=lane,
            artifact_binding=artifact_binding,
            gate_b_authority_source=gate_b_authority_source,
            gate_b_authorized_at=gate_b_authorized_at,
        )
        consumed_key = (
            clean_cell(group[0].get("Deployment authorization", "")),
            clean_cell(group[0].get("Deployment receipt digest", "")),
        )
        current_key = (
            clean_cell(current_expected.get("authorization_id", "")),
            clean_cell(current_expected.get("receipt_digest", "")),
        )
        if current_issues or not all(current_key):
            authority_status = "UNAVAILABLE"
        elif current_key == consumed_key:
            authority_status = "CONSUMED"
        else:
            authority_status = "FRESH"
        return {
            **projection,
            "status": "CONSUMED" if acknowledged else projection["status"],
            "acknowledged": acknowledged,
            "acknowledged_evidence_id": terminal_id if acknowledged else "NONE",
            "release_evidence_cutoff": release_evidence_cutoff,
            "current_mutation_authority_status": authority_status,
            "basis_stale": terminal_basis_stale,
        }

    group_basis = clean_cell(group[0].get("REQ / DES / AUTH", ""))
    basis_stale = group_basis != expected_basis
    reconciliation_read_authority = None
    if projection.get("status") == "RECONCILIATION_REQUIRED":
        restricted_read = restricted_closure or basis_stale
        reconciliation_read_authority = None if restricted_read else read_authority
        if reconciliation_read_authority is None:
            reconciliation_read_authority = _deployment_reconciliation_read_authority(
                verify_text,
                cost_posture,
                group,
                allow_expired=restricted_read,
                require_post_action_freshness=restricted_read,
            )
        elif not restricted_read:
            reconciliation_read_authority = {
                **dict(reconciliation_read_authority),
                "reconciliation_only": False,
                "attempt_id": attempt_id,
            }
    if basis_stale:
        historical_issues = _deployment_historical_group_issues(
            group,
            verify_text,
            current_read_authority=(
                reconciliation_read_authority
                if any(row.get("Phase") == "AWS-30" for row in group)
                else None
            ),
            require_authorization_proof=True,
            gate_b_authority_source=gate_b_authority_source,
            gate_b_authorized_at=gate_b_authorized_at,
        )
        if historical_issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "basis_stale": True,
                "issues": historical_issues,
            }
        if projection.get("status") == "ACTION_TERMINAL_REQUIRED":
            return {**projection, "basis_stale": True}
        return {
            **projection,
            "status": "RECONCILIATION_REQUIRED",
            "basis_stale": True,
            "reconciliation_read_authority": (
                dict(reconciliation_read_authority)
                if reconciliation_read_authority is not None
                else {}
            ),
            "blocker_or_stale_reason": (
                projection.get("blocker_or_stale_reason")
                if projection.get("reconciliation_status") == "STALE"
                else "Current REQ / DES / AUTH differs from the attempted action"
            ),
        }

    expected, binding_issues = _deployment_expected_binding(
        verify_text,
        construction_authorization=construction_authorization,
        envelope=envelope,
        lane=lane,
        artifact_binding=artifact_binding,
        gate_b_authority_source=gate_b_authority_source,
        gate_b_authorized_at=gate_b_authorized_at,
    )
    group_key = (
        clean_cell(group[0].get("Deployment authorization", "")),
        clean_cell(group[0].get("Deployment receipt digest", "")),
    )
    expected_key = (
        clean_cell(expected.get("authorization_id", "")),
        clean_cell(expected.get("receipt_digest", "")),
    )
    if group_key != expected_key:
        historical_issues = _deployment_historical_group_issues(
            group,
            verify_text,
            require_authorization_proof=True,
            gate_b_authority_source=gate_b_authority_source,
            gate_b_authorized_at=gate_b_authorized_at,
        )
        if historical_issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "issues": historical_issues,
            }
        return {
            **projection,
            "reconciliation_read_authority": (
                dict(reconciliation_read_authority)
                if reconciliation_read_authority is not None
                else {}
            ),
        }
    binding_issues.extend(_deployment_authority_timing_issues(group, expected))
    for row in group:
        if clean_cell(row.get("REQ / DES / AUTH", "")) != expected_basis:
            binding_issues.append(
                f"{row['Evidence ID']} does not match current REQ / DES / AUTH"
            )
        binding_issues.extend(
            _deployment_row_binding_issues(row, expected, reconciliation_read_authority)
        )
    if binding_issues:
        return {
            **base,
            "status": "BLOCKED",
            "attempt_id": attempt_id,
            "issues": binding_issues,
        }
    return {
        **projection,
        "reconciliation_read_authority": (
            dict(reconciliation_read_authority)
            if reconciliation_read_authority is not None
            else {}
        ),
    }


def _teardown_values(value: str, label: str, *, allow_none: bool) -> list[str]:
    cleaned = clean_cell(value)
    if allow_none and cleaned == "NONE":
        return []
    values = _split_authority_values(cleaned)
    if (
        not values
        or len(values) != len(set(values))
        or any("*" in item for item in values)
    ):
        raise ValueError(f"{label} must be a unique wildcard-free exact list")
    return values


def _teardown_receipt_row_issues(
    row: Mapping[str, str],
    verify_text: str,
    *,
    construction_authorization: str,
    envelope: Mapping[str, str],
    require_row_role_match: bool = True,
    historical: bool = False,
) -> tuple[dict[str, str] | None, str, list[str]]:
    """Validate one evidence row against the exact current teardown receipt."""

    try:
        receipt = marked_receipt(verify_text, "aws-teardown")
    except ValueError:
        receipt = ""
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS TEARDOWN",
        AWS_TEARDOWN_RECEIPT_FIELDS,
        allow_none_fields=frozenset(
            {"Resources and data to retain", "Shared dependencies"}
        ),
    )
    provenance = _action_authorization_rows(verify_text).get("Teardown")
    digest = (
        "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        if receipt
        else "NONE"
    )
    issues: list[str] = []
    if fields is None or provenance is None or unresolved(receipt):
        return (
            None,
            digest,
            ["evidence requires one exact owner-authored teardown receipt"],
        )
    action_authorization = clean_cell(row.get("Teardown authorization", ""))
    action_digest = clean_cell(row.get("Teardown receipt digest", ""))
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    if (
        action_authorization != fields["Teardown authorization"]
        or action_digest != digest
        or fields["Construction authorization"] != construction_authorization
        or (
            require_row_role_match
            and fields["Profile or role"] != clean_cell(row.get("Role or profile", ""))
        )
        or fields["Stack, application, and resources to remove"]
        != clean_cell(row.get("Resources proposed to remove", ""))
        or fields["Resources and data to retain"]
        != clean_cell(row.get("Resources retained", ""))
        or fields["Allowed deletion operations"]
        != clean_cell(row.get("Allowed deletion operations", ""))
        or fields["Shared dependencies"]
        != clean_cell(row.get("Shared dependencies", ""))
        or fields["Cost effect"] != clean_cell(row.get("Cost effect", ""))
        or fields["Post-teardown verification"]
        != clean_cell(row.get("Post-teardown verification", ""))
        or clean_cell(row.get("Account / Region / environment", "")) != expected_scope
        or (not historical and not _receipt_identity_matches_gate_b(fields, envelope))
        or provenance.get("Authorization ID") != action_authorization
        or provenance.get("Construction AUTH") != construction_authorization
        or provenance.get("Role or profile") != fields["Profile or role"]
        or provenance.get("Account / Region / environment") != expected_scope
        or provenance.get("Approver") != fields["Approver"]
        or not explicit_human_approver(fields["Approver"])
        or clean_cell(provenance.get("Verbatim receipt SHA-256", "")) != digest
        or not explicit_value(provenance.get("Stable owner-message source", ""))
        or not explicit_timestamp(provenance.get("Observed at", ""))
        or clean_cell(provenance.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or clean_cell(provenance.get("Result", ""))
        not in {"AUTHORIZED", "RUNNING", "READY"}
    ):
        issues.append("evidence does not bind the exact teardown receipt")
    return fields, digest, issues


def _teardown_action_attempt_row_issues(
    row: Mapping[str, str],
    envelope: Mapping[str, str],
    *,
    historical: bool = False,
) -> list[str]:
    """Validate one direct AWS-50 STARTED or terminal journal row."""

    issues: list[str] = []
    status = clean_cell(row.get("Status", ""))
    if status not in AWS_TEARDOWN_ACTION_STATUSES:
        return ["matching AWS-50 attempt has an invalid action status"]
    try:
        resources = _teardown_values(
            row.get("Resources proposed to remove", ""),
            "Resources proposed to remove",
            allow_none=False,
        )
        operations = _teardown_values(
            row.get("Allowed deletion operations", ""),
            "Allowed deletion operations",
            allow_none=False,
        )
        retained = _teardown_values(
            row.get("Resources retained", ""), "Resources retained", allow_none=True
        )
        shared = _teardown_values(
            row.get("Shared dependencies", ""), "Shared dependencies", allow_none=True
        )
        removed = _teardown_values(
            row.get("Resources removed", ""), "Resources removed", allow_none=True
        )
        residuals = _teardown_values(
            row.get("Residual resources", ""), "Residual resources", allow_none=True
        )
    except ValueError as exc:
        return [str(exc)]
    if not historical and not _receipt_scope_within_gate_b(
        resources, operations, envelope
    ):
        issues.append("matching AWS-50 attempt exceeds Gate B")
    if (
        set(resources).intersection(retained)
        or set(resources).intersection(shared)
        or set(retained).intersection(shared)
    ):
        issues.append("matching AWS-50 removal, retention, and shared sets overlap")
    for field_name, allow_none in (
        ("Expected manifest or stack", False),
        ("Cost effect", False),
        ("Post-teardown verification", False),
        ("Stack events and terminal status", False),
        ("Resources removed", True),
        ("Snapshots and backups", True),
        ("Residual resources", True),
        ("Inventory or discovery limits", False),
    ):
        if not explicit_value(row.get(field_name, ""), allow_none=allow_none):
            issues.append(f"matching AWS-50 attempt requires {field_name}")
    if clean_cell(row.get("Identity and boundary match", "")) not in {
        "PASS",
        "VERIFIED",
    }:
        issues.append("matching AWS-50 attempt requires verified identity and boundary")
    direct_fields = (
        "Stack events and terminal status",
        "Resources removed",
        "Snapshots and backups",
        "Residual resources",
        "Inventory or discovery limits",
    )
    if status == "STARTED":
        if (
            clean_cell(row.get("Stack events and terminal status", ""))
            != AWS_TEARDOWN_PRECALL_RESULT
        ):
            issues.append("AWS-50 STARTED must use the exact pre-call sentinel")
        if (
            clean_cell(row.get("Inventory or discovery limits", ""))
            != AWS_TEARDOWN_PRECALL_RESULT
        ):
            issues.append(
                "AWS-50 STARTED inventory must use the exact pre-call sentinel"
            )
        for field_name in (
            "Resources removed",
            "Snapshots and backups",
            "Residual resources",
        ):
            if clean_cell(row.get(field_name, "")) != "NONE":
                issues.append(f"AWS-50 STARTED must use {field_name} = NONE")
        return issues
    if any(
        clean_cell(row.get(field_name, "")) == AWS_TEARDOWN_PRECALL_RESULT
        for field_name in direct_fields
    ):
        issues.append("AWS-50 terminal evidence cannot reuse the pre-call sentinel")
    if status == "SUCCEEDED":
        if residuals:
            issues.append("matching SUCCEEDED AWS-50 attempt cannot retain residuals")
        if set(removed) != set(resources):
            issues.append(
                "matching SUCCEEDED AWS-50 attempt must reconcile every removal"
            )
    return issues


def _teardown_basis_authorization(row: Mapping[str, str]) -> str | None:
    parts = [
        clean_cell(item)
        for item in clean_cell(row.get("REQ / DES / AUTH", "")).split(" / ")
    ]
    if (
        len(parts) != 3
        or re.fullmatch(r"REQ-\d{4,}", parts[0]) is None
        or re.fullmatch(r"DES-\d{4,}", parts[1]) is None
        or re.fullmatch(r"AUTH-\d{4,}", parts[2]) is None
    ):
        return None
    return parts[2]


def _teardown_attempt_timing_issues(
    started: Mapping[str, str], fields: Mapping[str, str], provenance: Mapping[str, str]
) -> list[str]:
    """Prove the one-operation receipt was current when STARTED was appended."""

    issues: list[str] = []
    started_at = _iso_datetime(started.get("Observed at", ""))
    authorized_at = _iso_datetime(provenance.get("Observed at", ""))
    valid_until = clean_cell(fields.get("Valid until", ""))
    expires_at = None if valid_until == "ONE_OPERATION" else _iso_datetime(valid_until)
    if started_at is None:
        issues.append("teardown STARTED timestamp is invalid")
    if authorized_at is None:
        issues.append("teardown authorization timestamp is invalid")
    elif started_at is not None and started_at < authorized_at:
        issues.append("teardown STARTED precedes its authorization provenance")
    if valid_until != "ONE_OPERATION" and expires_at is None:
        issues.append("teardown authority has a noncanonical validity boundary")
    elif started_at is not None and expires_at is not None and started_at > expires_at:
        issues.append("teardown STARTED occurred after authority expiry")
    return issues


def _teardown_read_row_issues(
    row: Mapping[str, str],
    authority: Mapping[str, Any] | None,
    *,
    require_authority: bool,
    require_exact_scope: bool = False,
) -> list[str]:
    """Validate durable AWS-40 read provenance without reviving old authority."""

    evidence_id = clean_cell(row.get("Evidence ID", "")) or "AWS-40 row"
    read_id = clean_cell(row.get("Read authorization", ""))
    read_role = clean_cell(row.get("Read role or profile", ""))
    read_digest = clean_cell(row.get("Read receipt digest", ""))
    read_valid_until = clean_cell(row.get("Read valid until", ""))
    read_source_proof = clean_cell(row.get("Read authority source", ""))
    source_match = AWS_TEARDOWN_READ_PROVENANCE.fullmatch(read_source_proof)
    read_source = clean_cell(source_match.group("source")) if source_match else ""
    read_authorized_at_value = (
        clean_cell(source_match.group("authorized_at")) if source_match else ""
    )
    observed_at = _iso_datetime(row.get("Observed at", ""))
    read_authorized_at = _iso_datetime(read_authorized_at_value)
    expires_at = _iso_datetime(read_valid_until)
    issues: list[str] = []
    if AWS_READ_AUTHORIZATION_ID.fullmatch(read_id) is None:
        issues.append(f"{evidence_id} AWS-40 requires a canonical read authorization")
    if not explicit_value(read_role, allow_none=False) or "*" in read_role:
        issues.append(f"{evidence_id} AWS-40 requires a concrete read role")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", read_digest) is None:
        issues.append(f"{evidence_id} AWS-40 requires an exact read receipt digest")
    if read_valid_until == "ONE_OPERATION" or expires_at is None:
        issues.append(f"{evidence_id} AWS-40 requires reusable ISO read validity")
    elif observed_at is not None and observed_at > expires_at:
        issues.append(f"{evidence_id} AWS-40 was observed after read authority expiry")
    if (
        source_match is None
        or not explicit_value(read_source, allow_none=False)
        or "*" in read_source
        or read_authorized_at is None
    ):
        issues.append(
            f"{evidence_id} AWS-40 requires a durable read authority source "
            "and ISO authorization timestamp"
        )
    elif observed_at is not None and observed_at < read_authorized_at:
        issues.append(f"{evidence_id} AWS-40 observation precedes read authorization")
    if authority is None:
        if require_authority:
            issues.append(
                f"{evidence_id} AWS-40 requires its exact current read receipt"
            )
        return issues

    expected_scope = (
        f"ACCOUNT: {authority.get('account')}; REGION: {authority.get('region')}; "
        f"ENVIRONMENT: {authority.get('environment')}"
    )
    if read_id != clean_cell(authority.get("authorization_id", "")):
        issues.append(
            f"{evidence_id} read authorization does not match current authority"
        )
    if read_role != clean_cell(authority.get("role_or_profile", "")):
        issues.append(f"{evidence_id} read role does not match its receipt")
    if read_digest != clean_cell(authority.get("receipt_digest", "")):
        issues.append(f"{evidence_id} read receipt digest is tampered")
    if read_valid_until != clean_cell(authority.get("expiration", "")):
        issues.append(f"{evidence_id} read validity is tampered")
    if read_source != clean_cell(authority.get("authority_source", "")):
        issues.append(f"{evidence_id} read authority source is tampered")
    if read_authorized_at_value != clean_cell(authority.get("authorized_at", "")):
        issues.append(f"{evidence_id} read authorization timestamp is tampered")
    if clean_cell(row.get("Account / Region / environment", "")) != expected_scope:
        issues.append(f"{evidence_id} read account boundary is stale")
    authority_authorized_at = _iso_datetime(authority.get("authorized_at", ""))
    if authority_authorized_at is None:
        issues.append(f"{evidence_id} read authorization timestamp is invalid")
    elif observed_at is not None and observed_at < authority_authorized_at:
        issues.append(f"{evidence_id} AWS-40 observation precedes read authorization")
    try:
        observed_resources: set[str] = set()
        for field_name in (
            "Resources proposed to remove",
            "Resources retained",
            "Shared dependencies",
            "Residual resources",
        ):
            observed_resources.update(
                _teardown_values(row.get(field_name, ""), field_name, allow_none=True)
            )
        observed_operations = _teardown_values(
            row.get("Post-teardown verification", ""),
            "Post-teardown verification",
            allow_none=clean_cell(row.get("Status", ""))
            in {"RUNNING", "BLOCKED", "STALE"},
        )
    except ValueError as exc:
        issues.append(str(exc))
        observed_resources, observed_operations = set(), []
    authorized_resources = set(authority.get("resources", []))
    authorized_operations = set(authority.get("operations", []))
    if require_exact_scope and observed_resources != authorized_resources:
        issues.append(f"{evidence_id} recorded resources do not match exact read scope")
    elif observed_resources and not observed_resources.issubset(authorized_resources):
        issues.append(f"{evidence_id} observed resources exceed read scope")
    if require_exact_scope and set(observed_operations) != authorized_operations:
        issues.append(
            f"{evidence_id} recorded operations do not match exact read scope"
        )
    elif observed_operations and not set(observed_operations).issubset(
        authorized_operations
    ):
        issues.append(f"{evidence_id} observed operations exceed read scope")
    return issues


def _teardown_reconciliation_read_authority(
    verify_text: str,
    cost_posture: str,
    group: list[dict[str, str]],
    attempt_id: str,
    *,
    restricted_closure: bool,
) -> dict[str, Any] | None:
    """Project current read authority for one immutable teardown attempt."""

    if not group:
        return None
    try:
        receipt = marked_receipt(verify_text, "aws-read-preflight")
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        "AUTHORIZE AWS READ-ONLY PREFLIGHT",
        AWS_READ_PREFLIGHT_RECEIPT_FIELDS,
    )
    if fields is None:
        return None
    synthetic_group = [
        {
            **row,
            "Artifact digest": fields["Artifact digest"],
            "Resources": row.get("Resources proposed to remove", ""),
        }
        for row in group
    ]
    authority = _deployment_reconciliation_read_authority(
        verify_text,
        cost_posture,
        synthetic_group,
        allow_expired=False,
        require_post_action_freshness=restricted_closure,
    )
    if authority is None:
        return None
    return {
        **authority,
        "attempt_id": attempt_id,
        "reconciliation_only": restricted_closure,
    }


def derive_teardown_sequence_state(
    verify_text: str,
    read_authority: Mapping[str, Any] | None,
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    envelope: Mapping[str, str],
    restricted_closure: bool = False,
    cost_posture: str = "",
    active_artifact: str = "",
) -> dict[str, Any]:
    """Derive append-only AWS-40/AWS-50 sequencing without replay authority."""

    base: dict[str, Any] = {
        "status": "NOT_ACTIVE",
        "attempt_id": "NONE",
        "evidence_id": "NONE",
        "observed_at": "NONE",
        "ready_evidence_id": "NONE",
        "read_authorization": "NONE",
        "read_role_or_profile": "NONE",
        "read_receipt_digest": "NONE",
        "read_valid_until": "NONE",
        "read_authority_source": "NONE",
        "expected_manifest_or_stack": "NONE",
        "account": "NONE",
        "region": "NONE",
        "environment": "NONE",
        "phase": "NONE",
        "action_status": "NONE",
        "review_status": "NONE",
        "issues": [],
        "resources_to_remove": [],
        "allowed_operations": [],
        "resources_to_retain": [],
        "shared_dependencies": [],
        "resources_removed": [],
        "residual_resources": [],
        "cost_effect": "NONE",
        "post_action_verification": "NONE",
        "terminal_status": "NONE",
        "snapshots_and_backups": "NONE",
        "inventory_limits": "NONE",
        "identity_and_boundary_match": "NONE",
        "teardown_authorization": "NONE",
        "teardown_receipt_digest": "NONE",
        "blocker_or_stale_reason": "NONE",
        "basis_stale": False,
        "post_action_bound": False,
        "current_mutation_authority_status": "UNAVAILABLE",
        "reconciliation_read_authority": {},
    }
    try:
        rows = parse_teardown_reconciliation_evidence(verify_text)
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    concrete: list[dict[str, str]] = []
    invalid_identifiers: list[str] = []
    for row in rows:
        evidence_id = clean_cell(row.get("Evidence ID", ""))
        if re.fullmatch(r"EV-\d{4,}", evidence_id):
            concrete.append({key: clean_cell(value) for key, value in row.items()})
            continue
        status = clean_cell(row.get("Status", ""))
        placeholder = (
            unresolved(evidence_id)
            and status in {"", "NOT_STARTED"}
            and all(
                unresolved(row.get(header, ""))
                for header in AWS_TEARDOWN_EVIDENCE_HEADERS
                if header not in {"Evidence ID", "Status"}
            )
        )
        if not placeholder:
            invalid_identifiers.append(evidence_id or "EMPTY")
    if invalid_identifiers:
        return {
            **base,
            "status": "BLOCKED",
            "issues": [
                "Teardown reconciliation evidence has noncanonical or partially "
                "populated IDs: " + ", ".join(sorted(invalid_identifiers))
            ],
        }
    if not concrete:
        return base
    identifiers = [row["Evidence ID"] for row in concrete]
    structural_issues: list[str] = []
    if len(identifiers) != len(set(identifiers)):
        structural_issues.append(
            "Teardown reconciliation evidence contains duplicate IDs"
        )
    timestamps: list[datetime] = []
    attempts: dict[str, list[dict[str, str]]] = {}
    attempt_order: list[str] = []
    closed_attempts: set[str] = set()
    active_attempt = ""
    for row in concrete:
        evidence_id = row["Evidence ID"]
        attempt_id = row.get("Attempt ID", "")
        phase = row.get("Phase", "")
        status = row.get("Status", "")
        observed_at = _iso_datetime(row.get("Observed at", ""))
        if phase == "AWS-40":
            if status not in AWS_TEARDOWN_REVIEW_STATUSES:
                structural_issues.append(
                    f"{evidence_id} has invalid AWS-40 status {status or 'EMPTY'}"
                )
            if (
                attempt_id != "NONE"
                and AWS_TEARDOWN_ATTEMPT_ID.fullmatch(attempt_id) is None
            ):
                structural_issues.append(f"{evidence_id} has a noncanonical Attempt ID")
            structural_issues.extend(
                _teardown_read_row_issues(row, None, require_authority=False)
            )
        elif phase == "AWS-50":
            if status not in AWS_TEARDOWN_ACTION_STATUSES:
                structural_issues.append(
                    f"{evidence_id} has invalid AWS-50 status {status or 'EMPTY'}"
                )
            if AWS_TEARDOWN_ATTEMPT_ID.fullmatch(attempt_id) is None:
                structural_issues.append(f"{evidence_id} has a noncanonical Attempt ID")
        else:
            structural_issues.append(
                f"{evidence_id} phase must be exactly AWS-40 or AWS-50"
            )
        if observed_at is None:
            structural_issues.append(
                f"{evidence_id} Observed at must be ISO 8601 with timezone"
            )
        else:
            timestamps.append(observed_at)
        if not explicit_value(row.get("Durable source", ""), allow_none=False):
            structural_issues.append(f"{evidence_id} requires a durable source")
        blocker_reason = row.get("Blocker or stale reason", "")
        if phase == "AWS-40" and status in {"BLOCKED", "STALE"}:
            if not explicit_value(blocker_reason, allow_none=False):
                structural_issues.append(
                    f"{evidence_id} requires an exact blocker or stale reason"
                )
        elif blocker_reason != "NONE":
            structural_issues.append(
                f"{evidence_id} must use Blocker or stale reason = NONE"
            )
        if attempt_id != "NONE":
            if attempt_id != active_attempt:
                if attempt_id in closed_attempts:
                    structural_issues.append(
                        f"{evidence_id} reopens a noncontiguous teardown attempt"
                    )
                if active_attempt:
                    closed_attempts.add(active_attempt)
                active_attempt = attempt_id
                attempt_order.append(attempt_id)
            attempts.setdefault(attempt_id, []).append(row)
        elif phase == "AWS-50":
            structural_issues.append(
                f"{evidence_id} AWS-50 requires a canonical Attempt ID"
            )
        elif active_attempt:
            active_rows = attempts.get(active_attempt, [])
            active_has_terminal_review = any(
                item.get("Phase") == "AWS-40"
                and item.get("Status")
                in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
                for item in active_rows
            )
            if phase == "AWS-40" and not active_has_terminal_review:
                structural_issues.append(
                    f"{evidence_id} AWS-40 cannot erase active teardown attempt "
                    f"binding {active_attempt}"
                )
            closed_attempts.add(active_attempt)
            active_attempt = ""
    if len(timestamps) != len(set(timestamps)):
        structural_issues.append(
            "Teardown reconciliation evidence timestamps must be unique"
        )
    if len(timestamps) == len(concrete) and timestamps != sorted(timestamps):
        structural_issues.append(
            "Teardown reconciliation evidence must be appended in observed-time order"
        )
    replayed_authorizations: set[str] = set()
    replayed_digests: set[str] = set()
    for index, attempt_id in enumerate(attempt_order):
        group = attempts[attempt_id]
        starts = [
            row
            for row in group
            if row.get("Phase") == "AWS-50" and row.get("Status") == "STARTED"
        ]
        terminals = [
            row
            for row in group
            if row.get("Phase") == "AWS-50"
            and row.get("Status") in AWS_TEARDOWN_TERMINAL_STATUSES
        ]
        reviews = [row for row in group if row.get("Phase") == "AWS-40"]
        if len(starts) != 1 or group[0] not in starts:
            structural_issues.append(
                f"{attempt_id} requires exactly one first AWS-50 STARTED row"
            )
        if len(terminals) > 1:
            structural_issues.append(
                f"{attempt_id} has more than one AWS-50 terminal row"
            )
        if terminals and group.index(terminals[0]) != 1:
            structural_issues.append(
                f"{attempt_id} AWS-50 terminal row must immediately follow STARTED"
            )
        if reviews and len(terminals) != 1:
            structural_issues.append(
                f"{attempt_id} AWS-40 requires one prior AWS-50 terminal row"
            )
        if (
            reviews
            and terminals
            and any(group.index(row) < group.index(terminals[0]) for row in reviews)
        ):
            structural_issues.append(
                f"{attempt_id} AWS-40 must follow the AWS-50 terminal row"
            )
        if len(reviews) > 2:
            structural_issues.append(
                f"{attempt_id} exceeds the bounded AWS-40 retry sequence"
            )
        if (
            len(reviews) == 2
            and reviews[0].get("Status") == "STALE"
            and reviews[0].get("Read authorization")
            == reviews[1].get("Read authorization")
        ):
            structural_issues.append(
                f"{attempt_id} AWS-40 recovery requires fresh read authority"
            )
        if len(reviews) == 2 and (
            reviews[0].get("Status") not in {"RUNNING", "STALE"}
            or reviews[1].get("Status")
            not in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
        ):
            structural_issues.append(
                f"{attempt_id} AWS-40 recovery must be RUNNING or STALE then terminal"
            )
        immutable_fields = (
            "REQ / DES / AUTH",
            "Read authorization",
            "Read role or profile",
            "Read receipt digest",
            "Read valid until",
            "Read authority source",
            "Teardown authorization",
            "Teardown receipt digest",
            "Role or profile",
            "Expected manifest or stack",
            "Resources proposed to remove",
            "Allowed deletion operations",
            "Resources retained",
            "Shared dependencies",
            "Cost effect",
            "Post-teardown verification",
            "Account / Region / environment",
        )
        action_rows = [row for row in group if row.get("Phase") == "AWS-50"]
        if action_rows:
            first = action_rows[0]
            for row in action_rows[1:]:
                for field_name in immutable_fields:
                    if row.get(field_name) != first.get(field_name):
                        structural_issues.append(
                            f"{attempt_id} changes immutable {field_name}"
                        )
        authority_row = starts[0] if starts else group[0]
        authorization_id = authority_row.get("Teardown authorization", "")
        receipt_digest = authority_row.get("Teardown receipt digest", "")
        if authorization_id in replayed_authorizations:
            structural_issues.append(
                f"{attempt_id} replays a teardown authorization ID"
            )
        replayed_authorizations.add(authorization_id)
        if receipt_digest in replayed_digests:
            structural_issues.append(f"{attempt_id} replays a teardown receipt digest")
        replayed_digests.add(receipt_digest)
        if index < len(attempt_order) - 1:
            terminal_reviews = [
                row
                for row in reviews
                if row.get("Status")
                in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
            ]
            if len(terminals) != 1 or len(terminal_reviews) != 1:
                structural_issues.append(
                    f"{attempt_id} was not reconciled before the next teardown attempt"
                )
    if structural_issues:
        return {**base, "status": "BLOCKED", "issues": structural_issues}

    expected_basis = (
        f"{requirements_revision} / {design_revision} / {construction_authorization}"
    )
    current_read = bool(
        read_authority is not None and read_authority.get("validity") == "CURRENT"
    )
    selected_attempt_id = clean_cell(concrete[-1].get("Attempt ID", ""))
    if selected_attempt_id != "NONE":
        if selected_attempt_id not in attempts:
            return {
                **base,
                "status": "BLOCKED",
                "issues": ["Latest teardown epoch is malformed"],
            }
        attempt_id = selected_attempt_id
        group = attempts[attempt_id]
        started = group[0]
        terminal = next(
            (
                row
                for row in group
                if row.get("Phase") == "AWS-50"
                and row.get("Status") in AWS_TEARDOWN_TERMINAL_STATUSES
            ),
            None,
        )
        reviews = [row for row in group if row.get("Phase") == "AWS-40"]
        latest = reviews[-1] if reviews else terminal or started
        group_basis = started.get("REQ / DES / AUTH", "")
        basis_authorization = _teardown_basis_authorization(started)
        basis_stale = group_basis != expected_basis
        historical = (
            restricted_closure or basis_stale or construction_authorization == "NONE"
        )
        issues: list[str] = []
        if basis_authorization is None:
            issues.append(f"{attempt_id} has a noncanonical REQ / DES / AUTH basis")
        started_index = concrete.index(started)
        ready = concrete[started_index - 1] if started_index > 0 else None
        if not (
            ready is not None
            and ready.get("Phase") == "AWS-40"
            and ready.get("Attempt ID") == "NONE"
            and ready.get("Status") == "READY_FOR_TEARDOWN"
        ):
            issues.append(
                f"{attempt_id} must immediately follow the latest READY_FOR_TEARDOWN evidence"
            )
            ready = None
        else:
            for field_name in (
                "REQ / DES / AUTH",
                "Read authorization",
                "Read role or profile",
                "Read receipt digest",
                "Read valid until",
                "Read authority source",
                "Role or profile",
                "Expected manifest or stack",
                "Resources proposed to remove",
                "Allowed deletion operations",
                "Resources retained",
                "Shared dependencies",
                "Cost effect",
                "Post-teardown verification",
                "Account / Region / environment",
            ):
                if ready.get(field_name) != started.get(field_name):
                    issues.append(
                        f"{attempt_id} does not match READY_FOR_TEARDOWN {field_name}"
                    )
            issues.extend(
                _teardown_read_row_issues(ready, None, require_authority=False)
            )
        if basis_authorization is not None:
            fields, digest, receipt_issues = _teardown_receipt_row_issues(
                started,
                verify_text,
                construction_authorization=basis_authorization,
                envelope=envelope,
                historical=historical,
            )
            issues.extend(receipt_issues)
            provenance = _action_authorization_rows(verify_text).get("Teardown")
            if fields is not None and provenance is not None:
                issues.extend(
                    _teardown_attempt_timing_issues(started, fields, provenance)
                )
            if digest != started.get("Teardown receipt digest"):
                issues.append(f"{attempt_id} has a stale teardown receipt digest")
        issues.extend(
            _teardown_action_attempt_row_issues(
                started, envelope, historical=historical
            )
        )
        if terminal is not None:
            issues.extend(
                _teardown_action_attempt_row_issues(
                    terminal, envelope, historical=historical
                )
            )
        if issues:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "evidence_id": latest.get("Evidence ID", "NONE"),
                "phase": latest.get("Phase", "NONE"),
                "action_status": terminal.get("Status", "STARTED")
                if terminal
                else "STARTED",
                "basis_stale": basis_stale,
                "issues": issues,
            }
        try:
            resources = _teardown_values(
                started["Resources proposed to remove"],
                "Resources proposed to remove",
                allow_none=False,
            )
            operations = _teardown_values(
                started["Allowed deletion operations"],
                "Allowed deletion operations",
                allow_none=False,
            )
            retained = _teardown_values(
                started["Resources retained"], "Resources retained", allow_none=True
            )
            shared = _teardown_values(
                started["Shared dependencies"], "Shared dependencies", allow_none=True
            )
            removed = _teardown_values(
                latest["Resources removed"], "Resources removed", allow_none=True
            )
            residuals = _teardown_values(
                latest["Residual resources"], "Residual resources", allow_none=True
            )
        except ValueError as exc:
            return {
                **base,
                "status": "BLOCKED",
                "attempt_id": attempt_id,
                "issues": [str(exc)],
            }
        reconciliation_read_authority: dict[str, Any] = {}
        if terminal is not None:
            restricted_read = (
                restricted_closure
                or basis_stale
                or construction_authorization == "NONE"
            )
            candidate = None if restricted_read else read_authority
            if candidate is not None and candidate.get("validity") == "CURRENT":
                reconciliation_read_authority = {
                    **dict(candidate),
                    "attempt_id": attempt_id,
                    "reconciliation_only": False,
                }
            else:
                recovered = _teardown_reconciliation_read_authority(
                    verify_text,
                    cost_posture,
                    group,
                    attempt_id,
                    restricted_closure=restricted_read,
                )
                if recovered is not None:
                    reconciliation_read_authority = recovered
        projection = {
            **base,
            "attempt_id": attempt_id,
            "evidence_id": latest.get("Evidence ID", "NONE"),
            "observed_at": latest.get("Observed at", "NONE"),
            "ready_evidence_id": ready.get("Evidence ID", "NONE"),
            "read_authorization": started["Read authorization"],
            "read_role_or_profile": started["Read role or profile"],
            "read_receipt_digest": started["Read receipt digest"],
            "read_valid_until": started["Read valid until"],
            "read_authority_source": started["Read authority source"],
            "expected_manifest_or_stack": started["Expected manifest or stack"],
            "account": fields["Account"],
            "region": fields["Region"],
            "environment": fields["Environment"],
            "phase": latest.get("Phase", "NONE"),
            "action_status": terminal.get("Status", "STARTED")
            if terminal
            else "STARTED",
            "basis_stale": basis_stale,
            "teardown_authorization": started["Teardown authorization"],
            "teardown_receipt_digest": started["Teardown receipt digest"],
            "role_or_profile": started["Role or profile"],
            "resources_to_remove": resources,
            "allowed_operations": operations,
            "resources_to_retain": retained,
            "shared_dependencies": shared,
            "resources_removed": removed,
            "residual_resources": residuals,
            "cost_effect": started["Cost effect"],
            "post_action_verification": started["Post-teardown verification"],
            "terminal_status": latest["Stack events and terminal status"],
            "snapshots_and_backups": latest["Snapshots and backups"],
            "inventory_limits": latest["Inventory or discovery limits"],
            "identity_and_boundary_match": latest["Identity and boundary match"],
            "blocker_or_stale_reason": latest["Blocker or stale reason"],
            "current_mutation_authority_status": "CONSUMED",
            "reconciliation_read_authority": reconciliation_read_authority,
        }
        if terminal is None:
            return {**projection, "status": "ACTION_TERMINAL_REQUIRED"}
        if not reviews:
            return {**projection, "status": "POST_ACTION_REVIEW"}
        review = reviews[-1]
        review_issues: list[str] = []
        terminal_time = _iso_datetime(terminal.get("Observed at", ""))
        review_time = _iso_datetime(review.get("Observed at", ""))
        if terminal_time is None or review_time is None or review_time <= terminal_time:
            review_issues.append(
                "post-action AWS-40 evidence must follow the terminal AWS-50 row"
            )
        if review.get("Teardown authorization") != started.get(
            "Teardown authorization"
        ):
            review_issues.append("post-action AWS-40 changes teardown authorization")
        if review.get("Teardown receipt digest") != started.get(
            "Teardown receipt digest"
        ):
            review_issues.append("post-action AWS-40 changes teardown receipt digest")
        for field_name in (
            "REQ / DES / AUTH",
            "Role or profile",
            "Expected manifest or stack",
            "Resources proposed to remove",
            "Allowed deletion operations",
            "Resources retained",
            "Shared dependencies",
            "Cost effect",
            "Post-teardown verification",
            "Account / Region / environment",
        ):
            if review.get(field_name) != started.get(field_name):
                review_issues.append(
                    f"post-action AWS-40 changes immutable {field_name}"
                )
        review_status = review.get("Status", "")
        review_authority = (
            reconciliation_read_authority
            if clean_cell(reconciliation_read_authority.get("authorization_id", ""))
            == clean_cell(review.get("Read authorization", ""))
            else None
        )
        review_issues.extend(
            _teardown_read_row_issues(
                review,
                review_authority,
                require_authority=review_status in {"RUNNING", "STALE"},
                require_exact_scope=(
                    review_status in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"}
                    and review_authority is not None
                ),
            )
        )
        if review_status in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN"} and review.get(
            "Identity and boundary match"
        ) not in {"PASS", "VERIFIED"}:
            review_issues.append(
                "post-action AWS-40 requires verified identity and boundary"
            )
        if review_status == "VERIFIED_CLEAN":
            if residuals:
                review_issues.append(
                    "VERIFIED_CLEAN requires Residual resources = NONE"
                )
            if set(removed) != set(resources):
                review_issues.append(
                    "VERIFIED_CLEAN must reconcile every proposed removal"
                )
        if review_status == "RESIDUALS_REMAIN" and not residuals:
            review_issues.append(
                "RESIDUALS_REMAIN requires an exact residual-resource list"
            )
        if review_issues:
            return {**projection, "status": "BLOCKED", "issues": review_issues}
        common_review = {
            **projection,
            "review_status": review_status,
            "evidence_id": review["Evidence ID"],
            "observed_at": review["Observed at"],
            "phase": "AWS-40",
            "read_authorization": review["Read authorization"],
            "read_role_or_profile": review["Read role or profile"],
            "read_receipt_digest": review["Read receipt digest"],
            "read_valid_until": review["Read valid until"],
            "read_authority_source": review["Read authority source"],
            "identity_and_boundary_match": review["Identity and boundary match"],
            "blocker_or_stale_reason": review["Blocker or stale reason"],
        }
        if review_status in {"RUNNING", "STALE"}:
            return {**common_review, "status": "POST_ACTION_REVIEW"}
        return {
            **common_review,
            "status": review_status,
            "post_action_bound": review_status
            in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN", "BLOCKED"},
        }

    standalone_rows = [row for row in concrete if row.get("Attempt ID") == "NONE"]
    if not standalone_rows:
        return base
    latest = standalone_rows[-1]
    evidence_id = latest["Evidence ID"]
    status = latest["Status"]
    basis_stale = latest.get("REQ / DES / AUTH") != expected_basis
    authority_for_row = read_authority if current_read and not basis_stale else None
    require_current_read = bool(not basis_stale and status not in {"BLOCKED", "STALE"})
    issues = _teardown_read_row_issues(
        latest,
        authority_for_row,
        require_authority=require_current_read,
    )
    if (
        latest.get("Teardown authorization") != "NONE"
        or latest.get("Teardown receipt digest") != "NONE"
    ):
        issues.append("pre-action AWS-40 evidence cannot claim teardown authority")
    if status in {
        "READY_FOR_TEARDOWN",
        "VERIFIED_CLEAN",
        "RESIDUALS_REMAIN",
    } and latest.get("Identity and boundary match") not in {"PASS", "VERIFIED"}:
        issues.append(f"{evidence_id} requires a verified identity and boundary match")
    if issues:
        return {
            **base,
            "status": "BLOCKED",
            "evidence_id": evidence_id,
            "phase": "AWS-40",
            "basis_stale": basis_stale,
            "issues": issues,
        }
    projection = {
        **base,
        "status": status,
        "evidence_id": evidence_id,
        "observed_at": latest["Observed at"],
        "phase": "AWS-40",
        "read_authorization": latest["Read authorization"],
        "read_role_or_profile": latest["Read role or profile"],
        "read_receipt_digest": latest["Read receipt digest"],
        "read_valid_until": latest["Read valid until"],
        "read_authority_source": latest["Read authority source"],
        "expected_manifest_or_stack": latest["Expected manifest or stack"],
        "role_or_profile": latest["Role or profile"],
        "account": authority_for_row.get("account", "NONE")
        if authority_for_row
        else "NONE",
        "region": authority_for_row.get("region", "NONE")
        if authority_for_row
        else "NONE",
        "environment": authority_for_row.get("environment", "NONE")
        if authority_for_row
        else "NONE",
        "identity_and_boundary_match": latest["Identity and boundary match"],
        "blocker_or_stale_reason": latest["Blocker or stale reason"],
        "basis_stale": basis_stale,
    }
    if basis_stale or not current_read or construction_authorization == "NONE":
        return {**projection, "status": "BLOCKED" if status == "BLOCKED" else "STALE"}
    if status in {"RUNNING", "STALE"}:
        return projection
    if status == "BLOCKED":
        return projection
    allow_empty = status in {"VERIFIED_CLEAN", "RESIDUALS_REMAIN"}
    try:
        resources = _teardown_values(
            latest["Resources proposed to remove"],
            "Resources proposed to remove",
            allow_none=allow_empty,
        )
        operations = _teardown_values(
            latest["Allowed deletion operations"],
            "Allowed deletion operations",
            allow_none=allow_empty,
        )
        retained = _teardown_values(
            latest["Resources retained"], "Resources retained", allow_none=True
        )
        shared = _teardown_values(
            latest["Shared dependencies"], "Shared dependencies", allow_none=True
        )
        removed = _teardown_values(
            latest["Resources removed"], "Resources removed", allow_none=True
        )
        residuals = _teardown_values(
            latest["Residual resources"], "Residual resources", allow_none=True
        )
    except ValueError as exc:
        return {**projection, "status": "BLOCKED", "issues": [str(exc)]}
    if bool(resources) != bool(operations):
        issues.append(
            "Removal resources and deletion operations must both be present or NONE"
        )
    elif resources and not _receipt_scope_within_gate_b(
        resources, operations, envelope
    ):
        issues.append("AWS-40 removal scope exceeds Gate B")
    if (
        set(resources).intersection(retained)
        or set(resources).intersection(shared)
        or set(retained).intersection(shared)
    ):
        issues.append("AWS-40 removal, retention, and shared sets overlap")
    for field_name, allow_none in (
        ("Expected manifest or stack", False),
        ("Cost effect", False),
        ("Post-teardown verification", False),
    ):
        if not explicit_value(latest.get(field_name, ""), allow_none=allow_none):
            issues.append(f"AWS-40 requires {field_name}")
    if status == "VERIFIED_CLEAN":
        if residuals:
            issues.append("VERIFIED_CLEAN requires Residual resources = NONE")
        if set(removed) != set(resources):
            issues.append("VERIFIED_CLEAN must reconcile every proposed removal")
    if status == "RESIDUALS_REMAIN" and not residuals:
        issues.append("RESIDUALS_REMAIN requires an exact residual-resource list")
    if issues:
        return {**projection, "status": "BLOCKED", "issues": issues}
    return {
        **projection,
        "resources_to_remove": resources,
        "allowed_operations": operations,
        "resources_to_retain": retained,
        "shared_dependencies": shared,
        "resources_removed": removed,
        "residual_resources": residuals,
        "cost_effect": latest["Cost effect"],
        "post_action_verification": latest["Post-teardown verification"],
        "terminal_status": latest["Stack events and terminal status"],
        "snapshots_and_backups": latest["Snapshots and backups"],
        "inventory_limits": latest["Inventory or discovery limits"],
    }


def derive_read_preflight_state(
    verify_text: str,
    authority: Mapping[str, Any] | None,
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    artifact_binding: str,
) -> dict[str, Any]:
    """Validate observed account evidence separately from AWS guidance evidence."""

    base: dict[str, Any] = {
        "status": "NOT_STARTED",
        "preflight_id": "NONE",
        "read_authorization": (
            authority.get("authorization_id", "NONE") if authority else "NONE"
        ),
        "account": authority.get("account", "NONE") if authority else "NONE",
        "region": authority.get("region", "NONE") if authority else "NONE",
        "environment": (authority.get("environment", "NONE") if authority else "NONE"),
        "account_access": "NOT_OBSERVED",
        "evidence_ids": [],
        "issues": [],
    }
    if authority is None or authority.get("validity") != "CURRENT":
        return base
    try:
        rows = parse_read_preflight_evidence(verify_text)
    except ValueError as exc:
        return {**base, "status": "BLOCKED", "issues": [str(exc)]}
    concrete = [
        row
        for row in rows
        if AWS_PREFLIGHT_ID.fullmatch(clean_cell(row.get("Preflight ID", "")))
    ]
    identifiers = [clean_cell(row["Preflight ID"]) for row in concrete]
    if len(identifiers) != len(set(identifiers)):
        return {
            **base,
            "status": "BLOCKED",
            "issues": ["Read-only preflight evidence contains duplicate Preflight IDs"],
        }
    candidates = [
        row
        for row in concrete
        if clean_cell(row.get("Read authorization", ""))
        == authority.get("authorization_id")
    ]
    if not candidates:
        return {**base, "status": "RUNNING"}
    if len(candidates) != 1:
        return {
            **base,
            "status": "BLOCKED",
            "issues": [
                "Expected exactly one preflight row for the current read authorization"
            ],
        }
    row = candidates[0]
    preflight_id = clean_cell(row["Preflight ID"])
    result = clean_cell(row.get("Result", ""))
    expected_basis = (
        f"{requirements_revision} / {design_revision} / {construction_authorization}"
    )
    expected_scalars = {
        "REQ / DES / AUTH": expected_basis,
        "Artifact digest": artifact_binding,
        "Role or profile": authority.get("role_or_profile"),
        "Account": authority.get("account"),
        "Region": authority.get("region"),
        "Environment": authority.get("environment"),
    }
    issues = [
        f"{field_name} does not match current read scope"
        for field_name, expected in expected_scalars.items()
        if clean_cell(row.get(field_name, "")) != expected
    ]
    authority_binding = authority.get("artifact_plan_binding")
    authorized_artifact = (
        authority_binding.get("artifact")
        if isinstance(authority_binding, Mapping)
        else None
    )
    if authorized_artifact != artifact_binding:
        issues.append(
            "Read receipt artifact binding does not match the current artifact"
        )
    resources = _split_authority_values(row.get("Resources", ""))
    operations = _split_authority_values(row.get("Operations observed", ""))
    if len(operations) != len(set(operations)):
        issues.append("Operations observed must not contain duplicates")
    if resources != list(authority.get("resources", [])):
        issues.append("Resources do not exactly match current read scope")
    if not operations or not set(operations).issubset(
        set(authority.get("operations", []))
    ):
        issues.append("Operations observed are empty or exceed current read scope")
    try:
        evidence_ids = _canonical_id_list(
            row.get("AWS evidence IDs", ""),
            re.compile(r"EV-\d{4,}"),
            "AWS evidence IDs",
        )
    except ValueError as exc:
        evidence_ids = []
        issues.append(str(exc))
    if clean_cell(row.get("Account access", "")) != "READ_ONLY_OBSERVED":
        issues.append("Account access must be READ_ONLY_OBSERVED")
    for label in ("Caller identity evidence", "Boundary and drift evidence"):
        value = clean_cell(row.get(label, ""))
        if re.fullmatch(r"EV-\d{4,}", value) is None:
            issues.append(f"{label} must reference one EV ID")
        elif value not in evidence_ids:
            issues.append(f"{label} must be included in AWS evidence IDs")
    started = _iso_datetime(row.get("Started at", ""))
    completed = _iso_datetime(row.get("Completed at", ""))
    if started is None:
        issues.append("Started at must be ISO 8601 with timezone")
    if result == "READY":
        if completed is None or (started is not None and completed < started):
            issues.append("Completed at must be current and not precede Started at")
        if clean_cell(row.get("Identity and boundary match", "")) not in {
            "PASS",
            "VERIFIED",
        }:
            issues.append("Identity and boundary match must be PASS or VERIFIED")
    if issues:
        return {
            **base,
            "status": "STALE" if result in {"READY", "RUNNING"} else "BLOCKED",
            "preflight_id": preflight_id,
            "evidence_ids": evidence_ids,
            "issues": issues,
            "account_access": "NOT_VERIFIED",
        }
    if result not in {"RUNNING", "READY", "BLOCKED", "STALE"}:
        return {
            **base,
            "status": "BLOCKED",
            "preflight_id": preflight_id,
            "issues": ["Preflight Result is not canonical"],
            "account_access": "NOT_VERIFIED",
        }
    return {
        **base,
        "status": result,
        "preflight_id": preflight_id,
        "evidence_ids": evidence_ids,
        "account_access": "READ_ONLY_OBSERVED",
    }


def derive_aws_execution_projection(
    materiality: Mapping[str, Any],
    *,
    release_decision: str,
    guidance_ready: bool,
    read_authority: Mapping[str, Any] | None,
    preflight: Mapping[str, Any],
    lane: str | None = None,
) -> dict[str, Any]:
    active = release_decision == "READY_TO_DEPLOY"
    preflight_projection = dict(preflight)
    read_scope_current = bool(
        read_authority is not None and read_authority.get("validity") == "CURRENT"
    )
    if not active:
        progress = "NOT_ACTIVE"
    elif lane == "documentation-only" and guidance_ready:
        progress = "AWS_PREFLIGHT_READY"
        preflight_projection.update(
            {
                "status": "NOT_APPLICABLE",
                "account": "NONE",
                "region": "NONE",
                "environment": "NONE",
                "account_access": "NOT_USED",
                "issues": [],
            }
        )
    elif not guidance_ready:
        progress = "AWS_GUIDANCE_REQUIRED"
    elif not read_scope_current:
        progress = "AWS_READ_SCOPE_REQUIRED"
    elif preflight.get("status") != "READY":
        progress = "AWS_PREFLIGHT_RUNNING"
    elif lane == "explicit-gate":
        progress = "WAITING_AWS_MUTATION_AUTH"
    else:
        progress = "AWS_PREFLIGHT_READY"
    completed: list[str] = []
    if active:
        if guidance_ready:
            completed.append("AWS_GUIDANCE_REQUIRED")
        if read_scope_current:
            completed.append("AWS_READ_SCOPE_REQUIRED")
        if preflight.get("status") in {"RUNNING", "READY"}:
            completed.append("AWS_PREFLIGHT_RUNNING")
        if preflight.get("status") == "READY" or (
            lane == "documentation-only" and guidance_ready
        ):
            completed.append("AWS_PREFLIGHT_READY")
    return {
        "schema_version": 1,
        "active": active,
        "lane": lane or "NONE",
        "requirements_materiality": dict(materiality),
        "guidance": {
            "status": "CURRENT" if guidance_ready else "REQUIRED",
        },
        "read_scope": {
            "status": (
                "NOT_APPLICABLE"
                if lane == "documentation-only"
                else "CURRENT"
                if read_scope_current
                else "REQUIRED"
            ),
            "authorization_id": (
                read_authority.get("authorization_id", "NONE")
                if read_scope_current and read_authority is not None
                else "NONE"
            ),
        },
        "preflight": preflight_projection,
        "completed_states": completed,
        "progress_state": progress,
    }


def _receipt_external_authority(
    verify_text: str,
    action: str,
    construction_authorization: str,
    *,
    envelope: Mapping[str, str],
    cost_posture: str,
    active_artifact: str,
    preflight: Mapping[str, Any] | None = None,
    teardown_review: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if action not in {"Deployment", "Teardown"}:
        return None
    deployment = action == "Deployment"
    gate = "aws-deployment" if deployment else "aws-teardown"
    title = "AUTHORIZE AWS DEPLOYMENT" if deployment else "AUTHORIZE AWS TEARDOWN"
    expected_fields = (
        AWS_DEPLOYMENT_RECEIPT_FIELDS if deployment else AWS_TEARDOWN_RECEIPT_FIELDS
    )
    allow_none_fields = (
        frozenset({"Rollback boundary"})
        if deployment
        else frozenset({"Resources and data to retain", "Shared dependencies"})
    )
    try:
        receipt = marked_receipt(verify_text, gate)
    except ValueError:
        return None
    fields = _exact_receipt_fields(
        receipt,
        title,
        expected_fields,
        allow_none_fields=allow_none_fields,
    )
    row = _action_authorization_rows(verify_text).get(action)
    if fields is None or row is None or unresolved(receipt):
        return None
    auth_key = "AWS authorization" if deployment else "Teardown authorization"
    authorization_id = fields.get(auth_key, "")
    expected_pattern = r"AWS-AUTH-\d{4,}" if deployment else r"TEARDOWN-AUTH-\d{4,}"
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    result = clean_cell(row.get("Result", ""))
    valid_until = _receipt_validity_within_gate_b(
        fields.get("Valid until", ""), result, envelope
    )
    expected_scope = (
        f"ACCOUNT: {fields['Account']}; REGION: {fields['Region']}; "
        f"ENVIRONMENT: {fields['Environment']}"
    )
    resources_field = (
        "Stack, application, and resources"
        if deployment
        else "Stack, application, and resources to remove"
    )
    operations_field = (
        "Allowed operations" if deployment else "Allowed deletion operations"
    )
    resources = _split_authority_values(fields[resources_field])
    operations = _split_authority_values(fields[operations_field])
    expected_resources = (
        f"RESOURCES: {fields[resources_field]}; OPERATIONS: {fields[operations_field]}"
    )
    observed_at = clean_cell(row.get("Observed at", ""))
    if (
        re.fullmatch(expected_pattern, authorization_id) is None
        or fields.get("Construction authorization") != construction_authorization
        or row.get("Authorization ID") != authorization_id
        or row.get("Construction AUTH") != construction_authorization
        or row.get("Role or profile") != fields.get("Profile or role")
        or row.get("Approver") != fields.get("Approver")
        or not explicit_human_approver(fields.get("Approver", ""))
        or clean_cell(row.get("Verbatim receipt SHA-256", "")) != digest
        or clean_cell(row.get("Identity and boundary match", ""))
        not in {"PASS", "VERIFIED"}
        or row.get("Account / Region / environment") != expected_scope
        or row.get("Resources and operations") != expected_resources
        or not explicit_value(
            row.get("Stable owner-message source", ""), allow_none=False
        )
        or not explicit_timestamp(observed_at)
        or valid_until is None
        or result not in {"AUTHORIZED", "READY"}
        or not _receipt_identity_matches_gate_b(fields, envelope)
        or not _receipt_scope_within_gate_b(resources, operations, envelope)
    ):
        return None
    if deployment:
        artifact = fields["Artifact digest"]
        plan = fields["IaC plan/change-set binding"]
        cost_ceiling = fields["Cost ceiling"]
        rollback = fields["Rollback boundary"]
        preflight_id = clean_cell(
            preflight.get("preflight_id", "") if preflight else ""
        )
        expected_cost_validity = (
            f"COST: {cost_ceiling}; VALID_UNTIL: {fields['Valid until']}"
        )
        if (
            preflight is None
            or preflight.get("status") != "READY"
            or preflight.get("account_access") != "READ_ONLY_OBSERVED"
            or AWS_PREFLIGHT_ID.fullmatch(preflight_id) is None
            or clean_cell(row.get("Preflight evidence", "")) != preflight_id
            or row.get("Artifact digest") != artifact
            or row.get("IaC plan/change-set binding") != plan
            or row.get("Cost ceiling and validity") != expected_cost_validity
            or row.get("Rollback boundary") != rollback
            or AWS_PLAN_BINDING.fullmatch(plan) is None
            or not _receipt_artifact_matches_gate_b(artifact, envelope, active_artifact)
            or not _mutation_cost_within_gate_b(cost_ceiling, envelope, cost_posture)
            or rollback != _gate_b_rollback_value(envelope)
        ):
            return None
        kind = "AWS_DEPLOYMENT"
        retained_resources: list[str] = []
        shared_dependencies: list[str] = []
        cost_effect = "NONE"
        post_action_verification = "NONE"
        teardown_ready_binding = None
    else:
        teardown_review = teardown_review or {}
        evidence_id = clean_cell(teardown_review.get("evidence_id", ""))
        retained_resources = _split_authority_values(
            fields["Resources and data to retain"]
        )
        shared_dependencies = _split_authority_values(fields["Shared dependencies"])
        cost_effect = fields["Cost effect"]
        post_action_verification = fields["Post-teardown verification"]
        expected_cost_validity = (
            f"COST: {cost_effect}; VALID_UNTIL: {fields['Valid until']}"
        )
        teardown_artifact = "NOT_APPLICABLE — teardown binds the observed inventory"
        teardown_plan = "NOT_APPLICABLE — teardown uses its removal/retention manifest"
        overlap = (
            set(resources).intersection(retained_resources)
            or set(resources).intersection(shared_dependencies)
            or set(retained_resources).intersection(shared_dependencies)
        )
        unsafe_lists = any(
            "*" in item
            for item in resources
            + operations
            + retained_resources
            + shared_dependencies
        )
        if (
            teardown_review.get("status") != "READY_FOR_TEARDOWN"
            or re.fullmatch(r"EV-\d{4,}", evidence_id) is None
            or clean_cell(row.get("Preflight evidence", "")) != evidence_id
            or row.get("Artifact digest") != teardown_artifact
            or row.get("IaC plan/change-set binding") != teardown_plan
            or row.get("Cost ceiling and validity") != expected_cost_validity
            or row.get("Rollback boundary") != post_action_verification
            or resources != list(teardown_review.get("resources_to_remove", []))
            or operations != list(teardown_review.get("allowed_operations", []))
            or retained_resources
            != list(teardown_review.get("resources_to_retain", []))
            or shared_dependencies
            != list(teardown_review.get("shared_dependencies", []))
            or cost_effect != teardown_review.get("cost_effect")
            or post_action_verification
            != teardown_review.get("post_action_verification")
            or fields["Profile or role"] != teardown_review.get("role_or_profile")
            or fields["Account"] != teardown_review.get("account")
            or fields["Region"] != teardown_review.get("region")
            or fields["Environment"] != teardown_review.get("environment")
            or clean_cell(teardown_review.get("identity_and_boundary_match", ""))
            not in {"PASS", "VERIFIED"}
            or overlap
            or unsafe_lists
            or len(retained_resources) != len(set(retained_resources))
            or len(shared_dependencies) != len(set(shared_dependencies))
        ):
            return None
        artifact = teardown_artifact
        plan = teardown_plan
        cost_ceiling = clean_cell(envelope.get("AWS cost ceiling", ""))
        rollback = clean_cell(envelope.get("AWS rollback boundary", ""))
        if (
            _parse_cost_ceiling(cost_ceiling) is None
            or _gate_b_rollback_value(envelope) is None
        ):
            return None
        kind = "AWS_TEARDOWN"
        teardown_ready_binding = {
            "evidence_id": evidence_id,
            "read_authorization": clean_cell(
                teardown_review.get("read_authorization", "")
            ),
            "read_role_or_profile": clean_cell(
                teardown_review.get("read_role_or_profile", "")
            ),
            "read_receipt_digest": clean_cell(
                teardown_review.get("read_receipt_digest", "")
            ),
            "read_valid_until": clean_cell(teardown_review.get("read_valid_until", "")),
            "read_authority_source": clean_cell(
                teardown_review.get("read_authority_source", "")
            ),
            "expected_manifest_or_stack": clean_cell(
                teardown_review.get("expected_manifest_or_stack", "")
            ),
            "resources_retained": retained_resources,
            "shared_dependencies": shared_dependencies,
            "cost_effect": cost_effect,
            "post_teardown_verification": post_action_verification,
        }
    return {
        "kind": kind,
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": digest,
        "account": fields["Account"],
        "region": fields["Region"],
        "environment": fields["Environment"],
        "role_or_profile": fields["Profile or role"],
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {"artifact": artifact, "plan": plan},
        "cost_ceiling": cost_ceiling,
        "rollback_boundary": rollback,
        "expiration": valid_until,
        "retained_resources": retained_resources,
        "shared_dependencies": shared_dependencies,
        "cost_effect": cost_effect,
        "post_action_verification": post_action_verification,
        "teardown_ready_binding": teardown_ready_binding,
    }


def derive_external_authority(
    ctx: Context,
    envelope: dict[str, str],
    lane: str | None,
    construction_authorization: str,
    *,
    cost_posture: str = "",
    aws_progress_state: str | None = None,
    active_artifact: str = "",
    preflight: Mapping[str, Any] | None = None,
    aws_action_phase: str | None = None,
    teardown_review: Mapping[str, Any] | None = None,
    deployment_sequence: Mapping[str, Any] | None = None,
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
    verify_text = ctx.texts.get(VERIFY_FILE, "")
    if aws_action_phase == "AWS-30" and deployment_sequence is not None:
        if ctx.has_errors or deployment_sequence.get("issues"):
            return empty
        reconciliation_authority = deployment_sequence.get(
            "reconciliation_read_authority"
        )
        if (
            isinstance(reconciliation_authority, Mapping)
            and reconciliation_authority.get("kind") == "AWS_READ_ONLY"
            and reconciliation_authority.get("validity") == "CURRENT"
            and reconciliation_authority.get("reconciliation_only") in {True, False}
            and reconciliation_authority.get("attempt_id")
            == deployment_sequence.get("attempt_id")
        ):
            return dict(reconciliation_authority)
        if (
            clean_cell(deployment_sequence.get("status", ""))
            == "RECONCILIATION_REQUIRED"
        ):
            required = dict(empty)
            required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
            required["validity"] = "REQUIRED"
            return required
        return empty
    if (
        aws_action_phase == "AWS-40"
        and teardown_review is not None
        and clean_cell(teardown_review.get("status", "")) == "POST_ACTION_REVIEW"
    ):
        if ctx.has_errors or teardown_review.get("issues"):
            return empty
        reconciliation_authority = teardown_review.get("reconciliation_read_authority")
        if (
            isinstance(reconciliation_authority, Mapping)
            and reconciliation_authority.get("kind") == "AWS_READ_ONLY"
            and reconciliation_authority.get("validity") == "CURRENT"
            and reconciliation_authority.get("reconciliation_only") in {True, False}
            and reconciliation_authority.get("attempt_id")
            == teardown_review.get("attempt_id")
        ):
            return dict(reconciliation_authority)
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if ctx.has_errors or construction_authorization == "NONE":
        return empty
    if aws_action_phase not in {"AWS-10", "AWS-20", "AWS-30", "AWS-40", "AWS-50"}:
        return empty
    if aws_action_phase == "AWS-10" and aws_progress_state == "AWS_READ_SCOPE_REQUIRED":
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if aws_action_phase == "AWS-10" and aws_progress_state == "AWS_PREFLIGHT_RUNNING":
        read_authority = _read_preflight_receipt_authority(
            verify_text,
            construction_authorization,
            cost_posture,
            envelope,
            active_artifact,
        )
        if read_authority is not None:
            return read_authority
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if (
        aws_action_phase == "AWS-10"
        and aws_progress_state == "AWS_PREFLIGHT_READY"
        and lane == "read-only"
    ):
        read_authority = _read_preflight_receipt_authority(
            verify_text,
            construction_authorization,
            cost_posture,
            envelope,
            active_artifact,
        )
        return read_authority if read_authority is not None else empty
    if aws_action_phase in {"AWS-30", "AWS-40"}:
        read_authority = _read_preflight_receipt_authority(
            verify_text,
            construction_authorization,
            cost_posture,
            envelope,
            active_artifact,
            allow_one_operation=False,
        )
        if read_authority is not None:
            return read_authority
        required = dict(empty)
        required["kind"] = "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    boundary = envelope.get("AWS boundary", "NONE")
    if boundary not in {"READ_ONLY", "MUTATE_LISTED_RESOURCES"}:
        return empty
    if boundary == "READ_ONLY":
        # Gate B bounds the project but never substitutes for the exact
        # owner-authored preflight receipt required for authenticated reads.
        return empty
    if aws_action_phase == "AWS-50":
        if clean_cell((teardown_review or {}).get("status", "")) in {
            "ACTION_TERMINAL_REQUIRED",
            "POST_ACTION_REVIEW",
            "VERIFIED_CLEAN",
            "RESIDUALS_REMAIN",
            "BLOCKED",
        }:
            return empty
        authority = _receipt_external_authority(
            verify_text,
            "Teardown",
            construction_authorization,
            envelope=envelope,
            cost_posture=cost_posture,
            active_artifact=active_artifact,
            teardown_review=teardown_review,
        )
        if authority is not None:
            return authority
        required = dict(empty)
        required["kind"] = "AWS_ACTION_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED"
        return required
    if aws_action_phase != "AWS-20":
        return empty
    preflight_ready = bool(
        preflight is not None
        and preflight.get("status") == "READY"
        and preflight.get("account_access") == "READ_ONLY_OBSERVED"
        and AWS_PREFLIGHT_ID.fullmatch(clean_cell(preflight.get("preflight_id", "")))
        is not None
    )
    if lane == "explicit-gate" and boundary == "MUTATE_LISTED_RESOURCES":
        if aws_progress_state != "WAITING_AWS_MUTATION_AUTH" or not preflight_ready:
            return empty
        candidates = [
            item
            for item in (
                _receipt_external_authority(
                    verify_text,
                    "Deployment",
                    construction_authorization,
                    envelope=envelope,
                    cost_posture=cost_posture,
                    active_artifact=active_artifact,
                    preflight=preflight,
                ),
            )
            if item is not None
        ]
        if len(candidates) == 1:
            candidate = candidates[0]
            consumed = deployment_sequence or {}
            same_consumed_authority = (
                clean_cell(consumed.get("status", "")) == "CONSUMED"
                and clean_cell(consumed.get("deployment_authorization", ""))
                == clean_cell(candidate.get("authorization_id", ""))
                and clean_cell(consumed.get("deployment_receipt_digest", ""))
                == clean_cell(candidate.get("receipt_digest", ""))
            )
            if not same_consumed_authority:
                return candidate
            candidates = []
        required = dict(empty)
        required["kind"] = "AWS_ACTION_RECEIPT_REQUIRED"
        required["validity"] = "REQUIRED" if not candidates else "CONFLICTING"
        return required
    if boundary != "MUTATE_LISTED_RESOURCES" or lane != "fast-dev":
        return empty
    if aws_progress_state != "AWS_PREFLIGHT_READY" or not preflight_ready:
        return empty
    try:
        expiration = parse_future_expiry(envelope.get("AWS authorization validity", ""))
    except ValueError:
        return empty
    environment = envelope.get("AWS environment", "")
    environment_name = environment
    try:
        environment_name, _environment_class = parse_aws_environment(environment)
    except ValueError:
        return empty
    account = _envelope_scalar(envelope, "AWS account", "ACCOUNT")
    region = _envelope_scalar(envelope, "AWS Region", "REGION")
    role = _envelope_scalar(envelope, "AWS role or profile", "ROLE")
    resources = _envelope_values(envelope, "AWS resource allowlist", "RESOURCES")
    allowed_operations = _envelope_values(
        envelope, "AWS allowed operations", "OPERATIONS"
    )
    operations = [
        operation
        for operation in allowed_operations
        if AWS_READ_ONLY_OPERATION.fullmatch(operation) is None
    ]
    if (
        account is None
        or not operations
        or region is None
        or role is None
        or clean_cell(preflight.get("account", "")) != account
        or clean_cell(preflight.get("region", "")) != region
        or clean_cell(preflight.get("environment", "")) != environment_name
        or not _receipt_artifact_matches_gate_b(
            active_artifact, envelope, active_artifact
        )
        or not _receipt_scope_within_gate_b(resources, operations, envelope)
    ):
        return empty
    kind = "FAST_DEV_GATE_B"
    cost_ceiling = envelope.get("AWS cost ceiling", "NONE")
    if not _mutation_cost_within_gate_b(cost_ceiling, envelope, cost_posture):
        return empty
    currency, amount = parse_positive_cost(
        cost_ceiling,
        AWS_COST_CEILING,
        "AWS cost ceiling",
    )
    cost_ceiling = f"{currency}: {amount:.2f}"
    return {
        "kind": kind,
        "validity": "CURRENT",
        "authorization_id": construction_authorization,
        "receipt_digest": "NONE",
        "account": account,
        "region": region,
        "environment": environment_name,
        "role_or_profile": role,
        "resources": resources,
        "operations": operations,
        "artifact_plan_binding": {
            "artifact": active_artifact,
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
    match = re.fullmatch(
        r"(?P<currency>[A-Z]{3}):\s*(?P<amount>\d+(?:\.\d{1,2})?)", normalized
    )
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
        issues.append(
            "exactly one reviewed script or immutable artifact digest is required"
        )

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
    validity = (
        raw_validity
        if raw_validity in {"CURRENT", "NONE", "STALE", "BLOCKED"}
        else "BLOCKED"
    )
    binding = authority.get("artifact_plan_binding")
    binding = binding if isinstance(binding, dict) else {}
    raw_teardown_binding = authority.get("teardown_ready_binding")
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
        "rollback_boundary": _machine_value(
            authority.get("rollback_boundary"), "ROLLBACK"
        ),
        "expires_at": _machine_value(authority.get("expiration")),
        "allowed_execution_lanes": [],
        "reviewed_script": None,
        "teardown_ready_binding": None,
    }
    if request_match["authority_kind"] == "AWS_TEARDOWN" and isinstance(
        raw_teardown_binding, Mapping
    ):
        request_match["teardown_ready_binding"] = {
            "evidence_id": _machine_value(raw_teardown_binding.get("evidence_id")),
            "read_authorization": _machine_value(
                raw_teardown_binding.get("read_authorization")
            ),
            "read_role_or_profile": _machine_value(
                raw_teardown_binding.get("read_role_or_profile"), "ROLE"
            ),
            "read_receipt_digest": _machine_value(
                raw_teardown_binding.get("read_receipt_digest")
            ),
            "read_valid_until": _machine_value(
                raw_teardown_binding.get("read_valid_until")
            ),
            "read_authority_source": _machine_value(
                raw_teardown_binding.get("read_authority_source")
            ),
            "expected_manifest_or_stack": _machine_value(
                raw_teardown_binding.get("expected_manifest_or_stack")
            ),
            "resources_retained": _machine_list(
                raw_teardown_binding.get("resources_retained"), "RESOURCES"
            ),
            "shared_dependencies": _machine_list(
                raw_teardown_binding.get("shared_dependencies"), "RESOURCES"
            ),
            "cost_effect": _machine_value(raw_teardown_binding.get("cost_effect")),
            "post_teardown_verification": _machine_value(
                raw_teardown_binding.get("post_teardown_verification")
            ),
        }
    if validity != "CURRENT":
        return request_match
    request_match["allowed_execution_lanes"] = ["STRUCTURED_API"]
    reviewed_script = _reviewed_script_contract(ctx, request_match)
    if reviewed_script is not None:
        request_match["allowed_execution_lanes"].append("REVIEWED_SCRIPT")
        request_match["reviewed_script"] = reviewed_script
    return request_match


def _aws_action_transition_projection(
    request_match: Mapping[str, Any] | None,
    sequence: Mapping[str, Any],
    *,
    authority_kind: str,
    authorization_field: str,
    receipt_digest_field: str,
) -> dict[str, Any]:
    """Bind one consumed journal attempt to its exact pre-call request ceiling.

    This projection is not mutation authority. It exists only so the optional
    hook can prove that the same-session call following STARTED is identical to
    the request that was current immediately before the journal append.
    """

    empty: dict[str, Any] = {
        "schema_version": 1,
        "status": "NONE",
        "attempt_id": "NONE",
        "authority_kind": "NONE",
        "request_match_sha256": "NONE",
        "request_match": {},
    }
    if (
        clean_cell(sequence.get("status", "")) != "ACTION_TERMINAL_REQUIRED"
        or sequence.get("issues")
        or not isinstance(request_match, Mapping)
        or request_match.get("schema_version") != 1
        or request_match.get("validity") != "CURRENT"
        or request_match.get("authority_kind") != authority_kind
        or clean_cell(request_match.get("authorization_id", ""))
        != clean_cell(sequence.get(authorization_field, ""))
        or clean_cell(request_match.get("receipt_digest", ""))
        != clean_cell(sequence.get(receipt_digest_field, ""))
    ):
        return empty
    attempt_id = clean_cell(sequence.get("attempt_id", ""))
    pattern = (
        AWS_TEARDOWN_ATTEMPT_ID
        if authority_kind == "AWS_TEARDOWN"
        else AWS_DEPLOYMENT_ATTEMPT_ID
    )
    if pattern.fullmatch(attempt_id) is None:
        return empty
    normalized = dict(request_match)
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                normalized,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
    )
    return {
        **empty,
        "status": "BOUND",
        "attempt_id": attempt_id,
        "authority_kind": authority_kind,
        "request_match_sha256": digest,
        "request_match": normalized,
    }


PROMPT_DOCS_ONLY_AWS_MODES = frozenset({"REQ-10", "DESIGN-10", "BUG-10"})
PROMPT_READ_ONLY_AWS_MODES = frozenset({"AWS-10", "AWS-30", "AWS-40"})
PROMPT_MUTATION_AWS_MODES = frozenset({"AWS-20", "AWS-50"})


def derive_current_prompt_aws_mode(next_prompt: str) -> str:
    """Return the maximum phase mode; authority is projected separately."""

    if next_prompt in PROMPT_DOCS_ONLY_AWS_MODES:
        return "DOCS_ONLY"
    if next_prompt in PROMPT_READ_ONLY_AWS_MODES:
        return "READ_ONLY"
    if next_prompt in PROMPT_MUTATION_AWS_MODES:
        return "MUTATION"
    return "NONE"


def derive_aws_mode_boundary(
    lane: str | None,
    envelope: Mapping[str, str],
    next_prompt: str,
    external_authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Separate planned ceilings, prompt capability, and current authority."""

    project_lane = lane if lane in AWS_LANES else "NONE"
    proposed_gate_b = clean_cell(envelope.get("AWS boundary", "NONE")).upper()
    gate_b_maximum = proposed_gate_b if proposed_gate_b in AWS_BOUNDARIES else "NONE"
    local_task_modes = ["NONE"] if gate_b_maximum == "NONE" else ["NONE", "DOCS_ONLY"]
    current_prompt_mode = derive_current_prompt_aws_mode(next_prompt)
    external_kind = clean_cell(external_authority.get("kind", "NONE")) or "NONE"
    external_validity = clean_cell(external_authority.get("validity", "NONE")) or "NONE"
    read_authorized = (
        current_prompt_mode == "READ_ONLY"
        and external_kind == "AWS_READ_ONLY"
        and external_validity == "CURRENT"
    )
    mutation_authorized = (
        current_prompt_mode == "MUTATION"
        and external_kind in {"AWS_DEPLOYMENT", "AWS_TEARDOWN", "FAST_DEV_GATE_B"}
        and external_validity == "CURRENT"
    )
    return {
        "project_lane": project_lane,
        "local_task_modes": local_task_modes,
        "current_prompt_mode": current_prompt_mode,
        "gate_b_maximum": gate_b_maximum,
        "external_authority_kind": external_kind,
        "external_authority_validity": external_validity,
        "account_access_authorized": read_authorized or mutation_authorized,
        "mutation_authorized": mutation_authorized,
    }


def _summary_table(ctx: Context, path: str, heading: str) -> dict[str, str]:
    text = ctx.texts.get(path, "")
    if not text:
        return {}
    try:
        return table_after_heading(text, heading)
    except ValueError:
        return {}


def _summary_value(value: object, fallback: str) -> str:
    cleaned = clean_cell(value)
    return cleaned if explicit_value(cleaned, allow_none=False) else fallback


def _summary_bullet(text: str, label: str) -> str:
    match = re.search(rf"(?m)^- {re.escape(label)}:[ \t]*(?P<value>.+?)[ \t]*$", text)
    return clean_cell(match.group("value")) if match else ""


# fmt: off
def derive_document_summary_specifications(ctx: Context, *, classification: str, lifecycle_state: str, next_prompt: str, project: Mapping[str, Any], prd_fields: Mapping[str, str], gate_a: str, gate_b: str, tasks: TaskSummary, release_decision: str, release_evidence_cutoff: str, aws_authorization: str, external_authority: Mapping[str, Any], interaction: Mapping[str, Any], active_artifact: str, deployment_sequence: Mapping[str, Any]) -> list[dict[str, Any]]:
# fmt: on
    """Normalize existing canonical values for the presentation-only summaries."""

    template_like = classification in {"TEMPLATE_SOURCE", "UNCONFIGURED_TEMPLATE"}
    prd_card = _summary_table(ctx, PRD_FILE, "### Gate A — readiness card")
    task_snapshot = _summary_table(ctx, TASKS_FILE, "## Active execution snapshot")
    verify_scope = _summary_table(ctx, VERIFY_FILE, "## Active evidence scope")
    runbook_boundary = _summary_table(ctx, RUNBOOK_FILE, "## Active operational boundary")
    verify_text = ctx.texts.get(VERIFY_FILE, "")
    bugfix_text = ctx.texts.get(BUGFIX_FILE, "")

    requirements_id = prd_fields.get("requirements_revision")
    design_id = prd_fields.get("design_revision")
    authorization_id = prd_fields.get("construction_authorization")
    checkpoint = _summary_value(task_snapshot.get("Last checkpoint"), "None")
    cutoff = _summary_value(release_evidence_cutoff, "Not yet recorded")
    updated = next(
        (
            value
            for value in (
                cutoff if cutoff != "Not yet recorded" else "",
                checkpoint if checkpoint != "None" else "",
                design_id,
                requirements_id,
            )
            if value
        ),
        "Current canonical records",
    )

    observed_ids: set[str] = set()
    failed_ids: set[str] = set()
    for line in verify_text.splitlines():
        evidence_ids = re.findall(r"\b(?:AWS-)?EV-\d{4,}\b", line)
        if not evidence_ids:
            continue
        upper = line.upper()
        if any(status in upper for status in ("VERIFIED", "PASSED", "OBSERVED")):
            observed_ids.update(evidence_ids)
        if any(status in upper for status in ("FAILED", "STALE", "BLOCKED")):
            failed_ids.update(evidence_ids)

    local_observed = release_decision in {"READY_TO_DEPLOY", "RELEASE_VERIFIED"}
    deployment_status = clean_cell(deployment_sequence.get("status", "NOT_ACTIVE"))
    deployment_observed = deployment_status == "RECONCILED"
    requirements_approved = gate_a == "APPROVED_FOR_DESIGN"
    design_approved = gate_b == "APPROVED_FOR_CONSTRUCTION"
    guidance_ready = not any(
        item.code.startswith("AWS_CORE_") and item.severity == "ERROR"
        for item in ctx.diagnostics
    )
    # fmt: off
    claim_rows = (
        ("Requirements are approved", requirements_approved, ("Owner confirmed", requirements_id, "Does not approve construction"), ("Not yet observed", "None", "Gate A is not approved")),
        ("Technical design is approved", design_approved, ("Owner confirmed", design_id, "Does not authorize AWS account work"), ("Not yet observed", "None", "Gate B is not approved")),
        ("Current AWS guidance informed the plan", guidance_ready and not template_like, ("Source verified", "Current AWS Core evidence", "Source guidance is not deployment evidence"), ("Not yet observed", "None", "Source guidance is not deployment evidence")),
        ("Local release checks passed", local_observed, ("Locally observed", release_decision, "Local evidence does not prove AWS behavior"), ("Not yet observed", "None", "Local evidence does not prove AWS behavior")),
        ("Application is deployed", deployment_observed, ("Deployed observed", "Deployment reconciliation", "Bound to the observed environment"), ("Not authorized", "None", "No deployment evidence or authority")),
    )
    # fmt: on
    claims = []
    for claim, ready, current, pending in claim_rows:
        maturity, evidence, limitation = current if ready else pending
        claims.append(
            {
                "claim": claim,
                "maturity": maturity,
                "evidence": evidence,
                "limitation": limitation,
            }
        )

    task_progress = (
        f"{len(tasks.done)} of {tasks.total} tasks complete"
        if tasks.total
        else "No tasks generated"
    )
    bug_title = _summary_bullet(bugfix_text, "Title")
    bug_active = active_artifact == BUGFIX_FILE or explicit_value(bug_title)
    bugfix = {
        "status": "Active bounded defect" if bug_active else "No active bounded defect",
        "defect": _summary_value(bug_title, "None") if bug_active else "None",
        "impact": "Recorded in the defect contract" if bug_active else "None",
        "reproduction": "Pending evidence" if bug_active else "Not active",
        "root_cause": "Pending evidence" if bug_active else "Not active",
        "repair": "Not started" if bug_active else "Not active",
        "regression": "Pending evidence" if bug_active else "Not active",
        "architecture": "Not yet assessed" if bug_active else "None",
        "environment": (
            _summary_value(_summary_bullet(bugfix_text, "Environment"), "Not recorded")
            if bug_active
            else "Not active"
        ),
        "requirements": (
            _summary_value(_summary_bullet(bugfix_text, "Related PRD requirements"), "None")
            if bug_active
            else "None"
        ),
        "updated": updated,
    }
    account_access = (
        external_authority.get("validity") == "CURRENT"
        and external_authority.get("kind")
        in {"AWS_READ_ONLY", "AWS_DEPLOYMENT", "AWS_TEARDOWN", "FAST_DEV_GATE_B"}
    )
    environment = _summary_value(
        runbook_boundary.get("Region and environment"),
        (
            f"Development in {project.get('region')}"
            if project.get("region")
            else "Development"
        ),
    )
    # fmt: off
    return build_summary_specifications({
        "template_like": template_like, "lifecycle_state": lifecycle_state, "next_prompt": next_prompt,
        "owner_stage": interaction.get("owner_stage"), "action_kind": interaction.get("action_kind"),
        "automatic_continuation_allowed": interaction.get("automatic_continuation_allowed"),
        "gate_a": gate_a, "gate_b": gate_b, "requirements_revision": requirements_id,
        "design_revision": design_id, "construction_authorization": authorization_id,
        "aws_authorization": aws_authorization, "aws_account_access_authorized": account_access,
        "updated": updated, "product_outcome": _summary_value(prd_card.get("Outcome"), "Not yet confirmed"),
        "release_boundary": _summary_value(prd_card.get("Scope"), "Not yet confirmed"),
        "region_and_cost": "Not yet recorded" if template_like else f"{project.get('region') or 'Region not recorded'}; {project.get('cost_posture') or 'Cost posture not recorded'}",
        "record_identities": "Not yet initialized" if template_like else " / ".join(item for item in (requirements_id, design_id, authorization_id) if item),
        "tasks": {
            "progress": task_progress, "plan_revision": tasks.plan_revision,
            "wave": _summary_value(task_snapshot.get("Current wave"), "None"),
            "active": ", ".join(tasks.active) if tasks.active else "None",
            "readiness": tasks.plan_state.replace("_", " ").title(),
            "blocker": ", ".join(tasks.blocked) if tasks.blocked else "None",
            "checkpoint": checkpoint, "known_green": _summary_value(task_snapshot.get("Last known-green commit"), "None"),
            "updated": checkpoint if checkpoint != "None" else updated,
        },
        "verify": {
            "release_result": release_decision.replace("_", " ").title(),
            "observed_count": str(len(observed_ids)), "failed_count": str(len(failed_ids)),
            "unobserved": "Recovery and teardown" if deployment_observed else "AWS deployment, recovery, and teardown" if local_observed else "Local build, AWS deployment, recovery, and teardown",
            "cutoff": _summary_value(verify_scope.get("Evidence cutoff"), cutoff),
            "updated": cutoff if cutoff != "Not yet recorded" else updated, "claims": claims,
        },
        "operations": {
            "environment": environment,
            "deployment_state": "Deployment observed" if deployment_observed else "Not deployed" if deployment_status in {"", "NOT_ACTIVE", "NONE"} else deployment_status.replace("_", " ").title(),
            "authority": str(external_authority.get("kind", "None")).replace("_", " ").title() if account_access else "None",
            "safe_action": "Only the exact authorized AWS operation" if account_access else "Local validation only",
            "deployment_approval": "Authorized only for the current deployment" if account_access and external_authority.get("kind") in {"AWS_DEPLOYMENT", "FAST_DEV_GATE_B"} else "Not authorized",
            "teardown_approval": "Authorized only for the current teardown" if account_access and external_authority.get("kind") == "AWS_TEARDOWN" else "Not authorized",
            "recovery_state": "Not yet observed",
            "emergency_state": "Follow the current runbook and authority" if deployment_observed else "No deployed environment exists",
            "updated": updated,
        },
        "bugfix": bugfix,
    })
    # fmt: on



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
    intake_contract: IntakeFoundationContract | None = None,
    coverage_contract: CoverageContract | None = None,
    requirements_contract: RequirementsContract | None = None,
    aws_core_usage: Mapping[str, Any] | None = None,
    aws_execution: Mapping[str, Any] | None = None,
    owner_stage_hint: str | None = None,
    active_artifact: str = "",
    deployment_sequence: Mapping[str, Any] | None = None,
    teardown_sequence: Mapping[str, Any] | None = None,
    release_evidence_cutoff: str = "NONE",
    req_aws_core_materiality: str = "OPTIONAL",
    req_aws_core_ready: bool = True,
    aws_lifecycle_intent_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = manifest or {}
    state = state or {}
    setup = state.get("setup") if isinstance(state.get("setup"), dict) else {}
    project = state.get("project") if isinstance(state.get("project"), dict) else {}
    lifecycle = (
        state.get("lifecycle") if isinstance(state.get("lifecycle"), dict) else {}
    )
    envelope = envelope or {}
    aws_execution_projection = dict(aws_execution or {})
    deployment_sequence_projection = dict(deployment_sequence or {})
    teardown_sequence_projection = dict(teardown_sequence or {})
    aws_sequence_conflict = aws_deployment_teardown_sequence_conflict(
        deployment_sequence_projection, teardown_sequence_projection
    )
    if aws_sequence_conflict:
        if not any(
            item.code == "AWS_DEPLOYMENT_TEARDOWN_CONFLICT" for item in ctx.diagnostics
        ):
            ctx.error(
                "AWS_DEPLOYMENT_TEARDOWN_CONFLICT",
                "Open deployment and teardown journal epochs cannot coexist; close one sequence before continuing",
                VERIFY_FILE,
            )
        lifecycle_state, next_prompt = "BLOCKED", "STOP"
    lifecycle_intent_projection = dict(
        aws_lifecycle_intent_record
        or {
            "value": "NONE",
            "source": "NONE",
            "recorded_at": "NONE",
            "provenance_status": "CURRENT",
            "authorizes_aws_access": False,
            "authorizes_mutation": False,
        }
    )
    residual_disposition_projection = derive_aws_residual_disposition(
        lifecycle_intent_projection, teardown_sequence_projection
    )
    aws_progress_state = (
        str(aws_execution_projection.get("progress_state"))
        if aws_execution_projection.get("active") is True
        else None
    )
    if design_contract is None:
        design_contract = DesignContract(
            design_revision=(
                prd_fields.get("design_revision") or lifecycle.get("design_revision")
            )
        )
    if coverage_contract is None:
        coverage_contract = CoverageContract()
    if intake_contract is None:
        intake_contract = IntakeFoundationContract()
    if requirements_contract is None:
        requirements_contract = RequirementsContract()
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
    resolved_owner_stage = (
        owner_stage_hint
        if owner_stage_hint in {"DEFINE", "DESIGN", "DELIVER"}
        else _owner_stage_from_gates(gate_a, gate_b)
    )
    authorization_id = prd_fields.get("construction_authorization") or lifecycle.get(
        "construction_authorization"
    )
    gate_b_authorization = (
        authorization_id
        if not ctx.has_errors and gate_b == "APPROVED_FOR_CONSTRUCTION"
        else "NONE"
    )
    deployment_status = clean_cell(deployment_sequence_projection.get("status", ""))
    auditable_status = (
        deployment_status
        in {
            "ACTION_TERMINAL_REQUIRED",
            "RECONCILIATION_REQUIRED",
            "RECONCILED",
            "BLOCKED",
        }
        or (deployment_status == "CONSUMED" and release_decision != "READY_TO_DEPLOY")
        or (
            deployment_status == "NOT_ACTIVE" and release_decision == "RELEASE_VERIFIED"
        )
    )
    deployment_authority_restricted = bool(
        not ctx.has_errors
        and not deployment_sequence_projection.get("issues")
        and auditable_status
    )
    teardown_status = clean_cell(teardown_sequence_projection.get("status", ""))
    teardown_attempt_id = clean_cell(teardown_sequence_projection.get("attempt_id", ""))
    teardown_action_status = clean_cell(
        teardown_sequence_projection.get("action_status", "")
    )
    teardown_attempt_unreconciled = bool(
        AWS_TEARDOWN_ATTEMPT_ID.fullmatch(teardown_attempt_id)
        and teardown_action_status in {"STARTED", *AWS_TEARDOWN_TERMINAL_STATUSES}
        and teardown_status
        in {"ACTION_TERMINAL_REQUIRED", "POST_ACTION_REVIEW", "BLOCKED"}
    )
    teardown_authority_restricted = bool(teardown_attempt_unreconciled)
    restricted_construction_authorization = (
        "NONE"
        if deployment_authority_restricted or teardown_authority_restricted
        else gate_b_authorization
    )
    aws_authorization = "NONE"
    deployment_journal_closure_authority = derive_deployment_journal_closure_authority(
        deployment_sequence_projection,
        next_prompt,
        restricted_closure=deployment_authority_restricted,
    )
    teardown_journal_closure_authority = derive_teardown_journal_closure_authority(
        teardown_sequence_projection,
        next_prompt,
        restricted_closure=teardown_authority_restricted,
    )
    external_authority = derive_external_authority(
        ctx,
        envelope,
        lane,
        restricted_construction_authorization,
        cost_posture=str(project.get("cost_posture", "")),
        aws_progress_state=aws_progress_state,
        active_artifact=active_artifact,
        aws_action_phase=next_prompt,
        teardown_review=teardown_sequence_projection,
        deployment_sequence=deployment_sequence_projection,
        preflight=(
            aws_execution_projection.get("preflight")
            if isinstance(aws_execution_projection.get("preflight"), Mapping)
            else None
        ),
    )
    aws_lifecycle_intent_write_authority = derive_aws_lifecycle_intent_write_authority(
        ctx,
        tasks,
        release_decision,
        deployment_sequence_projection,
        teardown_sequence_projection,
        external_authority,
        lifecycle_intent=lifecycle_intent_projection,
    )
    construction_authorization = (
        "NONE"
        if aws_lifecycle_intent_write_authority.get("valid") is True
        else restricted_construction_authorization
    )
    write_authority = derive_write_authority(
        ctx, envelope, tasks, construction_authorization
    )
    if external_authority.get("validity") == "CURRENT" and external_authority.get(
        "kind"
    ) in {"AWS_READ_ONLY", "AWS_DEPLOYMENT", "AWS_TEARDOWN", "FAST_DEV_GATE_B"}:
        projected_authorization = external_authority.get("authorization_id")
        if isinstance(projected_authorization, str):
            aws_authorization = projected_authorization
    external_authority["request_match"] = derive_request_match(ctx, external_authority)
    transition_authority: dict[str, Any] = {
        "kind": "NONE",
        "validity": "NONE",
        "request_match": {},
    }
    transition_sequence: Mapping[str, Any] = {}
    transition_kind = "NONE"
    transition_authorization_field = ""
    transition_receipt_field = ""
    if not aws_sequence_conflict and deployment_status == "ACTION_TERMINAL_REQUIRED":
        transition_authority = derive_external_authority(
            ctx,
            envelope,
            lane,
            gate_b_authorization,
            cost_posture=str(project.get("cost_posture", "")),
            aws_progress_state=aws_progress_state,
            active_artifact=active_artifact,
            aws_action_phase="AWS-20",
            teardown_review=teardown_sequence_projection,
            deployment_sequence={},
            preflight=(
                aws_execution_projection.get("preflight")
                if isinstance(aws_execution_projection.get("preflight"), Mapping)
                else None
            ),
        )
        transition_sequence = deployment_sequence_projection
        transition_kind = clean_cell(transition_authority.get("kind", ""))
        transition_authorization_field = "deployment_authorization"
        transition_receipt_field = "deployment_receipt_digest"
    elif not aws_sequence_conflict and teardown_status == "ACTION_TERMINAL_REQUIRED":
        transition_review = {
            **teardown_sequence_projection,
            "status": "READY_FOR_TEARDOWN",
            "evidence_id": teardown_sequence_projection.get(
                "ready_evidence_id", "NONE"
            ),
        }
        transition_authority = derive_external_authority(
            ctx,
            envelope,
            lane,
            gate_b_authorization,
            cost_posture=str(project.get("cost_posture", "")),
            aws_progress_state=aws_progress_state,
            active_artifact=active_artifact,
            aws_action_phase="AWS-50",
            teardown_review=transition_review,
            deployment_sequence=deployment_sequence_projection,
            preflight=(
                aws_execution_projection.get("preflight")
                if isinstance(aws_execution_projection.get("preflight"), Mapping)
                else None
            ),
        )
        transition_sequence = teardown_sequence_projection
        transition_kind = "AWS_TEARDOWN"
        transition_authorization_field = "teardown_authorization"
        transition_receipt_field = "teardown_receipt_digest"
    transition_request_match = (
        derive_request_match(ctx, transition_authority)
        if transition_kind != "NONE"
        else None
    )
    aws_action_transition = _aws_action_transition_projection(
        transition_request_match,
        transition_sequence,
        authority_kind=transition_kind,
        authorization_field=transition_authorization_field,
        receipt_digest_field=transition_receipt_field,
    )
    (
        owner_decision_brief, owner_decision_inventory, owner_brief_issues
    ) = derive_owner_decision_brief(
        ctx.texts.get(PRD_FILE, ""),
        prd_fields,
        intake_contract,
        requirements_contract,
        design_contract,
        envelope,
        has_errors=ctx.has_errors,
        enabled=classification not in {"TEMPLATE_SOURCE", "UNCONFIGURED_TEMPLATE"},
    )
    for code, message in owner_brief_issues:
        if code == "OWNER_BRIEF_SOURCE_STALE":
            ctx.warning(code, message, PRD_FILE)
        else:
            ctx.error(code, message, PRD_FILE)
    owner_answer_confirmation = derive_owner_answer_confirmation(
        ctx.texts.get(PRD_FILE, ""), intake_contract
    )
    diagnostic_codes = [item.code for item in ctx.diagnostics]
    aws_mutation_authority_ready = external_authority.get(
        "validity"
    ) == "CURRENT" and external_authority.get("kind") in {
        "AWS_DEPLOYMENT",
        "AWS_TEARDOWN",
        "FAST_DEV_GATE_B",
    }
    remediation = derive_remediation(
        ctx,
        classification=classification,
        gate_a=gate_a,
        gate_b=gate_b,
        envelope=envelope,
        tasks=tasks,
        requirements_revision=prd_fields.get("requirements_revision"),
        design_revision=prd_fields.get("design_revision"),
        owner_stage_hint=resolved_owner_stage,
    )
    interaction = derive_interaction(
        lifecycle_state,
        next_prompt,
        has_errors=ctx.has_errors,
        diagnostic_codes=diagnostic_codes,
        design_aws_core_ready=design_aws_core_ready,
        aws_execution_planning_ready=aws_execution_planning_ready,
        remediation=remediation,
        owner_stage_hint=resolved_owner_stage,
        aws_progress_state=aws_progress_state,
        aws_mutation_authority_ready=aws_mutation_authority_ready,
        aws_lane=lane,
        aws_read_authority_required=(
            external_authority.get("kind") == "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
        ),
        req_aws_core_materiality=req_aws_core_materiality,
        req_aws_core_ready=req_aws_core_ready,
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
        next_prompt=next_prompt,
        restricted_deployment_closure=deployment_authority_restricted,
        restricted_teardown_closure=teardown_authority_restricted,
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
        deployment_journal_closure_authority = (
            derive_deployment_journal_closure_authority(
                deployment_sequence_projection,
                next_prompt,
                restricted_closure=False,
            )
        )
        teardown_journal_closure_authority = derive_teardown_journal_closure_authority(
            teardown_sequence_projection,
            next_prompt,
            restricted_closure=False,
        )
        external_authority = derive_external_authority(
            ctx,
            envelope,
            lane,
            "NONE",
            cost_posture=str(project.get("cost_posture", "")),
            aws_progress_state=aws_progress_state,
            active_artifact=active_artifact,
            aws_action_phase=next_prompt,
            teardown_review=teardown_sequence_projection,
            deployment_sequence=deployment_sequence_projection,
            preflight=(
                aws_execution_projection.get("preflight")
                if isinstance(aws_execution_projection.get("preflight"), Mapping)
                else None
            ),
        )
        external_authority["request_match"] = derive_request_match(
            ctx, external_authority
        )
        aws_lifecycle_intent_write_authority = (
            derive_aws_lifecycle_intent_write_authority(
                ctx,
                tasks,
                release_decision,
                deployment_sequence_projection,
                teardown_sequence_projection,
                external_authority,
                lifecycle_intent=lifecycle_intent_projection,
            )
        )
        (
            owner_decision_brief, owner_decision_inventory, _owner_brief_issues
        ) = derive_owner_decision_brief(
            ctx.texts.get(PRD_FILE, ""),
            prd_fields,
            intake_contract,
            requirements_contract,
            design_contract,
            envelope,
            has_errors=ctx.has_errors,
            enabled=classification not in {"TEMPLATE_SOURCE", "UNCONFIGURED_TEMPLATE"},
        )
        diagnostic_codes = [item.code for item in ctx.diagnostics]
        remediation = derive_remediation(
            ctx,
            classification=classification,
            gate_a=gate_a,
            gate_b=gate_b,
            envelope=envelope,
            tasks=tasks,
            requirements_revision=prd_fields.get("requirements_revision"),
            design_revision=prd_fields.get("design_revision"),
            owner_stage_hint=resolved_owner_stage,
        )
        interaction = derive_interaction(
            lifecycle_state,
            next_prompt,
            has_errors=True,
            diagnostic_codes=diagnostic_codes,
            design_aws_core_ready=design_aws_core_ready,
            aws_execution_planning_ready=aws_execution_planning_ready,
            remediation=remediation,
            owner_stage_hint=resolved_owner_stage,
            aws_progress_state=aws_progress_state,
            aws_mutation_authority_ready=False,
            aws_lane=lane,
            aws_read_authority_required=False,
            req_aws_core_materiality=req_aws_core_materiality,
            req_aws_core_ready=req_aws_core_ready,
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
            next_prompt=next_prompt,
            restricted_deployment_closure=False,
            restricted_teardown_closure=False,
            source_texts=ctx.texts,
        )
        context_plan.pop("_resolution_issues", None)
    summary_sources: dict[str, str] = {}
    for summary_path in DOCUMENT_SUMMARY_FILES:
        summary_text = ctx.presentation_texts.get(summary_path)
        if summary_text is None:
            safe_read_text(ctx, summary_path)
            summary_text = ctx.presentation_texts.get(summary_path)
        if summary_text is not None:
            summary_sources[summary_path] = summary_text
    # fmt: off
    summary_specifications = derive_document_summary_specifications(ctx, classification=classification, lifecycle_state=lifecycle_state, next_prompt=next_prompt, project=project, prd_fields=prd_fields, gate_a=gate_a, gate_b=gate_b, tasks=tasks, release_decision=release_decision, release_evidence_cutoff=release_evidence_cutoff, aws_authorization=aws_authorization, external_authority=external_authority, interaction=interaction, active_artifact=active_artifact, deployment_sequence=deployment_sequence_projection)
    # fmt: on
    document_summaries, summary_issues = project_document_summaries(
        summary_sources, summary_specifications
    )
    brief_was_ready = owner_decision_brief.get("status") == "READY"
    for issue in summary_issues:
        reporter = (
            ctx.warning
            if issue["code"] == "DOCUMENT_SUMMARY_STALE" and not brief_was_ready
            else ctx.error
        )
        reporter(
            str(issue["code"]),
            str(issue["message"]),
            str(issue["path"]),
        )
    if summary_issues and brief_was_ready:
        blocked_brief = dict(owner_decision_brief)
        blocked_brief["status"] = "BLOCKED"
        blocked_brief["formal_receipt_required"] = False
        owner_decision_brief, _ = finalize_owner_decision_brief(blocked_brief)
    if any(
        issue["code"] != "DOCUMENT_SUMMARY_STALE" or brief_was_ready
        for issue in summary_issues
    ):
        status = "BLOCKED"
        diagnostic_codes = [item.code for item in ctx.diagnostics]
        remediation = derive_remediation(
            ctx,
            classification=classification,
            gate_a=gate_a,
            gate_b=gate_b,
            envelope=envelope,
            tasks=tasks,
            requirements_revision=prd_fields.get("requirements_revision"),
            design_revision=prd_fields.get("design_revision"),
            owner_stage_hint=resolved_owner_stage,
        )
        interaction = derive_interaction(
            lifecycle_state,
            next_prompt,
            has_errors=True,
            diagnostic_codes=diagnostic_codes,
            design_aws_core_ready=design_aws_core_ready,
            aws_execution_planning_ready=aws_execution_planning_ready,
            remediation=remediation,
            owner_stage_hint=resolved_owner_stage,
            aws_progress_state=aws_progress_state,
            aws_mutation_authority_ready=aws_mutation_authority_ready,
            aws_lane=lane,
            aws_read_authority_required=(
                external_authority.get("kind")
                == "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
            ),
            req_aws_core_materiality=req_aws_core_materiality,
            req_aws_core_ready=req_aws_core_ready,
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
            next_prompt=next_prompt,
            restricted_deployment_closure=deployment_authority_restricted,
            restricted_teardown_closure=teardown_authority_restricted,
            source_texts=ctx.texts,
        )
        context_plan.pop("_resolution_issues", None)

    aws_mode_boundary = derive_aws_mode_boundary(
        lane,
        envelope,
        next_prompt,
        external_authority,
    )
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
        "aws_mode_boundary": aws_mode_boundary,
        "gates": {
            "gate_a": gate_a,
            "gate_b": gate_b,
        },
        "evidence_state": release_decision,
        "release_evidence_cutoff": release_evidence_cutoff,
        "aws_core_evidence": {
            "aws_execution_planning": (
                "READY" if aws_execution_planning_ready else "BLOCKED"
            ),
            "observed_usage": dict(aws_core_usage or {}),
        },
        "authorizations": {
            "construction": construction_authorization,
            "aws": aws_authorization,
        },
        "write_authority": write_authority,
        "deployment_journal_closure_authority": (deployment_journal_closure_authority),
        "teardown_journal_closure_authority": (teardown_journal_closure_authority),
        "aws_lifecycle_intent": lifecycle_intent_projection,
        "aws_residual_disposition": residual_disposition_projection,
        "aws_lifecycle_intent_write_authority": aws_lifecycle_intent_write_authority,
        "external_authority": external_authority,
        "hook_constraints": {
            "GitHub boundary": envelope.get("GitHub boundary", "NONE"),
            "GitHub repository, branch, and merge constraints": envelope.get(
                "GitHub repository, branch, and merge constraints", "NONE"
            ),
        },
        "aws_action_transition": aws_action_transition,
        "aws_execution": aws_execution_projection,
        "aws_deployment": deployment_sequence_projection,
        "aws_teardown": teardown_sequence_projection,
        "basis": {
            "requirements_revision": prd_fields.get("requirements_revision"),
            "design_revision": prd_fields.get("design_revision"),
            "construction_authorization": prd_fields.get("construction_authorization"),
            "prd_snapshot_sha256": (
                "sha256:"
                + hashlib.sha256(
                    canonical_bytes_without_generated_summary(
                        ctx.presentation_texts[PRD_FILE]
                    )
                ).hexdigest()
                if PRD_FILE in ctx.presentation_texts
                else "NONE"
            ),
        },
        "document_summaries": document_summaries,
        "owner_decision_brief": owner_decision_brief,
        "owner_decision_inventory": owner_decision_inventory,
        "owner_answer_confirmation": owner_answer_confirmation,
        "intake_foundation": intake_contract.to_dict(),
        "requirements_contract": requirements_contract.to_dict(),
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
            "requirement_coverage_complete": tasks.requirement_coverage_complete,
            "requirement_coverage": [
                tasks.requirement_coverage[requirement_id]
                for requirement_id in sorted(tasks.requirement_coverage)
            ],
            "missing_requirement_ids": tasks.missing_requirement_ids,
        },
        "diagnostics": [
            item.to_dict(f"DGN-{index:04d}")
            for index, item in enumerate(ctx.diagnostics, start=1)
        ],
    }


def print_human(report: dict[str, Any]) -> None:
    status = "PASS" if report["ok"] else "BLOCKED"
    basis = report["basis"]
    print(f"AWS Codex Fastlane Engine: {status}")
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


def _parse_current_intake_response(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    report = inspect_project(args.root, template_source=args.template_source)
    if not report["ok"]:
        return {
            "schema_version": 1,
            "status": "FAIL",
            "errors": [
                {
                    "code": "INTAKE_PROJECT_INVALID",
                    "message": "Project must pass the Fastlane Engine before an intake response can be parsed",
                }
            ],
        }, 1
    pending_card = report["intake_foundation"].get("pending_card")
    if not isinstance(pending_card, dict):
        return {
            "schema_version": 1,
            "status": "FAIL",
            "errors": [
                {
                    "code": "INTAKE_CARD_INVALID",
                    "message": "Project has no valid pending intake card",
                }
            ],
        }, 1
    try:
        basis = report.get("basis")
        if not isinstance(basis, Mapping):
            raise ValueError("Current project basis is missing")
        text, _ = bounded_prd_snapshot(
            args.root, clean_cell(basis.get("prd_snapshot_sha256", ""))
        )
        response_table = contract_table_after_heading(
            text, INTAKE_RESPONSE_REGISTER_HEADING, INTAKE_RESPONSE_REGISTER_HEADERS
        )
        if response_table is None:
            raise ValueError("Normalized owner response register is missing")
        register_issues: list[tuple[str, str]] = []
        responses = _parse_intake_response_register(
            response_table, dict(INTAKE_FOUNDATION_FIELDS), register_issues
        )
        if register_issues:
            raise ValueError("Normalized owner response register is invalid")
    except (OSError, UnicodeError, ValueError):
        return {
            "schema_version": 1,
            "status": "FAIL",
            "errors": [
                {
                    "code": "INTAKE_PROJECT_INVALID",
                    "message": "Current intake contract cannot be parsed safely",
                }
            ],
        }, 1
    numbers = [
        int(response.owner_response_id.rsplit("-", 1)[1]) for response in responses
    ]
    result = parse_intake_owner_response(
        sys.stdin.read(MAX_RESPONSE_CHARACTERS + 1),
        pending_card,
        expected_card_id=args.presented_card_id,
        expected_revision=args.presented_card_revision,
        expected_sha256=args.presented_card_sha256,
        owner_response_id=f"OWNER-MSG-{max(numbers, default=0) + 1:04d}",
    )
    return result.to_dict(), 0 if result.status == "PASS" else 2


def _validate_current_gate_receipt(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    """Validate a pending Gate A/B candidate without changing project files."""

    report = inspect_project(args.root, template_source=args.template_source)
    if not report["ok"]:
        return {
            "schema_version": 1,
            "status": "FAIL",
            "candidate_accepted": False,
            "project_state_changed": False,
            "errors": [
                {
                    "code": "GATE_RECEIPT_PROJECT_INVALID",
                    "message": (
                        "Project must pass the Fastlane Engine before a gate "
                        "receipt can be validated"
                    ),
                }
            ],
        }, 1
    try:
        contract = current_gate_receipt_contract(args.root, report)
    except ValueError:
        return {
            "schema_version": 1,
            "status": "FAIL",
            "candidate_accepted": False,
            "project_state_changed": False,
            "lifecycle_state": report.get("lifecycle_state", "BLOCKED"),
            "next_prompt": report.get("next_prompt", "STOP"),
            "errors": [
                {
                    "code": "GATE_RECEIPT_NOT_PENDING",
                    "message": "The project is not waiting for an owner gate receipt",
                }
            ],
        }, 1
    candidate = sys.stdin.read(MAX_GATE_RECEIPT_CHARACTERS + 1)
    result = validate_gate_receipt_candidate(candidate, contract)
    return result, 0 if result["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    configure_utf8_standard_streams()
    parser = argparse.ArgumentParser(description="Read-only AWS Codex Fastlane Engine")
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
    parser.add_argument(
        "--prior-remediation-fingerprint",
        help="Prior sha256 remediation fingerprint for one bounded retry",
    )
    parser.add_argument("--parse-intake-response", action="store_true")
    parser.add_argument("--parse-gate-correction", action="store_true")
    parser.add_argument("--validate-gate-receipt", action="store_true")
    parser.add_argument("--input-stdin", action="store_true")
    parser.add_argument("--presented-card-id")
    parser.add_argument("--presented-card-revision", type=int)
    parser.add_argument("--presented-card-sha256")
    args = parser.parse_args(argv)
    if (
        args.prior_remediation_fingerprint is not None
        and re.fullmatch(r"sha256:[0-9a-f]{64}", args.prior_remediation_fingerprint)
        is None
    ):
        parser.error(
            "--prior-remediation-fingerprint must be sha256:<64 lowercase hex>"
        )
    owner_input_modes = sum(
        (
            args.parse_intake_response,
            args.parse_gate_correction,
            args.validate_gate_receipt,
        )
    )
    if owner_input_modes > 1:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "FAIL",
                    "errors": [
                        {
                            "code": "OWNER_INPUT_USAGE",
                            "message": "Select exactly one owner-input parser mode",
                        }
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    if args.parse_gate_correction:
        if not args.input_stdin or not args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "FAIL",
                        "errors": [
                            {
                                "code": "GATE_CORRECTION_USAGE",
                                "message": "Gate correction parsing requires stdin and JSON",
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        candidate = sys.stdin.read(MAX_RESPONSE_CHARACTERS + 1)
        result = parse_gate_correction(candidate).to_dict()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 2
    if args.parse_intake_response:
        if (
            not args.input_stdin
            or not args.json
            or args.presented_card_id is None
            or args.presented_card_revision is None
            or args.presented_card_sha256 is None
        ):
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "FAIL",
                        "errors": [
                            {
                                "code": "INTAKE_PARSE_USAGE",
                                "message": "Parsing requires stdin, JSON, and the presented card ID, revision, and digest",
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        result, exit_code = _parse_current_intake_response(args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return exit_code
    if args.validate_gate_receipt:
        if not args.input_stdin or not args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "FAIL",
                        "errors": [
                            {
                                "code": "GATE_RECEIPT_USAGE",
                                "message": (
                                    "Gate receipt validation requires stdin and JSON"
                                ),
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        result, exit_code = _validate_current_gate_receipt(args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return exit_code
    report = inspect_project(
        args.root,
        template_source=args.template_source,
        prior_remediation_fingerprint=args.prior_remediation_fingerprint,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
