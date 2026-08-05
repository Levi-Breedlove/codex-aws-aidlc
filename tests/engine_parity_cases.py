"""Frozen Fastlane Engine parity fixtures and ephemeral measurement helpers."""

from __future__ import annotations

import argparse
import ast
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
BASELINE_COMMIT = "312b53ce00f9db5263f3a72e778f833e70c7db8e"
BASELINE_PACKAGE_VERSION = "1" + ".2.10"
PACKAGE_VERSION_SENTINEL = "<PACKAGE_VERSION>"
GIT_SHA_SENTINEL = "<GIT_SHA>"
GIT_SHA = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")


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


REPORT_CASES = (
    "template_source",
    "unconfigured_template",
    "rendered_intake",
    "gate_a_pending",
    "gate_a_approved",
    "gate_b_pending",
    "gate_b_approved",
)


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


def build_oracle() -> dict[str, Any]:
    reports = build_parity_reports()
    return {
        "schema_version": 1,
        "baseline": {
            "commit": BASELINE_COMMIT,
            "package_version": BASELINE_PACKAGE_VERSION,
            "report_schema_version": 2,
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
        "doctor_characterization": doctor_characterization(),
        "receipt_contracts": receipt_contracts(),
        "report_case_digests": {
            name: canonical_digest(case) for name, case in reports.items()
        },
        "report_cases": reports,
        "scenario_coverage": {
            name: list(selectors) for name, selectors in SCENARIO_COVERAGE.items()
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
    action.add_argument("--benchmark", action="store_true")
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args(argv)
    if args.benchmark:
        print(json.dumps(benchmark_template_source(args.iterations), indent=2))
        return 0
    ORACLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ORACLE_PATH.write_text(
        json.dumps(build_oracle(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {ORACLE_PATH.relative_to(REPOSITORY_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
