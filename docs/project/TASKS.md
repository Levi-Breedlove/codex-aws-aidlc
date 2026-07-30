# {{PROJECT_NAME}} — Executable Tasks

`docs/project/TASKS.md` is the live construction ledger after Gate B. Task blocks are the
only authoritative task records. GitHub Issues are conditional mirrors when the
current construction authorization (`AUTH`) permits the named GitHub writes.

Gate A and Gate B are the only routine human gates. Task readiness, wave
selection, checkpoints, verification, deployment preflight, and release checks
are execution controls inside an approved envelope; they are not additional
human gates.

## How to read a task card

Start with four visible fields: status, owner, blocker, and GitHub issue. Then
read the Outcome, Acceptance criteria, and Validation sections to understand
what will change, what “done” means, and how the result will be proved.

The collapsed **Agent execution details** section contains exact requirement,
design, authorization, dependency, write-boundary, attempt, evidence, and
checkpoint data. Those fields keep a long-running Codex session safe and
resumable; a human normally needs them only when reviewing a boundary or
investigating a stop.

## Agent reference — exact run and task state

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

Run state is one of `NOT_STARTED`, `RUNNING`, `PAUSED`, `BLOCKED`, or
`COMPLETE`. Task-plan state is exactly `UNINITIALIZED`, `CURRENT`, or `STALE`.
Use monotonic IDs such as `PLAN-0001`, `RUN-0001`, and `CP-0001`. Update this
snapshot only at a coordinator checkpoint.

Lifecycle prompts update this snapshot before task generation. REQ-10 copies a
new requirements identity and makes construction non-runnable; an agent-ready
Gate A is `PENDING_OWNER_APPROVAL`. DESIGN-10 copies the current REQ/DES/AUTH,
authorized single-writer limit, baseline, and protected dirty paths and sets an
agent-ready Gate B to `PENDING_OWNER_APPROVAL`. DESIGN-20 acceptance changes the
snapshot to `APPROVED_FOR_CONSTRUCTION` in the same checkpoint as docs/project/PRD.md and
bootstrap.yaml. A stale gate or identity mismatch sets the run to `BLOCKED` and
never silently retargets existing tasks. Before marking a plan `STALE`,
reconcile every `IN_PROGRESS` task to `DONE` with evidence or `BLOCKED` with the
observed revision blocker, checkpoint and commit the stale ledger, then stop all
claims. After a new Gate B, TASK-10 archives the stale plan by commit, replaces
its graph with tasks for the current IDs, and sets the new plan `CURRENT`.

## Derived requirement disposition contract

This ledger does not store a second manually maintained coverage table. For a
`CURRENT` plan based on a modern, non-grandfathered requirements schema, the
Engine projects the approved first-release requirements, task `Requirements`
traces, and current `docs/project/VERIFY.md` no-task evidence into exactly one
derived disposition per requirement:

- `TASK_COVERED` — one or more non-`SKIPPED` `BACKLOG`, `READY`,
  `IN_PROGRESS`, `BLOCKED`, or `DONE` task cards contain the current `REQ-*`
  identity and the exact requirement ID plus its canonical `AC-*` ID.
- `ALREADY_SATISFIED` — no task is needed because a current-scoped concrete
  Verification matrix row has `Task IDs` equal to `NONE`, binds exactly that
  requirement and canonical acceptance ID, and has status `LOCAL_PASS` or
  `VERIFIED`.
- `NOT_APPLICABLE` — no task is needed only when the approved EARS form is
  `OPTIONAL_FEATURE` and a current-scoped concrete Verification matrix row
  binds the exact requirement and canonical acceptance ID with status
  `NOT_APPLICABLE`.

Multiple task IDs or evidence IDs may support one derived disposition. A
`SKIPPED` task never supplies requirement coverage, and task coverage conflicts
with `NOT_APPLICABLE` evidence. Missing pairs, unknown or duplicate traces,
conflicting evidence, stale scope, and uncovered requirement IDs are Codex-owned
task replanning, not an owner decision or approval gate. Only a genuine change
to the approved requirement, design, envelope, or authority uses the existing
gate invalidation rules.

The additive Engine JSON under `tasks` reports
`requirement_coverage_complete`, `requirement_coverage`, and
`missing_requirement_ids`. Each `requirement_coverage` item contains
`requirement_id`, `acceptance_id`, `disposition`, `task_ids`, and
`evidence_ids`. These fields are a deterministic projection, never a new source
of truth or authorization.

## Coordinator contract

- One coordinator owns task selection, claims, implementation, checkpoints, and
  every write to application, infrastructure, project ledgers, manifests,
  lockfiles, schemas, generated output, and GitHub metadata.
