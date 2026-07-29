from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


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
        raw_external if "request_match" in raw_external else normalized_authority(raw_external)
    )
    return {
        "gates": {"gate_a": "BLOCKED", "gate_b": "BLOCKED"},
        "authorizations": {"construction": construction, "aws": aws},
        "write_authority": write_authority or {
            "valid": False,
            "approved_write_roots": [],
            "exclusions": [],
            "protected_paths": [],
            "active_task": "NONE",
            "active_task_write_set": [],
        },
        "external_authority": projected_external,
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
        "resources": [f"RESOURCES: {item}" for item in (resources or ["fastlane-stack"])],
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
        "Action", "Authorization ID", "Construction AUTH", "Role or profile",
        "Artifact digest", "IaC plan/change-set binding",
        "Account / Region / environment", "Resources and operations",
        "Cost ceiling and validity", "Rollback boundary",
        "Stable owner-message source", "Approver", "Observed at",
        "Verbatim receipt SHA-256", "Preflight evidence",
        "Identity and boundary match", "Result",
    )
    row = (
        "Read-only preflight", "AWS-READ-AUTH-0001", "AUTH-0001",
        "fastlane-role", row_artifact,
        "NOT_APPLICABLE — read-only preflight creates no plan",
        "ACCOUNT: 111122223333; REGION: us-west-2; ENVIRONMENT: development",
        "RESOURCES: fastlane-stack; OPERATIONS: cloudformation:DescribeStacks",
        "COST: expected low-volume request charges under USD 0.01; "
        "BOUNDED_BY: MINIMIZE_TOTAL_COST; HARD_CAP: USD 20.00; "
        f"VALID_UNTIL: {valid_until}",
        "NOT_APPLICABLE — no mutation", "owner-message-1", "owner-handle",
        "2026-07-20T12:00:00+00:00", digest, "NONE", "PASS", "AUTHORIZED",
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
    return {
        "command": f"*** Begin Patch\n*** Update File: {path}\n*** End Patch"
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
                    self.assertIn("git rev-parse --show-toplevel", hook["command"])
                    self.assertIn(
                        "git rev-parse --show-toplevel", hook["commandWindows"]
                    )
                    self.assertIn("fastlane_hook.py", hook["command"])
                    self.assertIn("fastlane_hook.py", hook["commandWindows"])
        for event in ("PreToolUse", "PermissionRequest"):
            matcher = data["hooks"][event][0]["matcher"]
            self.assertIn("use_aws", matcher)
            self.assertIn("aws___.*", matcher)
            self.assertIn("mcp__.*", matcher)
            self.assertNotIn("call_aws", matcher)
            self.assertNotIn("run_script", matcher)

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
        external = authority(
            "FAST_DEV_GATE_B", ["cloudformation:CreateStack"]
        )
        for tool_name in (
            "aws___invoke_operation",
            "mcp__aws-core__invoke_operation",
            "aws___call_aws",
        ):
            with self.subTest(tool_name=tool_name):
                self.assertIsNone(
                    fastlane_hook.handle_event(
                        "pre-tool-use",
                        payload(
                            "PreToolUse",
                            self.root,
                            tool_name=tool_name,
                            tool_input=aws_request("CreateStack"),
                        ),
                        root=self.root,
                        doctor_report=report(
                            aws="AUTH-0001", external_authority=external
                        ),
                        envelope={
                            "AWS boundary": "MUTATE_LISTED_RESOURCES",
                            "GitHub boundary": "NONE",
                        },
                    )
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

    def test_presigned_urls_require_exact_direction_resource_and_expiration(self) -> None:
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
                doctor_report=report(
                    aws="AUTH-0001", external_authority=download
                ),
                envelope={
                    "AWS boundary": "READ_ONLY",
                    "GitHub boundary": "NONE",
                },
            )
        )

        mismatches = (
            ({**request, "direction": "upload"}, "mutation authority"),
            ({**request, "key": "releases/other.zip"}, "resource target"),
            ({key: value for key, value in request.items() if key != "expires_in"}, "positive expiration"),
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
                    doctor_report=report(
                        aws="AUTH-0001", external_authority=download
                    ),
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
            "AWS_DEPLOYMENT", ["cloudformation:CreateStack"],
            authorization_id="AWS-AUTH-0001",
        )
        for tool_input, reason in (
            ({"aws_profile": "fastlane-role"}, "exact task identifier"),
            (
                {"task_id": "task-123", "aws_profile": "fastlane-role"},
                "not bound in current doctor-derived authority",
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
                tool_name="mcp__github__create_pull_request",
                tool_input={"description": "Open the reviewed pull request"},
            ),
            root=self.root,
            doctor_report=report(construction="AUTH-0001"),
            envelope={
                "AWS boundary": "NONE",
                "GitHub boundary": "BRANCH_AND_PR",
            },
        )
        self.assertIsNone(result)

    def test_write_authority_enforces_roots_exclusions_protection_and_active_task(self) -> None:
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
                    doctor_report=report(construction="AUTH-0001", write_authority=authority),
                    envelope={"AWS boundary": "NONE", "GitHub boundary": "NONE"},
                )
                self.assertIn(reason, denied["hookSpecificOutput"]["permissionDecisionReason"])

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

    def test_aws_read_fast_dev_explicit_deployment_and_teardown_are_distinct(self) -> None:
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
                        doctor_report=report(
                            aws="AUTH-0001", external_authority=read
                        ),
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
            doctor_report=report(
                aws="AUTH-0001", external_authority=gate_b_only
            ),
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
        current_report = report(
            aws="AUTH-0001", external_authority=read_authority
        )
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
                self.assertEqual(
                    invalid["kind"], "AWS_READ_PREFLIGHT_RECEIPT_REQUIRED"
                )
                self.assertEqual(invalid["validity"], "REQUIRED")

        fast_dev = authority(
            "FAST_DEV_GATE_B", ["cloudformation:CreateStack"]
        )
        self.assertIsNone(
            fastlane_hook.handle_event(
                "permission-request",
                payload(
                    "PermissionRequest",
                    self.root,
                    tool_name="aws___call_aws",
                    tool_input=aws_request("CreateStack"),
                ),
                root=self.root,
                doctor_report=report(
                    aws="AUTH-0001", external_authority=fast_dev
                ),
                envelope={
                    "AWS boundary": "MUTATE_LISTED_RESOURCES",
                    "GitHub boundary": "NONE",
                },
            )
        )

        mismatches = (
            ({**aws_request("CreateStack"), "operation_name": "Create"}, "exact operation"),
            (aws_request("CreateStack", "fastlane"), "resource target"),
            ({**aws_request("CreateStack"), "region": "us-east-1"}, "region"),
            ({**aws_request("CreateStack"), "aws_profile": "other-role"}, "profile"),
            ({**aws_request("CreateStack"), "artifact_digest": "sha256:wrong"}, "artifact"),
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
                    doctor_report=report(
                        aws="AUTH-0001", external_authority=fast_dev
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
            doctor_report=report(
                aws="AWS-AUTH-0001", external_authority=deployment
            ),
            envelope={
                "AWS boundary": "MUTATE_LISTED_RESOURCES",
                "GitHub boundary": "NONE",
            },
        )
        self.assertIn(
            "distinct current teardown receipt",
            denied_teardown["hookSpecificOutput"]["permissionDecisionReason"],
        )
        self.assertIsNone(
            fastlane_hook.handle_event(
                "pre-tool-use",
                payload(
                    "PreToolUse",
                    self.root,
                    tool_name="aws___call_aws",
                    tool_input=aws_request("DeleteStack"),
                ),
                root=self.root,
                doctor_report=report(
                    aws="TEARDOWN-AUTH-0001", external_authority=teardown
                ),
                envelope={
                    "AWS boundary": "MUTATE_LISTED_RESOURCES",
                    "GitHub boundary": "NONE",
                },
            )
        )

    def test_reviewed_scripts_require_exact_observable_content_and_authority(self) -> None:
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
            doctor_report=report(
                aws="AWS-AUTH-0001", external_authority=wrong_kind
            ),
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
                doctor_report=report(
                    aws="AWS-AUTH-0001", external_authority=teardown
                ),
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
        external = authority(
            "FAST_DEV_GATE_B", ["cloudformation:CreateStack"]
        )
        commands = (
            "aws cloudformation create-stack --stack-name fastlane-stack; "
            "aws cloudformation delete-stack --stack-name fastlane-stack",
            "powershell -Command \"aws cloudformation create-stack "
            "--stack-name fastlane-stack; aws cloudformation delete-stack "
            "--stack-name fastlane-stack\"",
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
                    doctor_report=report(
                        aws="AUTH-0001", external_authority=external
                    ),
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

        def fail(root: Path, command: object) -> bool:
            calls.append(list(command))
            return False

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
        self.assertEqual(calls, [["git", "diff", "--check"]])
        self.assertIn("diff-format problem", result["systemMessage"])
        self.assertNotIn("evidence", result["systemMessage"].casefold())

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

    def test_no_transcript_parsing_secret_persistence_or_tool_input_logging(self) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "transcript_path",
            "last_assistant_message",
            "AWS_ACCESS_KEY",
            "OPENAI_API_KEY",
            "GITHUB_TOKEN",
            "write_text(",
            "open(\"a",
            "logging.",
        ):
            self.assertNotIn(forbidden, source)
        security = (self.root / "SECURITY.md").read_text(encoding="utf-8")
        hooks = (self.root / "docs" / "HOOKS.md").read_text(encoding="utf-8")
        self.assertIn("Hooks are defense in depth", hooks)
        self.assertIn("never auto-allows", security)


if __name__ == "__main__":
    unittest.main()
