from __future__ import annotations

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
AUTHORIZATION_STEP = "Authorize, validate, and apply idempotency"
PERSISTENCE_STEP = "Persist approved data"
QUEUE_ACK_STEP = "Durable enqueue acknowledged"
ACCEPTED_STEP = "Accepted response with correlation ID"
WORKER_DELIVERY_STEP = "Deliver work"
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
        self.assertIn("planned project views, never observed deployment", prd)

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
        for phrase in (
            "project-specific diagrams",
            "semantic SHA-256",
            "rendered SHA-256",
            "Diagrams are planned views",
            "never prove implementation, deployment, or authority",
        ):
            self.assertIn(phrase, normalized)

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

    def test_automatic_agents_context_has_explicit_headroom(self) -> None:
        root_agents = REPOSITORY_ROOT / "AGENTS.md"
        chains = {
            "root": [root_agents],
            "app": [root_agents, REPOSITORY_ROOT / "app" / "AGENTS.md"],
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

    def test_readme_is_short_human_onboarding(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(readme.splitlines()), 90)
        for heading in (
            "## Start",
            "## What to expect",
            "## Project files",
            "## Safety",
            "## Agent reference",
        ):
            self.assertIn(heading, readme)
        self.assertIn(
            "Gate A — approve requirements → Gate B — approve the PRD and construction boundary → Codex builds autonomously inside that boundary.",
            readme,
        )


if __name__ == "__main__":
    unittest.main()
