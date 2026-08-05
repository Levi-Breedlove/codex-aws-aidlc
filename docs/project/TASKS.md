# {{PROJECT_NAME}} — Construction Progress

This document shows the approved work plan, current progress, blockers, and
validation for local construction. GitHub issues may mirror this work only when
that separate update is approved.
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

Tasks begin only after the technical plan is approved. Completing a task never
authorizes GitHub publication or work in an AWS account.

## Current progress

The table above shows where construction stands and what happens next. It does
not approve new work or an external action.

## Roadmap

| State | Work |
|---|---|
| Current | No tasks generated |
| Next | Approve the technical plan, then prepare the work plan |

## Active work, blockers, and next action

No task is active yet. When construction begins, the current task card shows its
outcome, success checks, blocker, and next safe action here.

## How to read a task card

Read the status and outcome first, then the success checks. Open the technical
records only when you need task IDs, dependencies, attempt history, checkpoints,
or evidence links.

<details>
<summary>Technical task records and history</summary>

## Exact run and task state

## Active execution snapshot

This snapshot identifies the last safe place to resume. If the approved
requirements or technical plan changes, construction pauses until the work plan
is refreshed.

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

This table shows how every approved requirement is covered or why it needs no
new work. Fastlane calculates it from the existing project records.

## Coordinator contract

Codex is the only writer so task records cannot conflict. Read-only reviewers
may comment but cannot change project state.

## Status and transition contract

| Status | Meaning | Allowed next status |
|---|---|---|
| `BACKLOG` | Defined but not executable | `READY`, `BLOCKED`, `SKIPPED` |
| `READY` | All execution preconditions are currently satisfied | `IN_PROGRESS`, `BACKLOG`, `BLOCKED`, `SKIPPED` |
| `IN_PROGRESS` | Claimed inside the current run and attempt budget | `DONE`, `BLOCKED` |
| `BLOCKED` | Cannot proceed; blocker and next action are recorded | `READY`, `BACKLOG`, `SKIPPED` |
| `DONE` | Acceptance criteria and required local evidence passed | Terminal |
| `SKIPPED` | Intentionally omitted under an explicit skip record | Terminal |

These statuses show where work stands. Fastlane rejects a status change that
skips required validation or exceeds the approved plan.

## Required task record schema

These fields connect each task to the approved plan and its proof. Fastlane
maintains them automatically; owners are not expected to complete this table.

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

The technical records below remain available for audit while the task card
above stays focused on the outcome and how success will be checked.

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

| Property ID | Framework TECH ID | Exact command | Run target/time bound | Seed or reproduction format | Evidence destination |
|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO |

| Harness ID | Layer | Selected check or tool | Trigger | Basis IDs | Exact command or API | Evidence destination | Required or conditional status |
|---|---|---|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

```bash
TODO
```

#### Execution log

- <timestamped coordinator entry or NOT_STARTED>

#### Agent execution details

<details>
<summary>Technical task metadata</summary>

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

</details>
~~~

## Dependencies, waivers, and waves

This section shows which work must finish first and any approved exception.
Fastlane still changes one task at a time.

### Dependency waiver registry

| Waiver ID | Skipped task | Applies to task | Authority | Rationale and preserved acceptance evidence | Recorded at |
|---|---|---|---|---|---|
| `NONE` | `NONE` | `NONE` | `NONE` | No waivers recorded | TODO |

## Attempt budget and stop conditions

Each task has a bounded number of attempts. Fastlane stops when evidence fails,
the approved scope changes, attempts run out, or an external result is uncertain.

## Checkpoints and resume

A checkpoint records the last safe place to resume after verified work or a
separately approved external action.

| Checkpoint | Run | Time | REQ / DES / AUTH | Commit and protected dirty paths | Task outcomes and attempts | Evidence and external actions | Blockers and next safe action |
|---|---|---|---|---|---|---|---|
| `NONE` | `NONE` | TODO | `REQ-0001` / `DES-0001` / `AUTH-0001` | TODO | No work started | `NONE` | Complete Gate B; when current, run `TASK-10` |

Fastlane resumes from the latest passing checkpoint. It confirms uncertain
external work before continuing.

### Archived task-plan registry

| Plan revision | Plan state | REQ / DES / AUTH | Archive commit | Reason replaced |
|---|---|---|---|---|
| `NONE` | `UNINITIALIZED` | `REQ-0001` / `DES-0001` / `AUTH-0001` | `NONE` | No prior plan |

</details>

## Task definitions

No tasks have been prepared yet. After the technical plan is approved, Fastlane
creates a work plan from the approved requirements and design. Each task explains
the outcome, what may change, how success will be checked, any blocker, and the
evidence produced.
