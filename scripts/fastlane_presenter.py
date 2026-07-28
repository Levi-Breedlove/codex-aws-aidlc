#!/usr/bin/env python3
"""Render deterministic Fastlane owner updates from machine-derived state."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Mapping, Sequence


class PresentationError(RuntimeError):
    """Raised when state cannot be rendered as a routine owner update."""


STATUS_TEXT = {
    "UNCONFIGURED_TEMPLATE": "This template has not been initialized.",
    "INTAKE_REQUIRED": "Ready to define the project.",
    "REQUIREMENTS_ANALYSIS": "Requirements are ready for analysis.",
    "REQUIREMENTS_STALE": "Approved requirements need review after a change.",
    "WAITING_GATE_A": "Requirements are ready for your Gate A decision.",
    "DESIGN_REQUIRED": "The technical design is ready to be developed.",
    "DESIGN_STALE": "The technical design must be refreshed.",
    "WAITING_GATE_B": "The design is ready for your Gate B decision.",
    "TASK_PLAN_REQUIRED": "The approved design is ready for task planning.",
    "CONSTRUCTION_SINGLE": "Approved local construction can continue.",
    "CONSTRUCTION_AUTONOMOUS": "Approved local construction is in progress.",
    "RELEASE_REVIEW": "Local construction is ready for release review.",
    "AWS_PREFLIGHT_REQUIRED": "Deployment planning needs current AWS evidence.",
    "RELEASE_VERIFIED": "The approved local workflow is complete.",
    "BLOCKED": "Fastlane stopped at a validation boundary.",
}

ACTION_TEXT = {
    "COMPLETE_PREREQUISITE_CHECKLIST": (
        "Complete the prerequisite checklist, then send `init template` again."
    ),
    "ANSWER_OPEN_DECISIONS": "Answer the next one to three project questions.",
    "APPROVE_GATE_A": "Review and decide the Gate A requirements receipt.",
    "ENABLE_AWS_CORE": "Enable official AWS Core, then continue the affected AWS step.",
    "APPROVE_GATE_B": "Review and decide the Gate B design and construction receipt.",
    "AUTHORIZE_AWS_OPERATION": "Review the exact AWS authority receipt before any AWS action.",
    "FIX_VALIDATION_FAILURE": "Resolve the listed validation failure, then continue Fastlane.",
    "REVIEW_SAFETY_BLOCKER": "Review the reported safety blocker before Fastlane changes anything.",
    "NONE_CONTINUE_AUTOMATICALLY": "Nothing.",
}

NEXT_TEXT = {
    "UNCONFIGURED_TEMPLATE": (
        "Codex will verify prerequisites before asking project questions."
    ),
    "INTAKE_REQUIRED": "Codex will record your answers and continue guided definition.",
    "REQUIREMENTS_ANALYSIS": "Codex will analyze the complete requirement set.",
    "REQUIREMENTS_STALE": "Codex will reconcile the changed requirement basis.",
    "WAITING_GATE_A": "After approval, Codex will begin technical design.",
    "DESIGN_REQUIRED": "Codex will compare complete architecture candidates.",
    "DESIGN_STALE": "Codex will refresh design evidence and the proposal.",
    "WAITING_GATE_B": "After approval, Codex will generate tasks and build locally.",
    "TASK_PLAN_REQUIRED": "Codex will generate the dependency-aware task plan.",
    "CONSTRUCTION_SINGLE": "Codex will execute the next ready local task.",
    "CONSTRUCTION_AUTONOMOUS": "Codex will continue approved local tasks.",
    "RELEASE_REVIEW": "Codex will validate evidence and release readiness.",
    "AWS_PREFLIGHT_REQUIRED": "Codex will collect documentation evidence without accessing an AWS account.",
    "RELEASE_VERIFIED": "No further action is required.",
    "BLOCKED": "Codex will resume only after the named blocker is resolved.",
}

COPYABLE_REPLIES = {
    "ANSWER_OPEN_DECISIONS": "Reply with your answers to the questions below.",
    "ENABLE_AWS_CORE": "CONTINUE FASTLANE",
    "FIX_VALIDATION_FAILURE": "CONTINUE FASTLANE",
}


def _interaction(report: Mapping[str, Any]) -> Mapping[str, Any]:
    value = report.get("interaction")
    if not isinstance(value, Mapping):
        raise PresentationError("doctor report is missing interaction state")
    return value


def _remediation_text(report: Mapping[str, Any]) -> tuple[str | None, str | None]:
    value = report.get("remediation")
    if value is None:
        return None, None
    if not isinstance(value, Mapping):
        raise PresentationError("doctor report has invalid remediation state")
    next_action = value.get("next_action")
    if not isinstance(next_action, Mapping):
        raise PresentationError("doctor report has invalid remediation next action")
    action_kind = str(next_action.get("action_kind", ""))
    party = str(next_action.get("responsible_party", ""))
    automatic = next_action.get("automatic_continuation_allowed") is True
    if action_kind == "CORRECT_AND_REVALIDATE":
        if party != "CODEX" or not automatic:
            raise PresentationError("unsafe automatic remediation state")
        return (
            "Fastlane found an in-scope validation defect.",
            "Codex will correct the reported in-scope failure and rerun validation.",
        )
    if action_kind == "REVIEW_SAFETY_BLOCKER":
        if party != "HUMAN_REVIEWER" or automatic:
            raise PresentationError("unsafe manual remediation state")
        return None, None
    if action_kind not in {
        "ANSWER_OPEN_DECISIONS",
        "APPROVE_GATE_A",
        "APPROVE_GATE_B",
        "AUTHORIZE_AWS_OPERATION",
        "COMPLETE_PREREQUISITE_CHECKLIST",
        "CONTINUE_CURRENT_ROUTE",
        "ENABLE_AWS_CORE",
    }:
        raise PresentationError("unknown remediation next action")
    return None, None


def _task_details(report: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = report.get("tasks")
    return value if isinstance(value, Mapping) else None


TASK_ID_PATTERN = re.compile(r"TASK-\d{4,}")
AWS_DISCOVERY_ID_PATTERN = re.compile(r"AWS-DISC-\d{4,}")
AWS_SKILL_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]*")
AWS_OFFICIAL_REFERENCE_PATTERN = re.compile(
    r"https://(?:docs\.aws\.amazon\.com|aws\.amazon\.com)/\S+", re.IGNORECASE
)


def _task_ids(tasks: Mapping[str, Any], field: str) -> list[str]:
    value = tasks.get(field)
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PresentationError("invalid deterministic task identifiers")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or TASK_ID_PATTERN.fullmatch(item) is None:
            raise PresentationError("invalid deterministic task identifiers")
        result.append(item)
    if len(result) != len(set(result)):
        raise PresentationError("duplicate deterministic task identifiers")
    return result


def _task_count(tasks: Mapping[str, Any], field: str) -> int:
    value = tasks.get(field, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PresentationError("invalid deterministic task progress")
    return value


def _delivery_status(report: Mapping[str, Any], reason: str) -> str | None:
    if reason not in {"CONSTRUCTION_SINGLE", "CONSTRUCTION_AUTONOMOUS"}:
        return None
    tasks = _task_details(report)
    if tasks is None:
        return None
    total = _task_count(tasks, "total")
    completed = _task_count(tasks, "completed")
    skipped = _task_count(tasks, "skipped")
    blocked = _task_count(tasks, "blocked")
    ready_count = _task_count(tasks, "ready")
    active_count = _task_count(tasks, "in_progress")
    active = _task_ids(tasks, "active_ids")
    ready = _task_ids(tasks, "ready_ids")
    if total < 1 or sum(
        (completed, skipped, blocked, ready_count, active_count)
    ) > total:
        raise PresentationError("invalid deterministic task progress")
    if "active_ids" in tasks and len(active) != active_count:
        raise PresentationError("active task count does not match task identifiers")
    if "ready_ids" in tasks and len(ready) != ready_count:
        raise PresentationError("ready task count does not match task identifiers")
    if "blocked_ids" in tasks:
        blocked_ids = _task_ids(tasks, "blocked_ids")
        if len(blocked_ids) != blocked:
            raise PresentationError("blocked task count does not match task identifiers")
    status = f"{completed} of {total} tasks complete"
    if skipped:
        status += f"; {skipped} skipped with an approved record"
    if active:
        status += "; working on " + ", ".join(active)
    elif ready:
        status += f"; {ready[0]} is ready next"
    return status + "."


def _delivery_next(report: Mapping[str, Any], reason: str) -> str | None:
    if reason not in {"CONSTRUCTION_SINGLE", "CONSTRUCTION_AUTONOMOUS"}:
        return None
    tasks = _task_details(report)
    if tasks is None:
        return None
    active = _task_ids(tasks, "active_ids")
    ready = _task_ids(tasks, "ready_ids")
    if active:
        return "Codex will finish and validate " + ", ".join(active) + "."
    if ready:
        return f"Codex will continue with {ready[0]}."
    return None


def _coverage_next(report: Mapping[str, Any], reason: str) -> str | None:
    if reason not in {"DESIGN_REQUIRED", "DESIGN_STALE"}:
        return None
    value = report.get("coverage_plan")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise PresentationError("invalid deterministic coverage plan")
    if value.get("status") != "READY":
        return None
    disposition = value.get("architecture_disposition")
    if disposition == "SELECT":
        return "Codex will compare complete architecture candidates."
    if disposition == "AMEND":
        return (
            "Codex will reconsider only architecture decisions affected by "
            "this change."
        )
    if disposition == "PRESERVE":
        return (
            "Codex will verify that the existing architecture remains valid "
            "for this bounded change."
        )
    raise PresentationError("invalid deterministic architecture disposition")


def _aws_core_audit(
    report: Mapping[str, Any], interaction: Mapping[str, Any]
) -> str | None:
    """Render AWS Core attribution only from the doctor's observed projection."""

    core = interaction.get("aws_core")
    if not isinstance(core, Mapping) or core.get("evidence_status") != "CURRENT":
        return None
    stage = str(interaction.get("owner_stage", ""))
    next_prompt = str(report.get("next_prompt", ""))
    if stage == "DESIGN":
        phase = "DESIGN-10"
    elif next_prompt.startswith("AWS-"):
        phase = "AWS-10"
    else:
        return None
    evidence = report.get("aws_core_evidence")
    if not isinstance(evidence, Mapping):
        return None
    observed = evidence.get("observed_usage")
    if not isinstance(observed, Mapping):
        return None
    usage = observed.get(phase)
    if not isinstance(usage, Mapping) or usage.get("status") != "OBSERVED":
        return None
    chains = usage.get("chains")
    if (
        not isinstance(chains, Sequence)
        or isinstance(chains, (str, bytes))
        or not chains
    ):
        raise PresentationError("invalid observed AWS Core attribution")
    skills: list[str] = []
    references: list[str] = []
    for chain in chains:
        if not isinstance(chain, Mapping):
            raise PresentationError("invalid observed AWS Core attribution")
        discovery_id = chain.get("discovery_id")
        skill = chain.get("skill_identifier")
        refs = chain.get("official_references")
        if (
            not isinstance(discovery_id, str)
            or AWS_DISCOVERY_ID_PATTERN.fullmatch(discovery_id) is None
            or not isinstance(skill, str)
            or AWS_SKILL_IDENTIFIER_PATTERN.fullmatch(skill) is None
            or chain.get("credentials_inspected") is not False
            or chain.get("aws_account_accessed") is not False
            or not isinstance(refs, Sequence)
            or isinstance(refs, (str, bytes))
            or not refs
        ):
            raise PresentationError("invalid observed AWS Core attribution")
        skills.append(skill)
        for reference in refs:
            if (
                not isinstance(reference, str)
                or AWS_OFFICIAL_REFERENCE_PATTERN.fullmatch(reference) is None
            ):
                raise PresentationError("invalid observed AWS Core attribution")
            references.append(reference)
    skill_text = ", ".join(dict.fromkeys(skills))
    reference_text = ", ".join(dict.fromkeys(references))
    return (
        f"AWS Core returned {skill_text} for this decision and supplied "
        f"{reference_text}. No AWS account was accessed."
    )


