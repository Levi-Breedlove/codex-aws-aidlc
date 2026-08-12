"""Materialize sanitized Fastlane Mermaid fixtures for maintainer rendering.

The files are derived only from the packaged procedure examples and synthetic
Golden Project records. They contain no customer repository, machine, AWS
account, credential, session, or authorization data.
"""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import hashlib
import json
import os
import re
import tempfile
import zlib
from pathlib import Path
from unittest import mock

from tests.test_bootstrap_doctor import (
    BootstrapDoctorTests,
    approve_gate_a,
    complete_diagram_contract,
    complete_existing_design_contract,
    doctor,
    refresh_document_summaries,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_RECORD_SEED = REPOSITORY_ROOT / "tests/fixtures/golden_project_records_v1.bin"
GOLDEN_RECORD_PATHS = (
    "bootstrap.yaml",
    "docs/project/BUGFIX.md",
    "docs/project/PRD.md",
    "docs/project/README.md",
    "docs/project/RUNBOOK.md",
    "docs/project/TASKS.md",
    "docs/project/VERIFY.md",
)
GOLDEN_PATTERN_PATH = ".agents/skills/fastlane/references/diagram-patterns.md"
GOLDEN_HELPER_PATH = "tests/test_bootstrap_doctor.py"
_GOLDEN_RECORD_HEADER = b"FASTLANE-GOLDEN-RECORDS-V1\n"
_MAX_GOLDEN_SEED_BYTES = 64 * 1024
_MAX_GOLDEN_RECORD_BYTES = 256 * 1024
_MAX_GOLDEN_PROCEDURE_BYTES = 1024 * 1024
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
PRD_NAMES = (
    "golden-prd-untouched",
    "golden-prd-greenfield-design",
    "golden-prd-brownfield-feature-design",
    "golden-prd-infrastructure-only-design",
)
PRD_DIAGRAM_BINDINGS = {
    "golden-prd-untouched": {},
    "golden-prd-greenfield-design": {
        "DIAGRAM-0001": "golden-complete-architecture",
        "DIAGRAM-0002": "golden-primary-outcome",
        "DIAGRAM-0003": "golden-data-lifecycle",
        "DIAGRAM-0004": "golden-failure-recovery",
        "DIAGRAM-0008": "golden-aws-implementation",
    },
    "golden-prd-brownfield-feature-design": {
        "DIAGRAM-0001": "golden-complete-architecture",
        "DIAGRAM-0002": "golden-primary-outcome",
        "DIAGRAM-0003": "golden-data-lifecycle",
        "DIAGRAM-0004": "golden-failure-recovery",
        "DIAGRAM-0005": "golden-brownfield-migration",
        "DIAGRAM-0008": "golden-aws-implementation",
    },
    "golden-prd-infrastructure-only-design": {
        "DIAGRAM-0001": "golden-complete-architecture",
        "DIAGRAM-0002": "golden-primary-outcome",
        "DIAGRAM-0003": "golden-data-lifecycle",
        "DIAGRAM-0004": "golden-failure-recovery",
        "DIAGRAM-0005": "golden-brownfield-migration",
        "DIAGRAM-0008": "golden-infrastructure-aws",
    },
}


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


def _literal_golden_blocks(helper_source: str) -> dict[str, str]:
    """Bind five synthetic literals by heading, never customer canonical state."""

    tree = ast.parse(helper_source)
    functions = tuple(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == complete_diagram_contract.__name__
    )
    if len(functions) != 1:
        raise ValueError("Golden Project fixture helper is not singular")
    by_heading: dict[str, str] = {}
    expected_headings = {heading for _name, heading in GOLDEN_BINDINGS}
    for node in ast.walk(functions[0]):
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

    template = _golden_record_overrides()["docs/project/PRD.md"].decode("utf-8")
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


def _inspect_prd(project: Path) -> tuple[str, dict[str, object]]:
    report = doctor.inspect_project(project)
    if not report["ok"] or report["document_summaries"]["status"] != "CURRENT":
        raise ValueError("Golden PRD project did not reach a current Engine state")
    return (project / "docs/project/PRD.md").read_text(encoding="utf-8"), report


def _manifest() -> dict[str, object]:
    return json.loads(
        (REPOSITORY_ROOT / "bootstrap.manifest.json").read_text(encoding="utf-8")
    )


def _manifest_bound_text(relative: str) -> str:
    """Read one packaged procedure only when its exact manifest hash is current."""

    pure = Path(relative)
    if pure.is_absolute() or pure.as_posix() != relative or ".." in pure.parts:
        raise ValueError("Golden procedure path is invalid")
    manifest = _manifest()
    required = manifest.get("required_files", [])
    stored = manifest.get("source_sha256", {}).get(relative)
    path = REPOSITORY_ROOT.joinpath(*pure.parts)
    if relative not in required or not isinstance(stored, str):
        raise ValueError("Golden procedure is not package-manifest bound")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Golden procedure is missing or unsafe")
    raw = path.read_bytes()
    if (
        len(raw) > _MAX_GOLDEN_PROCEDURE_BYTES
        or hashlib.sha256(raw).hexdigest() != stored
    ):
        raise ValueError("Golden procedure differs from its package-manifest binding")
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Golden procedure is not UTF-8") from exc
    if "\r" in source:
        raise ValueError("Golden procedure is not canonical LF text")
    return source


def _golden_record_overrides() -> dict[str, bytes]:
    """Load one bounded immutable seed, never live project record bytes."""

    if GOLDEN_RECORD_SEED.is_symlink() or not GOLDEN_RECORD_SEED.is_file():
        raise ValueError("Golden record seed is missing or unsafe")
    raw = GOLDEN_RECORD_SEED.read_bytes()
    if not raw.endswith(b"\n") or not raw.startswith(_GOLDEN_RECORD_HEADER):
        raise ValueError("Golden record seed envelope is invalid")
    encoded = raw[len(_GOLDEN_RECORD_HEADER) : -1]
    if not encoded or len(raw) > _MAX_GOLDEN_SEED_BYTES:
        raise ValueError("Golden record seed exceeds its bounded envelope")
    manifest = _manifest()
    stored = manifest.get("source_sha256", {}).get(
        "tests/fixtures/golden_project_records_v1.bin"
    )
    if stored != hashlib.sha256(raw).hexdigest():
        raise ValueError("Golden record seed is not bound by the package manifest")
    try:
        compressed = base64.b64decode(encoded, validate=True)
        inflater = zlib.decompressobj()
        decoded = inflater.decompress(compressed, _MAX_GOLDEN_RECORD_BYTES + 1)
    except (binascii.Error, ValueError, zlib.error) as exc:
        raise ValueError("Golden record seed payload is invalid") from exc
    if (
        len(decoded) > _MAX_GOLDEN_RECORD_BYTES
        or not inflater.eof
        or inflater.unused_data
        or inflater.unconsumed_tail
    ):
        raise ValueError("Golden record seed contract is invalid")
    try:
        decoded += inflater.flush()
        payload = json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, zlib.error) as exc:
        raise ValueError("Golden record seed payload is invalid") from exc
    if (
        len(decoded) > _MAX_GOLDEN_RECORD_BYTES
        or not isinstance(payload, dict)
        or set(payload) != {"schema_version", "bootstrap_version", "records"}
        or payload.get("schema_version") != 1
    ):
        raise ValueError("Golden record seed contract is invalid")
    if payload.get("bootstrap_version") != manifest.get("bootstrap_version"):
        raise ValueError("Golden record seed version is stale")
    records = payload.get("records")
    if (
        not isinstance(records, list)
        or not all(isinstance(row, dict) for row in records)
        or [row.get("path") for row in records] != list(GOLDEN_RECORD_PATHS)
    ):
        raise ValueError("Golden record seed inventory is invalid")
    overrides: dict[str, bytes] = {}
    for row in records:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "text"}:
            raise ValueError("Golden record seed row is invalid")
        path, expected, text = row["path"], row["sha256"], row["text"]
        if (
            not isinstance(text, str)
            or "\r" in text
            or not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
        ):
            raise ValueError(f"Golden record seed text is invalid: {path}")
        content = text.encode("utf-8")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Golden record seed hash is invalid: {path}")
        overrides[path] = content
    return overrides


