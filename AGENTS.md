# AWS Codex Fastlane Operating Guide

## Mission and routing

`fastlane` coordinates/writes, follows the Fastlane Engine-selected route, and
initialized projects never repeat setup. Maintenance is separate. `LEARN-10`
explains on request. `BUG-10`/`SYNC-10` are adjuncts, not Engine
routes; each reruns Engine and restores route/action.
## Sources of truth

`PRD.md` owns requirements/design/gates/construction/architecture/technology;
`BUGFIX.md` the defect; `TASKS.md` task state; `VERIFY.md` evidence; `RUNBOOK.md`
operations (under `docs/project/`). ADRs are history only. `bootstrap.yaml` is
a mirror; the manifest inventories the package. Code/tests/schemas/config/IaC
own behavior. Stop duplicate/conflicting authority. Nested `AGENTS.md` may
narrow, never widen, this guide.
## Invariants

- Exactly two owner gates: Gate A requirements; Gate B PRD/construction.
- Only the owner accepts assumptions, approves gates, or authorizes external
  actions; reject `Codex`, `agent`, `automation`, `system`, `AI`, or services.
- Credentials and connector availability are not authorization. Tool access
  never widens filesystem, GitHub, Codex, or AWS boundaries.
- Requirement changes stale both gates; design/envelope changes stale Gate B.
  A stale Gate B with a current Gate A routes to `DESIGN-10`.
- Every descendant subagent is read-only and cannot spawn a writer, edit state,
  claim tasks, approve/authorize, supply AWS evidence, or operate AWS.
- Deterministic scripts own routes, receipts, readiness, evidence, and package
  integrity; only the coordinator writes.
- Never claim unobserved tests, AWS facts, deployments, or recovery results.
- Do not leave an agent-ready gate marked `BLOCKED`; make it pending-owner and
  synchronize derived snapshots.
## Choices and safeguards

Before Gate A record mode (`greenfield`/`brownfield`), profile (`quick-mvp`,
`standard`, or `high-risk`), and lane (`documentation-only`, `read-only`,
`fast-dev`, or `explicit-gate`). A Quick MVP is one small, reversible development release.
Use `high-risk` for production, regulated data, payments/identity, shared
infrastructure, irreversible work, or large outage/cost impact. Profiles change
depth without adding lifecycle gates or weakening safeguards/evidence.

Default `MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED`; preserve owner caps as
`MINIMIZE_TOTAL_COST; HARD_CAP: <ISO> <AMOUNT>`. Caps are ceilings, not targets
or guaranteed stops. Evaluate secure managed serverless, then verified fit.
Never weaken an invariant, identity, least privilege, encryption, secrets,
validation, isolation, recovery, logging, or evidence for cost.

An AWS lane describes planned access; it does not authorize a change. Mutation
requires exact account, Region, environment, resources, operations, positive
cost ceiling, rollback, and expiry.
## Lifecycle

Run `python scripts/bootstrap_doctor.py --root . --json` before routing and
after checkpoints; load only resolved slices and the selected prompt. Route:
BOOT-00 -> INTAKE-10/REQ-10 -> Gate A -> DESIGN-10 -> Gate B -> TASK-10 ->
BUILD-10/20 -> RELEASE-10 -> optional AWS-10..50. Intake asks at most three
related decisions; exact receipts bind both gates and Gate B binds construction.
Gate A continues to design and Gate B to build. BUILD never deploys; AWS mutation
returns through read-only AWS-30. BUG-10/SYNC-10 preserve route/authority and
rerun Engine. Stop only for owner decisions, conflicting scope, failed evidence,
exhausted boundaries, or missing authority.
## Challengers and explanation

`Maximum workers: 1` governs task claims and mutable execution. Codex is sole
coordinator/writer. One conditional synchronous read-only challenger may run at
its checkpoint. It is not a worker: it claims no task, changes no state, and
cannot write/select/approve/authorize/satisfy AWS evidence. Quick MVP uses none
otherwise. `explain-fastlane` runs only when asked, changes no state, and
restores the action.
## Tasks, tests, evidence

Run only dependency-ready `READY` tasks through `scripts/task_waves.py`; preserve
IDs, boundaries, attempts, checkpoints, and transitions. Update Task completion evidence
only after passing. Trace acceptance/`PROP-*`/design/tasks/tests/evidence;
preserve seeds, classify failures, and never weaken an invariant/generator,
discard seeds, or hide failure.
## AWS Core and external actions

Fresh templates require current official AWS Core before initialization:
`aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws`. Do not pin.
Initialize credential-free with `search_documentation`, then matching
`retrieve_skill`; content stays external. Initialized projects skip setup.
Missing evidence pauses its step; cache/delegation cannot replace it. Owners
manage plugin/trust; planning never changes them, inspects credentials, or accesses AWS.

GitHub and AWS stages follow the Engine; AWS stages require explicit
`operate-fastlane-aws`. That skill owns execution, journal, retry,
reconciliation, and teardown procedure; the prompt registry owns exact
receipts. The Engine alone projects current or closure authority. Ordinary
authority remains NONE unless current, and every defect fails closed.
## Brownfield and completion

Before brownfield writes record baseline behavior, tests, interfaces, data,
security, user changes, migration, rollback, and collisions. Preserve user work;
adoption requires the owner's complete ordered decision map. Complete only when
checks pass, VERIFY/RUNBOOK hold observed evidence, and external tracking is
reconciled or explicitly pending.
## Agent reference

This file owns invariants/routing. Nested `AGENTS.md` files narrow app,
AWS, Engine, or test rules; phase references own procedures;
`operate-fastlane-aws` owns AWS operations; `prompts/CODEX-PROMPTS.md` owns
exact syntax/receipts; the Engine validates and projects authority; and
`docs/WORKFLOW.md` explains the product.
