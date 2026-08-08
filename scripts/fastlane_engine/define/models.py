"""Immutable models returned by Fastlane Define evaluators.

Canonical inputs remain the current PRD records. These models are derived,
read-only projections. They perform no I/O and cannot approve Gate A, alter a
requirement digest, route work, or authorize an external action. Their public
serialization retains the characterized compatibility contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
            "change_lineage": (
                self.change_lineage.to_dict() if self.change_lineage else None
            ),
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
                {"A": self.option_a, "B": self.option_b, "C": self.option_c}
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
class IntakeQuestionGuidance:
    """Derived, non-authoritative guidance for the next owner consultation."""

    schema_version: int = 1
    status: str = "WAITING_FOR_OWNER_CONTEXT"
    owner_work_context: str | None = None
    objective: str | None = None
    fields: tuple[str, ...] = ()
    target_ids: tuple[str, ...] = ()
    basis_ids: tuple[str, ...] = ()
    owner_action_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "owner_work_context": self.owner_work_context,
            "objective": self.objective,
            "fields": list(self.fields),
            "target_ids": list(self.target_ids),
            "basis_ids": list(self.basis_ids),
            "owner_action_required": self.owner_action_required,
        }


@dataclass(frozen=True)
class ProjectConfigurationGuidance:
    """Derived, non-authoritative ownership and basis for internal selections."""

    schema_version: int = 1
    status: str = "WAITING_FOR_OWNER_FACTS"
    owner_action_required: bool = False
    current_project_mode: str | None = None
    derived_project_mode: str | None = None
    current_delivery_profile: str | None = None
    current_effective_risk: str | None = None
    current_aws_lane: str | None = None
    safest_current_aws_lane: str = "documentation-only"
    project_mode_basis_ids: tuple[str, ...] = ()
    risk_profile_basis_ids: tuple[str, ...] = ()
    codex_actions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "owner_action_required": self.owner_action_required,
            "current_project_mode": self.current_project_mode,
            "derived_project_mode": self.derived_project_mode,
            "current_delivery_profile": self.current_delivery_profile,
            "current_effective_risk": self.current_effective_risk,
            "current_aws_lane": self.current_aws_lane,
            "safest_current_aws_lane": self.safest_current_aws_lane,
            "project_mode_basis_ids": list(self.project_mode_basis_ids),
            "risk_profile_basis_ids": list(self.risk_profile_basis_ids),
            "codex_actions": list(self.codex_actions),
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
    next_question_guidance: IntakeQuestionGuidance = field(
        default_factory=IntakeQuestionGuidance
    )
    project_configuration: ProjectConfigurationGuidance = field(
        default_factory=ProjectConfigurationGuidance
    )
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
            "pending_card": self.pending_card.to_dict() if self.pending_card else None,
            "next_question_guidance": self.next_question_guidance.to_dict(),
            "project_configuration": self.project_configuration.to_dict(),
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


__all__ = (
    "AssumptionLifecycleRecord",
    "ChangeImpactContract",
    "ChangeImpactRow",
    "CoverageContract",
    "CoverageOmission",
    "IntakeCard",
    "IntakeFoundationContract",
    "IntakeQuestionGuidance",
    "IntakeQuestion",
    "NormalizedOwnerResponse",
    "ProjectConfigurationGuidance",
    "RequirementsChangeLineage",
    "RequirementsContract",
)