def collect_prd_fixtures() -> dict[str, tuple[str, dict[str, object]]]:
    """Build four complete sanitized PRD records through real fixture routes."""

    _manifest_bound_text(GOLDEN_HELPER_PATH)
    fixture = BootstrapDoctorTests()
    record_overrides = _golden_record_overrides()
    baseline_paths = tuple(record_overrides)
    git_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    git_environment.update(
        {
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    with (
        tempfile.TemporaryDirectory() as directory,
        mock.patch.dict(os.environ, git_environment, clear=True),
    ):
        projects: dict[str, Path] = {}
        for name in PRD_NAMES:
            destination = Path(directory) / name
            destination.mkdir()
            projects[name] = fixture.copy_project(
                destination, source_overrides=record_overrides
            )
        refresh_document_summaries(projects[PRD_NAMES[0]])
        fixture.pending_gate_b(projects[PRD_NAMES[1]], baseline_paths=baseline_paths)
        fixture.approve_existing_project(
            projects[PRD_NAMES[2]],
            work_kind="FEATURE",
            baseline_paths=baseline_paths,
        )
        fixture.approve_existing_project(
            projects[PRD_NAMES[3]],
            work_kind="INFRASTRUCTURE",
            baseline_paths=baseline_paths,
        )
        return {name: _inspect_prd(projects[name]) for name in PRD_NAMES}


def collect_mermaid_fixtures(_root: Path | None = None) -> dict[str, str]:
    """Return the exact sanitized Mermaid sources rendered in CI."""

    helper_source = _manifest_bound_text(GOLDEN_HELPER_PATH)
    pattern_source = _manifest_bound_text(GOLDEN_PATTERN_PATH)
    published = _blocks(
        pattern_source,
        expected=len(PUBLISHED_NAMES),
        label="Published diagram procedure",
    )
    golden = _literal_golden_blocks(helper_source)
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


def write_review_fixtures(output_dir: Path) -> tuple[Path, ...]:
    """Write four complete PRDs and the deduplicated Mermaid render inputs."""

    mermaid = write_mermaid_fixtures(output_dir)
    prds = collect_prd_fixtures()
    expected_names = {path.name for path in mermaid} | {f"{name}.md" for name in prds}
    unexpected = {path.name for path in output_dir.iterdir()} - expected_names
    if unexpected:
        raise ValueError(
            "Review output directory contains unexpected entries: "
            + ", ".join(sorted(unexpected))
        )
    outputs = list(mermaid)
    for name, (source, _report) in prds.items():
        path = output_dir / f"{name}.md"
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
    outputs = write_review_fixtures(args.output_dir.resolve())
    print(f"Prepared {len(outputs)} sanitized review fixtures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
