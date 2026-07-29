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
                destination = source if not path_part else (source.parent / unquote(path_part)).resolve()
                try:
                    destination.relative_to(REPOSITORY_ROOT)
                except ValueError:
                    failures.append(f"{source.relative_to(REPOSITORY_ROOT)} -> {target} escapes root")
                    continue
                if not destination.exists():
                    failures.append(f"{source.relative_to(REPOSITORY_ROOT)} -> {target} missing")
                    continue
                if separator and fragment and destination.is_file() and destination.suffix.casefold() == ".md":
                    if unquote(fragment).casefold() not in headings(destination):
                        failures.append(
                            f"{source.relative_to(REPOSITORY_ROOT)} -> {target} fragment missing"
                        )
        self.assertEqual(failures, [])

    def test_markdown_and_mermaid_fences_are_balanced(self) -> None:
        failures: list[str] = []
        for path in self.markdown_files():
            active: str | None = None
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
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
            for failure in mermaid_structure_failures(
                path.read_text(encoding="utf-8")
            ):
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

    def test_project_documents_are_canonical_and_removed_surfaces_stay_removed(self) -> None:
        required = ("BUGFIX.md", "PRD.md", "RUNBOOK.md", "TASKS.md", "VERIFY.md")
        for name in required:
            self.assertTrue((REPOSITORY_ROOT / "docs" / "project" / name).is_file())
            self.assertFalse((REPOSITORY_ROOT / name).exists())
        for removed in ("CHANGELOG.md", "CONTRIBUTING.md", "VERSION"):
            self.assertFalse((REPOSITORY_ROOT / removed).exists())
        self.assertFalse((REPOSITORY_ROOT / "scripts" / "run_demo.py").exists())
        combined = "\n".join(path.read_text(encoding="utf-8") for path in self.markdown_files())
        self.assertNotIn("docs/demo/", combined)
        self.assertNotIn("scripts/run_demo.py", combined)

    def test_prd_diagrams_keep_trust_and_validation_before_persistence(self) -> None:
        prd = (REPOSITORY_ROOT / "docs" / "project" / "PRD.md").read_text(
            encoding="utf-8"
        )
        required = (
            "External trust boundary",
            "Approved AWS account, Region, and environment",
            "Authorize, validate, and apply idempotency",
            "Rejected input",
            "Encrypted active data",
            "Optional queue",
            "Logs, metrics, traces, and alarms",
            "Safe terminal response",
        )
        for phrase in required:
            self.assertIn(phrase, prd)
        self.assertEqual(persistence_order_failures(prd), [])
        self.assertNotIn("Client->>Service: Validated request", prd)
        self.assertNotIn("API->>Data: Validate or persist", prd)
        self.assertNotIn("Input[Validated input]", prd)

    def test_prd_starter_diagrams_model_safe_specialization_paths(self) -> None:
        prd = (REPOSITORY_ROOT / "docs" / "project" / "PRD.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "Managed entry and identity boundary",
            "Application processing boundary",
            "Data boundary",
            "Operations boundary",
            "Identity verification",
            "Application authorization, validation, and compute",
            "Logs, metrics, traces, and alarms without secrets",
            "Verified restore test",
            "Recovery evidence without sensitive values",
            "Deletion evidence without sensitive values",
            "Operational owner",
            "Durable recovery record exists",
            "Actionable alarm with correlation ID",
            "Reconciliation evidence",
        ):
            self.assertIn(phrase, prd)
        self.assertNotIn("Actor --> Entry --> Identity --> App", prd)
        self.assertIn("Entry --> App", prd)

        async_block = next(
            block
            for block in MERMAID_BLOCK.findall(prd)
            if ACCEPTED_STEP in block and WORKER_DELIVERY_STEP in block
        )
        self.assertLess(
            async_block.index(QUEUE_ACK_STEP), async_block.index(ACCEPTED_STEP)
        )
        self.assertLess(
            async_block.index(ACCEPTED_STEP),
            async_block.index(WORKER_DELIVERY_STEP),
        )
        self.assertLess(
            async_block.index(WORKER_VALIDATION_STEP),
            async_block.index(WORKER_PERSISTENCE_STEP),
        )

    def test_prd_requires_diagrams_to_be_specialized_in_place(self) -> None:
        prd = (REPOSITORY_ROOT / "docs" / "project" / "PRD.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("editable starter patterns", prd)
        self.assertIn("update the existing\nblocks in place", prd)
        self.assertIn("Do\nnot append another diagram by default", prd)
        self.assertIn("A diagram records intended\ndesign", prd)

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
