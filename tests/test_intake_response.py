from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "intake_response.py"
SPEC = importlib.util.spec_from_file_location("intake_response_under_test", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
intake = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = intake
SPEC.loader.exec_module(intake)


CARD_ID = "INTAKE-CARD-0001"
CARD_REVISION = 3
CARD_SHA256 = "sha256:" + ("a" * 64)
OWNER_RESPONSE_ID = "OWNER-MSG-0007"


def base_card() -> dict[str, Any]:
    return {
        "card_id": CARD_ID,
        "revision": CARD_REVISION,
        "canonical_sha256": CARD_SHA256,
        "reply_token": intake.intake_reply_token(CARD_ID, CARD_REVISION, CARD_SHA256),
        "accept_all_allowed": False,
        "questions": [
            {
                "reply_key": "1",
                "question_id": "INTAKE-Q-0001",
                "kind": "DECISION",
                "basis_ids": ["INTAKE-0001"],
                "options": {
                    "A": "A new application",
                    "B": "A change to an existing application",
                    "C": "A repair or migration",
                },
                "recommended": None,
                "required_detail_for": [],
            },
            {
                "reply_key": "2",
                "question_id": "INTAKE-Q-0002",
                "kind": "FACT",
                "basis_ids": ["INTAKE-0002", "INTAKE-0003"],
                "options": {},
                "recommended": None,
                "required_detail_for": ["RESPONSE"],
            },
            {
                "reply_key": "3",
                "question_id": "INTAKE-Q-0003",
                "kind": "DECISION",
                "basis_ids": ["INTAKE-0004"],
                "options": {
                    "A": "Invited development testing",
                    "B": "Internal production use",
                    "C": "Another release boundary",
                },
                "recommended": "A",
                "required_detail_for": ["C"],
            },
        ],
    }


def recommendation_card() -> dict[str, Any]:
    card = base_card()
    card["accept_all_allowed"] = True
    card["questions"] = [
        {
            "reply_key": str(index),
            "question_id": f"INTAKE-Q-{index:04d}",
            "kind": "DECISION",
            "basis_ids": [f"INTAKE-{index:04d}"],
            "options": {"A": "Alpha", "B": "Beta", "C": "Gamma"},
            "recommended": recommendation,
            "required_detail_for": [],
        }
        for index, recommendation in enumerate(("A", "A", "A"), start=1)
    ]
    return card


def parse(
    raw_response: str,
    card: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    current = card if card is not None else base_card()
    arguments = {
        "expected_card_id": CARD_ID,
        "expected_revision": CARD_REVISION,
        "expected_sha256": CARD_SHA256,
        "owner_response_id": OWNER_RESPONSE_ID,
    }
    arguments.update(overrides)
    return intake.parse_intake_owner_response(raw_response, current, **arguments)


def error_codes(result: Any) -> set[str]:
    return {error["code"] for error in result.to_dict()["errors"]}


class IntakeResponseAcceptanceTests(unittest.TestCase):
    def test_plain_and_matching_legacy_replies_use_the_same_current_card(self) -> None:
        card = base_card()
        plain = parse("1A", card)
        legacy = parse(f"{card['reply_token']}; 1A", card)

        self.assertEqual(plain.status, "PASS", plain.to_dict())
        self.assertEqual(legacy.status, "PASS", legacy.to_dict())
        self.assertEqual(
            [answer.to_dict() for answer in plain.answers],
            [answer.to_dict() for answer in legacy.answers],
        )

    def test_decision_forms_are_case_insensitive_and_normalized(self) -> None:
        cases = (
            ("1A", "A"),
            ("1 a", "A"),
            ("1: a", "A"),
            ("1B", "B"),
            ("1 b", "B"),
            ("1: b", "B"),
            ("1C", "C"),
            ("1 c", "C"),
            ("1: c", "C"),
        )
        for raw_response, expected in cases:
            with self.subTest(raw_response=raw_response):
                result = parse(raw_response)
                self.assertEqual(result.status, "PASS")
                self.assertEqual(len(result.answers), 1)
                self.assertEqual(result.answers[0].selection, expected)
                self.assertEqual(result.answers[0].detail, None)
                self.assertEqual(result.unresolved_reply_keys, ("2", "3"))

    def test_ascii_whitespace_and_mixed_separators_are_bounded_and_normalized(
        self,
    ) -> None:
        result = parse(
            " \t1 a ;\r\n 2:\tDevelopment\t users   need a report\n3:\tc:\tPublic pilot \r\n"
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(
            [
                (answer.reply_key, answer.selection, answer.detail)
                for answer in result.answers
            ],
            [
                ("1", "A", None),
                ("2", "RESPONSE", "Development users need a report"),
                ("3", "C", "Public pilot"),
            ],
        )
        self.assertEqual(result.unresolved_reply_keys, ())

    def test_crlf_lf_and_semicolon_each_separate_entries(self) -> None:
        for separator in (";", "\n", "\r\n"):
            with self.subTest(separator=repr(separator)):
                result = parse(f"1A{separator}2: Users{separator}3A")
                self.assertEqual(result.status, "PASS")
                self.assertEqual(
                    [answer.reply_key for answer in result.answers],
                    ["1", "2", "3"],
                )

    def test_factual_partial_reply_does_not_infer_missing_answers(self) -> None:
        result = parse("2:  People who manage   development releases ")
        self.assertEqual(result.status, "PASS")
        self.assertEqual(len(result.answers), 1)
        answer = result.answers[0]
        self.assertEqual(answer.reply_key, "2")
        self.assertEqual(answer.question_id, "INTAKE-Q-0002")
        self.assertEqual(answer.kind, "FACT")
        self.assertEqual(answer.basis_ids, ("INTAKE-0002", "INTAKE-0003"))
        self.assertEqual(answer.selection, "RESPONSE")
        self.assertEqual(answer.detail, "People who manage development releases")
        self.assertEqual(result.unresolved_reply_keys, ("1", "3"))
        self.assertEqual(
            result.owner_status()["required_from_you"],
            "Nothing until Codex records them and presents only the remaining questions.",
        )

    def test_pending_subset_retains_original_reply_keys(self) -> None:
        card = base_card()
        card["questions"] = card["questions"][1:]
        result = parse("2: Users; 3A", card)
        self.assertEqual(result.status, "PASS")
        self.assertEqual([answer.reply_key for answer in result.answers], ["2", "3"])

    def test_accept_all_exact_phrase_uses_only_complete_current_recommendations(
        self,
    ) -> None:
        result = parse(" \tAccept all recommendations.\r\n", recommendation_card())
        self.assertEqual(result.status, "PASS")
        self.assertEqual(
            [(answer.reply_key, answer.selection) for answer in result.answers],
            [("1", "A"), ("2", "A"), ("3", "A")],
        )
        self.assertTrue(all(answer.detail is None for answer in result.answers))
        self.assertEqual(result.unresolved_reply_keys, ())

    def test_normalized_result_and_provenance_bind_to_exact_card_without_raw_echo(
        self,
    ) -> None:
        raw_response = "\t2:\tUser-visible   outcome\r\n"
        result = parse(raw_response)
        self.assertEqual(
            result.to_dict(),
            {
                "schema_version": 1,
                "status": "PASS",
                "owner_status": {
                    "status": "1 answer was parsed; 2 questions remain.",
                    "updated": "Nothing yet; the parsed answers are ready to record.",
                    "required_from_you": (
                        "Nothing until Codex records them and presents only the "
                        "remaining questions."
                    ),
                    "after_that": (
                        "Codex will record only the parsed answers, validate them, "
                        "and present the remaining questions."
                    ),
                },
                "owner_response_id": OWNER_RESPONSE_ID,
                "card_id": CARD_ID,
                "card_revision": CARD_REVISION,
                "card_sha256": CARD_SHA256,
                "answers": [
                    {
                        "reply_key": "2",
                        "question_id": "INTAKE-Q-0002",
                        "kind": "FACT",
                        "basis_ids": ["INTAKE-0002", "INTAKE-0003"],
                        "selection": "RESPONSE",
                        "detail": "User-visible outcome",
                        "provenance": (
                            "OWNER_RESPONSE: OWNER-MSG-0007; CARD: INTAKE-CARD-0001; "
                            f"REVISION: 3; SHA256: {CARD_SHA256}; "
                            "QUESTION: INTAKE-Q-0002; ANSWER: RESPONSE"
                        ),
                    }
                ],
                "unresolved_reply_keys": ["1", "3"],
                "errors": [],
            },
        )
        serialized = json.dumps(result.to_dict(), sort_keys=True)
        self.assertNotIn("raw_response", serialized)
        self.assertNotIn("\t", serialized)
        self.assertNotIn("User-visible   outcome", serialized)
        for unsupported_claim in (
            "authenticated",
            "identity_verified",
            "cryptographic",
        ):
            self.assertNotIn(unsupported_claim, serialized.casefold())

    def test_maximum_detail_length_is_accepted(self) -> None:
        detail = "x" * intake.MAX_DETAIL_CHARACTERS
        result = parse(f"2: {detail}")
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.answers[0].detail, detail)


class IntakeResponseRejectionTests(unittest.TestCase):
    def assert_failed_with(self, result: Any, code: str) -> None:
        self.assertEqual(result.status, "FAIL")
        self.assertIn(code, error_codes(result))
        self.assertEqual(result.answers, ())
        self.assertEqual(result.unresolved_reply_keys, ())

    def test_unknown_duplicate_and_conflicting_reply_keys_are_rejected(self) -> None:
        cases = (
            ("4A", "INTAKE_REPLY_KEY_UNKNOWN"),
            ("1A; 1A", "INTAKE_REPLY_KEY_DUPLICATE"),
            ("1A; 1B", "INTAKE_REPLY_KEY_DUPLICATE"),
        )
        for raw_response, expected_code in cases:
            with self.subTest(raw_response=raw_response):
                self.assert_failed_with(parse(raw_response), expected_code)

    def test_exact_card_id_revision_and_digest_are_each_required(self) -> None:
        cases = (
            {"expected_card_id": "INTAKE-CARD-9999"},
            {"expected_revision": CARD_REVISION + 1},
            {"expected_sha256": "sha256:" + ("b" * 64)},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assert_failed_with(
                    parse("1A", **overrides),
                    "INTAKE_CARD_STALE",
                )

    def test_delayed_reply_token_cannot_bind_to_a_newer_card(self) -> None:
        old = base_card()
        delayed = f"{old['reply_token']}; 1A"
        current = base_card()
        current["canonical_sha256"] = "sha256:" + ("b" * 64)
        current["reply_token"] = intake.intake_reply_token(
            CARD_ID, CARD_REVISION, current["canonical_sha256"]
        )
        self.assert_failed_with(
            parse(delayed, current, expected_sha256=current["canonical_sha256"]),
            "INTAKE_CARD_STALE",
        )

    def test_stale_or_invalid_identity_inside_card_is_rejected(self) -> None:
        cases = (
            ("card_id", "INTAKE-CARD-old"),
            ("revision", 0),
            ("revision", True),
            ("canonical_sha256", "sha256:not-a-digest"),
            ("canonical_sha256", "sha256:" + ("A" * 64)),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                card = base_card()
                card[field] = value
                self.assert_failed_with(parse("1A", card), "INTAKE_CARD_INVALID")

    def test_placeholder_values_cannot_confirm_owner_facts_or_details(self) -> None:
        placeholders = (
            "<your answer>",
            "TODO",
            "TBD",
            "TBC",
            "UNKNOWN",
            "UNASSIGNED",
            "PENDING",
            "PLACEHOLDER",
            "NONE",
            "N/A",
            "required detail",
            "choose A, B, or C",
        )
        for placeholder in placeholders:
            with self.subTest(placeholder=placeholder):
                self.assert_failed_with(
                    parse(f"2: {placeholder}"),
                    "INTAKE_PLACEHOLDER",
                )

    def test_secret_like_details_are_rejected_without_echo(self) -> None:
        secret_like = "aws_secret_access_key=synthetic-value"
        result = parse(f"2: {secret_like}")
        self.assert_failed_with(result, "INTAKE_SECRET_MATERIAL")
        serialized = json.dumps(result.to_dict(), sort_keys=True)
        self.assertNotIn(secret_like, serialized)
        self.assertEqual(
            result.owner_status()["status"], "Your intake reply was not recorded."
        )
        self.assertEqual(result.owner_status()["updated"], "Nothing.")

        for secret_like in (
            "password: huntertwo",
            "token: abcdefgh",
            "client_secret: alphabeticvalue",
            "password: abc",
            "token: 12345",
            "secret: foo",
        ):
            with self.subTest(secret_like=secret_like):
                self.assert_failed_with(
                    parse(f"2: {secret_like}"), "INTAKE_SECRET_MATERIAL"
                )

    def test_ordinary_sentinel_and_password_words_remain_valid_prose(self) -> None:
        for detail in (
            "None of the current users can export reports",
            "The release is pending legal review",
            "Password: recovery is the main problem",
            "None - there are no external users",
            "N/A - this is a new application",
            "Pending - legal review completes Friday",
            "Password: 12 characters minimum",
            "Token: JWT-based access is required",
        ):
            with self.subTest(detail=detail):
                result = parse(f"2: {detail}")
                self.assertEqual(result.status, "PASS", result.to_dict())

    def test_required_missing_and_unexpected_detail_are_rejected(self) -> None:
        self.assert_failed_with(parse("3C"), "INTAKE_DETAIL_REQUIRED")
        self.assert_failed_with(parse("3A: unnecessary"), "INTAKE_DETAIL_UNEXPECTED")
        self.assert_failed_with(parse("2:"), "INTAKE_DETAIL_REQUIRED")

    def test_unparsed_or_trailing_content_is_rejected_without_echoing_it(self) -> None:
        hostile = "UNPARSED_PRIVATE_VALUE_4921"
        cases = (
            hostile,
            f"1A; {hostile}",
            "1A because it looks right",
            ";1A",
            "1A;",
            "1A;;2: Users",
        )
        for raw_response in cases:
            with self.subTest(raw_response=raw_response):
                result = parse(raw_response)
                self.assertEqual(result.status, "FAIL")
                serialized = json.dumps(result.to_dict(), sort_keys=True)
                self.assertNotIn("raw_response", serialized)
                self.assertNotIn(hostile, serialized)

    def test_accept_all_phrase_is_case_sensitive_and_card_scoped(self) -> None:
        for raw_response in (
            "accept all recommendations.",
            "ACCEPT ALL RECOMMENDATIONS.",
            "Accept all recommendations",
            "Accept all recommendations. extra",
        ):
            with self.subTest(raw_response=raw_response):
                self.assertEqual(
                    parse(raw_response, recommendation_card()).status,
                    "FAIL",
                )

        self.assert_failed_with(
            parse(intake.ACCEPT_ALL_RECOMMENDATIONS, base_card()),
            "INTAKE_ACCEPT_ALL_NOT_ALLOWED",
        )

    def test_accept_all_rejects_incomplete_or_detail_dependent_recommendations(
        self,
    ) -> None:
        no_recommendation = recommendation_card()
        no_recommendation["questions"][0]["recommended"] = None

        factual = recommendation_card()
        factual["questions"][1] = copy.deepcopy(base_card()["questions"][1])

        needs_detail = recommendation_card()
        needs_detail["questions"][2]["required_detail_for"] = ["A"]

        for card in (no_recommendation, factual, needs_detail):
            with self.subTest(card=card):
                self.assert_failed_with(
                    parse(intake.ACCEPT_ALL_RECOMMENDATIONS, card),
                    "INTAKE_ACCEPT_ALL_NOT_ALLOWED",
                )

    def test_unicode_whitespace_and_confusable_characters_are_rejected(self) -> None:
        whitespace_cases = (
            "2:\u00a0Users",
            "2:\u2003Users",
            "1A\u20282: Users",
        )
        for raw_response in whitespace_cases:
            with self.subTest(raw_response=ascii(raw_response)):
                self.assert_failed_with(
                    parse(raw_response),
                    "INTAKE_RESPONSE_WHITESPACE",
                )

        confusables = (
            "\uff11A",  # Full-width digit one.
            "1\uff21",  # Full-width Latin A.
            "1\u0410",  # Cyrillic capital A.
            "1\u0430",  # Cyrillic small a.
        )
        for raw_response in confusables:
            with self.subTest(raw_response=ascii(raw_response)):
                self.assertEqual(parse(raw_response).status, "FAIL")

    def test_zero_width_characters_are_not_silently_normalized(self) -> None:
        for character in ("\u200b", "\u200c", "\ufeff"):
            with self.subTest(character=ascii(character)):
                result = parse(f"1{character}A")
                self.assert_failed_with(result, "INTAKE_RESPONSE_CHARACTER")

                factual = parse(f"2: Users{character}need a report")
                self.assert_failed_with(factual, "INTAKE_RESPONSE_CHARACTER")

    def test_unsupported_control_characters_are_rejected(self) -> None:
        for character in ("\x00", "\x07", "\x1b"):
            with self.subTest(character=ascii(character)):
                self.assert_failed_with(
                    parse(f"2: Users{character}need a report"),
                    "INTAKE_RESPONSE_CHARACTER",
                )

    def test_record_unsafe_details_are_rejected_without_echo(self) -> None:
        cases = (
            "2: Users | operators",
            "2: Users <!-- hidden -->",
            "2: Users ``` hidden",
            "3C: Public | external",
        )
        for raw_response in cases:
            with self.subTest(raw_response=raw_response):
                result = parse(raw_response)
                self.assert_failed_with(result, "INTAKE_DETAIL_RECORD_UNSAFE")
                serialized = json.dumps(result.to_dict(), sort_keys=True)
                self.assertNotIn(raw_response, serialized)

    def test_malformed_question_contracts_fail_closed(self) -> None:
        cases: list[tuple[str, Any]] = []

        no_questions = base_card()
        no_questions["questions"] = []
        cases.append(("no questions", no_questions))

        too_many = base_card()
        too_many["questions"].append(copy.deepcopy(too_many["questions"][2]))
        too_many["questions"][3]["reply_key"] = "4"
        too_many["questions"][3]["question_id"] = "INTAKE-Q-0004"
        cases.append(("too many questions", too_many))

        duplicate_key = base_card()
        duplicate_key["questions"][1]["reply_key"] = "1"
        cases.append(("duplicate reply key", duplicate_key))

        duplicate_id = base_card()
        duplicate_id["questions"][1]["question_id"] = "INTAKE-Q-0001"
        cases.append(("duplicate question id", duplicate_id))

        missing_basis = base_card()
        missing_basis["questions"][0]["basis_ids"] = []
        cases.append(("missing basis", missing_basis))

        bad_kind = base_card()
        bad_kind["questions"][0]["kind"] = "CHOICE"
        cases.append(("bad kind", bad_kind))

        bad_options = base_card()
        bad_options["questions"][0]["options"] = {"A": "Alpha", "B": "Beta"}
        cases.append(("bad options", bad_options))

        bad_recommendation = base_card()
        bad_recommendation["questions"][0]["recommended"] = "D"
        cases.append(("bad recommendation", bad_recommendation))

        unsupported_recommendation = base_card()
        unsupported_recommendation["questions"][0]["recommended"] = "B"
        cases.append(("unsupported recommendation", unsupported_recommendation))

        bad_fact_rules = base_card()
        bad_fact_rules["questions"][1]["required_detail_for"] = []
        cases.append(("bad fact rules", bad_fact_rules))

        bad_accept_all_flag = base_card()
        bad_accept_all_flag["accept_all_allowed"] = "false"
        cases.append(("bad accept-all flag", bad_accept_all_flag))

        out_of_order = base_card()
        out_of_order["questions"] = list(reversed(out_of_order["questions"]))
        cases.append(("out-of-order keys", out_of_order))

        for label, card in cases:
            with self.subTest(label=label):
                self.assert_failed_with(parse("1A", card), "INTAKE_CARD_INVALID")

    def test_invalid_owner_response_id_is_rejected(self) -> None:
        result = parse("1A", owner_response_id="OWNER-MSG-invalid")
        self.assert_failed_with(result, "OWNER_RESPONSE_ID_INVALID")
        self.assertNotIn("OWNER-MSG-invalid", json.dumps(result.to_dict()))

    def test_oversize_response_and_detail_are_rejected(self) -> None:
        response = "x" * (intake.MAX_RESPONSE_CHARACTERS + 1)
        self.assert_failed_with(
            parse(response),
            "INTAKE_RESPONSE_TOO_LONG",
        )

        detail = "x" * (intake.MAX_DETAIL_CHARACTERS + 1)
        self.assert_failed_with(
            parse(f"2: {detail}"),
            "INTAKE_DETAIL_TOO_LONG",
        )

    def test_empty_and_non_string_responses_fail_closed(self) -> None:
        for value in ("", " \t\r\n", None, 42):
            with self.subTest(value=value):
                result = intake.parse_intake_owner_response(
                    value,  # type: ignore[arg-type]
                    base_card(),
                    expected_card_id=CARD_ID,
                    expected_revision=CARD_REVISION,
                    expected_sha256=CARD_SHA256,
                    owner_response_id=OWNER_RESPONSE_ID,
                )
                self.assert_failed_with(result, "INTAKE_RESPONSE_EMPTY")


if __name__ == "__main__":
    unittest.main()
