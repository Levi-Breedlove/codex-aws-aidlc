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


def decision_card(
    *,
    recommended: str | None = None,
    required_detail_for: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "card_id": CARD_ID,
        "revision": CARD_REVISION,
        "canonical_sha256": CARD_SHA256,
        "reply_token": intake.intake_reply_token(CARD_ID, CARD_REVISION, CARD_SHA256),
        "accept_all_allowed": recommended == "A" and "A" not in required_detail_for,
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
                "recommended": recommended,
                "required_detail_for": list(required_detail_for),
            }
        ],
    }


def fact_card() -> dict[str, Any]:
    card = decision_card()
    card["accept_all_allowed"] = False
    card["questions"] = [
        {
            "reply_key": "1",
            "question_id": "INTAKE-Q-0002",
            "kind": "FACT",
            "basis_ids": ["INTAKE-0002", "INTAKE-0003"],
            "options": {},
            "recommended": None,
            "required_detail_for": ["RESPONSE"],
        }
    ]
    return card


def parse(
    raw_response: str,
    card: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    current = card if card is not None else decision_card()
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
    def test_natural_keyed_and_legacy_replies_use_the_same_current_card(self) -> None:
        card = decision_card()
        natural = parse("A", card)
        keyed = parse("1A", card)
        legacy = parse(f"{card['reply_token']}; 1A", card)

        self.assertEqual(natural.status, "PASS", natural.to_dict())
        self.assertEqual(keyed.status, "PASS", keyed.to_dict())
        self.assertEqual(legacy.status, "PASS", legacy.to_dict())
        self.assertEqual(
            [answer.to_dict() for answer in natural.answers],
            [answer.to_dict() for answer in keyed.answers],
        )
        self.assertEqual(
            [answer.to_dict() for answer in natural.answers],
            [answer.to_dict() for answer in legacy.answers],
        )

    def test_decision_forms_are_case_insensitive_and_normalized(self) -> None:
        cases = (
            ("A", "A"),
            (" a ", "A"),
            ("1A", "A"),
            ("1 a", "A"),
            ("1: a", "A"),
            ("B", "B"),
            ("1B", "B"),
            ("1 b", "B"),
            ("1: b", "B"),
            ("C", "C"),
            ("1C", "C"),
            ("1 c", "C"),
            ("1: c", "C"),
        )
        for raw_response, expected in cases:
            with self.subTest(raw_response=raw_response):
                result = parse(raw_response)
                self.assertEqual(result.status, "PASS", result.to_dict())
                self.assertEqual(len(result.answers), 1)
                self.assertEqual(result.answers[0].selection, expected)
                self.assertIsNone(result.answers[0].detail)
                self.assertEqual(result.unresolved_reply_keys, ())

    def test_factual_reply_accepts_natural_prose_semicolons_and_line_breaks(
        self,
    ) -> None:
        result = parse(
            (
                "I'm building a PRD app for AWS; the difficult part is choosing "
                "cost-efficient services,\r\nwriting them together securely."
            ),
            fact_card(),
        )
        self.assertEqual(result.status, "PASS", result.to_dict())
        self.assertEqual(len(result.answers), 1)
        answer = result.answers[0]
        self.assertEqual(answer.reply_key, "1")
        self.assertEqual(answer.question_id, "INTAKE-Q-0002")
        self.assertEqual(answer.kind, "FACT")
        self.assertEqual(answer.basis_ids, ("INTAKE-0002", "INTAKE-0003"))
        self.assertEqual(answer.selection, "RESPONSE")
        self.assertEqual(
            answer.detail,
            (
                "I'm building a PRD app for AWS; the difficult part is choosing "
                "cost-efficient services, writing them together securely."
            ),
        )
        self.assertEqual(result.unresolved_reply_keys, ())

    def test_keyed_factual_reply_remains_compatible(self) -> None:
        result = parse(
            " \t1:\tPeople who manage   development releases \r\n",
            fact_card(),
        )
        self.assertEqual(result.status, "PASS", result.to_dict())
        self.assertEqual(
            result.answers[0].detail,
            "People who manage development releases",
        )

    def test_factual_reply_never_interprets_semicolon_text_as_another_answer(
        self,
    ) -> None:
        result = parse(
            "The first zone is 1A; 1B is a label in the source material.",
            fact_card(),
        )

        self.assertEqual(result.status, "PASS", result.to_dict())
        self.assertEqual(
            result.answers[0].detail,
            "The first zone is 1A; 1B is a label in the source material.",
        )

    def test_accept_phrase_applies_only_to_the_current_recommendation(self) -> None:
        for phrase in (
            intake.ACCEPT_THIS_RECOMMENDATION,
            intake.ACCEPT_ALL_RECOMMENDATIONS,
        ):
            with self.subTest(phrase=phrase):
                result = parse(
                    f" \t{phrase}\r\n",
                    decision_card(recommended="A"),
                )
                self.assertEqual(result.status, "PASS", result.to_dict())
                self.assertEqual(
                    [(answer.reply_key, answer.selection) for answer in result.answers],
                    [("1", "A")],
                )
                self.assertIsNone(result.answers[0].detail)

    def test_normalized_result_binds_to_exact_card_without_raw_echo(self) -> None:
        raw_response = "\t1:\tUser-visible   outcome\r\n"
        result = parse(raw_response, fact_card())
        self.assertEqual(result.status, "PASS", result.to_dict())
        self.assertEqual(result.owner_status()["required_from_you"], "Nothing.")
        self.assertEqual(
            result.answers[0].provenance,
            (
                "OWNER_RESPONSE: OWNER-MSG-0007; CARD: INTAKE-CARD-0001; "
                f"REVISION: 3; SHA256: {CARD_SHA256}; "
                "QUESTION: INTAKE-Q-0002; ANSWER: RESPONSE"
            ),
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
        result = parse(detail, fact_card())
        self.assertEqual(result.status, "PASS", result.to_dict())
        self.assertEqual(result.answers[0].detail, detail)


class IntakeResponseRejectionTests(unittest.TestCase):
    def assert_failed_with(self, result: Any, code: str) -> None:
        self.assertEqual(result.status, "FAIL", result.to_dict())
        self.assertIn(code, error_codes(result))
        self.assertEqual(result.answers, ())
        self.assertEqual(result.unresolved_reply_keys, ())

    def test_unknown_duplicate_and_conflicting_reply_keys_are_rejected(self) -> None:
        cases = (
            ("2A", "INTAKE_REPLY_KEY_UNKNOWN"),
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

    def test_delayed_legacy_token_cannot_bind_to_a_newer_card(self) -> None:
        old = decision_card()
        delayed = f"{old['reply_token']}; 1A"
        current = decision_card()
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
                card = decision_card()
                card[field] = value
                self.assert_failed_with(parse("1A", card), "INTAKE_CARD_INVALID")

    def test_placeholder_values_cannot_confirm_owner_facts(self) -> None:
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
                    parse(f"1: {placeholder}", fact_card()),
                    "INTAKE_PLACEHOLDER",
                )

    def test_secret_like_details_are_rejected_without_echo(self) -> None:
        for secret_like in (
            "aws_" + "secret_access_key=synthetic-value",
            "pass" + "word: synthetic-value",
            "token: abcdefgh",
            "client_" + "secret: synthetic-value",
        ):
            with self.subTest(secret_like=secret_like):
                result = parse(f"1: {secret_like}", fact_card())
                self.assert_failed_with(result, "INTAKE_SECRET_MATERIAL")
                self.assertNotIn(
                    secret_like, json.dumps(result.to_dict(), sort_keys=True)
                )

    def test_ordinary_sensitive_words_remain_valid_prose(self) -> None:
        for detail in (
            "None of the current users can export reports",
            "The release is pending legal review",
            "Password recovery is the main problem",
            "None - there are no external users",
            "N/A - this is a new application",
            "Pending - legal review completes Friday",
            "Password: 12 characters minimum",
            "Token: JWT-based access is required",
        ):
            with self.subTest(detail=detail):
                result = parse(f"1: {detail}", fact_card())
                self.assertEqual(result.status, "PASS", result.to_dict())

    def test_required_missing_and_unexpected_detail_are_rejected(self) -> None:
        detail_card = decision_card(required_detail_for=("C",))
        self.assert_failed_with(parse("C", detail_card), "INTAKE_DETAIL_REQUIRED")
        accepted = parse("C: Existing review application", detail_card)
        self.assertEqual(accepted.status, "PASS", accepted.to_dict())
        self.assertEqual(accepted.answers[0].selection, "C")
        self.assertEqual(accepted.answers[0].detail, "Existing review application")
        self.assert_failed_with(
            parse("A: unnecessary", detail_card),
            "INTAKE_DETAIL_UNEXPECTED",
        )
        self.assert_failed_with(parse("1:", fact_card()), "INTAKE_DETAIL_REQUIRED")

    def test_unparsed_or_trailing_content_is_rejected_without_echo(self) -> None:
        hostile = "UNPARSED_PRIVATE_VALUE_4921"
        cases = (
            hostile,
            f"1A; {hostile}",
            "1A because it looks right",
            ";1A",
            "1A;",
            "1A;;2A",
        )
        for raw_response in cases:
            with self.subTest(raw_response=raw_response):
                result = parse(raw_response)
                self.assertEqual(result.status, "FAIL")
                self.assertNotIn(hostile, json.dumps(result.to_dict(), sort_keys=True))

    def test_accept_phrase_is_exact_and_card_scoped(self) -> None:
        card = decision_card(recommended="A")
        for raw_response in (
            "accept this recommendation.",
            "ACCEPT THIS RECOMMENDATION.",
            "Accept this recommendation",
            "Accept this recommendation. extra",
            "accept all recommendations.",
            "ACCEPT ALL RECOMMENDATIONS.",
            "Accept all recommendations",
            "Accept all recommendations. extra",
        ):
            with self.subTest(raw_response=raw_response):
                self.assertEqual(parse(raw_response, card).status, "FAIL")
        for phrase in (
            intake.ACCEPT_THIS_RECOMMENDATION,
            intake.ACCEPT_ALL_RECOMMENDATIONS,
        ):
            with self.subTest(phrase=phrase):
                self.assert_failed_with(
                    parse(phrase, decision_card()),
                    "INTAKE_ACCEPT_ALL_NOT_ALLOWED",
                )

    def test_accept_all_rejects_incomplete_or_detail_dependent_choice(self) -> None:
        factual = fact_card()
        factual["accept_all_allowed"] = True
        for card in (
            decision_card(),
            factual,
            decision_card(recommended="A", required_detail_for=("A",)),
        ):
            card["accept_all_allowed"] = True
            for phrase in (
                intake.ACCEPT_THIS_RECOMMENDATION,
                intake.ACCEPT_ALL_RECOMMENDATIONS,
            ):
                with self.subTest(card=card, phrase=phrase):
                    self.assert_failed_with(
                        parse(phrase, card),
                        "INTAKE_ACCEPT_ALL_NOT_ALLOWED",
                    )

    def test_legacy_accept_phrase_remains_an_exact_compatibility_alias(self) -> None:
        self.assertEqual(
            intake.ACCEPT_ALL_RECOMMENDATIONS,
            "Accept all recommendations.",
        )
        self.assertNotEqual(
            intake.ACCEPT_THIS_RECOMMENDATION,
            intake.ACCEPT_ALL_RECOMMENDATIONS,
        )

    def test_unicode_whitespace_and_confusable_characters_are_rejected(self) -> None:
        for raw_response in ("1:\u00a0Users", "1:\u2003Users"):
            with self.subTest(raw_response=ascii(raw_response)):
                self.assert_failed_with(
                    parse(raw_response, fact_card()),
                    "INTAKE_RESPONSE_WHITESPACE",
                )
        for raw_response in ("\uff11A", "1\uff21", "1\u0410", "1\u0430"):
            with self.subTest(raw_response=ascii(raw_response)):
                self.assertEqual(parse(raw_response).status, "FAIL")

    def test_zero_width_and_control_characters_are_rejected(self) -> None:
        for character in ("\u200b", "\u200c", "\ufeff", "\x00", "\x07", "\x1b"):
            with self.subTest(character=ascii(character)):
                result = parse(f"1: Users{character}need a report", fact_card())
                self.assertIn(
                    result.errors[0]["code"],
                    {"INTAKE_RESPONSE_CHARACTER", "INTAKE_RESPONSE_WHITESPACE"},
                )

    def test_record_unsafe_details_are_rejected_without_echo(self) -> None:
        for raw_response in (
            "1: Users | operators",
            "1: Users <!-- hidden -->",
        ):
            with self.subTest(raw_response=raw_response):
                result = parse(raw_response, fact_card())
                self.assert_failed_with(result, "INTAKE_DETAIL_RECORD_UNSAFE")
                self.assertNotIn(
                    raw_response, json.dumps(result.to_dict(), sort_keys=True)
                )

    def test_malformed_question_contracts_fail_closed(self) -> None:
        cases: list[tuple[str, Any]] = []

        no_questions = decision_card()
        no_questions["questions"] = []
        cases.append(("no questions", no_questions))

        multiple_questions = decision_card()
        multiple_questions["questions"].append(
            copy.deepcopy(multiple_questions["questions"][0])
        )
        multiple_questions["questions"][1]["reply_key"] = "2"
        multiple_questions["questions"][1]["question_id"] = "INTAKE-Q-0002"
        cases.append(("multiple questions", multiple_questions))

        missing_basis = decision_card()
        missing_basis["questions"][0]["basis_ids"] = []
        cases.append(("missing basis", missing_basis))

        bad_kind = decision_card()
        bad_kind["questions"][0]["kind"] = "CHOICE"
        cases.append(("bad kind", bad_kind))

        bad_options = decision_card()
        bad_options["questions"][0]["options"] = {"A": "Alpha", "B": "Beta"}
        cases.append(("bad options", bad_options))

        bad_recommendation = decision_card()
        bad_recommendation["questions"][0]["recommended"] = "D"
        cases.append(("bad recommendation", bad_recommendation))

        unsupported_recommendation = decision_card()
        unsupported_recommendation["questions"][0]["recommended"] = "B"
        cases.append(("unsupported recommendation", unsupported_recommendation))

        bad_fact_rules = fact_card()
        bad_fact_rules["questions"][0]["required_detail_for"] = []
        cases.append(("bad fact rules", bad_fact_rules))

        bad_accept_all_flag = decision_card()
        bad_accept_all_flag["accept_all_allowed"] = "false"
        cases.append(("bad accept-all flag", bad_accept_all_flag))

        for label, card in cases:
            with self.subTest(label=label):
                self.assert_failed_with(parse("1A", card), "INTAKE_CARD_INVALID")

    def test_invalid_owner_response_id_is_rejected(self) -> None:
        result = parse("1A", owner_response_id="OWNER-MSG-invalid")
        self.assert_failed_with(result, "OWNER_RESPONSE_ID_INVALID")
        self.assertNotIn("OWNER-MSG-invalid", json.dumps(result.to_dict()))

    def test_oversize_response_and_detail_are_rejected(self) -> None:
        response = "x" * (intake.MAX_RESPONSE_CHARACTERS + 1)
        self.assert_failed_with(parse(response), "INTAKE_RESPONSE_TOO_LONG")
        detail = "x" * (intake.MAX_DETAIL_CHARACTERS + 1)
        self.assert_failed_with(
            parse(f"1: {detail}", fact_card()),
            "INTAKE_DETAIL_TOO_LONG",
        )

    def test_empty_and_non_string_responses_fail_closed(self) -> None:
        for value in ("", " \t\r\n", None, 42):
            with self.subTest(value=value):
                result = intake.parse_intake_owner_response(
                    value,  # type: ignore[arg-type]
                    decision_card(),
                    expected_card_id=CARD_ID,
                    expected_revision=CARD_REVISION,
                    expected_sha256=CARD_SHA256,
                    owner_response_id=OWNER_RESPONSE_ID,
                )
                self.assert_failed_with(result, "INTAKE_RESPONSE_EMPTY")


class GateCorrectionTests(unittest.TestCase):
    def test_exact_requirement_and_design_corrections_parse_without_approval(
        self,
    ) -> None:
        requirements = intake.parse_gate_correction(
            "Change the requirements: Support invited beta users only."
        )
        design = intake.parse_gate_correction(
            "Change the design: Use a managed queue for background work."
        )

        self.assertEqual(requirements.status, "PASS")
        self.assertEqual(requirements.gate, "GATE_A")
        self.assertEqual(requirements.correction, "Support invited beta users only")
        self.assertFalse(requirements.to_dict()["approval_granted"])
        self.assertEqual(design.status, "PASS")
        self.assertEqual(design.gate, "GATE_B")
        self.assertFalse(design.to_dict()["approval_granted"])

    def test_correction_never_accepts_approval_or_loose_prose(self) -> None:
        for value in (
            "APPROVE REQUIREMENTS GATE A",
            "Please change the requirements",
            "Change the requirements: ",
            "Change the design: use a queue",
        ):
            with self.subTest(value=value):
                result = intake.parse_gate_correction(value)
                self.assertEqual(result.status, "FAIL")
                self.assertFalse(result.to_dict()["approval_granted"])

    def test_secret_like_correction_fails_without_echoing_input(self) -> None:
        raw = "Change the design: client_" + "secret=do-not-store."
        result = intake.parse_gate_correction(raw)

        self.assertEqual(result.status, "FAIL")
        self.assertNotIn(raw, json.dumps(result.to_dict(), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
