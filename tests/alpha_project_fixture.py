def complete_alpha_requirements(text: str, requirement_ids: list[str]) -> str:
    from scripts.fastlane_engine.define.requirements_v16 import (
        DETAIL_HEADERS,
        RECOVERY_HEADERS,
        SCENARIO_HEADERS,
        APPLICABILITY_HEADERS,
        INPUT_HEADERS,
    )
    from tests.test_bootstrap_doctor import replace_contract_table

    text = text.replace(
        "| FR-001 | TODO | UBIQUITOUS | AC-FR-001 | TODO | MEASURABLE |",
        "| FR-001 | The application SHALL display the current approved project outcome. | UBIQUITOUS | AC-FR-001 | A rendered-output test confirms the approved outcome is displayed. | MEASURABLE |",
    )
    text = text.replace(
        "| FR-002 | TODO | UNWANTED_BEHAVIOR | AC-FR-002 | TODO | GHERKIN |",
        "| FR-002 | IF input violates approved constraints, THEN the application SHALL reject it without changing approved state. | UNWANTED_BEHAVIOR | AC-FR-002 | GIVEN input outside approved constraints, WHEN the application receives it, THEN the input is rejected and approved state is unchanged. | GHERKIN |",
    )
    text = text.replace(
        "| QAS-001 | TODO | TODO | TODO | TODO | TODO | TODO | TODO |",
        "| QAS-001 | REL-004 | Operator | Primary data store becomes unavailable | Development recovery rehearsal | Durable data store | Restore the latest approved backup | A timed restore rehearsal meets RTO 60 minutes and RPO 15 minutes. |",
    )
    text = text.replace(
        "WHERE durable recovery applies, the service SHALL restore data within the approved recovery objectives.",
        "WHERE fixture recreation applies, the service SHALL recreate synthetic records within the approved recovery objectives.",
    )
    text = text.replace(
        "A timed restore rehearsal meets the current RTO and RPO, or the requirement records why durable recovery does not apply.",
        "A timed fixture recreation rehearsal meets the approved RTO and RPO.",
    )
    text = text.replace(
        "WHERE durable recovery applies, the service SHALL restore within the approved RTO and RPO.",
        "WHERE fixture recreation applies, the service SHALL recreate synthetic records within the approved RTO and RPO.",
    )
    text = text.replace(
        "A timed restore rehearsal meets the approved RTO and RPO.",
        "A timed fixture recreation rehearsal meets the approved RTO and RPO.",
    )
    text = text.replace(
        "Recreate from source fixtures; no backup promise",
        "RECREATE: Regenerate synthetic records from the versioned local fixture",
    )
    text = text.replace(
        "DATA-001, DATA-002, DATA-003, DATA-004, DATA-005 |",
        "DATA-001, DATA-002, DATA-003, DATA-004, DATA-005, REL-004 |",
    )
    text = text.replace(
        "Restore the latest approved backup",
        "RECREATE: Regenerate synthetic records from the versioned local fixture",
    )
    text = text.replace(
        "A timed restore rehearsal meets RTO 60 minutes and RPO 15 minutes.",
        "RTO 60 minutes and RPO 0 minutes",
    )
    rows = {
        RECOVERY_HEADERS: [
            (
                "DATASET-001",
                "DATA-004, REL-004",
                "QAS-001",
                "RECREATE",
                "60",
                "0",
                "Synthetic records are regenerated from versioned fixtures; no backup is promised",
            )
        ],
        SCENARIO_HEADERS: [
            (
                "QAS-001",
                "RECOVERY",
                "DATASET-001",
                "Synthetic record regeneration exercises the declared recovery objective",
            )
        ],
        APPLICABILITY_HEADERS: [
            (
                identifier,
                "INPUT-001" if identifier == "FR-002" else "NONE",
                "Validates the request outcome enum"
                if identifier == "FR-002"
                else "This requirement adds no external input field",
            )
            for identifier in requirement_ids
        ],
        INPUT_HEADERS: [
            (
                "INPUT-001",
                "FR-002",
                "Request outcome selector",
                "ENUM",
                "NOT_APPLICABLE",
                "NOT_APPLICABLE",
                '["current", "previous"]',
                '"current"',
                '"unknown"',
                "Reject the request without changing approved state",
            )
        ],
    }
    for headers, heading in DETAIL_HEADERS.items():
        if heading not in text:
            table = "\n".join(
                [
                    heading,
                    "",
                    "| " + " | ".join(headers) + " |",
                    "|" + "---|" * len(headers),
                ]
            )
            text = (
                text.replace(
                    "## 13. Cross-requirement analysis",
                    table + "\n\n## 13. Cross-requirement analysis",
                )
                if "## 13. Cross-requirement analysis" in text
                else text + "\n\n" + table + "\n\n"
            )
        text = replace_contract_table(text, heading, headers, rows[headers])
    return text


