from __future__ import annotations

import html
import unittest

from scripts.fastlane_project_identity import (
    markdown_inline,
    normalize_aws_region,
    normalize_project_name,
)


class ProjectIdentityTests(unittest.TestCase):
    def test_project_name_normalizes_nfc_and_preserves_visible_text(self) -> None:
        cases = {
            "  Cafe\u0301  ": "Caf\u00e9",
            "\u6771\u4eac \u2014 \U0001f469\u200d\U0001f4bb": (
                "\u6771\u4eac \u2014 \U0001f469\u200d\U0001f4bb"
            ),
            'Tracker "Home" \\ A | <demo> [x] *Caf\u00e9* & Sons': (
                'Tracker "Home" \\ A | <demo> [x] *Caf\u00e9* & Sons'
            ),
            "Release {{2026}}": "Release {{2026}}",
            "Owner's App": "Owner's App",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_project_name(raw), expected)

    def test_project_name_accepts_full_documented_unicode_boundary(self) -> None:
        for value in ("\u754c" * 100, "\U0001f600" * 100):
            with self.subTest(length=len(value)):
                self.assertEqual(normalize_project_name(value), value)

    def test_project_name_rejects_invisible_structural_or_oversized_values(
        self,
    ) -> None:
        cases = (
            "",
            "   ",
            "line\nbreak",
            "tab\tname",
            "line\u2028break",
            "direction\u202eoverride",
            "zero\u200bwidth",
            "\ufeffbom",
            "{{AWS_REGION}}",
            "prefix {{PROJECT_NAME}} suffix",
            "a" * 101,
            "\U0001f600" * 101,
            "\u200d",
            "\u0301",
            "---",
        )
        for raw in cases:
            with self.subTest(raw=repr(raw)), self.assertRaises(ValueError):
                normalize_project_name(raw)

    def test_project_name_allows_joiners_inside_visible_international_text(
        self,
    ) -> None:
        value = "\u0915\u094d\u200d\u0937 App"
        self.assertEqual(normalize_project_name(value), value)

    def test_region_normalizes_supported_shapes_without_claiming_availability(
        self,
    ) -> None:
        values = (
            "us-west-2",
            "us-gov-west-1",
            "us-iso-east-1",
            "eu-isoe-west-1",
            "cn-north-1",
            "eusc-de-east-1",
            "ap-southeast-7",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(normalize_aws_region(f" {value.upper()} "), value)

    def test_region_rejects_non_region_zone_and_control_shapes(self) -> None:
        values = (
            "aws-global",
            "us-west-2a",
            "us-west-2-lax-1",
            "us-west-2-lax-1a",
            "us-east-1-wl1-bos-wlz-1",
            "us-west-2-1",
            "us_west_2",
            "Seattle",
            "https://us-west-2",
            "us-west-0",
            "us-west-2\nprod",
            "\nus-west-2\n",
            "\tus-west-2\t",
            "us-west-2\u00a0",
            "a" * 64,
        )
        for value in values:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                normalize_aws_region(value)

    def test_markdown_inline_round_trips_without_structural_characters(self) -> None:
        value = 'Tracker "Home" \\ A | <demo> [x] *Caf\u00e9* & Sons'
        rendered = markdown_inline(value)
        self.assertEqual(html.unescape(rendered), value)
        for structural in ("\\", "|", "<", ">", "[", "]", "*", "& Sons"):
            self.assertNotIn(structural, rendered)


if __name__ == "__main__":
    unittest.main()
