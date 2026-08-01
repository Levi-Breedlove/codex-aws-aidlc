from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / ".codex" / "hooks" / "fastlane_hook.py"
EXAMPLE_PATH = REPOSITORY_ROOT / ".codex" / "hooks.fastlane.example.json"
DOCTOR_PATH = REPOSITORY_ROOT / "scripts" / "bootstrap_doctor.py"
SPEC = importlib.util.spec_from_file_location("fastlane_hook", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
fastlane_hook = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fastlane_hook)


DOCTOR_SPEC = importlib.util.spec_from_file_location(
    "bootstrap_doctor_for_hook_tests", DOCTOR_PATH
)
if DOCTOR_SPEC is None or DOCTOR_SPEC.loader is None:
    raise RuntimeError(f"Unable to load {DOCTOR_PATH}")
doctor = importlib.util.module_from_spec(DOCTOR_SPEC)
sys.modules[DOCTOR_SPEC.name] = doctor
DOCTOR_SPEC.loader.exec_module(doctor)


def normalized_authority(
    authority: dict[str, object], *, verify_text: str | None = None
) -> dict[str, object]:
    raw = dict(authority)
    ctx = doctor.Context(REPOSITORY_ROOT)
    ctx.texts[doctor.VERIFY_FILE] = verify_text or (
        REPOSITORY_ROOT / doctor.VERIFY_FILE
    ).read_text(encoding="utf-8")
    raw["request_match"] = doctor.derive_request_match(ctx, raw)
    return raw


def report(
    *,
    construction: str = "NONE",
    aws: str = "NONE",
    automatic: bool = False,
    owner_action: bool = True,
    formal_receipt: bool = False,
    write_authority: dict[str, object] | None = None,
    external_authority: dict[str, object] | None = None,
) -> dict[str, object]:
    raw_external = external_authority or {
        "kind": "NONE",
        "validity": "NONE",
        "resources": [],
        "operations": [],
    }
    projected_external = (
        raw_external
        if "request_match" in raw_external
        else normalized_authority(raw_external)
    )
    return {
        "gates": {"gate_a": "BLOCKED", "gate_b": "BLOCKED"},
        "authorizations": {"construction": construction, "aws": aws},
        "write_authority": write_authority
        or {
            "valid": False,
            "approved_write_roots": [],
            "exclusions": [],
            "protected_paths": [],
            "active_task": "NONE",
            "active_task_write_set": [],
        },
        "external_authority": projected_external,
        "hook_constraints": {
            "GitHub boundary": "NONE",
            "GitHub repository, branch, and merge constraints": "NONE",
        },
        "interaction": {
            "owner_stage": "DEFINE",
            "owner_action_kind": "ANSWER_OPEN_DECISIONS",
            "automatic_continuation_allowed": automatic,
            "owner_action_required": owner_action,
            "formal_receipt_required": formal_receipt,
        },
    }


def payload(event: str, root: Path, **values: object) -> dict[str, object]:
    result: dict[str, object] = {
        "hook_event_name": event,
        "cwd": str(root),
        "permission_mode": "default",
    }
    result.update(values)
    return result


def github_envelope(
    boundary: str = "BRANCH_AND_PR", *, merge: str = "PROHIBITED"
) -> dict[str, str]:
    return {
        "AWS boundary": "NONE",
        "GitHub boundary": boundary,
        "GitHub repository, branch, and merge constraints": (
            f"REPO: example/project; BRANCH: fast-lane; MERGE: {merge}"
        ),
    }


def authority(
    kind: str,
    operations: list[str],
    *,
    authorization_id: str = "AUTH-0001",
    resources: list[str] | None = None,
) -> dict[str, object]:
    return {
        "kind": kind,
        "validity": "CURRENT",
        "authorization_id": authorization_id,
        "receipt_digest": "NONE",
        "account": "ACCOUNT: 111122223333",
        "region": "REGION: us-west-2",
        "environment": "ENVIRONMENT: development",
        "role_or_profile": "ROLE: fastlane-role",
        "resources": [
            f"RESOURCES: {item}" for item in (resources or ["fastlane-stack"])
        ],
        "operations": [f"OPERATIONS: {item}" for item in operations],
        "artifact_plan_binding": {
            "artifact": "EXACT_DIGEST: sha256:" + "a" * 64,
            "plan": "STACK: change-set-1",
        },
        "cost_ceiling": "USD: 25.00",
        "rollback_boundary": "ROLLBACK: restore the previous stack",
        "expiration": "2099-12-31T23:59:59+00:00",
    }


def read_preflight_document(
    *,
    receipt_artifact: str | None = None,
    row_artifact: str | None = None,
    valid_until: str = "ONE_OPERATION",
) -> str:
    receipt_artifact = receipt_artifact or "sha256:" + "a" * 64
    row_artifact = row_artifact or receipt_artifact
    receipt = "\n".join(
        (
            "AUTHORIZE AWS READ-ONLY PREFLIGHT",
            "Read authorization: AWS-READ-AUTH-0001",
            "Construction authorization: AUTH-0001",
            "Profile or role: fastlane-role",
            "Account: 111122223333",
            "Region: us-west-2",
            "Environment: development",
            "Stack, application, and resources: fastlane-stack",
            "Allowed read-only operations: cloudformation:DescribeStacks",
            f"Artifact digest: {receipt_artifact}",
            "Prohibited operations: ALL_MUTATIONS",
            f"Valid until: {valid_until}",
            "Approver: owner-handle",
        )
    )
    digest = "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()
    headers = (
        "Action",
        "Authorization ID",
        "Construction AUTH",
        "Role or profile",
        "Artifact digest",
        "IaC plan/change-set binding",
        "Account / Region / environment",
        "Resources and operations",
        "Cost ceiling and validity",
        "Rollback boundary",
        "Stable owner-message source",
        "Approver",
        "Observed at",
        "Verbatim receipt SHA-256",
        "Preflight evidence",
        "Identity and boundary match",
        "Result",
    )
    row = (
        "Read-only preflight",
        "AWS-READ-AUTH-0001",
        "AUTH-0001",
        "fastlane-role",
        row_artifact,
        "NOT_APPLICABLE — read-only preflight creates no plan",
        "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
        "RESOURCES: fastlane-stack; OPERATIONS: cloudformation:DescribeStacks",
        "COST: expected low-volume request charges under USD 0.01; "
        "BOUNDED_BY: MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00; "
        f"VALID_UNTIL: {valid_until}",
        "NOT_APPLICABLE — no mutation",
        "owner-message-1",
        "owner-handle",
        "2026-07-20T12:00:00+00:00",
        digest,
        "NONE",
        "PASS",
        "AUTHORIZED",
    )
    return "\n".join(
        (
            "<!-- bootstrap:aws-read-preflight-receipt:start -->",
            "```text",
            receipt,
            "```",
            "<!-- bootstrap:aws-read-preflight-receipt:end -->",
            "## Action authorization provenance",
            "| " + " | ".join(headers) + " |",
            "|" + "|".join("---" for _ in headers) + "|",
            "| " + " | ".join(row) + " |",
            "| Deployment | " + " | ".join("TODO" for _ in headers[1:]) + " |",
        )
    )


def aws_request(operation: str, stack: str = "fastlane-stack") -> dict[str, object]:
    return {
        "service_name": "cloudformation",
        "operation_name": operation,
        "parameters": {"StackName": stack},
        "region": "us-west-2",
        "aws_profile": "fastlane-role",
    }


def patch_input(path: str) -> dict[str, str]:
    return {"command": f"*** Begin Patch\n*** Update File: {path}\n*** End Patch"}


def _section_rows(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == heading]
    if len(starts) != 1:
        raise AssertionError(f"expected one {heading!r} heading")
    rows: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## "):
            break
        if line.startswith("|"):
            rows.append(line)
    if len(rows) < 3:
        raise AssertionError(f"expected a data table after {heading!r}")
    return rows[2:]


def _marked_block_lines(text: str, name: str) -> list[str]:
    start = f"<!-- bootstrap:{name}:start -->"
    end = f"<!-- bootstrap:{name}:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise AssertionError(f"expected one marked {name!r} block")
    return text.split(start, 1)[1].split(end, 1)[0].strip().splitlines()


def _table_line(cells: tuple[str, ...]) -> str:
    return "| " + " | ".join(cells) + " |"


def _action_unknown_row(
    status: str = "UNKNOWN",
    phase: str = "AWS-20",
    evidence_id: str = "EV-9001",
) -> str:
    return _table_line(
        (
            evidence_id,
            "AWS-DEPLOY-0001",
            phase,
            "REQ-0001 / DES-0001 / AUTH-0001",
            "AWS-AUTH-0001",
            "sha256:" + "1" * 64,
            "2099-01-01T00:00:00Z",
            "owner-message MSG-AWS-0001",
            "NONE",
            "fastlane-deployment-role",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "sha256:" + "a" * 64,
            "TYPE: CLOUDFORMATION_CHANGE_SET; IDENTIFIER: change-set-1; DIGEST: sha256:"
            + "b" * 64,
            "fastlane-stack",
            "cloudformation:ExecuteChangeSet",
            "NONE",
            "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
            "OPERATION_IDS: change-set-1; DIRECT_RESULT: authority lost before terminal observation",
            "NONE",
            "NONE",
            "2026-07-29T00:01:00Z",
            "local closure journal",
            "PASS",
            "mutation outcome requires read-only reconciliation",
            status,
        )
    )


def _read_receipt_lines(read_id: str = "AWS-READ-AUTH-9001") -> list[str]:
    return [
        "```text",
        "AUTHORIZE AWS READ-ONLY PREFLIGHT",
        f"Read authorization: {read_id}",
        "Construction authorization: AUTH-0001",
        "Profile or role: fastlane-read-role",
        "Account: 111122223333",
        "Region: us-west-2",
        "Environment: development",
        "Stack, application, and resources: fastlane-stack",
        "Allowed read-only operations: cloudformation:DescribeStacks",
        "Artifact digest: sha256:" + "a" * 64,
        "Prohibited operations: ALL_MUTATIONS",
        "Valid until: 2099-01-01T00:00:00Z",
        "Approver: owner-handle",
        "```",
    ]


def _read_receipt_digest(lines: list[str]) -> str:
    receipt = "\n".join(lines[1:-1]).strip()
    return "sha256:" + hashlib.sha256(receipt.encode("utf-8")).hexdigest()


def _read_provenance_row(read_id: str, digest: str) -> str:
    return _table_line(
        (
            "Read-only preflight",
            read_id,
            "AUTH-0001",
            "fastlane-read-role",
            "sha256:" + "a" * 64,
            "NOT_APPLICABLE - read-only preflight creates no plan",
            "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
            "RESOURCES: fastlane-stack; OPERATIONS: cloudformation:DescribeStacks",
            "COST: expected low-volume under USD 0.01; BOUNDED_BY: USD: 20.00; "
            "VALID_UNTIL: 2099-01-01T00:00:00Z",
            "NOT_APPLICABLE - no mutation",
            "owner-message MSG-AWS-READ-9001",
            "owner-handle",
            "2026-07-29T00:02:00Z",
            digest,
            "NONE",
            "PASS",
            "AUTHORIZED",
        )
    )


def _reconciliation_row(
    read_id: str,
    digest: str,
    *,
    status: str = "COMPLETE",
    evidence_id: str = "EV-9001",
) -> str:
    return _table_line(
        (
            evidence_id,
            "AWS-DEPLOY-0001",
            "AWS-30",
            "REQ-0001 / DES-0001 / AUTH-0001",
            "AWS-AUTH-0001",
            "sha256:" + "1" * 64,
            "2099-01-01T00:00:00Z",
            "owner-message MSG-AWS-0001",
            read_id,
            "fastlane-deployment-role",
            "fastlane-read-role",
            digest,
            "2099-01-01T00:00:00Z",
            "SOURCE: owner-message MSG-AWS-READ-9001; "
            "AUTHORIZED_AT: 2026-07-29T00:02:00Z; "
            "RESOURCES: fastlane-stack; "
            "OPERATIONS: cloudformation:DescribeStacks",
            "sha256:" + "a" * 64,
            "TYPE: CLOUDFORMATION_CHANGE_SET; IDENTIFIER: change-set-1; DIGEST: sha256:"
            + "b" * 64,
            "fastlane-stack",
            "cloudformation:ExecuteChangeSet",
            "cloudformation:DescribeStacks",
            "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
            "OPERATION_IDS: change-set-1; DIRECT_RESULT: UPDATE_COMPLETE",
            "NONE",
            "EV-0001",
            "2026-07-29T00:03:00Z",
            "AWS read-only reconciliation",
            "PASS",
            "NONE",
            status,
        )
    )


