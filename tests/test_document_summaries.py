from __future__ import annotations

import copy
import unittest
from pathlib import Path

from scripts import bootstrap_doctor as doctor
from scripts.fastlane_document_summaries import (
    SUMMARY_BEGIN,
    SUMMARY_END,
    build_summary_specifications,
    project_document_summaries,
    render_summary_markdown,
    wrapped_summary_markdown,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def visible_markdown_lines(markdown: str) -> list[str]:
    """Return nonblank rendered lines while hiding closed disclosure bodies."""

    visible: list[str] = []
    in_details = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("<!--") and line.endswith("-->"):
            continue
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
            [
                "# Record",
                "Visible",
                "<summary>Exact records</summary>",
                "Visible again",
            ],
        )


DOCUMENT_PATHS = (
    "docs/project/README.md",
    "docs/project/PRD.md",
    "docs/project/TASKS.md",
    "docs/project/VERIFY.md",
    "docs/project/RUNBOOK.md",
    "docs/project/BUGFIX.md",
)


def template_specifications() -> list[dict[str, object]]:
    return build_summary_specifications(
        {
            "template_like": True,
            "lifecycle_state": "UNCONFIGURED_TEMPLATE",
            "next_prompt": "BOOT-00",
            "gate_a": "BLOCKED",
            "gate_b": "BLOCKED",
            "tasks": {},
            "verify": {
                "claims": [
                    {
                        "claim": "Requirements are approved",
                        "maturity": "Not yet observed",
                        "evidence": "None",
                        "limitation": "Gate A is not approved",
                    },
                    {
                        "claim": "Technical design is approved",
                        "maturity": "Not yet observed",
                        "evidence": "None",
                        "limitation": "Gate B is not approved",
                    },
                    {
                        "claim": "Current AWS guidance informed the plan",
                        "maturity": "Not yet observed",
                        "evidence": "None",
                        "limitation": "Source guidance is not deployment evidence",
                    },
                    {
                        "claim": "Local release checks passed",
                        "maturity": "Not yet observed",
                        "evidence": "None",
                        "limitation": "Local evidence does not prove AWS behavior",
                    },
                    {
                        "claim": "Application is deployed",
                        "maturity": "Not authorized",
                        "evidence": "None",
                        "limitation": "No deployment evidence or authority",
                    },
                ]
            },
            "operations": {},
            "bugfix": {"status": "No active bounded defect"},
        }
    )


