from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path
from urllib.parse import unquote


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
    value = re.sub(r"\s+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


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


class MarkdownIntegrityTests(unittest.TestCase):
    def markdown_files(self) -> list[Path]:
        return sorted(
            path
            for path in REPOSITORY_ROOT.rglob("*.md")
            if ".git" not in path.parts and "dist" not in path.parts
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
        self.assertEqual(len(MERMAID_BLOCK.findall(patterns)), 4)
        self.assertIn("Load only during Design", patterns)
        self.assertIn("not application architecture", patterns)
        self.assertIn("Never imply that a planned diagram was deployed", patterns)

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
            "semantic digest",
            "rendered digest",
            "Diagrams never prove implementation, deployment, or authority",
        ):
            self.assertIn(phrase, design)

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
            "### Sequence — primary outcome": "sequence-primary-outcome",
        }
        mermaid_fence = chr(96) * 3 + "mermaid"
        for heading, expected_anchor in required.items():
            empty_slot_text = (
                "No project architecture diagram has been created yet."
                if expected_anchor == "proposed-system-at-a-glance"
                else "No primary-outcome sequence has been created yet."
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
            anchor = re.sub(
                r"[\s-]+",
                "-",
                re.sub(r"[^\w -]", "", heading[4:].lower()),
            ).strip("-")
            self.assertEqual(anchor, expected_anchor)

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

    def test_prd_owner_path_stays_within_the_readability_ceiling(self) -> None:
        prd = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
        visible_lines = [
            line
            for _number, line, depth in disclosure_lines(prd)
            if line
            and line not in {"<details>", "</details>"}
            and (depth == 0 or line.startswith("<summary>"))
        ]
        self.assertLessEqual(len(visible_lines), 330)

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
            for path in REPOSITORY_ROOT.rglob("AGENTS.md")
            if path.resolve() != root_agents and ".git" not in path.parts
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
        self.assertLessEqual(len(workflow.read_bytes()), 7_500)
        index_text = index.read_text(encoding="utf-8")
        for target in (
            "SETUP.md",
            "WORKFLOW.md",
            "TROUBLESHOOTING.md",
            "../.codex/hooks/README.md",
            "DEPENDENCY-POLICY.md",
            "../.agents/skills/maintain-fastlane/SKILL.md",
            "../.agents/skills/maintain-fastlane/references/evaluation.md",
            "../.agents/skills/maintain-fastlane/references/qualification.md",
            "project/PRD.md",
            "project/TASKS.md",
            "project/VERIFY.md",
            "project/RUNBOOK.md",
            "project/BUGFIX.md",
        ):
            self.assertIn(f"]({target})", index_text)
            self.assertTrue((index.parent / target).is_file(), target)
        for removed in (
            "docs/AGENTS.md",
            "docs/QUALIFICATION.md",
            "docs/SHOWCASE.md",
            "docs/advanced",
            "docs/assets",
            "docs/maintainers",
        ):
            self.assertFalse((REPOSITORY_ROOT / removed).exists(), removed)

        setup = (REPOSITORY_ROOT / "docs/SETUP.md").read_text(encoding="utf-8")
        self.assertIn("pipx install uv", setup)
        self.assertIn("uvx --version", setup)
        self.assertIn("docs.astral.sh/uv/getting-started/installation", setup)

        owner_workflow = workflow.read_text(encoding="utf-8")
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

    def test_readme_is_short_human_onboarding(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(readme.splitlines()), 90)
        for heading in (
            "## Start",
            "## What to expect",
            "## Repository map",
            "## AWS Core and AWS changes",
            "## Learn more",
        ):
            self.assertIn(heading, readme)
        self.assertIn(
            "Gate A — approve requirements → Gate B — approve the PRD and construction boundary → Codex builds autonomously inside that boundary.",
            readme,
        )


if __name__ == "__main__":
    unittest.main()
