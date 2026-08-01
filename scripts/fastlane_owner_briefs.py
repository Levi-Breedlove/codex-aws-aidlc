#!/usr/bin/env python3
"""Pure derived projections for Fastlane owner decisions.

The project documents remain canonical.  This module validates and hashes
ephemeral owner-facing views; it does not parse or write project records.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence


SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
MAX_OWNER_BRIEF_OUTPUT_BYTES = 48_000
ALLOWED_MATURITIES = frozenset(
    {
        "CONFIRMED_BY_OWNER",
        "OBSERVED_IN_REPOSITORY",
        "SOURCE_VERIFIED",
        "LOCALLY_OBSERVED",
        "AWS_READ_OBSERVED",
        "DEPLOYED_OBSERVED",
        "RECOVERY_OBSERVED",
        "PLANNED_AFTER_APPROVAL",
        "NOT_YET_OBSERVED",
        "NOT_AUTHORIZED",
    }
)
BRIEF_STATUSES = frozenset({"NONE", "BUILDING", "READY", "STALE", "BLOCKED"})
TECHNICAL_DOMAINS = frozenset(
    {
        "application/runtime",
        "identity",
        "data",
        "messaging",
        "edge/networking",
        "observability",
        "deployment/recovery",
        "validation/construction",
    }
)
WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
SECRET_LIKE = re.compile(
    r"(?:AKIA|ASIA)[0-9A-Z]{16}|github_pat_|gh[pousr]_|sk-proj-|"
    r"(?:password|secret|access[_-]?key|client[_-]?secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def canonical_sha256(value: Mapping[str, Any]) -> str:
    """Hash one JSON projection using the stable Fastlane JSON grammar."""

    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def canonical_section_bytes(text: str) -> bytes:
    """Return LF-normalized UTF-8 bytes ending in exactly one LF."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    return (normalized + "\n").encode("utf-8")


def source_locator(
    *,
    key: str,
    label: str,
    path: str,
    heading: str,
    start_line: int,
    end_line: int,
    section_text: str,
    required: bool = True,
) -> dict[str, Any]:
    """Build one repository-relative, content-bound source locator."""

    if (
        not key
        or not label
        or not path
        or not heading
        or path.startswith(("/", "\\"))
        or WINDOWS_ABSOLUTE.match(path)
        or ".." in path.replace("\\", "/").split("/")
        or "\\" in path
        or start_line < 1
        or end_line < start_line
    ):
        raise ValueError("source locator is not repository-relative and canonical")
    content = canonical_section_bytes(section_text)
    return {
        "key": key,
        "label": label,
        "path": path,
        "heading": heading,
        "start_line": start_line,
        "end_line": end_line,
        "section_sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "required": required,
    }


