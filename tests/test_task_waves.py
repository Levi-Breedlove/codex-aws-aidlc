from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


task_waves = load_module(
    "task_waves_under_test",
    REPOSITORY_ROOT / "scripts" / "task_waves.py",
)


def snapshot(
    *,
    task_plan: str = "PLAN-0001",
    task_plan_state: str = "CURRENT",
    gate_b: str = "APPROVED_FOR_CONSTRUCTION",
    run_state: str = "NOT_STARTED",
    run_id: str = "NONE",
    coordinator: str = "UNASSIGNED",
    maximum_workers: int = 1,
    current_wave: str = "1",
    protected_dirty_paths: str = "NONE",
    baseline_commit: str = "abc1234",
    last_known_green_commit: str = "abc1234",
    last_checkpoint: str = "NONE",
) -> str:
    return f"""## Active execution snapshot

| Field | Value |
|---|---|
| Task-plan revision | `{task_plan}` |
| Task-plan state | `{task_plan_state}` |
| Requirements revision | `REQ-0001` |
| Design revision | `DES-0001` |
| Construction authorization | `AUTH-0001` |
| Gate B state | `{gate_b}` |
| Run state | `{run_state}` |
| Active run ID | `{run_id}` |
| Baseline commit | `{baseline_commit}` |
| Protected dirty paths | `{protected_dirty_paths}` |
| Coordinator | `{coordinator}` |
| Maximum workers | `{maximum_workers}` |
| Current wave | `{current_wave}` |
| Last checkpoint | `{last_checkpoint}` |
| Last known-green commit | `{last_known_green_commit}` |
| Next safe action | `Claim a ready task` |

"""


def task_block(
    task_id: str,
    status: str,
    dependencies: str = "NONE",
    *,
    waivers: str = "NONE",
    owner: str | None = None,
    run_id: str | None = None,
    write_set: str | None = None,
    external_state: str = "NONE",
    aws_mode: str = "NONE",
    attempt_budget: int = 2,
    attempts_used: int | None = None,
    evidence: str | None = None,
    blocker: str | None = None,
    skip_record: str | None = None,
    checkpoint: str | None = None,
    authorization: str = "AUTH-0001",
    design: str = "DES-0001; TECH: TECH-0001",
    requirements: str = "REQ-0001, FR-001",
    validation_command: str = "python -m unittest",
    property_execution_rows: tuple[str, ...] = (),
    harness_projection_rows: tuple[str, ...] = (),
) -> str:
    owner = owner or ("worker-1" if status == "IN_PROGRESS" else "UNASSIGNED")
    run_id = run_id or ("RUN-0001" if status == "IN_PROGRESS" else "NONE")
    attempts_used = (
        attempts_used
        if attempts_used is not None
        else (1 if status == "IN_PROGRESS" else 0)
    )
    evidence = evidence or ("EV-0001" if status == "DONE" else "NONE")
    blocker = blocker or (
        "Dependency unavailable; obtain fixture" if status == "BLOCKED" else "NONE"
    )
    skip_record = skip_record or ("SKIP-001" if status == "SKIPPED" else "NONE")
    checkpoint = checkpoint or ("CP-0001" if status == "IN_PROGRESS" else "NONE")
    write_set = write_set or f"app/{task_id.lower()}.py"
    property_projection = ""
    if property_execution_rows:
        property_projection = (
            "| Property ID | Framework TECH ID | Exact command | Run target/time bound | "
            "Seed or reproduction format | Evidence destination |\n"
            "|---|---|---|---|---|---|\n" + "\n".join(property_execution_rows) + "\n\n"
        )
    if harness_projection_rows:
        property_projection += (
            "| Harness ID | Layer | Selected check or tool | Trigger | Basis IDs | "
            "Exact command or API | Evidence destination | Required or conditional status |\n"
            "|---|---|---|---|---|---|---|---|\n"
            + "\n".join(harness_projection_rows)
            + "\n\n"
        )
    return f"""### {task_id} — Test task

- Status: `{status}`
- Requirements: `{requirements}`
- Design: `{design}`
- Authorization: `{authorization}`
- Depends on: `{dependencies}`
- Dependency waivers: `{waivers}`
- Owner: `{owner}`
- Run ID: `{run_id}`
- Risk: `LOW`
- Write set: `{write_set}`
- External state: `{external_state}`
- AWS mode: `{aws_mode}`
- Attempt budget: `{attempt_budget}`
- Attempts used: `{attempts_used}`
- Evidence: `{evidence}`
- Blocker: `{blocker}`
- Skip record: `{skip_record}`
- GitHub issue: `PENDING_SYNC`
- Last checkpoint: `{checkpoint}`
- Last updated: `2026-07-17T00:00:00+00:00`

#### Outcome

The task's bounded behavior is implemented and observable.

#### Acceptance criteria

- [{"x" if status == "DONE" else " "}] The observable task result matches its requirement.

#### Validation

{property_projection}```bash
{validation_command}
```

#### Execution log

{"2026-07-17T00:00:00+00:00 coordinator observed validation pass." if status == "DONE" else "Not started."}

"""


def document(
    blocks: list[str],
    *,
    snapshot_text: str | None = None,
    waiver_rows: list[str] | None = None,
    checkpoint_rows: list[str] | None = None,
) -> str:
    waiver_rows = waiver_rows or []
    rows = (
        "\n".join(waiver_rows)
        or "| `NONE` | `NONE` | `NONE` | `NONE` | No waivers recorded | TODO |"
    )
    checkpoint_content = "\n".join(checkpoint_rows or []) or (
        "| `NONE` | `NONE` | TODO | `REQ-0001` / `DES-0001` / `AUTH-0001` | "
        "TODO | No work started | Evidence: NONE; External: NONE | "
        "Blockers: NONE; Next: start run |"
    )
    return (
        "# Tasks\n\n"
        + (snapshot_text or snapshot())
        + "## Dependencies, waivers, and waves\n\n"
        + "### Dependency waiver registry\n\n"
        + "| Waiver ID | Skipped task | Applies to task | Authority | Rationale and preserved acceptance evidence | Recorded at |\n"
        + "|---|---|---|---|---|---|\n"
        + rows
        + "\n\n## Checkpoints and resume\n\n"
        + "| Checkpoint | Run | Time | REQ / DES / AUTH | Commit and protected dirty paths | Task outcomes and attempts | Evidence and external actions | Blockers and next safe action |\n"
        + "|---|---|---|---|---|---|---|---|\n"
        + checkpoint_content
        + "\n\n## Task definitions\n\n"
        + "".join(blocks)
    )


def parse_document(text: str):
    tasks = task_waves.parse_tasks(text)
    snap = task_waves.parse_snapshot(text)
    waivers = task_waves.parse_waivers(text)
    by_id = task_waves.validate(tasks, snap, waivers)
    return tasks, snap, waivers, by_id


def write_matching_state(root: Path, tasks_text: str) -> Path:
    state = json.loads((REPOSITORY_ROOT / "bootstrap.yaml").read_text(encoding="utf-8"))
    snap = task_waves.parse_snapshot(tasks_text)
    tasks = task_waves.parse_tasks(tasks_text)
    state["lifecycle"].update(
        {
            "requirements_revision": snap.get("Requirements revision"),
            "design_revision": snap.get("Design revision"),
            "construction_authorization": snap.get("Construction authorization"),
            "gate_a": "APPROVED_FOR_DESIGN",
            "gate_b": snap.get("Gate B state"),
        }
    )
    plan = snap.get("Task-plan revision")
    state_map = {
        "NOT_STARTED": "IDLE",
        "RUNNING": "RUNNING",
        "PAUSED": "CHECKPOINTED",
        "BLOCKED": "BLOCKED",
        "COMPLETE": "COMPLETE",
    }
    execution_state = state_map[snap.get("Run state")]
    checkpoint = snap.get("Last checkpoint")
    state["execution"].update(
        {
            "plan_revision": None if plan == "UNINITIALIZED" else plan,
            "plan_state": snap.get("Task-plan state"),
            "run_id": None
            if snap.get("Active run ID") == "NONE"
            else snap.get("Active run ID"),
            "coordinator": None
            if snap.get("Coordinator") in {"NONE", "UNASSIGNED"}
            else snap.get("Coordinator"),
            "mode": "NONE" if execution_state == "IDLE" else "AUTONOMOUS",
            "state": execution_state,
            "basis": None
            if execution_state == "IDLE"
            else {
                "requirements_revision": snap.get("Requirements revision"),
                "design_revision": snap.get("Design revision"),
                "construction_authorization": snap.get("Construction authorization"),
            },
            "active_tasks": sorted(
                task.task_id for task in tasks if task.status == "IN_PROGRESS"
            ),
            "attempts": {task.task_id: task.attempts_used for task in tasks},
            "last_checkpoint": None
            if execution_state == "IDLE" or checkpoint == "NONE"
            else {
                "id": checkpoint,
                "at": "2026-07-17T00:00:00+00:00",
                "evidence_ref": f"VERIFY.md#{checkpoint.lower()}",
            },
        }
    )
    path = root / "bootstrap.yaml"
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return path


def write_task_project(root: Path, tasks_text: str) -> tuple[Path, Path]:
    tasks_path = root / "TASKS.md"
    tasks_path.write_text(tasks_text, encoding="utf-8")
    return tasks_path, write_matching_state(root, tasks_text)


def write_technology_register(
    root: Path,
    *tech_ids: str,
    property_rows: tuple[str, ...] = (),
    property_version_policy: str = "MINIMUM: 6.0",
) -> Path:
    prd_path = root / "docs" / "project" / "PRD.md"
    prd_path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        (
            f"| {tech_id} | "
            f"{'PROPERTY_TESTING' if tech_id == 'TECH-0007' else 'TEST_TOOLING'} | "
            f"{'Hypothesis' if tech_id == 'TECH-0007' else 'Python unittest'} | "
            f"{property_version_policy if tech_id == 'TECH-0007' else 'MINIMUM: 3.11'} | "
            "REPOSITORY_FACT | REQ-0001, DES-0001 | Selected for fixture validation | "
            "NONE | Run the exact validation command |"
        )
        for tech_id in tech_ids
    )
    property_section = ""
    if property_rows:
        property_section = (
            "### Property execution contract\n\n"
            "| Property ID | Framework TECH ID | Exact command | Run target/time bound | "
            "Seed or reproduction format | Evidence destination |\n"
            "|---|---|---|---|---|---|\n" + "\n".join(property_rows) + "\n\n"
        )
    prd_path.write_text(
        "# PRD\n\n"
        "### Technology and toolchain decision register\n\n"
        "| Decision ID | Concern | Selection | Version policy | Source | Basis IDs | Alternatives and rationale | Compatibility/migration | Validation |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        f"{rows}\n\n"
        f"{property_section}"
        "## Next section\n",
        encoding="utf-8",
    )
    return prd_path


def property_execution_values(
    property_id: str = "PROP-001",
    framework_tech_id: str = "TECH-0007",
    command: str = "python -m unittest tests.test_properties",
    run_bound: str = "MIN_CASES: 100; MAX_SECONDS: 30",
    seed_format: str = "integer seed; reproduce with the recorded --seed value",
    evidence_destination: str = "docs/project/VERIFY.md#property-based-test-evidence",
) -> tuple[str, task_waves.PropertyExecutionRow]:
    values = (
        property_id,
        framework_tech_id,
        command,
        run_bound,
        seed_format,
        evidence_destination,
    )
    return "| " + " | ".join(values) + " |", task_waves.PropertyExecutionRow(*values)


def write_gate_b_bound_project(
    root: Path,
    tasks_text: str,
) -> tuple[Path, Path]:
    """Write a canonical project whose Gate B hash binds the current PRD."""

    from tests import test_bootstrap_doctor as doctor_fixtures

    tasks_path = root / "docs" / "project" / "TASKS.md"
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    tasks_path.write_text(tasks_text, encoding="utf-8")
    prd = (REPOSITORY_ROOT / "docs" / "project" / "PRD.md").read_text(encoding="utf-8")
    # This synthetic approval fixture activates only PROP-001. Remove the
    # template's other candidate property definitions so the approved contract
    # has an exact applicability/definition/execution inverse mapping.
    prd = (
        "\n".join(
            line
            for line in prd.splitlines()
            if not any(
                line.startswith(f"| PROP-{number:03d} |") for number in range(2, 6)
            )
        )
        + "\n"
    )
    prd = doctor_fixtures.approve_gate_b(doctor_fixtures.approve_gate_a(prd))
    (tasks_path.parent / "PRD.md").write_text(prd, encoding="utf-8")
    (root / "bootstrap.manifest.json").write_text("{}\n", encoding="utf-8")
    return tasks_path, write_matching_state(root, tasks_text)


def harness_execution_values(
    harness_id: str = "HARNESS-001",
    *,
    command: str = "python -m unittest tests.test_unit",
) -> tuple[str, task_waves.HarnessExecutionRow]:
    values = (
        harness_id,
        "UNIT",
        "Python unittest",
        "Before task completion",
        "REQ-0001, DES-0001, TECH-0001",
        command,
        "docs/project/VERIFY.md#harness-execution-evidence",
        "REQUIRED",
    )
    return "| " + " | ".join(values) + " |", task_waves.HarnessExecutionRow(*values)


def walking_harness_values() -> tuple[str, task_waves.HarnessExecutionRow]:
    values = (
        "HARNESS-900",
        "End-to-end",
        "Walking-skeleton journey check",
        "Before first-wave completion",
        "REQ-0001, DES-0001, JOURNEY-001, FR-001",
        "python -m unittest tests.test_walking_skeleton",
        "docs/project/VERIFY.md#harness-execution-evidence",
        "REQUIRED",
    )
    return "| " + " | ".join(values) + " |", task_waves.HarnessExecutionRow(*values)


def new_build_delivery_contract(
    *,
    spike: bool = False,
    grandfathered: bool = False,
) -> task_waves.ApprovedDeliveryContract:
    approved_spike = (
        task_waves.ApprovedSpikeContract(
            spike_id="SPIKE-001",
            max_attempts=2,
            disposable_boundaries=("scratch/**",),
            exit_criterion="python -m unittest tests.test_spike_exit",
        )
        if spike
        else None
    )
    return task_waves.ApprovedDeliveryContract(
        grandfathered=grandfathered,
        wave_contract_id=None if grandfathered else "WAVE-001",
        journey_id=None if grandfathered else "JOURNEY-001",
        requirement_ids=() if grandfathered else ("FR-001",),
        acceptance_test_ids=() if grandfathered else ("AC-FR-001",),
        harness_id=None if grandfathered else "HARNESS-900",
        spike=approved_spike,
    )


