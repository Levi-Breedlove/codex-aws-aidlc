"""Bounded project observation and compatibility-level project vocabulary.

Canonical inputs are repository-relative package files and immutable project text.
The module returns bounded observations and normalized compatibility values. It
performs read-only filesystem observation only; it never writes, routes, approves,
or authorizes GitHub or AWS actions. Fastlane 1.2.16 public names remain stable.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

from .aws import (
    AwsCoreEvidenceRow,
    aws_core_evidence_diagnostic_code,
    aws_core_phase_evidence_issues,
)
from .core.diagnostics import Diagnostic, DiagnosticCollector
from .core.contracts import table_after_heading
from .core.ids import (
    canonical_id_list,
    clean_cell,
    explicit_value,
)
from .core.snapshot import (
    GitObserver,
    GitObservationError,  # noqa: F401 - stable compatibility re-export
    GitQueryKey,
    GitQueryResult,
    ObservationError,
    ProjectSnapshot,
    SnapshotObserver,
    git_read,  # noqa: F401 - stable compatibility re-export
    inspect_git_baseline,  # noqa: F401 - stable compatibility re-export
)
from .define.models import (
    AssumptionLifecycleRecord,
    ChangeImpactRow,
    CoverageOmission,
    IntakeCard,
    IntakeQuestion,
    NormalizedOwnerResponse,
    RequirementsChangeLineage,
)
from .define.requirements import (
    concrete_requirement_subject,
    measurable_acceptance_is_bound,
    observable_requirement_response,
    quality_attribute_scenario_issues,
    requirement_method_issues,
)
from .design import parse_future_expiry_at
from .design.adr import ADR_DIRECTORY, MAX_ADR_BYTES, MAX_ADR_FILES
from .deliver import parse_checkpoint_git_receipt
from .package.manifest import ManifestPolicy
from .package.state import StatePolicy

try:
    from fastlane_context import SourceSpan
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_context import SourceSpan

try:
    from fastlane_contracts import without_fenced_code
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_contracts import without_fenced_code

try:
    from fastlane_document_summaries import (
        canonical_bytes_without_generated_summary,
        strip_generated_summary,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_document_summaries import (
        canonical_bytes_without_generated_summary,
        strip_generated_summary,
    )


try:
    from fastlane_project_identity import PROJECT_NAME_TOKEN
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.fastlane_project_identity import PROJECT_NAME_TOKEN

try:
    from intake_response import (
        intake_detail_safety_code,
        intake_reply_token,
    )
except ModuleNotFoundError:  # Loaded as scripts.bootstrap_doctor in unit tests.
    from scripts.intake_response import (
        intake_detail_safety_code,
        intake_reply_token,
    )


# COMPATIBILITY: Internal callers retain the historical private helper name.
_canonical_id_list = canonical_id_list

# COMPATIBILITY: These names remain importable from the stable doctor facade
# while new callers use ``fastlane_engine.api`` or the owning Define module.
_DEFINE_COMPATIBILITY_EXPORTS = (
    AssumptionLifecycleRecord,
    ChangeImpactRow,
    CoverageOmission,
    IntakeCard,
    IntakeQuestion,
    NormalizedOwnerResponse,
    RequirementsChangeLineage,
    concrete_requirement_subject,
    intake_detail_safety_code,
    intake_reply_token,
    measurable_acceptance_is_bound,
    observable_requirement_response,
    quality_attribute_scenario_issues,
    requirement_method_issues,
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
ENGINE_RUNTIME_CONTROL_FILES = {
    "scripts/fastlane_engine/__init__.py",
    "scripts/fastlane_engine/api.py",
    "scripts/fastlane_engine/authority/__init__.py",
    "scripts/fastlane_engine/authority/aws.py",
    "scripts/fastlane_engine/authority/closure.py",
    "scripts/fastlane_engine/authority/github.py",
    "scripts/fastlane_engine/authority/models.py",
    "scripts/fastlane_engine/authority/receipts.py",
    "scripts/fastlane_engine/authority/write.py",
    "scripts/fastlane_engine/aws/__init__.py",
    "scripts/fastlane_engine/aws/deployment.py",
    "scripts/fastlane_engine/aws/evidence.py",
    "scripts/fastlane_engine/aws/lifecycle.py",
    "scripts/fastlane_engine/aws/models.py",
    "scripts/fastlane_engine/aws/preflight.py",
    "scripts/fastlane_engine/aws/teardown.py",
    "scripts/fastlane_engine/composition.py",
    "scripts/fastlane_engine/core/__init__.py",
    "scripts/fastlane_engine/core/contracts.py",
    "scripts/fastlane_engine/core/diagnostics.py",
    "scripts/fastlane_engine/core/digests.py",
    "scripts/fastlane_engine/core/ids.py",
    "scripts/fastlane_engine/core/markdown_index.py",
    "scripts/fastlane_engine/core/snapshot.py",
    "scripts/fastlane_engine/define/__init__.py",
    "scripts/fastlane_engine/define/coverage.py",
    "scripts/fastlane_engine/define/intake.py",
    "scripts/fastlane_engine/define/models.py",
    "scripts/fastlane_engine/define/project.py",
    "scripts/fastlane_engine/define/requirements.py",
    "scripts/fastlane_engine/define/source_assist.py",
    "scripts/fastlane_engine/design/__init__.py",
    "scripts/fastlane_engine/design/adr.py",
    "scripts/fastlane_engine/design/architecture.py",
    "scripts/fastlane_engine/design/architecture_board.py",
    "scripts/fastlane_engine/design/architecture_board_validation.py",
    "scripts/fastlane_engine/design/diagrams.py",
    "scripts/fastlane_engine/design/envelope.py",
    "scripts/fastlane_engine/design/harness.py",
    "scripts/fastlane_engine/design/models.py",
    "scripts/fastlane_engine/design/project.py",
    "scripts/fastlane_engine/design/source.py",
    "scripts/fastlane_engine/design/support.py",
    "scripts/fastlane_engine/deliver/__init__.py",
    "scripts/fastlane_engine/deliver/evidence.py",
    "scripts/fastlane_engine/deliver/models.py",
    "scripts/fastlane_engine/deliver/release.py",
    "scripts/fastlane_engine/deliver/repository.py",
    "scripts/fastlane_engine/deliver/tasks.py",
    "scripts/fastlane_engine/doctor_compat.py",
    "scripts/fastlane_engine/evaluation.py",
    "scripts/fastlane_engine/orchestration.py",
    "scripts/fastlane_engine/owner_decisions.py",
    "scripts/fastlane_engine/package/__init__.py",
    "scripts/fastlane_engine/package/manifest.py",
    "scripts/fastlane_engine/package/state.py",
    "scripts/fastlane_engine/project_delivery.py",
    "scripts/fastlane_engine/project_inspection.py",
    "scripts/fastlane_engine/project_validation.py",
    "scripts/fastlane_engine/remediation.py",
    "scripts/fastlane_engine/report.py",
    "scripts/fastlane_engine/routing.py",
}
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
STABLE_CONTRACT_ID = re.compile(r"[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
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
STATE_MODEL_TRIGGERS = (
    "LIFECYCLE_RESOURCE",
    "ASYNCHRONOUS_WORK",
    "RETRY_OR_RESUME",
    "APPROVAL_FLOW",
    "MIGRATION_OR_CUTOVER",
    "OTHER_MEANINGFUL_TRANSITION",
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
PROPERTY_TEST_RESULTS = {"NOT_STARTED", "PASS", "FAIL"}
PROPERTY_TEST_FAILURE_CLASSES = {
    "IMPLEMENTATION_DEFECT",
    "SPECIFICATION_AMBIGUITY_OR_DEFECT",
    "GENERATOR_OR_ORACLE_DEFECT",
    "ENVIRONMENT_DEFECT",
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
MANDATORY_REQUIRED_FILES = (
    {
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
        "infrastructure/README.md",
        "prompts/CODEX-PROMPTS.md",
        "scripts/bootstrap_doctor.py",
        "scripts/fastlane_adr.py",
        "scripts/fastlane_contracts.py",
        "scripts/fastlane_owner_briefs.py",
        "scripts/bootstrap_dependencies.py",
        "scripts/setup_assistant.py",
        "scripts/task_waves.py",
        "tests/AGENTS.md",
    }
    | ENGINE_RUNTIME_CONTROL_FILES
    | {"scripts/fastlane_engine/AGENTS.md"}
)


@dataclass
class Context:
    root: Path
    template_source: bool = False
    observed_snapshot: ProjectSnapshot | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    presentation_texts: dict[str, str] = field(default_factory=dict)
    source_file_bytes: dict[str, bytes] = field(default_factory=dict)
    source_bytes_read: int = 0
    manifest_document: dict[str, Any] = field(default_factory=dict)
    bootstrap_state_document: dict[str, Any] = field(default_factory=dict)
    prior_remediation_fingerprint: str | None = None
    _observer: SnapshotObserver = field(init=False, repr=False)
    _diagnostic_collector: DiagnosticCollector = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        if (
            self.observed_snapshot is not None
            and self.observed_snapshot.root != self.root
        ):
            raise ValueError("ProjectSnapshot root does not match Context root")
        self._diagnostic_collector = DiagnosticCollector(backing=self.diagnostics)
        self._observer = SnapshotObserver(
            self.root,
            observed_at=(
                self.observed_snapshot.observed_at
                if self.observed_snapshot is not None
                else None
            ),
            canonicalize_text=lambda relative, text: (
                strip_generated_summary(text)
                if relative in DOCUMENT_SUMMARY_FILES
                else text
            ),
            max_files=MAX_REQUIRED_FILES,
            max_file_bytes=MAX_REQUIRED_FILE_BYTES,
            max_source_bytes=MAX_PROJECT_SOURCE_BYTES,
        )

    def error(self, code: str, message: str, path: str | None = None) -> None:
        self._diagnostic_collector.error(code, message, path)

    def warning(self, code: str, message: str, path: str | None = None) -> None:
        self._diagnostic_collector.warning(code, message, path)

    @property
    def has_errors(self) -> bool:
        return self._diagnostic_collector.has_errors

    @property
    def snapshot(self) -> ProjectSnapshot:
        """Freeze the files and Markdown indexes observed by this invocation."""

        if self.observed_snapshot is not None:
            return self.observed_snapshot

        project = self.bootstrap_state_document.get("project", {})
        project_identity = (
            {key: str(project[key]) for key in ("name", "region") if key in project}
            if isinstance(project, dict)
            else {}
        )
        return self._observer.freeze(
            project_identity=project_identity,
            bootstrap_state=self.bootstrap_state_document,
            manifest=self.manifest_document,
        )

    @property
    def observed_at(self) -> datetime:
        """Return the one invocation clock captured by the snapshot boundary."""

        return self.snapshot.observed_at

    def git_result(self, *arguments: str) -> GitQueryResult:
        """Return a captured Git fact, never running Git during normal evaluation."""

        if self.observed_snapshot is not None:
            return self.observed_snapshot.git.result(*arguments)
        completed = git_read(self.root, *arguments)
        return GitQueryResult(
            key=GitQueryKey.from_arguments(tuple(arguments)),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def git_baseline(self) -> str:
        """Return the captured HEAD or the historical PENDING sentinel."""

        if self.observed_snapshot is not None:
            return self.observed_snapshot.git.head_sha or "PENDING"
        return inspect_git_baseline(self.root)


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
    "scripts/fastlane_adr.py",
    "scripts/fastlane_contracts.py",
    "scripts/fastlane_process.py",
    "scripts/fastlane_project_identity.py",
    "scripts/fastlane_stdio.py",
    "scripts/setup_assistant.py",
    "scripts/task_waves.py",
} | ENGINE_RUNTIME_CONTROL_FILES
COORDINATOR_LEDGER_PATHS = {TASKS_FILE, VERIFY_FILE, STATE_FILE}
ID_LIKE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*-\d+\b")
GITHUB_ISSUE_URL = re.compile(
    r"https://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/[1-9]\d*"
)
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
AWS_CORE_MATERIALITY_VALUES = {"REQUIRED", "OPTIONAL", "NOT_MATERIAL"}
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
    """SAFETY: translate pure AWS Core gaps into current diagnostics."""

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


def explicit_human_approver(value: str) -> bool:
    """Require an explicit owner identity that is not an agent or automation."""

    cleaned = clean_cell(value)
    return explicit_value(cleaned) and NON_HUMAN_APPROVER.search(cleaned) is None


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


MAX_REQUIRED_FILES = 512
MAX_REQUIRED_FILE_BYTES = 16 * 1024 * 1024
MAX_PROJECT_SOURCE_BYTES = 64 * 1024 * 1024
BINARY_REQUIRED_SUFFIXES = frozenset({".png"})
# SAFETY: distributed verification sources are package-integrity inputs, not
# lifecycle text. Keep their bytes hash-bound without retaining decoded copies
# in every normal ProjectSnapshot. The scoped tests/AGENTS.md guide remains a
# text input because context planning may select it during construction work.
_BINARY_REQUIRED_PREFIXES = (
    "tests/engine_",
    "tests/fixtures/",
    "tests/test_",
)

MANIFEST_POLICY = ManifestPolicy(
    manifest_file=MANIFEST_FILE,
    prompt_file=PROMPT_FILE,
    mandatory_required_files=frozenset(MANDATORY_REQUIRED_FILES),
    control_hash_files=frozenset(CONTROL_HASH_FILES),
    canonical_placeholders=frozenset(CANONICAL_PLACEHOLDERS),
    max_required_files=MAX_REQUIRED_FILES,
    binary_required_suffixes=BINARY_REQUIRED_SUFFIXES,
    binary_required_prefixes=_BINARY_REQUIRED_PREFIXES,
)

STATE_POLICY = StatePolicy(
    state_file=STATE_FILE,
    project_name_token=PROJECT_NAME_TOKEN,
    setup_status_token="{{SETUP_STATUS}}",
    setup_method_token="{{SETUP_METHOD}}",
    aws_region_token="{{AWS_REGION}}",
    cost_posture_token="{{COST_POSTURE}}",
    project_modes=frozenset(PROJECT_MODES),
    delivery_profiles=frozenset(DELIVERY_PROFILES),
    risk_levels=frozenset(RISK_LEVELS),
    aws_lanes=frozenset(AWS_LANES),
    brownfield_states=frozenset(BROWNFIELD_STATES),
    gate_a_states=frozenset(GATE_A_STATES),
    gate_b_states=frozenset(GATE_B_STATES),
    run_modes=frozenset(RUN_MODES),
    run_states=frozenset(RUN_STATES),
    req_id=REQ_ID,
    des_id=DES_ID,
    auth_id=AUTH_ID,
    plan_id=PLAN_ID,
    task_id=TASK_ID,
    run_id=RUN_ID,
    checkpoint_id=CHECKPOINT_ID,
)


_SNAPSHOT_PRIMARY_TEXT_PATHS = (
    MANIFEST_FILE,
    STATE_FILE,
    PROMPT_FILE,
    PROJECT_README_FILE,
    PRD_FILE,
    TASKS_FILE,
    VERIFY_FILE,
    RUNBOOK_FILE,
    BUGFIX_FILE,
)


def capture_engine_snapshot(
    root: Path,
    *,
    observed_at: datetime | None = None,
) -> ProjectSnapshot:
    """SAFETY: complete bounded observation before lifecycle evaluation."""

    observer = SnapshotObserver(
        root,
        observed_at=observed_at,
        canonicalize_text=lambda relative, text: (
            strip_generated_summary(text)
            if relative in DOCUMENT_SUMMARY_FILES
            else text
        ),
        max_files=MAX_REQUIRED_FILES + MAX_ADR_FILES,
        max_file_bytes=MAX_REQUIRED_FILE_BYTES,
        max_source_bytes=MAX_PROJECT_SOURCE_BYTES,
    )
    observer.capture_text(MANIFEST_FILE)
    observer.capture_text(STATE_FILE)
    manifest = _captured_json(observer, MANIFEST_FILE)
    state = _captured_json(observer, STATE_FILE)
    requested: list[str] = [
        *_SNAPSHOT_PRIMARY_TEXT_PATHS,
        *sorted(MANDATORY_REQUIRED_FILES),
    ]
    required_files = manifest.get("required_files")
    if isinstance(required_files, list):
        requested.extend(
            item
            for item in required_files[:MAX_REQUIRED_FILES]
            if isinstance(item, str)
        )
    seen: set[str] = set()
    for relative in requested:
        if relative in seen:
            continue
        seen.add(relative)
        if MANIFEST_POLICY.requires_binary_observation(relative):
            observer.capture_binary(relative)
        else:
            observer.capture_text(relative)

    adr_directory = observer.observe_directory(
        ADR_DIRECTORY, maximum_entries=MAX_ADR_FILES + 2
    )
    adr_entries = tuple(
        entry for entry in adr_directory.entries if entry.name != "0000-template.md"
    )
    if len(adr_entries) <= MAX_ADR_FILES:
        for entry in adr_entries:
            if entry.is_file and entry.byte_size <= MAX_ADR_BYTES:
                observer.capture_text(entry.path)

    git_observer = GitObserver(root)
    git_observer.observe_repository_state()
    queries, baseline_sha, protected_paths = _planned_git_queries(observer, state)
    for arguments in queries:
        git_observer.query(*arguments)
    git_snapshot = git_observer.freeze(
        baseline_sha=baseline_sha,
        protected_dirty_paths=protected_paths,
    )
    project = state.get("project")
    identity = (
        {key: str(project[key]) for key in ("name", "region") if key in project}
        if isinstance(project, dict)
        else {}
    )
    return observer.freeze(
        project_identity=identity,
        git=git_snapshot,
        bootstrap_state=state,
        manifest=manifest,
    )


def _captured_json(observer: SnapshotObserver, relative: str) -> dict[str, Any]:
    captured = observer.file(relative)
    if captured is None or captured.canonical_text is None:
        return {}
    try:
        value = json.loads(captured.canonical_text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _planned_git_queries(
    observer: SnapshotObserver,
    state: dict[str, Any],
) -> tuple[list[tuple[str, ...]], str | None, tuple[str, ...]]:
    """SAFETY: derive only the canonical Git facts required by current records."""

    prd = observer.file(PRD_FILE)
    tasks = observer.file(TASKS_FILE)
    prd_text = prd.canonical_text if prd and prd.canonical_text else ""
    tasks_text = tasks.canonical_text if tasks and tasks.canonical_text else ""
    try:
        envelope = table_after_heading(prd_text, "## 28. Construction envelope")
    except ValueError:
        envelope = {}
    try:
        document = table_after_heading(prd_text, "## Document status")
    except ValueError:
        document = {}
    try:
        task_snapshot = table_after_heading(tasks_text, "## Active execution snapshot")
    except ValueError:
        task_snapshot = {}

    full_commit = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
    queries: list[tuple[str, ...]] = []
    envelope_baseline = clean_cell(envelope.get("Authorized baseline commit", ""))
    if full_commit.fullmatch(envelope_baseline):
        queries.append(("rev-parse", "--verify", f"{envelope_baseline}^{{commit}}"))

    task_baseline = clean_cell(task_snapshot.get("Baseline commit", ""))
    known_green = clean_cell(task_snapshot.get("Last known-green commit", ""))
    has_task_records = TASK_HEADER_PATTERN.search(tasks_text) is not None
    construction_active = (
        clean_cell(document.get("Gate B derived status", ""))
        == "APPROVED_FOR_CONSTRUCTION"
        or has_task_records
    )
    baseline_sha = (
        task_baseline
        if full_commit.fullmatch(task_baseline)
        else (envelope_baseline if full_commit.fullmatch(envelope_baseline) else None)
    )
    execution = state.get("execution")
    execution_state = (
        clean_cell(execution.get("state", "")) if isinstance(execution, dict) else ""
    )
    reconcile = execution_state in {"CHECKPOINTED", "BLOCKED", "COMPLETE"}
    if (
        construction_active
        and full_commit.fullmatch(task_baseline)
        and full_commit.fullmatch(known_green)
    ):
        queries.extend(
            (
                ("rev-parse", "--verify", f"{task_baseline}^{{commit}}"),
                ("rev-parse", "--verify", f"{known_green}^{{commit}}"),
                ("merge-base", "--is-ancestor", task_baseline, known_green),
                ("merge-base", "--is-ancestor", known_green, "HEAD"),
                (
                    "diff",
                    "--name-only",
                    "-z",
                    "--relative",
                    f"{known_green}..HEAD",
                    "--",
                    ".",
                ),
            )
        )
        if reconcile:
            checkpoint_id = clean_cell(task_snapshot.get("Last checkpoint", ""))
            if CHECKPOINT_ID.fullmatch(checkpoint_id):
                try:
                    checkpoint_commit, _dirty = parse_checkpoint_git_receipt(
                        tasks_text, checkpoint_id
                    )
                except ValueError:
                    checkpoint_commit = None
                if checkpoint_commit is not None:
                    queries.append(
                        (
                            "rev-parse",
                            "--verify",
                            f"{checkpoint_commit}^{{commit}}",
                        )
                    )
            queries.extend(
                (
                    (
                        "diff",
                        "--name-only",
                        "-z",
                        "--relative",
                        "HEAD",
                        "--",
                        ".",
                    ),
                    (
                        "ls-files",
                        "--others",
                        "--exclude-standard",
                        "-z",
                        "--",
                        ".",
                    ),
                )
            )
    protected: tuple[str, ...] = ()
    protected_value = clean_cell(task_snapshot.get("Protected dirty paths", ""))
    if protected_value and protected_value != "NONE":
        try:
            protected = tuple(
                parse_task_write_set(protected_value, "Protected dirty paths")
            )
        except ValueError:
            protected = ()
    return queries, baseline_sha, protected


def safe_read_required_binary(
    ctx: Context, relative: str, *, required: bool = True
) -> bytes | None:
    """Read one explicitly supported binary package file within integrity bounds."""

    cached = ctx.source_file_bytes.get(relative)
    if cached is not None:
        return cached
    if ctx.observed_snapshot is not None:
        error = ctx.observed_snapshot.file_errors.get(relative)
        snapshot = ctx.observed_snapshot.file(relative)
        if error is not None:
            if required or error.code != "REQUIRED_FILE_MISSING":
                ctx.error(error.code, error.message, error.path)
            return None
        if snapshot is None:
            if required:
                ctx.error("REQUIRED_FILE_MISSING", "Required file is missing", relative)
            return None
        ctx.source_bytes_read = ctx.observed_snapshot.observation_metrics.bytes_observed
        ctx.source_file_bytes[relative] = snapshot.raw_bytes
        return snapshot.raw_bytes
    try:
        snapshot = ctx._observer.observe_binary(relative)
    except ObservationError as exc:
        if required or exc.code != "REQUIRED_FILE_MISSING":
            ctx.error(exc.code, exc.message, exc.path)
        return None
    ctx.source_bytes_read = ctx._observer.bytes_observed
    ctx.source_file_bytes[relative] = snapshot.raw_bytes
    return snapshot.raw_bytes


def safe_read_text(ctx: Context, relative: str, *, required: bool = True) -> str | None:
    """SAFETY: replay one bounded snapshot text observation without rereading."""

    cached = ctx.texts.get(relative)
    if cached is not None:
        return cached
    if ctx.observed_snapshot is not None:
        error = ctx.observed_snapshot.text_errors.get(
            relative
        ) or ctx.observed_snapshot.file_errors.get(relative)
        snapshot = ctx.observed_snapshot.file(relative)
        if error is not None:
            if required or error.code != "REQUIRED_FILE_MISSING":
                ctx.error(error.code, error.message, error.path)
            return None
        if snapshot is None:
            if required:
                ctx.error("REQUIRED_FILE_MISSING", "Required file is missing", relative)
            return None
        presentation_text = snapshot.presentation_text
        canonical_text = snapshot.canonical_text
        if presentation_text is None or canonical_text is None:
            ctx.error(
                "REQUIRED_FILE_UNREADABLE",
                "Unable to read UTF-8 text: snapshot did not contain text",
                relative,
            )
            return None
        ctx.source_file_bytes[relative] = snapshot.raw_bytes
        ctx.source_bytes_read = ctx.observed_snapshot.observation_metrics.bytes_observed
        ctx.presentation_texts[relative] = presentation_text
        ctx.texts[relative] = canonical_text
        return canonical_text
    try:
        snapshot = ctx._observer.observe_text(relative)
    except ObservationError as exc:
        if required or exc.code != "REQUIRED_FILE_MISSING":
            ctx.error(exc.code, exc.message, exc.path)
        return None
    presentation_text = snapshot.presentation_text
    canonical_text = snapshot.canonical_text
    if presentation_text is None or canonical_text is None:
        ctx.error(
            "REQUIRED_FILE_UNREADABLE",
            "Unable to read UTF-8 text: snapshot did not contain text",
            relative,
        )
        return None
    ctx.source_file_bytes[relative] = snapshot.raw_bytes
    ctx.source_bytes_read = ctx._observer.bytes_observed
    ctx.presentation_texts[relative] = presentation_text
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


COMPATIBILITY_EXPORTS = (
    "_canonical_id_list",
    "_DEFINE_COMPATIBILITY_EXPORTS",
    "STATE_FILE",
    "MANIFEST_FILE",
    "PROJECT_DOCUMENT_DIRECTORY",
    "BUGFIX_FILE",
    "PROJECT_README_FILE",
    "PRD_FILE",
    "RUNBOOK_FILE",
    "TASKS_FILE",
    "VERIFY_FILE",
    "PROMPT_FILE",
    "ENGINE_RUNTIME_CONTROL_FILES",
    "DOCUMENT_SUMMARY_FILES",
    "REQ_ID",
    "DES_ID",
    "AUTH_ID",
    "PLAN_ID",
    "TASK_ID",
    "RUN_ID",
    "CHECKPOINT_ID",
    "COST_AMOUNT",
    "AWS_COST_CEILING",
    "COST_POSTURE_WITH_CAP",
    "DEFAULT_COST_POSTURE",
    "MAX_GATE_RECEIPT_CHARACTERS",
    "ISO_4217_CURRENCY_CODES",
    "PROJECT_MODES",
    "DELIVERY_PROFILES",
    "RISK_LEVELS",
    "AWS_LANES",
    "WORK_KINDS",
    "ARCHITECTURE_DISPOSITIONS",
    "COVERAGE_DOMAINS",
    "ALWAYS_REQUIRED_COVERAGE",
    "COVERAGE_PLAN_HEADING",
    "COVERAGE_PLAN_HEADERS",
    "CHANGE_IMPACT_HEADING",
    "CHANGE_IMPACT_HEADERS",
    "CHANGE_ID",
    "INTAKE_FOUNDATION_HEADING",
    "INTAKE_FOUNDATION_HEADERS",
    "LEGACY_INTAKE_FOUNDATION_HEADERS",
    "INTAKE_FOUNDATION_FIELDS",
    "INTAKE_CORE_FIELDS",
    "OWNER_WORK_CONTEXTS",
    "OWNER_WORK_CONTEXT_SELECTIONS",
    "INTAKE_BASES",
    "INTAKE_CARD_HEADING",
    "INTAKE_CARD_HEADERS",
    "INTAKE_ID",
    "INTAKE_CARD_ID",
    "INTAKE_QUESTION_ID",
    "OWNER_RESPONSE_ID",
    "INTAKE_OWNER_RESPONSE",
    "INTAKE_RESPONSE_REGISTER_HEADING",
    "INTAKE_RESPONSE_REGISTER_HEADERS",
    "STABLE_CONTRACT_ID",
    "NORMATIVE_REQUIREMENT_HEADERS",
    "LEGACY_NORMATIVE_REQUIREMENT_HEADERS",
    "LEGACY_REQUIREMENT_HEADERS",
    "PROJECT_CONTRACT_SCHEMA",
    "REQUIREMENTS_CHANGE_LINEAGE_HEADING",
    "REQUIREMENTS_CHANGE_LINEAGE_HEADERS",
    "ASSUMPTION_LIFECYCLE_HEADING",
    "ASSUMPTION_LIFECYCLE_HEADERS",
    "ASSUMPTION_STATUSES",
    "REQUIREMENTS_REVISION_ID",
    "ASSUMPTION_ID",
    "ACTOR_HEADING",
    "ACTOR_HEADERS",
    "ACTOR_KINDS",
    "ACTOR_ID",
    "ACCEPTANCE_ID",
    "ACCEPTANCE_TEST_BINDING_ID",
    "RICH_USE_CASE_TRIGGERS",
    "RICH_USE_CASE_APPLICABILITY_HEADING",
    "RICH_USE_CASE_APPLICABILITY_HEADERS",
    "RICH_USE_CASE_HEADING",
    "RICH_USE_CASE_HEADERS",
    "USE_CASE_ID",
    "BUSINESS_RULE_HEADING",
    "BUSINESS_RULE_HEADERS",
    "BUSINESS_RULE_ID",
    "REQUIREMENT_COVERAGE_HEADING",
    "REQUIREMENT_COVERAGE_HEADERS",
    "INTAKE_FOUNDATION_IDS",
    "STATE_MODEL_TRIGGERS",
    "EARS_FORMS",
    "EARS_PATTERNS",
    "CONCRETE_SUBJECT",
    "NON_CONCRETE_SUBJECTS",
    "ACCEPTANCE_FORMS",
    "GHERKIN_ACCEPTANCE",
    "MEASURABLE_EXPECTED_RESULT",
    "MEASURABLE_BINDING",
    "QAS_HEADERS",
    "QAS_ID",
    "PROPERTY_TEST_EVIDENCE_HEADING",
    "PROPERTY_TEST_EVIDENCE_HEADERS",
    "PROPERTY_TEST_RESULTS",
    "PROPERTY_TEST_FAILURE_CLASSES",
    "GATE_A_STATES",
    "GATE_B_STATES",
    "RUN_MODES",
    "RUN_STATES",
    "BROWNFIELD_STATES",
    "CANONICAL_PLACEHOLDERS",
    "MANDATORY_REQUIRED_FILES",
    "Context",
    "TASK_METADATA_KEYS",
    "TASK_HEADER_PATTERN",
    "TASK_META_PATTERN",
    "TASK_STATUSES",
    "TASK_AWS_MODES",
    "TASK_DESIGN_TRACE_PATTERN",
    "EVIDENCE_PATTERN",
    "LOCAL_EVIDENCE_ID",
    "LOCAL_EVIDENCE_LIKE",
    "TASK_COMPLETION_EVIDENCE_STATUSES",
    "EVIDENCE_PLACEHOLDER_PATTERN",
    "UNRESOLVED_TOKEN",
    "SNAPSHOT_FIELDS",
    "SNAPSHOT_RUN_STATES",
    "GITHUB_BOUNDARIES",
    "AWS_BOUNDARIES",
    "AWS_DETAIL_FIELDS",
    "CONTROL_HASH_FILES",
    "COORDINATOR_LEDGER_PATHS",
    "ID_LIKE",
    "GITHUB_ISSUE_URL",
    "SHELL_CONTROL",
    "NON_HUMAN_APPROVER",
    "ENVELOPE_EXPLICIT_FIELDS",
    "BROWNFIELD_BASELINE_FIELDS",
    "GATE_A_READINESS_FIELDS",
    "GATE_B_READINESS_FIELDS",
    "AWS_CORE_MATERIALITY_VALUES",
    "VERIFICATION_MATRIX_HEADING",
    "VERIFICATION_MATRIX_HEADERS",
    "require_aws_core_phase_evidence",
    "parse_task_write_set",
    "parse_task_external_state",
    "parse_positive_cost",
    "parse_cost_posture",
    "validate_aws_cost_ceiling",
    "explicit_human_approver",
    "_heading_title_span",
    "MAX_REQUIRED_FILES",
    "MAX_REQUIRED_FILE_BYTES",
    "MAX_PROJECT_SOURCE_BYTES",
    "BINARY_REQUIRED_SUFFIXES",
    "MANIFEST_POLICY",
    "STATE_POLICY",
    "safe_read_required_binary",
    "safe_read_text",
    "bounded_prd_snapshot",
    "load_json_document",
)


def install_compatibility_exports(namespace: dict[str, object]) -> None:
    """COMPATIBILITY: expose legacy doctor names from the stable facade."""

    namespace.update({name: globals()[name] for name in COMPATIBILITY_EXPORTS})


def parse_future_expiry(value: str, *, observed_at: datetime | None = None) -> datetime:
    """COMPATIBILITY: evaluate expiry against one observed UTC clock."""

    return parse_future_expiry_at(
        value, observed_at if observed_at is not None else datetime.now(timezone.utc)
    )
