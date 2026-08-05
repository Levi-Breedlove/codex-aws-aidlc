"""Validate optional ADR rationale bound to canonical Fastlane design decisions.

The PRD remains authoritative. ADR files are supporting, non-authoritative
explanations and are deliberately excluded from every lifecycle and design
digest. This module is pure and standard-library-only so the Fastlane Engine
can project their status without granting write or external authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

try:
    from fastlane_contracts import (
        ContractParseError,
        parse_exact_section_table,
        without_fenced_code,
    )
except ModuleNotFoundError:  # Loaded as scripts.fastlane_adr in unit tests.
    from scripts.fastlane_contracts import (
        ContractParseError,
        parse_exact_section_table,
        without_fenced_code,
    )


ADR_DIRECTORY = "docs/adr"
ADR_TEMPLATE = f"{ADR_DIRECTORY}/0000-template.md"
ADR_AUTHORITY = "SUPPORTING_RATIONALE_ONLY — grants no construction or AWS authority"
ADR_LINK = re.compile(
    r"\[ADR-(?P<number>\d{4})\]"
    r"\((?P<target>\.\./adr/(?P=number)-[a-z0-9]+(?:-[a-z0-9]+)*\.md)\)"
)
ADR_FILE = re.compile(r"(?P<number>\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md")
ADR_HEADING = re.compile(
    r"^# ADR-(?P<number>\d{4}): (?P<title>[^\r\n]+)$", re.MULTILINE
)
ADR_ID = re.compile(r"ADR-\d{4}")
STABLE_ID = re.compile(r"[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d{3,}")
EVIDENCE_ID = re.compile(r"(?:AWS-)?EV-[A-Z0-9][A-Z0-9._-]*")
DECISION_RECORD_FIELDS = (
    "Status",
    "Design revision",
    "Primary decision",
    "Decision value",
    "Related basis IDs",
    "Canonical PRD section",
    "Evidence maturity",
    "Evidence IDs",
    "Supersedes",
    "Superseded by",
    "Authority",
)
REQUIRED_BODY_SECTIONS = (
    "Context",
    "Decision",
    "Alternatives considered",
    "Consequences",
    "Evidence and validation",
    "Revisit when",
)
ADR_STATUSES = {"Proposed", "Accepted", "Superseded"}
ADR_EVIDENCE_MATURITIES = {"SOURCE_VERIFIED", "PLANNED_AFTER_APPROVAL"}
ADR_PRD_HEADINGS = {
    "Selected architecture",
    "Technology and toolchain decision register",
}
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|TBC|UNKNOWN|PLACEHOLDER)\b|<[^>]+>", re.I)
UNSAFE_CONTENT = re.compile(
    r"(?:[A-Za-z]:\\(?:Users|Documents)\\|/(?:Users|home)/|"
    r"AKIA[0-9A-Z]{16}|aws_secret_access_key|"
    r"https?://[^\s/@:]+:[^\s/@]+@)",
    re.I,
)
MAX_ADR_FILES = 32
MAX_ADR_BYTES = 64 * 1024
MAX_AGGREGATE_BYTES = 512 * 1024


def empty_adr_rationale() -> dict[str, Any]:
    """Return the additive, explicitly non-authoritative empty projection."""

    return {
        "schema_version": 1,
        "status": "NONE",
        "authoritative": False,
        "authority": ADR_AUTHORITY,
        "records": [],
        "projection_sha256": None,
    }


def _normalized_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def _source_sha256(value: str) -> str:
    return (
        "sha256:" + hashlib.sha256(_normalized_text(value).encode("utf-8")).hexdigest()
    )


def _projection_sha256(projection: Mapping[str, Any]) -> str:
    payload = {
        key: value for key, value in projection.items() if key != "projection_sha256"
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _clean(value: object) -> str:
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] == "`":
        return text[1:-1].strip()
    return text


def _split_exact_ids(value: object, pattern: re.Pattern[str]) -> tuple[str, ...] | None:
    cleaned = _clean(value)
    if cleaned == "NONE":
        return ()
    items = tuple(item.strip() for item in cleaned.split(","))
    if not items or any(pattern.fullmatch(item) is None for item in items):
        return None
    if len(items) != len(set(items)):
        return None
    return items


def _issue(code: str, message: str, path: str | None) -> dict[str, str]:
    result = {"code": code, "message": message}
    if path is not None:
        result["path"] = path
    return result


def _section_body(text: str, heading: str) -> str | None:
    structural = without_fenced_code(text)
    matches = list(
        re.finditer(rf"^## {re.escape(heading)}[ \t]*$", structural, re.MULTILINE)
    )
    if len(matches) != 1:
        return None
    following = re.search(r"^##\s+", structural[matches[0].end() :], re.MULTILINE)
    end = matches[0].end() + following.start() if following else len(text)
    return text[matches[0].end() : end].strip()


def _decision_catalog(design: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in design.get("technology_decisions", []):
        if not isinstance(raw, Mapping):
            continue
        decision_id = _clean(raw.get("decision_id", ""))
        result[decision_id] = {
            "decision_id": decision_id,
            "value": _clean(raw.get("selection", "")),
            "basis_ids": _split_exact_ids(raw.get("basis_ids", ""), STABLE_ID),
            "heading": "Technology and toolchain decision register",
            "validation": _clean(raw.get("validation", "")),
        }
    architecture = design.get("architecture")
    if isinstance(architecture, Mapping):
        selection = architecture.get("selection")
        if isinstance(selection, Mapping):
            decision_id = _clean(selection.get("architecture_id", ""))
            result[decision_id] = {
                "decision_id": decision_id,
                "value": _clean(selection.get("selected_candidate", "")),
                "basis_ids": _split_exact_ids(
                    selection.get("requirement_and_driver_basis", ""), STABLE_ID
                ),
                "heading": "Selected architecture",
                "validation": _clean(selection.get("validation", "")),
            }
    evidence: dict[str, set[str]] = {key: set() for key in result}
    if isinstance(architecture, Mapping):
        for raw in architecture.get("aws_evidence", []):
            if not isinstance(raw, Mapping):
                continue
            evidence_id = _clean(raw.get("evidence_id", ""))
            design_ids = _split_exact_ids(raw.get("design_ids", ""), STABLE_ID)
            if EVIDENCE_ID.fullmatch(evidence_id) is None or design_ids is None:
                continue
            for decision_id in design_ids:
                if decision_id in evidence:
                    evidence[decision_id].add(evidence_id)
    for decision_id, values in evidence.items():
        result[decision_id]["evidence_ids"] = tuple(sorted(values))
    return result


def _safe_adr_inventory(root: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    directory = root / "docs" / "adr"
    for path in (root / "docs", directory):
        if path.is_symlink():
            return {}, [
                _issue(
                    "ADR_RATIONALE_UNSAFE",
                    "The ADR directory must not traverse a symbolic link.",
                    ADR_DIRECTORY,
                )
            ]
    if not directory.is_dir():
        return {}, issues
    paths = sorted(
        path for path in directory.iterdir() if path.name != "0000-template.md"
    )
    if len(paths) > MAX_ADR_FILES:
        return {}, [
            _issue(
                "ADR_RATIONALE_UNSAFE",
                f"At most {MAX_ADR_FILES} ADR files may be evaluated at once.",
                ADR_DIRECTORY,
            )
        ]
    by_id: dict[str, str] = {}
    for path in paths:
        relative = PurePosixPath(ADR_DIRECTORY, path.name).as_posix()
        match = ADR_FILE.fullmatch(path.name)
        if match is None:
            issues.append(
                _issue(
                    "ADR_RATIONALE_UNSAFE",
                    "ADR filenames must use NNNN-lowercase-slug.md.",
                    relative,
                )
            )
            continue
        if path.is_symlink() or not path.is_file():
            issues.append(
                _issue(
                    "ADR_RATIONALE_UNSAFE",
                    "ADR files must be regular files.",
                    ADR_DIRECTORY,
                )
            )
            continue
        adr_id = f"ADR-{match.group('number')}"
        if adr_id in by_id:
            issues.append(
                _issue(
                    "ADR_RATIONALE_DUPLICATE",
                    f"{adr_id} appears in more than one ADR filename.",
                    ADR_DIRECTORY,
                )
            )
        else:
            by_id[adr_id] = relative
    return by_id, issues


def _read_adr(root: Path, relative: str) -> tuple[str | None, dict[str, str] | None]:
    path = root.joinpath(*PurePosixPath(relative).parts)
    try:
        size = path.stat().st_size
        if size > MAX_ADR_BYTES:
            raise ValueError(f"ADR exceeds the {MAX_ADR_BYTES}-byte limit")
        raw = path.read_bytes()
        if len(raw) != size:
            raise ValueError("ADR changed while it was being read")
        text = raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        return None, _issue("ADR_RATIONALE_MALFORMED", str(exc), relative)
    if "\x00" in text or UNSAFE_CONTENT.search(text):
        return None, _issue(
            "ADR_RATIONALE_UNSAFE",
            "ADR content contains unsafe machine, credential, or private-path data.",
            relative,
        )
    return _normalized_text(text), None


def _parse_adr(
    text: str, relative: str
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    headings = list(ADR_HEADING.finditer(without_fenced_code(text)))
    if len(headings) != 1:
        return None, _issue(
            "ADR_RATIONALE_MALFORMED",
            "ADR requires one '# ADR-NNNN: title' heading.",
            relative,
        )
    filename_number = PurePosixPath(relative).name[:4]
    if headings[0].group("number") != filename_number:
        return None, _issue(
            "ADR_RATIONALE_MISMATCH",
            "ADR heading ID must match its filename.",
            relative,
        )
    try:
        rows = parse_exact_section_table(
            text,
            heading="Decision record",
            headers=("Field", "Current value"),
        )
    except ContractParseError as exc:
        return None, _issue(
            "ADR_RATIONALE_MALFORMED",
            f"Decision record table is invalid: {exc}.",
            relative,
        )
    if tuple(row[0] for row in rows) != DECISION_RECORD_FIELDS:
        return None, _issue(
            "ADR_RATIONALE_MALFORMED",
            "Decision record fields are missing, duplicated, or out of order.",
            relative,
        )
    fields = {key: _clean(value) for key, value in rows}
    if fields["Status"] not in ADR_STATUSES:
        return None, _issue(
            "ADR_RATIONALE_MALFORMED", "ADR status is not supported.", relative
        )
    if (
        re.fullmatch(r"DES-\d{4,}", fields["Design revision"]) is None
        or re.fullmatch(r"(?:ARCH|TECH)-\d{4,}", fields["Primary decision"]) is None
        or not fields["Decision value"]
        or PLACEHOLDER.search(fields["Decision value"])
        or _split_exact_ids(fields["Related basis IDs"], STABLE_ID) is None
        or fields["Canonical PRD section"] not in ADR_PRD_HEADINGS
        or fields["Evidence maturity"] not in ADR_EVIDENCE_MATURITIES
        or _split_exact_ids(fields["Evidence IDs"], EVIDENCE_ID) is None
        or any(
            value != "NONE" and ADR_ID.fullmatch(value) is None
            for value in (fields["Supersedes"], fields["Superseded by"])
        )
    ):
        return None, _issue(
            "ADR_RATIONALE_MALFORMED",
            "ADR decision metadata contains an invalid or unresolved value.",
            relative,
        )
    if fields["Authority"] != ADR_AUTHORITY:
        return None, _issue(
            "ADR_RATIONALE_UNSAFE",
            "ADR authority must state that it is supporting rationale only.",
            relative,
        )
    for heading in REQUIRED_BODY_SECTIONS:
        body = _section_body(text, heading)
        if body is None or len(body) < 12 or PLACEHOLDER.search(body):
            return None, _issue(
                "ADR_RATIONALE_MALFORMED",
                f"The {heading!r} section must contain concrete rationale.",
                relative,
            )
    return {
        "relative_path": relative,
        "adr_id": f"ADR-{filename_number}",
        "title": headings[0].group("title").strip(),
        "status": fields["Status"],
        "design_revision": fields["Design revision"],
        "primary_decision": fields["Primary decision"],
        "decision_value": fields["Decision value"],
        "related_basis_ids_raw": fields["Related basis IDs"],
        "prd_heading": fields["Canonical PRD section"],
        "evidence_maturity": fields["Evidence maturity"],
        "evidence_ids_raw": fields["Evidence IDs"],
        "supersedes": fields["Supersedes"],
        "superseded_by": fields["Superseded by"],
        "source_sha256": _source_sha256(text),
    }, None


def derive_adr_rationale(
    root: Path,
    design_contract: Mapping[str, Any],
    prd_text: str,
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, str]]:
    """Project optional ADR rationale without changing canonical project state."""

    projection = empty_adr_rationale()
    issues: list[dict[str, str]] = []
    loaded_sources: dict[str, str] = {}
    inventory, inventory_issues = _safe_adr_inventory(root)
    catalog = _decision_catalog(design_contract)

    references: dict[str, str] = {}
    for decision_id, decision in catalog.items():
        validation = str(decision.get("validation", ""))
        matches = list(ADR_LINK.finditer(validation))
        adr_mentions = ADR_ID.findall(validation)
        if not matches and not adr_mentions:
            continue
        if len(matches) != 1 or adr_mentions != [f"ADR-{matches[0].group('number')}"]:
            issues.append(
                _issue(
                    "ADR_RATIONALE_UNSAFE",
                    f"{decision_id} must use one exact relative ADR Markdown link.",
                    "docs/project/PRD.md",
                )
            )
            continue
        match = matches[0]
        adr_id = f"ADR-{match.group('number')}"
        relative = PurePosixPath(
            "docs/adr", PurePosixPath(match.group("target")).name
        ).as_posix()
        if inventory.get(adr_id) != relative:
            issues.append(
                _issue(
                    "ADR_RATIONALE_MISSING",
                    f"{decision_id} references {adr_id}, but the exact safe ADR file is missing.",
                    relative,
                )
            )
            continue
        if adr_id in references:
            issues.append(
                _issue(
                    "ADR_RATIONALE_DUPLICATE",
                    f"{adr_id} is current for more than one canonical decision.",
                    "docs/project/PRD.md",
                )
            )
            continue
        references[adr_id] = decision_id

    if not references and not issues:
        return projection, [], {}
    issues.extend(inventory_issues)

    parsed: dict[str, dict[str, Any]] = {}
    total_bytes = 0

    def load(adr_id: str) -> dict[str, Any] | None:
        nonlocal total_bytes
        if adr_id in parsed:
            return parsed[adr_id]
        relative = inventory.get(adr_id)
        if relative is None:
            issues.append(
                _issue(
                    "ADR_RATIONALE_MISSING",
                    f"Supersession references missing {adr_id}.",
                    ADR_DIRECTORY,
                )
            )
            return None
        text, read_issue = _read_adr(root, relative)
        if read_issue is not None:
            issues.append(read_issue)
            return None
        assert text is not None
        total_bytes += len(text.encode("utf-8"))
        if total_bytes > MAX_AGGREGATE_BYTES:
            issues.append(
                _issue(
                    "ADR_RATIONALE_UNSAFE",
                    f"Reachable ADR content exceeds {MAX_AGGREGATE_BYTES} bytes.",
                    ADR_DIRECTORY,
                )
            )
            return None
        record, parse_issue = _parse_adr(text, relative)
        if parse_issue is not None:
            issues.append(parse_issue)
            return None
        assert record is not None
        if record["adr_id"] != adr_id:
            issues.append(
                _issue(
                    "ADR_RATIONALE_MISMATCH",
                    f"{adr_id} does not match the ADR record identity.",
                    relative,
                )
            )
            return None
        parsed[adr_id] = record
        loaded_sources[relative] = text
        return record

    design_revision = _clean(design_contract.get("design_revision", ""))
    for adr_id, decision_id in references.items():
        record = load(adr_id)
        if record is None:
            continue
        decision = catalog[decision_id]
        path = str(record["relative_path"])
        if record["status"] != "Accepted" or record["superseded_by"] != "NONE":
            issues.append(
                _issue(
                    "ADR_RATIONALE_SUPERSESSION_INVALID",
                    f"Current {adr_id} must be Accepted and not superseded.",
                    path,
                )
            )
        if record["design_revision"] != design_revision:
            issues.append(
                _issue(
                    "ADR_RATIONALE_STALE",
                    f"{adr_id} must bind current design revision {design_revision}.",
                    path,
                )
            )
        expected_basis = decision.get("basis_ids")
        actual_basis = _split_exact_ids(record["related_basis_ids_raw"], STABLE_ID)
        expected_evidence = tuple(decision.get("evidence_ids", ()))
        actual_evidence = _split_exact_ids(record["evidence_ids_raw"], EVIDENCE_ID)
        expected_maturity = (
            "SOURCE_VERIFIED" if expected_evidence else "PLANNED_AFTER_APPROVAL"
        )
        mismatches = []
        if record["primary_decision"] != decision_id:
            mismatches.append("primary decision")
        if record["decision_value"] != decision["value"]:
            mismatches.append("decision value")
        if expected_basis is None or actual_basis != expected_basis:
            mismatches.append("basis IDs")
        if record["prd_heading"] != decision["heading"]:
            mismatches.append("PRD section")
        if record["evidence_maturity"] != expected_maturity:
            mismatches.append("evidence maturity")
        if actual_evidence != expected_evidence:
            mismatches.append("evidence IDs")
        if mismatches:
            issues.append(
                _issue(
                    "ADR_RATIONALE_MISMATCH",
                    f"{adr_id} does not match the canonical "
                    + ", ".join(mismatches)
                    + ".",
                    path,
                )
            )

    visiting: set[str] = set()
    visited: set[str] = set()
    chain_decisions: dict[str, str] = {}

    def validate_chain(adr_id: str, decision_id: str) -> None:
        if adr_id in visiting:
            record = parsed.get(adr_id)
            issues.append(
                _issue(
                    "ADR_RATIONALE_SUPERSESSION_INVALID",
                    "ADR supersession contains a cycle.",
                    str(record["relative_path"]) if record else ADR_DIRECTORY,
                )
            )
            return
        if adr_id in visited:
            if chain_decisions.get(adr_id) != decision_id:
                record = parsed.get(adr_id)
                issues.append(
                    _issue(
                        "ADR_RATIONALE_SUPERSESSION_INVALID",
                        f"{adr_id} cannot support supersession chains for different decisions.",
                        str(record["relative_path"]) if record else ADR_DIRECTORY,
                    )
                )
            return
        record = load(adr_id)
        if record is None:
            return
        chain_decisions[adr_id] = decision_id
        expected_heading = catalog[decision_id]["heading"]
        if (
            record["primary_decision"] != decision_id
            or record["prd_heading"] != expected_heading
        ):
            issues.append(
                _issue(
                    "ADR_RATIONALE_SUPERSESSION_INVALID",
                    f"{adr_id} does not belong to the {decision_id} decision chain.",
                    str(record["relative_path"]),
                )
            )
        visiting.add(adr_id)
        prior_id = record["supersedes"]
        if prior_id != "NONE":
            if ADR_ID.fullmatch(prior_id) is None or prior_id == adr_id:
                issues.append(
                    _issue(
                        "ADR_RATIONALE_SUPERSESSION_INVALID",
                        f"{adr_id} has an invalid Supersedes value.",
                        str(record["relative_path"]),
                    )
                )
            else:
                prior = load(prior_id)
                if prior is not None:
                    if (
                        prior["status"] != "Superseded"
                        or prior["superseded_by"] != adr_id
                    ):
                        issues.append(
                            _issue(
                                "ADR_RATIONALE_SUPERSESSION_INVALID",
                                f"{prior_id} must reciprocally name {adr_id} as its successor.",
                                str(prior["relative_path"]),
                            )
                        )
                    validate_chain(prior_id, decision_id)
        visiting.remove(adr_id)
        visited.add(adr_id)

    for adr_id, decision_id in references.items():
        validate_chain(adr_id, decision_id)

    records = []
    for adr_id in sorted(parsed):
        record = parsed[adr_id]
        basis = _split_exact_ids(record["related_basis_ids_raw"], STABLE_ID)
        evidence = _split_exact_ids(record["evidence_ids_raw"], EVIDENCE_ID)
        records.append(
            {
                "path": record["relative_path"],
                "adr_id": adr_id,
                "status": record["status"],
                "design_revision": record["design_revision"],
                "primary_decision": record["primary_decision"],
                "decision_value": record["decision_value"],
                "related_basis_ids": list(basis or ()),
                "prd_heading": record["prd_heading"],
                "evidence_maturity": record["evidence_maturity"],
                "evidence_ids": list(evidence or ()),
                "supersedes": record["supersedes"],
                "superseded_by": record["superseded_by"],
                "source_sha256": record["source_sha256"],
                "current_reference": adr_id in references,
            }
        )
    projection["records"] = records
    if issues:
        projection["status"] = (
            "STALE"
            if all(item["code"] == "ADR_RATIONALE_STALE" for item in issues)
            else "BLOCKED"
        )
    else:
        projection["status"] = "CURRENT"
    projection["projection_sha256"] = _projection_sha256(projection)
    return projection, issues, loaded_sources