- `Maximum workers` remains `1` for task claims and mutable execution. A
  conditional challenger may return one synchronous read-only critique at its
  defined checkpoint; it is not a worker, claims no task, and changes no state.
  No subagent or worker edits files or mutable external state.
- Each path and mutable target has exactly one writer. Treat ambiguous globs,
  generated output, the same branch, stack, state backend, or database as
  overlapping.
- The coordinator records task ID, checkpoint, REQ/DES/AUTH IDs, changed paths,
  commands/results, evidence IDs, external actions, and deviations before DONE.
- GitHub writes occur only when the current AUTH names the repository and
  operation. Otherwise retain `PENDING_SYNC`.
- Local tasks use only AWS mode `NONE` or `DOCS_ONLY`. If a task reaches
  authenticated AWS work, checkpoint its local state and route account reads
  through AWS-10, deployment mutations through AWS-20, and teardown mutations
  through AWS-50. Task metadata never carries authenticated read or mutation
  authority; Gate B remains only the maximum planned AWS ceiling.
## Fastlane task methodology

Task cards trace to approved EARS requirement IDs; they are not written in EARS
and contain no `EARS form`, `INVEST`, `THIN_SLICE`, or `DEFINITION_OF_DONE`
metadata fields.

Apply the Fastlane INVEST profile when TASK-10 creates the graph:

- **Independent:** only necessary dependencies and one writer.
- **Negotiable:** implementation details may vary only inside the approved
  DES/AUTH boundary.
- **Valuable:** one user- or operator-observable approved outcome.
- **Estimable:** bounded paths, dependencies, risks, commands, and attempt
  budget.
- **Small:** one coherent implementation-and-validation cycle.
- **Testable:** objective acceptance criteria and exact validation commands.

Prefer a Thin Vertical Slice when the selected architecture permits it. A
legitimate migration-only, security-only, infrastructure-only, or evidence-only
task does not need artificial vertical behavior, but it still needs one
coherent outcome and independent evidence.

For `NEW_BUILD`, the Gate-B-approved first construction wave implements one
tested end-to-end user journey. It is the only first-wave task unless a
documented, time-boxed, disposable technical spike blocks that path. The spike
may record learning, but its code is discarded and it cannot satisfy the
approved outcome or replace the earliest non-spike end-to-end task.

### Fastlane Definition of Done

The existing DONE transition remains authoritative. A task is DONE only when:

- all acceptance criteria pass;
- exact validation ran and passed;
- applicable property tests pass;
- observed evidence is recorded;
- the task remained inside REQ/DES/AUTH and write boundaries;
- execution log and checkpoint state are current;
- no unresolved blocker or placeholder remains; and
- required documentation and runbook changes are complete.


## Status and transition contract

| Status | Meaning | Allowed next status |
|---|---|---|
| `BACKLOG` | Defined but not executable | `READY`, `BLOCKED`, `SKIPPED` |
| `READY` | All execution preconditions are currently satisfied | `IN_PROGRESS`, `BACKLOG`, `BLOCKED`, `SKIPPED` |
| `IN_PROGRESS` | Claimed inside the current run and attempt budget | `DONE`, `BLOCKED` |
| `BLOCKED` | Cannot proceed; blocker and next action are recorded | `READY`, `BACKLOG`, `SKIPPED` |
| `DONE` | Acceptance criteria and required local evidence passed | Terminal |
| `SKIPPED` | Intentionally omitted under an explicit skip record | Terminal |

- `BACKLOG` is never runnable. Only an explicitly `READY` task may be claimed.
- Only a `CURRENT` task plan may be validated for execution or claimed;
  `UNINITIALIZED` and `STALE` route to TASK-10.
- An interrupted task remains `IN_PROGRESS` until the coordinator reconciles
  its paths and external state. Do not hide partial work by returning it to
  `READY`.
- `DONE` and `SKIPPED` are audit-terminal. Represent later work with a new task.
- `READY` requires current matching REQ/DES/AUTH IDs, resolved inputs, a concrete
  write set and external-state set, available attempt budget, objective
  validation, and satisfied dependencies.
- `IN_PROGRESS` requires an assigned owner, incremented attempt count, and base
  checkpoint; its `Run ID` must equal the snapshot's active run. `DONE` requires
  recorded evidence. `BLOCKED` requires a blocker and smallest useful next
  action. `SKIPPED` requires an explicit skip record.

Use the coordinator-owned tool for validation and atomic task updates:

```bash
python scripts/task_waves.py docs/project/TASKS.md
python scripts/task_waves.py docs/project/TASKS.md --ready --json
```

The ready result is a candidate list; the coordinator claims one task at a time.

