"""Frozen Fastlane Engine parity fixtures and ephemeral measurement helpers."""

from __future__ import annotations

import argparse
import ast
import copy
import contextlib
import hashlib
import io
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable, Mapping
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import bootstrap_doctor as doctor
from tests import test_bootstrap_doctor as doctor_fixtures


ORACLE_PATH = REPOSITORY_ROOT / "tests/fixtures/engine_parity_v1.json"
QUALIFICATION_ORACLE_PATH = (
    REPOSITORY_ROOT / "tests/fixtures/engine_qualification_v1.json"
)
BASELINE_COMMIT = "312b53ce00f9db5263f3a72e778f833e70c7db8e"
BASELINE_PACKAGE_VERSION = "1" + ".2.10"
SUMMARY_TRUTH_BASE_COMMIT = "8dbb11fd0e54af392ac073ce597cdb26fc336fcc"
QUALIFICATION_BASE_COMMIT = "f26a085170de2f99ad11450b5bf3c2ebaaf30501"
QUALIFICATION_BASE_PACKAGE_VERSION = "1" + ".2.24"
PACKAGE_VERSION_SENTINEL = "<PACKAGE_VERSION>"
GIT_SHA_SENTINEL = "<GIT_SHA>"
GIT_SHA = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")

APPROVED_BEHAVIOR_CHANGES = [
    {
        "id": "DOCUMENT_SUMMARY_TRUTH_1_2_19",
        "base_commit": SUMMARY_TRUTH_BASE_COMMIT,
        "scope": [
            "document summary owner action and next action",
            "document summary canonical field selection",
            "document summary evidence maturity",
        ],
        "prohibited": [
            "lifecycle or routing change",
            "gate or authority change",
            "canonical digest change",
            "receipt change",
        ],
    }
]
SUMMARY_TRUTH_COMPATIBILITY_DIGESTS = {
    "template_source": (
        "3137e52e381bd524015f621805e1d1a973ec4b2b4dcf8db0bdf1c77d5d5559ff"
    ),
    "unconfigured_template": (
        "c92a5a86a32fbcd361ad4ab7d045cd354bd402b9d22352b379a5875358884d58"
    ),
    "rendered_intake": (
        "148d12873c7f29075cc3e26fc5ea3e086b072e797d39cfb92c0e2f4c3470324d"
    ),
    "gate_a_pending": (
        "e571531e8412407e9c227855f82f10c186dbc4e1d7bf271512f73b69cc6eeb9b"
    ),
    "gate_a_approved": (
        "ff0128a1e2e2a96ac08b47584388aadeb089b65563a14b5f33fe979b7d3dde5f"
    ),
    "gate_b_pending": (
        "4e3afacd02bfd47562de31b604b30541a06edc557bd021f2f4a10e8b2c60a688"
    ),
    "gate_b_approved": (
        "28b3d7001c738216fac2dae0d48be0a3a2e1b1b09375c62357c6adc068f92b0c"
    ),
}


