"""Pure source-bound validation explanations; no route or authority changes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .core.contracts import contract_table_after_heading, table_after_heading
from .core.snapshot import ProjectSnapshot
from .define.requirements import QAS_HEADERS
from .define.requirements_v15 import DATASET_HEADERS, DATASET_HEADING
from .deliver.evidence import fenced_command_lines, parse_task_completion_evidence
from .deliver.tasks import inspect_task_blocks, inspect_task_sections
from .design import (
    HARNESS_HEADING,
    IAC_VALIDATION_HEADERS,
    IAC_VALIDATION_HEADING,
    INTERFACE_HEADERS,
    INTERFACE_HEADING,
    PROPERTY_EXECUTION_HEADING,
    command_matches_prefix,
    parse_command_prefixes,
)
from .design.contract_v9 import VALIDATION_CHECK_HEADING
from .evaluation import EngineEvaluation, freeze_evaluation_value

PRD = "docs/project/PRD.md"
TASKS = "docs/project/TASKS.md"
VERIFY = "docs/project/VERIFY.md"


@dataclass(frozen=True)
class ValidationExplanation:
    values: Mapping[str, Any]

    def __post_init__(self):
        object.__setattr__(self, "values", freeze_evaluation_value(self.values))


def _text(snapshot: ProjectSnapshot, path: str) -> str:
    source = snapshot.file(path)
    return source.canonical_text or "" if source else ""


def _locator(snapshot: ProjectSnapshot, path: str, heading: str, identifier: str = ""):
    source = snapshot.file(path)
    if source is None:
        return {"path": path, "heading": heading, "status": "UNOBSERVED"}
    lines = (source.presentation_text or "").splitlines()
    matches = [index + 1 for index, line in enumerate(lines) if line.strip() == heading]
    if identifier:
        row_matches = [
            index + 1
            for index, line in enumerate(lines)
            if re.match(r"^[ \t]*\|[ \t]*" + re.escape(identifier) + r"[ \t]*\|", line)
        ]
        if len(row_matches) == 1:
            matches = row_matches
    return {
        "path": path,
        "heading": heading,
        "identifier": identifier,
        "line": matches[0] if len(matches) == 1 else None,
        "source_sha256": "sha256:" + source.byte_sha256,
    }


def _declarations(snapshot: ProjectSnapshot, text: str, errors: list[str]):
    result = {}
    for name, heading, headers in (
        ("iac", IAC_VALIDATION_HEADING, IAC_VALIDATION_HEADERS),
        ("interfaces", INTERFACE_HEADING, INTERFACE_HEADERS),
        ("datasets", DATASET_HEADING, DATASET_HEADERS),
        ("quality_scenarios", "### Quality attribute scenarios", QAS_HEADERS),
    ):
        try:
            table = contract_table_after_heading(text, heading, headers)
            result[name] = (
                [
                    {
                        "values": dict(zip(headers, row)),
                        "source": _locator(snapshot, PRD, heading, row[0]),
                    }
                    for row in table.rows
                ]
                if table
                else []
            )
        except ValueError as exc:
            errors.append(str(exc))
            result[name] = []
    return result


def _design_checks(snapshot: ProjectSnapshot, design: Mapping[str, Any]):
    result = []
    for row in design.get("project_contract", {}).get("validation_checks", ()):
        result.append(
            {
                "id": row[0],
                "kind": "SPECIFICATION",
                "basis": row[1],
                "stage": row[2],
                "command": row[3],
                "time_limit_seconds": row[4],
                "evidence_destination": row[5],
                "expected_result": row[6],
                "source": _locator(snapshot, PRD, VALIDATION_CHECK_HEADING, row[0]),
            }
        )
    for row in design.get("property_execution", ()):
        result.append(
            {
                "id": row["property_id"],
                "kind": "PROPERTY",
                "stage": "LOCAL_BUILD",
                "command": row["exact_command"],
                "run_target_time_bound": row["run_target_time_bound"],
                "seed_or_reproduction_format": row["seed_or_reproduction_format"],
                "evidence_destination": row["evidence_destination"],
                "source": _locator(
                    snapshot, PRD, PROPERTY_EXECUTION_HEADING, row["property_id"]
                ),
            }
        )
    harness = design.get("harness", {})
    for row in harness.get("rows", ()):
        if row["harness_id"] not in harness.get("required_ids", ()):
            continue
        result.append(
            {
                "id": row["harness_id"],
                "kind": "PROFILE",
                "stage": "DECLARED_PROFILE_TRIGGER",
                "trigger": row["trigger"],
                "basis": row["basis_ids"],
                "command": row["exact_command"],
                "evidence_destination": row["evidence_destination"],
                "source": _locator(snapshot, PRD, HARNESS_HEADING, row["harness_id"]),
            }
        )
    return result


def _task_checks(snapshot: ProjectSnapshot, evaluation: EngineEvaluation):
    result = []
    state = evaluation.deliver.get("tasks", {})
    for task in inspect_task_blocks(_text(snapshot, TASKS)):
        sections, duplicates = inspect_task_sections(task.block)
        if duplicates:
            continue
        for index, command in enumerate(
            fenced_command_lines(sections.get("Validation", "")), 1
        ):
            result.append(
                {
                    "id": f"{task.task_id}/command-{index}",
                    "kind": "TASK",
                    "stage": "LOCAL_BUILD",
                    "command": command,
                    "task_id": task.task_id,
                    "task_status": task.status,
                    "selected_task_state": "ACTIVE"
                    if task.task_id in state.get("active_ids", ())
                    else "READY"
                    if task.task_id in state.get("ready_ids", ())
                    else "OTHER",
                    "evidence_destination": "docs/project/VERIFY.md#task-completion-evidence",
                    "source": _locator(
                        snapshot, TASKS, f"### {task.task_id} — {task.title}"
                    ),
                }
            )
    return result


def _recorded_evidence(text: str, errors: list[str]):
    try:
        rows = parse_task_completion_evidence(text)
    except ValueError as exc:
        errors.append(str(exc))
        return {}
    result = {}
    for row in rows:
        result.setdefault(row.command_or_observation, []).append(
            {
                "evidence_id": row.evidence_id,
                "status": row.status,
                "observed_at": row.observed_at,
                "artifact": row.commit_worktree_artifact,
                "durable_source": row.durable_source,
                "qualification": "RECORDED_CLAIM_REQUIRES_CURRENT_BASIS_VALIDATION",
            }
        )
    return result


def derive_validation_explanation(
    snapshot: ProjectSnapshot, evaluation: EngineEvaluation
) -> ValidationExplanation:
    """Use one observed snapshot and its unchanged Engine decision."""
    errors: list[str] = []
    prd = _text(snapshot, PRD)
    try:
        envelope = table_after_heading(prd, "## 28. Construction envelope")
        prefixes = parse_command_prefixes(envelope.get("Local command boundary", ""))
    except ValueError as exc:
        errors.append(str(exc))
        envelope, prefixes = {}, []
    design = evaluation.design.get("design_contract", {})
    checks = [*_design_checks(snapshot, design), *_task_checks(snapshot, evaluation)]
    evidence = _recorded_evidence(_text(snapshot, VERIFY), errors)
    for check in checks:
        command = check["command"]
        check["declared_local_prefix_match"] = any(
            command_matches_prefix(command, prefix) for prefix in prefixes
        )
        check["requires_separate_aws_authority"] = check["stage"].startswith("AWS_")
        check["recorded_evidence"] = evidence.get(command, [])
        check["execution_performed"] = False
    declarations = _declarations(snapshot, prd, errors)
    return ValidationExplanation(
        {
            "schema_version": 1,
            "kind": "VALIDATION_EXPLANATION",
            "engine_ok": evaluation.ok,
            "status": "INCOMPLETE" if errors else "SOURCE_BOUND",
            "requirements_digest": evaluation.define.get(
                "requirements_contract", {}
            ).get("canonical_sha256"),
            "design_digest": design.get("canonical_sha256"),
            "checks": checks,
            "source_drivers": declarations,
            "input_recovery_details": evaluation.define.get(
                "requirements_contract", {}
            ).get("requirements_v16", {}),
            "coverage_plan": evaluation.define.get("coverage_plan", {}),
            "declared_command_boundary": envelope.get("Local command boundary"),
            "permission_conflicts": [
                check["id"]
                for check in checks
                if not check["declared_local_prefix_match"]
                and not check["requires_separate_aws_authority"]
            ],
            "authority": evaluation.authority,
            "evidence_state": evaluation.deliver.get("evidence_state"),
            "route": evaluation.route,
            "interaction": evaluation.interaction,
            "limitations": [
                "A declared command-prefix match is only one boundary check, not permission to execute.",
                "Current Engine authority, task scope, dependency policy, hooks, and external receipts still apply.",
                "Recorded evidence is reported with provenance; this explanation executes no checks and does not requalify historical results.",
                "Legacy prose obligations retain their exact source details; missing exact commands or bounds are not invented.",
            ],
            "errors": errors,
        }
    )
