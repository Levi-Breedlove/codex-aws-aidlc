from __future__ import annotations

import hashlib
import os
import re
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock
from urllib.parse import unquote

from tests import render_mermaid_fixtures, test_bootstrap_doctor
from tests.repository_sources import source_files
from scripts.fastlane_engine.design.diagrams import LINEAR_DIAGRAM_CONFIG


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
MAX_AGENT_CONTEXT_BYTES = 28 * 1024
NESTED_AGENT_SCOPE_MARKER = (
    "This guide narrows the root rules and never widens approval or authorization."
)
MERMAID_BLOCK = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
MERMAID_DECLARATION = re.compile(
    r"^(?:flowchart\s+(?:TB|TD|BT|RL|LR)|sequenceDiagram|"
    r"stateDiagram(?:-v2)?|classDiagram|erDiagram|journey|gantt|pie|mindmap|"
    r"timeline|quadrantChart|requirementDiagram)\b"
)
PRD_DISCLOSURE = re.compile(
    r"<details>\s*<summary>([^<\n]+)</summary>\s*(.*?)\s*</details>",
    re.DOTALL,
)
AUTHORIZATION_STEP = "Authorize, validate, and apply idempotency"
PERSISTENCE_STEP = "Persist approved data"
QUEUE_ACK_STEP = "Durable enqueue acknowledged"
ACCEPTED_STEP = "Accepted response with correlation ID"
WORKER_DELIVERY_STEP = "Deliver work"
RECEIPT_SHA256 = {
    "gate-a-receipt": "7b6ad510b449d0095101c0ebdd75f9ac21d826076f5ee215c03dc17579880266",
    "gate-b-receipt": "455995bf3557aa32ef9cd82513430eb25f26265924929aad4d6d32e1698275c4",
    "aws-read-preflight-receipt": "72b244b89c1b2affd194ded7484147eef406ecfd09e8be9e4a1c86d318313433",
    "aws-deployment-receipt": "0d58dd6348d513216cf57936f9b4ccada146389533c077d252145df91ac8d7de",
    "aws-teardown-receipt": "a6bc0f3dca0104238b0c344af61386af00f167e9f326026b786197cfb1067119",
}
WORKER_VALIDATION_STEP = "Validate trusted source, schema, and idempotency"
WORKER_PERSISTENCE_STEP = "Worker->>Data: Persist approved data"


def github_anchor(value: str) -> str:
    value = value.strip().casefold()
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE)
    return re.sub(r"\s", "-", value).strip("-")


def headings(path: Path) -> set[str]:
    result: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            result.add(github_anchor(match.group(1)))
    return result


def persistence_order_failures(markdown: str) -> list[str]:
    failures: list[str] = []
    for index, block in enumerate(MERMAID_BLOCK.findall(markdown), 1):
        if PERSISTENCE_STEP not in block:
            continue
        if AUTHORIZATION_STEP not in block:
            failures.append(f"Mermaid block {index} persists without authorization")
            continue
        if block.index(AUTHORIZATION_STEP) > block.index(PERSISTENCE_STEP):
            failures.append(f"Mermaid block {index} persists before authorization")
    return failures


def mermaid_structure_failures(markdown: str) -> list[str]:
    """Return block-local failures for empty or unsupported Mermaid structures."""

    failures: list[str] = []
    for index, block in enumerate(MERMAID_BLOCK.findall(markdown), 1):
        declaration = next(
            (
                line.strip()
                for line in block.splitlines()
                if line.strip() and not line.strip().startswith("%%")
            ),
            None,
        )
        if declaration is None:
            failures.append(f"Mermaid block {index} is empty")
        elif MERMAID_DECLARATION.match(declaration) is None:
            failures.append(f"Mermaid block {index} has an unsupported declaration")
    return failures


def disclosure_lines(markdown: str) -> list[tuple[int, str, int]]:
    """Return normalized lines and their enclosing disclosure depth."""

    result: list[tuple[int, str, int]] = []
    depth = 0
    for number, raw_line in enumerate(markdown.splitlines(), 1):
        line = raw_line.strip()
        if line == "</details>":
            depth -= 1
            if depth < 0:
                raise AssertionError(f"Unexpected </details> at line {number}")
            result.append((number, line, depth))
            continue
        result.append((number, line, depth))
        if line == "<details>":
            depth += 1
    if depth:
        raise AssertionError(f"Unclosed <details> depth: {depth}")
    return result


def visible_outside_disclosures(markdown: str) -> str:
    return "\n".join(
        line
        for _number, line, depth in disclosure_lines(markdown)
        if depth == 0 and line not in {"<details>", "</details>"}
    )


def rendered_visible_lines(markdown: str) -> list[str]:
    """Return owner-visible rendered lines outside closed disclosures."""

    visible: list[str] = []
    table_rule = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$")
    fence = re.compile(r"^(?:```|~~~)(?:[A-Za-z0-9_-]+)?$")
    for _number, line, depth in disclosure_lines(markdown):
        if not line or line in {"<details>", "</details>"}:
            continue
        if depth and not line.startswith("<summary>"):
            continue
        if line.startswith("<!--") and line.endswith("-->"):
            continue
        if fence.fullmatch(line) or table_rule.fullmatch(line):
            continue
        visible.append(line)
    return visible


