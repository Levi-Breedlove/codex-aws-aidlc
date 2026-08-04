# {{PROJECT_NAME}} — Executable Tasks

`docs/project/TASKS.md` is the live construction ledger after Gate B. Task blocks are the
only authoritative task records. GitHub Issues are conditional mirrors when the
current construction authorization (`AUTH`) permits the named GitHub writes.
<!-- FASTLANE:DOCUMENT_SUMMARY:BEGIN -->
## Current state

| Field | Current value |
|---|---|
| Progress | No tasks generated |
| Current wave | None |
| Active task | None |
| Readiness | Not yet initialized |
| Blocker | None |
| Last passing checkpoint | None |
| Construction approval | Not yet initialized |
| AWS account work | Not authorized |
| Updated | Not yet initialized |
| Need from you | Run `init template`. |
| Next | Codex will verify prerequisites and initialize the project. |

## Go directly to

- [Current progress](#current-progress)
- [Roadmap](#roadmap)
- [Active work and blockers](#active-work-blockers-and-next-action)
- [Task definitions](#task-definitions)
- [Checkpoint history](#checkpoints-and-resume)
- [Exact execution state](#exact-run-and-task-state)
<!-- FASTLANE:DOCUMENT_SUMMARY:END -->

<!-- FASTLANE:HUMAN_VIEW:BEGIN -->
## What this record means

Fastlane keeps this explanation synchronized with the current project records.

### Construction progress

No tasks generated. The active task is None, and the current blocker is None.

### Current construction boundary

Construction approval is Not yet initialized; AWS account work is Not authorized. Current owner action: Run `init template`. Next, Codex will verify prerequisites and initialize the project.
<!-- FASTLANE:HUMAN_VIEW:END -->

## Current progress

The Engine-derived table above is the current progress view. It grants no new
authority and stays synchronized with the exact task records.

## Roadmap

| State | Work |
|---|---|
| Current | No tasks generated |
| Next | Complete Gate B, then derive the approved task graph |

## Active work, blockers, and next action

No task is active in the untouched template. When work begins, the current task
card shows its outcome, acceptance criteria, validation, blocker, and next safe
action here in the normal reading path.

## How to read a task card

Read status and outcome first, then acceptance criteria and validation. Expand
the exact execution records only when auditing a boundary, attempt, dependency,
checkpoint, or evidence binding.

<details>
<summary>Exact run, task, dependency, attempt, and checkpoint records</summary>

## Exact run and task state

## Active execution snapshot

This is a resumable snapshot, not a new authorization. It must match the
authoritative values in `docs/project/PRD.md`. A mismatch or stale Gate B stops construction.

| Field | Value |
|---|---|
| Task-plan revision | `UNINITIALIZED` |
| Task-plan state | `UNINITIALIZED` |
| Requirements revision | `REQ-0001` |
| Design revision | `DES-0001` |
| Construction authorization | `AUTH-0001` |
| Gate B state | `BLOCKED` |
| Run state | `NOT_STARTED` |
| Active run ID | `NONE` |
| Baseline commit | `TODO` |
| Protected dirty paths | `NONE` |
| Coordinator | `UNASSIGNED` |
| Maximum workers | `1` |
| Current wave | `NONE` |
| Last checkpoint | `NONE` |
| Last known-green commit | `TODO` |
| Next safe action | Complete Gate B; when current, run `TASK-10` |

## Derived requirement disposition contract

The Engine derives requirement coverage from the approved PRD, task cards, and
current verification evidence. This ledger never stores a second coverage source.

## Coordinator contract

Codex is the sole writer. The Deliver reference and Engine enforce task claims,
attempts, checkpoints, path ownership, GitHub limits, and AWS boundaries.

## Fastlane task methodology

TASK-10 derives small, independently verifiable work from the approved boundary.

### Fastlane Definition of Done

The Deliver reference owns the complete rule. `DONE` always requires passing
acceptance, validation, evidence, boundaries, and a current checkpoint.

## Status and transition contract

| Status | Meaning | Allowed next status |
|---|---|---|
| `BACKLOG` | Defined but not executable | `READY`, `BLOCKED`, `SKIPPED` |
| `READY` | All execution preconditions are currently satisfied | `IN_PROGRESS`, `BACKLOG`, `BLOCKED`, `SKIPPED` |
| `IN_PROGRESS` | Claimed inside the current run and attempt budget | `DONE`, `BLOCKED` |
| `BLOCKED` | Cannot proceed; blocker and next action are recorded | `READY`, `BACKLOG`, `SKIPPED` |
| `DONE` | Acceptance criteria and required local evidence passed | Terminal |
| `SKIPPED` | Intentionally omitted under an explicit skip record | Terminal |

The Engine and `task_waves.py` enforce these transitions; do not hand-edit run or claim state.

## Required task record schema

`TASK-10` creates task headings and these exact singleton metadata keys. There
is intentionally no placeholder task: `UNINITIALIZED` plus a current Gate B
routes to `TASK-10`, not construction.

| Metadata key | Required content |
|---|---|
| `Status` | One status from the transition contract |
| `Requirements` | Current REQ ID, requirement IDs, applicable acceptance/journey/PROP IDs, `WAVE-*` for the walking skeleton, and `SPIKE-*` when authorized |
| `Design` | Exact `DES-nnnn; TECH: TECH-nnnn[, TECH-nnnn...]` trace, or `DES-nnnn; TECH: NONE — no technology/toolchain impact` |
| `Authorization` | Current AUTH ID |
| `Depends on` | Stable task IDs or `NONE` |
| `Dependency waivers` | `TASK-nnn=WAIVER-nnn` entries or `NONE` |
| `Owner` | Assigned coordinator or `UNASSIGNED` |
| `Run ID` | Active run ID while `IN_PROGRESS`, otherwise `NONE` |
| `Risk` | Objective task risk classification |
| `Write set` | Exact paths or narrow globs |
| `External state` | Exact mutable targets or `NONE` |
| `AWS mode` | `NONE` or `DOCS_ONLY`; authenticated AWS work routes outside TASK/BUILD |
| `Attempt budget` | Positive integer from AUTH |
| `Attempts used` | Non-negative integer not exceeding the budget |
| `Evidence` | Evidence IDs or `NONE` before evidence exists |
| `Blocker` | Current blocker and next action, or `NONE` |
| `Skip record` | Explicit record ID or `NONE` |
| `GitHub issue` | Authorized issue URL or `PENDING_SYNC` |
| `Last checkpoint` | Coordinator checkpoint ID or `NONE` |
| `Last updated` | ISO 8601 timestamp or `TODO` before initialization |

The Deliver reference owns task generation. The Engine validates exact
requirement, acceptance, design, property, Harness, and evidence bindings.

~~~text
### <TASK-ID> — <short title>

- Status: BACKLOG
- Owner: UNASSIGNED
- Blocker: NONE
- GitHub issue: PENDING_SYNC

#### Outcome

<one observable outcome>

#### Acceptance criteria

- [ ] <objective criterion>

#### Validation

<!-- Omit this table only when Requirements contains no approved PROP-* ID. -->
| Property ID | Framework TECH ID | Exact command | Run target/time bound | Seed or reproduction format | Evidence destination |
|---|---|---|---|---|---|
| <copy one exact approved PRD row per referenced PROP-ID> |

<!-- Omit this table only when this task owns no REQUIRED Harness row. -->
| Harness ID | Layer | Selected check or tool | Trigger | Basis IDs | Exact command or API | Evidence destination | Required or conditional status |
|---|---|---|---|---|---|---|---|
| <copy each owned REQUIRED PRD Harness row; every required ID appears in exactly one task> |

```bash
<each exact property and Harness command owned by this task, once>
```

#### Execution log

- <timestamped coordinator entry or NOT_STARTED>

#### Exact execution metadata

- Requirements: <current REQ ID and requirement IDs>
- Design: <DES-nnnn; TECH: TECH-nnnn[, TECH-nnnn...] or DES-nnnn; TECH: NONE — no technology/toolchain impact>
- Authorization: <current AUTH ID>
- Depends on: NONE
- Dependency waivers: NONE
- Run ID: NONE
- Risk: <objective risk>
- Write set: <exact paths or narrow globs>
- External state: NONE
- AWS mode: NONE
- Attempt budget: <positive integer from AUTH>
- Attempts used: 0
- Evidence: NONE
- Skip record: NONE
- Last checkpoint: NONE
- Last updated: <ISO 8601 timestamp>
~~~

## Dependencies, waivers, and waves

Dependencies determine structural waves, never parallel mutable work. Any
waiver must preserve the approved acceptance and authority boundary.

### Dependency waiver registry

| Waiver ID | Skipped task | Applies to task | Authority | Rationale and preserved acceptance evidence | Recorded at |
|---|---|---|---|---|---|
| `NONE` | `NONE` | `NONE` | `NONE` | No waivers recorded | TODO |

## Attempt budget and stop conditions

The Engine enforces the authorized attempt budget and stops on stale gates,
boundary drift, failed evidence, exhausted attempts, or uncertain external state.

## Checkpoints and resume

The coordinator records one durable checkpoint after each validated task or
wave and before or after any separately authorized external action.

| Checkpoint | Run | Time | REQ / DES / AUTH | Commit and protected dirty paths | Task outcomes and attempts | Evidence and external actions | Blockers and next safe action |
|---|---|---|---|---|---|---|---|
| `NONE` | `NONE` | TODO | `REQ-0001` / `DES-0001` / `AUTH-0001` | TODO | No work started | `NONE` | Complete Gate B; when current, run `TASK-10` |

Resume only from a current Engine-validated checkpoint; never blindly repeat an external action.

### Archived task-plan registry

| Plan revision | Plan state | REQ / DES / AUTH | Archive commit | Reason replaced |
|---|---|---|---|---|
| `NONE` | `UNINITIALIZED` | `REQ-0001` / `DES-0001` / `AUTH-0001` | `NONE` | No prior plan |

</details>

## Task definitions

No tasks have been generated. After Gate B is current, run `TASK-10` when the
plan state is `UNINITIALIZED` or `STALE` to create or replace the current
`TASK-nnn` graph from the approved REQ/DES/AUTH envelope. Preserve the stale
graph in its archive commit and registry row; never reuse its task IDs. Each task
must include an observable outcome, bounded scope, objective acceptance criteria,
exact validation commands, evidence references, blockers, and an execution log.
