"""Owner-grounded intake evaluation for Fastlane Define.

Canonical input is the current PRD intake foundation, normalized response
register, and current decision card. The module returns immutable projections
and ordered issues. It performs no I/O, writes, routing, approval, authorization,
or owner-facing rendering and preserves the characterized compatibility contract.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

from ..core.contracts import ContractTable, contract_table_after_heading
from ..core.ids import canonical_id_list, clean_cell, explicit_value
from .models import (
    IntakeCard,
    IntakeFoundationContract,
    IntakeQuestion,
    NormalizedOwnerResponse,
)

try:
    from ...intake_response import intake_detail_safety_code, intake_reply_token
except ImportError:  # Imported directly with scripts/ on sys.path.
    from intake_response import intake_detail_safety_code, intake_reply_token


PROJECT_MODES = {"greenfield", "brownfield"}
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


def _intake_required_detail(value: str, kind: str) -> tuple[str, ...]:
    cleaned = clean_cell(value)
    if cleaned == "NONE":
        return ()
    if kind == "FACT":
        if cleaned != "RESPONSE":
            raise ValueError("FACT questions require detail for RESPONSE")
        return ("RESPONSE",)
    if cleaned == "RESPONSE":
        raise ValueError("DECISION questions require detail for A, B, or C")
    keys = [item.strip() for item in cleaned.split(",")]
    if (
        not keys
        or any(key not in {"A", "B", "C"} for key in keys)
        or len(keys) != len(set(keys))
        or cleaned != ", ".join(keys)
    ):
        raise ValueError(
            "Required detail for must be NONE or comma-space-separated A/B/C keys"
        )
    return tuple(keys)


def _intake_owner_reply_example(questions: list[IntakeQuestion]) -> str:
    replies: list[str] = []
    for question in questions:
        if question.kind == "FACT":
            replies.append(f"{question.reply_key}: <your answer>")
            continue
        if question.recommended is None:
            replies.append(f"{question.reply_key}: <choose A, B, or C>")
            continue
        choice = question.recommended
        reply = f"{question.reply_key}{choice}"
        if choice in question.required_detail_for:
            reply += ": <required detail>"
        replies.append(reply)
    return "; ".join(replies)


def _intake_reply_example(questions: list[IntakeQuestion], reply_token: str) -> str:
    return reply_token + "; " + _intake_owner_reply_example(questions)


def _parse_intake_response_register(
    table: ContractTable,
    expected_foundation_rows: Mapping[str, str],
    issues: list[tuple[str, str]],
) -> tuple[NormalizedOwnerResponse, ...]:
    """SAFETY: Parse owner responses in the canonical diagnostic order.

    Message identity and provenance binding remain cohesive so malformed or
    replayed responses continue to fail closed with byte-compatible issues.
    """
    responses: list[NormalizedOwnerResponse] = []
    seen_question_rows: set[tuple[str, str]] = set()
    seen_reply_rows: set[tuple[str, str]] = set()
    seen_presented_questions: set[tuple[str, int, str]] = set()
    message_identities: dict[str, tuple[str, int, str]] = {}
    response_numbers: set[int] = set()
    for raw in table.rows:
        (
            owner_response_id,
            card_id,
            revision_text,
            presented_card_digest,
            reply_key,
            question_id,
            selection,
            selection_detail,
            basis_value,
        ) = raw
        valid = True
        if OWNER_RESPONSE_ID.fullmatch(owner_response_id) is None:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"Invalid owner response ID {owner_response_id!r}",
                )
            )
            valid = False
        else:
            response_numbers.add(int(owner_response_id.rsplit("-", 1)[1]))
        if INTAKE_CARD_ID.fullmatch(card_id) is None:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid card ID",
                )
            )
            valid = False
        try:
            revision = int(revision_text)
            if revision < 1 or str(revision) != revision_text:
                raise ValueError
        except ValueError:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid revision",
                )
            )
            revision = 0
            valid = False
        if re.fullmatch(r"sha256:[0-9a-f]{64}", presented_card_digest) is None:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid presented-card digest",
                )
            )
            valid = False
        if reply_key not in {"1", "2", "3"}:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid reply key",
                )
            )
            valid = False
        if INTAKE_QUESTION_ID.fullmatch(question_id) is None:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid question ID",
                )
            )
            valid = False
        if selection not in {"A", "B", "C", "RESPONSE"}:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has an invalid selection",
                )
            )
            valid = False
        if selection_detail != "NONE" and not explicit_value(
            selection_detail, allow_none=False
        ):
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has unresolved selection detail",
                )
            )
            valid = False
        detail_safety = (
            None
            if selection_detail == "NONE"
            else intake_detail_safety_code(selection_detail)
        )
        if detail_safety is not None:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has unsafe or placeholder selection detail",
                )
            )
            valid = False
        if selection == "RESPONSE" and (
            selection_detail == "NONE" or detail_safety is not None
        ):
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} requires concrete factual detail",
                )
            )
            valid = False
        try:
            basis_ids = tuple(
                canonical_id_list(
                    basis_value, INTAKE_ID, f"{owner_response_id} Basis IDs"
                )
            )
            if not set(basis_ids).issubset(expected_foundation_rows):
                raise ValueError("Basis IDs must cite canonical intake foundation rows")
        except ValueError as exc:
            issues.append(
                ("INTAKE_RESPONSE_REGISTER_INVALID", f"{owner_response_id}: {exc}")
            )
            basis_ids = ()
            valid = False
        question_key = (owner_response_id, question_id)
        reply_key_pair = (owner_response_id, reply_key)
        if question_key in seen_question_rows or reply_key_pair in seen_reply_rows:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} has a duplicate normalized answer",
                )
            )
            valid = False
        seen_question_rows.add(question_key)
        seen_reply_rows.add(reply_key_pair)
        presented_question = (card_id, revision, question_id)
        if presented_question in seen_presented_questions:
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} repeats an answer to one presented question",
                )
            )
            valid = False
        seen_presented_questions.add(presented_question)
        identity = (card_id, revision, presented_card_digest)
        if (
            owner_response_id in message_identities
            and message_identities[owner_response_id] != identity
        ):
            issues.append(
                (
                    "INTAKE_RESPONSE_REGISTER_INVALID",
                    f"{owner_response_id} mixes card identities",
                )
            )
            valid = False
        message_identities[owner_response_id] = identity
        if valid:
            responses.append(
                NormalizedOwnerResponse(
                    owner_response_id=owner_response_id,
                    card_id=card_id,
                    revision=revision,
                    presented_card_digest=presented_card_digest,
                    reply_key=reply_key,
                    question_id=question_id,
                    selection=selection,
                    selection_detail=(
                        None if selection_detail == "NONE" else selection_detail
                    ),
                    basis_ids=basis_ids,
                )
            )
    if response_numbers and sorted(response_numbers) != list(
        range(1, max(response_numbers) + 1)
    ):
        issues.append(
            (
                "INTAKE_RESPONSE_REGISTER_INVALID",
                "Owner response IDs must be monotonic without gaps",
            )
        )
    return tuple(responses)


def _load_intake_tables(
    text: str,
    repository_mode_value: str | None,
    grandfather_current_gate_a: bool,
) -> tuple[
    tuple[ContractTable, ContractTable, ContractTable] | None,
    tuple[IntakeFoundationContract, list[tuple[str, str]]] | None,
]:
    """COMPATIBILITY: Load or migrate the three exact intake tables together."""

    try:
        foundation_table = contract_table_after_heading(
            text, INTAKE_FOUNDATION_HEADING, INTAKE_FOUNDATION_HEADERS
        )
        response_table = contract_table_after_heading(
            text, INTAKE_RESPONSE_REGISTER_HEADING, INTAKE_RESPONSE_REGISTER_HEADERS
        )
        card_table = contract_table_after_heading(
            text, INTAKE_CARD_HEADING, INTAKE_CARD_HEADERS
        )
    except ValueError as exc:
        try:
            legacy_foundation = contract_table_after_heading(
                text, INTAKE_FOUNDATION_HEADING, LEGACY_INTAKE_FOUNDATION_HEADERS
            )
            legacy_card = contract_table_after_heading(
                text, INTAKE_CARD_HEADING, INTAKE_CARD_HEADERS
            )
            legacy_response = contract_table_after_heading(
                text,
                INTAKE_RESPONSE_REGISTER_HEADING,
                INTAKE_RESPONSE_REGISTER_HEADERS,
            )
        except ValueError:
            legacy_foundation = legacy_card = legacy_response = None
        if (
            legacy_foundation is not None
            and legacy_card is not None
            and legacy_response is None
        ):
            if grandfather_current_gate_a:
                return None, (
                    IntakeFoundationContract(
                        status="READY_FOR_REQUIREMENTS",
                        repository_mode=repository_mode_value,
                        grandfathered_approved_gate_a=True,
                    ),
                    [],
                )
            return None, (
                IntakeFoundationContract(
                    status="FOUNDATION_REQUIRED",
                    repository_mode=repository_mode_value,
                    missing_fields=tuple(
                        field for _identifier, field in INTAKE_FOUNDATION_FIELDS
                    ),
                ),
                [
                    (
                        "INTAKE_CONTRACT_MIGRATION_REQUIRED",
                        "Unapproved legacy intake requires owner-response provenance and the normalized response register; retain legacy values only as unconfirmed context, reopen affected facts, and present the smallest current owner card without synthesizing historical OWNER-MSG records",
                    )
                ],
            )
        return None, (
            IntakeFoundationContract(
                status="BLOCKED", repository_mode=repository_mode_value
            ),
            [("INTAKE_FOUNDATION_INVALID", str(exc))],
        )

    if foundation_table is None and response_table is None and card_table is None:
        if grandfather_current_gate_a:
            return None, (
                IntakeFoundationContract(
                    status="READY_FOR_REQUIREMENTS",
                    repository_mode=repository_mode_value,
                    grandfathered_approved_gate_a=True,
                ),
                [],
            )
        return None, (
            IntakeFoundationContract(
                status="FOUNDATION_REQUIRED",
                repository_mode=repository_mode_value,
                missing_fields=tuple(
                    field for _identifier, field in INTAKE_FOUNDATION_FIELDS
                ),
            ),
            [
                (
                    "INTAKE_CONTRACT_MIGRATION_REQUIRED",
                    "Unapproved initialized projects require the intake foundation, normalized response register, and current decision card",
                )
            ],
        )
    if foundation_table is None or response_table is None or card_table is None:
        missing_records = ", ".join(
            name
            for name, table in (
                ("intake foundation", foundation_table),
                ("normalized response register", response_table),
                ("current decision card", card_table),
            )
            if table is None
        )
        return None, (
            IntakeFoundationContract(
                status="FOUNDATION_REQUIRED",
                repository_mode=repository_mode_value,
                missing_fields=tuple(
                    field for _identifier, field in INTAKE_FOUNDATION_FIELDS
                ),
            ),
            [
                (
                    "INTAKE_CONTRACT_MIGRATION_REQUIRED",
                    "Unapproved project is missing: " + missing_records,
                )
            ],
        )
    return (foundation_table, response_table, card_table), None


def _current_understanding(
    owner_work_context: str | None,
    observed_rows: dict[str, tuple[str, str, str, str]],
) -> tuple[str, ...]:
    """COMPATIBILITY: Render the established ordered intake understanding."""

    confirmed_values = {
        field_name: value
        for field_name, value, status, _owner_response in observed_rows.values()
        if status == "CONFIRMED"
    }
    result: list[str] = []
    context_summary = {
        "NEW_APPLICATION": "Starting point: a new application.",
        "EXISTING_APPLICATION_CHANGE": (
            "Starting point: a change to an existing application."
        ),
        "REPAIR_OR_MIGRATION": "Starting point: a repair, replacement, or migration.",
    }.get(owner_work_context)
    if context_summary is not None:
        result.append(context_summary)
    users = confirmed_values.get("PRIMARY_USERS")
    problem = confirmed_values.get("OWNER_STATED_PROBLEM")
    if users and problem:
        result.append(f"Users and problem: {users} — {problem}")
    elif users:
        result.append(f"Users: {users}")
    elif problem:
        result.append(f"Problem: {problem}")
    outcome = confirmed_values.get("OBSERVABLE_OUTCOME")
    boundary = confirmed_values.get("FIRST_RELEASE_BOUNDARY")
    if outcome and boundary:
        result.append(f"First useful outcome and release: {outcome} — {boundary}")
    elif outcome:
        result.append(f"First useful outcome: {outcome}")
    elif boundary:
        result.append(f"First release: {boundary}")
    success = confirmed_values.get("SUCCESS_MEASURE")
    audience = confirmed_values.get("RELEASE_AUDIENCE")
    if success and audience:
        result.append(f"Success and first audience: {success} — {audience}")
    elif success:
        result.append(f"Success measure: {success}")
    elif audience:
        result.append(f"First audience: {audience}")
    boundaries = [
        value
        for value in (
            confirmed_values.get("DATA_TYPES"),
            confirmed_values.get("DATA_SENSITIVITY"),
            confirmed_values.get("OPERATING_GEOGRAPHY"),
        )
        if value is not None
    ]
    if boundaries:
        result.append("Data and operating boundaries: " + " — ".join(boundaries))
    return tuple(result)


def _foundation_rows(
    foundation_table: ContractTable,
    normalized_responses: tuple[NormalizedOwnerResponse, ...],
    issues: list[tuple[str, str]],
) -> dict[str, tuple[str, str, str, str]]:
    """SAFETY: Validate foundation rows and provenance in canonical order."""

    expected_rows = dict(INTAKE_FOUNDATION_FIELDS)
    responses_by_provenance = {
        response.provenance: response for response in normalized_responses
    }
    observed_rows: dict[str, tuple[str, str, str, str]] = {}
    for (
        intake_id,
        field_name,
        value,
        basis,
        status,
        owner_response,
    ) in foundation_table.rows:
        if intake_id in observed_rows:
            issues.append(
                ("INTAKE_FOUNDATION_INVALID", f"Duplicate intake ID {intake_id}")
            )
            continue
        if INTAKE_ID.fullmatch(intake_id) is None:
            issues.append(
                ("INTAKE_FOUNDATION_INVALID", f"Invalid intake ID {intake_id!r}")
            )
        if expected_rows.get(intake_id) != field_name:
            issues.append(
                (
                    "INTAKE_FOUNDATION_INVALID",
                    f"{intake_id} must define {expected_rows.get(intake_id)!r}",
                )
            )
        if basis not in INTAKE_BASES:
            issues.append(
                (
                    "INTAKE_FOUNDATION_INVALID",
                    f"{intake_id} has invalid basis {basis!r}",
                )
            )
        if status not in {"OPEN", "CONFIRMED"}:
            issues.append(
                (
                    "INTAKE_FOUNDATION_INVALID",
                    f"{intake_id} has invalid status {status!r}",
                )
            )
        if status == "CONFIRMED":
            if not explicit_value(value, allow_none=False):
                issues.append(
                    (
                        "INTAKE_FOUNDATION_INVALID",
                        f"{intake_id} has no concrete owner value",
                    )
                )
            normalized_response = responses_by_provenance.get(owner_response)
            if (
                normalized_response is None
                or intake_id not in normalized_response.basis_ids
            ):
                issues.append(
                    (
                        "INTAKE_FOUNDATION_PROVENANCE_INVALID",
                        f"{intake_id} is not bound to one normalized owner response that cites it",
                    )
                )
            if field_name == "OWNER_WORK_CONTEXT" and normalized_response is not None:
                expected_context = OWNER_WORK_CONTEXT_SELECTIONS.get(
                    normalized_response.selection
                )
                if expected_context is None or value != expected_context:
                    issues.append(
                        (
                            "INTAKE_FOUNDATION_PROVENANCE_INVALID",
                            "OWNER_WORK_CONTEXT must map A/B/C to NEW_APPLICATION/EXISTING_APPLICATION_CHANGE/REPAIR_OR_MIGRATION",
                        )
                    )
            if basis != "OWNER_FACT":
                issues.append(
                    (
                        "INTAKE_FOUNDATION_INVALID",
                        f"{intake_id} can be confirmed only with OWNER_FACT provenance",
                    )
                )
            if field_name == "OWNER_WORK_CONTEXT" and value not in OWNER_WORK_CONTEXTS:
                issues.append(
                    (
                        "INTAKE_FOUNDATION_INVALID",
                        "OWNER_WORK_CONTEXT must be NEW_APPLICATION, EXISTING_APPLICATION_CHANGE, or REPAIR_OR_MIGRATION",
                    )
                )
        else:
            if basis == "OWNER_FACT":
                issues.append(
                    (
                        "INTAKE_FOUNDATION_INVALID",
                        f"{intake_id} cannot remain OPEN with OWNER_FACT provenance",
                    )
                )
            if owner_response != "NONE":
                issues.append(
                    (
                        "INTAKE_FOUNDATION_PROVENANCE_INVALID",
                        f"{intake_id} is OPEN but cites an owner response",
                    )
                )
        observed_rows[intake_id] = (field_name, value, status, owner_response)
    if (
        tuple((identifier, row[0]) for identifier, row in observed_rows.items())
        != INTAKE_FOUNDATION_FIELDS
    ):
        issues.append(
            (
                "INTAKE_FOUNDATION_INVALID",
                "Intake foundation rows and order must match the ten canonical INTAKE IDs",
            )
        )
    return observed_rows


def _card_question(
    raw: tuple[str, ...],
    expected_rows: dict[str, str],
    observed_rows: dict[str, tuple[str, str, str, str]],
    normalized_responses: tuple[NormalizedOwnerResponse, ...],
    responses_by_provenance: dict[str, NormalizedOwnerResponse],
    reply_keys: set[str],
    question_ids: set[str],
    issues: list[tuple[str, str]],
) -> tuple[IntakeQuestion, str, int, str, bool]:
    """SAFETY: Validate one decision-card row in canonical field order.

    Keeping the row-level checks cohesive preserves fail-closed provenance and
    the exact issue ordering consumed by existing owner-conversation flows.
    """
    (
        card_id,
        revision_text,
        reply_key,
        question_id,
        kind,
        basis_value,
        prompt,
        option_a,
        option_b,
        option_c,
        recommended,
        required_detail_value,
        detail_prompt,
        selection,
        selection_detail,
        owner_response,
    ) = raw
    try:
        revision = int(revision_text)
        if revision < 1 or str(revision) != revision_text:
            raise ValueError
    except ValueError:
        issues.append(
            ("INTAKE_CARD_INVALID", f"{question_id} has invalid card revision")
        )
        revision = 0
    if INTAKE_CARD_ID.fullmatch(card_id) is None:
        issues.append(("INTAKE_CARD_INVALID", f"Invalid card ID {card_id!r}"))
    if reply_key not in {"1", "2", "3"} or reply_key in reply_keys:
        issues.append(
            (
                "INTAKE_CARD_INVALID",
                f"{question_id} has invalid or duplicate reply key",
            )
        )
    reply_keys.add(reply_key)
    if INTAKE_QUESTION_ID.fullmatch(question_id) is None or question_id in question_ids:
        issues.append(
            (
                "INTAKE_CARD_INVALID",
                f"Invalid or duplicate question ID {question_id!r}",
            )
        )
    question_ids.add(question_id)
    if kind not in {"FACT", "DECISION"}:
        issues.append(
            ("INTAKE_CARD_INVALID", f"{question_id} kind must be FACT or DECISION")
        )
    try:
        question_basis = tuple(
            canonical_id_list(basis_value, INTAKE_ID, f"{question_id} Basis IDs")
        )
        if not set(question_basis).issubset(expected_rows):
            raise ValueError("Basis IDs must cite canonical intake foundation rows")
    except ValueError as exc:
        issues.append(("INTAKE_CARD_INVALID", f"{question_id}: {exc}"))
        question_basis = ()
    if not explicit_value(prompt, allow_none=False):
        issues.append(("INTAKE_CARD_INVALID", f"{question_id} prompt is unresolved"))
    if kind == "DECISION":
        options = (option_a, option_b, option_c)
        if any(not explicit_value(option, allow_none=False) for option in options):
            issues.append(
                (
                    "INTAKE_CARD_INVALID",
                    f"{question_id} requires concrete A/B/C choices",
                )
            )
        if len(set(options)) != 3:
            issues.append(
                ("INTAKE_CARD_INVALID", f"{question_id} choices must be distinct")
            )
        if recommended not in {"A", "NONE"}:
            issues.append(
                (
                    "INTAKE_CARD_INVALID",
                    f"{question_id} recommendation must be A or NONE",
                )
            )
    else:
        if any(option != "NOT_APPLICABLE" for option in (option_a, option_b, option_c)):
            issues.append(
                (
                    "INTAKE_CARD_INVALID",
                    f"{question_id} FACT choices must be NOT_APPLICABLE",
                )
            )
        if recommended != "NONE":
            issues.append(
                (
                    "INTAKE_CARD_INVALID",
                    f"{question_id} FACT recommendation must be NONE",
                )
            )
    try:
        required_detail = _intake_required_detail(required_detail_value, kind)
    except ValueError as exc:
        issues.append(("INTAKE_CARD_INVALID", f"{question_id}: {exc}"))
        required_detail = ()
    if required_detail:
        if not explicit_value(detail_prompt, allow_none=False):
            issues.append(
                (
                    "INTAKE_CARD_INVALID",
                    f"{question_id} requires a concrete detail prompt",
                )
            )
        detail_prompt_value: str | None = detail_prompt
    else:
        if detail_prompt != "NONE":
            issues.append(
                ("INTAKE_CARD_INVALID", f"{question_id} detail prompt must be NONE")
            )
        detail_prompt_value = None
    allowed_selections = (
        {"PENDING", "RESPONSE"} if kind == "FACT" else {"PENDING", "A", "B", "C"}
    )
    if selection not in allowed_selections:
        issues.append(
            (
                "INTAKE_CARD_INVALID",
                f"{question_id} has invalid selection {selection!r}",
            )
        )
    resolved = selection != "PENDING"
    provenance = INTAKE_OWNER_RESPONSE.fullmatch(owner_response)
    if not resolved:
        if selection_detail != "NONE" or owner_response != "NONE":
            issues.append(
                (
                    "INTAKE_SELECTION_PROVENANCE_INVALID",
                    f"{question_id} has an unproven selection; remove it and present the current card again",
                )
            )
        if any(
            response.card_id == card_id
            and response.revision == revision
            and response.question_id == question_id
            for response in normalized_responses
        ):
            issues.append(
                (
                    "INTAKE_SELECTION_PROVENANCE_INVALID",
                    f"{question_id} has an unproven selection; remove it and present the current card again",
                )
            )
    else:
        normalized_response = responses_by_provenance.get(owner_response)
        if (
            provenance is None
            or provenance.group("card") != card_id
            or int(provenance.group("revision")) != revision
            or provenance.group("question") != question_id
            or provenance.group("answer") != selection
            or normalized_response is None
        ):
            issues.append(
                (
                    "INTAKE_SELECTION_PROVENANCE_INVALID",
                    f"{question_id} selection is not bound to a current OWNER_RESPONSE",
                )
            )
        elif (
            normalized_response.reply_key != reply_key
            or normalized_response.selection_detail
            != (None if selection_detail == "NONE" else selection_detail)
            or normalized_response.basis_ids != question_basis
        ):
            issues.append(
                (
                    "INTAKE_SELECTION_PROVENANCE_INVALID",
                    f"{question_id} does not match its normalized owner response",
                )
            )
        for basis_id in question_basis:
            foundation_row = observed_rows.get(basis_id)
            if (
                foundation_row is None
                or foundation_row[2] != "CONFIRMED"
                or foundation_row[3] != owner_response
            ):
                issues.append(
                    (
                        "INTAKE_FOUNDATION_PROVENANCE_INVALID",
                        f"{question_id} and {basis_id} must cite the same parsed owner response",
                    )
                )
        detail_required = selection == "RESPONSE" or selection in required_detail
        if detail_required and not explicit_value(selection_detail, allow_none=False):
            issues.append(
                (
                    "INTAKE_SELECTION_PROVENANCE_INVALID",
                    f"{question_id} remains unresolved until its required detail is supplied",
                )
            )
        if not detail_required and selection_detail != "NONE":
            issues.append(
                (
                    "INTAKE_SELECTION_PROVENANCE_INVALID",
                    f"{question_id} has unexpected selection detail",
                )
            )
    question = IntakeQuestion(
        reply_key=reply_key,
        question_id=question_id,
        kind=kind,
        basis_ids=question_basis,
        prompt=prompt,
        option_a=option_a,
        option_b=option_b,
        option_c=option_c,
        recommended=None if recommended == "NONE" else recommended,
        required_detail_for=required_detail,
        detail_prompt=detail_prompt_value,
        selection=selection,
        selection_detail=None if selection_detail == "NONE" else selection_detail,
    )
    return question, card_id, revision, reply_key, resolved


def _derive_from_tables(
    tables: tuple[ContractTable, ContractTable, ContractTable],
    repository_mode_value: str | None,
) -> tuple[IntakeFoundationContract, list[tuple[str, str]]]:
    """SAFETY: Assemble intake state from the three validated canonical tables."""

    foundation_table, response_table, card_table = tables
    issues: list[tuple[str, str]] = []
    expected_rows = dict(INTAKE_FOUNDATION_FIELDS)
    normalized_responses = _parse_intake_response_register(
        response_table, expected_rows, issues
    )
    observed_rows = _foundation_rows(foundation_table, normalized_responses, issues)
    missing_fields = tuple(
        field_name
        for intake_id, field_name in INTAKE_FOUNDATION_FIELDS
        if observed_rows.get(intake_id, ("", "", "OPEN"))[2] != "CONFIRMED"
    )
    basis_ids = tuple(
        intake_id
        for intake_id, _field_name in INTAKE_FOUNDATION_FIELDS
        if observed_rows.get(intake_id, ("", "", "OPEN"))[2] == "CONFIRMED"
    )
    owner_work_context = None
    owner_row = observed_rows.get("INTAKE-0001")
    if owner_row is not None and owner_row[2] == "CONFIRMED":
        owner_work_context = owner_row[1]

    all_questions: list[IntakeQuestion] = []
    pending_questions: list[IntakeQuestion] = []
    card_ids: set[str] = set()
    revisions: set[int] = set()
    reply_keys: set[str] = set()
    question_ids: set[str] = set()
    responses_by_provenance = {
        response.provenance: response for response in normalized_responses
    }
    for raw in card_table.rows:
        question, card_id, revision, _reply_key, resolved = _card_question(
            raw,
            expected_rows,
            observed_rows,
            normalized_responses,
            responses_by_provenance,
            reply_keys,
            question_ids,
            issues,
        )
        card_ids.add(card_id)
        revisions.add(revision)
        all_questions.append(question)
        if not resolved:
            pending_questions.append(question)

    if len(all_questions) > 1:
        issues.append(
            (
                "INTAKE_CARD_MIGRATION_REQUIRED",
                "Reissue the first unresolved intake question alone with a new card revision and digest",
            )
        )
    elif len(all_questions) != 1:
        issues.append(
            (
                "INTAKE_CARD_INVALID",
                "Current intake card must contain exactly one question",
            )
        )
    if len(card_ids) != 1 or len(revisions) != 1:
        issues.append(
            ("INTAKE_CARD_INVALID", "Current intake card must use one ID and revision")
        )
    if sorted(reply_keys) != [str(index) for index in range(1, len(reply_keys) + 1)]:
        issues.append(
            (
                "INTAKE_CARD_INVALID",
                "Reply keys must be consecutive uppercase-choice numbers",
            )
        )

    pending_card = None
    if (
        len(all_questions) == 1
        and pending_questions
        and len(card_ids) == 1
        and len(revisions) == 1
    ):
        card_id = next(iter(card_ids))
        revision = next(iter(revisions))
        accept_all = all(
            question.kind == "DECISION"
            and question.recommended == "A"
            and "A" not in question.required_detail_for
            for question in pending_questions
        )
        canonical_sha256 = (
            "sha256:" + hashlib.sha256(card_table.canonical_bytes).hexdigest()
        )
        reply_token = intake_reply_token(card_id, revision, canonical_sha256)
        pending_card = IntakeCard(
            card_id=card_id,
            revision=revision,
            questions=tuple(pending_questions),
            accept_all_allowed=accept_all,
            owner_reply=_intake_owner_reply_example(pending_questions),
            exact_reply=_intake_reply_example(pending_questions, reply_token),
            canonical_sha256=canonical_sha256,
            reply_token=reply_token,
        )
    if missing_fields and not pending_questions:
        issues.append(
            (
                "INTAKE_CARD_REQUIRED",
                "Create the next one-question intake card for the remaining foundation fields",
            )
        )
    invalid_codes = {
        "INTAKE_FOUNDATION_INVALID",
        "INTAKE_FOUNDATION_PROVENANCE_INVALID",
        "INTAKE_RESPONSE_REGISTER_INVALID",
        "INTAKE_CARD_INVALID",
        "INTAKE_SELECTION_PROVENANCE_INVALID",
    }
    if any(code in invalid_codes for code, _ in issues):
        status = "BLOCKED"
    elif pending_questions or missing_fields:
        status = (
            "FOUNDATION_REQUIRED"
            if INTAKE_CORE_FIELDS.intersection(missing_fields)
            else "FOUNDATION_READY"
        )
    else:
        status = "READY_FOR_REQUIREMENTS"
    return IntakeFoundationContract(
        status=status,
        current_understanding=_current_understanding(owner_work_context, observed_rows),
        repository_mode=repository_mode_value,
        owner_work_context=owner_work_context,
        basis_ids=basis_ids,
        missing_fields=missing_fields,
        pending_card=pending_card,
        normalized_responses=tuple(normalized_responses),
        all_questions=tuple(all_questions),
    ), issues


def derive_intake_foundation_contract(
    text: str,
    repository_mode: str | None,
    *,
    grandfather_current_gate_a: bool,
) -> tuple[IntakeFoundationContract, list[tuple[str, str]]]:
    """Derive owner-grounded intake state without treating examples as facts."""

    normalized_repository_mode = (
        repository_mode.strip().lower() if isinstance(repository_mode, str) else None
    )
    repository_mode_value = (
        normalized_repository_mode.upper()
        if normalized_repository_mode in PROJECT_MODES
        else None
    )
    tables, early_result = _load_intake_tables(
        text, repository_mode_value, grandfather_current_gate_a
    )
    if early_result is not None:
        return early_result
    assert tables is not None
    return _derive_from_tables(tables, repository_mode_value)


__all__ = (
    "INTAKE_BASES",
    "INTAKE_CARD_HEADERS",
    "INTAKE_CARD_HEADING",
    "INTAKE_CARD_ID",
    "INTAKE_CORE_FIELDS",
    "INTAKE_FOUNDATION_FIELDS",
    "INTAKE_FOUNDATION_HEADERS",
    "INTAKE_FOUNDATION_HEADING",
    "INTAKE_ID",
    "INTAKE_OWNER_RESPONSE",
    "INTAKE_QUESTION_ID",
    "INTAKE_RESPONSE_REGISTER_HEADERS",
    "INTAKE_RESPONSE_REGISTER_HEADING",
    "LEGACY_INTAKE_FOUNDATION_HEADERS",
    "OWNER_RESPONSE_ID",
    "OWNER_WORK_CONTEXTS",
    "OWNER_WORK_CONTEXT_SELECTIONS",
    "PROJECT_MODES",
    "derive_intake_foundation_contract",
)