class MarkdownIntegrityTests(unittest.TestCase):
    def markdown_files(self) -> list[Path]:
        return sorted(
            path for path in source_files(REPOSITORY_ROOT) if path.suffix == ".md"
        )

    def test_relative_markdown_links_and_fragments_resolve(self) -> None:
        failures: list[str] = []
        for source in self.markdown_files():
            text = source.read_text(encoding="utf-8")
            for raw in MARKDOWN_LINK.findall(text):
                target = raw.strip().strip("<>")
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if " " in target and not raw.strip().startswith("<"):
                    target = target.split()[0]
                path_part, separator, fragment = target.partition("#")
                destination = (
                    source
                    if not path_part
                    else (source.parent / unquote(path_part)).resolve()
                )
                try:
                    destination.relative_to(REPOSITORY_ROOT)
                except ValueError:
                    failures.append(
                        f"{source.relative_to(REPOSITORY_ROOT)} -> {target} escapes root"
                    )
                    continue
                if not destination.exists():
                    failures.append(
                        f"{source.relative_to(REPOSITORY_ROOT)} -> {target} missing"
                    )
                    continue
                if (
                    separator
                    and fragment
                    and destination.is_file()
                    and destination.suffix.casefold() == ".md"
                ):
                    if unquote(fragment).casefold() not in headings(destination):
                        failures.append(
                            f"{source.relative_to(REPOSITORY_ROOT)} -> {target} fragment missing"
                        )
        self.assertEqual(failures, [])

    def test_markdown_and_mermaid_fences_are_balanced(self) -> None:
        failures: list[str] = []
        for path in self.markdown_files():
            active: str | None = None
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                match = re.match(r"^\s*(```+|~~~+)", line)
                if not match:
                    continue
                marker = match.group(1)[0]
                if active is None:
                    active = marker
                elif marker == active:
                    active = None
            if active is not None:
                failures.append(str(path.relative_to(REPOSITORY_ROOT)))
        self.assertEqual(failures, [])

    def test_mermaid_blocks_have_supported_structural_declarations(self) -> None:
        failures: list[str] = []
        for path in self.markdown_files():
            for failure in mermaid_structure_failures(path.read_text(encoding="utf-8")):
                failures.append(f"{path.relative_to(REPOSITORY_ROOT)}: {failure}")
        self.assertEqual(failures, [])

    def test_mermaid_structure_fixtures_are_block_local(self) -> None:
        fixture = """
```mermaid
```
```mermaid
unknownDiagram
```
```mermaid
%% structural comment
flowchart TD
    A --> B
```
```mermaid
sequenceDiagram
    A->>B: Request
```
"""
        self.assertEqual(
            mermaid_structure_failures(fixture),
            [
                "Mermaid block 1 is empty",
                "Mermaid block 2 has an unsupported declaration",
            ],
        )

    def test_project_documents_are_canonical_and_removed_surfaces_stay_removed(
        self,
    ) -> None:
        required = ("BUGFIX.md", "PRD.md", "RUNBOOK.md", "TASKS.md", "VERIFY.md")
        for name in required:
            self.assertTrue((REPOSITORY_ROOT / "docs" / "project" / name).is_file())
            self.assertFalse((REPOSITORY_ROOT / name).exists())
        for removed in ("CHANGELOG.md", "CONTRIBUTING.md", "VERSION"):
            self.assertFalse((REPOSITORY_ROOT / removed).exists())
        self.assertFalse((REPOSITORY_ROOT / "scripts" / "run_demo.py").exists())
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in self.markdown_files()
        )
        self.assertNotIn("docs/demo/", combined)
        self.assertNotIn("scripts/run_demo.py", combined)

    def test_fresh_prd_has_honest_project_diagram_slots(self) -> None:
        prd = (REPOSITORY_ROOT / "docs" / "project" / "PRD.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(MERMAID_BLOCK.findall(prd), [])
        for kind in (
            "SYSTEM_CONTEXT",
            "PRIMARY_OUTCOME",
            "DATA_LIFECYCLE",
            "FAILURE_RECOVERY",
            "MIGRATION",
            "JOURNEY",
            "STATE",
            "AWS_IMPLEMENTATION",
        ):
            self.assertRegex(
                prd,
                rf"\| DIAGRAM-[0-9]{{4}} \| {kind} \| .* \| NOT_YET_CREATED \|",
            )
        self.assertIn("Diagrams describe planned design", " ".join(prd.split()))
        design = (
            REPOSITORY_ROOT / ".agents/skills/fastlane/references/design.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "Diagrams never prove implementation, deployment, or authority", design
        )

    def test_diagram_patterns_are_on_demand_and_non_authoritative(self) -> None:
        patterns = (
            REPOSITORY_ROOT
            / ".agents"
            / "skills"
            / "fastlane"
            / "references"
            / "diagram-patterns.md"
        ).read_text(encoding="utf-8")
        blocks = MERMAID_BLOCK.findall(patterns)
        self.assertEqual(len(blocks), 4)
        self.assertIn("Load only during Design", patterns)
        self.assertIn("not application architecture", patterns)
        self.assertIn(
            "Never imply that a planned diagram was deployed",
            " ".join(patterns.split()),
        )

        expected_roles = (
            {
                "ACT-000": "actor",
                "API-000": "compute",
                "BOUNDARY-000": "entry",
                "ARCH-0000": "compute",
                "TECH-0004": "data",
                "TECH-0005": "ops",
            },
            {
                "TECH-0001": "compute",
                "TECH-0002": "entry",
                "TECH-0003": "entry",
                "TECH-0004": "data",
                "TECH-0005": "event",
                "TECH-0006": "ops",
                "TECH-0007": "ops",
                "TECH-0008": "event",
                "ARCH-0000": "compute",
            },
        )
        node = re.compile(r"^\s*([A-Z][A-Z0-9_]*-\d{3,}).*:::([a-z][a-z0-9_-]*)\s*$")
        class_def = re.compile(r"^\s*classDef\s+([a-z][a-z0-9_-]*)\s+")
        solid = re.compile(
            r"^\s*[A-Z][A-Z0-9_]*-\d{3,}\s*-->\|[^|]+\|\s*"
            r"[A-Z][A-Z0-9_]*-\d{3,}\s*$"
        )
        dashed = re.compile(
            r'^\s*[A-Z][A-Z0-9_]*-\d{3,}\s*-\.\s*"[^"]+"\s*\.->\s*'
            r"[A-Z][A-Z0-9_]*-\d{3,}\s*$"
        )
        for index, block in enumerate(blocks):
            with self.subTest(block=index + 1):
                first = next(
                    line.strip() for line in block.splitlines() if line.strip()
                )
                self.assertEqual(first, LINEAR_DIAGRAM_CONFIG)
                declaration = next(
                    line.strip()
                    for line in block.splitlines()
                    if line.strip() and line.strip() != LINEAR_DIAGRAM_CONFIG
                )
                self.assertEqual(
                    declaration,
                    ("flowchart TB", "flowchart TB", "flowchart LR", "flowchart TB")[
                        index
                    ],
                )
                self.assertEqual(block.count("accTitle:"), 1)
                self.assertEqual(block.count("accDescr:"), 1)
                for line in block.splitlines():
                    if "-->" in line or "-." in line:
                        self.assertTrue(
                            solid.fullmatch(line) or dashed.fullmatch(line),
                            line,
                        )
        for index, roles in enumerate(expected_roles):
            with self.subTest(broad_block=index + 1):
                observed_roles = {
                    match.group(1): match.group(2)
                    for line in blocks[index].splitlines()
                    if (match := node.fullmatch(line)) is not None
                }
                declared = {
                    match.group(1)
                    for line in blocks[index].splitlines()
                    if (match := class_def.match(line)) is not None
                }
                self.assertEqual(observed_roles, roles)
                self.assertEqual(declared, set(roles.values()))
        self.assertIn(
            'TECH-0003 -. "provides token issuer trust to" .-> TECH-0002',
            blocks[1],
        )
        self.assertIn(
            'TECH-0005 -. "restores" .-> ARCH-0000',
            blocks[0],
        )
        self.assertIn(
            'TECH-0007 -. "delivers and rolls back" .-> TECH-0001',
            blocks[1],
        )
        self.assertIn(
            "accTitle: Customer journey with a safe alternate path", blocks[2]
        )
        self.assertIn(
            'API-000 -. "uses the recovery path" .-> TECH-0005',
            blocks[2],
        )
        self.assertIn(
            'TECH-0005 -. "returns to" .-> API-000',
            blocks[2],
        )
        self.assertIn("accTitle: Compact project state flow", blocks[3])
        self.assertIn(
            "ARCH-0000 -->|permits DRAFT to VALIDATED<br/>and VALIDATED to PUBLISHED| STATE-000",
            blocks[3],
        )
        self.assertNotRegex(blocks[3], r"(STATE-\d{3})\s+-->[^\n]+\1")

    def test_prd_binds_project_specific_diagram_semantics_and_rendering(self) -> None:
        prd = (REPOSITORY_ROOT / "docs" / "project" / "PRD.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(prd.split())
        self.assertIn("### Project diagram contract", prd)
        self.assertIn("Diagrams describe planned design", normalized)
        design = (
            REPOSITORY_ROOT / ".agents/skills/fastlane/references/design.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "project-specific Mermaid block",
            "complete top-to-bottom architecture",
            "concise top-to-bottom AWS implementation map",
            "semantic digest",
            "presentation-source digest",
            "Diagrams never prove implementation, deployment, or authority",
        ):
            self.assertIn(phrase, design)

    def test_prd_explains_complete_material_aws_design_coverage(self) -> None:
        prd = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        expected_concerns = (
            "Compute",
            "API and edge",
            "Identity",
            "Data",
            "Messaging",
            "Observability",
            "Deployment",
            "Secrets and encryption",
        )
        section = prd.split("## 20. AWS implementation approach", 1)[1].split(
            "### Lightweight Well-Architected decision review", 1
        )[0]
        normalized_section = " ".join(section.split())
        concerns = tuple(
            match.group(1)
            for match in re.finditer(r"(?m)^\| ([^|]+?) \| TODO \|", section)
        )
        self.assertEqual(concerns, expected_concerns)
        for phrase in (
            "material AWS implementation concern",
            "not a catalog of every AWS service",
            "Gate A approves product requirements and constraints",
            "full architecture diagram for Gate B",
            "One row may use several services or mechanisms",
        ):
            self.assertIn(phrase, normalized_section)
        self.assertNotIn("| Messaging or orchestration |", section)
        self.assertNotIn("| Networking |", section)

    def test_fresh_prd_uses_canonical_design_status_and_targeted_release_acceptance(
        self,
    ) -> None:
        prd = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        self.assertNotIn("| Design status |", prd)
        document_status = prd.split("## Document status", 1)[1].split(
            "### Delivery profile overlays", 1
        )[0]
        self.assertEqual(document_status.count("| Current design revision |"), 1)
        self.assertEqual(document_status.count("| Gate B derived status |"), 1)
        release = prd.split("## 26. Release acceptance", 1)[1].split(
            "# Gate B Review", 1
        )[0]
        normalized_release = " ".join(release.split())
        for statement in (
            "Local release work is complete only when:",
            "AWS targets are accepted independently",
            "`READY_TO_DEPLOY` does not mean deployed",
            "`RELEASE_VERIFIED` does not imply recovery or teardown",
            "Unobserved AWS work remains explicit",
        ):
            self.assertIn(statement, normalized_release)
        self.assertNotIn(
            "deployment, monitoring, rollback, recovery, and cleanup are verified",
            release,
        )

    def test_each_mermaid_block_is_checked_independently(self) -> None:
        fixture = """
```mermaid
sequenceDiagram
    API->>API: Authorize, validate, and apply idempotency
    API->>Data: Persist approved data
```
```mermaid
sequenceDiagram
    API->>Data: Persist approved data
    API->>API: Authorize, validate, and apply idempotency
```
"""
        self.assertEqual(
            persistence_order_failures(fixture),
            ["Mermaid block 2 persists before authorization"],
        )

    def test_project_disclosures_are_balanced_labeled_and_keep_critical_content_visible(
        self,
    ) -> None:
        project_documents = tuple(
            REPOSITORY_ROOT / "docs" / "project" / name
            for name in ("PRD.md", "TASKS.md", "VERIFY.md", "RUNBOOK.md")
        )
        failures: list[str] = []
        for path in project_documents:
            source = path.read_text(encoding="utf-8")
            lines = source.splitlines()
            annotated = disclosure_lines(source)
            for index, (_number, line, depth) in enumerate(annotated):
                if line == "<details>":
                    next_line = next(
                        (item.strip() for item in lines[index + 1 :] if item.strip()),
                        "",
                    )
                    if not (
                        next_line.startswith("<summary>")
                        and next_line.endswith("</summary>")
                    ):
                        failures.append(
                            f"{path.name}: unlabeled disclosure near line {index + 1}"
                        )
                if line == "```mermaid" and depth:
                    failures.append(
                        f"{path.name}: Mermaid block hidden near line {index + 1}"
                    )
                if (
                    path.name == "RUNBOOK.md"
                    and line in {"```bash", "```powershell", "```sh"}
                    and depth
                ):
                    failures.append(
                        f"{path.name}: operator command hidden near line {index + 1}"
                    )
                if "bootstrap:" in line and "-receipt:" in line and depth:
                    failures.append(
                        f"{path.name}: formal receipt hidden near line {index + 1}"
                    )
        self.assertEqual(failures, [])

    def test_required_project_diagrams_are_visible_unindented_and_stably_anchored(
        self,
    ) -> None:
        source_text = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(
            encoding="utf-8"
        )
        lines = source_text.splitlines()
        annotated = disclosure_lines(source_text)
        depth_by_line = {number: depth for number, _line, depth in annotated}
        required = {
            "### Proposed system at a glance": "proposed-system-at-a-glance",
            "### AWS implementation at a glance": "aws-implementation-at-a-glance",
            "### Sequence — primary outcome": "sequence--primary-outcome",
        }
        mermaid_fence = chr(96) * 3 + "mermaid"
        for heading, expected_anchor in required.items():
            empty_slot_text = (
                "No project architecture diagram has been created yet."
                if expected_anchor == "proposed-system-at-a-glance"
                else (
                    "No AWS implementation diagram has been created yet."
                    if expected_anchor == "aws-implementation-at-a-glance"
                    else "No primary-outcome sequence has been created yet."
                )
            )
            self.assertEqual(lines.count(heading), 1, heading)
            heading_index = lines.index(heading)
            next_heading = next(
                (
                    index
                    for index in range(heading_index + 1, len(lines))
                    if lines[index].startswith("#")
                ),
                len(lines),
            )
            mermaid_index = next(
                (
                    index
                    for index in range(heading_index + 1, next_heading)
                    if lines[index] == mermaid_fence
                ),
                None,
            )
            self.assertEqual(depth_by_line[heading_index + 1], 0)
            if mermaid_index is None:
                slot = " ".join(lines[heading_index + 1 : next_heading])
                self.assertIn(empty_slot_text, slot, heading)
                self.assertNotIn("NOT_YET_CREATED", slot, heading)
            else:
                self.assertEqual(lines[mermaid_index], lines[mermaid_index].lstrip())
                self.assertFalse(lines[mermaid_index].startswith("|"))
                self.assertEqual(depth_by_line[mermaid_index + 1], 0)
            anchor = github_anchor(heading[4:])
            self.assertEqual(anchor, expected_anchor)

    def test_prd_diagram_guide_links_without_copying_diagrams(self) -> None:
        prd = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        self.assertEqual(prd.count("# Diagram guide"), 1)
        self.assertGreater(
            prd.index("# Diagram guide"), prd.index("# Contract Appendices")
        )
        guide = prd.split("# Diagram guide", 1)[1]
        self.assertNotIn("```mermaid", guide)
        links = re.findall(r"\[([^]]+)\]\((#[^)]+)\)", guide)
        self.assertEqual(
            links,
            [
                ("View complete architecture", "#proposed-system-at-a-glance"),
                ("View AWS implementation", "#aws-implementation-at-a-glance"),
                ("View first useful outcome", "#sequence--primary-outcome"),
                ("View journey paths", "#journey-view"),
                ("View state lifecycle", "#state-view"),
                ("View data lifecycle", "#data-lifecycle-view"),
                ("View failure and recovery", "#sequence--failure-and-recovery"),
                ("View migration", "#migration-view"),
            ],
        )
        targets = [target for _label, target in links]
        self.assertEqual(len(targets), len(set(targets)))
        h1_headings = re.findall(r"(?m)^# [^#].+$", prd)
        self.assertEqual(h1_headings[-1], "# Diagram guide")
        self.assertTrue(prd.rstrip().endswith("[View migration](#migration-view) |"))

    def test_gate_b_decision_surface_keeps_the_exact_receipt_last(self) -> None:
        prd = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        gate_b = prd.split("# Gate B Review", 1)[1].split("# Contract Appendices", 1)[0]
        self.assertTrue(
            gate_b.strip().endswith("<!-- bootstrap:gate-b-receipt:end -->"),
            gate_b[-500:],
        )

    def test_gate_b_technical_index_links_each_owner_source(self) -> None:
        prd = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        index = prd.split("## Technical decision index", 1)[1].split(
            "## 27. Gate B agent review record", 1
        )[0]
        self.assertEqual(
            github_anchor("Gate B — readiness card"),
            "gate-b--readiness-card",
        )
        expected = {
            "[current project diagrams](#diagram-guide)": "# Diagram guide",
            "[Gate B readiness card](#gate-b--readiness-card)": (
                "### Gate B — readiness card"
            ),
            "[exact construction envelope](#28-construction-envelope)": (
                "## 28. Construction envelope"
            ),
        }
        for link, heading in expected.items():
            with self.subTest(link=link):
                self.assertIn(link, index)
                self.assertEqual(prd.count(heading), 1)

    def test_prd_disclosures_explain_and_contain_the_promised_records(self) -> None:
        prd = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        disclosures = PRD_DISCLOSURE.findall(prd)
        self.assertEqual(len(disclosures), prd.count("<details>"))
        self.assertGreater(len(disclosures), 0)

        for summary, body in disclosures:
            with self.subTest(summary=summary):
                self.assertRegex(summary, r"^(?:Exact|Detailed)\s+")
                introduction = body.strip().split("\n\n", 1)[0]
                self.assertNotRegex(introduction, r"^(?:#|\||[-*]\s|```)")
                self.assertRegex(introduction, r"[.!?](?:\s|$)")
                has_table = re.search(r"(?m)^\|.*\|\s*\n\|[-:| ]+\|", body) is not None
                has_list = re.search(r"(?m)^(?:[-*]|\d+\.)\s+", body) is not None
                has_code = chr(96) * 3 in body
                self.assertTrue(
                    has_table or has_list or has_code,
                    f"{summary} explains records but does not contain them",
                )

        gate_b_body = dict(disclosures)["Detailed Gate B readiness basis"]
        self.assertIn(
            "| Field | Current design and construction decision basis |",
            gate_b_body,
        )
        for field in (
            "Design basis IDs",
            "Architecture/components",
            "Technology/toolchains/version policy",
            "Interfaces/data flow",
            "Identity/secrets",
            "Failure/retry/concurrency",
            "Deployment/operations",
            "Validation/evidence",
            "Rollback/recovery/teardown",
            "Brownfield compatibility/migration",
            "Outstanding gaps",
        ):
            self.assertIn(f"| {field} |", gate_b_body)

    def test_numbered_record_headings_are_visible_and_records_fold_together(
        self,
    ) -> None:
        prd = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        depth_by_line = {
            number: depth for number, _line, depth in disclosure_lines(prd)
        }
        disclosures = dict(PRD_DISCLOSURE.findall(prd))
        cases = (
            (
                "## 13. Cross-requirement analysis",
                "Exact Gate A analysis, lineage, assumptions, and open-decision records",
                "These records show the findings, changes, assumptions, and unresolved decisions",
                (
                    "| ID | Type | Requirements involved | Finding | Resolution or decision | Blocking? | Status |",
                    "| RA-001 |",
                    "| Current revision | Prior revision | Trigger | Added IDs | Changed IDs | Removed IDs | Preserved IDs | Stale reason | Required revalidation |",
                    "| REQ-0001 |",
                    "| Assumption ID | Assumption | Status | Basis IDs | Validation or successor |",
                    "| ASM-001 |",
                    "| ID | Decision needed | Options | Decision owner | Blocking? | Resolution |",
                    "| DEC-001 |",
                    "| Field | Agent-recorded value |",
                    "| Requirements revision analyzed |",
                ),
            ),
            (
                "## 27. Gate B agent review record",
                "Detailed Gate B independent review record",
                "This record shows what the independent read-only review examined",
                (
                    "| Field | Agent-recorded value |",
                    "| Requirements revision reviewed |",
                ),
            ),
            (
                "## 28. Construction envelope",
                "Exact construction envelope",
                "This record defines the bounded local work Codex may perform after Gate B.",
                (
                    "| Boundary | Authorized value |",
                    "| Construction authorization ID |",
                ),
            ),
        )
        for heading, summary, introduction, required_records in cases:
            with self.subTest(heading=heading):
                self.assertEqual(prd.count(heading), 1)
                heading_line = prd.splitlines().index(heading) + 1
                self.assertEqual(depth_by_line[heading_line], 0)

                body = disclosures[summary]
                self.assertNotIn(heading, body)
                self.assertIn(introduction, " ".join(body.split()))
                for required_record in required_records:
                    self.assertIn(required_record, body)

    def test_project_owner_paths_stay_within_readability_ceilings(self) -> None:
        ceilings = {
            "PRD.md": 330,
            "TASKS.md": 65,
            "VERIFY.md": 90,
            "RUNBOOK.md": 220,
            "BUGFIX.md": 90,
        }
        for name, ceiling in ceilings.items():
            with self.subTest(document=name):
                source = (REPOSITORY_ROOT / "docs/project" / name).read_text(
                    encoding="utf-8"
                )
                self.assertLessEqual(len(rendered_visible_lines(source)), ceiling)

    def test_prd_contains_records_but_no_framework_maintenance_instructions(
        self,
    ) -> None:
        prd = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        for phrase in (
            "Use only",
            "Replace this table",
            "During DESIGN-10",
            "During REQ-10",
            "schema migration",
            "canonical order",
            "parser-controlled",
            "CreateChangeSet",
            "ValidatePolicy",
            "The Engine owns",
            "recompute the",
            "sort rows",
        ):
            self.assertNotIn(phrase, prd)

    def test_owner_reading_path_keeps_actions_boundaries_and_receipts_visible(
        self,
    ) -> None:
        prd = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        tasks = (REPOSITORY_ROOT / "docs/project/TASKS.md").read_text(encoding="utf-8")
        verify = (REPOSITORY_ROOT / "docs/project/VERIFY.md").read_text(
            encoding="utf-8"
        )
        runbook = (REPOSITORY_ROOT / "docs/project/RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        visible = {
            "PRD.md": visible_outside_disclosures(prd),
            "TASKS.md": visible_outside_disclosures(tasks),
            "VERIFY.md": visible_outside_disclosures(verify),
            "RUNBOOK.md": visible_outside_disclosures(runbook),
        }
        required = {
            "PRD.md": (
                "# Gate A Review",
                "# Gate B Review",
                "## Construction and authorization boundary",
                "<!-- bootstrap:gate-a-receipt:start -->",
                "<!-- bootstrap:gate-b-receipt:start -->",
            ),
            "TASKS.md": (
                "## Current progress",
                "## Active work, blockers, and next action",
            ),
            "VERIFY.md": (
                "## Current result",
                "<!-- bootstrap:aws-read-preflight-receipt:start -->",
                "<!-- bootstrap:aws-deployment-receipt:start -->",
                "<!-- bootstrap:aws-teardown-receipt:start -->",
            ),
            "RUNBOOK.md": (
                "## Safety boundary",
                "## 6. Deployment",
                "## 10. Rollback",
                "## 11. Backup and recovery",
                "## 13. Teardown and decommissioning",
            ),
        }
        for name, phrases in required.items():
            for phrase in phrases:
                self.assertIn(phrase, visible[name], (name, phrase))

        forbidden_visible_instructions = (
            "Fastlane EARS Contract",
            "Compatibility is revision-bound",
            "modern design digest",
            "The release lifecycle is",
            "A Harness Profile row that",
            "canonical_sha256",
            "context_plan",
            "maximum_initial_source_bytes",
            "parser-controlled",
        )
        owner_path = "\n".join(visible.values())
        for phrase in forbidden_visible_instructions:
            self.assertNotIn(phrase, owner_path)

        for line in visible["PRD.md"].splitlines():
            if not (line.startswith("|") and line.endswith("|")):
                continue
            columns = len(re.findall(r"(?<!\\)\|", line)) - 1
            self.assertLessEqual(columns, 6, ("PRD.md", columns, line))

    def test_runbook_command_examples_do_not_look_like_document_headings(
        self,
    ) -> None:
        runbook = (REPOSITORY_ROOT / "docs/project/RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        misleading = (
            "# Add workload-specific read-only checks.",
            "# Format, lint, type-check, test, validate infrastructure, and scan dependencies",
            "# Health, primary flow, authorization, persistence, and integrations",
            "# Dry run or inventory",
            "# Execution only under the exact teardown authorization",
            "# Resource inventory checks",
            "# Billing and cost checks",
        )
        for line in misleading:
            self.assertNotIn(line, runbook)

    def test_all_five_receipt_blocks_match_the_1_2_3_base_bytes(self) -> None:
        locations = {
            "gate-a-receipt": "docs/project/PRD.md",
            "gate-b-receipt": "docs/project/PRD.md",
            "aws-read-preflight-receipt": "docs/project/VERIFY.md",
            "aws-deployment-receipt": "docs/project/VERIFY.md",
            "aws-teardown-receipt": "docs/project/VERIFY.md",
        }
        for marker, relative_path in locations.items():
            source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
            start = f"<!-- bootstrap:{marker}:start -->"
            end = f"<!-- bootstrap:{marker}:end -->"
            block = source[source.index(start) : source.index(end) + len(end)] + "\n"
            self.assertEqual(
                hashlib.sha256(block.encode("utf-8")).hexdigest(),
                RECEIPT_SHA256[marker],
                marker,
            )

    def test_automatic_agents_context_has_explicit_headroom(self) -> None:
        root_agents = REPOSITORY_ROOT / "AGENTS.md"
        chains = {
            "root": [root_agents],
            "app": [root_agents],
            "infrastructure": [
                root_agents,
                REPOSITORY_ROOT / "infrastructure" / "AGENTS.md",
            ],
            "tests": [root_agents, REPOSITORY_ROOT / "tests" / "AGENTS.md"],
            "scripts": [root_agents, REPOSITORY_ROOT / "scripts" / "AGENTS.md"],
        }
        sizes = {
            name: sum(len(path.read_bytes()) for path in paths)
            for name, paths in chains.items()
        }
        self.assertLessEqual(max(sizes.values()), MAX_AGENT_CONTEXT_BYTES, sizes)

    def test_nested_agent_guides_explicitly_narrow_root_authority(self) -> None:
        root_agents = (REPOSITORY_ROOT / "AGENTS.md").resolve()
        nested_guides = sorted(
            path
            for path in source_files(REPOSITORY_ROOT)
            if path.name == "AGENTS.md" and path.resolve() != root_agents
        )
        self.assertTrue(nested_guides)
        for guide in nested_guides:
            with self.subTest(guide=guide.relative_to(REPOSITORY_ROOT)):
                self.assertIn(
                    NESTED_AGENT_SCOPE_MARKER,
                    guide.read_text(encoding="utf-8"),
                )

    def test_docs_governance_and_index_are_compact_and_linked(self) -> None:
        guide = (
            REPOSITORY_ROOT
            / ".agents/skills/maintain-fastlane/references/documentation-governance.md"
        )
        index = REPOSITORY_ROOT / "docs" / "README.md"
        workflow = REPOSITORY_ROOT / "docs" / "WORKFLOW.md"
        self.assertFalse((REPOSITORY_ROOT / "docs/AGENTS.md").exists())
        self.assertLessEqual(len(guide.read_text(encoding="utf-8").splitlines()), 70)
        self.assertLessEqual(
            len(workflow.read_text(encoding="utf-8").splitlines()), 370
        )
        self.assertLessEqual(len(workflow.read_bytes()), 17_000)
        index_text = index.read_text(encoding="utf-8")
        self.assertIn("Mermaid", index_text)
        for target in (
            "SETUP.md",
            "WORKFLOW.md",
            "TROUBLESHOOTING.md",
            "../.codex/hooks/README.md",
            "DEPENDENCY-POLICY.md",
            "project/PRD.md",
            "project/TASKS.md",
            "project/VERIFY.md",
            "project/RUNBOOK.md",
            "project/BUGFIX.md",
        ):
            self.assertIn(f"]({target})", index_text)
            self.assertTrue((index.parent / target).is_file(), target)
        for maintainer_target in (
            "../.agents/skills/maintain-fastlane/SKILL.md",
            "../.agents/skills/maintain-fastlane/references/evaluation.md",
            "../.agents/skills/maintain-fastlane/references/qualification.md",
        ):
            self.assertNotIn(f"]({maintainer_target})", index_text)
        for removed in (
            "docs/AGENTS.md",
            "docs/QUALIFICATION.md",
            "docs/SHOWCASE.md",
            "docs/advanced",
            "docs/assets",
            "docs/maintainers",
        ):
            self.assertFalse((REPOSITORY_ROOT / removed).exists(), removed)

    def test_customer_document_navigation_is_role_and_action_oriented(self) -> None:
        workflow = (REPOSITORY_ROOT / "docs/WORKFLOW.md").read_text(encoding="utf-8")
        dependency = (REPOSITORY_ROOT / "docs/DEPENDENCY-POLICY.md").read_text(
            encoding="utf-8"
        )
        troubleshooting = (REPOSITORY_ROOT / "docs/TROUBLESHOOTING.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("**Contents:**", workflow)
        for target in (
            "#first-run",
            "#customer-delivery-lifecycle",
            "#gate-a--product-owner-brief",
            "#design-and-gate-b--technical-owner-brief",
            "#architecture-diagrams-and-the-professional-board",
            "#how-the-control-plane-works",
            "#canonical-records-and-traceability",
            "#aws-core-and-aws-authority",
            "#build-resume-and-optional-hooks",
        ):
            self.assertIn(f"]({target})", workflow)

        self.assertIn("**Project owners:**", dependency)
        self.assertIn("**Maintainers:**", dependency)
        for target in (
            "#aws-core",
            "#privacy-and-authority",
            "#ruff",
            "#mermaid-rendering",
            "#github-actions",
        ):
            self.assertIn(f"]({target})", dependency)

        self.assertIn("| Symptom | Start here |", troubleshooting)
        for target in (
            "#read-only-checks",
            "#init-template-repeats-setup",
            "#aws-core-is-missing",
            "#aws-core-research-fails-later",
            "#a-gate-becomes-stale",
            "#optional-hooks-deny-a-valid-action",
            "#another-blocker-appears",
        ):
            self.assertIn(f"]({target})", troubleshooting)

        setup = (REPOSITORY_ROOT / "docs/SETUP.md").read_text(encoding="utf-8")
        self.assertIn("pipx install uv", setup)
        self.assertIn("uvx --version", setup)
        self.assertIn("docs.astral.sh/uv/getting-started/installation", setup)

        owner_workflow = workflow
        self.assertEqual(owner_workflow.count("```mermaid"), 2)
        self.assertEqual(owner_workflow.count("flowchart TB"), 2)
        self.assertNotIn("<br", owner_workflow)
        for customer_explanation in (
            "## Customer delivery lifecycle",
            "## How the control plane works",
            "ProjectSnapshot",
            "EngineEvaluation",
            "Authority intersection",
            "Schema-2 report",
            "task_waves.py",
            "Reconciliation means Fastlane compared expected and observed AWS state.",
        ):
            self.assertIn(customer_explanation, owner_workflow)
        for internal_term in (
            "canonical digest",
            "schema-migration",
            "EARS",
            "QAS",
            "Harness Profile",
            "maximum_initial_bytes",
            "resolved_initial_slices",
        ):
            self.assertNotIn(internal_term, owner_workflow)

    def test_readme_is_a_compact_product_first_landing_page(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        workflow = (REPOSITORY_ROOT / "docs/WORKFLOW.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(readme.splitlines()), 140)
        self.assertLessEqual(len(readme.encode("utf-8")), 9_000)
        self.assertLess(len(readme.splitlines()), len(workflow.splitlines()) // 2)

        headings = (
            "## Quick start",
            "## Why Fastlane is different",
            "## Product lifecycle",
            "## Supported project work",
            "## What the repository retains",
            "## Trust and evidence boundary",
            "## Documentation",
        )
        for heading in headings:
            self.assertIn(heading, readme)
        self.assertEqual(
            [readme.index(heading) for heading in headings],
            sorted(readme.index(heading) for heading in headings),
        )

        pitch_match = re.search(
            r"^AWS Codex Fastlane is an owner-controlled AWS delivery workflow "
            r"for Codex\..*?AWS permission\.$",
            readme,
            re.MULTILINE,
        )
        self.assertIsNotNone(pitch_match)
        pitch_words = re.findall(r"\b[\w’'-]+\b", pitch_match.group(0))
        self.assertGreaterEqual(len(pitch_words), 70)
        self.assertLessEqual(len(pitch_words), 95)

        start_action = (
            "**[Use this template →](https://github.com/"
            "Levi-Breedlove/codex-aws-aidlc/generate)**"
        )
        self.assertLess(readme.index(start_action), readme.index("## Quick start"))
        self.assertEqual(readme.count("img.shields.io/"), 3)
        self.assertNotIn("actions/workflows/", readme)

        for product_claim in (
            "owner-controlled AWS delivery workflow for Codex",
            "AWS software and infrastructure",
            "evidence-backed local result",
            "Canonical project records—not chat memory",
            "Gate A approves what should be built",
            "Gate B approves the technical plan and bounded local construction",
            "Build never deploys",
            "Source-assisted Define",
            "New AWS application",
            "Existing application",
            "Infrastructure-only work",
            "Product Agreement",
            "Fastlane Engine",
            "A local pass never proves AWS behavior",
            "Deployment never authorizes teardown",
        ):
            self.assertIn(product_claim, readme)

        self.assertNotIn("## What has actually been proven", readme)
        self.assertNotIn("FRAMEWORK_RELEASE_QUALIFIED", readme)
        self.assertNotIn("PRODUCT_FIELD_VALIDATED", readme)
        self.assertIsNone(re.search(r"\b[0-9a-fA-F]{64}\b", readme))

        self.assertEqual(readme.count("```mermaid"), 1)
        self.assertEqual(readme.count("flowchart TB"), 1)
        self.assertEqual(readme.count("accTitle:"), 1)
        self.assertEqual(readme.count("accDescr:"), 1)
        self.assertIn("accTitle: AWS Codex Fastlane product lifecycle", readme)
        for lifecycle_edge in (
            "DEFINE --> GATEA",
            'GATEA -->|"Approve"| DESIGN',
            "DESIGN --> GATEB",
            'GATEB -->|"Approve"| LOCAL',
            "LOCAL --> REVIEW",
            'REVIEW -. "Separate exact authorization" .-> AWS',
            'AWS -->|"Record observed result"| REVIEW',
        ):
            self.assertIn(lifecycle_edge, readme)
        for unsupported_mermaid in (
            "subgraph ",
            "classDef ",
            "<br",
            "flowchart TD",
            "flowchart LR",
        ):
            self.assertNotIn(unsupported_mermaid, readme)

        for implementation_detail in (
            "ProjectSnapshot",
            "EngineEvaluation",
            "Schema-2",
            "task_waves.py",
            "parser",
            "digest",
            "## Skills and agents",
            "## How Fastlane works under the hood",
            "accTitle: Fastlane technical control plane",
        ):
            self.assertNotIn(implementation_detail, readme)
        self.assertIsNone(
            re.search(
                r"\b(?:BOOT|INTAKE|REQ|DESIGN|TASK|BUILD|RELEASE|AWS)-\d{2}\b",
                readme,
            )
        )

        self.assertIn("## Customer delivery lifecycle", workflow)
        self.assertIn("accTitle: Fastlane customer delivery lifecycle", workflow)
        self.assertIn("### Architecture diagrams and the professional board", workflow)
        self.assertIn(
            "Every project includes system-context, primary-outcome, and AWS-implementation",
            workflow,
        )
        self.assertIn("not a third gate", workflow)
        self.assertIn("## How the control plane works", workflow)
        self.assertIn("accTitle: Fastlane technical control plane", workflow)
        self.assertIn("ProjectSnapshot", workflow)
        self.assertIn("EngineEvaluation", workflow)
        self.assertIn("task_waves.py", workflow)

        def substantial_lines(source: str) -> set[str]:
            prose = re.sub(r"```mermaid.*?```", "", source, flags=re.DOTALL)
            return {
                line.strip()
                for line in prose.splitlines()
                if len(line.strip()) >= 40
                and not line.lstrip().startswith(("#", "- [", "```"))
            }

        shared_lines = substantial_lines(readme) & substantial_lines(workflow)
        self.assertLessEqual(len(shared_lines), 12, msg=sorted(shared_lines))

    def test_render_review_inputs_are_exact_sanitized_and_organized(self) -> None:
        fixtures = render_mermaid_fixtures.collect_mermaid_fixtures(REPOSITORY_ROOT)
        self.assertEqual(
            tuple(fixtures),
            (
                *render_mermaid_fixtures.PUBLISHED_NAMES,
                *render_mermaid_fixtures.GOLDEN_NAMES,
                *render_mermaid_fixtures.VARIANT_NAMES,
            ),
        )
        self.assertEqual(len(fixtures), 11)
        expected_golden_markers = {
            "golden-complete-architecture": (
                "accTitle: Complete proposed review application architecture",
                "ACT-001 -->|sends a review request through| TECH-0013",
            ),
            "golden-primary-outcome": (
                "accTitle: First useful owner outcome",
                "ACT-001 -->|submits a review request to| API-001",
            ),
            "golden-data-lifecycle": (
                "accTitle: Owner record data lifecycle",
                "API-001 -->|validates and stores in| TECH-0011",
            ),
            "golden-failure-recovery": (
                "accTitle: Review failure and recovery path",
                "API-001 -->|fails safely and invokes| TECH-0015",
            ),
            "golden-aws-implementation": (
                "accTitle: Proposed AWS implementation",
                'TECH-0010 -. "provides token issuer trust to" .-> TECH-0013',
            ),
            "golden-brownfield-migration": (
                "accTitle: Existing application compatibility and rollback",
                "BOUNDARY-001 -->|routes existing requests to| ARCH-0001",
                'TECH-0015 -. "restores" .-> ARCH-0001',
            ),
            "golden-infrastructure-aws": (
                "accTitle: Infrastructure-only AWS implementation",
                'TECH-0004 -. "defines changes for" .-> TECH-0009',
                'TECH-0009 -. "deploys" .-> TECH-0001',
            ),
        }
        for name, markers in expected_golden_markers.items():
            for marker in markers:
                self.assertIn(marker, fixtures[name], name)
        complete = fixtures["golden-complete-architecture"]
        self.assertTrue(complete.startswith(LINEAR_DIAGRAM_CONFIG + "\nflowchart TB\n"))
        self.assertEqual(complete.count("classDef "), 6)
        organized_groups = (
            'subgraph PEOPLE["People"]',
            'subgraph AWS_CLOUD["AWS Cloud',
            'subgraph REGION["AWS Region',
            'subgraph ENTRY["Managed entry and identity"]',
            'subgraph APPLICATION["Application · trust boundary"]',
            'subgraph DATA["Owner data and safeguards"]',
            'subgraph OPERATIONS["Operations, delivery, and recovery"]',
        )
        self.assertEqual(
            [complete.index(marker) for marker in organized_groups],
            sorted(complete.index(marker) for marker in organized_groups),
        )
        published_journey = fixtures["published-journey-flow"]
        self.assertTrue(
            published_journey.startswith(LINEAR_DIAGRAM_CONFIG + "\nflowchart LR\n")
        )
        self.assertIn(
            "accTitle: Customer journey with a safe alternate path",
            published_journey,
        )
        self.assertIn(
            'API-000 -. "uses the recovery path" .-> TECH-0005',
            published_journey,
        )
        self.assertIn(
            'TECH-0005 -. "returns to" .-> API-000',
            published_journey,
        )
        published_state = fixtures["published-state-flow"]
        self.assertTrue(
            published_state.startswith(LINEAR_DIAGRAM_CONFIG + "\nflowchart TB\n")
        )
        self.assertIn("accTitle: Compact project state flow", published_state)
        self.assertIn('ARCH-0000["Project application"]:::compute', published_state)
        self.assertIn(
            'STATE-000["DRAFT<br/>VALIDATED<br/>PUBLISHED"]:::event',
            published_state,
        )
        self.assertIn(
            "classDef compute fill:#FFF1E8,stroke:#D86613,color:#232F3E;",
            published_state,
        )
        self.assertIn(
            "classDef event fill:#F3ECFF,stroke:#8C4FFF,color:#232F3E;",
            published_state,
        )
        self.assertIn(
            "ARCH-0000 -->|permits DRAFT to VALIDATED<br/>and VALIDATED to PUBLISHED| STATE-000",
            published_state,
        )
        self.assertNotRegex(published_state, r"(STATE-\d{3})\s+-->[^\n]+\1")
        with tempfile.TemporaryDirectory() as directory:
            synthetic_root = Path(directory) / "initialized-adopter"
            pattern_path = (
                synthetic_root
                / ".agents/skills/fastlane/references/diagram-patterns.md"
            )
            pattern_path.parent.mkdir(parents=True)
            pattern_path.write_text(
                (
                    REPOSITORY_ROOT
                    / ".agents/skills/fastlane/references/diagram-patterns.md"
                ).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            adopter_prd = synthetic_root / "docs/project/PRD.md"
            adopter_prd.parent.mkdir(parents=True)
            adopter_prd.write_text(
                "SECRET_CUSTOMER_MARKER\n```mermaid\nflowchart LR\nA --> B\n```\n",
                encoding="utf-8",
            )
            adopter_fixtures = render_mermaid_fixtures.collect_mermaid_fixtures(
                synthetic_root
            )
            self.assertEqual(adopter_fixtures, fixtures)
            self.assertNotIn(
                "SECRET_CUSTOMER_MARKER",
                "\n".join(adopter_fixtures.values()),
            )

            output_dir = Path(directory) / "rendered-inputs"
            outputs = render_mermaid_fixtures.write_mermaid_fixtures(output_dir)
            self.assertEqual(len(outputs), 11)
            self.assertEqual(
                {path.name for path in outputs},
                {f"{name}.mmd" for name in fixtures},
            )
            for path in outputs:
                source = path.read_text(encoding="utf-8")
                self.assertTrue(
                    source.startswith(LINEAR_DIAGRAM_CONFIG + "\nflowchart "), path.name
                )
                self.assertTrue(source.endswith("\n"), path.name)
                self.assertNotIn("TODO", source)
                self.assertNotIn("PLACEHOLDER", source)
                self.assertNotRegex(source, r"(?i)arn:aws|aws_access_key|secret_key")
                self.assertNotRegex(source, r"[A-Z]:\\|/(?:Users|home)/")
                self.assertNotRegex(source, r"(?<!\d)\d{12}(?!\d)")

    def test_complete_golden_prds_align_with_the_rendered_diagram_corpus(
        self,
    ) -> None:
        mermaid = render_mermaid_fixtures.collect_mermaid_fixtures(REPOSITORY_ROOT)
        prds = render_mermaid_fixtures.collect_prd_fixtures()
        self.assertEqual(tuple(prds), render_mermaid_fixtures.PRD_NAMES)
        self.assertEqual(
            tuple(render_mermaid_fixtures._golden_record_overrides()),
            render_mermaid_fixtures.GOLDEN_RECORD_PATHS,
        )
        for name, (source, _report) in prds.items():
            write_set = test_bootstrap_doctor.doctor.table_after_heading(
                source, "## 28. Construction envelope"
            )["Allowed repository write set"]
            if name == render_mermaid_fixtures.PRD_NAMES[0]:
                self.assertNotIn("dist/architecture/**", write_set)
            else:
                self.assertIn("dist/architecture/**", write_set)
        self.assertEqual(
            prds[render_mermaid_fixtures.PRD_NAMES[1]][1]["write_authority"][
                "approved_write_roots"
            ],
            [],
        )
        self.assertEqual(
            prds[render_mermaid_fixtures.PRD_NAMES[2]][1]["write_authority"][
                "approved_write_roots"
            ],
            ["legacy/**", "tests/**", "dist/architecture/**"],
        )
        self.assertEqual(
            prds[render_mermaid_fixtures.PRD_NAMES[3]][1]["write_authority"][
                "approved_write_roots"
            ],
            ["infrastructure/**", "tests/**", "dist/architecture/**"],
        )
        with tempfile.TemporaryDirectory() as directory:
            outputs = render_mermaid_fixtures.write_review_fixtures(Path(directory))
            self.assertEqual(len(outputs), 15)
            self.assertEqual(
                {path.name for path in outputs},
                {f"{name}.mmd" for name in mermaid} | {f"{name}.md" for name in prds},
            )
            for name, (source, _report) in prds.items():
                self.assertEqual(
                    (Path(directory) / f"{name}.md").read_text(encoding="utf-8"),
                    source.rstrip() + "\n",
                )
            fixture = test_bootstrap_doctor.BootstrapDoctorTests()
            adopter_root = Path(directory) / "initialized-adopter"
            adopter_root.mkdir()
            adopter = fixture.copy_project(adopter_root)
            marker = b"\nSECRET_CUSTOMER_MARKER\n"
            for relative in render_mermaid_fixtures.GOLDEN_RECORD_PATHS:
                path = adopter.joinpath(*PurePosixPath(relative).parts)
                path.write_bytes(path.read_bytes() + marker)
            unrelated = adopter / "app/README.md"
            unrelated.write_bytes(unrelated.read_bytes() + marker)
            pattern = adopter.joinpath(
                *PurePosixPath(render_mermaid_fixtures.GOLDEN_PATTERN_PATH).parts
            )
            canonical_pattern = pattern.read_bytes()
            pattern.write_bytes(canonical_pattern + marker)
            helper = adopter.joinpath(
                *PurePosixPath(render_mermaid_fixtures.GOLDEN_HELPER_PATH).parts
            )
            canonical_helper = helper.read_bytes()
            isolated_output = Path(directory) / "isolated-review"
            with (
                mock.patch.object(test_bootstrap_doctor, "PROJECT_ROOT", adopter),
                mock.patch.object(
                    render_mermaid_fixtures,
                    "REPOSITORY_ROOT",
                    adopter,
                ),
                mock.patch.object(
                    render_mermaid_fixtures,
                    "GOLDEN_RECORD_SEED",
                    adopter / "tests/fixtures/golden_project_records_v1.bin",
                ),
            ):
                with self.assertRaisesRegex(ValueError, "package-manifest binding"):
                    render_mermaid_fixtures.write_review_fixtures(isolated_output)
                self.assertFalse(any(isolated_output.iterdir()))
                pattern.write_bytes(canonical_pattern)
                helper.write_bytes(canonical_helper + marker)
                with self.assertRaisesRegex(ValueError, "package-manifest binding"):
                    render_mermaid_fixtures.write_review_fixtures(isolated_output)
                self.assertFalse(any(isolated_output.iterdir()))
                helper.write_bytes(canonical_helper)
                isolated = render_mermaid_fixtures.write_review_fixtures(
                    isolated_output
                )
            self.assertEqual(len(isolated), 15)
            for name, source in mermaid.items():
                rendered = (isolated_output / f"{name}.mmd").read_text(encoding="utf-8")
                self.assertEqual(rendered, source.rstrip() + "\n")
                self.assertNotIn(marker.decode().strip(), rendered)
            for name, (source, _report) in prds.items():
                rendered = (isolated_output / f"{name}.md").read_text(encoding="utf-8")
                self.assertEqual(rendered, source.rstrip() + "\n")
                self.assertNotIn(marker.decode().strip(), rendered)
            hooks = Path(directory) / "hostile-hooks"
            hooks.mkdir()
            hook_marker = "SECRET_GIT_HOOK_MARKER"
            (hooks / "pre-commit").write_text(
                "#!/bin/sh\n"
                f"printf '\\n{hook_marker}\\n' >> docs/project/PRD.md\n"
                "git add -f -- docs/project/PRD.md\n",
                encoding="utf-8",
                newline="\n",
            )
            git_config = Path(directory) / "hostile-gitconfig"
            git_config.write_text(
                f"[core]\n\thooksPath = {hooks.as_posix()}\n",
                encoding="utf-8",
                newline="\n",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "GIT_CONFIG_GLOBAL": str(git_config),
                    "GIT_CONFIG_NOSYSTEM": "1",
                },
            ):
                hook_isolated = render_mermaid_fixtures.collect_prd_fixtures()
            self.assertFalse(
                [
                    name
                    for name, (source, _report) in hook_isolated.items()
                    if hook_marker in source
                ]
            )
        expected_contract = {
            "DIAGRAM-0001": (
                "SYSTEM_CONTEXT",
                "proposed-system-at-a-glance",
                ("ARCH-0001", "FR-001"),
            ),
            "DIAGRAM-0002": (
                "PRIMARY_OUTCOME",
                "sequence-primary-outcome",
                ("ARCH-0001", "JOURNEY-001"),
            ),
            "DIAGRAM-0003": (
                "DATA_LIFECYCLE",
                "data-lifecycle-view",
                ("ARCH-0001", "DATA-001"),
            ),
            "DIAGRAM-0004": (
                "FAILURE_RECOVERY",
                "sequence-failure-and-recovery",
                ("ARCH-0001", "REL-005"),
            ),
            "DIAGRAM-0005": (
                "MIGRATION",
                "migration-view",
                ("PRES-001", "ARCH-0001"),
            ),
            "DIAGRAM-0008": (
                "AWS_IMPLEMENTATION",
                "aws-implementation-at-a-glance",
                ("ARCH-0001", "DES-0001"),
            ),
        }
        expected_relationships = {
            "golden-complete-architecture": {
                ("ACT-001", "SOLID", "sends a review request through", "TECH-0013"),
                ("TECH-0010", "DASHED", "provides token issuer trust to", "TECH-0013"),
                (
                    "TECH-0013",
                    "SOLID",
                    "routes authenticated requests into",
                    "BOUNDARY-001",
                ),
                ("BOUNDARY-001", "SOLID", "allows requests to", "API-001"),
                ("API-001", "SOLID", "invokes", "TECH-0002"),
                ("TECH-0002", "SOLID", "runs on", "TECH-0001"),
                ("TECH-0001", "SOLID", "implements", "ARCH-0001"),
                ("ARCH-0001", "SOLID", "stores owner records in", "TECH-0011"),
                (
                    "TECH-0008",
                    "DASHED",
                    "protects code, data, and secrets posture for",
                    "ARCH-0001",
                ),
                ("ARCH-0001", "DASHED", "emits operational signals to", "TECH-0014"),
                ("TECH-0004", "DASHED", "defines changes for", "TECH-0009"),
                ("TECH-0009", "DASHED", "deploys", "TECH-0001"),
                ("TECH-0015", "DASHED", "restores", "TECH-0001"),
            },
            "golden-primary-outcome": {
                ("ACT-001", "SOLID", "submits a review request to", "API-001"),
                ("API-001", "SOLID", "returns the validated review to", "ACT-001"),
            },
            "golden-data-lifecycle": {
                ("API-001", "SOLID", "validates and stores in", "TECH-0011")
            },
            "golden-failure-recovery": {
                ("API-001", "SOLID", "fails safely and invokes", "TECH-0015")
            },
            "golden-aws-implementation": {
                ("TECH-0010", "DASHED", "provides token issuer trust to", "TECH-0013"),
                ("TECH-0013", "SOLID", "routes authenticated requests to", "TECH-0002"),
                ("TECH-0002", "SOLID", "runs on", "TECH-0001"),
                ("TECH-0001", "SOLID", "implements", "ARCH-0001"),
                ("ARCH-0001", "SOLID", "reads and writes", "TECH-0011"),
                ("TECH-0008", "DASHED", "protects", "ARCH-0001"),
                ("ARCH-0001", "DASHED", "emits signals to", "TECH-0014"),
                ("TECH-0004", "DASHED", "defines changes for", "TECH-0009"),
                ("TECH-0009", "DASHED", "deploys", "TECH-0001"),
                ("TECH-0015", "DASHED", "restores", "TECH-0001"),
            },
            "golden-brownfield-migration": {
                ("BOUNDARY-001", "SOLID", "routes existing requests to", "ARCH-0001"),
                ("ARCH-0001", "SOLID", "keeps compatible records in", "TECH-0011"),
                ("TECH-0015", "DASHED", "restores", "ARCH-0001"),
            },
        }
        expected_relationships["golden-infrastructure-aws"] = expected_relationships[
            "golden-aws-implementation"
        ]

        def relationships(candidate: str) -> set[tuple[str, str, str, str]]:
            solid = re.compile(
                r"^\s*([A-Z][A-Z0-9_]*-\d{3,})\s*-->\|([^|]+)\|\s*"
                r"([A-Z][A-Z0-9_]*-\d{3,})\s*$"
            )
            dashed = re.compile(
                r'^\s*([A-Z][A-Z0-9_]*-\d{3,})\s*-\.\s*"([^"]+)"\s*\.->\s*'
                r"([A-Z][A-Z0-9_]*-\d{3,})\s*$"
            )
            observed: set[tuple[str, str, str, str]] = set()
            for line in candidate.splitlines():
                match = solid.fullmatch(line) or dashed.fullmatch(line)
                if match is None:
                    continue
                kind = "SOLID" if "-->|" in line else "DASHED"
                label = " ".join(match.group(2).replace("<br/>", " ").split())
                observed.add((match.group(1), kind, label, match.group(3)))
            return observed

        used_sources: set[str] = set()
        for name, (source, report) in prds.items():
            self.assertNotIn("\r", source)
            self.assertNotRegex(source, r"\{\{[A-Z0-9_]+\}\}")
            self.assertNotRegex(source, r"(?i)aws_access_key|secret_key|session_token")
            self.assertNotRegex(source, r"[A-Z]:\\|/(?:Users|home)/")
            self.assertNotRegex(source, r"(?im)(?:account|arn:aws)[^\n|`]*\d{12}")
            self.assertNotIn("SECRET_CUSTOMER_MARKER", source)
            self.assertEqual(report["document_summaries"]["status"], "CURRENT")
            if name != "golden-prd-untouched":
                gate_b_owner = source.split(
                    "## 29. Gate B owner authorization record", 1
                )
                self.assertEqual(len(gate_b_owner), 2)
                self.assertNotRegex(gate_b_owner[0], r"\b(?:TODO|TBD)\b")
                expected_pending = 8 if name == "golden-prd-greenfield-design" else 0
                self.assertEqual(
                    len(re.findall(r"\b(?:TODO|TBD)\b", gate_b_owner[1])),
                    expected_pending,
                )
                self.assertNotRegex(source, r"(?m)^\| (?:RA|DEC)-\d+")
                self.assertIn("| Open blocking finding IDs | `NONE` |", source)
                self.assertIn("| Open blocking decision IDs | `NONE` |", source)
            self.assertLessEqual(
                len(
                    rendered_visible_lines(
                        MERMAID_BLOCK.sub("[Rendered diagram]", source)
                    )
                ),
                330,
            )
            diagram = report["design_contract"]["diagram_contract"]
            current = {
                item["diagram_id"]: item
                for item in diagram["records"]
                if item["status"] == "CURRENT"
            }
            bindings = render_mermaid_fixtures.PRD_DIAGRAM_BINDINGS[name]
            primary_region = test_bootstrap_doctor.doctor.table_after_heading(
                source, "## 1. Workload profile"
            )["Primary Region"]
            self.assertEqual(set(current), set(bindings))
            self.assertEqual(len(MERMAID_BLOCK.findall(source)), len(bindings))
            if bindings:
                self.assertEqual(report["design_contract"]["status"], "READY")
                self.assertEqual(diagram["status"], "CURRENT")
            for diagram_id, fixture_name in bindings.items():
                record = current[diagram_id]
                kind, anchor, basis_ids = expected_contract[diagram_id]
                self.assertEqual(
                    (record["kind"], record["anchor"], tuple(record["basis_ids"])),
                    (kind, anchor, basis_ids),
                )
                heading_matches = [
                    match
                    for match in re.finditer(r"(?m)^#{1,6} (.+?)\s*$", source)
                    if re.sub(r"[^a-z0-9]+", "-", match.group(1).lower()).strip("-")
                    == anchor
                ]
                self.assertEqual(len(heading_matches), 1, diagram_id)
                following_heading = re.search(
                    r"(?m)^#{1,6} .+?\s*$", source[heading_matches[0].end() :]
                )
                section_end = (
                    heading_matches[0].end() + following_heading.start()
                    if following_heading is not None
                    else len(source)
                )
                blocks = re.findall(
                    r"(?ms)^```mermaid\s*\n.*?^```\s*$",
                    source[heading_matches[0].end() : section_end],
                )
                self.assertEqual(len(blocks), 1, diagram_id)
                canonical = blocks[0].rstrip() + "\n"
                expected = "```mermaid\n" + mermaid[fixture_name].rstrip() + "\n```\n"
                self.assertEqual(canonical, expected, diagram_id)
                if record["kind"] in {"SYSTEM_CONTEXT", "AWS_IMPLEMENTATION"}:
                    self.assertIn(primary_region, mermaid[fixture_name])
                self.assertEqual(
                    record["rendered_sha256"],
                    "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
                )
                endpoint_ids = {
                    endpoint
                    for relationship in record["relationships"]
                    for endpoint in (
                        relationship["from_id"],
                        relationship["to_id"],
                    )
                }
                self.assertEqual(endpoint_ids, set(record["referenced_ids"]))
                observed = relationships(mermaid[fixture_name])
                self.assertEqual(observed, expected_relationships[fixture_name])
                self.assertEqual(
                    {(start, label, end) for start, _kind, label, end in observed},
                    {
                        (
                            relationship["from_id"],
                            relationship["relation"],
                            relationship["to_id"],
                        )
                        for relationship in record["relationships"]
                    },
                )
                used_sources.add(fixture_name)
        self.assertEqual(
            used_sources,
            set(render_mermaid_fixtures.GOLDEN_NAMES)
            | set(render_mermaid_fixtures.VARIANT_NAMES),
        )


if __name__ == "__main__":
    unittest.main()
