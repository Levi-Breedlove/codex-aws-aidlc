# AWS Codex Fastlane Operating Guide

## Mission and routing

Fastlane turns ideas into approved requirements, AWS designs, tasks, and evidence.
`fastlane` is the sole coordinator/writer and follows the doctor-selected route;
initialized projects never repeat setup.
`maintain-fastlane` is framework-only. Launch, plan, and build aliases delegate
to `fastlane`; explanation/AWS operation skills are explicit-only, and
`LEARN-10` is only an explanation alias.

## Sources of truth

| Subject | Authority |
|---|---|
| Requirements, design, gates, construction envelope | `docs/project/PRD.md` |
| Active defect contract | `docs/project/BUGFIX.md` |
| Tasks, dependencies, waves, execution state | `docs/project/TASKS.md` |
| Observed evidence | `docs/project/VERIFY.md` |
| Deploy, rollback, recovery, operations, teardown | `docs/project/RUNBOOK.md` |
| Consequential architecture decisions | `docs/adr/` |
| Derived lifecycle mirror | `bootstrap.yaml` (never authorization) |
| Engine and package inventory | `bootstrap.manifest.json` |
| Actual behavior | Code, tests, schemas, configuration, and IaC |

Stop on disagreement; never create duplicate authority. Nested `AGENTS.md`
files may narrow but never widen this guide.

## Invariants

- Fastlane has exactly two routine owner gates: Gate A for requirements and
  Gate B for the PRD plus construction boundary.
- Only the owner may accept assumptions, approve gates, or authorize external
  actions. Reject `Codex`, `agent`, `automation`, `system`, `AI`, or a
  service as approver.
- Credentials and connector availability are not authorization. Tool access
  never widens filesystem, GitHub, Codex, or AWS boundaries.
- Requirements changes stale both gates; design or envelope changes stale Gate
  B. A stale Gate B with a current Gate A routes to `DESIGN-10`.
- The coordinator is the only writer. Challengers are read-only and cannot
  choose scope or architecture, edit files, approve gates, satisfy AWS
  evidence, or authorize actions.
- Deterministic scripts decide routes, receipt validity, task readiness, stale
  approvals, evidence completeness, and package integrity.
- Never claim a test, AWS fact, deployment, or recovery result not observed.
- Do not leave an agent-ready gate marked `BLOCKED`; make it pending-owner and
  synchronize derived snapshots.

## Project choices and safeguards

Before Gate A record project mode (`greenfield` or `brownfield`), delivery
profile (`quick-mvp`, `standard`, or `high-risk`), and AWS lane
(`documentation-only`, `read-only`, `fast-dev`, or `explicit-gate`).
A Quick MVP is one small, reversible development release. Use `high-risk`
for production, sensitive or regulated data, payments, identity, customer
isolation, shared infrastructure, irreversible work, or large outage/cost
impact. Profiles change depth without adding lifecycle gates or weakening
approval, tests, safeguards, or evidence.

Default cost posture to `MINIMIZE_TOTAL_COST; HARD_CAP_NOT_STATED`. Preserve an
owner cap as `MINIMIZE_TOTAL_COST; HARD_CAP: <ISO> <AMOUNT>`. A cap is a
ceiling, not a spending target or guaranteed billing stop. Evaluate a secure
managed serverless baseline, then select verified workload fit. Never weaken
an invariant, identity, least privilege, encryption, secrets, validation,
isolation, recovery, logging, or evidence to reduce cost.

An AWS lane describes planned access; it does not authorize a change. Mutation
requires exact current account, Region, environment, resources, operations,
finite positive cost ceiling, rollback, and expiration.

## Lifecycle

Run `python scripts/bootstrap_doctor.py --root . --json` before routing and after
each checkpoint. Load one phase reference and its canonical prompt section.

1. BOOT-00 initializes or resumes.
2. INTAKE-10 and REQ-10 create measurable requirements; ask at most three
   related decisions per response.
3. Gate A requires the exact current owner receipt and no blocking finding.
4. DESIGN-10 completes whole-system design and current material AWS evidence.
5. Gate B requires the exact current receipt and construction-envelope digest.
6. TASK-10 and BUILD-10/BUILD-20 run current approved local work. BUILD never
   deploys; AWS mutation routes through AWS-10/AWS-20.
7. RELEASE-10, AWS-10 through AWS-50, and teardown retain exact evidence and
   authorization contracts.

After valid Gate A continue to design; after valid Gate B generate tasks and
continue permitted local construction. Stop only for owner decisions, stale
scope, failed validation, unavailable material evidence, exhausted boundaries,
or missing external authority.

## Challengers and explanation

Quick MVP uses no subagent by default. Use the requirements challenger for
material ambiguity, contradiction, sensitive data, identity, payments,
migration, shared interfaces, high risk, or owner request. Use the architecture
challenger after a complete proposal for high-risk, hard-to-reverse, shared,
isolation, recovery, or owner-requested review. Both are read-only.

Use `explain-fastlane` only when explicitly invoked or asked to teach. It
changes no state and restores the pending owner action.

## Tasks, tests, and evidence

Run only dependency-ready `READY` tasks through `scripts/task_waves.py`.
Preserve IDs, boundaries, attempts, checkpoints, and transitions.
Update Task completion evidence only after passing work.

Trace requirements through acceptance, `PROP-*`, design, tasks, tests,
counterexamples, and evidence. Preserve seeds and classify failures before
correction. Never weaken an invariant or generator, discard a seed, or hide a
failure.

## AWS Core and external actions

Fresh templates require current official AWS Core before initialization:
`aws-core@agent-toolkit-for-aws` from `aws/agent-toolkit-for-aws`. Do not pin
it. Initialization requires credential-free `search_documentation` then
matching `retrieve_skill`; skill content stays external. Initialized projects
skip setup. Missing evidence pauses only setup or the affected AWS step;
connectors, memory, challengers, and installation metadata cannot replace it.

Plugin installation and native trust are owner-managed. Do not install
software, change plugin state, inspect private trust, credentials, or an AWS
account during planning.

GitHub synchronization requires current Gate B authority or explicit owner
request. AWS mutation uses AWS-10 and the exact AWS-20 receipt; teardown uses
AWS-40/AWS-50 and its distinct exact receipt.

## Brownfield and completion

Before brownfield writes, record baseline behavior, tests, interfaces, data,
security, user changes, migration, and rollback; preview collisions. Adoption
requires the owner's complete ordered decision map. Preserve user work.

Complete only when the approved outcome is implemented, checks pass, VERIFY
and RUNBOOK hold observed evidence, and authorized external tracking is
reconciled or explicitly pending.

## Agent reference

- Application: `app/AGENTS.md`
- Infrastructure/AWS: `infrastructure/AGENTS.md`
- Engine: `scripts/AGENTS.md`
- Tests: `tests/AGENTS.md`
- Phase procedures: `.agents/skills/fastlane/references/`
- Exact receipts/IDs: `prompts/CODEX-PROMPTS.md`
