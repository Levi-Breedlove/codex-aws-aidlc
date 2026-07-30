from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


ACCEPT_ALL_RECOMMENDATIONS = "Accept all recommendations."
CARD_ID = re.compile(r"INTAKE-CARD-\d{4,}")
QUESTION_ID = re.compile(r"INTAKE-Q-\d{4,}")
OWNER_RESPONSE_ID = re.compile(r"OWNER-MSG-\d{4,}")
CARD_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
REPLY_KEY = re.compile(r"[1-3]")
REPLY_TOKEN = re.compile(r"R-[0-9A-F]{12}")
ANGLE_PLACEHOLDER = re.compile(r"<[^>\r\n]+>")
SENTINEL = re.compile(
    r"(?:TODO|TBD|TBC|UNKNOWN|UNASSIGNED|PENDING|PLACEHOLDER|NONE|N/?A|your answer|required detail|choose A, B, or C)(?:\s+(?:-|\u2014)\s+(?:unavailable|unknown|not (?:provided|decided|applicable)|todo|tbd|pending))?",
    re.IGNORECASE,
)
SECRET_LIKE = re.compile(
    r"(?:secret|token|password|access[_-]?key|client[_-]?secret)\s*=\s*\S+|"
    r"(?:secret|token|password|access[_-]?key|client[_-]?secret)\s*:\s*(?:['\"][^'\"]+['\"]|[^\s,;]+)\s*$|"
    r"(?:AKIA|ASIA)[0-9A-Z]{16}|github_pat_|gh[pousr]_|sk-proj-|"
    r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----",
    re.IGNORECASE,
)
ALLOWED_WHITESPACE = frozenset({" ", "\t", "\r", "\n"})
MAX_RESPONSE_CHARACTERS = 6000
MAX_DETAIL_CHARACTERS = 2000