def claim(
    text: str,
    maturity: str,
    *,
    basis_ids: Sequence[str] = (),
    evidence_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Create one evidence-bound plain-language claim."""

    if not text.strip() or maturity not in ALLOWED_MATURITIES:
        raise ValueError("owner claim is incomplete or has an invalid maturity")
    return {
        "text": text.strip(),
        "maturity": maturity,
        "basis_ids": sorted({item for item in basis_ids if item}),
        "evidence_ids": sorted({item for item in evidence_ids if item}),
    }


def empty_owner_decision_brief() -> dict[str, Any]:
    """Return the additive neutral projection used outside a pending gate."""

    return {
        "schema_version": 1,
        "kind": "NONE",
        "status": "NONE",
        "basis": {
            "requirements_revision": None,
            "design_revision": None,
            "construction_authorization": None,
            "design_contract_sha256": None,
        },
        "executive_sections": [],
        "technical_decision_groups": [],
        "claims": [],
        "source_locators": [],
        "authorization_effect": {"approves": [], "does_not_approve": []},
        "formal_receipt_required": False,
        "canonical_sha256": None,
    }


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def validate_owner_decision_brief(projection: Mapping[str, Any]) -> list[str]:
    """Return stable issue strings for a derived Owner Decision Brief."""

    issues: list[str] = []
    kind = projection.get("kind")
    status = projection.get("status")
    if projection.get("schema_version") != 1 or kind not in {"NONE", "GATE_A", "GATE_B"}:
        issues.append("brief identity is invalid")
    if status not in BRIEF_STATUSES:
        issues.append("brief status is invalid")
    for field in ("executive_sections", "technical_decision_groups", "claims", "source_locators"):
        if not _sequence(projection.get(field)):
            issues.append(f"{field} must be an array")
    if kind == "NONE":
        return issues
    sections = projection.get("executive_sections", [])
    if status == "READY" and not sections:
        issues.append("brief has no executive decision sections")
    for section in sections if _sequence(sections) else []:
        if not isinstance(section, Mapping) or not all(
            isinstance(section.get(field), str) and section.get(field)
            for field in ("section_id", "title")
        ):
            issues.append("brief contains an invalid executive section")
            continue
        items = section.get("items")
        if not _sequence(items) or not items or any(
            not isinstance(item, str) or not item.strip() for item in items
        ):
            issues.append(f"{section.get('section_id')} has invalid owner-facing items")
    groups = projection.get("technical_decision_groups", [])
    if kind == "GATE_B" and status == "READY" and not groups:
        issues.append("Gate B has no technical decision index")
    if kind == "GATE_A" and groups:
        issues.append("Gate A cannot contain a technical decision index")
    seen_domains: set[str] = set()
    seen_decisions: set[str] = set()
    referenced_locator_keys: set[str] = set()
    for group in groups if _sequence(groups) else []:
        if not isinstance(group, Mapping) or not isinstance(group.get("domain"), str):
            issues.append("brief contains an invalid technical decision group")
            continue
        domain = str(group["domain"])
        if domain not in TECHNICAL_DOMAINS or domain in seen_domains:
            issues.append("technical decision domains must be allowed and unique")
        else:
            seen_domains.add(domain)
        decisions = group.get("decisions")
        if not _sequence(decisions) or not decisions:
            issues.append(f"{domain} decisions must be a non-empty array")
            continue
        for decision in decisions:
            if not isinstance(decision, Mapping):
                issues.append("brief contains an invalid technical decision")
                continue
            decision_id = decision.get("decision_id")
            if not isinstance(decision_id, str) or not decision_id or decision_id in seen_decisions:
                issues.append("technical decision IDs must be present and unique")
            else:
                seen_decisions.add(decision_id)
            for field in ("decision", "selection", "why", "tradeoff"):
                if not isinstance(decision.get(field), str) or not decision.get(field):
                    issues.append(f"{decision_id or 'decision'} is missing {field}")
            for field in ("basis_ids", "evidence_ids", "source_locator_keys"):
                values = decision.get(field)
                if not _sequence(values) or any(
                    not isinstance(item, str) or not item for item in values or []
                ):
                    issues.append(f"{decision_id or 'decision'} has invalid {field}")
            if status == "READY" and not decision.get("basis_ids"):
                issues.append(f"{decision_id or 'decision'} has no canonical basis")
            source_keys = decision.get("source_locator_keys")
            if status == "READY" and not source_keys:
                issues.append(f"{decision_id or 'decision'} has no source location")
            elif _sequence(source_keys):
                referenced_locator_keys.update(str(item) for item in source_keys)
    claims = projection.get("claims", [])
    for item in claims if _sequence(claims) else []:
        if not isinstance(item, Mapping) or item.get("maturity") not in ALLOWED_MATURITIES:
            issues.append("brief contains an invalid claim maturity")
        elif not isinstance(item.get("text"), str) or not item.get("text"):
            issues.append("brief contains an empty claim")
    locators = projection.get("source_locators", [])
    if status == "READY" and not locators:
        issues.append("ready brief has no canonical source locations")
    keys: set[str] = set()
    for locator in locators if _sequence(locators) else []:
        if not isinstance(locator, Mapping):
            issues.append("brief contains an invalid source locator")
            continue
        key = locator.get("key")
        path = locator.get("path")
        digest = locator.get("section_sha256")
        if not isinstance(key, str) or not key or key in keys:
            issues.append("source locator keys must be present and unique")
        else:
            keys.add(key)
        start_line = locator.get("start_line")
        end_line = locator.get("end_line")
        if (
            not isinstance(locator.get("label"), str)
            or not locator.get("label")
            or not isinstance(locator.get("heading"), str)
            or not locator.get("heading")
            or not isinstance(start_line, int)
            or not isinstance(end_line, int)
            or start_line < 1
            or end_line < start_line
            or not isinstance(locator.get("required"), bool)
        ):
            issues.append("source locator coordinates are invalid")
        if (
            not isinstance(path, str)
            or path.startswith(("/", "\\"))
            or WINDOWS_ABSOLUTE.match(path)
            or "\\" in path
            or ".." in path.split("/")
        ):
            issues.append("source locator path is unsafe")
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            issues.append("source locator digest is invalid")
    missing_locator_keys = sorted(referenced_locator_keys - keys)
    if missing_locator_keys:
        issues.append(
            "technical decisions reference missing source locations: "
            + ", ".join(missing_locator_keys)
        )
    serialized = json.dumps(projection, ensure_ascii=False)
    if SECRET_LIKE.search(serialized) is not None:
        issues.append("brief contains secret-like content")
    authorization = projection.get("authorization_effect")
    if not isinstance(authorization, Mapping) or any(
        not _sequence(authorization.get(field)) or not authorization.get(field)
        for field in ("approves", "does_not_approve")
    ):
        issues.append("brief approval boundary is incomplete")
    if projection.get("formal_receipt_required") is not (status == "READY"):
        issues.append("brief receipt requirement conflicts with readiness")
    return issues


def finalize_owner_decision_brief(projection: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Validate and digest a projection without raising into Engine routing."""

    projection = dict(projection)
    projection.pop("canonical_sha256", None)
    issues = validate_owner_decision_brief(projection)
    output_bytes = len(
        json.dumps(
            projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )
    if output_bytes > MAX_OWNER_BRIEF_OUTPUT_BYTES:
        issues.append(
            "brief exceeds the deterministic owner-facing output budget "
            f"({output_bytes} > {MAX_OWNER_BRIEF_OUTPUT_BYTES} bytes)"
        )
    projection["canonical_sha256"] = canonical_sha256(projection) if not issues else None
    return projection, issues


def answer_confirmation(
    *,
    status: str = "NONE",
    owner_response_id: str | None = None,
    card_id: str | None = None,
    revision: int | None = None,
    presented_sha256: str | None = None,
    recorded: Sequence[str] = (),
    project_effect: str | None = None,
    correction_prompt: str | None = None,
    basis_ids: Sequence[str] = (),
    source_locators: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build one ephemeral confirmation of a validated normalized owner answer."""

    projection: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "owner_response_id": owner_response_id,
        "card_binding": {
            "card_id": card_id,
            "revision": revision,
            "presented_sha256": presented_sha256,
        },
        "recorded": list(recorded),
        "project_effect": project_effect,
        "correction_prompt": correction_prompt,
        "basis_ids": sorted({item for item in basis_ids if item}),
        "source_locators": [dict(item) for item in source_locators],
        "canonical_sha256": None,
    }
    valid_ready = bool(
        status == "READY"
        and isinstance(owner_response_id, str)
        and isinstance(card_id, str)
        and isinstance(revision, int)
        and revision > 0
        and isinstance(presented_sha256, str)
        and SHA256.fullmatch(presented_sha256)
        and projection["recorded"]
        and project_effect
        and correction_prompt
    )
    if status not in {"NONE", "READY", "BLOCKED"} or (status == "READY" and not valid_ready):
        projection["status"] = "BLOCKED"
    digest_source = dict(projection)
    digest_source.pop("canonical_sha256", None)
    projection["canonical_sha256"] = canonical_sha256(digest_source)
    return projection