def walking_task_block(
    *,
    task_id: str = "TASK-001",
    status: str = "READY",
    dependencies: str = "NONE",
) -> str:
    row, harness = walking_harness_values()
    return task_block(
        task_id,
        status,
        dependencies,
        requirements=("REQ-0001, FR-001, AC-FR-001, JOURNEY-001, WAVE-001"),
        validation_command=harness.exact_command,
        harness_projection_rows=(row,),
    )


def spike_task_block(
    *,
    status: str = "READY",
    dependencies: str = "NONE",
    attempt_budget: int = 2,
    write_set: str = "scratch/probe.txt",
    external_state: str = "NONE",
    aws_mode: str = "NONE",
    validation_command: str = "python -m unittest tests.test_spike_exit",
) -> str:
    return task_block(
        "TASK-001",
        status,
        dependencies,
        requirements="REQ-0001, SPIKE-001",
        attempt_budget=attempt_budget,
        write_set=write_set,
        external_state=external_state,
        aws_mode=aws_mode,
        validation_command=validation_command,
    )


def harness_evidence_row(
    *,
    evidence_id: str,
    status: str,
    observed_at: str,
    observed_result: str,
    harness_id: str = "HARNESS-001",
    command: str = "python -m unittest tests.test_unit",
) -> str:
    return (
        f"| {evidence_id} | {harness_id} | UNIT | "
        "TASK-001, REQ-0001, DES-0001, AUTH-0001, TECH-0001 | "
        f"{command} | Worktree abc1234 | {observed_result} | {observed_at} | "
        f"docs/project/VERIFY.md#{evidence_id.lower()} | {status} |"
    )


def harness_evidence_document(*rows: str) -> str:
    return (
        "## Harness execution evidence\n\n"
        "| Evidence ID | Harness ID | Layer | Basis IDs | Exact command or API | "
        "Artifact / environment | Observed result | Observed at | Durable source | Status |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n"
    )


def property_evidence_row(
    *,
    evidence_id: str = "EV-1001",
    task_id: str = "TASK-001",
    result: str = "PASS",
    command: str = "python -m unittest tests.test_properties",
    counterexample: str = "NONE",
    failure: str = "NONE",
    observed_at: str = "2026-07-17T00:00:00+00:00",
    observed_version: str = "6.112.1",
) -> str:
    return (
        f"| {evidence_id} | {task_id} | REQ-0001 / DES-0001 / AUTH-0001 | "
        f"PROP-001 | TECH-0007 | Hypothesis | {observed_version} | "
        f"{command} | CASES: 100; ELAPSED_SECONDS: 0.50 | SEED: 12345 | "
        f"{counterexample} | {failure} | {result} | {observed_at} | Worktree: abc1234; "
        "artifact: tests/artifacts/property-PROP-001.json | "
        "tests/artifacts/property-PROP-001.json |"
    )


def property_evidence_document(*rows: str) -> str:
    content = rows or (property_evidence_row(),)
    return (
        "\n## Property-based test evidence\n\n"
        "| Evidence ID | Task ID | REQ / DES / AUTH | Property ID | Framework TECH ID | Framework selection | Observed exact version | Exact command | Observed run | Replay seed or exact command | Minimized counterexample | Failure class / resolution | Result | Observed at | Commit / worktree / artifact | Durable source |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        + "\n".join(content)
        + "\n"
    )


def observed_task_text(text: str, *, count: int = 1) -> str:
    for _index in range(count):
        text = text.replace("- [ ]", "- [x]", 1)
        text = text.replace(
            "Not started.",
            "2026-07-17T00:00:00+00:00 coordinator observed validation pass.",
            1,
        )
    return text


def checkpoint_row(
    checkpoint_id: str,
    *,
    commit: str = "abc1234",
    dirty: str = "NONE",
    outcomes: str = "TASK-001 DONE attempts=1/2",
    evidence: str = "EV-0001",
    next_action: str = "resume or complete",
) -> str:
    return (
        f"| `{checkpoint_id}` | `RUN-0001` | 2026-07-17T00:00:00+00:00 | "
        f"`REQ-0001` / `DES-0001` / `AUTH-0001` | Commit: `{commit}`; Dirty: {dirty} | "
        f"{outcomes} | Evidence: {evidence}; External: NONE | "
        f"Blockers: NONE; Next: {next_action} |"
    )


def completion_evidence_row(
    *,
    evidence_id: str = "EV-0001",
    task_id: str = "TASK-001",
    command_or_observation: str = "python -m unittest tests.test_task_waves",
    result: str = "exit=0; 37 tests passed",
    actor: str = "codex-coordinator",
    observed_at: str = "2026-07-17T00:00:00+00:00",
    material: str = "Commit: abc1234",
    durable_source: str = "VERIFY.md#ev-0001",
    status: str = "LOCAL_PASS",
) -> str:
    return (
        f"| `{evidence_id}` | `{task_id}` | {command_or_observation} | {result} | "
        f"`{actor}` | {observed_at} | {material} | {durable_source} | `{status}` |"
    )


def completion_evidence_document(*rows: str) -> str:
    content = rows or (completion_evidence_row(),)
    return (
        "# Verification\n\n"
        "## Task completion evidence\n\n"
        "| Evidence ID | Task | Command or observation | Result | Actor | Observed at | Commit / worktree / artifact | Durable source | Status |\n"
        "|---|---|---|---|---|---|---|---|---|\n" + "\n".join(content) + "\n"
    )


def append_checkpoint(tasks_text: str, row: str) -> str:
    marker = "\n\n## Task definitions\n\n"
    if marker not in tasks_text:
        raise AssertionError("Task definitions marker is missing")
    return tasks_text.replace(marker, "\n" + row + marker, 1)


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def initialize_git(root: Path) -> str:
    git(root, "init", "-q")
    git(root, "config", "user.email", "tests@example.com")
    git(root, "config", "user.name", "Fastlane Tests")
    marker = root / "base.txt"
    marker.write_text("base\n", encoding="utf-8")
    git(root, "add", "base.txt")
    git(root, "commit", "-qm", "base")
    return git(root, "rev-parse", "HEAD")