Use the next unused monotonic IDs and these command shapes; do not hand-edit
claim or run fields:

```bash
# Start exactly one task or an autonomous run.
python scripts/task_waves.py docs/project/TASKS.md --start-run RUN-0001 --coordinator codex-coordinator --run-mode SINGLE_TASK
python scripts/task_waves.py docs/project/TASKS.md --start-run RUN-0001 --coordinator codex-coordinator --run-mode AUTONOMOUS

# Claim one serialized task only after the run is RUNNING.
python scripts/task_waves.py docs/project/TASKS.md --claim TASK-0001 --owner codex-coordinator --run-id RUN-0001 --coordinator codex-coordinator --checkpoint CP-0000

# Reconcile every IN_PROGRESS task, then pause or complete.
python scripts/task_waves.py docs/project/TASKS.md --set-status TASK-0001 DONE --evidence EV-0001 --run-id RUN-0001 --coordinator codex-coordinator --checkpoint CP-0001
python scripts/task_waves.py docs/project/TASKS.md --pause-run RUN-0001 --coordinator codex-coordinator --checkpoint CP-0002

# Resume only the same safely checkpointed run and coordinator.
python scripts/task_waves.py docs/project/TASKS.md --resume-run RUN-0001 --coordinator codex-coordinator
```

Use `--complete-run RUN-0001 --coordinator codex-coordinator --checkpoint
CP-0002` only when all tasks are terminal. Every mutation names the exact active
coordinator. Each claim cites the current base checkpoint and each
`IN_PROGRESS` reconciliation advances to the next unique
checkpoint. Pause or completion then consumes a later unique checkpoint and
requires its newest complete row and docs/project/VERIFY.md reference; do not reuse CP-0001.
Run start and issue synchronization do not create fictional checkpoints. A
persisted `RUNNING` state is recovery-required, not automatically resumable.

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

For every modern approved requirement cited by a task, `Requirements` contains
the exact requirement ID and its canonical acceptance ID together; neither may
appear without the other. The current `REQ-*` identity remains mandatory on
every task card. A task may cover several approved pairs, and an approved pair
may be implemented by several non-skipped tasks.

When a task implements or verifies an approved property, include its `PROP-*`
IDs in `Requirements` and copy its complete PRD Property execution row into one
exact projection table under `Validation`. The framework `TECH-*`, command, run
bound, seed/reproduction format, and evidence destination must match the PRD
byte-for-byte after Markdown cell normalization, and the exact command must also
appear once in the fenced command list. Omit the projection table only when no
approved property applies. A DONE task must cite the matching property
`EV-nnnn` row in `docs/project/VERIFY.md`. That row must bind the same task,
REQ/DES/AUTH trace, property, framework decision and selection, command,
observed time, commit/worktree/artifact, and durable source; the latest row for
that task and property must pass the approved run target.

`TASK-10` emits every real record in this exact structural shape. The four
human-status fields remain visible and every other singleton metadata field is
kept in the collapsed agent section. Replace every angle-bracket value. In a
`CURRENT` plan, `BACKLOG` is a fully specified dependency-gated task, so do not
leave unresolved values on a `BACKLOG`, `READY`, `IN_PROGRESS`, `BLOCKED`, or
`DONE` task. The stock `UNINITIALIZED` placeholder is exempt.
Keep the exact metadata key set above: technology traceability stays inside
`Design`; do not add a separate `Technologies` metadata key.

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

#### Agent execution details

<details>
<summary>Exact metadata used by Codex and task_waves.py</summary>

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

A READY task cannot contain `TODO` in its outcome, acceptance, validation,
boundaries, or traceability. A DONE task has every acceptance checkbox checked,
non-`NONE` Evidence using `EV-nnnn` IDs (for example `EV-0001`), and an observed
execution-log entry. Each cited local ID must have exactly one explicit,
passing row under docs/project/VERIFY.md `Task completion evidence`; the task tool rejects
placeholder, duplicate, wrong-task, unfenced URL-only, and non-passing rows.
Every `BACKLOG`, `READY`, `IN_PROGRESS`, `BLOCKED`, or `DONE` task in a
`CURRENT` plan uses one of the exact `Design` forms above and preserves every
applicable property projection; TECH references are comma-separated, unique,
and contain no placeholders. `BACKLOG` contributes to plan coverage but never
appears in `--ready` and cannot be claimed until it explicitly transitions to
`READY` after its dependencies are satisfied. `SKIPPED` does not contribute to
property coverage.

## Dependencies, waivers, and waves

- `Depends on: NONE` places a task in structural Wave 1. Other wave numbers are
  derived from the dependency graph and are not manually stored.
- Missing dependencies, duplicate IDs, self-dependencies, and cycles are
  invalid.
