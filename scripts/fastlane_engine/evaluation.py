"""Immutable Fastlane Engine evaluation model.

Canonical inputs are already-derived domain, authority, routing, remediation, and
owner-projection results. EngineEvaluation is the sole value accepted by the report
serializer. This module performs no observation, parsing, policy derivation, state
write, or external action and grants no approval or authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


def freeze_evaluation_value(value: Any) -> Any:
    """Recursively freeze JSON-compatible evaluation data.

    SAFETY: report inputs cannot be changed after policy and authority evaluation.
    """

    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): freeze_evaluation_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze_evaluation_value(item) for item in value)
    return value


def thaw_evaluation_value(value: Any) -> Any:
    """Return mutable JSON containers for schema serialization only."""

    if isinstance(value, Mapping):
        return {str(key): thaw_evaluation_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_evaluation_value(item) for item in value]
    return value


@dataclass(frozen=True)
class EngineEvaluation:
    """Complete immutable Fastlane policy result before schema-2 serialization."""

    schema_version: int
    package: Mapping[str, Any]
    status: str
    classification: str
    ok: bool
    route: Mapping[str, Any]
    interaction: Mapping[str, Any]
    remediation: Mapping[str, Any]
    context_plan: Mapping[str, Any]
    project: Mapping[str, Any]
    git_baseline: Mapping[str, Any]
    gates: Mapping[str, Any]
    define: Mapping[str, Any]
    design: Mapping[str, Any]
    deliver: Mapping[str, Any]
    aws: Mapping[str, Any]
    authority: Mapping[str, Any]
    basis: Mapping[str, Any]
    owner_decisions: Mapping[str, Any]
    document_summaries: Mapping[str, Any]
    diagnostics: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        """SAFETY: freeze every nested projection before it can be reported."""

        for name in (
            "package",
            "route",
            "interaction",
            "remediation",
            "context_plan",
            "project",
            "git_baseline",
            "gates",
            "define",
            "design",
            "deliver",
            "aws",
            "authority",
            "basis",
            "owner_decisions",
            "document_summaries",
        ):
            object.__setattr__(self, name, freeze_evaluation_value(getattr(self, name)))
        object.__setattr__(
            self,
            "diagnostics",
            tuple(freeze_evaluation_value(item) for item in self.diagnostics),
        )

    @classmethod
    def from_schema2(cls, report: Mapping[str, Any]) -> EngineEvaluation:
        """COMPATIBILITY: group one complete schema-2 fixture without policy work.

        This constructor exists for compatibility fixtures and callers that already
        hold a validated report. Production composition constructs EngineEvaluation
        directly so serialization cannot become an input to lifecycle evaluation.
        """

        if report.get("schema_version") != 2:
            raise ValueError("EngineEvaluation requires report schema version 2")
        return cls(
            schema_version=2,
            package={"bootstrap_version": report.get("bootstrap_version")},
            status=str(report["status"]),
            classification=str(report["classification"]),
            ok=bool(report["ok"]),
            route={
                "lifecycle_state": report["lifecycle_state"],
                "resume_safe": report["resume_safe"],
                "next_prompt": report["next_prompt"],
            },
            interaction=report["interaction"],
            remediation=report["remediation"],
            context_plan=report["context_plan"],
            project=report["project"],
            git_baseline=report["git_baseline"],
            gates=report["gates"],
            define={
                "intake_foundation": report["intake_foundation"],
                "requirements_contract": report["requirements_contract"],
                "coverage_plan": report["coverage_plan"],
            },
            design={
                "design_contract": report["design_contract"],
                "adr_rationale": report["adr_rationale"],
            },
            deliver={
                "evidence_state": report["evidence_state"],
                "release_evidence_cutoff": report["release_evidence_cutoff"],
                "tasks": report["tasks"],
            },
            aws={
                "aws_access": report["aws_access"],
                "aws_mode_boundary": report["aws_mode_boundary"],
                "aws_core_evidence": report["aws_core_evidence"],
                "aws_lifecycle_intent": report["aws_lifecycle_intent"],
                "aws_residual_disposition": report["aws_residual_disposition"],
                "external_authority": report["external_authority"],
                "hook_constraints": report["hook_constraints"],
                "aws_action_transition": report["aws_action_transition"],
                "aws_execution": report["aws_execution"],
                "aws_deployment": report["aws_deployment"],
                "aws_teardown": report["aws_teardown"],
            },
            authority={
                "authorizations": report["authorizations"],
                "write_authority": report["write_authority"],
                "deployment_journal_closure_authority": report[
                    "deployment_journal_closure_authority"
                ],
                "teardown_journal_closure_authority": report[
                    "teardown_journal_closure_authority"
                ],
                "aws_lifecycle_intent_write_authority": report[
                    "aws_lifecycle_intent_write_authority"
                ],
            },
            basis=report["basis"],
            owner_decisions={
                "owner_decision_brief": report["owner_decision_brief"],
                "owner_decision_inventory": report["owner_decision_inventory"],
                "owner_answer_confirmation": report["owner_answer_confirmation"],
            },
            document_summaries=report["document_summaries"],
            diagnostics=tuple(report["diagnostics"]),
        )


__all__ = [
    "EngineEvaluation",
    "freeze_evaluation_value",
    "thaw_evaluation_value",
]
