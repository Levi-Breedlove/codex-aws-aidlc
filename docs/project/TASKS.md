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

Read the status and outcome first, then the success checks. Each check names
the approved outcome and the evidence needed to demonstrate it. Open the technical
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

## Task record template

The exact task cards below preserve the approved basis, bounded work, validation,
attempt history, and evidence needed to resume safely. Fastlane maintains their
technical format automatically.

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

#### Technical execution details

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