# Each required refactor scenario remains tied to a named existing regression.
# Full report snapshots below add exact cross-domain parity at representative gates.
SCENARIO_COVERAGE: dict[str, tuple[str, ...]] = {
    "fresh_template": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_ordinary_doctor_routes_untouched_template_to_prerequisites",
    ),
    "prerequisite_failure_and_initialization": (
        "tests.test_product_journeys.ProductJourneyTests."
        "test_extracted_template_setup_initializes_once_and_resumes",
    ),
    "intake_pending_and_partial": (
        "tests.test_product_journeys.ProductJourneyTests."
        "test_partial_high_risk_intake_remains_a_plain_owner_consultation",
    ),
    "intake_stale_or_unproven": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_unproven_selection_is_agent_correctable_without_owner_confirmation",
    ),
    "intake_ambiguous": (
        "tests.test_intake_response.IntakeResponseRejectionTests."
        "test_unknown_duplicate_and_conflicting_reply_keys_are_rejected",
    ),
    "intake_secret_like": (
        "tests.test_intake_response.IntakeResponseRejectionTests."
        "test_record_unsafe_details_are_rejected_without_echo",
    ),
    "gate_a_blocked": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_gate_a_rejects_unresolved_normative_requirement",
    ),
    "gate_a_ready_and_receipt": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_gate_receipt_cli_validates_same_gate_and_never_writes",
    ),
    "gate_a_approved": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_exact_approved_receipts_route_uninitialized_plan_to_tasks",
    ),
    "gate_a_stale": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_stale_gates_route_to_repair_prompts",
    ),
    "gate_b_blocked": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_undeclared_architecture_traceability_blocks_gate_b",
    ),
    "gate_b_ready_and_receipt": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_gate_receipt_cli_validates_same_gate_and_never_writes",
    ),
    "gate_b_approved": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_exact_approved_receipts_route_uninitialized_plan_to_tasks",
    ),
    "gate_b_stale": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_gate_b_design_hash_staleness_blocks_query_start_claim_and_status",
    ),
    "adr_absent": (
        "tests.test_adr_rationale.AdrRationaleTests."
        "test_no_reference_keeps_projects_unchanged",
    ),
    "adr_current": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_current_adr_is_additive_and_digest_neutral",
    ),
    "adr_stale": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_stale_adr_is_safe_codex_correction_without_owner_turn",
    ),
    "adr_malformed_or_unsafe": (
        "tests.test_adr_rationale.AdrRationaleTests."
        "test_missing_and_unsafe_links_fail_closed",
    ),
    "adr_duplicate_or_conflicting": (
        "tests.test_adr_rationale.AdrRationaleTests.test_duplicate_id_fails_closed",
    ),
    "task_plan_and_claim": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_ready_selects_only_explicit_ready_tasks",
    ),
    "task_coverage_failure": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_task_requirement_coverage_rejects_invalid_acceptance_traces",
    ),
    "task_completion": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_single_task_mode_survives_pause_resume_and_complete",
    ),
    "task_failed_local_evidence": (
        "tests.test_product_journeys.ProductJourneyTests."
        "test_failed_task_evidence_cannot_produce_false_done",
    ),
    "release_ready_and_blocked": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_plan_state_and_release_state_have_explicit_routes",
    ),
    "aws_guidance_and_read_authority": (
        "tests.test_product_journeys.ProductJourneyTests."
        "test_aws_guidance_read_scope_preflight_and_mutation_wait_are_serial",
    ),
    "aws_preflight": (
        "tests.test_doctor_interaction.DoctorInteractionTests."
        "test_aws_preflight_collects_evidence_before_requesting_authority",
    ),
    "deployment_started_and_terminal": (
        "tests.test_bootstrap_doctor.AwsDeploymentReconciliationRegressionTests."
        "test_started_and_every_terminal_action_require_aws30",
    ),
    "deployment_partial_or_stale": (
        "tests.test_bootstrap_doctor.AwsDeploymentReconciliationRegressionTests."
        "test_aws30_complete_blocked_and_stale_have_distinct_states",
    ),
    "deployment_reconciliation": (
        "tests.test_bootstrap_doctor.AwsDeploymentReconciliationRegressionTests."
        "test_deployment_sequence_routes_through_release_cutoff_and_residual_review",
    ),
    "residual_review": (
        "tests.test_product_journeys.ProductJourneyTests."
        "test_residual_disposition_is_fresh_set_level_and_non_authorizing",
    ),
    "teardown_readiness_and_terminal": (
        "tests.test_bootstrap_doctor.AwsExecutionContractRegressionTests."
        "test_teardown_sequence_routes_by_current_phase_evidence",
    ),
    "greenfield": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_greenfield_gate_b_binds_application_source_to_singular_app",
    ),
    "brownfield": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_brownfield_baseline_is_deferred_until_gate_a_readiness",
    ),
    "high_risk": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_high_risk_requires_high_risk_profile",
    ),
    "select_amend_preserve": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_adaptive_coverage_select_amend_preserve_and_fail_closed",
    ),
    "grandfathered_schemas": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_approved_schema_five_design_is_grandfathered_without_diagrams",
    ),
    "malformed_or_duplicate_rows": (
        "tests.test_fastlane_contracts.SharedEvidenceAndCheckpointTests."
        "test_malformed_or_discontiguous_checkpoints_fail",
    ),
    "tampered_digests": (
        "tests.test_bootstrap_doctor.BootstrapDoctorTests."
        "test_gate_b_hash_binds_every_envelope_row",
    ),
    "unsafe_paths": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_unsafe_write_boundaries_are_rejected",
    ),
    "unsafe_authority": (
        "tests.test_fastlane_hooks.FastlaneHookTests."
        "test_unauthorized_aws_and_github_mutations_are_denied",
    ),
    "interrupted_action": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_interrupted_state_first_write_blocks_next_mutation",
    ),
    "resume": (
        "tests.test_task_waves.TaskWaveSafetyTests."
        "test_resume_fails_closed_when_git_is_unavailable_or_dirty_set_drifts",
    ),
}

