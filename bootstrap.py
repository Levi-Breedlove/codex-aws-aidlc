#!/usr/bin/env python3
"""Install the Fastlane template without overwriting unreviewed user files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Sequence
from scripts.fastlane_process import resolve_trusted_git
from scripts.fastlane_project_identity import (
    PROJECT_NAME_TOKEN,
    markdown_inline,
    normalize_aws_region,
    normalize_project_name,
)
from scripts.fastlane_stdio import configure_utf8_standard_streams
from scripts.setup_assistant import (
    SetupError,
    read_ready_prerequisite_report,
)


PLACEHOLDERS = {
    "{{PROJECT_NAME}}": "AWS Codex Project",
    "{{AWS_REGION}}": "us-west-2",
    "{{COST_POSTURE}}": "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED",
    "{{SETUP_METHOD}}": "EXTERNAL_COPY",
    "{{SETUP_STATUS}}": "CONFIGURED",
}
DEFAULT_COST_POSTURE = "MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED"
COST_POSTURE_WITH_CAP = re.compile(
    r"MINIMIZE_TOTAL_COST; HARD_CAP: (?P<currency>[A-Z]{3}) "
    r"(?P<amount>[1-9]\d*(?:\.\d{1,2})?)"
)
# Current ISO 4217 List One currency and fund codes, excluding the testing
# code XTS and no-currency code XXX. The static allowlist keeps bootstrap
# validation deterministic and dependency-free.
ISO_4217_CURRENCY_CODES = frozenset(
    """AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR XOF XPD XPF XPT XSU XUA YER ZAR ZMW ZWG""".split()
)

SKIP_NAMES = {".git", "__pycache__"}
SKIP_SUFFIXES = {".zip", ".pyc"}
SKIP_NAMES_CASEFOLD = {name.casefold() for name in SKIP_NAMES}
ENGINE_RUNTIME_CONTROL_PATHS = {
    "scripts/fastlane_engine/__init__.py",
    "scripts/fastlane_engine/api.py",
    "scripts/fastlane_engine/aws/__init__.py",
    "scripts/fastlane_engine/aws/deployment.py",
    "scripts/fastlane_engine/aws/evidence.py",
    "scripts/fastlane_engine/aws/lifecycle.py",
    "scripts/fastlane_engine/aws/models.py",
    "scripts/fastlane_engine/aws/preflight.py",
    "scripts/fastlane_engine/aws/teardown.py",
    "scripts/fastlane_engine/core/__init__.py",
    "scripts/fastlane_engine/core/contracts.py",
    "scripts/fastlane_engine/core/diagnostics.py",
    "scripts/fastlane_engine/core/digests.py",
    "scripts/fastlane_engine/core/ids.py",
    "scripts/fastlane_engine/core/markdown_index.py",
    "scripts/fastlane_engine/core/snapshot.py",
    "scripts/fastlane_engine/define/__init__.py",
    "scripts/fastlane_engine/define/coverage.py",
    "scripts/fastlane_engine/define/intake.py",
    "scripts/fastlane_engine/define/models.py",
    "scripts/fastlane_engine/define/project.py",
    "scripts/fastlane_engine/define/requirements.py",
    "scripts/fastlane_engine/design/__init__.py",
    "scripts/fastlane_engine/design/adr.py",
    "scripts/fastlane_engine/design/architecture.py",
    "scripts/fastlane_engine/design/diagrams.py",
    "scripts/fastlane_engine/design/envelope.py",
    "scripts/fastlane_engine/design/harness.py",
    "scripts/fastlane_engine/design/models.py",
    "scripts/fastlane_engine/design/project.py",
    "scripts/fastlane_engine/design/source.py",
    "scripts/fastlane_engine/design/support.py",
    "scripts/fastlane_engine/deliver/__init__.py",
    "scripts/fastlane_engine/deliver/evidence.py",
    "scripts/fastlane_engine/deliver/models.py",
    "scripts/fastlane_engine/deliver/release.py",
    "scripts/fastlane_engine/deliver/repository.py",
    "scripts/fastlane_engine/deliver/tasks.py",
    "scripts/fastlane_engine/package/__init__.py",
    "scripts/fastlane_engine/package/manifest.py",
    "scripts/fastlane_engine/package/state.py",
}
NO_RENDER_PATHS = {
    "bootstrap.py",
    "bootstrap.manifest.json",
    "scripts/bootstrap_dependencies.py",
    "scripts/bootstrap_doctor.py",
    "scripts/fastlane_adr.py",
    "scripts/fastlane_contracts.py",
    "scripts/fastlane_process.py",
    "scripts/fastlane_project_identity.py",
    "scripts/fastlane_stdio.py",
    "scripts/setup_assistant.py",
    "scripts/task_waves.py",
    "scripts/fastlane_engine/AGENTS.md",
} | ENGINE_RUNTIME_CONTROL_PATHS
NO_RENDER_PREFIXES = ("tests/",)
CORE_CONTROL_PATHS = {
    "AGENTS.md",
    "docs/project/BUGFIX.md",
    "docs/project/PRD.md",
    "docs/project/RUNBOOK.md",
    "docs/project/TASKS.md",
    "docs/project/VERIFY.md",
    "bootstrap.manifest.json",
    "bootstrap.py",
    "bootstrap.yaml",
    "prompts/CODEX-PROMPTS.md",
    "scripts/bootstrap_doctor.py",
    "scripts/fastlane_adr.py",
    "scripts/fastlane_contracts.py",
    "scripts/fastlane_process.py",
    "scripts/fastlane_project_identity.py",
    "scripts/fastlane_stdio.py",
    "scripts/setup_assistant.py",
    "scripts/task_waves.py",
} | ENGINE_RUNTIME_CONTROL_PATHS
ADOPTION_ACTIONS = {"PRESERVE", "ADOPT_TEMPLATE", "STAGE_FOR_MERGE"}
RUNTIME_CONTROL_PATHS = {
    "bootstrap.py",
    "scripts/bootstrap_dependencies.py",
    "scripts/bootstrap_doctor.py",
    "scripts/fastlane_adr.py",
    "scripts/fastlane_contracts.py",
    "scripts/fastlane_process.py",
    "scripts/fastlane_project_identity.py",
    "scripts/fastlane_stdio.py",
    "scripts/setup_assistant.py",
    "scripts/task_waves.py",
} | ENGINE_RUNTIME_CONTROL_PATHS
RFC3339_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)
NON_HUMAN_IDENTITY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:codex|agent|automation|system|bot|model|ai|assistant|"
    r"service|todo|tbd|tbc|unknown|pending|unassigned)(?![A-Za-z0-9])",
    re.IGNORECASE,
)


@dataclass
class CopyReport:
    """Summary of a preflighted template installation."""

    planned: int = 0
    written: int = 0
    unchanged: int = 0
    collisions: int = 0
    unresolved: int = 0
    preserved: int = 0
    adopted: int = 0
    staged: int = 0
    partial_adoption: bool = False


@dataclass(frozen=True)
class CopyOperation:
    """One operation that is safe to apply after the complete preflight."""

    relative: str
    source: Path
    destination: Path
    content: bytes | None
    action: str
    expected_destination_sha256: str | None = None


@dataclass(frozen=True)
class AdoptionDecision:
    """A hash-bound decision for one existing, non-identical target file."""

    path: str
    action: str
    expected_target_sha256: str
    expected_template_sha256: str


@dataclass(frozen=True)
class AdoptionPlan:
    """Reviewed decisions bound to exact source and target roots."""

    source_root: Path
    target_root: Path
    decisions: dict[str, AdoptionDecision] = field(default_factory=dict)
    authorized_by: str | None = None
    authorized_at: str | None = None
    authorization_source: str | None = None
    plan_sha256: str | None = None


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def should_render_path(relative: str) -> bool:
    """Return whether project placeholders may be rendered in this file."""

    return relative not in NO_RENDER_PATHS and not relative.startswith(
        NO_RENDER_PREFIXES
    )


def canonical_adoption_plan_sha256(
    source_root: Path,
    target_root: Path,
    decisions: object,
) -> str:
    """Bind an authorization receipt to both roots and the ordered decisions."""

    return sha256_bytes(
        json.dumps(
            {
                "schema_version": 1,
                "source_root": str(source_root.resolve()),
                "target_root": str(target_root.resolve()),
                "decisions": decisions,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def adoption_decision_payload(
    decisions: dict[str, AdoptionDecision],
) -> list[dict[str, str]]:
    """Return the canonical ordered JSON representation of parsed decisions."""

    return [
        {
            "path": decision.path,
            "action": decision.action,
            "expected_target_sha256": decision.expected_target_sha256,
            "expected_template_sha256": decision.expected_template_sha256,
        }
        for decision in decisions.values()
    ]


def validate_rfc3339(value: object, field_name: str) -> str:
    """Return a strict, timezone-qualified RFC 3339 timestamp."""

    if not isinstance(value, str) or RFC3339_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} requires an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} requires an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} timestamp must include a timezone")
    return value


def validate_human_identity(value: object, field_name: str) -> str:
    """Reject unresolved, synthetic, or automation identities at a human gate."""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} requires a named human owner")
    normalized = value.strip()
    if (
        not normalized
        or any(character in normalized for character in "\r\n<>")
        or NON_HUMAN_IDENTITY_PATTERN.search(normalized) is not None
    ):
        raise ValueError(f"{field_name} requires a named human owner")
    return normalized


def validate_adoption_authority(plan: AdoptionPlan) -> None:
    """Validate the complete programmatic plan and any destructive authority."""

    if not isinstance(plan.source_root, Path) or not isinstance(plan.target_root, Path):
        raise ValueError("Adoption plan roots must be Path objects")
    if not isinstance(plan.decisions, dict):
        raise ValueError("Adoption plan decisions must be a path-keyed object")
    for key, decision in plan.decisions.items():
        relative = validate_relative_path(key)
        if not isinstance(decision, AdoptionDecision):
            raise ValueError(f"{relative}: invalid programmatic adoption decision")
        if decision.path != relative:
            raise ValueError(f"{relative}: decision path does not match its lookup key")
        if decision.action not in ADOPTION_ACTIONS:
            raise ValueError(f"{relative}: invalid adoption action {decision.action!r}")
        validate_digest(
            decision.expected_target_sha256,
            "expected_target_sha256",
            relative,
        )
        validate_digest(
            decision.expected_template_sha256,
            "expected_template_sha256",
            relative,
        )

    if not any(
        decision.action == "ADOPT_TEMPLATE" for decision in plan.decisions.values()
    ):
        return
    validate_human_identity(plan.authorized_by, "Adoption authorization")
    if plan.authorization_source != "OWNER_CONFIRMATION":
        raise ValueError("Adoption authorization_source must be OWNER_CONFIRMATION")
    validate_rfc3339(plan.authorized_at, "Adoption authorization")
    expected = canonical_adoption_plan_sha256(
        plan.source_root,
        plan.target_root,
        adoption_decision_payload(plan.decisions),
    )
    if plan.plan_sha256 != expected:
        raise ValueError("Adoption authorization does not match the complete plan")


def is_text_file(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
        return True
    except (UnicodeDecodeError, OSError):
        return False


def normalize_render_values(values: dict[str, str]) -> dict[str, str]:
    """Normalize owner identity tokens before any render plan or write."""

    normalized = dict(values)
    if PROJECT_NAME_TOKEN in normalized:
        normalized[PROJECT_NAME_TOKEN] = normalize_project_name(
            normalized[PROJECT_NAME_TOKEN]
        )
    if "{{AWS_REGION}}" in normalized:
        normalized["{{AWS_REGION}}"] = normalize_aws_region(
            normalized["{{AWS_REGION}}"]
        )
    return normalized


def contextual_render_values(
    relative: str,
    values: dict[str, str],
) -> dict[str, str]:
    """Encode replacement values for the exact destination syntax."""

    rendered = dict(values)
    if relative == "bootstrap.yaml":
        rendered = {
            key: json.dumps(value, ensure_ascii=False)[1:-1]
            for key, value in rendered.items()
        }
    elif PurePosixPath(relative).suffix.casefold() == ".md":
        rendered[PROJECT_NAME_TOKEN] = markdown_inline(
            rendered.get(PROJECT_NAME_TOKEN, "")
        )
    return rendered


def render_text(text: str, values: dict[str, str], relative: str) -> str:
    """Render known tokens once so owner text cannot become another token."""

    replacements = contextual_render_values(relative, values)
    if not replacements:
        return text
    pattern = re.compile(
        "|".join(re.escape(key) for key in sorted(replacements, key=len, reverse=True))
    )
    return pattern.sub(lambda match: replacements[match.group(0)], text)


def validate_rendered_bootstrap_state(content: bytes) -> None:
    """Require the rendered structured identity to remain canonical JSON."""

    try:
        state = json.loads(content.decode("utf-8"))
        project = state["project"]
        name = project["name"]
        region = project["region"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(
            "Rendered bootstrap.yaml is not valid canonical project state"
        ) from exc
    if normalize_project_name(name) != name or normalize_aws_region(region) != region:
        raise ValueError("Rendered bootstrap.yaml project identity is not canonical")


def paths_overlap(first: Path, second: Path) -> bool:
    first = first.resolve()
    second = second.resolve()
    return first == second or first in second.parents or second in first.parents


def validate_non_overlapping_paths(source: Path, target: Path) -> None:
    """Reject overlapping source and target trees before creating anything."""

    source = source.resolve()
    target = target.resolve()
    if not source.is_dir():
        raise ValueError(f"Template source is not a directory: {source}")
    filesystem_root = Path(target.anchor).resolve()
    if target in {filesystem_root, Path.home().resolve()}:
        raise ValueError(
            f"Target must not be a filesystem root or home directory: {target}"
        )
    if any(part.casefold() == ".git" for part in target.parts):
        raise ValueError(f"Target must not be inside Git metadata: {target}")
    if paths_overlap(source, target):
        raise ValueError(
            "Source and target directories must not overlap: "
            f"source={source}, target={target}"
        )
    if target.exists() and not target.is_dir():
        raise ValueError(f"Target exists and is not a directory: {target}")


def validate_relative_path(raw: str) -> str:
    """Return one canonical repository-relative POSIX path or fail closed."""

    if (
        not isinstance(raw, str)
        or not raw
        or raw == "."
        or "\\" in raw
        or any(character in raw for character in "*?[]{}")
    ):
        raise ValueError(f"Invalid adoption path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(
        part in {"", ".", ".."} or part.casefold() == ".git" for part in path.parts
    ):
        raise ValueError(f"Invalid adoption path: {raw!r}")
    canonical = path.as_posix()
    if canonical != raw:
        raise ValueError(f"Adoption path is not canonical: {raw!r}")
    return canonical


def validate_digest(value: object, field_name: str, path: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{path}: invalid {field_name}")
    return value


def validate_template_control_hashes(source: Path) -> None:
    """Verify trusted runtime bytes before an installer tells users to run them."""

    manifest_path = source / "bootstrap.manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to verify template control hashes: {exc}") from exc
    controls = manifest.get("control_sha256") if isinstance(manifest, dict) else None
    if not isinstance(controls, dict) or set(controls) != RUNTIME_CONTROL_PATHS:
        raise ValueError(
            "bootstrap.manifest.json control_sha256 must name the exact runtime controls"
        )
    for relative in sorted(RUNTIME_CONTROL_PATHS):
        expected = validate_digest(controls[relative], "control_sha256", relative)
        path = source / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Runtime control is missing or unsafe: {relative}")
        actual = sha256_bytes(path.read_bytes())
        if actual != expected:
            raise ValueError(f"Runtime control hash mismatch: {relative}")


def validate_repository_dependencies(source: Path) -> None:
    """Fail before setup when Fastlane assets or dependency policy drift."""

    # The validator is executable code. Bind every runtime control to the
    # manifest before starting that helper so drift cannot execute first and be
    # detected only by a later in-place or copy-path check.
    validate_template_control_hashes(source)
    script = source / "scripts" / "bootstrap_dependencies.py"
    if script.is_symlink() or not script.is_file():
        raise ValueError("Bootstrap dependency validator is missing or unsafe")
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(source), "--json"],
            cwd=source,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ValueError(
            f"Bootstrap dependency validation could not run: {exc}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(
            "Bootstrap dependency validation failed" + (f": {detail}" if detail else "")
        )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Bootstrap dependency validator returned invalid JSON"
        ) from exc
    if not isinstance(report, dict) or report.get("status") != "READY":
        raise ValueError("Bootstrap dependency validator did not report READY")


def load_template_manifest(source: Path) -> dict[str, object]:
    """Load one structurally valid template manifest."""

    manifest_path = source / "bootstrap.manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError(f"Template manifest is missing or unsafe: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read template manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Template manifest must be a JSON object")
    return payload


def load_manifest_required_files(source: Path) -> list[str]:
    """Return the exact canonical file allowlist from the manifest."""

    manifest = load_template_manifest(source)
    raw_files = manifest.get("required_files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("Template manifest required_files must be a non-empty array")
    required: list[str] = []
    folded: set[str] = set()
    for raw in raw_files:
        if not isinstance(raw, str):
            raise ValueError(f"Template manifest path must be text: {raw!r}")
        relative = validate_relative_path(raw)
        if relative.casefold() in folded:
            raise ValueError(f"Duplicate or case-colliding manifest path: {relative}")
        folded.add(relative.casefold())
        required.append(relative)
    if required != sorted(required):
        raise ValueError("Template manifest required_files must be sorted canonically")
    if "bootstrap.manifest.json" not in required:
        raise ValueError("Template manifest must include bootstrap.manifest.json")
    return required


def validate_template_source_hashes(source: Path, required: Sequence[str]) -> None:
    """Require the untouched source bytes recorded for an in-place template."""

    manifest = load_template_manifest(source)
    raw_hashes = manifest.get("source_sha256")
    expected_paths = set(required) - {"bootstrap.manifest.json"}
    if not isinstance(raw_hashes, dict) or set(raw_hashes) != expected_paths:
        raise ValueError(
            "Template manifest source_sha256 must name every required file except itself"
        )
    for relative in sorted(expected_paths):
        expected = validate_digest(raw_hashes[relative], "source_sha256", relative)
        path = source.joinpath(*PurePosixPath(relative).parts)
        if has_unsafe_parent(source, path) or path.is_symlink() or not path.is_file():
            raise ValueError(f"Template source file is missing or unsafe: {relative}")
        observed = sha256_bytes(path.read_bytes())
        if observed != expected:
            raise ValueError(
                f"Template source hash mismatch for {relative}: "
                f"expected {expected}, observed {observed}"
            )


def validate_template_tree_inventory(source: Path, required: Sequence[str]) -> None:
    """Require an initial in-place tree to contain only manifest source files."""

    expected = set(required)
    actual: set[str] = set()
    for item in source.rglob("*"):
        relative_path = item.relative_to(source)
        folded_parts = {part.casefold() for part in relative_path.parts}
        if ".git" in folded_parts or "__pycache__" in folded_parts:
            continue
        if item.is_symlink():
            raise ValueError(
                "In-place template tree contains an unsupported symbolic link: "
                f"{relative_path.as_posix()}"
            )
        if item.is_file() and item.suffix.casefold() != ".pyc":
            actual.add(relative_path.as_posix())
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if extra:
            details.append("unexpected: " + ", ".join(extra))
        raise ValueError(
            "In-place template tree does not match bootstrap.manifest.json ("
            + "; ".join(details)
            + ")"
        )


def git_text(root: Path, *arguments: str, allow_failure: bool = False) -> str:
    """Run one read-only Git query or fail closed."""

    try:
        result = subprocess.run(
            [resolve_trusted_git(root), "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"Unable to inspect the Git repository: {exc}") from exc
    if result.returncode != 0:
        if allow_failure:
            return ""
        message = result.stderr.strip() or result.stdout.strip() or "Git query failed"
        raise ValueError(f"Unable to inspect the Git repository: {message}")
    return result.stdout.strip()


def validate_in_place_repository(source: Path) -> None:
    """Protect the official source and user changes during in-place setup."""

    if not (source / ".git").exists():
        return
    origin = git_text(
        source,
        "config",
        "--get",
        "remote.origin.url",
        allow_failure=True,
    )
    normalized = origin.casefold().strip().rstrip("/")
    for prefix in ("https://", "http://", "ssh://git@"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
            break
    if normalized.startswith("git@github.com:"):
        normalized = "github.com/" + normalized.removeprefix("git@github.com:")
    official_names = {
        "github.com/levi-breedlove/aws-bootstrap",
        "github.com/levi-breedlove/aws-bootstrap.git",
        "github.com/levi-breedlove/codex-aws-aidlc",
        "github.com/levi-breedlove/codex-aws-aidlc.git",
    }
    if normalized in official_names:
        raise ValueError(
            "In-place setup is disabled in the official maintainer repository; "
            "use GitHub 'Use this template' or the release ZIP"
        )
    dirty = git_text(source, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise ValueError(
            "In-place setup requires an untouched, clean template repository"
        )


def run_generated_doctor(root: Path) -> tuple[bool, str]:
    """Run the generated project's read-only doctor."""

    doctor = root / "scripts" / "bootstrap_doctor.py"
    try:
        result = subprocess.run(
            [sys.executable, str(doctor), "--root", str(root), "--json"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    output = result.stdout.strip() or result.stderr.strip()
    return result.returncode == 0, output


def initialize_template_in_place(
    source: Path,
    values: dict[str, str],
    *,
    dry_run: bool = False,
) -> CopyReport:
    """Atomically configure an untouched template instance at its own root."""

    source = source.resolve()
    if source in {Path(source.anchor).resolve(), Path.home().resolve()}:
        raise ValueError(f"In-place template root is unsafe: {source}")
    required = load_manifest_required_files(source)
    validate_template_control_hashes(source)

    renderable = [relative for relative in required if should_render_path(relative)]
    placeholder_bytes = [token.encode("utf-8") for token in PLACEHOLDERS]
    remaining = {
        relative
        for relative in renderable
        if any(
            token in source.joinpath(*PurePosixPath(relative).parts).read_bytes()
            for token in placeholder_bytes
        )
    }
    if not remaining:
        ok, output = run_generated_doctor(source)
        if not ok:
            raise ValueError(
                f"Configured template Fastlane Engine validation failed: {output}"
            )
        return CopyReport(unchanged=len(required))

    validate_in_place_repository(source)
    validate_template_tree_inventory(source, required)
    validate_template_source_hashes(source, required)
    values = normalize_render_values(values)
    values["{{SETUP_METHOD}}"] = "IN_PLACE"
    operations: list[tuple[str, Path, bytes, bytes]] = []
    for relative in renderable:
        path = source.joinpath(*PurePosixPath(relative).parts)
        original = path.read_bytes()
        rendered = rendered_bytes(path, values, relative=relative, render=True)
        if original != rendered:
            operations.append((relative, path, original, rendered))

    report = CopyReport(planned=len(operations))
    if dry_run:
        for relative, _path, _original, rendered in operations:
            print(f"WOULD CONFIGURE {relative} sha256={sha256_bytes(rendered)}")
        return report

    written: list[tuple[Path, bytes]] = []
    try:
        for relative, path, original, rendered in operations:
            atomic_write_bytes(path, rendered, path)
            written.append((path, original))
            report.written += 1
            print(f"CONFIGURED {relative} sha256={sha256_bytes(rendered)}")
        ok, output = run_generated_doctor(source)
        if not ok:
            raise ValueError(
                f"Configured template Fastlane Engine validation failed: {output}"
            )
    except Exception:
        for path, original in reversed(written):
            atomic_write_bytes(path, original, path)
        raise
    return report


def load_adoption_plan(path: Path, source: Path, target: Path) -> AdoptionPlan:
    """Load a strict, duplicate-free, hash-bound brownfield adoption plan."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read adoption map {path}: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Adoption map must be an object with schema_version 1")
    expected_keys = {
        "schema_version",
        "source_root",
        "target_root",
        "decisions",
        "authorization",
    }
    if set(payload) != expected_keys:
        raise ValueError(
            "Adoption map fields must be exactly: " + ", ".join(sorted(expected_keys))
        )

    source_root = Path(str(payload["source_root"])).expanduser().resolve()
    target_root = Path(str(payload["target_root"])).expanduser().resolve()
    if source_root != source.resolve() or target_root != target.resolve():
        raise ValueError(
            "Adoption map source_root or target_root does not match this run"
        )

    raw_decisions = payload["decisions"]
    if not isinstance(raw_decisions, list):
        raise ValueError("Adoption map decisions must be a list")

    decisions: dict[str, AdoptionDecision] = {}
    for item in raw_decisions:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "action",
            "expected_target_sha256",
            "expected_template_sha256",
        }:
            raise ValueError("Every adoption decision must contain exactly four fields")
        relative = validate_relative_path(item["path"])
        if relative in decisions:
            raise ValueError(f"Duplicate adoption decision: {relative}")
        action = item["action"]
        if action not in ADOPTION_ACTIONS:
            raise ValueError(f"{relative}: invalid adoption action {action!r}")
        decisions[relative] = AdoptionDecision(
            path=relative,
            action=action,
            expected_target_sha256=validate_digest(
                item["expected_target_sha256"], "expected_target_sha256", relative
            ),
            expected_template_sha256=validate_digest(
                item["expected_template_sha256"], "expected_template_sha256", relative
            ),
        )
    raw_authorization = payload["authorization"]
    destructive = any(
        decision.action == "ADOPT_TEMPLATE" for decision in decisions.values()
    )
    if raw_authorization is None:
        if destructive:
            raise ValueError(
                "ADOPT_TEMPLATE requires an exact owner-confirmation receipt"
            )
        return AdoptionPlan(source_root, target_root, decisions)
    if not isinstance(raw_authorization, dict) or set(raw_authorization) != {
        "authorized_by",
        "authorized_at",
        "authorization_source",
        "plan_sha256",
    }:
        raise ValueError(
            "Adoption authorization must contain exactly authorized_by, "
            "authorized_at, authorization_source, and plan_sha256"
        )
    authorized_by = raw_authorization["authorized_by"]
    authorized_at = raw_authorization["authorized_at"]
    authorization_source = raw_authorization["authorization_source"]
    plan_digest = validate_digest(
        raw_authorization["plan_sha256"],
        "plan_sha256",
        "authorization",
    )
    authorized_by = validate_human_identity(
        authorized_by,
        "Adoption authorization",
    )
    validate_rfc3339(authorized_at, "Adoption authorization")
    if authorization_source != "OWNER_CONFIRMATION":
        raise ValueError("Adoption authorization_source must be OWNER_CONFIRMATION")
    result = AdoptionPlan(
        source_root,
        target_root,
        decisions,
        authorized_by,
        authorized_at,
        authorization_source,
        plan_digest,
    )
    validate_adoption_authority(result)
    return result


def rendered_bytes(
    path: Path,
    values: dict[str, str],
    *,
    relative: str,
    render: bool = True,
) -> bytes:
    if is_text_file(path):
        content = path.read_text(encoding="utf-8")
        if render:
            content = render_text(content, values, relative)
        rendered = content.encode("utf-8")
        if relative == "bootstrap.yaml":
            validate_rendered_bootstrap_state(rendered)
        return rendered
    return path.read_bytes()


def has_unsafe_parent(root: Path, destination: Path) -> bool:
    """Return true when an existing parent could redirect or block a write."""

    current = root
    for part in destination.relative_to(root).parts[:-1]:
        current = current / part
        if current.is_symlink():
            return True
        if current.exists() and not current.is_dir():
            return True
    return False


def atomic_write_bytes(destination: Path, content: bytes, source: Path) -> None:
    """Write one generated file atomically in its destination directory."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        shutil.copymode(source, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def validate_copy_operation(operation: CopyOperation, root: Path) -> None:
    """Recheck one planned destination without changing either tree."""

    if has_unsafe_parent(root, operation.destination):
        raise ValueError(
            f"{operation.relative}: destination parent changed after preflight"
        )
    if operation.content is None:
        if operation.destination.is_symlink() or (
            operation.destination.exists() and not operation.destination.is_dir()
        ):
            raise ValueError(
                f"{operation.relative}: directory destination changed after preflight"
            )
        return
    if operation.expected_destination_sha256 is None:
        if operation.destination.exists() or operation.destination.is_symlink():
            raise ValueError(
                f"{operation.relative}: destination appeared after preflight"
            )
        return
    if (
        operation.destination.is_symlink()
        or not operation.destination.is_file()
        or sha256_bytes(operation.destination.read_bytes())
        != operation.expected_destination_sha256
    ):
        raise ValueError(f"{operation.relative}: destination changed after preflight")


def copy_template(
    source: Path,
    target: Path,
    values: dict[str, str],
    force: bool = False,
    *,
    dry_run: bool = False,
    adoption_plan: AdoptionPlan | None = None,
    staging_target: Path | None = None,
    allowed_files: Sequence[str] | None = None,
) -> CopyReport:
    """Preflight and apply a new install or a reviewed brownfield overlay."""

    source = source.resolve()
    target = target.resolve()
    validate_non_overlapping_paths(source, target)
    values = normalize_render_values(values)
    if force:
        raise ValueError(
            "Blanket --force is disabled; use a hash-bound per-path adoption map"
        )
    if adoption_plan and (
        adoption_plan.source_root != source or adoption_plan.target_root != target
    ):
        raise ValueError("Adoption plan roots do not match this copy operation")
    if adoption_plan:
        validate_adoption_authority(adoption_plan)
    if staging_target is not None:
        staging_target = staging_target.expanduser().resolve()
        if staging_target in {
            Path(staging_target.anchor).resolve(),
            Path.home().resolve(),
        }:
            raise ValueError(
                f"Staging target must not be a filesystem root or home directory: {staging_target}"
            )
        if any(part.casefold() == ".git" for part in staging_target.parts):
            raise ValueError(
                f"Staging target must not be inside Git metadata: {staging_target}"
            )
        if paths_overlap(source, staging_target) or paths_overlap(
            target, staging_target
        ):
            raise ValueError("Staging target must be separate from source and target")
        if staging_target.exists() and not staging_target.is_dir():
            raise ValueError(f"Staging target is not a directory: {staging_target}")

    if allowed_files is None:
        discovered_items = sorted(
            source.rglob("*"), key=lambda item: item.relative_to(source).parts
        )
    else:
        discovered_items = []
        for relative in allowed_files:
            canonical = validate_relative_path(relative)
            item = source.joinpath(*PurePosixPath(canonical).parts)
            if has_unsafe_parent(source, item) or item.is_symlink():
                raise ValueError(
                    f"Manifest file uses an unsafe source path: {canonical}"
                )
            if not item.is_file():
                raise ValueError(f"Manifest file is missing: {canonical}")
            discovered_items.append(item)
    symlinks = [item for item in discovered_items if item.is_symlink()]
    if symlinks:
        raise ValueError(
            f"Template source contains unsupported symbolic link: {symlinks[0]}"
        )

    items: list[Path] = []
    casefolded_paths: dict[str, str] = {}
    for item in discovered_items:
        relative_path = item.relative_to(source)
        if (
            any(part.casefold() in SKIP_NAMES_CASEFOLD for part in relative_path.parts)
            or item.suffix.casefold() in SKIP_SUFFIXES
        ):
            continue
        relative = relative_path.as_posix()
        casefolded = "/".join(part.casefold() for part in relative_path.parts)
        previous = casefolded_paths.get(casefolded)
        if previous is not None and previous != relative:
            raise ValueError(
                "Template paths collide on a case-insensitive filesystem: "
                f"{previous}, {relative}"
            )
        casefolded_paths[casefolded] = relative
        items.append(item)

    report = CopyReport()
    operations: list[CopyOperation] = []
    collision_paths: set[str] = set()
    decisions_used: set[str] = set()
    receipts: list[str] = []
    preserved_checks: list[tuple[str, Path, str]] = []

    source_agent_paths = {
        item.relative_to(source).as_posix().casefold()
        for item in items
        if item.name.casefold() == "agents.md"
    }
    if target.is_dir():
        for target_item in sorted(target.rglob("*")):
            try:
                relative_target = target_item.relative_to(target)
            except ValueError:
                continue
            if any(
                part.casefold() in SKIP_NAMES_CASEFOLD for part in relative_target.parts
            ):
                continue
            relative = relative_target.as_posix()
            if (
                target_item.name.casefold() == "agents.md"
                and relative.casefold() not in source_agent_paths
            ):
                report.partial_adoption = True
                print(f"PRESERVED TARGET CONTROL {relative} reason=target-only-AGENTS")

    for item in items:
        relative_path = item.relative_to(source)
        relative = relative_path.as_posix()

        destination = target / relative_path
        if item.is_dir():
            if destination.is_symlink() or (
                destination.exists() and not destination.is_dir()
            ):
                report.collisions += 1
                report.unresolved += 1
                collision_paths.add(relative)
                print(f"COLLISION {relative} reason=target-type")
            elif not destination.exists():
                operations.append(
                    CopyOperation(relative, item, destination, None, "CREATE_DIRECTORY")
                )
            continue

        if has_unsafe_parent(target, destination):
            report.collisions += 1
            report.unresolved += 1
            collision_paths.add(relative)
            print(f"COLLISION {relative} reason=unsafe-parent")
            continue

        content = rendered_bytes(
            item,
            values,
            relative=relative,
            render=should_render_path(relative),
        )
        template_digest = sha256_bytes(content)
        if destination.is_symlink() or (
            destination.exists() and not destination.is_file()
        ):
            report.collisions += 1
            report.unresolved += 1
            collision_paths.add(relative)
            print(f"COLLISION {relative} reason=target-type")
            continue

        if not destination.exists():
            operations.append(
                CopyOperation(relative, item, destination, content, "WRITE")
            )
            report.planned += 1
            continue

        try:
            target_content = destination.read_bytes()
        except OSError as exc:
            raise ValueError(
                f"Unable to read collision target {destination}: {exc}"
            ) from exc
        target_digest = sha256_bytes(target_content)
        if target_content == content:
            report.unchanged += 1
            print(f"UNCHANGED {relative} sha256={target_digest}")
            continue

        report.collisions += 1
        collision_paths.add(relative)
        decision = adoption_plan.decisions.get(relative) if adoption_plan else None
        if decision is None:
            report.unresolved += 1
            print(
                f"COLLISION {relative} target_sha256={target_digest} "
                f"template_sha256={template_digest}"
            )
            continue

        decisions_used.add(relative)
        if decision.expected_target_sha256 != target_digest:
            raise ValueError(f"{relative}: target changed after adoption review")
        if decision.expected_template_sha256 != template_digest:
            raise ValueError(
                f"{relative}: rendered template changed after adoption review"
            )

        if decision.action == "PRESERVE":
            report.preserved += 1
            report.partial_adoption |= (
                relative in CORE_CONTROL_PATHS
                or PurePosixPath(relative).name.casefold() == "agents.md"
            )
            preserved_checks.append((relative, destination, target_digest))
            receipts.append(
                f"ADOPTION PRESERVE {relative} pre={target_digest} post={target_digest}"
            )
        elif decision.action == "ADOPT_TEMPLATE":
            operations.append(
                CopyOperation(
                    relative,
                    item,
                    destination,
                    content,
                    "ADOPT_TEMPLATE",
                    target_digest,
                )
            )
            report.planned += 1
            report.adopted += 1
            receipts.append(
                f"ADOPTION ADOPT_TEMPLATE {relative} pre={target_digest} "
                f"post={template_digest}"
            )
        else:
            if staging_target is None:
                raise ValueError(
                    f"{relative}: STAGE_FOR_MERGE requires --staging-target"
                )
            staged_destination = staging_target / relative_path
            if has_unsafe_parent(staging_target, staged_destination):
                raise ValueError(f"{relative}: unsafe staging parent")
            if staged_destination.is_symlink() or (
                staged_destination.exists() and not staged_destination.is_file()
            ):
                raise ValueError(f"{relative}: unsafe staging collision")
            if (
                staged_destination.exists()
                and staged_destination.read_bytes() != content
            ):
                raise ValueError(
                    f"{relative}: staging target already has different content"
                )
            if not staged_destination.exists():
                operations.append(
                    CopyOperation(
                        relative,
                        item,
                        staged_destination,
                        content,
                        "STAGE_FOR_MERGE",
                    )
                )
                report.planned += 1
            report.staged += 1
            # Staged content has not been reconciled into the active target yet.
            report.partial_adoption = True
            receipts.append(
                f"ADOPTION STAGE_FOR_MERGE {relative} pre={target_digest} "
                f"staged={template_digest}"
            )

    if adoption_plan:
        unused = sorted(set(adoption_plan.decisions) - decisions_used)
        if unused:
            raise ValueError(
                "Adoption map contains paths that are not current collisions: "
                + ", ".join(unused)
            )

    if report.unresolved or dry_run:
        for receipt in sorted(receipts):
            print(f"PLAN {receipt}")
        for operation in operations:
            if operation.content is not None:
                print(f"PLAN {operation.action} {operation.relative}")
        return report

    for relative, destination, expected_digest in preserved_checks:
        if (
            destination.is_symlink()
            or not destination.is_file()
            or sha256_bytes(destination.read_bytes()) != expected_digest
        ):
            raise ValueError(f"{relative}: preserved target changed after preflight")

    # Recheck the complete operation set before the first write so late drift in
    # one destination cannot follow an earlier destructive adoption write.
    for operation in operations:
        operation_root = (
            staging_target if operation.action == "STAGE_FOR_MERGE" else target
        )
        if operation_root is None:
            raise ValueError(f"{operation.relative}: operation root is unavailable")
        validate_copy_operation(operation, operation_root)

    target.mkdir(parents=True, exist_ok=True)
    for operation in operations:
        operation_root = (
            staging_target if operation.action == "STAGE_FOR_MERGE" else target
        )
        if operation_root is None:
            raise ValueError(f"{operation.relative}: operation root is unavailable")
        validate_copy_operation(operation, operation_root)
        if operation.content is None:
            operation.destination.mkdir(parents=True, exist_ok=True)
            continue
        atomic_write_bytes(operation.destination, operation.content, operation.source)
        print(f"{operation.action} {operation.relative}")
        if operation.action in {"ADOPT_TEMPLATE", "STAGE_FOR_MERGE"}:
            print(
                f"ADOPTION RECEIPT {operation.action} {operation.relative} "
                f"post={sha256_bytes(operation.content)}"
            )
        report.written += 1
    for receipt in sorted(receipts):
        if receipt.startswith("ADOPTION PRESERVE"):
            print(f"ADOPTION RECEIPT {receipt.removeprefix('ADOPTION ')}")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    configure_utf8_standard_streams()
    parser = argparse.ArgumentParser(
        description="Create or safely adopt an AWS Codex Fastlane project."
    )
    parser.add_argument("--target", required=True, help="Target project directory")
    parser.add_argument(
        "--project-name", required=True, help="One-line human-readable project name"
    )
    parser.add_argument("--region", default="us-west-2", help="Canonical AWS Region ID")
    parser.add_argument(
        "--cost-posture",
        "--budget",
        dest="cost_posture",
        default=DEFAULT_COST_POSTURE,
        help=(
            "Canonical planning posture; use MINIMIZE_TOTAL_COST; HARD_CAP: "
            "USD 20.00 only when the owner supplied that real limit"
        ),
    )
    parser.add_argument(
        "--in-place-template-instance",
        action="store_true",
        help=(
            "Configure an untouched GitHub-template or extracted-ZIP instance "
            "at its own root; ordinary source/target overlap remains rejected"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Deprecated and rejected; use --adoption-map",
    )
    parser.add_argument(
        "--adoption-map",
        type=Path,
        help=(
            "Per-path JSON collision decisions bound to SHA-256 digests; "
            "ADOPT_TEMPLATE also requires an exact owner-confirmation receipt"
        ),
    )
    parser.add_argument(
        "--staging-target",
        type=Path,
        help="Separate target required by STAGE_FOR_MERGE decisions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview writes and collision digests without changing the target",
    )
    parser.add_argument(
        "--prerequisite-report-stdin",
        action="store_true",
        help="Read the current ephemeral PREREQUISITES_READY report from stdin",
    )
    args = parser.parse_args(argv)

    source = Path(__file__).resolve().parent
    target = Path(args.target).expanduser().resolve()
    values = dict(PLACEHOLDERS)

    try:
        project_name = normalize_project_name(args.project_name)
        region = normalize_aws_region(args.region)
        values[PROJECT_NAME_TOKEN] = project_name
        values["{{AWS_REGION}}"] = region
        values["{{COST_POSTURE}}"] = args.cost_posture
        if args.cost_posture != DEFAULT_COST_POSTURE:
            cost_match = COST_POSTURE_WITH_CAP.fullmatch(args.cost_posture)
            if cost_match is None:
                raise ValueError(
                    "--cost-posture must be MINIMIZE_TOTAL_COST; "
                    "HARD_CAP_NOT_STATED or preserve the owner's exact value "
                    "as MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00"
                )
            if cost_match.group("currency") not in ISO_4217_CURRENCY_CODES:
                raise ValueError(
                    "--cost-posture currency must be a current ISO 4217 List One code"
                )
        if not args.prerequisite_report_stdin:
            raise SetupError(
                "fresh bootstrap requires --prerequisite-report-stdin with the current setup report"
            )
        read_ready_prerequisite_report(sys.stdin)
        validate_repository_dependencies(source)

        if args.in_place_template_instance:
            if target != source:
                raise ValueError(
                    "--in-place-template-instance requires --target to name this template root"
                )
            if args.force or args.adoption_map or args.staging_target:
                raise ValueError(
                    "In-place setup cannot use --force, --adoption-map, or --staging-target"
                )
            report = initialize_template_in_place(
                source,
                values,
                dry_run=args.dry_run,
            )
        else:
            validate_template_control_hashes(source)
            required_files = load_manifest_required_files(source)
            adoption_plan = (
                load_adoption_plan(args.adoption_map, source, target)
                if args.adoption_map
                else None
            )
            report = copy_template(
                source,
                target,
                values,
                args.force,
                dry_run=args.dry_run,
                adoption_plan=adoption_plan,
                staging_target=args.staging_target,
                allowed_files=required_files,
            )
    except (OSError, SetupError, ValueError) as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        return 2

    print()
    if args.dry_run:
        print("Dry run complete. No files were changed.")
    elif report.unresolved:
        print("Bootstrap stopped with unresolved, preserved target collisions.")
    elif report.partial_adoption:
        print(
            "Bootstrap partially adopted; merge staged/preserved control files and run the Fastlane Engine."
        )
    else:
        print("Bootstrap complete.")
    print(f"Project root: {target}")
    print(
        "Summary: "
        f"{report.planned} planned, {report.written} written, "
        f"{report.unchanged} unchanged, {report.collisions} collision(s), "
        f"{report.unresolved} unresolved, {report.preserved} preserved, "
        f"{report.adopted} adopted, {report.staged} staged"
    )
    if report.partial_adoption:
        print("Target-only or preserved control instructions require reconciliation.")

    if report.unresolved:
        print("Review every digest and supply a hash-bound per-path adoption map.")
        return 1
    if args.dry_run:
        return 0
    if report.partial_adoption:
        return 3

    print()
    print("Next steps:")
    print("1. Run the Fastlane Engine: python scripts/bootstrap_doctor.py --root .")
    print(
        "2. If setup was run manually, open this repository in Codex and send: init template"
    )
    print(
        "3. Answer the project name, Region, and budget questions; Codex begins intake."
    )
    print(
        "Fastlane verifies official AWS Core before fresh initialization; "
        "this generator did not inspect plugin state or access AWS."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
