"""Pure Delivery release-decision parsing.

Canonical input is already-observed VERIFY Markdown. The result and ordered
issues are non-authoritative validation output. This module performs no I/O,
mutation, routing, approval, deployment, or external action.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from ..core.ids import clean_cell


RELEASE_CLAIM_TARGETS = ("LOCAL", "AWS_READ", "DEPLOYED", "RECOVERY")
RELEASE_CLAIM_APPLICABILITY = (
    "APPLICABLE",
    "NOT_APPLICABLE",
    "UNDETERMINED",
)
RELEASE_CLAIM_STATUSES = (
    "NOT_PROVEN",
    "CURRENT",
    "HISTORICAL",
    "STALE",
    "FAILED",
    "BLOCKED",
    "NOT_APPLICABLE",
)
RELEASE_CLAIM_CODES = {
    target: f"PROJECT_TARGET_COMPLETE({target})" for target in RELEASE_CLAIM_TARGETS
}
RELEASE_RECOVERY_OBSERVATION = re.compile(
    r"^(?:ROLLBACK|RESTORE)_OBSERVED: (?P<evidence>EV-\d{4,}); "
    r"RESULT: (?:PASS|VERIFIED)$"
)
_RELEASE_CLAIM_KEYS = (
    "schema_version",
    "basis",
    "claims",
    "authority_effect",
    "authorizes_aws_access",
    "authorizes_mutation",
)
_RELEASE_CLAIM_BASIS_KEYS = (
    "requirements_revision",
    "design_revision",
    "construction_authorization",
    "artifact_sha256",
    "account",
    "region",
    "environment",
    "lane",
    "evidence_cutoff",
)
_RELEASE_TARGET_CLAIM_KEYS = (
    "applicability",
    "status",
    "evidence_ids",
    "limitations",
    "allowed_claims",
    "prohibited_claims",
)


def _require_release_claim_keys(
    value: Mapping[str, Any], expected: tuple[str, ...], label: str
) -> None:
    if set(value) != set(expected):
        raise ValueError(f"{label} must contain exactly {', '.join(expected)}")


def _release_claim_text(value: Any, label: str, *, allow_none: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    cleaned = clean_cell(value)
    if (
        not cleaned
        or len(cleaned) > 500
        or re.search(r"[\r\n\x00-\x1f\x7f]", cleaned) is not None
        or "*" in cleaned
        or (cleaned == "NONE" and not allow_none)
    ):
        raise ValueError(f"{label} must be exact, bounded, and wildcard-free")
    return cleaned


def _release_claim_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of text values")
    cleaned = [_release_claim_text(item, label) for item in value]
    if cleaned != sorted(set(cleaned)):
        raise ValueError(f"{label} must be sorted unique cumulative values")
    return cleaned


def _validate_release_claim_basis(value: Any) -> str:
    basis = value.get("basis")
    if not isinstance(basis, Mapping):
        raise ValueError("release_claim basis must be an object")
    _require_release_claim_keys(basis, _RELEASE_CLAIM_BASIS_KEYS, "release_claim basis")
    for field, pattern in (
        ("requirements_revision", r"REQ-\d{4,}"),
        ("design_revision", r"DES-\d{4,}"),
        ("construction_authorization", r"AUTH-\d{4,}"),
        ("artifact_sha256", r"sha256:[0-9a-f]{64}"),
    ):
        if re.fullmatch(pattern, str(basis.get(field, ""))) is None:
            raise ValueError(f"release_claim basis has invalid {field}")
    account = _release_claim_text(
        basis.get("account"), "release_claim account", allow_none=True
    )
    if account != "NONE" and re.fullmatch(r"\d{12}", account) is None:
        raise ValueError("release_claim account must be a 12-digit account or NONE")
    region = _release_claim_text(
        basis.get("region"), "release_claim region", allow_none=True
    )
    if (
        region != "NONE"
        and re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", region) is None
    ):
        raise ValueError("release_claim region must be canonical or NONE")
    for field in ("environment", "lane"):
        _release_claim_text(basis.get(field), f"release_claim {field}", allow_none=True)
    cutoff = _release_claim_text(
        basis.get("evidence_cutoff"), "release_claim evidence cutoff", allow_none=True
    )
    if cutoff != "NONE" and re.fullmatch(r"EV-\d{4,}", cutoff) is None:
        raise ValueError("release_claim evidence cutoff must be EV-* or NONE")
    return cutoff


def _validate_noncurrent_release_target(
    target: str,
    applicability: Any,
    status: Any,
    evidence: list[str],
    allowed: list[str],
    prohibited: list[str],
) -> None:
    code = RELEASE_CLAIM_CODES[target]
    if allowed or prohibited != [code]:
        raise ValueError(f"release_claim {target} must prohibit an unproven claim")
    if status == "HISTORICAL" and (applicability != "APPLICABLE" or not evidence):
        raise ValueError(f"release_claim {target} historical claim requires evidence")
    if status == "NOT_APPLICABLE" and (applicability != "NOT_APPLICABLE" or evidence):
        raise ValueError(f"release_claim {target} not-applicable state is invalid")
    if applicability == "NOT_APPLICABLE" and status != "NOT_APPLICABLE":
        raise ValueError(f"release_claim {target} applicability conflicts with status")


def _validate_release_target_state(
    target: str,
    applicability: Any,
    status: Any,
    evidence: list[str],
    allowed: list[str],
    prohibited: list[str],
) -> bool:
    code = RELEASE_CLAIM_CODES[target]
    if status == "CURRENT":
        if applicability != "APPLICABLE" or not evidence:
            raise ValueError(f"release_claim {target} current claim requires evidence")
        if allowed != [code] or prohibited:
            raise ValueError(f"release_claim {target} current claim code is invalid")
        return True
    _validate_noncurrent_release_target(
        target, applicability, status, evidence, allowed, prohibited
    )
    return False


def _validate_release_target(
    target: str,
    claim: Any,
    prior_evidence: set[str],
) -> tuple[set[str], bool]:
    if not isinstance(claim, Mapping):
        raise ValueError(f"release_claim {target} must be an object")
    _require_release_claim_keys(claim, _RELEASE_TARGET_CLAIM_KEYS, target)
    applicability = claim.get("applicability")
    status = claim.get("status")
    if applicability not in RELEASE_CLAIM_APPLICABILITY:
        raise ValueError(f"release_claim {target} has invalid applicability")
    if status not in RELEASE_CLAIM_STATUSES:
        raise ValueError(f"release_claim {target} has invalid status")
    evidence = _release_claim_string_list(
        claim.get("evidence_ids"), f"release_claim {target} evidence_ids"
    )
    if any(re.fullmatch(r"EV-\d{4,}", item) is None for item in evidence):
        raise ValueError(f"release_claim {target} has noncanonical evidence IDs")
    evidence_set = set(evidence)
    if evidence and not prior_evidence.issubset(evidence_set):
        raise ValueError(f"release_claim {target} evidence must be cumulative")
    limitations = _release_claim_string_list(
        claim.get("limitations"), f"release_claim {target} limitations"
    )
    if not limitations:
        raise ValueError(f"release_claim {target} requires a limitation")
    allowed = _release_claim_string_list(
        claim.get("allowed_claims"), f"release_claim {target} allowed_claims"
    )
    prohibited = _release_claim_string_list(
        claim.get("prohibited_claims"), f"release_claim {target} prohibited_claims"
    )
    current = _validate_release_target_state(
        target, applicability, status, evidence, allowed, prohibited
    )
    if evidence and prior_evidence and evidence_set == prior_evidence:
        raise ValueError(f"release_claim {target} requires new target evidence")
    return evidence_set if evidence else prior_evidence, current


def _validate_current_target_chain(current_targets: set[str]) -> None:
    for index, target in enumerate(RELEASE_CLAIM_TARGETS):
        if target in current_targets and any(
            lower not in current_targets for lower in RELEASE_CLAIM_TARGETS[:index]
        ):
            raise ValueError(
                f"release_claim {target} current state requires current lower targets"
            )


def validate_release_claim_projection(value: Any) -> dict[str, Any]:
    """Validate one additive schema-2 project-target claim projection.

    SAFETY: this validates shape and overclaim boundaries only. It performs no
    observation or policy derivation and creates no gate, authority, or AWS access.
    """

    if not isinstance(value, Mapping):
        raise ValueError("release_claim must be an object")
    _require_release_claim_keys(value, _RELEASE_CLAIM_KEYS, "release_claim")
    if value.get("schema_version") != 1:
        raise ValueError("release_claim schema_version must be 1")
    if (
        value.get("authority_effect") != "NONE"
        or value.get("authorizes_aws_access") is not False
        or value.get("authorizes_mutation") is not False
    ):
        raise ValueError("release_claim must have no authority effect")
    cutoff = _validate_release_claim_basis(value)
    claims = value.get("claims")
    if not isinstance(claims, Mapping) or set(claims) != set(RELEASE_CLAIM_TARGETS):
        raise ValueError(
            "release_claim claims must contain every project target exactly once"
        )
    prior_evidence: set[str] = set()
    current_targets: set[str] = set()
    for target in RELEASE_CLAIM_TARGETS:
        prior_evidence, current = _validate_release_target(
            target, claims.get(target), prior_evidence
        )
        if current:
            current_targets.add(target)
    _validate_current_target_chain(current_targets)
    basis = value["basis"]
    if current_targets.intersection({"AWS_READ", "DEPLOYED", "RECOVERY"}) and (
        basis["account"] == "NONE" or basis["region"] == "NONE"
    ):
        raise ValueError("release_claim current AWS targets require account and region")
    deployed_evidence = set(claims["DEPLOYED"]["evidence_ids"])
    if claims["DEPLOYED"]["status"] == "CURRENT" and cutoff not in deployed_evidence:
        raise ValueError(
            "release_claim deployed targets require a current evidence cutoff"
        )
    return copy.deepcopy(dict(value))


def _canonical_release_evidence(*groups: Any) -> list[str]:
    values = {
        clean_cell(item)
        for group in groups
        if isinstance(group, (list, tuple, set, frozenset))
        for item in group
        if isinstance(item, str) and re.fullmatch(r"EV-\d{4,}", clean_cell(item))
    }
    return sorted(values)


def _release_basis(
    *,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    artifact_sha256: str,
    environment: str,
    lane: str,
    evidence_cutoff: str,
    preflight: Mapping[str, Any],
) -> dict[str, str] | None:
    identifiers = (
        (requirements_revision, r"REQ-\d{4,}"),
        (design_revision, r"DES-\d{4,}"),
        (construction_authorization, r"AUTH-\d{4,}"),
        (artifact_sha256, r"sha256:[0-9a-f]{64}"),
    )
    if any(
        re.fullmatch(pattern, clean_cell(value)) is None
        for value, pattern in identifiers
    ):
        return None
    cleaned_environment = clean_cell(environment)
    cleaned_lane = clean_cell(lane) or "NONE"
    if not cleaned_environment or cleaned_environment in {"TODO", "TBD", "NONE"}:
        return None
    preflight_ready = (
        preflight.get("status") == "READY"
        and preflight.get("account_access") == "READ_ONLY_OBSERVED"
        and not preflight.get("issues")
    )
    candidate_account = clean_cell(preflight.get("account", ""))
    candidate_region = clean_cell(preflight.get("region", ""))
    candidate_environment = clean_cell(preflight.get("environment", ""))
    preflight_scope_valid = bool(
        preflight_ready
        and re.fullmatch(r"\d{12}", candidate_account)
        and re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", candidate_region)
        and candidate_environment == cleaned_environment
    )
    account = candidate_account if preflight_scope_valid else "NONE"
    region = candidate_region if preflight_scope_valid else "NONE"
    cutoff = clean_cell(evidence_cutoff)
    if re.fullmatch(r"EV-\d{4,}", cutoff) is None:
        cutoff = "NONE"
    return {
        "requirements_revision": clean_cell(requirements_revision),
        "design_revision": clean_cell(design_revision),
        "construction_authorization": clean_cell(construction_authorization),
        "artifact_sha256": clean_cell(artifact_sha256),
        "account": account,
        "region": region,
        "environment": cleaned_environment,
        "lane": cleaned_lane,
        "evidence_cutoff": cutoff,
    }


def _read_observation_current(
    preflight: Mapping[str, Any],
    artifact_sha256: str,
    basis: Mapping[str, str],
) -> bool:
    return bool(
        preflight.get("status") == "READY"
        and preflight.get("account_access") == "READ_ONLY_OBSERVED"
        and clean_cell(preflight.get("artifact_digest", artifact_sha256))
        == artifact_sha256
        and clean_cell(preflight.get("account", "")) == basis["account"]
        and clean_cell(preflight.get("region", "")) == basis["region"]
        and clean_cell(preflight.get("environment", "")) == basis["environment"]
        and basis["account"] != "NONE"
        and basis["region"] != "NONE"
        and not preflight.get("issues")
        and _canonical_release_evidence(preflight.get("evidence_ids", []))
    )


def _deployment_observation_current(
    deployment: Mapping[str, Any], artifact_sha256: str, evidence_cutoff: str
) -> bool:
    acceptance = _canonical_release_evidence(
        deployment.get("acceptance_evidence_ids", [])
    )
    return bool(
        deployment.get("status") in {"RECONCILED", "CONSUMED"}
        and deployment.get("action_status") == "SUCCEEDED"
        and deployment.get("reconciliation_status") == "COMPLETE"
        and clean_cell(deployment.get("artifact_digest", "")) == artifact_sha256
        and deployment.get("identity_and_boundary_match") in {"PASS", "VERIFIED"}
        and deployment.get("acknowledged") is True
        and clean_cell(deployment.get("acknowledged_evidence_id", ""))
        == clean_cell(evidence_cutoff)
        and clean_cell(deployment.get("release_evidence_cutoff", ""))
        == clean_cell(evidence_cutoff)
        and clean_cell(deployment.get("evidence_id", "")) == clean_cell(evidence_cutoff)
        and not deployment.get("basis_stale")
        and not deployment.get("issues")
        and acceptance
        and re.fullmatch(r"EV-\d{4,}", clean_cell(evidence_cutoff)) is not None
    )


def _release_target_claim(
    target: str,
    *,
    applicable: bool,
    observed: bool,
    current: bool,
    evidence: list[str],
) -> dict[str, Any]:
    code = RELEASE_CLAIM_CODES[target]
    current = applicable and current
    if not applicable:
        status = "NOT_APPLICABLE"
        evidence = []
        limitation = (
            "The approved project completion target excludes this higher target."
        )
    elif current:
        status = "CURRENT"
        limitation = "Current evidence proves only this named project target."
    elif observed:
        status = "HISTORICAL"
        limitation = "Historical evidence does not prove the current project target."
    else:
        status = "NOT_PROVEN"
        evidence = []
        limitation = "Current evidence does not prove this named project target."
    return {
        "applicability": "APPLICABLE" if applicable else "NOT_APPLICABLE",
        "status": status,
        "evidence_ids": evidence,
        "limitations": [limitation],
        "allowed_claims": [code] if current else [],
        "prohibited_claims": [] if current else [code],
    }


def _release_claim_evidence(
    *,
    local_evidence_ids: Any,
    preflight: Mapping[str, Any],
    deployment: Mapping[str, Any],
    recovery_evidence_ids: Any,
) -> tuple[dict[str, list[str]], list[str]]:
    local_evidence = _canonical_release_evidence(local_evidence_ids)
    read_evidence = _canonical_release_evidence(
        local_evidence, preflight.get("evidence_ids", [])
    )
    recovery_increment = _canonical_release_evidence(recovery_evidence_ids)
    deployment_acceptance = [
        item
        for item in _canonical_release_evidence(
            deployment.get("acceptance_evidence_ids", [])
        )
        if item not in recovery_increment
    ]
    deployment_evidence = _canonical_release_evidence(
        read_evidence,
        deployment_acceptance,
        [deployment.get("evidence_id", "")],
    )
    return (
        {
            "LOCAL": local_evidence,
            "AWS_READ": read_evidence,
            "DEPLOYED": deployment_evidence,
            "RECOVERY": _canonical_release_evidence(
                deployment_evidence, recovery_increment
            ),
        },
        recovery_increment,
    )


def derive_release_claim_projection(
    *,
    requirements_schema: str,
    completion_target: str | None,
    requirements_revision: str,
    design_revision: str,
    construction_authorization: str,
    artifact_sha256: str,
    environment: str,
    lane: str,
    release_state: str,
    evidence_cutoff: str,
    local_evidence_ids: Any,
    preflight: Mapping[str, Any],
    deployment: Mapping[str, Any],
    recovery_evidence_ids: Any = (),
    local_ready: bool = False,
    has_errors: bool = False,
) -> dict[str, Any] | None:
    """Project current target claims only for the new exact Requirements contract."""

    if requirements_schema != "1.5" or completion_target not in RELEASE_CLAIM_TARGETS:
        return None
    basis = _release_basis(
        requirements_revision=requirements_revision,
        design_revision=design_revision,
        construction_authorization=construction_authorization,
        artifact_sha256=artifact_sha256,
        environment=environment,
        lane=lane,
        evidence_cutoff=evidence_cutoff,
        preflight=preflight,
    )
    if basis is None:
        return None
    evidence, recovery_increment = _release_claim_evidence(
        local_evidence_ids=local_evidence_ids,
        preflight=preflight,
        deployment=deployment,
        recovery_evidence_ids=recovery_evidence_ids,
    )
    local_observed = bool(
        local_ready
        and evidence["LOCAL"]
        and release_state in {"READY_TO_DEPLOY", "RELEASE_VERIFIED"}
    )
    read_observed = local_observed and _read_observation_current(
        preflight, artifact_sha256, basis
    )
    deployed_observed = (
        read_observed
        and _deployment_observation_current(
            deployment, artifact_sha256, basis["evidence_cutoff"]
        )
        and basis["evidence_cutoff"] not in recovery_increment
    )
    recovery_observed = deployed_observed and bool(recovery_increment)
    observed = {
        "LOCAL": local_observed,
        "AWS_READ": read_observed,
        "DEPLOYED": deployed_observed,
        "RECOVERY": recovery_observed,
    }
    target_index = RELEASE_CLAIM_TARGETS.index(completion_target)
    claims = {
        target: _release_target_claim(
            target,
            applicable=index <= target_index,
            observed=observed[target],
            current=observed[target] and not has_errors,
            evidence=evidence[target],
        )
        for index, target in enumerate(RELEASE_CLAIM_TARGETS)
    }
    return validate_release_claim_projection(
        {
            "schema_version": 1,
            "basis": basis,
            "claims": claims,
            "authority_effect": "NONE",
            "authorizes_aws_access": False,
            "authorizes_mutation": False,
        }
    )


def parse_release_decision_record(
    text: str | None,
) -> tuple[dict[str, str], tuple[tuple[str, str], ...]]:
    """CANONICALIZATION: return release state and exact ordered issues."""

    fallback = {"release_state": "NOT_READY", "active_evidence_cutoff": "NONE"}
    if text is None:
        return fallback, ()
    heading = "## Current release decision"
    matches = list(re.finditer(rf"^{re.escape(heading)}[ \t]*$", text, re.MULTILINE))
    if len(matches) != 1:
        return fallback, (("RELEASE_DECISION", f"Expected exactly one {heading!r}"),)
    section = text[matches[0].end() :]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    issues: list[tuple[str, str]] = []
    decisions = re.findall(r"^- Release state:\s*`([^`]+)`\s*$", section, re.MULTILINE)
    release_state = decisions[0] if len(decisions) == 1 else "NOT_READY"
    if len(decisions) != 1 or decisions[0] not in {
        "NOT_READY",
        "READY_TO_DEPLOY",
        "RELEASE_VERIFIED",
    }:
        issues.append(
            (
                "RELEASE_DECISION",
                "Release decision must be exactly NOT_READY, READY_TO_DEPLOY, or RELEASE_VERIFIED",
            )
        )
        release_state = "NOT_READY"
    cutoff_rows = re.findall(
        r"^- Active evidence cutoff:\s*(?P<value>[^\r\n]+?)\s*$",
        section,
        re.MULTILINE,
    )
    cutoff = clean_cell(cutoff_rows[0]) if len(cutoff_rows) == 1 else "NONE"
    if len(cutoff_rows) != 1 or (
        cutoff not in {"TODO", "NONE"} and re.fullmatch(r"EV-\d{4,}", cutoff) is None
    ):
        issues.append(
            (
                "RELEASE_EVIDENCE_CUTOFF",
                "Active evidence cutoff must appear exactly once and be TODO, NONE, "
                "or one canonical EV-* ID",
            )
        )
        cutoff = "NONE"
    return {
        "release_state": release_state,
        "active_evidence_cutoff": cutoff,
    }, tuple(issues)


__all__ = (
    "RELEASE_CLAIM_APPLICABILITY",
    "RELEASE_CLAIM_CODES",
    "RELEASE_CLAIM_STATUSES",
    "RELEASE_CLAIM_TARGETS",
    "RELEASE_RECOVERY_OBSERVATION",
    "derive_release_claim_projection",
    "parse_release_decision_record",
    "validate_release_claim_projection",
)
