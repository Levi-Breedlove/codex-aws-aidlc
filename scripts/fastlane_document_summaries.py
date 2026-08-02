"""Deterministic, read-only project-document summary projection."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
SUMMARY_BEGIN = "<!-- FASTLANE:DOCUMENT_SUMMARY:BEGIN -->"
SUMMARY_END = "<!-- FASTLANE:DOCUMENT_SUMMARY:END -->"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
FORBIDDEN_VISIBLE_VALUE = re.compile(
    r"(?i)(?:[A-Z]:\\Users\\|/Users/|/home/|AKIA[0-9A-Z]{16}|"
    r"R-[A-F0-9]{8,}|https?://[^\s/@]+:[^\s/@]+@)"
)


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical_markdown(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    return normalized + "\n"


def _plain(value: object, fallback: str = "Not yet recorded") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text or text in {"TODO", "NONE", "UNINITIALIZED"}:
        text = fallback
    if FORBIDDEN_VISIBLE_VALUE.search(text):
        raise ValueError("summary value contains unsafe private or ephemeral content")
    return text.replace("|", "\\|")


def _basis_ids(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    result = sorted({_plain(item, "") for item in value if _plain(item, "")})
    return result


def _relative_target(value: object) -> str:
    target = str(value or "").strip()
    path_part = target.split("#", 1)[0]
    if (
        not target
        or "\\" in target
        or target.startswith(("/", "http:", "https:", "file:"))
        or (path_part and ".." in PurePosixPath(path_part).parts)
    ):
        raise ValueError("summary navigation target must be repository-relative")
    return target


def normalized_document(specification: Mapping[str, Any]) -> dict[str, Any]:
    path = str(specification.get("path", "")).strip()
    pure_path = PurePosixPath(path)
    if (
        not path
        or pure_path.is_absolute()
        or ".." in pure_path.parts
        or pure_path.as_posix() != path
    ):
        raise ValueError("summary document path must be canonical and relative")

    raw_fields = specification.get("fields")
    if not isinstance(raw_fields, Sequence) or isinstance(raw_fields, (str, bytes)):
        raise ValueError("summary fields must be a sequence")
    fields: list[dict[str, Any]] = []
    labels: set[str] = set()
    for item in raw_fields:
        if not isinstance(item, Mapping):
            raise ValueError("summary field must be an object")
        label = _plain(item.get("label"), "")
        if not label or label in labels:
            raise ValueError("summary field labels must be non-empty and unique")
        labels.add(label)
        fields.append(
            {
                "label": label,
                "value": _plain(item.get("value")),
                "basis_ids": _basis_ids(item.get("basis_ids", [])),
            }
        )

    raw_claims = specification.get("claims", [])
    if not isinstance(raw_claims, Sequence) or isinstance(raw_claims, (str, bytes)):
        raise ValueError("summary claims must be a sequence")
    claims: list[dict[str, str]] = []
    for item in raw_claims:
        if not isinstance(item, Mapping):
            raise ValueError("summary claim must be an object")
        claims.append(
            {
                "claim": _plain(item.get("claim"), ""),
                "maturity": _plain(item.get("maturity"), ""),
                "evidence": _plain(item.get("evidence"), "None"),
                "limitation": _plain(item.get("limitation"), "None"),
            }
        )

    raw_navigation = specification.get("navigation")
    if not isinstance(raw_navigation, Sequence) or isinstance(
        raw_navigation, (str, bytes)
    ):
        raise ValueError("summary navigation must be a sequence")
    navigation: list[dict[str, str]] = []
    for item in raw_navigation:
        if not isinstance(item, Mapping):
            raise ValueError("summary navigation entry must be an object")
        navigation.append(
            {
                "label": _plain(item.get("label"), ""),
                "target": _relative_target(item.get("target")),
            }
        )
    if not navigation:
        raise ValueError("summary navigation cannot be empty")

    return {
        "path": path,
        "heading": "Current state",
        "fields": fields,
        "need_from_owner": _plain(specification.get("need_from_owner"), "Nothing"),
        "next_action": _plain(specification.get("next_action")),
        "claims": claims,
        "navigation": navigation,
    }


def render_summary_markdown(specification: Mapping[str, Any]) -> str:
    document = normalized_document(specification)
    lines = [
        "## Current state",
        "",
        "| Field | Current value |",
        "|---|---|",
    ]
    lines.extend(
        f"| {item['label']} | {item['value']} |" for item in document["fields"]
    )
    lines.extend(
        [
            f"| Need from you | {document['need_from_owner']} |",
            f"| Next | {document['next_action']} |",
        ]
    )
    if document["claims"]:
        lines.extend(
            [
                "",
                "### Important claims",
                "",
                "| Claim | Current maturity | Evidence | Limitation |",
                "|---|---|---|---|",
            ]
        )
        lines.extend(
            "| {claim} | {maturity} | {evidence} | {limitation} |".format(**item)
            for item in document["claims"]
        )
    lines.extend(["", "## Go directly to", ""])
    lines.extend(
        f"- [{item['label']}]({item['target']})" for item in document["navigation"]
    )
    return canonical_markdown("\n".join(lines))


def wrapped_summary_markdown(specification: Mapping[str, Any]) -> str:
    return (
        SUMMARY_BEGIN
        + "\n"
        + render_summary_markdown(specification)
        + SUMMARY_END
        + "\n"
    )


def _source_digest(document: Mapping[str, Any]) -> str:
    payload = {
        "fields": document["fields"],
        "need_from_owner": document["need_from_owner"],
        "next_action": document["next_action"],
        "claims": document["claims"],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256(canonical)


def _observed_summary(source: str) -> tuple[str | None, str | None]:
    begin_count = source.count(SUMMARY_BEGIN)
    end_count = source.count(SUMMARY_END)
    if begin_count == 0 and end_count == 0:
        return None, None
    if begin_count != 1 or end_count != 1:
        return None, "summary delimiters must occur exactly once"
    begin = source.index(SUMMARY_BEGIN) + len(SUMMARY_BEGIN)
    end = source.index(SUMMARY_END)
    if end <= begin:
        return None, "summary delimiters are reversed or overlapping"
    return canonical_markdown(source[begin:end]), None


def project_document_summaries(
    source_texts: Mapping[str, str],
    specifications: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    documents: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    for raw_specification in specifications:
        try:
            document = normalized_document(raw_specification)
            expected = render_summary_markdown(document)
        except (TypeError, ValueError) as exc:
            path = str(raw_specification.get("path", "NONE"))
            issues.append(
                {
                    "code": "DOCUMENT_SUMMARY_UNSAFE",
                    "path": path,
                    "message": str(exc),
                }
            )
            continue

        path = document["path"]
        observed_source = source_texts.get(path)
        status = "CURRENT"
        if observed_source is None:
            status = "BLOCKED"
            issues.append(
                {
                    "code": "DOCUMENT_SUMMARY_SOURCE_INVALID",
                    "path": path,
                    "message": "Canonical project document is unavailable",
                }
            )
        else:
            observed, unsafe_reason = _observed_summary(observed_source)
            if unsafe_reason is not None:
                status = "BLOCKED"
                issues.append(
                    {
                        "code": "DOCUMENT_SUMMARY_UNSAFE",
                        "path": path,
                        "message": unsafe_reason,
                    }
                )
            elif observed != expected:
                status = "STALE"
                issues.append(
                    {
                        "code": "DOCUMENT_SUMMARY_STALE",
                        "path": path,
                        "message": (
                            "Visible project summary differs from the current "
                            "canonical Engine projection"
                        ),
                    }
                )

        documents.append(
            {
                "path": path,
                "heading": document["heading"],
                "status": status,
                "fields": document["fields"],
                "need_from_owner": document["need_from_owner"],
                "next_action": document["next_action"],
                "claims": document["claims"],
                "navigation": document["navigation"],
                "canonical_sha256": _source_digest(document),
                "rendered_sha256": _sha256(expected.encode("utf-8")),
            }
        )

    overall = "CURRENT"
    if any(item["status"] == "BLOCKED" for item in documents) or any(
        issue["code"] in {"DOCUMENT_SUMMARY_SOURCE_INVALID", "DOCUMENT_SUMMARY_UNSAFE"}
        for issue in issues
    ):
        overall = "BLOCKED"
    elif any(item["status"] == "STALE" for item in documents):
        overall = "STALE"
    return (
        {
            "schema_version": SCHEMA_VERSION,
            "status": overall,
            "documents": documents,
        },
        issues,
    )


def _field(label: str, value: object, *basis_ids: object) -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "basis_ids": [item for item in basis_ids if item],
    }


def _spec(
    base: Mapping[str, Any],
    path: str,
    fields: Sequence[tuple[object, ...]],
    navigation: Sequence[tuple[str, str]],
    claims: Sequence[Mapping[str, str]] = (),
) -> dict[str, Any]:
    return {
        **base,
        "path": path,
        "fields": [_field(*row) for row in fields],
        "claims": list(claims),
        "navigation": [
            {"label": label, "target": target} for label, target in navigation
        ],
    }


def build_summary_specifications(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build six human-facing views from Engine-normalized canonical state."""

    template = bool(state.get("template_like"))
    req = None if template else state.get("requirements_revision")
    des = None if template else state.get("design_revision")
    auth = None if template else state.get("construction_authorization")
    gate_a = str(state.get("gate_a") or "BLOCKED")
    gate_b = str(state.get("gate_b") or "BLOCKED")
    action = str(state.get("action_kind") or "NONE_CONTINUE_AUTOMATICALLY")
    automatic = bool(state.get("automatic_continuation_allowed"))
    # fmt: off
    owner_actions = {
        "COMPLETE_PREREQUISITE_CHECKLIST": "Complete the prerequisite checklist.",
        "ANSWER_OPEN_DECISIONS": "Answer the current project question.",
        "APPROVE_GATE_A": "Review the requirements and approve them or request a correction.",
        "APPROVE_GATE_B": "Review the technical plan and approve it or request a correction.",
        "AUTHORIZE_AWS_OPERATION": "Review the exact AWS operation authorization.",
        "AUTHORIZE_AWS_READ_PREFLIGHT": "Review the exact read-only AWS authorization.",
        "AUTHORIZE_AWS_TEARDOWN": "Review the exact teardown authorization.",
        "CHOOSE_AWS_RESIDUAL_DISPOSITION": "Choose what should happen to the remaining AWS resources.",
        "REVIEW_SAFETY_BLOCKER": "Review the reported safety boundary.",
    }
    prompt_actions = {
        "BOOT-00": "Codex will verify prerequisites and initialize the project.",
        "INTAKE-10": "Codex will record the answer and ask the next material question.",
        "REQ-10": "Codex will complete and validate the product requirements.",
        "INTAKE-20": "Codex will prepare the Gate A requirements review.",
        "DESIGN-10": "Codex will complete the technical design and supporting evidence.",
        "DESIGN-20": "Codex will prepare the Gate B technical review.",
        "TASK-10": "Codex will derive the approved construction tasks.",
        "BUILD-10": "Codex will continue the active local construction task.",
        "BUILD-20": "Codex will reconcile local construction evidence.",
        "RELEASE-10": "Codex will reconcile release evidence.",
        "AWS-10": "Codex will prepare the read-only AWS preflight.",
        "AWS-20": "Codex will perform only the separately authorized deployment operation.",
        "AWS-30": "Codex will reconcile deployment evidence using read-only access.",
        "AWS-40": "Codex will review residual resources and teardown readiness.",
        "AWS-50": "Codex will perform only the separately authorized teardown operation.",
        "STOP": "Codex will continue after the required owner or safety action.",
    }
    # fmt: on
    need = (
        "Run `init template`."
        if template
        else "Nothing"
        if automatic or action == "NONE_CONTINUE_AUTOMATICALLY"
        else owner_actions.get(action, "Review the current Fastlane request.")
    )
    next_action = (
        prompt_actions["BOOT-00"]
        if template
        else prompt_actions.get(
            str(state.get("next_prompt") or ""),
            "Codex will continue from the current validated checkpoint.",
        )
    )
    phase = (
        "Not yet initialized"
        if template
        else {
            "INTAKE_REQUIRED": "Requirements discovery",
            "REQUIREMENTS_STALE": "Requirements correction",
            "WAITING_GATE_A": "Gate A requirements review",
            "WAITING_GATE_B": "Gate B technical review",
            "RELEASE_VERIFIED": "Local release verified",
            "BLOCKED": "Paused at a validated boundary",
        }.get(
            str(state.get("lifecycle_state") or ""),
            {
                "DEFINE": "Requirements",
                "DESIGN": "Technical design",
                "DELIVER": "Local construction",
            }.get(str(state.get("owner_stage") or ""), "In progress"),
        )
    )
    gate_a_status = {
        "APPROVED_FOR_DESIGN": "Approved",
        "PENDING_OWNER_APPROVAL": "Ready for owner review",
        "BLOCKED": "Not yet ready",
        "STALE": "Needs requirements review",
    }.get(gate_a, gate_a.replace("_", " ").title())
    gate_b_status = {
        "APPROVED_FOR_CONSTRUCTION": "Approved",
        "PENDING_OWNER_APPROVAL": "Ready for owner review",
        "BLOCKED": "Not yet ready",
        "STALE": "Needs technical review",
    }.get(gate_b, gate_b.replace("_", " ").title())
    if template:
        gate_a_status = gate_b_status = "Not yet initialized"

    aws_boundary = (
        "Authorized only for the current exact operation"
        if state.get("aws_account_access_authorized")
        else "Not authorized"
    )
    updated = (
        "Not yet initialized"
        if template
        else state.get("updated") or "Current canonical records"
    )
    overall = (
        "Not yet initialized"
        if template
        else "Requirements and technical plan approved"
        if gate_b == "APPROVED_FOR_CONSTRUCTION"
        else "Requirements approved; technical plan in progress"
        if gate_a == "APPROVED_FOR_DESIGN"
        else "Requirements in progress"
    )
    milestone = (
        "None"
        if template
        else "Gate B approved"
        if gate_b == "APPROVED_FOR_CONSTRUCTION"
        else "Gate A approved"
        if gate_a == "APPROVED_FOR_DESIGN"
        else "Project setup complete"
    )
    # fmt: off
    tasks = state.get("tasks") if isinstance(state.get("tasks"), Mapping) else {}
    verify = state.get("verify") if isinstance(state.get("verify"), Mapping) else {}
    operations = state.get("operations") if isinstance(state.get("operations"), Mapping) else {}
    bugfix = state.get("bugfix") if isinstance(state.get("bugfix"), Mapping) else {}
    if template:
        tasks = {"progress": "No tasks generated", "wave": "None", "active": "None", "readiness": "Not yet initialized", "blocker": "None", "checkpoint": "None", "known_green": "None", "updated": updated}
        verify = {"release_result": "Not yet initialized", "observed_count": "0", "failed_count": "0", "unobserved": "Local build, AWS deployment, recovery, and teardown", "cutoff": "Not yet recorded", "updated": updated, "claims": verify.get("claims", [])}
        operations = {"environment": "Not yet initialized", "deployment_state": "Not deployed", "authority": "None", "safe_action": "Local validation only", "deployment_approval": "Not authorized", "teardown_approval": "Not authorized", "recovery_state": "Not yet observed", "emergency_state": "No deployed environment exists", "updated": updated}
        bugfix = {**bugfix, "updated": updated}
    # fmt: on

    aws_id = state.get("aws_authorization")
    plan_id = tasks.get("plan_revision")
    base = {"need_from_owner": need, "next_action": next_action}
    # Declarative rows are kept compact because their order is part of the UI contract.
    # fmt: off
    fields = {
        "docs/project/README.md": (
            ("Phase", phase, req, des), ("Overall status", overall, req, des),
            ("Last completed milestone", milestone, req, des), ("Gate A", gate_a_status, req),
            ("Gate B", gate_b_status, des, auth), ("AWS deployment", aws_boundary, aws_id),
            ("Construction tasks", tasks.get("progress", "Not started"), auth),
            ("Verification", verify.get("release_result", "Not ready")),
            ("Operations", operations.get("deployment_state", "Not deployed")),
            ("Bounded defect", bugfix.get("status", "No active bounded defect")),
            ("AWS account access", aws_boundary, aws_id), ("Updated", updated, req, des),
        ),
        "docs/project/PRD.md": (
            ("Product outcome", "Not yet confirmed" if template else state.get("product_outcome", "Not yet confirmed"), req),
            ("First-release boundary", "Not yet confirmed" if template else state.get("release_boundary", "Not yet confirmed"), req),
            ("Requirements", gate_a_status, req), ("Technical design", gate_b_status, des),
            ("Gate A", gate_a_status, req), ("Gate B", gate_b_status, des, auth),
            ("Last completed milestone", milestone, req, des),
            ("Region and cost", state.get("region_and_cost", "Not yet recorded"), req),
            ("Construction authorization", auth or "None", auth),
            ("AWS account work", aws_boundary, aws_id),
            ("Current records", state.get("record_identities", "Not yet initialized"), req, des, auth),
            ("Updated", updated, req, des),
        ),
        "docs/project/TASKS.md": (
            ("Progress", tasks.get("progress", "No tasks generated"), plan_id),
            ("Current wave", tasks.get("wave", "None"), plan_id), ("Active task", tasks.get("active", "None")),
            ("Readiness", tasks.get("readiness", "Not started"), plan_id), ("Blocker", tasks.get("blocker", "None")),
            ("Last passing checkpoint", tasks.get("checkpoint", "None")), ("Construction approval", gate_b_status, auth),
            ("Last known-green commit", tasks.get("known_green", "None")), ("AWS account work", aws_boundary, aws_id),
            ("Updated", tasks.get("updated", updated), plan_id),
        ),
        "docs/project/VERIFY.md": (
            ("Release result", verify.get("release_result", "Not ready")),
            ("Locally observed evidence", verify.get("observed_count", "0")),
            ("Failed or stale evidence", verify.get("failed_count", "0")),
            ("Still unobserved", verify.get("unobserved", "Local build, AWS deployment, recovery, and teardown")),
            ("Evidence cutoff", verify.get("cutoff", "Not yet recorded")), ("AWS account work", aws_boundary, aws_id),
            ("Updated", verify.get("updated", updated)),
        ),
        "docs/project/RUNBOOK.md": (
            ("Environment", operations.get("environment", "Development")),
            ("Deployment state", operations.get("deployment_state", "Not deployed")),
            ("Current AWS authority", operations.get("authority", "None"), aws_id),
            ("Construction approval", gate_b_status, auth),
            ("Safest available operation", operations.get("safe_action", "Local validation only")),
            ("Deployment approval", operations.get("deployment_approval", "Not authorized")),
            ("Teardown approval", operations.get("teardown_approval", "Not authorized")),
            ("Recovery state", operations.get("recovery_state", "Not yet observed")),
            ("Emergency condition", operations.get("emergency_state", "No deployed environment exists")),
            ("AWS account work", aws_boundary, aws_id), ("Updated", operations.get("updated", updated)),
        ),
        "docs/project/BUGFIX.md": (
            ("Status", bugfix.get("status", "No active bounded defect")), ("Defect", bugfix.get("defect", "None")),
            ("User impact", bugfix.get("impact", "None")), ("Reproduction", bugfix.get("reproduction", "Not active")),
            ("Environment", bugfix.get("environment", "Not active")), ("Related requirements", bugfix.get("requirements", "None")),
            ("Root cause", bugfix.get("root_cause", "Not active")), ("Repair", bugfix.get("repair", "Not active")),
            ("Regression evidence", bugfix.get("regression", "Not active")),
            ("Architecture impact", bugfix.get("architecture", "None")), ("Updated", bugfix.get("updated", updated)),
        ),
    }
    navigation = {
        "docs/project/README.md": (("Product and technical plan", "PRD.md#product-agreement"), ("Construction progress", "TASKS.md#current-progress"), ("Verification and evidence", "VERIFY.md#current-result"), ("Operations runbook", "RUNBOOK.md#safety-boundary"), ("Bounded defect record", "BUGFIX.md#current-state")),
        "docs/project/PRD.md": (("Product Agreement", "#product-agreement"), ("Gate A Review", "#gate-a-review"), ("Technical Plan", "#technical-plan"), ("Gate B Review", "#gate-b-review"), ("Exact contract records", "#contract-appendices")),
        "docs/project/TASKS.md": (("Current progress", "#current-progress"), ("Roadmap", "#roadmap"), ("Active work and blockers", "#active-work-blockers-and-next-action"), ("Task definitions", "#task-definitions"), ("Exact execution state", "#agent-reference-exact-run-and-task-state")),
        "docs/project/VERIFY.md": (("Current result", "#current-result"), ("Passing evidence", "#verification-matrix"), ("Failed or stale evidence", "#failed-or-stale"), ("AWS evidence", "#aws-core-evidence"), ("Release decision", "#current-release-decision")),
        "docs/project/RUNBOOK.md": (("Before deploying", "#2-prerequisites"), ("Deploy", "#6-deployment"), ("Verify", "#7-smoke-tests"), ("Roll back", "#10-rollback"), ("Recover", "#11-backup-and-recovery"), ("Tear down", "#13-teardown-and-decommissioning")),
        "docs/project/BUGFIX.md": (("Summary", "#1-summary"), ("Current behavior", "#2-current-behavior"), ("Root-cause analysis", "#7-root-cause-analysis"), ("Fix constraints", "#8-fix-constraints"), ("Regression evidence", "#9-regression-and-property-specification")),
    }
    # fmt: on
    return [
        _spec(
            base,
            path,
            fields[path],
            navigation[path],
            verify.get("claims", []) if path == "docs/project/VERIFY.md" else (),
        )
        for path in fields
    ]
