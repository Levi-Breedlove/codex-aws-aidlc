"""Materialize sanitized Fastlane Mermaid fixtures for maintainer rendering.

The files are derived only from the packaged procedure examples and synthetic
Golden Project records. They contain no customer repository, machine, AWS
account, credential, session, or authorization data.
"""

from __future__ import annotations

import argparse
import ast
import inspect
import re
import textwrap
from pathlib import Path

from tests.test_bootstrap_doctor import (
    approve_gate_a,
    complete_diagram_contract,
    complete_existing_design_contract,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MERMAID_BLOCK = re.compile(r"(?ms)^```mermaid\r?\n(.*?)\r?\n```\s*$")
PUBLISHED_NAMES = (
    "published-complete-architecture",
    "published-aws-implementation",
    "published-journey-flow",
    "published-state-flow",
)
GOLDEN_BINDINGS = (
    ("golden-complete-architecture", "### Proposed system at a glance"),
    ("golden-primary-outcome", "### Sequence — primary outcome"),
    ("golden-data-lifecycle", "### Data lifecycle view"),
    ("golden-failure-recovery", "### Sequence — failure and recovery"),
    ("golden-aws-implementation", "### AWS implementation at a glance"),
)
GOLDEN_NAMES = tuple(name for name, _heading in GOLDEN_BINDINGS)
VARIANT_BINDINGS = (
    ("golden-brownfield-migration", "FEATURE", "### Migration view"),
    (
        "golden-infrastructure-aws",
        "INFRASTRUCTURE",
        "### AWS implementation at a glance",
    ),
)
VARIANT_NAMES = tuple(name for name, _work_kind, _heading in VARIANT_BINDINGS)


def _blocks(source: str, *, expected: int, label: str) -> tuple[str, ...]:
    blocks = tuple(MERMAID_BLOCK.findall(source))
    if len(blocks) != expected:
        raise ValueError(f"{label} must contain exactly {expected} Mermaid blocks")
    for index, block in enumerate(blocks, 1):
        first = next((line.strip() for line in block.splitlines() if line.strip()), "")
        if not first.startswith("flowchart "):
            raise ValueError(f"{label} Mermaid block {index} is not a flowchart")
        if "TODO" in block or "PLACEHOLDER" in block:
            raise ValueError(f"{label} Mermaid block {index} is unresolved")
    return blocks


def _literal_golden_blocks() -> dict[str, str]:
    """Bind five synthetic literals by heading, never customer canonical state."""

    tree = ast.parse(textwrap.dedent(inspect.getsource(complete_diagram_contract)))
    by_heading: dict[str, str] = {}
    expected_headings = {heading for _name, heading in GOLDEN_BINDINGS}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) < 4:
            continue
        heading_node, body_node = node.args[1], node.args[3]
        if not (
            isinstance(heading_node, ast.Constant)
            and isinstance(heading_node.value, str)
            and heading_node.value in expected_headings
            and isinstance(body_node, ast.Constant)
            and isinstance(body_node.value, str)
        ):
            continue
        match = MERMAID_BLOCK.fullmatch(body_node.value)
        if match is not None:
            by_heading[heading_node.value] = match.group(1)
    if set(by_heading) != expected_headings:
        raise ValueError(
            "Golden Project fixture must define exactly "
            f"{len(GOLDEN_NAMES)} literal Mermaid blocks"
        )
    return {name: by_heading[heading] for name, heading in GOLDEN_BINDINGS}


def _block_after_heading(source: str, heading: str) -> str:
    start = source.index(heading) + len(heading)
    match = MERMAID_BLOCK.search(source, start)
    if match is None:
        raise ValueError(
            f"Synthetic Design record has no Mermaid block after {heading}"
        )
    return match.group(1)


def _variant_golden_blocks() -> dict[str, str]:
    """Build sanitized brownfield and infrastructure Design-stage records."""

    template = (REPOSITORY_ROOT / "docs/project/PRD.md").read_text(encoding="utf-8")
    variants: dict[str, str] = {}
    for name, work_kind, heading in VARIANT_BINDINGS:
        design = complete_existing_design_contract(
            approve_gate_a(
                template,
                work_context_choice="B",
                project_mode="brownfield",
            ),
            work_kind=work_kind,
        )
        variants[name] = _block_after_heading(design, heading)
    return variants


def collect_mermaid_fixtures(root: Path = REPOSITORY_ROOT) -> dict[str, str]:
    """Return the exact sanitized Mermaid sources rendered in CI."""

    pattern_source = (
        root / ".agents/skills/fastlane/references/diagram-patterns.md"
    ).read_text(encoding="utf-8")
    published = _blocks(
        pattern_source,
        expected=len(PUBLISHED_NAMES),
        label="Published diagram procedure",
    )
    golden = _literal_golden_blocks()
    variants = _variant_golden_blocks()
    return {
        **dict(zip(PUBLISHED_NAMES, published, strict=True)),
        **golden,
        **variants,
    }


def write_mermaid_fixtures(output_dir: Path) -> tuple[Path, ...]:
    """Write deterministic LF Mermaid inputs beneath one explicit directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    fixtures = collect_mermaid_fixtures()
    expected_names = {f"{name}.mmd" for name in fixtures}
    unexpected = {
        path.name for path in output_dir.iterdir() if path.name not in expected_names
    }
    if unexpected:
        raise ValueError(
            "Mermaid output directory contains unexpected entries: "
            + ", ".join(sorted(unexpected))
        )
    outputs: list[Path] = []
    for name, source in fixtures.items():
        path = output_dir / f"{name}.mmd"
        path.write_text(source.rstrip() + "\n", encoding="utf-8", newline="\n")
        outputs.append(path)
    return tuple(outputs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize sanitized Mermaid fixtures for rendering."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    outputs = write_mermaid_fixtures(args.output_dir.resolve())
    print(f"Prepared {len(outputs)} sanitized Mermaid fixtures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