def closure_patch_input(
    path: str,
    operation: str,
    *,
    verify_text: str | None = None,
    add_unrelated_hunk: bool = False,
    extra_same_section: bool = False,
    delete_journal_row: bool = False,
    edit_other_receipt: str | None = None,
    aws20_status: str = "UNKNOWN",
    wrong_phase: bool = False,
    mismatch_read_id: bool = False,
    mismatch_evidence_id: bool = False,
    release_state: str = "RELEASE_VERIFIED",
    extra_release_change: bool = False,
) -> dict[str, str]:
    stock = verify_text or (REPOSITORY_ROOT / doctor.VERIFY_FILE).read_text(
        encoding="utf-8"
    )
    journal_row = _section_rows(
        stock, "## AWS deployment action and reconciliation evidence"
    )[0]
    hunks: list[str]
    if operation == "APPEND_ACTION_TERMINAL_ROW":
        phase = "AWS-30" if wrong_phase else "AWS-20"
        evidence_id = "EV-9999" if mismatch_evidence_id else "EV-9001"
        new_row = _action_unknown_row(aws20_status, phase, evidence_id)
        hunks = ["@@"]
        hunks.append(("-" if delete_journal_row else " ") + journal_row)
        hunks.append("+" + new_row)
    elif operation == "APPEND_RECONCILIATION_ROW":
        read_id = "AWS-READ-AUTH-9001"
        new_receipt = _read_receipt_lines(read_id)
        old_receipt = _marked_block_lines(stock, "aws-read-preflight-receipt")
        if len(old_receipt) != len(new_receipt):
            raise AssertionError("read receipt fixture shape drifted")
        receipt_entries = ["@@"]
        for old_line, new_line in zip(old_receipt, new_receipt):
            if old_line == new_line:
                receipt_entries.append(" " + old_line)
            else:
                receipt_entries.extend(("-" + old_line, "+" + new_line))
        digest = _read_receipt_digest(new_receipt)
        old_provenance = next(
            row
            for row in _section_rows(stock, "## Action authorization provenance")
            if row.startswith("| Read-only preflight |")
        )
        new_provenance = _read_provenance_row(read_id, digest)
        journal_read_id = "AWS-READ-AUTH-9999" if mismatch_read_id else read_id
        evidence_id = "EV-9999" if mismatch_evidence_id else "EV-9001"
        new_journal = _reconciliation_row(
            journal_read_id, digest, evidence_id=evidence_id
        )
        hunks = receipt_entries + [
            "@@",
            "-" + old_provenance,
            "+" + new_provenance,
            "@@",
            ("-" if delete_journal_row else " ") + journal_row,
            "+" + new_journal,
        ]
    elif operation == "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF":
        old_state = next(
            line for line in stock.splitlines() if line.startswith("- Release state: ")
        )
        old_cutoff = next(
            line
            for line in stock.splitlines()
            if line.startswith("- Active evidence cutoff: ")
        )
        evidence_id = "EV-9999" if mismatch_evidence_id else "EV-9001"
        hunks = [
            "@@",
            "-" + old_state,
            f"+- Release state: `{release_state}`",
            " - AWS lifecycle intent: `NONE`",
            " - AWS lifecycle intent source: `NONE`",
            " - AWS lifecycle intent recorded at: `NONE`",
            "-" + old_cutoff,
            f"+- Active evidence cutoff: {evidence_id}",
            " - Blocking or stale evidence IDs: TODO",
        ]
        if extra_release_change:
            hunks.extend(
                [
                    "@@",
                    "-- Pending AWS evidence IDs: TODO / `NONE`",
                    "+- Pending AWS evidence IDs: `NONE`",
                    " - Accepted risks: `NONE`",
                ]
            )
    else:
        raise ValueError(f"unknown closure operation: {operation}")
    if extra_same_section:
        hunks.append("+unauthorized same-section closure text")
    if edit_other_receipt is not None:
        block = _marked_block_lines(stock, edit_other_receipt)
        field_index = next(index for index, line in enumerate(block) if ": " in line)
        old_line = block[field_index]
        name = old_line.split(": ", 1)[0]
        hunks.extend(["@@", "-" + old_line, f"+{name}: unauthorized-edit"])
    if add_unrelated_hunk:
        lines = stock.splitlines()
        anchor = next(
            line
            for line in lines
            if line.startswith("This ledger proves current runtime")
        )
        following = lines[lines.index(anchor) + 1]
        hunks.extend(
            [
                "@@",
                " " + anchor,
                "-" + following,
                "+unrelated mutation",
            ]
        )
    body = "\n".join(hunks)
    return {
        "command": (f"*** Begin Patch\n*** Update File: {path}\n{body}\n*** End Patch")
    }


def lifecycle_intent_capability(*, residual_choice: bool = False) -> dict[str, object]:
    return {
        "valid": True,
        "kind": "AWS_LIFECYCLE_INTENT_RECORD",
        "authorization_id": "AWS_LIFECYCLE_INTENT_RECORD",
        "mode": "BOUNDED_RELEASE_INTENT_RECORD",
        "allowed_write_paths": ["docs/project/VERIFY.md"],
        "allowed_sections": ["## Current release decision"],
        "allowed_operations": ["UPDATE_AWS_LIFECYCLE_INTENT"],
        "allowed_values": (
            ["RETAIN", "RESIDUAL_REVIEW", "TEARDOWN"]
            if residual_choice
            else ["NONE", "RESIDUAL_REVIEW", "TEARDOWN"]
        ),
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }


def lifecycle_intent_record(
    value: str = "NONE",
    *,
    source: str = "NONE",
    recorded_at: str = "NONE",
    provenance_status: str = "CURRENT",
) -> dict[str, object]:
    return {
        "value": value,
        "source": source,
        "recorded_at": recorded_at,
        "provenance_status": provenance_status,
        "authorizes_aws_access": False,
        "authorizes_mutation": False,
    }


def lifecycle_intent_patch_input(
    path: str = "docs/project/VERIFY.md",
    *,
    value: str = "RESIDUAL_REVIEW",
    source: str = "owner-message MSG-AWS-LIFECYCLE-0001",
    recorded_at: str = "2026-07-29T12:00:00+00:00",
    legacy_none: bool = False,
    partial: bool = False,
    extra_same_section: bool = False,
    current_value: str = "NONE",
    current_source: str = "NONE",
    current_recorded_at: str = "NONE",
) -> dict[str, str]:
    deleted = [f"- AWS lifecycle intent: `{current_value}`"]
    if not legacy_none:
        deleted.extend(
            (
                f"- AWS lifecycle intent source: `{current_source}`",
                (f"- AWS lifecycle intent recorded at: `{current_recorded_at}`"),
            )
        )
    added = [
        f"- AWS lifecycle intent: `{value}`",
        f"- AWS lifecycle intent source: `{source}`",
        f"- AWS lifecycle intent recorded at: `{recorded_at}`",
    ]
    if partial:
        added.pop()
    entries = ["@@"]
    entries.extend("-" + line for line in deleted)
    entries.extend("+" + line for line in added)
    if extra_same_section:
        entries.append("+unauthorized lifecycle-intent text")
    return {
        "command": (
            f"*** Begin Patch\n*** Update File: {path}\n"
            + "\n".join(entries)
            + "\n*** End Patch"
        )
    }


def lifecycle_intent_report(
    *,
    record: dict[str, object] | None = None,
    capability: dict[str, object] | None = None,
    write_authority: dict[str, object] | None = None,
) -> dict[str, object]:
    current = report(write_authority=write_authority)
    current["aws_lifecycle_intent"] = record or lifecycle_intent_record()
    current["aws_lifecycle_intent_write_authority"] = (
        capability or lifecycle_intent_capability()
    )
    return current


def closure_authority(sections: list[str], operations: list[str]) -> dict[str, object]:
    return {
        "valid": True,
        "kind": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
        "authorization_id": "AWS_DEPLOYMENT_JOURNAL_CLOSURE",
        "mode": "BOUNDED_EVIDENCE_CLOSURE",
        "allowed_write_paths": ["docs/project/VERIFY.md"],
        "allowed_sections": sections,
        "allowed_operations": operations,
        "allowed_release_states": (
            ["NOT_READY", "RELEASE_VERIFIED"]
            if operations == ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"]
            else []
        ),
        "attempt_id": "AWS-DEPLOY-0001",
        "evidence_id": "EV-9001",
        "construction_authorization": "NONE",
        "aws_mutation_authority": "NONE",
    }


def reviewed_authority(
    script: str | None = None,
    *,
    artifact_bytes: bytes | None = None,
    kind: str = "AWS_DEPLOYMENT",
    operation: str = "cloudformation:CreateStack",
) -> dict[str, object]:
    if (script is None) == (artifact_bytes is None):
        raise ValueError("provide exactly one reviewed script or artifact")
    raw = authority(kind, [operation], authorization_id="AWS-AUTH-0001")
    content = script.encode("utf-8") if script is not None else artifact_bytes
    if content is None:
        raise AssertionError("reviewed content is absent")
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    script_digest = digest if script is not None else "NONE"
    artifact_digest = digest if artifact_bytes is not None else "NONE"
    stock = (REPOSITORY_ROOT / doctor.VERIFY_FILE).read_text(encoding="utf-8")
    marker = "| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | `NOT_STARTED` |"
    row = (
        "| AWS-EXEC-0001 | "
        f"{kind} | AWS-AUTH-0001 | NONE | {script_digest} | {artifact_digest} | {operation} | "
        "fastlane-stack | 111122223333 | us-west-2 | development | fastlane-role | "
        f"sha256:{'a' * 64} | change-set-1 | USD: 25.00 | restore the previous stack | "
        "2099-01-01T00:00:00+00:00 | EV-0001 | CURRENT |"
    )
    if marker not in stock:
        raise AssertionError("stock reviewed-execution placeholder row is missing")
    return normalized_authority(raw, verify_text=stock.replace(marker, row, 1))


class FastlaneHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = REPOSITORY_ROOT

    def test_example_is_opt_in_complete_and_cross_platform(self) -> None:
        self.assertFalse((self.root / ".codex" / "hooks.json").exists())
        data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            set(data["hooks"]),
            {"SessionStart", "PreToolUse", "PermissionRequest", "PostToolUse", "Stop"},
        )
        for groups in data["hooks"].values():
            for group in groups:
                for hook in group["hooks"]:
                    for field in ("command", "commandWindows"):
                        self.assertEqual(hook[field], "")
        self.assertIn("post-Gate-B", data["description"])
        self.assertIn("stale gates fail closed", data["description"])
        for event in ("PreToolUse", "PermissionRequest", "PostToolUse"):
            matcher = data["hooks"][event][0]["matcher"]
            self.assertIn("use_aws", matcher)
            self.assertIn("aws___.*", matcher)
            self.assertIn("mcp__.*", matcher)
            self.assertNotIn("call_aws", matcher)
            self.assertNotIn("run_script", matcher)
        hooks_guide = (self.root / "docs" / "HOOKS.md").read_text(encoding="utf-8")
        self.assertIn("Enable this pack only after a current Gate B", hooks_guide)
        self.assertIn("`BOOT-00`, `INTAKE-10`, `REQ-10`, or `DESIGN-10`", hooks_guide)
        self.assertIn("If Gate B later becomes stale or invalid", hooks_guide)
        self.assertIn("then regenerate the pack", hooks_guide)

    def test_valid_and_malformed_event_payloads(self) -> None:
        parsed = fastlane_hook.read_event(
            io.StringIO(json.dumps(payload("Stop", self.root, stop_hook_active=True)))
        )
        self.assertEqual(parsed["hook_event_name"], "Stop")
        with self.assertRaises(fastlane_hook.HookInputError):
            fastlane_hook.read_event(io.StringIO("not-json"))
        with self.assertRaises(fastlane_hook.HookInputError):
            fastlane_hook.handle_event(
                "stop",
                payload("PreToolUse", self.root),
                root=self.root,
                doctor_report=report(),
            )

    def test_session_start_adds_short_read_only_state_context(self) -> None:
        result = fastlane_hook.handle_event(
            "session-start",
            payload("SessionStart", self.root),
            root=self.root,
            doctor_report=report(),
        )
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("stage=DEFINE", context)
        self.assertIn("Hooks are defense in depth", context)
        self.assertLessEqual(len(context), fastlane_hook.MAX_CONTEXT_CHARS)
        self.assertNotIn("sha256", context.casefold())

    def test_additive_owner_projections_do_not_change_hook_routing(self) -> None:
        baseline = report()
        enriched = json.loads(json.dumps(baseline))
        enriched["schema_version"] = 2
        enriched["owner_decision_brief"] = {
            "schema_version": 1,
            "kind": "NONE",
            "status": "NONE",
        }
        enriched["owner_answer_confirmation"] = {
            "schema_version": 1,
            "status": "NONE",
        }
        event = payload("SessionStart", self.root)

        self.assertEqual(
            fastlane_hook.handle_event(
                "session-start", event, root=self.root, doctor_report=enriched
            ),
            fastlane_hook.handle_event(
                "session-start", event, root=self.root, doctor_report=baseline
            ),
        )
    def test_unconfigured_template_session_start_routes_to_prerequisites(self) -> None:
        observed = fastlane_hook.run_doctor(self.root)
        self.assertEqual(observed["classification"], "UNCONFIGURED_TEMPLATE")
        self.assertEqual(observed["interaction"]["owner_stage"], "DEFINE")
        self.assertEqual(
            observed["interaction"]["owner_action_kind"],
            "COMPLETE_PREREQUISITE_CHECKLIST",
        )
        result = fastlane_hook.handle_event(
            "session-start",
            payload("SessionStart", self.root),
            root=self.root,
            doctor_report=observed,
        )
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("template is not initialized", context)
        self.assertIn("prerequisite checklist", context)
        self.assertNotIn("stage=DELIVER", context)

    def test_documentation_only_aws_tools_remain_allowed(self) -> None:
        for tool_name in (
            "aws___retrieve_skill",
            "aws___search_documentation",
            "aws___read_documentation",
            "mcp__aws-core__retrieve_skill",
            "mcp__aws-core__search_documentation",
            "mcp__codex_apps__aws_documentation_aws___get_regi_f8690b05bd48",
        ):
            result = fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    self.root,
                    tool_name=tool_name,
                    tool_input={"query": "Lambda security guidance"},
                ),
                root=self.root,
                doctor_report=report(),
                envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
            )
            self.assertIsNone(result)

        deceptive = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="aws___recommend_delete_stack",
                tool_input={},
            ),
            root=self.root,
            doctor_report=report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "external authority is absent",
            deceptive["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_account_tools_are_classified_by_capability_not_product_name(self) -> None:
        external = authority("FAST_DEV_GATE_B", ["cloudformation:CreateStack"])
        for tool_name in (
            "aws___invoke_operation",
            "mcp__aws-core__invoke_operation",
            "aws___call_aws",
        ):
            with self.subTest(tool_name=tool_name):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name=tool_name,
                        tool_input=aws_request("CreateStack"),
                    ),
                    root=self.root,
                    doctor_report=report(aws="AUTH-0001", external_authority=external),
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIn(
                    "STARTED journal row",
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

        unrelated = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="mcp__calendar__invoke_operation",
                tool_input=aws_request("CreateStack"),
            ),
            root=self.root,
            doctor_report=report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIsNone(unrelated)

    def test_presigned_urls_require_exact_direction_resource_and_expiration(
        self,
    ) -> None:
        resource = "arn:aws:s3:::fastlane-bucket/releases/app.zip"
        download = authority(
            "AWS_READ_ONLY",
            ["s3:GetObject"],
            resources=[resource],
        )
        request = {
            "bucket": "fastlane-bucket",
            "key": "releases/app.zip",
            "direction": "download",
            "expires_in": 300,
            "region": "us-west-2",
            "aws_profile": "fastlane-role",
        }
        self.assertIsNone(
            fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    self.root,
                    tool_name="aws___get_presigned_url",
                    tool_input=request,
                ),
                root=self.root,
                doctor_report=report(aws="AUTH-0001", external_authority=download),
                envelope={
                    "AWS boundary": "READ_ONLY",
                    "GitHub boundary": "NONE",
                },
            )
        )

        mismatches = (
            ({**request, "direction": "upload"}, "mutation authority"),
            ({**request, "key": "releases/other.zip"}, "resource target"),
            (
                {key: value for key, value in request.items() if key != "expires_in"},
                "positive expiration",
            ),
            ({**request, "expires_in": 10**12}, "expiration exceeds"),
        )
        for tool_input, reason in mismatches:
            with self.subTest(reason=reason):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="mcp__aws-core__get_presigned_url",
                        tool_input=tool_input,
                    ),
                    root=self.root,
                    doctor_report=report(aws="AUTH-0001", external_authority=download),
                    envelope={
                        "AWS boundary": "READ_ONLY",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIn(
                    reason,
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

    def test_task_polling_requires_a_doctor_derived_task_binding(self) -> None:
        current = authority(
            "AWS_DEPLOYMENT",
            ["cloudformation:CreateStack"],
            authorization_id="AWS-AUTH-0001",
        )
        for tool_input, reason in (
            ({"aws_profile": "fastlane-role"}, "exact task identifier"),
            (
                {"task_id": "task-123", "aws_profile": "fastlane-role"},
                "not bound by the current Fastlane Engine authority",
            ),
        ):
            with self.subTest(reason=reason):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="aws___get_tasks",
                        tool_input=tool_input,
                    ),
                    root=self.root,
                    doctor_report=report(
                        aws="AWS-AUTH-0001", external_authority=current
                    ),
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIn(
                    reason,
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

    def test_product_execution_guidance_is_tool_name_independent(self) -> None:
        documents = (
            REPOSITORY_ROOT / "docs" / "HOOKS.md",
            REPOSITORY_ROOT / "docs" / "project" / "RUNBOOK.md",
            REPOSITORY_ROOT / "docs" / "project" / "VERIFY.md",
            REPOSITORY_ROOT / "prompts" / "CODEX-PROMPTS.md",
        )
        for path in documents:
            with self.subTest(path=path):
                content = path.read_text(encoding="utf-8")
                self.assertNotIn("call_aws", content)
                self.assertNotIn("run_script", content)
                self.assertIn("STRUCTURED_API", content)
                self.assertIn("REVIEWED_SCRIPT", content)
        self.assertIn(
            "AWS Core selects a currently supported account-operation tool",
            (REPOSITORY_ROOT / "docs" / "project" / "RUNBOOK.md").read_text(
                encoding="utf-8"
            ),
        )

    def test_read_only_gh_api_is_not_misclassified_as_publication(self) -> None:
        read_result = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="Bash",
                tool_input={"command": "gh api repos/example/project"},
            ),
            root=self.root,
            doctor_report=report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIsNone(read_result)

        write_result = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="Bash",
                tool_input={
                    "command": "gh api --method POST repos/example/project/issues"
                },
            ),
            root=self.root,
            doctor_report=report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "GitHub publication",
            write_result["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_unauthorized_aws_and_github_mutations_are_denied(self) -> None:
        cases = (
            (
                "aws___call_aws",
                aws_request("CreateStack"),
                "external authority is absent",
            ),
            (
                "use_aws",
                aws_request("CreateStack"),
                "external authority is absent",
            ),
            ("Bash", {"command": "terraform destroy"}, "external authority is absent"),
            (
                "mcp__github__merge_pull_request",
                {"number": 1},
                "GitHub publication",
            ),
            ("Bash", {"command": "git push origin main"}, "GitHub publication"),
        )
        for tool_name, tool_input, expected in cases:
            with self.subTest(tool_name=tool_name, tool_input=tool_input):
                result = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name=tool_name,
                        tool_input=tool_input,
                    ),
                    root=self.root,
                    doctor_report=report(),
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                decision = result["hookSpecificOutput"]
                self.assertEqual(decision["permissionDecision"], "deny")
                self.assertIn(expected, decision["permissionDecisionReason"])

    def test_out_of_repository_write_is_denied(self) -> None:
        outside = self.root.parent / "not-fastlane.txt"
        result = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="apply_patch",
                tool_input=patch_input(str(outside)),
            ),
            root=self.root,
            doctor_report=report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "outside the current repository",
            result["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_authorized_requests_keep_normal_owner_approval(self) -> None:
        result = fastlane_hook.handle_event(
            "permission-request",
            payload(
                "PermissionRequest",
                self.root,
                tool_name="mcp__codex_apps__github_create_pull_request",
                tool_input={
                    "repository_full_name": "example/project",
                    "base_branch": "fast-lane",
                    "head_branch": "feature/safe-change",
                    "title": "Reviewed change",
                },
            ),
            root=self.root,
            doctor_report=report(construction="AUTH-0001"),
            envelope=github_envelope(),
        )
        self.assertIsNone(result)

    def test_current_github_connector_mutations_use_external_not_local_scope(
        self,
    ) -> None:
        allowed = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="mcp__codex_apps__github_create_file",
                tool_input={
                    "repository_full_name": "example/project",
                    "branch": "fast-lane",
                    "path": "docs/review.md",
                    "content": "reviewed",
                    "message": "docs: reviewed",
                },
            ),
            root=self.root,
            doctor_report=report(construction="AUTH-0001"),
            envelope=github_envelope(),
        )
        self.assertIsNone(allowed)

        cases = (
            (
                {"repository_full_name": "other/project", "branch": "fast-lane"},
                "repository",
            ),
            ({"repository_full_name": "example/project", "branch": "other"}, "branch"),
            (
                {"repository_full_name": "example/project", "branch": None},
                "branch is not observable",
            ),
        )
        for override, expected in cases:
            tool_input = {
                "repository_full_name": "example/project",
                "branch": "fast-lane",
                "path": "docs/review.md",
                "content": "reviewed",
                "message": "docs: reviewed",
            }
            tool_input.update(override)
            with self.subTest(tool_input=tool_input):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="mcp__codex_apps__github_create_file",
                        tool_input=tool_input,
                    ),
                    root=self.root,
                    doctor_report=report(construction="AUTH-0001"),
                    envelope=github_envelope(),
                )
                reason = denied["hookSpecificOutput"]["permissionDecisionReason"]
                self.assertIn(expected, reason)
                self.assertNotIn("file mutation", reason)

    def test_github_connector_enforces_repo_and_merge_constraint(
        self,
    ) -> None:
        cases = (
            (
                "mcp__codex_apps__github_create_issue",
                {"repository_full_name": "example/project", "title": "Issue"},
                github_envelope("ISSUES"),
                None,
            ),
            (
                "mcp__codex_apps__github_create_issue",
                {"repository_full_name": "other/project", "title": "Issue"},
                github_envelope("ISSUES"),
                "repository",
            ),
            (
                "mcp__codex_apps__github_merge_pull_request",
                {"repo_full_name": "example/project", "pr_number": 51},
                github_envelope("MERGE_WHEN_GREEN"),
                "prohibit",
            ),
            (
                "mcp__codex_apps__github_merge_pull_request",
                {
                    "repo_full_name": "example/project",
                    "pr_number": 51,
                    "base_branch": "fast-lane",
                },
                github_envelope("MERGE_WHEN_GREEN", merge="ALLOWED"),
                "target branch is not observable",
            ),
        )
        for tool_name, tool_input, envelope, expected in cases:
            with self.subTest(tool_name=tool_name, tool_input=tool_input):
                result = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name=tool_name,
                        tool_input=tool_input,
                    ),
                    root=self.root,
                    doctor_report=report(construction="AUTH-0001"),
                    envelope=envelope,
                )
                if expected is None:
                    self.assertIsNone(result)
                else:
                    self.assertIn(
                        expected,
                        result["hookSpecificOutput"]["permissionDecisionReason"],
                    )

    def test_github_branch_scope_denies_unbound_structured_and_shell_mutations(
        self,
    ) -> None:
        structured = (
            (
                "mcp__codex_apps__github_create_pull_request",
                {
                    "repository_full_name": "example/project",
                    "base_branch": "Legacy",
                    "head_branch": "feature/change",
                    "title": "Wrong target",
                },
                "branch",
            ),
            (
                "mcp__codex_apps__github_update_pull_request",
                {
                    "repository_full_name": "example/project",
                    "pr_number": 51,
                    "base_branch": "Legacy",
                },
                "branch",
            ),
            (
                "mcp__codex_apps__github_merge_pull_request",
                {"repository_full_name": "example/project", "pr_number": 51},
                "branch is not observable",
            ),
            (
                "mcp__codex_apps__github_merge_pull_request",
                {
                    "repository_full_name": "example/project",
                    "pr_number": 51,
                    "base_branch": "fast-lane",
                    "expected_head_sha": "a" * 40,
                },
                "target branch is not observable",
            ),
            (
                "mcp__codex_apps__github_enable_auto_merge",
                {"repository_full_name": "example/project", "pr_number": 51},
                "target branch is not observable",
            ),
            (
                "mcp__github__update_release",
                {
                    "repository_full_name": "example/project",
                    "release_id": 99,
                    "target_commitish": "fast-lane",
                },
                "target branch is not observable",
            ),
            (
                "mcp__github__upload_release",
                {
                    "repository_full_name": "example/project",
                    "release_id": 99,
                    "file": "release.zip",
                },
                "target branch is not observable",
            ),
        )
        for tool_name, tool_input, expected in structured:
            with self.subTest(tool_name=tool_name, tool_input=tool_input):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name=tool_name,
                        tool_input=tool_input,
                    ),
                    root=self.root,
                    doctor_report=report(construction="AUTH-0001"),
                    envelope=github_envelope("MERGE_WHEN_GREEN", merge="ALLOWED"),
                )
                self.assertIn(
                    expected,
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

        metadata_update = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="mcp__codex_apps__github_update_pull_request",
                tool_input={
                    "repository_full_name": "example/project",
                    "pr_number": 51,
                    "title": "Clarify title only",
                },
            ),
            root=self.root,
            doctor_report=report(construction="AUTH-0001"),
            envelope=github_envelope(),
        )
        self.assertIsNone(metadata_update)

        conflicting_branch = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="mcp__codex_apps__github_create_file",
                tool_input={
                    "repository_full_name": "example/project",
                    "branch": "fast-lane",
                    "ref": "Legacy",
                    "path": "README.md",
                    "content": "change",
                },
            ),
            root=self.root,
            doctor_report=report(construction="AUTH-0001"),
            envelope=github_envelope(),
        )
        self.assertIn(
            "branch is not observable",
            conflicting_branch["hookSpecificOutput"]["permissionDecisionReason"],
        )

        shell_commands = (
            "git push origin Legacy",
            "command git push origin fast-lane",
            "env FASTLANE=1 git.exe push origin fast-lane",
            "gh pr merge 51 --repo other/project",
            "gh.exe pr create --repo example/project --base fast-lane",
        )
        for command in shell_commands:
            with self.subTest(command=command):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="Bash",
                        tool_input={"command": command},
                    ),
                    root=self.root,
                    doctor_report=report(construction="AUTH-0001"),
                    envelope=github_envelope("MERGE_WHEN_GREEN", merge="ALLOWED"),
                )
                self.assertIn(
                    "exact repository and branch are not observable",
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

    def test_every_github_mutation_has_one_target_binding_policy(self) -> None:
        mutations = (
            fastlane_hook.GITHUB_ISSUE_MUTATION_CAPABILITIES
            | fastlane_hook.GITHUB_BRANCH_PR_MUTATION_CAPABILITIES
            | fastlane_hook.GITHUB_MERGE_MUTATION_CAPABILITIES
        )
        policies = (
            fastlane_hook.GITHUB_REPOSITORY_ONLY_MUTATION_CAPABILITIES,
            fastlane_hook.GITHUB_BRANCH_REQUIRED_CAPABILITIES,
            fastlane_hook.GITHUB_BRANCH_IF_PRESENT_CAPABILITIES,
            fastlane_hook.GITHUB_UNOBSERVABLE_PROTECTED_CAPABILITIES,
        )
        observed: set[str] = set()
        for policy in policies:
            self.assertFalse(observed & policy)
            observed.update(policy)
        self.assertEqual(observed, set(mutations))

    def test_doctor_projected_hook_constraints_avoid_prd_reread(self) -> None:
        current = report(construction="AUTH-0001")
        current["hook_constraints"] = {
            "GitHub boundary": "ISSUES",
            "GitHub repository, branch, and merge constraints": (
                "REPO: example/project; BRANCH: fast-lane; MERGE: PROHIBITED"
            ),
        }
        with mock.patch.object(
            Path,
            "read_text",
            side_effect=AssertionError("hook must not reread project documents"),
        ):
            allowed = fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    self.root,
                    tool_name="mcp__codex_apps__github_create_issue",
                    tool_input={
                        "repository_full_name": "example/project",
                        "title": "Projected constraints",
                    },
                ),
                root=self.root,
                doctor_report=current,
            )
        self.assertIsNone(allowed)

    def test_github_connector_is_read_only_explicit_and_unknown_fails_closed(
        self,
    ) -> None:
        read_only = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="mcp__codex_apps__github_fetch_file",
                tool_input={
                    "repo_full_name": "example/project",
                    "path": "README.md",
                    "ref": "fast-lane",
                },
            ),
            root=self.root,
            doctor_report=report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIsNone(read_only)
        generated_alias = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name=(
                    "mcp__codex_apps__github_search_installed_reposito_be740b6e4965"
                ),
                tool_input={"query": "aws-bootstrap"},
            ),
            root=self.root,
            doctor_report=report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIsNone(generated_alias)

        unknown = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="mcp__codex_apps__github_future_mutation",
                tool_input={"repository_full_name": "example/project"},
            ),
            root=self.root,
            doctor_report=report(construction="AUTH-0001"),
            envelope=github_envelope(),
        )
        self.assertIn(
            "unrecognized GitHub connector capability",
            unknown["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_github_repository_url_rejects_credentials_query_and_fragment(self) -> None:
        unsafe_urls = (
            "https://token@" + "github.com/example/project",
            "https://github.com/example/project?token=secret",
            "https://github.com/example/project#private",
        )
        for repository_url in unsafe_urls:
            with self.subTest(repository_url=repository_url):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="mcp__github__create_issue",
                        tool_input={
                            "repository_url": repository_url,
                            "title": "Issue",
                        },
                    ),
                    root=self.root,
                    doctor_report=report(construction="AUTH-0001"),
                    envelope=github_envelope("ISSUES"),
                )
                self.assertIn(
                    "exact repository is not observable",
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

    def test_lf_and_crlf_command_boundaries_cannot_hide_mutations(self) -> None:
        cases = (
            (
                "Bash",
                "Write-Output safe\nRemove-Item -LiteralPath ..\\outside.txt",
                (
                    "outside the current repository"
                    if os.name == "nt"
                    else "ambiguous non-native path separator"
                ),
            ),
            (
                "Bash",
                "printf safe\r\ngit push origin fast-lane",
                "GitHub publication",
            ),
            (
                "Bash",
                "printf safe\naws cloudformation delete-stack --stack-name demo",
                "external authority is absent",
            ),
        )
        for tool_name, command, expected in cases:
            with self.subTest(command=command):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name=tool_name,
                        tool_input={"command": command},
                    ),
                    root=self.root,
                    doctor_report=report(),
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    expected,
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

    def test_write_authority_enforces_roots_exclusions_protection_and_active_task(
        self,
    ) -> None:
        authority = {
            "valid": True,
            "approved_write_roots": ["app/**"],
            "exclusions": ["app/owner-only/**"],
            "protected_paths": ["app/protected.txt"],
            "active_task": "TASK-0001",
            "active_task_write_set": ["app/service/**"],
        }
        allowed = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="apply_patch",
                tool_input=patch_input("app/service/handler.py"),
            ),
            root=self.root,
            doctor_report=report(construction="AUTH-0001", write_authority=authority),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIsNone(allowed)
        for path, reason in (
            ("docs/project/PRD.md", "Gate B write roots"),
            ("app/owner-only/secret.txt", "excluded write path"),
            ("app/protected.txt", "protected dirty path"),
            ("app/other/file.py", "active write set"),
        ):
            with self.subTest(path=path):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="apply_patch",
                        tool_input=patch_input(path),
                    ),
                    root=self.root,
                    doctor_report=report(
                        construction="AUTH-0001", write_authority=authority
                    ),
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    reason, denied["hookSpecificOutput"]["permissionDecisionReason"]
                )

    @unittest.skipIf(os.name == "nt", "Backslash is a native separator on Windows")
    def test_posix_literal_backslash_cannot_bypass_write_roots(self) -> None:
        authority = {
            "valid": True,
            "approved_write_roots": ["app/**"],
            "exclusions": [],
            "protected_paths": [],
            "active_task": "TASK-0001",
            "active_task_write_set": ["app/service/**"],
        }
        denied = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="write_file",
                tool_input={"path": r"app\service\handler.py"},
            ),
            root=self.root,
            doctor_report=report(construction="AUTH-0001", write_authority=authority),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "ambiguous non-native path separator",
            denied["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_lifecycle_intent_allows_only_exact_atomic_local_record(self) -> None:
        allowed = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="apply_patch",
                tool_input=lifecycle_intent_patch_input(),
            ),
            root=self.root,
            doctor_report=lifecycle_intent_report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIsNone(allowed)

        for changes, expected in (
            ({"partial": True}, "atomically write"),
            ({"extra_same_section": True}, "atomically write"),
            ({"source": "agent-generated"}, "atomically write"),
            ({"recorded_at": "2026-07-29T12:00:00"}, "atomically write"),
            ({"path": "docs/project/RUNBOOK.md"}, "only to docs/project/VERIFY.md"),
        ):
            with self.subTest(changes=changes):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="apply_patch",
                        tool_input=lifecycle_intent_patch_input(**changes),
                    ),
                    root=self.root,
                    doctor_report=lifecycle_intent_report(),
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    expected,
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

    def test_lifecycle_intent_profiles_bound_residual_retain(self) -> None:
        source = "owner-message MSG-AWS-LIFECYCLE-0002"
        recorded_at = "2026-07-29T13:00:00+00:00"
        retain_patch = lifecycle_intent_patch_input(
            value="RETAIN",
            source=source,
            recorded_at=recorded_at,
        )
        normal_denial = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="apply_patch",
                tool_input=retain_patch,
            ),
            root=self.root,
            doctor_report=lifecycle_intent_report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "atomically write",
            normal_denial["hookSpecificOutput"]["permissionDecisionReason"],
        )

        residual_allowed = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="apply_patch",
                tool_input=retain_patch,
            ),
            root=self.root,
            doctor_report=lifecycle_intent_report(
                capability=lifecycle_intent_capability(residual_choice=True)
            ),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIsNone(residual_allowed)

        none_denial = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="apply_patch",
                tool_input=lifecycle_intent_patch_input(
                    value="NONE",
                    source="NONE",
                    recorded_at="NONE",
                ),
            ),
            root=self.root,
            doctor_report=lifecycle_intent_report(
                capability=lifecycle_intent_capability(residual_choice=True)
            ),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "atomically write",
            none_denial["hookSpecificOutput"]["permissionDecisionReason"],
        )

        stock = (self.root / "docs/project/VERIFY.md").read_text(encoding="utf-8")
        retained = stock.replace(
            "- AWS lifecycle intent: `NONE`\n"
            "- AWS lifecycle intent source: `NONE`\n"
            "- AWS lifecycle intent recorded at: `NONE`\n",
            "- AWS lifecycle intent: `RETAIN`\n"
            f"- AWS lifecycle intent source: `{source}`\n"
            f"- AWS lifecycle intent recorded at: `{recorded_at}`\n",
            1,
        )
        self.assertNotEqual(retained, stock)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            verify_path = root / "docs" / "project" / "VERIFY.md"
            verify_path.parent.mkdir(parents=True)
            verify_path.write_text(retained, encoding="utf-8")
            reset = fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    root,
                    tool_name="apply_patch",
                    tool_input=lifecycle_intent_patch_input(
                        value="NONE",
                        source="NONE",
                        recorded_at="NONE",
                        current_value="RETAIN",
                        current_source=source,
                        current_recorded_at=recorded_at,
                    ),
                ),
                root=root,
                doctor_report=lifecycle_intent_report(
                    record=lifecycle_intent_record(
                        "RETAIN", source=source, recorded_at=recorded_at
                    )
                ),
                envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
            )
            self.assertIsNone(reset)

        for allowed_values in (
            ["NONE", "RETAIN", "RESIDUAL_REVIEW", "TEARDOWN"],
            ["RETAIN", "TEARDOWN", "RESIDUAL_REVIEW"],
            ["RETAIN", "RESIDUAL_REVIEW"],
            ["RETAIN", "RESIDUAL_REVIEW", "TEARDOWN", "TEARDOWN"],
        ):
            with self.subTest(allowed_values=allowed_values):
                capability = lifecycle_intent_capability(residual_choice=True)
                capability["allowed_values"] = allowed_values
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="apply_patch",
                        tool_input=retain_patch,
                    ),
                    root=self.root,
                    doctor_report=lifecycle_intent_report(capability=capability),
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    "absent or malformed",
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

    def test_lifecycle_intent_supports_one_legacy_none_migration(self) -> None:
        stock = (self.root / "docs/project/VERIFY.md").read_text(encoding="utf-8")
        legacy = stock.replace(
            "- AWS lifecycle intent: `NONE`\n"
            "- AWS lifecycle intent source: `NONE`\n"
            "- AWS lifecycle intent recorded at: `NONE`\n",
            "- AWS lifecycle intent: `NONE`\n",
            1,
        )
        self.assertNotEqual(legacy, stock)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            verify_path = root / "docs" / "project" / "VERIFY.md"
            verify_path.parent.mkdir(parents=True)
            verify_path.write_text(legacy, encoding="utf-8")
            current = lifecycle_intent_report(
                record=lifecycle_intent_record(provenance_status="LEGACY_NONE")
            )
            allowed = fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    root,
                    tool_name="apply_patch",
                    tool_input=lifecycle_intent_patch_input(legacy_none=True),
                ),
                root=root,
                doctor_report=current,
                envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
            )
            self.assertIsNone(allowed)

    def test_lifecycle_intent_can_cancel_before_current_aws_access(self) -> None:
        source = "owner-message MSG-AWS-LIFECYCLE-0001"
        recorded_at = "2026-07-29T12:00:00+00:00"
        stock = (self.root / "docs/project/VERIFY.md").read_text(encoding="utf-8")
        active_record = (
            "- AWS lifecycle intent: `TEARDOWN`\n"
            f"- AWS lifecycle intent source: `{source}`\n"
            f"- AWS lifecycle intent recorded at: `{recorded_at}`\n"
        )
        stock = stock.replace(
            "- AWS lifecycle intent: `NONE`\n"
            "- AWS lifecycle intent source: `NONE`\n"
            "- AWS lifecycle intent recorded at: `NONE`\n",
            active_record,
            1,
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            verify_path = root / "docs" / "project" / "VERIFY.md"
            verify_path.parent.mkdir(parents=True)
            verify_path.write_text(stock, encoding="utf-8")
            current = lifecycle_intent_report(
                record=lifecycle_intent_record(
                    "TEARDOWN", source=source, recorded_at=recorded_at
                )
            )
            allowed = fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    root,
                    tool_name="apply_patch",
                    tool_input=lifecycle_intent_patch_input(
                        value="NONE",
                        source="NONE",
                        recorded_at="NONE",
                        current_value="TEARDOWN",
                        current_source=source,
                        current_recorded_at=recorded_at,
                    ),
                ),
                root=root,
                doctor_report=current,
                envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
            )
            self.assertIsNone(allowed)

    def test_lifecycle_intent_capability_cannot_be_bypassed(self) -> None:
        broad = {
            "valid": True,
            "approved_write_roots": ["docs/**"],
            "exclusions": [],
            "protected_paths": [],
            "active_task": "NONE",
            "active_task_write_set": [],
        }
        malformed_capability = lifecycle_intent_capability()
        malformed_capability["allowed_operations"] = ["WRITE_ANYTHING"]
        cases = (
            (
                lifecycle_intent_report(capability=malformed_capability),
                "absent or malformed",
            ),
            (
                lifecycle_intent_report(write_authority=broad),
                None,
            ),
            (
                lifecycle_intent_report(
                    record={
                        **lifecycle_intent_record(),
                        "authorizes_aws_access": True,
                    }
                ),
                "absent or malformed",
            ),
            (
                {
                    **lifecycle_intent_report(),
                    "external_authority": {
                        "kind": "AWS_READ_ONLY",
                        "validity": "CURRENT",
                        "resources": ["fastlane-stack"],
                        "operations": ["cloudformation:DescribeStacks"],
                    },
                },
                "absent or malformed",
            ),
        )
        for current, expected in cases:
            with self.subTest(expected=expected):
                if expected is None:
                    current.pop("aws_lifecycle_intent_write_authority")
                    expected = "absent or malformed"
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="apply_patch",
                        tool_input=lifecycle_intent_patch_input(),
                    ),
                    root=self.root,
                    doctor_report=current,
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    expected,
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

        denied_whole_file = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="write_file",
                tool_input={
                    "file_path": "docs/project/VERIFY.md",
                    "content": (
                        "- AWS lifecycle intent: `RESIDUAL_REVIEW`\n"
                        "- AWS lifecycle intent source: "
                        "`owner-message MSG-AWS-LIFECYCLE-0001`\n"
                        "- AWS lifecycle intent recorded at: "
                        "`2026-07-29T12:00:00+00:00`"
                    ),
                },
            ),
            root=self.root,
            doctor_report=lifecycle_intent_report(),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "only an exact file patch",
            denied_whole_file["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_release_closure_context_does_not_become_intent_write(self) -> None:
        closure_report = report()
        closure_report["deployment_journal_closure_authority"] = closure_authority(
            ["## Current release decision"],
            ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
        )
        allowed = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="apply_patch",
                tool_input=closure_patch_input(
                    "docs/project/VERIFY.md",
                    "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF",
                ),
            ),
            root=self.root,
            doctor_report=closure_report,
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIsNone(allowed)

    def test_bounded_verify_closure_allows_only_exact_section_patches(self) -> None:
        contracts = (
            (
                "ACTION_TERMINAL_REQUIRED",
                "AWS-20",
                "APPEND_ACTION_TERMINAL_ROW",
            ),
            (
                "RECONCILIATION_REQUIRED",
                "AWS-30",
                "APPEND_RECONCILIATION_ROW",
            ),
            (
                "RECONCILED",
                "RELEASE-10",
                "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF",
            ),
        )
        for status, next_prompt, patch_operation in contracts:
            with self.subTest(status=status):
                closure = doctor.derive_deployment_journal_closure_authority(
                    {
                        "status": status,
                        "attempt_id": "AWS-DEPLOY-0001",
                        "evidence_id": "EV-9001",
                        "issues": [],
                    },
                    next_prompt,
                    restricted_closure=True,
                )
                self.assertTrue(closure["valid"], closure)
                closure_report = report()
                closure_report["deployment_journal_closure_authority"] = closure
                allowed = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="apply_patch",
                        tool_input=closure_patch_input(
                            "docs/project/VERIFY.md", patch_operation
                        ),
                    ),
                    root=self.root,
                    doctor_report=closure_report,
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIsNone(allowed)

                denied_path = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="apply_patch",
                        tool_input=closure_patch_input("app.py", patch_operation),
                    ),
                    root=self.root,
                    doctor_report=closure_report,
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    "only to docs/project/VERIFY.md",
                    denied_path["hookSpecificOutput"]["permissionDecisionReason"],
                )

                denied_section = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="apply_patch",
                        tool_input=closure_patch_input(
                            "docs/project/VERIFY.md",
                            patch_operation,
                            add_unrelated_hunk=True,
                        ),
                    ),
                    root=self.root,
                    doctor_report=closure_report,
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    "outside its exact authority",
                    denied_section["hookSpecificOutput"]["permissionDecisionReason"],
                )

        shell_report = report()
        shell_report["deployment_journal_closure_authority"] = closure_authority(
            ["## Current release decision"],
            ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
        )
        denied_shell = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="exec_command",
                tool_input={
                    "command": (
                        "Set-Content -Path docs/project/VERIFY.md "
                        "'- Active evidence cutoff: EV-9001'"
                    )
                },
            ),
            root=self.root,
            doctor_report=shell_report,
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "only an exact file patch",
            denied_shell["hookSpecificOutput"]["permissionDecisionReason"],
        )

        malformed_report = report()
        malformed = closure_authority(
            ["## Current release decision"],
            ["UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF"],
        )
        malformed["allowed_operations"] = [
            "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF",
            "WRITE_ANY",
        ]
        malformed_report["deployment_journal_closure_authority"] = malformed
        denied_malformed = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="apply_patch",
                tool_input=closure_patch_input(
                    "docs/project/VERIFY.md",
                    "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF",
                ),
            ),
            root=self.root,
            doctor_report=malformed_report,
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "closure authority is malformed",
            denied_malformed["hookSpecificOutput"]["permissionDecisionReason"],
        )

        action_report = report()
        action_report["deployment_journal_closure_authority"] = (
            doctor.derive_deployment_journal_closure_authority(
                {
                    "status": "ACTION_TERMINAL_REQUIRED",
                    "attempt_id": "AWS-DEPLOY-0001",
                    "evidence_id": "EV-9001",
                    "issues": [],
                },
                "AWS-20",
                restricted_closure=True,
            )
        )
        wrong_operation = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="apply_patch",
                tool_input=closure_patch_input(
                    "docs/project/VERIFY.md",
                    "APPEND_ACTION_TERMINAL_ROW",
                    wrong_phase=True,
                ),
            ),
            root=self.root,
            doctor_report=action_report,
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "exactly one AWS-20 UNKNOWN",
            wrong_operation["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_bounded_aws20_allows_only_one_unknown_append(self) -> None:
        closure_report = report()
        closure_report["deployment_journal_closure_authority"] = (
            doctor.derive_deployment_journal_closure_authority(
                {
                    "status": "ACTION_TERMINAL_REQUIRED",
                    "attempt_id": "AWS-DEPLOY-0001",
                    "evidence_id": "EV-9001",
                    "issues": [],
                },
                "AWS-20",
                restricted_closure=True,
            )
        )
        for forbidden in ("SUCCEEDED", "FAILED", "PARTIAL", "ROLLED_BACK"):
            with self.subTest(status=forbidden):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="apply_patch",
                        tool_input=closure_patch_input(
                            "docs/project/VERIFY.md",
                            "APPEND_ACTION_TERMINAL_ROW",
                            aws20_status=forbidden,
                        ),
                    ),
                    root=self.root,
                    doctor_report=closure_report,
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    "exactly one AWS-20 UNKNOWN",
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

        for flag in (
            "extra_same_section",
            "delete_journal_row",
            "mismatch_evidence_id",
        ):
            with self.subTest(flag=flag):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="apply_patch",
                        tool_input=closure_patch_input(
                            "docs/project/VERIFY.md",
                            "APPEND_ACTION_TERMINAL_ROW",
                            **{flag: True},
                        ),
                    ),
                    root=self.root,
                    doctor_report=closure_report,
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    "preserve all prior evidence",
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

        stock = (self.root / doctor.VERIFY_FILE).read_text(encoding="utf-8")
        placeholder = _section_rows(
            stock, "## AWS deployment action and reconciliation evidence"
        )[0]
        prior_started = _action_unknown_row("STARTED")
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            verify_path = temporary_root / doctor.VERIFY_FILE
            verify_path.parent.mkdir(parents=True)
            prior_text = stock.replace(placeholder, prior_started, 1)
            verify_path.write_text(prior_text, encoding="utf-8")
            denied = fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    temporary_root,
                    tool_name="apply_patch",
                    tool_input=closure_patch_input(
                        "docs/project/VERIFY.md",
                        "APPEND_ACTION_TERMINAL_ROW",
                        verify_text=prior_text,
                        delete_journal_row=True,
                    ),
                ),
                root=temporary_root,
                doctor_report=closure_report,
                envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
            )
        self.assertIn(
            "preserve all prior evidence",
            denied["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_bounded_aws30_binds_only_one_read_receipt_and_row(self) -> None:
        closure_report = report()
        closure_report["deployment_journal_closure_authority"] = (
            doctor.derive_deployment_journal_closure_authority(
                {
                    "status": "RECONCILIATION_REQUIRED",
                    "attempt_id": "AWS-DEPLOY-0001",
                    "evidence_id": "EV-9001",
                    "issues": [],
                },
                "AWS-30",
                restricted_closure=True,
            )
        )
        for kwargs, expected in (
            ({"mismatch_read_id": True}, "does not bind one exact AWS-30"),
            ({"mismatch_evidence_id": True}, "does not bind one exact AWS-30"),
            ({"extra_same_section": True}, "preserve prior evidence"),
            ({"delete_journal_row": True}, "preserve prior evidence"),
            (
                {"edit_other_receipt": "aws-deployment-receipt"},
                "outside its exact authority",
            ),
            (
                {"edit_other_receipt": "aws-teardown-receipt"},
                "outside its exact authority",
            ),
        ):
            with self.subTest(kwargs=kwargs):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="apply_patch",
                        tool_input=closure_patch_input(
                            "docs/project/VERIFY.md",
                            "APPEND_RECONCILIATION_ROW",
                            **kwargs,
                        ),
                    ),
                    root=self.root,
                    doctor_report=closure_report,
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    expected,
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

    def test_bounded_aws30_preserves_historical_provenance(self) -> None:
        closure_report = report()
        closure_report["deployment_journal_closure_authority"] = (
            doctor.derive_deployment_journal_closure_authority(
                {
                    "status": "RECONCILIATION_REQUIRED",
                    "attempt_id": "AWS-DEPLOY-0001",
                    "evidence_id": "EV-9001",
                    "issues": [],
                },
                "AWS-30",
                restricted_closure=True,
            )
        )
        stock = (self.root / doctor.VERIFY_FILE).read_text(encoding="utf-8")
        placeholder = next(
            row
            for row in _section_rows(stock, "## Action authorization provenance")
            if row.startswith("| Read-only preflight |")
        )
        prior_receipt = _read_receipt_lines("AWS-READ-AUTH-8001")
        prior_row = _read_provenance_row(
            "AWS-READ-AUTH-8001", _read_receipt_digest(prior_receipt)
        )
        prior_text = stock.replace(placeholder, prior_row, 1)
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            verify_path = temporary_root / doctor.VERIFY_FILE
            verify_path.parent.mkdir(parents=True)
            verify_path.write_text(prior_text, encoding="utf-8")
            denied = fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    temporary_root,
                    tool_name="apply_patch",
                    tool_input=closure_patch_input(
                        "docs/project/VERIFY.md",
                        "APPEND_RECONCILIATION_ROW",
                        verify_text=prior_text,
                    ),
                ),
                root=temporary_root,
                doctor_report=closure_report,
                envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
            )
        self.assertIn(
            "does not bind one exact AWS-30",
            denied["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_bounded_release_closure_binds_state_and_cutoff_together(self) -> None:
        cases = (
            ("RECONCILED", False, ["NOT_READY", "RELEASE_VERIFIED"]),
            ("RECONCILED", True, ["NOT_READY"]),
            ("BLOCKED", False, ["NOT_READY"]),
        )
        for status, basis_stale, expected_states in cases:
            with self.subTest(status=status, basis_stale=basis_stale):
                closure = doctor.derive_deployment_journal_closure_authority(
                    {
                        "status": status,
                        "attempt_id": "AWS-DEPLOY-0001",
                        "evidence_id": "EV-9001",
                        "basis_stale": basis_stale,
                        "issues": [],
                    },
                    "RELEASE-10",
                    restricted_closure=True,
                )
                self.assertEqual(closure["allowed_release_states"], expected_states)
                closure_report = report()
                closure_report["deployment_journal_closure_authority"] = closure
                for release_state in expected_states:
                    with self.subTest(release_state=release_state):
                        allowed = fastlane_hook.handle_event(
                            "pre-tool-use",
                            payload(
                                "PreToolUse",
                                self.root,
                                tool_name="apply_patch",
                                tool_input=closure_patch_input(
                                    "docs/project/VERIFY.md",
                                    "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF",
                                    release_state=release_state,
                                ),
                            ),
                            root=self.root,
                            doctor_report=closure_report,
                            envelope={
                                "AWS boundary": "NONE",
                                "GitHub boundary": "NONE",
                            },
                        )
                        self.assertIsNone(allowed)

                forbidden_states = {"READY_TO_DEPLOY", "RELEASE_VERIFIED"} - set(
                    expected_states
                )
                for release_state in forbidden_states:
                    denied = fastlane_hook.handle_event(
                        "pre-tool-use",
                        payload(
                            "PreToolUse",
                            self.root,
                            tool_name="apply_patch",
                            tool_input=closure_patch_input(
                                "docs/project/VERIFY.md",
                                "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF",
                                release_state=release_state,
                            ),
                        ),
                        root=self.root,
                        doctor_report=closure_report,
                        envelope={
                            "AWS boundary": "NONE",
                            "GitHub boundary": "NONE",
                        },
                    )
                    self.assertIn(
                        "permitted release state",
                        denied["hookSpecificOutput"]["permissionDecisionReason"],
                    )

                for kwargs in (
                    {"mismatch_evidence_id": True},
                    {"extra_release_change": True},
                    {"extra_same_section": True},
                ):
                    denied = fastlane_hook.handle_event(
                        "pre-tool-use",
                        payload(
                            "PreToolUse",
                            self.root,
                            tool_name="apply_patch",
                            tool_input=closure_patch_input(
                                "docs/project/VERIFY.md",
                                "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF",
                                release_state=expected_states[0],
                                **kwargs,
                            ),
                        ),
                        root=self.root,
                        doctor_report=closure_report,
                        envelope={
                            "AWS boundary": "NONE",
                            "GitHub boundary": "NONE",
                        },
                    )
                    self.assertIn(
                        "release state",
                        denied["hookSpecificOutput"]["permissionDecisionReason"],
                    )

        malformed_report = report()
        malformed = doctor.derive_deployment_journal_closure_authority(
            {
                "status": "RECONCILED",
                "attempt_id": "AWS-DEPLOY-0001",
                "evidence_id": "EV-9001",
                "issues": [],
            },
            "RELEASE-10",
            restricted_closure=True,
        )
        malformed["allowed_release_states"] = ["RELEASE_VERIFIED"]
        malformed_report["deployment_journal_closure_authority"] = malformed
        denied = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="apply_patch",
                tool_input=closure_patch_input(
                    "docs/project/VERIFY.md",
                    "UPDATE_RELEASE_DECISION_AND_EVIDENCE_CUTOFF",
                ),
            ),
            root=self.root,
            doctor_report=malformed_report,
            envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
        )
        self.assertIn(
            "closure authority is malformed",
            denied["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_bounded_closure_rejects_nested_and_mismatched_receipt_markers(
        self,
    ) -> None:
        closure_report = report()
        closure_report["deployment_journal_closure_authority"] = (
            doctor.derive_deployment_journal_closure_authority(
                {
                    "status": "ACTION_TERMINAL_REQUIRED",
                    "attempt_id": "AWS-DEPLOY-0001",
                    "evidence_id": "EV-9001",
                    "issues": [],
                },
                "AWS-20",
                restricted_closure=True,
            )
        )
        stock = (self.root / doctor.VERIFY_FILE).read_text(encoding="utf-8")
        read_start = "<!-- bootstrap:aws-read-preflight-receipt:start -->"
        read_end = "<!-- bootstrap:aws-read-preflight-receipt:end -->"
        variants = {
            "nested": stock.replace(
                read_start,
                read_start + "\n<!-- bootstrap:aws-deployment-receipt:start -->",
                1,
            ),
            "mismatched": stock.replace(
                read_end,
                "<!-- bootstrap:aws-teardown-receipt:end -->",
                1,
            ),
        }
        for name, verify_text in variants.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                temporary_root = Path(directory)
                verify_path = temporary_root / doctor.VERIFY_FILE
                verify_path.parent.mkdir(parents=True)
                verify_path.write_text(verify_text, encoding="utf-8")
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        temporary_root,
                        tool_name="apply_patch",
                        tool_input=closure_patch_input(
                            "docs/project/VERIFY.md",
                            "APPEND_ACTION_TERMINAL_ROW",
                            verify_text=verify_text,
                        ),
                    ),
                    root=temporary_root,
                    doctor_report=closure_report,
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(
                    "exact, unambiguous apply_patch hunk",
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

    def test_hook_requires_the_doctor_normalized_authority_projection(self) -> None:
        raw_report = report(
            aws="AUTH-0001",
            external_authority=authority(
                "FAST_DEV_GATE_B", ["cloudformation:CreateStack"]
            ),
        )
        raw_report["external_authority"].pop("request_match")
        denied = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="aws___call_aws",
                tool_input=aws_request("CreateStack"),
            ),
            root=self.root,
            doctor_report=raw_report,
            envelope={
                "AWS boundary": "MUTATE_LISTED_RESOURCES",
                "GitHub boundary": "NONE",
            },
        )
        self.assertIn(
            "normalized current external authority is absent",
            denied["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_aws_read_fast_dev_explicit_deployment_and_teardown_are_distinct(
        self,
    ) -> None:
        read = authority("AWS_READ_ONLY", ["cloudformation:DescribeStacks"])
        for tool_name in ("aws___call_aws", "mcp__aws-core__call_aws"):
            with self.subTest(tool_name=tool_name):
                self.assertIsNone(
                    fastlane_hook.handle_event(
                        "pre-tool-use",
                        payload(
                            "PreToolUse",
                            self.root,
                            tool_name=tool_name,
                            tool_input=aws_request("DescribeStacks"),
                        ),
                        root=self.root,
                        doctor_report=report(aws="AUTH-0001", external_authority=read),
                        envelope={
                            "AWS boundary": "READ_ONLY",
                            "GitHub boundary": "NONE",
                        },
                    )
                )

    def test_exact_read_preflight_receipt_is_required_and_cannot_mutate(self) -> None:
        active_artifact = "sha256:" + "a" * 64
        cost_posture = "MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00"
        envelope = {
            "AWS boundary": "READ_ONLY",
            "AWS role or profile": "ROLE: fastlane-role",
            "AWS account": "ACCOUNT: 111122223333",
            "AWS Region": "REGION: us-west-2",
            "AWS environment": "ENVIRONMENT: development; CLASS: NON_PRODUCTION",
            "AWS resource allowlist": "RESOURCES: fastlane-stack",
            "AWS allowed operations": "OPERATIONS: cloudformation:DescribeStacks",
            "AWS cost ceiling": "USD: 20.00",
            "AWS artifact authorization and provenance": (
                f"EXACT_DIGEST: {active_artifact}"
            ),
            "AWS authorization validity": "NOT_APPLICABLE — exact read receipt required",
            "Authorization expiry or completion condition": (
                "Expires at 2099-12-31T23:59:59Z; earlier completion: release review"
            ),
            "GitHub boundary": "NONE",
        }
        context = doctor.Context(REPOSITORY_ROOT)
        context.texts[doctor.VERIFY_FILE] = (
            REPOSITORY_ROOT / doctor.VERIFY_FILE
        ).read_text(encoding="utf-8")
        gate_b_only = doctor.derive_external_authority(
            context,
            envelope,
            "read-only",
            "AUTH-0001",
            cost_posture=cost_posture,
            active_artifact=active_artifact,
            aws_action_phase="AWS-10",
            aws_progress_state=None,
        )
        self.assertEqual(gate_b_only["kind"], "NONE")
        denied = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="aws___call_aws",
                tool_input=aws_request("DescribeStacks"),
            ),
            root=self.root,
            doctor_report=report(aws="AUTH-0001", external_authority=gate_b_only),
            envelope=envelope,
        )
        self.assertIn(
            "normalized current external authority is absent",
            denied["hookSpecificOutput"]["permissionDecisionReason"],
        )

        context.texts[doctor.VERIFY_FILE] = read_preflight_document()
        read_authority = doctor.derive_external_authority(
            context,
            envelope,
            "read-only",
            "AUTH-0001",
            cost_posture=cost_posture,
            active_artifact=active_artifact,
            aws_action_phase="AWS-10",
            aws_progress_state="AWS_PREFLIGHT_RUNNING",
        )
        self.assertEqual(read_authority["kind"], "AWS_READ_ONLY")
        current_report = report(aws="AUTH-0001", external_authority=read_authority)
        self.assertIsNone(
            fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    self.root,
                    tool_name="aws___call_aws",
                    tool_input=aws_request("DescribeStacks"),
                ),
                root=self.root,
                doctor_report=current_report,
                envelope=envelope,
            )
        )
        for operation in ("CreateStack", "DeleteStack"):
            with self.subTest(operation=operation):
                blocked = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="aws___call_aws",
                        tool_input=aws_request(operation),
                    ),
                    root=self.root,
                    doctor_report=current_report,
                    envelope=envelope,
                )
                self.assertEqual(
                    blocked["hookSpecificOutput"]["permissionDecision"], "deny"
                )

        invalid_documents = (
            read_preflight_document(
                receipt_artifact="sha256:" + "a" * 64,
                row_artifact="sha256:" + "b" * 64,
            ),
            read_preflight_document(valid_until="2000-01-01T00:00:00+00:00"),
        )
        for invalid_document in invalid_documents:
            with self.subTest(case="stale-or-mismatched"):
                context.texts[doctor.VERIFY_FILE] = invalid_document
                invalid = doctor.derive_external_authority(
                    context,
                    envelope,
                    "read-only",
                    "AUTH-0001",
                    cost_posture=cost_posture,
                    active_artifact=active_artifact,
                    aws_action_phase="AWS-10",
                    aws_progress_state="AWS_PREFLIGHT_RUNNING",
                )
                self.assertEqual(invalid["kind"], "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED")
                self.assertEqual(invalid["validity"], "REQUIRED")

        fast_dev = authority("FAST_DEV_GATE_B", ["cloudformation:CreateStack"])
        denied_fast_dev = fastlane_hook.handle_event(
            "permission-request",
            payload(
                "PermissionRequest",
                self.root,
                tool_name="aws___call_aws",
                tool_input=aws_request("CreateStack"),
            ),
            root=self.root,
            doctor_report=report(aws="AUTH-0001", external_authority=fast_dev),
            envelope={
                "AWS boundary": "MUTATE_LISTED_RESOURCES",
                "GitHub boundary": "NONE",
            },
        )
        self.assertIn(
            "STARTED journal row",
            denied_fast_dev["hookSpecificOutput"]["decision"]["message"],
        )

        mismatches = (
            (
                {**aws_request("CreateStack"), "operation_name": "Create"},
                "exact operation",
            ),
            (aws_request("CreateStack", "fastlane"), "resource target"),
            ({**aws_request("CreateStack"), "region": "us-east-1"}, "region"),
            ({**aws_request("CreateStack"), "aws_profile": "other-role"}, "profile"),
            (
                {**aws_request("CreateStack"), "artifact_digest": "sha256:wrong"},
                "artifact",
            ),
            ({**aws_request("CreateStack"), "plan_binding": "other-plan"}, "plan"),
        )
        for request, reason in mismatches:
            with self.subTest(reason=reason):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="aws___call_aws",
                        tool_input=request,
                    ),
                    root=self.root,
                    doctor_report=report(aws="AUTH-0001", external_authority=fast_dev),
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIn(
                    reason,
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

        deployment = authority(
            "AWS_DEPLOYMENT",
            ["cloudformation:UpdateStack"],
            authorization_id="AWS-AUTH-0001",
        )
        teardown = authority(
            "AWS_TEARDOWN",
            ["cloudformation:DeleteStack"],
            authorization_id="TEARDOWN-AUTH-0001",
        )
        denied_teardown = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="aws___call_aws",
                tool_input=aws_request("DeleteStack"),
            ),
            root=self.root,
            doctor_report=report(aws="AWS-AUTH-0001", external_authority=deployment),
            envelope={
                "AWS boundary": "MUTATE_LISTED_RESOURCES",
                "GitHub boundary": "NONE",
            },
        )
        self.assertIn(
            "distinct current teardown receipt",
            denied_teardown["hookSpecificOutput"]["permissionDecisionReason"],
        )
        denied_current_teardown = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="aws___call_aws",
                tool_input=aws_request("DeleteStack"),
            ),
            root=self.root,
            doctor_report=report(aws="TEARDOWN-AUTH-0001", external_authority=teardown),
            envelope={
                "AWS boundary": "MUTATE_LISTED_RESOURCES",
                "GitHub boundary": "NONE",
            },
        )
        self.assertIn(
            "STARTED journal row",
            denied_current_teardown["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_reviewed_scripts_require_exact_observable_content_and_authority(
        self,
    ) -> None:
        script = "print('reviewed Fastlane deployment')"
        deployment = reviewed_authority(script)
        match = deployment["request_match"]
        self.assertIn("REVIEWED_SCRIPT", match["allowed_execution_lanes"])
        self.assertIsNone(
            fastlane_hook.handle_event(
                "permission-request",
                payload(
                    "PermissionRequest",
                    self.root,
                    tool_name="aws___run_script",
                    tool_input={"script": script, "aws_profile": "fastlane-role"},
                ),
                root=self.root,
                doctor_report=report(
                    aws="AWS-AUTH-0001", external_authority=deployment
                ),
                envelope={
                    "AWS boundary": "MUTATE_LISTED_RESOURCES",
                    "GitHub boundary": "NONE",
                },
            )
        )
        for tool_name, tool_input in (
            ("aws___run_script", {"script": script + "\n# changed"}),
            ("mcp__aws-core__run_script", {"description": "deploy the stack"}),
            ("aws___run_script", {"script": script, "aws_profile": "other-role"}),
        ):
            with self.subTest(tool_name=tool_name, tool_input=tool_input):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name=tool_name,
                        tool_input=tool_input,
                    ),
                    root=self.root,
                    doctor_report=report(
                        aws="AWS-AUTH-0001", external_authority=deployment
                    ),
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                self.assertIn(
                    "blocked",
                    denied["hookSpecificOutput"]["permissionDecisionReason"],
                )

        teardown_script = "print('reviewed teardown')"
        wrong_kind = reviewed_authority(
            teardown_script,
            operation="cloudformation:DeleteStack",
        )
        denied = fastlane_hook.handle_event(
            "pre-tool-use",
            payload(
                "PreToolUse",
                self.root,
                tool_name="aws___run_script",
                tool_input={"script": teardown_script},
            ),
            root=self.root,
            doctor_report=report(aws="AWS-AUTH-0001", external_authority=wrong_kind),
            envelope={
                "AWS boundary": "MUTATE_LISTED_RESOURCES",
                "GitHub boundary": "NONE",
            },
        )
        self.assertIn(
            "distinct current teardown receipt",
            denied["hookSpecificOutput"]["permissionDecisionReason"],
        )
        teardown = reviewed_authority(
            teardown_script,
            kind="AWS_TEARDOWN",
            operation="cloudformation:DeleteStack",
        )
        self.assertIsNone(
            fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    self.root,
                    tool_name="aws___run_script",
                    tool_input={"script": teardown_script},
                ),
                root=self.root,
                doctor_report=report(aws="AWS-AUTH-0001", external_authority=teardown),
                envelope={
                    "AWS boundary": "MUTATE_LISTED_RESOURCES",
                    "GitHub boundary": "NONE",
                },
            )
        )

        artifact_bytes = b"print('immutable reviewed artifact')\n"
        artifact_authority = reviewed_authority(artifact_bytes=artifact_bytes)
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary).resolve()
            artifact = temporary_root / "reviewed.py"
            artifact.write_bytes(artifact_bytes)
            self.assertIsNone(
                fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        temporary_root,
                        tool_name="aws___run_script",
                        tool_input={
                            "script_path": "reviewed.py",
                            "aws_profile": "fastlane-role",
                        },
                    ),
                    root=temporary_root,
                    doctor_report=report(
                        aws="AWS-AUTH-0001",
                        external_authority=artifact_authority,
                    ),
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
            )

    def test_shell_wrappers_powershell_and_mixed_chains_fail_closed(self) -> None:
        external = authority("FAST_DEV_GATE_B", ["cloudformation:CreateStack"])
        commands = (
            "aws cloudformation create-stack --stack-name fastlane-stack; "
            "aws cloudformation delete-stack --stack-name fastlane-stack",
            'powershell -Command "aws cloudformation create-stack '
            "--stack-name fastlane-stack; aws cloudformation delete-stack "
            '--stack-name fastlane-stack"',
            "bash -c 'aws cloudformation create-stack --stack-name fastlane-stack; "
            "aws cloudformation delete-stack --stack-name fastlane-stack'",
        )
        for command in commands:
            with self.subTest(command=command):
                denied = fastlane_hook.handle_event(
                    "pre-tool-use",
                    payload(
                        "PreToolUse",
                        self.root,
                        tool_name="Bash",
                        tool_input={"command": command},
                    ),
                    root=self.root,
                    doctor_report=report(aws="AUTH-0001", external_authority=external),
                    envelope={
                        "AWS boundary": "MUTATE_LISTED_RESOURCES",
                        "GitHub boundary": "NONE",
                    },
                )
                decision = denied["hookSpecificOutput"]
                self.assertEqual(decision["permissionDecision"], "deny")

    def test_permission_request_never_auto_allows(self) -> None:
        result = fastlane_hook.handle_event(
            "permission-request",
            payload(
                "PermissionRequest",
                self.root,
                tool_name="Bash",
                tool_input={
                    "command": "python -m unittest",
                    "description": "disable sandbox for unrestricted access",
                },
            ),
            root=self.root,
            doctor_report=report(construction="AUTH-0001"),
            envelope={"AWS boundary": "NONE", "GitHub boundary": "BRANCH_AND_PR"},
        )
        decision = result["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "deny")
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"behavior": "allow"', source)

    def test_post_tool_runs_bounded_validation_without_claiming_evidence(self) -> None:
        calls: list[list[str]] = []
        trusted_git = str((self.root.parent / "trusted-tools" / "git.exe").resolve())

        def fail(root: Path, command: object) -> bool:
            calls.append(list(command))
            return False

        with mock.patch.object(
            fastlane_hook, "_resolve_trusted_git", return_value=trusted_git
        ):
            result = fastlane_hook.handle_event(
                "post-tool-use",
                payload(
                    "PostToolUse",
                    self.root,
                    tool_name="apply_patch",
                    tool_input={"command": "*** Begin Patch\n*** End Patch"},
                    tool_response={"ok": True},
                ),
                root=self.root,
                validation_runner=fail,
            )
        self.assertEqual(calls, [[trusted_git, "diff", "--check"]])
        self.assertIn("diff-format problem", result["systemMessage"])
        self.assertNotIn("evidence", result["systemMessage"].casefold())

        calls.clear()
        with mock.patch.object(
            fastlane_hook,
            "_resolve_trusted_git",
            side_effect=OSError("Trusted Git executable is unavailable or unsafe"),
        ):
            blocked = fastlane_hook.handle_event(
                "post-tool-use",
                payload(
                    "PostToolUse",
                    self.root,
                    tool_name="apply_patch",
                    tool_input={"command": "*** Begin Patch\n*** End Patch"},
                    tool_response={"ok": True},
                ),
                root=self.root,
                validation_runner=fail,
            )
        self.assertEqual(calls, [])
        self.assertIn("trusted Git", blocked["systemMessage"])

    def test_stop_continuation_and_loop_prevention(self) -> None:
        event = payload("Stop", self.root, stop_hook_active=False)
        continue_result = fastlane_hook.handle_event(
            "stop",
            event,
            root=self.root,
            doctor_report=report(automatic=True, owner_action=False),
        )
        self.assertEqual(continue_result["decision"], "block")
        for blocked in (
            report(automatic=False, owner_action=False),
            report(automatic=True, owner_action=True),
            report(automatic=True, owner_action=False, formal_receipt=True),
        ):
            self.assertIsNone(
                fastlane_hook.handle_event(
                    "stop", event, root=self.root, doctor_report=blocked
                )
            )
        self.assertIsNone(
            fastlane_hook.handle_event(
                "stop",
                payload("Stop", self.root, stop_hook_active=True),
                root=self.root,
                doctor_report=report(automatic=True, owner_action=False),
            )
        )

    def test_no_transcript_parsing_secret_persistence_or_tool_input_logging(
        self,
    ) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "transcript_path",
            "last_assistant_message",
            "AWS_ACCESS_KEY",
            "OPENAI_API_KEY",
            "GITHUB_TOKEN",
            "write_text(",
            'open("a',
            "logging.",
        ):
            self.assertNotIn(forbidden, source)
        security = (self.root / "SECURITY.md").read_text(encoding="utf-8")
        hooks = (self.root / "docs" / "HOOKS.md").read_text(encoding="utf-8")
        self.assertIn("Hooks are defense in depth", hooks)
        self.assertIn("internal schema 2", hooks)
        self.assertIn("expires after 15 minutes", hooks)
        self.assertIn("without assuming a `tool_use_id`", hooks)
        self.assertIn("never auto-allows", security)
        self.assertIn("private schema-2 transition record", security)