- A `DONE` dependency is satisfied. A `SKIPPED` dependency is not satisfied by
  status alone.
- To proceed past a skipped dependency, the downstream task must declare
  `TASK-nnn=WAIVER-nnn` under `Dependency waivers`, and the waiver registry must
  name the downstream task, skipped task, rationale, evidence, and current AUTH
  clause or separate owner decision that permits the omission.
- A waiver cannot broaden scope, weaken an acceptance criterion, or conceal a
  missing security, data, migration, recovery, or release obligation. If it
  would, stop and revise Gate A or Gate B as applicable.
- Structural waves express dependency order; they do not authorize concurrent
  mutable work. The coordinator claims and executes one mutable task at a time.
  Read-only analysis may run outside task claims, but it cannot write files or
  mutable external state.
- No local task uses authenticated `READ_ONLY` or `MUTATION` mode. BUILD-10 and
  BUILD-20 checkpoint and stop at an authenticated AWS boundary: preflight
  through AWS-10, deploy only through AWS-20, reconcile deployment evidence
  through AWS-30, review residuals through AWS-40, and tear down only through
  AWS-50. Later AWS mutations remain serialized even when local paths are
  disjoint.

### Dependency waiver registry

| Waiver ID | Skipped task | Applies to task | Authority | Rationale and preserved acceptance evidence | Recorded at |
|---|---|---|---|---|---|
| `NONE` | `NONE` | `NONE` | `NONE` | No waivers recorded | TODO |

## Attempt budget and stop conditions

An attempt is one coherent implementation-and-validation cycle for a task.
Claiming a task atomically increments `Attempts used`. A materially new
hypothesis may use the next available attempt; repeating the same failed action
does not reset the budget.

Stop affected work and checkpoint when any of the following occurs:

- Gate A or Gate B is stale, expired, revoked, or inconsistent with the active
  REQ/DES/AUTH IDs;
- the requested outcome, task, path, command, GitHub operation, AWS target, or
  external-state mutation is outside AUTH;
- an attempt budget is exhausted without a materially new authorized approach;
- the coordinator discovers overlapping ownership, protected dirty work,
  unexpected generated changes, or an unattributable failing baseline;
- a new requirement, design decision, migration, destructive action, public
  exposure, IAM broadening, production/shared-resource impact, sensitive-data
  concern, or material cost change is required;
- caller identity, account, Region, environment, artifact, change set, or live
  state does not match the authorized AWS boundary;
- an external operation is partial or its result is unknown; or
- the next action cannot be validated objectively.

Record the smallest decision or boundary change needed. Do not ask routine
questions while safe tasks remain inside the current envelope.

## Checkpoints and resume

The coordinator checkpoints after every task or safe wave, before and after an
external mutation, before handing work to another session, and whenever work
pauses or stops. Gate B requires a local Git repository and resolvable baseline
commit. After each validated wave, the coordinator inspects the integrated
diff, records EV evidence, commits only authorized wave changes, updates Last
known-green commit and the checkpoint row to that commit, and then runs the Fastlane Engine.
Only after those steps may the run pause or start another wave. Never absorb a
protected dirty path into the checkpoint commit.

| Checkpoint | Run | Time | REQ / DES / AUTH | Commit and protected dirty paths | Task outcomes and attempts | Evidence and external actions | Blockers and next safe action |
|---|---|---|---|---|---|---|---|
| `NONE` | `NONE` | TODO | `REQ-0001` / `DES-0001` / `AUTH-0001` | TODO | No work started | `NONE` | Complete Gate B; when current, run `TASK-10` |

To resume, reconcile the active revisions and authorization expiry, baseline and
current worktree, protected paths, task states and owners, remaining attempt
budgets, last-known GitHub state, and last-known AWS state. Inspect an interrupted
external operation read-only and classify it as succeeded, failed, partial, or
unknown before deciding what is safe. Stop on any mismatch; never blindly rerun
a mutation.

### Archived task-plan registry

| Plan revision | Plan state | REQ / DES / AUTH | Archive commit | Reason replaced |
|---|---|---|---|---|
| `NONE` | `UNINITIALIZED` | `REQ-0001` / `DES-0001` / `AUTH-0001` | `NONE` | No prior plan |

## Task definitions

No tasks have been generated. After Gate B is current, run `TASK-10` when the
plan state is `UNINITIALIZED` or `STALE` to create or replace the current
`TASK-nnn` graph from the approved REQ/DES/AUTH envelope. Preserve the stale
graph in its archive commit and registry row; never reuse its task IDs. Each task
must include an observable outcome, bounded scope, objective acceptance criteria,
exact validation commands, evidence references, blockers, and an execution log.