@dataclass(frozen=True)
class ParsedIntakeAnswer:
    reply_key: str
    question_id: str
    kind: str
    basis_ids: tuple[str, ...]
    selection: str
    detail: str | None
    provenance: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply_key": self.reply_key,
            "question_id": self.question_id,
            "kind": self.kind,
            "basis_ids": list(self.basis_ids),
            "selection": self.selection,
            "detail": self.detail,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class IntakeResponseParse:
    status: str
    owner_response_id: str | None
    card_id: str | None
    card_revision: int | None
    card_sha256: str | None
    answers: tuple[ParsedIntakeAnswer, ...] = ()
    unresolved_reply_keys: tuple[str, ...] = ()
    errors: tuple[dict[str, str], ...] = ()

    def owner_status(self) -> dict[str, str]:
        if self.errors:
            return {
                "status": "Your intake reply was not recorded.",
                "updated": "Nothing.",
                "required_from_you": (
                    "Correct the reported fields using the latest copyable intake reply."
                ),
                "after_that": (
                    "Codex will parse it again before writing project records."
                ),
            }
        if self.unresolved_reply_keys:
            answers = len(self.answers)
            remaining = len(self.unresolved_reply_keys)
            return {
                "status": (
                    f"{answers} answer{' was' if answers == 1 else 's were'} parsed; "
                    f"{remaining} question{' remains' if remaining == 1 else 's remain'}."
                ),
                "updated": "Nothing yet; the parsed answers are ready to record.",
                "required_from_you": (
                    "Nothing until Codex records them and presents only the "
                    "remaining questions."
                ),
                "after_that": (
                    "Codex will record only the parsed answers, validate them, "
                    "and present the remaining questions."
                ),
            }
        return {
            "status": "Your intake reply is valid and complete.",
            "updated": "Nothing yet; the parsed answers are ready to record.",
            "required_from_you": "Nothing.",
            "after_that": (
                "Codex will record only the parsed answers, validate them, and "
                "continue requirements definition."
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": self.status,
            "owner_status": self.owner_status(),
            "owner_response_id": self.owner_response_id,
            "card_id": self.card_id,
            "card_revision": self.card_revision,
            "card_sha256": self.card_sha256,
            "answers": [answer.to_dict() for answer in self.answers],
            "unresolved_reply_keys": list(self.unresolved_reply_keys),
            "errors": list(self.errors),
        }


def _error(code: str, message: str, *, reply_key: str | None = None) -> dict[str, str]:
    result = {"code": code, "message": message}
    if reply_key is not None:
        result["reply_key"] = reply_key
    return result


def _ascii_strip(value: str) -> str:
    return value.strip(" \t\r\n")


def _normalized_detail(value: str) -> str:
    return re.sub(r"[ \t]+", " ", _ascii_strip(value))


def _contains_unsupported_whitespace(value: str) -> bool:
    return any(
        character.isspace() and character not in ALLOWED_WHITESPACE
        for character in value
    )


def _contains_unsupported_control(value: str) -> bool:
    return any(
        unicodedata.category(character) == "Cf"
        or (
            unicodedata.category(character) == "Cc"
            and character not in ALLOWED_WHITESPACE
        )
        for character in value
    )


def _contains_record_unsafe_detail(value: str) -> bool:
    return "|" in value or "<!--" in value or "```" in value


def intake_reply_token(card_id: str, revision: int, card_sha256: str) -> str:
    """Return the opaque token that binds a copyable reply to one card."""
    identity = f"{card_id}\n{revision}\n{card_sha256}".encode("ascii")
    return "R-" + hashlib.sha256(identity).hexdigest()[:12].upper()


def intake_detail_safety_code(detail: str) -> str | None:
    """Return the shared fail-closed code for unsafe durable intake detail."""
    cleaned = _ascii_strip(detail)
    if _contains_record_unsafe_detail(cleaned):
        return "INTAKE_DETAIL_RECORD_UNSAFE"
    if ANGLE_PLACEHOLDER.search(cleaned) is not None or SENTINEL.fullmatch(cleaned):
        return "INTAKE_PLACEHOLDER"
    if SECRET_LIKE.search(cleaned) is not None:
        return "INTAKE_SECRET_MATERIAL"
    return None


def _question_contracts(
    pending_card: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    raw_questions = pending_card.get("questions")
    if (
        not isinstance(raw_questions, Sequence)
        or isinstance(raw_questions, (str, bytes))
        or not 1 <= len(raw_questions) <= 3
    ):
        return [], [
            _error(
                "INTAKE_CARD_INVALID",
                "Current card must contain one to three questions",
            )
        ]

    questions: list[dict[str, Any]] = []
    seen_reply_keys: set[str] = set()
    seen_question_ids: set[str] = set()
    for raw in raw_questions:
        if not isinstance(raw, Mapping):
            errors.append(
                _error(
                    "INTAKE_CARD_INVALID", "Current card contains an invalid question"
                )
            )
            continue
        reply_key = raw.get("reply_key")
        question_id = raw.get("question_id")
        kind = raw.get("kind")
        basis_ids = raw.get("basis_ids")
        required_detail_for = raw.get("required_detail_for")
        if (
            not isinstance(reply_key, str)
            or REPLY_KEY.fullmatch(reply_key) is None
            or reply_key in seen_reply_keys
            or not isinstance(question_id, str)
            or QUESTION_ID.fullmatch(question_id) is None
            or question_id in seen_question_ids
            or kind not in {"DECISION", "FACT"}
            or not isinstance(basis_ids, Sequence)
            or isinstance(basis_ids, (str, bytes))
            or not basis_ids
            or any(not isinstance(item, str) or not item for item in basis_ids)
            or not isinstance(required_detail_for, Sequence)
            or isinstance(required_detail_for, (str, bytes))
        ):
            errors.append(
                _error(
                    "INTAKE_CARD_INVALID",
                    "Current card contains an invalid question contract",
                )
            )
            continue
        seen_reply_keys.add(reply_key)
        seen_question_ids.add(question_id)
        recommended = raw.get("recommended")
        options = raw.get("options")
        if kind == "DECISION":
            if (
                not isinstance(options, Mapping)
                or set(options) != {"A", "B", "C"}
                or recommended not in {None, "A"}
                or any(item not in {"A", "B", "C"} for item in required_detail_for)
            ):
                errors.append(
                    _error(
                        "INTAKE_CARD_INVALID",
                        "Decision question has invalid choices or detail rules",
                        reply_key=reply_key,
                    )
                )
                continue
        elif (
            options != {}
            or recommended is not None
            or tuple(required_detail_for) != ("RESPONSE",)
        ):
            errors.append(
                _error(
                    "INTAKE_CARD_INVALID",
                    "Factual question has invalid choice or detail rules",
                    reply_key=reply_key,
                )
            )
            continue
        questions.append(
            {
                "reply_key": reply_key,
                "question_id": question_id,
                "kind": kind,
                "basis_ids": tuple(str(item) for item in basis_ids),
                "recommended": recommended,
                "required_detail_for": tuple(str(item) for item in required_detail_for),
            }
        )
    if not errors and [question["reply_key"] for question in questions] != sorted(
        seen_reply_keys
    ):
        errors.append(
            _error(
                "INTAKE_CARD_INVALID",
                "Current card reply keys must retain ascending source order",
            )
        )
    return questions, errors


def _parse_entry(
    entry: str, question: Mapping[str, Any]
) -> tuple[str | None, str | None, dict[str, str] | None]:
    key = str(question["reply_key"])
    remainder = _ascii_strip(entry[len(key) :])
    kind = question["kind"]
    if kind == "FACT":
        if not remainder.startswith(":"):
            return (
                None,
                None,
                _error(
                    "INTAKE_FACT_FORMAT",
                    "Factual answers must use '<key>: <answer>'",
                    reply_key=key,
                ),
            )
        detail = _normalized_detail(remainder[1:])
        if not detail:
            return (
                None,
                None,
                _error(
                    "INTAKE_DETAIL_REQUIRED", "Factual answer is empty", reply_key=key
                ),
            )
        return "RESPONSE", detail, None

    choice: str | None = None
    detail: str | None = None
    if remainder.startswith(":"):
        value = _ascii_strip(remainder[1:])
        match = re.fullmatch(r"(?i)([ABC])(?:[ \t]*:[ \t]*(.*))?", value)
        if match is not None:
            choice = match.group(1).upper()
            detail = _normalized_detail(match.group(2) or "") or None
    elif remainder and remainder[0].upper() in {"A", "B", "C"}:
        choice = remainder[0].upper()
        trailing = _ascii_strip(remainder[1:])
        if trailing:
            if not trailing.startswith(":"):
                return (
                    None,
                    None,
                    _error(
                        "INTAKE_DECISION_FORMAT",
                        "Decision detail must follow a colon",
                        reply_key=key,
                    ),
                )
            detail = _normalized_detail(trailing[1:]) or None
    if choice is None:
        return (
            None,
            None,
            _error(
                "INTAKE_DECISION_FORMAT",
                "Decision answers must choose A, B, or C",
                reply_key=key,
            ),
        )
    required = choice in question["required_detail_for"]
    if required and detail is None:
        return (
            None,
            None,
            _error(
                "INTAKE_DETAIL_REQUIRED",
                "This choice requires supporting detail",
                reply_key=key,
            ),
        )
    if not required and detail is not None:
        return (
            None,
            None,
            _error(
                "INTAKE_DETAIL_UNEXPECTED",
                "This choice does not accept supporting detail",
                reply_key=key,
            ),
        )
    return choice, detail, None


def _provenance(
    owner_response_id: str,
    card_id: str,
    card_revision: int,
    card_sha256: str,
    question_id: str,
    selection: str,
) -> str:
    return (
        f"OWNER_RESPONSE: {owner_response_id}; CARD: {card_id}; "
        f"REVISION: {card_revision}; SHA256: {card_sha256}; "
        f"QUESTION: {question_id}; ANSWER: {selection}"
    )


def parse_intake_owner_response(
    raw_response: str,
    pending_card: Mapping[str, Any],
    *,
    expected_card_id: str,
    expected_revision: int,
    expected_sha256: str,
    owner_response_id: str,
) -> IntakeResponseParse:
    """Parse only a reply to the exact current card; never infer missing answers."""

    errors: list[dict[str, str]] = []
    card_id = pending_card.get("card_id")
    card_revision = pending_card.get("revision")
    card_sha256 = pending_card.get("canonical_sha256")
    reply_token = pending_card.get("reply_token")
    valid_owner_response_id = (
        isinstance(owner_response_id, str)
        and OWNER_RESPONSE_ID.fullmatch(owner_response_id) is not None
    )
    if not valid_owner_response_id:
        errors.append(
            _error(
                "OWNER_RESPONSE_ID_INVALID", "Owner response ID must use OWNER-MSG-nnnn"
            )
        )
    if (
        not isinstance(card_id, str)
        or CARD_ID.fullmatch(card_id) is None
        or not isinstance(card_revision, int)
        or isinstance(card_revision, bool)
        or card_revision < 1
        or not isinstance(card_sha256, str)
        or CARD_DIGEST.fullmatch(card_sha256) is None
        or not isinstance(reply_token, str)
        or REPLY_TOKEN.fullmatch(reply_token) is None
        or not isinstance(pending_card.get("accept_all_allowed"), bool)
    ):
        errors.append(
            _error("INTAKE_CARD_INVALID", "Current intake card identity is invalid")
        )
    elif (
        expected_card_id != card_id
        or expected_revision != card_revision
        or expected_sha256 != card_sha256
        or reply_token != intake_reply_token(card_id, card_revision, card_sha256)
    ):
        errors.append(
            _error(
                "INTAKE_CARD_STALE",
                "This reply targets an older intake card; use the latest copyable reply",
            )
        )

    questions, question_errors = _question_contracts(pending_card)
    errors.extend(question_errors)
    if not isinstance(raw_response, str) or not _ascii_strip(raw_response):
        errors.append(_error("INTAKE_RESPONSE_EMPTY", "Owner response is empty"))
    elif len(raw_response) > MAX_RESPONSE_CHARACTERS:
        errors.append(
            _error(
                "INTAKE_RESPONSE_TOO_LONG",
                "Owner response exceeds the bounded intake limit",
            )
        )
    elif _contains_unsupported_whitespace(raw_response):
        errors.append(
            _error(
                "INTAKE_RESPONSE_WHITESPACE",
                "Owner response contains unsupported Unicode whitespace",
            )
        )
    elif _contains_unsupported_control(raw_response):
        errors.append(
            _error(
                "INTAKE_RESPONSE_CHARACTER",
                "Owner response contains an unsupported control or format character",
            )
        )
    if errors:
        return IntakeResponseParse(
            status="FAIL",
            owner_response_id=owner_response_id if valid_owner_response_id else None,
            card_id=card_id if isinstance(card_id, str) else None,
            card_revision=card_revision
            if isinstance(card_revision, int) and not isinstance(card_revision, bool)
            else None,
            card_sha256=card_sha256 if isinstance(card_sha256, str) else None,
            errors=tuple(errors),
        )

    assert isinstance(card_id, str)
    assert isinstance(card_revision, int)
    assert isinstance(card_sha256, str)
    assert isinstance(reply_token, str)
    normalized = _ascii_strip(raw_response)
    token_prefix = reply_token + ";"
    if not normalized.startswith(token_prefix):
        return IntakeResponseParse(
            status="FAIL",
            owner_response_id=owner_response_id,
            card_id=card_id,
            card_revision=card_revision,
            card_sha256=card_sha256,
            errors=(
                _error(
                    "INTAKE_CARD_STALE",
                    "This reply is not bound to the latest intake card; use its copyable reply",
                ),
            ),
        )
    normalized = _ascii_strip(normalized[len(token_prefix) :])
    if not normalized:
        errors.append(_error("INTAKE_RESPONSE_EMPTY", "Owner response is empty"))
    selected: dict[str, tuple[str, str | None]] = {}
    if normalized == ACCEPT_ALL_RECOMMENDATIONS:
        if not pending_card.get("accept_all_allowed"):
            errors.append(
                _error(
                    "INTAKE_ACCEPT_ALL_NOT_ALLOWED",
                    "Current card does not allow accepting all recommendations",
                )
            )
        else:
            for question in questions:
                recommended = question["recommended"]
                if (
                    question["kind"] != "DECISION"
                    or recommended not in {"A", "B", "C"}
                    or recommended in question["required_detail_for"]
                ):
                    errors.append(
                        _error(
                            "INTAKE_ACCEPT_ALL_NOT_ALLOWED",
                            "Current card recommendations are not independently complete",
                        )
                    )
                    break
                selected[str(question["reply_key"])] = (str(recommended), None)
    else:
        if normalized.casefold() == ACCEPT_ALL_RECOMMENDATIONS.casefold():
            errors.append(
                _error(
                    "INTAKE_ACCEPT_ALL_EXACT",
                    "Use the exact phrase 'Accept all recommendations.'",
                )
            )
        elif (
            normalized.startswith(";") or normalized.endswith(";") or ";;" in normalized
        ):
            errors.append(
                _error(
                    "INTAKE_RESPONSE_FORMAT",
                    "Reply contains an empty or trailing entry",
                )
            )
        else:
            entries = re.split(r"(?:;|\r?\n)+", normalized)
            by_key = {str(question["reply_key"]): question for question in questions}
            for raw_entry in entries:
                entry = _ascii_strip(raw_entry)
                match = re.match(r"([0-9]+)", entry)
                if match is None:
                    errors.append(
                        _error(
                            "INTAKE_RESPONSE_EXTRA_TEXT", "Reply contains unparsed text"
                        )
                    )
                    continue
                key = match.group(1)
                if key not in by_key:
                    errors.append(
                        _error(
                            "INTAKE_REPLY_KEY_UNKNOWN",
                            "Reply key is not on the current card",
                            reply_key=key,
                        )
                    )
                    continue
                if key in selected:
                    errors.append(
                        _error(
                            "INTAKE_REPLY_KEY_DUPLICATE",
                            "Reply key appears more than once",
                            reply_key=key,
                        )
                    )
                    continue
                selection, detail, entry_error = _parse_entry(entry, by_key[key])
                if entry_error is not None:
                    errors.append(entry_error)
                    continue
                assert selection is not None
                if detail is not None:
                    if len(detail) > MAX_DETAIL_CHARACTERS:
                        errors.append(
                            _error(
                                "INTAKE_DETAIL_TOO_LONG",
                                "Answer detail exceeds the bounded intake limit",
                                reply_key=key,
                            )
                        )
                        continue
                    safety_code = intake_detail_safety_code(detail)
                    if safety_code is not None:
                        messages = {
                            "INTAKE_DETAIL_RECORD_UNSAFE": "Answer detail contains record-unsafe Markdown syntax",
                            "INTAKE_PLACEHOLDER": "Placeholders cannot confirm an owner answer",
                            "INTAKE_SECRET_MATERIAL": (
                                "Potential secret material cannot be accepted in intake; "
                                "remove it and rotate it if real"
                            ),
                        }
                        errors.append(
                            _error(safety_code, messages[safety_code], reply_key=key)
                        )
                        continue
                selected[key] = (selection, detail)

    if errors:
        return IntakeResponseParse(
            status="FAIL",
            owner_response_id=owner_response_id,
            card_id=card_id,
            card_revision=card_revision,
            card_sha256=card_sha256,
            errors=tuple(errors),
        )

    answers: list[ParsedIntakeAnswer] = []
    for question in questions:
        key = str(question["reply_key"])
        if key not in selected:
            continue
        selection, detail = selected[key]
        answers.append(
            ParsedIntakeAnswer(
                reply_key=key,
                question_id=str(question["question_id"]),
                kind=str(question["kind"]),
                basis_ids=tuple(str(item) for item in question["basis_ids"]),
                selection=selection,
                detail=detail,
                provenance=_provenance(
                    owner_response_id,
                    card_id,
                    card_revision,
                    card_sha256,
                    str(question["question_id"]),
                    selection,
                ),
            )
        )
    unresolved = tuple(
        str(question["reply_key"])
        for question in questions
        if str(question["reply_key"]) not in selected
    )
    return IntakeResponseParse(
        status="PASS",
        owner_response_id=owner_response_id,
        card_id=card_id,
        card_revision=card_revision,
        card_sha256=card_sha256,
        answers=tuple(answers),
        unresolved_reply_keys=unresolved,
    )
