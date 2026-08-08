"""Non-authoritative source-assisted Define projection.

Canonical input is one already-observed owner-supplied UTF-8 product brief.
The module returns a bounded preview of candidate product facts, technical
proposals, and missing Define domains. It performs no I/O, canonical write,
approval, architecture selection, routing, or authority derivation. Imported
language can reduce later consultation questions but can never import authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from ..core.markdown_index import MarkdownDocumentIndex


SOURCE_ASSIST_SCHEMA_VERSION = 1
SOURCE_BRIEF_MAX_BYTES = 512 * 1024
SOURCE_BRIEF_MAX_CANDIDATES = 12
SOURCE_BRIEF_MAX_TECHNICAL_PROPOSALS = 6
SOURCE_BRIEF_MAX_SUMMARY_CHARACTERS = 280

_SECRET_LIKE = re.compile(
    r"(?:AKIA|ASIA)[0-9A-Z]{16}|"
    r"(?:github_pat_|gh[pousr]_|sk-proj-)[A-Za-z0-9_-]{12,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:api[_ -]?key|secret[_ -]?access[_ -]?key|client[_ -]?secret|"
    r"password|access[_ -]?token)\s*[:=]\s*['\"]?[^\s,'\"]{8,}",
    re.IGNORECASE,
)
_AUTHORITY_LANGUAGE = re.compile(
    r"\b(?:approved|authorized|final requirements?|ready to (?:build|develop|deploy)|"
    r"construction approved|deployment approved)\b",
    re.IGNORECASE,
)
_TECHNICAL_HEADING = re.compile(
    r"\b(?:architecture|technical|technology|stack|implementation|infrastructure|"
    r"deployment|hosting|database)\b",
    re.IGNORECASE,
)
_TECHNICAL_LANGUAGE = re.compile(
    r"\b(?:Lambda|DynamoDB|RDS|Aurora|S3|Cognito|"
    r"API Gateway|AppSync|EC2|ECS|EKS|Fargate|CloudFront|Route 53|SQS|SNS|"
    r"EventBridge|Step Functions|CloudFormation|CDK|Terraform|Kubernetes|"
    r"React|Vue|Angular|Next\.js|Node\.js|Python|Java|\.NET|PostgreSQL|"
    r"MySQL|MongoDB|Redis|serverless|container|microservice|architecture|"
    r"technology stack|framework|database)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceCandidate:
    """One bounded source statement requiring later owner confirmation."""

    category: str
    label: str
    summary: str
    treatment: str

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "label": self.label,
            "summary": self.summary,
            "treatment": self.treatment,
        }


_CATEGORY_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "NON_GOALS",
        "Non-goals and deferrals",
        ("non-goal", "non goal", "out of scope", "excluded", "deferred"),
    ),
    (
        "ACCEPTANCE_CRITERIA",
        "Acceptance and success",
        ("acceptance", "success criteria", "definition of done", "measure"),
    ),
    (
        "USER_JOURNEYS",
        "User journeys",
        ("journey", "user story", "use case", "workflow", "flow"),
    ),
    (
        "INTENDED_USERS",
        "Intended users",
        ("user", "audience", "persona", "actor", "stakeholder", "customer"),
    ),
    (
        "DATA_AND_ACCESS",
        "Data and access boundaries",
        (
            "data",
            "privacy",
            "security",
            "access",
            "identity",
            "authentication",
            "authorization",
            "retention",
            "deletion",
        ),
    ),
    (
        "RELIABILITY_AND_RECOVERY",
        "Failure and recovery expectations",
        (
            "reliability",
            "recovery",
            "backup",
            "failure",
            "availability",
            "rto",
            "rpo",
            "retry",
        ),
    ),
    (
        "REGION_AND_COST",
        "Region and cost constraints",
        ("budget", "cost", "region", "location", "spend"),
    ),
    (
        "ASSUMPTIONS_AND_RISKS",
        "Assumptions, constraints, and risks",
        ("assumption", "risk", "constraint", "dependency", "concern"),
    ),
    (
        "FIRST_RELEASE_SCOPE",
        "First-release scope",
        ("scope", "mvp", "first release", "feature", "requirement", "capability"),
    ),
    (
        "PRODUCT_OUTCOME",
        "Product outcome",
        (
            "overview",
            "product",
            "problem",
            "vision",
            "goal",
            "objective",
            "outcome",
            "summary",
            "background",
        ),
    ),
)

_MISSING_DOMAINS: tuple[tuple[str, str], ...] = (
    ("PRODUCT_OUTCOME", "The product outcome and first useful result"),
    ("INTENDED_USERS", "The intended users and their access boundaries"),
    ("FIRST_RELEASE_SCOPE", "The first-release scope"),
    ("NON_GOALS", "Explicit non-goals and deferrals"),
    ("ACCEPTANCE_CRITERIA", "Measurable acceptance criteria"),
    ("DATA_AND_ACCESS", "Data classification, retention, deletion, and access"),
    ("RELIABILITY_AND_RECOVERY", "Failure and recovery expectations"),
    ("REGION_AND_COST", "AWS Region and development cost constraints"),
)

_DOES_NOT_AUTHORIZE = (
    "Gate A approval",
    "Architecture selection or Gate B approval",
    "Local construction",
    "AWS account access",
    "Deployment or spending",
    "Teardown",
)


def _utc_timestamp(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def _plain_summary(value: str) -> str:
    """Return a short owner-readable excerpt without Markdown machinery."""

    value = re.sub(r"<!--[\s\S]*?-->", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    lines: list[str] = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line or re.fullmatch(r"[-:| ]+", line):
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+|>\s*)", "", line)
        line = line.replace("|", ";")
        line = line.replace("`", "")
        line = re.sub(r"[*_~]+", "", line)
        line = re.sub(r"\s+", " ", line).strip(" ;")
        if line:
            lines.append(line)
        if len(" ".join(lines)) >= SOURCE_BRIEF_MAX_SUMMARY_CHARACTERS:
            break
    summary = " ".join(lines)
    if len(summary) <= SOURCE_BRIEF_MAX_SUMMARY_CHARACTERS:
        return summary
    clipped = summary[: SOURCE_BRIEF_MAX_SUMMARY_CHARACTERS - 1].rsplit(" ", 1)[0]
    return clipped.rstrip(".,;:") + "…"


def _document_sections(
    source_text: str,
    markdown: MarkdownDocumentIndex | None,
) -> tuple[tuple[str, str], ...]:
    if markdown is None or not markdown.headings:
        summary = _plain_summary(source_text)
        return (("Product brief", summary),) if summary else ()
    sections: list[tuple[str, str]] = []
    headings = markdown.headings
    for index, heading in enumerate(headings):
        end = (
            headings[index + 1].span.start
            if index + 1 < len(headings)
            else len(markdown.structural_text)
        )
        summary = _plain_summary(markdown.structural_text[heading.span.end : end])
        if summary:
            sections.append((heading.title, summary))
    return tuple(sections)


def _candidate_category(title: str, summary: str) -> tuple[str, str] | None:
    title_key = title.casefold()
    combined = f"{title_key} {summary.casefold()}"
    for category, label, keywords in _CATEGORY_RULES:
        subject = (
            title_key if any(keyword in title_key for keyword in keywords) else combined
        )
        if any(keyword in subject for keyword in keywords):
            return category, label
    return None


def _candidate_facts(
    sections: tuple[tuple[str, str], ...],
) -> tuple[SourceCandidate, ...]:
    candidates: list[SourceCandidate] = []
    seen: set[tuple[str, str]] = set()
    for title, summary in sections:
        category = _candidate_category(title, summary)
        if category is None:
            continue
        category_id, label = category
        identity = (category_id, summary.casefold())
        if identity in seen:
            continue
        seen.add(identity)
        candidates.append(
            SourceCandidate(category_id, label, summary, "OWNER_CONFIRMATION_REQUIRED")
        )
        if len(candidates) >= SOURCE_BRIEF_MAX_CANDIDATES:
            break
    if not candidates and sections:
        candidates.append(
            SourceCandidate(
                "PRODUCT_OUTCOME",
                "Product outcome",
                sections[0][1],
                "OWNER_CONFIRMATION_REQUIRED",
            )
        )
    return tuple(candidates)


def _technical_proposals(
    sections: tuple[tuple[str, str], ...],
) -> tuple[dict[str, Any], ...]:
    proposals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for title, summary in sections:
        if (
            _TECHNICAL_HEADING.search(title) is None
            and _TECHNICAL_LANGUAGE.search(summary) is None
        ):
            continue
        identity = summary.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        proposals.append(
            {
                "label": title,
                "summary": summary,
                "treatment": "PROPOSED_TECHNICAL_INPUT",
                "allowed_classifications": [
                    "OWNER_CONSTRAINT",
                    "OWNER_PREFERENCE",
                    "SOURCE_RECOMMENDATION",
                    "UNSUPPORTED_TECHNICAL_SUGGESTION",
                ],
                "selected": False,
            }
        )
        if len(proposals) >= SOURCE_BRIEF_MAX_TECHNICAL_PROPOSALS:
            break
    return tuple(proposals)


def blocked_source_assist_preview(
    source_path: str,
    observed_at: datetime,
    *,
    code: str,
    message: str,
    secret_like_material: str = "UNKNOWN",
) -> dict[str, Any]:
    """Return a safe failure projection without source content or authority."""

    return {
        "schema_version": SOURCE_ASSIST_SCHEMA_VERSION,
        "kind": "SOURCE_ASSISTED_DEFINE",
        "status": "BLOCKED",
        "source": {
            "type": "OWNER_SUPPLIED_AI_DRAFT",
            "path": source_path,
            "digest": "NONE",
            "observed_at": _utc_timestamp(observed_at),
            "authority": "NON_AUTHORITATIVE_SOURCE",
        },
        "safety": {
            "secret_like_material": secret_like_material,
            "canonical_writes_allowed": False,
            "source_instructions_trusted": False,
        },
        "candidate_facts": [],
        "technical_proposals": [],
        "missing_or_unclear": [],
        "approval_language_ignored": True,
        "confirmation": {
            "status": "NOT_AVAILABLE",
            "question": "NONE",
            "options": [],
        },
        "does_not_authorize": list(_DOES_NOT_AUTHORIZE),
        "issues": [{"code": code, "message": message}],
    }


def derive_source_assist_preview(
    source_path: str,
    source_text: str,
    source_sha256: str,
    observed_at: datetime,
    *,
    markdown: MarkdownDocumentIndex | None = None,
) -> dict[str, Any]:
    """Derive one safe source preview without importing facts or authority."""

    if _SECRET_LIKE.search(source_text) is not None:
        return blocked_source_assist_preview(
            source_path,
            observed_at,
            code="SOURCE_BRIEF_SECRET_LIKE",
            message=(
                "Potential secret material was detected. Remove or redact it before "
                "Fastlane reviews this source; no canonical project record was changed."
            ),
            secret_like_material="DETECTED",
        )
    sections = _document_sections(source_text, markdown)
    if not sections:
        return blocked_source_assist_preview(
            source_path,
            observed_at,
            code="SOURCE_BRIEF_EMPTY",
            message=(
                "The supplied source contains no readable product content; no "
                "canonical project record was changed."
            ),
            secret_like_material="NOT_DETECTED",
        )
    candidates = _candidate_facts(sections)
    technical = _technical_proposals(sections)
    present_categories = {candidate.category for candidate in candidates}
    missing = [
        label
        for category, label in _MISSING_DOMAINS
        if category not in present_categories
    ]
    return {
        "schema_version": SOURCE_ASSIST_SCHEMA_VERSION,
        "kind": "SOURCE_ASSISTED_DEFINE",
        "status": "READY_FOR_CONFIRMATION",
        "source": {
            "type": "OWNER_SUPPLIED_AI_DRAFT",
            "path": source_path,
            "digest": "sha256:" + source_sha256,
            "observed_at": _utc_timestamp(observed_at),
            "authority": "NON_AUTHORITATIVE_SOURCE",
        },
        "safety": {
            "secret_like_material": "NOT_DETECTED",
            "canonical_writes_allowed": False,
            "source_instructions_trusted": False,
        },
        "candidate_facts": [candidate.to_dict() for candidate in candidates],
        "technical_proposals": list(technical),
        "missing_or_unclear": missing,
        "approval_language_ignored": bool(_AUTHORITY_LANGUAGE.search(source_text)),
        "confirmation": {
            "status": "OWNER_CONFIRMATION_REQUIRED",
            "question": "How should Fastlane use this document?",
            "options": [
                {
                    "key": "A",
                    "label": "Use the complete document as proposed input.",
                    "effect": (
                        "Product and technical content remain candidates; no technical "
                        "choice is selected automatically."
                    ),
                    "recommended": False,
                },
                {
                    "key": "B",
                    "label": (
                        "Use its product information and independently reconsider "
                        "every technical choice."
                    ),
                    "effect": (
                        "Fastlane uses supported product content to reduce Define "
                        "questions and evaluates architecture later in Design."
                    ),
                    "recommended": True,
                },
                {
                    "key": "C",
                    "label": "Do not import it.",
                    "effect": "Fastlane continues the normal Define consultation.",
                    "recommended": False,
                },
            ],
        },
        "does_not_authorize": list(_DOES_NOT_AUTHORIZE),
        "issues": [],
    }


__all__ = (
    "SOURCE_ASSIST_SCHEMA_VERSION",
    "SOURCE_BRIEF_MAX_BYTES",
    "SourceCandidate",
    "blocked_source_assist_preview",
    "derive_source_assist_preview",
)