def canonical_sources() -> dict[str, str]:
    return {
        path: (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
        for path in DOCUMENT_PATHS
    }


def first_screen(markdown: str) -> list[str]:
    end = markdown.index(SUMMARY_END) + len(SUMMARY_END)
    return visible_markdown_lines(markdown[:end])


class DocumentSummaryProjectionTests(unittest.TestCase):
    def test_untouched_template_summaries_are_current_and_deterministic(self) -> None:
        specifications = template_specifications()
        first, first_issues = project_document_summaries(
            canonical_sources(), specifications
        )
        second, second_issues = project_document_summaries(
            canonical_sources(), specifications
        )

        self.assertEqual(first_issues, [])
        self.assertEqual(second_issues, [])
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], 1)
        self.assertEqual(first["status"], "CURRENT")
        self.assertEqual(
            [document["path"] for document in first["documents"]],
            list(DOCUMENT_PATHS),
        )
        for document in first["documents"]:
            self.assertEqual(document["status"], "CURRENT")
            self.assertRegex(document["canonical_sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(document["rendered_sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(document["heading"], "Current state")

    def test_each_first_screen_is_compact_current_and_owner_safe(self) -> None:
        for path in DOCUMENT_PATHS:
            with self.subTest(path=path):
                source = canonical_sources()[path]
                lines = first_screen(source)
                self.assertGreaterEqual(len(lines), 25)
                self.assertLessEqual(len(lines), 40)
                self.assertEqual(
                    sum(line.startswith("| Need from you |") for line in lines),
                    1,
                )
                visible = "\n".join(lines)
                summary = source[
                    source.index(SUMMARY_BEGIN) : source.index(SUMMARY_END)
                ]
                self.assertNotIn("{{", summary)
                self.assertNotIn("sha256:", visible)
                self.assertNotIn("R-", visible)
                self.assertNotRegex(visible, r"[A-Z]:\\Users\\|/Users/|/home/")

    def test_document_specific_fields_and_verify_claims_are_rendered(self) -> None:
        projected, _ = project_document_summaries(
            canonical_sources(), template_specifications()
        )
        by_path = {document["path"]: document for document in projected["documents"]}
        required = {
            "docs/project/README.md": {
                "Phase",
                "Overall status",
                "Last completed milestone",
                "Gate A",
                "Gate B",
                "AWS deployment",
            },
            "docs/project/PRD.md": {
                "Product outcome",
                "First-release boundary",
                "Requirements",
                "Technical design",
                "Region and cost",
                "Construction authorization",
            },
            "docs/project/TASKS.md": {
                "Progress",
                "Current wave",
                "Active task",
                "Blocker",
                "Last known-green commit",
            },
            "docs/project/VERIFY.md": {
                "Release result",
                "Locally observed evidence",
                "Failed or stale evidence",
                "Still unobserved",
            },
            "docs/project/RUNBOOK.md": {
                "Environment",
                "Deployment state",
                "Current AWS authority",
                "Deployment approval",
                "Teardown approval",
            },
            "docs/project/BUGFIX.md": {
                "Status",
                "Defect",
                "User impact",
                "Environment",
                "Related requirements",
            },
        }
        for path, labels in required.items():
            actual = {field["label"] for field in by_path[path]["fields"]}
            self.assertTrue(labels.issubset(actual), (path, labels - actual))

        verify_source = canonical_sources()["docs/project/VERIFY.md"]
        self.assertIn(
            "| Claim | Current maturity | Evidence | Limitation |", verify_source
        )
        self.assertIn("Application is deployed", verify_source)
        self.assertIn("Not yet observed", verify_source)

    def test_stale_summary_is_agent_correctable(self) -> None:
        sources = canonical_sources()
        sources["docs/project/PRD.md"] = sources["docs/project/PRD.md"].replace(
            "| Product outcome | Not yet confirmed |",
            "| Product outcome | Hand-edited value |",
            1,
        )
        projected, issues = project_document_summaries(
            sources, template_specifications()
        )
        self.assertEqual(projected["status"], "STALE")
        self.assertEqual(
            [(issue["code"], issue["path"]) for issue in issues],
            [("DOCUMENT_SUMMARY_STALE", "docs/project/PRD.md")],
        )

        context = doctor.Context(REPOSITORY_ROOT)
        context.error(
            "DOCUMENT_SUMMARY_STALE",
            "Visible project summary differs from canonical state",
            "docs/project/PRD.md",
        )
        remediation = doctor.derive_remediation(
            context,
            classification="UNCONFIGURED_TEMPLATE",
            gate_a="BLOCKED",
            gate_b="BLOCKED",
            envelope={},
            tasks=doctor.TaskSummary(),
            owner_stage_hint="DEFINE",
        )
        self.assertEqual(
            remediation["next_action"],
            {
                "responsible_party": "CODEX",
                "action_kind": "CORRECT_AND_REVALIDATE",
                "automatic_continuation_allowed": True,
            },
        )
        self.assertEqual(remediation["items"][0]["category"], "AGENT_CORRECTION")

    def test_missing_ambiguous_and_private_sources_fail_closed(self) -> None:
        specifications = template_specifications()

        missing_sources = canonical_sources()
        del missing_sources["docs/project/BUGFIX.md"]
        projected, issues = project_document_summaries(missing_sources, specifications)
        self.assertEqual(projected["status"], "BLOCKED")
        self.assertEqual(issues[0]["code"], "DOCUMENT_SUMMARY_SOURCE_INVALID")

        duplicate_sources = canonical_sources()
        duplicate_sources["docs/project/README.md"] += "\n" + SUMMARY_BEGIN + "\n"
        projected, issues = project_document_summaries(
            duplicate_sources, specifications
        )
        self.assertEqual(projected["status"], "BLOCKED")
        self.assertEqual(issues[0]["code"], "DOCUMENT_SUMMARY_UNSAFE")

        unsafe = copy.deepcopy(specifications)
        unsafe[0]["fields"][0]["value"] = r"C:\Users\owner\private"
        projected, issues = project_document_summaries(canonical_sources(), unsafe)
        self.assertEqual(projected["status"], "BLOCKED")
        self.assertEqual(issues[0]["code"], "DOCUMENT_SUMMARY_UNSAFE")

    def test_rendering_is_lf_normalized_and_wrapped_once(self) -> None:
        specification = template_specifications()[0]
        rendered = render_summary_markdown(specification)
        wrapped = wrapped_summary_markdown(specification)
        self.assertNotIn("\r", rendered)
        self.assertTrue(rendered.endswith("\n"))
        self.assertEqual(wrapped.count(SUMMARY_BEGIN), 1)
        self.assertEqual(wrapped.count(SUMMARY_END), 1)
        self.assertIn(rendered, wrapped)

    def test_project_rules_define_the_first_screen_contract(self) -> None:
        project_rules = (REPOSITORY_ROOT / "docs" / "project" / "AGENTS.md").read_text(
            encoding="utf-8"
        )
        workflow = (REPOSITORY_ROOT / "docs" / "WORKFLOW.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("25-40 visible nonblank lines", project_rules)
        self.assertIn("Engine-derived `Current state`", project_rules)
        self.assertIn("one owner need or `Nothing`", workflow)