class AwsActionTransitionHookTests(unittest.TestCase):
    def _report_for(self, external: dict[str, object]) -> dict[str, object]:
        current = report(
            aws=str(external["authorization_id"]), external_authority=external
        )
        current["basis"] = {
            "requirements_revision": "REQ-0001",
            "design_revision": "DES-0001",
        }
        current["authorizations"]["construction"] = "AUTH-0001"
        return current

    def _candidate(
        self,
        heading: str,
        row: str,
        current_report: dict[str, object],
        *,
        existing_rows: tuple[str, ...] = (),
    ) -> tuple[
        bool, dict[str, str] | None, str | None, Path, tempfile.TemporaryDirectory[str]
    ]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        verify = root / "docs" / "project" / "VERIFY.md"
        verify.parent.mkdir(parents=True)
        stock = (REPOSITORY_ROOT / doctor.VERIFY_FILE).read_text(encoding="utf-8")
        anchor = _section_rows(stock, heading)[0]
        if existing_rows:
            stock = stock.replace(anchor, "\n".join((anchor, *existing_rows)), 1)
            anchor = existing_rows[-1]
        verify.write_text(stock, encoding="utf-8")
        tool_input = {
            "command": (
                "*** Begin Patch\n"
                "*** Update File: docs/project/VERIFY.md\n"
                "@@\n"
                f" {anchor}\n"
                f"+{row}\n"
                "*** End Patch"
            )
        }
        result = fastlane_hook._started_patch_candidate(
            "apply_patch", tool_input, current_report, root
        )
        return (*result, root, temporary)

    def _active_structured_transition(
        self, root: Path
    ) -> tuple[
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, str],
    ]:
        external = authority("FAST_DEV_GATE_B", ["cloudformation:CreateStack"])
        current = self._report_for(external)
        match = current["external_authority"]["request_match"]
        attempt_id = "AWS-DEPLOY-9300"
        authority_digest = fastlane_hook._canonical_digest(match)
        start_event = payload(
            "PreToolUse",
            root,
            tool_name="apply_patch",
            tool_input={"command": "approved STARTED patch"},
            session_id="session-9300",
            turn_id="turn-9300",
            tool_use_id="start-tool-9300",
        )
        identity = fastlane_hook._tool_identity(start_event)
        self.assertIsNotNone(identity)
        state = fastlane_hook._empty_transition_state(
            stage="START_BOUND",
            action_kind="FAST_DEV_GATE_B",
            identity=identity,
            tool_name="apply_patch",
            attempt_sha256=fastlane_hook._value_digest(attempt_id),
            authority_sha256=authority_digest,
            start_patch_sha256="sha256:" + "e" * 64,
        )
        fastlane_hook._store_transition(root, state)
        current["aws_action_transition"] = {
            "schema_version": 1,
            "status": "BOUND",
            "attempt_id": attempt_id,
            "authority_kind": "FAST_DEV_GATE_B",
            "request_match_sha256": authority_digest,
            "request_match": match,
        }
        tool_input = aws_request("CreateStack")
        pre_event = payload(
            "PreToolUse",
            root,
            tool_name="aws___call_aws",
            tool_input=tool_input,
            session_id="session-9300",
            turn_id="turn-9300",
            tool_use_id="aws-tool-9300",
        )
        permission_event = payload(
            "PermissionRequest",
            root,
            tool_name="aws___call_aws",
            tool_input=tool_input,
            session_id="session-9300",
            turn_id="turn-9300",
        )
        return (
            current,
            pre_event,
            permission_event,
            {
                "AWS boundary": "MUTATE_LISTED_RESOURCES",
                "GitHub boundary": "NONE",
            },
        )

    def test_permission_request_uses_documented_fields_and_exact_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            current, pre_event, permission_event, envelope = (
                self._active_structured_transition(root)
            )
            self.assertNotIn("tool_use_id", permission_event)
            self.assertIsNone(
                fastlane_hook.handle_event(
                    "pre-tool-use",
                    pre_event,
                    root=root,
                    doctor_report=current,
                    envelope=envelope,
                )
            )
            self.assertIsNone(
                fastlane_hook.handle_event(
                    "permission-request",
                    permission_event,
                    root=root,
                    doctor_report=current,
                    envelope=envelope,
                )
            )

        cases = ("session", "turn", "tool-name", "request", "authority")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                current, pre_event, permission_event, envelope = (
                    self._active_structured_transition(root)
                )
                self.assertIsNone(
                    fastlane_hook.handle_event(
                        "pre-tool-use",
                        pre_event,
                        root=root,
                        doctor_report=current,
                        envelope=envelope,
                    )
                )
                changed = dict(permission_event)
                if case == "session":
                    changed["session_id"] = "other-session"
                elif case == "turn":
                    changed["turn_id"] = "other-turn"
                elif case == "tool-name":
                    changed["tool_name"] = "mcp__aws-core__call_aws"
                elif case == "request":
                    changed["tool_input"] = aws_request("UpdateStack")
                else:
                    current = json.loads(json.dumps(current))
                    current["aws_action_transition"]["attempt_id"] = "AWS-DEPLOY-9999"
                denied = fastlane_hook.handle_event(
                    "permission-request",
                    changed,
                    root=root,
                    doctor_report=current,
                    envelope=envelope,
                )
                self.assertEqual(
                    denied["hookSpecificOutput"]["decision"]["behavior"], "deny"
                )
                self.assertIsNone(fastlane_hook._load_transition(root))

    def test_post_tool_use_requires_exact_tool_use_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            current, pre_event, permission_event, envelope = (
                self._active_structured_transition(root)
            )
            self.assertIsNone(
                fastlane_hook.handle_event(
                    "pre-tool-use",
                    pre_event,
                    root=root,
                    doctor_report=current,
                    envelope=envelope,
                )
            )
            self.assertIsNone(
                fastlane_hook.handle_event(
                    "permission-request",
                    permission_event,
                    root=root,
                    doctor_report=current,
                    envelope=envelope,
                )
            )
            missing_identity = {
                **permission_event,
                "hook_event_name": "PostToolUse",
                "tool_response": {"ok": True},
            }
            result = fastlane_hook.handle_event(
                "post-tool-use",
                missing_identity,
                root=root,
                doctor_report=current,
                envelope=envelope,
            )
            self.assertIn("identity changed", result["systemMessage"])
            self.assertIsNone(fastlane_hook._load_transition(root))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            current, pre_event, permission_event, envelope = (
                self._active_structured_transition(root)
            )
            fastlane_hook.handle_event(
                "pre-tool-use",
                pre_event,
                root=root,
                doctor_report=current,
                envelope=envelope,
            )
            fastlane_hook.handle_event(
                "permission-request",
                permission_event,
                root=root,
                doctor_report=current,
                envelope=envelope,
            )
            post_event = {
                **permission_event,
                "hook_event_name": "PostToolUse",
                "tool_use_id": "aws-tool-9300",
                "tool_response": {"ok": True},
            }
            result = fastlane_hook.handle_event(
                "post-tool-use",
                post_event,
                root=root,
                doctor_report=current,
                envelope=envelope,
            )
            self.assertIn("observed the AWS result", result["systemMessage"])
            state = fastlane_hook._load_transition(root)
            self.assertEqual(state["stage"], "AWS_RESULT_BOUND")
            fastlane_hook._clear_transition(root)

    def test_private_transition_state_clears_legacy_expired_and_replay(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self._active_structured_transition(root)
            state = fastlane_hook._load_transition(root)
            self.assertEqual(state["schema_version"], "2")

            legacy = dict(state)
            legacy["schema_version"] = "1"
            fastlane_hook._store_transition(root, legacy)
            self.assertIsNone(fastlane_hook._load_transition(root))
            self.assertFalse(fastlane_hook._transition_path(root).exists())

            path = fastlane_hook._transition_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
            self.assertIsNone(fastlane_hook._load_transition(root))
            self.assertFalse(path.exists())

            current, pre_event, _permission_event, envelope = (
                self._active_structured_transition(root)
            )
            path = fastlane_hook._transition_path(root)
            expired = (
                path.stat().st_mtime - fastlane_hook.TRANSITION_MAX_AGE_SECONDS - 1
            )
            os.utime(path, (expired, expired))
            self.assertIsNone(fastlane_hook._load_transition(root))

            current, pre_event, _permission_event, envelope = (
                self._active_structured_transition(root)
            )
            self.assertIsNone(
                fastlane_hook.handle_event(
                    "pre-tool-use",
                    pre_event,
                    root=root,
                    doctor_report=current,
                    envelope=envelope,
                )
            )
            replay = {**pre_event, "tool_use_id": "replayed-tool"}
            denied = fastlane_hook.handle_event(
                "pre-tool-use",
                replay,
                root=root,
                doctor_report=current,
                envelope=envelope,
            )
            self.assertIn(
                "replay",
                denied["hookSpecificOutput"]["permissionDecisionReason"],
            )
            self.assertIsNone(fastlane_hook._load_transition(root))

    def test_deployment_started_uses_observed_at_and_durable_source_columns(
        self,
    ) -> None:
        external = authority("FAST_DEV_GATE_B", ["cloudformation:CreateStack"])
        current = self._report_for(external)
        match = current["external_authority"]["request_match"]
        row = _table_line(
            (
                "EV-9100",
                "AWS-DEPLOY-9100",
                "AWS-20",
                "REQ-0001 / DES-0001 / AUTH-0001",
                "AUTH-0001",
                "NONE",
                str(match["expires_at"]),
                "Gate B fast-dev authority",
                "NONE",
                "fastlane-role",
                "NONE",
                "NONE",
                "NONE",
                "NONE",
                "sha256:" + "a" * 64,
                "change-set-1",
                "fastlane-stack",
                "cloudformation:CreateStack",
                "NONE",
                "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
                fastlane_hook.DEPLOYMENT_PRECALL_RESULT,
                "NONE",
                "NONE",
                "2027-01-01T00:00:00Z",
                "pre-call deployment journal",
                "PASS",
                "NONE",
                "STARTED",
            )
        )
        recognized, candidate, reason, _root, temporary = self._candidate(
            fastlane_hook.DEPLOYMENT_JOURNAL, row, current
        )
        try:
            self.assertTrue(recognized)
            self.assertIsNone(reason)
            self.assertEqual(candidate["action_kind"], "FAST_DEV_GATE_B")
        finally:
            temporary.cleanup()

    def test_teardown_started_binds_ready_fields_and_terminal_rejects_drift(
        self,
    ) -> None:
        external = authority(
            "AWS_TEARDOWN",
            ["cloudformation:DeleteStack"],
            authorization_id="TEARDOWN-AUTH-0001",
        )
        external.update(
            {
                "retained_resources": [],
                "shared_dependencies": [],
                "cost_effect": "removes stack billing",
                "post_action_verification": "cloudformation:DescribeStacks",
                "teardown_ready_binding": {
                    "evidence_id": "EV-9040",
                    "read_authorization": "AWS-READ-AUTH-0001",
                    "read_role_or_profile": "fastlane-read-role",
                    "read_receipt_digest": "sha256:" + "b" * 64,
                    "read_valid_until": "2099-12-31T23:59:59+00:00",
                    "read_authority_source": "owner-message MSG-AWS-READ-0001",
                    "expected_manifest_or_stack": "fastlane-stack",
                    "resources_retained": [],
                    "shared_dependencies": [],
                    "cost_effect": "removes stack billing",
                    "post_teardown_verification": "cloudformation:DescribeStacks",
                },
            }
        )
        current = self._report_for(external)
        cells = [
            "EV-9200",
            "AWS-TEARDOWN-9200",
            "AWS-50",
            "REQ-0001 / DES-0001 / AUTH-0001",
            "AWS-READ-AUTH-0001",
            "fastlane-read-role",
            "sha256:" + "b" * 64,
            "2099-12-31T23:59:59+00:00",
            "owner-message MSG-AWS-READ-0001",
            "TEARDOWN-AUTH-0001",
            "NONE",
            "fastlane-role",
            "fastlane-stack",
            "fastlane-stack",
            "cloudformation:DeleteStack",
            "NONE",
            "NONE",
            "removes stack billing",
            "cloudformation:DescribeStacks",
            fastlane_hook.TEARDOWN_PRECALL_RESULT,
            "NONE",
            "NONE",
            "NONE",
            fastlane_hook.TEARDOWN_PRECALL_RESULT,
            "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
            "2027-01-01T00:00:00Z",
            "pre-call teardown journal",
            "PASS",
            "NONE",
            "STARTED",
        ]
        started = _table_line(tuple(cells))
        recognized, candidate, reason, root, temporary = self._candidate(
            fastlane_hook.TEARDOWN_JOURNAL, started, current
        )
        try:
            self.assertTrue(recognized)
            self.assertIsNone(reason)
            self.assertEqual(candidate["action_kind"], "AWS_TEARDOWN")
            for index in (4, 5, 6, 7, 8, 12, 15, 16, 17, 18):
                changed = list(cells)
                changed[index] = "changed-bound-field"
                changed_result = self._candidate(
                    fastlane_hook.TEARDOWN_JOURNAL,
                    _table_line(tuple(changed)),
                    current,
                )
                try:
                    self.assertTrue(changed_result[0])
                    self.assertIsNone(changed_result[1])
                    self.assertIn("exactly bound", changed_result[2])
                finally:
                    changed_result[-1].cleanup()

            match = current["external_authority"]["request_match"]
            current["aws_action_transition"] = {
                "schema_version": 1,
                "status": "BOUND",
                "attempt_id": "AWS-TEARDOWN-9200",
                "authority_kind": "AWS_TEARDOWN",
                "request_match_sha256": fastlane_hook._canonical_digest(match),
                "request_match": match,
            }
            state = {
                "action_kind": "AWS_TEARDOWN",
                "attempt_sha256": candidate["attempt_sha256"],
                "authority_sha256": candidate["authority_sha256"],
                "aws_tool_sha256": "sha256:" + "c" * 64,
                "response_sha256": "sha256:" + "d" * 64,
            }
            terminal_cells = list(cells)
            terminal_cells[0] = "EV-9201"
            terminal_cells[19] = "DELETE_COMPLETE"
            terminal_cells[20] = "fastlane-stack"
            terminal_cells[23] = "CloudFormation stack scope"
            terminal_cells[25] = "2027-01-01T00:00:01Z"
            terminal_cells[26] = (
                "HOOK_RESULT: TOOL_USE_SHA256="
                + state["aws_tool_sha256"]
                + "; RESPONSE_SHA256="
                + state["response_sha256"]
            )
            terminal_cells[29] = "SUCCEEDED"
            terminal = _table_line(tuple(terminal_cells))
            verify = root / "docs" / "project" / "VERIFY.md"
            verify_text = verify.read_text(encoding="utf-8")
            placeholder = _section_rows(verify_text, fastlane_hook.TEARDOWN_JOURNAL)[0]
            heading_index = verify_text.index(fastlane_hook.TEARDOWN_JOURNAL)
            placeholder_index = verify_text.index(placeholder, heading_index)
            verify.write_text(
                verify_text[:placeholder_index]
                + "\n".join((placeholder, started))
                + verify_text[placeholder_index + len(placeholder) :],
                encoding="utf-8",
            )
            terminal_input = {
                "command": (
                    "*** Begin Patch\n*** Update File: docs/project/VERIFY.md\n@@\n"
                    f" {started}\n+{terminal}\n*** End Patch"
                )
            }
            terminal_result = fastlane_hook._terminal_patch_candidate(
                "apply_patch", terminal_input, current, root, state
            )
            self.assertTrue(terminal_result[0])
            self.assertIsNone(terminal_result[2])

            unknown_cells = list(cells)
            unknown_cells[0] = "EV-9202"
            unknown_cells[19] = fastlane_hook.TEARDOWN_RESUME_UNKNOWN_RESULT
            unknown_cells[20] = "NONE"
            unknown_cells[21] = "NONE"
            unknown_cells[22] = fastlane_hook.TEARDOWN_RESUME_UNKNOWN_RESIDUALS
            unknown_cells[23] = fastlane_hook.TEARDOWN_RESUME_UNKNOWN_RESULT
            unknown_cells[25] = "2027-01-01T00:00:02Z"
            unknown_cells[26] = (
                "RESUME_CLOSURE: STARTED_EVIDENCE=EV-9200; RESULT=UNOBSERVED"
            )
            unknown_cells[27] = "PASS"
            unknown_cells[28] = "NONE"
            unknown_cells[29] = "UNKNOWN"
            self.assertTrue(
                fastlane_hook._valid_aws50_unknown_row(
                    _table_line(tuple(unknown_cells)),
                    attempt_id="AWS-TEARDOWN-9200",
                    started_evidence_id="EV-9200",
                    started=cells,
                )
            )
            for index in (4, 5, 6, 7, 8, 12, 17, 18, 24):
                changed_unknown = list(unknown_cells)
                changed_unknown[index] = "changed-immutable-field"
                self.assertFalse(
                    fastlane_hook._valid_aws50_unknown_row(
                        _table_line(tuple(changed_unknown)),
                        attempt_id="AWS-TEARDOWN-9200",
                        started_evidence_id="EV-9200",
                        started=cells,
                    )
                )
            for index in (4, 5, 6, 7, 8, 12, 17, 18):
                changed_terminal = list(terminal_cells)
                changed_terminal[index] = "changed-immutable-field"
                changed_input = {
                    "command": (
                        "*** Begin Patch\n*** Update File: docs/project/VERIFY.md\n@@\n"
                        f" {started}\n+{_table_line(tuple(changed_terminal))}\n"
                        "*** End Patch"
                    )
                }
                changed_result = fastlane_hook._terminal_patch_candidate(
                    "apply_patch", changed_input, current, root, state
                )
                self.assertTrue(changed_result[0])
                self.assertIsNone(changed_result[1])
                self.assertIn("exactly bound", changed_result[2])
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