def render_owner_update(
    report: Mapping[str, Any],
    *,
    updated: str = "Nothing.",
) -> str:
    """Render one concise non-receipt lifecycle update."""

    interaction = _interaction(report)
    if interaction.get("formal_receipt_required") is True:
        raise PresentationError("formal gate and AWS receipts use canonical receipt renderers")
    stage = str(interaction.get("owner_stage", ""))
    if stage not in {"DEFINE", "DESIGN", "DELIVER"}:
        raise PresentationError("invalid owner stage")
    reason = str(interaction.get("route_reason_code", ""))
    action_kind = str(interaction.get("owner_action_kind", ""))
    if reason not in STATUS_TEXT or reason not in NEXT_TEXT:
        raise PresentationError("unknown route reason code")
    if action_kind not in ACTION_TEXT:
        raise PresentationError("unknown owner action kind")
    required = interaction.get("owner_action_required") is True
    if required == (action_kind == "NONE_CONTINUE_AUTOMATICALLY"):
        raise PresentationError("owner action requirement conflicts with action kind")

    remediation_status, remediation_next = _remediation_text(report)
    status_text = remediation_status or _delivery_status(report, reason) or STATUS_TEXT[reason]
    next_text = (
        remediation_next or _delivery_next(report, reason)
        or _coverage_next(report, reason) or NEXT_TEXT[reason]
    )
    lines = [
        f"FASTLANE · {stage}",
        "",
        f"Status: {status_text}",
        f"Updated: {updated}",
        f"Need from you: {ACTION_TEXT[action_kind]}",
        f"Next: {next_text}",
    ]
    audit = _aws_core_audit(report, interaction)
    if audit is not None:
        lines.append(f"Audit: {audit}")
    reply = COPYABLE_REPLIES.get(action_kind)
    if required and reply:
        lines.extend(("", "Copyable reply:", reply))
    return "\n".join(lines)


