"""Pure Design 9 validation bindings; declarations never grant execution authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace

from ..core.contracts import (
    _heading_section_lines,
    contract_table_after_heading,
    table_after_heading,
    without_fenced_code,
)
from ..core.ids import STABLE_CONTRACT_ID, explicit_value, parse_exact_id_list
from .models import ProjectDesignContract
from .support import (
    IAC_VALIDATION_HEADERS,
    IAC_VALIDATION_HEADING,
    IAC_VALIDATION_PATHS,
    valid_property_execution_command,
)

VALIDATION_CHECK_HEADING = "### Validation check bindings"
VALIDATION_CHECK_HEADERS = (
    "Check ID",
    "Obligation ID",
    "Stage",
    "Exact command",
    "Time limit seconds",
    "Evidence destination",
    "Expected result",
)
CHECK_ID = re.compile(r"CHECK-\d{3,}")
EVIDENCE_DESTINATION = re.compile(r"docs/project/VERIFY\.md#[a-z][a-z0-9-]*")


def source_expectation(cells) -> str:
    """Canonical JSON binds all source cells, including empty-string examples."""
    return json.dumps(list(cells), ensure_ascii=False, separators=(",", ":"))


def design9_surface_present(text: str) -> bool:
    structural = without_fenced_code(text)
    return bool(
        re.search(
            r"^### Validation check bindings\s*$|^[ \t]*\|\s*Check ID\s*\|",
            structural,
            re.MULTILINE,
        )
    )


def _iac_obligations(text: str, completion_target: str | None):
    table = contract_table_after_heading(
        text, IAC_VALIDATION_HEADING, IAC_VALIDATION_HEADERS
    )
    if table is None:
        raise ValueError("Design 9 requires IaC validation applicability")
    obligations = {}
    for path, applicability, tech, local, aws, destination in table.rows:
        if applicability != "APPLICABLE":
            continue
        path_index = IAC_VALIDATION_PATHS.index(path) + 1
        for kind, value, stages in (
            ("L", local, {"LOCAL_RELEASE"}),
            ("A", aws, {"AWS_READ", "AWS_MUTATION"}),
        ):
            if (
                kind == "A"
                and completion_target == "LOCAL"
                and value.startswith("NOT_APPLICABLE - ")
                and explicit_value(
                    value.removeprefix("NOT_APPLICABLE - "), allow_none=False
                )
            ):
                continue
            try:
                commands = json.loads(value)
            except (ValueError, RecursionError) as exc:
                raise ValueError(
                    f"{path}: validation requires a JSON array of exact commands"
                ) from exc
            if not isinstance(commands, list) or not 1 <= len(commands) <= 20:
                raise ValueError(f"{path}: declare one through twenty commands")
            if not all(
                isinstance(command, str) and valid_property_execution_command(command)
                for command in commands
            ):
                raise ValueError(f"{path}: each validation command must be concrete")
            if len(set(commands)) != len(commands):
                raise ValueError(f"{path}: duplicate validation commands")
            for index, command in enumerate(commands, 1):
                identifier = f"IAC-{kind}-{path_index:03d}{index:02d}"
                obligations[identifier] = (
                    source_expectation((path, tech, command)),
                    stages,
                    command,
                    destination,
                )
    return obligations


def validation_obligations(text: str, requirements, interfaces):
    """Bind one check to one complete canonical obligation; IDs alone are insufficient."""
    obligations = {
        identifier: (criterion, {"LOCAL_BUILD"}, None, None)
        for identifier, criterion in requirements.acceptance_criteria
    }
    details = requirements.requirements_v16.to_dict()
    for name, key in (("inputs", "Constraint ID"), ("quality_scenarios", "QAS ID")):
        for row in details.get(name, []):
            obligations[row[key]] = (
                source_expectation(row.values()),
                {"LOCAL_BUILD"},
                None,
                None,
            )
    for row in interfaces.rows if interfaces else ():
        obligations[row[0]] = (source_expectation(row), {"LOCAL_BUILD"}, None, None)
    obligations.update(_iac_obligations(text, requirements.completion_target))
    return obligations


def _check_row_issues(row, expected) -> list[str]:
    identifier, basis, stage, command, bound, destination, outcome = row
    expected_result, stages, exact_command, exact_destination = expected
    issues: list[str] = []
    if stage not in stages or outcome != expected_result:
        issues.append(
            f"{identifier}: stage and complete expected result must match {basis}"
        )
    if not valid_property_execution_command(command) or (
        exact_command is not None and command != exact_command
    ):
        issues.append(
            f"{identifier}: exact command must match the applicable source obligation"
        )
    if re.fullmatch(r"[1-9]\d{0,4}", bound) is None or int(bound) > 86400:
        issues.append(f"{identifier}: time limit must be 1 through 86400 seconds")
    if EVIDENCE_DESTINATION.fullmatch(destination) is None or (
        exact_destination is not None and destination != exact_destination
    ):
        issues.append(
            f"{identifier}: evidence destination must match the applicable VERIFY section"
        )
    return issues


def _check_issues(rows, obligations) -> list[str]:
    issues: list[str] = []
    if [row[0] for row in rows] != sorted({row[0] for row in rows}):
        issues.append("Validation checks require sorted unique IDs")
    covered: set[str] = set()
    for row in rows:
        identifier, basis = row[:2]
        expected = obligations.get(basis)
        if CHECK_ID.fullmatch(identifier) is None or expected is None:
            issues.append(f"{identifier}: invalid check or unknown obligation {basis}")
            continue
        issues.extend(_check_row_issues(row, expected))
        covered.add(basis)
    if set(obligations) - covered:
        issues.append(
            "Missing validation obligations: "
            + ", ".join(sorted(set(obligations) - covered))
        )
    return issues


def _interface_issues(interfaces, inputs) -> list[str]:
    issues: list[str] = []
    for row in interfaces.rows if interfaces else ():
        basis = set(parse_exact_id_list(row[2], STABLE_CONTRACT_ID, row[0]))
        required = sorted(
            identifier
            for identifier, requirements in inputs.items()
            if basis & requirements
        )
        if required and row[8] != ", ".join(required):
            issues.append(
                f"{row[0]}: Input validation must bind exactly {', '.join(required)}"
            )
        if not required and not (
            row[8].startswith("NONE: ") and explicit_value(row[8][6:], allow_none=False)
        ):
            issues.append(
                f"{row[0]}: no-input validation needs a concrete NONE disposition"
            )
    return issues


def _check_table(text: str):
    table = contract_table_after_heading(
        text, VALIDATION_CHECK_HEADING, VALIDATION_CHECK_HEADERS
    )
    section = _heading_section_lines(text, VALIDATION_CHECK_HEADING)
    if table is None or section is None:
        raise ValueError("Design 9 requires Validation check bindings")
    lines = section[1]
    starts = sum(
        line.strip().startswith("|")
        and (i == 0 or not lines[i - 1].strip().startswith("|"))
        for i, line in enumerate(lines)
    )
    if starts != 1:
        raise ValueError("Validation check bindings requires exactly one table")
    return table


def bind_design9_project(
    text: str, project: ProjectDesignContract, requirements, interfaces
):
    document = table_after_heading(text, "## Document status")
    if document.get("Project design contract schema") != "9":
        return project, []
    issues: list[str] = []
    if requirements.schema_version != "1.6" or requirements.status != "READY":
        issues.append("Design 9 requires a complete Requirements 1.6 contract")
    checks = ()
    canonical = b""
    try:
        inputs = {
            row["Constraint ID"]: set(
                parse_exact_id_list(
                    row["Requirement IDs"], STABLE_CONTRACT_ID, row["Constraint ID"]
                )
            )
            for row in requirements.requirements_v16.to_dict().get("inputs", [])
        }
        issues.extend(_interface_issues(interfaces, inputs))
        obligations = validation_obligations(text, requirements, interfaces)
        table = _check_table(text)
        checks, canonical = table.rows, table.canonical_bytes
        issues.extend(_check_issues(checks, obligations))
    except (ValueError, TypeError) as exc:
        issues.append(str(exc))
    prefix = b"PROJECT_DESIGN_CONTRACT_SCHEMA: 8\n"
    payload, digest = None, None
    if project.canonical_bytes is None or not project.canonical_bytes.startswith(
        prefix
    ):
        issues.append(
            "Design 9 requires the complete canonical base Design representation"
        )
    else:
        payload = (
            b"PROJECT_DESIGN_CONTRACT_SCHEMA: 9\n"
            + project.canonical_bytes[len(prefix) :]
            + canonical
        )
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return replace(
        project,
        schema_version=9,
        status="BLOCKED" if issues else project.status,
        validation_checks=checks,
        acceptance_criteria=requirements.acceptance_criteria,
        canonical_bytes=payload,
        canonical_sha256=digest,
    ), issues


def bind_approved_schema8(
    text: str, project: ProjectDesignContract, digest: str | None, approved: bool
):
    if project.schema_version != 8:
        return project, []
    try:
        stored = table_after_heading(text, "## 28. Construction envelope").get(
            "Design contract SHA-256"
        )
    except ValueError:
        stored = None
    if (
        approved
        and project.status == "READY"
        and digest is not None
        and stored == digest
        and not design9_surface_present(text)
    ):
        return project, []
    return replace(project, status="MIGRATION_REQUIRED"), [
        "PROJECT_DESIGN_SCHEMA_MIGRATION_REQUIRED: Design 8 remains compatible only with its exact approved aggregate digest and no Design 9 surfaces; migrate to schema 9"
    ]
