"""Immutable AWS lifecycle vocabulary and adapter policy.

Canonical inputs are already-observed PRD, VERIFY, and authorization records.
The models grant no AWS access or authority and perform no I/O. Callbacks make
the still-monolithic authority layer explicit until PR 7 extracts it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


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
AWS_DISCOVERY_ID = re.compile(r"AWS-DISC-\d{4,}")
TECHNOLOGY_DECISION_ID = re.compile(r"TECH-\d{4}")

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
AWS_DEPLOYMENT_PRECALL_RESULT = "NOT_OBSERVED — pre-call journal only"
AWS_READ_ONLY_OPERATION = re.compile(
    r"(?i)^(?:[a-z0-9-]+[.:])?(?:BatchGet|Check|Describe|Detect|Estimate|Get|"
    r"Head|List|Lookup|Preview|Search|Simulate|Validate)[A-Za-z0-9]*$"
)
AWS_READ_AUTHORIZATION_ID = re.compile(r"AWS-READ-AUTH-\d{4,}")
AWS_PREFLIGHT_ID = re.compile(r"AWS-PREFLIGHT-\d{4,}")
AWS_LIFECYCLE_INTENT_VALUES = {"NONE", "RESIDUAL_REVIEW", "TEARDOWN", "RETAIN"}
AWS_LIFECYCLE_INTENT_SOURCE = re.compile(r"owner-message MSG-AWS-LIFECYCLE-\d{4,}")


@dataclass(frozen=True)
class AwsCoreEvidenceRow:
    """One observed AWS Core capability row; never an authority record."""

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
class AwsAuthorityPolicy:
    """COMPATIBILITY: explicit callbacks owned by the PR 7 authority layer."""

    split_authority_values: Callable[[str], list[str]]
    action_authorization_rows: Callable[[str], dict[str, dict[str, str]]]
    exact_receipt_fields: Callable[..., dict[str, str] | None]
    envelope_scalar: Callable[..., str | None]
    envelope_values: Callable[..., list[str]]
    receipt_identity_matches_gate_b: Callable[..., bool]
    receipt_scope_within_gate_b: Callable[..., bool]
    receipt_artifact_matches_gate_b: Callable[..., bool]
    gate_b_rollback_value: Callable[..., str | None]
    deployment_reconciliation_read_authority: Callable[..., dict[str, Any] | None]
    teardown_reconciliation_read_authority: Callable[..., dict[str, Any] | None]
    parse_verification_matrix: Callable[[str], list[dict[str, str]]]
    explicit_human_approver: Callable[[str], bool]
    marked_receipt: Callable[[str, str], str]
    parse_aws_environment: Callable[[str], dict[str, str]]


__all__ = (
    "AWS_CORE_EVIDENCE_HEADERS",
    "AWS_CORE_EVIDENCE_HEADERS_V1",
    "AWS_CORE_EVIDENCE_PHASES",
    "AWS_CORE_EVIDENCE_STATUSES",
    "AWS_CORE_REQUIRED_CAPABILITIES",
    "AWS_DEPLOYMENT_ACTION_STATUSES",
    "AWS_DEPLOYMENT_ATTEMPT_ID",
    "AWS_DEPLOYMENT_EVIDENCE_HEADERS",
    "AWS_DEPLOYMENT_EVIDENCE_HEADING",
    "AWS_DEPLOYMENT_PRECALL_RESULT",
    "AWS_DEPLOYMENT_READ_PROVENANCE",
    "AWS_DEPLOYMENT_RECEIPT_FIELDS",
    "AWS_DEPLOYMENT_RECONCILIATION_STATUSES",
    "AWS_DEPLOYMENT_TERMINAL_STATUSES",
    "AWS_DISCOVERY_ID",
    "AWS_LIFECYCLE_INTENT_SOURCE",
    "AWS_LIFECYCLE_INTENT_VALUES",
    "AWS_PLAN_BINDING",
    "AWS_PREFLIGHT_ID",
    "AWS_READ_AUTHORIZATION_ID",
    "AWS_READ_ONLY_OPERATION",
    "AWS_READ_PREFLIGHT_HEADERS",
    "AWS_READ_PREFLIGHT_HEADING",
    "AWS_READ_PREFLIGHT_RECEIPT_FIELDS",
    "AWS_TEARDOWN_ACTION_STATUSES",
    "AWS_TEARDOWN_ATTEMPT_ID",
    "AWS_TEARDOWN_EVIDENCE_HEADERS",
    "AWS_TEARDOWN_EVIDENCE_HEADING",
    "AWS_TEARDOWN_PRECALL_RESULT",
    "AWS_TEARDOWN_READ_PROVENANCE",
    "AWS_TEARDOWN_RECEIPT_FIELDS",
    "AWS_TEARDOWN_REVIEW_STATUSES",
    "AWS_TEARDOWN_TERMINAL_STATUSES",
    "AwsAuthorityPolicy",
    "AwsCoreEvidenceRow",
    "TECHNOLOGY_DECISION_ID",
)