def render_side_question_response(
    report: Mapping[str, Any],
    *,
    answer: str,
    project_state_changed: bool = False,
) -> str:
    """Answer directly, then restore the current deterministic owner action."""

    cleaned_answer = answer.strip()
    if not cleaned_answer:
        raise PresentationError("side-question answer must not be empty")
    interaction = _interaction(report)
    _remediation_status, remediation_next = _remediation_text(report)
    action_kind = str(interaction.get("owner_action_kind", ""))
    if action_kind not in ACTION_TEXT:
        raise PresentationError("unknown owner action kind")
    required = interaction.get("owner_action_required") is True
    if required == (action_kind == "NONE_CONTINUE_AUTOMATICALLY"):
        raise PresentationError("owner action requirement conflicts with action kind")
    lines = [
        cleaned_answer,
        "",
        "Project state changed: " + ("Yes." if project_state_changed else "No."),
        f"Pending next action: {ACTION_TEXT[action_kind]}",
    ]
    if not required:
        reason = str(interaction.get("route_reason_code", ""))
        if reason not in NEXT_TEXT:
            raise PresentationError("unknown route reason code")
        lines.append(f"Next: {remediation_next or NEXT_TEXT[reason]}")
    return "\n".join(lines)


def render_prerequisite_update(report: Mapping[str, Any]) -> str:
    """Render one prerequisite action with one consolidated owner checklist."""

    state = str(report.get("state", ""))
    if state == "PREREQUISITES_READY":
        raise PresentationError("ready prerequisites route to the welcome renderer")
    checklist = report.get("checklist")
    if not isinstance(checklist, Sequence) or isinstance(checklist, (str, bytes)):
        raise PresentationError("prerequisite report is missing its checklist")
    steps = [item for item in checklist if isinstance(item, Mapping)]
    if not steps:
        raise PresentationError("blocked prerequisites require at least one checklist step")
    lines = [
        "FASTLANE · PREREQUISITES",
        "",
        "Status: Required local setup is incomplete.",
        "Updated: Nothing.",
        "Need from you: Complete the checklist below, then send `init template` again.",
        "Next: Codex will verify everything together before asking project questions.",
        "",
        "Checklist:",
    ]
    for index, step in enumerate(steps, start=1):
        label = str(step.get("label", "Required step"))
        lines.append(f"{index}. {label}")
        grouped = any(
            key in step
            for key in (
                "install_commands",
                "action_commands",
                "verification_commands",
            )
        )
        if grouped:
            for heading, key in (
                ("Owner-run install", "install_commands"),
                ("Owner action", "action_commands"),
                ("Verify", "verification_commands"),
            ):
                commands = step.get(key, [])
                if isinstance(commands, Sequence) and not isinstance(
                    commands, (str, bytes)
                ):
                    for command in commands:
                        lines.append(f"   {heading}: `{command}`")
        else:
            commands = step.get("commands", [])
            if isinstance(commands, Sequence) and not isinstance(
                commands, (str, bytes)
            ):
                for command in commands:
                    lines.append(f"   `{command}`")
        guide = step.get("guide")
        if guide:
            lines.append(f"   Official guide: {guide}")
        instruction = step.get("instruction")
        if instruction:
            lines.append(f"   {instruction}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render Fastlane owner conversation from JSON on stdin"
    )
    parser.add_argument("mode", choices=("owner", "side-question"))
    parser.add_argument(
        "--input-stdin",
        action="store_true",
        help="Read one JSON object containing report and presentation fields",
    )
    args = parser.parse_args(argv)
    if not args.input_stdin:
        parser.error("--input-stdin is required")
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, Mapping):
            raise PresentationError("input must be a JSON object")
        report = payload.get("report")
        if not isinstance(report, Mapping):
            raise PresentationError("input is missing report")
        if args.mode == "owner":
            if "audit" in payload:
                raise PresentationError(
                    "audit text is derived from the doctor report, not caller prose"
                )
            output = render_owner_update(
                report,
                updated=str(payload.get("updated", "Nothing.")),
            )
        else:
            output = render_side_question_response(
                report,
                answer=str(payload.get("answer", "")),
                project_state_changed=payload.get("project_state_changed") is True,
            )
    except (json.JSONDecodeError, PresentationError) as exc:
        print(f"Fastlane presentation blocked: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