# COMPATIBILITY: the frozen pre-refactor oracle records the original selectors.
# The regression methods moved without semantic changes during 1.2.25
# qualification, so discovery resolves only these exact class prefixes.
SCENARIO_SELECTOR_RELOCATIONS = {
    ("tests.test_bootstrap_doctor.AwsDeploymentReconciliationRegressionTests."): (
        "tests.test_engine_aws_deployment.AwsDeploymentReconciliationRegressionTests."
    ),
    ("tests.test_bootstrap_doctor.AwsExecutionContractRegressionTests."): (
        "tests.test_engine_aws_execution.AwsExecutionContractRegressionTests."
    ),
}


def current_scenario_selector(selector: str) -> str:
    """Return the current location for one frozen regression selector."""

    for previous, current in SCENARIO_SELECTOR_RELOCATIONS.items():
        if selector.startswith(previous):
            return current + selector[len(previous) :]
    return selector


REPORT_CASES = (
    "template_source",
    "unconfigured_template",
    "rendered_intake",
    "gate_a_pending",
    "gate_a_approved",
    "gate_b_pending",
    "gate_b_approved",
)

QUALIFICATION_REPORT_CASES = (
    "stale_gate_a_summary",
    "task_ready",
)

QUALIFICATION_AWS_SCENARIO_COVERAGE: dict[str, tuple[str, ...]] = {
    "deployment_action_terminals": (
        "tests.test_engine_aws_deployment."
        "AwsDeploymentReconciliationRegressionTests."
        "test_started_and_every_terminal_action_require_aws30",
    ),
    "deployment_reconciliation_terminals": (
        "tests.test_engine_aws_deployment."
        "AwsDeploymentReconciliationRegressionTests."
        "test_aws30_complete_blocked_and_stale_have_distinct_states",
    ),
    "teardown_action_and_review_terminals": (
        "tests.test_engine_aws_execution."
        "AwsExecutionContractRegressionTests."
        "test_teardown_sequence_routes_by_current_phase_evidence",
    ),
}


def _normalize_string(value: str) -> str:
    return GIT_SHA.sub(GIT_SHA_SENTINEL, value)