class TaskWaveSafetyTests(unittest.TestCase):
    def test_generated_summary_cannot_inject_task_or_snapshot_records(self) -> None:
        canonical = document([task_block("TASK-001", "READY")])
        injected = (
            "<!-- FASTLANE:DOCUMENT_SUMMARY:BEGIN -->\n"
            + snapshot(task_plan="PLAN-9999")
            + task_block("TASK-999", "READY")
            + "<!-- FASTLANE:DOCUMENT_SUMMARY:END -->\n"
            + canonical
        )
        tasks = task_waves.parse_tasks(injected)
        observed = task_waves.parse_snapshot(injected)
        self.assertEqual([task.task_id for task in tasks], ["TASK-001"])
        self.assertEqual(observed.get("Task-plan revision"), "PLAN-0001")
        self.assertEqual(
            len(task_waves.strip_generated_summary(injected)), len(injected)
        )

    def test_canonical_project_ledger_resolves_root_state_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path = root / "docs" / "project" / "TASKS.md"
            tasks_path.parent.mkdir(parents=True)
            state_path = root / "bootstrap.yaml"
            state_path.write_text(
                json.dumps({"lifecycle": {}, "execution": {}}),
                encoding="utf-8",
            )

            observed_state_path, _state = task_waves.read_bootstrap_state(tasks_path)

            self.assertEqual(observed_state_path, state_path.resolve())
            self.assertEqual(
                task_waves.project_root_for_tasks(tasks_path), root.resolve()
            )
            self.assertEqual(
                task_waves.coordinator_ledger_paths(tasks_path),
                {
                    "bootstrap.yaml",
                    "docs/project/TASKS.md",
                    "docs/project/VERIFY.md",
                },
            )
            self.assertEqual(
                task_waves.canonical_verify_reference(tasks_path, "cp-0001"),
                "docs/project/VERIFY.md#cp-0001",
            )

    def test_ready_selects_only_explicit_ready_tasks(self) -> None:
        text = document(
            [
                task_block("TASK-001", "BACKLOG"),
                task_block("TASK-002", "READY"),
                task_block("TASK-003", "DONE"),
                task_block("TASK-004", "READY", "TASK-001"),
            ]
        )
        tasks, _snap, waivers, by_id = parse_document(text)

        selected = task_waves.ready_tasks(tasks, by_id, waivers)

        self.assertEqual([task.task_id for task in selected], ["TASK-002"])

    def test_human_first_collapsed_metadata_remains_parser_compatible(self) -> None:
        block = """### TASK-9001 - Human-first task

- Status: `READY`
- Owner: `UNASSIGNED`
- Blocker: `NONE`
- GitHub issue: `PENDING_SYNC`

#### Outcome

The approved behavior is observable.

#### Acceptance criteria

- [ ] The observable result matches FR-001.

#### Validation

```bash
python -m unittest
```

#### Execution log

Not started.

#### Agent execution details

<details>
<summary>Exact metadata used by Codex and task_waves.py</summary>

- Requirements: `REQ-0001, FR-001`
- Design: `DES-0001; TECH: TECH-0001`
- Authorization: `AUTH-0001`
- Depends on: `NONE`
- Dependency waivers: `NONE`
- Run ID: `NONE`
- Risk: `LOW`
- Write set: `app/task-9001.py`
- External state: `NONE`
- AWS mode: `NONE`
- Attempt budget: `2`
- Attempts used: `0`
- Evidence: `NONE`
- Skip record: `NONE`
- Last checkpoint: `NONE`
- Last updated: `2026-07-17T00:00:00+00:00`

</details>

"""
        tasks, _snap, waivers, by_id = parse_document(document([block]))

        self.assertEqual(set(tasks[0].metadata), set(task_waves.REQUIRED_METADATA))
        self.assertNotIn("Technologies", task_waves.REQUIRED_METADATA)
        self.assertEqual(
            [task.task_id for task in task_waves.ready_tasks(tasks, by_id, waivers)],
            ["TASK-9001"],
        )

    def test_new_build_walking_skeleton_is_the_only_first_wave(self) -> None:
        row, harness = walking_harness_values()
        text = document(
            [
                walking_task_block(),
                task_block("TASK-002", "BACKLOG", "TASK-001"),
            ]
        )
        tasks = task_waves.parse_tasks(text)
        snap = task_waves.parse_snapshot(text)

        by_id = task_waves.validate(
            tasks,
            snap,
            approved_harness={harness.harness_id: harness},
            approved_delivery=new_build_delivery_contract(),
        )

        self.assertEqual(
            task_waves.compute_waves(tasks, by_id),
            {
                "TASK-001": 1,
                "TASK-002": 2,
            },
        )
        self.assertEqual(set(tasks[0].metadata), set(task_waves.REQUIRED_METADATA))
        self.assertNotIn("Wave contract", task_waves.REQUIRED_METADATA)
        self.assertIn(row, tasks[0].block)

    def test_legacy_gate_a_schema_five_wave_needs_no_invented_journey(self) -> None:
        row, harness = walking_harness_values()
        text = document(
            [
                task_block(
                    "TASK-001",
                    "READY",
                    requirements="REQ-0001, FR-001, AC-FR-001, WAVE-001",
                    validation_command=harness.exact_command,
                    harness_projection_rows=(row,),
                ),
                task_block("TASK-002", "BACKLOG", "TASK-001"),
            ]
        )
        delivery = task_waves.ApprovedDeliveryContract(
            grandfathered=False,
            wave_contract_id="WAVE-001",
            journey_id=None,
            requirement_ids=("FR-001",),
            acceptance_test_ids=("AC-FR-001",),
            harness_id=harness.harness_id,
        )
        tasks = task_waves.parse_tasks(text)
        snapshot = task_waves.parse_snapshot(text)
        by_id = task_waves.validate(
            tasks,
            snapshot,
            approved_harness={harness.harness_id: harness},
            approved_delivery=delivery,
        )
        self.assertEqual(task_waves.compute_waves(tasks, by_id)["TASK-001"], 1)
        self.assertNotIn("JOURNEY-", tasks[0].metadata["Requirements"])
        self.assertNotIn("NONE", tasks[0].metadata["Requirements"])

    def test_new_build_delivery_contract_rejects_missing_duplicate_and_bypassed_walk(
        self,
    ) -> None:
        _row, harness = walking_harness_values()
        approved_harness = {harness.harness_id: harness}
        delivery = new_build_delivery_contract()

        missing = document([task_block("TASK-001", "READY")])
        with self.assertRaisesRegex(
            ValueError, "requires exactly one walking-skeleton task; found 0"
        ):
            task_waves.validate(
                task_waves.parse_tasks(missing),
                task_waves.parse_snapshot(missing),
                approved_harness=approved_harness,
                approved_delivery=delivery,
            )

        duplicate = document(
            [
                walking_task_block(),
                walking_task_block(
                    task_id="TASK-002",
                    dependencies="TASK-001",
                ),
            ]
        )
        with self.assertRaisesRegex(
            ValueError, "requires exactly one walking-skeleton task; found 2"
        ):
            task_waves.validate(
                task_waves.parse_tasks(duplicate),
                task_waves.parse_snapshot(duplicate),
                approved_harness=approved_harness,
                approved_delivery=delivery,
            )

        peer_root = document(
            [
                walking_task_block(),
                task_block("TASK-002", "READY"),
            ]
        )
        with self.assertRaisesRegex(ValueError, "sole active structural wave 1"):
            task_waves.validate(
                task_waves.parse_tasks(peer_root),
                task_waves.parse_snapshot(peer_root),
                approved_harness=approved_harness,
                approved_delivery=delivery,
            )

        later_harness_row, _later_harness = walking_harness_values()
        wrong_harness_owner = document(
            [
                task_block(
                    "TASK-001",
                    "READY",
                    requirements=("REQ-0001, FR-001, AC-FR-001, JOURNEY-001, WAVE-001"),
                ),
                task_block(
                    "TASK-002",
                    "BACKLOG",
                    "TASK-001",
                    validation_command=harness.exact_command,
                    harness_projection_rows=(later_harness_row,),
                ),
            ]
        )
        with self.assertRaisesRegex(
            ValueError, "walking-skeleton Validation must own approved end-to-end"
        ):
            task_waves.validate(
                task_waves.parse_tasks(wrong_harness_owner),
                task_waves.parse_snapshot(wrong_harness_owner),
                approved_harness=approved_harness,
                approved_delivery=delivery,
            )

    def test_new_build_allows_one_bounded_spike_before_the_walking_skeleton(
        self,
    ) -> None:
        _row, harness = walking_harness_values()
        text = document(
            [
                spike_task_block(),
                walking_task_block(task_id="TASK-002", dependencies="TASK-001"),
                task_block("TASK-003", "BACKLOG", "TASK-002"),
            ]
        )
        tasks = task_waves.parse_tasks(text)
        snap = task_waves.parse_snapshot(text)

        by_id = task_waves.validate(
            tasks,
            snap,
            approved_harness={harness.harness_id: harness},
            approved_delivery=new_build_delivery_contract(spike=True),
        )

        self.assertEqual(
            task_waves.compute_waves(tasks, by_id),
            {
                "TASK-001": 1,
                "TASK-002": 2,
                "TASK-003": 3,
            },
        )

    def test_bounded_spike_rejects_scope_authority_and_sequence_violations(
        self,
    ) -> None:
        _row, harness = walking_harness_values()
        approved_harness = {harness.harness_id: harness}
        delivery = new_build_delivery_contract(spike=True)

        cases = (
            (
                "attempt budget",
                spike_task_block(attempt_budget=3),
                "Attempt budget exceeds approved",
            ),
            (
                "write boundary",
                spike_task_block(write_set="app/probe.py"),
                "Write set exceeds the approved disposable boundary",
            ),
            (
                "external state",
                spike_task_block(external_state="github:issue:1"),
                "blocking spike requires External state NONE",
            ),
            (
                "aws mode",
                spike_task_block(aws_mode="READ_ONLY"),
                "blocking spike AWS mode must be NONE or DOCS_ONLY",
            ),
            (
                "missing exit",
                spike_task_block(validation_command="python -m unittest tests.other"),
                "exit criterion must appear unchanged exactly once",
            ),
            (
                "duplicate exit",
                spike_task_block(
                    validation_command=(
                        "python -m unittest tests.test_spike_exit\n"
                        "python -m unittest tests.test_spike_exit"
                    )
                ),
                "exit criterion must appear unchanged exactly once",
            ),
        )
        for label, spike_block, message in cases:
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, message):
                text = document(
                    [
                        spike_block,
                        walking_task_block(
                            task_id="TASK-002",
                            dependencies="TASK-001",
                        ),
                    ]
                )
                task_waves.validate(
                    task_waves.parse_tasks(text),
                    task_waves.parse_snapshot(text),
                    approved_harness=approved_harness,
                    approved_delivery=delivery,
                )

        bypass = document(
            [
                spike_task_block(),
                walking_task_block(task_id="TASK-002", dependencies="TASK-001"),
                task_block("TASK-003", "BACKLOG", "TASK-001"),
            ]
        )
        with self.assertRaisesRegex(
            ValueError, "walking skeleton must be the sole active structural wave 2"
        ):
            task_waves.validate(
                task_waves.parse_tasks(bypass),
                task_waves.parse_snapshot(bypass),
                approved_harness=approved_harness,
                approved_delivery=delivery,
            )

    def test_walking_skeleton_and_blocking_spike_cannot_be_skipped(self) -> None:
        _row, harness = walking_harness_values()
        approved_harness = {harness.harness_id: harness}

        skipped_walk = document([walking_task_block(status="SKIPPED")])
        with self.assertRaisesRegex(
            ValueError, "walking-skeleton task cannot be SKIPPED"
        ):
            task_waves.validate(
                task_waves.parse_tasks(skipped_walk),
                task_waves.parse_snapshot(skipped_walk),
                approved_harness=approved_harness,
                approved_delivery=new_build_delivery_contract(),
            )

        skipped_spike = document(
            [
                spike_task_block(status="SKIPPED"),
                walking_task_block(task_id="TASK-002", dependencies="TASK-001"),
            ]
        )
        with self.assertRaisesRegex(ValueError, "blocking spike cannot be SKIPPED"):
            task_waves.validate(
                task_waves.parse_tasks(skipped_spike),
                task_waves.parse_snapshot(skipped_spike),
                approved_harness=approved_harness,
                approved_delivery=new_build_delivery_contract(spike=True),
            )

    def test_current_plan_requires_exact_requirement_acceptance_pair(self) -> None:
        text = document([task_block("TASK-001", "READY")])

        with self.assertRaisesRegex(ValueError, "AC-FR-001"):
            task_waves.validate(
                task_waves.parse_tasks(text),
                task_waves.parse_snapshot(text),
                approved_requirement_rules={"FR-001": ("AC-FR-001", "UBIQUITOUS")},
                approved_requirement_evidence={},
            )

    def test_current_plan_accepts_already_satisfied_requirement_evidence(
        self,
    ) -> None:
        text = document([task_block("TASK-001", "READY", requirements="REQ-0001")])

        task_waves.validate(
            task_waves.parse_tasks(text),
            task_waves.parse_snapshot(text),
            approved_requirement_rules={"FR-001": ("AC-FR-001", "UBIQUITOUS")},
            approved_requirement_evidence={
                "FR-001": ("ALREADY_SATISFIED", ("EV-0001",))
            },
        )

    def test_approved_contract_loads_current_requirement_coverage_inputs(
        self,
    ) -> None:
        text = document([task_block("TASK-001", "READY")])

        with tempfile.TemporaryDirectory() as directory:
            tasks_path, _state_path = write_gate_b_bound_project(Path(directory), text)
            contract = task_waves.approved_contract_for_tasks(tasks_path, text)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertIsNotNone(contract.requirement_rules)
        assert contract.requirement_rules is not None
        self.assertEqual(
            contract.requirement_rules["FR-001"][0],
            "AC-FR-001",
        )
        self.assertEqual(contract.requirement_evidence, {})
        kwargs = task_waves.execution_contract_kwargs(contract)
        self.assertIs(kwargs["approved_requirement_rules"], contract.requirement_rules)
        self.assertIs(
            kwargs["approved_requirement_evidence"], contract.requirement_evidence
        )

    def test_skipping_last_requirement_covering_task_is_atomic(self) -> None:
        text = document(
            [
                task_block(
                    "TASK-001",
                    "READY",
                    requirements="REQ-0001, FR-001, AC-FR-001",
                )
            ],
            snapshot_text=snapshot(
                run_state="RUNNING",
                run_id="RUN-0001",
                coordinator="lead",
            ),
        )
        approved = task_waves.ApprovedTaskContract(
            technology_ids=frozenset({"TECH-0001"}),
            property_execution={},
            harness={},
            requirement_rules={"FR-001": ("AC-FR-001", "UBIQUITOUS")},
            requirement_evidence={},
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path, state_path = write_task_project(root, text)
            original_tasks = tasks_path.read_bytes()
            original_state = state_path.read_bytes()

            with (
                mock.patch.object(
                    task_waves,
                    "approved_contract_for_tasks",
                    return_value=approved,
                ),
                self.assertRaisesRegex(ValueError, "FR-001"),
            ):
                task_waves.mutate_task_file(
                    tasks_path,
                    "TASK-001",
                    {"Skip record": "SKIP-001"},
                    coordinator="lead",
                    new_status="SKIPPED",
                )

            self.assertEqual(tasks_path.read_bytes(), original_tasks)
            self.assertEqual(state_path.read_bytes(), original_state)

    def test_invalid_delivery_graph_is_rejected_before_mutation_writes(self) -> None:
        _row, harness = walking_harness_values()
        text = document(
            [
                walking_task_block(),
                task_block("TASK-002", "READY"),
            ]
        )
        approved = task_waves.ApprovedTaskContract(
            technology_ids=frozenset({"TECH-0001"}),
            property_execution={},
            harness={harness.harness_id: harness},
            delivery=new_build_delivery_contract(),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path, state_path = write_task_project(root, text)
            original_tasks = tasks_path.read_bytes()
            original_state = state_path.read_bytes()

            with (
                mock.patch.object(
                    task_waves,
                    "approved_contract_for_tasks",
                    return_value=approved,
                ),
                self.assertRaisesRegex(ValueError, "sole active structural wave 1"),
            ):
                task_waves.mutate_run_snapshot(
                    tasks_path,
                    operation="start",
                    run_id="RUN-0001",
                    coordinator="lead",
                    run_mode="AUTONOMOUS",
                )

            self.assertEqual(tasks_path.read_bytes(), original_tasks)
            self.assertEqual(state_path.read_bytes(), original_state)

    def test_delivery_order_is_noop_for_non_new_build_and_grandfathered_designs(
        self,
    ) -> None:
        text = document(
            [
                task_block("TASK-001", "READY"),
                task_block("TASK-002", "READY"),
            ]
        )
        tasks = task_waves.parse_tasks(text)
        snap = task_waves.parse_snapshot(text)

        task_waves.validate(
            tasks,
            snap,
            approved_delivery=task_waves.ApprovedDeliveryContract(grandfathered=False),
        )
        task_waves.validate(
            tasks,
            snap,
            approved_delivery=new_build_delivery_contract(grandfathered=True),
        )

    def test_design_trace_parses_and_serializes_technology_refs(self) -> None:
        task = task_waves.parse_tasks(
            task_block(
                "TASK-001",
                "READY",
                design="DES-0001; TECH: TECH-0001, TECH-0002",
            )
        )[0]

        task_waves.validate([task])

        self.assertEqual(task.design_revision, "DES-0001")
        self.assertEqual(task.technology_refs, ["TECH-0001", "TECH-0002"])
        self.assertEqual(
            task_waves.task_to_dict(task, 1)["technology_refs"],
            ["TECH-0001", "TECH-0002"],
        )

        no_impact = task_waves.parse_tasks(
            task_block(
                "TASK-002",
                "READY",
                design="DES-0001; TECH: NONE — no technology/toolchain impact",
            )
        )[0]
        task_waves.validate([no_impact])
        self.assertEqual(no_impact.technology_refs, [])
        self.assertEqual(task_waves.task_to_dict(no_impact, 1)["technology_refs"], [])

    def test_executable_and_terminal_tasks_require_exact_design_trace_grammar(
        self,
    ) -> None:
        malformed_values = (
            "DES-0001, Section 10",
            "DES-0001; TECH: TECH-0001,TECH-0002",
            "DES-0001; TECH: TECH-nnnn",
            "DES-0001; TECH: NONE",
            "DES-0001; TECH: NONE — no technology/toolchain impact, TECH-0001",
        )
        for status in ("READY", "IN_PROGRESS", "BLOCKED", "DONE"):
            for design in malformed_values:
                with (
                    self.subTest(status=status, design=design),
                    self.assertRaisesRegex(ValueError, "Design must exactly match"),
                ):
                    task_waves.validate(
                        task_waves.parse_tasks(
                            task_block("TASK-001", status, design=design)
                        )
                    )

        backlog = task_waves.parse_tasks(
            task_block("TASK-001", "BACKLOG", design="TODO")
        )
        task_waves.validate(backlog)
        self.assertEqual(task_waves.ready_tasks(backlog, {"TASK-001": backlog[0]}), [])

    def test_design_trace_rejects_duplicate_or_unapproved_tech_ids(self) -> None:
        duplicate = task_waves.parse_tasks(
            task_block(
                "TASK-001",
                "READY",
                design="DES-0001; TECH: TECH-0001, TECH-0001",
            )
        )
        with self.assertRaisesRegex(ValueError, "duplicate TECH reference"):
            task_waves.validate(duplicate)

        task = task_waves.parse_tasks(
            task_block(
                "TASK-001",
                "READY",
                design="DES-0001; TECH: TECH-0001, TECH-0002",
            )
        )
        task_waves.validate(
            task,
            approved_tech_ids={"TECH-0001", "TECH-0002"},
        )
        with self.assertRaisesRegex(ValueError, "unapproved TECH IDs: TECH-0002"):
            task_waves.validate(task, approved_tech_ids={"TECH-0001"})

    def test_property_projection_is_exact_for_every_executable_status(self) -> None:
        row, execution = property_execution_values()
        approved = {execution.property_id: execution}
        for status in ("READY", "IN_PROGRESS", "BLOCKED", "DONE"):
            with self.subTest(status=status):
                task = task_waves.parse_tasks(
                    task_block(
                        "TASK-001",
                        status,
                        requirements="REQ-0001, FR-001, PROP-001",
                        design="DES-0001; TECH: TECH-0001, TECH-0007",
                        validation_command=execution.exact_command,
                        property_execution_rows=(row,),
                    )
                )
                task_waves.validate(
                    task,
                    approved_tech_ids={"TECH-0001", "TECH-0007"},
                    approved_property_execution=approved,
                )

    def test_required_harness_projects_to_exactly_one_task(self) -> None:
        row, approved_row = harness_execution_values()
        task = task_waves.parse_tasks(
            task_block(
                "TASK-001",
                "READY",
                validation_command=approved_row.exact_command,
                harness_projection_rows=(row,),
            )
        )
        self.assertEqual(
            task_waves.validate_harness_projections(
                task,
                {approved_row.harness_id: approved_row},
                current_plan=True,
            ),
            [],
        )

        duplicate_tasks = task_waves.parse_tasks(
            document(
                [
                    task_block(
                        "TASK-001",
                        "READY",
                        validation_command=approved_row.exact_command,
                        harness_projection_rows=(row,),
                    ),
                    task_block(
                        "TASK-002",
                        "READY",
                        validation_command=approved_row.exact_command,
                        harness_projection_rows=(row,),
                    ),
                ]
            )
        )
        errors = task_waves.validate_harness_projections(
            duplicate_tasks,
            {approved_row.harness_id: approved_row},
            current_plan=True,
        )
        self.assertTrue(
            any("exactly one owning task; found 2" in error for error in errors),
            errors,
        )

    def test_harness_projection_rejects_changed_command(self) -> None:
        row, approved_row = harness_execution_values()
        changed = "python -m unittest tests.test_other"
        altered = row.replace(approved_row.exact_command, changed, 1)
        task = task_waves.parse_tasks(
            task_block(
                "TASK-001",
                "READY",
                validation_command=changed,
                harness_projection_rows=(altered,),
            )
        )
        errors = task_waves.validate_harness_projections(
            task,
            {approved_row.harness_id: approved_row},
            current_plan=True,
        )
        self.assertTrue(
            any(
                "does not match the approved PRD Harness row" in error
                for error in errors
            ),
            errors,
        )

    def test_harness_done_requires_latest_pass_and_preserves_failure(self) -> None:
        row, approved_row = harness_execution_values()
        failed = harness_evidence_row(
            evidence_id="EV-2001",
            status="FAILED",
            observed_at="2026-07-17T00:00:00+00:00",
            observed_result="exit=1; assertion failed",
        )
        passed = harness_evidence_row(
            evidence_id="EV-2002",
            status="LOCAL_PASS",
            observed_at="2026-07-17T00:01:00+00:00",
            observed_result="exit=0; 12 tests passed",
        )
        task = task_waves.parse_tasks(
            task_block(
                "TASK-001",
                "DONE",
                evidence="EV-2002",
                validation_command=approved_row.exact_command,
                harness_projection_rows=(row,),
            )
        )[0]
        snap = task_waves.parse_snapshot(document([task.block]))

        with self.assertRaisesRegex(
            ValueError, "latest observation must be a current PASS"
        ):
            task_waves.validate_done_harness_evidence(
                harness_evidence_document(failed),
                task,
                snap,
                {approved_row.harness_id: approved_row},
            )

        task_waves.validate_done_harness_evidence(
            harness_evidence_document(failed, passed),
            task,
            snap,
            {approved_row.harness_id: approved_row},
        )
        parsed = task_waves.parse_harness_evidence(
            harness_evidence_document(failed, passed)
        )
        self.assertEqual([item.status for item in parsed], ["FAILED", "LOCAL_PASS"])

    def test_property_execution_rejects_sentinels_and_prose_commands(self) -> None:
        headers = (
            "| Property ID | Framework TECH ID | Exact command | Run target/time bound | "
            "Seed or reproduction format | Evidence destination |\n"
            "|---|---|---|---|---|---|\n"
        )
        execution = property_execution_values()[1]
        valid_values = [
            execution.property_id,
            execution.framework_tech_id,
            execution.exact_command,
            execution.run_target_time_bound,
            execution.seed_or_reproduction_format,
            execution.evidence_destination,
        ]
        semantic_indexes = range(2, 6)
        for sentinel in ("NONE", "PENDING", "PLACEHOLDER"):
            for index in semantic_indexes:
                with self.subTest(sentinel=sentinel, column=index):
                    values = valid_values.copy()
                    values[index] = sentinel
                    with self.assertRaisesRegex(
                        ValueError, "property execution row is unresolved"
                    ):
                        task_waves.parse_property_execution_rows(
                            headers + "| " + " | ".join(values) + " |\n",
                            "test contract",
                        )

        for prose in (
            "Run the exact property tests",
            "Execute the validation command",
            "The exact command",
        ):
            with self.subTest(prose=prose):
                values = valid_values.copy()
                values[2] = prose
                with self.assertRaisesRegex(
                    ValueError, "Exact command must be a concrete command"
                ):
                    task_waves.parse_property_execution_rows(
                        headers + "| " + " | ".join(values) + " |\n",
                        "test contract",
                    )

        bad_row, bad_execution = property_execution_values(command="NONE")
        bad_task = task_waves.parse_tasks(
            task_block(
                "TASK-001",
                "READY",
                requirements="REQ-0001, FR-001, PROP-001",
                design="DES-0001; TECH: TECH-0001, TECH-0007",
                validation_command="NONE",
                property_execution_rows=(bad_row,),
            )
        )
        with self.assertRaisesRegex(ValueError, "property execution row is unresolved"):
            task_waves.validate(
                bad_task,
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                approved_property_execution={"PROP-001": bad_execution},
            )

    def test_property_projection_rejects_missing_altered_extra_and_duplicate_values(
        self,
    ) -> None:
        row, execution = property_execution_values()
        approved = {execution.property_id: execution}

        def validate_row(
            observed_rows: tuple[str, ...],
            *,
            requirements: str = "REQ-0001, FR-001, PROP-001",
            design: str = "DES-0001; TECH: TECH-0001, TECH-0007, TECH-0008",
            command: str = execution.exact_command,
            approved_rows: dict[str, task_waves.PropertyExecutionRow] = approved,
        ) -> None:
            task_waves.validate(
                task_waves.parse_tasks(
                    task_block(
                        "TASK-001",
                        "READY",
                        requirements=requirements,
                        design=design,
                        validation_command=command,
                        property_execution_rows=observed_rows,
                    )
                ),
                approved_tech_ids={"TECH-0001", "TECH-0007", "TECH-0008"},
                approved_property_execution=approved_rows,
            )

        with self.assertRaisesRegex(
            ValueError, "missing the property execution projection"
        ):
            validate_row(())

        alterations = (
            ("Framework TECH ID", row.replace("TECH-0007", "TECH-0008", 1)),
            (
                "Exact command",
                row.replace(
                    execution.exact_command, "python -m unittest tests.other", 1
                ),
            ),
            (
                "Run target/time bound",
                row.replace(
                    execution.run_target_time_bound,
                    "MIN_CASES: 101; MAX_SECONDS: 30",
                    1,
                ),
            ),
            (
                "Seed or reproduction format",
                row.replace(
                    execution.seed_or_reproduction_format,
                    "UUID seed; record exact value",
                    1,
                ),
            ),
            (
                "Evidence destination",
                row.replace(
                    execution.evidence_destination, "docs/project/VERIFY.md#other", 1
                ),
            ),
        )
        for label, altered in alterations:
            with (
                self.subTest(label=label),
                self.assertRaisesRegex(
                    ValueError, "does not exactly match the approved PRD row"
                ),
            ):
                validate_row((altered,))

        extra_row, extra_execution = property_execution_values(
            property_id="PROP-002",
            command="python -m unittest tests.test_other_properties",
        )
        with self.assertRaisesRegex(
            ValueError, "unreferenced property execution rows: PROP-002"
        ):
            validate_row(
                (row, extra_row),
                command=execution.exact_command + "\n" + extra_execution.exact_command,
                approved_rows={
                    execution.property_id: execution,
                    extra_execution.property_id: extra_execution,
                },
            )

        with self.assertRaisesRegex(
            ValueError, "duplicate property execution ID PROP-001"
        ):
            validate_row((row, row))

        with self.assertRaisesRegex(ValueError, "found 2"):
            validate_row(
                (row,),
                command=execution.exact_command + "\n" + execution.exact_command,
            )

        with self.assertRaisesRegex(
            ValueError, "Framework TECH ID is missing from Design"
        ):
            validate_row((row,), design="DES-0001; TECH: TECH-0001")

    def test_property_projection_order_matches_requirements(self) -> None:
        row_one, execution_one = property_execution_values()
        row_two, execution_two = property_execution_values(
            property_id="PROP-002",
            command="python -m unittest tests.test_other_properties",
        )
        task = task_waves.parse_tasks(
            task_block(
                "TASK-001",
                "READY",
                requirements="REQ-0001, FR-001, PROP-001, PROP-002",
                design="DES-0001; TECH: TECH-0001, TECH-0007",
                validation_command=(
                    execution_one.exact_command + "\n" + execution_two.exact_command
                ),
                property_execution_rows=(row_two, row_one),
            )
        )
        with self.assertRaisesRegex(
            ValueError, "order must exactly match Requirements"
        ):
            task_waves.validate(
                task,
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                approved_property_execution={
                    execution_one.property_id: execution_one,
                    execution_two.property_id: execution_two,
                },
            )

    def test_current_plan_requires_aggregate_property_coverage(self) -> None:
        row, execution = property_execution_values()
        approved = {execution.property_id: execution}
        tasks = task_waves.parse_tasks(document([task_block("TASK-001", "READY")]))
        snap = task_waves.parse_snapshot(document([task_block("TASK-001", "READY")]))
        with self.assertRaisesRegex(
            ValueError, "does not cover approved property execution IDs: PROP-001"
        ):
            task_waves.validate(
                tasks,
                snap,
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                approved_property_execution=approved,
            )

        malformed_blocked = document(
            [
                task_block(
                    "TASK-001",
                    "BLOCKED",
                    requirements="REQ-0001, FR-001, PROP-001",
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                )
            ]
        )
        with self.assertRaisesRegex(
            ValueError, "missing the property execution projection"
        ):
            task_waves.validate(
                task_waves.parse_tasks(malformed_blocked),
                task_waves.parse_snapshot(malformed_blocked),
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                approved_property_execution=approved,
            )

        repeated = document(
            [
                task_block(
                    task_id,
                    "READY",
                    requirements="REQ-0001, FR-001, PROP-001",
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    validation_command=execution.exact_command,
                    property_execution_rows=(row,),
                )
                for task_id in ("TASK-001", "TASK-002")
            ]
        )
        task_waves.validate(
            task_waves.parse_tasks(repeated),
            task_waves.parse_snapshot(repeated),
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            approved_property_execution=approved,
        )

        skipped_only = document(
            [
                task_block(
                    "TASK-001",
                    "SKIPPED",
                    requirements="REQ-0001, FR-001, PROP-001",
                ),
            ]
        )
        with self.assertRaisesRegex(
            ValueError, "does not cover approved property execution IDs: PROP-001"
        ):
            task_waves.validate(
                task_waves.parse_tasks(skipped_only),
                task_waves.parse_snapshot(skipped_only),
                approved_tech_ids={"TECH-0001", "TECH-0007"},
                approved_property_execution=approved,
            )

    def test_resolved_backlog_property_counts_coverage_but_is_not_runnable(
        self,
    ) -> None:
        row, execution = property_execution_values()
        approved = {execution.property_id: execution}
        tasks_text = document(
            [
                task_block("TASK-001", "READY"),
                task_block(
                    "TASK-002",
                    "BACKLOG",
                    dependencies="TASK-001",
                    requirements="REQ-0001, FR-001, PROP-001",
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    validation_command=execution.exact_command,
                    property_execution_rows=(row,),
                ),
            ],
            snapshot_text=snapshot(
                run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
            ),
        )
        tasks = task_waves.parse_tasks(tasks_text)
        snap = task_waves.parse_snapshot(tasks_text)
        by_id = task_waves.validate(
            tasks,
            snap,
            approved_tech_ids={"TECH-0001", "TECH-0007"},
            approved_property_execution=approved,
        )
        self.assertEqual(
            [task.task_id for task in task_waves.ready_tasks(tasks, by_id)],
            ["TASK-001"],
        )
        with self.assertRaisesRegex(ValueError, "incomplete dependencies: TASK-001"):
            task_waves.validate_status_transition(by_id["TASK-002"], "READY", by_id)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "docs" / "project" / "TASKS.md"
            path.parent.mkdir(parents=True)
            path.write_text(tasks_text, encoding="utf-8")
            write_matching_state(root, tasks_text)
            write_technology_register(
                root, "TECH-0001", "TECH-0007", property_rows=(row,)
            )
            with self.assertRaisesRegex(ValueError, "only READY tasks may be claimed"):
                task_waves.claim_task_file(
                    path,
                    "TASK-002",
                    owner="lead",
                    coordinator="lead",
                    run_id="RUN-0001",
                    checkpoint="CP-0000",
                )

    def test_property_contract_survives_start_claim_and_status_preflight(self) -> None:
        row, execution = property_execution_values()
        tasks_text = document(
            [
                task_block(
                    "TASK-001",
                    "READY",
                    requirements="REQ-0001, FR-001, PROP-001",
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    validation_command=execution.exact_command,
                    property_execution_rows=(row,),
                )
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "docs" / "project" / "TASKS.md"
            path.parent.mkdir(parents=True)
            path.write_text(tasks_text, encoding="utf-8")
            write_matching_state(root, tasks_text)
            write_technology_register(
                root, "TECH-0001", "TECH-0007", property_rows=(row,)
            )
            _approved_ids, approved_properties = task_waves.approved_contract_values(
                path, tasks_text
            )
            self.assertIsNotNone(approved_properties)
            self.assertEqual(
                approved_properties["PROP-001"].framework_selection,
                "Hypothesis",
            )
            self.assertEqual(
                approved_properties["PROP-001"].framework_version_policy,
                "MINIMUM: 6.0",
            )

            task_waves.mutate_run_snapshot(
                path,
                operation="start",
                run_id="RUN-0001",
                coordinator="lead",
            )
            task_waves.claim_task_file(
                path,
                "TASK-001",
                owner="lead",
                coordinator="lead",
                run_id="RUN-0001",
                checkpoint="CP-0000",
            )
            task_waves.update_task_file(
                path,
                "TASK-001",
                coordinator="lead",
                status="BLOCKED",
                blocker="Observed dependency failure; route to DESIGN-10",
                run_id="RUN-0001",
                checkpoint="CP-0001",
            )
            self.assertEqual(
                task_waves.parse_tasks(path.read_text(encoding="utf-8"))[0].status,
                "BLOCKED",
            )

    def test_gate_b_design_hash_staleness_blocks_query_start_claim_and_status(
        self,
    ) -> None:
        row, execution = property_execution_values()

        def property_task(status: str, *, running: bool = False) -> str:
            return document(
                [
                    task_block(
                        "TASK-001",
                        status,
                        requirements="REQ-0001, FR-001, PROP-001",
                        design="DES-0001; TECH: TECH-0001, TECH-0007",
                        validation_command=execution.exact_command,
                        property_execution_rows=(row,),
                    )
                ],
                snapshot_text=snapshot(
                    run_state="RUNNING" if running else "NOT_STARTED",
                    run_id="RUN-0001" if running else "NONE",
                    coordinator="lead" if running else "UNASSIGNED",
                ),
            )

        def make_stale(root: Path, text: str) -> tuple[Path, Path]:
            path, state_path = write_gate_b_bound_project(root, text)
            prd_path = path.with_name("PRD.md")
            prd = prd_path.read_text(encoding="utf-8").replace(
                "| TECH-0007 | PROPERTY_TESTING | Hypothesis |",
                "| TECH-0007 | PROPERTY_TESTING | Hypothesis 7 |",
                1,
            )
            prd_path.write_text(prd, encoding="utf-8")
            return path, state_path

        with tempfile.TemporaryDirectory() as directory:
            path, _state = make_stale(Path(directory), property_task("READY"))
            query_arguments = (
                (),
                ("--ready",),
                ("--safe-ready",),
                ("--task", "TASK-001"),
                ("--json",),
            )
            for arguments in query_arguments:
                with (
                    self.subTest(query=arguments),
                    mock.patch.object(
                        sys, "argv", ["task_waves.py", str(path), *arguments]
                    ),
                ):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        result = task_waves.main()
                    self.assertEqual(result, 1)
                    self.assertIn("design contract hash is stale", stderr.getvalue())
            with self.assertRaisesRegex(ValueError, "design contract hash is stale"):
                task_waves.approved_contract_values(
                    path, path.read_text(encoding="utf-8")
                )

        operations = (
            (
                "start",
                property_task("READY"),
                lambda path: task_waves.mutate_run_snapshot(
                    path,
                    operation="start",
                    run_id="RUN-0001",
                    coordinator="lead",
                ),
            ),
            (
                "claim",
                property_task("READY", running=True),
                lambda path: task_waves.claim_task_file(
                    path,
                    "TASK-001",
                    owner="lead",
                    coordinator="lead",
                    run_id="RUN-0001",
                    checkpoint="CP-0000",
                ),
            ),
            (
                "status",
                property_task("IN_PROGRESS", running=True),
                lambda path: task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="BLOCKED",
                    blocker="Observed dependency failure; route to DESIGN-10",
                    run_id="RUN-0001",
                    checkpoint="CP-0002",
                ),
            ),
            (
                "issue",
                property_task("READY"),
                lambda path: task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    issue="https://example.test/tasks/1",
                ),
            ),
            *(
                (
                    operation,
                    property_task("READY"),
                    lambda path, operation=operation: task_waves.mutate_run_snapshot(
                        path,
                        operation=operation,
                        run_id="RUN-0001",
                        coordinator="lead",
                        checkpoint="CP-0001"
                        if operation in {"pause", "complete"}
                        else None,
                    ),
                )
                for operation in ("resume", "pause", "complete")
            ),
        )
        for name, tasks_text, operation in operations:
            with (
                self.subTest(operation=name),
                tempfile.TemporaryDirectory() as directory,
            ):
                path, state_path = make_stale(Path(directory), tasks_text)
                original_tasks = path.read_text(encoding="utf-8")
                original_state = state_path.read_text(encoding="utf-8")
                with self.assertRaisesRegex(
                    ValueError, "design contract hash is stale"
                ):
                    operation(path)
                self.assertEqual(path.read_text(encoding="utf-8"), original_tasks)
                self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)

    def test_same_id_property_contract_change_invalidates_gate_b_hash(self) -> None:
        row, execution = property_execution_values()
        original = document(
            [
                task_block(
                    "TASK-001",
                    "READY",
                    requirements="REQ-0001, FR-001, PROP-001",
                    design="DES-0001; TECH: TECH-0001, TECH-0007",
                    validation_command=execution.exact_command,
                    property_execution_rows=(row,),
                )
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state = write_gate_b_bound_project(root, original)
            old_bound = execution.run_target_time_bound
            new_bound = "MIN_CASES: 250; MAX_SECONDS: 45"
            prd_path = path.with_name("PRD.md")
            prd_path.write_text(
                prd_path.read_text(encoding="utf-8").replace(old_bound, new_bound, 1),
                encoding="utf-8",
            )
            path.write_text(
                path.read_text(encoding="utf-8").replace(old_bound, new_bound, 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "design contract hash is stale"):
                task_waves.approved_contract_values(
                    path, path.read_text(encoding="utf-8")
                )

            from tests import test_bootstrap_doctor as doctor_fixtures

            prd = prd_path.read_text(encoding="utf-8")
            contract, issues = (
                task_waves.load_bootstrap_doctor().derive_design_contract(
                    prd, "DES-0001", required=True
                )
            )
            self.assertEqual(issues, [])
            self.assertIsNotNone(contract.canonical_sha256)
            prd_path.write_text(
                doctor_fixtures.set_table_value(
                    prd,
                    "## 28. Construction envelope",
                    "## 29. Gate B owner authorization record",
                    "Design contract SHA-256",
                    f"`{contract.canonical_sha256}`",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Gate B approval binding is stale"):
                task_waves.approved_contract_values(
                    path, path.read_text(encoding="utf-8")
                )

    def test_property_done_requires_structured_evidence_and_later_pass_atomically(
        self,
    ) -> None:
        row, execution = property_execution_values()
        text = observed_task_text(
            document(
                [
                    task_block(
                        "TASK-001",
                        "IN_PROGRESS",
                        requirements="REQ-0001, FR-001, PROP-001",
                        design="DES-0001; TECH: TECH-0001, TECH-0007",
                        validation_command=execution.exact_command,
                        property_execution_rows=(row,),
                    )
                ],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "docs" / "project" / "TASKS.md"
            path.parent.mkdir(parents=True)
            path.write_text(text, encoding="utf-8")
            state_path = write_matching_state(root, text)
            write_technology_register(
                root, "TECH-0001", "TECH-0007", property_rows=(row,)
            )
            verify_path = path.with_name("VERIFY.md")
            property_material = (
                "Worktree: abc1234; artifact: tests/artifacts/property-PROP-001.json"
            )
            property_source = "tests/artifacts/property-PROP-001.json"

            def completion(
                evidence_id: str,
                observed_at: str,
                *,
                status: str,
            ) -> str:
                return completion_evidence_row(
                    evidence_id=evidence_id,
                    command_or_observation=execution.exact_command,
                    result="property test observed",
                    observed_at=observed_at,
                    material=property_material,
                    durable_source=property_source,
                    status=status,
                )

            first_pass_time = "2026-07-17T00:00:00+00:00"
            failure_time = "2026-07-17T00:01:00+00:00"
            later_pass_time = "2026-07-17T00:02:00+00:00"
            generic = completion_evidence_document(
                completion("EV-1001", first_pass_time, status="LOCAL_PASS")
            )
            verify_path.write_text(generic, encoding="utf-8")
            original_tasks = path.read_text(encoding="utf-8")
            original_state = state_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Property-based test evidence"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-1001",
                    run_id="RUN-0001",
                    checkpoint="CP-0002",
                )
            self.assertEqual(path.read_text(encoding="utf-8"), original_tasks)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)

            failure = property_evidence_row(
                evidence_id="EV-1002",
                result="FAIL",
                counterexample="user=''; car_id=0",
                failure="IMPLEMENTATION_DEFECT — corrected in worktree abc1234",
                observed_at=failure_time,
            )
            first_pass = property_evidence_row(
                evidence_id="EV-1001",
                observed_at=first_pass_time,
            )
            verify_path.write_text(
                completion_evidence_document(
                    completion("EV-1001", first_pass_time, status="LOCAL_PASS"),
                    completion("EV-1002", failure_time, status="FAILED"),
                )
                + property_evidence_document(first_pass, failure),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "Status must be LOCAL_PASS or VERIFIED"
            ):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-1002",
                    run_id="RUN-0001",
                    checkpoint="CP-0002",
                )
            self.assertEqual(path.read_text(encoding="utf-8"), original_tasks)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)
            with self.assertRaisesRegex(ValueError, "latest observed.*PASS"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-1001",
                    run_id="RUN-0001",
                    checkpoint="CP-0002",
                )
            self.assertEqual(path.read_text(encoding="utf-8"), original_tasks)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)

            later_pass = property_evidence_row(
                evidence_id="EV-1003",
                observed_at=later_pass_time,
            )
            verify_path.write_text(
                completion_evidence_document(
                    completion("EV-1002", failure_time, status="FAILED"),
                    completion("EV-1003", later_pass_time, status="LOCAL_PASS"),
                )
                + property_evidence_document(
                    failure,
                    later_pass,
                ),
                encoding="utf-8",
            )
            task_waves.update_task_file(
                path,
                "TASK-001",
                coordinator="lead",
                status="DONE",
                evidence="EV-1003",
                run_id="RUN-0001",
                checkpoint="CP-0002",
            )
            self.assertEqual(
                task_waves.parse_tasks(path.read_text(encoding="utf-8"))[0].status,
                "DONE",
            )

    def test_property_done_rejects_noncomparable_version_policy_atomically(
        self,
    ) -> None:
        row, execution = property_execution_values()
        text = observed_task_text(
            document(
                [
                    task_block(
                        "TASK-001",
                        "IN_PROGRESS",
                        requirements="REQ-0001, FR-001, PROP-001",
                        design="DES-0001; TECH: TECH-0001, TECH-0007",
                        validation_command=execution.exact_command,
                        property_execution_rows=(row,),
                    )
                ],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
            )
        )
        for policy in (
            "CURRENT_LTS_AS_OF: 2026-07-01",
            "ORG_MANAGED: company baseline",
        ):
            with (
                self.subTest(policy=policy),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                path = root / "docs" / "project" / "TASKS.md"
                path.parent.mkdir(parents=True)
                path.write_text(text, encoding="utf-8")
                state_path = write_matching_state(root, text)
                write_technology_register(
                    root,
                    "TECH-0001",
                    "TECH-0007",
                    property_rows=(row,),
                    property_version_policy=policy,
                )
                observed_at = "2026-07-17T00:00:00+00:00"
                material = (
                    "Worktree: abc1234; "
                    "artifact: tests/artifacts/property-PROP-001.json"
                )
                durable_source = "tests/artifacts/property-PROP-001.json"
                path.with_name("VERIFY.md").write_text(
                    completion_evidence_document(
                        completion_evidence_row(
                            evidence_id="EV-1001",
                            command_or_observation=execution.exact_command,
                            result="property test observed",
                            observed_at=observed_at,
                            material=material,
                            durable_source=durable_source,
                            status="LOCAL_PASS",
                        )
                    )
                    + property_evidence_document(
                        property_evidence_row(
                            evidence_id="EV-1001",
                            observed_at=observed_at,
                            observed_version="0.0.1",
                        )
                    ),
                    encoding="utf-8",
                )
                original_tasks = path.read_text(encoding="utf-8")
                original_state = state_path.read_text(encoding="utf-8")

                with self.assertRaisesRegex(
                    ValueError,
                    "observed exact version does not satisfy",
                ):
                    task_waves.update_task_file(
                        path,
                        "TASK-001",
                        coordinator="lead",
                        status="DONE",
                        evidence="EV-1001",
                        run_id="RUN-0001",
                        checkpoint="CP-0002",
                    )
                self.assertEqual(path.read_text(encoding="utf-8"), original_tasks)
                self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)

    def test_property_projection_mutation_failure_is_atomic(self) -> None:
        row, execution = property_execution_values()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path = root / "docs" / "project" / "TASKS.md"
            tasks_path.parent.mkdir(parents=True)
            altered_row = row.replace(
                execution.run_target_time_bound,
                "MIN_CASES: 101; MAX_SECONDS: 30",
                1,
            )
            tasks_path.write_text(
                document(
                    [
                        task_block(
                            "TASK-001",
                            "READY",
                            requirements="REQ-0001, FR-001, PROP-001",
                            design="DES-0001; TECH: TECH-0001, TECH-0007",
                            validation_command=execution.exact_command,
                            property_execution_rows=(altered_row,),
                        )
                    ]
                ),
                encoding="utf-8",
            )
            write_technology_register(
                root,
                "TECH-0001",
                "TECH-0007",
                property_rows=(row,),
            )
            with mock.patch.object(sys, "argv", ["task_waves.py", str(tasks_path)]):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    result = task_waves.main()
            self.assertEqual(result, 1)
            self.assertIn("does not exactly match", stderr.getvalue())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path = root / "docs" / "project" / "TASKS.md"
            tasks_path.parent.mkdir(parents=True)
            altered_row = row.replace(
                execution.run_target_time_bound,
                "MIN_CASES: 101; MAX_SECONDS: 30",
                1,
            )
            original = document(
                [
                    task_block(
                        "TASK-001",
                        "BACKLOG",
                        requirements="REQ-0001, FR-001, PROP-001",
                        design="DES-0001; TECH: TECH-0001, TECH-0007",
                        validation_command=execution.exact_command,
                        property_execution_rows=(altered_row,),
                    ),
                    task_block(
                        "TASK-002",
                        "READY",
                        requirements="REQ-0001, FR-001, PROP-001",
                        design="DES-0001; TECH: TECH-0001, TECH-0007",
                        validation_command=execution.exact_command,
                        property_execution_rows=(row,),
                    ),
                ],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
            )
            tasks_path.write_text(original, encoding="utf-8")
            write_matching_state(root, original)
            write_technology_register(
                root,
                "TECH-0001",
                "TECH-0007",
                property_rows=(row,),
            )

            with self.assertRaisesRegex(ValueError, "does not exactly match"):
                task_waves.update_task_file(
                    tasks_path,
                    "TASK-001",
                    coordinator="lead",
                    status="READY",
                )
            self.assertEqual(tasks_path.read_text(encoding="utf-8"), original)

    def test_cli_and_atomic_mutation_enforce_prd_tech_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path = root / "docs" / "project" / "TASKS.md"
            tasks_path.parent.mkdir(parents=True)
            tasks_text = document(
                [
                    task_block(
                        "TASK-001",
                        "READY",
                        design="DES-0001; TECH: TECH-0002",
                    )
                ]
            )
            tasks_path.write_text(tasks_text, encoding="utf-8")
            write_technology_register(root, "TECH-0001")
            with mock.patch.object(sys, "argv", ["task_waves.py", str(tasks_path)]):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    result = task_waves.main()
            self.assertEqual(result, 1)
            self.assertIn("unapproved TECH IDs: TECH-0002", stderr.getvalue())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_path = root / "docs" / "project" / "TASKS.md"
            tasks_path.parent.mkdir(parents=True)
            original = document(
                [
                    task_block(
                        "TASK-001",
                        "BACKLOG",
                        design="DES-0001; TECH: TECH-0002",
                    )
                ],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
            )
            tasks_path.write_text(original, encoding="utf-8")
            write_matching_state(root, original)
            write_technology_register(root, "TECH-0001")

            with self.assertRaisesRegex(ValueError, "unapproved TECH IDs: TECH-0002"):
                task_waves.update_task_file(
                    tasks_path,
                    "TASK-001",
                    coordinator="lead",
                    status="READY",
                )

            self.assertEqual(tasks_path.read_text(encoding="utf-8"), original)

    def test_missing_status_metadata_is_invalid(self) -> None:
        text = task_block("TASK-001", "READY").replace("- Status: `READY`\n", "")
        tasks = task_waves.parse_tasks(text)

        with self.assertRaisesRegex(ValueError, "missing Status metadata"):
            task_waves.validate(tasks)

    def test_duplicate_singleton_metadata_is_invalid(self) -> None:
        text = task_block("TASK-001", "READY").replace(
            "- Status: `READY`",
            "- Status: `BACKLOG`\n- Status: `READY`",
        )
        tasks = task_waves.parse_tasks(text)

        with self.assertRaisesRegex(ValueError, "duplicate Status metadata"):
            task_waves.validate(tasks)

    def test_cannot_start_task_with_incomplete_dependency(self) -> None:
        text = document(
            [
                task_block(
                    "TASK-001",
                    "IN_PROGRESS",
                    owner="worker-1",
                    run_id="RUN-0001",
                ),
                task_block("TASK-002", "BACKLOG", "TASK-001"),
            ],
            snapshot_text=snapshot(
                run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
            ),
        )
        _tasks, _snap, waivers, by_id = parse_document(text)

        with self.assertRaisesRegex(ValueError, "incomplete dependencies: TASK-001"):
            task_waves.validate_status_transition(
                by_id["TASK-002"], "READY", by_id, waivers
            )

    def test_done_is_terminal_and_in_progress_cannot_requeue(self) -> None:
        done = task_waves.parse_tasks(task_block("TASK-001", "DONE"))[0]
        running = task_waves.parse_tasks(task_block("TASK-002", "IN_PROGRESS"))[0]
        by_id = {done.task_id: done, running.task_id: running}

        with self.assertRaisesRegex(ValueError, "illegal status transition"):
            task_waves.validate_status_transition(done, "IN_PROGRESS", by_id)
        with self.assertRaisesRegex(ValueError, "illegal status transition"):
            task_waves.validate_status_transition(running, "READY", by_id)

    def test_idempotent_update_does_not_change_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            original = document(
                [task_block("TASK-001", "READY")],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
            )
            path, _state_path = write_task_project(root, original)

            changed = task_waves.update_task_file(
                path, "TASK-001", coordinator="lead", status="READY"
            )

            self.assertFalse(changed)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_failed_atomic_replace_preserves_original_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            original = document(
                [task_block("TASK-001", "READY")],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
            )
            path, _state_path = write_task_project(root, original)

            with mock.patch.object(os, "replace", side_effect=OSError("disk error")):
                with self.assertRaisesRegex(OSError, "disk error"):
                    task_waves.update_task_file(
                        path,
                        "TASK-001",
                        coordinator="lead",
                        status="BLOCKED",
                        blocker="Test failure; inspect output",
                        run_id="RUN-0001",
                    )

            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(list(path.parent.glob(".TASKS.md.*.tmp")), [])

    def test_concurrent_update_fails_instead_of_losing_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "TASKS.md"
            original = document([task_block("TASK-001", "READY")])
            path.write_text(original, encoding="utf-8")

            with task_waves.task_file_lock(path):
                with self.assertRaisesRegex(ValueError, "already being updated"):
                    task_waves.update_task_file(
                        path,
                        "TASK-001",
                        coordinator="lead",
                        issue="https://example/1",
                    )

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_skipped_dependency_requires_matching_waiver(self) -> None:
        without = document(
            [
                task_block("TASK-001", "SKIPPED"),
                task_block("TASK-002", "READY", "TASK-001"),
            ]
        )
        tasks, _snap, waivers, by_id = parse_document(without)
        self.assertEqual(task_waves.ready_tasks(tasks, by_id, waivers), [])

        with_waiver = document(
            [
                task_block("TASK-001", "SKIPPED"),
                task_block(
                    "TASK-002",
                    "READY",
                    "TASK-001",
                    waivers="TASK-001=WAIVER-001",
                ),
            ],
            waiver_rows=[
                "| `WAIVER-001` | `TASK-001` | `TASK-002` | `AUTH-0001 clause 4` | Equivalent evidence EV-0009 preserves acceptance | 2026-07-17T00:00:00+00:00 |"
            ],
        )
        tasks, _snap, waivers, by_id = parse_document(with_waiver)
        self.assertEqual(
            [task.task_id for task in task_waves.ready_tasks(tasks, by_id, waivers)],
            ["TASK-002"],
        )

    def test_claim_is_atomic_and_persists_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            tasks_text = document(
                [task_block("TASK-001", "READY")],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
            )
            path, _state_path = write_task_project(root, tasks_text)

            task_waves.claim_task_file(
                path,
                "TASK-001",
                owner="lead",
                coordinator="lead",
                run_id="RUN-0001",
                checkpoint="CP-0000",
            )

            task = task_waves.parse_tasks(path.read_text(encoding="utf-8"))[0]
            self.assertEqual(task.status, "IN_PROGRESS")
            self.assertEqual(task.run_id, "RUN-0001")
            self.assertEqual(task.attempts_used, 1)
            self.assertEqual(task_waves.clean(task.metadata["Owner"]), "lead")
            self.assertEqual(
                task_waves.clean(task.metadata["Last checkpoint"]), "CP-0000"
            )
            self.assertEqual(
                task_waves.parse_snapshot(path.read_text(encoding="utf-8")).get(
                    "Last checkpoint"
                ),
                "NONE",
            )

    def test_claim_requires_current_base_without_consuming_checkpoint(self) -> None:
        for checkpoint in ("CP-0004", "CP-0006"):
            with (
                self.subTest(checkpoint=checkpoint),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                tasks_text = document(
                    [task_block("TASK-001", "READY")],
                    snapshot_text=snapshot(
                        run_state="RUNNING",
                        run_id="RUN-0001",
                        coordinator="lead",
                        last_checkpoint="CP-0005",
                    ),
                )
                path, _state_path = write_task_project(root, tasks_text)
                with self.assertRaisesRegex(ValueError, "current base CP-0005"):
                    task_waves.claim_task_file(
                        path,
                        "TASK-001",
                        owner="lead",
                        coordinator="lead",
                        run_id="RUN-0001",
                        checkpoint=checkpoint,
                    )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_text = document(
                [task_block("TASK-001", "READY")],
                snapshot_text=snapshot(
                    run_state="RUNNING",
                    run_id="RUN-0001",
                    coordinator="lead",
                    last_checkpoint="NONE",
                ),
            )
            path, _state_path = write_task_project(root, tasks_text)
            task_waves.claim_task_file(
                path,
                "TASK-001",
                owner="lead",
                coordinator="lead",
                run_id="RUN-0001",
                checkpoint="CP-0000",
            )
            updated = path.read_text(encoding="utf-8")
            self.assertEqual(
                task_waves.parse_snapshot(updated).get("Last checkpoint"), "NONE"
            )
            self.assertEqual(
                task_waves.clean(
                    task_waves.parse_tasks(updated)[0].metadata["Last checkpoint"]
                ),
                "CP-0000",
            )

    def test_exhausted_attempt_budget_fails_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            original = document(
                [task_block("TASK-001", "BACKLOG", attempt_budget=1, attempts_used=1)],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
            ).replace("- Status: `BACKLOG`", "- Status: `READY`")
            path, _state_path = write_task_project(root, original)

            with self.assertRaisesRegex(ValueError, "attempt budget exhausted"):
                task_waves.claim_task_file(
                    path,
                    "TASK-001",
                    owner="lead",
                    coordinator="lead",
                    run_id="RUN-0001",
                    checkpoint="CP-0000",
                )

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_done_blocked_and_skipped_require_records(self) -> None:
        cases = [
            ("DONE", "Evidence", "NONE"),
            ("BLOCKED", "Blocker", "NONE"),
            ("SKIPPED", "Skip record", "NONE"),
        ]
        for status, field, value in cases:
            with self.subTest(status=status):
                text = task_block("TASK-001", status)
                text = task_waves.META_LINE.sub(
                    lambda match: (
                        f"- {field}: `{value}`"
                        if match.group("key") == field
                        else match.group(0)
                    ),
                    text,
                )
                with self.assertRaisesRegex(ValueError, f"{status} requires"):
                    task_waves.validate(task_waves.parse_tasks(text))

    def test_runnable_tasks_require_objective_sections(self) -> None:
        text = task_block("TASK-001", "READY").replace(
            "#### Outcome\n\nThe task's bounded behavior is implemented and observable.\n\n",
            "",
        )
        with self.assertRaisesRegex(
            ValueError, "missing required section #### Outcome"
        ):
            task_waves.validate(task_waves.parse_tasks(text))

        done = task_block("TASK-001", "DONE").replace("- [x]", "- [ ]")
        with self.assertRaisesRegex(ValueError, "incomplete acceptance criteria"):
            task_waves.validate(task_waves.parse_tasks(done))

    def test_local_tasks_allow_only_none_or_docs_only_aws_modes(self) -> None:
        for aws_mode in ("NONE", "DOCS_ONLY"):
            with self.subTest(aws_mode=aws_mode):
                tasks = task_waves.parse_tasks(
                    task_block("TASK-001", "READY", aws_mode=aws_mode)
                )
                task_waves.validate(tasks)

        for aws_mode in ("READ_ONLY", "MUTATION"):
            with self.subTest(aws_mode=aws_mode):
                tasks = task_waves.parse_tasks(
                    task_block("TASK-001", "READY", aws_mode=aws_mode)
                )
                with self.assertRaisesRegex(
                    ValueError, f"invalid AWS mode '{aws_mode}'"
                ):
                    task_waves.validate(tasks)

    def test_safe_groups_serialize_overlaps_and_invalid_legacy_aws_mutations(
        self,
    ) -> None:
        text = document(
            [
                task_block("TASK-001", "READY", write_set="app/**"),
                task_block("TASK-002", "READY", write_set="app/api.py"),
                task_block("TASK-003", "READY", write_set="tests/api.py"),
                task_block(
                    "TASK-004",
                    "READY",
                    write_set="infrastructure/stack.py",
                    external_state="aws:stack/dev",
                    aws_mode="MUTATION",
                ),
            ]
        )
        with self.assertRaisesRegex(ValueError, "invalid AWS mode 'MUTATION'"):
            task_waves.validate(task_waves.parse_tasks(text))

        # Keep invalid legacy metadata serialized defensively before migration.
        tasks = task_waves.parse_tasks(text)
        waivers = task_waves.parse_waivers(text)
        by_id = {task.task_id: task for task in tasks}
        waves = task_waves.compute_waves(tasks, by_id)
        ready = task_waves.ready_tasks(tasks, by_id, waivers)

        isolated = task_waves.safe_execution_groups(
            ready, waves, isolated_worktrees=True, maximum_workers=1
        )
        nonisolated = task_waves.safe_execution_groups(
            ready, waves, isolated_worktrees=False
        )

        expected = [[task.task_id] for task in ready]
        self.assertEqual(
            [[task.task_id for task in group] for group in isolated], expected
        )
        self.assertEqual(
            [[task.task_id for task in group] for group in nonisolated], expected
        )
        with self.assertRaisesRegex(ValueError, "exactly 1"):
            task_waves.safe_execution_groups(
                ready, waves, isolated_worktrees=True, maximum_workers=2
            )

    def test_unsafe_write_boundaries_are_rejected(self) -> None:
        for value in (
            "../secret",
            "/tmp/file",
            ".git/config",
            ".GiT/config",
            "APP/.GIT/config",
            "app/*.py",
            "TODO",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Write set"):
                    task_waves.validate_write_boundary(value, "TASK-001")

    def test_cycle_message_is_deterministic(self) -> None:
        tasks = task_waves.parse_tasks(
            task_block("TASK-001", "BACKLOG", "TASK-002")
            + task_block("TASK-002", "BACKLOG", "TASK-001")
        )
        by_id = task_waves.validate(tasks)

        with self.assertRaisesRegex(
            ValueError,
            "TASK-001 -> TASK-002 -> TASK-001",
        ):
            task_waves.compute_waves(tasks, by_id)

    def test_run_claim_is_exclusive_and_unclean_run_is_not_auto_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            tasks_text = document([task_block("TASK-001", "READY")])
            path, _state_path = write_task_project(root, tasks_text)

            task_waves.mutate_run_snapshot(
                path,
                operation="start",
                run_id="RUN-0001",
                coordinator="lead",
            )
            with self.assertRaisesRegex(ValueError, "already exists|reconciliation"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="start",
                    run_id="RUN-0002",
                    coordinator="other",
                )

    def test_run_and_attempt_state_are_mirrored_to_bootstrap_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "TASKS.md"
            tasks_text = document([task_block("TASK-001", "READY")])
            path.write_text(tasks_text, encoding="utf-8")
            state_path = write_matching_state(root, tasks_text)

            task_waves.mutate_run_snapshot(
                path,
                operation="start",
                run_id="RUN-0001",
                coordinator="lead",
            )
            task_waves.claim_task_file(
                path,
                "TASK-001",
                owner="lead",
                coordinator="lead",
                run_id="RUN-0001",
                checkpoint="CP-0000",
            )

            mirrored = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(mirrored["execution"]["run_id"], "RUN-0001")
            self.assertEqual(mirrored["execution"]["coordinator"], "lead")
            self.assertEqual(mirrored["execution"]["state"], "RUNNING")
            self.assertEqual(mirrored["execution"]["active_tasks"], ["TASK-001"])
            self.assertEqual(mirrored["execution"]["attempts"], {"TASK-001": 1})
            with self.assertRaisesRegex(ValueError, "checkpointed run"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="resume",
                    run_id="RUN-0001",
                    coordinator="lead",
                )

    def test_fenced_examples_do_not_create_tasks_or_metadata(self) -> None:
        fake = """```markdown
### TASK-999 — Fake example

- Status: `READY`
- Attempts used: `99`
```

"""
        real = task_block("TASK-001", "READY").replace(
            "#### Validation\n",
            "#### Validation\n\n```text\n- Status: `DONE`\n```\n\n",
        )
        text = document([real]).replace(
            "## Task definitions\n\n", "## Task definitions\n\n" + fake
        )

        tasks, _snap, _waivers, _by_id = parse_document(text)

        self.assertEqual([task.task_id for task in tasks], ["TASK-001"])
        self.assertEqual(tasks[0].status, "READY")
        self.assertEqual(tasks[0].attempts_used, 0)

    def test_waiver_requires_exact_authority_timestamp_and_evidence(self) -> None:
        blocks = [
            task_block("TASK-001", "SKIPPED"),
            task_block(
                "TASK-002",
                "READY",
                "TASK-001",
                waivers="TASK-001=WAIVER-001",
            ),
        ]
        cases = [
            (
                "AUTH-00010",
                "Equivalent evidence EV-0009 preserves acceptance",
                "2026-07-17T00:00:00+00:00",
                "exact current authority",
            ),
            (
                "AUTH-0001",
                "Equivalent behavior preserves acceptance",
                "2026-07-17T00:00:00+00:00",
                "preserved evidence",
            ),
            (
                "AUTH-0001",
                "Equivalent evidence EV-0009 preserves acceptance",
                "2026-07-17",
                "UTC offset",
            ),
        ]
        for authority, rationale, recorded_at, message in cases:
            with self.subTest(message=message):
                text = document(
                    blocks,
                    waiver_rows=[
                        f"| `WAIVER-001` | `TASK-001` | `TASK-002` | `{authority}` | {rationale} | {recorded_at} |"
                    ],
                )
                with self.assertRaisesRegex(ValueError, message):
                    parse_document(text)

    def test_external_targets_overlap_hierarchically(self) -> None:
        self.assertTrue(
            task_waves.external_targets_overlap("aws:stack", "AWS:STACK/dev")
        )
        self.assertTrue(
            task_waves.external_targets_overlap("github:repo#issues", "github:repo")
        )
        self.assertFalse(
            task_waves.external_targets_overlap("aws:stack/dev", "aws:stack/prod")
        )

    def test_second_mutable_claim_is_rejected_even_with_isolated_worktrees(
        self,
    ) -> None:
        base_snapshot = snapshot(
            run_state="RUNNING",
            run_id="RUN-0001",
            coordinator="lead",
            maximum_workers=1,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            original = document(
                [
                    task_block(
                        "TASK-001",
                        "IN_PROGRESS",
                        owner="worker-a",
                        write_set="app/one.py",
                        checkpoint="CP-0000",
                    ),
                    task_block("TASK-002", "READY", write_set="tests/two.py"),
                ],
                snapshot_text=base_snapshot,
            )
            path, _state_path = write_task_project(root, original)

            with self.assertRaisesRegex(ValueError, "already IN_PROGRESS"):
                task_waves.claim_task_file(
                    path,
                    "TASK-002",
                    owner="lead",
                    coordinator="lead",
                    run_id="RUN-0001",
                    checkpoint="CP-0000",
                    isolated_worktrees=True,
                )
            self.assertEqual(path.read_text(encoding="utf-8"), original)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            original = document(
                [
                    task_block(
                        "TASK-001",
                        "IN_PROGRESS",
                        write_set="app/**",
                        checkpoint="CP-0000",
                    ),
                    task_block("TASK-002", "READY", write_set="APP/api.py"),
                ],
                snapshot_text=base_snapshot,
            )
            path, _state_path = write_task_project(root, original)
            with self.assertRaisesRegex(ValueError, "already IN_PROGRESS"):
                task_waves.claim_task_file(
                    path,
                    "TASK-002",
                    owner="lead",
                    coordinator="lead",
                    run_id="RUN-0001",
                    checkpoint="CP-0000",
                    isolated_worktrees=True,
                )
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_claim_enforces_worker_cap_protected_paths_and_control_owner(self) -> None:
        cases = [
            (
                snapshot(
                    run_state="RUNNING",
                    run_id="RUN-0001",
                    coordinator="lead",
                    maximum_workers=1,
                ),
                [
                    task_block("TASK-001", "IN_PROGRESS"),
                    task_block("TASK-002", "READY"),
                ],
                "lead",
                "already IN_PROGRESS",
            ),
            (
                snapshot(
                    run_state="RUNNING",
                    run_id="RUN-0001",
                    coordinator="lead",
                    protected_dirty_paths="app/**",
                ),
                [task_block("TASK-002", "READY", write_set="APP/api.py")],
                "lead",
                "Protected dirty paths",
            ),
            (
                snapshot(run_state="RUNNING", run_id="RUN-0001", coordinator="lead"),
                [task_block("TASK-002", "READY", write_set="TASKS.md")],
                "worker-b",
                "coordinator ownership",
            ),
        ]
        for snap, blocks, owner, message in cases:
            with (
                self.subTest(message=message),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                original = document(blocks, snapshot_text=snap)
                path, _state_path = write_task_project(root, original)
                with self.assertRaisesRegex(ValueError, message):
                    task_waves.claim_task_file(
                        path,
                        "TASK-002",
                        owner=owner,
                        coordinator="lead",
                        run_id="RUN-0001",
                        checkpoint="CP-0000",
                        isolated_worktrees=True,
                    )
                self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_two_wave_run_advances_only_after_dependency_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_text = document(
                [
                    task_block("TASK-001", "READY"),
                    task_block("TASK-002", "READY", "TASK-001"),
                ]
            )
            path, _state_path = write_task_project(root, tasks_text)
            task_waves.mutate_run_snapshot(
                path, operation="start", run_id="RUN-0001", coordinator="lead"
            )
            task_waves.claim_task_file(
                path,
                "TASK-001",
                owner="lead",
                coordinator="lead",
                run_id="RUN-0001",
                checkpoint="CP-0000",
            )
            with self.assertRaisesRegex(ValueError, "incomplete dependencies"):
                task_waves.claim_task_file(
                    path,
                    "TASK-002",
                    owner="lead",
                    coordinator="lead",
                    run_id="RUN-0001",
                    checkpoint="CP-0000",
                    isolated_worktrees=True,
                )
            path.write_text(
                observed_task_text(path.read_text(encoding="utf-8")), encoding="utf-8"
            )
            path.with_name("VERIFY.md").write_text(
                completion_evidence_document(
                    completion_evidence_row(),
                    completion_evidence_row(
                        evidence_id="EV-0002",
                        durable_source="VERIFY.md#ev-0002",
                    ),
                ),
                encoding="utf-8",
            )
            task_waves.update_task_file(
                path,
                "TASK-001",
                coordinator="lead",
                status="DONE",
                evidence=(
                    "EV-0001, EV-0002, VERIFY.md#ev-0001, "
                    "https://example.test/runs/EV-0001"
                ),
                run_id="RUN-0001",
                checkpoint="CP-0001",
            )
            self.assertEqual(
                task_waves.parse_snapshot(path.read_text(encoding="utf-8")).get(
                    "Current wave"
                ),
                "2",
            )
            task_waves.claim_task_file(
                path,
                "TASK-002",
                owner="lead",
                coordinator="lead",
                run_id="RUN-0001",
                checkpoint="CP-0001",
            )
            self.assertEqual(
                task_waves.parse_tasks(path.read_text(encoding="utf-8"))[1].status,
                "IN_PROGRESS",
            )

    def test_single_task_mode_survives_pause_resume_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = initialize_git(root)
            protected = "NONE"
            tasks_text = document(
                [task_block("TASK-001", "READY")],
                snapshot_text=snapshot(
                    baseline_commit=commit,
                    last_known_green_commit=commit,
                    protected_dirty_paths=protected,
                ),
            )
            path, state_path = write_task_project(root, tasks_text)
            verify_path = root / "VERIFY.md"
            verify_path.write_text("# Verification\n", encoding="utf-8")

            task_waves.mutate_run_snapshot(
                path,
                operation="start",
                run_id="RUN-0001",
                coordinator="lead",
                run_mode="SINGLE_TASK",
            )
            task_waves.claim_task_file(
                path,
                "TASK-001",
                owner="lead",
                coordinator="lead",
                run_id="RUN-0001",
                checkpoint="CP-0000",
            )
            path.write_text(
                observed_task_text(path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            verify_path.write_text(completion_evidence_document(), encoding="utf-8")
            task_waves.update_task_file(
                path,
                "TASK-001",
                coordinator="lead",
                status="DONE",
                evidence="EV-0001",
                run_id="RUN-0001",
                checkpoint="CP-0001",
            )
            path.write_text(
                append_checkpoint(
                    path.read_text(encoding="utf-8"),
                    checkpoint_row(
                        "CP-0002",
                        commit=commit,
                        dirty=protected,
                        next_action="resume run",
                    ),
                ),
                encoding="utf-8",
            )
            with verify_path.open("a", encoding="utf-8") as file:
                file.write("\nCP-0002: pause checkpoint evidence recorded.\n")
            task_waves.mutate_run_snapshot(
                path,
                operation="pause",
                run_id="RUN-0001",
                coordinator="lead",
                checkpoint="CP-0002",
            )
            task_waves.mutate_run_snapshot(
                path,
                operation="resume",
                run_id="RUN-0001",
                coordinator="lead",
            )
            path.write_text(
                append_checkpoint(
                    path.read_text(encoding="utf-8"),
                    checkpoint_row(
                        "CP-0003",
                        commit=commit,
                        dirty=protected,
                        next_action="release decision",
                    ),
                ),
                encoding="utf-8",
            )
            with verify_path.open("a", encoding="utf-8") as file:
                file.write("CP-0003: completion checkpoint evidence recorded.\n")
            task_waves.mutate_run_snapshot(
                path,
                operation="complete",
                run_id="RUN-0001",
                coordinator="lead",
                checkpoint="CP-0003",
            )

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["execution"]["mode"], "SINGLE_TASK")
            self.assertEqual(state["execution"]["state"], "COMPLETE")

    def test_interrupted_state_first_write_blocks_next_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "TASKS.md"
            tasks_text = document([task_block("TASK-001", "READY")])
            path.write_text(tasks_text, encoding="utf-8")
            state_path = write_matching_state(root, tasks_text)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["execution"]["attempts"]["TASK-001"] = 1
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            original = path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "reconcile before mutation"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    issue="https://github.com/example/repo/issues/1",
                )

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_wrong_run_id_and_invalid_evidence_are_rejected(self) -> None:
        text = document(
            [task_block("TASK-001", "IN_PROGRESS")],
            snapshot_text=snapshot(
                run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, text)
            with self.assertRaisesRegex(ValueError, "must match the active run"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-0001",
                    run_id="RUN-9999",
                    checkpoint="CP-0002",
                )
            with self.assertRaisesRegex(ValueError, "Evidence reference"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="tests passed",
                    run_id="RUN-0001",
                    checkpoint="CP-0002",
                )

    def test_done_requires_checkpoint_advance_and_recorded_local_evidence(self) -> None:
        text = document(
            [task_block("TASK-001", "IN_PROGRESS")],
            snapshot_text=snapshot(
                run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
            ),
        )
        text = observed_task_text(text)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, text)
            with self.assertRaisesRegex(ValueError, "new --checkpoint"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-0001",
                    run_id="RUN-0001",
                )
            with self.assertRaisesRegex(ValueError, "checkpoint must advance"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-0001",
                    run_id="RUN-0001",
                    checkpoint="CP-0001",
                )

            verify_path = path.with_name("VERIFY.md")
            verify_path.write_text(
                completion_evidence_document(
                    completion_evidence_row(
                        evidence_id="EV-0002",
                        durable_source="VERIFY.md#ev-0002",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "not recorded in VERIFY.md"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-0001",
                    run_id="RUN-0001",
                    checkpoint="CP-0002",
                )
            verify_path.write_text(
                completion_evidence_document(),
                encoding="utf-8",
            )
            task_waves.update_task_file(
                path,
                "TASK-001",
                coordinator="lead",
                status="DONE",
                evidence="EV-0001",
                run_id="RUN-0001",
                checkpoint="CP-0002",
            )
            completed = task_waves.parse_tasks(path.read_text(encoding="utf-8"))[0]
            self.assertEqual(completed.status, "DONE")
            self.assertEqual(
                task_waves.clean(completed.metadata["Last checkpoint"]), "CP-0002"
            )

    def test_done_evidence_requires_exact_unique_structured_task_row(self) -> None:
        base = observed_task_text(
            document(
                [task_block("TASK-001", "IN_PROGRESS")],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
            )
        )
        valid_table = completion_evidence_document()
        fenced_table = (
            "# Verification\n\n```markdown\n"
            + valid_table.split("\n\n", 1)[1]
            + "```\n"
        )
        cases = [
            (
                "stock token",
                "# Verification\n\nEV-0001 | TODO | NOT_STARTED\n",
                "exactly one.*Task completion evidence",
            ),
            ("fenced table", fenced_table, "exactly one.*Task completion evidence"),
            (
                "placeholder row",
                completion_evidence_document(
                    completion_evidence_row(
                        command_or_observation="TODO",
                        result="NOT_STARTED",
                    )
                ),
                "placeholder evidence",
            ),
            (
                "duplicate row",
                completion_evidence_document(
                    completion_evidence_row(), completion_evidence_row()
                ),
                "Evidence IDs must be unique",
            ),
            (
                "wrong task",
                completion_evidence_document(
                    completion_evidence_row(task_id="TASK-0010")
                ),
                "wrong task",
            ),
            (
                "URL-only source",
                completion_evidence_document(
                    completion_evidence_row(
                        durable_source="https://example.test/runs/1"
                    )
                ),
                "Durable source.*durable source",
            ),
        ]
        for name, verify_text, message in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path, state_path = write_task_project(root, base)
                (root / "VERIFY.md").write_text(verify_text, encoding="utf-8")
                original_tasks = path.read_text(encoding="utf-8")
                original_state = state_path.read_text(encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    task_waves.update_task_file(
                        path,
                        "TASK-001",
                        coordinator="lead",
                        status="DONE",
                        evidence="EV-0001",
                        run_id="RUN-0001",
                        checkpoint="CP-0002",
                    )
                self.assertEqual(path.read_text(encoding="utf-8"), original_tasks)
                self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)

    def test_done_rejects_noncanonical_local_evidence_ids(self) -> None:
        base = observed_task_text(
            document(
                [task_block("TASK-001", "IN_PROGRESS")],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
            )
        )
        for evidence in (
            "EV-001",
            "EVIDENCE-0001",
            "EV-0001-SUFFIX",
            "ev-0001",
            "VERIFY.md#ev-0001",
        ):
            with (
                self.subTest(evidence=evidence),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                path, _state_path = write_task_project(root, base)
                (root / "VERIFY.md").write_text(
                    completion_evidence_document(), encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, "Evidence reference"):
                    task_waves.update_task_file(
                        path,
                        "TASK-001",
                        coordinator="lead",
                        status="DONE",
                        evidence=evidence,
                        run_id="RUN-0001",
                        checkpoint="CP-0002",
                    )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, base)
            (root / "VERIFY.md").write_text(
                completion_evidence_document(), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "duplicate local Evidence"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-0001, EV-0001",
                    run_id="RUN-0001",
                    checkpoint="CP-0002",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, base)
            (root / "VERIFY.md").write_text(
                completion_evidence_document(), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "not recorded.*EV-0002"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-0001, EV-0002",
                    run_id="RUN-0001",
                    checkpoint="CP-0002",
                )

    def test_claim_requires_exact_coordinator(self) -> None:
        text = document(
            [task_block("TASK-001", "READY")],
            snapshot_text=snapshot(
                run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, text)
            with self.assertRaisesRegex(ValueError, "does not match"):
                task_waves.claim_task_file(
                    path,
                    "TASK-001",
                    owner="lead",
                    coordinator="other",
                    run_id="RUN-0001",
                    checkpoint="CP-0000",
                )

    def test_every_shared_mutation_binds_the_active_coordinator(self) -> None:
        running = document(
            [task_block("TASK-001", "READY")],
            snapshot_text=snapshot(
                run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, running)
            for action in ("issue", "status"):
                with (
                    self.subTest(action=action),
                    self.assertRaisesRegex(ValueError, "does not match"),
                ):
                    task_waves.update_task_file(
                        path,
                        "TASK-001",
                        coordinator="other",
                        issue="https://example.test/1" if action == "issue" else None,
                        status="READY" if action == "status" else None,
                    )
            for operation in ("pause", "complete"):
                with (
                    self.subTest(operation=operation),
                    self.assertRaisesRegex(ValueError, "does not match"),
                ):
                    task_waves.mutate_run_snapshot(
                        path,
                        operation=operation,
                        run_id="RUN-0001",
                        coordinator="other",
                        checkpoint="CP-0001",
                    )

        paused = document(
            [task_block("TASK-001", "READY")],
            snapshot_text=snapshot(
                run_state="PAUSED",
                run_id="RUN-0001",
                coordinator="lead",
                last_checkpoint="CP-0001",
            ),
            checkpoint_rows=[
                checkpoint_row(
                    "CP-0001",
                    outcomes="TASK-001 READY attempts=0/2",
                    evidence="NONE",
                )
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, paused)
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "does not match"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="resume",
                    run_id="RUN-0001",
                    coordinator="other",
                )

    def test_mutation_requires_bootstrap_state_file(self) -> None:
        text = document(
            [task_block("TASK-001", "READY")],
            snapshot_text=snapshot(
                run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASKS.md"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bootstrap.yaml is required"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    issue="https://example.test/1",
                )

    def test_uninitialized_and_stale_plans_are_readable_but_not_mutable(self) -> None:
        stale = document(
            [task_block("TASK-001", "READY")],
            snapshot_text=snapshot(
                task_plan_state="STALE",
                run_state="RUNNING",
                run_id="RUN-0001",
                coordinator="lead",
            ),
        )
        tasks, snap, _waivers, _by_id = parse_document(stale)
        self.assertEqual(snap.get("Task-plan state"), "STALE")
        self.assertEqual(len(tasks), 1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, stale)
            with self.assertRaisesRegex(ValueError, "Task-plan state CURRENT"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    issue="https://example.test/1",
                )
            with self.assertRaisesRegex(ValueError, "Task-plan state CURRENT"):
                task_waves.claim_task_file(
                    path,
                    "TASK-001",
                    owner="lead",
                    coordinator="lead",
                    run_id="RUN-0001",
                    checkpoint="CP-0000",
                )
            with self.assertRaisesRegex(ValueError, "Task-plan state CURRENT"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="pause",
                    run_id="RUN-0001",
                    coordinator="lead",
                    checkpoint="CP-0001",
                )

        uninitialized = document(
            [],
            snapshot_text=snapshot(
                task_plan="UNINITIALIZED",
                task_plan_state="UNINITIALIZED",
                current_wave="NONE",
                last_checkpoint="NONE",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, uninitialized)
            with self.assertRaisesRegex(ValueError, "Task-plan state CURRENT"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="start",
                    run_id="RUN-0001",
                    coordinator="lead",
                )

    def test_plan_state_mirror_drift_blocks_mutation(self) -> None:
        text = document(
            [task_block("TASK-001", "READY")],
            snapshot_text=snapshot(
                run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, state_path = write_task_project(root, text)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["execution"]["plan_state"] = "STALE"
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "plan_state"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    issue="https://example.test/1",
                )

    def test_resume_fails_closed_when_git_is_unavailable_or_dirty_set_drifts(
        self,
    ) -> None:
        paused = document(
            [task_block("TASK-001", "READY")],
            snapshot_text=snapshot(
                run_state="PAUSED",
                run_id="RUN-0001",
                coordinator="lead",
                last_checkpoint="CP-0001",
            ),
            checkpoint_rows=[
                checkpoint_row(
                    "CP-0001",
                    outcomes="TASK-001 READY attempts=0/2",
                    evidence="NONE",
                )
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, paused)
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            original = path.read_text(encoding="utf-8")
            with mock.patch.object(
                task_waves.subprocess, "run", side_effect=FileNotFoundError("git")
            ):
                with self.assertRaisesRegex(
                    ValueError, "Git reconciliation unavailable"
                ):
                    task_waves.mutate_run_snapshot(
                        path,
                        operation="resume",
                        run_id="RUN-0001",
                        coordinator="lead",
                    )
            self.assertEqual(path.read_text(encoding="utf-8"), original)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = initialize_git(root)
            tasks_text = document(
                [task_block("TASK-001", "READY")],
                snapshot_text=snapshot(
                    run_state="PAUSED",
                    run_id="RUN-0001",
                    coordinator="lead",
                    baseline_commit=commit,
                    last_known_green_commit=commit,
                    protected_dirty_paths="NONE",
                    last_checkpoint="CP-0001",
                ),
                checkpoint_rows=[
                    checkpoint_row(
                        "CP-0001",
                        commit=commit,
                        outcomes="TASK-001 READY attempts=0/2",
                        evidence="NONE",
                    )
                ],
            )
            path, _state_path = write_task_project(root, tasks_text)
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            (root / "unexpected.txt").write_text("drift\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "unrecorded dirty paths=unexpected.txt"
            ):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="resume",
                    run_id="RUN-0001",
                    coordinator="lead",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = initialize_git(root)
            missing_receipt = document(
                [task_block("TASK-001", "READY")],
                snapshot_text=snapshot(
                    run_state="PAUSED",
                    run_id="RUN-0001",
                    coordinator="lead",
                    baseline_commit=commit,
                    last_known_green_commit=commit,
                    protected_dirty_paths="NONE",
                    last_checkpoint="CP-0001",
                ),
            )
            path, state_path = write_task_project(root, missing_receipt)
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            original_tasks = path.read_text(encoding="utf-8")
            original_state = state_path.read_text(encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "existing checkpoint row"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="resume",
                    run_id="RUN-0001",
                    coordinator="lead",
                )
            self.assertEqual(path.read_text(encoding="utf-8"), original_tasks)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)

    def test_pause_requires_complete_unique_checkpoint_receipt(self) -> None:
        running_snapshot = snapshot(
            run_state="RUNNING",
            run_id="RUN-0001",
            coordinator="lead",
        )
        base = document(
            [task_block("TASK-001", "READY")], snapshot_text=running_snapshot
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _state_path = write_task_project(root, base)
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "existing checkpoint row"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="pause",
                    run_id="RUN-0001",
                    coordinator="lead",
                    checkpoint="CP-0001",
                )

        valid_row = checkpoint_row(
            "CP-0001",
            outcomes="TASK-001 READY attempts=0/2",
            evidence="NONE",
            next_action="resume task selection",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_text = document(
                [task_block("TASK-001", "READY")],
                snapshot_text=running_snapshot,
                checkpoint_rows=[valid_row],
            )
            path, _state_path = write_task_project(root, tasks_text)
            (root / "VERIFY.md").write_text(
                "# Verification\n\n```text\nCP-0001\n```\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "not referenced in VERIFY.md"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="pause",
                    run_id="RUN-0001",
                    coordinator="lead",
                    checkpoint="CP-0001",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incomplete_row = valid_row.replace(
                "Blockers: NONE; Next: resume task selection", "NONE"
            )
            tasks_text = document(
                [task_block("TASK-001", "READY")],
                snapshot_text=running_snapshot,
                checkpoint_rows=[incomplete_row],
            )
            path, _state_path = write_task_project(root, tasks_text)
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "blockers and next safe action"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="pause",
                    run_id="RUN-0001",
                    coordinator="lead",
                    checkpoint="CP-0001",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reused_snapshot = snapshot(
                run_state="RUNNING",
                run_id="RUN-0001",
                coordinator="lead",
                last_checkpoint="CP-0001",
            )
            tasks_text = document(
                [task_block("TASK-001", "READY")],
                snapshot_text=reused_snapshot,
                checkpoint_rows=[valid_row],
            )
            path, _state_path = write_task_project(root, tasks_text)
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "advance and may not be reused"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="pause",
                    run_id="RUN-0001",
                    coordinator="lead",
                    checkpoint="CP-0001",
                )

        duplicate = document(
            [task_block("TASK-001", "READY")],
            snapshot_text=running_snapshot,
            checkpoint_rows=[valid_row, valid_row],
        )
        with self.assertRaisesRegex(ValueError, "may not be reused"):
            task_waves.parse_checkpoint_rows(duplicate)

    def test_checkpoint_receipt_uses_exact_task_and_evidence_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_text = document(
                [
                    task_block("TASK-001", "READY"),
                    task_block("TASK-0010", "READY"),
                ],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
                checkpoint_rows=[
                    checkpoint_row(
                        "CP-0001",
                        outcomes="TASK-0010 READY attempts=0/2",
                        evidence="NONE",
                    )
                ],
            )
            path, _state_path = write_task_project(root, tasks_text)
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            tasks = task_waves.parse_tasks(tasks_text)
            snap = task_waves.parse_snapshot(tasks_text)
            with self.assertRaisesRegex(ValueError, "missing outcome for TASK-001"):
                task_waves.validate_checkpoint_receipt(
                    path, tasks_text, "CP-0001", "RUN-0001", tasks, snap
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks_text = document(
                [task_block("TASK-001", "DONE", evidence="EV-0001")],
                snapshot_text=snapshot(
                    run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                ),
                checkpoint_rows=[
                    checkpoint_row(
                        "CP-0001",
                        outcomes="TASK-001 DONE attempts=0/2",
                        evidence="EV-00010",
                    )
                ],
            )
            path, _state_path = write_task_project(root, tasks_text)
            (root / "VERIFY.md").write_text(
                completion_evidence_document() + "\nCP-0001\n", encoding="utf-8"
            )
            tasks = task_waves.parse_tasks(tasks_text)
            snap = task_waves.parse_snapshot(tasks_text)
            with self.assertRaisesRegex(
                ValueError, "evidence for TASK-001 is incomplete"
            ):
                task_waves.validate_checkpoint_receipt(
                    path, tasks_text, "CP-0001", "RUN-0001", tasks, snap
                )

    def test_checkpoint_receipt_requires_exact_attempt_fraction(self) -> None:
        for attempts in ("attempts=0/99", "attempts=0"):
            with (
                self.subTest(attempts=attempts),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                tasks_text = document(
                    [task_block("TASK-001", "READY", attempt_budget=3)],
                    snapshot_text=snapshot(
                        run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
                    ),
                    checkpoint_rows=[
                        checkpoint_row(
                            "CP-0001",
                            outcomes=f"TASK-001 READY {attempts}",
                            evidence="NONE",
                        )
                    ],
                )
                path, _state_path = write_task_project(root, tasks_text)
                (root / "VERIFY.md").write_text(
                    "# Verification\n\nCP-0001\n", encoding="utf-8"
                )
                tasks = task_waves.parse_tasks(tasks_text)
                snap = task_waves.parse_snapshot(tasks_text)
                with self.assertRaisesRegex(
                    ValueError, "attempts for TASK-001 are not explicit"
                ):
                    task_waves.validate_checkpoint_receipt(
                        path, tasks_text, "CP-0001", "RUN-0001", tasks, snap
                    )

    def test_pause_git_reconciliation_fails_closed_and_round_trips_ledgers(
        self,
    ) -> None:
        def running_receipt(commit: str, *, baseline: str | None = None) -> str:
            return document(
                [task_block("TASK-001", "READY")],
                snapshot_text=snapshot(
                    run_state="RUNNING",
                    run_id="RUN-0001",
                    coordinator="lead",
                    baseline_commit=baseline or commit,
                    last_known_green_commit=commit,
                    protected_dirty_paths="NONE",
                ),
                checkpoint_rows=[
                    checkpoint_row(
                        "CP-0001",
                        commit=commit,
                        outcomes="TASK-001 READY attempts=0/2",
                        evidence="NONE",
                    )
                ],
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, state_path = write_task_project(root, running_receipt("abc1234"))
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            original_tasks = path.read_text(encoding="utf-8")
            original_state = state_path.read_text(encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not a regular Git worktree"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="pause",
                    run_id="RUN-0001",
                    coordinator="lead",
                    checkpoint="CP-0001",
                )
            self.assertEqual(path.read_text(encoding="utf-8"), original_tasks)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = initialize_git(root)
            path, _state_path = write_task_project(
                root, running_receipt("deadbee", baseline=baseline)
            )
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "commits are not resolvable"):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="pause",
                    run_id="RUN-0001",
                    coordinator="lead",
                    checkpoint="CP-0001",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = initialize_git(root)
            path, _state_path = write_task_project(root, running_receipt(commit))
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            (root / "unexpected.txt").write_text("drift\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "unrecorded dirty paths=unexpected.txt"
            ):
                task_waves.mutate_run_snapshot(
                    path,
                    operation="pause",
                    run_id="RUN-0001",
                    coordinator="lead",
                    checkpoint="CP-0001",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = initialize_git(root)
            path, state_path = write_task_project(root, running_receipt(commit))
            (root / "VERIFY.md").write_text(
                "# Verification\n\nCP-0001\n", encoding="utf-8"
            )
            task_waves.mutate_run_snapshot(
                path,
                operation="pause",
                run_id="RUN-0001",
                coordinator="lead",
                checkpoint="CP-0001",
            )
            self.assertEqual(
                task_waves.parse_snapshot(path.read_text(encoding="utf-8")).get(
                    "Run state"
                ),
                "PAUSED",
            )
            task_waves.mutate_run_snapshot(
                path,
                operation="resume",
                run_id="RUN-0001",
                coordinator="lead",
            )
            self.assertEqual(
                task_waves.parse_snapshot(path.read_text(encoding="utf-8")).get(
                    "Run state"
                ),
                "RUNNING",
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["execution"]["state"], "RUNNING")

    def test_done_rejects_url_only_evidence_and_placeholder_execution_log(self) -> None:
        base = document(
            [task_block("TASK-001", "IN_PROGRESS")],
            snapshot_text=snapshot(
                run_state="RUNNING", run_id="RUN-0001", coordinator="lead"
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            url_text = observed_task_text(base)
            path, _state_path = write_task_project(root, url_text)
            with self.assertRaisesRegex(ValueError, "local Evidence reference"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="https://example.test/run/1",
                    run_id="RUN-0001",
                    checkpoint="CP-0002",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unchecked_only = base.replace("- [ ]", "- [x]", 1)
            path, _state_path = write_task_project(root, unchecked_only)
            (root / "VERIFY.md").write_text(
                completion_evidence_document(), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "observed Execution log"):
                task_waves.update_task_file(
                    path,
                    "TASK-001",
                    coordinator="lead",
                    status="DONE",
                    evidence="EV-0001",
                    run_id="RUN-0001",
                    checkpoint="CP-0002",
                )

    def test_cli_allows_only_one_mutation_and_rejects_ignored_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TASKS.md"
            original = document([task_block("TASK-001", "READY")])
            path.write_text(original, encoding="utf-8")
            cases = [
                (
                    [
                        "task_waves.py",
                        str(path),
                        "--start-run",
                        "RUN-0001",
                        "--coordinator",
                        "lead",
                        "--claim",
                        "TASK-001",
                        "--owner",
                        "coordinator-a",
                        "--run-id",
                        "RUN-0001",
                        "--checkpoint",
                        "CP-0001",
                    ],
                    "one mutating action",
                ),
                (
                    ["task_waves.py", str(path), "--ready", "--owner", "coordinator-a"],
                    "not valid for this action",
                ),
                (
                    [
                        "task_waves.py",
                        str(path),
                        "--set-issue",
                        "TASK-001",
                        "https://example.test/1",
                    ],
                    "--set-issue requires --coordinator",
                ),
                (
                    [
                        "task_waves.py",
                        str(path),
                        "--pause-run",
                        "RUN-0001",
                        "--checkpoint",
                        "CP-0001",
                    ],
                    "--pause-run requires --coordinator and --checkpoint",
                ),
            ]
            for argv, message in cases:
                with (
                    self.subTest(message=message),
                    mock.patch.object(sys, "argv", argv),
                ):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        result = task_waves.main()
                    self.assertEqual(result, 1)
                    self.assertIn(message, stderr.getvalue())
                    self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