def complete_alpha_design(text: str) -> str:
    import json
    from scripts import bootstrap_doctor as doctor
    from tests.test_bootstrap_doctor import put_contract_table, replace_contract_table

    # Expectations come directly from independently declared fixture records,
    # never from the production validation-obligation builder.
    normative = [
        row
        for table in doctor.markdown_tables(text)
        if tuple(table[0]) == doctor.NORMATIVE_REQUIREMENT_HEADERS
        for row in table[2:]
    ]
    obligations = {
        row[3]: (
            row[4],
            "python -m unittest",
            "LOCAL_BUILD",
            "docs/project/VERIFY.md#task-completion-evidence",
        )
        for row in normative
    }
    for headers, key in (("Constraint ID", 0), ("QAS ID", 0), ("Contract ID", 0)):
        for table in doctor.markdown_tables(text):
            if table[0][0] == headers and len(table[0]) in {10, 8, 16}:
                for row in table[2:]:
                    obligations[row[key]] = (
                        json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                        "python -m unittest",
                        "LOCAL_BUILD",
                        "docs/project/VERIFY.md#task-completion-evidence",
                    )
    iac = doctor.contract_table_after_heading(
        text, doctor.IAC_VALIDATION_HEADING, doctor.IAC_VALIDATION_HEADERS
    )
    assert iac is not None
    rows = [tuple(row) for row in iac.rows]
    first = rows[0]
    local = "sam validate --lint --template-file infrastructure/template.yaml"
    aws = "aws cloudformation describe-change-set --change-set-name synthetic-plan --region us-west-2"
    rows[0] = (*first[:3], json.dumps([local]), json.dumps([aws]), first[5])
    text = replace_contract_table(
        text, doctor.IAC_VALIDATION_HEADING, doctor.IAC_VALIDATION_HEADERS, rows
    )
    for identifier, command, stage in (
        ("IAC-L-00101", local, "LOCAL_RELEASE"),
        ("IAC-A-00101", aws, "AWS_READ"),
    ):
        obligations[identifier] = (
            json.dumps([first[0], first[2], command], separators=(",", ":")),
            command,
            stage,
            first[5],
        )
    headers = (
        "Check ID",
        "Obligation ID",
        "Stage",
        "Exact command",
        "Time limit seconds",
        "Evidence destination",
        "Expected result",
    )
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for index, (identifier, (expected, command, stage, destination)) in enumerate(
        sorted(obligations.items()), 1
    ):
        row = (
            f"CHECK-{index:03d}",
            identifier,
            stage,
            command,
            "120",
            destination,
            expected,
        )
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    return put_contract_table(
        text,
        "### Validation check bindings",
        "\n".join(lines),
        "## 23. Example-based scenarios",
    )


def no_persistent_data_details(text: str) -> str:
    """Independently declare a no-data fixture, including its non-recovery scenario."""
    from scripts.fastlane_engine.define.requirements_v16 import (
        RECOVERY_HEADING,
        RECOVERY_HEADERS,
        SCENARIO_HEADING,
        SCENARIO_HEADERS,
        QAS_HEADING,
        QAS_HEADERS,
    )
    from tests.test_bootstrap_doctor import replace_contract_table

    text = replace_contract_table(
        text,
        RECOVERY_HEADING,
        RECOVERY_HEADERS,
        [("NO PERSISTENT DATA", *("NONE",) * 6)],
    )
    text = replace_contract_table(
        text,
        SCENARIO_HEADING,
        SCENARIO_HEADERS,
        [("QAS-001", "OTHER", "NONE", "Availability uses no persistent data")],
    )
    return replace_contract_table(
        text,
        QAS_HEADING,
        QAS_HEADERS,
        [
            (
                "QAS-001",
                "FR-001",
                "User",
                "Requests current output",
                "Local synthetic run",
                "Rendered response",
                "Display the approved outcome",
                "The local response meets the approved 2 second limit.",
            )
        ],
    )


def bind_alpha_task_checks(prd: str, tasks_text: str) -> str:
    """Give current-project task fixtures the exact independently declared check plan."""
    import re
    from scripts import bootstrap_doctor as doctor

    table = doctor.contract_table_after_heading(
        prd,
        "### Validation check bindings",
        (
            "Check ID",
            "Obligation ID",
            "Stage",
            "Exact command",
            "Time limit seconds",
            "Evidence destination",
            "Expected result",
        ),
    )
    if table is None:
        return tasks_text
    rows = [row for row in table.rows if row[2] == "LOCAL_BUILD"]
    projection = "\n".join(
        [
            "| " + " | ".join(table.headers) + " |",
            "|" + "---|" * len(table.headers),
            *(
                "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |"
                for row in rows
            ),
        ]
    )
    chunks = re.split(r"(?m)(?=^### TASK-\d+)", tasks_text)
    for i, block in enumerate(chunks):
        if not block.startswith("### TASK-") or "#### Validation" not in block:
            continue
        match = re.search(r"(?m)^- Requirements: `([^`]+)`", block)
        referenced = set(
            re.findall(r"[A-Z]+(?:-[A-Z]+)*-\d+", match[1] if match else "")
        )
        acceptance = "\n".join(
            f"- [ ] {row[1]}: {row[6]} [CHECK: {row[0]}]"
            for row in rows
            if row[1].startswith("AC-") and row[1].removeprefix("AC-") in referenced
        )
        block = block.replace(
            "#### Acceptance criteria\n",
            "#### Acceptance criteria\n\n" + acceptance + "\n",
            1,
        )
        commands = "\n".join(sorted({row[3] for row in rows}))
        block = block.replace(
            "#### Validation\n",
            "#### Validation\n\n" + projection + "\n\n```bash\n" + commands + "\n```\n",
            1,
        )
        chunks[i] = block
    return "".join(chunks)