def normalize_report(value: Any, *, key: str | None = None) -> Any:
    """Normalize only approved package and synthetic Git identities."""

    if key == "bootstrap_version":
        return PACKAGE_VERSION_SENTINEL
    if isinstance(value, Mapping):
        return {
            str(item_key): normalize_report(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_report(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_report(item) for item in value]
    if isinstance(value, str):
        return _normalize_string(value)
    return value


def _capture_case(report: dict[str, Any]) -> dict[str, Any]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        doctor.print_human(report)
    return {
        "exit_code": 0 if report["ok"] else 1,
        "human_output": _normalize_string(stream.getvalue()),
        "report": normalize_report(report),
    }


def _project_case(
    temporary: Path,
    name: str,
    configure: Callable[[doctor_fixtures.BootstrapDoctorTests, Path], None],
) -> dict[str, Any]:
    parent = temporary / name
    parent.mkdir()
    fixture = doctor_fixtures.BootstrapDoctorTests()
    project = fixture.copy_project(parent)
    if name.startswith("gate-b"):
        # CANONICALIZATION: bind Gate B to one synthetic commit whose tree is
        # independent of later packaged-source movement. The ignored package is
        # still read and validated by the Engine; it simply cannot perturb the
        # deliberately synthetic Git identity allowed by the parity contract.
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        (project / ".fastlane-parity-baseline").write_text(
            "Fastlane synthetic parity baseline.\n",
            encoding="utf-8",
            newline="\n",
        )
        (project / ".git/info/exclude").write_text(
            "*\n!.fastlane-parity-baseline\n",
            encoding="utf-8",
            newline="\n",
        )
    with mock.patch.dict(
        os.environ,
        {
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
        },
    ):
        configure(fixture, project)
    return _capture_case(doctor.inspect_project(project))


def build_parity_reports() -> dict[str, dict[str, Any]]:
    """Build representative complete Engine outputs from synthetic records."""

    reports = {
        "template_source": _capture_case(
            doctor.inspect_project(REPOSITORY_ROOT, template_source=True)
        ),
        "unconfigured_template": _capture_case(doctor.inspect_project(REPOSITORY_ROOT)),
    }
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        reports["rendered_intake"] = _project_case(
            temporary,
            "rendered-intake",
            lambda _fixture, _project: None,
        )
        reports["gate_a_pending"] = _project_case(
            temporary,
            "gate-a-pending",
            lambda fixture, project: fixture.pending_gate_a(project),
        )

        def approve_gate_a(
            fixture: doctor_fixtures.BootstrapDoctorTests, project: Path
        ) -> None:
            fixture.approve_project(project, gate_b=False)
            fixture.set_non_material_req_evidence(project)
            doctor_fixtures.refresh_document_summaries(project)

        reports["gate_a_approved"] = _project_case(
            temporary, "gate-a-approved", approve_gate_a
        )
        reports["gate_b_pending"] = _project_case(
            temporary,
            "gate-b-pending",
            lambda fixture, project: fixture.pending_gate_b(project),
        )

        def approve_gate_b(
            fixture: doctor_fixtures.BootstrapDoctorTests, project: Path
        ) -> None:
            fixture.approve_project(project)
            fixture.set_non_material_req_evidence(project)
            doctor_fixtures.refresh_document_summaries(project)

        reports["gate_b_approved"] = _project_case(
            temporary, "gate-b-approved", approve_gate_b
        )
    return {name: reports[name] for name in REPORT_CASES}


def build_qualification_reports() -> dict[str, dict[str, Any]]:
    """Build reports not present in the frozen pre-refactor oracle."""

    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)

        def stale_gate_a_summary(
            fixture: doctor_fixtures.BootstrapDoctorTests, project: Path
        ) -> None:
            fixture.pending_gate_a(project)
            baseline = doctor.inspect_project(project)
            prd_path = project / "docs/project/PRD.md"
            source_text = prd_path.read_text(encoding="utf-8")
            prd_summary = next(
                item
                for item in baseline["document_summaries"]["documents"]
                if item["path"] == doctor.PRD_FILE
            )
            product_outcome = next(
                item["value"]
                for item in prd_summary["fields"]
                if item["label"] == "Product outcome"
            )
            changed = source_text.replace(
                f"| Product outcome | {product_outcome} |",
                "| Product outcome | Stale generated value |",
                1,
            )
            if changed == source_text:
                raise AssertionError("qualification summary fixture did not change")
            prd_path.write_text(changed, encoding="utf-8", newline="\n")
            doctor_fixtures.refresh_control_hashes(project)

        def task_ready(
            fixture: doctor_fixtures.BootstrapDoctorTests, project: Path
        ) -> None:
            fixture.approve_project(project)
            fixture.set_non_material_req_evidence(project)
            fixture.initialize_task_plan(
                project,
                doctor_fixtures.ready_task(
                    requirements=(
                        doctor_fixtures.MODERN_TASK_REQUIREMENT_TRACE + "; PROP-001"
                    ),
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    command="python -m unittest tests.test_properties",
                    property_projection=(
                        doctor_fixtures.property_execution_projection()
                    ),
                ),
            )
            doctor_fixtures.refresh_document_summaries(project)

        reports = {
            "stale_gate_a_summary": _project_case(
                temporary, "stale-gate-a-summary", stale_gate_a_summary
            ),
            "task_ready": _project_case(temporary, "gate-b-task-ready", task_ready),
        }
    return {name: reports[name] for name in QUALIFICATION_REPORT_CASES}


def build_deployment_qualification_cases() -> dict[str, dict[str, Any]]:
    """Project every deployment terminal through the public Engine contract."""

    from tests.test_engine_aws_deployment import (
        AwsDeploymentReconciliationRegressionTests,
    )

    fixture = AwsDeploymentReconciliationRegressionTests()
    read_authority = fixture.deployment_read_authority()
    cases: dict[str, dict[str, Any]] = {}

    def capture(name: str, rows: list[tuple[str, ...]], *, read: bool = False) -> None:
        projection = fixture.derive_deployment(
            rows,
            read_authority=read_authority if read else None,
        )
        route = doctor.derive_aws_delivery_route(
            "READY_TO_DEPLOY",
            {"progress_state": "AWS_PREFLIGHT_READY"},
            projection,
            "fast-dev",
        )
        cases[name] = {
            "status": projection["status"],
            "action_status": projection["action_status"],
            "reconciliation_status": projection["reconciliation_status"],
            "phase": projection["phase"],
            "route": list(route) if route else None,
            "issues": list(projection["issues"]),
        }

    for index, action_status in enumerate(
        ("STARTED", "SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN"), start=1
    ):
        rows = [
            fixture.deployment_row(
                evidence_id=f"EV-31{index:02d}",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-01T00:00:00Z",
            )
        ]
        if action_status != "STARTED":
            rows.append(
                fixture.deployment_row(
                    evidence_id=f"EV-32{index:02d}",
                    phase="AWS-20",
                    status=action_status,
                    observed_at="2027-01-01T00:01:00Z",
                )
            )
        capture(f"action_{action_status.casefold()}", rows)

    for index, action_status in enumerate(
        ("SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN"), start=1
    ):
        rows = [
            fixture.deployment_row(
                evidence_id=f"EV-33{index:02d}",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-02T00:00:00Z",
            ),
            fixture.deployment_row(
                evidence_id=f"EV-34{index:02d}",
                phase="AWS-20",
                status=action_status,
                observed_at="2027-01-02T00:01:00Z",
            ),
            fixture.deployment_row(
                evidence_id=f"EV-35{index:02d}",
                phase="AWS-30",
                status="COMPLETE",
                observed_at="2027-01-02T00:02:00Z",
                read_authority=read_authority,
            ),
        ]
        capture(f"reconciled_{action_status.casefold()}", rows, read=True)

    for index, reconciliation_status in enumerate(("BLOCKED", "STALE"), start=1):
        rows = [
            fixture.deployment_row(
                evidence_id=f"EV-36{index:02d}",
                phase="AWS-20",
                status="STARTED",
                observed_at="2027-01-03T00:00:00Z",
            ),
            fixture.deployment_row(
                evidence_id=f"EV-37{index:02d}",
                phase="AWS-20",
                status="SUCCEEDED",
                observed_at="2027-01-03T00:01:00Z",
            ),
            fixture.deployment_row(
                evidence_id=f"EV-38{index:02d}",
                phase="AWS-30",
                status=reconciliation_status,
                observed_at="2027-01-03T00:02:00Z",
                read_authority=read_authority,
            ),
        ]
        capture(f"reconciliation_{reconciliation_status.casefold()}", rows, read=True)

    return cases


def _branch_complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(
            child,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.IfExp,
                ast.ExceptHandler,
                ast.Assert,
                ast.comprehension,
            ),
        ):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(0, len(child.values) - 1)
        elif isinstance(child, ast.Match):
            score += len(child.cases)
    return score


