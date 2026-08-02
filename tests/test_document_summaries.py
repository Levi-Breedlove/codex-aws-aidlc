from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def visible_markdown_lines(markdown: str) -> list[str]:
    """Return nonblank rendered lines while hiding closed disclosure bodies."""

    visible: list[str] = []
    in_details = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line == "<details>":
            in_details = True
            continue
        if in_details:
            if line.startswith("<summary>") and line.endswith("</summary>"):
                visible.append(line)
            elif line == "</details>":
                in_details = False
            continue
        if line:
            visible.append(line)
    return visible


class DocumentSummaryReadabilityTests(unittest.TestCase):
    def test_visible_line_helper_counts_only_disclosure_summary(self) -> None:
        markdown = """# Record

Visible

<details>
<summary>Exact records</summary>

Hidden row

</details>

Visible again
"""
        self.assertEqual(
            visible_markdown_lines(markdown),
            ["# Record", "Visible", "<summary>Exact records</summary>", "Visible again"],
        )

    def test_project_rules_define_the_first_screen_contract(self) -> None:
        project_rules = (
            REPOSITORY_ROOT / "docs" / "project" / "AGENTS.md"
        ).read_text(encoding="utf-8")
        workflow = (REPOSITORY_ROOT / "docs" / "WORKFLOW.md").read_text(
            encoding="utf-8"
        )
