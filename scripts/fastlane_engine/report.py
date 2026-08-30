"""Pure Fastlane Engine schema-2 report serialization.

Canonical input is one complete immutable EngineEvaluation. The returned dictionary
preserves the public report schema and ordering. This module performs no observation,
parsing, validation, routing, remediation, authority derivation, clock access, state
write, or external action.
"""

from __future__ import annotations

from typing import Any

from .evaluation import EngineEvaluation, thaw_evaluation_value


def serialize_evaluation(evaluation: EngineEvaluation) -> dict[str, Any]:
    """SAFETY: serialize a complete evaluation without deriving or widening state.

    The result preserves schema-2 field names and order. Missing evaluation fields
    fail closed through ordinary key access; this function never supplies defaults,
    reads canonical records, invokes policy, or grants approval or authority.
    """

    package = thaw_evaluation_value(evaluation.package)
    route = thaw_evaluation_value(evaluation.route)
    deliver = thaw_evaluation_value(evaluation.deliver)
    aws = thaw_evaluation_value(evaluation.aws)
    authority = thaw_evaluation_value(evaluation.authority)
    define = thaw_evaluation_value(evaluation.define)
    design = thaw_evaluation_value(evaluation.design)
    owner = thaw_evaluation_value(evaluation.owner_decisions)
    return {
        "schema_version": evaluation.schema_version,
        "bootstrap_version": package.get("bootstrap_version"),
        "status": evaluation.status,
        "classification": evaluation.classification,
        "ok": evaluation.ok,
        "lifecycle_state": route["lifecycle_state"],
        "resume_safe": route["resume_safe"],
        "next_prompt": route["next_prompt"],
        "interaction": thaw_evaluation_value(evaluation.interaction),
        "remediation": thaw_evaluation_value(evaluation.remediation),
        "context_plan": thaw_evaluation_value(evaluation.context_plan),
        "project": thaw_evaluation_value(evaluation.project),
        "git_baseline": thaw_evaluation_value(evaluation.git_baseline),
        "aws_access": aws["aws_access"],
        "aws_mode_boundary": aws["aws_mode_boundary"],
        "gates": thaw_evaluation_value(evaluation.gates),
        "evidence_state": deliver["evidence_state"],
        "release_evidence_cutoff": deliver["release_evidence_cutoff"],
        **(
            {"release_claim": deliver["release_claim"]}
            if "release_claim" in deliver
            else {}
        ),
        "aws_core_evidence": aws["aws_core_evidence"],
        "authorizations": authority["authorizations"],
        "write_authority": authority["write_authority"],
        "deployment_journal_closure_authority": authority[
            "deployment_journal_closure_authority"
        ],
        "teardown_journal_closure_authority": authority[
            "teardown_journal_closure_authority"
        ],
        "aws_lifecycle_intent": aws["aws_lifecycle_intent"],
        "aws_residual_disposition": aws["aws_residual_disposition"],
        "aws_lifecycle_intent_write_authority": authority[
            "aws_lifecycle_intent_write_authority"
        ],
        "external_authority": aws["external_authority"],
        "hook_constraints": aws["hook_constraints"],
        "aws_action_transition": aws["aws_action_transition"],
        "aws_execution": aws["aws_execution"],
        "aws_deployment": aws["aws_deployment"],
        "aws_teardown": aws["aws_teardown"],
        "basis": thaw_evaluation_value(evaluation.basis),
        "document_summaries": thaw_evaluation_value(evaluation.document_summaries),
        "owner_decision_brief": owner["owner_decision_brief"],
        "owner_decision_inventory": owner["owner_decision_inventory"],
        "owner_answer_confirmation": owner["owner_answer_confirmation"],
        "intake_foundation": define["intake_foundation"],
        "requirements_contract": define["requirements_contract"],
        "coverage_plan": define["coverage_plan"],
        "design_contract": design["design_contract"],
        "adr_rationale": design["adr_rationale"],
        "tasks": deliver["tasks"],
        "diagnostics": thaw_evaluation_value(evaluation.diagnostics),
    }


__all__ = ["serialize_evaluation"]
