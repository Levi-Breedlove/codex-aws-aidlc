# AWS Codex Fastlane Operating Guide

## Mission and routing

Fastlane turns ideas into approved requirements, AWS designs, tasks, and
evidence. `fastlane` is coordinator/writer and follows the Fastlane Engine-selected route;
initialized projects never repeat setup. Framework maintenance is separate.
Explanation/AWS skills are explicit-only; `LEARN-10` explains only.
`BUG-10`/`SYNC-10` are explicit-request adjuncts, never Engine routes; each
reruns Engine and restores route/action.

## Sources of truth

- Project docs: `PRD.md` owns requirements/design/gates/construction;
  `BUGFIX.md` the active defect; `TASKS.md` tasks/waves/state; `VERIFY.md`
  evidence; `RUNBOOK.md` operations (all under `docs/project/`).
- `PRD.md` owns the current approved architecture and technology decisions.
  Cited `docs/adr/` records preserve rationale/history and cannot override it.
  `bootstrap.yaml` is a lifecycle mirror, never authorization; the manifest inventories Engine/package files.
- Code, tests, schemas, config, and IaC own actual behavior.

Stop on disagreement/duplicate authority. Nested `AGENTS.md` may narrow, never
widen, this guide.

## Invariants

- Exactly two owner gates: Gate A approves requirements; Gate B the
  PRD/construction boundary.
- Only the owner accepts assumptions, approves gates, or authorizes external
  actions; reject `Codex`, `agent`, `automation`, `system`, `AI`, or services.
- Credentials and connector availability are not authorization. Tool access
  never widens filesystem, GitHub, Codex, or AWS boundaries.
- Requirement changes stale both gates; design/envelope changes stale Gate B.
  A stale Gate B with a current Gate A routes to `DESIGN-10`.
- Every descendant subagent is read-only and cannot spawn a writer, edit scope/
  state, claim tasks, approve/authorize, supply AWS evidence, or operate AWS.
- Deterministic scripts decide routes, receipts, readiness/staleness, evidence,
  and package integrity; only the coordinator writes.
- Never claim unobserved tests, AWS facts, deployments, or recovery results.
- Do not leave an agent-ready gate marked `BLOCKED`; make it pending-owner and
  synchronize derived snapshots.

## Choices and safeguards

Before Gate A record mode (`greenfield`/`brownfield`), profile (`quick-mvp`,
`standard`, or `high-risk`), and lane (`documentation-only`, `read-only`,
`fast-dev`, or `explicit-gate`).
A Quick MVP is one small, reversible development release. Use `high-risk` for
production; sensitive/regulated data; payments/identity; customer isolation/
shared infrastructure; irreversible work; or large outage/cost impact. Profiles
change depth without adding lifecycle gates or weakening approval, tests,
safeguards, or evidence.

Default `MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED`; preserve owner caps as
`MINIMIZE_TOTAL_COST; HARD_CAP: <ISO> <AMOUNT>`. Caps are ceilings, not targets
or guaranteed stops. Evaluate secure managed serverless, then verified fit.
Never weaken an invariant, identity, least privilege, encryption, secrets,
validation, isolation, recovery, logging, or evidence for cost.

An AWS lane describes planned access; it does not authorize a change. Mutation
requires exact current account, Region, environment, resources, operations,
finite positive cost ceiling, rollback, and expiry.

## Lifecycle

Run `python scripts/bootstrap_doctor.py --root . --json` before routing and
after checkpoints; load only its phase reference/prompt. Order:
BOOT-00 -> INTAKE-10/REQ-10 -> Gate A -> DESIGN-10 -> Gate B -> TASK-10 ->
BUILD-10/20 -> RELEASE-10 -> optional AWS-10..50. Intake asks at most three
related decisions. Gates need exact owner receipts; Gate B binds the envelope.
Gate A -> design; Gate B -> build; BUILD-10 may advance to BUILD-20. BUILD never
deploys: AWS-10/20 mutation returns through read-only AWS-30. BUG-10/SYNC-10
never alter route/authority and rerun Engine. Stop only for owner decisions,
stale/conflicting scope, failed validation/evidence, exhausted boundaries, or
missing authority.

## Challengers and explanation

`Maximum workers: 1` governs task claims and mutable execution. Codex is sole
coordinator/writer. At its checkpoint one conditional synchronous read-only
challenger may run. It is not a worker: it claims no task, changes no state,
cannot write/select/approve/authorize/satisfy AWS evidence; Quick MVP uses none
otherwise.

`explain-fastlane` runs only when asked; it changes no state/restores action.

## Tasks, tests, evidence

Run only dependency-ready `READY` tasks via `scripts/task_waves.py`; preserve
IDs/boundaries/attempts/checkpoints/transitions. Update Task completion evidence
only after passing work. Trace acceptance/`PROP-*`/design/tasks/tests/evidence;
preserve seeds, classify failures, and never weaken an invariant/generator,
discard seeds, or hide failure.

## AWS Core and external actions

Fresh templates require current official AWS Core before initialization:
`aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws`. Do not pin.
Initialize credential-free with `search_documentation` then matching
`retrieve_skill`; content stays external. Initialized projects skip setup.
Missing evidence pauses only the affected step; cached/delegated material
cannot replace it. Plugin/trust are owner-managed. During planning do not
install, change plugin state, inspect trust/credentials, or access AWS.

SYNC-10 allows only current-Gate-B or explicit-owner GitHub work, then reruns
Engine. AWS-20 records pre-mutation STARTED plus one terminal; lone STARTED gets
Codex-owned UNKNOWN closure before owner action/AWS-30 reads. Attempt deployment/
read provenance is immutable. AWS-30 needs current read authority: one STALE
may retry under different authority; a second needs safety review; nothing
follows COMPLETE/BLOCKED. RELEASE-10 stores terminal Evidence ID as cutoff.
Retry needs a new Attempt ID plus new explicit-gate receipt or fresh fast-dev
approval. Prior authority grants neither reads nor replay. AWS-40/50 teardown
has a distinct receipt.

Gate B expiry/staleness after valid STARTED never revives construction/mutation
authority or erases the attempt. Engine may project only
`deployment_journal_closure_authority` for bounded VERIFY closure: append lone-
STARTED UNKNOWN, marked read provenance/AWS-30, or RELEASE-10 cutoff. Rows are
append-only; ordinary write/construction/mutation authority is invalid/NONE and
app/task/runbook writes are prohibited. Closure requires STARTED under then-
current recorded mutation authority and a valid journal; expiry relaxes only
`GATE_B_AUTHORITY_EXPIRED`. Receipt, hash, state, journal, scope, timing, or
evidence defects fail closed.

## Brownfield and completion

Before brownfield writes record baseline behavior, tests, interfaces, data,
security, user changes, migration, rollback, and collisions. Preserve user work;
adoption requires the owner's complete ordered decision map.

Complete only when outcome/checks pass, VERIFY/RUNBOOK hold observed evidence,
and external tracking is reconciled or explicitly pending.

## Agent reference

App/AWS/Engine/tests: nested `AGENTS.md`; phases:
`.agents/skills/fastlane/references/`; receipts: `prompts/CODEX-PROMPTS.md`.