def doctor_characterization() -> dict[str, Any]:
    """Return deterministic structural metrics for the locked monolith."""

    path = REPOSITORY_ROOT / "scripts/bootstrap_doctor.py"
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    tree = ast.parse(text)
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = node.end_lineno or node.lineno
            functions.append(
                {
                    "branch_complexity": _branch_complexity(node),
                    "end_line": end_line,
                    "line_count": end_line - node.lineno + 1,
                    "name": node.name,
                    "start_line": node.lineno,
                }
            )
        elif isinstance(node, ast.ClassDef):
            classes.append(
                {
                    "end_line": node.end_lineno or node.lineno,
                    "name": node.name,
                    "start_line": node.lineno,
                }
            )
    structural = {"classes": classes, "functions": functions}
    canonical = json.dumps(
        structural, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return {
        "byte_count": len(raw),
        "class_count": len(classes),
        "classes": classes,
        "function_count": len(functions),
        "functions": functions,
        "line_count": len(text.splitlines()),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "structure_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def receipt_contracts() -> dict[str, dict[str, str]]:
    """Capture the five exact owner receipt templates byte-for-byte."""

    text = (REPOSITORY_ROOT / "prompts/CODEX-PROMPTS.md").read_text(encoding="utf-8")
    sections = []
    for heading in (
        "## Exactly accepted Gate receipts",
        "## Exact conditional AWS action receipts",
    ):
        start = text.index(heading)
        next_heading = text.find("\n## ", start + len(heading))
        sections.append(text[start:] if next_heading < 0 else text[start:next_heading])
    blocks = []
    for section in sections:
        blocks.extend(
            match.group("body")
            for match in re.finditer(
                r"(?P<fence>`{3}|~{3})text\n(?P<body>.*?)\n(?P=fence)",
                section,
                re.DOTALL,
            )
        )
    result: dict[str, dict[str, str]] = {}
    for block in blocks:
        normalized = block.replace("\r\n", "\n").replace("\r", "\n") + "\n"
        label = normalized.splitlines()[0]
        result[label] = {
            "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "text": normalized,
        }
    return result


def canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def summary_truth_compatibility_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only the approved derived view and locator-coordinate drift."""

    normalized = copy.deepcopy(dict(case))
    report = normalized.get("report")
    if not isinstance(report, dict):
        return normalized
    report.pop("document_summaries", None)
    context_plan = report.get("context_plan")
    if not isinstance(context_plan, dict):
        return normalized
    for group in ("resolved_initial_slices", "resolved_on_demand_slices"):
        slices = context_plan.get(group)
        if not isinstance(slices, list):
            continue
        for source_slice in slices:
            if not isinstance(source_slice, dict):
                continue
            for field in (
                "canonical_sha256",
                "source_bytes",
                "start_line",
                "end_line",
            ):
                source_slice.pop(field, None)
    return normalized


def frozen_doctor_characterization() -> dict[str, Any]:
    """Preserve the exact pre-refactor structural baseline when refreshing reports."""

    if ORACLE_PATH.is_file():
        existing = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
        baseline = existing.get("baseline")
        characterization = existing.get("doctor_characterization")
        if (
            isinstance(baseline, Mapping)
            and baseline.get("commit") == BASELINE_COMMIT
            and isinstance(characterization, dict)
        ):
            return characterization
    return doctor_characterization()


def build_oracle() -> dict[str, Any]:
    reports = build_parity_reports()
    return {
        "schema_version": 1,
        "baseline": {
            "commit": BASELINE_COMMIT,
            "package_version": BASELINE_PACKAGE_VERSION,
            "report_schema_version": 2,
        },
        "approved_behavior_changes": APPROVED_BEHAVIOR_CHANGES,
        "summary_truth_compatibility": {
            "base_commit": SUMMARY_TRUTH_BASE_COMMIT,
            "allowed_projection": "document_summaries",
            "allowed_locator_metadata": [
                "canonical_sha256",
                "source_bytes",
                "start_line",
                "end_line",
            ],
            "report_case_digests": SUMMARY_TRUTH_COMPATIBILITY_DIGESTS,
        },
        "normalization": {
            "allowed": [
                "package version",
                "repository or synthetic Git commit identity",
            ],
            "forbidden": [
                "diagnostic IDs or order",
                "paths or messages",
                "lifecycle or next prompt",
                "owner action or continuation",
                "authority or remediation",
                "canonical projections or receipts",
            ],
        },
        "doctor_characterization": frozen_doctor_characterization(),
        "receipt_contracts": receipt_contracts(),
        "report_case_digests": {
            name: canonical_digest(case) for name, case in reports.items()
        },
        "report_cases": reports,
        "scenario_coverage": {
            name: list(selectors) for name, selectors in SCENARIO_COVERAGE.items()
        },
    }


def build_qualification_oracle() -> dict[str, Any]:
    """Freeze current modular boundaries without replacing the original oracle."""

    reports = build_qualification_reports()
    deployment_cases = build_deployment_qualification_cases()
    return {
        "schema_version": 1,
        "baseline": {
            "commit": QUALIFICATION_BASE_COMMIT,
            "package_version": QUALIFICATION_BASE_PACKAGE_VERSION,
            "report_schema_version": 2,
        },
        "normalization": {
            "allowed": [
                "package version",
                "repository or synthetic Git commit identity",
            ],
            "forbidden": [
                "diagnostic IDs or order",
                "lifecycle or next prompt",
                "owner action or continuation",
                "authority or remediation",
                "deployment action or reconciliation result",
                "canonical projections or receipts",
            ],
        },
        "report_case_digests": {
            name: canonical_digest(case) for name, case in reports.items()
        },
        "report_cases": reports,
        "deployment_case_digests": {
            name: canonical_digest(case) for name, case in deployment_cases.items()
        },
        "deployment_cases": deployment_cases,
        "aws_scenario_coverage": {
            name: list(selectors)
            for name, selectors in QUALIFICATION_AWS_SCENARIO_COVERAGE.items()
        },
    }


def benchmark_template_source(iterations: int = 5) -> dict[str, Any]:
    """Measure the same-process template scenario without persisting machine data."""

    if iterations < 1:
        raise ValueError("iterations must be positive")
    doctor.inspect_project(REPOSITORY_ROOT, template_source=True)
    wall_ms: list[float] = []
    cpu_ms: list[float] = []
    for _index in range(iterations):
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        report = doctor.inspect_project(REPOSITORY_ROOT, template_source=True)
        cpu_ms.append((time.process_time() - cpu_start) * 1000)
        wall_ms.append((time.perf_counter() - wall_start) * 1000)
        if not report["ok"]:
            raise RuntimeError("template-source benchmark scenario is not coherent")
    tracemalloc.start()
    doctor.inspect_project(REPOSITORY_ROOT, template_source=True)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "iterations": iterations,
        "peak_memory_mib": peak / (1024 * 1024),
        "warm_median_cpu_ms": statistics.median(cpu_ms),
        "warm_median_wall_ms": statistics.median(wall_ms),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write-oracle", action="store_true")
    action.add_argument("--write-qualification-oracle", action="store_true")
    action.add_argument("--benchmark", action="store_true")
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args(argv)
    if args.benchmark:
        print(json.dumps(benchmark_template_source(args.iterations), indent=2))
        return 0
    output_path = (
        QUALIFICATION_ORACLE_PATH if args.write_qualification_oracle else ORACLE_PATH
    )
    payload = (
        build_qualification_oracle()
        if args.write_qualification_oracle
        else build_oracle()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {output_path.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
